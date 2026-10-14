"""Register the prospect stat-line row in data/model_registry.json (idempotent).

Writes, once, the row docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md names
for TL_11_STATLINE_BUILD_DARK: mlb_projections_prospects_statline, status
"registered, development read only". No eval artifact yet: the look's artifact
data/prospect_statline_eval.json is written by TL_17 and ships; the development
read lives at data/_labs/prospect_statline_dev.json, which ships in neither deploy
consumer. Keeps the file's line endings and its one-space indent. Running it twice
changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_prospect_statline_row.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
GATE = "docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md"

ROW = {
    "model_id": "mlb_projections_prospects_statline",
    "summary": "Registered, development read only: the prospect arrival line (first-three-season rates with bands, conditional on reaching MLB); one look on holdout H decides; nothing served reads it.",
    "surface": "None served: prospect_statline.py behind proj_export.SERVE_PROSPECT_STATLINE (default False; on, it writes only under .cache/prospect_statline/preview/). TL_18 would serve the stats that pass on /projections/ prospect rows and the PROSPX card under owner answer TL-Q6 (a); the WAR cell stays the FV-anchored path",
    "predicts": "Per debuted player, pooled over his first three MLB seasons: hitters K%, BB%, ISO, AVG, BABIP, wOBA, xwOBA; pitchers K%, BB%, HR per BF, BABIP against, xwOBA against (150 PA or BF per rate); first-three-season WAR assembled through proj_components on FanGraphs' frame from the point predictions, never a sum of quantile points",
    "champion": "none - registered, not read on holdout H. Per stat and side a stacked ridge (level 0: TIP_first and TIP_now from tool_implied tables fit inside each fold, the milb_translation estimator refit per fold, level-relative ISO and BABIP, efv_proxy's estimator refit backward per fold, the aging v2 component delta to 27; level 1: a weighted ridge with an intercept and missing indicators, penalty by nested forward-chained CV on 10 ** k, k = -3 to 3 by 0.5, ties to the larger penalty); P10 to P90 from the inner chain's out-of-fold residuals",
    "baseline": "B0 the league-average rookie line by side and position group; B1 the translation alone (K%, BB%); B2 TIP_first alone (hitter ISO, AVG, BABIP); B3 the backward-refit proxy alone (xwOBA); INC the served FV-anchored path (prospect_path._baseline_first3 at the as-of consensus FV, one continuous number) for WAR",
    "metric": "Registered, not computed on the holdout: L1 per stat and side the exposure-weighted MAE of the model against the best baseline on identical rows, d with a player-clustered paired bootstrap (B 2000, seed 20261210, within side and debut cohort), one-sided lower bound, Holm within each side's family (m 7 hitters, m 5 pitchers), P10 to P90 coverage in [0.75, 0.85] as a veto; L2 WAR MAE and within-(side, cohort) Spearman against INC with both lower bounds above 0 and the calibration slope not further from 1",
    "eval_artifact": None,
    "verdict": "unvalidated",
    "registration_status": "registered, development read only",
    "notes": (
        "Registered 2026-10-09 in docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md (TL_3; owner ask of 2026-10-01, message 1; PLAN Part 9 section 9.4.6; "
        "owner answer TL-Q6 arrival line on both pages; unifier amendments U2 to U6: every label is FanGraphs' WAR from the frozen vintage 2026-10-02-0341299c20ec and the WAR leg stays on FanGraphs' frame). "
        "Row written 2026-10-14 by TL_11_STATLINE_BUILD_DARK with the build (prospect_statline.py, test_prospect_statline.py) and the ONE development read, "
        "data/_labs/prospect_statline_dev.json (role development; debut cohorts 2017 to 2021, scored 2019, 2020 and 2021 forward-chained, the spent WS-7 cohorts of gate 0.1, so it decides nothing). "
        "Frames: holdout H (debut cohorts 2022 to 2024) is read once by TL_17_STATLINE_LOOK under gate Part 9's day rule and raises in development mode; R-VM (2025 and later) raises in every mode. "
        "No table fit by look P, T or W, no served milb_translation or efv_proxy fit and no table of data/tool_grade_tables.json is an input or a baseline (gate 0.2, 0.3); test_prospect_statline.py scans the module. "
        "No statistic is cut by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md): the strata are side, debut age band, position group and last pre-debut level. "
        "Survivorship: every number is accuracy among debuts, conditional on reaching MLB. Nothing served moves."
    ),
}


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    cur = by_id.get(ROW["model_id"])
    if cur == ROW:
        print("registry already carries mlb_projections_prospects_statline; nothing written")
        return 0
    if cur is not None:
        # the row exists with older text: replace it in place (still idempotent)
        rows[rows.index(cur)] = dict(ROW)
        what = "registry row replaced"
    else:
        # insert after mlb_projections_prospects so the prospect rows sit together
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == "mlb_projections_prospects"),
                   len(rows) - 1)
        rows.insert(idx + 1, dict(ROW))
        what = "registry written"
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print(f"{what}: mlb_projections_prospects_statline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
