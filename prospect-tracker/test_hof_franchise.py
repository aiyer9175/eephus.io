# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Hall of Fame franchise credit (owner answer 2026-09-25, final-pass batch 6).

THE RULE, frozen: an inductee is credited to the franchise with which he
accumulated the most bWAR, summed over every war_daily stint. The map is
data/franchise_spine.json, carried back to 1871 by tools/franchise_spine_history.py
with every season before 1969 on one of the 30 franchises or on a named defunct
club. docs/HOF_FRANCHISE_ATTRIBUTION.md holds the rule and what it rejected.

WHAT THESE TESTS PIN, each because it is easy to get quietly wrong:
  1. every war_daily stint from 1871 lands on exactly one franchise or defunct
     club, never on a default;
  2. every inductee maps to exactly one primary franchise, in the frame and on
     the served page;
  3. the WAR credited to a player's franchises sums to his career WAR;
  4. the four Negro Leagues inductees bridged in 9bd4930a (Josh Gibson, Oscar
     Charleston, Cool Papa Bell, Ray Brown) resolve to their clubs;
  5. the tie-break never depends on row order.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "hof_board.json"
SPINE = ROOT / "data" / "franchise_spine.json"
DOC = ROOT / "docs" / "HOF_FRANCHISE_ATTRIBUTION.md"

BRIDGED = {"gibsojo99": "DEF-HG-1929", "charlos99": "DEF-HBG-1924",
           "bellco99": "DEF-SLS-1922", "brownra99": "DEF-HG-1929"}


def _frames_present() -> bool:
    return all((ROOT / ".cache" / "war_daily" / f).exists() for f in ("bat.parquet", "pit.parquet"))


@pytest.fixture(scope="module")
def hd():
    if not _frames_present():
        pytest.skip("war_daily cache absent")
    import hof_data
    return hof_data


@pytest.fixture(scope="module")
def credit(hd):
    return hd.franchise_credit(offline=True)


@pytest.fixture(scope="module")
def served():
    if not ART.exists():
        pytest.skip("run python hof_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))["sections"]["franchises"]


# --------------------------------------------------------------------------
# 1. The map
# --------------------------------------------------------------------------

def test_every_war_daily_stint_since_1871_maps_to_one_franchise_or_defunct_club(hd):
    """Null-WAR stints included: the map has to place every row, not only the
    ones that carry WAR today."""
    import pandas as pd
    fmap = hd.franchise_map()
    assert not fmap.duplicated(subset=["team_ID", "lg", "year_ID"]).any()
    spine = json.loads(SPINE.read_text(encoding="utf-8"))
    first_modern = spine["first_season"]
    seen = set()
    for f in ("bat.parquet", "pit.parquet"):
        df = pd.read_parquet(ROOT / ".cache" / "war_daily" / f, columns=["team_ID", "lg_ID", "year_ID"])
        assert int(df["year_ID"].min()) == 1871
        for t, lg, y in zip(df["team_ID"], df["lg_ID"], df["year_ID"]):
            y = int(y)
            key_lg = "*" if y >= first_modern else ("NA" if lg is None or lg != lg else str(lg))
            seen.add((str(t), key_lg, y))
    have = set(zip(fmap["team_ID"], fmap["lg"], fmap["year_ID"].astype(int)))
    missing = sorted(seen - have)
    assert not missing, f"team-league-seasons with no franchise: {missing[:10]}"
    buckets = dict(zip(fmap["franchise"], fmap["bucket"]))
    clubs = {k for k, b in buckets.items() if b == "club"}
    assert clubs == set(spine["orgs"]), "the 30 franchises are the spine's 30 orgs"
    assert all(k.startswith("DEF-") for k, b in buckets.items() if b == hd.DEFUNCT_BUCKET)


def test_the_history_block_is_what_the_tool_writes():
    """data/franchise_spine.json is a curation with a writer: the `history`
    block must be byte-for-byte what tools/franchise_spine_history.py writes."""
    if not _frames_present():
        pytest.skip("war_daily cache absent")
    sys.path.insert(0, str(ROOT / "tools"))
    import franchise_spine_history as fsh
    assert fsh.main(["--check"]) == 0


def test_the_history_block_reaches_the_1969_spine_without_overlap():
    spine = json.loads(SPINE.read_text(encoding="utf-8"))
    h = spine["history"]
    assert h["first_season"] == 1871 and h["last_season"] + 1 == spine["first_season"]
    assert set(h["lineage"]) <= set(spine["orgs"])
    for org, ivs in h["lineage"].items():
        for iv in ivs:
            assert 1871 <= iv["first"] <= iv["last"] <= h["last_season"], (org, iv)
    for c in h["defunct"]:
        assert c["group"] in h["defunct_groups"], c["key"]
        for iv in c["intervals"]:
            assert iv["last"] <= h["last_season"], (c["key"], iv)
    # A lineage club and a defunct club sharing a code are told apart by league.
    assert any(c["key"] == "DEF-BAL-1882" for c in h["defunct"])
    assert {"team_id": "BAL", "lg": "AL", "first": 1954, "last": 1968} in h["lineage"]["BAL"]


# --------------------------------------------------------------------------
# 2 and 3. One primary per inductee; the credit sums to the career
# --------------------------------------------------------------------------

def test_franchise_credit_sums_to_career_war_for_every_player(hd, credit):
    cf = hd.career_frame(offline=True).set_index("player_ID")
    s = credit.groupby("player_ID")["war"].sum()
    assert set(s.index) == set(cf.index)
    gap = (s - cf["career_war"].reindex(s.index)).abs().max()
    assert gap < 1e-9, gap


def test_every_inductee_maps_to_exactly_one_primary_franchise(hd, credit):
    b = hd.ballots()
    ind = set(b["inducted"])
    prim = hd.primary_franchise(credit[credit["player_ID"].isin(ind)])
    assert len(prim) == len(ind) and set(prim["player_ID"]) == ind
    assert not prim["player_ID"].duplicated().any()


def test_the_served_credit_puts_every_inductee_in_exactly_one_list(served):
    c = served["counts"]
    assert c["n_unmapped"] == 0 and c["n_credited"] == c["n_inductees"] == len(served["inductees"])
    homes = {}
    for club in served["clubs"]:
        for i in club["inductees"]:
            assert i not in homes, (i, homes.get(i), club["code"])
            homes[i] = club["code"]
    for i in served["defunct"]["inductees"]:
        assert i not in homes, (i, homes.get(i))
        homes[i] = served["defunct"]["key"]
    assert len(homes) == c["n_credited"]
    assert len(served["clubs"]) == 30
    assert sum(x["n"] for x in served["clubs"]) == c["n_to_a_current_franchise"]
    assert served["defunct"]["n"] == c["n_to_a_defunct_club"]
    assert sum(served["defunct"]["by_group"].values()) == served["defunct"]["n"]
    for r in served["inductees"]:
        home = served["defunct"]["key"] if r["primary_bucket"] == "DEFUNCT" else r["primary"]
        assert homes[r["id"]] == home, r["id"]
        assert r["induction"] in ("player_bbwaa", "route_unverified")


def test_the_served_credit_sums_to_the_served_career_war(served, hd):
    """The credit carries the file's two decimals and the career WAR the board's
    tenth, so the served check is to within half a tenth; the exact check is the
    in-memory one above."""
    for r in served["inductees"]:
        tot = sum(w for _, w in r["credit"])
        assert abs(tot - r["career_war"]) <= 0.05 + 1e-9, (r["id"], tot, r["career_war"])
        assert r["credit"][0][0] == r["primary"], r["id"]
        assert hd.round_half_up(r["credit"][0][1], 1) == r["primary_war"], r["id"]
        assert len({k for k, _ in r["credit"]}) == len(r["credit"]), r["id"]


# --------------------------------------------------------------------------
# 4. The four bridged Negro Leagues inductees, and named spot checks
# --------------------------------------------------------------------------

def test_the_four_bridged_negro_leagues_inductees_resolve(served):
    rows = {r["id"]: r for r in served["inductees"]}
    for pid, club in BRIDGED.items():
        assert pid in rows, f"{pid} is not credited"
        r = rows[pid]
        assert r["primary"] == club, (pid, r["primary"])
        assert r["primary_bucket"] == "DEFUNCT" and r["primary_group"] == "negro_leagues"
        assert r["induction"] == "route_unverified"
        assert pid in served["defunct"]["inductees"]


def test_named_spot_checks(served):
    rows = {r["id"]: r for r in served["inductees"]}
    assert rows["ruthba01"]["primary"] == "NYY"
    assert rows["johnswa01"]["primary"] == "MIN", "the 1901-1960 Senators are the Twins franchise"
    assert rows["mayswi01"]["primary"] == "SFG"
    assert rows["youngcy01"]["primary"] == "DEF-CLE-1887", "the Cleveland Spiders, a defunct club"
    # Connie Mack is credited where he PLAYED, and still reads route unverified.
    assert rows["mackco01"]["primary"] == "PIT" and rows["mackco01"]["induction"] == "route_unverified"


# --------------------------------------------------------------------------
# 5. The tie-break
# --------------------------------------------------------------------------

def test_the_tie_break_is_seasons_then_first_season_then_key(hd):
    import pandas as pd
    rows = [("x", "AAA", "club", 10.0, 3, 1990, 1992), ("x", "BBB", "club", 10.0, 5, 1993, 1997),
            ("y", "AAA", "club", 4.0, 2, 1950, 1951), ("y", "CCC", "club", 4.0, 2, 1940, 1941),
            ("z", "AAA", "club", -1.0, 1, 1900, 1900)]
    cr = pd.DataFrame(rows, columns=["player_ID", "franchise", "bucket", "war", "seasons", "first", "last"])
    for order in (cr, cr.iloc[::-1]):
        p = hd.primary_franchise(order).set_index("player_ID")
        assert p.at["x", "franchise"] == "BBB" and bool(p.at["x", "tied"])
        assert p.at["y", "franchise"] == "CCC" and bool(p.at["y", "tied"])
        assert p.at["z", "franchise"] == "AAA" and not bool(p.at["z", "tied"])


def test_the_rule_is_written_down_with_its_date(hd):
    txt = DOC.read_text(encoding="utf-8")
    assert hd.FRANCHISE_RULE_FROZEN in txt and "2026-09-25" == hd.FRANCHISE_RULE_FROZEN
    assert "Rejected" in txt and "plaque" in txt.lower()
    assert "DEFUNCT" in txt and "1871" in txt
    assert chr(0x2014) not in txt and chr(0x2013) not in txt


def test_a_map_that_cannot_place_every_stint_darkens_only_this_section(hd, monkeypatch, tmp_path):
    """The board must not go down with the map: the section turns dark with its
    reason and every other section still builds."""
    import hof_export as he
    monkeypatch.setattr(hd, "FRANCHISE_SPINE_PATH", tmp_path / "missing.json")
    r = he._franchises_or_dark(hd.ballots(), hd.career_frame(offline=True))
    assert r["live"] is False and "franchise_spine" in r["blocked_on"]
    assert len(r["why"]) > 80
