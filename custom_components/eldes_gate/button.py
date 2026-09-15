from homeassistant.components.button import ButtonEntity
from .const import CHANNELS, DOMAIN
from .entity import EldesEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EldesButton(hass.data[DOMAIN][entry.entry_id], channel) for channel in CHANNELS])


class EldesButton(EldesEntity, ButtonEntity):
    _attr_icon = "mdi:gate"

    def __init__(self, controller, channel):
        super().__init__(controller, channel, "press")
        self._attr_translation_key = f"press_{channel.lower()}"

    async def async_press(self):
        await self.controller.press(self.channel)
