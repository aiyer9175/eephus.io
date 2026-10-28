# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Re-derive the proj_def_prior and prospect_def_value registry rows from their eval
artifacts (task STALE_EVALS_REMEASURE, 2026-10-28).

Both rows quoted their 2026-06-29 headline numbers by hand (summary and notes). After a
re-measure the served claim must be read off the artifact, never typed, so this script:

  * rewrites each row's summary from the artifact when the model's own registered rule
    still holds (proj_def_prior: the pos_only variant reduces holdout pooled MAE without
    regressing the dev bases or the star slice; prospect_def_value: |Spearman| beats the
    FG grade and MAE_z is no worse). When a rule does NOT hold the summary and verdict
    are left exactly as registered and the paragraph says so: a verdict is changed by
    the owner, not by a refresh. EXCEPTION, answered: for proj_def_prior the owner
    ruled on 2026-10-28 (EVAL-Q, DECISIONS_FOR_OWNER.md, 'Downgrade to provisional')
    that a failed re-measure sets the verdict to provisional with provisional_kind
    shipped_partial_measurement, the feature staying in the model and nothing
    retrained; this script applies that answer (task EVAL_FOLLOWUPS_REFREEZE).
  * replaces the row's RE-MEASURED paragraph in notes (one per row, derived).
  * restamps last_checked / stale / artifact_age_days from model_registry.freshness().

Idempotent: a second run on the same day rewrites nothing. Keeps the file's line endings
and the registry's own json.dumps(indent=1) layout, and refuses to write if the file no
longer round-trips through that layout (so it can never reformat the registry).

Run: python tools/refresh_def_eval_registry_rows.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import model_registry as mr  # noqa: E402

REGISTRY = ROOT / "data" / "model_registry.json"
_PARA_RE = re.compile(r"\nRE-MEASURED \d{4}-\d{2}-\d{2} \(STALE_EVALS_REMEASURE[^\n]*")


def _proj_def_prior(row: dict, art: dict) -> bool:
    d = art["deltas_vs_baseline"]["pos_only"]
    base = art["variants"]["baseline"]["holdout"]
    hp, hs, dp, ds = d["holdout_pooled"], d["holdout_star"], d["dev_pooled"], d["dev_star"]
    rule = hp < 0 and dp <= 0 and hs <= 0
    stamp = art["evaluated_at"][:10]
    para = (
        f"\nRE-MEASURED {stamp} (STALE_EVALS_REMEASURE; same bases, variants and gate rule as "
        f"2026-06-29 on the corpus and training label of this date, horizon targets scored through "
        f"{art['scored_through']}; evaluated_at in data/proj_def_feature_eval.json): pos_only HOLDOUT "
        f"pooled {hp:+.4f} / star {hs:+.4f} against a baseline of {base['pooled_mae']:.4f} / "
        f"{base['pooled_star_mae']:.4f} (n {base['pooled_n']:,} / {base['pooled_star_n']:,}); dev "
        f"{dp:+.4f} / star {ds:+.4f}. Gate rule (reduce holdout pooled MAE without regressing the dev "
        f"bases or the star slice): {'HOLDS' if rule else 'DOES NOT HOLD. OWNER ANSWER 2026-10-28 (EVAL-Q, DECISIONS_FOR_OWNER.md): verdict provisional, provisional_kind shipped_partial_measurement; the 2026-06-29 ship on bWAR stands as the record of its day, the feature stays in the model and nothing is retrained'}."
    )
    if rule:
        row["summary"] = (f"Validated: the defensive prior cuts holdout hitter MAE {hp:.4f} and the "
                          f"star slice {hs:.4f}; a feature of the WAR-path model, not a separate model.")
    else:
        # The served claim may not say "cuts" when the artifact no longer shows it. The
        # verdict moves by the owner's 2026-10-28 answer (docstring): provisional, the
        # feature kept. provisional_kind sits beside verdict so the row reads in order.
        row["summary"] = (f"Provisional: shipped 2026-06-29 on its bWAR gate; re-measured {stamp} "
                          f"on fWAR: holdout hitter MAE {hp:+.4f}, star slice {hs:+.4f}, dev {dp:+.4f} "
                          f"(gate rule not met). Feature kept, nothing retrained.")
        row["verdict"] = "provisional"
        if row.get("provisional_kind") != "shipped_partial_measurement":
            items = [(k, v) for k, v in row.items() if k != "provisional_kind"]
            row.clear()
            for k, v in items:
                row[k] = v
                if k == "verdict":
                    row["provisional_kind"] = "shipped_partial_measurement"
    row["notes"] = _PARA_RE.sub("", row["notes"]) + para
    return rule


def _prospect_def_value(row: dict, art: dict) -> bool:
    v = art["validation_vs_fg"]
    dv, fg = v["def_value_spearman"], v["fg_tool_field_spearman"]
    mdv, mfg, n = v["def_value_mae_z"], v["fg_tool_field_mae_z"], v["n_graduated"]
    rule = abs(dv) > abs(fg) and mdv <= mfg
    stamp = art["evaluated_at"][:10]
    carried = art.get("carried_forward", {})
    para = (
        f"\nRE-MEASURED {stamp} (STALE_EVALS_REMEASURE; validate() on the current graduated frame; "
        f"evaluated_at in data/prospect_def_value_eval.json): Spearman {dv:.4f} vs FG fFld {fg:.4f}, "
        f"MAE_z {mdv:.4f} vs {mfg:.4f}, n={n} graduated; verdict by its registered rule: {v['verdict']}"
        f"{'' if rule else ' (the rule no longer holds; the verdict is left as registered and an owner question is open)'}. "
        f"The {', '.join(carried.get('blocks', []))} blocks are carried forward under their "
        f"{carried.get('measured_at', '2026-06-29')} date, not re-run: {carried.get('reason', 'see the artifact')}."
    )
    if rule:
        row["summary"] = (f"Beats FanGraphs fielding grades at predicting positional value (Spearman "
                          f"{dv:.2f} vs {fg:.2f}, n {n}), but adds nothing to eFV or the projection "
                          f"model; display only.")
    row["notes"] = _PARA_RE.sub("", row["notes"]) + para
    return rule


ROWS = {
    "proj_def_prior": ("data/proj_def_feature_eval.json", _proj_def_prior),
    "prospect_def_value": ("data/prospect_def_value_eval.json", _prospect_def_value),
}


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    raw = REGISTRY.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    reg = json.loads(text)
    assert json.dumps(reg, ensure_ascii=False, indent=1) + "\n" == text, \
        "data/model_registry.json no longer round-trips through json.dumps(indent=1); not rewriting it"
    fresh = mr.freshness(reg)
    today = date.today().isoformat()
    rules = {}
    for m in reg["models"]:
        mid = m.get("model_id")
        if mid not in ROWS:
            continue
        art_path, fn = ROWS[mid]
        art = json.loads((ROOT / art_path).read_text(encoding="utf-8"))
        assert art.get("evaluated_at"), f"{art_path} carries no evaluated_at stamp"
        rules[mid] = fn(m, art)
        f = fresh[mid]
        m["last_checked"] = today
        m["stale"] = f["stale"]
        m["artifact_age_days"] = f["artifact_age_days"]
    assert set(rules) == set(ROWS), f"rows missing from the registry: {set(ROWS) - set(rules)}"
    out = json.dumps(reg, ensure_ascii=False, indent=1) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    changed = out.encode("utf-8") != raw.encode("utf-8")
    for mid, ok in rules.items():
        print(f"{mid}: rule {'holds' if ok else 'DOES NOT HOLD'}; summary: {next(m for m in reg['models'] if m['model_id'] == mid)['summary']}")
    if changed and not check:
        REGISTRY.write_bytes(out.encode("utf-8"))
    print(("would change" if check else "changed") if changed else "unchanged", REGISTRY.name)
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
