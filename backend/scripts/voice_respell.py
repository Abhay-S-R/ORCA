"""voice_respell: find a spelling of ONE word that the English voice reads right.

    python scripts/voice_respell.py height --carrier "Wave height is 1.5 metres." --carrier "The wave height is low."
    python scripts/voice_respell.py gauge --candidates gage,gayge --carrier "The tide gauge reads 0.7 metres."

For each candidate spelling (the plain word first) it voices the carrier sentences with the word replaced,
reads them back (faster-whisper) and counts in how many the word came back right. Keep a spelling only when it
scores in every carrier sentence, then add it to `ENGLISH_RESPELLING` in `orca/agents/speech_lexicon.py` with
the scores beside it. This is how "height", "roughly", "relied", "gauge" and "zones" were done. The audio is the
same every time for the same text, so a respelling that works keeps working.

Use real sentences from answers as carriers: a word that reads right alone can fail next to its neighbours
("fishing zones" read "fishing ones" although "zones" alone was fine). Needs the network, a Bhashini account in
`.env` and the faster-whisper weights; a manual tool, not a CI step.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Spellings to try when none are given: respellings that commonly fix an English word the voice drops sounds from.
_DEFAULT_CANDIDATES = ("{w}", "{w}-", "ee{w}")


def default_candidates(word: str) -> list[str]:
    """The plain word, then a few mechanical variants (a hyphen after the first syllable, doubled consonants)."""
    out = [word]
    if len(word) > 3:
        out += [word[: len(word) // 2] + "-" + word[len(word) // 2:], re.sub(r"([bcdfglmnprst])", r"\1\1", word, count=1)]
    return list(dict.fromkeys(out))


def score_spelling(word: str, spelled: str, carriers: list[str], heard_for) -> tuple[int, str]:
    """(how many carrier sentences read the word right, one wrong reading as an example)."""
    right, example = 0, ""
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    for carrier in carriers:
        heard = heard_for(pattern.sub(spelled, carrier))
        if pattern.search(heard):
            right += 1
        elif not example:
            example = heard
    return right, example


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("word")
    ap.add_argument("--carrier", action="append", required=True, help="a sentence containing the word (give 3 or 4)")
    ap.add_argument("--candidates", default="", help="comma-separated spellings to try; default: the word and a few variants")
    ap.add_argument("--gender", default="male")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT.parent / ".env")
    import numpy as np
    from faster_whisper import WhisperModel

    from orca.agents import bhashini, voice

    bhashini.TTS_TIMEOUT_S = 40.0
    asr = WhisperModel("small", device="cpu", compute_type="int8")

    def heard_for(text: str) -> str:
        samples, rate = voice._wav_to_array(bhashini.tts(text, "en", args.gender))
        samples = np.interp(np.linspace(0, len(samples) - 1, int(len(samples) * 16000 / rate)), np.arange(len(samples)), samples)
        segments, _ = asr.transcribe(samples.astype("float32"), language="en", beam_size=5, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments)

    candidates = [c.strip() for c in args.candidates.split(",") if c.strip()] or default_candidates(args.word)
    if args.word not in candidates:
        candidates.insert(0, args.word)
    for spelled in candidates:
        right, example = score_spelling(args.word, spelled, args.carrier, heard_for)
        print(f"{spelled!r:18} {right}/{len(args.carrier)}" + (f"   heard e.g.: {example}" if example else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
