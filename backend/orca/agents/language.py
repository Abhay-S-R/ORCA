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

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Protocol

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
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name, trust_remote_code=True)
            model.eval()
            self._models[model_name] = (tokenizer, model)
        return self._models[model_name]

    def _get_processor(self):
        if self._processor is None:
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


def translate_to_english(text: str, source: Language) -> str:
    if source == "en":
        return text
    if _backend is None:
        raise RuntimeError(
            "No translation backend registered. Pull IndicTrans2 weights via "
            "backend/scripts/download_ml_models.py and register an IndicTrans2 "
            "backend before calling this (plan §4 S6 pre-Phase-1 action item)."
        )
    return _backend.translate(text, source=source, target="en")


def translate_from_english(text: str, target: Language) -> str:
    if target == "en":
        return text
    if _backend is None:
        raise RuntimeError(
            "No translation backend registered. Pull IndicTrans2 weights via "
            "backend/scripts/download_ml_models.py and register an IndicTrans2 "
            "backend before calling this (plan §4 S6 pre-Phase-1 action item)."
        )
    return _backend.translate(text, source="en", target=target)


# --- Agent entry points (Architecture: "Ingress & Egress") -------------------
#
# Two call sites, not one run(state) — Agent 1 genuinely runs twice per
# query: once before Planning (detect + translate in), once after Reporting
# (translate the assembled English response back out). Forcing both through
# a single run() would need a stage flag with no natural home in ORCAState;
# two functions matching the architecture's own "ingress & egress" framing
# is the more honest shape.


def run_ingress(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Detects language and translates the raw
    query to English for everything downstream (Planning's keyword matcher
    and every specialist agent are English-only by design)."""
    raw = state.get("raw_user_query", "") or ""
    detected = detect_language(raw)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        normalized = translate_to_english(raw, source=detected)
        status: Literal["ok", "degraded"] = "ok"
        confidence = Confidence(
            score="MEDIUM",  # distilled 200M model, not independently WER/BLEU-validated yet
            rationale=f"IndicTrans2 {detected}->en, local inference",
        )
        error_detail = None
    except RuntimeError as exc:
        # No backend registered — degrade to passing the raw text through
        # rather than crashing the graph. Planning's English-keyword table
        # will not match a Tamil/Hindi string, so this correctly falls
        # through to the no-match fallback rather than silently mistranslating.
        normalized = raw
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
            dataset="IndicTrans2 (local, indictrans2-indic-en-dist-200M)",
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
    )


def run_egress(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Translates the assembled English response
    back to the query's detected language. English queries pass through
    untouched (translate_from_english short-circuits on target == "en")."""
    target = _coerce_language(state.get("detected_language", "en") or "en")
    english_text = state.get("final_english_response", "") or ""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        vernacular = translate_from_english(english_text, target=target)
        status: Literal["ok", "degraded"] = "ok"
        confidence = Confidence(score="MEDIUM", rationale=f"IndicTrans2 en->{target}, local inference")
        error_detail = None
    except RuntimeError as exc:
        vernacular = english_text  # degrade to English rather than crash the response
        status = "degraded"
        confidence = Confidence(score="LOW_DATA", rationale=f"No translation backend: {exc}")
        error_detail = str(exc)

    return AgentResult(
        agent_name="language_egress",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"final_english_response": english_text, "target_language": target},
        outputs={"final_vernacular_response": vernacular},
        source_provenance=SourceProvenance(
            dataset="IndicTrans2 (local, indictrans2-en-indic-dist-200M)",
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
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
