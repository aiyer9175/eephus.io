# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Re-derive the rem_plus registry row from its eval artifact (task
EVAL_FOLLOWUPS_REFREEZE, owner answer EVAL-Q 2026-10-28 'Re-measure REM+').

The row's summary and its 2026-06-30 headline (rho 0.236 vs ERA 0.090 and raw FIP
0.211) were typed by hand. After a re-run of tools/rem_plus_backtest.py --write the
served claim is read off data/rem_plus_eval.json here, never typed:

  * the summary is rewritten from the artifact when the artifact's own verdict status
    is 'validated' (the registered rule: REM+ beats ERA and raw WPA at a bootstrap gap
    lo95 above zero and is not worse than raw FIP at lo95 >= -0.01). When the status is
    anything else the summary and verdict are left exactly as registered and the
    paragraph says so: a verdict is changed by the owner, not by a refresh.
  * one RE-MEASURED paragraph in notes is replaced (derived from the artifact).
  * the derived card is re-read through model_registry.derive_card (the same reader
    refresh_stamps uses), so the /models/ card equals the artifact.
  * last_checked / stale / artifact_age_days are restamped from model_registry.freshness().

Idempotent: a second run on the same day rewrites nothing. Keeps the file's line endings
and the registry's own json.dumps(indent=1) layout, and refuses to write if the file no
longer round-trips through that layout (so it can never reformat the registry).

Run: python tools/refresh_rem_plus_registry_row.py [--check]
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
ARTIFACT = "data/rem_plus_eval.json"
MODEL_ID = "rem_plus"
_PARA_RE = re.compile(r"\nRE-MEASURED \d{4}-\d{2}-\d{2} \(EVAL_FOLLOWUPS_REFREEZE[^\n]*")


def _lo(gap: dict, key: str) -> float:
    return float(gap[key]["lo95"])


def rederive(row: dict, art: dict) -> bool:
    fs = art["forward_spearman_vs_RA9_next"]
    gap = art["gap_ci_vs_RA9_next"]
    rem, fip, era, wpa = fs["rem_plus"], fs["raw_fip"], fs["era"], fs["raw_wpa"]
    lo_fip, lo_era, lo_wpa = _lo(gap, "vs_raw_fip"), _lo(gap, "vs_era"), _lo(gap, "vs_raw_wpa")
    rule = lo_era > 0 and lo_wpa > 0 and lo_fip >= -0.01
    status = (art.get("verdict") or {}).get("status")
    assert (status == "validated") == rule, (
        f"{ARTIFACT}: verdict.status {status!r} disagrees with the registered rule ({rule})")
    stamp = art["generated_at"][:10]
    bake = art.get("leverage_variant_bakeoff") or {}
    best = bake.get("best") or {}
    stab = (art.get("stabilization_split_half") or {}).get("by_tbf_bin") or {}
    bins = ", ".join(f"{k} BF {v['split_half_rho']:.3f} (n {v['n']})" for k, v in stab.items()
                     if v.get("split_half_rho") is not None)
    market = art.get("market_check_aav") or {}
    fip_clause = (f"edges raw FIP ({fip:.3f}, lo95 {lo_fip:+.3f})" if lo_fip > 0 else
                  f"is not worse than raw FIP ({fip:.3f}, lo95 {lo_fip:+.3f})")
    para = (
        f"\nRE-MEASURED {stamp} (EVAL_FOLLOWUPS_REFREEZE; tools/rem_plus_backtest.py --write with the "
        f"same seasons, floors, damping grid and bootstrap seed as 2026-06-30, on the StatsAPI season "
        f"lines and the winProbability cache of this date; generated_at in {ARTIFACT}): "
        f"{art['n_forward_pairs']} Y->Y+1 pairs over {len(art['seasons'])} seasons; forward Spearman "
        f"vs next-year RA9: REM+ {rem:.4f}, raw FIP {fip:.4f}, ERA {era:.4f}, raw WPA {wpa:.4f}; rho "
        f"gap lo95 vs ERA {lo_era:+.4f}, vs raw WPA {lo_wpa:+.4f}, vs raw FIP {lo_fip:+.4f}. Leverage "
        f"bake-off best d={best.get('d')} (rho {best.get('rho')} vs pure "
        f"{bake.get('rem_plus_pure_on_this_subset')}; {bake.get('verdict', 'n/a')}). Split-half rho by "
        f"TBF: {bins or 'n/a'}. Verdict by the registered rule (beats ERA and raw WPA at lo95 > 0, "
        f"raw-FIP gap lo95 >= -0.01): {status}"
        + ("" if rule else
           " (the rule no longer holds; the verdict is left as registered and an owner question is open)")
        + f". The artifact's market_check_aav block ({market.get('n_signings_matched')} name-matched "
        f"signings) is a lab read the scorecard does not print (census M06-01); the served market line "
        f"stays the 2026-09-18 re-gate."
    )
    if rule:
        row["summary"] = (f"Validated: REM+ predicts next-year RA9 better than ERA (rho {rem:.3f} vs "
                          f"{era:.3f}, lo95 {lo_era:+.3f}) and {fip_clause}. Leverage stays out of the "
                          f"skill number.")
    row["notes"] = _PARA_RE.sub("", row["notes"]) + para
    if (row.get("card") or {}).get("derived_from"):
        row["card"] = mr.derive_card(row, art)
    return rule


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    raw = REGISTRY.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    reg = json.loads(text)
    assert json.dumps(reg, ensure_ascii=False, indent=1) + "\n" == text, \
        "data/model_registry.json no longer round-trips through json.dumps(indent=1); not rewriting it"
    art = json.loads((ROOT / ARTIFACT).read_text(encoding="utf-8"))
    assert art.get("generated_at"), f"{ARTIFACT} carries no generated_at stamp"
    row = next((m for m in reg["models"] if m.get("model_id") == MODEL_ID), None)
    assert row is not None, f"{MODEL_ID} row missing from the registry"
    assert row.get("eval_artifact") == ARTIFACT, f"{MODEL_ID} row points at {row.get('eval_artifact')}"
    rule = rederive(row, art)
    f = mr.freshness(reg)[MODEL_ID]
    row["last_checked"] = date.today().isoformat()
    row["stale"] = f["stale"]
    row["artifact_age_days"] = f["artifact_age_days"]
    problems = [p for p in mr.validate(reg) if p.startswith(MODEL_ID + ":")]
    assert not problems, f"the re-derived row fails validate(): {problems}"
    out = json.dumps(reg, ensure_ascii=False, indent=1) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    changed = out.encode("utf-8") != raw.encode("utf-8")
    print(f"{MODEL_ID}: rule {'holds' if rule else 'DOES NOT HOLD'}; verdict {row['verdict']}; "
          f"summary: {row['summary']}")
    print(f"{MODEL_ID}: card headline "
          f"{[(h['champion'], h['baseline'], h['gap_ci']) for h in (row.get('card') or {}).get('headline', [])]}")
    if changed and not check:
        REGISTRY.write_bytes(out.encode("utf-8"))
    print(("would change" if check else "changed") if changed else "unchanged", REGISTRY.name)
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
