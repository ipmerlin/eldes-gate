"""Eldes web portal client. No relay commands during validation."""
import json
import re
from html.parser import HTMLParser

import aiohttp

BASE = "https://security.eldes.lt"


class EldesError(Exception):
    """Portal or protocol failure."""


class EldesAuthError(EldesError):
    """Credentials rejected."""


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.fields = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "input":
            self.fields.append(dict(attrs))


def parse_login(html):
    fields = Inputs(html).fields
    csrf = next((f for f in fields if "csrf" in f.get("name", "").lower()), None)
    if not csrf or not csrf.get("value"):
        raise EldesError("Login form has no CSRF token")
    def field(*hints):
        for hint in hints:
            for item in fields:
                if hint in item.get("name", "").lower():
                    return item["name"]
        return f"UserLogin[{hints[0]}]"
    return csrf["name"], csrf["value"], field("username", "email"), field("password")


def parse_control(html):
    values = []
    for name in ("deviceKey", "userid"):
        match = re.search(rf"\b{name}\s*=\s*['\"]([^'\"]+)['\"]", html)
        if not match:
            raise EldesError("Control page has no device credentials")
        values.append(match.group(1))
    return values


class EldesClient:
    def __init__(self, username, password, device_id):
        self.username = username
        self.password = password
        self.device_id = device_id

    async def _request(self, session, method, path, **kwargs):
        try:
            async with session.request(method, BASE + path, **kwargs) as response:
                if response.status in (401, 403):
                    raise EldesAuthError("Portal denied access")
                response.raise_for_status()
                body = await response.text()
                return str(response.url), body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EldesError("Cannot communicate with Eldes") from err

    async def _authenticate(self, session):
        _, html = await self._request(session, "GET", "/user/login")
        csrf_name, csrf, login, password = parse_login(html)
        url, _ = await self._request(session, "POST", "/user/login", data={
            login: self.username, password: self.password, csrf_name: csrf,
        })
        if "/user/login" in url:
            raise EldesAuthError("Login failed")
        url, html = await self._request(session, "GET", "/device/control/", params={"id": self.device_id})
        if "/user/login" in url:
            raise EldesAuthError("Session expired")
        return parse_control(html)

    async def execute(self, channel=None):
        if channel is not None and channel not in ("C1", "C2"):
            raise ValueError("Invalid output")
        # An isolated cookie jar prevents mixing accounts with other integrations.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "HomeAssistant/EldesGate"}) as session:
            key, user = await self._authenticate(session)
            if channel is None:
                return
            url, body = await self._request(session, "POST", "/api1", params={
                "id": self.device_id, "key": key, "update": "device",
                "app": "webappAPI", "userid": user,
            }, data={"json": json.dumps({"vars": {channel: 1}})},
                headers={"X-Requested-With": "XMLHttpRequest"})
            if "/user/login" in url:
                raise EldesAuthError("Session expired")
            try:
                result = json.loads(body)
            except ValueError as err:
                raise EldesError("Command response is not JSON") from err
            if not isinstance(result, dict) or result.get("error") or result.get("success") is False:
                raise EldesError("Portal rejected command")
            # The supplied script does not document the positive acknowledgement schema.
            # Receipt of JSON is not confirmation of physical gate movement.
