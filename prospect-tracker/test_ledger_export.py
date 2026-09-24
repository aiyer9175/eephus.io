# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /ledger/ payload (Club Ledger, D1, 2026-09-23).

THE POINT OF THIS PAGE IS WHAT IT REFUSES TO SAY. It is a ledger of what each club
has on the books, owes and controls, and the mistakes these tests exist for are the
ones that would turn a ledger into a forecast or an income statement:

  1. A SINGLE PROJECTED PAYROLL. Contract dollars on file, projected arbitration
     steps and pre-arbitration minimums are three keys; no key sums them and the
     page never prints the sum. A club payroll forecast would need registry row
     club_payroll_path and the 2016-2025 payroll history as labels, and has neither.
  2. MIXING THE TWO 2027 CBT BASES. Spotrac's 2027 page computes space against
     247,000,000; cba_rules carries 244,000,000 forward as explicitly-unknown. Both
     ship, each named; a cell never holds one on the other's basis.
  3. COLOURING A COST. A salary cell, a club surplus total and a cap-space cell take
     no ladder; only Cost+ and OrgSur+ (100+10z) take the z ladder.
  4. COMBINING ou_mkt AND ou_war. The arbitration history artifact says never_combine.
  5. SERVING REVENUE, ATTENDANCE MONEY, TV MONEY OR VALUATIONS. No source carries
     them; the not-claimed list says so and the writer refuses the keys.
  6. LETTING A DARK BLOCK LOOK LIKE A BUG. Every dark section names its blocker.

The payload is read once per module; build() is exercised under a socket ban and
NEVER writes (conftest deletes any data/ file a test creates).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "ledger_board.json"
PAGE = ROOT / "ledger" / "index.html"
JS = ROOT / "assets" / "ledger.js"
CSS = ROOT / "assets" / "ledger.css"

SITE_CODES = {"KCR": "KC", "CHW": "CWS", "WSN": "WSH", "ATH": "ATH", "SFG": "SF",
              "SDP": "SD", "TBR": "TB", "ARI": "AZ"}


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python ledger_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def proj():
    p = ROOT / "data" / "mlb_projections.json"
    if not p.exists():
        pytest.skip("mlb_projections.json absent")
    return json.loads(p.read_text(encoding="utf-8"))


def _walk(obj, path=""):
    """(path, key, value) for every dict key in the document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, k, v
            yield from _walk(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _leaves(obj):
    """Every numeric leaf in a block, lists included."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield obj


# --------------------------------------------------------------------------
# The join and the reference row
# --------------------------------------------------------------------------

def test_thirty_clubs_and_only_thirty_after_the_canonical_join(d):
    clubs = set(d["clubs"])
    assert len(clubs) == 30 and len(d["league"]["rows"]) == 30
    assert set(SITE_CODES) <= clubs, "site canonical codes on every key"
    for bad in ("OAK", "Cuba", "AVERAGES", "KC", "CWS", "WSH", "AZ", "SD", "SF", "TB"):
        assert bad not in clubs, bad
    oj = d["accountability"]["org_join"]
    assert oj["fa_meta"][1] == 30 and oj["trade_values"][1] == 30 and oj["arb_history"][1] == 30
    assert oj["fa_meta"][0] > 30, "fa_meta carries AVERAGES and OAK before the join"
    assert "Cuba" in oj["trade_values_dropped"], "the 31st trade_values org is Cuba and it is dropped"
    assert d["accountability"]["n_clubs"] == 30


def test_the_averages_row_is_a_reference_and_not_a_club(d):
    av = d["league"]["averages_row"]
    assert av["label"] and "AVERAGES" not in d["clubs"]
    assert all(r["club"] != "AVERAGES" for r in d["league"]["rows"])
    pool = d["league"]["pools"]["cost_plus"]
    assert pool["averages_excluded"] is True and pool["n"] == 30
    assert d["accountability"]["averages_excluded"] is True


# --------------------------------------------------------------------------
# Mistake 1: no single projected payroll
# --------------------------------------------------------------------------

def test_no_key_serves_a_single_projected_payroll(d):
    for path, k, _v in _walk(d):
        ks = str(k).lower()
        assert "projected_payroll" not in ks and "payroll_forecast" not in ks, path
    s = d["sections"]["single_payroll_line"]
    assert s["live"] is False and "club_payroll_path" in s["blocked_on"]
    assert "not served" in d["copy"]["no_payroll_line"]


def test_contract_dollars_and_arbitration_steps_are_two_keys_never_summed(d):
    fk = d["field_key"]["commitments.by_season"]
    assert "NO SUM" in fk
    for c, club in d["clubs"].items():
        K = club["commitments"]
        vals = set(_leaves(K))
        for row in K["by_season"]:
            season, a, _na, b, _nb, p, _np, _cliff = row
            assert isinstance(a, int) and isinstance(b, int) and isinstance(p, int)
            for total in (a + b + p, a + b, a + p):
                if total and total not in (a, b, p):
                    assert total not in vals, (c, season, total, "a sum of the segments reached the payload")
        assert "n_unpriced" in K and K["n_priced"] + K["n_unpriced"] == K["n_vets"]


def test_unpriced_vets_are_counted_per_club_beside_the_timeline(d, proj):
    from trades import canonical_org
    unpriced = {}
    for v in proj["vets"]:
        c = canonical_org(v.get("team"))
        if c in d["clubs"]:
            unpriced[c] = unpriced.get(c, 0) + (0 if v.get("salPath") else 1)
    for c, club in d["clubs"].items():
        assert club["commitments"]["n_unpriced"] == unpriced.get(c, 0), c
        assert club["contracts"]["n_unpriced"] == len(club["contracts"]["unpriced"]) == unpriced.get(c, 0)
    assert sum(unpriced.values()) == sum(1 for v in proj["vets"] if not v.get("salPath"))


# --------------------------------------------------------------------------
# Mistake 2: the two CBT bases, and the CBA banner on every 2027 dollar
# --------------------------------------------------------------------------

def test_space_2027_names_its_basis_spotrac_247m_and_platform_244m(d):
    import fa_cba
    import ledger_export as L
    T27 = fa_cba.cbt_threshold(d["class_year"])["threshold_usd"]
    assert fa_cba.cbt_threshold(d["class_year"])["carry_forward"] is True
    assert L.SPOTRAC_2027_BASIS_USD != T27, "the two bases differ, which is why both are named"
    for c, club in d["clubs"].items():
        sp = club["payroll"]["space_2027"]
        tax = club["payroll"]["s2027"]["tax_payroll_usd"]
        assert sp["spotrac_basis_usd"] == L.SPOTRAC_2027_BASIS_USD
        assert sp["platform_basis_usd"] == T27
        if tax is not None:
            assert sp["spotrac_usd"] + tax == sp["spotrac_basis_usd"], c
            assert sp["platform_usd"] + tax == sp["platform_basis_usd"], c
    assert d["cba"]["spotrac_2027_basis_usd"] == L.SPOTRAC_2027_BASIS_USD
    assert d["cba"]["threshold_by_season"][str(d["class_year"])] == T27
    lab = d["copy"]["space_2027_spotrac_label"] + d["copy"]["space_2027_platform_label"]
    assert str(L.SPOTRAC_2027_BASIS_USD // 1_000_000) in lab and str(T27 // 1_000_000) in lab


def test_every_2027_plus_dollar_block_carries_the_cba_banner(d):
    assert d["cba"]["banner_text"] and d["cba"]["expiry"] in d["cba"]["banner_text"]
    assert d["copy"]["cba_banner"] == d["cba"]["banner_text"]
    for c, club in d["clubs"].items():
        for blk in ("payroll", "commitments", "contracts", "arbitration", "fa", "indexes"):
            assert club[blk].get("cba_banner") is True, (c, blk)
        assert club["cbt"][str(d["class_year"])]["cba_banner"] is True, c
        assert club["cbt"][str(d["class_year"])]["carry_forward"] is True
    assert d["league"]["cba_banner"] is True and d["rules"]["cba_banner"] is True


# --------------------------------------------------------------------------
# The CBT computation is the rule table, never a typed rate
# --------------------------------------------------------------------------

def test_the_computed_cbt_bill_reproduces_the_rate_table():
    import fa_cba
    import ledger_export as L
    T = fa_cba.cbt_threshold(2026)["threshold_usd"]
    rates = fa_cba.cbt_tax_rates()
    tiers = fa_cba.cbt_surcharge_tiers()
    base = rates["base_rate_by_payor_year"]
    sur = rates["surcharge_rates"]
    t1, t2, t3 = tiers
    for tier, bkey in (("Non-Tax", "1"), ("1st-Time", "1"), ("2nd-Time", "2"), ("3+-Time", "3+")):
        b = base[bkey]
        s2 = sur["tier2_first"] if bkey == "1" else sur["tier2_repeat"]
        for over_m in (10, 30, 50, 70):
            over = over_m * 1_000_000
            got = L.computed_cbt_bill(T + over, T, tier, rates, tiers)
            expect = (b * min(over, t1)
                      + (b + sur["tier1"]) * max(0, min(over - t1, t2 - t1))
                      + (b + s2) * max(0, min(over - t2, t3 - t2))
                      + (b + sur["tier3"]) * max(0, over - t3))
            assert got["bill_usd"] == int(round(expect)), (tier, over_m, got, expect)
            assert got["over_usd"] == over
        assert L.computed_cbt_bill(T, T, tier, rates, tiers)["bill_usd"] == 0
        assert L.computed_cbt_bill(T - 1, T, tier, rates, tiers)["bracket"] == "under"
    assert L.computed_cbt_bill(T + t1, T, "1st-Time", rates, tiers)["bracket"] == "base"
    assert L.computed_cbt_bill(T + t1 + 1, T, "1st-Time", rates, tiers)["bracket"] == "surcharge_1"
    assert L.computed_cbt_bill(T + t3 + 1, T, "1st-Time", rates, tiers)["bracket"] == "surcharge_3"
    assert L.computed_cbt_bill(None, T, "1st-Time", rates, tiers)["bill_usd"] is None


def test_the_computed_bill_prints_beside_spotrac_where_spotrac_has_one(d):
    n = 0
    for c, club in d["clubs"].items():
        est = club["payroll"]["s2026"]["est_tax_bill_usd"]
        blk = club["cbt"][str(d["season_now"])]
        if est:
            n += 1
            assert blk["spotrac_est_bill_usd"] == est
            assert blk["diff_usd"] == blk["computed_bill_usd"] - est
            assert blk["over_usd"] > 0 and blk["bracket"] != "under", c
    assert n >= 1, "Spotrac carries an estimate for its payors"
    assert n == sum(1 for r in d["league"]["rows"] if r["est_tax_2026"] is not None)


def test_a_non_payor_prints_blank_not_zero_for_the_spotrac_estimate(d):
    n = 0
    for c, club in d["clubs"].items():
        blk = club["cbt"][str(d["season_now"])]
        if blk["over_usd"] is not None and blk["over_usd"] <= 0:
            n += 1
            assert blk["computed_bill_usd"] == 0 and blk["bracket"] == "under"
            assert blk["spotrac_est_bill_usd"] is None, (c, "blank, never zero")
    for r in d["league"]["rows"]:
        assert r["est_tax_2026"] != 0, r["club"]
    assert n >= 1
    assert d["copy"]["cbt_under"]


def test_the_2026_split_is_not_drawn_when_the_source_is_null(d):
    for c, club in d["clubs"].items():
        s26 = club["payroll"]["s2026"]
        assert s26["split"] is None and s26["split_available"] is False, c
    js = JS.read_text(encoding="utf-8")
    assert "s2026.split" not in js and "p27.split_available" in js
    assert d["copy"]["split_2026_note"]


def test_the_2027_payor_tier_is_spotrac_where_present_and_derived_only_on_nulls(d):
    import storage
    from trades import canonical_org
    import ledger_export as L
    raw = storage.load_fa_team_payroll(d["class_year"])
    if not raw:
        pytest.skip("fa_team_payroll absent")
    spotrac = {canonical_org(t): r.get("payor_status_raw") for (t, _s), r in raw.items() if t != "AVERAGES"}
    census = d["accountability"]["payor_2027_basis_census"]
    n_spotrac = sum(1 for c in d["clubs"] if spotrac.get(c))
    assert census.get(L.PAYOR_BASIS_SPOTRAC, 0) == n_spotrac
    assert census.get(L.PAYOR_BASIS_DERIVED, 0) == 30 - n_spotrac
    assert 0 < n_spotrac < 30, "the 2027 page carries the status on most rows, not all"
    T = d["cba"]["threshold_by_season"][str(d["season_now"])]
    for c, club in d["clubs"].items():
        p = club["payroll"]["payor_2027"]
        if spotrac.get(c):
            assert p == {"value": spotrac[c], "basis": L.PAYOR_BASIS_SPOTRAC}, c
        else:
            assert p["basis"] == L.PAYOR_BASIS_DERIVED, c
            tax26 = club["payroll"]["s2026"]["tax_payroll_usd"]
            t26 = club["payroll"]["s2026"]["payor_status_raw"] or "Non-Tax"
            expect = L.PAYOR_NEXT[t26] if tax26 > T else "Non-Tax"
            assert p["value"] == expect, c


# --------------------------------------------------------------------------
# Mistake 4: the two arbitration residuals
# --------------------------------------------------------------------------

def test_the_two_arbitration_residuals_are_never_combined(d):
    for path, k, _v in _walk(d):
        ks = str(k).lower()
        assert not ("ou_mkt" in ks and "ou_war" in ks), path
        assert ks not in ("ou_total", "ou_combined", "ou_sum", "ou_mean"), path
    assert d["copy"]["never_combine"] and "never" in d["copy"]["never_combine"]
    for c, club in d["clubs"].items():
        R = club["arbitration"]["realized"]
        m, w = R["ou_mkt_total_usd"], R["ou_war_total_usd"]
        assert m == sum(s[4] for s in R["seasons"]) and w == sum(s[5] for s in R["seasons"])
        if m and w and m + w not in (m, w):
            vals = set(_leaves(club))
            assert (m + w) not in vals and (m + w) / 2 not in vals, c


def test_the_arbitration_sum_is_labelled_an_upper_bound(d):
    s = d["copy"]["arb_upper_bound"].lower()
    assert "upper bound" in s and "not a payroll forecast" in s
    col = [c for c in d["league"]["columns"] if c[0] == "arb_exposure_2027"][0]
    assert "upper bound" in col[3]
    js = JS.read_text(encoding="utf-8")
    assert 'copy("arb_upper_bound")' in js
    for club in d["clubs"].values():
        A = club["arbitration"]
        assert A["s2027_usd"] == sum(r[3] or 0 for r in A["rows"])


# --------------------------------------------------------------------------
# Realized value is not skill
# --------------------------------------------------------------------------

def test_realized_value_copy_says_not_skill_and_names_the_counterfactual(d):
    s = d["copy"]["realized_sentence"]
    assert "not how well the club chose" in s and "counterfactual" in s and "no club is ranked" in s
    a = d["copy"]["arb_realized_copy"]
    assert "not skill" in a and "counterfactual" in a
    assert d["copy"]["realized_not_skill"].startswith("Realized value, not skill")
    assert d["sections"]["fa_realized"]["note"] == "realized value, not skill"


def test_realized_fa_value_is_served_from_fa_archive_with_method_and_coverage(d):
    from trades import canonical_org
    arch = json.loads((ROOT / "data" / "fa_archive.json").read_text(encoding="utf-8"))
    assert d["copy"]["realized_method"] == "level_proration_backcast_dpw_v1"
    covered = {}
    for w in arch["winters"]:
        for s in w["signings"]:
            c = canonical_org(s.get("to"))
            if c in d["clubs"] and s.get("warTd") is not None:
                covered[(c, w["year"])] = covered.get((c, w["year"]), 0) + 1
    for c, club in d["clubs"].items():
        R = club["fa"]["realized"]
        assert R["status"] == "live"
        for row in R["by_winter"]:
            winter, n, n_cov, _war, paid, sur, realized, _done = row
            assert n_cov <= n and n_cov == covered.get((c, winter), 0), (c, winter)
            assert realized == paid + sur, (c, winter, "value delivered = paid + surplus to date")
        assert R["by_winter"][-1][2] == 0, "the current winter carries no realized value; no season has elapsed"
    assert "level_proration" in d["field_key"]["fa.realized.by_winter"] or "realized_usd" in d["field_key"]["fa.realized.by_winter"]


# --------------------------------------------------------------------------
# Surplus: sums of means, $M, no tier
# --------------------------------------------------------------------------

def test_surplus_totals_are_sums_of_means_and_no_quantile_is_summed(d):
    fc = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    from trades import canonical_org
    for c, club in d["clubs"].items():
        S = club["surplus"]
        assert S["total_mm"] == round(S["mlb_mm"] + (S["farm_mm"] or 0), 1), c
        assert S["mlb_mm"] == round(sum(S["mlb_by_salsrc_mm"].values()), 1), c
        members = [m for m in fc["members"] if canonical_org(m.get("from")) == c]
        e = club["commitments"]["expiring"]["2027"]
        assert e[0] == len(members)
        assert e[2] == int(sum(float(m.get("projGuar") or 0) for m in members)), (c, "sum of means")
        p10 = int(sum(float(m.get("projGuarP10") or 0) for m in members))
        if p10 and p10 != e[2]:
            assert p10 not in set(_leaves(club["commitments"])), (c, "a sum of P10s reached the payload")
    for path, k, _v in _walk(d):
        assert "p10_sum" not in str(k) and "p90_sum" not in str(k), path
    assert "quantiles are never summed" in d["copy"]["surplus_ev"]


def test_club_surplus_totals_are_in_millions_and_take_no_tier(d):
    for club in d["clubs"].values():
        assert club["surplus"]["unit"] == "$M"
    assert "$M" in d["copy"]["surplus_basis"] and "Both legs in $M" in d["copy"]["surplus_basis"]
    js = JS.read_text(encoding="utf-8")
    assert "moneyMM(S.total_mm)" in js and "zCell(S.total_mm)" not in js
    col = [c for c in d["league"]["columns"] if c[0] == "controlled_surplus_mm"][0]
    assert "$M" in col[3] and "plain" in col[3]
    assert "controlled_surplus_mm" not in d["league"]["coloured"]


def test_cost_plus_is_100_plus_10z_over_thirty_clubs_and_no_room_plus_exists(d):
    cp = [r["cost_plus"] for r in d["league"]["rows"]]
    assert len(cp) == 30 and all(isinstance(v, int) for v in cp)
    assert abs(statistics.mean(cp) - 100) <= 0.5
    assert abs(statistics.pstdev(cp) - 10) <= 0.5
    ratios = {c: club["indexes"]["cost_ratio_war_per_mm"] for c, club in d["clubs"].items()}
    mu = statistics.mean(ratios.values())
    sd = statistics.pstdev(ratios.values())
    for c, club in d["clubs"].items():
        z = (ratios[c] - mu) / sd
        assert abs(club["indexes"]["cost_plus"] - (100 + 10 * z)) <= 1.0, c
    for path, k, _v in _walk(d):
        assert "room_plus" not in str(k).lower() and "room+" not in str(k).lower(), path
    assert set(d["league"]["coloured"]) == {"cost_plus", "orgsur_plus"}


def test_the_indexes_are_labelled_descriptive_and_have_no_registry_claim(d):
    s = d["copy"]["cost_plus_basis"].lower()
    assert "descriptive" in s and "not a model" in s
    assert "no registry row" in d["copy"]["cost_plus_registry"]
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    ids = {m.get("model_id") for m in reg["models"]}
    assert "cost_plus" not in ids and "room_plus" not in ids and "club_payroll_path" not in ids
    col = [c for c in d["league"]["columns"] if c[0] == "cost_plus"][0]
    assert "descriptive" in col[3]


def test_orgsur_plus_carries_the_unvalidated_verdict_from_the_registry(d):
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = [m for m in reg["models"] if m.get("model_id") == "org_sur_plus"][0]
    assert row["verdict"] == "unvalidated"
    quoted = [r for r in d["accountability"]["registry_verdicts"] if r["model_id"] == "org_sur_plus"][0]
    assert quoted["verdict"] == "unvalidated" and quoted["eval_artifact"] is None
    assert "unvalidated" in d["copy"]["orgsur_chip"]
    col = [c for c in d["league"]["columns"] if c[0] == "orgsur_plus"][0]
    assert "unvalidated" in col[3]


# --------------------------------------------------------------------------
# Farm capital
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def org_summary():
    p = ROOT / "data" / "timeseries.json"
    if not p.exists():
        pytest.skip("timeseries.json absent")
    from trades import canonical_org
    ts = json.loads(p.read_text(encoding="utf-8"))
    return {canonical_org(o["org"]): o for o in ts["org_summary"]}


def test_farm_letters_are_copied_from_org_summary_not_recomputed(d, org_summary):
    import ledger_export as L
    for c, club in d["clubs"].items():
        o = org_summary[c]
        for k in L.FIN_LEAVES:
            leaf = club["farm"]["leaves"][k]
            if not leaf["sparse"]:
                assert leaf["letter"] == o["grades"][k], (c, k)
                assert leaf["score_100"] == o["tree"][k]["score_100"], (c, k)
        assert club["farm"]["orgsur_plus"]["financial_score"] == o["financial_score"]
        assert club["indexes"]["orgsur_plus"] == o["financial_score"]
    assert "never recomputed" in d["copy"]["farm_letters_note"]


def test_a_sparse_farm_leaf_renders_a_dash_not_a_letter():
    import ledger_export as L
    tree = {"fin_ifa_roi": {"war_per_m_ifa": 0.4, "grad_count": 0, "score_100": None, "sparse": True},
            "fin_war_per_m": {"value": 2.1, "grad_count": 12, "score_100": 108.0}}
    grades = {"fin_ifa_roi": "F", "fin_war_per_m": "B+"}
    sparse = L.farm_leaf(tree, grades, "fin_ifa_roi")
    assert sparse["letter"] == " - " and sparse["score_100"] is None and sparse["sparse"] is True
    live = L.farm_leaf(tree, grades, "fin_war_per_m")
    assert live["letter"] == "B+" and live["score_100"] == 108.0 and live["sparse"] is False
    missing = L.farm_leaf({}, {}, "fin_contract_surplus")
    assert missing["letter"] == " - " and missing["sparse"] is True


def test_slot_coverage_is_published_per_draft_year(d):
    import storage
    rows = storage.load_draft_results()
    if not rows:
        pytest.skip("draft_results absent")
    by_year = {}
    for r in rows:
        y = str(r["draft_year"])
        n, k = by_year.get(y, (0, 0))
        by_year[y] = (n + 1, k + (1 if r.get("slot_usd") else 0))
    for c, club in d["clubs"].items():
        for y, row in club["farm"]["draft_paid"].items():
            n, k = by_year[y]
            assert row[8] == round(100.0 * k / n, 1), (c, y)
    assert "slot_usd" in d["copy"]["slot_coverage_basis"]


def test_pick_capital_is_war_only_and_says_why_it_is_not_lottery_weighted(d):
    for club in d["clubs"].values():
        pw = club["farm"]["pick_war"]
        assert len(pw) == 3
    assert "not lottery-weighted" in d["copy"]["pick_war_label"]
    assert "not served" in d["copy"]["pick_dollars"]
    for path, k, _v in _walk(d):
        assert "pick_usd" not in str(k) and "pick_dollars_usd" not in str(k), path


# --------------------------------------------------------------------------
# Contracts, deferrals, dead money, retained
# --------------------------------------------------------------------------

def test_dead_money_never_widens_the_priced_contract_set(d):
    """The table_id tag trails v1 (owner default deferred it to a dark block). The
    v1 contract is therefore: the Spotrac team pages are NOT read by this export,
    the block is dark and names the tag, and no contract-set hash is claimed. When
    the tag lands this test flips to the sha comparison."""
    s = d["sections"]["dead_money"]
    assert s["live"] is False and "table_id" in s["blocked_on"] and "widen" in s["blocked_on"]
    acc = d["accountability"]
    assert acc["contract_set_sha"] is None and "not read" in acc["contract_set_note"]
    src = (ROOT / "ledger_export.py").read_text(encoding="utf-8")
    assert "scrape_spotrac_team_contracts" not in src and "import spotrac" not in src
    for club in d["clubs"].values():
        assert club["contracts"]["dead_money"]["status"] == "dark"
        assert club["contracts"]["dead_money"]["by_season"] == []
    assert "never summed" in d["copy"]["dead_money_beside"]


def test_retained_salary_is_never_merged_into_employing_club_aav(d):
    s = d["sections"]["retained"]
    assert s["live"] is False and "never merged" in s["blocked_on"]
    for club in d["clubs"].values():
        R = club["contracts"]["retained"]
        assert R["status"] == "dark" and R["by_season"] == []
        assert "retained_usd_2027" in R, "the Spotrac club total rides as a cross-check only"
    assert "club total" in d["copy"]["retained_cross_check"]


def test_the_deferral_block_states_its_coverage_rule(d):
    import fa_market
    rate = float(fa_market._discount_rate())
    cov = d["copy"]["deferral_coverage"]
    assert "200M" in cov and "not a complete" in cov
    assert f"{rate * 100:g} pct" in d["copy"]["deferral_rate_label"]
    assert f"{rate * 100:g} pct" in d["copy"]["deferral_rate_note"] and "statutory" in d["copy"]["deferral_rate_note"]
    assert d["accountability"]["discount_rate"] == rate
    js = JS.read_text(encoding="utf-8")
    assert not re.search(r"\b\d+(\.\d+)? ?(pct|percent|%)\s*(rate|discount)", js), "the JS types no rate"
    for club in d["clubs"].values():
        D = club["contracts"]["deferrals"]
        assert D["n"] == len(D["players"])
        assert D["sticker_usd"] == sum(p[1] for p in D["players"])
        assert D["npv_usd"] == sum(p[2] for p in D["players"])
        for p in D["players"]:
            assert p[2] <= p[1], "an NPV never exceeds its sticker"


def test_contract_rows_cover_every_priced_vet_and_name_their_basis(d, proj):
    n = sum(club["contracts"]["n_priced"] for club in d["clubs"].values())
    assert n == sum(1 for v in proj["vets"] if v.get("salPath"))
    assert set(d["copy"]["cell_basis"]) == {"contract", "arb_ladder", "class_closure"}
    assert "band, not a calibrated interval" == d["copy"]["band_note"]
    for club in d["clubs"].values():
        assert len(club["contracts"]["rows"]) == club["contracts"]["n_priced"]
        for row in club["contracts"]["rows"]:
            assert len(row) == 12 and row[10], "every priced row carries its salPath"
    assert isinstance(d["accountability"]["contract_disagreements"], int)


# --------------------------------------------------------------------------
# What the page says it cannot say, and every dark block
# --------------------------------------------------------------------------

def test_dark_sections_name_their_blocker(d):
    for k, s in d["sections"].items():
        if not s.get("live"):
            assert s.get("blocked_on"), k
    assert d["sections"]["payroll_history"]["blocked_on"].startswith("Payroll history is cached but not yet ingested")
    for club in d["clubs"].values():
        assert club["payroll"]["history"]["status"] == "dark" and club["payroll"]["history"]["seasons"] == []
        assert club["farm"]["pools"]["2021"][1] in ("not parsed", "live")


def test_pending_qos_render_no_live_stamps_when_every_event_is_invalidated(d):
    import storage
    events = [e for e in storage.load_fa_events() if e.get("event_type") == "qo_offered"]
    live = [e for e in events if not e.get("invalidated")]
    q = d["sections"]["qo_pending"]
    assert q["n_live"] == len(live)
    if not live:
        assert q["live"] is False and q["note"] == d["copy"]["qo_none"] == "no live QO stamps"


def test_the_not_claimed_list_names_revenue_attendance_tv_and_valuation(d):
    text = "\n".join(d["what_this_page_does_not_claim"]).lower()
    for kw in ("revenue", "attendance", "tv", "valuation", "ticket", "central-fund", "revenue-sharing",
               "minor-league payroll", "front-office", "stadium debt", "cbt bills", "bonus pools"):
        assert kw in text, kw
    assert len(d["what_this_page_does_not_claim"]) >= 12
    for path, k, _v in _walk(d):
        assert str(k).lower() not in ("revenue", "attendance", "valuation", "tv", "rsn"), path


def test_every_registry_verdict_quoted_matches_model_registry_json(d):
    import ledger_export as L
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    by = {m.get("model_id"): m for m in reg["models"]}
    quoted = {r["model_id"]: r for r in d["accountability"]["registry_verdicts"]}
    assert set(quoted) == set(L.REGISTRY_IDS)
    for mid, r in quoted.items():
        assert r["present"] is (mid in by), mid
        if mid in by:
            assert r["verdict"] == by[mid]["verdict"] and r["eval_artifact"] == by[mid].get("eval_artifact"), mid
    assert d["accountability"]["registry_checked_at"] == reg.get("checked_at")


# --------------------------------------------------------------------------
# The export itself: offline, watched, catalogued, shipped
# --------------------------------------------------------------------------

def test_the_export_never_opens_a_socket(monkeypatch):
    import socket
    import ledger_export as L

    def _no(*a, **k):
        raise AssertionError("ledger_export opened a socket")
    monkeypatch.setattr(socket, "socket", _no)
    monkeypatch.setattr(socket, "create_connection", _no)
    try:
        import requests
        monkeypatch.setattr(requests.sessions.Session, "request", _no)
    except ImportError:
        pass
    before = ART.stat().st_mtime if ART.exists() else None
    doc = L.build()
    assert len(doc["clubs"]) == 30
    assert (ART.stat().st_mtime if ART.exists() else None) == before, "build() never writes"


def test_the_export_is_a_watched_scheduled_export_and_a_numbered_step():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_export"' in src[i:i + 3200], "the window scan on mgmt_export must still hold"
    j = src.index(")\n", src.index('"ledger_export"', i))
    block = src[i:j]
    assert block.index('"mgmt_export"') < block.index('"mlbstats_windows"') < block.index('"ledger_export"')
    assert "d10e. Club Ledger board" in src
    assert '_record_ingest("ledger_export"' in src
    assert src.index("d10d. ESPN new-article probe") < src.index("d10e. Club Ledger board")


def test_the_board_is_in_the_data_catalog():
    src = (ROOT / "data_catalog.py").read_text(encoding="utf-8")
    assert '"ledger_board.json"' in src and '"pinned_by": "test_ledger_export.py"' in src
    i = src.index('"ledger_board.json"')
    assert "NO single projected payroll" in src[i:i + 1200]


def test_ledger_is_in_the_deploy_publish_list():
    lines = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()
    assert "ledger" in lines, "omit this and every test stays green while /ledger/ 404s in production"


def test_ledger_is_in_the_sitemap():
    assert "/ledger/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '("/ledger/", "daily"' in src


def test_ledger_is_excluded_from_pytest_collection():
    assert "\n    ledger\n" in (ROOT / "pytest.ini").read_text(encoding="utf-8")


def test_ledger_is_in_nav_items_and_the_static_copies():
    from build_site import MODULE_STAGE, nav_leaves
    keys = [k for k, _l, _h in nav_leaves()]
    assert "ledger" in keys
    assert keys.index("arbitration") + 1 == keys.index("ledger") < keys.index("management")
    assert [(l, h) for k, l, h in nav_leaves() if k == "ledger"] == [("Club Ledger", "/ledger/")]
    assert MODULE_STAGE["ledger"][0] == MODULE_STAGE["arbitration"][0], "slot 0 is the sigil, not the word"
    assert MODULE_STAGE["ledger"][1] == "Beta. Descriptive ledger: no payroll forecast, no revenue"
    for rel in ("prospx/index.html", "collegesavant/index.html", "collegesavant/pitcher_index.html"):
        nav = (ROOT / rel).read_text(encoding="utf-8")
        i = nav.index('<a href="/arbitration/" role="menuitem">Arbitration</a>')
        assert nav[i:].startswith('<a href="/arbitration/" role="menuitem">Arbitration</a><a href="/ledger/" role="menuitem">Club Ledger</a>'), rel


def test_the_payload_stays_under_the_one_megabyte_line(d):
    assert ART.stat().st_size < 1_000_000, "D12: one payload up to 1 MB, lazy per-club files past it"
    assert "field_key" in d and "copy" in d


def test_every_club_carries_a_statsapi_code_and_mlbstats_links_use_it(d):
    import trades
    for c, club in d["clubs"].items():
        code = club["statsapi_code"]
        assert code and code == trades.statsapi_code(c), c
        if c in SITE_CODES:
            assert code == SITE_CODES[c], (c, code)
        assert club["links"]["mlbstats_war"].endswith("&team=" + code)
        assert club["links"]["mlbstats_bullpen"].endswith("&team=" + code)
        assert "wview=teams" in club["links"]["mlbstats_war"]
        assert club["links"]["roster_board"] == f"/projections/#team={c}"
        assert club["links"]["fa_fits"] == f"/fa/#view=fits&team={c}"
        assert club["links"]["management_club"] == f"/management/#section=clubs&team={c}"
    rows = {r["club"]: r["statsapi_code"] for r in d["league"]["rows"]}
    assert rows == {c: club["statsapi_code"] for c, club in d["clubs"].items()}


def test_every_glossary_hook_on_the_page_and_in_the_js_resolves(d):
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in g["entries"]}
    for slug in ("cbt_payroll", "payroll_allocations", "cbt_bracket", "computed_cbt_bill", "payor_tier",
                 "dead_money", "retained_salary", "contract_dollars_on_file", "arb_exposure",
                 "payroll_horizon", "cost_plus", "controlled_surplus", "implied_ifa_pool", "pick_war",
                 "realized_contract_value"):
        assert slug in ids, slug
    hooks = set(re.findall(r'data-gl="([a-z_]+)"', PAGE.read_text(encoding="utf-8"))) if PAGE.exists() else set()
    js = JS.read_text(encoding="utf-8")
    hooks |= set(re.findall(r'gl\([^,]+,\s*"([a-z_]+)"\)', js))
    hooks |= {c[2] for c in d["league"]["columns"] if c[2]}
    missing = sorted(h for h in hooks if h not in ids)
    assert not missing, missing


# --------------------------------------------------------------------------
# Review fixes (2026-09-23): the served payload behind the six defects
# --------------------------------------------------------------------------

def test_the_2026_cbt_block_names_the_2026_page_and_the_2027_block_its_own_basis(d):
    import ledger_export as L
    labels = d["copy"]["payor_basis"]
    assert L.PAYOR_BASIS_SPOTRAC_2026 != L.PAYOR_BASIS_SPOTRAC
    assert labels[L.PAYOR_BASIS_SPOTRAC_2026] == f"Spotrac {d['season_now']} page"
    assert labels[L.PAYOR_BASIS_SPOTRAC] == f"Spotrac {d['class_year']} page"
    for c, club in d["clubs"].items():
        now = club["cbt"][str(d["season_now"])]
        assert now["tier_basis"] == L.PAYOR_BASIS_SPOTRAC_2026, c
        assert now["tier"] == club["payroll"]["s2026"]["payor_status_raw"], c
        nxt = club["cbt"][str(d["class_year"])]
        assert nxt["tier_basis"] == club["payroll"]["payor_2027"]["basis"], c
        assert nxt["tier_basis"] in labels, c


def test_the_league_means_carry_their_pool_size_and_the_tax_pool_is_the_payors(d):
    mv = d["league"]["means"]["values"]
    rows = d["league"]["rows"]
    for k in list(mv):
        if k.endswith("_n"):
            continue
        assert k + "_n" in mv, k
        assert mv[k + "_n"] == sum(1 for r in rows if r.get(k) is not None), k
    payors = [r["est_tax_2026"] for r in rows if r["est_tax_2026"] is not None]
    assert 0 < len(payors) < len(rows)
    assert mv["est_tax_2026_n"] == len(payors)
    assert mv["est_tax_2026"] == round(statistics.mean(payors), 1)
    assert mv["cbt_payroll_2026_n"] == len(rows)


def test_each_league_header_and_farm_leaf_links_the_entry_that_defines_it(d):
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in g["entries"]}
    slug = {c[0]: c[2] for c in d["league"]["columns"]}
    assert slug["committed_2027"] == "payroll_allocations", "Spotrac total payroll allocations, not the on-file segment"
    assert slug["proj_wins_2027"] is None and slug["farm_rank"] is None, "no entry defines these; the header prints plain"
    assert "farm_grade_financial" in ids
    for c, club in d["clubs"].items():
        for k in club["farm"]["leaves"]:
            assert k in ids or k == "fin_active_surplus", (c, k)
    js = JS.read_text(encoding="utf-8")
    assert 'k === "fin_active_surplus" ? "farm_grade_financial" : k' in js
    assert '"contract_dollars_on_file"), money(p27' not in js
