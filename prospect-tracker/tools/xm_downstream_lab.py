# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The xM$ downstream tests (task XM_4_DOWNSTREAM_TESTS), the build of the
registration docs/xm/XM_DOWNSTREAM.md.

Five tests ask where xM$ (Expected Market $) can improve other metrics:

  A  arbitration: arb-year share x as-of xM$ AAV as a feature in the
     champion's two stages, against the served estimator and a permuted twin.
  B  qualifying offer: acceptance from log(xM$ total / QO value), against the
     training base rate.
  C  extensions: xM$ AAV for the bought FA years x a fitted control discount,
     against a WAR-only rule, on Cot's extension rows.
  D  FA destination: a club-level xM$ demand term added to the destination
     model's arm N, the destination gate's own C3 form.
  E  Trade Machine: sign disagreements between market-rate surplus and the
     Trade Machine's surplus, descriptive.

xM$ here is fa_market.MarketModel refit AS OF each winter exactly as Gate 2
refits it for a test winter (registration section 2). Nothing served moves:
the one output is a lab artifact under data/_labs/, which ships in neither
deploy consumer. arb_model, arb_export, fa_destination, fa_market and
xm_export are imported, never edited; the lab's two arbitration fit functions
carry a feature hook and are pinned to reproduce arb_model.forward_chain's
champion before any score.

Usage:
    python tools/xm_downstream_lab.py --dry-run            # fixture, nulls
    python -u tools/xm_downstream_lab.py --frames-only --task-dir DIR  # counts only
    python -u tools/xm_downstream_lab.py --read --task-dir DIR
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import traceback
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

GATE_DOC = "docs/xm/XM_DOWNSTREAM.md"
OUT_PATH = ROOT / "data" / "_labs" / "xm_downstream" / "xm_downstream_eval.json"
DRY_RUN_DIR = ROOT / ".cache" / "xm_downstream" / "dry_run"
PEOPLE_DIR = ROOT / ".cache" / "mlb_people"

SEED = 20261019
BOOT_B = 4000
MIN_TRAIN_ROWS_XM = 100          # the Gate 2 fold rule
FIRST_XM_WINTER = 2017
XM_PATH_YEARS = 10               # xm_export's counterfactual path length

# Test A
SHARES = {3: {1: 0.40, 2: 0.60, 3: 0.80}, 4: {1: 0.25, 2: 0.40, 3: 0.60, 4: 0.80}}
SHARE_OTHER = 0.80
PLANT_A_BETA = 0.25
PLANT_A_FLOOR = 0.81
REPRO_TOL = 1e-6
# Test B
PLANT_B_SLOPE = -2.0
LOGIT_MAX_ITER = 100
# Test C
COTS_SERVICE_THROUGH = 2025      # Cot's 'ML service' is as of the end of 2025
SVC_DAYS = 172.0
EXT_MIN_TRAIN = 20
PLANT_C = {"a": -0.3, "b": -0.1, "sd": 0.30}
# Test D
PLANT_D_BETA = 0.5
PERM_SHARE_CAP = 0.60
HOLM_FIRST, HOLM_SECOND = 0.025, 0.05
# Test E
TOP_K = 15


# ==========================================================================
# small pure pieces
# ==========================================================================

def norm_name(s) -> str:
    """Lower-case ascii, punctuation dropped, a generational suffix dropped."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[.'`]", "", t.lower())
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    t = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", t)
    return t


def arb_share(step, super_two) -> float:
    """Registration section 3: the arb-year share of the market AAV."""
    n = 4 if super_two is True else 3
    try:
        k = int(step)
    except (TypeError, ValueError):
        return SHARE_OTHER
    return SHARES[n].get(k, SHARE_OTHER)


def xm_arb_value(aav, share: float, league_min) -> float:
    """log(max(share x AAV, league minimum) / 1e6); a missing AAV reads the
    league minimum."""
    base = share * float(aav) if aav else 0.0
    return math.log(max(base, float(league_min or 0.0), 1.0) / 1e6)


def cluster_lb(loss_cmp, loss_cand, clusters, B: int = BOOT_B, seed: int = SEED) -> dict:
    """Paired improvement mean(loss_cmp) - mean(loss_cand) on identical rows,
    and the 5th percentile of its player-clustered bootstrap (the one-sided 95
    percent lower bound)."""
    a = np.asarray(loss_cmp, float)
    b = np.asarray(loss_cand, float)
    if a.size == 0:
        return {"n": 0, "clusters": 0, "improvement": None, "lb05": None,
                "B": B, "seed": seed}
    d = a - b
    keys = sorted({str(c) for c in clusters})
    ix = {k: i for i, k in enumerate(keys)}
    cl = np.asarray([ix[str(c)] for c in clusters])
    K = len(keys)
    S = np.bincount(cl, weights=d, minlength=K)
    N = np.bincount(cl, minlength=K).astype(float)
    rng = np.random.default_rng(seed)
    stats = np.empty(B)
    for i in range(B):
        dr = rng.integers(0, K, K)
        stats[i] = S[dr].sum() / N[dr].sum()
    return {"n": int(d.size), "clusters": K, "improvement": float(d.mean()),
            "lb05": float(np.percentile(stats, 5)), "B": B, "seed": seed,
            "mean_cmp": float(a.mean()), "mean_cand": float(b.mean())}


def logit_fit(x, y, iters: int = LOGIT_MAX_ITER) -> tuple[np.ndarray, dict]:
    """Logistic regression with an intercept by Newton steps, no penalty."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(x)), x])
    w = np.zeros(2)
    conv, it = False, 0
    for it in range(1, iters + 1):
        z = np.clip(X @ w, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        g = X.T @ (y - p)
        H = X.T @ (X * (p * (1 - p))[:, None]) + 1e-12 * np.eye(2)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w = w + step
        if float(np.max(np.abs(step))) < 1e-10:
            conv = True
            break
    return w, {"converged": conv, "iterations": it}


def logit_pred(w, x) -> np.ndarray:
    z = np.clip(w[0] + w[1] * np.asarray(x, float), -30, 30)
    return 1.0 / (1.0 + np.exp(-z))


def brier(p, y) -> np.ndarray:
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def logloss(p, y) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def auc(p, y) -> float | None:
    p = np.asarray(p, float)
    y = np.asarray(y, int)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def ols(X, y) -> np.ndarray:
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


# ---- Cot's sheets --------------------------------------------------------

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})\b")
_SVC_RE = re.compile(r"ML service:\s*(\d+)\.(\d{1,3})")
_SEG_RE = re.compile(r"(?<![\d$.])(\d{2})(?:\s*-\s*(\d{2}))?\s*:\s*")
_SAL_START = re.compile(r"^\s*\d{2}(?:\s*-\s*\d{2})?\s*:\s*\$?")


def service_years(facts) -> float | None:
    """'ML service: 7.159' -> 7 + 159 / 172."""
    for f in facts or []:
        m = _SVC_RE.search(str(f))
        if m:
            return int(m.group(1)) + int(m.group(2)) / SVC_DAYS
    return None


def parse_salary_note(note: str) -> tuple[dict, int] | None:
    """A per-year salary note ('23 :$4M, 24 :$9M, 25-29 :$18M annually,
    30-34 : $90M player option ...') -> ({season: usd}, option segments
    skipped). None when the note is not a per-year salary note."""
    import ingest_cots as ic
    if not note or "$" not in note or not _SAL_START.match(note):
        return None
    ms = list(_SEG_RE.finditer(note))
    if not ms:
        return None
    out, opt = {}, 0
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(note)
        text = note[m.end():end].strip().rstrip(",").strip()
        a = 2000 + int(m.group(1))
        b = 2000 + int(m.group(2)) if m.group(2) else a
        if b < a:
            continue
        if "option" in text.lower():
            opt += 1
            continue
        v = ic.parse_money(text)
        if v is None:
            continue
        if b > a and "total" in text.lower():
            v = v / (b - a + 1)
        for s in range(a, b + 1):
            out[s] = float(v)
    return (out, opt) if out else None


def extension_row(player: dict, contract: dict, mlbam: int, appear: set,
                  through: int = COTS_SERVICE_THROUGH) -> tuple[dict | None, str]:
    """One Cot's extension contract -> the test C row, or (None, reason)."""
    note = next((n for n in contract.get("notes") or []
                 if re.search(r"signed extension", n, re.I)), None)
    if note is None:
        return None, "not_extension"
    S0, last = contract.get("first_season"), contract.get("last_season")
    if not S0 or not last or last < S0:
        return None, "no_span"
    svc = service_years(player.get("facts"))
    if svc is None:
        return None, "no_service"
    m = _DATE_RE.search(note)
    sign = None
    if m:
        try:
            sign = date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            sign = None
    acc = sum(1 for s in range(int(S0), through + 1) if s in appear)
    svc0 = max(0.0, svc - acc)
    if svc0 >= 6.0:
        return None, "service_6_plus"
    F = int(S0) + int(math.ceil(6.0 - svc0 - 1e-9))
    sal, spread, opt = None, False, 0
    for n in contract.get("notes") or []:
        got = parse_salary_note(n)
        if got:
            sal, opt = got
            break
    if sal:
        sal = {s: v for s, v in sal.items() if int(S0) <= s <= int(last)}
    if not sal:
        tot = contract.get("total_usd")
        if not tot:
            return None, "no_salary"
        n_yr = int(last) - int(S0) + 1
        sal = {s: float(tot) / n_yr for s in range(int(S0), int(last) + 1)}
        spread = True
    bought = [sal[s] for s in range(max(F, int(S0)), int(last) + 1) if s in sal]
    if not bought:
        return None, "no_fa_year_bought"
    return {"player": player.get("name"), "sheet": player.get("sheet"), "mlbam": int(mlbam),
            "S0": int(S0), "last": int(last), "sign_date": sign.isoformat() if sign else None,
            "svc_cot": round(svc, 4), "svc0": round(svc0, 4), "F": F, "ctrl": F - int(S0),
            "n_bought": len(bought), "bought_aav": float(np.mean(bought)),
            "spread": spread, "option_segments": opt,
            "in_season": bool(sign is not None and sign < date(int(S0) - 1, 10, 1)),
            "label": contract.get("label")}, "ok"


# ---- club demand (test D) ------------------------------------------------

def zscore(vals) -> list:
    v = np.asarray(vals, float)
    sd = float(v.std())
    if sd <= 0:
        return [0.0] * len(v)
    return [float(x) for x in (v - v.mean()) / sd]


def club_demand(need_usd: dict, tax_prev: dict, threshold_usd: float, orgs) -> tuple[list, dict]:
    """demand_j = min(max(room_j, 0), need_j) / 1e6, z-scored across the clubs
    (registration section 6). Unknown payroll gives room 0, counted."""
    raw, unknown = [], 0
    for o in orgs:
        T = tax_prev.get(o)
        if T is None:
            unknown += 1
            room = 0.0
        else:
            room = float(threshold_usd) - float(T)
        raw.append(min(max(room, 0.0), float(need_usd.get(o, 0.0))) / 1e6)
    return zscore(raw), {"raw_musd": [round(x, 3) for x in raw], "unknown_payroll": unknown}


def holm_c3(rr: dict, ll: dict, M: dict, draws: np.ndarray, cand="NX", base="N",
            perm="NX_PERM") -> dict:
    """The destination gate's C3 form for cand against base, with perm's share."""
    def ple0(d):
        return (1.0 + float(np.sum(d <= 0))) / (draws.shape[0] + 1.0)
    if rr[cand].size:
        d_mrr = rr[cand][draws].mean(axis=1) - rr[base][draws].mean(axis=1)
        d_ll = ll[base][draws].mean(axis=1) - ll[cand][draws].mean(axis=1)
        p = {"mrr": ple0(d_mrr), "log_loss": ple0(d_ll)}
    else:
        p = {"mrr": 1.0, "log_loss": 1.0}
    order = sorted(p, key=lambda k: (p[k], k))
    rejected = []
    if p[order[0]] <= HOLM_FIRST:
        rejected.append(order[0])
        if p[order[1]] <= HOLM_SECOND:
            rejected.append(order[1])
    favours, shares = {}, {}
    for k in ("mrr", "log_loss"):
        mc, mb, mp = M[k][cand], M[k][base], M[k][perm]
        favours[k] = (mc is not None and mb is not None and mc > mb)
        shares[k] = ((mp - mb) / (mc - mb)) if (favours[k] and mp is not None) else None
    ok = (bool(rejected) and all(favours[k] and shares[k] is not None
                                 and shares[k] < PERM_SHARE_CAP for k in rejected))
    return {"pass": bool(ok), "p": p, "holm_rejected": rejected,
            "point_favours_cand": favours, "perm_share": shares}


# ---- the Trade Machine sign check (test E) -------------------------------

def sign_check(xm_doc: dict, tm_by_mlbam: dict, k: int = TOP_K) -> dict:
    cols = xm_doc.get("columns") or []
    ix = {c: i for i, c in enumerate(cols)}
    rows, no_tm = [], 0
    for key, r in (xm_doc.get("players") or {}).items():
        ms = r[ix["msur_xm"]]
        if ms is None:
            continue
        mid = r[ix["mlbam"]]
        tm = tm_by_mlbam.get(int(mid)) if mid is not None else None
        if tm is None:
            no_tm += 1
            continue
        rows.append({"id": key, "key": r[ix["key"]], "name": r[ix["name"]], "mlbam": mid,
                     "club": r[ix["club"]],
                     "pop": r[ix["pop"]], "ctrl": r[ix["ctrl"]], "ctrl_src": r[ix["ctrl_src"]],
                     "msur_xm": int(ms), "msur_fair": r[ix["msur_fair"]], "tm_sur_npv": int(tm)})

    def opposite(a, b):
        return a is not None and b is not None and a != 0 and b != 0 and (a > 0) != (b > 0)

    dis = [r for r in rows if opposite(r["msur_xm"], r["tm_sur_npv"])]
    dis_f = [r for r in rows if opposite(r["msur_fair"], r["tm_sur_npv"])]
    top = sorted(dis, key=lambda r: (-abs(r["msur_xm"] - r["tm_sur_npv"]), str(r["key"])))[:k]
    by_dir = Counter("xm_pos_tm_neg" if r["msur_xm"] > 0 else "xm_neg_tm_pos" for r in dis)
    return {"n_joined": len(rows), "n_no_tm_price": no_tm,
            "n_opposite_sign": len(dis),
            "share_opposite_sign": round(len(dis) / len(rows), 4) if rows else None,
            "by_direction": dict(sorted(by_dir.items())),
            "n_opposite_sign_fair_leg": len(dis_f),
            "share_opposite_sign_fair_leg": round(len(dis_f) / len(rows), 4) if rows else None,
            "top_disagreements": [{**r, "abs_gap": abs(r["msur_xm"] - r["tm_sur_npv"])}
                                  for r in top]}


def tm_prices(detail_doc: dict) -> dict:
    """{mlbam: proj.surNpv} off mlb_player_detail.json."""
    out = {}
    for p in (detail_doc.get("players") or {}).values():
        pr = p.get("proj") or {}
        if p.get("mlbam") and pr.get("surNpv") is not None:
            try:
                out[int(p["mlbam"])] = float(pr["surNpv"])
            except (TypeError, ValueError):
                continue
    return out


# ==========================================================================
# the as-of xM$ engine (registration section 2)
# ==========================================================================

class AsOfXM:
    """fa_market.MarketModel refit for winter W on class years below W, the
    Gate 2 fold body, and a price for any player with MLB history."""

    def __init__(self, enriched=None):
        import fa_market as fm
        import fa_projection as fp
        self.fm, self.fp = fm, fp
        self.corpus = fp.build_corpus()
        self.league = self.corpus["league"]
        self.by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
        for side in ("hit", "pit"):
            for r in self.corpus[side]:
                if r.get("mlbam"):
                    self.by_player[side][int(r["mlbam"])][int(r["season"])] = r
        self.enriched = enriched if enriched is not None else fm.enriched_signings(2015, 2026)
        self._w: dict = {}
        self._people: dict = {}
        self._cache: dict = {}
        self.counts = Counter()

    def people(self, season: int) -> dict:
        if season not in self._people:
            out = {}
            p = PEOPLE_DIR / f"people_{season}.json"
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                i = {c: n for n, c in enumerate(d["columns"])}
                for r in d["rows"]:
                    out[int(r[i["id"]])] = (r[i["name"]], r[i["pos"]])
            except (OSError, ValueError, KeyError):
                pass
            self._people[season] = out
        return self._people[season]

    def winter(self, W: int):
        if W not in self._w:
            fm, fp = self.fm, self.fp
            train = [s for s in self.enriched if s["class_year"] < W]
            if len(train) < MIN_TRAIN_ROWS_XM:
                self._w[W] = None
            else:
                model = fm.MarketModel(train, fm.dollars_per_war_by_winter(train))
                model.supply_by_year[W] = fm._supply(
                    [s for s in self.enriched if s["class_year"] == W], W)
                curves, war_map = fp.fitted_models(self.corpus, W - 1,
                                                   use_def=fm.FA_PRICING_USE_DEF)
                self._w[W] = {"model": model, "curves": curves, "war_map": war_map,
                              "n_train": len(train)}
        return self._w[W]

    def hist(self, mlbam: int, side: str, W: int) -> list:
        seasons = self.by_player[side].get(int(mlbam)) or {}
        return [seasons[t] for t in (W - 1, W - 2, W - 3) if t in seasons]

    def war(self, mlbam: int, season: int) -> float:
        tot = 0.0
        for side in ("hit", "pit"):
            r = (self.by_player[side].get(int(mlbam)) or {}).get(int(season))
            if r is not None:
                tot += float(r.get("war") or 0.0)
        return tot

    def price(self, mlbam: int, W: int, qo: bool = False, name: str | None = None) -> dict | None:
        key = (int(mlbam), int(W), bool(qo))
        if key in self._cache:
            return self._cache[key]
        out = self._price(int(mlbam), int(W), bool(qo), name)
        self._cache[key] = out
        self.counts["priced" if out else "unpriced"] += 1
        return out

    def _price(self, mlbam: int, W: int, qo: bool, name) -> dict | None:
        fm = self.fm
        ctx = self.winter(W)
        if ctx is None:
            self.counts["no_model_for_winter"] += 1
            return None
        pp = self.people(W - 1).get(mlbam) or self.people(W).get(mlbam)
        pos = (pp[1] if pp else None) or None
        hit_h, pit_h = self.hist(mlbam, "hit", W), self.hist(mlbam, "pit", W)
        if pos in ("P", "SP", "RP", "LHP", "RHP"):
            side = "pit"
        elif pos:
            side = "hit"
        else:
            side = "pit" if (pit_h and not hit_h) else "hit"
        hist = pit_h if side == "pit" else hit_h
        if not hist:
            self.counts["no_history_on_side"] += 1
            return None
        age_row = next((h for h in hist if h.get("age")), None)
        if age_row is None:
            self.counts["no_age"] += 1
            return None
        age = age_row["age"] + (W - age_row["season"])
        path = fm.contract_war_path(hist, side, W, XM_PATH_YEARS, age, ctx["curves"],
                                    ctx["war_map"], self.league, use_ml=False)
        if path is None:
            self.counts["no_path"] += 1
            return None
        if side == "pit":
            pos2 = "SP" if (path.get("role") or "").upper() == "SP" else "RP"
        else:
            pos2 = pos if pos and pos not in ("P", "TWP") else "DH"
        s = {"player_key": f"mlbam_{mlbam}" + ("_qo" if qo else ""),
             "player_name": name or (pp[0] if pp else None), "position": pos2,
             "class_year": W, "qo": qo, "mlbam_id": mlbam, "_war_path": path, "_age": age}
        pred = ctx["model"].predict(s)
        return {"aav": float(pred["proj_aav_usd"]), "total": float(pred["proj_guarantee_usd"]),
                "years": float(pred["proj_years"]), "side": side, "pos": pos2, "age": age}

    def engine_check(self, tuples: list) -> dict:
        """Gate 2's collected predictions against this engine's winter model on
        the same signing rows: the refit is the same fit."""
        by = defaultdict(list)
        for s in self.enriched:
            by[(s["class_year"], s.get("player_key"))].append(s)
        diffs, n, missing = [], 0, 0
        for t in tuples:
            W, key = int(t[0]), t[1]
            rows = by.get((W, key)) or []
            ctx = self.winter(W)
            if len(rows) != 1 or ctx is None:
                missing += 1
                continue
            pred = ctx["model"].predict(rows[0])
            diffs.append(abs(pred["proj_guarantee_usd"] / 1e6 - float(t[2]))
                         / max(abs(float(t[2])), 1e-9))
            n += 1
        return {"n_compared": n, "n_not_compared": missing,
                "max_rel_diff": (max(diffs) if diffs else None)}


# ==========================================================================
# test A: arbitration
# ==========================================================================

def _feat(Mod, r, metrics, keys, extra):
    v = Mod.features(r, Mod._mx(metrics, r), keys)
    if extra is not None:
        v = v + [float(extra[(int(r["mlbam"]), int(r["season"]))])]
    return v


def _fit_stage1(Mod, rows, metrics, defl, extra, keys):
    from efv_mde_lab import ridge_fit, ridge_pred
    X, y = [], []
    for r in rows:
        if int(r["arb_year"]) != 1 or not r.get("salary"):
            continue
        X.append(_feat(Mod, r, metrics, keys, extra))
        y.append(math.log(Mod.deflate(r["salary"], r["season"], defl)))
    if len(y) < 20:
        return None
    X, y = np.asarray(X, float), np.asarray(y, float)
    m = ridge_fit(X, y, np.ones(len(y)))
    if m is None:
        return None
    resid = y - ridge_pred(m, X)
    return {"m": m, "smear": float(np.mean(np.exp(resid)))}


def _fit_stage2(Mod, rows, metrics, defl, extra, keys):
    from efv_mde_lab import ridge_fit, ridge_pred
    X, y, steps = [], [], []
    for r in rows:
        if int(r["arb_year"]) < 2 or not r.get("salary") or not r.get("prior_salary"):
            continue
        a = Mod.deflate(r["salary"], r["season"], defl)
        b = Mod.deflate(r["prior_salary"], r["season"] - 1, defl)
        if b <= 0:
            continue
        ratio = a / b
        if ratio <= Mod.MAX_CUT_FLOOR:
            continue
        X.append(_feat(Mod, r, metrics, keys, extra))
        y.append(math.log(ratio - Mod.MAX_CUT_FLOOR))
        steps.append(int(r["arb_year"]))
    if len(y) < 20:
        return None
    X, y = np.asarray(X, float), np.asarray(y, float)
    m = ridge_fit(X, y, np.ones(len(y)))
    if m is None:
        return None
    resid = y - ridge_pred(m, X)
    smear = {}
    for s in sorted(set(steps)):
        idx = [i for i, v in enumerate(steps) if v == s]
        smear[s] = float(np.mean(np.exp(resid[idx]))) if idx else 1.0
    return {"m": m, "smear_by_step": smear}


def _predict(Mod, r, metrics, defl, s1, s2, extra, keys):
    from efv_mde_lab import ridge_pred
    step = int(r["arb_year"])
    if step == 1:
        if not s1:
            return None
        x = np.asarray([_feat(Mod, r, metrics, keys, extra)], float)
        return float(math.exp(ridge_pred(s1["m"], x)[0]) * s1["smear"])
    if not s2 or not r.get("prior_salary"):
        return None
    x = np.asarray([_feat(Mod, r, metrics, keys, extra)], float)
    z = float(ridge_pred(s2["m"], x)[0])
    sm = s2["smear_by_step"].get(step, 1.0)
    b = Mod.deflate(r["prior_salary"], r["season"] - 1, defl)
    return float(b * (Mod.MAX_CUT_FLOOR + math.exp(z) * sm))


def arb_chain(Mod, fr, metrics, seasons, extra=None) -> dict:
    """arb_model.forward_chain's folds with a feature hook:
    {(mlbam, season): deflated prediction}."""
    keys = Mod.CHAMPION_KEYS
    seasons = sorted(seasons)
    out = {}
    for i in range(1, len(seasons)):
        test_y = seasons[i]
        tr = [r for r in fr if r["season"] < test_y]
        te = [r for r in fr if r["season"] == test_y]
        if len(tr) < 60 or len(te) < 15:
            continue
        defl = Mod.fit_deflator(tr, base_year=seasons[0])
        s1 = _fit_stage1(Mod, tr, metrics, defl, extra, keys)
        s2 = _fit_stage2(Mod, tr, metrics, defl, extra, keys)
        for r in te:
            if not r.get("salary"):
                continue
            out[(int(r["mlbam"]), int(r["season"]))] = _predict(Mod, r, metrics, defl, s1, s2,
                                                                extra, keys)
    return out


def permute_in_cells(vals: dict, cell_of: dict, seed: int = SEED) -> dict:
    """Values permuted across keys within each cell, one draw, cells in
    sorted order."""
    rng = np.random.default_rng(seed)
    cells = defaultdict(list)
    for k in sorted(vals):
        cells[cell_of[k]].append(k)
    out = {}
    for c in sorted(cells):
        ks = cells[c]
        perm = rng.permutation(len(ks))
        for i, k in enumerate(ks):
            out[k] = vals[ks[int(perm[i])]]
    return out


def arb_repro(Mod, fr, metrics, seasons) -> dict:
    """The lab's fit functions with no extra feature against
    arb_model.forward_chain's champion, row by row (no score is computed)."""
    cur = Mod.forward_chain(fr, metrics, seasons=seasons)
    base = arb_chain(Mod, fr, metrics, seasons, None)
    diffs, n = [], 0
    for r in cur:
        k = (int(r["mlbam"]), int(r["season"]))
        a, b = r.get("champion"), base.get(k)
        if a is None and b is None:
            continue
        n += 1
        if a is None or b is None:
            diffs.append(float("inf"))
        else:
            diffs.append(abs(a - b) / max(abs(a), 1e-9))
    mx = max(diffs) if diffs else None
    return {"n": n, "max_rel_diff": mx, "tolerance": REPRO_TOL,
            "pass": bool(mx is not None and mx <= REPRO_TOL)}


def arb_score(Mod, fr, metrics, seasons, xm_vals: dict, perm_vals: dict,
              swartz: dict | None = None) -> dict:
    cur = Mod.forward_chain(fr, metrics, seasons=seasons)
    res = {}
    aug = arb_chain(Mod, fr, metrics, seasons, xm_vals)
    prm = arb_chain(Mod, fr, metrics, seasons, perm_vals)
    rows = []
    for r in cur:
        k = (int(r["mlbam"]), int(r["season"]))
        if r.get("served") is None or aug.get(k) is None or prm.get(k) is None or not r.get("actual"):
            continue
        rows.append({"k": k, "step": int(r["arb_year"]), "actual": float(r["actual"]),
                     "salary": float(r["salary"]), "served": float(r["served"]),
                     "champion": r.get("champion"), "aug": float(aug[k]), "perm": float(prm[k])})
    act = np.asarray([x["actual"] for x in rows])
    err = {m: np.abs(np.asarray([x[m] for x in rows]) - act) for m in ("served", "aug", "perm")}
    cl = [x["k"][0] for x in rows]
    c1 = cluster_lb(err["served"], err["aug"], cl)
    c2 = cluster_lb(err["perm"], err["aug"], cl)
    passed = bool(c1["lb05"] is not None and c1["lb05"] > 0
                  and c2["lb05"] is not None and c2["lb05"] > 0)
    res.update({"n_scored": len(rows),
                "mae": {m: (float(err[m].mean()) if len(rows) else None) for m in err},
                "clause_i_current_minus_aug": c1, "clause_ii_perm_minus_aug": c2,
                "pass": passed})

    def mdape(key, sub):
        v = [abs(x[key] - x["actual"]) / x["actual"] for x in sub if x.get(key) is not None]
        return float(np.median(v)) if v else None

    per = {}
    for st in sorted({x["step"] for x in rows}):
        sub = [x for x in rows if x["step"] == st]
        a2 = np.asarray([x["actual"] for x in sub])
        per[str(st)] = {"n": len(sub), **{f"mae_{m}": float(np.mean(np.abs(
            np.asarray([x[m] for x in sub]) - a2))) for m in ("served", "aug", "perm")},
            **{f"mdape_{m}": mdape(m, sub) for m in ("served", "aug", "perm", "champion")}}
    res["per_step"] = per
    res["mdape"] = {m: mdape(m, rows) for m in ("served", "aug", "perm", "champion")}
    champ_rows = [x for x in rows if x["champion"] is not None]
    if champ_rows:
        a3 = np.asarray([x["actual"] for x in champ_rows])
        res["reported_aug_vs_unaugmented_champion"] = cluster_lb(
            np.abs(np.asarray([x["champion"] for x in champ_rows]) - a3),
            np.abs(np.asarray([x["aug"] for x in champ_rows]) - a3),
            [x["k"][0] for x in champ_rows])
    if swartz:
        sw = [x for x in rows if swartz.get(x["k"])]
        if sw:
            def ape(key):
                return float(np.median([abs(x[key] - x["actual"]) / x["actual"] for x in sw]))
            res["reported_swartz"] = {
                "n": len(sw),
                "mdape_swartz": float(np.median([abs(swartz[x["k"]] - x["salary"]) / x["salary"]
                                                 for x in sw])),
                "mdape_served": ape("served"), "mdape_aug": ape("aug"),
                "note": "nominal against nominal; a fold's deflator cancels in an absolute percent error"}
    return res


def arb_test(Mod, fr, metrics, seasons, xm_vals: dict, swartz=None, real=True) -> dict:
    """Planted recovery (P-A1, P-A2), then the real read once."""
    step_of = {(int(r["mlbam"]), int(r["season"])): int(r["arb_year"]) for r in fr}
    cell = {k: (k[1], step_of[k]) for k in xm_vals}
    perm_vals = permute_in_cells(xm_vals, cell, SEED)
    out = {}
    # P-A1: planted signal
    keys = list(xm_vals)
    v = np.asarray([xm_vals[k] for k in keys])
    z = dict(zip(keys, ((v - v.mean()) / (v.std() if v.std() > 0 else 1.0)).tolist()))
    fr_sim = []
    for r in fr:
        x = dict(r)
        k = (int(r["mlbam"]), int(r["season"]))
        if x.get("salary") and k in z:
            s = float(x["salary"]) * math.exp(PLANT_A_BETA * z[k])
            if int(x["arb_year"]) >= 2 and x.get("prior_salary"):
                s = max(s, PLANT_A_FLOOR * float(x["prior_salary"]))
            x["salary"] = s
        fr_sim.append(x)
    p1 = arb_score(Mod, fr_sim, metrics, seasons, xm_vals, perm_vals)
    # P-A2: planted null, noise in place of the feature
    rng = np.random.default_rng(SEED)
    noise = {k: float(rng.normal()) for k in sorted(xm_vals)}
    p2 = arb_score(Mod, fr, metrics, seasons, noise, permute_in_cells(noise, cell, SEED))
    out["planted"] = {"P_A1_signal": {"beta": PLANT_A_BETA, "pass_rule_passed": p1["pass"],
                                      "ok": bool(p1["pass"]), "detail": _slim(p1)},
                      "P_A2_null": {"pass_rule_passed": p2["pass"], "ok": not p2["pass"],
                                    "detail": _slim(p2)}}
    out["planted_ok"] = bool(out["planted"]["P_A1_signal"]["ok"]
                             and out["planted"]["P_A2_null"]["ok"])
    return out, perm_vals


def _slim(res: dict) -> dict:
    return {k: res[k] for k in ("n_scored", "mae", "clause_i_current_minus_aug",
                                "clause_ii_perm_minus_aug", "pass") if k in res}


# ==========================================================================
# test B: qualifying offers
# ==========================================================================

def qo_score(rows: list) -> dict:
    """rows: {mlbam, W, x, y}. Forward chain by winter."""
    winters = sorted({r["W"] for r in rows})
    scored, folds = [], {}
    for Y in winters:
        tr = [r for r in rows if r["W"] < Y]
        te = [r for r in rows if r["W"] == Y]
        ys = [r["y"] for r in tr]
        if not te or not (1 in ys and 0 in ys):
            continue
        w, info = logit_fit([r["x"] for r in tr], ys)
        base = float(np.mean(ys))
        pl = logit_pred(w, [r["x"] for r in te])
        folds[str(Y)] = {"n_train": len(tr), "n_test": len(te), "coef": [float(c) for c in w],
                         **info, "base_rate": base,
                         "accepted_in_test": int(sum(r["y"] for r in te))}
        for r, p in zip(te, pl):
            scored.append({**r, "p_logit": float(p), "p_base": base})
    y = np.asarray([r["y"] for r in scored], float)
    pl = np.asarray([r["p_logit"] for r in scored])
    pb = np.asarray([r["p_base"] for r in scored])
    lb = cluster_lb(brier(pb, y), brier(pl, y), [r["mlbam"] for r in scored])
    res = {"n_scored": len(scored), "accepted": int(y.sum()) if len(y) else 0,
           "scored_winters": sorted({r["W"] for r in scored}), "folds": folds,
           "brier": {"base": float(brier(pb, y).mean()) if len(y) else None,
                     "logit": float(brier(pl, y).mean()) if len(y) else None},
           "log_loss": {"base": float(logloss(pb, y).mean()) if len(y) else None,
                        "logit": float(logloss(pl, y).mean()) if len(y) else None},
           "auc_logit": auc(pl, y) if len(y) else None,
           "base_minus_logit_brier": lb,
           "pass": bool(lb["lb05"] is not None and lb["lb05"] > 0)}
    return res


def qo_lowo(rows: list) -> dict:
    """Leave-one-winter-out twin (context only: it trains on later winters)."""
    out = []
    for Y in sorted({r["W"] for r in rows}):
        tr = [r for r in rows if r["W"] != Y]
        te = [r for r in rows if r["W"] == Y]
        ys = [r["y"] for r in tr]
        if not (1 in ys and 0 in ys):
            continue
        w, _ = logit_fit([r["x"] for r in tr], ys)
        for r, p in zip(te, logit_pred(w, [r["x"] for r in te])):
            out.append((r["y"], float(p), float(np.mean(ys))))
    if not out:
        return {"n": 0}
    y = np.asarray([o[0] for o in out], float)
    pl = np.asarray([o[1] for o in out])
    pb = np.asarray([o[2] for o in out])
    return {"n": len(out), "accepted": int(y.sum()), "brier_logit": float(brier(pl, y).mean()),
            "brier_base": float(brier(pb, y).mean()), "auc_logit": auc(pl, y)}


def qo_test(rows: list) -> dict:
    out = {}
    x = np.asarray([r["x"] for r in rows], float)
    rate = float(np.mean([r["y"] for r in rows])) if rows else 0.0
    lo, hi = -50.0, 50.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if float(np.mean(logit_pred([mid, PLANT_B_SLOPE], x))) < rate:
            lo = mid
        else:
            hi = mid
    a0 = (lo + hi) / 2
    rng = np.random.default_rng(SEED)
    sim = [{**r, "y": int(rng.random() < p)} for r, p in
           zip(rows, logit_pred([a0, PLANT_B_SLOPE], x))]
    p1 = qo_score(sim)
    rng2 = np.random.default_rng(SEED)
    perm = []
    for W in sorted({r["W"] for r in rows}):
        sub = [r for r in rows if r["W"] == W]
        ys = [r["y"] for r in sub]
        pr = rng2.permutation(len(sub))
        perm += [{**r, "y": ys[int(pr[i])]} for i, r in enumerate(sub)]
    p2 = qo_score(perm)
    out["planted"] = {
        "P_B1_signal": {"slope": PLANT_B_SLOPE, "a0": a0, "accepted": p1["accepted"],
                        "pass_rule_passed": p1["pass"], "ok": bool(p1["pass"]),
                        "brier": p1["brier"], "lb": p1["base_minus_logit_brier"]},
        "P_B2_null": {"pass_rule_passed": p2["pass"], "ok": not p2["pass"],
                      "brier": p2["brier"], "lb": p2["base_minus_logit_brier"]}}
    out["planted_ok"] = bool(p1["pass"] and not p2["pass"])
    out["void_reason"] = (None if out["planted_ok"] else
                          ("underpowered at this frame" if not p1["pass"]
                           else "planted null passed"))
    return out


# ==========================================================================
# test C: extensions
# ==========================================================================

def ext_score(rows: list) -> dict:
    """rows: {mlbam, S0, ctrl, war3, plat, log_xm, y}. Forward chain by S0."""
    def design(r, kind):
        if kind == "xm":
            return [1.0, r["ctrl"]]
        if kind == "war":
            return [1.0, r["ctrl"], r["war3"], r["plat"]]
        if kind == "const":
            return [1.0, r["ctrl"]]
        return [1.0, r["log_xm"], r["ctrl"]]          # free coefficient

    def target(r, kind):
        return r["y"] - r["log_xm"] if kind == "xm" else r["y"]

    kinds = ("xm", "war", "const", "free")
    seasons = sorted({r["S0"] for r in rows})
    scored, folds = [], {}
    for Y in seasons:
        tr = [r for r in rows if r["S0"] < Y]
        te = [r for r in rows if r["S0"] == Y]
        if len(tr) < EXT_MIN_TRAIN or not te:
            continue
        co = {k: ols([design(r, k) for r in tr], [target(r, k) for r in tr]) for k in kinds}
        folds[str(Y)] = {"n_train": len(tr), "n_test": len(te),
                         **{k: [float(c) for c in co[k]] for k in kinds}}
        for r in te:
            pr = {k: float(np.dot(co[k], design(r, k))) + (r["log_xm"] if k == "xm" else 0.0)
                  for k in kinds}
            scored.append({**r, **{f"pred_{k}": pr[k] for k in kinds}})
    y = np.asarray([r["y"] for r in scored], float)
    err = {k: np.abs(np.asarray([r[f"pred_{k}"] for r in scored]) - y) for k in kinds}
    lb = cluster_lb(err["war"], err["xm"], [r["mlbam"] for r in scored])
    res = {"n_scored": len(scored), "scored_seasons": sorted({r["S0"] for r in scored}),
           "folds": folds,
           "mae_log": {k: (float(err[k].mean()) if len(y) else None) for k in kinds},
           "mdape": {k: (float(np.median(np.abs(np.exp(np.asarray(
               [r[f"pred_{k}"] for r in scored]) - y) - 1))) if len(y) else None) for k in kinds},
           "war_minus_xm": lb,
           "pass": bool(lb["lb05"] is not None and lb["lb05"] > 0)}
    if rows:
        allc = ols([design(r, "xm") for r in rows], [target(r, "xm") for r in rows])
        res["discount_all_rows"] = {str(c): round(float(math.exp(allc[0] + allc[1] * c)), 4)
                                    for c in sorted({r["ctrl"] for r in rows})}
    return res


def ext_test(rows: list) -> dict:
    rng = np.random.default_rng(SEED)
    e = rng.normal(0.0, PLANT_C["sd"], len(rows))
    sim1 = [{**r, "y": r["log_xm"] + PLANT_C["a"] + PLANT_C["b"] * r["ctrl"] + float(e[i])}
            for i, r in enumerate(rows)]
    p1 = ext_score(sim1)
    if rows:
        cw = ols([[1.0, r["ctrl"], r["war3"], r["plat"]] for r in rows], [r["y"] for r in rows])
        sim2 = [{**r, "y": float(np.dot(cw, [1.0, r["ctrl"], r["war3"], r["plat"]])) + float(e[i])}
                for i, r in enumerate(rows)]
    else:
        sim2 = []
    p2 = ext_score(sim2)
    out = {"planted": {
        "P_C1_signal": {**PLANT_C, "pass_rule_passed": p1["pass"], "ok": bool(p1["pass"]),
                        "mae_log": p1["mae_log"], "lb": p1["war_minus_xm"]},
        "P_C2_null": {"pass_rule_passed": p2["pass"], "ok": not p2["pass"],
                      "mae_log": p2["mae_log"], "lb": p2["war_minus_xm"]}}}
    out["planted_ok"] = bool(p1["pass"] and not p2["pass"])
    return out


def ext_frame(xm: AsOfXM, players: list, people_by_season, appear: dict) -> tuple[list, dict]:
    """Cot's extension rows joined to MLBAM ids, service, xM$ and WAR."""
    counts = Counter()
    rows, seen = [], set()
    for p in players:
        for c in p.get("contracts") or []:
            if not any(re.search(r"signed extension", n, re.I) for n in c.get("notes") or []):
                continue
            counts["extension_contracts"] += 1
            if service_years(p.get("facts")) is None:
                counts["drop_no_service"] += 1
                continue
            S0 = c.get("first_season")
            if not S0:
                counts["drop_no_span"] += 1
                continue
            ids = set()
            nn = norm_name(p.get("name"))
            for s in (S0 - 1, S0):
                ids |= set(people_by_season(s).get(nn, ()))
            if len(ids) != 1:
                counts["drop_name_unmatched" if not ids else "drop_name_ambiguous"] += 1
                continue
            mlbam = next(iter(ids))
            row, why = extension_row(p, c, mlbam, appear.get(mlbam, set()))
            if row is None:
                counts[f"drop_{why}"] += 1
                continue
            k = (mlbam, row["S0"], row["last"])
            if k in seen:
                counts["drop_duplicate"] += 1
                continue
            seen.add(k)
            if row["S0"] < FIRST_XM_WINTER:
                counts["drop_before_2017"] += 1
                continue
            pr = xm.price(mlbam, row["S0"], name=p.get("name"))
            if pr is None or pr["aav"] <= 0:
                counts["drop_no_xm"] += 1
                continue
            row.update({"xm_aav": pr["aav"], "log_xm": math.log(pr["aav"]),
                        "y": math.log(row["bought_aav"]),
                        "war3": round(sum(xm.war(mlbam, row["S0"] - j) for j in (1, 2, 3)), 3),
                        "plat": round(xm.war(mlbam, row["S0"] - 1), 3)})
            rows.append(row)
            counts["kept"] += 1
    return rows, dict(sorted(counts.items()))


# ==========================================================================
# test D: FA destination
# ==========================================================================

D_ARMS = {"N": ("fit_analog", "incumbent"),
          "NX": ("fit_analog", "xm_demand", "incumbent"),
          "NX_PERM": ("fit_analog", "xm_demand", "incumbent")}


def _perm_member(feat: dict, Y: int) -> dict:
    perm = np.random.default_rng(SEED + int(Y)).permutation(30)
    out = dict(feat)
    out["xm_demand"] = [feat["xm_demand"][int(perm[j])] for j in range(30)]
    return out


def dest_fit(members: list, scored_winters: list) -> dict:
    import fa_destination as fd
    out = {}
    for arm, names in D_ARMS.items():
        probs, folds = [], {}
        for Y in scored_winters:
            tr = [m for m in members if m["winter"] < Y]
            te = [m for m in members if m["winter"] == Y]
            f = (lambda m: _perm_member(m["feat"], m["winter"])) if arm == "NX_PERM" \
                else (lambda m: m["feat"])
            Xtr = fd.stack([f(m) for m in tr], names)
            Xte = fd.stack([f(m) for m in te], names)
            Xtr, Xte, stats = fd.fold_standardize(Xtr, Xte, names)
            coefs, info = fd.fit_clogit(Xtr, np.asarray([m["y"] for m in tr]), names)
            folds[str(Y)] = {"coefs": coefs, "converged": info["converged"]}
            probs.append(fd.predict_proba(Xte, coefs, names))
        out[arm] = {"folds": folds, "probs": np.vstack(probs) if probs else np.zeros((0, 30))}
    return out


def dest_score(frame: dict) -> dict:
    import fa_destination_lab as fdl
    members = fdl._scored(frame)
    fits = dest_fit(frame["members"], frame["scored_winters"])
    rr, ll, met = {}, {}, {}
    for arm in D_ARMS:
        P = fits[arm]["probs"]
        met[arm] = fdl.rank_metrics(P, members)
        rr[arm] = fdl._rr(P, members) if members else np.zeros(0)
        ll[arm] = fdl.log_losses(P, members)
        met[arm]["log_loss"] = float(ll[arm].mean()) if len(ll[arm]) else None
    draws = fdl.bootstrap_draws(len(members))
    M = {"mrr": {a: met[a]["mrr"] for a in D_ARMS},
         "log_loss": {a: (-met[a]["log_loss"] if met[a]["log_loss"] is not None else None)
                      for a in D_ARMS}}
    c3 = holm_c3(rr, ll, M, draws)
    nonconv = sum(1 for a in D_ARMS for f in fits[a]["folds"].values() if not f["converged"])
    return {"n_scored": len(members), "scored_winters": frame["scored_winters"],
            "metrics": met, "c3": c3, "pass": c3["pass"], "nonconverged_folds": nonconv,
            "folds": {a: fits[a]["folds"] for a in D_ARMS}}


def attach_demand(frame: dict, tuples: list, from_team: dict, states: dict) -> dict:
    """xm_demand on every member's feature dict; returns the per-winter block."""
    import fa_destination as fd
    need = defaultdict(lambda: defaultdict(float))
    counts = Counter()
    for t in tuples:
        W, key = int(t[0]), t[1]
        ft = from_team.get((W, key))
        club = fd.canonical_club(ft) if ft else None
        if club is None or club not in fd.ORGS:
            counts["tuple_no_club"] += 1
            continue
        need[W][club] += float(t[4]) * 1e6
        counts["tuple_counted"] += 1
    by_w = {}
    for Y in sorted({m["winter"] for m in frame["members"]}):
        st = states[Y]
        tax = {o: st["clubs"][o]["tax_payroll_prev_usd"] for o in fd.ORGS}
        z, info = club_demand(need.get(Y, {}), tax, st["threshold_usd"], fd.ORGS)
        by_w[Y] = z
        counts["unknown_payroll_club_winters"] += info["unknown_payroll"]
    for m in frame["members"]:
        m["feat"] = dict(m["feat"])
        m["feat"]["xm_demand"] = list(by_w[m["winter"]])
    return {"counts": dict(sorted(counts.items())),
            "z_by_winter": {str(Y): [round(v, 4) for v in z] for Y, z in by_w.items()}}


def dest_test(frame: dict) -> dict:
    import fa_destination as fd
    ms = frame["members"]
    names = D_ARMS["N"]
    X = fd.stack([m["feat"] for m in ms], names)
    coefs, info = fd.fit_clogit(X, np.asarray([m["y"] for m in ms]), names)
    Xd = fd.stack([m["feat"] for m in ms], ("xm_demand",))[:, :, 0] if ms else np.zeros((0, 30))
    base_u = (X @ np.asarray([coefs[n] for n in names])) if ms else np.zeros((0, 30))
    out = {"n_coefficients_all_winters": coefs}
    for tag, beta in (("P_D1_signal", PLANT_D_BETA), ("P_D2_null", 0.0)):
        rng = np.random.default_rng(SEED)
        u = base_u + beta * Xd
        sim = []
        for i, m in enumerate(ms):
            p = np.exp(u[i] - u[i].max())
            p = p / p.sum()
            sim.append({**m, "y": int(rng.choice(30, p=p))})
        res = dest_score({**frame, "members": sim})
        want = tag == "P_D1_signal"
        out[tag] = {"beta": beta, "pass_rule_passed": res["pass"],
                    "ok": bool(res["pass"]) if want else not res["pass"],
                    "c3": res["c3"], "metrics": res["metrics"]}
    out["planted_ok"] = bool(out["P_D1_signal"]["ok"] and out["P_D2_null"]["ok"])
    return out


# ==========================================================================
# artifact plumbing
# ==========================================================================

def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not math.isfinite(f) else round(f, 6)
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def persist(doc: dict, out_path: Path, step: str) -> None:
    doc.setdefault("order", []).append(step)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(_jsonable(doc), indent=1, ensure_ascii=False,
                                   allow_nan=False) + "\n", encoding="utf-8")


def verdict(planted_ok: bool, passed: bool | None) -> str:
    if not planted_ok:
        return "VOID"
    return "PASS" if passed else "FAIL"


# ==========================================================================
# inputs: real and fixture
# ==========================================================================

class Inputs:
    """What the run reads. ``fixture`` marks the dry run."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _people_index_fn(xm: AsOfXM):
    cache = {}

    def by_season(season: int) -> dict:
        if season not in cache:
            idx = defaultdict(set)
            for pid, (name, _pos) in xm.people(season).items():
                idx[norm_name(name)].add(pid)
            cache[season] = idx
        return cache[season]
    return by_season


def real_inputs() -> Inputs:
    import arb_dataset as A
    import arb_metrics as AM
    import arb_model as Mod
    import fa_cba
    import fa_destination_lab as fdl
    import fa_market as fm
    import ingest_cots as ic
    import storage
    enriched = fm.enriched_signings(2015, 2026)
    xm = AsOfXM(enriched)
    panel = A.build_panel(log=None)
    rows = panel["rows"]
    sc = A.scored_rows(rows)
    fr = Mod.attach_frame(sc, rows, Mod.FRAME)
    metrics = AM.metric_panel(2018, 2026)
    seasons = sorted({r["season"] for r in sc})
    swartz, sw_census = A.swartz_by_mlbam(rows, pool="repaired")
    players = []
    for slug, fp_ in sorted(ic.newest_files().items()):
        players += ic.parse_sheet(fp_.read_text(encoding="utf-8", errors="replace"), slug)
    dest = fdl.real_inputs()
    from_team = {(s["class_year"], s.get("player_key")): s.get("from_team") for s in enriched}
    xm_doc = json.loads((ROOT / "data" / "xm_players.json").read_text(encoding="utf-8"))
    detail = json.loads((ROOT / "data" / "mlb_player_detail.json").read_text(encoding="utf-8"))
    qo_sign = {W: [s for s in storage.load_fa_signings(W).values() if s.get("qo")]
               for W in range(FIRST_XM_WINTER, 2027)}
    return Inputs(fixture=False, Mod=Mod, xm=xm, fr=fr, metrics=metrics, seasons=seasons,
                  swartz=swartz, swartz_census=sw_census, cots_players=players,
                  appear=A.career_appearance_seasons(), people_by_season=_people_index_fn(xm),
                  dest=dest, from_team=from_team, xm_doc=xm_doc,
                  tm=tm_prices(detail), qo_signings=qo_sign,
                  qo_acceptances=fa_cba.qo_acceptances(), qo_value=fa_cba.qo_value,
                  fdl=fdl)


class _FixtureXM:
    """A stand-in engine for the dry run: synthetic prices, one null."""

    def __init__(self):
        self.counts = Counter()

    def price(self, mlbam, W, qo=False, name=None):
        if int(mlbam) % 17 == 0:                     # a row with no xM$
            self.counts["unpriced"] += 1
            return None
        rng = np.random.default_rng(int(mlbam) * 31 + int(W))
        aav = float(np.exp(rng.normal(15.5, 0.9)))
        self.counts["priced"] += 1
        return {"aav": aav, "total": aav * 2.0, "years": 2.0, "side": "hit", "pos": "DH",
                "age": 29}

    def war(self, mlbam, season):
        return float(np.random.default_rng(int(mlbam) + int(season)).normal(1.5, 1.0))

    def engine_check(self, tuples):
        return {"n_compared": 0, "n_not_compared": len(tuples), "max_rel_diff": None,
                "note": "fixture"}


def fixture_inputs() -> Inputs:
    """Synthetic inputs over every test, with nulls: an arbitration row with no
    xM$, a QO winter with no acceptance and a QO row with no xM$, a Cot's
    extension with no per-year note and an executive with no service line,
    the destination lab's own fixture (a member with no price, a club with no
    payroll), and an xM$ row with no Trade Machine price."""
    import arb_model as Mod
    import fa_destination_lab as fdl
    rng = np.random.default_rng(SEED)
    fr = []
    mid = 700000
    for season in range(2022, 2027):
        for i in range(150):
            mid += 1
            step = 1 + i % 3
            war = float(rng.normal(1.5, 1.2))
            prior = None if step == 1 else float(np.exp(rng.normal(15.0, 0.6)))
            sal = (float(np.exp(14.5 + 0.25 * war + rng.normal(0, 0.3))) if step == 1
                   else prior * float(np.exp(0.3 + 0.08 * war + rng.normal(0, 0.15))))
            fr.append({"mlbam": mid, "name": f"Fixture Arb {mid}", "season": season,
                       "arb_year": step, "super_two": bool(i % 11 == 0), "salary": sal,
                       "prior_salary": prior, "league_min": 740000, "war": war,
                       "award_war": war, "war3": war * 2.5, "career_war": war * 4,
                       "age": 27.0, "pa": 400 if i % 2 else 0, "ipouts": 0 if i % 2 else 300,
                       "gs": 0 if i % 2 else 10})
    xm = _FixtureXM()
    qo_sign, acc = {}, []
    mid = 800000
    for W in range(2017, 2023):
        lst = []
        for i in range(10):
            mid += 1
            lst.append({"player_name": f"Fixture QO {W} {i}", "mlbam_id": mid, "qo": True})
        qo_sign[W] = lst
        if W != 2019:                                # 2019 has no acceptance
            acc.append({"class_year": W, "player_name": f"Fixture QO {W} 0"})
    players = []
    for i in range(60):
        S0 = 2018 + i % 8
        sal = ", ".join(f"{(S0 + k) % 100:02d} :${4 + 3 * k}M" for k in range(6))
        notes = [f"signed extension with Fixture 3/1/{(S0) % 100:02d}"]
        if i % 9:
            notes.append(sal)                        # i % 9 == 0: no per-year note
        players.append({"sheet": "fixture", "name": f"Fixture Ext {i}", "pos": "ss",
                        "facts": [f"ML service: {1 + i % 4 + 2026 - S0}.050"],
                        "contracts": [{"label": f"6 years/$40M ({S0}-{(S0 + 5) % 100:02d})",
                                       "years": 6, "total_usd": 40e6, "first_season": S0,
                                       "last_season": S0 + 5, "notes": notes}]})
    players.append({"sheet": "fixture", "name": "Fixture Executive", "pos": "",
                    "facts": ["President, 9/06"],
                    "contracts": [{"label": "5 years (2020-24)", "years": 5, "total_usd": None,
                                   "first_season": 2020, "last_season": 2024,
                                   "notes": ["signed extension with Fixture 9/13/19"]}]})
    ids = {norm_name(p["name"]): 900000 + i for i, p in enumerate(players)}
    appear = {pid: set(range(2015, 2026)) for pid in ids.values()}
    dest = fdl.fixture_inputs()
    from_team = {(Y, rec["player_key"]): rec["from_team"]
                 for (Y, _m), rec in dest.all_signings.items()}
    cols = ["key", "name", "mlbam", "pop", "club", "ctrl", "ctrl_src", "msur_xm", "msur_fair"]
    xrows = {}
    for i in range(30):
        m = 600000 + i
        xrows[str(m)] = [f"fx_{i}", f"Fixture MLB {i}", m, "mlb", "NYY", 3, "salary_path",
                         int(rng.normal(0, 20e6)), int(rng.normal(0, 20e6))]
    tm = {600000 + i: float(rng.normal(0, 20e6)) for i in range(29)}   # 600029: no price
    return Inputs(fixture=True, Mod=Mod, xm=xm, fr=fr, metrics={},
                  seasons=list(range(2022, 2027)), swartz={}, swartz_census={},
                  cots_players=players, appear=appear,
                  people_by_season=lambda s: {k: {v} for k, v in ids.items()},
                  dest=dest, from_team=from_team,
                  xm_doc={"columns": cols, "players": xrows}, tm=tm, qo_signings=qo_sign,
                  qo_acceptances=acc,
                  qo_value=lambda W: {"value_usd": 18_000_000 + 500_000 * (W - 2017)},
                  fdl=fdl)


# ==========================================================================
# the run, in the registered order
# ==========================================================================

def qo_frame(inp: Inputs) -> tuple[list, dict]:
    counts = Counter()
    rows = []
    people = inp.people_by_season
    for W in sorted(inp.qo_signings):
        acc = {norm_name(a["player_name"]) for a in inp.qo_acceptances if a["class_year"] == W}
        seen = {}
        for s in inp.qo_signings[W]:
            nn = norm_name(s.get("player_name"))
            if nn in seen:
                counts["duplicate_name"] += 1
                continue
            seen[nn] = s.get("mlbam_id")
        for nn in sorted(acc - set(seen)):
            ids = set(people(W - 1).get(nn, ()))
            if len(ids) == 1:
                seen[nn] = next(iter(ids))
                counts["acceptance_joined_by_name"] += 1
            else:
                counts["acceptance_unmatched"] += 1
        qv = (inp.qo_value(W) or {}).get("value_usd")
        for nn, mid in sorted(seen.items()):
            if mid is None:
                ids = set(people(W - 1).get(nn, ()))
                mid = next(iter(ids)) if len(ids) == 1 else None
            if mid is None or not qv:
                counts["no_id_or_value"] += 1
                continue
            pr = inp.xm.price(int(mid), W, qo=True, name=nn)
            if pr is None or pr["total"] <= 0:
                counts["no_xm"] += 1
                continue
            rows.append({"mlbam": int(mid), "W": W, "name": nn,
                         "x": math.log(pr["total"] / float(qv)), "y": int(nn in acc),
                         "xm_total": pr["total"], "qo_value": qv})
            counts["kept"] += 1
    return rows, dict(sorted(counts.items()))


def run(inp: Inputs, out_path: Path, generated_at: str, frames_only: bool = False) -> dict:
    """The registered order. ``frames_only`` stops after the engine and the
    frames (counts only, no planted run and no read): the crash check of the
    real inputs before the one read."""
    Mod = inp.Mod
    doc = {"task": "XM_4_DOWNSTREAM_TESTS", "gate_doc": GATE_DOC,
           "generated_at": generated_at, "dry_run": bool(inp.fixture), "seed": SEED,
           "bootstrap": {"B": BOOT_B, "unit": "player (MLBAM id)", "lb": "5th percentile"},
           "xm_model": "fa_market.MarketModel refit as of each winter (Gate 2 fold body)",
           "served_changes": "none"}
    if inp.fixture:
        doc["fixture_note"] = ("synthetic dry run: no number here is a measurement of any "
                               "player, club or winter")
    # (2) the engine and the shared frames
    dest = inp.dest
    tuples = dest.gate2_fn()
    override, join_counts = inp.fdl.join_gate2(tuples, dest.signings, dest.club_states)
    doc["engine"] = {"gate2_tuples": len(tuples),
                     "check_vs_gate2": inp.xm.engine_check(tuples)}
    keys = sorted({(int(r["mlbam"]), int(r["season"])) for r in inp.fr})
    by_k = {(int(r["mlbam"]), int(r["season"])): r for r in inp.fr}
    xm_vals, no_xm = {}, 0
    for k in keys:
        r = by_k[k]
        pr = inp.xm.price(k[0], k[1], name=r.get("name"))
        if pr is None:
            no_xm += 1
        xm_vals[k] = xm_arb_value(pr["aav"] if pr else None,
                                  arb_share(r["arb_year"], r.get("super_two")),
                                  r.get("league_min"))
    doc["A_frame"] = {"rows": len(keys), "rows_no_xm_league_min": no_xm,
                      "seasons": inp.seasons}
    qrows, qcounts = qo_frame(inp)
    doc["B_frame"] = {"rows": len(qrows), "accepted": sum(r["y"] for r in qrows),
                      "by_winter": {str(W): {"n": sum(1 for r in qrows if r["W"] == W),
                                             "accepted": sum(r["y"] for r in qrows if r["W"] == W)}
                                    for W in sorted({r["W"] for r in qrows})},
                      "counts": qcounts}
    erows, ecounts = ext_frame(inp.xm, inp.cots_players, inp.people_by_season, inp.appear)
    doc["C_frame"] = {"rows": len(erows), "counts": ecounts,
                      "in_season_signings": sum(1 for r in erows if r["in_season"]),
                      "spread_no_per_year_note": sum(1 for r in erows if r["spread"]),
                      "by_S0": dict(sorted(Counter(str(r["S0"]) for r in erows).items())),
                      "by_ctrl": dict(sorted(Counter(str(r["ctrl"]) for r in erows).items())),
                      "attribution": "Cot's Contracts (Baseball Prospectus)"}
    signings = {k: dict(v) for k, v in dest.signings.items()}
    for k, (g, a) in override.items():
        signings[k]["_price_guarantee_usd"] = g
        signings[k]["_price_aav_usd"] = a
    frame = inp.fdl.build_frame(dest.primary_rows_fn(override), signings, dest.club_states,
                                "gate2_predicted")
    dem = attach_demand(frame, tuples, inp.from_team, dest.club_states)
    doc["D_frame"] = {"signings": len(frame["members"]), "scored_winters": frame["scored_winters"],
                      "gate2_join": join_counts["total"], "demand": dem}
    doc["xm_engine_counts"] = dict(sorted(inp.xm.counts.items()))
    persist(doc, out_path, "engine_and_frames")
    if frames_only:
        return doc
    # (2b) the arbitration reproduction check, before any score
    doc["A_reproduction"] = arb_repro(Mod, inp.fr, inp.metrics, inp.seasons)
    persist(doc, out_path, "A_reproduction")
    # (3) planted recovery for A to D
    pa, perm_vals = arb_test(Mod, inp.fr, inp.metrics, inp.seasons, xm_vals)
    pb = qo_test(qrows)
    pc = ext_test(erows)
    pd = dest_test(frame)
    doc["planted"] = {"A": pa, "B": pb, "C": pc, "D": pd}
    persist(doc, out_path, "planted")
    # (4) the real reads, once each
    a_ok = bool(pa["planted_ok"] and (doc["A_reproduction"] or {}).get("pass"))
    ra = arb_score(Mod, inp.fr, inp.metrics, inp.seasons, xm_vals, perm_vals,
                   swartz=inp.swartz)
    doc["A"] = {**ra, "verdict": verdict(a_ok, ra["pass"]),
                "void_reason": (None if a_ok else ("reproduction failed"
                                                   if not (doc["A_reproduction"] or {}).get("pass")
                                                   else "planted recovery failed"))}
    persist(doc, out_path, "A")
    rb = qo_score(qrows)
    doc["B"] = {**rb, "lowo_context": qo_lowo(qrows), "verdict": verdict(pb["planted_ok"], rb["pass"]),
                "void_reason": pb.get("void_reason")}
    persist(doc, out_path, "B")
    rc = ext_score(erows)
    rc_sens = ext_score([r for r in erows if not r["in_season"]])
    doc["C"] = {**rc, "sensitivity_no_in_season": {k: rc_sens[k] for k in
                                                   ("n_scored", "mae_log", "war_minus_xm", "pass")},
                "verdict": verdict(pc["planted_ok"], rc["pass"]),
                "void_reason": None if pc["planted_ok"] else "planted recovery failed",
                "rows": [{k: r[k] for k in ("player", "mlbam", "S0", "last", "sign_date", "svc0",
                                            "F", "ctrl", "n_bought", "bought_aav", "xm_aav",
                                            "in_season", "spread")} for r in erows]}
    persist(doc, out_path, "C")
    rd = dest_score(frame)
    doc["D"] = {**rd, "verdict": verdict(pd["planted_ok"], rd["pass"]),
                "void_reason": None if pd["planted_ok"] else "planted recovery failed"}
    persist(doc, out_path, "D")
    # (5) E, descriptive
    doc["E"] = sign_check(inp.xm_doc, inp.tm)
    doc["xm_engine_counts"] = dict(sorted(inp.xm.counts.items()))
    persist(doc, out_path, "E")
    return doc


def _owner_question(task_dir: Path, exc: BaseException) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "OWNER_QUESTION.md").write_text(
        "# XM_4_DOWNSTREAM_TESTS: the read stopped\n\n"
        "The one-time read raised an exception after scoring began and was not rerun "
        "(registration section 8).\n\n```\n" + "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)) + "```\n",
        encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--read", action="store_true")
    g.add_argument("--frames-only", action="store_true")
    ap.add_argument("--task-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--generated-at", default=None)
    a = ap.parse_args(argv)
    gen = a.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if a.dry_run:
        out = Path(a.out) if a.out else DRY_RUN_DIR / "xm_downstream_eval.json"
        doc = run(fixture_inputs(), out, gen)
        print(json.dumps({"dry_run": True, "out": str(out), "order": doc["order"],
                          "verdicts": {t: doc[t]["verdict"] for t in "ABCD"}}, indent=1))
        return 0
    import scrapers
    task_dir = Path(a.task_dir) if a.task_dir else ROOT / ".cache" / "xm_downstream"
    out = Path(a.out) if a.out else OUT_PATH
    if a.frames_only:
        out = Path(a.out) if a.out else task_dir / "frames_only.json"
        with scrapers.cache_only():
            doc = run(real_inputs(), out, gen, frames_only=True)
        print(json.dumps({"frames_only": True, "out": str(out), "order": doc["order"]},
                         indent=1))
        return 0
    with scrapers.cache_only():
        inp = real_inputs()
        try:
            doc = run(inp, out, gen)
        except BaseException as exc:                 # noqa: BLE001
            _owner_question(task_dir, exc)
            raise
    print(json.dumps({"out": str(out), "order": doc["order"],
                      "verdicts": {t: doc[t]["verdict"] for t in "ABCD"},
                      "E_opposite_sign": doc["E"]["n_opposite_sign"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
