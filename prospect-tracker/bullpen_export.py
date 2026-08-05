# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Bullpen Leaderboards sidecar (data/bullpen_leaderboards.json).

Assembles the REM+ reliever board + team Bullpen+ + depth charts from REACHABLE
sources (FanGraphs is 403-blocked here):

  SKILL CORE   MLB StatsAPI season pitching leaderboard (playerPool=all) - one
               combined season line per pitcher with the proper team, holds,
               inherited runners, and every FIP input (K/BB/HBP/HR/IP/BF).
               Traded players come back as a single total under their most
               recent club, so there is no same-city ambiguity or multi-stint
               fragmentation (the trap Baseball-Reference's city-name Tm has).
  SwStr%       optional enrichment from pybaseball.pitching_stats_bref (StatsAPI
               has no swinging-strike count); best-effort, null when unavailable.
  LEVERAGE     mlb_leverage.fetch_season_leverage - gmLI / WPA / WPA-LI / SD / MD
               self-computed from the StatsAPI winProbability feed, joined by
               MLBAM id.

These feed rem_plus.score_pool(), which filters to true relievers, anchors REM+
to the reliever pool (100 = average), and rolls up team bullpens.

Run: `python bullpen_export.py [season] [leverage_game_limit]`. Also wired into
run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing fetches at
import; any pull failure logs and returns 0 rather than aborting the caller.
`leverage_game_limit` caps the winProbability walk for a fast partial refresh
(the skill core stays full-season; only the Impact columns are partial, which
the coverage block discloses)."""
from __future__ import annotations

import bisect
import functools
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import feed_cache  # hardened, 429-retrying requests session
import rem_plus
from rem_plus import Reliever

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "bullpen_leaderboards.json"
HISTORY_PATH = DATA_DIR / "bullpen_history.json"
# Yearly reliever-history window: the seasons the /mlbstats/ history tabs offer
# (ex-2020 COVID short season). Cached winProbability makes the walk fast.
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]
EVAL_PATH = DATA_DIR / "rem_plus_eval.json"
LEVCON_PATH = DATA_DIR / "leverage_consistency_eval.json"
MULTIYR_PATH = DATA_DIR / "rem_plus_multiyear_eval.json"
# frozen trailing-window vintage for WAR/PA+ and WAR/IP+ (all three anchor pools
# live in one artifact, one block each); see join_war_rate_3yr
WAR_RATE_MULTIYR_PATH = DATA_DIR / "war_rate_plus_multiyear_eval.json"

STATSAPI = "https://statsapi.mlb.com/api/v1"


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def ip_to_float(ip) -> float:
    """Convert MLB IP notation (X.1 = X+1/3, X.2 = X+2/3) to true decimal."""
    v = _num(ip)
    if v is None:
        return 0.0
    whole = int(v)
    outs = round((v - whole) * 10)
    if outs >= 3:  # guard against a true-decimal input sneaking in
        return v
    return whole + outs / 3.0


# --------------------------------------------------------------------------- #
# data pulls (network-gated: only run inside export())
# --------------------------------------------------------------------------- #
def _get_json(path: str, params: dict) -> dict:
    resp = feed_cache.SESSION.get(f"{STATSAPI}/{path}", params=params, timeout=45)
    resp.raise_for_status()
    return resp.json()


@functools.lru_cache(maxsize=1)
def _team_abbrev_map() -> dict:
    try:
        data = _get_json("teams", {"sportId": 1})
        return {t["id"]: t.get("abbreviation") for t in data.get("teams", [])}
    except Exception as e:
        _log.warning("team abbreviation map fetch failed: %s", e)
        return {}


@functools.lru_cache(maxsize=2)
def _active_mlbam_ids(season: int) -> Optional[frozenset]:
    """Set of MLBAM ids on a current ACTIVE roster (26-man), fetched ONCE per
    season and cached. Walks the 30 club active rosters from the StatsAPI teams
    roster endpoint and unions the person ids.

    Returns None on any failure so the caller does NOT filter (never break the
    board): an unreachable roster feed must leave the depth ladders intact rather
    than blank them. rosterType=active (not 40Man) so a demoted arm optioned to
    Triple-A (e.g. Blade Tidwell) is correctly dropped."""
    try:
        teams = _get_json("teams", {"sportId": 1}).get("teams", [])
    except Exception as e:
        _log.warning("active-roster team list fetch failed: %s", e)
        return None
    if not teams:
        return None
    ids: set = set()
    any_ok = False
    for t in teams:
        tid = t.get("id")
        if not tid:
            continue
        try:
            data = _get_json(f"teams/{tid}/roster", {"rosterType": "active", "season": int(season)})
        except Exception as e:
            _log.warning("active-roster fetch team %s failed: %s", tid, e)
            continue
        for r in data.get("roster", []):
            pid = (r.get("person") or {}).get("id")
            if pid:
                ids.add(int(pid))
                any_ok = True
    # if not a single roster came back, treat it as a total failure (do not filter)
    return frozenset(ids) if any_ok else None


def _apply_roster_filter(teams: list, active_ids: Optional[frozenset]) -> int:
    """Drop depth-ladder entries whose MLBAM (depth row 'key' = str(mlbam)) is not
    on a current active roster. `active_ids` None => roster fetch failed, so do NOT
    filter. An unidentifiable key is KEPT (never over-filter). Returns the number
    of off-roster arms dropped."""
    if not active_ids:
        return 0
    dropped = 0
    for t in teams:
        depth = t.get("depth")
        if not depth:
            continue
        kept = []
        for d in depth:
            try:
                mid = int(d.get("key"))
            except (TypeError, ValueError):
                kept.append(d)   # can't identify the player -> keep
                continue
            if mid in active_ids:
                kept.append(d)
            else:
                dropped += 1
        t["depth"] = kept
    return dropped


def load_season_pitching(season: int) -> list[dict]:
    """All MLB pitchers' season lines from the StatsAPI leaderboard (playerPool
    'all' so relievers are included). One combined row per player. [] on any
    failure (offline / API change)."""
    try:
        data = _get_json("stats", {
            "stats": "season", "group": "pitching", "season": int(season),
            "sportId": 1, "gameType": "R", "playerPool": "all", "limit": 3000})
    except Exception as e:
        _log.warning("StatsAPI season pitching (%s) failed: %s", season, e)
        return []
    stats = data.get("stats") or []
    if not stats:
        return []
    tmap = _team_abbrev_map()
    out = []
    for s in stats[0].get("splits", []):
        st = s.get("stat") or {}
        pl = s.get("player") or {}
        tm = s.get("team") or {}
        pid = pl.get("id")
        if not pid:
            continue
        # drop position players pitching mop-up (their primary position is not P)
        pos = (s.get("position") or {}).get("abbreviation")
        if pos and pos != "P":
            continue
        out.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""),
            "team": tmap.get(tm.get("id")) or "",
            "G": st.get("gamesPitched"), "GS": st.get("gamesStarted"),
            "SV": st.get("saves"), "HLD": st.get("holds"),
            "IP": st.get("inningsPitched"), "ER": st.get("earnedRuns"),
            "R": st.get("runs"), "BB": st.get("baseOnBalls"),
            "SO": st.get("strikeOuts"), "HR": st.get("homeRuns"),
            "HBP": st.get("hitByPitch"), "BF": st.get("battersFaced"),
            "Pit": st.get("numberOfPitches"),
            "IR": st.get("inheritedRunners"), "IRS": st.get("inheritedRunnersScored"),
            # starter-side context (SEM+): durability + a batted-ball signal
            "CG": st.get("completeGames"), "GO": st.get("groundOuts"),
            "AO": st.get("airOuts"), "Strk": st.get("strikes"),
        })
    return out


def load_bref_swstr(season: int) -> dict:
    """Optional SwStr% enrichment from Baseball-Reference (StatsAPI has no
    swinging-strike count). {mlbam: swstr_pct}; {} on any failure."""
    try:
        import pybaseball as pyb
        df = pyb.pitching_stats_bref(int(season))
    except Exception as e:
        _log.warning("bref SwStr enrichment unavailable: %s", e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            mid = r.get("mlbID")
            # bref StS is already the swinging-strike RATE (e.g. 0.19), not a count
            sts_rate = _num(r.get("StS"))
            if mid is None or sts_rate is None:
                continue
            try:
                out[int(float(mid))] = round(sts_rate, 4)
            except (TypeError, ValueError):
                continue
    except Exception as e:
        _log.warning("bref SwStr parse failed: %s", e)
    return out


def build_relievers(rows: list[dict], leverage: dict, swstr: Optional[dict] = None) -> list[Reliever]:
    """StatsAPI season rows -> Reliever records, joined to leverage (by MLBAM id)
    and the optional SwStr% enrichment."""
    swstr = swstr or {}
    out: list[Reliever] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        pit = _num(r.get("Pit")) or 0.0
        sw = swstr.get(mlbam)
        # None (not 0.0) when the bref SwStr enrichment is absent: swstr_pct downstream
        # (_safe_div(sts, pit)) then reports null "unknown", not a fake 0% swinging-strike
        # rate that read as a real (terrible) value for every player missing a bref row.
        sts = (sw * pit) if (sw is not None and pit) else None
        rel = Reliever(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            g=_num(r.get("G")) or 0.0, gs=_num(r.get("GS")) or 0.0,
            ip=ip_to_float(r.get("IP")), tbf=_num(r.get("BF")) or 0.0,
            so=_num(r.get("SO")) or 0.0, bb=_num(r.get("BB")) or 0.0,
            hbp=_num(r.get("HBP")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            er=_num(r.get("ER")) or 0.0, r=_num(r.get("R")) or 0.0,
            pit=pit, sts=sts,
            sv=_num(r.get("SV")) or 0.0, hld=_num(r.get("HLD")) or 0.0,
        )
        lev = leverage.get(int(mlbam))
        if lev:
            rel.gmli = lev.get("gmli")
            rel.wpa = lev.get("wpa")
            rel.wpa_li = lev.get("wpa_li")
            rel.sd = lev.get("sd")
            rel.md = lev.get("md")
            rel.entry_inning = lev.get("entry_inning")
        out.append(rel)
    return out


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        v = (j.get("verdict") or {})
        return v.get("status") or "provisional"
    except Exception:
        return "provisional"


def _backtest() -> dict:
    """Compact accountability card from data/rem_plus_eval.json - the forward
    chained out-of-sample backtest that earned REM+ its validated verdict. Shown
    to users on /mlbstats/ so a validated model advertises its rigor."""
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fs = j.get("forward_spearman_vs_RA9_next") or {}
    gap = (j.get("gap_ci_vs_RA9_next") or {}).get("vs_era") or {}
    mk = j.get("market_check_aav") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_rem_plus": fs.get("rem_plus"),
        "rho_fip": fs.get("raw_fip"),
        "rho_era": fs.get("era"),
        "gap_vs_era_lo95": gap.get("lo95"),
        "market_rho": mk.get("rho_leverage_weighted_vs_aav"),
        "disclaimer": ("REM+ predicts next-year run prevention out of sample. Leverage (gmLI, WPA, "
                       "Shutdowns minus Meltdowns) rides separate Impact columns because it is "
                       "assigned by the manager, not a repeatable skill."),
    }


def _join_leverage_consistency(relievers: list[dict]) -> int:
    """Stamp gmli_3yr / pool percentile / stability tag onto reliever rows
    from the committed leverage-consistency artifact
    (tools/leverage_consistency_eval.py, gate-validated 2026-07: pooled
    Y->Y+1 rho 0.4683 vs the 0.30 bar). Deployment context only - never an
    input to REM+. Missing artifact or unmatched player -> fields absent and
    the column renders blank. Returns the number of rows stamped."""
    try:
        pv = json.loads(LEVCON_PATH.read_text(encoding="utf-8"))["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return 0
    n = 0
    for r in relievers:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r["gmli_3yr"] = p.get("gmli_3yr")
        r["gmli_3yr_pct"] = p.get("pct")
        r["gmli_3yr_tag"] = p.get("tag")
        if r["gmli_3yr"] is not None:   # count only rows that will render
            n += 1
    return n


def _join_rem_plus_3yr(relievers: list[dict]) -> dict:
    """Stamp rem_plus_3yr / percentile / tag onto reliever rows from the committed
    multi-year artifact (tools/rem_plus_lab.py, X-R2: 3-year IP-weighted REM+, a
    more stable talent read than one season). Companion SKILL column - a longer
    window of the same REM+ scale, not a new metric. Missing artifact or unmatched
    player -> fields absent and the column renders blank.

    VINTAGE, NOT PIPELINE OUTPUT. These values are read VERBATIM from a FROZEN
    lab artifact; nothing here recomputes them, so a board row can show a
    same-day 1-year REM+ beside a 3-year REM+ that was frozen weeks earlier, and
    any arm who entered the pool after the lab last ran is simply blank. That
    divergence is real and must not be silent, so this returns the artifact's
    vintage block (generated_at / season / window / pool size) for the payload
    to carry and the frontend to disclose. Computing the window in-pipeline
    would need three seasons of StatsAPI pulls plus the lab's IP-weighting and
    pct/tag banding conventions - a new pipeline stage with its own eval, not a
    correctness fix - so this labels the divergence instead of unifying it."""
    meta = {"source": MULTIYR_PATH.name, "n_stamped": 0, "available": False}
    try:
        art = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
    n = 0
    for r in relievers:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r["rem_plus_3yr"] = p.get("rem_plus_3yr")
        r["rem_plus_3yr_pct"] = p.get("pct")
        r["rem_plus_3yr_tag"] = p.get("tag")
        if r["rem_plus_3yr"] is not None:
            n += 1
    meta.update({
        "available": True,
        "n_stamped": n,
        "generated_at": art.get("generated_at"),
        "season": pv.get("season"),
        "window": pv.get("window"),
        "n_in_artifact": len(players),
        "note": ("3-year REM+ is FROZEN lab output read verbatim from "
                 f"{MULTIYR_PATH.name}, not recomputed by this run. It is as of "
                 "generated_at, NOT as of this board's as_of date, and arms who "
                 "joined the pool after that date have no value."),
    })
    return meta


_XREM_MIN_PA = 80.0   # min Savant batters-faced for a stable xwOBA-allowed read


def _join_xrem_plus(relievers: list[dict], season: int) -> int:
    """Stamp xREM+ (deserved run prevention on Savant expected wOBA-allowed) + Luck
    onto tracked relievers.

    HONEST FRAMING (loss ledger): Statcast xwOBA-allowed was tested against FIP for
    REM+ and did NOT win, so REM+ stays FIP-based. xREM+ is a COMPANION deserved-
    suppression read plus a luck residual, NOT a more predictive replacement. It
    INVERTS the hitter xHEM+ ratio (lower allowed xwOBA = higher +, mirroring
    rem_plus = 100 * poolFIP / playerFIP) and anchors the pool over the RELIEVER
    board (so 100 = the average reliever, matching REM+'s reliever anchor). Luck =
    actual wOBA-allowed minus expected (positive = allowed more than deserved =
    unlucky, room to improve). MLB-only + min-BBE gated; missing -> fields absent
    (column blank). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "pitcher")
    except Exception:   # noqa: BLE001 - best-effort, network/parse anything
        return 0
    board = {int(r["mlbam"]) for r in relievers if r.get("mlbam") is not None}
    xw: dict[int, tuple[float, float]] = {}
    luck_by: dict[int, float] = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if mid not in board or pa < _XREM_MIN_PA or ew <= 0:
            continue
        xw[mid] = (ew, pa)
        try:
            luck_by[mid] = round(float(r["woba"]) - ew, 3)
        except (TypeError, ValueError, KeyError):
            pass
    if not xw:
        return 0
    dtot = sum(pa for _, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    if not pool:
        return 0
    n = 0
    for r in relievers:
        ent = xw.get(int(r["mlbam"])) if r.get("mlbam") is not None else None
        if not ent:
            continue
        r["xrem_plus"] = int(round(100.0 * pool / ent[0]))   # INVERTED: lower allowed = higher
        r["xwoba_against"] = round(ent[0], 3)
        mid = int(r["mlbam"])
        if mid in luck_by:
            r["luck"] = luck_by[mid]
        n += 1
    return n


# --------------------------------------------------------------------------- #
# WAR/PA+ and WAR/IP+ (new Arkmetrics, 2026-07-29)
#
# Convention 3 of docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md: 100 + 10z,
# ten points per anchor-pool standard deviation. A ratio-to-mean index (the HEM+
# / REM+ / SEM+ convention) is UNDEFINED on this rate: league mean WAR/PA is
# about +0.0025 and WAR goes negative, so 100 * player / pool would flip sign and
# blow up. There is therefore no HEM_SPREAD_GAIN analog here and none should be
# added: the index is a SINGLE LEG z-scored against its own anchor pool, so its
# pool spread is already exactly 10 points per sigma and there is nothing left to
# re-standardize. (Contrast fwdHEM+ in hitter_export, a 0.7/0.3 blend of two z
# legs, whose pool sd is BELOW 1 and which does need the extra step.)
#
# This module owns the shared machinery because it is the base of the /mlbstats/
# exporter chain: starter_export and hitter_export already import from here.
# The three anchored surfaces are wired in three places, deliberately:
#   hitter_export   war_pa_plus, anchored on the hitter pool
#   starter_export  war_ip_plus, anchored on the QUALIFIED-STARTER pool
#   bullpen_export  war_ip_plus, anchored on the RELIEVER pool
# Starter-anchored and reliever-anchored values must never share one column
# (ARKMETRIC_SCALE_CONVENTIONS.md:77), exactly as SEM+ and REM+ coexist.
#
# Lab + pre-registration: tools/war_rate_plus_lab.py. Ledger:
# data/war_rate_plus_eval.json.
# --------------------------------------------------------------------------- #
WAR_RATE_PER_SIGMA = 10.0          # convention 3: ten points is one pool sigma
# Two-tier volume floors (house pattern). The pool floor decides who sets mu/sd;
# the display gate decides who gets a value. NO shrink is applied (pre-registered
# in the lab): a WAR rate has no component rates to shrink, shrinkage is not
# monotone across players so it cannot ride a rank-preserved defence, and a
# descriptive index must describe what was banked. The lab measures the shrunk
# arm and reports it; if it is ever shipped, mu/sd MUST come from the shrunk pool
# (gated defect C3, the aStuff+ 7.16-points-per-sigma class).
WAR_RATE_POOL_MIN_PA = 50.0
WAR_RATE_DISPLAY_MIN_PA = 100.0
WAR_RATE_POOL_MIN_IP = 20.0
WAR_RATE_DISPLAY_MIN_SP_IP = 40.0
WAR_RATE_DISPLAY_MIN_RP_IP = 30.0
# A silent bWAR fetch failure must never be served as a board of zeros, so the
# join refuses when it cannot see a WAR value for at least this share of the
# pool-eligible rows (the fa_projection.py:191-201 degenerate-fetch pattern).
WAR_RATE_MIN_COVERAGE = 0.50


@functools.lru_cache(maxsize=1)
def _side_war_by_season() -> dict:
    """{mlbam: {season: {"bat": bWAR, "pit": bWAR}}} with the two sides kept on
    SEPARATE keys, via war_source.side_war_by_season (provider 'bwar', which
    delegates to mlb_player_export._war_daily).

    The side split is the whole point. fa_projection._war_age_maps SUMS the two
    sides onto one number, which would divide a two-way player's PITCHING WAR by
    his plate appearances. Reading the sides apart means a two-way player
    legitimately carries a batting WAR/PA+ on the hitter board and a pitching
    WAR/IP+ on a pitcher board, two different indexes over two different
    denominators, so no two-way discount factor is needed or wanted here
    (proj_export.TWO_WAY_PIT_PTH_FACTOR exists for a display path that shares one
    denominator; this one does not).

    Cached for the process: the three exporters each ask for it once."""
    import war_source
    return war_source.side_war_by_season()


def score_war_rate(rows: list[dict], season: int, *, side: str, denom_key: str,
                   pool_min: float, display_min: float, out_key: str,
                   anchor: str) -> dict:
    """Stamp `out_key` (100 + 10z of side bWAR per denominator) onto `rows`.

    `rows` are already-scored board dicts; `denom_key` is the field holding the
    denominator ('pa' or 'ip'); `side` is 'bat' or 'pit'. Rows at or above
    `pool_min` with a bWAR value set mu/sd; rows at or above `display_min` get a
    value. A row with no bWAR row of its own gets NO field (not a zero), so the
    column renders blank rather than reading as a real replacement-level season.

    Returns a meta block for the payload: the anchor description, the two floors,
    and the pool rate mean and sd that DEFINE the scale, so a reader of the served
    file can check the "ten points is one pool sigma" claim arithmetically instead
    of taking it on trust. Best-effort: any failure logs and returns an
    unavailable meta without touching a row."""
    meta = {"available": False, "n_stamped": 0, "anchor": anchor,
            "per_sigma": WAR_RATE_PER_SIGMA, "pool_min": pool_min,
            "display_min": display_min}
    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("%s unavailable (bWAR fetch failed: %s)", out_key, e)
        meta["refused"] = f"bWAR fetch failed: {e}"
        return meta

    def _war(r):
        mid = r.get("mlbam")
        if mid is None:
            return None
        return ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)

    elig = [r for r in rows if (_num(r.get(denom_key)) or 0.0) >= pool_min]
    pool = [(r, _war(r)) for r in elig]
    covered = [(r, w) for r, w in pool if w is not None]
    if not elig or len(covered) < WAR_RATE_MIN_COVERAGE * len(elig):
        # Degenerate fetch: pybaseball came back empty or stale, so almost nobody
        # has a WAR row. Refuse rather than anchor a board on a handful of rows.
        _log.warning("%s REFUSED: bWAR covers %d of %d pool-eligible rows for %s",
                     out_key, len(covered), len(elig), season)
        meta["refused"] = (f"bWAR covered {len(covered)} of {len(elig)} "
                           f"pool-eligible rows (floor {WAR_RATE_MIN_COVERAGE:.0%})")
        meta["pool_n"] = len(covered)
        return meta

    rates = [w / (_num(r.get(denom_key)) or 1.0) for r, w in covered]
    n = len(rates)
    mu = sum(rates) / n
    sd = (sum((x - mu) ** 2 for x in rates) / (n - 1)) ** 0.5 if n > 1 else 0.0
    if not sd:
        meta["refused"] = "degenerate pool spread"
        return meta

    # Sample-size companion (arm S), OWNER CALL CLOSED 2026-07-30:
    # docs/efv-2026-07-30/WAR_RATE_SHRINK_OWNER_CALL.md. The pre-registered rule
    # fired on hit and RP and the ship stayed unshrunk with the call left open;
    # the owner closed it as "ship it, but as a SEPARATE column". So the raw
    # index above is untouched - it still reproduces war/denom against
    # pool_mean_rate on the row, which is the property the override protected -
    # and the regressed variant lands beside it under its own name. Renaming is
    # not cosmetic: an adjusted value no longer reproduces the row's own rate, so
    # serving it under the raw column's name would silently change what a
    # published number means (ARKMETRIC_SCALE_CONVENTIONS.md).
    #
    # K is the pool MEDIAN denominator and mu/sd come from the SHRUNK pool, never
    # the unshrunk one. That second clause is the whole defect-C3 guard: aStuff+
    # shipped 7.16 points per sigma while advertising 10 precisely by z-scoring a
    # shrunk numerator against unshrunk moments (GATED_CANDIDATES.md C3).
    dens = sorted((_num(r.get(denom_key)) or 0.0) for r, _w in covered)
    K = dens[len(dens) // 2] if dens else 0.0
    tot_d = sum(dens)
    pool_rate = (sum(w for _r, w in covered) / tot_d) if tot_d else mu
    adj_rates = [((w + pool_rate * K) / ((_num(r.get(denom_key)) or 1.0) + K))
                 for r, w in covered]
    mu_s = sum(adj_rates) / n
    sd_s = (sum((x - mu_s) ** 2 for x in adj_rates) / (n - 1)) ** 0.5 if n > 1 else 0.0

    stamped = 0
    for r in rows:
        d = _num(r.get(denom_key)) or 0.0
        w = _war(r)
        if w is None or d < display_min or d <= 0:
            continue
        raw = 100.0 + WAR_RATE_PER_SIGMA * ((w / d) - mu) / sd
        r[out_key] = int(round(raw))          # "+" stats round to nearest
        # pre-display core at the rem_plus_raw / hem_plus_raw precision. The lab
        # never reads this field (it recomputes from bWAR), so the harness-v2
        # unrounded-predictor rule is satisfied upstream, not here.
        r[f"{out_key}_raw"] = round(raw, 1)
        if sd_s:
            adj = 100.0 + WAR_RATE_PER_SIGMA * (
                ((w + pool_rate * K) / (d + K)) - mu_s) / sd_s
            r[f"{out_key}_adj"] = int(round(adj))
            r[f"{out_key}_adj_raw"] = round(adj, 1)
        r["war"] = round(w, 1)
        stamped += 1

    # 1yr percentile chip. The 3yr columns already carry one (`*_3yr_pct`) and the
    # 1yr did not, which is why a top-of-board rate read as an unremarkable number:
    # on a 100+10z scale a reader has to do z-arithmetic to learn that 113 is rare.
    # Midrank over the SERVED rows, matching war_rate_plus_lab._pct_map exactly so
    # the two chips mean the same thing on the same row.
    served = sorted(r[out_key] for r in rows if r.get(out_key) is not None)
    if served:
        m = len(served)
        for r in rows:
            v = r.get(out_key)
            if v is None:
                continue
            lo = bisect.bisect_left(served, v)
            hi = bisect.bisect_right(served, v)
            r[f"{out_key}_pct"] = int(round(100.0 * ((lo + hi) / 2.0) / m))
    meta.update({
        "available": True, "n_stamped": stamped, "pool_n": n,
        "pool_mean_rate": round(mu, 6), "pool_sd_rate": round(sd, 6),
        "shrink_K": round(K, 1), "pool_rate": round(pool_rate, 6),
        "adj_mean_rate": round(mu_s, 6), "adj_sd_rate": round(sd_s, 6),
        "note": (f"100 + 10z of bWAR per {denom_key.upper()} over {anchor}. Ten "
                 f"points is one standard deviation of that pool, not one "
                 f"percent: this is not the HEM+/REM+/SEM+ ratio scale. No "
                 f"shrink and no clamp. Rows under {display_min:g} "
                 f"{denom_key.upper()} carry no value."),
        "adj_note": (f"{out_key}_adj regresses the rate toward the pool rate by "
                     f"sample size (K = pool median {denom_key.upper()} = {K:g}) "
                     f"and re-standardises on the SHRUNK pool. It is a "
                     f"readability aid for thin samples, not a forward claim: the "
                     f"ship gate G2 failed on every pool, and the post-hoc volume "
                     f"control shows the shrink gain is mostly a volume leak. It "
                     f"does NOT reproduce war/{denom_key} on the row."),
    })
    return meta


def _join_war_ip_plus(relievers: list[dict], season: int) -> dict:
    """RELIEVER-anchored WAR/IP+: 100 = the average reliever's pitching bWAR per
    inning. The starter board ships its own starter-anchored WAR/IP+; the two are
    separate metrics that happen to share a field name across two different
    payload files, never one pooled column."""
    return score_war_rate(
        relievers, season, side="pit", denom_key="ip",
        pool_min=WAR_RATE_POOL_MIN_IP, display_min=WAR_RATE_DISPLAY_MIN_RP_IP,
        out_key="war_ip_plus", anchor="relievers with 20+ IP")


def _join_war_ip_plus_3yr(relievers: list[dict]) -> dict:
    """Stamp war_ip_plus_3yr / percentile / tag from the frozen multi-year
    artifact (tools/war_rate_plus_lab.py), reliever block.

    VINTAGE, NOT PIPELINE OUTPUT (same contract as _join_rem_plus_3yr): read
    VERBATIM from a frozen lab artifact, never recomputed here, so a row can show
    a same-day 1-year value beside a 3-year value frozen weeks earlier and an arm
    who entered the pool after the lab ran is blank. Returns the vintage block so
    the payload carries it and the frontend can disclose it."""
    return join_war_rate_3yr(relievers, "rp", "war_ip_plus_3yr", "arms")


def join_war_rate_3yr(rows: list[dict], block: str, key: str, who: str) -> dict:
    """Shared frozen-vintage join for the three trailing-window WAR-rate columns
    (hitter / starter / reliever blocks of data/war_rate_plus_multiyear_eval.json).
    Missing artifact, missing block, or unmatched player -> fields absent and the
    column renders blank."""
    meta = {"source": WAR_RATE_MULTIYR_PATH.name, "n_stamped": 0, "available": False,
            "block": block}
    try:
        art = json.loads(WAR_RATE_MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"][block]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
    n = 0
    for r in rows:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r[key] = p.get(key)
        r[f"{key}_pct"] = p.get("pct")
        r[f"{key}_tag"] = p.get("tag")
        if r[key] is not None:
            n += 1
    meta.update({
        "available": True, "n_stamped": n,
        "generated_at": art.get("generated_at"),
        "season": pv.get("season"), "window": pv.get("window"),
        "anchor_pool": pv.get("anchor_pool"),
        "n_in_artifact": len(players),
        "note": (f"The 3-year column is FROZEN lab output read verbatim from "
                 f"{WAR_RATE_MULTIYR_PATH.name}, not recomputed by this run. It is "
                 f"as of generated_at, NOT as of this board's as_of date, and "
                 f"{who} who joined the pool after that date have no value."),
    })
    return meta


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export(season: Optional[int] = None, *, leverage_limit: Optional[int] = None,
           out_path: Optional[Path] = None, write: bool = True, log=print,
           today: Optional[str] = None) -> int:
    """Build data/bullpen_leaderboards.json and return the reliever count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  bullpen: loading {season} StatsAPI season pitching...")
    rows = load_season_pitching(season)
    if not rows:
        log(f"  bullpen: no pitching data for {season} (source blocked or empty); skipping")
        return 0
    swstr = load_bref_swstr(season)  # best-effort SwStr% enrichment

    log(f"  bullpen: computing leverage from StatsAPI winProbability"
        + (f" (first {leverage_limit} games)" if leverage_limit else " (full season)") + "...")
    try:
        import mlb_leverage
        leverage, coverage = mlb_leverage.fetch_season_leverage(
            season, limit=leverage_limit,
            progress=lambda i, n: (log(f"    leverage {i}/{n} games") if i % 200 == 0 else None))
    except Exception as e:
        _log.warning("leverage walk failed: %s", e)
        leverage, coverage = {}, {"games": 0, "games_total": 0}

    relievers = build_relievers(rows, leverage, swstr)
    scored = rem_plus.score_pool(relievers)
    n_lev = _join_leverage_consistency(scored["relievers"])
    if n_lev:
        log(f"  bullpen: gmLI-consistency joined for {n_lev} relievers")
    r3_meta = _join_rem_plus_3yr(scored["relievers"])
    if r3_meta.get("n_stamped"):
        log(f"  bullpen: 3-year REM+ joined for {r3_meta['n_stamped']} relievers "
            f"(frozen lab vintage {r3_meta.get('generated_at')})")
    n_xr = _join_xrem_plus(scored["relievers"], season)
    if n_xr:
        log(f"  bullpen: xREM+ (Savant deserved run prevention) joined for {n_xr} relievers")
    wr_meta = _join_war_ip_plus(scored["relievers"], season)
    if wr_meta.get("available"):
        log(f"  bullpen: WAR/IP+ (reliever-anchored) joined for "
            f"{wr_meta['n_stamped']} relievers (pool {wr_meta['pool_n']})")
    elif wr_meta.get("refused"):
        log(f"  bullpen: WAR/IP+ refused ({wr_meta['refused']})")
    wr3_meta = _join_war_ip_plus_3yr(scored["relievers"])
    if wr3_meta.get("n_stamped"):
        log(f"  bullpen: 3-year WAR/IP+ joined for {wr3_meta['n_stamped']} relievers "
            f"(frozen lab vintage {wr3_meta.get('generated_at')})")

    # Bullpen Charts should show only players actually ON the active roster; drop
    # off-roster arms (demoted / released) from the depth ladders. Roster fetch is
    # a single guarded pass and falls back to NO filtering if it fails.
    active_ids = _active_mlbam_ids(season)
    if active_ids is None:
        log("  bullpen: active-roster feed unavailable; depth ladders left unfiltered")
    else:
        n_off = _apply_roster_filter(scored["teams"], active_ids)
        log(f"  bullpen: active-roster filter kept {len(active_ids)} rostered ids, "
            f"dropped {n_off} off-roster arms from depth ladders")

    payload = {
        "generated_at": today,
        "season": season,
        "as_of": today,
        "coverage": {
            "games": coverage.get("games", 0),
            "expected": coverage.get("games_total", 0),
            "note": ("gmLI / WPA / SD-MD reflect the games walked so far; REM+ skill is "
                     "full-season. Coverage fills toward complete as the feed cache accrues."),
        },
        "verdict": _verdict(),
        "backtest": _backtest(),
        # Vintage of the FROZEN 3-year REM+ column (see _join_rem_plus_3yr):
        # it is not regenerated by this run, so the frontend can disclose how
        # old the 3yr number beside a live 1yr number actually is.
        "multiyear": r3_meta,
        # WAR/IP+ scale block (anchor pool + measured pool parameters) and the
        # vintage of its FROZEN 3-year companion, same disclosure contract.
        "war_rate": wr_meta,
        "multiyear_war_rate": wr3_meta,
        "pool": scored["pool"],
        "relievers": scored["relievers"],
        "teams": scored["teams"],
    }

    n = len(scored["relievers"])
    log(f"  bullpen: {n} relievers ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(scored['teams'])} team pens; leverage {coverage.get('games', 0)}/"
        f"{coverage.get('games_total', 0)} games")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        try:
            shown = out_path.relative_to(Path(__file__).parent)
        except ValueError:
            shown = out_path.name
        log(f"  bullpen: wrote {shown}")
    return n


_HISTORY_FIELDS = ("mlbam", "name", "team", "rem_plus", "riv_plus", "role",
                   "ip", "g", "tbf", "era", "fip", "k_pct", "bb_pct", "k_bb_pct",
                   "swstr_pct", "hr9", "gmli", "wpa", "sd", "md", "saves", "holds",
                   "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/bullpen_history.json - per-season reliever boards (qualified
    arms) for the /mlbstats/ yearly history tabs, so users can read past seasons
    and eyeball how REM+ (skill) and RIV+ (realized impact) played forward. One
    compact row per qualified reliever per season; the current live season stays
    in bullpen_leaderboards.json. Cached winProbability keeps the walk fast."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    for y in seasons:
        log(f"  bullpen-history: {y}...")
        rows = load_season_pitching(y)
        if not rows:
            log(f"  bullpen-history: no data for {y}; skipping")
            continue
        swstr = load_bref_swstr(y)
        try:
            import mlb_leverage
            leverage, cov = mlb_leverage.fetch_season_leverage(y)
        except Exception as e:  # noqa: BLE001
            _log.warning("history leverage walk %s failed: %s", y, e)
            leverage, cov = {}, {"games": 0, "games_total": 0}
        scored = rem_plus.score_pool(build_relievers(rows, leverage, swstr))
        board = [{k: r.get(k) for k in _HISTORY_FIELDS}
                 for r in scored["relievers"] if r.get("qualified")]
        board.sort(key=lambda r: (r.get("rem_plus") or -999), reverse=True)
        hist[str(y)] = {
            "season": y,
            "leverage_games": cov.get("games", 0),
            "leverage_expected": cov.get("games_total", 0),
            "n_qualified": len(board),
            "relievers": board,
        }
        log(f"  bullpen-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Per-season qualified-reliever boards for the yearly history tabs. "
                 "REM+ is the pure-skill run-prevention index; RIV+ is the realized "
                 "leverage-weighted impact index (deployment value, not repeatable skill)."),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  bullpen-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        _limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        export(_season, leverage_limit=_limit)
