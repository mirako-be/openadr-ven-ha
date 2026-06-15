"""Config flow for OpenADR VEN (OpenADR 3.0)."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LEVEL_0_PCT,
    CONF_LEVEL_1_PCT,
    CONF_LEVEL_2_PCT,
    CONF_LEVEL_3_PCT,
    CONF_POLL_INTERVAL,
    CONF_TARGET_ENTITY,
    CONF_TOKEN_URL,
    CONF_VEN_NAME,
    CONF_VTN_URL,
    DEFAULT_POLL_INTERVAL,
    DEFAULTS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_CONNECTION_SCHEMA = vol.Schema({
    vol.Required(CONF_VTN_URL): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
    ),
    vol.Required(CONF_VEN_NAME): selector.TextSelector(),
    vol.Required(CONF_TOKEN_URL): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
    ),
    vol.Required(CONF_CLIENT_ID): selector.TextSelector(),
    vol.Required(CONF_CLIENT_SECRET): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    ),
})


class OpenADRVENConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step config flow: OAuth2 connection -> target entity."""

    VERSION = 1
    _connection_data: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1: VTN URL, VEN name, OAuth2 credentials."""
        errors = {}

        if user_input is not None:
            err = await self._validate(user_input)
            if not err:
                self._connection_data = user_input
                return await self.async_step_target()
            errors["base"] = err

        return self.async_show_form(
            step_id="user",
            # Repopulate fields with previously submitted values on error
            data_schema=self.add_suggested_values_to_schema(
                _CONNECTION_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_target(self, user_input=None):
        """Step 2: choose the Modbus number entity."""
        if user_input is not None:
            data = {**self._connection_data, **user_input}
            return self.async_create_entry(
                title=f"OpenADR VEN ({self._connection_data[CONF_VEN_NAME]})",
                data=data,
                options=DEFAULTS,
            )

        return self.async_show_form(
            step_id="target",
            data_schema=vol.Schema({
                vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
            }),
        )

    async def _validate(self, data: dict) -> str | None:
        """Try fetching an OAuth2 token to validate credentials."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    data[CONF_TOKEN_URL],
                    data={
                        "grant_type":    "client_credentials",
                        "client_id":     data[CONF_CLIENT_ID],
                        "client_secret": data[CONF_CLIENT_SECRET],
                    },
                ) as resp:
                    if resp.status == 401:
                        return "invalid_auth"
                    resp.raise_for_status()
                    if "access_token" not in await resp.json():
                        return "invalid_auth"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("OAuth2 validation failed: %s", exc)
            return "cannot_connect"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_LEVEL_0_PCT, default=opts.get(CONF_LEVEL_0_PCT, 100)):
                    vol.All(int, vol.Range(min=0, max=100)),
                vol.Required(CONF_LEVEL_1_PCT, default=opts.get(CONF_LEVEL_1_PCT, 75)):
                    vol.All(int, vol.Range(min=0, max=100)),
                vol.Required(CONF_LEVEL_2_PCT, default=opts.get(CONF_LEVEL_2_PCT, 50)):
                    vol.All(int, vol.Range(min=0, max=100)),
                vol.Required(CONF_LEVEL_3_PCT, default=opts.get(CONF_LEVEL_3_PCT, 0)):
                    vol.All(int, vol.Range(min=0, max=100)),
                vol.Required(CONF_POLL_INTERVAL, default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)):
                    vol.All(int, vol.Range(min=10, max=3600)),
            }),
        )
