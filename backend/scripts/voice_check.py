"""voice_check: voice a corpus of real answers, read it back, and show the words the voice got wrong.

    python scripts/voice_check.py                         # the kept English corpus, male voice
    python scripts/voice_check.py --limit 5               # the first five answers
    python scripts/voice_check.py --text "Wave height is 1 m."   # one sentence
    python scripts/voice_check.py --lang kn --corpus my.jsonl     # another language (the file's "text" in that language)
    python scripts/voice_check.py --save-audio out/        # keep the WAVs to listen to
    python scripts/voice_check.py --text "..." --timeline   # which word is at which second (to name a doubled word)

What it does, per answer: `voice.speakable` (exactly what the app sends the voice), Bhashini TTS (the same
backend and gender the app uses, so the name splice and the male voice are included), then speech recognition
(faster-whisper "small", the model the app already caches) on the audio, then a word-by-word comparison with
what was meant. A word the recogniser heard differently is a CANDIDATE for a mispronunciation: it is how
"height" (heard "hate"), "roughly" ("really") and "relied" ("releaid") were found. Recognition is not an ear:
it can mishear a word that sounds fine, so the report says "heard", not "wrong", and the user's ear decides.
Add a confirmed word to `orca/agents/speech_lexicon.py` (ENGLISH_RESPELLING) with the evidence.

It needs the network (Bhashini), a Bhashini account in `.env` and the faster-whisper weights. It is a manual
tool, not a CI step: a CI run must not depend on a government speech service being up.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Spellings the recogniser and the app disagree on without anyone being wrong: spelling variants, the symbol
# the recogniser writes for a unit ("km" for "kilometers"), and compounds it writes as one word.
_EQUIVALENT = {
    "metres": "meter", "metre": "meter", "meters": "meter", "m": "meter",
    "kilometres": "kilometer", "kilometre": "kilometer", "kilometers": "kilometer", "km": "kilometer",
    "centre": "center", "grey": "gray", "okay": "ok",
}
# Pairs that sound the same: not a mispronunciation, whichever the recogniser chose.
_SAME_SOUND = {("off", "of"), ("sea", "see"), ("i'm", "i am"), ("i'll", "it'll"), ("i'll", "ill"), ("is", "his")}
_COMPOUNDS = {
    "i am": "i'm", "it is": "it's", "do not": "don't", "cannot": "can't", "can not": "can't",
    "north west": "northwest", "north east": "northeast", "south west": "southwest", "south east": "southeast",
    "north north west": "north northwest", "north north east": "north northeast", "south south west": "south southwest",
    "south south east": "south southeast", "east north east": "east northeast", "east south east": "east southeast",
    "west north west": "west northwest", "west south west": "west southwest",
}


def _words(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 1,000
    text = re.sub(r"[-‐-―]", " ", text)  # north-west, north north-west
    text = re.sub(r"\b(?:" + "|".join(sorted(_COMPOUNDS, key=len, reverse=True)) + r")\b", lambda m: _COMPOUNDS[m.group(0)], text)
    words = re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?", text)
    return [_EQUIVALENT.get(w, w) for w in words]


def _intended(spoken: str) -> list[str]:
    """The words that were MEANT: the spoken text with the respellings put back ("hite" is meant as "height")."""
    from orca.agents.speech_lexicon import ENGLISH_ACRONYMS, ENGLISH_RESPELLING

    text = spoken
    for word, respelled in ENGLISH_RESPELLING.items():
        text = re.sub(rf"\b{re.escape(respelled)}\b", word, text, flags=re.IGNORECASE)
    # An acronym spoken as letters ("pee ef zee") is meant as the acronym: the recogniser writes "PFZ" when it
    # hears it right. One spoken as the words it stands for ("marine protected area") is checked as words.
    for acronym, spoken_form in ENGLISH_ACRONYMS.items():
        if all(len(token) <= 4 for token in spoken_form.split()):
            text = re.sub(rf"\b{re.escape(spoken_form)}\b", acronym.replace("-", ""), text)
    return _words(text)


def long_pauses(samples, rate: int, min_len: float = 0.45, threshold: float = 0.012) -> list[tuple[float, float]]:
    """(start second, length in seconds) of every silence of at least `min_len` seconds. The voice's own gap
    between sentences is 0.17-0.32 s; anything longer is the service cutting a long text (it does so at about
    25 s, even inside a sentence), which is what `voice.split_for_bhashini` prevents."""
    import numpy as np

    hop = max(1, int(0.005 * rate))
    frames = len(samples) // hop
    env = np.sqrt((np.asarray(samples[: frames * hop], dtype="float64").reshape(frames, hop) ** 2).mean(axis=1))
    out: list[tuple[float, float]] = []
    start = None
    for i, quiet in enumerate(list(env < threshold) + [False]):
        if quiet and start is None:
            start = i
        elif not quiet and start is not None:
            if (i - start) * 0.005 >= min_len:
                out.append((start * 0.005, (i - start) * 0.005))
            start = None
    return out


def format_timeline(words: list[tuple[str, float, float]], per_line: int = 6) -> str:
    """"0:07.2  wind,  tides,  fishing  ..." lines of a few words each, with the time of the first word of the
    line and of every word, so a person who hears something odd at 0:07 can name the word."""
    lines = []
    for i in range(0, len(words), per_line):
        chunk = words[i:i + per_line]
        start = chunk[0][1]
        lines.append(f"{int(start // 60)}:{start % 60:04.1f}   " + "   ".join(f"{w} ({s:.1f}s)" for w, s, _ in chunk))
    return "\n".join(lines)


def _compare(meant: list[str], heard: list[str]) -> list[tuple[str, str]]:
    """(meant, heard) pairs where a word was heard as a different word. Digits on either side are skipped
    (the recogniser writes "twenty twenty-six" as "2026" and the reverse): numbers are checked by eye."""
    out: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(a=meant, b=heard, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag != "replace":
            continue
        a, b = meant[a0:a1], heard[b0:b1]
        if any(w[0].isdigit() for w in a + b):
            continue
        if len(a) == len(b):
            out += [(x, y) for x, y in zip(a, b, strict=True) if x != y and (x, y) not in _SAME_SOUND]
        elif (" ".join(a), " ".join(b)) not in _SAME_SOUND:
            out.append((" ".join(a), " ".join(b)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(ROOT / "tests" / "voice_corpus_en.jsonl"))
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--text", default="", help="check this one text instead of a corpus")
    ap.add_argument("--save-audio", default="", help="a folder to keep the WAVs in")
    ap.add_argument("--json", default="", help="write the full result here")
    ap.add_argument("--timeline", action="store_true", help="print each word with the second it is spoken at")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT.parent / ".env")
    import numpy as np
    from faster_whisper import WhisperModel

    from orca.agents import bhashini, voice

    bhashini.TTS_TIMEOUT_S = 40.0
    bhashini.TIMEOUT_S = 25.0
    if args.text:
        items = [{"prompt": "(--text)", "text": args.text}]
    else:
        items = [json.loads(line) for line in Path(args.corpus).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        items = items[: args.limit]
    keep = Path(args.save_audio) if args.save_audio else None
    if keep:
        keep.mkdir(parents=True, exist_ok=True)

    asr = WhisperModel("small", device="cpu", compute_type="int8")
    backend = voice.BhashiniTtsBackend()
    counts: Counter[tuple[str, str]] = Counter()
    total_words = 0
    report = []
    for n, item in enumerate(items, 1):
        spoken = voice.speakable(item["text"], args.lang)  # type: ignore[arg-type]
        try:
            wav = backend.speak(spoken, args.lang)  # type: ignore[arg-type]
        except Exception as exc:  # the service is down or slow: say so, do not stop the run
            print(f"[{n}/{len(items)}] {item['prompt']!r}: TTS FAILED ({type(exc).__name__})")
            continue
        if keep:
            (keep / f"{n:02d}.wav").write_bytes(wav)
        samples, rate = voice._wav_to_array(wav)
        samples = np.interp(np.linspace(0, len(samples) - 1, int(len(samples) * 16000 / rate)), np.arange(len(samples)), samples)
        segments, _ = asr.transcribe(
            samples.astype("float32"), language=args.lang, beam_size=5, condition_on_previous_text=False, word_timestamps=args.timeline,
        )
        segments = list(segments)
        heard_text = " ".join(s.text.strip() for s in segments)
        if args.timeline:
            timed = [(w.word.strip(), w.start, w.end) for seg in segments for w in (seg.words or [])]
            print(f"\nSPOKEN : {spoken}\n\n" + format_timeline(timed) + "\n")
        meant = _intended(spoken)
        diffs = _compare(meant, _words(heard_text))
        pauses = long_pauses(samples, 16000)
        total_words += len(meant)
        counts.update(diffs)
        report.append({"prompt": item["prompt"], "spoken": spoken, "heard": heard_text, "differences": diffs, "pauses": pauses})
        mark = "ok  " if not diffs else f"{len(diffs):2d} ?"
        print(f"[{n}/{len(items)}] {mark} {item['prompt'][:60]!r}")
        for start, length in pauses:
            print(f"        a {length * 1000:.0f} ms silence at {start:.1f}s (a sentence gap is 170-320 ms; check the text there)")
        for meant_word, heard_word in diffs:
            print(f"        meant {meant_word!r:18} heard {heard_word!r}")

    print(f"\n{len(report)} answers, {total_words} words, {sum(counts.values())} words heard differently "
          f"({100 * sum(counts.values()) / max(total_words, 1):.1f}%).")
    if counts:
        print("\nMost frequent (meant -> heard); add a confirmed one to ENGLISH_RESPELLING with its evidence:")
        for (a, b), c in counts.most_common(25):
            print(f"  {c:2d}x  {a!r} -> {b!r}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
