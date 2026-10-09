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
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

from orca import engines, local_models
from orca.agents.speech_lexicon import COMPASS_MULTI
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
# The placeholder is a short NUMBER (801, 802, ...) (FIX-PLACEHOLDER-1, 2026-10-09). Its history:
#   * "⟦0⟧" came back as a bare "0" (2026-09-23).
#   * "ZKEEPZ0Z" was copied by Tamil and Hindi, but a translator spells a Latin pseudo-word by ear: in
#     Marathi, Bengali and sometimes Hindi it came back as "झेडकेईईपीझेड5झेड" and the answer LOST the
#     number it stood for (a wave height). Measured 2026-10-09 over six answers in all nine languages:
#     312 of 333 placeholders survived.
#   * A 7-digit number was reformatted with Indian digit grouping ("70,00,043"): 314 of 333.
#   * "[n]" 89 of 90, "#n#" 0 of 90, "Qn Q" 23 of 90, no masking 19 of 90 (units and numbers reworded).
#   * A 3-digit number (801 + n): 333 of 333, in every language, and a 4-digit one 332 of 333.
# Translators leave digits alone, and a 3-digit number is not grouped. All real numbers are masked, so
# no other digit string is in the sentence. Unmasking checks that each placeholder came back exactly
# once; if not, the sentence is translated again without masking rather than losing a number.
# FIX-COMPASS-1 (2026-10-09): ONE token per phrase. Protecting "NNW" separately made "16 km NNW" two adjacent
# placeholders ("801 802"); a translator reads an adjacent pair of numbers as one number and drops or moves
# them (Hindi lost the distance and the direction, Tamil put them in the date, Kannada lost the direction).
# Measured 2026-10-09, nine languages x nine sentences: the previous masking left 71% of sentences intact, one
# token per phrase 96%. A phrase is: a written date ("2 Oct 2026", "October 2, 2026", "2026-10-02"), a time, a
# coordinate pair ("9.915 N, 76.074 E"), a number or range with its unit and a following compass point
# ("16 km NNW", "28-33 m"), a lone compass point, or one of the fixed terms.
_MONTHS_RE = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
_COMPASS_RE = r"(?:" + "|".join(COMPASS_MULTI) + r")"
_NUM_RE = r"\d+(?:\.\d+)?"
_COORD_RE = rf"{_NUM_RE}\s?\u00b0?\s?[NESW](?![A-Za-z])"
_UNIT_RE = r"(?:km/h|kmh|km/hr|km|nm|m/s|m|kt|kn)"
_PROTECTED_TERM = re.compile(
    rf"\b{_NUM_RE}\s+{_MONTHS_RE}\.?(?:\s+\d{{4}})?\b|\b{_MONTHS_RE}\.?\s+{_NUM_RE},?(?:\s+\d{{4}})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b"
    r"|\bIMBL\b|\bPFZ\b|\bNO[-_ ]?GO\b|\bGO\b|\bSEC\d{3}\b"
    rf"|{_COORD_RE}(?:,?\s{_COORD_RE})?"
    rf"|[+-]?{_NUM_RE}(?:\s?[-\u2010-\u2015\u2212]\s?{_NUM_RE})?"
    rf"(?:\s?{_UNIT_RE}(?![A-Za-z])(?:\s{_COMPASS_RE}\b)?|\u00b0C|%)?(?![A-Za-z])"
    rf"|\b{_COMPASS_RE}\b"
)
_PLACEHOLDER_BASE = 801
_MAX_PLACEHOLDERS = 150  # 801..950; an answer with more numbers than this is translated unmasked


# The product's name, written the way a speaker of each language writes it (FIX-NAME-1). Bhashini
# translates a name by its sound, and a model writing a reply in Kannada or Bengali does the same, so
# the spelling changed by language and by sentence ("ಸಾಗರ್ ಸಾರಥಿ", "ಸಾಗರ ಸರಥಿ", "ಸಾಗರ ಸಾಗತಿ", "স্যারথি").
# It is a brand, so code owns it: hidden from the translator like IMBL and the numbers, put back in this
# spelling, and corrected when a model writes it by ear. Every language has an entry.
#   * Confirmed by the user: Devanagari (hi, mr) and Kannada.
#   * Derived, not yet confirmed by a native reader: ta, te, ml, bn, gu, or. They are Bhashini's
#     transliteration of the Latin "Saagara Saarathi", the spelling that reproduces the user's
#     Kannada and Devanagari exactly (the other Latin spellings tried did not). To change one, edit it
#     here: nothing else holds a copy.
PRODUCT_NAME_NATIVE: dict[str, str] = {
    "hi": "सागर सारथी",
    "mr": "सागर सारथी",
    "kn": "ಸಾಗರ ಸಾರಥಿ",
    "ta": "சாகர சாரதி",
    "te": "సాగర సారథి",
    "ml": "സാഗര സാരഥി",
    "bn": "সাগর সারথি",
    "gu": "સાગર સારથી",
    "or": "ସାଗର ସାରଥି",
}
_PRODUCT_NAME = re.compile(r"\bSa+gar\w*\s+Sa+r+a?(?:th|t)i\b", re.IGNORECASE)
_NAME_EDGE = "\"'.,;:!?()[]{}\u2018\u2019\u201c\u201d\u0964\u0965"


def _skeleton(word: str) -> tuple[str, ...]:
    """A word's consonant skeleton, script-free: ("SA", "GA", "RA") for "सागर", "ಸಾಗರ್" and "ସାଗର".
    Vowel signs, the virama and a final vowel drop out, which is exactly where spellings by ear
    differ; a "ya" after a virama (Bengali "স্যা") drops too; tha and ta are one letter, since
    "Sarathi" is heard "Sarati". A letter of another script keeps its Latin-named sound, so a
    Devanagari "थ" inside a Kannada word still counts as "tha"."""
    out: list[str] = []
    after_virama = False
    for ch in word.strip(_NAME_EDGE):
        if unicodedata.category(ch) == "Lo":
            sound = unicodedata.name(ch, "").split()[-1]
            if not (after_virama and sound == "YA"):
                # tha is ta, and Tamil's one letter for sa and ca and for ka and ga is one letter here.
                out.append({"THA": "TA", "CA": "SA", "KA": "GA"}.get(sound, sound))
        after_virama = "VIRAMA" in unicodedata.name(ch, "")
    return tuple(out)


_NAME_SKELETONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def localize_product_name(text: str, language: str) -> str:
    """The product's name in `language`'s own spelling, wherever it appears in `text`: written in
    Latin letters, or spelt by ear in that script (a skeleton match: see `_skeleton`). English and
    a language with no entry are returned unchanged. A word pair that merely resembles the name
    (another consonant) is left alone."""
    native = PRODUCT_NAME_NATIVE.get(language)
    if not native:
        return text
    text = _PRODUCT_NAME.sub(native, text)
    if language not in _NAME_SKELETONS:
        first, second = native.split()
        _NAME_SKELETONS[language] = (_skeleton(first), _skeleton(second))
    want_first, want_second = _NAME_SKELETONS[language]
    words = list(re.finditer(r"\S+", text))
    out: list[str] = []
    last = 0
    i = 0
    while i < len(words):
        if i + 1 < len(words) and _skeleton(words[i].group()) == want_first and _skeleton(words[i + 1].group()) == want_second:
            trail = words[i + 1].group()
            tail = trail[len(trail.rstrip(_NAME_EDGE)):]
            lead = words[i].group()[: len(words[i].group()) - len(words[i].group().lstrip(_NAME_EDGE))]
            out.append(text[last:words[i].start()] + lead + native + tail)
            last = words[i + 1].end()
            i += 2
            continue
        i += 1
    return "".join(out) + text[last:]


_WORD_POINT = {
    "north": "N", "south": "S", "east": "E", "west": "W",
    "northeast": "NE", "northwest": "NW", "southeast": "SE", "southwest": "SW",
}
_POINT_WORD = "(?:" + "|".join(sorted(_WORD_POINT, key=len, reverse=True)) + ")"
# not part of a longer letter run: "A-N-W" and "N-W-X" are not compass points
_LETTER_POINT_RE = re.compile(
    r"(?<![A-Za-z])(?<![A-Za-z][\-\u2010-\u2015.])[NESW](?:[\-\u2010-\u2015.][NESW]){1,2}\.?(?![A-Za-z])(?![\-\u2010-\u2015.][A-Za-z])"
)
_SPELLED_POINT_RE = re.compile(rf"\b{_POINT_WORD}(?:[\-\u2010-\u2015\s]+{_POINT_WORD}){{1,2}}\b", re.IGNORECASE)
_SPELLED_UNITS = (
    (re.compile(rf"({_NUM_RE})\s*(?:kilometres|kilometers|kilometre|kilometer)\b", re.IGNORECASE), r"\1 km"),
    (re.compile(rf"({_NUM_RE})\s*(?:nautical miles?)\b", re.IGNORECASE), r"\1 nm"),
    (re.compile(rf"({_NUM_RE})\s*(?:metres|meters|metre|meter)\b", re.IGNORECASE), r"\1 m"),
)
_RANGE_TO_RE = re.compile(rf"({_NUM_RE})\s+to\s+({_NUM_RE})(?=\s?{_UNIT_RE}(?![A-Za-z]))")


def normalise_compass(text: str) -> str:
    """"N-N-W", "N.N.W.", "west south-west", "north-north-west" -> "NNW", "WSW" (every one of the sixteen points
    that has three letters, and the two-letter letter forms). A word that is only north-west or south-east is
    left alone: translators handle those. A letter sequence that is not a compass point is left alone."""
    points = set(COMPASS_MULTI)

    def letters(m: re.Match[str]) -> str:
        joined = re.sub(r"[^NESW]", "", m.group(0))
        return joined if joined in points else m.group(0)

    def spelled(m: re.Match[str]) -> str:
        joined = "".join(_WORD_POINT[w.lower()] for w in re.findall(r"[A-Za-z]+", m.group(0)))
        return joined if len(joined) == 3 and joined in points else m.group(0)

    return _SPELLED_POINT_RE.sub(spelled, _LETTER_POINT_RE.sub(letters, text))


def normalise_for_translation(text: str) -> str:
    """The English answer in the form that survives translation as a few big tokens: compass spellings as
    abbreviations, and a spelled unit after a number as its symbol ("14.9 kilometres" -> "14.9 km", "28 to 33
    meters" -> "28-33 m"), so that a number, its unit and its compass point are ONE protected phrase and the
    translator is not left to drop a placeholder that stands alone between native words."""
    text = normalise_compass(text)
    for pattern, replacement in _SPELLED_UNITS:
        text = pattern.sub(replacement, text)
    return _RANGE_TO_RE.sub(r"\1-\2", text)


def _mask_protected_terms(text: str) -> tuple[str, list[str]]:
    """The text with each protected term replaced by a 3-digit placeholder, and the originals in order.
    The product's name is deliberately NOT hidden (FIX-NAME-2): it was, and in Marathi and Bengali the
    translator turned the placeholder into gibberish and the answer lost the name. The translator
    writes the name by ear and `localize_product_name` corrects it afterwards."""
    tokens: list[str] = []

    def _keep(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return str(_PLACEHOLDER_BASE + len(tokens) - 1)

    masked = _PROTECTED_TERM.sub(_keep, text)
    if len(tokens) > _MAX_PLACEHOLDERS:
        return text, []
    return masked, tokens


def _unmask_protected_terms(text: str, tokens: list[str]) -> tuple[str, bool]:
    """(the text with each placeholder replaced by its original, whether every placeholder came back
    exactly once). A missing or repeated one means the translator dropped or duplicated a number."""
    seen: dict[int, int] = {}

    def _back(m: re.Match[str]) -> str:
        i = int(m.group(0)) - _PLACEHOLDER_BASE
        if 0 <= i < len(tokens):
            seen[i] = seen.get(i, 0) + 1
            return tokens[i]
        return m.group(0)

    restored = re.sub(r"(?<!\d)\d{3}(?!\d)", _back, text)
    return restored, all(seen.get(i) == 1 for i in range(len(tokens)))


# (source_provenance.dataset, human rationale prefix) per rung — one table
# both ingress and egress read, so the two spans never drift apart on wording.
_RUNG_LABEL: dict[str, tuple[str, str]] = {
    "bhashini": ("Bhashini ASR/NMT pipeline", "Bhashini"),
    "indictrans2": ("IndicTrans2 (local, indictrans2-indic-en-dist-200M)", "IndicTrans2, local inference"),  # only if a backend is registered (tests)
}


def _translate_with_rung(text: str, source: Language, target: Language) -> tuple[str, str]:
    """Two rungs: Bhashini NMT first (P3.8 — the primary path once
    credentialed), IndicTrans2 local inference second. Returns (translation,
    rung) so callers can tag their span with which one actually served,
    rather than always claiming the local model regardless of which ran."""
    if source == "en":
        text = normalise_for_translation(text)
    masked, tokens = _mask_protected_terms(text)

    def _finish(translated: str, translate: Callable[[str], str]) -> str:
        restored, complete = _unmask_protected_terms(translated, tokens)
        if not complete:
            # A protected phrase was dropped, moved or repeated. Translating the WHOLE answer again unmasked
            # spells a compass point in letters and swaps numbers (seen in Tamil), so redo it a sentence at a
            # time: a sentence that comes back whole is kept, and only one that does not is left unmasked.
            logging.getLogger("orca.language").warning("translation lost a protected term; retranslating by sentence")
            restored = _translate_by_sentence(text, translate)
        return localize_product_name(restored, target)

    try:
        from orca.agents import bhashini

        result = bhashini.nmt(masked, source, target)
        return _finish(result, lambda t: bhashini.nmt(t, source, target)), "bhashini"
    except Exception:
        pass  # not configured, unreachable, or timed out — fall to the local rung
    if _backend is None:
        raise RuntimeError("Bhashini could not translate this and no other translation backend is registered.")
    backend = _backend
    result = backend.translate(masked, source=source, target=target)
    return _finish(result, lambda t: backend.translate(t, source=source, target=target)), "indictrans2"


def _translate_by_sentence(text: str, translate: Callable[[str], str]) -> str:
    """`text` translated one sentence at a time, each protected; a sentence whose protected phrases do not all
    come back exactly once is translated again unmasked, so one bad sentence does not cost the others."""
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.?!])\s+", text.strip()):
        if not sentence:
            continue
        masked, tokens = _mask_protected_terms(sentence)
        restored, complete = _unmask_protected_terms(translate(masked), tokens)
        pieces.append(restored if complete else translate(sentence))
    return " ".join(pieces)


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
    """The language a query is written in, from its SCRIPT alone.

    Text with no Indic codepoint, which is English and also romanized Hindi, Tamil, Kannada and the
    rest, resolves to "en" and is passed on exactly as typed (PC5.3, decision D8). It is not sent to
    a language detector and not machine-translated: Bhashini's detector mislabelled short English as
    Malayalam, Odia or Kashmiri (so an English question got a reply in that language), and
    translating romanized text without a transliteration step returns it unchanged. The planning
    model reads the text as typed instead, and replies to such text are in English (decision D11).
    Native script is unaffected: it is still detected by its Unicode block and translated."""
    detected = detect_language(raw)
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
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    engine = None
    try:
        normalized, rung = (pre["english"], pre["rung"]) if reuse else english_query(raw, detected)
        status: Literal["ok", "degraded"] = "ok"
        # P3.8 — the span names which rung actually served, Bhashini or the
        # local offline fallback, rather than always claiming IndicTrans2.
        if rung == "passthrough":
            dataset = engines.NO_TRANSLATION
            engine = engines.NO_TRANSLATION
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
        dataset = engines.NO_TRANSLATION
        engine = engines.NO_TRANSLATION
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
    back to the requested reply language, or else the query's detected one. English queries pass through
    untouched (translate_from_english short-circuits on target == "en")."""
    # PC5.8: an explicit "answer in <language>" request wins; otherwise the language of the
    # question's script (English for Latin text).
    target = _coerce_language(state.get("reply_language") or state.get("detected_language", "en") or "en")
    english_text = state.get("final_english_response", "") or ""
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    engine = None
    try:
        vernacular, rung = (english_text, "passthrough") if target == "en" else _translate_with_rung(english_text, "en", target)
        status: Literal["ok", "degraded"] = "ok"
        if rung == "passthrough":
            dataset = engine = engines.NO_TRANSLATION
            confidence = Confidence(score="HIGH", rationale="already English, no translation needed")
        else:
            dataset = _RUNG_LABEL["bhashini"][0]
            engine = "Bhashini NMT"
            confidence = Confidence(score="MEDIUM", rationale=f"Bhashini en->{target}")
        error_detail = None
    except RuntimeError as exc:
        vernacular = english_text  # degrade to English rather than crash the response
        rung = "passthrough"
        dataset = engine = engines.NO_TRANSLATION
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
