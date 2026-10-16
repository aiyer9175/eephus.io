"""Add the MiLB fielding runs (MFR) entry to data/glossary.json (idempotent).

Task MILB_FIELDING_RUNS (docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md part 6, a licensed
glossary entry after estimand (b) passed). Keeps the file's CRLF line endings, its one-space
indent and its non-ASCII characters; refuses when a plain round trip would rewrite the file.
Running it twice changes nothing.

    python tools/add_milb_fielding_runs_glossary.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"

ENTRY = {
    "id": "milb_fielding_runs",
    "term": "MiLB fielding runs (MFR)",
    "category": "custom-index",
    "section": "Prospects",
    "module": ["prospx"],
    "aliases": ["MFR", "MiLB fielding runs", "MiLB Fielding Runs", "minor-league fielding runs"],
    "priority": 47,
    "definition": ("A minor-league fielding reading in runs: how many runs a player's fielding saved "
                   "or cost per 1,000 innings at a position against the average fielder at the "
                   "same level and season, from MiLB play-by-play 2021 to 2026, shrunk by "
                   "reliability and put on an AAA-equivalent scale. Shown on PROSPX prospect pages "
                   "by position; never in a grade, rank or sort."),
    "methodology": ("Every ball in play gets an expected out rate from balls of the same trajectory, "
                    "hardness, spray angle (5-degree bins) and distance (30-foot bins, air balls) at "
                    "that level, and each position's share of the outs made in that zone. A fielder "
                    "who turns a ball into an out earns the part of it his position was not expected "
                    "to make; a ball that falls costs each responsible position its expected share, "
                    "in runs (the gap between the zone's hits and an out). Infielders add double "
                    "plays turned against the level rate, outfielders add runner kills and extra "
                    "bases allowed on hits they field, and catchers add called strikes on tracked "
                    "pitches (AAA 2023 on, the Florida State League) and caught stealing. Every part "
                    "is zeroed within level, season and position. The total is shrunk toward zero by "
                    "innings over innings plus a split-half constant per position, and lower levels "
                    "are scaled to AAA by players seen at two levels in the same season. Its "
                    "pre-registered gate found that pre-debut MFR ranks later MLB fielding runs "
                    "(B-Ref rfield and Statcast OAA) for players who debuted 2022 to 2024; the "
                    "numbers and their intervals print in the card's tooltip from the gate's eval "
                    "artifact. The gate could not show that MFR adds to the scouting field grade."),
    "formula": ("runs on a ball in play, position k = (1[k made the out] - p_zone x share_k) x "
                "run gap of the zone\nMFR = 1,000 x sum over levels (F_level x runs) / (innings + k_pos)"
                "\nreliability = innings / (innings + k_pos); bands: low under 0.35, medium under "
                "0.60, high"),
    "example": ("A shortstop at +4.0 over 800 innings, high reliability, saved about four runs per "
                "1,000 innings more than an average AAA shortstop would on the same balls."),
    "seeAlso": ["field_tool", "def_home_chip", "fielding_runs", "d_tool"],
    "shelf": "ark",
    "origin": ("Arkmetric, original to eephus.io (MILB_FIELDING_RUNS gate, "
               "tools/milb_fielding_runs.py), built on MLB StatsAPI play-by-play."),
}


def main() -> int:
    raw = GLOSSARY.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))

    def render(d) -> bytes:
        text = json.dumps(d, indent=1, ensure_ascii=False)
        if crlf:
            text = text.replace("\n", "\r\n")
        if raw.endswith(b"\n"):
            text += "\r\n" if crlf else "\n"
        return text.encode("utf-8")

    if render(doc) != raw:
        print("refusing: a plain round trip would rewrite data/glossary.json")
        return 2
    entries = doc["entries"]
    cur = next((e for e in entries if e.get("id") == ENTRY["id"]), None)
    if cur == ENTRY:
        print("glossary already carries milb_fielding_runs; nothing written")
        return 0
    if cur is None:
        entries.append(dict(ENTRY))
    else:
        cur.clear()
        cur.update(ENTRY)
    GLOSSARY.write_bytes(render(doc))
    print("glossary written: milb_fielding_runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
