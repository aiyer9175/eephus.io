# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline unit tests for the Statcast (tracked parks) hitter sidecar
(statcast_aaa_hitters.py; the file keeps its old name, the card does not). Builds from the cached Savant minors batter
CSVs in .cache/savant_minors/ - no network - and pins the payload shape,
a known covered mlbam, the latest-season-wins rule, and the luck_gap
arithmetic. The monthly refresh tests (step 6b2a, owner answer M25-3) redirect
the live cache and the sidecar to tmp_path and fetch through a fake getter, so
they never touch the network, the served sidecar or the model cache."""

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
            "pa", "season", "levels"}


@pytest.fixture(scope="module")
def payload():
    return sah.build()


def test_payload_shape(payload):
    assert set(payload) == {"generated_at", "note", "source", "source_fetched",
                            "source_through", "by_mlbam"}
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
    qualified = []
    for season in sah.SEASONS:
        for r in sah.season_rows(season)[0]:     # the same cache build() reads
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


def _card_block() -> str:
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    start = html.index("// ===== Statcast (tracked parks) hitter sidecar")
    return html[start:html.index("// ===== A-ball Statcast signal pill", start)]


def test_the_card_is_titled_tracked_parks_and_names_the_level():
    """Owner answer M25AAA-2 (2026-10-01): the Savant minors rows cover every
    tracked park (every AAA park and the Florida State League), so the card
    keeps every row and is titled "Statcast (tracked parks)", never "AAA
    Statcast", and prints each row's level(s) beside the season."""
    block = _card_block()
    assert '>Statcast (tracked parks)</div>' in block
    assert "AAA Statcast" not in block
    assert "at AAA" not in block and "AAA tracked parks" not in block
    assert "r.levels" in block and "_aaaLevelLabel" in block
    assert "_aaaProvenance(r.season, r.levels)" in block
    # keep and relabel: no AAA-only filter on the client either
    assert 'levels.includes("AAA")' not in block and 'indexOf("AAA")' not in block


def test_the_level_rule_is_aaa_anywhere_and_a_in_the_fsl_only(monkeypatch):
    import milb_history as mh
    lines = {1: [{"level": "AAA", "league": "PCL", "pa": 300},
                 {"level": "A", "league": "FSL", "pa": 40},
                 {"level": "AA", "league": "EAS", "pa": 120},
                 {"level": "A+", "league": "SAL", "pa": 90},
                 {"level": "MLB", "league": "AL", "pa": 30}],
             2: [{"level": "A", "league": "CAL", "pa": 200},
                 {"level": "CPX", "league": "FCL", "pa": 20},
                 {"level": "A", "league": "FSL", "pa": 0}],
             3: [{"level": "A+", "league": "MID", "pa": 250},
                 {"level": "A", "league": "FSL", "pa": 180}]}
    monkeypatch.setattr(mh, "player_index", lambda season, group, fetch=True: lines)
    assert sah.tracked_levels(1, 2026) == ["AAA", "A"]
    assert sah.tracked_levels(2, 2026) == []
    assert sah.tracked_levels(3, 2026) == ["A"]
    assert sah.tracked_levels(4, 2026) == []


def test_every_row_names_its_level_and_the_pa_reconciles(payload):
    """The docstring's PARKS claim, recomputed: the Savant PA of a row equals
    the PA of its tracked season lines (AAA plus FSL) for nearly every row,
    every row names a level, and the rows with no AAA line are kept."""
    import milb_history as mh
    if not mh.player_index(2026, "hitting", fetch=False):
        pytest.skip("milb_history 2026 hitting cache absent")
    by = payload["by_mlbam"]
    exact = 0
    for mid, row in by.items():
        assert row["levels"], f"{mid}: no tracked season line in {row['season']}"
        pa = sum(int(sah._f(r.get("pa")) or 0)
                 for r in sah.tracked_lines(int(mid), row["season"]))
        exact += pa == row["pa"]
    assert exact / len(by) >= 0.99, (exact, len(by))
    assert sum(r["levels"] == ["A"] for r in by.values()) > 100


def test_the_served_card_prints_the_fetch_date_on_a_partial_season():
    """The PROSPX panel reads source_through (the data-through date) and
    source_fetched, prints the date on a season fetched inside its own year,
    and carries the source as hover provenance."""
    block = _card_block()
    assert "source_fetched" in block
    assert "source_through" in block
    assert "_aaaFetchedSuffix" in block
    assert "_aaaProvenance" in block
    assert "through ${" in block


# ---------------------------------------------------------------------------
# The monthly refresh (run_monthly step 6b2a)
# ---------------------------------------------------------------------------
import json  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402

CAL_2026 = {"start": "2026-03-27", "end": "2026-09-20"}
_HEAD = ("player_id,player_name,pa,xwoba,woba,xslg,slg,launch_speed,"
         "hardhit_percent,barrels_per_bbe_percent,swing_miss_percent,bat_speed")


def _csv(n: int, xwoba: float = 0.330) -> bytes:
    rows = [_HEAD] + [f"{900000 + i},Player {i},{150 + i},{xwoba},0.320,0.420,"
                      f"0.400,89.5,40.0,8.0,25.0," for i in range(n)]
    return ("\n".join(rows) + "\n").encode("utf-8")


def _raise(url, timeout=0):
    raise OSError("timeout")


def _no_network(url, timeout=0):
    raise AssertionError(f"unexpected fetch: {url}")


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """Redirect both outputs (the live cache and the sidecar) to tmp_path and
    seed a fresh AAA 2026 calendar so no test reaches StatsAPI."""
    d = tmp_path / "savant_minors_live"
    d.mkdir()
    monkeypatch.setattr(sah, "LIVE_DIR", d)
    monkeypatch.setattr(sah, "OUT_PATH", tmp_path / "statcast_aaa_hitters.json")
    (d / "aaa_season_2026.json").write_text(json.dumps({"seasons": [{
        "seasonId": "2026", "regularSeasonStartDate": CAL_2026["start"],
        "regularSeasonEndDate": CAL_2026["end"]}]}), encoding="utf-8")
    return d


def test_the_phase_is_registered_with_the_monthly_savant_phases():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index('_step("6b2a. Savant minors batter refresh, tracked parks '
                  '(statcast_aaa_hitters.json)"')
    assert src.index('_step("6b2. Swing+ scoring') < i < src.index('_step("6b2b. AAA Stuff+')
    body = src[i:src.index('_step("6b2b. AAA Stuff+', i)]
    assert "from statcast_aaa_hitters import refresh" in body
    assert body.count('_record_ingest("savant_aaa_batters"') == 2
    import run_monthly
    assert "savant_aaa_batters" in run_monthly.SCHEDULED_EXPORTS


def test_the_gate_is_the_regular_season_plus_one_final_pull():
    old = {"fetched_ts": datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp(),
           "through": "2026-05-31"}
    now = datetime(2026, 7, 1, 12, tzinfo=timezone.utc).timestamp()
    cal_2027 = {"start": "2027-03-26", "end": "2027-09-19"}
    assert sah.phase_decision(date(2027, 1, 1), cal_2027, {})[0] is False
    assert sah.phase_decision(date(2026, 7, 1), CAL_2026, {}, now)[0] is True
    assert sah.phase_decision(date(2026, 7, 1), CAL_2026, old, now)[0] is True
    fresh = dict(old, fetched_ts=now - 86400)
    assert sah.phase_decision(date(2026, 7, 1), CAL_2026, fresh, now)[0] is False
    # after the season: one more pull unless the copy already covers the end
    assert sah.phase_decision(date(2026, 10, 1), CAL_2026, old)[0] is True
    done = dict(old, through="2026-09-20")
    assert sah.phase_decision(date(2026, 10, 1), CAL_2026, done)[0] is False
    assert sah.phase_decision(date(2026, 11, 1), CAL_2026, done)[0] is False


def test_data_through_is_the_day_before_the_fetch_capped_at_the_season_end():
    assert sah.data_through(datetime(2026, 6, 23, 1, 30, tzinfo=timezone.utc),
                            CAL_2026) == "2026-06-21"
    assert sah.data_through(datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
                            CAL_2026) == "2026-09-20"
    assert sah.data_through(datetime(2026, 3, 20, 12, tzinfo=timezone.utc),
                            CAL_2026) is None


def test_a_good_fetch_lands_in_the_live_cache_only(live):
    import arkmetric_forward_eval as af
    model = af.CACHE_DIR / "batter_2026.csv"
    before = (model.stat().st_mtime, model.read_bytes()) if model.exists() else None
    res = sah.fetch_live(2026, CAL_2026, getter=lambda url, t=0: _csv(600),
                         now=datetime(2026, 10, 1, 9, tzinfo=timezone.utc))
    assert res["ok"] and res["rows"] == 600 and res["through"] == "2026-09-20"
    meta = sah.read_live_meta(2026)
    assert meta["fetched"] == "2026-10-01" and meta["through"] == "2026-09-20"
    assert "hfSea=2026" in meta["url"] and "minors=true" in meta["url"]
    after = (model.stat().st_mtime, model.read_bytes()) if model.exists() else None
    assert after == before, "the refresh must never write the model cache"
    payload = sah.build()
    assert payload["source_through"] == {"2026": "2026-09-20"}
    assert payload["source_fetched"]["2026"] == "2026-10-01"
    assert payload["by_mlbam"]["900000"]["season"] == 2026


@pytest.mark.parametrize("getter", [
    pytest.param(_raise, id="network"),
    pytest.param(lambda url, t=0: b"<html>Service Unavailable</html>", id="html"),
    pytest.param(lambda url, t=0: b"player_id,pa\n1,200\n", id="columns"),
    pytest.param(lambda url, t=0: _csv(100), id="shrunk"),
])
def test_a_failed_fetch_keeps_the_last_good_file(live, getter):
    sah.fetch_live(2026, CAL_2026, getter=lambda url, t=0: _csv(600),
                   now=datetime(2026, 6, 1, 12, tzinfo=timezone.utc))
    path, meta_path = sah.live_path(2026), sah.live_meta_path(2026)
    good, good_meta = path.read_bytes(), meta_path.read_bytes()
    res = sah.refresh(date(2026, 7, 15), getter=getter, persist=True)
    assert res["ok"] is False and res["fetched"] is False
    assert path.read_bytes() == good and meta_path.read_bytes() == good_meta
    # the sidecar is still baked, from the last good file
    out = json.loads(sah.OUT_PATH.read_text(encoding="utf-8"))
    assert out["source_through"] == {"2026": "2026-05-31"}
    assert out["by_mlbam"]["900000"]["season"] == 2026


def test_an_off_season_run_fetches_nothing(live):
    sah.fetch_live(2026, CAL_2026, getter=lambda url, t=0: _csv(600),
                   now=datetime(2026, 9, 25, 12, tzinfo=timezone.utc))
    res = sah.refresh(date(2026, 11, 1), getter=_no_network, persist=False)
    assert res["ok"] is True and res["fetched"] is False
    assert "final pull done" in res["message"]
