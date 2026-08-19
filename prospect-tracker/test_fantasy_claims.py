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
   history, may never appear in assets/fantasy.js.
2. REQUIRED DISCLOSURES: the honesty sentences the 2026-08-19 audit left
   in place (screen posture, role-order posture, display-ranking posture)
   are load-bearing; deleting one silently would re-open the claim it
   closes, so their presence is pinned.

SCOPE: assets/fantasy.js only. The redraft.js / fantasy-card.js ports carry
sibling copies of the buy/sell and closer notes; they were out of scope for
the 2026-08-19 lane and adding them to FANTASY_SURFACES before their copy
is repaired would turn this ratchet red on day one. Add each port here in
the same change that fixes its copy.

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
