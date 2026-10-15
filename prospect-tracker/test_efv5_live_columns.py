# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 COMBINED on the live board (efv5_combined.live_columns, efv_v2_serve.score_live).

The defect: the live rows carried V2's keys only, so every candidate column read None,
took its head's training mean (z = 0) and the served board was not the fitted v5.

What is pinned here:
  1. every candidate key has a plain-English chip label (no dash characters, never the raw
     key, timing labels say arrival, no v1 pitcher-block label reused);
  2. the live read rule: the read season had ended by today, never a partial season;
  3. live columns on the real live board: exactly the side's candidates on (list year,
     player_key, 'live') slots, finite values for every family built live, None for the
     report family (the production construction), z scores on the training scale;
  4. score_live attaches them under the flag (candidate chips print with their labels) and
     is the V2 path byte for byte with the flag off;
  5. no look-ahead: nothing dated after today changes a column, and a read past today
     raises;
  6. the training side is untouched: the season-local Lines equal the training Lines, and
     the production fit still reproduces the committed served weights.

Nothing here runs a backtest or reads an outcome.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as X
import efv5_group_drivers as G
import efv_v2_model as H
import efv_v2_serve as S

ROOT = Path(__file__).parent
DATA = ROOT / "data"
TODAY = "2026-10-15"
#: Families the live board can build from the sources on disk (their primitives exist and
#: their sources cover the read); the rest are dark or partial by a named reason.
FEASIBLE = ("group", "tool", "il", "pbp_bb", "popmle", "w2s")
BANNED_V1_PIT = {"Peak K rate", "Walk rate vs level", "K-backed run prevention", "Fastball",
                 "Age", "Age for level", "Contact (K%) vs level", "ERA vs level",
                 "Peak walk rate", "Command", "Slider", "Changeup", "Curveball"}


def _live(side: str) -> list[dict]:
    import efv_dataset as D
    p = D.live_matrix_path(side)
    if not p.exists():
        pytest.skip(f"{p.name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


_COLS: dict = {}


def _cols(side: str):
    if side not in _COLS:
        live = _live(side)
        rows = S.live_rows(side, live, today=TODAY)
        rec: dict = {}
        cols = X.live_columns(side, rows, today=TODAY,
                              raw_by_key={r["player_key"]: r for r in live}, receipt=rec,
                              log=lambda *_a, **_k: None)
        _COLS[side] = (live, rows, cols, rec)
    return _COLS[side]


# ---------------------------------------------------------------------------
# 1. labels
# ---------------------------------------------------------------------------

def test_every_candidate_key_has_a_plain_label():
    cands = X.candidates()
    keys = {s["key"] for s in cands.values()}
    assert set(X.CHIP_LABELS_V5) == keys
    for n, s in cands.items():
        lab = X.CHIP_LABELS_V5[s["key"]]
        assert lab and lab != s["key"] and lab != n, n
        assert "scr_" not in lab and "_" not in lab, (n, lab)
        assert chr(0x2014) not in lab and chr(0x2013) not in lab, n
        if s["head"] == "timing":
            assert lab.endswith("(arrival)"), (n, lab)
        else:
            assert "arrival" not in lab, (n, lab)
        if s["side"] == "pit":
            assert lab not in BANNED_V1_PIT, (n, lab)
    for side in ("hit", "pit"):
        labs = [X.CHIP_LABELS_V5[cands[n]["key"]] for n in X.side_candidates(side)]
        assert len(labs) == len(set(labs)), side


def test_every_served_receipt_key_has_a_label():
    p = DATA / "xfv.json"
    if not p.exists():
        pytest.skip("data/xfv.json not built on this machine")
    rec = (json.loads(p.read_text(encoding="utf-8"))["meta"].get("served_model") or {}).get(
        "receipt") or {}
    keys = {k for side in ("hit", "pit") for h in ("skill", "timing")
            for k in ((rec.get(side) or {}).get(h) or {}).get("keys") or []}
    if not keys:
        pytest.skip("no served receipt")
    for k in keys:
        lab = S.chip_label(k)
        assert lab != k and chr(0x2014) not in lab, k


def test_chip_labels_keep_v2_and_add_v5():
    for k, lab in S.CHIP_LABELS.items():
        assert S.chip_label(k) == lab
    assert S.chip_label("scr_g5_pit_A_all_all_k_minus_bb") == "Single-A strikeout rate minus walk rate"
    assert S.chip_label("scr_rpt_conviction_hit") == "Scouting report conviction (arrival)"
    assert S.chip_label("not_a_key") == "not_a_key"


# ---------------------------------------------------------------------------
# 2. the read rule
# ---------------------------------------------------------------------------

def test_the_live_read_never_reads_a_partial_season():
    r = X.live_read(TODAY)
    assert r["group_year"] == S.live_year()
    assert r["read_year"] == r["group_year"] + 1 and r["cutoff"] == TODAY
    assert r["season"] == 2026                       # the 2026 season ended before 10-15
    mid = X.live_read("2026-08-02")
    assert mid["season"] == 2025                     # mid-season: the last complete one
    for d in ("2026-01-01", "2026-04-15", "2026-09-30", "2026-10-01", "2026-12-31"):
        rr = X.live_read(d)
        assert X._season_ended(rr["season"], d), d


# ---------------------------------------------------------------------------
# 3. live columns on the live board
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("side", ["hit", "pit"])
def test_live_columns_cover_every_candidate_on_live_slots(side):
    _live_rows, rows, cols, rec = _cols(side)
    assert set(cols) == set(X.side_candidates(side))
    want = {(S.live_year(), r["player_key"], X.LIVE_KIND) for r in rows}
    for n, mp in cols.items():
        assert set(mp) == want, n
        for v in mp.values():
            assert v is None or math.isfinite(v), n
    fams = rec["families"]
    for fam in FEASIBLE:
        if fam not in fams:
            continue
        ns = [n for n in cols if X._family_of(n) == fam]
        for n in ns:
            nz = sum(1 for v in cols[n].values() if v not in (None, 0.0))
            if fam == "group" and n in (fams[fam].get("dark_columns") or []):
                continue                              # named in the receipt, read 0.0
            assert nz > 0, (fam, n)
    for n in cols:
        if X._family_of(n) == "report":
            assert all(v is None for v in cols[n].values()), n
    for fam, note in fams.items():
        if note.get("status") != "lit":
            assert note.get("reason"), fam            # every dark family says why


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_live_values_sit_on_the_training_scale(side):
    _live_rows, rows, cols, _rec = _cols(side)
    m = S.production_models()[side]
    if m.get("model_id") != X.MODEL_ID:
        pytest.skip("eFV v5 COMBINED is not the served model")
    cands = X.candidates()
    by_key = {cands[n]["key"]: n for n in cols}
    checked = 0
    for h in ("skill", "timing"):
        head = m.get(h)
        if not head:
            continue
        for j, k in enumerate(head["keys"]):
            n = by_key.get(k)
            if n is None:
                continue
            vals = np.array([v for v in cols[n].values() if v is not None], dtype=float)
            if vals.size < 20:
                continue
            z = (vals - float(head["mu"][j])) / float(head["sd"][j])
            assert float(np.median(np.abs(z))) < 3.0, (n, float(np.median(np.abs(z))))
            checked += 1
    assert checked >= 10


# ---------------------------------------------------------------------------
# 4. score_live
# ---------------------------------------------------------------------------

def _score_live_v2(side, live, models, today):
    """The V2 path before the live columns, verbatim (the byte-identity reference)."""
    model = models[side]
    rows = S.live_rows(side, live, today=today)
    preds = H.predict_v2(model, rows)
    parts = S._chip_parts(model, rows)
    head_chips = S._tracking_head(side, rows, preds, model)
    grades = np.array([p["efv_grade"] for p in preds], dtype=np.float64)
    war6 = H.war_at(model.get("war_map_6yr"), grades) if preds else np.array([])
    n = len(preds)
    by_order = sorted(range(n), key=lambda i: (-preds[i]["order_idx"], preds[i]["player_key"]))
    o_rank = {i: pos + 1 for pos, i in enumerate(by_order)}
    fvs = [float(r["fv"]) for r in rows]
    c_rank = {i: 1 + sum(1 for v in fvs if v > fvs[i]) for i in range(n)}
    out = {}
    for i, (r, p) in enumerate(zip(rows, preds)):
        out[r["player_key"]] = dict(p, efv_war_6yr=float(war6[i]),
                                    order_rank=o_rank[i], consensus_rank=c_rank[i],
                                    group_n=n, has_block=bool(r["v2"]["has_block"]),
                                    has_milb=r["has_milb"],
                                    chips=S.driver_chips(parts[i]) + head_chips[i])
    return out


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_flag_off_is_the_v2_path_byte_for_byte(side, monkeypatch):
    live = _live(side)
    models = S.production_models()
    monkeypatch.setattr(X, "EFV_V5_COMBINED_ON", False)
    got = S.score_live(side, live, models=models, today=TODAY)
    ref = _score_live_v2(side, live, models, TODAY)
    assert json.dumps(got, sort_keys=True) == json.dumps(ref, sort_keys=True)


def test_a_non_v5_model_takes_no_candidate_even_with_the_flag_on():
    assert X.EFV_V5_COMBINED_ON is True
    assert S.v5c_serves({"model_id": X.MODEL_ID}) is True
    assert S.v5c_serves({"model_id": "efv_v2"}) is False
    rows = [{"player_key": "a", "v2": {}}]
    assert S._with_live_candidates("hit", rows, [], {"model_id": "efv_v2"}, TODAY) is rows


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_score_live_attaches_the_candidates_and_their_chips_print(side):
    live = _live(side)
    models = S.production_models()
    if not S.v5c_serves(models[side]):
        pytest.skip("eFV v5 COMBINED is not the served model")
    cand: dict = {}
    preds = S.score_live(side, live, models=models, today=TODAY, cand_out=cand)
    assert set(cand) == set(preds)
    keys = {X.candidates()[n]["key"] for n in X.side_candidates(side)}
    for pk, vals in cand.items():
        assert set(vals) == keys, pk
    chips = [c for p in preds.values() for c in p["chips"] if c["driver"].startswith("scr_")]
    assert chips, "no candidate chip on the live board"
    for c in chips:
        assert c["label"] == X.CHIP_LABELS_V5[c["driver"]]
        assert c["mag"] >= S.CHIP_FLOOR_PCT - 1e-9
    # the candidate keys move the order: the board is not the V2-keys-only read
    off = _score_live_v2(side, live, models, TODAY)
    assert any(abs(preds[k]["order_idx"] - off[k]["order_idx"]) > 1e-9 for k in preds)


def test_the_card_takes_the_explainer_cut_under_v5():
    import efv_score as E
    chips = [{"label": f"d{i}", "driver": f"scr_{i}", "dir": "up", "mag": float(i),
              "unit": "percentile points"} for i in range(1, 8)]
    chips.append({"label": "Injury note", "on_grade": False, "mag": 0.0})
    kept, more = E._v5_explainer_cut(chips)
    assert [c["mag"] for c in kept if c.get("on_grade") is not False] == [7.0, 6.0, 5.0, 4.0]
    assert any(c.get("on_grade") is False for c in kept)
    assert more == {"n": 3, "mag": 6.0}


# ---------------------------------------------------------------------------
# 5. no look-ahead
# ---------------------------------------------------------------------------

def test_nothing_dated_after_today_changes_a_column():
    side = "pit"
    _live_rows, rows, cols, rec = _cols(side)
    tomorrow = (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()
    later = (date.fromisoformat(TODAY) + timedelta(days=40)).isoformat()
    sample = [r for r in rows if r.get("mlbam_id")][:200]
    # a stint placed after today, an NRI entry known after today, a scouting board dated
    # after today, for every sampled player
    idx, _end, _rc = X._stint_index(TODAY)
    nri_idx, _have = X._nri_index(TODAY, S.live_year())
    sc = X._scout_index(TODAY)
    assert max(e[0] for v in sc.by_key.values() for e in v) <= TODAY
    added = []
    for r in sample:
        pid, pk = int(r["mlbam_id"]), r["player_key"]
        st = {"pid": pid, "start": tomorrow, "placed": tomorrow, "list": "60", "severe": 1,
              "severe_announced": tomorrow, "end": None, "end_announced": None, "how": None,
              "team": None, "start_inferred": 0}
        idx.setdefault(pid, []).append(st)
        nri_idx.entries.setdefault(pid, []).append((tomorrow, 2027, True))
        sc.by_key.setdefault(pk, []).append(
            (later, "fangraphs", {"sl": 80.0, "cb": 80.0, "fb": 80.0, "cmd": 80.0},
             {"sl": 20.0}, {"arm": 80.0}, "RHP"))
        added.append((pid, pk))
    try:
        X._LIVE_MEMO.clear()
        live = _live(side)
        again = X.live_columns(side, rows, today=TODAY,
                               raw_by_key={r["player_key"]: r for r in live},
                               log=lambda *_a, **_k: None)
        for n in cols:
            assert again[n] == cols[n], n
    finally:
        for pid, pk in added:
            idx[pid] = [s for s in idx[pid] if s["placed"] != tomorrow]
            nri_idx.entries[pid] = [e for e in nri_idx.entries[pid] if e[0] != tomorrow]
            sc.by_key[pk] = [e for e in sc.by_key[pk] if e[0] != later]
        X._LIVE_MEMO.clear()


def test_a_read_past_today_raises():
    import efv_vintage_frame as F
    it = X._item((2026, "x", X.LIVE_KIND), "x", 1, 2026, 2027, TODAY, "2026-10-16", 50.0)
    with pytest.raises(F.ReservedFrameError):
        X.asof_columns("pit", [it], today=TODAY, names=["w2s_cmd_pit"])
    it = X._item((2026, "x", X.LIVE_KIND), "x", 1, 2026, 2027, "2026-10-20", TODAY, 50.0)
    with pytest.raises(F.ReservedFrameError):
        X.asof_columns("pit", [it], today=TODAY, names=["w2s_cmd_pit"])


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_every_live_read_is_on_or_before_today(side):
    _live_rows, rows, _cols_, rec = _cols(side)
    rd = rec["read"]
    assert rd["cutoff"] <= TODAY and X._season_ended(rd["season"], TODAY)
    fams = rec["families"]
    if "il" in fams:
        assert fams["il"]["feed_last_day"] <= TODAY
        assert fams["il"]["read_cut_capped_at"] <= (
            date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()
    if "group" in fams:
        assert fams["group"]["seasons"] == [rd["season"]]
    if "w2s" in fams:
        assert fams["w2s"]["snapshot_cap"] == (
            date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# 6. the training side is untouched
# ---------------------------------------------------------------------------

def test_season_local_lines_equal_the_training_lines():
    side = "pit"
    full = G.lines_for(side, log=lambda *_a, **_k: None)
    metrics = [s["metric"] for s in G.menu_columns().values() if s["side"] == side]
    one = G.Lines(side, metrics, seasons=(2023,), log=lambda *_a, **_k: None)
    keys = [k for k in full.vals if k[1] == 2023]
    assert keys and set(keys) == set(one.vals)
    for k in keys:
        assert one.vals[k] == full.vals[k], k
        assert one.band.get(k) == full.band.get(k)
        assert one.role.get(k) == full.role.get(k)
    assert {p: v for p, v in full.norm.items() if p[0] == 2023} == one.norm


def test_the_production_fit_still_reproduces_the_served_weights():
    doc = json.loads(X.WEIGHTS_PATH.read_text(encoding="utf-8"))
    models = S.production_models()
    for side, m in models.items():
        if m.get("model_id") != X.MODEL_ID:
            pytest.skip("eFV v5 COMBINED is not the served model")
        got = json.loads(json.dumps(X.weights_table(m)))
        assert got == doc["weights"][side], side
