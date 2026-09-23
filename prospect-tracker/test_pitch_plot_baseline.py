# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Guards for the ONE thing a tjStuff+ number cannot be published without:
the baseline it was scored against.

WHAT WENT WRONG. mlb_stuff_plus.score_pitch_points picks a primary fastball
out of whatever row set it is handed and scores every pitch as a difference
against it. Handed a pitcher's pooled rows and then his per-level rows, it
can pick a different fastball, after which the SAME PITCH carries two
tjStuff+ values with nothing in the payload or on the page to say which ruler
either sits on. Measured on data/pitch_plots on 2026-09-18: 610 of 1,789
entries are multi-level, 22 of those publish an aggregate view that is a real
pool of several levels, and in all 22 the pooled view and the level views
disagree on shared pitches - 2,348 pitch instances, -38.4 to +16.6.

WHAT THE HOUSE ANSWER IS. tools/mlbstats_window_lab.py hit the identical
problem for the multi-year index boards and answered it the same way twice
over: score each view on its OWN pool, because a different population is a
different comparison, and then PUBLISH the pool so no ruler travels unnamed.
So these tests do not assert that the two numbers agree. They assert that
neither can be published without its baseline attached, and that a reader
flipping level tabs is told the baselines differ.

WHAT ELSE IS GUARDED. The published entry shape: internal scorer inputs do
not ship, the model label ships once per view rather than once per pitch, and
a view identical to one of its own splits ships as a reference to it. All
three are byte savings that must not move a single value, so every one of
them is asserted value-by-value rather than by eyeball.

Run it under pytest, or directly (`python test_pitch_plot_baseline.py`) when
a full collection would be heavier than the question deserves.
"""

from __future__ import annotations

import json
from pathlib import Path

import mlb_stuff_plus
import storage
from mlb_stuff_plus import ScoredPitches, baseline_label, score_pitch_points
from storage import (dedupe_pitch_plot_entry, resolve_pitch_plot_entry,
                     slim_pitch_plot_view)

ROOT = Path(__file__).parent
PLOT_DIR = ROOT / "data" / "pitch_plots"
PROSPX = ROOT / "prospx" / "index.html"

# THE PRE-REFETCH OFFENDERS, pinned as a SET rather than a count. data/pitch_plots
# on 2026-09-18 holds entries written before the baseline shipped, and these
# publish an aggregate view whose numbers disagree with a level view's on
# shared pitches with no `stuff_baseline` on either side. An EXPORT cannot
# clear them: the baseline is written by statcast_metrics._finalize_pitch at
# FETCH time, and export reads stored rows out of prospects.db. What clears
# them is the first statcast re-fetch after METRIC_SCHEMA_VERSION 2, which
# rebuilds every stored row. A set is pinned so a shrink is visible and a
# substitution (one offender fixed, a new one fetched) is never silently
# tolerated the way a `<= 22` count would.
UNLABELLED_OFFENDERS = frozenset({
    'braden_nett.json',
    'bryce_hubbart.json',
    'calvin_ziegler.json',
    'cameron_foster.json',
    'cesar_aquino.json',
    'claudio_estelie.json',
    'cory_lewis.json',
    'danny_flatt.json',
    'dominic_perachi.json',
    'dominic_pipkin.json',
    'franklin_sanchez.json',
    'gerardo_lopez.json',
    'jarod_bayless.json',
    'joe_miller.json',
    'joel_diaz.json',
    'jose_atencio.json',
    'juan_amarante.json',
    'luis_r_rodriguez.json',
    'michael_walsh.json',
    'ryan_jensen.json',
    'win_scott.json',
})


def _row(pitch_type, velo, **kw):
    row = {
        "pitch_type": pitch_type,
        "pitch_name": {"FF": "Four-Seam Fastball", "SI": "Sinker",
                       "SL": "Slider"}.get(pitch_type, pitch_type),
        "velo": velo,
        "spin": 2400,
        "extension": 6.4,
        "az": -12.0,
        "ax": -8.0,
        "x0": -1.7,
        "release_height": 5.6,
        "pitcher_hand": "R",
        "hb": 6.0,
        "ivb": 12.0,
    }
    row.update(kw)
    return row


# ---------------------------------------------------------------------------
# the scorer hands back the ruler it used
# ---------------------------------------------------------------------------

def test_scored_rows_carry_the_baseline_they_were_scored_against():
    rows = [_row("FF", 96.0)] * 6 + [_row("SL", 85.0, az=-30.0, ax=8.0)] * 3
    scored = score_pitch_points([dict(r) for r in rows])

    assert isinstance(scored, ScoredPitches)
    assert isinstance(scored, list), "callers iterate this; it stays a list"
    assert len(scored) == len(rows)
    if scored[0].get("tj_stuff_plus") is None:
        return  # model artifact absent in this checkout; nothing to label
    label = baseline_label(scored.baseline, len(scored))
    assert label["scored"] is True
    assert label["pitch_type"] == "FF"
    assert label["n"] == 6
    assert label["is_fastball"] is True
    assert label["tracked_rows"] == len(rows)
    assert label["model"] == mlb_stuff_plus.TJSTUFF_MODEL_NAME
    assert "scale" not in label, "the scale sentence is a renderer constant, not per-view payload"


def test_pooling_two_levels_can_change_the_baseline_and_the_label_says_so():
    """The defect, reproduced. The AAA rows alone put the primary on FF; the
    pooled rows put it on SI, and every pitch moves with it. Both numbers are
    defensible - what is not defensible is publishing them unlabelled."""

    aaa = [_row("FF", 96.0) for _ in range(10)]
    mlb = [_row("SI", 94.0) for _ in range(14)]
    slider = [_row("SL", 85.0, az=-30.0, ax=8.0)]

    only_aaa = score_pitch_points([dict(r) for r in aaa + slider])
    pooled = score_pitch_points([dict(r) for r in aaa + mlb + slider])
    if only_aaa[-1].get("tj_stuff_plus") is None:
        return  # model artifact absent

    a = baseline_label(only_aaa.baseline, len(only_aaa))
    b = baseline_label(pooled.baseline, len(pooled))
    assert a["pitch_type"] == "FF"
    assert b["pitch_type"] == "SI"
    assert a != b, "different pools, different ruler"
    # the same slider, two numbers - which is exactly why the label ships
    assert only_aaa[-1]["tj_stuff_plus"] != pooled[-1]["tj_stuff_plus"]


def test_baseline_label_reports_a_non_fastball_fallback():
    rows = [_row("SL", 85.0, az=-30.0, ax=8.0) for _ in range(4)]
    scored = score_pitch_points([dict(r) for r in rows])
    if scored[0].get("tj_stuff_plus") is None:
        return
    label = baseline_label(scored.baseline, len(scored))
    assert label["pitch_type"] == "SL"
    assert label["is_fastball"] is False


def test_baseline_label_of_nothing_says_unscored_rather_than_guessing():
    assert baseline_label(None) == {"scored": False}


# ---------------------------------------------------------------------------
# the published shape
# ---------------------------------------------------------------------------

def _view(n=3, model="tjstuff_plus_2020_2023_lgbm"):
    return {
        "x_axis": "Horizontal break",
        "y_axis": "Induced vertical break",
        "stuff_baseline": {"scored": True, "pitch_type": "FF", "n": 9,
                           "avg_velo": 95.1, "is_fastball": True},
        "points": [{"game_pk": 1 + i, "pitch_type": "FF", "hb": 6.0 + i,
                    "ivb": 12.0, "velo": 95.0, "ax": -8.0, "x0": -1.7,
                    "ax_mirrored": 8.0, "x0_mirrored": 1.7,
                    "tj_stuff_plus": 101.5 + i,
                    "tj_stuff_plus_model": model} for i in range(n)],
    }


def test_slim_drops_internal_inputs_hoists_the_label_and_moves_no_value():
    before = _view()
    after = slim_pitch_plot_view(before)

    assert after["stuff_model"] == "tjstuff_plus_2020_2023_lgbm"
    assert after["stuff_baseline"] == before["stuff_baseline"]
    assert list(after["points"][0]) == [
        "game_pk", "pitch_type", "hb", "ivb", "velo", "ax", "x0",
        "tj_stuff_plus"], "internal inputs and the per-row stamp are gone"
    for a, b in zip(before["points"], after["points"]):
        assert a["tj_stuff_plus"] == b["tj_stuff_plus"]
        assert (a["hb"], a["ivb"], a["velo"]) == (b["hb"], b["ivb"], b["velo"])
    assert before["points"][0].get("ax_mirrored") == 8.0, "input untouched"


def test_slim_refuses_to_hoist_a_label_two_rows_disagree_on():
    view = _view(n=2)
    view["points"][1]["tj_stuff_plus_model"] = "some_other_model"
    after = slim_pitch_plot_view(view)

    assert "stuff_model" not in after
    assert [p["tj_stuff_plus_model"] for p in after["points"]] == [
        "tjstuff_plus_2020_2023_lgbm", "some_other_model"]


def test_a_view_identical_to_its_own_split_ships_once():
    only = slim_pitch_plot_view(_view())
    entry = dedupe_pitch_plot_entry({"top": only, "level_splits": {"AAA": only}})

    assert entry["top_ref"] == "AAA"
    assert "top" not in entry
    assert resolve_pitch_plot_entry(entry)["top"] == only
    assert json.dumps(entry).count('"tj_stuff_plus"') == 3, "one copy, not two"


def test_a_genuinely_pooled_view_is_kept_whole():
    top = slim_pitch_plot_view(_view(n=3))
    aaa = slim_pitch_plot_view(_view(n=2))
    entry = dedupe_pitch_plot_entry({"top": top, "level_splits": {"AAA": aaa}})

    assert "top_ref" not in entry
    assert entry["top"] == top
    assert resolve_pitch_plot_entry(entry) == entry


def test_resolve_is_a_no_op_on_an_entry_that_was_never_deduped():
    entry = {"top": _view(), "level_splits": {"AAA": _view(n=2)}}
    assert resolve_pitch_plot_entry(entry) == entry


# ---------------------------------------------------------------------------
# the writer, end to end
# ---------------------------------------------------------------------------

def _export_one_pitcher(tmp_dir, top, splits):
    """Run the REAL export over one pitcher carrying these plot views and
    return the entry it wrote to data/pitch_plots/. Exercises the harvest
    closure itself, not a re-implementation of it."""

    from scrapers import Snapshot
    from consensus import build_timeseries

    snaps = [Snapshot(source="fangraphs", snapshot_date="2026-02-14",
                      interval_label="2026report", player_key="arm_one",
                      player_name="Arm One", position="RHP", org="PIT",
                      rank=30, fv=50.0, status="active", tools={})]
    old_db = storage.DB_PATH
    storage.DB_PATH = tmp_dir / "test.db"
    try:
        storage.init_db()
        storage.insert_snapshots(snaps)
        storage.export_timeseries_json(
            build_timeseries(snaps, single_source_k=0),
            tmp_dir / "timeseries.json",
            statcast_metrics={"arm_one": {
                "player_key": "arm_one", "is_pitcher": True, "level": "AAA",
                "pitch_plot": top,
                "level_splits": [{"level": lvl, "pitch_plot": blk}
                                 for lvl, blk in splits.items()],
            }})
    finally:
        storage.DB_PATH = old_db
    written = tmp_dir / "pitch_plots" / "arm_one.json"
    assert written.exists(), "the export wrote no pitch_plots shard"
    return json.loads(written.read_text(encoding="utf-8"))


def test_export_writes_the_baseline_and_ships_a_repeated_view_once(tmp_path):
    only = _view()
    entry = _export_one_pitcher(tmp_path, only, {"AAA": dict(only)})

    assert entry["top_ref"] == "AAA"
    assert "top" not in entry
    view = entry["level_splits"]["AAA"]
    assert view["stuff_baseline"]["pitch_type"] == "FF"
    assert view["stuff_model"] == "tjstuff_plus_2020_2023_lgbm"
    assert "ax_mirrored" not in view["points"][0]
    assert [p["tj_stuff_plus"] for p in view["points"]] == \
        [p["tj_stuff_plus"] for p in only["points"]], "no value moved"


def test_export_keeps_a_pooled_view_and_labels_both_sides(tmp_path):
    top, aaa = _view(n=3), _view(n=2)
    aaa["stuff_baseline"] = dict(aaa["stuff_baseline"], avg_velo=92.4, n=4)
    entry = _export_one_pitcher(tmp_path, top, {"AAA": aaa})

    assert "top_ref" not in entry, "a real pool is not a reference"
    assert entry["top"]["stuff_baseline"]["avg_velo"] == 95.1
    assert entry["level_splits"]["AAA"]["stuff_baseline"]["avg_velo"] == 92.4


def test_the_unified_reader_resolves_a_referenced_view(tmp_path):
    only = _view()
    _export_one_pitcher(tmp_path, only, {"AAA": dict(only)})
    payload = storage.load_export_unified(tmp_path / "timeseries.json")
    sc = next(p for p in payload["players"]
              if p["player_key"] == "arm_one")["statcast_metrics"]

    assert (sc["pitch_plot"].get("points") or []), \
        "a referenced view must re-inline like a whole one"
    assert [p["tj_stuff_plus"] for p in sc["pitch_plot"]["points"]] == \
        [p["tj_stuff_plus"] for p in only["points"]]


# ---------------------------------------------------------------------------
# the renderer
# ---------------------------------------------------------------------------

def test_prospx_resolves_a_referenced_top_and_prints_the_baseline():
    src = PROSPX.read_text(encoding="utf-8")

    assert "function _pitchPlotTopView(" in src
    assert "entry.top_ref" in src, "the renderer resolves a referenced top"
    assert "function _pitchPlotBaselineNote(" in src
    assert "Stuff+ baseline: " in src
    # the note is rendered, not merely defined
    assert "${baselineNote}" in src
    # and the cross-view warning exists for a pitcher whose views differ
    assert "other levels have their own baseline" in src


def test_prospx_never_derives_a_baseline_from_the_plotted_points():
    """The plot publishes at most PITCH_PLOT_LIMIT points while the baseline
    was taken over every tracked pitch, so a baseline computed in the browser
    would name a ruler the numbers were never scored on. Re-measured on the
    2026-09-18 artifact: 938 of 4,227 published views sit at that cap."""

    src = PROSPX.read_text(encoding="utf-8")
    start = src.index("function _pitchPlotBaselineNote(")
    end = src.index("function makePitchMovementPlot(", start)
    body = src[start:end]
    assert "stuff_baseline" in body
    for forbidden in ("_primary_fastball", "FASTBALL_TYPES", "avg_velo =",
                      "reduce("):
        assert forbidden not in body, f"{forbidden} would recompute the ruler"


# ---------------------------------------------------------------------------
# the served artifact
# ---------------------------------------------------------------------------

def _entries():
    if not PLOT_DIR.is_dir():
        return []
    return sorted(PLOT_DIR.glob("*.json"))


def test_every_served_entry_resolves_to_a_top_view():
    files = _entries()
    if not files:
        return
    for f in files[:400]:
        entry = resolve_pitch_plot_entry(json.loads(f.read_text(encoding="utf-8")))
        top = entry.get("top") or {}
        assert (top.get("points") or []), f"{f.name} has no aggregate view"


def test_two_values_for_one_pitch_never_ship_without_both_baselines():
    """The invariant this whole lane exists for. If two views of one pitcher
    disagree about a pitch, each must carry the baseline that explains why.
    The budget is the pre-regen debt and may only fall."""

    files = _entries()
    if not files:
        return

    def key(p):
        return (p.get("game_pk"), p.get("pitch_type"), p.get("velo"),
                p.get("hb"), p.get("ivb"), p.get("spin"), p.get("vaa"))

    offenders = []
    for f in files:
        entry = resolve_pitch_plot_entry(json.loads(f.read_text(encoding="utf-8")))
        top = entry.get("top") or {}
        tmap = {key(p): p.get("tj_stuff_plus") for p in (top.get("points") or [])}
        for level, block in (entry.get("level_splits") or {}).items():
            if block is top:
                continue
            for p in (block or {}).get("points") or []:
                other = tmap.get(key(p))
                if other is None or p.get("tj_stuff_plus") is None:
                    continue
                if other == p["tj_stuff_plus"]:
                    continue
                if (top.get("stuff_baseline") or {}).get("scored") and \
                   (block.get("stuff_baseline") or {}).get("scored"):
                    continue
                offenders.append((f.name, level))
                break

    names = frozenset(o[0] for o in offenders)
    extra = sorted(names - UNLABELLED_OFFENDERS)
    gone = sorted(UNLABELLED_OFFENDERS - names)
    assert not extra, f"NEW unlabelled two-value entries appeared: {extra}"
    assert not gone, (f"entries left the pinned set (fixed, or refetched): {gone}; "
                      "remove them from UNLABELLED_OFFENDERS in the same change")


def test_the_writer_and_the_reader_agree_on_the_published_shape():
    """dedupe/resolve are each other's inverse over the served artifact, so
    a reader on either side of the change sees the same views."""

    files = _entries()
    if not files:
        return
    for f in files[:200]:
        entry = json.loads(f.read_text(encoding="utf-8"))
        resolved = resolve_pitch_plot_entry(entry)
        again = resolve_pitch_plot_entry(dedupe_pitch_plot_entry(resolved))
        assert again == resolved, f.name


def test_storage_helpers_are_importable_by_name():
    for name in ("slim_pitch_plot_view", "dedupe_pitch_plot_entry",
                 "resolve_pitch_plot_entry", "PITCH_PLOT_INTERNAL_FIELDS"):
        assert hasattr(storage, name), name


if __name__ == "__main__":
    import inspect
    import tempfile
    import traceback
    failed = 0
    for _name, _fn in sorted(list(globals().items())):
        if not _name.startswith("test_") or not callable(_fn):
            continue
        try:
            if "tmp_path" in inspect.signature(_fn).parameters:
                with tempfile.TemporaryDirectory() as _d:
                    _fn(Path(_d))
                print("PASS", _name)
                continue
            _fn()
            print("PASS", _name)
        except Exception:
            failed += 1
            print("FAIL", _name)
            traceback.print_exc()
    print("failures:", failed)
    raise SystemExit(1 if failed else 0)
