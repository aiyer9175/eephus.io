# scratch lab: intlalias (C4 adjudication). Not part of the build.
import sys, os, json, sqlite3
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import grade_normalization as gn

def step1():
    remap = gn.build_remapper()
    # inspect the closure's table
    tbl = remap.__closure__
    # easier: rebuild the table logic
    latest = gn._all_latest()
    sources = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    print("SOURCES:", sorted(sources))
    cells = []
    for (role, yr) in sorted(latest.keys()):
        for src in sorted(sources):
            if src == gn.REFERENCE or src in gn._SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, pooled = gn._paired_dists(src, role, yr)
            if len(s_sorted) and len(r_sorted) and gn._mappable(s_sorted, r_sorted):
                off = float(np.mean(s_sorted) - np.mean(r_sorted))
                cells.append((src, role, yr, len(s_sorted), pooled, round(off, 3)))
    intl = [c for c in cells if c[0] == "mlb_pipeline_international"]
    print("\nINTL CELLS (src, role, year, n_pair, pooled, offset):")
    for c in intl:
        print("  ", c)
    print("\nALL CELLS count:", len(cells))
    mp = [c for c in cells if c[0] == "mlb_pipeline"]
    print("\nmlb_pipeline CELLS:")
    for c in mp:
        print("  ", c)
    return cells

if __name__ == "__main__":
    step1()
