# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xM$ (Expected Market $) and Fair $ for every 40-man player and every board
prospect, with club roll-ups (task XM_2_EXPORT_ROLLUPS_DARK; owner decisions
XM-1 to XM-4 of 2026-10-19, gate docs/xm/XM_GATE.md).

Two files, data only (XM_EXPORT_ON True, XM_DISPLAY_ON False: no page reads
them yet):

  xm_players.json  one row per priced player, keyed by MLBAM id for a 40-man
                   player and by player key for a board prospect: xM$ term,
                   AAV and NPV guarantee with their P10 / P50 / P90, Fair $,
                   the counterfactual flag, the support-clip flag and the
                   per-player market-rate surplus over the priced control
                   seasons. A prospect row has Fair $ only (xm_withheld).
  xm_clubs.json    per club: (a) the 40-man xM$ AAV sum beside Spotrac's
                   payroll figures, (b) the market-rate surplus over control,
                   (c) the farm Fair $ total and (d) every Fair $ counterpart.
                   Every club figure is the sum of its listed player rows
                   (test_xm_export pins the identity).

THE MODEL. XM_1's read stopped in its one-time holdout step (exit 139, owner
question XM1-Q1) with no holdout number written; its development selection was
the incumbent. So xM$ is the served /fa/ market model, fa_market.MarketModel,
built exactly as fa_export builds it for the class board (same corpus, same
written $/WAR series, same class supply), and Fair $ is
fa_market.expected_rational_value_usd at the xM$ point term (a prospect's Fair $
is prospect_fair_usd, gate section 16). Nothing here
refits, re-weights or re-gates either; the gate's counterfactual extension
(section 11: the eFV prospect path, the training support box and its clip) is
the only new machinery.

POPULATIONS. A player in the 2027 free-agent class who is on a 40-man roster is
NOT re-priced: his row copies the /fa/ board (fa_class.json), so the two
surfaces cannot disagree, and he is the one non-counterfactual row. Every other
40-man player is priced as if he were a free agent this winter on his as-of
champion WAR path (fa_market.contract_war_path, use_ml False, the /fa/ input).
A board prospect (any player with no 2027 MLB WAR path and an eFV row) shows
Fair $ only (gate section 16, owner answer XM2B-Q1): the NPV of the served eFV
WAR path at this winter's market $/WAR, carried by the $/WAR index and
discounted at value_framework's rate (prospect_fair_usd), bust risk counted
once (the path already carries it); his xM$ is withheld as outside the market
model's range, which is fit on free agents, nearly all 29 or older.
Counterfactual rows carry no accuracy claim under any verdict (gate section 9).

CLUB ROLL-UPS (gate section 16, owner answer XM2-Q2). xm_clubs.json carries
the roster, market-rate surplus and farm blocks; the farm block holds every
board prospect and carries Fair $ only. club_blocks() hands the
Ledger the roster block (Spotrac's payroll on file beside it, labelled not a
payroll projection) and the farm block only, because a club surplus total is
on the Club Ledger never-list. The market-rate surplus goes to Franchise only,
and the Trade Machine sums it per side from the player rows.

Nothing here stratifies by consensus FV (docs/PROSPECT_ANCHOR_GATE.md); the
support-clip shares are reported by population only.
"""

from __future__ import annotations

import glob
import json
import logging
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
#: Data only: the two files are written to data/ and published; no page reads
#: them while XM_DISPLAY_ON is False.
XM_EXPORT_ON = True
#: The surfaces (cards, Ledger / Franchise club blocks, Trade Machine, FA /
#: Arbitration, board columns) stay dark until the owner flips this after the
#: gate (XM-4). ledger_export and franchise_export attach the club block only
#: when it is True.
XM_DISPLAY_ON = False

OUT_PLAYERS = DATA / "xm_players.json"
OUT_CLUBS = DATA / "xm_clubs.json"
#: Where the writer goes while XM_EXPORT_ON is False (resolved at call time so
#: the tests can redirect every path).
PREVIEW_DIR = ROOT / ".cache" / "xm" / "preview"

MODEL_ID = "fa_market"
FAIR_MODEL_ID = "fa_rational_value"
GATE_DOC = "docs/xm/XM_GATE.md"
SCHEMA = 1

#: Player-row columns (xm_players.json "columns"); money in USD.
COLUMNS = ["key", "name", "mlbam", "pop", "club", "bucket", "on40", "cf", "clip", "pos",
           "age", "years", "years_p10", "years_p90", "aav", "aav_p10", "aav_p90",
           "total", "total_p10", "total_p90", "fair", "ctrl", "ctrl_src",
           "msur_xm", "msur_fair", "arrive", "xm_withheld"]

CF_NOTE = "counterfactual: priced as if a free agent this winter"
#: Gate section 16 (owner answer XM2B-Q1): a prospect's xM$ is withheld, never
#: extrapolated; the market model is fit on free agents, nearly all 29 or older.
XM_WITHHELD_NOTE = "outside the market model's range"
CF_NOTE_PROSPECT = ("counterfactual: Fair $ only, the NPV of his eFV WAR path; xM$ withheld, "
                    + XM_WITHHELD_NOTE)
#: The money and term columns a withheld row leaves null.
XM_COLUMNS = ("years", "years_p10", "years_p90", "aav", "aav_p10", "aav_p90",
              "total", "total_p10", "total_p90")
#: What each consumer may show of a club's xm_clubs.json entry (owner answer
#: XM2-Q2): the Ledger never shows the market-rate surplus, a club surplus total
#: on the Club Ledger never-list.
SURFACE_BLOCKS = {"ledger": ("roster", "farm"),
                  "franchise": ("roster", "market_surplus", "farm")}
PAYROLL_NOTE = "not a payroll projection"

#: The 40-man roster files proj_export's statsapi read leaves in .cache.
ROSTER_GLOB = "statsapi_roster_40man_*_{season}.json"


# ============================================================================
# Small pure pieces (the gate's section 11 extension), unit-tested directly
# ============================================================================

#: Seasons in a prospect's eFV path (section 11), the class season first.
PROSPECT_PATH_YEARS = 15


def prospect_path(war_6yr: float, eta_season, age_in_winter: float,
                  winter: int, n_years: int = PROSPECT_PATH_YEARS) -> list:
    """Gate section 11: the expected six-season WAR (reach probability
    included) spread evenly over the six seasons from the ETA season, zero
    before it; the six-season level held until age 30, then walked down 0.5
    WAR a season (floored at 0). A missing or past ETA starts the path in the
    winter's season."""
    level = max(float(war_6yr or 0.0), 0.0) / 6.0
    eta = int(eta_season) if eta_season else int(winter)
    eta = max(eta, int(winter))
    out = []
    for t in range(n_years):
        season = int(winter) + t
        age = float(age_in_winter) + t
        if season < eta:
            out.append(0.0)
        elif season < eta + 6 or age <= 30:
            out.append(round(level, 4))
        else:
            out.append(round(max(0.0, level - 0.5 * (age - 30.0)), 4))
    return out


def arrival_year(eta_season, winter: int) -> int:
    """Gate section 16: the first season of a prospect's path, the ETA season
    and never before the winter's class year (a missing ETA takes the winter)."""
    return max(int(eta_season), int(winter)) if eta_season else int(winter)


def prospect_fair_usd(war_by_year: list, dpw_usd: float, index: list, disc: list) -> int:
    """Gate section 16 (owner answer XM2B-Q1): Fair $ for a prospect, the NPV
    of his eFV WAR path at the market rate,
        SUM_t WAR_t x dpw x index[t] x disc[t]   (t = 0 is the class season).
    Linear in WAR: the path is an expectation over outcomes (bust included),
    and value_framework's tier curve is never read on an averaged WAR. No
    reach weight: the path already carries the bust risk."""
    n = len(war_by_year)
    if len(index) < n or len(disc) < n:
        raise ValueError("prospect_fair_usd: index and discount must cover the path")
    return int(round(sum(float(w) * float(dpw_usd) * float(index[t]) * float(disc[t])
                         for t, w in enumerate(war_by_year))))


def support_box(train_rows: list) -> dict:
    """[min, max] of age, year-1 WAR and the whole-path WAR total over the
    market model's training rows (gate section 11)."""
    ages = [float(r["_age"]) for r in train_rows]
    y1 = [float(r["_war_path"]["war_y1"]) for r in train_rows]
    tot = [float(sum(r["_war_path"]["war_by_year"])) for r in train_rows]
    return {"age": [min(ages), max(ages)], "war_y1": [min(y1), max(y1)],
            "war_tot": [min(tot), max(tot)], "n": len(train_rows)}


def clip_to_support(age: float, war_by_year: list, box: dict) -> tuple:
    """Clip age into the box and scale the WAR path DOWN so year 1 and the
    total fall inside it. Returns (age, path, factor, outside). A path below
    the box's floor is flagged and left as it is (scaling a short path up would
    invent production)."""
    wy = [float(w) for w in war_by_year]
    out = False
    a = float(age)
    lo, hi = box["age"]
    if a < lo or a > hi:
        out = True
        a = min(max(a, lo), hi)
    y1, tot = (wy[0] if wy else 0.0), sum(wy)
    f = 1.0
    if y1 > box["war_y1"][1] and y1 > 0:
        f = min(f, box["war_y1"][1] / y1)
    if tot > box["war_tot"][1] and tot > 0:
        f = min(f, box["war_tot"][1] / tot)
    if f < 1.0:
        out = True
        wy = [w * f for w in wy]
    if y1 < box["war_y1"][0] or tot < box["war_tot"][0]:
        out = True
    return a, wy, f, out


def ordered_band(p10, p50, p90) -> tuple:
    """P10 <= P50 <= P90, enforced (a missing side takes the point)."""
    if p50 is None:
        return None, None, None
    lo = p50 if p10 is None else min(p10, p50)
    hi = p50 if p90 is None else max(p90, p50)
    return lo, p50, hi


def control_surplus(aav: float, salaries: list, fair_seasons: list | None,
                    index: list, disc: list) -> tuple:
    """Market-rate surplus over the priced control seasons (roll-up (b)).

    ``salaries[t]`` is the expected salary of control season t (t = 0 is the
    class season), ``index[t]`` the $/WAR index of that season relative to the
    class season, ``disc[t]`` its discount factor at the platform rate.
      xM$ leg  = sum_t (aav x index[t] - salary[t]) x disc[t]
      Fair leg = sum_t fair_seasons[t] - salary[t] x disc[t]
    (``fair_seasons[t]`` is already discounted: fa_market prices each season to
    the class year.) Integers, so a club total is an exact sum of rows."""
    xm = sum((aav * index[t] - salaries[t]) * disc[t] for t in range(len(salaries)))
    fair = None
    if fair_seasons is not None:
        fair = sum(fair_seasons[t] - salaries[t] * disc[t] for t in range(len(salaries)))
    return int(round(xm)), (int(round(fair)) if fair is not None else None)


# ============================================================================
# Inputs
# ============================================================================

def _j(name: str, data_dir: Path | None = None):
    p = (data_dir or DATA) / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_dir() -> Path:
    try:
        from scrapers import CACHE_DIR
        return Path(CACHE_DIR)
    except Exception:                                    # noqa: BLE001
        return ROOT / ".cache"


def roster_40man(season: int) -> tuple:
    """{mlbam: {"club", "pos", "status", "name"}} off the cached StatsAPI
    40-man roster files (cache only, never a socket), and the season read. Falls
    back to the season after when the season's files are absent."""
    from trades import canonical_org
    cdir = _cache_dir()
    teams = None
    for s in (season, season + 1):
        p = cdir / f"statsapi_teams_{s}.json"
        if p.is_file():
            try:
                teams = {int(t["id"]): canonical_org(t.get("name") or "")
                         for t in json.loads(p.read_text(encoding="utf-8")).get("teams") or []}
                break
            except (OSError, ValueError, KeyError, TypeError):
                teams = None
    for s in (season, season + 1):
        files = sorted(glob.glob(str(cdir / ROSTER_GLOB.format(season=s))))
        if not files:
            continue
        out = {}
        for f in files:
            tid = int(Path(f).stem.split("_")[-2])
            club = (teams or {}).get(tid)
            if not club or len(club) > 3:
                continue
            try:
                ros = json.loads(Path(f).read_text(encoding="utf-8")).get("roster") or []
            except (OSError, ValueError):
                continue
            for r in ros:
                pid = (r.get("person") or {}).get("id")
                if not pid:
                    continue
                out[int(pid)] = {"club": club,
                                 "pos": (r.get("position") or {}).get("abbreviation"),
                                 "ptype": (r.get("position") or {}).get("type"),
                                 "status": (r.get("status") or {}).get("code"),
                                 "name": (r.get("person") or {}).get("fullName")}
        return out, s
    return {}, None


def _season_age(age_now: float, as_of: date, class_year: int) -> int:
    """Season age in the class year (age on June 30) from an age read on
    ``as_of``."""
    days = (date(class_year, 6, 30) - as_of).days
    return int(math.floor(float(age_now) + days / 365.25))


class MarketContext:
    """The /fa/ market model and its pricing inputs, built as fa_export builds
    them for the class board (fa_export._build_fa_class_payload_body)."""

    def __init__(self, class_year: int):
        import fa_export
        import fa_market as fm
        import fa_projection as fp
        import storage
        self.class_year = W = int(class_year)
        corpus = fp.build_corpus()
        self.league = corpus["league"]
        self.curves, self.war_map = fp.fitted_models(corpus, W - 1)
        self.frac = fp.season_fraction(self.league, W - 1)
        by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
        for side in ("hit", "pit"):
            for r in corpus[side]:
                if r.get("mlbam"):
                    by_player[side][r["mlbam"]][r["season"]] = r
        self.by_player = by_player
        enriched = fm.enriched_signings(2015, W - 1)
        in_run = fm.dollars_per_war_by_winter(enriched)
        dpw_series = fm.written_dpw_series(through=W - 1)
        self.series_src = "data/fa_dpw_series.json"
        if not dpw_series:
            dpw_series, self.series_src = in_run, "in_run_fallback"
        self.model = fm.MarketModel(enriched, dpw_series)
        cls = list(storage.load_fa_class_players(W).values())
        if fm.X_FEATURES.get("supply_pop"):
            self.model.supply_by_year[W] = fm._supply(
                fa_export._class_supply_rows(cls, W, by_player), W)
        else:
            self.model.supply_by_year[W] = fm._supply(
                [{"class_year": W, "position": p.get("position")} for p in cls], W)
        self.dpw = ((fm.written_pricing_level_usd(W) if self.series_src != "in_run_fallback"
                     else None) or fm.winter_dpw(dpw_series, W))
        self.destale = fm._destale_rate(dpw_series, W)
        self.box = support_box(self.model.train_pool)

    def index_and_discount(self, n: int) -> tuple:
        """$/WAR index (relative to the class season) and discount factor for
        control seasons 0..n-1: the unified path's own levels and nominal rate
        when it serves, else the /fa/ carry (fa_market._destale_rate, the rate
        the class board carries dollars forward at) and value_framework's
        discount rate."""
        import fa_market as fm
        import value_framework as vf
        W = self.class_year
        if vf.dpw_path_active():
            p0 = vf.price_level(W)
            idx = [vf.price_level(W + t) / p0 for t in range(n)]
            r = vf.nominal_rate()
        else:
            idx = [(1.0 + self.destale) ** t for t in range(n)]
            r = fm._discount_rate()
        return idx, [(1.0 + r) ** -t for t in range(n)]

    def history(self, mlbam: int, side: str) -> list:
        W = self.class_year
        seasons = self.by_player[side].get(mlbam) or {}
        return [seasons[t] for t in (W - 1, W - 2, W - 3) if t in seasons]

    def age_from(self, hist: list, fallback) -> int | None:
        import fa_market as fm
        W = self.class_year
        if fm.X_FEATURES.get("age_anchor"):
            age_row = next((h for h in hist if h.get("age")), None)
            return (age_row["age"] + (W - age_row["season"])) if age_row else fallback
        age_prev = next((h.get("age") for h in hist if h.get("age")), None)
        return (age_prev + (W - hist[0]["season"])) if age_prev else fallback

    def mlb_path(self, hist: list, side: str, age: int) -> dict | None:
        import fa_market as fm
        W = self.class_year
        return fm.contract_war_path(hist, side, W, 10, age, self.curves, self.war_map,
                                    self.league, in_progress=(W - 1, self.frac),
                                    use_ml=False)

    def price(self, row: dict, path: dict, age: float) -> dict:
        """xM$ and Fair $ for one counterfactual row: the support clip, then
        MarketModel.predict and expected_rational_value_usd at the point term."""
        import fa_market as fm
        a2, wy2, f, outside = clip_to_support(age, path["war_by_year"], self.box)
        pth = dict(path)
        pth["war_by_year"] = [round(w, 4) for w in wy2]
        pth["war_y1"] = pth["war_by_year"][0] if wy2 else 0.0
        if f < 1.0:
            for k in ("war_by_year_p10", "war_by_year_p90"):
                if pth.get(k):
                    pth[k] = [w * f for w in pth[k]]
        s = {"player_key": row["key"], "player_name": row["name"],
             "position": row["pos"], "class_year": self.class_year, "qo": False,
             "mlbam_id": row.get("mlbam"), "_war_path": pth, "_age": int(round(a2))}
        pred = self.model.predict(s)
        yrs = int(pred["proj_years"])
        fair = int(fm.expected_rational_value_usd(pth, yrs, self.class_year, self.dpw,
                                                  infl=self.destale))
        return {"pred": pred, "path": pth, "clip": bool(outside), "fair": fair}

    def fair_seasons(self, path: dict, n: int) -> list:
        """Each season's discounted Fair $ (differences of the cumulative
        expected rational value, which is additive by season)."""
        import fa_market as fm
        cum = [0]
        for k in range(1, n + 1):
            cum.append(int(fm.expected_rational_value_usd(path, k, self.class_year, self.dpw,
                                                          infl=self.destale)))
        return [cum[k + 1] - cum[k] for k in range(n)]


# ============================================================================
# Build
# ============================================================================

def _row_from_pred(base: dict, pred: dict, fair: int, clip: bool, cf: bool) -> dict:
    y10, y50, y90 = ordered_band(pred.get("proj_years_p10"), pred["proj_years"],
                                 pred.get("proj_years_p90"))
    a10, a50, a90 = ordered_band(pred.get("proj_aav_p10_usd"), pred["proj_aav_usd"],
                                 pred.get("proj_aav_p90_usd"))
    g10, g50, g90 = ordered_band(pred.get("proj_guarantee_p10_usd"), pred["proj_guarantee_usd"],
                                 pred.get("proj_guarantee_p90_usd"))
    return {**base, "cf": cf, "clip": clip,
            "years": int(y50), "years_p10": int(y10), "years_p90": int(y90),
            "aav": int(a50), "aav_p10": int(a10), "aav_p90": int(a90),
            "total": int(g50), "total_p10": int(g10), "total_p90": int(g90),
            "fair": int(fair), "xm_withheld": False}


def _pitcher_pos(pos: str | None, role: str | None, ptype: str | None) -> str:
    """A generic pitcher code ('P', 'RHP', 'LHP') resolved to SP or RP off the
    projection's own role, so the market model groups him correctly."""
    head = (pos or "").upper().split("/")[0].strip()
    if head in ("SP", "RP"):
        return head
    if head in ("P", "LHP", "RHP") or (ptype or "").lower() == "pitcher":
        return "SP" if (role or "").upper() == "SP" else "RP"
    return pos or ""


def build(data_dir: Path | None = None, as_of: date | None = None) -> tuple:
    """(players_doc, clubs_doc). Reads served artifacts, the store and the
    cache; never a socket."""
    import fa_export
    import fa_market as fm
    import salary_path as spth
    data_dir = data_dir or DATA
    as_of = as_of or date.today()
    W = int(fa_export.CLASS_YEAR)
    ctx = MarketContext(W)

    tvd = _j("trade_values.json", data_dir) or {}
    tv_all = tvd.get("players") or []
    tv_by_mlbam = {int(p["mlbam_id"]): p for p in tv_all if p.get("mlbam_id")}
    tv_as_of = date.fromisoformat(str(tvd.get("generated_at") or as_of.isoformat())[:10])
    proj = _j("mlb_projections.json", data_dir) or {}
    vets = {int(v["mlbam"]): v for v in (proj.get("vets") or []) if v.get("mlbam")}
    ts = _j("timeseries.json", data_dir) or {}
    eta = {p.get("player_key"): (p.get("eta") or {}).get("year")
           for p in (ts.get("players") or []) if isinstance(p.get("eta"), dict)}
    board_keys = {p.get("player_key") for p in (ts.get("players") or []) if p.get("player_key")}
    fa_cls = _j("fa_class.json", data_dir) or {}
    fa_by_mlbam = {int(m["mlbam"]): m for m in (fa_cls.get("members") or []) if m.get("mlbam")}
    roster, roster_season = roster_40man(W - 1)
    if not roster:
        raise RuntimeError("xm_export: no cached 40-man roster files; nothing to price")

    rows: dict = {}
    unpriced: list = []
    counts = Counter()
    arrivals = Counter()          # prospects by arrival class year (gate section 16)

    # ---- 40-man players -----------------------------------------------------
    for mlbam, rs in sorted(roster.items()):
        tv = tv_by_mlbam.get(mlbam) or {}
        vet = vets.get(mlbam) or {}
        key = tv.get("player_key") or vet.get("key") or f"mlbam_{mlbam}"
        name = vet.get("name") or tv.get("player_name") or rs.get("name")
        base = {"key": key, "name": name, "mlbam": mlbam, "club": rs["club"], "on40": True}
        fa = fa_by_mlbam.get(mlbam)
        if fa is not None:
            if not fa.get("projAav"):
                unpriced.append({"id": str(mlbam), **base, "pop": "fa", "why": "fa_unprojected"})
                counts["fa_unprojected"] += 1
                continue
            pred = {"proj_years": fa["projYears"], "proj_years_p10": fa.get("projYearsP10"),
                    "proj_years_p90": fa.get("projYearsP90"),
                    "proj_aav_usd": fa["projAav"], "proj_aav_p10_usd": fa.get("projAavP10"),
                    "proj_aav_p90_usd": fa.get("projAavP90"),
                    "proj_guarantee_usd": fa["projGuar"],
                    "proj_guarantee_p10_usd": fa.get("projGuarP10"),
                    "proj_guarantee_p90_usd": fa.get("projGuarP90")}
            r = _row_from_pred({**base, "pop": "fa", "bucket": "fa",
                                "pos": fa.get("pos") or vet.get("pos"),
                                "age": fa.get("age")}, pred, fa.get("rational") or 0,
                               False, False)
            r.update(ctrl=0, ctrl_src="free_agent", msur_xm=None, msur_fair=None)
            rows[str(mlbam)] = r
            counts["fa"] += 1
            continue
        pos0 = vet.get("pos") or tv.get("position") or rs.get("pos")
        side = ("pit" if (fm._pos_group(pos0) in ("SP", "RP")
                          or (rs.get("ptype") or "").lower() == "pitcher") and pos0 != "TWP"
                else "hit")
        hist = ctx.history(mlbam, side)
        if not hist:
            if tv.get("status") == "active" and tv.get("player_key") in board_keys:
                counts["on40_prospect"] += 1
                continue                      # priced below as a board prospect, on40 kept
            unpriced.append({"id": str(mlbam), **base, "pop": "mlb", "why": "no_mlb_history"})
            counts["no_mlb_history"] += 1
            continue
        age = ctx.age_from(hist, int(round(float(tv["age"]))) if tv.get("age") else None)
        path = ctx.mlb_path(hist, side, age) if age is not None else None
        if path is None:
            unpriced.append({"id": str(mlbam), **base, "pop": "mlb", "why": "no_path"})
            counts["no_path"] += 1
            continue
        pos = _pitcher_pos(pos0, path.get("role"), rs.get("ptype")) if side == "pit" else pos0
        base.update(pop="mlb", pos=pos, age=int(age))
        pr = ctx.price(base, path, age)
        r = _row_from_pred(base, pr["pred"], pr["fair"], pr["clip"], True)
        # control seasons and expected salary: the served salary path where
        # proj_export priced one (contract, arbitration ladder or the minimum);
        # a pre-arbitration player off that board at the league minimum for his
        # remaining pre-arbitration seasons; anything else is not summed.
        sal, src = None, None
        sp = vet.get("salPath")
        ctrl_thru = vet.get("ctrlThru")
        if vet and vet.get("salSrc") == "pending":
            src = "pending_free_agent"
        elif sp and ctrl_thru:
            cells = sorted((c for c in sp if W <= int(c[0]) <= int(ctrl_thru) and c[1] is not None),
                           key=lambda c: c[0])
            seasons = [int(c[0]) for c in cells]
            if cells and seasons == list(range(W, W + len(cells))):
                sal, src = [float(c[1]) for c in cells], "salary_path"
            else:
                src = "salary_path_gap"
        elif not vet:
            cr = tv.get("crunch") or {}
            sy = cr.get("service_years")
            if cr.get("service_phase") == "pre_arb" and sy is not None:
                n = max(1, 3 - int(sy))
                sal, src = [float(spth.league_min_usd(W + t)) for t in range(n)], "prearb_minimum"
            else:
                src = "no_salary_path"
        else:
            src = "no_salary_path"
        r["bucket"] = "roster"
        if sal:
            idx, disc = ctx.index_and_discount(len(sal))
            fs = ctx.fair_seasons(pr["path"], len(sal))
            mx, mf = control_surplus(r["aav"], sal, fs, idx, disc)
            r.update(ctrl=len(sal), ctrl_src=src, msur_xm=mx, msur_fair=mf)
        else:
            r.update(ctrl=0, ctrl_src=src, msur_xm=None, msur_fair=None)
            if src == "pending_free_agent":
                r["bucket"] = "fa"
        counts[f"mlb_{src}"] += 1
        rows[str(mlbam)] = r

    # ---- board prospects ------------------------------------------------------
    p_idx, p_disc = ctx.index_and_discount(PROSPECT_PATH_YEARS)
    for p in tv_all:
        if p.get("status") != "active" or p.get("player_key") not in board_keys:
            continue
        key = p["player_key"]
        mlbam = int(p["mlbam_id"]) if p.get("mlbam_id") else None
        if mlbam is not None and str(mlbam) in rows:
            continue
        rs = roster.get(mlbam) if mlbam is not None else None
        base = {"key": key, "name": p.get("player_name"), "mlbam": mlbam,
                "club": (rs or {}).get("club") or p.get("org"), "on40": bool(rs),
                "pop": "prospect"}
        if p.get("age") is None or p.get("xfv_war_6yr") is None:
            unpriced.append({"id": key, **base, "why": "no_age" if p.get("age") is None
                             else "no_efv_war"})
            counts["prospect_unpriced"] += 1
            continue
        age = _season_age(p["age"], tv_as_of, W)
        pos0 = p.get("position")
        # Gate section 16 (owner answer XM2B-Q1): Fair $ only, the NPV of the
        # served eFV WAR path (section 11 shape, from the class season) at the
        # market rate; no reach weight (the path carries the bust risk); xM$
        # withheld, outside the market model's range. Nothing is passed to the
        # market model, so no support clip applies.
        arrive = arrival_year(eta.get(key), W)
        wy = prospect_path(p["xfv_war_6yr"], arrive, age, W)
        base.update(pos=pos0, age=age)
        r = {**base, "cf": True, "clip": False, "xm_withheld": True,
             **{c: None for c in XM_COLUMNS},
             "fair": prospect_fair_usd(wy, ctx.dpw, p_idx, p_disc), "arrive": arrive}
        arrivals[arrive] += 1
        # Every board prospect, on a 40-man or not, sits in the farm block; his
        # service clock has not started, so no control season is priced.
        r["bucket"] = "farm"
        r.update(ctrl=0, ctrl_src=("no_service_clock" if rs else None),
                 msur_xm=None, msur_fair=None)
        rows[key] = r
        counts["prospect_on40" if rs else "prospect"] += 1

    inputs = {"trade_values": tvd.get("generated_at"), "mlb_projections": proj.get("generated_at"),
              "timeseries": ts.get("generated_at"), "fa_class": fa_cls.get("generated_at")}
    return _assemble(rows, unpriced, counts, ctx, roster_season, as_of, W, inputs,
                     arrivals=arrivals, gate_eval=_j("xm_eval.json", data_dir))


def _sum(vals) -> int:
    return int(sum(int(v) for v in vals))


def _gate_status(gate_eval: dict | None) -> tuple:
    """(status, verdict) off the gate's eval artifact (data/xm_eval.json), so
    the export never restates a verdict by hand."""
    ho = (gate_eval or {}).get("holdout") or {}
    verdict = ho.get("verdict")
    if not verdict:
        return "no holdout verdict on file in the gate's eval artifact", None
    return (f"XM_1 read once (holdout resumed once, owner answer XM1-Q1): verdict {verdict}, "
            f"served model {ho.get('served_model')}, registry {ho.get('registry_verdict')} "
            f"({ho.get('provisional_kind')})", verdict)


def _assemble(rows: dict, unpriced: list, counts: Counter, ctx, roster_season,
              as_of: date, W: int, inputs: dict | None = None, arrivals: Counter | None = None,
              gate_eval: dict | None = None) -> tuple:
    import ledger_export
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status, verdict = _gate_status(gate_eval)
    by_pop = defaultdict(list)
    for r in rows.values():
        by_pop[r["pop"]].append(r)
    # Only rows the market model priced (a prospect's xM$ is withheld, gate
    # section 16, so he is never clipped).
    clip_share = {pop: {"n": len(rs), "outside_support": sum(1 for r in rs if r["clip"]),
                        "share": round(sum(1 for r in rs if r["clip"]) / len(rs), 4) if rs else None}
                  for pop, rs in sorted(by_pop.items())
                  if not all(r.get("xm_withheld") for r in rs)}
    meta = {
        "schema": SCHEMA, "as_of": as_of.isoformat(), "generated_at": generated_at,
        "class_year": W, "model_id": MODEL_ID, "fair_model_id": FAIR_MODEL_ID,
        "gate": {"doc": GATE_DOC, "eval_artifact": "data/xm_eval.json", "status": status,
                 "verdict": verdict},
        "display_on": XM_DISPLAY_ON,
        "inputs_generated_at": dict(inputs or {}),
        "pricing": {"dpw_usd": int(ctx.dpw), "dpw_series_source": ctx.series_src,
                    "carry_rate": round(ctx.destale, 6),
                    "discount_rate": round((1.0 / ctx.index_and_discount(2)[1][1]) - 1.0, 6),
                    "support_box": ctx.box},
    }
    cols = COLUMNS
    players_doc = {
        **meta,
        "what": ("xM$ is what the free-agent market would pay this winter: years, AAV and the NPV "
                 "guarantee, each with P10 and P90. Fair $ is what the projected production is "
                 "worth at the same term. The two are separate numbers and are never subtracted. "
                 "A board prospect shows Fair $ only, the NPV of his eFV WAR path; his xM$ is "
                 "withheld (" + XM_WITHHELD_NOTE + ")."),
        "counterfactual_note": CF_NOTE,
        "counterfactual_note_prospect": CF_NOTE_PROSPECT,
        "prospect_pricing": {
            "rule": ("gate section 16 (owner answer XM2B-Q1): Fair $ only, SUM over the "
                     f"{PROSPECT_PATH_YEARS} seasons from the class year of eFV WAR_t x the "
                     "winter's market $/WAR x the $/WAR index I(t) x (1 + r)^-t; the path is the "
                     "section 11 eFV path (xfv_war_6yr spread over six seasons from the ETA "
                     "season, zero before it); bust risk counted once (no reach weight); xM$ "
                     "withheld"),
            "xm_withheld_note": XM_WITHHELD_NOTE,
            "by_arrival_year": {str(k): v for k, v in sorted((arrivals or {}).items())},
        },
        "roster_season": roster_season,
        "columns": cols,
        "n": len(rows),
        "counts": dict(sorted(counts.items())),
        "support_clip_by_population": clip_share,
        "players": {k: [r.get(c) for c in cols] for k, r in sorted(rows.items())},
        "unpriced": sorted(unpriced, key=lambda u: (u.get("club") or "", u["id"])),
    }

    payroll, _av, _join = ledger_export._payroll_rows()
    clubs = sorted({r["club"] for r in rows.values() if r.get("club")}
                   | {c for (c, s) in payroll if s == W - 1})
    club_docs = {}
    for c in clubs:
        mine = [(k, r) for k, r in sorted(rows.items()) if r.get("club") == c]
        ros = [(k, r) for k, r in mine if r["bucket"] == "roster"]
        farm = [(k, r) for k, r in mine if r["bucket"] == "farm"]
        surp = [(k, r) for k, r in ros if r.get("msur_xm") is not None]
        excl = Counter(r.get("ctrl_src") for k, r in ros if r.get("msur_xm") is None)
        p26 = payroll.get((c, W - 1)) or {}
        p27 = payroll.get((c, W)) or {}
        club_docs[c] = {
            "roster": {
                "n": len(ros),
                "n_on40_prospects_in_farm": sum(1 for _, r in farm if r.get("on40")),
                "xm_aav_usd": _sum(r["aav"] for _, r in ros),
                "fair_aav_usd": _sum(int(round(r["fair"] / max(r["years"], 1))) for _, r in ros),
                "payroll_spotrac": {f"total_{W - 1}_usd": p26.get("total_payroll_usd"),
                                    f"committed_{W}_usd": p27.get("total_payroll_usd"),
                                    "note": PAYROLL_NOTE},
                "n_free_agents_excluded": sum(1 for _, r in mine if r["bucket"] == "fa"),
                "ids": [k for k, _ in ros],
            },
            "market_surplus": {
                "n": len(surp),
                "seasons": _sum(r["ctrl"] for _, r in surp),
                "xm_usd": _sum(r["msur_xm"] for _, r in surp),
                "fair_usd": _sum(r["msur_fair"] for _, r in surp),
                "n_not_summed": dict(sorted((str(k), v) for k, v in excl.items())),
                "ids": [k for k, _ in surp],
            },
            "farm": {
                "n": len(farm),
                "n_on40": sum(1 for _, r in farm if r.get("on40")),
                "fair_usd": _sum(r["fair"] for _, r in farm),
                "ids": [k for k, _ in farm],
            },
        }
    clubs_doc = {
        **meta,
        "what": {
            "roster.xm_aav_usd": ("the sum of xM$ AAV (P50) over the club's 40-man rows with an MLB "
                                  "WAR path or a /fa/ price, the market cost to replace them this "
                                  "winter; quantiles are never summed; 40-man prospects sit in the "
                                  "farm block"),
            "roster.fair_aav_usd": "the sum of Fair $ per year of the xM$ term over the same rows",
            "roster.payroll_spotrac": ("Spotrac's figures, quoted beside the sum and never netted "
                                       "against it; " + PAYROLL_NOTE),
            "market_surplus.xm_usd": ("sum over each player's priced control seasons of xM$ AAV carried "
                                      "by the $/WAR index minus the expected salary (contract, the "
                                      "arbitration ladder or the league minimum), discounted"),
            "market_surplus.fair_usd": "the same seasons with each season's Fair $ in place of the xM$ leg",
            "farm.fair_usd": ("the sum of Fair $ over the club's board prospects, on its 40-man or "
                              "off it: each the NPV of his eFV WAR path at the market rate (gate "
                              "section 16); no farm xM$ exists, a prospect's xM$ is withheld ("
                              + XM_WITHHELD_NOTE + ")"),
        },
        "surfaces": {"ledger": list(SURFACE_BLOCKS["ledger"]),
                     "franchise": list(SURFACE_BLOCKS["franchise"]),
                     "trademachine": "the market-rate surplus summed per side from xm_players rows"},
        "n_clubs": len(club_docs),
        "clubs": club_docs,
    }
    _assert_docs(players_doc, clubs_doc)
    return players_doc, clubs_doc


def _assert_docs(players_doc: dict, clubs_doc: dict) -> None:
    """The served invariants, asserted before anything is written."""
    cols = players_doc["columns"]
    ix = {c: i for i, c in enumerate(cols)}
    for k, row in players_doc["players"].items():
        v = row[ix["fair"]]
        assert v is not None and not (isinstance(v, float) and math.isnan(v)), (k, "fair")
        if row[ix["xm_withheld"]]:
            # gate section 16: a withheld row carries no xM$ figure at all
            assert row[ix["pop"]] == "prospect" and row[ix["bucket"]] == "farm", k
            assert all(row[ix[c]] is None for c in XM_COLUMNS), k
            assert row[ix["clip"]] is False, k
            continue
        for c in ("years", "aav", "total"):
            v = row[ix[c]]
            assert v is not None and not (isinstance(v, float) and math.isnan(v)), (k, c)
        for a, b, c in (("years_p10", "years", "years_p90"), ("aav_p10", "aav", "aav_p90"),
                        ("total_p10", "total", "total_p90")):
            assert row[ix[a]] <= row[ix[b]] <= row[ix[c]], (k, a, b, c)
    rows = {k: dict(zip(cols, v)) for k, v in players_doc["players"].items()}
    for c, cd in clubs_doc["clubs"].items():
        assert cd["roster"]["xm_aav_usd"] == sum(rows[k]["aav"] for k in cd["roster"]["ids"]), c
        assert cd["market_surplus"]["xm_usd"] == sum(rows[k]["msur_xm"]
                                                     for k in cd["market_surplus"]["ids"]), c
        # gate section 16: the farm totals reconcile to their rows
        assert cd["farm"]["n"] == len(cd["farm"]["ids"]), c
        assert cd["farm"]["fair_usd"] == sum(rows[k]["fair"] for k in cd["farm"]["ids"]), c
        assert not any(k.startswith("xm_") for k in cd["farm"]), c
        assert all(rows[k]["xm_withheld"] is False for k in cd["roster"]["ids"]), c


def _dump(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write(players_doc: dict, clubs_doc: dict, out_dir: Path | None = None) -> list:
    """Write both files to data/ while XM_EXPORT_ON, else under the preview
    directory; returns the written paths."""
    if out_dir is None:
        out_dir = DATA if XM_EXPORT_ON else PREVIEW_DIR
        p_players = OUT_PLAYERS if XM_EXPORT_ON else PREVIEW_DIR / OUT_PLAYERS.name
        p_clubs = OUT_CLUBS if XM_EXPORT_ON else PREVIEW_DIR / OUT_CLUBS.name
    else:
        p_players, p_clubs = Path(out_dir) / OUT_PLAYERS.name, Path(out_dir) / OUT_CLUBS.name
    p_players.parent.mkdir(parents=True, exist_ok=True)
    p_players.write_text(_dump(players_doc), encoding="utf-8")
    p_clubs.write_text(_dump(clubs_doc), encoding="utf-8")
    return [p_players, p_clubs]


def export(data_dir: Path | None = None) -> dict:
    """Build and write; returns a small summary for the pipeline log."""
    pd, cd = build(data_dir)
    paths = write(pd, cd)
    return {"n_players": pd["n"], "n_unpriced": len(pd["unpriced"]),
            "n_clubs": cd["n_clubs"], "paths": [str(p) for p in paths]}


# ============================================================================
# Dark consumers (ledger_export, franchise_export)
# ============================================================================

def club_blocks(data_dir: Path | None = None, surface: str = "franchise") -> dict | None:
    """{club: block} off the written xm_clubs.json for a consumer to attach,
    or None while XM_DISPLAY_ON is False (nothing is read, nothing moves).
    ``surface`` picks what it may show (SURFACE_BLOCKS, owner answer XM2-Q2):
    the Ledger gets the roster and farm blocks only, never the market-rate
    surplus."""
    if surface not in SURFACE_BLOCKS:
        raise ValueError(f"xm_export.club_blocks: unknown surface {surface!r}")
    if not XM_DISPLAY_ON:
        return None
    doc = _j(OUT_CLUBS.name, data_dir)
    if not doc:
        return None
    out = {}
    for c, cd in (doc.get("clubs") or {}).items():
        blk = {"as_of": doc.get("as_of"), "model_id": doc.get("model_id")}
        for name in SURFACE_BLOCKS[surface]:
            blk[name] = {k: v for k, v in (cd.get(name) or {}).items() if k != "ids"}
        out[c] = blk
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(export(), indent=1))
