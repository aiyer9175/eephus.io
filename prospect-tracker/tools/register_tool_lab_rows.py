"""Register the tool lab rows in data/model_registry.json (idempotent).

Writes, once, the three rows docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md
names for TL_4_TOOL_LAB_BUILD: tool_implied_production (provisional, registered
and not read), tool_source_accuracy (registered, not read; it supersedes
ba_tool_grade_weight at look W) and power_composite_v2 (registered, not read).
No row carries an eval artifact yet: data/power_composite_eval.json and
data/tool_accuracy_eval.json are written by the looks (TL_5, TL_12) and are
registry eval artifacts that ship, never listed in deploy/data_exclude.txt.
Keeps the file's line endings (CRLF) and its one-space indent. Running it twice
changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_tool_lab_rows.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
REGISTERED = "2026-10-14"
GATE = "docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md"

ROWS = [
    {
        "model_id": "tool_implied_production",
        "summary": "Provisional and not read: grade-to-stat tables (TIP) for the tool framework, fit per use on declared rows; nothing served reads them.",
        "surface": "None served: tool_implied.py (fit_tables, tip_mat, tip_f3, tip_now, tip_level, tip_first) read by tools/tool_accuracy_lab.py and the stat-line model's registration; no page, exporter or scoring path reads a table",
        "predicts": "The MLB stat a tool grade implies (hit to K% and AVG, game power to ISO, raw power to exit velocity, speed to sprint speed and SB, field to OAA, throw to arm strength, fb to K%, cmd to BB%): per-grade-bin medians, thin bins dropped, PAVA-smoothed, interpolated, flat beyond the last non-thin bin",
        "champion": "none - a measurement table, a pure function of the rows it is fit on; a table never scores a row of its own fit set, and no table in data/tool_grade_tables.json scores a row here",
        "baseline": "The published FanGraphs-framework estimates (docs/reference/FANGRAPHS_FV_FRAMEWORK.md Part 2), read at look T (gate Part T)",
        "metric": "Registered, not computed: tool above grade (TAG) per debuted player, source and tool: the gap to TIP_f3, the mid-rank percentile in the grade bin and the regressed gap with k_m from the gate's Part 4 (split-half reliability on MLB 2018 and 2019 player-seasons, the window's seasons on disk)",
        "eval_artifact": None,
        "verdict": "provisional",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-09 in docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part 1.2 (owner asks 2026-10-01, PLAN Part 9 section 9.4.2; "
            "owner answers TL-Q2 K% primary for hit, TL-Q4 PWR means production power). Row written 2026-10-14 by TL_4_TOOL_LAB_BUILD with the build: "
            "tool_implied.py (bins round(g / 5) * 5, THIN_N 15, weighted PAVA oriented by the stat's sign, no extrapolation), tip_level built point in time per vintage V "
            "(level norms with an explicit as-of date of December 31 of V - 1, the within-player AAA-minus-MLB offset on seasons up to V - 1, never the artifact's concurrent offset; "
            "raises on any input season at or after V or 2026 or later), tip_first a hook on aging_v3.AgingModel.component_curve with aging v2 (raises ServiceMissing without the service). "
            "Part 4's k_m constants were measured by tools/tool_accuracy_lab.py --k-m on the per-event caches (.cache/pbp_corpus, .cache/pbp_runners) for 2018 and 2019, the only seasons of the 2015 to 2019 window on disk; "
            "sprint speed, OAA, arm strength and barrels are NOT COMPUTABLE (no per-event data for the window), so their regressed TAG is not computed. "
            "No FV cell is read, grouped or labelled anywhere (docs/PROSPECT_ANCHOR_GATE.md); the bins are tool grade bins. Nothing served moves."
        ),
    },
    {
        "model_id": "tool_source_accuracy",
        "summary": "Registered, not read: per-source tool grade accuracy (ordering, bias, error) and whether an accuracy-weighted tool consensus beats the equal mean, one look. Equal weight retains until then.",
        "surface": "None served: tools/tool_accuracy_lab.py --look W; a passing tool's weighted grade would live on the separate key tools_consensus_w (TL_13) and the Source Accuracy Tools tab (TL_14), both dark until the look",
        "predicts": "Whether the within-board-year ordering of a tool's realized MLB stat (hit to K%, speed to sprint speed, field to OAA per 1,000 innings, throw to arm strength) by an accuracy-weighted consensus beats the equal mean by more than the test resolves",
        "champion": "none - registered, not read: BA2's estimator imported by name (MIN_LAG_YEARS 3, WEIGHT_SHRINK_K 150, WEIGHT_CLAMP 0.6 to 1.5, SPEARMAN_FLOOR 0.05), gate G1 to G5, Holm m = 4 on the permutation p",
        "baseline": "The equal (unweighted) tool consensus of consensus.py on the common set; the permuted-source-label floor (1,000 draws); the player-clustered paired bootstrap B 2000 at seeds 8641 and 1337",
        "metric": "Registered, not computed: d = weighted minus equal within-board-year Spearman per tool on board years 2017 to 2024 (debut year at most 2024, outcomes through 2026), PASS when G1 to G5 hold on arm A and Holm survives; secondaries (game_pwr to ISO, fb to K%, cmd to BB%, hit to AVG, speed to SB) descriptive only, BA2's verdicts stand",
        "eval_artifact": None,
        "verdict": "unvalidated",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-09 in docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part W (PLAN Part 9 section 9.4.3; owner answers TL-Q2 and TL-Q5). "
            "Row written 2026-10-14 by TL_4_TOOL_LAB_BUILD with the build; the look is TL_12_TOOL_WEIGHTS_LOOK, once, under the gate's W.11 day rule, "
            "with --gate-sha (the REGISTERED commit) and --rlv-record (the R-LV record of Part 0.3, commit 1c73c420). "
            "SUPERSEDES ba_tool_grade_weight at look W: BA2's lane read board years 2020 to 2025 before the R-LV and R-VM reservations (gate Part 0.1), so its hit result "
            "may not be credited to any eFV V2 candidate; look W reads BA2's own board years again, and a hit PASS is not independent of BA2 (W.9). "
            "Artifact at the look: data/tool_accuracy_eval.json (a registry eval artifact that ships, never listed in deploy/data_exclude.txt); display copy only at "
            ".cache/tool_accuracy/preview/tool_source_accuracy.json. The dry run on fixtures with None values completed on 2026-10-14 (data/_labs/tool_accuracy/dryrun/). "
            "Arm B (adding Baseball America) is NULL by construction (earliest BA tool vintage 2023). A NULL is a finding: equal weight retains."
        ),
    },
    {
        "model_id": "power_composite_v2",
        "summary": "Registered, not read: the PWR composite candidates (game only; a weighted game and raw blend) against the served mean on realized ISO, one look. C0 retains until then.",
        "surface": "None served: tools/tool_accuracy_lab.py --look P; the winner would be built behind POWER_COMPOSITE_MODE (TL_6, default off) and served by TL_7 under TL-Q4",
        "predicts": "Realized MLB ISO over the first three seasons after the board year (300 PA pooled), ordered within board year by C0 round-half(mean(game, raw)), C1 the game consensus, C2 round-half(a game + (1 - a) raw) with a cross-fit player-disjoint on the grid 0.0 to 1.0",
        "champion": "none - registered, not read: the served v12 formula (consensus.py) is C0 and retains unless C1 or C2 passes",
        "baseline": "C0; the swap floor (game and raw swapped with probability 0.5 per row, 1,000 draws, the whole pipeline rerun); the player-clustered paired bootstrap B 2000 seed 20261021; the top-tercile AUC veto",
        "metric": "Registered, not computed: d = within-board-year Spearman of the candidate minus C0 on identical rows (board years 2017 to 2019 and 2022 to 2024, debut year at most 2024); PASS needs lo95 above 0, d at least 2 times the floor, no AUC veto and Holm across C1 and C2; secondaries HR per PA, barrels per PA and exit velocity never decide",
        "eval_artifact": None,
        "verdict": "unvalidated",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-09 in docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part P (owner message 1 of 2026-10-01, PLAN Part 9 section 9.4.4; owner answer TL-Q4 production power). "
            "Row written 2026-10-14 by TL_4_TOOL_LAB_BUILD with the build; the look is TL_5_POWER_COMPOSITE_LOOK, once, under the gate's P.10 day rule, with --gate-sha the REGISTERED commit. "
            "Board years 2020 and 2021 are out of look P by its own frame definition (owner question TL2-Q2). Prediction written before any number (P.9): C1 and C2 ahead of C0 by +0.01 to +0.03 rho on ISO, a near 0.7 to 1.0. "
            "Artifact at the look: data/power_composite_eval.json (a registry eval artifact that ships, never listed in deploy/data_exclude.txt). "
            "The dry run on fixtures with None values completed on 2026-10-14 (data/_labs/tool_accuracy/dryrun/). Neither verdict moves an eFV input (gate Part 7)."
        ),
    },
]


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    changed = []
    for row in ROWS:
        if row["model_id"] in by_id:
            continue
        # insert after tool_grade_tables so the tool rows sit together
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == "tool_grade_tables"), len(rows) - 1)
        rows.insert(idx + 1 + len(changed), dict(row))
        changed.append(row["model_id"])
    if not changed:
        print("registry already carries the tool lab rows; nothing written")
        return 0
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print("registry written:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
