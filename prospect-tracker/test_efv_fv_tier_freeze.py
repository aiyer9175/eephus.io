# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FV-tier freeze (lane D E3-Q3 = A, 2026-10-02; docs/efv-v2/EFV_V2_GATE.md s8.3;
EFV3_PLAN.md s9 unifier note; landed with EFV3_D2).

Three pre-existing surfaces computed a realized-WAR statistic by consensus-FV tier
every night (source_backtest._tier_table, the efv_scoreboard by_fv_tier / t45 / wm
blocks, the source_cohort_accuracy by_fv_tier block). Until the anchor look record
exists (docs/PROSPECT_ANCHOR_GATE.md section 18) they serve the values frozen in
data/efv_fv_tier_frozen.json with the chip "frozen pending the anchor look".

Pinned here:
1. the freeze is on, applies to the served data directory only, and lifts itself
   when section 18 of the anchor gate carries a dated look record;
2. the frozen block content equals the COMMITTED artifact (git HEAD) for the two
   tracked producers, and the on-disk artifact for the gitignored source_backtest;
3. each producer serves the frozen block, never a fresh one, while the freeze is on;
4. the chip copy carries no em-dash and no banned word.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import source_backtest as SB
import source_cohort_accuracy as SCA

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import copy_lint  # noqa: E402

FROZEN = ROOT / "data" / "efv_fv_tier_frozen.json"
TRACKED = {"efv_scoreboard": "data/xfv_scoreboard_eval.json",
           "source_cohort_accuracy": "data/source_cohort_accuracy.json"}

pytestmark = pytest.mark.skipif(
    not SB.FV_TIER_FREEZE,
    reason="the owner lifted the freeze (source_backtest.FV_TIER_FREEZE = False)")


def _frozen() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))


def _head(rel: str):
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:./{rel}"],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout.decode("utf-8"))


# ---------------------------------------------------------------------------
# 1. the switch
# ---------------------------------------------------------------------------

def test_the_freeze_is_on_for_the_served_directory_only(tmp_path):
    assert SB.FV_TIER_FREEZE is True
    assert SB.fv_tier_frozen() is (not SB.anchor_look_record_exists())
    assert SB.fv_tier_frozen(SB.DATA_DIR) is SB.fv_tier_frozen()
    assert SB.fv_tier_frozen(tmp_path) is False, "a fixture run computes as before"


def test_anchor_look_record_detection_on_fixture_texts():
    empty = ("# gate\n\n## 17. Before\n\ntext\n\n## 18. Results\n\n"
             "EMPTY AT REGISTRATION (2026-09-23).\n\n## 19. After\n")
    dated = empty.replace("EMPTY AT REGISTRATION (2026-09-23).",
                          "EMPTY AT REGISTRATION (2026-09-23).\n\n2026-12-04: look taken.")
    cleared = empty.replace("EMPTY AT REGISTRATION (2026-09-23).", "The look record follows.")
    assert SB.anchor_look_record_exists(empty) is False
    assert SB.anchor_look_record_exists(dated) is True
    assert SB.anchor_look_record_exists(cleared) is True
    assert SB.anchor_look_record_exists("# gate\n\n## 1. Nothing here\n") is False
    assert SB.anchor_look_record_exists("") is False


def test_the_anchor_gate_document_still_carries_an_empty_section_18_today():
    """Today's state, read off the document the switch reads. When this flips the
    freeze lifts itself; this test then records that the look record exists."""
    text = (ROOT / SB.ANCHOR_GATE_DOC).read_text(encoding="utf-8")
    assert re.search(r"^##\s+18\.\s", text, re.M), "section 18 of the anchor gate is gone"
    exists = SB.anchor_look_record_exists(text)
    assert SB.fv_tier_frozen() is (not exists)


# ---------------------------------------------------------------------------
# 2. frozen == committed
# ---------------------------------------------------------------------------

def test_frozen_file_exists_and_names_its_sources():
    fz = _frozen()
    assert fz["chip"] == SB.FV_TIER_FREEZE_CHIP == "frozen pending the anchor look"
    assert set(fz["sources"]) == {"source_backtest", "efv_scoreboard", "source_cohort_accuracy"}
    for k, src in fz["sources"].items():
        assert src["generated_at"], k
        assert len(src["sha256"]) == 64, k
    assert fz["sources"]["efv_scoreboard"]["equals_git_head"] is True
    assert fz["sources"]["source_cohort_accuracy"]["equals_git_head"] is True
    # data/source_backtest.json is gitignored: the frozen copy IS its committed record.
    assert fz["sources"]["source_backtest"]["tracked"] is False


def test_frozen_scoreboard_blocks_equal_the_committed_artifact():
    head = _head(TRACKED["efv_scoreboard"])
    if head is None:
        pytest.skip("data/xfv_scoreboard_eval.json is not at git HEAD")
    fz = _frozen()["efv_scoreboard"]
    for side, blk in (head.get("sides") or {}).items():
        assert fz[side]["by_fv_tier"] == (blk.get("by_fv_tier") or {}), side
        assert fz[side]["t45"] == blk.get("t45"), side
        assert fz[side]["wm"] == blk.get("wm"), side


def test_frozen_cohort_accuracy_block_equals_the_committed_artifact():
    head = _head(TRACKED["source_cohort_accuracy"])
    if head is None:
        pytest.skip("data/source_cohort_accuracy.json is not at git HEAD")
    fz = _frozen()["source_cohort_accuracy"]
    acc = head["accuracy"]
    assert fz["by_fv_tier"] == acc["by_fv_tier"]
    assert fz["by_fv_tier_range_restriction_warning"] == acc["by_fv_tier_range_restriction_warning"]


def test_frozen_source_backtest_tiers_equal_the_served_artifact():
    """source_backtest.json is gitignored (nightly on the box). The frozen copy was
    taken from the artifact on disk on 2026-10-02 and every later served run copies
    it back, so the two agree whichever one is on disk."""
    p = ROOT / "data" / "source_backtest.json"
    if not p.exists():
        pytest.skip("data/source_backtest.json not built")
    sb = json.loads(p.read_text(encoding="utf-8"))
    fz = _frozen()["source_backtest"]
    for rater, c in (sb.get("cohorts") or {}).items():
        assert fz.get(rater) == (c.get("tiers") or []), rater


# ---------------------------------------------------------------------------
# 3. the producers serve the frozen block
# ---------------------------------------------------------------------------

def test_frozen_block_accessors_return_copies_with_the_chip():
    a = SB.frozen_fv_tier_block("efv_scoreboard")
    b = SB.frozen_fv_tier_block("efv_scoreboard")
    assert a == b and a is not b, "a deep copy each time, never the cache"
    assert SB.frozen_fv_tier_block("not_a_producer") is None
    chip = SB.fv_tier_freeze_chip("source_backtest")
    assert chip["chip"] == SB.FV_TIER_FREEZE_CHIP
    assert chip["file"] == "data/efv_fv_tier_frozen.json"
    assert "FV_TIER_FREEZE = False" in chip["owner_line"]
    assert "section 18" in chip["until"]


def test_source_backtest_routes_every_tier_table_through_the_freeze():
    """Inside run_source_backtest no cohort reads _tier_table directly: every tier
    block goes through the _tiers_for closure that serves the frozen copy."""
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    body = src.split("def run_source_backtest(", 1)[1]
    body = body.split("\ndef ", 1)[0]
    direct = [ln for ln in body.splitlines()
              if "_tier_table(" in ln and "def _tiers_for" not in ln
              and "return _tier_table(rows)" not in ln]
    assert direct == [], direct
    assert body.count('"tiers": _tiers_for(') == 2
    assert 'result["fv_tier_freeze"] = _tier_chip' in body


def test_cohort_accuracy_block_serves_the_frozen_partition_under_the_freeze():
    """_accuracy_block with the frozen block: by_fv_tier and its warning are the
    frozen ones, the chip sits beside them, and the partitions after it keep their
    cell indices (the seeds) because idx advances by the frozen cell count."""
    frozen = SB.frozen_fv_tier_block("source_cohort_accuracy")
    assert frozen and frozen["by_fv_tier"]
    rng_rows = []
    import random
    rnd = random.Random(7)
    for i in range(240):
        war = max(0.0, rnd.gauss(2, 3))
        fg = 40 + 5 * (i % 5) + rnd.gauss(0, 2)
        mp = 40 + 5 * ((i + 1) % 5) + rnd.gauss(0, 2)
        rng_rows.append({"key": f"k{i}", "side": "bat" if i % 2 else "arm",
                         "fg": fg, "mp": mp, "cons": (fg + mp) / 2.0, "war": war,
                         "contributor": war >= 3.0,
                         "acquisition": ["draft_hs", "draft_college", "international"][i % 3],
                         "archetype": ["hs_bat", "college_arm", "intl_bat"][i % 3],
                         "pos_group": ["IF", "OF", "C"][i % 3],
                         "age_at_grading": 19 + (i % 7), "year": 2017 + (i % 4),
                         "debuted": True})
    fresh = SCA._accuracy_block([dict(r) for r in rng_rows])
    under = SCA._accuracy_block([dict(r) for r in rng_rows], frozen)
    assert under["by_fv_tier"] == frozen["by_fv_tier"]
    assert under["by_fv_tier_range_restriction_warning"] == frozen["by_fv_tier_range_restriction_warning"]
    assert under["by_fv_tier_freeze"]["chip"] == SB.FV_TIER_FREEZE_CHIP
    assert "by_fv_tier_freeze" not in fresh
    assert under["by_fv_tier"] != fresh["by_fv_tier"] or len(fresh["by_fv_tier"]) == 0


def test_scoreboard_side_block_reads_the_frozen_tier_cells(monkeypatch):
    import efv_scoreboard as ES
    import source_backtest as SBT
    fz = SBT.frozen_fv_tier_block("efv_scoreboard")
    assert fz and set(fz) >= {"hit", "pit"}
    monkeypatch.setattr(SBT, "FV_TIER_FREEZE", True)
    monkeypatch.setattr(SBT, "anchor_look_record_exists", lambda text=None: False)
    assert SBT.fv_tier_frozen() is True
    # the guard in _side_block: under the freeze the three blocks are copies
    src = (ROOT / "tools" / "efv_scoreboard.py").read_text(encoding="utf-8")
    assert "if SBT.fv_tier_frozen():" in src
    assert 'block["fv_tier_freeze"] = SBT.fv_tier_freeze_chip("efv_scoreboard")' in src
    assert ES is not None


# ---------------------------------------------------------------------------
# 4. copy
# ---------------------------------------------------------------------------

def test_chip_copy_is_clean():
    for producer in ("source_backtest", "efv_scoreboard", "source_cohort_accuracy"):
        chip = SB.fv_tier_freeze_chip(producer)
        for v in chip.values():
            if isinstance(v, str):
                assert "—" not in v and "–" not in v, v
                assert not copy_lint.BAN_RE.search(v), v
    src = (ROOT / "tools" / "efv_fv_tier_freeze.py").read_text(encoding="utf-8")
    assert "—" not in src and "–" not in src
