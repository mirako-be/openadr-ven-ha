"""Config flow for OpenADR VEN integration."""
from __future__ import annotations

import os
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_VTN_URL,
    CONF_VEN_NAME,
    CONF_CERT_PATH,
    CONF_KEY_PATH,
    CONF_CA_CERT_PATH,
    CONF_VERIFY_TLS,
    CONF_TARGET_ENTITY,
    CONF_LEVEL_0_PCT,
    CONF_LEVEL_1_PCT,
    CONF_LEVEL_2_PCT,
    CONF_LEVEL_3_PCT,
    DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)


class OpenADRVENConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1
    _user_input: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1: VTN connection details."""
        errors = {}

        if user_input is not None:
            err = await self._validate_connection(user_input)
            if not err:
                self._user_input = user_input
                return await self.async_step_target()
            errors["base"] = err

        schema = vol.Schema({
            vol.Required(CONF_VTN_URL): str,
            vol.Required(CONF_VEN_NAME, default="ven-001"): str,
            vol.Required(CONF_VERIFY_TLS, default=True): bool,
            vol.Optional(CONF_CERT_PATH, default=""): str,
            vol.Optional(CONF_KEY_PATH, default=""): str,
            vol.Optional(CONF_CA_CERT_PATH, default=""): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_target(self, user_input=None):
        """Step 2: choose the target Modbus number entity."""
        if user_input is not None:
            data = {**self._user_input, **user_input}
            return self.async_create_entry(
                title=f"OpenADR VEN ({self._user_input[CONF_VEN_NAME]})",
                data=data,
                options=DEFAULTS,
            )

        schema = vol.Schema({
            vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="number")
            ),
        })

        return self.async_show_form(step_id="target", data_schema=schema)

    async def _validate_connection(self, data: dict) -> str | None:
        """Return an error key string, or None if everything looks valid."""
        for path_key in (CONF_CERT_PATH, CONF_KEY_PATH, CONF_CA_CERT_PATH):
            path = data.get(path_key, "")
            if path and not os.path.isfile(path):
                return "invalid_cert"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    data[CONF_VTN_URL],
                    ssl=data.get(CONF_VERIFY_TLS, True),
                ):
                    pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("VTN connection validation failed: %s", exc)
            return "cannot_connect"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle SIMPLE level → setpoint mapping updates."""

    def __init__(self, entry: config_entries.ConfigEntry):
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options

        schema = vol.Schema({
            vol.Required(
                CONF_LEVEL_0_PCT,
                default=opts.get(CONF_LEVEL_0_PCT, DEFAULTS[CONF_LEVEL_0_PCT]),
            ): vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(
                CONF_LEVEL_1_PCT,
                default=opts.get(CONF_LEVEL_1_PCT, DEFAULTS[CONF_LEVEL_1_PCT]),
            ): vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(
                CONF_LEVEL_2_PCT,
                default=opts.get(CONF_LEVEL_2_PCT, DEFAULTS[CONF_LEVEL_2_PCT]),
            ): vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(
                CONF_LEVEL_3_PCT,
                default=opts.get(CONF_LEVEL_3_PCT, DEFAULTS[CONF_LEVEL_3_PCT]),
            ): vol.All(int, vol.Range(min=0, max=100)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
