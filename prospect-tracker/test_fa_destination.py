# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination model's builder and lab, on fixtures only.

docs/fa-2026-10/FA_DESTINATION_GATE.md section 15: any ranking, probability,
coefficient, floor or metric of the destination arms computed on the real
2018-2026 chain before the one look (task Q9_04b) voids the registration. So
every test here runs on the lab's synthetic fixture or on hand-built rows; the
real-data pins (the Gate 3 row hash, the five registered arm metrics, the
byte identity of the served FA files) live in
test_fa_destination_byte_identity.py and read no destination arm.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import fa_destination as fd  # noqa: E402
import fa_fit_backtest as fb  # noqa: E402
import fa_destination_lab as lab  # noqa: E402


@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("fa_dest") / "eval.json"
    inputs = lab.fixture_inputs()
    doc = lab.run(inputs, out, "2026-10-09")
    return inputs, doc, out


def _primary(inputs):
    override, _ = lab.join_gate2(inputs.gate2_fn(), inputs.signings, inputs.club_states)
    signings = {k: dict(v) for k, v in inputs.signings.items()}
    for k, (g, a) in override.items():
        signings[k]["_price_guarantee_usd"] = g
        signings[k]["_price_aav_usd"] = a
    return lab.build_frame(inputs.primary_rows_fn(override), signings, inputs.club_states,
                           "gate2_predicted")


# --------------------------------------------------------------------------
# the probability vector
# --------------------------------------------------------------------------

def test_each_members_30_probabilities_lie_in_0_1_and_sum_to_1():
    inputs = lab.fixture_inputs()
    frame = _primary(inputs)
    fits = lab.fit_arms(frame)
    n_checked = 0
    for arm in ("P", "N", "L_perm", "incumbency_only"):
        P = fits[arm]["probs"]
        assert P.shape == (len(lab._scored(frame)), fd.N_CLUBS)
        assert np.all(P > 0.0) and np.all(P < 1.0), arm
        assert np.all(np.abs(P.sum(axis=1) - 1.0) <= 1e-9), arm
        n_checked += P.shape[0]
    assert n_checked > 0
    rng = np.random.default_rng(3)
    X = rng.normal(0, 2, (50, fd.N_CLUBS, len(fd.ARM_FEATURES["P"])))
    coefs = {f: float(c) for f, c in zip(fd.ARM_FEATURES["P"], rng.normal(0, 1, 6))}
    P = fd.predict_proba(X, coefs, fd.ARM_FEATURES["P"])
    assert np.all((P > 0) & (P < 1)) and np.all(np.abs(P.sum(axis=1) - 1) <= 1e-9)


def test_the_fit_is_a_conditional_logit_with_the_registered_penalty():
    """The analytic gradient matches a finite difference, only the L terms
    are penalized, and the optimizer settings are the registered ones."""
    rng = np.random.default_rng(5)
    names = fd.ARM_FEATURES["P"]
    X = rng.normal(0, 1, (40, fd.N_CLUBS, len(names)))
    y = rng.integers(0, fd.N_CLUBS, 40)
    pen = np.asarray([1.0 if f in fd.L_FEATS else 0.0 for f in names])
    assert pen.tolist() == [0.0, 1.0, 1.0, 1.0, 1.0, 0.0]
    w = rng.normal(0, 0.3, len(names))
    f0, g = fd._objective(w, X, y, pen, 1.0)
    for k in range(len(names)):
        e = np.zeros(len(names))
        e[k] = 1e-6
        fd_k = (fd._objective(w + e, X, y, pen, 1.0)[0]
                - fd._objective(w - e, X, y, pen, 1.0)[0]) / 2e-6
        assert abs(fd_k - g[k]) < 1e-4 * max(1.0, abs(g[k]))
    coefs, info = fd.fit_clogit(X, y, names)
    assert info["converged"] and set(coefs) == set(names)
    assert fd.OPTIMIZER == {"method": "L-BFGS-B", "gtol": 1e-8, "maxiter": 2000,
                            "start": "zeros"}
    assert fd.PENALTY_LAMBDA == 1.0


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------

def test_identical_inputs_give_identical_bytes(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    lab.run(lab.fixture_inputs(), a, "2026-10-09")
    lab.run(lab.fixture_inputs(), b, "2026-10-09")
    assert a.read_bytes() == b.read_bytes()
    s1 = json.dumps(lab._jsonable(lab.fixture_inputs().club_states), sort_keys=True)
    s2 = json.dumps(lab._jsonable(lab.fixture_inputs().club_states), sort_keys=True)
    assert s1 == s2


def test_lperm_draws_one_permutation_per_winter():
    p1 = fd.permutation_for_winter(2019)
    assert sorted(p1.tolist()) == list(range(30))
    assert p1.tolist() == np.random.default_rng(7 + 2019).permutation(30).tolist()
    assert p1.tolist() != fd.permutation_for_winter(2020).tolist()
    m = {f: list(range(30)) for f in fd.L_FEATS}
    m.update({"fit_analog": [0.0] * 30, "incumbent": [0.0] * 30})
    pm = fd.permute_l(m, p1)
    for f in fd.L_FEATS:
        assert pm[f] == [int(p1[j]) for j in range(30)]
    assert pm["fit_analog"] == m["fit_analog"]


# --------------------------------------------------------------------------
# no winter-Y leak
# --------------------------------------------------------------------------

def _club_state_json(Y, signings_by_year, payroll):
    st = fd.club_state(Y, load_signings=lambda y: signings_by_year.get(y, {}),
                       npv_fn=lambda k, y, g: float(g), payroll=payroll)
    return json.dumps(lab._jsonable(st), sort_keys=True)


def test_a_winter_y_signing_cannot_change_any_club_side_feature_of_winter_y():
    orgs = fd.ORGS
    sby = {y: {f"p{y}_{i}": {"player_key": f"p{y}_{i}", "mlb_deal": True, "years": 2,
                             "guarantee_usd": 1e6 * (i + 1), "to_team": orgs[i % 30]}
               for i in range(40)} for y in (2016, 2017, 2018)}
    pay = {o: {"tax_payroll_usd": 1e8 + 1e6 * j, "payor": "Non-Tax"}
           for j, o in enumerate(orgs)}
    before = _club_state_json(2019, sby, pay)
    sby[2019] = {"new": {"player_key": "new", "mlb_deal": True, "years": 10,
                         "guarantee_usd": 5e8, "to_team": "LAD"}}
    assert _club_state_json(2019, sby, pay) == before
    # the winter-Y signing does count in winter Y+1
    assert _club_state_json(2020, sby, pay) != _club_state_json(
        2020, {**sby, 2019: {}}, pay)


def _patch_build_rows_sources(monkeypatch, enriched):
    orgs = fb.ORGS
    monkeypatch.setattr(fb.fm, "enriched_signings", lambda a, b: [dict(s) for s in enriched])
    monkeypatch.setattr(fb, "team_payroll_state", lambda season: {
        o: {"tax_payroll_usd": 1.5e8 + 2e6 * j, "payor": "Non-Tax"} for j, o in enumerate(orgs)})
    monkeypatch.setattr(fb, "standings_wins", lambda season: {
        o: 70 + j for j, o in enumerate(orgs)})
    monkeypatch.setattr(fb.fa_sources, "fetch_savant_park_factors", lambda season: [
        {"name_display_club": o, "index_woba": 95 + j % 10, "index_hr": 90 + j % 20}
        for j, o in enumerate(orgs)])


def _fixture_enriched():
    orgs = fb.ORGS
    rng = np.random.default_rng(11)
    out = []
    for y in (2015, 2016, 2017, 2018):
        for i in range(25):
            g = float(1e6 * (1 + int(rng.integers(0, 60))))
            out.append({"class_year": y, "player_key": f"k{y}_{i}",
                        "to_team": orgs[int(rng.integers(0, 30))],
                        "from_team": orgs[int(rng.integers(0, 30))],
                        "years": int(rng.integers(1, 5)), "guarantee_usd": g,
                        "npv_guarantee_usd": g,
                        "position": ("SP" if i % 3 == 0 else "SS")})
    return out


def _rows_by_signing(rows):
    out = {}
    for r in rows:
        out.setdefault((r["winter"], r["signing"]), []).append(r)
    return out


def _features_only(rs):
    return [{k: v for k, v in r.items() if k != "signed"} for r in rs]


def test_a_winter_y_signing_cannot_change_any_fit_feature_of_winter_y(monkeypatch):
    """build_rows on a fixture: moving one winter-2018 signing to another club
    and changing his price leaves every other 2018 signing's rows unchanged,
    and leaves his own features unchanged when only the club moves."""
    base = _fixture_enriched()
    _patch_build_rows_sources(monkeypatch, base)
    rows0 = _rows_by_signing(fb.build_rows())
    assert rows0 and {k[0] for k in rows0} == {2018}
    target = next(s for s in base if s["class_year"] == 2018)
    moved = [dict(s) for s in base]
    for s in moved:
        if s["player_key"] == target["player_key"]:
            s["to_team"] = "LAD" if target["to_team"] != "LAD" else "NYY"
    _patch_build_rows_sources(monkeypatch, moved)
    rows1 = _rows_by_signing(fb.build_rows())
    for key, rs in rows0.items():
        if key[1] == target["player_key"]:
            assert _features_only(rows1[key]) == _features_only(rs)
            assert rows1[key] != rs                       # only the label moved
        else:
            assert rows1[key] == rs
    repriced = [dict(s) for s in base]
    for s in repriced:
        if s["player_key"] == target["player_key"]:
            s["guarantee_usd"] = s["npv_guarantee_usd"] = 4.0e8
    _patch_build_rows_sources(monkeypatch, repriced)
    rows2 = _rows_by_signing(fb.build_rows())
    for key, rs in rows0.items():
        if key[1] != target["player_key"]:
            assert rows2[key] == rs


def test_price_override_replaces_only_the_signings_own_price(monkeypatch):
    base = _fixture_enriched()
    _patch_build_rows_sources(monkeypatch, base)
    default = fb.build_rows()
    same = {(s["class_year"], s["player_key"]):
            (s["npv_guarantee_usd"], s["npv_guarantee_usd"] / max(int(s["years"]), 1))
            for s in base if s["class_year"] == 2018}
    assert fb.build_rows(price_override=same) == default
    drop = dict(same)
    gone = sorted(drop)[0]
    del drop[gone]
    rows = fb.build_rows(price_override=drop)
    assert all((r["winter"], r["signing"]) != gone for r in rows)
    assert rows == [r for r in default if (r["winter"], r["signing"]) != gone]
    cheap = {k: (v[0] / 10.0, v[1] / 10.0) for k, v in same.items()}
    moved = _rows_by_signing(fb.build_rows(price_override=cheap))
    for key, rs in _rows_by_signing(default).items():
        for a, b in zip(rs, moved[key]):
            for f in ("need", "window", "park", "incumbent", "signed", "org"):
                assert a[f] == b[f]


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------

def test_weights_are_read_from_config_and_checked():
    assert fd.check_weights() == fd.REGISTERED_WEIGHTS
    bad = dict(fd.REGISTERED_WEIGHTS, need=0.41)
    with pytest.raises(fd.WeightsMismatch):
        fd.check_weights(bad)
    comp = {"need": 1.0, "window": 0.5, "afford": 1.0, "park": 0.5, "behavior_cond": 0.2}
    assert fd.fit_analog(comp) == pytest.approx(0.40 + 0.025 + 0.05 + 0.025 + 0.09)


def test_the_lab_stops_on_a_changed_protocol():
    doc = (ROOT / fd.GATE_DOC).read_text(encoding="utf-8")
    assert fd.check_protocol(doc) == fd.PROTOCOL_SHA256
    with pytest.raises(fd.ProtocolMismatch):
        fd.check_protocol(doc.replace("lambda = 1.0", "lambda = 2.0"))


def test_tax_multiplier_reads_the_ledger_bill():
    import fa_cba
    import ledger_export as le
    rates, tiers = fa_cba.cbt_tax_rates(), fa_cba.cbt_surcharge_tiers()
    thr = 241_000_000
    m, dflt = fd.tax_multiplier(200e6, 20e6, thr, "Non-Tax", rates, tiers)
    assert (m, dflt) == (1.0, False)                    # stays under
    T, a = 250e6, 30e6
    m, dflt = fd.tax_multiplier(T, a, thr, "2nd-Time", rates, tiers)
    b1 = le.computed_cbt_bill(T + a, thr, "2nd-Time", rates, tiers)["bill_usd"]
    b0 = le.computed_cbt_bill(T, thr, "2nd-Time", rates, tiers)["bill_usd"]
    assert not dflt and m == pytest.approx(1 + (b1 - b0) / a) and m > 1.3
    assert fd.tax_multiplier(None, a, thr, "Non-Tax", rates, tiers) == (1.0, True)
    assert fd.tax_multiplier(T, 0.0, thr, "Non-Tax", rates, tiers) == (1.0, True)


def test_payor_tier_and_qo_cost_follow_the_ledger_rules():
    assert fd.tier_for_winter(250e6, 241e6, "1st-Time") == "2nd-Time"
    assert fd.tier_for_winter(250e6, 241e6, None) == "1st-Time"
    assert fd.tier_for_winter(200e6, 241e6, "2nd-Time") == "Non-Tax"
    assert fd.tier_for_winter(None, 241e6, "2nd-Time") == "Non-Tax"
    assert fd.qo_cost(True, False, 2) == 2.0
    assert fd.qo_cost(True, True, 2) == 0.0
    assert fd.qo_cost(False, False, 1) == 0.0
    assert fd.canonical_club("OAK") == "ATH" and fd.canonical_club("OS") is None


def test_payroll_level_is_a_population_z_and_missing_clubs_take_zero():
    tax = {o: 1e8 + 1e6 * j for j, o in enumerate(fd.ORGS)}
    tax["MIA"] = None
    z, counts = fd.payroll_level(tax)
    assert counts == {"clubs_with_value": 29, "clubs_without_value": 1}
    assert z["MIA"] == 0.0
    vals = [z[o] for o in fd.ORGS if o != "MIA"]
    assert abs(sum(vals)) < 1e-9 and abs(np.std(vals) - 1.0) < 1e-9


# --------------------------------------------------------------------------
# the lab on its fixture: the look's dry run
# --------------------------------------------------------------------------

def test_the_dry_run_exercises_every_null(fixture_run):
    _inputs, doc, _out = fixture_run
    assert doc["dry_run"] is True
    assert doc["order"] == ["step0", "gate2_join", "folds", "floors",
                            "metrics_clauses_verdict", "reported", "industry"]
    tot = doc["gate2_join"]["total"]
    assert tot["unmatched"] == 1 and tot["duplicate"] == 1
    assert tot["integrity_drop"] == 1 and tot["tuples_without_gate3_signing"] == 1
    assert doc["gate2_join"]["by_winter"]["2020"]["gate3_signings"] == 0
    flags = doc["primary_frame"]["feature_flags"]
    assert flags["payroll_level_missing"] > 0 and flags["tax_multiplier_default"] > 0
    st = doc["inputs"]["club_states"]
    assert st["2021"]["counts"]["payroll_level"]["clubs_without_value"] == 1
    assert st["2018"]["counts"]["fa_share_3"]["remapped_club_code"] > 0
    assert doc["primary_frame"]["scored_winters"] == [2019, 2021, 2022]
    retro = doc["industry"]["retro"]["counts_by_offseason"]
    assert sum(c["unresolved"] for c in retro.values()) >= 2
    assert sum(c["no_parsed_pick"] for c in retro.values()) == 1
    assert sum(c["not_a_scored_signing"] for c in retro.values()) >= 1
    assert doc["reported"]["accepted_qo_excluded"]["matched_signings"] == 1
    assert doc["reported"]["first_club_concentration_served_class"]["available"] is False
    assert set(doc["clauses"]["P"]) >= {"C1", "C2", "C3", "C4", "C5"}
    assert doc["verdict"]["serve"] in (None, "P", "N")
    for arm in lab.FITTED_ARMS:
        for Y, f in doc["folds"][arm]["folds"].items():
            assert len(f["coef_hash"]) == 64 and set(f["coefs"]) == set(fd.ARM_FEATURES[arm])
    assert doc["protocol_sha256"] == fd.PROTOCOL_SHA256


def test_the_floors_block_is_written_before_any_mean_metric(tmp_path, monkeypatch):
    out = tmp_path / "eval.json"
    seen = []

    def guard(fn, name):
        def wrapped(*a, **k):
            on_disk = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
            seen.append((name, "floors" in on_disk))
            return fn(*a, **k)
        return wrapped

    for name in ("rank_metrics", "analytic_metrics", "reliability", "frame_metrics"):
        monkeypatch.setattr(lab, name, guard(getattr(lab, name), name))
    doc = lab.run(lab.fixture_inputs(), out, "2026-10-09")
    assert seen and all(ok for _n, ok in seen), seen[:5]
    assert doc["order"].index("floors") < doc["order"].index("metrics_clauses_verdict")
    assert doc["floors"]["resample_seed"] == 7 and doc["floors"]["resample_count"] == 2000
    assert doc["floors"]["mrr_mde95"] == 0.0139


def test_rank_metrics_match_the_gate3_sort_on_ties():
    members = [{"winter": 2019, "key": "a", "y": 3}, {"winter": 2019, "key": "b", "y": 0}]
    scores = np.zeros((2, 30))
    scores[1, 5] = 1.0
    ranks = lab._ranks(scores, np.asarray([3, 0]))
    assert ranks.tolist() == [4, 2]                    # ties keep ORGS order
    m = lab.rank_metrics(scores, members)
    assert m["mrr"] == round((1 / 4 + 1 / 2) / 2, 4) and m["top1"] == 0.0 and m["top3"] == 0.5


def test_incumbency_only_and_random_are_analytic():
    rnd, _ = lab.analytic_metrics([{"incumbent_idx": None, "y": 0}], "random")
    assert rnd["mrr"] == 0.1332 and rnd["top5"] == round(5 / 30, 4)
    inc, rr = lab.analytic_metrics([{"incumbent_idx": 2, "y": 2},
                                    {"incumbent_idx": 2, "y": 4},
                                    {"incumbent_idx": None, "y": 1}], "incumbency")
    assert rr[0] == 1.0 and rr[2] == pytest.approx(lab.H30 / 30)
    assert rr[1] == pytest.approx(sum(1 / r for r in range(2, 31)) / 29)
    assert inc["top1"] == round((1 + 0 + 1 / 30) / 3, 4)


def test_the_ship_rule():
    ok = {"C1": True, "C2": True, "C4": True, "C5": True}
    assert lab.ship_verdict({**ok, "C3": True}, ok)["serve"] == "P"
    v = lab.ship_verdict({**ok, "C3": False}, ok)
    assert v["serve"] == "N" and v["loss"] == lab.NULL_LINE
    assert lab.ship_verdict({**ok, "C3": False}, {**ok, "C4": False})["serve"] is None
    assert lab.ship_verdict({**ok, "C1": False, "C3": True}, ok)["serve"] is None
    assert lab.ship_verdict({**ok, "C5": False, "C3": True}, ok)["serve"] is None


def test_the_mlbtr_pick_rule():
    assert lab._mlbtr_pick_credit({"pred_team": "OAK"}) == {"ATH": 1.0}
    tie = lab._mlbtr_pick_credit({"pred_team": None, "pred_team_by_writer": [
        {"team": "NYY"}, {"team": "LAD"}, {"team": None}]})
    assert tie == {"LAD": 0.5, "NYY": 0.5}
    most = lab._mlbtr_pick_credit({"pred_team": None, "pred_team_by_writer": [
        {"team": "NYY"}, {"team": "NYY"}, {"team": "LAD"}]})
    assert most == {"NYY": 1.0}
    assert lab._mlbtr_pick_credit({"pred_team": None, "pred_team_by_writer": None}) is None


def test_serving_is_off_and_nothing_is_written_under_data(fixture_run):
    assert fd.FA_DESTINATION_SERVE is False
    assert not (ROOT / "data" / "fa_destinations.json").exists()
    _inputs, _doc, out = fixture_run
    assert (ROOT / "data") not in out.parents
