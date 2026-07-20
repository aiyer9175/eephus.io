# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitcher Alchemy Lab - the sidecar export (data/pal.json).

Assembles the role-conversion board from reachable, mostly-bulk sources
(FanGraphs is 403-blocked, so no Stuff+/role-split scrapes):

  ROLE + rates    bullpen_export.load_season_pitching(year) - StatsAPI season
                  pitching 2018-2026 (GS/G/IP -> role; K%/BB%).
  ARSENAL         pybaseball.statcast_pitcher_arsenal_stats(year) - per-pitch
                  usage / whiff / xwOBA / hard-hit, ONE bulk call per season.
  VELOCITY        pybaseball.statcast_pitcher_pitch_arsenal(year) - avg velo per
                  pitch, bulk.
  PLATOON         StatsAPI sitCodes=vl,vr - OPS-against by batter hand, one
                  leaderboard-style call per pitcher (NOT a feed walk).
  REM+ projection rem_plus (display-only relief projection for SP->RP arms).

Produces three sections (RP->SP candidates, SP->RP candidates, conversion
history) plus a backtest scorecard. The backtest is a SIGN CHECK, not a weight
fitter: the observed conversion sample is tiny and selection-biased, so the fit
weights are frozen priors and we report Spearman rho (pre-conversion fit vs the
held-the-role label) with a caveat, plus where converters fall in the full-pool
fit distribution. The relief K% bump used by the REM+ projection is MEASURED from
the converters themselves.

Run: `python pal_export.py`. Wired into run_monthly (best-effort). NETWORK-GATED:
nothing fetches at import; any pull failure logs and degrades (a null component
just drops from the renormalized blend) rather than aborting."""
from __future__ import annotations

import concurrent.futures as cf
import functools
import json
import logging
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import bullpen_export as be
import pal_conversion as pc
import rem_plus
from pal_conversion import PalArm

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "pal.json"
EVAL_PATH = DATA_DIR / "pal_eval.json"

HISTORY_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]  # 2020 kept out of pairs
CAND_MIN_IP = 20.0
STATSAPI = "https://statsapi.mlb.com/api/v1"


def _num(v):
    return be._num(v)


# --------------------------------------------------------------------------- #
# data pulls (network-gated)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=16)
def load_arsenal(year: int) -> dict:
    """{mlbam: [ {pitch, usage(0-1), whiff(0-1), est_woba, hard_hit(0-1)} ]}."""
    try:
        import pybaseball as pyb
        df = pyb.statcast_pitcher_arsenal_stats(int(year))
    except Exception as e:
        _log.warning("arsenal_stats(%s) failed: %s", year, e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            pid = r.get("player_id")
            if pid is None:
                continue
            out.setdefault(int(pid), []).append({
                "pitch": r.get("pitch_type"),
                "usage": (_num(r.get("pitch_usage")) or 0) / 100.0,
                "whiff": (_num(r.get("whiff_percent")) or 0) / 100.0,
                "est_woba": _num(r.get("est_woba")),
                "hard_hit": (_num(r.get("hard_hit_percent")) or 0) / 100.0,
            })
    except Exception as e:
        _log.warning("arsenal parse(%s) failed: %s", year, e)
    return out


@functools.lru_cache(maxsize=16)
def load_velo(year: int) -> dict:
    """{mlbam: top-fastball avg velo}."""
    try:
        import pybaseball as pyb
        df = pyb.statcast_pitcher_pitch_arsenal(int(year))
    except Exception as e:
        _log.warning("pitch_arsenal velo(%s) failed: %s", year, e)
        return {}
    out: dict = {}
    fb_cols = ["ff_avg_speed", "si_avg_speed", "fc_avg_speed"]
    try:
        for r in df.to_dict("records"):
            pid = r.get("pitcher")
            if pid is None:
                continue
            vs = [_num(r.get(c)) for c in fb_cols if _num(r.get(c)) is not None]
            if vs:
                out[int(pid)] = round(max(vs), 1)
    except Exception as e:
        _log.warning("velo parse(%s) failed: %s", year, e)
    return out


def _platoon_one(pid_year):
    pid, year = pid_year
    import urllib.request as U
    url = (f"{STATSAPI}/people/{pid}/stats?stats=statSplits&sitCodes=vl,vr"
           f"&group=pitching&season={year}&gameType=R")
    try:
        req = U.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with U.urlopen(req, timeout=20) as r:
            d = json.load(r)
        vals, tbf = {}, {}
        for s in d.get("stats", []):
            for sp in (s.get("splits") or []):
                code = (sp.get("split") or {}).get("code")
                st = sp.get("stat") or {}
                ops = _num(st.get("ops"))
                if code in ("vl", "vr") and ops is not None:
                    vals[code] = ops
                    tbf[code] = _num(st.get("battersFaced"))
        mt = (min(tbf["vl"], tbf["vr"]) if tbf.get("vl") is not None and tbf.get("vr") is not None else None)
        return pid, vals.get("vl"), vals.get("vr"), mt
    except Exception:
        return pid, None, None, None


def load_platoon(pid_years: list, workers: int = 12) -> dict:
    """{(mlbam, year): (ops_vl, ops_vr)} for a set of (pid, year) pairs."""
    out: dict = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_platoon_one, py): py for py in pid_years}
        for fut in cf.as_completed(futs):
            pid, year = futs[fut]
            try:
                _pid, vl, vr, mt = fut.result()
                out[(pid, year)] = (vl, vr, mt)
            except Exception:
                out[(pid, year)] = (None, None, None)
    return out


@functools.lru_cache(maxsize=16)
def load_pitch_hand(season: int) -> dict:
    """{mlbam: 'L'|'R'} for every MLB pitcher, one bulk call (reverse platoon)."""
    try:
        data = be._get_json("sports/1/players", {"season": int(season)})
    except Exception as e:
        _log.warning("pitchHand fetch failed: %s", e)
        return {}
    out = {}
    for p in data.get("people", []):
        ph = (p.get("pitchHand") or {}).get("code")
        if p.get("id") and ph:
            out[int(p["id"])] = ph
    return out


@functools.lru_cache(maxsize=1)
def load_bref_pitcher_war() -> dict:
    """{year: {mlbam: bWAR}} - Baseball-Reference pitcher WAR by season, summed
    across in-season stints (traded pitchers), for the "WAR produced by
    conversion" read. One bulk pull (pybaseball.bwar_pitch); best-effort, {} on
    any failure so the history still renders without the WAR column."""
    try:
        import pybaseball as pyb
        df = pyb.bwar_pitch(return_all=True)
    except Exception as e:  # noqa: BLE001
        _log.warning("bref pitcher WAR unavailable: %s", e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            mid, yr, war = r.get("mlb_ID"), r.get("year_ID"), r.get("WAR")
            if mid is None or yr is None or war is None:
                continue
            try:
                mid_i, yr_i, war_f = int(float(mid)), int(yr), float(war)
            except (TypeError, ValueError):
                continue
            out.setdefault(yr_i, {})
            out[yr_i][mid_i] = out[yr_i].get(mid_i, 0.0) + war_f
    except Exception as e:  # noqa: BLE001
        _log.warning("bref pitcher WAR parse failed: %s", e)
        return {}
    return out


def load_player_links() -> dict:
    """{mlbam: link} from data/player_links.json (mlbam <-> prospx key)."""
    try:
        d = json.loads((DATA_DIR / "player_links.json").read_text(encoding="utf-8"))
        return {e["mlbam"]: e for e in (d.get("byKey") or {}).values() if e.get("mlbam")}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _graduated_player_keys() -> frozenset:
    """player_keys of prospects with an MLB debut on record (data/debuts.json).
    A HARD MLB-graduation gate for the prospect watch: anyone here has reached the
    majors and is no longer a conversion-watch prospect. Empty set on any failure
    (never crash the export)."""
    try:
        d = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    except Exception as e:
        _log.warning("debuts.json unavailable for graduation gate: %s", e)
        return frozenset()
    return frozenset(e.get("player_key") for e in d if e.get("player_key"))


def load_prospect_pitchers(exclude_keys: Optional[set] = None) -> list:
    """Prospect pitcher pool with 20-80 scout tool grades. Best-effort: needs the
    prospect DB, so degrades to [] where it is absent (tests / no DB).

    A hard MLB-graduation gate drops anyone with an MLB debut on record
    (data/debuts.json) or with meaningful MLB service (`exclude_keys`, player_keys
    the caller resolves from career MLB innings via player_links). This catches
    established MLB pitchers whose prospect record was never marked debuted
    (e.g. NPB/KBO arrivals like Kodai Senga) that the status signal alone misses."""
    graduated = set(_graduated_player_keys())
    if exclude_keys:
        graduated |= set(exclude_keys)
    try:
        from storage import load_all_snapshots
        from consensus import build_timeseries, _is_pitcher_pos, ADOPT_NORMALIZED_CONSENSUS
        ts = build_timeseries(load_all_snapshots(), normalize=ADOPT_NORMALIZED_CONSENSUS)
    except Exception as e:
        _log.warning("prospect pool load unavailable: %s", e)
        return []
    out = []
    for p in ts:
        try:
            if p.player_key in graduated:
                continue    # hard MLB-graduation gate (debuted or meaningful MLB service)
            if getattr(p, "status", "") != "active" or not _is_pitcher_pos(p.position):
                continue
            pt = p.points[-1] if getattr(p, "points", None) else None
            tools = (getattr(pt, "tools_consensus", None) or getattr(pt, "tools", None) or {}) if pt else {}
            keys = list(pc.PROSPECT_TOOL_KEYS) + ["cmd"]
            tools = {k: _num(tools.get(k)) for k in keys if _num(tools.get(k)) is not None}
            if not tools:
                continue
            out.append({"player_key": p.player_key, "name": p.player_name, "org": p.org,
                        "position": p.position, "fv": _r(getattr(p, "fv_close", None), 1), "tools": tools})
        except Exception:
            continue
    return out


MLB_SERVICE_IP = 50.0   # career MLB innings that mark a pitcher as graduated


def _mlb_service_keys(by_pid: dict, links: dict) -> set:
    """player_keys of pitchers with meaningful career MLB innings (>= MLB_SERVICE_IP
    across the loaded seasons), resolved from their MLBAM id via player_links. The
    service half of the prospect-watch graduation gate (backstops debuts.json for
    foreign-league arrivals the debut tracker never marked)."""
    keys = set()
    for mlbam, byyr in by_pid.items():
        try:
            tot = sum(be.ip_to_float(r.get("IP")) for r in byyr.values())
        except Exception:
            continue
        if tot < MLB_SERVICE_IP:
            continue
        lk = links.get(mlbam)
        if lk and lk.get("key"):
            keys.add(lk["key"])
    return keys


def _prospect_role(pos: Optional[str]) -> Optional[str]:
    pos = (pos or "").upper()
    if "SP" in pos:
        return "SP"
    if "RP" in pos or "IRP" in pos or "CL" in pos:
        return "RP"
    return None


def _was_starter(by_pid: dict, mlbam: int, cur_season: int) -> bool:
    """Did this pitcher hold a starting role in a prior MLB season (>= ~half a
    rotation turn)? The free MLB-history half of the starter-pedigree signal."""
    for y, r in by_pid.get(mlbam, {}).items():
        if y >= cur_season:
            continue
        if pc.role_of(r.get("G"), r.get("GS"), r.get("IP")) == "SP" and be.ip_to_float(r.get("IP")) >= 40:
            return True
    return False


# --------------------------------------------------------------------------- #
# arm assembly
# --------------------------------------------------------------------------- #
def build_arm(row: dict, arsenal: dict, velo: dict, platoon: dict, year: int) -> PalArm:
    mlbam = row["mlbam"]
    tbf = _num(row.get("BF")) or 0
    so = _num(row.get("SO")) or 0
    bb = _num(row.get("BB")) or 0
    ipf = be.ip_to_float(row.get("IP"))
    er = _num(row.get("ER")) or 0
    plat = platoon.get((mlbam, year)) or (None, None, None)
    return PalArm(
        mlbam=mlbam, name=row.get("name", ""), team=row.get("team", ""), season=year,
        role=pc.role_of(row.get("G"), row.get("GS"), row.get("IP")) or "",
        g=_num(row.get("G")) or 0, gs=_num(row.get("GS")) or 0, ip=ipf, tbf=tbf,
        k_pct=(so / tbf) if tbf else None, bb_pct=(bb / tbf) if tbf else None,
        era=(er * 9.0 / ipf) if ipf else None,
        arsenal=arsenal.get(mlbam, []), fb_velo=velo.get(mlbam),
        ops_vl=plat[0], ops_vr=plat[1], platoon_tbf=(plat[2] if len(plat) > 2 else None),
    )


# --------------------------------------------------------------------------- #
# backtest helpers
# --------------------------------------------------------------------------- #
def _spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return None if vx == 0 or vy == 0 else cov / (vx * vy)


def _build_rem_pool(rows_2026: list, arsenal, velo, platoon) -> rem_plus.Pool:
    relievers = be.build_relievers(rows_2026, {}, {})
    pool = [r for r in relievers if rem_plus.is_true_reliever(r)]
    for r in pool:
        rem_plus.derive_rates(r)
    return rem_plus.build_pool(pool)


def build_prospect_watch(prospects: list, cap: int = 150) -> list:
    """The /pal/ prospect conversion watch: the role MISMATCHES worth a look (a
    scouted starter that profiles as a reliever, or vice versa), gated to real
    prospects (FV >= 40) and capped. Shape-only (scout tools, no MiLB stuff physics).

    Each entry carries `player_key` so a consumer (prospx pitcher cards) can join
    the role-fit read back onto its own prospect board by the canonical prospect
    key -- the reason this is a named helper rather than an inline loop."""
    watch = []
    for p in prospects:
        rf = pc.prospect_role_fit(p.get("tools"), p.get("position"))
        if not rf["mismatch"] or (p.get("fv") or 0) < 40:
            continue
        watch.append({"player_key": p.get("player_key"), "name": p["name"],
                      "org": p.get("org"), "position": p.get("position"),
                      "fv": p.get("fv"), "tools": p.get("tools"), **rf})
    watch.sort(key=lambda x: -(x.get("fv") or 0))
    return watch[:cap]


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  pal: loading season pitching {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]}...")
    by_pid: dict = {}
    rows_by_year: dict = {}
    for y in HISTORY_YEARS:
        rows = be.load_season_pitching(y)
        rows_by_year[y] = rows
        for r in rows:
            r = dict(r); r["season"] = y
            by_pid.setdefault(r["mlbam"], {})[y] = r
    if not rows_by_year.get(season):
        log(f"  pal: no {season} pitching (source blocked); skipping")
        return 0

    # conversions from role flips (cheap, season-stats only). The current
    # season is in progress, so held labels only read seasons through season-1
    # (T1-6: an in-progress b+1 GS-share is not a settled role).
    events = pc.detect_conversions(by_pid, last_closed_season=season - 1)
    log(f"  pal: detected {len(events)} role conversions {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]}")
    # Current-season (in-progress) conversions that season-cumulative role_of misses
    # because a mid-year switch reads as SWING (e.g. Griffin Jax 2026). Always pending;
    # merged de-duped so a pitcher already caught by the historical detector isn't doubled.
    _seen = {(e["mlbam"], e["year"]) for e in events}
    _inprog = [e for e in pc.detect_in_progress_conversions(by_pid, HISTORY_YEARS[-1])
               if (e["mlbam"], e["year"]) not in _seen]
    events.extend(_inprog)
    log(f"  pal: + {len(_inprog)} in-progress {HISTORY_YEARS[-1]} conversions")

    # measured relief K% bump from the converters (RP->SP loses K, SP->RP gains)
    sp2rp_dk = [ (_num(e["post"]["k_pct"]) - _num(e["pre"]["k_pct"]))
                 for e in events if e["direction"] == "SP->RP"
                 and e["post"]["k_pct"] is not None and e["pre"]["k_pct"] is not None ]
    relief_k_bump = round(statistics.median(sp2rp_dk), 4) if len(sp2rp_dk) >= 5 else pc.DEFAULT_RELIEF_K_BUMP

    log("  pal: pulling arsenal + velocity (bulk Statcast)...")
    arsenal_by_year = {y: load_arsenal(y) for y in HISTORY_YEARS}
    velo_by_year = {y: load_velo(y) for y in HISTORY_YEARS}

    # who needs platoon: the current candidate pool + each converter's TRUE
    # pre-year. detect_conversions pairs seasons up to 2 apart (2020 excluded,
    # injury gaps), so the pre row is e["pre"]["season"], NOT year-1 (T1-6:
    # year-1 silently dropped every gap-2 event from the backtest).
    cur_rows = rows_by_year[season]
    cand_pids = [(r["mlbam"], season) for r in cur_rows
                 if be.ip_to_float(r.get("IP")) >= CAND_MIN_IP]
    pre_pids = [(e["mlbam"], (e.get("pre") or {}).get("season", e["year"] - 1))
                for e in events]
    log(f"  pal: pulling platoon splits for {len(set(cand_pids) | set(pre_pids))} pitcher-seasons...")
    platoon = load_platoon(list(set(cand_pids) | set(pre_pids)))

    # REM+ pool (current relievers) for the SP->RP relief projection
    rem_pool = _build_rem_pool(cur_rows, arsenal_by_year[season], velo_by_year[season], platoon)

    # extensions: throwing hand (reverse platoon), MLB + PROSPX starter pedigree
    pitch_hand = load_pitch_hand(season)
    # ... and for the backtest pre-arms: hand is static, so merge the bulk
    # players call across each distinct pre-year (T1-6: backtested scores must
    # carry the same p_throws input the live board scores do).
    hand_all = {}
    for y in sorted({(e.get("pre") or {}).get("season", e["year"] - 1) for e in events}):
        if y != season:
            hand_all.update(load_pitch_hand(y) or {})
    hand_all.update(pitch_hand)
    links = load_player_links()
    # hard MLB-graduation gate for the prospect watch: anyone with meaningful MLB
    # service (career innings across the loaded seasons) has graduated even when
    # the debut tracker missed them (e.g. NPB/KBO arrivals like Senga). Resolve
    # those MLBAM ids back to prospect player_keys via player_links.
    served = _mlb_service_keys(by_pid, links)
    prospects = load_prospect_pitchers(exclude_keys=served)
    prospx_role_map = {p["player_key"]: _prospect_role(p.get("position")) for p in prospects}

    def _prospx_role_for(mlbam):
        lk = links.get(mlbam)
        return prospx_role_map.get(lk.get("prospx")) if lk and lk.get("prospx") else None

    # ---- current candidates -------------------------------------------------
    rp2sp, sp2rp, platoon_rows = [], [], []
    for r in cur_rows:
        if be.ip_to_float(r.get("IP")) < CAND_MIN_IP:
            continue
        arm = build_arm(r, arsenal_by_year[season], velo_by_year[season], platoon, season)
        arm.p_throws = pitch_hand.get(arm.mlbam)
        arm.was_starter = _was_starter(by_pid, arm.mlbam, season)
        arm.prospx_role = _prospx_role_for(arm.mlbam)
        rp = pc.reverse_platoon(arm)
        if rp:
            platoon_rows.append({"mlbam": arm.mlbam, "name": arm.name, "team": arm.team,
                                 "role": arm.role, "min_tbf": _r(arm.platoon_tbf, 0), **rp})
        if arm.role == "RP" and arm.arsenal:
            fit = pc.rp_sp_fit(arm)
            row = _cand_row(arm, fit, "rp2sp")
            row["pitch_add"] = pc.recommend_pitch(arm)
            row["reverse_platoon"] = rp
            rp2sp.append(row)
        elif arm.role == "SP" and arm.arsenal:
            fit = pc.sp_rp_fit(arm)
            row = _cand_row(arm, fit, "sp2rp")
            row["proj_relief_rem_plus"] = pc.project_relief_rem_plus(arm, rem_pool, relief_k_bump)
            sp2rp.append(row)
    rp2sp.sort(key=lambda x: x["fit"], reverse=True)
    sp2rp.sort(key=lambda x: x["fit"], reverse=True)
    # reverse-platoon radar: most-reverse first (a hidden strength), extremes flagged
    platoon_rows.sort(key=lambda x: x["reverse_index"], reverse=True)

    # ---- conversion history + backtest -------------------------------------
    war_by_year = load_bref_pitcher_war()   # {year: {mlbam: bWAR}}, best-effort
    history, mix_changes = [], []
    pre_fits, labels = [], []           # legacy pooled read (REPORTING ONLY)
    per_dir = {d: {"fit_war": [], "war": [], "fit_held": [], "held": []}
               for d in ("RP->SP", "SP->RP")}
    for e in events:
        # TRUE pre-season (T1-6): the season the detector actually paired.
        # year-1 lost every gap-2 pair (2020 exclusion / injury gaps) and
        # silently dropped them from the labeled backtest set.
        py = (e.get("pre") or {}).get("season", e["year"] - 1)
        pre_row = by_pid.get(e["mlbam"], {}).get(py)
        pre_fit = None
        if pre_row and pre_row.get("mlbam") in arsenal_by_year.get(py, {}):
            pre_arm = build_arm(pre_row, arsenal_by_year.get(py, {}), velo_by_year.get(py, {}), platoon, py)
            # backtested scores carry the SAME inputs the live board scores do
            # (T1-6): throwing hand + the +3.0 starter-pedigree nudge.
            pre_arm.p_throws = hand_all.get(pre_arm.mlbam)
            pre_arm.was_starter = _was_starter(by_pid, pre_arm.mlbam, py)
            if pre_arm.arsenal:
                fit = (pc.rp_sp_fit(pre_arm) if e["direction"] == "RP->SP"
                       else pc.sp_rp_fit(pre_arm))
                pre_fit = fit["fit"]
        succ = pc.label_success(e)
        h = dict(e); h["pre_fit"] = pre_fit
        h["success"] = succ
        # WAR produced by the conversion: bWAR in the pre-role season vs the
        # post-role season, plus the delta. Keyed by the seasons the detector
        # recorded. Absent (older season or no bref row) renders as a dash.
        pre_season = (e.get("pre") or {}).get("season", py)
        post_season = (e.get("post") or {}).get("season", e["year"])
        pre_war = (war_by_year.get(pre_season) or {}).get(e["mlbam"])
        post_war = (war_by_year.get(post_season) or {}).get(e["mlbam"])
        h["pre_war"] = None if pre_war is None else round(pre_war, 1)
        h["post_war"] = None if post_war is None else round(post_war, 1)
        h["war_delta"] = (None if pre_war is None or post_war is None
                          else round(post_war - pre_war, 1))
        # pitch-mix change (before/after arsenal usage) for the converter,
        # attached INLINE to the record so the history view can show the arsenal
        # shift per conversion (kept as a standalone array too).
        pre_ars = arsenal_by_year.get(py, {}).get(e["mlbam"])
        post_ars = arsenal_by_year.get(e["year"], {}).get(e["mlbam"])
        if pre_ars and post_ars:
            before, after = _mix(pre_ars), _mix(post_ars)
            h["pitch_mix"] = {"before": before, "after": after}
            mix_changes.append({
                "mlbam": e["mlbam"], "name": e["name"], "team": e["team"],
                "direction": e["direction"], "year": e["year"],
                "before": before, "after": after,
            })
        history.append(h)
        if pre_fit is not None and succ is not None:
            pre_fits.append(pre_fit)
            labels.append(1.0 if succ else 0.0)
            if e["direction"] in per_dir:
                per_dir[e["direction"]]["fit_held"].append(pre_fit)
                per_dir[e["direction"]]["held"].append(1.0 if succ else 0.0)
        # PRIMARY continuous outcome (T1-6): war_delta, PER DIRECTION (the two
        # fit scores are different 0-100 scales - pooling them was never
        # meaningful), closed post seasons only (a partial in-progress post
        # season deflates bWAR mechanically).
        if (pre_fit is not None and h["war_delta"] is not None
                and post_season < season and e["direction"] in per_dir):
            per_dir[e["direction"]]["fit_war"].append(pre_fit)
            per_dir[e["direction"]]["war"].append(h["war_delta"])
    history.sort(key=lambda h: (h["year"], -(h["pre_fit"] or 0)), reverse=True)

    rho = _spearman(pre_fits, labels)   # legacy pooled - REPORTING ONLY, not the gate
    per_direction = {}
    for d, v in per_dir.items():
        rw = _spearman(v["fit_war"], v["war"])
        rh = _spearman(v["fit_held"], v["held"])
        per_direction[d] = {
            "n_war": len(v["war"]),
            "rho_prefit_vs_war_delta": None if rw is None else round(rw, 3),
            "n_held": len(v["held"]),
            "rho_prefit_vs_held": None if rh is None else round(rh, 3),
        }
    # where do converters fall in the full-pool fit distribution (selection-bias check)
    full_rp_fits = sorted(x["fit"] for x in rp2sp)
    conv_rp_pct = _percentile_of([h["pre_fit"] for h in history
                                  if h["direction"] == "RP->SP" and h["pre_fit"] is not None], full_rp_fits)

    backtest = {
        "n_labeled": len(pre_fits),
        "spearman_prefit_vs_held": None if rho is None else round(rho, 3),
        "per_direction": per_direction,
        "primary_outcome": ("war_delta (bWAR post-season minus pre-season), per direction, "
                            "closed post seasons only; the pooled held rho above is a legacy "
                            "reporting field (two different 0-100 scales)"),
        "relief_k_bump_measured": relief_k_bump,
        "converter_median_fit_pool_pctile": conv_rp_pct,
        "disclaimer": ("A screen, not a success-probability model. The conversion sample is small and "
                       "selection-biased (only pitchers teams chose to convert), so the weights are frozen "
                       "priors from the literature. The gated evaluation (per-direction rho vs same-event "
                       "baselines, bootstrap CI) lives in tools/pal_backtest_lab.py -> data/pal_eval.json; "
                       "the rhos here are the live stamp of the same repaired harness. Held labels read "
                       "closed >=20 IP follow-up seasons only."),
    }

    # pitch-add lab: RP->SP candidates with a recommended weapon to add
    pitch_add = [{"mlbam": r["mlbam"], "name": r["name"], "team": r["team"], "fit": r["fit"],
                  "n_pitches": r["n_pitches"], "arsenal": r["arsenal"],
                  "platoon_split": r["platoon_split"], "rec": r["pitch_add"]}
                 for r in rp2sp if r.get("pitch_add")]

    # prospect conversion watch (shape-only, no MiLB stuff physics): the role
    # MISMATCHES worth a look (a scouted starter that profiles as a reliever, or
    # vice versa), gated to real prospects (FV >= 40) and capped. Each entry now
    # carries player_key so prospx can cross-link the role-fit read onto its
    # pitcher cards (see build_prospect_watch).
    prospect_watch = build_prospect_watch(prospects)

    payload = {
        "generated_at": today, "season": season,
        "n_conversions": len(events),
        "rp2sp": rp2sp, "sp2rp": sp2rp, "history": history,
        "pitch_mix_changes": mix_changes,
        "pitch_add": pitch_add,
        "reverse_platoon": platoon_rows,
        "prospect_watch": prospect_watch,
        "n_prospects": len(prospects),
        "backtest": backtest,
        "verdict": _verdict(),
    }

    log(f"  pal: {len(rp2sp)} RP->SP, {len(sp2rp)} SP->RP, {len(events)} conversions, "
        f"{len(prospect_watch)} prospect pitchers, {len(platoon_rows)} platoon rows; "
        f"backtest rho={backtest['spearman_prefit_vs_held']} (n={backtest['n_labeled']})")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        try:
            shown = out_path.relative_to(Path(__file__).parent)
        except ValueError:
            shown = out_path.name
        log(f"  pal: wrote {shown}")
    return len(rp2sp) + len(sp2rp)


def _cand_row(arm: PalArm, fit: dict, kind: str) -> dict:
    row = {
        "mlbam": arm.mlbam, "name": arm.name, "team": arm.team,
        "fit": fit["fit"], "n_pitches": fit["n_pitches"],
        "ip": round(arm.ip, 1), "k_pct": _r(arm.k_pct, 4), "bb_pct": _r(arm.bb_pct, 4),
        "fb_velo": arm.fb_velo, "proj_velo": fit.get("proj_velo"),
        "fb_pct": fit.get("fb_pct"),
        "platoon_split": (round(abs(arm.ops_vl - arm.ops_vr), 3)
                          if arm.ops_vl is not None and arm.ops_vr is not None else None),
        "components": fit["components"], "flags": fit["flags"],
        # succeeding in his CURRENT role? (display-only tiering signal, ERA + K-BB)
        "successful": pc.role_success(arm),
        "arsenal": [{"pitch": p.get("pitch"), "usage": _r(p.get("usage"), 3),
                     "whiff": _r(p.get("whiff"), 3), "est_woba": _r(p.get("est_woba"), 3)}
                    for p in arm.arsenal if (p.get("usage") or 0) >= 0.03],
    }
    if kind == "sp2rp":
        row["best_whiff"] = fit.get("best_whiff")
        row["relief_upside"] = fit.get("relief_upside")
        row["starter_era"] = fit.get("starter_era")
    return row


def _mix(arsenal: list) -> list:
    return sorted([{"pitch": p.get("pitch"), "usage": round((p.get("usage") or 0), 3)}
                   for p in arsenal if (p.get("usage") or 0) >= 0.03],
                  key=lambda x: x["usage"], reverse=True)


def _percentile_of(vals: list, dist: list):
    vals = [v for v in vals if v is not None]
    if not vals or not dist:
        return None
    med = statistics.median(vals)
    below = sum(1 for d in dist if d <= med)
    return round(100.0 * below / len(dist))


def _r(v, n):
    v = _num(v)
    return None if v is None else round(v, n)


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        return (j.get("verdict") or {}).get("status") or "provisional"
    except Exception:
        return "provisional"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export(int(sys.argv[1]) if len(sys.argv) > 1 else None)
