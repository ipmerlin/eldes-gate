from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN


class EldesEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller, channel, kind):
        self.controller = controller
        self.channel = channel
        self._attr_unique_id = f"{controller.entry.entry_id}_{channel}_{kind}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.unique_id)},
            name=controller.entry.title, manufacturer="Eldes", model="Cloud gate controller",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.controller.signal, self.async_write_ha_state,
        ))
        if getattr(self, "kind", None) == "opening" and self.contact:
            self.async_on_remove(async_track_state_change_event(
                self.hass, [self.contact], self._contact_changed,
            ))

    @callback
    def _contact_changed(self, event):
        self.async_write_ha_state()
