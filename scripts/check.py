"""Offline checks; never contacts Eldes or operates a relay."""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "custom_components").rglob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
for path in ROOT.rglob("*.json"):
    json.loads(path.read_text(encoding="utf-8"))

# Aiohttp isn't installed in the standalone runtime; only _request is mocked.
class Session:
    def __init__(self, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass

sys.modules["aiohttp"] = types.SimpleNamespace(
    ClientSession=Session, ClientTimeout=lambda **kwargs: None, ClientError=RuntimeError,
)
spec = importlib.util.spec_from_file_location("eldes_api", ROOT / "custom_components/eldes_gate/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
form = '<input value="a&amp;b" name="_csrf" type="hidden"><input name="UserLogin[email]"><input name="UserLogin[password]">'
assert api.parse_login(form) == ("_csrf", "a&b", "UserLogin[email]", "UserLogin[password]")
assert api.parse_control('deviceKey="secret"; userid = \'123\';') == ["secret", "123"]
for parser in (api.parse_login, api.parse_control):
    try:
        parser("<html></html>")
    except api.EldesError:
        pass
    else:
        raise AssertionError("Missing credentials must fail")

async def check():
    client = api.EldesClient("user", "password", "42")
    calls = []
    command_response = '{"success":true}'
    reject_login = False
    async def request(session, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/user/login":
            return (api.BASE + (path if method == "GET" or reject_login else "/devices"), form)
        if path == "/device/control/":
            return api.BASE + path, 'deviceKey="key";userid="123";'
        return api.BASE + path, command_response
    client._request = request
    await client.execute()
    assert len(calls) == 3 and all(path != "/api1" for _, path, _ in calls)
    for channel in ("C1", "C2"):
        await client.execute(channel)
        assert json.loads(calls[-1][2]["data"]["json"]) == {"vars": {channel: 1}}
    for body in ('invalid', '[]', '{"error":"denied"}', '{"success":false}'):
        command_response = body
        before = len(calls)
        try:
            await client.execute("C1")
        except api.EldesError:
            pass
        else:
            raise AssertionError("Bad response accepted")
        assert len(calls) - before == 4, "Command must not be retried"
    reject_login = True
    try:
        await client.execute("C1")
    except api.EldesAuthError:
        assert calls[-1][1] == "/user/login"
    else:
        raise AssertionError("Rejected login accepted")

asyncio.run(check())

# Exercise the actual sensor properties without requiring a running HA instance.
tree = ast.parse((ROOT / "custom_components/eldes_gate/binary_sensor.py").read_text())
sensor_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
sensor_class.bases = []
namespace = {}
exec(compile(ast.Module(body=[sensor_class], type_ignores=[]), "binary_sensor.py", "exec"), namespace)
sensor = object.__new__(namespace["EldesStatus"])
sensor.kind = "opening"
sensor.channel = "C1"
sensor.contact = ""
sensor.controller = types.SimpleNamespace(sending={"C1": False, "C2": True})
assert sensor.available and sensor.is_on is False
sensor.controller.sending["C1"] = True
assert sensor.is_on is True and sensor.extra_state_attributes["source"] == "command_timer"
sensor.contact = "binary_sensor.gate"
states = {}
sensor.hass = types.SimpleNamespace(states=types.SimpleNamespace(get=states.get))
assert not sensor.available and sensor.is_on is None
for state, available, opened in (("on", True, True), ("off", True, False), ("unavailable", False, None), ("unknown", False, None)):
    states[sensor.contact] = types.SimpleNamespace(state=state)
    assert sensor.available == available and sensor.is_on is opened
sensor.channel = "C2"
sensor.contact = ""
assert sensor.is_on is True
sensor.controller.sending["C2"] = False
assert sensor.is_on is False
print("PASS: syntax, JSON, portal parsing, safe validation, commands/errors/no retries, contact on/off/unknown/unavailable, independent timer fallback")
