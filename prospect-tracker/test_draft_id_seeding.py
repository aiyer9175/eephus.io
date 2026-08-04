# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the draft-time MLBAM id harvest (draft_promotion, J1).

A signed draftee used to depend entirely on name-search resolution for his
stats even when the draft API had already handed us his MLBAM id at ingest.
That is the residue of the negative-cache bug that left the whole 2026 draft
class without stats. `_harvest_known_mlbam_ids` collects the ids the system
already holds so `storage.bind_player_ids` can make them durable.

The whole point of the harvest is that it must never FUSE two identities, so
most of what is pinned here is the refusal to bind:
  * two sources disagreeing about one key,
  * two draft keys claiming one key,
  * an id that already belongs to a different key (the 'jack_natili' vs
    'jackson_natili' case measured on the live DB, which the key-side guard
    inside bind_player_ids does not cover).

Fully hermetic: the DB reads are stubbed, nothing is written anywhere.
"""

from __future__ import annotations

import inspect
import sqlite3
import unittest
from contextlib import contextmanager

import draft_promotion as DP


class _Patched:
    """Swap module attributes for the duration of a test."""

    def __init__(self, **attrs):
        self._attrs = attrs
        self._saved: dict = {}

    def __enter__(self):
        for name, value in self._attrs.items():
            self._saved[name] = getattr(DP, name)
            setattr(DP, name, value)
        return self

    def __exit__(self, *exc):
        for name, value in self._saved.items():
            setattr(DP, name, value)
        return False


def _harvest(pairs, by_key, tj=None, owned=None):
    """Run `_harvest_known_mlbam_ids` with both DB reads stubbed.

    tj    = the {player_key: mlbam_id} the TJStats `_extras` index would return
    owned = the {mlbam_id(str): player_key} player_photos already holds
    """
    import storage
    saved = storage.load_mlbam_player_keys
    storage.load_mlbam_player_keys = lambda: dict(owned or {})
    try:
        with _Patched(_tjstats_extras_ids=lambda: dict(tj or {})):
            return DP._harvest_known_mlbam_ids(pairs, by_key)
    finally:
        storage.load_mlbam_player_keys = saved


class HarvestSources(unittest.TestCase):
    """Both in-system id sources reach the durable binding."""

    def test_draft_players_mlbam_id_is_harvested(self):
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {"mlbam_id": 814819}})
        self.assertEqual(out, {"ace_hurler": 814819})

    def test_tjstats_extras_id_is_harvested(self):
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {}},
                       tj={"ace_hurler": 803863})
        self.assertEqual(out, {"ace_hurler": 803863})

    def test_agreeing_sources_collapse_to_one_id(self):
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {"mlbam_id": 803863}},
                       tj={"ace_hurler": 803863})
        self.assertEqual(out, {"ace_hurler": 803863})

    def test_string_ids_coerce(self):
        """draft_players stores INTEGER, tjstats `_extras` stores a STRING."""
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {}},
                       tj={"ace_hurler": "814819"})
        self.assertEqual(out, {"ace_hurler": 814819})

    def test_unknown_id_yields_nothing(self):
        for missing in (None, "", 0, "n/a"):
            with self.subTest(missing=missing):
                out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                               {"draft_2026_ace_hurler": {"mlbam_id": missing}})
                self.assertEqual(out, {})

    def test_empty_input(self):
        self.assertEqual(_harvest([], {}), {})
        self.assertEqual(_harvest([("", ""), (None, "x")], {}), {})


class HarvestRefusesToFuse(unittest.TestCase):
    """Every ambiguity is dropped, never guessed at."""

    def test_disagreeing_sources_are_dropped(self):
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {"mlbam_id": 814819}},
                       tj={"ace_hurler": 803863})
        self.assertEqual(out, {})

    def test_two_draft_keys_claiming_one_milb_key_are_dropped(self):
        """The Jake Bennett shape: one name-slug, two different people."""
        out = _harvest(
            [("draft_2022_jake_bennett", "jake_bennett"),
             ("draft_2026_jake_bennett", "jake_bennett")],
            {"draft_2022_jake_bennett": {"mlbam_id": 686294},
             "draft_2026_jake_bennett": {"mlbam_id": 814385}},
        )
        self.assertEqual(out, {})

    def test_id_owned_by_a_different_key_is_not_rebound(self):
        """Measured live 2026-08-03: MLBAM 814385 is bound to
        'jackson_natili' while the draft API spells the pick 'jack_natili'.
        bind_player_ids guards the KEY side only; its ON CONFLICT(mlbam_id)
        would repoint the id row, so the harvest has to refuse first."""
        out = _harvest([("draft_2026_jack_natili", "jack_natili")],
                       {"draft_2026_jack_natili": {"mlbam_id": 814385}},
                       owned={"814385": "jackson_natili"})
        self.assertEqual(out, {})

    def test_id_owned_by_the_same_key_still_passes(self):
        """Already bound to the SAME key is not ambiguous - it is a no-op
        that bind_player_ids itself skips."""
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {"mlbam_id": 814819}},
                       owned={"814819": "ace_hurler"})
        self.assertEqual(out, {"ace_hurler": 814819})

    def test_no_binding_at_all_when_the_durable_index_is_unreadable(self):
        """Without player_photos there is no id-side guard, so the honest
        answer is to bind nothing rather than to bind blind."""
        import storage
        saved = storage.load_mlbam_player_keys

        def _boom():
            raise sqlite3.OperationalError("no such table: player_photos")

        storage.load_mlbam_player_keys = _boom
        try:
            with _Patched(_tjstats_extras_ids=lambda: {}):
                out = DP._harvest_known_mlbam_ids(
                    [("draft_2026_ace_hurler", "ace_hurler")],
                    {"draft_2026_ace_hurler": {"mlbam_id": 814819}})
        finally:
            storage.load_mlbam_player_keys = saved
        self.assertEqual(out, {})

    def test_only_supplied_pairs_are_considered(self):
        """The identity guards in seed_signed_draftees are the gate: a key
        that was never passed in must never be harvested, even when its id
        sits right there in the TJStats index."""
        out = _harvest([("draft_2026_ace_hurler", "ace_hurler")],
                       {"draft_2026_ace_hurler": {"mlbam_id": 814819}},
                       tj={"someone_else": 999999})
        self.assertEqual(out, {"ace_hurler": 814819})


class TjstatsExtrasIndex(unittest.TestCase):
    """`_tjstats_extras_ids` reads the id TJStats stamps into `_extras`."""

    def _con(self, rows):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE snapshots (source TEXT, player_key TEXT, "
                    "tools_json TEXT)")
        con.executemany("INSERT INTO snapshots VALUES (?, ?, ?)", rows)
        return con

    @contextmanager
    def _connect_to(self, con):
        with _Patched(connect=lambda: con):
            yield

    def test_reads_the_extras_id(self):
        con = self._con([
            ("tjstats", "ace_hurler",
             '{"fb": 60, "_extras": {"mlbam_id": "814819", "age": 21}}'),
        ])
        with self._connect_to(con):
            self.assertEqual(DP._tjstats_extras_ids(), {"ace_hurler": 814819})

    def test_ignores_non_tjstats_sources(self):
        con = self._con([
            ("fangraphs", "ace_hurler", '{"_extras": {"mlbam_id": "814819"}}'),
        ])
        with self._connect_to(con):
            self.assertEqual(DP._tjstats_extras_ids(), {})

    def test_key_with_two_different_ids_is_dropped(self):
        con = self._con([
            ("tjstats", "ace_hurler", '{"_extras": {"mlbam_id": "814819"}}'),
            ("tjstats", "ace_hurler", '{"_extras": {"mlbam_id": "803863"}}'),
        ])
        with self._connect_to(con):
            self.assertEqual(DP._tjstats_extras_ids(), {})

    def test_repeated_same_id_survives(self):
        con = self._con([
            ("tjstats", "ace_hurler", '{"_extras": {"mlbam_id": "814819"}}'),
            ("tjstats", "ace_hurler", '{"_extras": {"mlbam_id": 814819}}'),
        ])
        with self._connect_to(con):
            self.assertEqual(DP._tjstats_extras_ids(), {"ace_hurler": 814819})

    def test_tolerates_junk_payloads(self):
        con = self._con([
            ("tjstats", "a", "not json at all"),
            ("tjstats", "b", '{"fb": 60}'),
            ("tjstats", "c", '{"_extras": []}'),
            ("tjstats", "d", '{"_extras": {"mlbam_id": null}}'),
            ("tjstats", "", '{"_extras": {"mlbam_id": "1"}}'),
            ("tjstats", "e", '{"_extras": {"mlbam_id": "814819"}}'),
        ])
        with self._connect_to(con):
            self.assertEqual(DP._tjstats_extras_ids(), {"e": 814819})


class SeedCallerContract(unittest.TestCase):
    """The harvest is only as safe as WHERE it is called from.

    Every chip/caller bug this repo has shipped got through because the
    callee was tested and the CALL SITE was not. `bindable` must be filled
    only after the identity guards have run, and must not be gated on the
    board-grade check that follows them (a missing grade is a reason not to
    fabricate a snapshot, not a reason to drop a known id).
    """

    def test_bindable_is_appended_after_the_identity_guards(self):
        src = inspect.getsource(DP.seed_signed_draftees)
        self.assertIn("bindable.append((dk, mk))", src)
        i_append = src.index("bindable.append((dk, mk))")
        for guard in ("if earliest_signed.get(mk, yr) < yr:",
                      "if pre:",
                      "if not mk:"):
            with self.subTest(guard=guard):
                self.assertIn(guard, src)
                self.assertLess(src.index(guard), i_append,
                                f"{guard!r} must run BEFORE the id is bound")
        # ...and BEFORE the board-grade check, which is not an identity guard.
        self.assertLess(i_append, src.index("fv = _draft_board_consensus_fv(dk)"))

    def test_binding_goes_through_the_durable_storage_path(self):
        """No private cache format: reuse storage.bind_player_ids, the same
        path run_monthly step 2a uses."""
        src = inspect.getsource(DP.seed_signed_draftees)
        self.assertIn("from storage import bind_player_ids", src)
        self.assertIn("bind_player_ids(known_ids)", src)


if __name__ == "__main__":
    unittest.main()
