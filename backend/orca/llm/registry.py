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
    """Rotates across every configured Gemini key on a per-key rate limit.

    Found 2026-09-26: five keys (`GEMINI_API_KEY`..`GEMINI_API_KEY5`) were
    sitting in `.env` and only the first was ever used — this class read a
    single key and nothing rotated it, the same class of gap `groq_keys()`
    had (see its own docstring). A 429/RESOURCE_EXHAUSTED/quota error is
    retried on the next key; a 503/"unavailable" is the model overloaded for
    everyone, not this key's quota, and is NOT retried here — a stalled model
    behind key 2 is stalled behind every key, and `tiers.py`'s own chain (a
    second model, then Groq, then local) is what a genuine outage needs, not
    five slower attempts at the same wall.
    """

    _KEY_RATE_LIMIT_MARKERS = ("429", "resource_exhausted", "rate limit", "quota")

    def __init__(self) -> None:
        # modern official vendor SDK — confined to this file. mypy sees `google`
        # as a namespace package contributed to by several installed Google
        # libraries and cannot always resolve `genai` under it, though the
        # import is real and works at runtime (google-genai's own package).
        from google import genai  # type: ignore[attr-defined]

        keys = gemini_keys()
        if not keys:
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
        self._clients = [
            genai.Client(api_key=k, http_options=genai.types.HttpOptions(timeout=_TIMEOUT_MS)) for k in keys
        ]

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
        last_exc: Exception = RuntimeError("no Gemini key configured")
        for i, client in enumerate(self._clients):
            try:
                if len(messages) == 1:
                    resp = client.models.generate_content(model=model, contents=messages[0]["content"], **kw)
                    return resp.text or ""
                chat = client.chats.create(model=model)
                for m in messages[:-1]:
                    chat.send_message(m["content"])
                resp = chat.send_message(messages[-1]["content"], **kw)
                return resp.text or ""
            except Exception as exc:  # decide retry-next-key vs propagate below
                last_exc = exc
                more_keys = i + 1 < len(self._clients)
                if more_keys and any(m in str(exc).lower() for m in self._KEY_RATE_LIMIT_MARKERS):
                    continue
                raise
        raise last_exc  # unreachable: the loop above always returns or raises

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        # ponytail: first key only — nothing calls stream() in production yet
        # (chatbot plan F2 adds token streaming to /ask); rotate here too once
        # something does.
        if not messages:
            return
        client = self._clients[0]
        if len(messages) == 1:
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=messages[0]["content"],
                **kw,
            ):
                if chunk.text:
                    yield chunk.text
            return

        chat = client.chats.create(model=model)
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


def _numbered_keys(prefix: str) -> list[str]:
    """Every value of `<prefix>`, `<prefix>N` or `<prefix>_N` in the
    environment, in ascending N (the bare name first) — however many were
    typed into `.env`. Both `KEY2` and `KEY_2` are accepted: found 2026-09-26,
    `groq_keys()` required the underscore and matched none of the five keys
    actually in `.env` (`GROQ_API_KEY1`..`GROQ_API_KEY5`, no underscore), so
    Groq had never actually been reached despite being configured. A value
    may also hold a comma-separated list. Deduplicated by value, not name, so
    `GEMINI_API_KEY` and `GOOGLE_API_KEY` naming the same key once is one key,
    not a wasted rotation slot."""
    names = sorted(
        (n for n in os.environ if re.fullmatch(rf"{prefix}_?(\d+)?", n)),
        key=lambda n: int(m.group()) if (m := re.search(r"\d+$", n)) else 0,
    )
    seen: set[str] = set()
    keys: list[str] = []
    for n in names:
        for k in os.environ[n].split(","):
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def groq_keys() -> list[str]:
    """Every Groq key in the environment. Several free-tier keys are several
    rate limits."""
    return _numbered_keys("GROQ_API_KEY")


def gemini_keys() -> list[str]:
    """Every Gemini key in the environment — `GEMINI_API_KEY`/`GOOGLE_API_KEY`
    and their numbered siblings. Found 2026-09-26: five keys were configured
    and only the first was ever used; `GeminiProvider` below now rotates
    across all of them the same way `GroqProvider` already did for Groq."""
    return _numbered_keys("GEMINI_API_KEY") or _numbered_keys("GOOGLE_API_KEY")


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


class GatewayProvider:
    """LLM Gateway provider using LangChain's ChatOpenAI connected to
    https://llm-gateway-jugn.vercel.app/v1 (or LLM_GATEWAY_BASE_URL)."""

    def __init__(self) -> None:
        self._base_url = (
            os.environ.get("LLM_GATEWAY_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://llm-gateway-jugn.vercel.app/v1"
        )
        self._api_key = (
            os.environ.get("LLM_GATEWAY_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or "gw_live_V9r2sNiCMr-8O_X2h5hMK-6M0J7YwYTuwiE-4UxxzLY"
        )
        if not self._api_key:
            raise KeyError("Neither LLM_GATEWAY_API_KEY nor OPENAI_API_KEY is set in environment")

    def get_client(self, model: str = "smart", timeout_s: float | None = None, **extra: Any) -> Any:
        from langchain_openai import ChatOpenAI

        timeout = timeout_s if timeout_s is not None else 30.0
        # For thinking-capable models on this gateway, thinking tokens count towards max_tokens.
        # Ensure a generous ceiling if low max_tokens was passed.
        max_tokens = extra.pop("max_tokens", None)
        if max_tokens is not None and int(max_tokens) < 1024:
            max_tokens = 2048

        kwargs: dict[str, Any] = {
            "base_url": self._base_url,
            "api_key": self._api_key,
            "model": model or "smart",
            "request_timeout": timeout,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        kwargs.update(extra)
        return ChatOpenAI(**kwargs)

    def complete(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> str:
        timeout_s = kw.pop("timeout_s", None)
        client = self.get_client(model=model, timeout_s=timeout_s, **kw)
        resp = client.invoke(messages)
        content = getattr(resp, "content", "")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            text = str(content or "")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def stream(self, messages: list[dict[str, str]], *, model: str, **kw: Any) -> Iterator[str]:
        timeout_s = kw.pop("timeout_s", None)
        client = self.get_client(model=model, timeout_s=timeout_s, **kw)
        for chunk in client.stream(messages):
            yield str(chunk.content or "")


def get_chat_openai(model: str = "smart", **kwargs: Any) -> Any:
    """Returns a configured LangChain ChatOpenAI instance pointing to the LLM gateway."""
    provider = get_provider("gateway")
    if isinstance(provider, GatewayProvider):
        return provider.get_client(model=model, **kwargs)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        base_url=os.environ.get("LLM_GATEWAY_BASE_URL", "https://llm-gateway-jugn.vercel.app/v1"),
        api_key=os.environ.get("LLM_GATEWAY_API_KEY", "gw_live_V9r2sNiCMr-8O_X2h5hMK-6M0J7YwYTuwiE-4UxxzLY"),
        model=model,
        **kwargs,
    )


# name -> lazy factory. Lazy so importing the registry never requires every
# vendor SDK to be installed — only the ones a tier actually resolves to.
_FACTORIES: dict[str, Callable[[], Provider]] = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "ollama": OllamaProvider,
    "gateway": GatewayProvider,
    "openai": GatewayProvider,
}
_instances: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    if name not in _FACTORIES:
        raise ValueError(f"Unknown LLM provider {name!r}. Registered: {sorted(_FACTORIES)}")
    if name not in _instances:
        _instances[name] = _FACTORIES[name]()
    return _instances[name]
