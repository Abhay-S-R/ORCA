"""Vendor SDK imports live here and ONLY here (plan §3.1). Two providers
registered for Phase 0; the Phase 2 bake-off (plan §3.3) decides which tier
uses which. Adding a provider is one class, not a refactor.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

from orca.llm.provider import Provider


class AnthropicProvider:
    def __init__(self) -> None:
        import anthropic  # vendor SDK — confined to this file

        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        max_tokens = kw.pop("max_tokens", 1024)
        # messages: our Provider protocol keeps a vendor-neutral {"role", "content"}
        # shape; anthropic's MessageParam is structurally the same but a distinct
        # TypedDict, so this is a deliberate cast, not a real type mismatch.
        resp = self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=messages, **kw  # type: ignore[arg-type]
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        max_tokens = kw.pop("max_tokens", 1024)
        with self._client.messages.stream(
            model=model, max_tokens=max_tokens, messages=messages, **kw  # type: ignore[arg-type]
        ) as s:
            yield from s.text_stream


class GeminiProvider:
    def __init__(self) -> None:
        import google.generativeai as genai  # vendor SDK — confined to this file

        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._genai = genai

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        chat = self._genai.GenerativeModel(model).start_chat(
            history=[{"role": m["role"], "parts": [m["content"]]} for m in messages[:-1]]
        )
        return chat.send_message(messages[-1]["content"], **kw).text

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        chat = self._genai.GenerativeModel(model).start_chat(
            history=[{"role": m["role"], "parts": [m["content"]]} for m in messages[:-1]]
        )
        for chunk in chat.send_message(messages[-1]["content"], stream=True, **kw):
            if chunk.text:
                yield chunk.text


# name -> lazy factory. Lazy so importing the registry never requires every
# vendor SDK to be installed — only the ones a tier actually resolves to.
_FACTORIES: dict[str, Callable[[], Provider]] = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}
_instances: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    if name not in _FACTORIES:
        raise ValueError(f"Unknown LLM provider {name!r}. Registered: {sorted(_FACTORIES)}")
    if name not in _instances:
        _instances[name] = _FACTORIES[name]()
    return _instances[name]
