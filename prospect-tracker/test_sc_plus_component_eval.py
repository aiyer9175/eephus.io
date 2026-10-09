# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SC_PLUS_EVAL_REPAIR (2026-10-08): tools/sc_plus_component_eval.py raised
"composite parity broken: 3537 mismatches" before writing because
arkmetric_forward_eval.sc_analog_index started dividing the composite by the
pool's own composite sd in a953ddc0 (2026-08-07) and the tool's copy of the
z math kept 100 + 10z. These tests pin the parity on a synthetic fixture
(no cache, no network) and the served artifact's schema."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

import pytest

import arkmetric_forward_eval as afe
from tools import sc_plus_component_eval as sce

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "data" / "sc_plus_component_eval.json"


def _fixture_rows(side: str, n: int = 60) -> list[dict]:
    """Deterministic Savant-shaped rows: n AAA players plus three that must
    be dropped (not AAA, under the PA floor, a missing component)."""
    rows = []
    for i in range(n):
        rows.append({
            "player_id": str(100000 + i),
            "pa": str(150 + (i * 7) % 300),
            "launch_speed": f"{86 + (i * 13) % 9 + 0.1 * (i % 5):.1f}",
            "hardhit_percent": f"{30 + (i * 11) % 20:.1f}",
            "barrels_per_bbe_percent": f"{4 + (i * 5) % 9 + 0.3 * (i % 3):.1f}",
            "swing_miss_percent": f"{18 + (i * 17) % 15:.1f}",
            "xwoba": f"{0.290 + 0.004 * ((i * 3) % 20):.3f}",
            "k_percent": f"{15 + (i * 7) % 16:.1f}",
            "bb_percent": "" if i % 9 == 0 else f"{6 + (i * 5) % 8:.1f}",
        })
    rows.append(dict(rows[0], player_id="999001"))          # not AAA
    rows.append(dict(rows[1], player_id="100001", pa="40"))  # duplicate id, under floor
    rows.append(dict(rows[2], player_id="999002", hardhit_percent=""))
    return rows


@pytest.fixture
def synthetic_pool(monkeypatch):
    aaa = frozenset(100000 + i for i in range(60)) | {999002}
    monkeypatch.setattr(afe, "_aaa_mlbams", lambda season: aaa)
    monkeypatch.setattr(afe, "savant_rows",
                        lambda season, side, fetch=True: _fixture_rows(side))


def test_composite_parity_holds_on_the_fixture(synthetic_pool):
    assert sce.assert_parity() == 0
    for side in ("batter", "pitcher"):
        ref = afe.sc_analog_index(2024, side)
        mine = sce.component_z_table(2024, side)
        assert set(ref) == set(mine) and len(mine) == 60
        assert all(mine[k]["sc_plus_analog"] == v for k, v in ref.items())


def test_composite_is_ten_points_per_pool_sigma(synthetic_pool):
    """The defect this repair closes: the unscaled 100 + 10z reads well under
    10 points per sigma because averaging correlated z-scores shrinks the
    variance. After the repair the pool composite sd is 10 (to rounding)."""
    for side in ("batter", "pitcher"):
        tab = sce.component_z_table(2024, side)
        sd = statistics.pstdev([v["sc_plus_analog"] for v in tab.values()])
        assert abs(sd - 10.0) < 0.05, (side, sd)
        unscaled = [100 + 10 * sce._mean([v["z"][c] for c in sce.CORE])
                    for v in tab.values()]
        assert statistics.pstdev(unscaled) < 9.5


def test_parity_check_catches_a_divergent_scale(synthetic_pool, monkeypatch):
    real = sce.component_z_table

    def unscaled(season, side):
        out = real(season, side)
        for v in out.values():
            v["sc_plus_analog"] = round(
                100 + 10 * sce._mean([v["z"][c] for c in sce.CORE]), 1)
        return out

    monkeypatch.setattr(sce, "component_z_table", unscaled)
    with pytest.raises(AssertionError, match="composite parity broken"):
        sce.assert_parity()


def test_artifact_schema():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for key in ("generated_at", "tool", "method", "pools", "cohort_n",
                "per_component", "component_read", "blend_check", "findings",
                "recommendation", "caveats"):
        assert key in d, key
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["generated_at"])
    assert d["tool"] == "tools/sc_plus_component_eval.py"
    assert set(d["pools"]) == {str(s) for s in sce.SEASONS}
    comps = sce.CORE + list(sce.EXTRAS) + ["composite"]
    for side, rate in (("hitters", "vs_first_mlb_ops"),
                       ("pitchers", "vs_first_mlb_era_inv")):
        for outcome in (rate, "vs_war_2y"):
            tbl = d["per_component"][side][outcome]
            assert set(tbl) == set(comps)
            for c in comps:
                assert set(tbl[c]) == {"n", "r", "rho", "p_two_sided"}
        assert set(d["component_read"][side]) == set(sce.CORE)
        for label in ("rate_outcome", "war_outcome"):
            blk = d["blend_check"][label][side]
            assert {"folds", "pooled_oos", "pooled_oos_closed"} <= set(blk)
    rec = d["recommendation"]
    assert rec["decision"] in ("reweight-candidate (queued; composite unchanged)",
                               "demote", "keep composite as-is")
    assert "docs/archive/REVIEW_QUEUE.md" in rec["shipping_note"]
    assert rec["decision_basis"].startswith("pooled_oos_closed")


def test_artifact_prose_is_derived_from_its_own_tables():
    """Every comparison word in findings comes from the tables, so the served
    prose must equal what findings() derives from the served numbers."""
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert d["findings"] == sce.findings(d["per_component"], d["blend_check"])
    assert d["recommendation"] == sce.recommendation(d["per_component"],
                                                     d["blend_check"])
    text = json.dumps(d, ensure_ascii=False)
    assert chr(0x2014) not in text and chr(0x2013) not in text
