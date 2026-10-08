# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""awards_export.py on a fixture world (AWARDS_3_EXPORTER; AWARDS_PLAN 6 'Invariants and
tests' rows I1 to I4, I9, I11, I13's export part is test_awards_flag.py).

test_fixtures/awards/export/ (built by its _build_fixture.py from the core fixtures) is a
synthetic 2026 season laid out in the shapes awards_export.py reads BY PATH: the five
/mlbstats/ boards and their history files, mlb_projections.json, management_board.json,
model_registry.json, xfv.json, debuts_lite.json, the StatsAPI standings cache, the team
map, data/_labs/awards/rookies.json and the projection bundle meta. The stint frames are
injected through the exporter's memoised reader (awards_export.inject_frames), so no test
touches the network: an autouse fixture refuses every socket. The exporter runs with
awards_core.AWARDS_LIVE False, so every file lands under a temp preview directory with the
names it would carry at data/ depth one (awards.json, awards_<S>.json,
awards_candidates_<S>.json, awards_eval.json).
"""
from __future__ import annotations

import bisect
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import time
from fnmatch import fnmatch
from pathlib import Path

import pytest

import awards_core as A
import awards_export as E

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "awards" / "export"
SEASON = 2026
PROV = "ewar_v2"
PLAYER_AWARDS = ("MVP", "CY", "ROY")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards_export test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class World:
    """One copy of the fixture tree in a temp dir, with the frames injected."""

    def __init__(self, base: Path):
        self.base = base
        self.data = base / "data"
        self.cache = base / "cache"
        self.labs = base / "labs"
        self.model = base / "model"
        self.preview = base / "preview"
        self.out = base / "out"
        for sub in ("data", "cache", "labs", "model"):
            shutil.copytree(FIX / sub, base / sub)
        self.stints = _load(FIX / "stints.json")

    def inject(self):
        E.reset_frames()
        E.inject_frames(self.stints, PROV)

    def export(self, **kw):
        self.inject()
        args = dict(out_dir=self.out, data_dir=self.data, cache_dir=self.cache, labs_dir=self.labs,
                    preview_dir=self.preview, model_dir=self.model, log=lambda *_a, **_k: None)
        args.update(kw)
        return E.export(**args)

    def freeze(self, season=SEASON, **kw):
        self.inject()
        args = dict(data_dir=self.data, cache_dir=self.cache, labs_dir=self.labs,
                    model_dir=self.model, log=lambda *_a, **_k: None)
        args.update(kw)
        return E.freeze(season, **args)

    def read(self, name: str):
        return _load(self.preview / name)

    def edit_json(self, rel: str, fn):
        p = self.base / rel
        doc = _load(p)
        fn(doc)
        p.write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    old = E._display_provider
    E._display_provider = lambda: PROV
    w = World(tmp_path_factory.mktemp("awards_export"))
    w.res = w.export()
    assert w.res["ok"], w.res
    w.awards = w.read("awards.json")
    w.cands = w.read(f"awards_candidates_{SEASON}.json")
    w.eval = w.read("awards_eval.json")
    w.rows = A.league_split(w.stints, season=SEASON, war_provider=PROV)
    w.ewar = _load(w.data / "ewar.json")
    w.board = _load(w.data / "war_leaderboards.json")
    w.board_players = {p["mlbam"]: p for p in w.board["players"]}
    w.boards = {
        "hitters": {r["mlbam"]: r for r in _load(w.data / "hitter_leaderboards.json")["hitters"]},
        "starters": {r["mlbam"]: r for r in _load(w.data / "starter_leaderboards.json")["starters"]},
        "relievers": {r["mlbam"]: r for r in _load(w.data / "bullpen_leaderboards.json")["relievers"]},
        "fielders": {r["mlbam"]: r for r in _load(w.data / "defense_leaderboards.json")["fielders"]},
    }
    lev = _load(w.data / "leverage_leaderboards.json")
    w.boards["lev_bat"] = {r["mlbam"]: r for r in lev["batters"]}
    w.boards["lev_sp"] = {r["mlbam"]: r for r in lev["starters"]}
    w.proj = _load(w.data / "mlb_projections.json")
    w.mgmt = _load(w.data / "management_board.json")
    w.registry = {m["model_id"] for m in _load(w.data / "model_registry.json")["models"]}
    yield w
    E._display_provider = old
    E.reset_frames()


@pytest.fixture
def fresh(tmp_path):
    """A private copy for the tests that mutate inputs or freeze."""
    old = E._display_provider
    E._display_provider = lambda: PROV
    w = World(tmp_path)
    yield w
    E._display_provider = old
    E.reset_frames()


def _side_totals(rows):
    out = {}
    for r in rows:
        t = out.setdefault(r["mlbam"], {"bat": 0.0, "pit": 0.0})
        t["bat"] += r["bat"]
        t["pit"] += r["pit"]
    return out


def _midrank(v, pool):
    srt = sorted(pool)
    lo, hi = bisect.bisect_left(srt, v), bisect.bisect_right(srt, v)
    return round(100.0 * (lo + 0.5 * (hi - lo)) / len(srt), 1)


def _cards(awards):
    for award, by in awards.items():
        for lg, blk in by.items():
            yield award, lg, blk


# --- I1 and I2: the league shares against the artifact and the board -----------------------

def test_i1_each_sides_shares_sum_to_the_artifact_and_print_as_the_board(world):
    from war_board_export import _blank_free
    totals = _side_totals(world.rows)
    seen = 0
    for award, lg, blk in _cards(world.awards["awards"]):
        if award == "MOY":
            continue
        for r in blk["top"]:
            m = r["mlbam"]
            art = world.ewar["players"][str(m)][str(SEASON)]
            assert abs(totals[m]["bat"] - float(art.get("ewb") or 0.0)) <= 0.005, (r["name"], "bat")
            assert abs(totals[m]["pit"] - float(art.get("ewp") or 0.0)) <= 0.005, (r["name"], "pit")
            if m in world.board_players:
                assert _blank_free(totals[m]["bat"] + totals[m]["pit"]) == world.board_players[m]["war"], r["name"]
            assert r["score_display"] == _blank_free(r["score"])
            assert blk["war_provider"] == PROV
            seen += 1
    assert seen >= 6 * 3
    # the same law over every candidate row the file carries
    for key, pool in world.cands["pools"].items():
        if key.endswith("-moy"):
            continue
        cols = [c["key"] for c in world.cands["columns"][pool["award"]]]
        for row in pool["rows"]:
            m = row[cols.index("id")]
            art = world.ewar["players"][str(m)][str(SEASON)]
            assert abs(totals[m]["bat"] - float(art.get("ewb") or 0.0)) <= 0.005
            assert abs(totals[m]["pit"] - float(art.get("ewp") or 0.0)) <= 0.005
    assert world.eval["reconciliation"]["I1"]["n_artifact_ok"] == world.eval["reconciliation"]["I1"]["n_checked"]
    assert world.eval["reconciliation"]["I1"]["n_board_ok"] == world.eval["reconciliation"]["I1"]["n_board_rows"]


def test_i2_cy_young_pit_is_the_pitcher_side_and_mvp_sums_both_for_one_league_players(world):
    from war_board_export import _blank_free
    totals = _side_totals(world.rows)
    for lg in A.LEAGUES:
        for r in world.awards["awards"]["CY"][lg]["top"]:
            assert r["score"] == r["pit"]
            bp = world.board_players.get(r["mlbam"]) or {}
            if bp.get("war_pit") is not None and not r.get("share"):
                assert _blank_free(r["pit"]) == bp["war_pit"], r["name"]
        for r in world.awards["awards"]["MVP"][lg]["top"]:
            assert abs(r["score"] - (r["bat"] + r["pit"])) < 1e-9
            if not r.get("share"):
                assert _blank_free(r["bat"] + r["pit"]) == world.board_players[r["mlbam"]]["war"], r["name"]
            else:
                assert "split_season" in r["flags"]
                assert abs(sum(v["bat"] + v["pit"] for v in r["share"].values())
                           - (totals[r["mlbam"]]["bat"] + totals[r["mlbam"]]["pit"])) < 1e-9
    assert world.eval["reconciliation"]["I2"]["n_pitch_ok"] == world.eval["reconciliation"]["I2"]["n_pitch_rows"] > 0


# --- I3: every copied value equals its producer's field byte for byte ------------------------

_BOARD_FIELDS = {
    "hem_plus": ("hitters", "hem_plus"), "xhem_plus": ("hitters", "xhem_plus"),
    "wrc_plus": ("hitters", "wrc_plus"), "sem_plus": ("starters", "sem_plus"),
    "xsem_plus": ("starters", "xsem_plus"), "rem_plus": ("relievers", "rem_plus"),
    "dem_plus": ("fielders", "dem_plus"), "gmli": ("relievers", "gmli"),
}


def _board_value(world, m, key):
    if key in _BOARD_FIELDS:
        src, field = _BOARD_FIELDS[key]
        return (world.boards[src].get(m) or {}).get(field)
    if key in ("era", "fip"):
        for src in ("starters", "relievers"):
            if m in world.boards[src]:
                return world.boards[src][m].get(key)
        return None
    if key == "wpa":
        for src in ("lev_bat", "lev_sp", "relievers"):
            if m in world.boards[src] and world.boards[src][m].get("wpa") is not None:
                return world.boards[src][m]["wpa"]
        return None
    if key == "bwp":
        return world.ewar["players"][str(m)][str(SEASON)].get("bwp")
    return "skip"


def test_i3_compare_values_are_byte_copies_of_their_producer_fields(world):
    n = 0
    for award, lg, blk in _cards(world.awards["awards"]):
        if award == "MOY":
            continue
        for m_ in blk["compare"]["metrics"]:
            assert m_["producer"], (award, lg, m_["key"])
            for r, v in zip(blk["top"][:3], m_["values"]):
                want = _board_value(world, r["mlbam"], m_["key"])
                if want == "skip":
                    continue
                assert json.dumps(v) == json.dumps(want), (award, lg, m_["key"], r["name"])
                n += 1 if v is not None else 0
    assert n > 20
    assert world.eval["reconciliation"]["I3"]["n_equal"] == world.eval["reconciliation"]["I3"]["n_copied_values"] > 0


def test_i3_superlative_fields_are_byte_copies(world):
    by_id = {s["id"]: s for s in world.awards["superlatives"]}
    for r in by_id["glove"]["rows"]:
        f = world.boards["fielders"][r["id"]]
        assert json.dumps(r["value_display"]) == json.dumps(f["dem_plus"])
        assert r["value"] == f["dem_plus_raw"] and r["pos"] == f["pos"] and r["inn"] == f["inn"]
        assert json.dumps(r["def_runs"]) == json.dumps(f["def_runs"])
    for r in by_id["relief"]["rows"]:
        p = world.boards["relievers"][r["id"]]
        assert json.dumps(r["value_display"]) == json.dumps(p["rem_plus"])
        assert r["value"] == p["rem_plus_raw"] and r["gmli"] == p["gmli"]
        assert json.dumps(r["wpa"]) == json.dumps(p["wpa"]) and json.dumps(r["saves"]) == json.dumps(p["saves"])
    for sl in ("contact_ahead", "results_ahead"):
        for r in by_id[sl]["rows"]:
            h = world.boards["hitters"][r["id"]]
            assert r["xwoba_minus_woba"] == h["luck_gap"] == r["value"]
            assert "luck" not in json.dumps(r).lower()
    rows = {r["club"]: r for r in world.mgmt["clubs"]["rows"] if r["season"] == SEASON}
    for r in by_id["pitching_changes"]["rows"]:
        club = r["id"][1:].upper()
        src = rows[club]
        assert r["value"] == src["mwpa_pitching_change"]
        assert r["n_pitching_change"] == src["n_pitching_change"] >= A.PITCHING_CHANGES_MIN_N
    vets = {v["mlbam"]: v for v in world.proj["vets"]}
    totals = _side_totals(world.rows)
    for sl in ("next_rise", "next_drop"):
        blk = by_id[sl]
        assert blk["war_provider"] == PROV and blk["rows"]
        for r in blk["rows"]:
            assert r["to"] == vets[r["id"]]["war"][0]
            assert abs(r["from"] - (totals[r["id"]]["bat"] + totals[r["id"]]["pit"])) < 1e-9
            assert abs(r["value"] - (r["to"] - r["from"])) < 1e-9
        assert blk["stamp"]["war_provider"] == PROV and blk["stamp"]["first_season"] == SEASON + 1


def test_i3_candidate_metric_columns_are_byte_copies(world):
    n = 0
    for key, pool in world.cands["pools"].items():
        if key.endswith("-moy"):
            continue
        cols = [c["key"] for c in world.cands["columns"][pool["award"]]]
        for row in pool["rows"] + [x["row"] for x in pool.get("proxy_out") or []]:
            m = row[cols.index("id")]
            for ck in cols:
                want = _board_value(world, m, ck)
                if want == "skip":
                    continue
                assert json.dumps(row[cols.index(ck)]) == json.dumps(want), (key, m, ck)
                n += 1
    assert n > 100


def test_i3_pool_percentiles_recompute_on_the_fixture(world):
    rook = A.rookie_status(_load(world.labs / "rookies.json")["seasons"][0])
    for award, lg, blk in _cards(world.awards["awards"]):
        if award == "MOY":
            continue
        pool = [r for r in world.rows if r["league"] == lg and A.clears_floor(award, r, SEASON)]
        if award == "ROY":
            pool = [r for r in pool if (rook.get(r["mlbam"]) or {}).get("eligible")]
        assert len(pool) == blk["n_pool"]
        for m_ in blk["compare"]["metrics"]:
            if m_["key"] == "score":
                vals = [(r["pit"] if award == "CY" else r["bat"] + r["pit"]) for r in pool]
                exact = [r["score"] for r in blk["top"][:3]]
            else:
                got = [_board_value(world, r["mlbam"], m_["key"]) for r in pool]
                if any(g == "skip" for g in got):
                    continue
                vals = [float(g) for g in got if g is not None]
                exact = m_["values"]
            assert m_["n_pool"] == len(vals)
            for v, pct in zip(exact, m_["pct"]):
                if v is None:
                    assert pct is None
                else:
                    assert pct == _midrank(float(v), vals), (award, lg, m_["key"])
            srt = sorted(vals)
            assert m_["p1"] == round(E._pctl(srt, 1), 4) and m_["p99"] == round(E._pctl(srt, 99), 4)
            assert m_["p1"] <= m_["p99"]


def test_every_compare_metric_race_block_and_candidate_column_names_its_producer_and_registry(world):
    ok = world.registry | {A.SELECTION_REGISTRY}
    for award, lg, blk in _cards(world.awards["awards"]):
        for m_ in blk["compare"]["metrics"]:
            assert isinstance(m_["producer"], str) and m_["producer"]
            assert m_["registry"] is None or m_["registry"] in ok, m_
            assert "registry" in m_ and "producer" in m_
    for key, race in world.awards["race"].items():
        assert race is None or ("producer" in race and "registry" in race)
    for award, cols in world.cands["columns"].items():
        for c in cols:
            assert set(c) == {"key", "label", "producer", "registry"}
            assert c["producer"]
            assert c["registry"] is None or c["registry"] in ok
    for s in world.awards["superlatives"]:
        if not s.get("blocked_on"):
            assert s["producer"] and s["registry"] in ok


# --- I4: Manager ---------------------------------------------------------------------------------

def test_i4_manager_pythag_parts_and_the_thirty_club_sum(world):
    outlook = {t["team"]: t["current"] for t in world.proj["team_outlook"]}
    for lg in A.LEAGUES:
        blk = world.awards["awards"]["MOY"][lg]
        assert blk["n_pool"] == 15
        for r in blk["top"]:
            cur = outlook[r["club"]]
            assert abs(r["pythag_w"] - cur["pythagPct"] * cur["gamesPlayed"]) < 1e-9
            assert abs(r["parts"]["sequencing"] + r["parts"]["runs_vs_player_value"] - r["score"]) < 1e-9
            assert r["links"] == {"management": f"/management/#team={r['club']}",
                                  "franchise": f"/franchise/#team={r['club']}"}
    scores = []
    for lg in A.LEAGUES:
        pool = world.cands["pools"][f"{lg.lower()}-moy"]
        cols = [c["key"] for c in world.cands["columns"]["MOY"]]
        assert all(str(row[cols.index("id")]).startswith("c") for row in pool["rows"])
        scores += [row[cols.index("score")] for row in pool["rows"]]
    assert len(scores) == 30 and abs(sum(scores)) < 0.5
    i4 = world.eval["reconciliation"]["I4"]
    assert i4["n_clubs"] == 30 and i4["n_parts_sum_to_score"] == 30 and i4["n_pythag_matches_team_outlook"] == 30


# --- I9: the freeze is write-once and the closed shards are byte-stable --------------------------

def test_i9_freeze_is_write_once_and_the_frozen_card_grows_a_drift_column(fresh):
    first = fresh.export()
    assert first["ok"] and first["status"] == "live"
    res = fresh.freeze()
    assert res["ok"], res
    frozen = fresh.labs / f"frozen_{SEASON}.json"
    log = fresh.labs / "freeze_log.json"
    raw, sha = frozen.read_bytes(), res["sha256"]
    assert hashlib.sha256(raw).hexdigest() == sha
    entries = _load(log)["entries"]
    assert entries[-1]["sha256"] == sha and entries[-1]["season"] == SEASON
    assert entries[-1]["path"] == f"data/_labs/awards/frozen_{SEASON}.json"
    rec = json.loads(raw)
    assert rec["freeze"]["war_provider"] == PROV and rec["war_provider"] == PROV
    assert rec["freeze"]["after_finalists"] is False and rec["freeze"]["finalists_announced"] is None
    assert {s["id"] for s in rec["superlatives"]}.isdisjoint({"next_rise", "next_drop"})
    again = fresh.freeze()
    assert again["ok"] is False and "write-once" in again["reason"]
    assert frozen.read_bytes() == raw and _load(log)["entries"] == entries
    second = fresh.export()
    assert second["ok"] and second["status"] == "frozen"
    doc = fresh.read("awards.json")
    assert doc["status"] == "frozen" and doc["freeze"]["record_sha256"] == sha
    assert doc["stamp"]["frozen_at"] == rec["frozen_at"]
    assert doc["selection_caption"].startswith("The eephus selection, 1st place")
    for award, lg, blk in _cards(doc["awards"]):
        assert blk["drift"] and len(blk["drift"]) == len(blk["top"])
        for d, r in zip(blk["drift"], blk["top"]):
            assert d["war_provider"] == PROV and d["unit_label"] == A.drift_unit_label(PROV)
            assert abs(d["score_now"] - r["score"]) < 1e-9
    shard = fresh.preview / f"awards_{SEASON}.json"
    assert shard.exists() and _load(shard)["status"] == "frozen"
    assert frozen.read_bytes() == raw, "a rebuild moved the frozen record"


def test_i9_closed_season_shards_are_byte_stable_across_runs(fresh):
    fresh.export()
    before = {p.name: p.read_bytes() for p in fresh.preview.glob("awards_20*.json")}
    assert before and all(not n.startswith("awards_candidates") for n in before)
    fresh.export()
    after = {p.name: p.read_bytes() for p in fresh.preview.glob("awards_20*.json")}
    assert after == before
    for name, raw in before.items():
        doc = json.loads(raw)
        assert doc["status"] == "closed" and doc["war_provider"] == PROV
        assert doc["generated_at"] == f"{doc['season']}-closed"


# --- I11: structure ------------------------------------------------------------------------------

TOP_KEYS = {"schema", "produced_by", "generated_at", "default_season", "seasons", "season", "status",
            "war_provider", "stamp", "freeze", "stamps", "registry", "ballot_rules", "rules", "awards",
            "superlatives", "race", "vote_table", "credits", "what_this_page_does_not_claim",
            "selection_caption"}
_WITHHELD_SHAPES = ("xfv_*matrix*", "*_matrix__*", "xfv_scored*", "star_label*")


def test_i11_structure_depth_one_paths_and_the_ballot_rules(world):
    doc = world.awards
    assert set(doc) == TOP_KEYS
    assert doc["schema"] == 1 and doc["produced_by"] == "awards_export.py"
    assert doc["default_season"] == doc["season"] == SEASON and doc["status"] == "live"
    assert doc["war_provider"] == PROV
    for award in A.AWARDS:
        for lg in A.LEAGUES:
            top = doc["awards"][award][lg]["top"]
            assert len(top) >= 3 and [r["rank"] for r in top[:3]] == [1, 2, 3]
            assert len(top) <= A.BALLOT_RULES[award]["n"]
    assert doc["ballot_rules"] == {"MVP": {"n": 10, "points": [14, 9, 8, 7, 6, 5, 4, 3, 2, 1]},
                                   "CY": {"n": 5, "points": [7, 4, 3, 2, 1]},
                                   "ROY": {"n": 3, "points": [5, 3, 1]},
                                   "MOY": {"n": 3, "points": [5, 3, 1]}}
    for s in doc["superlatives"]:
        if not s.get("blocked_on"):
            assert E.SL_MIN_ROWS <= len(s["rows"]) <= A.SL_TOP_N, s["id"]
        else:
            assert s["rows"] == []
    thin = next(s for s in doc["superlatives"] if s["id"] == "relief")
    assert thin["n_pool"] == 1 and "Only 1 of" in thin["blocked_on"], "the fixture's one-reliever pool"
    assert "relief" not in doc["seasons"][0]["superlatives"]
    assert [s["id"] for s in doc["superlatives"]] == list(A.SL_IDS)
    assert len(doc["what_this_page_does_not_claim"]) == 7
    assert doc["what_this_page_does_not_claim"][4] == f"The selection reads {A.war_unit_label(PROV)} on today's files."
    assert doc["seasons"][0] == {"season": SEASON, "status": "live", "awards": list(A.AWARDS),
                                 "superlatives": doc["seasons"][0]["superlatives"], "race": False, "note": None}
    assert [s["season"] for s in doc["seasons"]] == list(range(SEASON, E.SELECTOR_FIRST - 1, -1))
    assert all(r["computed_after_the_fact"] for r in doc["vote_table"])
    assert all(r["season"] < SEASON for r in doc["vote_table"])
    exclude = {ln.strip() for ln in (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.startswith("#")}
    for name in world.res["files"]:
        assert "/" not in name and "\\" not in name, name
        assert re.fullmatch(r"awards(_candidates_\d{4}|_\d{4}|_eval)?\.json", name), name
        assert name not in exclude
        assert not any(fnmatch(name, pat) for pat in _WITHHELD_SHAPES)
    expected = {"awards.json", "awards_eval.json"} | {f"awards_candidates_{s}.json" for s in range(E.SELECTOR_FIRST, SEASON + 1)} \
        | {f"awards_{s}.json" for s in range(E.SELECTOR_FIRST, SEASON)}
    assert set(world.res["files"]) == expected
    for mid, row in doc["registry"].items():
        assert row["registered"] or mid == A.SELECTION_REGISTRY, mid
        assert row["registered"] == (mid in world.registry)
    cand = world.cands
    assert cand["war_provider"] == PROV and cand["season"] == SEASON and cand["ballot_rules"] == doc["ballot_rules"]
    assert set(cand["pools"]) == {f"{lg.lower()}-{a.lower()}" for a in A.AWARDS for lg in A.LEAGUES}
    assert str(E.CANDIDATE_MIN_PA) in cand["pool_rule"] and str(E.CANDIDATE_MIN_IP) in cand["pool_rule"]
    for key, pool in cand["pools"].items():
        n = A.BALLOT_RULES[pool["award"]]["n"]
        cols = [c["key"] for c in cand["columns"][pool["award"]]]
        places = [row[cols.index("place")] for row in pool["rows"] if row[cols.index("place")] is not None]
        assert sorted(places) == list(range(1, min(n, len(places)) + 1)), key
        if key.endswith("-roy"):
            assert "proxy_out" in pool
            for x in pool["proxy_out"]:
                assert x["reason"] and x["row"][cols.index("outside_rookie_proxy")] is True


def test_i11_war_provider_sits_on_every_war_bearing_block(world):
    doc = world.awards
    for award, lg, blk in _cards(doc["awards"]):
        assert blk["war_provider"] == PROV
        assert doc["rules"][award]["war_provider"] == PROV
        unit = "wins" if award == "MOY" else A.war_unit_label(PROV)
        assert doc["rules"][award]["unit"] == unit
    for s in doc["superlatives"]:
        if s["id"].startswith(("prospect_", "proj_", "next_")):
            assert s["war_provider"] in (PROV, None) if s.get("blocked_on") else s["war_provider"] == PROV
    assert world.cands["war_provider"] == PROV
    assert doc["stamp"]["stint_frames"] == {"provider": PROV, "stale": {}}
    assert world.eval["war_provider"] == PROV


def test_served_superlatives_carry_what_the_page_prints(world):
    """AWARDS_8: every served superlative block carries the unit, axis label, ruler and row
    context lines awards_core.sl_present builds from its own fields (idempotent, so a
    block read from a frozen record gains them without the record being rewritten)."""
    for s in world.awards["superlatives"]:
        assert {"unit", "war_unit", "axis_label", "ruler"} <= set(s), s["id"]
        assert A.sl_present(s, SEASON) == s, s["id"]
        assert all("context" in r for r in s["rows"])
    by = {s["id"]: s for s in world.awards["superlatives"]}
    assert by["glove"]["ruler"] == "z" and by["relief"]["ruler"] == "run"
    assert by["next_rise"]["unit"] == A.war_unit_label(PROV)


def test_payload_strings_carry_no_verdict_word_ban_word_or_dash(world):
    def strings(obj, key=None):
        if isinstance(obj, str):
            if key not in ("name", "club_name", "producer"):
                yield obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                yield from strings(v, k)
        elif isinstance(obj, list):
            for v in obj:
                yield from strings(v, key)
    for payload in (world.awards, world.cands, world.eval):
        hits = [(s, A.verdict_hits(s)) for s in strings(payload) if A.verdict_hits(s)]
        assert not hits, hits[:5]


def test_the_prospect_pair_holds_only_debut_cohorts_the_frame_guard_admits(world):
    frames = A.reserved_frames()
    debuts = {d["mlbam_id"]: int(d["debut_date"][:4]) for d in _load(world.data / "debuts_lite.json")}
    reserved = {m for m, y in debuts.items() if y >= frames["lv_first"]}
    assert reserved, "the fixture carries no reserved cohort to test the guard"
    for s in world.awards["superlatives"]:
        if s["id"].startswith("prospect_"):
            assert s["rows"]
            for r in s["rows"]:
                assert debuts[r["id"]] < frames["lv_first"]
                assert r["id"] not in reserved
            assert s["frame_label"] == A.prospect_frame_label(frames)
        if s["id"].startswith("proj_"):
            assert s["blocked_on"] == A.proj_blocked_on(SEASON) and s["rows"] == []


# --- refusals (AWARDS_PLAN 4.9), each on a fixture, each leaving yesterday's files ------------------

def _snapshot(d: Path) -> dict:
    return {p.name: p.read_bytes() for p in d.glob("*.json")} if d.exists() else {}


def _refuses(fresh, mutate, needle: str, **kw):
    assert fresh.export()["ok"]
    before = _snapshot(fresh.preview)
    mutate()
    res = fresh.export(**kw)
    assert res["ok"] is False and res["files"] == {}, res
    assert needle in res["reason"], res["reason"]
    assert _snapshot(fresh.preview) == before, "a refusal moved yesterday's files"
    return res


def test_refuses_on_a_stale_ewar_board(fresh):
    def mutate():
        fresh.edit_json("data/war_leaderboards.json", lambda d: d["ewar_vintage"].__setitem__("stale", True))
    _refuses(fresh, mutate, "eWAR board is stale")


def test_refuses_when_a_stint_frame_was_served_from_its_last_good_parquet(fresh, monkeypatch):
    def mutate():
        monkeypatch.setattr(E, "_served_stale", lambda: {"pit": {"age_days": 3.4, "rows": 10, "error": "timeout"}})
    res = _refuses(fresh, mutate, "pit stint frame from its last-good parquet")
    assert "3.4 days" in res["reason"]


def test_refuses_when_a_top_row_breaks_i1(fresh):
    top = fresh.export()
    m = None

    def mutate():
        nonlocal m
        doc = fresh.read("awards.json")
        m = doc["awards"]["MVP"]["AL"]["top"][0]["mlbam"]
        fresh.edit_json("data/ewar.json", lambda d: d["players"][str(m)][str(SEASON)].__setitem__(
            "ewb", float(d["players"][str(m)][str(SEASON)].get("ewb") or 0.0) + 0.5))
    assert top["ok"]
    _refuses(fresh, mutate, "I1:")


def test_refuses_on_a_projection_provider_mismatch(fresh):
    def mutate():
        fresh.edit_json("model/meta.json", lambda d: d.__setitem__("war_provider", "bwar"))
    res = _refuses(fresh, mutate, "next_rise / next_drop")
    assert "bwar" in res["reason"] and PROV in res["reason"]


def test_refuses_on_fewer_than_thirty_clubs(fresh):
    def mutate():
        fresh.edit_json(f"cache/statsapi_standings_{SEASON}.json",
                        lambda d: d["records"][0].__setitem__("teamRecords", d["records"][0]["teamRecords"][:3]))
    _refuses(fresh, mutate, f"fewer than {E.MIN_CLUBS} clubs")


def test_refuses_without_a_rookie_block_for_the_season(fresh):
    def mutate():
        fresh.edit_json("labs/rookies.json", lambda d: d.__setitem__("seasons", []))
    _refuses(fresh, mutate, f"rookies.json has no block for {SEASON}")


def test_refuses_when_the_frozen_record_hash_is_not_in_the_freeze_log(fresh):
    assert fresh.export()["ok"]
    assert fresh.freeze()["ok"]

    def mutate():
        p = fresh.labs / f"frozen_{SEASON}.json"
        p.write_bytes(p.read_bytes() + b"\n")
    _refuses(fresh, mutate, "freeze_log.json")


def test_refuses_on_an_old_standings_cache_in_season(fresh):
    def mutate():
        fresh.edit_json("data/mlb_projections.json", lambda d: (
            d.__setitem__("mc_schedule_source", "live"),
            d["team_outlook"][0]["current"].__setitem__("remGames", 4)))
        p = fresh.cache / f"statsapi_standings_{SEASON}.json"
        old = time.time() - 5 * 86400
        os.utime(p, (old, old))
    _refuses(fresh, mutate, "standings cache is older than")


def test_refuses_over_the_size_line(fresh, monkeypatch):
    def mutate():
        monkeypatch.setattr(E, "CANDIDATES_MAX_BYTES", 1000)
    _refuses(fresh, mutate, "over its size line")


def test_the_freeze_refuses_while_the_season_is_in_progress(fresh):
    fresh.edit_json("data/mlb_projections.json", lambda d: (
        d.__setitem__("mc_schedule_source", "live"),
        d["team_outlook"][0]["current"].__setitem__("remGames", 4)))
    res = fresh.freeze()
    assert res["ok"] is False and "in progress" in res["reason"]
    assert not (fresh.labs / f"frozen_{SEASON}.json").exists()
    assert not (fresh.labs / "freeze_log.json").exists()


# --- the size lines ----------------------------------------------------------------------------------

def test_size_lines_hold_on_the_fixture_and_are_the_plans(world):
    assert E.AWARDS_MAX_BYTES == 400_000 and E.CANDIDATES_MAX_BYTES == 300_000
    assert world.res["files"]["awards.json"] < E.AWARDS_MAX_BYTES
    for name, n in world.res["files"].items():
        if name.startswith("awards_candidates_"):
            assert n < E.CANDIDATES_MAX_BYTES
    assert world.res["n_rows"] == sum(len(p["rows"]) + len(p.get("proxy_out") or [])
                                      for p in world.cands["pools"].values())


# --- the pipeline, the catalog and the eval artifact -----------------------------------------------------

def test_the_pipeline_steps_sit_where_the_plan_puts_them():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    d = src.index('with _step("d10h. Awards board (awards.json)"')
    fr = src.index('with _step("6b7d. Franchise board (franchise_board.json)"')
    fin = src.index("finish_run(run_id, new_snapshots=0, stat_lines=0,", d)
    assert fr < d < fin
    m = src.index('with _step("6b7f. Awards board (awards.json)"')
    hof = src.index('with _step("6b7b. Hall of Fame board (hof_board.json)"')
    assert hof < m
    assert src.count("def _export_awards_board(log)") == 1
    assert src.count("            _export_awards_board(log)" + chr(10)) == 2
    assert '_record_ingest("awards_export"' in src
    i = src.index("SCHEDULED_EXPORTS = (")
    j = src.index("\n)\n", i)
    literal = src[i:j]
    assert '"awards_export"' not in literal, "the watched row joins the tuple only at the flip"
    assert '"statsapi_standings"' in literal
    branch = src.index('SCHEDULED_EXPORTS = SCHEDULED_EXPORTS + ("awards_export",)')
    assert branch > j and "if _AWARDS_LIVE:" in src[j:branch]


def test_the_catalog_names_the_published_files_and_the_labs_files():
    src = (ROOT / "data_catalog.py").read_text(encoding="utf-8")
    for name in ("awards.json", "awards_*.json", "awards_candidates_*.json", "awards_eval.json",
                 "_labs/awards/*.json"):
        assert f'"file": "{name}"' in src, name
    import data_catalog as dc
    rows = [a for a in dc.ARTIFACTS if a["file"].startswith(("awards", "_labs/awards"))]
    assert len(rows) == 5
    for a in rows:
        assert a["pinned_by"] == "test_awards_export.py" and a["group"] == "mlb"


def test_the_eval_artifact_carries_the_reconciliation_counts_and_the_freeze_hashes(fresh):
    assert fresh.export()["ok"]
    ev = fresh.read("awards_eval.json")
    assert ev["model_id"] == A.SELECTION_REGISTRY and ev["war_provider"] == PROV
    assert set(ev["reconciliation"]) == {"I1", "I2", "I3", "I4"}
    assert ev["rookie_winners"]["status"] == "no winners file" and ev["freeze"] == []
    assert fresh.freeze()["ok"] and fresh.export()["ok"]
    ev2 = fresh.read("awards_eval.json")
    assert [e["season"] for e in ev2["freeze"]] == [SEASON]
    assert ev2["freeze"] == _load(fresh.labs / "freeze_log.json")["entries"]


def test_the_winners_file_feeds_the_writers_line_the_vote_table_and_the_rookie_check(fresh):
    base = fresh.export()
    assert base["ok"]
    doc = fresh.read("awards.json")
    win = doc["awards"]["ROY"]["AL"]["top"][1]
    cands = fresh.read(f"awards_candidates_{SEASON}.json")
    club = cands["pools"]["al-moy"]["rows"][2][0][1:].upper()
    team_id = next(int(k) for k, v in _load(fresh.cache / "team_abbrev_map.json").items()
                   if A._club_code(v) == club)
    # The shape tools/award_winners_ingest.py writes: seasons -> StatsAPI award id -> record,
    # with the optional finalists keys a later ingest may add.
    winners = {"fetched_at": "2026-11-20", "source": {"id": "awards_statsapi"}, "copyright": "c",
               "seasons": {str(SEASON): {
                   "ALROY": {"person_id": win["mlbam"], "name": win["name"], "team_id": 0,
                             "team_code": None, "date": "2026-10-02",
                             "finalists": [{"person_id": r["mlbam"], "name": r["name"], "team_id": 0}
                                           for r in doc["awards"]["ROY"]["AL"]["top"][:3]],
                             "finalists_announced": "2026-10-01"},
                   "ALMOY": {"person_id": 1, "name": "A Manager", "team_id": team_id,
                             "team_code": None, "date": "2026-11-18"}}}}
    (fresh.labs / "award_winners.json").write_text(json.dumps(winners), encoding="utf-8")
    res = fresh.export()
    assert res["ok"] and "fetched 2026-11-20" in res["message"]
    doc = fresh.read("awards.json")
    w = doc["awards"]["ROY"]["AL"]["writers"]
    assert w["status"] == "final" and w["winner"] == {"id": win["mlbam"], "name": win["name"]}
    assert w["announce_label"] is None
    assert w["rule_place_of_winner"] == 2 and len(w["finalists"]) == 3
    wm = doc["awards"]["MOY"]["AL"]["writers"]
    assert wm["winner"]["id"] == "c" + club.lower() and wm["rule_place_of_winner"] == 3
    rows = [r for r in doc["vote_table"] if r["season"] == SEASON]
    assert {(r["award"], r["league"]) for r in rows} == {("ROY", "AL"), ("MOY", "AL")}
    assert all(r["computed_after_the_fact"] for r in rows)
    roy = next(r for r in rows if r["award"] == "ROY")
    assert roy["rule_place_of_writers_first"] == 2 and roy["writers_first"]["id"] == win["mlbam"]
    ev = fresh.read("awards_eval.json")
    assert ev["rookie_winners"]["status"] == "measured" and ev["rookie_winners"]["n_winners"] == 0
    fz = fresh.freeze()
    assert fz["ok"]
    rec = _load(fresh.labs / f"frozen_{SEASON}.json")
    assert rec["freeze"]["finalists_announced"] == "2026-10-01" and rec["freeze"]["after_finalists"] is True


def test_the_winners_place_is_read_on_the_rules_ballot():
    """rule_place_of_winner and rule_place_of_writers_first read the rule's ballot (the
    BBWAA length): a winner past it, or off the pool, is null, outside the rule's ballot."""
    top = [{"rank": i, "mlbam": 1000 + i} for i in range(1, 13)]
    assert E.ballot_place("MVP", top, 1004) == 4
    assert E.ballot_place("MVP", top, 1010) == 10
    assert E.ballot_place("MVP", top, 1011) is None
    assert E.ballot_place("CY", top, 1005) == 5 and E.ballot_place("CY", top, 1006) is None
    assert E.ballot_place("ROY", top, 1003) == 3 and E.ballot_place("ROY", top, 1004) is None
    assert E.ballot_place("ROY", top, 99) is None and E.ballot_place("ROY", top, None) is None
    clubs = [{"rank": 1, "club": "TB"}, {"rank": 2, "club": "HOU"}, {"rank": 3, "club": "NYY"},
             {"rank": 4, "club": "SEA"}]
    assert E.ballot_place("MOY", clubs, "cnyy") == 3 and E.ballot_place("MOY", clubs, "csea") is None


def test_winner_rows_read_the_ingest_shape():
    doc = {"seasons": {"2012": {"ALMVP": {"person_id": 5, "name": "B", "team_id": 116,
                                          "team_code": "DET", "date": "2012-11-15"}},
                       "2011": {"NLMOY": {"person_id": 7, "name": "M", "team_id": 109,
                                          "team_code": "ARI", "date": "2011-11-16"},
                                "XXMVP": {"person_id": 9}}}}
    rows = E.winner_rows(doc)
    assert [(r["season"], r["award"], r["league"]) for r in rows] == [(2011, "MOY", "NL"), (2012, "MVP", "AL")]
    assert rows[1]["winner"] == {"person_id": 5, "name": "B", "team_id": 116, "team_code": "DET"}
    assert rows[1]["announced"] == "2012-11-15" and rows[1]["finalists"] == []
    assert E.winner_rows(None) == [] and E.winner_rows({}) == []
