# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the CollegeSavant per-year payload split (2026-07-17).

The two pages used to eagerly ship every season's pitch rows and batted-ball
points (~2.5MB gz combined per cold visit), 83%+ of it 2024 data nobody sees
at boot. The heavy tables now ride in per-year vendor files that the apps
lazy-inject on first use (pitcher_app.js ensurePitchData / app.js
ensureHitterBip, the same injector pattern as ensurePitchShapes). These pins
hold the split in place:

  - the HTML ships no per-year table and no /data/ sidecar at boot (QREP01,
    surface-quality audit 2026-10-02: the current-season tables and the 2.1 MB
    translation sidecar held the first home row back 2.4 to 3.7 s at 10 Mbps;
    every one is injected by the view that reads it),
  - the slimmed monolith files no longer carry the moved globals,
  - each per-year file carries exactly its own season (a regenerated payload
    that mixes seasons would silently double-ship), and
  - the dead legacy B1G_BIP blob stays deleted (922KB, unreachable on the
    happy path; its consumer now degrades to an empty scatter by design).

The Python reader college_translation.py reads only the FIRST array in
hitter_year_data.js / pitcher_data.js (window.HITTER_DATA / window.
PITCHER_DATA via _first_array), which the split must keep in first position.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CS = Path(__file__).parent / "collegesavant"

_SCRIPT_SRC = re.compile(r'<script\s+src="([^"?]+)')

PITCH_YEARS = (2024, 2025, 2026)
BIP_YEARS = (2024, 2025)


def _script_srcs(page: str) -> list[str]:
    return _SCRIPT_SRC.findall((CS / page).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Page structure: what ships eagerly
# --------------------------------------------------------------------------- #
SIDECARS = ("/data/collegesavant_translation.js", "/data/collegesavant_draft_prospects.js")


def test_hitter_page_ships_no_batted_balls_or_sidecars_at_boot():
    srcs = _script_srcs("index.html")
    assert "data.js" in srcs
    # HITTER_DATA (all years) stays eager: the leaderboard and the global
    # search index every year of it.
    assert "hitter_year_data.js" in srcs
    for year in BIP_YEARS:
        assert f"hitter_bip_{year}.js" not in srcs, f"hitter_bip_{year}.js is injected by ensureHitterBip"
    for side in SIDECARS:
        assert side not in srcs, f"{side} is injected by ensurePayload on the views that read it"
    assert "pitcher_data.js" not in srcs, "pitcher payload is search-lazy on the hitter page"


def test_pitcher_page_ships_no_pitch_tables_or_sidecars_at_boot():
    srcs = _script_srcs("pitcher_index.html")
    assert "data.js" in srcs
    # PITCHER_DATA (all years) stays eager: leaderboard + global search.
    assert "pitcher_data.js" in srcs
    for year in PITCH_YEARS:
        assert f"pitcher_pitch_data_{year}.js" not in srcs, f"pitcher_pitch_data_{year}.js is injected by ensurePitchData"
    for side in SIDECARS:
        assert side not in srcs, f"{side} is injected by ensurePayload on the views that read it"
    assert "hitter_year_data.js" not in srcs, "hitter payload is search-lazy on the pitcher page"
    for shape in ("pitch_shape_data_2024.js", "pitch_shape_data_2025.js"):
        assert shape not in srcs, f"{shape} is injected by ensurePitchShapes, never eager"


def test_apps_wire_the_lazy_injectors():
    pitcher_app = (CS / "pitcher_app.js").read_text(encoding="utf-8")
    assert "pitcher_pitch_data_${year}.js" in pitcher_app
    assert "function ensurePitchData" in pitcher_app
    hitter_app = (CS / "app.js").read_text(encoding="utf-8")
    assert "hitter_bip_${year}.js" in hitter_app
    assert "function ensureHitterBip" in hitter_app
    # The boot path no longer fetches a season: setActiveYear only filters, and
    # the profile views ask for their own tables.
    for src, inj in ((hitter_app, "ensureHitterBip(state.year)"), (pitcher_app, "ensurePitchData(state.year)")):
        set_year = src.split("function setActiveYear(")[1].split("\n}\n")[0]
        assert inj not in set_year
    assert "ensurePitchData(pitcher.year)" in pitcher_app.split("function renderPitcher(")[1].split("\n}\n")[0]
    for src in (hitter_app, pitcher_app):
        assert "function ensurePayload(name, global)" in src
        assert "/data/${name}.js${ver ? `?v=${ver}` : \"\"}" in src
        assert "window.CS_PAYLOAD_VER" in src
        proj = src.split("function renderProjections()")[1].split("\n}\n")[0]
        assert "if (!ensureTranslation())" in proj
        assert "ensureDraftProspects()" in src.split("function renderProspects()")[1].split("\n}\n")[0]


# --------------------------------------------------------------------------- #
# Data invariants: the slimmed monoliths and the per-year files
# --------------------------------------------------------------------------- #
def test_slimmed_monoliths_keep_first_arrays_and_drop_moved_globals():
    data = (CS / "data.js").read_text(encoding="utf-8")
    assert "window.B1G_CSV" in data and "window.B1G_TEAMS" in data
    assert "window.B1G_BIP" not in data, "the dead legacy blob must stay deleted"

    hitter = (CS / "hitter_year_data.js").read_text(encoding="utf-8")
    assert hitter.startswith("window.HITTER_DATA = ["), \
        "college_translation._first_array reads HITTER_DATA first"
    assert "window.HITTER_BIP" not in hitter

    pitcher = (CS / "pitcher_data.js").read_text(encoding="utf-8")
    assert pitcher.startswith("window.PITCHER_DATA = ["), \
        "college_translation._first_array reads PITCHER_DATA first"
    assert "window.PITCHER_PITCH_DATA" not in pitcher


def test_hitter_app_fallback_no_longer_reads_b1g_bip():
    # A comment may still NAME the removed blob; no code may READ it.
    app = (CS / "app.js").read_text(encoding="utf-8")
    assert "window.B1G_BIP" not in app, "CSV fallback degrades to an empty scatter now"
    assert "normalizeBattedBalls({})" in app


@pytest.mark.parametrize("year", PITCH_YEARS)
def test_pitch_year_file_carries_exactly_its_season(year):
    path = CS / f"pitcher_pitch_data_{year}.js"
    text = path.read_text(encoding="utf-8")
    prefix = f"window.PITCHER_PITCH_DATA_{year} = "
    assert text.startswith(prefix)
    rows = json.loads(text[len(prefix):].rstrip().rstrip(";"))
    assert rows, f"{path.name} is empty"
    bad = {r.get("year") for r in rows} - {year}
    assert not bad, f"{path.name} carries stray seasons: {sorted(bad)}"


@pytest.mark.parametrize("year", BIP_YEARS)
def test_bip_year_file_carries_exactly_its_season(year):
    path = CS / f"hitter_bip_{year}.js"
    text = path.read_text(encoding="utf-8")
    prefix = f"window.HITTER_BIP_{year} = "
    assert text.startswith(prefix)
    table = json.loads(text[len(prefix):].rstrip().rstrip(";"))
    assert table, f"{path.name} is empty"
    bad = [k for k in table if not k.startswith(f"{year}:")]
    assert not bad, f"{path.name} carries stray keys, e.g. {bad[:3]}"
