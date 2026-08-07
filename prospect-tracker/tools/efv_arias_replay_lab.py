# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""efv_arias_replay_lab.py -- attribution replay for the Franklin Arias -0.13 WAR move
between the 2026-08-03 board vintage (7626fd0) and the 2026-08-04 regen (d50c1af).

READ-ONLY LAB. Writes nothing under data/ and nothing the site serves. Everything it
prints comes from (a) the two COMMITTED data/xfv.json blobs, read through `git show`,
and (b) one production-stack fit on the matrices that are on disk right now, used only
to calibrate the ridge-units -> WAR conversion and to prove the replay machinery
reproduces a served number before any of it is trusted.

WHY THE OBVIOUS METHOD IS NOT AVAILABLE. data/xfv_hitter_matrix.json and
data/xfv_live_hitter_matrix.json are gitignored and the nightly box overwrites them, so
the 08-03 and 08-04 feature matrices no longer exist anywhere. A replay that rebuilt
them from the CURRENT database would not be those vintages: the identity repair, the
draft-class stat cache fix and a full MiLB re-pull all landed inside the window. So the
decomposition is anchored on what WAS committed at each SHA, which is the per-player
explainer array -- and that array is not a summary, it is literally the model's own
per-feature terms:

    _predict(ridge, feats) = ridge.b + SUM_k w_k * (x_k - mu_k) / sd_k
    efv_score._factors     = those same w_k * (x_k - mu_k) / sd_k, collinear-grouped,
                             fv / milb_missing / is_ifa / is_college / age dropped,
                             top 4 by |magnitude|, rounded to 2dp

so a committed factor array is an exact (truncated) slice of the served prediction at
that vintage, in ridge units. One multiplication by the calibration slope b puts it in
WAR.

SINGLE PROCESS, BY MANDATE. Both vintages are loaded and scored in this one process
(`git show` into memory, never onto disk) for the reason recorded from the earlier
session: measuring before and after as two separate processes is unsound here because
the box regenerates inputs mid-measurement and the two runs then do not share a corpus.

USAGE
    python tools/efv_arias_replay_lab.py            # everything
    python tools/efv_arias_replay_lab.py validate   # machinery check only
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

# The two vintages the flip happened across, plus the two before it and the head, so the
# "what moved" table can show that the model leg is the only thing that ever moved.
VINTAGES = [
    ("297d7eb", "2026-07-30", "outcome-anchored board reaches served output"),
    ("fe670dd", "2026-08-01", "board reorders, every artifact agrees on the price"),
    ("7626fd0", "2026-08-03", "FanGraphs 2026 updated board, 1,384 re-graded"),
    ("d50c1af", "2026-08-04", "regen behind the identity repair  <-- the flip"),
    ("HEAD",    "2026-08-06", "current served"),
]
SUBJECT = "franklin_arias"
PEERS = ["jesus_made", "leo_de_vries"]

# efv_score inserts the Statcast chip at magnitude |sc-1|*6 and the stale-anchor chip at
# discount/2. Neither is a ridge term, so both are excluded from the ridge-unit ledger.
NON_RIDGE_CHIPS = {
    "Statcast+ quality", "Injury penalty", "Prospect age penalty", "Reliever ceiling",
    "Stale list coverage",
}
# efv_score._FACTOR_LABELS is one-way (key -> label). The ledger needs the inverse, and
# _relabel_pace_factor rewrites one of them on fast climbers, so both spellings map back
# to the same model key.
LABEL_TO_KEY = {
    "On-base vs level": "obp_rel",
    "Contact (K%) vs level": "k_rate_group",
    "Strikeout rate vs level": "k_rate_group",
    "Walk rate vs level": "bb_rate_group",
    "Power (ISO) vs level": "iso_rel",
    "Age for level": "age_rel_level",
    "Level reached": "level_rank",
    "Hit tool": "tool_hit",
    "Speed tool": "tool_speed",
    "Power tool": "tool_game_pwr",
    "Field tool": "tool_field",
    "Production (OPS) vs level": "ops_rel",
    "Seasons to reach level": "n_milb_seasons",
    "Seasons used (fast riser from a low start)": "n_milb_seasons",
    "Source coverage": "n_sources",
    "Draft pedigree": "pick_overall",
    "Signing bonus": "bonus_log",
    "Source disagreement": "fv_stddev",
    "Injury history": "il_stints_pre",
    "Age": "age",
}


def _show(sha: str, path: str) -> bytes:
    out = subprocess.run(["git", "-C", str(REPO), "show", f"{sha}:{path}"],
                         capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"git show {sha}:{path} failed: {out.stderr.decode()[:300]}")
    return out.stdout


def load_vintages() -> dict:
    """Every vintage's xfv.json, in memory, in this one process."""
    return {sha: json.loads(_show(sha, "prospect-tracker/data/xfv.json").decode("utf-8"))
            for sha, _d, _n in VINTAGES}


def signed_factors(row: dict) -> dict:
    """Committed explainer array -> {model_key: signed ridge-unit contribution}.
    Non-ridge overlay chips are returned under their label so the caller can see them
    and keep them out of the ridge ledger."""
    out = {}
    for f in row.get("factors") or []:
        label = f["label"]
        mag = float(f["mag"]) * (1.0 if f["dir"] == "up" else -1.0)
        if label in NON_RIDGE_CHIPS:
            out["chip:" + label] = mag
            continue
        out[LABEL_TO_KEY.get(label, "unlabelled:" + label)] = mag
    return out


# ---------------------------------------------------------------------------
# machinery validation: reproduce a SERVED number from the modules themselves
# ---------------------------------------------------------------------------

def validate_machinery(vint: dict) -> dict:
    """Refit the production stack on the matrices that are on disk and re-derive the
    HEAD row for the subject from scratch. This does not replay 08-03 or 08-04 -- those
    matrices are gone -- it proves the arithmetic below (contribution = w*z, war =
    a + b*pred, chip = |sc-1|*6) is the arithmetic that actually ships, and it MEASURES
    b, the WAR-per-ridge-unit slope the whole ledger is denominated in."""
    import efv_model as XM
    import efv_factor_groups as FG
    from efv_dataset import matrix_path, live_matrix_path
    from prospect_path import _predict

    rows = json.loads(matrix_path("hit").read_text(encoding="utf-8"))
    stack = XM.fit_production_stack(rows, "hit")
    ridge, a, b = stack["ridge"], stack["a"], stack["b"]

    live = json.loads(live_matrix_path("hit").read_text(encoding="utf-8"))
    subj = next((r for r in live if r.get("player_key") == SUBJECT), None)
    if subj is None:
        return {"ok": False, "why": f"{SUBJECT} not in the live hitter matrix"}

    feats = XM._vec(subj, "hit")
    pred = _predict(ridge, feats)
    war_untilted = max(-2.0, a + b * pred)

    head = vint["HEAD"]["by_player"][SUBJECT]
    sc = float(head.get("statcast_factor") or 1.0)
    war_tilted = war_untilted * sc if war_untilted >= 0 else war_untilted / sc

    skip = {"fv", "milb_missing", "is_ifa", "is_college", "age"}
    contribs = [(k, w * ((feats.get(k, 0.0) - m) / (s or 1.0)))
                for k, m, s, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"])
                if k not in skip]
    replay_factors = FG.collapse(contribs, "hit",
                                 lambda k: _label_of(k), min_mag=0.05, top=4)
    served = [f for f in (head.get("factors") or []) if f["label"] not in NON_RIDGE_CHIPS]

    return {
        "ok": True,
        "a": a, "b": b, "alpha": ridge.get("alpha"), "n_train": stack["n"],
        "pred": pred,
        "war_untilted": round(war_untilted, 4),
        "statcast_factor": sc,
        "war_replayed": round(war_tilted, 2),
        "war_served_head": head.get("xfv_war_6yr"),
        "war_matches": abs(round(war_tilted, 2) - float(head["xfv_war_6yr"])) <= 0.02,
        "factors_replayed": replay_factors,
        "factors_served": served,
        "factors_match": ([(f["label"], f["dir"], f["mag"]) for f in replay_factors]
                          == [(f["label"], f["dir"], f["mag"]) for f in served]),
        "all_contribs": dict(sorted(contribs, key=lambda kc: -abs(kc[1]))),
        "fv_term": next((w * ((feats.get("fv", 0.0) - m) / (s or 1.0))
                         for k, m, s, w in zip(ridge["keys"], ridge["mu"],
                                               ridge["sd"], ridge["w"]) if k == "fv"), None),
        "ridge_intercept": ridge["b"],
        "feats": {k: feats.get(k) for k in ridge["keys"]},
    }


def _label_of(key: str) -> str:
    import efv_score as XS   # import-safe: every write in efv_score is inside a persist branch
    return XS._FACTOR_LABELS.get(key, key)


# ---------------------------------------------------------------------------
# the population instrument: refit-common vs player-specific
# ---------------------------------------------------------------------------

def is_live_scored_hitter(r: dict) -> bool:
    """Rows in xfv.json come from three writers. Only efv_score.run_live's rows are
    scored by the flagship hitter ridge; efv_ungraded's carry xfv_provisional and a
    coarse consensus-keyed prior (which is why hundreds of them share a WAR value to the
    cent), and run_backgrade's carry realized_war. Mixing them was worth 88 rows of pure
    noise in the first pass of this lab, so the filter is explicit."""
    return (r.get("side") == "H" and r.get("kind") == "active"
            and "xfv_provisional" not in r and "realized_war" not in r)


def population_move(vint: dict, old: str, new: str) -> dict:
    """Every hitter scored at BOTH vintages, with his model-leg WAR at each.

    This is the zero-information control the attribution needs. A refit moves the whole
    population; a feature change moves one player against it. Conditioning the population
    move on consensus FV (the dominant ridge term, and the one thing about the subject
    that provably did not change) gives the counterfactual "what a player with his anchor
    got from this regen for free", and the residual is what is his alone."""
    a, bnew = vint[old]["by_player"], vint[new]["by_player"]
    pool = []
    for k, r0 in a.items():
        r1 = bnew.get(k)
        if not r1 or not is_live_scored_hitter(r0) or not is_live_scored_hitter(r1):
            continue
        w0, w1 = r0.get("xfv_war_6yr"), r1.get("xfv_war_6yr")
        fv0, fv1 = r0.get("consensus_fv"), r1.get("consensus_fv")
        if None in (w0, w1, fv0, fv1):
            continue
        pool.append({"key": k, "w0": float(w0), "w1": float(w1), "d": float(w1) - float(w0),
                     "fv0": float(fv0), "fv1": float(fv1), "fv_moved": abs(fv1 - fv0) > 1e-9})
    return {"n": len(pool), "pool": pool}


def fv_band_curve(pool: list, half_width: float = 1.0) -> dict:
    """Median model-leg WAR move by consensus-FV band, over the anchor-stable rows only.
    Anchor-stable is the point: a player whose CONSENSUS moved has a second reason to
    move and cannot serve as the control."""
    stable = [p for p in pool if not p["fv_moved"]]
    out = {}
    for p in stable:
        lo = round(p["fv0"] * 2) / 2.0
        out.setdefault(lo, []).append(p["d"])
    curve = {}
    for fv, ds in sorted(out.items()):
        ds = sorted(ds)
        n = len(ds)
        curve[fv] = {"n": n, "median": ds[n // 2] if n % 2 else (ds[n // 2 - 1] + ds[n // 2]) / 2,
                     "mean": sum(ds) / n,
                     "p10": ds[max(0, int(0.10 * (n - 1)))],
                     "p90": ds[min(n - 1, int(0.90 * (n - 1)))]}
    return {"n_stable": len(stable), "curve": curve, "half_width": half_width}


def local_control(pool: list, fv: float, half_width: float = 1.0, exclude=()) -> dict:
    """The subject's OWN control group: anchor-stable hitters within +-half_width FV of
    him, and what the regen handed each of them. No feature of the subject enters."""
    near = [p for p in pool
            if not p["fv_moved"] and abs(p["fv0"] - fv) <= half_width and p["key"] not in exclude]
    ds = sorted(p["d"] for p in near)
    n = len(ds)
    if not n:
        return {"n": 0}
    return {"n": n,
            "median": ds[n // 2] if n % 2 else (ds[n // 2 - 1] + ds[n // 2]) / 2,
            "mean": round(sum(ds) / n, 4),
            "p10": ds[max(0, int(0.10 * (n - 1)))],
            "p25": ds[max(0, int(0.25 * (n - 1)))],
            "p75": ds[min(n - 1, int(0.75 * (n - 1)))],
            "p90": ds[min(n - 1, int(0.90 * (n - 1)))],
            "min": ds[0], "max": ds[-1]}


# ---------------------------------------------------------------------------
# the per-feature ledger
# ---------------------------------------------------------------------------

def affine_probe(vint: dict, old: str, new: str, keys=("level_rank", "age_rel_level",
                                                      "ops_rel", "tool_hit", "obp_rel",
                                                      "tool_speed", "n_milb_seasons",
                                                      "k_rate_group", "age", "iso_rel")) -> dict:
    """The refit map per feature, fitted AFFINELY instead of as a scalar ratio.

    A scalar ratio is only correct when the training MEAN of the column did not move. It
    did move, and the tell was level_rank: its ratios spread 0.55 to 0.77 while ops_rel's
    sat inside 0.86 to 0.90. With
        c = (w/sd) * (x - mu)
    holding x fixed and letting the fit move gives c_new = p*c_old + q exactly, with
        p = (w_new * sd_old) / (w_old * sd_new),   q = (w_new/sd_new) * (mu_old - mu_new).
    So the affine fit is not a smoothing convenience, it is the exact form of a refit with
    the feature value held. Its residual is therefore a DIRECT measurement of how much
    feature movement there was, per feature, across the board."""
    a, bnew = vint[old]["by_player"], vint[new]["by_player"]
    per = {k: [] for k in keys}
    for pk, r0 in a.items():
        r1 = bnew.get(pk)
        if not r1 or not is_live_scored_hitter(r0) or not is_live_scored_hitter(r1):
            continue
        f0, f1 = signed_factors(r0), signed_factors(r1)
        for k in keys:
            if k in f0 and k in f1:
                per[k].append((pk, f0[k], f1[k]))
    out = {}
    for k, rows in per.items():
        n = len(rows)
        if n < 12:
            out[k] = {"n": n, "note": "too thin to fit"}
            continue
        mx = sum(r[1] for r in rows) / n
        my = sum(r[2] for r in rows) / n
        var = sum((r[1] - mx) ** 2 for r in rows)
        cov = sum((r[1] - mx) * (r[2] - my) for r in rows)
        p = cov / var if var > 0 else 1.0
        q = my - p * mx
        errs = sorted(abs(r[2] - (p * r[1] + q)) for r in rows)
        ss_tot = sum((r[2] - my) ** 2 for r in rows)
        ss_res = sum((r[2] - (p * r[1] + q)) ** 2 for r in rows)
        out[k] = {"n": n, "p": round(p, 5), "q": round(q, 5),
                  "r2": round(1 - ss_res / ss_tot, 6) if ss_tot > 0 else None,
                  "med_abs_err": round(errs[n // 2], 4),
                  "p90_abs_err": round(errs[min(n - 1, int(0.90 * (n - 1)))], 4),
                  "max_abs_err": round(errs[-1], 4),
                  "n_over_0.03": sum(1 for e in errs if e > 0.03)}
    return out


def invert_affine(c_new: float, fit: dict) -> float:
    """08-04 contribution -> the 08-03 contribution the same feature VALUE would have
    produced under the old fit. c_new = p*c_old + q, so c_old = (c_new - q)/p."""
    p = fit.get("p")
    if not p:
        return c_new
    return (c_new - fit["q"]) / p


def anchor_block(vint: dict, fv_head: dict, aff: dict, min_fv: float) -> dict:
    """The anchor/calibration block, computed the SAME way for every live-scored hitter
    at or above min_fv. It is the row the ledger cannot split, so it has to be shown to
    behave like what it is claimed to be: a smooth function of the consensus anchor that
    knows nothing about the player. Reported per player, sorted by anchor."""
    a0, a1 = vint["7626fd0"]["by_player"], vint["d50c1af"]["by_player"]
    rows = []
    for pk in fv_head["vec"]:
        r0, r1 = a0.get(pk), a1.get(pk)
        if not r0 or not r1 or not is_live_scored_hitter(r0) or not is_live_scored_hitter(r1):
            continue
        if r0.get("consensus_fv") != r1.get("consensus_fv"):
            continue
        if float(r0["consensus_fv"]) < min_fv:
            continue
        if float(r0.get("statcast_factor") or 1.0) != float(r1.get("statcast_factor") or 1.0):
            continue
        led = player_ledger(vint, fv_head, aff, pk)
        rows.append({"key": pk, "fv": float(r0["consensus_fv"]),
                     "war0": led["war_0803"], "d_war": led["observed_d_war"],
                     "explainer_war": led["explainer_war"], "anchor_war": led["anchor_war"]})
    rows.sort(key=lambda r: -r["fv"])
    vals = sorted(r["anchor_war"] for r in rows)
    n = len(vals)
    summ = {}
    if n:
        summ = {"n": n,
                "median": round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 4),
                "p10": round(vals[max(0, int(0.10 * (n - 1)))], 4),
                "p25": round(vals[max(0, int(0.25 * (n - 1)))], 4),
                "p75": round(vals[min(n - 1, int(0.75 * (n - 1)))], 4),
                "p90": round(vals[min(n - 1, int(0.90 * (n - 1)))], 4),
                "min": round(vals[0], 4), "max": round(vals[-1], 4)}
    return {"rows": rows, "summary": summ}


def head_equals_0804(vint: dict) -> dict:
    """How much of the live hitter board has a BYTE-IDENTICAL explainer array at d50c1af
    and at HEAD. The ledger below reads the 08-04 full contribution vector off the
    CURRENT matrix (the 08-04 matrix is gone), so this is the licence for doing that:
    if the served explainer did not move between the two, neither did the features."""
    a, b = vint["d50c1af"]["by_player"], vint["HEAD"]["by_player"]
    same = diff = 0
    for k, r0 in a.items():
        r1 = b.get(k)
        if not r1 or r0.get("side") != "H" or r0.get("kind") != "active":
            continue
        f0 = [(f["label"], f["dir"], f["mag"]) for f in (r0.get("factors") or [])
              if f["label"] not in NON_RIDGE_CHIPS]
        f1 = [(f["label"], f["dir"], f["mag"]) for f in (r1.get("factors") or [])
              if f["label"] not in NON_RIDGE_CHIPS]
        if f0 == f1:
            same += 1
        else:
            diff += 1
    return {"identical": same, "changed": diff,
            "share_identical": round(same / max(1, same + diff), 4)}


def full_vector_head() -> dict:
    """Every live hitter's COMPLETE ridge contribution vector at the current fit, plus
    the pieces the explainer never shows (intercept, fv anchor, cohort dummies, age).
    One fit, one pass, in this process."""
    import efv_model as XM
    from efv_dataset import matrix_path, live_matrix_path
    from prospect_path import _predict

    rows = json.loads(matrix_path("hit").read_text(encoding="utf-8"))
    stack = XM.fit_production_stack(rows, "hit")
    ridge, a, b = stack["ridge"], stack["a"], stack["b"]
    live = json.loads(live_matrix_path("hit").read_text(encoding="utf-8"))
    out = {}
    for r in live:
        if not r.get("milb"):
            continue
        feats = XM._vec(r, "hit")
        c = {k: w * ((feats.get(k, 0.0) - m) / (s or 1.0))
             for k, m, s, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"])}
        out[r["player_key"]] = {"contrib": c, "pred": _predict(ridge, feats)}
    return {"vec": out, "a": a, "b": b, "b0": ridge["b"], "keys": list(ridge["keys"])}


EXPLAINER_ROWS = ("ops_rel", "tool_hit", "age_rel_level", "level_rank", "n_milb_seasons",
                  "obp_rel", "tool_speed", "k_rate_group")
GROUPED = {"k_rate_group": ("k_rel", "peak_k_rel")}


def player_ledger(vint: dict, fv_head: dict, aff: dict, pk: str) -> dict:
    """The attribution table for one player.

    c(08-04) is the COMMITTED value where the explainer showed it, otherwise the current
    full contribution vector (licensed per player by the 08-04 == HEAD explainer check).
    c(08-03) is the COMMITTED value where the explainer showed it, otherwise the affine
    refit map inverted onto c(08-04) -- which is exact for a feature whose VALUE did not
    move, and the affine fit's own residuals say that is the case board-wide.

    Every row's WAR column is b * sc * (c_0804 - c_0803). What is left over is the
    anchor/calibration block: the ridge intercept, the consensus-FV term, the two cohort
    dummies, the skipped age term, and the (a, b) output recalibration. That block is a
    function of the consensus anchor and nothing about the player's production, so it is
    reported as one row and characterized against peers rather than split further."""
    b = fv_head["b"]
    vec = (fv_head["vec"].get(pk) or {}).get("contrib", {})
    r0, r1 = vint["7626fd0"]["by_player"][pk], vint["d50c1af"]["by_player"][pk]
    f0, f1 = signed_factors(r0), signed_factors(r1)
    sc0 = float(r0.get("statcast_factor") or 1.0)
    sc1 = float(r1.get("statcast_factor") or 1.0)
    w0, w1 = float(r0["xfv_war_6yr"]), float(r1["xfv_war_6yr"])

    table, sum_war = [], 0.0
    for k in EXPLAINER_ROWS:
        members = GROUPED.get(k)
        head_c = sum(vec.get(m, 0.0) for m in members) if members else vec.get(k, 0.0)
        c1 = f1[k] if k in f1 else head_c
        src1 = "committed" if k in f1 else "current vector"
        fit = aff.get(k) or {}
        if k in f0:
            c0, src0 = f0[k], "committed"
        elif fit.get("p"):
            c0, src0 = invert_affine(c1, fit), "affine inverse"
        else:
            c0, src0 = c1, "UNMEASURED, held flat"
        d = c1 - c0
        dw = b * d * sc1
        sum_war += dw
        table.append({"feature": k, "c_0803": round(c0, 4), "c_0804": round(c1, 4),
                      "p": fit.get("p"), "q": fit.get("q"),
                      "d_ridge": round(d, 4), "d_war": round(dw, 4),
                      "src": f"{src0} / {src1}"})
    observed = round(w1 - w0, 4)
    return {"key": pk, "table": table, "explainer_war": round(sum_war, 4),
            "observed_d_war": observed, "anchor_war": round(observed - sum_war, 4),
            "b": b, "sc_0803": sc0, "sc_0804": sc1,
            "consensus_fv": r0.get("consensus_fv"),
            "war_0803": w0, "war_0804": w1,
            "skipped_terms_head": {k: round(vec.get(k, 0.0), 4)
                                   for k in ("fv", "milb_missing", "is_ifa", "is_college", "age")},
            "intercept_head": fv_head["b0"], "a_head": fv_head["a"]}


def training_pool_across_vintages() -> list:
    """WHY the fit moved. The hitter TRAINING matrix's own report, per vintage. The
    number that matters is milb_feature_coverage: how many labeled rows carry a real
    MiLB production block instead of an imputed one. Every MiLB-derived column's mean,
    sd and fitted weight is a function of that pool, so a step change here IS a refit of
    the whole production block."""
    out = []
    for sha, dt, note in VINTAGES:
        d = json.loads(_show(sha, "prospect-tracker/data/xfv_dataset_report.json").decode("utf-8"))
        out.append({"sha": sha, "vintage": dt, "generated_at": d.get("generated_at"),
                    "rows_total": (d.get("counts") or {}).get("rows_total"),
                    "milb_covered": (d.get("milb_feature_coverage") or {}).get("level_rank"),
                    "baseline_rho_full_km": ((d.get("baseline_consensus_fv_spearman") or {})
                                             .get("full_pool_km_censored") or {}).get("spearman")})
    return out


def source_grades(keys) -> dict:
    """Each player's most recent published FV per source, read-only out of prospects.db.
    This is the consensus side of the answer: what the industry actually has on them."""
    import sqlite3
    con = sqlite3.connect("file:" + str(ROOT / "prospects.db") + "?mode=ro", uri=True)
    cur = con.cursor()
    out = {}
    for k in keys:
        cur.execute("select source, max(snapshot_date) from snapshots "
                    "where player_key=? and fv is not null group by source", (k,))
        rows = []
        for src, dt in cur.fetchall():
            cur.execute("select fv, rank from snapshots where player_key=? and source=? "
                        "and snapshot_date=? and fv is not null", (k, src, dt))
            got = cur.fetchone()
            if got:
                rows.append({"source": src, "date": dt, "fv": got[0], "rank": got[1]})
        out[k] = sorted(rows, key=lambda r: r["source"])
    con.close()
    return out


def war_to_grade(vint: dict, sha: str = "HEAD") -> list:
    """The served WAR -> board-grade map, read empirically off the vintage itself. It is
    monotone by construction (efv_score calls value_framework.outcome_implied_fv on the
    model-leg WAR), so the committed (war, grade) pairs ARE the map, and reading it here
    means the lab never has to import or re-run the valuation engine."""
    bp = vint[sha]["by_player"]
    pts = sorted({(float(r["xfv_war_6yr"]), float(r["xfv_grade"]))
                  for r in bp.values()
                  if is_live_scored_hitter(r) and r.get("xfv_war_6yr") is not None
                  and r.get("xfv_grade") is not None})
    return pts


def war_needed(pts: list, grade: float) -> float | None:
    """Least model-leg WAR that reaches `grade` on the served map."""
    for w, g in pts:
        if g >= grade:
            return w
    return None


def main(argv):
    mode = argv[1] if len(argv) > 1 else "all"
    vint = load_vintages()

    print("=" * 78)
    print("PART 0. WHAT MOVED, from the committed artifacts (single process, git show)")
    print("=" * 78)
    for sha, d, note in VINTAGES:
        bp = vint[sha]["by_player"]
        line = [f"{sha:8s} {d}  gen={vint[sha]['meta'].get('generated_at')}"]
        for k in [SUBJECT] + PEERS:
            r = bp.get(k) or {}
            line.append(f"    {k:14s} grade={r.get('xfv_grade')}  war={r.get('xfv_war_6yr')}"
                        f"  cons={r.get('consensus_fv')}  sc={r.get('statcast_factor')}")
            line.append(f"        {[(f['label'], f['dir'], f['mag']) for f in (r.get('factors') or [])]}")
        print("\n".join(line))
        print(f"    ({note})\n")

    if mode in ("all", "validate"):
        print("=" * 78)
        print("PART 1. MACHINERY VALIDATION (reproduce a SERVED number end to end)")
        print("=" * 78)
        v = validate_machinery(vint)
        if not v.get("ok"):
            print("  FAILED:", v.get("why"))
        else:
            print(f"  production stack: n_train={v['n_train']} alpha={v['alpha']} "
                  f"a={v['a']:.4f} b={v['b']:.4f}")
            print(f"  ridge intercept b0={v['ridge_intercept']:.4f}  pred={v['pred']:.4f}")
            print(f"  fv term          {v['fv_term']:+.4f} ridge units")
            print(f"  war untilted     {v['war_untilted']}")
            print(f"  statcast tilt    {v['statcast_factor']}")
            print(f"  war replayed     {v['war_replayed']}   served(HEAD) {v['war_served_head']}"
                  f"   MATCH={v['war_matches']}")
            print(f"  factors replayed {[(f['label'], f['dir'], f['mag']) for f in v['factors_replayed']]}")
            print(f"  factors served   {[(f['label'], f['dir'], f['mag']) for f in v['factors_served']]}")
            print(f"  FACTORS MATCH    {v['factors_match']}")
            print("  all ridge contributions (HEAD vintage, ridge units):")
            for k, c in v["all_contribs"].items():
                print(f"      {k:18s} {c:+.4f}")
            print("  WAR PER RIDGE UNIT (the ledger's denominator) = "
                  f"{v['b']:.4f} * statcast {v['statcast_factor']} = "
                  f"{v['b'] * v['statcast_factor']:.4f}")
        if mode == "validate":
            return 0

    print()
    print("=" * 78)
    print("PART 2. POPULATION MOVE 08-03 -> 08-04 (the zero-information control)")
    print("=" * 78)
    pm = population_move(vint, "7626fd0", "d50c1af")
    print(f"  hitters scored at both vintages: {pm['n']}")
    subj = next(p for p in pm["pool"] if p["key"] == SUBJECT)
    print(f"  subject move: {subj['w0']} -> {subj['w1']}  delta {subj['d']:+.2f}  "
          f"consensus {subj['fv0']} -> {subj['fv1']} (moved={subj['fv_moved']})")
    for k in PEERS:
        p = next((x for x in pm["pool"] if x["key"] == k), None)
        if p:
            print(f"  peer {k:14s} {p['w0']} -> {p['w1']}  delta {p['d']:+.2f}  "
                  f"consensus {p['fv0']} -> {p['fv1']}")
    lc = local_control(pm["pool"], subj["fv0"], 1.0, exclude={SUBJECT})
    print(f"\n  LOCAL CONTROL: anchor-stable hitters within +-1.0 FV of {subj['fv0']}")
    print(f"    {lc}")
    lc2 = local_control(pm["pool"], subj["fv0"], 2.0, exclude={SUBJECT})
    print(f"  LOCAL CONTROL (+-2.0 FV): {lc2}")
    band = fv_band_curve(pm["pool"])
    print(f"\n  anchor-stable rows: {band['n_stable']}")
    print("  median model-leg WAR move by consensus-FV band:")
    for fv, c in band["curve"].items():
        if c["n"] >= 15:
            print(f"      FV {fv:5.1f}  n={c['n']:4d}  median {c['median']:+.3f}  "
                  f"mean {c['mean']:+.3f}  p10 {c['p10']:+.3f}  p90 {c['p90']:+.3f}")

    print()
    print("=" * 78)
    print("PART 3. SUBJECT vs PEERS, per-feature ridge units")
    print("=" * 78)
    for k in [SUBJECT] + PEERS:
        f0 = signed_factors(vint["7626fd0"]["by_player"][k])
        f1 = signed_factors(vint["d50c1af"]["by_player"][k])
        print(f"  {k}")
        for feat in sorted(set(f0) | set(f1)):
            v0, v1 = f0.get(feat), f1.get(feat)
            d = (v1 - v0) if (v0 is not None and v1 is not None) else None
            print(f"      {feat:26s} {('%+.2f' % v0) if v0 is not None else '  --  ':>7s}"
                  f" -> {('%+.2f' % v1) if v1 is not None else '  --  ':>7s}"
                  f"   {('%+.2f' % d) if d is not None else ''}")

    print()
    print("=" * 78)
    print("PART 4. LICENCE CHECK: is the CURRENT matrix a faithful stand-in for 08-04?")
    print("=" * 78)
    print(f"  board-wide: {head_equals_0804(vint)}")
    print("  (board-wide it is NOT, which is why the ledger below prefers the COMMITTED")
    print("   value on every feature the explainer showed and falls back to the current")
    print("   vector only underneath the top-4 cut. For the SUBJECT the stand-in holds:")
    _a4 = [(f["label"], f["dir"], f["mag"]) for f in vint["d50c1af"]["by_player"][SUBJECT]["factors"]
           if f["label"] not in NON_RIDGE_CHIPS]
    _ah = [(f["label"], f["dir"], f["mag"]) for f in vint["HEAD"]["by_player"][SUBJECT]["factors"]
           if f["label"] not in NON_RIDGE_CHIPS]
    print(f"   his 08-04 explainer == his HEAD explainer: {_a4 == _ah})")

    fvh = full_vector_head()
    print(f"  live hitters with a full reconstructed contribution vector: {len(fvh['vec'])}")
    print(f"  calibration a={fvh['a']:.4f} b={fvh['b']:.4f} ridge intercept={fvh['b0']:.4f}")

    print()
    print("=" * 78)
    print("PART 5. THE REFIT MAP, FITTED AFFINELY (the exact form of a refit)")
    print("=" * 78)
    aff = affine_probe(vint, "7626fd0", "d50c1af")
    for k, s in aff.items():
        print(f"  {k:16s} {s}")
    print()
    print("  SPECIFICITY TEST: the subject's own residual against those population maps.")
    print("  A feature VALUE that moved shows up here and nowhere else.")
    for k in [SUBJECT] + PEERS:
        f0 = signed_factors(vint["7626fd0"]["by_player"][k])
        f1 = signed_factors(vint["d50c1af"]["by_player"][k])
        print(f"    {k}")
        for feat in sorted(set(f0) & set(f1)):
            fit = aff.get(feat) or {}
            if not fit.get("p"):
                continue
            err = f1[feat] - (fit["p"] * f0[feat] + fit["q"])
            flag = "  MOVED" if abs(err) > 2 * fit["p90_abs_err"] else ""
            print(f"      {feat:16s} predicted {fit['p'] * f0[feat] + fit['q']:+.4f}  "
                  f"actual {f1[feat]:+.4f}  err {err:+.4f}  "
                  f"(population p90 err {fit['p90_abs_err']}){flag}")

    print()
    print("=" * 78)
    print("PART 6. THE ATTRIBUTION TABLES")
    print("=" * 78)
    leds = {}
    for pk in [SUBJECT] + PEERS:
        led = leds[pk] = player_ledger(vint, fvh, aff, pk)
        print(f"\n  {pk}   consensus FV {led['consensus_fv']}   "
              f"model-leg WAR {led['war_0803']} -> {led['war_0804']}")
        print(f"  {'feature':16s} {'c(08-03)':>9s} {'c(08-04)':>9s} {'d ridge':>8s} "
              f"{'d WAR':>7s}   source")
        for row in led["table"]:
            print(f"  {row['feature']:16s} {row['c_0803']:+9.4f} {row['c_0804']:+9.4f} "
                  f"{row['d_ridge']:+8.4f} {row['d_war']:+7.4f}   {row['src']}")
        print(f"  {'-' * 62}")
        print(f"  {'explainer subtotal':16s} {'':>29s} {led['explainer_war']:+7.4f}")
        print(f"  {'anchor block':16s} {'':>29s} {led['anchor_war']:+7.4f}"
              f"   (intercept + fv term + cohort dummies + a,b recal)")
        print(f"  {'-' * 62}")
        print(f"  {'OBSERVED':16s} {'':>29s} {led['observed_d_war']:+7.4f}")
        print(f"  statcast tilt {led['sc_0803']} -> {led['sc_0804']}"
              f"    b={led['b']:.4f}  skipped terms at HEAD {led['skipped_terms_head']}")

    print()
    print("  RELATIVE MOVE (this is what actually reordered the board):")
    for peer in PEERS:
        a, p = leds[SUBJECT], leds[peer]
        print(f"    {SUBJECT} vs {peer}: observed {a['observed_d_war'] - p['observed_d_war']:+.4f}"
              f"  = explainer {a['explainer_war'] - p['explainer_war']:+.4f}"
              f"  + anchor {a['anchor_war'] - p['anchor_war']:+.4f}")
        for i, row in enumerate(a["table"]):
            d = row["d_war"] - p["table"][i]["d_war"]
            if abs(d) >= 0.005:
                print(f"        {row['feature']:16s} {d:+.4f}")

    print()
    print("=" * 78)
    print("PART 7. IS THE ANCHOR BLOCK GLOBAL? Same computation for every live hitter")
    print("=" * 78)
    ab = anchor_block(vint, fvh, aff, min_fv=48.0)
    print(f"  consensus FV >= 48, anchor-stable, tilt-stable: {ab['summary']}")
    tier = sorted(r["d_war"] for r in ab["rows"])
    nt = len(tier)
    print(f"  OBSERVED model-leg move over that same tier: n={nt} "
          f"median {tier[nt // 2]:+.3f}  p10 {tier[max(0, int(0.1 * (nt - 1)))]:+.3f}  "
          f"p90 {tier[min(nt - 1, int(0.9 * (nt - 1)))]:+.3f}  "
          f"(subject {next(r['d_war'] for r in ab['rows'] if r['key'] == SUBJECT):+.3f})")
    for r in ab["rows"][:45]:
        mark = "  <== SUBJECT" if r["key"] == SUBJECT else ("  <== peer" if r["key"] in PEERS else "")
        print(f"    FV {r['fv']:5.1f} {r['key']:24s} war {r['war0']:6.2f}  "
              f"dWAR {r['d_war']:+.3f} = explainer {r['explainer_war']:+.3f} "
              f"+ anchor {r['anchor_war']:+.3f}{mark}")

    print()
    print("=" * 78)
    print("PART 8. WHAT WOULD ACTUALLY CHANGE THE RANK")
    print("=" * 78)
    pts = war_to_grade(vint, "HEAD")
    hp = vint["HEAD"]["by_player"]
    for k in [SUBJECT] + PEERS:
        r = hp[k]
        print(f"  {k:16s} consensus {r['consensus_fv']}  model-leg WAR {r['xfv_war_6yr']}"
              f"  board grade {r['xfv_grade']}  premium over consensus "
              f"{r['xfv_minus_consensus']:+.1f}")
    a = hp[SUBJECT]
    for target in sorted({float(hp[p]["xfv_grade"]) for p in PEERS}):
        need = war_needed(pts, target)
        if need is None:
            continue
        print(f"  to reach board grade {target}: model-leg WAR must reach {need:.2f}, "
              f"i.e. {need - float(a['xfv_war_6yr']):+.2f} on his current "
              f"{a['xfv_war_6yr']} ({(need / float(a['xfv_war_6yr']) - 1) * 100:+.1f}%)")
    print(f"  for scale, the ENTIRE 08-04 regen moved his model leg by -0.13, and the "
          f"largest single\n  feature term in that regen was {-0.2225:+.4f}.")

    fvterm = {k: fvh["vec"][k]["contrib"]["fv"] for k in [SUBJECT] + PEERS}
    per_fv = ((fvterm["jesus_made"] - fvterm[SUBJECT])
              / (float(hp["jesus_made"]["consensus_fv"]) - float(hp[SUBJECT]["consensus_fv"])))
    sc = float(hp[SUBJECT].get("statcast_factor") or 1.0)
    print(f"  consensus anchor sensitivity: the fv ridge term is {per_fv:.4f} ridge units "
          f"per FV point,\n  i.e. {per_fv * fvh['b'] * sc:.4f} WAR of model leg per "
          f"consensus FV point (fv terms {fvterm}).")

    print()
    print("  WHAT THE INDUSTRY ACTUALLY HAS ON THEM (prospects.db, latest per source):")
    for k, rows in source_grades([SUBJECT] + PEERS).items():
        print(f"    {k:16s} consensus {hp[k]['consensus_fv']}   "
              + "  ".join(f"{r['source']}={r['fv']:.0f}({r['date']})" for r in rows))

    print()
    print("=" * 78)
    print("PART 9. WHY THE FIT MOVED: the training pool behind each vintage")
    print("=" * 78)
    for row in training_pool_across_vintages():
        print(f"    {row['sha']:8s} {row['vintage']}  report {row['generated_at']}  "
              f"rows {row['rows_total']}  MiLB-covered {row['milb_covered']}  "
              f"consensus baseline rho {row['baseline_rho_full_km']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
