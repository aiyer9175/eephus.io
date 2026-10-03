# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The BUST2 union invariant (docs/efv-2026-10-02/BUST2_GATE.md, registered text):

    "The union BUST-NEVER plus BUST-MLB reproduces the served realized-bust event on
    every resolved row (an invariant test, asserted before the lab runs)."

Two parts. The FIXTURE part always runs and pins the classification against the served
event on synthetic rows, boundaries and negatives included. The LIVE part reads the
current matrices on disk (data/xfv_hitter_matrix.json and data/xfv_pitcher_matrix.json),
classifies every row with efv_dataset.bust2_category and asserts the union on every
resolved row; it reads the bust event, computes no statistic and scores nothing. It
skips, with the reason stated, only when the matrices are absent (CI).

EPOCH_RUN runs the live part at step F before the Arm R arm is built:

    python -m pytest test_bust2_union_invariant.py -p no:cacheprovider -k live -s

A failure there makes Arm R a FAILED ARM (FWAR_LABEL_EPOCH_GATE.md clause (i) point 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_dataset as ed

ROOT = Path(__file__).resolve().parent


def _union_holds(row: dict) -> bool:
    cat = ed.bust2_category(row)
    in_union = cat in ("BUST-NEVER", "BUST-MLB")
    return in_union == bool(ed.served_bust_event(row["target_resolved"]))


# ---------------------------------------------------------------------------
# the fixture part
# ---------------------------------------------------------------------------

def _deb(pk, target, censored=False):
    return {"player_key": pk, "kind": "debuted", "target_resolved": target,
            "target_censored": target, "censored": censored, "weight": 1.0}


def _never(pk, recent=False):
    return {"player_key": pk, "kind": "bust", "target_resolved": 0.0,
            "target_censored": 0.0, "censored": False, "bust_recent": recent,
            "weight": 0.5 if recent else 1.0}


def test_the_cut_is_the_served_bust_event():
    """BUST-MLB's 3.0 is _prem_odds.bust_label's 0.5-per-season band, value for value."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_prem_odds_probe",
                                                  ROOT / "tools" / "_prem_odds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.BUST_AVG_WAR * mod.TARGET_SEASONS == ed.BUST2_MLB_SUM_WAR
    for v in (-5.0, -0.001, 0.0, 0.5, 2.9, 2.999, 2.9999999, 3.0, 3.0000001, 3.1, 12.0, 40.0):
        assert ed.served_bust_event(v) == mod.bust_label(v), v


def test_union_on_fixture_rows():
    rows = [_deb("a", -1.5), _deb("b", 0.0), _deb("c", 2.999), _deb("d", 3.0),
            _deb("e", 3.001), _deb("f", 25.0), _never("g"), _never("h")]
    assert all(ed.is_resolved_row(r) for r in rows)
    assert all(_union_holds(r) for r in rows)
    cats = [ed.bust2_category(r) for r in rows]
    assert cats == ["BUST-MLB", "BUST-MLB", "BUST-MLB", "NON-BUST", "NON-BUST",
                    "NON-BUST", "BUST-NEVER", "BUST-NEVER"]


def test_unresolved_rows_are_outside_the_invariant():
    """A censored debuted row and a CENSORED-NEVER row carry no resolved event; they
    are not read, and the classifier says so rather than guessing."""
    rows = [_deb("x", 1.0, censored=True), _never("y", recent=True)]
    assert not any(ed.is_resolved_row(r) for r in rows)
    assert [ed.bust2_category(r) for r in rows] == ["UNRESOLVED-MLB", "CENSORED-NEVER"]


def test_a_never_row_with_a_nonzero_label_breaks_the_union():
    """What the live part would catch: a never-MLB row carrying WAR (a bust-loop guard
    miss) is BUST-NEVER by marker and not a bust by the served event."""
    bad = dict(_never("z"), target_resolved=4.0)
    assert not _union_holds(bad)


# ---------------------------------------------------------------------------
# the live part: the current matrices, read-only, no statistic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("side", ("hit", "pit"))
def test_union_live_on_the_current_matrices(side):
    p = ed.matrix_path(side)
    if not p.exists():
        pytest.skip(f"{p.name} is not on disk (CI); the live part needs the built matrix")
    rows = json.loads(p.read_text(encoding="utf-8"))
    resolved = [r for r in rows if ed.is_resolved_row(r)]
    assert resolved, f"{p.name} carries no resolved row"
    broken = [r["player_key"] for r in resolved if not _union_holds(r)]
    counts = {}
    for r in resolved:
        c = ed.bust2_category(r)
        counts[c] = counts.get(c, 0) + 1
    print(f"\nBUST2 union live [{side}]: rows {len(rows)}, resolved {len(resolved)}, "
          f"by category {counts}, union breaks {len(broken)}")
    assert not broken, (f"BUST2 union invariant fails on {len(broken)} {side} rows: "
                        f"{broken[:10]}")
