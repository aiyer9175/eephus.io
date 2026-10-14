"""Point the prospect_anchor registry row at the look's artifact (idempotent; task
PROSPECT_ANCHOR_LOOK, docs/PROSPECT_ANCHOR_GATE.md section 18, 2026-10-14).

Reads data/prospect_anchor_gate.json, sets the row's eval_artifact to it, moves the verdict
from unvalidated to provisional (the registry enum has no word for UNDECIDED; a row that
carries an artifact may not read unvalidated), marks provisional_kind
shipped_partial_measurement (the served anchor serves, the one read adjudicated nothing),
rewrites the summary, sets registration_status, and appends one dated note carrying the
gate verdict, the frame, every cell's disposition and the fitted-file hash scored. Keeps the
file's line endings (CRLF) and its one-space indent. Running it twice changes nothing.

    python tools/register_prospect_anchor_look.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "prospect_anchor_gate.json"
FITTED = ROOT / "data" / "value_framework_fitted.json"
ROW = "prospect_anchor"
CELLS = ("45", "50", "55", "60", "65+")


def _f(v, nd=4):
    return "n/a" if v is None else f"{float(v):.{nd}f}"


def _ci(ci):
    return "none" if not ci else f"[{_f(ci[0])}, {_f(ci[1])}]"


def note_text(art: dict, fitted_sha: str, art_sha: str) -> str:
    run = art["run"]
    d = run["today"]
    early = run.get("early_read") or {}
    marker = f"LOOK {d} (PROSPECT_ANCHOR_LOOK)"
    st = art["label_stamps"]
    parts = [f"{marker}: the one look of section 14, taken once from HEAD a82bc17e by {run['command']}, "
             f"{'an OWNER-WAIVED EARLY READ under ' + early['waiver'].split(':')[0] + ', ' + str(early['days_before_floor']) + ' days before the registered floor ' + early['registered_floor'] if early else 'on its registered date'}; "
             f"step Z entry {run['step_z_entry']}. Label stamps: provider {st['war_basis']['provider']}, "
             f"{st['war_basis']['board_label_term']}, RESOLVED_THROUGH {st['RESOLVED_THROUGH']}, "
             f"SERVICE_ALIGNED_WINDOW {st['label_window_rule']['SERVICE_ALIGNED_WINDOW']}, "
             f"empirical_anchors generated_at {st['empirical_anchors_generated_at']}, cohort_window "
             f"{st['empirical_anchors_cohort_window']}, n_cohort {st['empirical_anchors_n_cohort']}. "
             f"Fitted file scored sha256 {fitted_sha}; artifact sha256 {art_sha}. "
             f"Verdict on the anchor: {art['verdict']} (margin pin holds {art['power']['margin_pin_holds']}; "
             f"concordance fired {art['concordance_fired'] or 'nowhere'}; lever {'none' if art['lever'] is None else art['lever'].get('result')})."]
    for fr in ("H", "S"):
        segs = []
        for c in CELLS:
            e = art["cells"][c][fr]
            segs.append(f"{c} {e['disposition']} (n {e['n']}, D_C {_f(e['d_c'])}, ci90 {_ci(e['ci90'])}, m_C {_f(art['cells'][c]['m_c'])})")
        parts.append(f"Frame {fr}{' (holdout, verdict-bearing)' if fr == 'H' else ' (shared, veto only)'}: " + "; ".join(segs) + ".")
    fam = art["families"]
    parts.append(f"Holm families at 0.10: H k {fam['H']['k']} rejected {fam['H']['rejected'] or 'none'}; "
                 f"S k {fam['S']['k']} rejected {fam['S']['rejected'] or 'none'}.")
    parts.append(f"Sentence: {art['sentence']}")
    parts.append("Nothing served moves: SERVE_PROSPECT_ANCHOR_V2 stays False, empirical_anchors_v2 does not exist, "
                 "prospect_surplus is untouched; the question re-arms under a new registration when "
                 "RESOLVED_THROUGH reaches 2027. Every number is on the published fWAR label and says nothing "
                 "about the label's accuracy (epoch clause (l)).")
    return " ".join(parts)


def _row_span(raw: bytes) -> tuple[int, int, bytes]:
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
    if "verdict" not in art or "cells" not in art:
        print("the artifact carries no verdict block; nothing written")
        return 1
    fitted_sha = hashlib.sha256(FITTED.read_bytes()).hexdigest()
    art_sha = hashlib.sha256(ART.read_bytes()).hexdigest()
    note = note_text(art, fitted_sha, art_sha)
    marker = note.split(":")[0]
    if marker in (row.get("notes") or ""):
        print("registry already carries the look note; nothing written")
        return 0
    h = art["cells"]["45"]["H"]
    row["eval_artifact"] = "data/prospect_anchor_gate.json"
    row["verdict"] = "provisional"
    row["provisional_kind"] = "shipped_partial_measurement"
    row["registration_status"] = (f"read once: the look of {art['run']['today']} (gate section 14), "
                                  f"{'an owner-waived early read' if art['run'].get('early_read') else 'on its registered date'}; "
                                  f"verdict {art['verdict']}; no lever, no flip")
    row["summary"] = (f"{art['verdict']}, read once {art['run']['today']} (owner-waived early read): the holdout is "
                      f"powered at FV 45 only, n {h['n']}, interval crosses the band; no S veto. Nothing served moves.")
    assert len(row["summary"].split()) <= 30, row["summary"]
    row["notes"] = (row.get("notes") or "").rstrip() + " " + note
    row["last_checked"] = art["run"]["today"]
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    REG.write_bytes(raw[:i] + text.encode("utf-8") + raw[j:])
    print(f"registry written: {ROW} -> provisional ({art['verdict']}), eval_artifact data/prospect_anchor_gate.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
