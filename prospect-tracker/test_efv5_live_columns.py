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
    # the measure runs on every candidate key the served heads carry (the re-fit's hitter
    # skill head is the hit tool alone, so the hitter keys are its arrival head's), and a
    # served candidate key with no values to compare fails here rather than passing unread
    m = S.production_models()[side]
    by_key = {X.candidates()[n]["key"] for n in cols}
    served = {k for h in ("skill", "timing") for j, k in enumerate((m.get(h) or {}).get("keys") or [])
              if k in by_key and float(m[h]["sd"][j]) != 0}
    assert served, side
    assert {k for k, *_r in got} == served, sorted(served - {k for k, *_r in got})
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
        # a key the drift rebase rescaled (DRIFT_REBASE_ON) is clipped after its factor
        f = r.get("rebase_factor")

        def adj(v, f=f):
            return v * f if (f and v is not None and v != 0.0) else v
        # withheld exactly when the training column was lit in a single pool (read
        # season), so it never saw this column lit on a board
        want = (bool(vals) and s["nonzero_seasons"] < X.SUPPORT_MIN_SEASONS
                and (nz > 0 or s["min"] is None))
        assert r["withheld"] is want, (k, s, nz)
        if want:
            assert all(v is None for v in mp.values()), k
            continue
        for slot, v in mp.items():
            rv = adj(raw[n][slot])
            if rv is None:
                assert v is None
            elif s["min"] is not None:
                assert v == pytest.approx(min(max(rv, s["min"]), s["max"]), rel=1e-5,
                                          abs=1e-12), (k, rv, v)
        vals = [adj(v) for v in vals]
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
    # the spread report (report only): a ratio wherever both sides are lit enough, and the
    # flag exactly above SPREAD_RATIO
    for k, r in rep.items():
        if r["withheld"]:
            continue
        assert bool(r.get("spread")) is (r["spread_ratio"] is not None
                                         and r["spread_ratio"] > X.SPREAD_RATIO), k
    assert rec["spread"] == sorted(k for k, r in rep.items() if r.get("spread"))


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


def test_the_spread_report_is_report_only(monkeypatch):
    """DRV-3 (docs/efv-v2/EFV_PIT_AUDIT_FIXES.md section 3): the served nonzero SD against the
    training nonzero SD, flagged above SPREAD_RATIO (the 2x rule), None under
    SPREAD_MIN_NONZERO; no value, clip, withhold or family status moves."""
    assert X.SPREAD_RATIO == X.DRIFT_RATIO == 2.0 and X.SPREAD_MIN_NONZERO == 20
    names = [n for n in X.side_candidates("pit")
             if X._family_of(n) == X._family_of(X.side_candidates("pit")[0])]
    a, b = names[0], names[1]
    cands = X.candidates()
    ka, kb = cands[a]["key"], cands[b]["key"]
    sup = {"n": 1000, "nonzero": 500, "nonzero_share": 0.5, "nonzero_seasons": 12,
           "nonzero_sd": 1.0, "min": -100.0, "max": 100.0}
    monkeypatch.setitem(X._SUPPORT, "pit", {ka: dict(sup), kb: dict(sup)})
    rng = np.random.default_rng(7)
    wide = {i: float(v) for i, v in enumerate(rng.normal(0, 3.0, 200))}       # planted 3x
    calm = {i: float(v) for i, v in enumerate(rng.normal(0, 1.0, 200))}       # null 1x
    fam = X._family_of(a)
    rec = {"families": {fam: {"status": "lit"}}}
    out = X.support_clip("pit", {a: wide, b: calm}, rec)
    assert out[a] == wide and out[b] == calm
    ra, rb = rec["support"][ka], rec["support"][kb]
    assert ra["spread_ratio"] == pytest.approx(3.0, rel=0.15) and ra["spread"] is True
    assert rb["spread_ratio"] == pytest.approx(1.0, rel=0.15) and "spread" not in rb
    assert rec["spread"] == [ka] and rec["families"][fam]["spread"] == [ka]
    assert rec["families"][fam]["status"] == "lit" and rec["withheld"] == []
    # under SPREAD_MIN_NONZERO nonzero values on either side: no ratio
    few = {i: float(v) for i, v in enumerate(rng.normal(0, 5.0, 10))}
    rec2: dict = {"families": {}}
    X.support_clip("pit", {a: few}, rec2)
    assert rec2["support"][ka]["spread_ratio"] is None and rec2["spread"] == []
    assert X.spread_ratio(list(wide.values()), dict(sup, nonzero=5)) is None
    assert X.spread_ratio(list(wide.values()), dict(sup, nonzero_sd=None)) is None


def test_the_drift_rebase_on_a_synthetic_support(monkeypatch):
    """EFV_PIT_DRIFT_REBASE (docs/efv-v2/EFV_PIT_DRIFT_REBASE.md sections 2 and 4): with the
    flag on, a registered key and any key the 2x spread report flags carry the training
    nonzero SD (0.0 and None kept, the clip after the factor); a calm unregistered key, a
    share-only drift and a key under SPREAD_MIN_NONZERO nonzero values do not move. Off
    (the default) the rule is the identity."""
    monkeypatch.setattr(X, "DRIFT_REBASE_ON", False)
    cands = X.candidates()
    names = X.side_candidates("pit")
    reg = next(n for n in names if cands[n]["key"] in X.REBASE_KEYS)
    other = [n for n in names if cands[n]["key"] not in X.REBASE_KEYS][:4]
    a, b, c, d = other
    sup = {"n": 1000, "nonzero": 500, "nonzero_share": 0.5, "nonzero_seasons": 12,
           "nonzero_sd": 1.0, "min": -100.0, "max": 100.0}
    monkeypatch.setitem(X._SUPPORT, "pit", {
        cands[reg]["key"]: dict(sup, min=-2.0, max=2.0), cands[a]["key"]: dict(sup),
        cands[b]["key"]: dict(sup), cands[c]["key"]: dict(sup, nonzero_share=0.05),
        cands[d]["key"]: dict(sup)})
    rng = np.random.default_rng(11)

    def col(sd, n_nz, n_zero=100):
        v = [float(x) for x in rng.normal(0, sd, n_nz)] + [0.0] * n_zero + [None]
        return {i: x for i, x in enumerate(v)}
    cols = {reg: col(1.4, 200), a: col(3.0, 200), b: col(1.4, 200), c: col(1.0, 200, 10),
            d: col(3.0, 10)}
    off = X.support_clip("pit", cols, {"families": {}})
    assert off[a] == cols[a] and off[b] == cols[b] and off[c] == cols[c]
    monkeypatch.setattr(X, "DRIFT_REBASE_ON", True)
    rec = {"families": {}}
    out = X.support_clip("pit", cols, rec)
    rep = {cands[n]["key"]: rec["support"][cands[n]["key"]] for n in cols}
    f_reg = X.rebase_factor(list(cols[reg].values()), sup)
    assert rep[cands[reg]["key"]]["rebase_factor"] == pytest.approx(f_reg, abs=1e-6)
    for slot, v in cols[reg].items():
        want = v if v in (None, 0.0) else min(max(v * f_reg, -2.0), 2.0)
        assert out[reg][slot] == pytest.approx(want) if v is not None else out[reg][slot] is None
    flagged = [v for v in out[a].values() if v not in (None, 0.0)]
    assert X._nonzero_sd(flagged) == pytest.approx(1.0)
    assert rep[cands[a]["key"]]["spread"] is True and rep[cands[a]["key"]]["rebased"] is True
    assert out[b] == cols[b] and "rebased" not in rep[cands[b]["key"]]
    assert rep[cands[c]["key"]].get("drift") is True and out[c] == cols[c]
    assert out[d] == cols[d] and "rebased" not in rep[cands[d]["key"]]
    assert rec["rebased"] == sorted([cands[reg]["key"], cands[a]["key"]])
    # under SPREAD_MIN_NONZERO on the served side, or no training SD: no factor
    assert X.rebase_factor(list(cols[d].values()), sup) is None
    assert X.rebase_factor(list(cols[a].values()), dict(sup, nonzero_sd=None)) is None


def test_the_drift_rebase_on_the_live_board(monkeypatch):
    """The dark rule on the real pitcher board: every registered key that has a factor is
    rescaled by exactly the training over served nonzero SD before the clip, the 60-day
    count is read by injury episode (never above the stored count) and the training
    support is untouched."""
    live, rows, _cols_off, _rec = _cols("pit")
    sup_before = json.dumps(X.training_support("pit", log=lambda *_a, **_k: None), sort_keys=True)
    raw = X.live_columns("pit", rows, today=TODAY, clip=False,
                         raw_by_key={r["player_key"]: r for r in live},
                         log=lambda *_a, **_k: None)
    monkeypatch.setattr(X, "DRIFT_REBASE_ON", True)
    rec: dict = {}
    on = X.live_columns("pit", rows, today=TODAY, receipt=rec,
                        raw_by_key={r["player_key"]: r for r in live},
                        log=lambda *_a, **_k: None)
    cands = X.candidates()
    sup = X.training_support("pit", log=lambda *_a, **_k: None)
    assert json.dumps(sup, sort_keys=True) == sup_before
    assert rec["families"]["il"].get("sixty_episodes") is True
    got = set(rec["rebased"])
    assert got >= {k for k in X.REBASE_KEYS
                   if X.rebase_factor(list(raw[next(n for n in raw if cands[n]["key"] == k)].values()),
                                      sup[k]) is not None}
    for n, mp in on.items():
        k = cands[n]["key"]
        r = rec["support"][k]
        if k in got:
            f = X.rebase_factor(list(raw[n].values()), sup[k])
            assert r["rebase_factor"] == pytest.approx(f, abs=1e-6)
            for slot, v in mp.items():
                rv = raw[n][slot]
                if rv is None:
                    continue
                want = rv * f if rv != 0.0 else 0.0
                assert v == pytest.approx(min(max(want, sup[k]["min"]), sup[k]["max"]))
        if k == "scr_w2i_sixty_skill_pit":
            for slot, v in mp.items():
                rv = raw[n][slot]
                if rv is not None:
                    assert v <= min(max(rv, sup[k]["min"]), sup[k]["max"])


def test_the_popup_chip_says_which_way_it_grades():
    """CON-3 (docs/efv-v2/EFV_PIT_AUDIT_FIXES.md section 4): the popup slope is negative,
    so its chip says a low rate grades up and why."""
    lab = X.CHIP_LABELS_V5["scr_w2b_pu_p"]
    assert lab.startswith("Low popup rate allowed grades up")
    assert "fewer popups went with more WAR" in lab
    assert S.chip_label("scr_w2b_pu_p") == lab


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
    # the drivers the served heads weight (a head at weight 0 moves nothing); under the
    # re-fit (2026-10-15) that is the hit tool for hitters and the candidate columns of
    # the joint skill head for pitchers
    m = models[side]
    moving = {k for h, w in (("skill", "w_skill"), ("timing", "w_time")) if (m.get(w) or 0) > 0
              for j, k in enumerate((m.get(h) or {}).get("keys") or [])
              if float(m[h]["beta"][j]) != 0.0}
    assert moving, side
    chips = [c for p in preds.values() for c in p["chips"] if c["driver"] in moving]
    assert chips, f"no chip of a served driver on the live board ({sorted(moving)})"
    assert not [c for p in preds.values() for c in p["chips"]
                if c["driver"] not in moving and c.get("on_grade") is not False
                and c["driver"].startswith("scr_")], "a chip names a driver the heads do not weight"
    for c in chips:
        if c["driver"].startswith("scr_"):
            assert c["label"] == X.CHIP_LABELS_V5[c["driver"]]
        else:
            assert c["label"] == S.CHIP_LABELS[c["driver"]]
        assert c["mag"] >= S.CHIP_FLOOR_PCT - 1e-9
    off = _score_live_v2(side, live, models, TODAY)
    moved = any(abs(preds[k]["order_idx"] - off[k]["order_idx"]) > 1e-9 for k in preds)
    if any(k.startswith("scr_") for k in moving):
        # the candidate keys move the order: the board is not the V2-keys-only read
        assert moved
    else:
        # no candidate key carries weight: the board is exactly the V2-keys-only read
        assert not moved


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
    """The served heads' driver table equals the one their own fit wrote: the re-fit's
    (data/_labs/efv5/efv5_refit_fit.json production, the served candidate) while
    efv5_refit.EFV_V5_REFIT_ON, else eFV v5 COMBINED's weights file."""
    import efv5_refit as R5
    refit = bool(R5.EFV_V5_REFIT_ON)
    if refit:
        cand = R5.served_candidate(json.loads(R5.WEIGHTS_PATH.read_text(encoding="utf-8")))
        fit = json.loads(R5.FIT_PATH.read_text(encoding="utf-8"))
        want = fit["production"][cand]["driver_tables"]
    else:
        want = json.loads(X.WEIGHTS_PATH.read_text(encoding="utf-8"))["weights"]

    def _no_se(t):
        # the stored re-fit head (efv5_refit._HEAD_FIELDS) keeps no standard errors, so
        # the SE columns are compared only where the served model carries them
        t = json.loads(json.dumps(t))
        for head in (t.get("heads") or {}).values():
            for r in (head or {}).get("drivers") or []:
                for k in ("se", "weight_se_pct_equiv", "at_bound"):
                    r.pop(k, None)
        return t

    models = S.production_models()
    for side, m in models.items():
        if m.get("model_id") != X.MODEL_ID:
            pytest.skip("eFV v5 COMBINED is not the served model")
        got = json.loads(json.dumps(X.weights_table(m)))
        if refit:
            got, exp = _no_se(got), _no_se(want[side])
        else:
            exp = want[side]
        assert got == exp, side


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
