# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitcher eFV drift rebase, read once on the development frames (EFV_PIT_DRIFT_REBASE;
owner decision EW3-36, 2026-10-16; registration docs/efv-v2/EFV_PIT_DRIFT_REBASE.md,
committed alone before this module).

WHAT IS READ. The served pitcher head (eFV v5 re-fit, variant RT, w_skill 1.0, w_time 0) on
the re-fit's own forward-chained development folds (the EFV_FIX_B_REFIT cache), with a
fold's TEST rows as the served read and its skill TRAINING rows (no twins) as the support:

  S   the test rows as built (the served head; the zero-change comparator)
  C   R2 + R1: the seven Single-A group z keys rebased to the fold's training nonzero spread
      (efv5_combined.rebase_factor) and the 60-day IL count rebuilt by injury episode
      (efv_w2_il_backfill.new_episode)
  C2  R2 only;  C1  R1 only (decomposition)
  W   the seven keys and the 60-day count withheld (None: the head's training mean), the
      null arm of the strongest change to the same columns

Statistics (section 5): within Spearman with paired E_cond CI95 against S; top-decile
realization of the centered shift for S and C; a random-direction placebo null for the
rebase factors; planted recovery. The ship rule of the re-fit (section 6 there, S in V5's
place) and the flip condition of the registration's section 6. The board effect (section 7)
reads the live board through the served path with efv5_combined.DRIFT_REBASE_ON off and on.

RESERVED FRAMES AND BANS. Only lv_dev (list vintages 2017 to 2019) and vm_dev (debut cohorts
2017 to 2023) are read, from the cached build; the list-vintage ids come from
efv_vintage_frame.build_frame, which raises on list vintages 2020 and 2021. Nothing is
grouped, counted or averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); the
groups are side, frame, fold and column. No model is refitted. backtest.run_backtest is
never called.

Run:  python efv5_pit_rebase.py --run --cache <the EFV_FIX_B_REFIT cache directory>
"""
from __future__ import annotations

import argparse
import collections
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

import efv5_combined as V5C
import efv5_refit as R
import efv_vintage_frame as F
import efv_w2_il_backfill as IL

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv5_pit_rebase.json"
DOC = "docs/efv-v2/EFV_PIT_DRIFT_REBASE.md"
TOOL = "efv5_pit_rebase.py"
ITEM = "EFV_PIT_DRIFT_REBASE"
SIDE = "pit"
SIXTY = "scr_w2i_sixty_skill_pit"
SIXTY_STAT = "il_60day_pre"
LV_DEV = (2017, 2018, 2019)
SEED = 20261016
N_PLACEBO = 1000
NOISE_SD = 0.3
MAX_TRAIL = R.MAX_TRAIL
CONFIGS = ("S", "C", "C2", "C1", "W")
GKEY = {c: f"rebase_{c.lower()}" for c in CONFIGS}


def _tools():
    return R._tools()


# ---------------------------------------------------------------------------
# the corrections on one fold
# ---------------------------------------------------------------------------

def nonzero_sd(vals) -> float | None:
    return V5C._nonzero_sd([float(v) for v in vals if v is not None])


def fold_factors(train: list[dict], test: list[dict], keys) -> dict:
    """{key: {"train_sd", "test_sd", "train_nonzero", "test_nonzero", "factor"}}: the
    served rule (efv5_combined.rebase_factor) with the fold's training rows as the support
    and its test rows as the served read."""
    out = {}
    for k in sorted(keys):
        tv = [r["v2"].get(k) for r in train if r["v2"].get(k) is not None]
        sv = [r["v2"].get(k) for r in test]
        t_nz = sum(1 for v in tv if v != 0.0)
        sup = {"nonzero": t_nz, "nonzero_sd": nonzero_sd(tv)}
        f = V5C.rebase_factor(sv, sup)
        out[k] = {"train_nonzero": t_nz, "train_sd": sup["nonzero_sd"],
                  "test_nonzero": sum(1 for v in sv if v not in (None, 0.0)),
                  "test_sd": nonzero_sd(sv), "factor": f}
    return out


def apply_rows(rows: list[dict], *, factors: dict | None = None, sixty: dict | None = None,
               withhold=None) -> list[dict]:
    """Copies of `rows` with the registered corrections: nonzero values of each key in
    `factors` times its factor (None factors skipped), the 60-day count replaced from
    `sixty` ({player_key: value}), and the keys in `withhold` set to None."""
    out = []
    for r in rows:
        v2 = dict(r["v2"])
        for k, f in (factors or {}).items():
            v = v2.get(k)
            if f is not None and v is not None and v != 0.0:
                v2[k] = float(v) * float(f)
        if sixty is not None and r["player_key"] in sixty:
            v2[SIXTY] = sixty[r["player_key"]]
        for k in (withhold or ()):
            v2[k] = None
        out.append(dict(r, v2=v2))
    return out


def e_skill(model: dict, rows: list[dict]) -> np.ndarray:
    return R.e_terms(model, R.rank_transform(rows, SIDE))[0]


def key_slopes(model: dict) -> dict:
    """{key: slope over sd over b_uc} of the skill head: e_skill is linear in each key."""
    h = model.get("skill") or {}
    if not h or not h.get("keys"):
        return {}
    return {k: float(b) / float(s) / float(h["b_uc"])
            for k, b, s in zip(h["keys"], h["beta"], h["sd"]) if float(s) != 0.0}


# ---------------------------------------------------------------------------
# the 60-day count, stored and rebuilt
# ---------------------------------------------------------------------------

class Ids:
    """The read id and cutoff of every pitcher test row: lv_dev the outcome-blind frame id
    at V-01-01, vm_dev the matrix id at efv_w2_il_backfill.vm_cutoff."""

    def __init__(self):
        self.lv = {}
        for V in LV_DEV:
            rows = F.build_frame(SIDE, V, milb=False, sidecars=False)
            self.lv[V] = {r["player_key"]: r.get("mlbam_id") for r in rows}
        self.raw = V5C._raw_by_side()[SIDE]

    def read(self, fid: str, fold: int, row: dict) -> tuple:
        if fid == "lv_dev":
            return self.lv[int(fold)].get(row["player_key"]), IL.lv_cutoff(fold)
        rw = self.raw.get(row["player_key"]) or {}
        return rw.get("mlbam_id"), IL.vm_cutoff(rw, int(row["decision_year"]))


def sixty(pid, cut: str, idx: dict, *, episodes: bool) -> float | None:
    return IL.transformed(SIXTY_STAT, IL.asof(pid, cut, idx, episodes=episodes).get(SIXTY_STAT))


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def _rows_out(p: dict, p0: dict, es: dict, *, scored_only=True) -> list[dict]:
    """The fold's scored pitcher rows with every configuration's order (u_c + e_skill,
    the served weights) and the realization fields (u_c, u_y, shifts)."""
    fid, fold = p["fid"], int(p["fold"])
    pos = {k: i for i, k in enumerate(p["keys"])}
    opos = {k: j for j, k in enumerate(p["ols"]["keys"])}
    out = []
    for c in p0["scored"][fid]:
        if c["side"] != SIDE or int(c["year"]) != fold or c["key"] not in pos:
            continue
        i = pos[c["key"]]
        g = dict(c["grades"])
        for name, e in es.items():
            g[GKEY[name]] = float(p["u_c"][i] + e[i])
        out.append(dict(c, grades=g, group=f"{fid}|{c['group']}", fid=fid, fold=fold,
                        fold_id=p["fold_id"], _uc=float(p["u_c"][i]),
                        _uy=(float(p["ols"]["u_y"][opos[c["key"]]]) if c["key"] in opos
                             else None),
                        _es={name: float(e[i]) for name, e in es.items()}))
    return out


def _keep(d: dict) -> dict:
    return R._keep(d)


def within(rows, key) -> float | None:
    return R.within_of(rows, key)["within"]


def cells(rows):
    return [("lv_dev", [r for r in rows if r["fid"] == "lv_dev"]),
            ("vm_dev", [r for r in rows if r["fid"] == "vm_dev"]), ("both", rows)]


def ship(read: dict) -> dict:
    """The re-fit's rule with S in V5's place, per candidate."""
    out = {}
    for c in ("C", "C2", "C1"):
        per, tot, n_tot = {}, 0.0, 0
        for fid in ("lv_dev", "vm_dev"):
            d = read[fid][f"{c}_vs_S"].get("delta")
            n = int(read[fid]["n"])
            per[fid] = {"n": n, "delta_vs_S": d}
            tot += n * float(d or 0.0)
            n_tot += n
        pooled = tot / n_tot if n_tot else None
        r1 = pooled is not None and pooled > 0
        r2 = all(v["delta_vs_S"] is not None and v["delta_vs_S"] >= -MAX_TRAIL
                 for v in per.values())
        no_loss = all(v["delta_vs_S"] is not None and v["delta_vs_S"] >= 0 for v in per.values())
        out[c] = {"frames": per, "pooled_delta_vs_S": None if pooled is None else round(pooled, 6),
                  "rule_pooled_above_zero": bool(r1), "rule_no_frame_trails": bool(r2),
                  "passes": bool(r1 and r2), "no_frame_below_zero": bool(no_loss)}
    return out


# -- top-decile realization (the audit's validation (a) measure) ------------------------

def _prep(rows: list[dict], name: str) -> list[dict]:
    """Per row: the centered shift within (frame, fold), its decile within frame, the
    quadratic expectation of u_y on u_c within frame, the residual and the implied lift
    (linear and bounded). Copies; nothing is cut by consensus level (deciles are of the
    model's shift)."""
    rr = [dict(r, shift=r["_es"][name]) for r in rows if r["_uy"] is not None]
    by = collections.defaultdict(list)
    for r in rr:
        by[(r["fid"], r["fold"])].append(r)
    for g in by.values():
        m = float(np.mean([r["shift"] for r in g]))
        for r in g:
            r["shc"] = r["shift"] - m
    for fid in ("lv_dev", "vm_dev"):
        sel = [r for r in rr if r["fid"] == fid]
        if not sel:
            continue
        y = np.array([r["_uy"] for r in sel])
        uc = np.array([r["_uc"] for r in sel])
        b = np.linalg.lstsq(np.column_stack([np.ones(len(y)), uc, uc ** 2]), y, rcond=None)[0]
        q = np.quantile(np.array([r["shc"] for r in sel]), np.linspace(0, 1, 11))
        for r in sel:
            exp = b[0] + b[1] * r["_uc"] + b[2] * r["_uc"] ** 2
            r["impl"] = (b[1] + 2 * b[2] * r["_uc"]) * r["shc"]
            x = min(r["_uc"] + r["shc"], 1.0)
            r["impl_b"] = float(np.clip(b[0] + b[1] * x + b[2] * x * x, 0, 1) - exp)
            r["res"] = r["_uy"] - exp
            r["dec"] = int(min(9, np.searchsorted(q[1:-1], r["shc"], side="right")))
    return rr


def _share(sel) -> np.ndarray:
    res = np.mean([r["res"] for r in sel])
    im = np.mean([r["impl"] for r in sel])
    ib = np.mean([r["impl_b"] for r in sel])
    return np.array([res / im if abs(im) > 1e-9 else np.nan,
                     res / ib if abs(ib) > 1e-9 else np.nan, res, im])


def realization(rows: list[dict], *, B: int, seed: int = SEED) -> dict:
    """Top-decile realized share (linear, bounded) for S and C and C minus S, per frame and
    pooled, player-clustered bootstrap (the same draws for both)."""
    prep = {c: _prep(rows, c) for c in ("S", "C")}
    out = {}
    for fr in ("both", "lv_dev", "vm_dev"):
        tops = {c: [r for r in prep[c] if r["dec"] == 9 and (fr == "both" or r["fid"] == fr)]
                for c in prep}
        est = {c: _share(t) for c, t in tops.items()}
        allk = sorted({r["key"] for r in prep["S"] if fr == "both" or r["fid"] == fr})
        idx = {c: collections.defaultdict(list) for c in prep}
        for c, t in tops.items():
            for r in t:
                idx[c][r["key"]].append(r)
        rng = np.random.default_rng(seed)
        draws = {c: [] for c in prep}
        diff = []
        for _ in range(int(B)):
            pick = rng.integers(0, len(allk), len(allk))
            got = {}
            for c in prep:
                sel = [r for j in pick for r in idx[c].get(allk[j], ())]
                got[c] = _share(sel) if sel else np.full(4, np.nan)
                draws[c].append(got[c])
            diff.append(got["C"] - got["S"])
        blk = {"n_top": {c: len(t) for c, t in tops.items()}, "players_in_frame": len(allk),
               "unit": "player cluster", "B": int(B), "seed": int(seed)}
        for c in prep:
            a = np.asarray(draws[c], float)
            blk[c] = {"share_linear": _r(est[c][0]), "share_bounded": _r(est[c][1]),
                      "mean_residual": _r(est[c][2]), "mean_implied": _r(est[c][3]),
                      "ci95_linear": [_r(np.nanpercentile(a[:, 0], 2.5)),
                                      _r(np.nanpercentile(a[:, 0], 97.5))],
                      "ci95_bounded": [_r(np.nanpercentile(a[:, 1], 2.5)),
                                       _r(np.nanpercentile(a[:, 1], 97.5))]}
        d = np.asarray(diff, float)
        blk["C_minus_S"] = {"linear": _r(est["C"][0] - est["S"][0]),
                            "bounded": _r(est["C"][1] - est["S"][1]),
                            "ci95_linear": [_r(np.nanpercentile(d[:, 0], 2.5)),
                                            _r(np.nanpercentile(d[:, 0], 97.5))],
                            "ci95_bounded": [_r(np.nanpercentile(d[:, 1], 2.5)),
                                             _r(np.nanpercentile(d[:, 1], 97.5))]}
        out[fr] = blk
    return out


def _r(v, n=5):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else round(v, n)


# ---------------------------------------------------------------------------
# the board effect (section 7)
# ---------------------------------------------------------------------------

def board_effect(*, today: str, log=print) -> dict:
    """The live board through the served path with DRIFT_REBASE_ON off, then on."""
    import efv_v2_serve as S
    import scrapers
    models = S.production_models()
    boards, recs = {}, {}
    orig = V5C.DRIFT_REBASE_ON
    try:
        for on in (False, True):
            V5C.DRIFT_REBASE_ON = on
            V5C._LIVE_MEMO.clear()
            b = {}
            for side in ("pit", "hit"):
                t0 = time.time()
                with scrapers.cache_only():
                    b[side] = R.score_board(side, models[side], today=today)
                log(f"  board {side} flag {on}: {len(b[side])} rows ({round(time.time() - t0, 1)} s)")
            boards[on] = b
            recs[on] = json.loads(json.dumps(V5C.live_receipt("pit"), default=str))
    finally:
        V5C.DRIFT_REBASE_ON = orig
        V5C._LIVE_MEMO.clear()
    return summarize_board(boards, recs)


def _top50_gain(board: dict) -> float:
    top = sorted(board.values(), key=lambda v: v["rank"])[:50]
    return float(np.mean([v["grade"] - v["fv"] for v in top]))


def summarize_board(boards: dict, recs: dict) -> dict:
    off, on = boards[False]["pit"], boards[True]["pit"]
    d = {pk: on[pk]["grade"] - off[pk]["grade"] for pk in off}
    movers = sorted(d, key=lambda pk: (-abs(d[pk]), pk))[:20]
    jor = "dylan_jordan"
    hit_same = all(boards[False]["hit"][pk]["grade"] == boards[True]["hit"][pk]["grade"]
                   and boards[False]["hit"][pk]["order_idx"] == boards[True]["hit"][pk]["order_idx"]
                   for pk in boards[False]["hit"])
    sup_on = (recs[True] or {}).get("support") or {}
    sup_off = (recs[False] or {}).get("support") or {}
    keys = sorted(V5C.REBASE_KEYS | {k for k, r in sup_on.items() if r.get("rebased")})
    return {
        "n_pitchers": len(off),
        "jordan": ({"consensus": round(off[jor]["fv"], 2),
                    "efv_off": round(off[jor]["grade"], 2), "rank_off": off[jor]["rank"],
                    "efv_on": round(on[jor]["grade"], 2), "rank_on": on[jor]["rank"],
                    "chips_on": on[jor]["chips"]} if jor in off else None),
        "top50_gain_off": round(_top50_gain(off), 4), "top50_gain_on": round(_top50_gain(on), 4),
        "mean_abs_efv_minus_cons_off": round(float(np.mean([abs(v["grade"] - v["fv"]) for v in off.values()])), 4),
        "mean_abs_efv_minus_cons_on": round(float(np.mean([abs(v["grade"] - v["fv"]) for v in on.values()])), 4),
        "moved_1_or_more": sum(1 for v in d.values() if abs(v) >= 1.0),
        "moved_3_or_more": sum(1 for v in d.values() if abs(v) >= 3.0),
        "largest_move": round(max((abs(v) for v in d.values()), default=0.0), 3),
        "top_movers": [{"player_key": pk, "consensus": round(off[pk]["fv"], 2),
                        "efv_off": round(off[pk]["grade"], 2), "efv_on": round(on[pk]["grade"], 2),
                        "rank_off": off[pk]["rank"], "rank_on": on[pk]["rank"]} for pk in movers],
        "hitters_unchanged": bool(hit_same),
        "rebased_keys": {k: {"factor": (sup_on.get(k) or {}).get("rebase_factor"),
                             "spread_ratio": (sup_off.get(k) or {}).get("spread_ratio"),
                             "served_nonzero_share": (sup_off.get(k) or {}).get("served_nonzero_share")}
                         for k in keys},
        "sixty": {"off": {f: (sup_off.get(SIXTY) or {}).get(f)
                          for f in ("served_nonzero_share", "train_nonzero_share", "spread_ratio",
                                    "drift", "clipped_high")},
                  "on": {f: (sup_on.get(SIXTY) or {}).get(f)
                         for f in ("served_nonzero_share", "train_nonzero_share", "spread_ratio",
                                   "drift", "clipped_high")}},
        "rebased_receipt": (recs[True] or {}).get("rebased"),
    }


def sixty_receipts(b1: dict, ids_live: list, *, today: str) -> dict:
    """Outcome-blind: the share of production training rows whose stored 60-day value the
    episode rule keeps; the live share and nonzero SD with the stored and the episode count
    (the served stint index, read cut as served)."""
    raw = V5C._raw_by_side()[SIDE]
    idx = IL.stint_index()
    agree = n = 0
    for r in b1["prod"][SIDE]:
        st = r["v2"].get(SIXTY)
        if st is None:
            continue
        rw = raw.get(r["player_key"]) or {}
        v = sixty(rw.get("mlbam_id"), IL.vm_cutoff(rw, int(r["decision_year"])), idx, episodes=True)
        n += 1
        agree += int(v == st)
    tv = [r["v2"][SIXTY] for r in b1["prod"][SIDE] if r["v2"].get(SIXTY) is not None]
    live_idx, end, _rc = V5C._stint_index(today)
    out = {"training_rows": n, "training_rows_kept": agree,
           "training_share_kept": round(agree / n, 4) if n else None,
           "training_nonzero_share": round(float(np.mean(np.asarray(tv) != 0)), 4),
           "training_nonzero_sd": _r(nonzero_sd(tv), 4)}
    for ep in (False, True):
        vals = []
        for mid in ids_live:
            cut = min(today, end) if end else today
            vals.append(sixty(mid, cut, live_idx, episodes=ep))
        a = np.asarray([v for v in vals if v is not None])
        out["live_episodes" if ep else "live_stored_definition"] = {
            "rows": int(a.size), "nonzero_share": round(float(np.mean(a != 0)), 4),
            "nonzero_sd": _r(nonzero_sd(a), 4), "max": float(a.max()) if a.size else None}
    return out


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def run(cache_dir: Path, *, B: int, today: str, log=print) -> dict:
    BT, _B4 = _tools()
    t0 = time.time()
    with (cache_dir / "build1.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    with (cache_dir / "packs_RT.pkl").open("rb") as fh:
        packs, _rec = pickle.load(fh)
    with (cache_dir / "phase0.pkl").open("rb") as fh:
        p0 = pickle.load(fh)
    inp = b1["inp"]
    ids = Ids()
    idx = IL.stint_index()
    rkeys = sorted(V5C.REBASE_KEYS)
    served_w = json.loads(R.WEIGHTS_PATH.read_text(encoding="utf-8"))["weights"][SIDE]
    if float(served_w["w_skill"]) != 1.0 or float(served_w["w_time"]) != 0.0:
        raise RuntimeError(f"the served pitcher weights moved: {served_w}")
    rows, folds, placebo_parts = [], {}, []
    for p in [q for q in packs if q["side"] == SIDE]:
        fid, fold = p["fid"], int(p["fold"])
        blk = inp.frames[fid]["by_side"][SIDE][fold]
        cols = (inp.cols.get(fid) or {}).get(SIDE) or {}
        te = V5C.attach(blk["test"], SIDE, cols, "test")
        tr = V5C.attach(blk["train"], SIDE, cols, "train")
        model = p["model"]
        es_S = e_skill(model, te)
        if float(np.max(np.abs(es_S - p["e_s"]))) > 1e-9:
            raise RuntimeError(f"{p['fold_id']}: the cache does not reproduce e_skill")
        # R1 parity, then the episode count
        new60, changed = {}, 0
        for r in te:
            pid, cut = ids.read(fid, fold, r)
            if sixty(pid, cut, idx, episodes=False) != r["v2"].get(SIXTY):
                raise RuntimeError(f"{p['fold_id']} {r['player_key']}: the stored 60-day "
                                   "definition does not reproduce the stored test value")
            v = sixty(pid, cut, idx, episodes=True)
            new60[r["player_key"]] = v
            changed += int(v != r["v2"].get(SIXTY))
        fac = fold_factors(tr, te, rkeys)
        f_only = {k: v["factor"] for k, v in fac.items()}
        es = {"S": es_S,
              "C": e_skill(model, apply_rows(te, factors=f_only, sixty=new60)),
              "C2": e_skill(model, apply_rows(te, factors=f_only)),
              "C1": e_skill(model, apply_rows(te, sixty=new60)),
              "W": e_skill(model, apply_rows(te, withhold=rkeys + [SIXTY]))}
        # the placebo reads e_skill linearly: check the slopes reproduce C from C1
        sl = key_slopes(model)
        x = {k: np.asarray([float(r["v2"].get(k) or 0.0) for r in te]) for k in rkeys}
        lin = es["C1"] + sum(sl.get(k, 0.0) * x[k] * ((f_only[k] or 1.0) - 1.0) for k in rkeys)
        if float(np.max(np.abs(lin - es["C"]))) > 1e-9:
            raise RuntimeError(f"{p['fold_id']}: e_skill is not linear in the rebased keys")
        mine = _rows_out(p, p0, es)
        rows += mine
        pos = {k: i for i, k in enumerate(p["keys"])}
        ix = np.asarray([pos[r["key"]] for r in mine], dtype=int)
        placebo_parts.append({"fold_id": p["fold_id"], "rows": (len(rows) - len(mine), len(rows)),
                              "base": (p["u_c"] + es["C1"])[ix],
                              "terms": {k: (sl.get(k, 0.0) * x[k])[ix] for k in rkeys},
                              "factors": f_only})
        folds[p["fold_id"]] = {"test_rows": len(te), "train_rows": len(tr), "scored": len(mine),
                               "sixty_changed_test_rows": changed,
                               "factors": {k: {kk: _r(vv, 4) if isinstance(vv, float) else vv
                                               for kk, vv in v.items()} for k, v in fac.items()},
                               "max_abs_e_skill_change": {c: _r(float(np.max(np.abs(es[c] - es_S))), 6)
                                                          for c in ("C", "C2", "C1", "W")},
                               "rows_moved_C": int(np.count_nonzero(np.abs(es["C"] - es_S) > 1e-12))}
        log(f"  {p['fold_id']}: {len(te)} test, {len(mine)} scored, 60-day changed {changed}, "
            f"factors {[_r(v, 3) for v in f_only.values()]}")
    log(f"built {len(rows)} scored pitcher rows ({round(time.time() - t0, 1)} s)")
    CONS = BT.CONS
    comps = [(f"{c}_vs_S", GKEY[c], GKEY["S"]) for c in ("C", "C2", "C1", "W")]
    comps += [("C_vs_consensus", GKEY["C"], CONS), ("S_vs_consensus", GKEY["S"], CONS)]
    read = {}
    for name, sel in cells(rows):
        blk = {"n": len(sel), "raters": {c: _r(within(sel, GKEY[c]), 6) for c in CONFIGS}}
        blk["raters"]["consensus"] = _r(within(sel, CONS), 6)
        for cname, a, b in comps:
            blk[cname] = _keep(BT.paired(sel, a, b, "within", B=B, seed=BT.SEED))
        read[name] = blk
        log(f"  {name}: n {len(sel)}, C minus S {blk['C_vs_S'].get('delta')} "
            f"{blk['C_vs_S'].get('ci95')}, W minus S {blk['W_vs_S'].get('delta')}")
    ship_ = ship(read)
    # NULL: random-direction factors of the same size, R1 kept, pooled delta against S
    rng = np.random.default_rng(SEED)
    s_within = {fid: within([r for r in rows if r["fid"] == fid], GKEY["S"])
                for fid in ("lv_dev", "vm_dev")}
    n_fr = {fid: sum(1 for r in rows if r["fid"] == fid) for fid in ("lv_dev", "vm_dev")}
    null = []
    for _ in range(N_PLACEBO):
        vals = np.zeros(len(rows))
        for part in placebo_parts:
            a, b = part["rows"]
            v = part["base"].copy()
            for k, t in part["terms"].items():
                f = part["factors"][k]
                if f is None:
                    continue
                f2 = f if rng.random() < 0.5 else 1.0 / f
                v = v + t * (f2 - 1.0)
            vals[a:b] = v
        perm = [dict(r, grades=dict(r["grades"], _null=float(vals[j]))) for j, r in enumerate(rows)]
        tot = 0.0
        for fid in ("lv_dev", "vm_dev"):
            sel = [r for r in perm if r["fid"] == fid]
            tot += n_fr[fid] * (within(sel, "_null") - s_within[fid])
        null.append(tot / sum(n_fr.values()))
    na = np.asarray(null)
    obs = ship_["C"]["pooled_delta_vs_S"]
    null_blk = {"n": N_PLACEBO, "seed": SEED, "observed_pooled_C_minus_S": obs,
                "q025": _r(np.quantile(na, 0.025), 6), "q975": _r(np.quantile(na, 0.975), 6),
                "share_at_or_above_observed": round(float((na >= obs - 1e-12).mean()), 4)}
    log(f"  placebo: observed {obs}, null 95% {null_blk['q025']} to {null_blk['q975']}")
    # PLANTED RECOVERY
    planted = {}
    for x in ("C", "S"):
        prng = np.random.default_rng(SEED)
        eps = prng.normal(0.0, NOISE_SD, len(rows))
        pr = [dict(r, outcome=dict(r["outcome"], war=r["_uc"] + r["_es"][x] + float(eps[j])))
              for j, r in enumerate(rows)]
        planted[f"plant_{x}"] = _keep(BT.paired(pr, GKEY["C"], GKEY["S"], "within", B=B,
                                                seed=BT.SEED))
    lb = (planted["plant_C"].get("ci95") or [None])[0]
    dS = planted["plant_S"].get("delta")
    recovered = bool(lb is not None and lb > 0 and dS is not None and dS <= 0)
    log(f"  planted: C {planted['plant_C'].get('delta')} {planted['plant_C'].get('ci95')}, "
        f"S {dS}; recovered {recovered}")
    real = realization(rows, B=B)
    log(f"  realization top decile, both: S {real['both']['S']['share_linear']}, "
        f"C {real['both']['C']['share_linear']}")
    flip = bool(ship_["C"]["passes"] and recovered and ship_["C"]["no_frame_below_zero"])
    t1 = time.time()
    board = board_effect(today=today, log=log)
    log(f"  board ({round(time.time() - t1, 1)} s): Jordan {board['jordan']}, top-50 gain "
        f"{board['top50_gain_off']} to {board['top50_gain_on']}")
    ids_live = _live_ids()
    rc = sixty_receipts(b1, ids_live, today=today)
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "role": "development",
           "adjudicates": False, "doc": DOC, "owner_decision": "EW3-36 (2026-10-16)",
           "side": SIDE, "frames": ["lv_dev", "vm_dev"],
           "served_weights": {"w_skill": float(served_w["w_skill"]),
                              "w_time": float(served_w["w_time"])},
           "rebase_keys": rkeys, "B": int(B), "seed": BT.SEED, "folds": folds, "read": read,
           "ship": ship_, "null_placebo": null_blk,
           "planted": {"noise_sd": NOISE_SD, "seed": SEED, **planted, "recovered": recovered},
           "realization_top_decile": real,
           "flip": {"rule": ("C passes the re-fit ship rule against S, the planted recovery "
                             "holds and neither frame's within delta is below 0"),
                    "flip": flip},
           "board": board, "sixty_receipts": rc,
           "code": {"commit": BT._commit(), "tool_sha256": BT._sha(ROOT / TOOL),
                    "efv5_combined_sha256": BT._sha(ROOT / "efv5_combined.py"),
                    "efv_w2_il_backfill_sha256": BT._sha(ROOT / "efv_w2_il_backfill.py"),
                    "doc_sha256": BT._sha(ROOT / DOC)},
           "today": today, "generated_at": BT._now()}
    BT.write_doc(doc, OUT_PATH)
    log(f"wrote {OUT_PATH} ({round(time.time() - t0, 1)} s)")
    return doc


def _live_ids() -> list:
    import efv_dataset as D
    live = json.loads(D.live_matrix_path(SIDE).read_text(encoding="utf-8"))
    return [r.get("mlbam_id") for r in live if r.get("player_key")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the EFV_FIX_B_REFIT cache directory")
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    BT, _B4 = _tools()
    if not a.run:
        ap.print_help()
        return 0
    if OUT_PATH.exists():
        print(f"refused: {OUT_PATH} exists; the registered read runs once")
        return 2
    if not a.cache:
        print("refused: --cache is needed")
        return 2
    B = BT.B_DEFAULT if a.B is None else int(a.B)
    run(Path(a.cache), B=B, today=a.today or R._today(), log=lambda m: print(m, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
