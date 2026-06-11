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
             date (level/age matching uses current rosters — the flag
             trail only began 2026-06, so every cohort is contemporary),
             scored over the SAME window with the SAME rule.
  METRIC     hit rate with Wilson 95% CIs, flag vs control.
  KILL RULE  a flag type whose hit-rate CI fails to clear its control
             after 2 matured monthly cohorts -> verdict 'deprecated'
             (hidden or retuned — owner decision, registry records it).

HONESTY GUARD: the artifact (data/editorial_eval.json) is only written
once at least one cohort has matured. Until then this module logs the
pending count and writes NOTHING — the registry row for
spotlights_movement stays `unvalidated` (an empty artifact would let it
masquerade as measured; the registry honesty tests forbid exactly that).

Wired into run_monthly after the registry freshness pass.
Run: python editorial_eval.py
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

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


def run(persist: bool = True) -> dict:
    flags = storage.load_editorial_flags()
    today = date.today()
    matured = [f for f in flags
               if (today - date.fromisoformat(f["emitted_at"])).days >= HORIZONS[0]]
    pending = len(flags) - len(matured)
    if not matured:
        log.info("editorial_eval: %d flags logged, NONE matured yet "
                 "(first window closes %s) — artifact not written",
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
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return {**out, "written": True}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    if not rep.get("written"):
        print(f"no matured cohorts yet ({rep['pending']} pending) — "
              "artifact withheld (registry honesty)")
    else:
        print(json.dumps({k: rep[k] for k in
                          ("flags_matured", "by_flag_type")}, indent=1))
