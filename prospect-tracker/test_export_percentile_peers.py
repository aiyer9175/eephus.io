# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the export's percentile-peer hoist and the shallow statcast copies
(perf(export), 2026-10-03).

Until then export_timeseries_json deep-copied every statcast payload (1.46 GB of
JSON, pitch_plot dominating) to rewrite only the contact_quality blocks, and the
statcast contact normalizer rebuilt its peer-value list inside the row loop
(O(rows^2 x metrics)). The zone twin in zone_metrics._attach_level_percentiles
had the same shape. These tests pin that the rewrite moves no number:

  * the hoisted normalizer equals a verbatim copy of the deep-copy version on a
    recorded cohort (dict equality, floats exact);
  * the bisect rank equals the linear count on ties, mixed ints, -0.0 and NaN;
  * the input payloads are unchanged after a full export (the guarantee the
    deepcopy existed for) while the heavy blocks are shared by reference;
  * zone_metrics._attach_level_percentiles equals its row-loop predecessor.
"""

from __future__ import annotations

import copy
import json
import lzma
import math
import random
from dataclasses import asdict
from pathlib import Path

import storage
import zone_metrics

FIXTURE = Path(__file__).parent / "test_fixtures" / "statcast_contact_cohort_2026-10-03.json.xz"


def _load_cohort() -> dict[str, dict]:
    with lzma.open(FIXTURE, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))["payloads"]


# ---------------------------------------------------------------------------
# the predecessor, verbatim (deepcopy + per-row peer rebuild + linear count)
# ---------------------------------------------------------------------------

def _legacy_num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _legacy_rank(value, values, higher_is_better):
    if not values:
        return 0.0
    if higher_is_better:
        count = sum(1 for v in values if v <= value)
    else:
        count = sum(1 for v in values if v >= value)
    return round(100.0 * count / len(values), 1)


def _legacy_contact_metric(cq, metric):
    if metric == "pull_air_pct":
        return _legacy_num((cq.get("spray") or {}).get("pull_air_pct"))
    return _legacy_num(cq.get(metric))


def _legacy_normalize(scm_by_key):
    out = copy.deepcopy(scm_by_key or {})
    rows_by_level_side = {}
    seen = set()
    for key, payload in out.items():
        if not isinstance(payload, dict):
            continue
        rows = payload.get("level_splits") or [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            level = row.get("level")
            if not level:
                continue
            is_pitcher = bool(row.get("is_pitcher"))
            dedupe_key = (key, level, is_pitcher)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cq = row.get("contact_quality") or {}
            bbe = int(cq.get("batted_balls") or 0)
            cq["qualified"] = bool(bbe >= storage._STATCAST_CONTACT_MIN_BBE)
            cq["qualifier_min_bbe"] = storage._STATCAST_CONTACT_MIN_BBE
            cq["percentile_sample_size"] = None
            cq["percentiles"] = {}
            if cq["qualified"]:
                rows_by_level_side.setdefault((level, is_pitcher), []).append(row)

    for (_level, is_pitcher), level_rows in rows_by_level_side.items():
        metric_directions = (
            storage._STATCAST_PITCHER_CONTACT_PERCENTILE_METRICS
            if is_pitcher else storage._STATCAST_HITTER_CONTACT_PERCENTILE_METRICS
        )
        n = len(level_rows)
        for row in level_rows:
            cq = row.get("contact_quality") or {}
            cq["percentile_sample_size"] = n
            for metric, higher_is_better in metric_directions.items():
                value = _legacy_contact_metric(cq, metric)
                if value is None:
                    continue
                vals = [
                    _legacy_contact_metric(peer.get("contact_quality") or {}, metric)
                    for peer in level_rows
                ]
                vals = [v for v in vals if v is not None]
                if len(vals) < 5:
                    continue
                cq["percentiles"][metric] = _legacy_rank(value, vals, higher_is_better)

    for payload in out.values():
        if not isinstance(payload, dict):
            continue
        split_map = {
            (row.get("level"), bool(row.get("is_pitcher"))): row
            for row in payload.get("level_splits") or []
            if isinstance(row, dict)
        }
        own_key = (payload.get("level"), bool(payload.get("is_pitcher")))
        normalized_primary = split_map.get(own_key)
        if normalized_primary:
            payload["contact_quality"] = copy.deepcopy(normalized_primary.get("contact_quality") or {})
    return out


def _legacy_zone_attach(rows):
    by_level_side = {}
    for row in rows.values():
        if row.pitches >= zone_metrics.PERCENTILE_MIN_PITCHES:
            by_level_side.setdefault((row.level, row.is_pitcher), []).append(row)
    for (_level, is_pitcher), level_rows in by_level_side.items():
        n = len(level_rows)
        metric_directions = (zone_metrics.PITCHER_PERCENTILE_METRICS if is_pitcher
                             else zone_metrics.HITTER_PERCENTILE_METRICS)
        for row in level_rows:
            row.qualified = True
            row.percentile_sample_size = n
            for metric, higher_is_better in metric_directions.items():
                value = getattr(row, metric)
                if value is None:
                    continue
                vals = [getattr(peer, metric) for peer in level_rows
                        if getattr(peer, metric) is not None]
                row.percentiles[metric] = _legacy_rank(value, vals, higher_is_better)


# ---------------------------------------------------------------------------
# the recorded cohort
# ---------------------------------------------------------------------------

def test_hoisted_normalizer_equals_the_deepcopy_version_on_the_recorded_cohort():
    cohort = _load_cohort()
    assert len(cohort) >= 1000, "fixture lost its cohort"
    legacy = _legacy_normalize(copy.deepcopy(cohort))
    hoisted = storage._normalize_statcast_contact_percentiles_for_export(cohort)

    assert hoisted == legacy
    assert set(hoisted) == set(cohort)
    ranked = sum(1 for p in hoisted.values()
                 for row in (p.get("level_splits") or [p])
                 if (row.get("contact_quality") or {}).get("percentiles"))
    assert ranked > 1000, f"only {ranked} rows ranked; the cohort is not exercising the pass"
    # float values compared exactly, not within a tolerance
    for key, payload in hoisted.items():
        for row, lrow in zip(payload.get("level_splits") or [payload],
                             legacy[key].get("level_splits") or [legacy[key]]):
            pc = (row.get("contact_quality") or {}).get("percentiles") or {}
            lpc = (lrow.get("contact_quality") or {}).get("percentiles") or {}
            assert list(pc.items()) == list(lpc.items())


def test_hoisted_normalizer_leaves_the_input_alone_and_shares_heavy_blocks():
    cohort = _load_cohort()
    keys = sorted(cohort)[:40]
    sample = {k: cohort[k] for k in keys}
    plot = {"points": [{"px": 0.1, "pz": 2.9, "tj_stuff_plus": 101.2}] * 3}
    moves = {"outings": [{"g": 1}], "pitches": {"FF": {"ivb": 17.1}}}
    for p in sample.values():
        p["pitch_plot"] = plot
        p["pitch_movement"] = moves
        for row in p.get("level_splits") or []:
            row["pitch_plot"] = plot
            (row.get("contact_quality") or {}).setdefault("hit_locations", [{"x": 1.0}])
    frozen = copy.deepcopy(sample)

    out = storage._normalize_statcast_contact_percentiles_for_export(sample)

    assert sample == frozen, "the normalizer wrote into its input"
    for k in keys:
        assert out[k] is not sample[k]
        assert out[k]["pitch_plot"] is sample[k]["pitch_plot"], "pitch_plot must be shared, not copied"
        assert out[k]["pitch_movement"] is sample[k]["pitch_movement"]
        assert out[k]["contact_quality"] is not sample[k]["contact_quality"]
        for row, src in zip(out[k]["level_splits"], sample[k]["level_splits"]):
            assert row is not src and row["pitch_plot"] is src["pitch_plot"]
            if isinstance(src.get("contact_quality"), dict):
                assert row["contact_quality"] is not src["contact_quality"]
                assert row["contact_quality"].get("hit_locations") is src["contact_quality"].get("hit_locations")
    # the top-level block owns its percentiles dict (the export writes into it later)
    for k in keys:
        top = out[k]["contact_quality"]
        prim = next((r for r in out[k]["level_splits"]
                     if (r.get("level"), bool(r.get("is_pitcher"))) ==
                     (out[k].get("level"), bool(out[k].get("is_pitcher")))), None)
        if prim is not None and isinstance(prim.get("contact_quality"), dict) and "percentiles" in top:
            assert top is not prim["contact_quality"]
            assert top["percentiles"] is not prim["contact_quality"]["percentiles"]
            assert top == prim["contact_quality"]


# ---------------------------------------------------------------------------
# the rank itself
# ---------------------------------------------------------------------------

def _rank_cases():
    rng = random.Random(20261003)
    cases = []
    for _ in range(60):
        n = rng.randint(1, 40)
        pool = [round(rng.uniform(-5, 105), rng.choice((0, 1, 3))) for _ in range(n)]
        pool += rng.sample(pool, k=min(len(pool), rng.randint(0, 5)))     # ties
        if rng.random() < 0.3:
            pool.append(int(pool[0]))                                     # an int among floats
        if rng.random() < 0.2:
            pool += [0.0, -0.0]
        probes = pool[:3] + [min(pool) - 1, max(pool) + 1, rng.uniform(-5, 105)]
        cases.append((pool, probes))
    cases.append(([1.0, 2.0, 3.0], [math.nan]))
    cases.append(([1.0, math.nan, 3.0], [2.0, math.nan, 3.0]))
    cases.append(([math.inf, 1.0, -math.inf], [1.0, math.inf, -math.inf, 0.0]))
    return cases


def test_storage_bisect_rank_equals_the_linear_count():
    for pool, probes in _rank_cases():
        sorted_vals = storage._sorted_peers(pool)
        if any(v != v for v in pool):
            assert sorted_vals is None, "a NaN peer must fall back to the linear count"
        for value in probes:
            for hib in (True, False):
                assert storage._percentile_rank_100(value, pool, hib, sorted_vals) == \
                    _legacy_rank(value, pool, hib), (pool, value, hib)
    assert storage._percentile_rank_100(1.0, [], True, []) == 0.0


def test_zone_bisect_rank_equals_the_linear_count():
    for pool, probes in _rank_cases():
        sorted_vals = zone_metrics._sorted_peers(pool)
        for value in probes:
            for hib in (True, False):
                assert zone_metrics._percentile_rank(value, pool, hib, sorted_vals) == \
                    _legacy_rank(value, pool, hib), (pool, value, hib)


# ---------------------------------------------------------------------------
# zone_metrics._attach_level_percentiles
# ---------------------------------------------------------------------------

def _zrow(i, level, is_pitcher, pitches, rng):
    def m():
        return None if rng.random() < 0.12 else round(rng.uniform(10, 90), 1)
    return zone_metrics.ZoneMetricRow(
        player_key=f"p{i}", player_name=f"P {i}", mlbam_id=i, season=2026, level=level,
        is_pitcher=is_pitcher, leagues=["x"], games=10, pitches=pitches,
        actual_zone_accuracy=None, actual_in_zone_accuracy=None,
        zone_rate=m(), z_swing_pct=m(), o_swing_pct=m(), z_contact_pct=m(),
        o_contact_pct=m(), overall_contact_pct=m(), whiff_pct=m(),
        actual_zone_rate=None, actual_z_swing_pct=None, actual_o_swing_pct=None,
        actual_z_contact_pct=None, actual_o_contact_pct=None,
        source="test", fetched_at="2026-10-03",
    )


def test_zone_attach_level_percentiles_equals_its_row_loop_predecessor():
    rng = random.Random(7)
    rows = {}
    for i in range(240):
        level = rng.choice(["AAA", "AA", "A"])
        is_pitcher = rng.random() < 0.5
        pitches = rng.choice([40, 99, 100, 101, 250, 900])
        rows[(f"p{i}", level)] = _zrow(i, level, is_pitcher, pitches, rng)
    # a tie cohort: identical values across several rows
    for i in range(240, 252):
        r = _zrow(i, "AA", True, 500, rng)
        r.zone_rate, r.whiff_pct = 50.0, 25.0
        rows[(f"p{i}", "AA")] = r
    legacy_rows = copy.deepcopy(rows)

    _legacy_zone_attach(legacy_rows)
    zone_metrics._attach_level_percentiles(rows)

    assert [asdict(r) for r in rows.values()] == [asdict(r) for r in legacy_rows.values()]
    assert any(r.percentiles for r in rows.values())
    assert any(not r.qualified for r in rows.values()), "the sub-threshold rows must stay unqualified"


# ---------------------------------------------------------------------------
# the full export: inputs untouched, outputs stripped
# ---------------------------------------------------------------------------

def _statcast_payload(key: str) -> dict:
    plot = {"points": [{"px": 0.3, "pz": 2.1, "tj_stuff_plus": 104.0,
                        "tj_stuff_plus_model": "tjstuff_plus_2020_2023_lgbm",
                        "ax_mirrored": 8.0}]}
    cq = {"batted_balls": 44, "avg_ev": 88.1, "max_ev": 108.2, "p90_ev": 103.0,
          "hard_hit_pct": 40.9, "barrel_pct": 9.1, "xwoba_est": 0.321, "xwobacon_est": 0.355,
          "spray": {"pull_air_pct": 18.2}, "direction": "pull",
          "hit_locations": [{"x": 125.0, "y": 90.0, "launch_speed": 101.0}],
          "rolling_xwoba": [0.3, 0.31]}
    return {
        "player_key": key, "player_name": "Arm One", "mlbam_id": 1, "season": 2026,
        "level": "AAA", "is_pitcher": True, "source": "mlb_stats_api",
        "fetched_at": "2026-10-01T00:00:00", "coverage": {"games": 9},
        "contact_quality": copy.deepcopy(cq),
        "pitch_movement": {"outings": [{"g": 1}], "pitches": {"FF": {"ivb": 17.1}}},
        "pitch_plot": copy.deepcopy(plot),
        "recent_games": [{"level": "AAA", "date": "2026-09-20", "ip": 5.0}],
        "standout_games": [{"level": "AAA", "date": "2026-09-20"}],
        "level_splits": [
            {"level": "AAA", "is_pitcher": True, "contact_quality": copy.deepcopy(cq),
             "pitch_plot": copy.deepcopy(plot)},
            {"level": "AA", "is_pitcher": True,
             "contact_quality": {**copy.deepcopy(cq), "batted_balls": 12, "avg_ev": 86.0},
             "pitch_plot": copy.deepcopy(plot)},
        ],
    }


def test_export_leaves_the_input_statcast_payloads_unchanged(tmp_path, monkeypatch):
    from scrapers import Snapshot
    from consensus import build_timeseries

    snaps = [Snapshot(source="fangraphs", snapshot_date="2026-02-14",
                      interval_label="2026report", player_key="arm_one",
                      player_name="Arm One", position="RHP", org="PIT",
                      rank=30, fv=50.0, status="active", tools={})]
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    storage.insert_snapshots(snaps)
    scm = {"arm_one": _statcast_payload("arm_one")}
    frozen = copy.deepcopy(scm)

    storage.export_timeseries_json(build_timeseries(snaps, single_source_k=0),
                                   tmp_path / "timeseries.json", statcast_metrics=scm)

    assert scm == frozen, "export_timeseries_json wrote into its statcast_metrics input"

    boot = json.loads((tmp_path / "timeseries.json").read_text(encoding="utf-8"))
    served = next(p for p in boot["players"] if p["player_key"] == "arm_one")["statcast_metrics"]
    assert served["pitch_plot"] == {}, "the boot block keeps pitch_plot out"
    assert all(row["pitch_plot"] == {} for row in served["level_splits"])
    assert served["contact_quality"]["hit_locations"] == []
    assert served["recent_games"] == [] and served["standout_games"] == []
    assert served["contact_quality"]["qualified"] is True
    assert served["contact_quality"]["qualifier_min_bbe"] == storage._STATCAST_CONTACT_MIN_BBE
    shard = json.loads((tmp_path / "pitch_plots" / "arm_one.json").read_text(encoding="utf-8"))
    assert shard, "the harvest found no pitch_plot to ship"
    detail = json.loads((tmp_path / "player_detail" / "arm_one.json").read_text(encoding="utf-8"))
    assert detail["statcast"]["top"]["contact_quality"]["hit_locations"] == \
        frozen["arm_one"]["contact_quality"]["hit_locations"]
