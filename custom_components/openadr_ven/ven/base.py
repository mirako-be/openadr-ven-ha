"""Abstract base class for OpenADR VEN protocol adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypedDict


class NormalizedEvent(TypedDict):
    """Protocol-agnostic DR event passed from any VEN client to the coordinator."""
    event_id:    str
    dr_level:    int    # SIMPLE signal value (0-3)
    signal_name: str    # always "SIMPLE" for now
    program_id:  str    # empty string for OpenADR 2.0b


OptDecision = str  # "optIn" | "optOut"
EventCallback = Callable[[NormalizedEvent], Awaitable[OptDecision]]


class VENClientBase(ABC):
    """Common interface for OpenADR VEN protocol adapters.

    Concrete implementations are responsible for:
    - Authenticating with the VTN
    - Receiving or polling for DR events
    - Normalising events into NormalizedEvent dicts
    - Invoking on_event() and handling the opt decision
    - Submitting any required acknowledgement back to the VTN
    """

    def __init__(self, on_event: EventCallback) -> None:
        self._on_event = on_event

    @abstractmethod
    async def run(self) -> None:
        """Start the client. Runs until cancelled or stop() is called.

        Should raise on unrecoverable errors so the HA background task
        supervisor can restart the task.
        """

    @abstractmethod
    def stop(self) -> None:
        """Signal the client to shut down gracefully."""
