#!/usr/bin/env python
"""The per club-season decision shards behind the /management/ drill-down.

ONE SHARD PER CLUB-SEASON, data/mgmt_decisions/{season}-{club}.json, so the board file
stays small and the drill-down loads one shard on demand. A shard is the full ledger of
that club-season: every decision with its window (the plays it governed, with the feed's
win probability before and after each), its realized mWPA and, where the matched-state
cell is thick enough, its value above state (DVS). Names are resolved at export from the
daily WAR frames and player_links.json; nothing is fetched.

OWNER DECISION OPEN (spec 14.1): whether the shards are tracked in git or generated on
the box. This writer does neither; it writes the files and returns the index the board
publishes, and the deploy rules ship the directory either way.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARD_DIR = ROOT / "data" / "mgmt_decisions"

_NAME_RE = re.compile(r"^(\d{4})-([A-Z]{2,3})\.json$")

SCHEMA_NOTE = (
    "one row per decision: id (game_pk:at_bat_index:event index, -1 for a play-result "
    "decision), date (local, from the feed's first play), game_pk, ab, idx, half, inning, "
    "outs, base (three-bit code: 1 first, 2 second, 4 third), score_diff (the deciding "
    "club's lead before the play), li (MLB feed leverage index; null on the leadoff plate "
    "appearance), family, kind, in_id / out_id and names, slot, pos, mwpa (wins, realized "
    "value, not skill: the window's endpoint difference in win probability, sign to the "
    "deciding club), dvs (wins above the matched-state league baseline; null in a thin "
    "cell), win_len (plays in the window), flags, window (the plays governed, each as "
    "[ab, event, wp_before, wp_after] with wp in percentage points); null-valued keys are "
    "omitted. Family extras ride beside: pitch_count and tto of "
    "the removed pitcher, inherited runners and inherited_scored (derived), first_pa_mwpa, "
    "walk_only_mwpa, the steal's model dv / er / realized_delta beside the feed's mwpa, "
    "the bunt's league dv_cell beside its realized figure.")


def shard_name(season, club: str) -> str:
    return f"{int(season)}-{club}.json"


def _sort_key(r: dict):
    return (r.get("date") or "", int(r.get("game_pk") or 0), int(r.get("ab") or 0), int(r.get("idx") or 0))


#: Row keys the shard header already states (season, club) or the reader derives
#: (id = game_pk:ab:idx; kind defaults to the family; empty flags and windows are
#: omitted). Measured 2026-09-23: the row scaffolding, not the windows, is four
#: fifths of a shard, so the compaction is on the scaffolding.
_HEADER_KEYS = ("season", "club", "id")


def compact_row(r: dict) -> dict:
    out = {}
    for k, v in r.items():
        if k in _HEADER_KEYS or v is None:
            continue
        if k in ("flags", "window") and not v:
            continue
        if k == "kind" and v == r.get("family"):
            continue
        out[k] = v
    return out


def write_season(rows: list, out_dir: Path | None = None, season=None) -> list:
    """Write one shard per club found in `rows` (one season). Returns the index rows
    [{season, club, n, bytes}]. Rows are copied and compacted; the caller's rows are
    left whole."""
    out_dir = Path(out_dir or SHARD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_club: dict = {}
    for r in rows:
        by_club.setdefault(r["club"], []).append(r)
    index = []
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for club in sorted(by_club):
        rs = [compact_row(r) for r in sorted(by_club[club], key=_sort_key)]
        s = int(season if season is not None else by_club[club][0]["season"])
        p = out_dir / shard_name(s, club)
        payload = {"season": s, "club": club, "n": len(rs), "generated_at": stamp,
                   "produced_by": "mgmt_shards.py", "schema_note": SCHEMA_NOTE,
                   "row_keys_omitted": ("season and club (this header), id (game_pk:ab:idx), "
                                        "kind when it equals the family, empty flags and "
                                        "windows, null values"),
                   "rows": rs}
        p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index.append({"season": s, "club": club, "n": len(rs), "bytes": p.stat().st_size})
    return index


def prune(out_dir: Path | None, keep: set) -> list:
    """Remove shards this run did not write (a renamed club, a dropped season). Only
    files shaped like a shard are touched."""
    out_dir = Path(out_dir or SHARD_DIR)
    removed = []
    if not out_dir.exists():
        return removed
    for p in out_dir.iterdir():
        m = _NAME_RE.match(p.name)
        if not m:
            continue
        if (int(m.group(1)), m.group(2)) not in keep:
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                continue
    return removed


def index_on_disk(out_dir: Path | None = None) -> list:
    """What is actually on disk, for the test that matches the index to the files."""
    out_dir = Path(out_dir or SHARD_DIR)
    out = []
    if not out_dir.exists():
        return out
    for p in sorted(out_dir.iterdir()):
        m = _NAME_RE.match(p.name)
        if m:
            out.append({"season": int(m.group(1)), "club": m.group(2), "bytes": p.stat().st_size})
    return out
