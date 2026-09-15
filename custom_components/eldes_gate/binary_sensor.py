from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .const import CHANNELS, CONTACTS, DOMAIN
from .entity import EldesEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EldesStatus(hass.data[DOMAIN][entry.entry_id], channel, kind)
        for channel in CHANNELS for kind in ("sending", "error", "opening")])


class EldesStatus(EldesEntity, BinarySensorEntity):
    def __init__(self, controller, channel, kind):
        super().__init__(controller, channel, kind)
        self.kind = kind
        key = CONTACTS[channel]
        self.contact = controller.entry.options.get(key, controller.entry.data.get(key, ""))
        self._attr_translation_key = f"{kind}_{channel.lower()}"
        if kind == "error":
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        elif kind == "opening":
            self._attr_device_class = BinarySensorDeviceClass.OPENING

    @property
    def available(self):
        if self.kind != "opening" or not self.contact:
            return True
        state = self.hass.states.get(self.contact)
        return state is not None and state.state in ("on", "off")

    @property
    def extra_state_attributes(self):
        if self.kind == "opening":
            return {"source": self.contact or "command_timer", "assumed_state": not bool(self.contact)}
        return None

    @property
    def is_on(self):
        if self.kind == "opening":
            if self.contact:
                state = self.hass.states.get(self.contact)
                return state.state == "on" if state and state.state in ("on", "off") else None
            return self.controller.sending[self.channel]
        values = self.controller.errors if self.kind == "error" else self.controller.sending
        return values[self.channel]
