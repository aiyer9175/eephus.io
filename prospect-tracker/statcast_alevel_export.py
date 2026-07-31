# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""S-XLINE-4 overlay signal bake: data/statcast_alevel_signals.json.

Offline exporter for the bounded A/CPX live overlay (efv_statcast_overlay,
registered in docs/efv-2026-07-23/GATES.md, section "S-XLINE-4 gate
registration"). Bakes the two INC-passing signals for CURRENT-season A + CPX
players from data the pipeline has ALREADY harvested - zero fetches:

  hitters : whiff share (WHIFF/SWING call codes) from the stored zone_metrics
            payloads (>= 100 pitches seen, the zone_metrics qualification the
            S-XLINE-3/4 lab used), plus the same player's current K% from the
            cached milb_history level row (>= 150 PA, the lab exposure floor)
  pitchers: avg fastball velo (codes FF/FA/FT/SI) from the stored
            statcast_metrics pitch_movement summaries (>= 50 tracked FB, the
            lab AUX-3 floor), plus current K%-against (>= 150 BF)

Both legs are z-scored WITHIN the signal-qualified (level, season, side)
pool (>= 20 members, the lab hygiene floor) so the overlay's residual is a
like-for-like reconstruction of the lab construction.

FROZEN residual coefficients: whiff_z ~ k_z (hitters) and velo_z ~ k_a_z
(pitchers), fit ONCE (2026-07-23) on the lab's 2023-2025 A-ball pair data -
the exact populations the S-XLINE-4 INC arms used (hit n=788 = the INC-2
rows; pit n=227 = the INC-3 rows; z pools identical to this exporter's
serve-time construction). The constants below are that fit, pasted verbatim;
this module contains NO fitting code, so the coefficients can never silently
refit at serve time (test_statcast_overlay pins run() re-emitting them
verbatim). Provenance: session fit script over the S-XLINE-3 backfill
accumulators via tools/efv_statcast_line2_lab.py helpers.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "statcast_alevel_signals.json"

LEVELS = ("A", "CPX")
MIN_PA = 150            # lab hitter exposure floor (both legs of the pair data)
MIN_BF = 150            # lab pitcher exposure floor
MIN_PITCHES_SEEN = 100  # zone_metrics qualification (lab AUX-2 / INC-2)
MIN_FB = 50             # lab tracked-fastball floor (AUX-3 / INC-3)
MIN_POOL_N = 20         # lab z-pool hygiene floor
FB_CODES = {"FF", "FA", "FT", "SI"}

# FROZEN 2026-07-23 (see module docstring). NEVER refit at serve time.
FROZEN_COEFFICIENTS = {
    "hit_whiff_on_k": {"slope": 0.887083, "intercept": 0.013667, "n": 788,
                       "resid_sd": 0.471241, "r": 0.8717},
    "pit_velo_on_ka": {"slope": 0.218195, "intercept": -0.009135, "n": 227,
                       "resid_sd": 0.967167, "r": 0.2194},
    "fit": "OLS signal_z ~ current-K z, A-ball 2023-2025, the exact S-XLINE-4 "
           "INC pair populations (lab accumulators + milb_history lines); "
           "z within the signal-qualified (A, season) pool, mirroring run()",
    "frozen": "2026-07-23 - pasted constants, no fitting code in this module; "
              "serve time NEVER refits",
    "beta_fv_per_residual_z": 0.6,   # a-priori overlay slope (efv_statcast_overlay)
    "delta_cap_fv": 2.0,             # registered ceiling (S-XLINE-4 ship rule)
}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _season_z(values: dict[int, float]) -> dict[int, float]:
    """z within one (level, season, side) pool; {} when the pool is too small
    or degenerate (mirrors the lab's _season_z)."""
    if len(values) < MIN_POOL_N:
        return {}
    vals = list(values.values())
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / len(vals)
    if var <= 0:
        return {}
    sd = var ** 0.5
    return {k: (v - m) / sd for k, v in values.items()}


def _zone_splits(season: int) -> dict[int, dict]:
    """{mlbam: best qualified A/CPX hitter zone split} from the stored
    zone_metrics payloads (level_splits include the primary row, so dedupe on
    (mlbam, level) keeping the max-pitches split, then keep the max-pitches
    level per player)."""
    import storage
    best: dict[tuple[int, str], dict] = {}
    with storage.connect() as con:
        rows = con.execute(
            "SELECT payload_json FROM zone_metrics WHERE season = ?", (season,)
        ).fetchall()
    for r in rows:
        p = json.loads(r["payload_json"])
        splits = p.get("level_splits") or [p]
        for ls in splits:
            if ls.get("is_pitcher"):
                continue
            lv, mid = ls.get("level"), ls.get("mlbam_id")
            pitches = int(ls.get("pitches") or 0)
            whiff = _f(ls.get("whiff_pct"))
            if (lv not in LEVELS or not mid or pitches < MIN_PITCHES_SEEN
                    or whiff is None):
                continue
            key = (int(mid), lv)
            if key not in best or pitches > best[key]["n_pitches"]:
                best[key] = {"level": lv, "n_pitches": pitches,
                             "whiff_share": round(whiff / 100.0, 4)}
    out: dict[int, dict] = {}
    for (mid, _lv), e in best.items():
        if mid not in out or e["n_pitches"] > out[mid]["n_pitches"]:
            out[mid] = e
    return out


def _statcast_splits(season: int) -> dict[int, dict]:
    """{mlbam: best qualified A/CPX pitcher velo split} from the stored
    statcast_metrics payloads (count-weighted avg FB velo over FB_CODES;
    n_pitches = tracked pitches at the split)."""
    import storage
    best: dict[tuple[int, str], dict] = {}
    with storage.connect() as con:
        rows = con.execute(
            "SELECT payload_json FROM statcast_metrics WHERE season = ?", (season,)
        ).fetchall()
    for r in rows:
        p = json.loads(r["payload_json"])
        if not p.get("is_pitcher") or not p.get("mlbam_id"):
            continue
        mid = int(p["mlbam_id"])
        for ls in p.get("level_splits") or []:
            lv = ls.get("level")
            if lv not in LEVELS:
                continue
            pm = ls.get("pitch_movement") or {}
            vsum = vn = 0.0
            for s in pm.get("pitch_summary") or []:
                velo, cnt = _f(s.get("avg_velo")), int(s.get("count") or 0)
                if s.get("pitch_type") in FB_CODES and velo is not None and cnt > 0:
                    vsum += velo * cnt
                    vn += cnt
            if vn < MIN_FB:
                continue
            tracked = int(pm.get("tracked_pitches") or 0) or int(vn)
            key = (mid, lv)
            if key not in best or tracked > best[key]["n_pitches"]:
                best[key] = {"level": lv, "n_pitches": tracked,
                             "fb_velo": round(vsum / vn, 2), "fb_n": int(vn)}
    out: dict[int, dict] = {}
    for (mid, _lv), e in best.items():
        if mid not in out or e["n_pitches"] > out[mid]["n_pitches"]:
            out[mid] = e
    return out


def _k_legs(season: int, group: str, mids_by_level: dict[str, list[int]]) -> dict[int, float]:
    """{mlbam: current K% (K%-against for pitchers)} from the CACHED
    milb_history level rows (fetch=False - this exporter never fetches)."""
    import milb_history as mh
    idx = mh.player_index(season, group, fetch=False)
    out: dict[int, float] = {}
    for lv, mids in mids_by_level.items():
        for mid in mids:
            rows = idx.get(mid)
            if not rows:
                continue
            row = mh.level_row(rows, lv, group)
            if row is None:
                continue
            so = _f(row.get("so"))
            if group == "hitting":
                pa = _f(row.get("pa")) or 0.0
                if pa >= MIN_PA and so is not None:
                    out[mid] = so / pa
            else:
                bf = _f(row.get("bf")) or 0.0
                if bf >= MIN_BF and so is not None:
                    out[mid] = so / bf
    return out


def run(persist: bool = True, season: int | None = None) -> dict:
    """Bake the signal sidecar for the current season. Pool z per (level,
    side); players missing either leg (signal or qualified K line) or in an
    under-floor pool are simply absent (the overlay treats absence as
    no-op). Compare-before-write so an unchanged bake is churn-free."""
    season = season or date.today().year
    by_mlbam: dict[str, dict] = {}
    counts: dict[str, dict] = {}

    zone = _zone_splits(season)
    mids_by_level = {lv: [m for m, e in zone.items() if e["level"] == lv]
                     for lv in LEVELS}
    k_map = _k_legs(season, "hitting", mids_by_level)
    for lv in LEVELS:
        pool = {m: zone[m] for m in mids_by_level[lv] if m in k_map}
        wz = _season_z({m: e["whiff_share"] for m, e in pool.items()})
        kz = _season_z({m: k_map[m] for m in pool})
        n_baked = 0
        for m in pool:
            if m in wz and m in kz:
                by_mlbam[str(m)] = {
                    "level": lv, "season": season, "side": "hit",
                    "whiff_share": pool[m]["whiff_share"],
                    "whiff_z": round(wz[m], 4), "k_z": round(kz[m], 4),
                    "n_pitches": pool[m]["n_pitches"],
                }
                n_baked += 1
        counts[f"hit_{lv}"] = {"signal_qualified": len(mids_by_level[lv]),
                               "with_k_line": len(pool), "baked": n_baked}

    velo = _statcast_splits(season)
    pmids_by_level = {lv: [m for m, e in velo.items() if e["level"] == lv]
                      for lv in LEVELS}
    ka_map = _k_legs(season, "pitching", pmids_by_level)
    for lv in LEVELS:
        pool = {m: velo[m] for m in pmids_by_level[lv] if m in ka_map}
        vz = _season_z({m: e["fb_velo"] for m, e in pool.items()})
        kz = _season_z({m: ka_map[m] for m in pool})
        n_baked = 0
        for m in pool:
            if m in vz and m in kz:
                key = str(m)
                entry = {
                    "level": lv, "season": season, "side": "pit",
                    "fb_velo": pool[m]["fb_velo"],
                    "velo_z": round(vz[m], 4), "k_a_z": round(kz[m], 4),
                    "n_pitches": pool[m]["n_pitches"],
                }
                # two-way collision guard: keep the higher-exposure side
                prev = by_mlbam.get(key)
                if prev is None or entry["n_pitches"] > prev["n_pitches"]:
                    by_mlbam[key] = entry
                    n_baked += 1
        counts[f"pit_{lv}"] = {"signal_qualified": len(pmids_by_level[lv]),
                               "with_k_line": len(pool), "baked": n_baked}

    out = {
        "generated_at": date.today().isoformat(),
        "season": season,
        "source": "stored zone_metrics (hitter whiff) + statcast_metrics "
                  "(pitcher FB velo) payloads + cached milb_history K legs; "
                  "offline, zero fetches",
        "frozen_coefficients": FROZEN_COEFFICIENTS,
        "counts": counts,
        "by_mlbam": {k: by_mlbam[k] for k in sorted(by_mlbam, key=int)},
    }
    if persist:
        text = json.dumps(out, indent=0) + "\n"
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != text:
            OUT_PATH.write_text(text, encoding="utf-8")
            log.info("wrote %s (%d players)", OUT_PATH, len(by_mlbam))
        else:
            log.info("%s unchanged (%d players)", OUT_PATH, len(by_mlbam))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print(json.dumps(rep["counts"], indent=1))
    print("baked", len(rep["by_mlbam"]), "players ->", OUT_PATH)
