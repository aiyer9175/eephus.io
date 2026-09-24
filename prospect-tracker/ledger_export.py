# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Build data/ledger_board.json, the payload behind /ledger/ (Club Ledger).

WHAT THIS PAGE IS. A ledger: what each club has on the books, what it owes, what
it controls, and what the platform's own prices say each dollar buys. Every
figure is read off a served artifact or the database; nothing here re-prices a
contract, a projection or a surplus, and nothing here opens a socket.

WHAT IT NEVER SERVES, decided before the first number was computed:

  * A SINGLE PROJECTED PAYROLL. The commitments block carries three labelled
    segments per season (contract dollars on file, projected arbitration steps,
    pre-arbitration minimums by rule) plus the count of vets with no price, and
    no key sums them. A club payroll forecast assembled from a provisional
    arbitration model, an inferred class token, rule minimums and a
    carry-forward CBA would need its own registry row (club_payroll_path) and a
    backtest on the 2016-2025 payroll history, and it has neither.
  * Revenue, attendance money, TV money, franchise valuations, revenue-sharing
    status, minor-league payroll, actual CBT bills paid. No source in the tree
    carries them; the page says so and the writer refuses any key by those
    names.
  * A colour on a salary, a club surplus total or a cap-space cell. Salaries are
    costs, cap space is a capacity fact, and the surplus ladder was cut on player
    rows; only Cost+ and OrgSur+ (100+10z indexes) take the z ladder.
  * ou_mkt and ou_war in one number. The arbitration history artifact says
    never_combine and this file honours it.

THE JOIN TRAPS, handled once: fa_meta.teams carries 32 keys (AVERAGES and OAK),
fa_team_payroll carries an AVERAGES row for 2027, trade_values carries 31 org
values (the 31st is "Cuba"), arb_history carries OAK. Everything goes through
trades.canonical_org and the writer asserts exactly 30 clubs.

TWO CBT BASES, never mixed. Spotrac's 2027 page computes space against
247,000,000; the platform's cba_rules carry 244,000,000 forward from 2026 as an
explicitly-unknown value. Both figures ship, each labelled with its basis.

ONE PAYLOAD. The per-club blocks are compact arrays with a single `field_key`
legend and a single `copy` block, because the first cut with per-club dicts and
per-club sentences measured 1,275 KB against the 1 MB line that decides between
one file and thirty lazy ones. Every sentence the page prints lives here once.

Deterministic. python ledger_export.py writes the file; build() returns the
document and never writes, so a test can call it under tmp_path.
"""
from __future__ import annotations

import json
import logging
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

OUT = ROOT / "data" / "ledger_board.json"
DATA = ROOT / "data"

SEASON_NOW = 2026
CLASS_YEAR = 2027
HORIZON = (2027, 2028, 2029, 2030, 2031)
DRAFT_YEARS = tuple(range(2017, 2027))
POOL_YEARS = ("2021", "2022", "2023", "2024", "2025", "2026")
IFA_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)

#: Spotrac's own 2027 basis, measured on the cached page: tax_payroll_usd +
#: space_usd = 247,000,000 on all 30 rows. Held as a MEASUREMENT (asserted
#: against the rows at build time), never as a rule.
SPOTRAC_2027_BASIS_USD = 247_000_000

#: Registry rows whose verdicts the Method tab quotes beside the numbers.
REGISTRY_IDS = ("arb_award", "team_win_projections", "prospect_surplus", "fa_market",
                "fa_projection_marcel", "fa_team_fit", "fa_dpw_series", "draft_slot_curve",
                "org_sur_plus", "dvm_plus_dollar", "farm_grades", "trade_machine_surplus",
                "ifa_step_prior")

#: Key names the writer refuses to emit anywhere in the document. The QO tier
#: key revenue_sharing_recipient is a rule-file vocabulary word for a tier the
#: page shows as a league value only; it is not one of these names.
FORBIDDEN_KEYS = {"revenue", "revenues", "attendance", "valuation", "valuations", "tv",
                  "tv_money", "rsn", "room_plus"}
FORBIDDEN_KEY_FRAGMENTS = ("projected_payroll", "payroll_forecast")

FIN_LEAVES = ("fin_active_surplus", "fin_dollar_dvm", "fin_contract_surplus",
              "fin_war_per_m", "fin_draft_pool_efficiency", "fin_ifa_roi")
LEAF_VALUE = {
    "fin_active_surplus": ("surplus_total_mm", "active_count", "$M controlled surplus, active prospects"),
    "fin_dollar_dvm": ("dollar_dvm_plus", "n", "$DvM+ within FV tier (tier-relative scale, unvalidated)"),
    "fin_contract_surplus": ("mean_usd_per_yr", "grad_count", "usd per year: current AAV minus bonus amortized over six years, graduates"),
    "fin_war_per_m": ("value", "grad_count", "WAR per $M of bonus, graduates"),
    "fin_draft_pool_efficiency": ("war_per_m_pool", "grad_count", "WAR per $M of draft pool in window"),
    "fin_ifa_roi": ("war_per_m_ifa", "grad_count", "WAR per $M of IFA bonus, eight-season window"),
}

PAYOR_NEXT = {"Non-Tax": "1st-Time", "1st-Time": "2nd-Time", "2nd-Time": "3+-Time",
              "3+-Time": "3+-Time"}
PAYOR_SEASONS = {"Non-Tax": 0, "1st-Time": 1, "2nd-Time": 2, "3+-Time": 3}
PAYOR_BASIS_SPOTRAC = "spotrac"              # the 2027 page: payor_2027 and the 2027 CBT block
PAYOR_BASIS_SPOTRAC_2026 = "spotrac_2026"    # the 2026 tax page: the 2026 CBT block
PAYOR_BASIS_DERIVED = "derived from the 2026 status + 2026 overage"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _j(name: str):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ledger_export: %s unreadable: %s", name, exc)
        return None


def _r(v, nd=1):
    try:
        if v is None or v != v:
            return None
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _canon(raw):
    from trades import canonical_org
    return canonical_org(raw) if raw else None


def _pct_str(rate: float) -> str:
    return f"{rate * 100:g} pct"


def _isum(rows, key):
    return int(sum(float(r.get(key) or 0) for r in rows))


# --------------------------------------------------------------------------
# the CBT computation (rule application, unit-tested against cba_rules.json)
# --------------------------------------------------------------------------

def payor_base_key(tier: str | None) -> str:
    """cba_rules base_rate_by_payor_year key for a Spotrac payor token. A
    Non-Tax club that is over the threshold pays as a first-time payor."""
    t = (tier or "Non-Tax").strip()
    if t.startswith("2nd"):
        return "2"
    if t.startswith("3"):
        return "3+"
    return "1"


def computed_cbt_bill(tax_payroll_usd, threshold_usd, tier, rates, tiers) -> dict:
    """The 2022 CBA schedule applied to a tax payroll.

    rates: cba_rules cbt_tax_rates; tiers: the three surcharge offsets above
    the threshold. Returns {over_usd, bill_usd, bracket, base_rate}. Nothing
    here is hard-coded: the rates and the offsets come from the rule file the
    caller read."""
    if tax_payroll_usd is None or threshold_usd is None:
        return {"over_usd": None, "bill_usd": None, "bracket": None, "base_rate": None}
    over = float(tax_payroll_usd) - float(threshold_usd)
    t1, t2, t3 = [float(x) for x in tiers[:3]]
    base_key = payor_base_key(tier)
    base = float(rates["base_rate_by_payor_year"][base_key])
    sur = rates["surcharge_rates"]
    s1 = float(sur["tier1"])
    s2 = float(sur["tier2_first"] if base_key == "1" else sur["tier2_repeat"])
    s3 = float(sur["tier3"])
    if over <= 0:
        return {"over_usd": int(round(over)), "bill_usd": 0, "bracket": "under", "base_rate": base}

    def clip(x, lo, hi):
        return max(lo, min(hi, x))

    bill = (base * min(over, t1)
            + (base + s1) * clip(over - t1, 0.0, t2 - t1)
            + (base + s2) * clip(over - t2, 0.0, t3 - t2)
            + (base + s3) * max(over - t3, 0.0))
    if over <= t1:
        bracket = "base"
    elif over <= t2:
        bracket = "surcharge_1"
    elif over <= t3:
        bracket = "surcharge_2"
    else:
        bracket = "surcharge_3"
    return {"over_usd": int(round(over)), "bill_usd": int(round(bill)), "bracket": bracket,
            "base_rate": base}


def farm_leaf(tree: dict, grades: dict, key: str) -> dict:
    """One fin_* leaf for the farm block: the LETTER copied from org_summary
    .grades (computed by rank across 30 orgs in storage._letter_grade, never
    recomputed here), the score_100 the tree already carries, the leaf's own
    headline value and count. A sparse leaf (the tree says so, or it has no
    score) prints a dash, never an unfair letter, exactly as PROSPX does."""
    leaf = (tree or {}).get(key) or {}
    vk, nk, _basis = LEAF_VALUE[key]
    sparse = bool(leaf.get("sparse")) or leaf.get("score_100") is None
    entry = {"letter": ((grades or {}).get(key) if not sparse and (grades or {}).get(key) else " - "),
             "score_100": leaf.get("score_100") if not sparse else None,
             "value": leaf.get(vk), "n": leaf.get(nk), "sparse": sparse}
    if key == "fin_war_per_m" and leaf.get("channels"):
        entry["channels"] = {ch: {"war_per_million": v.get("war_per_million"), "war_sum": v.get("war_sum"),
                                  "bonus_usd": v.get("bonus_usd"), "grad_count": v.get("grad_count")}
                             for ch, v in leaf["channels"].items()}
    if key == "fin_active_surplus" and leaf.get("method_efficiency"):
        entry["method_efficiency"] = {m: {"surplus_total_mm": v.get("surplus_total_mm"), "count": v.get("count"),
                                          "cost_basis_mm": v.get("cost_basis_mm"),
                                          "surplus_per_fv_pt_mm": v.get("surplus_per_fv_pt_mm")}
                                      for m, v in leaf["method_efficiency"].items()}
    return entry


def bracket_labels(tiers) -> dict:
    """Bracket names built from the rule offsets, never typed."""
    t = [int(x) // 1_000_000 for x in tiers[:3]]
    return {"under": "under the threshold",
            "base": f"base bracket (up to {t[0]}M over)",
            "surcharge_1": f"first surcharge ({t[0]}-{t[1]}M over)",
            "surcharge_2": f"second surcharge ({t[1]}-{t[2]}M over)",
            "surcharge_3": f"third surcharge ({t[2]}M+ over)"}


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------

def _team_names() -> dict:
    """canonical club -> StatsAPI name, from the cached /api/v1/teams payload."""
    out = {}
    try:
        raw = json.loads((ROOT / ".cache" / "statsapi_teams_2026.json").read_text(encoding="utf-8"))
        for t in raw.get("teams") or []:
            if (t.get("sport") or {}).get("id") not in (1, None):
                continue
            c = _canon(t.get("abbreviation"))
            if c:
                out[c] = t.get("name")
    except (OSError, ValueError, AttributeError):
        pass
    return out


def _payroll_rows() -> tuple[dict, dict, dict]:
    """{(club, season): row} for the clubs, the AVERAGES rows, and the join census.

    The census also carries each row's fetch stamp (fetched_at, date part) keyed
    (canonical code or AVERAGES, season): the League footer's two means are two
    fetches of one Spotrac page, and the page has to say when each was taken."""
    import storage
    raw = storage.load_fa_team_payroll()
    clubs: dict = {}
    averages: dict = {}
    for (team, season), row in raw.items():
        if team == "AVERAGES":
            averages[int(season)] = row
            continue
        c = _canon(team)
        if not c:
            continue
        key = (c, int(season))
        if key in clubs and team != c:
            continue      # an alias row never overwrites the canonical one
        clubs[key] = row
    stamps: dict = {}
    try:
        with storage.connect() as con:
            for team, season, at in con.execute(
                    "SELECT team, season, fetched_at FROM fa_team_payroll").fetchall():
                key = ("AVERAGES" if team == "AVERAGES" else _canon(team), int(season))
                if key[0] and at and (key not in stamps or str(at)[:10] > stamps[key]):
                    stamps[key] = str(at)[:10]
    except Exception as exc:                      # noqa: BLE001
        log.warning("ledger_export: fa_team_payroll stamps unavailable: %s", exc)
    return clubs, averages, {"rows_in": len(raw), "club_rows": len(clubs),
                             "averages_rows": len(averages), "fetched_at": stamps}


def footer_means_note(av_fetched, clubs_fetched, gap_usd, class_year) -> str:
    """The one sentence beneath the League footer: why Spotrac's league-average row
    and the mean of the 30 club rows disagree on Committed {class_year}.

    MEASURED 2026-09-23: the gap (about $17.0M) is VINTAGE, not basis. Both figures
    are Spotrac total payroll allocations for 2027. The AVERAGES row in
    fa_team_payroll is the last one the payroll-page parser emitted, fetched
    2026-07-07 (the 2026-09-23 page parses to the 30 clubs and no Averages row, so
    the nightly refresh rewrites the clubs and leaves the average where it was),
    while the club rows carry the 2026-09-23 stamp; that page's own Averages row
    reads 144,788,882, the computed mean to the dollar. test_ledger_export pins the
    sentence to the two stamps and, where the page cache is on disk, to that
    identity. When the stamps agree the sentence says so and the gap is the whole
    story, which the same test then requires to be small."""
    if gap_usd is None:
        return ""
    g = f"${abs(gap_usd) / 1e6:.1f}M"
    if av_fetched and clubs_fetched and av_fetched < clubs_fetched:
        return (f"The two rows differ by {g} because Spotrac's league average is the page's average "
                f"row as fetched {av_fetched}, while the 30 club rows were refetched {clubs_fetched}; "
                f"the basis is the same (Spotrac total payroll allocations {class_year}), so the gap "
                f"is {class_year} money that reached club books between the two fetches.")
    return f"Both rows are from the {clubs_fetched or av_fetched} fetch and differ by {g}."


def _trade_trajectory() -> dict:
    """club -> [[snapshot_date, sum trade_value_mm]] since the first snapshot."""
    import storage
    out: dict = defaultdict(list)
    try:
        with storage.connect() as con:
            rows = con.execute(
                "SELECT org, snapshot_date, SUM(trade_value_mm) FROM trade_value_history "
                "WHERE org IS NOT NULL GROUP BY org, snapshot_date ORDER BY snapshot_date"
            ).fetchall()
    except Exception as exc:                      # noqa: BLE001
        log.warning("ledger_export: trade_value_history unavailable: %s", exc)
        return {}
    for org, d, mm in rows:
        c = _canon(org)
        if c and mm is not None:
            out[c].append([d, round(float(mm), 1)])
    return dict(out)


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------

def build() -> dict:
    import fa_cba
    import fa_market
    import storage
    from salary_path import LEAGUE_MIN_CURATED
    from trades import statsapi_code

    # ---- inputs -----------------------------------------------------------
    fa_meta = _j("fa_meta.json") or {}
    proj = _j("mlb_projections.json") or {}
    tv = _j("trade_values.json") or {}
    arb = _j("arbitration.json") or {}
    arb_hist = _j("arb_history.json") or {}
    fa_class = _j("fa_class.json") or {}
    fa_2028 = _j("fa_class_2028.json") or {}
    fa_2029 = _j("fa_class_2029.json") or {}
    fa_archive = _j("fa_archive.json") or {}
    ts = _j("timeseries.json") or {}
    slot_curve = _j("draft_slot_curve.json") or {}
    ifa_ts = _j("ifa_timeseries.json") or {}
    org_tend = _j("org_tendencies.json") or {}
    registry = _j("model_registry.json") or {}
    dpw_series = _j("fa_dpw_series.json") or (fa_meta.get("dpw_series") or {})
    options_file = _j("contract_options.json") or {}

    payroll, averages, payroll_join = _payroll_rows()
    names = _team_names()
    clubs = sorted({c for (c, s) in payroll if s == SEASON_NOW})
    assert len(clubs) == 30, f"expected 30 clubs after the canonical join, got {len(clubs)}: {clubs}"

    # CBA rule inputs, resolved through fa_cba (never typed)
    thr = {s: fa_cba.cbt_threshold(s) for s in range(2017, 2028)}
    T_now = thr[SEASON_NOW]["threshold_usd"]
    T_next = thr[CLASS_YEAR]["threshold_usd"]
    rates = fa_cba.cbt_tax_rates()
    tiers = fa_cba.cbt_surcharge_tiers()
    brackets = bracket_labels(tiers)
    rules_doc = fa_cba._rules()
    cba_expiry = next((r["effective_to"] for r in rules_doc.get("cba_regimes", [])
                       if r.get("regime") == "cba_2022"), "2026-12-01")
    banner_text = (f"Every {CLASS_YEAR} figure is a 2022 CBA carry-forward: the agreement expires "
                   f"{cba_expiry} and no threshold, league minimum, arbitration structure or "
                   "qualifying-offer value past it has been published. Where Spotrac uses a "
                   f"different {CLASS_YEAR} basis the page prints both, each labelled.")
    unverified = fa_cba.unverified_records()

    # measured bases, asserted rather than assumed
    for c in clubs:
        r26, r27 = payroll.get((c, SEASON_NOW)) or {}, payroll.get((c, CLASS_YEAR)) or {}
        if r26.get("tax_payroll_usd") is not None and r26.get("space_usd") is not None:
            assert r26["tax_payroll_usd"] + r26["space_usd"] == T_now, (c, SEASON_NOW)
        if r27.get("tax_payroll_usd") is not None and r27.get("space_usd") is not None:
            assert r27["tax_payroll_usd"] + r27["space_usd"] == SPOTRAC_2027_BASIS_USD, (c, CLASS_YEAR)

    # projections
    vets = proj.get("vets") or []
    vets_by_club: dict = defaultdict(list)
    vets_by_key: dict = {}
    for v in vets:
        c = _canon(v.get("team"))
        if c:
            vets_by_club[c].append(v)
        if v.get("key"):
            vets_by_key[v["key"]] = v
    outlook = {}
    for row in proj.get("team_outlook") or []:
        c = _canon(row.get("team"))
        if c:
            outlook[c] = row
    dpw_proj = proj.get("dpw_usd")
    sp_census = (proj.get("accountability") or {}).get("salary_path") or {}
    prearb_min_season = max(LEAGUE_MIN_CURATED)
    prearb_min = LEAGUE_MIN_CURATED[prearb_min_season]

    # trade values (31 org values; non-club values dropped after the join)
    tv_by_club: dict = defaultdict(list)
    tv_by_key: dict = {}
    tv_orgs_in = set()
    for p in tv.get("players") or []:
        tv_orgs_in.add(p.get("org"))
        c = _canon(p.get("org"))
        if c in clubs:
            tv_by_club[c].append(p)
        if p.get("player_key"):
            tv_by_key[p["player_key"]] = p
    tv_dropped = sorted(o for o in tv_orgs_in if _canon(o) not in clubs)

    # arbitration board and history
    arb_rows_by_club: dict = defaultdict(list)
    for r in arb.get("rows") or []:
        c = _canon(r.get("t"))
        if c in clubs:
            arb_rows_by_club[c].append(r)
    hist_by_club: dict = defaultdict(list)
    hist_teams_in = set()
    for r in arb_hist.get("rows") or []:
        hist_teams_in.add(r[3])
        c = _canon(r[3])
        if c in clubs:
            hist_by_club[c].append(r)
    hist_fk = arb_hist.get("field_key") or {}

    # free agency
    members = fa_class.get("members") or []
    fits = fa_class.get("teamFits") or {}
    winters = fa_archive.get("winters") or []

    # farm capital
    org_summary = {}
    for o in ts.get("org_summary") or []:
        c = _canon(o.get("org"))
        if c:
            org_summary[c] = o
    pools = ts.get("mlb_draft_pools") or {}
    first6 = {int(k): v for k, v in (slot_curve.get("fitted_first6_by_bucket") or {}).items()}
    bucket_keys = sorted(first6)
    draft_results = storage.load_draft_results()
    slot_cov = {}
    for y in DRAFT_YEARS:
        ys = [r for r in draft_results if r.get("draft_year") == y]
        slot_cov[str(y)] = round(100.0 * sum(1 for r in ys if r.get("slot_usd")) / len(ys), 1) if ys else None
    lottery = storage.load_draft_lottery_odds(CLASS_YEAR)
    slot_orgs = ((org_tend.get("slot") or {}).get("orgs") or {})
    slot_league = ((org_tend.get("slot") or {}).get("league") or {})
    slot_window = (org_tend.get("windows") or {}).get("draft")
    ifa_classes = {int(c.get("year")): c for c in (ifa_ts.get("classes") or []) if c.get("year")}
    trajectory = _trade_trajectory()
    leaf_weights = dict(getattr(storage, "FARM_LEAF_WEIGHTS", {}).get("financial") or {})

    # deferrals (curated ledger, platform rate read off the engine)
    rate = float(fa_market._discount_rate())
    deferral_ledger = fa_market._deferral_ledger()
    deferral_unmatched = sum(1 for dk in deferral_ledger
                             if dk.rsplit(":", 1)[0] not in vets_by_key)

    # QO stamps
    events = storage.load_fa_events()
    qo_live = [e for e in events if e.get("event_type") == "qo_offered" and not e.get("invalidated")]

    # registry verdicts
    reg_rows = {m.get("model_id"): m for m in (registry.get("models") or [])}
    registry_verdicts = []
    for mid in REGISTRY_IDS:
        m = reg_rows.get(mid)
        registry_verdicts.append({
            "model_id": mid, "present": bool(m),
            "verdict": (m or {}).get("verdict"), "surface": (m or {}).get("surface"),
            "eval_artifact": (m or {}).get("eval_artifact"),
            "last_checked": (m or {}).get("last_checked"), "stale": (m or {}).get("stale")})
    verdict_of = {r["model_id"]: r["verdict"] for r in registry_verdicts}

    # ---- per-club blocks ---------------------------------------------------
    club_docs: dict = {}
    ratio_by_club: dict = {}
    contract_disagreements = 0

    for c in clubs:
        r26 = payroll.get((c, SEASON_NOW)) or {}
        r27 = payroll.get((c, CLASS_YEAR)) or {}
        meta = fa_meta.get("teams", {}).get(c) or {}
        out = outlook.get(c) or {}
        code = statsapi_code(c)
        assert code, f"no statsapi_code for {c}"

        # -- C1 payroll now ---------------------------------------------------
        tax26, tax27 = r26.get("tax_payroll_usd"), r27.get("tax_payroll_usd")
        if r27.get("payor_status_raw"):
            payor27 = {"value": r27["payor_status_raw"], "basis": PAYOR_BASIS_SPOTRAC}
        else:
            t26 = r26.get("payor_status_raw") or "Non-Tax"
            over26 = tax26 is not None and tax26 > T_now
            payor27 = {"value": PAYOR_NEXT.get(t26, "1st-Time") if over26 else "Non-Tax",
                       "basis": PAYOR_BASIS_DERIVED}
        split27 = [r27.get(k) for k in ("active_usd", "injured_usd", "retained_usd", "buried_usd")]
        payroll_block = {
            "s2026": {"total_payroll_usd": r26.get("total_payroll_usd"), "tax_payroll_usd": tax26,
                      "space_usd": r26.get("space_usd"), "payor_status_raw": r26.get("payor_status_raw"),
                      "est_tax_bill_usd": r26.get("est_tax_bill_usd") or None,
                      "split": None, "split_available": False},
            "s2027": {"total_payroll_usd": r27.get("total_payroll_usd"), "tax_payroll_usd": tax27,
                      "space_usd": r27.get("space_usd"), "payor_status_raw": r27.get("payor_status_raw"),
                      "est_tax_bill_usd": r27.get("est_tax_bill_usd") or None,
                      "split": split27 if any(v is not None for v in split27) else None,
                      "split_available": any(v is not None for v in split27),
                      "avg_age": r27.get("avg_age")},
            "payor_2027": payor27,
            "space_2027": {"spotrac_usd": r27.get("space_usd"), "spotrac_basis_usd": SPOTRAC_2027_BASIS_USD,
                           "platform_usd": (T_next - tax27) if tax27 is not None else None,
                           "platform_basis_usd": T_next},
            "history": {"status": "dark", "seasons": []},
            "cba_banner": True,
        }

        # -- C3 CBT position and tax -----------------------------------------
        cbt = {}
        for season, row, T, tier, tier_basis in (
                (SEASON_NOW, r26, T_now, r26.get("payor_status_raw"), PAYOR_BASIS_SPOTRAC_2026),
                (CLASS_YEAR, r27, T_next, payor27["value"], payor27["basis"])):
            tax = row.get("tax_payroll_usd")
            comp = computed_cbt_bill(tax, T, tier, rates, tiers)
            est = row.get("est_tax_bill_usd") or None
            blk = {"threshold_usd": T, "threshold_verify": thr[season]["verify_status"],
                   "carry_forward": bool(thr[season]["carry_forward"]),
                   "tax_payroll_usd": tax, "over_usd": comp["over_usd"], "bracket": comp["bracket"],
                   "computed_bill_usd": comp["bill_usd"], "spotrac_est_bill_usd": est,
                   "diff_usd": (comp["bill_usd"] - est) if (est is not None and comp["bill_usd"] is not None) else None,
                   "tier": tier, "tier_basis": tier_basis, "base_rate": comp["base_rate"]}
            if season == CLASS_YEAR:
                blk["spotrac_basis_usd"] = SPOTRAC_2027_BASIS_USD
                blk["over_spotrac_basis_usd"] = (tax - SPOTRAC_2027_BASIS_USD) if tax is not None else None
                blk["cba_banner"] = True
            cbt[str(season)] = blk
        n_consec = PAYOR_SEASONS.get(r26.get("payor_status_raw") or "Non-Tax", 0)
        cbt["clock"] = {"consecutive_payor_seasons_implied": n_consec, "tier_2026": r26.get("payor_status_raw") or "Non-Tax"}
        qo_tier_key = "cbt_payor" if (r26.get("payor_status_raw") or "Non-Tax") != "Non-Tax" else "other"
        qo_tax = fa_meta.get("qo_tax_by_payor_tier") or {}
        cbt["qo_pick_tax"] = {"club_tier": qo_tier_key, "club_usd": (qo_tax.get(qo_tier_key) or {}).get("total_usd")}

        # -- C4 commitments ------------------------------------------------------
        cvets = vets_by_club.get(c) or []
        priced = [v for v in cvets if v.get("salPath")]
        unpriced = [v for v in cvets if not v.get("salPath")]
        by_season = []
        for s in HORIZON:
            a = b = 0.0
            n_a = n_b = n_c = n_cut = 0
            for v in priced:
                for cell in v["salPath"]:
                    if cell[0] != s:
                        continue
                    tok, src, cliff = cell[4], cell[5], cell[6]
                    if cliff:
                        n_cut += 1
                    if src == "contract":
                        a += float(cell[1] or 0); n_a += 1
                    elif tok == "PRE-ARB":
                        n_c += 1
                    else:
                        b += float(cell[1] or 0); n_b += 1
            by_season.append([s, int(round(a)), n_a, int(round(b)), n_b, n_c * prearb_min, n_c, n_cut])
        base27 = by_season[0][1]
        horizon_season = next((row[0] for row in by_season if base27 and row[1] < 0.5 * base27), None)
        exp27 = [m for m in members if _canon(m.get("from")) == c]
        exp28 = [m for m in (fa_2028.get("members") or []) if _canon(m.get("from")) == c]
        exp29 = [m for m in (fa_2029.get("members") or []) if _canon(m.get("from")) == c]
        commitments = {
            "by_season": by_season,
            "n_vets": len(cvets), "n_priced": len(priced), "n_unpriced": len(unpriced),
            "threshold_2027_usd": T_next,
            "horizon_season": horizon_season,
            "expiring": {"2027": [len(exp27), _isum(exp27, "prevAav"), _isum(exp27, "projGuar")],
                         "2028": [len(exp28), _isum(exp28, "prevAav"), None],
                         "2029": [len(exp29), None, None]},
            "cba_banner": True,
        }

        # -- C5 contract ledger ----------------------------------------------------
        rows = []
        opts_all = []
        for v in sorted(priced, key=lambda x: -(x.get("aav") or 0)):
            opts = [[s, kind, None] for s, kind in (v.get("salOpt") or [])]
            co = (options_file.get("players") or {}).get(v.get("key")) or {}
            for o in co.get("club_options") or []:
                opts.append([o.get("year"), "club", o.get("price_usd")])
            if not v.get("salOpt"):
                for y in co.get("player_options") or []:
                    opts.append([y, "player", None])
            tvc = (tv_by_key.get(v.get("key")) or {}).get("contract") or {}
            if not opts:
                for y in tvc.get("player_opt_years") or []:
                    opts.append([y, "player", None])
                for y in tvc.get("club_opt_years") or []:
                    opts.append([y, "club", None])
            if (v.get("salSrc") in ("contract", "contract+arb") and v.get("thru")
                    and tvc.get("signed_through") and int(tvc["signed_through"]) != int(v["thru"])):
                contract_disagreements += 1
            opts = [list(o) for o in sorted({(o[0], o[1], o[2]) for o in opts if o[0]})]
            if opts:
                opts_all.append([v.get("name"), opts])
            rows.append([v.get("key"), v.get("name"), v.get("pos"), v.get("age"), v.get("salSrc"),
                         v.get("aav"), v.get("thru"), v.get("ctrlThru"), v.get("ctrlWhy"),
                         v.get("surNpv"), v.get("salPath"), opts])
        unpriced_rows = [[v.get("key"), v.get("name"), v.get("pos"), v.get("salSrc")]
                         for v in sorted(unpriced, key=lambda x: x.get("name") or "")]
        d_players = []
        d_sticker = d_npv = 0
        n_no_def = 0
        for dk, entry in deferral_ledger.items():
            pk = dk.rsplit(":", 1)[0]
            v = vets_by_key.get(pk)
            if not v or _canon(v.get("team")) != c:
                continue
            if not entry.get("deferred"):
                n_no_def += 1
                continue
            npv = fa_market.deferral_npv_usd(entry.get("schedule"), int(entry.get("sticker_usd") or 0))
            d_sticker += int(entry.get("sticker_usd") or 0)
            d_npv += int(npv["npv_usd"])
            d_players.append([v.get("name"), int(entry.get("sticker_usd") or 0), int(npv["npv_usd"]),
                              int(dk.rsplit(":", 1)[1]), entry.get("verify_status")])
        contracts = {
            "rows": rows, "n_priced": len(priced), "n_unpriced": len(unpriced), "unpriced": unpriced_rows,
            "options": opts_all,
            "deferrals": {"n": len(d_players), "n_no_deferral_assertions": n_no_def,
                          "sticker_usd": d_sticker, "npv_usd": d_npv, "players": d_players},
            "dead_money": {"status": "dark", "by_season": [], "buried_usd_2027": r27.get("buried_usd")},
            "retained": {"status": "dark", "by_season": [], "retained_usd_2027": r27.get("retained_usd")},
            "cba_banner": True,
        }

        # -- C5 right: arbitration exposure and the realized ledger -------------
        arows = arb_rows_by_club.get(c) or []
        flags = Counter()
        for r in arows:
            e = int(r.get("e") or 0)
            for bit in (1, 2, 4, 8, 16):
                if e & bit:
                    flags[str(bit)] += 1
        s27 = 0.0
        arb_list = []
        for r in sorted(arows, key=lambda x: -(x.get("tot") or 0)):
            l27 = next((t for t in (r.get("l") or []) if t[0] == CLASS_YEAR), None) or [None] * 5
            s27 += float(l27[1] or 0)
            arb_list.append([r.get("n"), r.get("m"), l27[4], l27[1], l27[2], l27[3], r.get("yl"),
                             (r.get("w") or [None])[0], r.get("c"), r.get("e")])
        hrows = hist_by_club.get(c) or []
        seasons_r = []
        for s in sorted({r[0] for r in hrows}):
            sr = [r for r in hrows if r[0] == s]
            seasons_r.append([s, len(sr), int(sum(r[5] or 0 for r in sr)), int(sum(r[6] or 0 for r in sr)),
                              int(sum(r[8] or 0 for r in sr)), int(sum(r[9] or 0 for r in sr)),
                              round(sum(float(r[10] or 0) for r in sr), 2)])
        arbitration = {
            "n": len(arows),
            "class_mix": {str(k): n for k, n in sorted(Counter(int(r.get("c") or 0) for r in arows).items())},
            "s2027_usd": int(round(s27)),
            "remaining_usd": int(sum(r.get("tot") or 0 for r in arows)),
            "war": round(sum(sum(float(w or 0) for w in (r.get("w") or [])) for r in arows), 2),
            "flags": dict(flags),
            "rows": arb_list,
            "cba_banner": True,
            "realized": {"seasons": seasons_r, "n": len(hrows),
                         "ou_mkt_total_usd": int(sum(r[8] or 0 for r in hrows)),
                         "ou_war_total_usd": int(sum(r[9] or 0 for r in hrows))},
        }

        # -- C6 surplus and cost per WAR ---------------------------------------
        mlb_by_src: dict = defaultdict(float)
        for v in cvets:
            if v.get("surNpv") is not None:
                mlb_by_src[v.get("salSrc") or "unknown"] += float(v["surNpv"]) / 1e6
        # The parts print at one decimal, so the leg is the sum of the PRINTED
        # parts: a reader adding the split back up lands on the figure shown.
        mlb_by_src_mm = {k: round(v, 1) for k, v in sorted(mlb_by_src.items())}
        mlb_mm = round(sum(mlb_by_src_mm.values()), 1)
        farm_mm = _r(((out.get("farm") or {}).get("farmSurplusMM")), 1)
        tvp = tv_by_club.get(c) or []
        surplus = {
            "mlb_mm": mlb_mm,
            "mlb_by_salsrc_mm": mlb_by_src_mm,
            "farm_mm": farm_mm,
            "total_mm": round(mlb_mm + (farm_mm or 0), 1),
            "unit": "$M",
            "trade_currency_mm": round(sum(float(p.get("trade_value_mm") or 0) for p in tvp), 1),
            "crunch": {
                "n_active": sum(1 for p in tvp if p.get("status") == "active"),
                "n_debuted": sum(1 for p in tvp if p.get("status") == "debuted"),
                "on_40_man": sum(1 for p in tvp if (p.get("crunch") or {}).get("on_40_man")),
                "rule5_exposed": sum(1 for p in tvp if (p.get("crunch") or {}).get("rule5_exposed")),
                "options_left_0": sum(1 for p in tvp if (p.get("crunch") or {}).get("options_left") == 0),
                "by_salary_basis": dict(Counter(p.get("salary_basis") or "none" for p in tvp)),
            },
            "trajectory": trajectory.get(c) or [],
        }
        wins27, war27 = out.get("wins"), out.get("war")
        ratio = (float(war27) / (float(tax27) / 1e6)) if (war27 and tax27) else None
        ratio_by_club[c] = ratio
        indexes = {
            "usd_per_win": int(round(float(tax27) / float(wins27))) if (tax27 and wins27) else None,
            "usd_per_war": int(round(float(tax27) / float(war27))) if (tax27 and war27) else None,
            "cost_plus": None,      # filled after the league pool is known
            "cost_ratio_war_per_mm": _r(ratio, 3),
            "orgsur_plus": (org_summary.get(c) or {}).get("financial_score"),
            "locked_pct": out.get("lockedPct"),
            "proj_wins_2027": wins27, "proj_war_2027": war27,
            "cba_banner": True,
        }

        # -- C7 farm capital ---------------------------------------------------
        o = org_summary.get(c) or {}
        tree = o.get("tree") or {}
        grades = o.get("grades") or {}
        leaves = {k: farm_leaf(tree, grades, k) for k in FIN_LEAVES}
        pool_by_year = {}
        for y in POOL_YEARS:
            tp = (pools.get(y) or {}).get("team_pools") or {}
            picks = [p for p in ((pools.get(y) or {}).get("pick_values") or []) if _canon(p.get("team")) == c]
            usd = None
            for k, v in tp.items():
                if _canon(k) == c:
                    usd = v
            pool_by_year[y] = [usd, "live" if usd is not None else ("not parsed" if y == "2021" else "absent"),
                               [[p.get("pick_overall"), p.get("slot_usd")] for p in picks] or None]
        paid_by_year = {}
        for y in DRAFT_YEARS:
            mine = [r for r in draft_results if r.get("draft_year") == y and _canon(r.get("team")) == c]
            slotted = [r for r in mine if r.get("slot_usd") and r.get("bonus_usd")]
            paid = int(sum(r.get("bonus_usd") or 0 for r in mine))
            pool_usd = (pool_by_year.get(str(y)) or [None])[0]
            paid_by_year[str(y)] = [
                len(mine), sum(1 for r in mine if r.get("signed")), sum(1 for r in mine if r.get("signed") == 0),
                paid, len(slotted), int(sum(r.get("slot_usd") or 0 for r in slotted)),
                int(sum(r.get("bonus_usd") or 0 for r in slotted)),
                int(sum((r.get("bonus_usd") or 0) - (r.get("slot_usd") or 0) for r in slotted)),
                slot_cov.get(str(y)), pool_usd, round(paid / pool_usd, 3) if (pool_usd and paid) else None]
        sc = slot_orgs.get(c) or {}
        slot_chips = {k: sc.get(k) for k in ("nSlotted", "overSlotShare", "r1UnderShare", "bonusHHI",
                                              "prepDollarShare", "zOver", "zBonusHHI", "zPrepDollar",
                                              "label", "spendLabel")}
        lot = next((r for r in lottery if _canon(r.get("team")) == c), None)
        pick_pos = lot.get("pick_pos") if lot else None
        bucket = next((b for b in bucket_keys if b >= pick_pos), None) if pick_pos else None
        ifa_by_class = {}
        for y in IFA_YEARS:
            cl = ifa_classes.get(y) or {}
            row = next((r for r in (cl.get("org_spending") or []) if _canon(r.get("org")) == c), None) or {}
            implied = [float(sg["bonus_usd"]) / (float(sg["pool_pct"]) / 100.0)
                       for sg in (cl.get("signings") or [])
                       if _canon(sg.get("org")) == c and sg.get("bonus_usd") and sg.get("pool_pct")]
            ifa_by_class[str(y)] = [row.get("total_usd"), row.get("signings"), row.get("top_bonus"),
                                    row.get("top_player"), row.get("pool_pct_sum"),
                                    int(statistics.median(implied)) if implied else None, len(implied)]
        fg = storage.load_farm_grade_history(c)
        farm = {
            "leaves": leaves,
            "orgsur_plus": {"financial_score": o.get("financial_score"),
                            "tree_fin_war_per_m_score_100": (tree.get("fin_war_per_m") or {}).get("score_100")},
            "financial_letter": grades.get("financial"),
            "financial_roi": o.get("financial_roi"),
            "method_surplus": o.get("_method_surplus"),
            "pools": pool_by_year,
            "draft_paid": paid_by_year,
            "slot_chips": slot_chips,
            "lottery": ([lot.get("pick_pos"), lot.get("odds_pct"), lot.get("odds_top6_pct"), lot.get("wins"),
                         lot.get("losses"), lot.get("snapshot_date"), lot.get("source")] if lot else None),
            "pick_war": [first6.get(bucket) if bucket else None, bucket, pick_pos],
            "ifa": ifa_by_class,
            "score_history": [[r.get("snapshot_date"), r.get("farm_score"), r.get("letter")] for r in fg],
            "farm_rank": (out.get("farm") or {}).get("farmRank"),
            "farm_score": (out.get("farm") or {}).get("farmScore"),
        }

        # -- C8 free agency ----------------------------------------------------
        outgoing = [[m.get("key"), m.get("name"), m.get("pos"), m.get("age"), m.get("status"), m.get("type"),
                     m.get("prevAav"), m.get("projYears"), m.get("projGuar"), m.get("projGuarP10"),
                     m.get("projGuarP90"), m.get("projAav"), m.get("surplus"), m.get("dealPlus"), m.get("verdict")]
                    for m in sorted(exp27, key=lambda x: -(x.get("projGuar") or 0))]
        fit_rows = []
        for f in fits.get(c) or []:
            m = members[f["i"]] if isinstance(f.get("i"), int) and f["i"] < len(members) else None
            if m:
                fit_rows.append([m.get("key"), m.get("name"), m.get("pos"), f.get("fit"), f.get("need"),
                                 f.get("window"), f.get("afford"), f.get("park"), f.get("behavior")])
        winter_rows = []
        realized_rows = []
        for w in winters:
            sg = w.get("signings") or []
            ins = [s for s in sg if _canon(s.get("to")) == c]
            outs = [s for s in sg if _canon(s.get("from")) == c]
            aavs = [s["aav"] for s in ins if s.get("aav")]
            winter_rows.append([w.get("year"), len(ins), _isum(ins, "guar"),
                                int(statistics.mean(aavs)) if aavs else None,
                                sum(1 for s in ins if s.get("qo")), len(outs), _isum(outs, "guar"),
                                w.get("dpw_usd"),
                                {str(k): n for k, n in sorted(Counter(s.get("years") for s in ins if s.get("years")).items())}])
            cov = [s for s in ins if s.get("warTd") is not None]
            realized_rows.append([w.get("year"), len(ins), len(cov),
                                  round(sum(float(s.get("warTd") or 0) for s in cov), 1),
                                  _isum(cov, "paidTd"), _isum(cov, "surplusTd"),
                                  int(sum((s.get("paidTd") or 0) + (s.get("surplusTd") or 0) for s in cov)),
                                  sum(1 for s in cov if s.get("done"))])
        fa = {
            "outgoing": outgoing, "fits": fit_rows,
            "expiring_2028": commitments["expiring"]["2028"], "expiring_2029": commitments["expiring"]["2029"],
            "winters": winter_rows,
            "priors": [meta.get("maxGuar"), meta.get("n100m"), meta.get("recentSpend")],
            "realized": {"status": "live", "by_winter": realized_rows},
            "cba_banner": True,
        }

        # -- C9 links -----------------------------------------------------------
        links = {
            "farm_tree": f"/prospx/#farm-org={c}",
            "org_tendencies": f"/prospx/#farm-org={c}&ftab=tendencies",
            "farm_board": "/prospx/#tab=farm", "ifa_board": "/prospx/#tab=ifa", "draft_board": "/prospx/#tab=draft",
            "roster_board": f"/projections/#team={c}",
            "team_outlook": "/projections/#view=teams",
            "fa_fits": f"/fa/#view=fits&team={c}",
            "fa_archive": f"/fa/#view=archive&winter={SEASON_NOW}",
            "arbitration_teams": "/arbitration/#teams",
            "trade_board": "/trademachine/#tab=tradeboard",
            "mlbstats_war": f"/mlbstats/#section=war&wview=teams&team={code}",
            "mlbstats_bullpen": f"/mlbstats/#section=bullpen&view=teams&team={code}",
            "betting_teams": "/betting/#section=teams",
            "fantasy_dynasty": f"/fantasy/#m=dynasty&team={c}",
            "management_club": f"/management/#section=clubs&team={c}",
            "franchise": f"/franchise/#team={c}" if (ROOT / "franchise" / "index.html").exists() else None,
        }

        club_docs[c] = {
            "club": c, "name": names.get(c), "statsapi_code": code,
            "payroll": payroll_block, "cbt": cbt, "commitments": commitments,
            "contracts": contracts, "arbitration": arbitration, "surplus": surplus,
            "indexes": indexes, "farm": farm, "fa": fa, "links": links,
        }

    # ---- Cost+ across the 30 clubs (AVERAGES never in the pool) ----------------
    vals = [ratio_by_club[c] for c in clubs if ratio_by_club.get(c) is not None]
    mu = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    for c in clubs:
        r = ratio_by_club.get(c)
        club_docs[c]["indexes"]["cost_plus"] = int(round(100 + 10 * (r - mu) / sd)) if (r is not None and sd) else None
    cp = [club_docs[c]["indexes"]["cost_plus"] for c in clubs if club_docs[c]["indexes"]["cost_plus"] is not None]
    assert abs(statistics.mean(cp) - 100) <= 0.5, statistics.mean(cp)
    assert abs(statistics.pstdev(cp) - 10) <= 0.5, statistics.pstdev(cp)

    # ---- league board ------------------------------------------------------------
    league_rows = []
    for c in clubs:
        d = club_docs[c]
        p26, p27 = d["payroll"]["s2026"], d["payroll"]["s2027"]
        league_rows.append({
            "club": c, "name": d["name"], "statsapi_code": d["statsapi_code"],
            "cbt_payroll_2026": p26["tax_payroll_usd"],
            "vs_threshold_2026": p26["space_usd"],
            "payor_2026": p26["payor_status_raw"],
            "est_tax_2026": p26["est_tax_bill_usd"],
            "committed_2027": p27["total_payroll_usd"],
            "space_2027_spotrac": d["payroll"]["space_2027"]["spotrac_usd"],
            "space_2027_platform": d["payroll"]["space_2027"]["platform_usd"],
            "proj_wins_2027": d["indexes"]["proj_wins_2027"],
            "usd_per_win": d["indexes"]["usd_per_win"],
            "cost_plus": d["indexes"]["cost_plus"],
            "usd_per_war": d["indexes"]["usd_per_war"],
            "locked_pct": d["indexes"]["locked_pct"],
            "controlled_surplus_mm": d["surplus"]["total_mm"],
            "arb_exposure_2027": d["arbitration"]["s2027_usd"],
            "orgsur_plus": d["indexes"]["orgsur_plus"],
            "farm_rank": d["farm"]["farm_rank"],
        })
    numeric_cols = ("cbt_payroll_2026", "vs_threshold_2026", "est_tax_2026", "committed_2027",
                    "space_2027_spotrac", "space_2027_platform", "proj_wins_2027", "usd_per_win",
                    "cost_plus", "usd_per_war", "locked_pct", "controlled_surplus_mm",
                    "arb_exposure_2027", "orgsur_plus")
    means = {}
    for k in numeric_cols:
        xs = [r[k] for r in league_rows if r.get(k) is not None]
        means[k] = round(statistics.mean(xs), 3 if k == "locked_pct" else 1) if xs else None
        means[k + "_n"] = len(xs)
    av27 = averages.get(CLASS_YEAR) or {}
    # The footer's two means are two fetches of one Spotrac page: stamp both and
    # state the gap's cause beneath them (footer_means_note).
    stamps = payroll_join.get("fetched_at") or {}
    av27_at = stamps.get(("AVERAGES", CLASS_YEAR))
    club27_at = sorted(s for s in (stamps.get((c, CLASS_YEAR)) for c in clubs) if s)
    means_at = club27_at[-1] if club27_at else None
    footer_gap = (means["committed_2027"] - av27["total_payroll_usd"]
                  if means.get("committed_2027") is not None and av27.get("total_payroll_usd") is not None
                  else None)
    tw = verdict_of.get("team_win_projections")
    league = {
        "rows": league_rows,
        "columns": [
            ["club", "Club", None, "canonical code; the StatsAPI code rides every row for the /mlbstats/ links"],
            ["cbt_payroll_2026", "CBT payroll 2026", "cbt_payroll", "Spotrac tax payroll, 2026"],
            ["vs_threshold_2026", "vs threshold", "cbt_bracket", f"space under the 2026 threshold ({T_now // 1_000_000}M, cba_rules); negative = over"],
            ["payor_2026", "Payor", "payor_tier", "Spotrac 2026 payor status"],
            ["est_tax_2026", "Est. tax 2026", "computed_cbt_bill", "Spotrac estimate; blank when the club is not a payor, never zero"],
            ["committed_2027", "Committed 2027", "payroll_allocations", "Spotrac total payroll allocations 2027"],
            ["space_2027_spotrac", "Space 2027", "cbt_payroll", f"Spotrac, {SPOTRAC_2027_BASIS_USD // 1_000_000}M basis; the platform {T_next // 1_000_000}M carry-forward figure sits in the tooltip and the two are never mixed"],
            ["proj_wins_2027", "Proj wins 2027", None, f"team_win_projections ({tw})"],
            ["usd_per_win", "$ per proj win", "cost_plus", f"Spotrac CBT payroll 2027 over team_win_projections 2027 wins ({tw}); plain dollars"],
            ["cost_plus", "Cost+", "cost_plus", f"100+10z of projected 2027 WAR per $M of 2027 CBT payroll across the 30 clubs; descriptive index, numerator {tw}"],
            ["usd_per_war", "$ per proj WAR", "cost_plus", "Spotrac CBT payroll 2027 over projected 2027 WAR; plain dollars, no ladder"],
            ["locked_pct", "Locked", "controlled_surplus", "share of 2027-31 core WAR under club control (a share of a projection)"],
            ["controlled_surplus_mm", "Controlled surplus", "controlled_surplus", "$M: MLB leg (surNpv) + farm leg (org active surplus), sums of means; plain"],
            ["arb_exposure_2027", "Arb exposure 2027", "arb_exposure", "upper bound, not a payroll forecast; arb_award provisional"],
            ["orgsur_plus", "OrgSur+", "sur_plus", "org_summary.financial_score; descriptive, unvalidated"],
            ["farm_rank", "Farm rank", None, "PROSPX farm rank (farm_grades provisional)"],
        ],
        "coloured": ["cost_plus", "orgsur_plus"],
        "averages_row": {"label": "Spotrac league average",
                         "committed_2027": av27.get("total_payroll_usd"), "active_2027": av27.get("active_usd"),
                         "retained_2027": av27.get("retained_usd"), "buried_2027": av27.get("buried_usd"),
                         "avg_age_2027": av27.get("avg_age"), "fetched_at": av27_at},
        "means": {"label": "Mean of the 30 club rows", "values": means,
                  "fetched_at": means_at, "fetched_at_min": club27_at[0] if club27_at else None},
        "pools": {"cost_plus": {"mean_ratio": _r(mu, 4), "sd_ratio": _r(sd, 4), "n": len(vals),
                                "mean_index": _r(statistics.mean(cp), 2), "sd_index": _r(statistics.pstdev(cp), 2),
                                "averages_excluded": True}},
        "quadrant": {"x": "cbt_payroll_2026", "y": "controlled_surplus_mm", "unit": "$M", "min_width_px": 700},
        "cba_banner": True,
    }

    # ---- rules tab -------------------------------------------------------------
    qo_comp = fa_cba.qo_compensation(date.today())
    arb_dpw = {str(k): v for k, v in (arb.get("dpw") or {}).items()}
    open_dpw = {str(k): v for k, v in (dpw_series.get("usd_per_war_by_winter") or {}).items()}
    arb_now, open_now = arb_dpw.get(str(SEASON_NOW)), open_dpw.get(str(SEASON_NOW))
    rules = {
        "thresholds": [{"season": s, "threshold_usd": thr[s]["threshold_usd"], "regime": thr[s]["regime"],
                        "carry_forward": bool(thr[s]["carry_forward"]), "verify_status": thr[s]["verify_status"]}
                       for s in range(2017, 2028)],
        "surcharge_tiers_usd": list(tiers),
        "rates": rates,
        "brackets": brackets,
        "qo_values": [{"class_year": r.get("class_year"), "winter": r.get("winter"), "value_usd": r.get("value_usd"),
                       "verify_status": r.get("verify_status")} for r in rules_doc.get("qo_values", [])],
        "qo_compensation": qo_comp,
        "qo_tax_by_payor_tier": fa_meta.get("qo_tax_by_payor_tier"),
        "league_minimum": [{"season": s, "usd": u} for s, u in sorted(LEAGUE_MIN_CURATED.items())],
        "dpw": {"open_market_by_winter": open_dpw, "open_market_method": dpw_series.get("method"),
                "arbitration_by_season": arb_dpw,
                "arbitration_discount_2026": _r(arb_now / open_now, 3) if (arb_now and open_now) else None,
                "projections_dpw_usd": dpw_proj,
                "breakdown_by_winter": {k: {kk: v.get(kk) for kk in ("n", "spend", "war", "dpw", "qo_share")}
                                        for k, v in ((dpw_series.get("breakdown") or {}).get("by_winter") or {}).items()}},
        "war_input_divergence": fa_meta.get("war_input_divergence"),
        "unverified_records": unverified,
        "cba_expiry": cba_expiry,
        "cba_banner": True,
    }

    # ---- copy: every sentence the page prints, once --------------------------------
    copy = {
        "masthead": ("Every dollar a club has on the books, from Spotrac and the platform's own "
                     "models, with what each dollar is projected to buy. No revenue, no valuations, "
                     "no TV money: nothing here says what a club earns."),
        "league_lede": ("Thirty clubs on two Spotrac bases and the platform's own prices. Only Cost+ "
                        "and OrgSur+ take a colour; every dollar cell prints plain, and the league "
                        "average row is a reference, never a club."),
        "footer_means_note": footer_means_note(av27_at, means_at, footer_gap, CLASS_YEAR),
        "club_foot": ("Descriptive ledger. No single projected payroll is served: contract dollars "
                      "on file, projected arbitration steps and rule minimums are three keys the page "
                      "never sums."),
        "cba_banner": banner_text,
        "cbt_computed_label": "computed from Spotrac tax payroll and the 2022 CBA schedule (cba_rules.json)",
        "cbt_under": "under the threshold",
        "cbt_clock_rule": ("the rate resets to first-time after one full season under the threshold; "
                           "rule text, not a forecast"),
        "cbt_verify_note": "every cba_rules record is curated-unverified; the 2027 threshold is explicitly unknown",
        "qo_recipient_note": ("which clubs receive revenue sharing is not sourceable here; that QO pick "
                              "tax tier is a league value only"),
        "payor_basis": {PAYOR_BASIS_SPOTRAC: f"Spotrac {CLASS_YEAR} page", PAYOR_BASIS_SPOTRAC_2026: f"Spotrac {SEASON_NOW} page",
                        PAYOR_BASIS_DERIVED: PAYOR_BASIS_DERIVED},
        "space_2027_spotrac_label": f"Spotrac, {SPOTRAC_2027_BASIS_USD // 1_000_000}M basis",
        "space_2027_platform_label": f"platform carry-forward, {T_next // 1_000_000}M",
        "split_2026_note": ("the 2026 Spotrac payroll page carries no active / injured / retained / "
                            "buried split; the strip is drawn for 2027 only"),
        "split_2027_label": "2027 allocations, Spotrac",
        "allocations_note": "CBT payroll is Spotrac's AAV basis; total payroll allocations are Spotrac's cash basis",
        "history_blocked_on": ("Payroll history is cached but not yet ingested (fa_team_payroll holds "
                               "2026-2027); the cache-only backfill of the 2016-2025 Spotrac pages has not run"),
        "commitments_bases": {"contract": "Contract dollars on file (Spotrac, never re-priced)",
                              "arb": "Arbitration steps, projected (arb_award provisional)",
                              "prearb": f"Pre-arb minimums by rule ({prearb_min:,} per PRE-ARB season, "
                                        f"salary_path.LEAGUE_MIN_CURATED[{prearb_min_season}] carried forward)"},
        "commitments_threshold_2027": f"platform carry-forward {T_next // 1_000_000}M (cba_rules, explicitly-unknown)",
        "commitments_threshold_later": "no threshold published",
        "commitments_not_summed": ("three labelled segments and a count of unpriced vets; no key sums them "
                                   "into a payroll, because that sum would be a forecast without a registry row"),
        "horizon_label": "half of today's contract dollars roll off by",
        "horizon_beyond": f"beyond {HORIZON[-1]}",
        "expiring_basis": ("fa_class members from this club; projected guarantees are sums of means and the "
                           "P10-P90 band is shown per player in the free agency block"),
        "holes": [
            f"every {CLASS_YEAR}+ arbitration step is a 2022 CBA carry-forward past the {cba_expiry} expiry, and no interval covers that",
            "the class token is inferred rather than read from published service time on most board rows, and class closure uses it twice, once for the rung and once for the horizon",
            "arb-2+ is a served null (an empirical step multiplier beat the model), and closure runs that same multiplier one to two rungs further",
            "window length is a property of Spotrac's grid depth, so two comparable players can carry two and four priced seasons for no baseball reason",
        ],
        "cell_basis": {"contract": "on file (Spotrac)", "arb_ladder": "Arbitration Predictor, provisional",
                       "class_closure": "class closure (inferred)"},
        "band_note": "band, not a calibrated interval",
        "options_note": ("Options on file (curated: salPath option stamps, contract_options.json and the "
                         "trade board's Spotrac years); Spotrac years_remaining omits them."),
        "deferral_rate_label": f"NPV at the platform {_pct_str(rate)} rate",
        "deferral_coverage": ("covered deals only: every guarantee of 200M or more has an entry (audited "
                              "into fa_gate2_eval.deferral_coverage); this is not a complete club deferral ledger"),
        "deferral_rate_note": (f"the platform discounts at {_pct_str(rate)}, which differs from the CBT "
                               "statutory rate, so these NPVs read lower than league-reported figures"),
        "dead_money_blocked_on": ("Spotrac's dataTable-dead rows carry no table_id on the read side yet "
                                  "(spotrac._parse_team_contract_table); the tag trails v1 so the priced "
                                  "contract set cannot widen by accident"),
        "dead_money_beside": ("Spotrac 2027 buried allocation, a different table with an overlapping "
                              "definition; never summed with dead money"),
        "retained_blocked_on": ("Spotrac's dataTable-retained rows carry no table_id on the read side yet; "
                                "retained obligations are never merged into the employing club's AAV"),
        "retained_cross_check": "Spotrac 2027 retained allocation, club total",
        "arb_upper_bound": "Upper bound, not a payroll forecast: non-tenders and extensions are absent",
        "arb_provisional": "provisional: the arb-1 model is gated, arb-2+ is a population multiplier",
        "arb_flag_key": (arb.get("field_key") or {}).get("e"),
        "arb_realized_title": "What arbitration cost, and what it bought",
        "arb_realized_copy": ("Realized value, not skill: what arbitration paid and what the seasons "
                              "returned. The counterfactual, what the club would have paid had it settled "
                              "or gone to a hearing differently, is not observed."),
        "ou_mkt": hist_fk.get("ou_mkt"), "ou_war": hist_fk.get("ou_war"),
        "never_combine": hist_fk.get("never_combine"),
        "surplus_basis": (f"MLB leg: MLB Projections surNpv at dpw {dpw_proj:,} ({CLASS_YEAR} ex-ante), 5-season "
                          f"horizon, {_pct_str(rate)} discount, usd converted to $M; farm leg: org_summary active "
                          "surplus ($M, prospect_surplus validated). Both legs in $M before the sum."),
        "surplus_no_tier": ("a club total sits above the player-row surplus ladder's top cut nearly "
                            "everywhere, so it prints plain"),
        "surplus_ev": "Sur+ sums are sums of expected values; quantiles are never summed",
        "trade_currency_basis": ("Trade Machine currency (trade_machine_surplus provisional); overlaps the "
                                 "MLB and farm legs by construction and is never added to them"),
        "trajectory_note": "since late June, no earlier history",
        "ratio_bases": (f"Spotrac CBT payroll {CLASS_YEAR} over team_win_projections {CLASS_YEAR} ({tw})"),
        "cost_plus_basis": "descriptive index: a ratio of two served numbers, not a model",
        "cost_plus_registry": "no registry row: Cost+ predicts nothing; a skill claim would need an eval first",
        "orgsur_chip": "descriptive, unvalidated",
        "farm_leaves": {k: {"basis": LEAF_VALUE[k][2], "weight": leaf_weights.get(k)} for k in FIN_LEAVES},
        "farm_letters_note": "letters come from org_summary.grades (rank across 30 orgs) and are never recomputed; a sparse leaf prints a dash",
        "pools_note": "2021 holds nine clubs (parser miss on the MLB.com article); 2027 pools are not published",
        "slot_coverage_basis": "share of the league's draft_results rows for that year carrying slot_usd",
        "slot_window": slot_window,
        "slot_league": slot_league,
        "pick_war_label": ("expected first-6 WAR of the 2027 first-round pick (draft_slot_curve, validated; "
                           "on the projected slot, not lottery-weighted)"),
        "pick_war_why": ("the lottery snapshot carries the odds of pick 1 and of a top-6 pick, not the full "
                         "odds vector, so the expectation is on the projected slot"),
        "pick_dollars": "pick dollars are not served: the only in-repo pick pricing is the QO tax method",
        "ifa_implied_basis": "implied from Spotrac pool percentages, not a published allocation",
        "ifa_history_blocked_on": ("IFA classes 2009-2018 are cached but run_monthly caps the range at 2021; "
                                   "extending it is a cache-only ingest deferred past v1, and 2019-2020 pages "
                                   "are not on disk"),
        "fits_note": "fa_team_fit is provisional: gate-3 MRR .165 against random .133",
        "implied_dpw_note": ("the club's implied dollars per WAR is not on the archive rows (projected WAR at "
                             "signing is not stored), so only the league rate prints"),
        "priors_basis": "from fa_fit.behavior_priors (fa_meta.teams)",
        "realized_title": "Contract value delivered (realized, elapsed seasons only)",
        "realized_method": "level_proration_backcast_dpw_v1",
        "realized_sentence": ("This is what the contracts returned, not how well the club chose them. "
                              "The counterfactual, what the same dollars would have bought elsewhere "
                              "that winter, is not observed, so no club is ranked by it."),
        "realized_coverage": ("covered signings carry the realized block; the current winter carries none "
                              "because no season has elapsed"),
        "realized_not_skill": ("Realized value, not skill: what happened after the money was spent, "
                               "with the counterfactual unobserved."),
        "qo_none": "no live QO stamps",
        "no_payroll_line": ("A single projected payroll is not served: it would need registry row "
                            "club_payroll_path and the 2016-2025 payroll history as labels."),
        "load_error": "The Club Ledger could not be loaded.",
        "arb_dpw_basis": (f"arbitration dollars per WAR {SEASON_NOW} (arbitration.json dpw) over the "
                          f"open-market rate for winter {SEASON_NOW} (fa_dpw_series)"),
        "projections_dpw_basis": f"mlb_projections dpw_usd, {CLASS_YEAR} ex-ante, the surplus pricing rate",
        "league_minimum_note": f"salary_path.LEAGUE_MIN_CURATED; seasons past {prearb_min_season} carry the last value forward by rule",
    }

    field_key = {
        "commitments.by_season": "[season, contract_usd, n_contract, arb_projected_usd, n_arb, prearb_rule_usd, n_prearb, n_cliff]; n_unpriced is on the block; NO SUM of the three",
        "commitments.expiring": "[n, prev_aav_usd, proj_guar_usd]",
        "contracts.rows": "[key, name, pos, age, salSrc, aav_usd, signed_thru, ctrl_thru, ctrl_why, sur_npv_usd, salPath, options]; salPath cell [season, proj_usd, lo_usd, hi_usd, token, source, cliff]; option [season, holder, price_usd]",
        "contracts.unpriced": "[key, name, pos, salSrc]",
        "contracts.deferrals.players": "[name, sticker_usd, npv_usd, class_year, verify_status]",
        "payroll.s2027.split": "[active_usd, injured_usd, retained_usd, buried_usd]",
        "arbitration.rows": "[name, mlbam, token_2027, proj_2027_usd, lo_usd, hi_usd, years_left, war_2027, class, flags]",
        "arbitration.realized.seasons": "[season, n, actual_usd, ours_usd, ou_mkt_usd, ou_war_usd, war]; ou_mkt and ou_war are never combined",
        "surplus.trajectory": "[snapshot_date, trade_value_mm sum]",
        "farm.pools": "year -> [pool_usd, status, picks [[pick_overall, slot_usd]]]",
        "farm.draft_paid": "year -> [n_picks, n_signed, n_unsigned, paid_usd, n_slotted, slot_usd_on_slotted, paid_usd_on_slotted, over_slot_usd, slot_coverage_pct, pool_usd, pool_used]",
        "farm.lottery": "[pick_pos, odds_pct, odds_top6_pct, wins, losses, snapshot_date, source]",
        "farm.pick_war": "[expected_first6_war, bucket_upper_bound, pick_pos]",
        "farm.ifa": "class year -> [total_usd, signings, top_bonus, top_player, pool_pct_sum, implied_pool_usd, implied_n]",
        "farm.score_history": "[snapshot_date, farm_score, letter]",
        "fa.outgoing": "[key, name, pos, age, status, type, prev_aav_usd, proj_years, proj_guar_usd, proj_guar_p10_usd, proj_guar_p90_usd, proj_aav_usd, surplus_usd, deal_plus, verdict]",
        "fa.fits": "[key, name, pos, fit, need, window, afford, park, behavior]",
        "fa.winters": "[winter, n_in, spend_in_usd, aav_mean_usd, qo_in, n_out, guar_out_usd, league_dpw_usd, years_mix]",
        "fa.priors": "[maxGuar_usd, n100m, recentSpend_usd]",
        "fa.realized.by_winter": "[winter, n, n_covered, war_td, paid_td_usd, surplus_td_usd, realized_usd, n_complete]",
    }

    sources = [
        ["S1", "fa_meta.json teams / cba / qo_tax_by_payor_tier / dpw_series", "fa_export", "daily"],
        ["S2", "storage.fa_team_payroll (Spotrac tax and payroll pages)", "fa_pipeline.refresh_payroll", "monthly"],
        ["S5", "mlb_projections.json vets / team_outlook / accountability.salary_path", "proj_export", "nightly"],
        ["S6", "trade_values.json players", "bayes_trade_value", "nightly"],
        ["S7", "storage.trade_value_history", "bayes_trade_value snapshot", "nightly"],
        ["S8", "arbitration.json", "arb_export", "monthly"],
        ["S9", "arb_history.json", "arb_export", "monthly"],
        ["S10", "fa_class.json / fa_class_2028 / fa_class_2029", "fa_export", "daily"],
        ["S11", "fa_archive.json (realized ledger included)", "fa_pipeline.backfill_historical -> fa_export", "daily"],
        ["S12", "cba_rules.json (via fa_cba)", "frozen curation", "frozen"],
        ["S13", "deferrals.json / contract_options.json", "frozen curation", "frozen"],
        ["S14", "timeseries.json org_summary / mlb_draft_pools", "storage.export_timeseries_json", "nightly"],
        ["S15", "storage.draft_results / draft_lottery_odds", "draft_bonus / Spotrac draft page", "monthly"],
        ["S16", "draft_slot_curve.json", "frozen", "frozen"],
        ["S17", "ifa_timeseries.json", "ifa_export", "nightly"],
        ["S18", "org_tendencies.json slot", "org_tendencies", "nightly"],
        ["S19", "storage.farm_grade_history", "storage snapshot", "nightly"],
        ["S20", "fa_dpw_series.json", "fa_export", "daily"],
        ["S21", "model_registry.json", "hand-committed", "frozen"],
        ["S22", "storage.fa_events (qo_offered)", "fa_pipeline", "daily"],
    ]
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season_now": SEASON_NOW, "class_year": CLASS_YEAR, "horizon": list(HORIZON),
        "cba": {"threshold_by_season": {str(s): thr[s]["threshold_usd"] for s in range(2017, 2028)},
                "threshold_2027_basis": "carry_forward",
                "spotrac_2027_basis_usd": SPOTRAC_2027_BASIS_USD,
                "banner_text": banner_text, "expiry": cba_expiry,
                "rates": rates, "surcharge_tiers_usd": list(tiers), "brackets": brackets,
                "unverified_records": len(unverified)},
        "copy": copy,
        "field_key": field_key,
        "league": league,
        "clubs": club_docs,
        "rules": rules,
        "sections": {
            "league": {"live": True}, "club": {"live": True}, "rules": {"live": True}, "method": {"live": True},
            "fa_realized": {"live": True, "note": "realized value, not skill"},
            "payroll_history": {"live": False, "blocked_on": copy["history_blocked_on"]},
            "dead_money": {"live": False, "blocked_on": copy["dead_money_blocked_on"]},
            "retained": {"live": False, "blocked_on": copy["retained_blocked_on"]},
            "ifa_history": {"live": False, "blocked_on": copy["ifa_history_blocked_on"]},
            "draft_pool_2021": {"live": False, "blocked_on": "the 2021 MLB.com pool article parsed nine clubs; the cell reads not parsed"},
            "qo_pending": {"live": bool(qo_live), "n_live": len(qo_live),
                           "note": (copy["qo_none"] if not qo_live else f"{len(qo_live)} live QO stamps"),
                           "blocked_on": (None if qo_live else
                                          "every qo_offered event on file is invalidated until a stamp "
                                          "inside the Oct-Jan window exists; the block never promises rows")},
            "single_payroll_line": {"live": False, "decided": "not served",
                                    "blocked_on": ("needs registry row club_payroll_path and the 2016-2025 "
                                                   "payroll history as labels for a backtest")},
            "quadrant": {"live": True, "min_width_px": 700},
        },
        "method": {"sources": sources,
                   "source_key": ["id", "artifact", "writer", "cadence"],
                   "inputs_generated_at": {"fa_meta": fa_meta.get("generated_at"),
                                           "mlb_projections": proj.get("generated_at"),
                                           "trade_values": tv.get("generated_at"),
                                           "arbitration": arb.get("generated_at"),
                                           "arb_history": arb_hist.get("generated_at"),
                                           "fa_class": fa_class.get("generated_at"),
                                           "fa_archive": fa_archive.get("generated_at"),
                                           "timeseries": ts.get("generated_at"),
                                           "ifa_timeseries": ifa_ts.get("generated_at"),
                                           "org_tendencies": org_tend.get("generated_at"),
                                           "draft_slot_curve": slot_curve.get("generated_at")}},
        "accountability": {
            "registry_verdicts": registry_verdicts,
            "registry_checked_at": registry.get("checked_at"),
            "salary_path_census": sp_census,
            "contract_disagreements": contract_disagreements,
            "contract_disagreement_rule": "S5 signed-through against the trade board's Spotrac years; the S5 value wins",
            "contract_set_sha": None,
            "contract_set_note": ("the dead-money table_id tag has not landed, so the Spotrac team pages "
                                  "were not read by this export and no contract-set hash is recorded"),
            "n_clubs": len(clubs), "averages_excluded": True,
            "org_join": {"fa_meta": [len(fa_meta.get("teams") or {}), len(clubs)],
                         "fa_team_payroll": [payroll_join["rows_in"], payroll_join["club_rows"]],
                         "trade_values": [len(tv_orgs_in), len([o for o in tv_orgs_in if _canon(o) in clubs])],
                         "trade_values_dropped": tv_dropped,
                         "arb_history": [len(hist_teams_in), len({_canon(t) for t in hist_teams_in if _canon(t) in clubs})]},
            "deferral_entries_unmatched": deferral_unmatched,
            "discount_rate": rate,
            "prearb_min_usd": prearb_min,
            "payor_2027_basis_census": dict(Counter(d["payroll"]["payor_2027"]["basis"] for d in club_docs.values())),
        },
        "what_this_page_does_not_claim": [
            "revenue: no source in the tree carries club revenue or operating income",
            "franchise valuation: no source carries a valuation",
            "attendance money: one season of home-game attendance exists in the game feeds and no history; no gate receipts",
            "ticket prices: not sourced",
            "local or national TV / RSN money: not sourced",
            "central-fund distributions: not sourced",
            "revenue-sharing payer or recipient status: which clubs receive revenue sharing is not sourceable; the QO tax tier for recipients prints as a league value only",
            "minor-league payroll: not sourced",
            "front-office and coaching salaries: not sourced",
            "stadium debt: not sourced",
            "actual CBT bills paid: only Spotrac's estimate for payors and the schedule computed here",
            f"{CLASS_YEAR}+ bonus pools and IFA pool allocations as published: pools past {POOL_YEARS[-1]} are not on disk and IFA pools are implied from Spotrac percentages",
            "service-time ground truth: the class token is inferred on most arbitration rows",
            "a single projected payroll: three labelled segments only",
        ],
    }
    _assert_document(doc)
    return doc


# --------------------------------------------------------------------------
# document-level assertions (run before every write)
# --------------------------------------------------------------------------

def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, k
            yield from _walk_keys(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def _assert_document(doc: dict) -> None:
    assert len(doc["clubs"]) == 30 and len(doc["league"]["rows"]) == 30
    for c, d in doc["clubs"].items():
        assert d["statsapi_code"], c
        sp = d["payroll"]["space_2027"]
        assert sp["spotrac_basis_usd"] == SPOTRAC_2027_BASIS_USD
        assert sp["platform_basis_usd"] == doc["cba"]["threshold_by_season"]["2027"]
        assert d["surplus"]["unit"] == "$M"
        for blk in ("payroll", "commitments", "contracts", "arbitration", "fa", "indexes"):
            assert d[blk].get("cba_banner") is True, (c, blk)
        assert d["cbt"]["2027"].get("cba_banner") is True
    for path, k in _walk_keys(doc):
        ks = str(k).lower()
        assert ks not in FORBIDDEN_KEYS, path
        for frag in FORBIDDEN_KEY_FRAGMENTS:
            assert frag not in ks, path
        assert not (("ou_mkt" in ks and "ou_war" in ks) or ks in ("ou_total", "ou_combined", "ou_sum")), path


def main(argv=None) -> int:
    doc = build()
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(ROOT)} ({n / 1e3:.0f} KB)")
    rows = doc["league"]["rows"]
    print(f"  clubs: {len(doc['clubs'])}; contract rows priced: "
          f"{sum(d['contracts']['n_priced'] for d in doc['clubs'].values())}")
    print(f"  Cost+ pool: {doc['league']['pools']['cost_plus']}")
    top = max(rows, key=lambda r: r["cost_plus"] or 0)
    print(f"  highest Cost+: {top['club']} {top['cost_plus']}")
    print(f"  live sections: {sorted(k for k, v in doc['sections'].items() if v.get('live'))}")
    print(f"  dark: {sorted(k for k, v in doc['sections'].items() if not v.get('live'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
