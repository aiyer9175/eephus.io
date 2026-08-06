# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Signing in must not hide the bets you logged signed out.

THE BUG THIS PINS (plan item G5, fixed 2026-08-06). Two modules kept the bet log
under two different localStorage keys:

    assets/betting.js         "eephus_bets_v1"    underscores
    assets/eephus-account.js  "eephus.bets.v1"    dots

`mergeOnSignIn` read betting.js's store and passed the rows to
`Account.mergeLocalBets(rows)`. That function IGNORED its argument and read its
own store instead, found it empty, reported {merged: 0} and inserted nothing.
`loadBets()` then switched the view to the account source. The rows were still on
disk under the other key and nothing read them again.

Sign in, and your bets disappear. Nothing was deleted and nothing raised, which
is why it survived a 55-finding QA pass: the only symptom is on an account
go-live day nobody has had yet.

Fixed by making the merge take the caller's rows, which is the right contract
regardless of the key names, rather than by renaming a key. A rename would
strand whatever is already sitting in real browsers under the old name.

These are source-level assertions on purpose. The behaviour lives in two browser
modules with a Supabase client between them, and the property worth protecting
is the CONTRACT: the merge consumes what it is handed, and neither side clears
storage the other owns.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ASSETS = Path(__file__).parent / "assets"
ACCOUNT = ASSETS / "eephus-account.js"
BETTING = ASSETS / "betting.js"

pytestmark = pytest.mark.skipif(
    not (ACCOUNT.exists() and BETTING.exists()), reason="assets absent")


def _src(p):
    return p.read_text(encoding="utf-8")


def test_the_two_modules_really_do_use_different_keys():
    """The premise. If these ever converge the fix is still correct, but this
    test should be re-read rather than silently passing for a new reason."""
    acct = re.search(r'_betsKey:\s*"([^"]+)"', _src(ACCOUNT))
    bet = re.search(r'LS_KEY\s*=\s*"([^"]+)"', _src(BETTING))
    assert acct and bet, "could not find both storage keys"
    assert acct.group(1) != bet.group(1), (
        "the keys now match; re-read this test, the orphaning path may be gone")


def test_the_merge_accepts_the_callers_rows():
    """THE REGRESSION. An argument-less merge reads the wrong store."""
    src = _src(ACCOUNT)
    m = re.search(r"mergeLocalBets:\s*function\s*\(([^)]*)\)", src)
    assert m, "mergeLocalBets not found"
    assert m.group(1).strip(), (
        "mergeLocalBets must take the caller's rows; taking none is what made "
        "it read a different storage key and merge nothing")


def test_the_merge_prefers_the_passed_rows_over_its_own_store():
    src = _src(ACCOUNT)
    body = src[src.index("mergeLocalBets:"):]
    body = body[:body.index("\n    },")]
    assert "Array.isArray(rows)" in body, (
        "the passed rows must be used when present")
    assert body.index("Array.isArray(rows)") < body.index("Account._localBets()"), (
        "the caller's rows must be preferred, with its own store as fallback")


def test_the_merge_does_not_clear_storage_it_does_not_own():
    """When the caller supplies rows, the caller owns that storage. Clearing the
    account key there would wipe a store the rows never came from."""
    src = _src(ACCOUNT)
    body = src[src.index("mergeLocalBets:"):]
    body = body[:body.index("\n    },")]
    assert "!passed" in body, (
        "the device-copy clear must be conditional on having used our own store")


def test_the_caller_clears_its_own_store_only_after_the_server_took_the_rows():
    """A merge that clears local storage before the insert lands is a data-loss
    bug, which is the opposite failure and just as bad."""
    src = _src(BETTING)
    i = src.index("a.mergeLocalBets(")
    body = src[i:i + 900]
    assert "res.merged" in body and "res.error" in body, (
        "the caller must check that the server accepted the rows")
    assert re.search(r"if\s*\(res\s*&&\s*res\.merged\s*&&\s*!res\.error\)\s*saveLocal\(\[\]\)", body), (
        "clear the local store only on a confirmed, error-free merge")


def test_a_failed_merge_leaves_the_rows_alone():
    src = _src(BETTING)
    i = src.index("a.mergeLocalBets(")
    body = src[i:i + 900]
    assert ".catch(" in body, "a failed merge must be caught"
    tail = body[body.index(".catch("):]
    assert "saveLocal" not in tail, (
        "the catch path must not touch local storage; staying local is the "
        "correct outcome of a failed merge")
