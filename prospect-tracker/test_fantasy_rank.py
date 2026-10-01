"""Tests for fantasy_rank.py, the /fantasy/ Dynasty Fantasy Rank (owner answer
M21-4, 2026-09-25): MLB players and prospects on one dynasty rank of projected
fantasy value, not WAR, that does not reorder /projections/."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

import fantasy_rank as fr
import fantasy_scoring as fscore

ROOT = Path(__file__).parent


def _hit_line(pa, k=0.22, bb=0.09, iso=0.17, babip=0.30, hr=0.035, sb=0.02):
    return fr.hitter_line({"k_pct": k, "bb_pct": bb, "iso": iso, "babip": babip,
                           "hr_pa": hr}, pa, sb)


def _pit_line(ip, k=0.25, bb=0.08, hr=0.03, role="SP"):
    bf = ip * 4.3
    comps = {"k_pct": k, "bb_pct": bb, "hr_bf": hr}
    return fr.pitcher_line(comps, bf, ip, role, fr.fip_from(comps, bf, ip, 3.1))


def _model(n_hit=160, n_pit=130, seed=7):
    """A synthetic monthly model: enough MLB lines per side that replacement
    sits inside the pool, plus a tabulated aging-free delta table."""
    rng = random.Random(seed)
    rows = []
    for i in range(n_hit):
        pa = 150 + rng.random() * 500
        line = _hit_line(pa, k=0.16 + rng.random() * 0.12, hr=0.02 + rng.random() * 0.03)
        rows.append({"mlbam": 10000 + i, "side": "hit", "pos": "H", "name": "H%d" % i,
                     "team": "AAA", "lines": [line] * fr.HORIZON})
    for i in range(n_pit):
        ip = 40 + rng.random() * 150
        line = _pit_line(ip, k=0.18 + rng.random() * 0.12)
        rows.append({"mlbam": 20000 + i, "side": "pit", "pos": "SP", "name": "P%d" % i,
                     "team": "BBB", "lines": [line] * fr.HORIZON})
    roto = {f: [] for f in fr.FORMATS if f not in fr.POINTS_FORMATS}
    for f in roto:
        for t in range(fr.HORIZON):
            roto[f].append({s: fscore.roto_params([r["lines"][t] for r in rows if r["side"] == s], f, s)
                            for s in ("hit", "pit")})
    mlb = []
    for r in rows:
        raw = {f: [fr.season_value(r["lines"][t], f, r["side"],
                                   roto[f][t][r["side"]] if f in roto else None)
                   for t in range(fr.HORIZON)] for f in fr.FORMATS}
        mlb.append({"mlbam": r["mlbam"], "side": r["side"], "pos": r["pos"], "name": r["name"],
                    "team": r["team"], "raw": raw})
    repl = {f: [{s: fr.replacement([m["raw"][f][t] for m in mlb if m["side"] == s], s)
                 for s in ("hit", "pit")} for t in range(fr.HORIZON)] for f in fr.FORMATS}
    fits = {"hit": {t: {"x_mean": 0.0, "y_mean": y, "slope": 0.0, "r2": 0.0, "n": 50,
                        "feature": x} for (t, x), y in zip(fr.HIT_TARGETS,
                                                           (20.0, 9.0, 17.0, 3.5, 30.0, 2.0))},
            "pit": {t: {"x_mean": 0.0, "y_mean": y, "slope": 0.0, "r2": 0.0, "n": 50,
                        "feature": x} for (t, x), y in zip(fr.PIT_TARGETS, (25.0, 8.0, 3.0))}}
    pt = {g: {"mean": [600.0] * fr.HORIZON, "bins": [[600.0] * fr.PT_BINS] * fr.HORIZON,
              "n": [100] * fr.HORIZON} for g in ("hit",)}
    pt.update({g: {"mean": [180.0] * fr.HORIZON, "bins": [[180.0] * fr.PT_BINS] * fr.HORIZON,
                   "n": [100] * fr.HORIZON} for g in ("sp", "rp")})
    return {"first_season": 2027, "seasons": list(range(2027, 2027 + fr.HORIZON)),
            "fipc": 3.1, "roto_params": roto, "repl": repl, "mlb": mlb, "fits": fits,
            "pt": pt, "deltas": {}}


_KM = {"AA": [0.4, 0.3, 0.25, 0.22, 0.2, 0.2, 0.2, 0.2, 0.2]}


def _board():
    return [{"mlbam": 30001, "name": "Near Kid", "org": "CCC", "pos": "SS", "eta": 2027, "rank": 1},
            {"mlbam": 30002, "name": "Far Kid", "org": "CCC", "pos": "SS", "eta": 2035, "rank": 2},
            {"mlbam": 30003, "name": "No ETA", "org": "CCC", "pos": "SS", "eta": None, "rank": 3}]


def _live():
    milb = {"milb_level": "AA", "k_rel": 0.0}
    return {30001: {"hit": {"milb": milb, "age_now": 21.0}},
            30002: {"hit": {"milb": milb, "age_now": 18.0}},
            30003: {"hit": {"milb": milb, "age_now": 20.0}}}


def _ranks(payload):
    return {r["mlbam"]: r["rk"] for r in payload["rows"]}


def test_the_rank_is_invariant_to_any_input_order():
    """Shuffling the MLB leg (the order any other board, /projections/
    included, might hand rows over in) and the board rows moves no rank."""
    m = _model()
    base = fr.build(m, _board(), cur_season=2026, live_milb=_live(), km=_KM)
    shuffled = dict(m)
    mlb = list(m["mlb"])
    random.Random(3).shuffle(mlb)
    shuffled["mlb"] = mlb
    board = list(reversed(_board()))
    again = fr.build(shuffled, board, cur_season=2026, live_milb=_live(), km=_KM)
    assert _ranks(base) == _ranks(again)


def test_nothing_on_projections_reads_the_rank_and_the_rank_reads_no_war():
    """It must not reorder /projections/: proj_export never imports it, and it
    reads neither the /projections/ artifact nor any WAR field."""
    proj = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    assert "fantasy_rank" not in proj
    src = (ROOT / "fantasy_rank.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert "mlb_projections.json\")" not in code and '_load_json("mlb_projections' not in code
    assert not re.search(r"""\[["']war["']\]|get\(["']war""", code)


def test_a_prospect_with_zero_arrival_probability_contributes_zero():
    m = _model()
    out = fr.build(m, _board(), cur_season=2026, live_milb=_live(), km=_KM)
    by = {r["mlbam"]: r for r in out["rows"]}
    far, none_ = by[30002], by[30003]
    assert far["p"] == [0.0] * fr.HORIZON and none_["p"] == [0.0] * fr.HORIZON
    for r in (far, none_):
        assert all(v == 0 for f in fr.FORMATS for v in r["s"][f])
        assert all(r["v"][f] == 0 for f in fr.FORMATS)
        assert all(r["rk"][f] is None for f in fr.FORMATS)
    # The arrived one is valued, so the zero above is the arrival and not the line.
    assert by[30001]["v"]["fgp"] > 0


def test_arrival_is_zero_before_the_eta_and_the_level_curve_after():
    p = fr.arrival(2029, "AA", 2027, _KM)
    assert p[:2] == [0.0, 0.0]
    assert p[2:] == [round(1 - 0.25, 4), round(1 - 0.22, 4), round(1 - 0.2, 4)]
    assert fr.arrival(2027, "Rk", 2027, _KM) == [0.0] * fr.HORIZON   # no CPX curve here
    assert fr.arrival(2027, "MLB", 2027, _KM) == [1.0] * fr.HORIZON
    assert fr.arrival(2026, "AA", 2027, _KM)[0] == round(1 - 0.4, 4)  # a past ETA starts now


def test_value_is_discounted_floored_above_replacement():
    assert fr.repl_index("hit") == 144 and fr.repl_index("pit") == 120
    vals = list(range(300, 0, -1))
    assert fr.replacement(vals, "hit") == vals[144]
    assert fr.above(10.0, 25.0) == 0.0 and fr.above(30.0, 25.0) == 5.0
    tot = fr.total_value([10.0, 10.0, 0.0, 0.0, 0.0], [1.0, 0.5, 1.0, 1.0, 1.0])
    assert tot == pytest.approx(10.0 + 0.5 * 10.0 / 1.07)
    assert fr.DISCOUNT_RATE == 0.07


def test_horizon_and_discount_match_the_projections_window_and_platform_rate():
    import value_framework as vf
    assert fr.DISCOUNT_RATE == float(vf._config()["discount_rate"])
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    assert re.search(r"^HORIZON = %d\b" % fr.HORIZON, src, re.M)


def test_the_mlb_leg_season_zero_is_the_corpus_line():
    proj = {"k_pct": 0.21, "bb_pct": 0.09, "iso": 0.18, "babip": 0.3, "hr_pa": 0.04,
            "pt_proj": 610.0, "age": 27, "role": "H"}
    lines = fr.mlb_horizon_lines(proj, "hit", "H", {}, sb_pa=0.02)
    import fantasy_export as fe
    assert lines[0] == fe._hitter_ros(proj, 610.0, 0.02)
    assert len(lines) == fr.HORIZON


def test_roto_params_value_a_line_outside_the_pool_on_the_pool_scale():
    pool = [dict(_hit_line(400 + 20 * i, hr=0.02 + 0.002 * i), id=i) for i in range(12)]
    vals = fscore.roto_valuations(pool, "5x5", "hit")
    params = fscore.roto_params(pool, "5x5", "hit")
    for p in pool:
        v, _ = fscore.roto_value(p, params)
        assert round(v, 2) == pytest.approx(vals[p["id"]]["value"], abs=0.01)
    assert fscore.roto_params([], "5x5", "hit") is None


def test_pt_bins_are_mean_preserving():
    vals = [0.0] * 50 + [600.0] * 50
    b = fr._bin_means(vals)
    assert len(b) == fr.PT_BINS and sum(b) / len(b) == pytest.approx(300.0)
    assert b[0] == 0.0 and b[-1] == 600.0


def test_the_backtest_frames_exclude_the_reserved_ones():
    assert not set(fr.BACKTEST_VINTAGES) & fr.RESERVED_LIST_VINTAGES
    assert not set(fr.KM_TRAIN_VINTAGES) & fr.RESERVED_LIST_VINTAGES
    assert fr.RESERVED_DEBUT_FROM == 2025 and fr.OBSERVED_THROUGH < fr.RESERVED_DEBUT_FROM
    with pytest.raises(AssertionError):
        fr._eta_cohort((2020,))


def test_translation_pairs_and_pt_cohort_drop_2025_debuts():
    corpus = {"hit": [{"mlbam": 1, "season": 2025, "pa": 400, "k_pct": 0.2, "bb_pct": 0.1,
                       "iso": 0.2, "babip": 0.3, "hr_pa": 0.04},
                      {"mlbam": 2, "season": 2023, "pa": 400, "k_pct": 0.25, "bb_pct": 0.08,
                       "iso": 0.15, "babip": 0.29, "hr_pa": 0.03}], "pit": []}
    mat = {"hit": [{"kind": "debuted", "mlbam_id": 1, "debut_year": 2025, "position": "SS",
                    "milb": {"k_rel": 0.01}},
                   {"kind": "debuted", "mlbam_id": 2, "debut_year": 2023, "position": "SS",
                    "milb": {"k_rel": -0.02}}], "pit": []}
    pairs = fr.translation_pairs(corpus, 2030, matrices=mat)
    assert pairs["hit"]["k_pct"] == [(-0.02, pytest.approx(25.0))]
    pt = fr.pt_curves(corpus, 2026, matrices=mat)
    assert pt["hit"]["n"][0] == 1 and pt["hit"]["mean"][0] == 400.0


def test_the_served_rank_is_ordered_by_value_and_quotes_its_backtest():
    path = ROOT / "data" / "fantasy_rank.json"
    if not path.exists():
        pytest.skip("data/fantasy_rank.json is built by fantasy_export")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert path.stat().st_size < 300 * 1024, path.stat().st_size
    assert d["horizon"] == fr.HORIZON and d["discount_rate"] == fr.DISCOUNT_RATE
    for f in fr.FORMATS:
        ranked = sorted((r for r in d["rows"] if r["rk"][f] is not None), key=lambda r: r["rk"][f])
        vals = [r["v"][f] for r in ranked]
        assert vals == sorted(vals, reverse=True), f
        assert all(r["v"][f] > 0 for r in ranked)
    assert d["prospect_leg"]["component_source"] == "translation"
    ev_path = ROOT / "data" / "fantasy_rank_eval.json"
    if ev_path.exists() and d.get("backtest"):
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        assert d["backtest"]["rho_prospect_leg"] == ev["pooled"]["rho_prospect_leg"]
        assert d["backtest"]["rho_consensus_fv"] == ev["pooled"]["rho_consensus_fv"]


def test_the_eval_artifact_is_provisional_and_names_its_frame():
    path = ROOT / "data" / "fantasy_rank_eval.json"
    if not path.exists():
        pytest.skip("written by python fantasy_rank.py --backtest")
    ev = json.loads(path.read_text(encoding="utf-8"))
    assert ev["verdict"] == "provisional"
    assert ev["frame"]["list_vintages"] == list(fr.BACKTEST_VINTAGES)
    assert ev["pooled"]["difference_ci95_player_clustered"]["draws"] == 2000
    # No stratum named after an FV cell (docs/PROSPECT_ANCHOR_GATE.md).
    assert not re.search(r"\bfv_?(45|50|55|60|65)\b", json.dumps(ev).lower())
