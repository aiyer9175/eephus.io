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
from rate_stabilization import REPLACEMENT_WINS
from scrapers import normalize_key

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FIRST_SEASON = 2027          # first fully projected season (2026 is in progress)
HORIZON = 5                  # 2027..2031
# Exposure floor for the veteran universe: at least one of the last three
# seasons with a real sample (sub-cup-of-coffee players add noise, not
# signal, and the engine's reliability buckets were fitted above this).
MIN_PA, MIN_IP = 100, 30

# Two-way "if-healthy" calibration: a two-way player cannot hold a FULL
# dedicated-starter inning load on top of a full hitting season, so naively
# summing each side's playing-time-held (PTH) path double-books durability and
# overstates the healthy ceiling (Ohtani read 10.7/11.56 WAR - above any season
# he has ever posted). The pitching side's PTH is workload-discounted by this
# factor (~a two-way ~130-IP load vs a ~180-IP dedicated starter) before
# summing; hitting PTH (DH, ~full PA) is untouched, and the pricing `war` path
# is unaffected (surplus/value/FA pricing unchanged). Tuned so the if-healthy
# ceiling lands near Ohtani's realistic peak (~9.5, under any 10+ season).
TWO_WAY_PIT_PTH_FACTOR = 0.48

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


# P-POSVAL: the Spotrac contract join copied ct["position"] onto the public row
# unvalidated, so malformed scrape rows shipped fielding-code strings as a
# position ("35" for Christopher Morel, "37" for Santiago Espinal on the
# 2026-07-24 payload - both with aav 0, i.e. the whole contract row was junk).
# Whitelist the vocabulary the surface actually renders; anything else leaves
# the engine's own role token in place instead of overwriting it with noise.
_VALID_POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH", "IF",
              "INF", "SP", "RP", "P", "LHP", "RHP", "SIRP", "MIRP", "CL",
              "TWP", "UT", "UTIL"}


def _valid_pos(pos) -> bool:
    return isinstance(pos, str) and pos.strip().upper() in _VALID_POS


# ============================================================================
# P-VETTEAM: team + contract identity resolution
# ============================================================================
# The Spotrac join is by NORMALIZED NAME and the roll-up drops any vet without a
# team (`if not tm: continue`). Two independent leaks, measured 2026-07-31 on the
# served payload: 361 of 1,319 vets carried no team and took 40.7 champion Y1 WAR
# out of Team Outlook. Causes:
#   1. Spotrac's team pages only list PRICED contracts (1,161 rows), so pre-arb
#      and optioned players are absent by construction - 356 of the 361.
#   2. Generational suffixes disagree between sources. Spotrac writes "Jazz
#      Chisholm", war_daily writes "Jazz Chisholm Jr." -> keys never met.
# The suffix mismatch also mis-AWARDED contracts: the WSN "Luis Garcia" deal
# joined mlbam 472610 (the reliever, on MIN) instead of 671277 (Luis Garcia Jr.,
# WSN), because the reliever's key matched exactly. Resolution below is
# mlbam-keyed and uses the observed club as the tiebreak.
_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv"}


def _base_key(key: str) -> str:
    """Normalized key with trailing generational suffixes removed. Guarded at
    two remaining tokens so a genuinely two-token name ("Sammy Sr") survives."""
    parts = key.split("_")
    while len(parts) > 2 and parts[-1] in _SUFFIX_TOKENS:
        parts = parts[:-1]
    return "_".join(parts)


_TEAM_BY_MLBAM: dict[int, str] | None = None


def _team_by_mlbam(lookback: int = 4) -> dict[int, str]:
    """{mlbam: org code} - the club each player was last seen playing for.

    Reads the StatsAPI season-stat splits the corpus build already caches (no
    new ingest); later seasons overwrite earlier ones, so the map reads as
    "most recent club seen". Best-effort: an unavailable cache leaves this
    empty and every join falls back to exactly the pre-fix behaviour."""
    global _TEAM_BY_MLBAM
    if _TEAM_BY_MLBAM is not None:
        return _TEAM_BY_MLBAM
    out: dict[int, str] = {}
    try:
        import fa_sources
        from trades import canonical_org
    except ImportError:                                        # noqa: BLE001
        _TEAM_BY_MLBAM = out
        return out
    for season in range(FIRST_SEASON - lookback, FIRST_SEASON):
        for group in ("hitting", "pitching"):
            try:
                splits = fa_sources.fetch_statsapi_season_stats(season, group)
            except Exception:                                  # noqa: BLE001
                log.warning("team map: statsapi %s %d unavailable", group, season)
                continue
            for sp in splits or []:
                pid = (sp.get("player") or {}).get("id")
                name = (sp.get("team") or {}).get("name")
                if not pid or not name:
                    continue
                org = canonical_org(name)
                if org:
                    out[int(pid)] = org
    _TEAM_BY_MLBAM = out
    log.info("team map: %d mlbam -> org from statsapi season splits", len(out))
    return out


def _resolve_contracts(mlbams, names: dict[int, str], contracts: dict[str, dict],
                       teams: dict[int, str]) -> tuple[dict[int, dict], dict[str, list[int]]]:
    """Assign at most one Spotrac contract per mlbam.

    Returns ({mlbam: contract}, {contract_key: [contested mlbam, ...]}). A
    contract is claimed by the exact normalized key first and by the
    suffix-stripped key second. When several players claim the same contract,
    the one whose OBSERVED club matches the contract's team wins outright;
    if that does not single anyone out the contract is left contested and the
    caller breaks the tie on projected WAR (the pre-fix behaviour)."""
    claims: dict[str, list[int]] = {}
    for mid in mlbams:
        nm = names.get(mid)
        if not nm:
            continue
        ekey = normalize_key(nm)
        for ck in (ekey, _base_key(ekey)):
            if ck in contracts:
                claims.setdefault(ck, []).append(mid)
                break
    assigned: dict[int, dict] = {}
    contested: dict[str, list[int]] = {}
    for ck, cands in claims.items():
        ct = contracts[ck]
        if len(cands) == 1:
            assigned[cands[0]] = ct
            continue
        tm = ct.get("team_code")
        agree = [m for m in cands if tm and teams.get(m) == tm]
        if len(agree) == 1:
            assigned[agree[0]] = ct
        else:
            contested[ck] = cands
    return assigned, contested


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
    # REST-OF-SEASON CONTROL (2026-08-03). Fraction of the in-progress season
    # still to be played. season_fraction() returns the ELAPSED share and falls
    # back to 1.0 when the league PA substrate is missing, so a broken estimate
    # lands here as 0.0 remaining: the rest-of-season leg silently prices at
    # nothing rather than inventing a full season of value. Clamp is defensive.
    ros_frac = max(0.0, min(1.0, 1.0 - frac))

    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row

    # Spotrac contracts are keyed by NORMALIZED NAME only (no mlbam), so two active
    # players sharing a name (Will Smith C/RP, Max Muncy LAD/ATH) would both join the
    # SAME contract -- corrupting team/pos/salary/surNpv and the team outlook. The
    # resolver above assigns each contract to ONE mlbam (exact key, then
    # suffix-stripped, then observed-club tiebreak); anything it still cannot single
    # out is awarded after the loop to the highest-projected-WAR row (Spotrac's
    # collapse keeps the highest-AAV deal, which belongs to the flagship player).
    # Everyone else honestly carries no contract rather than a wrong one.
    _vet_ids = set(by_player["hit"]) | set(by_player["pit"])
    _name_counts: dict[str, int] = {}
    for _mid in _vet_ids:
        _nm = names.get(_mid)
        if _nm:
            _k = normalize_key(_nm)
            _name_counts[_k] = _name_counts.get(_k, 0) + 1
    _teams = _team_by_mlbam()
    _ct_by_mlbam, _contested = _resolve_contracts(_vet_ids, names, contracts, _teams)
    _contested_by_mlbam = {m: ck for ck, ms in _contested.items() for m in ms}

    def _apply_contract(m: dict, ct: dict) -> None:
        """Stamp the contract-dependent fields (pos/team/thru/aav/sur/surNpv) onto a
        built row. Shared by the inline (unambiguous) join and the post-loop
        collision-winner award so both paths price identically."""
        if not m.get("twoWay") and _valid_pos(ct.get("position")):
            m["pos"] = ct["position"].strip().upper()
        if ct.get("team_code"):
            m["team"] = ct["team_code"]
        sal = {int(y): int(v) for y, v in (ct.get("salary_by_year") or {}).items()}
        if ct.get("signed_through") is not None:
            m["thru"] = ct["signed_through"]
        if ct.get("aav_usd") is not None:
            m["aav"] = ct["aav_usd"]
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
        # REST-OF-SEASON CONTROL (2026-08-03, owner ask). Until now a contract
        # whose last season is the one in progress produced no `sur` and no
        # `surNpv` at all: the horizon starts at FIRST_SEASON, so the months a
        # club still controls the player were worth exactly zero everywhere on
        # the platform. That made every deadline rental "not tradeable" (the
        # question that opened docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md,
        # whose answer for A.J. Minter is superseded here: a rental IS a trade
        # asset, it is simply a small one).
        #
        # Deliberate conventions, so the two legs stay comparable:
        #   * UNDISCOUNTED and un-escalated (t=0). This is money and wins now,
        #     and surNpv's own discount origin is t=0 at FIRST_SEASON, so a
        #     naive t=-1 would have inflated the remainder by (1+r).
        #   * Talent basis is war[0], the nearest full-season projection,
        #     prorated by the share of the season left. Slightly conservative
        #     for an aging vet (his in-season talent is a shade above next
        #     year's) and it deliberately does not read 2026 results to date,
        #     which measure what the SELLING club already banked.
        #   * The prorated WAR is priced through the same convex tier curve at
        #     its own level, exactly as every full season is.
        #
        #     THIS COMMENT USED TO SAY THAT UNDER-PRICES A STAR RENTAL. It was
        #     asserted, never measured, and MEASURING IT REFUTED IT (2026-08-04,
        #     lane R5.2). The shortfall against pricing at the full-season rate,
        #     f*V(w_full), is SINGLE-PEAKED and largest for MID-tier rentals: it
        #     peaks around a 2.5 to 3.0 WAR full-season rate at roughly +0.79,
        #     then FALLS MONOTONICALLY across the star class (Spearman -1.0000
        #     over n=69) and is EXACTLY ZERO at and above 8.31 WAR. The reason
        #     is mechanical: the platform's own curve is LINEAR above about 2.5
        #     WAR, and proration is exact on a linear segment, so there is no
        #     convexity left to under-price at the top. The intuition had the
        #     population backwards - if anything is mispriced here it is the
        #     mid-tier deadline add, not the star.
        #
        #     A concentration premium may still exist in what clubs PAY; that
        #     is a different claim and it is UNMEASURED. The backtest is
        #     BLOCKED, not merely unfinished: historical per-player salary and
        #     in-season WAR splits do not exist in this tree, and the only
        #     multi-year return valuation (xfv_history) is 0% covered before
        #     2021 and survivor-selected after, leaving 8 usable deadline
        #     trades against a pre-registered floor of 40. Unblocks, in order of
        #     cheapness: trade_value_history has snapshotted every board member
        #     contemporaneously since 2026-06-25 and accrues an unbiased
        #     price-paid series on its own; failing that, per-player historical
        #     salary by season, then in-season WAR splits or dated game logs.
        #     Do NOT ship a premium constant before one of those lands.
        #   * Salary is prorated too: the acquiring club pays only the balance.
        # Applies to EVERY vet with a current-season salary, not just expiring
        # ones. Pricing Minter's remainder while ignoring Judge's would invent
        # a new inconsistency of exactly the class this codebase keeps paying
        # to remove.
        ros_d = None
        cur_sal = sal.get(FIRST_SEASON - 1)
        war_now = (m.get("war") or [None])[0]
        if cur_sal is not None and war_now is not None and ros_frac > 0.0:
            ros_war = float(war_now) * ros_frac
            ros_d = _season_value_usd(ros_war, 0, dpw) - float(cur_sal) * ros_frac
            m["surRos"] = round(ros_d / 1e6, 1)
            m["rosWar"] = round(ros_war, 2)
            m["rosFrac"] = round(ros_frac, 3)
        # What the player is worth to ACQUIRE right now: the balance of the
        # current season plus the NPV of every controlled season after it.
        # `surNpv` keeps its old meaning (FIRST_SEASON onward) so /projections/
        # and any external reader of that field are unchanged.
        if ros_d is not None or any_sal:
            m["surTotal"] = int((ros_d or 0.0) + npv)

    out: list[dict] = []
    _collision_rows: dict[str, list[dict]] = {}
    for mlbam in _vet_ids:
        sides = {}
        for side in ("hit", "pit"):
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
            # Anchor the age offset to the row that supplied the age.
            age_row = next((h for h in hist_s if h.get("age")), None)
            if age_row is None:
                continue
            age_s = age_row["age"] + (FIRST_SEASON - age_row["season"])
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
            # Champion MEAN path (both sides summed) for the team roll-up - the
            # displayed war_arr may be the median-like ML quantile head, which
            # must never be summed across a roster.
            champ_arr = _sum_arr("war_by_year_champ") or war_arr
            # If-healthy display path: workload-discount the pitching side's PTH
            # (a two-way arm can't carry a full starter's innings on top of a
            # full hitting season) before summing. See TWO_WAY_PIT_PTH_FACTOR.
            _hit_pth = paths["hit"].get("war_by_year_pth")
            _pit_pth = paths["pit"].get("war_by_year_pth")
            if _hit_pth and _pit_pth:
                pth_arr = [round((_hit_pth[t] or 0)
                                 + TWO_WAY_PIT_PTH_FACTOR * (_pit_pth[t] or 0), 2)
                           for t in range(min(HORIZON, len(_hit_pth), len(_pit_pth)))]
            else:
                pth_arr = _sum_arr("war_by_year_pth")   # if-healthy display path
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
            champ_arr = (path.get("war_by_year_champ") or path["war_by_year"])[:HORIZON]
            pth_arr = (path.get("war_by_year_pth") or war_arr)[:HORIZON]   # if-healthy display path
            # `or None` after the slice never fired ([None] is truthy), so a vet path
            # with no band shipped warP10/warP90 = [None] (a 1-elem null list) instead
            # of None -- gate on the source list being present first.
            p10_arr = (path.get("war_by_year_p10") or None) and path["war_by_year_p10"][:HORIZON]
            p90_arr = (path.get("war_by_year_p90") or None) and path["war_by_year_p90"][:HORIZON]
        name = names.get(mlbam)
        if not name:
            continue
        _nkey = normalize_key(name)
        _ambiguous = _name_counts.get(_nkey, 0) > 1
        ct = _ct_by_mlbam.get(mlbam)
        m = {
            # Collided names get a collision-safe key (base__mlbam, the thin-card
            # convention); the post-loop award below restores the PLAIN key on the
            # flagship row so existing links / FA / trade joins keep working for him.
            "key": (f"{_nkey}__{mlbam}" if _ambiguous else _nkey), "name": name, "age": age,
            "mlbam": mlbam,
            "src": "vet", "twoWay": True if two_way else None,
            "pos": "TWP" if two_way else ((ct or {}).get("position") or path["role"]),
            # Contract club first (it is the paying club); the observed club is the
            # fallback that keeps un-contracted vets on a roster instead of dropped.
            "team": (ct or {}).get("team_code") or _teams.get(mlbam),
            "war": war_arr,
            # Champion MEAN path (5y) - the SUM basis for the Team Outlook
            # multi-year roll-up (warChamp[0] == warY1Champ below).
            "warChamp": [round(w, 2) for w in champ_arr],
            # If-healthy (playing-time-held) display path - shown on the board's
            # WAR cells; surplus/value below still price off `war` (expected value).
            "warPTH": (pth_arr or war_arr),
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
        # Projected RATE lines (fa_projection.rate_path - the year-1 Marcel
        # components walked along the per-component aging curves). Hitters:
        # wOBA + wRC+; pitchers: FIP; two-way rows carry both. Display
        # surfaces only - WAR/pricing are untouched by these.
        _rh = (paths.get("hit") or {}).get("rates_by_year") or []
        _rp = (paths.get("pit") or {}).get("rates_by_year") or []
        if _rh:
            m["woba"] = [r.get("woba") for r in _rh[:HORIZON]]
            m["wrc"] = [r.get("wrc_plus") for r in _rh[:HORIZON]]
        if _rp:
            m["fip"] = [r.get("fip") for r in _rp[:HORIZON]]
        if two_way:
            m["warHit"] = [round(w, 2) for w in paths["hit"]["war_by_year"][:HORIZON]]
            m["warPit"] = [round(w, 2) for w in paths["pit"]["war_by_year"][:HORIZON]]
        m["warTotal"] = round(sum(m["war"]), 1)
        m["warTotalPTH"] = round(sum(m.get("warPTH") or m["war"]), 1)  # if-healthy display total
        if p10_arr:
            m["warTotalP10"] = round(sum(p10_arr), 1)
            m["warTotalP90"] = round(sum(p90_arr), 1)
        if ct:
            _apply_contract(m, ct)
            # A resolved collision winner takes the plain key back (links/joins).
            if _ambiguous and contracts.get(_nkey) is ct:
                m["key"] = _nkey
        m = _clean(m)
        out.append(m)
        _ck = _contested_by_mlbam.get(mlbam)
        if _ck:
            _collision_rows.setdefault(_ck, []).append(m)
    # Contracts the resolver could not single out: award to the highest-projected-WAR
    # claimant only (Spotrac's collapse keeps the highest-AAV deal, i.e. the flagship).
    for _ck, rows in _collision_rows.items():
        ct = contracts.get(_ck)
        if not ct or not rows:
            continue
        winner = max(rows, key=lambda m: m.get("warTotal") or 0.0)
        _apply_contract(winner, ct)   # mutates the row already in `out`
        if winner["key"].split("__")[0] == _ck:
            winner["key"] = _ck       # flagship keeps the plain key (links/joins)
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


# BASIS REPAIR 2026-08-03. THE board eFV number, mirroring build_site's
# `_load_xfv_grades` precedence exactly (which in turn mirrors
# storage.BOARD_GRADE_FIELD and the prospx client's efvBoardValue): the
# calibrated board value first, then the realized grade, then the RETIRED
# quantile as a legacy fallback. This file kept a private quantile-FIRST copy of
# the precedence when the board unified onto raw xfv_grade on 2026-07-25, so
# /projections/ went on serving the retired quantile as the eFV headline while
# the board, the homepage and prospx served xfv_grade: one player, two different
# eFV numbers. The SCALE itself is owned by efv_board_scale.board_value(); there
# is deliberately no second copy of the coefficients here to drift.
try:
    from efv_board_scale import board_value as _efv_board_value
except Exception:                                            # pragma: no cover
    def _efv_board_value(rec):
        return (rec or {}).get("xfv_grade")


def _board_grade(rec: dict | None):
    """The DISPLAYED eFV grade for an xfv.json record, or None. Unrounded -
    callers that display it round to NEAREST (eFV is not a scouting FV)."""
    rec = rec or {}
    g = _efv_board_value(rec)
    if g is None:
        g = rec.get("xfv_grade_realized")
    if g is None:
        g = rec.get("xfv_grade_quantile")
    return float(g) if isinstance(g, (int, float)) else None


def _prospect_rows(dpw: float) -> list[dict]:
    try:
        players = json.loads((DATA_DIR / "timeseries.json")
                             .read_text(encoding="utf-8")).get("players") or []
    except (OSError, ValueError):
        log.warning("mlb projections: timeseries.json unavailable - no prospects")
        return []
    cal_shift = _prospect_calibration_shift()
    try:
        xfv_by = (json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
                  .get("by_player") or {})
    except (OSError, ValueError):
        xfv_by = {}
    out: list[dict] = []
    for p in players:
        cons_fv = p.get("fv_close")
        # DISPLAY grade: THE board eFV headline, on the SAME precedence as
        # build_site._load_xfv_grades and storage.BOARD_GRADE_FIELD (see
        # _board_grade above), so /projections/, the homepage Top Prospects module
        # and the PROSPX board all show the same eFV number for the same player.
        _rec = xfv_by.get(p.get("player_key")) or {}
        _xg = _board_grade(_rec)
        fv = _xg if _xg is not None else cons_fv
        fv_source = "xfv" if _xg is not None else "consensus"
        # PRICING grade: DELIBERATELY the retired per-side quantile, NOT the displayed
        # board grade. The FV>=45 gate + p_bucket / WAR-path / surplus / prime curves are
        # all calibrated on the CONSENSUS 20-80 scale, which is exactly the scale the
        # quantile map lands on; the pure-model grade sits lower and floors a pile at 20,
        # and pricing on it once inflated the projected prospect pool ~+60% vs consensus.
        # This is the same split efv_export documents in meta.grade_scale: the board
        # displays xfv_grade while surplus_mm stays priced through xfv_grade_quantile,
        # which is why the 2026-07-30 grade refit moved zero dollars. So display and
        # pricing are two different numbers here ON PURPOSE - do not "unify" them without
        # re-fitting the value curves. Mirrors fa_fit.py's blocker-FV rule.
        _pq = _rec.get("xfv_grade_quantile")
        price_fv = _pq if (fv_source == "xfv" and _pq is not None) else fv
        eta = (p.get("eta") or {}).get("year")
        if (price_fv is None or price_fv < 45 or not eta or p.get("status") != "active"
                or eta > FIRST_SEASON + HORIZON - 1):
            continue
        pos = p.get("position")
        is_pit = vf.is_pitcher_position(pos)
        reliever = vf.is_reliever_position(pos)
        role = vf._role_key(is_pit)
        probs = vf.p_bucket_given_fv(float(price_fv), is_pit)
        if not probs:
            continue
        age = p.get("age")
        # P-ETACLAMP: anchor the trajectory to the SHIPPED eta, not the raw one.
        # The row ships eta_yr = max(eta, FIRST_SEASON) and both the board
        # (assets/projections.js warAt) and the team roll-up offset the path by
        # that shipped value - but debut_age was computed from the RAW eta, so
        # every prospect whose eta had already passed (98 of 232 on the
        # 2026-07-24 payload, 42%) got a trajectory shaped for a debut at their
        # CURRENT age and then rendered one calendar year later. Aging, scaling
        # and the surplus eta_years term (which already used the clamped value)
        # now agree.
        eta_shipped = max(int(eta), FIRST_SEASON)
        debut_age = (float(age) + max(0, eta_shipped - (FIRST_SEASON - 1))) if age else None
        scale = vf._war_scale_for(float(price_fv), role)
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
        eta_yr = eta_shipped
        # P-PWINDOW: the prospect war[] arrays are ETA-ALIGNED (index 0 = the
        # debut season) while the veteran arrays are CALENDAR-aligned at
        # FIRST_SEASON, so `sum(path[:HORIZON])` is NOT "the same HORIZON window
        # as the veteran rows" its comment claimed - for a 2031-ETA prospect it
        # summed 2031-2035 and labelled it a 2027-2031 total. Measured on the
        # 2026-07-24 payload: 79 prospects with eta>2027 shipped 155.2 total WAR
        # against 101.7 actually inside the window (1.53x). The board already
        # windows correctly in JS (warShown); the PAYLOAD field did not, and
        # mlb_player_export / fa_export / bayes_trade_value read it directly.
        _in_win = max(0, HORIZON - (eta_yr - FIRST_SEASON))

        def _wtot(series):
            return round(sum(series[:_in_win]), 1)

        sv = vf.surplus_value_mm(float(price_fv), is_pit, pos, age=age,
                                 eta_years=max(0.0, eta_yr - (FIRST_SEASON - 1)))
        # PRIME/TALENT display path (warPTH) + headline peak: reconciled to the
        # industry-style prime anchor so the board shows "what he is if he
        # sticks" (a 62-FV SS ~ 3-4 WAR, star ceiling ~5) instead of the
        # realized-mean ramp. The expected `war` above is unchanged and still
        # prices surplus.
        prime = vf.prospect_prime_path(float(price_fv), is_pit, debut_age, reliever)
        out.append(_clean({
            "key": p.get("player_key"), "name": p.get("player_name"),
            "age": age, "src": "prospect", "fv": fv, "consensus_fv": cons_fv,
            "fv_source": fv_source, "eta": eta_yr,
            "pos": pos, "team": p.get("org"),
            "war": [round(w, 2) for w in mean_path],
            "warP10": [round(w, 2) for w in paths[lo_b]],
            "warP90": [round(w, 2) for w in paths[hi_b]],
            # Totals sum the SAME CALENDAR window as the veteran rows: the war
            # arrays are ETA-aligned, so the in-window count is HORIZON minus the
            # seasons before debut (see P-PWINDOW above). The arrays themselves
            # keep the full control window for the card path.
            "warTotal": _wtot(mean_path),
            "warTotalP10": _wtot(paths[lo_b]),
            "warTotalP90": _wtot(paths[hi_b]),
            # Prime/talent display path (not used for $): board WAR cells.
            "warPTH": [round(w, 2) for w in prime["mean"]] if prime else None,
            "warPTHP10": [round(w, 2) for w in prime["p10"]] if prime else None,
            "warPTHP90": [round(w, 2) for w in prime["p90"]] if prime else None,
            "warTotalPTH": _wtot(prime["mean"]) if prime else None,
            "warTotalPTHP10": _wtot(prime["p10"]) if prime else None,
            "warTotalPTHP90": _wtot(prime["p90"]) if prime else None,
            "warPeak": prime["peak"] if prime else None,
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
    the team-level improvement, nothing finer). Missing artifact = no-op.

    GATED on the artifact's own ship_decision (added 2026-07-31). Until now
    this read the intercepts unconditionally, so re-running proj_backtest.py
    served whatever it produced even when the challenger LOST its holdout.
    That is not hypothetical: re-fitting on the post-E3 paths yields
    cohort_recentered 7.29 against plain recentered 7.19, i.e. the intercepts
    become actively harmful, and the old code would have shipped them the
    moment anyone regenerated the artifact. challenger_wins is True on the
    committed 2026-06-12 fit, so this guard is a no-op TODAY and changes no
    served number; it exists so the next refit cannot ship itself."""
    try:
        d = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
        rb = (d.get("retro_backtest") or {})
        if not ((rb.get("ship_decision") or {}).get("challenger_wins")):
            return {}
        return rb.get("cohort_intercepts_fit_2022_24") or {}
    except (OSError, ValueError):
        return {}


def _age_band(age) -> str:
    a = int(age) if age else 28
    for lo, hi in ((0, 25), (26, 29), (30, 33), (34, 99)):
        if lo <= a <= hi:
            return f"{lo}-{hi}"
    return "34-99"


def _last_controlled_season(m: dict) -> int:
    """Last season this player counts on his team's CONTROLLED roster - the
    'control cliff' that makes the out-year team WAR decline as players reach
    free agency.

    - Prospect: controlled the full window from his ETA (6-year control >> the
      5-year horizon), so he never cliffs inside the horizon.
    - Veteran with a Spotrac contract: through ``signed_through`` (``thru``).
    - Veteran without a contract row: an AGE-based proxy (the pipeline carries
      no service time) - a pre-arb/arb player (age <= 24) holds the full horizon,
      a likely pending free agent (age >= 29) holds only the first season.
    """
    last = FIRST_SEASON + HORIZON - 1
    if m.get("src") == "prospect":
        return last
    thru = m.get("thru")
    if thru:
        try:
            t = int(thru)
            # A contract that still covers the first projected season governs
            # the cliff. A stale / already-expired `thru` (option years, past
            # deals on a still-rostered player) is ignored - the player is on
            # the current roster, so fall through to the age proxy, which never
            # drops the first season.
            if t >= FIRST_SEASON:
                return min(t, last)
        except (TypeError, ValueError):
            pass
    try:
        age = int(m.get("age"))
    except (TypeError, ValueError):
        age = 28
    rem = max(0, min(HORIZON - 1, 29 - age))
    return FIRST_SEASON + rem


def _row_sides(m: dict) -> list[str]:
    if m.get("twoWay"):
        return ["hit", "pit"]              # two-way = both stat lines
    return ["pit" if (m.get("pos") or "") in ("SP", "RP", "P") else "hit"]


def _depth_pool(corpus: dict, names: dict[int, str],
                contracts: dict[str, dict], vet_mlbams: set) -> tuple[dict, dict]:
    """Per-season WAR for every projectable player the exposure floors exclude
    from the display list - the retro backtest showed the floor-gated
    universe carries only ~560 of the league's ~1000 WAR while the full
    >=1-input-season population, on real rosters, sums to ~870-935. These
    players never appear in the UI table; their WAR joins the Team Outlook
    roll-up per team (contract team), shrinking the uniform depth allowance to
    a small remainder.

    RANGE RECONCILED 2026-08-04. This said "~870-930" while
    test_team_outlook_calibration floors the same quantity at 900, and that
    test's own docstring flagged the disagreement ("whichever is right, both
    should not stand") back when the served value was 886.3 and sat between
    them. It no longer does: after the F-DEF ship restored the vet paths and
    the stale cohort-intercept vector was dropped, the served sum is 932.9, so
    the top of the stated range was the stale half. Widened to 935; the test's
    900 floor stands unchanged and now has real headroom.

    Multi-year: champion MEANS (use_ml=False pins the champion path) are summed
    season-by-season - the same mean basis the rostered roll-up uses - and each
    depth player counts only through his control window
    (_last_controlled_season; depth players are nearly all non-contracted, so
    the age proxy dominates), so the depth pool also cliffs in the out-years.
    Returns ({org: [war_2027..2031]}, accounting)."""
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, fp.season_fraction(league, FIRST_SEASON - 1))
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row
    team_war: dict[str, list[float]] = defaultdict(lambda: [0.0] * HORIZON)
    war_unassigned = [0.0] * HORIZON
    n = n_unassigned = 0
    # Contract joins are by normalized name (Spotrac has no mlbam): a depth player
    # sharing a name with ANY projectable player (vet or depth) must not inherit the
    # namesake's contract/team - count name keys over the full projectable universe
    # and leave collided names unassigned (honest) instead of crediting the wrong club.
    _dp_name_counts: dict[str, int] = {}
    for _mid in (set(by_player["hit"]) | set(by_player["pit"])) | vet_mlbams:
        _nm = names.get(_mid)
        if _nm:
            _k = normalize_key(_nm)
            _dp_name_counts[_k] = _dp_name_counts.get(_k, 0) + 1
    _dp_teams = _team_by_mlbam()
    for mlbam in (set(by_player["hit"]) | set(by_player["pit"])) - vet_mlbams:
        champ = [0.0] * HORIZON
        age_any = None
        for side in ("hit", "pit"):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            # Anchor the age offset to the row that supplied the age.
            age_row = next((h for h in hist if h.get("age")), None)
            age = (age_row["age"] + (FIRST_SEASON - age_row["season"])) if age_row else None
            age_any = age or age_any
            cp = fm.contract_war_path(hist, side, FIRST_SEASON, HORIZON, age,
                                      curves, war_map, league,
                                      in_progress=in_prog, use_ml=False)
            if cp is None:
                continue
            arr = cp.get("war_by_year_champ") or cp.get("war_by_year") or []
            for t in range(HORIZON):
                if t < len(arr):
                    champ[t] += float(arr[t] or 0.0)
        if not any(champ):
            continue
        n += 1
        name = names.get(mlbam)
        _dk = normalize_key(name) if name else None
        ct = (contracts.get(_dk) if (_dk and _dp_name_counts.get(_dk, 0) == 1) else None)
        # Same fallback the vet rows use: the depth pool is nearly all pre-arb
        # players, exactly the population Spotrac's contract pages omit.
        org = (ct or {}).get("team_code") or _dp_teams.get(mlbam)
        last_ctrl = _last_controlled_season(
            {"src": "vet", "thru": (ct or {}).get("signed_through"), "age": age_any})
        bucket = team_war[org] if org else war_unassigned
        if not org:
            n_unassigned += 1
        for t in range(HORIZON):
            if FIRST_SEASON + t <= last_ctrl:
                bucket[t] += champ[t]
    acct = {"n_depth_players": n,
            "depth_war_y1": round(sum(v[0] for v in team_war.values()), 1),
            "depth_war_5y": round(sum(sum(v) for v in team_war.values()), 1),
            "n_unassigned": n_unassigned,
            "war_unassigned_y1": round(war_unassigned[0], 1),
            "war_unassigned_5y": round(sum(war_unassigned), 1)}
    return {k: [round(x, 2) for x in v] for k, v in team_war.items()}, acct


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

    # System Duration: surplus-weighted arrival timing per org. etaMean is the
    # bond-math "duration" of a farm (when its surplus arrives, on average);
    # etaByYear is the arrival curve (share of farm surplus landing each season,
    # last bucket = FIRST_SEASON+HORIZON and later). Weight = expected surplus
    # $ (floored at 0 so an over-valued negative-surplus prospect never pulls
    # the center); count-weight fallback keeps a zero-surplus org from vanishing.
    LAST = FIRST_SEASON + HORIZON            # the "and later" bucket edge
    acc: dict[str, dict] = {}
    for p in ts.get("players") or []:
        org = p.get("org")
        eta = p.get("eta") or {}
        yr = eta.get("year")
        if not org or yr is None or org not in out:
            continue
        try:
            yr = int(yr)
        except (TypeError, ValueError):
            continue
        w = max(0.0, float((p.get("surplus") or {}).get("value_mm") or 0.0))
        yr_c = min(LAST, max(FIRST_SEASON, yr))
        a = acc.setdefault(org, {"wsum": 0.0, "wyr": 0.0, "n": 0,
                                 "by": [0.0] * (HORIZON + 1), "cn": 0, "cyr": 0.0})
        a["n"] += 1
        a["cyr"] += yr_c          # count-weighted center fallback
        a["cn"] += 1
        a["wsum"] += w
        a["wyr"] += w * yr_c
        a["by"][yr_c - FIRST_SEASON] += w if w > 0 else 0.0
    for org, a in acc.items():
        if a["wsum"] > 0:
            eta_mean = a["wyr"] / a["wsum"]
            tot = sum(a["by"]) or 1.0
            eta_by = [round(x / tot, 3) for x in a["by"]]
        else:                     # no positive surplus: fall back to count-weight
            eta_mean = a["cyr"] / a["cn"] if a["cn"] else None
            eta_by = None
        out[org]["etaMean"] = round(eta_mean, 2) if eta_mean is not None else None
        out[org]["etaByYear"] = eta_by
        out[org]["etaN"] = a["n"]
    return out


def _team_outlook(vets: list[dict], prospects: list[dict],
                  depth_team_war: dict | None = None,
                  depth_acct: dict | None = None,
                  intercepts: dict | None = None) -> list[dict]:
    """Team WAR roll-up. The DISPLAY headline is the first projected season
    (47.7 replacement baseline + roster WAR -> projected wins; PRE-FREE-AGENCY
    frame, forward-gated against actual standings). On top of that, the
    multi-year controlled-core machinery powers an organizational CONTROL
    metric: `lockedPct` = the WAR-weighted share of the core's projected
    2027-31 production that the team actually controls (controlled WAR / the
    same players' everyone-stays WAR). Aging affects both numerator and
    denominator, so it cancels - lockedPct isolates cost control: 1.0 = every
    contributor locked through the horizon, low = a core about to leak to free
    agency. `byYear[].war` (controlled WAR per season) drives the decline
    sparkline. Prospects contribute at their org from their ETA forward.

    REPLACEMENT_WINS comes from rate_stabilization (shared with the retro
    backtest in proj_backtest.py)."""
    # bWAR is calibrated so the league's players sum to ~1000 WAR every
    # season (verified 1000/1000/1000 for 2023-25 in war_daily). The
    # rostered universe captures ~56% of that pool (Marcel regression +
    # shrunk playing time + exposure floors), which read as a ~15-win
    # negative bias on every team (the best team projected 83 wins).
    LEAGUE_WINS = 2430.0
    intercepts = intercepts or {}
    depth_team_war = depth_team_war or {}

    teams: dict[str, dict] = {}

    def _team(tm: str) -> dict:
        return teams.setdefault(tm, {
            "raw":  [0.0] * HORIZON,  # CONTROLLED champion-mean roster WAR/season
            "full": [0.0] * HORIZON,  # everyone-stays WAR/season (control denominator)
            "coh":  [0.0] * HORIZON,  # cohort-intercept adjustment, per season
            "n":    [0] * HORIZON,
            "top": []})               # (year1_war, name, key) for the top-3 strip

    # Veterans contribute their champion MEAN per season (the displayed ML
    # quantile head is median-like and must NOT be summed), only through their
    # control window - the 'control cliff' that makes the out-years decline.
    for m in vets:
        tm = m.get("team")
        champ = m.get("warChamp") or []
        if not tm or not champ:
            continue
        last_ctrl = _last_controlled_season(m)
        sides = _row_sides(m)
        age0 = m.get("age")
        t_ = _team(tm)
        for t in range(HORIZON):
            if t >= len(champ):
                continue
            w = champ[t]
            if w is None:
                continue
            # Everyone-stays denominator counts every horizon season (the WAR
            # the player would give THIS team if he never left).
            t_["full"][t] += w
            if FIRST_SEASON + t > last_ctrl:
                continue
            t_["raw"][t] += w
            t_["n"][t] += 1
            # Cohort intercept, re-banded by age-in-season (out-year application
            # is an approximation - the fit was on year-1 residuals).
            band = _age_band((age0 + t) if age0 is not None else None)
            for side in sides:
                t_["coh"][t] += intercepts.get(f"{side}:{band}", 0.0)
        y1 = (m.get("war") or [None])[0]   # displayed year-1 WAR for the strip
        if y1 is not None:
            t_["top"].append((y1, m.get("name"), m.get("key")))

    # Prospects join from their ETA season forward (their mean `war[]` is
    # ETA-aligned, not calendar-aligned). 6-year control >> the horizon, so no
    # in-horizon cliff.
    for m in prospects:
        tm = m.get("team")
        eta = m.get("eta")
        war = m.get("war") or []
        if not tm or eta is None or not war:
            continue
        off = int(eta) - FIRST_SEASON
        if off >= HORIZON:
            continue
        t_ = _team(tm)
        for t in range(max(0, off), HORIZON):
            idx = t - off
            if idx < len(war) and war[idx] is not None:
                t_["raw"][t] += war[idx]
                t_["full"][t] += war[idx]   # prospects are controlled all horizon
                t_["n"][t] += 1
        if off <= 0 and war[0] is not None:
            t_["top"].append((war[0], m.get("name"), m.get("key")))

    farm = _org_farm_blocks()

    # Per-season INDEPENDENT recenter to the 2,430-win league sum. Calibration
    # mirrors year-1 (cohort intercepts + sub-floor depth pool + uniform
    # remainder); applied to every season. In the out-years the freed
    # control-cliff WAR + unassigned depth + future entrants ride the (growing)
    # remainder, pulling teams toward .500 unless their controlled core sustains.
    season_remainder = [0.0] * HORIZON
    for t in range(HORIZON):
        cal_sum = 30 * REPLACEMENT_WINS
        for tm, t_ in teams.items():
            depth_t = (depth_team_war.get(tm) or [0.0] * HORIZON)[t]
            cal_sum += t_["raw"][t] + t_["coh"][t] + depth_t
        season_remainder[t] = (LEAGUE_WINS - cal_sum) / max(len(teams), 1)

    raw_wins_sum_y1 = 30 * REPLACEMENT_WINS + sum(t_["raw"][0] for t_ in teams.values())
    out = []
    for tm, t_ in teams.items():
        t_["top"].sort(reverse=True)
        depth_arr = depth_team_war.get(tm) or [0.0] * HORIZON
        by_year = []
        for t in range(HORIZON):
            war_cal = t_["raw"][t] + t_["coh"][t] + depth_arr[t]
            wins = round(REPLACEMENT_WINS + war_cal + season_remainder[t], 1)
            by_year.append({
                "season": FIRST_SEASON + t,
                "war": round(t_["raw"][t], 1),
                "wins": wins,
                "losses": round(162.0 - wins, 1),
                "winsRaw": round(REPLACEMENT_WINS + t_["raw"][t], 1),
                "depthWar": round(war_cal - t_["raw"][t] + season_remainder[t], 1),
                "n": t_["n"][t],
            })
        y1 = by_year[0]
        # Organizational CONTROL: WAR-weighted share of the core's projected
        # 2027-31 production the team controls (controlled / everyone-stays).
        ctrl5 = sum(t_["raw"])
        full5 = sum(t_["full"])
        locked = max(0.0, min(1.0, ctrl5 / full5)) if full5 > 0.01 else None
        # Window Alignment: does the farm arrive while the big-league core is
        # still under control? coreCenter = WAR-weighted midpoint of the
        # controlled core's 2027-31 production; etaAlignYears = farm arrival
        # center minus coreCenter. <= 0: farm lands inside the window (aligned);
        # positive: it arrives after the core has leaked to free agency (gap).
        fb = farm.get(tm)
        core_w = sum(max(0.0, b["war"]) for b in by_year)
        core_center = (sum((b["season"]) * max(0.0, b["war"]) for b in by_year) / core_w
                       if core_w > 0.01 else None)
        eta_mean = (fb or {}).get("etaMean")
        align = (round(eta_mean - core_center, 2)
                 if (fb and eta_mean is not None and core_center is not None) else None)
        if fb is not None:
            fb = dict(fb)
            fb["coreCenter"] = round(core_center, 2) if core_center is not None else None
            fb["etaAlignYears"] = align
        out.append({
            "team": tm,
            # Back-compat year-1 top-level fields (GFX + older consumers read
            # these directly; identical to the prior single-season output).
            "war": y1["war"], "wins": y1["wins"], "losses": y1["losses"],
            "winsRaw": y1["winsRaw"], "depthWar": y1["depthWar"], "n": y1["n"],
            "byYear": by_year,
            # Cost-controlled core strength + lock-up security.
            "lockedPct": round(locked, 3) if locked is not None else None,
            "ctrlWar5y": round(ctrl5, 1),   # controlled WAR banked over the horizon
            "fullWar5y": round(full5, 1),   # everyone-stays WAR (the denominator)
            "top": [{"name": n, "key": k, "war": round(w, 1)}
                    for w, n, k in t_["top"][:3]],
            "farm": fb,
        })
    out.sort(key=lambda r: -r["wins"])
    _write_team_outlook_eval(out, raw_wins_sum_y1, season_remainder, depth_acct or {})
    return out


def _write_team_outlook_eval(rows: list[dict], raw_wins_sum_y1: float,
                             season_remainder: list[float], depth_acct: dict) -> None:
    """data/team_outlook_eval.json - the league-sum accounting plus the
    shipped calibration composition, committed per the eval-artifact
    standing rule. The retro_backtest block (proj_backtest.py) is
    PRESERVED across re-exports - it is the measurement the calibration
    rests on. The forward gate (MAE vs actual wins) stays pending until
    the first projected season completes; only the first season is
    forward-gateable (out-years are a controlled-core trajectory)."""
    try:
        payload = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    by_season = []
    for t in range(HORIZON):
        seas = [r["byYear"][t] for r in rows if t < len(r.get("byYear") or [])]
        by_season.append({
            "season": FIRST_SEASON + t,
            "roster_war_sum": round(sum(s["war"] for s in seas), 1),
            "wins_sum": round(sum(s["wins"] for s in seas), 1),  # recenters to 2,430
            "remainder_recenter_wins_per_team": round(season_remainder[t], 2),
        })
    payload.update({
        "generated_at": date.today().isoformat(),
        "first_season": FIRST_SEASON,
        "horizon": HORIZON,
        "league_sum_accounting": {
            # Year-1 aliases (back-compat with the calibration guards + external
            # readers); the full series lives under by_season.
            "roster_war_sum": round(sum(r["war"] for r in rows), 1),
            "remainder_recenter_wins_per_team": round(season_remainder[0], 2),
            "roster_war_sum_y1": round(sum(r["war"] for r in rows), 1),
            "league_war_benchmark": 1000,
            "benchmark_basis": "actual league bWAR sums 1000/1000/1000 for 2023/2024/2025 (war_daily)",
            "raw_wins_sum": round(raw_wins_sum_y1, 1),
            "raw_wins_sum_y1": round(raw_wins_sum_y1, 1),
            "target_wins_sum": 2430,
            "depth_pool": depth_acct,
            "by_season": by_season,
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
                    "+ small uniform remainder to the 2,430-win league sum, "
                    "applied per season",
            "limitations": [
                "depth-pool team assignment needs a contract row; unassigned depth WAR rides the uniform remainder",
                "spread stays projection-compressed (correct for a mean projection; bands carry the uncertainty)"],
        },
        "multi_year": {
            "kind": "controlled-core: each player counts only through his control "
                    "window (_last_controlled_season); each season is independently "
                    "recentered to the 2,430-win league sum",
            "display_metric": "the surface shows year-1 W-L + WAR plus lockedPct = "
                    "WAR-weighted control share (controlled / everyone-stays WAR over "
                    "2027-31); aging cancels, so it isolates cost control",
            "limitations": [
                f"only the first season ({FIRST_SEASON}) is forward-gateable; "
                "out-years (2028+) are a controlled-core competitive trajectory, "
                "NOT scored against actual standings",
                "control window = Spotrac signed_through where present, else an "
                "age-based proxy (no service time in the pipeline)",
                "cohort intercepts were fit on year-1 residuals; out-year "
                "application re-bands by age but is an approximation"],
        },
        "forward_gate": {
            "status": "pending",
            "first_scoreable": f"end of the {FIRST_SEASON} season",
            "scope": f"first season only; {FIRST_SEASON + 1}+ are not gateable",
            "metric": "MAE vs actual wins; baseline = prior-season wins carry-forward"},
    })
    # System Duration / Window Alignment coverage + league distribution. A
    # descriptive rollup of committed inputs (eta model validated, surplus
    # validated, controlled-core WAR), so this is disclosure, not a new gate.
    aligns = [r["farm"]["etaAlignYears"] for r in rows
              if r.get("farm") and r["farm"].get("etaAlignYears") is not None]
    etas = [r["farm"]["etaMean"] for r in rows
            if r.get("farm") and r["farm"].get("etaMean") is not None]
    aligns_sorted = sorted(aligns)
    payload["window_alignment"] = {
        "kind": "surplus-weighted farm ETA (etaMean) vs the controlled-core WAR "
                "center (coreCenter); etaAlignYears = etaMean - coreCenter, "
                "<= 0 = farm arrives inside the control window (aligned)",
        "weight": "expected surplus $ (value_mm), floored at 0; count-weight fallback",
        "eta_coverage_orgs": len(etas),
        "align_coverage_orgs": len(aligns),
        "eta_mean_range": [round(min(etas), 2), round(max(etas), 2)] if etas else None,
        "align_median": (round(aligns_sorted[len(aligns_sorted) // 2], 2)
                         if aligns_sorted else None),
        "align_range": [round(aligns_sorted[0], 2), round(aligns_sorted[-1], 2)]
                       if aligns_sorted else None,
        "aligned_org_count": sum(1 for a in aligns if a <= 0),
        "limitations": [
            "etaMean is surplus-weighted by the platform surplus model (its "
            "uncertainty flows through); coreCenter is the controlled-core "
            "trajectory, not a scored contention forecast",
            "orgs whose farm carries no positive-surplus prospect fall back to "
            "a count-weighted center and report no arrival curve"],
    }
    (DATA_DIR / "team_outlook_eval.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")


# ============================================================================
# Current-season (2026) view - Bayesian + Pythag blend, log5 SOS, playoff odds
# ============================================================================
# DARK-LAUNCHED, ADDITIVE overlay. This runs OUTSIDE _team_outlook, after it
# returns, and only ever writes a nested `current` block (+ two flat mirrors) on
# each row - the 2027 byYear[]/wins/war/lockedPct output and team_outlook_eval
# are never touched. When live standings/schedule are absent (offline / degraded
# local build) every team's `current` is None and the row is byte-for-byte the
# 2027-only output. FIRST_SEASON=2027 is the first PROJECTED season; the
# in-progress current season is FIRST_SEASON-1 = 2026.
_PYTHAG_EXP = 1.83               # fixed fallback exponent (baseball-reference standard)
_PYTHAGENPAT_EXP = 0.287         # Smyth/Patriot Pythagenpat: exp = RPG**0.287
CURRENT_PRIOR_PSEUDO_GAMES = 40  # k: prior worth ~1/4 season; wPrior=0.5 at G=40
# StatsAPI 40-man roster status codes -> "out for the bulk of the season" flag,
# used ONLY for the display-only ilOut60 badge (NOT any projection number).
_IL60_CODES = {"D60", "D7D60", "60"}


def _pythag_pct(rs: float | None, ra: float | None,
                g: float | None = None) -> float | None:
    """Pythagorean win expectation from runs scored/allowed.

    When games played `g` is known, use Pythagenpat (Smyth/Patriot): the exponent
    scales with the run environment, exp = ((RS+RA)/G)**0.287, which is materially
    more accurate than a fixed exponent for extreme offenses/pitching and is the
    modern sabermetric standard. Falls back to the fixed 1.83 when G is unavailable
    (e.g. RS/RA present but gamesPlayed absent). NOTE the caller prefers StatsAPI's
    own xWinLoss when present; this fires only when that is missing."""
    if rs is None or ra is None or rs < 0 or ra < 0 or (rs + ra) <= 0:
        return None
    if g and g > 0:
        rpg = (rs + ra) / g
        exp = rpg ** _PYTHAGENPAT_EXP if rpg > 0 else _PYTHAG_EXP
    else:
        exp = _PYTHAG_EXP
    rse = rs ** exp
    rae = ra ** exp
    if rse + rae <= 0:
        return None
    return rse / (rse + rae)


def _talent_prior_pct(win_total: float) -> float:
    """The pure roster-talent prior as a win rate: the model's recentered year-1
    (2027) team win total / 162, clamped to a sane [.20, .80]. This reuses the
    EXISTING machinery (the same `wins` the 2027 view already published) - it does
    NOT recompute the model, and 2026-vs-2027 talent drift is negligible next to
    the k=40 shrinkage."""
    return min(0.80, max(0.20, win_total / 162.0))


def _current_blend(rec: dict, prior_pct: float,
                   k: float = CURRENT_PRIOR_PSEUDO_GAMES) -> dict:
    """Bayesian blend of the roster-talent prior, actual record, and Pythag for
    the in-progress season. Prior acts as k pseudo-games, so it dominates in April
    and fades (never fully) toward the in-season signals by September; Pythag gets
    twice actual's share of the in-season weight (it predicts future record
    better). Projected full-season record banks games played and projects the
    remainder at the forward-looking (prior+Pythag) rate."""
    g = rec.get("gamesPlayed") or 0
    wins = rec.get("wins")
    losses = rec.get("losses")
    actual_pct = rec.get("pct")
    if actual_pct is None and wins is not None and g:
        actual_pct = wins / g
    if actual_pct is None:
        actual_pct = 0.5
    # Prefer StatsAPI's own xWinLoss pythag; else compute from RS/RA.
    if rec.get("pythagWins") is not None and rec.get("pythagLosses") is not None:
        pw, pl = rec["pythagWins"], rec["pythagLosses"]
        pythag_pct = pw / (pw + pl) if (pw + pl) > 0 else None
    else:
        pythag_pct = _pythag_pct(rec.get("rs"), rec.get("ra"), g)
    if pythag_pct is None:
        pythag_pct = prior_pct   # no run data yet -> lean on the prior

    w_prior = k / (k + g)
    in_season = 1.0 - w_prior
    w_actual = in_season * (1.0 / 3.0)
    w_pythag = in_season * (2.0 / 3.0)
    # Forward rate for un-played games drops `actual` (those games are banked).
    fwd_denom = w_prior + w_pythag
    forward_pct = ((w_prior * prior_pct + w_pythag * pythag_pct) / fwd_denom
                   if fwd_denom > 0 else prior_pct)
    wins_to_date = wins if wins is not None else round(actual_pct * g)
    cur_wins = int(round(wins_to_date + max(0, 162 - g) * forward_pct))
    cur_wins = min(162, max(0, cur_wins))
    cur_losses = 162 - cur_wins
    return {
        "gamesPlayed": g,
        "record": f"{wins}-{losses}" if wins is not None and losses is not None else None,
        "actualPct": round(actual_pct, 3),
        "pythagPct": round(pythag_pct, 3),
        "talentPriorPct": round(prior_pct, 3),
        "curWins": cur_wins,
        "curLosses": cur_losses,
        "curPct": round(cur_wins / 162.0, 3),
        "gb": rec.get("divGb"),
        "blendWeights": {"prior": round(w_prior, 3),
                         "actual": round(w_actual, 3),
                         "pythag": round(w_pythag, 3)},
    }


def _attach_current_season(rows: list[dict], standings: dict[str, dict],
                           il_out60: dict[str, int] | None = None,
                           season: int | None = None) -> str | None:
    """Overlay the `current` block onto each team_outlook row IN PLACE and return
    the schedule-source flag ('live' | 'balanced_fallback' | None). rows carry the
    2027 view; `standings` is standings_now(2026). No-op returning None when
    `standings` is empty (degraded/offline) - the 2027 output is left untouched."""
    if not standings:
        return None
    season = season or (FIRST_SEASON - 1)
    il_out60 = il_out60 or {}

    # 1) blend: pure talent prior (2027 team win total / 162) + actual + Pythag.
    prior_by_team: dict[str, float] = {}
    for r in rows:
        tm = r.get("team")
        rec = standings.get(tm)
        if not rec:
            r["current"] = None
            continue
        prior_pct = _talent_prior_pct(r.get("wins") or 0.0)
        prior_by_team[tm] = prior_pct
        cur = _current_blend(rec, prior_pct)
        cur["ilOut60"] = il_out60.get(tm)
        r["current"] = cur
        # flat mirrors for GFX / sortless consumers (mirror war/wins at :859)
        r["curWins"] = cur["curWins"]
        r["curPct"] = cur["curPct"]

    # 2) shared remaining schedule (live -> fallback), used by BOTH SOS + MC.
    import proj_current as pc
    teams_present = [r["team"] for r in rows if r.get("current")]
    sched = pc.remaining_schedule(season)
    sched_source = "live"
    if not sched:
        # fallback needs a per-team games-remaining estimate: 162 - gamesPlayed.
        gr = {r["team"]: max(0, 162 - (r["current"]["gamesPlayed"] or 0))
              for r in rows if r.get("current")}
        sched = pc.balanced_remaining(teams_present, games_remaining=gr)
        sched_source = "balanced_fallback"

    # 3) log5 SOS + remaining-win expectation over that schedule.
    talent = {tm: prior_by_team.get(tm, 0.5) for tm in teams_present}
    sos_vals: dict[str, float] = {}
    for r in rows:
        cur = r.get("current")
        if not cur:
            continue
        tm = r["team"]
        opps = sched.get(tm) or []
        if not opps:
            cur["sos"] = None
            cur["remGames"] = 0
            cur["remWinExp"] = 0.0
            continue
        opp_pcts = [talent.get(o, 0.5) for o in opps]
        sos = sum(opp_pcts) / len(opp_pcts)
        rem_win_exp = sum(pc.log5(talent.get(tm, 0.5), op) for op in opp_pcts)
        cur["sos"] = round(sos, 4)
        cur["remGames"] = len(opps)
        cur["remWinExp"] = round(rem_win_exp, 1)
        sos_vals[tm] = sos
    # SOS rank: 1 = hardest (highest opponent talent). Ties broken by org.
    for rank, tm in enumerate(sorted(sos_vals, key=lambda t: (-sos_vals[t], t)), 1):
        for r in rows:
            if r.get("team") == tm and r.get("current"):
                r["current"]["sosRank"] = rank

    # 4) Monte-Carlo playoff odds over the SAME schedule + pure talent.
    mc_teams = {}
    for r in rows:
        cur = r.get("current")
        tm = r.get("team")
        rec = standings.get(tm)
        if not cur or not rec:
            continue
        mc_teams[tm] = {"wins": rec.get("wins") or 0, "losses": rec.get("losses") or 0,
                        "p": talent.get(tm, 0.5),
                        "league": rec.get("league"), "div": rec.get("div")}
    pairs = pc.remaining_pairs(season) if sched_source == "live" else _pairs_from_sched(sched)
    odds = pc.simulate_playoffs(mc_teams, pairs)
    for r in rows:
        cur = r.get("current")
        if cur is None:
            continue
        o = odds.get(r.get("team"))
        if o:
            cur.update(o)
        else:
            for kf in ("playoffPct", "divisionPct", "wildcardPct",
                       "projWinsMean", "projWinsP10", "projWinsP90"):
                cur.setdefault(kf, None)
    return sched_source


def _pairs_from_sched(sched: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Reconstruct (home, away) pairs from a {org:[opp,...]} fallback schedule,
    de-duplicating the mirrored entries (each game appears on both teams)."""
    seen: dict[tuple, int] = {}
    pairs: list[tuple[str, str]] = []
    for tm, opps in sched.items():
        for op in opps:
            key = tuple(sorted((tm, op)))
            seen[key] = seen.get(key, 0) + 1
    for (a, b), cnt in seen.items():
        for _ in range(max(1, cnt // 2)):
            pairs.append((a, b))
    return pairs


def _il_out60(season: int) -> dict[str, int]:
    """Display-only {org: count of 40-man players on the 60-day IL}. Best-effort;
    {} on any failure (badge just doesn't render). Never feeds a projection."""
    try:
        import proj_current  # noqa: F401  (keep import graph explicit)
        from trades import canonical_org
        from scrapers import _fetch
    except Exception:                                          # noqa: BLE001
        return {}
    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1&season={}".format(season)
    fr = _fetch(teams_url, f"statsapi_teams_{season}", accept_json=True)
    if fr.status != 200 or not fr.body:
        return {}
    out: dict[str, int] = {}
    try:
        teams = json.loads(fr.body).get("teams") or []
    except (ValueError, TypeError):
        return {}
    for t in teams:
        tid, name = t.get("id"), t.get("name")
        org = canonical_org(name or "")
        if not tid or not org or len(org) > 3:
            continue
        rr = _fetch("https://statsapi.mlb.com/api/v1/teams/{}/roster?rosterType=40Man"
                    "&season={}".format(tid, season),
                    f"statsapi_roster_40man_{tid}_{season}", accept_json=True)
        if rr.status != 200 or not rr.body:
            continue
        try:
            roster = json.loads(rr.body).get("roster") or []
        except (ValueError, TypeError):
            continue
        n = sum(1 for p in roster
                if ((p.get("status") or {}).get("code")) in _IL60_CODES)
        if n:
            out[org] = n
    return out


# ============================================================================
# Model Accountability (/projections/#view=accountability)
# ============================================================================
# Curated, ordered registry rows that power the projections surface, paired
# with a friendly card label. The view renders each model's owner-committed
# verdict + methodology straight from the audit ledger (model_registry.json),
# never a re-derived claim, alongside the held-out backtest tables below.
_ACCOUNTABILITY_MODELS = [
    ("fa_war_paths_decay", "Veteran WAR paths"),
    ("mlb_projections_prospects", "Prospect post-ETA paths"),
    ("team_win_projections", "Team win totals"),
    ("prospect_surplus", "Surplus pricing"),
]


def _read_data_json(name: str) -> dict:
    """Best-effort read of a committed data/ artifact; missing or unparseable
    degrades to {} so the accountability block surfaces whatever is present."""
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _accountability_block() -> dict:
    """The Model Accountability surface: the projection models' verdicts +
    methodology from data/model_registry.json, plus the held-out backtest
    'receipts' read verbatim from the committed eval artifacts. Pure
    surfacing - no metric is computed here; the registry is the single source
    of truth (refreshed monthly, gated by test_methodology_freshness.py).
    Each backtest is keyed by its eval_artifact so the frontend can attach it
    to the matching card. Missing artifacts degrade to empty."""
    reg = _read_data_json("model_registry.json")
    by_id = {m["model_id"]: m for m in reg.get("models", [])}
    keep = ("model_id", "surface", "predicts", "champion", "baseline",
            "metric", "verdict", "notes", "eval_artifact", "last_checked",
            "artifact_age_days", "stale")
    models = []
    for mid, label in _ACCOUNTABILITY_MODELS:
        m = by_id.get(mid)
        if m:
            models.append({"label": label, **{k: m.get(k) for k in keep}})

    # Team win totals: the retro backtest (2022-25, holdout-gated) read
    # straight from the committed artifact - per-season team-wins MAE/r for
    # the shipped engine vs the prior-wins baseline, pooled player bias, the
    # ship decision, and the still-pending forward gate.
    to = _read_data_json("team_outlook_eval.json")
    retro = to.get("retro_backtest") or {}
    team_wins = {
        "design": retro.get("design"),
        "per_season": [
            {"season": s.get("season"),
             "n_assigned_players": s.get("n_assigned_players"),
             "is_holdout": s.get("is_holdout"),
             "mae": (s.get("cohort_recentered") or {}).get("mae"),
             "r": (s.get("cohort_recentered") or {}).get("r"),
             "baseline_mae": (s.get("baseline_prior_wins") or {}).get("mae"),
             "baseline_r": (s.get("baseline_prior_wins") or {}).get("r")}
            for s in (retro.get("team_level_per_season") or [])
        ],
        "player_pooled": (retro.get("player_level") or {}).get("pooled"),
        "ship_decision": retro.get("ship_decision"),
        "forward_gate": to.get("forward_gate"),
    } if retro else {}

    # Veteran WAR paths: the touched-once 2022-24 holdout - the shipped
    # champion (proj_lgbm_v1) against the prior champion / baseline
    # (marcel_decay_v2), per horizon. Holdout labels mature only through h4.
    he = _read_data_json("proj_horizon_eval.json")
    cb = he.get("challenger_blocks") or {}

    def _horizon_rows(block) -> list[dict]:
        # `coverage` is the POOLED band coverage. The eval harness's own
        # docstring warns absent seasons (actual=0) sit inside almost any
        # P10-P90 band, so pooled coverage reads trivially high (~0.9+) and is
        # NOT band reliability. Surface the honest reads alongside it -
        # coverage_survived (only players who actually played the target
        # season, plus its n) and the pinball loss (the proper quantile scoring
        # rule) - so the accountability view is not misleadingly optimistic.
        # All four are already computed and committed on each horizon block by
        # proj_eval; this is pure surfacing (additive - the frontend still
        # reads h/n/mae/bias/coverage and degrades absent the new fields).
        hz = (block or {}).get("horizons") or {}
        return [{"h": int(h), "n": v.get("n"), "mae": v.get("mae"),
                 "bias": v.get("bias"), "coverage": v.get("coverage"),
                 "coverage_survived": v.get("coverage_survived"),
                 "n_survived": v.get("n_survived"),
                 "pinball_q10": v.get("pinball_q10"),
                 "pinball_q90": v.get("pinball_q90"),
                 "mae_star": v.get("mae_star"), "n_star": v.get("n_star")}
                for h, v in sorted(hz.items(), key=lambda kv: int(kv[0]))]

    vet_horizons = {
        "frame": "2022-2024 holdout (touched once; labels mature through h4)",
        "champion": {"model": "proj_lgbm_v1",
                     "horizons": _horizon_rows(cb.get("holdout_2022_2024"))},
        "baseline": {"model": "marcel_decay_v2",
                     "horizons": _horizon_rows(cb.get("holdout_2022_2024_champion"))},
    } if cb.get("holdout_2022_2024") else {}

    # Prospect post-ETA paths: forward-chained debut cohorts. The FV-only
    # scouting-consensus model (the shipped champion, labeled "baseline" in
    # the artifact's A/B) vs the MiLB-stats ridge challenger that lost its
    # pre-registered gate - committed either way.
    pe = _read_data_json("prospect_path_eval.json")
    champ = pe.get("baseline_pooled_oos") or {}
    chall = pe.get("challenger_pooled_oos") or {}
    prospect_paths = {
        "scored_years": pe.get("scored_years"),
        "champion": {"label": "FV outcome model (scouting consensus)",
                     "n": champ.get("n"), "mae": champ.get("mae"),
                     "spearman": champ.get("spearman")},
        "challenger": {"label": "MiLB-stats ridge (committed loss)",
                       "n": chall.get("n"), "mae": chall.get("mae"),
                       "spearman": chall.get("spearman")},
        "ship_decision": pe.get("ship_decision"),
    } if champ else {}

    return {
        "generated_at": date.today().isoformat(),
        "registry_version": reg.get("version"),
        "verdict_enum": reg.get("verdict_enum"),
        "models": models,
        # keyed by eval_artifact so the frontend attaches each table to its card
        "backtests": {
            "data/team_outlook_eval.json": team_wins,
            "data/proj_horizon_eval.json": vet_horizons,
            "data/prospect_path_eval.json": prospect_paths,
        },
    }


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
    # Current-season (2026) overlay - ADDITIVE, dark-launched. Best-effort: any
    # fetch failure (offline / degraded local build) leaves team_outlook exactly
    # as the 2027-only output and mc_schedule_source None. FIRST_SEASON-1 = 2026.
    mc_schedule_source = None
    try:
        from fa_fit_backtest import standings_now as _standings_now
        _sn = _standings_now(FIRST_SEASON - 1)
        if _sn:
            mc_schedule_source = _attach_current_season(
                team_outlook, _sn, il_out60=_il_out60(FIRST_SEASON - 1),
                season=FIRST_SEASON - 1)
    except Exception:                                          # noqa: BLE001
        log.warning("current-season overlay skipped (best-effort)", exc_info=True)
    cfg = vf._config()
    re_anchor = (cfg["dollars_per_war"].get("_fa_reanchor") or {})
    return {
        "generated_at": date.today().isoformat(),
        # Which dollar calibration priced surNpv on the prospect rows.
        "calibration": vf.calibration_stamp(),
        "first_season": FIRST_SEASON, "horizon": HORIZON,
        # Provenance for the rest-of-season control leg (surRos / surTotal):
        # the share of the in-progress season already played, and therefore the
        # share still being sold. Published so a reader can reconstruct surRos
        # instead of taking it on trust.
        "season_fraction": round(fp.season_fraction(corpus["league"],
                                                    FIRST_SEASON - 1), 3),
        "ros_fraction": round(max(0.0, min(1.0, 1.0 - fp.season_fraction(
            corpus["league"], FIRST_SEASON - 1))), 3),
        "dpw_usd": int(dpw),
        "dpw_infl": float(cfg.get("dollars_per_war_inflation", 0.05)),
        "dpw_reanchor": re_anchor or None,
        "n_vets": len(vets), "n_prospects": len(prospects),
        "vets": vets, "prospects": prospects,
        "team_outlook": team_outlook,
        "current_season": (FIRST_SEASON - 1) if mc_schedule_source else None,
        "mc_schedule_source": mc_schedule_source,
        "accountability": _accountability_block(),
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
