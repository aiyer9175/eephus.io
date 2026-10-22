# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline eWAR label vintage and eFV's label switch (docs/efv-2026-10-22/
EWAR_HEADLINE_LABEL_GATE.md part 3; task EFV_LABEL_HEADLINE_EWAR_CHECK).

Pins: the frozen file reproduces from its inputs; the identities of part 3 (identity 3
under amendment 9.1); the write-once rule; the label series equals the displayed eWAR v3
transform of the same fwar row at the freeze; the switch is scoped to efv_dataset's label
(amendment 9.2: DEFAULT_PROVIDER, the table and efv_labels' frames untouched) and reads the
label through war_source.efv_label_seasons; the fingerprint's label term follows the switch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ewar_headline_label as H
import war_source

ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def frozen() -> dict:
    if not H.available():
        pytest.skip("data/ewar_headline_label.json is not frozen in this checkout")
    return H.load()


def test_switch_is_scoped_to_efv():
    assert war_source.DEFAULT_PROVIDER == "fwar"
    assert war_source.LABEL_EWAR_CORE is False
    assert war_source.EFV_LABEL_PROVIDER == ("ewar_headline" if war_source.EFV_LABEL_EWAR_HEADLINE
                                             else war_source.DEFAULT_PROVIDER)
    assert "ewar_headline" not in war_source.PROVIDERS, "no door serves the eFV label"
    assert war_source.DISPLAY_PROVIDER in ("ewar_v3", "ewar_v2")


def test_frozen_file_reproduces_from_its_inputs(frozen):
    fresh = H.build(log=lambda *a, **k: None)
    assert fresh["content_sha256"] == frozen["content_sha256"]
    assert fresh["vintage_id"] == frozen["vintage_id"]
    assert frozen["vintage_id"] == H.make_vintage_id(frozen["fwar_vintage_id"], frozen["content_sha256"])
    import fwar_vintage
    assert frozen["fwar_vintage_id"] == fwar_vintage.load()["vintage_id"]


def test_identities(frozen):
    seasons = frozen["seasons"]
    for s, blk in seasons.items():
        if int(s) < H.FIRST_HEADLINE_SEASON:
            assert blk["bat"] == {} and blk["pit"] == {}, f"identity 4: {s}"
        for side in ("bat", "pit"):
            tot = sum(blk[side].values())
            assert abs(tot) <= 5e-7 * len(blk[side]) + 1e-9, (s, side, tot)
    # identity 2 against the artifact, both series
    import ewar_v3
    for name in H.SERIES:
        want = ewar_v3.departures(series=name)
        got = H.departures(series=name)
        assert set(got) <= set(want)
        for k, cell in want.items():
            for side, v in cell.items():
                assert abs(got.get(k, {}).get(side, 0.0) - v) <= 5e-7, (name, k, side)


def test_write_once(tmp_path, frozen):
    p = tmp_path / "label.json"
    path, how = H.write(frozen, p)
    assert how == "written" and path == p
    assert H.write(frozen, p)[1] == "unchanged"
    other = dict(frozen, content_sha256="0" * 64, vintage_id="ewar-headline-x-000000000000")
    with pytest.raises(H.EwarHeadlineLabelRefusal):
        H.write(other, p)


def test_build_refuses_a_pre_2026_headline_departure(frozen):
    import copy
    import ewar_v3
    pay = copy.deepcopy(ewar_v3.load())
    mid, blk = next(iter(pay["players"].items()))
    pay["players"][mid]["2024"] = {"dh": {"bat": 0.5}, "dr": {"bat": 0.5}}
    with pytest.raises(H.EwarHeadlineLabelRefusal, match="identity 4"):
        H.build(v3=pay, log=lambda *a, **k: None)


def test_build_refuses_another_fwar_vintage():
    import ewar_v3
    with pytest.raises(H.EwarHeadlineLabelRefusal, match="identity 1"):
        H.build(v3=ewar_v3.load(), fwar_vintage_id="2000-01-01-000000000000", log=lambda *a, **k: None)


def _fwar_row(mid: int) -> dict:
    return {"seasons": {"2025": 1.5, "2026": 2.25, "1999": 0.4},
            "career_war": 4.15, "war_per_yr": 1.38, "war_seasons_count": 3, "source": "fwar",
            "seasons_ewar_v2": {"2025": 1.4, "2026": 2.0, "1999": 0.4},
            "fwar_coverage": {"vintage_id": "x", "mlbam": mid, "fallback_pre_years": [1999],
                              "fallback_post_years": [], "war_basis": "mixed"}}


def _a_departing_player(frozen) -> int:
    blk = frozen["seasons"]["2026"]
    return int(next(iter(blk["bat"] or blk["pit"])))


def test_label_series_equals_the_displayed_transform_at_the_freeze(frozen):
    mid = _a_departing_player(frozen)
    row = _fwar_row(mid)
    lab = H.label_series(row)
    shown = war_source.row_on_provider(row, "ewar_v3")["seasons"]
    assert lab == shown
    d = sum((H.departures(series="headline").get((mid, 2026)) or {}).values())
    assert lab["2026"] == round(2.25 + d, 2) and d != 0.0
    assert lab["2025"] == 1.5, "no headline departure before 2026"
    assert lab["1999"] == 0.4, "a season the vintage did not serve keeps its value"
    assert row["seasons"]["2026"] == 2.25, "the row is never mutated"
    v2 = {"seasons": {"2026": 1.0}, "source": "ewar_v2"}
    assert H.label_series(v2) == {"2026": 1.0}


def test_efv_label_seasons_follows_the_switch(frozen, monkeypatch):
    mid = _a_departing_player(frozen)
    row = _fwar_row(mid)
    monkeypatch.setattr(war_source, "EFV_LABEL_PROVIDER", "fwar")
    assert war_source.efv_label_seasons(row) == row["seasons"]
    import efv_dataset
    import efv_labels
    assert efv_dataset._label_seasons(row) == (row["seasons"], 0)
    assert efv_labels.provider() == "fwar"
    monkeypatch.setattr(war_source, "EFV_LABEL_PROVIDER", "ewar_headline")
    assert war_source.efv_label_seasons(row) == H.label_series(row)
    assert efv_dataset._label_seasons(row) == (H.label_series(row), 0)
    assert efv_dataset._label_provider() == "ewar_headline"
    # amendment 9.2: the development frames keep published fWAR (registered reads froze it)
    assert efv_labels.provider() == "fwar"


def test_fingerprint_label_term_follows_the_switch(frozen, monkeypatch):
    import storage
    monkeypatch.setattr(war_source, "EFV_LABEL_PROVIDER", "ewar_headline")
    assert f"|label=ewar_headline@{frozen['vintage_id']}|" in storage.board_basis_fingerprint()
    monkeypatch.setattr(war_source, "EFV_LABEL_PROVIDER", "fwar")
    assert "|label=fwar@" in storage.board_basis_fingerprint()


def test_label_vintage_is_off_the_webroot():
    text = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8")
    assert "\newar_headline_label.json\n" in text.replace("\r\n", "\n")
