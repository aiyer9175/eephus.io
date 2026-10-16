# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV_RELIEVER_ADJ (owner decision EW3-31; docs/efv-v2/EFV_RELIEVER_ADJ.md): the usage
classification, the candidates' rules, the dark switch, the read's artifact and the gate
scan."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv_reliever_adj as X

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "efv_reliever_adj.py"
DOC = ROOT / X.DOC


# ---------------------------------------------------------------------------
# 1. the usage classification (section 2)
# ---------------------------------------------------------------------------

def test_the_cut_points_are_the_registrations():
    assert (X.MIN_G, X.GS_SHARE_CUT, X.IP_PER_GS_CUT) == (5, 0.5, 3.5)
    doc = DOC.read_text(encoding="utf-8")
    assert "GS / G < 0.5" in doc and "IP / GS < 3.5" in doc


@pytest.mark.parametrize("g,gs,outs,want", [
    (10, 10, 89, X.SHORT),        # Brandon Clarke 2026: 29.2 IP over 10 starts
    (10, 4, 60, X.RELIEF),        # under half the appearances are starts
    (10, 5, 60, X.STARTER),       # exactly half is not relief; 20 IP / 5 GS = 4.0
    (25, 25, 360, X.STARTER),     # 120 IP over 25 starts
    (4, 4, 60, X.FEW),
    (0, 0, 0, X.NO_LINE),
])
def test_classify(g, gs, outs, want):
    assert X.classify(g, gs, outs) == want


def test_the_ip_per_start_boundary_is_a_starter():
    assert X.classify(10, 10, 105) == X.STARTER        # 35.0 IP / 10 GS = 3.5
    assert X.classify(10, 10, 104) == X.SHORT


def test_usage_reads_the_read_season_and_never_a_later_one(monkeypatch):
    seen = []
    lines = {2025: {1: (20.0, 20.0, 300.0, 400.0), 2: (12.0, 12.0, 90.0, 150.0)},
             2026: {1: (8.0, 8.0, 96.0, 110.0), 2: (2.0, 0.0, 6.0, 9.0)},
             2027: {1: (99.0, 0.0, 99.0, 99.0), 2: (99.0, 0.0, 99.0, 99.0)}}

    def fake(season):
        seen.append(int(season))
        return lines.get(int(season), {})
    monkeypatch.setattr(X, "season_usage", fake)
    u = X.usage(1, 2026)
    assert u["role"] == X.STARTER and u["seasons"] == [2026] and u["g"] == 8
    u2 = X.usage(2, 2026)                     # 2 appearances: the season before is added
    assert u2["seasons"] == [2025, 2026] and u2["g"] == 14 and u2["role"] == X.SHORT
    u3 = X.usage(1, 2026, window="two")
    assert u3["g"] == 28
    assert X.usage(None, 2026)["role"] == X.NO_LINE
    assert max(seen) == 2026


def test_the_card_label():
    u = {"role": X.SHORT, "seasons": [2026], "g": 10, "gs": 10, "ip": "29.2",
         "ip_per_g": 29.6667 / 10, "ip_per_gs": 29.6667 / 10}
    assert X.label_text(u) == "Usage: Short starts (2026 MiLB): 10 G, 10 GS, 29.2 IP, 3.0 IP per start"
    r = {"role": X.RELIEF, "seasons": [2025, 2026], "g": 40, "gs": 2, "ip": "55.1",
         "ip_per_g": 55.333 / 40, "ip_per_gs": 55.333 / 2}
    assert X.label_text(r) == "Usage: Reliever (2025-26 MiLB): 40 G, 2 GS, 55.1 IP, 1.4 IP per appearance"
    assert X.label_text({"role": X.FEW}) is None and X.label_text({"role": X.NO_LINE}) is None
    assert X.ip_text(89) == "29.2" and X.ip_text(114) == "38.0"


# ---------------------------------------------------------------------------
# 2. the estimand and the candidates' rules
# ---------------------------------------------------------------------------

def _synthetic(n=6000, k_relief=0.3, seed=11):
    rng = np.random.default_rng(seed)
    u_c = rng.random(n)
    e_s = rng.normal(0, 0.2, n)
    roles = rng.choice([X.STARTER, X.SHORT, X.RELIEF], size=n, p=[0.6, 0.1, 0.3])
    k = np.where(roles == X.RELIEF, k_relief, 1.0)
    u_y = 0.1 + 0.5 * u_c + 0.5 * k * e_s + rng.normal(0, 0.02, n)
    return u_c, u_y, e_s, roles


def test_b_rule_recovers_a_planted_relief_weight():
    u_c, u_y, e_s, roles = _synthetic()
    w = X.role_ols(u_c, u_y, e_s, np.zeros(u_c.size), [X.role_group(r) for r in roles])
    assert w["ratio|REF"] == pytest.approx(1.0, abs=0.05)
    assert w["ratio|RELIEF"] == pytest.approx(0.3, abs=0.05)
    assert w["w|RELIEF"] == pytest.approx(w["ratio|RELIEF"])
    assert w["w|time"] == 0.0 and "e_time" not in w["coef"]


def test_e1_recovers_a_planted_share():
    u_c, u_y, e_s, roles = _synthetic(k_relief=0.4)
    sh = X.realized_shares(u_c, u_y, e_s, roles)
    assert sh[X.STARTER] == pytest.approx(1.0, abs=0.05)
    assert sh[X.RELIEF] == pytest.approx(0.4, abs=0.05)
    assert sh["NONSTARTER_minus_STARTER"] < 0


def test_the_role_term_leaves_the_reference_alone():
    fit = {"coef": {"g|RELIEF": -0.2, "d|RELIEF": -0.05, "g|SHORT-START": 0.1},
           "a_uc": 0.5}
    e = np.array([0.1, 0.1, 0.1, 0.1])
    got = X.role_term_apply(fit, e, [X.STARTER, X.FEW, X.RELIEF, X.SHORT])
    assert got[0] == got[1] == pytest.approx(0.1)
    assert got[2] == pytest.approx(0.1 + (-0.2 * 0.1 - 0.05) / 0.5)
    assert got[3] == pytest.approx(0.1 + (0.1 * 0.1) / 0.5)


def test_workload_normalization_removes_the_outing_length_slope():
    rng = np.random.default_rng(4)
    z = rng.normal(2.6, 0.4, 500)
    rows = [{"v2": {"scr_w2p_csw_p": float(2.0 + 0.5 * zi + rng.normal(0, 0.01)),
                    "other": 1.0}} for zi in z]
    fit = X.workload_fit(rows, list(z))
    assert fit["scr_w2p_csw_p"][0] == pytest.approx(0.5, abs=0.01)
    out = X.workload_apply(rows, list(z), fit)
    x = np.array([r["v2"]["scr_w2p_csw_p"] for r in out])
    assert abs(np.corrcoef(x, z)[0, 1]) < 0.1
    assert all(r["v2"]["other"] == 1.0 for r in out)
    assert X.workload_apply(rows[:1], [None], fit)[0] is rows[0]   # no usage line: unchanged
    assert set(X.RATE_KEYS) >= {"scr_w2p_csw_p", "scr_w2p_k_resid_p", "scr_w4p_pop_pit", "k_rel"}


def test_the_ship_rule_needs_the_pooled_lower_bound_above_zero():
    def r(lo, lv, vm):
        return {"pooled": {"delta": 0.01, "ci95": [lo, 0.02]},
                "frames": {"lv_dev": {"delta": lv}, "vm_dev": {"delta": vm}}}
    reads = {"A": r(0.001, 0.0, 0.0), "B": r(-0.001, 0.01, 0.01), "C": r(0.002, -0.006, 0.01)}
    s = X.ship_reading(reads)
    assert s["passing"] == ["A"] and s["prepared"] == "A"
    assert X.MAX_TRAIL == 0.005


# ---------------------------------------------------------------------------
# 3. the read, the dark switch and the frames
# ---------------------------------------------------------------------------

def test_the_adjustment_is_dark():
    assert X.RELIEVER_ADJ_ON is False


def test_the_read_and_what_it_prepared():
    if not X.FIT_PATH.exists():
        pytest.skip("the registered read has not run in this tree")
    fit = json.loads(X.FIT_PATH.read_text(encoding="utf-8"))
    assert fit["role"] == "development" and fit["adjudicates"] is False
    for fid, p in fit["parity"].items():
        assert p["recomputed"] == pytest.approx(p["committed"], abs=X.PARITY_TOL), fid
    ship = fit["ship"]
    for c in X.CANDIDATES:
        got = ship["candidates"][c]
        lo = got["pooled_ci95"][0]
        assert got["passes"] == bool(lo > 0 and all(v >= -X.MAX_TRAIL
                                                    for v in got["frame_deltas"].values()))
    # a fail prepares nothing: no served weights file exists
    assert (ship["prepared"] is None) == (not X.WEIGHTS_PATH.exists())
    assert fit["served_check"]["brandon_clarke"]["recomputed_rank"] == \
        fit["served_check"]["brandon_clarke"]["served_rank"]


def test_no_reserved_vintage_is_built():
    import efv_vintage_frame as F
    book = object.__new__(X.RoleBook)
    book._lv, book._universe = {}, None
    for V in F.RESERVED_LV:
        with pytest.raises(F.ReservedFrameError):
            book.lv_ids(V)


# ---------------------------------------------------------------------------
# 4. the card label (section 9)
# ---------------------------------------------------------------------------

def test_the_roles_artifact_matches_its_rule():
    if not X.ROLES_PATH.exists():
        pytest.skip("the usage labels have not been exported in this tree")
    doc = json.loads(X.ROLES_PATH.read_text(encoding="utf-8"))
    players = doc["players"]
    assert sum(doc["counts"].values()) == len(players)
    for pk, r in players.items():
        if r["role"] == X.NO_LINE:
            assert "label" not in r
            continue
        outs = int(r["ip"].split(".")[0]) * 3 + int(r["ip"].split(".")[1])
        assert X.classify(r["g"], r["gs"], outs) == r["role"], pk
        assert ("label" in r) == (r["role"] in X.LABEL_WORD), pk
        assert max(r["seasons"]) <= doc["read_season"]
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in X.ROLES_PATH.read_text(encoding="utf-8")


def test_export_roles_writes_where_it_is_told(monkeypatch, tmp_path):
    import efv_dataset as D
    live = tmp_path / "live.json"
    live.write_text(json.dumps([
        {"player_key": "a", "mlbam_id": 1, "consensus_fv_raw": 45.0},
        {"player_key": "b", "mlbam_id": 2, "consensus_fv_raw": 40.0},
        {"player_key": "c", "mlbam_id": 3, "consensus_fv_raw": None}]), encoding="utf-8")
    monkeypatch.setattr(D, "live_matrix_path", lambda side: live)
    monkeypatch.setattr(X, "season_usage", lambda s: {1: (10.0, 10.0, 89.0, 121.0)} if s == 2026 else {})
    out = tmp_path / "roles.json"
    doc = X.export_roles(out=out, today="2026-10-15", log=lambda *_a: None)
    assert out.exists() and set(doc["players"]) == {"a", "b"}
    assert doc["players"]["a"]["role"] == X.SHORT and doc["players"]["b"]["role"] == X.NO_LINE
    assert doc["read_season"] == 2026


def test_the_card_prints_the_label_for_pitchers_only():
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert 'fetch("/data/efv_pitcher_roles.json"' in html
    i = html.index("function efvDetailCard(p)")
    body = html[i:html.index("\nfunction ", i + 10)]
    assert 'x.side === "P" ? pitcherUsageHTML(p) : ""' in body
    fn = html[html.index("function pitcherUsageHTML(p)"):]
    fn = fn[:fn.index("\n}") + 2]
    assert "escapeHtml(r.label)" in fn and "does not move the grade" in fn


def test_the_regen_writes_the_labels_when_persisting():
    src = (ROOT / "efv_export.py").read_text(encoding="utf-8")
    i = src.index("def regen_all(")
    body = src[i:src.index("\nif __name__", i)]
    j = body.index("if persist:\n        with _regen_stage(\"valuation_curve\"")
    assert body.index('_regen_stage("pitcher_roles"') > j
    assert "efv_reliever_adj.export_roles(" in body


# ---------------------------------------------------------------------------
# 5. gate compliance
# ---------------------------------------------------------------------------

def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
    assert "run_backtest" not in src
