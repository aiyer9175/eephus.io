#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The glossary entry, registry row and MODEL_GLOSSARY mapping of level-relative eBR
(EBR_Q6B_MILB_CARDS, the flip commit). Idempotent: a second run changes nothing.
Preserves each file's line endings (CRLF) and indent (1), the glossary's non-ASCII
and trailing newline, the registry's absence of one. Every figure printed in the copy
is read from data/ebr_milb_eval.json.

Usage (from the module root, after data/ebr_milb_eval.json exists):
    python tools/ebr_milb_flip_registry.py --check     # dry run into a temp dir, validates
    python tools/ebr_milb_flip_registry.py             # apply

Writes data/glossary.json (entry ebr_milb), data/model_registry.json (row ebr_milb,
provisional, measurement_only) and test_methodology_freshness.py (MODEL_GLOSSARY).
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
DOC = "docs/ebr-2026-09-30/EBR_MILB.md"
GATE = "docs/ebr-2026-09-30/EBR_GATE.md"


def _read_eval(root: Path) -> dict:
    return json.loads((root / "data" / "ebr_milb_eval.json").read_text(encoding="utf-8"))


def figures(ev: dict) -> dict:
    rel = {k: v.get("spearman_brown") for k, v in ev["reliability_split_half"].items()}
    upper = [v for k, v in rel.items() if not k.startswith("rookie") and v is not None]
    rookie = [v for k, v in rel.items() if k.startswith("rookie") and v is not None]
    ident = ev["identity"]
    sb_rel = max(v["I1"]["sb_rel_diff"] for v in ident.values())
    cs_rel = max(v["I1"]["cs_rel_diff"] for v in ident.values())
    share = min(v["I2"]["sb_cs_exact_share"] for v in ident.values())
    gshare = min(v["I2"]["gidp_exact_share"] for v in ident.values())
    exact = sorted(k for k, v in ident.items() if v["I1"]["exact"])
    units = ev["units"]
    return {
        "n_units": len(units),
        "upper": (min(upper), max(upper)), "rookie": (min(rookie), max(rookie)),
        "sb_rel_pct": round(100 * max(sb_rel, cs_rel), 3), "player_share_pct": round(100 * share, 2),
        "gidp_share_pct": round(100 * gshare, 2), "exact_units": exact,
        "pairs": ev["continuity"]["all_pairs"]["n"], "pairs_r": ev["continuity"]["all_pairs"]["r"],
        "players_150": sum(u["players_150"] for u in units.values()),
        "all_pass": all(v["all_pass"] for v in ident.values()),
    }


def glossary_entry(f: dict) -> dict:
    return {
        "id": "ebr_milb", "term": "Level-relative eBR (minor leagues)", "category": "custom-index",
        "section": "Prospects", "module": ["prospx"],
        "aliases": ["MiLB eBR", "level-relative baserunning", "minor-league baserunning runs",
                    "Baserunning, level-relative"],
        "priority": 48,
        "definition": ("Runs a prospect added or cost on the bases in one minor-league season against an average "
                       "runner at the same level in the same season: stealing, taking the extra base, and staying "
                       "out of double plays, counted from minor-league play-by-play. Shown on PROSPX prospect pages "
                       "for each level and season at 150 or more plate appearances. Descriptive: what happened, "
                       "not a forecast, and never part of a grade, rank or projection."),
        "methodology": ("The same five parts as eBR (steals, pickoffs, advancement and outs on the bases, double "
                        "plays), priced on a run-expectancy table fitted to that level and season and shrunk toward "
                        "the level's pooled table (or toward all of the minors that season where a level has one "
                        "season of play-by-play on file), with every part centred to zero within the level and "
                        "season. A runner is compared with the average runner of his own league-season, so the "
                        "minors' rule changes (pickoff limits, bigger bases, the pitch clock) are absorbed, and the "
                        "number is not comparable across levels or with MLB's eBR in runs. Advances on wild pitches "
                        "and passed balls are counted beside it and are not in it. Each level-season is checked "
                        "against the official season lines: league stolen bases and caught stealing within "
                        f"{f['sb_rel_pct']} percent and exact for {f['player_share_pct']} percent or more of the "
                        "players who have any. One season is a noisy reading: the split-half reliability of runs at "
                        f"150 plate appearances is {f['upper'][0]:.2f} to {f['upper'][1]:.2f} at AAA through "
                        f"Single-A and {f['rookie'][0]:.2f} to {f['rookie'][1]:.2f} at Rookie, and prints in each "
                        "row's tooltip. On file: Single-A and Rookie 2023 to 2026, AAA, AA and High-A 2026."),
        "formula": "level-relative eBR = SB runs + XB runs + DP runs, each centred to zero over every runner of the level and season",
        "seeAlso": ["ebr", "ebr_sb", "ebr_xb", "ebr_dp", "milb_fielding_runs"],
        "shelf": "ark", "origin": ORIGIN,
    }


def registry_row(f: dict) -> dict:
    return {
        "model_id": "ebr_milb",
        "summary": ("Descriptive: runs above an average runner at the same level and season on the minor-league "
                    f"bases, from play-by-play; official steal counts match within {f['sb_rel_pct']} percent. "
                    "Measurement only."),
        "surface": ("PROSPX prospect pages, the Baserunning, level-relative block in Signals (one row per level and "
                    "season at 150 or more plate appearances, position players), from data/ebr_milb.json"),
        "predicts": ("nothing forward; DESCRIPTIVE runs above an average runner at the same level in the same season "
                     "from the minor-league per-runner play-by-play: SB runs + XB runs + DP runs"),
        "champion": ("ebr_milb_v1 (" + DOC + "): eBR's five parts with s = (level, season): RE24 per level-season "
                     "shrunk toward the level's pooled table or the season's all-MiLB table, K by the method of "
                     "moments clipped to [500, 5000], outcome backoff level-season to level to all MiLB, every part "
                     "centred to zero per level-season; advances on balls in the dirt reported as W and never in "
                     "the number"),
        "baseline": ("n/a, descriptive; the official StatsAPI minor-league season hitting lines (SB, CS and GIDP, "
                     "fetched once per level-season) which the record is scored against and never seeded from"),
        "metric": ("descriptive: league SB and CS within 0.1 percent of the official lines and exact for 99 percent "
                   "of players with any, GIDP within 0.5 percent and exact for 97 percent (I1, I2), record complete "
                   "(I3), zero league sums (I4), monotone RE24 (I5), row identity (I6), coverage (I7), "
                   "determinism (I8), isolation (I9); split-half reliability and cross-level continuity reported"),
        "eval_artifact": "data/ebr_milb_eval.json",
        "verdict": "provisional", "provisional_kind": "measurement_only",
        "notes": ("Built dark by EBR_Q6B_MILB_CARDS and served in one flip commit (owner answer EBR-Q6 (b), "
                  "2026-10-01: show it on prospect cards, per level and season at 150 or more plate appearances, "
                  f"display only). {f['n_units']} level-seasons, {f['players_150']} player-seasons at 150 or more "
                  f"plate appearances, every level-season passing I1 to I9 ({'yes' if f['all_pass'] else 'NO'}). "
                  "The minor-league bounds are looser than MLB's exact match because a few official steals are "
                  "scorer decisions the feed's runner entries do not carry; league SB and CS are exact in "
                  f"{len(f['exact_units'])} of {f['n_units']} level-seasons. Reliability is low at Rookie and "
                  f"moderate elsewhere (split-half {f['upper'][0]:.2f} to {f['upper'][1]:.2f} above Rookie). Never "
                  "an eFV input (no efv_ module reads it; a driver test would be a separate registration under "
                  "docs/efv-v2/DRIVER_SYSTEM_V2.md, not before EFV_V2_GATE.md is final), never a reserved eFV "
                  "frame, never summarised, validated or stratified by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md). "
                  "Level-relative: not comparable across levels or with MLB's eBR in runs.")}


MODEL_GLOSSARY_LINE = '    "ebr_milb": ["ebr_milb"],'


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


def apply_registry(path: Path, row: dict) -> list[str]:
    text, crlf = _read(path)
    r = json.loads(text)
    by = {m["model_id"]: m for m in r["models"]}
    if row["model_id"] in by:
        cur = by[row["model_id"]]
        if all(cur.get(k) == v for k, v in row.items()):
            return []
        cur.update(row)
        out = ["updated " + row["model_id"]]
    else:
        r["models"].append(dict(row))
        out = ["added " + row["model_id"]]
    _write(path, json.dumps(r, indent=1, ensure_ascii=False), crlf)
    return out


def apply_model_glossary(path: Path) -> list[str]:
    text, crlf = _read(path)
    lf = text.replace("\r\n", "\n")
    anchor = '    "team_ebr": ["team_ebr"],\n'
    assert lf.count(anchor) == 1, "MODEL_GLOSSARY anchor moved"
    if (MODEL_GLOSSARY_LINE + "\n") in lf:
        return []
    _write(path, lf.replace(anchor, anchor + MODEL_GLOSSARY_LINE + "\n"), crlf)
    return ["MODEL_GLOSSARY + ebr_milb"]


def copy_checks(row: dict, entry: dict) -> list[str]:
    bad = []
    ban = re.compile(r"\b(seamless|robust|delve|comprehensive|crucial|essential|powerful|showcase|utilize|unlock|"
                     r"elevate|game-changing|cutting-edge|tapestry|meticulous|underscore|harness|luck|due|regress|"
                     r"trending|clutch|sleeper)\b|leverage(?! index)", re.I)
    for obj in (row, entry):
        for k, v in obj.items():
            if not isinstance(v, str):
                continue
            if "—" in v or "–" in v:
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
    entry, row = glossary_entry(f), registry_row(f)
    bad = copy_checks(row, entry)
    if bad:
        print("COPY: " + "; ".join(bad))
        return 2
    gl, reg, tf = root / "data" / "glossary.json", root / "data" / "model_registry.json", root / "test_methodology_freshness.py"
    if a.check:
        tmp = Path(tempfile.mkdtemp(prefix="ebr_milb_flip_check_"))
        (tmp / "data").mkdir()
        for src in (gl, reg):
            shutil.copy2(src, tmp / "data" / src.name)
        shutil.copy2(root / "data" / "ebr_milb_eval.json", tmp / "data" / "ebr_milb_eval.json")
        shutil.copy2(tf, tmp / tf.name)
        gl, reg, tf = tmp / "data" / "glossary.json", tmp / "data" / "model_registry.json", tmp / tf.name
    for label, fn in (("glossary", lambda: apply_glossary(gl, entry)), ("registry", lambda: apply_registry(reg, row)),
                      ("MODEL_GLOSSARY", lambda: apply_model_glossary(tf))):
        ch = fn()
        print(f"{label}: " + ("; ".join(ch) if ch else "no change"))
    again = apply_glossary(gl, entry) + apply_registry(reg, row) + apply_model_glossary(tf)
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
