"""Configure an Eldes account and device through the UI."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import EldesAuthError, EldesClient, EldesError
from .const import CONF_DEVICE_ID, CONF_HOLD, CONTACTS, DOMAIN


def contact_fields(values):
    return {
        (vol.Optional(key, default=values[key]) if values.get(key) else vol.Optional(key)):
        selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))
        for key in CONTACTS.values()
    }


class EldesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EldesOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input["username"] = user_input["username"].strip()
            user_input[CONF_DEVICE_ID] = user_input[CONF_DEVICE_ID].strip()
            await self.async_set_unique_id(f"{user_input['username'].casefold()}:{user_input[CONF_DEVICE_ID]}")
            self._abort_if_unique_id_configured()
            try:
                if not user_input["username"] or not user_input[CONF_DEVICE_ID]:
                    raise EldesError("Empty account or device")
                await EldesClient(user_input["username"], user_input["password"], user_input[CONF_DEVICE_ID]).execute()
            except EldesAuthError:
                errors["base"] = "invalid_auth"
            except EldesError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=f"Eldes {user_input[CONF_DEVICE_ID]}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): str,
            vol.Required(CONF_DEVICE_ID): str,
            vol.Required(CONF_HOLD, default=30): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
            **contact_fields({}),
        }), errors=errors)


class EldesOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            for key in CONTACTS.values():
                user_input.setdefault(key, "")
            return self.async_create_entry(title="", data=user_input)
        values = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_HOLD, default=values[CONF_HOLD]): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
            **contact_fields(values),
        }))
