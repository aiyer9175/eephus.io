# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-06: provisional grades v2 (provisional_v2.py) and its two artifacts.

Acceptance (PROVISIONAL_V2.md section 5, PV-06): the port reproduces the frozen p_g12 on
the 4,163 frozen rows (Spearman >= 0.99, same seed); no served row carries a pre-anchor
opinion; each level head speaks its own source's scale. Also pinned: the frame drops a
player graded on or before the anchor and never reads an opinion dated after the run
date, FanGraphs 35+ codes as 37.5 and an opinion is dated by its first sighting, the
capture guard leaves out a window whose source was not captured, the eval is a
forward-chained BACKCAST, the outputs are redirected under pytest, and the module reads
no WAR.

The frozen-frame reproduction needs only the committed fixture and the freeze; the
served-row check reads the local prospects.db and identity maps (read only) and skips
where they are absent. No test here writes inside the checkout.
"""
from __future__ import annotations

import collections
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import provisional_v2 as P

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "provisional_v2.json"
EVAL = ROOT / "data" / "provisional_v2_eval.json"


def _doc(p):
    if not p.exists():
        pytest.skip(f"{p.name} not built")
    return json.loads(p.read_text(encoding="utf-8"))


# --- acceptance ---------------------------------------------------------------------

def test_the_port_reproduces_the_frozen_p_g12_on_the_frozen_rows():
    fx = P.FREEZE_FRAME_PATH
    if not fx.exists():
        pytest.skip("frozen lane frame fixture missing")
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == P.FREEZE_FRAME_SHA256
    res = P.reproduce_freeze(frame=P.load_freeze_frame())
    assert res["seed"] == 7 and P.PARAMS["random_state"] == 7
    assert res["frozen_rows_with_p"] == 4163
    assert res["matched"] == 4163 and res["frozen_only"] == 0 and res["port_only"] == 0
    assert res["p_g12"]["spearman"] >= 0.99
    assert res["p_g6"]["spearman"] >= 0.99
    # the freeze stores P to 4 decimals; the port lands inside that rounding
    assert res["p_g12"]["max_abs_diff"] <= 1e-4 and res["p_g6"]["max_abs_diff"] <= 1e-4


def test_the_eval_records_both_reproductions():
    ev = _doc(EVAL)
    rep = ev["freeze_reproduction"]
    ff = rep["frozen_frame"]
    assert ff["matched"] == 4163 and ff["p_g12"]["spearman"] >= 0.99
    live = rep["live_inputs"]
    assert live["matched"] >= 4100
    assert live["p_g12"]["spearman"] >= 0.95
    assert 0 < live["seed_floor"]["p_g12_spearman"] < 1


def test_no_served_row_has_an_opinion_on_or_before_the_run_date():
    doc = _doc(OUT)
    if not (ROOT / "prospects.db").exists():
        pytest.skip("prospects.db not on this machine")
    import provisional_track as T
    m2k, opin = T.identity(), T.opinions()
    as_of = doc["as_of"]
    bad = []
    for r in doc["rows"]:
        pk = m2k.get(str(r["mlbam"]))
        if pk and any(d <= as_of for d, _s, _fv in opin.get(pk, [])):
            bad.append((r["mlbam"], pk))
    assert bad == []
    assert len({r["mlbam"] for r in doc["rows"]}) == len(doc["rows"])


def test_each_level_head_speaks_its_own_source_scale():
    doc = _doc(OUT)
    t2 = doc["heads"]["T2"]
    assert "FanGraphs" in t2["FG"]["scale"] and "37.5" in t2["FG"]["scale"]
    assert "Pipeline" in t2["MLBP"]["scale"]
    for s, (lo, hi) in (("FG", (30.0, 50.0)), ("MLBP", (30.0, 55.0))):
        h = t2[s]
        assert abs(h["served_mean"] - h["train_label_mean"]) <= 2.5, s
        vals = [r[f"fv_first_{s.lower()}"] for r in doc["rows"]]
        assert all(v is not None and lo <= v <= hi for v in vals), s
    # two scales, not one: each head sits where its own source's first grades sit
    assert (t2["MLBP"]["train_label_mean"] - t2["FG"]["train_label_mean"]) > 1.0
    assert t2["MLBP"]["served_mean"] > t2["FG"]["served_mean"]
    assert doc["not_on_efv_scale"] is True and doc["feeds_efv"] is False


def test_served_probabilities_are_probabilities():
    doc = _doc(OUT)
    keys = [f"p_{s.lower()}_{w.lower()}" for s, w in P.T1_HEADS]
    for r in doc["rows"]:
        for k in keys + ["p_any_w6_raw", "p_any_w12_raw"]:
            assert 0.0 <= r[k] <= 1.0, (r["mlbam"], k)
    for key, h in doc["heads"]["T1"].items():
        assert h["shift_anchor"] in h["train_anchors"], key
        assert h["window_end"] > doc["as_of"], key


# --- the backcast -------------------------------------------------------------------

def test_the_eval_is_a_forward_chained_backcast():
    ev = _doc(EVAL)
    assert ev["label"] == "BACKCAST" and ev["reads_no_war"] is True
    as_of = ev["as_of"]
    for atype, res in ev["backcast"].items():
        for key, h in res["T1"].items():
            window = key.split("_")[1]
            left_out = {int(y) for y in h["anchors_left_out"]}
            for t, b in h["by_anchor"].items():
                t = int(t)
                assert P.window_end(atype, t, window) <= as_of, (atype, key, t)
                assert all(x < t for x in b["train_anchors"]), (atype, key, t)
                assert b["shift_from_anchor"] in b["train_anchors"], (atype, key, t)
                assert not left_out & set(b["train_anchors"]) and t not in left_out
        for s, h in res["T2"].items():
            assert all(P.window_end(atype, t, "W12") <= as_of for t in h["test_anchors"])


# --- synthetic ----------------------------------------------------------------------

def _hit(m, season, lv="A", pa=300, age=20.0, name="x"):
    return {"mlbam": m, "name": name, "lv": lv, "pa": pa, "ab": pa - 30, "h": 70, "doubles": 15,
            "triples": 2, "hr": 8, "bb": 25, "hbp": 3, "sf": 2, "so": 60, "sb": 10, "age": age}


def _fake_inputs(ev_raw):
    inp = object.__new__(P.Inputs)
    inp.typ = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0, "AA": 22.5, "AAA": 24.0}
    inp.lines = collections.defaultdict(list)
    for m in (1, 2, 3, 4):
        inp.lines[(m, 2024, "hit")].append(_hit(m, 2024))
    inp.mlb_seasons = collections.defaultdict(set)
    inp.names = {m: f"p{m}" for m in (1, 2, 3, 4)}
    inp._load_norms()
    inp.draft, inp.phys, inp.aaah = {}, {}, {}
    inp.ev_raw = ev_raw
    return inp


def test_the_frame_drops_pre_anchor_opinions_and_ignores_later_ones():
    ev = {1: [("2024-09-01", "fangraphs", 40.0, None)],        # graded before the Oct 15 anchor
          2: [("2024-11-13", "fangraphs", 37.5, None)],        # first graded inside W6
          3: [("2026-11-01", "mlb_pipeline", 45.0, None)]}     # after the run date: never read
    df = P.build_frame(_fake_inputs(ev), "2026-10-02", [("oct", 2024)])
    got = {int(m): r for m, r in zip(df.mlbam, df.to_dict("records"))}
    assert set(got) == {2, 3, 4}
    assert (got[2]["G6_ANY"], got[2]["G6_FG"], got[2]["FV1_FG"]) == (1, 1, 37.5)
    assert (got[3]["G12_ANY"], got[3]["G12_MLBP"]) == (0, 0)
    assert got[4]["G12_ANY"] == 0


def test_fangraphs_plus_codes_half_step_and_dates_by_first_sighting(tmp_path):
    db = tmp_path / "p.db"
    con = sqlite3.connect(db)
    con.execute("create table snapshots (player_key text, source text, snapshot_date text, "
                "inserted_at text, fv real, fv_plus integer, rank integer)")
    con.executemany("insert into snapshots values (?,?,?,?,?,?,?)", [
        ("a", "fangraphs", "2025-02-12", "2025-02-12 10:00:00", 35.0, 1, None),
        ("b", "mlb_pipeline", "2026-09-30", "2026-08-14 03:00:00", 40.0, 0, 12),   # bumped in place
        ("c", "tjstats", "2025-01-01", "2025-01-01 00:00:00", 50.0, 0, None),     # not a label source
    ])
    con.commit()
    con.close()
    inp = object.__new__(P.Inputs)
    inp.db_path, inp.k2m = db, {"a": 10, "b": 11, "c": 12}
    inp._load_opinions()
    assert inp.ev_raw[10] == [("2025-02-12", "fangraphs", 37.5, None)]
    assert inp.ev_raw[11] == [("2026-08-14", "mlb_pipeline", 40.0, 12)]
    assert 12 not in inp.ev_raw


def test_the_capture_guard_leaves_out_an_uncaptured_window():
    import pandas as pd
    df = pd.DataFrame({"atype": ["oct"] * 5, "y": [2021, 2022, 2023, 2024, 2025]})
    days = collections.Counter()
    for y in (2021, 2022, 2023, 2024):
        days[("mlb_pipeline", f"{y + 1}-01-22")] = 1000
        days[("fangraphs", f"{y + 1}-02-12")] = 1300
    days[("mlb_pipeline", "2026-01-22")] = 48
    days[("fangraphs", "2026-02-12")] = 1050
    keep, out = P.usable_years(df, days, "oct", "MLBP", "W6", "2026-10-02")
    assert keep == [2021, 2022, 2023, 2024] and list(out) == [2025]
    assert "mlb_pipeline 48 rows" in out[2025]
    keep, out = P.usable_years(df, days, "oct", "FG", "W6", "2026-10-02")
    assert keep == [2021, 2022, 2023, 2024, 2025] and out == {}
    keep, out = P.usable_years(df, days, "oct", "ANY", "W12", "2026-10-02")
    assert 2025 not in keep            # its W12 window is still open


def test_the_serving_anchor_follows_the_season():
    assert P.serving_anchor("2026-10-02") == ("oct", 2026)
    assert P.serving_anchor("2026-09-24") == ("jun", 2026)
    assert P.serving_anchor("2027-03-01") == ("oct", 2026)
    assert P.serving_anchor("2027-06-01") == ("jun", 2027)
    assert P._anchor("oct", 2020) is None and P._anchor("jun", 2021) is None


def test_outputs_are_redirected_under_pytest():
    assert P.OUT_PATH.resolve() != OUT.resolve()
    assert P.EVAL_PATH.resolve() != EVAL.resolve()


def test_the_module_reads_no_war():
    src = (ROOT / "provisional_v2.py").read_text(encoding="utf-8")
    for tok in ("career_war", "realized_war", "xfv_war", "war6", "target_censored", "import efv_ungraded",
                "sabermetrics", "fit_nofv"):
        assert tok not in src, tok
    q = src[src.index("def _load_opinions("):src.index("# anchors")]
    assert "from snapshots" in q and "war" not in q.lower()


def test_the_registry_row_quotes_the_artifact():
    ev = _doc(EVAL)
    reg = {m["model_id"]: m for m in json.loads(
        (ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))["models"]}
    row = reg["provisional_v2"]
    assert row["eval_artifact"] == "data/provisional_v2_eval.json"
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "shipped_partial_measurement"
    a = ev["backcast"]["oct"]["T1"]["ANY_W12"]["pooled"]
    f = ev["backcast"]["oct"]["T2"]["FG"]["pooled"]
    lv = ev["freeze_reproduction"]["live_inputs"]
    for want in (f"AUC {a['auc']:.3f} against the level-rank null {a['null_level_rank_auc']:.3f}",
                 f"Brier from {a['brier_raw']} to {a['brier_shifted']}",
                 f"FanGraphs first FV MAE {f['mae']} against {f['mae_const']}",
                 f"Spearman {lv['p_g12']['spearman']} on {lv['matched']:,} matched rows"):
        assert want in row["notes"], want


def test_efv_export_builds_it_only_when_persisting():
    import inspect

    import efv_export
    src = inspect.getsource(efv_export.regen_all)
    i = src.index("provisional_v2.build(persist)")
    assert "if persist:" in src[max(0, i - 200):i]
