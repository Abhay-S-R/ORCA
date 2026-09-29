"""ORCA_LOCAL_MODELS — the one switch for every model ORCA loads into this process's memory
(or, for Ollama, onto this machine): IndicTrans2, faster-whisper, MMS-TTS, the e5 intent
model and the local LLM rung.

`0` means none of them is ever loaded — not warmed at startup and not lazily on first use —
so a small host (Render: the warmed image measured 824 MB) stays within its memory. Each one
is a fallback or an optional tier with a hosted or deterministic rung in front of it: Bhashini
for translation and speech, word overlap for intent routing, Groq/Gemini for answers. Blank or
`1` loads them as before.

`loading()` is also the fix for a real race: the startup warm-ups ran in parallel threads, and
two threads importing `transformers` for the first time at once left the e5 load failing with
`ImportError: cannot import name 'is_torch_npu_available'` (reproduced 2026-09-30: parallel
warm-ups fail, the same four run one after another succeed). Every loader holds one
process-wide lock, so model loads — and the first heavy imports inside them — never overlap.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_load_lock = threading.RLock()


def enabled() -> bool:
    return (os.environ.get("ORCA_LOCAL_MODELS") or "1") != "0"


@contextmanager
def loading(what: str) -> Iterator[None]:
    """Wrap a local model load. Raises RuntimeError when the switch is off — the exception
    every fallback chain in ORCA already treats as "this rung is unavailable, try the next"."""
    if not enabled():
        raise RuntimeError(f"{what} not loaded: local models are off (ORCA_LOCAL_MODELS=0)")
    with _load_lock:
        yield


if __name__ == "__main__":
    os.environ["ORCA_LOCAL_MODELS"] = "0"
    assert not enabled()
    try:
        with loading("x"):
            raise AssertionError("body must not run while off")
    except RuntimeError as exc:
        assert "ORCA_LOCAL_MODELS=0" in str(exc)
    for on in ("", "1"):
        os.environ["ORCA_LOCAL_MODELS"] = on
        assert enabled()
        with loading("x"), loading("nested"):  # re-entrant: a loader may call another
            pass
    print("local_models self-check ok")
