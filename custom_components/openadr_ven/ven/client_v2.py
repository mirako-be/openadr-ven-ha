"""OpenADR 2.0b VEN client adapter wrapping openleadr."""
from __future__ import annotations

import asyncio
import logging

from openleadr import OpenADRClient

from .base import EventCallback, NormalizedEvent, VENClientBase

_LOGGER = logging.getLogger(__name__)


class OpenADR2Client(VENClientBase):
    """Wraps openleadr.OpenADRClient and normalises events for the coordinator.

    Authentication uses mutual TLS (client certificate + key).
    Transport is HTTP pull polling; push (XMPP) is not supported here.
    """

    def __init__(
        self,
        on_event: EventCallback,
        *,
        ven_name: str,
        vtn_url: str,
        cert: str | None = None,
        key: str | None = None,
        ca_file: str | None = None,
        verify_hostname: bool = True,
    ) -> None:
        super().__init__(on_event)

        self._client = OpenADRClient(
            ven_name=ven_name,
            vtn_url=vtn_url,
            cert=cert,
            key=key,
            ca_file=ca_file,
            verify_hostname=verify_hostname,
        )
        self._client.add_handler("on_event", self._handle_raw_event)
        _LOGGER.debug("OpenADR 2.0b client initialised — VTN: %s", vtn_url)

    async def _handle_raw_event(self, event: dict) -> str:
        """Translate the openleadr event dict into a NormalizedEvent and
        delegate to the coordinator. Returns the opt decision to openleadr."""
        event_id = event["event_descriptor"]["event_id"]
        signals  = event["event_descriptor"]["event_signals"]

        for sig in signals:
            if sig.get("signal_name") != "SIMPLE":
                _LOGGER.debug(
                    "Skipping non-SIMPLE signal '%s' in event %s",
                    sig.get("signal_name"), event_id,
                )
                continue

            try:
                level = int(sig["intervals"][0]["signal_payload"])
            except (KeyError, IndexError, ValueError) as exc:
                _LOGGER.warning("Could not parse SIMPLE level in event %s: %s", event_id, exc)
                continue

            normalised: NormalizedEvent = {
                "event_id":    event_id,
                "dr_level":    level,
                "signal_name": "SIMPLE",
                "program_id":  "",
            }
            return await self._on_event(normalised)

        _LOGGER.warning("No supported signal found in event %s — defaulting optIn", event_id)
        return "optIn"

    async def run(self) -> None:
        try:
            await self._client.run()
        except asyncio.CancelledError:
            _LOGGER.info("OpenADR 2.0b client cancelled cleanly")
            raise

    def stop(self) -> None:
        self._client.stop()
