"""ADJUDICATION probe: is a served export slice on the REPAIRED (mean-offset) grade
scale or the OLD (near-identity quantile map) scale?

Independent re-derivation. For every point in a slice we recompute the plain mean of
the per-source published FVs, once through the SHIPPED remapper (new) and once raw
(the old map was a near-identity, so raw is its stand-in), and compare each against
the served avg_fv. We only use points where the comparison is unambiguous:
  - no source is dropped_off (that path shrinks halfway to 30)
  - avg_fv_n equals the number of per_source entries carrying fv_published
  - avg_fv is present
Equal source weights are assumed; data/source_weights.json is {} on this tree.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from grade_normalization import build_remapper  # noqa: E402
import consensus as C  # noqa: E402

remap = build_remapper(aliases=getattr(C, "SOURCE_ALIASES", None))
TOL = 0.06  # tolerance absorbs 2dp rounding of avg_fv + DB drift since the 13:37 export


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def audit(path: Path, players_key="players", limit_pts=None):
    doc = json.loads(path.read_text(encoding="utf-8"))
    players = doc[players_key] if isinstance(doc, dict) else doc
    n_pts = n_cmp = 0
    new_exact = old_exact = 0
    sum_new = sum_old = 0.0
    disagree = []
    per_year_new = {}
    per_year_tot = {}
    for p in players:
        pos = p.get("position")
        for pt in (p.get("points") or []):
            n_pts += 1
            avg = _f(pt.get("avg_fv"))
            n = pt.get("avg_fv_n")
            if avg is None or not n:
                continue
            ps = pt.get("per_source") or {}
            if not isinstance(ps, dict):
                continue
            vals = []
            bad = False
            for src, ent in ps.items():
                if not isinstance(ent, dict):
                    bad = True
                    break
                if ent.get("dropped_off"):
                    bad = True
                    break
                fvp = _f(ent.get("fv_published"))
                if fvp is None:
                    continue
                vals.append((src, fvp, ent.get("snapshot_date") or pt.get("snapshot_date")))
            if bad or len(vals) != int(n) or not vals:
                continue
            n_cmp += 1
            raws = [v for _, v, _ in vals]
            news = []
            for src, v, dt in vals:
                try:
                    yr = int(str(dt)[:4])
                except (TypeError, ValueError):
                    yr = None
                nv = remap(v, src, pos, yr) if yr else None
                news.append(v if nv is None else nv)
            pred_new = sum(news) / len(news)
            pred_old = sum(raws) / len(raws)
            dn = abs(pred_new - avg)
            do = abs(pred_old - avg)
            sum_new += dn
            sum_old += do
            if dn < TOL:
                new_exact += 1
            if do < TOL:
                old_exact += 1
            yr = str(pt.get("snapshot_date") or "")[:4]
            per_year_tot[yr] = per_year_tot.get(yr, 0) + 1
            if dn < TOL:
                per_year_new[yr] = per_year_new.get(yr, 0) + 1
            elif len(disagree) < 12:
                disagree.append((p.get("player_key"), pt.get("snapshot_date"), avg,
                                 round(pred_new, 3), round(pred_old, 3)))
    print(f"\n=== {path.name} ===")
    print(f"  points {n_pts}  comparable {n_cmp}")
    if n_cmp:
        print(f"  matches NEW scale: {new_exact} ({new_exact/n_cmp:.4%})  mean|d| {sum_new/n_cmp:.4f}")
        print(f"  matches OLD/raw  : {old_exact} ({old_exact/n_cmp:.4%})  mean|d| {sum_old/n_cmp:.4f}")
    print("  per-year NEW-match rate (year: matched/total):")
    for y in sorted(per_year_tot):
        t = per_year_tot[y]
        m = per_year_new.get(y, 0)
        print(f"    {y}: {m}/{t} = {m/t:.4f}")
    if disagree:
        print("  sample rows matching OLD but not NEW:")
        for d in disagree:
            print("   ", d)


if __name__ == "__main__":
    for name in sys.argv[1:] or ["timeseries.json", "debuts.json", "inactive.json"]:
        audit(ROOT / "data" / name)
