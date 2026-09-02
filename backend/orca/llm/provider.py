"""The provider protocol every LLM adapter implements (plan §3.1)."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


class Provider(Protocol):
    # kw is Any, not a narrower type, because it is forwarded verbatim into
    # whichever vendor SDK call the concrete provider wraps (registry.py) —
    # those signatures differ per vendor and per call (create vs stream).
    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str: ...

    def stream(
        self, messages: list[dict[str, str]], *, model: str, **kw: Any
    ) -> Iterator[str]: ...
