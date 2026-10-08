# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The repaired MLBTR / Swartz join (docs/ARBITRATION_GATE.md section 14).

load_ledger keeps one entry per (key, class year), so the arbitration
TRACKER post overwrote the Swartz PROJECTION for nearly every settled
2024-2026 player and the History's MLBTR column was filled on 18, 16 and 17
rows for those years. The repaired join reads the projection kind only. The
coverage check below resolves names on its own, independently of the join it
checks, the way the census measured the gap.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

import arb_dataset as A

ROOT = Path(__file__).parent

PANEL = [{"mlbam": 1, "bbref": "abc01", "season": 2025},
         {"mlbam": 2, "bbref": "xyz01", "season": 2025}]


def test_a_tracker_entry_shadows_the_projection_only_in_the_frozen_join():
    proj = {"kind": "projection", "class_year": 2025, "bbref_id": "abc01",
            "projected_usd": 4_000_000}
    trk = {"kind": "tracker", "class_year": 2025, "bbref_id": "abc01",
           "settled_usd": 4_200_000}
    ledger = {"abc01": {2025: trk}}          # load_ledger's shape: last read wins
    frozen, _ = A.swartz_by_mlbam(PANEL, pool="frozen", ledger=ledger)
    assert frozen == {}
    repaired, census = A.swartz_by_mlbam(PANEL, pool="repaired", projections=[proj])
    assert repaired == {(1, 2025): 4_000_000.0}
    assert census["joined"] == 1 and census["collisions"] == 0


def test_collisions_and_missing_ids_are_counted_and_left_out():
    ents = [
        {"kind": "projection", "class_year": 2025, "bbref_id": "abc01", "projected_usd": 1e6},
        {"kind": "projection", "class_year": 2025, "mlbam": 1, "projected_usd": 2e6},
        {"kind": "projection", "class_year": 2025, "bbref_id": "xyz01", "projected_usd": 3e6},
        {"kind": "projection", "class_year": 2025, "mlbam": 2, "projected_usd": 3e6},
        {"kind": "projection", "class_year": 2025, "projected_usd": 9e6},
        {"kind": "projection", "class_year": 2025, "bbref_id": "nobody", "projected_usd": 9e6},
    ]
    out, census = A.swartz_by_mlbam(PANEL, pool="repaired", projections=ents)
    assert out == {(2, 2025): 3e6}, "a same-figure duplicate is not a collision"
    assert census["collisions"] == 1 and census["collision_keys"][0][:2] == [1, 2025]
    assert census["no_id"] == 1 and census["bbref_not_in_rows"] == 1
    with pytest.raises(ValueError):
        A.swartz_by_mlbam(PANEL, pool="other")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def test_the_history_carries_mlbtr_wherever_a_projection_exists():
    """Section 14c: per class year 2023-2026, history rows with an MLBTR
    figure over history rows whose player has a projection entry for that
    year (resolved here by name, independently of the join), at least 0.95."""
    lp = ROOT / "data" / "_labs" / "arb_ledger.json"
    hp = ROOT / "data" / "arb_history.json"
    if not lp.exists() or not hp.exists():
        pytest.skip("ledger or history absent")
    ents = json.loads(lp.read_text(encoding="utf-8"))["entries"]
    have = {(int(e["class_year"]), _norm(e.get("player_name")))
            for e in ents if e.get("kind") == "projection" and e.get("projected_usd")}
    rows = json.loads(hp.read_text(encoding="utf-8"))["rows"]
    den, num = Counter(), Counter()
    for r in rows:
        if (int(r[0]), _norm(r[2])) in have:
            den[r[0]] += 1
            num[r[0]] += 1 if r[7] else 0
    for y in (2023, 2024, 2025, 2026):
        if den[y] == 0:
            continue
        assert num[y] / den[y] >= 0.95, (y, num[y], den[y])


def test_the_eval_scores_both_pools_side_by_side():
    p = ROOT / "data" / "arbitration_eval.json"
    if not p.exists():
        pytest.skip("no eval artifact")
    ev = json.loads(p.read_text(encoding="utf-8"))
    a6, fz = ev["a6_swartz"], ev["a6_swartz_frozen_pool"]
    assert a6["pool"] == "repaired" and fz["pool"] == "frozen"
    assert a6["units"] == fz["units"] == "repaired"
    assert a6["n"] > fz["n"]
    assert a6["verdict"] == ("PASS" if a6["ours_mdape"] < a6["swartz_mdape"] else "NULL")
    assert a6["join_census"]["collisions"] == len(a6["join_census"]["collision_keys"])
