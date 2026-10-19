# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one-time innings amendment of the frozen fWAR vintage (EWAR_P0B_VINTAGE_IP,
the EW3-19 precedent). Offline: fixtures only, every write goes to tmp_path, and
the only fetches are a fake fetcher's."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

import fwar_vintage as FV

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import amend_fwar_vintage_ip as AM  # noqa: E402

OLD_PIT_FIELDS = [f for f in FV.PITCHING_FIELDS if f not in FV.IP_FIELDS]


def _body(splits) -> bytes:
    return json.dumps({"copyright": "x", "stats": [{"splits": splits}]}).encode("utf-8")


def _hit_block(ids):
    fields = list(FV.HITTING_FIELDS)
    rows = {}
    for k, pid in enumerate(ids):
        vals = [None] * len(fields)
        vals[fields.index("war")] = round(0.5 * k, 2)
        vals[fields.index("plateAppearances")] = 100 * k
        vals[fields.index("numTeams")] = 1
        rows[str(pid)] = vals
    block = {"group": "hitting", "status": "frozen", "url": "u", "fetched_at": "2026-10-02T23:00:00+00:00",
             "http_status": 200, "raw_sha256": "0" * 64, "n_rows": len(ids), "n_players": len(ids),
             "n_multi_team": 0, "ambiguous_ids": [], "n_string_refused": 0, "fields": fields,
             "rows": rows, "pa_join": {"field": "plateAppearances"}}
    block["content_sha256"] = FV.group_content_sha(block)
    return block


def _pit_block(ids):
    fields = list(OLD_PIT_FIELDS)
    rows = {}
    for k, pid in enumerate(ids):
        vals = [None] * len(fields)
        vals[fields.index("war")] = 1.0 + k
        vals[fields.index("gmli")] = 0.9
        vals[fields.index("numTeams")] = 1
        rows[str(pid)] = vals
    block = {"group": "pitching", "status": "frozen", "url": "u", "fetched_at": "2026-10-02T23:00:01+00:00",
             "http_status": 200, "raw_sha256": "1" * 64, "n_rows": len(ids), "n_players": len(ids),
             "n_multi_team": 0, "ambiguous_ids": [], "n_string_refused": 0, "fields": fields,
             "rows": rows}
    block["content_sha256"] = FV.group_content_sha(block)
    return block


def _old_vintage():
    blob = FV.empty_vintage()
    blob["fields"]["pitching"] = list(OLD_PIT_FIELDS)
    for s in (2025, 2026):
        sb = {"hitting": _hit_block([1, 2, 3]), "pitching": _pit_block([10, 11])}
        sb["fetched_at"] = "2026-10-02T23:00:01+00:00"
        sb["basis"] = FV.season_basis(sb)
        sb["content_sha256"] = FV.season_content_sha(sb)
        blob["seasons"][str(s)] = sb
    blob["vintage_id"] = FV.vintage_id(blob)
    blob["amendments"] = [{"task": "EWAR_P0_VINTAGE_PA", "previous_vintage_id": "pre-pa",
                           "vintage_id": blob["vintage_id"], "war_identical": True}]
    return blob


IP = {10: (541, 33, 32), 11: (190, 60, 0)}     # outs, games, starts


class Fake:
    def __init__(self, team_outs=None):
        self.calls = []
        self.team_outs = team_outs

    def __call__(self, url):
        self.calls.append(url)
        if "teams/stats" in url:
            outs = sum(v[0] for v in IP.values()) if self.team_outs is None else self.team_outs
            gs = sum(v[2] for v in IP.values())
            teams = [{"team": {"id": 100 + k},
                      "stat": {"outs": outs // 30 + (k < outs % 30), "gamesStarted": gs // 30 + (k < gs % 30)}}
                     for k in range(30)]
            return FV.FetchResponse(200, _body(teams))
        lines = [{"player": {"id": p}, "numTeams": 1,
                  "stat": {"outs": o, "inningsPitched": f"{o // 3}.{o % 3}", "gamesPitched": g,
                           "gamesStarted": gs}} for p, (o, g, gs) in IP.items()]
        return FV.FetchResponse(200, _body(lines))


def _amend(tmp_path, fake=None):
    old = _old_vintage()
    seasons = AM.pitching_seasons(old)
    fake = fake or Fake()
    AM.fetch_sources(seasons, tmp_path, fetch=fake, now=lambda: "2026-10-19T20:00:00+00:00",
                     pause=lambda s: None)
    new = AM.amend(old, AM.load_sources(seasons, tmp_path), date="2026-10-19",
                   previous_file_sha256="f" * 64)
    return old, new, fake


def test_the_amendment_appends_innings_and_holds_every_invariant(tmp_path):
    old, new, fake = _amend(tmp_path)
    assert AM.check(old, new) == []
    assert new["vintage_id"] != old["vintage_id"]
    assert new["vintage_id"][:10] == old["vintage_id"][:10]       # the freeze date is kept
    pit = new["seasons"]["2025"]["pitching"]
    assert pit["fields"] == OLD_PIT_FIELDS + list(FV.IP_FIELDS)
    assert new["fields"]["pitching"] == pit["fields"]
    row = dict(zip(pit["fields"], pit["rows"]["10"]))
    assert row["outs"] == 541 and row["inningsPitched"] == 541 / 3.0
    assert row["gamesPitched"] == 33 and row["gamesStarted"] == 32 and row["war"] == 1.0
    assert new["seasons"]["2025"]["hitting"] == old["seasons"]["2025"]["hitting"]
    am = new["amendments"][-1]
    assert am["task"] == AM.TASK and am["war_identical"] is True and am["seasons"] == [2025, 2026]
    assert am["previous_vintage_id"] == old["vintage_id"] and am["vintage_id"] == new["vintage_id"]
    assert am["league_ip"]["2025"]["outs_teams"] == 731 and am["league_ip"]["2025"]["gs_teams"] == 32
    assert FV.war_lineage(new) == [new["vintage_id"], old["vintage_id"], "pre-pa"]
    # only StatsAPI season lines and team totals were called, never the sabermetrics feed
    assert len(fake.calls) == 4 and not any("sabermetrics" in u for u in fake.calls)
    assert all("group=pitching" in u for u in fake.calls)


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
        AM.amend(new, AM.load_sources([2025, 2026], tmp_path), date="2026-10-20",
                 previous_file_sha256=None)


def test_a_league_total_mismatch_refuses_the_write(tmp_path):
    old, new, _ = _amend(tmp_path, Fake(team_outs=732))
    assert any("disagree" in p for p in AM.check(old, new))


def test_a_moved_published_value_refuses_the_write(tmp_path):
    old, new, _ = _amend(tmp_path)
    bad = copy.deepcopy(new)
    bad["seasons"]["2026"]["pitching"]["rows"]["11"][0] = 9.9           # a war value
    probs = AM.check(old, bad)
    assert any("rows moved outside IP_FIELDS" in p for p in probs)
    assert any("side_targets(pit) moved" in p for p in probs)
    bad = copy.deepcopy(new)
    bad["seasons"]["2026"]["hitting"]["rows"]["2"][0] = 0.0
    assert any("hitting block moved" in p for p in AM.check(old, bad))
    bad = copy.deepcopy(new)
    k = bad["seasons"]["2026"]["pitching"]["fields"].index("inningsPitched")
    bad["seasons"]["2026"]["pitching"]["rows"]["10"][k] = 180.1             # baseball notation
    assert any("not outs / 3" in p for p in AM.check(old, bad))


def test_a_row_left_without_innings_refuses_the_write(tmp_path):
    old = _old_vintage()
    saved = dict(IP)
    try:
        IP.pop(11)
        AM.fetch_sources([2025, 2026], tmp_path, fetch=Fake(), pause=lambda s: None)
    finally:
        IP.clear()
        IP.update(saved)
    new = AM.amend(old, AM.load_sources([2025, 2026], tmp_path), date="2026-10-19",
                   previous_file_sha256=None)
    assert any("1 rows still without innings" in p for p in AM.check(old, new))


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
