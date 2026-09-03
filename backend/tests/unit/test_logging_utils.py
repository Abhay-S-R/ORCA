import logging

from orca.logging_utils import RedactionFilter


def _filtered_message(msg: str, *args: object) -> str:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, args or None, None)
    RedactionFilter().filter(record)
    return record.getMessage()


def test_redacts_coordinate_pair():
    out = _filtered_message("user location: 8.822495, 78.119064")
    assert "8.822495" not in out
    assert "78.119064" not in out
    assert "[REDACTED_COORDS]" in out


def test_redacts_lat_lon_keyword_value():
    out = _filtered_message("query lat=8.822495 lon=78.119064")
    assert "8.822495" not in out
    assert "78.119064" not in out


def test_redacts_email_address():
    out = _filtered_message("registration for fisherman@example.com succeeded")
    assert "fisherman@example.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_redacts_jwt_looking_token():
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    out = _filtered_message(f"issued token {fake_jwt}")
    assert fake_jwt not in out
    assert "[REDACTED_TOKEN]" in out


def test_redacts_phone_number():
    out = _filtered_message("contact +91 98765 43210 for follow-up")
    assert "98765" not in out


def test_leaves_ordinary_messages_untouched():
    out = _filtered_message("planning matched routing row: SAFETY_CHECK")
    assert out == "planning matched routing row: SAFETY_CHECK"


def test_redacts_interpolated_args_not_just_the_format_string():
    out = _filtered_message("user %s logged in", "someone@example.com")
    assert "someone@example.com" not in out
