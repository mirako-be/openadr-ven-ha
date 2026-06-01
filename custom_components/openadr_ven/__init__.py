"""OpenADR VEN integration for Home Assistant.

Runs a VEN client as a supervised HA background task.
Supports OpenADR 2.0b (openleadr, mutual TLS) and
OpenADR 3.0 (REST + OAuth2 polling) via a protocol adapter pattern.

DR events are normalised by the adapter, mapped to a power setpoint
via the SIMPLE level options, and written to a Modbus number entity.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
    DOMAIN,
    PROTOCOL_V3,
)
from .ven import NormalizedEvent, OpenADR2Client, OpenADR3Client, VENClientBase

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenADR VEN from a config entry."""
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
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the user changes options."""
    await hass.config_entries.async_reload(entry.entry_id)


class DRCoordinator(DataUpdateCoordinator):
    """Holds current DR state and manages the VEN client lifecycle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._entry = entry
        self._client: VENClientBase | None = None
        self.data: dict = {
            "dr_level":     None,
            "setpoint_pct": None,
            "event_id":     None,
            "protocol":     entry.data.get(CONF_PROTOCOL_VERSION, "2.0b"),
        }

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _create_client(self) -> VENClientBase:
        """Instantiate the correct adapter based on configured protocol version."""
        data    = self._entry.data
        opts    = self._entry.options
        version = data.get(CONF_PROTOCOL_VERSION, "2.0b")

        if version == PROTOCOL_V3:
            return OpenADR3Client(
                on_event      = self._handle_event,
                vtn_url       = data[CONF_VTN_URL],
                ven_name      = data[CONF_VEN_NAME],
                client_id     = data[CONF_CLIENT_ID],
                client_secret = data[CONF_CLIENT_SECRET],
                token_url     = data[CONF_TOKEN_URL],
                poll_interval = opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )

        # Default: OpenADR 2.0b
        return OpenADR2Client(
            on_event        = self._handle_event,
            ven_name        = data[CONF_VEN_NAME],
            vtn_url         = data[CONF_VTN_URL],
            cert            = data.get(CONF_CERT_PATH) or None,
            key             = data.get(CONF_KEY_PATH)  or None,
            ca_file         = data.get(CONF_CA_CERT_PATH) or None,
            verify_hostname = data.get(CONF_VERIFY_TLS, True),
        )

    # ------------------------------------------------------------------
    # Signal level → setpoint mapping
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
        """Start the VEN client. Raises on unrecoverable error so HA restarts it."""
        data    = self._entry.data
        version = data.get(CONF_PROTOCOL_VERSION, "2.0b")

        _LOGGER.info(
            "OpenADR VEN '%s' starting (protocol %s) — VTN: %s",
            data[CONF_VEN_NAME], version, data[CONF_VTN_URL],
        )

        self._client = self._create_client()
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

    # ------------------------------------------------------------------
    # Event handling (protocol-agnostic)
    # ------------------------------------------------------------------

    async def _handle_event(self, event: NormalizedEvent) -> str:
        """Receive a normalised DR event, update state, apply setpoint."""
        event_id  = event["event_id"]
        dr_level  = event["dr_level"]
        setpoint  = self._level_map().get(dr_level, 100)

        _LOGGER.info(
            "DR event '%s': SIMPLE level %s → %s%% power setpoint",
            event_id, dr_level, setpoint,
        )

        self.async_set_updated_data({
            "dr_level":     dr_level,
            "setpoint_pct": setpoint,
            "event_id":     event_id,
            "protocol":     self._entry.data.get(CONF_PROTOCOL_VERSION, "2.0b"),
        })

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
            _LOGGER.error("Failed to set value on %s: %s", target, exc, exc_info=True)
