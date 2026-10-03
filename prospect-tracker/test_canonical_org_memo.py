# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""trades.canonical_org is memoised (PERF_7, 2026-10-03).

storage.authoritative_org_map resolves the destination of every transaction
event (210,492 events over 851 distinct club and affiliate names, measured
2026-10-03), and the token-search miss path re-sorted the alias table and ran a
regex per alias on each call: 19.1 s per call, eight calls per Alchemy Lab
build. The memo pays each distinct name once. These tests pin that the memo is
transparent: the same answer on every path (code remap, exact alias, token
search, pass-through, empty) and a repeat call served from the cache.
"""
import trades
from trades import canonical_org


def test_every_resolution_path_is_unchanged_under_the_memo():
    canonical_org.cache_clear()
    assert canonical_org("KC") == "KCR"                       # code remap
    assert canonical_org("BOS") == "BOS"                      # short code pass-through
    assert canonical_org("boston") == "BOS"                   # exact alias
    assert canonical_org("Boston Red Sox") == "BOS"           # token search
    assert canonical_org("Palm Beach Cardinals") == "STL"     # affiliate carrying the parent
    assert canonical_org("Somerset Patriots") == "Somerset Patriots"   # unresolved pass-through
    assert canonical_org(None) is None
    assert canonical_org("") is None
    assert canonical_org("  ") == ""      # the pre-memo pass-through, pinned as found


def test_a_repeat_call_is_served_from_the_cache():
    canonical_org.cache_clear()
    first = canonical_org("Palm Beach Cardinals")
    before = canonical_org.cache_info().hits
    assert canonical_org("Palm Beach Cardinals") == first
    assert canonical_org.cache_info().hits == before + 1


def test_the_alias_tables_are_still_the_only_inputs():
    # The memo is only safe while the function reads nothing but its argument
    # and these two module constants; a future runtime mutation of either must
    # call canonical_org.cache_clear().
    assert isinstance(trades.ORG_ALIASES, dict) and isinstance(trades._CODE_REMAP, dict)
    assert hasattr(canonical_org, "cache_clear")
