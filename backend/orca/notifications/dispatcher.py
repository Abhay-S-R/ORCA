"""The three dispatchers (plan §4.9).

`InAppDispatcher` is real: it writes the notification row and the payload is
shown verbatim in the feed. `SMSDispatcher` and `IVRDispatcher` raise
`NotImplementedError` with a clear reason — DLT template registration is a
regulatory process, not an engineering one (plan §9), and nothing anywhere
may claim a message was delivered when it was only rendered.

Sentinel's loop catches the `NotImplementedError` and degrades (records a
`failed`/`simulated` notification, keeps polling) rather than crashing —
asserted in tests/unit/test_dispatcher.py and tests/unit/test_sentinel.py.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from orca.notifications.contracts import DispatchResult

_SMS_REASON = (
    "SMS delivery is not implemented in Phase 3. The message is rendered and "
    "stored (shown as SIMULATED in the feed), but no SMS transport exists — "
    "DLT sender-ID / template registration with an aggregator is a regulatory "
    "step outside this scope (plan §9)."
)
_IVR_REASON = (
    "IVR delivery is not implemented in Phase 3. The TTS script is rendered "
    "and stored (shown as SIMULATED in the feed), but no telephony/IVR "
    "transport exists — provisioning a voice line and DTMF flow is outside "
    "this scope (plan §9)."
)


class InAppDispatcher:
    channel = "in_app"

    def __init__(self, db: Session) -> None:
        self._db = db

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        """The caller (Sentinel / /ops) has already written the notification
        row; the in-app 'transport' is that write plus making it visible, so
        there is nothing to transmit here. This exists to keep every channel
        behind the same `send()` call — `sent` means the feed row is live."""
        return DispatchResult(channel="in_app", status="sent", detail="written to the in-app feed")


class SMSDispatcher:
    channel = "sms"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_SMS_REASON)


class IVRDispatcher:
    channel = "ivr"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_IVR_REASON)


def get_dispatcher(channel: str, db: Session) -> InAppDispatcher | SMSDispatcher | IVRDispatcher:
    if channel == "in_app":
        return InAppDispatcher(db)
    if channel == "sms":
        return SMSDispatcher()
    if channel in ("ivr", "ussd"):  # ussd shares the IVR "no transport" story
        return IVRDispatcher()
    raise ValueError(f"unknown dispatch channel {channel!r}")
