"""Section 5k (docs/diamond-betting.md): the run-environment harness, on fixtures and on
pre-2026 data only. No test here reads a 2026 game, outcome or price.

Pins: the env_runs hook is bit-identical at its default and no served caller passes it;
nothing served calls run_environment_term; RUN_ENV_PRE2026 equals the Fitted block and a
re-run of the prefit; every choice under "Choices pinned"; the row rules; the window;
the guard; Holm and the labels; the report path on a fixture of None values (the one-look
crash protocol); and one end-to-end run of the lab on a synthetic league."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import random
import re
from pathlib import Path

import pytest

import betting_model as bm

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "diamond-betting.md"


def _fitted_block() -> str:
    s = DOC.read_text(encoding="utf-8")
    a = s.find("### Fitted (2026-10-14): the 5k pre-2026 constants")
    assert a >= 0, "the 5k Fitted block is missing"
    b = s.find("\n### ", a + 10)
    c = s.find("\n## 5l. ", a)
    return s[a:min(x for x in (b, c) if x > 0)]


# ---------------------------------------------------------------------------
# the served hook
# ---------------------------------------------------------------------------
def _teams():
    t = {"_scale": {"prev_mu": 100.0, "prev_sd": 6.0, "off_mu": 100.0, "off_sd": 8.0}}
    for i, org in enumerate(("AAA", "BBB")):
        t[org] = {"z_off": 0.3 - 0.6 * i, "offense_plus": 103 - 6 * i,
                  "bullpen_plus": 98 + 4 * i, "rotation_plus": 101 - 2 * i,
                  "sp_ip_share": 0.58}
    return t


COEFFS = {"b0": 4.4, "b1": 0.35, "b2": -0.3, "b3": 2.0, "b4": 0.05}


def test_env_runs_default_is_bit_identical():
    kw = dict(teams=_teams(), parks={"AAA": 1.02}, coeffs=COEFFS, home_adj=0.12,
              diff_shrink=0.8)
    a = bm.expected_runs("AAA", "BBB", **kw)
    b = bm.expected_runs("AAA", "BBB", env_runs=0.0, **kw)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_env_runs_moves_the_pair_mean_only():
    kw = dict(teams=_teams(), parks={"AAA": 1.02}, coeffs=COEFFS, home_adj=0.12,
              diff_shrink=0.8)
    a = bm.expected_runs("AAA", "BBB", **kw)
    b = bm.expected_runs("AAA", "BBB", env_runs=0.25, **kw)
    assert b["lam_home"] + b["lam_away"] == pytest.approx(a["lam_home"] + a["lam_away"] + 0.5)
    assert b["lam_home"] - b["lam_away"] == pytest.approx(a["lam_home"] - a["lam_away"])


ALLOWED_CALLERS = {"_re_split", "run_environment_gate"}


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []

    def walk(node, fn):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(ch, fn or ch.name)
                continue
            if isinstance(ch, ast.Call):
                name = getattr(ch.func, "id", None) or getattr(ch.func, "attr", None)
                kws = {k.arg for k in ch.keywords}
                if "env_runs" in kws or name == "run_environment_term":
                    out.append((fn, name, ch.lineno))
            walk(ch, fn)
    walk(tree, None)
    return out


def test_no_served_caller_passes_env_runs_or_calls_the_term():
    for p in sorted(ROOT.glob("*.py")):
        if p.name.startswith("test_") or p.name == "conftest.py":
            continue
        for fn, name, line in _calls(p):
            assert p.name == "betting_model.py" and fn in ALLOWED_CALLERS, (
                f"{p.name}:{line} {fn} reaches the dark 5k hook ({name})")


def test_served_modules_do_not_import_the_lab():
    for p in sorted(ROOT.glob("*.py")):
        if p.name.startswith("test_") or p.name in ("conftest.py", "betting_model.py"):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        assert "run_environment_gate" not in txt, p.name
        assert "RUN_ENV_PRE2026" not in txt, p.name


# ---------------------------------------------------------------------------
# the constants and the choices pinned
# ---------------------------------------------------------------------------
def test_literal_digest_is_its_own():
    lit = dict(bm.RUN_ENV_PRE2026)
    dig = lit.pop("digest")
    assert hashlib.sha256(json.dumps(lit, sort_keys=True).encode()).hexdigest()[:16] == dig


def test_literal_equals_the_fitted_block():
    blk = " ".join(_fitted_block().split())
    c = bm.RUN_ENV_PRE2026
    assert f"`{c['digest']}`" in blk
    assert f"**{c['k']['14']:.8f}**" in blk
    assert f"**{c['k']['30']:.8f}**" in blk
    assert f"A = **{c['month']['A']:.8f}**" in blk
    for m, v in c["month"]["offset"].items():
        assert f"**{v:.8f}**" in blk, m
    assert f"**{c['power']['sigma_T']:.6f}**" in blk
    for m, v in c["power"]["RMS_T"].items():
        assert f"{m} **{v:.6f}**" in blk, m
    assert c["k"]["14"] > 0 and c["k"]["30"] > 0 and c["month"]["A"] > 0


def test_choices_pinned():
    assert bm.RUN_ENV_WINDOWS == (14, 30)
    assert bm.RUN_ENV_WINDOW_FLOORS == {w: math.ceil(13.1 * w / 2) for w in (14, 30)}
    assert bm.RUN_ENV_WINDOW_FLOORS == {14: 92, 30: 197}
    assert bm.RUN_ENV_PREFIT_SEASONS == ("2018", "2019", "2021", "2022", "2023", "2024",
                                         "2025")
    assert sum(bm.RUN_ENV_CENSUS.values()) == 17008
    assert bm.RUN_ENV_MONTH_BINS == ("04", "05", "06", "07", "08", "09")
    assert (bm.RUN_ENV_BOOT_SEED, bm.RUN_ENV_BOOT_N) == (20260911, 1000)
    assert bm.RUN_ENV_TWIN_SEEDS == tuple(range(200))
    assert bm.RUN_ENV_TWIN_PERCENTILE == 95
    assert bm.RUN_ENV_FAMILY_ALPHA == 0.05
    assert bm.RUN_ENV_MEMBERS == ("5d-C", "5h-A", "5k-A14", "5k-A30", "5k-B")
    assert (bm.RUN_ENV_EARLIEST_READ, bm.RUN_ENV_LAST_READ) == ("2026-10-07", "2026-10-31")
    assert bm.RUN_ENV_READY_CUTOFF == "2026-09-28"
    assert bm.VINTAGE_MIN_FIT_GAMES == 100 and bm.VINTAGE_MIN_EVAL_GAMES == 50
    assert bm.DISPERSION_SPLIT_QUANTILES == (0.6, 0.7, 0.8)
    assert bm.RUN_ENV_5DC_STATUS["p"] == 1.0 and bm.RUN_ENV_5HA_STATUS["p"] == 1.0


@pytest.mark.skipif(not (ROOT / ".cache" / "betting" / "regular_finals" / "2025.json").exists(),
                    reason="the pre-2026 finals cache is not on this box")
def test_prefit_reproduces_the_literal(tmp_path):
    from tools import betting_run_env_prefit as pf
    res = pf.fit(fetch=False)
    assert res["literal"] == bm.RUN_ENV_PRE2026
    assert all(c["explained"] for c in res["census"])


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def _row(pk, date, h, a, inn=9, season="2026"):
    return {"game_pk": pk, "season": season, "date": date, "home_org": "AAA",
            "away_org": "BBB", "home_runs": h, "away_runs": a, "innings": inn}


def test_row_rules_in_order():
    rows = [_row(1, "2026-05-01", 3, 2), _row(1, "2026-05-01", 3, 2),
            _row(2, "2026-05-01", 1, 0, season="2025"), _row(3, "2026-05-01", 4, 4, inn=7),
            _row(4, "2026-05-01", 5, 1, inn=None), _row(5, "2026-05-02", 2, 6),
            _row(6, "2026-05-02", 2, 1)]
    kept, drops = bm.run_env_qualifying(rows, "2026",
                                        listings={1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 1})
    assert [r["game_pk"] for r in kept] == [1, 6]
    assert drops == {"duplicate_game_pk": 1, "season_not_requested": 1,
                     "innings_missing_or_below_9": 2, "resumed": 1}


def test_unresolved_resume_status_stops_the_build():
    with pytest.raises(bm.RunEnvStop, match="game_pk 9"):
        bm.run_env_qualifying([_row(9, "2026-05-01", 1, 2)], "2026", listings={})


def test_window_reads_strictly_before_d_and_holds_its_floor():
    daily = {}
    for k in range(1, 20):
        d = f"2026-06-{k:02d}"
        daily[d] = [90, 10]                     # 4.5 runs per team-game
    daily["2026-06-15"] = [1000, 10]            # the game's own date never enters
    w = bm.run_env_window(daily, "2026-06-15", 14)
    assert w["value"] == pytest.approx(4.5) and w["n_games"] == 140
    assert w["covers_through"] == "2026-06-14" and w["covers_through"] < "2026-06-15"
    thin = bm.run_env_window(daily, "2026-06-05", 14)
    assert thin["n_games"] == 40 and thin["value"] is None


def test_term_null_by_construction_and_below_floor():
    daily = {f"2026-06-{k:02d}": [90, 10] for k in range(1, 29)}
    c = {"k": {"14": -0.1, "30": 0.2}, "month": {"A": 0.0, "offset": {
        m: 0.0 for m in bm.RUN_ENV_MONTH_BINS}}}
    assert bm.run_environment_term("5k-A14", "2026-06-20", daily=daily, consts=c) is None
    assert bm.run_environment_term("5k-B", "2026-06-20", daily=daily, consts=c) is None
    assert bm.run_environment_term("5k-A30", "2026-06-20", daily=daily, consts=c) is None
    t = bm.run_environment_term("5k-A30", "2026-06-20", daily=daily, consts=bm.RUN_ENV_PRE2026,
                                center=4.4)
    assert t is None                                     # 190 games < 197
    t = bm.run_environment_term("5k-A14", "2026-06-20", daily=daily,
                                consts=bm.RUN_ENV_PRE2026, center=4.4)
    assert t["term"] == pytest.approx(bm.RUN_ENV_PRE2026["k"]["14"] * 0.1)
    assert t["provenance"]["source"] == "archive-reconstruct"
    b = bm.run_environment_term("5k-B", "2026-03-30", daily=daily, consts=bm.RUN_ENV_PRE2026,
                                center=0.01)
    assert b["month_bin"] == "04"
    assert b["term"] == pytest.approx(bm.RUN_ENV_PRE2026["month"]["offset"]["04"] - 0.01)
    assert bm.run_env_month_bin("2026-10-01") == "09"


def test_cluster_t_is_cr1_on_dates():
    d = [1.0, 2.0, 3.0, 5.0]
    dates = ["a", "a", "b", "b"]
    r = bm._re_cluster_t(d, dates)
    dbar = 2.75
    S = [(1 - dbar) + (2 - dbar), (3 - dbar) + (5 - dbar)]
    se = math.sqrt(2 / 1 * sum(x * x for x in S)) / 4
    assert r["G"] == 2 and r["t"] == pytest.approx(dbar / se)
    from scipy import stats
    assert r["p"] == pytest.approx(stats.t.sf(dbar / se, 1))
    assert bm._re_cluster_t([1.0], ["a"])["p"] == 1.0


def test_holm_and_labels():
    h = bm.holm_family({"5d-C": 0.004, "5h-A": 1.0, "5k-A14": 0.02, "5k-A30": 0.011,
                        "5k-B": 1.0})
    assert h["members"]["5d-C"]["rejected"] and h["members"]["5d-C"]["bar"] == 0.01
    assert h["members"]["5k-A30"]["rank"] == 2 and h["members"]["5k-A30"]["rejected"]
    assert h["members"]["5k-A14"]["rank"] == 3 and not h["members"]["5k-A14"]["rejected"]
    assert h["stopped_at_step"] == 3
    tie = bm.holm_family({k: 1.0 for k in bm.RUN_ENV_MEMBERS})
    assert [tie["members"][k]["rank"] for k in bm.RUN_ENV_MEMBERS] == [1, 2, 3, 4, 5]
    assert tie["stopped_at_step"] == 1
    lab = bm.re_member_label
    assert lab([0.001] * 4, 0.01, True, True, True, True) == "PASS"
    assert lab([0.5] * 4, 0.01, False, True, True, True) == "FAIL"
    assert lab([0.001, 0.5, 0.001, 0.001], 0.01, False, True, True, True) == "INDETERMINATE"
    assert lab([0.001] * 4, 0.01, False, True, True, True) == "FAIL (Holm stopped)"
    assert lab([0.001] * 4, 0.01, True, False, True, True) == "FAIL"


# ---------------------------------------------------------------------------
# the guard and the crash protocol
# ---------------------------------------------------------------------------
def test_guard_refuses_early_and_second_runs(tmp_path):
    rec = tmp_path / "rec.json"
    doc = tmp_path / "doc.md"
    doc.write_text("## 5k. x\n\n### Fitted (d)\n\n---\n\n## 5l. y\n", encoding="utf-8")
    assert "before" in bm.run_env_guard("2026-10-06", record_path=rec, doc_path=doc)
    assert bm.run_env_guard("2026-10-14", record_path=rec, doc_path=doc) is None
    rec.write_text("{}", encoding="utf-8")
    assert "already exists" in bm.run_env_guard("2026-10-14", record_path=rec, doc_path=doc)
    rec.unlink()
    doc.write_text("## 5k. x\n\n### Result (run 2026-10-14, once): FAIL\n\n## 5l. y\n",
                   encoding="utf-8")
    assert "result block" in bm.run_env_guard("2026-10-14", record_path=rec, doc_path=doc)


def test_report_path_tolerates_none():
    rec = {"read_date": None, "n_window": None, "n_gradable": None, "last_date": None,
           "grid": [{"split_q": None, "split_date": None, "n_fit": None, "n_eval": None,
                     "status": None, "members": {
                         "5k-A14": {"n_eval_with_term": None,
                                    "criterion_1": {"dbar": None, "t": None, "G": None,
                                                    "p": None},
                                    "criterion_2": {"delta_incumbent_minus_challenger": None},
                                    "twin": {"bar_p95": None, "beaten": None},
                                    "screen": {"dbar": None, "t": None}},
                         "5k-B": None}}],
           "holm": {"m": None, "stopped_at_step": None},
           "members": {"5k-A14": {"family_p": None, "computed_p": None, "label": None},
                       "5d-C": {"p": None, "label": None}}}
    lines = bm.run_env_report(rec)
    assert lines and all(isinstance(x, str) for x in lines)


def test_carry_forward_keeps_the_eval_key(tmp_path, monkeypatch):
    p = tmp_path / "eval.json"
    monkeypatch.setattr(bm, "EVAL_PATH", p)
    res = {"a": 1}
    bm._carry_run_environment(res)
    assert res == {"a": 1}
    p.write_text(json.dumps({"run_environment": {"m": 5}}), encoding="utf-8")
    bm._carry_run_environment(res)
    assert res["run_environment"] == {"m": 5}


# ---------------------------------------------------------------------------
# one end-to-end run on a synthetic league (no real game, outcome or price)
# ---------------------------------------------------------------------------
def _synthetic_league(n_dates=32, per_date=8, seed=7):
    rng = random.Random(seed)
    orgs = [f"T{i:02d}" for i in range(16)]
    teams = {"_scale": {"prev_mu": 100.0, "prev_sd": 6.0, "off_mu": 100.0, "off_sd": 8.0}}
    for o in orgs:
        teams[o] = {"z_off": rng.gauss(0, 1), "offense_plus": 100 + rng.gauss(0, 8),
                    "bullpen_plus": 100 + rng.gauss(0, 6),
                    "rotation_plus": 100 + rng.gauss(0, 6), "sp_ip_share": 0.58}
    games, pk = [], 900000
    for k in range(n_dates):
        date = f"2026-07-{k + 1:02d}" if k < 31 else f"2026-08-{k - 30:02d}"
        rng.shuffle(orgs)
        for j in range(per_date):
            h, a = orgs[2 * j], orgs[2 * j + 1]
            lam_h = max(1.5, 4.4 + 0.4 * teams[h]["z_off"])
            lam_a = max(1.5, 4.2 + 0.4 * teams[a]["z_off"])
            hr = sum(1 for _ in range(60) if rng.random() < lam_h / 60)
            ar = sum(1 for _ in range(60) if rng.random() < lam_a / 60)
            if hr == ar:
                hr += 1
            pk += 1
            games.append({"game_pk": pk, "season": "2026", "date": date, "home_org": h,
                          "away_org": a, "home_runs": hr, "away_runs": ar, "innings": 9,
                          "home_sp": None, "away_sp": None})
    return games, teams


def test_lab_end_to_end_on_a_synthetic_league(tmp_path, monkeypatch):
    games, teams = _synthetic_league()
    parks = {o: 1.0 for o in teams if not o.startswith("_")}

    def fake_resolver():
        return (lambda g: (teams, {}, parks)), {}

    monkeypatch.setattr(bm, "_vintage_resolver", fake_resolver)
    monkeypatch.setattr(bm, "_market_open_by_market", lambda need: {})
    monkeypatch.setattr(bm, "run_dispersion_alpha", lambda: None)
    monkeypatch.setattr(bm, "served_platt", lambda: None)
    monkeypatch.setattr(bm, "_re_roof_by_org", lambda games: {})
    doc = tmp_path / "doc.md"
    doc.write_text("## 5k. x\n\n## 5l. y\n", encoding="utf-8")
    rec_path = tmp_path / "rec.json"
    rec = bm.run_environment_gate(
        read_date="2026-10-14", games=games, teams=teams, parks=parks, starters={},
        listings={g["game_pk"]: 1 for g in games}, consts=bm.RUN_ENV_PRE2026,
        harness_first_ready="2026-10-14", record_path=rec_path, doc_path=doc,
        write_eval=False)
    assert rec_path.exists()
    on_disk = json.loads(rec_path.read_text(encoding="utf-8"))
    assert on_disk["holm"]["m"] == 5
    assert [r["status"] for r in rec["grid"]] == ["ran"] * 4
    a14 = rec["grid"][0]["members"]["5k-A14"]
    assert a14["twin"]["n"] == 200 and "criterion_1" in a14 and "screen" in a14
    assert "status" in rec["grid"][0]["members"]["5k-A30"]   # no fit-half 30-day term
    for m in ("5k-A14", "5k-A30", "5k-B"):
        assert rec["members"][m]["family_p"] == 1.0          # first ready after 09-28
        assert rec["members"][m]["label"] == "FAIL"
    assert rec["members"]["5d-C"]["label"].startswith("FAIL")
    assert rec["holm"]["stopped_at_step"] == 1
    assert bm.run_env_report(rec)
    with pytest.raises(bm.RunEnvStop, match="already exists"):
        bm.run_environment_gate(read_date="2026-10-14", games=games, teams=teams,
                                parks=parks, starters={}, record_path=rec_path,
                                doc_path=doc, write_eval=False)
