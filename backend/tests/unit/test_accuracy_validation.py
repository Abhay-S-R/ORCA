"""P6.1 (`R-EVID-1`) — the golden-case regression table behind
`docs/competition/DLC_accuracy_validation.md`, run in CI so the confusion-matrix numbers
quoted in the deck and the demo script cannot silently rot.

The held-out window is the Cyclone Gaja replay (`orca/replay/gaja.py`) — the
only dataset in this tree with independently-derived ground truth (IBTrACS
best-track wind speed, mapped through IMD's own cyclonic-intensity scale,
never through `evaluate_marine_safety`'s own thresholds). `docs/
DLC_accuracy_validation.md` names exactly why this substitutes for a real
INCOIS small-vessel-advisory archive (no such historical archive is
reachable from this environment) and what that substitution costs the
number's strength. Skips cleanly, same as `test_gaja_replay.py`, if the
Gaja data files are not present on this machine.
"""
from __future__ import annotations

import pytest

from orca.replay import gaja

pytestmark = pytest.mark.skipif(
    not (gaja.TRACK_FILE.exists() and gaja.ERA5_FILE.exists()),
    reason="Cyclone Gaja replay data not present on this machine (data/cyclone_gaja/)",
)


def _confusion_matrix() -> dict[str, int]:
    """Ground truth NO_GO := IMD Orange/Red cyclone alert (Severe Cyclonic
    Storm, 48kt+ sustained wind) at that hour — INCOIS's own small-vessel
    advisories escalate to "do not go to sea" at the same IMD alert colours,
    which is the chain this substitutes for a direct advisory-text archive.
    Predicted NO_GO := ORCA's actual `evaluate_marine_safety()` verdict for
    that hour, the same function the live query path calls."""
    cascade = gaja.hazard_cascade()
    tp = fn = fp = tn = 0
    for frame in cascade:
        ground_truth_no_go = frame.get("cyclone_alert") in ("Red", "Orange")
        predicted_no_go = frame.get("go_no_go") == "NO_GO"
        if ground_truth_no_go and predicted_no_go:
            tp += 1
        elif ground_truth_no_go and not predicted_no_go:
            fn += 1
        elif not ground_truth_no_go and predicted_no_go:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "n": len(cascade)}


def test_confusion_matrix_matches_the_published_evidence_numbers():
    """The exact TP/FN/FP/TN cited in docs/competition/DLC_accuracy_validation.md's
    table — a change here means that document is now wrong and must be
    regenerated from this same function, not hand-edited."""
    m = _confusion_matrix()
    assert m == {"tp": 17, "fn": 0, "fp": 0, "tn": 39, "n": 56}


def test_no_false_go_across_the_landfall_window():
    """The asymmetric cost the plan names explicitly: a false GO risks a
    life, a false NO_GO costs a day's income. This is the one number in the
    matrix a regression must never move in the wrong direction — a false
    NO_GO regression is a nuisance; a false GO regression is silently
    dangerous and gets its own named assertion rather than living only
    inside the combined dict above."""
    assert _confusion_matrix()["fn"] == 0


if __name__ == "__main__":
    m = _confusion_matrix()
    print("Gaja replay confusion matrix:", m)
