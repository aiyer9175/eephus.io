# scratch lab: intlalias step 4 -- simulate the PATCH through the real consensus path.
# Monkeypatches only (repo files untouched).
import sys, json, collections, copy
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import storage, consensus, grade_normalization as gn
from consensus import build_timeseries, ADOPT_NORMALIZED_CONSENSUS, SOURCE_ALIASES

print("loading snapshots...")
snaps = storage.load_all_snapshots()
print("  n snapshots:", len(snaps))

# ---------------- ARM 1: production, as shipped ----------------
ts0 = build_timeseries(snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)
base = {}
for p in ts0:
    pts = p.points if hasattr(p, "points") else None
    last = pts[-1] if pts else None
    base[p.player_key] = dict(
        name=getattr(p, "player_name", None),
        fv=getattr(last, "consensus_fv", None) if last else None,
        fv_raw=getattr(last, "consensus_fv_raw", None) if last else None,
        status=getattr(p, "status", None),
    )
print("ARM1 players:", len(base))

# ---------------- PATCH ----------------
_orig_build_remapper = gn.build_remapper

def patched_build_remapper(years=None, aliases=None):
    latest = gn._all_latest()
    sources = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    table = {}
    for (role, yr) in list(latest.keys()):
        if years is not None and yr not in years:
            continue
        for src in sources:
            if src == gn.REFERENCE or src in gn._SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _pooled = gn._paired_dists(src, role, yr)
            if not (len(s_sorted) and len(r_sorted) and gn._mappable(s_sorted, r_sorted)):
                continue
            if len(s_sorted) < gn._MIN_N:      # NEW: honour the module's own min_n
                continue
            table[(src, role, yr)] = (s_sorted, r_sorted)
    alias_map = dict(aliases or {})

    def remap(fv, source, position, year):
        if fv is None:
            return None
        if source == gn.REFERENCE:
            return float(fv)
        try:
            yr = int(year)
        except (TypeError, ValueError):
            return float(fv)
        role = "pitcher" if gn._is_pitcher(position) else "hitter"
        ent = table.get((source, role, yr))
        if not ent:                                    # NEW: alias fallback
            canon = alias_map.get(source)
            if canon and canon != source:
                ent = table.get((canon, role, yr))
        if not ent:
            return float(fv)
        src, ref = ent
        return gn._apply_offset(float(fv), src, ref)
    return remap


def _alias_grade_sources(day_snaps):
    if not day_snaps or not SOURCE_ALIASES:
        return {}
    present = {s.source for s in day_snaps}
    out = {}
    for s in day_snaps:
        target = SOURCE_ALIASES.get(s.source)
        if target is None or target in present:
            continue
        out[(s.player_key, target)] = s.source
    return out


_orig_ccp = consensus.compute_consensus_point

def patched_ccp(day_snaps, **kw):
    gnorm = kw.get("grade_norm")
    if gnorm is None or not day_snaps:
        return _orig_ccp(day_snaps, **kw)
    amap = _alias_grade_sources(day_snaps)
    if not amap:
        return _orig_ccp(day_snaps, **kw)
    def wrapped(fv, source, position, year, _amap=amap, _g=gnorm):
        # the production loop calls grade_norm(fv, s.source, ...) AFTER the alias
        # collapse; re-attach the originating list so the right cell is used.
        for (pk, canon), orig in _amap.items():
            if canon == source:
                return _g(fv, orig, position, year)
        return _g(fv, source, position, year)
    kw = dict(kw); kw["grade_norm"] = wrapped
    return _orig_ccp(day_snaps, **kw)


gn.build_remapper = lambda years=None, aliases=None: patched_build_remapper(years, SOURCE_ALIASES)
consensus.compute_consensus_point = patched_ccp
import sys as _s
_s.modules["grade_normalization"].build_remapper = gn.build_remapper

ts1 = build_timeseries(snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)
new = {}
for p in ts1:
    pts = p.points if hasattr(p, "points") else None
    last = pts[-1] if pts else None
    new[p.player_key] = dict(
        name=getattr(p, "player_name", None),
        fv=getattr(last, "consensus_fv", None) if last else None,
        fv_raw=getattr(last, "consensus_fv_raw", None) if last else None,
        status=getattr(p, "status", None),
    )
print("ARM2 players:", len(new))

# ---------------- diff ----------------
moved = []
for pk in base:
    a, b = base[pk], new.get(pk)
    if b is None:
        continue
    if a["fv"] is None or b["fv"] is None:
        continue
    d = b["fv"] - a["fv"]
    dr = (b["fv_raw"] - a["fv_raw"]) if (a["fv_raw"] is not None and b["fv_raw"] is not None) else None
    if abs(d) > 1e-9 or (dr is not None and abs(dr) > 1e-9):
        moved.append(dict(pk=pk, name=a["name"], status=a["status"],
                          fv0=a["fv"], fv1=b["fv"], d=d,
                          raw0=a["fv_raw"], raw1=b["fv_raw"], draw=dr))
moved.sort(key=lambda r: r["draw"] if r["draw"] is not None else r["d"])
print(f"\nBOARD MOVEMENT: {len(moved)} of {len(base)} players move")
act = [m for m in moved if m["status"] == "active"]
print(f"  active: {len(act)}")
print(f"{'player':26s} {'st':9s} {'fv0':>5s} {'fv1':>5s} {'d':>5s} {'raw0':>7s} {'raw1':>7s} {'draw':>7s}")
for m in moved:
    print(f"{str(m['name'])[:26]:26s} {str(m['status'])[:9]:9s} {m['fv0']:5.1f} {m['fv1']:5.1f} "
          f"{m['d']:+5.1f} {m['raw0']:7.2f} {m['raw1']:7.2f} {m['draw']:+7.2f}")
if moved:
    dd = [m["draw"] for m in moved]
    print(f"\nmean raw delta {np.mean(dd):+.3f}  min {min(dd):+.3f}  max {max(dd):+.3f}")
    di = [m["d"] for m in moved]
    print(f"mean served-FV delta {np.mean(di):+.3f}  min {min(di):+.3f}  max {max(di):+.3f}")
json.dump(moved, open(HERE / "tools" / "_gn_intlalias_moved.json", "w"), indent=1)
