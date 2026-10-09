"""VOICE-6: the comparison logic of scripts/voice_check.py (the part that needs no network or model)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "voice_check.py"
spec = importlib.util.spec_from_file_location("voice_check", SCRIPT)
assert spec and spec.loader
voice_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice_check)


def test_words_are_lowercased_unhyphenated_and_spelling_variants_equalised():
    assert voice_check._words("North-West, 1,000 Metres; it’s OK") == ["northwest", "1000", "meter", "it's", "ok"]


def test_units_compasses_and_homophones_are_not_reported_as_mispronunciations():
    meant = voice_check._words("16 kilometres north north-west, off the sea, I'm here")
    heard = voice_check._words("16 km north northwest of the see I am here")
    assert voice_check._compare(meant, heard) == []


def test_a_word_heard_as_another_word_is_reported_with_both():
    meant = voice_check._words("The wave height is low")
    heard = voice_check._words("The wave hate is low")
    assert voice_check._compare(meant, heard) == [("height", "hate")]


def test_identical_text_and_missing_words_are_not_reported_as_replacements():
    assert voice_check._compare(["a", "b", "c"], ["a", "b", "c"]) == []
    assert voice_check._compare(["a", "b", "c"], ["a", "c"]) == []  # a dropped word is not a mispronunciation


def test_numbers_are_skipped_because_recognition_writes_them_differently():
    meant = voice_check._words("valid on 2 October twenty twenty-six")
    heard = voice_check._words("valid on 2 October 2026")
    assert voice_check._compare(meant, heard) == []


def test_a_respelled_word_is_put_back_so_it_is_checked_as_the_word_that_was_meant():
    meant = voice_check._intended("Wave hite is low, ruffley 5 kilometres, re-lied on")
    assert meant[:3] == ["wave", "height", "is"] and "roughly" in meant and "relied" in meant
    # heard right: no difference; heard wrong: reported against the ORIGINAL word
    assert voice_check._compare(meant, voice_check._words("Wave height is low roughly 5 kilometers relied on")) == []
    assert ("height", "hate") in voice_check._compare(meant, voice_check._words("Wave hate is low roughly 5 kilometers relied on"))


def test_the_kept_corpus_exists_is_valid_and_has_the_users_report_first():
    import json

    rows = [json.loads(line) for line in (SCRIPT.parents[1] / "tests" / "voice_corpus_en.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 20 and all(r["text"].strip() for r in rows)
    assert "no MPA breach" in rows[0]["text"] and "relied on" in rows[0]["text"]


def test_an_acronym_spoken_as_letters_is_meant_as_the_acronym_but_one_spoken_as_words_is_checked_as_words():
    meant = voice_check._intended("the pee ef zee and the marine protected area and eye em bee el")
    assert "pfz" in meant and "imbl" in meant
    assert "marine" in meant and "protected" in meant and "area" in meant
    assert voice_check._compare(meant, voice_check._words("the PFZ and the marine protected area and IMBL")) == []


def test_the_timeline_names_each_word_with_its_second():
    words = [("wave", 6.04, 6.4), ("height", 6.4, 6.9), ("is", 6.9, 7.0), ("low", 7.0, 7.3)]
    out = voice_check.format_timeline(words, per_line=2)
    assert out.splitlines() == ["0:06.0   wave (6.0s)   height (6.4s)", "0:06.9   is (6.9s)   low (7.0s)"]
    assert voice_check.format_timeline([("x", 75.2, 75.5)]) == "1:15.2   x (75.2s)"


def _load_respell():
    spec = importlib.util.spec_from_file_location("voice_respell", SCRIPT.with_name("voice_respell.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_spelling_is_scored_by_how_many_carrier_sentences_read_it_right():
    respell = _load_respell()
    reads = {"Wave hite is low.": "Wave height is low.", "The hite is 2 m.": "The hate is two meters."}
    score, example = respell.score_spelling("height", "hite", ["Wave height is low.", "The height is 2 m."], lambda text: reads[text])
    assert score == 1 and example == "The hate is two meters."


def test_the_default_candidates_start_with_the_plain_word_and_have_no_duplicates():
    respell = _load_respell()
    out = respell.default_candidates("height")
    assert out[0] == "height" and len(out) == len(set(out)) and len(out) >= 2


def test_a_long_silence_is_found_and_a_normal_sentence_gap_is_not():
    import numpy as np

    rate = 16000
    tone = (0.3 * np.sin(2 * np.pi * 200 * np.arange(rate) / rate)).astype("float32")
    gap = lambda seconds: np.zeros(int(seconds * rate), dtype="float32")
    audio = np.concatenate([tone, gap(0.25), tone, gap(0.7), tone])
    found = voice_check.long_pauses(audio, rate)
    assert len(found) == 1 and abs(found[0][0] - 2.25) < 0.05 and abs(found[0][1] - 0.7) < 0.05
    assert voice_check.long_pauses(np.concatenate([tone, gap(0.25), tone]), rate) == []
    assert voice_check.long_pauses(tone, rate) == []
