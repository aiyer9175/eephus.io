# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""League Trends' eval artifact (plan 3.2, 3.3 and 5.3; task TR_2B_CALIBRATE_DARK).

Reads the preview path while league_trends_export.MLBSTATS_TRENDS_LIVE is
False (data/ after the flip): the artifact's bars equal trend_detect's table;
every listed family meets the stated policy on its calibration seasons from
the COUNTS in the artifact, at the smallest bar that does; the held-out verdict
recomputes from the artifact's counts and policy.held_out.phi, and phi from
its X2 and df; no lab fit season equals or follows its scored season;
false_per_day equals tail x tests summed over families; generated_at is
present; the lab's arithmetic re-run on the artifact's counts reproduces every
derived block, and the measure step re-run on the same synthetic inputs
reproduces its tables. The policy rules are also pinned on hand-made counts.
"""
from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sst

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import league_trends_calibrate as L  # noqa: E402
import trend_detect as TD  # noqa: E402

ART_PATH = L.eval_path()


@pytest.fixture(scope="module")
def art():
    if not ART_PATH.exists():
        pytest.skip(f"no League Trends eval artifact on this machine ({ART_PATH}); "
                    "run python tools/league_trends_calibrate.py")
    import json
    return json.loads(ART_PATH.read_text(encoding="utf-8"))


def _counts(art, key):
    """season -> the counts the lab's pure functions take, from the artifact."""
    out = {}
    for s, blk in art["families"][key]["seasons"].items():
        out[int(s)] = {"dates": blk["dates"], "tests": blk["tests"],
                       "by_bar": {b: {"flags": v["flags"], "placebo_sum": v["placebo_sum"]}
                                  for b, v in blk["by_bar"].items()}}
    return out


# --------------------------------------------------------------------------- #
# the artifact
# --------------------------------------------------------------------------- #
def test_path_follows_the_flag():
    assert ART_PATH == (L.EVAL_DATA if L.live_flag() else L.EVAL_PREVIEW)
    if not L.live_flag():
        assert ".cache" in ART_PATH.parts and "preview" in ART_PATH.parts


def test_generated_at_and_policy_constants(art):
    assert art["generated_at"] and datetime.strptime(art["generated_at"], "%Y-%m-%dT%H:%M:%SZ")
    p = art["policy"]
    assert p["strict"] == {"false_per_day_max": 0.05, "real_min": 0.90}
    assert p["looser"] == {"false_per_day_max": 0.10, "real_min": 0.85}
    assert (p["count_floor"], p["season_floor"], p["season_real_min"]) == (20, 5, 0.75)
    assert p["grid"] == list(TD.BAR_GRID) and p["R"] == TD.PLACEBO_R == 20
    assert p["calibration_seasons"] == {"pitch": [2023, 2024, 2025], "swing": [2024, 2025]}
    assert p["held_out"]["bound"] == "quasi-Poisson 99th" and p["held_out"]["q"] == 0.99


def test_bars_equal_trend_detect(art):
    for pol in ("strict", "looser"):
        assert {k: float(v) for k, v in art["bars"][pol].items()} == \
            {k: float(v) for k, v in TD.BARS[pol].items()}, pol
        assert set(TD.BARS[pol]) <= set(TD.FAMILIES), pol
    assert TD.BARS_PROVISIONAL is False
    assert {k: float(v) for k, v in art["placebo_sd"].items()} == \
        {k: float(v) for k, v in TD.PLACEBO_SD.items()}
    assert sorted(art["served"]) == sorted(TD.BARS["strict"])


def test_listed_families_meet_the_policy_from_the_counts(art):
    pol_rules = art["policy"]
    for pol in ("strict", "looser"):
        rule = pol_rules[pol]
        for key, bar in art["bars"][pol].items():
            fam = art["families"][key]
            cal = fam["calibration_seasons"]
            c = _counts(art, key)
            fl = sum(c[s]["by_bar"][f"{bar:g}"]["flags"] for s in cal)
            fa = sum(c[s]["by_bar"][f"{bar:g}"]["placebo_sum"] for s in cal) / art["policy"]["R"]
            nd = sum(c[s]["dates"] for s in cal)
            assert fa / nd <= rule["false_per_day_max"] + 1e-12, (pol, key)
            assert 1 - fa / fl >= rule["real_min"] - 1e-12, (pol, key)
            assert fl >= pol_rules["count_floor"], (pol, key)
            for s in cal:
                f_s = c[s]["by_bar"][f"{bar:g}"]["flags"]
                if f_s >= pol_rules["season_floor"]:
                    share = 1 - c[s]["by_bar"][f"{bar:g}"]["placebo_sum"] / art["policy"]["R"] / f_s
                    assert share >= pol_rules["season_real_min"] - 1e-12, (pol, key, s)
            # the smallest bar on the grid that passes
            for b in TD.BAR_GRID:
                if b >= bar:
                    break
                assert not L.passes(L.pooled(c, cal, f"{b:g}", art["policy"]["R"]), pol), \
                    (pol, key, b)


def test_held_out_verdict_recomputes(art):
    Rr = art["policy"]["R"]
    for pol, hk in (("strict", "held_out"), ("looser", "held_out_looser")):
        h = art["policy"][hk]
        x2, df = 0.0, 0
        for part in h["families"]:
            key, bar = part["family"], f"{part['bar']:g}"
            ch = art["families"][key]["chosen"][pol]
            c = _counts(art, key)
            fx2 = 0.0
            for s in art["families"][key]["calibration_seasons"]:
                e = ch["tail_per_test"] * c[s]["tests"] * Rr
                if e > 0:
                    fx2 += (c[s]["by_bar"][bar]["placebo_sum"] - e) ** 2 / e
            x2 += fx2
            df += part["df"]
        assert x2 == pytest.approx(h["x2"], abs=1e-3) and df == h["df"]
        phi = max(1.0, x2 / df) if df else 1.0
        assert phi == pytest.approx(h["phi"], abs=1e-3)
        for key, verdict in h["verdicts"].items():
            ho = art["families"][key]["held_out"][pol]
            if verdict == "not scored":
                continue
            ch = art["families"][key]["chosen"][pol]
            lam = ch["tail_per_test"] * ho["tests"] * Rr
            bound = h["phi"] * sst.poisson.ppf(0.99, lam / h["phi"]) if lam > 0 else 0.0
            # the artifact rounds lam and the bound to 4 decimals
            assert ho["lam"] == pytest.approx(lam, abs=1e-4)
            assert ho["bound"] == pytest.approx(bound, abs=1e-4)
            assert sum(ho["per_shuffle"]) == ho["placebo_sum"]
            assert verdict == ("left off" if ho["placebo_sum"] > bound else "kept"), (pol, key)
            assert (key in art["bars"][pol]) == (verdict == "kept")


def test_no_fit_season_equals_or_follows_its_scored_season(art):
    for key, by in art["shrink"]["lab_seasons"].items():
        for s, fit_seasons in by.items():
            assert all(int(x) < int(s) for x in fit_seasons), (key, s, fit_seasons)
    for key, fam in art["families"].items():
        for s, blk in fam["seasons"].items():
            assert all(int(x) < int(s) for x in blk["phi_seasons"]), (key, s)
            if blk["fit"]:
                assert all(int(x) < int(s) for x in blk["fit"]["seasons"]), (key, s)
                assert blk["fit"]["scored_season"] == int(s)
    for g, seasons in art["shrink"]["seasons"].items():
        assert all(int(x) < art["policy"]["live_season"] for x in seasons), g


def test_false_per_day_is_tail_times_tests_summed(art):
    for pol in ("strict", "looser"):
        tot = sum(art["families"][k]["chosen"][pol]["tail_per_test"]
                  * art["families"][k]["chosen"][pol]["tests_per_day"] for k in art["bars"][pol])
        assert art["totals"][pol]["false_per_day"] == pytest.approx(tot, abs=1e-5)
        assert art["totals"][pol]["families"] == len(art["bars"][pol])
    assert art["false_per_day"] == art["totals"]["strict"]["false_per_day"]


def test_rerun_of_the_arithmetic_reproduces_the_artifact(art):
    """The policy, the dispersion and the held-out verdicts re-derived by the
    lab's own functions from the artifact's per-season counts."""
    Rr = art["policy"]["R"]
    for key, fam in art["families"].items():
        c = _counts(art, key)
        cal = fam["calibration_seasons"]
        for b, p in fam["pooled"].items():
            assert L.pooled(c, cal, b, Rr) == p, (key, b)
        for pol in ("strict", "looser"):
            assert L.choose(c, cal, pol, Rr) == fam["chosen"][pol], (key, pol)
    for pol, hk in (("strict", "held_out"), ("looser", "held_out_looser")):
        items = [(k, _counts(art, k), art["families"][k]["calibration_seasons"],
                  f"{art['families'][k]['chosen'][pol]['bar']:g}",
                  art["families"][k]["chosen"][pol]["tail_per_test"])
                 for k in sorted(art["families"]) if art["families"][k]["chosen"][pol]]
        d = L.dispersion(items, Rr)
        for f in ("phi", "x2", "df", "families"):
            assert d[f] == art["policy"][hk][f], (pol, f)


def test_pool_receipts_and_league_env(art):
    pool = art["pool"]
    assert pool["source"] == "savant_days" and pool["label"] == "all tracked"
    for s, pin in pool["pinned"].items():
        got = pool["receipts"][s]
        assert got["hitters"] >= pin["hitters"] and got["swings"] >= pin["swings"], s
    env = art["league_env"]["seasons"]
    assert sorted(env) == ["2018", "2019", "2021", "2022", "2023", "2024", "2025"]
    for s, v in env.items():
        assert 92.5 < v["ff_mph"] < 95.5 and 0 <= v["st_pct"] < 15 and 0 < v["fs_pct"] < 5, s
        assert v["sba_per_club_game"] == pytest.approx((v["sb"] + v["cs"]) / (2 * v["games"]),
                                                       abs=1e-5)
    recs = art["inputs"]["betting_records"]
    assert (art["rd_band"] is None) == (not (recs["5c-A"] and recs["5d"] and recs["5k"]))


# --------------------------------------------------------------------------- #
# the policy rules on hand-made counts
# --------------------------------------------------------------------------- #
def _season(flags_by_bar: dict, placebo_by_bar: dict, tests=2000, dates=20):
    return {"dates": dates, "tests": tests,
            "by_bar": {f"{b:g}": {"flags": flags_by_bar.get(b, 0),
                                  "placebo_sum": placebo_by_bar.get(b, 0)} for b in TD.BAR_GRID}}


def test_policy_rules_on_hand_made_counts():
    # 3 seasons: 10 flags each at 4.0 with 0.4 false each (8 placebo over R 20)
    per = {s: _season({4.0: 10, 4.25: 9}, {4.0: 8, 4.25: 2}) for s in (2023, 2024, 2025)}
    p = L.pooled(per, [2023, 2024, 2025], "4", 20)
    assert (p["flag_count"], p["false_count"], p["dates"]) == (30, 1.2, 60)
    assert p["real"] == pytest.approx(0.96) and p["false_per_day"] == pytest.approx(0.02)
    assert L.passes(p, "strict")
    assert L.choose(per, [2023, 2024, 2025], "strict", 20)["bar"] == 4.0
    # the count floor: 19 pooled flags never pass
    per19 = {s: _season({4.0: n}, {4.0: 0}) for s, n in ((2023, 6), (2024, 6), (2025, 7))}
    assert not L.passes(L.pooled(per19, [2023, 2024, 2025], "4", 20), "strict")
    # a season under 5 flags is not judged, one at 5 or more is
    perj = {2023: _season({4.0: 4}, {4.0: 40}), 2024: _season({4.0: 30}, {4.0: 0}),
            2025: _season({4.0: 5}, {4.0: 30})}
    pj = L.pooled(perj, [2023, 2024, 2025], "4", 20)
    assert pj["seasons_judged"] == [2024, 2025] and pj["seasons_not_judged"] == [2023]
    assert pj["worst_judged"] == pytest.approx(0.7) and not L.passes(pj, "strict")


def test_quasi_poisson_bound_and_dispersion():
    assert L.quasi_bound(10.0, 1.0) == sst.poisson.ppf(0.99, 10.0)
    assert L.quasi_bound(10.0, 3.0) == pytest.approx(3.0 * sst.poisson.ppf(0.99, 10.0 / 3.0))
    per = {2023: _season({4.0: 10}, {4.0: 10}, tests=1000),
           2024: _season({4.0: 10}, {4.0: 30}, tests=1000)}
    tail = 40 / 20 / 2000
    d = L.dispersion([("x", per, [2023, 2024], "4", tail)], 20)
    e = tail * 1000 * 20
    assert d["x2"] == pytest.approx(((10 - e) ** 2 + (30 - e) ** 2) / e, abs=1e-4)
    assert d["df"] == 1 and d["phi"] == pytest.approx(max(1.0, d["x2"]), abs=1e-4)
    ho = L.held_out(_season({4.0: 3}, {4.0: 50}, tests=1000), tail, 1.0, "4", 20)
    assert ho["verdict"] == ("left off" if 50 > sst.poisson.ppf(0.99, e) else "kept")


# --------------------------------------------------------------------------- #
# re-running the measure step on the same synthetic inputs
# --------------------------------------------------------------------------- #
def _frame(season: int, seed: int):
    from test_trend_detect import Builder, relievers, starters
    b = Builder(season)
    rng = np.random.default_rng(seed)
    starters(b, rng, n=30, last_day=180)
    relievers(b, rng, range(101, 181), last_day=180)
    return b.frame()


def test_measure_and_fit_rerun_is_identical(tmp_path):
    frames = {2023: _frame(2023, 1), 2024: _frame(2024, 2)}
    for f in frames.values():
        f.meta.update({"key": f"synthetic-{f.season}", "games": len(f.games),
                       "covers_through": str(f.games["date"].max())})
    keys = ["sp_velo", "rp_velo", "p_k_30d"]

    def go(lab):
        out = {}
        for s, f in frames.items():
            m = L.measure_season(s, keys, lab_dir=lab, frame_loader=lambda y: frames[y], R_=3)
            out[s] = m
        return out

    a, b = go(tmp_path / "a"), go(tmp_path / "b")
    for s in frames:
        for k in keys:
            pd.testing.assert_frame_equal(a[s]["tables"][k], b[s]["tables"][k])
    # the memo reads back the same tables
    c = go(tmp_path / "a")
    for s in frames:
        for k in keys:
            pd.testing.assert_frame_equal(a[s]["tables"][k], c[s]["tables"][k])
    dates = {s: a[s]["dates"] for s in frames}
    r1 = L.fits_and_counts("rp_velo", {s: a[s]["tables"]["rp_velo"] for s in frames}, dates,
                           [2024], R_=3)
    r2 = L.fits_and_counts("rp_velo", {s: b[s]["tables"]["rp_velo"] for s in frames}, dates,
                           [2024], R_=3)
    assert r1["seasons"] == r2["seasons"] and r1["phi_used"] == r2["phi_used"]
    assert r1["phi_seasons"][2024] == [2023]
    assert r1["fits"][2024]["seasons"] == [2023]
    assert math.isfinite(r1["phi_used"][2024]) and r1["phi_used"][2024] > 0


# --------------------------------------------------------------------------- #
# the betting records and the rd_band block (plan 4.3; owner TR-5d 2026-10-21)
# --------------------------------------------------------------------------- #
_C5A = "#### Closure, recorded 2026-10-02: the pair closes for 2026\n"
_K5 = "### Result (run 2026-10-14, once): 5k-A14, 5k-A30 and 5k-B FAIL at p = 1\n"
_D5C = ("### Decisions recorded 2026-10-14: 5d-C at p = 1 without a read, and 5d-A, 5d-B, "
        "5d-D and 5d-E not read\n\n**5d-A, 5d-B, 5d-D and 5d-E: not read.** These are ...\n")


def test_the_5d_c_decision_counts_as_the_5d_record():
    recs = L.betting_records(_C5A + _K5 + _D5C)
    assert (recs["5c-A"], recs["5d"], recs["5k"]) == (True, True, True)
    assert "TR-5d" in recs["5d_note"]
    # no 5d block at all: no record
    assert L.betting_records(_C5A + _K5)["5d"] is False
    assert L.betting_records(_C5A + _K5)["5d_note"] is None
    # a 5d result block counts too
    assert L.betting_records(_C5A + _K5 + "### Result (run 2026-10-20, once): 5d-A FAIL\n")["5d"]
    # the 5c-A and 5k records are still required
    assert not L.betting_records(_K5 + _D5C)["5c-A"]
    assert not L.betting_records(_C5A + _D5C)["5k"]
    note = L.rd_band_note(L.betting_records(_C5A + _D5C))
    assert note.startswith("null: docs/diamond-betting.md records 5c-A, 5d but not the 5k")


def test_rd_band_refresh_writes_that_block_only(tmp_path, monkeypatch):
    import json
    src = tmp_path / "eval.json"
    base = {"generated_at": "2026-10-14T18:34:01Z", "bars": {"rp_velo": 4.5},
            "families": {"rp_velo": {"x": 1}}, "rd_band": None, "rd_band_note": "null: old",
            "inputs": {"lab_version": 2, "betting_records": {"5d": False}},
            "live_check": {"as_of": "2026-09-27"}}
    src.write_text(json.dumps(base), encoding="utf-8")
    doc = tmp_path / "betting.md"
    monkeypatch.setattr(L, "BETTING_DOC", doc)
    band = {"sigma_m": 4.4, "seasons": [2021, 2022, 2023, 2024, 2025], "n": 10, "club_seasons": 2}
    monkeypatch.setattr(L, "rd_band_measure", lambda: dict(band))
    out = tmp_path / "out.json"
    # the records are there: rd_band measured, the note dropped
    doc.write_text(_C5A + _K5 + _D5C, encoding="utf-8")
    assert L.rd_band_refresh(path=src, out=out, log=lambda *a: None) == band
    new = json.loads(out.read_text(encoding="utf-8"))
    assert new["rd_band"] == band and "rd_band_note" not in new
    assert new["inputs"]["betting_records"]["5d"] is True
    assert new["inputs"]["lab_version"] == 2 and new["inputs"]["rd_band_refreshed_at"]
    for k in ("generated_at", "bars", "families", "live_check"):
        assert new[k] == base[k], k
    assert set(new) == set(base) - {"rd_band_note"}
    # a record missing: null with the reason, nothing measured
    doc.write_text(_C5A + _D5C, encoding="utf-8")
    monkeypatch.setattr(L, "rd_band_measure", lambda: pytest.fail("measured without the records"))
    assert L.rd_band_refresh(path=src, out=out, log=lambda *a: None) is None
    new = json.loads(out.read_text(encoding="utf-8"))
    assert new["rd_band"] is None and "5k" in new["rd_band_note"]


# --------------------------------------------------------------------------- #
# isolation
# --------------------------------------------------------------------------- #
def test_the_lab_reads_no_gated_cache_and_names_no_gated_string():
    for path in (ROOT / "tools" / "league_trends_calibrate.py", ROOT / "trend_detect.py",
                 ROOT / "trend_frames.py"):
        src = path.read_text(encoding="utf-8")
        for banned in ("mg_" + "pen_", "mg_" + "hook_", "sp_" + "n365", "sp_" + "budget",
                       "sp_" + "ppo", "sp_" + "xouts", "bat_" + "ppa_l30",
                       "betting_model" + "_context", "leaderboard_" + "vintages",
                       "lineup_" + "captures", "weather_" + "forecasts", "game_" + "feeds",
                       '"bet' + 'ting"', "'bet" + "ting'", '"od' + 'ds"'):
            assert banned not in src, (path.name, banned)
        assert not re.search(r"import\s+bet" + r"ting", src), path.name
