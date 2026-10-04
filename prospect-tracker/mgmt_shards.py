#!/usr/bin/env python
"""The per club-season decision shards behind the /management/ drill-down.

ONE SHARD PER CLUB-SEASON, data/mgmt_decisions/{season}-{club}.json, so the board file
stays small and the drill-down loads one shard on demand. A shard is the full ledger of
that club-season: every decision with its window (the plays it governed, with the feed's
win probability before and after each), its realized mWPA and, where the matched-state
cell is thick enough, its value above state (DVS). Names are resolved at export from the
daily WAR frames and player_links.json; nothing is fetched.

SCHEMA 2 (2026-09-23): COMPACTED SO THE OWNER CAN TRACK THE SET IN GIT. The schema-1
shards were dict rows that repeated every key, the game's date, opponent and home flag
and every player name on every row: 157 MB over 240 shards. Each step below was measured
on 2025-NYY (1,522 rows, 710 KB) and then cumulatively on the whole set:

    schema 1 as written                                           157.07 MB
    (a) game table {game_pk: [date, opp, home]}, rows drop three  144.69 MB
    (b) name table {player_id: name}, rows carry ids only         129.29 MB
    (c) array rows under a per-family key legend                   70.07 MB
    (d) event code table for the window plays                      57.27 MB
    (f) half as 0/1                                                55.63 MB
    (g) window chain: [event, wp_after], wp_before written only
        where the feed's chain breaks (2.6 percent of plays); the
        play's ab is the row's ab plus its offset (0 gaps in 1.5M)  45.30 MB
    (f) kinds and flags coded, win_len derived (this writer)       41.50 MB
    (e) mound visits as per-game counts per pitcher: measured at a
        further 1.54 MB on top of (g) and NOT taken, because the
        drill-down lists every visit with its situation and LI

The reader (assets/management.js expandShard, and expand() below for the tests) rebuilds
the schema-1 row dicts, so every renderer downstream is unchanged and the page prints
the same values to the character. There is one reader and no legacy path: the shards
are regenerated on every corpus rebuild and tracked in git.

OWNER DECISION (spec 14.1, taken 2026-09-23): compacted first, then TRACKED in git
(41.5 MB over 240 files), like the board, so the box serves the drill-down before its
first nightly. This writer writes the files and returns the index the board publishes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARD_DIR = ROOT / "data" / "mgmt_decisions"

_NAME_RE = re.compile(r"^(\d{4})-([A-Z]{2,3})\.json$")

SCHEMA_VERSION = 2

SCHEMA_NOTE = (
    "schema 2: one array per decision under its family's key legend (families.<family>.keys, "
    "a trailing run of nulls trimmed). Fields: game_pk (key into games, whose entry is [date "
    "(local, from the feed's first play), opponent, home as 1/0]), ab, idx (event index in the "
    "plate appearance, -1 for a play-result decision; the decision id is game_pk:ab:idx), half "
    "(0 top, 1 bottom), inning, outs, base (three-bit code: 1 first, 2 second, 4 third), "
    "score_diff (the deciding club's lead before the play), li (MLB feed leverage index; null "
    "on the leadoff plate appearance), kind (index into kinds; absent when it equals the "
    "family), in_id / out_id / pitcher_id / due_id / ondeck_id (the names table keys them; a "
    "row carries ids only), slot, pos, mwpa (wins, realized value, not skill: the window's "
    "endpoint difference in win probability, sign to the deciding club), dvs (wins above the "
    "matched-state league baseline; null in a thin cell), flags (indexes into flags), window "
    "(the plays governed, each [event index into events, wp_after] or [event, wp_after, "
    "wp_before] where the feed's chain breaks, the first play always carrying wp_before, wp in "
    "percentage points; the play's ab is the row's ab plus its offset; win_len is the window's "
    "length, 0 for a counted family and for the steal, which happens between plays). Family "
    "extras ride beside: pitch_count and tto of the removed pitcher, inherited runners and "
    "inherited_scored (derived), first_pa_mwpa, walk_only_mwpa, the steal's model dv / er / "
    "realized_delta (its mwpa is that realized_delta, the steal itself, and it has no dvs), "
    "the bunt's league dv_cell beside its realized figure.")

#: Family order, the detection order of mgmt_decisions.build_season: rows that tie on
#: the sort key (a steal and a bunt in one plate appearance, both idx -1) resolve in
#: this order on both sides of the codec.
FAMILY_ORDER = ("pitching_change", "pinch_hit", "pinch_run", "defensive_sub",
                "intentional_walk", "bunt", "steal", "mound_visit", "ejection")
#: Row keys the shard header already states (season, club) or the reader derives
#: (id = game_pk:ab:idx; kind defaults to the family; empty flags and windows are
#: omitted).
_HEADER_KEYS = ("season", "club", "id")
#: The name the reader attaches beside each id field, from the names table.
NAME_OF = {"in_id": "in_name", "out_id": "out_name", "pitcher_id": "pitcher_name",
           "due_id": "due_name", "ondeck_id": "ondeck_name"}
#: Per-game fields, held once in the games table.
GAME_KEYS = ("date", "opp", "home")
#: Fields the reader derives and no row carries.
DERIVED = GAME_KEYS + ("win_len",) + tuple(NAME_OF.values())
#: The state keys every family carries, first in every legend.
_STATE_KEYS = ("game_pk", "ab", "idx", "half", "inning", "outs", "base", "score_diff", "li")
#: The finalise emit order of the other keys, for ties in presence.
_KEY_ORDER = ("kind", "in_id", "out_id", "slot", "pos", "mwpa", "dvs", "flags", "window",
              "pitch_count", "tto", "inherited", "inherited_scored", "first_pa_mwpa",
              "batter_side", "pitcher_hand", "due_id", "out_side", "pitcher_id",
              "entry_base", "ondeck_id", "ondeck_side", "walk_only_mwpa", "dv_cell", "dv",
              "er", "realized_delta", "breakeven_p", "success", "ejected_name")
HALF = ("top", "bottom")

LEGEND = {
    "row": ("one array per decision under families.<family>.keys; a trailing run of nulls "
            "is trimmed; the family is the block key"),
    "games": "game_pk -> [date, opponent, home (1 home, 0 away)]",
    "names": "player id -> name; rows carry ids only (in_id, out_id, pitcher_id, due_id, ondeck_id)",
    "events": "window event strings by index",
    "kinds": "kind strings by index",
    "flags": "flag strings by index",
    "half": list(HALF),
    "window": ("[event, wp_after] or [event, wp_after, wp_before] where the chain breaks "
               "(the first play always carries wp_before); a fourth element, if present, "
               "is the play's ab where it is not the row's ab plus the offset"),
}


def shard_name(season, club: str) -> str:
    return f"{int(season)}-{club}.json"


def _sort_key(r: dict):
    return (r.get("date") or "", int(r.get("game_pk") or 0), int(r.get("ab") or 0), int(r.get("idx") or 0))


def compact_row(r: dict) -> dict:
    """The schema-1 row: header keys, null values, empty flags and windows and a kind
    that equals the family dropped. expand() reproduces exactly this shape."""
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


def _code(table: list, index: dict, v):
    if v not in index:
        index[v] = len(table)
        table.append(v)
    return index[v]


def _code_window(window: list, row_ab: int, events: list, ev_ix: dict) -> list:
    """[ab, event, wp_before, wp_after] per play -> [event, wp_after] (+ wp_before where
    the chain breaks or on the first play; + ab where it is not row_ab + offset)."""
    out = []
    prev = None
    for k, p in enumerate(window):
        ab, ev, wpb, wpa = p
        e = _code(events, ev_ix, ev)
        if k > 0 and wpb is not None and wpb == prev and ab == row_ab + k:
            out.append([e, wpa])
        elif ab == row_ab + k:
            out.append([e, wpa, wpb])
        else:
            out.append([e, wpa, wpb, ab])
        prev = wpa
    return out


def _decode_window(coded: list, row_ab: int, events: list) -> list:
    out = []
    prev = None
    for k, p in enumerate(coded):
        wpb = p[2] if len(p) > 2 else prev
        ab = p[3] if len(p) > 3 else row_ab + k
        out.append([ab, events[p[0]], wpb, p[1]])
        prev = p[1]
    return out


def compact_season(rows: list, season, club: str, stamp: str | None = None) -> dict:
    """The schema-2 payload of ONE club-season from its finalised rows (any order; the
    caller's rows are left whole)."""
    rs = [compact_row(r) for r in sorted(rows, key=_sort_key)]
    games: dict = {}
    names: dict = {}
    events: list = []
    kinds: list = []
    flags: list = []
    ev_ix: dict = {}
    kind_ix: dict = {}
    flag_ix: dict = {}
    by_fam: dict = {}
    for r in rs:
        by_fam.setdefault(r["family"], []).append(r)
    order = [f for f in FAMILY_ORDER if f in by_fam] + sorted(f for f in by_fam if f not in FAMILY_ORDER)
    families: dict = {}
    for fam in order:
        frs = by_fam[fam]
        pres: dict = {}
        for r in frs:
            for k in r:
                if k == "family" or k in DERIVED:
                    continue
                pres[k] = pres.get(k, 0) + 1
        rest = [k for k in pres if k not in _STATE_KEYS]
        rest.sort(key=lambda k: (-pres[k], _KEY_ORDER.index(k) if k in _KEY_ORDER else len(_KEY_ORDER), k))
        keys = [k for k in _STATE_KEYS if k in pres] + rest
        arr = []
        for r in frs:
            g = int(r["game_pk"])
            games.setdefault(str(g), [r.get("date"), r.get("opp"), 1 if r.get("home") else 0])
            for ik, nk in NAME_OF.items():
                if r.get(ik) is not None and r.get(nk) is not None:
                    names[str(r[ik])] = r[nk]
            row = []
            for k in keys:
                v = r.get(k)
                if v is None:
                    row.append(None)
                    continue
                if k == "half":
                    v = HALF.index(v)
                elif k == "kind":
                    v = _code(kinds, kind_ix, v)
                elif k == "flags":
                    v = [_code(flags, flag_ix, f) for f in v]
                elif k == "window":
                    v = _code_window(v, int(r["ab"]), events, ev_ix)
                row.append(v)
            while row and row[-1] is None:
                row.pop()
            arr.append(row)
        families[fam] = {"keys": keys, "rows": arr}
    return {"season": int(season), "club": club, "n": len(rs),
            "generated_at": stamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "produced_by": "mgmt_shards.py", "schema_version": SCHEMA_VERSION,
            "schema_note": SCHEMA_NOTE, "legend": LEGEND,
            "games": games, "names": names, "events": events, "kinds": kinds, "flags": flags,
            "families": families}


def expand(payload: dict) -> list:
    """The schema-1 rows of a schema-2 shard, in the shard's row order (date, game_pk, ab,
    idx; ties in family order). This is the Python twin of expandShard in
    assets/management.js, for the tests."""
    games = payload.get("games") or {}
    names = payload.get("names") or {}
    events = payload.get("events") or []
    kinds = payload.get("kinds") or []
    flags = payload.get("flags") or []
    half = tuple((payload.get("legend") or {}).get("half") or HALF)
    rows = []
    for fam, blk in (payload.get("families") or {}).items():
        keys = blk.get("keys") or []
        for arr in blk.get("rows") or []:
            cells = {k: (arr[i] if i < len(arr) else None) for i, k in enumerate(keys)}
            g = games.get(str(cells.get("game_pk"))) or [None, None, 0]
            r: dict = {}
            if g[0] is not None:
                r["date"] = g[0]
            r["game_pk"] = cells.get("game_pk")
            r["ab"] = cells.get("ab")
            r["idx"] = cells.get("idx")
            if g[1] is not None:
                r["opp"] = g[1]
            r["home"] = bool(g[2])
            for k in keys:
                v = cells.get(k)
                if v is None or k in ("game_pk", "ab", "idx"):
                    continue
                if k == "half":
                    r[k] = half[v]
                elif k == "kind":
                    r[k] = kinds[v]
                elif k == "flags":
                    r[k] = [flags[i] for i in v]
                elif k == "window":
                    r[k] = _decode_window(v, int(r["ab"]), events)
                else:
                    r[k] = v
                if k in NAME_OF and str(v) in names:
                    r[NAME_OF[k]] = names[str(v)]
            r["family"] = fam
            r["win_len"] = len(r["window"]) if r.get("window") else 0
            rows.append(r)
    rows.sort(key=_sort_key)
    return rows


def _on_disk(p: Path):
    """The shard already at `p`, parsed, or None."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_season(rows: list, out_dir: Path | None = None, season=None, *,
                 frozen: bool = False) -> list:
    """Write one shard per club found in `rows` (one season). Returns the index rows
    [{season, club, n, bytes}]. Rows are copied and compacted; the caller's rows are
    left whole.

    A shard whose content equals the file on disk (every key but generated_at) is
    NOT rewritten, so a rebuild on an unchanged corpus leaves every byte alone and
    generated_at keeps the date the content last changed. Before 2026-10-02 every
    run restamped all 240 files with nothing else moving. With `frozen` (a completed
    season, owner answer 2026-09-25) a shard already on disk is never rewritten even
    when its content would move: the bunt family prices its cells on the pooled
    corpus, so a growing open season moves dv_cell on earlier seasons' bunt rows in
    the fourth or fifth decimal, and a completed season stays as it was last built.
    A frozen shard missing from disk is still written."""
    out_dir = Path(out_dir or SHARD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_club: dict = {}
    for r in rows:
        by_club.setdefault(r["club"], []).append(r)
    index = []
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for club in sorted(by_club):
        s = int(season if season is not None else by_club[club][0]["season"])
        p = out_dir / shard_name(s, club)
        old = _on_disk(p)
        if frozen and old is not None and old.get("schema_version") == SCHEMA_VERSION:
            index.append({"season": s, "club": club, "n": old.get("n"),
                          "bytes": p.stat().st_size})
            continue
        payload = compact_season(by_club[club], s, club, stamp)
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if old is not None and {k: v for k, v in old.items() if k != "generated_at"} == {
                k: v for k, v in json.loads(text).items() if k != "generated_at"}:
            index.append({"season": s, "club": club, "n": payload["n"],
                          "bytes": p.stat().st_size})
            continue
        p.write_text(text, encoding="utf-8")
        index.append({"season": s, "club": club, "n": payload["n"], "bytes": p.stat().st_size})
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
