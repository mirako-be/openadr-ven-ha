"""Config flow for OpenADR VEN integration.

Step routing:
  user            → protocol version selector
  v2_connection   → OpenADR 2.0b: VTN URL, VEN name, TLS certs
  v3_connection   → OpenADR 3.0:  VTN URL, VEN name, OAuth2 credentials
  target          → shared: Modbus number entity selector

Options flow (post-setup):
  init            → SIMPLE level mapping + poll interval (v3 only)
"""
from __future__ import annotations

import logging
import os

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CA_CERT_PATH,
    CONF_CERT_PATH,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_KEY_PATH,
    CONF_LEVEL_0_PCT,
    CONF_LEVEL_1_PCT,
    CONF_LEVEL_2_PCT,
    CONF_LEVEL_3_PCT,
    CONF_POLL_INTERVAL,
    CONF_PROTOCOL_VERSION,
    CONF_TARGET_ENTITY,
    CONF_TOKEN_URL,
    CONF_VEN_NAME,
    CONF_VERIFY_TLS,
    CONF_VTN_URL,
    DEFAULT_POLL_INTERVAL,
    DEFAULTS,
    DOMAIN,
    PROTOCOL_V2,
    PROTOCOL_V3,
    PROTOCOLS,
)

_LOGGER = logging.getLogger(__name__)


class OpenADRVENConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow supporting OpenADR 2.0b and 3.0."""

    VERSION = 2  # bumped from v1 to handle new protocol_version field
    _connection_data: dict = {}

    # ------------------------------------------------------------------
    # Step 1: protocol version
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._connection_data = {CONF_PROTOCOL_VERSION: user_input[CONF_PROTOCOL_VERSION]}
            if user_input[CONF_PROTOCOL_VERSION] == PROTOCOL_V3:
                return await self.async_step_v3_connection()
            return await self.async_step_v2_connection()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PROTOCOL_VERSION, default=PROTOCOL_V2): vol.In(PROTOCOLS),
            }),
        )

    # ------------------------------------------------------------------
    # Step 2a: OpenADR 2.0b connection
    # ------------------------------------------------------------------

    async def async_step_v2_connection(self, user_input=None):
        errors = {}

        if user_input is not None:
            err = await self._validate_v2(user_input)
            if not err:
                self._connection_data.update(user_input)
                return await self.async_step_target()
            errors["base"] = err

        schema = vol.Schema({
            vol.Required(CONF_VTN_URL): str,
            vol.Required(CONF_VEN_NAME, default="ven-001"): str,
            vol.Required(CONF_VERIFY_TLS, default=True): bool,
            vol.Optional(CONF_CERT_PATH,    default=""): str,
            vol.Optional(CONF_KEY_PATH,     default=""): str,
            vol.Optional(CONF_CA_CERT_PATH, default=""): str,
        })

        return self.async_show_form(
            step_id="v2_connection", data_schema=schema, errors=errors
        )

    async def _validate_v2(self, data: dict) -> str | None:
        for key in (CONF_CERT_PATH, CONF_KEY_PATH, CONF_CA_CERT_PATH):
            path = data.get(key, "")
            if path and not os.path.isfile(path):
                return "invalid_cert"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(data[CONF_VTN_URL], ssl=data.get(CONF_VERIFY_TLS, True)):
                    pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("V2 VTN reachability check failed: %s", exc)
            return "cannot_connect"
        return None

    # ------------------------------------------------------------------
    # Step 2b: OpenADR 3.0 connection
    # ------------------------------------------------------------------

    async def async_step_v3_connection(self, user_input=None):
        errors = {}

        if user_input is not None:
            err = await self._validate_v3(user_input)
            if not err:
                self._connection_data.update(user_input)
                return await self.async_step_target()
            errors["base"] = err

        schema = vol.Schema({
            vol.Required(CONF_VTN_URL): str,
            vol.Required(CONF_VEN_NAME, default="ven-001"): str,
            vol.Required(CONF_TOKEN_URL): str,
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_CLIENT_SECRET): str,
        })

        return self.async_show_form(
            step_id="v3_connection", data_schema=schema, errors=errors
        )

    async def _validate_v3(self, data: dict) -> str | None:
        """Try fetching an OAuth2 token to validate the credentials."""
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
                    payload = await resp.json()
                    if "access_token" not in payload:
                        return "invalid_auth"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("V3 OAuth2 validation failed: %s", exc)
            return "cannot_connect"
        return None

    # ------------------------------------------------------------------
    # Step 3: shared target entity selector
    # ------------------------------------------------------------------

    async def async_step_target(self, user_input=None):
        if user_input is not None:
            data = {**self._connection_data, **user_input}
            ven_name = self._connection_data.get(CONF_VEN_NAME, "ven")
            protocol = self._connection_data.get(CONF_PROTOCOL_VERSION, PROTOCOL_V2)
            return self.async_create_entry(
                title=f"OpenADR VEN {protocol} ({ven_name})",
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

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(entry)


# ------------------------------------------------------------------
# Options flow
# ------------------------------------------------------------------

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Update SIMPLE level mapping and (for v3) poll interval."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts     = self._entry.options
        protocol = self._entry.data.get(CONF_PROTOCOL_VERSION, PROTOCOL_V2)
        is_v3    = protocol == PROTOCOL_V3

        fields: dict = {
            vol.Required(CONF_LEVEL_0_PCT, default=opts.get(CONF_LEVEL_0_PCT, DEFAULTS[CONF_LEVEL_0_PCT])):
                vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(CONF_LEVEL_1_PCT, default=opts.get(CONF_LEVEL_1_PCT, DEFAULTS[CONF_LEVEL_1_PCT])):
                vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(CONF_LEVEL_2_PCT, default=opts.get(CONF_LEVEL_2_PCT, DEFAULTS[CONF_LEVEL_2_PCT])):
                vol.All(int, vol.Range(min=0, max=100)),
            vol.Required(CONF_LEVEL_3_PCT, default=opts.get(CONF_LEVEL_3_PCT, DEFAULTS[CONF_LEVEL_3_PCT])):
                vol.All(int, vol.Range(min=0, max=100)),
        }

        if is_v3:
            fields[vol.Required(
                CONF_POLL_INTERVAL,
                default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )] = vol.All(int, vol.Range(min=10, max=3600))

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields)
        )
