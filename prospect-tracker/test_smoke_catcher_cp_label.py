# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke audit 2026-10-01, finding SHO01.

Baseball America's 2023 org boards print "CP" as the position line of every
catcher, and the 16 debuted catchers whose last board was BA 2023 carry it in
debuts.json. The homepage This Day rail and /history/ printed "Bo Naylor
debuted · CP" and "Francisco Alvarez debuted · CP" for two catchers, where
every other reader of a position string takes CP for a closer. build_site now
prints CP as C. The position field itself is a model input (fantasy_rank,
storage, consensus read it) and stays as it is, so this test asserts on what
the pages print, not on debuts.json.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import build_site as B

ROOT = Path(__file__).parent

_FALLBACK_ROWS = [
    {"player_key": "bo_naylor", "player_name": "Bo Naylor", "position": "CP",
     "org": "CLE", "debut_date": "2022-10-01"},
    {"player_key": "francisco_alvarez", "player_name": "Francisco Alvarez",
     "position": "CP", "org": "NYM", "debut_date": "2022-09-30"},
]


def _cp_rows() -> list[dict]:
    p = ROOT / "data" / "debuts.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _FALLBACK_ROWS
    rows = d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])
    cp = [r for r in rows
          if "CP" in [t.strip().upper() for t in str(r.get("position") or "").split("/")]]
    return cp or _FALLBACK_ROWS


def test_catcher_cp_prints_as_c():
    problems: list[str] = []
    # The built pages print no CP position.
    for rel in ("index.html", "history/index.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "debuted · CP" in text or " · CP" in text:
            problems.append(f"{rel} still prints a CP position")
    # Every CP row in debuts.json renders as a catcher on a This Day debut row.
    for r in _cp_rows():
        row = B._otd_debut_row(r, date(2022, 10, 1))
        # HOME_2: the verb is the row's value, in its family colour (.wire-val)
        if "debuted</span> · C<" not in row or "· CP" in row:
            problems.append(f"{r.get('player_key')} renders {row!r}")
    # Every other label keeps its own spelling.
    for pos in ("C", "RHP", "SIRP", "SS/2B", "OF / C", "CL", ""):
        if B._pos_label(pos) != pos:
            problems.append(f"_pos_label({pos!r}) = {B._pos_label(pos)!r}")
    if B._pos_label(None) != "":
        problems.append("_pos_label(None) is not empty")
    assert not problems, problems
