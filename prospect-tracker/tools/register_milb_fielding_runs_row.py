"""Add the milb_fielding_runs row to data/model_registry.json (idempotent).

The read is docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md (task MILB_FIELDING_RUNS, owner
decision EW3-33), artifact data/milb_fielding_runs_eval.json (tools/milb_fielding_runs.py).
Every number below is copied from that artifact. Keeps the file's line endings and its
one-space indent; refuses when a plain round trip would rewrite the file. Running it twice
changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_milb_fielding_runs_row.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"

ROW = {
    "model_id": "milb_fielding_runs",
    "summary": ("Pre-debut MiLB fielding runs rank later MLB fielding: Spearman 0.256 with "
                "rfield (203 debuts, LB95 0.107) and 0.198 with OAA (164, LB95 0.033). "
                "Provisional."),
    "surface": ("PROSPX prospect pages, the MiLB fielding runs block (by position, "
                "AAA-equivalent runs per 1,000 innings, reliability, levels), from "
                "data/milb_fielding_runs.json"),
    "predicts": ("MiLB fielding in runs per inning from StatsAPI play-by-play fielder credits "
                 "2021 to 2026 (expected outs by trajectory, direction, distance and level; "
                 "double plays, outfield arm, catcher framing on tracked pitches and throwing), "
                 "level-centred, shrunk by split-half reliability and chained to "
                 "AAA-equivalent; read against MLB fielding runs after debut"),
    "champion": ("MFR served as a descriptive MiLB fielding reading; it enters no eFV, eWAR or "
                 "projection number (the eFV driver read is development only)"),
    "baseline": ("Zero (LB95 above 0), a fielder-shuffled and a within-position permuted null, "
                 "planted recovery; the consensus field grade for the incremental leg"),
    "metric": ("Pre-registered, read once: (a) MiLB year-to-year Spearman; (b) pre-debut MFR "
               "vs B-Ref rfield and OAA per 1,000 MLB innings, debuts 2022 to 2024, centred "
               "within position, player bootstrap, Holm over two targets; (c) rank partial "
               "given the field grade"),
    "eval_artifact": "data/milb_fielding_runs_eval.json",
    "verdict": "provisional",
    "provisional_kind": "shipped_partial_measurement",
    "notes": (
        "REGISTERED 2026-10-16 (docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md, commit 0ab2ed5f, "
        "alone, before any number); task MILB_FIELDING_RUNS, owner decision EW3-33 (SDR-MILB-Q1: "
        "build MiLB fielding runs). READ ONCE 2026-10-16, OWNER-WAIVED EARLY READ (EW3-5). Data: "
        "61,885 scheduled MiLB games 2021 to 2026 (AAA, AA, A+, A, ROK), 2,785,793 rated balls in "
        "play, census data/milb_fielding_runs_census.json. (a) PASS: persistence 0.2483 (5,471 "
        "pairs, LB95 0.2163) vs fielder-shuffled null -0.0050 (UB95 0.0369); planted recovery "
        "PASS. (b) PASS: T1 rfield 0.2559 (203, LB95 0.1073), T2 OAA 0.1980 (164, LB95 0.0330), "
        "both Holm; permuted null does not clear; planted rho 0.25 clears through T2. Reported: "
        "FRP 0.2138, DRS 0.2478, UZR to 2024 0.1358 (LB95 -0.0648). (c) UNDERPOWERED: partial "
        "given the field grade T1 0.2774 (174, LB95 0.1207), T2 0.1455 (LB95 -0.0248), but the "
        "planted check failed on both targets, so no claim that MFR adds to the field grade. "
        "Survivorship: (b) and (c) are among debuts with 300+ MLB innings. Level factors to "
        "AAA: AA 0.366, A+ 0.172, A 0.050, ROK 0.022. Supersedes EWAR_SDR_PROSPECT_DISPLAY "
        "(EW3-33)."
    ),
    "last_checked": "2026-10-16",
    "stale": False,
    "artifact_age_days": 0,
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
    rows = doc["models"]
    cur = next((r for r in rows if r.get("model_id") == ROW["model_id"]), None)
    if cur == ROW:
        print("registry already carries milb_fielding_runs; nothing written")
        return 0
    if cur is None:
        rows.append(dict(ROW))
    else:
        cur.clear()
        cur.update(ROW)
    REG.write_bytes(render(doc))
    print("registry written: milb_fielding_runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
