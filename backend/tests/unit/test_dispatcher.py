"""Dispatcher layer (plan §4.9). The load-bearing assertions: SMS and IVR
raise NotImplementedError (never a silent fake delivery), and a caller that
catches it degrades rather than crashes (exit criterion 10)."""
import pytest

from orca.notifications.contracts import DispatchResult
from orca.notifications.dispatcher import (
    InAppDispatcher,
    IVRDispatcher,
    SMSDispatcher,
    get_dispatcher,
)


def test_in_app_dispatcher_returns_sent():
    result = InAppDispatcher(db=None).send(recipient={"user_id": "u"}, rendered_payload={})
    assert isinstance(result, DispatchResult)
    assert result.status == "sent"
    assert result.channel == "in_app"


def test_sms_dispatcher_raises_not_implemented_with_a_reason():
    with pytest.raises(NotImplementedError, match="SMS delivery is not implemented"):
        SMSDispatcher().send(recipient={}, rendered_payload={"sms": "text"})


def test_ivr_dispatcher_raises_not_implemented_with_a_reason():
    with pytest.raises(NotImplementedError, match="IVR delivery is not implemented"):
        IVRDispatcher().send(recipient={}, rendered_payload={})


def test_get_dispatcher_maps_channels():
    assert isinstance(get_dispatcher("in_app", db=None), InAppDispatcher)
    assert isinstance(get_dispatcher("sms", db=None), SMSDispatcher)
    assert isinstance(get_dispatcher("ivr", db=None), IVRDispatcher)
    assert isinstance(get_dispatcher("ussd", db=None), IVRDispatcher)  # ussd shares the no-transport story
    with pytest.raises(ValueError):
        get_dispatcher("carrier-pigeon", db=None)


def test_a_caller_can_degrade_around_the_not_implemented_error():
    """This is the pattern orca/sentinel_runtime.dispatch_decision uses — a
    NotImplementedError from a channel becomes a 'simulated' record, the
    loop keeps going."""
    status = "sent"
    try:
        SMSDispatcher().send(recipient={}, rendered_payload={})
    except NotImplementedError:
        status = "simulated"
    assert status == "simulated"  # did not propagate, did not crash
