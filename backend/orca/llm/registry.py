"""Vendor SDK imports live here and ONLY here (plan §3.1). Two hosted
providers registered for Phase 0, plus a local one (Ollama) as the last rung
of every narration chain (chatbot plan C0.2); the Phase 2 bake-off (plan
§3.3) decides which tier uses which. Adding a provider is one class, not a
refactor.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from typing import Any

from orca.llm.provider import Provider


class AnthropicProvider:
    def __init__(self) -> None:
        import anthropic  # vendor SDK — confined to this file

        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        max_tokens = int(kw.pop("max_tokens", 1024))
        timeout_s = kw.pop("timeout_s", None)
        # Cast to Any so PyLance / mypy cleanly accepts the generic dict messages shape
        anthropic_messages: Any = messages
        resp: Any = self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=anthropic_messages,
            **({"timeout": timeout_s} if timeout_s else {}), **kw,
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


_TIMEOUT_MS = 15_000


class GeminiProvider:
    def __init__(self) -> None:
        # modern official vendor SDK — confined to this file. mypy sees `google`
        # as a namespace package contributed to by several installed Google
        # libraries and cannot always resolve `genai` under it, though the
        # import is real and works at runtime (google-genai's own package).
        from google import genai  # type: ignore[attr-defined]

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise KeyError("Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set in environment")
        # The SDK default is no timeout at all: a stalled gemini-3.5-flash-lite
        # request held Planning's one intent-confirmation call for 94.9 s
        # (measured 2026-09-24; the same call normally answers in 1.2 s). Every
        # caller already degrades on LLMUnavailable, and an httpx ReadTimeout
        # classifies as "provider unavailable (timeout)" in tiers.py, so a cap
        # is all this needs. httpx applies it per read, so a long stream whose
        # chunks keep arriving is not cut off.
        # ponytail: one cap for every tier; per-tier timeouts if "deep"
        # completions ever legitimately exceed it.
        self._client = genai.Client(api_key=api_key, http_options=genai.types.HttpOptions(timeout=_TIMEOUT_MS))

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        if not messages:
            return ""
        # A per-call cap tighter than the client's, so a provider chain can
        # split one answer's time budget across its rungs (tiers.py).
        timeout_s = kw.pop("timeout_s", None)
        if timeout_s:
            from google.genai import types  # type: ignore[attr-defined]

            kw["config"] = types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
            )
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


class OllamaProvider:
    """A model on this machine, through Ollama's HTTP API. The last model rung
    of every narration chain (tiers.py): no network, no quota, so "every
    prompt gets a written answer" holds when every hosted provider is down.

    `think` is off because Gemma 4 otherwise spends most of its time on
    hidden reasoning: 15.1 s vs 4.7 s warm for the same Reporting-sized prompt
    on an RTX 3050 (measured 2026-09-24). `keep_alive` keeps the weights
    loaded between questions — a cold load took 137 s, which is no fallback.
    `num_ctx` is 8192, not Ollama's 4096: the real Reporting prompt is already
    2,002 tokens before chat history or a critique, and Ollama drops the
    *start* of an overlong prompt silently — the start is where the rules are.
    Measured on the same GPU it is faster, not slower (3.8 s vs 5.9 s), and
    still fits entirely in 6 GB of VRAM.
    """

    def __init__(self) -> None:
        import httpx

        self._url = (os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self._keep_alive = os.environ.get("ORCA_OLLAMA_KEEP_ALIVE") or "60m"
        # The same options on every call and on warm(): a different num_ctx
        # makes Ollama reload the model, which is the cold start warm() avoids.
        self._options = {"num_ctx": int(os.environ.get("ORCA_OLLAMA_NUM_CTX") or 8192)}
        self._http = httpx.Client()

    def _chat(self, messages: list[dict[str, str]], model: str, timeout_s: float | None, stream: bool) -> Any:
        return self._http.post(
            f"{self._url}/api/chat",
            json={"model": model, "messages": messages, "stream": stream,
                  "think": False, "keep_alive": self._keep_alive, "options": self._options},
            timeout=timeout_s or _TIMEOUT_MS / 1000,
        )

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        resp = self._chat(messages, model, kw.get("timeout_s"), stream=False)
        resp.raise_for_status()
        return str((resp.json().get("message") or {}).get("content") or "")

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        # ponytail: whole reply as one chunk; nothing streams narration yet
        # (plan F2 adds token streaming to /ask).
        text = self.complete(messages, model=model, **kw)
        if text:
            yield text

    def warm(self, model: str) -> None:
        """Load the weights now, so the first fallback of the day is not the
        137 s cold load. An empty prompt loads the model and returns."""
        self._http.post(
            f"{self._url}/api/generate",
            json={"model": model, "keep_alive": self._keep_alive, "options": self._options},
            timeout=300,
        ).raise_for_status()


def groq_keys() -> list[str]:
    """Every Groq key in the environment, in .env order: GROQ_API_KEY, then
    GROQ_API_KEY_1, GROQ_API_KEY_2, … — each may also hold a comma-separated
    list. Several free-tier keys are several rate limits."""
    names = sorted(
        (n for n in os.environ if re.fullmatch(r"GROQ_API_KEY(_\d+)?", n)),
        key=lambda n: int(n.rsplit("_", 1)[1]) if n[-1].isdigit() else 0,
    )
    return [k.strip() for n in names for k in os.environ[n].split(",") if k.strip()]


class GroqProvider:
    """Groq's OpenAI-compatible chat API, over the httpx already installed —
    no vendor SDK. A rate-limited key hands the same request to the next key
    before the rung counts as failed (tiers.py), so N keys are N quotas."""

    _URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        import httpx

        self._keys = groq_keys()
        if not self._keys:
            raise KeyError("No GROQ_API_KEY set in environment")
        self._http = httpx.Client()

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        timeout = kw.get("timeout_s") or _TIMEOUT_MS / 1000
        for i, key in enumerate(self._keys):
            resp = self._http.post(
                self._URL, headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages}, timeout=timeout,
            )
            if resp.status_code == 429 and i + 1 < len(self._keys):
                continue
            resp.raise_for_status()
            text = str(resp.json()["choices"][0]["message"].get("content") or "")
            # Reasoning models on Groq may return their thinking inline.
            return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return ""  # unreachable: the last key either returns or raises

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        # ponytail: whole reply as one chunk, same as OllamaProvider.
        text = self.complete(messages, model=model, **kw)
        if text:
            yield text


# name -> lazy factory. Lazy so importing the registry never requires every
# vendor SDK to be installed — only the ones a tier actually resolves to.
_FACTORIES: dict[str, Callable[[], Provider]] = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "ollama": OllamaProvider,
}
_instances: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    if name not in _FACTORIES:
        raise ValueError(f"Unknown LLM provider {name!r}. Registered: {sorted(_FACTORIES)}")
    if name not in _instances:
        _instances[name] = _FACTORIES[name]()
    return _instances[name]
