"""Record the 2026-10-15 SDR gate reads on the sdr_mlb and sdr_milb rows of
data/model_registry.json (idempotent).

The reads are docs/sdr-2026-08-18/SDR_EVAL_GATE.md (G-A, FAIL) and
MILB_SDR_EVAL_GATE.md (G-C, NOT RUN), artifacts data/sdr_eval.json and
data/milb_sdr_eval.json (tools/sdr_eval_gate.py, task EWAR_SDR_INHOUSE). Every
number below is copied from those artifacts. Keeps the file's line endings and
its one-space indent; refuses when a plain round trip would rewrite the file.
Running it twice changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_sdr_eval_rows.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"

UPDATES = {
    "sdr_mlb": {
        "summary": ("Measured, failed its gate: in-house SDR persisted year to year less "
                    "than OAA (0.403 vs 0.470, 1,644 pairs) and tracked next-season club runs "
                    "allowed less than rfield (0.150 vs 0.181)."),
        "surface": "None: no page reads SDR; the gate failed, so nothing is served",
        "predicts": ("MLB fielding value in runs per player-season-position: Will Cahoon's "
                     "Defense+ composite (06_total_defense_plus: reliability-weighted OAA, DRS "
                     "and FRP z-blend, innings-shrunk), run in-house on public FanGraphs and "
                     "Savant inputs, 2017 to 2026"),
        "champion": ("none served; B-Ref rfield stays the eWAR v2 fielding source and the "
                     "candidate failed G-A"),
        "baseline": ("B-Ref rfield and FanGraphs-hosted Savant OAA on identical player-season "
                     "pairs; FG Defense, UZR and the prospect-frame baselines as context only"),
        "metric": ("Pre-registered: year-to-year Spearman (C1) and next-season club runs "
                   "allowed beyond FIP (C2), beating both baselines at player-clustered LB95, "
                   "Holm, noise twins; EW3-23 leave-one-system-out leg (C5)"),
        "verdict": "provisional",
        "provisional_kind": "measured_not_adopted",
        "notes": (
            "REGISTERED 2026-08-18 as a data-blocked stub. READ 2026-10-15, OWNER-WAIVED EARLY READ "
            "(EW3-5), task EWAR_SDR_INHOUSE (owner decision EW3-18): Will's method run in-house by "
            "tools/sdr_inhouse.py on public inputs fetched into .cache/sdr (his files copied byte for "
            "byte, config patch for the season window only); drop accepted by sdr_intake, census "
            "committed first; frame fixed by the gate's Amendment 2026-10-15 before the drop existed. "
            "Adapter receipt: his 2025 run reproduced (reliabilities FRP 0.515, OAA 0.469, DRS 0.400 vs "
            "his .52/.47/.40). G-A FAIL: C1 self-persistence SDR 0.4031, rfield 0.3809, OAA 0.4696 "
            "(1,644 pairs, d -0.0665, LB95 -0.1055); C2 club runs allowed beyond FIP SDR 0.1499, "
            "rfield 0.1808, OAA 0.1345 (270 pairs, d -0.0308, LB95 -0.0792); both twins fail. EW3-23 "
            "leg C5 UNRESOLVED (gap +0.0044, LB95 -0.0146); C6 on UZR(Y+1) SDR 0.2787, OAA 0.2736, "
            "rfield 0.2233 (LB95 -0.0248). Per position (reported): catchers SDR 0.6145 vs rfield "
            "0.0248 (LB95 +0.451); SDR leads OAA at the point at six of seven other positions, none "
            "at LB95. Post-hoc, deciding nothing: the pooled OAA rate carries position-mean "
            "differences; centred within position-season SDR 0.3994, OAA 0.3823, rfield 0.3516. "
            "Not served; does not enter eWAR on this gate."
        ),
        "last_checked": "2026-10-15",
        "stale": False,
        "artifact_age_days": 0,
    },
    "sdr_milb": {
        "summary": ("Not run: Will's method emits no MiLB defensive runs (15 is position "
                    "history, 26 a grade prior), so no pre-debut MiLB SDR exists to score."),
        "champion": ("none served; the in-house drop holds no MiLB rows (census 2026-10-15: "
                     "3,466 rows, all MLB)"),
        "notes": (
            "REGISTERED 2026-08-18, DATA-BLOCKED. 2026-10-15 (task EWAR_SDR_INHOUSE, OWNER-WAIVED "
            "EARLY READ): G-C recorded NOT RUN under the gate's Amendment 2026-10-15 rule, fixed "
            "before the drop existed: the census holds 0 MiLB rows because 15_milb_translation "
            "measures position history only and 26_prospect_prior is a scouting-grade and "
            "body-frame prior, not a minor-league measurement. Not a finding that MiLB SDR fails to "
            "predict. data/milb_sdr_eval.json carries the census and Will's 15 run in-house as "
            "descriptive context (487 usable; AAA position held in MLB: C 96.5%, CF 69.3%, 3B "
            "62.7%, 2B 59.1%, SS 53.9%). Three standing refutations of defense-into-eFV (tool_field, "
            "Defense+ prior, prospect_def_value) stay on the record. Measurement only."
        ),
        "last_checked": "2026-10-15",
        "stale": False,
        "artifact_age_days": 0,
    },
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
    by_id = {r["model_id"]: r for r in doc["models"]}
    changed = []
    for mid, upd in UPDATES.items():
        row = by_id.get(mid)
        if row is None:
            print(f"refusing: no {mid} row")
            return 2
        for k, v in upd.items():
            if row.get(k) != v:
                row[k] = v
                changed.append(f"{mid}.{k}")
    if not changed:
        print("registry already carries the 2026-10-15 SDR reads; nothing written")
        return 0
    REG.write_bytes(render(doc))
    print("registry written: " + ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
