# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Add the fielding_triangulation row to data/model_registry.json (idempotent).

The read is docs/ewar/FIELDING_TRIANGULATION_GATE.md part 11 (2026-10-16, FAIL),
artifact data/fielding_triangulation_eval.json (tools/fielding_triangulation_lab.py,
task EWAR_LADDER). Every number below is copied from that artifact. The row is
inserted after sdr_milb. Keeps the file's line endings and its one-space indent;
refuses when a plain round trip would rewrite the file. Running it twice changes
nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_fielding_triangulation.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
AFTER = "sdr_milb"

ROW = {
    "model_id": "fielding_triangulation",
    "summary": ("Failed its gate: a weighted blend of five fielding systems ranked next "
                "season's fielding runs +0.011 better than one system (interval -0.001 to "
                "+0.022). Not served."),
    "surface": "None: no page reads it, and it is not scored in the eWAR v3 skill look",
    "predicts": ("Next season's fielding runs per inning: per position, the best linear predictor "
                 "of a row's next-season FanGraphs fielding rate from the SDR, OAA, DRS, UZR and "
                 "FRP readings it has at its innings (one-factor model, weights fitted on 2016 to "
                 "2018 and frozen); catchers on framing and throwing, each shrunk"),
    "champion": ("none served; FanGraphs fielding stays the eWAR v3 frame's fielding and S3 stays "
                 "candidate part 6's only arm"),
    "baseline": ("A single fielding system that does not read the target's system (FRP on the DRS "
                 "and UZR legs, DRS on the Statcast leg); FanGraphs fielding (Fld + Frm) on the club "
                 "leg; SDR alone, S3, an equal-weight blend and B-Ref rfield as references"),
    "metric": ("Pre-registered: L1 the mean of three Spearman gaps on next-season fielding runs from "
               "a system left out (DRS with UZR, Statcast, UZR), L2 next-season club runs allowed "
               "beyond FIP from roster-weighted sums; each must beat its comparator at a "
               "player-clustered LB95 with Holm k 2 and a failing twin"),
    "eval_artifact": "data/fielding_triangulation_eval.json",
    "verdict": "provisional",
    "provisional_kind": "measured_not_adopted",
    "last_checked": "2026-10-16",
    "stale": False,
    "artifact_age_days": 0,
    "notes": (
        "Registered 2026-10-16 in docs/ewar/FIELDING_TRIANGULATION_GATE.md (task EWAR_LADDER, owner "
        "decisions EW3-18, EW3-20 and its UZR amendment, EW3-23), committed alone before any number, "
        "with EBR_GATE.md 11.5 registering the arm S3t of eWAR v3 candidate part 6; amended before "
        "the read (A1: every rate centred within position and season) and after the fit with one "
        "recorded fact (A2: FanGraphs' catcher blocking is zero in 2016 and 2017, so blocking "
        "carries no weight). Fit once on data seasons 2016 to 2018 "
        "(data/_labs/fielding_triangulation_fit.json). Read once 2026-10-16, OWNER-WAIVED EARLY READ "
        "(EW3-5), predictor seasons 2019 to 2025, B 2,000, seed 20261016. FAIL: L1 gap +0.0107 "
        "(LB95 -0.0005, p 0.030 against a Holm threshold 0.025; 1,227 pairs; DRS +0.0067, Statcast "
        "+0.0040, UZR +0.0215); L2 0.2831 against FanGraphs fielding 0.2329, gap +0.0503 (LB95 "
        "-0.0251, 210 club pairs), not non-inferior under the club bootstrap; both twins fail. S3t "
        "is not eligible for the skill look. Reported: SDR alone minus the triangulation -0.0124 "
        "(-0.0235 to -0.0016); the triangulation minus S3 +0.0026 (-0.0111 to +0.0170); the "
        "triangulation minus an equal-weight blend +0.0289 (+0.0114 to +0.0459); catchers' "
        "components against the base's catcher fielding -0.0337 (-0.0621 to -0.0074). Weight "
        "leaders at 1,000 innings: OAA in LF (0.80), FRP in CF (0.52) and 3B (0.43), SDR in RF "
        "(0.47), SDR and DRS at SS. Not served; enters no WAR."
    ),
}


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))

    def render(d) -> bytes:
        text = json.dumps(d, indent=1, ensure_ascii=False)
        if crlf:
            text = text.replace("\n", "\r\n")
        if raw.endswith(b"\n"):
            text += "\r\n" if crlf else "\n"
        return text.encode("utf-8")

    if render(doc) != raw:
        print("refusing: a plain round trip would rewrite data/model_registry.json")
        return 2
    ids = [r["model_id"] for r in doc["models"]]
    if ROW["model_id"] in ids:
        row = doc["models"][ids.index(ROW["model_id"])]
        changed = [k for k, v in ROW.items() if row.get(k) != v]
        if not changed:
            print("registry already carries fielding_triangulation; nothing written")
            return 0
        row.update(ROW)
    else:
        if AFTER not in ids:
            print(f"refusing: no {AFTER} row")
            return 2
        doc["models"].insert(ids.index(AFTER) + 1, dict(ROW))
        changed = ["inserted"]
    REG.write_bytes(render(doc))
    print("registry written: " + ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
