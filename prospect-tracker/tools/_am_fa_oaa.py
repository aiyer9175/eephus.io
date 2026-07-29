# AUDIT LANE `fa`. (e) NEW DATA: does Statcast OAA carry FA WAR-path signal?
"""SCREENING GATE before any expensive refit.

fa_projection.py states as a documented v1 simplification that "defense/
baserunning are not" modelled, while its target is bWAR, which INCLUDES
defense. So there is a real, testable gap: if the year-1 WAR projection is
blind to defense, its residual should be predictable from a prior-season
defensive measurement.

THE SCREEN: residual = actual class-year bWAR - projected war_y1, for every
position player in the Gate-2 signing corpus, against that player's OAA in
the season BEFORE the class year (strictly ex-ante).

If the residual carries no OAA signal there is nothing for a feature to
learn and the expensive refit is not warranted. Reported with a permutation
null, a bootstrap CI, and per-winter folds, so a null here is a MEASURED
null and not an absence of evidence.
"""
from __future__ import annotations

import json
import math
import pickle
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa  # noqa: E402


def spearman(a, b):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((x - mb) ** 2 for x in rb))
    if va == 0 or vb == 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (va * vb)


def build():
    import fa_projection as fp
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        pool = pickle.load(fh)
    oaa = json.loads((ROOT / "data" / "savant_oaa.json").read_text(encoding="utf-8"))
    by = oaa["by_mlbam"]
    corpus = fp.build_corpus()
    actual = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                actual[(r["mlbam"], r["season"])] = r
    rows = []
    for s in pool:
        if s.get("_side") != "hit":
            continue
        m = s.get("mlbam_id")
        if not m:
            continue
        cy = s["class_year"]
        a = actual.get((m, cy))
        if not a or not a.get("pa") or a["pa"] < 150:
            continue
        rec = by.get(str(m)) or by.get(m)
        if not rec:
            continue
        # prior-season OAA, summed over the positions he played that season
        # (by_mlbam[id][season][pos] -> metrics, plus a "_primary" marker).
        # Strictly the season BEFORE the class year: ex-ante by construction.
        season_rec = rec.get(str(cy - 1)) if isinstance(rec, dict) else None
        if not isinstance(season_rec, dict):
            continue
        tot_oaa = tot_frp = 0.0
        found = False
        for pos, v in season_rec.items():
            if pos.startswith("_") or not isinstance(v, dict):
                continue
            if v.get("oaa") is not None:
                tot_oaa += float(v["oaa"])
                found = True
            if v.get("frp") is not None:
                tot_frp += float(v["frp"])
        if not found:
            continue
        rows.append({
            "winter": cy, "name": s["player_name"], "pos": s.get("position"),
            "war_y1": float(s["_war_path"]["war_y1"]),
            "act_war": float(a.get("war") or 0.0),
            "oaa": tot_oaa, "frp": tot_frp, "age": s.get("_age"),
        })
    for r in rows:
        r["resid"] = r["act_war"] - r["war_y1"]
    return rows


if __name__ == "__main__":
    rows = _am_fa.cached("fa_oaa_rows", build)
    print("COVERAGE: %d position-player signings with prior-season OAA and a "
          "scoreable class year" % len(rows))
    if not rows:
        print("UNAVAILABLE - no overlap; screen cannot be run")
        sys.exit(0)
    byw = defaultdict(list)
    for r in rows:
        byw[r["winter"]].append(r)
    print("  winters: %s" % {w: len(v) for w, v in sorted(byw.items())})

    resid = [r["resid"] for r in rows]
    print("\n  residual (actual bWAR - projected war_y1): mean %+.4f sd %.4f"
          % (statistics.mean(resid), statistics.pstdev(resid)))

    for sig in ("oaa", "frp"):
        x = [r[sig] for r in rows]
        rho = spearman(x, resid)
        # bootstrap
        rng = random.Random(20260725)
        bs = []
        for _ in range(2000):
            idx = [rng.randrange(len(rows)) for _ in range(len(rows))]
            bs.append(spearman([x[i] for i in idx], [resid[i] for i in idx]))
        bs = sorted(v for v in bs if v == v)
        lo, hi = bs[int(.025 * len(bs))], bs[int(.975 * len(bs))]
        # permutation null on the SAME column
        rng2 = random.Random(31)
        nulls = []
        for _ in range(2000):
            xp = x[:]
            rng2.shuffle(xp)
            nulls.append(spearman(xp, resid))
        nulls = sorted(v for v in nulls if v == v)
        nlo, nhi = nulls[int(.025 * len(nulls))], nulls[int(.975 * len(nulls))]
        print("\n  %-4s vs residual: Spearman %+0.4f  CI95 [%+0.4f, %+0.4f]"
              % (sig, rho, lo, hi))
        print("       permutation null band [%+0.4f, %+0.4f]  -> MDE95 ~ %0.4f"
              % (nlo, nhi, (nhi - nlo) / 2))
        print("       verdict: %s"
              % ("SIGNAL (outside the null band)" if (rho < nlo or rho > nhi)
                 else "NULL (inside the zero-information band)"))
        print("       per-winter rho: " + "  ".join(
            "%d %+0.3f" % (w, spearman([r[sig] for r in v], [r["resid"] for r in v]))
            for w, v in sorted(byw.items()) if len(v) >= 15))

    # sanity: does OAA correlate with the LEVEL of WAR at all in this sample?
    print("\n  sanity check (OAA should track WAR LEVEL even if not the residual):")
    print("       oaa vs actual bWAR  rho %+0.4f"
          % spearman([r["oaa"] for r in rows], [r["act_war"] for r in rows]))
    print("       oaa vs projected    rho %+0.4f"
          % spearman([r["oaa"] for r in rows], [r["war_y1"] for r in rows]))
