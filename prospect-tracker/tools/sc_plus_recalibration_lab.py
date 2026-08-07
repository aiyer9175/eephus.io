# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast+ recalibration lab (omnibus-3 lane E).

Scores three SC+ variants side by side on the SERVED pool
(data/timeseries.json) so the pre-registered battery in
docs/SC_PLUS_RECALIBRATION_GATE.md is measured, not asserted:

  S0  shipped         current statcast_plus.py, no shrink, no rescale
  S1  shrink          EB shrink + volume floors (the reverted 2026-07-29 C1 build)
  S2  shrink+rescale  S1 divided by ONE per-side composite-z sd (the lane brief's
                      version of the 10-per-sigma fix)
  S3  shrink+coverage S1 divided by the composite-z sd of the player's own
                      CONTRIBUTING-COMPONENT class

S2 exists to be rejected on the record. A composite that averages k correlated
unit-z legs has a spread that falls with k, so one per-side divisor leaves every
coverage class on a different sigma and the elite band stays a coverage artifact
rather than a talent signal. S3 is the same divisor computed conditionally. It
does NOT reweight the composite: the legs stay equal-weight, only the divisor
that turns the mean into "10 points per sigma" becomes honest.

Read-only. Writes NOTHING under data/. The battery artifact goes to
docs/sc-plus-2026-08-07/ only when --emit is passed, and never to data/.

Run: python tools/sc_plus_recalibration_lab.py [--emit]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import statcast_plus as SP  # noqa: E402

TS = ROOT / "data" / "timeseries.json"

# Which raw sample size backs each component. The shrink is only as honest as
# this map: a component whose volume field is absent gets NO shrink credit and
# is dropped, which is the conservative direction.
_VOLUME_OF = {
    "avg_ev": "bbe", "hard_hit_pct": "bbe", "barrel_pct": "bbe",
    "hh_inv": "bbe", "barrel_inv": "bbe",
    "z_contact": "pitches", "whiff_inv": "pitches", "chase_inv": "pitches",
    "whiff": "pitches", "chase": "pitches",
    "top_velo": "velo_n",
}
_FLOOR = {"bbe": 10, "pitches": 25, "velo_n": 10}
_K = {"bbe": 50, "pitches": 100, "velo_n": 50}


def volumes(player: dict) -> dict:
    sc = player.get("statcast_metrics") or {}
    cq = sc.get("contact_quality") or {}
    z = SP._zone_row(player) or {}
    pm = sc.get("pitch_movement") or {}
    summary = pm.get("pitch_summary") or []
    top = summary[0] if summary else {}
    return {"bbe": cq.get("batted_balls"),
            "pitches": z.get("pitches"),
            "velo_n": top.get("count")}


def _num(v):
    return v if isinstance(v, (int, float)) and v is not None else None


def build_pool_v2(players, shrink: bool, rescale: bool) -> dict:
    """Two-pass pool: raw means give the EB prior, then the pool mean/sd are
    recomputed on the SHRUNK column so the numerator and the denominator live
    on the same scale. Taking the denominator from the UNSHRUNK pool is the
    measured aStuff+ defect (docs/efv-2026-07-29/GATED_CANDIDATES.md C3, 7.16
    points per sigma against an advertised 10); it is the same bug here."""
    rows = []
    for p in players:
        is_pit = SP._is_pitcher(p)
        row = SP._extract_pitcher(p) if is_pit else SP._extract_hitter(p)
        rows.append(("pit" if is_pit else "hit", row, volumes(p)))

    out = {}
    for side in ("hit", "pit"):
        side_rows = [(r, v) for s, r, v in rows if s == side]
        if not side_rows:
            out[side] = {}
            continue
        keys = sorted({k for r, _ in side_rows for k in r})
        prior = {}
        for k in keys:
            nums = [float(r[k]) for r, _ in side_rows if _num(r.get(k)) is not None]
            prior[k] = st.mean(nums) if nums else None
        stats = {}
        for k in keys:
            vals = [shrunk_value(k, r.get(k), v, prior[k], shrink)
                    for r, v in side_rows]
            vals = [x for x in vals if x is not None]
            if not vals:
                stats[k] = {"mean": None, "sd": 1.0, "prior": prior[k]}
                continue
            m = st.mean(vals)
            sd = st.pstdev(vals) if len(vals) > 1 else 0.0
            # Relative near-zero guard: `sd > 0` lets a degenerate column
            # through and hands one row an unbounded z.
            if not (sd > 0 and sd > abs(m) * 1e-9 and sd > 1e-9):
                sd = 1.0
            stats[k] = {"mean": m, "sd": sd, "prior": prior[k]}
        out[side] = stats

    if rescale:
        for side in ("hit", "pit"):
            zs = []
            cells: dict[str, list[float]] = {}
            for s, r, v in rows:
                if s != side:
                    continue
                got = composite_parts(r, v, out[side], shrink)
                if got is None:
                    continue
                z, cov = got
                zs.append(z)
                cells.setdefault(cov, []).append(z)
            sd = st.pstdev(zs) if len(zs) > 1 else 1.0
            out[side]["__composite_sd__"] = sd if sd > 1e-6 else 1.0
            out[side]["__coverage_sd__"] = {
                c: st.pstdev(v) for c, v in cells.items()
                if len(v) >= MIN_CELL and st.pstdev(v) > 1e-6}
    return out


# Below this many members a coverage class borrows the pooled per-side sd
# rather than fitting its own: a divisor estimated on a handful of rows is
# noisier than the bias it removes.
MIN_CELL = 50


def shrunk_value(key, raw, vol, prior, shrink: bool):
    raw = _num(raw)
    if raw is None:
        return None
    if not shrink:
        return float(raw)
    fam = _VOLUME_OF.get(key)
    if fam is None or prior is None:
        return float(raw)
    n = _num(vol.get(fam))
    if n is None or n < _FLOOR[fam]:
        return None
    k = _K[fam]
    return (n * float(raw) + k * float(prior)) / (n + k)


def composite_parts(row, vol, side_pool, shrink: bool):
    """(mean z, coverage key) or None. The coverage key names the legs that
    actually contributed, which is what the divisor has to condition on."""
    zs, keys = [], []
    for key in row:
        ps = side_pool.get(key)
        if not ps or ps.get("mean") is None:
            continue
        val = shrunk_value(key, row.get(key), vol, ps.get("prior"), shrink)
        if val is None:
            continue
        zs.append((val - float(ps["mean"])) / float(ps["sd"]))
        keys.append(key)
    if not zs:
        return None
    return sum(zs) / len(zs), "|".join(sorted(keys))


def composite_z(row, vol, side_pool, shrink: bool):
    got = composite_parts(row, vol, side_pool, shrink)
    return None if got is None else got[0]


def score(player, pool, shrink: bool, rescale: str | bool):
    is_pit = SP._is_pitcher(player)
    row = SP._extract_pitcher(player) if is_pit else SP._extract_hitter(player)
    side_pool = pool.get("pit" if is_pit else "hit") or {}
    got = composite_parts(row, volumes(player), side_pool, shrink)
    if got is None:
        return None
    z, cov = got
    if rescale == "coverage":
        sd = (side_pool.get("__coverage_sd__") or {}).get(cov)
        z = z / float(sd or side_pool.get("__composite_sd__") or 1.0)
    elif rescale:
        z = z / float(side_pool.get("__composite_sd__") or 1.0)
    return int(round(100 + z * 10))


def _spearman(a, b):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = st.mean(ra), st.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    return round(cov / (va * vb) ** 0.5, 4) if va and vb else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    players = json.loads(TS.read_text(encoding="utf-8"))["players"]
    flags = {"S0_shipped": (False, False), "S1_shrink": (True, False),
             "S2_shrink_rescale": (True, True),
             "S3_shrink_coverage": (True, "coverage")}
    stages = {name: build_pool_v2(players, shrink=sh, rescale=bool(rs))
              for name, (sh, rs) in flags.items()}

    scores = {}
    for name, pool in stages.items():
        sh, rs = flags[name]
        scores[name] = {p["player_key"]: score(p, pool, sh, rs) for p in players}

    by_key = {p["player_key"]: p for p in players}
    report = {"stages": {}}

    for name in stages:
        s = scores[name]
        carriers = {k: v for k, v in s.items() if v is not None}
        per_side = {"hit": [], "pit": []}
        for k, v in carriers.items():
            per_side["pit" if SP._is_pitcher(by_key[k]) else "hit"].append(v)
        ent = {"n_carriers": len(carriers)}
        for side, vals in per_side.items():
            ent[side] = {"n": len(vals),
                         "mean": round(st.mean(vals), 2) if vals else None,
                         "sd": round(st.pstdev(vals), 3) if len(vals) > 1 else None,
                         "min": min(vals) if vals else None,
                         "max": max(vals) if vals else None}
        top = sorted(carriers.items(), key=lambda kv: -kv[1])[:10]
        ent["top10"] = []
        sh, rs = flags[name]
        for k, v in top:
            p = by_key[k]
            vol = volumes(p)
            side = "pit" if SP._is_pitcher(p) else "hit"
            row = SP._extract_pitcher(p) if side == "pit" else SP._extract_hitter(p)
            got = composite_parts(row, vol, stages[name][side], sh)
            legs = got[1].split("|") if got else []
            # The honest volume question is not "does this row have thin data
            # anywhere" but "is any leg that CONTRIBUTED built on a thin sample".
            worst = None
            for leg in legs:
                fam = _VOLUME_OF.get(leg)
                if fam:
                    n = _num(vol.get(fam))
                    worst = n if worst is None else min(worst, n)
            ent["top10"].append({"key": k, "sc": v, "legs": len(legs),
                                 "min_contributing_n": worst,
                                 "bbe": vol["bbe"], "pitches": vol["pitches"],
                                 "velo_n": vol["velo_n"]})
        report["stages"][name] = ent

    # Gate-band populations at the SHIPPED numeric thresholds.
    gates = {"eta_elite_130": (">=", 130), "eta_top_115": (">=", 115),
             "eta_bottom_85": ("<=", 85), "breakout_115": (">=", 115),
             "breakout_stat_130": (">=", 130), "quintile_top_110": (">=", 110),
             "quintile_bot_90": ("<=", 90), "spot_elite_120": (">=", 120),
             "spot_above_105": (">=", 105), "spot_below_95": ("<=", 95)}
    report["populations_at_shipped_thresholds"] = {}
    for name in stages:
        s = {k: v for k, v in scores[name].items() if v is not None}
        report["populations_at_shipped_thresholds"][name] = {
            g: sum(1 for v in s.values() if (v >= t if op == ">=" else v <= t))
            for g, (op, t) in gates.items()}

    # Per-side composite sd is the E3 transform constant.
    report["composite_sd"] = {
        name: {side: round(float(stages[name][side].get("__composite_sd__") or 0), 4)
               for side in ("hit", "pit")}
        for name in ("S2_shrink_rescale",)}
    for name in ("S0_shipped", "S1_shrink"):
        report["composite_sd"][name] = {}
        for side in ("hit", "pit"):
            vals = [v for k, v in scores[name].items()
                    if v is not None
                    and (SP._is_pitcher(by_key[k]) == (side == "pit"))]
            report["composite_sd"][name][side] = round(st.pstdev(vals) / 10.0, 4) if len(vals) > 1 else None

    # Rank agreement between consecutive stages, on the common carrier set.
    report["spearman"] = {}
    for a, b in (("S0_shipped", "S1_shrink"), ("S1_shrink", "S2_shrink_rescale"),
                 ("S1_shrink", "S3_shrink_coverage"),
                 ("S0_shipped", "S3_shrink_coverage")):
        common = [k for k in scores[a] if scores[a][k] is not None and scores[b][k] is not None]
        report["spearman"][f"{a}->{b}"] = {
            "n_common": len(common),
            "rho": _spearman([scores[a][k] for k in common], [scores[b][k] for k in common]),
            "dropped": sum(1 for k in scores[a] if scores[a][k] is not None and scores[b][k] is None),
            "added": sum(1 for k in scores[b] if scores[b][k] is not None and scores[a][k] is None)}

    # Volume hygiene: how much of the shipped pool rests on unusable samples.
    thin = {"bbe_lt10": 0, "pitches_lt25": 0, "velo_lt10": 0}
    for p in players:
        if scores["S0_shipped"].get(p["player_key"]) is None:
            continue
        v = volumes(p)
        if _num(v["bbe"]) is not None and v["bbe"] < 10:
            thin["bbe_lt10"] += 1
        if _num(v["pitches"]) is not None and v["pitches"] < 25:
            thin["pitches_lt25"] += 1
        if _num(v["velo_n"]) is not None and v["velo_n"] < 10:
            thin["velo_lt10"] += 1
    report["thin_samples_in_shipped_pool"] = thin

    # Coverage-class spread. This is the number that decides S2 vs S3: if the
    # classes sit on different sigmas, one per-side divisor cannot fix the scale.
    report["coverage_classes"] = {}
    for name in ("S0_shipped", "S1_shrink", "S3_shrink_coverage"):
        sh, _ = flags[name]
        cells: dict[str, list[float]] = {}
        for p in players:
            side = "pit" if SP._is_pitcher(p) else "hit"
            row = SP._extract_pitcher(p) if side == "pit" else SP._extract_hitter(p)
            got = composite_parts(row, volumes(p), stages[name][side], sh)
            if got:
                cells.setdefault(f"{side}:{got[1]}", []).append(got[0])
        report["coverage_classes"][name] = {
            c: {"n": len(v), "pts_per_sigma": round(10 * st.pstdev(v), 2)}
            for c, v in sorted(cells.items(), key=lambda kv: -len(kv[1]))
            if len(v) > 1}

    # Served points per sigma AFTER the transform, per coverage class. A true
    # 10-per-sigma index reads ~10.0 in every row of this table.
    report["served_pts_per_sigma_by_class"] = {}
    for name in stages:
        sh, rs = flags[name]
        cells: dict[str, list[float]] = {}
        for p in players:
            v = scores[name].get(p["player_key"])
            if v is None:
                continue
            side = "pit" if SP._is_pitcher(p) else "hit"
            row = SP._extract_pitcher(p) if side == "pit" else SP._extract_hitter(p)
            got = composite_parts(row, volumes(p), stages[name][side], sh)
            if got:
                cells.setdefault(f"{side}:{got[1]}", []).append(float(v))
        report["served_pts_per_sigma_by_class"][name] = {
            c: round(st.pstdev(v), 2) for c, v in sorted(cells.items())
            if len(v) > 1}

    # ---- Consumer crossings -------------------------------------------------
    # ETA nudge, breakout gates and the TBS band are what a reader actually
    # sees move, so they are counted per stage rather than argued about.
    def eta_nudge(v):
        if v is None:
            return 0.0
        return -0.50 if v >= 130 else -0.25 if v >= 115 else 0.25 if v <= 85 else 0.0

    def tbs_term(v):
        return None if v is None else max(0.0, min(1.0, (v - 80) / 50.0))

    report["crossings"] = {}
    base = scores["S0_shipped"]
    for name in ("S1_shrink", "S2_shrink_rescale", "S3_shrink_coverage"):
        s = scores[name]
        keys = [k for k in base if base[k] is not None or s[k] is not None]
        eta_moved = sum(1 for k in keys if eta_nudge(base[k]) != eta_nudge(s[k]))
        g115 = sum(1 for k in keys
                   if ((base[k] or 0) >= 115) != ((s[k] or 0) >= 115))
        g130 = sum(1 for k in keys
                   if ((base[k] or 0) >= 130) != ((s[k] or 0) >= 130))
        tb = [abs(tbs_term(s[k]) - tbs_term(base[k]))
              for k in keys if base[k] is not None and s[k] is not None]
        report["crossings"][name] = {
            "eta_nudge_changed": eta_moved,
            "breakout_115_flipped": g115,
            "breakout_130_flipped": g130,
            "tbs_term_mean_abs_delta": round(st.mean(tb), 4) if tb else None,
            "tbs_term_max_abs_delta": round(max(tb), 4) if tb else None,
            "tbs_base_mean_abs_delta_x_w20": round(st.mean(tb) * 0.20, 4) if tb else None,
        }

    # eFV tilt: the served multiplier on the WAR projection, at the shipped
    # slope. `c` is the per-side preservation constant that holds the tilt at
    # its pre-rescale spread instead of letting it grow to intent size.
    fwd_r = {"hit": 0.1541, "pit": 0.1206}
    report["tilt"] = {}
    for name in stages:
        per_side = {"hit": [], "pit": []}
        for p in players:
            v = scores[name].get(p["player_key"])
            if v is None:
                continue
            side = "pit" if SP._is_pitcher(p) else "hit"
            slope = fwd_r[side] * 0.01
            per_side[side].append(min(1.18, max(0.82, 1.0 + (v - 100.0) * slope)))
        report["tilt"][name] = {
            side: {"sd": round(st.pstdev(v), 5) if len(v) > 1 else None,
                   "min": round(min(v), 4) if v else None,
                   "max": round(max(v), 4) if v else None,
                   "n_clamped": sum(1 for x in v if x <= 0.8201 or x >= 1.1799)}
            for side, v in per_side.items()}
    for side in ("hit", "pit"):
        a = report["tilt"]["S1_shrink"][side]["sd"]
        b = report["tilt"]["S3_shrink_coverage"][side]["sd"]
        report["tilt"].setdefault("preservation_constant_S1_over_S3", {})[side] = (
            round(a / b, 4) if a and b else None)

    print(json.dumps(report, indent=2))
    if args.emit:
        out = ROOT / "docs" / "sc-plus-2026-08-07"
        out.mkdir(parents=True, exist_ok=True)
        (out / "battery.json").write_text(json.dumps(report, indent=2) + "\n",
                                          encoding="utf-8")
        print("wrote", out / "battery.json", file=sys.stderr)


if __name__ == "__main__":
    main()
