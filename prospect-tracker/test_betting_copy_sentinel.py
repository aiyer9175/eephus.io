# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Two guards from the 2026-08-19 batch.

1. THE BOTH-LEGS COPY STATE. When the evidence leg (section 7b ledger gate)
   closes a market the theory leg (dispersion exclusion) already bars, the
   payload must say so as ONE flag (`both_legs`) and the page must render the
   pre-decided copy with every number DERIVED from the payload, none
   hand-written. The flag is derived from the two legs beside it, so these
   tests hold it to the AND it summarizes.

2. THE NIGHTLY-GAP SENTINEL. The 2026-08-15 and 2026-08-17 nightlies missed
   silently: two vintage nights, a DFS slate and two days of schema-3 accrual
   are gone and cannot be backfilled. run_monthly._vintage_capture_gap reads
   the two per-date .cache/ archives on the next night that DOES run and
   files a named yellow/red ingest_health row with the missing dates listed.
   These tests fire it on the exact incident shape and hold it quiet when
   capture is current.

Offline: synthetic ledgers and tmp archives only. No network.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import betting_export as be
import betting_model as bm
import run_monthly as rm
from tools import betting_calibration as bc

ROOT = Path(__file__).resolve().parent
JS = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# synthetic ledgers (the test_betting_market_gate.py shape)
# ---------------------------------------------------------------------------
def _add_side(events: list, *, slate: str, game_pk: int, market: str,
              side: str, brier: float, point=None) -> None:
    cid = bc.cal_id(slate, game_pk, market, side, point)
    events.append({"cal_id": cid, "phase": bc.PHASE_OPEN, "written_at": "t",
                   "slate_date": slate, "game_pk": game_pk, "market": market,
                   "side": side, "point": point, "model_prob": 0.6})
    events.append({"cal_id": cid, "phase": bc.PHASE_SETTLED, "written_at": "t",
                   "result": "lost", "brier": brier, "settled_at": "t"})


def _ledger(tmp_path: Path, name: str, sides: list[tuple]) -> Path:
    p = tmp_path / name
    events: list[dict] = []
    for spec in sides:
        market, side, game_pk, brier = spec[:4]
        point = spec[4] if len(spec) > 4 else None
        _add_side(events, slate="2026-08-01", game_pk=game_pk, market=market,
                  side=side, brier=brier, point=point)
    bc.append(events, path=p)
    return p


def _worse(tmp_path: Path, market: str, name: str) -> Path:
    """120 canonical games at mean Brier 0.33: resolves worse than a coin."""
    side = bc.CANONICAL_SIDES[market]
    point = 8.5 if market in ("total", "runline") else None
    sides = [(market, side, i, 0.36 if i % 2 else 0.30, point)
             for i in range(120)]
    return _ledger(tmp_path, name, sides)


def _eval(cal: Path, state: Path, day: int) -> dict:
    return be.market_gate_evaluate(
        cal_path=cal, state_path=state,
        now=datetime(2026, 9, day, 4, 0, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# 1a. the both_legs flag on the served table
# ---------------------------------------------------------------------------
def test_both_legs_true_when_evidence_closes_a_dispersion_barred_market(tmp_path):
    """The total is barred by the theory leg while the dispersion correction
    is unserved; a ledger close on top of that must raise both_legs."""
    assert bm.SERVE_RUN_DISPERSION is False, (
        "the dispersion premise moved; re-read these expectations")
    cal = _worse(tmp_path, "total", "worse_total.jsonl")
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        t = _eval(cal, state, d)
    tot = t["markets"]["total"]
    assert tot["dispersion_leg"]["publishable"] is False
    assert tot["ledger_leg"]["status"] == "ledger_closed"
    assert tot["both_legs"] is True
    assert tot["publishable"] is False
    assert "both legs" in tot["reason"]


def test_both_legs_false_when_only_the_evidence_leg_bars(tmp_path):
    """Moneyline is never dispersion-barred, so even ledger-closed it is a
    one-leg exclusion. Flipping the AND to an OR dies here."""
    cal = _worse(tmp_path, "moneyline", "worse_ml.jsonl")
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        t = _eval(cal, state, d)
    ml = t["markets"]["moneyline"]
    assert ml["ledger_leg"]["status"] == "ledger_closed"
    assert ml["dispersion_leg"]["publishable"] is True
    assert ml["both_legs"] is False


def test_both_legs_false_when_only_the_theory_leg_bars(tmp_path):
    """Runline and total with OPEN ledger legs: dispersion-barred alone is
    not a both-legs state, and every market row carries the key."""
    cal = _ledger(tmp_path, "tiny.jsonl", [("moneyline", "home", 1, 0.36)])
    t = be.market_publishability(cal_path=cal,
                                 state_path=tmp_path / "none.json")
    for m, row in t["markets"].items():
        assert "both_legs" in row, f"{m} row lost the both_legs key"
        assert row["both_legs"] is False
    for m in ("runline", "total"):
        assert t["markets"][m]["dispersion_leg"]["publishable"] is False
        assert t["markets"][m]["ledger_leg"]["status"] == "open"


# ---------------------------------------------------------------------------
# 1b. the page renders the state and derives every number
# ---------------------------------------------------------------------------
def _js_fn(name: str) -> str:
    """One top-level function body out of betting.js, by its declaration.
    Ends at the function's own two-space close so neighbouring comment blocks
    (which legitimately carry numbers) never leak into the slice."""
    start = JS.index("function " + name)
    end = JS.index("\n  }\n", start)
    return JS[start:end]


def test_betting_js_renders_the_both_legs_copy_state():
    body = _js_fn("marketGateNotes")
    assert "watch-only for two independent reasons" in body
    assert "both_legs" in body
    assert "market_publishability" in body
    # rendered where a reader can see it: the watch tab AND the board, since
    # a market closed by both legs never reaches a slot card. Three matches:
    # the declaration plus the two render sites.
    assert JS.count("marketGateNotes()") >= 3


def test_the_copy_numbers_are_derived_not_hand_written():
    """The live statistics (t 1.767 on the total tonight, the 1.645 bar, the
    0.263 Brier) must reach the copy through the payload fields, never as
    literals: a hand-written number is the defect class three labs
    self-reported on 2026-08-18."""
    body = _js_fn("marketGateNotes")
    for lit in ("1.767", "1.645", "0.263", "100"):
        assert lit not in body, f"hand-written statistic {lit!r} in the copy"
    # the fields the numbers must come from instead
    for field in ("lg.t", "lg.brier", "lg.n_games", "pol.z", "pol.n_min"):
        assert field in body, f"the copy no longer reads {field}"


# ---------------------------------------------------------------------------
# 2. the nightly-gap sentinel
# ---------------------------------------------------------------------------
def _arch(tmp_path: Path, name: str, days: list[str]) -> Path:
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    for day in days:
        (d / f"{day}.json").write_text("{}", encoding="utf-8")
    return d


def test_sentinel_quiet_when_capture_is_current(tmp_path):
    v = _arch(tmp_path, "vint", ["2026-08-17", "2026-08-18"])
    f = _arch(tmp_path, "dfs", ["2026-08-18"])
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=f)
    assert out["ok"] is True
    assert out["severity"] == "ok"
    assert out["missing_vintage_dates"] == []
    assert "2026-08-18" in out["message"]


def test_sentinel_fires_red_on_the_incident_shape(tmp_path):
    """The exact 2026-08-15 + 2026-08-17 shape: two interior holes inside the
    window. The next healthy nightly (08-18) must shout, with the missing
    dates listed by name."""
    v = _arch(tmp_path, "vint", ["2026-08-14", "2026-08-16", "2026-08-18"])
    f = _arch(tmp_path, "dfs", ["2026-08-18"])
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=f)
    assert out["ok"] is False
    assert out["severity"] == "red"
    assert out["missing_vintage_dates"] == ["2026-08-15", "2026-08-17"]
    assert "2026-08-15" in out["message"] and "2026-08-17" in out["message"]
    assert "VINTAGE GAP RED" in out["message"]


def test_a_single_missed_night_is_yellow(tmp_path):
    v = _arch(tmp_path, "vint", ["2026-08-16", "2026-08-18"])
    f = _arch(tmp_path, "dfs", ["2026-08-18"])
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=f)
    assert out["severity"] == "yellow"
    assert out["ok"] is False
    assert out["missing_vintage_dates"] == ["2026-08-17"]


def test_a_stale_tail_is_red(tmp_path):
    """Newest vintage 3 days back is an ONGOING outage (~36h+ old at the
    nightly hour), red regardless of interior holes."""
    v = _arch(tmp_path, "vint", ["2026-08-14", "2026-08-15"])
    f = _arch(tmp_path, "dfs", ["2026-08-15"])
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=f)
    assert out["severity"] == "red"
    assert out["newest_vintage"] == "2026-08-15"
    assert "2026-08-16" in out["missing_vintage_dates"]
    assert "2026-08-18" in out["missing_vintage_dates"]


def test_dfs_only_staleness_is_yellow_never_red(tmp_path):
    """Vintage tail current, DFS tail stale: the shape of a dead
    _archive_slate, but an off day or empty slate is legitimate, so yellow is
    the ceiling for the DFS leg on its own."""
    v = _arch(tmp_path, "vint", ["2026-08-16", "2026-08-17", "2026-08-18"])
    f = _arch(tmp_path, "dfs", ["2026-08-14", "2026-08-15"])
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=f)
    assert out["severity"] == "yellow"
    assert out["newest_dfs"] == "2026-08-15"
    assert "DFS" in out["message"]


def test_offseason_and_empty_archive_stay_quiet(tmp_path):
    """The season fence: January is quiet whatever the archive says, and an
    in-season empty archive is 'not watching yet', never a manufactured red
    off last season's tail."""
    v = _arch(tmp_path, "vint", ["2026-08-18"])
    f = _arch(tmp_path, "dfs", [])
    out = rm._vintage_capture_gap(today=date(2027, 1, 10),
                                  vintage_dir=v, dfs_dir=f)
    assert out["ok"] is True and out["severity"] == "off_season"
    # in season, but only PRIOR-season files on disk: quiet, not red
    out2 = rm._vintage_capture_gap(today=date(2027, 4, 10),
                                   vintage_dir=v, dfs_dir=f)
    assert out2["ok"] is True and out2["severity"] == "no_archive"
    # missing directories are an empty archive, not a crash
    out3 = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                   vintage_dir=tmp_path / "absent_v",
                                   dfs_dir=tmp_path / "absent_d")
    assert out3["ok"] is True and out3["severity"] == "no_archive"


def test_non_date_filenames_are_ignored(tmp_path):
    v = _arch(tmp_path, "vint", ["2026-08-18"])
    (v / "notes.json").write_text("{}", encoding="utf-8")
    (v / "2026-13-99.json").write_text("{}", encoding="utf-8")
    out = rm._vintage_capture_gap(today=date(2026, 8, 18),
                                  vintage_dir=v, dfs_dir=tmp_path / "no_dfs")
    assert out["severity"] == "ok"
    assert out["newest_vintage"] == "2026-08-18"


def test_the_sentinel_is_a_watched_export(tmp_path):
    """Membership in SCHEDULED_EXPORTS is what carries a fired sentinel into
    red[] at drain time; fa_class_identity was silently dropped for a day for
    lacking exactly this (see the tuple's comment in run_monthly)."""
    assert "vintage_capture_gap" in rm.SCHEDULED_EXPORTS
    assert rm._ingest_kind("vintage_capture_gap") == "export"
    saved = list(rm._INGEST_HEALTH)
    rm._INGEST_HEALTH.clear()
    try:
        rm._record_ingest("vintage_capture_gap", False, 0,
                          "!!! VINTAGE GAP RED: synthetic", log=None)
        payload = rm.write_ingest_health(tmp_path, "test", log=None)
    finally:
        rm._INGEST_HEALTH.clear()
        rm._INGEST_HEALTH.extend(saved)
    assert "vintage_capture_gap" in payload["red"]
    row = next(r for r in payload["sources"]
               if r["source"] == "vintage_capture_gap")
    assert row["kind"] == "export"
