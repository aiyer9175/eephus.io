# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The game-intensity stage-1 lab (tools/intensity_lab.py) on fixtures only.

The section "Game intensity: stakes, matchup quality and the postseason" of
docs/diamond-betting.md registers stage 1; a dry run of any fit, score or twin on real
data before its look IS the look. So nothing here reads .cache/betting/regular_finals,
the play corpus, a postseason feed or the postseason cache: every source is the
built-in synthetic fixture or a hand-made table. Pinned:

- the refusals: the clock (no step Z, a registered look day, before 2026-11-02, before
  the day after the 2026 World Series), the overlap list (5c-B, 5c-C, 5d, 5k and 7e-D by
  record or kill date; never 5e or 5i-B), the one-run guard (the artifact, the
  section's result heading), data/ for the dry run and counts, a 2026 game, an
  unregistered parameter;
- fixture arithmetic for each family (the offset logistic, the paired delta, CR1, the
  focus set, the fixed-effects panel, the difference in differences, Holm, Wilson,
  q = RD / (G + 70), the Elo snapshot strictly before the date);
- the twin draws (default_rng(k), k = 0 to 199, within-date permutations, a strict bar);
- counts-only mode prints no statistic;
- G_REF equals the recorded literal, in the core, the lab and the section;
- the reporting path end to end on the fixture with nulls.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import math
import re
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pytest

import intensity_core as ic
import test_betting_intensity_registration as reg

ROOT = Path(__file__).resolve().parent
LAB_PATH = ROOT / "tools" / "intensity_lab.py"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)


def _load():
    spec = importlib.util.spec_from_file_location("intensity_lab_under_test", LAB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _load()

EPOCH_OK = "## 9. Results\n\n### 2026-10-03: step Z, the fWAR label epoch's results\n"
OK_DAY = dt.date(2026, 11, 3)
WS_END = "2026-10-31"


def _doc_with(records: tuple = (), stage1: bool = False) -> str:
    """A miniature gate document: the section plus the overlap looks' headings, with a
    Result heading under each look named in `records`."""
    parts = ["# doc\n"]
    for look, head in (("5c-B", "### 5c-B. availability"), ("5c-C", "### 5c-C. star")):
        parts.append(f"## 5c. Schema 3\n\n{head}\n\ntext\n" if look == "5c-B" else
                     f"{head}\n\ntext\n")
        if look in records:
            parts.append("### Result (run 2026-10-08, once): FAIL\n\ntext\n")
    for look, head in (("5d", "## 5d. Schema 4"), ("5k", "## 5k. Run environment")):
        parts.append(f"{head}\n\ntext\n")
        if look in records:
            parts.append("### Result (run 2026-10-20, once): FAIL\n\ntext\n")
    parts.append("## 5e. The handedness gate\n\ntext\n")
    parts.append(f"## 5o. {L.SECTION_TITLE} (pre-registered 2026-10-08)\n\ntext\n")
    if stage1:
        parts.append("### Stage 1 result (run 2026-11-03, once): no member resolved\n\n")
    parts.append("---\n\n## 7e. The per-market objective\n\n### 7e-D. The as-served replay\n\n")
    if "7e-D" in records:
        parts.append("### Result (run 2026-10-30, once): FAIL\n\n")
    parts.append("## 7f. next\n")
    return "".join(parts)


ALL_RECORDED = ("5c-B", "5c-C", "5d", "5k", "7e-D")


@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("ix") / "game_intensity_eval.json"
    with redirect_stdout(io.StringIO()):
        art = L.run_stage1(L.synthetic_fixture(), out, mode="dry_run_fixture",
                           params=dict(L.FIXTURE_PARAMS), log=lambda *_a, **_k: None)
    return art, out


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------
def test_the_clock_refusals():
    doc = _doc_with(ALL_RECORDED)
    with pytest.raises(L.LabRefused, match="step Z"):
        L.check_clock(OK_DAY, epoch_text="## 9. Results\n", doc_text=doc, ws_end=WS_END)
    for d in ("2026-11-06", "2026-11-13", "2026-11-20", "2026-12-01"):
        with pytest.raises(L.LabRefused, match="look day"):
            L.check_clock(dt.date.fromisoformat(d), epoch_text=EPOCH_OK, doc_text=doc,
                          ws_end=WS_END)
    with pytest.raises(L.LabRefused, match="2026-11-02"):
        L.check_clock(dt.date(2026, 11, 1), epoch_text=EPOCH_OK, doc_text=doc, ws_end=WS_END)
    with pytest.raises(L.LabRefused, match="World Series"):
        L.check_clock(OK_DAY, epoch_text=EPOCH_OK, doc_text=doc, ws_end=None)
    # the later of the two dates: a World Series ending 2026-11-04 holds the run to 11-05
    with pytest.raises(L.LabRefused, match="World Series"):
        L.check_clock(dt.date(2026, 11, 4), epoch_text=EPOCH_OK, doc_text=doc,
                      ws_end="2026-11-04")
    ok = L.check_clock(dt.date(2026, 11, 5), epoch_text=EPOCH_OK, doc_text=doc,
                       ws_end="2026-11-04")
    assert ok["world_series_last_game"] == "2026-11-04" and ok["step_z_entry"] == "2026-10-03"
    assert ok["not_waited"] == ["5e", "5i-B"]
    assert L.EARLIEST_RUN == dt.date(2026, 11, 2)


def test_the_overlap_list_waits_by_record_or_kill_date(monkeypatch):
    looks = tuple((n, o, c, "2026-12-31") for n, o, c, _k in L.OVERLAP_LOOKS)
    monkeypatch.setattr(L, "OVERLAP_LOOKS", looks)
    monkeypatch.setattr(L.overlap_status, "__defaults__", (None, looks))
    for missing in ALL_RECORDED:
        doc = _doc_with(tuple(x for x in ALL_RECORDED if x != missing))
        with pytest.raises(L.LabRefused, match=re.escape(missing)):
            L.check_clock(OK_DAY, epoch_text=EPOCH_OK, doc_text=doc, ws_end=WS_END)
    # every record present: no wait, and 5e or 5i-B without records never hold it
    assert L.check_clock(OK_DAY, epoch_text=EPOCH_OK, doc_text=_doc_with(ALL_RECORDED),
                         ws_end=WS_END)["today"] == "2026-11-03"


def test_the_registered_overlap_list_and_kill_dates():
    names = [n for n, *_ in L.OVERLAP_LOOKS]
    assert names == list(reg.OVERLAP_WAITED)
    assert tuple(L.NOT_WAITED) == reg.OVERLAP_NOT_WAITED
    assert all(k == "2026-10-31" for *_x, k in L.OVERLAP_LOOKS)
    # with the registered kill dates, no record is needed after 2026-10-31
    st = L.overlap_status(OK_DAY, _doc_with(()))
    assert all(v["satisfied"] and not v["recorded"] for v in st.values())
    st = L.overlap_status(dt.date(2026, 10, 30), _doc_with(("5c-B",)))
    assert st["5c-B"]["recorded"] and st["5c-B"]["satisfied"]
    assert not st["5k"]["satisfied"]


def test_the_overlap_reader_finds_the_live_records():
    """On the real document: 5c-B and 5c-C carry their 2026-10-08 results."""
    st = L.overlap_status(dt.date(2026, 10, 9))
    assert st["5c-B"]["recorded"] and st["5c-C"]["recorded"]


def test_the_one_run_guard(tmp_path):
    doc = _doc_with(ALL_RECORDED)
    art = tmp_path / "game_intensity_eval.json"
    L.check_one_run(art, doc)                                   # nothing yet: allowed
    art.write_text(json.dumps({"stage1": {"status": "crashed"}}), encoding="utf-8")
    with pytest.raises(L.LabRefused, match="stage-1 block"):
        L.check_one_run(art, doc)
    art.write_text("{not json", encoding="utf-8")
    with pytest.raises(L.LabRefused, match="does not parse"):
        L.check_one_run(art, doc)
    art.unlink()
    with pytest.raises(L.LabRefused, match="Stage 1 result"):
        L.check_one_run(art, _doc_with(ALL_RECORDED, stage1=True))
    assert L.ARTIFACT == ROOT / "data" / "game_intensity_eval.json"


def test_the_dry_run_and_counts_refuse_data(tmp_path):
    with pytest.raises(L.LabRefused, match="data/"):
        L.check_out_path(ROOT / "data" / "game_intensity_eval.json")
    assert L.check_out_path(tmp_path / "x.json") == (tmp_path / "x.json").resolve()
    assert L.main(["--dry-run", "--out", str(ROOT / "data" / "x.json")]) == 2


def test_a_2026_game_and_2020_are_refused():
    for s in (2026, 2027):
        with pytest.raises(L.LabRefused, match="2026"):
            L.season_games({"rows": []}, s)
    with pytest.raises(L.LabRefused, match="2020"):
        L.season_games({"rows": []}, 2020)
    row = {"game_pk": 1, "season": "2025", "date": "2026-01-02", "home_org": "NYY",
           "away_org": "BOS", "home_runs": 1, "away_runs": 0, "innings": 9}
    with pytest.raises(L.LabRefused, match="2026"):
        L.season_games({"rows": [row]}, 2025)


def test_the_run_takes_the_registered_parameters_only():
    L.check_params(dict(L.REGISTERED_PARAMS))
    with pytest.raises(L.LabRefused):
        L.check_params(dict(L.FIXTURE_PARAMS))
    assert L.REGISTERED_PARAMS["n_sims"] == ic.SIMS == 20_000
    assert L.REGISTERED_PARAMS["seed"] == ic.SEED == 12345
    assert L.REGISTERED_PARAMS["twin_draws"] == 200


def test_the_registered_frame():
    assert L.SEASONS == (2018, 2019, 2021, 2022, 2023, 2024, 2025)
    assert L.FIT_SEASONS == (2018, 2019, 2021, 2022)
    assert L.GRADE_SEASONS == (2023, 2024, 2025)
    assert L.POSTSEASONS_INT_B1 == tuple(range(2000, 2018))
    assert L.TYPE_MEMBERS == ("rotation_quality", "bullpen_quality", "contact", "power")
    assert set(L.TYPE_EXCLUDED) == {"bullpen_usage", "team_defense"}
    assert len(L.ARCH_MEMBERS) == 6
    assert L.DQ_PRIOR_GAMES == 70 and L.TYPE_MIN_GAMES == 20
    assert L.TWIN_DRAWS == 200 and L.TWIN_PERCENTILE == 95.0 and L.ALPHA == 0.05


def test_only_the_lab_reads_the_postseason_feed_directory():
    allowed = {"tools/intensity_fetch.py", "tools/intensity_lab.py"}
    hits = set()
    for base, pat in ((ROOT, "*.py"), (ROOT / "tools", "*.py"), (ROOT / "assets", "*.js")):
        for p in base.glob(pat):
            if p.name.startswith("test_"):
                continue
            # a path built to the directory (a docstring that names it is not a reader)
            if re.search(r"[\"']win_prob_post[\"'/]",
                         p.read_text(encoding="utf-8", errors="replace")):
                hits.add(p.relative_to(ROOT).as_posix())
    assert hits <= allowed, hits
    assert L.POST_FEED_DIR == ROOT / ".cache" / "win_prob_post"
    src = LAB_PATH.read_text(encoding="utf-8")
    assert '"win_prob"' not in src and "'win_prob'" not in src   # never builds that path


# ---------------------------------------------------------------------------
# G_REF
# ---------------------------------------------------------------------------
def test_g_ref_equals_the_recorded_literal():
    rec = L.G_REF_RECORD
    assert ic.G_REF == rec["value"] == 0.01158
    assert round(rec["unrounded"], 5) == rec["value"]
    assert rec["seed"] == ic.G_REF_SEED == 20260930
    assert rec["sims"] == ic.G_REF_SIMS == 300_000
    sec = reg._norm(reg._section())
    m = re.search(r"### G_REF recorded \(amendment, (\d{4}-\d{2}-\d{2})\)", reg._section())
    assert m and m.group(1) == rec["recorded"]
    assert f"G_REF recorded: {ic.G_REF}" in sec
    assert f"300,000 simulations at seed {ic.G_REF_SEED}" in sec
    assert "It replaces the draft value 0.01145" in sec
    assert f"= {math.log1p(2 / ic.G_REF):.3f}" in sec
    assert "### The stage-1 lab's pinned choices (amendment, 2026-10-09)" in reg._section()
    # the default reference is the frozen one
    assert ic.stakes_score(ic.G_REF) == pytest.approx(math.log(2) / math.log1p(2 / ic.G_REF))


def test_the_g_ref_league_is_the_registered_one():
    pairs = L.synthetic_schedule()
    assert len(pairs) == 2430
    per = {o: {"division": 0, "league": 0, "interleague": 0} for o in L.ORGS}
    for h, a in pairs:
        per[h][L.game_kind(h, a)] += 1
        per[a][L.game_kind(h, a)] += 1
    assert all(v == ic.G_REF_SCHEDULE for v in per.values())
    od = L.opening_day_games(pairs)
    assert {k: len(v) for k, v in od.items()} == {"division": 12, "league": 14,
                                                   "interleague": 15}
    for idx in od.values():
        clubs = [c for k in idx for c in pairs[k]]
        assert len(clubs) == len(set(clubs))
    # deterministic at a fixed seed, and the same computation the record came from
    a = L.compute_g_ref(n_sims=60)
    b = L.compute_g_ref(n_sims=60)
    assert a == b and a["seed"] == 20260930 and a["home_edge"] == ic.HOME_EDGE
    assert a["mix"]["division"] == pytest.approx(52 / 162)


# ---------------------------------------------------------------------------
# fixture arithmetic, family by family
# ---------------------------------------------------------------------------
def test_offset_logistic_is_the_maximum_likelihood():
    rng = np.random.default_rng(3)
    n = 4000
    off = rng.normal(0, 0.4, n)
    x = rng.normal(0, 1, n)
    y = (rng.random(n) < L._sigmoid(off + 0.3 * x)).astype(float)
    b = L.fit_offset_logistic(off, x, y)
    p = L._sigmoid(off + b[0] * x)
    assert abs(float(((y - p) * x).sum())) < 1e-8          # the score equation
    assert 0.2 < b[0] < 0.4
    assert L.fit_offset_logistic(off, np.zeros(n), y)[0] == 0.0
    two = L.fit_offset_logistic(off, np.column_stack([x, np.zeros(n)]), y)
    assert two[1] == 0.0 and two[0] == pytest.approx(b[0])


def test_paired_delta_is_betting_models_form():
    import betting_model
    rng = np.random.default_rng(5)
    inc, chal = rng.random(50), rng.random(50)
    mine = L.paired_delta(inc, chal)
    theirs = betting_model._paired_delta(list(inc), list(chal))
    for k in ("n", "delta", "sd", "t", "lb95"):
        assert mine[k] == theirs[k], k
    assert L.paired_delta([1.0], [0.0])["t"] is None


def test_cr1_mean_hand_computed():
    d = np.array([1.0, 2.0, 3.0, 6.0])
    cl = np.array(["a", "a", "b", "b"])
    out = L.cr1_mean(d, cl)
    # dbar 3; S_a = (1-3)+(2-3) = -3, S_b = 0+3 = 3; SE = sqrt(2 x 18) / 4 = 1.5
    assert out["mean"] == 3.0 and out["G"] == 2 and out["df"] == 1
    assert out["se"] == pytest.approx(1.5) and out["t"] == pytest.approx(2.0)
    from scipy import stats
    assert out["p_two_sided"] == pytest.approx(2 * stats.t.sf(2.0, 1))


def test_holm_step_down():
    h = L.holm({"a": 0.01, "b": 0.04, "c": 0.02})
    assert h["a"]["reject"] and h["a"]["threshold"] == pytest.approx(0.05 / 3)
    assert h["c"]["reject"] and h["c"]["threshold"] == pytest.approx(0.025)
    assert h["b"]["reject"] and h["b"]["threshold"] == pytest.approx(0.05)
    h = L.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert h["a"]["reject"] and not h["c"]["reject"] and not h["b"]["reject"]   # stops at 0.025
    h = L.holm({"a": 0.02, "b": 0.001})
    assert h["b"]["reject"] and h["a"]["reject"]
    h = L.holm({"a": 0.03, "b": 0.03})
    assert not h["a"]["reject"] and not h["b"]["reject"]      # the first step fails at 0.025
    h = L.holm({"a": None, "b": 0.001})
    assert h["b"]["reject"] and not h["a"]["reject"]


def test_the_focus_set_is_inclusive_at_005():
    assert ic.FOCUS_THRESHOLD == 0.05
    ds = np.array([0.05, -0.05, 0.0499999, -0.2])
    assert (np.abs(ds) >= ic.FOCUS_THRESHOLD).tolist() == [True, True, False, True]


def test_the_panel_beta_equals_dummy_ols_and_cr1_matches():
    rng = np.random.default_rng(9)
    rows = []
    clubs = ("NYY", "BOS", "TBR", "TOR")
    for i in range(240):
        h, a = rng.choice(clubs, 2, replace=False)
        rows.append({"season": 2023 + i % 2, "home": h, "away": a, "venue": h,
                     "month": 4 + i % 3, "date": f"d{i // 4}", "S": float(rng.random())})
    D = L.fe_design(rows)
    S = np.array([r["S"] for r in rows])
    y = 8 + D @ rng.normal(0, 1, D.shape[1]) + 0.7 * S + rng.normal(0, 1, len(rows))
    fit = L.panel_fit(L.Residualizer(D), y, S, [r["date"] for r in rows])
    full = np.linalg.lstsq(np.column_stack([D, S]), y, rcond=None)[0]
    assert fit["beta"][0] == pytest.approx(full[-1], abs=1e-9)
    # CR1 by hand on the FWL residuals
    res = L.Residualizer(D)
    rx, ry = res(S), res(y)
    e = ry - fit["beta"][0] * rx
    dates = np.array([r["date"] for r in rows])
    G = len(set(dates))
    sg = np.array([float((rx[dates == g] * e[dates == g]).sum()) for g in sorted(set(dates))])
    V = G / (G - 1) * float((sg ** 2).sum()) / float((rx ** 2).sum()) ** 2
    assert fit["t"][0] == pytest.approx(fit["beta"][0] / math.sqrt(V))
    # one club-season column per club entered for both participants
    assert all(D[j].sum() == 4.0 for j in range(len(rows)))


def test_the_did_is_a_difference_in_differences():
    rng = np.random.default_rng(1)
    n = 800
    A = rng.random(n) < 0.3
    T = rng.random(n) < 0.2
    r = rng.normal(0, 1, n) + 0.5 * (A & T)
    g = np.arange(n) // 2
    out = L.did_fit(r, A, T, g)
    want = ((r[A & T].mean() - r[A & ~T].mean()) - (r[~A & T].mean() - r[~A & ~T].mean()))
    assert out["did"] == pytest.approx(want)
    assert out["G"] == n // 2 and out["t"] is not None
    assert L.did_fit(r, np.zeros(n, bool), T, g)["did"] is None


def test_wilson_and_the_dq_literal():
    lo, hi = L.wilson(15, 23)
    assert (round(lo, 4), round(hi, 4)) == (0.4489, 0.8119)
    assert L.wilson(0, 0) is None
    # q = RD / (G + 70): RD/G x G/(G + 70)
    games = [{"pk": 1, "season": 2023, "date": "2023-04-01", "home": "NYY", "away": "BOS",
              "hr": 5, "ar": 1, "innings": 9, "home_sp": None, "away_sp": None,
              "venue": None, "known_on": "2023-04-01", "resumed": False},
             {"pk": 2, "season": 2023, "date": "2023-04-02", "home": "NYY", "away": "BOS",
              "hr": 2, "ar": 3, "innings": 9, "home_sp": None, "away_sp": None,
              "venue": None, "known_on": "2023-04-02", "resumed": False}]
    params = dict(L.FIXTURE_PARAMS, n_sims=4)
    rows, _clubs, _c = L.season_features(games, None, 2023, params, g_ref=ic.G_REF)
    second = [r for r in rows if r["pk"] == 2][0]
    assert second["q_h"] == pytest.approx(4 / 71) and second["q_a"] == pytest.approx(-4 / 71)
    first = [r for r in rows if r["pk"] == 1][0]
    assert first["q_h"] == 0.0 and first["p_base"] == pytest.approx(
        ic.elo_win_prob(1500, 1500, 24))
    assert second["A"] is None and second["A_null"] == "unannounced"


def test_elo_snapshot_is_strictly_before_the_date():
    src = L.synthetic_fixture()
    games, _ = L.season_games(src.finals(2023), 2023)
    plain = [g for g in games if not g["resumed"]]
    rows, _clubs, _c = L.season_features(plain, None, 2023, dict(L.FIXTURE_PARAMS, n_sims=2),
                                         g_ref=ic.G_REF)
    compact = [{"game_pk": g["pk"], "date": g["date"], "home_org": g["home"],
                "away_org": g["away"], "home_runs": g["hr"], "away_runs": g["ar"]}
               for g in plain]
    for r in rows[::37]:
        rt = ic.elo_ratings_before(compact, r["date"])
        want = ic.elo_win_prob(rt.get(r["home"], 1500.0), rt.get(r["away"], 1500.0), 24)
        assert r["p_base"] == pytest.approx(want, abs=1e-12)


def test_row_rules_and_stated_nulls():
    src = L.synthetic_fixture()
    games, c = L.season_games(src.finals(2019), 2019)
    assert c["null_no_elo_outside_field"] == 1 and c["resumed"] == 1
    res = [g for g in games if g["resumed"]][0]
    assert res["known_on"] > res["date"]
    assert L.row_rule(res) == "drop_resumed"
    assert L.row_rule(dict(res, resumed=False, innings=7)) == "drop_innings_below_9"
    assert L.row_rule(dict(res, resumed=False, innings=None)) == "drop_no_innings"
    assert L.row_rule(dict(res, resumed=False, innings=10)) is None


def test_type_z_is_standardized_across_the_clubs_playing_that_date():
    clubs = {"2023-07-01": {"NYY": {"power": 0.04}, "BOS": {"power": 0.02},
                            "TBR": {"power": None}}}
    z = L._date_z(clubs, "power")["2023-07-01"]
    assert set(z) == {"NYY", "BOS"} and z["NYY"] == pytest.approx(1.0)
    assert L._club_types({"games": 19}, 20)["power"] is None
    t = L._club_types({"games": 20, "sp_bf": 100, "sp_k": 25, "sp_bb": 5, "rp_bf": 50,
                       "rp_k": 10, "rp_bb": 10, "pa": 200, "k": 40, "hr": 6}, 20)
    assert t == {"rotation_quality": 0.2, "bullpen_quality": 0.0, "contact": -0.2,
                 "power": 0.03}


# ---------------------------------------------------------------------------
# the twin draws
# ---------------------------------------------------------------------------
def test_the_twin_draws_are_the_registered_ones():
    seeds = list(L.twin_rngs())
    assert [k for k, _ in seeds] == list(range(200))
    dates = ["d1", "d1", "d2", "d2", "d2", "d3"]
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    groups = L._date_groups(dates)
    for k, rng in L.twin_rngs(5):
        out = L.permute_slots(vals, groups, rng)
        for _d, idx in groups:
            assert sorted(out[idx]) == sorted(vals[idx])       # within the date only
        # the same draw again from default_rng(k)
        again = L.permute_slots(vals, groups, np.random.default_rng(k))
        assert out.tolist() == again.tolist()
    first = L.permute_slots(vals, groups, np.random.default_rng(0))
    r0 = np.random.default_rng(0)
    want = vals.copy()
    for _d, idx in groups:
        want[idx] = vals[idx[r0.permutation(idx.size)]]
    assert first.tolist() == want.tolist()


def test_the_twin_bar_is_strict():
    twins = list(range(100))
    bar = L.twin_bar(twins)
    assert bar["p95"] == pytest.approx(np.percentile(twins, 95))
    assert not L.beats(bar["p95"], bar)
    assert L.beats(bar["p95"] + 1e-9, bar)
    assert not L.beats(None, bar)
    assert L.twin_bar([None, float("nan")])["p95"] is None


def test_club_value_twins_permute_among_the_clubs_of_the_date():
    clubs = {"2023-07-01": {"NYY": {"power": 1.0}, "BOS": {"power": 2.0},
                            "TBR": {"power": 3.0}},
             "2023-07-02": {"NYY": {"power": 4.0}, "SEA": {"power": 5.0}}}
    out = L._permute_club_values(clubs, "power", np.random.default_rng(0))
    for D in clubs:
        assert sorted(v["power"] for v in out[D].values()) == sorted(
            v["power"] for v in clubs[D].values())
        assert set(out[D]) == set(clubs[D])


# ---------------------------------------------------------------------------
# counts-only mode
# ---------------------------------------------------------------------------
STAT_WORDS = ("mean", "beta", "brier", "log_loss", "delta", "slope", "rate", "improvement",
              "p95", "p_two", "p_holm", "did", "corr", "ci95", "sd")


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}/{i}")
    else:
        yield path, x


def test_counts_only_mode_prints_no_statistic(tmp_path):
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert L.main(["--counts", "--fixture", "--out", str(tmp_path / "counts.json")]) == 0
    printed = buf.getvalue()
    rep = json.loads(printed)
    assert rep == json.loads((tmp_path / "counts.json").read_text(encoding="utf-8"))
    for path, v in _leaves(rep):
        assert v is None or isinstance(v, (int, str, bool)), (path, v)
        assert not isinstance(v, float), path
        low = path.lower()
        assert not any(f"/{w}" in low or low.endswith(w) for w in STAT_WORDS), path
    assert not re.search(r"\d\.\d", printed), "a decimal number was printed"
    s = rep["seasons"]["2023"]
    assert s["focus_games_by_month"]["6"] == 0 and s["games_by_month"]["6"] == 0
    assert rep["postseason"]["feed_missing"] == 1


# ---------------------------------------------------------------------------
# the reporting path, end to end, with nulls
# ---------------------------------------------------------------------------
def test_the_reporting_path_end_to_end_with_nulls(fixture_run):
    art, out = fixture_run
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(art))
    st = art["stage1"]
    assert st["status"] == "complete" and st["mode"] == "dry_run_fixture"
    assert art["g_ref"] == ic.G_REF and art["construction"] == "ix_v1"
    fam = st["families"]
    assert set(fam) == {"IX-ML", "IX-TOT", "IX-TYPE", "IX-ARCH"}
    assert set(fam["IX-ML"]["holm"]) == {"IX-A", "IX-A2"} and fam["IX-ML"]["m"] == 2
    assert set(fam["IX-TOT"]["holm"]) == {"IX-B"}
    assert set(fam["IX-TYPE"]["holm"]) == set(L.TYPE_MEMBERS)
    assert set(fam["IX-ARCH"]["holm"]) == set(L.ARCH_MEMBERS)
    a = fam["IX-ML"]["IX-A"]
    assert a["twin"]["draws"] == 200 and a["twin"]["draws_used"] >= 190
    assert set(a["criteria"]) == {"c1_focus_brier_t_at_least_1_645", "c2_log_loss_not_worse",
                                  "c3_sign_b_positive", "c4_beats_twin", "c5_beats_control_2"}
    assert a["resolved"] == (all(a["criteria"].values())
                             and fam["IX-ML"]["holm"]["IX-A"]["reject"])
    # nulls: an unannounced probable, a game with no Elo, an empty focus month
    c23 = st["counts"]["seasons"]["2023"]
    assert c23["finals_and_features"]["features_A_null_unannounced"] == 1
    assert c23["finals_and_features"]["null_no_elo_outside_field"] == 1
    assert c23["row_rule_drops"] == {"drop_innings_below_9": 1, "drop_resumed": 1}
    graded = a["focus_by_season_month"]["graded"]["2023"]["6"]
    assert graded == {"games": 0, "focus": 0}
    # seasons with no prior-season archetype source are stated, not filled
    arch = fam["IX-ARCH"]["seasons"]
    assert arch["2018"]["status"] == "no prior-season source"
    assert arch["2021"]["status"] == "no prior-season source"
    assert arch["2019"]["status"] == "read"
    e = st["IX-E"]
    assert e["counts"]["null_no_feed_or_score"] == 1
    assert e["counts"]["null_no_regular_season_source"] >= 1
    assert e["frames"]["int_b1_2000_2017"]["home_minus_elo_price"]["n"] == 0
    assert "verdict" not in json.dumps(e).lower().replace("no verdict", "")
    assert set(fam["IX-TYPE"]["excluded"]) == {"bullpen_usage", "team_defense"}


def test_the_artifact_names_no_dark_column(fixture_run):
    art, _out = fixture_run
    text = json.dumps(art)
    assert not re.search(r'"ix_(?!v\d)', text)
    for col in reg.COLUMNS + reg.FLAGS:
        assert col not in text
    assert "game_intensity_eval" not in json.dumps(L.REGISTERED_PARAMS)


def test_the_result_block_appends_once_and_keeps_crlf(fixture_run, tmp_path):
    art, _out = fixture_run
    doc = tmp_path / "doc.md"
    doc.write_bytes(_doc_with(ALL_RECORDED).replace("\n", "\r\n").encode("utf-8"))
    L.append_result(doc, art)
    raw = doc.read_bytes().decode("utf-8")
    assert "\r\n" in raw and "\n" not in raw.replace("\r\n", "")
    sec = L.section_text(raw)
    assert L.STAGE1_HEADING_RE.search(sec)
    assert L.result_heading(art).startswith("### Stage 1 result (run ")
    with pytest.raises(L.LabRefused):
        L.append_result(doc, art)
    for t in (L.result_text(art), raw):
        assert EM_DASH not in t and EN_DASH not in t


def test_a_crash_after_the_first_write_blocks_a_rerun(tmp_path, monkeypatch):
    out = tmp_path / "game_intensity_eval.json"

    def boom(*_a, **_k):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(L, "family_tot", boom)
    with pytest.raises(RuntimeError):
        L.run_stage1(L.synthetic_fixture(), out, mode="dry_run_fixture",
                     params=dict(L.FIXTURE_PARAMS, twin_draws=3), log=lambda *_a: None)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["stage1"]["status"] == "crashed" and "never rerun" in doc["stage1"]["protocol"]
    with pytest.raises(L.LabRefused):
        L.check_one_run(out, _doc_with(ALL_RECORDED))


def test_no_dashes_or_banned_words_in_the_lab():
    src = LAB_PATH.read_text(encoding="utf-8")
    assert EM_DASH not in src and EN_DASH not in src
    for w in ("leverage", "seamless", "robust", "delve", "comprehensive", "crucial",
              "essential", "powerful", "showcase", "utilize", "unlock", "elevate",
              "cutting-edge", "tapestry", "meticulous", "underscore", "harness"):
        assert not re.search(r"\b" + w + r"\b", src, flags=re.I), w


def test_the_registry_row_is_registered_and_unvalidated():
    rows = {m["model_id"]: m for m in json.loads(
        (ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))["models"]}
    row = rows[L.REGISTRY_ROW]
    assert row["verdict"] == "unvalidated"
    if not L.ARTIFACT.exists():
        assert row["eval_artifact"] is None
    assert "G_REF 0.01158" in row["champion"]
    assert "betting_model_eval" not in json.dumps(row)
