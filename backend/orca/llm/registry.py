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
        max_tokens = int(kw.pop("max_tokens", 1024))
        # Cast to Any so PyLance / mypy cleanly accepts the generic dict messages shape
        anthropic_messages: Any = messages
        resp: Any = self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=anthropic_messages, **kw
        )
        content = getattr(resp, "content", [])
        return "".join(getattr(block, "text", "") for block in content if getattr(block, "type", "") == "text")

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        max_tokens = int(kw.pop("max_tokens", 1024))
        anthropic_messages: Any = messages
        with self._client.messages.stream(
            model=model, max_tokens=max_tokens, messages=anthropic_messages, **kw
        ) as s:
            yield from s.text_stream


class GeminiProvider:
    def __init__(self) -> None:
        from google import genai  # modern official vendor SDK — confined to this file

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise KeyError("Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set in environment")
        self._client = genai.Client(api_key=api_key)

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        if not messages:
            return ""
        if len(messages) == 1:
            resp = self._client.models.generate_content(
                model=model,
                contents=messages[0]["content"],
                **kw,
            )
            return resp.text or ""

        chat = self._client.chats.create(model=model)
        for m in messages[:-1]:
            chat.send_message(m["content"])
        resp = chat.send_message(messages[-1]["content"], **kw)
        return resp.text or ""

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        if not messages:
            return
        if len(messages) == 1:
            for chunk in self._client.models.generate_content_stream(
                model=model,
                contents=messages[0]["content"],
                **kw,
            ):
                if chunk.text:
                    yield chunk.text
            return

        chat = self._client.chats.create(model=model)
        for m in messages[:-1]:
            chat.send_message(m["content"])
        for chunk in chat.send_message_stream(messages[-1]["content"], **kw):
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
