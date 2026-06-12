# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Projections module - sidecar export (data/mlb_projections.json).

The FA module's Gate-1-validated projection engine, applied to the WHOLE
league: every player with recent MLB history gets a multi-year bWAR path
(mean + P10/P90 probability buckets), and PROSPX prospects get post-ETA
paths from the calibrated FV outcome model. One surface, two clearly
labeled sources:

  VETERANS   the FA Marcel engine (components -> composites -> fitted WAR
             map), decayed along the survivorship-corrected aging curves;
             buckets are the Gate-1 empirical year-1 residual quantiles
             decayed through the same curves (identical machinery to the
             FA class board - fa_market.contract_war_path).
  PROSPECTS  the value_framework outcome model: P(bucket|FV) x per-bucket
             WAR trajectories (FV-scaled, aging-shaped from projected
             debut age), starting at the PROSPX ETA. Floor/ceiling are
             the 10th/90th percentile OUTCOME BUCKETS of the categorical
             - a prospect's downside is busting, not a residual ribbon.

Dollars: each projected season is priced through the platform's convex
tier curve at the winter's ex-ante FA $/WAR level, escalated by the
configured $/WAR inflation per season - the same pricing the FA rational
value and the (re-anchored) prospect surplus use. Veteran SURPLUS only
exists where a real contract exists: salary-known seasons (Spotrac
contract pages) net against production value and discount at the platform
9%; arb/pre-arb seasons carry projections but no surplus claim. Prospect
surplus IS the platform surplus value (control-window, service-time
aware) - never a parallel number.

Run: python proj_export.py   (also wired into run_monthly after the FA
refresh). Reads only caches + committed artifacts; never writes PROSPX
data (read-only consumer, same contract as the FA module).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_class
import fa_ident
import fa_market as fm
import fa_projection as fp
import value_framework as vf
from scrapers import normalize_key

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FIRST_SEASON = 2027          # first fully projected season (2026 is in progress)
HORIZON = 5                  # 2027..2031
# Exposure floor for the veteran universe: at least one of the last three
# seasons with a real sample (sub-cup-of-coffee players add noise, not
# signal, and the engine's reliability buckets were fitted above this).
MIN_PA, MIN_IP = 100, 30

_BUCKET_ORDER = ("bust", "bench", "regular", "good", "star")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def _display_names() -> dict[int, str]:
    """{mlbam: display name} - the war_daily index inverted (the same
    identity source fa_ident resolves against, read in reverse)."""
    out: dict[int, str] = {}
    for _norm, cands in fa_ident.war_daily_index().items():
        for mid in cands:
            out.setdefault(mid, "")
    # second pass for the raw display string: war_daily_index normalizes
    # names away, so rebuild from pybaseball directly (cached by pybaseball).
    import pybaseball as pyb
    for fn in (pyb.bwar_bat, pyb.bwar_pitch):
        try:
            df = fn(return_all=True)
        except Exception:                                     # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                out[int(row.mlb_ID)] = str(row.name_common)
            except (TypeError, ValueError):
                continue
    return {k: v for k, v in out.items() if v}


def _season_value_usd(war: float, t: int, dpw_level: float) -> float:
    """One projected season priced on the platform's convex tier curve at
    the winter's ex-ante $/WAR level, escalated t seasons out."""
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    infl = float(vf._config().get("dollars_per_war_inflation", 0.05))
    return vf.tiered_war_value_usd(war) * (dpw_level / base_flat) * ((1 + infl) ** t)


def _winter_dpw(first_season: int) -> float:
    """Ex-ante $/WAR level for the first projected season, from the
    committed signings-implied series (last prior winter escalated)."""
    try:
        series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
        by = {int(k): float(v) for k, v in series["usd_per_war_by_winter"].items()}
    except (OSError, ValueError, KeyError):
        return fa_class._flat_dpw_usd()
    return fm.winter_dpw(by, first_season)


# ============================================================================
# Veterans - the FA engine over the whole league
# ============================================================================

def _veteran_rows(corpus: dict, names: dict[int, str],
                  contracts: dict[str, dict], dpw: float) -> list[dict]:
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    frac = fp.season_fraction(league, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, frac)
    r = float(vf._config()["discount_rate"])

    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row

    out: list[dict] = []
    for mlbam in set(by_player["hit"]) | set(by_player["pit"]):
        sides = {}
        for side, expo_key, floor in (("hit", "pa", MIN_PA), ("pit", "bf", 0)):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            if side == "hit":
                if max(h.get("pa") or 0 for h in hist) < MIN_PA:
                    continue
            elif max(h.get("ip") or 0 for h in hist) < MIN_IP:
                continue
            sides[side] = hist
        if not sides:
            continue
        # Two-way (the Ohtani fix): project BOTH sides through the engine
        # and SUM the season paths - a two-way player IS both stat lines,
        # not the larger one. Per-side paths ship too (warHit/warPit) so
        # the player page can render both sections. Bands sum per-side
        # quantiles (a conservative width: the sides aren't perfectly
        # correlated - disclosed in the export notes).
        two_way = len(sides) == 2
        paths: dict[str, dict] = {}
        ages: dict[str, float] = {}
        for s_key, hist_s in sides.items():
            age_prev = next((h.get("age") for h in hist_s if h.get("age")), None)
            if age_prev is None:
                continue
            age_s = age_prev + (FIRST_SEASON - hist_s[0]["season"])
            p_s = fm.contract_war_path(hist_s, s_key, FIRST_SEASON, HORIZON,
                                       age_s, curves, war_map, league,
                                       in_progress=in_prog)
            if p_s is not None:
                paths[s_key] = p_s
                ages[s_key] = age_s
        if not paths:
            continue
        two_way = two_way and len(paths) == 2
        if two_way:
            def _sum_arr(key):
                a = paths["hit"].get(key)
                b = paths["pit"].get(key)
                if not a or not b:
                    return None
                return [round((a[t] or 0) + (b[t] or 0), 2)
                        for t in range(min(HORIZON, len(a), len(b)))]
            war_arr = _sum_arr("war_by_year")
            # Band combination at assumed cross-side correlation rho=0.5
            # (a player's hitting and pitching seasons share health/PT
            # shocks but not skill shocks - a documented assumption, less
            # conservative than the previous straight quantile sum).
            _RHO = 0.5
            def _comb_band(key, sign):
                lo_h = paths["hit"].get(key); lo_p = paths["pit"].get(key)
                if not lo_h or not lo_p or not war_arr:
                    return None
                out = []
                mh_ = paths["hit"]["war_by_year"]; mp_ = paths["pit"]["war_by_year"]
                for tt in range(len(war_arr)):
                    dh = abs((mh_[tt] or 0) - (lo_h[tt] or 0))
                    dp = abs((mp_[tt] or 0) - (lo_p[tt] or 0))
                    d = (dh * dh + dp * dp + 2 * _RHO * dh * dp) ** 0.5
                    out.append(round(war_arr[tt] + sign * d, 2))
                return out
            p10_arr = _comb_band("war_by_year_p10", -1)
            p90_arr = _comb_band("war_by_year_p90", +1)
            path = paths.get("hit") or paths.get("pit")   # role/meta carrier
            age = max(ages.values())
        else:
            side = next(iter(paths))
            path = paths[side]
            age = ages[side]
            war_arr = path["war_by_year"][:HORIZON]
            p10_arr = (path.get("war_by_year_p10") or [None])[:HORIZON] or None
            p90_arr = (path.get("war_by_year_p90") or [None])[:HORIZON] or None
        name = names.get(mlbam)
        if not name:
            continue
        ct = contracts.get(normalize_key(name))
        m = {
            "key": normalize_key(name), "name": name, "age": age,
            "mlbam": mlbam,
            "src": "vet", "twoWay": True if two_way else None,
            "pos": "TWP" if two_way else ((ct or {}).get("position") or path["role"]),
            "team": (ct or {}).get("team_code"),
            "war": war_arr,
            "warP10": p10_arr,
            "warP90": p90_arr,
            # Champion MEAN year-1 for team aggregation (sum across both
            # sides for two-way). The displayed path may be the gated ML
            # quantile head, whose median-like points must not be summed.
            "warY1Champ": round(sum((paths[s].get("war_y1_champ")
                                     if paths[s].get("war_y1_champ") is not None
                                     else paths[s]["war_by_year"][0]) or 0.0
                                    for s in paths), 2),
        }
        if two_way:
            m["warHit"] = [round(w, 2) for w in paths["hit"]["war_by_year"][:HORIZON]]
            m["warPit"] = [round(w, 2) for w in paths["pit"]["war_by_year"][:HORIZON]]
        m["warTotal"] = round(sum(m["war"]), 1)
        if p10_arr:
            m["warTotalP10"] = round(sum(p10_arr), 1)
            m["warTotalP90"] = round(sum(p90_arr), 1)
        if ct:
            sal = {int(y): int(v) for y, v in (ct.get("salary_by_year") or {}).items()}
            m["thru"] = ct.get("signed_through")
            m["aav"] = ct.get("aav_usd")
            sur = []
            npv = 0.0
            any_sal = False
            for t in range(HORIZON):
                season = FIRST_SEASON + t
                s_usd = sal.get(season)
                if s_usd is None:
                    sur.append(None)
                    continue
                any_sal = True
                v_usd = _season_value_usd(m["war"][t], t, dpw)
                d_usd = v_usd - s_usd
                sur.append(round(d_usd / 1e6, 1))
                npv += d_usd / ((1 + r) ** t)
            if any_sal:
                m["sur"] = sur
                m["surNpv"] = int(npv)
        out.append(_clean(m))
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out


# ============================================================================
# Prospects - the calibrated FV outcome model, post-ETA
# ============================================================================

def _prospect_calibration_shift() -> float:
    """The SHIPPED intercept-only mean-path correction (prospect_path
    candidate #2, pre-registered + gated: held-out bias 0.341 -> 0.110
    on identical rows, MAE down, slope within tolerance). Fit on the
    first-3-season SUM; applied as shift/3 per season to the first three
    projected seasons. Display layer only - surplus keeps its own
    isotonic calibration (never double-corrected)."""
    try:
        d = json.loads((DATA_DIR / "prospect_path_eval.json").read_text(encoding="utf-8"))
        blk = d.get("calibration_intercept_only") or {}
        if blk.get("ship") and blk.get("full_window_shift") is not None:
            return float(blk["full_window_shift"])
    except (OSError, ValueError):
        pass
    return 0.0


def _prospect_rows(dpw: float) -> list[dict]:
    try:
        players = json.loads((DATA_DIR / "timeseries.json")
                             .read_text(encoding="utf-8")).get("players") or []
    except (OSError, ValueError):
        log.warning("mlb projections: timeseries.json unavailable - no prospects")
        return []
    cal_shift = _prospect_calibration_shift()
    out: list[dict] = []
    for p in players:
        fv = p.get("fv_close")
        eta = (p.get("eta") or {}).get("year")
        if (fv is None or fv < 45 or not eta or p.get("status") != "active"
                or eta > FIRST_SEASON + HORIZON - 1):
            continue
        pos = p.get("position")
        is_pit = vf.is_pitcher_position(pos)
        reliever = vf.is_reliever_position(pos)
        role = vf._role_key(is_pit)
        probs = vf.p_bucket_given_fv(float(fv), is_pit)
        if not probs:
            continue
        age = p.get("age")
        debut_age = (float(age) + max(0, int(eta) - (FIRST_SEASON - 1))) if age else None
        scale = vf._war_scale_for(float(fv), role)
        paths = [vf._bucket_season_wars(role, i, reliever, debut_age, scale)
                 for i in range(len(_BUCKET_ORDER))]
        n_yrs = len(paths[0])
        mean_path = [round(sum(pr * paths[i][t] for i, pr in enumerate(probs)), 2)
                     for t in range(n_yrs)]
        if cal_shift:
            # intercept-only mean correction, first three seasons (the
            # window it was fit on), floored at 0
            mean_path = [round(max(0.0, w - cal_shift / 3.0), 2) if t < 3 else w
                         for t, w in enumerate(mean_path)]

        def _q_bucket(q: float) -> int:
            cum = 0.0
            for i, pr in enumerate(probs):
                cum += pr
                if cum >= q:
                    return i
            return len(probs) - 1

        lo_b, hi_b = _q_bucket(0.10), _q_bucket(0.90)
        eta_yr = max(int(eta), FIRST_SEASON)
        sv = vf.surplus_value_mm(float(fv), is_pit, pos, age=age,
                                 eta_years=max(0.0, eta_yr - (FIRST_SEASON - 1)))
        out.append(_clean({
            "key": p.get("player_key"), "name": p.get("player_name"),
            "age": age, "src": "prospect", "fv": fv, "eta": eta_yr,
            "pos": pos, "team": p.get("org"),
            "war": [round(w, 2) for w in mean_path],
            "warP10": [round(w, 2) for w in paths[lo_b]],
            "warP90": [round(w, 2) for w in paths[hi_b]],
            "warTotal": round(sum(mean_path), 1),
            "warTotalP10": round(sum(paths[lo_b]), 1),
            "warTotalP90": round(sum(paths[hi_b]), 1),
            "bucketLo": _BUCKET_ORDER[lo_b], "bucketHi": _BUCKET_ORDER[hi_b],
            "pBust": round(probs[0], 3),
            "surNpv": int(sv * 1e6) if sv is not None else None,
        }))
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out


# ============================================================================
# Payload
# ============================================================================

def _cohort_intercepts() -> dict[str, float]:
    """side:ageband -> additive year-1 WAR intercept, from the committed
    retro backtest (proj_backtest.py, fit on 2022-24 residuals, won the
    2025 holdout 7.71 vs 7.76 team-MAE). Applied at the TEAM ROLL-UP only
    - the per-player display keeps the engine's mean (the gate validated
    the team-level improvement, nothing finer). Missing artifact = no-op."""
    try:
        d = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
        return (d.get("retro_backtest") or {}).get("cohort_intercepts_fit_2022_24") or {}
    except (OSError, ValueError):
        return {}


def _age_band(age) -> str:
    a = int(age) if age else 28
    for lo, hi in ((0, 25), (26, 29), (30, 33), (34, 99)):
        if lo <= a <= hi:
            return f"{lo}-{hi}"
    return "34-99"


def _row_sides(m: dict) -> list[str]:
    if m.get("twoWay"):
        return ["hit", "pit"]              # two-way = both stat lines
    return ["pit" if (m.get("pos") or "") in ("SP", "RP", "P") else "hit"]


def _depth_pool(corpus: dict, names: dict[int, str],
                contracts: dict[str, dict], vet_mlbams: set) -> tuple[dict, dict]:
    """Year-1 WAR for every projectable player the exposure floors exclude
    from the display list - the retro backtest showed the floor-gated
    universe carries only ~560 of the league's ~1000 WAR while the full
    >=1-input-season population, on real rosters, sums to ~870-930. These
    players never appear in the UI table; their year-1 WAR joins the Team
    Outlook roll-up per team (contract team), shrinking the uniform depth
    allowance to a small remainder. Returns ({org: war_sum}, accounting)."""
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, fp.season_fraction(league, FIRST_SEASON - 1))
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row
    team_war: dict[str, float] = defaultdict(float)
    n = n_unassigned = 0
    war_unassigned = 0.0
    for mlbam in (set(by_player["hit"]) | set(by_player["pit"])) - vet_mlbams:
        w1 = 0.0
        age_any = None
        for side in ("hit", "pit"):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            age_prev = next((h.get("age") for h in hist if h.get("age")), None)
            age = (age_prev + (FIRST_SEASON - hist[0]["season"])) if age_prev else None
            age_any = age or age_any
            proj = fp.project_player(hist, side, FIRST_SEASON, curves, league,
                                     age, in_progress=in_prog)
            if proj is None:
                continue
            w1 += float(fp.war_from_projection(proj, side, war_map, league,
                                               FIRST_SEASON) or 0.0)
        if not w1:
            continue
        n += 1
        name = names.get(mlbam)
        ct = contracts.get(normalize_key(name)) if name else None
        org = (ct or {}).get("team_code")
        if org:
            team_war[org] += w1
        else:
            n_unassigned += 1
            war_unassigned += w1
    acct = {"n_depth_players": n, "depth_war_sum": round(sum(team_war.values()), 1),
            "n_unassigned": n_unassigned, "war_unassigned": round(war_unassigned, 1)}
    return dict(team_war), acct


def _org_farm_blocks() -> dict[str, dict]:
    """Farm-system context joined onto the Team Outlook rows - the org
    dashboard columns the retired /teams/ page carried (merged into the
    projections module 2026-06-12): farm rank + grade score, net active
    prospect surplus, and the top prospect with his FV."""
    try:
        ts = json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for o in ts.get("org_summary") or []:
        org = o.get("org")
        if not org:
            continue
        top = (o.get("prospects") or [{}])[0]
        out[org] = {
            "farmRank": o.get("farm_rank"),
            "farmScore": o.get("farm_score"),
            "farmSurplusMM": o.get("_active_surplus_net_mm"),
            "topProspect": ({"name": top.get("name"),
                             "key": top.get("player_key"),
                             "fv": top.get("fv_label")}
                            if top.get("name") else None),
        }
    return out


def _team_outlook(vets: list[dict], prospects: list[dict],
                  depth_team_war: dict | None = None,
                  depth_acct: dict | None = None,
                  intercepts: dict | None = None) -> list[dict]:
    """First-season team WAR roll-up -> projected wins (47.7 replacement
    baseline + roster WAR). PRE-FREE-AGENCY frame: the upcoming winter's
    FA class is unassigned (their WAR sits on no roster), and players
    below the exposure floors count as replacement - both stated on the
    surface. Prospects contribute at their org when their ETA is the
    first projected season. Forward gate: scored against the season's
    actual standings when it completes (registry row carries the clock)."""
    REPLACEMENT_WINS = 47.7
    # bWAR is calibrated so the league's players sum to ~1000 WAR every
    # season (verified 1000/1000/1000 for 2023-25 in war_daily). The
    # rostered universe captures ~56% of that pool (Marcel regression +
    # shrunk playing time + exposure floors), which read as a ~15-win
    # negative bias on every team (the best team projected 83 wins).
    LEAGUE_WAR_POOL = 1000.0
    LEAGUE_WINS = 2430.0
    teams: dict[str, dict] = {}
    for m in vets:
        tm = m.get("team")
        w = (m.get("war") or [None])[0]
        if not tm or w is None:
            continue
        t_ = teams.setdefault(tm, {"war": 0.0, "n": 0, "top": []})
        # Sum the champion MEAN (warY1Champ): the displayed ML quantile
        # point is median-like and sums to ~half the league's WAR pool
        # (measured 2026-06-12). Display ranking still uses the shown war.
        t_["war"] += m.get("warY1Champ") if m.get("warY1Champ") is not None else w
        t_["n"] += 1
        t_["top"].append((w, m.get("name"), m.get("key")))
    for m in prospects:
        tm = m.get("team")
        if not tm or m.get("eta") != FIRST_SEASON:
            continue
        w = (m.get("war") or [None])[0]
        if w is None:
            continue
        t_ = teams.setdefault(tm, {"war": 0.0, "n": 0, "top": []})
        t_["war"] += w
        t_["n"] += 1
        t_["top"].append((w, m.get("name"), m.get("key")))
    farm = _org_farm_blocks()
    # Calibration v2 (2026-06-12, retro-backtest-driven - proj_backtest.py):
    #   1. cohort intercepts (side x age band, fit 2022-24, won the 2025
    #      holdout) adjust each ROSTERED player's year-1 contribution;
    #   2. the sub-floor DEPTH POOL joins per team (the floors hid ~40% of
    #      the league's WAR from the roll-up - the original 83-win-Dodgers
    #      level bug);
    #   3. a small uniform remainder recenters the league to 2,430 wins
    #      (new entrants ~61 WAR/season + unassigned depth). Ordering moves
    #      only through measured, committed per-team terms.
    intercepts = intercepts or {}
    depth_team_war = depth_team_war or {}
    coh_adj: dict[str, float] = defaultdict(float)
    for m in vets:
        tm = m.get("team")
        if not tm or (m.get("war") or [None])[0] is None:
            continue
        for side in _row_sides(m):
            coh_adj[tm] += intercepts.get(f"{side}:{_age_band(m.get('age'))}", 0.0)
    for tm, t_ in teams.items():
        t_["war_cal"] = (t_["war"] + coh_adj.get(tm, 0.0)
                         + depth_team_war.get(tm, 0.0))
    raw_wins_sum = 30 * REPLACEMENT_WINS + sum(t_["war"] for t_ in teams.values())
    cal_wins_sum = 30 * REPLACEMENT_WINS + sum(t_["war_cal"] for t_ in teams.values())
    remainder = (LEAGUE_WINS - cal_wins_sum) / max(len(teams), 1)
    out = []
    for tm, t_ in teams.items():
        t_["top"].sort(reverse=True)
        wins = round(REPLACEMENT_WINS + t_["war_cal"] + remainder, 1)
        out.append({"team": tm, "war": round(t_["war"], 1),
                    "wins": wins,
                    "losses": round(162.0 - wins, 1),
                    "winsRaw": round(REPLACEMENT_WINS + t_["war"], 1),
                    "depthWar": round(t_["war_cal"] - t_["war"] + remainder, 1),
                    "n": t_["n"],
                    "top": [{"name": n, "key": k, "war": round(w, 1)}
                            for w, n, k in t_["top"][:3]],
                    "farm": farm.get(tm)})
    out.sort(key=lambda r: -r["wins"])
    _write_team_outlook_eval(out, raw_wins_sum, remainder, depth_acct or {})
    return out


def _write_team_outlook_eval(rows: list[dict], raw_wins_sum: float,
                             remainder: float, depth_acct: dict) -> None:
    """data/team_outlook_eval.json - the league-sum accounting plus the
    shipped calibration composition, committed per the eval-artifact
    standing rule. The retro_backtest block (proj_backtest.py) is
    PRESERVED across re-exports - it is the measurement the calibration
    rests on. The forward gate (MAE vs actual wins) stays pending until
    the first projected season completes."""
    try:
        payload = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    payload.update({
        "generated_at": date.today().isoformat(),
        "first_season": FIRST_SEASON,
        "league_sum_accounting": {
            "roster_war_sum": round(sum(r["war"] for r in rows), 1),
            "league_war_benchmark": 1000,
            "benchmark_basis": "actual league bWAR sums 1000/1000/1000 for 2023/2024/2025 (war_daily)",
            "raw_wins_sum": round(raw_wins_sum, 1),
            "target_wins_sum": 2430,
            "depth_pool": depth_acct,
            "remainder_recenter_wins_per_team": round(remainder, 2),
            "coverage_decomposition_2025": {
                "returning_player_war": 940, "new_entrant_war": 61,
                "new_entrant_players": 253,
                "note": "new-entrant WAR is covered by the ETA-prospect block "
                        "and the recentering remainder; the original level gap "
                        "was the exposure-floor universe (see retro_backtest)"},
        },
        "calibration": {
            "kind": "v2: per-team sub-floor depth pool + cohort intercepts "
                    "(side x age band, retro-backtest-fit 2022-24, holdout-gated) "
                    "+ small uniform remainder to the 2,430-win league sum",
            "limitations": [
                "depth-pool team assignment needs a contract row; unassigned depth WAR rides the uniform remainder",
                "spread stays projection-compressed (correct for a mean projection; bands carry the uncertainty)"],
        },
        "forward_gate": {
            "status": "pending",
            "first_scoreable": f"end of the {FIRST_SEASON} season",
            "metric": "MAE vs actual wins; baseline = prior-season wins carry-forward"},
    })
    (DATA_DIR / "team_outlook_eval.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")


def build_payload() -> dict:
    corpus = fp.build_corpus()
    names = _display_names()
    from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key, _SPOTRAC_TEAM_SLUGS
    slug_to_org = {slug: code for code, slug in _SPOTRAC_TEAM_SLUGS.items()}
    contracts = {}
    for key, c in build_contracts_by_key(scrape_all_spotrac_contracts()).items():
        contracts[key] = {**c, "team_code": slug_to_org.get(c.get("team_slug"))}
    dpw = _winter_dpw(FIRST_SEASON)
    vets = _veteran_rows(corpus, names, contracts, dpw)
    prospects = _prospect_rows(dpw)
    depth_team_war, depth_acct = _depth_pool(
        corpus, names, contracts, {m["mlbam"] for m in vets if m.get("mlbam")})
    team_outlook = _team_outlook(vets, prospects, depth_team_war, depth_acct,
                                 _cohort_intercepts())
    cfg = vf._config()
    re_anchor = (cfg["dollars_per_war"].get("_fa_reanchor") or {})
    return {
        "generated_at": date.today().isoformat(),
        "first_season": FIRST_SEASON, "horizon": HORIZON,
        "dpw_usd": int(dpw),
        "dpw_infl": float(cfg.get("dollars_per_war_inflation", 0.05)),
        "dpw_reanchor": re_anchor or None,
        "n_vets": len(vets), "n_prospects": len(prospects),
        "vets": vets, "prospects": prospects,
        "team_outlook": team_outlook,
        "notes": [
            "veterans: the FA module's Gate-1-validated Marcel engine; bands = Gate-1 empirical year-1 residual quantiles decayed along the fitted aging curves",
            "prospects: P(bucket|FV) x calibrated per-bucket WAR trajectories from projected debut age, starting at the PROSPX ETA; floor/ceiling = 10th/90th-percentile OUTCOME buckets",
            f"dollars: convex tier pricing at the {FIRST_SEASON} ex-ante FA $/WAR level, escalated per season; veteran surplus only on salary-known (contracted) seasons, discounted at the platform rate",
            "two-way players project BOTH sides, summed per season (per-side paths in warHit/warPit; bands combine at assumed cross-side correlation rho=0.5 - documented)",
            f"veteran universe: >= {MIN_PA} PA or >= {MIN_IP} IP in one of the last three seasons",
        ],
    }


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    (DATA_DIR / "mlb_projections.json").write_text(raw, encoding="utf-8")
    log.info("mlb projections export: %dKB, %d vets + %d prospects",
             len(raw) // 1024, payload["n_vets"], payload["n_prospects"])
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
