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
     report family (the production construction), every served value inside the
     production training range (clipped, withheld where the training column was never
     lit, drift named in the receipt);
  4. score_live attaches them under the flag (candidate chips print with their labels) and
     is the V2 path byte for byte with the flag off;
  5. no look-ahead: nothing dated after today changes a column, and a read past today
     raises; on the FV-history series, a snapshot before today never takes the live values
     (the served grade is its own point dated today), the population fit never learns a
     label still open on a snapshot's date, and no pooled value (centering mean, z norm,
     percentile) reads a snapshot dated after it;
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
FEASIBLE = ("group", "tool", "il", "pbp", "pbp_bb", "popmle", "w2s")
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
    cands = X.candidates()
    withheld = set(rec.get("withheld") or [])
    for fam in FEASIBLE:
        if fam not in fams:
            continue
        ns = [n for n in cols if X._family_of(n) == fam]
        for n in ns:
            nz = sum(1 for v in cols[n].values() if v not in (None, 0.0))
            if fam == "group" and n in (fams[fam].get("dark_columns") or []):
                continue                              # named in the receipt, read 0.0
            if cands[n]["key"] in withheld:
                assert all(v is None for v in cols[n].values()), n
                continue                              # no training support: named, None
            assert nz > 0, (fam, n)
    for n in cols:
        if X._family_of(n) == "report":
            assert all(v is None for v in cols[n].values()), n
    for fam, note in fams.items():
        if note.get("status") != "lit":
            assert note.get("reason"), fam            # every dark family says why


def _head_z_ranges(side, cols):
    """[(key, training max |head z|, served p99 |head z|, served max |head z|)] for every
    served candidate key with values on both sides, under the served head's mu and sd."""
    m = S.production_models()[side]
    if m.get("model_id") != X.MODEL_ID:
        pytest.skip("eFV v5 COMBINED is not the served model")
    train = X.production_train(side, log=lambda *_a, **_k: None)
    cands = X.candidates()
    by_key = {cands[n]["key"]: n for n in cols}
    out = []
    for h in ("skill", "timing"):
        head = m.get(h)
        if not head:
            continue
        for j, k in enumerate(head["keys"]):
            n = by_key.get(k)
            sd = float(head["sd"][j])
            if n is None or sd == 0:
                continue
            mu = float(head["mu"][j])
            tv = np.array([r["v2"][k] for r in train if r["v2"].get(k) is not None], float)
            lv = np.array([v for v in cols[n].values() if v is not None], float)
            if not tv.size or not lv.size:
                continue
            tz, lz = np.abs((tv - mu) / sd), np.abs((lv - mu) / sd)
            out.append((k, float(tz.max()), float(np.percentile(lz, 99)), float(lz.max())))
    return out


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_live_values_never_leave_the_training_range(side):
    """The verifier's measure (2026-10-15), replacing a median |z| that a mostly-zero column
    passes at any spread: per served candidate key, the served p99 and max |head z| stay
    inside the training max |head z| (High-A slider gap reached 36.0 against 11.2, 60-day
    IL stints 26.9 against 5.2)."""
    _live_rows, rows, cols, _rec = _cols(side)
    got = _head_z_ranges(side, cols)
    assert len(got) >= 10
    for k, tmax, p99, lmax in got:
        assert lmax <= tmax + 1e-9, (k, tmax, lmax)
        assert p99 <= tmax + 1e-9, (k, tmax, p99)


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_the_support_receipt_names_every_clip_withhold_and_drift(side):
    _live_rows, rows, cols, rec = _cols(side)
    sup = X.training_support(side, log=lambda *_a, **_k: None)
    cands = X.candidates()
    rep = rec["support"]
    assert set(rep) == {cands[n]["key"] for n in cols}
    raw = X.live_columns(side, rows, today=TODAY, clip=False,
                         raw_by_key={r["player_key"]: r for r in _live(side)},
                         log=lambda *_a, **_k: None)
    n_clip = 0
    for n, mp in cols.items():
        k = cands[n]["key"]
        s, r = sup[k], rep[k]
        vals = [v for v in raw[n].values() if v is not None]
        nz = sum(1 for v in vals if v != 0.0)
        # withheld exactly when the training column was lit in a single pool (read
        # season), so it never saw this column lit on a board
        want = (bool(vals) and s["nonzero_seasons"] < X.SUPPORT_MIN_SEASONS
                and (nz > 0 or s["min"] is None))
        assert r["withheld"] is want, (k, s, nz)
        if want:
            assert all(v is None for v in mp.values()), k
            continue
        for slot, v in mp.items():
            rv = raw[n][slot]
            if rv is None:
                assert v is None
            elif s["min"] is not None:
                assert v == min(max(rv, s["min"]), s["max"]), (k, rv, v)
        lo = sum(1 for v in vals if s["min"] is not None and v < s["min"])
        hi = sum(1 for v in vals if s["max"] is not None and v > s["max"])
        assert (r["clipped_low"], r["clipped_high"]) == (lo, hi), k
        n_clip += lo + hi
    assert rec["clipped"] == n_clip
    assert rec["withheld"] == sorted(k for k, r in rep.items() if r["withheld"])
    drifting = {k for k, r in rep.items() if r.get("drift")}
    for fam, note in rec["families"].items():
        mine = {cands[n]["key"] for n in cols if X._family_of(n) == fam} & drifting
        if mine:
            assert set(note["drift"]) == mine and note["status"] != "lit", fam


def test_the_high_a_slider_gap_is_withheld_and_il_counts_stay_in_support():
    """The two measured cases. The High-A slider gap cells had 33, 0 and 0 nonzero training
    rows (one 2019 pool) and light 8 to 14% of the live board: withheld. A 60-day IL count
    was 0 or 1 on every training hitter (67 rows over 8 seasons) and reaches 5 live:
    clipped to 1 and kept, and the IL family's drift is named."""
    _l, _r, pcols, prec = _cols("pit")
    psup = X.training_support("pit", log=lambda *_a, **_k: None)
    assert psup["scr_t5_pit_Ap_all_all_sl_gap"]["nonzero_seasons"] == 1
    for n in ("t5_pit_Ap_all_all_sl_gap", "t5_pit_Ap_all_SP_sl_gap", "t5_pit_Ap_young_all_sl_gap"):
        assert n in pcols
        assert all(v is None for v in pcols[n].values()), n
        assert X.candidates()[n]["key"] in prec["withheld"], n
    _l, _r, hcols, hrec = _cols("hit")
    sup = X.training_support("hit", log=lambda *_a, **_k: None)
    k = "scr_w2i_sixty_time_hit"
    n = next(n for n in hcols if X.candidates()[n]["key"] == k)
    assert sup[k]["nonzero_seasons"] >= X.SUPPORT_MIN_SEASONS and k not in hrec["withheld"]
    assert max(v for v in hcols[n].values() if v is not None) <= sup[k]["max"]
    assert hrec["support"][k]["clipped_high"] > 0
    assert hrec["families"]["il"]["status"] == "drift" and k in hrec["families"]["il"]["drift"]


def test_support_clip_on_a_synthetic_support(monkeypatch):
    names = X.side_candidates("pit")
    cands = X.candidates()
    a, b = names[0], names[1]
    ka, kb = cands[a]["key"], cands[b]["key"]
    monkeypatch.setitem(X._SUPPORT, "pit", {
        ka: {"n": 500, "nonzero": 400, "nonzero_share": 0.8, "nonzero_seasons": 12,
             "min": -1.0, "max": 2.0},
        kb: {"n": 500, "nonzero": 10, "nonzero_share": 0.02, "nonzero_seasons": 1,
             "min": -0.5, "max": 0.5}})
    cols = {a: {1: -3.0, 2: 0.5, 3: 9.0, 4: None}, b: {1: 0.0, 2: 3.0, 3: None, 4: 0.0}}
    rec = {"families": {}}
    out = X.support_clip("pit", cols, rec)
    assert out[a] == {1: -1.0, 2: 0.5, 3: 2.0, 4: None}
    assert out[b] == {1: None, 2: None, 3: None, 4: None}
    assert rec["support"][ka]["clipped_low"] == 1 and rec["support"][ka]["clipped_high"] == 1
    assert rec["withheld"] == [kb] and rec["clipped"] == 2
    # a thin column the board leaves at 0.0 everywhere is the training construction: kept
    out = X.support_clip("pit", {b: {1: 0.0, 2: 0.0}}, None)
    assert out[b] == {1: 0.0, 2: 0.0}


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
# 5b. the FV-history series: every snapshot as of its own date (verifier defects 2026-10-15)
# ---------------------------------------------------------------------------

def _stub_grader(**kw):
    g = S.HistoryGrader.__new__(S.HistoryGrader)
    g.side, g.today, g._v5 = "pit", TODAY, True
    g._cand_live = {"p": {"scr_x": 1.0}}
    g._cand_hist = {("p", "2024-08-01"): {"scr_x": 0.25}, ("p", "2026-08-02"): {"scr_x": 0.5}}
    g._served = {"p": (55.04, 50.0)}
    for k, v in kw.items():
        setattr(g, k, v)
    return g


def test_a_snapshot_before_today_never_takes_the_live_values():
    """The live values read the 2026 season, the IL feed through 2026-09-30 and the 2027
    population fit. They used to land on the snapshot dated at the player's consensus
    as-of date (as early as 2024-08-01); now only a snapshot dated on the live read date
    takes them, and every older one reads as of itself."""
    g = _stub_grader()
    assert g._candidates_at("p", "2024-08-01") == {"scr_x": 0.25}
    assert g._candidates_at("p", "2026-08-02") == {"scr_x": 0.5}
    assert g._candidates_at("p", "2026-10-02") == {}          # never primed: no candidate
    assert g._candidates_at("p", TODAY) == {"scr_x": 1.0}
    assert not hasattr(g, "_live_asof")


def test_prime_reads_every_older_snapshot_as_of_itself(monkeypatch):
    seen = {}

    def fake(side, todo, *, today, log, **_k):
        seen["todo"], seen["today"] = list(todo), today
        return {}, {}
    monkeypatch.setattr(X, "history_columns", fake)
    g = _stub_grader(_cand_hist={})
    pts = [{"d": "2024-08-01", "fv": 45.0}, {"d": "2026-08-02", "fv": 50.0},
           {"d": TODAY, "fv": 50.0}]
    g.prime({"p": {"mlbam_id": 7, "points": pts}})
    assert seen["today"] == TODAY
    assert [t[2] for t in seen["todo"]] == ["2024-08-01", "2026-08-02"]


def test_the_served_grade_is_a_point_dated_today():
    g = _stub_grader()
    s = [{"d": "2024-02-14", "x": 44.0, "c": 45.0}, {"d": "2024-08-01", "x": 47.0, "c": 50.0}]
    assert g.served_point("p", s) == {"d": TODAY, "x": 55.0, "c": 50.0}
    assert g.served_point("p", s + [{"d": TODAY, "x": 55.0, "c": 50.0}]) is None
    assert g.served_point("p", [{"d": "2024-08-01", "x": 55.0, "c": 50.0}]) is None
    assert g.served_point("q", s) is None
    assert _stub_grader(_v5=False, _served={}).served_point("p", s) is None


def test_the_population_fit_never_learns_a_label_open_on_the_read_date():
    """history_columns reads a snapshot at min(year, list year) + 1; the population fit at
    that year learns fWAR through the snapshot's own season, still being played on a
    pre-October date. pop_fit_year lowers it to the last season ended by the cutoff."""
    import efv_w2_popmle as PM
    assert X.pop_fit_year(2027, TODAY) == 2027                 # the live board: unchanged
    assert X.pop_fit_year(2027, "2026-08-02") == 2026
    assert X.pop_fit_year(2026, "2025-08-01") == 2025
    assert X.pop_fit_year(2026, "2025-10-02") == 2026
    d = date(2014, 1, 1)
    while d <= date.fromisoformat(TODAY):
        ds = d.isoformat()
        ry = min(d.year, S.live_year()) + X.LIVE_READ_YEAR_OFFSET
        fy = X.pop_fit_year(ry, ds)
        seasons = PM.train_seasons(fy)
        assert not seasons or max(seasons) + PM.HORIZON <= X._last_season_ended(ds), ds
        d += timedelta(days=17)


def test_pooled_values_read_only_earlier_items_of_the_same_season():
    items = [{"slot": i, "season": s, "cutoff": c, "v": v}
             for i, (s, c, v) in enumerate([(2025, "2026-01-22", 1.0), (2025, "2026-02-14", 3.0),
                                            (2025, "2026-08-02", 8.0), (2026, "2026-10-02", 100.0),
                                            (2025, "2026-02-14", 5.0)])]

    def finish(pool):
        m = sum(it["v"] for it in pool) / len(pool)
        return {"c": {it["slot"]: it["v"] - m for it in pool}}
    got = X._pooled_asof(items, finish)["c"]
    assert got[0] == 0.0                                       # alone in its pool
    assert got[1] == 3.0 - 3.0 and got[4] == 5.0 - 3.0         # pool {1, 3, 5}
    assert got[2] == 8.0 - 17.0 / 4                            # pool {1, 3, 5, 8}
    assert got[3] == 0.0                                       # the 2026 read: its own pool
    # one cutoff (the live board): exactly one call over every item
    live = [dict(it, cutoff=TODAY, season=2026) for it in items]
    assert X._pooled_asof(live, finish) == finish(live)


def test_a_history_point_is_untouched_by_snapshots_dated_after_it():
    """The verifier's measurement as a test: rebuilding the group and tool columns with only
    the snapshots dated before 2026-06-01 must leave those snapshots' values unchanged
    (they moved by up to 2.66 z when every snapshot of the year shared one pool)."""
    live = _live("pit")
    ids = {r["player_key"]: r.get("mlbam_id") for r in live if r.get("mlbam_id")}
    if not (DATA / "timeseries.json").exists():
        pytest.skip("data/timeseries.json not built on this machine")
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))["players"]
    pts, seen = [], set()
    for rec in ts:
        pk = rec.get("player_key")
        if pk not in ids:
            continue
        for pt in rec.get("points") or []:
            d = str(pt.get("snapshot_date") or "")[:10]
            if ("2025-10-01" <= d <= TODAY and pt.get("consensus_fv_raw") is not None
                    and (pk, d) not in seen):
                seen.add((pk, d))
                pts.append((pk, ids[pk], d, float(pt["consensus_fv_raw"])))
    assert len(pts) > 300 and any(p[2] >= "2026-10-01" for p in pts)
    rd = X.live_read(TODAY)
    Y = rd["group_year"]

    def items(points):
        return [X._item((pk, d), pk, mid, int(d[:4]), min(int(d[:4]), Y) + 1, d, d, fv)
                for pk, mid, d, fv in points]
    names = [n for n in X.side_candidates("pit") if X._family_of(n) in ("group", "tool")]
    full, _r = X.asof_columns("pit", items(pts), today=TODAY, names=names,
                              log=lambda *_a, **_k: None)
    early = [p for p in pts if p[2] < "2026-06-01"]
    part, _r = X.asof_columns("pit", items(early), today=TODAY, names=names,
                              log=lambda *_a, **_k: None)
    for n in names:
        for pk, _m, d, _fv in early:
            assert part[n][(pk, d)] == full[n][(pk, d)], (n, pk, d)


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


# ---------------------------------------------------------------------------
# 7. the served disclosures (EFV_FIX_A A3, owner decision EW3-21)
# ---------------------------------------------------------------------------

def _fake_models():
    def head(keys):
        return {"keys": list(keys)}
    return {"hit": {"w_skill": 0.9, "w_time": 0.2,
                    "skill": head(["tool_hit", "scr_w2p_swstr_h", "scr_w2r_panel_hit",
                                   "scr_g5_hit_Ap_all_all_pbp_swstr",
                                   "scr_g5_hit_A_all_all_k_pct"]),
                    "timing": head(["level_rank", "scr_rpt_conviction_hit"])}}


def test_disclosures_follow_the_live_receipt():
    rec = {"families": {
        "pbp": {"status": "dark", "reason": "no aggregate"},
        "raters": {"status": "dark", "reason": "no list"},
        "report": {"status": "dark", "reason": "by construction"},
        "group": {"status": "partial", "reason": "no discipline aggregate",
                  "dark_columns": ["g5_hit_Ap_all_all_pbp_swstr"]},
        "popmle": {"status": "lit"}},
        "support": {"scr_w2r_panel_hit": {"withheld": True, "reason": "few seasons"}}}
    d = X.served_disclosures(_fake_models(), {"hit": rec}, today=TODAY)
    sk = d["served_keys"]["hit"]
    assert sk["n"] == 7 and "level_rank" in sk["timing"]
    rows = {r["family"]: r for r in d["dark"]["hit"]}
    assert rows["pbp"]["keys"] == ["scr_w2p_swstr_h"]
    assert rows["raters"]["keys"] == ["scr_w2r_panel_hit"]
    assert rows["report"]["keys"] == ["scr_rpt_conviction_hit"]
    assert rows["group"]["keys"] == ["scr_g5_hit_Ap_all_all_pbp_swstr"]
    assert rows["support"]["keys"] == ["scr_w2r_panel_hit"]
    assert "popmle" not in rows
    rd = X.live_read(TODAY)
    sr = d["season_read"]
    assert sr["read_season"] == rd["season"] and sr["kind"] == "in-season update"
    assert sr["live_read_year_offset"] == X.LIVE_READ_YEAR_OFFSET
    assert sr["text"] == X.season_read_sentence(rd["season"])
    assert d["head_weights"]["weights"]["hit"] == {"w_skill": 0.9, "w_time": 0.2}
    assert d["head_weights"]["pending"] == "EFV_FIX_B_REFIT"


def test_disclosure_copy_is_plain():
    for text in (X.HEAD_WEIGHTS_NOTE, X.season_read_sentence(2026)):
        assert chr(0x2014) not in text and chr(0x2013) not in text
    assert X.season_read_sentence(2026) == ("The grade reads the latest full minor league "
                                            "season (2026), which is newer than some "
                                            "consensus lists.")


def test_the_served_artifact_carries_the_disclosures():
    p = DATA / "xfv.json"
    if not p.exists():
        pytest.skip("data/xfv.json not built on this machine")
    sm = json.loads(p.read_text(encoding="utf-8"))["meta"].get("served_model") or {}
    rec = sm.get("receipt") or {}
    if not rec.get("hit") or not X.EFV_V5_COMBINED_ON:
        pytest.skip("eFV v5 COMBINED is not the served model")
    d = sm.get("disclosures")
    assert d, "meta.served_model.disclosures missing (efv_export._served_model_meta)"
    for side in ("hit", "pit"):
        served = set(rec[side]["skill"]["keys"]) | set(rec[side]["timing"]["keys"])
        got = d["served_keys"][side]
        assert set(got["skill"]) | set(got["timing"]) == served and got["n"] == len(served)
        for row in d["dark"][side]:
            assert row["keys"] and set(row["keys"]) <= served, row
            assert row["reason"], row
        assert d["head_weights"]["weights"][side] == {"w_skill": rec[side]["w_skill"],
                                                      "w_time": rec[side]["w_time"]}
    sr = d["season_read"]
    assert sr["text"] == X.season_read_sentence(sr["read_season"])
    assert sr["read_year"] == sr["list_year"] + X.LIVE_READ_YEAR_OFFSET
