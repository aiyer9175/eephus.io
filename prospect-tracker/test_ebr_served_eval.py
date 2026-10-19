# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served eBR eval carries no correlation against runs or wins (task
EBR_2F_FLIP; plan Part 8 8.A; EBR_GATE.md 12.1).

Leg T's and DP-2's r, and any other correlation of eBR with runs scored or wins,
stay in the gate document's part 12.1 and .cache/ebr/preview/. data/ebr_eval.json
carries from the look only the dispositions, the guard pass flags, the floors, the
NOISE flags and the identity receipts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import baserunning_export as bre

ROOT = Path(__file__).parent
EVAL = ROOT / "data" / "ebr_eval.json"

#: A key path naming the outcome the gate's guards are scored against.
_OUTCOME_PATH = re.compile(r"leg_t|dp_?2|vs_runs|vs_wins|team_runs|runs_scored|vs_win|r_off|off_b|wins")
#: A leaf that is a correlation.
_CORR_LEAF = re.compile(r"(^|_)(r|rho|corr|correlation|pearson|spearman)(_|$)")


def _walk(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, path + ("[]",))
    else:
        yield path, o


def _offenders(doc):
    bad = []
    for path, val in _walk(doc):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        low = [p.lower() for p in path]
        joined = "/".join(low)
        if _OUTCOME_PATH.search(joined) and any(_CORR_LEAF.search(p) for p in low):
            bad.append(joined)
        elif _OUTCOME_PATH.search(joined):
            bad.append(joined)
    return bad


def _served():
    return json.loads(EVAL.read_text(encoding="utf-8"))


def test_the_served_eval_carries_no_correlation_against_runs_or_wins():
    assert _offenders(_served()) == []


def test_the_scan_catches_a_planted_leg_t_r():
    planted = {"look": {"leg_t": {"r_off_B": 0.78}, "dp_2": {"r": 0.79}, "x": {"rho_vs_wins": 0.3}}}
    assert len(_offenders(planted)) == 3


def test_the_look_block_carries_only_the_allowed_keys():
    look = _served()["look"]
    assert set(look) == {"status", "commit", "waived_early_read", "finished_at", "dispositions", "floors",
                         "guards", "noise_flags", "bem_plus", "identity_receipts"}
    assert set(look["dispositions"]) == {"leg_e", "leg_e_twin", "e_dp", "e_dp_twin"}
    for k, v in look["dispositions"].items():
        assert v in ("SHIP", "RULED OUT", "UNDECIDED", "RESOLVED_LOSS"), (k, v)
    for k, v in look["guards"].items():
        assert isinstance(v, bool), k


def test_the_served_look_strips_a_full_look_block():
    full = json.loads((bre.EVAL_PREVIEW).read_text(encoding="utf-8")) if bre.EVAL_PREVIEW.exists() else None
    if full is None or not full.get("look"):
        return
    out = bre._served_look(full["look"])
    assert _offenders(out) == []
    assert "reported" not in out and "licenses" not in out


def test_the_repeat_copy_is_only_the_licensed_sentence():
    lk = {"dispositions": {"leg_e": "RESOLVED_LOSS", "leg_e_twin": "RESOLVED_LOSS",
                           "e_dp": "UNDECIDED", "e_dp_twin": "RESOLVED_LOSS"}}
    c = bre.repeat_copy(lk)
    assert c["eBR"] == "repeats less from one season to the next than FanGraphs' BsR on the same runners"
    assert c["DP"] == ""
    lk["dispositions"]["leg_e_twin"] = "UNDECIDED"          # a twin that is not a loss voids the look
    assert bre.repeat_copy(lk)["eBR"] == ""
    assert bre.repeat_copy(None) == {"eBR": "", "DP": ""}
    for word in ("better", "more accurate", "closer to the truth"):
        assert word not in " ".join(c.values())
