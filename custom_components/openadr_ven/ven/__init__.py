"""VEN client adapter package.

Exports VENClientBase, OpenADR2Client, OpenADR3Client, and the
create_ven_client() factory so callers only need one import.
"""
from .base import VENClientBase, NormalizedEvent, OptDecision, EventCallback
from .client_v2 import OpenADR2Client
from .client_v3 import OpenADR3Client

__all__ = [
    "VENClientBase",
    "NormalizedEvent",
    "OptDecision",
    "EventCallback",
    "OpenADR2Client",
    "OpenADR3Client",
]
