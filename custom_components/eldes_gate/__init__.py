"""Eldes gate command integration."""
import asyncio

from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import EldesClient, EldesError
from .const import CONF_DEVICE_ID, CONF_HOLD, DOMAIN

PLATFORMS = [Platform.BUTTON, Platform.BINARY_SENSOR]


class GateController:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.client = EldesClient(entry.data["username"], entry.data["password"], entry.data[CONF_DEVICE_ID])
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.lock = asyncio.Lock()
        self.sending = {"C1": False, "C2": False}
        self.errors = {"C1": False, "C2": False}

    def notify(self):
        async_dispatcher_send(self.hass, self.signal)

    async def press(self, channel):
        if self.lock.locked():
            raise HomeAssistantError("Another Eldes operation is running")
        async with self.lock:
            self.errors[channel] = False
            self.sending[channel] = True
            self.notify()
            started = asyncio.get_running_loop().time()
            try:
                await self.client.execute(channel)
                hold = self.entry.options.get(CONF_HOLD, self.entry.data[CONF_HOLD])
                remaining = hold - (asyncio.get_running_loop().time() - started)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            except EldesError as err:
                self.errors[channel] = True
                raise HomeAssistantError(str(err)) from err
            finally:
                self.sending[channel] = False
                self.notify()


async def async_setup_entry(hass, entry):
    controller = GateController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass, entry):
    controller = hass.data[DOMAIN][entry.entry_id]
    async with controller.lock:
        pass
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if hass.data[DOMAIN][entry.entry_id].lock.locked():
        return False
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
