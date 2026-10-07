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


# ---------------------------------------------------------------------------
# The projections plain-key award (proj_export, 2026-10-04)
# ---------------------------------------------------------------------------
# Since the 2026-10-03 refetch Spotrac's year columns start at 2027, so a
# player whose only money was his 2026 salary now reads as a STATUS-ONLY row
# (ARB / PRE-ARB tokens, no money year, no signed_through). Counted as a
# contract, such a row moved three plain keys against the step A copy:
# jose_fermin from STL 665877 to LAA 820862 and logan_allen onto CLE 671106.
# A status-only row says which club controls a player, not which of two
# same-named players is the flagship, so it never moves a plain key.

def _status_only_row(team="los-angeles-angels"):
    return {"player_key": "jose_fermin", "team_slug": team, "aav_usd": 0,
            "salary_by_year": {}, "status_by_year": {2027: "PRE-ARB"},
            "signed_through": None, "position": "RP"}


def test_status_only_predicate():
    import spotrac
    assert spotrac.is_status_only(_status_only_row())
    priced = {**_status_only_row(), "salary_by_year": {2027: 800_000},
              "signed_through": 2027, "aav_usd": 800_000}
    assert not spotrac.is_status_only(priced)


def test_the_join_serves_no_zero_aav_for_a_status_only_row():
    import proj_export as pe
    ct = pe._join_contract(_status_only_row(), {"los-angeles-angels": "LAA"})
    assert ct["aav_usd"] is None and ct["status_only"] is True
    assert ct["status_by_year"] == {2027: "PRE-ARB"} and ct["team_code"] == "LAA"
    assert not pe._awards_plain_key(ct)
    # A priced row passes through with its AAV and no mark.
    priced = pe._join_contract({**_status_only_row(), "aav_usd": 900_000,
                                "salary_by_year": {2027: 900_000},
                                "signed_through": 2027}, {})
    assert priced["aav_usd"] == 900_000 and "status_only" not in priced


def test_a_status_only_row_never_moves_a_plain_key():
    import proj_export as pe
    stl = {"key": "jose_fermin__665877", "mlbam": 665877, "warTotal": 0.7}
    laa = {"key": "jose_fermin__820862", "mlbam": 820862, "warTotal": 1.2}
    ct = pe._join_contract(_status_only_row(), {"los-angeles-angels": "LAA"})
    # The contested award hands it to nobody...
    assert pe._award_winner([stl, laa], ct) is None
    # ...and a priced contract still goes to the highest projected WAR claimant.
    priced = pe._join_contract({**_status_only_row(), "aav_usd": 900_000,
                                "salary_by_year": {2027: 900_000},
                                "signed_through": 2027}, {})
    assert pe._awards_plain_key(priced)
    assert pe._award_winner([stl, laa], priced) is laa
    assert pe._award_winner([], priced) is None
    # Both award sites in the veteran builder go through the same predicate.
    import inspect
    src = inspect.getsource(pe._veteran_rows)
    assert "_awards_plain_key(ct)" in src and "_award_winner(rows, ct)" in src


def test_served_plain_keys_are_held_by_a_priced_contract():
    """On the served payload: a name two veterans share keeps its plain key
    only on a row a PRICED contract reached (it carries `thru`), and no veteran
    row serves a $0 AAV without a signed season."""
    from pathlib import Path
    p = Path(__file__).parent / "data" / "mlb_projections.json"
    if not p.exists():
        import pytest
        pytest.skip("data/mlb_projections.json not built")
    vets = json.loads(p.read_text("utf-8")).get("vets") or []
    keys = {v.get("key") for v in vets}
    bad = [v["key"] for v in vets
           if v.get("key") and "__" not in v["key"]
           and any(k and k.startswith(v["key"] + "__") for k in keys)
           and v.get("thru") is None]
    assert not bad, bad[:5]
    zero = [v["key"] for v in vets if v.get("aav") == 0 and v.get("thru") is None]
    assert not zero, zero[:5]
