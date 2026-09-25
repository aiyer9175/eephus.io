# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline unit tests for the AAA Statcast hitter sidecar
(statcast_aaa_hitters.py). Builds from the cached Savant minors batter
CSVs in .cache/savant_minors/ - no network - and pins the payload shape,
a known covered mlbam, the latest-season-wins rule, and the luck_gap
arithmetic."""

from __future__ import annotations

from pathlib import Path

import pytest

import statcast_aaa_hitters as sah

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache" / "savant_minors"

# Justyn-Henry Malloy: 611 PA in the committed batter_2023.csv cache, so he
# is covered in every rebuild regardless of which later seasons qualify.
KNOWN_MLBAM = "669234"

pytestmark = pytest.mark.skipif(
    not (CACHE / "batter_2023.csv").exists(),
    reason="savant minors batter cache absent (offline fixture)")

ROW_KEYS = {"xwoba", "woba", "xslg", "slg", "ev", "hardhit_percent",
            "barrels_per_bbe_percent", "whiff", "bat_speed", "luck_gap",
            "pa", "season"}


@pytest.fixture(scope="module")
def payload():
    return sah.build()


def test_payload_shape(payload):
    assert set(payload) == {"generated_at", "note", "source_fetched", "by_mlbam"}
    assert isinstance(payload["note"], str) and payload["note"]
    by = payload["by_mlbam"]
    assert len(by) > 500, "cached seasons should yield hundreds of hitters"
    for mid, row in by.items():
        assert mid.isdigit(), f"mlbam keys must be numeric strings: {mid!r}"
        assert set(row) == ROW_KEYS, f"{mid}: row keys drifted: {sorted(row)}"
        assert row["pa"] >= sah.MIN_PA
        assert row["season"] in sah.SEASONS


def test_known_covered_mlbam_appears(payload):
    row = payload["by_mlbam"].get(KNOWN_MLBAM)
    assert row is not None, f"{KNOWN_MLBAM} qualified in the 2023 cache"
    assert row["xwoba"] is not None and row["woba"] is not None
    assert row["ev"] is not None


def test_latest_qualified_season_wins(payload):
    """The emitted season for the known player must be the max cached
    season in which he has >= MIN_PA (recomputed from the CSVs here)."""
    import arkmetric_forward_eval as af
    qualified = []
    for season in sah.SEASONS:
        for r in af.savant_rows(season, "batter", fetch=False):
            try:
                mid, pa = int(float(r["player_id"])), float(r["pa"])
            except (KeyError, TypeError, ValueError):
                continue
            if str(mid) == KNOWN_MLBAM and pa >= sah.MIN_PA:
                qualified.append(season)
    assert qualified, "known mlbam vanished from the cache"
    assert payload["by_mlbam"][KNOWN_MLBAM]["season"] == max(qualified)


def test_luck_gap_arithmetic(payload):
    checked = 0
    for mid, row in payload["by_mlbam"].items():
        if row["xwoba"] is None or row["woba"] is None:
            assert row["luck_gap"] is None, mid
            continue
        assert row["luck_gap"] == round(row["xwoba"] - row["woba"], 3), mid
        checked += 1
    assert checked > 500, "luck_gap should be computable for nearly all rows"


def test_every_served_season_names_its_fetch_date(payload):
    """generated_at is the bake date. The card needs the date the season's
    CSV was fetched, or a June snapshot reads as the whole season."""
    import re
    fetched = payload["source_fetched"]
    for season in {row["season"] for row in payload["by_mlbam"].values()}:
        d = fetched.get(str(season))
        assert d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d), (season, d)
        assert int(d[:4]) >= season, (season, d)


def test_source_fetched_reads_the_file_time(tmp_path):
    import os
    p = tmp_path / "batter_2026.csv"
    p.write_text("x", encoding="utf-8")
    ts = 1782163845  # 2026-06-22T21:30:45Z
    os.utime(p, (ts, ts))
    assert sah.source_fetched((2025, 2026), tmp_path) == {"2026": "2026-06-22"}


def test_the_served_card_prints_the_fetch_date_on_a_partial_season():
    """The PROSPX panel reads source_fetched and prints the date when the
    CSV was fetched inside the season it covers."""
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    start = html.index("// ===== AAA Statcast hitter sidecar")
    block = html[start:html.index("// ===== A-ball Statcast signal pill", start)]
    assert "source_fetched" in block
    assert "_aaaFetchedSuffix" in block
