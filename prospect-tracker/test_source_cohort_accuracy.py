"""Tests for source_cohort_accuracy: the PROPERTIES, not the numbers.

Every number in data/source_cohort_accuracy.json moves with the data vintage. The rules do
not, and it is the rules that make the artifact honest:

  * `answerable` is False wherever abs(d_rho) < mde95. That equivalence is the whole
    deliverable: the lane publishes "not resolvable" instead of a sign.
  * `cohort_ab.ship` is the INCUMBENT gate (0.0068 / 0.0052, lifted from source_backtest)
    applied to the measured deltas, and it is tested on BOTH sides: a null fixture where
    the two sources are exchangeable and no arm can pass, and a signal fixture where a
    cohort weight genuinely helps and every arm does pass. Tested on the null alone the
    assertion was vacuous - a module that hardcoded ship=False would have satisfied it.
  * The lane reports and never ships: `ships_a_weight` stays False even in the run whose
    gate passes, the module writes exactly one artifact, and data/source_weights.json and
    data/draft_source_weights.json are byte-identical afterwards.
  * Two runs on a frozen fixture are byte-identical apart from the timestamp. That pins the
    seeds, the iteration orders and the EM's pattern ordering.
  * No board year at or before the last outcome-resolved year can carry a vintage-legal
    precision weight, so the precision route cannot be A/B-tested on this data.
  * The EM solver returns a non-Heywood solution on the fixture.
  * The archetype Spearmans reproduce source_backtest.

The real-data reproduction test reads the SHIPPED artifact rather than recomputing the
7,322-player universe, so it costs a file read. The binding reproduction leg is computed
inside the module (`reproduction.matches_source_backtest_code`) and asserted here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import source_cohort_accuracy as sca

DATA = Path(__file__).parent / "data"
ARTIFACT = DATA / "source_cohort_accuracy.json"
PARTITIONS = ("by_side", "by_acquisition", "by_archetype", "by_position_group",
              "by_fv_tier", "by_age_at_grading")

# Digested at IMPORT, which is before any fixture has run the module. The weights files
# are what a shipped weight would land in; see test_the_repo_weights_files_are_untouched.
_WEIGHTS_AT_IMPORT = {
    name: hashlib.sha256((DATA / name).read_bytes()).hexdigest()
    for name in ("source_weights.json", "draft_source_weights.json")
    if (DATA / name).exists()
}


# --------------------------------------------------------------------------
# Frozen fixture: a synthetic universe with a known factor structure.
# --------------------------------------------------------------------------
def _fixture_universe(n_players: int = 420, seed: int = 4242,
                      sd_fg_arm: float = 3.0, sd_mp_arm: float = 3.0,
                      sd_fg_bat: float = 3.0, sd_mp_bat: float = 3.0,
                      key_prefix: str = "p",
                      third_instrument: bool = True) -> tuple[dict, list[dict]]:
    """Deterministic synthetic prospects: latent quality -> three noisy graders -> WAR.

    Built with a fixed seed and a fixed field order so the whole pipeline (row build,
    bootstrap, EM, permutations) is reproducible. Grades are quantized to the 5-point
    lattice because the Sheppard column and the range-restriction checks are about the
    quantized grade the aggregator actually sees.

    The four sd knobs set each scored source's noise SEPARATELY BY SIDE, which is what
    lets the same generator produce both arms of the cohort-weight test. All four equal
    (the default) makes FanGraphs and MLB Pipeline exchangeable, so no cohort weight can
    help; making them differ by side plants a real cohort effect. See test_no_weight_ships.
    """
    rng = np.random.default_rng(seed)
    positions = ("SS", "C", "OF", "3B", "RHP", "LHP", "SP", "RP")
    active, graduated = [], []
    for i in range(n_players):
        mu = float(rng.normal())
        pos = positions[i % len(positions)]
        intl = (i % 5) == 0
        birth = 2000 + (i % 6)
        draft_year = birth + (19 if (i % 3) else 22)
        acq = ({"method": "international_fa", "year": birth + 16} if intl
               else {"method": "draft", "year": draft_year})
        war = max(0.0, 3.0 * mu + rng.normal(scale=1.5))
        debuted = war > 0.4
        arm = pos in ("RHP", "LHP", "SP", "RP")
        sd_fg = sd_fg_arm if arm else sd_fg_bat
        sd_mp = sd_mp_arm if arm else sd_mp_bat
        points = []
        for year in (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026):
            per = {}
            for src, load, sd in (("fangraphs", 5.0, sd_fg), ("mlb_pipeline", 5.0, sd_mp),
                                  ("baseballamerica", 4.5, 3.5)):
                if src == "baseballamerica" and (year < 2023 or not third_instrument):
                    continue
                if (i + year) % 7 == 0:            # deliberate missingness for the EM
                    continue
                fv = 45.0 + load * mu + rng.normal(scale=sd)
                per[src] = {"rank": None, "fv_published": float(round(fv / 5.0) * 5.0)}
            if not per:
                continue
            cons = sum(v["fv_published"] for v in per.values()) / len(per)
            points.append({"snapshot_date": f"{year}-02-15",
                           "consensus_fv_raw": round(cons, 2),
                           "sources_contributing": sorted(per),
                           "per_source": per})
        rec = {"player_key": f"{key_prefix}{i:04d}", "player_name": f"Player {i}",
               "position": pos, "birth_date": f"{birth}-05-01",
               "acquisition": acq, "points": points}
        if debuted:
            rec["debut_date"] = "2024-06-01"
            rec["status"] = "debuted"
            rec["career_war"] = {"career_war": round(war, 2), "war_per_yr": round(war / 2, 2)}
            graduated.append(rec)
        else:
            rec["status"] = "active"
            active.append(rec)
    return {"players": active}, graduated


def _write_universe(d: Path, ts: dict, deb: list[dict]) -> Path:
    (d / "timeseries.json").write_text(json.dumps(ts), encoding="utf-8")
    (d / "debuts.json").write_text(json.dumps(deb), encoding="utf-8")
    return d


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory) -> Path:
    return _write_universe(tmp_path_factory.mktemp("sca_fixture"), *_fixture_universe())


@pytest.fixture(scope="module")
def fixture_result(fixture_dir) -> dict:
    return sca.run_source_cohort_accuracy(data_dir=fixture_dir, write=True)


@pytest.fixture(scope="module")
def signal_dir(tmp_path_factory) -> Path:
    """A universe where a cohort weight GENUINELY helps: FanGraphs is the sharp rater on
    arms (sd 1.0 against Pipeline's 7.0) and Pipeline is the sharp rater on bats. Same
    generator, same size, same missingness; only the noise allocation differs."""
    return _write_universe(
        tmp_path_factory.mktemp("sca_signal"),
        *_fixture_universe(seed=90210, sd_fg_arm=1.0, sd_mp_arm=7.0,
                           sd_fg_bat=7.0, sd_mp_bat=1.0, key_prefix="s"))


@pytest.fixture(scope="module")
def signal_result(signal_dir) -> dict:
    return sca.run_source_cohort_accuracy(data_dir=signal_dir, write=True)


# --------------------------------------------------------------------------
# The properties
# --------------------------------------------------------------------------
def _scored_cells(res: dict):
    acc = res["accuracy"]
    out = [("pooled", acc["pooled"])]
    for part in PARTITIONS:
        for label, cell in (acc.get(part) or {}).items():
            out.append((f"{part}:{label}", cell))
    return [(name, c) for name, c in out if isinstance(c, dict) and c.get("scored")]


def test_answerable_is_exactly_the_mde_rule(fixture_result):
    cells = _scored_cells(fixture_result)
    assert cells, "fixture produced no scored cells"
    for name, c in cells:
        expected = abs(c["d_rho"]) >= c["mde95"]
        assert c["answerable"] is expected, (
            f"{name}: answerable={c['answerable']} but abs(d_rho)={abs(c['d_rho'])} "
            f"vs mde95={c['mde95']}")
        if not c["answerable"]:
            assert c["winner"] == "not_resolvable", f"{name} names a winner it cannot resolve"


def test_no_weight_ships(fixture_result, signal_result, signal_dir):
    """TWO ARMS, because one of them cannot fail on its own.

    The null fixture gives FanGraphs and MLB Pipeline the same loading and the same noise,
    so they are exchangeable and NO cohort weight can help: `ship is False` there is a
    property of the fixture, not of the gate. Measured on it, the six arms land at d_rho
    -0.00617 to -0.00898 and the fitted alphas never leave [0.486, 0.523].

    The signal fixture plants a real cohort effect (sd 1.0 against 7.0, opposite by side)
    and the gate FIRES on it: all six arms clear both floors, best d_rho about +0.043
    against a 0.0068 gate and d_auc about +0.024 against 0.0052, with side alphas at
    ~0.59 (arms) and ~0.42 (bats). That is the arm that catches a gate wired shut.

    What must hold in BOTH is the lane's actual contract: this module reports and never
    ships. `ships_a_weight` stays False even when the A/B gate passes, and the only file
    it writes is its own artifact. data/source_weights.json is byte-checked because that
    is the file a shipped weight would land in.
    """
    for label, res in (("null", fixture_result), ("signal", signal_result)):
        ab = res["cohort_ab"]
        # The gate must be the incumbent constants, not a floor invented for this lane.
        assert ab["gate"]["min_d_rho"] == 0.0068, label
        assert ab["gate"]["min_d_auc"] == 0.0052, label
        # `ship` is the gate applied to the measured deltas, on every arm and in the roll-up.
        for name, arm in ab["arms"].items():
            if arm.get("d_rho") is None:
                continue
            assert arm["ship"] is (arm["d_rho"] >= 0.0068 and arm["d_auc"] >= 0.0052), \
                f"{label}:{name} ship flag does not follow its own gate"
        assert ab["ship"] is any(a.get("ship") for a in ab["arms"].values()), label
        # The lane never ships, whatever the A/B says.
        assert res["ships_a_weight"] is False, label

    # NULL arm: exchangeable sources, so nothing can pass and nothing does.
    null_ab = fixture_result["cohort_ab"]
    assert null_ab["ship"] is False
    assert all(a["d_rho"] < 0.0068 for a in null_ab["arms"].values()
               if a.get("d_rho") is not None)

    # SIGNAL arm: a cohort weight really does help, and the gate says so. Without this the
    # assertion above is vacuous: a module that hardcoded ship=False would pass it.
    sig_ab = signal_result["cohort_ab"]
    assert sig_ab["ship"] is True, "the ship gate never fires, so it is not being tested"
    assert all(a["ship"] is True for a in sig_ab["arms"].values()
               if a.get("d_rho") is not None)
    best = sig_ab["arms"][sig_ab["best_arm"]]
    assert best["d_rho"] > 0.03 and best["d_auc"] > 0.015, best
    # and the weights the arm fitted are far from equal, i.e. the machinery engaged.
    side = sig_ab["arms"]["side_shrunk"]["per_year"]
    assert side, "the side arm scored no year"
    assert max(abs(py["alpha_fg"]["arm"] - 0.5) for py in side) > 0.05, side
    assert max(abs(py["alpha_fg"]["bat"] - 0.5) for py in side) > 0.05, side

    # ... and even in that run the module wrote ONE artifact and no weights file.
    assert sorted(p.name for p in signal_dir.iterdir()) == [
        "debuts.json", "source_cohort_accuracy.json", "timeseries.json"]
    assert not (signal_dir / "source_weights.json").exists()
    assert not (signal_dir / "draft_source_weights.json").exists()


def test_the_repo_weights_files_are_untouched(fixture_result, signal_result):
    """The two shipped weight files are BYTE-IDENTICAL after two full runs of this module,
    one of which passed the A/B gate. Digested at import, i.e. before any fixture ran.

    run_source_cohort_accuracy writes into its data_dir argument, so an edit that reached
    for the module-level DATA_DIR instead - the way a weight would actually escape - lands
    here instead of in production."""
    assert _WEIGHTS_AT_IMPORT, "neither weights file exists; this test would be vacuous"
    for name, digest in sorted(_WEIGHTS_AT_IMPORT.items()):
        now = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        assert now == digest, f"{name} was rewritten by this lane; it ships no weight"


def test_two_runs_are_byte_identical(fixture_dir, fixture_result):
    """Pins every seed and every iteration order. Only the wall clock may differ."""
    volatile = ("generated_at", "as_of_date")
    again = sca.run_source_cohort_accuracy(data_dir=fixture_dir, write=False)
    a = {k: v for k, v in fixture_result.items() if k not in volatile}
    b = {k: v for k, v in again.items() if k not in volatile}
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_precision_route_cannot_be_ab_tested_before_2024(fixture_result):
    va = fixture_result["precision_label_free"]["vintage_availability"]
    # A board year can carry a vintage-legal precision weight only when an estimable year
    # sits at or before Y - MIN_LAG_YEARS. No such year is also outcome-resolved, so the
    # two sets are disjoint. Structural, not a power problem.
    assert all(y > 2023 for y in va["weightable_board_years"]), va["weightable_board_years"]
    assert va["overlap_with_ab_eligible"] == []
    assert all(y <= 2023 for y in va["ab_eligible_board_years"])


def test_em_solver_returns_a_non_heywood_solution(fixture_result):
    em = fixture_result["precision_label_free"]["estimator_primary_em_fiml"]
    assert em["heywood"] is False
    assert all(s > 0 for s in em["sigma"])
    assert all(0.0 < r < 1.0 for r in em["reliability"])
    # The GLS weight is b / sigma^2, not 1 / sigma^2. A source with a larger loading and the
    # same noise must weigh more.
    b, sig2 = em["b"], em["sigma2"]
    for i in range(3):
        assert em["gls_weight"][i] == pytest.approx(b[i] / sig2[i], rel=1e-3)
    # Sheppard is reported and NOT netted out of the weight.
    assert fixture_result["precision_label_free"]["sheppard"]["subtracted_from_weight"] is False


def test_two_sources_are_not_identified(fixture_result):
    assert fixture_result["precision_label_free"]["two_source_identification"]["identified"] is False


def test_the_precision_block_reports_unidentified_when_the_third_instrument_is_gone(
        tmp_path_factory):
    """With no third instrument the block must SAY it cannot estimate, not crash and not
    guess.

    This is a live operating state, not a hypothetical: Baseball America is subscription
    content ingested from owner-supplied pastes, so every re-ingest opens a window with
    zero BA rows (2026-08-10 was one, when all four seasons were purged for a re-download).
    Before the guard the module raised `need at least one array to concatenate` three
    frames deep in an empty player bootstrap, which reads as a code fault rather than as
    absent evidence.

    The accuracy half must be UNAFFECTED, because it never scored the third instrument -
    Baseball America is deliberately outside SCORED_SOURCES. That half of the assertion is
    the one that would catch a leak.
    """
    d = _write_universe(tmp_path_factory.mktemp("sca_no_third"),
                        *_fixture_universe(third_instrument=False))
    res = sca.run_source_cohort_accuracy(data_dir=d, write=True)

    p = res["precision_label_free"]
    assert p["identified"] is False
    assert p["n_third_instrument_rows"] == 0
    assert p["third_instrument"] not in p["sources_present"]
    # It must not emit any estimate a reader could mistake for a measurement.
    for leaked in ("estimator_primary_em_fiml", "complete_case", "gls_weight",
                   "alpha_fg", "sigma", "reliability"):
        assert leaked not in p, leaked
    assert "restores_when" in p

    # The accuracy conclusions stand without the third instrument.
    assert res["ships_a_weight"] is False
    assert res["cohort_ab"]["ship"] is False
    assert res["accuracy"]["pooled"], "the accuracy half must still be computed"


def test_fv_tier_block_carries_its_range_restriction_warning(fixture_result):
    warn = fixture_result["accuracy"]["by_fv_tier_range_restriction_warning"]
    assert "range restriction" in warn
    assert fixture_result["accuracy"]["level_at_grading"]["available"] is False
    assert fixture_result["accuracy"]["level_at_grading"]["substitute"] == "age_at_grading"


def test_coverage_block_builds_no_selection_model(fixture_result):
    cov = fixture_result["accuracy"]["coverage_selection"]
    assert cov["selection_model"]["built"] is False
    for s, rec in cov["per_source"].items():
        assert rec["rows_common"] <= rec["rows_own"], s


def test_multiplicity_reports_a_family_level_test(fixture_result):
    het = fixture_result["multiplicity"]["archetype_heterogeneity"]
    assert het["df"] == het["k"] - 1
    assert 0.0 <= het["chi2_p"] <= 1.0
    assert 0.0 <= het["permutation_p_labels"] <= 1.0
    assert het["i2_percent"] >= 0.0


# --------------------------------------------------------------------------
# Reproduction against source_backtest, on the shipped artifact
# --------------------------------------------------------------------------
@pytest.mark.skipif(not ARTIFACT.exists(), reason="data/source_cohort_accuracy.json not built")
def test_shipped_artifact_reproduces_source_backtest():
    res = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    rep = res["reproduction"]
    # BINDING leg: source_backtest._archetype_accuracy recomputed on this lane's rows.
    assert rep["matches_source_backtest_code"] is True, rep["code_diffs"]
    # INFORMATIONAL leg: the served source_backtest.json can predate its own inputs (it did
    # on 2026-08-09: artifact 13:56, timeseries.json 14:24). Where the cell n agrees, the
    # Spearmans must agree too; where the n disagrees, the artifact is stale and says so.
    sb_path = DATA / "source_backtest.json"
    if sb_path.exists() and rep.get("served_diffs"):
        for d in rep["served_diffs"]:
            assert d.get("n_mine") != d.get("n_served"), (
                "same cell population but a different Spearman: this is a real divergence, "
                f"not staleness: {d}")


@pytest.mark.skipif(not ARTIFACT.exists(), reason="data/source_cohort_accuracy.json not built")
def test_shipped_artifact_answerable_rule_and_no_ship():
    res = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for name, c in _scored_cells(res):
        assert c["answerable"] is (abs(c["d_rho"]) >= c["mde95"]), name
    assert res["cohort_ab"]["ship"] is False
    assert res["ships_a_weight"] is False
    assert res["produced_by"] == sca.PRODUCED_BY
    assert res["generated_at"].endswith("Z") and len(res["generated_at"]) >= 20


@pytest.mark.skipif(not ARTIFACT.exists(), reason="data/source_cohort_accuracy.json not built")
def test_shipped_artifact_precision_vintages_are_disjoint_from_the_ab():
    p = json.loads(ARTIFACT.read_text(encoding="utf-8"))["precision_label_free"]
    if p.get("identified") is False:
        # The third instrument is absent, which is a real operating state between a
        # Baseball America purge and its re-ingest. Assert the block reports that
        # honestly instead of asserting on estimates it correctly refused to make.
        assert p["n_third_instrument_rows"] < p["min_rows_required"]
        assert "vintage_availability" not in p
        pytest.skip(f"third instrument absent: {p['reason'][:60]}")
    va = p["vintage_availability"]
    assert va["overlap_with_ab_eligible"] == []
    assert all(y > max(va["ab_eligible_board_years"]) for y in va["weightable_board_years"])
