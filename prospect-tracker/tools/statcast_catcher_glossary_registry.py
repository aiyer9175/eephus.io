# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Statcast catcher runs glossary entry and registry row (owner decision EW3-38).

Idempotent: a second run changes nothing. Keeps each file's line endings, its
one-space indent and the glossary's non-ASCII and trailing newline; refuses when a
plain round trip would rewrite either file. Reads data/statcast_catcher_runs.json
for the counts the registry row quotes, so build that first. Then regenerate the
generated docs:

    python statcast_catcher_export.py
    python tools/statcast_catcher_glossary_registry.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
PAYLOAD = ROOT / "data" / "statcast_catcher_runs.json"
GLOSSARY_AFTER = "catcher_throwing"
REGISTRY_AFTER = "savant_sprint"

ENTRY = {
    "id": "statcast_catcher_runs",
    "term": "Statcast catcher runs",
    "category": "statcast",
    "section": "Players & Stats",
    "module": ["mlbstats", "projections"],
    "aliases": ["Statcast runs", "SC Frm", "SC Blk", "SC Thr", "FRP at C", "Catcher Fielding Run Prevention"],
    "priority": 13,
    "definition": "The runs a catcher saved or cost at C in a season by Statcast's own count: framing (called strikes on borderline pitches), blocking (pitches in the dirt kept in front) and throwing (runners thrown out), and their total.",
    "methodology": "Statcast's run values as FanGraphs publishes them on the player's catcher row of its fielding leaderboard (fFRP, bFRP, tFRP and their total FRP), read by season from 2016 and carried verbatim in whole runs. The total equals the three parts within one run of rounding. Statcast blocking begins in 2018, so 2016 and 2017 show framing and throwing only. Statcast's framing number is not the FanGraphs framing column (Frm) the Fielding total carries. Shown on the /mlbstats/ Defense board (Catching view) and the player page's Defense tab as Statcast's public number: not computed, shrunk or validated here, and DEM+, eWAR and the team totals do not read it.",
    "formula": "Statcast runs at C = framing + blocking + throwing, as published",
    "seeAlso": ["framing_runs", "catcher_blocking", "catcher_throwing", "fielding_runs", "dem_plus"],
    "shelf": "industry",
    "origin": "Industry metric. MLB Statcast (Baseball Savant) catcher framing, blocking and throwing run values, as FanGraphs publishes them.",
}


def _row(payload: dict) -> dict:
    counts = payload.get("counts") or {}
    seasons = payload.get("seasons") or []
    n_rows = sum(int(v) for v in counts.values())
    n_players = len(payload.get("players") or {})
    span = f"{seasons[0]} to {seasons[-1]}" if seasons else "none"
    return {
        "model_id": "statcast_catcher_runs",
        "summary": "Measurement only: Statcast's published catcher runs (framing, blocking, throwing, total at C), displayed verbatim by season; no model claim, in no WAR.",
        "surface": "/mlbstats/ Defense board (Catching view, All, past seasons) and the /projections/ player page Defense tab; data/statcast_catcher_runs.json",
        "predicts": "Nothing: Statcast's own framing, blocking and throwing run values at C and their published total, per catcher-season, descriptive",
        "champion": "Statcast's published number (fFRP, bFRP, tFRP, FRP on the FanGraphs fielding leaderboard catcher row), carried verbatim",
        "baseline": "none: descriptive by design, a published measurement displayed as published; its forward reading lives in docs/sdr-2026-08-18/SDR_CATCHER_GATE.md and is quoted by no served sentence",
        "metric": "Refusing invariants, no forward claim: every input file carries the pinned columns, one catcher row per player and season, 40 to 300 catcher rows a season, innings in baseball notation; blocking null before 2018",
        "eval_artifact": "data/statcast_catcher_runs.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (
            "Owner decision EW3-38 (2026-10-16, SDR-CATCHER-Q1 options (b) and (d)), task STATCAST_CATCHER_RUNS. "
            "docs/sdr-2026-08-18/SDR_CATCHER_GATE.md read PARTIAL on 2026-10-16: SDR at catcher ties this series "
            "(E1 two-season persistence SDR 0.4315 against Statcast 0.4208, 244 pairs, LB95 of the gap -0.0624; "
            "on next-season DRS per inning at C, SDR's FRP reading 0.5160 against Statcast 0.5177) and beats only "
            "B-Ref rfield, so the owner chose to serve Statcast's own number as the catcher defense measurement, "
            "labelled as Statcast's. Those reads are the gate's, recorded here; the page quotes none of them. "
            f"Served {span}: {n_rows} catcher-seasons, {n_players} catchers, every catcher row with innings at C, "
            f"as of {payload.get('as_of')}. Built by statcast_catcher_export.py from the cached FanGraphs fielding "
            "leaderboard files the SDR intake fetched (.cache/sdr; refresh with python tools/sdr_inhouse.py fetch). "
            "The same series is registered as eWAR v3's catcher component S3c in docs/ebr-2026-09-30/EBR_GATE.md "
            "part 11.6, scored only by the skill look; nothing here enters eWAR, DEM+, Position Fit or the team totals."
        ),
        "last_checked": "2026-10-16",
    }


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def main() -> int:
    if not PAYLOAD.exists():
        print("refusing: data/statcast_catcher_runs.json is not built (python statcast_catcher_export.py first)")
        return 2
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    for path, key, coll, after, new in ((GLOSSARY, "id", "entries", GLOSSARY_AFTER, ENTRY),
                                        (REGISTRY, "model_id", "models", REGISTRY_AFTER, _row(payload))):
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if _render(raw, doc) != raw:
            print(f"refusing: a plain round trip would rewrite {path.name}")
            return 2
        rows = doc[coll]
        cur = next((r for r in rows if r.get(key) == new[key]), None)
        if cur == new:
            print(f"{path.name} already carries {new[key]}; nothing written")
            continue
        if cur is not None:
            rows[rows.index(cur)] = dict(new)
        else:
            idx = next((i for i, r in enumerate(rows) if r.get(key) == after), len(rows) - 1)
            rows.insert(idx + 1, dict(new))
        path.write_bytes(_render(raw, doc))
        print(f"{path.name}: wrote {new[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
