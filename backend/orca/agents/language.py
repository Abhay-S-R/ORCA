"""Agent 1 (User Interaction) — language detection & translation, plan §4 S6
Day 6, extended Phase 3 D1 Day 16 to the full ten-language requirement
(Architecture §2.1 / Master Requirements: Hindi, Tamil, Telugu, Malayalam,
Kannada, Bengali, Marathi, Gujarati, Odia, English).

`detect_language` is real: deterministic Unicode-block script detection.
Eight of the nine Indic scripts here occupy disjoint Unicode blocks, so
detection between them is exact, not a statistical guess — same spirit as
Agent 12's distress detection (plan §4 S2 — pattern match, not semantic
inference). The one honest exception: Marathi and Hindi both use the
Devanagari block, and script alone cannot tell them apart — Devanagari text
resolves to "hi" here, a stated approximation, not a silent one. A real
disambiguator (lexical heuristics or the ASR/NMT model's own language ID,
plan §4 D1 Day 16) is future work, not claimed as done.

IndicTrans2's distilled 200M models are themselves multilingual across all
22 scheduled Indian languages in one checkpoint per direction — the two
models already loaded for Tamil/Hindi need no new weights for the other
seven; only the FLORES-200 code table below had to grow.

`IndicTrans2Backend` is real, local inference — the weights are downloaded
(backend/scripts/download_ml_models.py) and confirmed working end-to-end
while writing this (Tamil/Hindi <-> English, both directions, both models).
Heavy imports (torch, transformers, IndicTransToolkit) are function-local so
importing this module — including for `detect_language` alone, which every
query needs — never pulls in ~2GB of ML libraries. Models load lazily on
first actual translate() call, not at import or registration time.

PINNED VERSION NOTE: transformers must stay at 4.46.3, not latest. Newer
transformers (5.x, confirmed against 5.16.1) removed
`PreTrainedTokenizerBase` from `transformers.tokenization_utils`, which
IndicTransToolkit imports directly and has no version pin against — the
import fails hard, not a deprecation warning. Confirmed by hitting this
exact break while setting this up, not read about it.

`translate_to_english` / `translate_from_english` are the seam Bhashini
slots into later (same interface, config swap) — calling either without a
registered backend raises loudly rather than silently returning source text
as if translated.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Protocol

from orca import local_models
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth

if TYPE_CHECKING:
    from orca.state import ORCAState

Language = Literal["ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en"]

# Unicode script blocks — disjoint for every pair except Devanagari, which
# Hindi and Marathi both use (see module docstring). Order in this table is
# the tie-break order in detect_language below and is otherwise irrelevant.
_SCRIPT_BLOCKS: tuple[tuple[Language, int, int], ...] = (
    ("ta", 0x0B80, 0x0BFF),  # Tamil
    ("te", 0x0C00, 0x0C7F),  # Telugu
    ("kn", 0x0C80, 0x0CFF),  # Kannada
    ("ml", 0x0D00, 0x0D7F),  # Malayalam
    ("bn", 0x0980, 0x09FF),  # Bengali
    ("or", 0x0B00, 0x0B7F),  # Odia
    ("gu", 0x0A80, 0x0AFF),  # Gujarati
    ("hi", 0x0900, 0x097F),  # Devanagari — Hindi and Marathi both live here
)

# FLORES-200 codes IndicTrans2/IndicTransToolkit expect.
_FLORES_CODE: dict[Language, str] = {
    "ta": "tam_Taml", "hi": "hin_Deva", "te": "tel_Telu", "ml": "mal_Mlym",
    "kn": "kan_Knda", "bn": "ben_Beng", "mr": "mar_Deva", "gu": "guj_Gujr",
    "or": "ory_Orya", "en": "eng_Latn",
}

_ALL_LANGUAGES: tuple[Language, ...] = ("ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en")


def detect_language(text: str) -> Language:
    """Script-range detection across all ten target languages. Falls back
    to "en" when no Indic codepoint from the table above is present.
    Devanagari text always resolves to "hi", never "mr" — a stated
    limitation (module docstring), not a silent misclassification of one
    for the other, since nothing downstream branches differently on it."""
    counts: dict[Language, int] = {lang: 0 for lang, _, _ in _SCRIPT_BLOCKS}
    for ch in text:
        cp = ord(ch)
        for lang, lo, hi in _SCRIPT_BLOCKS:
            if lo <= cp <= hi:
                counts[lang] += 1
                break
    best_lang, best_count = max(counts.items(), key=lambda kv: kv[1])
    return best_lang if best_count > 0 else "en"


# P3.5 (`R-PS-2`)/P3.14 — a short, common-English word list, checked only
# against ALL-Latin text that has no Indic codepoint at all (script-mixed
# text, e.g. Tamil script + English words, is already correctly resolved by
# `detect_language` above — every Indic codepoint anywhere makes it win over
# the untracked "en" bucket). This is the other case: text with NO Indic
# codepoint that may still not be English — "kadal safe-a irukka" (romanized
# Tamil, P3.5/P3.14's own example). Deliberately small and unglamorous: it
# only has to be wrong in one safe direction — treating too much as "maybe
# not English" costs one extra (fast, local) Bhashini TLD call; treating too
# little that way is the actual failure mode this exists to close.
_COMMON_ENGLISH_WORDS = frozenset({
    "the", "is", "it", "safe", "to", "go", "sea", "today", "tomorrow", "and", "in", "a", "i",
    "am", "are", "will", "what", "when", "where", "how", "boat", "fishing", "weather", "wind",
    "wave", "should", "can", "my", "me", "you", "please", "help", "yes", "no", "okay", "thanks",
})


def _low_english_coverage(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return False
    known = sum(1 for w in words if w in _COMMON_ENGLISH_WORDS)
    return (known / len(words)) < 0.5


def detect_language_with_bhashini(text: str) -> Language:
    """P3.5/P3.14 — `detect_language`, extended: when script detection found
    no Indic codepoint AND the Latin text does not read as ordinary English,
    ask Bhashini TLD (text language detection) rather than defaulting to
    English. Falls straight back to the script-only result when Bhashini is
    unreachable or unconfigured — there is no local rung for GENERAL
    romanized language detection (only for the distress phrase list itself,
    which is safety-critical and stays fully offline — see
    orca/agents/distress.py's `_ROMANIZED_DISTRESS_PATTERNS`)."""
    script_result = detect_language(text)
    if script_result != "en" or not _low_english_coverage(text):
        return script_result
    try:
        from orca.agents import bhashini

        code = bhashini.detect_language(text)
        return _coerce_language(code)
    except Exception:
        return script_result  # Bhashini unavailable/unconfigured — degrade to the script-only call


def _coerce_language(value: str) -> Language:
    """ORCAState.detected_language is a plain `str` (Architecture §5); the
    Literal type here is stricter. Same gap as coerce_reasoning_depth
    (orca/contracts.py) for the same reason — a stale/typo'd value degrades
    to "en" here rather than reaching translate_from_english untyped."""
    if value in _ALL_LANGUAGES:
        return value  # type: ignore[return-value]
    return "en"


class TranslationBackend(Protocol):
    """The seam IndicTrans2 (Phase 1 primary) and Bhashini (when access
    lands) both implement — a config swap, not a code change.
    """

    def translate(self, text: str, source: Language, target: Language) -> str: ...


class IndicTrans2Backend:
    """Local IndicTrans2, distilled 200M models — one for Indic->English, one
    for English->Indic (both directions covered; the architecture's own
    convention is that synthesis happens in English and translation is only
    ever at the edge, so a direct Indic<->Indic call is never needed here).
    """

    _INDIC_TO_EN = "ai4bharat/indictrans2-indic-en-dist-200M"
    _EN_TO_INDIC = "ai4bharat/indictrans2-en-indic-dist-200M"

    def __init__(self) -> None:
        self._models: dict[str, tuple] = {}
        self._processor = None

    def _get_model(self, model_name: str):
        if model_name not in self._models:
            with local_models.loading("IndicTrans2"):
                if model_name in self._models:  # loaded by the thread that held the lock
                    return self._models[model_name]
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
                # transformers resolves its public names through a lazy module, so a
                # checker sees `AutoModelForSeq2SeqLM` as None rather than a class. The
                # sibling AutoTokenizer call above is not flagged only because it
                # happens to resolve; both are the same real, working import.
                # pyrefly: ignore[not-callable]
                model = AutoModelForSeq2SeqLM.from_pretrained(model_name, trust_remote_code=True)
                model.eval()
                self._models[model_name] = (tokenizer, model)
        return self._models[model_name]

    def _get_processor(self):
        if self._processor is None:
            with local_models.loading("IndicTrans2 processor"):
                if self._processor is not None:
                    return self._processor
                try:
                    from IndicTransToolkit.processor import IndicProcessor
                except ModuleNotFoundError as exc:
                    # Optional native dependency (requires MSVC C++ Build Tools on
                    # Windows — requirements.txt leaves it commented out on a dev
                    # machine without them). Surfaced as RuntimeError so it degrades
                    # through the same "no translation backend" path as an
                    # unregistered backend, rather than crashing run_ingress/
                    # run_egress with an exception their narrower except clause
                    # doesn't catch.
                    raise RuntimeError(
                        "IndicTransToolkit is not installed (optional dependency, "
                        "requires MSVC C++ Build Tools on Windows — see requirements.txt)."
                    ) from exc

                self._processor = IndicProcessor(inference=True)
        return self._processor

    def warm(self) -> None:
        """P6.4 (orca_final §14.3) — load both direction models and the
        processor now, off the request path, so the first Tamil/Hindi query
        after a cold start does not pay a ~40s model-load stall mid-demo.
        Called from `main.py`'s startup in a background thread, the same
        `run_in_executor` pattern `intent_embeddings.warm` already uses.
        Exceptions are caught and logged here, not left to propagate into
        the executor's Future — an uncaught one there is never awaited (the
        caller fires-and-forgets it), so it would otherwise surface only as
        asyncio's "Future exception was never retrieved" on every reload, a
        misleading way to spell "IndicTransToolkit isn't installed on this
        machine," which is a real, expected, already-disclosed state
        (`_get_processor`'s own RuntimeError message) and never a startup
        failure."""
        try:
            self._get_model(self._INDIC_TO_EN)
            self._get_model(self._EN_TO_INDIC)
            self._get_processor()
        except Exception:
            logging.getLogger("orca.language").warning("IndicTrans2 warm-up skipped", exc_info=True)

    def translate(self, text: str, source: Language, target: Language) -> str:
        if source == target:
            return text
        import torch

        model_name = self._EN_TO_INDIC if source == "en" else self._INDIC_TO_EN
        tokenizer, model = self._get_model(model_name)
        ip = self._get_processor()
        src_code, tgt_code = _FLORES_CODE[source], _FLORES_CODE[target]

        batch = ip.preprocess_batch([text], src_lang=src_code, tgt_lang=tgt_code)
        inputs = tokenizer(batch, truncation=True, padding="longest", return_tensors="pt")
        with torch.no_grad():
            generated = model.generate(**inputs, max_length=256, num_beams=5)
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        return ip.postprocess_batch(decoded, lang=tgt_code)[0]


_backend: TranslationBackend | None = None


def register_translation_backend(backend: TranslationBackend) -> None:
    global _backend
    _backend = backend


# P3.8 — domain-term masking around NMT. IMBL/PFZ/GO/NO-GO/sector codes and
# every number are exactly what a marine safety answer cannot afford a
# translation model to paraphrase, mistranslate, or drop a decimal from.
#
# The placeholder format below (`ZKEEPZ0Z`, `ZKEEPZ1Z`, …) replaced an
# earlier bracket scheme (`⟦0⟧`) that looked safer and was not: verified
# live against Bhashini NMT on 2026-09-23, `⟦0⟧` came back as a bare `0` —
# the brackets were stripped but the digit kept, so "GO: All Parameters..."
# translated to "0: பாதுகாப்பான..." with no way to tell the corrupted
# placeholder from a real answer. `ZKEEPZ0Z` (and a letter variant,
# `ZKEEPZAZ`) were tested against the same live model and came back
# byte-for-byte unchanged, including with three of them in one sentence and
# Tamil's own word-reordering around them — an all-caps run with no
# punctuation reads to the model as an unknown proper noun to copy, not a
# structure to normalize away. Still a best-effort choice, not a guarantee
# for every model this seam might ever run against (IndicTrans2 included,
# untested here — see module docstring on `IndicTransToolkit`), which is why
# unmasking stays a plain, order-independent string substitution rather than
# something that assumes the live-verified shape is the only one it will
# ever see.
_PROTECTED_TERM = re.compile(
    r"\bIMBL\b|\bPFZ\b|\bNO[-_ ]?GO\b|\bGO\b|\bSEC\d{3}\b"
    r"|[+-]?\d+(?:\.\d+)?\s?(?:m|km|kmh|km/h|kt|kn|nm|°C|%)?\b"
)


def _mask_protected_terms(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"ZKEEPZ{len(tokens) - 1}Z"

    return _PROTECTED_TERM.sub(_sub, text), tokens


def _unmask_protected_terms(text: str, tokens: list[str]) -> str:
    for i, original in enumerate(tokens):
        text = text.replace(f"ZKEEPZ{i}Z", original)
    return text


# (source_provenance.dataset, human rationale prefix) per rung — one table
# both ingress and egress read, so the two spans never drift apart on wording.
_RUNG_LABEL: dict[str, tuple[str, str]] = {
    "bhashini": ("Bhashini ASR/NMT pipeline", "Bhashini"),
    "indictrans2": ("IndicTrans2 (local, indictrans2-indic-en-dist-200M)", "IndicTrans2, local inference"),
}


def _translate_with_rung(text: str, source: Language, target: Language) -> tuple[str, str]:
    """Two rungs: Bhashini NMT first (P3.8 — the primary path once
    credentialed), IndicTrans2 local inference second. Returns (translation,
    rung) so callers can tag their span with which one actually served,
    rather than always claiming the local model regardless of which ran."""
    masked, tokens = _mask_protected_terms(text)
    try:
        from orca.agents import bhashini

        result = bhashini.nmt(masked, source, target)
        return _unmask_protected_terms(result, tokens), "bhashini"
    except Exception:
        pass  # not configured, unreachable, or timed out — fall to the local rung
    if _backend is None:
        raise RuntimeError(
            "No translation backend registered. Pull IndicTrans2 weights via "
            "backend/scripts/download_ml_models.py and register an IndicTrans2 "
            "backend before calling this (plan §4 S6 pre-Phase-1 action item)."
        )
    result = _backend.translate(masked, source=source, target=target)
    return _unmask_protected_terms(result, tokens), "indictrans2"


def translate_to_english(text: str, source: Language) -> str:
    if source == "en":
        return text
    return _translate_with_rung(text, source, "en")[0]


def translate_from_english(text: str, target: Language) -> str:
    if target == "en":
        return text
    return _translate_with_rung(text, "en", target)[0]


# --- Agent entry points (Architecture: "Ingress & Egress") -------------------
#
# Two call sites, not one run(state) — Agent 1 genuinely runs twice per
# query: once before Planning (detect + translate in), once after Reporting
# (translate the assembled English response back out). Forcing both through
# a single run() would need a stage flag with no natural home in ORCAState;
# two functions matching the architecture's own "ingress & egress" framing
# is the more honest shape.


def query_language(raw: str, user_language_default: str | None = None) -> Language:
    """The language a query is written in."""
    detected = detect_language_with_bhashini(raw)
    # P3.1 — script detection on empty/no-Indic-codepoint text always falls
    # to "en" (module docstring); for a signed-in user that is a wrong
    # default, not a neutral one, e.g. the SOS control fires with no text
    # message at all. A language actually found IN the text always wins —
    # this only fills the gap when detection found nothing to go on.
    if not raw.strip() and user_language_default:
        detected = _coerce_language(user_language_default)
    return detected


def english_query(raw: str, detected: Language) -> tuple[str, str]:
    """(English text, rung). Raises RuntimeError when no rung can translate.
    Called by /query before the graph, because the place, vessel and command
    parsers there are English-only and a Kannada "ಕೊಚ್ಚಿ" never matches
    "Kochi"; ingress then reuses that result via `pretranslated`."""
    if detected == "en":
        return raw, "passthrough"
    return _translate_with_rung(raw, detected, "en")


def run_ingress(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Detects language and translates the raw
    query to English for everything downstream (Planning's keyword matcher
    and every specialist agent are English-only by design)."""
    raw = state.get("raw_user_query", "") or ""
    pre = state.get("pretranslated") or {}
    reuse = pre.get("raw") == raw
    detected = _coerce_language(pre["language"]) if reuse else query_language(raw, state.get("user_language_default"))
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    engine = None
    try:
        normalized, rung = (pre["english"], pre["rung"]) if reuse else english_query(raw, detected)
        status: Literal["ok", "degraded"] = "ok"
        # P3.8 — the span names which rung actually served, Bhashini or the
        # local offline fallback, rather than always claiming IndicTrans2.
        if rung == "passthrough":
            dataset = "IndicTrans2 (local, indictrans2-indic-en-dist-200M)"
            confidence = Confidence(score="HIGH", rationale="already English, no translation needed")
        else:
            dataset, rung_label = _RUNG_LABEL[rung]
            engine = "Bhashini NMT" if rung == "bhashini" else None
            confidence = Confidence(
                score="MEDIUM",  # neither rung independently WER/BLEU-validated yet
                rationale=f"{rung_label} {detected}->en",
            )
        error_detail = None
    except RuntimeError as exc:
        # No backend registered — degrade to passing the raw text through
        # rather than crashing the graph. Planning's English-keyword table
        # will not match a Tamil/Hindi string, so this correctly falls
        # through to the no-match fallback rather than silently mistranslating.
        normalized = raw
        dataset, _ = _RUNG_LABEL["indictrans2"]
        status = "degraded"
        confidence = Confidence(score="LOW_DATA", rationale=f"No translation backend: {exc}")
        error_detail = str(exc)

    return AgentResult(
        agent_name="language_ingress",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"raw_user_query": raw},
        outputs={"detected_language": detected, "normalized_english_query": normalized},
        source_provenance=SourceProvenance(
            dataset=dataset,
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
        engine=engine,
    )


def run_egress(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Translates the assembled English response
    back to the query's detected language. English queries pass through
    untouched (translate_from_english short-circuits on target == "en")."""
    target = _coerce_language(state.get("detected_language", "en") or "en")
    english_text = state.get("final_english_response", "") or ""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    engine = None
    try:
        vernacular, rung = (english_text, "passthrough") if target == "en" else _translate_with_rung(english_text, "en", target)
        status: Literal["ok", "degraded"] = "ok"
        dataset = "IndicTrans2 (local, indictrans2-en-indic-dist-200M)" if rung != "bhashini" else _RUNG_LABEL["bhashini"][0]
        engine = "Bhashini NMT" if rung == "bhashini" else None
        rung_label = "Bhashini" if rung == "bhashini" else "IndicTrans2, local inference"
        confidence = Confidence(
            score="MEDIUM",
            rationale=f"{rung_label} en->{target}" if rung != "passthrough" else "already English",
        )
        error_detail = None
    except RuntimeError as exc:
        vernacular = english_text  # degrade to English rather than crash the response
        rung = "passthrough"
        dataset = "IndicTrans2 (local, indictrans2-en-indic-dist-200M)"
        status = "degraded"
        confidence = Confidence(score="LOW_DATA", rationale=f"No translation backend: {exc}")
        error_detail = str(exc)

    # The "Data limited" reason is shown beside the answer, so it speaks the
    # answer's language too; English if that one translation fails.
    reason = state.get("confidence_reason")
    if reason and target != "en" and rung != "passthrough":
        try:
            reason, _ = _translate_with_rung(reason, "en", target)
        except RuntimeError:
            pass

    return AgentResult(
        agent_name="language_egress",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"final_english_response": english_text, "target_language": target},
        outputs={"final_vernacular_response": vernacular, "confidence_reason": reason},
        source_provenance=SourceProvenance(
            dataset=dataset,
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
        engine=engine,
    )


if __name__ == "__main__":
    assert detect_language("நாளை காலை கடலுக்குச் செல்வது பாதுகாப்பானதா?") == "ta"
    assert detect_language("క్రొత్త రోజు మొదలైంది") == "te"
    assert detect_language("ನಾಳೆ ಸಮುದ್ರಕ್ಕೆ ಹೋಗುವುದು ಸುರಕ್ಷಿತವೇ") == "kn"
    assert detect_language("നാളെ കടലിൽ പോകുന്നത് സുരക്ഷിതമാണോ") == "ml"
    assert detect_language("আগামীকাল সমুদ্রে যাওয়া কি নিরাপদ") == "bn"
    assert detect_language("ଆସନ୍ତାକାଲି ସମୁଦ୍ରକୁ ଯିବା ସୁରକ୍ଷିତ କି") == "or"
    assert detect_language("આવતીકાલે દરિયામાં જવું સલામત છે") == "gu"
    assert detect_language("क्या कल सुबह समुद्र में जाना सुरक्षित है?") == "hi"
    assert detect_language("Is it safe to go to sea tomorrow morning?") == "en"
    assert set(_FLORES_CODE) == set(_ALL_LANGUAGES)
    assert translate_to_english("hello", "en") == "hello"
    try:
        translate_to_english("வணக்கம்", "ta")
        raise AssertionError("expected RuntimeError with no backend registered")
    except RuntimeError:
        pass
    print("language self-check ok")
