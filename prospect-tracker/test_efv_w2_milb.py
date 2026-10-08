# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the wave-2 MiLB profile family (efv_w2_milb.py, EFV3_W2_1b).

1. As of: a column reads only MiLB seasons that had ended by the read (the
   efv_dataset._milb_features rule), never below the row's floor, at most MAX_SEASONS
   seasons; a line after the read never moves a value (fixture leakage test).
2. Level and age relative: a line on its level-season's age line reads zero.
3. The arms: eight, all skill-head columns, registered in the screening lab's wave 2
   without touching wave 1, and buildable through the lab's own column_values.
4. Bans: reserved list vintages raise, nothing is grouped by consensus-FV level, no
   served exporter is imported, no em-dash.
5. The artifact, when present: development only, the frozen label, no reserved year,
   coverage counted per vintage and side, and the ledger rows it lands are its own.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_screen_lab as LAB  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_milb as M  # noqa: E402

SRC = ROOT / "efv_w2_milb.py"
PID = 900001


def _line(pid, season, level, age, side, **kw):
    sport = {"AAA": 11, "AA": 12, "A+": 13, "A": 14, "CPX": 16}[level]
    row = {"mlbam": pid, "season": season, "sport": sport, "league": "XX",
           "level": level, "age": age, "hbp": 0}
    if side == "hit":
        row.update({"pa": 400, "ab": 360, "h": 90, "doubles": 18, "triples": 2,
                    "hr": 10, "bb": 40, "so": 80, "go": 120, "ao": 110})
    else:
        row.update({"bf": 400, "bb": 36, "so": 90, "hr": 8, "go": 130, "ao": 100})
    row.update(kw)
    return row


def _population(season, level, side):
    """Forty lines whose rates do not depend on age: the age line is flat, so the
    level-season norm is the common rate itself."""
    return [_line(PID + 1000 + i, season, level, 19 + (i % 8), side) for i in range(40)]


@pytest.fixture
def cache(monkeypatch):
    """A synthetic StatsAPI cache: populations at A, A+ and AA for 2012 to 2018 and one
    player of interest with a line in every season."""
    store: dict = {}
    for side, group in M.GROUPS.items():
        for season in range(2012, 2019):
            for level in ("A", "A+", "AA"):
                sport = {"AA": 12, "A+": 13, "A": 14}[level]
                store.setdefault((sport, season, group), []).extend(
                    _population(season, level, side))
    plays = {2013: "A", 2014: "A", 2015: "A+", 2016: "A+", 2017: "AA", 2018: "AA"}
    for season, level in plays.items():
        sport = {"AA": 12, "A+": 13, "A": 14}[level]
        store[(sport, season, "hitting")].append(
            _line(PID, season, level, 21, "hit", bb=40 + 10 * (season - 2012)))
        store[(sport, season, "pitching")].append(
            _line(PID, season, level, 21, "pit", bb=36 + 4 * (season - 2012)))

    def fake(sport, season, group, *, fetch=True):
        return list(store.get((int(sport), int(season), group), []))
    monkeypatch.setattr(M, "fetch_season", fake)
    M.season_lines.cache_clear()
    M._norm_own.cache_clear()
    yield store
    M.season_lines.cache_clear()
    M._norm_own.cache_clear()


# ---------------------------------------------------------------------------
# 1. as of
# ---------------------------------------------------------------------------

def test_last_readable_season_is_the_milb_features_rule():
    assert M.last_readable_season(2017, "2017-01-01") == 2016
    assert M.last_readable_season(2019, "2018-07-15") == 2017
    assert M.last_readable_season(2019, "2018-10-02") == 2018
    assert M.last_readable_season(2019, None) == 2018


def test_a_line_after_the_read_never_moves_the_value(cache):
    before = M.profile(PID, 2017, "2017-01-01", "hit", 2005)
    assert before["_seasons"] == [2016, 2015, 2014]
    # change every line the read must not see: the 2017 and 2018 seasons
    for (sport, season, group), rows in cache.items():
        if season >= 2017:
            for r in rows:
                if r["mlbam"] == PID:
                    r.update({"bb": 300, "so": 1, "hr": 90, "go": 1, "ao": 400})
    M.season_lines.cache_clear()
    M._norm_own.cache_clear()
    after = M.profile(PID, 2017, "2017-01-01", "hit", 2005)
    for s in M.STATS:
        if M.STATS[s]["side"] == "hit":
            assert after[s] == pytest.approx(before[s]), s


def test_the_floor_and_max_seasons_bound_the_walk(cache):
    p = M.profile(PID, 2019, "2019-01-01", "pit", 2016)
    assert p["_seasons"] == [2018, 2017, 2016]
    p = M.profile(PID, 2019, "2019-01-01", "pit", 2018)
    assert p["_seasons"] == [2018]
    p = M.profile(PID, 2014, "2014-01-01", "pit", 2014)
    assert p["_seasons"] == [] and all(p[s] is None for s in M.STATS
                                       if M.STATS[s]["side"] == "pit")


def test_no_id_reads_none(cache):
    p = M.profile(None, 2017, "2017-01-01", "hit", 2005)
    assert all(p[s] is None for s in M.STATS if M.STATS[s]["side"] == "hit")


def test_lv_profiles_read_the_outcome_blind_id_at_the_window_start(cache):
    rows = [{"player_key": "x", "mlbam_id": PID, "record_mlbam_id": 1, "vintage": 2017,
             "window": ["2017-01-01", "2017-05-01"], "milb_floor": 2005},
            {"player_key": "y", "mlbam_id": None, "record_mlbam_id": PID, "vintage": 2017,
             "window": ["2017-01-01", "2017-05-01"], "milb_floor": 2005}]
    out = M.lv_profiles("hit", {"hit": {2017: (rows, [{}, {}])}})
    assert out[(2017, "x")]["_seasons"] == [2016, 2015, 2014]
    # the record's stored id is audit only: no outcome-blind id, no value
    assert out[(2017, "y")]["bb_hit"] is None


# ---------------------------------------------------------------------------
# 2. level and age relative
# ---------------------------------------------------------------------------

def test_a_line_on_its_level_season_age_line_reads_zero(cache):
    # 2016 A holds the flat population alone (the player of interest is at A+)
    nm = M.norm(2016, "A", "k_hit")
    assert nm is not None and nm["n"] == 40
    assert nm["b"] == pytest.approx(0.0, abs=1e-12)
    slot = {"counts": M._counts(_line(PID, 2016, "A", 20, "hit"), "hit"), "age": 20.0}
    rel, den = M.relative(slot, 2016, "A", "k_hit")
    assert rel == pytest.approx(0.0, abs=1e-12) and den == 400
    slot = {"counts": M._counts(_line(PID, 2016, "A", 20, "hit", bb=80), "hit"),
            "age": 20.0}
    rel, _ = M.relative(slot, 2016, "A", "bb_hit")
    assert rel == pytest.approx(0.1, abs=1e-12)


def test_the_value_is_shrunk_on_the_total_denominator(cache):
    p = M.profile(PID, 2017, "2017-01-01", "hit", 2016)
    assert p["_seasons"] == [2016]
    # one 400-PA line at A+ in 2016 with bb 80, age 21, against its level-season line
    nm = M.norm(2016, "A+", "bb_hit")
    rel = 80 / 400 - (nm["a"] + nm["b"] * 21)
    k = M.STATS["bb_hit"]["k"]
    assert p["bb_hit"] == pytest.approx(rel * 400 / (400 + k))


# ---------------------------------------------------------------------------
# 3. the arms and their registration
# ---------------------------------------------------------------------------

def test_the_arms_are_eight_skill_columns_registered_in_wave_two():
    names = [a["name"] for a in M.ARMS]
    assert names == ["w2m_bb_hit", "w2m_k_hit", "w2m_iso_hit", "w2m_hr_hit",
                     "w2m_air_hit", "w2m_bb_pit", "w2m_gb_pit", "w2m_hr_pit"]
    for a in M.ARMS:
        assert a["head"] == "skill" and a["side"] in F.SIDES and not a["retest"]
        assert a["column"]["source"] == "module" and a["column"]["arg"] == a["stat"]
    assert "efv_w2_milb" in LAB.WAVE2_ARM_MODULES
    assert set(names) <= {a["name"] for a in LAB.wave2_candidates()}
    # wave 1 is untouched
    assert [c["name"] for c in LAB.CANDIDATES][:2] == ["txt_skill_hit", "txt_skill_pit"]
    assert LAB.registration_echo()["family_size"] == 7


def test_the_lab_builds_an_arm_through_its_own_column_values(cache):
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2018,
             "window": ["2018-01-01", "2018-05-01"], "milb_floor": 2005}]
    frames = {"pit": {2018: (rows, [{}])}}
    arm = next(a for a in M.ARMS if a["name"] == "w2m_bb_pit")
    vals = LAB.column_values(arm, frames)
    assert set(vals) == {(2018, "x")} and vals[(2018, "x")] is not None
    with pytest.raises(ValueError):
        M.screen_column("bb_hit", "pit", frames)


def test_absent_families_are_named():
    for k in ("ld_rate", "pull_rate", "fb_rate_true", "prospects_db_milb"):
        assert k in M.ABSENT and M.ABSENT[k]


# ---------------------------------------------------------------------------
# 4. bans
# ---------------------------------------------------------------------------

def test_reserved_list_vintages_raise(cache):
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2020,
             "window": ["2020-01-01", "2020-05-01"], "milb_floor": 2005}]
    with pytest.raises(F.ReservedFrameError):
        M.lv_profiles("hit", {"hit": {2020: (rows, [{}])}})


def test_vm_profiles_never_read_a_reserved_cohort(cache):
    data = [{"player_key": "a", "decision_year": 2019},
            {"player_key": "b", "decision_year": F.R_VM_FIRST_DEBUT_YEAR}]
    raw = {"a": {"mlbam_id": PID, "cutoff": "2019-06-01"},
           "b": {"mlbam_id": PID, "cutoff": "2025-06-01"}}
    out = M.vm_profiles("hit", data, raw)
    assert set(out) == {"a"} and out["a"]["_seasons"] == [2018, 2017, 2016]


_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")
_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def test_no_consensus_level_grouping_no_exporter_no_emdash():
    """The lab's own scan of names and short strings (test_efv_screen_lab). The FV-grid
    integer scan is not applied: the exposure floors and stabilization points (60, 70,
    80) share those integers, and no grade is compared with any constant here."""
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED_TOKENS), name
            assert not fv_group.search(low), name
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & _SERVED_EXPORTERS, mods
    assert "—" not in src and "–" not in src
    # a column builder reads no label, WAR or debut
    for fn in ("profile", "lv_profiles", "vm_profiles", "season_lines", "screen_column"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            low = body.lower().replace("warm", "").replace("r_vm_first_debut_year", "")
            assert banned not in low, (fn, banned)


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def _artifact():
    if not M.OUT_PATH.exists():
        pytest.skip("development read not run on this tree")
    return json.loads(M.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_on_the_frozen_label():
    d = _artifact()
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["exploratory"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["label"]["id"].startswith("fwar@2026-10-02")
    assert d["lv_dev"]["frame"]["folds"] == [2017, 2018, 2019]
    assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in d["vm_dev"]["frame"]["fold_years"])
    assert all(p["mismatched_base_order"] == 0 for p in d["vm_dev"]["parity"].values())
    for side, by_stat in d["lv_dev"]["coverage"].items():
        for st, cov in by_stat.items():
            assert M.STATS[st]["side"] == side
            assert not ({"2020", "2021"} & set(cov)), (side, st)
    for a in M.ARMS:
        for fid in ("lv_dev", "vm_dev"):
            blk = d[fid]["arms"][a["name"]]["frame"]
            for comp in ("candidate_vs_efv_v2_base", "candidate_vs_prospx_consensus"):
                leg = blk["deltas"][comp]["spearman"]
                assert leg["delta"] is not None and len(leg["ci95"]) == 2


def test_the_ledger_rows_are_this_modules_development_rows():
    d = _artifact()
    docs = M.ledger_docs(d)
    assert len(docs) == 2 * len(M.ARMS)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(M.MODEL_PREFIX)
        assert doc["screening"]["exploratory"] is False
        assert len(doc["frames"]) == 1
