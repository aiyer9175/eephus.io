"""Team projection candidates T1, T2 and T3 (docs/TEAM_PROJECTIONS_GATE.md
section 1; LANE_A section 2.6; plan Part 9 section 9.5): the pure functions
the exporter, the backtest and the DEV driver share. Task
TM_3_TEAM_CANDIDATES_DARK.

T1  talent ranges. The simulator draws each club's talent once per
    simulation, before the games, from Normal(p_prior, sd) with
    sd = sigma_T x k / (k + G) / 162, k = 40 pseudo-games, G the club's games
    played, clipped to [0.20, 0.80] (proj_current.simulate_playoffs,
    talent_sd_wins). sigma_T = sqrt(max(0, s_res^2 - s_sched^2)): s_res the
    RMSE of the served_recentered retro residual over the DEV club-seasons
    2022-2025, s_sched the mean schedule-only sd of the simulated win total.
    Frozen in model/team_projection/params.json by tools/team_projection_dev.py.
T2  the club PA and IP budget. Each rostered player's projected playing time
    is allocated, capped at his own projection; a club whose sum exceeds the
    budget scales every allocation down pro rata; a shortfall is filled at
    replacement (0 WAR); then the 2,430-win pin. The constants are the
    2022-2025 league means of club PA and IP per 162 games, frozen with T1.
T3  runs. RS = league runs per team-season + the roster's batting and
    baserunning runs at T2's allocated PA; RA = league runs per team-season +
    the staff's FIP runs allowed above average at T2's allocated IP, minus the
    club's fielding runs; the club park factor (FanGraphs, the season's
    cache) applied at the team level; run differential and Pythagenpat wins
    beside the WAR wins, never replacing them.

The three flags live in proj_export (TEAM_TALENT_RANGE_LIVE,
TEAM_PT_BUDGET_LIVE, TEAM_RUNS_LIVE) and default False: while False the
exporter writes the candidates under PREVIEW_DIR only and every served file is
byte-identical apart from its timestamp. Nothing here reads a 2026 club
outcome; the DEV driver reads the retro seasons 2022-2025 through
proj_backtest.team_frame and never the GATE season.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARAMS_DIR = ROOT / "model" / "team_projection"
PARAMS_PATH = PARAMS_DIR / "params.json"
DEV_RECEIPT_PATH = PARAMS_DIR / "dev_receipt.json"
CACHE_DIR = ROOT / ".cache" / "team_projection"
PREVIEW_DIR = CACHE_DIR / "preview"
SCHEDULE_DIR = CACHE_DIR / "schedules"
PREVIEW_NAME = "team_outlook_candidates.json"
PARK_FACTOR_DIR = ROOT / ".cache" / "fangraphs"

K_PSEUDO_GAMES = 40            # proj_export.CURRENT_PRIOR_PSEUDO_GAMES (pinned by test)
TALENT_CLIP = (0.20, 0.80)     # proj_export._talent_prior_pct's rails (pinned by test)
GAMES = 162.0
BF_PER_IP = 4.3                # proj_components.BF_PER_IP (pinned by test)
PF_COLUMN = "Basic (5yr)"      # the FanGraphs park factor column applied at the team level
PF_NEUTRAL = 100.0
PYTHAGENPAT_EXP = 0.287        # proj_export._PYTHAGENPAT_EXP (pinned by test)
#: |sum RS - sum RA| over the 30 clubs within this share of league runs: the
#: league identity the runs block reports (test_team_projection_candidates).
RUNS_IDENTITY_TOL = 0.01

#: Club nicknames by org code, as the FanGraphs park factor rows name them
#: (build_site.ORG_NAMES; pinned by test).
ORG_NICKNAMES = {
    "ARI": "Diamondbacks", "ATH": "Athletics", "ATL": "Braves", "BAL": "Orioles",
    "BOS": "Red Sox", "CHC": "Cubs", "CHW": "White Sox", "CIN": "Reds",
    "CLE": "Guardians", "COL": "Rockies", "DET": "Tigers", "HOU": "Astros",
    "KCR": "Royals", "LAA": "Angels", "LAD": "Dodgers", "MIA": "Marlins",
    "MIL": "Brewers", "MIN": "Twins", "NYM": "Mets", "NYY": "Yankees",
    "PHI": "Phillies", "PIT": "Pirates", "SDP": "Padres", "SEA": "Mariners",
    "SFG": "Giants", "STL": "Cardinals", "TBR": "Rays", "TEX": "Rangers",
    "TOR": "Blue Jays", "WSN": "Nationals",
}
_ORG_BY_NICKNAME = {v: k for k, v in ORG_NICKNAMES.items()}
#: Former nicknames the older park factor files carry.
_ORG_BY_NICKNAME.update({"Indians": "CLE", "Cleveland": "CLE"})


class TeamParamsError(RuntimeError):
    """The frozen params are absent, unreadable or hash to another record."""


# --------------------------------------------------------------------------
# T1: the talent draw
# --------------------------------------------------------------------------

def talent_sd_pct(talent_sd_wins, games_played=0, k: float = K_PSEUDO_GAMES) -> float:
    """The per-club talent draw's sd as a win rate: sigma_T x k / (k + G) / 162.
    A preseason projection (G = 0) keeps the whole sigma_T; in season the
    draw shrinks as the club's games played grow, the same k the in-season
    blend uses. 0.0 at sigma_T 0 (the incumbent)."""
    sd = float(talent_sd_wins or 0.0)
    if sd <= 0.0:
        return 0.0
    g = max(0.0, float(games_played or 0.0))
    return sd * float(k) / (float(k) + g) / GAMES


def clip_talent(p: float) -> float:
    lo, hi = TALENT_CLIP
    return min(hi, max(lo, float(p)))


# --------------------------------------------------------------------------
# The frozen params
# --------------------------------------------------------------------------

def params_hash(params: dict) -> str:
    """sha256 of the canonical JSON (sorted keys, no spaces), independent of
    the file's line endings and indent (proj_components.params_hash's form)."""
    blob = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_params(path: Path | None = None) -> dict | None:
    """The frozen params, or None while the DEV freeze has not happened."""
    p = Path(path) if path else PARAMS_PATH
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise TeamParamsError(f"{p}: {e}") from e


def check_params(params: dict, recorded_hash: str) -> dict:
    got = params_hash(params)
    if got != str(recorded_hash).strip().lower():
        raise TeamParamsError(f"params hash {got} != recorded {recorded_hash}")
    return params


def sigma_t(s_res: float, s_sched: float) -> float:
    """sqrt(max(0, s_res^2 - s_sched^2)): the talent sd net of schedule noise."""
    return math.sqrt(max(0.0, float(s_res) ** 2 - float(s_sched) ** 2))


# --------------------------------------------------------------------------
# T2: the club PA and IP budget
# --------------------------------------------------------------------------

def allocate(players: list[dict], budget: float) -> dict:
    """One side of a club's budget. ``players`` carry ``pt`` (projected PA or
    IP, the cap) and ``war`` (the champion mean WAR at that playing time).
    Every allocation is the player's own projection; when the club's sum
    exceeds ``budget`` each is scaled down pro rata, so the WAR carried is
    scaled by the same factor; a sum under the budget leaves a shortfall
    filled at replacement (0 WAR). Returns the scale, the sums and the WAR."""
    pts = [max(0.0, float(p.get("pt") or 0.0)) for p in players]
    wars = [float(p.get("war") or 0.0) for p in players]
    pt_sum = sum(pts)
    b = max(0.0, float(budget or 0.0))
    scale = 1.0 if (pt_sum <= b or pt_sum <= 0.0) else b / pt_sum
    return {
        "n": len(players), "budget": b, "pt_sum": round(pt_sum, 1),
        "pt_allocated": round(min(pt_sum, b), 1),
        "shortfall": round(max(0.0, b - pt_sum), 1),
        "scale": scale,
        "war_unscaled": round(sum(wars), 3),
        "war": round(sum(w * scale for w in wars), 3),
    }


def budgeted_club_war(hitters: list[dict], pitchers: list[dict],
                      budget_pa: float, budget_ip: float) -> dict:
    """T2 for one club and one season: the PA side and the IP side allocated
    separately, the WAR they carry summed."""
    hit = allocate(hitters, budget_pa)
    pit = allocate(pitchers, budget_ip)
    return {"war": round(hit["war"] + pit["war"], 3),
            "war_unscaled": round(hit["war_unscaled"] + pit["war_unscaled"], 3),
            "hit": hit, "pit": pit}


def recenter(wins_raw: dict, league_wins: float = 2430.0) -> tuple[dict, float]:
    """The 2,430 pin: one uniform shift so the clubs sum to ``league_wins``."""
    if not wins_raw:
        return {}, 0.0
    shift = (float(league_wins) - sum(float(v) for v in wins_raw.values())) / len(wins_raw)
    return {o: float(v) + shift for o, v in wins_raw.items()}, shift


# --------------------------------------------------------------------------
# T3: runs
# --------------------------------------------------------------------------

def league_runs_per_team(consts: dict) -> float:
    """League runs per team-season from the held constants of the last
    completed season: lg_r_pa x lg_pa over the season's team-games (two per
    game), per 162. By the league identity the same number is runs allowed."""
    games = float(consts.get("mlb_games") or 2430.0)
    team_games = 2.0 * games
    return float(consts["lg_r_pa"]) * float(consts["lg_pa"]) / team_games * GAMES


def park_factors(season: int, cache_dir: Path | None = None,
                 column: str = PF_COLUMN) -> tuple[dict[str, float], dict]:
    """{org: park factor / 100} from the latest COMPLETE FanGraphs park
    factor cache at or before ``season`` (.cache/fangraphs/park_factors_<s>.json),
    with a receipt naming the file used. A club absent from the file is
    neutral (1.0) and named."""
    d = Path(cache_dir) if cache_dir else PARK_FACTOR_DIR
    used = None
    rows: list[dict] = []
    for s in range(int(season), int(season) - 6, -1):
        p = d / f"park_factors_{s}.json"
        if not p.exists():
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not blob.get("complete"):
            continue
        rows = blob.get("rows") or []
        used = s
        break
    out: dict[str, float] = {}
    for r in rows:
        org = _ORG_BY_NICKNAME.get(str(r.get("Team") or ""))
        v = r.get(column)
        if org and isinstance(v, (int, float)):
            out[org] = float(v) / PF_NEUTRAL
    missing = sorted(o for o in ORG_NICKNAMES if o not in out)
    for o in missing:
        out[o] = 1.0
    meta = {"requested_season": int(season), "season_used": used, "column": column,
            "n_rows": len(rows), "neutral_fallback": missing,
            "file": (f"park_factors_{used}.json" if used else None)}
    return out, meta


def pythag_wins(rs, ra, g: float = GAMES) -> float | None:
    """Pythagenpat wins: g x RS^e / (RS^e + RA^e), e = ((RS + RA) / g)^0.287
    (proj_export._pythag_pct with games known; pinned by test)."""
    if rs is None or ra is None or rs < 0 or ra < 0 or (rs + ra) <= 0 or not g or g <= 0:
        return None
    rpg = (rs + ra) / g
    e = rpg ** PYTHAGENPAT_EXP
    num = rs ** e
    den = num + ra ** e
    return (g * num / den) if den > 0 else None


def club_runs(lg_runs: float, bat_bsr: float, fip_raa: float, fld: float,
              pf: float = 1.0, g: float = GAMES) -> dict:
    """One club's T3 line. ``bat_bsr`` is the roster's batting plus
    baserunning runs at the allocated PA; ``fip_raa`` the staff's FIP runs
    saved above average at the allocated IP (positive = fewer runs than the
    league); ``fld`` the club's fielding runs; ``pf`` the club park factor
    as a multiplier (1.0 neutral), applied to both sides at the team level."""
    rs = (float(lg_runs) + float(bat_bsr or 0.0)) * float(pf)
    ra = (float(lg_runs) - float(fip_raa or 0.0) - float(fld or 0.0)) * float(pf)
    rs = max(0.0, rs)
    ra = max(0.0, ra)
    pw = pythag_wins(rs, ra, g)
    return {"rs": round(rs, 1), "ra": round(ra, 1), "runDiff": round(rs - ra, 1),
            "pythW": round(pw, 1) if pw is not None else None,
            "pythL": round(g - pw, 1) if pw is not None else None,
            "pf": round(float(pf), 4)}


def component_runs(block: dict | None, side: str, scale: float = 1.0,
                   horizon: int = 1) -> dict:
    """The runs one player's component block (proj_components.project_
    components' side block) adds to his club at season ``horizon``, scaled
    by the club's budget factor. A component the heads do not project
    counts 0 and is named."""
    out = {"bat_bsr": 0.0, "fld": 0.0, "fip_raa": 0.0, "not_projected": [], "pt": 0.0}
    if not block:
        out["not_projected"].append(f"{side}:no_block")
        return out
    line = (block.get("lines") or {}).get(horizon) or {}
    s = float(scale)
    if side == "hit":
        bat, bsr, fld = line.get("bat"), line.get("bsr"), line.get("fld")
        out["pt"] = float(line.get("pa") or 0.0) * s
        if bat is None:
            out["not_projected"].append("hit:bat")
        if bsr is None:
            out["not_projected"].append("hit:bsr")
        if fld is None:
            out["not_projected"].append("hit:fld")
        out["bat_bsr"] = (float(bat or 0.0) + float(bsr or 0.0)) * s
        out["fld"] = float(fld or 0.0) * s
    else:
        ip = line.get("ip")
        f100 = line.get("fip_runs_100ip")
        out["pt"] = float(ip or 0.0) * s
        if ip is None or f100 is None:
            out["not_projected"].append("pit:fip_runs")
        else:
            out["fip_raa"] = float(f100) * float(ip) / 100.0 * s
    return out


def runs_identity(clubs: dict, lg_runs: float, tol: float = RUNS_IDENTITY_TOL) -> dict:
    """The league identity report: the 30 clubs' RS and RA sums against each
    other and against 30 x the league mean, and whether |sum RS - sum RA|
    sits within ``tol`` of league runs. Reported, never enforced: no
    team-level recalibration (gate section 7)."""
    rs = sum(float((v or {}).get("rs") or 0.0) for v in clubs.values())
    ra = sum(float((v or {}).get("ra") or 0.0) for v in clubs.values())
    league = float(lg_runs) * len(clubs)
    return {"n_clubs": len(clubs), "rs_sum": round(rs, 1), "ra_sum": round(ra, 1),
            "league_sum": round(league, 1), "rs_minus_ra": round(rs - ra, 1),
            "rs_minus_league": round(rs - league, 1), "ra_minus_league": round(ra - league, 1),
            "tol_share": tol, "tol_runs": round(league * tol, 1),
            "within_tol": bool(abs(rs - ra) <= league * tol)}


# --------------------------------------------------------------------------
# The preview file (every flag False) and the DEV schedule cache
# --------------------------------------------------------------------------

def write_preview(payload: dict, path: Path | None = None) -> Path:
    p = Path(path) if path else (PREVIEW_DIR / PREVIEW_NAME)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload.setdefault("written_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def schedule_path(season: int, cache_dir: Path | None = None) -> Path:
    return (Path(cache_dir) if cache_dir else SCHEDULE_DIR) / f"schedule_{int(season)}.json"
