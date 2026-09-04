"""Priority lane classification (Architecture §9.10, phase4 plan §8) — a
SAFETY_CHECK-shaped, SHALLOW-or-unset-depth query gets the priority lane;
everything else (a DEEP diagnostic, an explicit non-safety query) gets the
standard lane. Reuses Agent 2's own Tier-1 rules match, so "which lane" can
never disagree with "which agents actually ran" for the same query.
"""
from __future__ import annotations

from orca.api.main import _is_priority_shaped


def test_safety_query_at_default_depth_is_priority():
    assert _is_priority_shaped("is it safe to go to sea tomorrow", None) is True


def test_safety_query_at_shallow_depth_is_priority():
    assert _is_priority_shaped("is it safe to fish today", "SHALLOW") is True


def test_safety_query_at_deep_depth_is_not_priority():
    assert _is_priority_shaped("is it safe to go to sea", "DEEP") is False


def test_non_safety_query_is_not_priority():
    assert _is_priority_shaped("nearest fishing zone", None) is False
