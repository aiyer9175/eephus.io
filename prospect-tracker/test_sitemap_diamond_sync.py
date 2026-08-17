# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SITE_MAP.md's Diamond payload rows track what the clients actually fetch.

SITE_MAP.md is the route inventory other work trusts (the 2026-07-14 deploy
defect happened because two lists drifted from the truth). Its payload
column states what each surface's client app fetches, so the /diamond/,
/cards/ and /betting/ rows are pinned here against the fetch literals in
the client sources themselves.

Comparison rules:
  * glossary.json and player_links.json are excluded on BOTH sides: the
    shared runtime (assets/eephus-gl.js, assets/eephus-hub.js) fetches them
    on every page, and SITE_MAP's own header carries that note, so rows
    list them inconsistently and honestly may.
  * /diamond/ and /cards/ are exact-match modulo the KNOWN_DESYNC ledger
    below. /betting/ is a SUPERSET assertion (the row may list more than
    the static literals, never less): betting.js carries many fetch sites
    and is under active edit, so the robust direction is "nothing fetched
    is undocumented".

KNOWN_DESYNC is the debt ledger for drift found on 2026-08-16, with both
directions asserted: drift not on the ledger fails, and a healed row must
leave the ledger in the change that heals it.

This file also carries the scoreboard freshness guard (see the last test's
docstring for why it lives here and not in the registry tests).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SITE_MAP = ROOT / "SITE_MAP.md"
ASSETS = ROOT / "assets"
DATA = ROOT / "data"

# Fetched on every page by the shared runtime; excluded from both sides.
RUNTIME_PAYLOADS = {"glossary.json", "player_links.json"}

# route -> the client scripts whose static /data/ literals define the truth.
ROUTE_CLIENTS = {
    "/diamond/": ["diamond.js", "diamond-config.js"],
    "/cards/": ["cards.js"],
    "/betting/": ["betting.js"],
}

FETCH_LITERAL = re.compile(r"/data/([A-Za-z0-9_.-]+\.json)")
ROW_PAYLOAD = re.compile(r"`([A-Za-z0-9_.-]+\.json)`")

# ---------------------------------------------------------------------------
# The drift ledger, found 2026-08-16. map_only = payloads the SITE_MAP row
# lists that no client on the page fetches. Healing a row means deleting its
# entry here in the same change.
# ---------------------------------------------------------------------------

KNOWN_DESYNC = {
    "/diamond/": {
        "map_only": {"xfv_power_eval.json"},
        "reason": (
            "2026-08-16: listed since 2026-08-10 (2d13e3b1) but no script on "
            "the page fetches it. diamond.js cites data/xfv_power_eval.json in "
            "COMMENTS only (the partb_floors provenance notes), and the "
            "registry row for it says 'model-dev artifact (rendered nowhere)'. "
            "Either the row loses the payload or the page starts reading it."
        ),
    },
    "/cards/": {
        "map_only": {"card_watchlist.json"},
        "reason": (
            "2026-08-16: listed since 2026-08-05 (4550a317) but cards.js never "
            "fetches it. card_watchlist.json is the bake-time input to "
            "card_market_export.py; cards.js mentions it in a comment and in "
            "methodology copy, not in a fetch. Either the row loses the "
            "payload or the page starts reading it."
        ),
    },
}


def sitemap_row_payloads(sitemap_text: str, route: str) -> set[str]:
    for line in sitemap_text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 5 and cells[1] == f"`{route}`":
            return set(ROW_PAYLOAD.findall(cells[4]))
    raise AssertionError(f"SITE_MAP.md has no surface-inventory row for {route}")


def client_payloads(route: str) -> set[str]:
    found = set()
    for name in ROUTE_CLIENTS[route]:
        src = (ASSETS / name).read_text(encoding="utf-8")
        found.update(FETCH_LITERAL.findall(src))
    return found


def drift(sitemap_text: str, route: str) -> tuple[set[str], set[str]]:
    """(map_only, client_only), both modulo the shared-runtime payloads."""
    mapped = sitemap_row_payloads(sitemap_text, route) - RUNTIME_PAYLOADS
    fetched = client_payloads(route) - RUNTIME_PAYLOADS
    return mapped - fetched, fetched - mapped


@pytest.fixture(scope="module")
def sitemap_text() -> str:
    return SITE_MAP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Derivation sanity before any comparison is trusted.
# ---------------------------------------------------------------------------

def test_client_literal_extraction_is_sane():
    assert "xfv_scoreboard_eval.json" in client_payloads("/diamond/")
    assert "card_market.json" in client_payloads("/cards/")
    assert len(client_payloads("/betting/")) >= 5, (
        "betting.js fetch literals collapsed; the extraction regex is broken")


def test_diamond_row_matches_the_client(sitemap_text):
    map_only, client_only = drift(sitemap_text, "/diamond/")
    ledger = KNOWN_DESYNC["/diamond/"]["map_only"]
    assert client_only == set(), (
        f"/diamond/ clients fetch payloads SITE_MAP.md does not list: "
        f"{sorted(client_only)}")
    assert map_only == ledger, (
        f"/diamond/ drift changed: SITE_MAP-only payloads are {sorted(map_only)} "
        f"but the KNOWN_DESYNC ledger records {sorted(ledger)}. If the row was "
        "healed, delete the ledger entry; if new drift landed, fix SITE_MAP.md")


def test_cards_row_matches_the_client(sitemap_text):
    map_only, client_only = drift(sitemap_text, "/cards/")
    ledger = KNOWN_DESYNC["/cards/"]["map_only"]
    assert client_only == set(), (
        f"/cards/ clients fetch payloads SITE_MAP.md does not list: "
        f"{sorted(client_only)}")
    assert map_only == ledger, (
        f"/cards/ drift changed: SITE_MAP-only payloads are {sorted(map_only)} "
        f"but the KNOWN_DESYNC ledger records {sorted(ledger)}. If the row was "
        "healed, delete the ledger entry; if new drift landed, fix SITE_MAP.md")


def test_betting_row_is_a_superset_of_the_client(sitemap_text):
    _, client_only = drift(sitemap_text, "/betting/")
    assert client_only == set(), (
        f"betting.js fetches payloads the SITE_MAP.md /betting/ row does not "
        f"list: {sorted(client_only)}. Add them to the row")


def test_known_desync_reasons_are_dated():
    for route, entry in KNOWN_DESYNC.items():
        assert re.search(r"20\d\d-\d\d-\d\d", entry["reason"]), (
            f"KNOWN_DESYNC[{route!r}] carries no date")
        assert entry["map_only"], (
            f"KNOWN_DESYNC[{route!r}] records no drift; delete the entry")


# ---------------------------------------------------------------------------
# Mutation proof: the comparison actually detects a payload removed from the
# SITE_MAP row (in-memory copy; the real file is never touched).
# ---------------------------------------------------------------------------

def test_mutation_removed_payload_is_detected(sitemap_text):
    tampered = sitemap_text.replace("`betting_record.json`, `glossary.json`",
                                    "`glossary.json`", 1)
    assert tampered != sitemap_text, (
        "the /diamond/ row no longer lists betting_record.json before "
        "glossary.json; update this tamper to remove a payload the row carries")
    map_only, client_only = drift(tampered, "/diamond/")
    assert "betting_record.json" in client_only, (
        "a payload removed from the SITE_MAP /diamond/ row was not detected "
        "as client-only drift")
    # And the untampered text does not report it.
    _, real_client_only = drift(sitemap_text, "/diamond/")
    assert "betting_record.json" not in real_client_only


# ---------------------------------------------------------------------------
# Scoreboard freshness. Why HERE: test_methodology_freshness.py is the
# registry-to-glossary documentation map and reads no artifact stamp at all.
# test_model_registry.py pins the freshness MACHINERY (stamps exist, mtime
# ages are never evidence, STALE_DAYS stays reachable) but no test fails
# when data/xfv_scoreboard_eval.json itself goes stale, and nothing anywhere
# ties its stamp to data/source_backtest.json, the backtest it is a view of.
# The /diamond/ receipts card prints its own stale note at 21 days
# (assets/diamond.js, "more than three weeks old"), so the pinned bound
# matches the threshold the page already shows readers.
# ---------------------------------------------------------------------------

def _stamp_date(path: Path) -> dt.date | None:
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    raw = doc.get("generated_at") or doc.get("as_of") or ""
    try:
        return dt.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def test_scoreboard_eval_is_within_21_days_of_the_backtest():
    score = _stamp_date(DATA / "xfv_scoreboard_eval.json")
    back = _stamp_date(DATA / "source_backtest.json")
    if score is None or back is None:
        pytest.skip("scoreboard eval or source backtest stamp missing; "
                    "nothing to compare")
    gap = abs((back - score).days)
    assert gap <= 21, (
        f"data/xfv_scoreboard_eval.json ({score}) is {gap} days from "
        f"data/source_backtest.json ({back}); the /diamond/ receipts card "
        "treats 21 days as a missed scoring cycle, so regenerate the "
        "scoreboard (tools/efv_scoreboard.py) with the rebuild")


def test_stamp_reader_mutation():
    # The reader returns None on a missing file and on an unstamped doc,
    # which is what routes the freshness test into skip rather than a
    # false pass on a fabricated date.
    assert _stamp_date(DATA / "no_such_artifact_xyz.json") is None
    real = _stamp_date(DATA / "xfv_scoreboard_eval.json")
    if real is not None:
        assert real.year >= 2025
