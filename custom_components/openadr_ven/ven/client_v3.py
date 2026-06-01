"""OpenADR 3.0 VEN client adapter.

Implements polling transport with OAuth2 client credentials authentication.
Webhook (server-sent events) transport is a planned future enhancement.

OpenADR 3.0 spec: https://www.openadr.org/specification
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from .base import EventCallback, NormalizedEvent, VENClientBase

_LOGGER = logging.getLogger(__name__)

# Seconds before expiry to proactively refresh the token
_TOKEN_REFRESH_BUFFER = 60


class OpenADR3Client(VENClientBase):
    """Polls a VTN REST API for DR events and submits opt reports.

    Authentication: OAuth2 client credentials (RFC 6749 §4.4).
    Transport: HTTP polling at a configurable interval.

    The VTN base URL is expected to expose the OpenADR 3.0 endpoints:
      GET  {vtn_url}/events
      POST {vtn_url}/reports
    """

    def __init__(
        self,
        on_event: EventCallback,
        *,
        vtn_url: str,
        ven_name: str,
        client_id: str,
        client_secret: str,
        token_url: str,
        poll_interval: int = 60,
    ) -> None:
        super().__init__(on_event)

        self._vtn_url       = vtn_url.rstrip("/")
        self._ven_name      = ven_name
        self._client_id     = client_id
        self._client_secret = client_secret
        self._token_url     = token_url
        self._poll_interval = poll_interval

        self._stop_event:     asyncio.Event = asyncio.Event()
        self._token:          str | None    = None
        self._token_expires:  datetime      = datetime.min.replace(tzinfo=timezone.utc)
        self._seen_event_ids: set[str]      = set()
        self._session:        aiohttp.ClientSession | None = None

        _LOGGER.debug(
            "OpenADR 3.0 client initialised — VTN: %s, poll interval: %ss",
            self._vtn_url, self._poll_interval,
        )

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a valid bearer token, refreshing proactively when near expiry."""
        now = datetime.now(tz=timezone.utc)
        if self._token and now < self._token_expires:
            return self._token

        _LOGGER.debug("Fetching OAuth2 token from %s", self._token_url)
        async with self._session.post(
            self._token_url,
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Accept": "application/json"},
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json()

        self._token = payload["access_token"]
        expires_in  = int(payload.get("expires_in", 3600))
        self._token_expires = now + timedelta(seconds=expires_in - _TOKEN_REFRESH_BUFFER)
        _LOGGER.debug("OAuth2 token acquired, expires in %ss", expires_in)
        return self._token

    def _bearer(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_once(self) -> None:
        """Fetch active events from the VTN and process any new ones."""
        token = await self._get_token()

        async with self._session.get(
            f"{self._vtn_url}/events",
            headers=self._bearer(token),
        ) as resp:
            resp.raise_for_status()
            events: list[dict] = await resp.json()

        _LOGGER.debug("Polled %d event(s) from VTN", len(events))

        for event in events:
            await self._process_event(event, token)

    async def _process_event(self, event: dict, token: str) -> None:
        """Parse a single OpenADR 3 event object and invoke the coordinator callback."""
        event_id  = str(event.get("id") or event.get("eventID", ""))
        program_id = str(event.get("programID", ""))

        if not event_id:
            _LOGGER.warning("Received event with no id, skipping: %s", event)
            return

        if event_id in self._seen_event_ids:
            return

        # Walk intervals → payloads looking for SIMPLE
        dr_level: int | None = None
        for interval in event.get("intervals", []):
            for payload in interval.get("payloads", []):
                if payload.get("type") == "SIMPLE":
                    values = payload.get("values", [])
                    if values:
                        dr_level = int(values[0])
                        break
            if dr_level is not None:
                break

        if dr_level is None:
            _LOGGER.debug("Event %s has no SIMPLE payload — skipping", event_id)
            return

        _LOGGER.info(
            "OpenADR 3.0 event '%s' (program '%s'): SIMPLE level %s",
            event_id, program_id, dr_level,
        )

        normalised: NormalizedEvent = {
            "event_id":    event_id,
            "dr_level":    dr_level,
            "signal_name": "SIMPLE",
            "program_id":  program_id,
        }
        opt_decision = await self._on_event(normalised)
        self._seen_event_ids.add(event_id)

        await self._submit_report(event_id, program_id, opt_decision, token)

    # ------------------------------------------------------------------
    # Report submission (opt acknowledgement)
    # ------------------------------------------------------------------

    async def _submit_report(
        self,
        event_id: str,
        program_id: str,
        opt_decision: str,
        token: str,
    ) -> None:
        """POST an OPT report back to the VTN to acknowledge the event."""
        opt_value = "OPT_IN" if opt_decision == "optIn" else "OPT_OUT"
        report = {
            "programID": program_id,
            "eventID":   event_id,
            "clientName": self._ven_name,
            "resources": [
                {
                    "resourceName": self._ven_name,
                    "intervals": [
                        {
                            "id": 0,
                            "payloads": [
                                {"type": "OPT", "values": [opt_value]},
                            ],
                        }
                    ],
                }
            ],
        }
        try:
            async with self._session.post(
                f"{self._vtn_url}/reports",
                headers=self._bearer(token),
                json=report,
            ) as resp:
                resp.raise_for_status()
            _LOGGER.debug(
                "Report submitted for event '%s': %s", event_id, opt_value
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to submit report for event '%s': %s", event_id, exc
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _sleep_or_stop(self) -> bool:
        """Wait for poll_interval seconds or until stop() is called.
        Returns True if stop() fired, False if the interval elapsed normally."""
        try:
            await asyncio.wait_for(
                self._stop_event.wait(), timeout=self._poll_interval
            )
            return True
        except asyncio.TimeoutError:
            return False

    async def run(self) -> None:
        self._session = aiohttp.ClientSession()
        try:
            while not self._stop_event.is_set():
                try:
                    await self._poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _LOGGER.error(
                        "Error during OpenADR 3.0 poll cycle: %s", exc, exc_info=True
                    )
                if await self._sleep_or_stop():
                    break
        except asyncio.CancelledError:
            _LOGGER.info("OpenADR 3.0 client cancelled cleanly")
        finally:
            await self._session.close()
            _LOGGER.debug("OpenADR 3.0 aiohttp session closed")

    def stop(self) -> None:
        self._stop_event.set()
