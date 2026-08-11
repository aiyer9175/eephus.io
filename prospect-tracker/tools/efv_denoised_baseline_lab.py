# B-L6: the denoised-baseline fairness control.
#
# WHY THIS FILE EXISTS. Every published "eFV beats the consensus" claim compares eFV
# against the consensus AS SERVED. The served consensus is a noisy aggregate of noisy
# raters, so part of eFV's margin could be eFV beating the AGGREGATION ERROR rather than
# beating the raters. This lab re-runs the head-to-head against a consensus built by
# measured per-source precision instead, and adjudicates the result under the decision
# rule registered in docs/efv-2026-08-09/DENOISED_BASELINE_GATE.md BEFORE it ran.
#
# The control was impossible until 2026-08-10. Identifying per-source precision needs a
# THIRD instrument (two sources give three second moments against four unknowns), and
# there were only two scored sources until the Baseball America backfill landed.
# Baseball America is the instrument here and NOT a term in the baseline: adding it to
# the scored set collapses the common set 4,284 -> 295 and flips consensus_wins.
#
# THE PARITY PRECONDITION. This lab must score the SAME frame the incumbent floor was
# measured on, so it never reimplements the pool. It calls efv_mde_lab._load_h2h and
# _h2h_pass, and it recovers the extra per-row channels it needs (fangraphs, pipeline,
# board year) by running the SAME _h2h_pass over shallow pool copies whose `rows` lists
# carry a different payload in the same slots. That trick is only legitimate if the
# emission order is identical, so the grade leg of every instrumented pass is asserted
# bit-identical to the real one, and a reconstructed (consensus, war) pass is asserted
# bit-identical to the real frame before any arm is scored. Parity failure raises and
# writes nothing.
#
# Run: python tools/efv_denoised_baseline_lab.py parity      (preconditions only)
#      python tools/efv_denoised_baseline_lab.py run [B]     (measure + write)
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import source_backtest as SB                                   # noqa: E402  read-only
from efv_mde_lab import _load_h2h, _h2h_pass, wrho, SIDES       # noqa: E402  read-only
from efv_power_lab import (                                    # noqa: E402  read-only
    _h2h_cluster_ids, scored_frame, frame_delta, boot_cond_cluster, summarize,
)

OUT_PATH = ROOT / "data" / "xfv_denoised_baseline_eval.json"
PRECISION_PATH = ROOT / "data" / "source_cohort_accuracy.json"
SEED = 20260809
Z95_ONE = 1.645
Z95_TWO = 1.96

# The incumbent registration, data/xfv_power_eval.json ->
# partb_floors.cells.headtohead_common, measured 2026-08-08.
#
# AMENDMENT 1 (DENOISED_BASELINE_GATE.md section 7a): these were registered as hard
# abort conditions and they FIRED - the frame moved under this program's own BA ingest
# and identity repairs. They are now a DRIFT REPORT. Structural integrity (parity,
# finite rho, non-collapsed clusters) remains a hard abort, and the incumbent is
# re-derived on today's frame inside the same run so no 2026-08-08 sd is ever mixed
# with a 2026-08-10 delta. That mixing has already crossed a verdict boundary twice in
# this program.
REG_ROWS = 3224
REG_CLUSTERS = 1051
REG_DELTA = 0.03318
REG_CONS_RHO = 0.32070
REG_MDE95_COND = 0.0322
REG_MDE95_REFIT = 0.0345
DRIFT_TOL = 5e-5

# WEIGHT_CLAMP=(0.6, 1.5) on the shipped consensus maps to alpha in [0.2857, 0.7143].
# C2 draws inside exactly that reachable range, so "any admissible reweighting" means
# admissible to the SHIPPED estimator, not an arbitrary interval.
CLAMP_ALPHA_LO, CLAMP_ALPHA_HI = 0.2857, 0.7143
C2_DRAWS = 200


# ------------------------------------------------------------------ precision inputs
def load_precision() -> dict:
    """b_s and sigma_s from C-A1's EM/FIML estimator, frozen.

    Read from the shipped artifact rather than hardcoded, so a re-run of C-A1 that
    moves the estimate moves this control too and cannot silently disagree with the
    page that publishes it.
    """
    d = json.loads(PRECISION_PATH.read_text(encoding="utf-8"))
    p = d["precision_label_free"]
    if not p.get("identified"):
        raise SystemExit("precision_label_free is not identified; B-L6 cannot run")
    em = p["estimator_primary_em_fiml"]
    src = list(em["sources"])
    out = {
        "sources": src,
        "b": {s: float(v) for s, v in zip(src, em["b"])},
        "sigma2": {s: float(v) for s, v in zip(src, em["sigma2"])},
        "reliability": {s: float(v) for s, v in zip(src, em["reliability"])},
        "gls_weight": {s: float(v) for s, v in zip(src, em["gls_weight"])},
        "alpha_fg": float(em["alpha_fg"]),
        "sheppard": float(em["sheppard_variance_h2_over_12"]),
        "estimator": "estimator_primary_em_fiml",
        "artifact_generated_at": d.get("generated_at"),
    }
    # The weight identity is the whole methodological point of C-A1; check it rather
    # than trust the stored column, because a stored column can go stale against b/sigma.
    for s in src:
        want = out["b"][s] / out["sigma2"][s]
        if abs(want - out["gls_weight"][s]) > 1e-4:
            raise AssertionError(
                f"gls_weight for {s} is not b/sigma^2: stored {out['gls_weight'][s]}, "
                f"recomputed {want:.5f}")
    return out


# ------------------------------------------------------------------------- the frame
def _rich_records() -> dict[str, list[tuple]]:
    """Per player_key, the common-set rows carrying every channel this lane needs.

    Mirrors efv_mde_lab._load_h2h's universe loop EXACTLY: same universe, same resolved
    years, same rater requirement, same iteration order, same append order. It differs
    only in the payload it keeps. The reconstruction is not trusted; `preconditions`
    proves it reproduces the real frame bit-for-bit.
    """
    uni = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(uni, SB.date.today().year)
    raters = list(SB.SCORED_SOURCES) + [SB.CONSENSUS_KEY]
    by_key: dict[str, list] = {}
    for p in uni:
        out = SB._outcome(p)
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                by_key.setdefault(p.get("player_key"), []).append((
                    float(g[SB.CONSENSUS_KEY]),          # 0 consensus as served
                    float(out["war"]),                   # 1 target
                    float(g[SB.SCORED_SOURCES[0]]),      # 2 fangraphs
                    float(g[SB.SCORED_SOURCES[1]]),      # 3 mlb_pipeline
                    float(y),                            # 4 board year
                    float(_n_sources(p, y)),             # 5 distinct graded sources
                ))
    return by_key


def _n_sources(p: dict, year: int) -> int:
    """How many distinct outlets published an FV for this player-year.

    The served consensus is NOT a two-source aggregate, so a two-source denoised
    baseline may lose to it on INFORMATION rather than on CONSTRUCTION. That confound
    has to be measured, not assumed away.
    """
    lo, hi = f"{year}{SB._WINDOW_START_MMDD}", f"{year}{SB._WINDOW_END_MMDD}"
    seen = set()
    for pt in (p.get("points") or []):
        sd = pt.get("snapshot_date")
        if not (sd and lo <= sd < hi):
            continue
        for src, ps in ((pt.get("per_source") or {})).items():
            if isinstance(ps, dict) and ps.get("fv_published") is not None:
                seen.add(src)
    return len(seen)


def _repayload(P, recs, keys, slot_a, slot_b):
    """A shallow pool copy whose `rows` carry (channel[slot_a], channel[slot_b]).

    _h2h_pass reads X / y / w / fv / dy / rows and nothing else, and its fold selection
    and fits never touch `rows`, so a shallow copy with a different row payload is a
    legitimate run of the SAME function through the SAME emission path.
    """
    out = {}
    for s, D in P.items():
        d = dict(D)
        d["rows"] = [[(r[slot_a], r[slot_b]) for r in (recs.get(k) or [])]
                     for k in keys[s]]
        out[s] = d
    return out


def _pool_keys(P):
    """player_key per pool row, in pool order, recovered from the prepped matrices.

    _load_h2h builds `rows` as [by_key.get(r["player_key"]) or [] for r in prep], so
    replaying _prep on the same matrices in the same order recovers the key list that
    indexed it. Length equality against D["n"] is asserted by the caller.
    """
    import efv_model as E
    from efv_dataset import matrix_path
    out = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        prep = E._prep(full, "target_censored", side)
        out[side] = [r["player_key"] for r in prep]
    return out


def build_channels(verbose=True):
    """The real frame plus every aligned per-row channel, with parity proved.

    Returns a dict of numpy arrays all of length n_rows, in _h2h_pass emission order:
      efv, cons, war, fg, mp, year, clu, side
    """
    t0 = time.time()
    P, n_common_players = _load_h2h()
    real = _h2h_pass(P)
    g, c, t = real
    if verbose:
        print(f"  real frame: {len(t)} rows, {n_common_players} common-set players "
              f"({time.time()-t0:.0f}s)", flush=True)

    keys = _pool_keys(P)
    for s in SIDES:
        if len(keys[s]) != P[s]["n"]:
            raise AssertionError(f"pool key replay length mismatch on {s}: "
                                 f"{len(keys[s])} vs {P[s]['n']}")
    recs = _rich_records()

    # --- PARITY GATE. Rebuild the REAL payload from the reconstruction and require the
    # whole frame back bit-identical. If this passes, every other channel recovered
    # through the same path is aligned by construction.
    Pc = _repayload(P, recs, keys, 0, 1)
    gc_, cc_, tc_ = _h2h_pass(Pc)
    for name, a, b in (("efv", g, gc_), ("consensus", c, cc_), ("war", t, tc_)):
        if not np.array_equal(a, b):
            raise AssertionError(
                f"PARITY FAILED on the {name} leg: the reconstructed record map does "
                f"not reproduce efv_mde_lab._load_h2h. Refusing to score.")
    if verbose:
        print("  parity: reconstructed frame is bit-identical on all three legs",
              flush=True)

    # --- extra channels, each asserting the grade leg came back unchanged
    def chan(slot_a, slot_b, label):
        gg, aa, bb = _h2h_pass(_repayload(P, recs, keys, slot_a, slot_b))
        if not np.array_equal(gg, g):
            raise AssertionError(f"instrumented pass for {label} moved the grade leg")
        return aa, bb

    fg, mp = chan(2, 3, "fangraphs/pipeline")
    year, _cons2 = chan(4, 0, "board year")
    if not np.array_equal(_cons2, c):
        raise AssertionError("the board-year pass did not return the consensus leg")
    nsrc, _cons3 = chan(5, 0, "source count")
    if not np.array_equal(_cons3, c):
        raise AssertionError("the source-count pass did not return the consensus leg")

    clu, side = _h2h_cluster_ids(P, real)
    return {
        "P": P, "efv": g, "cons": c, "war": t, "fg": fg, "mp": mp,
        "year": year.astype(int), "nsrc": nsrc.astype(int), "clu": clu, "side": side,
        "n_common_players": int(n_common_players),
        "recs": recs, "keys": keys,
        "elapsed_s": round(time.time() - t0, 1),
    }


def preconditions(ch, verbose=True):
    """Structural integrity (hard abort) plus the drift report against the 2026-08-08
    registration (informational). See AMENDMENT 1."""
    n = int(len(ch["war"]))
    nclu = int(len(np.unique(ch["clu"])))
    cons_rho = wrho(ch["cons"], ch["war"])
    efv_rho = wrho(ch["efv"], ch["war"])
    delta = efv_rho - cons_rho

    fatal = []
    if not (np.isfinite(cons_rho) and np.isfinite(efv_rho)):
        fatal.append("a leg produced a non-finite rho")
    if n < 2000:
        fatal.append(f"scored rows collapsed to {n}")
    if nclu < 800:
        fatal.append(f"player clusters collapsed to {nclu}")
    if not np.all(np.isfinite(ch["fg"])) or not np.all(np.isfinite(ch["mp"])):
        fatal.append("a per-source channel carries non-finite values")

    drift = {
        "registered_basis": "2026-08-08, data/xfv_power_eval.json headtohead_common",
        "rows": {"registered": REG_ROWS, "today": n, "change": n - REG_ROWS},
        "clusters": {"registered": REG_CLUSTERS, "today": nclu,
                     "change": nclu - REG_CLUSTERS},
        "consensus_rho": {"registered": REG_CONS_RHO, "today": round(cons_rho, 5),
                          "change": round(cons_rho - REG_CONS_RHO, 5)},
        "efv_rho": {"registered": 0.35387, "today": round(efv_rho, 5),
                    "change": round(efv_rho - 0.35387, 5)},
        "delta": {"registered": REG_DELTA, "today": round(delta, 5),
                  "change": round(delta - REG_DELTA, 5)},
        "frame_moved": bool(n != REG_ROWS or abs(delta - REG_DELTA) > DRIFT_TOL),
        "cause": ("the cluster count is unchanged, so the eFV matrix pool did not move; "
                  "what grew is the common-set rows those same players own, from this "
                  "program's Baseball America backfill and identity repairs"),
    }
    if verbose:
        print(f"  n_rows {n}  clusters {nclu}  cons {cons_rho:.5f}  "
              f"efv {efv_rho:.5f}  delta {delta:+.5f}", flush=True)
        if drift["frame_moved"]:
            print(f"  DRIFT vs the 2026-08-08 registration: rows {n - REG_ROWS:+d}, "
                  f"delta {delta - REG_DELTA:+.5f} -> the incumbent is re-derived on "
                  f"today's frame (AMENDMENT 1)", flush=True)
    return {"n_rows": n, "n_clusters": nclu, "consensus_rho": round(cons_rho, 5),
            "efv_rho": round(efv_rho, 5), "delta": round(delta, 5),
            "structurally_sound": not fatal, "fatal": fatal, "drift": drift}


# ------------------------------------------------------------------- the baselines
def _center(x, year, per_year=True):
    """Subtract a_s. Per (source, board year) by default.

    a_s is a free per-source intercept in the C-A1 model, and a source that rebases its
    published scale between vintages has the rebase read as signal without this. The
    centering is computed ONCE on the full scored frame and then held fixed: it is part
    of the baseline's DEFINITION, like a published scale, not a fitted prediction.
    """
    out = np.asarray(x, dtype=float).copy()
    if not per_year:
        return out - out.mean()
    for y in np.unique(year):
        m = year == y
        out[m] = out[m] - out[m].mean()
    return out


def build_arms(ch, prec):
    """Every registered baseline arm, as {name: score array}. P1 is the primary."""
    fg, mp, yr = ch["fg"], ch["mp"], ch["year"]
    s_fg, s_mp = SB.SCORED_SOURCES[0], SB.SCORED_SOURCES[1]
    b, s2 = prec["b"], prec["sigma2"]

    cf, cm = _center(fg, yr), _center(mp, yr)
    w_fg, w_mp = b[s_fg] / s2[s_fg], b[s_mp] / s2[s_mp]

    arms = {}
    arms["P0_published_consensus"] = np.asarray(ch["cons"], dtype=float)
    arms["P1_gls_precision"] = w_fg * cf + w_mp * cm

    # S1: Sheppard-corrected sigma^2. The lattice variance h^2/12 is REMOVED from the
    # noise estimate before weighting, i.e. the opposite of C-A1's served-aggregator
    # choice, run here because a baseline definition can argue it either way.
    sh = prec["sheppard"]
    s2c = {k: max(v - sh, 1e-6) for k, v in s2.items()}
    arms["S1_sheppard_corrected"] = (b[s_fg] / s2c[s_fg]) * cf + (b[s_mp] / s2c[s_mp]) * cm

    # S2: shrink the GLS estimate toward the per-board-year mean by reliability.
    # Shrinking toward a PER-YEAR mean is a within-year affine map, not a global
    # monotone one, so it can move a pooled Spearman even though a global shrink cannot.
    rel = prec["reliability"]
    k = 0.5 * (rel[s_fg] + rel[s_mp])
    p1 = arms["P1_gls_precision"]
    sh2 = p1.copy()
    for y in np.unique(yr):
        m = yr == y
        sh2[m] = k * p1[m] + (1 - k) * p1[m].mean()
    arms["S2_reliability_shrunk"] = sh2

    # S3: global centering only, the sensitivity to the per-year choice in S/P1.
    arms["S3_global_centering"] = (w_fg * _center(fg, yr, per_year=False)
                                   + w_mp * _center(mp, yr, per_year=False))

    # S4: equal weight, alpha = 0.5. Isolates "any principled recombination" from
    # "recombination BY MEASURED PRECISION".
    arms["S4_equal_weight"] = 0.5 * cf + 0.5 * cm

    # C1: the weights exchanged between the two sources. If this also beats the served
    # consensus the finding is about consensus.py, not about precision.
    arms["C1_weights_swapped"] = w_mp * cf + w_fg * cm
    return arms


def mechanism(ch, arms):
    """Why the per-year-centered arms lose, and what the served consensus is actually
    winning on. Diagnostics, never gates.

    Two candidate explanations have to be separated before any verdict means anything:

    1. CONSTRUCTION. The pooled Spearman mixes board years. Centering each source inside
       its board year removes the year-level location differences, and cohort years
       differ systematically in realized WAR, so a within-year transform strips signal a
       POOLED rank statistic was using. If this is the cause, the same arm without
       per-year centering should recover it.
    2. INFORMATION. The served consensus is not a two-source aggregate. If it blends
       more outlets than FanGraphs and Pipeline on these rows, a two-source baseline
       loses on inputs rather than on method, and the control is answering a different
       question than the one it was asked.
    """
    t, cons, yr = ch["war"], ch["cons"], ch["year"]
    out = {}

    # --- 1. how much of the pooled statistic is cross-year
    within = []
    for y in np.unique(yr):
        m = yr == y
        if int(m.sum()) >= 30:
            r = wrho(cons[m], t[m])
            if np.isfinite(r):
                within.append({"year": int(y), "n": int(m.sum()),
                               "consensus_rho": round(float(r), 5)})
    pooled = wrho(cons, t)
    mean_within = float(np.mean([w["consensus_rho"] for w in within])) if within else float("nan")
    out["pooled_vs_within_year"] = {
        "pooled_consensus_rho": round(float(pooled), 5),
        "mean_within_year_consensus_rho": round(mean_within, 5),
        "cross_year_contribution": round(float(pooled) - mean_within, 5),
        "by_year": within,
        "reading": ("if the pooled rho materially exceeds the mean within-year rho, the "
                    "statistic is partly ranking cohorts against each other, and any "
                    "per-year centering of a baseline deletes exactly that part"),
    }

    # --- 2. is the served consensus a two-source object on these rows?
    ns = ch["nsrc"]
    vals, cnts = np.unique(ns, return_counts=True)
    out["consensus_input_breadth"] = {
        "rows_by_distinct_source_count": {int(v): int(c) for v, c in zip(vals, cnts)},
        "mean_sources_per_row": round(float(ns.mean()), 3),
        "share_rows_with_more_than_two": round(float((ns > 2).mean()), 4),
        "reading": ("the denoised arms combine FanGraphs and Pipeline only. Every row "
                    "above two sources is information the served consensus has and the "
                    "baseline does not, which is a confound in the served consensus's "
                    "favour and must be stated wherever this control is quoted"),
    }
    # The same contrast restricted to rows the baseline is NOT handicapped on.
    m2 = ns <= 2
    if int(m2.sum()) >= 200:
        row = {"n_rows": int(m2.sum())}
        for name, sc in arms.items():
            row[name] = round(float(wrho(np.asarray(sc)[m2], t[m2])), 5)
        row["efv"] = round(float(wrho(ch["efv"][m2], t[m2])), 5)
        row["reading"] = ("restricted to rows where the served consensus had at most the "
                          "same two sources the baseline uses, so construction is "
                          "compared without the information gap")
        out["two_source_rows_only"] = row
    return out


def c2_random_weights(ch, rng, draws=C2_DRAWS):
    """Random admissible reweightings inside the shipped WEIGHT_CLAMP alpha range."""
    cf, cm = _center(ch["fg"], ch["year"]), _center(ch["mp"], ch["year"])
    t, cons = ch["war"], ch["cons"]
    base = wrho(cons, t)
    rhos = []
    for _ in range(draws):
        a = float(rng.uniform(CLAMP_ALPHA_LO, CLAMP_ALPHA_HI))
        rhos.append(wrho(a * cf + (1 - a) * cm, t))
    r = np.array(rhos, dtype=float)
    return {
        "draws": int(draws),
        "alpha_range": [CLAMP_ALPHA_LO, CLAMP_ALPHA_HI],
        "published_consensus_rho": round(base, 5),
        "mean_rho": round(float(r.mean()), 5),
        "min_rho": round(float(r.min()), 5),
        "max_rho": round(float(r.max()), 5),
        "share_beating_published": round(float((r > base).mean()), 4),
        "interpretation": (
            "if a majority of arbitrary admissible reweightings already beat the "
            "served consensus, the finding is a defect report against consensus.py's "
            "construction, not evidence that precision weighting works"),
    }


# ------------------------------------------------------------------------ the floors
def _frame_for(ch, baseline):
    return scored_frame(
        pa=ch["efv"], pb=baseline, y=ch["war"], w=None, blk=ch["side"], clu=ch["clu"],
        target="war", leg_names=("efv", "baseline"), label="headtohead_denoised")


def refit_draws(ch, slot_scores, B, rng, verbose=True):
    """E_refit for a denoised arm: resample the eFV matrix pool BY PLAYER, refit the
    forward chain, and rescore BOTH legs on the rows the resampled players own.

    The baseline is a per-common-set-row quantity, so it rides the SAME instrumented
    pass: a pool copy whose rows carry (baseline_score, war) is emitted through the
    identical fold selection and therefore stays aligned to the refit grade leg under
    any `sel`. This is the same protocol and the same estimand as
    efv_mde_lab.headtohead, which is what makes the floor comparable to the incumbent's.
    """
    P = ch["P"]
    # The arm's score is one value per EMITTED row, but a pool copy needs it indexed by
    # (pool row, within-player index). _h2h_pass emits by fold and only for scored test
    # rows, so that map is not the trivial enumeration of the pool; recover both
    # coordinates with an instrumented pass and invert it.
    off = 0
    inst = {}
    for s in SIDES:
        D = P[s]
        d = dict(D)
        d["rows"] = [[(float(off + i_row), float(j)) for j in range(len(rw))]
                     for i_row, rw in enumerate(D["rows"])]
        inst[s] = d
        off += D["n"]
    gi, pool_idx, within_idx = _h2h_pass(inst)
    if not np.array_equal(gi, ch["efv"]):
        raise AssertionError("the coordinate pass moved the grade leg")
    score_by = {}
    for k in range(len(slot_scores)):
        score_by[(int(pool_idx[k]), int(within_idx[k]))] = float(slot_scores[k])

    # A pool row that no fold ever scored owns common-set rows with no score. Under a
    # bootstrap `sel` such a row can be drawn INTO a scored fold, so it needs a value.
    # It gets NaN, which wrho would propagate silently, so instead the count is reported
    # and the rows are filled with the arm mean - a choice that must be visible rather
    # than a KeyError deep in a resample.
    fill = float(np.mean(slot_scores))
    n_uncovered = 0
    off = 0
    Ps = {}
    for s in SIDES:
        D = P[s]
        d = dict(D)
        rows = []
        for i_row, rw in enumerate(D["rows"]):
            out_rw = []
            for j in range(len(rw)):
                key = (off + i_row, j)
                if key not in score_by:
                    n_uncovered += 1
                out_rw.append((score_by.get(key, fill), float(rw[j][1])))
            rows.append(out_rw)
        d["rows"] = rows
        Ps[s] = d
        off += D["n"]

    draws = []
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in P}
        r = _h2h_pass(P, sel)
        rb = _h2h_pass(Ps, sel)
        if r is None or rb is None:
            continue
        gg, _cc, tt = r
        _gb, bb, tb = rb
        if not np.array_equal(tt, tb):
            raise AssertionError("baseline pass desynchronized from the grade pass")
        d = wrho(gg, tt) - wrho(bb, tt)
        if np.isfinite(d):
            draws.append(d)
        if verbose and (i + 1) % 250 == 0:
            print(f"    refit {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    return draws, n_uncovered


# ----------------------------------------------------------------------- adjudication
def adjudicate(d1, mde_cond, mde_refit, rho_p1, rho_p0, noop_rho):
    """The registered decision rule. Order matters: informativeness and the no-op check
    come BEFORE the survive/collapse test, so a baseline that did not improve can never
    be reported as a win for eFV."""
    if noop_rho is not None and noop_rho >= 0.999:
        return "NO_OP", ("the denoised baseline ranks these rows the same as the served "
                         "consensus, so this statistic cannot see the reweighting")
    if rho_p1 <= rho_p0:
        return "UNINFORMATIVE", ("the denoised construction is not a better aggregate on "
                                 "this frame, so it says nothing about eFV's margin")
    if d1 < 0:
        return "REVERSAL", "the denoised consensus outranks eFV on the common set"
    if d1 >= mde_cond:
        return "SURVIVES", ("the margin clears its E_cond floor against the better "
                            "baseline, at the same strength as before and no higher: "
                            "E_cond win, E_refit null")
    return "COLLAPSES", ("the E_cond win the site rests on does not survive a "
                         "precision-weighted baseline")


def run(B=2000, write=True, verbose=True):
    t_all = time.time()
    prec = load_precision()
    if verbose:
        print("=== B-L6 1/6: frame + parity ===", flush=True)
    ch = build_channels(verbose=verbose)
    pre = preconditions(ch, verbose=verbose)
    if not pre["structurally_sound"]:
        raise SystemExit("ABORT (structural): " + "; ".join(pre["fatal"]))

    if verbose:
        print("=== B-L6 2/6: arms ===", flush=True)
    arms = build_arms(ch, prec)
    t, cons = ch["war"], ch["cons"]
    rho0 = wrho(cons, t)
    efv_rho = wrho(ch["efv"], t)
    arm_rows = {}
    for name, sc in arms.items():
        r = wrho(sc, t)
        arm_rows[name] = {
            "baseline_rho": round(r, 5),
            "delta_vs_published_baseline": round(r - rho0, 5),
            "efv_minus_baseline": round(efv_rho - r, 5),
            "rank_corr_with_published": round(wrho(sc, cons), 5),
        }
        if verbose:
            print(f"  {name:28s} rho {r:.5f}  vs published {r-rho0:+.5f}  "
                  f"efv-margin {efv_rho-r:+.5f}", flush=True)

    if verbose:
        print("=== B-L6 3/6: E_cond floors (cluster, B=%d) ===" % B, flush=True)
    floors = {}
    for name, sc in arms.items():
        # Every arm draws from the SAME stream (SEED + 7, fresh generator per arm), so
        # arm-to-arm floor differences are the statistic moving and never the seed.
        # Never key a seed on hash(): it is salted per process and would break repro.
        F = _frame_for(ch, sc)
        pt = frame_delta(F)
        dr = boot_cond_cluster(F, B, np.random.default_rng(SEED + 7), mode="cluster")
        floors[name] = summarize(dr, pt)
        floors[name]["point_delta"] = round(float(pt), 5)
        if verbose:
            print(f"  {name:28s} delta {pt:+.5f}  MDE95_cond "
                  f"{floors[name]['MDE95']:.4f}  {floors[name]['verdict']}", flush=True)

    if verbose:
        print("=== B-L6 4/6: E_refit floors, incumbent + both primaries (B=%d) ===" % B,
              flush=True)
    # AMENDMENT 1: the incumbent is re-derived HERE, on today's frame, at the same B and
    # the same seed as the challenger. This is the whole point - a 2026-08-08 sd against
    # a 2026-08-10 delta is the mixing that has already crossed a verdict boundary twice.
    # AMENDMENT 2: S3 carries an E_refit floor too, because it is the corrected primary.
    refit_legs = {}
    for nm in ("P0_published_consensus", "P1_gls_precision", "S3_global_centering"):
        sc = arms[nm]
        dr, n_uncov = refit_draws(ch, sc, B, np.random.default_rng(SEED + 1),
                                  verbose=verbose)
        Fx = _frame_for(ch, sc)
        px = frame_delta(Fx)
        row = summarize(dr, px)
        row["point_delta"] = round(float(px), 5)
        row["common_rows_never_scored_in_any_fold"] = int(n_uncov)
        row["uncovered_fill"] = ("arm mean, reachable only when a bootstrap draw pulls a "
                                 "never-scored pool row into a scored fold")
        refit_legs[nm] = row
        if verbose:
            print(f"  {nm:28s} delta {px:+.5f}  MDE95_refit {row['MDE95']:.4f}  "
                  f"{row['verdict']}", flush=True)
    refit = refit_legs["P1_gls_precision"]
    p1 = arms["P1_gls_precision"]
    pt1 = frame_delta(_frame_for(ch, p1))

    if verbose:
        print("=== B-L6 5/6: C2 random admissible reweightings ===", flush=True)
    c2 = c2_random_weights(ch, np.random.default_rng(SEED + 2))

    if verbose:
        print("=== B-L6 6/6: mechanism diagnostics ===", flush=True)
    mech = mechanism(ch, arms)

    d1 = float(pt1)
    verdict, why = adjudicate(
        d1, floors["P1_gls_precision"]["MDE95"], refit["MDE95"],
        wrho(p1, t), rho0, wrho(p1, cons))

    # AMENDMENT 2. The registered primary applies a per-board-year centering that the
    # incumbent baseline does not have, so P1 is not like-for-like: it is a denoised
    # consensus PLUS a within-year transform. S3 is the same GLS weights with a global
    # per-source intercept, which is the correct like-for-like form. It is adjudicated
    # under the IDENTICAL rule and reported beside the registered primary, never
    # instead of it. Note the direction: the correction moves the verdict AGAINST eFV,
    # which is why it is not spec-shopping.
    s3 = arms["S3_global_centering"]
    d3 = float(frame_delta(_frame_for(ch, s3)))
    v3, w3 = adjudicate(d3, floors["S3_global_centering"]["MDE95"],
                        refit_legs["S3_global_centering"]["MDE95"],
                        wrho(s3, t), rho0, wrho(s3, cons))

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_denoised_baseline_lab.py run",
        "registration": "docs/efv-2026-08-09/DENOISED_BASELINE_GATE.md",
        "lane": "B-L6 denoised-baseline fairness control",
        "seed": SEED,
        "B": int(B),
        "basis": {
            "frame": "the incumbent head-to-head common set, unchanged",
            "n_rows": pre["n_rows"],
            "n_clusters": pre["n_clusters"],
            "common_set_players": ch["n_common_players"],
            "target_column": "war",
            "statistic": "unweighted pooled Spearman",
            "parity_proved": True,
            "vintage_disciplined": False,
            "vintage_note": (
                "per-source precision is estimable for board years 2023-2026 only, and "
                "MIN_LAG_YEARS=3 keeps the scored window at 2014-2024, so the baseline "
                "is DEFINED using an estimate computed partly on the rows it scores. "
                "Legitimate for a baseline definition, which is not a prediction; NOT "
                "quotable as an out-of-sample result. This handicaps eFV, not the "
                "baseline, and the write-up must say so wherever the number appears."),
            "baseball_america_role": (
                "identifying third instrument only. It is not a term in the baseline: "
                "two sources give three second moments against four unknowns, so b and "
                "sigma are unidentified without it. Adding BA to SCORED_SOURCES would "
                "collapse the common set 4,284 -> 295 and is not done here."),
        },
        "precision_inputs": prec,
        "incumbent_as_registered_2026_08_08": {
            "consensus_rho": REG_CONS_RHO,
            "efv_rho": 0.35387,
            "delta": REG_DELTA,
            "MDE95_E_refit": REG_MDE95_REFIT,
            "MDE95_E_cond": REG_MDE95_COND,
            "verdict_E_refit": "NULL (0.963x)",
            "verdict_E_cond": "RESOLVABLE WIN (1.031x)",
            "source": "data/xfv_power_eval.json partb_floors.cells.headtohead_common",
            "STALE": True,
            "why_stale": pre["drift"]["cause"],
        },
        "incumbent_rederived_today": {
            "consensus_rho": pre["consensus_rho"],
            "efv_rho": pre["efv_rho"],
            "delta": pre["delta"],
            "MDE95_E_cond": floors["P0_published_consensus"]["MDE95"],
            "MDE95_E_refit": refit_legs["P0_published_consensus"]["MDE95"],
            "verdict_E_cond": floors["P0_published_consensus"]["verdict"],
            "verdict_E_refit": refit_legs["P0_published_consensus"]["verdict"],
            "margin_over_E_cond": (
                round(abs(pre["delta"]) / floors["P0_published_consensus"]["MDE95"], 3)
                if floors["P0_published_consensus"]["MDE95"] else None),
            "margin_over_E_refit": (
                round(abs(pre["delta"]) / refit_legs["P0_published_consensus"]["MDE95"], 3)
                if refit_legs["P0_published_consensus"]["MDE95"] else None),
            "note": ("AMENDMENT 1. Same frame, same B, same seeds as every challenger "
                     "arm in this artifact. This is the number the site's head-to-head "
                     "claim actually rests on today, and it supersedes the row above."),
        },
        "drift_vs_registration": pre["drift"],
        "arms": arm_rows,
        "floors_E_cond": floors,
        "floors_E_refit": refit_legs,
        "controls": {"C2_random_admissible_weights": c2},
        "mechanism": mech,
        "primary_as_registered": {
            "arm": "P1_gls_precision",
            "delta": round(d1, 5),
            "MDE95_E_cond": floors["P1_gls_precision"]["MDE95"],
            "MDE95_E_refit": refit["MDE95"],
            "margin_over_E_cond": round(abs(d1) / floors["P1_gls_precision"]["MDE95"], 3)
                                  if floors["P1_gls_precision"]["MDE95"] else None,
            "margin_over_E_refit": round(abs(d1) / refit["MDE95"], 3) if refit["MDE95"] else None,
            "verdict": verdict,
            "verdict_why": why,
        },
        "primary_corrected_amendment_2": {
            "arm": "S3_global_centering",
            "why": ("the registered primary centers each source inside its board year, a "
                    "transform the incumbent baseline does not have, so it is not "
                    "like-for-like. S3 is the same GLS precision weights with a global "
                    "per-source intercept. The correction moves the verdict AGAINST "
                    "eFV, which is why it is a correction and not spec-shopping."),
            "delta": round(d3, 5),
            "MDE95_E_cond": floors["S3_global_centering"]["MDE95"],
            "MDE95_E_refit": refit_legs["S3_global_centering"]["MDE95"],
            "margin_over_E_cond": round(abs(d3) / floors["S3_global_centering"]["MDE95"], 3)
                                  if floors["S3_global_centering"]["MDE95"] else None,
            "margin_over_E_refit": (
                round(abs(d3) / refit_legs["S3_global_centering"]["MDE95"], 3)
                if refit_legs["S3_global_centering"]["MDE95"] else None),
            "verdict": v3,
            "verdict_why": w3,
        },
        "attribution": {
            "why": ("if the head-to-head win is gone, the site needs to know how much of "
                    "that is this control and how much was already true. Attributing the "
                    "whole move to denoising would overstate what B-L6 found; "
                    "attributing none of it would bury a live defect in the served "
                    "claim."),
            "delta_registered_2026_08_08": REG_DELTA,
            "delta_today_vs_served_consensus": pre["delta"],
            "delta_today_vs_denoised_baseline": round(d3, 5),
            "moved_by_frame_drift": round(pre["delta"] - REG_DELTA, 5),
            "moved_by_denoising": round(d3 - pre["delta"], 5),
            "drift_share_of_total_move": (
                round(abs(pre["delta"] - REG_DELTA) / abs(d3 - REG_DELTA), 3)
                if abs(d3 - REG_DELTA) > 1e-9 else None),
            "reading": ("frame drift is the BA backfill and the identity repairs landing "
                        "in the common set; denoising is this lane. They are separate "
                        "findings and must be reported separately."),
        },
        "verdict": verdict,
        "verdict_why": why,
        "verdict_corrected": v3,
        "elapsed_s": round(time.time() - t_all, 1),
    }
    if write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH}")
    print(f"\nVERDICT (registered primary P1): {verdict} - {why}")
    print(f"VERDICT (corrected primary S3):  {v3} - {w3}")
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "parity"
    if cmd == "parity":
        prec = load_precision()
        print("precision inputs:", json.dumps(prec, indent=1))
        ch = build_channels()
        print(json.dumps(preconditions(ch), indent=1))
        return 0
    if cmd == "run":
        B = int(argv[2]) if len(argv) > 2 else 2000
        run(B=B)
        return 0
    print(__doc__ or "commands: parity | run [B]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
