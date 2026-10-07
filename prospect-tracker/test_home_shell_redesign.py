# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The four shell pages of REDESIGN_home_shell (site pass, 2026-10-07).

Pins: no shell page serves a 'coming soon' placeholder; a Masthead member with
nothing for a card back gets a one-sided card (no back face, no turn control)
while a member with back content keeps the turn; /report/ is a plain page with
the address and what to include, no form shell; /forums/ shows one
'unmeasured' state card while the account layer is unconfigured, with the list
mount kept hidden behind it; /sources/ leads with a table carrying one row per
source note, every row with what we take, a cadence and a terms cell, and the
notes folded under it. Each check runs on the builder and on the served file."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent

PAGES = {
    "team/index.html": B.build_team,
    "report/index.html": B.build_bug_report,
    "forums/index.html": B.build_forums_index,
    "sources/index.html": B.build_sources,
}


def _served(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _main(page: str) -> str:
    m = re.search(r"<main\b.*?</main>", page, re.S)
    assert m, "no <main> on the page"
    return m.group(0)


@pytest.mark.parametrize("rel", sorted(PAGES))
def test_no_coming_soon_on_a_shell_page(rel):
    for text in (PAGES[rel](), _served(rel)):
        assert not re.search(r"coming soon", text, re.I), rel


# ------------------------------------------------------------------ /team/

def _one_sided_member() -> dict:
    return {"key": "test-member", "name": "Test Member", "group": "developers",
            "order": 99, "role": "Tester"}


def test_a_member_without_back_content_gets_a_one_sided_card():
    team = B._load_team()
    group = next(g for g in team["groups"] if g["key"] == "developers")
    card = B._team_card(_one_sided_member(), group, team)
    assert "tc-back" not in card
    assert "data-flip" not in card
    assert 'class="tc-card no-back"' in card


def test_members_with_back_content_keep_the_turn():
    team = B._load_team()
    groups = {g["key"]: g for g in team["groups"]}
    for m in team["members"]:
        card = B._team_card(m, groups[m["group"]], team)
        assert 'class="tc-face tc-back"' in card, m["key"]
        assert 'data-flip="back"' in card and 'data-flip="front"' in card, m["key"]
        assert "no-back" not in card, m["key"]


def test_team_js_never_turns_a_one_sided_card():
    js = (ROOT / "assets" / "team.js").read_text(encoding="utf-8")
    assert '.tc-card:not(.is-unnamed):not(.no-back)' in js
    assert 'classList.contains("no-back")' in js


# ------------------------------------------------------------------ /report/

@pytest.mark.parametrize("text", [B.build_bug_report(), _served("report/index.html")],
                         ids=["built", "served"])
def test_report_is_a_plain_page(text):
    main = _main(text)
    assert "<form" not in main and "<iframe" not in main
    assert "not configured" not in main
    assert 'href="mailto:arkndjl@gmail.com' in main
    for what in ("The page", "The steps", "Your browser"):
        assert f"<strong>{what}</strong>" in main, what


def test_the_unused_form_constant_is_gone():
    assert not hasattr(B, "BUG_FORM_URL")


# ------------------------------------------------------------------ /forums/

@pytest.mark.parametrize("text", [B.build_forums_index(), _served("forums/index.html")],
                         ids=["built", "served"])
def test_forums_shows_one_unmeasured_state_until_accounts_are_live(text):
    main = _main(text)
    assert main.count('class="px-state ') == 1
    assert 'class="px-state is-unmeasured' in main
    # the list mount stays, hidden, for the moment the account layer is configured
    assert '<div id="eph-forums-live" hidden><div id="eph-forums-index"></div></div>' in main
    assert "window.EEPHUS_SUPABASE" in main


# ------------------------------------------------------------------ /sources/

@pytest.mark.parametrize("text", [B.build_sources(), _served("sources/index.html")],
                         ids=["built", "served"])
def test_sources_leads_with_one_table_row_per_source(text):
    main = _main(text)
    table = re.search(r'<table class="src-table">.*?</table>', main, re.S)
    assert table, "no source table"
    rows = re.findall(r"<tr><th scope=\"row\">", table.group(0))
    notes = re.findall(r'<div class="card source-card" id="src-[a-z0-9-]+"><h3>', main)
    assert len(rows) == len(notes) == len(B.SOURCE_ROWS) > 0
    # the table comes before the lede and before every source note
    assert main.index('class="src-table"') < main.index('class="gl-intro"')
    assert main.index('class="src-table"') < main.index('class="card source-card"')
    # the notes are folded under the table
    fold = re.search(r'<details class="src-fold" id="src-notes">.*?</details>', main, re.S)
    assert fold and len(re.findall(r'class="card source-card" id="src-', fold.group(0))) == len(notes)
    head = re.findall(r'<th scope="col">([^<]+)</th>', table.group(0))
    assert head == ["Source", "What we take", "Cadence", "Terms"]


def test_every_source_row_carries_the_table_fields():
    names = set()
    for s in B.SOURCE_ROWS:
        assert s["name"] not in names, s["name"]
        names.add(s["name"])
        for k in ("url", "take", "cadence", "use"):
            assert isinstance(s.get(k), str) and s[k].strip(), (s["name"], k)
        assert s["url"].startswith("https://"), s["name"]
        t = s.get("terms")
        assert t is None or re.match(r"https?://", t), s["name"]
        assert (t is None) == (s.get("terms_label") is None), s["name"]
