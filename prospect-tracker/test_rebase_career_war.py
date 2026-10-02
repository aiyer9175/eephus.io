# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/rebase_career_war.py, the rebase with a provider parameter (fWAR label
epoch precondition E3 part 4), offline on a throwaway sqlite file and a fixture
vintage, the funnel test's pattern: nothing here reads prospects.db,
data/fwar_vintage.json, data/ewar.json or the network.

Pinned: the dry run writes nothing; apply twice equals apply once (plain
--apply refuses the second time, --reapply re-derives); the incumbent eWAR v2
series reconstructs from the table bit for bit; the neither-value abort fires;
pre-2011 seasons keep the incumbent and are counted mixed; --provider ewar_v2
writes exactly the L1 tool's payload; both providers report one receipt schema.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import rebase_career_war as RB              # noqa: E402
import rebase_career_war_to_ewar as L1      # noqa: E402


def _grp(rows: dict, status: str = "frozen") -> dict:
    return {"status": status, "fields": ["war", "rar", "numTeams"],
            "rows": {str(k): [v, None, 1] for k, v in rows.items()}}


VINTAGE = {
    "schema": "fwar_vintage/1", "vintage_id": "2026-10-05-0123456789ab",
    "seasons": {
        "2018": {"hitting": _grp({2002: 0.37}), "pitching": _grp({1001: 2.91})},
        "2019": {"hitting": _grp({}), "pitching": _grp({1001: 0.55})},
        "2020": {"hitting": _grp({2002: 2.24}), "pitching": _grp({})},
        # pre-2011, pitching absent: mixed, served by nothing
        "2009": {"hitting": _grp({2002: 9.9}), "pitching": _grp({}, "absent")},
    },
}

EWAR = {"model": "ewar_v2", "generated_at": "2026-09-03T00:00:00", "seasons": [2016, 2026],
        "players": {"1001": {"2018": {"ew": 2.4, "bw": 1.5, "ewp": 2.4, "bwp": 1.5},
                             "2019": {"ew": 0.7, "bw": 1.9, "ewp": 0.7, "bwp": 1.9}},
                    "2002": {"2020": {"ew": 3.1, "bw": 3.1, "ewb": 3.1, "bwb": 3.1}}}}

# the table as the eWAR epoch left it: two rebased rows, one bbref row the
# eWAR rebase could not resolve, one bbref row no resolver knows
TABLE = {
    "pitcher": {"seasons": {"2015": 0.8, "2018": 2.4, "2019": 0.7},
                "seasons_bwar": {"2015": 0.8, "2018": 1.5, "2019": 1.9},
                "career_war": 3.9, "war_per_yr": 1.3, "war_seasons_count": 3,
                "source": "ewar_v2", "ewar_coverage": {"n_seasons": 3, "n_ewar": 2}},
    "hitter": {"seasons": {"2009": 1.1, "2020": 3.1}, "seasons_bwar": {"2009": 1.1, "2020": 3.1},
               "career_war": 4.2, "war_per_yr": 2.1, "war_seasons_count": 2,
               "source": "ewar_v2"},
    "late_id": {"seasons": {"2018": 0.123456}, "career_war": 0.12, "war_per_yr": 0.12,
                "war_seasons_count": 1, "source": "bbref"},
    "ghost": {"seasons": {"2020": 0.4}, "career_war": 0.4, "war_per_yr": 0.4,
              "war_seasons_count": 1, "source": "bbref"},
}


@pytest.fixture
def db(monkeypatch, tmp_path):
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_rebase.db", raising=False)
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    monkeypatch.setattr(L1, "durable_ids_by_key", lambda: {"pitcher": 1001})
    monkeypatch.setattr(L1, "override_ids", lambda: {"hitter": 2002, "late_id": 3003})
    storage.upsert_career_war(json.loads(json.dumps(TABLE)))
    yield storage


def _run(args, payload=VINTAGE):
    return RB.main(args, payload=payload)


def test_the_dry_run_writes_nothing(db, tmp_path, capsys):
    before = db.load_career_war()
    assert _run(["--provider", "fwar"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert db.load_career_war() == before
    assert not list(tmp_path.glob("*.bak-*"))


def test_apply_writes_fwar_keeps_the_incumbent_and_backs_up(db, tmp_path):
    before = db.load_career_war()
    assert _run(["--provider", "fwar", "--apply"]) == 0
    after = db.load_career_war()
    bak = tmp_path / f"test_rebase.db.bak-fwar-{dt.date.today().isoformat()}"
    assert bak.exists()
    with sqlite3.connect(str(bak)) as con:
        assert con.execute("SELECT COUNT(*) FROM career_war").fetchone()[0] == 4
    p = after["pitcher"]
    assert p["source"] == "fwar"
    assert p["seasons"] == {"2015": 0.8, "2018": 2.91, "2019": 0.55}   # 2015 not in the vintage
    assert p["seasons_ewar_v2"] == before["pitcher"]["seasons"]
    assert p["seasons_bwar"] == before["pitcher"]["seasons_bwar"]
    assert p["ewar_coverage"] == before["pitcher"]["ewar_coverage"]
    assert p["career_war"] == round(0.8 + 2.91 + 0.55, 2) and p["war_seasons_count"] == 3
    cov = p["fwar_coverage"]
    assert cov["vintage_id"] == "2026-10-05-0123456789ab" and cov["war_basis"] == "mixed"
    assert cov["fallback_pre_years"] == [2015] and cov["incumbent_source"] == "ewar_v2"
    h = after["hitter"]
    assert h["seasons"] == {"2009": 1.1, "2020": 2.24}                   # 2009 is mixed: incumbent
    assert h["fwar_coverage"]["fallback_pre_years"] == [2009]
    lat = after["late_id"]                     # a bbref row: its incumbent is what it served
    assert lat["seasons"] == {"2018": 0.123456}                          # no feed row for 3003
    assert lat["fwar_coverage"]["fallback_post_years"] == [2018]
    assert lat["seasons_ewar_v2"] == {"2018": 0.123456} and lat["seasons_bwar"] == {"2018": 0.123456}
    assert after["ghost"] == before["ghost"]                             # unresolved: untouched


def test_the_incumbent_reconstructs_bit_for_bit(db):
    before = db.load_career_war()
    _run(["--provider", "fwar", "--apply"])
    after = db.load_career_war()
    for key, row in before.items():
        rebuilt = after[key].get("seasons_ewar_v2") or after[key]["seasons"]
        assert rebuilt == row["seasons"], key
        assert all(type(a) is type(b) and a == b
                   for a, b in zip(rebuilt.values(), row["seasons"].values())), key
    assert RB.incumbent_breaks(before, after, "fwar") == []


def test_apply_twice_equals_apply_once(db, capsys):
    assert _run(["--provider", "fwar", "--apply"]) == 0
    once = db.load_career_war()
    assert _run(["--provider", "fwar", "--apply"]) == 2            # the once-only guard
    assert "REFUSED" in capsys.readouterr().out
    assert db.load_career_war() == once
    assert _run(["--provider", "fwar", "--reapply"]) == 0
    assert db.load_career_war() == once
    # the re-derivation reads the kept incumbent, never the served series
    tampered = dict(once["pitcher"])
    tampered["seasons"] = {"2015": 9.9, "2018": 9.9, "2019": 9.9}
    idx = RB.war_source.fwar_index(VINTAGE)
    again = RB.rebase_row_fwar(tampered, 1001, idx)
    assert again["seasons"] == once["pitcher"]["seasons"]
    # an fwar row that lost its kept incumbent cannot be rebased
    lost = dict(once["pitcher"])
    lost.pop("seasons_ewar_v2")
    assert RB.rebase_row_fwar(lost, 1001, idx) is None


def test_the_neither_value_abort_fires_and_writes_nothing(db, tmp_path, capsys):
    db.upsert_career_war({"broken": {"seasons": {"2009": None, "2018": 0.2}, "career_war": 0.2,
                                     "war_per_yr": 0.1, "war_seasons_count": 2,
                                     "source": "ewar_v2"}})
    import storage
    before = storage.load_career_war()
    with pytest.raises(RB.RebaseAbort, match="neither"):
        RB.plan(before, "fwar", VINTAGE)
    assert _run(["--provider", "fwar", "--apply"]) == 3
    assert "ABORT" in capsys.readouterr().out
    assert storage.load_career_war() == before
    assert not list(tmp_path.glob("*.bak-*"))
    assert RB.neither_value(before) == [("broken", "2009")]
    # a season with an fWAR value and no incumbent value is NOT a neither
    assert RB.neither_value({"k": {"seasons": {"2018": 2.91},
                                   "seasons_ewar_v2": {"2018": None}}}) == []


def test_the_receipt_counts_mixed_and_has_one_schema_for_both_providers(db):
    rows = db.load_career_war()
    _, rf = RB.plan(rows, "fwar", VINTAGE)
    _, re_ = RB.plan(rows, "ewar_v2", EWAR)
    assert set(rf) == set(re_) == set(RB.receipt_keys())
    assert rf["schema"] == re_["schema"] == RB.RECEIPT_SCHEMA
    assert rf["rows"] == 4 and rf["rows_rebased"] == 3 and rf["rows_unresolved"] == 1
    assert rf["seasons_mixed"] == 2                     # pitcher 2015 + hitter 2009
    assert rf["seasons_fallback_post"] == 1             # late_id 2018: no feed row
    assert rf["seasons_provider"] == 3
    assert rf["rows_war_basis"] == {"mixed": 3}
    assert rf["artifact"]["id"] == "2026-10-05-0123456789ab"
    assert rf["artifact"]["non_fwar_seasons"] == [2009]
    assert rf["incumbent_key"] == "seasons_ewar_v2" and re_["incumbent_key"] == "seasons_bwar"
    assert rf["neither_value"] == [] and rf["incumbent_breaks"] == []


def test_provider_ewar_v2_writes_exactly_the_l1_payload(db):
    rows = db.load_career_war()
    mine, rep = RB.plan(rows, "ewar_v2", EWAR)
    theirs, old = L1.plan(rows, EWAR)
    assert mine == theirs
    assert rep["rows_rebased"] == old["rows_rebased"]
    assert rep["seasons_provider"] == old["seasons_ewar"]
    assert rep["seasons_changed"] == old["seasons_changed"]


def test_the_rebase_and_the_funnel_share_one_transform(monkeypatch):
    seen = []

    def spy(inc, mlbam, idx):
        seen.append(mlbam)
        return dict(inc), {"n_seasons": len(inc), "n_fwar": 0, "n_fallback_pre": len(inc),
                           "n_fallback_post": 0, "fallback_pre_years": [],
                           "fallback_post_years": [], "war_basis": "mixed"}
    monkeypatch.setattr(RB.war_source, "fwar_seasons_from_incumbent", spy)
    RB.rebase_row_fwar(TABLE["pitcher"], 1001, {"vintage_id": "x"})
    assert seen == [1001]


def test_an_incumbent_payload_on_an_fwar_row_refreshes_the_kept_series(db):
    """A nightly ewar_v2 payload that lands on a rebased row (the order the
    runbook forbids, guarded anyway): its seasons ARE the incumbent, so they
    refresh seasons_ewar_v2 and every kept season survives the merge."""
    _run(["--provider", "fwar", "--apply"])
    db.upsert_career_war({"pitcher": {"seasons": {"2019": 0.75, "2020": 1.0},
                                      "seasons_bwar": {"2019": 1.9, "2020": 1.2},
                                      "career_war": 1.75, "war_per_yr": 0.88,
                                      "war_seasons_count": 2, "source": "ewar_v2"}})
    row = db.load_career_war()["pitcher"]
    assert row["seasons_ewar_v2"] == {"2015": 0.8, "2018": 2.4, "2019": 0.75, "2020": 1.0}
    assert row["source"] == "ewar_v2"
    # --reapply restores the fwar basis from the refreshed incumbent
    assert _run(["--provider", "fwar", "--reapply"]) == 0
    row = db.load_career_war()["pitcher"]
    assert row["source"] == "fwar"
    assert row["seasons"] == {"2015": 0.8, "2018": 2.91, "2019": 0.55, "2020": 1.0}


def test_the_old_entry_point_is_untouched():
    src = (HERE / "tools" / "rebase_career_war_to_ewar.py").read_text(encoding="utf-8")
    assert "def main(" in src and "bak-ewar-" in src
    assert RB.PROVIDERS == ("ewar_v2", "fwar")
