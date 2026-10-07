"""LIBRARY_14: paired, clustered intervals on the ten legs that printed "no
interval on record" (owner answer LB-Q4, 2026-10-02).

What these pin:
  * the shared bootstrap (gap_intervals) is paired, clustered, seeded and
    oriented so positive means the model is better;
  * write_beside never moves a point value: it refuses unless the rerun
    reproduces every protected block, and adds only the new keys;
  * every producer computes its block (synthetic rows, no data read);
  * each interval present in an artifact has lo <= point <= hi, its point is
    the gap between the champion and baseline values stored beside it, the
    rest of the artifact equals HEAD when the artifact was not regenerated,
    and the registry card names it (a written interval is never left unwired,
    and a card never names one its artifact lacks).
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

import gap_intervals as gi
import model_registry as mr
import model_updates as mu

HERE = Path(__file__).parent

# (model_id, leg, artifact, interval leg path, champion path, baseline path, better)
LEGS = [
    ("eta", 0, "data/eta_eval.json", "champion_on_baseline_rows.gap_ci_vs_naive.mae",
     "champion_on_baseline_rows.mae", "baseline_naive_level_table.mae", "lower"),
    ("eta", 1, "data/eta_eval.json", "champion_on_baseline_rows.gap_ci_vs_naive.within_1y",
     "champion_on_baseline_rows.within_1y", "baseline_naive_level_table.within_1y", "higher"),
    ("farm_grades", 0, "data/farm_grade_eval.json", "mean_spearman_gap_ci_vs_count.spearman",
     "mean_spearman.sum_surplus_mm", "mean_spearman.count", "higher"),
    ("ewar", 0, "data/ewar_eval.json", "gate_1_team_wins.gap_ci_vs_bwar.r",
     "gate_1_team_wins.ewar.r", "gate_1_team_wins.bwar.r", "higher"),
    ("ewar", 1, "data/ewar_eval.json", "gate_2_pitcher_persistence.gap_ci_vs_bwar_ra.r",
     "gate_2_pitcher_persistence.self_r_ewar_fip",
     "gate_2_pitcher_persistence.self_r_bwar_ra", "higher"),
    ("team_win_projections", 0, "data/team_outlook_eval.json",
     "retro_backtest.ship_decision.holdout_gap_ci_vs_prior_wins.mae",
     "retro_backtest.ship_decision.holdout_mae.served_recentered",
     "retro_backtest.ship_decision.holdout_mae.baseline_prior_wins", "lower"),
    ("mlb_projections_prospects", 0, "data/prospect_path_eval.json",
     "baseline_gap_ci_vs_challenger.spearman",
     "baseline_pooled_oos.spearman", "challenger_pooled_oos.spearman", "higher"),
    ("mlb_projections_prospects", 1, "data/prospect_path_eval.json",
     "baseline_gap_ci_vs_challenger.mae",
     "baseline_pooled_oos.mae", "challenger_pooled_oos.mae", "lower"),
    ("arb_award", 2, "data/arbitration_eval.json", "a6_swartz.gap_ci_vs_swartz.mdape",
     "a6_swartz.ours_mdape", "a6_swartz.swartz_mdape", "lower"),
    ("betting_game_prob", 1, "data/betting_model_eval.json",
     "benchmarks.tiers.market_open_devig.gap_ci_model_vs_market.brier",
     "benchmarks.tiers.market_open_devig.same_games.model",
     "benchmarks.tiers.market_open_devig.brier", "lower"),
]
#: The legs whose producer rerun reproduced the stored points on 2026-10-07,
#: so their interval was written beside them (tools/gap_intervals_beside.py).
WRITTEN = {("eta", 0), ("eta", 1), ("ewar", 0), ("ewar", 1), ("betting_game_prob", 1)}


def _doc(rel):
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def _get(doc, dotted):
    try:
        return mr._dig_path(doc, dotted)
    except KeyError:
        return None


def _rows():
    return {m["model_id"]: m for m in mr.load()["models"]}


# --------------------------------------------------------------------------- #
# the shared bootstrap
# --------------------------------------------------------------------------- #

def test_the_interval_is_paired_clustered_and_seeded():
    rng = np.random.default_rng(1)
    clusters = np.repeat(np.arange(40), 3)
    a = rng.normal(0, 1, 120)
    b = a + 0.5 + rng.normal(0, 0.2, 120)       # b is worse by about 0.5

    def gaps(idx):
        return {"mae": float(np.abs(b[idx]).mean() - np.abs(a[idx]).mean()),
                "same": 0.0 * float(idx.size)}

    one = gi.paired_cluster_interval(clusters, gaps, seed=7, cluster="test", b=400)
    two = gi.paired_cluster_interval(clusters, gaps, seed=7, cluster="test", b=400)
    assert one == two
    assert one["clusters"] == 40 and one["n"] == 120 and one["B"] == 400
    assert one["mae"]["lo95"] <= one["mae"]["point"] <= one["mae"]["hi95"]
    # a paired gap with no difference has a zero-width interval
    assert one["same"] == {"point": 0.0, "lo95": 0.0, "hi95": 0.0}
    with pytest.raises(ValueError):
        gi.paired_cluster_interval([], gaps, seed=7, cluster="test")


def test_spearman_matches_tie_averaged_ranks():
    x = np.array([1, 2, 2, 3, 5], float)
    y = np.array([2, 1, 4, 4, 9], float)
    rx, ry = gi._avg_ranks(x), gi._avg_ranks(y)
    assert list(rx) == [1, 2.5, 2.5, 4, 5]
    assert gi.spearman(x, y) == pytest.approx(np.corrcoef(rx, ry)[0, 1])
    assert gi.spearman(x[:2], y[:2]) is None
    assert gi.pearson(np.ones(5), y) is None


def test_write_beside_adds_only_the_new_key_and_refuses_a_moved_point(tmp_path):
    p = tmp_path / "eval.json"
    stored = {"generated_at": "2026-01-01", "block": {"mae": 1.5, "n": 10}, "other": [1, 2]}
    p.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    ci = {"mae": {"point": 0.1, "lo95": 0.0, "hi95": 0.2}, "B": 10}
    moved = {"block": {"mae": 1.6, "n": 10, "gap": ci}}
    with pytest.raises(RuntimeError, match="does not reproduce"):
        gi.write_beside(p, moved, ["block.gap"], protect=["block"])
    assert p.read_text(encoding="utf-8") == before
    fresh = {"generated_at": "2026-10-07", "block": {"mae": 1.5, "n": 10, "gap": ci}}
    assert gi.check_beside(p, fresh, ["block.gap"], protect=["block"]) == {"block.gap": ci}
    assert p.read_text(encoding="utf-8") == before
    gi.write_beside(p, fresh, ["block.gap"], protect=["block"])
    got = json.loads(p.read_text(encoding="utf-8"))
    assert got == {"generated_at": "2026-01-01", "block": {"mae": 1.5, "n": 10, "gap": ci},
                   "other": [1, 2]}
    # idempotent: a second write leaves the same bytes
    once = p.read_text(encoding="utf-8")
    gi.write_beside(p, fresh, ["block.gap"], protect=["block"])
    assert p.read_text(encoding="utf-8") == once


def test_write_beside_refuses_a_file_it_cannot_reserialise(tmp_path):
    p = tmp_path / "eval.json"
    p.write_text('{"block": {"mae": 1.5}}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="re-serialise"):
        gi.write_beside(p, {"block": {"mae": 1.5, "gap": {"B": 1}}}, ["block.gap"],
                        protect=["block"])


# --------------------------------------------------------------------------- #
# every producer computes its block (synthetic rows)
# --------------------------------------------------------------------------- #

def _ok(block, legs):
    for leg in legs:
        assert block[leg]["lo95"] <= block[leg]["point"] <= block[leg]["hi95"], (leg, block)
    assert block["B"] == gi.B and block["seed"] == gi.SEED


def test_eta_producer_block():
    import eta_backtest as E
    rng = np.random.default_rng(3)
    rows = [{"player_key": f"p{i % 60}", "actual": 2020, "pred": 2020 + int(rng.integers(-1, 2)),
             "naive": 2020 + int(rng.integers(-3, 4))} for i in range(150)]
    blk = E._gap_ci_vs_naive(rows)
    _ok(blk, ("mae", "within_1y"))
    assert blk["clusters"] == 60 and blk["mae"]["point"] > 0


def test_farm_producer_block():
    import farm_grade_backtest as F
    rng = np.random.default_rng(4)
    rows = []
    for vy in F.VINTAGE_YEARS:
        for o in range(30):
            real = float(rng.normal(20, 8))
            rows.append((f"o{o}", vy, real + float(rng.normal(0, 4)), int(rng.integers(20, 40)), real))
    blk = F._gap_ci_vs_count(rows)
    _ok(blk, ("spearman",))
    assert blk["clusters"] == 30 and blk["spearman"]["point"] > 0


def test_team_wins_producer_block():
    import proj_backtest as PB
    rng = np.random.default_rng(5)
    orgs = [f"T{i:02d}" for i in range(30)]
    act = {o: int(rng.integers(60, 100)) for o in orgs}
    served = {o: act[o] + float(rng.normal(0, 6)) for o in orgs}
    prior = {o: act[o] + float(rng.normal(0, 9)) for o in orgs}
    blk = PB._holdout_gap_ci(served, prior, act)
    _ok(blk, ("mae",))
    assert blk["clusters"] == 30


def test_prospect_path_producer_block():
    import prospect_path as PP
    rng = np.random.default_rng(6)
    obs = rng.normal(1, 1, 200)
    base = [(float(o + rng.normal(0, 1)), float(o)) for o in obs]
    chall = [(float(o + rng.normal(0, 2)), float(o)) for o in obs]
    blk = PP._gap_ci_vs_challenger(base, chall, [f"k{i}" for i in range(200)])
    _ok(blk, ("spearman", "mae"))


def test_betting_market_producer_block():
    import betting_model as B
    rng = np.random.default_rng(8)
    window = [{"game_pk": i, "date": f"2026-08-{1 + i // 10:02d}"} for i in range(200)]
    ys = {g["game_pk"]: int(rng.integers(0, 2)) for g in window}
    model = {pk: 0.5 for pk in ys}
    market = {pk: (0.6 if y else 0.4) for pk, y in ys.items()}
    blk = B._market_gap_ci(window, market, model, ys, sorted(ys))
    _ok(blk, ("brier",))
    assert blk["clusters"] == 20 and blk["brier"]["point"] < 0     # the market is better


def test_ewar_persistence_producer_block():
    import ewar
    rng = np.random.default_rng(9)
    rows = []
    for mid in range(80):
        skill = float(rng.normal(0, 1))
        for season in (2020, 2021, 2022):
            e = skill + float(rng.normal(0, 0.5))
            b = skill + float(rng.normal(0, 1.5))
            rows.append({"side": "pit", "mid": mid, "season": season, "ip": 100.0,
                         "praa_ewar": e * 100 / 9, "praa_bref": b * 100 / 9,
                         "ewar": e, "bwar": b, "pitch_src": "fip"})
    blk = ewar.persistence_gap_ci({"rows": rows})
    _ok(blk, ("r",))
    assert blk["clusters"] == 80 and blk["n"] == 160 and blk["r"]["point"] > 0


# --------------------------------------------------------------------------- #
# the artifacts and the cards
# --------------------------------------------------------------------------- #

def test_each_written_interval_exists_and_brackets_its_point():
    for mid, i, rel, leg, champ, base, better in LEGS:
        if (mid, i) not in WRITTEN:
            continue
        doc = _doc(rel)
        blk = _get(doc, leg)
        assert isinstance(blk, dict), f"{mid} leg {i}: no interval at {leg}"
        assert blk["lo95"] <= blk["point"] <= blk["hi95"], (mid, i, blk)
        parent = _get(doc, leg.rsplit(".", 1)[0])
        assert parent["B"] == gi.B and parent["cluster"] and parent["clusters"] > 1


def test_each_interval_point_is_the_gap_between_the_points_beside_it():
    """The interval was measured on the stored rows: its point (unrounded
    arithmetic) equals the gap between the stored champion and baseline, which
    carry 3 or 4 decimals, to that rounding."""
    for mid, i, rel, leg, champ, base, better in LEGS:
        doc = _doc(rel)
        blk = _get(doc, leg)
        if blk is None:
            continue
        c, b = _get(doc, champ), _get(doc, base)
        gap = (b - c) if better == "lower" else (c - b)
        assert abs(gap - blk["point"]) <= 0.0011, (mid, i, gap, blk["point"])


def _head_doc(rel):
    try:
        out = subprocess.run(["git", "show", f"HEAD:prospect-tracker/{rel}"], cwd=HERE,
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return json.loads(out.stdout.decode("utf-8"))


def _strip(doc, keys):
    doc = json.loads(json.dumps(doc))
    for k in keys:
        parent, _, leaf = k.rpartition(".")
        holder = _get(doc, parent) if parent else doc
        if isinstance(holder, dict):
            holder.pop(leaf, None)
    return doc


def test_the_point_values_are_unchanged_against_head():
    """Adding an interval moves nothing else: once its interval keys are set
    aside an artifact equals HEAD's, unless it was regenerated since (its
    generated_at moved), when a rescore is a different event."""
    blocks = {}
    for mid, i, rel, leg, *_ in LEGS:
        blocks.setdefault(rel, set()).add(leg.rsplit(".", 1)[0])
    checked = 0
    for rel, keys in blocks.items():
        head = _head_doc(rel)
        if head is None:
            continue
        cur = _doc(rel)
        if cur.get("generated_at") != head.get("generated_at"):
            continue
        assert _strip(cur, keys) == _strip(head, keys), rel
        checked += 1
    if checked == 0:
        pytest.skip("no artifact comparable with HEAD (git unavailable or all regenerated)")


def test_every_interval_on_record_is_wired_and_no_card_names_a_missing_one():
    rows = _rows()
    for mid, i, rel, leg, *_ in LEGS:
        doc = _doc(rel)
        hs = rows[mid]["card"]["derived_from"]["headline"][i]
        want = {"lo": f"{leg}.lo95", "hi": f"{leg}.hi95"}
        if isinstance(_get(doc, leg), dict):
            assert hs.get("gap_ci") == want, (
                f"{mid} leg {i}: {rel} carries {leg} but the card does not name it")
        else:
            assert "gap_ci" not in hs, f"{mid} leg {i}: the card names an interval {rel} lacks"
    assert {(mid, i) for mid, i, rel, leg, *_ in LEGS
            if isinstance(_get(_doc(rel), leg), dict)} >= WRITTEN


def test_the_wired_cards_resolve_and_print_an_interval_edge():
    rows = _rows()
    for mid in {mid for mid, _ in WRITTEN}:
        m = rows[mid]
        assert mr.derive_card(m) == m["card"], mid
        legs = mu.card_legs(m, _doc(m["eval_artifact"]))
        for (wmid, i) in WRITTEN:
            if wmid != mid:
                continue
            lg = legs[i]
            assert lg is not None and lg["ci95"] is not None, (mid, i)
            assert lg["ci95"][0] <= lg["ci95"][1]
            assert "no interval on record" not in lg["edge_text"], (mid, i, lg["edge_text"])
            assert lg["edge_state"] in ("lead", "tie", "trails"), (mid, i)
