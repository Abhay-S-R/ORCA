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
# P6.10 — the remaining four channels, same shape as SMS/IVR above: each is
# rendered (orca/channels/renderers.py) and stored as SIMULATED, and each
# reason names the real-world integration that would make it live, so
# "simulated" never reads as "we forgot this one."
_WHATSAPP_REASON = (
    "WhatsApp delivery is not implemented. The message (with its map-card "
    "link) is rendered and stored (shown as SIMULATED), but no WhatsApp "
    "Business API account/template registration exists — that is a Meta "
    "onboarding process, not an engineering one (plan §9)."
)
_MISSED_CALL_REASON = (
    "Missed-call callback is not implemented. The IVR script for the "
    "caller's home port is rendered and stored (shown as SIMULATED), but no "
    "inbound telephony number or callback dialer exists — same provisioning "
    "gap as IVR itself, one level upstream of it."
)
_VHF_REASON = (
    "VHF broadcast is not implemented. The Channel 16 safety-broadcast "
    "script is rendered and stored (shown as SIMULATED), but no radio "
    "transmitter/licensed VHF station exists in this system — broadcasting "
    "on a maritime safety channel is a licensed-spectrum operation, not "
    "something software can simulate its way into being real."
)
_HARBOUR_BOARD_REASON = (
    "Harbour display-board delivery is not implemented. The board text is "
    "rendered and stored (shown as SIMULATED), but no physical LED/split-"
    "flap board or its control protocol is wired up — that is per-harbour "
    "hardware, not something this codebase can provision."
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


class WhatsAppDispatcher:
    channel = "whatsapp"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_WHATSAPP_REASON)


class MissedCallDispatcher:
    channel = "missed_call"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_MISSED_CALL_REASON)


class VHFDispatcher:
    channel = "vhf"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_VHF_REASON)


class HarbourBoardDispatcher:
    channel = "harbour_board"

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:
        raise NotImplementedError(_HARBOUR_BOARD_REASON)


_DISPATCHER_TYPES = {
    "whatsapp": WhatsAppDispatcher,
    "missed_call": MissedCallDispatcher,
    "vhf": VHFDispatcher,
    "harbour_board": HarbourBoardDispatcher,
}


def get_dispatcher(
    channel: str, db: Session
) -> InAppDispatcher | SMSDispatcher | IVRDispatcher | WhatsAppDispatcher | MissedCallDispatcher | VHFDispatcher | HarbourBoardDispatcher:
    if channel == "in_app":
        return InAppDispatcher(db)
    if channel == "sms":
        return SMSDispatcher()
    if channel in ("ivr", "ussd"):  # ussd shares the IVR "no transport" story
        return IVRDispatcher()
    if channel in _DISPATCHER_TYPES:
        return _DISPATCHER_TYPES[channel]()
    raise ValueError(f"unknown dispatch channel {channel!r}")
