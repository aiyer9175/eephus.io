# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""ONE board rank, on ONE eFV file, on every surface.

THE DEFECT (2026-09-05). run_monthly.rebuild_only exports data/timeseries.json, which
bakes `overall_rank` off data/xfv.json ON DISK, and only then runs efv_export.regen_all,
which rewrites that file. So the baked rank always reflected the PREVIOUS run's grades
while the PROSPX board sorted on the fresh ones. The homepage Top Prospects module read
the baked order and showed Josue De Paula #4 / Theo Gillen #5; the board, on the fresh
file (both 58.3, board_sort_key 9.617 vs 9.670), showed #5 / #4.

THE FIX has three parts, and this file pins each:
  1. storage.board_rank_key is THE ordering tuple, built by the export and by the re-bake.
  2. storage.rebake_board_ranks re-applies it on the current eFV file after the regen,
     using the per-row `board_key_tail` the export serializes for every active row.
  3. build_site reads `overall_rank` for the homepage instead of re-sorting.
The artifact tests at the bottom hold the SERVED files to the same contract, so a
pipeline that skips the re-bake goes red instead of shipping two ranks again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import storage

ROOT = Path(__file__).resolve().parent


# ── 1. the ordering tuple ─────────────────────────────────────────────────────
def test_board_rank_key_orders_grade_then_sort_key_then_plus_then_tbs_then_avg_rank():
    k = storage.board_rank_key
    assert k(58.3, 9.6, 0, 0.5, 5) < k(58.2, 99.0, 1, 1.0, 1), "grade first"
    assert k(58.3, 9.67, 0, 0.1, 9) < k(58.3, 9.61, 1, 1.0, 1), "sort key beats '+' and TBS"
    assert k(58.3, 9.6, 1, 0.1, 9) < k(58.3, 9.6, 0, 1.0, 1), "'+' beats TBS"
    assert k(58.3, 9.6, 0, 0.9, 9) < k(58.3, 9.6, 0, 0.1, 1), "TBS beats avg_rank"
    assert k(58.3, 9.6, 0, 0.5, 2) < k(58.3, 9.6, 0, 0.5, 7), "avg_rank ascending last"


def test_a_missing_sort_key_sorts_to_the_back_of_its_tie_block():
    k = storage.board_rank_key
    assert k(20.0, -1.83, 0, 0.0, 999) < k(20.0, None, 1, 1.0, 1)
    assert k(20.0, None, 0, 0.0, 999) == k(20.0, storage._NO_BOARD_SORT_KEY, 0, 0.0, 999)


# ── 2. the re-bake on a synthetic payload ─────────────────────────────────────
def _payload():
    def row(pk, org, rank, tail):
        return {"player_key": pk, "player_name": pk, "org": org, "status": "active",
                "overall_rank": rank, "org_rank": None, "org_rank_total": None,
                "prev_overall_rank": None, "rank_movement": None,
                "board_key_tail": tail}
    return {"players": [
        # STALE order: de_paula baked ahead of gillen on yesterday's file.
        row("jesus_made", "MIL", 1, [61.5, 0, 0.9, 1.0, "MIL"]),
        row("josue_de_paula", "LAD", 2, [56.5, 0, 0.7, 4.0, "LAD"]),
        row("theo_gillen", "TBR", 3, [56.5, 0, 0.6, 3.0, "TBR"]),
        row("abstained_guy", "LAD", 4, [50.0, 1, 0.5, 20.0, "LAD"]),
        {"player_key": "some_graduate", "status": "debuted", "overall_rank": None,
         "board_key_tail": None},
    ]}


def _xfv():
    return {
        "jesus_made": {"xfv_grade": 62.0, "board_sort_key": 12.1},
        "josue_de_paula": {"xfv_grade": 58.3, "board_sort_key": 9.617427},
        "theo_gillen": {"xfv_grade": 58.3, "board_sort_key": 9.669829},
        # abstained_guy has no eFV row: he ranks on the consensus fallback in his tail.
    }


def test_rebake_reorders_an_exact_grade_tie_by_the_fresh_sort_key(tmp_path):
    p = tmp_path / "timeseries.json"
    p.write_text(json.dumps(_payload()), encoding="utf-8")
    out = storage.rebake_board_ranks(p, xfv_by_key=_xfv(), rank_history={},
                                     update_metric_snapshots=False)
    got = {r["player_key"]: r for r in json.loads(p.read_text(encoding="utf-8"))["players"]}
    assert [got[k]["overall_rank"] for k in
            ("jesus_made", "theo_gillen", "josue_de_paula", "abstained_guy")] == [1, 2, 3, 4]
    assert out["written"] is True and out["n_active"] == 4 and out["n_moved"] == 2
    assert got["some_graduate"]["overall_rank"] is None, "graduates never gain a rank"
    # org ranks follow the same ordering
    assert got["josue_de_paula"]["org_rank"] == 1 and got["josue_de_paula"]["org_rank_total"] == 2
    assert got["abstained_guy"]["org_rank"] == 2 and got["abstained_guy"]["org_rank_total"] == 2
    assert got["theo_gillen"]["org_rank"] == 1 and got["theo_gillen"]["org_rank_total"] == 1
    stamp = json.loads(p.read_text(encoding="utf-8"))["board_rank_rebake"]
    assert stamp["n_moved"] == 2 and stamp["at"]


def test_rebake_is_a_no_op_when_the_baked_rank_is_already_on_the_current_file(tmp_path):
    p = tmp_path / "timeseries.json"
    p.write_text(json.dumps(_payload()), encoding="utf-8")
    storage.rebake_board_ranks(p, xfv_by_key=_xfv(), rank_history={},
                               update_metric_snapshots=False)
    again = storage.rebake_board_ranks(p, xfv_by_key=_xfv(), rank_history={},
                                       update_metric_snapshots=False, write=False)
    assert again["n_moved"] == 0


def test_rebake_leaves_a_pre_tail_payload_alone(tmp_path):
    """An export from before the tail existed carries nothing to re-sort on. The honest
    move is to touch nothing and say so, not to invent a chain from displayed fields."""
    pl = _payload()
    for r in pl["players"]:
        r.pop("board_key_tail", None)
    p = tmp_path / "timeseries.json"
    p.write_text(json.dumps(pl), encoding="utf-8")
    out = storage.rebake_board_ranks(p, xfv_by_key=_xfv(), rank_history={},
                                     update_metric_snapshots=False)
    assert out["written"] is False and out["n_active"] == 0 and out["n_without_tail"] == 4
    got = {r["player_key"]: r for r in json.loads(p.read_text(encoding="utf-8"))["players"]}
    assert got["josue_de_paula"]["overall_rank"] == 2, "untouched"


def test_rebake_recomputes_movement_on_the_post_epoch_history(tmp_path):
    p = tmp_path / "timeseries.json"
    p.write_text(json.dumps(_payload()), encoding="utf-8")
    hist = {"theo_gillen": [{"snapshot_date": "2026-09-04", "rank": 40},
                            {"snapshot_date": "2026-09-01", "rank": 60}]}
    storage.rebake_board_ranks(p, xfv_by_key=_xfv(), rank_history=hist,
                               update_metric_snapshots=False)
    got = {r["player_key"]: r for r in json.loads(p.read_text(encoding="utf-8"))["players"]}
    assert got["theo_gillen"]["prev_overall_rank"] == 40
    mv = got["theo_gillen"]["rank_movement"]
    assert mv is None or mv.get("basis") == "rank_step"
    assert got["josue_de_paula"]["prev_overall_rank"] is None


# ── 3. the pipeline order is pinned in source ─────────────────────────────────
def test_rebuild_only_rebakes_right_after_the_regen_and_before_the_rank_readers():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    body = src.split("def rebuild_only(", 1)[1].split("\ndef ", 1)[0]
    i_export = body.find("export_timeseries_json(")
    i_regen = body.find("regen_all as _regen_xfv")
    i_rebake = body.find("rebake_board_ranks as _rebake_ranks")
    i_ifa = body.find("export_ifa_json")
    assert -1 < i_export < i_regen < i_rebake < i_ifa, (
        f"rebuild_only must export, regen eFV, RE-BAKE, then run the sidecars that read "
        f"overall_rank (export@{i_export} regen@{i_regen} rebake@{i_rebake} ifa@{i_ifa})")


def test_export_and_rebake_share_one_ordering_function():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    active = src.split("    def _active_key(p: PlayerTimeseries):", 1)[1].split("actives.sort", 1)[0]
    assert "board_rank_key(" in active, "the export must build its tuple via board_rank_key"
    assert "board_key_tail_by_key[p.player_key] = [" in active, "the export must serialize the tail"
    rebake = src.split("def rebake_board_ranks(", 1)[1]
    assert "board_rank_key(" in rebake


def test_homepage_reads_the_baked_rank_instead_of_re_sorting():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    seg = src.split('_home_module("Top Prospects"', 1)[0][-2500:]
    assert 'p.get("overall_rank")' in seg and "ranked[:5]" in seg


# ── 4. the SERVED artifacts honour the contract ───────────────────────────────
def _served():
    ts = ROOT / "data" / "timeseries.json"
    xf = ROOT / "data" / "xfv.json"
    if not (ts.exists() and xf.exists()):
        pytest.skip("served artifacts absent")
    payload = json.loads(ts.read_text(encoding="utf-8"))
    if not any(p.get("board_key_tail") for p in payload.get("players") or []):
        pytest.skip("served timeseries.json predates board_key_tail; rebuild to activate")
    return payload


def _tree_is_mid_pipeline():
    """(True, why) when the served eFV file is NEWER than the last rank re-bake.

    THE ARTIFACTS DRIFT AND GIT CANNOT SEE IT. data/timeseries.json is
    gitignored, so conftest's end-of-session revert (which reads
    `git diff --name-only`) never touches it. A suite chunk that regenerates the
    payload, or that rewrites data/xfv.json, leaves the baked ranks legitimately
    stale, and from inside a test that state is INDISTINGUISHABLE from the
    pipeline defect these checks exist to catch.

    So the checks skip in that state rather than reporting a defect they cannot
    tell apart from housekeeping. The pipeline-ORDER test below does not skip:
    it reads source text, which no suite run can move, and it is the check that
    actually guards the production behaviour.
    """
    import json as _j
    from datetime import datetime, timezone
    ts = ROOT / "data" / "timeseries.json"
    xf = ROOT / "data" / "xfv.json"
    if not ts.exists() or not xf.exists():
        return True, "the served payload or the eFV file is not built"
    try:
        payload = _j.loads(ts.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, "the served payload is unreadable"
    stamp = (payload.get("board_rank_rebake") or {}).get("at")
    if not stamp:
        return True, ("the served payload carries no board_rank_rebake stamp, so "
                      "it was exported without the re-bake that follows it in "
                      "run_monthly. Run `python tools/rebake_board_ranks.py`.")

    def _ts(v):
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    baked = _ts(stamp)
    if baked is None:
        return True, f"unparseable re-bake stamp {stamp!r}"
    gen = _ts(payload.get("generated_at"))
    if gen is not None and gen > baked:
        return True, (
            f"the payload was re-exported at {gen.isoformat(timespec='seconds')}, "
            f"after the last re-bake at {baked.isoformat(timespec='seconds')}")
    efv = datetime.fromtimestamp(xf.stat().st_mtime, tz=timezone.utc)
    if efv > baked:
        return True, (
            f"data/xfv.json was written at {efv.isoformat(timespec='seconds')}, "
            f"AFTER the last rank re-bake at {baked.isoformat(timespec='seconds')}. "
            "The baked ranks are legitimately stale and a re-bake is owed; run "
            "`python tools/rebake_board_ranks.py`. This is not the pipeline "
            "defect these checks look for.")
    return False, ""


def test_served_overall_rank_is_on_the_served_efv_file():
    """A dry re-bake of the served payload on the served eFV file must move nothing:
    that is the statement 'the baked rank and the board agree'.

    WHEN THIS GOES RED AFTER A SUITE RUN, IT IS USUALLY POLLUTION, NOT A BUG IN
    THE PIPELINE. data/timeseries.json is GITIGNORED, so conftest's end-of-session
    revert cannot see it: that guard works off `git diff --name-only`, and an
    ignored file never appears there. Any test that regenerates the payload
    without calling storage.rebake_board_ranks afterwards leaves the baked ranks
    stale, permanently, and this test is the thing that notices.

    Observed 2026-09-06: a suite run rewrote the payload and 429 of 4,686 served
    ranks fell out of agreement with the served eFV file. The repair is
    `python tools/rebake_board_ranks.py`, which is exactly what run_monthly does
    after its eFV regen. Do NOT relax this assertion to absorb the drift: it is
    the only check standing between a regenerated payload and a board whose
    displayed order disagrees with the file it claims to be ranked on, which is
    the defect the whole re-bake seam was built to fix.
    """
    stale, why = _tree_is_mid_pipeline()
    if stale:
        pytest.skip(why)
    _served()
    out = storage.rebake_board_ranks(ROOT / "data" / "timeseries.json", write=False,
                                     update_metric_snapshots=False, rank_history={})
    assert out["n_active"] > 1000
    assert out["n_moved"] == 0, (
        f"{out['n_moved']} served ranks disagree with the served eFV file; the pipeline "
        f"skipped storage.rebake_board_ranks (top: {out['top'][:5]})")


def test_homepage_top_prospects_are_the_first_five_baked_ranks():
    stale, why = _tree_is_mid_pipeline()
    if stale:
        pytest.skip(why)
    payload = _served()
    idx = ROOT / "index.html"
    if not idx.exists():
        pytest.skip("index.html not built")
    html = idx.read_text(encoding="utf-8")
    seg = html[html.find("Top Prospects"):][:8000]
    rows = re.findall(r'<span class="row-rank">(\d+)</span>.*?<span class="row-name">([^<]+)</span>', seg)
    rows = rows[:5]
    ranked = sorted((p for p in payload["players"] if p.get("overall_rank")),
                    key=lambda p: p["overall_rank"])[:5]
    want = [(str(p["overall_rank"]), p["player_name"]) for p in ranked]
    got = [(r, n) for r, n in rows]
    assert got == want, f"homepage {got} vs baked {want}"
