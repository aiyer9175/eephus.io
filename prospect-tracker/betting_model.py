# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_model.py - MLB game probabilities from the site's own surfaces.

THE POINT: everything a book prices, this platform already measures. Team
offense is HEM+ rolled up to `offense_plus`; the rotation is SEM+ rolled up to
`rotation_plus` with the listed probable's own SEM+ available per start; the
bullpen is REM+ rolled up to `bullpen_plus`; park run environment is the same
Savant index the FA engine reads out of data/fa_meta.json. No new data source
is invented here. The model is a run-scoring regression on those four inputs
plus home field, and a Poisson-difference margin on top of it.

THE SCORING MODEL (two rows per game, one per scoring side)

    runs_S = b0 + b1*z_off_S + b2*z_prev_O + b3*park + b4*home

      z_off_S    the scoring team's offense_plus, standardized across the 30
                 teams for the season.
      z_prev_O   the OPPONENT's run prevention for THIS game: the listed
                 probable's SEM+ for the share of the game a starter covers
                 (ip_per_gs / 9), the opponent's bullpen_plus for the rest,
                 standardized on the team-level prevention distribution. With
                 no probable announced, the opponent's rotation_plus stands in.
      park       the home park's Savant runs index / 100 - 1 (0 = neutral).
      home       1 when S bats last.

    The coefficients are FIT, not assumed (`fit_coefficients`), on completed
    games read out of the existing .cache/game_feeds StatsAPI feed cache. That
    matters: a plus-stat sigma is not a run, and guessing the conversion is
    where a model like this usually goes wrong. When no fit is available the
    module falls back to literature priors (LITERATURE_COEFFS) and says so in
    `coefficients()["source"]`.

    Expected runs go into a Poisson-difference (Skellam) margin, computed by
    direct convolution so there is no scipy dependency in the serving path.
    That gives the moneyline (P(margin > 0), with the measured extra-innings
    home rate splitting the tie mass), the runline (P(margin >= 2)), and the
    total (Poisson on the run sum).

WHAT THIS MODEL IS NOT, AND THE PAGE SAYS SO
    Poisson underdisperses real run scoring: baseball scores in clumps, so the
    true margin distribution has fatter tails than the convolution assumes.
    That pushes runline and total probabilities toward the middle. The
    moneyline is the least exposed of the three.

    Worse, and this is the reason the module ships UNVALIDATED: the team
    inputs are SEASON-TO-DATE aggregates. Backtesting 2026 games against
    August's leaderboards means the features already contain the outcomes
    being predicted. `backtest()` runs, reports honest numbers, and labels
    them contaminated. Nothing here unlocks a published pick. A pick ships
    only once vintage-dated team inputs exist and a clean out-of-sample
    number does.

DE-VIGGING (`devig`) uses the PROPORTIONAL method: each side's raw implied
probability divided by the book's overround. It is the standard, it is
transparent, and it is the one an edge number can be audited against.
Shin and the power/additive methods shift favourite-longshot weight around;
they are not used, and swapping one in would change every edge on the page,
so the method name travels in the payload.

CLI:
    python betting_model.py --context      # league constants + fitted coefficients
    python betting_model.py --backtest     # the contaminated in-sample number
    python betting_model.py --game NYM CLE # one matchup, hand-checkable
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("betting_model")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
FEED_CACHE = ROOT / ".cache" / "game_feeds"
GAME_CACHE = ROOT / ".cache" / "betting"
CONTEXT_PATH = DATA_DIR / "betting_model_context.json"
EVAL_PATH = DATA_DIR / "betting_model_eval.json"

MODEL_VERSION = "betting_runs_v1"

# Share of a game the listed starter is expected to cover when the pitcher has
# no measured ip_per_gs. 5.2 IP is roughly the 2026 league average start.
DEFAULT_SP_SHARE = 5.2 / 9.0

# Fallbacks for a checkout with no feed cache. Sourced from published league
# run environments (2023-2025 MLB sat at 4.3-4.6 R/G per team, home teams won
# 52-54%), NOT from anything measured here. `coefficients()["source"]` says
# which set is live, and the page prints it.
LITERATURE_COEFFS = {
    "b0": 4.45,      # league runs per team per game
    "b1": 0.32,      # runs per sigma of team offense
    "b2": -0.32,     # runs per sigma of opponent run prevention
    "b3": 3.20,      # runs per unit of park index deviation (1.10 park -> +0.32)
    "b4": 0.09,      # home field, in runs, per side
    "source": "literature-priors",
    "n_rows": 0,
}
LITERATURE_TIE_HOME = 0.50       # home win rate once a game reaches extras
# Shrink strength for the extra-innings home rate. A season carries ~140 extra
# inning games, whose raw rate swings +/- 4 points on noise alone, so the
# measured value is shrunk toward a coin flip on a 100-game prior.
TIE_SHRINK_K = 100.0


# ---------------------------------------------------------------------------
# small io helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _data(name: str):
    return _load_json(DATA_DIR / name)


def _org(name: str | None) -> str | None:
    """Anything team-shaped -> the canonical 3-letter org code. The site runs
    TWO code sets: the leaderboards carry StatsAPI abbreviations (SD, SF, TB,
    KC, AZ, CWS, WSH, ATH) while park factors and fantasy_schedule carry the
    Baseball-Reference style (SDP, SFG, TBR, KCR, ARI, CHW, WSN, ATH).
    canonical_org maps the first onto the second, so EVERY join in this module
    goes through it. Mixing the two silently drops eight clubs."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if not n:
        return 0.0, 1.0
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / n
    return mu, (math.sqrt(var) or 1.0)


# ---------------------------------------------------------------------------
# team + pitcher inputs off the committed leaderboards
# ---------------------------------------------------------------------------
def team_inputs() -> dict:
    """{org: {...}} team strength, standardized. Empty when the leaderboards
    are absent (fresh checkout), which the caller degrades on."""
    hit = _data("hitter_leaderboards.json") or {}
    pen = _data("bullpen_leaderboards.json") or {}
    rot = _data("starter_leaderboards.json") or {}

    off = {}
    for t in hit.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("offense_plus") is not None:
            off[o] = float(t["offense_plus"])
    pens, relief_ip = {}, {}
    for t in pen.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("bullpen_plus") is not None:
            pens[o] = float(t["bullpen_plus"])
            relief_ip[o] = float(t.get("relief_ip") or 0.0)
    rots, starter_ip = {}, {}
    for t in rot.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("rotation_plus") is not None:
            rots[o] = float(t["rotation_plus"])
            starter_ip[o] = float(t.get("starter_ip") or 0.0)

    orgs = sorted(set(off) & set(pens) & set(rots))
    if not orgs:
        return {}
    # Team run prevention = rotation and bullpen weighted by their ACTUAL
    # innings split, not a guessed 60/40. The split moves several points a year
    # and moves more than that for an opener-heavy staff.
    prev = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        w = sip / (sip + rip) if (sip + rip) > 0 else DEFAULT_SP_SHARE
        prev[o] = w * rots[o] + (1.0 - w) * pens[o]

    off_mu, off_sd = _mean_sd([off[o] for o in orgs])
    prev_mu, prev_sd = _mean_sd([prev[o] for o in orgs])
    out = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        out[o] = {
            "org": o,
            "offense_plus": off[o],
            "rotation_plus": rots[o],
            "bullpen_plus": pens[o],
            "prev_plus": prev[o],
            "sp_ip_share": (sip / (sip + rip)) if (sip + rip) > 0 else DEFAULT_SP_SHARE,
            "z_off": (off[o] - off_mu) / off_sd,
            "z_prev": (prev[o] - prev_mu) / prev_sd,
        }
    out["_scale"] = {"off_mu": off_mu, "off_sd": off_sd,
                     "prev_mu": prev_mu, "prev_sd": prev_sd}
    return out


def starter_inputs() -> dict:
    """{mlbam: {sem_plus, ip_per_gs, name, org}} from starter_leaderboards, so a
    game can be priced on the announced probable rather than the rotation
    average. Relievers are folded in too (openers, bulk relief)."""
    out = {}
    rot = _data("starter_leaderboards.json") or {}
    for r in rot.get("starters") or []:
        mid = r.get("mlbam")
        if not mid or r.get("sem_plus") is None:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["sem_plus"]),
                         "ip_per_gs": float(r.get("ip_per_gs") or 0.0) or None,
                         "role": r.get("role") or "SP"}
    pen = _data("bullpen_leaderboards.json") or {}
    for r in pen.get("relievers") or []:
        mid = r.get("mlbam")
        if not mid or r.get("rem_plus") is None or int(mid) in out:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["rem_plus"]),   # same 100/10z scale
                         "ip_per_gs": None, "role": "RP"}
    return out


def park_index() -> dict:
    """{org: runs index / 100}. data/fa_meta.json carries the Savant park
    factors the FA engine already reads; no second copy is fetched. Missing
    parks resolve neutral at lookup, never invented."""
    meta = _data("fa_meta.json") or {}
    pf = meta.get("park_factors") or {}
    out = {}
    for org, v in pf.items():
        try:
            out[str(org)] = float((v or {}).get("runs") or 100) / 100.0
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# fitted (or literature) coefficients
# ---------------------------------------------------------------------------
def coefficients() -> dict:
    """The live run-scoring coefficients. Fitted set if data/betting_model_context.json
    exists, literature priors otherwise. Callers print `source` on the page."""
    ctx = _load_json(CONTEXT_PATH) or {}
    c = ctx.get("coefficients")
    if isinstance(c, dict) and all(k in c for k in ("b0", "b1", "b2", "b3", "b4")):
        return c
    return dict(LITERATURE_COEFFS)


def league_context() -> dict:
    ctx = _load_json(CONTEXT_PATH) or {}
    return {
        "season": ctx.get("season"),
        "n_games": ctx.get("n_games") or 0,
        "lg_rpg": ctx.get("lg_rpg"),
        "home_win_rate": ctx.get("home_win_rate"),
        "extra_inning_home_rate": ctx.get("extra_inning_home_rate_shrunk") or LITERATURE_TIE_HOME,
        "home_logit_offset": float(ctx.get("home_logit_offset") or 0.0),
        "generated_at": ctx.get("generated_at"),
        "source": (coefficients() or {}).get("source"),
    }


# ---------------------------------------------------------------------------
# the game model
# ---------------------------------------------------------------------------
def game_prevention_z(team: dict, starter: dict | None, teams: dict) -> tuple[float, dict]:
    """(z, detail) for one side's run prevention IN THIS GAME.

    The listed probable's own SEM+ covers ip_per_gs/9 of the game; the team
    bullpen covers the rest. With nobody announced the team's rotation average
    stands in for the starter share, which is exactly what a book does with a
    TBD."""
    scale = teams.get("_scale") or {}
    mu = scale.get("prev_mu", 100.0)
    sd = scale.get("prev_sd", 1.0) or 1.0
    pen_plus = team.get("bullpen_plus", 100.0)
    if starter and starter.get("sem_plus") is not None:
        share = (starter.get("ip_per_gs") or (DEFAULT_SP_SHARE * 9.0)) / 9.0
        share = max(0.25, min(0.85, share))
        sp_plus = float(starter["sem_plus"])
        src = "probable"
    else:
        share = float(team.get("sp_ip_share") or DEFAULT_SP_SHARE)
        sp_plus = float(team.get("rotation_plus", 100.0))
        src = "rotation-average"
    blended = share * sp_plus + (1.0 - share) * pen_plus
    return (blended - mu) / sd, {
        "starter_plus": round(sp_plus, 1), "bullpen_plus": round(pen_plus, 1),
        "starter_share": round(share, 3), "blend_plus": round(blended, 1),
        "source": src,
    }


def expected_runs(home_org: str, away_org: str, *, home_sp: dict | None = None,
                  away_sp: dict | None = None, teams: dict | None = None,
                  parks: dict | None = None, coeffs: dict | None = None,
                  home_adj: float | None = None,
                  diff_shrink: float | None = None) -> dict | None:
    """Expected runs for both sides, plus the components that produced them.
    None when either club is missing from the leaderboards.

    THE HOME-FIELD CORRECTION, because the raw fit gets it wrong for a
    structural reason worth naming. Fitting runs scored on a home dummy
    recovers only +0.013 runs of home field in 2026, while home teams actually
    won 52.3% of those same games. Both numbers are right: a home team leading
    after the top of the ninth DOES NOT BAT, so its runs-scored column is
    censored exactly in the games it wins. Regressing on runs therefore
    understates home field almost to zero.

    `home_adj` is the run-differential shift that reconciles them, solved in
    build_context so that the model's mean home win probability equals the
    observed home win rate. It is applied as +adj/2 to the home side and
    -adj/2 to the away side, so the runline moves coherently with the
    moneyline and the fair TOTAL is left untouched (the two halves cancel).
    Zero when no context has been built.

    THE MARGIN SHRINK, for a defect the first calibration table caught. The
    raw linear predictor put 2026 games as far apart as 90/10, and the bins
    above 0.80 came back 0.86 predicted against 0.67 actual: the model was
    more sure than the season was. `diff_shrink` scales the run DIFFERENTIAL
    toward zero while holding the pair mean, so it shrinks the moneyline and
    the runline together and leaves the fair total alone. It is fitted by
    minimizing log loss on completed games (`_solve_diff_shrink`), not chosen.
    1.0 when no context has been built."""
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    c = coeffs or coefficients()
    if home_adj is None or diff_shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        if home_adj is None:
            home_adj = float(ctx.get("home_field_runs_adj") or 0.0)
        if diff_shrink is None:
            diff_shrink = float(ctx.get("diff_shrink") or 1.0)
    h, a = teams.get(home_org), teams.get(away_org)
    if not h or not a:
        return None
    park = (parks.get(home_org) or 1.0) - 1.0
    zp_home, det_home = game_prevention_z(h, home_sp, teams)
    zp_away, det_away = game_prevention_z(a, away_sp, teams)

    def _runs(z_off, z_prev_opp, is_home):
        return (c["b0"] + c["b1"] * z_off + c["b2"] * z_prev_opp
                + c["b3"] * park + (c["b4"] if is_home else 0.0)
                + (home_adj / 2.0 if is_home else -home_adj / 2.0))

    raw_home = _runs(h["z_off"], zp_away, True)
    raw_away = _runs(a["z_off"], zp_home, False)
    mid, half = (raw_home + raw_away) / 2.0, (raw_home - raw_away) / 2.0
    lam_home = max(1.5, min(9.5, mid + diff_shrink * half))
    lam_away = max(1.5, min(9.5, mid - diff_shrink * half))
    return {
        "lam_home": lam_home, "lam_away": lam_away,
        "home_field_runs_adj": round(float(home_adj), 4),
        "diff_shrink": round(float(diff_shrink), 4),
        "park_index": round(park + 1.0, 3),
        "home": {"org": home_org, "z_off": round(h["z_off"], 3),
                 "offense_plus": h["offense_plus"], "prevention": det_home},
        "away": {"org": away_org, "z_off": round(a["z_off"], 3),
                 "offense_plus": a["offense_plus"], "prevention": det_away},
    }


def _poisson_pmf(lam: float, k_max: int) -> list[float]:
    """pmf[0..k_max] for Poisson(lam), recurrence form (no factorials, no
    overflow at the tail)."""
    out = [math.exp(-lam)]
    for k in range(1, k_max + 1):
        out.append(out[-1] * lam / k)
    return out


def margin_distribution(lam_home: float, lam_away: float, k_max: int = 24) -> dict:
    """P(home runs - away runs = d) for d in [-k_max, k_max], by direct
    convolution of two Poissons (a Skellam, computed without Bessel functions
    so the serving path has no scipy dependency)."""
    ph = _poisson_pmf(lam_home, k_max)
    pa = _poisson_pmf(lam_away, k_max)
    dist = {}
    for i, p_i in enumerate(ph):
        if p_i < 1e-12:
            continue
        for j, p_j in enumerate(pa):
            if p_j < 1e-12:
                continue
            d = i - j
            dist[d] = dist.get(d, 0.0) + p_i * p_j
    return dist


def total_distribution(lam_home: float, lam_away: float, k_max: int = 40) -> list[float]:
    """P(total runs = k) - the sum of two independent Poissons is Poisson."""
    return _poisson_pmf(lam_home + lam_away, k_max)


def game_probabilities(home_org: str, away_org: str, *, home_sp=None, away_sp=None,
                       teams=None, parks=None, coeffs=None, tie_home=None,
                       home_adj=None, diff_shrink=None) -> dict | None:
    """The full model view of one game: moneyline, runline, fair total.

    Ties do not exist in MLB, so the P(margin = 0) mass is split by the
    MEASURED extra-innings home win rate (league_context, shrunk toward a coin
    flip on a 100-game prior), not by an invented constant."""
    er = expected_runs(home_org, away_org, home_sp=home_sp, away_sp=away_sp,
                       teams=teams, parks=parks, coeffs=coeffs, home_adj=home_adj,
                       diff_shrink=diff_shrink)
    if not er:
        return None
    lam_h, lam_a = er["lam_home"], er["lam_away"]
    dist = margin_distribution(lam_h, lam_a)
    p_tie = dist.get(0, 0.0)
    th = tie_home if tie_home is not None else (league_context().get("extra_inning_home_rate")
                                               or LITERATURE_TIE_HOME)
    p_home_reg = sum(p for d, p in dist.items() if d > 0)
    p_home = p_home_reg + p_tie * th
    # Runline. A -1.5 favourite must win by 2+. The +1.5 dog needs the game
    # inside one run OR an outright win, which is 1 - P(margin >= 2).
    p_home_minus15 = sum(p for d, p in dist.items() if d >= 2)
    p_away_minus15 = sum(p for d, p in dist.items() if d <= -2)
    tot = total_distribution(lam_h, lam_a)
    fair_total = lam_h + lam_a

    def over(line: float) -> float:
        need = math.floor(line) + 1 if line != int(line) else int(line) + 1
        return sum(tot[k] for k in range(need, len(tot)))

    return {
        "home_org": home_org, "away_org": away_org,
        "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
        "p_home": round(p_home, 5), "p_away": round(1.0 - p_home, 5),
        "p_home_minus_1_5": round(p_home_minus15, 5),
        "p_away_minus_1_5": round(p_away_minus15, 5),
        "p_home_plus_1_5": round(1.0 - p_away_minus15, 5),
        "p_away_plus_1_5": round(1.0 - p_home_minus15, 5),
        "fair_total": round(fair_total, 2),
        "over": over,                      # callable; the export resolves a line
        "components": er,
        "model_version": MODEL_VERSION,
    }


# ---------------------------------------------------------------------------
# market math
# ---------------------------------------------------------------------------
def devig(decimals: dict, method: str = "proportional") -> dict:
    """Raw prices -> fair (no-vig) probabilities.

    PROPORTIONAL method: q_i = 1/decimal_i, then p_i = q_i / sum(q). The sum of
    the raw implieds is the overround (a two-way MLB moneyline at -110/-110
    sums to 1.0476, a 4.76% hold); dividing it out spreads the vig in
    proportion to each side's raw probability.

    This is a CHOICE. Shin's method and the power method both take relatively
    more vig off the longshot, which moves a fair probability by up to a point
    on a lopsided moneyline and therefore moves every edge on the page. The
    method name ships in the payload so the number can be audited."""
    if method != "proportional":
        raise ValueError(f"unsupported de-vig method {method!r}")
    raw = {}
    for k, d in (decimals or {}).items():
        try:
            dv = float(d)
        except (TypeError, ValueError):
            continue
        if dv > 1.0:
            raw[k] = 1.0 / dv
    s = sum(raw.values())
    if not raw or s <= 0:
        return {}
    return {k: v / s for k, v in raw.items()}


def hold_pct(decimals: dict) -> float | None:
    """The book's hold on a market: sum of raw implieds minus 1, in percent."""
    raw = [1.0 / float(d) for d in (decimals or {}).values() if _pos(d)]
    return None if not raw else (sum(raw) - 1.0) * 100.0


def _pos(d) -> bool:
    try:
        return float(d) > 1.0
    except (TypeError, ValueError):
        return False


def ev_per_unit(p: float, decimal: float) -> float:
    """Expected profit on a 1-unit stake at `decimal` odds given probability p."""
    return p * (decimal - 1.0) - (1.0 - p)


def kelly_fraction(p: float, decimal: float) -> float:
    """Full-Kelly stake fraction. INFORMATIONAL ONLY on this site: the public
    record is flat 1 unit, always, because a variable stake makes a published
    ROI unauditable and invites the exact behaviour the disclaimer warns
    against. Negative means no bet."""
    b = decimal - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (p * b - (1.0 - p)) / b)


def edge(p_model: float, p_fair: float) -> float:
    """Our probability minus the de-vigged market probability. Positive means
    the model thinks the market is short."""
    return p_model - p_fair


# ---------------------------------------------------------------------------
# offline game results (for fitting + backtest)
# ---------------------------------------------------------------------------
_SPORT_RE = re.compile(rb"/api/v1/sports/(\d+)")


def _mlb_feed_paths() -> list[Path]:
    """MLB (sportId 1) game feeds inside the existing StatsAPI feed cache.
    The cache is mostly minor-league, so the sport is sniffed off the first
    few KB rather than parsing 18k files."""
    if not FEED_CACHE.exists():
        return []
    out = []
    for p in sorted(FEED_CACHE.glob("*.json")):
        try:
            head = p.open("rb").read(9000)
        except OSError:
            continue
        m = _SPORT_RE.search(head)
        if m and m.group(1) == b"1":
            out.append(p)
    return out


def build_game_cache(*, force: bool = False, log_fn=None) -> list[dict]:
    """Completed MLB games as compact rows, from .cache/game_feeds.

    OFFLINE. The feed cache is already on the box for leverage and Statcast;
    this only reads it. The compact result is cached under .cache/betting so
    the 1.5GB walk happens once."""
    GAME_CACHE.mkdir(parents=True, exist_ok=True)
    out_path = GAME_CACHE / "completed_games.json"
    if out_path.exists() and not force:
        cached = _load_json(out_path)
        if isinstance(cached, list) and cached:
            return cached
    rows: list[dict] = []
    paths = _mlb_feed_paths()
    if log_fn:
        log_fn(f"betting_model: scanning {len(paths)} MLB feeds")
    for p in paths:
        d = _load_json(p)
        if not isinstance(d, dict):
            continue
        gd = d.get("gameData") or {}
        if (gd.get("status") or {}).get("abstractGameState") != "Final":
            continue
        game = gd.get("game") or {}
        if game.get("type") != "R":
            continue
        teams = gd.get("teams") or {}
        line = ((d.get("liveData") or {}).get("linescore") or {})
        lt = line.get("teams") or {}
        hr, ar = (lt.get("home") or {}).get("runs"), (lt.get("away") or {}).get("runs")
        if hr is None or ar is None:
            continue
        pp = gd.get("probablePitchers") or {}
        rows.append({
            "game_pk": game.get("pk"),
            "season": str(game.get("season") or ""),
            "date": (gd.get("datetime") or {}).get("officialDate"),
            "home_org": _org((teams.get("home") or {}).get("abbreviation")
                             or (teams.get("home") or {}).get("name")),
            "away_org": _org((teams.get("away") or {}).get("abbreviation")
                             or (teams.get("away") or {}).get("name")),
            "home_runs": int(hr), "away_runs": int(ar),
            "innings": line.get("currentInning"),
            "home_sp": (pp.get("home") or {}).get("id"),
            "away_sp": (pp.get("away") or {}).get("id"),
        })
    rows = [r for r in rows if r["home_org"] and r["away_org"]]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
    out_path.write_text(json.dumps(rows), encoding="utf-8")
    if log_fn:
        log_fn(f"betting_model: cached {len(rows)} completed games -> {out_path}")
    return rows


def completed_games(season: str | None = None) -> list[dict]:
    rows = build_game_cache()
    return [r for r in rows if not season or r.get("season") == str(season)]


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------
def _design_rows(games: list[dict], teams: dict, parks: dict, starters: dict):
    """Two rows per game (each side as the scoring side) -> (X, y, meta)."""
    X, y, meta = [], [], []
    for g in games:
        h, a = teams.get(g["home_org"]), teams.get(g["away_org"])
        if not h or not a:
            continue
        park = (parks.get(g["home_org"]) or 1.0) - 1.0
        zp_home, _ = game_prevention_z(h, starters.get(g.get("home_sp")), teams)
        zp_away, _ = game_prevention_z(a, starters.get(g.get("away_sp")), teams)
        X.append([1.0, h["z_off"], zp_away, park, 1.0])
        y.append(float(g["home_runs"]))
        meta.append((g, "home"))
        X.append([1.0, a["z_off"], zp_home, park, 0.0])
        y.append(float(g["away_runs"]))
        meta.append((g, "away"))
    return X, y, meta


def fit_coefficients(games: list[dict] | None = None, *, teams=None, parks=None,
                     starters=None) -> dict | None:
    """OLS for the five run-scoring coefficients. None when there is nothing to
    fit on (no feed cache), which is what sends `coefficients()` to the
    literature priors."""
    import numpy as np

    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    games = games if games is not None else completed_games()
    if not games or not teams:
        return None
    X, y, _ = _design_rows(games, teams, parks, starters)
    if len(X) < 200:
        return None
    A, b = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ beta
    ss_tot = float(((b - b.mean()) ** 2).sum())
    return {
        "b0": float(beta[0]), "b1": float(beta[1]), "b2": float(beta[2]),
        "b3": float(beta[3]), "b4": float(beta[4]),
        "source": "fitted",
        "n_rows": len(X),
        "rmse": float(math.sqrt(float((resid ** 2).mean()))),
        "r2": float(1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot else None,
    }


def _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, shrink):
    """(predicted p_home, observed home win) for every game. The inner loop of
    both solvers, written once so they cannot drift apart."""
    ps, ys = [], []
    for g in games:
        gp = game_probabilities(g["home_org"], g["away_org"],
                                home_sp=starters.get(g.get("home_sp")),
                                away_sp=starters.get(g.get("away_sp")),
                                teams=teams, parks=parks, coeffs=coeffs,
                                tie_home=tie_home, home_adj=adj, diff_shrink=shrink)
        if gp:
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
    return ps, ys


def _solve_home_adj(games, teams, parks, starters, coeffs, tie_home, target: float,
                    shrink: float = 1.0) -> float:
    """The run-differential shift that makes the model's MEAN home win
    probability equal the observed home win rate. Bisection over a bounded
    interval; one parameter, one target, no free lunch. See the docstring on
    expected_runs for why the raw fit needs it."""
    def mean_p(adj: float) -> float:
        ps, _ = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, shrink)
        return sum(ps) / len(ps) if ps else 0.5

    lo, hi = -0.60, 1.20
    if mean_p(lo) > target or mean_p(hi) < target:
        return 0.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if mean_p(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 4)


def _solve_diff_shrink(games, teams, parks, starters, coeffs, tie_home,
                       adj: float = 0.0) -> tuple[float, float]:
    """(shrink, log loss) minimizing log loss over a coarse-to-fine grid.

    ONE parameter. A value below 1 means the linear predictor spread the
    league further apart than the results did, which is the normal failure
    mode for a model built out of season-long rate stats: the inputs are
    themselves shrunk estimates, and stacking them recovers less signal than
    their spread implies."""
    def ll(s: float) -> float:
        ps, ys = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, s)
        return _logloss(ps, ys) if ps else 9.9

    best_s, best_l = 1.0, ll(1.0)
    for step, span in ((0.1, 8), (0.02, 5)):
        centre = best_s
        for i in range(-span, span + 1):
            s = round(centre + i * step, 4)
            if s < 0.2 or s > 1.6:
                continue
            l = ll(s)
            if l < best_l:
                best_s, best_l = s, l
    return best_s, round(best_l, 6)


def build_context(*, season: str | None = None, write: bool = True, log_fn=None) -> dict:
    """Fit the coefficients and measure the league constants, then write
    data/betting_model_context.json. Offline; safe to re-run."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    coeffs = fit_coefficients(games, teams=teams, parks=parks, starters=starters)
    n = len(games)
    lg_rpg = (sum(g["home_runs"] + g["away_runs"] for g in games) / (2.0 * n)) if n else None
    home_wins = sum(1 for g in games if g["home_runs"] > g["away_runs"])
    home_rate = (home_wins / n) if n else None
    extras = [g for g in games if (g.get("innings") or 9) > 9]
    x_wins = sum(1 for g in extras if g["home_runs"] > g["away_runs"])
    tie_raw = (x_wins / len(extras)) if extras else None
    tie_shrunk = ((x_wins + 0.5 * TIE_SHRINK_K) / (len(extras) + TIE_SHRINK_K)
                  if extras else LITERATURE_TIE_HOME)
    # Two one-parameter corrections, solved in sequence and then refined once,
    # because they interact: shrinking the differential moves the mean home
    # probability, and shifting home field moves the log loss the shrink is
    # minimizing. Two passes is enough; the second changes the shrink in the
    # third decimal.
    adj, shrink, shrink_ll = 0.0, 1.0, None
    if n and coeffs:
        shrink, shrink_ll = _solve_diff_shrink(games, teams, parks, starters, coeffs,
                                               tie_shrunk, 0.0)
        adj = _solve_home_adj(games, teams, parks, starters, coeffs, tie_shrunk,
                              home_rate, shrink)
        shrink, shrink_ll = _solve_diff_shrink(games, teams, parks, starters, coeffs,
                                               tie_shrunk, adj)
        adj = _solve_home_adj(games, teams, parks, starters, coeffs, tie_shrunk,
                              home_rate, shrink)
    ctx = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season or (games[-1]["season"] if games else None),
        "n_games": n,
        "lg_rpg": round(lg_rpg, 4) if lg_rpg else None,
        "home_win_rate": round(home_rate, 4) if home_rate else None,
        "extra_inning_games": len(extras),
        "extra_inning_home_rate_raw": round(tie_raw, 4) if tie_raw is not None else None,
        "extra_inning_home_rate_shrunk": round(tie_shrunk, 4),
        "home_field_runs_adj": adj,
        "diff_shrink": shrink,
        "diff_shrink_log_loss": shrink_ll,
        "diff_shrink_note": ("run-differential shrink fitted by log loss on completed games; "
                             "below 1.0 means the raw predictor separated clubs further than "
                             "the results did, and the fair total is untouched by it"),
        "home_field_note": ("the runs regression recovers almost no home field because a "
                            "home team leading after the top of the ninth never bats; the "
                            "adjustment restores the observed home win rate as a run "
                            "differential, leaving the fair total unchanged"),
        "coefficients": coeffs or dict(LITERATURE_COEFFS),
        "source_note": ("fit on completed games read out of .cache/game_feeds, offline; "
                        "team inputs are season-to-date leaderboards, so this fit is "
                        "IN-SAMPLE and cannot validate the model"),
    }
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONTEXT_PATH.write_text(json.dumps(ctx, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {CONTEXT_PATH.name} (n={n})")
    return ctx


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------
def _brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / max(1, len(ps))


def _logloss(ps: list[float], ys: list[int]) -> float:
    eps = 1e-9
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(ps, ys)) / max(1, len(ps))


def _calibration(ps: list[float], ys: list[int], bins: int = 10) -> list[dict]:
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in zip(ps, ys) if (lo <= p < hi or (i == bins - 1 and p == 1.0))]
        if not sel:
            continue
        out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(sel),
                    "pred": round(sum(p for p, _ in sel) / len(sel), 4),
                    "actual": round(sum(y for _, y in sel) / len(sel), 4)})
    return out


def backtest(*, season: str | None = None, split_date: str | None = None,
             write: bool = True, log_fn=None) -> dict:
    """Grade the model on completed games. Runs entirely offline.

    THE HONESTY BLOCK, and it is the reason no pick ships off this number:
    the team inputs (offense_plus / rotation_plus / bullpen_plus / SEM+) are
    SEASON-TO-DATE aggregates as of the last leaderboard build. Every game
    graded here contributed to the features used to predict it. `forward`
    additionally refits the coefficients on games before `split_date` and
    grades only games after it, which removes coefficient leakage but NOT
    feature leakage. Both numbers are reported; both are labelled
    contaminated; `validated` is False in every branch until vintage-dated
    team inputs exist.

    Baselines are what make the number readable: 0.500 flat, and the measured
    home-field rate. A model that cannot beat "always take the home team" has
    not earned a page."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season,
        "validated": False,
        "contaminated": True,
        "contamination": ("team inputs are season-to-date leaderboards, so every graded "
                          "game is inside its own features; this measures calibration, "
                          "not out-of-sample skill"),
        "gates_picks": False,
        "min_edge": None,
        "n_games": len(games),
    }
    if not games or not teams:
        result["status"] = "no data"
        result["note"] = ("no completed-game cache and/or no leaderboards; run "
                          "betting_model.build_game_cache() on a box that has "
                          ".cache/game_feeds")
        if write:
            EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result

    def _grade(fit_games, eval_games, label):
        coeffs = fit_coefficients(fit_games, teams=teams, parks=parks, starters=starters) \
            or dict(LITERATURE_COEFFS)
        tie = (league_context().get("extra_inning_home_rate") or LITERATURE_TIE_HOME)
        # The home-field reconciliation is refit on the FIT window too, so the
        # forward split does not smuggle the evaluation window's home rate in
        # through the back door.
        fit_home_rate = (sum(1 for g in fit_games if g["home_runs"] > g["away_runs"])
                         / max(1, len(fit_games)))
        shrink, _ = _solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie, 0.0)
        adj = _solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                              fit_home_rate, shrink)
        ps, ys, tot_err, n_tot = [], [], 0.0, 0
        for g in eval_games:
            gp = game_probabilities(g["home_org"], g["away_org"],
                                    home_sp=starters.get(g.get("home_sp")),
                                    away_sp=starters.get(g.get("away_sp")),
                                    teams=teams, parks=parks, coeffs=coeffs, tie_home=tie,
                                    home_adj=adj, diff_shrink=shrink)
            if not gp:
                continue
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
            tot_err += abs(gp["fair_total"] - (g["home_runs"] + g["away_runs"]))
            n_tot += 1
        if not ps:
            return None
        base_home = sum(ys) / len(ys)
        return {
            "label": label,
            "n": len(ps),
            "coefficients": coeffs,
            "home_field_runs_adj": adj,
            "diff_shrink": shrink,
            "brier": round(_brier(ps, ys), 5),
            "brier_flat_500": round(_brier([0.5] * len(ps), ys), 5),
            "brier_home_base": round(_brier([base_home] * len(ps), ys), 5),
            "log_loss": round(_logloss(ps, ys), 5),
            "log_loss_flat_500": round(_logloss([0.5] * len(ps), ys), 5),
            "accuracy": round(sum(1 for p, y in zip(ps, ys)
                                  if (p >= 0.5) == bool(y)) / len(ps), 4),
            "home_win_rate": round(base_home, 4),
            "mean_p_home": round(sum(ps) / len(ps), 4),
            "total_mae": round(tot_err / n_tot, 3) if n_tot else None,
            "calibration": _calibration(ps, ys),
        }

    result["in_sample"] = _grade(games, games, "in-sample (coefficients and features both leak)")
    dates = sorted({g["date"] for g in games if g.get("date")})
    sd = split_date or (dates[int(len(dates) * 0.7)] if len(dates) > 20 else None)
    if sd:
        fit_g = [g for g in games if (g.get("date") or "") < sd]
        ev_g = [g for g in games if (g.get("date") or "") >= sd]
        if len(fit_g) > 200 and len(ev_g) > 50:
            result["split_date"] = sd
            result["forward"] = _grade(fit_g, ev_g,
                                       f"forward from {sd} (coefficient leakage removed, "
                                       "feature leakage remains)")
    result["status"] = "ran"
    result["note"] = ("A pick threshold is NOT set from these numbers. Publishing a pick "
                      "needs vintage-dated team inputs and a clean forward test.")
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {EVAL_PATH.name}")
    return result


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB game probability model (eephus.io).")
    ap.add_argument("--context", action="store_true", help="fit + write betting_model_context.json")
    ap.add_argument("--backtest", action="store_true", help="grade on completed games (offline)")
    ap.add_argument("--game", nargs=2, metavar=("AWAY", "HOME"), help="price one matchup")
    ap.add_argument("--season", default=None)
    args = ap.parse_args()

    if args.context:
        print(json.dumps(build_context(season=args.season, log_fn=print), indent=1))
    if args.backtest:
        r = backtest(season=args.season, log_fn=print)
        for k in ("in_sample", "forward"):
            if r.get(k):
                b = r[k]
                print(f"  {b['label']}: n={b['n']} brier={b['brier']} "
                      f"(flat .500 {b['brier_flat_500']}, home-base {b['brier_home_base']}) "
                      f"acc={b['accuracy']} total MAE={b['total_mae']}")
    if args.game:
        away, home = _org(args.game[0]), _org(args.game[1])
        gp = game_probabilities(home, away)
        if not gp:
            print(f"no leaderboard rows for {away} / {home}")
        else:
            gp.pop("over", None)
            print(json.dumps(gp, indent=1))
