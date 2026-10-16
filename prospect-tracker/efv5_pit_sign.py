# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV pitcher slope signs: the stability read (EFV_PIT_SIGN_STABILITY).

docs/efv-v2/EFV_PIT_SIGN_STABILITY.md, registered alone before this module existed (owner
decision EW3-36, 2026-10-16). The served pitcher head (the re-fit's variant RT) leaves fifteen
candidate columns free-signed. This read, once, on the development frames only:

1. the fold sign table: each free-signed key's fitted slope in each of the ten pitcher
   development folds of the re-fit's own forward-chained build (its cached fold models,
   checked against the fit artifact's fold receipts), the production slope beside it;
2. the out-of-fold sign test per key (partial slope of u_y on the key's z, consensus and the
   fold model's other drivers held, player-clustered CI95) with planted recovery;
3. for each flagged key, a bounded-at-prior arm and a dropped arm (and IL family arms),
   refitted by the re-fit's own procedure, read at the served weights against the served head
   with the re-fit's ship rule on pitchers, a null comparator and planted recovery;
4. the prepared arm, if any, with its board effect, behind PIT_SIGN_ARM_ON = False.

No reserved row is built or scored; nothing is cut by consensus-FV level; the served grade does
not move (the flag is False).

    python efv5_pit_sign.py --run --cache <re-fit cache> --work <scratch dir> [--budget S]
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

import efv5_combined as V5C
import efv5_refit as RF
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
OUT_PATH = LAB_DIR / "efv5_pit_sign_stability.json"
WEIGHTS_PATH = DATA_DIR / "efv5_pit_sign_weights.json"
DOC = "docs/efv-v2/EFV_PIT_SIGN_STABILITY.md"
TOOL = "efv5_pit_sign.py"
ITEM = "EFV_PIT_SIGN_STABILITY"
SIDE = "pit"

#: Section 8: the prepared arm serves only when the owner flips this (False: byte identical).
PIT_SIGN_ARM_ON = False

#: Registered constants (sections 3 to 5).
SEED = 20261016
B_SIGN = 2000
N_PERM = 1000
NOISE_SD = 0.3
PLANT_G = 0.02
MAX_TRAIL = RF.MAX_TRAIL
CONFIG = "RT"
SERVED_KEY = "ps_served"

#: Section 1: the free-signed pitcher skill columns and their registered baseball prior sign
#: (+1 helps, -1 hurts, 0 no prior: no bounded arm).
PRIOR: dict[str, int] = {
    "g5_pit_A_all_SP_bf_per_g": 0,
    "t5_pit_AAA_all_all_fb_fut": 1,
    "w2i_stints_skill_pit": -1,
    "w2i_days_skill_pit": -1,
    "w2i_sixty_skill_pit": -1,
    "w2i_open_skill_pit": -1,
    "w2i_recur_skill_pit": -1,
    "w2p_cstr_p": 1,
    "w2p_csw_p": 1,
    "w2p_k_resid_p": 0,
    "w2p_fstrike_p": 1,
    "w2b_pu_p": 1,
    "w4p_pop_pit": 1,
    "w2s_brk_pit": 1,
    "w2s_cmd_pit": 1,
}
IL_KEYS: tuple[str, ...] = ("w2i_stints_skill_pit", "w2i_days_skill_pit", "w2i_sixty_skill_pit",
                            "w2i_open_skill_pit", "w2i_recur_skill_pit")


def _tools():
    return RF._tools()


def free_keys() -> list[str]:
    """The pitcher skill candidates of the re-fit with no sign bound; must equal PRIOR."""
    cands = V5C.candidates()
    got = [n for n in RF.refit_candidates(SIDE, "skill") if int(cands[n]["sign"]) == 0]
    if sorted(got) != sorted(PRIOR):
        raise RuntimeError(f"the free-signed pitcher keys moved: {sorted(set(got) ^ set(PRIOR))}")
    return got


def col_key(name: str) -> str:
    return V5C.candidates()[name]["key"]


def _sign(b) -> str:
    if b is None:
        return "not in head"
    return "+" if b > 0 else ("-" if b < 0 else "0")


# ---------------------------------------------------------------------------
# the cache and its checks (section 1)
# ---------------------------------------------------------------------------

def load_cache(cache_dir: Path) -> tuple[list[dict], dict]:
    cache_dir = Path(cache_dir)
    _tools()
    with (cache_dir / "packs_RT.pkl").open("rb") as fh:
        packs, _rec = pickle.load(fh)
    with (cache_dir / "build1.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    mine = [p for p in packs if p["side"] == SIDE]
    return mine, b1


def head_slopes(head: dict | None) -> dict:
    """{column key: standardized slope} of a skill head ({} when it has none)."""
    if not head:
        return {}
    return {k: float(b) for k, b in zip(head.get("keys") or [], head.get("beta") or [])}


def check_receipts(packs: list[dict], fit: dict) -> dict:
    """Each cached fold model's nonzero skill list must equal the fit artifact's receipt."""
    rec = fit["fold_receipts"][CONFIG]
    out = {}
    for p in packs:
        sl = head_slopes((p["model"] or {}).get("skill"))
        got = [k for k, b in sl.items() if b != 0.0]
        want = rec[p["fold_id"]]["skill_nonzero"]
        if got != want:
            raise RuntimeError(f"{p['fold_id']}: cached nonzero keys {got} differ from the receipt {want}")
        out[p["fold_id"]] = {"nonzero": len(got), "matches_receipt": True}
    return out


def sign_table(packs: list[dict], prod: dict) -> dict:
    """Section 2: per key, per fold slope (beta, beta / b_uc, sign) and the production slope."""
    out = {}
    folds = [p["fold_id"] for p in packs]
    for n in free_keys():
        key = col_key(n)
        row = {"key": key, "prior": PRIOR[n], "folds": {}}
        signs = []
        for p in packs:
            head = (p["model"] or {}).get("skill")
            sl = head_slopes(head)
            if key not in sl:
                row["folds"][p["fold_id"]] = {"beta": None, "per_sd": None, "sign": "not in head"}
                continue
            b = sl[key]
            row["folds"][p["fold_id"]] = {"beta": round(b, 6), "per_sd": round(b / head["b_uc"], 5),
                                          "sign": _sign(b)}
            if b != 0.0:
                signs.append(_sign(b))
        ph = prod.get("skill")
        pb = head_slopes(ph).get(key)
        row["production"] = {"beta": None if pb is None else round(pb, 6),
                             "per_sd": None if pb is None else round(pb / ph["b_uc"], 5),
                             "sign": _sign(pb)}
        row["n_plus"] = signs.count("+")
        row["n_minus"] = signs.count("-")
        row["n_zero"] = sum(1 for f in row["folds"].values() if f["sign"] == "0")
        row["n_not_in_head"] = sum(1 for f in row["folds"].values() if f["sign"] == "not in head")
        row["flips"] = bool(row["n_plus"] and row["n_minus"])
        out[n] = row
    return {"folds": folds, "keys": out}


# ---------------------------------------------------------------------------
# the out-of-fold sign test (section 3)
# ---------------------------------------------------------------------------

def oof_rows(packs: list[dict], b1: dict) -> tuple[list[dict], float]:
    """Each fold's scored test rows with u_c, u_y, e_skill, e_time and, per free key the
    fold head carries, its z and its part beta z / b_uc. Returns (rows, max |sum of parts -
    e_skill|)."""
    inp = b1["inp"]
    names = free_keys()
    recs, worst = [], 0.0
    for p in packs:
        fid, fold, m = p["fid"], int(p["fold"]), p["model"]
        blk = inp.frames[fid]["by_side"][SIDE][fold]
        cols = (inp.cols.get(fid) or {}).get(SIDE) or {}
        te = V5C.attach(blk["test"], SIDE, cols, "test")
        if [r["player_key"] for r in te] != list(p["keys"]):
            raise RuntimeError(f"{p['fold_id']}: the test rows differ from the cached pack")
        te_x = RF.rank_transform(te, SIDE)
        head = m.get("skill")
        Z = Cb = None
        hk: list = []
        if H.head_usable(head):
            X = H.skill_design(te_x, head)
            Z = (X - np.asarray(head["mu"])) / np.asarray(head["sd"])
            Cb = Z * np.asarray(head["beta"]) / head["b_uc"]
            hk = list(head["keys"])
            worst = max(worst, float(np.max(np.abs(Cb.sum(1) - p["e_s"]))) if len(te) else 0.0)
        pos = {r["player_key"]: i for i, r in enumerate(te)}
        ols = p["ols"]
        for i, k in enumerate(ols["keys"]):
            j = pos[k]
            z, part = {}, {}
            for n in names:
                key = col_key(n)
                if Z is not None and key in hk:
                    c = hk.index(key)
                    z[n] = float(Z[j, c])
                    part[n] = float(Cb[j, c])
            recs.append({"fold_id": p["fold_id"], "fid": fid, "player": k,
                         "u_c": float(ols["u_c"][i]), "u_y": float(ols["u_y"][i]),
                         "e_s": float(ols["e_s"][i]), "e_t": float(ols["e_t"][i]),
                         "z": z, "part": part})
    return recs, worst


def _design(rows: list[dict], name: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    u_c = np.asarray([r["u_c"] for r in rows])
    z = np.asarray([r["z"][name] for r in rows])
    rest = np.asarray([r["e_s"] - r["part"][name] for r in rows])
    et = np.asarray([r["e_t"] for r in rows])
    cols, names = [np.ones(len(rows)), u_c, rest], ["intercept", "u_c", "rest"]
    if np.any(et != 0):
        cols.append(et)
        names.append("e_time")
    cols.append(z)
    names.append("z")
    return np.column_stack(cols), z, names


def _slope(X: np.ndarray, y: np.ndarray) -> float:
    return float(np.linalg.lstsq(X, y, rcond=None)[0][-1])


def _clusters(rows: list[dict]) -> list[np.ndarray]:
    ids: dict = {}
    for i, r in enumerate(rows):
        ids.setdefault(r["player"], []).append(i)
    return [np.asarray(v) for v in ids.values()]


def boot_slope(X: np.ndarray, y: np.ndarray, members: list[np.ndarray], *, B: int = B_SIGN,
               seed: int = SEED) -> list[float]:
    rng = np.random.default_rng(int(seed))
    got = []
    for _ in range(int(B)):
        d = rng.integers(0, len(members), size=len(members))
        ix = np.concatenate([members[j] for j in d])
        got.append(_slope(X[ix], y[ix]))
    a = np.asarray(got)
    return [round(float(np.quantile(a, 0.025)), 5), round(float(np.quantile(a, 0.975)), 5)]


def sign_test(rows_all: list[dict], name: str, *, B: int = B_SIGN) -> dict:
    """The out-of-fold sign test of one key and its planted recovery."""
    rows = [r for r in rows_all if name in r["z"]]
    out = {"n": len(rows), "folds": sorted({r["fold_id"] for r in rows}),
           "n_players": len({r["player"] for r in rows})}
    if len(rows) < 20:
        return dict(out, status="too few rows", supported=False, resolves=False)
    X, z, names = _design(rows, name)
    if float(np.std(z)) == 0.0:
        return dict(out, status="no variation", supported=False, resolves=False)
    out["z_nonconstant_share"] = round(float(np.mean(np.abs(z - np.median(z)) > 1e-12)), 4)
    y = np.asarray([r["u_y"] for r in rows])
    members = _clusters(rows)
    c = _slope(X, y)
    ci = boot_slope(X, y, members, B=B)
    out.update(design=names, slope=round(c, 5), ci95=ci,
               supported=bool(ci[0] > 0 or ci[1] < 0),
               oof_sign=("+" if ci[0] > 0 else "-" if ci[1] < 0 else "spans zero"))
    # planted recovery: u_y replaced by u_c + rest + g z + noise
    base = X[:, 1] + X[:, 2]
    eps = np.random.default_rng(SEED).normal(0.0, NOISE_SD, len(rows))
    pl = {}
    for g in (PLANT_G, -PLANT_G, 0.0):
        yp = base + g * z + eps
        pl[f"{g:+g}"] = {"slope": round(_slope(X, yp), 5), "ci95": boot_slope(X, yp, members, B=B)}
    up, dn = pl[f"{PLANT_G:+g}"]["ci95"], pl[f"{-PLANT_G:+g}"]["ci95"]
    z0 = pl["+0"]["ci95"]
    out["planted"] = dict(pl, g=PLANT_G, noise_sd=NOISE_SD)
    out["resolves"] = bool(up[0] > 0 and dn[1] < 0)
    out["planted_zero_excludes_zero"] = bool(z0[0] > 0 or z0[1] < 0)
    return out


def flagged_keys(table: dict, tests: dict) -> dict:
    """{key: [reasons]} for every flagged key (section 3)."""
    out = {}
    for n in free_keys():
        why = []
        if table["keys"][n]["flips"]:
            why.append("flips across folds")
        t = tests[n]
        if not t.get("supported"):
            why.append("out-of-fold CI95 spans zero" if "ci95" in t else f"no sign test ({t.get('status')})")
        if not t.get("resolves"):
            why.append("sign test does not resolve the planted slope")
        if why:
            out[n] = why
    return out


# ---------------------------------------------------------------------------
# the arms (section 4)
# ---------------------------------------------------------------------------

def arms_for(flags: dict) -> list[dict]:
    out = []
    for n in free_keys():
        if n not in flags:
            continue
        if PRIOR[n]:
            out.append({"name": f"B:{n}", "bound": {n: PRIOR[n]}, "drop": [], "keys": [n]})
        out.append({"name": f"D:{n}", "bound": {}, "drop": [n], "keys": [n]})
    il = [n for n in IL_KEYS if n in flags]
    if len(il) >= 2:
        out.append({"name": "B:IL", "bound": {n: PRIOR[n] for n in il if PRIOR[n]}, "drop": [],
                    "keys": il})
        out.append({"name": "D:IL", "bound": {}, "drop": il, "keys": il})
    return out


@contextmanager
def edited(edit: dict | None):
    """The pitcher skill head's candidate list and sign bounds with the arm's edit, for the
    block only (restored afterwards)."""
    edit = edit or {}
    bound, drop = dict(edit.get("bound") or {}), set(edit.get("drop") or [])
    cands = V5C.candidates()
    saved = {n: cands[n]["sign"] for n in bound}
    orig = RF.refit_candidates

    def rc(side, head=None, *, dark=True):
        names = orig(side, head, dark=dark)
        if side == SIDE and head == "skill":
            names = [n for n in names if n not in drop]
        return names
    RF.refit_candidates = rc
    for n, s in bound.items():
        cands[n]["sign"] = int(s)
    try:
        yield
    finally:
        RF.refit_candidates = orig
        for n, s in saved.items():
            cands[n]["sign"] = s


def fit_folds(b1: dict, edit: dict | None, *, log=print) -> list[dict]:
    """The ten pitcher development folds of the RT configuration (forward chaining, the
    re-fit's fold_packs FC branch) with the arm's edit."""
    BT, _B4 = _tools()
    R = RF.Run(B=0, log=lambda *_a, **_k: None)
    cfg = RF.CONFIGS[CONFIG]
    inp, pool, twins = b1["inp"], b1["pool"], b1["twins"]
    packs = []
    with RF.pop_repair(True), edited(edit):
        for fid in BT.FRAMES_DEV:
            kind = BT.FRAME_KIND[fid]
            cols = (inp.cols.get(fid) or {}).get(SIDE) or {}
            for fold, blk in inp.frames[fid]["by_side"][SIDE].items():
                Y = int(fold)
                te = V5C.attach(blk["test"], SIDE, cols, "test")
                test_keys = {r["player_key"] for r in te}
                tr = V5C.attach(blk["train"], SIDE, cols, "train")
                if fid == "vm_dev" and cfg["twins"]:
                    tr = tr + [t for t in twins[SIDE] if int(t["decision_year"]) < Y]
                if fid == "lv_dev":
                    tim = V5C.attach(blk["train"], SIDE, cols, "train")
                else:
                    tim = RF.lv_timing_rows(pool[SIDE], last=min(RF.LV_POOL_LAST, Y - 1),
                                            leave_out=test_keys)
                m = R._fit(cfg, SIDE, tr, kind, tim, "lv")
                te_x = RF.rank_transform(te, SIDE) if cfg["transform"] else te
                es, et = RF.e_terms(m, te_x)
                packs.append(RF.pack(f"{fid}|{SIDE}|{fold}", fid, SIDE, Y, te, blk["scored"],
                                     es, et, model=m))
    return packs


def fit_production(b1: dict, edit: dict | None, weights: dict) -> dict:
    """The production pitcher fit of the RT configuration with the arm's edit (the re-fit's
    Run.production for one side)."""
    R = RF.Run(B=0, log=lambda *_a, **_k: None)
    with RF.pop_repair(True), edited(edit):
        cfg = RF.CONFIGS[CONFIG]
        tr = list(b1["prod"][SIDE]) + (list(b1["twins"][SIDE]) if cfg["twins"] else [])
        tim = RF.lv_timing_rows(b1["pool"][SIDE], last=RF.LV_POOL_LAST, leave_out=set())
        m = R._fit(cfg, SIDE, tr, "vm", tim, "lv", with_se=True)
        m["w_skill"] = float(weights["w_skill"]) if H.head_usable(m["skill"]) else 0.0
        m["w_time"] = float(weights["w_time"]) if H.head_usable(m["timing"]) else 0.0
        m["w_skill_unscaled"], m["w_time_unscaled"] = m["w_skill"], m["w_time"]
        m["consensus_only"] = m["w_skill"] <= 0 and m["w_time"] <= 0
        if m["consensus_only"] and m.get("consensus_only_reason") is None:
            m["consensus_only_reason"] = "no usable head carries a positive re-derived weight"
        base = list(b1["prod"][SIDE])
        m["war_map"] = H.fit_war_map(base)
        m["war_map_6yr"] = H.fit_war_map(base)
        m["refit"] = {"item": RF.ITEM, "candidate": CONFIG, "transform": bool(cfg["transform"]),
                      "twins": sum(1 for r in tr if r.get("twin")),
                      "sign_arm": None if not edit else {"name": edit.get("name"),
                                                         "bound": edit.get("bound"),
                                                         "drop": edit.get("drop")}}
        m["refit_transform"] = bool(cfg["transform"])
    return m


# ---------------------------------------------------------------------------
# the statistic and the rule (section 5)
# ---------------------------------------------------------------------------

def stat_rows(b1: dict, served: list[dict], weights: dict) -> list[dict]:
    """The scored pitcher rows of both frames with the served order; group frame|side|year."""
    inp = b1["inp"]
    ws, wt = float(weights["w_skill"]), float(weights["w_time"])
    out = []
    for p in served:
        fid, fold = p["fid"], int(p["fold"])
        pos = {k: i for i, k in enumerate(p["keys"])}
        for c in inp.scored(fid):
            if c["side"] != SIDE or int(c["year"]) != fold or c["key"] not in pos:
                continue
            i = pos[c["key"]]
            g = dict(c["grades"])
            g[SERVED_KEY] = float(p["u_c"][i] + ws * p["e_s"][i] + wt * p["e_t"][i])
            out.append(dict(c, grades=g, group=f"{fid}|{c['group']}", fid=fid,
                            fold_id=p["fold_id"], _i=i))
    return out


def arm_orders(rows: list[dict], packs: list[dict], weights: dict) -> np.ndarray:
    ws, wt = float(weights["w_skill"]), float(weights["w_time"])
    by = {p["fold_id"]: p for p in packs}
    return np.asarray([float(by[r["fold_id"]]["u_c"][r["_i"]] + ws * by[r["fold_id"]]["e_s"][r["_i"]]
                             + wt * by[r["fold_id"]]["e_t"][r["_i"]]) for r in rows])


def _frame_within(order: np.ndarray, y: np.ndarray, codes: np.ndarray, idx: dict, keep: dict) -> dict:
    import efv_v2_stat as S
    return {f: S.within(order, y, codes, keep[f], ix)[0] for f, ix in idx.items()}


def _pooled(d: dict, n: dict) -> float:
    return sum(n[f] * d[f] for f in d) / sum(n[f] for f in d)


def null_read(rows: list[dict], served_o: np.ndarray, arm_o: np.ndarray, *, n_perm: int = N_PERM,
              seed: int = SEED) -> dict:
    """Rule 3: the arm's own order change permuted among each fold's scored rows."""
    import efv_v2_stat as S
    y = np.asarray([r["outcome"]["war"] for r in rows], dtype=np.float64)
    codes = np.asarray([str(r["group"]) for r in rows])
    idx = {f: np.flatnonzero(np.asarray([r["fid"] == f for r in rows])) for f in ("lv_dev", "vm_dev")}
    n = {f: int(ix.size) for f, ix in idx.items()}
    keep = {f: S.kept_groups(codes[ix]) for f, ix in idx.items()}
    w_s = _frame_within(served_o, y, codes, idx, keep)

    def pooled_of(o):
        w = _frame_within(o, y, codes, idx, keep)
        return _pooled({f: w[f] - w_s[f] for f in w}, n)
    d = arm_o - served_o
    obs = pooled_of(arm_o)
    folds: dict = {}
    for j, r in enumerate(rows):
        folds.setdefault(r["fold_id"], []).append(j)
    folds = {k: np.asarray(v) for k, v in folds.items()}
    rng = np.random.default_rng(int(seed))
    null = []
    for _ in range(int(n_perm)):
        dp = d.copy()
        for ix in folds.values():
            dp[ix] = d[rng.permutation(ix)]
        null.append(pooled_of(served_o + dp))
    na = np.asarray(null)
    q975 = float(np.quantile(na, 0.975))
    return {"n_perm": int(n_perm), "seed": int(seed), "observed": round(float(obs), 6),
            "q025": round(float(np.quantile(na, 0.025)), 6), "q975": round(q975, 6),
            "share_at_or_above_observed": round(float((na >= obs).mean()), 4),
            "passes": bool(obs > q975)}


def planted_read(rows: list[dict], served_o: np.ndarray, arm_o: np.ndarray, arm_key: str, *,
                 B: int) -> dict:
    """Rule 4: outcome = arm order + noise (arm must beat served, CI95 above 0) and outcome =
    served order + the same noise (arm must trail served)."""
    BT, _B4 = _tools()
    eps = np.random.default_rng(SEED).normal(0.0, NOISE_SD, len(rows))
    out = {}
    for name, o in (("truth_arm", arm_o), ("truth_served", served_o)):
        pr = [dict(r, outcome=dict(r["outcome"], war=float(o[j] + eps[j]))) for j, r in enumerate(rows)]
        out[name] = RF._keep(BT.paired(pr, arm_key, SERVED_KEY, "within", B=B, seed=BT.SEED))
    lb = (out["truth_arm"].get("ci95") or [None])[0]
    d0 = out["truth_served"].get("delta")
    out["recovered"] = bool(lb is not None and lb > 0 and d0 is not None and d0 < 0)
    out["noise_sd"] = NOISE_SD
    out["seed"] = SEED
    return out


def read_arm(rows: list[dict], served_o: np.ndarray, arm: dict, packs: list[dict], weights: dict,
             *, B: int, log=print) -> dict:
    """Every number of one arm: within reads, the rule, the null, planted recovery."""
    BT, _B4 = _tools()
    key = f"ps_{arm['name']}"
    arm_o = arm_orders(rows, packs, weights)
    rr = [dict(r, grades=dict(r["grades"], **{key: float(arm_o[j])})) for j, r in enumerate(rows)]
    changed = int(np.sum(np.abs(arm_o - served_o) > 1e-12))
    out = {"name": arm["name"], "bound": arm["bound"], "drop": arm["drop"], "keys": arm["keys"],
           "rows_changed": changed, "n": len(rows)}
    out["fold_slopes"] = {p["fold_id"]: {col_key(n): head_slopes((p["model"] or {}).get("skill")).get(col_key(n))
                                         for n in arm["keys"]} for p in packs}
    out["fold_lam"] = {p["fold_id"]: V5C._lam_str((p["model"]["config"]["lam"] or {}).get("skill"))
                       for p in packs}
    out["weights_ols"] = {k: v for k, v in RF.weights_from(packs).items() if k != "coef"}
    if changed == 0:
        out.update(identical=True, passes=False,
                   rule={"rule_pooled_above_zero": False, "rule_no_frame_trails": True,
                         "note": "orders equal the served orders on every row"})
        return out
    cells = {"lv_dev": [r for r in rr if r["fid"] == "lv_dev"],
             "vm_dev": [r for r in rr if r["fid"] == "vm_dev"], "both": rr}
    reads = {}
    for c, sel in cells.items():
        reads[c] = {"n": len(sel),
                    "vs_served": RF._keep(BT.paired(sel, key, SERVED_KEY, "within", B=B, seed=BT.SEED)),
                    "vs_consensus": RF._keep(BT.paired(sel, key, BT.CONS, "within", B=B, seed=BT.SEED))}
    out["reads"] = reads
    d_lv, d_vm = reads["lv_dev"]["vs_served"].get("delta"), reads["vm_dev"]["vs_served"].get("delta")
    n_lv, n_vm = reads["lv_dev"]["n"], reads["vm_dev"]["n"]
    pooled = None if (d_lv is None or d_vm is None) else (n_lv * d_lv + n_vm * d_vm) / (n_lv + n_vm)
    r1 = pooled is not None and pooled > 0
    r2 = d_lv is not None and d_vm is not None and d_lv >= -MAX_TRAIL and d_vm >= -MAX_TRAIL
    out["null"] = null_read(rows, served_o, arm_o)
    out["planted"] = planted_read(rr, served_o, arm_o, key, B=B)
    out["rule"] = {"pooled_delta_vs_served": None if pooled is None else round(pooled, 6),
                   "rule_pooled_above_zero": bool(r1), "rule_no_frame_trails": bool(r2),
                   "rule_null": out["null"]["passes"], "rule_planted": out["planted"]["recovered"]}
    out["passes"] = bool(r1 and r2 and out["null"]["passes"] and out["planted"]["recovered"])
    out["identical"] = False
    log(f"  arm {arm['name']}: changed {changed}, lv {d_lv}, vm {d_vm}, pooled "
        f"{out['rule']['pooled_delta_vs_served']}, null q975 {out['null']['q975']}, planted "
        f"{out['planted']['recovered']}, passes {out['passes']}")
    return out


def combined_arm(results: list[dict]) -> dict | None:
    """Section 6: the best passing arm plus every later passing arm with disjoint keys."""
    passing = sorted([a for a in results if a.get("passes")],
                     key=lambda a: (-a["rule"]["pooled_delta_vs_served"], a["name"]))
    if len(passing) < 2:
        return None
    take, keys = [passing[0]], set(passing[0]["keys"])
    for a in passing[1:]:
        if keys.isdisjoint(a["keys"]):
            take.append(a)
            keys |= set(a["keys"])
    if len(take) < 2:
        return None
    bound, drop = {}, []
    for a in take:
        bound.update(a["bound"])
        drop += list(a["drop"])
    return {"name": "C:" + "+".join(a["name"] for a in take), "bound": bound, "drop": drop,
            "keys": sorted(keys), "members": [a["name"] for a in take]}


# ---------------------------------------------------------------------------
# the board effect (section 7)
# ---------------------------------------------------------------------------

def board_read(model: dict, *, today: str) -> dict:
    """The prepared arm's live pitcher board against data/xfv.json."""
    import efv_w2_popmle as PM
    RF.clear_flag_caches()
    if not PM.POP_REPAIR_ON:
        raise RuntimeError("the served norms flag is off; the board effect reads the served norms")
    got = RF.score_board(SIDE, model, today=today)
    eff = RF.board_effect({SIDE: got})[SIDE]
    doc = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    bp = doc["by_player"]
    served = {k: r for k, r in bp.items()
              if ((r or {}).get("efv_v2") or {}).get("group", [None])[0] == SIDE
              and r.get("grade_basis") == "efv_v2"}
    both = sorted(set(served) & set(got))

    def top50(grade_of):
        order = sorted(both, key=lambda k: (-grade_of(k), k))[:50]
        return round(float(np.mean([grade_of(k) - float(served[k]["consensus_fv"]) for k in order])), 3)
    eff["top50_mean_efv_minus_consensus"] = {
        "served": top50(lambda k: float(served[k]["xfv_grade"])),
        "arm": top50(lambda k: float(got[k]["grade"]))}
    eff["top_movers"] = eff["top_movers"][:25]
    if "dylan_jordan" in served and "dylan_jordan" in got:
        eff["dylan_jordan"] = {"consensus": float(served["dylan_jordan"]["consensus_fv"]),
                               "served": {"grade": float(served["dylan_jordan"]["xfv_grade"]),
                                          "rank": int(served["dylan_jordan"]["efv_v2"]["order_rank"])},
                               "arm": {"grade": round(float(got["dylan_jordan"]["grade"]), 2),
                                       "rank": int(got["dylan_jordan"]["rank"])}}
    return eff


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _save(work: Path, name: str, obj) -> None:
    work.mkdir(parents=True, exist_ok=True)
    with (work / f"{name}.pkl").open("wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _load(work: Path, name: str):
    p = work / f"{name}.pkl"
    if p.exists():
        with p.open("rb") as fh:
            return pickle.load(fh)
    return None


def _fname(arm_name: str) -> str:
    return "arm_" + arm_name.replace(":", "_").replace("+", "__")


def run(cache_dir: Path, work: Path, *, B: int, budget: float | None = None, log=print,
        today: str | None = None) -> dict | None:
    """The registered read, once; resumable from `work` (returns None when the time budget
    ran out before the end)."""
    import efv_labels as L
    BT, _B4 = _tools()
    t0 = time.time()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    today = today or RF._today()
    packs, b1 = load_cache(cache_dir)
    for fid in BT.FRAMES_DEV:
        for f in b1["inp"].frames[fid]["by_side"][SIDE]:
            if fid.startswith("lv") and int(f) in F.RESERVED_LV:
                raise F.ReservedFrameError("a reserved list vintage reached the read")
            if fid.startswith("vm") and int(f) >= 2025:
                raise F.ReservedFrameError("a reserved debut cohort reached the read")
    fit = json.loads(RF.FIT_PATH.read_text(encoding="utf-8"))
    wdoc = json.loads(RF.WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = {k: float(wdoc["weights"][SIDE][k]) for k in ("w_skill", "w_time")}
    if weights != {"w_skill": 1.0, "w_time": 0.0}:
        raise RuntimeError(f"the served pitcher weights moved: {weights}")
    names = free_keys()
    # section 1: the receipts and the production parity
    checks = _load(work, "checks")
    if checks is None:
        receipts = check_receipts(packs, fit)
        stored = RF.production_models()[SIDE]
        prod0 = fit_production(b1, None, weights)
        sb, pb = head_slopes(stored["skill"]), head_slopes(prod0["skill"])
        dmax = max(abs(sb[k] - pb.get(k, np.inf)) for k in sb)
        if list(sb) != list(pb) or dmax > 1e-9:
            raise RuntimeError(f"the production pitcher head does not reproduce: {dmax}")
        checks = {"receipts": receipts, "production_max_abs_diff": dmax}
        _save(work, "checks", checks)
    log(f"receipts match on {len(checks['receipts'])} folds; production parity {checks['production_max_abs_diff']:.2e}")
    stored = RF.production_models()[SIDE]
    # section 4 parity: the unedited refit reproduces the cached folds
    base = _load(work, "arm_none")
    if base is None:
        base = fit_folds(b1, None, log=log)
        _save(work, "arm_none", base)
    by = {p["fold_id"]: p for p in packs}
    pmax = 0.0
    for p in base:
        q = by[p["fold_id"]]
        if list(p["keys"]) != list(q["keys"]):
            raise RuntimeError(f"{p['fold_id']}: the refitted test rows differ")
        pmax = max(pmax, float(np.max(np.abs(np.asarray(p["e_s"]) - np.asarray(q["e_s"])))) if len(q["keys"]) else 0.0)
    if pmax > 1e-9:
        raise RuntimeError(f"the unedited refit does not reproduce the cached folds: {pmax}")
    log(f"fold parity: max |e_skill refit - cached| {pmax:.2e}")
    # sections 2 and 3
    table = sign_table(packs, stored)
    rows_oof, worst = oof_rows(packs, b1)
    if worst > 1e-9:
        raise RuntimeError(f"the key parts do not sum to e_skill: {worst}")
    tests = _load(work, "tests")
    if tests is None:
        tests = {n: sign_test(rows_oof, n) for n in names}
        _save(work, "tests", tests)
    flags = flagged_keys(table, tests)
    for n in names:
        t = table["keys"][n]
        log(f"  {n}: +{t['n_plus']} -{t['n_minus']} 0:{t['n_zero']} prod {t['production']['sign']}; "
            f"oof {tests[n].get('slope')} {tests[n].get('ci95')} resolves {tests[n].get('resolves')}; "
            f"{'FLAGGED ' + '; '.join(flags[n]) if n in flags else 'stable'}")
    # section 5: the served rows and every arm
    rows = stat_rows(b1, packs, weights)
    served_o = np.asarray([r["grades"][SERVED_KEY] for r in rows])
    arms = arms_for(flags)
    results = []
    for arm in arms:
        got = _load(work, _fname(arm["name"]))
        if got is None:
            if budget is not None and time.time() - t0 > budget:
                log(f"budget reached before {arm['name']}; rerun to resume")
                return None
            t1 = time.time()
            ap = fit_folds(b1, arm, log=log)
            got = read_arm(rows, served_o, arm, ap, weights, B=B, log=log)
            got["seconds"] = round(time.time() - t1, 1)
            _save(work, _fname(arm["name"]), got)
        results.append(got)
    comb = combined_arm(results)
    comb_res = None
    if comb is not None:
        comb_res = _load(work, _fname(comb["name"]))
        if comb_res is None:
            ap = fit_folds(b1, comb, log=log)
            comb_res = read_arm(rows, served_o, comb, ap, weights, B=B, log=log)
            _save(work, _fname(comb["name"]), comb_res)
    passing = sorted([a for a in results if a["passes"]],
                     key=lambda a: (-a["rule"]["pooled_delta_vs_served"], a["name"]))
    prepared = None
    if passing:
        prepared = passing[0]
        if (comb_res is not None and comb_res["passes"]
                and comb_res["rule"]["pooled_delta_vs_served"] > prepared["rule"]["pooled_delta_vs_served"]):
            prepared = comb_res
    board, prod_model = None, None
    if prepared is not None:
        edit = {"name": prepared["name"], "bound": prepared["bound"], "drop": prepared["drop"]}
        prod_model = fit_production(b1, edit, weights)
        board = board_read(prod_model, today=today)
    served_within = {f: RF.within_of([r for r in rows if f == "both" or r["fid"] == f], SERVED_KEY)["within"]
                     for f in ("lv_dev", "vm_dev", "both")}
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC,
           "owner_decision": "EW3-36 (2026-10-16)", "label": fit.get("label"),
           "source_fit": RF.FIT_PATH.relative_to(ROOT).as_posix(),
           "source_fit_generated_at": fit.get("generated_at"),
           "served_weights": dict(weights, source=RF.WEIGHTS_PATH.relative_to(ROOT).as_posix()),
           "checks": dict(checks, fold_parity_max_abs_diff=pmax, parts_sum_max_abs_diff=worst),
           "served_within": served_within,
           "n_rows": {"lv_dev": sum(1 for r in rows if r["fid"] == "lv_dev"),
                      "vm_dev": sum(1 for r in rows if r["fid"] == "vm_dev")},
           "sign_table": table, "sign_tests": tests,
           "planted_zero_excludes_zero_share": round(float(np.mean(
               [bool(tests[n].get("planted_zero_excludes_zero")) for n in names])), 4),
           "flagged": flags, "stable": [n for n in names if n not in flags],
           "arms_read": len(results) + (1 if comb_res is not None else 0),
           "arms": results, "combined": comb_res,
           "passing": [a["name"] for a in passing], "prepared": None if prepared is None else prepared["name"],
           "board": board, "B": int(B), "seed": SEED, "elapsed_s": round(time.time() - t0, 1),
           "code": {"tool": TOOL, "commit": BT._commit(), "tool_sha256": BT._sha(ROOT / TOOL)}}
    BT.write_doc(doc, OUT_PATH)
    log(f"wrote {OUT_PATH}")
    if prod_model is not None:
        wd = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "generated_at": doc["generated_at"],
              "doc": DOC, "artifact": OUT_PATH.relative_to(ROOT).as_posix(), "arm": doc["prepared"],
              "served": False, "flag": "efv5_pit_sign.PIT_SIGN_ARM_ON",
              "note": ("the prepared arm's production pitcher fit; read by the serve path only when "
                       "the owner flips PIT_SIGN_ARM_ON (hitters unchanged)"),
              "model": RF.model_out(prod_model)}
        BT.write_doc(wd, WEIGHTS_PATH)
        log(f"wrote {WEIGHTS_PATH}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the re-fit's cache (packs_RT.pkl, build1.pkl)")
    ap.add_argument("--work", default=None, help="a scratch directory for resumable arms")
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--budget", type=float, default=None, help="seconds before stopping to resume")
    a = ap.parse_args(argv)
    BT, _B4 = _tools()

    def log(msg):
        print(msg, flush=True)
    if a.run:
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the read runs once")
            return 2
        if not (a.cache and a.work):
            log("refused: --cache and --work are needed")
            return 2
        B = BT.B_DEFAULT if a.B is None else int(a.B)
        doc = run(Path(a.cache), Path(a.work), B=B, budget=a.budget, log=log)
        return 0 if doc is not None else 3
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
