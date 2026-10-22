# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The core eWAR label vintage and its provider (docs/efv-2026-10-22/
EWAR_CORE_LABEL_EPOCH_GATE.md part 3; task EFV_LABEL_EPOCH_EWAR).

Pins: the frozen file reproduces from its inputs; the identities of part 3; the
write-once rule; the provider is servable and NOT the default; display doors and
every other provider read an ewar_core row exactly as they read the fwar row it was
built on; the career_war rebase onto ewar_core reconstructs its fwar incumbent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ewar_core_label as C
import war_source

ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def frozen() -> dict:
    if not C.available():
        pytest.skip("data/ewar_core_label.json is not frozen in this checkout")
    return C.load()


def test_flag_off_and_default_unchanged():
    assert war_source.LABEL_EWAR_CORE is False
    assert war_source.DEFAULT_PROVIDER == "fwar"
    assert "ewar_core" in war_source.PROVIDERS
    assert war_source.DISPLAY_PROVIDER in ("ewar_v3", "ewar_v2")
    assert war_source.EWAR_CORE_BUILD_CMD == C.BUILD_CMD


def test_frozen_file_reproduces_from_its_inputs(frozen):
    fresh = C.build(log=lambda *a, **k: None)
    assert fresh["content_sha256"] == frozen["content_sha256"]
    assert fresh["vintage_id"] == frozen["vintage_id"]
    assert frozen["vintage_id"] == C.make_vintage_id(frozen["fwar_vintage_id"], frozen["content_sha256"])
    import fwar_vintage
    assert frozen["fwar_vintage_id"] == fwar_vintage.load()["vintage_id"]


def test_identities(frozen):
    seasons = frozen["seasons"]
    assert int(frozen["first_season"]) == 2000
    for s in ("2000", "2001"):
        assert seasons[s]["bat"] == {}, "no part departs before 2002"
    for s, blk in seasons.items():
        # CORE keeps each season's published fWAR total (stored rounding allowed)
        tot = sum(blk["bat"].values())
        assert abs(tot) <= 1e-6 + 5e-7 * len(blk["bat"]), (s, tot)
        if int(s) < 2016:
            assert blk["pit_r2"] == {}, "R2 starts in 2016"


def test_write_once(tmp_path, frozen):
    p = tmp_path / "label.json"
    path, how = C.write(frozen, p)
    assert how == "written" and path == p
    assert C.write(frozen, p)[1] == "unchanged"
    other = dict(frozen, content_sha256="0" * 64, vintage_id="ewar-core-x-000000000000")
    with pytest.raises(C.EwarCoreLabelRefusal):
        C.write(other, p)


def test_departures_series(frozen):
    head = C.departures(series="headline")
    real = C.departures(series="realized")
    assert all(set(c) == {"bat"} for c in head.values())
    assert any("pit" in c for c in real.values())
    for k, c in head.items():
        assert real[k]["bat"] == c["bat"]
    with pytest.raises(ValueError):
        C.departures(series="full")


def _fwar_row(mid: int) -> dict:
    return {"seasons": {"2015": 1.5, "2016": 2.25, "1999": 0.4},
            "career_war": 4.15, "war_per_yr": 1.38, "war_seasons_count": 3, "source": "fwar",
            "seasons_ewar_v2": {"2015": 1.4, "2016": 2.0, "1999": 0.4},
            "seasons_bwar": {"2015": 1.4, "2016": 2.0, "1999": 0.4},
            "fwar_coverage": {"vintage_id": "x", "mlbam": mid, "fallback_pre_years": [1999],
                              "fallback_post_years": [], "war_basis": "mixed"}}


def _a_departing_hitter(frozen) -> int:
    for m in frozen["seasons"]["2016"]["bat"]:
        if m in frozen["seasons"]["2015"]["bat"]:
            return int(m)
    raise AssertionError("no hitter departs in both 2015 and 2016")


def test_row_round_trip_and_display_doors(frozen):
    mid = _a_departing_hitter(frozen)
    row = _fwar_row(mid)
    core = war_source.row_on_provider(row, "ewar_core")
    assert core["source"] == "ewar_core" and core["seasons_fwar"] == row["seasons"]
    d16 = frozen["seasons"]["2016"]["bat"][str(mid)]
    assert core["seasons"]["2016"] == round(2.25 + d16, 2)
    assert core["seasons"]["1999"] == 0.4, "a season the vintage did not serve keeps its value"
    assert core["ewar_core_coverage"]["vintage_id"] == frozen["vintage_id"]
    # every other provider reads the core row as it reads the fwar row
    for prov in ("fwar", "ewar_v2", "bwar", "ewar_v3"):
        assert war_source.row_on_provider(core, prov) == war_source.row_on_provider(row, prov), prov
    assert war_source.row_on_provider(core, "ewar_core") == core
    # a non-fwar row is returned as stored
    v2 = {"seasons": {"2015": 1.0}, "source": "ewar_v2"}
    assert war_source.row_on_provider(v2, "ewar_core") == v2


def test_rebase_row_core_reconstructs_fwar(frozen):
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import rebase_career_war as RB
    assert "ewar_core" in RB.PROVIDERS and RB.INCUMBENT_KEY["ewar_core"] == "seasons_fwar"
    mid = _a_departing_hitter(frozen)
    idx = {"totals": {(mid, 2015): 1.5, (mid, 2016): 2.25}, "fwar_years": {2015, 2016},
           "vintage_id": "fixture"}
    row = {"seasons": {"2015": 1.4, "2016": 2.0}, "source": "ewar_v2",
           "seasons_bwar": {"2015": 1.4, "2016": 2.0}}
    fw = RB.rebase_row_fwar(row, mid, idx)
    core = RB.rebase_row_core(row, mid, idx)
    assert core["source"] == "ewar_core" and core["seasons_fwar"] == fw["seasons"]
    # idempotent: rebasing the core row again gives the same core row
    again = RB.rebase_row_core(core, mid, idx)
    assert again["seasons"] == core["seasons"] and again["seasons_fwar"] == core["seasons_fwar"]
    assert again["fwar_coverage"]["incumbent_source"] == core["fwar_coverage"]["incumbent_source"]
    assert RB.served_incumbent(core, "ewar_core") == fw["seasons"]
    assert RB.incumbent_breaks({"k": fw}, {"k": core}, "ewar_core") == []


def test_label_vintage_is_off_the_webroot():
    text = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8")
    assert "\newar_core_label.json\n" in text.replace("\r\n", "\n")


def test_fingerprint_label_term_unchanged_while_flag_off():
    import storage
    assert "|label=fwar@" in storage.board_basis_fingerprint()
