# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""data/franchise_spine.json: the frozen B-Ref team_ID -> canonical org map.

SCOPED TO THE CLUB bWAR LINE ONLY. The 2000-2026 standings join by StatsAPI
team id, which is stable across the relocations (120 Expos / Nationals, 133
Athletics, 139 Devil Rays / Rays, 146 Marlins), so they need no spine; the HoF
franchises section needs a team column on the season frame and a frozen
multi-team attribution rule, which this spine does not supply. The tests pin
that every team_ID the war_daily frames carry since 1969 maps to exactly one
org, that no org's intervals overlap, and that the relocations are named.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
SPINE = ROOT / "data" / "franchise_spine.json"


@pytest.fixture(scope="module")
def spine():
    assert SPINE.exists(), "data/franchise_spine.json is a committed curation"
    return json.loads(SPINE.read_text(encoding="utf-8"))


def test_every_team_id_in_war_daily_since_1969_maps_to_one_canonical_org(spine):
    pd = pytest.importorskip("pandas")
    bat = ROOT / ".cache" / "war_daily" / "bat.parquet"
    pit = ROOT / ".cache" / "war_daily" / "pit.parquet"
    if not (bat.exists() and pit.exists()):
        pytest.skip("war_daily cache absent")
    first = spine["first_season"]
    seen = set()
    for p in (bat, pit):
        df = pd.read_parquet(p, columns=["year_ID", "team_ID"])
        df = df[df["year_ID"] >= first]
        seen |= set(zip(df["team_ID"].astype(str), df["year_ID"].astype(int)))
    lookup = {}
    for org, intervals in spine["orgs"].items():
        for iv in intervals:
            for s in range(iv["first"], iv["last"] + 1):
                assert (iv["team_id"], s) not in lookup, (iv["team_id"], s, org, lookup[(iv["team_id"], s)])
                lookup[(iv["team_id"], s)] = org
    unmapped = sorted({t for (t, s) in seen if (t, s) not in lookup})
    assert not unmapped, f"team_IDs since {first} with no org: {unmapped}"
    orgs = {v for v in lookup.values()}
    assert len(orgs) == 30 and len(spine["orgs"]) == 30
    from trades import canonical_org
    for org in spine["orgs"]:
        assert canonical_org(org) == org, org


def test_standings_join_by_team_id_and_need_no_spine(spine):
    from trades import canonical_org_from_id
    ids = {}
    for season in (2000, 2004, 2005, 2011, 2012, 2024, 2025, 2026):
        p = ROOT / ".cache" / f"statsapi_standings_{season}.json"
        if not p.exists():
            pytest.skip(f"standings cache {season} absent")
        raw = json.loads(p.read_text(encoding="utf-8"))
        for rec in raw["records"]:
            for tr in rec["teamRecords"]:
                tid = tr["team"]["id"]
                org = canonical_org_from_id(tid)
                assert org, (season, tid)
                assert ids.setdefault(tid, org) == org, "a StatsAPI id never changes org"
    assert len(ids) == 30
    assert ids[120] == "WSN" and ids[133] == "ATH" and ids[139] == "TBR" and ids[146] == "MIA"
    assert "standings" in " ".join(spine["not_in_scope"]).lower()
    assert "Hall of Fame" in " ".join(spine["not_in_scope"])


def test_spine_intervals_do_not_overlap_within_an_org(spine):
    for org, intervals in spine["orgs"].items():
        ivs = sorted(intervals, key=lambda iv: iv["first"])
        assert ivs and ivs[-1]["last"] == spine["last_season"], org
        for a, b in zip(ivs, ivs[1:]):
            assert a["last"] < b["first"], (org, a, b)
            assert a["last"] + 1 == b["first"], (org, "a gap in the line", a, b)
        for iv in ivs:
            assert iv["first"] >= spine["first_season"] and iv["first"] <= iv["last"], (org, iv)


def test_relocations_are_named(spine):
    moves = {(r["from"], r["to"]) for r in spine["relocations"]}
    for pair in (("OAK", "ATH"), ("MON", "WSN"), ("FLA", "MIA"), ("TBD", "TBR"), ("CAL", "ANA"), ("ANA", "LAA"),
                 ("SEP", "MIL"), ("WSA", "TEX")):
        assert pair in moves, pair
    for r in spine["relocations"]:
        assert r["note"] and r["kind"] in ("relocation", "rename")
        org = next(o for o, ivs in spine["orgs"].items() if any(iv["team_id"] == r["to"] for iv in ivs))
        assert any(iv["team_id"] == r["from"] for iv in spine["orgs"][org]), (r, org)
        assert any(iv["team_id"] == r["to"] and iv["first"] == r["season"] for iv in spine["orgs"][org]), r
    assert [iv["team_id"] for iv in spine["orgs"]["ATH"]] == ["OAK", "ATH"]
    assert spine["orgs"]["ATH"][0]["last"] == 2024 and spine["orgs"]["ATH"][1]["first"] == 2025
    assert [iv["team_id"] for iv in spine["orgs"]["LAA"]] == ["CAL", "ANA", "LAA"]
