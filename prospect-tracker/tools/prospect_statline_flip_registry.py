#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The glossary entry, registry row update and MODEL_GLOSSARY mapping of the prospect
arrival line (TL_18_STATLINE_DISPLAY_FLIP, the flip commit). Idempotent: a second run
changes nothing. Preserves each file's line endings (CRLF) and indent (1), the
glossary's non-ASCII and trailing newline, the registry's absence of one. Every figure
printed in the copy is read from data/prospect_statline_eval.json; the stats named are
the ones whose L1 verdict there is PASS.

Usage (from the module root, after data/prospect_statline_eval.json exists):
    python tools/prospect_statline_flip_registry.py --check     # dry run into a temp dir
    python tools/prospect_statline_flip_registry.py             # apply

Writes data/glossary.json (entry arrival_line), data/model_registry.json (row
mlb_projections_prospects_statline, surface, champion, status and notes) and
test_methodology_freshness.py (MODEL_GLOSSARY).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE.parent if HERE.name == "tools" else HERE
ORIGIN = "Arkmetric, original to eephus.io."
GATE = "docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md"
MODEL_ID = "mlb_projections_prospects_statline"
FLIP_MARK = "\nFLIP 2026-10-21 (TL_18_STATLINE_DISPLAY_FLIP):"
LABEL = {"k_pct": "K%", "bb_pct": "BB%", "iso": "ISO", "avg": "AVG", "babip": "BABIP",
         "woba": "wOBA", "xwoba": "xwOBA", "hr_bf": "HR per BF"}
BASE = {"B0": "the league-average rookie line", "B1": "the translated minor league rate alone",
        "B2": "the tool-implied value of his grade alone", "B3": "the xwOBA prior alone"}


def _read_eval(root: Path) -> dict:
    return json.loads((root / "data" / "prospect_statline_eval.json").read_text(encoding="utf-8"))


def _rate(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".lstrip("0") if abs(v) < 1 else f"{v:.{d}f}"


def figures(ev: dict) -> dict:
    res = ev["results"]
    l1 = res["l1"]
    passed = [(side, stat, e) for side in ("hit", "pit") for stat, e in l1[side].items()
              if e.get("verdict") == "PASS"]
    null = [(side, stat, e) for side in ("hit", "pit") for stat, e in l1[side].items()
            if e.get("verdict") != "PASS"]
    l2 = res["l2"]
    veto = [(side, stat, e) for side, stat, e in null if e.get("holm_survives") and e.get("coverage_veto")]
    coh = ev["holdout_cohorts"]
    return {"passed": passed, "n_null": len(null), "veto": veto, "l2": l2,
            "span": f"{coh[0]} to {coh[-1]}", "look_date": ev["generated_at"][:10],
            "train": f"{ev['train_cohorts'][0]} to {ev['train_cohorts'][-1]}"}


def _stat_clause(side: str, stat: str, e: dict) -> str:
    return (f"{LABEL[stat]} mean miss {_rate(e['mae_model'], 4)} against {_rate(e['mae_best_baseline'], 4)} "
            f"for {BASE[e['best_baseline']]} (n {e['n']}, lower bound of the gain {_rate(e['d_lb95'], 4)}), "
            f"the P10 to P90 band holding {round(100 * e['coverage_p10_p90'])} percent")


def glossary_entry(f: dict) -> dict:
    names = " and ".join(LABEL[s] for _side, s, _e in f["passed"])
    clauses = "; ".join(_stat_clause(side, s, e) for side, s, e in f["passed"])
    veto = "; ".join(f"{LABEL[s]} cleared its bound but its band held {100 * e['coverage_p10_p90']:.1f} percent, "
                     "over the 85 percent limit, so it is not shown" for _side, s, e in f["veto"])
    l2 = f["l2"]
    return {
        "id": "arrival_line", "term": "Arrival line", "category": "custom-index",
        "section": "Prospects", "module": ["prospx", "projections"],
        "aliases": ["arrival line", "prospect stat line", "If he reaches the majors",
                    "first three seasons if he reaches the majors"],
        "priority": 47,
        "definition": (f"The rates a hitter prospect is projected to post over his first three MLB seasons if he "
                       f"reaches the majors, with a P10 to P90 band, beside what his grade implies for the stat. "
                       f"Shown on /projections/ prospect rows and PROSPX hitter cards for the stats that passed a "
                       f"one-time check on players who debuted {f['span']}: {names}. Conditional on reaching MLB: "
                       "it is not a chance of reaching the majors, and it does not change his eFV or his "
                       "projected WAR."),
        "methodology": (f"Per stat, a ridge regression on the tool-implied value at his consensus grade (tables fit on "
                        "earlier debut classes only), the same table read at his FanGraphs present grade, and, for "
                        "xwOBA, the xwOBA prior from his pre-debut profile, with the penalty chosen by "
                        f"forward-chained cross-validation inside the {f['train']} debut classes. The band is the point "
                        "plus the 10th and 90th percentile of that cross-validation's out-of-sample misses. The served "
                        "fit is the one the look scored, refit on the same classes and checked against the look's "
                        "penalties, bands and coefficients before the file is written. Checked once on "
                        f"{f['span']} debuts (docs/proj-prospect-2026-10): {clauses}. "
                        f"The other {f['n_null']} rates (the rest of the hitter and all five pitcher rates) did not "
                        f"pass and are not shown{('; ' + veto) if veto else ''}. "
                        "Accuracy among players who reached the majors, not over all prospects. "
                        f"The first-three-season WAR assembled from the same inputs lost to the WAR path the site "
                        f"already serves (mean miss {_rate(l2['mae_model'], 2)} against {_rate(l2['mae_inc'], 2)} WAR, "
                        f"n {l2['n']}), so the WAR cells are unchanged. A stat is left off a player's line when none "
                        "of its inputs exists for him."),
        "formula": "arrival line(stat) = ridge(tool-implied value at his grade, tool-implied value at his present grade, xwOBA prior); P10 and P90 = point + out-of-sample miss quantiles",
        "seeAlso": ["tool_implied_production", "p10_p90_bands", "rookie_proxy", "proj_buckets", "xfv"],
        "shelf": "ark", "origin": ORIGIN,
    }


def registry_row(f: dict, current: dict | None) -> dict:
    names = " and ".join(LABEL[s] for _side, s, _e in f["passed"])
    base = (current or {}).get("notes", "")
    base = base.split(FLIP_MARK)[0]
    flip = (f"{FLIP_MARK} the arrival line for {names} is served under owner answer TL-Q6 (a), arrival line on both "
            "pages: data/prospect_statline.json, written by proj_export behind SERVE_PROSPECT_STATLINE (True), "
            "shown on the /projections/ prospect detail line and the PROSPX hitter card Signals section under the "
            f"heading 'If he reaches the majors, first three seasons'. The served fit is the look's fit "
            f"(debut classes {f['train']}, aging v2) and the exporter refuses to write the file unless it "
            "reproduces the look's penalties, bands and coefficients. Only the stats whose L1 verdict in the eval "
            "artifact is PASS are served, read from the artifact. The WAR cell stays the FV-anchored path (L2 "
            "INC retains), and a PASS on L2 would be an owner question. Never an eFV input, never a reserved eFV "
            "frame, never cut by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md).")
    return {
        "model_id": MODEL_ID,
        "summary": (f"Served: the {names} arrival lines beat their best baselines on {f['span']} debuts; "
                    f"{f['n_null']} other rates are NULL and WAR loses to the FV-anchored path."),
        "surface": ("/projections/ prospect detail line and the PROSPX hitter card (Signals), from "
                    "data/prospect_statline.json behind proj_export.SERVE_PROSPECT_STATLINE (True): "
                    f"{names} with P10 to P90 bands. The WAR cell stays the FV-anchored path"),
        "registration_status": (f"served 2026-10-21 (TL_18): hitter {names}; the other rates and the WAR leg "
                                "are not served"),
        "notes": base + flip,
    }


MODEL_GLOSSARY_LINE = '    "mlb_projections_prospects_statline": ["arrival_line"],'


def _read(path: Path):
    b = path.read_bytes()
    return b.decode("utf-8"), (b"\r\n" in b)


def _write(path: Path, text: str, crlf: bool) -> None:
    text = text.replace("\r\n", "\n")
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def apply_glossary(path: Path, entry: dict) -> list[str]:
    text, crlf = _read(path)
    g = json.loads(text)
    by = {e["id"]: e for e in g["entries"]}
    if entry["id"] in by:
        if by[entry["id"]] == entry:
            return []
        by[entry["id"]].clear()
        by[entry["id"]].update(entry)
        out = ["updated " + entry["id"]]
    else:
        g["entries"].append(dict(entry))
        out = ["added " + entry["id"]]
    _write(path, json.dumps(g, indent=1, ensure_ascii=False) + "\n", crlf)
    return out


def current_row(path: Path) -> dict | None:
    r = json.loads(_read(path)[0])
    return next((m for m in r["models"] if m["model_id"] == MODEL_ID), None)


def apply_registry(path: Path, row: dict) -> list[str]:
    text, crlf = _read(path)
    r = json.loads(text)
    by = {m["model_id"]: m for m in r["models"]}
    if row["model_id"] not in by:
        raise SystemExit("registry row " + row["model_id"] + " is missing; TL_11 writes it")
    cur = by[row["model_id"]]
    if all(cur.get(k) == v for k, v in row.items()):
        return []
    cur.update(row)
    _write(path, json.dumps(r, indent=1, ensure_ascii=False), crlf)
    return ["updated " + row["model_id"]]


def apply_model_glossary(path: Path) -> list[str]:
    text, crlf = _read(path)
    lf = text.replace("\r\n", "\n")
    anchor = '    "tool_source_accuracy": ["tool_above_grade", "tool_implied_production"],\n'
    assert lf.count(anchor) == 1, "MODEL_GLOSSARY anchor moved"
    if (MODEL_GLOSSARY_LINE + "\n") in lf:
        return []
    _write(path, lf.replace(anchor, anchor + MODEL_GLOSSARY_LINE + "\n"), crlf)
    return ["MODEL_GLOSSARY + " + MODEL_ID]


def copy_checks(row: dict, entry: dict) -> list[str]:
    bad = []
    ban = re.compile(r"\b(seamless|robust|delve|comprehensive|crucial|essential|powerful|showcase|utilize|unlock|"
                     r"elevate|game-changing|cutting-edge|tapestry|meticulous|underscore|harness|luck|due|regress|"
                     r"trending|clutch|sleeper|will)\b|leverage(?! index)", re.I)
    for obj in (row, entry):
        for k, v in obj.items():
            if not isinstance(v, str):
                continue
            if chr(8212) in v or chr(8211) in v:
                bad.append(f"dash in {k}")
            m = ban.search(v)
            if m:
                bad.append(f"banned word {m.group(0)!r} in {k}")
    if len(row["summary"].split()) > 30:
        bad.append("summary over 30 words")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(MODULE_ROOT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    f = figures(_read_eval(root))
    gl, reg, tf = root / "data" / "glossary.json", root / "data" / "model_registry.json", root / "test_methodology_freshness.py"
    entry = glossary_entry(f)
    row = registry_row(f, current_row(reg))
    bad = copy_checks(row, entry)
    if bad:
        print("COPY: " + "; ".join(bad))
        return 2
    if a.check:
        tmp = Path(tempfile.mkdtemp(prefix="statline_flip_check_"))
        (tmp / "data").mkdir()
        for src in (gl, reg):
            shutil.copy2(src, tmp / "data" / src.name)
        shutil.copy2(tf, tmp / tf.name)
        gl, reg, tf = tmp / "data" / "glossary.json", tmp / "data" / "model_registry.json", tmp / tf.name
    for label, fn in (("glossary", lambda: apply_glossary(gl, entry)), ("registry", lambda: apply_registry(reg, row)),
                      ("MODEL_GLOSSARY", lambda: apply_model_glossary(tf))):
        ch = fn()
        print(f"{label}: " + ("; ".join(ch) if ch else "no change"))
    row2 = registry_row(f, current_row(reg))
    again = apply_glossary(gl, entry) + apply_registry(reg, row2) + apply_model_glossary(tf)
    assert not again, "not idempotent: " + "; ".join(again)
    for p in (gl, reg):
        b = p.read_bytes()
        assert b"\r\n" in b and b"\n" not in b.replace(b"\r\n", b""), f"{p.name}: line endings not CRLF"
    sys.path.insert(0, str(root))
    import model_registry
    problems = model_registry.validate(json.loads(reg.read_bytes().decode("utf-8")))
    print("validate():", problems or "clean")
    ids = {e["id"] for e in json.loads(gl.read_bytes().decode("utf-8"))["entries"]}
    missing = sorted(set(entry["seeAlso"]) - ids)
    print("seeAlso unresolved:", missing or "none")
    return 1 if (problems or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
