# SCRATCH LAB (lane: blastradius). Re-derives the grade-normalization blast radius
# by running the SHIPPED consensus.build_timeseries path twice: once with the NEW
# continuous offset (_apply_offset as committed in the working tree) and once with
# the OLD discrete np.interp quantile map (restored by monkeypatch).
#
# Nothing is written outside data/_gn_lab/.
import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)

OUT = _HERE / "data" / "_gn_lab"
OUT.mkdir(parents=True, exist_ok=True)

import grade_normalization as gn          # noqa: E402
import consensus as cns                   # noqa: E402
from storage import load_all_snapshots    # noqa: E402


def _old_apply(fv, src, ref):
    """The PRE-repair discrete quantile map, verbatim from git HEAD."""
    if len(src) == 1:
        q = 0.5
    else:
        q = float(np.interp(float(fv), src, np.linspace(0.0, 1.0, len(src))))
    return float(np.interp(q, np.linspace(0.0, 1.0, len(ref)), ref))


_NEW_APPLY = gn._apply_offset


def build(mode: str):
    """mode in {'new','old','off'} -> {player_key: (latest_date, consensus_fv_raw)}"""
    gn._paired_dists.cache_clear()
    gn._all_latest.cache_clear()
    if mode == "old":
        gn._apply_offset = _old_apply
    else:
        gn._apply_offset = _NEW_APPLY
    snaps = load_all_snapshots()
    ts = cns.build_timeseries(snaps, normalize=(mode != "off"))
    out = {}
    for p in ts:
        pts = p.points or []
        if not pts:
            continue
        last = pts[-1]
        fv = getattr(last, "consensus_fv_raw", None)
        out[p.player_key] = (last.snapshot_date, None if fv is None else float(fv),
                             p.player_name, p.position, p.org, p.status,
                             float(p.fv_close) if p.fv_close is not None else None)
    gn._apply_offset = _NEW_APPLY
    return out


def main():
    res = {}
    for mode in ("new", "old"):
        print(f"building consensus: mode={mode} ...", flush=True)
        res[mode] = build(mode)
        print(f"  players={len(res[mode])}", flush=True)
    (OUT / "consensus_modes.json").write_text(
        json.dumps({m: {k: v for k, v in d.items()} for m, d in res.items()}),
        encoding="utf-8")
    print("wrote", OUT / "consensus_modes.json")


if __name__ == "__main__":
    main()
