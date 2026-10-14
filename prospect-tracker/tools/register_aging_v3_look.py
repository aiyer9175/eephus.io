"""Write the look's verdicts into the aging_v3 and aging_v3_prospect_shape
registry rows (idempotent; docs/AGING_V3_GATE.md section 16, task
AG_7_AGING_V3_LOOK).

Reads data/aging_v3_eval.json (the one look: the ladder on GATE, PS, the
TIER-2 veto, CONFIRM) and sets each row's eval_artifact, verdict,
registration_status, summary, champion and metric from the artifact, and
appends one LOOK note to its notes. The ship rule of the spec, in the
registry's own verdict vocabulary (model_registry.VERDICTS has no 'failed'
or 'underpowered'): a ladder whose final composition is non-empty is
'validated' (the note names the composition); a ladder with no surviving arm
is 'deprecated', the status saying FAILED or UNDERPOWERED arm by arm; PS
'validated' on PASS, else 'deprecated' (FAIL, or 'composition withdrawn').

Every edit is a replacement of one JSON value literal inside the row's own
span of the file's bytes: every other byte, the line endings (CRLF) and the
indent of every other row stay as they are. Running it twice changes
nothing; running it after a re-read replaces the earlier LOOK note.

    python tools/register_aging_v3_look.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
EVAL = ROOT / "data" / "aging_v3_eval.json"
ARTIFACT = "data/aging_v3_eval.json"
MARK = " LOOK ("
ARMS = ("T", "S", "P", "R")
ARM_NAMES = {"T": "playing time", "S": "the rate estimator", "P": "positional buckets", "R": "skill archetypes"}


def _r(x, nd=5):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _p(x):
    return "n/a" if x is None else f"{x:.4f}"


def ladder_lines(doc: dict) -> tuple[list[str], list[str]]:
    """Per-arm GATE readings and the veto readings, as short phrases."""
    out, veto = [], []
    arms = doc["ladder"]["arms"]
    for a in ARMS:
        e = arms.get(a) or {}
        v = e.get("verdict")
        if v == "UNDERPOWERED":
            out.append(f"{a} ({ARM_NAMES[a]}) UNDERPOWERED on DEV (not run)")
            continue
        b = e.get("bootstrap") or {}
        g = e.get("guards") or {}
        failed = [k for k in ("G1", "G2", "G3", "G4") if (g.get(k) or {}).get("pass") is False]
        pred = "+".join(e.get("predecessor") or []) or "comparator"
        out.append(f"{a} ({ARM_NAMES[a]}) vs {pred}: D {_r(b.get('D'))} p {_p(b.get('p'))}"
                   f"{(' guards failed ' + ','.join(failed)) if failed else ' guards ok'} -> {v}")
    for name, key in (("TIER-2", "tier2_veto"), ("CONFIRM", "confirm")):
        blk = doc.get(key) or {}
        if key == "confirm" and not blk.get("opened"):
            veto.append(f"CONFIRM not opened (n {blk.get('n_rows')} < 1,000)")
            continue
        for a, e in (blk.get("arms") or {}).items():
            b = e.get("bootstrap") or {}
            veto.append(f"{name} {a}: D {_r(b.get('D'))} p_reversal {_p(b.get('p_reversal'))} -> {e.get('verdict')}")
        if not (blk.get("arms") or {}):
            opened = f" (opened, n {blk.get('n_rows'):,} >= 1,000)" if key == "confirm" else f" (n {blk.get('n_rows'):,})"
            veto.append(f"{name}{opened}: no passed arm to read")
    return out, veto


def ladder_fields(doc: dict) -> dict:
    final = list(doc.get("final_composition") or [])
    passed = list(doc["ladder"].get("passed") or [])
    day = doc["generated_at"][:10]
    gate = doc["frames"]["GATE"]
    arms_txt, veto_txt = ladder_lines(doc)
    waived = bool(doc.get("owner_waived_early_read"))
    how = "the owner-waived early read of" if waived else "the look of"
    if final:
        verdict = "validated"
        comp = "+".join(final)
        status = (f"read once: {how} {day} (gate sections 7 and 9); PASS, composition {comp}; "
                  f"served by no page until AG_8 flips")
        summary = (f"Read once {day}: the ladder's accepted composition is {comp} on GATE (label seasons "
                   f"2011-2013, {gate['n_rows']:,} rows), kept through the TIER-2 and CONFIRM vetoes; "
                   "served by no page until the AG_8 flip.")
        champion = (f"The composition {comp} of the aging v3 service at the DEV selections (lambda "
                    f"{doc['selected']['lambda']}, smoother {doc['selected']['smoother']} penalty "
                    f"{doc['selected']['penalty']}, k_P {doc['selected']['k_P']}, k_R {doc['selected']['k_R']}), "
                    f"cfg8 {doc['final_cfg8']}; the full fit is data/aging_v3_curves.json")
    else:
        verdict = "deprecated"
        words = []
        for a in ARMS:
            v = (doc["ladder"]["arms"].get(a) or {}).get("verdict")
            words.append(f"{a} {v}")
        status = (f"read once: {how} {day} (gate sections 7 and 9); no arm ships: "
                  + ", ".join(words) + (f"; passed at GATE then withdrawn: {'+'.join(passed)}" if passed else "")
                  + "; never served")
        summary = (f"Read once {day}: no ladder arm ships ({', '.join(words)}) on GATE (label seasons "
                   f"2011-2013, {gate['n_rows']:,} rows); the v2 champion curves stay the served engine.")
        champion = ("none: no arm survived the one read; the v2 champion curves (fa_aging_curves) stay the "
                    "served engine and every consumer door keeps aging=\"v2\"")
    metric = ("ACAL over 10 age-band by side cells on GATE (label seasons 2011-2013, fWAR), player-cluster "
              "bootstrap B 2000 seed 20261124, PASS p < 0.0125 per arm with guards G1 to G4; "
              + "; ".join(arms_txt) + ". Vetoes: " + "; ".join(veto_txt) + ".")
    note = (f"{MARK}{day}, AG_7_AGING_V3_LOOK, {ARTIFACT}"
            + (", an OWNER-WAIVED EARLY READ under EW3-5 (owner 2026-10-14)" if waived else "")
            + f"): GATE {gate['n_rows']:,} rows, bases {gate['bases'][0]}-{gate['bases'][-1]}; "
            + "; ".join(arms_txt) + ". " + "; ".join(veto_txt)
            + f". Final composition {'+'.join(final) if final else 'none'} (cfg8 {doc['final_cfg8']}). "
            + ("data/aging_v3_curves.json is the accepted composition fitted on the full fWAR corpus, read by no "
               "page and no consumer until AG_8 flips proj_display." if final else
               "No data/aging_v3_curves.json is written: there is no accepted composition to serve.")
            + " A TIER-2 or CONFIRM number is never cited as support for a PASS.")
    return {"summary": summary, "champion": champion, "metric": metric, "eval_artifact": ARTIFACT,
            "verdict": verdict, "registration_status": status, "_note": note}


def ps_fields(doc: dict) -> dict:
    ps = doc["ps"]
    day = doc["generated_at"][:10]
    waived = bool(doc.get("owner_waived_early_read"))
    how = "the owner-waived early read of" if waived else "the look of"
    v = ps.get("verdict")
    prim = ps.get("primary") or {}
    comp = "+".join(doc["ladder"].get("passed") or []) or "no arm (the v2 curves through shape())"
    failed = sorted(k for k, g in (ps.get("guards") or {}).items() if g.get("pass") is False)
    reading = (f"n {ps.get('n')} debutants (cohorts 2014-2018), mean paired SSE_inc minus SSE_v3 "
               f"{_r(prim.get('mean_paired_sse_diff'))}, lo95 {_r(prim.get('lo95'))}"
               + (f", guards failed {', '.join(failed)}" if failed else ", guards ok") + f" -> {v}")
    if v == "PASS":
        verdict = "validated"
        status = f"read once: {how} {day} (gate section 9); PASS on the composition {comp}; served by no page until AG_8 flips"
        summary = (f"Read once {day}: the v3 shape() beats the incumbent tent on debut cohorts 2014-2018 "
                   f"({reading}); served by no page until the AG_8 flip.")
        champion = f"aging_v3.shape() under the ladder's composition {comp} (cfg8 {ps.get('composition_cfg8')})"
    else:
        verdict = "deprecated"
        status = f"read once: {how} {day} (gate section 9); {v}; never served"
        summary = (f"Read once {day}, {v}: the v3 shape() does not beat the incumbent tent on debut cohorts "
                   f"2014-2018 (n {ps.get('n')}, lo95 {_r(prim.get('lo95'))}); the tent stays, prospect consumers stay off.")
        champion = ("none: the incumbent tent value_framework._trajectory_shape stays; shape() returns only as a "
                    "new registration")
    metric = ("Mean paired SSE_inc minus SSE_v3 of the level-free fit per player on debut cohorts 2014-2018 "
              "(seasons d to d+6, 2020 masked), player bootstrap B 2000 seed 20261124, one-sided lo95 > 0, with "
              "debut-age and bucket guards (10 percent, n >= 40): " + reading + ".")
    note = (f"{MARK}{day}, AG_7_AGING_V3_LOOK, {ARTIFACT}"
            + (", an OWNER-WAIVED EARLY READ under EW3-5 (owner 2026-10-14)" if waived else "")
            + f"): {reading}; composition scored {comp}. No FV, grade, list vintage or prospect row was read.")
    return {"summary": summary, "champion": champion, "metric": metric, "eval_artifact": ARTIFACT,
            "verdict": verdict, "registration_status": status, "_note": note}


def _row_span(text: str, model_id: str) -> tuple[int, int]:
    """The span of the row's object in the file text: from its model_id key
    to the next row's model_id key (or the end of the models list)."""
    key = json.dumps("model_id") + ": " + json.dumps(model_id)
    s = text.index(key)
    n = text.find(json.dumps("model_id") + ": ", s + len(key))
    return s, (n if n >= 0 else len(text))


def apply(text: str, model_id: str, fields: dict, row: dict) -> tuple[str, dict]:
    s, e = _row_span(text, model_id)
    block = text[s:e]
    new_row = dict(row)
    note = fields.pop("_note")
    base = (row.get("notes") or "").rstrip()
    if MARK in base:
        base = base[:base.index(MARK)].rstrip()
    fields["notes"] = base + note
    for k, v in fields.items():
        if row.get(k) == v:
            continue
        old_lit = json.dumps(k) + ": " + json.dumps(row.get(k), ensure_ascii=False)
        if block.count(old_lit) != 1:
            raise SystemExit(f"{model_id}.{k}: the literal occurs {block.count(old_lit)} times in the row; nothing written")
        block = block.replace(old_lit, json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False), 1)
        new_row[k] = v
    return text[:s] + block + text[e:], new_row


def main() -> int:
    if not EVAL.exists():
        raise SystemExit(f"{EVAL} is absent: the look has not been written")
    doc = json.loads(EVAL.read_text(encoding="utf-8"))
    if doc.get("task") != "AG_7_AGING_V3_LOOK":
        raise SystemExit("data/aging_v3_eval.json is not the AG_7 look artifact")
    raw = REG.read_bytes()
    text = raw.decode("utf-8")
    reg = json.loads(text)
    rows = {r["model_id"]: r for r in reg["models"]}
    expected = {}
    for model_id, fields in (("aging_v3", ladder_fields(doc)), ("aging_v3_prospect_shape", ps_fields(doc))):
        text, expected[model_id] = apply(text, model_id, fields, rows[model_id])
    if text == raw.decode("utf-8"):
        print("registry already carries this look; nothing written")
        return 0
    check = {r["model_id"]: r for r in json.loads(text)["models"]}
    for model_id, row in expected.items():
        assert check[model_id] == row, model_id
    REG.write_bytes(text.encode("utf-8"))
    for model_id in expected:
        print(f"registry written: {model_id} -> {expected[model_id]['verdict']}; {expected[model_id]['registration_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
