# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Record look P (the power composite, one look) on its registry row (idempotent;
task TL_5_POWER_COMPOSITE_LOOK, docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md
Parts P, 7 and 8).

Reads data/power_composite_eval.json, points the power_composite_v2 row's
eval_artifact at it and moves the verdict per gate P.7: a C1 or C2 serve moves the
row to provisional (eligible, built dark by TL_6 and served by TL_7); a C0 verdict
moves it to provisional, measured_not_adopted (a real gate ran and no candidate
ships). Appends one dated note with the numbers read from the artifact and stamps
freshness (last_checked, stale, artifact_age_days). Splices only the
power_composite_v2 row and keeps the file's line endings and indent. Running it
twice changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_power_composite_look.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "power_composite_eval.json"
ROW = "power_composite_v2"
READ_DATE = "2026-10-14"
READ_KIND = "OWNER-WAIVED EARLY READ"

CLAUSE_WORDS = {
    "1_lo95_above_0": "clause 1 (lower bound above 0)",
    "2_d_at_least_2F": "clause 2 (d at least twice the swap floor)",
    "3_not_vetoed": "clause 3 (no AUC veto)",
    "4_holm": "clause 4 (Holm)",
}


def _s(v, nd=4):
    return "n/a" if v is None else f"{float(v):+.{nd}f}"


def _failed(c: dict) -> str:
    return ", ".join(CLAUSE_WORDS[k] for k, ok in c["clauses"].items() if not ok) or "none"


def note_text(art: dict) -> str:
    res = art["result"]
    v = res["verdict"]
    cd = res["candidates"]
    marker = f"READ {READ_DATE} (TL_5)"
    parts = [f"{marker}: look P, run once, an {READ_KIND} (owner EW3-5), gate sha {art['gate_sha'][:8]}; "
             f"{res['n']} hitters over board years 2017 to 2019 and 2022 to 2024 (by year "
             + ", ".join(f"{y} {n}" for y, n in res["rows_by_year"].items()) + "). "
             f"Within-year Spearman with pooled ISO: C0 {cd['C0']['rho']}, C1 {cd['C1']['rho']}, "
             f"C2 {cd['C2']['rho']}."]
    for name in ("C1", "C2"):
        c = v[name]
        parts.append(f"{name}: d {_s(c['d'], 6)}, lo95 {_s(c['lo95'], 6)}, swap floor F {c['F']} "
                     f"(ratio {c['ratio_to_floor']}), d_auc {_s(c['d_auc'], 6)} against floor {c['F_auc']} "
                     f"(veto {c['auc_veto']}), permutation p {c['p_perm']}, Holm step {c['holm_step']}; "
                     f"pass {c['pass']}; failed: {_failed(c)}.")
    parts.append(f"Fold-wise a {json.dumps(res['a_by_year'])}; served a {res['served_a']} "
                 f"(C2 would serve as {res['served_as']}).")
    if v["serve"] == "C0":
        parts.append("Verdict C0 retains: the served v12 mean of game and raw consensus stays the power "
                     "composite; TL_6 and TL_7 have no winner to build or serve; pwr_comp is not an eFV "
                     "candidate (gate Part 7); no eFV input moves. Secondaries (HR per PA, barrels per PA, "
                     "exit velocity) are reported in the artifact and never decide.")
    else:
        parts.append(f"Verdict serve {v['serve']}: eligible behind POWER_COMPOSITE_MODE (TL_6, default off), "
                     "served only by TL_7's own commit.")
    parts.append(res["survivorship"])
    return " ".join(parts)


def _row_span(raw: bytes) -> tuple[int, int, bytes]:
    """(start, end, indent) of the row's object: from its '{' through the '}' that closes
    it, so every other byte of the file stays as it is."""
    m = re.search(rb"\r?\n(\s*)\{\r?\n\s*\"model_id\": \"" + ROW.encode() + rb"\",", raw)
    if m is None:
        raise SystemExit(f"registry carries no {ROW} row")
    i = raw.index(b"{", m.start())
    depth, j, in_str, esc = 0, i, False, False
    while True:
        c = raw[j:j + 1]
        if in_str:
            if esc:
                esc = False
            elif c == b"\\":
                esc = True
            elif c == b'"':
                in_str = False
        elif c == b'"':
            in_str = True
        elif c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return i, j + 1, m.group(1)


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    i, j, indent = _row_span(raw)
    row = json.loads(raw[i:j].decode("utf-8"))
    assert row.get("model_id") == ROW
    if not ART.exists():
        print(f"{ART} missing; nothing written")
        return 1
    art = json.loads(ART.read_text(encoding="utf-8"))
    if art.get("look") != "P" or not art.get("spent") or art.get("stopped"):
        print("the artifact carries no completed look P record; nothing written")
        return 1
    note = note_text(art)
    marker = note.split(":")[0]
    if marker in (row.get("notes") or ""):
        print("registry already carries the read note; nothing written")
        return 0
    res = art["result"]
    v = res["verdict"]
    c1 = v["C1"]
    served = v["serve"] != "C0"
    row["eval_artifact"] = "data/power_composite_eval.json"
    row["verdict"] = "provisional"
    if served:
        row.pop("provisional_kind", None)
    else:
        row["provisional_kind"] = "measured_not_adopted"
    row["registration_status"] = (
        f"read once: the owner-waived early read of {READ_DATE} (gate Part 8); "
        + (f"{v['serve']} eligible, not served" if served else "C0 retains, nothing served"))
    if served:
        row["summary"] = (f"Look P read once {READ_DATE}: {v['serve']} passes on ISO against the served mean "
                          f"(n {res['n']}). Eligible behind POWER_COMPOSITE_MODE, not served.")
        row["champion"] = (f"{v['serve']}, eligible behind POWER_COMPOSITE_MODE (TL_6, default off); the served "
                           "v12 formula (consensus.py) stays until TL_7's flip")
    else:
        row["summary"] = (f"Measured, not adopted: game power alone leads the served mean on ISO by rho "
                          f"{_s(c1['d'])} (lo95 {_s(c1['lo95'])}, n {res['n']}) but falls short of twice its "
                          f"swap floor; C0 retains.")
        row["champion"] = ("none adopted: C0, the served v12 formula (consensus.py, round-half mean of game and "
                           "raw consensus), retains after the one look; C1 and C2 failed P.6 clause 2")
        row["surface"] = ("None served: look P read once (C0 retains); the power composite on every surface "
                          "stays the v12 mean of game and raw consensus; TL_6 and TL_7 have no winner to build")
    row["metric"] = ("d = within-board-year Spearman of the candidate minus C0 with pooled MLB ISO on identical "
                     "rows (board years 2017 to 2019 and 2022 to 2024, debut year at most 2024, 300 PA); PASS "
                     "needs lo95 above 0 (player-clustered bootstrap B 2000, seed 20261021), d at least twice "
                     "the swap floor (1,000 draws), no top-tercile AUC veto and Holm across C1 and C2; "
                     "secondaries HR per PA, barrels per PA and exit velocity never decide")
    assert len(row["summary"].split()) <= 30, row["summary"]
    row["notes"] = (row.get("notes") or "").rstrip() + " " + note
    gen = datetime.strptime(art["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    row["last_checked"] = READ_DATE
    row["stale"] = False
    row["artifact_age_days"] = max(0, (datetime(2026, 10, 14, tzinfo=timezone.utc) - gen).days)
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    REG.write_bytes(raw[:i] + text.encode("utf-8") + raw[j:])
    print(f"registry written: {ROW} -> {row['verdict']} ({row.get('provisional_kind')}), "
          f"eval_artifact {row['eval_artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
