# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- population slices (level / age / acquisition)."""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

F = json.loads((HERE / "_sweep_calib_out" / "frame.json").read_text(encoding="utf-8"))
PRIMARY = [r for r in F["rows"] if r["year"] <= 2020]


def implied(g):
    v = vf.fv_to_6yr_avg_war(g)
    return None if v is None else v * 6.0


def cell(rows, gkey="grade_quantile"):
    if not rows:
        return None
    im = statistics.mean(implied(r[gkey]) for r in rows)
    re = statistics.mean(r["war"] for r in rows)
    return {"n": len(rows), "mean_grade": round(statistics.mean(r[gkey] for r in rows), 1),
            "implied": round(im, 2), "realized": round(re, 2), "bias": round(re - im, 2),
            "med_real": round(statistics.median(r["war"] for r in rows), 2),
            "bust_rate": round(sum(1 for r in rows if r["war"] < 3.0) / len(rows), 3)}


def show(title, keyfn, order=None, gkey="grade_quantile", minn=15):
    print(f"\n--- {title} (grade key {gkey}) ---")
    print(f"  {'cell':>10s} {'side':>4s} {'n':>5s} {'grade':>6s} {'implied':>8s} {'real':>7s} {'bias':>7s} {'bustrt':>7s}")
    groups = defaultdict(list)
    for r in PRIMARY:
        k = keyfn(r)
        if k is None:
            continue
        groups[(k, r["side"])].append(r)
    keys = order or sorted({k for k, _ in groups})
    for k in keys:
        for side in ("hit", "pit"):
            g = groups.get((k, side)) or []
            if len(g) < minn:
                continue
            c = cell(g, gkey)
            print(f"  {str(k):>10s} {side:>4s} {c['n']:5d} {c['mean_grade']:6.1f} {c['implied']:8.2f} "
                  f"{c['realized']:7.2f} {c['bias']:+7.2f} {c['bust_rate']:7.3f}")


LEVELS = ["DSL", "CPX", "A", "A+", "AA", "AAA"]
show("(b1) by LEVEL reached at decision", lambda r: r["level"], LEVELS)


def ageband(r):
    a = r.get("age")
    if a is None:
        return None
    a = float(a)
    if a < 19:
        return "<19"
    if a < 21:
        return "19-20"
    if a < 23:
        return "21-22"
    if a < 25:
        return "23-24"
    return "25+"


show("(b2) by AGE BAND at decision", ageband, ["<19", "19-20", "21-22", "23-24", "25+"])
show("(b3) by ACQUISITION cohort", lambda r: r["acq"], ["IFA", "college", "HS", "unknown"])


def arl(r):
    v = r.get("age_rel_level")
    if v is None:
        return None
    v = float(v)
    if v <= -1.5:
        return "young<=-1.5"
    if v <= -0.5:
        return "-1.5..-0.5"
    if v < 0.5:
        return "~0"
    if v < 1.5:
        return "+0.5..1.5"
    return "old>=1.5"


show("(b4) by AGE-REL-LEVEL", arl, ["young<=-1.5", "-1.5..-0.5", "~0", "+0.5..1.5", "old>=1.5"])

print("\n--- (b5) LEVEL x within-tier: only rows with grade_quantile in [42.5, 57.5] ---")
mid = [r for r in PRIMARY if 42.5 <= r["grade_quantile"] <= 57.5]
groups = defaultdict(list)
for r in mid:
    groups[r["level"]].append(r)
for k in LEVELS:
    g = groups.get(k) or []
    if len(g) < 10:
        continue
    c = cell(g)
    print(f"  {k:>5s} n={c['n']:4d} grade={c['mean_grade']:.1f} implied={c['implied']:.2f} "
          f"real={c['realized']:.2f} bias={c['bias']:+.2f}")

print("\n--- (b6) age band within the mid tier ---")
groups = defaultdict(list)
for r in mid:
    groups[ageband(r)].append(r)
for k in ["<19", "19-20", "21-22", "23-24", "25+"]:
    g = groups.get(k) or []
    if len(g) < 10:
        continue
    c = cell(g)
    print(f"  {k:>6s} n={c['n']:4d} grade={c['mean_grade']:.1f} implied={c['implied']:.2f} "
          f"real={c['realized']:.2f} bias={c['bias']:+.2f}")
