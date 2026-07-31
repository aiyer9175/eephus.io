# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""S-XLINE gate lab (pre-registered: docs/efv-2026-07-23/GATES.md).

Protocol per side (hit, pit):
  1. Rebuild the training matrix with the blend OFF (env flag), snapshot rows.
  2. Rebuild with the blend ON, snapshot rows.
  3. Clause 1: every row without a covered adjustment must be IDENTICAL.
  4. Clause 2: efv_model.run(persist=False) on each matrix; debuted-KM pooled
     OOS Spearman of the shipped blend must not degrade by more than 0.003.
  5. Clause 3 (pre-flip half): max |delta| on *_rel features of changed rows.
Writes data/xfv_statcast_line_eval.json. Restores the ON/OFF state by
rebuilding the matrix a final time honoring the module DEFAULTS (so the tree
is left consistent with whatever ship decision the defaults encode).

Run: python -m tools.efv_statcast_line_lab      (from prospect-tracker/)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

POOL_BAR = -0.003          # clause 2: max tolerated pooled-rho degradation
RATE_PULL_BAR = 0.5        # clause 3: max |delta| on hitter rate features
ERA_PULL_BAR = 1.2         # clause 3: max |delta| on era_rel


def _flag_env(side: str, val: str | None):
    key = "EEPHUS_XLINE_PIT" if side == "pit" else "EEPHUS_XLINE_HIT"
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


def _build_matrix(side: str):
    import efv_dataset
    import efv_statcast_line
    efv_statcast_line._gap_index.cache_clear()
    efv_dataset.run(True, side)
    rows = json.loads(efv_dataset.matrix_path(side).read_text(encoding="utf-8"))
    return rows


def _row_key(r):
    return r.get("player_key")


def _eval_side(side: str) -> dict:
    import efv_model
    out = {"side": side}

    def _pooled(ev):
        block = (ev.get("evals") or ev).get("debuted_km") or {}
        try:
            return float(block["pooled_oos"]["blend"]["spearman"])
        except (KeyError, TypeError, ValueError):
            return None

    _flag_env(side, "0")
    off_rows = _build_matrix(side)
    off_eval = efv_model.run(persist=False, side=side)
    off_rho = _pooled(off_eval)

    _flag_env(side, "1")
    on_rows = _build_matrix(side)
    on_eval = efv_model.run(persist=False, side=side)
    on_rho = _pooled(on_eval)

    _flag_env(side, None)   # back to module defaults

    off_by = {_row_key(r): r for r in off_rows}
    on_by = {_row_key(r): r for r in on_rows}
    changed, max_pull, invariance_violations = [], {}, 0
    rate_keys = [k for k in (("k_rel", "bb_rel", "era_rel") if side == "pit" else
                             ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel",
                              "peak_ops_rel", "peak_obp_rel")) ]
    for pk, a in off_by.items():
        b = on_by.get(pk)
        if b is None:
            invariance_violations += 1
            continue
        ma, mb = (a.get("milb") or {}), (b.get("milb") or {})
        deltas = {}
        for k in rate_keys:
            va, vb = ma.get(k), mb.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and abs(va - vb) > 1e-12:
                deltas[k] = vb - va
        if deltas:
            changed.append({"player_key": pk, "deltas": {k: round(v, 4) for k, v in deltas.items()},
                            "debut_year": a.get("debut_year"), "kind": a.get("kind")})
            for k, v in deltas.items():
                max_pull[k] = max(max_pull.get(k, 0.0), abs(v))
        else:
            # no rate delta: the whole row (incl. milb) must be identical
            if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
                invariance_violations += 1

    n_changed = len(changed)
    clause1_pass = invariance_violations == 0
    clause2_delta = (on_rho - off_rho) if (on_rho is not None and off_rho is not None) else None
    clause2_pass = clause2_delta is not None and clause2_delta >= POOL_BAR
    pull_bar_viol = [k for k, v in max_pull.items()
                     if v > (ERA_PULL_BAR if k == "era_rel" else RATE_PULL_BAR)]
    clause3_pass = not pull_bar_viol

    out.update({
        "off_pooled_rho": off_rho, "on_pooled_rho": on_rho,
        "clause1_invariance": {"violations": invariance_violations, "pass": clause1_pass},
        "clause2_no_harm": {"delta": round(clause2_delta, 4) if clause2_delta is not None else None,
                            "bar": POOL_BAR, "pass": clause2_pass},
        "clause3_bounded_pull": {"max_abs_delta_by_key": {k: round(v, 4) for k, v in max_pull.items()},
                                 "violations": pull_bar_viol, "pass": clause3_pass,
                                 "n_changed_rows": n_changed},
        "changed_rows_sample": changed[:12],
        "verdict": "PASS" if (clause1_pass and clause2_pass and clause3_pass) else "FAIL",
    })
    return out


def main():
    results = {"generated_at": date.today().isoformat(),
               "experiment": "S-XLINE (docs/efv-2026-07-23/GATES.md)",
               "tool": "tools/efv_statcast_line_lab.py",
               "clause_m_measurement": {
                   "hit": {"delta_rho": 0.0253, "ci95": [0.0046, 0.0449], "p_gt0": 0.991,
                           "n_pairs": 776, "verdict": "PASS"},
                   "pit": {"delta_rho_xslg_arm": 0.0511, "ci95": [0.0115, 0.0907],
                           "p_gt0": 0.996, "n_pairs": 491, "verdict": "PASS"}},
               "sides": {}}
    for side in ("hit", "pit"):
        print(f"=== S-XLINE gate: {side} ===", flush=True)
        results["sides"][side] = _eval_side(side)
        s = results["sides"][side]
        print(f"  clause1 pass={s['clause1_invariance']['pass']} "
              f"clause2 delta={s['clause2_no_harm']['delta']} pass={s['clause2_no_harm']['pass']} "
              f"clause3 pass={s['clause3_bounded_pull']['pass']} "
              f"changed={s['clause3_bounded_pull']['n_changed_rows']} -> {s['verdict']}", flush=True)
    overall = {s: results["sides"][s]["verdict"] for s in results["sides"]}
    results["overall"] = overall
    (Path("data") / "xfv_statcast_line_eval.json").write_text(
        json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print("wrote data/xfv_statcast_line_eval.json", overall, flush=True)
    # leave the tree on the DEFAULT (module-constant) state
    for side in ("hit", "pit"):
        _build_matrix(side)
    print("matrices restored to module-default state", flush=True)


# ============================================================================
# AMENDMENT 2026-07-24 (docs/efv-2026-07-24/GATES.md): W-XLINE-W + W-XISO.
#
# Two registered arms on the SHIPPED S-XLINE hitter measurement layer:
#   W-XLINE-W  raise the hitter blend weight W_HIT 0.5 -> 0.7 (env EEPHUS_XLINE_WHIT).
#   W-XISO     add a fourth capped delta d_iso = w*cap(x_iso_gap, 0.060),
#              x_iso = xSLG - xBA, x_iso_gap = x_iso - iso (all within-Savant)
#              (env EEPHUS_XLINE_XISO=1). Both default-OFF; flips are wave-D.
#
# Clause M'/M re-read on the SAME measurement-pair protocol as the shipped
# study. The shipped study's driver script lived in a prior session scratch and
# is not in-tree; the protocol is RECONSTRUCTED from the module docstring +
# eval clause_m_measurement block, and cross-checked against the recorded hit
# result (delta_rho +0.0253, n_pairs 776). FROZEN reconstruction (no new
# freedom; every choice pinned to an in-tree convention):
#   - source pool: Savant AAA batter aggregates (arkmetric_forward_eval.savant_
#     rows, fetch=False), seasons N in {2023,2024,2025}, pa >= MIN_SAVANT_PA
#     (100; the CSV is already min_pas=100), full xBA/xOBP/xSLG fields present.
#   - blend (OPS family): obp' = obp + w*cap(xOBP-obp, D_CAP_OBP);
#     slg' = slg + w*cap(xSLG-slg, D_CAP_SLG); ops = obp'+slg' (identical caps
#     and algebra to efv_statcast_line.maybe_adjust_row).
#   - target: next-season (N+1) AAA OPS, largest-exposure AAA line (milb_history.
#     level_row), pa >= NEXT_PA_FLOOR (150 - the sibling S-XLINE-2/3 lab's
#     MIN_PA season-pair leg floor).
#   - metric: Spearman(predictor, next_OPS); delta = rho(blend) - rho(raw);
#     player-clustered percentile bootstrap, W0724_REPS reps, seed W0724_SEED.
# Recorded n=776 vs reconstructed n~808 differs only by live-season drift on the
# 2025->2026 leg (the 2026 AAA cache fills in daily); delta_rho at w=0.5 lands
# at +0.0267, inside the recorded CI. A minpa robustness sweep {150,175,200} is
# reported so the verdict is shown NOT to hinge on the reconstruction choice.
#
# Bars (GATES.md):
#   M'  (W-XLINE-W): rho(blend@0.7)-rho(raw) lo95 > 0 AND point(0.7) >= point(0.5).
#   M   (W-XISO):    rho(iso_blend@w)-rho(iso_raw) lo95 > 0 (next-season iso).
#   clause 1 invariance: uncovered rows byte-identical; flag-OFF == committed.
#   clause 2 no-harm:    in-matrix pooled OOS blend Spearman delta >= -0.003.
# The heavy in-matrix clauses REDIRECT the hitter matrix/report to a scratch
# path (monkeypatch of efv_dataset.matrix_path/report_path - no edit to the
# shared file) so the committed data/xfv_hitter_matrix.json is NEVER written
# and concurrent lanes are unaffected. pit side is untouched by either arm
# (both live in the hit branch of maybe_adjust_row), so pit no-harm holds by
# construction and is not rebuilt.
# ============================================================================

W0724_SEED = 20260724
W0724_REPS = 2000
MEAS_PAIRS = ((2023, 2024), (2024, 2025), (2025, 2026))
MIN_SAVANT_PA_MEAS = 100
NEXT_PA_FLOOR = 150
MINPA_SWEEP = (150, 175, 200)      # robustness; canonical = MINPA_SWEEP[0]
NO_HARM_BAR = -0.003


def _mf(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _cap_m(v, c):
    return max(-c, min(c, v))


def _rankdata_avg(a):
    import numpy as np
    a = np.asarray(a, float)
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    start = np.cumsum(cnt) - cnt
    return (start + (cnt + 1) / 2.0)[inv]


def _spearman_m(x, y):
    import numpy as np
    if len(x) < 8:
        return None
    rx, ry = _rankdata_avg(x), _rankdata_avg(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _meas_records(minpa):
    """Frozen measurement-pair pool: [{mid, avg,xba,obp,xobp,slg,xslg,
    next_ops, next_iso}] over MEAS_PAIRS."""
    import arkmetric_forward_eval as af
    import milb_history as mh

    def savidx(season):
        out = {}
        for r in af.savant_rows(season, "batter", fetch=False):
            mid = _mf(r.get("player_id"))
            pa = _mf(r.get("pa")) or 0.0
            if mid is not None and pa >= MIN_SAVANT_PA_MEAS:
                out[int(mid)] = r
        return out

    def target(season):
        idx = mh.player_index(season, "hitting", fetch=False)
        out = {}
        for mid, rows in idx.items():
            row = mh.level_row(rows, "AAA", "hitting")
            if row is None:
                continue
            pa = _mf(row.get("pa")) or 0.0
            ops, slg, avg = _mf(row.get("ops")), _mf(row.get("slg")), _mf(row.get("avg"))
            if pa >= minpa and None not in (ops, slg, avg):
                out[mid] = (ops, slg - avg)
        return out

    recs = []
    for a, b in MEAS_PAIRS:
        sav, nxt = savidx(a), target(b)
        for mid, r in sav.items():
            if mid not in nxt:
                continue
            avg, xba = _mf(r.get("ba")), _mf(r.get("xba"))
            obp, xobp = _mf(r.get("obp")), _mf(r.get("xobp"))
            slg, xslg = _mf(r.get("slg")), _mf(r.get("xslg"))
            if None in (avg, xba, obp, xobp, slg, xslg):
                continue
            n_ops, n_iso = nxt[mid]
            recs.append({"mid": mid, "avg": avg, "xba": xba, "obp": obp,
                         "xobp": xobp, "slg": slg, "xslg": xslg,
                         "next_ops": n_ops, "next_iso": n_iso})
    return recs


def _clustered_delta(recs, blend_fn, raw_fn, tgt_key):
    """point delta rho + player-clustered percentile-bootstrap lo/hi/p_gt0."""
    import numpy as np
    from collections import defaultdict
    import efv_statcast_line as xl
    byc = defaultdict(list)
    for i, r in enumerate(recs):
        byc[r["mid"]].append(i)
    clusters = list(byc.values())
    raw = np.array([raw_fn(r, xl) for r in recs])
    bl = np.array([blend_fn(r, xl) for r in recs])
    tg = np.array([r[tgt_key] for r in recs])
    point = _spearman_m(bl, tg) - _spearman_m(raw, tg)
    rng = np.random.default_rng(W0724_SEED)
    C = len(clusters)
    stats = []
    for _ in range(W0724_REPS):
        pick = rng.integers(0, C, size=C)
        idx = np.concatenate([clusters[p] for p in pick])
        rb, rr = _spearman_m(bl[idx], tg[idx]), _spearman_m(raw[idx], tg[idx])
        if rb is not None and rr is not None:
            stats.append(rb - rr)
    arr = np.asarray(stats)
    return {"delta_rho": round(point, 4),
            "lo95": round(float(np.percentile(arr, 2.5)), 4),
            "hi95": round(float(np.percentile(arr, 97.5)), 4),
            "p_gt0": round(float(np.mean(arr > 0)), 3),
            "n_pairs": len(recs), "n_players": C}


def _ops_raw(r, xl):
    return r["obp"] + r["slg"]


def _ops_blend(r, xl, w):
    return (r["obp"] + w * xl._cap(r["xobp"] - r["obp"], xl.D_CAP_OBP)
            + r["slg"] + w * xl._cap(r["xslg"] - r["slg"], xl.D_CAP_SLG))


def _iso_raw(r, xl):
    return r["slg"] - r["avg"]


def _iso_blend(r, xl, w):
    x_iso_gap = (r["xslg"] - r["xba"]) - (r["slg"] - r["avg"])
    return (r["slg"] - r["avg"]) + w * xl._cap(x_iso_gap, xl.D_CAP_ISO)


def _measurement_clauses():
    """M' (weight arm) + M (xiso arm) on the frozen protocol; canonical minpa
    plus a robustness sweep."""
    import efv_statcast_line as xl
    canon = MINPA_SWEEP[0]
    out = {"protocol": {
        "source": "Savant AAA batter aggregates, seasons 2023/2024/2025, "
                  "pa>=100 (arkmetric_forward_eval.savant_rows, fetch=False)",
        "target": f"next-season AAA OPS/ISO, level_row largest-exposure AAA line, "
                  f"pa>={NEXT_PA_FLOOR} (milb_history)",
        "blend": "capped within-Savant de-luck, identical caps/algebra to "
                 "efv_statcast_line.maybe_adjust_row",
        "bootstrap": f"player-clustered percentile, {W0724_REPS} reps, seed {W0724_SEED}",
        "canonical_minpa": canon, "robustness_minpa_sweep": list(MINPA_SWEEP),
        "recorded_shipped_hit": {"delta_rho": 0.0253, "n_pairs": 776,
                                 "ci95": [0.0046, 0.0449]},
        "reconstruction_note": "exact shipped driver script not in-tree; "
                               "reconstructed from the module docstring + "
                               "clause_m block; recorded n=776 vs ~808 here is "
                               "2025->2026 live-season fill drift",
    }}
    sweep = {}
    for minpa in MINPA_SWEEP:
        recs = _meas_records(minpa)
        w05 = _clustered_delta(recs, lambda r, x: _ops_blend(r, x, 0.5), _ops_raw, "next_ops")
        w07 = _clustered_delta(recs, lambda r, x: _ops_blend(r, x, 0.7), _ops_raw, "next_ops")
        w_hit_now = xl._w_hit()
        xiso = _clustered_delta(recs, lambda r, x: _iso_blend(r, x, w_hit_now),
                                _iso_raw, "next_iso")
        sweep[str(minpa)] = {"w05_delta": w05, "w07_delta": w07,
                             "xiso_delta": xiso, "xiso_w_hit": w_hit_now}
    out["minpa_sweep"] = sweep
    c = sweep[str(canon)]
    m_prime_pass = (c["w07_delta"]["lo95"] > 0
                    and c["w07_delta"]["delta_rho"] >= c["w05_delta"]["delta_rho"])
    m_pass = c["xiso_delta"]["lo95"] > 0
    out["W_XLINE_W_M_prime"] = {
        "point_0_5": c["w05_delta"]["delta_rho"], "point_0_7": c["w07_delta"]["delta_rho"],
        "w07_lo95": c["w07_delta"]["lo95"], "w07_p_gt0": c["w07_delta"]["p_gt0"],
        "n_pairs": c["w07_delta"]["n_pairs"],
        "clause_lo95_gt0": c["w07_delta"]["lo95"] > 0,
        "clause_point07_ge_point05": c["w07_delta"]["delta_rho"] >= c["w05_delta"]["delta_rho"],
        "verdict": "PASS" if m_prime_pass else "FAIL"}
    out["W_XISO_M"] = {
        "delta_rho": c["xiso_delta"]["delta_rho"], "lo95": c["xiso_delta"]["lo95"],
        "p_gt0": c["xiso_delta"]["p_gt0"], "n_pairs": c["xiso_delta"]["n_pairs"],
        "w_hit_used": c["xiso_w_hit"], "verdict": "PASS" if m_pass else "FAIL"}
    return out


# ------------------------------------------------------------ heavy clauses
_RATE_KEYS_HIT = ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel",
                  "peak_ops_rel", "peak_obp_rel")


def _scratch_dir():
    import tempfile
    d = Path(tempfile.gettempdir()) / "xline_w0724_scratch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _in_matrix_clauses():
    """Invariance + no-harm for both arms, hit side, in an ISOLATED scratch
    matrix (committed matrix never written)."""
    import efv_dataset
    import efv_model
    import efv_statcast_line as xl
    scr = _scratch_dir()
    committed = json.loads(efv_dataset.matrix_path("hit").read_text(encoding="utf-8"))
    _omp, _orp = efv_dataset.matrix_path, efv_dataset.report_path
    efv_dataset.matrix_path = lambda side="hit": (scr / "hit_matrix.json") if side == "hit" else _omp(side)
    efv_dataset.report_path = lambda side="hit": (scr / "hit_report.json") if side == "hit" else _orp(side)

    def build(env):
        for k in ("EEPHUS_XLINE_WHIT", "EEPHUS_XLINE_XISO"):
            os.environ.pop(k, None)
        os.environ["EEPHUS_XLINE_HIT"] = "1"
        for k, v in env.items():
            os.environ[k] = v
        xl._gap_index.cache_clear()
        efv_dataset.run(True, "hit")
        return json.loads((scr / "hit_matrix.json").read_text(encoding="utf-8"))

    def pooled():
        ev = efv_model.run(persist=False, side="hit")
        b = (ev.get("evals") or ev).get("debuted_km") or {}
        return float(b["pooled_oos"]["blend"]["spearman"])

    def invariance(base, trt):
        a = {r.get("player_key"): r for r in base}
        b = {r.get("player_key"): r for r in trt}
        changed, unc_viol, missing = 0, 0, 0
        for pk, ra in a.items():
            rb = b.get(pk)
            if rb is None:
                missing += 1
                continue
            ma, mb = (ra.get("milb") or {}), (rb.get("milb") or {})
            moved = any(isinstance(ma.get(k), (int, float)) and isinstance(mb.get(k), (int, float))
                        and abs(mb[k] - ma[k]) > 1e-12 for k in _RATE_KEYS_HIT)
            if moved:
                changed += 1
            elif json.dumps(ra, sort_keys=True) != json.dumps(rb, sort_keys=True):
                unc_viol += 1
        return changed, unc_viol, missing

    try:
        base = build({})
        base_pooled = pooled()
        base_eq_committed = json.dumps(base, sort_keys=True) == json.dumps(committed, sort_keys=True)
        w07 = build({"EEPHUS_XLINE_WHIT": "0.7"})
        w07_pooled = pooled()
        ch1, uv1, ms1 = invariance(base, w07)
        xiso = build({"EEPHUS_XLINE_XISO": "1"})
        xiso_pooled = pooled()
        ch2, uv2, ms2 = invariance(base, xiso)
        build({})   # leave scratch on module defaults
    finally:
        efv_dataset.matrix_path, efv_dataset.report_path = _omp, _orp
        for k in ("EEPHUS_XLINE_WHIT", "EEPHUS_XLINE_XISO", "EEPHUS_XLINE_HIT"):
            os.environ.pop(k, None)

    return {
        "isolation": "hit matrix/report redirected to scratch; committed "
                     "data/xfv_hitter_matrix.json never written",
        "baseline": {"pooled_oos": round(base_pooled, 4),
                     "equals_committed_matrix": base_eq_committed},
        "W_XLINE_W": {
            "pooled_oos": round(w07_pooled, 4),
            "no_harm_delta": round(w07_pooled - base_pooled, 4), "bar": NO_HARM_BAR,
            "no_harm_pass": (w07_pooled - base_pooled) >= NO_HARM_BAR,
            "invariance": {"changed_rows": ch1, "uncovered_violations": uv1,
                           "missing": ms1, "pass": uv1 == 0 and ms1 == 0 and base_eq_committed}},
        "W_XISO": {
            "pooled_oos": round(xiso_pooled, 4),
            "no_harm_delta": round(xiso_pooled - base_pooled, 4), "bar": NO_HARM_BAR,
            "no_harm_pass": (xiso_pooled - base_pooled) >= NO_HARM_BAR,
            "invariance": {"changed_rows": ch2, "uncovered_violations": uv2,
                           "missing": ms2, "pass": uv2 == 0 and ms2 == 0 and base_eq_committed}},
        "pit_side": "untouched by both arms (hit-branch only); no-harm holds by "
                    "construction, not rebuilt",
    }


def run_w0724():
    print("=== W-XLINE-W + W-XISO amendment (docs/efv-2026-07-24/GATES.md) ===", flush=True)
    print("[1/2] measurement clauses M'/M ...", flush=True)
    meas = _measurement_clauses()
    print(f"  M'(weight): {meas['W_XLINE_W_M_prime']['verdict']} "
          f"(pt0.5={meas['W_XLINE_W_M_prime']['point_0_5']} "
          f"pt0.7={meas['W_XLINE_W_M_prime']['point_0_7']} "
          f"lo95={meas['W_XLINE_W_M_prime']['w07_lo95']})", flush=True)
    print(f"  M (xiso)  : {meas['W_XISO_M']['verdict']} "
          f"(delta={meas['W_XISO_M']['delta_rho']} lo95={meas['W_XISO_M']['lo95']})", flush=True)
    print("[2/2] in-matrix invariance + no-harm (heavy) ...", flush=True)
    heavy = _in_matrix_clauses()
    w_pass = (meas["W_XLINE_W_M_prime"]["verdict"] == "PASS"
              and heavy["W_XLINE_W"]["no_harm_pass"] and heavy["W_XLINE_W"]["invariance"]["pass"])
    x_pass = (meas["W_XISO_M"]["verdict"] == "PASS"
              and heavy["W_XISO"]["no_harm_pass"] and heavy["W_XISO"]["invariance"]["pass"])
    block = {
        "generated_at": date.today().isoformat(),
        "experiment": "W-XLINE-W + W-XISO (docs/efv-2026-07-24/GATES.md, Phase 1a/1c)",
        "tool": "tools/efv_statcast_line_lab.py::run_w0724",
        "mechanism_flags": {
            "W_XLINE_W": "efv_statcast_line._w_hit(); env EEPHUS_XLINE_WHIT; "
                         "default W_HIT=0.5",
            "W_XISO": "efv_statcast_line._xiso_on() + D_CAP_ISO; env EEPHUS_XLINE_XISO; "
                      "default XISO_HIT_DEFAULT=False"},
        "measurement_clauses": meas,
        "in_matrix_clauses": heavy,
        "verdicts": {"W_XLINE_W": "PASS" if w_pass else "FAIL",
                     "W_XISO": "PASS" if x_pass else "FAIL"},
        "ship_rule": "both PASS -> wave-D flips W_HIT=0.7 + XISO_HIT_DEFAULT=True, "
                     "then ONE combined post-flip battery (3.0 FV ceiling vs a "
                     "single pre-flip snapshot) + regen. Flips NOT applied here.",
    }
    path = Path("data") / "xfv_statcast_line_eval.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    existing["amendment_2026_07_24"] = block
    path.write_text(json.dumps(existing, indent=1) + "\n", encoding="utf-8")
    print(f"wrote amendment_2026_07_24 block -> {path} "
          f"verdicts={block['verdicts']}", flush=True)
    return block


if __name__ == "__main__":
    # Bare / w0724 -> the 2026-07-24 amendment (NON-destructive: heavy clauses
    # redirect the hitter matrix to scratch, committed matrices never written).
    # `shipped` -> the original 2026-07-23 S-XLINE gate (rebuilds committed
    # matrices IN PLACE - do not run during parallel waves).
    if len(sys.argv) > 1 and sys.argv[1] == "shipped":
        main()
    else:
        run_w0724()
