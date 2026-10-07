"""tools/b4_availability_look.py: the 5c-B and 5c-C look harness, on synthetic
fixtures only. No test here reads the real vintage store, the real game cache
or any real column value; 5c rule 1 and both sections forbid a dry run of the
fit on the real store before the look."""
from __future__ import annotations

import importlib.util
import json
import math
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "b4_availability_look", ROOT / "tools" / "b4_availability_look.py")
b4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b4)

import betting_model as bm            # noqa: E402
import leaderboard_vintages as lv     # noqa: E402

ORGS = ["BAL", "BOS", "NYY", "TBR", "TOR", "CLE"]


# ---------------------------------------------------------------------------
# the refusals
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("d", ["2026-09-28", "2026-10-04", "2026-11-01", "2026-10-07",
                               "2026-10-23", None])
def test_date_refusal_refuses(d):
    with pytest.raises(b4.LookRefused):
        b4.check_b4_look_date(d)


@pytest.mark.parametrize("d", ["2026-10-05", "2026-10-08", "2026-10-31"])
def test_date_refusal_admits_the_span(d):
    b4.check_b4_look_date(d)


def test_outcome_fields_are_refused_and_stripped():
    with pytest.raises(b4.OutcomeJoinRefused):
        b4.refuse_outcome_fields([{"game_pk": 1, "date": "2026-09-20", "home_runs": 3}])
    with pytest.raises(b4.OutcomeJoinRefused):
        b4.refuse_outcome_fields(["not a row"])
    rows = b4.feature_rows([{"game_pk": 1, "date": "2026-09-20", "home_org": "NYY",
                             "away_org": "BOS", "home_runs": 3, "away_runs": 2,
                             "innings": 9}])
    assert set(rows[0]) <= b4.ALLOWED_FEATURE_KEYS
    assert "home_runs" not in rows[0]


def test_no_look_before_the_first_day_reads_anything(tmp_path):
    """A run dated before 2026-10-05 is refused before the note, the store or
    the game cache is opened, so z_star_out never meets an outcome field."""
    with pytest.raises(b4.LookRefused):
        b4.run_look("star_out", note_path=tmp_path / "absent.json", out_dir=tmp_path,
                    today=date(2026, 10, 4))
    with pytest.raises(b4.LookRefused):
        b4.run_look("lineup_strength", note_path=tmp_path / "absent.json",
                    out_dir=tmp_path, today=date(2026, 10, 4))


def test_one_look_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(b4, "RECORD_DIR", tmp_path)
    (tmp_path / "5cB_SCORING_BEGAN").write_text("x", encoding="utf-8")
    with pytest.raises(b4.LookRefused, match="no second"):
        b4.run_look("lineup_strength", note_path=tmp_path / "n.json", out_dir=tmp_path,
                    today=date(2026, 10, 8))


def test_store_guard_refuses_another_host_or_dir(tmp_path):
    fake = type("LV", (), {"VINTAGE_DIR": b4.STORE})
    with pytest.raises(b4.StoreRefused):
        b4.check_store(fake, host="deploy-box")
    other = type("LV", (), {"VINTAGE_DIR": tmp_path})
    with pytest.raises(b4.StoreRefused):
        b4.check_store(other, host="NOAH-PC")
    assert b4.check_store(fake, host="noah-pc")["host"] == "noah-pc"


# ---------------------------------------------------------------------------
# the arithmetic
# ---------------------------------------------------------------------------
def test_split_date_is_floor_of_the_half_span():
    assert b4.split_date(["2026-09-08", "2026-09-27"])["M"] == "2026-09-17"
    assert b4.split_date(["2026-09-06", "2026-09-19", "2026-09-10"])["M"] == "2026-09-12"
    assert b4.split_date(["2026-09-06", "2026-09-27"])["M"] == "2026-09-16"
    assert b4.split_date([])["M"] is None


def test_paired_stat_is_the_written_form():
    d = [0.01, -0.02, 0.03, 0.00, 0.02]
    st = b4.paired_stat(d)
    mean = sum(d) / 5
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / 4)
    assert st["mean"] == pytest.approx(mean)
    assert st["sd"] == pytest.approx(sd)
    assert st["t"] == pytest.approx(mean / (sd / math.sqrt(5)))
    assert st["lb95"] == pytest.approx(mean - 1.645 * sd / math.sqrt(5))
    zero = b4.paired_stat([0.1, 0.1, 0.1])
    assert zero["runnable"] is False and zero["t"] is None and zero["se"] is None
    assert b4.paired_stat([0.1])["runnable"] is False


def test_paired_delta_fixture_check_reports_the_divisor():
    fx = b4.paired_delta_fixture_check(bm)
    assert fx["agree"]["delta"] is True
    # the helper divides by n at HEAD and at the pinned commit; the check says so
    assert fx["helper_agrees"] is False
    assert "n-1" in fx["note"]


def _rows(xs, cs, lam=4.5, noise=None, xo=None):
    rnd = random.Random(7)
    out = []
    for i, z in enumerate(xs):
        zo = xo[i] if xo else 0.0
        mu = lam + cs[0] * z + (cs[1] * zo if len(cs) > 1 else 0.0)
        out.append({"lam": lam, "runs": mu + (noise or 0.0) * rnd.gauss(0, 1),
                    "z_s": z, "z_o": zo})
    return out


def test_one_term_fit_recovers_c_without_intercept():
    xs = [(-1) ** i * (i % 5) / 2.0 for i in range(60)]
    xbar = sum(xs) / len(xs)
    rows = _rows(xs, [0.4])
    f = b4.fit_terms(rows, 1)
    assert f["ok"]
    # runs - lam = 0.4 z = 0.4 (x + xbar): the no-intercept slope on centred x
    exp = sum((z - xbar) * 0.4 * z for z in xs) / sum((z - xbar) ** 2 for z in xs)
    assert f["c"] == pytest.approx(exp)
    assert f["zbar"] == pytest.approx(xbar)


def test_two_term_fit_and_its_refusals():
    rnd = random.Random(3)
    zs = [rnd.gauss(0, 1) for _ in range(80)]
    zo = [rnd.gauss(0, 1) for _ in range(80)]
    rows = _rows(zs, [-0.3, 0.2], xo=zo)
    # make zbar zero so the centring is exact
    zb = sum(zs) / 80
    for r in rows:
        r["runs"] = r["lam"] - 0.3 * (r["z_s"] - zb) + 0.2 * (r["z_o"] - zb)
    f = b4.fit_terms(rows, 2)
    assert f["ok"]
    assert f["c_own"] == pytest.approx(-0.3, abs=1e-9)
    assert f["c_opp"] == pytest.approx(0.2, abs=1e-9)
    flat = [{"lam": 4, "runs": 5, "z_s": 1.0, "z_o": 1.0} for _ in range(10)]
    assert b4.fit_terms(flat, 1)["ok"] is False
    assert b4.fit_terms(flat, 2)["ok"] is False
    collinear = [{"lam": 4, "runs": 5, "z_s": z, "z_o": z} for z in zs]
    assert b4.fit_terms(collinear, 2)["ok"] is False
    assert b4.fit_terms([{"lam": 4, "runs": 5, "z_s": None, "z_o": 0.1}], 1)["ok"] is False


def test_shifts_follow_the_registered_candidates():
    f1 = {"zbar": 0.1, "c": 0.5}
    assert b4.shifts({}, f1, 1, 1.1, -0.9) == pytest.approx((0.5, -0.5))
    f2 = {"zbar": 0.0, "c_own": -0.2, "c_opp": 0.3}
    dh, da = b4.shifts({}, f2, 2, 1.0, 2.0)
    assert dh == pytest.approx(-0.2 * 1.0 + 0.3 * 2.0)
    assert da == pytest.approx(-0.2 * 2.0 + 0.3 * 1.0)


# ---------------------------------------------------------------------------
# the seam and the identity check
# ---------------------------------------------------------------------------
def _teams(z_ls=None, z_so=None):
    off = {o: 95 + 2 * i for i, o in enumerate(ORGS)}
    rots = {o: 100 + (i % 3) for i, o in enumerate(ORGS)}
    pens = {o: 99 + (i % 2) for i, o in enumerate(ORGS)}
    sip = {o: 800.0 for o in ORGS}
    rip = {o: 500.0 for o in ORGS}
    ex = {o: {c: None for c in bm.DARK_TEAM_COLUMNS} for o in ORGS}
    for i, o in enumerate(ORGS):
        ex[o]["lineup_strength"] = None if z_ls is None else z_ls[i]
        ex[o]["star_out"] = None if z_so is None else z_so[i]
    return bm._assemble_team_inputs(off, rots, pens, sip, rip, ex)


PARAMS = {"coeffs": {"b0": 4.3, "b1": 0.2, "b2": -0.25, "b3": 0.6, "b4": 0.1},
          "tie_home": 0.52, "diff_shrink": 0.9, "home_adj": 0.05,
          "runline_split": (0.2, 0.6)}


def test_seam_at_zero_equals_game_probabilities_to_5_places():
    teams = _teams([0.30, 0.31, 0.32, 0.33, 0.34, 0.35])
    parks = {o: 1.0 + 0.01 * i for i, o in enumerate(ORGS)}
    games = [{"game_pk": i, "date": "2026-09-20", "home_org": h, "away_org": a}
             for i, (h, a) in enumerate([(h, a) for h in ORGS for a in ORGS if h != a])]
    res = b4.identity_check(bm, games, PARAMS, resolve=lambda g: (teams, {}, parks))
    assert res["pass"] and res["n_checked"] == 30 and res["n_mismatch"] == 0


def test_seam_shift_moves_and_clamps():
    s0 = b4.seam(bm, 4.0, 4.0, 0.5, None)
    s1 = b4.seam(bm, 4.0, 4.0, 0.5, None, 0.5, -0.5)
    assert s1["p_home"] > s0["p_home"]
    s2 = b4.seam(bm, 9.4, 1.6, 0.5, None, 1.0, -1.0)
    assert (s2["lam_home"], s2["lam_away"]) == (9.5, 1.5)


# ---------------------------------------------------------------------------
# the twins
# ---------------------------------------------------------------------------
def _recs(n_days=6, z=None):
    out, pk = [], 100
    for d in range(n_days):
        day = f"2026-09-{10 + d:02d}"
        vint = f"2026-09-{9 + d:02d}"
        for h, a in (("BAL", "BOS"), ("NYY", "TBR"), ("TOR", "CLE")):
            zz = z or {o: (ORGS.index(o) + d) / 10.0 for o in ORGS}
            out.append({"game_pk": pk, "date": day, "vintage": vint, "home_org": h,
                        "away_org": a, "z_home": zz[h], "z_away": zz[a],
                        "lam_home": 4.5, "lam_away": 4.2, "home_runs": (pk % 7),
                        "away_runs": (pk % 5), "bucket": "dated_value",
                        "vintage_age_days": 1})
            pk += 1
    return out


def test_twin_a_permutes_within_each_vintage_with_seed_k():
    recs = _recs()
    vc = b4._vintage_z_map(recs)
    m0 = b4.twin_a_maps(recs, vc, 0)
    m0b = b4.twin_a_maps(recs, vc, 0)
    m1 = b4.twin_a_maps(recs, vc, 1)
    assert m0 == m0b and m0 != m1
    for vd, perm in m0.items():
        assert sorted(perm.values()) == sorted(v for v in vc[vd].values())
        assert sorted(perm) == sorted(vc[vd])


def test_twin_b_keeps_each_club_inside_its_half():
    recs = _recs()
    fit, graded = recs[:9], recs[9:]
    m = b4.twin_b_maps(fit, graded, 0)
    assert m == b4.twin_b_maps(fit, graded, 0)
    for half in (fit, graded):
        for org in ORGS:
            orig = sorted([r["z_home"] for r in half if r["home_org"] == org]
                          + [r["z_away"] for r in half if r["away_org"] == org])
            perm = sorted(m[(r["game_pk"], org)] for r in half
                          if org in (r["home_org"], r["away_org"]))
            assert orig == perm
    const = _recs(z={o: 0.5 for o in ORGS})
    assert b4.constant_z_clubs(const) == sorted(ORGS)


def test_twin_bar_is_strictly_above_the_190th_smallest():
    recs = _recs(n_days=8)
    fit, graded = recs[:12], recs[12:]
    tw = b4.run_twin(bm, "A", fit, graded, 1, PARAMS, {}, cand_mean=1e9)
    assert tw["runnable"] and tw["n"] == 200
    assert tw["bar_190th_smallest"] == sorted(tw["means"])[189]
    assert tw["beaten"] is True and tw["candidate_rank"] == 200
    tie = b4.run_twin(bm, "A", fit, graded, 1, PARAMS, {},
                      cand_mean=sorted(tw["means"])[189])
    assert tie["beaten"] is False


# ---------------------------------------------------------------------------
# the buckets, on a synthetic store
# ---------------------------------------------------------------------------
COLS = ["offense_plus", "rotation_plus", "bullpen_plus", "starter_ip", "relief_ip",
        "lineup_strength", "star_out"]


def _write_vintage(store, d, *, captured=None, prov="live", ls=0.320, so=1,
                   null_org=None, as_of=None):
    teams = {}
    for i, o in enumerate(ORGS):
        teams[o] = [95.0 + i, 100.0, 99.0, 800.0, 500.0,
                    None if o == null_org else ls + 0.001 * i,
                    None if o == null_org else (so + i) % 3]
    rec = {"schema": 5, "vintage_date": d, "covers_through": d, "season": "2026",
           "captured_at": captured or f"{d}T18:00:00+00:00",
           "provenance": {"source": prov}, "team_columns": COLS, "teams": teams,
           "pitcher_columns": ["plus", "ip_per_gs", "org", "role"], "pitchers": {},
           "parks": {o: 1.0 for o in ORGS},
           "sources": {"hitter_leaderboards.json": {"as_of": as_of or d}},
           "feature_basis": {"lineup_strength": {"basis": "mean projected year-1 wOBA",
                                                 "n": 6},
                             "star_out": {"basis": "top-5 projected players", "n": 6}}}
    (store / f"{d}.json").write_text(json.dumps(rec), encoding="utf-8")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = tmp_path / "leaderboard_vintages"
    s.mkdir()
    monkeypatch.setattr(lv, "VINTAGE_DIR", s)
    lv.reset_cache()
    bm.reset_vintage_cache()
    yield s
    lv.reset_cache()
    bm.reset_vintage_cache()


def _games(dates):
    out, pk = [], 1
    for d in dates:
        for h, a in (("BAL", "BOS"), ("NYY", "TBR"), ("TOR", "CLE")):
            out.append({"game_pk": pk, "date": d, "home_org": h, "away_org": a,
                        "home_runs": 4, "away_runs": 3, "season": "2026"})
            pk += 1
    return out


def test_star_out_buckets_in_the_registered_order(store):
    _write_vintage(store, "2026-09-03")                                     # pre-change
    _write_vintage(store, "2026-09-04")                                     # unconfirmed
    _write_vintage(store, "2026-09-05")                                     # dated value
    _write_vintage(store, "2026-09-06", captured="2026-09-09T10:00:00+00:00")  # late
    _write_vintage(store, "2026-09-07", null_org="BOS")                     # stated null
    _write_vintage(store, "2026-09-19")                                     # stamp missing
    _write_vintage(store, "2026-09-24", captured="2026-09-24T18:00:00+00:00")  # post-retrain
    games = _games(["2026-09-04", "2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08",
                    "2026-09-20", "2026-09-25"])
    cl = b4.classify_games(bm, lv, "star_out", games, store=store)
    by = {}
    for g in cl["games"]:
        by.setdefault(g["date"], []).append(g["bucket"])
    assert set(by["2026-09-04"]) == {"pre_change_ranking_basis"}
    assert set(by["2026-09-05"]) == {"basis_unconfirmed"}
    assert set(by["2026-09-06"]) == {"dated_value"}
    assert set(by["2026-09-07"]) == {"not_present_night"}
    assert sorted(by["2026-09-08"]) == ["dated_value", "dated_value", "stated_null"]
    assert set(by["2026-09-20"]) == {"stamp_missing"}
    assert set(by["2026-09-25"]) == {"post_retrain"}
    for g in cl["games"]:
        assert "home_runs" not in g and "star_out" not in g


def test_lineup_strength_git_stamp_and_stamp_missing(store):
    _write_vintage(store, "2026-09-07")
    _write_vintage(store, "2026-09-13")
    _write_vintage(store, "2026-09-19")
    _write_vintage(store, "2026-09-24")
    _write_vintage(store, "2026-09-26", as_of="2026-09-25")
    stamps = {"2026-09-07": [{"commit": "7cd5f572", "applied": True, "skipped": []}],
              "2026-09-24": [{"commit": "1b20dc2a", "applied": True, "skipped": ["NYY"]}],
              "2026-09-25": [{"commit": "3f449c5c", "applied": False, "skipped": []}]}
    games = _games(["2026-09-08", "2026-09-14", "2026-09-20", "2026-09-25", "2026-09-27"])
    cl = b4.classify_games(bm, lv, "lineup_strength", games, store=store,
                           board_stamps=stamps)
    got = {(g["date"], g["home_org"]): (g["bucket"], tuple(g.get("sub") or ()))
           for g in cl["games"]}
    assert got[("2026-09-08", "BAL")] == ("dated_value",
                                          ("filter_flag_unrecorded", "stamped_from_git"))
    assert got[("2026-09-14", "BAL")] == ("dated_value", ("stamp_late",))
    assert got[("2026-09-20", "BAL")][0] == "stamp_missing"
    assert got[("2026-09-25", "NYY")] == ("pre_change_membership", ("skipped_club",))
    assert got[("2026-09-25", "BAL")] == ("dated_value", ("stamped_from_git",))
    assert got[("2026-09-27", "BAL")] == ("pre_change_membership", ("board_applied_false",))


def test_a_record_stamp_stops_the_run(store):
    _write_vintage(store, "2026-09-20")
    p = store / "2026-09-20.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["feature_basis"]["star_out"]["basis"] += "; bundle_sha256 abc"
    p.write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()
    with pytest.raises(b4.StoreRefused):
        b4.classify_games(bm, lv, "star_out", _games(["2026-09-21"]), store=store)


def test_counts_report_reads_nulls_only_and_computes_m(store):
    for d in ("2026-09-05", "2026-09-06", "2026-09-07", "2026-09-09"):
        _write_vintage(store, d)
    games = _games(["2026-09-06", "2026-09-07", "2026-09-08", "2026-09-11"])
    rep = b4.counts_report(bm, lv, "star_out", games, store=store)
    assert rep["split"] == {"F": "2026-09-06", "L": "2026-09-11", "M": "2026-09-08"}
    assert rep["n_fit"] == 6 and rep["n_graded"] == 6
    assert rep["floors"] == {"nights": False, "fit": False, "graded": False}
    assert rep["step1_counts_pass"] is False
    assert rep["clock"]["nights"]["n_present"] == 4
    assert rep["vintage_age"]["n_age_2_plus"] == 3


def test_present_night_rule():
    rec = {"captured_at": "2026-09-11T03:00:00+00:00", "provenance": {"source": "live"},
           "vintage_date": "2026-09-10"}
    assert b4.is_present_night("2026-09-10", rec, lv)
    rec2 = dict(rec, captured_at="2026-09-12T00:00:01+00:00")
    assert not b4.is_present_night("2026-09-10", rec2, lv)
    rec3 = dict(rec, provenance={"source": "backfill"})
    assert not b4.is_present_night("2026-09-10", rec3, lv)
    assert not b4.is_present_night("2026-09-10", None, lv)


def test_store_hash_is_over_sorted_name_and_digest_pairs(tmp_path):
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.json").write_text("[]", encoding="utf-8")
    h = b4.store_hash(tmp_path)
    import hashlib
    exp = hashlib.sha256()
    for n in ("a.json", "b.json"):
        exp.update(f"{n}\t{hashlib.sha256((tmp_path / n).read_bytes()).hexdigest()}\n"
                   .encode())
    assert h["sha256"] == exp.hexdigest() and h["n_files"] == 2


# ---------------------------------------------------------------------------
# leg 1 helpers
# ---------------------------------------------------------------------------
def test_star_top5_ranking_and_dated_counts():
    vets = [{"mlbam": 10 + i, "team": "New York Yankees", "warY1Champ": w}
            for i, w in enumerate([5, 4, 4, 3, 2, 1])]
    vets.append({"mlbam": 99, "team": "Boston Red Sox", "warY1Champ": 3})
    top = b4.star_top5(vets, lv)
    assert top == {"NYY": [10, 11, 12, 13, 14]}

    def status(tid, d):
        if tid == 2:
            return None
        return {10: "D60", 11: "A", 13: "D10"} if d < "2026-09-01" else {10: "A"}
    dated = b4.dated_star_out(top, status, {"NYY": 1, "BOS": 2},
                              ["2026-08-15", "2026-09-02"])
    assert dated == {"2026-08-15": {"NYY": 2}, "2026-09-02": {"NYY": 0}}
    assert b4.leg1_coverage(dated)["ok"] is False


def test_standardize_reads_sd_zero_as_one():
    z = b4.standardize({"A": 2.0, "B": 2.0}, bm)
    assert z == {"A": 0.0, "B": 0.0}


def test_season_end_value_skips_ungraded_vintages(store):
    _write_vintage(store, "2026-09-24", ls=0.300)
    _write_vintage(store, "2026-09-26", ls=0.310, as_of="2026-09-25")
    _write_vintage(store, "2026-09-27", ls=0.330)
    vm = b4.vintage_meta_all(lv, "lineup_strength",
                             {"2026-09-24": [{"applied": True, "skipped": []}],
                              "2026-09-25": [{"applied": True, "skipped": ["BAL"]}]},
                             "2026-09-07", "2026-09-27", store=store)
    vals = b4.season_end_lineup_values(lv, "lineup_strength", vm, store=store)
    assert vals["BOS"] == (pytest.approx(0.311), "2026-09-26")
    assert vals["BAL"] == (pytest.approx(0.300), "2026-09-24")


# ---------------------------------------------------------------------------
# the reporting path, dry run with None values (the crash protocol)
# ---------------------------------------------------------------------------
def test_reporting_path_with_none_values(tmp_path):
    none_stat = b4.paired_stat([])
    crit = {"1_moneyline_brier": {**none_stat, "pass": None, "runnable": False},
            "2_moneyline_logloss": {**none_stat, "pass": None, "runnable": False},
            "3_sign": {"value": None, "pass": None, "runnable": False},
            "4_total_not_worse": {**none_stat, "pass": None, "runnable": False}}
    twins = {"A": {"runnable": False, "why": "replicate 0: sum of x squared is 0"},
             "B": {"runnable": False}}
    v = b4.verdict("lineup_strength", ran_in_span=True, note_ok=True, checks_ok=True,
                   step1_ok=True, step2_ok=True, criteria=crit, twins=twins,
                   leg1={"runnable": False, "why": None})
    assert v["verdict"] == "INDETERMINATE" and v["row"] == 3
    rec = {"column": "lineup_strength", "section": "5c-B", "verdict": v,
           "criteria": crit, "twins": twins, "fit": {"c": None, "zbar": float("nan")},
           "power_reported": {"rms_p_home_shift": None, "sqrt_n_rms": None},
           "features_reported": {"fit": {"corr_with_z_off": b4.corr([None], [None])},
                                 "graded": {"vif": b4.vif([], [], [])}},
           "_games": [{"x": None}]}
    out = tmp_path / "rec.json"
    b4._finish(rec, {"split": {"F": None, "L": None, "M": None}}, out)
    back = json.loads(out.read_text(encoding="utf-8"))
    assert back["fit"]["zbar"] is None and "_games" not in back
    assert b4.fit_terms([{"lam": 4.0, "runs": 3, "z_s": None, "z_o": None}], 2)["ok"] is False
    assert b4.date_clustered_t([], []) is None


def test_verdict_rows():
    ok_c = {"1": {"runnable": True, "pass": True}, "2": {"runnable": True, "pass": True}}
    ok_t = {"A": {"runnable": True, "beaten": True}, "B": {"runnable": True, "beaten": True}}
    leg = {"runnable": True, "fires": False}
    kw = dict(ran_in_span=True, note_ok=True, checks_ok=True, step1_ok=True, step2_ok=True)
    assert b4.verdict("star_out", **kw, criteria=ok_c, twins=ok_t, leg1=leg)["verdict"] == "PASS"
    assert b4.verdict("star_out", **{**kw, "checks_ok": False}, criteria=ok_c, twins=ok_t,
                      leg1=leg)["row"] == 1
    assert b4.verdict("lineup_strength", **{**kw, "step1_ok": False}, criteria=None,
                      twins=None, leg1=None)["row"] == 1
    assert b4.verdict("lineup_strength", ran_in_span=False, note_ok=True, checks_ok=True,
                      step1_ok=True, step2_ok=True, criteria=None, twins=None,
                      leg1=None)["row"] == 1
    bad_t = {**ok_t, "B": {"runnable": True, "beaten": False}}
    v = b4.verdict("star_out", **kw, criteria=ok_c, twins=bad_t,
                   leg1={"runnable": False})
    assert v["verdict"] == "FAIL" and v["row"] == 2 and "leg 1" in v["could_not_run"]
    assert b4.verdict("star_out", **kw, criteria=ok_c, twins=ok_t,
                      leg1={"runnable": True, "fires": True})["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# the pinned incumbent
# ---------------------------------------------------------------------------
def _git_ok() -> bool:
    try:
        subprocess.run(["git", "rev-parse", f"{b4.INCUMBENT_COMMIT}^{{commit}}"],
                       cwd=str(ROOT.parent), check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not _git_ok(), reason="the pinned commit is not reachable")
def test_pinned_incumbent_loads_and_restores_the_import_name():
    before = sys.modules.get("leaderboard_vintages")
    with b4.pinned_incumbent() as (pbm, plv, blobs):
        assert pbm.MODEL_VERSION == "betting_runs_v2"
        assert sys.modules["leaderboard_vintages"] is plv
        flags = b4.serve_flags(pbm)
        assert flags["SERVE_RUN_DISPERSION"] is False
        assert flags["SERVE_PROB_CALIBRATION"] is False
        assert flags["SERVE_RUNLINE_TIE_SPLIT"] is True
        assert flags["SERVE_ATH_PARK"] is True
        assert flags["SERVE_LINEUP_STRENGTH"] is None and flags["SERVE_STAR_OUT"] is None
        b4.assert_incumbent_form(pbm)
        assert set(blobs) == {"betting_model", "leaderboard_vintages"}
        assert Path(plv.VINTAGE_DIR).resolve() == b4.STORE.resolve()
    assert sys.modules.get("leaderboard_vintages") is before


def test_no_served_module_imports_the_harness():
    for p in list(ROOT.glob("*.py")):
        if p.name.startswith("test_"):
            continue
        assert "b4_availability_look" not in p.read_text(encoding="utf-8", errors="ignore"), p
    assert not hasattr(bm, "SERVE_LINEUP_STRENGTH")
    assert not hasattr(bm, "SERVE_STAR_OUT")


# ---------------------------------------------------------------------------
# steps 1 to 3 end to end, on a synthetic season (small floors, 20 twins)
# ---------------------------------------------------------------------------
def _season(store, col, first_day, last_day, seed):
    rnd = random.Random(seed)
    days = [f"2026-09-{d:02d}" for d in range(first_day, last_day + 1)]
    for d in days[:-1]:
        _write_vintage(store, d)
        p = store / f"{d}.json"
        rec = json.loads(p.read_text(encoding="utf-8"))
        for o in ORGS:
            rec["teams"][o][5] = round(0.300 + 0.02 * rnd.random(), 4)
            rec["teams"][o][6] = rnd.choice([0, 0, 1, 2])
        p.write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()
    bm.reset_vintage_cache()
    games, pk = [], 1
    for d in days[1:]:
        for h, a in (("BAL", "BOS"), ("NYY", "TBR"), ("TOR", "CLE")):
            hr, ar = rnd.randint(0, 9), rnd.randint(0, 9)
            if hr == ar:
                hr += 1
            games.append({"game_pk": pk, "date": d, "home_org": h, "away_org": a,
                          "home_runs": hr, "away_runs": ar, "innings": 9,
                          "home_sp": None, "away_sp": None, "season": "2026"})
            pk += 1
    return days, games


@pytest.mark.parametrize("col,first,last", [("lineup_strength", 7, 27), ("star_out", 5, 19)])
def test_look_core_end_to_end_on_a_synthetic_season(store, tmp_path, monkeypatch,
                                                      col, first, last):
    for k, v in dict(MIN_FIT_GAMES=10, MIN_EVAL_GAMES=5, NIGHT_FLOOR=5, N_TWIN=20,
                     TWIN_BAR=19, ID_MIN_CLUB_GAMES=2).items():
        monkeypatch.setattr(b4, k, v)
    days, games = _season(store, col, first, last, seed=11)
    stamps = {d: [{"commit": "x", "applied": True, "skipped": []}] for d in days}
    counts = b4.counts_report(bm, lv, col, games, store=store, board_stamps=stamps)
    assert counts["step1_counts_pass"], counts["floors"]
    resolve, _ = bm._vintage_resolver()
    marker = tmp_path / "marker"
    rec = b4.look_core(bm, lv, col, games, counts, PARAMS, resolve=resolve,
                       fwd={"ok": False, "why": "fixture"},
                       fpar={"pass": col == "star_out"},
                       checks_ok=True, record={"column": col,
                                               "section": b4.COLUMN_SPECS[col]["section"]},
                       out_dir=tmp_path, marker=marker)
    rid = b4.COLUMN_SPECS[col]["record"]
    assert (tmp_path / f"{rid}_M_before_fit.json").exists() and marker.exists()
    assert rec["fit"]["ok"]
    assert len(rec["twins"]["A"]["means"]) == 20 and len(rec["twins"]["B"]["means"]) == 20
    assert set(rec["criteria"]) == {"1_moneyline_brier", "2_moneyline_logloss",
                                    "3_sign", "4_total_not_worse"}
    assert rec["leg1"]["runnable"] is False
    assert rec["verdict"]["verdict"] in ("FAIL", "INDETERMINATE")
    assert rec["verdict"]["row"] in (2, 3)
    json.dumps(b4._jsonable(rec))
    if col == "star_out":
        assert rec["identification"]["fit_club_games_count_0"] >= 2
        assert "vif_on_z_off_z_prev" in rec["features_reported"]["fit"]
