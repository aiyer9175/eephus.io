# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV against consensus on arrival labels (EFV_BEAT_TILTED_LABELS; owner EW3-11 path 3,
2026-10-15; method docs/efv-v2/EFV_BEAT_TILTED_LABELS.md, committed alone before this module).

THE CLAIM is arrival, kept apart from the value claim: does the served eFV order prospects
by who reaches the majors better than PROSPX consensus? The deciding rater is the served eFV
(eFV v5 COMBINED as re-fit, variant RT): its out-of-fold development order, rebuilt in memory
by efv5_refit's own fold code with the committed cross-fit guard. The pre-refit v5 COMBINED
development fit and both timing heads alone are reported beside it.

Labels: lv_dev (list vintages 2017 to 2019) R3, R5 and W2 (early WAR); vm_dev (debut cohorts
2017 to 2023) AD (arrival day: earlier debut in the season scores higher) and W2. The primary
label is R3 on lv_dev and AD on vm_dev. Within (side, year) Spearman, paired, player- and
club-clustered bootstrap, B 2000, seed 20261017. PASS when the served rater minus consensus
has a one-sided 95 percent lower bound above 0 under both clusterings on both frames, the
observed delta clears the permutation null's 95th percentile on both frames, and the planted
rater is recovered on both frames.

Run once:
    python -u tools/efv_beat_tilted_labels.py --run --cache <scratch dir>

Nothing served moves: no fit, weight, flag or served file is written. The parity guards
(the v5 COMBINED development read and the re-fit's RT read reproduced) stop the read before
any arrival number when they fail.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are frame, side and year.
Consensus enters as a rater. Nothing here groups, counts or averages rows by consensus-FV
level; test_efv_beat_tilted_labels.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import efv_v2_stat as S  # noqa: E402
import source_backtest as SB  # noqa: E402

ITEM = "EFV_BEAT_TILTED_LABELS"
TOOL = "tools/efv_beat_tilted_labels.py"
DOC = "docs/efv-v2/EFV_BEAT_TILTED_LABELS.md"
RESULTS_DOC = "docs/efv-v2/EFV_BEAT_TILTED_LABELS_RESULTS.md"
OUT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv_beat_tilted_labels.json"
V5_FIT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv5_combined_fit.json"
REFIT_FIT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv5_refit_fit.json"
HOLDOUT_PATH = ROOT / "data" / "efv_2026_holdout.json"
#: The registration commit (the document alone, before this module).
REGISTRATION_COMMIT = "b7798fc8"
#: The date the re-fit's read built its twins as of (its artifact: 2026-10-16T00:24Z UTC,
#: 2026-10-15 local); the parity guard proves the rebuild matches.
BUILD_TODAY = "2026-10-15"
B = 2000
SEED = 20261017
B_PLANT = 500
N_PERM = 200
PLANT_A = 0.15
PARITY_TOL_V5 = 5e-5
PARITY_TOL_RT = 1e-4
CLUSTERINGS = ("player", "club")
FRAMES = ("lv_dev", "vm_dev")
#: rater name -> row score key
SERVED = "efv_served_rt"
V5C = "efv_v5_combined_dev"
T_RT = "timing_head_rt"
T_V5 = "timing_head_v5c"
CONS = "prospx_consensus"
PLANT = "planted"
NULL = "null_permuted"
#: (comparison, rater a, rater b); the first is the deciding one.
COMPARISONS = (("served_vs_consensus", SERVED, CONS),
               ("v5c_dev_vs_consensus", V5C, CONS),
               ("timing_rt_vs_consensus", T_RT, CONS),
               ("timing_v5c_vs_consensus", T_V5, CONS),
               ("served_vs_v5c_dev", SERVED, V5C))
DECIDING = "served_vs_consensus"
#: the labels read on each frame (registration section 5)
LABELS = {"lv_dev": ("R3", "R5", "W2"), "vm_dev": ("AD", "W2")}
BINARY = frozenset({"R3", "R5"})
#: the claims: {claim: {frame: label}}; ARRIVAL is the primary (deciding) one
CLAIMS = {"ARRIVAL": {"lv_dev": "R3", "vm_dev": "AD"},
          "R5": {"lv_dev": "R5", "vm_dev": "AD"},
          "W2": {"lv_dev": "W2", "vm_dev": "W2"}}
PRIMARY = "ARRIVAL"
R5_WINDOW = 5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _pp():
    import efv_beat_pooled_power as PP
    return PP


# ---------------------------------------------------------------------------
# labels (registration section 5)
# ---------------------------------------------------------------------------

def r5_label(lab: dict) -> float | None:
    """1 when REACHED with an effective debut in V..V+5, else 0; None when the label
    record is an identity conflict (its r3 is None too)."""
    if lab.get("status") == "identity_conflict" or lab.get("r3") is None:
        return None
    V = int(lab["vintage"])
    dy = lab.get("debut_year")
    ok = lab.get("reached") == "reached" and dy is not None and V <= int(dy) <= V + R5_WINDOW
    return 1.0 if ok else 0.0


def arrival_day(cutoff, year: int, placeholder: bool) -> float | None:
    """Minus the days from year-01-01 to the debut day (earlier scores higher); None unless
    the day is a full date inside `year` and not a placeholder."""
    d = str(cutoff or "")[:10]
    if placeholder or len(d) != 10 or d[:4] != str(int(year)):
        return None
    try:
        day = date.fromisoformat(d)
    except ValueError:
        return None
    return -float((day - date(int(year), 1, 1)).days)


def early_war(seasons: dict | None, year: int) -> float:
    """WAR over seasons year and year + 1 (the first two MLB seasons of a debut in year)."""
    s = seasons or {}
    return round(float(s.get(int(year), 0.0)) + float(s.get(int(year) + 1, 0.0)), 3)


# ---------------------------------------------------------------------------
# the statistics
# ---------------------------------------------------------------------------

def pool_rows(rows: list[dict], label: str, fid: str, raters) -> tuple[list[dict], int]:
    """The rows carrying `label`, shaped for efv_beat_pooled_power.Pool (y = the label,
    group frame:side|year). Returns (rows, rows dropped for a missing label)."""
    out, dropped = [], 0
    for r in rows:
        y = r["labels"].get(label)
        if y is None:
            dropped += 1
            continue
        out.append({"key": r["key"], "frame": fid, "kind": fid[:2], "side": r["side"],
                    "year": r["year"], "pgroup": f"{fid}:{r['side']}|{r['year']}",
                    "club": r["club"], "y": float(y),
                    "scores": {k: r["scores"][k] for k in raters}})
    return out, dropped


def _auc_groups(pool, idx: np.ndarray, raters) -> list[tuple[str, int, dict]]:
    gc = pool.codes[idx]
    out = []
    for u in pool.keep:
        m = idx[gc == u]
        if m.size < 3:
            continue
        yy = pool.y[m]
        n1 = float((yy > 0.5).sum())
        n0 = float(m.size - n1)
        if n1 == 0 or n0 == 0:
            continue
        au = {}
        for k in raters:
            rk = SB._ranks_np(np, pool.score[k][m])
            au[k] = (float(rk[yy > 0.5].sum()) - n1 * (n1 + 1) / 2.0) / (n1 * n0)
        out.append((str(u), int(m.size), au))
    return out


def _auc_pair(groups, a: str, b: str) -> tuple[float | None, float | None]:
    ta = tb = 0.0
    n = 0
    for _u, size, au in groups:
        ta += au[a] * size
        tb += au[b] * size
        n += size
    if not n:
        return None, None
    return ta / n, tb / n


def read_auc(prows: list[dict], comparisons, *, B_: int = B, seed: int = SEED) -> dict:
    """Within (side, year) AUC on a binary label, size-weighted; each comparison's point
    and paired bootstrap under both clusterings (reported, decides nothing)."""
    PP = _pp()
    raters = sorted({k for _n, a, b in comparisons for k in (a, b)})
    pool = PP.Pool(prows, raters)
    full = _auc_groups(pool, np.arange(pool.n), raters)
    out = {"raters": {}, "legs": {}}
    for k in raters:
        tot = sum(au[k] * s for _u, s, au in full)
        n = sum(s for _u, s, _au in full)
        out["raters"][k] = _rnd(tot / n, 4) if n else None
    for name, a, b in comparisons:
        wa, wb = _auc_pair(full, a, b)
        out["legs"][name] = {"a": a, "b": b, "auc_a": _rnd(wa), "auc_b": _rnd(wb),
                             "delta": None if wa is None else _rnd(wa - wb)}
    for cl in CLUSTERINGS:
        keys = [r["key"] if cl == "player" else r["club"] for r in prows]
        ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
        order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
        rng = np.random.default_rng(int(seed))
        diffs = {name: [] for name, _a, _b in comparisons}
        for _ in range(int(B_)):
            idx = SB._cluster_draw(np, rng, order, starts, lens)
            if idx.size < 8:
                continue
            g = _auc_groups(pool, idx, raters)
            for name, a, b in comparisons:
                xa, xb = _auc_pair(g, a, b)
                if xa is not None:
                    diffs[name].append(xa - xb)
        for name in diffs:
            blk = PP.summarize(diffs[name])
            blk.update(B=int(B_), seed=int(seed), n_clusters=len(ids))
            out["legs"][name][cl] = blk
    return out


def frame_verdict(leg: dict) -> dict:
    """Section 7, one frame: lower bound above 0 under both clusterings."""
    p = leg.get("player") or {}
    c = leg.get("club") or {}
    lp, lc = p.get("lb95"), c.get("lb95")
    ok = bool(lp is not None and lc is not None and lp > 0 and lc > 0)
    if ok:
        word = "beats"
    elif p.get("ub95") is not None and p["ub95"] < 0:
        word = "trails"
    else:
        word = "ties"
    return {"lb_above_0": ok, "word": word, "delta": leg.get("delta"), "n": leg.get("n"),
            "lb95_player": lp, "lb95_club": lc, "ub95_player": p.get("ub95"),
            "ci95_player": p.get("ci95"), "ci95_club": c.get("ci95"),
            "mde95_player": p.get("mde95"), "mde95_club": c.get("mde95")}


def claim_verdict(per_frame: dict, null: dict | None, planted: dict | None) -> dict:
    """The rule of section 7 over both frames. per_frame {fid: frame_verdict}; null and
    planted {fid: block} (None for a secondary claim read without them)."""
    words = {}
    passed = True
    for fid in FRAMES:
        v = per_frame.get(fid) or {}
        w = v.get("word", "ties")
        if planted is not None and not (planted.get(fid) or {}).get("recovered"):
            w = "unresolved"
        if not v.get("lb_above_0"):
            passed = False
        if null is not None and not (null.get(fid) or {}).get("above_null_p95"):
            passed = False
        if w == "unresolved":
            passed = False
        words[fid] = w
    return {"pass": passed, "verdict": "PASS" if passed else "NOT PASS", "words": words}


def null_read(rows: list[dict], label: str, fid: str, *, n_perm: int = N_PERM,
              seed: int = SEED) -> dict:
    """The permutation null: within each fold's test rows the served rater's (e_skill,
    e_time) pairs permuted together, u_c and the fold's weights held; served minus
    consensus within Spearman on the label, point only."""
    PP = _pp()
    sel = [r for r in rows if r["labels"].get(label) is not None]
    base, _d = pool_rows(sel, label, fid, (SERVED, CONS))
    pool = PP.Pool(base, (SERVED, CONS))
    obs_a, obs_b = pool.pair(pool.group_rhos(np.arange(pool.n)), SERVED, CONS, "both")
    obs = None if obs_a is None else obs_a - obs_b
    uc = np.asarray([r["null"]["u_c"] for r in sel])
    es = np.asarray([r["null"]["e_s"] for r in sel])
    et = np.asarray([r["null"]["e_t"] for r in sel])
    ws = np.asarray([r["null"]["w_s"] for r in sel])
    wt = np.asarray([r["null"]["w_t"] for r in sel])
    by: dict = {}
    for j, r in enumerate(sel):
        by.setdefault(r["null"]["fold_id"], []).append(j)
    rng = np.random.default_rng(int(seed))
    draws = []
    for _ in range(int(n_perm)):
        perm = np.arange(len(sel))
        for ix in by.values():
            ix = np.asarray(ix)
            perm[ix] = ix[rng.permutation(ix.size)]
        pool.score[SERVED] = uc + ws * es[perm] + wt * et[perm]
        xa, xb = pool.pair(pool.group_rhos(np.arange(pool.n)), SERVED, CONS, "both")
        if xa is not None:
            draws.append(xa - xb)
    d = np.asarray(draws, dtype=np.float64)
    p95 = float(np.quantile(d, 0.95)) if d.size else None
    return {"label": label, "n_perm": int(n_perm), "seed": int(seed), "draws": int(d.size),
            "observed": _rnd(obs), "null_mean": _rnd(d.mean()) if d.size else None,
            "null_p95": _rnd(p95), "p_null_ge_observed": (None if obs is None or not d.size
                                                          else _rnd(float((d >= obs).mean()), 4)),
            "above_null_p95": bool(obs is not None and p95 is not None and obs > p95)}


def planted_read(rows: list[dict], label: str, fid: str, *, B_: int = B_PLANT,
                 seed: int = SEED) -> dict:
    """The planted rater P = u_c + PLANT_A x (q - 0.5), q the within (side, year)
    percentile of (the label standardized within the group plus a standard normal draw);
    P minus consensus, player-clustered, B_PLANT draws."""
    PP = _pp()
    import efv_v2_model as H
    sel = [r for r in rows if r["labels"].get(label) is not None]
    rng = np.random.default_rng(int(seed))
    groups: dict = {}
    for j, r in enumerate(sel):
        groups.setdefault((r["side"], r["year"]), []).append(j)
    p = np.zeros(len(sel))
    for _g, ix in sorted(groups.items()):
        ix = np.asarray(ix)
        y = np.asarray([sel[j]["labels"][label] for j in ix], dtype=np.float64)
        sd = y.std()
        z = (y - y.mean()) / sd if sd > 0 else np.zeros(ix.size)
        q = H.within_pct(z + rng.standard_normal(ix.size), [0] * ix.size)
        uc = np.asarray([sel[j]["null"]["u_c"] for j in ix])
        p[ix] = uc + PLANT_A * (np.asarray(q) - 0.5)
    base, _d = pool_rows(sel, label, fid, (CONS,))
    for j, r in enumerate(base):
        r["scores"][PLANT] = float(p[j])
    res = PP.read_pool(base, (("planted_vs_consensus", PLANT, CONS),), B_=B_, seed=seed,
                       clusterings=("player",), log=lambda *_a: None)
    leg = res["legs"]["planted_vs_consensus|both"]
    pl = leg.get("player") or {}
    return {"label": label, "a": PLANT_A, "B": int(B_), "seed": int(seed),
            "delta": leg.get("delta"), "lb95_player": pl.get("lb95"), "ci95": pl.get("ci95"),
            "recovered": bool(pl.get("lb95") is not None and pl["lb95"] > 0)}


# ---------------------------------------------------------------------------
# building the rows (efv5_refit's fold code, in memory)
# ---------------------------------------------------------------------------

def _build1_lite(R, *, log=print) -> dict:
    """efv5_refit.Run.build1 without the production rows and the live receipt (the FC
    fold design reads neither): the repaired-norm inputs, the list-vintage pool and the
    twins, as built there."""
    got = R._load("tilted_build1")
    if got is not None:
        return got
    import efv5_combined as V5
    import efv5_group_drivers as G
    import efv5_refit as R5
    import efv_v2_model as H
    import efv_vintage_frame as F
    with G.registered(), V5.v5c_names():
        inp, frames_lv, _rec = V5.build_dev(log=log)
        pool, prec = R5.lv_pool(frames_lv, log=log)
        twins = {}
        for side in F.SIDES:
            base = [r for r in H.matrix_training_rows(side)
                    if int(r["decision_year"]) < F.train_end_year()]
            tw, _trec = R5.build_twins(side, base)
            cols, _crec = R5.twin_columns(side, tw, today=R.today, log=log)
            twins[side] = R5.attach_slots(tw, side, cols, R5.twin_slot)
    out = {"inp": inp, "pool": pool, "pool_rec": prec, "prod": {}, "twins": twins}
    R._save("tilted_build1", out)
    return out


def _pack_scores(packs: list[dict], weights: dict | None) -> dict:
    """{fid: {(side, fold, key): {...}}} per test row: u_c, e_s, e_t and, with weights,
    the order and the fold's weights."""
    out: dict = {}
    for p in packs:
        w = None if weights is None else weights[p["side"]][p["fold_id"]]
        mine = out.setdefault(p["fid"], {})
        for i, k in enumerate(p["keys"]):
            d = {"u_c": float(p["u_c"][i]), "e_s": float(p["e_s"][i]),
                 "e_t": float(p["e_t"][i]), "fold_id": p["fold_id"]}
            if w is not None:
                d["w_s"], d["w_t"] = float(w["w_skill"]), float(w["w_time"])
                d["order"] = d["u_c"] + d["w_s"] * d["e_s"] + d["w_t"] * d["e_t"]
            mine[(p["side"], int(p["fold"]), k)] = d
    return out


def build(cache_dir: Path, *, log=print) -> dict:
    """Every development row with each rater's score, the labels and the null terms, after
    the parity guards (registration section 4)."""
    import efv5_combined as V5
    import efv5_refit as R5
    import efv_labels as L
    import efv_vintage_frame as F
    BT, _B4 = V5._tools()
    t0 = time.time()
    R = R5.Run(B=0, log=log, cache_dir=cache_dir, today=BUILD_TODAY)
    log("phase 0 (legacy norms): the v5 COMBINED development fit")
    p0 = R.phase0()
    with R5.pop_repair(True):
        log("phase 1 (repaired norms): the re-fit RT folds")
        b1 = _build1_lite(R, log=log)
        inp = b1["inp"]
        got = R._load("packs_RT")
        if got is None:
            got = R.fold_packs("RT", b1, design="FC")
            R._save("packs_RT", got)
        packs_rt, _rec = got
    receipts: dict = {"build_today": BUILD_TODAY, "parity": {}}
    scored_keys = {}
    for fid in FRAMES:
        k0 = sorted((c["side"], int(c["year"]), c["key"]) for c in p0["scored"][fid])
        k1 = sorted((c["side"], int(c["year"]), c["key"]) for c in inp.scored(fid))
        if k0 != k1:
            raise RuntimeError(f"parity guard: {fid} scored rows differ between the builds")
        scored_keys[fid] = set(k1)
    # (a) v5 COMBINED reproduces its committed development read
    v5fit = json.loads(V5_FIT_PATH.read_text(encoding="utf-8"))
    refit = json.loads(REFIT_FIT_PATH.read_text(encoding="utf-8"))
    cf_read = {s: R5.cross_fitted([p for p in packs_rt if p["side"] == s], min_nonzero=0)
               for s in F.SIDES}
    cf_guard = {s: R5.cross_fitted([p for p in packs_rt if p["side"] == s]) for s in F.SIDES}
    for s in F.SIDES:
        for fold_id, w in refit["weights_cross_fitted"]["RT"][s].items():
            for k in ("w_skill", "w_time"):
                if abs(float(cf_read[s][fold_id][k]) - float(w[k])) > 1e-9:
                    raise RuntimeError(f"parity guard: RT as-read weight {fold_id} {k} "
                                       f"{cf_read[s][fold_id][k]} against {w[k]}")
    o_read = R5.orders_from(packs_rt, cf_read, scored_keys)
    for fid in FRAMES:
        rows = R5.frame_rows(inp, fid, {"V5": p0["orders"], "RT": o_read})
        got_v5 = R5.within_of(rows, R5.KEY["V5"])["within"]
        want_v5 = v5fit["frames"][fid]["raters"]["efv_v5_combined"]["within"]
        got_rt = R5.within_of(rows, R5.KEY["RT"])["within"]
        want_rt = refit["frames"][fid]["raters"]["efv_v5_rt"]["within"]
        receipts["parity"][fid] = {"v5c_dev": {"recomputed": _rnd(got_v5, 6), "committed": want_v5},
                                   "rt_as_read": {"recomputed": _rnd(got_rt, 6),
                                                  "committed": want_rt}}
        if got_v5 is None or abs(float(got_v5) - float(want_v5)) > PARITY_TOL_V5:
            raise RuntimeError(f"parity guard: {fid} v5 COMBINED {got_v5} against {want_v5}")
        if got_rt is None or abs(float(got_rt) - float(want_rt)) > PARITY_TOL_RT:
            raise RuntimeError(f"parity guard: {fid} RT {got_rt} against {want_rt}")
    log(f"parity holds: {receipts['parity']}")
    served = _pack_scores(packs_rt, cf_guard)
    t_v5 = _pack_scores(p0["packs"], None)
    receipts["weights_guarded"] = {s: {k: {"w_skill": _rnd(v["w_skill"], 6),
                                           "w_time": _rnd(v["w_time"], 6),
                                           "held_at_zero": v.get("held_at_zero")}
                                       for k, v in cf_guard[s].items()} for s in F.SIDES}
    # labels
    universe_l = F.load_universe()
    war = L.war_seasons_table()
    raw = V5._raw_by_side()
    universe_c = _pp()._universe()
    frames: dict = {}
    for fid in FRAMES:
        out = []
        cnt = {"rows": 0, "w3_mismatch": 0, "ad_none": 0, "ad_before_read": 0,
               "label_none": {}}
        pinned = {s: V5._pinned_asof(s) for s in F.SIDES} if fid == "vm_dev" else {}
        for c in inp.scored(fid):
            side, year, key = c["side"], int(c["year"]), c["key"]
            k = (side, year, key)
            sv = served[fid][k]
            tv = t_v5[fid][k]
            scores = {SERVED: sv["order"], V5C: float(p0["orders"][fid][k]),
                      T_RT: sv["u_c"] + sv["e_t"], T_V5: tv["u_c"] + tv["e_t"],
                      CONS: float(c["grades"][BT.CONS])}
            if fid == "lv_dev":
                lab = L.labels_for(universe_l[key], year, war.get(key))
                if lab.get("w3") is None or abs(float(lab["w3"]) - float(c["outcome"]["war"])) > 1e-6:
                    cnt["w3_mismatch"] += 1
                labels = {"R3": lab.get("r3"), "R5": r5_label(lab), "W2": lab.get("w2")}
            else:
                rr = raw[side].get(key) or {}
                ad = arrival_day(rr.get("cutoff"), year, bool(rr.get("debut_date_is_placeholder")))
                if ad is None:
                    cnt["ad_none"] += 1
                else:
                    asof = str((pinned.get(side) or {}).get(key) or "")[:10]
                    if asof and str(rr.get("cutoff"))[:10] < asof:
                        cnt["ad_before_read"] += 1
                labels = {"AD": ad, "W2": early_war(war.get(key), year)}
            for name, v in labels.items():
                if v is None:
                    cnt["label_none"][name] = cnt["label_none"].get(name, 0) + 1
            out.append({"key": key, "side": side, "year": year,
                        "club": _pp().club_of(universe_c.get(key), year),
                        "scores": scores, "labels": labels,
                        "null": {"u_c": sv["u_c"], "e_s": sv["e_s"], "e_t": sv["e_t"],
                                 "w_s": sv["w_s"], "w_t": sv["w_t"], "fold_id": sv["fold_id"]}})
            cnt["rows"] += 1
        if fid == "lv_dev" and cnt["w3_mismatch"]:
            raise RuntimeError(f"label guard: {cnt['w3_mismatch']} lv_dev rows whose W3 from "
                               f"efv_labels differs from the frame's outcome")
        frames[fid] = out
        receipts[fid] = cnt
        log(f"{fid}: {cnt['rows']} rows; {cnt}")
    receipts["elapsed_build_s"] = round(time.time() - t0, 1)
    return {"frames": frames, "receipts": receipts, "label_id": refit.get("label")}


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def read(built: dict, *, log=print) -> dict:
    PP = _pp()
    raters = sorted({k for _n, a, b in COMPARISONS for k in (a, b)})
    reads: dict = {}
    for fid in FRAMES:
        for label in LABELS[fid]:
            t0 = time.time()
            prows, dropped = pool_rows(built["frames"][fid], label, fid, raters)
            blk = PP.read_pool(prows, COMPARISONS, B_=B, seed=SEED, log=log)
            blk["rows_without_label"] = dropped
            blk["clubs"] = PP.club_receipt(prows)
            if label in BINARY:
                blk["auc"] = read_auc(prows, COMPARISONS)
                blk["base_rate"] = _rnd(float(np.mean([r["y"] for r in prows])), 4)
            blk["elapsed_s"] = round(time.time() - t0, 1)
            reads[f"{fid}|{label}"] = blk
            leg = blk["legs"][f"{DECIDING}|both"]
            log(f"  {fid} {label}: n {leg['n']} served minus consensus {leg['delta']} "
                f"lb95 {(leg.get('player') or {}).get('lb95')} / "
                f"{(leg.get('club') or {}).get('lb95')} ({blk['elapsed_s']} s)")
    null = {fid: null_read(built["frames"][fid], CLAIMS[PRIMARY][fid], fid) for fid in FRAMES}
    planted = {fid: planted_read(built["frames"][fid], CLAIMS[PRIMARY][fid], fid)
               for fid in FRAMES}
    claims = {}
    for claim, by in CLAIMS.items():
        per_frame = {fid: frame_verdict(reads[f"{fid}|{by[fid]}"]["legs"][f"{DECIDING}|both"])
                     for fid in FRAMES}
        cv = claim_verdict(per_frame, null if claim == PRIMARY else None,
                           planted if claim == PRIMARY else None)
        others = {}
        for name, _a, _b in COMPARISONS[1:]:
            others[name] = {fid: frame_verdict(reads[f"{fid}|{by[fid]}"]["legs"][f"{name}|both"])
                            for fid in FRAMES}
            others[name]["both_frames_lb_above_0"] = all(others[name][f]["lb_above_0"]
                                                         for f in FRAMES)
        claims[claim] = {"labels": by, "role": ("primary (decides)" if claim == PRIMARY
                                                else "secondary (reported; licenses no copy)"),
                         "served": per_frame, "reading": cv, "other_raters": others}
    return {"reads": reads, "null": null, "planted": planted, "claims": claims}


def holdout_record() -> dict:
    d = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    legs = ((d.get("frames") or {}).get("list") or {}).get("legs") or {}
    out = {"artifact": "data/efv_2026_holdout.json",
           "role": "corroboration only (EW3-13; the 2026 frame is spent; the rater there is "
                   "the pre-refit v5 COMBINED served at the time)",
           "generated_at": d.get("generated_at"), "legs": {}}
    for scope in ("pooled", "hit", "pit"):
        k = f"r2026|auc|{scope}|efv_v5_combined-consensus"
        leg = legs.get(k) or {}
        out["legs"][k] = {"delta": leg.get("delta"), "n": leg.get("n"),
                          "lb95_player": (leg.get("player") or {}).get("lb95"),
                          "lb95_club": (leg.get("club") or {}).get("lb95"),
                          "ci95_player": (leg.get("player") or {}).get("ci95")}
    return out


def _code() -> dict:
    return {"commit": _git("rev-parse", "--short=8", "HEAD"),
            "registration_commit": REGISTRATION_COMMIT, "tool": TOOL}


def run(cache_dir: Path, *, log=print) -> dict:
    import efv_labels as L
    t0 = time.time()
    built = build(cache_dir, log=log)
    res = read(built, log=log)
    prim = res["claims"][PRIMARY]["reading"]
    return {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "registration": DOC,
        "generated_at": _now(), "code": _code(),
        "owner_decision": "EW3-11 (2026-10-15), path 3: tilted labels (arrival)",
        "role": ("development (the served re-fit's weights and penalties were chosen on these "
                 "frames out of fold); an ARRIVAL read, never the value claim"),
        "label": {"provider": L.provider(), "id": (built.get("label_id") or {}).get("id")},
        "raters": {SERVED: "served eFV: v5 COMBINED re-fit RT, out of fold, guarded cross-fit",
                   V5C: "eFV v5 COMBINED development fit (pre-refit)",
                   T_RT: "the re-fit RT timing head alone (u_c + e_time)",
                   T_V5: "the v5 COMBINED timing head alone (u_c + e_time)",
                   CONS: "PROSPX consensus (the comparator)"},
        "statistic": ("within (side, year) Spearman, size-weighted over groups of at least "
                      f"{S.MIN_GROUP_ROWS} rows with a non-constant label; rater minus PROSPX "
                      "consensus; AUC on binary labels reported"),
        "bootstrap": {"B": B, "seed": SEED, "estimator": "E_cond, paired",
                      "clusterings": list(CLUSTERINGS)},
        "pass_rule": ("served eFV minus consensus on ARRIVAL (R3 on lv_dev, AD on vm_dev): "
                      "one-sided 95 percent lower bound above 0 under both clusterings on both "
                      "frames, observed delta above the permutation null's 95th percentile on "
                      "both frames, planted rater recovered on both frames"),
        "verdict": prim, "claims": res["claims"], "reads": res["reads"],
        "null": res["null"], "planted": res["planted"],
        "receipts": built["receipts"], "holdout_2026": holdout_record(),
        "spent": ("not opened" if not prim["pass"] else
                  "development PASS: the spent read is the next registered step (section 10)"),
        "elapsed_s": round(time.time() - t0, 1)}


def write(doc: dict) -> Path:
    import efv_v3_backtest as BT
    return BT.write_doc(doc, OUT_PATH)


def summary_lines(doc: dict) -> list[str]:
    out = []
    for claim, c in doc["claims"].items():
        for fid in FRAMES:
            v = c["served"][fid]
            out.append(f"{claim} {fid} ({c['labels'][fid]}): n {v['n']} delta {v['delta']} "
                       f"lb95 {v['lb95_player']} / {v['lb95_club']} ci95 {v['ci95_player']} "
                       f"mde95 {v['mde95_player']}")
        out.append(f"{claim}: {c['reading']['verdict']} {c['reading']['words']}")
    for fid in FRAMES:
        out.append(f"null {fid}: {doc['null'][fid]}")
        out.append(f"planted {fid}: {doc['planted'][fid]}")
    out.append(f"VERDICT: {doc['verdict']['verdict']}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="a scratch directory for resumable builds")
    ap.add_argument("--build-only", action="store_true",
                    help="build and cache the rows and run the parity guards; no statistic")
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    import efv_labels as L
    if a.build_only:
        if not a.cache:
            log("refused: pass --cache <scratch dir>")
            return 2
        built = build(Path(a.cache), log=log)
        log(json.dumps(built["receipts"]["parity"]))
        return 0
    if not a.run:
        ap.print_help()
        return 0
    if L.provider() != "fwar":
        log(f"refused: label provider is {L.provider()!r}, not the frozen 'fwar'")
        return 2
    if _git("cat-file", "-e", REGISTRATION_COMMIT) is None:
        log("refused: the registration commit is not in this repository")
        return 2
    if OUT_PATH.exists():
        log(f"refused: {OUT_PATH} exists; the read ran once")
        return 2
    if not a.cache:
        log("refused: pass --cache <scratch dir> (the re-fit's builds are cached there)")
        return 2
    doc = run(Path(a.cache), log=log)
    write(doc)
    for line in summary_lines(doc):
        log(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
