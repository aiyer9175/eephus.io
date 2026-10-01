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
    # a non-club org (Cuba through 2026-09-24's inputs) is dropped, never made a 31st club
    assert oj["trade_values"][0] - oj["trade_values"][1] == len(oj["trade_values_dropped"])
    assert not set(oj["trade_values_dropped"]) & clubs
    assert d["accountability"]["n_clubs"] == 30


def test_the_averages_row_is_a_reference_and_not_a_club(d):
    av = d["league"]["averages_row"]
    assert av["label"] and "AVERAGES" not in d["clubs"]
    assert all(r["club"] != "AVERAGES" for r in d["league"]["rows"])
    pool = d["league"]["pools"]["cost_plus"]
    assert pool["averages_excluded"] is True and pool["n"] == 30
    assert d["accountability"]["averages_excluded"] is True


def test_the_league_footer_note_is_pinned_to_the_measured_vintage_gap(d):
    """Spotrac's average row and the mean of the 30 club rows disagreed on Committed
    2027 by $17.0M (review of 53726dd8). Measured cause: VINTAGE, not basis. The
    AVERAGES row's fetched_at is 2026-07-07 (the payroll-page parser has emitted no
    Averages row since; the 2026-09-23 page parses to 30 clubs) while the club rows
    are refetched nightly; the cached 2026-09-23 page's own Averages row reads
    144,788,882, the computed mean to the dollar. The sentence beneath the footer
    names the gap and both stamps, and this test recomputes each from the payload
    and, where the page cache is on disk, checks the basis identity too."""
    import ledger_export as LE
    L = d["league"]
    av, mv = L["averages_row"], L["means"]
    note = d["copy"]["footer_means_note"]
    assert note and chr(0x2014) not in note and chr(0x2013) not in note
    gap = mv["values"]["committed_2027"] - av["committed_2027"]
    assert f"${abs(gap) / 1e6:.1f}M" in note
    assert av["fetched_at"] and mv["fetched_at"] and mv["fetched_at_min"] <= mv["fetched_at"]
    assert note == LE.footer_means_note(av["fetched_at"], mv["fetched_at"], gap, d["class_year"])
    if abs(gap) >= 1_000_000:
        assert av["fetched_at"] < mv["fetched_at"], "a gap with no vintage difference has no measured cause"
        assert av["fetched_at"] in note and mv["fetched_at"] in note
        assert "the basis is the same" in note and str(d["class_year"]) in note
    else:
        assert "Both rows are from" in note
    page = ROOT / ".cache" / f"spotrac_payroll_{d['class_year']}.html"
    if not page.exists():
        return
    from datetime import datetime
    if datetime.fromtimestamp(page.stat().st_mtime).strftime("%Y-%m-%d") != mv["fetched_at"]:
        return
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page.read_text(encoding="utf-8", errors="replace"), "html.parser")
    avg_rows = [tr for tr in soup.find("table").find_all("tr") if tr.get_text(" ", strip=True).startswith("Averages")]
    if not avg_rows:
        return
    dollars = [int(c.replace("$", "").replace(",", "")) for c in
               (td.get_text(strip=True) for td in avg_rows[0].find_all("td")) if c.startswith("$")]
    assert abs(dollars[0] - mv["values"]["committed_2027"]) < 1, "the page's own average IS the computed mean: basis, not vintage"


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
        # the 2027 basis (owner answer M13-1): Spotrac's tax payroll, or the
        # club's guaranteed contract AAV where that is larger
        tax = club["payroll"]["cbt_basis_2027"]["usd"]
        assert sp["source"] == club["payroll"]["cbt_basis_2027"]["source"], c
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


def test_the_arbitration_sum_assumes_every_player_tendered(d):
    """Owner answer M10-4 (2026-09-25): the ladder sum is not called an upper bound
    (an extension or a raise can exceed it); it assumes every player is tendered and
    a non-tender lowers it."""
    s = d["copy"]["arb_tender_note"].lower()
    assert "assumes every player is tendered" in s and "a non-tender lowers the figure" in s
    assert "not a payroll forecast" in s and "upper bound" not in s
    assert "arb_upper_bound" not in d["copy"]
    col = [c for c in d["league"]["columns"] if c[0] == "arb_exposure_2027"][0]
    assert "assumes every player is tendered" in col[3] and "upper bound" not in col[3]
    assert "upper bound" not in d["field_key"]["arbitration.by_season"]
    assert "upper bound" not in json.dumps(d, ensure_ascii=False).lower()
    js = JS.read_text(encoding="utf-8")
    assert 'copy("arb_tender_note")' in js and "arb_upper_bound" not in js
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
        # The leaves carry a 12 px pixel icon before the label (PX-04/PX-10);
        # the slot order is what this pins, so the icon markup is set aside.
        nav = re.sub(r'<svg class="ico"[^>]*>.*?</svg>', "", (ROOT / rel).read_text(encoding="utf-8"))
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


# ==========================================================================
# D5 depth pass (2026-09-24): one board plus thirty per-club row files
# ==========================================================================
# Every new row layer RECONCILES to the v1 roll-up it sits under, and each
# identity here is measured on the served files, never assumed: farm rows to
# the fin_active_surplus leaf (to a vintage tolerance, both stamps printed),
# arbitration rungs by season to the v1 ladder sums (exact), contract strips to
# the served NPV and surTotal (to the stated rounding). Quantiles are never
# summed anywhere; ou_mkt and ou_war never share a key; the Swartz figure is a
# third quantity; no P10 or P90 sits beside an arbitration figure.

SHARD_DIR = ROOT / "data" / "ledger_clubs"
NEW_COPY_STATIC = ("farm_dollar_is_not", "farm_reconcile", "farm_vintage_gap", "farm_gap_broken", "farm_no_bonus",
                   "trade_cost_dark", "grad_two_engines", "grad_contract_dark", "grad_no_registry", "shard_failed",
                   "shard_vintage", "dvm_within_tier", "p_bust_basis", "preview_note", "trajectory_active_basis",
                   "arb_prearb_rungs", "arb_two_populations", "arb_quantiles_dark", "arb_comps_dark", "arb_filing_dark",
                   "npv_identity", "sur_total_identity", "tv_reanchored", "opt_out_two_engines", "trade_currency_split", "sources_stamps",
                   "not_summed", "shown_rows", "band_row_only", "grad_preview_note", "arb_preview_note",
                   "trade_preview_note", "paths_preview_note", "trajectory_loading")
NEW_COPY_TEMPLATES = ("farm_dollar_is_template", "swartz_label_template")


@pytest.fixture(scope="module")
def shards(d):
    if not SHARD_DIR.exists():
        pytest.skip("run python ledger_export.py (writes data/ledger_clubs/)")
    out = {}
    for c in d["clubs"]:
        p = SHARD_DIR / f"{c}.json"
        if not p.exists():
            pytest.skip(f"shard {p.name} absent; run python ledger_export.py")
        out[c] = json.loads(p.read_text(encoding="utf-8"))
    return out


@pytest.fixture(scope="module")
def tv():
    p = ROOT / "data" / "trade_values.json"
    if not p.exists():
        pytest.skip("trade_values.json absent")
    doc = json.loads(p.read_text(encoding="utf-8"))
    # by_proj_key: the row of each projections vet's HUMAN. A row carries
    # proj_key only where its own slug names a different human in projections.
    by_proj = {}
    for r in doc["players"]:
        k = r["proj_key"] if "proj_key" in r else r.get("player_key")
        if k:
            by_proj[k] = r
    return {"doc": doc, "by_key": {r["player_key"]: r for r in doc["players"] if r.get("player_key")},
            "by_proj_key": by_proj}


def _col(d, key, name):
    return d["columns"][key].index(name)


def _rows(shard, key):
    if key == "arbitration.realized.rows":
        return shard["arbitration"]["realized_rows"]
    blk, _, name = key.rpartition(".")
    return shard[blk][name]


# --------------------------------------------------------------------------
# D5-0: the spine
# --------------------------------------------------------------------------

def test_the_main_payload_carries_no_row_array_and_stays_under_one_megabyte(d, shards):
    """The preview guard (ledger_export: PREVIEW_N rows, PREVIEW_N_SMALL once the
    full-preview board passes PREVIEW_GUARD_BYTES).

    Re-expressed 2026-09-30, while landing VAL_1 (owner answer FP2-1): the
    guard fired for the first time, on a full-preview board of about 955 KB,
    and the page dropped to five preview rows. Owner answer VAL1-Q1 the same
    day: trim the payload and restore ten rows, the guard staying at 950,000.
    The three per-club snapshot series moved into the shards (about 86 KB of
    the board), so the built board must now carry the FULL preview AND sit
    under the guard; PREVIEW_N_SMALL stays in the exporter as the fallback and
    this test fails if it is ever taken again."""
    import ledger_export as L
    size = ART.stat().st_size
    assert size < L.BOARD_CAP_BYTES
    n = d["shards"]["preview_n"]
    assert d["shards"]["board_guard_bytes"] == L.PREVIEW_GUARD_BYTES == 950_000
    assert n == L.PREVIEW_N == 10, (n, "the guard dropped the preview; trim the board again or ask the owner")
    assert size <= L.PREVIEW_GUARD_BYTES, (size, "a full-preview board past the guard")
    for c, club in d["clubs"].items():
        assert "prospects" not in club["farm"] and "graduates" not in club["farm"] and "picks" not in club["farm"], c
        assert "ladders" not in club["arbitration"] and "realized_rows" not in club["arbitration"], c
        assert "paths" not in club["contracts"] and "rows_debuted" not in club["surplus"], c
        assert len(club["farm"]["preview"]) == min(n, club["farm"]["n_prospects"]), c


def _history_rollups():
    """The v1 roll-ups straight from storage.trade_value_history, the same
    queries the exporter runs; skipped where the database is not on disk."""
    import ledger_export as L
    tr, ta = L._trade_trajectory(), L._trade_trajectory_active()
    if not tr:
        pytest.skip("storage.trade_value_history unavailable")
    return tr, ta


def test_the_trajectories_live_in_the_shards_with_the_v1_rollup_values_and_the_board_keeps_a_receipt(d, shards):
    """Owner answer VAL1-Q1 (2026-09-30). No trajectory array rides on the main
    board; each club's shard carries its trade currency series, its actives
    series and the per-prospect series of the preview keys, each equal to the
    v1 roll-up of storage.trade_value_history on every snapshot the shard
    carries (a later nightly snapshot may extend the history, never rewrite
    an earlier point the shard printed). The board keeps one receipt saying
    where the series live, and the field key still names all three."""
    import ledger_export as L
    tr, ta = _history_rollups()
    receipt = d["shards"]["trajectories"]
    assert receipt == L.TRAJECTORY_RECEIPT and "ledger_clubs/CODE.json" in receipt
    for key in L.TRAJECTORY_KEYS:
        assert key in receipt and key in d["field_key"], key
    n = d["shards"]["preview_n"]
    keys = [r[0] for c in d["clubs"] for r in _rows(shards[c], "farm.prospects")[:n]]
    per_player = L._player_trajectories(keys)
    for c, club in d["clubs"].items():
        for path, k, _v in _walk(club):
            assert "traject" not in str(k), (c, path, "a trajectory key on the board")
        s = shards[c]
        for mine, v1 in ((s["surplus"]["trajectory"], tr.get(c) or []), (s["farm"]["trajectory_active"], ta.get(c) or [])):
            assert mine, (c, "an empty series")
            last = mine[-1][0]
            assert mine == [p for p in v1 if p[0] <= last], (c, "the shard series is the v1 roll-up")
        pt = s["farm"]["prospect_trajectory"]
        assert set(pt) == {r[0] for r in _rows(s, "farm.prospects")[:n]}, c
        for k, series in pt.items():
            if series:
                assert series == [p for p in per_player.get(k, []) if p[0] <= series[-1][0]], (c, k)
        assert s["columns"]["farm.trajectory_active"] == L.COLUMNS["farm.trajectory_active"]
        assert "surplus.trajectory" in s["field_key"] and "farm.trajectory_active" in s["field_key"]


def test_every_shard_is_under_160_kb_names_its_club_and_the_index_matches_disk(d, shards):
    import hashlib
    import ledger_export as L
    idx = d["shards"]
    assert idx["dir"] == L.SHARD_DIRNAME and idx["n"] == 30 and set(idx["files"]) == set(d["clubs"])
    on_disk = {p.stem for p in SHARD_DIR.glob("*.json") if re.fullmatch(r"[A-Z]{2,3}", p.stem)}
    assert on_disk == set(d["clubs"]), "no extra CODE.json and none missing"
    for c, club in d["clubs"].items():
        p = SHARD_DIR / f"{c}.json"
        b = p.read_bytes()
        st = idx["files"][c]
        assert st["path"] == f"{L.SHARD_DIRNAME}/{c}.json" and club["shard"]["path"] == st["path"], c
        assert st["bytes"] == len(b) == club["shard"]["bytes"], c
        assert st["sha256_16"] == hashlib.sha256(b).hexdigest()[:16] == club["shard"]["sha256_16"], c
        assert len(b) <= L.SHARD_CAP_BYTES, (c, len(b))
        s = shards[c]
        assert s["club"] == c and s["statsapi_code"] == club["statsapi_code"]
        assert s["board_generated_at"] == d["generated_at"] == club["shard"]["generated_at"]
        assert s["cba_banner"] is True and s["calibration"] == d["calibration"]
        for key, cols in s["columns"].items():
            assert cols == d["columns"][key], (c, key)
            if key in L.SHARD_ROW_KEYS:
                for row in _rows(s, key):
                    assert len(row) == len(cols), (c, key)
        for year_rows in s["farm"]["picks"].values():
            for row in year_rows:
                assert len(row) == len(s["columns"]["farm.picks"]), c


def test_the_shard_writer_never_opens_a_socket_and_build_all_never_writes(monkeypatch, tmp_path):
    import socket
    import ledger_export as L

    def _no(*a, **k):
        raise AssertionError("ledger_export opened a socket")
    monkeypatch.setattr(socket, "socket", _no)
    monkeypatch.setattr(socket, "create_connection", _no)
    before = {p: p.stat().st_mtime for p in [ART] + sorted(SHARD_DIR.glob("*.json")) if p.exists()}
    doc, shard_docs = L.build_all()
    assert len(doc["clubs"]) == 30 == len(shard_docs)
    assert L.build()["clubs"].keys() == doc["clubs"].keys(), "build() keeps its v1 signature: the board alone"
    assert {p: p.stat().st_mtime for p in before} == before, "build_all() and build() never write"
    monkeypatch.setattr(L, "SHARD_DIR", tmp_path / "ledger_clubs")
    (tmp_path / "ledger_clubs").mkdir()
    (tmp_path / "ledger_clubs" / "ZZZ.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ledger_clubs" / "keep.txt").write_text("x", encoding="utf-8")
    written = L.write_shards(doc, shard_docs)
    assert len(written) == 30 and all(p.parent == tmp_path / "ledger_clubs" for p in written)
    assert not (tmp_path / "ledger_clubs" / "ZZZ.json").exists(), "a stale club file is removed"
    assert (tmp_path / "ledger_clubs" / "keep.txt").exists(), "the directory is otherwise left alone"
    for c, p in zip(sorted(shard_docs), sorted(written)):
        assert p.stat().st_size == doc["shards"]["files"][c]["bytes"], c
    assert {p: p.stat().st_mtime for p in before} == before


def test_no_new_key_serves_a_summed_quantile_or_a_combined_residual(d, shards):
    import ledger_export as L
    L.assert_aggregate_keys(d)
    for s in shards.values():
        L.assert_aggregate_keys(s)
    for bad in ({"reconciliation": {"rows_p10_mm": 1}}, {"summary": {"band_lo_mm": 1}},
                {"by_season": [{"lo_usd": 1}]}, {"paths_summary": {"war_p90_sum": 1}},
                {"method": {"draft": {"hi": 1}}}, {"footer": {"p90": 1}},
                {"reconciliation": {"rows_extra_mm": 1}}, {"summary": {"trade_rows_all_mm": 1}}):
        with pytest.raises(AssertionError):
            L.assert_aggregate_keys(bad)
    L.assert_aggregate_keys({"reconciliation": {k: 1 for k in L.SUM_KEYS_ALLOWED}})
    L.assert_aggregate_keys({"rows": [{"band_lo_mm": 1, "band_hi_mm": 2}]})   # a band on a row outside the aggregates is the rule
    L.assert_aggregate_keys({"method": {"inputs_generated_at": {"arb_history": "x"}}})   # a token match, never a substring one
    for path, k, _v in _walk(d):
        ks = str(k).lower()
        assert not ("ou_mkt" in ks and "ou_war" in ks), path
    for c, s in shards.items():
        for path, k, _v in _walk(s):
            ks = str(k).lower()
            assert not ("ou_mkt" in ks and "ou_war" in ks) and "swartz_ou" not in ks, (c, path)


def test_the_new_registry_verdicts_are_quoted_from_the_registry(d):
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    by = {m.get("model_id"): m for m in reg["models"]}
    quoted = {r["model_id"]: r for r in d["accountability"]["registry_verdicts"]}
    for mid in ("control_window_salary_path", "mlb_projections_prospects", "xfv_provisional_prior"):
        assert mid in quoted and quoted[mid]["present"] is True, mid
        assert quoted[mid]["verdict"] == by[mid]["verdict"] == "provisional", mid
    assert "debuted_player_value" not in by, "no registry row; the graduates copy says so"
    assert "no registry row" in d["copy"]["grad_no_registry"] and "prospect_surplus" in d["copy"]["grad_no_registry"]
    assert d["sections"]["debuted_value_registry"]["live"] is True


def test_the_new_copy_sentences_exist_and_carry_no_typed_figure(d, tv):
    cp = d["copy"]
    for k in NEW_COPY_STATIC + NEW_COPY_TEMPLATES + ("farm_dollar_is", "swartz_label", "swartz_a6", "sur_strip_basis"):
        assert cp.get(k), k
        assert chr(0x2014) not in cp[k] and chr(0x2013) not in cp[k], k
    for k in NEW_COPY_STATIC + NEW_COPY_TEMPLATES:
        assert not re.search(r"(?<![_a-z])\d{4,}", cp[k]), (k, "a typed figure in a copy template")
        assert "isotonic" not in cp[k], (k, "a typed calibration stamp")
    cal = tv["doc"]["calibration"]["version"]
    assert cal in cp["farm_dollar_is"] and cp["farm_dollar_is"] == cp["farm_dollar_is_template"].format(calibration_version=cal)
    hist = json.loads((ROOT / "data" / "arb_history.json").read_text(encoding="utf-8"))
    n_swartz = sum(1 for r in hist["rows"] if r[7] is not None)
    a6 = json.loads((ROOT / "data" / "arbitration_eval.json").read_text(encoding="utf-8"))["a6_swartz"]
    assert cp["swartz_label"] == cp["swartz_label_template"].format(n_swartz=n_swartz, n_a6=a6["n"])
    assert str(d["class_year"]) in cp["sur_strip_basis"], "the class year is formatted at build time"


def test_the_new_sources_rows_and_stamps_are_published(d, shards):
    ids = {s[0]: s for s in d["method"]["sources"]}
    for sid, frag in (("S23", "timeseries.json players"), ("S24", "debuts_lite.json"),
                      ("S25", "arbitration_eval.json"), ("S26", "xfv.json meta header")):
        assert sid in ids and frag in ids[sid][1], sid
    stamps = d["method"]["inputs_generated_at"]
    for k in ("debuts_lite", "arbitration_eval", "xfv", "timeseries", "trade_values", "mlb_projections"):
        assert stamps.get(k), k
    oj = d["accountability"]["org_join"]
    assert oj["debuts_lite"][1] == 30 and oj["debuts_lite"][0] > 30
    assert oj["debuts_lite"][0] - oj["debuts_lite"][1] == len(oj["debuts_lite_dropped"])
    assert "Office of the Commissioner" in oj["debuts_lite_dropped"]
    assert not set(oj["debuts_lite_dropped"]) & set(d["clubs"])
    assert d["method"]["sources_stamps"] == d["copy"]["sources_stamps"]
    for c, club in d["clubs"].items():
        fr = club["farm"]["reconciliation"]
        assert fr["leaf_generated_at"] == stamps["timeseries"] and fr["rows_generated_at"] == stamps["trade_values"], c
        assert shards[c]["generated_at"] == d["generated_at"], c


def test_the_shards_are_catalogued_shipped_and_written_by_the_step():
    src = (ROOT / "data_catalog.py").read_text(encoding="utf-8")
    assert '"ledger_clubs/*.json"' in src
    i = src.index('"ledger_clubs/*.json"')
    assert '"pinned_by": "test_ledger_export.py"' in src[i:i + 1600] and "never summed" in src[i:i + 1600]
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = rm.index("d10e. Club Ledger board")
    step = rm[i:i + 2500]
    assert "_lgd, _lgs = _lg.build_all()" in step and "_lg.write_shards(_lgd, _lgs)" in step
    assert step.index("_lg.OUT.write_text(") < step.index("_lg.write_shards("), "the board is written first, then the shards"
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/ledger_clubs/***'" in nightly
    wf = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf.exists():
        assert "cp -r data/ledger_clubs _site/data/ledger_clubs" in wf.read_text(encoding="utf-8")
    assert "ledger_clubs" in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert '"ledger_board.json": ("calibration",)' in (ROOT / "test_calibration_vintage.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# D5-1: farm finance per prospect
# --------------------------------------------------------------------------

def test_the_farm_rows_sum_to_the_served_leaf_within_the_vintage_tolerance_and_print_the_gap(d, shards, org_summary):
    import ledger_export as L
    P = "farm.prospects"
    for c, club in d["clubs"].items():
        fr = club["farm"]["reconciliation"]
        leaf = org_summary[c]["tree"]["fin_active_surplus"]
        assert fr["leaf_mm"] == leaf["surplus_total_mm"] and fr["leaf_n"] == leaf["active_count"], c
        assert fr["status"] in ("exact", "vintage_drift"), (c, fr["status"], fr["gap_mm"], fr["tolerance_mm"])
        assert abs(fr["gap_mm"] - (fr["leaf_mm"] - fr["rows_net_mm"])) <= 0.05, c
        assert fr["tolerance_mm"] == round(max(L.FARM_TOL_PCT * abs(fr["leaf_mm"]), L.FARM_TOL_FLOOR_MM), 2), c
        assert abs(fr["gap_mm"]) <= fr["tolerance_mm"], c
        rows = _rows(shards[c], P)
        assert len(rows) == fr["n_rows"] == club["farm"]["n_prospects"], c
        net = sum(r[_col(d, P, "net_mm")] or 0 for r in rows)
        gross = sum(r[_col(d, P, "surplus_mm")] or 0 for r in rows)
        bonus = sum((r[_col(d, P, "bonus_usd")] or 0) for r in rows) / 1e6
        assert abs(net - fr["rows_net_mm"]) <= 0.05 and abs(gross - fr["rows_gross_mm"]) <= 0.05, c
        assert abs(gross - bonus - net) <= 0.05, c
        assert fr["leaf_source"].startswith("timeseries.org_summary") and "trade_values.json" in fr["rows_source"]
        assert fr["leaf_generated_at"] and fr["rows_generated_at"], "both stamps always print"
    assert L.farm_reconcile_status(455.4, 456.38) == (-0.98, 9.11, "vintage_drift")
    assert L.farm_reconcile_status(100.0, 100.04)[2] == "exact"
    assert L.farm_reconcile_status(100.0, 106.0)[2] == "broken"
    assert L.farm_reconcile_status(100.0, 104.9)[2] == "vintage_drift", "the floor is 5 $M"
    assert L.farm_reconcile_status(None, 1.0)[2] == "broken"
    for k in ("farm_reconcile", "farm_vintage_gap", "farm_gap_broken"):
        assert d["copy"][k]
    assert "neither is corrected" in d["copy"]["farm_gap_broken"]


def test_the_farm_cost_basis_reconciles_exactly_and_names_the_rows_without_a_bonus(d, shards, org_summary):
    P = "farm.prospects"
    for c, club in d["clubs"].items():
        fr = club["farm"]["reconciliation"]
        leaf = org_summary[c]["tree"]["fin_active_surplus"]
        assert fr["leaf_cost_mm"] == leaf["cost_basis_mm"], c
        assert abs(fr["rows_cost_mm"] - leaf["cost_basis_mm"]) <= 0.05 + 1e-9, (c, fr["rows_cost_mm"], leaf["cost_basis_mm"])
        rows = _rows(shards[c], P)
        with_bonus = sum(1 for r in rows if r[_col(d, P, "bonus_usd")])
        assert fr["n_with_bonus"] == with_bonus <= fr["n_rows"], c
        assert abs(sum((r[_col(d, P, "bonus_usd")] or 0) for r in rows) / 1e6 - fr["rows_cost_mm"]) <= 0.05, c
    assert "counts a cost of zero" in d["copy"]["farm_no_bonus"]
    assert d["sections"]["farm_bonus_missing"]["blocked_on"] == d["copy"]["farm_no_bonus"]
    assert sum(club["farm"]["reconciliation"]["n_rows"] - club["farm"]["reconciliation"]["n_with_bonus"]
               for club in d["clubs"].values()) > 0, "the uncaptured bonuses are real and counted"


def test_the_farm_method_buckets_reconcile_to_method_efficiency_and_trade_is_dark(d, shards, org_summary):
    import ledger_export as L
    M = "farm.method"
    n, nb, gross, cost, net, ratio, s_net, s_cost, s_n, s_pfv = [_col(d, M, k) for k in d["columns"][M]]
    for c, club in d["clubs"].items():
        me = org_summary[c]["tree"]["fin_active_surplus"]["method_efficiency"]
        fm = club["farm"]["method"]
        assert set(fm) == set(L.METHOD_BUCKETS)
        for m in L.METHOD_BUCKETS:
            row = fm[m]
            assert row[n] == (me[m]["count"] or 0) == row[s_n], (c, m, "counts equal exactly")
            assert row[s_net] == me[m]["surplus_total_mm"] and row[s_cost] == me[m]["cost_basis_mm"] and row[s_pfv] == me[m]["surplus_per_fv_pt_mm"], (c, m)
            if row[n]:
                assert abs(row[cost] - me[m]["cost_basis_mm"]) <= 0.05 + 1e-9, (c, m, "cost equal exactly")
                tol = max(L.FARM_TOL_PCT * abs(me[m]["surplus_total_mm"] or 0), L.FARM_TOL_FLOOR_MM)
                assert abs(row[net] - me[m]["surplus_total_mm"]) <= tol, (c, m)
                assert row[nb] <= row[n]
                if row[cost] > 0:
                    assert abs(row[ratio] - row[net] / row[cost]) <= 0.011, (c, m, "a ratio of two served numbers")
                else:
                    assert row[ratio] is None, (c, m)
        assert fm["trade"] == [0, 0, None, None, None, None, None, None, 0, None], (c, "trade has no cost basis today")
        rows = _rows(shards[c], "farm.prospects")
        i = _col(d, "farm.prospects", "acq_method")
        assert club["farm"]["reconciliation"]["n_unbucketed"] == sum(1 for r in rows if r[i] not in L.METHOD_BUCKETS), c
    s = d["sections"]["farm_trade_cost_basis"]
    assert s["live"] is False and s["blocked_on"] == d["copy"]["trade_cost_dark"]
    assert "no cost basis exists for the trade channel" in d["copy"]["trade_cost_dark"]
    assert "no ladder" in d["field_key"]["farm.method"]


def test_the_prospect_row_prints_one_surplus_basis_and_its_band_is_never_summed(d, shards):
    P = "farm.prospects"
    fk = d["field_key"][P]
    assert "never summed" in fk and "the only column the leaf sums" in fk and "consensus-basis" in fk
    assert d["columns"][P][:3] == ["key", "name", "pos"] and len(d["columns"][P]) == 28
    s_i, lo_i, hi_i, cs_i = [_col(d, P, k) for k in ("surplus_mm", "band_lo_mm", "band_hi_mm", "cons_surplus_mm")]
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], P)
        assert [r[s_i] for r in rows] == sorted((r[s_i] for r in rows), reverse=True), (c, "rows by surplus desc")
        lo_sum = sum(r[lo_i] or 0 for r in rows)
        hi_sum = sum(r[hi_i] or 0 for r in rows)
        leaves = set(_leaves(club["farm"]["reconciliation"])) | set(_leaves(club["farm"]["method"])) | set(_leaves(club["surplus"]["reconciliation"]))
        # Dollar leaves only (JSON floats). A summed band would land as a rounded
        # $M float; an integer leaf is a count. Added 2026-09-30 (VAL_1, owner
        # answer FP2-1): ATL's band-low sum read exactly 63.0 on the new level and
        # collided with its draft-method prospect COUNT of 63, a false alarm.
        leaves = {v for v in leaves if isinstance(v, float)}
        for bad in (round(lo_sum, 1), round(lo_sum, 2), round(hi_sum, 1), round(hi_sum, 2)):
            if bad:
                assert bad not in leaves, (c, bad, "a summed band reached a reconciliation block")
        for r in rows:
            if r[lo_i] is not None and r[hi_i] is not None:
                assert r[lo_i] <= r[hi_i], (c, r[0])
            assert r[cs_i] is None or isinstance(r[cs_i], (int, float)), (c, r[0])
    assert "never added" in d["copy"]["farm_dollar_is_not"]


def test_the_prospect_row_surplus_equals_the_trade_board_and_the_efv_export(d, shards, tv):
    P = "farm.prospects"
    xp = ROOT / "data" / "xfv.json"
    if not xp.exists():
        pytest.skip("xfv.json absent")
    xfv = json.loads(xp.read_text(encoding="utf-8"))["by_player"]
    k_i, s_i, lo_i, hi_i, g_i = [_col(d, P, k) for k in ("key", "surplus_mm", "band_lo_mm", "band_hi_mm", "tv_grade")]
    n = 0
    for c in d["clubs"]:
        for r in _rows(shards[c], P):
            t = tv["by_key"][r[k_i]]
            assert t["status"] == "active" and r[s_i] == t["trade_value_mm"], (c, r[k_i])
            assert r[lo_i] == t["trade_value_lo"] and r[hi_i] == t["trade_value_hi"] and r[g_i] == t["trade_value_grade"], (c, r[k_i])
            x = xfv.get(r[k_i])
            if x and x.get("surplus_mm") is not None:
                assert abs(r[s_i] - x["surplus_mm"]) <= 0.05, (c, r[k_i], "eFV export")
                n += 1
    assert n > 4000, "the equality is pinned on the whole active pool"


def test_the_slot_join_is_by_year_and_pick_never_by_name(d, shards):
    import storage
    P = "farm.prospects"
    rows = storage.load_draft_results()
    sirota = [r for r in rows if (r.get("player_key") or "").endswith("mike_sirota")]
    if len(sirota) < 2:
        pytest.skip("the Sirota fixture (two draft_results rows) is not on this box")
    signed = [r for r in sirota if r.get("signed")]
    assert len(signed) == 1 and signed[0]["draft_year"] == 2024 and signed[0]["pick_overall"] == 87
    unsigned = [x for x in sirota if not x.get("signed")][0]
    assert unsigned["slot_usd"] is None, "the name-match row carries no slot; a join on name would print none or the wrong one"
    k_i, y_i, p_i, sl_i, b_i = [_col(d, P, k) for k in ("key", "acq_year", "pick_overall", "slot_usd", "bonus_usd")]
    hit = None
    for c in d["clubs"]:
        for r in _rows(shards[c], P):
            if r[k_i] == "mike_sirota":
                hit = (c, r)
    if hit is None:
        pytest.skip("mike_sirota is not an active prospect on this board")
    c, r = hit
    assert (r[y_i], r[p_i]) == (2024, 87) and r[sl_i] == signed[0]["slot_usd"] and r[b_i] == signed[0]["bonus_usd"], c
    src = (ROOT / "ledger_export.py").read_text(encoding="utf-8")
    assert 'slot_by_year_pick.get((acq.get("year"), acq.get("pick_overall")))' in src
    i = src.index("slot_by_year_pick = {")
    assert "player_name" not in src[i:i + 220] and "player_key" not in src[i:i + 220]


def test_an_unsigned_pick_carries_no_over_slot_figure_and_the_pick_rows_sum_to_draft_paid(d, shards):
    """farm.picks over_slot_usd follows the v1 draft_paid slotted rule: bonus minus
    slot only when both are non-zero. An unsigned pick (bonus 0) prints no
    fabricated under-slot saving, and per club and year the rows sum to the v1
    draft_paid over_slot_usd exactly (ints, no tolerance)."""
    P = "farm.picks"
    sl_i, b_i, sg_i, ov_i = [_col(d, P, k) for k in ("slot_usd", "bonus_usd", "signed", "over_slot_usd")]
    n_rows = 0
    for c, club in d["clubs"].items():
        for y, rows in shards[c]["farm"]["picks"].items():
            paid = club["farm"]["draft_paid"][y]
            assert len(rows) == paid[0], (c, y, "the pick rows are the draft_paid population")
            for r in rows:
                n_rows += 1
                if r[sg_i] == 0:
                    assert r[ov_i] is None, (c, y, r, "an unsigned pick carries no over-slot figure")
                if r[sl_i] and r[b_i]:
                    assert r[ov_i] == int(r[b_i]) - int(r[sl_i]), (c, y, r)
                else:
                    assert r[ov_i] is None, (c, y, r, "no figure without both a slot and a bonus")
            assert sum(r[ov_i] or 0 for r in rows) == paid[7], (c, y, "rows sum to draft_paid over_slot_usd")
    assert n_rows
    assert "unsigned pick is not an under-slot saving" in d["field_key"][P]


def test_the_graduate_row_carries_two_engines_labelled_and_no_sum(d, shards, tv):
    G = "farm.graduates"
    fk = d["field_key"][G]
    assert "two engines" in fk and "never summed" in fk
    k_i, dv_i, tvv_i, src_i, inv_i = [_col(d, G, k) for k in ("key", "dv_trade_value_mm", "tv_trade_value_mm", "tv_surplus_source", "in_vets")]
    differ = both = 0
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], G)
        assert len(rows) == club["farm"]["n_graduates"], c
        dv_sum = round(sum(r[dv_i] or 0 for r in rows), 1)
        tv_sum = round(sum(r[tvv_i] or 0 for r in rows), 1)
        leaves = set(_leaves(club["farm"]))
        for bad in (dv_sum, tv_sum, round(dv_sum + tv_sum, 1)):
            if bad:
                assert bad not in leaves, (c, bad, "an engine total reached the board")
        for r in rows:
            if r[tvv_i] is not None:
                t = tv["by_key"][r[k_i]]
                assert t["status"] == "debuted" and r[tvv_i] == t["trade_value_mm"] and r[src_i] == t["surplus_source"], (c, r[k_i])
                if r[dv_i] is not None:
                    both += 1
                    differ += 1 if abs(r[dv_i] - r[tvv_i]) > 0.05 else 0
            assert isinstance(r[inv_i], bool)
    assert both > 100 and differ > both * 0.5, "the two engines are different numbers on most rows, which is why they are never averaged"
    assert "never averaged or summed" in d["copy"]["grad_two_engines"]
    for path, k, _v in _walk(d):
        assert "grad_total" not in str(k) and "engines_mean" not in str(k), path


def test_graduate_control_is_current_not_at_debut(d, shards, tv, proj):
    """The Control column is the current window (the trade board's control_thru,
    else the projections vet ctrlThru), never debuted_value's at-debut window,
    which is 7 on every priced row. A graduate neither source carries prints
    blank, so a 2010 debut can no longer read seven years of control.

    The vet is the graduate's own HUMAN: joined on the debuts_lite mlbam id
    where the graduate has one, and on the slug only where he does not. The
    slug join gave the ATH graduate max_muncy (691777) the LAD veteran's
    (571970) control window and in_vets flag."""
    G = "farm.graduates"
    assert "dv_remaining_control_years" not in d["columns"][G]
    k_i, th_i, why_i, dd_i, iv_i = [_col(d, G, k) for k in
                                    ("key", "control_thru", "control_why", "debut_date", "in_vets")]
    vets = {v["key"]: v for v in proj.get("vets") or [] if v.get("key")}
    vets_by_id = {int(v["mlbam"]): v for v in proj.get("vets") or [] if v.get("mlbam") is not None}
    dl = ROOT / "data" / "debuts_lite.json"
    if not dl.exists():
        pytest.skip("debuts_lite.json absent")
    dl_rows = json.loads(dl.read_text(encoding="utf-8"))
    dl_rows = dl_rows if isinstance(dl_rows, list) else (dl_rows.get("players") or [])
    grad_id = {g["player_key"]: g.get("mlbam_id") for g in dl_rows if g.get("player_key")}
    n = n_set = n_old = n_split = 0
    for c in d["clubs"]:
        for r in _rows(shards[c], G):
            n += 1
            t = tv["by_key"].get(r[k_i]) or {}
            t = t if t.get("status") == "debuted" else {}
            gid = grad_id.get(r[k_i])
            v = (vets_by_id.get(int(gid)) if gid is not None else vets.get(r[k_i])) or {}
            if gid is not None and r[k_i] in vets and int(vets[r[k_i]]["mlbam"]) != int(gid):
                n_split += 1
                assert r[iv_i] is bool(v), (c, r[k_i], "a different human's vet row is not this graduate's")
            if t.get("control_thru") is not None:
                want = (t["control_thru"], t.get("control_why"))
            elif v.get("ctrlThru") is not None:
                want = (v["ctrlThru"], v.get("ctrlWhy"))
            else:
                want = (None, None)
            assert (r[th_i], r[why_i]) == want, (c, r[k_i])
            if r[th_i] is not None:
                n_set += 1
            if r[dd_i] and int(r[dd_i][:4]) <= 2019:
                n_old += 1
                assert r[th_i] is None or r[th_i] == want[0], (c, r[k_i])
    assert n and 0 < n_set < n and n_old
    assert n_split, "the served graduates carry slugs a different vet holds; the join is exercised"
    assert "never the at-debut" in d["field_key"][G]


def test_draft_pool_usage_is_slotted_bonuses_over_the_pool(d):
    """Pool used divides the round 1-10 slotted bonuses by the published pool
    (the sum of those slot values). Dividing every round's bonuses printed
    146 of 159 club-years above the CBA's 5% tolerance; on the slotted
    numerator none exceed it."""
    n = 0
    for c, club in d["clubs"].items():
        for y, r in club["farm"]["draft_paid"].items():
            if not r[9]:
                continue
            n += 1
            assert r[10] == (round(r[6] / r[9], 3) if r[6] else None), (c, y)
            assert r[10] is None or r[10] <= 1.0505, (c, y, r[10], "over the 5% tolerance")
            assert r[3] >= r[6], (c, y, "paid, all rounds includes the slotted picks")
    assert n > 100
    assert "paid_usd_on_slotted / pool_usd" in d["field_key"]["farm.draft_paid"]
    assert "rounds 11 and later" in d["copy"]["pool_used_basis"]
    assert "its own column, not in Pool used" in d["copy"]["pool_used_basis"]


def test_round_11_over_the_cba_threshold_is_its_own_column_and_reconciles_to_the_pick_rows(d, shards):
    """Owner answers M10-3 (2026-09-25) and M9M10-1 (b) (2026-10-01): Pool used keeps
    rounds 1-10; the part of each round 11+ bonus above that draft year's CBA
    threshold is a separate column, draft_paid[11] with its pick count in [12] and
    the threshold in [13]. The threshold is read per draft year through
    fa_cba.draft_r11_threshold (125,000 for 2017-2021, 150,000 from 2022), never
    typed in the exporter. Per club and year it equals the shard's pick rows
    recomputed (ints, no tolerance), and Pool used never includes it."""
    import fa_cba
    import ledger_export as le
    assert not hasattr(le, "R11_THRESHOLD_USD") and not hasattr(le, "R11_FIRST_DRAFT")
    P = "farm.picks"
    rd_i, b_i = _col(d, P, "round_label"), _col(d, P, "bonus_usd")
    n_years = n_charged = n_early = 0
    for c, club in d["clubs"].items():
        assert sorted(club["farm"]["draft_paid"]) == [str(y) for y in range(2017, 2027)], c
        for y, r in club["farm"]["draft_paid"].items():
            assert len(r) == 14, (c, y, len(r))
            thr = fa_cba.draft_r11_threshold(int(y))["threshold_usd"]
            assert r[13] == thr == (125_000 if int(y) <= 2021 else 150_000), (c, y, r[13])
            rows = shards[c]["farm"]["picks"][y]
            over = [int(p[b_i]) - thr for p in rows
                    if str(p[rd_i] or "").isdigit() and int(p[rd_i]) > 10 and (p[b_i] or 0) > thr]
            assert r[11] == sum(over) and r[12] == len(over), (c, y, r[11], r[12], over)
            assert r[11] <= r[3], (c, y, "the charge is part of Paid, all rounds")
            if r[9]:
                assert r[10] == (round(r[6] / r[9], 3) if r[6] else None), (c, y, "Pool used stays rounds 1-10")
            if y == "2020":
                assert r[11] == 0 and r[12] == 0, (c, "the 2020 draft ran five rounds")
            n_years += 1
            n_charged += r[12] > 0
            n_early += int(y) <= 2021 and r[12] > 0
    assert n_years == 300 and n_charged > 150 and n_early > 60, (n_years, n_charged, n_early)
    fk = d["field_key"]["farm.draft_paid"]
    assert "pool_used, r11_over_usd, n_r11_over, r11_threshold_usd]" in fk and "null" not in fk
    sched = "$125,000 for the 2017 to 2021 drafts; $150,000 for the 2022 to 2026 drafts"
    assert sched in d["copy"]["r11_over_basis"] and sched in fk
    assert d["copy"]["r11_threshold_schedule"] == "CBA threshold: " + sched
    assert "The 2020 draft ran 5 rounds, so it has no such pick" in d["copy"]["r11_over_basis"]
    assert "n/a" not in d["copy"]["r11_over_basis"] and "$150,000" not in d["copy"]["pool_used_basis"]
    js = JS.read_text(encoding="utf-8")
    assert ("<th>Pool used</th><th title=\"' + esc(copy(\"r11_threshold_schedule\")) + '\">"
            "Round 11+ over the CBA threshold</th>") in js and 'copy("r11_over_basis")' in js
    assert "$150K" not in js and "isNum(r[13])" in js


def test_grad_contract_surplus_per_graduate_is_dark_and_the_mean_is_copied(d, org_summary):
    s = d["sections"]["grad_contract_per_graduate"]
    assert s["live"] is False and s["blocked_on"] == d["copy"]["grad_contract_dark"]
    assert "org mean only" in d["copy"]["grad_contract_dark"] and "no registry row" in d["copy"]["grad_contract_dark"]
    assert "six" in d["method"]["grad_contract_formula"] and "AAV minus bonus" in d["method"]["grad_contract_formula"]
    for c, club in d["clubs"].items():
        leaf = club["farm"]["leaves"]["fin_contract_surplus"]
        src = org_summary[c]["tree"]["fin_contract_surplus"]
        assert leaf["value"] == src.get("mean_usd_per_yr") and leaf["n"] == src.get("grad_count"), c
        assert leaf["n"] is None or leaf["n"] <= club["farm"]["n_graduates"], (c, "n is the rows with both an AAV and a bonus")
    for path, k, _v in _walk(d):
        assert "per_graduate_surplus" not in str(k) and "grad_surplus_rows" not in str(k), path


def test_the_farm_block_carries_the_calibration_stamp_of_every_source(d, shards, tv):
    cal = d["calibration"]
    assert set(cal["sources"]) == {"timeseries", "trade_values", "xfv", "mlb_projections"}
    for k, s in cal["sources"].items():
        assert s["version"] and s["generated_at"], k
    assert cal["version"] == tv["doc"]["calibration"]["version"] == cal["sources"]["trade_values"]["version"]
    assert cal["agree"] is (len({s["version"] for s in cal["sources"].values()}) == 1)
    xp = ROOT / "data" / "xfv.json"
    if xp.exists():
        import ledger_export as L
        meta = L._xfv_meta()
        assert meta["calibration"]["version"] == cal["sources"]["xfv"]["version"]
        assert meta["generated_at"] == cal["sources"]["xfv"]["generated_at"]
    for c in d["clubs"]:
        assert shards[c]["calibration"] == cal, c
    import test_calibration_vintage as TCV
    assert TCV._SURPLUS_ARTIFACTS.get("ledger_board.json") == ("calibration",), "owner decision D9"


def test_the_preview_is_the_top_n_of_the_shard_rows_and_n_is_published(d, shards):
    import ledger_export as L
    n = d["shards"]["preview_n"]
    assert n == L.PREVIEW_N or n == L.PREVIEW_N_SMALL
    s_i = _col(d, "farm.prospects", "surplus_mm")
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], "farm.prospects")
        assert club["farm"]["preview"] == rows[:n], c
        assert [r[s_i] for r in club["farm"]["preview"]] == sorted((r[s_i] for r in club["farm"]["preview"]), reverse=True), c
        traj = shards[c]["farm"]["prospect_trajectory"]
        assert set(traj) == {r[0] for r in rows[:n]}, (c, "per-player series for the preview keys only")
        for k, series in traj.items():
            for p in series:
                assert len(p) == 2 and isinstance(p[0], str) and isinstance(p[1], (int, float)), (c, k)
    assert "PREVIEW_N" in d["field_key"]["farm.preview"]


def test_the_actives_trajectory_is_status_filtered_and_labelled_gross(d, shards):
    """The two club series now ride in the shard (VAL1-Q1). Today's point equals
    the rows' gross only when the snapshot is the served board's vintage: the
    history is snapshotted by the monthly run, while a rebuild-only pass can
    re-export trade_values.json later the same day (2026-09-30: the snapshot at
    21:40Z predates the VAL_1, VAL_2 and ETA re-exports). Same vintage is read
    off the artifacts: the trade currency series' point for that date equals
    the served trade currency."""
    src = (ROOT / "ledger_export.py").read_text(encoding="utf-8")
    body = src[src.index("def _trade_trajectory_active"):src.index("def _player_trajectories")]
    assert "status = 'active'" in body and "GROUP BY org, snapshot_date" in body
    assert "gross" in d["copy"]["trajectory_active_basis"] and "each snapshot" in d["copy"]["trajectory_active_basis"]
    assert "not the leaf's series" in d["field_key"]["farm.trajectory_active"]
    for c, club in d["clubs"].items():
        ta = shards[c]["farm"]["trajectory_active"]
        v1 = shards[c]["surplus"]["trajectory"]
        fr = club["farm"]["reconciliation"]
        assert all(len(p) == 2 for p in ta), c
        assert [p[0] for p in ta] == sorted(p[0] for p in ta), c
        same_vintage = (bool(v1) and v1[-1][0] == fr["rows_generated_at"]
                        and abs(v1[-1][1] - club["surplus"]["trade_currency_mm"]) <= 0.15)
        if ta and ta[-1][0] == fr["rows_generated_at"] and same_vintage:
            assert abs(ta[-1][1] - fr["rows_gross_mm"]) <= 0.15, (c, "today's snapshot is the rows' gross")
        if ta and v1 and ta[-1][0] == v1[-1][0]:
            assert ta[-1][1] <= v1[-1][1] + 0.05, (c, "actives are a subset of the trade currency")


# --------------------------------------------------------------------------
# D5-2: arbitration per player
# --------------------------------------------------------------------------

def test_the_full_ladder_reproduces_tot_and_the_2027_rung_of_v1(d, shards):
    Lk = "arbitration.ladders"
    n_i, m_i, l_i, w_i, t_i = [_col(d, Lk, k) for k in ("name", "mlbam", "ladder", "war", "tot_usd")]
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], Lk)
        A = club["arbitration"]
        assert len(rows) == A["n"] == len(A["rows"]), c
        v1 = {r[1]: r for r in A["rows"]}
        for r in rows:
            lad = r[l_i]
            assert (r[t_i] or 0) == sum(t[1] for t in lad if t[1] is not None), (c, r[n_i], "tot is the ladder's non-null sum")
            assert len(r[w_i]) == len(lad), (c, r[n_i], "eWAR aligned to the ladder")
            r27 = next((t for t in lad if t[0] == d["class_year"]), None)
            v = v1[r[m_i]]
            assert (v[2], v[3], v[4], v[5]) == ((r27[4], r27[1], r27[2], r27[3]) if r27 else (None, None, None, None)), (c, r[n_i])
            for t in lad:
                assert len(t) == 5 and (t[1] is None or (t[2] <= t[1] <= t[3])), (c, r[n_i], t)
        assert sum(r[t_i] or 0 for r in rows) == A["remaining_usd"], c
        assert A["n_in_vets"] == sum(1 for r in rows if r[_col(d, Lk, "in_vets")]) and A["n_with_salpath"] == sum(1 for r in rows if r[_col(d, Lk, "has_salpath")]), c
        assert A["n_with_salpath"] <= A["n_in_vets"] <= A["n"], c


def test_the_arbitration_band_is_labelled_a_band_and_never_p10_p90(d):
    assert d["copy"]["band_note"] == "band, not a calibrated interval"
    assert "not P10/P90" in d["field_key"]["arbitration.ladders"] and "fixed-spread" in d["field_key"]["arbitration.ladders"]
    for k, v in d["copy"].items():
        if isinstance(v, str) and k.startswith("arb") and k != "arb_quantiles_dark":
            assert "P10" not in v and "P90" not in v, k
    assert "not published" in d["copy"]["arb_quantiles_dark"]
    js = JS.read_text(encoding="utf-8")
    for m in re.finditer(r"P10|P90", js):
        window = js[max(0, m.start() - 40):m.end() + 40].lower()
        assert "arb" not in window, (m.start(), window)


def test_arbitration_by_season_splits_arb_and_prearb_rungs_and_reproduces_v1_sums(d, shards):
    B, Lk = "arbitration.by_season", "arbitration.ladders"
    assert d["columns"][B] == ["season", "arb_rung_usd", "n_arb_rungs", "prearb_rung_usd", "n_prearb_rungs", "n_null_rungs"]
    assert "n_null_rungs counts rungs with proj null" in d["field_key"][B] and "neither is summed into the commitments stack" in d["field_key"][B]
    l_i = _col(d, Lk, "ladder")
    for c, club in d["clubs"].items():
        A = club["arbitration"]
        per = {}
        for r in _rows(shards[c], Lk):
            for season, proj, _lo, _hi, tok in r[l_i]:
                row = per.setdefault(season, [season, 0, 0, 0, 0, 0])
                if proj is None:
                    row[5] += 1
                elif tok == "PRE-ARB":
                    row[3] += proj
                    row[4] += 1
                else:
                    row[1] += proj
                    row[2] += 1
        assert A["by_season"] == [per[s] for s in sorted(per)], c
        bs = {row[0]: row for row in A["by_season"]}
        s27 = bs.get(d["class_year"], [d["class_year"], 0, 0, 0, 0, 0])
        assert s27[1] + s27[3] == A["s2027_usd"], (c, "the two parts of the v1 ladder sum")
        assert sum(row[1] + row[3] for row in A["by_season"]) == A["remaining_usd"], c
        assert A["s2027_note"] == "arb_prearb_rungs"
    league = {r["club"]: r for r in d["league"]["rows"]}
    for c, club in d["clubs"].items():
        assert league[c]["arb_exposure_2027"] == club["arbitration"]["s2027_usd"], (c, "D14: the league column keeps the v1 value")
    assert "pre-arbitration minimum sit in this sum" in d["copy"]["arb_prearb_rungs"]
    # the spec's worked example, recomputed from the artifact rather than typed
    arb = json.loads((ROOT / "data" / "arbitration.json").read_text(encoding="utf-8"))
    lad_rows = [r for r in arb["rows"] if r.get("t") == "LAD"]
    row28 = {row[0]: row for row in d["clubs"]["LAD"]["arbitration"]["by_season"]}.get(2028)
    if lad_rows and row28:
        n28 = sum(1 for r in lad_rows for t in r["l"] if t[0] == 2028 and t[4] != "PRE-ARB")
        null28 = sum(1 for r in lad_rows for t in r["l"] if t[0] == 2028 and t[1] is None)
        assert row28[2] + row28[5] == n28 and row28[5] == null28, "n_arb_rungs counts priced rungs; the null rungs sit apart"


def test_the_realized_rows_reproduce_the_v1_season_sums_and_keep_two_residual_columns(d, shards):
    R = "arbitration.realized.rows"
    cols = d["columns"][R]
    assert cols.index("ou_mkt_usd") != cols.index("ou_war_usd") and "swartz_usd" in cols and "team" not in cols
    s_i, a_i, o_i, m_i, w_i, war_i = [cols.index(k) for k in ("season", "actual_usd", "ours_usd", "ou_mkt_usd", "ou_war_usd", "war")]
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], R)
        by = {}
        for r in rows:
            by.setdefault(r[s_i], []).append(r)
        v1 = {s[0]: s for s in club["arbitration"]["realized"]["seasons"]}
        assert set(by) == set(v1), c
        for s, rs in by.items():
            exp = v1[s]
            assert exp[1] == len(rs), (c, s)
            assert exp[2] == int(sum(r[a_i] or 0 for r in rs)) and exp[3] == int(sum(r[o_i] or 0 for r in rs)), (c, s)
            assert exp[4] == int(sum(r[m_i] or 0 for r in rs)) and exp[5] == int(sum(r[w_i] or 0 for r in rs)), (c, s)
            assert abs(exp[6] - sum(float(r[war_i] or 0) for r in rs)) <= 0.011, (c, s)
        assert club["arbitration"]["realized"]["n"] == len(rows), c
        assert [r[s_i] for r in rows] == sorted((r[s_i] for r in rows), reverse=True), (c, "season desc")


def test_swartz_is_labelled_mlbtr_and_the_a6_statement_is_quoted_verbatim(d, shards):
    ae = json.loads((ROOT / "data" / "arbitration_eval.json").read_text(encoding="utf-8"))["a6_swartz"]
    E = d["arbitration_eval"]
    for k in ("n", "ours_mdape", "swartz_mdape", "ratio_ours_over_swartz", "verdict", "claim", "statement"):
        assert E[k] == ae[k], k
    assert E["verdict"] == "NULL"
    assert d["copy"]["swartz_a6"] == ae["statement"] and d["copy"]["swartz_a6_prefix"] == "a6 arm"
    assert d["copy"]["swartz_label"].startswith("MLB Trade Rumors, Matt Swartz")
    assert "MLB Trade Rumors" in d["field_key"]["arbitration.realized.rows"] and "swartz is neither" in d["field_key"]["arbitration.realized.rows"]
    sw_i = _col(d, "arbitration.realized.rows", "swartz_usd")
    n_sw = sum(1 for c in d["clubs"] for r in _rows(shards[c], "arbitration.realized.rows") if r[sw_i] is not None)
    hist = json.loads((ROOT / "data" / "arb_history.json").read_text(encoding="utf-8"))
    n_hist = sum(1 for r in hist["rows"] if r[7] is not None)
    assert n_sw == n_hist, "every Swartz figure on the history reaches a club row (OAK joins as ATH)"
    assert str(n_hist) in d["copy"]["swartz_label"] and str(ae["n"]) in d["copy"]["swartz_label"]
    js = JS.read_text(encoding="utf-8")
    assert "MLBTR (Swartz)" in js and 'copy("swartz_a6")' in js


def test_comps_filing_and_quantiles_are_dark_with_blockers(d):
    for k in ("arb_quantiles", "arb_comps", "arb_filing", "opt_out_value", "ifa_slot", "farm_years_to_fa"):
        s = d["sections"][k]
        assert s["live"] is False and s["blocked_on"], k
    assert d["sections"]["arb_comps"]["blocked_on"] == d["copy"]["arb_comps_dark"]
    assert "aav_usd" in d["copy"]["arb_comps_dark"] and "ARBITRATION_GATE 10" in d["copy"]["arb_comps_dark"]
    assert "svy" in d["copy"]["arb_filing_dark"]
    assert "MdAPE" in d["copy"]["arb_quantiles_dark"]
    for key in ("arbitration.ladders", "arbitration.realized.rows"):
        for name in d["columns"][key]:
            assert "comp" not in name and "filing" not in name and "hearing" not in name and "p10" not in name, (key, name)
    assert d["sections"]["arb_service_time"]["live"] is True and "inferred" in d["sections"]["arb_service_time"]["note"]


def test_the_arbitration_link_is_narrowed_only_when_the_page_honours_team(d):
    import ledger_export as L
    js = (ROOT / "assets" / "arbitration.js").read_text(encoding="utf-8")
    narrows = "TEAM_NARROW_RE" in js
    for c, club in d["clubs"].items():
        assert club["links"]["arbitration_teams"] == (f"/arbitration/#teams&team={c}" if narrows else "/arbitration/#teams"), c
    assert L.arbitration_link("LAD", "var x = 1;") == "/arbitration/#teams"
    assert L.arbitration_link("LAD", "var TEAM_NARROW_RE = /x/;") == "/arbitration/#teams&team=LAD"
    assert L.arbitration_link("LAD", js) == d["clubs"]["LAD"]["links"]["arbitration_teams"]


# --------------------------------------------------------------------------
# D5-3: contracts and surplus per contract
# --------------------------------------------------------------------------

def test_the_contract_path_npv_reproduces_sur_npv_at_the_payload_rate(d, shards):
    import ledger_export as L
    C = "contracts.paths"
    rate = d["accountability"]["discount_rate"]
    assert rate and 0 < rate < 0.2
    s_i, n_i, chk_i, k_i = [_col(d, C, k) for k in ("sur_mm", "sur_npv_usd", "npv_check_usd", "key")]
    worst = 0
    n = 0
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], C)
        assert [r[k_i] for r in rows] == [r[0] for r in club["contracts"]["rows"]], (c, "one path per priced row, same order")
        npv_by_key = {r[0]: r[9] for r in club["contracts"]["rows"]}
        for r in rows:
            assert r[n_i] == npv_by_key[r[k_i]], (c, r[k_i], "sur_npv_usd equals the contract row's")
            chk = L.npv_of_strip(r[s_i], rate)
            assert r[chk_i] == chk, (c, r[k_i])
            gap = abs(chk - (r[n_i] or 0))
            worst = max(worst, gap)
            assert gap <= L.NPV_TOL_USD, (c, r[k_i], gap)
            n += 1
    assert n > 800 and worst < L.NPV_TOL_USD
    assert "rounded to 0.1M" in d["copy"]["npv_identity"]
    strip = [88.5, 82.7, 57.6, 33.8, -7.0]
    assert L.npv_of_strip(strip, 0.07) == int(round(sum(v * 1e6 / 1.07 ** t for t, v in enumerate(strip))))
    assert L.npv_of_strip([None, None], 0.07) == 0 and L.npv_of_strip(None, 0.07) == 0


def test_sur_total_is_sur_ros_plus_sur_npv(d, shards, proj):
    import ledger_export as L
    C = "contracts.paths"
    t_i, r_i, n_i, k_i = [_col(d, C, k) for k in ("sur_total_usd", "sur_ros_mm", "sur_npv_usd", "key")]
    vets = {v["key"]: v for v in proj["vets"] if v.get("key")}
    worst = 0
    for c in d["clubs"]:
        for r in _rows(shards[c], C):
            v = vets[r[k_i]]
            assert r[t_i] == v.get("surTotal") and r[n_i] == v.get("surNpv") and r[r_i] == v.get("surRos"), (c, r[k_i])
            gap = abs(r[t_i] - (int(round((r[r_i] or 0.0) * 1e6)) + r[n_i]))
            worst = max(worst, gap)
            assert gap <= L.SURTOTAL_TOL_USD, (c, r[k_i], gap)
    assert worst <= L.SURTOTAL_TOL_USD


def test_the_trade_value_matches_sur_total_on_projection_rows_or_is_flagged_reanchored(d, shards, tv):
    import ledger_export as L
    C = "contracts.paths"
    k_i, t_i, tv_i, src_i, re_i = [_col(d, C, k) for k in ("key", "sur_total_usd", "tv_mm", "surplus_source", "reanchored")]
    n_proj = n_re = 0
    for c, club in d["clubs"].items():
        rows = _rows(shards[c], C)
        n_re_c = 0
        for r in rows:
            if r[tv_i] is not None:
                # joined on the projections key of the board row's human, never
                # on a slug another human holds on the board
                t = tv["by_proj_key"][r[k_i]]
                assert r[tv_i] == t["trade_value_mm"] and r[src_i] == t["surplus_source"], (c, r[k_i])
            if r[src_i] == "projection" and r[tv_i] is not None and r[t_i] is not None:
                n_proj += 1
                off = abs(r[tv_i] - r[t_i] / 1e6) > L.TV_MATCH_TOL_MM
                assert r[re_i] is off, (c, r[k_i], r[tv_i], r[t_i])
                n_re_c += 1 if off else 0
            else:
                assert r[re_i] is False, (c, r[k_i], "no equality asserted off the projection source")
        assert club["contracts"]["paths_summary"]["n_reanchored"] == n_re_c and club["contracts"]["paths_summary"]["n_paths"] == len(rows), c
        n_re += n_re_c
    assert n_proj > 800 and n_re < n_proj * 0.1, (n_proj, n_re, "most projection rows equal surTotal; the rest are flagged")
    assert "archetype posterior floor" in d["copy"]["tv_reanchored"]
    assert "FLOOR" in d["copy"]["prearb_min_floor"], "the prearb_min sentence is quoted from the artifact"


def test_the_war_path_is_expected_values_and_the_bands_are_never_summed(d, shards, proj):
    C = "contracts.paths"
    k_i, w_i, lo_i, hi_i, s_i = [_col(d, C, k) for k in ("key", "war", "war_p10", "war_p90", "sur_mm")]
    vets = {v["key"]: v for v in proj["vets"] if v.get("key")}
    for c, club in d["clubs"].items():
        for r in _rows(shards[c], C):
            v = vets[r[k_i]]
            assert r[w_i] == v["war"] and r[lo_i] == v.get("warP10") and r[hi_i] == v.get("warP90"), (c, r[k_i])
            # The WAR path is the five projected seasons; the surplus strip runs
            # through the last priced season, which is past the horizon on a
            # guarantee the contract tail prices (owner answer 2026-09-25).
            last_h = d["horizon"][-1]
            tail = [cell[0] for cell in (v.get("salPath") or []) if cell[0] > last_h]
            assert len(r[w_i]) == len(d["horizon"]), (c, r[k_i])
            assert len(r[s_i]) == len(d["horizon"]) + (max(tail) - last_h if tail else 0), (c, r[k_i])
            for t, w in enumerate(r[w_i]):
                if r[lo_i] and r[hi_i] and w is not None and r[lo_i][t] is not None:
                    assert r[lo_i][t] <= w <= r[hi_i][t] + 1e-9, (c, r[k_i], t)
        ps = club["contracts"]["paths_summary"]
        assert set(ps) == {"n_paths", "n_reanchored", "n_opt_out_rows", "n_opt_out_seasons"}
    fk = d["field_key"][C]
    assert "never summed" in fk and "per-season expected values" in fk
    assert "never summed" in d["copy"]["war_band_cell"]


def test_the_salary_source_split_reconciles_row_by_row(d, shards):
    C = "contracts.paths"
    k_i, n_i = _col(d, C, "key"), _col(d, C, "sur_npv_usd")
    for c, club in d["clubs"].items():
        src_by_key = {r[0]: (r[4] or "unknown") for r in club["contracts"]["rows"]}
        by = {}
        for r in _rows(shards[c], C):
            by[src_by_key[r[k_i]]] = by.get(src_by_key[r[k_i]], 0) + int(r[n_i] or 0)
        R = club["surplus"]["reconciliation"]
        assert set(R["by_salsrc"]) == set(club["surplus"]["mlb_by_salsrc_mm"]) == set(by), c
        for src, (served, rows_mm, n) in R["by_salsrc"].items():
            assert served == club["surplus"]["mlb_by_salsrc_mm"][src] == rows_mm == round(by[src] / 1e6, 1), (c, src)
            assert n == sum(1 for k, s in src_by_key.items() if s == src), (c, src)
        assert R["mlb_rows_mm"] == R["mlb_served_mm"] == club["surplus"]["mlb_mm"], c
        assert R["status"] == "exact", c


def test_the_trade_currency_equals_prospect_rows_plus_debuted_rows(d, shards, tv):
    P, T = "farm.prospects", "surplus.rows_debuted"
    s_i, tv_i, k_i, inc_i = _col(d, P, "surplus_mm"), _col(d, T, "tv_mm"), _col(d, T, "key"), _col(d, T, "in_contract_rows")
    for c, club in d["clubs"].items():
        R = club["surplus"]["reconciliation"]
        act = round(sum(r[s_i] or 0 for r in _rows(shards[c], P)), 1)
        deb_rows = _rows(shards[c], T)
        deb = round(sum(r[tv_i] or 0 for r in deb_rows), 1)
        assert abs(R["trade_rows_active_mm"] - act) <= 0.1 and abs(R["trade_rows_debuted_mm"] - deb) <= 0.1, c
        assert abs(R["trade_currency_served_mm"] - (act + deb)) <= 0.1 and R["trade_currency_served_mm"] == club["surplus"]["trade_currency_mm"], c
        assert R["farm_served_mm"] == club["surplus"]["farm_mm"] and R["farm_leaf_mm"] == club["farm"]["reconciliation"]["leaf_mm"], c
        assert abs((R["farm_served_mm"] or 0) - (R["farm_leaf_mm"] or 0)) <= 0.05, c
        assert len(deb_rows) == club["surplus"]["n_debuted_rows"] == club["surplus"]["crunch"]["n_debuted"], c
        keys = {r[0] for r in club["contracts"]["rows"]}
        for r in deb_rows:
            assert tv["by_key"][r[k_i]]["status"] == "debuted" and r[inc_i] is (r[k_i] in keys), (c, r[k_i])
    assert "never added to them" in d["copy"]["trade_currency_split"]


def test_opt_outs_are_stamped_not_priced_and_the_sentence_is_quoted(d, shards):
    sp = " ".join((ROOT / "salary_path.py").read_text(encoding="utf-8").split())
    assert "Pricing an opt-out needs an opt-out model with its own gate" in sp
    assert "the tooltip says the opt-out is not modelled" in sp
    btv = (ROOT / "bayes_trade_value.py").read_text(encoding="utf-8")
    assert "def _p_player_opts_out" in btv
    s = d["copy"]["opt_out_two_engines"]
    assert "opt-out not modelled" in s and "bayes_trade_value" in s and "neither is a served opt-out value" in s
    assert d["sections"]["opt_out_value"]["live"] is False and d["sections"]["opt_out_value"]["blocked_on"] == s
    C = "contracts.paths"
    po_i, k_i = _col(d, C, "player_opt_years"), _col(d, C, "key")
    total_rows = total_seasons = 0
    for c, club in d["clubs"].items():
        opts = {r[0]: r[11] for r in club["contracts"]["rows"]}
        n_rows = n_seasons = 0
        for r in _rows(shards[c], C):
            po = r[po_i]
            assert po == sorted({o[0] for o in opts[r[k_i]] if o[1] == "player"}), (c, r[k_i], "the option years are the v1 chips' years")
            if po:
                n_rows += 1
                n_seasons += len(po)
        ps = club["contracts"]["paths_summary"]
        assert ps["n_opt_out_rows"] == n_rows and ps["n_opt_out_seasons"] == n_seasons, c
        total_rows += n_rows
        total_seasons += n_seasons
    assert total_rows >= 1 and total_seasons >= total_rows
    for path, k, _v in _walk(d):
        assert "opt_out_value" not in str(k) or path.startswith("sections"), path


def test_picks_summary_splits_the_signed_picks_by_tracker_coverage(d):
    """A 2026 pick the prospect tracker does not carry is 'not tracked', never
    'no longer active' (M09-06: 212 of 565 signed 2026 picks are on the tracker)."""
    cols = d["columns"]["farm.picks_summary"] if "farm.picks_summary" in d.get("columns", {}) else None
    import ledger_export as LE
    cols = cols or LE.COLUMNS["farm.picks_summary"]
    assert cols == ["n_picks", "n_signed", "n_on_tracker", "n_graduated", "n_not_tracked", "n_unsigned_on_tracker"]
    assert "not every signed minor leaguer" in d["field_key"]["farm.picks_summary"]
    tot = {}
    for code, c in d["clubs"].items():
        shard = json.loads((ROOT / "data" / "ledger_clubs" / f"{code}.json").read_text(encoding="utf-8"))
        for y, ps in c["farm"]["picks_summary"].items():
            n_picks, n_signed, n_on, n_grad, n_not, n_unsigned_on = ps
            rows = shard["farm"]["picks"][y]
            assert n_picks == len(rows), (code, y)
            assert n_signed == sum(1 for r in rows if r[5]), (code, y)
            assert n_on + n_grad + n_not == n_signed and min(ps) >= 0, (code, y)
            t = tot.setdefault(y, [0, 0, 0])
            t[0] += n_signed
            t[1] += n_on
            t[2] += n_not
    # the 2026 class is two months old: most of it is untracked, not gone
    assert tot["2026"][0] > 500 and tot["2026"][2] > tot["2026"][1]


def test_tax_floor_census_names_every_club_below_its_own_guaranteed_2027_contracts(d):
    """M09-03: Spotrac 2027 tax payroll >= the AAV of the club's own guaranteed
    2027 contract rows. Recomputed here from the served rows; the census, the
    per-club block and the league flag all agree, and Spotrac's figure is never
    replaced."""
    import ledger_export as LE
    cen = d["accountability"]["tax_floor_census"]
    assert cen["n_clubs"] == 30 and "option" in cen["rule"]
    expect = {}
    for code, c in d["clubs"].items():
        opt = {r[0] for r in c["fa"]["outgoing"] if r[4] == "pending_option" and r[5] in LE.TAX_FLOOR_NOT_GUARANTEED}
        aav = sum(int(r[5] or 0) for r in c["contracts"]["rows"]
                  if any(x[0] == LE.CLASS_YEAR and x[5] == "contract" for x in (r[10] or []))
                  and r[0] not in opt and not any(o[0] == LE.CLASS_YEAR and o[1] in ("club", "mutual") for o in r[11]))
        tf = c["payroll"]["tax_floor_2027"]
        tax = c["payroll"]["s2027"]["tax_payroll_usd"]
        assert tf["guaranteed_aav_usd"] == aav and tf["spotrac_tax_payroll_usd"] == tax, code
        assert tf["gap_usd"] == tax - aav and tf["below"] == (tax - aav < 0), code
        if tf["below"]:
            expect[code] = tax - aav
    assert cen["below"] == expect
    rows = {r["club"]: r for r in d["league"]["rows"]}
    assert {c for c, r in rows.items() if r["tax_floor_below_2027"]} == set(expect)
    # owner answer M13-1: a club below its own guaranteed AAV takes the AAV as its
    # 2027 basis (space, CBT block, Cost+ family), and only such a club does;
    # Spotrac's figure stays in payroll.s2027 as published
    for code, c in d["clubs"].items():
        b = c["payroll"]["cbt_basis_2027"]
        tax = c["payroll"]["s2027"]["tax_payroll_usd"]
        assert b["spotrac_usd"] == tax and b["guaranteed_aav_usd"] == c["payroll"]["tax_floor_2027"]["guaranteed_aav_usd"], code
        if tax is not None:
            assert b["usd"] == max(tax, b["guaranteed_aav_usd"]), code
        assert (b["source"] == "guaranteed_aav") == (code in expect), code
        assert c["cbt"]["2027"]["tax_payroll_source"] == b["source"] and c["cbt"]["2027"]["spotrac_tax_payroll_usd"] == tax, code
        if b["usd"] is not None:
            assert c["payroll"]["space_2027"]["spotrac_usd"] + b["usd"] == LE.SPOTRAC_2027_BASIS_USD, code
            assert c["cbt"]["2027"]["tax_payroll_usd"] == b["usd"] == c["indexes"]["cost_plus_parts"]["guaranteed_usd"], code
    assert d["league"]["pools"]["cost_plus"]["n_guaranteed_aav_basis"] == len(expect)
    assert "below own contracts" == d["copy"]["tax_floor_flag"] and "stands in" in d["copy"]["tax_floor_note"]
    assert d["copy"]["cbt_basis_aav_label"]


def test_the_2027_basis_is_the_larger_of_spotrac_and_the_guaranteed_aav():
    import ledger_export as LE
    assert LE.cbt_payroll_basis(27_666_666, 39_500_000) == (39_500_000, "guaranteed_aav")
    assert LE.cbt_payroll_basis(39_500_000, 39_500_000) == (39_500_000, "spotrac")
    assert LE.cbt_payroll_basis(202_884_218, 193_930_144) == (202_884_218, "spotrac")
    assert LE.cbt_payroll_basis(None, 39_500_000) == (None, "spotrac")


def test_the_2027_surcharges_only_note_is_derived_from_an_exact_reconstruction(d):
    """Spotrac's 2027 estimate for a payor is the surcharge schedule alone on its
    247M basis. The flag is set only where the reconstruction lands within $1."""
    import ledger_export as LE
    n_flag = 0
    for code, c in d["clubs"].items():
        blk = c["cbt"]["2027"]
        est = blk["spotrac_est_bill_usd"]
        if est is None:
            assert blk["spotrac_est_is_surcharges_only"] is False, code
            continue
        sur = blk["spotrac_est_surcharges_only_usd"]
        assert blk["spotrac_est_is_surcharges_only"] == (abs(sur - est) <= 1), code
        n_flag += blk["spotrac_est_is_surcharges_only"]
    assert n_flag >= 1
    lad = d["clubs"]["LAD"]["cbt"]["2027"]
    if lad["spotrac_est_is_surcharges_only"]:
        rates = d["cba"]["rates"]
        over = lad["tax_payroll_usd"] - LE.SPOTRAC_2027_BASIS_USD
        t = d["cba"]["surcharge_tiers_usd"]
        manual = (rates["surcharge_rates"]["tier1"] * (t[1] - t[0]) + rates["surcharge_rates"]["tier2_repeat"] * (t[2] - t[1])
                  + rates["surcharge_rates"]["tier3"] * max(over - t[2], 0))
        assert abs(manual - lad["spotrac_est_bill_usd"]) <= 1
    assert "247M basis" in d["copy"]["cbt_spotrac_surcharges_only"]


def test_cost_plus_says_what_its_two_sides_hold_and_what_it_ranks(d):
    """Owner answers M13-4 and COSTPLUS-1: the Cost+ family divides by three
    parts (guaranteed salaries, projected arbitration awards, pre-arbitration
    minimum rungs) and its numerator leaves out the locked free agents. The
    disclosure and both rank correlations are measured every build, never typed."""
    import ledger_export as LE
    pool = d["league"]["pools"]["cost_plus"]
    rows = []
    for c in d["clubs"].values():
        I, P = c["indexes"], c["indexes"]["cost_plus_parts"]
        if I["cost_ratio_war_per_mm"] is None:
            continue
        den = P["guaranteed_usd"] + P["arb_usd"] + P["prearb_usd"]
        war_ex = I["proj_war_2027"] - I["locked_fa_2027"]["war"]
        rows.append((I["cost_ratio_war_per_mm"], -den, I["proj_war_2027_ex_fa"]))
        # the index, the $ per WAR and the $ per win all divide by the same parts
        assert abs(I["cost_ratio_war_per_mm"] - war_ex / (den / 1e6)) <= 0.003, c["club"]
        assert abs(I["usd_per_war"] - den / war_ex) / I["usd_per_war"] < 0.005, c["club"]
        assert abs(I["usd_per_win"] - den / (I["proj_wins_2027"] - I["locked_fa_2027"]["war"])) / I["usd_per_win"] < 0.005, c["club"]
    assert pool["n_spearman"] == len(rows) == 30
    rho_pay = LE._spearman([r[0] for r in rows], [r[1] for r in rows])
    rho_war = LE._spearman([r[0] for r in rows], [r[2] for r in rows])
    assert abs(pool["spearman_vs_neg_denominator"] - rho_pay) <= 0.02
    assert abs(pool["spearman_vs_proj_war"] - rho_war) <= 0.02
    basis = d["copy"]["cost_plus_basis"]
    assert "three parts" in basis and "locked free agents" in basis and "never added into one payroll figure" in basis
    assert f"Spearman {pool['spearman_vs_neg_denominator']:.2f}" in basis and f"{pool['spearman_vs_proj_war']:.2f} against projected WAR" in basis
    assert ("inverse cost rank" in basis) == (abs(pool["spearman_vs_neg_denominator"]) > abs(pool["spearman_vs_proj_war"]))
    cols = {c[0]: c for c in d["league"]["columns"]}
    for k in ("cost_plus", "usd_per_win", "usd_per_war"):
        assert LE.COST_PLUS_SIDES in cols[k][3], k
    assert LE._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0 and LE._spearman([1, 2], [1, 2]) is None


def test_the_cost_plus_denominator_parts_recompute_from_the_arbitration_ladders(d, proj):
    """M13-4: the arbitration and pre-arbitration parts are the club's 2027
    rungs in data/arbitration.json, apart, less any rung whose player already
    carries a signed 2027 contract salary cell (counted once, in the guaranteed
    part). They reconcile to the ledger's own arbitration by_season row."""
    import ledger_export as LE
    from trades import canonical_org
    arb = json.loads((ROOT / "data" / "arbitration.json").read_text(encoding="utf-8"))
    vets = {int(v["mlbam"]): v for v in proj["vets"] if v.get("mlbam") is not None}
    want = {}
    for r in arb["rows"]:
        c = canonical_org(r.get("t"))
        if c not in d["clubs"]:
            continue
        rung = next((t for t in (r.get("l") or []) if t[0] == LE.CLASS_YEAR), None)
        if rung is None or rung[1] is None:
            continue
        w = want.setdefault(c, [0, 0, 0])
        v = vets.get(int(r["m"])) if r.get("m") is not None else None
        cell = next((x for x in ((v or {}).get("salPath") or []) if x[0] == LE.CLASS_YEAR), None)
        usd = int(round(float(rung[1])))
        if cell is not None and cell[5] == "contract":
            w[2] += usd
        elif rung[4] == "PRE-ARB":
            w[1] += usd
        else:
            w[0] += usd
    for code, c in d["clubs"].items():
        P = c["indexes"]["cost_plus_parts"]
        a, p, x = want.get(code, [0, 0, 0])
        assert (P["arb_usd"], P["prearb_usd"], P["contract_dropped_usd"]) == (a, p, x), code
        s27 = {row[0]: row for row in c["arbitration"]["by_season"]}.get(LE.CLASS_YEAR) or [0, 0, 0, 0, 0, 0]
        assert P["arb_usd"] + P["prearb_usd"] + P["contract_dropped_usd"] == s27[1] + s27[3], code
    one = LE.cost_plus_arb_parts([{"m": 1, "l": [[2027, 780000, 0, 0, "PRE-ARB"]]}],
                                 {1: {"salPath": [[2027, 1e7, 1e7, 1e7, "signed", "contract", 0]]}}, 2027)
    assert one["n_contract_dropped"] == 1 and one["prearb_usd"] == 0


def test_locked_free_agents_leave_the_cost_plus_numerator(d, proj):
    """COSTPLUS-1: every fa_class member with status locked leaves the
    numerator with his 2027 champion-mean WAR, on the club the projection rolls
    him into; $ per projected win drops the same WAR from the wins."""
    from trades import canonical_org
    fa = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    locked = {m["key"] for m in fa["members"] if m.get("status") == "locked"}
    idx = d["class_year"] - int(proj.get("first_season") or d["class_year"])
    want = {}
    for v in proj["vets"]:
        if v.get("key") in locked and (v.get("warChamp") or [None])[idx] is not None:
            w = want.setdefault(canonical_org(v["team"]), [0, 0.0])
            w[0] += 1
            w[1] += float(v["warChamp"][idx])
    for code, c in d["clubs"].items():
        n, war = want.get(code, [0, 0.0])
        F = c["indexes"]["locked_fa_2027"]
        assert F["n"] == n and abs(F["war"] - war) <= 0.051, code
        assert abs(c["indexes"]["proj_war_2027_ex_fa"] - (c["indexes"]["proj_war_2027"] - war)) <= 0.051, code
    pool = d["league"]["pools"]["cost_plus"]
    assert pool["locked_fa_n"] == sum(n for n, _ in want.values())
    assert pool["locked_fa_not_in_projections"] == len(locked) - sum(1 for v in proj["vets"] if v.get("key") in locked)


def test_the_cost_plus_divisor_is_never_served_as_one_figure(d):
    """The NEVER list: the three parts are keys apart, their sum reaches no key
    on a club block, and the page prints them on separate rows."""
    for code, c in d["clubs"].items():
        P = c["indexes"]["cost_plus_parts"]
        total = P["guaranteed_usd"] + P["arb_usd"] + P["prearb_usd"]
        if total in (P["guaranteed_usd"], P["arb_usd"], P["prearb_usd"]):
            continue
        assert total not in set(_leaves(c)), code
    js = JS.read_text(encoding="utf-8")
    body = js[js.index("function costParts("):js.index("function costTitle(")]
    assert "P.guaranteed_usd + " not in body and "+ P.arb_usd" not in body


# --------------------------------------------------------------------------
# The option and opt-out calendar (owner answer 2026-09-25, census M09-07)
# --------------------------------------------------------------------------

def test_the_options_calendar_carries_every_pending_class_option_once_at_its_club(d):
    """Every fa_class member with a pending option lands on exactly one club's
    calendar, with the class row's option price as the salary at stake and a
    price only where fa_export band-priced the row."""
    import ledger_export as LE
    from trades import canonical_org
    fa = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    cols = d["columns"]["options.calendar"]
    assert cols == LE.COLUMNS["options.calendar"]
    i = {n: k for k, n in enumerate(cols)}
    seen = {}
    for code, c in d["clubs"].items():
        O = c["options_calendar"]
        assert O["n"] == len(O["rows"]) and O["n_priced"] == sum(1 for r in O["rows"] if r[i["priced"]])
        assert set(O) == {"rows", "n", "n_priced"}, "counts only: no dollar total on the block"
        for r in O["rows"]:
            assert r[i["key"]] not in seen, r[i["key"]]
            seen[r[i["key"]]] = (code, r)
    pending = [m for m in fa["members"] if m.get("status") == "pending_option"]
    assert pending, "the class carries pending options"
    for m in pending:
        code, r = seen[m["key"]]
        assert code == canonical_org(m["from"]), m["key"]
        assert r[i["type"]] == m["type"] and r[i["holder"]] == LE.OPTION_HOLDER[m["type"]]
        assert r[i["salary_usd"]] == (int(m["optPrice"]) if m.get("optPrice") else None), m["key"]
        assert r[i["salary_basis"]] == ("remaining_guarantee" if m["type"] == "opt_out" else "option_year_salary")
        band = str(m.get("enterProbSrc") or "").startswith("band_priced") and m.get("optValue") is not None
        assert r[i["priced"]] is band, m["key"]
        if band:
            p = m["enterProb"] if m["type"] == "opt_out" else 1 - m["enterProb"]
            assert abs(r[i["p_exercise"]] - round(p, 3)) < 1e-9 and r[i["option_value_usd"]] == int(m["optValue"]), m["key"]
            assert r[i["unpriced_reason"]] is None
        else:
            assert r[i["p_exercise"]] is None and r[i["option_value_usd"]] is None
            assert r[i["unpriced_reason"]] in LE.OPTION_UNPRICED_REASONS, m["key"]
        assert r[i["state"]] == "pending"
        assert r[i["decision_by"]] == d["league"]["options_calendar"]["decision"]["decision_by"]
    S = d["league"]["options_calendar"]
    assert S["n_rows"] == len(seen) and S["n_priced"] == sum(1 for _c, r in seen.values() if r[i["priced"]])
    assert S["n_unjoined"] == 0
    assert sum(S["unpriced_by_reason"].values()) == S["n_rows"] - S["n_priced"]
    assert d["sections"]["options_calendar"]["live"] is True
    assert f"{S['n_priced']} of {S['n_rows']}" in d["sections"]["options_calendar"]["note"]
    for path, k, _v in _walk(d["league"]["options_calendar"]):
        assert not str(k).endswith("_usd"), (path, "the league summary carries counts, never a dollar figure")


def test_the_options_calendar_rule_on_a_small_class():
    """The pure builder: P(exercise) is 1 - P(enter) for a club or player option
    and P(enter) for an opt-out; mutual, conditional, unprojected and strikeless
    rows carry terms and a reason; a resolution event wins over the row status;
    a row whose club is not one of the thirty is counted, never placed."""
    import ledger_export as LE
    band = {"enterProbSrc": "band_priced_club_side", "optValue": 5_000_000}

    def mem(key, club, otype, price, p_enter, priced=False, **kw):
        m = {"key": key, "name": key.upper(), "from": club, "status": "pending_option", "type": otype,
             "optPrice": price, "enterProb": p_enter}
        if priced:
            m.update(band)
        m.update(kw)
        return m

    members = [
        mem("a", "TBR", "club_option", 20_000_000, 0.2, True),
        mem("b", "SDP", "opt_out", 32_000_000, 0.6, True),
        mem("c", "SDP", "player_option", 4_500_000, 0.35, True),
        mem("d", "CHC", "mutual_option", 8_000_000, 0.85),
        mem("e", "HOU", "conditional_club_option", 13_400_000, 0.5),
        mem("f", "CLE", "club_option", 7_300_000, 0.69, noProj="no_recent_seasons"),
        mem("g", "ARI", "mutual_option", 0, 0.85),
        {"key": "h", "name": "H", "from": "TBR", "status": "locked", "type": "ufa"},
        {"key": "i", "name": "I", "from": "MIL", "status": "locked", "type": "ufa"},
        mem("j", "Cuba", "club_option", 1_000_000, None),
    ]
    events = [{"type": "option_declined", "key": "i", "date": "2026-11-03", "optPrice": 9_000_000},
              {"type": "option_exercised", "key": "a", "date": "2026-11-02"},
              {"type": "signing", "key": "h", "date": "2026-11-20"}]
    clubs = {"TBR", "SDP", "CHC", "HOU", "CLE", "ARI", "MIL"}
    by, S = LE.options_calendar(members, events, {"a", "b"}, "2026-11-05", clubs)
    i = {n: k for k, n in enumerate(LE.COLUMNS["options.calendar"])}
    rows = {r[0]: r for rs in by.values() for r in rs}
    assert set(rows) == set("abcdefgi") and S["n_unjoined"] == 1, "the UFA h never enters; j's club is not one of the thirty"
    a, b, c = rows["a"], rows["b"], rows["c"]
    assert a[i["state"]] == "exercised" and a[i["decided_on"]] == "2026-11-02" and a[i["decision_by"]] is None
    assert abs(a[i["p_exercise"]] - 0.8) < 1e-9, "a club option is exercised when the player does not enter"
    assert abs(b[i["p_exercise"]] - 0.6) < 1e-9 and b[i["salary_basis"]] == "remaining_guarantee"
    assert abs(c[i["p_exercise"]] - 0.65) < 1e-9 and c[i["holder"]] == "player"
    assert [rows[k][i["unpriced_reason"]] for k in "defg"] == ["mutual", "conditional", "no_projection", "mutual"]
    assert rows["g"][i["salary_usd"]] is None, "a zero option price is not on file, never $0"
    assert rows["d"][i["p_exercise"]] is None and rows["d"][i["option_value_usd"]] is None, "a fixed prior is not a price"
    assert rows["i"][i["state"]] == "declined" and rows["i"][i["type"]] == "option" and rows["i"][i["salary_usd"]] == 9_000_000
    assert b[i["decision_by"]] == "2026-11-05" and a[i["in_projections"]] is True and c[i["in_projections"]] is False
    assert [r[0] for r in by["TBR"]] == ["a"] and [r[0] for r in by["SDP"]] == ["b", "c"], "pending first, then the larger salary"
    assert S["n_rows"] == 8 and S["n_priced"] == 3 and S["by_state"] == {"declined": 1, "exercised": 1, "pending": 6}
    assert S["unpriced_by_reason"] == {"mutual": 2, "conditional": 1, "no_projection": 1, "no_band": 1}


def test_the_decision_day_reads_the_season_calendar_on_disk(tmp_path):
    import ledger_export as LE
    assert LE.option_decision_by("2026-10-31") == "2026-11-05" and LE.option_decision_by(None) is None
    assert LE.postseason_end_on_disk(2026, tmp_path) is None, "no cached calendar, no date"
    (tmp_path / "season_2026.json").write_text(json.dumps({"seasons": [
        {"seasonId": "2026", "regularSeasonStartDate": "2026-03-25", "regularSeasonEndDate": "2026-09-27",
         "postSeasonEndDate": "2026-10-31"}]}), encoding="utf-8")
    assert LE.postseason_end_on_disk(2026, tmp_path) == "2026-10-31"
    assert LE.postseason_end_on_disk(2025, tmp_path) is None


def test_the_options_calendar_copy_names_its_sources_and_its_limits(d):
    import ledger_export as LE
    cp = d["copy"]
    for k in ("options_title", "options_lede", "options_decision_rule", "options_p_exercise_basis", "options_value_basis",
              "options_not_summed", "options_none", "options_later", "options_source", "options_terms_only",
              "options_decision_unknown", "options_resolved_note", "options_league_summary",
              "options_no_strike_short"):
        assert cp.get(k), k
        assert chr(0x2014) not in cp[k] and chr(0x2013) not in cp[k], k
    assert set(cp["options_unpriced"]) == set(LE.OPTION_UNPRICED_REASONS)
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    v = next(m["verdict"] for m in reg["models"] if m["model_id"] == "fa_penter")
    assert f"fa_penter, {v}" in cp["options_p_exercise_basis"], "the registry verdict is quoted, never typed"
    assert "never added" in cp["options_value_basis"] and "never added" in cp["options_not_summed"]
    dec = d["league"]["options_calendar"]["decision"]
    if dec["ws_scheduled_last_day"]:
        assert dec["ws_scheduled_last_day"] in cp["options_decision_rule"]
    assert any("options calendar" in s for s in d["what_this_page_does_not_claim"])
