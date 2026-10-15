# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for tools/league_trends_persistence.py, League Trends' registered
persistence read (docs/LEAGUE_TRENDS_PERSISTENCE_GATE.md), on fixtures with
nulls. Nothing here reads a frame, a lab memo or the eval artifact: the whole
reporting path runs on the module's synthetic seasons, so a crash on a null
shows here before the one look runs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import league_trends_persistence as P  # noqa: E402
import trend_detect as TD  # noqa: E402


@pytest.fixture(scope="module")
def dry(tmp_path_factory):
    """The dry run once: frames, tables, the artifact and its path."""
    out = tmp_path_factory.mktemp("lt_persistence") / "persistence_eval.json"
    art = P.dry_run(out, log=lambda *a, **k: None)
    return {"art": art, "path": out, "frames": P.fixture_frames()}


# --------------------------------------------------------------------------- #
# the registration
# --------------------------------------------------------------------------- #
def test_registration_matches_the_gate_document():
    reg = P.parse_registration(P.GATE_DOC.read_text(encoding="utf-8"))
    assert reg["families"] == P.REGISTERED
    assert sorted(reg["excluded"]) == sorted(P.EXCLUDED)
    assert set(P.REGISTERED) <= set(TD.FAMILIES)
    assert all(b in TD.BAR_GRID for b in P.REGISTERED.values())
    assert all(TD.BARS["strict"][k] == b for k, b in P.REGISTERED.items())
    assert not any(k in P.REGISTERED for k in ("sp_velo", "rp_velo", "rp_entry_li"))
    assert re.fullmatch(r"[0-9a-f]{64}", P.EVAL_SHA256_REGISTERED)


def test_parse_registration_on_a_hand_made_table():
    text = ("## 2. The families\n\nRegistered families (2):\n\n| key | family | group | drift | bar |\n"
            "|---|---|---|---|---|\n| `rp_hb` | HB | pitch | yes | 4.25 |\n| `mix` | Mix | pitch | yes | 6 |\n\n"
            "Served families excluded from this read:\n\n| key | family | bar | why |\n|---|---|---|---|\n"
            "| `sp_velo` | V | 4.5 | velocity |\n\n## 3. Frame\n\n| `other` | x | y | z | 1 |\n")
    reg = P.parse_registration(text)
    assert reg == {"families": {"rp_hb": 4.25, "mix": 6.0}, "excluded": ["sp_velo"]}


def test_look_dates_close_every_outcome_window_inside_the_season():
    ds = P.look_dates(2025, "2025-09-28")
    assert ds[0] == "2025-05-18" and ds[-1] == "2025-08-24"
    assert all(d in TD.eval_dates(2025, "2025-09-28") for d in ds)
    last = pd.Timestamp(ds[-1]) + pd.Timedelta(days=P.OUTCOME_DAYS)
    assert last <= pd.Timestamp("2025-09-28")
    assert P.look_dates(2021, "2021-10-03")[-1] == "2021-08-29"


# --------------------------------------------------------------------------- #
# hit, tercile, Holm, verdict, bootstrap on hand-made rows
# --------------------------------------------------------------------------- #
def test_hit_rule():
    row = {"n_out": 3, "change_net": 1.2}
    assert P._hit(row, 1.0, 1.0) and not P._hit(row, -1.0, 1.0)
    assert not P._hit({"n_out": 3, "change_net": 0.9}, 1.0, 1.0)
    assert P._hit({"n_out": 1, "change_net": -1.0}, -1.0, 1.0)
    assert not P._hit({"n_out": 0, "change_net": 5.0}, 1.0, 1.0)
    assert not P._hit({"n_out": 2, "change_net": np.nan}, 1.0, 1.0)


def test_tercile_puts_nulls_nowhere():
    sd = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, np.nan, 0.9, 0.95])
    t = P._tercile(sd)
    assert np.isnan(t.iloc[6])
    assert t.iloc[0] == 0 and t.iloc[8] == 2
    assert sorted(set(t.dropna().astype(int))) == [0, 1, 2]
    assert P._tercile(pd.Series([np.nan, np.nan])).isna().all()


def test_holm_is_step_down_over_every_family_with_none_as_one():
    h = P.holm({"a": 0.001, "b": 0.012, "c": 0.02, "d": None, "e": 0.3, "f": 0.0005})
    assert h["m"] == 6 and h["alpha"] == 0.05
    f = h["families"]
    assert f["f"]["rank"] == 1 and f["f"]["pass"] and f["f"]["threshold"] == pytest.approx(0.05 / 6)
    assert f["a"]["rank"] == 2 and f["a"]["pass"] and f["a"]["threshold"] == pytest.approx(0.05 / 5)
    assert f["b"]["rank"] == 3 and f["b"]["pass"] and f["b"]["threshold"] == pytest.approx(0.05 / 4)
    assert f["c"]["rank"] == 4 and not f["c"]["pass"]            # 0.02 > 0.05 / 3
    assert not f["e"]["pass"] and f["d"]["p"] is None and not f["d"]["pass"]
    # once a rank fails, every later one fails even below its own threshold
    h2 = P.holm({"a": 0.03, "b": 0.04, "c": 0.0})
    assert h2["families"]["c"]["pass"] and not h2["families"]["a"]["pass"]   # 0.03 > 0.05 / 2
    assert not h2["families"]["b"]["pass"]                                   # 0.04 < 0.05, still fails


def test_verdict_rules():
    ok = {"pass": True}
    assert P.verdict_for({"episodes": 39, "hit_rate": 0.9}, ok) == "INDETERMINATE"
    assert P.verdict_for({"episodes": 40, "hit_rate": 0.5}, ok) == "PASS"
    assert P.verdict_for({"episodes": 40, "hit_rate": 0.49}, ok) == "FAIL"
    assert P.verdict_for({"episodes": 400, "hit_rate": 0.9}, {"pass": False}) == "FAIL"
    assert P.verdict_for({"episodes": 0, "hit_rate": None}, {"pass": False}) == "INDETERMINATE"
    line = P.line_for({"hit_rate": 0.714, "control_rate": 0.2})
    assert line.startswith("Of the changes like this listed in 2021 to 2025, 71 percent")
    assert line.endswith("(players with no listed change: 20 percent)")


def _rec(pid, hit, ctrl_hits, n_ctrl=5, n_out=1):
    return {"pid": pid, "hit": hit, "n_out": n_out,
            "controls": [{"hit": i < ctrl_hits, "n_out": 1} for i in range(n_ctrl)]}


def test_rates_and_bootstrap_resample_players_whole():
    recs = [_rec(1, True, 1), _rec(1, True, 0), _rec(2, False, 2), _rec(3, True, 1, n_ctrl=3),
            _rec(4, False, 0, n_out=0)]
    r = P.family_rates(recs)
    assert r["episodes"] == 5 and r["players"] == 4 and r["hits"] == 3
    assert r["hit_rate"] == pytest.approx(0.6) and r["controls"] == 23 and r["control_hits"] == 4
    assert r["control_rate"] == pytest.approx(4 / 23) and r["flags_no_game"] == 1
    assert r["episodes_short_of_controls"] == 1
    assert r["gap"] == pytest.approx(0.6 - 4 / 23)
    b = P.bootstrap_gap(recs, "rp_hb", reps=400)
    assert b["reps"] == 400 and b["finite_reps"] == 400
    assert b["ci95"][0] <= r["gap"] <= b["ci95"][1]
    assert 0.0 <= b["p_one_sided"] <= 1.0
    assert P.bootstrap_gap(recs, "rp_hb", reps=400) == b             # seeded
    one = P.bootstrap_gap([_rec(9, True, 0), _rec(9, False, 0)], "mix", reps=50)
    assert one["ci95"] == [0.5, 0.5] and one["p_one_sided"] == 0.0   # one player: no spread
    assert P.bootstrap_gap([], "mix")["p_one_sided"] is None
    assert P.family_rates([])["hit_rate"] is None and P.family_rates([])["gap"] is None


# --------------------------------------------------------------------------- #
# the whole reporting path on fixtures with nulls
# --------------------------------------------------------------------------- #
def test_dry_run_scores_the_planted_changes_and_carries_nulls(dry):
    art, path = dry["art"], dry["path"]
    text = path.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text) == art
    assert art["mode"] == "dry_run" and art["schema"] == P.SCHEMA
    assert set(art["families"]) == set(P.REGISTERED) == set(art["verdict"])
    assert art["holm"]["m"] == len(P.REGISTERED)
    hb = art["families"]["rp_hb"]
    by = {(r["season"], r["pid"]): r for r in hb["episode_records"]}
    assert by[(2024, 1)]["hit"] and by[(2025, 1)]["hit"]                 # the lasting change
    assert not by[(2024, 2)]["hit"] and not by[(2025, 2)]["hit"]         # the change that reverts
    assert by[(2024, 3)]["n_out"] == 0 and not by[(2024, 3)]["hit"]      # no game after the flag
    assert by[(2024, 3)]["out_mean"] is None and by[(2024, 3)]["change_net"] is None
    assert hb["flags_no_game"] >= 1
    for r in hb["episode_records"]:
        assert r["direction"] == "up" and r["threshold"] == pytest.approx(0.5 * abs(r["raw"]))
        assert r["mean_b"] == pytest.approx(r["mean_b_test"], abs=1e-6)
        assert len(r["controls"]) <= P.CONTROLS_PER_FLAG
        assert all(c["pid"] not in (1, 2, 3) for c in r["controls"])     # flagged players never control
        assert r["episode_dates"] >= 1 and r["episode_last"] >= r["D"]
    # the first episode of the lasting change is one episode over consecutive weeks
    assert by[(2024, 1)]["episode_dates"] > 1
    # mix: the flag's selected family is the trait scored
    mx = art["families"]["mix"]
    assert mx["episodes"] >= 1 and all(r["trait"] in TD.MIX_FAMS for r in mx["episode_records"])
    assert all(r["pid"] == 1 and r["hit"] for r in mx["episode_records"])
    # attack angle: the planted hitter, through the competitive cut, with a null angle elsewhere
    aa = art["families"]["attack_angle"]
    assert aa["episodes"] >= 1 and all(r["pid"] == 101 and r["hit"] for r in aa["episode_records"])
    # families nobody changed in: no episode, null rates, INDETERMINATE at p = 1 in Holm
    for k in ("rp_spin", "rp_ext", "bat_speed"):
        f = art["families"][k]
        assert f["episodes"] == 0 and f["hit_rate"] is None and f["control_rate"] is None
        assert f["gap"] is None and f["bootstrap"]["p_one_sided"] is None
        assert f["verdict"] == "INDETERMINATE" and f["holm"]["p"] is None and not f["holm"]["pass"]
    assert all(v == "INDETERMINATE" for v in art["verdict"].values())    # under 40 episodes
    assert art["lines"] == {}
    # the fits: a first season has none (floor on the raw change), the next fits on it only
    assert hb["fits"]["2024"]["fit"] is None and hb["fits"]["2024"]["phi"] == 1.0
    assert hb["fits"]["2025"]["fit_seasons"] == [2024]
    assert art["frame"]["2025"]["dates"][-1] <= "2025-09-03"


def test_controls_match_role_date_and_tercile_and_are_seeded(dry):
    frame = dry["frames"][2024]
    fam = TD.FAMILIES["rp_hb"]
    D = "2024-06-23"
    fl = P.flags_at(frame, D, fam, P.REGISTERED["rp_hb"], None, 1.0)
    assert fl["flag"].sum() >= 2
    tab = P.eligible_table(frame, D, fam, fl)
    assert set(tab["trait"]) == {"rp_hb"} and tab["pid"].is_unique
    assert tab["tercile"].dropna().isin([0, 1, 2]).all()
    assert tab.loc[tab["n_out"] > 0, "drift"].notna().all()
    first = fl.loc[fl["flag"], "pid"].astype(int).tolist()
    a = P.score_date(frame, D, fam, fl, first)
    b = P.score_date(frame, D, fam, fl, first)
    assert a == b                                                       # the seed per flag
    terc = tab.set_index("pid")["tercile"]
    for r in a:
        assert r["candidates"] >= len(r["controls"])
        for c in r["controls"]:
            assert terc[c["pid"]] == r["tercile"]
            assert c["pid"] not in first
    assert P.score_date(frame, D, fam, fl, []) == []


def test_baseline_and_outcome_tables_as_of_d(dry):
    frame = dry["frames"][2025]
    fam = TD.FAMILIES["rp_hb"]
    base = P.baseline_stats(frame, "2025-06-22", fam)
    out = P.outcome_stats(frame, "2025-06-22", fam)
    assert list(base.columns) == P._BASE_COLS and list(out.columns) == P._OUT_COLS
    assert (base["n_b"] >= 1).all() and base["mean_b"].notna().all()
    assert 3 not in set(out[out["n_out"] > 2]["pid"])                   # pid 3 stopped pitching
    assert (out["n_out"] > 0).all()
    assert P.outcome_stats(frame, "2025-10-03", fam).empty             # nothing after the season
    assert P.baseline_stats(frame, "2025-03-01", fam).empty
    prim = P.primary_as_of(frame, "2025-06-22", fam)
    assert prim and set(prim.values()) <= set(TD.FB_TYPES)
    mix = P.baseline_stats(frame, "2025-06-22", TD.FAMILIES["mix"])
    assert set(mix["trait"]) == set(TD.MIX_FAMS)
    sw = P.outcome_stats(frame, "2025-06-22", TD.FAMILIES["attack_angle"])
    assert 101 in set(sw["pid"]) and sw["out_mean"].notna().all()
    with pytest.raises(ValueError):
        P.outcome_stats(frame, "2025-06-22", TD.FAMILIES["rp_entry_li"])


def test_season_fit_takes_earlier_seasons_only(dry):
    frames = dry["frames"]
    import league_trends_calibrate as L
    fam = TD.FAMILIES["rp_hb"]
    tables = {s: L.measure_family(fr, fam, TD.eval_dates(s, fr.meta["covers_through"])[:4], R_=2)
              for s, fr in frames.items()}
    f24 = P.season_fit("rp_hb", tables, 2024)
    assert f24["fit"] is None and f24["phi"] == 1.0 and f24["fit_seasons"] == []
    f25 = P.season_fit("rp_hb", tables, 2025)
    assert f25["fit_seasons"] == [2024] and f25["fit"]["seasons"] == [2024]
    assert f25["phi"] > 0 and f25["fit"]["scored_season"] == 2025


# --------------------------------------------------------------------------- #
# the honesty guard and isolation
# --------------------------------------------------------------------------- #
def test_write_artifact_refuses_the_served_directory(tmp_path):
    with pytest.raises(ValueError):
        P.write_artifact({"a": 1}, P.DATA_DIR / "league_trends_persistence_eval.json")
    p = tmp_path / "x" / "eval.json"
    P.write_artifact({"a": np.float64(1.5), "b": np.nan}, p)
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1.5, "b": None}
    assert not (P.DATA_DIR / "league_trends_persistence_eval.json").exists()


def test_the_module_reads_no_gated_cache_and_names_no_gated_string():
    src = (ROOT / "tools" / "league_trends_persistence.py").read_text(encoding="utf-8")
    for banned in ("mg_" + "pen_", "mg_" + "hook_", "sp_" + "n365", "sp_" + "budget",
                   "sp_" + "ppo", "sp_" + "xouts", "bat_" + "ppa_l30",
                   "betting_model" + "_context", "leaderboard_" + "vintages",
                   "lineup_" + "captures", "weather_" + "forecasts", "game_" + "feeds",
                   '"bet' + 'ting"', "'bet" + "ting'", '"od' + 'ds"', "pbp_" + "corpus",
                   "swing_" + "pitches", "mlb_" + "transactions"):
        assert banned not in src, banned
    assert not re.search(r"import\s+bet" + r"ting", src)
    assert "to_parquet" not in src and "read_csv" not in src
    for word in (" luck", " due ", "regress", "trending", "clutch", "sleeper", "breakout",
                 " hot ", " cold "):
        assert word not in src.lower(), word
    em, en = chr(0x2014), chr(0x2013)
    assert em not in src and en not in src
    test_src = Path(__file__).read_text(encoding="utf-8")
    assert em not in test_src and en not in test_src
