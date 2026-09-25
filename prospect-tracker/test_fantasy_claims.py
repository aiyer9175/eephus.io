# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fantasy-surface claims ratchet (2026-08-19).

The glossary freshness net (test_claims_freshness.py) deliberately does not
reach /fantasy/: the page IS the documentation there, so its copy strings
carry the claims discipline themselves. This file extends the phrase
ratchet to that surface, in two layers:

1. PHRASE RATCHET: the shared BANNED_CLAIM_FRAGMENTS from
   test_claims_freshness (contradicted eFV/consensus claims) plus the
   fantasy-specific fragments removed on 2026-08-19, each with its own
   history, may never appear on a fantasy surface (FANTASY_SURFACES).
2. REQUIRED DISCLOSURES: the honesty sentences the 2026-08-19 audit left
   in place (screen posture, role-order posture, display-ranking posture)
   are load-bearing; deleting one silently would re-open the claim it
   closes, so their presence is pinned.

SCOPE: assets/fantasy.js since 2026-08-19; the SERVED ports joined on
2026-09-11 in the change that repaired their copy. assets/redraft.js was
still printing "is due to improve", "Buy-Low (unlucky)" and "the likely
closer" on the live /fantasy/ page, and assets/fantasy-card.js called the
top bullpen arm a "likely closer" and the positive gap "the buy case", all
while the frozen fantasy.js (loaded by no page) carried the repaired copy.
assets/dynasty.js joined for its blend disclosure.

Import-safe and deterministic: no network, no rebuilds, every file read
happens inside a test function.
"""

from __future__ import annotations

from pathlib import Path

from test_claims_freshness import BANNED_CLAIM_FRAGMENTS

ROOT = Path(__file__).parent

# Fantasy copy surfaces the ratchet scans (see SCOPE note above before
# adding the ports).
FANTASY_SURFACES = (
    "assets/fantasy.js",
    "assets/redraft.js",
    "assets/fantasy-card.js",
    "assets/dynasty.js",
)

# ---------------------------------------------------------------------------
# Fantasy-specific ratchet. Every fragment below was LIVE hand-written copy
# in assets/fantasy.js on 2026-08-19 and was removed that day because it
# claimed accuracy no artifact backs. Matching is case-insensitive substring.
FANTASY_BANNED_FRAGMENTS = (
    # Buy/Sell note claimed a positive luck gap FORECASTS improvement. The
    # fantasy_buy_sell registry row (2026-08-16) states the opposite posture:
    # "no committed measurement exists that a large luck gap regresses toward
    # the x-stat rather than persisting". The surface is a SCREEN; it states
    # the gap direction and stops.
    "is due to improve",
    # Buy/Sell column headers asserted luck causality on the same unmeasured
    # gap. Removed with the note; headers now name the gap direction
    # ("behind x-stats" / "ahead of x-stats"), not a luck verdict.
    "buy-low (unlucky)",
    "sell-high (overperforming)",
    # Closer Grid note called the top arm "the likely closer". The
    # fantasy_closer_depth row is a role-ORDER display, not a saves
    # projection, and the save-share model LOST to the pace rule (closer
    # gate RED, 2026-08-16, docs/fantasy-closer-gate-2026-08-16.md). Copy
    # may describe the ordering rule (gmLI, saves/REM+ tiebreaks); it may
    # not attach a likelihood to who gets saves.
    "the likely closer",
    # The card's role chip carried the same claim without the article
    # ("likely closer"), and its skill note called a positive gap "the buy
    # case". Both removed 2026-09-11 with the ports' copy repair.
    "likely closer",
    "the buy case",
)

# ---------------------------------------------------------------------------
# Honesty sentences the 2026-08-19 audit verified or installed. Each closes
# a specific claim; each must stay in the copy verbatim (case-insensitive).
#   (surface, fragment, what it protects)
FANTASY_REQUIRED_DISCLOSURES = (
    ("assets/fantasy.js", "whether a gap closes or persists is unmeasured",
     "buy/sell screen posture (fantasy_buy_sell: baseline none run)"),
    ("assets/fantasy.js", "not a saves projection",
     "closer grid role-order posture (fantasy_closer_depth; gate RED 2026-08-16)"),
    ("assets/fantasy.js", "display ranking over served efv numbers, not a separate model",
     "dynasty blend is a stated convention over gated upstream legs, never a fit"),
    # The served ports (2026-09-11). Same three postures, on the pages a
    # reader actually loads.
    ("assets/redraft.js", "whether a gap closes or persists is unmeasured",
     "buy/sell screen posture on the served Redraft board"),
    ("assets/redraft.js", "not a saves projection",
     "closer grid role-order posture on the served Redraft board"),
    ("assets/fantasy-card.js", "whether a gap closes or persists is unmeasured",
     "player card skill note: the gap is a screen, not a forecast"),
    ("assets/fantasy-card.js", "not a saves projection",
     "player card bullpen role: an order, not a saves projection"),
    ("assets/fantasy-card.js", "not a separate model",
     "player card dynasty block: the rank is a display blend"),
    ("assets/dynasty.js", "display ranking over served efv numbers, not a separate model",
     "dynasty board blend disclosure on the served Dynasty board"),
    # M11-06 (2026-09-25): the keeper verdict compares a PROSPECT rank with a
    # pick, so it is a prospects-only draft verdict and must say so.
    ("assets/dynasty.js", "pick spent against board rank in a prospects-only draft",
     "keeper calculator basis: the board ranks prospects only"),
    ("assets/fantasy-card.js", "keep by (farm draft)",
     "player card keeper chip names the draft its round is for"),
)


def _read_text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_fantasy_surfaces_exist():
    """A ratchet over a missing file is a silent no-op; refuse that."""
    for rel in FANTASY_SURFACES:
        assert (ROOT / rel).is_file(), f"fantasy ratchet surface missing: {rel}"


def test_fantasy_banned_fragments_absent():
    """Neither the shared contradicted-claim fragments nor the fantasy
    fragments removed on 2026-08-19 may appear on a fantasy surface."""
    fragments = tuple(BANNED_CLAIM_FRAGMENTS) + FANTASY_BANNED_FRAGMENTS
    violations = []
    for rel in FANTASY_SURFACES:
        text = _read_text(rel).lower()
        for frag in fragments:
            if frag.lower() in text:
                violations.append(f"{rel}: {frag!r}")
    assert not violations, (
        "banned claim fragment(s) on a fantasy surface (each was a live "
        "unbacked claim; the page is the documentation, so its copy states "
        "the served number or the stated convention and stops): "
        + "; ".join(violations)
    )


def test_fantasy_required_disclosures_present():
    """The honesty sentences are load-bearing: each one closes a claim the
    ratchet above bans. Deleting one re-opens the claim, so the copy must
    keep it (reword only together with this table)."""
    problems = []
    for rel, frag, why in FANTASY_REQUIRED_DISCLOSURES:
        if frag.lower() not in _read_text(rel).lower():
            problems.append(f"{rel}: missing {frag!r} ({why})")
    assert not problems, (
        "required fantasy disclosure(s) gone: " + "; ".join(problems)
    )


def test_dynasty_masthead_claims_only_what_ships():
    """The Dynasty masthead said prospects and MLB players "share one ranking"
    (0 of 300 board rows are MLB players) and that the keeper calculator
    "prices years of control" (the window input never reaches the verdict)."""
    for rel in ("build_site.py", "fantasy/index.html"):
        text = _read_text(rel).lower()
        for frag in ("share one ranking", "prices years of control"):
            assert frag not in text, f"{rel}: {frag!r}"
