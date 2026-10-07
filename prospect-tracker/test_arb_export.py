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
            X.F_CARRY_FWD, X.F_PRORATED, X.F_ORDER_FIX]
    assert bits == [1, 2, 4, 8, 16, 32]
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
    # every key a row carries is in the legend, the link token included
    emitted = set().union(*(r.keys() for r in b["rows"])) if b["rows"] else set()
    assert emitted <= set(b["field_key"]), emitted - set(b["field_key"])
    h = _doc("arb_history.json")
    assert h.get("field_key", {}).get("rows")
    width = len(h["field_key"]["rows"].strip("[]").split(","))
    assert all(len(r) == width for r in h["rows"]), width


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
    """THE SINGLE INVARIANT THE WHOLE 2026-09-16 CHANGE TURNS ON, and it moved
    from the ROW to the SEASON without moving in intent.

    Until ask C the guarantee was "a row that already carries a surplus is
    skipped wholesale", which is what left 408 veterans on a one-year 2026 deal
    with their 2027-2028 arbitration steps unread. The guarantee now is "a
    SEASON a contract prices is never re-priced", which is strictly stronger per
    season and strictly weaker per row - exactly the change that was wanted.

    Three cases, in the order they matter:
      1. a season a contract prices keeps the contract's dollars even when the
         status grid carries a token for that same season (a token must never
         beat dollars);
      2. a season AFTER the contract must take the board's step, which is the
         behaviour that did not exist before;
      3. the old letter, kept: a row whose grid is entirely inside `thru` takes
         nothing from the board at all.
    """
    import salary_path as sp

    def steps(*rows):
        return {"steps": [{"season": s, "usd": u, "lo": u, "hi": u, "tok": k}
                          for s, u, k in rows]}

    # 1 + 2: contracted 2027, arbitration-projected 2028. The board's step for
    # 2028 clears 80% of the contracted 2027 salary, so nothing but rule 1 and
    # rule 2 is in play here.
    p = sp.salary_path(1, first_season=2027, horizon=5, mode="ladder",
                       contract={"salary_by_year": {2027: 9_500_000},
                                 "signed_through": 2027},
                       board_row=steps((2027, 4_000_000, "ARB 2"),
                                       (2028, 9_000_000, "ARB 3")))
    assert p["seasons"][0]["src"] == "contract" and p["seasons"][0]["usd"] == 9_500_000
    assert p["seasons"][1]["src"] == "arb_ladder" and p["seasons"][1]["usd"] == 9_000_000

    # 2b: the ONE rule that may override a board step, and it raises rather
    # than lowers. CBA Article VI: an award may not cut a salary by more than
    # 20%, and the board chains off its own panel's prior salary, so it cannot
    # see an extension paying more. A $6.0M projection beside a contracted
    # $9.5M is not an award; it is floored at $7.6M and flagged.
    f = sp.salary_path(1, first_season=2027, horizon=5, mode="ladder",
                       contract={"salary_by_year": {2027: 9_500_000},
                                 "signed_through": 2027},
                       board_row=steps((2027, 4_000_000, "ARB 2"),
                                       (2028, 6_000_000, "ARB 3")))
    assert f["seasons"][1]["src"] == "arb_ladder"
    assert f["seasons"][1]["usd"] == 7_600_000 and f["seasons"][1]["cba_floor"]
    assert f["cba_floored"] == 1

    # 3: the old case. Everything the grid offers is already bought out.
    q = sp.salary_path(1, first_season=2027, horizon=5, mode="ladder",
                       contract={"salary_by_year": {2027: 9_500_000,
                                                    2028: 10_000_000},
                                 "signed_through": 2028},
                       board_row=steps((2027, 4_000_000, "ARB 2"),
                                       (2028, 6_000_000, "ARB 3")))
    assert {c["src"] for c in q["seasons"] if c["usd"]} == {"contract"}

    # and the row-level half of the old rule still governs the "off" revert.
    import proj_export as PX
    rows = [
        {"mlbam": 1, "surNpv": 5, "war": [1.0] * 5},          # already priced
        {"mlbam": 2, "surTotal": 7, "war": [1.0] * 5},        # already priced
    ]
    PX._legacy_arbitration_paths(rows, 1e7, 0.07)
    assert rows[0]["surNpv"] == 5 and rows[0]["salSrc"] == "contract"
    assert rows[1]["surTotal"] == 7 and rows[1]["salSrc"] == "contract"


def test_gate_c_stamps_provenance_on_everything_it_prices():
    """A reader must be able to tell a signed contract from a projection."""
    import inspect

    import proj_export as PX
    src = inspect.getsource(PX._apply_salary_paths)
    assert '"arb_projection"' in src and '"contract"' in src
    assert '"contract+arb"' in src and '"pending"' in src


def test_gate_c_runs_last_in_the_vet_builder():
    import inspect

    import proj_export as PX
    src = inspect.getsource(PX._veteran_rows)
    i = src.index("_apply_salary_paths(out, dpw, r, _ct_final)")
    # Every contract application must already have happened, AND the pass must
    # be handed the contract set the rows actually got. `_ct_by_mlbam` leaves a
    # CONTESTED Spotrac key out on purpose and the collision-winner loop applies
    # it afterwards, so passing the assigned map showed the path ct=None for
    # exactly the row that had just taken a contract.
    assert src.rindex("_apply_contract(") < i
    assert "_ct_final[winner[\"mlbam\"]] = ct" in src


def test_gate_c_scope_limit_is_stated():
    """It prices players with an observed MLB record only. A never-debuted
    prospect has no prior salary, the raise model cannot run, and extrapolating
    a model fit on observed awards onto him is a documented prior failure."""
    import inspect

    import proj_export as PX
    doc = inspect.getdoc(PX._legacy_arbitration_paths) or ""
    assert "never touches a prospect" in doc
    # The rule itself lives in salary_path.py now, and its docstring is where a
    # reader looking for "why is this prospect not priced?" will land.
    import salary_path
    assert "never prices a never-debuted prospect" in (salary_path.__doc__ or "")


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


# --------------------------------------------------------------------------- #
# sv: published service time on the board (ask C commit 1, 2026-09-16)
# --------------------------------------------------------------------------- #

def test_the_panel_carries_published_service_time_to_the_board():
    """`sv` asked `build_panel` for `service_time` and got None on all 852 rows,
    because nothing ever emitted it. Nothing reads it today, so populating it
    moves no served number; what it unblocks is GATE C2's C9', the only external
    check on the control horizon."""
    import inspect

    import arb_dataset as A
    src = inspect.getsource(A.build_panel)
    assert '"service_time":' in src and '"service_years":' in src


def test_the_board_documents_sv_because_it_now_carries_one():
    board = _doc("arbitration.json")
    key = board.get("field_key") or {}
    assert "sv" in key and "service time" in key["sv"].lower()
    assert "STRING" in key["sv"], "a float lies about .043 being 43/1000"

# --------------------------------------------------------------------------- #
# Forward rungs are built the way training rows are (2026-09-24, M08-01;
# docs/ARBITRATION_GATE.md section 11h)
# --------------------------------------------------------------------------- #

def _spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


def test_a_forward_arb1_rung_reads_built_features_not_zeros(monkeypatch):
    """A pre-arb player's latest panel row is not a scored row, so it carries
    no war3/career_war, and the rung's own season is in the future, so the
    metric lookup keyed on it found nothing. Both used to fall to features()'
    defaults (0.0 and 100) on every forward ARB 1 rung."""
    import arb_dataset as A
    panel = [
        {"mlbam": 7, "season": 2024, "war": 1.0, "name": "P", "team": "AAA",
         "age": 22.0, "pa": 300, "ipouts": 0, "gs": 0, "salary": None},
        {"mlbam": 7, "season": 2025, "war": 3.0, "name": "P", "team": "AAA",
         "age": 23.0, "pa": 600, "ipouts": 0, "gs": 0, "salary": None},
        {"mlbam": 7, "season": 2026, "war": 4.0, "name": "P", "team": "AAA",
         "age": 24.0, "pa": 640, "ipouts": 0, "gs": 0, "salary": None},
    ]
    monkeypatch.setattr(A, "spotrac_status_by_mlbam",
                        lambda: {7: {2027: "PRE-ARB", 2028: "ARB 1"}})
    monkeypatch.setattr(A, "league_min_by_year",
                        lambda: {2025: 760000.0, 2026: 780000.0})
    monkeypatch.setattr(X, "_projected_war", lambda: {7: [2027, [5.0, 6.0]]})
    seen = []

    def spy(row, metrics_by, defl, s1, s2):
        seen.append((dict(row), M._mx(metrics_by, row)))
        return 1_000_000.0

    monkeypatch.setattr(M, "predict", spy)
    metrics = {2026: {7: {"hem": 130.0, "sem": 100.0, "rem": 100.0}}}
    X.build_board(panel, {}, metrics, {}, season=2027, s1={"keys": []},
                  defl={2026: 1.0}, banded={})
    assert len(seen) == 1
    row, mx = seen[0]
    assert row["season"] == 2028
    # award season inclusive: 2028 proj 6.0 + 2027 proj 5.0 + 2026 realized 4.0
    assert row["war3"] == 15.0
    # realized 1 + 3 + 4 through 2026, then projected 5 + 6 through 2028
    assert row["career_war"] == 19.0
    assert row["age"] == 26.0
    assert mx and mx["hem"] == 130.0, "metrics must come from the latest observed season"
    # the PRE-ARB rung before it sets the prior at the league minimum
    assert row["prior_salary"] == 780000.0


def test_a_first_trip_with_no_salary_on_file_raises_off_the_league_minimum(monkeypatch):
    import arb_dataset as A
    panel = [{"mlbam": 9, "season": 2026, "war": 2.0, "name": "Q", "team": "BBB",
              "age": 26.0, "pa": 500, "ipouts": 0, "gs": 0, "salary": None}]
    monkeypatch.setattr(A, "spotrac_status_by_mlbam", lambda: {9: {2027: "ARB 1"}})
    monkeypatch.setattr(A, "league_min_by_year", lambda: {2026: 780000.0})
    monkeypatch.setattr(X, "_projected_war", lambda: {9: [2027, [2.5]]})
    seen = []
    monkeypatch.setattr(M, "predict",
                        lambda row, *a: seen.append(dict(row)) or 500_000.0)
    out = X.build_board(panel, {}, {}, {}, season=2027, s1={"keys": []},
                        defl={2027: 1.0}, banded={})
    assert seen[0]["prior_salary"] == 780000.0
    # and no award is served below the league minimum
    assert out["rows"][0]["l"][0][1] == 780000


def _arb1_rungs(board):
    out = []
    for r in board.get("rows") or []:
        w = r.get("w") or []
        for i, s in enumerate(r.get("l") or []):
            if str(s[4]).startswith("ARB 1") and s[1]:
                out.append((s[0], s[1], w[i] if i < len(w) else None, r.get("c")))
    return out


def test_served_arb1_rungs_respond_to_projected_war():
    """The zeroed-feature board ranked its ARB 1 rungs against projected WAR at
    Spearman 0.151 (n 187), and the four rungs projected at 3+ WAR were among
    the cheapest. The backtest with full features ranks at 0.546 (arb_history
    ours vs war, n 361)."""
    b = _doc("arbitration.json")
    rungs = [t for t in _arb1_rungs(b) if t[2] is not None]
    if len(rungs) < 30:
        pytest.skip("too few projected ARB 1 rungs to rank")
    assert _spearman([t[1] for t in rungs], [t[2] for t in rungs]) >= 0.35
    direct = [t for t in rungs if t[3] == 1]
    if len(direct) >= 20:
        assert _spearman([t[1] for t in direct], [t[2] for t in direct]) >= 0.35


def test_served_arb1_rungs_have_a_star_tail():
    """The level check reads the backtest's own full-feature predictions (ours,
    column 6), not realized awards, so it never tunes against the 2026 pool
    GATE C2 clause C2' scores."""
    b = _doc("arbitration.json")
    h = _doc("arb_history.json")
    served = sorted(t[1] for t in _arb1_rungs(b))
    ours = sorted(r[6] for r in h["rows"] if r[4] == 1 and r[6])
    if len(served) < 30 or len(ours) < 30:
        pytest.skip("pools too small")
    p90 = served[int(round(0.9 * (len(served) - 1)))]
    p75 = ours[int(round(0.75 * (len(ours) - 1)))]
    assert p90 >= p75, (p90, p75)
    lm = min(s[1] for r in b["rows"] for s in r["l"] if s[4] == "PRE-ARB" and s[1])
    low = [t for t in _arb1_rungs(b) if t[2] is not None and t[2] >= 3 and t[1] < 2 * lm]
    assert not low, f"3+ WAR ARB 1 rungs priced under twice the league minimum: {low}"
    assert all(t[1] >= lm for t in _arb1_rungs(b)), "an award below the league minimum"
