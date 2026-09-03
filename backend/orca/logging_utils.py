"""Log redaction filter (plan §5.4 Day 10: "Log redaction filter ahead of
the formatter") — a logging.Filter, so it runs before any Formatter turns a
record into text, on every handler attached via `configure_logging()`.

Coordinates and identity are what a marine-safety log line most often
carries incidentally (a lat/lon in `inputs_consumed`, an email in an auth
log message) and what must never sit in plaintext ops logs — the audit
trail of *who* asked *where* belongs in `audit_trace_log` under RBAC, not
in a log file anyone with server access can grep.
"""
from __future__ import annotations

import logging
import re

# 4+ decimal places is the practical GPS-precision signature (≈11m or
# better) — 2-3 decimals covers city-scale numbers too common in ordinary
# log messages to redact without gutting the logs' usefulness.
_COORD_PAIR = re.compile(r"-?\d{1,3}\.\d{4,},\s*-?\d{1,3}\.\d{4,}")
_LAT_LON_KV = re.compile(r'\b(lat|lon|latitude|longitude)["\']?\s*[:=]\s*-?\d{1,3}\.\d+', re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\-\s]{8,13}\d")
_JWT = re.compile(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


class RedactionFilter(logging.Filter):
    """Attach to a handler (not a logger) so it runs ahead of that
    handler's formatter. Rewrites `record.msg` in place and clears
    `record.args`, so %-style interpolation arguments are covered too, not
    just a pre-formatted message string."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — a malformed record must still be logged, not dropped
            return True
        redacted = _redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def _redact(text: str) -> str:
    text = _COORD_PAIR.sub("[REDACTED_COORDS]", text)
    text = _LAT_LON_KV.sub(lambda m: f"{m.group(1)}=[REDACTED_COORD]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _JWT.sub("[REDACTED_TOKEN]", text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    return text


def configure_logging(level: int = logging.INFO) -> None:
    """Call once at process startup (orca/api/main.py's lifespan). Attaches
    a single StreamHandler carrying `RedactionFilter` to the root logger —
    every orca.* module logger propagates to it with no handler of its own,
    so this is the one place redaction has to be wired for it to cover all
    of them."""
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.addFilter(RedactionFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


if __name__ == "__main__":
    logging.getLogger("demo").addHandler(logging.NullHandler())
    f = RedactionFilter()
    r = logging.LogRecord("demo", logging.INFO, __file__, 1, "user at 8.822495, 78.119064 logged in as a@b.com", None, None)
    f.filter(r)
    assert "8.822495" not in r.getMessage()
    assert "a@b.com" not in r.getMessage()
    print("logging_utils self-check ok:", r.getMessage())
