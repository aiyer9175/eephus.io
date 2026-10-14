"""Move the proj_components registry row to provisional after the PJ-C look
(idempotent; task PJ_5_COMPONENT_LOOK, docs/PROJ_COMPONENTS_GATE.md section 5).

Reads data/proj_components_eval.json, points the row's eval_artifact at it,
sets verdict provisional (whatever the outcome; the gate's own words), updates
the summary and registration_status, and appends one dated note listing each
head's verdict with its numbers read from the artifact. Keeps the file's line
endings (CRLF) and its one-space indent. Running it twice changes nothing.

    python tools/register_proj_components_look.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "proj_components_eval.json"
ROW = "proj_components"


def _f(v, nd=4):
    return "n/a" if v is None else f"{float(v):.{nd}f}"


def note_text(art: dict) -> str:
    d = art["look_date"]
    marker = f"LOOK {d} (PJ_5_COMPONENT_LOOK)"
    parts = [f"{marker}: the one PJ-C holdout read, bases 2022 to 2024, cells (2022, h1-h4), (2023, h1-h3), "
             f"(2024, h1-h2), label seasons {art['holdout'].get('label_seasons')}, frozen params sha256 "
             f"{art['params_sha256']}, seed 20261124, B {art['bootstrap'].get('B')}, VIF 1.8, "
             f"scorer rows {art['holdout'].get('n_rows_in_cells')}. Verdicts by gate 4.5 and 4.6 only:"]
    for head, v in art["verdicts"].items():
        ch = v["checks"]
        seg = [f"{v['label']} {v['verdict']} (h1 survived n {v['h1_n_survived']}, rate MAE {_f(v['h1_mae'])}"]
        for c in ("naive", "implicit"):
            k = ch[f"h1_ub95_below_0_vs_{c}"]
            seg.append(f"vs {c} MAE {_f(v['h1_comparator_mae'][c])} delta {_f(k['delta'])} ub95 {_f(k['ub95'])}")
        parts.append("; ".join(seg) + ")" + ("; " + "; ".join(v["reasons"]) if v["reasons"] else "") + ".")
    for head, v in art["exposure_test"].items():
        ch = v["checks"]
        seg = [f"{v['label']} {v['verdict']} (h1 survived n {v['h1_n_survived']}, MAE {_f(v['h1_mae'], 2)}"]
        for c in ("prior_season", "w543"):
            k = ch[f"h1_ub95_below_0_vs_{c}"]
            seg.append(f"vs {c} MAE {_f(k['comparator_mae'], 2)} delta {_f(k['delta'], 2)} ub95 {_f(k['ub95'], 2)}")
        parts.append("; ".join(seg) + ").")
    t = art["gap_tripwire"]
    p = t["pooled"]
    parts.append(f"Gap tripwire: pooled mean (served war minus component WAR) at h1 on the holdout rows "
                 f"{_f(p.get('mean'))} WAR on n {p.get('n')} (threshold 0.30 either sign): "
                 f"{'BLOCKS the flip' if t.get('blocks_flip') else ('clear' if t.get('blocks_flip') is False else 'n/a')}.")
    parts.append("A failed or UNDERPOWERED head is not served; its runs ride in the gap line and the card says "
                 "'not projected'. No number here is a WAR accuracy claim (owner answer PJ-Q2). Nothing served "
                 "moves at this look; a flip is PJ_8's own commit behind PROJ_COMPONENTS_LIVE.")
    return " ".join(parts)


def _row_span(raw: bytes) -> tuple[int, int, bytes]:
    """(start, end, indent) of the proj_components row's bytes: the '{' that
    opens it through the '}' that closes it, so every other byte of the file
    stays as it is (other rows carry their own indent; none is reformatted)."""
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
    if "holdout" not in art:
        print("the artifact carries no holdout block; nothing written")
        return 1
    note = note_text(art)
    marker = note.split(":")[0]
    if marker in (row.get("notes") or ""):
        print("registry already carries the look note; nothing written")
        return 0
    verdicts = {h: v["verdict"] for h, v in art["verdicts"].items()}
    expo = {h: v["verdict"] for h, v in art["exposure_test"].items()}
    passed = [art["verdicts"][h]["label"] for h, v in verdicts.items() if v == "PASS"]
    row["eval_artifact"] = "data/proj_components_eval.json"
    row["verdict"] = "provisional"
    row["registration_status"] = f"read once: the PJ-C holdout look of {art['look_date']} (gate section 5); no flip"
    # the summary is capped at 30 words and one short sentence (model_registry.validate)
    short = {"bsr": "H3 BsR", "fld_pos": "H4 + H5 Fld + Pos", "gmli_relief": "P4 gmLI",
             "ra9_gap": "P5 RA9 gap", "pa": "PA", "ip": "IP"}
    allv = dict(verdicts, **expo)
    groups = []
    for verdict, word in (("PASS", "pass"), ("UNDERPOWERED", "underpowered"), ("FAIL", "fail")):
        names = [short[h] for h, v in allv.items() if v == verdict]
        if names:
            groups.append(f"{', '.join(names)} {word}")
    row["summary"] = ("Read once on the holdout, not served: " + "; ".join(groups)
                      + f"; tripwire {'blocks' if art['gap_tripwire'].get('blocks_flip') else 'clear'}.")
    assert len(row["summary"].split()) <= 30, row["summary"]
    row["notes"] = (row.get("notes") or "").rstrip() + " " + note
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    # raw[:i] already ends with the row's own indent before its '{'
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    REG.write_bytes(raw[:i] + text.encode("utf-8") + raw[j:])
    print("registry written: proj_components -> provisional, eval_artifact data/proj_components_eval.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
