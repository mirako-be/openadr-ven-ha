"""OpenADR VEN integration for Home Assistant — OpenADR 3.0.

Runs an OpenADR 3.0 VEN client (REST + OAuth2 polling) as a supervised
HA background task. DR events are mapped to a power setpoint via the
SIMPLE level options and written to a Modbus number entity.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
    DOMAIN,
)
from .ven import NormalizedEvent, OpenADR3Client, VENClientBase

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = DRCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(
        hass,
        coordinator.run_ven(),
        name=f"openadr_ven_{entry.entry_id}",
    )

    entry.async_on_unload(coordinator.stop)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


class DRCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._entry  = entry
        self._client: VENClientBase | None = None
        self.data: dict = {"dr_level": None, "setpoint_pct": None, "event_id": None}

    def _level_map(self) -> dict[int, int]:
        opts = self._entry.options
        return {
            0: opts.get(CONF_LEVEL_0_PCT, 100),
            1: opts.get(CONF_LEVEL_1_PCT, 75),
            2: opts.get(CONF_LEVEL_2_PCT, 50),
            3: opts.get(CONF_LEVEL_3_PCT, 0),
        }

    async def run_ven(self) -> None:
        data = self._entry.data
        opts = self._entry.options
        _LOGGER.info(
            "OpenADR 3.0 VEN '%s' starting — VTN: %s",
            data[CONF_VEN_NAME], data[CONF_VTN_URL],
        )
        self._client = OpenADR3Client(
            on_event      = self._handle_event,
            vtn_url       = data[CONF_VTN_URL],
            ven_name      = data[CONF_VEN_NAME],
            client_id     = data[CONF_CLIENT_ID],
            client_secret = data[CONF_CLIENT_SECRET],
            token_url     = data[CONF_TOKEN_URL],
            poll_interval = opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )
        try:
            await self._client.run()
        except asyncio.CancelledError:
            _LOGGER.info("OpenADR VEN task cancelled")
        except Exception as exc:
            _LOGGER.error("OpenADR VEN error: %s", exc, exc_info=True)
            raise

    def stop(self) -> None:
        if self._client:
            self._client.stop()

    async def _handle_event(self, event: NormalizedEvent) -> str:
        dr_level = event["dr_level"]
        setpoint = self._level_map().get(dr_level, 100)
        _LOGGER.info(
            "DR event '%s': SIMPLE level %s → %s%%",
            event["event_id"], dr_level, setpoint,
        )
        self.async_set_updated_data({
            "dr_level":     dr_level,
            "setpoint_pct": setpoint,
            "event_id":     event["event_id"],
        })
        await self._apply_setpoint(setpoint)
        return "optIn"

    async def _apply_setpoint(self, setpoint_pct: int) -> None:
        target = self._entry.data.get(CONF_TARGET_ENTITY)
        if not target:
            _LOGGER.warning("No target entity configured")
            return
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": target, "value": setpoint_pct},
                blocking=True,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Failed to set %s: %s", target, exc, exc_info=True)
