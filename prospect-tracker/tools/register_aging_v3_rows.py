"""Register the aging v3 rows in data/model_registry.json (idempotent).

Writes, once, the three rows docs/AGING_V3_GATE.md section 16 names, each
"registered, not read" with no eval artifact (the artifact names are in the
notes; a row carries one only after its look), re-points the fa_aging_curves
row's notes at the gate and says data/fa_aging_curves.json is a documentation
snapshot not read at run time, and names the call-scoped v2 pin of the ML
features in fa_war_paths_decay's notes. Keeps the file's line endings (CRLF)
and its one-space indent. Running it twice changes nothing.

    python tools/register_aging_v3_rows.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
REGISTERED = "2026-10-09"
GATE = "docs/AGING_V3_GATE.md"

ROWS = [
    {
        "model_id": "aging_v3",
        "summary": "Registered, not read: the aging v3 ladder (playing time, rate estimator, position buckets, archetypes) against the v2 champion, one look after the DEV artifact lands. Nothing served moves.",
        "surface": "None served: aging_v3.py built dark behind fa_config.yaml aging_v3.consumers (all false); every consumer door selects aging=\"v2\" until a pass is recorded",
        "predicts": "The champion engine's expected WAR in seasons B to B+4 for a player-side line observable at the end of season B-1, under an aging configuration (arms T, S, P, R)",
        "champion": "none - registered, not read: four arms as configurations of one service, adjudicated in the fixed order T, S, P, R, each against the composition of the arms already passed (the comparator of section 4 for T)",
        "baseline": "The v2 champion curves refit point-in-time per base on the same corpus and rows, with the PT cap computed call-scoped (owner answer AG-Q5 'Fix both now'); gated by registration",
        "metric": "Registered, not computed: ACAL over 10 age-band by side cells on the GATE frame (label seasons 2011-2013, fWAR), player-cluster bootstrap B 2000 seed 20261124, PASS p < 0.0125 per arm with guards G1 to G4; TIER-2 and CONFIRM veto only",
        "eval_artifact": None,
        "verdict": "unvalidated",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-08 in docs/AGING_V3_GATE.md (owner ask 2026-10-01, PLAN section 9.3 'Aging v3 (the one aging service)'; "
            "owner answers AG-Q1 seven hitter buckets C, SS, 2B/3B, CF, LF/RF, 1B, DH plus SP and RP; AG-Q2 two archetype families per side, out of window; AG-Q5 'Fix both now'). "
            "Row written 2026-10-09 by AG_5_AGING_SERVICE_BUILD_DARK with the dark build: aging_v3.py (fit, AgingModel: rate_delta, pt_next, level, shape, factor, component_curve, meta), "
            "aging_v3_sidecar.py (.cache/aging_v3_sidecar_{first}_{last}_{sig}.pkl keyed by (mlbam, season): StatsAPI positions and counts, the frozen vintage's run parts, IL features through tools/pt_risk_lab.py, data/tj_surgery.json), "
            "call-scoped selectors default \"v2\" on fa_projection.fitted_models, fa_market.contract_war_path and _decay_path, value_framework._trajectory_shape, prospect_prime_path and prospect_peak_war, bayes_trade_value._aging_factor; "
            "proj_ml.build_features and proj_eval pass aging=\"v2\" explicitly. NO arm is active by default: under the default config the service reproduces v2 exactly (test_aging_v3.py), "
            "and with every consumer flag false the served payloads are byte-identical (test_aging_v3_byte_identity.py). The fit cache is versioned, never deleted: "
            ".cache/aging_v3_fits_{max_season}_{first}_{last}_{sig}_{AGING_V3_VERSION}_{cfg8}.pkl. Frames: DEV 2008-2010, GATE 2011-2013, TIER-2 2014-2025 (2020 masked), CONFIRM 2026, on the fWAR corpus (war_provider fwar, seasons 2000-2026). "
            "Artifacts, none existing yet: data/aging_v3_mde.json (AG_6, DEV only), data/aging_v3_eval.json (AG_7, the look), data/aging_v3_curves.json (the flip's committed full fit). "
            "The look is the first free day after AG_6 lands (gate section 13, owner decision EPOCH-NOW); the component curves K%, BB%, ISO, BABIP and HR never change under any arm."
        ),
    },
    {
        "model_id": "aging_v3_prospect_shape",
        "summary": "Registered, not read: the v3 prospect shape against the incumbent tent on corpus debut cohorts 2014-2018, read in the ladder's session. Nothing served moves.",
        "surface": "None served: AgingModel.shape() behind the prospect_surplus and proj_display flags (false); value_framework._trajectory_shape keeps the tent until a pass is recorded",
        "predicts": "The within-window timing of a debutant's WAR (mean 1.0 over the control window; the FV anchors keep every level) from the debut age and the position bucket",
        "champion": "none - registered, not read: aging_v3.shape(), level() times the regular-tier PT curve renormalized to mean 1.0, bucket from the debut-season position, never an archetype",
        "baseline": "The incumbent tent value_framework._trajectory_shape (climb 0.04 to the peak, decline 0.07 past it, floor 0.25), both fit point-in-time through d-1; gated by registration",
        "metric": "Registered, not computed: mean paired SSE_inc minus SSE_v3 of the level-free fit per player on debut cohorts 2014-2018 (seasons d to d+6, 2020 masked), player bootstrap B 2000 seed 20261124, one-sided lo95 > 0, with debut-age and bucket guards",
        "eval_artifact": None,
        "verdict": "unvalidated",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-08 in docs/AGING_V3_GATE.md section 9 (PS); row written 2026-10-09 by AG_5_AGING_SERVICE_BUILD_DARK with the dark build. "
            "Population from the corpus itself (first MLB season with exposure, 2001 or later); no FV, grade, list vintage or prospect database row is read and no statistic is computed by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md); "
            "cohorts 2020, 2021, 2025 and 2026 are never read. Prospects get a bucket only (board position; C/1B reads its first token; SIRP and RP read RP), never an archetype and never a health term. "
            "Its verdict holds only for the composition it scored: a TIER-2 or CONFIRM veto that changes the composition records 'composition withdrawn' and the prospect consumers stay off. "
            "Artifact at the look: data/aging_v3_eval.json (AG_7), none existing yet."
        ),
    },
    {
        "model_id": "aging_v3_health",
        "summary": "Registered, not read: a playing-time hazard on IL and Tommy John history, read at its own look after the ladder's record. A null is the likely outcome.",
        "surface": "None served: the health multiplier inside AgingModel.pt_next behind fa_config.yaml aging_v3.health (false); the rate is never touched",
        "predicts": "Next-season exposure (PA, or IP x 4.3 for pitchers) through pt_next *= exp(gamma . z), clipped to [0.80, 1.05] and recentred within each season so the league's projected exposure is unchanged",
        "champion": "none - registered, not read: ridge (alpha 1.0, z-features, no intercept) on IL days, IL stints and 60-day placements over t-2..t, tj_prior (pitchers) and age x IL days, each z-scored within its season",
        "baseline": "The ladder's accepted composition alone, same rows; gated by registration",
        "metric": "Registered, not computed: paired exposure MAE over h1-h3 (DEV 2011-2014 for the fit, GATE 2015-2018, CONFIRM 2026), player-cluster bootstrap B 2000 seed 20261124, lo95 of the MAE reduction > 0; guards: h1-h3 WAR MAE upper bound <= +0.003, per-season league exposure drift < 1 percent, CONFIRM not reversed",
        "eval_artifact": None,
        "verdict": "unvalidated",
        "registration_status": "registered, not read",
        "notes": (
            "Registered 2026-10-08 in docs/AGING_V3_GATE.md section 10 (owner answer AG-Q3 'Register, read 2027-01-12'; the day is now the condition of section 13: the first free day after the ladder's record); "
            "row written 2026-10-09 by AG_5_AGING_SERVICE_BUILD_DARK with the dark build. Features come from the league transactions cache .cache/mlb_transactions/ (2008 onward, refreshed to the current month by tools/pt_risk_lab.py's own fetch code, never on a look day) "
            "through that lab's reconstruction and stint-truncation rules (a-priori choices 3 and 4, imported, not copied) and data/tj_surgery.json; a cell enters only if its feature window t-2..t lies inside the coverage (bases 2011 and later). "
            "Prior: W1 PT-RISK (data/fa_pt_risk_eval.json, 2026-07-23) failed out of sample, dev gain 2.84 PA of 164 (1.7 percent); the within-season z-scores are the era fix. "
            "Artifact at the look: data/aging_v3_eval.json (AG_13), none existing yet. The health flag stays false until the H record exists."
        ),
    },
]

FA_AGING_CURVES_NOTE = (
    " AGING V3 (2026-10-09, AG_5_AGING_SERVICE_BUILD_DARK): the registered successor is aging_v3 "
    "(docs/AGING_V3_GATE.md; registry rows aging_v3, aging_v3_prospect_shape, aging_v3_health), built dark with "
    "every consumer flag false; this row's curves stay the served engine until that gate records a pass. "
    "data/fa_aging_curves.json is a DOCUMENTATION SNAPSHOT, not read at run time: regenerated once on 2026-10-09 "
    "from the incumbent v2 fit on the fwar corpus (seasons 2000-2026) with that note in its meta; the served curves "
    "are refit live from the corpus-keyed cache as before."
)

FA_WAR_PATHS_NOTE = (
    " AGING V2 PIN (2026-10-09, AG_5_AGING_SERVICE_BUILD_DARK): proj_ml.build_features and proj_eval pass "
    "aging=\"v2\" explicitly to fa_projection.fitted_models and fa_market.contract_war_path, the call-scoped "
    "selector aging v3 added (docs/AGING_V3_GATE.md section 2, train/serve parity: the heads were trained on v2 "
    "champion features); the ML path adopts v3 only through the 2027 forward read (AG_14 to AG_16, owner answer AG-Q7)."
)


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
        # insert after fa_aging_curves so the aging rows sit together
        idx = next((i for i, r in enumerate(rows) if r["model_id"] == "fa_aging_curves"), len(rows) - 1)
        rows.insert(idx + 1 + len(changed), dict(row))
        changed.append(row["model_id"])
    fac = by_id.get("fa_aging_curves")
    if fac is not None and "AGING V3 (2026-10-09" not in fac["notes"]:
        fac["notes"] = fac["notes"].rstrip() + FA_AGING_CURVES_NOTE
        changed.append("fa_aging_curves notes")
    fwp = by_id.get("fa_war_paths_decay")
    if fwp is not None and "AGING V2 PIN (2026-10-09" not in fwp["notes"]:
        fwp["notes"] = fwp["notes"].rstrip() + FA_WAR_PATHS_NOTE
        changed.append("fa_war_paths_decay notes")
    if not changed:
        print("registry already carries the aging v3 rows; nothing written")
        return 0
    # the file carries no trailing newline; json.dumps adds none
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print("registry written:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
