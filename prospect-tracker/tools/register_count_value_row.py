"""Register the RE288 count-state run value row in data/model_registry.json (idempotent).

Writes, once, the row docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md part 8 names:
count_value, verdict provisional, provisional_kind measurement_only, eval_artifact
data/count_value.json (built by tools/build_count_value.py). Keeps the file's line
endings and its one-space indent; refuses when a plain round trip would rewrite the file.
Running it twice changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_count_value_row.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
AFTER = "win_expectancy_state"

ROW = {
    "model_id": "count_value",
    "summary": "Measured, not a prediction: RE288 run expectancy by count, bases and outs, 2018 to 2026 (2020 absent); every invariant passed on the third build after two refusals.",
    "surface": "None served: no page reads it. data/count_value.json is the run basis for later registered work (eABS challenge values, pitch economy, framing, swing decisions)",
    "predicts": "Nothing: the mean runs scored from a pitch to the end of its half-inning, by balls, strikes, base occupancy and outs (288 cells per MLB season), a descriptive table",
    "champion": "none. RE288_s = RE24_s (eBR's ebr_v1 table) + lambda_s x a pooled count departure, the departure measured against RE24 of the play's end state (gate parts 3, 11.1 and 11.2)",
    "baseline": "eBR's RE24 at count 0-0: invariant 1 bounds the 0-0 row within 0.03 runs per base-out cell and 0.01 weighted",
    "metric": "Refusing invariants and receipts, no forward statistic: 0-0 row against RE24; monotone in balls (up) and strikes (down) at fixed base-out; per-event values summing to each play's RE24 change; index, count and runs agreement with the runner record at 0.999 or better",
    "eval_artifact": "data/count_value.json",
    "verdict": "provisional",
    "provisional_kind": "measurement_only",
    "notes": (
        "Registered 2026-10-15 in docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md (task EWAR_P1_RE288, the ewar-map plan P1, owner decisions EW3-16 to EW3-19), "
        "committed alone before any number. Build: count_value.py (pure core) and tools/build_count_value.py over the corpus pitches and events and the eBR runner record, "
        "seasons 2018, 2019 and 2021 to 2026, about 5.47 million fit-set pitch observations. "
        "Two builds refused first and are disclosed in the gate: run 1 (the direct estimator on runs to the end of the half-inning, K 500) reversed count steps in the pool and in every season "
        "and missed the 0-0 bound in six seasons; run 2 (the 11.1 departure against RE24 of the play's end state, per-season shrink, K 1202.6) left the pool monotone but reversed six count "
        "steps in five seasons (up to 0.0134 runs) and missed the 0-0 bound in 2022 and 2023. "
        "Run 3 applies the default of owner question RE288-Q1 (gate 11.2): the count departure is pooled over 2018 to 2026 (frozen pool sha256 560b9f3c895c, K 1202.6) and each season keeps "
        "its run environment through RE24_s and eBR's frozen lambda; every invariant passes in every season (0 count reversals; 0-0 per-cell max 0.0207 to 0.0228, weighted 0.0017 to 0.0019; "
        "per-event values sum to the RE24 change on every fit-set play; R1 index and R3 runs 1.0, R2 count 0.9999 or better). The other RE288-Q1 options are (b) an isotonic projection of "
        "per-season tables, (c) reporting instead of refusing, (d) leaving RE288 refused. Pooled count values against 0-0, read 2026-10-15: 3-0 +0.206, 0-2 -0.098 runs. "
        "No player, team or umpire value is computed; no year-to-year or forward statistic; nothing served moves."
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
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    cur = by_id.get(ROW["model_id"])
    if cur == ROW:
        print("registry already carries count_value; nothing written")
        return 0
    if cur is not None:
        rows[rows.index(cur)] = dict(ROW)
        what = "registry row replaced"
    else:
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == AFTER), len(rows) - 1)
        rows.insert(idx + 1, dict(ROW))
        what = "registry written"
    REG.write_bytes(render(doc))
    print(f"{what}: count_value")
    return 0


if __name__ == "__main__":
    sys.exit(main())
