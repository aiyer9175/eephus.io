# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HEALTH PROFILE as an outcome-grounded eFV driver (owner ask, 2026-09-04).

> "build a predictive machine-learning based driver submodel which will build a player's
> health profile based on their IL history, stints, and injury specifications and weight
> this to boost (durability) or drop (fragility) a prospect's eFV grade. This will replace
> our current system of just penalizing players for being currently on IL ... built by
> testing injury thresholds against bust probability / MLB health outcomes. Ex. what
> correlation is there between Tommy John and a pitcher's MLB production? What correlation
> is there between players who spent a cumulative number of X days on the Injured List
> during their time as a prospect and their eventual outcomes?"

READ THE COVERAGE SECTION FIRST. The idea is sound and the arithmetic below is real, but
the archive does not reach the cohort the label needs, and no amount of modelling fixes
that. Measured before anything was fitted:

  * `il_history` is NOT a history. 1,415 of its 1,662 placements are 2026 and it was first
    populated 2026-06-06, so it is a forward-collected table.
  * `player_transactions` IS the historical source: 27,255 IL events on 4,887 players,
    with both placements and activations, so cumulative DAYS are computable. It starts in
    2019.
  * Consequently PRE-DECISION IL coverage is exactly 0 percent for debut years 2016-2018,
    18-20 percent for 2019, and 39-79 percent for 2020-2024. Overall 33.8 percent of
    debuted rows on both sides.

That last line is the whole constraint. A health feature built naively would read "no IL
history" for every pre-2019 row, and since those are the cohorts with the most fully
resolved labels, the feature would encode DEBUT ERA and be scored as though it encoded
health. So this lab never scores the full pool. It carries an explicit `il_observable`
flag, restricts the gated arm to rows whose pre-decision window the archive actually
covers, and reports the descriptive tables on that cohort only.

WHAT IS MEASURED
  Part 1  descriptive: IL burden buckets (stints, cumulative days, 60-day and full-season
          placements, longest single stint) against mean first-6yr WAR, star rate and bust
          rate, on the observable cohort.
  Part 2  the Tommy John question, asked as the owner asked it: pitchers carrying a
          UCL or Tommy John event before the decision date, against those who do not.
  Part 3  injury CATEGORY effects from the description text (elbow, shoulder, back,
          hamstring, oblique, knee, wrist, forearm, lat, hip).
  Part 4  gated: each candidate added to the shipped feature set and scored as an
          incremental forward-chained margin, E_cond floor, permutation null, Holm across
          the family. Reported with its fold count, which is small by construction.

NOTHING HERE REPLACES THE IL PENALTY YET. Replacing it is a serving-path change and the
serving path has a different data situation from the training path: current IL status is
densely covered for today's board, while the TRAINING cohort is not. The two must not be
conflated, and this lab measures only the training side.

Run:
    python tools/efv_health_profile_lab.py
    python tools/efv_health_profile_lab.py --describe-only
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_model as E                       # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_health_profile_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")

STAR_WAR = 10.0
BUST_WAR = 0.5

#: the archive's first usable year; before this a row has no observable IL window
ARCHIVE_FIRST_YEAR = 2019

IL_RE = re.compile(r"injured list|disabled list", re.I)
PLACE_RE = re.compile(r"\bplaced\b|\btransferred\b", re.I)
ACT_RE = re.compile(r"activated|reinstated|returned", re.I)
TYPE_RE = re.compile(r"on the ([\w-]+?)[- ]?day injured list|on the (full-season) injured list", re.I)
TJ_RE = re.compile(r"tommy john|ucl", re.I)
CATEGORIES = ("elbow", "shoulder", "back", "hamstring", "oblique", "knee",
              "wrist", "forearm", "lat", "hip")


def _d(s: str):
    try:
        y, m, dd = str(s)[:10].split("-")
        return date(int(y), int(m), int(dd))
    except Exception:
        return None


def il_events() -> dict[str, list[dict]]:
    """{player_key: [{date, kind, il_type, text}]} from player_transactions, sorted."""
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for pk, payload in con.execute("select player_key, payload_json from player_transactions"):
        try:
            rows = json.loads(payload)
        except Exception:
            continue
        for t in rows:
            txt = t.get("description") or ""
            if not IL_RE.search(txt):
                continue
            dt = _d(t.get("date"))
            if dt is None:
                continue
            if PLACE_RE.search(txt):
                kind = "place"
            elif ACT_RE.search(txt):
                kind = "activate"
            else:
                continue
            m = TYPE_RE.search(txt)
            il_type = (m.group(1) or m.group(2)) if m else None
            out[pk].append({"date": dt, "kind": kind, "il_type": il_type, "text": txt})
    for pk in out:
        out[pk].sort(key=lambda e: e["date"])
    con.close()
    return dict(out)


def profile(events: list[dict], cutoff, first_seen=None) -> dict:
    """The health profile as of the decision date. Days pair a placement with the next
    activation; a stint still open at the cutoff is censored AT the cutoff, never beyond,
    so the number can never see past the decision."""
    p = {"il_stints": 0.0, "il_days": 0.0, "il_60day": 0.0, "il_fullseason": 0.0,
         "il_max_stint_days": 0.0, "tj": 0.0}
    for c in CATEGORIES:
        p[f"cat_{c}"] = 0.0
    open_at = None
    for e in events:
        if e["date"] >= cutoff:
            break
        if e["kind"] == "place":
            if open_at is None:
                open_at = e["date"]
            p["il_stints"] += 1
            t = (e["il_type"] or "").lower()
            if t.startswith("60"):
                p["il_60day"] += 1
            if t.startswith("full"):
                p["il_fullseason"] += 1
            if TJ_RE.search(e["text"]):
                p["tj"] = 1.0
            for c in CATEGORIES:
                if re.search(rf"\b{c}", e["text"], re.I):
                    p[f"cat_{c}"] = 1.0
        elif e["kind"] == "activate" and open_at is not None:
            days = (e["date"] - open_at).days
            if days >= 0:
                p["il_days"] += days
                p["il_max_stint_days"] = max(p["il_max_stint_days"], days)
            open_at = None
    if open_at is not None:                      # still on the IL at the decision date
        days = (cutoff - open_at).days
        if days > 0:
            p["il_days"] += days
            p["il_max_stint_days"] = max(p["il_max_stint_days"], days)
        p["il_open_at_decision"] = 1.0
    else:
        p["il_open_at_decision"] = 0.0
    # OBSERVABILITY IS A PROPERTY OF THE ARCHIVE, NOT OF THE PLAYER. Keying this off
    # "did this player have an IL event" would keep only injured players and drop every
    # healthy one, which destroys the contrast the whole lab exists to measure and would
    # have made `durable_zero_il` unmeasurable by construction. The archive starts in
    # 2019, so a decision taken in 2020 or later has at least one full prior year of
    # coverage behind it and the ABSENCE of a stint is then real evidence of health.
    p["il_observable"] = 1.0 if cutoff.year >= ARCHIVE_FIRST_YEAR + 1 else 0.0
    return p


def build_pool(side: str, ev: dict) -> dict:
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, _m = E._feature_spec(side)
    by_key = {r["player_key"]: r for r in raw}
    profs = []
    for r in prep:
        src = by_key.get(r.get("player_key")) or {}
        cut = _d(src.get("cutoff")) or date(int(r["decision_year"]), 7, 1)
        e = ev.get(r.get("player_key")) or []
        first = e[0]["date"] if e else None
        profs.append(profile(e, cut, first))
    return {
        "side": side, "keys": list(keys),
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "profs": profs, "n": len(prep), "lam": E.blend_lambda(side),
    }


def observable_mask(P: dict) -> np.ndarray:
    return np.array([p["il_observable"] > 0 for p in P["profs"]], dtype=bool)


def candidates(side: str) -> list[dict]:
    C = []

    def add(name, fn, why):
        C.append({"name": name, "fn": fn, "why": why})

    add("il_stints", lambda p: p["il_stints"], "count of IL placements before the decision")
    add("il_days", lambda p: p["il_days"], "cumulative IL days before the decision")
    add("il_max_stint_days", lambda p: p["il_max_stint_days"], "longest single stint")
    add("il_60day", lambda p: p["il_60day"], "count of 60-day placements")
    add("il_fullseason", lambda p: p["il_fullseason"], "count of full-season placements")
    add("il_open_at_decision", lambda p: p["il_open_at_decision"],
        "on the IL at the decision date: the INCUMBENT signal, included so the new "
        "features are measured against it rather than beside it")
    for t in (30, 60, 90, 120, 180):
        add(f"il_days_ge_{t}", (lambda p, t=t: 1.0 if p["il_days"] >= t else 0.0),
            f"{t}+ cumulative IL days as a prospect")
    for t in (2, 3, 4):
        add(f"il_stints_ge_{t}", (lambda p, t=t: 1.0 if p["il_stints"] >= t else 0.0),
            f"{t}+ separate IL stints as a prospect")
    add("durable_zero_il", lambda p: 1.0 if p["il_stints"] == 0 else 0.0,
        "NO IL placement in an observable window: the durability side of the ask")
    if side == "pit":
        add("tommy_john", lambda p: p["tj"], "a Tommy John or UCL event before the decision")
    for c in CATEGORIES:
        add(f"cat_{c}", (lambda p, c=c: p[f"cat_{c}"]), f"an IL event naming the {c}")
    return C


def describe(P: dict, cands: list[dict], mask: np.ndarray) -> dict:
    y, prof = P["y"][mask], [p for p, m in zip(P["profs"], mask) if m]
    pool_star = float((y >= STAR_WAR).mean()) if len(y) else 0.0
    rows = []
    for c in cands:
        v = np.array([c["fn"](p) for p in prof], dtype=float)
        binary = set(np.unique(v)) <= {0.0, 1.0}
        if binary:
            m = v > 0.5
            n_in = int(m.sum())
            if n_in < 10 or n_in == len(v):
                rows.append({"name": c["name"], "why": c["why"], "support": n_in,
                             "note": "too thin to read" if n_in < 10 else "no contrast"})
                continue
            yi, yo = y[m], y[~m]
            rows.append({
                "name": c["name"], "why": c["why"], "support": n_in,
                "support_share": round(n_in / len(y), 4),
                "mean_label_in": round(float(yi.mean()), 3),
                "mean_label_out": round(float(yo.mean()), 3),
                "star_rate_in": round(float((yi >= STAR_WAR).mean()), 4),
                "star_rate_out": round(float((yo >= STAR_WAR).mean()), 4),
                "bust_rate_in": round(float((yi <= BUST_WAR).mean()), 4),
                "bust_rate_out": round(float((yo <= BUST_WAR).mean()), 4),
                "star_lift_vs_pool": (round(float((yi >= STAR_WAR).mean()) / pool_star, 3)
                                      if pool_star > 0 else None),
            })
        else:
            rows.append({"name": c["name"], "why": c["why"], "support": int((v > 0).sum()),
                         "spearman_with_label": round(float(M.wrho(v, y, P["w"][mask])), 5),
                         "mean": round(float(v.mean()), 2),
                         "p90": round(float(np.percentile(v, 90)), 2)})
    return {"n": int(mask.sum()), "pool_star_rate": round(pool_star, 4), "rows": rows}


def chain(P, extra=None, sel=None, years=None, mask=None):
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = P["lam"]
    X = P["X"] if extra is None else np.column_stack([P["X"], extra])
    y, w, fv, dy = P["y"], P["w"], P["fv"], P["dy"]
    if mask is not None:
        X, y, w, fv, dy = X[mask], y[mask], w[mask], fv[mask], dy[mask]
    if sel is None:
        sel = np.arange(len(y))
    X, y, w, fv, dy = X[sel], y[sel], w[sel], fv[sel], dy[sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], y[tr])
        rg = M.ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr)); C.append(cons)
        B.append((1 - lam) * cons + lam * mod); T.append(y[te]); W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def margin(parts, sel=None):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    if sel is not None:
        cons, blend, tgt, w = cons[sel], blend[sel], tgt[sel], w[sel]
    return float(M.wrho(blend, tgt, w)) - float(M.wrho(cons, tgt, w))


def holm(p):
    items = sorted(p.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        run = max(run, min(1.0, (m - i) * v))
        out[k] = round(run, 5)
    return out


def gate(P, cands, mask, b_cond, b_perm):
    rng = np.random.default_rng(SEED)
    base_parts = chain(P, mask=mask)
    if base_parts is None:
        return {"skipped": "no fold survived on the observable cohort"}
    base = margin(base_parts)
    n_te = len(base_parts[3])
    prof = [p for p, m in zip(P["profs"], mask) if m]
    res, pv = [], {}
    for i, c in enumerate(cands):
        v = np.array([c["fn"](p) for p in prof], dtype=float)
        if np.allclose(v, v[0]):
            res.append({"name": c["name"], "skipped": "constant on this cohort"})
            continue
        sd = v.std()
        vz = ((v - v.mean()) / sd if sd > 0 else v)
        full = np.zeros(P["n"]); full[np.flatnonzero(mask)] = vz
        parts = chain(P, extra=full.reshape(-1, 1), mask=mask)
        m_ = margin(parts)
        if m_ is None:
            res.append({"name": c["name"], "skipped": "no fold survived"})
            continue
        delta = m_ - base
        cond = []
        for _ in range(b_cond):
            s = rng.integers(0, n_te, n_te)
            a_, b_ = margin(parts, s), margin(base_parts, s)
            if a_ is not None and b_ is not None:
                cond.append(a_ - b_)
        cond = np.array([x for x in cond if np.isfinite(x)], dtype=float)
        null = []
        for j in range(b_perm):
            r2 = np.random.default_rng(SEED + 31337 * (i + 1) + j)
            pv2 = vz[r2.permutation(len(vz))]
            f2 = np.zeros(P["n"]); f2[np.flatnonzero(mask)] = pv2
            mm = margin(chain(P, extra=f2.reshape(-1, 1), mask=mask))
            if mm is not None:
                null.append(mm - base)
        null = np.array(null, dtype=float)
        p = float((np.abs(null) >= abs(delta)).mean()) if len(null) else 1.0
        pv[c["name"]] = p
        floor = 1.96 * float(cond.std(ddof=1)) if len(cond) > 1 else None
        res.append({
            "name": c["name"], "why": c["why"],
            "margin_base": round(base, 5), "margin_with": round(m_, 5),
            "delta": round(delta, 5),
            "E_cond_floor_mde95": round(floor, 5) if floor else None,
            "clears_own_floor": bool(floor and abs(delta) >= floor),
            "permutation_p": round(p, 4), "permutation_B": int(len(null)),
        })
    adj = holm(pv)
    for r in res:
        if r.get("name") in adj:
            r["holm_p"] = adj[r["name"]]
            r["SHIPPABLE"] = bool(r.get("clears_own_floor") and adj[r["name"]] < 0.05
                                  and r.get("delta", 0) > 0)
    return {"baseline_margin": round(base, 5), "n_scored_rows": int(n_te),
            "family_size": len(pv), "results": res}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", choices=["hit", "pit", "both"], default="both")
    ap.add_argument("--describe-only", action="store_true")
    ap.add_argument("--b-cond", type=int, default=1000)
    ap.add_argument("--b-perm", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    ev = il_events()
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_health_profile_lab.py",
        "asked_by": "owner, 2026-09-04: an outcome-grounded health profile driver",
        "label_basis": "eWAR v2 (the 2026-09-04 label epoch)",
        "source": ("player_transactions, which carries 27,255 IL events on 4,887 players "
                   "with placements AND activations so cumulative days are computable. "
                   "il_history is NOT usable as history: 1,415 of its 1,662 placements are "
                   "2026 and it was first populated 2026-06-06."),
        "coverage_constraint": (
            "the IL archive starts in 2019, so pre-decision coverage is 0 percent for debut "
            "years 2016-2018, about 19 percent for 2019 and 39 to 79 percent for 2020-2024. "
            "A feature built on the full pool would encode DEBUT ERA rather than health, so "
            "every gated arm here runs on the observable cohort only."),
        "archive_first_year": ARCHIVE_FIRST_YEAR,
        "players_with_any_il_event": len(ev),
        "sides": {},
    }
    for side in (SIDES if a.side == "both" else (a.side,)):
        t0 = time.time()
        P = build_pool(side, ev)
        mask = observable_mask(P)
        cands = candidates(side)
        print(f"=== {side}: {P['n']} rows, observable cohort {int(mask.sum())} "
              f"({mask.mean():.1%}), {len(cands)} candidates ({time.time()-t0:.0f}s)",
              flush=True)
        blk = {"n_rows": P["n"], "observable_rows": int(mask.sum()),
               "observable_share": round(float(mask.mean()), 4),
               "descriptive": describe(P, cands, mask)}
        if not a.describe_only:
            blk["gated"] = gate(P, cands, mask, a.b_cond, a.b_perm)
        out["sides"][side] = blk
    if not a.no_write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
