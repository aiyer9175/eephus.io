# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Editorial forward-validation (model-audit Phase 5, WS-10).

Spotlight/movement flags make an implicit predictive claim ("this
movement persists"). WS-0c started logging every emitted flag with
matched-control sampling keys (fv_band x level x age_band) precisely so
that claim could be scored. This module does the scoring, monthly:

  COHORT     every (player, flag_type, emitted_at) row in
             editorial_flags whose 30-day (and 60-day) window has
             closed ("matured").
  HIT        config-defined per flag type (HIT_RULES): the player's
             consensus FV at horizon is >= emit FV + fv_delta, OR the
             player newly enters a source top-100, OR >= 1 NEW source
             publishes an FV on them (multi-source pickup). Fallers
             invert the FV leg (a faller "hits" when the FV drops).
  CONTROL    unflagged players sharing the flag's fv_band at the emit
             date (level/age matching uses current rosters; the flag
             trail only began 2026-06, so every cohort is contemporary),
             scored over the SAME window with the SAME rule.
  METRIC     hit rate with Wilson 95% CIs, flag vs control.
  KILL RULE  a flag type whose hit-rate CI fails to clear its control
             after 2 matured monthly cohorts -> verdict 'deprecated'
             (hidden or retuned: owner decision, registry records it).

HONESTY GUARD: the artifact (data/editorial_eval.json) is only written
once at least one cohort has matured. Until then this module logs the
pending count and writes NOTHING; the registry row for
spotlights_movement stays `unvalidated` (an empty artifact would let it
masquerade as measured; the registry honesty tests forbid exactly that).

VERSIONS. The description above is v1, the template the GRPO forward gate
froze. v2 (registered 2026-10-01, see the block above run()) re-scores the
same flags on one point-in-time basis with random matched controls,
monthly cohorts and player-clustered intervals; the artifact carries both
blocks plus a before/after table, and the served verdicts read v2.

Wired into run_monthly after the registry freshness pass.
Run: python editorial_eval.py
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import random
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

import storage

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "editorial_eval.json"

HORIZONS = (30, 60)
# per-flag-type hit definitions (the plan: FV upgrade / top-100 entry /
# multi-source pickup, config-defined). fv_delta is on the 20-80 scale.
HIT_RULES = {
    "riser":   {"fv_delta": +5.0, "direction": +1},
    "rebound": {"fv_delta": +5.0, "direction": +1},
    "faller":  {"fv_delta": -5.0, "direction": -1},
}
MIN_COHORTS_FOR_KILL = 2


def _wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(p, 4), round(max(0.0, center - half), 4),
            round(min(1.0, center + half), 4))


def _consensus_fv_asof(con, player_key: str, asof: str) -> tuple[float | None, int]:
    """(median of each source's latest FV <= asof, n_sources)."""
    rows = con.execute(
        """SELECT source, fv FROM snapshots s
           WHERE player_key = ? AND fv IS NOT NULL AND snapshot_date <= ?
             AND snapshot_date = (SELECT MAX(snapshot_date) FROM snapshots
                                  WHERE player_key = s.player_key
                                    AND source = s.source
                                    AND fv IS NOT NULL
                                    AND snapshot_date <= ?)""",
        (player_key, asof, asof)).fetchall()
    vals = [float(r["fv"]) for r in rows]
    return (statistics.median(vals) if vals else None), len(vals)


def _top100_entry(con, player_key: str, start: str, end: str) -> bool:
    """Newly ranked <= 100 by any source inside the window, having had
    no such rank before the window."""
    pre = con.execute(
        "SELECT 1 FROM snapshots WHERE player_key=? AND rank IS NOT NULL "
        "AND rank <= 100 AND snapshot_date < ? LIMIT 1",
        (player_key, start)).fetchone()
    if pre:
        return False
    post = con.execute(
        "SELECT 1 FROM snapshots WHERE player_key=? AND rank IS NOT NULL "
        "AND rank <= 100 AND snapshot_date >= ? AND snapshot_date <= ? LIMIT 1",
        (player_key, start, end)).fetchone()
    return bool(post)


def _is_hit(con, player_key: str, flag_type: str, emitted_at: str,
            horizon_days: int, emit_fv: float | None) -> bool | None:
    """None = unscoreable (no FV on either end)."""
    rule = HIT_RULES.get(flag_type)
    if rule is None:
        return None
    end = (date.fromisoformat(emitted_at) +
           timedelta(days=horizon_days)).isoformat()
    fv_now, n_now = _consensus_fv_asof(con, player_key, end)
    base_fv = emit_fv
    if base_fv is None:
        base_fv, _ = _consensus_fv_asof(con, player_key, emitted_at)
    if fv_now is not None and base_fv is not None:
        delta = fv_now - base_fv
        if rule["direction"] > 0 and delta >= rule["fv_delta"]:
            return True
        if rule["direction"] < 0 and delta <= rule["fv_delta"]:
            return True
    if rule["direction"] > 0:
        if _top100_entry(con, player_key, emitted_at, end):
            return True
        _, n_then = _consensus_fv_asof(con, player_key, emitted_at)
        if n_now > n_then:               # multi-source pickup
            return True
    if fv_now is None and base_fv is None:
        return None
    return False


def _controls(con, fv_band: str | None, emitted_at: str,
              flagged_keys: set[str], cap: int = 200) -> list[str]:
    """Unflagged players sharing the fv_band near the emit date."""
    if not fv_band:
        return []
    lo, hi = {"<45": (0, 44.99), "45": (45, 49.99), "50": (50, 54.99),
              "55": (55, 59.99), "60+": (60, 99)}.get(fv_band, (0, 99))
    start = (date.fromisoformat(emitted_at) - timedelta(days=15)).isoformat()
    rows = con.execute(
        """SELECT DISTINCT player_key FROM snapshots
           WHERE fv >= ? AND fv <= ? AND snapshot_date BETWEEN ? AND ?
           ORDER BY player_key LIMIT ?""",
        (lo, hi, start, emitted_at, cap * 3)).fetchall()
    out = [r["player_key"] for r in rows if r["player_key"] not in flagged_keys]
    return out[:cap]


# ===========================================================================
# v2, registered 2026-10-01 beside v1 (census M02-04 and X01-10; owner answer
# 2026-09-25, batch 4). v1 above stays exactly as written: the GRPO forward
# gate (docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md) froze its design on the v1
# template, so HIT_RULES, _is_hit, _controls and the v1 block of the artifact
# do not change. v2 is what the Spotlights receipt and the registry card read.
#
# What v2 repairs, one line per audit finding:
#   ONE BASIS  v1 scores a flag from the FV stored at emit and a control from
#              the median of the sources' latest snapshots, and the snapshots
#              table is not point-in-time (an upsert can rewrite its date). v2
#              scores both legs from metric_snapshots, the board's consensus
#              FV written on the night of each run. Base = the board row on
#              the emit date (or the latest board night at most
#              V2_BASE_LOOKBACK_DAYS earlier); end = the board row on the first
#              board night on or after emit + horizon. A player with no board
#              row at either end is unscoreable and leaves numerator and
#              denominator (the GRPO gate's rule). The hit is the FV leg of
#              HIT_RULES; the top-100 and new-source legs read the snapshots
#              table, which the board history does not carry.
#   CONTROLS   v1 took the first five unflagged players by key and excluded
#              every key ever flagged (a look-ahead). v2 draws
#              V2_CONTROLS_PER_FLAG players at random, seeded per flag, from
#              the board players in the flag's own cell (fv_band x level x
#              age_band, each as of the base night) and excludes only players
#              flagged, of any type, on the same date.
#   COHORTS    v1 counts every emit date as a cohort; v2 counts calendar
#              months, so the kill rule waits for two matured months.
#   CIs        a riser is re-flagged night after night, so flag rows are not
#              independent. v2 bootstraps by player (flags clustered by the
#              flagged player, controls by the control player) and reads the
#              verdict off the interval of the gap between the two rates.
# ===========================================================================

V2_VERSION = "v2"
V2_REGISTERED = "2026-10-01"
V2_SEED = 20260925
V2_CONTROLS_PER_FLAG = 5
V2_BASE_LOOKBACK_DAYS = 3
V2_BOOT_REPS = 2000
V2_LEVEL_ORDER = ("DSL", "CPX", "A", "A+", "AA", "AAA", "MLB")


def _board_history(con) -> tuple[list[str], dict[str, dict[str, tuple]]]:
    """Board nights, sorted, and {night: {player_key: (consensus_fv, age)}}
    from metric_snapshots, the point-in-time board written on each run."""
    nights: dict[str, dict[str, tuple]] = {}
    for r in con.execute(
            "SELECT snapshot_date, player_key, consensus_fv, age "
            "FROM metric_snapshots WHERE consensus_fv IS NOT NULL"):
        nights.setdefault(r[0], {})[r[1]] = (float(r[2]), r[3])
    return sorted(nights), nights


def _base_night(nights: list[str], emitted_at: str) -> str | None:
    """The latest board night on or before the emit date, inside the
    lookback; None when the board was not written close enough to it."""
    i = bisect.bisect_right(nights, emitted_at) - 1
    if i < 0:
        return None
    gap = (date.fromisoformat(emitted_at) - date.fromisoformat(nights[i])).days
    return nights[i] if gap <= V2_BASE_LOOKBACK_DAYS else None


def _end_night(nights: list[str], emitted_at: str, horizon_days: int) -> str | None:
    """The first board night on or after emit + horizon (the GRPO gate's
    maturity rule); None while the window has not closed."""
    target = (date.fromisoformat(emitted_at) + timedelta(days=horizon_days)).isoformat()
    i = bisect.bisect_left(nights, target)
    return nights[i] if i < len(nights) else None


def load_level_history(data_dir: Path | None = None) -> dict[str, tuple[list, str | None]]:
    """{player_key: (level_changes, statline level)} from the served board and
    inactive payloads. level_changes is stats.derive_level_changes output,
    resolved against point-in-time team affiliations; reading it from disk
    keeps the eval off the network. A missing file leaves its players
    without a level, so they cannot be matched (reported, never guessed)."""
    data_dir = data_dir or DATA_DIR
    out: dict[str, tuple[list, str | None]] = {}
    for name, key in (("timeseries.json", "players"), ("inactive.json", None)):
        try:
            doc = json.loads((data_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("editorial_eval v2: %s unreadable, its players have no level", name)
            continue
        rows = doc.get(key) if (key and isinstance(doc, dict)) else doc
        for r in rows or []:
            k = r.get("player_key") if isinstance(r, dict) else None
            if k and k not in out:
                out[k] = (list(r.get("level_changes") or []),
                          r.get("statline_level") or r.get("current_level"))
    return out


def _level_asof(entry: tuple[list, str | None] | None, asof: str) -> str | None:
    """The level a player held on `asof`: the destination of his last level
    change on or before it, else the origin of his first later change, else
    (he never changed level) his statline level."""
    if entry is None:
        return None
    changes, current = entry
    ch = sorted((c for c in changes if c.get("date")), key=lambda c: c["date"])
    prior = [c for c in ch if c["date"] <= asof]
    if prior:
        return prior[-1].get("to_level")
    if ch:
        return ch[0].get("from_level")
    return current


def _v2_cell(fv: float | None, age: float | None, level: str | None) -> tuple | None:
    fv_band, age_band = storage._editorial_band(fv, age)
    if fv_band is None or age_band is None or not level:
        return None
    return (fv_band, level, age_band)


def _v2_hit(flag_type: str, fv_base: float, fv_end: float) -> bool:
    rule = HIT_RULES[flag_type]
    delta = fv_end - fv_base
    return delta >= rule["fv_delta"] if rule["direction"] > 0 else delta <= rule["fv_delta"]


def _draw_controls(pool: list[str], flag_type: str, emitted_at: str,
                   player_key: str, k: int = V2_CONTROLS_PER_FLAG) -> list[str]:
    """k players drawn at random from the flag's cell pool. The seed is a
    string of (V2_SEED, type, date, player), so a draw never depends on how
    many other flags exist or on the order they are scored in."""
    rng = random.Random(f"{V2_SEED}|{flag_type}|{emitted_at}|{player_key}")
    pool = sorted(pool)
    return rng.sample(pool, min(k, len(pool)))


def _cluster_draws(by_player: dict[str, list[int]], rng) -> "np.ndarray":
    """Bootstrap rates with players resampled whole (hits and rows travel
    together), V2_BOOT_REPS draws."""
    keys = sorted(by_player)
    hits = np.array([by_player[p][0] for p in keys], dtype=float)
    rows = np.array([by_player[p][1] for p in keys], dtype=float)
    idx = rng.integers(0, len(keys), size=(V2_BOOT_REPS, len(keys)))
    return hits[idx].sum(axis=1) / np.maximum(rows[idx].sum(axis=1), 1.0)


def _v2_verdict(lo: float, hi: float) -> str:
    return "clears" if lo > 0 else ("trails" if hi < 0 else "inside")


def run_v2(con, flags: list[dict], level_history: dict | None = None) -> dict:
    """The v2 block of data/editorial_eval.json (see the header above)."""
    if level_history is None:
        level_history = load_level_history()
    nights, board = _board_history(con)
    same_date: dict[str, set[str]] = {}
    for f in flags:
        same_date.setdefault(f["emitted_at"], set()).add(f["player_key"])

    pools: dict[tuple[str, tuple], list[str]] = {}
    pooled_nights: set[str] = set()

    def _pool(night: str, cell: tuple, excluded: set[str]) -> list[str]:
        if night not in pooled_nights:
            pooled_nights.add(night)
            for pk, (fv, age) in board[night].items():
                c = _v2_cell(fv, age, _level_asof(level_history.get(pk), night))
                if c is not None:
                    pools.setdefault((night, c), []).append(pk)
        return [p for p in pools.get((night, cell), []) if p not in excluded]

    level_agree = level_n = fv_far = fv_n = 0
    by_type: dict[str, dict] = {}
    for t_i, ftype in enumerate(sorted({f["flag_type"] for f in flags})):
        if ftype not in HIT_RULES:
            continue
        mine = [f for f in flags if f["flag_type"] == ftype]
        counts = {"flags": len(mine), "no_board_row_at_emit": 0,
                  "no_cell": 0, "empty_pool": 0}
        matched = []                 # (flag, base night, base fv, controls)
        for f in mine:
            night = _base_night(nights, f["emitted_at"])
            row = board[night].get(f["player_key"]) if night else None
            if row is None:
                counts["no_board_row_at_emit"] += 1
                continue
            lvl = _level_asof(level_history.get(f["player_key"]), night) or f.get("level")
            if f.get("level"):
                level_n += 1
                level_agree += int(lvl == f.get("level"))
            if f.get("fv") is not None:
                fv_n += 1
                fv_far += int(abs(row[0] - float(f["fv"])) > 1.0)
            cell = _v2_cell(row[0], row[1], lvl)
            if cell is None:
                counts["no_cell"] += 1
                continue
            pool = _pool(night, cell, same_date.get(f["emitted_at"], set()))
            if not pool:
                counts["empty_pool"] += 1
                continue
            ctrls = _draw_controls(pool, ftype, f["emitted_at"], f["player_key"])
            matched.append((f, night, row[0], ctrls, len(pool)))
        counts["matched"] = len(matched)
        pool_sizes = sorted(m[4] for m in matched)

        horizons: dict[str, dict] = {}
        months_h: dict[str, set[str]] = {}
        for h in HORIZONS:
            f_rows: dict[str, list[int]] = {}
            c_rows: dict[str, list[int]] = {}
            month: dict[str, list[int]] = {}
            n = hits = c_n = c_hits = unscoreable = 0
            for f, night, fv0, ctrls, _ in matched:
                end = _end_night(nights, f["emitted_at"], h)
                if end is None:
                    continue                                  # not matured
                fv1 = board[end].get(f["player_key"])
                if fv1 is None:
                    unscoreable += 1
                    continue
                v = int(_v2_hit(ftype, fv0, fv1[0]))
                n += 1
                hits += v
                fr = f_rows.setdefault(f["player_key"], [0, 0])
                fr[0] += v
                fr[1] += 1
                mo = month.setdefault(f["emitted_at"][:7], [0, 0, 0, 0])
                mo[0] += v
                mo[1] += 1
                for ck in ctrls:
                    c0 = board[night].get(ck)
                    c1 = board[end].get(ck)
                    if c0 is None or c1 is None:
                        continue
                    cv = int(_v2_hit(ftype, c0[0], c1[0]))
                    c_n += 1
                    c_hits += cv
                    cr = c_rows.setdefault(ck, [0, 0])
                    cr[0] += cv
                    cr[1] += 1
                    mo[2] += cv
                    mo[3] += 1
            months_h[f"h{h}"] = {m for m, v in month.items() if v[1]}
            res = {"n": n, "players": len(f_rows), "unscoreable": unscoreable,
                   "hit_rate": round(hits / n, 4) if n else None,
                   "control_n": c_n, "control_players": len(c_rows),
                   "control_rate": round(c_hits / c_n, 4) if c_n else None}
            if n and c_n:
                rng = np.random.default_rng([V2_SEED, t_i, h])
                fd = _cluster_draws(f_rows, rng)
                cd = _cluster_draws(c_rows, rng)
                gd = fd - cd
                q = lambda a: [round(float(x), 4) for x in np.percentile(a, [2.5, 97.5])]
                res["ci"] = q(fd)
                res["control_ci"] = q(cd)
                res["gap"] = round(hits / n - c_hits / c_n, 4)
                res["gap_ci"] = q(gd)
                res["gap_lo95"], res["gap_hi95"] = res["gap_ci"]
                res["verdict"] = _v2_verdict(res["gap_ci"][0], res["gap_ci"][1])
                res["clears_control"] = res["verdict"] == "clears"
                res["verdict_text"] = (
                    f"{res['verdict']}: flag {res['hit_rate']:.4f} vs matched control "
                    f"{res['control_rate']:.4f}, gap 95% CI {res['gap_lo95']:+.4f} to "
                    f"{res['gap_hi95']:+.4f} (clustered by player)")
            else:
                res.update({"ci": None, "control_ci": None, "gap": None,
                            "gap_ci": None, "gap_lo95": None, "gap_hi95": None,
                            "verdict": "unread", "clears_control": False,
                            "verdict_text": "unread: no matured flag or control"})
            res["by_month"] = {
                m: {"n": v[1], "hit_rate": round(v[0] / v[1], 4) if v[1] else None,
                    "control_n": v[3],
                    "control_rate": round(v[2] / v[3], 4) if v[3] else None}
                for m, v in sorted(month.items())}
            horizons[f"h{h}"] = res
        cohorts = sorted(months_h.get(f"h{HORIZONS[0]}", set()))
        read = [horizons[f"h{h}"] for h in HORIZONS if horizons[f"h{h}"]["n"]]
        fails = bool(read) and all(not r["clears_control"] for r in read)
        eligible = len(cohorts) >= MIN_COHORTS_FOR_KILL
        by_type[ftype] = {
            "matured_monthly_cohorts": len(cohorts),
            "cohort_months": cohorts,
            "flag_counts": counts,
            "median_pool": pool_sizes[len(pool_sizes) // 2] if pool_sizes else None,
            "horizons": horizons,
            "kill_rule": {
                "eligible": eligible,
                "fails_to_clear": fails,
                "verdict_recommendation": ("deprecated" if eligible and fails
                                           else "keep-measuring"),
            },
        }
    n_scored = {f"h{h}": sum(b["horizons"][f"h{h}"]["n"] for b in by_type.values())
                for h in HORIZONS}
    return {
        "version": V2_VERSION,
        "registered": V2_REGISTERED,
        "n_scored": n_scored,
        "board_nights": {"first": nights[0] if nights else None,
                         "last": nights[-1] if nights else None,
                         "count": len(nights)},
        "by_flag_type": by_type,
        "diagnostics": {
            "level_asof_matches_stored_flag_level": round(level_agree / level_n, 4) if level_n else None,
            "level_rows": level_n,
            "board_fv_differs_from_stored_flag_fv_by_more_than_1": round(fv_far / fv_n, 4) if fv_n else None,
            "fv_rows": fv_n,
        },
        "conventions": {
            "basis": "both legs on metric_snapshots consensus_fv: base = board row on the "
                     f"emit date (or up to {V2_BASE_LOOKBACK_DAYS} days earlier), end = first "
                     "board night on or after emit + horizon; no board row at either end = "
                     "unscoreable, out of numerator and denominator",
            "hit": "board consensus FV moves by fv_delta or more in the flag's direction "
                   "(HIT_RULES FV leg; the top-100 and new-source legs are not on the board "
                   "history)",
            "control": f"{V2_CONTROLS_PER_FLAG} board players drawn at random (seed "
                       f"{V2_SEED}, per flag) from the flag's fv_band x level x age_band "
                       "cell on the base night, excluding only players flagged on the same "
                       "date; level is the level held that night (level_changes)",
            "ci": f"95% percentile bootstrap, {V2_BOOT_REPS} draws, players resampled "
                  "whole (flags by flagged player, controls by control player); the gap "
                  "interval is flag rate minus control rate",
            "verdict": "clears = gap interval above 0, trails = below 0, inside = spans 0",
            "cohorts": "calendar months of the emit date",
            "kill_rule": f"a flag type that clears its control on no horizon after "
                         f"{MIN_COHORTS_FOR_KILL} matured monthly cohorts -> deprecated "
                         "(registry verdict, owner-committed)",
        },
    }


def before_after(v1_by_type: dict, v2: dict) -> dict:
    """Per flag type and horizon, the v1 (before) and v2 (after) reads side by
    side, copied from the two blocks of the same run."""
    out: dict[str, dict] = {}
    for ftype, b in sorted(v2.get("by_flag_type", {}).items()):
        a = v1_by_type.get(ftype, {})
        row: dict[str, dict] = {}
        for h in HORIZONS:
            hb = (a.get("horizons") or {}).get(f"h{h}") or {}
            ha = (b.get("horizons") or {}).get(f"h{h}") or {}
            row[f"h{h}"] = {
                "before": {"n": hb.get("n"), "hit_rate": hb.get("hit_rate"),
                           "control_rate": hb.get("control_rate"),
                           "clears_control": hb.get("clears_control")},
                "after": {"n": ha.get("n"), "hit_rate": ha.get("hit_rate"),
                          "control_rate": ha.get("control_rate"),
                          "gap_ci": ha.get("gap_ci"), "verdict": ha.get("verdict"),
                          "clears_control": ha.get("clears_control")},
            }
        row["kill_rule"] = {
            "before": (a.get("kill_rule") or {}).get("verdict_recommendation"),
            "after": (b.get("kill_rule") or {}).get("verdict_recommendation"),
        }
        out[ftype] = row
    return out


def run(persist: bool = True, level_history: dict | None = None) -> dict:
    flags = storage.load_editorial_flags()
    today = date.today()
    matured = [f for f in flags
               if (today - date.fromisoformat(f["emitted_at"])).days >= HORIZONS[0]]
    pending = len(flags) - len(matured)
    if not matured:
        log.info("editorial_eval: %d flags logged, NONE matured yet "
                 "(first window closes %s); artifact not written",
                 len(flags),
                 (date.fromisoformat(min(f["emitted_at"] for f in flags))
                  + timedelta(days=HORIZONS[0])).isoformat() if flags else "n/a")
        return {"matured": 0, "pending": pending, "written": False}

    flagged_keys = {f["player_key"] for f in flags}
    by_type: dict[str, dict] = {}
    with storage.connect() as con:
        for ftype in sorted({f["flag_type"] for f in matured}):
            mine = [f for f in matured if f["flag_type"] == ftype]
            cohorts = sorted({f["emitted_at"] for f in mine})
            res: dict[str, dict] = {}
            for h in HORIZONS:
                ready = [f for f in mine
                         if (today - date.fromisoformat(f["emitted_at"])).days >= h]
                hits = n = 0
                c_hits = c_n = 0
                for f in ready:
                    v = _is_hit(con, f["player_key"], ftype, f["emitted_at"],
                                h, f.get("fv"))
                    if v is None:
                        continue
                    n += 1
                    hits += int(v)
                    for ck in _controls(con, f.get("fv_band"), f["emitted_at"],
                                        flagged_keys, cap=5):
                        cv = _is_hit(con, ck, ftype, f["emitted_at"], h, None)
                        if cv is None:
                            continue
                        c_n += 1
                        c_hits += int(cv)
                p, lo, hi = _wilson(hits, n)
                cp, clo, chi = _wilson(c_hits, c_n)
                res[f"h{h}"] = {"n": n, "hit_rate": p, "ci": [lo, hi],
                                "control_n": c_n, "control_rate": cp,
                                "control_ci": [clo, chi],
                                "clears_control": bool(n and c_n and lo > cp)}
            fails = all(not res[f"h{h}"]["clears_control"] for h in HORIZONS
                        if res.get(f"h{h}", {}).get("n"))
            by_type[ftype] = {
                "matured_cohorts": len(cohorts),
                "horizons": res,
                "kill_rule": {
                    "eligible": len(cohorts) >= MIN_COHORTS_FOR_KILL,
                    "fails_to_clear": fails,
                    "verdict_recommendation": (
                        "deprecated" if len(cohorts) >= MIN_COHORTS_FOR_KILL
                        and fails else "keep-measuring"),
                },
            }
    out = {
        "generated_at": today.isoformat(),
        "hit_rules": HIT_RULES,
        "horizons_days": list(HORIZONS),
        "flags_logged": len(flags),
        "flags_matured": len(matured),
        "flags_pending": pending,
        "by_flag_type": by_type,
        "conventions": {
            "hit": "consensus FV moves >= fv_delta by the horizon, OR new "
                   "top-100 entry, OR a new source publishes an FV "
                   "(fallers invert the FV leg)",
            "control": "unflagged players in the flag's fv_band with a "
                       "snapshot within 15 days pre-emit, same rule + window",
            "kill_rule": f"flag type failing to clear control after "
                         f"{MIN_COHORTS_FOR_KILL} matured cohorts -> "
                         "deprecated (registry verdict, owner-committed)",
        },
    }
    # v2 beside v1 (registered 2026-10-01): same flags, one basis. The v1
    # keys above keep their shape; the served receipt reads the v2 block.
    with storage.connect() as con:
        v2 = run_v2(con, [f for f in flags if f["emitted_at"] <= today.isoformat()],
                    level_history)
    out["served_version"] = V2_VERSION
    out["v2"] = v2
    out["before_after"] = before_after(by_type, v2)
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return {**out, "written": True}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    if not rep.get("written"):
        print(f"no matured cohorts yet ({rep['pending']} pending); "
              "artifact withheld (registry honesty)")
    else:
        print(json.dumps({k: rep[k] for k in
                          ("flags_matured", "before_after")}, indent=1))
