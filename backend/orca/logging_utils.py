"""Log redaction filter (plan §5.4 Day 10: "Log redaction filter ahead of
the formatter") — a logging.Filter, so it runs before any Formatter turns a
record into text, on every handler attached via `configure_logging()`.

Coordinates and identity are what a marine-safety log line most often
carries incidentally (a lat/lon in `inputs_consumed`, an email in an auth
log message) and what must never sit in plaintext ops logs — the audit
trail of *who* asked *where* belongs in `audit_trace_log` under RBAC, not
in a log file anyone with server access can grep.

Also:
- `install_uvicorn_access_filter`: strips query strings from uvicorn's
  access log so SSE `?token=…` JWTs never reach Render's log drain.
- `log_startup_memory` / `start_memory_watchdog`: OOM breadcrumbs — on
  Render free-tier the OOM-killer SIGKILLs the process with no log line;
  these ensure there's always a recent RSS reading before the silence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone

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
        except Exception:
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



# P6.12 (orca_final §28) — every log line keyed by the query_id it belongs
# to, so an incident can be grepped end to end instead of reconstructed from
# timestamps. A ContextVar rather than a parameter threaded into every log
# call: `bind_query_id` is set once at the top of the request handler
# (`orca/api/main.py`'s query-streaming generator) and every `logging.info(…)`
# anywhere in that call tree — including inside LangGraph's node functions,
# none of which take a query_id parameter today — picks it up automatically.
# ContextVars propagate through `await` within the same task and through
# `asyncio.to_thread`/`run_in_executor` (both copy the current context by
# default), which covers LangGraph's own thread offloading for sync nodes.
_query_id_var: ContextVar[str] = ContextVar("query_id", default="")


def bind_query_id(query_id: str) -> None:
    """Call once per request, before any node runs, so every log line
    emitted while handling it carries the same id a judge can also find in
    `audit_trace_log`, `/trace/{query_id}` and the DB's own audit rows."""
    _query_id_var.set(query_id)


class QueryIdFilter(logging.Filter):
    """Stamps the ambient query_id (if any) onto every record, for
    `JsonFormatter` to render. A background task with no request in flight
    (Sentinel's poll loop) simply gets an empty string — not an error."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.query_id = _query_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line — `docker logs`/`journalctl` friendly, and
    grep/jq-able by query_id without a log-aggregation stack this project
    doesn't have. Runs after RedactionFilter/QueryIdFilter, which mutate
    `record.msg`/set `record.query_id` respectively before this ever sees
    the record."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "query_id": getattr(record, "query_id", "") or None,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Call once at process startup (orca/api/main.py's lifespan). Attaches
    a single StreamHandler carrying `RedactionFilter`/`QueryIdFilter` to the
    root logger — every orca.* module logger propagates to it with no
    handler of its own, so this is the one place redaction and the
    query_id key have to be wired for it to cover all of them."""
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.addFilter(RedactionFilter())
    handler.addFilter(QueryIdFilter())
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Uvicorn access-log filter — strip query strings so tokens stay out of logs
# ---------------------------------------------------------------------------

_QS_RE = re.compile(r"\?.*")


class _StripQueryStringFilter(logging.Filter):
    """Uvicorn's access logger formats the line with %-style args:
        '%s - "%s %s HTTP/%s" %d'  →  (addr, method, full_path, version, status)
    `full_path` is arg index 2 and may contain `?token=eyJ…`.

    This filter rewrites that arg to strip everything after '?' *before*
    the formatter renders the final string, so no token ever reaches the
    log output.  Falls back gracefully if uvicorn changes its format.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple) and len(record.args) >= 3:
            # Make mutable — LogRecord.args is usually a plain tuple.
            args = list(record.args)
            path = args[2]
            if isinstance(path, str) and "?" in path:
                args[2] = _QS_RE.sub("", path)
                record.args = tuple(args)
        return True


def install_uvicorn_access_filter() -> None:
    """Attach `_StripQueryStringFilter` to `uvicorn.access` so its default
    StreamHandler never logs `?token=…` query params.

    Safe to call more than once (idempotent) and safe if uvicorn is not
    installed — the logger just won't have handlers to attach to, and the
    filter itself is a no-op without matching log records.
    """
    access_logger = logging.getLogger("uvicorn.access")
    # Avoid duplicating if called twice (e.g. --reload).
    for f in access_logger.filters:
        if isinstance(f, _StripQueryStringFilter):
            return
    access_logger.addFilter(_StripQueryStringFilter())
    # Also add to any handlers uvicorn.access already has, so the filter
    # runs even if the logger propagates=False (uvicorn's default).
    for h in access_logger.handlers:
        already = any(isinstance(f, _StripQueryStringFilter) for f in h.filters)
        if not already:
            h.addFilter(_StripQueryStringFilter())


# ---------------------------------------------------------------------------
# OOM breadcrumbs — memory logging at startup and periodically
# ---------------------------------------------------------------------------

def _rss_mb() -> float | None:
    """Current RSS of this process in MiB, or None if unavailable."""
    try:
        import resource  # Unix only
        # resource.getrusage returns ru_maxrss in KiB on Linux
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024.0
    except (ImportError, AttributeError):
        pass
    # Fallback: /proc on Linux (works on Render's Docker containers)
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0  # kB → MiB
    except (FileNotFoundError, OSError):
        pass
    return None


def log_startup_memory() -> None:
    """Log the current RSS and a cold-start marker.

    On Render free-tier the OOM-killer SIGKILLs the process with zero
    warning — no Python handler runs, no log line is emitted. By logging
    "orca process started" with the initial RSS, ops can diff timestamps
    against the *previous* log line to tell whether a restart was a clean
    redeploy or a silent OOM kill (gap > graceful-shutdown timeout ⇒ OOM).
    """
    _log = logging.getLogger("orca.runtime")
    rss = _rss_mb()
    rss_str = f"{rss:.1f} MiB" if rss is not None else "unknown"
    _log.info(
        "orca process started — initial RSS %s, PID %s",
        rss_str,
        os.getpid(),
    )


async def start_memory_watchdog(
    interval_seconds: int = 60,
    warn_threshold_mb: float = 400.0,
) -> asyncio.Task:
    """Spawn a background task that logs RSS every *interval_seconds*.

    On Render free (512 MB) this means the logs always contain a reading
    within the last minute before a silent OOM kill — enough to confirm
    "memory was at 490 MiB and climbing" vs "memory was stable at 200 MiB,
    so the restart was something else".

    The task is a daemon-style fire-and-forget; cancelling the returned
    `Task` stops it cleanly (done in lifespan teardown).
    """
    _log = logging.getLogger("orca.runtime")

    async def _watchdog() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            rss = _rss_mb()
            if rss is None:
                continue
            if rss >= warn_threshold_mb:
                _log.warning(
                    "memory watchdog: RSS %.1f MiB (threshold %.0f MiB)",
                    rss,
                    warn_threshold_mb,
                )
            else:
                _log.info("memory watchdog: RSS %.1f MiB", rss)

    task = asyncio.create_task(_watchdog(), name="memory-watchdog")
    return task


if __name__ == "__main__":
    logging.getLogger("demo").addHandler(logging.NullHandler())
    f = RedactionFilter()
    r = logging.LogRecord("demo", logging.INFO, __file__, 1, "user at 8.822495, 78.119064 logged in as a@b.com", None, None)
    f.filter(r)
    assert "8.822495" not in r.getMessage()
    assert "a@b.com" not in r.getMessage()

    bind_query_id("qid-123")
    QueryIdFilter().filter(r)
    line = JsonFormatter().format(r)
    parsed = json.loads(line)
    assert parsed["query_id"] == "qid-123", parsed
    assert "8.822495" not in line and "a@b.com" not in line

    bind_query_id("")  # the no-request-in-flight case (e.g. Sentinel's poll loop)
    r2 = logging.LogRecord("demo", logging.INFO, __file__, 1, "background tick", None, None)
    QueryIdFilter().filter(r2)
    assert json.loads(JsonFormatter().format(r2))["query_id"] is None

    print("logging_utils self-check ok:", line)
