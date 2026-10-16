# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eABS v0 (docs/eabs-2026-10-15/EABS_GATE.md): the per-challenge value, the budget
walk, the option-value cost, the per-player identities, the stability statistics and
the exporter's refusing invariants, on fixtures; the constants against the gate."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import count_value as cv  # noqa: E402
import eabs as E  # noqa: E402
import eabs_export as X  # noqa: E402

GATE = ROOT / "docs" / "eabs-2026-10-15" / "EABS_GATE.md"
CV = ROOT / "data" / "count_value.json"


def _row(**kw):
    r = {"game_pk": 1, "season": 2026, "kind": "zone", "flags": None, "inning": 1, "half": "top",
         "at_bat_index": 0, "event_index": 0, "challenge_side": "batting", "original_call": "C",
         "overturned": False, "balls_before": 0, "strikes_before": 0, "outs_before": 0,
         "bases_before": "___", "bat_score_before": 0, "fld_score_before": 0}
    r.update(kw)
    return r


# ---------------------------------------------------------------- the gate
def test_constants_match_the_registration():
    g = GATE.read_text(encoding="utf-8")
    assert E.GATE_DOC == "docs/eabs-2026-10-15/EABS_GATE.md"
    assert "N_MIN = 8" in g and E.N_MIN == 8
    assert "K_OPT = 100" in g and E.K_OPT == 100.0
    assert "B = 2,000 draws, seed 20261015" in g and E.BOOT == 2000 and E.SEED == 20261015
    assert "seed 20261016" in g and E.SEED_TWIN == 20261016
    assert "seed 20261017, B_PLANT = 500" in g and E.SEED_PLANT == 20261017 and E.B_PLANT == 500
    assert "seed 20261018" in g and E.SEED_NULL_PLANT == 20261018
    assert "Normal(0, 0.5)" in g and E.PLANT_SD == 0.5
    assert "at least 5 challenges in each half" in g and E.N_MIN_HALF == 5
    assert "exceed 1 percent of rows" in g and E.BUDGET_VIOLATION_MAX == 0.01
    assert "1.645 x the bootstrap standard deviation" in g and E.Z95 == 1.645


def test_registration_precedes_results():
    g = GATE.read_text(encoding="utf-8")
    assert g.index("## 9. Results") < g.index("### 9.1 The stability check")


# ---------------------------------------------------------------- rows and values
def test_bases_bits_and_exclusions():
    assert E.bases_bits("___") == 0 and E.bases_bits("1_3") == 5 and E.bases_bits("123") == 7
    assert E.bases_bits("_2_") == 2 and E.bases_bits(None) == 0
    assert E.exclusion(_row()) is None
    assert E.exclusion(_row(challenge_side="fielding", original_call="B")) is None
    assert E.exclusion(_row(original_call="B")) == "call_side_mismatch"
    assert E.exclusion(_row(challenge_side="fielding", original_call="C")) == "call_side_mismatch"
    assert E.exclusion(_row(kind="check_swing")) == "not_zone"
    assert E.exclusion(_row(flags=["call_suspect"])) == "call_suspect"


@pytest.mark.skipif(not CV.exists(), reason="data/count_value.json is not built")
def test_challenge_value_is_the_called_pitch_value_and_never_negative():
    doc = json.loads(CV.read_text(encoding="utf-8"))
    t288, re24 = E.season_tables(doc, 2026)
    for b in range(4):
        for s in range(3):
            for base in range(8):
                for o in range(3):
                    code = "".join(str(i + 1) if base & (1 << i) else "_" for i in range(3))
                    v = E.challenge_value(_row(balls_before=b, strikes_before=s, bases_before=code, outs_before=o),
                                          t288, re24)
                    assert v == cv.called_pitch_value(t288, re24, b, s, base, o)
                    assert v >= 0
    # a full count with the bases loaded is worth more than 0-0 with them empty
    assert (E.challenge_value(_row(balls_before=3, strikes_before=2, bases_before="123"), t288, re24)
            > E.challenge_value(_row(), t288, re24))


def test_half_index_side_and_margin():
    assert E.half_index(1, "top") == 0 and E.half_index(1, "bottom") == 1
    assert E.half_index(9, "bottom") == 17 and E.half_index(10, "top") == 18 and E.half_index(13, "bottom") == 18
    assert E.club_side(_row(half="top", challenge_side="batting")) == "away"
    assert E.club_side(_row(half="top", challenge_side="fielding")) == "home"
    assert E.club_side(_row(half="bottom", challenge_side="batting")) == "home"
    assert E.club_side(_row(half="bottom", challenge_side="fielding")) == "away"
    assert E.club_margin(_row(bat_score_before=3, fld_score_before=1)) == 2
    assert E.club_margin(_row(challenge_side="fielding", original_call="B", bat_score_before=3, fld_score_before=1)) == -2
    assert [E.margin_bucket(m) for m in (-5, -3, -2, -1, 0, 1, 2, 3, 7)] == [0, 0, 1, 1, 2, 3, 3, 4, 4]


# ---------------------------------------------------------------- the budget
def test_budget_walk_spends_failures_keeps_successes_and_grants_extras():
    g = [_row(inning=1, at_bat_index=1, overturned=False),
         _row(inning=2, at_bat_index=9, overturned=True),
         _row(inning=3, at_bat_index=20, overturned=False),
         _row(inning=4, at_bat_index=30, overturned=False),     # none left: a violation
         _row(inning=10, at_bat_index=80, overturned=False),    # extra-inning grant
         _row(inning=11, at_bat_index=90, overturned=True)]     # granted again at the 11th
    assert E.budget_walk(g) == [2, 1, 1, 0, 1, 1]
    # input order does not matter; the home club has its own budget
    h = [_row(inning=2, half="bottom", at_bat_index=12, overturned=False),
         _row(inning=1, half="top", at_bat_index=0, overturned=False)]
    assert E.budget_walk(h) == [2, 2]


def test_half_points_future_value_and_budget():
    rows = [_row(inning=1, at_bat_index=1, overturned=False),
            _row(inning=2, at_bat_index=9, overturned=True)]
    halves = [(1, "top"), (1, "bottom"), (2, "top"), (2, "bottom")]
    scores = {(1, "top"): (0, 0), (1, "bottom"): (0, 0), (2, "top"): (1, 0), (2, "bottom"): (1, 0)}
    pts = E.half_points(rows, [2, 1], halves, scores, [0.3, 0.25])
    away = [p for i, p in enumerate(pts) if i % 2 == 0]
    home = [p for i, p in enumerate(pts) if i % 2 == 1]
    assert [p[1] for p in away] == [2, 1, 1, 1]
    assert [p[3] for p in away] == [0.25, 0.25, 0.25, 0.0]
    assert all(p[1] == 2 and p[3] == 0.0 for p in home)
    assert away[2][2] == E.margin_bucket(1) and home[2][2] == E.margin_bucket(-1)


def test_option_model_cost_is_the_midpoint_marginal_and_clipped():
    pts = [(0, 2, 2, 1.0)] * 10 + [(0, 1, 2, 0.4)] * 10 + [(1, 2, 2, 0.8)] * 10 + [(1, 1, 2, 0.6)] * 10
    m = E.OptionModel(pts, k_opt=0.0)
    assert m.cost(0, 2, 2) == pytest.approx(((1.0 - 0.4) + (0.8 - 0.6)) / 2)
    assert m.cost(0, 0, 2) == 0.0
    inv = E.OptionModel([(18, 2, 2, 0.0)] * 5 + [(18, 1, 2, 0.5)] * 5, k_opt=0.0)
    assert inv.cost(18, 2, 2) == 0.0                       # a negative marginal is clipped
    shrunk = E.OptionModel([(0, 2, 0, 2.0)] + [(0, 2, 2, 0.0)] * 99, k_opt=100.0)
    assert shrunk.v(0, 2, 0) == pytest.approx((2.0 + 100 * shrunk.v_hk(0, 2)) / 101)
    assert E.constant_cost(10.0, 50) == 0.1


# ---------------------------------------------------------------- players
def test_player_line_identities():
    items = [{"o": 1, "v": 0.3, "c": 0.05, "c0": 0.1, "p": 0.5},
             {"o": 0, "v": 0.2, "c": 0.04, "c0": 0.1, "p": 0.5},
             {"o": 0, "v": 0.1, "c": 0.02, "c0": 0.1, "p": 0.6}]
    ln = E.player_line(items)
    assert ln["n"] == 3 and ln["won"] == 1 and ln["lost"] == 2
    assert ln["rg"] == pytest.approx(0.3) and ln["fc"] == pytest.approx(0.06)
    assert ln["raw"] == pytest.approx(ln["rg"] - ln["fc"])
    expected = sum(x["p"] * x["v"] for x in items) - sum((1 - x["p"]) * x["c"] for x in items)
    assert ln["eabs"] == pytest.approx(ln["raw"] - expected)
    assert ln["x_ovr"] == pytest.approx((0.5 + 0.5 + 0.6) / 3)
    # a challenger exactly at the league rate scores 0
    flat = [{"o": 1, "v": 0.2, "c": 0.05, "c0": 0.1, "p": 1.0}]
    assert E.player_line(flat)["eabs"] == 0.0


def test_cell_rates_sum_to_zero_per_cell():
    rows = [_row(overturned=o, balls_before=b) for o, b in ((1, 0), (0, 0), (0, 0), (1, 3), (1, 3))]
    p = E.cell_rates(rows)
    sums = {}
    for r in rows:
        sums.setdefault(E.mix_cell(r), 0.0)
        sums[E.mix_cell(r)] += (1 if r["overturned"] else 0) - p[E.mix_cell(r)]
    assert all(abs(v) < 1e-12 for v in sums.values())


# ---------------------------------------------------------------- statistics
def test_spearman_matches_scipy_and_handles_ties():
    scipy_stats = pytest.importorskip("scipy.stats")
    x = [1, 2, 2, 3, 5, 4, 7, 7, 1]
    y = [2, 1, 3, 3, 6, 5, 6, 8, 0]
    assert E.spearman(x, y) == pytest.approx(scipy_stats.spearmanr(x, y)[0])
    assert E.spearman([1, 1, 1], [1, 2, 3]) is None
    assert E.spearman([1, 2], [1, 2]) is None


def test_pair_observations_floor_and_twin_permutes_within_pairs():
    items = lambda n, o: [{"o": o, "v": 0.2, "c0": 0.1, "p": 0.5}] * n  # noqa: E731
    by_ps = {(1, 2023): items(8, 1), (1, 2024): items(8, 0), (2, 2023): items(7, 1), (2, 2024): items(9, 1),
             (3, 2024): items(10, 1), (3, 2025): items(10, 0)}
    obs = E.pair_observations(by_ps, seasons=(2023, 2024, 2025))
    assert sorted((o[0], o[1]) for o in obs) == [(1, "2023-2024"), (3, "2024-2025")]
    assert obs[0][2] == pytest.approx(0.5 * 0.3)
    big = [(p, "a" if p < 50 else "b", float(p), float(p)) for p in range(100)]
    tw = E.permuted_twin(big, seed=1)
    assert sorted(o[3] for o in tw if o[1] == "a") == sorted(float(p) for p in range(50))
    assert [o[2] for o in tw] == [o[2] for o in big]


def test_bootstrap_and_holm_and_dispositions():
    obs = [(p, "x", float(p), float(p) + (p % 3)) for p in range(60)]
    b = E.bootstrap_rho(obs, b=200, seed=3)
    assert b["rho"] > 0.9 and b["lo95"] > 0.8 and b["p"] == 0.0 and b["mde95"] == pytest.approx(1.645 * b["sd"])
    assert E.holm({"a": 0.01, "b": 0.04}) == {"a": 0.02, "b": 0.04}
    assert E.holm({"a": 0.03, "b": 0.02}) == {"b": 0.04, "a": 0.04}
    real = {"rho": 0.3, "mde95": 0.1, "lo95": 0.2}
    ok_twin = {"rho": 0.0, "lo95": -0.1}
    plant = {"lo95": 0.2}
    null = {"lo95": -0.1}
    assert E.disposition(real, ok_twin, plant, null, 0.01) == "PERSISTS"
    assert E.disposition({"rho": 0.05, "mde95": 0.1}, ok_twin, plant, null, 0.01) == "SMALL"
    assert E.disposition(real, ok_twin, plant, null, 0.2) == "NULL"
    assert E.disposition(real, ok_twin, {"lo95": -0.01}, null, 0.01) == "UNDERPOWERED"
    assert E.disposition(real, {"rho": 0.2, "lo95": 0.05}, plant, null, 0.01) == "VOID"
    assert E.disposition(real, ok_twin, plant, {"lo95": 0.01}, 0.01) == "VOID"
    assert E.disposition(real, ok_twin, plant, null, 0.01, crashed=True) == "VOID"


# ---------------------------------------------------------------- the exporter
def _ledger(tmp_path, rows):
    fields = ["game_pk", "season", "game_type", "official_date", "inning", "half", "at_bat_index", "event_index",
              "kind", "challenge_org", "challenger_id", "role", "challenge_side", "overturned", "original_call",
              "balls_before", "strikes_before", "outs_before", "bases_before", "bat_score_before",
              "fld_score_before", "flags"]
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"fields": fields, "rows": [[r.get(f) for f in fields] for r in rows],
                             "names": {"10": "A Batter", "20": "A Catcher"}}), encoding="utf-8")
    return p


def _game(pk, fails_away=1):
    rows = []
    for j in range(fails_away):
        rows.append(_row(game_pk=pk, inning=1 + j, at_bat_index=j, challenger_id=10, role="batter",
                         challenge_org="NYY", official_date="2026-05-01", overturned=False))
    rows.append(_row(game_pk=pk, inning=5, half="top", at_bat_index=40, challenger_id=20, role="catcher",
                     challenge_side="fielding", original_call="B", challenge_org="NYY", balls_before=3,
                     strikes_before=2, bases_before="123", official_date="2026-05-01", overturned=True))
    return rows


@pytest.mark.skipif(not CV.exists(), reason="data/count_value.json is not built")
def test_exporter_builds_reconciles_and_writes_only_where_told(tmp_path):
    rows = _game(1) + _game(2, 2) + [_row(game_pk=3, original_call="B", challenger_id=10, role="batter")]
    halves = {g: [((i, h), (0, 0)) for i in range(1, 10) for h in ("top", "bottom")] for g in (1, 2, 3)}
    out = tmp_path / "out.json"
    p = X.build(_ledger(tmp_path, rows), CV, out_path=out, halves=halves, stability_path=tmp_path / "none.json")
    assert out.exists() and json.loads(out.read_text(encoding="utf-8"))["version"] == E.EABS_VERSION
    assert p["exclusions"] == {"call_side_mismatch": 1}
    assert p["invariants"]["reconcile"]["batter"] == {"ledger_n": 3, "board_n": 3, "ledger_won": 0, "board_won": 0}
    assert p["invariants"]["reconcile"]["catcher"]["board_won"] == 2
    assert p["stability"] is None
    bat = p["boards"]["batters"][0]
    assert bat["name"] == "A Batter" and bat["n"] == 3 and bat["rg"] == 0.0
    assert bat["raw"] == pytest.approx(-bat["fc"], abs=1e-3)
    cat = p["boards"]["catchers"][0]
    assert cat["won"] == 2 and cat["rg"] > 0 and cat["fc"] == 0.0
    assert p["values"]["club_games"] == 6
    assert p["values"]["c0"] == pytest.approx(cat["rg"] / 6 / 2, abs=1e-3)


@pytest.mark.skipif(not CV.exists(), reason="data/count_value.json is not built")
def test_exporter_refuses_a_broken_budget(tmp_path):
    rows = _game(1, 4)
    halves = {1: [((i, h), (0, 0)) for i in range(1, 10) for h in ("top", "bottom")]}
    with pytest.raises(E.EabsRefusal, match="budget walk"):
        X.build(_ledger(tmp_path, rows), CV, write=False, halves=halves)


@pytest.mark.skipif(not CV.exists(), reason="data/count_value.json is not built")
def test_stability_dry_run_reports_on_fixtures_with_nulls(capsys):
    import eabs_stability as S
    assert S.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DISPOSITION" in out and "MDE95" in out and "nothing written" in out
    assert out.index("MDE95") < out.index("] rho ")


def test_stability_artifact_matches_its_gate_entry():
    p = ROOT / "data" / "_labs" / "eabs" / "stability.json"
    if not p.exists():
        pytest.skip("the stability check has not run")
    doc = json.loads(p.read_text(encoding="utf-8"))
    g = GATE.read_text(encoding="utf-8")
    for role, label in (("batter", "Batters"), ("catcher", "Catchers")):
        r = doc["primary"][role]
        line = next(ln for ln in g.splitlines() if ln.startswith(f"| {label} |"))
        assert f"{r['real']['rho']:.4f}" in line and line.rstrip().endswith(f"| {r['disposition']} |")
        assert re.search(rf"\| {r['real']['mde95']:.4f} \|", line)
