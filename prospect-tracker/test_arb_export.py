# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Contract tests for the /arbitration/ payloads and the model behind them.

Offline unit tests first, then shape tests that skip when the committed
artifacts are absent, so the suite stays green before the exporter has run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import arb_export as X
import arb_model as M

ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- #
# Model mechanics
# --------------------------------------------------------------------------- #

def test_the_max_cut_floor_is_a_transform_not_a_clamp():
    """The CBA caps an arbitration cut at 20%. Imposing that as a transformed
    target means EVERY prediction and every band endpoint is legal by
    construction; a clamp would fix the point estimate and leave the lower band
    arm dangling below a legally impossible value."""
    assert M.MAX_CUT_FLOOR == 0.795
    assert M.MAX_CUT_FLOOR < 0.80


def test_the_champion_never_sees_a_counting_stat():
    """Counting stats are what arbitration panels reward AND what nothing in
    this pipeline projects forward. Serving them would mean the forecast could
    not reproduce the backtest, so they are diagnostic-only by construction."""
    for banned in ("hr", "sb", "sv", "hld"):
        assert banned not in M.CHAMPION_KEYS
        assert banned in M.CEILING_KEYS


def test_raise_multipliers_fall_as_the_prior_salary_rises():
    """Measured on the scored pool: 1.70 under $2M down to 1.37 above $10M. A
    step-only multiplier ignores that and compounds a small-salary raise onto a
    large one, which took one player to a $48M arbitration award."""
    assert M._band(1_000_000) < M._band(3_000_000) < M._band(7_000_000) < M._band(20_000_000)


def test_paired_refuses_to_compare_different_populations():
    recs = [
        {"actual": 1.0, "champion": 1.0, "bar": 1.0},
        {"actual": 1.0, "champion": None, "bar": 1.0},   # champion abstains
        {"actual": 1.0, "champion": 1.0, "bar": None},
    ]
    assert len(M.paired(recs, "champion", "bar")) == 1


def test_smearing_is_applied_so_the_served_point_is_a_mean():
    """exp(mu_hat) alone understates every award by exp(s^2/2) - about 4.6% at a
    0.30 residual log-sd - which becomes a same-signed OVERSTATEMENT of surplus
    for every player downstream."""
    import inspect
    src = inspect.getsource(M.fit_stage1)
    assert "smear" in src and "np.exp(resid)" in src


# --------------------------------------------------------------------------- #
# Payload conventions
# --------------------------------------------------------------------------- #

def test_dollars_round_to_whole_thousands():
    assert X._k(2_325_400) == 2_325_000
    assert X._k(999) == 1_000
    assert X._k(None) is None


def test_flag_bits_are_distinct_powers_of_two():
    bits = [X.F_SERVICE_EST, X.F_CLASS_EST, X.F_NO_SALARY,
            X.F_CARRY_FWD, X.F_PRORATED]
    assert bits == [1, 2, 4, 8, 16]
    assert len(set(bits)) == len(bits)


def test_a_step_token_parses_super_two():
    assert X._token_step("ARB 2 (S2)") == (2, True)
    assert X._token_step("ARB 3") == (3, False)
    assert X._token_step("PRE-ARB") == (0, False)
    assert X._token_step("UFA")[0] is None


def test_the_cba_expiry_is_published_not_hardcoded_in_prose():
    assert X.CBA_EXPIRES == "2026-12-01"


# --------------------------------------------------------------------------- #
# Committed artifacts
# --------------------------------------------------------------------------- #

def _doc(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text("utf-8"))


def test_board_is_within_its_first_paint_budget():
    p = ROOT / "data" / "arbitration.json"
    if not p.exists():
        pytest.skip("not built")
    assert p.stat().st_size <= X.BOARD_CAP_BYTES


def test_history_is_within_its_budget():
    p = ROOT / "data" / "arb_history.json"
    if not p.exists():
        pytest.skip("not built")
    assert p.stat().st_size <= X.HISTORY_CAP_BYTES


def test_both_payloads_document_every_key_they_emit():
    """A two-letter key with no legend is a private format."""
    b = _doc("arbitration.json")
    assert b.get("field_key")
    for k in ("m", "n", "t", "e", "yl", "l", "tot"):
        assert k in b["field_key"], k
    h = _doc("arb_history.json")
    assert h.get("field_key", {}).get("rows")


def test_no_combined_residual_column_exists():
    """The two residuals answer different questions. One sums to roughly zero by
    construction and the other does not, so averaging them gives neither."""
    h = _doc("arb_history.json")
    assert "never_combine" in h["field_key"]
    src = (ROOT / "assets" / "arbitration.js").read_text("utf-8")
    import re
    assert not re.search(r"ou_?mkt\s*\+\s*ou_?war", src)
    assert not re.search(r"r\[8\]\s*\+\s*r\[9\]", src)


def test_the_board_carries_the_cba_expiry_because_the_rules_file_never_ships():
    """data/cba_rules.json is on deploy/data_exclude.txt, so the client can
    never fetch it and every CBA fact must be baked in or server-rendered."""
    b = _doc("arbitration.json")
    assert b["rules"]["expires"] == X.CBA_EXPIRES
    excl = (ROOT / "deploy" / "data_exclude.txt").read_text("utf-8")
    assert "cba_rules.json" in excl
    src = (ROOT / "assets" / "arbitration.js").read_text("utf-8")
    assert "cba_rules" not in src


def test_every_ladder_step_is_non_decreasing_except_at_the_max_cut():
    b = _doc("arbitration.json")
    bad = []
    for r in b["rows"]:
        prev = None
        for step in r.get("l") or []:
            usd = step[1]
            if usd is None:
                continue
            if prev is not None and usd < prev * 0.80:
                bad.append((r.get("n"), step[0], prev, usd))
            prev = usd
    assert not bad, f"ladder steps below the maximum cut: {bad[:5]}"


# --------------------------------------------------------------------------- #
# GATE C: pricing the club-control years the contract join leaves blank
# --------------------------------------------------------------------------- #

def test_gate_c_never_overwrites_a_real_contract():
    """It runs last and only touches rows that carry no surplus at all, so a
    projected arbitration salary can never displace a signed one."""
    import proj_export as PX
    rows = [
        {"mlbam": 1, "surNpv": 5, "war": [1.0] * 5},          # already priced
        {"mlbam": 2, "surTotal": 7, "war": [1.0] * 5},        # already priced
    ]
    PX._apply_arbitration_paths(rows, 1e7, 0.07)
    assert rows[0]["surNpv"] == 5 and rows[0]["salSrc"] == "contract"
    assert rows[1]["surTotal"] == 7 and rows[1]["salSrc"] == "contract"


def test_gate_c_stamps_provenance_on_everything_it_prices():
    """A reader must be able to tell a signed contract from a projection."""
    import inspect

    import proj_export as PX
    src = inspect.getsource(PX._apply_arbitration_paths)
    assert '"arb_projection"' in src and '"contract"' in src


def test_gate_c_runs_last_in_the_vet_builder():
    import inspect

    import proj_export as PX
    src = inspect.getsource(PX._veteran_rows)
    i = src.index("_apply_arbitration_paths(out, dpw, r)")
    # Every contract application must already have happened.
    assert src.rindex("_apply_contract(") < i


def test_gate_c_scope_limit_is_stated():
    """It prices players with an observed MLB record only. A never-debuted
    prospect has no prior salary, the raise model cannot run, and extrapolating
    a model fit on observed awards onto him is a documented prior failure."""
    import inspect

    import proj_export as PX
    doc = inspect.getdoc(PX._apply_arbitration_paths) or ""
    assert "never touches a prospect" in doc


def test_the_status_tables_never_grow_the_contract_set():
    """The Minor / retained tables are read for ARB tokens only. Folding them
    into contracts moves Nolan Arenado's AAV $5.5M -> $27.36M and Nick
    Castellanos's $0.3M -> $19.7M through the highest-AAV tiebreak, which is a
    contract-semantics question with its own blast radius on served trade
    values, not an arbitration one."""
    import spotrac
    assert "table" not in spotrac.CONTRACT_TABLE_IDS
    assert "table" in spotrac.STATUS_TABLE_IDS
    assert set(spotrac.CONTRACT_TABLE_IDS).isdisjoint(spotrac.STATUS_TABLE_IDS)


def test_the_eval_artifact_records_its_nulls():
    ev = _doc("arbitration_eval.json")
    assert ev.get("generated_at")
    assert isinstance(ev.get("verdict"), str)
    claims = " ".join(str(x.get("statement", "")) for x in ev.get("loss_ledger") or [])
    assert "NULL" in claims
