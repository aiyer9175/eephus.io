# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DEM+ confirmatory holdout mode (DEM_PLUS_GATE.md section 7): X-D1's
code path on the 2025 to 2026 pairs alone, reported beside the verdict and
never merged into it. Fixtures carry None values so the reporting path is
exercised on the shapes a real season produces."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import dem_plus_lab as L  # noqa: E402
import plus_lab_harness as plh  # noqa: E402


def _season(seed: int, n: int = 60, *, shift: float = 0.0) -> dict:
    rng = random.Random(seed)
    out = {}
    for mid in range(1, n + 1):
        skill = rng.gauss(0.0, 4.0)
        rate = skill + rng.gauss(0.0, 3.0) + shift
        inn = rng.choice([150.0, 350.0, 700.0, 1100.0])
        out[mid] = {"dem_plus_raw": 100.0 + 2.5 * skill, "dem_plus": int(100 + 2.5 * skill),
                    "rate": rate, "inn": inn,
                    "fld_pct": None if mid % 17 == 0 else 0.98 + 0.001 * skill,
                    "prim": "SS", "name": f"p{mid}", "share": 1.0, "c_share": 0.0,
                    "pinn": inn}
    return out


def _by_season():
    # the same skill draw in both seasons so the forward rho is positive
    a = _season(1)
    b = _season(1, shift=0.5)
    for mid in b:
        b[mid]["rate"] = a[mid]["dem_plus_raw"] / 2.5 - 40.0 + random.Random(mid).gauss(0, 3)
    return {2025: a, 2026: b}


def test_holdout_reads_only_the_2025_to_2026_pairs_under_the_override(monkeypatch):
    monkeypatch.setenv(plh.SEASON_COMPLETE_ASOF_ENV, "2026:2026-10-01")
    plh._OVERRIDE_LOGGED.clear()
    block = L.holdout_block(_by_season())
    assert block["seasons"] == [2025]
    assert block["status"] == "SCORED"
    assert block["n_pairs"] >= 30
    assert block["n_partial_outcome_pairs_dropped"] == 0
    assert block["reported_beside_the_verdict"] is True
    assert block["merged_into_the_verdict"] is False
    assert block["season_complete_override"]["seasons"] == {"2026": "2026-10-01"}
    for k in ("gap_ci_vs_fld_pct", "gap_ci_vs_innings", "gap_ci_vs_raw_rate"):
        assert set(block[k]) >= {"mean", "lo95", "hi95"}
    assert set(block["clauses_v1"]) == {"beats_fld_pct", "beats_innings",
                                        "not_worse_than_raw", "all"}
    assert isinstance(block["twin"]["fails_as_required"], bool)
    json.dumps(block)  # serializable with every None a fixture carries


def test_without_the_override_the_2026_outcome_is_dropped_before_nov_15(monkeypatch):
    monkeypatch.delenv(plh.SEASON_COMPLETE_ASOF_ENV, raising=False)
    from datetime import date
    # the convention as read on 2026-10-14: season 2026 is not past Nov 15
    monkeypatch.setattr(plh, "season_complete",
                        lambda y, today=None: date(2026, 10, 14) >= date(int(y), 11, 15))
    block = L.holdout_block(_by_season())
    assert block["status"] == "NOT_SCORED"
    assert block["n_pairs"] == 0
    assert block["n_partial_outcome_pairs_dropped"] > 0


def test_the_holdout_write_leaves_every_other_key_of_the_artifact_alone(monkeypatch, tmp_path):
    monkeypatch.setenv(plh.SEASON_COMPLETE_ASOF_ENV, "2026:2026-10-01")
    plh._OVERRIDE_LOGGED.clear()
    eval_path = tmp_path / "dem_plus_eval.json"
    before = {"generated_at": "2026-09-11", "experiment": "X-D1",
              "verdict": {"status": "validated", "summary": "fixture"},
              "gate": {"pass": True}}
    eval_path.write_text(json.dumps(before, indent=1) + "\n", encoding="utf-8")
    monkeypatch.setattr(L, "EVAL", eval_path)
    monkeypatch.setattr(L, "ROOT", tmp_path)
    bs = _by_season()
    monkeypatch.setattr(L, "load_season", lambda y: bs.get(y, {}))
    block = L.run_holdout(write=True)
    after = json.loads(eval_path.read_text(encoding="utf-8"))
    assert after[L.HOLDOUT_KEY]["n_pairs"] == block["n_pairs"]
    for k, v in before.items():
        assert after[k] == v, f"{k} moved; the holdout is reported beside the verdict"
    assert after["verdict"]["status"] == "validated"
