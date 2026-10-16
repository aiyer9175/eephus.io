# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast catcher runs: framing, blocking, throwing and their total, by season.

WHY THIS EXISTS (owner decision EW3-38, 2026-10-16, answering SDR-CATCHER-Q1
with options (b) and (d)). docs/sdr-2026-08-18/SDR_CATCHER_GATE.md read
PARTIAL: SDR at catcher ties Statcast's catcher runs and beats only B-Ref's
rfield. The owner chose to serve Statcast's own number as the catcher defense
measurement on the MLB Stats catcher board and the player pages, labelled as
Statcast's, with no model claim.

WHAT IS SERVED. Per catcher-season, the four Statcast catcher run values as
FanGraphs' fielding leaderboard publishes them on the player's catcher row:

    frm   fFRP   Statcast framing runs
    blk   bFRP   Statcast blocking runs (Statcast blocking begins in 2018;
                 FanGraphs prints 0 on every catcher row of 2016 and 2017, so
                 those seasons serve null, never 0)
    thr   tFRP   Statcast throwing runs
    tot   FRP    the published total at C (frm + blk + thr within one run of
                 rounding on every catcher row 2016 to 2026, SDR_CATCHER_GATE
                 part 0)
    inn          innings at C, converted from baseball thirds to decimal

That total is the series SDR_CATCHER_GATE scored as its incumbent I-S, and the
series docs/ebr-2026-09-30/EBR_GATE.md part 11.6 registers as eWAR v3's
catcher component S3c. Nothing here computes, shrinks or re-scales a value:
every number is the published whole run, carried verbatim.

INPUTS. The cached FanGraphs fielding leaderboard files
.cache/sdr/home/defense_plus/data/raw/fg_field_full_<season>.csv, fetched by
`python tools/sdr_inhouse.py fetch` (url, sha256 and fetch time per file in
.cache/sdr/fetch_manifest.json). This module reads the cache only and never
touches the network. A season whose file is missing is left out and named in
missing_seasons; a file whose shape changed is refused for that season.

DISPLAY ONLY. DEM+, eWAR, Position Fit, the team rollups and the betting model
do not read this file. It enters eWAR v3 only through the skill look of
EBR_GATE.md part 11.6, which reads the same cached files itself.

DETERMINISTIC. as_of is the newest fetch time among the files read, so the
same cache always writes the same bytes.

Run:  python statcast_catcher_export.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
RAW = ROOT / ".cache" / "sdr" / "home" / "defense_plus" / "data" / "raw"
MANIFEST = ROOT / ".cache" / "sdr" / "fetch_manifest.json"
OUT = ROOT / "data" / "statcast_catcher_runs.json"

FIRST_SEASON = 2016
LAST_SEASON = 2026
BLOCKING_FIRST_SEASON = 2018
REQUIRED = ("xMLBAMID", "Season", "Pos", "Inn", "fFRP", "bFRP", "tFRP", "FRP")
CATCHER_ROWS = (40, 300)
FIELDS = ["season", "inn", "frm", "blk", "thr", "tot"]

LABEL = "Statcast catcher runs"
SOURCE = ("Statcast catcher run values (Baseball Savant framing, blocking and throwing), "
          "as FanGraphs' fielding leaderboard publishes them on the catcher row (fFRP, bFRP, tFRP, FRP)")
CLAIM = ("Statcast's public number, carried verbatim: a measurement, not computed, shrunk or "
         "validated here. DEM+, eWAR and the team totals do not read it.")


class ShapeChanged(ValueError):
    """A cached file no longer has the columns or rows this module reads."""


def _num(v) -> Optional[float]:
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def innings_from_thirds(v) -> Optional[float]:
    """FanGraphs prints innings in baseball notation (995.2 is 995 and two
    thirds). Returns decimal innings to one place; refuses any other fraction."""
    x = _num(v)
    if x is None:
        return None
    whole = int(x)
    outs = round((x - whole) * 10)
    if outs not in (0, 1, 2) or abs((x - whole) * 10 - outs) > 1e-6:
        raise ShapeChanged(f"innings {v!r} is not in baseball notation")
    return round(whole + outs / 3.0, 1)


def _whole(v) -> Optional[int]:
    x = _num(v)
    return None if x is None else int(round(x))


def parse_season(text: str, season: int) -> list[list]:
    """The catcher rows of one season's fielding leaderboard, as FIELDS lists."""
    rdr = csv.DictReader(text.splitlines())
    head = set(rdr.fieldnames or ())
    missing = [c for c in REQUIRED if c not in head]
    if missing:
        raise ShapeChanged(f"{season}: missing columns {missing}")
    out: dict[int, list] = {}
    for r in rdr:
        if str(r.get("Pos") or "").strip() != "C":
            continue
        if _whole(r.get("Season")) != int(season):
            raise ShapeChanged(f"{season}: a catcher row is stamped {r.get('Season')!r}")
        mid = _whole(r.get("xMLBAMID"))
        if mid is None or mid <= 0:
            continue
        inn = innings_from_thirds(r.get("Inn"))
        if not inn:
            continue
        if mid in out:
            raise ShapeChanged(f"{season}: two catcher rows for mlbam {mid}")
        blk = _whole(r.get("bFRP")) if season >= BLOCKING_FIRST_SEASON else None
        out[mid] = [int(season), inn, _whole(r.get("fFRP")), blk, _whole(r.get("tFRP")), _whole(r.get("FRP"))]
    if not CATCHER_ROWS[0] <= len(out) <= CATCHER_ROWS[1]:
        raise ShapeChanged(f"{season}: {len(out)} catcher rows outside {CATCHER_ROWS}")
    return [[mid] + row for mid, row in sorted(out.items())]


def build(raw_dir: Path = RAW, manifest_path: Path = MANIFEST,
          seasons: range = range(FIRST_SEASON, LAST_SEASON + 1)) -> Optional[dict]:
    """The payload, or None when no season could be read."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    players: dict[str, list] = {}
    counts: dict[str, int] = {}
    inputs: dict[str, dict] = {}
    missing: list[int] = []
    refused: dict[str, str] = {}
    fetched: list[str] = []
    for s in seasons:
        name = f"fg_field_full_{s}.csv"
        path = Path(raw_dir) / name
        if not path.exists():
            missing.append(s)
            continue
        try:
            rows = parse_season(path.read_text(encoding="utf-8-sig"), s)
        except (OSError, ShapeChanged) as exc:
            refused[str(s)] = str(exc)
            continue
        for row in rows:
            players.setdefault(str(row[0]), []).append(row[1:])
        counts[str(s)] = len(rows)
        meta = manifest.get(name) or {}
        inputs[str(s)] = {"file": name, "fetched_at": meta.get("fetched_at"),
                          "sha256": (meta.get("raw_sha256") or "")[:16] or None,
                          "url": meta.get("url")}
        if meta.get("fetched_at"):
            fetched.append(meta["fetched_at"])
    if not counts:
        return None
    as_of = max(fetched)[:10] if fetched else None
    return {
        "label": LABEL,
        "as_of": as_of,
        "source": SOURCE,
        "claim": CLAIM,
        "producer": "python statcast_catcher_export.py (reads .cache/sdr; refresh with python tools/sdr_inhouse.py fetch)",
        "seasons": sorted(int(s) for s in counts),
        "blocking_first_season": BLOCKING_FIRST_SEASON,
        "missing_seasons": missing,
        "refused_seasons": refused,
        "counts": counts,
        "columns": {
            "season": "season",
            "inn": "innings at C, decimal",
            "frm": "Statcast framing runs (fFRP)",
            "blk": "Statcast blocking runs (bFRP); null before 2018, when Statcast blocking begins",
            "thr": "Statcast throwing runs (tFRP)",
            "tot": "Statcast catcher runs at C as published (FRP)",
        },
        "units": "runs, whole numbers as published; positive saved runs",
        "scope": "every catcher row with innings at C, all catchers, no innings floor",
        "use": "display only on the /mlbstats/ Defense board (Catching view) and the player pages; DEM+, eWAR, Position Fit and the team rollups do not read it",
        "inputs": inputs,
        "fields": FIELDS,
        "players": {k: players[k] for k in sorted(players, key=int)},
    }


def render(doc: dict) -> str:
    """The metadata indented, one line per catcher: about 60 KB, not 600."""
    meta = {k: v for k, v in doc.items() if k != "players"}
    head = json.dumps(meta, indent=1, ensure_ascii=False)
    lines = [f" {json.dumps(k)}: {json.dumps(v, separators=(',', ':'))}"
             for k, v in doc.get("players", {}).items()]
    body = ' "players": {' + ("\n" + ",\n".join(lines) + "\n }" if lines else "}")
    return head[:-2] + ",\n" + body + "\n}\n"


def write(out: Path = OUT, **kw) -> Optional[dict]:
    doc = build(**kw)
    if doc is None:
        print("  [warn] statcast catcher runs: no season readable; the served file is kept")
        return None
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    text = render(doc)
    try:
        if Path(out).read_text(encoding="utf-8") == text:
            return doc
    except OSError:
        pass
    Path(out).write_text(text, encoding="utf-8", newline="\n")
    return doc


def main(argv: list[str]) -> int:
    doc = write()
    if doc is None:
        return 1
    n = sum(doc["counts"].values())
    print(f"  statcast catcher runs: {n} catcher-seasons, {len(doc['players'])} catchers, "
          f"seasons {doc['seasons'][0]} to {doc['seasons'][-1]}, as of {doc['as_of']} -> {OUT.relative_to(ROOT)}")
    if doc["missing_seasons"] or doc["refused_seasons"]:
        print(f"  missing {doc['missing_seasons']}, refused {doc['refused_seasons']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
