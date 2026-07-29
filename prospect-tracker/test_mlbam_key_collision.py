# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Name-slug MLBAM key-collision guard (the Jose Valdez bug).

Two different humans can normalize to the same player_key slug: the 2026
DSL Giants OF signee Jose Valdez (mlbam 838649) and the retired Tigers RHP
Jose A. Valdez both slug to "jose_a_valdez". Binding the newcomer's id to
the incumbent's key merged the two identities and made the signee fail
every active-board gate (status=debuted + "Office of the Commissioner").

These tests pin the fork logic:
  * scrapers._SPLIT_KEYS / split_key_for_mlbam — the per-(slug, mlbam)
    allowlist that routes a known newcomer to a discriminated key;
  * stats._apply_collision_guard — the generic binding-seam backstop
    (durable player_photos mapping vs freshly-resolved id);
  * mlbam_ingest._collision_safe_key — the discovery seam where a brand
    new mlbam id and a freshly-derived slug first meet;
  * stats.resolve_mlbam_id — heals a stale pre-split cache binding on the
    cache-hit path without any network access.

No network: every test injects the durable mapping / cache explicitly.
"""

from __future__ import annotations

import json

import mlbam_ingest
import stats
from scrapers import _SPLIT_KEYS, split_key_for_mlbam


# ---------------------------------------------------------------------------
# The allowlist itself
# ---------------------------------------------------------------------------

def test_split_map_contains_valdez():
    assert _SPLIT_KEYS[("jose_a_valdez", 838649)] == "jose_valdez_sfg"


def test_split_key_for_mlbam_routes_known_newcomer():
    assert split_key_for_mlbam("jose_a_valdez", 838649) == "jose_valdez_sfg"
    # string mlbam ids (scraped payloads) hit the map too
    assert split_key_for_mlbam("jose_a_valdez", "838649") == "jose_valdez_sfg"


def test_split_key_for_mlbam_ignores_non_colliding_pairs():
    assert split_key_for_mlbam("jose_a_valdez", 123456) is None
    assert split_key_for_mlbam("someone_else", 838649) is None
    assert split_key_for_mlbam("jose_a_valdez", None) is None
    assert split_key_for_mlbam("jose_a_valdez", "not-an-id") is None


# ---------------------------------------------------------------------------
# The generic guard at the binding seam (stats._apply_collision_guard)
# ---------------------------------------------------------------------------

def test_guard_allowlisted_split_binds_under_split_key():
    cache: dict = {}
    rid = stats._apply_collision_guard(cache, "jose_a_valdez", 838649,
                                       durable=({}, {}))
    # The requested key does NOT get the newcomer's id...
    assert rid is None
    assert cache["jose_a_valdez"] is None
    # ...the split key does.
    assert cache["jose_valdez_sfg"] == 838649


def test_guard_forks_newcomer_when_key_durably_bound_to_other_id():
    # Incumbent: slug "shared_slug" durably owns mlbam 111 (player_photos).
    durable = ({"shared_slug": 111}, {111: "shared_slug"})
    cache: dict = {}
    rid = stats._apply_collision_guard(cache, "shared_slug", 222,
                                       durable=durable)
    # Requested key keeps resolving to its durable incumbent id.
    assert rid == 111
    assert cache["shared_slug"] == 111
    # The newcomer id is parked under a discriminated key.
    assert cache["shared_slug_222"] == 222


def test_guard_refuses_id_that_durably_belongs_to_another_key():
    durable = ({"owner_key": 333}, {333: "owner_key"})
    cache: dict = {}
    rid = stats._apply_collision_guard(cache, "colliding_key", 333,
                                       durable=durable)
    assert rid is None
    assert cache["colliding_key"] is None
    # The owner's binding is never rewritten.
    assert "owner_key" not in cache


def test_guard_same_id_re_resolve_is_stable():
    durable = ({"jane_doe": 444}, {444: "jane_doe"})
    cache: dict = {}
    for _ in range(2):  # resolve twice -> identical, no fork churn
        rid = stats._apply_collision_guard(cache, "jane_doe", 444,
                                           durable=durable)
        assert rid == 444
        assert cache["jane_doe"] == 444
    assert "jane_doe_444" not in cache


def test_guard_no_durable_binding_binds_normally():
    cache: dict = {}
    rid = stats._apply_collision_guard(cache, "fresh_key", 555,
                                       durable=({}, {}))
    assert rid == 555
    assert cache["fresh_key"] == 555


# ---------------------------------------------------------------------------
# The discovery seam (mlbam_ingest._collision_safe_key)
# ---------------------------------------------------------------------------

def test_two_identities_same_slug_get_two_distinct_keys():
    durable_by_key = {"shared_slug": 100}
    incumbent = mlbam_ingest._collision_safe_key("shared_slug", 100,
                                                 durable_by_key)
    newcomer = mlbam_ingest._collision_safe_key("shared_slug", 200,
                                                durable_by_key)
    assert incumbent == "shared_slug"          # incumbent keeps the slug
    assert newcomer == "shared_slug_200"       # newcomer is forked
    assert incumbent != newcomer
    # Same mlbam re-resolves to the same (stable) key.
    assert mlbam_ingest._collision_safe_key("shared_slug", 200,
                                            durable_by_key) == newcomer
    assert mlbam_ingest._collision_safe_key("shared_slug", 100,
                                            durable_by_key) == incumbent


def test_ingest_allowlist_wins_over_generic_fork():
    # Even with no durable binding, the allowlisted pair routes to the
    # registered split key (not the generic f"{slug}_{id}" form).
    assert mlbam_ingest._collision_safe_key("jose_a_valdez", 838649, {}) \
        == "jose_valdez_sfg"


def test_ingest_unknown_slug_passes_through():
    assert mlbam_ingest._collision_safe_key("brand_new_guy", 999, {}) \
        == "brand_new_guy"


# ---------------------------------------------------------------------------
# resolve_mlbam_id cache-hit healing (no network: returns before any fetch)
# ---------------------------------------------------------------------------

def test_resolve_heals_stale_pre_split_cache_binding(tmp_path, monkeypatch):
    cache_file = tmp_path / "mlbam_ids.json"
    cache_file.write_text(json.dumps({"jose_a_valdez": 838649}))
    monkeypatch.setattr(stats, "ID_CACHE_FILE", cache_file)

    got = stats.resolve_mlbam_id("jose_a_valdez", "Jose A. Valdez")

    # The stale binding no longer serves the newcomer's id...
    assert got is None
    healed = json.loads(cache_file.read_text())
    assert healed["jose_a_valdez"] is None
    # ...and the id has been re-homed under the split key.
    assert healed["jose_valdez_sfg"] == 838649


def test_resolve_cache_hit_untouched_for_normal_players(tmp_path, monkeypatch):
    cache_file = tmp_path / "mlbam_ids.json"
    cache_file.write_text(json.dumps({"konnor_griffin": 700000}))
    monkeypatch.setattr(stats, "ID_CACHE_FILE", cache_file)

    assert stats.resolve_mlbam_id("konnor_griffin", "Konnor Griffin") == 700000
    # No rewrite happened.
    assert json.loads(cache_file.read_text()) == {"konnor_griffin": 700000}
