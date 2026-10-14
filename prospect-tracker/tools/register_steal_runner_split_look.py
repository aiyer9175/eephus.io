# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Record the one steal runner split read on its registry row (idempotent; task
W11_3_STEAL_RUNNER_SPLIT_BUILD_READ, docs/management-2026-10/STEAL_RUNNER_SPLIT_GATE.md
sections 5, 6 and 8).

Reads data/steal_runner_split_eval.json, points the row's eval_artifact at it and moves
the verdict per gate section 5: a NULL moves the row to deprecated with the failed
conditions named; a PASS moves it to provisional (eligible, not served; serving is the
flip task's own commit). Appends one dated note with the numbers read from the
artifact. Splices only the steal_runner_split row and keeps the file's line endings and
indent. Running it twice changes nothing.

    python tools/register_steal_runner_split_look.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "steal_runner_split_eval.json"
ROW = "steal_runner_split"

COND_WORDS = {
    "1_n_scored_at_least_1000": "condition 1 (at least 1,000 scored attempts)",
    "2_dLL_lower_bound_above_0": "condition 2 (dLL lower bound above 0)",
    "3_dBrier_lower_bound_above_0": "condition 3 (dBrier lower bound above 0)",
    "4_dLL_runner_lower_bound_above_0": "condition 4 (dLL_runner lower bound above 0)",
}


def _f(v, nd=6):
    return "n/a" if v is None else f"{float(v):+.{nd}f}"


def note_text(art: dict) -> str:
    rd = art["read"]
    sc = art["score"]
    fz = art["frozen_fit"]
    bt = sc["bootstrap"]
    marker = f"READ {rd['run_date']} (W11_3)"
    parts = [f"{marker}: {rd['kind']}, registered date {rd['registered_date']}; code {rd['code_commit'][:8]}, "
             f"context payload sha256 {rd['context_sha256']}. Fit 2018-2023 {fz['frames']['fit']['rows']:,} "
             f"attempts, tune 2024 {fz['frames']['tune']['rows']:,}, score 2025 {sc['n_scored']:,} attempts "
             f"in {sc['bootstrap_games']:,} games. Chosen lambda: candidate {fz['candidate']['lambda']}, twin "
             f"{fz['twin']['lambda']}. Game bootstrap B 2000, seed 20261020, one-sided 95% lower bounds:"]
    for k in ("dLL", "dBrier", "dLL_runner"):
        s = bt[k]
        parts.append(f"{k} {_f(s['point'])} (lower bound {_f(s['lower_95_one_sided'])}, 90% "
                     f"[{_f(s['interval_90'][0])}, {_f(s['interval_90'][1])}]);")
    if art["verdict"] == "PASS":
        parts.append("PASS on all four conditions: ER_runner and ER_other are eligible behind "
                     "STEAL_RUNNER_SPLIT_LIVE, served only by the flip task's own commit.")
    else:
        failed = ", ".join(COND_WORDS.get(c, c) for c in art["failed_conditions"])
        parts.append(f"NULL: {failed} failed. The split stays dark and is never served; the stage 1 "
                     "context columns stay as served; ER is served whole; no second read on 2025, and a "
                     "new feature set or model needs a new registration on a frame not yet read.")
    parts.append("DV and every manager or club figure are unchanged; nothing prices a steal in the Diamond.")
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
    note = note_text(art)
    marker = note.split(":")[0]
    if marker in (row.get("notes") or ""):
        print("registry already carries the read note; nothing written")
        return 0
    rd = art["read"]
    bt = art["score"]["bootstrap"]
    passed = art["verdict"] == "PASS"
    row["eval_artifact"] = "data/steal_runner_split_eval.json"
    row["verdict"] = "provisional" if passed else "deprecated"
    row["registration_status"] = (
        f"read once: the {'owner-waived early read' if 'EARLY' in rd['kind'] else 'registered read'} "
        f"of {rd['run_date']} (gate section 6); {'PASS, eligible, not served' if passed else 'NULL, never served'}")
    if passed:
        row["summary"] = (f"Read once {rd['run_date']}, PASS: the runner-aware steal model beats the league "
                          f"rate on 2025 and the runner terms add log loss. Eligible, not served.")
        row["champion"] = ("the runner-aware candidate of gate section 2.1, eligible behind "
                           "STEAL_RUNNER_SPLIT_LIVE; DV keeps the league-average runner")
    else:
        row["summary"] = (f"Read once {rd['run_date']}, NULL: beats the league rate on 2025 (dLL bound "
                          f"{bt['dLL']['lower_95_one_sided']:+.4f}); the runner terms add no resolvable gain "
                          f"(bound {bt['dLL_runner']['lower_95_one_sided']:+.4f}); never served.")
        row["champion"] = ("none: the candidate failed gate section 5 at its one read; the "
                           "league-average-runner incumbent stays, and ER is served whole")
        row["surface"] = ("None served: the split of the /management/ steal execution residual into "
                          "ER_runner and ER_other stays dark after a NULL read; DV and every served "
                          "management number unchanged")
    row["metric"] = ("Paired per-attempt log loss and Brier against the incumbent, and log loss against a "
                     "twin without the runner terms, on 2025 attempts; game bootstrap B 2000 seed 20261020; "
                     "one-sided 95% lower bound above zero")
    assert len(row["summary"].split()) <= 30, row["summary"]
    row["notes"] = (row.get("notes") or "").rstrip() + " " + note
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    REG.write_bytes(raw[:i] + text.encode("utf-8") + raw[j:])
    print(f"registry written: {ROW} -> {row['verdict']}, eval_artifact {row['eval_artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
