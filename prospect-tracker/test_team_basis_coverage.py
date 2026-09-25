# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One convention, four boards, and it must be disclosed on all of them.

`team` points at the club MLB's transaction feed says employs the player TODAY,
on closed seasons as well as the current one. That is a locked owner decision
with a recorded dissent and it is NOT what this file is about. This file is about
whether the reader is told.

MEASURED 2026-09-06, before the repair:
  * teamBasisNote() was mounted at ONE render site, the bullpen view, which is the
    board where the convention moves the FEWEST rows (39 of 790).
  * The starter (2 sites), hitter (2) and Leverage (2) renders called bannerHTML()
    without it.
  * Four served payloads carried no team_basis block to render at all:
    leverage_leaderboards.json, bullpen_history.json, starter_history.json and
    hitter_history.json.
  * The history boards are where it bites hardest: the same rule points a 2021
    season at a 2026 club, and 2,088 of 6,885 served history rows (30.3%) carry a
    club the player did not play for that year.

test_mlbstats_smoke.py already pins that the note EXISTS and is mounted once. This
pins that it reaches every board, and that every board has something to say.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
JS = ROOT / "assets" / "mlbstats.js"

# Every payload the /mlbstats/ page renders a team column from. The eWAR
# board joined them in wave 5: it carries a team column on its player list
# AND a club rollup on two named bases, so it has MORE to disclose than the
# others, not less.
BOARDS = ("bullpen_leaderboards.json", "starter_leaderboards.json",
          "hitter_leaderboards.json", "leverage_leaderboards.json",
          "defense_leaderboards.json", "war_leaderboards.json",
          "bullpen_history.json", "starter_history.json", "hitter_history.json",
          "defense_history.json")


def _js():
    return JS.read_text(encoding="utf-8")


def test_every_render_site_that_shows_a_team_mounts_the_note():
    """bannerHTML is the banner every board draws. The note rides with it."""
    js = _js()
    banners = [m.start() for m in re.finditer(r"bannerHTML\(", js)]
    # Two occurrences are not mounts: the definition (`function bannerHTML(`) and
    # the one-line `banner()` wrapper, whose caller adds the note itself. The
    # definition check reads the nine characters immediately before the match, so
    # it cannot be defeated by the window boundary the way an `in` check on a
    # 40-char slice was.
    mounts = [i for i in banners
              if js[max(0, i - 9):i] != "function "
              and "function banner() { return bannerHTML(DATA" not in js[max(0, i - 30):i + 30]]
    assert len(mounts) >= 4, (
        f"only {len(mounts)} banner mount(s) found; the detector has stopped "
        f"seeing the render sites it is supposed to police")
    missing = []
    for i in mounts:
        window = js[i:i + 260]
        if "teamBasisNote" not in window:
            missing.append(js[max(0, i - 120):i + 90].strip().splitlines()[-2:])
    assert not missing, (
        f"{len(missing)} render site(s) draw the board banner without the team-basis "
        f"note, so those boards apply the convention silently: {missing}"
    )


def test_the_note_is_mounted_with_each_board_own_payload():
    """A shared payload would misreport three boards: the counts differ.

    Every board mounts the note through sectionBasis(sec, live, history)
    (e654c440 folded the Defense board's defenseBasis() into it), which hands
    the note the history file's own block on a past-season pill (the
    CLOSED-season sentence) and the live board's otherwise."""
    js = _js()
    for sec, payload, hist in (("bullpen", "DATA", "HISTORY"),
                               ("starters", "starterData", "STARTER_HISTORY"),
                               ("hitters", "hitterData", "HITTER_HISTORY"),
                               ("leverage", "leverageData", "leverageHistory"),
                               ("defense", "defenseData", "DEFENSE_HISTORY")):
        assert f'teamBasisNote(sectionBasis("{sec}", {payload}, {hist}))' in js, (
            f"the note is not mounted with {payload}, so that board either shows "
            f"nothing or shows another board's row counts"
        )
    body = js.split("function sectionBasis(sec, live, hist)")[1].split("\n  }")[0]
    assert "return live" in body and "hist" in body, (
        "sectionBasis() no longer chooses between the live and the history payload")


def test_every_served_board_carries_the_block():
    missing = []
    for name in BOARDS:
        p = ROOT / "data" / name
        if not p.exists():
            continue
        tb = json.loads(p.read_text(encoding="utf-8")).get("team_basis")
        if not tb or not tb.get("note"):
            missing.append(name)
    if not any((ROOT / "data" / n).exists() for n in BOARDS):
        pytest.skip("no /mlbstats/ boards built on this machine")
    assert not missing, (
        f"{len(missing)} served board(s) publish a team column with no team_basis "
        f"block, so the page has nothing to disclose for them: {missing}"
    )


def test_a_history_board_says_the_history_thing():
    """The current-season sentence understates the closed-season case.

    On the live board the strongest case is an August acquisition credited to his
    new club. On a closed season the same rule points a 2021 line at a 2026 club.
    A reader given the August sentence on a history board has been told the mild
    half of the convention.
    """
    checked = 0
    for name in ("bullpen_history.json", "starter_history.json", "hitter_history.json",
                 "defense_history.json"):
        p = ROOT / "data" / name
        if not p.exists():
            continue
        tb = json.loads(p.read_text(encoding="utf-8")).get("team_basis") or {}
        if tb.get("basis") != "current_roster":
            continue
        checked += 1
        assert tb.get("scope") == "history", f"{name} is not stamped as a history scope"
        assert "CLOSED seasons" in (tb.get("note") or ""), (
            f"{name} carries the current-season sentence, which describes an August "
            f"acquisition rather than a 2021 line shown under a 2026 club"
        )
    if not checked:
        pytest.skip("no history boards built on this machine")


def test_the_disclosure_counts_what_the_reader_sees():
    """n_rows must be the served board, not the season pool behind it."""
    for name, key in (("bullpen_history.json", "relievers"),
                      ("starter_history.json", "starters"),
                      ("hitter_history.json", "hitters"),
                      ("defense_history.json", "fielders")):
        p = ROOT / "data" / name
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        tb = d.get("team_basis") or {}
        served = sum(len(v.get(key) or []) for v in (d.get("history") or {}).values())
        assert tb.get("n_rows") == served, (
            f"{name} discloses {tb.get('n_rows')} rows but serves {served}; the "
            f"disclosure is counting the season pool rather than the board"
        )
