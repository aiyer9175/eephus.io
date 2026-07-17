# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""pal_gamelogs - T1-13: sportId=1-restricted MLB game-log pulls for PAL.

The season-cumulative role read (pal_conversion.role_of) cannot see a MID-YEAR
role switch: a reliever who moves into the rotation in June reads SWING for the
whole season, so detect_conversions drops the pair (both sides must be a clean
SP/RP). This module pulls per-game MLB pitching logs (the statcast_metrics
._game_logs hydrate pattern, restricted to sportId=1 - the one-line loop
restriction below) and derives:

  LANE A  mid-year switch detection inside a SWING season (strict attempt
          definition, pre-registered constants below) + terminal-role reads for
          swing-bridge pairs (an RP season -> SWING bridge -> SP season). These
          come back as TAGGED events only; pal_conversion.detect_conversions is
          NEVER touched, so the legacy event set reproduces byte-identical with
          recovery off.
  LANE B  relief-usage features for RP->SP candidates: multi_inning_share
          (share of relief appearances with >= 4 outs recorded) and b2b_rate
          (share of relief appearances on the day after a previous appearance).
          A reliever his org already stretches out is structurally closer to a
          starter than a max-effort back-to-back one-inning arm.

Network: one StatsAPI call per pitcher-season, disk-cached under
.cache/pal_gamelogs/ (closed seasons effectively forever, the current season
1 day). Pure feature math everywhere else.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import bullpen_export as be
import pal_conversion as pc

MLB_STATS_API = "https://statsapi.mlb.com/api/v1"

# repo root: env override first (lane workspaces), then this file's parent
_ENV_ROOT = os.environ.get("EEPHUS_ROOT")
ROOT = Path(_ENV_ROOT) if _ENV_ROOT else Path(__file__).resolve().parent
if not (ROOT / ".cache").exists():                       # lane-workspace fallback
    _cand = Path(r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
    if (_cand / ".cache").exists():
        ROOT = _cand
CACHE_DIR = ROOT / ".cache" / "pal_gamelogs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# same sport map as statcast_metrics (kept whole so the restriction is explicit)
SPORT_LEVELS = {
    1:  "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "CPX",
    17: "DSL",
}

SESSION = requests.Session()
_retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retries, pool_connections=20, pool_maxsize=20)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)


def _get_json(url: str, params: dict | None = None, ttl_seconds: int = 7 * 86400) -> dict:
    key = requests.Request("GET", url, params=params).prepare().url or url
    safe = hashlib.md5(key.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
        return json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.04)
    resp = SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _game_logs(player_id: int, season: int, is_pitcher: bool = True,
               ttl_seconds: Optional[int] = None) -> list[dict]:
    """statcast_metrics._game_logs pattern, MLB only. Closed seasons cache ~forever."""
    if ttl_seconds is None:
        ttl_seconds = 86400 if int(season) >= date.today().year else 10 * 365 * 86400
    group = "pitching" if is_pitcher else "hitting"
    out: list[dict] = []
    seen: set[int] = set()
    for sport_id, level in SPORT_LEVELS.items():
        if sport_id != 1:          # T1-13: PAL is an MLB-role lane - sportId=1 ONLY
            continue
        data = _get_json(
            f"{MLB_STATS_API}/people/{player_id}",
            {
                "hydrate": (
                    f"stats(group={group},type=gameLog,season={season},"
                    f"sportId={sport_id},gameType=[R]),hydrations"
                )
            },
            ttl_seconds=ttl_seconds,
        )
        people = data.get("people") or []
        stats = (people[0].get("stats") or []) if people else []
        for split in (stats[0].get("splits") if stats else []) or []:
            game_pk = (split.get("game") or {}).get("gamePk")
            if not game_pk or int(game_pk) in seen:
                continue
            seen.add(int(game_pk))
            split["_level"] = level
            out.append(split)
    return out


def _num(v):
    return be._num(v)


def appearances(player_id: int, season: int) -> list[dict]:
    """Ordered per-game pitching lines: date, start flag, outs, and rate inputs."""
    apps = []
    for sp in _game_logs(int(player_id), int(season), is_pitcher=True):
        st = sp.get("stat") or {}
        d = sp.get("date") or ((sp.get("game") or {}).get("officialDate"))
        if not d:
            continue
        ip = be.ip_to_float(st.get("inningsPitched"))
        apps.append({
            "date": d,
            "start": int(_num(st.get("gamesStarted")) or 0) > 0,
            "outs": int(round(ip * 3)),
            "ip": round(ip, 1),
            "bf": _num(st.get("battersFaced")) or 0,
            "so": _num(st.get("strikeOuts")) or 0,
            "bb": _num(st.get("baseOnBalls")) or 0,
            "er": _num(st.get("earnedRuns")) or 0,
        })
    apps.sort(key=lambda a: a["date"])
    return apps


# --------------------------------------------------------------------------- #
# LANE B: relief-usage features
# --------------------------------------------------------------------------- #
MULTI_INNING_OUTS = 4        # a >= 4-out relief appearance counts as multi-inning
MIN_RELIEF_APPS_FEAT = 8     # feature undefined under this relief-appearance sample


def _d(iso: str) -> date:
    y, m, dd = iso.split("-")
    return date(int(y), int(m), int(dd))


def relief_usage_features(apps: list[dict]) -> Optional[dict]:
    """multi_inning_share + b2b_rate over a season's RELIEF appearances.
    None when the relief sample is under MIN_RELIEF_APPS_FEAT (starters,
    cameo relievers): the feature simply drops from the renormalized blend."""
    relief = [a for a in apps if not a["start"]]
    if len(relief) < MIN_RELIEF_APPS_FEAT:
        return None
    all_dates = {_d(a["date"]) for a in apps}
    mi = sum(1 for a in relief if a["outs"] >= MULTI_INNING_OUTS)
    b2b = sum(1 for a in relief if (_d(a["date"]) - timedelta(days=1)) in all_dates)
    n = len(relief)
    return {
        "multi_inning_share": round(mi / n, 4),
        "b2b_rate": round(b2b / n, 4),
        "n_relief_apps": n,
    }


# --------------------------------------------------------------------------- #
# LANE A: strict mid-year switch detection + terminal role (pre-registered)
# --------------------------------------------------------------------------- #
MIN_PRE_RELIEF = 8           # relief apps before the switch (RP->SP attempt)
MIN_POST_STARTS = 5          # starts after the switch (RP->SP attempt)
MIN_PRE_STARTS = 5           # starts before the switch (SP->RP attempt)
MIN_POST_RELIEF = 8          # relief apps after the switch (SP->RP attempt)
RELIEF_SEG_START_SHARE_MAX = 0.15   # a relief segment may carry a stray opener/spot start
START_SEG_START_SHARE_MIN = 0.70    # a rotation segment is starts, mostly
TERMINAL_SP_LAST_N, TERMINAL_SP_MIN_STARTS = 6, 5
TERMINAL_RP_LAST_N = 8       # last 8 apps with zero starts => terminal RP


def detect_midyear_switch(apps: list[dict]) -> Optional[dict]:
    """STRICT single-changepoint role switch inside one season's MLB appearance
    sequence. Returns {direction, t, pre, post} (segment lines) or None. The
    strictness is the point (Lane C: most SWING seasons are openers / spot
    starts / injury shuffles, not conversion attempts)."""
    n = len(apps)
    best = None
    for t in range(1, n):
        pre, post = apps[:t], apps[t:]
        pre_starts = sum(a["start"] for a in pre)
        post_starts = sum(a["start"] for a in post)
        pre_share = pre_starts / len(pre)
        post_share = post_starts / len(post)
        cand = None
        if (len(pre) - pre_starts >= MIN_PRE_RELIEF
                and pre_share <= RELIEF_SEG_START_SHARE_MAX
                and post_starts >= MIN_POST_STARTS
                and post_share >= START_SEG_START_SHARE_MIN
                and apps[t]["start"]):
            cand = ("RP->SP", t, (1 - pre_share) + post_share)
        elif (pre_starts >= MIN_PRE_STARTS
                and pre_share >= START_SEG_START_SHARE_MIN
                and len(post) - post_starts >= MIN_POST_RELIEF
                and post_share <= RELIEF_SEG_START_SHARE_MAX
                and not apps[t]["start"]):
            cand = ("SP->RP", t, pre_share + (1 - post_share))
        if cand and (best is None or cand[2] > best[2]):
            best = cand
    if best is None:
        return None
    direction, t, _score = best
    return {"direction": direction, "t": t,
            "pre": _segment_line(apps[:t]), "post": _segment_line(apps[t:])}


def _segment_line(seg: list[dict]) -> dict:
    ip = sum(a["ip"] for a in seg)
    ipf = sum(a["outs"] for a in seg) / 3.0
    bf = sum(a["bf"] for a in seg)
    so = sum(a["so"] for a in seg)
    bb = sum(a["bb"] for a in seg)
    er = sum(a["er"] for a in seg)
    return {
        "g": len(seg), "gs": sum(1 for a in seg if a["start"]),
        "ip": round(ipf, 1),
        "k_pct": round(so / bf, 4) if bf else None,
        "bb_pct": round(bb / bf, 4) if bf else None,
        "era": round(er * 9.0 / ipf, 2) if ipf else None,
        "first": seg[0]["date"], "last": seg[-1]["date"],
    }


def terminal_role(apps: list[dict]) -> Optional[str]:
    """What was he at the END of the season? (swing-bridge read). Conservative:
    None unless the tail is clean."""
    if len(apps) >= TERMINAL_SP_LAST_N:
        lastn = apps[-TERMINAL_SP_LAST_N:]
        if sum(a["start"] for a in lastn) >= TERMINAL_SP_MIN_STARTS:
            return "SP"
    if len(apps) >= TERMINAL_RP_LAST_N:
        lastn = apps[-TERMINAL_RP_LAST_N:]
        if sum(a["start"] for a in lastn) == 0:
            return "RP"
    return None


# --------------------------------------------------------------------------- #
# LANE A: recovery over the season table (returns TAGGED events ONLY)
# --------------------------------------------------------------------------- #
def swing_seasons(by_pid: dict, min_ip: float = pc.CONV_MIN_IP,
                  years: Optional[set] = None) -> list[tuple]:
    """(mlbam, season) of every SWING pitcher-season with a real sample."""
    out = []
    for pid, byyr in by_pid.items():
        for y, row in byyr.items():
            if years is not None and y not in years:
                continue
            if be.ip_to_float(row.get("IP")) < min_ip:
                continue
            if pc.role_of(row.get("G"), row.get("GS"), row.get("IP")) == "SWING":
                out.append((int(pid), int(y)))
    return sorted(out)


def recover_events(by_pid: dict, history_years: list, legacy_events: list,
                   apps_of=appearances, log=print) -> list:
    """Recover mid-year + swing-bridge conversions from MLB game logs as TAGGED
    events (recovered: 'mid_year' | 'swing_bridge'). detect_conversions output
    is never modified; callers concatenate.

    Pre-registered conventions (set before any results were computed):
      MID-YEAR (inside SWING season b): strict detect_midyear_switch fires AND
        the most recent prior >= CONV_MIN_IP season within 2 years has a CLEAN
        role equal to the switch's old role (an established RP moved into the
        rotation, or the mirror). Event year = b; pre = that prior season's
        line (the fit is scored there, pre-decision, exactly like legacy
        events); post = season b's line; war_delta reads bWAR(b) - bWAR(pre);
        held reads season b+1 (closed, >= CONV_MIN_IP, role == new role).
      SWING-BRIDGE (SWING season a -> clean season b, b - a <= 2): season a's
        game-log terminal_role is a clean SP/RP that differs from season b's
        role. Event year = b; pre = season a line; fit scored at a; war_delta
        = bWAR(b) - bWAR(a); held reads b+1. (Burnes 2019 SWING terminal-RP ->
        2021 SP is the motivating case.)
      DE-DUP: one event per (mlbam, direction) per overlapping window; a
        mid-year event wins over a bridge event that spans it; anything already
        in the legacy set (mlbam, year) is skipped.
    """
    seen = {(e["mlbam"], e["year"]) for e in legacy_events}
    years = set(history_years)
    swings = swing_seasons(by_pid, years=years)
    log(f"pal-gamelogs: {len(swings)} SWING pitcher-seasons (IP>={pc.CONV_MIN_IP}) to walk")
    apps_cache: dict = {}

    def _apps(pid, y):
        if (pid, y) not in apps_cache:
            apps_cache[(pid, y)] = apps_of(pid, y)
        return apps_cache[(pid, y)]

    out = []
    # ---- mid-year events ----------------------------------------------------
    for pid, y in swings:
        byyr = by_pid[pid]
        sw = detect_midyear_switch(_apps(pid, y))
        if not sw:
            continue
        old_role, new_role = sw["direction"].split("->")
        # anchor: most recent prior clean season in the OLD role
        anchor = None
        for py in sorted((p for p in byyr if p < y and p in years), reverse=True):
            if y - py > 2:
                break
            if be.ip_to_float(byyr[py].get("IP")) < pc.CONV_MIN_IP:
                continue
            r = pc.role_of(byyr[py].get("G"), byyr[py].get("GS"), byyr[py].get("IP"))
            if r in ("SP", "RP"):
                anchor = (py, r)
                break
        if not anchor or anchor[1] != old_role:
            continue
        py = anchor[0]
        if (pid, y) in seen:
            continue
        held = _held(byyr, y, new_role, years)
        out.append({
            "mlbam": pid, "name": byyr[y].get("name", ""), "team": byyr[y].get("team", ""),
            "direction": sw["direction"], "year": y,
            "pre": pc._role_line(byyr[py]), "post": pc._role_line(byyr[y]),
            "held": held, "recovered": "mid_year",
            "switch": {"t": sw["t"], "pre_seg": sw["pre"], "post_seg": sw["post"]},
        })
        seen.add((pid, y))

    # ---- swing-bridge events -------------------------------------------------
    for pid, a in swings:
        byyr = by_pid[pid]
        term = terminal_role(_apps(pid, a))
        if term not in ("SP", "RP"):
            continue
        for b in sorted(y for y in byyr if a < y <= a + 2 and y in years):
            if be.ip_to_float(byyr[b].get("IP")) < pc.CONV_MIN_IP:
                continue
            rb = pc.role_of(byyr[b].get("G"), byyr[b].get("GS"), byyr[b].get("IP"))
            if rb not in ("SP", "RP") or rb == term:
                continue
            direction = f"{term}->{rb}"
            if (pid, b) in seen:
                break
            # a mid-year event for the same player+direction whose year falls in
            # [a, b] wins over the bridge read
            if any(e["mlbam"] == pid and e["direction"] == direction
                   and a <= e["year"] <= b for e in out):
                break
            held = _held(byyr, b, rb, years)
            out.append({
                "mlbam": pid, "name": byyr[b].get("name", ""), "team": byyr[b].get("team", ""),
                "direction": direction, "year": b,
                "pre": pc._role_line(byyr[a]), "post": pc._role_line(byyr[b]),
                "held": held, "recovered": "swing_bridge",
                "bridge": {"swing_season": a, "terminal_role": term},
            })
            seen.add((pid, b))
            break
    return out


def _held(byyr: dict, b: int, new_role: str, years: set):
    last_closed = date.today().year - 1
    nxt = b + 1
    if nxt > last_closed or nxt not in byyr or nxt not in years:
        return None
    row = byyr[nxt]
    if be.ip_to_float(row.get("IP")) < pc.CONV_MIN_IP:
        return None
    rn = pc.role_of(row.get("G"), row.get("GS"), row.get("IP"))
    return (rn == new_role) if rn else None
