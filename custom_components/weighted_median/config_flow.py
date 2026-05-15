"""Config flow for the Weighted Median Filter helper."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import selector

from .const import (
    CONF_SOURCE_ENTITY,
    CONF_WINDOW_SECONDS,
    DEFAULT_WINDOW_SECONDS,
    DOMAIN,
    MAX_WINDOW_SECONDS,
    MIN_WINDOW_SECONDS,
)

_SCHEMA = vol.Schema(
    {
        vol.Required("name"): selector.TextSelector(),
        vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
        ),
        vol.Required(CONF_WINDOW_SECONDS, default=DEFAULT_WINDOW_SECONDS): vol.All(
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_WINDOW_SECONDS,
                    max=MAX_WINDOW_SECONDS,
                    step=1,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Coerce(int),
        ),
    }
)


class WeightedMedianConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input["name"],
                data=user_input,
            )
        return self.async_show_form(step_id="user", data_schema=_SCHEMA)
