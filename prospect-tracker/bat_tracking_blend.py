# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""BT Blend (btblend_plus): the SERVED construction of the bat-tracking blend,
arm B of tools/bat_tracking_lab.py, registered in docs/BAT_TRACKING_SERVED_GATE.md
(2026-10-14) before any served-construction number existed.

    blend = 0.595 z(est_woba) + 0.255 z(hem_plus_raw) + 0.15 z(BT composite)

1. BT composite: each component (bat speed, squared-up rate, blast rate) is
   z-scored over the season's FULL bat-tracking leaderboard at >= 100
   competitive swings with the population sd, and the composite is the mean of
   the three z. This is the lab's own component normalizer (zmap over load_bt):
   the pool never depends on which hitters the board shows.
2. Board floor: a row is stamped only with Savant PA >= 100, a HEM core, and a
   bat-tracking row at >= 100 competitive swings. A missing leg leaves the field
   absent; nothing is imputed.
3. Blend legs: z over the joined served pool J(Y) with the sample sd (the
   fwdHEM+ convention), the 0.595 / 0.255 / 0.15 blend re-standardized by its own
   sd over J(Y) and mapped onto J(Y)'s HEM+ core location and spread, rounded to
   an integer on the HEM+ ruler.

Every weight, floor and component is FIXED by the gate document; a change is a
new registration. Pure functions here; hitter_export owns the flag
(BTBLEND_SERVE, default off) and the only call sites. Stdlib only.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
SERVED_CACHE_DIR = ROOT / ".cache" / "bat_tracking" / "served"
PREVIEW_DIR = ROOT / ".cache" / "bat_tracking" / "preview"

# The lab's endpoint, unchanged (tools/bat_tracking_lab.BT_URL).
BT_URL = ("https://baseballsavant.mlb.com/leaderboard/bat-tracking"
          "?seasonStart={y}&seasonEnd={y}&gameType=Regular&minSwings=25&type=batter")
LIVE_TTL_S = 24 * 3600          # mlb_player_export._SAVANT_LIVE_TTL_S
FETCH_TIMEOUT_S = 90

# Fixed by the gate document (section 1 rule 3).
W_XWOBA, W_HEM, W_BT = 0.595, 0.255, 0.15
MIN_PA = 100.0                  # Savant PA floor on the board (the xHEM+ Blend floor)
MIN_SWINGS = 100.0              # competitive swings (tools/bat_tracking_lab.BT_MIN_SWINGS)
COMPONENTS = ("avg_sweetspot_speed_mph_qualified",   # bat speed
              "squared_up_per_swing",                # squared-up rate
              "squared_up_with_speed_per_swing")     # blast rate
# load_bt keeps a row only when every mapped field parses; the population the
# components are z-scored over must be that same population.
REQUIRED_FIELDS = ("avg_sweetspot_speed_mph_qualified", "swing_length_qualified",
                   "attack_angle", "attack_direction_pullopp",
                   "avg_plane_vertical_angle", "rate_ideal_attack_angle",
                   "squared_up_per_swing", "squared_up_with_speed_per_swing")


# --------------------------------------------------------------------------- #
# fetch (served cache, never the lab's frozen captures)
# --------------------------------------------------------------------------- #
def extract_embedded_data(html: str):
    """The page's embedded `const data = [...]` array (the csv export omits
    fields), or None."""
    m = re.search(r"const data = (\[)", html)
    if not m:
        return None
    i = m.start(1)
    depth, in_str, esc = 0, False, False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(html[i:j + 1])
    return None


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_leaderboard(season: int, *, cache_dir: Optional[Path] = None,
                      getter: Optional[Callable[[str], str]] = None,
                      now: Optional[float] = None,
                      today: Optional[date] = None) -> list[dict]:
    """Raw bat-tracking batter rows for `season`. Closed seasons cache forever;
    the current season refreshes after LIVE_TTL_S. A failed refresh falls back
    to the stale file; no file means [] (no column)."""
    cache = Path(cache_dir or SERVED_CACHE_DIR)
    path = cache / f"bat_tracking_batter_{int(season)}.json"
    today = today or date.today()
    now = time.time() if now is None else now
    stale = False
    if path.exists() and int(season) >= today.year:
        try:
            stale = (now - path.stat().st_mtime) > LIVE_TTL_S
        except OSError:
            stale = False
    if not path.exists() or stale:
        try:
            rows = extract_embedded_data((getter or _http_get)(BT_URL.format(y=int(season))))
            if rows is None:
                raise ValueError("bat-tracking embedded data not found")
            cache.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rows), encoding="utf-8")
            tmp.replace(path)
        except Exception:   # noqa: BLE001 - best-effort; the stale file or nothing
            if not path.exists():
                return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


# --------------------------------------------------------------------------- #
# the construction
# --------------------------------------------------------------------------- #
def _pop_mu_sd(vals: list[float]) -> tuple[float, float]:
    """Population mean and sd (numpy's np.mean / np.std defaults, the lab's
    zmap); an sd of 0 reads as 1 there, kept here."""
    k = len(vals)
    mu = math.fsum(vals) / k
    sd = math.sqrt(math.fsum((v - mu) ** 2 for v in vals) / k)
    return mu, (sd or 1.0)


def _sample_mu_sd(vals: list[float]) -> tuple[float, float]:
    """hitter_export._join_fwdhem_plus._mu_sd: sample sd."""
    k = len(vals)
    mu = sum(vals) / k
    sd = (sum((v - mu) ** 2 for v in vals) / (k - 1)) ** 0.5
    return mu, sd


def composite_map(rows: list[dict], min_swings: float = MIN_SWINGS) -> dict[int, float]:
    """{mlbam: BT composite} over the leaderboard rows at >= min_swings
    competitive swings with every required field present."""
    pop: dict[int, dict] = {}
    for r in rows or []:
        try:
            mid = int(r["id"])
            swings = float(r["swings_qualified"])
        except (KeyError, TypeError, ValueError):
            continue
        if swings < min_swings:
            continue
        rec = {}
        try:
            for f in REQUIRED_FIELDS:
                rec[f] = float(r[f])
        except (KeyError, TypeError, ValueError):
            continue
        pop[mid] = rec
    if not pop:
        return {}
    z: dict[int, float] = {m: 0.0 for m in pop}
    for f in COMPONENTS:
        mu, sd = _pop_mu_sd([v[f] for v in pop.values()])
        for m, v in pop.items():
            z[m] += (v[f] - mu) / sd
    return {m: s / len(COMPONENTS) for m, s in z.items()}


def savant_xwoba_map(rows: list[dict], min_pa: float = MIN_PA) -> dict[int, float]:
    """{mlbam: est_woba} off the Savant expected batter leaderboard at
    PA >= min_pa and est_woba > 0 (the xHEM+ Blend gate)."""
    out: dict[int, float] = {}
    for r in rows or []:
        try:
            mid = int(r["player_id"])
            ew = float(r["est_woba"])
            pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= min_pa and ew > 0:
            out[mid] = ew
    return out


def blend_params(xw: dict, hem_raw: dict, comp: dict) -> Optional[dict]:
    """The served normalizer over J(Y): rows with all three legs."""
    pool = {m: (x, hem_raw[m], comp[m]) for m, x in xw.items()
            if hem_raw.get(m) is not None and comp.get(m) is not None}
    if len(pool) < 2:
        return None
    mu_x, sd_x = _sample_mu_sd([v[0] for v in pool.values()])
    mu_h, sd_h = _sample_mu_sd([v[1] for v in pool.values()])
    mu_c, sd_c = _sample_mu_sd([v[2] for v in pool.values()])
    if not sd_x or not sd_h or not sd_c:
        return None
    p = {"mu_x": mu_x, "sd_x": sd_x, "mu_h": mu_h, "sd_h": sd_h,
         "mu_c": mu_c, "sd_c": sd_c, "n_pool": len(pool)}
    _mu_b, sd_b = _sample_mu_sd([blend_z(x, h, c, p) for x, h, c in pool.values()])
    if not sd_b:
        return None
    p["sd_b"] = sd_b
    return p


def blend_z(x: float, h: float, c: float, p: dict) -> float:
    """The plain blend of the three J(Y) leg z (rung D1 of the gate ladder)."""
    return (W_XWOBA * (x - p["mu_x"]) / p["sd_x"]
            + W_HEM * (h - p["mu_h"]) / p["sd_h"]
            + W_BT * (c - p["mu_c"]) / p["sd_c"])


def blend_unrounded(x: float, h: float, c: float, p: dict) -> float:
    """Re-standardized and mapped onto the HEM+ ruler (rungs D2 / D3)."""
    return p["mu_h"] + p["sd_h"] * (blend_z(x, h, c, p) / p["sd_b"])


def served_values(xw: dict, hem_raw: dict, comp: dict) -> tuple[dict[int, int], Optional[dict]]:
    """({mlbam: btblend_plus integer} over J(Y), the normalizer)."""
    p = blend_params(xw, hem_raw, comp)
    if p is None:
        return {}, None
    out = {}
    for m, x in xw.items():
        h, c = hem_raw.get(m), comp.get(m)
        if h is None or c is None:
            continue
        out[m] = int(round(blend_unrounded(x, h, c, p)))
    return out, p


def stamp(hitters: list[dict], values: dict[int, int]) -> int:
    """Stamp btblend_plus onto the board rows that are in J(Y)."""
    n = 0
    for h in hitters:
        v = values.get(int(h["mlbam"])) if h.get("mlbam") is not None else None
        if v is None:
            continue
        h["btblend_plus"] = v
        n += 1
    return n
