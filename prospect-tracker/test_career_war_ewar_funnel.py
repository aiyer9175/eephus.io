# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The career_war funnel under the eWAR epoch (2026-09-03), offline.

Three contracts, each pinned on a throwaway sqlite file and a synthetic
ewar.json payload, so nothing here reads prospects.db, data/ewar.json or the
network:

  1. storage.upsert_career_war MERGES `seasons_bwar` by the same union rule as
     `seasons`, recomputes the aggregates over the served series, lets the
     new payload's `source` win, and leaves a legacy payload on a legacy row
     byte-identical to the pre-epoch behaviour.
  2. tools/rebase_career_war_to_ewar.py is idempotent: apply twice == apply
     once, because an ewar_v2 row is re-derived from `seasons_bwar` and never
     from its served `seasons`; seasons outside the artifact fall back to
     bWAR and the receipt counts them.
  3. run_monthly's career-WAR step calls war_source.career_war_bulk on the
     default provider (a static pin on the source text).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import rebase_career_war_to_ewar as rebase  # noqa: E402


@pytest.fixture
def db(monkeypatch, tmp_path):
    """storage pointed at a throwaway DB with the schema applied."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_career_war.db", raising=False)
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    yield storage


def _row(db, key):
    return db.load_career_war()[key]


# a two-player synthetic artifact: a pitcher whose eWAR differs from bWAR and a
# position player whose eWAR equals bWAR (w = 0.0 fielding: exact by design)
PAYLOAD = {
    "model": "ewar_v2", "generated_at": "2026-09-03T00:00:00", "seasons": [2016, 2026],
    "players": {
        "1001": {"2018": {"ew": 2.4, "bw": 1.5, "ewp": 2.4, "bwp": 1.5},
                 "2019": {"ew": 0.7, "bw": 1.9, "ewp": 0.7, "bwp": 1.9}},
        "2002": {"2020": {"ew": 3.1, "bw": 3.1, "ewb": 3.1, "bwb": 3.1}},
    },
}


# --------------------------------------------------------------------------- #
# 1. upsert merge
# --------------------------------------------------------------------------- #
def test_legacy_payload_on_legacy_row_merges_exactly_as_before(db):
    db.upsert_career_war({"p": {"seasons": {"2015": 1.0, "2016": 2.0}, "career_war": 3.0,
                                "war_per_yr": 1.5, "war_seasons_count": 2, "source": "bbref"}})
    db.upsert_career_war({"p": {"seasons": {"2016": 2.5, "2017": 0.5}, "career_war": 3.0,
                                "war_per_yr": 1.5, "war_seasons_count": 2, "source": "bbref"}})
    r = _row(db, "p")
    assert r["seasons"] == {"2015": 1.0, "2016": 2.5, "2017": 0.5}   # union, new wins
    assert r["career_war"] == 4.0
    assert r["war_seasons_count"] == 3
    assert r["war_per_yr"] == round(4.0 / 3, 3)
    assert "seasons_bwar" not in r                                    # legacy stays legacy
    assert r["source"] == "bbref"


def test_ewar_payload_merges_both_series_and_source_wins(db):
    db.upsert_career_war({"p": {"seasons": {"2015": 1.0, "2016": 2.0}, "career_war": 3.0,
                                "war_per_yr": 1.5, "war_seasons_count": 2, "source": "bbref"}})
    db.upsert_career_war({"p": {"seasons": {"2016": 2.8, "2017": 0.9},
                                "seasons_bwar": {"2016": 2.0, "2017": 0.5},
                                "career_war": 3.7, "war_per_yr": 1.85,
                                "war_seasons_count": 2, "source": "ewar_v2",
                                "ewar_coverage": {"n_seasons": 2}}})
    r = _row(db, "p")
    assert r["seasons"] == {"2015": 1.0, "2016": 2.8, "2017": 0.9}
    assert r["seasons_bwar"] == {"2016": 2.0, "2017": 0.5}
    assert r["career_war"] == 4.7                        # recomputed over served
    assert r["war_seasons_count"] == 3
    assert r["source"] == "ewar_v2"
    assert r["ewar_coverage"] == {"n_seasons": 2}
    # a second eWAR payload with a narrower window deletes nothing on either series
    db.upsert_career_war({"p": {"seasons": {"2018": -0.2}, "seasons_bwar": {"2018": -0.1},
                                "career_war": -0.2, "war_per_yr": -0.2,
                                "war_seasons_count": 1, "source": "ewar_v2"}})
    r = _row(db, "p")
    assert r["seasons"] == {"2015": 1.0, "2016": 2.8, "2017": 0.9, "2018": -0.2}
    assert r["seasons_bwar"] == {"2016": 2.0, "2017": 0.5, "2018": -0.1}
    assert r["career_war"] == 4.5


def test_legacy_bbref_payload_on_ewar_row_refreshes_the_frame_and_source(db):
    """Pre-L2 monthly runs still hand the table bWAR payloads. On a rebased
    row they must refresh seasons_bwar (their seasons ARE the frame) and the
    stored frame must survive, so --reapply can re-derive the served series."""
    db.upsert_career_war({"p": {"seasons": {"2018": 2.4}, "seasons_bwar": {"2018": 1.5},
                                "career_war": 2.4, "war_per_yr": 2.4,
                                "war_seasons_count": 1, "source": "ewar_v2"}})
    db.upsert_career_war({"p": {"seasons": {"2018": 1.6, "2019": 1.9}, "career_war": 3.5,
                                "war_per_yr": 1.75, "war_seasons_count": 2, "source": "bbref"}})
    r = _row(db, "p")
    assert r["source"] == "bbref"                        # new payload's source wins
    assert r["seasons"] == {"2018": 1.6, "2019": 1.9}
    assert r["seasons_bwar"] == {"2018": 1.6, "2019": 1.9}


# --------------------------------------------------------------------------- #
# 2. the rebase transform
# --------------------------------------------------------------------------- #
def test_transform_uses_ewar_where_present_and_bwar_elsewhere():
    frame = {"2015": 0.8, "2018": 1.5, "2019": 1.9}
    seasons, counts = rebase.transform_seasons(frame, 1001, PAYLOAD)
    assert seasons == {"2015": 0.8, "2018": 2.4, "2019": 0.7}
    assert counts == {"n_ewar": 2, "n_fallback_pre": 1, "n_fallback_post": 0}
    # a player-season inside the window but absent from the artifact falls back too
    seasons, counts = rebase.transform_seasons({"2021": 0.3}, 2002, PAYLOAD)
    assert seasons == {"2021": 0.3}
    assert counts == {"n_ewar": 0, "n_fallback_pre": 0, "n_fallback_post": 1}


def test_position_player_is_bwar_exact_at_w_zero():
    row = {"seasons": {"2020": 3.1}, "career_war": 3.1, "war_per_yr": 3.1,
           "war_seasons_count": 1, "source": "bbref"}
    new = rebase.rebase_row(row, 2002, PAYLOAD)
    assert new["seasons"] == new["seasons_bwar"] == {"2020": 3.1}
    assert new["source"] == "ewar_v2"
    assert new["ewar_coverage"]["n_ewar"] == 1


def test_rebase_is_idempotent_and_never_reads_served_seasons_twice():
    legacy = {"seasons": {"2015": 0.8, "2018": 1.5, "2019": 1.9}, "career_war": 4.2,
              "war_per_yr": 1.4, "war_seasons_count": 3, "source": "bbref"}
    once = rebase.rebase_row(legacy, 1001, PAYLOAD)
    assert once["seasons"] == {"2015": 0.8, "2018": 2.4, "2019": 0.7}
    assert once["seasons_bwar"] == {"2015": 0.8, "2018": 1.5, "2019": 1.9}
    assert once["career_war"] == 3.9
    assert once["war_per_yr"] == 1.3
    assert once["war_seasons_count"] == 3
    twice = rebase.rebase_row(once, 1001, PAYLOAD)
    assert twice == once
    # the frame is what gets re-derived: tamper with the served series and the
    # second pass ignores it
    tampered = dict(once)
    tampered["seasons"] = {"2015": 9.9, "2018": 9.9, "2019": 9.9}
    assert rebase.rebase_row(tampered, 1001, PAYLOAD) == once
    # an ewar_v2 row that lost its frame cannot be rebased
    lost = dict(once)
    lost.pop("seasons_bwar")
    assert rebase.rebase_row(lost, 1001, PAYLOAD) is None


def test_rebase_through_storage_twice_equals_once(db, monkeypatch):
    db.upsert_career_war({
        "pitcher": {"seasons": {"2015": 0.8, "2018": 1.5, "2019": 1.9}, "career_war": 4.2,
                    "war_per_yr": 1.4, "war_seasons_count": 3, "source": "bbref"},
        "hitter": {"seasons": {"2020": 3.1}, "career_war": 3.1, "war_per_yr": 3.1,
                   "war_seasons_count": 1, "source": "bbref"},
        "ghost": {"seasons": {"2020": 0.4}, "career_war": 0.4, "war_per_yr": 0.4,
                  "war_seasons_count": 1, "source": "bbref"},
    })
    monkeypatch.setattr(rebase, "durable_ids_by_key", lambda: {"pitcher": 1001})
    monkeypatch.setattr(rebase, "override_ids", lambda: {"hitter": 2002, "pitcher": 9999})
    new, rep = rebase.plan(db.load_career_war(), PAYLOAD)
    assert rep["rows"] == 3 and rep["rows_rebased"] == 2 and rep["rows_unresolved"] == 1
    assert rep["unresolved_keys"] == ["ghost"]
    assert rep["id_from_photos"] == 1 and rep["id_from_override"] == 1
    assert rep["override_disagrees_with_photos"] == [("pitcher", 1001, 9999)]   # photos wins
    assert rep["seasons"] == 5 and rep["seasons_ewar"] == 3
    assert rep["seasons_fallback_pre"] == 1 and rep["seasons_fallback_post"] == 0
    assert rep["seasons_changed"] == 2
    assert rep["abs_delta_sum"] == pytest.approx(0.9 + 1.2)
    db.upsert_career_war(new)
    first = db.load_career_war()
    assert first["pitcher"]["seasons"] == {"2015": 0.8, "2018": 2.4, "2019": 0.7}
    assert first["pitcher"]["seasons_bwar"] == {"2015": 0.8, "2018": 1.5, "2019": 1.9}
    assert first["pitcher"]["source"] == "ewar_v2"
    assert first["ghost"]["source"] == "bbref"           # unresolved row untouched
    new2, rep2 = rebase.plan(first, PAYLOAD)
    assert rep2["rows_already_ewar"] == 2
    db.upsert_career_war(new2)
    assert db.load_career_war() == first


# --------------------------------------------------------------------------- #
# 3. the call site
# --------------------------------------------------------------------------- #
def test_run_monthly_career_war_step_goes_through_war_source_default_provider():
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    assert "war_source.career_war_bulk(" in src
    assert not re.search(r"(?<![\w.])fetch_career_war_bulk\s*\(", src), \
        "run_monthly must not call stats.fetch_career_war_bulk directly"
    # the default provider IS the served basis: the call site never pins one
    call = src[src.index("war_source.career_war_bulk("):]
    call = call[:call.index(")")]
    assert "provider" not in call
