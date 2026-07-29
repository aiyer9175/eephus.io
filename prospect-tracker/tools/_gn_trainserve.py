# SCRATCH LAB (lane: blastradius) -- Step 2: train/serve skew.
# Does the eFV TRAINING feature source (debuts.json + inactive.json, consumed by
# efv_dataset.build_matrix) carry the SAME grade normalization as the SERVED board
# (timeseries.json, consumed by efv_dataset.build_live_matrix)?
import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "data" / "_gn_lab"

modes = json.loads((OUT / "consensus_modes.json").read_text(encoding="utf-8"))
new, old = modes["new"], modes["old"]


def probe(fname, label):
    recs = json.loads((_HERE / "data" / fname).read_text(encoding="utf-8"))
    if isinstance(recs, dict):
        recs = recs.get("players") or []
    dn, do, n_cmp = [], [], 0
    for r in recs:
        k = r.get("player_key")
        pts = r.get("points") or []
        if not k or not pts or k not in new:
            continue
        # match the LAB's latest point by date so we compare like with like
        last = pts[-1]
        if last.get("snapshot_date") != new[k][0]:
            continue
        fv = last.get("consensus_fv_raw")
        if fv is None or new[k][1] is None or old[k][1] is None:
            continue
        n_cmp += 1
        dn.append(abs(fv - new[k][1]))
        do.append(abs(fv - old[k][1]))
    dn, do = np.array(dn), np.array(do)
    print(f"{label:16s} rows={len(recs):6d}  comparable={n_cmp:6d}")
    if n_cmp:
        print(f"   vs NEW offset: exact {int((dn<0.051).sum())} ({100*(dn<0.051).mean():5.2f}%)"
              f"  mean|d| {dn.mean():.4f}")
        print(f"   vs OLD map   : exact {int((do<0.051).sum())} ({100*(do<0.051).mean():5.2f}%)"
              f"  mean|d| {do.mean():.4f}")
        print(f"   VERDICT: sidecar is on the "
              f"{'NEW (repaired)' if dn.mean() < do.mean() else 'OLD (pre-repair)'} scale")
    return n_cmp


for f, lab in (("timeseries.json", "served board"),
               ("debuts.json", "TRAIN debuted"),
               ("inactive.json", "TRAIN busts")):
    probe(f, lab)
    print()

# --- how many TRAINING rows would actually move? (the debut-year cohort) ---
print("training-cohort exposure: eFV DEBUT_YEARS rows whose as-of grade is remapped")
import efv_dataset as ed  # noqa: E402
print("  DEBUT_YEARS:", sorted(ed.DEBUT_YEARS))
