"""SCRATCH: measure the SERVED eFV effect of giving gap players a real draft-board anchor.

Isolated + restorable: patches only the live feature matrices, re-runs efv_score.run_live
and efv_export.run, diffs the served grade. Restores from .cache/anchor_probe/bak.

  python tools/_anchor_serve_lab.py baseline
  python tools/_anchor_serve_lab.py patch
  python tools/_anchor_serve_lab.py restore
"""
from __future__ import annotations
import json, sys, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
BAK = HERE / ".cache" / "anchor_probe" / "bak"
OUT = HERE / ".cache" / "anchor_probe"
sys.path.insert(0, str(HERE))

MATS = ["xfv_live_hitter_matrix.json", "xfv_live_pitcher_matrix.json"]
GEN = ["xfv_scored_live.json", "xfv_scored_live_pitcher.json", "xfv.json",
       "xfv_tools_live.json"]


def score_and_capture(tag: str) -> dict:
    import efv_score, efv_export
    for side in ("hit", "pit"):
        efv_score.run_live(True, side)
    rep = efv_export.run(persist=False)
    grades = {k: {"q": v.get("xfv_grade_quantile"),
                  "g": v.get("xfv_grade"),
                  "kind": v.get("kind"),
                  "cons": v.get("consensus_fv")}
              for k, v in rep["by_player"].items()}
    (OUT / f"served_{tag}.json").write_text(json.dumps(grades), encoding="utf-8")
    print(tag, "captured", len(grades))
    return grades


def patch_matrices(cands: dict) -> int:
    n = 0
    for f in MATS:
        p = DATA / f
        rows = json.loads(p.read_text(encoding="utf-8"))
        for r in rows:
            c = cands.get(r["player_key"])
            if not c:
                continue
            fv = float(c["fv"])
            r["consensus_fv_raw"] = fv
            r["consensus_fv_pre_shrinkage"] = fv
            r["fv_effective"] = fv          # board date is recent; no stale decay
            r["anchor_stale_discount"] = 0.0
            r["asof_date"] = c["date"]
            n += 1
        p.write_text(json.dumps(rows), encoding="utf-8")
    return n


def restore():
    for f in MATS + GEN:
        if (BAK / f).exists():
            shutil.copy2(BAK / f, DATA / f)
    print("restored", len(MATS + GEN), "artifacts")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "baseline":
        score_and_capture("baseline")
    elif cmd == "patch":
        cands = json.loads((OUT / "seedable_gap.json").read_text(encoding="utf-8"))
        print("patched rows:", patch_matrices(cands))
        score_and_capture("patched")
    elif cmd == "restore":
        restore()
