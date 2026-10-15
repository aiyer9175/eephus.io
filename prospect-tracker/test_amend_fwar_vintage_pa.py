# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one-time plate-appearance amendment of the frozen fWAR vintage
(EWAR_P0_VINTAGE_PA, owner answer EW3-19). Offline: fixtures only, every write
goes to tmp_path, and the only fetches are a fake fetcher's."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

import fwar_vintage as FV

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import amend_fwar_vintage_pa as AM  # noqa: E402


def _body(splits) -> bytes:
    return json.dumps({"copyright": "x", "stats": [{"splits": splits}]}).encode("utf-8")


def _hit_block(ids):
    fields = list(FV.HITTING_FIELDS)
    rows = {}
    for k, pid in enumerate(ids):
        vals = [None] * len(fields)
        vals[fields.index("war")] = round(0.5 * k, 2)
        vals[fields.index("batting")] = 1.5 * k
        vals[fields.index("numTeams")] = 1
        rows[str(pid)] = vals
    block = {"group": "hitting", "status": "frozen", "url": "u", "fetched_at": "2026-10-02T23:00:00+00:00",
             "http_status": 200, "raw_sha256": "0" * 64, "n_rows": len(ids), "n_players": len(ids),
             "n_multi_team": 0, "ambiguous_ids": [], "n_string_refused": 0, "fields": fields,
             "rows": rows}
    block["content_sha256"] = FV.group_content_sha(block)
    return block


def _pit_block(ids):
    fields = list(FV.PITCHING_FIELDS)
    rows = {str(p): [1.0] + [None] * (len(fields) - 1) for p in ids}
    block = {"group": "pitching", "status": "frozen", "url": "u", "fetched_at": "2026-10-02T23:00:01+00:00",
             "http_status": 200, "raw_sha256": "1" * 64, "n_rows": len(ids), "n_players": len(ids),
             "n_multi_team": 0, "ambiguous_ids": [], "n_string_refused": 0, "fields": fields,
             "rows": rows}
    block["content_sha256"] = FV.group_content_sha(block)
    return block


def _old_vintage():
    blob = FV.empty_vintage()
    for s in (2025, 2026):
        sb = {"hitting": _hit_block([1, 2, 3]), "pitching": _pit_block([10, 11])}
        sb["fetched_at"] = "2026-10-02T23:00:01+00:00"
        sb["basis"] = FV.season_basis(sb)
        sb["content_sha256"] = FV.season_content_sha(sb)
        blob["seasons"][str(s)] = sb
    blob["vintage_id"] = FV.vintage_id(blob)
    return blob


PA = {1: 600, 2: 250, 3: 0}


class Fake:
    def __init__(self, team_total=None):
        self.calls = []
        self.team_total = team_total

    def __call__(self, url):
        self.calls.append(url)
        if "teams/stats" in url:
            tot = sum(PA.values()) if self.team_total is None else self.team_total
            teams = [{"team": {"id": 100 + k}, "stat": {"plateAppearances": tot // 30 + (k < tot % 30)}}
                     for k in range(30)]
            return FV.FetchResponse(200, _body(teams))
        lines = [{"player": {"id": p}, "numTeams": 1, "stat": {"plateAppearances": v}}
                 for p, v in PA.items()]
        return FV.FetchResponse(200, _body(lines))


def _amend(tmp_path, fake=None):
    old = _old_vintage()
    seasons = AM.hitting_seasons(old)
    fake = fake or Fake()
    AM.fetch_sources(seasons, tmp_path, fetch=fake, now=lambda: "2026-10-15T23:00:00+00:00",
                     pause=lambda s: None)
    new = AM.amend(old, AM.load_sources(seasons, tmp_path), date="2026-10-15",
                   previous_file_sha256="f" * 64)
    return old, new, fake


def test_the_amendment_fills_pa_and_holds_every_invariant(tmp_path):
    old, new, fake = _amend(tmp_path)
    assert AM.check(old, new) == []
    assert new["vintage_id"] != old["vintage_id"]
    assert new["vintage_id"][:10] == old["vintage_id"][:10]       # the freeze date is kept
    i = FV.HITTING_FIELDS.index("plateAppearances")
    assert {int(m): v[i] for m, v in new["seasons"]["2025"]["hitting"]["rows"].items()} == PA
    assert new["seasons"]["2025"]["pitching"] == old["seasons"]["2025"]["pitching"]
    am = new["amendments"][-1]
    assert am["previous_vintage_id"] == old["vintage_id"] and am["vintage_id"] == new["vintage_id"]
    assert am["war_identical"] is True and am["seasons"] == [2025, 2026]
    assert FV.war_lineage(new) == [new["vintage_id"], old["vintage_id"]]
    # only StatsAPI season lines and team totals were called, never the sabermetrics feed
    assert len(fake.calls) == 4 and not any("sabermetrics" in u for u in fake.calls)


def test_the_fetch_keeps_the_bodies_and_never_refetches(tmp_path):
    _, _, fake = _amend(tmp_path)
    man = json.loads((tmp_path / AM.MANIFEST).read_text(encoding="utf-8"))
    assert sorted(man) == ["lines_2025", "lines_2026", "teams_2025", "teams_2026"]
    again = Fake()
    AM.fetch_sources([2025, 2026], tmp_path, fetch=again, pause=lambda s: None)
    assert again.calls == []
    (tmp_path / "lines_2025.json").write_bytes(b'{"stats": []}')
    with pytest.raises(AM.AmendError, match="does not match its manifest"):
        AM.load_sources([2025], tmp_path)


def test_it_runs_once(tmp_path):
    _, new, _ = _amend(tmp_path)
    with pytest.raises(AM.AmendError, match="runs once"):
        AM.amend(new, AM.load_sources([2025, 2026], tmp_path), date="2026-10-16",
                 previous_file_sha256=None)


def test_a_league_total_mismatch_refuses_the_write(tmp_path):
    old, new, _ = _amend(tmp_path, Fake(team_total=sum(PA.values()) + 1))
    assert any("disagree" in p for p in AM.check(old, new))


def test_a_moved_published_value_refuses_the_write(tmp_path):
    old, new, _ = _amend(tmp_path)
    bad = copy.deepcopy(new)
    bad["seasons"]["2026"]["hitting"]["rows"]["2"][0] = 9.9           # a war value
    probs = AM.check(old, bad)
    assert any("rows moved outside plateAppearances" in p for p in probs)
    assert any("side_targets(bat) moved" in p for p in probs)
    bad = copy.deepcopy(new)
    bad["seasons"]["2026"]["pitching"]["rows"]["10"][0] = 0.0
    assert any("pitching block moved" in p for p in AM.check(old, bad))


def test_a_required_season_left_without_pa_refuses_the_write(tmp_path):
    old = _old_vintage()
    blank = Fake()
    PA_SAVED = dict(PA)
    try:
        PA.pop(3)
        AM.fetch_sources([2025, 2026], tmp_path, fetch=blank, pause=lambda s: None)
    finally:
        PA.clear()
        PA.update(PA_SAVED)
    new = AM.amend(old, AM.load_sources([2025, 2026], tmp_path), date="2026-10-15",
                   previous_file_sha256=None)
    assert any("1 rows still without PA" in p for p in AM.check(old, new))


def test_the_cli_plans_without_writing(tmp_path, capsys):
    vp = tmp_path / "v.json"
    FV.write(_old_vintage(), vp)
    before = vp.read_bytes()
    cache = tmp_path / "c"
    AM.fetch_sources([2025, 2026], cache, fetch=Fake(), pause=lambda s: None)
    assert AM.main(["--vintage", str(vp), "--cache-dir", str(cache)]) == 0
    out = capsys.readouterr().out
    assert "all invariants hold" in out and "PLAN ONLY" in out
    assert vp.read_bytes() == before
    assert AM.main(["--vintage", str(vp), "--cache-dir", str(cache), "--write"]) == 0
    assert FV.load(vp)["amendments"][-1]["task"] == AM.TASK
    assert AM.main(["--vintage", str(vp), "--cache-dir", str(cache)]) == 2
