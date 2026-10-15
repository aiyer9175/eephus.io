# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for etools.py (docs/tools-2026-10/ETOOLS_GATE.md). Fixtures only: no database,
no cache, no label is read."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

import etools as E

SRC = Path(E.__file__).read_text(encoding="utf-8")


def test_flag_is_dark_and_preview_off_the_webroot():
    assert E.ETOOLS_ON is False
    assert "_labs" in E.EVAL_PATH.parts and "_labs" in E.ATLAS_PATH.parts
    assert ".cache" in E.PREVIEW_PATH.parts
    assert E.SERVED_PATH.name == "etools.json"


def test_development_years_exclude_the_reserved_lists():
    assert 2020 not in E.DEV_YEARS and 2021 not in E.DEV_YEARS
    assert max(E.DEV_YEARS) == 2024 and min(E.DEV_YEARS) == 2011
    with pytest.raises(E.GuardError):
        E.guard_years([2019, 2020])
    E.guard_years([2011, 2024])


def test_no_fv_grouping_key():
    with pytest.raises(E.GuardError):
        E.guard_no_fv(["group", "fv_band"])
    E.guard_no_fv(["group", "level", "age_band"])


def test_source_never_calls_the_banned_entry_points():
    tree = ast.parse(SRC)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for banned in ("run_backtest", "run_monthly", "build_site"):
        assert banned not in names
    assert "urlopen" not in SRC and "requests." not in SRC


def test_gate_sha_rejects_garbage():
    assert not E.gate_sha_ok(None)
    assert not E.gate_sha_ok("not-a-sha")
    assert not E.gate_sha_ok("0000000")


def test_constants_match_the_gate():
    assert E.SEED == 20261023 and E.PERM_SEED == 20261024 and E.B == 2000
    assert E.Q_ADMIT == 0.10 and E.R_CAP == 0.6 and E.MAX_SUB == 3 and E.POOL_MIN == 100
    assert E.LAST_UM_SEASON == 2024 and E.MAX_DEBUT_YEAR == 2024
    gate = (Path(E.ROOT) / E.GATE_DOC).read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in gate
    for tool, spec in E.TOOLS.items():
        for c in spec["cands"]:
            assert c in gate, (tool, c)


def test_fold_is_player_disjoint():
    year = np.array([2011, 2011, 2012, 2012, 2013])
    pid = np.array([1, 2, 1, 3, 4])
    tr = E.fold_train_mask(year, pid, 2011)
    # player 1 appears in 2012: excluded from 2011's training rows
    assert tr.tolist() == [False, False, False, True, True]


def test_tip_is_monotone_and_inverse_is_flat_beyond():
    rng = np.random.default_rng(1)
    g = rng.choice([30, 40, 45, 50, 55, 60, 70], 2000).astype(float)
    y = 0.01 * g + rng.normal(0, 0.05, g.size)
    tip = E.fit_tip(g, y)
    assert tip is not None
    assert all(b >= a for a, b in zip(tip["stat"], tip["stat"][1:]))
    inv = E.tip_inverse(tip, np.array([-10.0, 10.0]))
    assert inv[0] == pytest.approx(min(tip["grade"]))
    assert inv[1] == pytest.approx(max(tip["grade"]))


def test_pava():
    assert E.pava_increasing([1, 3, 2, 4], [1, 1, 1, 1]) == [1, 2.5, 2.5, 4]


def test_etool_equals_consensus_without_a_candidate():
    gc = np.array([45.0, 50.0, 55.0])
    Z = np.array([[np.nan], [np.nan], [np.nan]])
    fit = {"lines": [(0.0, 0.1, True)], "c": [3.0]}
    assert E.etool_apply(gc, Z, fit).tolist() == gc.tolist()
    Z2 = np.array([[1.0], [np.nan], [-1.0]])
    out = E.etool_apply(gc, Z2, fit)
    # u = z - (0 + 0.1 gc); eTool = gc + 3 u; a missing candidate leaves the consensus
    assert out.tolist() == pytest.approx([45.0 + 3.0 * (1.0 - 4.5), 50.0, 55.0 + 3.0 * (-1.0 - 5.5)])
    out2 = E.etool_apply(np.array([50.0]), np.array([[200.0]]), fit)
    assert out2[0] == 80.0                  # clamped to the 20-80 scale


def test_display_rounds_up_to_five():
    assert E.display_grade(50.1) == 55
    assert E.display_grade(50.0) == 50
    assert E.display_grade(19.0) == 20
    assert E.display_grade(None) is None


def test_parse_mph():
    assert E.parse_mph("94-97") == pytest.approx(95.5)
    assert E.parse_mph("98") == 98.0
    assert E.parse_mph(None) is None


def test_zmetric_shrinks_and_reads_only_before_the_board_year():
    rng = np.random.default_rng(3)
    lines = {}
    for pid in range(400):
        talent = rng.normal()
        for s in (2015, 2016, 2017, 2018):
            e = float(rng.integers(150, 500))
            lines[(pid, s, "AA")] = (0.3 + 0.02 * talent + rng.normal(0, 0.03), e, None)
    z = E.ZMetric("t", lines, 100.0)
    k = z.k_at(2018)
    assert k is not None and k > 0
    v = z.asof(5, 2018)                 # reads 2015 to 2017 only
    lines2 = dict(lines)
    lines2[(5, 2018, "AA")] = (9.0, 400.0, None)
    z2 = E.ZMetric("t", lines2, 100.0)
    z2._k[2017] = z.k_at(2017)
    # the 2018 line is never read for board year 2018: the as-of value is unchanged, exactly
    assert z2.asof(5, 2018) == v
    # and it is shrunk: |as-of| < |the unshrunk Marcel mean of the season z|, by E / (E + k)
    d = z.season_z[5]
    num = sum(w * d[2018 - b][1] * d[2018 - b][0] for b, w in E.MARCEL.items())
    den = sum(w * d[2018 - b][1] for b, w in E.MARCEL.items())
    E_exp = sum((w / E.MARCEL[1]) * d[2018 - b][1] for b, w in E.MARCEL.items())
    raw = num / den
    kk = z.k_at(2017)
    assert v == pytest.approx(raw * E_exp / (E_exp + kk))
    assert abs(v) < abs(raw)


def test_within_rho_and_bootstrap_agree():
    rng = np.random.default_rng(4)
    n = 400
    year = rng.choice([2011, 2012, 2013], n)
    pid = np.arange(n)
    x = rng.normal(size=n)
    y = x + rng.normal(size=n)
    r = E.within_rho(x, y, year)
    W = np.ones((3, n))
    assert np.allclose(E.within_rho(x, y, year, W), r)
    draws = E.within_rho(x, y, year, E.cluster_weights(pid, 400, 9))
    assert abs(float(np.mean(draws)) - r) < 0.02 and float(np.std(draws)) > 0.005


def test_dry_run_completes_on_fixtures():
    out = E.dry_run()
    assert set(out["tools"]) == set(E.TOOLS)
    assert out["atlas_rows"] > 0
    assert out["tools"]["field"] in ("NO SUB-DRIVER", "NOT PASS (no upper-minors label, gate 5.2)")


def test_bh_q():
    q = E.bh_q([0.01, 0.04, None, 0.5])
    assert q[2] is None and q[0] <= q[1] <= q[3]


# ---------------------------------------------------------------------------
# review fixes (amendment 1, R3): admission, the eTool fit, flag routing, pitch rates
# ---------------------------------------------------------------------------
def _hit_frame(n=240, seed=11, corr_with_first=()):
    rng = np.random.default_rng(seed)
    rows = []
    base = rng.normal(size=n)
    for i in range(n):
        cands = {c: float(rng.normal()) for c in E.TOOLS["hit"]["cands"]}
        cands["k_rw"] = float(base[i])
        for c in corr_with_first:
            cands[c] = float(2.0 * base[i] + 0.01 * rng.normal())
        rows.append({"year": int(E.DEV_YEARS[i % 6]), "pid": i, "gc": 50.0,
                     "src": {s: None for s in E.SOURCES}, "cands": cands,
                     "y": {"mlb": 0.0, "um": 0.0}})
    return E.ToolFrame("hit", rows)


def _row(c, lb, *, q=0.01, lb95=0.05, d=0.10, floor=0.02):
    return {"tool": "hit", "candidate": c, "label": lb, "cell": "pooled", "cell_value": "all",
            "computable": True, "q": q, "lb95": lb95, "d": d, "perm_floor95": floor}


def test_admit_applies_each_gate_clause():
    fr = _hit_frame(corr_with_first=("pbp_swstr",))
    rows = [
        _row("k_rw", "mlb", q=0.01), _row("k_rw", "um", q=0.02, d=0.05),           # admitted 1st
        _row("babip_rw", "mlb", q=0.20), _row("babip_rw", "um", q=0.30),           # 4.4.1: q
        _row("woba_rw", "mlb", lb95=-0.01), _row("woba_rw", "um", lb95=-0.02),      # 4.4.1: lower bound
        _row("age_rel_level", "mlb", d=0.01), _row("age_rel_level", "um", d=0.015),  # 4.4.1: floor
        _row("pbp_contact", "mlb", q=0.015),
        _row("pbp_contact", "um", q=0.5, lb95=-0.1, d=-0.01),                        # 4.4.2: other label
        _row("pbp_swstr", "mlb", q=0.02), _row("pbp_swstr", "um", d=0.02, q=0.3),   # 4.4.3: |r| with k_rw
        _row("pbp_two_strike_contact", "mlb", q=0.03),
        _row("pbp_two_strike_contact", "um", d=0.01, q=0.4),
        _row("trk_zone_contact", "um", q=0.04),                                      # other label absent
        _row("trk_whiff", "mlb", q=0.05), _row("trk_whiff", "um", d=0.01, q=0.6),   # 4.4.4: cap of 3
    ]
    out = E.admit({"hit": fr}, rows)["hit"]
    assert [a["candidate"] for a in out["admitted"]] == ["k_rw", "pbp_two_strike_contact", "trk_zone_contact"]
    why = {r["candidate"]: r.get("dropped") for r in out["qualifying"]}
    assert why["pbp_swstr"].startswith("|r|")
    assert why["trk_whiff"] == "cap of 3"
    for c in ("babip_rw", "woba_rw", "age_rel_level", "pbp_contact"):
        assert c not in why
    assert out["admitted"][0]["label"] == "mlb" and out["admitted"][2]["label"] == "um"


def test_admit_takes_the_other_label_when_only_it_qualifies():
    fr = _hit_frame()
    rows = [_row("k_rw", "mlb", q=0.5, lb95=-0.1, d=0.01), _row("k_rw", "um", q=0.01)]
    out = E.admit({"hit": fr}, rows)["hit"]
    assert [(a["candidate"], a["label"]) for a in out["admitted"]] == [("k_rw", "um")]


def _planted(n=3000, c_true=3.0, seed=5):
    rng = np.random.default_rng(seed)
    gc = rng.choice(np.arange(25.0, 80.0, 5.0), n)
    u = rng.normal(size=n)
    z = 0.04 * (gc - 50.0) + u                       # the candidate, correlated with the grade
    yg = gc + c_true * u + rng.normal(0, 1.0, n)     # the realized outcome on the grade scale
    y_mlb = np.where(rng.random(n) < 0.5, (yg - 50.0) / 100.0, np.nan)          # a linear stat
    y_um = np.where(rng.random(n) < 0.7, np.exp((yg - 50.0) / 20.0), np.nan)    # a convex stat
    return gc, z.reshape(-1, 1), {"mlb": y_mlb, "um": y_um}


def test_etool_fit_recovers_a_planted_c_through_the_tip_inverse_on_stacked_labels():
    gc, Z, ys = _planted()
    train = np.ones(gc.size, dtype=bool)
    fit = E.etool_fit(gc, Z, ys, train)
    assert fit is not None
    interior = (gc > 30) & (gc < 70) & np.isfinite(ys["mlb"])
    yg = E.tip_inverse(fit["tips"]["mlb"], ys["mlb"][interior])
    assert np.corrcoef(yg, 50.0 + 100.0 * ys["mlb"][interior])[0, 1] > 0.999
    # recovered up to the registered flat-beyond TIP, which truncates the outcome at the
    # table's ends and pulls c in a little (about 13% here); without the inverse (raw stat
    # units) c would be near 0.03 for the linear label and far from 3 for the convex one
    assert 2.4 <= fit["c"][0] <= 3.1
    _a, b, ok = fit["lines"][0]
    assert ok and b == pytest.approx(0.04, abs=0.01)
    # both labels stacked: one row per (row, label) present
    assert fit["n_fit"] == int(np.isfinite(ys["mlb"]).sum() + np.isfinite(ys["um"]).sum())
    assert set(fit["tips"]) == {"mlb", "um"}
    # one label alone gives the same c (each label reaches the grade scale through its own TIP)
    one = E.etool_fit(gc, Z, {"um": ys["um"]}, train)
    assert one["c"][0] == pytest.approx(fit["c"][0], abs=0.35)
    # the train mask is honoured
    half = np.arange(gc.size) < gc.size // 2
    fh = E.etool_fit(gc, Z, ys, half)
    assert fh["n_fit"] == int(np.isfinite(ys["mlb"][half]).sum() + np.isfinite(ys["um"][half]).sum())


def _preview_rows():
    return [{"year": 0, "pid": 1, "player_key": "pk1", "name": "A", "side": "hit", "position": "SS",
             "per_source": {"fangraphs": {"hit": 50.0, "game_pwr": 45.0}, "mlb_pipeline": {"hit": 55.0}},
             "cands": {"k_rw": 1.0}}]


def _preview_eval():
    return {"etools": {"hit": {"verdict": "PASS", "admitted": ["k_rw"],
                               "final_fit": {"lines": [[0.0, 0.0, True]], "c": [4.0], "sigma": 2.0}},
                       "game_pwr": {"verdict": "NOT PASS", "admitted": ["iso_rw"],
                                    "final_fit": {"lines": [[0.0, 0.0, True]], "c": [9.0], "sigma": 2.0}}}}


def _stub_preview_inputs(monkeypatch, tmp_path, flag):
    monkeypatch.setattr(E, "load_board", lambda **_k: {})
    monkeypatch.setattr(E, "build_universe", lambda *_a, **_k: (_preview_rows(), {}))
    monkeypatch.setattr(E, "attach_candidates", lambda *_a, **_k: {})
    prev, served = tmp_path / "preview.json", tmp_path / "served.json"
    monkeypatch.setattr(E, "PREVIEW_PATH", prev)
    monkeypatch.setattr(E, "SERVED_PATH", served)
    if flag is not None:
        monkeypatch.setattr(E, "ETOOLS_ON", flag)
    return prev, served


@pytest.mark.parametrize("flag", [False, True])
def test_build_preview_routes_by_the_flag(monkeypatch, tmp_path, flag):
    import json
    prev, served = _stub_preview_inputs(monkeypatch, tmp_path, flag)
    path = E.build_preview(_preview_eval(), log=lambda *_a: None)
    assert path == (served if flag else prev)
    assert path.exists() and not (prev if flag else served).exists()
    doc = json.loads(path.read_text(encoding="utf-8"))
    t = doc["players"]["pk1"]["tools"]
    assert t["eHIT"]["basis"] == "etool" and t["eHIT"]["consensus"] == 52.5
    assert t["eHIT"]["etool"] == pytest.approx(56.5)          # 52.5 + 4 x (1 - 0)
    assert t["eHIT"]["etool_display"] == 60
    assert t["eHIT"]["band80"] == pytest.approx([56.5 - E.BAND_Z * 2.0, 56.5 + E.BAND_Z * 2.0], abs=0.01)
    # a tool that did not pass keeps the consensus even with a fit on file
    assert t["ePOW"]["basis"] == "consensus" and "etool" not in t["ePOW"]
    assert doc["flag_etools_on"] is flag


def test_preview_is_dark_by_default(monkeypatch, tmp_path):
    prev, served = _stub_preview_inputs(monkeypatch, tmp_path, None)
    assert E.ETOOLS_ON is False
    E.build_preview(_preview_eval(), log=lambda *_a: None)
    assert prev.exists() and not served.exists()


class _StubPR:
    MILB_FIRST = 2019
    MILB_LEVELS = ("AA",)
    BASIS_ROLE = "role_split"

    @staticmethod
    def league_rates(lv, s):
        return {"hit": {"p_pa": 4.0}, "sp": {"p_bf": 3.8, "p_ip": 16.0}, "rp": {"p_bf": 4.0, "p_ip": 17.0}}

    @staticmethod
    def player_lines(s, lv):
        return {
            # role split: majority role SP, exposure from the SP line
            10: {"pit": {"role": "SP", "basis": "role_split", "p_bf": 3.9, "p_ip": 15.5,
                         "sp": {"bf": 400}, "rp": {"bf": 60}, "season_line": {"bf": 460}}},
            # fallback basis with role lines present: the rate is the season line's, so is the BF
            11: {"pit": {"role": "RP", "basis": "season_line_fallback", "p_bf": 4.2, "p_ip": 18.0,
                         "sp": {"bf": 20}, "rp": {"bf": 90}, "season_line": {"bf": 150}}},
            # a hitter line, and a pitcher's own hitting line (skipped)
            20: {"hit": {"pos": "SS", "p_pa": 4.4, "pa": 300}},
            21: {"hit": {"pos": "P", "p_pa": 3.0, "pa": 5}},
        }


def test_pitch_rate_lines_read_exposure_off_the_rated_line(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pitch_rates", _StubPR)
    pit = E.pitch_rate_lines("pit", last_season=2019)
    assert pit["pbf_raw"][(10, 2019, "AA")] == (3.9, 400.0, None)
    v, e, role = pit["pbf_par"][(10, 2019, "AA")]
    assert v == pytest.approx(3.9 / 3.8) and e == 400.0 and role == "SP"
    assert pit["pip_par"][(10, 2019, "AA")][0] == pytest.approx(15.5 / 16.0)
    # R4: on the fallback basis the exposure is the season line's 150 BF, not the RP line's 90
    assert pit["pbf_raw"][(11, 2019, "AA")] == (4.2, 150.0, None)
    v, e, role = pit["pbf_par"][(11, 2019, "AA")]
    assert v == pytest.approx(4.2 / 4.0) and e == 150.0 and role == "RP"
    hit = E.pitch_rate_lines("hit", last_season=2019)
    assert hit["ppa_raw"] == {(20, 2019, "AA"): (4.4, 300.0, None)}
    assert hit["ppa_par"][(20, 2019, "AA")][0] == pytest.approx(4.4 / 4.0)


def test_review_reads_refuse_without_a_registered_amendment(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "REVIEW_PATH", tmp_path / "r.json")
    with pytest.raises(E.GuardError):
        E.review_reads("not-a-sha", log=lambda *_a: None)
    (tmp_path / "r.json").write_text('{"spent": true, "spent_at": "x"}', encoding="utf-8")
    with pytest.raises(E.GuardError, match="spent"):
        E.review_reads("0000000", log=lambda *_a: None)


def _fixture_hit_with_debuts():
    fr = E.fixture_frames(n_players=800)["hit"]
    fr.debut = (fr.pid % 2) == 0
    return fr


def test_promotion_counts_partition_the_frame():
    fr = _fixture_hit_with_debuts()
    c = E.promotion_counts(fr)
    assert c["um_and_debut"] + c["um_no_debut"] + c["no_um_no_debut"] + c["no_um_debut"] == fr.n
    um = np.isfinite(fr.y["um"])
    assert c["um_no_debut"] == int((um & ~fr.debut).sum())


def test_tool_frame_reads_debut_by_2024():
    rows = [{"year": 2015, "pid": p, "gc": 50.0, "src": {}, "cands": {}, "y": {}, "mlb_first": mf}
            for p, mf in ((1, 2016), (2, 2024), (3, 2025), (4, None))]
    fr = E.ToolFrame("speed", rows)
    assert fr.debut.tolist() == [True, True, False, False]


def test_nondebut_read_reproduces_the_pooled_eval_and_splits_it():
    fr = _fixture_hit_with_debuts()
    ev = E.etool_eval(fr, ["k_rw"], Bn=100)
    out = E.nondebut_read(fr, ["k_rw"], Bn=100)
    assert out["pooled"]["d"] == ev["labels"]["um"]["d"]
    assert out["pooled"]["lb95"] == pytest.approx(ev["labels"]["um"]["lb95"])
    assert out["non_debut"]["n"] + out["debut"]["n"] == out["pooled"]["n"]
    assert out["promotion_dependent"] is False          # the fixture's k_rw carries the truth for all


def test_margin_read_flags_a_noise_subdriver():
    fr = E.fixture_frames(n_players=800)["hit"]
    out = E.margin_read(fr, ["k_rw", "babip_rw"], Bn=200)
    k, b = out["subdrivers"]["k_rw"], out["subdrivers"]["babip_rw"]
    assert k["without"] == ["babip_rw"] and b["without"] == ["k_rw"]
    assert k["no_added_effect"] is False
    assert b["no_added_effect"] is True
    for lb in ("mlb", "um"):
        assert k["labels"][lb]["given_others"]["lb95"] > 0
