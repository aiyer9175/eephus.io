"""EFV3_A9_LABEL_HORIZON_2026 (docs/efv-v2/LABEL_HORIZON_2026.md): the counts are pinned to
the label builder and the read touched nothing reserved.

1. The per-cohort terms in data/efv_label_horizon_2026.json equal efv_dataset._label_6yr
   called under RESOLVED_THROUGH 2025 and 2026 (an empty seasons dict: calendar only),
   and the read's own matrices' stored weight, observed_seasons and censored flag equal
   the 2025 terms on every censored row (zero mismatches).
2. The per-(cohort, side) rows, censored rows and the 2021 move count reconcile to the
   matrices; the weight mass is rows times the builder's term plus the terminal rows.

The matrices the read was taken on are the pre-epoch ones: the fWAR label epoch's step F
rebuilt data/xfv_<side>_matrix.json under RESOLVED_THROUGH 2026 (86226bb2). Under
LABEL_HORIZON_2026.md section 10 ("A run after step D+U is a new read on the fWAR label
and a new section here, never an edit of the numbers above") the artifact and the doc
stay as they are, so the tests read the step A snapshot copies and verify each against
the artifact's own inputs.matrices[<side>].sha256.
3. The reserved guard raises for debut cohorts 2020, 2021, 2025 and 2026; the artifact's
   outcome cohorts are 2014 to 2019 and its newest season read is 2024; the window sum
   refuses a season past 2024.
4. Every correlation block is label-to-label (no rater key under it), no key names an
   FV cell, no em-dash anywhere, and the views resolve on the documented rule.
5. The document carries the artifact's headline numbers, and no label-horizon row was
   appended to data/efv_progress.json.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

TOOL = ROOT / "tools" / "efv_label_horizon_2026.py"
ART = ROOT / "data" / "efv_label_horizon_2026.json"
DOC = ROOT / "docs" / "efv-v2" / "LABEL_HORIZON_2026.md"
PROG = ROOT / "data" / "efv_progress.json"

_FV_CELL = re.compile(
    r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])|tier|fv_cell|fv_bucket", re.I)
_RATER = re.compile(r"efv|consensus|prospx|fangraphs|pipeline|rater|grade", re.I)


def _tool():
    spec = importlib.util.spec_from_file_location("efv_label_horizon_2026", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def T():
    return _tool()


@pytest.fixture(scope="module")
def doc():
    if not ART.exists():
        pytest.skip("data/efv_label_horizon_2026.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def _git_root(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def _pre_epoch_snapshot() -> Path | None:
    """The fWAR label epoch's step A snapshot folder (files flat, read only).

    PRE_EPOCH_FWAR_SNAPSHOT wins. Otherwise the main checkout: in a linked worktree the
    .git FILE reads 'gitdir: <main>/.git/worktrees/<name>', which gives <main>; in the
    main checkout .git is the directory itself. The snapshot is <main>/_pre_epoch_fwar_2026-10."""
    env = os.environ.get("PRE_EPOCH_FWAR_SNAPSHOT")
    if env:
        return Path(env)
    root = _git_root(ROOT)
    if root is None:
        return None
    dotgit = root / ".git"
    main = root
    if dotgit.is_file():
        line = dotgit.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            return None
        gitdir = Path(line[len("gitdir:"):].strip())
        if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
            return None
        main = gitdir.parent.parent.parent
    return main / "_pre_epoch_fwar_2026-10"


@pytest.fixture(scope="module")
def mats(T, doc):
    """The matrices the read was taken on, pinned by the artifact's own input hashes.
    Skips (named reason) only when no snapshot file is found; a hash mismatch fails."""
    snap = _pre_epoch_snapshot()
    paths = {}
    for s in T.SIDES:
        want = doc["inputs"]["matrices"][s]
        p = snap / Path(want["path"]).name if snap is not None else None
        if p is None or not p.is_file():
            pytest.skip(f"no pre-epoch snapshot copy of {Path(want['path']).name} "
                        f"(set PRE_EPOCH_FWAR_SNAPSHOT; looked in {snap})")
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want["sha256"]:
            pytest.fail(f"{p} sha256 {got} is not the read's input {want['sha256']}")
        paths[s] = p
    return T.load_matrices(paths)


def _direct_terms(cohort: int, rt: int) -> tuple[int, float, bool]:
    saved = D.RESOLVED_THROUGH
    try:
        D.RESOLVED_THROUGH = rt
        _r, _c, censored, weight, n_obs = D._label_6yr({}, cohort)
    finally:
        D.RESOLVED_THROUGH = saved
    return int(n_obs), float(weight), bool(censored)


def _walk_keys(o, out: list) -> list:
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_keys(v, out)
    return out


# ---------------------------------------------------------------------------
# 1. the terms are the builder's

def test_terms_are_the_label_builders_own(T, doc):
    # 86226bb2 (the fWAR label epoch) moved the module clock to the read's RT_AFTER.
    assert T.RT_BEFORE == 2025 and T.RT_AFTER == 2026
    assert D.RESOLVED_THROUGH == T.RT_AFTER
    assert D.SERVICE_ALIGNED_WINDOW is False
    for rt in (T.RT_BEFORE, T.RT_AFTER):
        for c in T.TERM_COHORTS:
            if c > rt - 1:
                assert str(c) not in doc["builder_terms"][str(rt)]
                continue
            n_obs, weight, censored = _direct_terms(c, rt)
            got = doc["builder_terms"][str(rt)][str(c)]
            assert got["observed_seasons"] == n_obs, (rt, c)
            assert got["weight"] == pytest.approx(weight, abs=1e-9), (rt, c)
            assert got["censored"] is censored, (rt, c)
            assert got["observed_fraction"] == pytest.approx(n_obs / D.TARGET_SEASONS, abs=1e-3)
            assert T.builder_terms(c, rt) == got
    # the documented shape of the move: 2021 resolves, 2022 to 2024 gain one season, 2025 enters
    t25, t26 = doc["builder_terms"]["2025"], doc["builder_terms"]["2026"]
    assert t25["2021"]["censored"] is True and t26["2021"]["censored"] is False
    for c in ("2022", "2023", "2024"):
        assert t26[c]["observed_seasons"] == t25[c]["observed_seasons"] + 1
    assert "2025" not in t25 and t26["2025"] == {"observed_seasons": 2, "observed_fraction": 0.333,
                                                  "weight": 0.333, "censored": True}


def test_builder_terms_restore_the_clock(T):
    before = D.RESOLVED_THROUGH
    T.builder_terms(2024, 2026)
    assert D.RESOLVED_THROUGH == before


def test_stored_matrix_terms_equal_the_2025_terms(T, doc, mats):
    assert doc["cohorts"]["pins_against_stored_matrix_terms"] == {
        "weight": 0, "observed_seasons": 0, "censored_flag": 0}
    checked = 0
    for s in T.SIDES:
        for r in mats[s]:
            c = int(r.get("debut_year") or 0)
            if c not in T.COHORTS or not r.get("censored"):
                continue
            n_obs, weight, censored = _direct_terms(c, T.RT_BEFORE)
            assert censored is True
            assert float(r["weight"]) == pytest.approx(weight, abs=1e-9), (s, c, r["player_key"])
            assert int(r["observed_seasons"]) == n_obs, (s, c, r["player_key"])
            checked += 1
    assert checked == sum(doc["cohorts"]["totals"][s]["censored_rows_2025"] for s in T.SIDES)
    assert checked > 800


# ---------------------------------------------------------------------------
# 2. the counts reconcile to the matrices

def test_rows_and_moves_reconcile_to_the_matrices(T, doc, mats):
    by = {(r["debut_cohort"], r["side"]): r for r in doc["cohorts"]["rows"]}
    assert set(by) == {(c, s) for c in T.COHORTS for s in T.SIDES}
    for (c, s), row in by.items():
        rs = [r for r in mats[s] if int(r.get("debut_year") or 0) == c]
        cens = [r for r in rs if r.get("censored")]
        assert row["rows"] == len(rs)
        assert row["censored_rows_at_2025"] == len(cens)
        t25, t26 = doc["builder_terms"]["2025"][str(c)], doc["builder_terms"]["2026"][str(c)]
        expect_moves = len(cens) if (t25["censored"] and not t26["censored"]) else 0
        assert row["moves_censored_to_resolved_at_2026"] == expect_moves
        resolved = len(rs) - len(cens)
        assert row["rt_2025"]["weight_mass_all"] == pytest.approx(
            resolved * 1.0 + len(cens) * t25["weight"], abs=0.01)
        assert row["rt_2026"]["weight_mass_all"] == pytest.approx(
            resolved * 1.0 + len(cens) * t26["weight"], abs=0.01)
    tot = doc["cohorts"]["totals"]
    for s in T.SIDES:
        assert tot[s]["rows_censored_to_resolved_at_2026"] == by[(2021, s)]["censored_rows_at_2025"]
        assert tot[s]["delta_weight_mass_all"] == pytest.approx(
            tot[s]["weight_mass_all_2026"] - tot[s]["weight_mass_all_2025"], abs=0.01)
        assert tot[s]["delta_weight_mass_all"] > 0


def test_fold_mass_is_cumulative_over_cohorts(T, doc):
    rows = doc["cohorts"]["rows"]
    for fold in doc["folds"]:
        y = fold["fold"]
        for s in T.SIDES:
            tr = [r for r in rows if r["side"] == s and r["debut_cohort"] < y]
            assert fold[s]["train_rows"] == sum(r["scored_rows"] for r in tr)
            assert fold[s]["train_mass_2026"] >= fold[s]["train_mass_2025"]


def test_margin_arithmetic_is_the_sqrt_rule(T, doc):
    m = doc["margin_arithmetic"]["sides"]
    for s in T.SIDES:
        side = m[s]
        ratio = side["W_before"] / side["W_after"]
        assert side["mde95_onesided_after"] == pytest.approx(
            side["mde95_onesided_ref"] * ratio ** 0.5, abs=1e-4)
        assert side["mde95_onesided_after"] < side["mde95_onesided_ref"]
        assert side["mde95_onesided_after"] > 0.02, "the advance alone resolves nothing new"


# ---------------------------------------------------------------------------
# 3. the reserved guard

@pytest.mark.parametrize("cohort", [2020, 2021, 2025, 2026])
def test_outcome_guard_raises_for_reserved_cohorts(T, cohort):
    with pytest.raises(T.ReservedCohortError):
        T.outcome_guard(cohort)


def test_outcome_cohorts_and_seasons_read(T, doc):
    assert doc["guards"]["outcome_cohorts_read"] == list(range(2014, 2020))
    assert doc["guards"]["max_season_read"] == 2024 == T.MAX_SEASON_READ
    assert set(doc["guards"]["reserved_debut_cohorts_never_read"]) >= {2020, 2021,
                                                                        F.R_VM_FIRST_DEBUT_YEAR}
    assert doc["guards"]["reserved_vm_pins"] == []
    assert doc["guards"]["no_rater_score"] is True
    lv = doc["label_views"]
    assert lv["outcome_cohorts_read"] == list(range(2014, 2020))
    for v in lv["views"].values():
        for prov in v["correlation_with_l6"].values():
            for c in prov.values():
                assert c["cohorts"] == list(range(2014, 2020))
    vint = doc["label"]["frozen_fwar_vintage"]
    if vint:
        assert vint["seasons_read_here"][1] == 2024


def test_window_sum_refuses_a_season_past_2024(T):
    with pytest.raises(T.ReservedCohortError):
        T._window_sum({}, 2020, 6)
    with pytest.raises(T.ReservedCohortError):
        T._window_sum({}, 2023, 3)
    assert T._window_sum({2019: 1.5, 2024: 2.0, 2025: 9.0}, 2019, 6) == 3.5


def test_fwar_reader_is_never_asked_for_2025_or_2026(T, monkeypatch):
    import fwar_vintage as FV
    asked = []

    def fake(blob, season, group):
        asked.append(int(season))
        return {}
    monkeypatch.setattr(FV, "war_by_group", fake)
    T.fwar_series({"seasons": {}}, {1, 2}, "hitting")
    assert asked and max(asked) == 2024 and min(asked) == 2014


# ---------------------------------------------------------------------------
# 4. label-to-label only, no FV cell, no em-dash, the resolution rule

def test_correlations_are_label_to_label_and_no_key_names_an_fv_cell(doc):
    bad = sorted({k for k in _walk_keys(doc, []) if _FV_CELL.search(k)})
    assert not bad, f"keys naming an FV cell or tier: {bad}"
    for name, v in doc["label_views"]["views"].items():
        for prov, by in v["correlation_with_l6"].items():
            assert prov in ("ewar_v2", "fwar_frozen")
            for s, c in by.items():
                assert c["label_to_label"] is True
                assert not [k for k in _walk_keys(c, []) if _RATER.search(k)], (name, prov, s)
                assert c["n"] >= 300 and c["B"] == 2000 and c["seed"] == 20260906
                lo, hi = c["spearman_ci95"]
                assert lo <= c["spearman"] <= hi
                assert 0.5 < c["spearman"] < 1.0


def test_views_resolve_on_the_documented_rule(T, doc):
    views = doc["label_views"]["views"]
    assert set(views) == {"first3", "first4"}
    for name, k in T.VIEWS.items():
        v = views[name]
        assert v["k"] == k
        for rt in (2025, 2026):
            assert v["resolved_cohorts"][str(rt)] == [c for c in T.COHORTS if c + k - 1 <= rt]
            assert v["l6_resolved_cohorts"][str(rt)] == [c for c in T.COHORTS if c + 5 <= rt]
            beyond = v["rows_beyond_l6"][str(rt)]
            assert beyond["cohorts"] == sorted(set(v["resolved_cohorts"][str(rt)])
                                               - set(v["l6_resolved_cohorts"][str(rt)]))
    assert views["first3"]["resolved_cohorts"]["2026"][-1] == 2024
    assert views["first4"]["resolved_cohorts"]["2026"][-1] == 2023
    # the first-k share of six-season mass: the copied profile and the rows agree in direction
    for name, lo, hi in (("first3", 0.35, 0.5), ("first4", 0.55, 0.7)):
        share = views[name]["share_of_six_season_mass"]
        assert lo < share["censoring_gate_profile"]["first_k_share"] < hi
        for val in share["development_rows"].values():
            assert lo < val < hi


def test_no_emdash_in_artifact_doc_tool_and_test():
    for p in (ART, DOC, TOOL, Path(__file__)):
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            assert chr(0x2014) not in txt and chr(0x2013) not in txt, p.name


# ---------------------------------------------------------------------------
# 5. the document carries the artifact's numbers; no ledger row

def test_document_carries_the_artifact_numbers(doc):
    assert DOC.exists()
    txt = DOC.read_text(encoding="utf-8")
    tot = doc["cohorts"]["totals"]
    assert f"{tot['hit']['rows_censored_to_resolved_at_2026']} hitter and " \
           f"{tot['pit']['rows_censored_to_resolved_at_2026']} pitcher" in txt
    for s in ("hit", "pit"):
        for key in ("weight_mass_all_2025", "weight_mass_all_2026"):
            assert str(tot[s][key]) in txt, (s, key)
        m = doc["margin_arithmetic"]["sides"][s]
        assert str(m["mde95_onesided_after"]) in txt
    for name in ("first3", "first4"):
        for s in ("hit", "pit"):
            c = doc["label_views"]["views"][name]["correlation_with_l6"]["ewar_v2"][s]
            assert str(c["spearman"]) in txt, (name, s)
    assert "SECONDARY" in txt and "six-year value" in txt


def test_no_label_horizon_row_in_the_progress_ledger(doc):
    assert doc["progress_ledger"]["appended"] is False
    if PROG.exists():
        rows = json.loads(PROG.read_text(encoding="utf-8"))["rows"]
        assert not [r for r in rows if r.get("model_id") == "efv_label_horizon"]
