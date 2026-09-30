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

#: The Cost+ family's denominator gap, said on every column that divides by it.
NO_ARB_IN_DENOM = ("the payroll carries no arbitration or pre-arbitration salaries, the projected roster "
                   "in the numerator does")

#: fa_class option types whose 2027 year is not guaranteed, so the tax floor
#: census leaves those contract rows out of the guaranteed AAV.
TAX_FLOOR_NOT_GUARANTEED = ("club_option", "mutual_option")

#: Registry rows whose verdicts the Method tab quotes beside the numbers. The
#: last three landed with the depth pass (D5, 2026-09-24): the salary path the
#: contract strips read, the prospect rows of the projections board, and the
#: provisional eFV prior the farm rows can inherit.
REGISTRY_IDS = ("arb_award", "team_win_projections", "prospect_surplus", "fa_market",
                "fa_projection_marcel", "fa_team_fit", "fa_dpw_series", "draft_slot_curve",
                "org_sur_plus", "dvm_plus_dollar", "farm_grades", "trade_machine_surplus",
                "ifa_step_prior",
                "control_window_salary_path", "mlb_projections_prospects", "xfv_provisional_prior")

# --------------------------------------------------------------------------
# D5 depth pass (2026-09-24): one board plus thirty lazy per-club files.
# The six per-club row arrays (prospects, graduates, arbitration ladders,
# realized arbitration rows, contract paths, debuted trade rows) measured about
# 1.8 MB over 30 clubs against the 1,000,000-byte line, so they live in
# data/ledger_clubs/CODE.json and the board keeps a preview of PREVIEW_N rows
# per block plus the reconciliation blocks that tie every row layer to the v1
# roll-up it sits under.
# --------------------------------------------------------------------------

SHARD_DIRNAME = "ledger_clubs"
SHARD_DIR = DATA / SHARD_DIRNAME
SHARD_CAP_BYTES = 160_000
#: Preview rows per block on the board; drops to PREVIEW_N_SMALL when the
#: written board would pass PREVIEW_GUARD_BYTES (the guard prints on the
#: Method tab as shards.preview_n).
PREVIEW_N = 10
PREVIEW_N_SMALL = 5
PREVIEW_GUARD_BYTES = 950_000
BOARD_CAP_BYTES = 1_000_000

#: Farm reconciliation (owner decision D3): the leaf is a net figure written by
#: storage.export_timeseries_json at one point of the nightly and the rows come
#: from trade_values written later the same night, so the identity holds to a
#: tolerance, never asserted exact.
FARM_EXACT_MM = 0.05
FARM_TOL_PCT = 0.02
FARM_TOL_FLOOR_MM = 5.0
#: Contract identities (5.3): the strip is published to 0.1 $M per cell and the
#: served NPV discounts the unrounded figures; surRos is published rounded and
#: surTotal was built from the raw float.
NPV_TOL_USD = 300_000
SURTOTAL_TOL_USD = 50_000
TV_MATCH_TOL_MM = 0.06

#: Method buckets the PROSPX org summary keeps (storage: every other method
#: aggregates outside the three, and so do these rows).
METHOD_BUCKETS = ("draft", "international_fa", "trade")

#: The key walker's rule for the new blocks (R1 / L14). Under any dict key in
#: AGGREGATE_KEYS a key whose underscore tokens name a band end (lo, hi, p10,
#: p90) is refused, and a "rows" sum in $M must be one of SUM_KEYS_ALLOWED: a
#: seventh sum fails until it is named here.
AGGREGATE_KEYS = ("reconciliation", "summary", "method", "paths_summary", "by_season", "footer")
BAND_TOKENS = ("lo", "hi", "p10", "p90")
SUM_KEYS_ALLOWED = ("rows_gross_mm", "rows_cost_mm", "rows_net_mm",
                    "trade_rows_active_mm", "trade_rows_debuted_mm", "mlb_rows_mm")

#: Column names in row order for every row array the depth pass serves. The
#: renderer indexes through these (colIdx), never through the prose legend.
COLUMNS = {
    "farm.prospects": ["key", "name", "pos", "age", "consensus_fv", "efv", "acq_method", "acq_year",
                       "pick_overall", "bonus_usd", "slot_usd", "cur_method", "cur_year", "surplus_mm",
                       "band_lo_mm", "band_hi_mm", "p_bust", "net_mm", "dollar_dvm_plus", "eta_year",
                       "service_phase", "on_40_man", "options_left", "rule5_exposed", "tv_grade",
                       "cons_surplus_mm", "cons_lo_mm", "cons_hi_mm"],
    "farm.graduates": ["key", "name", "pos", "debut_date", "acq_method", "acq_year", "bonus_usd",
                       "dv_trade_value_mm", "dv_realized_mm", "control_thru", "control_why",
                       "tv_trade_value_mm", "tv_surplus_source", "service_phase", "career_war",
                       "wag_label", "in_vets"],
    "farm.picks": ["pick_overall", "round_label", "player_name", "slot_usd", "bonus_usd", "signed",
                   "over_slot_usd", "prospect_key"],
    "farm.picks_summary": ["n_picks", "n_signed", "n_on_tracker", "n_graduated", "n_not_tracked",
                           "n_unsigned_on_tracker"],
    "farm.method": ["n", "n_with_bonus", "gross_mm", "cost_mm", "net_mm", "net_per_cost_ratio",
                    "served_net_mm", "served_cost_mm", "served_count", "served_per_fv_pt_mm"],
    "farm.trajectory_active": ["snapshot_date", "active_trade_value_mm"],
    "farm.prospect_trajectory": ["snapshot_date", "trade_value_mm"],
    "arbitration.ladders": ["name", "mlbam", "sv", "svy", "class", "flags", "years_left", "ladder", "war",
                            "tot_usd", "in_vets", "has_salpath"],
    "arbitration.by_season": ["season", "arb_rung_usd", "n_arb_rungs", "prearb_rung_usd",
                              "n_prearb_rungs", "n_null_rungs"],
    "arbitration.realized.rows": ["season", "mlbam", "name", "arb_year", "actual_usd", "ours_usd",
                                  "swartz_usd", "ou_mkt_usd", "ou_war_usd", "war", "flags"],
    "contracts.paths": ["key", "war", "war_p10", "war_p90", "sur_mm", "sur_npv_usd", "sur_ros_mm",
                        "sur_total_usd", "tv_mm", "tv_lo_mm", "tv_hi_mm", "tv_grade", "surplus_source",
                        "band_basis", "salary_basis", "control_thru", "control_why",
                        "remaining_control_years", "player_opt_years", "club_opt_years", "reanchored",
                        "npv_check_usd"],
    "surplus.rows_debuted": ["key", "name", "pos", "tv_mm", "tv_lo_mm", "tv_hi_mm", "tv_tier", "tv_grade",
                             "surplus_source", "salary_basis", "control_thru", "control_why",
                             "in_contract_rows"],
}
SHARD_ROW_KEYS = ("farm.prospects", "farm.graduates", "arbitration.ladders",
                  "arbitration.realized.rows", "contracts.paths", "surplus.rows_debuted")

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


def _mlbam(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def graduate_vet(g: dict, vets_by_key: dict, vets_by_mlbam: dict):
    """The projections vet row for a debuts_lite graduate, joined on the HUMAN.

    A player_key is a slug and a slug can name two humans: the CLE graduate
    jose_ramirez is a 2004-born arm (802064) while the projections vet under
    that slug is the 34-year-old third baseman (608070). A graduate with an
    mlbam id joins on it and nothing else; only a graduate without one falls
    back to the slug."""
    m = _mlbam(g.get("mlbam_id"))
    if m is not None:
        return vets_by_mlbam.get(m)
    return vets_by_key.get(g.get("player_key"))


def trade_row_projection_key(p: dict):
    """The mlb_projections key of a trade_values row's human: the row's
    `proj_key` where bayes_trade_value stamped one (its own slug names a
    different human there, or none), else its player_key."""
    return p["proj_key"] if "proj_key" in p else p.get("player_key")


def _pct_str(rate: float) -> str:
    return f"{rate * 100:g} pct"


def _isum(rows, key):
    return int(sum(float(r.get(key) or 0) for r in rows))


# --------------------------------------------------------------------------
# the CBT computation (rule application, unit-tested against cba_rules.json)
# --------------------------------------------------------------------------

def _spearman(xs: list, ys: list) -> float | None:
    """Spearman rank correlation with average ranks for ties; None under 3 pairs."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out
    if len(xs) < 3:
        return None
    return statistics.correlation(ranks(xs), ranks(ys))


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


def _trade_trajectory_active() -> dict:
    """club -> [[snapshot_date, sum trade_value_mm over that snapshot's ACTIVE rows]].

    Each snapshot's own actives, on that snapshot's own status, gross of bonuses:
    so this is not the leaf's series and a graduation moves it (L15). The copy
    says what the query does."""
    import storage
    out: dict = defaultdict(list)
    try:
        with storage.connect() as con:
            rows = con.execute(
                "SELECT org, snapshot_date, SUM(trade_value_mm) FROM trade_value_history "
                "WHERE org IS NOT NULL AND status = 'active' GROUP BY org, snapshot_date "
                "ORDER BY snapshot_date"
            ).fetchall()
    except Exception as exc:                      # noqa: BLE001
        log.warning("ledger_export: trade_value_history (active) unavailable: %s", exc)
        return {}
    for org, d, mm in rows:
        c = _canon(org)
        if c and mm is not None:
            out[c].append([d, round(float(mm), 1)])
    return dict(out)


def _player_trajectories(keys) -> dict:
    """player_key -> [[snapshot_date, trade_value_mm]] for the preview keys only
    (owner decision D6). One query with an IN list; 300 keys over 64 snapshots."""
    import storage
    keys = sorted({k for k in keys if k})
    if not keys:
        return {}
    out: dict = defaultdict(list)
    try:
        with storage.connect() as con:
            for i in range(0, len(keys), 400):
                chunk = keys[i:i + 400]
                rows = con.execute(
                    "SELECT player_key, snapshot_date, trade_value_mm FROM trade_value_history "
                    f"WHERE player_key IN ({','.join('?' * len(chunk))}) ORDER BY snapshot_date",
                    chunk).fetchall()
                for k, d, mm in rows:
                    if mm is not None:
                        out[k].append([d, round(float(mm), 1)])
    except Exception as exc:                      # noqa: BLE001
        log.warning("ledger_export: per-player trade_value_history unavailable: %s", exc)
        return {}
    return dict(out)


def _xfv_meta() -> dict:
    """xfv.json's `meta` header only. The file is 9 MB and the farm rows never
    read its player rows (trade_values carries the same surplus, pinned equal by
    test_the_prospect_row_surplus_equals_the_trade_board_and_the_efv_export); the
    header is the first key, so a raw_decode from its opening brace reads the
    calibration stamp without parsing the rest."""
    p = DATA / "xfv.json"
    try:
        with p.open("r", encoding="utf-8") as fh:
            head = fh.read(262_144)
    except OSError as exc:
        log.warning("ledger_export: xfv.json unreadable: %s", exc)
        return {}
    i = head.find('"meta"')
    if i < 0:
        return {}
    j = head.find("{", i + 6)
    if j < 0:
        return {}
    try:
        meta, _end = json.JSONDecoder().raw_decode(head, j)
    except ValueError as exc:
        log.warning("ledger_export: xfv.json meta header did not decode: %s", exc)
        return {}
    return meta if isinstance(meta, dict) else {}


def _file_stamp(name: str):
    """ISO stamp of a data file's mtime, for an artifact that carries no
    generated_at of its own (debuts_lite.json is a bare list)."""
    try:
        ts = (DATA / name).stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def arbitration_link(club: str, arbitration_js: str | None = None) -> str:
    """Feature-detected at build time (owner decision D8): the Team View of
    /arbitration/ narrows to a club only when assets/arbitration.js carries
    TEAM_NARROW_RE; otherwise the v1 unnarrowed link. If that lane's change is
    ever reverted the ledger degrades without an edit, and no key is added to
    the arbitration grammar by this file."""
    if arbitration_js is None:
        try:
            arbitration_js = (ROOT / "assets" / "arbitration.js").read_text(encoding="utf-8")
        except OSError:
            arbitration_js = ""
    if "TEAM_NARROW_RE" in arbitration_js:
        return f"/arbitration/#teams&team={club}"
    return "/arbitration/#teams"


def farm_reconcile_status(leaf_mm, rows_net_mm) -> tuple:
    """(gap_mm, tolerance_mm, status) for the farm roll-up against its rows:
    exact under FARM_EXACT_MM, vintage_drift inside max(2 pct of the leaf,
    5 $M), broken beyond it. Both figures always print; neither is corrected."""
    if leaf_mm is None or rows_net_mm is None:
        return None, None, "broken"
    gap = round(float(leaf_mm) - float(rows_net_mm), 2)
    tol = round(max(FARM_TOL_PCT * abs(float(leaf_mm)), FARM_TOL_FLOOR_MM), 2)
    if abs(gap) < FARM_EXACT_MM:
        return gap, tol, "exact"
    if abs(gap) <= tol:
        return gap, tol, "vintage_drift"
    return gap, tol, "broken"


def npv_of_strip(sur_mm, rate: float) -> int:
    """NPV in usd of a published per-season surplus strip ($M, t = 0 at the
    class year) at the platform rate: the identity the contract expander prints
    beside the served surNpv. A None cell is a season with no salary and enters
    no sum."""
    total = 0.0
    for t, s in enumerate(sur_mm or []):
        if s is None:
            continue
        total += float(s) * 1e6 / ((1.0 + rate) ** t)
    return int(round(total))


def _shard_bytes(shard: dict) -> bytes:
    """The one serialization of a shard, shared by the index on the board and
    the writer, so bytes and sha256_16 on the board equal the file on disk."""
    return json.dumps(shard, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sha16(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()[:16]


def _doc_bytes(doc: dict) -> int:
    return len(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------

def build_all() -> tuple:
    """(doc, shard_docs): the board and the thirty per-club row files, built
    together and never written here (tests call this under tmp_path)."""
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
    # D5 reads: the debuted rows (S24, a bare list), the eFV export's meta
    # header only (S26), the a6 Swartz arm to quote (S25), and the arbitration
    # page's source for the link feature detection (D8).
    debuts_lite = _j("debuts_lite.json") or []
    if not isinstance(debuts_lite, list):
        debuts_lite = debuts_lite.get("players") or debuts_lite.get("rows") or []
    xfv_meta = _xfv_meta()
    arb_eval = _j("arbitration_eval.json") or {}
    try:
        arbitration_js = (ROOT / "assets" / "arbitration.js").read_text(encoding="utf-8")
    except OSError:
        arbitration_js = ""
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

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
    # The level the farm leg's prospect dollars were priced at (the timeseries
    # stamp, VAL_1): equal to dpw_proj when one level prices both legs.
    farm_level = (ts.get("calibration") or {}).get("dpw_level_usd")
    # The contract tail (proj_export.PRICE_CONTRACT_TAIL): surNpv prices a
    # guarantee that runs past the horizon through its last season.
    tail_on = bool((((proj.get("accountability") or {}).get("salary_path") or {})
                    .get("contract_tail") or {}).get("enabled"))
    sp_census = (proj.get("accountability") or {}).get("salary_path") or {}
    prearb_min_season = max(LEAGUE_MIN_CURATED)
    prearb_min = LEAGUE_MIN_CURATED[prearb_min_season]
    vets_by_mlbam: dict = {}
    for v in vets:
        if v.get("mlbam") is not None:
            vets_by_mlbam[int(v["mlbam"])] = v

    # trade values (31 org values; non-club values dropped after the join)
    tv_by_club: dict = defaultdict(list)
    tv_by_key: dict = {}
    # The same rows keyed by the PROJECTION key of their human, for every join
    # that starts from a projections vet (contract options, contract paths).
    # Keying those on player_key handed the LAD veteran max_muncy the ATH
    # infielder's board row.
    tv_by_proj_key: dict = {}
    tv_orgs_in = set()
    for p in tv.get("players") or []:
        tv_orgs_in.add(p.get("org"))
        c = _canon(p.get("org"))
        if c in clubs:
            tv_by_club[c].append(p)
        if p.get("player_key"):
            tv_by_key[p["player_key"]] = p
        _pkp = trade_row_projection_key(p)
        if _pkp:
            tv_by_proj_key[_pkp] = p
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

    # D5 farm joins (R16): player_key joins timeseries / trade_values / debuts_lite
    # / mlb_projections; draft_results joins on (draft_year, pick_overall), never
    # on name (Sirota: a signed 2024 CIN row at 87 and an unsigned 2021 LAD row
    # at 492); orgs go through canonical_org and the non-club codes drop.
    ts_by_key = {p.get("player_key"): p for p in (ts.get("players") or []) if p.get("player_key")}
    slot_by_year_pick = {(r.get("draft_year"), r.get("pick_overall")): r for r in draft_results
                         if r.get("draft_year") is not None and r.get("pick_overall") is not None}
    acq_table = storage.load_acquisitions()
    trajectory_active = _trade_trajectory_active()
    grads_by_club: dict = defaultdict(list)
    grads_orgs_in = set()
    for g in debuts_lite:
        grads_orgs_in.add(g.get("org"))
        gc = _canon(g.get("org"))
        if gc in clubs:
            grads_by_club[gc].append(g)
    grads_dropped = sorted(o for o in grads_orgs_in if _canon(o) not in clubs)
    # league-wide pick maps for the picks summary: a pick counts as on the prospect
    # tracker or graduated wherever the player is now, not only on the drafting club.
    # The tracker carries the ranked and graded prospects, not every signed minor
    # leaguer, so a signed pick it does not carry is "not tracked", never "inactive".
    active_by_pick: dict = {}
    for p in ts.get("players") or []:
        a = p.get("acquisition") or {}
        if a.get("method") == "draft" and a.get("year") is not None and a.get("pick_overall") is not None:
            active_by_pick[(a["year"], a["pick_overall"])] = p.get("player_key")
    grad_by_pick: dict = {}
    for g in debuts_lite:
        a = g.get("acquisition") or acq_table.get(g.get("player_key")) or {}
        if a.get("method") == "draft" and a.get("year") is not None and a.get("pick_overall") is not None:
            grad_by_pick[(a["year"], a["pick_overall"])] = g.get("player_key")
    hist_n_swartz = sum(1 for r in (arb_hist.get("rows") or []) if r[7] is not None)
    a6 = arb_eval.get("a6_swartz") or {}

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
    shard_docs: dict = {}
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
                # Spotrac's 2027 estimate, reconstructed: the same schedule with no
                # base rate on Spotrac's own basis. The note prints only where the
                # reconstruction lands within $1, never as a standing claim.
                sur_only = None
                if est is not None and tax is not None:
                    no_base = {**rates, "base_rate_by_payor_year": {k: 0.0 for k in rates["base_rate_by_payor_year"]}}
                    sur_only = computed_cbt_bill(tax, SPOTRAC_2027_BASIS_USD, tier, no_base, tiers)["bill_usd"]
                blk["spotrac_est_surcharges_only_usd"] = sur_only
                blk["spotrac_est_is_surcharges_only"] = sur_only is not None and abs(sur_only - est) <= 1
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
            tvc = (tv_by_proj_key.get(v.get("key")) or {}).get("contract") or {}
            if not opts:
                for y in tvc.get("player_opt_years") or []:
                    opts.append([y, "player", None])
                for y in tvc.get("club_opt_years") or []:
                    opts.append([y, "club", None])
            if (v.get("salSrc") in ("contract", "contract+arb") and v.get("thru")
                    and tvc.get("signed_through") and int(tvc["signed_through"]) != int(v["thru"])):
                contract_disagreements += 1
            # One option per (season, holder), keeping the curated price where a
            # source has one. salOpt stamps a season with no price; since the
            # contract tail (2026-09-30) it reaches past the horizon, where the
            # curated file prices the same club option, and a set over
            # (season, holder, price) held both and could not sort None
            # against a price.
            best = {}
            for o in opts:
                if not o[0]:
                    continue
                k = (o[0], o[1])
                if k not in best or (best[k][2] is None and o[2] is not None):
                    best[k] = o
            opts = [list(best[k]) for k in sorted(best)]
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
            paid_slotted = int(sum(r.get("bonus_usd") or 0 for r in slotted))
            pool_usd = (pool_by_year.get(str(y)) or [None])[0]
            # pool_used divides by the published pool, which is the sum of the
            # club's round 1-10 slot values; the numerator is the bonuses on those
            # slotted picks only. Rounds 11+ carry no slot_usd, so their bonuses
            # stay in paid_usd (all rounds) and out of the pool share.
            paid_by_year[str(y)] = [
                len(mine), sum(1 for r in mine if r.get("signed")), sum(1 for r in mine if r.get("signed") == 0),
                paid, len(slotted), int(sum(r.get("slot_usd") or 0 for r in slotted)),
                paid_slotted,
                int(sum((r.get("bonus_usd") or 0) - (r.get("slot_usd") or 0) for r in slotted)),
                slot_cov.get(str(y)), pool_usd,
                round(paid_slotted / pool_usd, 3) if (pool_usd and paid_slotted) else None]
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
            "arbitration_teams": arbitration_link(c, arbitration_js),
            "trade_board": "/trademachine/#tab=tradeboard",
            "mlbstats_war": f"/mlbstats/#section=war&wview=teams&team={code}",
            "mlbstats_bullpen": f"/mlbstats/#section=bullpen&view=teams&team={code}",
            "betting_teams": "/betting/#section=teams",
            "fantasy_dynasty": f"/fantasy/#m=dynasty&team={c}",
            "management_club": f"/management/#section=clubs&team={c}",
            "franchise": f"/franchise/#team={c}" if (ROOT / "franchise" / "index.html").exists() else None,
        }

        # -- tax floor census (M09-03): Spotrac's 2027 tax payroll against the AAV of
        # the club's own guaranteed 2027 contract rows. A club or mutual option
        # year is not guaranteed and is left out. The figure is FLAGGED where it
        # sits below the floor, never replaced: Spotrac's number still prints.
        opt27 = {r[0] for r in outgoing if r[4] == "pending_option" and r[5] in TAX_FLOOR_NOT_GUARANTEED}
        floor_rows = [row for row in rows
                      if any(cell[0] == CLASS_YEAR and cell[5] == "contract" for cell in (row[10] or []))
                      and row[0] not in opt27
                      and not any(o[0] == CLASS_YEAR and o[1] in ("club", "mutual") for o in (row[11] or []))]
        floor_aav = int(sum(int(row[5] or 0) for row in floor_rows))
        floor_gap = (int(tax27) - floor_aav) if tax27 is not None else None
        payroll_block["tax_floor_2027"] = {
            "guaranteed_aav_usd": floor_aav, "n_rows": len(floor_rows),
            "n_option_rows_excluded": sum(1 for row in rows if row[0] in opt27),
            "spotrac_tax_payroll_usd": tax27, "gap_usd": floor_gap,
            "below": floor_gap is not None and floor_gap < 0,
        }

        club_docs[c] = {
            "club": c, "name": names.get(c), "statsapi_code": code,
            "payroll": payroll_block, "cbt": cbt, "commitments": commitments,
            "contracts": contracts, "arbitration": arbitration, "surplus": surplus,
            "indexes": indexes, "farm": farm, "fa": fa, "links": links,
        }

        # ==== D5 depth: the row layers, each reconciled to the v1 roll-up above ====
        # -- (a) farm rows: the trade board's actives joined to the PROSPX rows ----
        actives = [p for p in tvp if p.get("status") == "active"]
        prospect_rows = []
        n_with_bonus = 0
        gross = cost = 0.0
        by_method = {m: {"n": 0, "n_with_bonus": 0, "gross": 0.0, "cost": 0.0} for m in METHOD_BUCKETS}
        n_unbucketed = 0
        pick_to_prospect: dict = {}
        for p in sorted(actives, key=lambda x: (-(x.get("trade_value_mm") or 0), x.get("player_key") or "")):
            key = p.get("player_key")
            t = ts_by_key.get(key) or {}
            acq = t.get("acquisition") or acq_table.get(key) or {}
            cur = t.get("current_acquisition") or {}
            cr = p.get("crunch") or {}
            psur = t.get("surplus") or {}
            dist = psur.get("dist") or {}
            bonus = acq.get("bonus_usd")
            method = acq.get("method")
            slot = None
            if method == "draft":
                dr = slot_by_year_pick.get((acq.get("year"), acq.get("pick_overall")))
                slot = dr.get("slot_usd") if dr else None
                if acq.get("year") is not None and acq.get("pick_overall") is not None:
                    pick_to_prospect[(acq["year"], acq["pick_overall"])] = key
            tvmm = p.get("trade_value_mm")
            bonus_mm = float(bonus or 0) / 1e6
            net = round(float(tvmm) - bonus_mm, 3) if tvmm is not None else None
            if tvmm is not None:
                gross += float(tvmm)
                cost += bonus_mm
            if bonus:
                n_with_bonus += 1
            if method in by_method:
                b = by_method[method]
                b["n"] += 1
                b["n_with_bonus"] += 1 if bonus else 0
                if tvmm is not None:
                    b["gross"] += float(tvmm)
                    b["cost"] += bonus_mm
            else:
                n_unbucketed += 1
            cur_date = cur.get("date") or (cur.get("event") or {}).get("date")
            cur_year = int(str(cur_date)[:4]) if cur_date and str(cur_date)[:4].isdigit() else None
            prospect_rows.append([
                key, p.get("player_name") or t.get("player_name"), p.get("position") or t.get("position"),
                p.get("age") if p.get("age") is not None else t.get("age"),
                t.get("fv_close"), p.get("xfv_grade"), method, acq.get("year"), acq.get("pick_overall"),
                bonus, slot, cur.get("method"), cur_year,
                tvmm, p.get("trade_value_lo"), p.get("trade_value_hi"), p.get("p_bust"), net,
                t.get("dollar_dvm_plus"), (t.get("eta") or {}).get("year"),
                cr.get("service_phase"), cr.get("on_40_man"), cr.get("options_left"), cr.get("rule5_exposed"),
                p.get("trade_value_grade"), psur.get("value_mm"), dist.get("p10_mm"), dist.get("p90_mm")])
        fas = tree.get("fin_active_surplus") or {}
        leaf_mm = fas.get("surplus_total_mm")
        gap, tol, fstatus = farm_reconcile_status(leaf_mm, gross - cost)
        farm["reconciliation"] = {
            "leaf_mm": leaf_mm, "leaf_cost_mm": fas.get("cost_basis_mm"), "leaf_n": fas.get("active_count"),
            "leaf_source": "timeseries.org_summary tree.fin_active_surplus",
            "leaf_generated_at": ts.get("generated_at"),
            "rows_gross_mm": round(gross, 2), "rows_cost_mm": round(cost, 2), "rows_net_mm": round(gross - cost, 2),
            "rows_source": "trade_values.json + timeseries.players", "rows_generated_at": tv.get("generated_at"),
            "n_rows": len(prospect_rows), "n_with_bonus": n_with_bonus, "n_unbucketed": n_unbucketed,
            "gap_mm": gap, "tolerance_mm": tol, "status": fstatus,
        }
        me = fas.get("method_efficiency") or {}
        farm_method = {}
        for m in METHOD_BUCKETS:
            b, s = by_method[m], (me.get(m) or {})
            has = b["n"] > 0
            net_m = b["gross"] - b["cost"]
            farm_method[m] = [b["n"], b["n_with_bonus"],
                              round(b["gross"], 2) if has else None, round(b["cost"], 2) if has else None,
                              round(net_m, 2) if has else None,
                              round(net_m / b["cost"], 2) if (has and b["cost"] > 0) else None,
                              s.get("surplus_total_mm"), s.get("cost_basis_mm"), s.get("count") or 0,
                              s.get("surplus_per_fv_pt_mm")]
        farm["method"] = farm_method
        farm["trajectory_active"] = trajectory_active.get(c) or []
        farm["n_prospects"] = len(prospect_rows)
        # graduates: debuts_lite rows for the club, two engines per row, never summed
        grad_rows = []
        for g in sorted(grads_by_club.get(c) or [], key=lambda x: (x.get("debut_date") or "", x.get("player_key") or ""), reverse=True):
            key = g.get("player_key")
            acq = g.get("acquisition") or acq_table.get(key) or {}
            dv = g.get("debuted_value") or {}
            tvr = tv_by_key.get(key) or {}
            tv_deb = tvr if tvr.get("status") == "debuted" else {}
            # current control: the trade board's control_thru (as surplus.rows_debuted
            # prints it), else the projections vet row's ctrlThru; blank when neither
            # carries the player. debuted_value.remaining_control_years is the at-debut
            # window the engine priced (7 on every row) and is not served here.
            vr = graduate_vet(g, vets_by_key, vets_by_mlbam) or {}
            if tv_deb.get("control_thru") is not None:
                ctrl_thru, ctrl_why = tv_deb.get("control_thru"), tv_deb.get("control_why")
            elif vr.get("ctrlThru") is not None:
                ctrl_thru, ctrl_why = vr.get("ctrlThru"), vr.get("ctrlWhy")
            else:
                ctrl_thru = ctrl_why = None
            grad_rows.append([
                key, g.get("player_name"), g.get("position"), g.get("debut_date"),
                acq.get("method"), acq.get("year"), acq.get("bonus_usd"),
                dv.get("trade_value_mm"), dv.get("realized_mm"), ctrl_thru, ctrl_why,
                tv_deb.get("trade_value_mm"), tv_deb.get("surplus_source"),
                (g.get("roster_status") or {}).get("service_phase"),
                (g.get("career_war") or {}).get("career_war"),
                (dv.get("wag") or {}).get("boom_label"), bool(vr)])
        farm["n_graduates"] = len(grad_rows)
        # draft picks by year: joined on (draft_year, pick_overall), never on name
        picks: dict = {}
        picks_summary: dict = {}
        for y in DRAFT_YEARS:
            mine = [r for r in draft_results if r.get("draft_year") == y and _canon(r.get("team")) == c]
            prow = []
            n_signed = n_act = n_grad = n_unsigned_act = 0
            for r in sorted(mine, key=lambda x: x.get("pick_overall") or 0):
                pk = (y, r.get("pick_overall"))
                # the v1 draft_paid slotted rule: a figure only when both slot and
                # bonus are non-zero; an unsigned pick (bonus 0) is not a saving
                over = ((int(r["bonus_usd"]) - int(r["slot_usd"]))
                        if (r.get("slot_usd") and r.get("bonus_usd")) else None)
                prow.append([r.get("pick_overall"), r.get("round_label"), r.get("player_name"), r.get("slot_usd"),
                             r.get("bonus_usd"), r.get("signed"), over, pick_to_prospect.get(pk)])
                # signed picks only, each in exactly one of three buckets:
                # on the tracker (active prospect), graduated, not tracked
                if r.get("signed"):
                    n_signed += 1
                    if pk in active_by_pick:
                        n_act += 1
                    elif pk in grad_by_pick:
                        n_grad += 1
                elif pk in active_by_pick:
                    n_unsigned_act += 1
            picks[str(y)] = prow
            picks_summary[str(y)] = [len(prow), n_signed, n_act, n_grad, n_signed - n_act - n_grad,
                                     n_unsigned_act]
        farm["picks_summary"] = picks_summary

        # -- (b) arbitration: every rung, the by-season split, the realized rows ----
        ladders = []
        per_season: dict = {}
        n_in_vets = n_with_sp = 0
        for r in sorted(arows, key=lambda x: -(x.get("tot") or 0)):
            m = r.get("m")
            vv = vets_by_mlbam.get(int(m)) if m is not None else None
            in_v = vv is not None
            has_sp = bool(vv and vv.get("salPath"))
            n_in_vets += 1 if in_v else 0
            n_with_sp += 1 if has_sp else 0
            ladders.append([r.get("n"), m, r.get("sv"), r.get("svy"), r.get("c"), r.get("e"), r.get("yl"),
                            r.get("l") or [], r.get("w") or [], r.get("tot"), in_v, has_sp])
            for rung in r.get("l") or []:
                season, proj_usd, tok = rung[0], rung[1], rung[4]
                dd = per_season.setdefault(int(season), [0, 0, 0, 0, 0])
                if proj_usd is None:
                    dd[4] += 1
                elif tok == "PRE-ARB":
                    dd[2] += int(round(float(proj_usd)))
                    dd[3] += 1
                else:
                    dd[0] += int(round(float(proj_usd)))
                    dd[1] += 1
        arbitration["by_season"] = [[s] + per_season[s] for s in sorted(per_season)]
        arbitration["n_in_vets"] = n_in_vets
        arbitration["n_with_salpath"] = n_with_sp
        arbitration["s2027_note"] = "arb_prearb_rungs"
        realized_rows = [[r[0], r[1], r[2], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]]
                         for r in sorted(hrows, key=lambda x: (-int(x[0]), str(x[2])))]

        # -- (c) contract paths and the debuted trade rows -------------------------
        contract_keys = {row[0] for row in rows}
        opts_by_key = {row[0]: row[11] for row in rows}
        paths = []
        n_re = n_opt_rows = n_opt_seasons = 0
        for v in sorted(priced, key=lambda x: -(x.get("aav") or 0)):
            key = v.get("key")
            tvr = tv_by_proj_key.get(key) or {}
            strip = v.get("sur") if isinstance(v.get("sur"), list) else [None] * len(HORIZON)
            tvmm, src, st = tvr.get("trade_value_mm"), tvr.get("surplus_source"), v.get("surTotal")
            re_ = bool(src == "projection" and tvmm is not None and st is not None
                       and abs(float(tvmm) - float(st) / 1e6) > TV_MATCH_TOL_MM)
            n_re += 1 if re_ else 0
            po = sorted({int(o[0]) for o in (opts_by_key.get(key) or []) if o[1] == "player"})
            co = sorted({int(o[0]) for o in (opts_by_key.get(key) or []) if o[1] == "club"})
            if po:
                n_opt_rows += 1
                n_opt_seasons += len(po)
            paths.append([key, v.get("war"), v.get("warP10"), v.get("warP90"), strip, v.get("surNpv"),
                          v.get("surRos"), st, tvmm, tvr.get("trade_value_lo"), tvr.get("trade_value_hi"),
                          tvr.get("trade_value_grade"), src, tvr.get("band_basis"), tvr.get("salary_basis"),
                          tvr.get("control_thru"), tvr.get("control_why"), tvr.get("remaining_control_years"),
                          po, co, re_, npv_of_strip(strip, rate)])
        contracts["paths_summary"] = {"n_paths": len(paths), "n_reanchored": n_re,
                                      "n_opt_out_rows": n_opt_rows, "n_opt_out_seasons": n_opt_seasons}
        debuted = [p for p in tvp if p.get("status") == "debuted"]
        rows_debuted = [[p.get("player_key"), p.get("player_name"), p.get("position"), p.get("trade_value_mm"),
                         p.get("trade_value_lo"), p.get("trade_value_hi"), p.get("trade_value_tier"),
                         p.get("trade_value_grade"), p.get("surplus_source"), p.get("salary_basis"),
                         p.get("control_thru"), p.get("control_why"), p.get("player_key") in contract_keys]
                        for p in sorted(debuted, key=lambda x: (-(x.get("trade_value_mm") or 0), x.get("player_key") or ""))]
        by_salsrc = {}
        for src in mlb_by_src_mm:
            rr = [row for row in rows if (row[4] or "unknown") == src]
            by_salsrc[src] = [mlb_by_src_mm[src], round(sum(int(row[9] or 0) for row in rr) / 1e6, 1), len(rr)]
        mlb_rows_mm = round(sum(v[1] for v in by_salsrc.values()), 1)
        tra = round(sum(float(p.get("trade_value_mm") or 0) for p in actives), 1)
        trd = round(sum(float(p.get("trade_value_mm") or 0) for p in debuted), 1)
        s_ok = (mlb_rows_mm == surplus["mlb_mm"]
                and all(v[0] == v[1] for v in by_salsrc.values())
                and (farm_mm is None or leaf_mm is None or abs(float(farm_mm) - float(leaf_mm)) <= FARM_EXACT_MM)
                and abs(float(surplus["trade_currency_mm"]) - (tra + trd)) <= 0.1)
        surplus["reconciliation"] = {
            "by_salsrc": by_salsrc, "mlb_served_mm": surplus["mlb_mm"], "mlb_rows_mm": mlb_rows_mm,
            "farm_served_mm": farm_mm, "farm_leaf_mm": leaf_mm,
            "trade_currency_served_mm": surplus["trade_currency_mm"],
            "trade_rows_active_mm": tra, "trade_rows_debuted_mm": trd,
            "status": "exact" if s_ok else "broken",
        }
        surplus["n_debuted_rows"] = len(rows_debuted)

        shard_docs[c] = {
            "club": c, "statsapi_code": code, "board_generated_at": generated_at, "generated_at": generated_at,
            "calibration": None, "cba_banner": True,
            "farm": {"prospects": prospect_rows, "graduates": grad_rows, "picks": picks, "prospect_trajectory": {}},
            "arbitration": {"ladders": ladders, "realized_rows": realized_rows},
            "contracts": {"paths": paths},
            "surplus": {"rows_debuted": rows_debuted},
            "field_key": {}, "columns": {},
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
    # what the index ranks: its Spearman against minus the CBT payroll and against
    # the projected WAR, on the unrounded ratio, measured here every build
    rk = [c for c in clubs if ratio_by_club.get(c) is not None
          and club_docs[c]["payroll"]["s2027"]["tax_payroll_usd"] and club_docs[c]["indexes"]["proj_war_2027"]]
    rho_pay = _spearman([ratio_by_club[c] for c in rk], [-club_docs[c]["payroll"]["s2027"]["tax_payroll_usd"] for c in rk])
    rho_war = _spearman([ratio_by_club[c] for c in rk], [club_docs[c]["indexes"]["proj_war_2027"] for c in rk])

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
            "tax_floor_below_2027": d["payroll"]["tax_floor_2027"]["below"],
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
            ["usd_per_win", "$ per proj win", "cost_plus", f"Spotrac CBT payroll 2027 over team_win_projections 2027 wins ({tw}); plain dollars; {NO_ARB_IN_DENOM}"],
            ["cost_plus", "Cost+", "cost_plus", f"100+10z of projected 2027 WAR per $M of 2027 CBT payroll across the 30 clubs; descriptive index, numerator {tw}; {NO_ARB_IN_DENOM}"],
            ["usd_per_war", "$ per proj WAR", "cost_plus", f"Spotrac CBT payroll 2027 over projected 2027 WAR; plain dollars, no ladder; {NO_ARB_IN_DENOM}"],
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
                                "averages_excluded": True,
                                "spearman_vs_neg_cbt_payroll": _r(rho_pay, 3), "spearman_vs_proj_war": _r(rho_war, 3),
                                "n_spearman": len(rk)}},
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
        "cbt_spotrac_surcharges_only": (f"Spotrac's {CLASS_YEAR} estimate equals the surcharges alone on its "
                                        f"{SPOTRAC_2027_BASIS_USD // 1_000_000}M basis, to the dollar; it carries no base "
                                        "rate, which the computed bill does"),
        "tax_floor_flag": "below own contracts",
        "tax_floor_note": ("Spotrac's 2027 tax payroll sits below the AAV of this club's own guaranteed 2027 "
                           "contract rows (club and mutual option years left out). The figure prints as "
                           "Spotrac publishes it; the 2027 space and Cost+ built on it overstate the room."),
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
                          "horizon"
                          + (f", every guaranteed season past {HORIZON[-1]} priced too, on the champion mean path"
                             if tail_on else "")
                          + f", {_pct_str(rate)} discount, usd converted to $M; farm leg: org_summary active "
                          "surplus ($M, prospect_surplus validated), "
                          + (f"priced at the same {dpw_proj:,} per WAR (one level for prospect and veteran "
                             "surplus since 2026-09-25). "
                             if farm_level and dpw_proj and int(farm_level) == int(dpw_proj) else
                             f"priced at {farm_level:,} per WAR against the MLB leg's {dpw_proj:,}, summed as "
                             "priced. " if farm_level and dpw_proj else "")
                          + "Both legs in $M before the sum."),
        "surplus_no_tier": ("a club total sits above the player-row surplus ladder's top cut nearly "
                            "everywhere, so it prints plain"),
        "surplus_ev": "Sur+ sums are sums of expected values; quantiles are never summed",
        "trade_currency_basis": ("Trade Machine currency (trade_machine_surplus provisional); overlaps the "
                                 "MLB and farm legs by construction and is never added to them"),
        "trajectory_note": "since late June, no earlier history",
        "ratio_bases": (f"Spotrac CBT payroll {CLASS_YEAR} over team_win_projections {CLASS_YEAR} ({tw})"),
        "cost_plus_basis": ("descriptive index: a ratio of two served numbers, not a model. The denominator is "
                            f"Spotrac's {CLASS_YEAR} CBT payroll, which carries no arbitration or pre-arbitration "
                            f"salaries, while the numerator is the whole projected {CLASS_YEAR} roster, so the index "
                            + ("runs mostly as an inverse payroll rank" if abs(rho_pay or 0) > abs(rho_war or 0)
                               else "reads payroll as well as WAR")
                            # printed from the stored 3dp value, so the copy and the pool
                            # key can never round to different last digits (0.8749 -> 0.875)
                            + f": Spearman {_r(rho_pay, 3):.2f} against minus the CBT "
                            f"payroll and {_r(rho_war, 3):.2f} against projected WAR across {len(rk)} clubs"),
        "cost_plus_registry": "no registry row: Cost+ predicts nothing; a skill claim would need an eval first",
        "orgsur_chip": "descriptive, unvalidated",
        "farm_leaves": {k: {"basis": LEAF_VALUE[k][2], "weight": leaf_weights.get(k)} for k in FIN_LEAVES},
        "farm_letters_note": "letters come from org_summary.grades (rank across 30 orgs) and are never recomputed; a sparse leaf prints a dash",
        "pools_note": "2021 holds nine clubs (parser miss on the MLB.com article); 2027 pools are not published",
        "slot_coverage_basis": "share of the league's draft_results rows for that year carrying slot_usd",
        "pool_used_basis": ("bonuses on the round 1-10 slotted picks over the published pool, which is "
                            "the sum of those slot values; the Paid column also counts rounds 11 and later, "
                            "which carry no slot, and their bonuses above $150,000 are not added to Pool used"),
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

    # ---- D5 copy: every new sentence once; the two templates take their figure
    # from the artifact at build time (L11, L12), never typed ------------------
    tv_cal = ((tv.get("calibration") or {}).get("version")) or "unstamped"
    copy.update({
        "farm_dollar_is_template": (
            "A farm dollar here is an expected value: the eFV expected surplus of an active prospect, "
            "in millions, on the clemens_2026 valuation set (its tier shape at the one free-agent $/WAR "
            "level the MLB leg also prices at) over its own seven-season window, priced "
            "through the platform's calibrated engine (calibration {calibration_version}, "
            "prospect_surplus validated on data/surplus_backtest_real.json). It is the mean of a "
            "distribution whose 10th and 90th percentiles print on the row. Net of the signing bonus "
            "it is what the club roll-up sums."),
        "farm_dollar_is_not": (
            "It is not a trade price (the Trade Machine re-anchors debuted players and adds a roster "
            "crunch), not the club-control-window surplus the MLB Projections board prices for the "
            "prospects it carries (a different window and a different discount), not a quantile, and "
            "not a realized figure: no farm dollar has been earned. Quantiles on these rows are never "
            "summed, and a row's number is never added to a number on another basis."),
        "farm_reconcile": (
            "The roll-up leaf is the sum over active prospects of eFV expected surplus minus the "
            "signing bonus on file, computed inside the PROSPX org summary. The rows below carry the "
            "same two quantities from the trade board export and the PROSPX prospect rows; their sum "
            "is printed beside the leaf with both artifacts' stamps."),
        "farm_vintage_gap": (
            "The leaf and the rows were written at different points of the same nightly, and eFV "
            "surplus moves nightly; a gap inside the tolerance is vintage drift, not a disagreement "
            "about any prospect."),
        "farm_gap_broken": (
            "The rows do not reconcile to the leaf beyond the tolerance. Both figures are shown; "
            "neither is corrected."),
        "farm_no_bonus": (
            "A prospect with no bonus on file counts a cost of zero in the leaf and in these rows; the "
            "count is printed beside every cost figure. Most such rows are international signings "
            "whose bonus the pipeline never captured."),
        "trade_cost_dark": (
            "What a trade cost is the value given up, in FV and surplus, not dollars; no cost basis "
            "exists for the trade channel and none is invented. The Trade Machine prices the exchange."),
        "grad_two_engines": (
            "Two engines price a graduate: debuted_player_value (PROSPX debuted rows) and the trade "
            "board's posterior. Each prints under its own name; they are never averaged or summed."),
        "grad_contract_dark": (
            "Grad-Contract Surplus is served as the org mean only (current AAV minus the bonus "
            "amortized over six years, storage.py); no per-graduate row is exported, and recomputing "
            "one here would be a new number with no registry row."),
        "grad_contract_formula": (
            "per graduate with both a current AAV and a bonus on file: AAV minus bonus over six; the "
            "org mean and its n are the leaf, which is why n is smaller than the graduate count"),
        "grad_no_registry": (
            "debuted_player_value carries no registry row of its own; its parent prospect_surplus is "
            "validated. Read the debuted column as a served number without its own eval."),
        "shard_failed": "The per-club rows did not load; the preview above is the board's.",
        "shard_vintage": "These rows were written against a different board build than the one on screen.",
        "dvm_within_tier": ("$DvM+ is scaled within the prospect's FV tier and clamped 40-160: not on "
                            "the league z pool, unvalidated."),
        "p_bust_basis": ("P(bust) on the eFV row is the retired realized_implied map (ground-truthed "
                         "there); the MLB Projections prospect row's pBust is a different curve and "
                         "prints only under its own label."),
        "preview_note": "top rows by expected surplus; the full farm ledger loads per club",
        "grad_preview_note": "the graduate rows load per club",
        "arb_preview_note": "the class-year rung per row; the full ladder and the realized rows load per club",
        "trade_preview_note": "the debuted trade rows load per club",
        "paths_preview_note": "the WAR and surplus strips load per club",
        "trajectory_active_basis": ("the actives of each snapshot, on that snapshot's own status, gross "
                                    "of bonuses; so it does not chart the leaf and a graduation moves it"),
        "band_row_only": "p10 to p90, eFV basis, per row only",
        "years_to_fa_dark": "control not started; service time is a proxy on this site",
        "service_time_source": (tv.get("prearb_basis") or {}).get("service_time_source"),
        "ifa_slot_dark": "no slot: IFA is pool-percentage, see implied pool",
        "arb_prearb_rungs": ("board rows at the pre-arbitration minimum sit in this sum; the "
                             "arbitration rungs alone are the first figure"),
        "arb_two_populations": (
            "The stack above prices the club's priced veterans' salary paths; this bar sums the "
            "Arbitration Predictor's board rows for the same season. They overlap on the players both "
            "carry and differ on the rest; neither is added to the other and neither is a payroll."),
        "swartz_label_template": ("MLB Trade Rumors, Matt Swartz, published before settlement; present "
                                  "on {n_swartz} history rows, of which the a6 arm scored {n_a6} on "
                                  "identical rows"),
        "swartz_a6": a6.get("statement"),
        "swartz_a6_prefix": "a6 arm",
        "arb_quantiles_dark": ("P10 / P50 / P90 are not published: the band is the champion's MdAPE "
                               "spread by rung (arb_export.py) and no per-rung residual quantiles exist"),
        "arb_comps_dark": ("no comps are served; the champion is a ridge level model on log deflated "
                           "salary (arb-1) and an empirical raise multiplier (arb-2+); a comps consumer "
                           "must not read the contract set's aav_usd as a player's income "
                           "(ARBITRATION_GATE 10)"),
        "arb_filing_dark": ("filing figures and hearing outcomes are on no served row; svy is the "
                            "service-time as-of season"),
        "arb_class_labels": {"0": "Pre-Arb", "1": "Arb 1", "2": "Arb 2", "3": "Arb 3", "4": "Arb 4"},
        "npv_identity": ("the served NPV discounts the unrounded per-season figures; the strip is "
                         "rounded to 0.1M, so the two can differ by a few tens of thousands"),
        "sur_total_identity": ("the rest-of-season leg is published to 0.1M and the total was built "
                               "from the raw float; the printed equation can miss by a few tens of "
                               "thousands"),
        "sur_strip_basis": (f"MLB Projections per-season surplus: convex tier pricing at the {CLASS_YEAR} "
                            "ex-ante FA $/WAR level, "
                            + (f"escalated {float(proj.get('dpw_infl')) * 100:.1f}% per season"
                               if proj.get("dpw_infl") else "flat across seasons")
                            + ", minus the season's salary path cell; not war x $/WAR"),
        "war_band_cell": "per season, never summed",
        "tv_reanchored": ("re-anchored on the trade board (archetype posterior floor); the projections "
                          "figure is the contract row's"),
        "prearb_min_floor": (tv.get("prearb_basis") or {}).get("window_priced"),
        "opt_out_two_engines": (
            "player option seasons: the salary path prices them as guaranteed (opt-out not modelled, "
            "salary_path); the trade board's value folds an opt-out probability into this row "
            "(bayes_trade_value); the two are different numbers on purpose and neither is a served "
            "opt-out value"),
        "trade_currency_split": ("the trade currency is the farm ledger's gross rows plus the debuted "
                                 "rows; it overlaps both legs and is never added to them"),
        "shown_rows": "shown rows: a sum of expected values",
        "not_summed": "not summed",
        "sources_stamps": "each block names the artifact and the build stamp it was read from",
        "registry_sentence": ("provisional rows are labelled with the registry verdict quoted on the "
                              "Method tab; nothing on this page is scored by this page"),
    })
    copy["farm_dollar_is"] = copy["farm_dollar_is_template"].format(calibration_version=tv_cal)
    copy["swartz_label"] = copy["swartz_label_template"].format(n_swartz=hist_n_swartz, n_a6=a6.get("n"))

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
        "farm.draft_paid": "year -> [n_picks, n_signed, n_unsigned, paid_usd, n_slotted, slot_usd_on_slotted, paid_usd_on_slotted, over_slot_usd, slot_coverage_pct, pool_usd, pool_used]; paid_usd is every round; pool_used = paid_usd_on_slotted / pool_usd, the round 1-10 slotted bonuses over the published pool (round 11+ bonuses above $150,000 are not added)",
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

    # ---- D5 legends: prose beside a `columns` array for every row array -------
    shard_field_key = {
        "farm.prospects": (
            "[key, name, pos, age, consensus_fv, efv, acq_method, acq_year, pick_overall, bonus_usd, "
            "slot_usd, cur_method, cur_year, surplus_mm, band_lo_mm, band_hi_mm, p_bust, net_mm, "
            "dollar_dvm_plus, eta_year, service_phase, on_40_man, options_left, rule5_exposed, tv_grade, "
            "cons_surplus_mm, cons_lo_mm, cons_hi_mm]; surplus_mm is the eFV expected surplus (trade board "
            "trade_value_mm, equal to the eFV export's surplus_mm); band_lo/hi are the row's p10/p90 on "
            "that basis and are never summed; net_mm = surplus_mm - bonus_usd / 1e6 and is the only column "
            "the leaf sums; cons_* are the PROSPX consensus-basis figures for the expander only"),
        "farm.graduates": (
            "[key, name, pos, debut_date, acq_method, acq_year, bonus_usd, dv_trade_value_mm, "
            "dv_realized_mm, control_thru, control_why, tv_trade_value_mm, tv_surplus_source, "
            "service_phase, career_war, wag_label, in_vets]; dv_* from debuts_lite debuted_value "
            "(debuted_player_value), tv_* from the trade board; two engines on one row, each labelled, "
            "never summed; control_thru/control_why are the current control window from the trade "
            "board's debuted row, else the /projections/ vet row, else null (never the at-debut "
            "window); in_vets says whether /projections/ carries the player"),
        "farm.picks": (
            "year -> [[pick_overall, round_label, player_name, slot_usd, bonus_usd, signed, over_slot_usd, "
            "prospect_key]]; over_slot_usd is bonus minus slot only when both are non-zero (the "
            "draft_paid slotted rule), else null: an unsigned pick is not an under-slot saving; "
            "prospect_key is the farm.prospects row when the pick is still an active "
            "prospect of this club, else null"),
        "arbitration.ladders": (
            "[name, mlbam, sv, svy, class, flags, years_left, ladder [[season, proj_usd, lo_usd, hi_usd, "
            "token]], war [eWAR per rung, aligned], tot_usd, in_vets, has_salpath]; lo/hi are a "
            "fixed-spread band (0.22 + 0.08 per rung) and not P10/P90; sv is a string and prints as is; "
            "svy is the season the string is as of; no filing figure, hearing flag or comp exists on "
            "any row"),
        "arbitration.realized.rows": (
            "[season, mlbam, name, arb_year, actual_usd, ours_usd, swartz_usd, ou_mkt_usd, ou_war_usd, "
            "war, flags]; the arb_history row minus its team; swartz_usd is the MLB Trade Rumors (Matt "
            "Swartz) published pre-settlement projection, present on some rows; ou_mkt and ou_war are "
            "never combined and swartz is neither"),
        "contracts.paths": (
            "[key, war[5], war_p10[5], war_p90[5], sur_mm[5], sur_npv_usd, sur_ros_mm, sur_total_usd, "
            "tv_mm, tv_lo_mm, tv_hi_mm, tv_grade, surplus_source, band_basis, salary_basis, control_thru, "
            "control_why, remaining_control_years, player_opt_years, club_opt_years, reanchored, "
            "npv_check_usd]; war and sur are per-season expected values (MLB Projections); war_p10/p90 "
            "and tv_lo/hi print per row and are never summed; sur_npv_usd equals the contract row's; "
            "reanchored is true when tv_mm differs from sur_total_usd / 1e6 by more than 0.06 on a "
            "projection-sourced row; npv_check_usd is the NPV of the published strip at the platform "
            "rate, printed beside sur_npv_usd as an identity check"),
        "surplus.rows_debuted": (
            "[key, name, pos, tv_mm, tv_lo_mm, tv_hi_mm, tv_tier, tv_grade, surplus_source, salary_basis, "
            "control_thru, control_why, in_contract_rows]; the trade board's debuted rows for the club; "
            "active rows are the farm ledger's prospect rows and are not repeated"),
        "farm.prospect_trajectory": "key -> [[snapshot_date, trade_value_mm]] for the preview keys only",
    }
    board_field_key = {
        "farm.preview": "same legend as farm.prospects, the top PREVIEW_N rows by surplus_mm (board)",
        "farm.reconciliation": (
            "{leaf_mm, leaf_cost_mm, leaf_n, leaf_source 'timeseries.org_summary tree.fin_active_surplus', "
            "leaf_generated_at, rows_gross_mm, rows_cost_mm, rows_net_mm, rows_source 'trade_values.json + "
            "timeseries.players', rows_generated_at, n_rows, n_with_bonus, n_unbucketed, gap_mm (= leaf_mm - "
            "rows_net_mm), tolerance_mm, status exact|vintage_drift|broken}"),
        "farm.method": (
            "method -> [n, n_with_bonus, gross_mm, cost_mm, net_mm, net_per_cost_ratio, served_net_mm, "
            "served_cost_mm, served_count, served_per_fv_pt_mm]; the served_* cells are org_summary "
            "method_efficiency copied; net_per_cost_ratio is net_mm / cost_mm, a ratio of two served "
            "numbers, plain, no ladder; trade is always [0, 0, null, null, null, null, null, null, 0, null] "
            "today"),
        "farm.picks_summary": ("year -> [n_picks, n_signed, n_on_tracker, n_graduated, n_not_tracked, "
                               "n_unsigned_on_tracker]; the middle three split the signed picks and sum to "
                               "n_signed; a pick counts as on the tracker or graduated wherever the player is "
                               "now, not only on the drafting club; the prospect tracker carries ranked and "
                               "graded prospects, not every signed minor leaguer, so not tracked mixes released "
                               "players with players the tracker never carried"),
        "farm.trajectory_active": (
            "[snapshot_date, sum of trade_value_mm over that snapshot's active-status rows]; each "
            "snapshot's own actives, gross eFV basis, no bonus netting, so it is not the leaf's series"),
        "arbitration.by_season": (
            "[season, arb_rung_usd, n_arb_rungs, prearb_rung_usd, n_prearb_rungs, n_null_rungs]; "
            "arb_rung_usd sums the season's arbitration rungs that carry a projection and prearb_rung_usd "
            "the season's PRE-ARB rungs; their sum is the v1 ladder sum for that season (s2027_usd for "
            "2027) and the sum over seasons of both is v1 remaining_usd; each is an upper bound and neither "
            "is summed into the commitments stack; n_arb_rungs and n_prearb_rungs count the rungs in each "
            "sum; n_null_rungs counts rungs with proj null (no salary on file, flag 13), which enter no sum "
            "and print dark on the ladder"),
        "surplus.reconciliation": (
            "{by_salsrc: {src: [served_mm, rows_mm, n_rows]}, mlb_served_mm, mlb_rows_mm, farm_served_mm, "
            "farm_leaf_mm, trade_currency_served_mm, trade_rows_active_mm, trade_rows_debuted_mm, status}"),
        "contracts.paths_summary": "{n_paths, n_reanchored, n_opt_out_rows, n_opt_out_seasons}",
        "shard": "{path, bytes, sha256_16, generated_at}: the per-club row file this club's rows live in",
    }
    field_key.update(shard_field_key)
    field_key.update(board_field_key)

    sources = [
        ["S1", "fa_meta.json teams / cba / qo_tax_by_payor_tier / dpw_series", "fa_export", "daily"],
        ["S2", "storage.fa_team_payroll (Spotrac tax and payroll pages)", "fa_pipeline.refresh_payroll", "monthly"],
        ["S5", "mlb_projections.json vets / team_outlook / accountability.salary_path", "proj_export", "nightly"],
        ["S6", "trade_values.json players", "bayes_trade_value", "nightly"],
        ["S7", "storage.trade_value_history", "bayes_trade_value snapshot", "nightly"],
        ["S8", "arbitration.json", "arb_export", "monthly"],
        ["S9", "arb_history.json", "arb_export", "monthly"],
        ["S10", "fa_class.json / fa_class_2028 / fa_class_2029", "fa_export", "daily"],
        ["S11", "fa_archive.json (realized ledger included)", "fa_pipeline.backfill_historical -> fa_export",
         "file re-exported daily; realized ledger rebuilt by hand (fa_pipeline --backfill)"],
        ["S12", "cba_rules.json (via fa_cba)", "frozen curation", "frozen"],
        ["S13", "deferrals.json / contract_options.json", "frozen curation", "frozen"],
        ["S14", "timeseries.json org_summary / mlb_draft_pools", "storage.export_timeseries_json", "nightly"],
        ["S15", "storage.draft_results / draft_lottery_odds", "draft_bonus / Spotrac draft page", "monthly"],
        ["S16", "draft_slot_curve.json", "frozen", "frozen"],
        ["S17", "ifa_timeseries.json", "ifa_export", "nightly"],
        ["S18", "org_tendencies.json slot", "org_tendencies", "nightly"],
        ["S19", "storage.farm_grade_history", "storage snapshot", "nightly"],
        ["S20", "fa_dpw_series.json (the one $/WAR series and level)", "fa_market.write_dpw_series",
         "nightly, first step of the rebuild"],
        ["S21", "model_registry.json", "hand-committed", "frozen"],
        ["S22", "storage.fa_events (qo_offered)", "fa_pipeline", "daily"],
        ["S23", "timeseries.json players (acquisition, surplus, roster_status, eta)", "storage.export_timeseries_json", "nightly"],
        ["S24", "debuts_lite.json (debuted rows, debuted_value)", "storage.export_timeseries_json", "nightly"],
        ["S25", "arbitration_eval.json a6_swartz (quoted only)", "arb_eval", "on change"],
        ["S26", "xfv.json meta header (calibration stamp only)", "efv_export", "nightly"],
    ]
    def _cal_src(doc_cal: dict | None, generated_at) -> dict:
        c = doc_cal or {}
        return {"version": c.get("version"), "dpw_level_usd": c.get("dpw_level_usd"),
                "generated_at": generated_at}

    cal_sources = {
        "timeseries": _cal_src(ts.get("calibration"), ts.get("generated_at")),
        "trade_values": _cal_src(tv.get("calibration"), tv.get("generated_at")),
        "xfv": _cal_src(xfv_meta.get("calibration"), xfv_meta.get("generated_at")),
        "mlb_projections": _cal_src(proj.get("calibration"), proj.get("generated_at")),
    }
    cal_versions = {s["version"] for s in cal_sources.values() if s.get("version")}
    # VAL_1 (2026-09-25): the stamp names the $/WAR level too; one map at two
    # levels is two currencies.
    cal_levels = {s["dpw_level_usd"] for s in cal_sources.values() if s.get("dpw_level_usd")}
    calibration = {"version": (tv.get("calibration") or {}).get("version"),
                   "dpw_level_usd": (tv.get("calibration") or {}).get("dpw_level_usd"),
                   "sources": cal_sources,
                   "agree": len(cal_versions) <= 1 and len(cal_levels) <= 1}
    arbitration_eval = {k: a6.get(k) for k in ("n", "ours_mdape", "swartz_mdape", "ratio_ours_over_swartz",
                                                "verdict", "claim", "statement")}
    arbitration_eval["generated_at"] = arb_eval.get("generated_at")
    doc = {
        "generated_at": generated_at,
        "season_now": SEASON_NOW, "class_year": CLASS_YEAR, "horizon": list(HORIZON),
        "cba": {"threshold_by_season": {str(s): thr[s]["threshold_usd"] for s in range(2017, 2028)},
                "threshold_2027_basis": "carry_forward",
                "spotrac_2027_basis_usd": SPOTRAC_2027_BASIS_USD,
                "banner_text": banner_text, "expiry": cba_expiry,
                "rates": rates, "surcharge_tiers_usd": list(tiers), "brackets": brackets,
                "unverified_records": len(unverified)},
        "copy": copy,
        "field_key": field_key,
        "columns": {k: list(v) for k, v in COLUMNS.items()},
        "calibration": calibration,
        "arbitration_eval": arbitration_eval,
        "shards": None,        # filled once the shard bytes are known (below)
        "league": league,
        "clubs": club_docs,
        "rules": rules,
        "sections": {
            # D5 dark and partial items, each with its blocker (section 11)
            "farm_trade_cost_basis": {"live": False, "blocked_on": copy["trade_cost_dark"]},
            "grad_contract_per_graduate": {"live": False, "blocked_on": copy["grad_contract_dark"]},
            "farm_years_to_fa": {"live": False, "blocked_on": copy["years_to_fa_dark"] + " (trade_values prearb_basis.service_time_source)"},
            "farm_bonus_missing": {"live": True, "note": "partial: actives with no bonus on file are counted per club and per method", "blocked_on": copy["farm_no_bonus"]},
            "ifa_slot": {"live": False, "blocked_on": copy["ifa_slot_dark"]},
            "arb_quantiles": {"live": False, "blocked_on": copy["arb_quantiles_dark"]},
            "arb_comps": {"live": False, "blocked_on": copy["arb_comps_dark"]},
            "arb_filing": {"live": False, "blocked_on": copy["arb_filing_dark"]},
            "arb_service_time": {"live": True, "note": "partial: sv on a minority of board rows; the class token is inferred elsewhere (flag 1)",
                                 "blocked_on": "published service time is on a minority of rows; the class token is inferred (flag bit 1)"},
            "opt_out_value": {"live": False, "blocked_on": copy["opt_out_two_engines"]},
            "debuted_value_registry": {"live": True, "note": "partial: debuted_player_value has no registry row; prospect_surplus (validated) is its parent",
                                       "blocked_on": copy["grad_no_registry"]},
            "shard_rows": {"live": True, "note": "per-club row files; dark at render time only when the fetch fails (copy.shard_failed)"},
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
                                           "draft_slot_curve": slot_curve.get("generated_at"),
                                           "debuts_lite": _file_stamp("debuts_lite.json"),
                                           "arbitration_eval": arb_eval.get("generated_at"),
                                           "xfv": xfv_meta.get("generated_at")},
                   "grad_contract_formula": copy["grad_contract_formula"],
                   "sources_stamps": copy["sources_stamps"]},
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
                         "arb_history": [len(hist_teams_in), len({_canon(t) for t in hist_teams_in if _canon(t) in clubs})],
                         "debuts_lite": [len(grads_orgs_in), len({_canon(o) for o in grads_orgs_in if _canon(o) in clubs})],
                         "debuts_lite_dropped": grads_dropped},
            "deferral_entries_unmatched": deferral_unmatched,
            "discount_rate": rate,
            "prearb_min_usd": prearb_min,
            "payor_2027_basis_census": dict(Counter(d["payroll"]["payor_2027"]["basis"] for d in club_docs.values())),
            "tax_floor_census": {
                "rule": ("Spotrac 2027 tax payroll >= the AAV of the club's own guaranteed 2027 contract rows "
                         "(club and mutual option years left out)"),
                "n_clubs": len(club_docs),
                "below": {c: d["payroll"]["tax_floor_2027"]["gap_usd"] for c, d in sorted(club_docs.items())
                          if d["payroll"]["tax_floor_2027"]["below"]},
            },
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
            "a prospect or contract number recomputed through value_framework: every figure on the row layers is a copy of a served artifact (PROSPECT_ANCHOR_GATE 13.2)",
            "a summed quantile or a combined residual: bands print per row, footers under a band column read not summed, ou_mkt and ou_war stay apart and the Swartz figure is a third quantity",
            "a dollar cost basis for the trade channel: FV given up is the Trade Machine's currency",
            "a per-graduate Grad-Contract Surplus: the org mean only is served (storage.py)",
            "arbitration comps, filing figures, hearing outcomes or per-rung residual quantiles: none is on any served row",
            "a served opt-out value: player option seasons are priced as guaranteed by the salary path and folded as a probability by the trade board, and neither is an opt-out value",
            "a rank or grade of clubs by farm finance beyond the v1 fin_* leaves",
            "a betting or management figure: the ledger's only touches are two links",
        ],
    }

    # ---- D5 finalize: previews, per-player trajectories, shard bytes and the
    # board index; the preview guard re-runs the step at the small size if the
    # written board would pass PREVIEW_GUARD_BYTES --------------------------------
    for c, sd in shard_docs.items():
        sd["calibration"] = calibration
        sd["field_key"] = dict(shard_field_key)
        sd["columns"] = {k: list(COLUMNS[k]) for k in
                         ("farm.prospects", "farm.graduates", "farm.picks", "arbitration.ladders",
                          "arbitration.realized.rows", "contracts.paths", "surplus.rows_debuted",
                          "farm.prospect_trajectory")}

    def _finalize(n: int) -> None:
        keys = []
        for c, sd in shard_docs.items():
            club_docs[c]["farm"]["preview"] = [list(r) for r in sd["farm"]["prospects"][:n]]
            keys.extend(r[0] for r in sd["farm"]["prospects"][:n])
        traj = _player_trajectories(keys)
        files = {}
        for c, sd in shard_docs.items():
            sd["farm"]["prospect_trajectory"] = {r[0]: traj.get(r[0]) or [] for r in sd["farm"]["prospects"][:n]}
            b = _shard_bytes(sd)
            stamp = {"path": f"{SHARD_DIRNAME}/{c}.json", "bytes": len(b), "sha256_16": _sha16(b)}
            files[c] = stamp
            club_docs[c]["shard"] = dict(stamp, generated_at=generated_at)
        doc["shards"] = {"dir": SHARD_DIRNAME, "n": len(files), "files": files, "preview_n": n,
                         "cap_bytes": SHARD_CAP_BYTES, "board_guard_bytes": PREVIEW_GUARD_BYTES}

    _finalize(PREVIEW_N)
    if _doc_bytes(doc) > PREVIEW_GUARD_BYTES:
        log.warning("ledger_export: board over %d bytes at preview %d; dropping to %d",
                    PREVIEW_GUARD_BYTES, PREVIEW_N, PREVIEW_N_SMALL)
        _finalize(PREVIEW_N_SMALL)
    _assert_document(doc)
    _assert_shards(doc, shard_docs)
    return doc, shard_docs


def build() -> dict:
    """The v1 signature: the board alone. run_monthly's d10e step and the tests
    that pin the v1 keys call this; the shards come from build_all()."""
    return build_all()[0]


def write_shards(doc: dict, shard_docs: dict) -> list:
    """Write data/ledger_clubs/CODE.json for the 30 clubs from the bytes the
    board indexed, remove any CODE.json whose club is not on the board, leave
    the directory otherwise. Returns the written paths. Called from main() and
    from run_monthly step d10e right after the board write."""
    import re as _re
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    files = (doc.get("shards") or {}).get("files") or {}
    written = []
    for c, sd in shard_docs.items():
        b = _shard_bytes(sd)
        stamp = files.get(c) or {}
        assert stamp.get("bytes") == len(b) and stamp.get("sha256_16") == _sha16(b), \
            f"{c}: shard bytes drifted from the board index"
        p = SHARD_DIR / f"{c}.json"
        p.write_bytes(b)
        written.append(p)
    keep = set(shard_docs)
    for p in SHARD_DIR.glob("*.json"):
        if _re.fullmatch(r"[A-Z]{2,3}\.json", p.name) and p.stem not in keep:
            try:
                p.unlink()
            except OSError as exc:
                log.warning("ledger_export: stale shard %s not removed: %s", p.name, exc)
    return written


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


def _walk_aggregates(obj, path="", inside=False):
    """(path, key) for every dict key that sits under an AGGREGATE_KEYS key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if inside:
                yield here, k
            yield from _walk_aggregates(v, here, inside or str(k) in AGGREGATE_KEYS)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_aggregates(v, f"{path}[{i}]", inside)


def assert_aggregate_keys(obj) -> None:
    """The depth pass's key rule (R1, L14). Under reconciliation / summary /
    method / paths_summary / by_season / footer: no key whose underscore
    tokens name a band end (lo, hi, p10, p90), because a band under an
    aggregate key is a summed quantile by construction; and a "rows" sum in
    $M must be one of SUM_KEYS_ALLOWED, so a seventh sum fails until it is
    named there. Positional rows carry their bands per row, where the
    renderer test pins "not summed" under every band column."""
    for path, k in _walk_aggregates(obj):
        ks = str(k).lower()
        toks = ks.split("_")
        assert not any(t in BAND_TOKENS for t in toks), f"{path}: a band end under an aggregate key"
        if "rows" in toks and ks.endswith("_mm"):
            assert ks in SUM_KEYS_ALLOWED, f"{path}: a sum the allow-list does not name"


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
        # D5: every row layer reconciles to the roll-up it sits under
        fr = d["farm"]["reconciliation"]
        assert fr["status"] in ("exact", "vintage_drift", "broken"), (c, fr["status"])
        assert fr["n_rows"] == d["farm"]["n_prospects"] and len(d["farm"]["preview"]) <= fr["n_rows"], c
        bs = {row[0]: row for row in d["arbitration"]["by_season"]}
        s27 = bs.get(CLASS_YEAR) or [CLASS_YEAR, 0, 0, 0, 0, 0]
        assert s27[1] + s27[3] == d["arbitration"]["s2027_usd"], (c, "by_season 2027 != s2027_usd")
        assert sum(r[1] + r[3] for r in bs.values()) == d["arbitration"]["remaining_usd"], (c, "by_season != remaining")
        assert d["surplus"]["reconciliation"]["status"] == "exact", (c, d["surplus"]["reconciliation"])
        assert d["shard"]["path"] == f"{SHARD_DIRNAME}/{c}.json", c
        for y, ps in d["farm"]["picks_summary"].items():
            assert len(ps) == len(COLUMNS["farm.picks_summary"]), (c, y)
            assert ps[2] + ps[3] + ps[4] == ps[1] and ps[4] >= 0, (c, y, "signed picks split")
    for path, k in _walk_keys(doc):
        ks = str(k).lower()
        assert ks not in FORBIDDEN_KEYS, path
        for frag in FORBIDDEN_KEY_FRAGMENTS:
            assert frag not in ks, path
        assert not (("ou_mkt" in ks and "ou_war" in ks) or ks in ("ou_total", "ou_combined", "ou_sum")), path
    assert_aggregate_keys(doc)
    assert doc["shards"] and doc["shards"]["n"] == 30 and set(doc["shards"]["files"]) == set(doc["clubs"])


def _assert_shards(doc: dict, shard_docs: dict) -> None:
    assert set(shard_docs) == set(doc["clubs"])
    for c, sd in shard_docs.items():
        assert sd["club"] == c and sd["board_generated_at"] == doc["generated_at"], c
        b = _shard_bytes(sd)
        assert len(b) <= SHARD_CAP_BYTES, (c, len(b), "shard over the cap")
        st = doc["shards"]["files"][c]
        assert st["bytes"] == len(b) and st["sha256_16"] == _sha16(b), c
        for key in SHARD_ROW_KEYS:
            blk, _, name = key.rpartition(".")
            if key == "arbitration.realized.rows":
                rows = sd["arbitration"]["realized_rows"]
            else:
                rows = sd[blk][name]
            n_cols = len(COLUMNS[key])
            for row in rows:
                assert len(row) == n_cols, (c, key, len(row), n_cols)
        for year_rows in sd["farm"]["picks"].values():
            for row in year_rows:
                assert len(row) == len(COLUMNS["farm.picks"]), (c, "farm.picks")
        for path, k in _walk_keys(sd):
            ks = str(k).lower()
            assert ks not in FORBIDDEN_KEYS, (c, path)
            for frag in FORBIDDEN_KEY_FRAGMENTS:
                assert frag not in ks, (c, path)
            assert not (("ou_mkt" in ks and "ou_war" in ks) or ks in ("ou_total", "ou_combined", "ou_sum")), (c, path)
        assert_aggregate_keys(sd)


def main(argv=None) -> int:
    doc, shard_docs = build_all()
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(ROOT)} ({n / 1e3:.0f} KB)")
    written = write_shards(doc, shard_docs)
    sizes = [p.stat().st_size for p in written]
    print(f"  shards: {len(written)} files in data/{SHARD_DIRNAME}/, {min(sizes) / 1e3:.0f}-{max(sizes) / 1e3:.0f} KB, "
          f"preview_n {doc['shards']['preview_n']}")
    fr = Counter(d["farm"]["reconciliation"]["status"] for d in doc["clubs"].values())
    print(f"  farm reconciliation: {dict(fr)}")
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
