"""OpenADR VEN integration for Home Assistant.

Runs an openleadr VEN client as a supervised background task.
DR events are mapped to a configurable Modbus number entity
(inverter power limit) via the signal mapping options.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from openleadr import OpenADRClient

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
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenADR VEN from a config entry."""
    coordinator = DRCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Supervised background task — HA restarts it automatically on failure
    entry.async_create_background_task(
        hass,
        coordinator.run_ven(),
        name=f"openadr_ven_{entry.entry_id}",
    )

    entry.async_on_unload(coordinator.stop)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the user updates signal mapping options."""
    await hass.config_entries.async_reload(entry.entry_id)


class DRCoordinator(DataUpdateCoordinator):
    """Holds current DR state and supervises the openleadr client."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._entry = entry
        self._client: OpenADRClient | None = None
        self.data: dict = {
            "dr_level":     None,
            "setpoint_pct": None,
            "event_id":     None,
        }

    # ------------------------------------------------------------------
    # Signal level → setpoint mapping (reads live options each time)
    # ------------------------------------------------------------------

    def _level_map(self) -> dict[int, int]:
        opts = self._entry.options
        return {
            0: opts.get(CONF_LEVEL_0_PCT, 100),
            1: opts.get(CONF_LEVEL_1_PCT, 75),
            2: opts.get(CONF_LEVEL_2_PCT, 50),
            3: opts.get(CONF_LEVEL_3_PCT, 0),
        }

    # ------------------------------------------------------------------
    # VEN lifecycle
    # ------------------------------------------------------------------

    async def run_ven(self) -> None:
        """Start the openleadr client. Raises on unrecoverable error so
        HA's background task supervisor can restart it."""
        data = self._entry.data

        client = OpenADRClient(
            ven_name        = data[CONF_VEN_NAME],
            vtn_url         = data[CONF_VTN_URL],
            cert            = data.get(CONF_CERT_PATH) or None,
            key             = data.get(CONF_KEY_PATH)  or None,
            ca_file         = data.get(CONF_CA_CERT_PATH) or None,
            verify_hostname = data.get(CONF_VERIFY_TLS, True),
        )
        client.add_handler("on_event", self._handle_event)
        self._client = client

        _LOGGER.info(
            "OpenADR VEN '%s' starting — VTN: %s",
            data[CONF_VEN_NAME],
            data[CONF_VTN_URL],
        )
        try:
            await client.run()
        except asyncio.CancelledError:
            _LOGGER.info("OpenADR VEN task cancelled cleanly")
        except Exception as exc:
            _LOGGER.error("OpenADR VEN encountered an error: %s", exc, exc_info=True)
            raise   # let HA supervisor restart the task

    def stop(self) -> None:
        """Called on integration unload."""
        if self._client:
            self._client.stop()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _handle_event(self, event: dict) -> str:
        """Process an incoming DR event from the VTN.

        Returns 'optIn' or 'optOut' to the VTN.
        """
        signals  = event["event_descriptor"]["event_signals"]
        event_id = event["event_descriptor"]["event_id"]
        level_map = self._level_map()

        for sig in signals:
            if sig["signal_name"] != "SIMPLE":
                _LOGGER.debug("Ignoring non-SIMPLE signal: %s", sig["signal_name"])
                continue

            level    = int(sig["intervals"][0]["signal_payload"])
            setpoint = level_map.get(level, 100)

            _LOGGER.info(
                "DR event '%s': SIMPLE level %s → %s%% power setpoint",
                event_id, level, setpoint,
            )

            # Push state to sensor entities
            self.async_set_updated_data({
                "dr_level":     level,
                "setpoint_pct": setpoint,
                "event_id":     event_id,
            })

            # Apply to target inverter entity
            await self._apply_setpoint(setpoint)

        return "optIn"

    async def _apply_setpoint(self, setpoint_pct: int) -> None:
        """Write the setpoint to the configured Modbus number entity."""
        target = self._entry.data.get(CONF_TARGET_ENTITY)
        if not target:
            _LOGGER.warning("No target entity configured — setpoint not applied")
            return

        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": target, "value": setpoint_pct},
                blocking=True,
            )
            _LOGGER.debug("Set %s → %s%%", target, setpoint_pct)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "Failed to set value on %s: %s", target, exc, exc_info=True
            )
