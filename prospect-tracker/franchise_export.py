# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Build data/franchise_board.json, the payload behind /franchise/ (Franchise).

WHAT THIS PAGE IS. A hub. It re-serves numbers the other modules already
publish, on the scale each was computed on, with a labelled basis and a deep
link back to the module that owns each one. It computes exactly two new things:

  * a BRANCH SCORE: 100 + 10z of one served value across the 30 clubs
    (population sd, one decimal, None stays None), for the three graded
    branches ROSTER (team eWAR, current roster), OUTLOOK (projected 2027 wins,
    a provisional projection, chip on the bubble) and FARM (the PROSPX farm
    composite, RE-STANDARDISED because farm_score measures sd 6.36 across the 30
    and would tier at two thirds of the ladder if passed through; its LETTER and
    RANK pass through from PROSPX unchanged);
  * the FRANCHISE INDEX: the weighted mean of the three branch scores (ROSTER
    0.40 / OUTLOOK 0.30 / FARM 0.30, declared in the payload, never redistributed
    at runtime), RE-STANDARDISED to 100 + 10z across the 30 clubs before any
    rank, letter or tier is taken from it. A weighted mean of z-scores has sd
    below 10 unless the branches are perfectly correlated, so it is never banded
    on the z ladder raw; raw_weighted_mean ships beside the score.

Both are DESCRIPTIVE rank indexes with registry rows marked unvalidated on the
org_sur_plus precedent. Thirty percent of the index rests on a provisional
projection (team_win_projections) and the root card says so. Nothing here
recomputes a model, opens a socket or lends a verdict chip to a surface that
has no registry row (futures.json has none, so the ODDS section quotes the
artifact's own interval sentence instead).

NEVER SERVED, decided before the first number: a HoF tile (the HoF franchises
section is dark with hof_export's own wording), pennants or titles as a served
field, any club decision-quality grade, any manager skill claim, revenue or
valuation figures. The DUGOUT and MARKET sections carry realized value with the
counterfactual named, never a letter, never a plus metric.

THE JOIN TRAPS, handled once: the five /mlbstats/ leaderboards carry StatsAPI
codes (AZ, CWS, KC, SD, SF, TB, WSH), fa_meta.teams carries AVERAGES and OAK,
trade_values carries "Cuba", arb_history carries OAK,
war_daily team_ID is Baseball-Reference's (OAK 1968-2024) and joins the club
bWAR line only through data/franchise_spine.json. Everything goes through
trades.canonical_org / canonical_org_from_id and the writer REFUSES (raises
FranchiseRefusal, leaving the previous file on disk) when fewer than 30 clubs
resolve on any graded branch.

Deterministic. python franchise_export.py writes the file; build() returns the
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

DATA = ROOT / "data"
CACHE = ROOT / ".cache"
OUT = DATA / "franchise_board.json"
SPINE = DATA / "franchise_spine.json"

SEASON_NOW = 2026
CLASS_YEAR = 2027
STANDINGS_FIRST = 2000
SPINE_FIRST = 1969
N_CLUBS = 30
SIZE_BUDGET_BYTES = 1_500_000

#: Owner decision (2026-09-23, spec D3 + D6 alternative): the three graded
#: branches and their weights. Declared here, printed from the payload, never
#: redistributed pro rata at runtime.
WEIGHTS = {"roster": 0.40, "outlook": 0.30, "farm": 0.30}
GRADED = ("roster", "outlook", "farm")
DESCRIPTIVE = ("season", "fin", "market", "front_office", "dugout", "arbitration",
               "park", "history", "odds")
BRANCH_ORDER = GRADED + DESCRIPTIVE
BRANCH_LABEL = {"roster": "ROSTER", "outlook": "OUTLOOK", "farm": "FARM", "season": "SEASON",
                "fin": "FIN", "market": "MARKET", "front_office": "FRONT OFFICE",
                "dugout": "DUGOUT", "arbitration": "ARBITRATION", "park": "PARK",
                "history": "HISTORY", "odds": "ODDS"}
BRANCH_TITLE = {"roster": "The major-league club today", "outlook": "2027 to 2031",
                "farm": "The farm (PROSPX composite)", "season": "2026 on the field",
                "fin": "Finances", "market": "Free agency", "front_office": "Front office",
                "dugout": "In-game management", "arbitration": "Arbitration",
                "park": "The park", "history": "History", "odds": "The model's season view"}

#: Registry rows the page QUOTES beside the numbers. There is no war_rate_plus
#: row and no futures row; neither is invented here.
REGISTRY_IDS = ("ewar", "team_win_projections", "farm_grades", "org_sur_plus", "fa_team_fit",
                "fa_market", "org_tendencies", "arb_award", "leverage_consistency",
                "mgmt_decision_ledger", "mgmt_style_z", "prospect_surplus", "playoff_odds_sim")

#: The registry row the ODDS section quotes: futures.json is its eval artifact.
ODDS_REGISTRY_ID = "playoff_odds_sim"

#: Key names the writer refuses to emit anywhere in the document.
FORBIDDEN_KEYS = {"revenue", "revenues", "valuation", "valuations", "tv_money", "rsn",
                  "pennants", "titles", "manager_skill", "decision_quality", "hof_plaques"}
FORBIDDEN_KEY_FRAGMENTS = ("ou_total", "ou_combined", "ou_sum")

#: ESPN logo slugs differ from the lower-cased StatsAPI code for two clubs only;
#: pinned against build_site.ESPN_SLUGS by test_franchise_export.
_LOGO_SLUG_OVERRIDE = {"ARI": "ari", "CHW": "chw"}

DUGOUT_FAMILIES = (("pitching_change", "Pitching changes"), ("pinch_hit", "Pinch hitters"),
                   ("pinch_run", "Pinch runners"), ("intentional_walk", "Intentional walks"),
                   ("bunt", "Bunts"), ("steal", "Steals"))
# What a reader saw happen, per family, for the dugout sentence. The sentence names
# only the families the decision ledger sums (decisions.families[f].summed), so it
# cannot promise a family the table already shows or name one it does not.
DUGOUT_HAPPENED = {"steal": "the run sent", "bunt": "the bunt laid down",
                   "pitching_change": "the reliever called", "pinch_hit": "the pinch hitter sent",
                   "pinch_run": "the pinch runner sent", "intentional_walk": "the intentional walk issued"}


def _summed_families(mgmt: dict) -> list:
    """DUGOUT_FAMILIES keys the decision ledger sums, in DUGOUT_FAMILIES order."""
    fams = ((mgmt.get("decisions") or {}).get("families") or {})
    return [fk for fk, _ in DUGOUT_FAMILIES if (fams.get(fk) or {}).get("summed") is True]


def _dugout_sentence(live: list) -> str:
    """The Dugout note, read off the families the ledger sums."""
    said = [DUGOUT_HAPPENED[f] for f in live if f in DUGOUT_HAPPENED]
    if not said:
        lead = "What is shown here is what happened after the club's decisions."
    elif len(said) == 1:
        lead = f"What is shown here is what happened after the club's decisions: {said[0]}."
    else:
        lead = ("What is shown here is what happened after the club's decisions: "
                + ", ".join(said[:-1]) + ", and " + said[-1] + ".")
    return ("Realized value, not skill. " + lead + " What the alternative would have produced, "
            "the runner held, the starter left in, was never observed, so nothing on this page "
            "ranks a manager or a club by decision quality. The running game's gate returned a "
            "bounded null: a club's decision value did not repeat between halves of its own season.")

TENDENCY_PANELS = (
    ("slot", "Draft slot behaviour", "draft",
     (("overSlotShare", "over-slot share", "zOver"), ("r1UnderShare", "first-round under-slot share", None),
      ("bonusHHI", "bonus concentration (HHI)", "zBonusHHI"), ("prepDollarShare", "prep dollar share", "zPrepDollar")),
     ("label", "spendLabel")),
    ("ifa", "International signings", None,
     (("top1Share", "top-signing share of the class", None), ("hhi", "class concentration (HHI)", "zConc"),
      ("signingsPerClass", "signings per class", "zVolume")),
     ("label",)),
    ("trades", "Trades", "trades",
     (("volume", "players moved", "zVolume"), ("netProspects", "net prospects acquired", "zNet"),
      ("acqTopShare", "top-graded share of acquisitions", "zQuality"), ("cashReceived", "cash received, deals", "zCash")),
     ("volLabel", "dirLabel", "qdLabel")),
    ("promotion", "Promotion pace", "promotion",
     (("avlDiff", "age vs level, difference", "zYoung"), ("promoRate", "promotion rate", "zPromo"),
      ("debutAgePit", "pitcher debut age", "zDebutAgePit"), ("debutAgeHit", "hitter debut age", "zDebutAgeHit")),
     ("label",)),
    ("health", "Health", None,
     (("stintsPer100", "IL stints per 100 prospects", "z"),),
     ("label",)),
    ("graduation", "Graduation", "graduation",
     (("gradsPerYear", "graduates per year", "zGrads"), ("meanGradWar", "mean graduate WAR", "zWar"),
      ("draftHitRate", "draft hit rate", "zHitRate")),
     ("label",)),
    ("draftPos", "Draft profile", "draft",
     (("pitchShare", "pitcher share", "zPitch"), ("prepShare", "prep share", "zPrep"),
      ("collShare", "college share", "zColl"), ("upMidShare", "up-the-middle share", "zUpMid")),
     ()),
)


class FranchiseRefusal(RuntimeError):
    """Raised when fewer than 30 clubs resolve on a graded branch. The caller
    leaves the previous file on disk and files a red under franchise_export."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _j(name: str, base: Path = DATA):
    p = base / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("franchise_export: %s unreadable: %s", name, exc)
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


def _score_100(values: dict) -> dict:
    """THE ONE FORMULA THIS MODULE OWNS. 100 + 10 x (v - mean) / sd across the
    served values (population sd, one decimal); None stays None; a degenerate
    pool (sd 0) scores 100 everywhere. storage._zscore_to_100 is the precedent
    but it is a closure inside export_timeseries_json and cannot be imported,
    so the formula lives here and test_franchise_export pins it against the
    served org_summary score_100 leaves."""
    xs = [float(v) for v in values.values() if v is not None]
    if not xs:
        return {k: None for k in values}
    mu = statistics.mean(xs)
    sd = statistics.pstdev(xs)
    out = {}
    for k, v in values.items():
        if v is None:
            out[k] = None
        elif sd == 0:
            out[k] = 100.0
        else:
            out[k] = round(100.0 + 10.0 * (float(v) - mu) / sd, 1)
    return out


def _rank_desc(values: dict) -> dict:
    """1-based rank, descending; ties broken by code so the rank is total."""
    keyed = sorted(((v, k) for k, v in values.items() if v is not None), key=lambda t: (-t[0], t[1]))
    ranks = {k: i + 1 for i, (_v, k) in enumerate(keyed)}
    return {k: ranks.get(k) for k in values}


def letter_for_rank(rank, n: int = N_CLUBS):
    """storage._letter_grade, with its em-dash sparse sentinel mapped to None so
    the copy lint never meets it."""
    import storage
    if rank is None:
        return None
    s = storage._letter_grade(int(rank), n)
    return None if (not s or ord(s[0]) >= 0x2000) else s


def _pool_stats(values: dict) -> dict:
    xs = [float(v) for v in values.values() if v is not None]
    return {"n": len(xs), "mean": _r(statistics.mean(xs), 3) if xs else None,
            "sd": _r(statistics.pstdev(xs), 3) if xs else None}


def _money_m(usd) -> float | None:
    return _r(float(usd) / 1e6, 1) if usd is not None else None


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------

def _clubs_from_cache() -> dict:
    """canonical code -> identity, from the cached /api/v1/teams payload (30 rows).
    The StatsAPI code rides every club so the /mlbstats/ links never carry a
    site code (their team hash is compared raw against the StatsAPI code)."""
    from trades import statsapi_code
    raw = _j("statsapi_teams_2026.json", CACHE) or {}
    out = {}
    for t in raw.get("teams") or []:
        if (t.get("sport") or {}).get("id") not in (1, None):
            continue
        code = _canon(t.get("abbreviation"))
        if not code:
            continue
        sapi = statsapi_code(code) or t.get("abbreviation")
        slug = _LOGO_SLUG_OVERRIDE.get(code, str(sapi).lower())
        out[code] = {
            "code": code, "statsapi_code": sapi, "name": t.get("name"),
            "mlbam_id": t.get("id"), "league": (t.get("league") or {}).get("name"),
            "division": (t.get("division") or {}).get("name"),
            "venue_id": (t.get("venue") or {}).get("id"), "venue_name": (t.get("venue") or {}).get("name"),
            "first_year": t.get("firstYearOfPlay"),
            "logo": f"https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png",
        }
    return out


def _standings() -> tuple[dict, dict]:
    """{code: {season: row}} joined by StatsAPI team id (stable across the
    relocations: 120, 133, 139, 146), plus the census of ids seen."""
    from trades import canonical_org_from_id
    out: dict = defaultdict(dict)
    ids_seen: dict = {}
    for season in range(STANDINGS_FIRST, SEASON_NOW + 1):
        raw = _j(f"statsapi_standings_{season}.json", CACHE)
        if not raw:
            continue
        for rec in raw.get("records") or []:
            div = (rec.get("division") or {}).get("id")
            for tr in rec.get("teamRecords") or []:
                tid = (tr.get("team") or {}).get("id")
                code = canonical_org_from_id(tid, (tr.get("team") or {}).get("name"))
                if not code:
                    continue
                ids_seen.setdefault(int(tid), code)
                out[code][season] = {
                    "w": tr.get("wins"), "l": tr.get("losses"), "rs": tr.get("runsScored"),
                    "ra": tr.get("runsAllowed"), "rd": tr.get("runDifferential"),
                    "rank": int(tr.get("divisionRank")) if tr.get("divisionRank") else None,
                    "gp": tr.get("gamesPlayed"), "pct": tr.get("winningPercentage"),
                    "clinched": bool(tr.get("clinched")), "div_champ": bool(tr.get("divisionChamp")),
                    "division_id": div,
                }
    return dict(out), ids_seen


def _venues() -> dict:
    raw = _j("venues_1.json", CACHE / "venue_meta") or []
    out = {}
    for v in raw if isinstance(raw, list) else (raw.get("venues") or []):
        fi = v.get("fieldInfo") or {}
        loc = v.get("location") or {}
        out[v.get("id")] = {
            "name": v.get("name"), "capacity": fi.get("capacity"), "roof": fi.get("roofType"),
            "turf": fi.get("turfType"), "elevation_ft": loc.get("elevation"),
            "azimuth": loc.get("azimuthAngle"), "city": loc.get("city"), "state": loc.get("stateAbbrev"),
            "dims": {k: fi.get(k) for k in ("leftLine", "left", "leftCenter", "center",
                                             "rightCenter", "right", "rightLine")},
        }
    return out


def load_spine() -> dict:
    return _j(SPINE.name) or {}


def spine_org_of(team_id: str, season: int, spine: dict) -> str | None:
    """The canonical org a B-Ref team_ID belonged to in `season`, or None."""
    for org, intervals in (spine.get("orgs") or {}).items():
        for iv in intervals:
            if iv["team_id"] == team_id and iv["first"] <= season <= iv["last"]:
                return org
    return None


def _bwar_by_org(spine: dict) -> tuple[dict, dict]:
    """{code: [[season, club bWAR]]} from the war_daily frames through the spine,
    plus the census of team_IDs since the spine's first season."""
    try:
        import pandas as pd
    except ImportError:                      # pragma: no cover
        return {}, {"error": "pandas unavailable"}
    frames = []
    for f in ("bat.parquet", "pit.parquet"):
        p = CACHE / "war_daily" / f
        if not p.exists():
            return {}, {"error": f"{f} absent"}
        df = pd.read_parquet(p, columns=["year_ID", "team_ID", "WAR"])
        frames.append(df[df["year_ID"] >= SPINE_FIRST])
    df = pd.concat(frames)
    lookup: dict = {}
    for org, intervals in (spine.get("orgs") or {}).items():
        for iv in intervals:
            for s in range(iv["first"], iv["last"] + 1):
                lookup[(iv["team_id"], s)] = org
    by: dict = defaultdict(dict)
    unmapped: Counter = Counter()
    grouped = df.groupby(["team_ID", "year_ID"])["WAR"].sum()
    for (tid, yr), war in grouped.items():
        org = lookup.get((str(tid), int(yr)))
        if not org:
            unmapped[str(tid)] += 1
            continue
        by[org][int(yr)] = round(float(war), 1)
    out = {org: [[s, w] for s, w in sorted(seasons.items())] for org, seasons in by.items()}
    return out, {"team_ids_since_first": sorted(df["team_ID"].dropna().unique().tolist()),
                 "unmapped_team_ids": sorted(unmapped), "first_season": SPINE_FIRST}


def _team_rows(payload: dict, key: str = "teams") -> dict:
    """{canonical code: row} for a leaderboard's `teams` block (StatsAPI codes)."""
    out = {}
    for r in (payload or {}).get(key) or []:
        c = _canon(r.get("team"))
        if c:
            out[c] = r
    return out


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------

def build() -> dict:
    import storage
    from trades import canonical_org_from_id  # noqa: F401  (the standings join)

    # ---- inputs -------------------------------------------------------------
    war = _j("war_leaderboards.json") or {}
    hit = _j("hitter_leaderboards.json") or {}
    sta = _j("starter_leaderboards.json") or {}
    pen = _j("bullpen_leaderboards.json") or {}
    dfn = _j("defense_leaderboards.json") or {}
    proj = _j("mlb_projections.json") or {}
    proj_eval = _j("team_outlook_eval.json") or {}
    ts = _j("timeseries.json") or {}
    fa_meta = _j("fa_meta.json") or {}
    fa_class = _j("fa_class.json") or {}
    fa_archive = _j("fa_archive.json") or {}
    org_tend = _j("org_tendencies.json") or {}
    mgmt = _j("management_board.json") or {}
    arb = _j("arbitration.json") or {}
    arb_hist = _j("arb_history.json") or {}
    futures = _j("futures.json") or {}
    tv = _j("trade_values.json") or {}
    ledger = _j("ledger_board.json") or {}
    registry = _j("model_registry.json") or {}
    hof = _j("hof_board.json") or {}
    spine = load_spine()

    clubs = _clubs_from_cache()
    codes = sorted(clubs)
    if len(codes) != N_CLUBS:
        raise FranchiseRefusal(f"{len(codes)} clubs resolved from the StatsAPI teams cache, not {N_CLUBS}")

    standings, standings_ids = _standings()
    venues = _venues()
    bwar, bwar_census = _bwar_by_org(spine)

    war_rows = _team_rows(war)
    hit_rows = _team_rows(hit)
    sta_rows = _team_rows(sta)
    pen_rows = _team_rows(pen)
    dfn_rows = _team_rows(dfn)
    outlook = {}
    for row in proj.get("team_outlook") or []:
        c = _canon(row.get("team"))
        if c:
            outlook[c] = row
    org_summary = {}
    for o in ts.get("org_summary") or []:
        c = _canon(o.get("org"))
        if c:
            org_summary[c] = o
    futures_rows = {}
    for row in futures.get("clubs") or []:
        c = _canon(row.get("team"))
        if c:
            futures_rows[c] = row
    ledger_clubs = ledger.get("clubs") or {}
    ledger_live = bool(ledger_clubs) and all(c in ledger_clubs for c in codes)

    # registry verdicts quoted on the page
    reg_rows = {m.get("model_id"): m for m in (registry.get("models") or [])}
    registry_verdicts = []
    for mid in REGISTRY_IDS:
        m = reg_rows.get(mid)
        registry_verdicts.append({"model_id": mid, "present": bool(m), "verdict": (m or {}).get("verdict"),
                                  "surface": (m or {}).get("surface"), "eval_artifact": (m or {}).get("eval_artifact")})
    verdict_of = {r["model_id"]: r["verdict"] for r in registry_verdicts}
    odds_registered = bool(reg_rows.get(ODDS_REGISTRY_ID))

    # ---- the three graded values, one per club -------------------------------
    v_roster = {c: (war_rows.get(c) or {}).get("war") for c in codes}
    v_outlook = {c: (outlook.get(c) or {}).get("wins") for c in codes}
    v_farm = {c: (org_summary.get(c) or {}).get("farm_score") for c in codes}
    for key, vals, src in (("roster", v_roster, "war_leaderboards.teams"),
                           ("outlook", v_outlook, "mlb_projections.team_outlook"),
                           ("farm", v_farm, "timeseries.org_summary")):
        missing = sorted(c for c, v in vals.items() if v is None)
        if missing:
            raise FranchiseRefusal(f"{key}: {len(missing)} of {N_CLUBS} clubs carry no value on {src}: {missing}")

    s_roster = _score_100(v_roster)
    s_outlook = _score_100(v_outlook)
    s_farm = _score_100(v_farm)
    r_roster = _rank_desc(v_roster)
    r_outlook = _rank_desc(v_outlook)
    # FARM: letter and rank PASS THROUGH from PROSPX; only the score is re-standardised.
    farm_letter = {c: (org_summary.get(c) or {}).get("grades", {}).get("overall") for c in codes}
    farm_rank = {c: (org_summary.get(c) or {}).get("farm_rank") for c in codes}

    raw_index = {c: round(WEIGHTS["roster"] * s_roster[c] + WEIGHTS["outlook"] * s_outlook[c]
                          + WEIGHTS["farm"] * s_farm[c], 3) for c in codes}
    s_index = _score_100(raw_index)
    r_index = _rank_desc(s_index)

    league = {
        "n": N_CLUBS,
        "pools": {"roster_war": _pool_stats(v_roster), "outlook_wins_2027": _pool_stats(v_outlook),
                  "farm_score": _pool_stats(v_farm), "raw_weighted_mean": _pool_stats(raw_index)},
        "scores": {"roster": _pool_stats(s_roster), "outlook": _pool_stats(s_outlook),
                   "farm": _pool_stats(s_farm), "index": _pool_stats(s_index)},
    }

    # ---- shared inputs read once ---------------------------------------------------
    as_of_war = war.get("as_of")
    team_basis = (war.get("team_basis") or {})
    lsa = proj_eval.get("league_sum_accounting") or {}
    target_wins = lsa.get("target_wins_sum")
    league_war_benchmark = lsa.get("league_war_benchmark")
    replacement_wins = (round((float(target_wins) - float(league_war_benchmark)) / N_CLUBS, 1)
                        if target_wins and league_war_benchmark else None)
    fg_history = {}
    for row in storage.load_farm_grade_history():
        c = _canon(row.get("org"))
        if c:
            fg_history.setdefault(c, []).append([row.get("snapshot_date"), row.get("farm_score"), row.get("letter")])

    members = fa_class.get("members") or []
    fits_all = fa_class.get("teamFits") or {}
    winters = fa_archive.get("winters") or []
    tend_similar = ((org_tend.get("similarFarms") or {}).get("orgs") or {})
    mgmt_teams = (mgmt.get("teams") or {}).get("rows") or []
    mgmt_clubs = (mgmt.get("clubs") or {}).get("rows") or []
    live_fams = _summed_families(mgmt)
    mgmt_routes = mgmt.get("routes") or {}
    arb_rows_by: dict = defaultdict(list)
    for r in arb.get("rows") or []:
        c = _canon(r.get("t"))
        if c:
            arb_rows_by[c].append(r)
    hist_by: dict = defaultdict(list)
    hist_teams_in = set()
    for r in arb_hist.get("rows") or []:
        hist_teams_in.add(r[3])
        c = _canon(r[3])
        if c:
            hist_by[c].append(r)
    hist_fk = arb_hist.get("field_key") or {}
    tv_by: dict = defaultdict(list)
    tv_orgs_in = set()
    for p in tv.get("players") or []:
        tv_orgs_in.add(p.get("org"))
        c = _canon(p.get("org"))
        if c in clubs:
            tv_by[c].append(p)
    tv_dropped = sorted(o for o in tv_orgs_in if _canon(o) not in clubs)
    park = fa_meta.get("park_factors") or {}
    park_short = fa_meta.get("park_factors_short_window") or {}
    park_hand = fa_meta.get("park_factors_by_hand") or {}
    cba = fa_meta.get("cba") or {}
    spotrac_basis = None
    if ledger_live:
        sp = (ledger_clubs[codes[0]].get("payroll") or {}).get("space_2027") or {}
        spotrac_basis = sp.get("spotrac_basis_usd")
    hof_franchises = ((hof.get("sections") or {}).get("franchises") or {})
    arb_router_narrows = "TEAM_NARROW_RE" in (ROOT / "assets" / "arbitration.js").read_text(encoding="utf-8") \
        if (ROOT / "assets" / "arbitration.js").exists() else False

    # ---- per-club documents -------------------------------------------------------------
    club_docs = []
    for c in codes:
        ident = clubs[c]
        sapi = ident["statsapi_code"]
        wr, hr, sr, pr, dr = (war_rows.get(c) or {}), (hit_rows.get(c) or {}), (sta_rows.get(c) or {}), \
            (pen_rows.get(c) or {}), (dfn_rows.get(c) or {})
        out = outlook.get(c) or {}
        cur = out.get("current") or {}
        os_ = org_summary.get(c) or {}
        grades = os_.get("grades") or {}
        cranks = os_.get("component_ranks") or {}
        meta = (fa_meta.get("teams") or {}).get(c) or {}
        st = standings.get(c) or {}
        s26 = st.get(SEASON_NOW) or {}
        fut = futures_rows.get(c) or {}
        lc = ledger_clubs.get(c) or {}
        lidx = lc.get("indexes") or {}
        lpay = lc.get("payroll") or {}

        links = {
            "mlbstats_hitters": f"/mlbstats/#section=hitters&hview=teams&team={sapi}",
            "mlbstats_starters": f"/mlbstats/#section=starters&sview=teams&team={sapi}",
            "mlbstats_bullpen": f"/mlbstats/#section=bullpen&view=teams&team={sapi}",
            "mlbstats_defense": f"/mlbstats/#section=defense&dview=teams&team={sapi}",
            "mlbstats_war": f"/mlbstats/#section=war&wview=teams&team={sapi}",
            "mlbstats_leverage": f"/mlbstats/#section=leverage&team={sapi}",
            "team_outlook": "/projections/#view=teams",
            "roster_board": f"/projections/#team={c}",
            "farm": f"/prospx/#farm-org={c}",
            "tendencies": f"/prospx/#farm-org={c}&ftab=tendencies",
            "farm_tree": f"/prospx/#farm-org={c}&ftree=simple",
            "draft_board": "/prospx/#tab=draft",
            "ifa_board": "/prospx/#tab=ifa",
            "ledger": f"/ledger/#team={c}" if ledger_live else None,
            "fa_fits": f"/fa/#view=fits&team={c}",
            "fa_archive": f"/fa/#view=archive&winter={SEASON_NOW}",
            "management_club": (f"/management/#section=clubs&team={c}" if mgmt_clubs else "/management/"),
            "arbitration_teams": (f"/arbitration/#teams&team={c}" if arb_router_narrows else "/arbitration/#teams"),
            "arbitration_history": "/arbitration/#history",
            "arbitration_model": "/arbitration/#model",
            "parks": "/parks/",
            "hof": "/hof/",
            "betting_teams": "/betting/#section=teams",
            "betting_futures": "/betting/#section=futures",
            "trade_board": "/trademachine/#tab=tradeboard",
            "fantasy_dynasty": f"/fantasy/#m=dynasty&team={c}",
        }

        # -- ROSTER (graded) ---------------------------------------------------------
        roster = {
            "war": wr.get("war"), "war_earned": wr.get("war_earned"), "n_players": wr.get("n_players"),
            "split": {"bat": wr.get("war_bat"), "sp": wr.get("war_sp"), "rp": wr.get("war_rp"), "sw": wr.get("war_sw")},
            "offense_plus": hr.get("offense_plus"), "rotation_plus": sr.get("rotation_plus"),
            "bullpen_plus": pr.get("bullpen_plus"), "team_dem_plus": dr.get("team_dem_plus"),
            "leverage_deploy_plus": pr.get("leverage_deploy_plus"),
            "lineup": [[x.get("tier"), x.get("name"), x.get("bats"), x.get("hem_plus"), x.get("pa"), x.get("key")]
                       for x in (hr.get("lineup") or [])],
            "rotation": [[x.get("role"), x.get("name"), x.get("sem_plus"), x.get("ip"), x.get("gs"), x.get("key")]
                         for x in (sr.get("rotation") or [])],
            "bullpen": [[x.get("role"), x.get("name"), x.get("rem_plus"), x.get("gmli"), x.get("ip"), x.get("key")]
                        for x in (pr.get("depth") or [])],
            "alignment": [[x.get("pos"), x.get("name"), x.get("dem_plus"), x.get("inn_at_pos"), x.get("frm_runs"), x.get("key")]
                          for x in (dr.get("alignment") or [])],
            "basis": f"eWAR v2, current roster, {as_of_war}",
        }

        # -- SEASON (descriptive) -------------------------------------------------------
        season = {
            "wins": s26.get("w"), "losses": s26.get("l"), "games": s26.get("gp"), "pct": s26.get("pct"),
            "run_diff": s26.get("rd"), "rs": s26.get("rs"), "ra": s26.get("ra"), "division_rank": s26.get("rank"),
            "clinched": s26.get("clinched"), "division_champ": s26.get("div_champ"),
            "cur_wins_outlook": out.get("curWins"), "cur_pct_outlook": out.get("curPct"),
            "pythag_pct": cur.get("pythagPct"), "actual_pct": cur.get("actualPct"),
            "talent_prior_pct": cur.get("talentPriorPct"), "blend_weights": cur.get("blendWeights"),
            "gb": cur.get("gb"), "rem_games": cur.get("remGames"),
            "basis": f"StatsAPI standings {SEASON_NOW}, joined by team id; pythag from the Team Outlook current overlay",
        }

        # -- OUTLOOK (graded, provisional) ------------------------------------------------
        by_year = [[y.get("season"), y.get("wins"), y.get("war"), y.get("depthWar"), y.get("n")]
                   for y in (out.get("byYear") or [])]
        outlook_doc = {
            "wins": out.get("wins"), "losses": out.get("losses"), "war": out.get("war"),
            "wins_raw": out.get("winsRaw"), "depth_war": out.get("depthWar"), "n_players": out.get("n"),
            "by_year": by_year, "locked_pct": out.get("lockedPct"),
            "ctrl_war_5y": out.get("ctrlWar5y"), "full_war_5y": out.get("fullWar5y"),
            "top": [[t.get("name"), t.get("key"), t.get("war")] for t in (out.get("top") or [])],
            "provisional": True, "verdict": verdict_of.get("team_win_projections"),
            "basis": f"team_win_projections, first projected season {proj.get('first_season')}; a provisional projection",
        }

        # -- FARM (graded, re-standardised) ---------------------------------------------------
        tree = os_.get("tree") or {}
        farm_doc = {
            "letter": grades.get("overall"), "rank": os_.get("farm_rank"), "farm_score": os_.get("farm_score"),
            "score": s_farm[c],
            "branches": {k: {"letter": grades.get(k), "rank": cranks.get(k), "score": os_.get(f"{k}_score")}
                         for k in ("acquisition_strategy", "development", "financial", "mlb_production")},
            "financial_score": os_.get("financial_score"),
            "rank_movement": {k: (os_.get("rank_movement") or {}).get(k)
                              for k in ("direction", "delta", "from_rank", "to_rank", "from_date", "to_date")},
            "health_burden": (os_.get("health_burden") or {}).get("score"),
            "farm_surplus_mm": _r(((out.get("farm") or {}).get("farmSurplusMM")), 1),
            "n_prospects": os_.get("count"), "avg_age": os_.get("avg_age"),
            "top_prospect": (out.get("farm") or {}).get("topProspect"),
            "eta_align_years": (out.get("farm") or {}).get("etaAlignYears"),
            "history": fg_history.get(c) or [],
            "fin_active_surplus_mm": (tree.get("fin_active_surplus") or {}).get("surplus_total_mm"),
            "basis": "PROSPX org_summary, principal window 7y; farm_grades provisional; score re-standardised across 30 clubs, letter and rank are the PROSPX letter and rank",
        }

        # -- FIN (descriptive) ----------------------------------------------------------------
        tvp = tv_by.get(c) or []
        act = [float(p.get("posterior_surplus_mm") or 0) for p in tvp if p.get("status") == "active"]
        deb = [float(p.get("posterior_surplus_mm") or 0) for p in tvp if p.get("status") == "debuted"]
        fin_doc = {
            "live": True, "descriptive": True,
            "cost_plus": lidx.get("cost_plus") if ledger_live else None,
            "usd_per_win": lidx.get("usd_per_win") if ledger_live else None,
            "space_2027": ((lpay.get("space_2027") or {}) if ledger_live else
                           {"spotrac_usd": meta.get("space"), "spotrac_basis_usd": None, "platform_usd": None,
                            "platform_basis_usd": cba.get("threshold_usd")}),
            "tax_payroll_2027": meta.get("taxPayroll"), "committed_2027": meta.get("committed"),
            "tax_floor_2027": (lpay.get("tax_floor_2027") if ledger_live else None),
            "payor_2027": ((lpay.get("payor_2027") or {}) if ledger_live else {"value": meta.get("payor"), "basis": "spotrac"}),
            "recent_spend": meta.get("recentSpend"), "max_guar": meta.get("maxGuar"), "n100m": meta.get("n100m"),
            "roster_surplus_ev": {"active_mm": _r(sum(act), 1), "debuted_mm": _r(sum(deb), 1),
                                  "total_mm": _r(sum(act) + sum(deb), 1), "n_active": len(act), "n_debuted": len(deb),
                                  "basis": ("sum of trade_values posterior_surplus_mm, a sum of means and never of quantiles; "
                                            "the Trade Machine currency, which overlaps the farm surplus and is never added to it")},
            "cba_banner": True,
            "basis": ("Club Ledger (ledger_export): Cost+ and space on both bases" if ledger_live
                      else "fa_meta.teams (Spotrac); Club Ledger not on disk"),
        }

        # -- MARKET (descriptive) ---------------------------------------------------------------
        fit_rows = []
        for f in fits_all.get(c) or []:
            m = members[f["i"]] if isinstance(f.get("i"), int) and f["i"] < len(members) else None
            if m:
                fit_rows.append([m.get("name"), m.get("key"), m.get("pos"), f.get("fit"), f.get("need"),
                                 f.get("afford"), f.get("window")])
        outgoing = [[m.get("name"), m.get("key"), m.get("pos"), m.get("prevAav"), m.get("projGuar"),
                     m.get("projGuarP10"), m.get("projGuarP90"), m.get("verdict")]
                    for m in sorted((m for m in members if _canon(m.get("from")) == c),
                                    key=lambda x: -(x.get("projGuar") or 0))]
        winter_rows, realized_rows = [], []
        tot = {"n": 0, "n_covered": 0, "war_td": 0.0, "paid_td": 0, "surplus_td": 0, "n_done": 0}
        for w in winters:
            sg = w.get("signings") or []
            ins = [s for s in sg if _canon(s.get("to")) == c]
            outs = [s for s in sg if _canon(s.get("from")) == c]
            cov = [s for s in ins if s.get("warTd") is not None]
            winter_rows.append([w.get("year"), len(ins), int(sum(float(s.get("guar") or 0) for s in ins)),
                                len(outs), int(sum(float(s.get("guar") or 0) for s in outs))])
            realized_rows.append([w.get("year"), len(ins), len(cov), _r(sum(float(s.get("warTd") or 0) for s in cov), 1),
                                  int(sum(float(s.get("paidTd") or 0) for s in cov)),
                                  int(sum(float(s.get("surplusTd") or 0) for s in cov)),
                                  sum(1 for s in cov if s.get("done"))])
            tot["n"] += len(ins); tot["n_covered"] += len(cov)
            tot["war_td"] += sum(float(s.get("warTd") or 0) for s in cov)
            tot["paid_td"] += int(sum(float(s.get("paidTd") or 0) for s in cov))
            tot["surplus_td"] += int(sum(float(s.get("surplusTd") or 0) for s in cov))
            tot["n_done"] += sum(1 for s in cov if s.get("done"))
        tot["war_td"] = _r(tot["war_td"], 1)
        market = {
            "fits": fit_rows, "outgoing": outgoing, "winters": winter_rows,
            "priors": {"max_guar": meta.get("maxGuar"), "n100m": meta.get("n100m"), "recent_spend": meta.get("recentSpend")},
            "realized": {"live": True, "by_winter": realized_rows, "totals": tot,
                         "method": "level_proration_backcast_dpw_v1", "not_skill": True},
            "verdict": verdict_of.get("fa_team_fit"), "cba_banner": True,
            "basis": f"fa_class {fa_class.get('class_year')} fits (fa_team_fit provisional) and fa_archive signings by club",
        }

        # -- FRONT OFFICE (descriptive) ---------------------------------------------------------
        panels = []
        for key, plabel, wkey, rows, label_keys in TENDENCY_PANELS:
            blk = org_tend.get(key) or {}
            orow = (blk.get("orgs") or {}).get(c) or {}
            lg = blk.get("league") or {}
            prow = []
            for vk, vlabel, zk in rows:
                v = orow.get(vk)
                z = orow.get(zk) if zk else None
                stat = lg.get(vk) if isinstance(lg.get(vk), dict) else (lg if key == "health" else {})
                mu, sd = (stat or {}).get("mean"), (stat or {}).get("sd")
                if z is None and v is not None and mu is not None and sd:
                    z = _r((float(v) - float(mu)) / float(sd), 2)
                prow.append([vk, vlabel, v, z, mu, sd])
            panels.append({"key": key, "label": plabel, "window": (org_tend.get("windows") or {}).get(wkey) if wkey else None,
                           "tags": [orow.get(k) for k in label_keys if orow.get(k)], "rows": prow})
        front_office = {
            "panels": panels,
            "similar": [[s.get("org"), s.get("score")] for s in ((tend_similar.get(c) or {}).get("similar") or [])[:5]],
            "verdict": verdict_of.get("org_tendencies"),
            "basis": "org_tendencies (descriptive league-relative profiles; windows differ per panel and print from the artifact)",
        }

        # -- DUGOUT (descriptive, gated) --------------------------------------------------------
        trows = sorted((r for r in mgmt_teams if _canon(r.get("team")) == c), key=lambda r: r.get("season") or 0)
        t26 = next((r for r in trows if r.get("season") == SEASON_NOW), None) or {}
        crow = next((r for r in mgmt_clubs if _canon(r.get("club")) == c and r.get("season") == SEASON_NOW), None) or {}
        fam_rows = [[fk, flabel, crow.get(f"n_{fk}"), crow.get(f"mwpa_{fk}")]
                    for fk, flabel in DUGOUT_FAMILIES if fk in live_fams] if crow else []
        dugout = {
            "style": {k: t26.get(k) for k in ("attempts", "success_rate", "share_2B", "share_3B", "mean_breakeven_faced")},
            "attempts_by_season": [[r.get("season"), r.get("attempts")] for r in trows],
            "realized": {"live": bool(crow), "season": crow.get("season"), "games": crow.get("games"),
                         "partial": crow.get("partial"), "agent": crow.get("agent"), "families": fam_rows,
                         "defensive_sub_n": crow.get("n_defensive_sub"),
                         "style_z": {k: crow.get(f"z_{k}") for k in ("hook", "pen", "bench", "ibb", "visit")}},
            "plus_metric": False, "letter": None,
            "basis": "management_board teams (style rows) and clubs (realized mWPA per family), both keyed on the canonical org; gate frozen, bounded null",
        }

        # -- ARBITRATION (descriptive) ----------------------------------------------------------
        arows = arb_rows_by.get(c) or []
        flags: Counter = Counter()
        for r in arows:
            e = int(r.get("e") or 0)
            for bit in (1, 2, 4, 8, 16):
                if e & bit:
                    flags[str(bit)] += 1
        s27 = 0.0
        w27 = 0.0
        alist = []
        for r in sorted(arows, key=lambda x: -(next((t[1] for t in (x.get("l") or []) if t[0] == CLASS_YEAR), 0) or 0)):
            l27 = next((t for t in (r.get("l") or []) if t[0] == CLASS_YEAR), None) or [None] * 5
            s27 += float(l27[1] or 0)
            w27 += float((r.get("w") or [0])[0] or 0)
            if len(alist) < 8:
                alist.append([r.get("n"), r.get("m"), l27[4], l27[1], l27[2], l27[3], (r.get("w") or [None])[0], r.get("c"), r.get("e")])
        hrows = hist_by.get(c) or []
        h26 = [r for r in hrows if r[0] == SEASON_NOW]
        # The split the artifact supports: class 1-4 rows against every row the
        # club carries (pre-arb class 0 included, at the minimum step). The class is
        # the one at the row's first remaining ladder season. The cost sums the
        # CLASS_YEAR tuple of every row, which equals /arbitration/ Team View's
        # CLASS_YEAR arbitration and pre-arb min. columns added together.
        n_arb = sum(1 for r in arows if int(r.get("c") or 0) >= 1)
        arbitration = {
            "n_rows": len(arows), "n_arb": n_arb, "n_pre_arb": len(arows) - n_arb,
            "proj_2027_usd": int(round(s27)), "proj_war_2027": _r(w27, 2),
            "flags": dict(flags), "rows": alist,
            "realized_2026": {"n": len(h26), "actual_usd": int(sum(r[5] or 0 for r in h26))},
            "ou_mkt_total_usd": int(sum(r[8] or 0 for r in hrows)),
            "ou_war_total_usd": int(sum(r[9] or 0 for r in hrows)),
            "verdict": verdict_of.get("arb_award"), "cba_banner": True,
            "basis": f"arbitration.json rows for the club, pre-arb rows included (arb_award provisional; cost is the sum of the {CLASS_YEAR} ladder steps incl. pre-arb minimums); arb_history by club",
        }

        # -- PARK (descriptive, never tiered) ---------------------------------------------------
        venue = venues.get(ident.get("venue_id")) or {}
        park_doc = {
            "factors": park.get(c), "short_window": (park_short.get("orgs") or {}).get(c),
            "by_hand": park_hand.get(c),
            "venue": {"name": ident.get("venue_name") or venue.get("name"), "capacity": venue.get("capacity"),
                      "roof": venue.get("roof"), "turf": venue.get("turf"), "elevation_ft": venue.get("elevation_ft"),
                      "azimuth": venue.get("azimuth"), "dims": venue.get("dims"), "city": venue.get("city"),
                      "state": venue.get("state")},
            "tiered": False,
            "basis": "fa_meta.park_factors (Baseball Savant, default 3-season view, 100 = neutral); venue plate from the StatsAPI venue cache",
        }

        # -- HISTORY (descriptive) ----------------------------------------------------------------
        srows = [[s, st[s].get("w"), st[s].get("l"), st[s].get("rd"), st[s].get("rank")] for s in sorted(st)]
        full = [r for r in srows if r[1] is not None and r[2] is not None and (r[1] + r[2]) >= 150]
        best = max(full, key=lambda r: r[1] / (r[1] + r[2])) if full else None
        worst = min(full, key=lambda r: r[1] / (r[1] + r[2])) if full else None
        history = {
            "standings": srows, "bwar": bwar.get(c) or [],
            "best": best, "worst": worst,
            "spine": (spine.get("orgs") or {}).get(c) or [],
            "hof": {"live": False, "blocked_on": hof_franchises.get("blocked_on") or "a frozen attribution rule for a multi-team career",
                    "why": hof_franchises.get("why")},
            "basis": f"StatsAPI standings {STANDINGS_FIRST}-{SEASON_NOW} by team id (no spine); club bWAR by season through franchise_spine.json from {SPINE_FIRST}",
        }

        # -- ODDS (descriptive; the verdict chip reads the playoff_odds_sim registry row) ----------
        odds = {
            "proj_wins": fut.get("projWins"), "p10": fut.get("winTotalP10"), "p90": fut.get("winTotalP90"),
            "record": fut.get("record"), "playoff_pct": fut.get("playoffPct"), "division_pct": fut.get("divisionPct"),
            "bye_pct": fut.get("byePct"), "pennant_pct": fut.get("pennantPct"), "ws_pct": fut.get("wsPct"),
            "pythag_pct": cur.get("pythagPct"), "actual_pct": cur.get("actualPct"),
            "sos": cur.get("sos"), "sos_rank": cur.get("sosRank"), "il_out_60": cur.get("ilOut60"),
            "registry_row": ODDS_REGISTRY_ID if odds_registered else None,
            "verdict": verdict_of.get(ODDS_REGISTRY_ID) if odds_registered else None,
            "basis": f"futures.json ({futures.get('sims')} sims) and the Team Outlook current overlay",
        }

        # -- the tree -------------------------------------------------------------------------------
        def leaf(key, label, value, kind, ladder=None, basis="", gl=None, link=None):
            return {"key": key, "label": label, "value": value, "kind": kind, "ladder": ladder,
                    "basis": basis, "gl": gl, "link": link}

        branches = [
            {"key": "roster", "kind": "graded", "label": "ROSTER", "title": BRANCH_TITLE["roster"],
             "weight": WEIGHTS["roster"], "score": s_roster[c], "rank": r_roster[c],
             "letter": letter_for_rank(r_roster[c]), "value": v_roster[c], "value_kind": "war",
             "basis": roster["basis"], "verdict": verdict_of.get("ewar"), "verdict_model": "ewar", "provisional": False,
             "leaves": [
                 leaf("war", "Team eWAR", wr.get("war"), "war", "rosterWar", "war_leaderboards.teams.war, current roster", "ewar", links["mlbstats_war"]),
                 # Each idx leaf takes the family /mlbstats/ paints the SAME key on
                 # (Offense+ ratio, Rotation+ z, Bullpen+ z, Team DEM+ z, Lev Deploy+ z);
                 # test_roster_leaf_ladders_are_the_family_mlbstats_applies reads the
                 # module's source, so a foreign scale cannot ship.
                 leaf("offense_plus", "Offense+", hr.get("offense_plus"), "idx", "ratio", "hitter_leaderboards.teams.offense_plus", "offense_plus", links["mlbstats_hitters"]),
                 leaf("rotation_plus", "Rotation+", sr.get("rotation_plus"), "idx", "z", "starter_leaderboards.teams.rotation_plus", "rotation_plus", links["mlbstats_starters"]),
                 leaf("bullpen_plus", "Bullpen+", pr.get("bullpen_plus"), "idx", "z", "bullpen_leaderboards.teams.bullpen_plus", "bullpen_plus", links["mlbstats_bullpen"]),
                 leaf("team_dem_plus", "Team DEM+", dr.get("team_dem_plus"), "idx", "z", "defense_leaderboards.teams.team_dem_plus", "dem_plus", links["mlbstats_defense"]),
                 leaf("leverage_deploy_plus", "Leverage deployment", pr.get("leverage_deploy_plus"), "idx", "z", "bullpen_leaderboards.teams.leverage_deploy_plus; deployment index, not skill", "leverage_deploy_plus", links["mlbstats_leverage"]),
             ]},
            {"key": "outlook", "kind": "graded", "label": "OUTLOOK", "title": BRANCH_TITLE["outlook"],
             "weight": WEIGHTS["outlook"], "score": s_outlook[c], "rank": r_outlook[c],
             "letter": letter_for_rank(r_outlook[c]), "value": v_outlook[c], "value_kind": "wins",
             "basis": outlook_doc["basis"], "verdict": verdict_of.get("team_win_projections"), "verdict_model": "team_win_projections", "provisional": True,
             "leaves": [
                 leaf("wins_2027", f"Wins {CLASS_YEAR}", out.get("wins"), "num1", None, "team_outlook.wins, provisional", None, links["team_outlook"]),
                 leaf("war_2027", f"Roster WAR {CLASS_YEAR}", out.get("war"), "war", None, "team_outlook.war", "ewar", links["roster_board"]),
                 leaf("locked_pct", "Core under control", out.get("lockedPct"), "pct", None, "team_outlook.lockedPct: share of 2027-31 core WAR under club control", "locked_pct", links["roster_board"]),
                 leaf("ctrl_war_5y", "Controlled WAR, 5y", out.get("ctrlWar5y"), "war", None, "team_outlook.ctrlWar5y", "ewar", links["roster_board"]),
             ] + [leaf(f"wins_{y[0]}", f"Wins {y[0]}", y[1], "num1", None, "team_outlook.byYear", None, links["team_outlook"])
                  for y in by_year if y[0] and y[0] != CLASS_YEAR]},
            {"key": "farm", "kind": "graded", "label": "FARM", "title": BRANCH_TITLE["farm"],
             "weight": WEIGHTS["farm"], "score": s_farm[c], "rank": farm_rank[c],
             "letter": farm_letter[c], "value": v_farm[c], "value_kind": "farm_score",
             "basis": farm_doc["basis"], "verdict": verdict_of.get("farm_grades"), "verdict_model": "farm_grades", "provisional": False,
             "leaves": [
                 leaf("acq", "ACQ (acquisition)", os_.get("acquisition_strategy_score"), "idx", "z", f"PROSPX letter {grades.get('acquisition_strategy')}, rank {cranks.get('acquisition_strategy')}", None, links["farm"]),
                 leaf("dev", "DEV (development)", os_.get("development_score"), "idx", "z", f"PROSPX letter {grades.get('development')}, rank {cranks.get('development')}", None, links["farm"]),
                 leaf("fin", "FIN (OrgSur+)", os_.get("financial_score"), "idx", "z", f"PROSPX letter {grades.get('financial')}, rank {cranks.get('financial')}; descriptive index, org_sur_plus unvalidated", "sur_plus", links["farm"]),
                 leaf("prod", "PROD (MLB production)", os_.get("mlb_production_score"), "idx", "z", f"PROSPX letter {grades.get('mlb_production')}, rank {cranks.get('mlb_production')}", None, links["farm"]),
                 leaf("farm_surplus_mm", "Farm surplus", farm_doc["farm_surplus_mm"], "usdm", None, "team_outlook.farm.farmSurplusMM, a sum of expected values", "surplus_value", links["farm"]),
                 leaf("health_burden", "Health burden", farm_doc["health_burden"], "num1", None, "org_summary.health_burden.score", None, links["farm"]),
             ]},
            {"key": "season", "kind": "descriptive", "label": "SEASON", "title": BRANCH_TITLE["season"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"{season['wins']}-{season['losses']}" if season["wins"] is not None else None),
             "basis": season["basis"], "verdict": None, "verdict_model": None,
             "leaves": [
                 leaf("wins", f"Wins {SEASON_NOW}", season["wins"], "count", None, f"standings {SEASON_NOW}, {season['games']} games", "season_record", links["betting_teams"]),
                 leaf("run_diff", "Run differential", season["run_diff"], "signed", None, "standings runDifferential", None, links["betting_teams"]),
                 leaf("division_rank", "Division rank", season["division_rank"], "count", None, "standings divisionRank", None, links["betting_teams"]),
                 leaf("pythag_pct", "Pythag pct", season["pythag_pct"], "pct3", None, "Team Outlook current overlay, blended", "pythag_pct", links["team_outlook"]),
             ]},
            {"key": "fin", "kind": "descriptive", "label": "FIN", "title": BRANCH_TITLE["fin"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"Cost+ {fin_doc['cost_plus']}" if fin_doc["cost_plus"] is not None else None),
             "basis": fin_doc["basis"], "verdict": None, "verdict_model": None,
             "leaves": [
                 leaf("cost_plus", "Cost+", fin_doc["cost_plus"], "idx_plain", None, "Club Ledger Cost+, descriptive index, printed plain here and tiered only on /ledger/", "cost_plus", links["ledger"]),
                 leaf("space_2027", f"Space {CLASS_YEAR}", (fin_doc["space_2027"] or {}).get("spotrac_usd"), "usd_signed", None, "Spotrac basis; never a ladder", "cbt_space", links["ledger"]),
                 leaf("tax_payroll_2027", f"Tax payroll {CLASS_YEAR}", fin_doc["tax_payroll_2027"], "usd", None,
                      "fa_meta.teams.taxPayroll (Spotrac)" + ("; below this club's own guaranteed 2027 contract AAV (Club Ledger tax floor census)"
                                                              if (fin_doc["tax_floor_2027"] or {}).get("below") else ""),
                      "cbt_payroll", links["ledger"]),
                 leaf("payor_2027", "Payor tier", (fin_doc["payor_2027"] or {}).get("value"), "text", None, "Spotrac or derived, named on the tile", "payor_tier", links["ledger"]),
                 leaf("roster_surplus_ev", "Trade currency (overlaps farm)", fin_doc["roster_surplus_ev"]["total_mm"], "usdm", None, "Trade Machine currency: sum of trade_values posterior means over prospect and debuted rows; contains the farm surplus, never added to it", "trade_machine", links["trade_board"]),
             ]},
            {"key": "market", "kind": "descriptive", "label": "MARKET", "title": BRANCH_TITLE["market"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"{len(outgoing)} outgoing" if outgoing is not None else None),
             "basis": market["basis"], "verdict": verdict_of.get("fa_team_fit"), "verdict_model": "fa_team_fit",
             "leaves": [
                 leaf("n_fits", "Top fits", len(fit_rows), "count", None, "fa_class.teamFits", "team_fit", links["fa_fits"]),
                 leaf("n_outgoing", "Outgoing free agents", len(outgoing), "count", None, "fa_class.members from this club", None, links["fa_fits"]),
                 leaf("recent_spend", "Recent spend, 3 winters", meta.get("recentSpend"), "usd", None, "fa_meta.teams.recentSpend", None, links["fa_archive"]),
                 leaf("realized_surplus_td", "Realized surplus to date", tot["surplus_td"], "usd_signed", None, "fa_archive surplusTd summed by signing club; realized value, not skill", "realized_contract_value", links["fa_archive"]),
             ]},
            {"key": "front_office", "kind": "descriptive", "label": "FRONT OFFICE", "title": BRANCH_TITLE["front_office"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": next((t for p in panels for t in p["tags"]), None),
             "basis": front_office["basis"], "verdict": verdict_of.get("org_tendencies"), "verdict_model": "org_tendencies",
             "leaves": [leaf(p["key"], p["label"], (p["tags"][0] if p["tags"] else None), "text", None,
                             f"org_tendencies.{p['key']}" + (f", window {p['window']}" if p["window"] else ""), "org_tendencies", links["tendencies"])
                        for p in panels]},
            {"key": "dugout", "kind": "descriptive", "label": "DUGOUT", "title": BRANCH_TITLE["dugout"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"{t26.get('attempts')} attempts" if t26.get("attempts") is not None else None),
             "basis": dugout["basis"], "verdict": verdict_of.get("mgmt_decision_ledger"), "verdict_model": "mgmt_decision_ledger",
             "leaves": [
                 leaf("attempts", f"Steal attempts {SEASON_NOW}", t26.get("attempts"), "count", None, "management_board.teams.rows", "steal_break_even", links["management_club"]),
                 leaf("success_rate", "Success rate", t26.get("success_rate"), "pct", None, "management_board.teams.rows", None, links["management_club"]),
             ] + [leaf(f"mwpa_{fk}", f"{fl}, realized", crow.get(f"mwpa_{fk}"), "signed2", None, "realized mWPA, club-season, never summed across families", "realized_mwpa", links["management_club"])
                  for fk, fl in DUGOUT_FAMILIES if crow]},
            {"key": "arbitration", "kind": "descriptive", "label": "ARBITRATION", "title": BRANCH_TITLE["arbitration"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"{arbitration['n_arb']} arb of {arbitration['n_rows']} rows" if arows else None),
             "basis": arbitration["basis"], "verdict": verdict_of.get("arb_award"), "verdict_model": "arb_award",
             "leaves": [
                 leaf("n_arb", "Arbitration class 1-4", arbitration["n_arb"], "count", None, "arbitration.json rows whose first remaining ladder season is class 1-4 (not all of them are arbitration-eligible in " + str(CLASS_YEAR) + "); pre-arb (class 0) rows are counted apart as n_pre_arb, all rows as n_rows", None, links["arbitration_teams"]),
                 leaf("proj_2027_usd", f"Projected {CLASS_YEAR} cost", arbitration["proj_2027_usd"], "usd", None, f"sum of the {CLASS_YEAR} ladder steps incl. pre-arb minimums; provisional; upper bound, not a payroll forecast", "arb_exposure", links["arbitration_teams"]),
                 leaf("proj_war_2027", "Projected eWAR of the class", arbitration["proj_war_2027"], "war", None, "arbitration.json w", "ewar", links["arbitration_teams"]),
                 leaf("ou_mkt_total_usd", "ou_mkt, all seasons", arbitration["ou_mkt_total_usd"], "usd_signed", None, "arb_history ou_mkt; never combined with ou_war", None, links["arbitration_history"]),
                 leaf("ou_war_total_usd", "ou_war, all seasons", arbitration["ou_war_total_usd"], "usd_signed", None, "arb_history ou_war; never combined with ou_mkt", None, links["arbitration_history"]),
             ]},
            {"key": "park", "kind": "descriptive", "label": "PARK", "title": BRANCH_TITLE["park"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"runs {park_doc['factors']['runs']}" if park_doc["factors"] else
                          (f"runs {park_doc['short_window']['runs']} (short)" if park_doc["short_window"] else None)),
             "basis": park_doc["basis"], "verdict": None, "verdict_model": None,
             "leaves": [
                 leaf("pf_runs", "Park factor, runs", (park_doc["factors"] or park_doc["short_window"] or {}).get("runs"), "plain", None, "100 = neutral; not tiered", "park_factor", links["parks"]),
                 leaf("pf_woba", "Park factor, wOBA", (park_doc["factors"] or park_doc["short_window"] or {}).get("woba"), "plain", None, "100 = neutral; not tiered", "park_factor", links["parks"]),
                 leaf("pf_hr", "Park factor, HR", (park_doc["factors"] or park_doc["short_window"] or {}).get("hr"), "plain", None, "100 = neutral; not tiered", "park_factor", links["parks"]),
                 leaf("capacity", "Capacity", venue.get("capacity"), "count", None, "StatsAPI venue cache", None, links["parks"]),
             ]},
            {"key": "history", "kind": "descriptive", "label": "HISTORY", "title": BRANCH_TITLE["history"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"best {best[0]}: {best[1]}-{best[2]}" if best else None),
             "basis": history["basis"], "verdict": None, "verdict_model": None,
             "leaves": [
                 leaf("best_season", "Best season since 2000", (f"{best[0]} ({best[1]}-{best[2]})" if best else None), "text", None, "StatsAPI standings", "season_record", links["hof"]),
                 leaf("worst_season", "Worst season since 2000", (f"{worst[0]} ({worst[1]}-{worst[2]})" if worst else None), "text", None, "StatsAPI standings", "season_record", links["hof"]),
                 leaf("bwar_last", f"Club bWAR {SEASON_NOW}", (bwar.get(c) or [[None, None]])[-1][1], "war", None, "war_daily through the spine; bWAR basis", None, links["hof"]),
                 leaf("hof", "Hall of Fame plaques", None, "dark", None, history["hof"]["blocked_on"], "jaws", links["hof"]),
             ]},
            {"key": "odds", "kind": "descriptive", "label": "ODDS", "title": BRANCH_TITLE["odds"],
             "weight": None, "score": None, "rank": None, "letter": None,
             "headline": (f"playoffs {round(100 * fut['playoffPct'])}%" if fut.get("playoffPct") is not None else None),
             "basis": odds["basis"], "verdict": odds["verdict"], "verdict_model": odds["registry_row"],
             "leaves": [
                 leaf("proj_wins", f"Projected wins {SEASON_NOW}", fut.get("projWins"), "num1", None, "futures.projWins with the P10-P90 band", None, links["betting_futures"]),
                 leaf("playoff_pct", "Playoff pct", fut.get("playoffPct"), "pct", None, "futures.playoffPct", None, links["betting_futures"]),
                 leaf("division_pct", "Division pct", fut.get("divisionPct"), "pct", None, "futures.divisionPct", None, links["betting_futures"]),
                 leaf("pennant_pct", "Pennant pct", fut.get("pennantPct"), "pct", None, "futures.pennantPct", None, links["betting_futures"]),
                 leaf("ws_pct", "World Series pct", fut.get("wsPct"), "pct", None, "futures.wsPct", None, links["betting_futures"]),
             ]},
        ]
        assert [b["key"] for b in branches] == list(BRANCH_ORDER)

        club_docs.append({
            "code": c, "statsapi_code": sapi, "name": ident["name"], "division": ident["division"],
            "league": ident["league"], "mlbam_id": ident["mlbam_id"], "logo": ident["logo"],
            "venue": ident.get("venue_name"), "first_year": ident.get("first_year"),
            "index": {"score": s_index[c], "rank": r_index[c], "letter": letter_for_rank(r_index[c]),
                      "raw_weighted_mean": raw_index[c]},
            "tree": {"branches": branches},
            "sections": {"roster": roster, "season": season, "outlook": outlook_doc, "farm": farm_doc, "fin": fin_doc,
                         "market": market, "front_office": front_office, "dugout": dugout,
                         "arbitration": arbitration, "park": park_doc, "history": history, "odds": odds},
            "links": links,
        })

    # ---- the board ---------------------------------------------------------------------------
    board = []
    for d in club_docs:
        s = d["sections"]
        board.append({
            "code": d["code"], "name": d["name"], "statsapi_code": d["statsapi_code"],
            "index_score": d["index"]["score"], "index_rank": d["index"]["rank"], "index_letter": d["index"]["letter"],
            "roster_score": d["tree"]["branches"][0]["score"], "outlook_score": d["tree"]["branches"][1]["score"],
            "farm_score": d["tree"]["branches"][2]["score"], "farm_letter": s["farm"]["letter"], "farm_rank": s["farm"]["rank"],
            "cost_plus": s["fin"]["cost_plus"], "wins_2027": s["outlook"]["wins"], "war": s["roster"]["war"],
            "tax_payroll_2027": s["fin"]["tax_payroll_2027"], "playoff_pct": s["odds"]["playoff_pct"],
            "tax_floor_below_2027": bool((s["fin"]["tax_floor_2027"] or {}).get("below")),
            "wins_2026": s["season"]["wins"], "losses_2026": s["season"]["losses"],
        })

    # ---- copy: every sentence the page prints, once ------------------------------------------------
    cba_expiry = "2026-12-01"
    copy = {
        "masthead": ("One page per club, re-serving what every module already publishes on the scale it was "
                     "computed on, each number labelled and linked back to the module that owns it."),
        "root_sentence": ("Re-standardised across 30 clubs: a weighted rank of realized standing and one provisional "
                          "projection, not a forecast of anything else. Thirty percent of the index rests on a "
                          "provisional projection (team_win_projections)."),
        "root_eyebrow": "Franchise Report Card",
        "root_foot_descriptive": "descriptive branches carry no weight",
        "weights_note": ("ROSTER and OUTLOOK are correlated: 2027 wins are the current roster rolled forward, so "
                         "one roster is counted twice by design; the weights are declared in the payload and never "
                         "redistributed at runtime."),
        "score_basis": ("branch score = 100 + 10z of the served value across the 30 clubs (population sd); the "
                        "Franchise Index is the weighted mean of the three branch scores re-standardised to "
                        "100 + 10z before any rank or letter is taken from it"),
        "letter_note": "letters follow rank across 30 clubs (storage._letter_grade); the score alone takes a tier colour",
        "farm_score_note": "score re-standardised across 30 clubs; letter is the PROSPX letter",
        "outlook_chip": "provisional",
        "outlook_note": (f"a provisional projection (team_win_projections): projected {CLASS_YEAR} wins from the current "
                         f"roster rolled forward; no interval is served for {CLASS_YEAR}, the {SEASON_NOW} win-total band "
                         "lives under ODDS"),
        "outlook_accounting": (f"league sum pinned to {target_wins} wins; replacement {replacement_wins} wins per club, "
                               f"derived from the {league_war_benchmark} WAR league benchmark in team_outlook_eval"),
        "roster_note": "current roster; the leaderboard team_basis names the day",
        "roster_basis_note": (team_basis.get("note") or ""),
        "leverage_deploy_note": "deployment index, not skill (leverage_consistency)",
        "season_note": "descriptive: the 2026 record is realized standing and carries no grade of its own",
        "pythag_label": "current overlay, blended",
        "cba_banner": (f"Every {CLASS_YEAR} figure is a 2022 CBA carry-forward: the agreement expires {cba_expiry} and "
                       f"no threshold, league minimum, arbitration structure or qualifying-offer value past it has "
                       f"been published."),
        "fin_headline_label": ("Cost+ (Club Ledger)" if ledger_live else f"space {CLASS_YEAR} (Spotrac, 247M basis)"),
        "fin_cost_plus_note": ((ledger.get("copy") or {}).get("cost_plus_basis") or "descriptive index: a ratio of two served numbers, not a model"),
        "fin_cost_plus_registry": ((ledger.get("copy") or {}).get("cost_plus_registry") or "no registry row: Cost+ predicts nothing"),
        "space_label_spotrac": (f"Spotrac, {spotrac_basis // 1_000_000}M basis" if spotrac_basis else "Spotrac basis"),
        "space_label_platform": (f"platform carry-forward, {cba.get('threshold_usd', 0) // 1_000_000}M" if cba.get("threshold_usd") else "platform carry-forward"),
        "fin_no_ladder": "a salary, a club surplus total and a cap-space cell never take a ladder; sign colour only",
        "surplus_ev": "a sum of posterior means (trade_values), never of quantiles",
        "tax_floor_flag": ((ledger.get("copy") or {}).get("tax_floor_flag") or "below own contracts"),
        "tax_floor_note": ((ledger.get("copy") or {}).get("tax_floor_note") or ""),
        "trade_currency_label": "Trade currency (overlaps farm)",
        "trade_currency_overlap": ((ledger.get("copy") or {}).get("trade_currency_split")
                                   or "the trade currency is the prospect rows plus the debuted rows; it overlaps the farm surplus and is never added to it"),
        "market_fits_note": "fit is a model of where a player signs, not of club quality (fa_team_fit provisional)",
        "market_realized_title": "Realized contract value to date",
        "market_realized_sentence": ("realized value, not skill: this is what the contracts returned, not how well the "
                                     "club chose them; the counterfactual, what the same dollars would have bought "
                                     "elsewhere that winter, is not observed, so no club is ranked by it"),
        "market_realized_coverage": ("covered signings carry the realized block; the current winter carries none "
                                     "because no season has elapsed"),
        "front_office_note": "descriptive league-relative behavioural profiles; no forward claims (org_tendencies)",
        "zbar_note": "z against the panel's league mean and sd; style, never a ladder",
        "dugout_sentence": _dugout_sentence(live_fams),
        "dugout_realized_tag": "realized",
        "dugout_agent": ((mgmt.get("clubs") or {}).get("agent_sentence") or "team-season"),
        "dugout_style": ((mgmt.get("clubs") or {}).get("style_sentence") or "style, not skill"),
        "dugout_not_summed": "per family, never a cross-family total; defensive subs carry a count only",
        "dugout_gate": ((mgmt.get("gate") or {}).get("verdict") or ""),
        "arb_upper_bound": "upper bound, not a payroll forecast: non-tenders and extensions are absent",
        "arb_flag_note": "steps not from published service time",
        "arb_cost_sum": f"sum of the {CLASS_YEAR} ladder steps incl. pre-arb minimums: the /arbitration/ Team View's {CLASS_YEAR} arbitration and pre-arb min. columns added together",
        "tile_open": "open",
        "arb_flag_key": (arb.get("field_key") or {}).get("e"),
        "ou_mkt": hist_fk.get("ou_mkt"), "ou_war": hist_fk.get("ou_war"), "never_combine": hist_fk.get("never_combine"),
        "park_source": park_short.get("source") or "Baseball Savant statcast park factors",
        "park_short_note": park_short.get("note") or "",
        "park_not_tiered": "100 = neutral; a hitter's park is not better, so nothing here takes a ladder",
        "park_attendance": "attendance is not served in v1 (owner decision D11)",
        "history_note": f"standings {STANDINGS_FIRST}-{SEASON_NOW} join by StatsAPI team id and need no spine; the bWAR line runs through franchise_spine.json",
        "history_pennants": "pennants and titles are not on disk as a served field; only clinched and divisionChamp for the cached season",
        "bwar_basis": "club bWAR by season, Baseball-Reference basis (war_daily), through the spine",
        "odds_interval": futures.get("what_the_intervals_are") or "",
        "odds_no_market": ((futures.get("no_market") or {}).get("what_is_missing") or ""),
        "odds_ledger": (f"no market captured; ledger has {((futures.get('ledger') or {}).get('n_entries'))} entries, "
                        f"{((futures.get('ledger') or {}).get('n_resolved'))} resolved"),
        "odds_win_total_basis": futures.get("win_total_basis") or "",
        "board_lede": "Thirty clubs on the Franchise Index, one column per graded branch and the headline descriptive figures; every row opens its club.",
        "board_foot": "index and branch scores are 100 + 10z across the 30 clubs and take the z ladder; every other column prints on its own scale, plain.",
        "load_error": "The Franchise Overview could not be loaded.",
        "tree_hidden": "Hide the tree; show only the root card",
        "tree_canopy": "Root and the twelve branches",
        "tree_full": "The full three-column tree with every leaf",
        "canopy_eyebrow": "Franchise Report Card . Composite Grade Tree",
        "canopy_right": "descriptive index . 30-club cohort",
        "dark_tag": "dark",
        "open_in": "Open in",
    }

    field_key = {
        "roster.lineup": "[tier, name, bats, hem_plus, pa, key]",
        "roster.rotation": "[role, name, sem_plus, ip, gs, key]",
        "roster.bullpen": "[role, name, rem_plus, gmli, ip, key]",
        "roster.alignment": "[pos, name, dem_plus, inn_at_pos, frm_runs, key]",
        "outlook.by_year": "[season, wins, war, depth_war, n]",
        "outlook.top": "[name, key, war]",
        "farm.history": "[snapshot_date, farm_score, letter]",
        "market.fits": "[name, key, pos, fit, need, afford, window]",
        "market.outgoing": "[name, key, pos, prev_aav_usd, proj_guar_usd, proj_guar_p10_usd, proj_guar_p90_usd, verdict]",
        "market.winters": "[winter, n_in, guar_in_usd, n_out, guar_out_usd]",
        "market.realized.by_winter": "[winter, n, n_covered, war_td, paid_td_usd, surplus_td_usd, n_complete]",
        "front_office.panels[].rows": "[key, label, value, z, league_mean, league_sd]",
        "front_office.similar": "[org, score]",
        "dugout.attempts_by_season": "[season, attempts]",
        "dugout.realized.families": "[family, label, n, realized_mwpa]; never summed across families",
        "arbitration.rows": "[name, mlbam, token_2027, proj_2027_usd, lo_usd, hi_usd, war_2027, class, flags]",
        "arbitration.n_rows | n_arb | n_pre_arb": "rows for the club incl. pre-arb | rows in arbitration class 1-4 | rows in class 0",
        "tree.branches[].leaves[].ladder": "z | ratio | run | rosterWar | null: the family /mlbstats/ paints the same key on, never a foreign scale",
        "history.standings": "[season, wins, losses, run_diff, division_rank]",
        "history.bwar": "[season, club_bwar]",
        "tree.branches[].leaves[].kind": "war | idx | idx_plain | pct | pct3 | count | usd | usd_signed | usdm | num1 | signed | signed2 | plain | text | dark",
    }

    sections_status = {
        "fin": {"live": True, "descriptive": True, "headline": copy["fin_headline_label"], "ledger_live": ledger_live},
        "market_realized": {"live": True, "method": "level_proration_backcast_dpw_v1",
                            "coverage_by_winter": [[w.get("year"), sum(1 for s in (w.get("signings") or []) if s.get("warTd") is not None),
                                                    len(w.get("signings") or [])] for w in winters]},
        "park_attendance": {"live": False, "blocked_on": "omitted in v1 by owner decision D11; a game-feed attendance ingest (2026 only) would light it"},
        "history_hof": {"live": False, "blocked_on": hof_franchises.get("blocked_on") or "a frozen attribution rule for a multi-team career",
                        "why": hof_franchises.get("why") or ("the season frame carries no team column and a frozen "
                                                              "multi-team attribution rule is required; the spine is "
                                                              "necessary but not sufficient")},
        "history_bwar": {"live": bool(bwar), "first_season": SPINE_FIRST,
                         "unmapped_team_ids": bwar_census.get("unmapped_team_ids")},
        "dugout_families": {"live": bool(mgmt_clubs), "blocked_on": None if mgmt_clubs else "management_board clubs block absent (D2 Wave A)"},
        "odds": {"registry_row": ODDS_REGISTRY_ID if odds_registered else None, "note": futures.get("what_the_intervals_are")},
        "arbitration_narrowing": {"live": arb_router_narrows,
                                  "note": ("arbitration.js accepts #teams&team=CODE" if arb_router_narrows
                                           else "arbitration.js accepts only #history, #teams and #model; the link is unnarrowed")},
        "manager_names": {"live": False, "blocked_on": "the manager entity (M-MWAR-2) is a network ingest not in this tree; rows say team-season"},
    }

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season_now": SEASON_NOW, "class_year": CLASS_YEAR,
        "basis": {"war_board": war.get("generated_at"), "hitters": hit.get("generated_at"), "starters": sta.get("generated_at"),
                  "bullpen": pen.get("generated_at"), "defense": dfn.get("generated_at"),
                  "projections": proj.get("generated_at"), "team_outlook_eval": proj_eval.get("generated_at"),
                  "timeseries": ts.get("generated_at"), "fa_meta": fa_meta.get("generated_at"),
                  "fa_class": fa_class.get("generated_at"), "fa_archive": fa_archive.get("generated_at"),
                  "org_tendencies": org_tend.get("generated_at"), "management": mgmt.get("generated_at"),
                  "arbitration": arb.get("generated_at"), "arb_history": arb_hist.get("generated_at"),
                  "futures": futures.get("generated_at"), "trade_values": tv.get("generated_at"),
                  "ledger": ledger.get("generated_at"), "standings": f"{STANDINGS_FIRST}-{SEASON_NOW} StatsAPI cache",
                  "war_daily": "B-Ref war_daily cache through franchise_spine.json", "venue_meta": "StatsAPI venue cache",
                  "spine": spine.get("generated_at")},
        "weights": dict(WEIGHTS),
        "graded": list(GRADED), "descriptive": list(DESCRIPTIVE), "branch_order": list(BRANCH_ORDER),
        "branch_labels": BRANCH_LABEL, "branch_titles": BRANCH_TITLE,
        "league": league,
        "clubs": club_docs,
        "codes": codes,
        "board": board,
        "board_default_sort": ["index_score", "desc"],
        "copy": copy,
        "field_key": field_key,
        "sections_status": sections_status,
        "accountability": {
            "registry_verdicts": registry_verdicts, "registry_checked_at": registry.get("checked_at"),
            "n_clubs": len(codes),
            "org_join": {"war_leaderboards": [len(war.get("teams") or []), len(war_rows)],
                         "team_outlook": [len(proj.get("team_outlook") or []), len(outlook)],
                         "org_summary": [len(ts.get("org_summary") or []), len(org_summary)],
                         "fa_meta": [len(fa_meta.get("teams") or {}), sum(1 for c in codes if c in (fa_meta.get("teams") or {}))],
                         "trade_values": [len(tv_orgs_in), len([o for o in tv_orgs_in if _canon(o) in clubs])],
                         "trade_values_dropped": tv_dropped,
                         "arb_history": [len(hist_teams_in), len({_canon(t) for t in hist_teams_in if _canon(t) in clubs})],
                         "management_teams": [len({r.get("team") for r in mgmt_teams}), len({_canon(r.get("team")) for r in mgmt_teams if _canon(r.get("team")) in clubs})],
                         "standings_ids": len(standings_ids), "futures": [len(futures.get("clubs") or []), len(futures_rows)],
                         "ledger": [len(ledger_clubs), sum(1 for c in codes if c in ledger_clubs)]},
            "bwar_census": bwar_census,
            "score_formula": "100 + 10 * (v - mean) / population sd over the 30 served values, one decimal; None stays None",
            "index_formula": "weighted mean of the three graded branch scores, re-standardised by the same formula",
        },
        "what_this_page_does_not_claim": [
            "a forecast: the Franchise Index is a descriptive rank of realized standing plus one provisional projection, re-standardised across 30 clubs",
            "revenue, operating income or a franchise valuation: no source in the tree carries them",
            "attendance before 2026, ticket prices, local or national TV money, revenue-sharing status: not sourced",
            "minor-league payroll, front-office salaries, actual CBT bills paid: not sourced",
            "pennants and titles as a served field: only clinched and divisionChamp for the cached season",
            "Hall of Fame plaques per franchise: hof_export needs a team column and a frozen attribution rule; the spine alone does not unblock it",
            "a per-game MLB park index over a home slate: the per-club park factor table is what is served (fa_meta.park_factors)",
            "defensive shifts, manager identity, any per-club decision-quality grade or manager skill claim",
            "a combined arbitration residual: ou_mkt and ou_war are two tiles and never one number",
            "a club payroll forecast: FIN is descriptive and quotes the Club Ledger, which serves none",
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
    assert len(doc["clubs"]) == N_CLUBS and len(doc["board"]) == N_CLUBS
    assert abs(sum(doc["weights"].values()) - 1.0) < 1e-9
    verdict_of = {r["model_id"]: r["verdict"] for r in doc["accountability"]["registry_verdicts"]}
    for d in doc["clubs"]:
        assert d["statsapi_code"], d["code"]
        graded = [b for b in d["tree"]["branches"] if b["kind"] == "graded"]
        assert [b["key"] for b in graded] == list(GRADED)
        for b in d["tree"]["branches"]:
            if b["kind"] == "descriptive":
                assert b["letter"] is None and b["score"] is None and not b["weight"], (d["code"], b["key"])
            if b.get("verdict_model"):
                assert b["verdict"] == verdict_of.get(b["verdict_model"]), (d["code"], b["key"])
            for lf in b["leaves"]:
                assert lf["basis"] and lf["kind"], (d["code"], b["key"], lf["key"])
        for blk in ("fin", "market", "arbitration"):
            assert d["sections"][blk].get("cba_banner") is True, (d["code"], blk)
        assert d["sections"]["odds"]["verdict"] == verdict_of.get(d["sections"]["odds"]["registry_row"]), d["code"]
        assert d["sections"]["dugout"]["plus_metric"] is False and d["sections"]["dugout"]["letter"] is None
    for path, k in _walk_keys(doc):
        ks = str(k).lower()
        assert ks not in FORBIDDEN_KEYS, path
        for frag in FORBIDDEN_KEY_FRAGMENTS:
            assert frag not in ks, path
        assert not ("ou_mkt" in ks and "ou_war" in ks), path
    txt = json.dumps(doc, ensure_ascii=False)
    assert chr(0x2014) not in txt and chr(0x2013) not in txt, "a banned dash reached the payload"


def main(argv=None) -> int:
    try:
        doc = build()
    except FranchiseRefusal as exc:
        print(f"REFUSED: {exc}; the previous {OUT.name} stands")
        return 2
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = OUT.stat().st_size
    print(f"wrote {OUT.name} ({n / 1e3:.0f} KB)")
    top = sorted(doc["clubs"], key=lambda d: d["index"]["rank"])[:3]
    for d in top:
        b = d["tree"]["branches"]
        print(f"  #{d['index']['rank']} {d['code']} index {d['index']['score']} ({d['index']['letter']}); "
              f"roster {b[0]['score']} outlook {b[1]['score']} farm {b[2]['score']}")
    print(f"  league: {doc['league']['scores']}")
    print(f"  dark: {sorted(k for k, v in doc['sections_status'].items() if v.get('live') is False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
