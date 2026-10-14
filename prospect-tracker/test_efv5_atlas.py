# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV v5 metric atlas (efv5_atlas.py, EFV5_METRIC_ATLAS).

1. Statistics: the AUC agrees with the rank formula and the weighted AUC at unit
   weights; the within-season Spearman agrees with scipy; the out-of-fold lift finds
   a planted signal and reads about zero on noise; BH q is monotone.
2. As of: a player with a MLB line at or before S is no row at S; labels resolve by
   the declared rule; the label window's last debut year sets the reserved flag.
3. Bans: the reserved list vintages are never in CONSENSUS_VINTAGES; nothing groups
   by consensus-FV level; no served exporter, backtest or fetch outside the module's
   own cache; the fetch refuses the nightly window; no em-dash.
4. The artifact, when present: development only, nothing served, no FV cell, no
   em-dash, the declared constants are the module's, every candidate meets the rule.
No test touches the network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv5_atlas as A  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

SRC = ROOT / "efv5_atlas.py"
TEST_SRC = Path(__file__)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def _auc_pairs(score, pos):
    s, p = np.asarray(score, float), np.asarray(pos, bool)
    tot = n = 0.0
    for i in np.flatnonzero(p):
        for j in np.flatnonzero(~p):
            tot += 1.0 if s[i] > s[j] else (0.5 if s[i] == s[j] else 0.0)
            n += 1
    return tot / n


def test_auc_matches_pair_count_and_weighted_unit():
    rng = np.random.default_rng(3)
    s = np.round(rng.normal(size=60), 1)              # ties on purpose
    y = (rng.uniform(size=60) < 1 / (1 + np.exp(-s))).astype(float)
    a = A.auc(s, y)
    assert a == pytest.approx(_auc_pairs(s, y), abs=1e-12)
    W = np.ones((3, 60))
    assert np.allclose(A.auc_weighted(s, y, W), a)
    # a row counted twice equals the row duplicated
    W2 = np.ones((1, 60))
    W2[0, 5] = 2.0
    dup = A.auc(np.r_[s, s[5]], np.r_[y, y[5]])
    assert A.auc_weighted(s, y, W2)[0] == pytest.approx(dup, abs=1e-12)


def test_within_rho_matches_scipy_and_unit_weights():
    scipy_stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(5)
    n = 80
    x = rng.normal(size=n)
    y = 0.5 * x + rng.normal(size=n)
    season = np.r_[np.full(40, 2015), np.full(40, 2016)]
    r1 = scipy_stats.spearmanr(x[:40], y[:40]).correlation
    r2 = scipy_stats.spearmanr(x[40:], y[40:]).correlation
    assert A.within_rho(x, y, season) == pytest.approx((r1 + r2) / 2.0, abs=1e-12)
    W = np.ones((4, n))
    assert np.allclose(A.within_rho(x, y, season, W), (r1 + r2) / 2.0)
    # a season under the floor is left out
    season2 = np.r_[np.full(70, 2015), np.full(10, 2016)]
    r_big = scipy_stats.spearmanr(x[:70], y[:70]).correlation
    assert A.within_rho(x, y, season2) == pytest.approx(r_big, abs=1e-12)


def test_bh_q_monotone_and_bounded():
    ps = [0.001, 0.01, 0.04, 0.2, None, 0.5]
    q = A.bh_q(ps)
    assert q[4] is None
    vals = [q[i] for i in (0, 1, 2, 3, 5)]
    assert vals == sorted(vals)
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert q[0] == pytest.approx(0.005, abs=1e-9)        # 0.001 x 5 / 1
    assert q[5] == pytest.approx(0.5, abs=1e-9)


def _table(rng, n=600, signal=1.0):
    pid = np.arange(n) // 2                    # two rows per player
    season = 2014 + (np.arange(n) % 3)
    c = rng.normal(size=n)
    m = rng.normal(size=n)
    z = 0.8 * c + signal * m - 0.5
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-z))).astype(float)
    rows = [{"pid": int(pid[i]), "season": int(season[i]), "level": "A", "band": "all",
             "group": None, "fv": 50.0 + 5.0 * float(c[i]),
             "m": {"k_pct_pit": float(m[i])},
             "y": {lb: (float(y[i]) if lb == "reach3" else None) for lb in A.LABELS}}
            for i in range(n)]
    return A.Table("pit", rows, ["k_pct_pit"])


def test_oof_lift_finds_signal_and_not_noise():
    rng = np.random.default_rng(11)
    T = _table(rng, signal=1.0)
    folds = A.player_folds(T.pid)
    assert set(np.unique(folds)) == set(range(A.FOLDS))
    # a player's rows share a fold
    for p in np.unique(T.pid)[:20]:
        assert np.unique(folds[T.pid == p]).size == 1
    mask = np.ones(T.n, dtype=bool)
    r = A.score_cell(T, mask, "k_pct_pit", "reach3", B=100, seed=1, folds_all=folds)
    lst = r["listed"]
    assert lst["delta"] > 0.05 and lst["ci95"][0] > 0
    assert lst["model_cm"] > lst["model_c"] > 0.5
    assert r["full"]["players"] == 300 and r["full"]["n"] == 600
    T0 = _table(np.random.default_rng(12), signal=0.0)
    r0 = A.score_cell(T0, mask, "k_pct_pit", "reach3", B=100, seed=1, folds_all=A.player_folds(T0.pid))
    assert abs(r0["listed"]["delta"]) < 0.03
    assert r0["listed"]["ci95"][0] <= 0.0 <= r0["listed"]["ci95"][1]


def test_minimum_cell_refuses_small_cells():
    pid = np.arange(A.MIN_PLAYERS - 1)
    y = np.r_[np.ones(A.MIN_POS), np.zeros(pid.size - A.MIN_POS)]
    assert not A.enough(pid, y, "binary")
    pid = np.arange(A.MIN_PLAYERS)
    y = np.r_[np.ones(A.MIN_POS - 1), np.zeros(pid.size - A.MIN_POS + 1)]
    assert not A.enough(pid, y, "binary")
    y = np.r_[np.ones(A.MIN_POS), np.zeros(pid.size - A.MIN_POS)]
    assert A.enough(pid, y, "binary")
    assert A.enough(pid, y, "rank")
    assert A.MIN_PLAYERS == 150 and A.MIN_POS == 30


# ---------------------------------------------------------------------------
# as of, labels, groups
# ---------------------------------------------------------------------------

def test_labels_resolve_by_the_declared_rule():
    H = A.HORIZON
    war = {(7, H - 4): 1.0, (7, H - 3): 2.0, (7, H - 2): 3.0, (7, H - 1): 4.0, (7, H): 5.0}
    mlb = {7: {H - 4, H - 3, H - 2, H - 1, H}, 8: {2012}}
    # a line at or before S: not a row
    assert A.labels_for_row(8, 2012, mlb, war) is None
    assert A.labels_for_row(8, 2015, mlb, war) is None
    S = H - 6                                   # first line at S + 2
    lab = A.labels_for_row(7, S, mlb, war)
    assert lab["reach3"] == 1.0 and lab["reach5"] == 1.0 and lab["reach_h"] == 1.0
    assert lab["w3"] == pytest.approx(6.0)      # the first three seasons
    assert lab["l6"] is None                    # S + 8 > H
    assert lab["war_rate_h"] == pytest.approx(15.0 / 5)
    # first line at S + 4: within 5, not within 3; w3 is 0 without a debut in window
    S = H - 8
    lab = A.labels_for_row(7, S, mlb, war)
    assert lab["reach3"] == 0.0 and lab["reach5"] == 1.0 and lab["w3"] == 0.0
    assert lab["l6"] == 0.0
    # never reached
    lab = A.labels_for_row(9, 2010, mlb, war)
    assert lab["reach3"] == 0.0 and lab["l6"] == 0.0 and lab["war_rate_h"] == 0.0
    # unresolved windows read None
    lab = A.labels_for_row(9, H - 2, mlb, war)
    assert lab["reach3"] is None and lab["reach5"] is None and lab["reach_h"] == 0.0


def test_label_window_sets_the_reserved_flag():
    first = F.R_VM_FIRST_DEBUT_YEAR
    assert A.label_max_debut("reach3", first - 4) == first - 1
    assert A.label_max_debut("reach3", first - 3) == first
    assert A.label_max_debut("reach5", first - 6) == first - 1
    assert A.label_max_debut("reach_h", 2015) == A.HORIZON
    assert A.label_max_debut("l6", A.LABELS["l6"]["max_s"]) < first


def test_label_frames_keep_the_clean_frame_before_the_reserved_cohort():
    first = F.R_VM_FIRST_DEBUT_YEAR
    season = np.array([2015, 2019, 2021, 2022, 2023])
    frames = dict(A.label_frames("reach3", season))
    assert set(frames) == {"all", "clean"} and frames["all"].all()
    assert frames["clean"].tolist() == [True, True, True, False, False]
    assert A.label_max_debut("reach3", first - 1 - 3) < first
    frames = dict(A.label_frames("reach5", season))
    assert frames["clean"].tolist() == [True, True, False, False, False]
    for lb in ("w3", "l6", "reach_h", "war_rate_h"):
        assert [f for f, _m in A.label_frames(lb, season)] == ["all"]
    assert A.label_max_debut("w3", A.LABELS["w3"]["max_s"]) < first


def test_position_groups_and_role_rule():
    assert A.position_group("SS/2B") == "SS"
    assert A.position_group("OF") == "COF"
    assert A.position_group("CF") == "CF"
    assert A.position_group("3B") == "IF"
    assert A.position_group("1B/OF") == "1B/DH"
    assert A.position_group("TWP") is None
    assert A.position_group("RHP") is None
    assert A.RP_GS_SHARE == 0.5
    assert set(A.POS_GROUP.values()) == set(A.HIT_GROUPS) - {"all"}


def test_rates_from_counts():
    h = A.hit_rates({"pa": 100.0, "ab": 90.0, "h": 27.0, "doubles": 5.0, "triples": 1.0, "hr": 4.0,
                     "so": 20.0, "bb": 8.0, "hbp": 1.0, "sf": 1.0, "ibb": 0.0, "sb": 3.0,
                     "go": 30.0, "ao": 20.0})
    assert h["k_pct"] == pytest.approx(0.2) and h["bb_minus_k"] == pytest.approx(-0.12)
    assert h["iso"] == pytest.approx((5 + 2 + 12) / 90)
    assert h["babip"] == pytest.approx(23 / (90 - 20 - 4 + 1))
    assert h["gb_pct"] == pytest.approx(0.6)
    p = A.pit_rates({"bf": 200.0, "so": 50.0, "bb": 20.0, "g": 10.0, "gs": 2.0, "hr": 4.0,
                     "go": 60.0, "ao": 40.0, "outs": 150.0, "er": 10.0})
    assert p["k_minus_bb"] == pytest.approx(0.15)
    assert p["gs_share"] == pytest.approx(0.2) and p["gb_pct"] == pytest.approx(0.6)
    assert p["era"] == pytest.approx(10.0 * 27 / 150)


def test_chart_mapping_names_pitcher_metrics():
    for label, metric, sign, val in A.CHART:
        assert sign in (1, -1) and 0 < val < 100
        if metric is not None:
            assert metric in A.METRICS and A.METRICS[metric][1] == "pit"
    assert sum(1 for c in A.CHART if c[1] is None) == 2        # Pitching+, Location+


# ---------------------------------------------------------------------------
# bans
# ---------------------------------------------------------------------------

def test_reserved_vintages_never_built():
    assert set(A.CONSENSUS_VINTAGES).isdisjoint(F.RESERVED_LV)
    assert max(A.CONSENSUS_VINTAGES) <= 2026 and min(A.CONSENSUS_VINTAGES) >= 2011


def test_source_bans():
    src = SRC.read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2014) not in TEST_SRC.read_text(encoding="utf-8")
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    assert not fv_group.search(src)
    assert not re.search(r"fv_cell|fv_tier|fv_bucket|FV cell\b(?! level)", src.replace("FV cell)", "").replace("by FV level", ""))
    for banned in ("import backtest", "run_backtest", "import efv_export", "import proj_export",
                   "train_proj_models", "import efv_score", "import storage"):
        assert banned not in src, banned
    # the only fetch target is the module's own cache folder
    assert "PROFILE_DIR = ROOT / \".cache\" / \"efv5_profile\"" in src
    assert "MILB_PROFILE_DIR" in src and "milb_profile\"" in src
    assert src.count("urlopen") == 1


def test_fetch_refuses_blackout_and_writes_only_its_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PROFILE_DIR", tmp_path / "own")
    monkeypatch.setattr(A, "MILB_PROFILE_DIR", tmp_path / "theirs")
    monkeypatch.setattr(A, "in_blackout", lambda now=None: True)
    with pytest.raises(RuntimeError):
        A.fetch_profile(14, 2024, "pitching", opener=lambda url: b"{}")
    monkeypatch.setattr(A, "in_blackout", lambda now=None: False)
    payload = {"stats": [{"totalSplits": 1, "splits": [
        {"player": {"id": 5}, "league": {"name": "FSL"},
         "stat": {"age": 22, "strikeOuts": 9, "baseOnBalls": 3, "homeRuns": 1,
                  "groundOuts": 10, "airOuts": 8, "hitByPitch": 1, "battersFaced": 60}}]}]}
    n = A.fetch_profile(14, 2024, "pitching", opener=lambda url: json.dumps(payload).encode())
    assert n == 1
    assert (tmp_path / "own" / "pitching_14_2024.json").exists()
    assert not (tmp_path / "theirs").exists()
    rows = A.profile_rows("pitching", 14, 2024)
    assert rows[0]["go"] == 10 and rows[0]["level"] == "A"
    # a present file is never refetched
    assert A.fetch_profile(14, 2024, "pitching", opener=lambda url: (_ for _ in ()).throw(AssertionError())) == 0


def test_blackout_window():
    from datetime import datetime, timezone
    assert A.in_blackout(datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc))
    assert not A.in_blackout(datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc))
    assert not A.in_blackout(datetime(2026, 10, 14, 5, 59, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# the artifact, when present
# ---------------------------------------------------------------------------

def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@pytest.fixture(scope="module")
def artifact():
    if not A.OUT_PATH.exists():
        pytest.skip("artifact not built")
    return json.loads(A.OUT_PATH.read_text(encoding="utf-8"))


def test_artifact_is_development_only(artifact):
    assert artifact["schema"] == A.SCHEMA and artifact["item"] == A.ITEM
    assert artifact["role"] == "development" and artifact["served"] is False
    d = artifact["declared"]
    assert d["min_players"] == A.MIN_PLAYERS and d["min_pos"] == A.MIN_POS
    assert d["seed"] == A.SEED and d["folds"] == A.FOLDS
    assert d["reserved_lv_never_built"] == sorted(F.RESERVED_LV)
    assert set(d["consensus_vintages"]).isdisjoint(F.RESERVED_LV)
    assert artifact["inputs"]["fwar_vintage_id"].startswith("2026-10-02")


def test_artifact_names_no_fv_cell_and_no_emdash(artifact):
    cell = re.compile(r"\bfv\s*_?\s*(35|40|45|50|55|60|65|70|80)\b", re.I)
    for s in _strings(artifact):
        assert chr(0x2014) not in s
        assert not cell.search(s), s
    for key in ("groups", "top_by_group", "candidates"):
        assert "fv" not in json.dumps(artifact[key]).lower().replace("consensus_raw", "")


def test_artifact_candidates_meet_the_rule(artifact):
    for c in artifact["candidates"]:
        assert c["incr"] > 0 and c["ci95"][0] > 0 and c["q"] <= A.CANDIDATE_Q
        assert c["metric"] in A.METRICS and c["status"] in ("clean", "spent-overlap")
        assert c["frame"] in ("all", "clean")
        if c["frame"] == "clean":
            assert c["status"] == "clean"
        assert c["players"] >= A.MIN_PLAYERS
    spans = artifact["chart_replication"]["spans"]
    assert artifact["chart_replication"]["primary"] in spans
    for ch in spans.values():
        assert ch["frame"]["side"] == "pit" and ch["spent"] == A.SPENT_NOTE
        names = [r["chart_label"] for r in ch["rows"]]
        assert names == [c[0] for c in A.CHART]


def test_cells_file_matches_columns(artifact):
    p = ROOT / artifact["cells_file"]
    if not p.exists():
        pytest.skip("cells file not built")
    cells = json.loads(p.read_text(encoding="utf-8"))
    assert cells["columns"] == list(A.CELL_COLUMNS)
    assert len(cells["rows"]) == artifact["tests"]
    cols = {c: i for i, c in enumerate(cells["columns"])}
    for row in cells["rows"][:5000]:
        assert len(row) == len(A.CELL_COLUMNS)
        assert row[cols["level"]] in A.LEVELS and row[cols["label"]] in A.LABELS
        assert row[cols["metric"]] in A.METRICS and row[cols["family"]] == A.METRICS[row[cols["metric"]]][0]
        s_full, s_listed = row[cols["seasons_full"]], row[cols["seasons_listed"]]
        s_max = max(s[1] for s in (s_full, s_listed) if s)
        assert row[cols["reserved_overlap"]] == (A.label_max_debut(row[cols["label"]], s_max)
                                                 >= F.R_VM_FIRST_DEBUT_YEAR)
        if row[cols["frame"]] == "clean":
            assert row[cols["reserved_overlap"]] is False
        if row[cols["players_full"]] is not None:
            assert row[cols["players_full"]] >= A.MIN_PLAYERS
        if row[cols["players_listed"]] is not None:
            assert row[cols["players_listed"]] >= A.MIN_PLAYERS
