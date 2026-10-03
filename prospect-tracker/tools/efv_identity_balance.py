# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-03 receipts for the outcome-blind identity resolver (bug B4,
docs/efv-v2/DRIVER_SYSTEM_V2.md s2 and s5). One development read, two parts:

1. LABEL BALANCE. On the list-vintage frame F-LV, development vintages 2011 to 2019 only,
   the W3 > 0 share (and the R3 share) of the rows that carry each missingness indicator
   against the rows that do not, by side, plus the indicator's partial coefficient in a
   linear probability model of W3 > 0 on the within-(side, vintage) consensus percentile
   (a quadratic) and vintage effects, with a player-clustered bootstrap CI95. An indicator
   is BALANCED when that CI95 covers zero. Only a balanced indicator may enter the
   REACHED/timing head (efv_v2_model.timing_keys); the rest are reported and kept out.

2. THE I2 H1 REGRESSION. Lane I2 found that a resolver reading the debut year made an
   age plus level model "beat" consensus by +0.0304 (CI95 +0.0125 to +0.0496) through the
   missing-level indicator alone. This tool rebuilds that leaky resolver as a named
   COUNTERFACTUAL (it lives here, never in efv_identity) and scores the same age plus
   level model under it and under efv_identity, with I2's estimator (per-side ridge on the
   within-(V, side) W3 percentile, a cubic in the consensus percentile plus each
   standardized input times (1, percentile - 0.5) plus its missing indicator,
   player-grouped 5-fold, rho within fold n-averaged, paired player-clustered bootstrap).
   The fake gain must appear under the counterfactual and vanish under efv_identity;
   test_efv_identity.py holds the artifact to that.

3. THE TIEBREAK ROUTES (EFV3 lane A, G5). The rows the SIDE and the RECENCY tiebreaks
   resolved (id_how name_side and name_recency) are read exactly like an indicator:
   the W3 > 0 share of those rows against the rest, by side, with the same partial
   coefficient and CI95. Two validity probes (DS-03:tiebreak.name_side and
   DS-03:tiebreak.name_recency), never timing-head inputs.

WHAT THIS IS NOT. It scores no eFV and no candidate, so no scored row reaches
data/efv_progress.json (whose chart is eFV minus consensus); `python
tools/efv_identity_balance.py ledger` appends one development row there (model_id
efv_identity_v2, resolvable none, no score) that records the resolver's coverage by
route beside the reads. Its reads are counted in the program's probe ledger through
data/xfv_arm_ledger.json (tools/efv_arm_ledger.py). The "text" block another tool
writes into the receipt (tools/efv_text_balance.py) is carried over unchanged.
Role: development. It adjudicates nothing.

NEVER READ: list vintages 2020 and 2021 (R-LV) and every player whose effective debut
year is 2025 or later (R-VM cohorts; dropped before any statistic, count reported).
Nothing is grouped or summarised by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md):
consensus enters only as a continuous within-(side, vintage) percentile.

Run:  python tools/efv_identity_balance.py [--dry-run]     (the receipt)
      python tools/efv_identity_balance.py ledger          (the development row)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_identity as ID  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import milb_history as mh  # noqa: E402
import source_backtest as SB  # noqa: E402

OUT = ROOT / "data" / "efv_identity_balance.json"
SEED = 20260925
B_H1 = 1000
B_BAL = 500
FOLDS = 5
RIDGE = 1.0
RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
#: The counterfactual's index reaches V + 3 for its "no major league line by V + 3" rule.
LEAKY_INDEX_SEASONS = range(2006, max(F.DEV_VINTAGES) + 4)

INDICATORS = (
    ("id_unresolved", "no outcome-blind id (efv_identity)"),
    ("milb_absent", "no MiLB block on the outcome-blind id (the V2 absence flag)"),
    ("level_prev_missing", "no minor league line in V - 1 on the outcome-blind id"),
    ("age_prev_missing", "no minor league age in V - 1 on the outcome-blind id"),
    ("acq_unknown_at_v", "acquisition record not known before V"),
    ("record_id_missing", "the record's own stored id is absent (the leak B4 names)"),
    ("record_birth_missing", "the record's stored birth date is absent"),
    ("leaky_level_missing", "no V - 1 level under the leaky counterfactual resolver"),
)
#: The tiebreak routes (efv_identity SIDE and RECENCY), read like an indicator and
#: reported as validity probes; they never enter timing_head_admissible.
TIEBREAK_ROUTES = (
    ("route_name_side", ID.HOW_SIDE, "resolved by the SIDE tiebreak (name_side)"),
    ("route_name_recency", ID.HOW_RECENCY,
     "resolved by the RECENCY tiebreak (name_recency)"),
)
#: Keys of the receipt written by other tools and carried over unchanged.
SIDECAR_KEYS = ("text",)
MODEL_ID = "efv_identity_v2"
LEDGER_FRAME = "lv_dev"


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    bad = sorted(set(F.DEV_VINTAGES) & set(F.RESERVED_LV))
    if bad:
        raise F.ReservedFrameError(f"DEV_VINTAGES overlaps RESERVED_LV: {bad}")
    if max(F.DEV_VINTAGES) >= min(F.RESERVED_LV):
        raise F.ReservedFrameError("a development vintage reaches the reserved range")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "vintages_read": list(F.DEV_VINTAGES), "reserved_vm_pins": pins}


# ---------------------------------------------------------------------------
# the counterfactual (leaky) resolver, I2's first attempt: NOT for use anywhere else
# ---------------------------------------------------------------------------

def _leaky_index() -> dict[str, dict[int, dict]]:
    idx: dict[str, dict[int, dict]] = {}
    for season in LEAKY_INDEX_SEASONS:
        for g in ("hitting", "pitching"):
            for m, rows in mh.player_index(season, g, fetch=False).items():
                for x in rows:
                    info = idx.setdefault(ID.norm_name(x.get("name")), {}).setdefault(
                        int(m), {"first": season, "mlb_first": None})
                    info["first"] = min(info["first"], season)
                    if x.get("level") == "MLB":
                        mf = info["mlb_first"]
                        info["mlb_first"] = season if mf is None else min(mf, season)
    return idx


def _leaky_resolve(rec: dict, V: int, idx: dict) -> int | None:
    """Record id first; else name candidates in pro ball by V, disambiguated by the
    published debut year, or, with no debut, by having no major league line by V + 3.
    Both disambiguators read the outcome: this is the defect DS-03 removes."""
    if rec.get("mlbam_id"):
        try:
            return int(rec["mlbam_id"])
        except (TypeError, ValueError):
            pass
    cands = {m: i for m, i in (idx.get(ID.norm_name(rec.get("player_name"))) or {}).items()
             if i["first"] <= V}
    dd = str(rec.get("debut_date") or "")
    if dd[:4].isdigit():
        pick = [m for m, i in cands.items() if i["mlb_first"] == int(dd[:4])]
    else:
        pick = [m for m, i in cands.items()
                if i["mlb_first"] is None or i["mlb_first"] > V + 3]
    return pick[0] if len(pick) == 1 else None


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def _prev(pid: int | None, V: int) -> tuple[float, float]:
    """(highest minor league level rank, age) in season V - 1 for an id, NaN if none."""
    if not pid:
        return float("nan"), float("nan")
    rows = []
    for g in ("hitting", "pitching"):
        rows += [r for r in (mh.player_index(V - 1, g, fetch=False).get(int(pid)) or [])
                 if r.get("level") in RANK]
    if not rows:
        return float("nan"), float("nan")
    lv = max(RANK[r["level"]] for r in rows)
    ages = [r.get("age") for r in rows if isinstance(r.get("age"), (int, float))]
    return float(lv), (float(max(ages)) if ages else float("nan"))


def _age_at(bd: str | None, V: int) -> float:
    try:
        return (date(V, 7, 1) - date.fromisoformat(str(bd)[:10])).days / 365.25
    except (TypeError, ValueError):
        return float("nan")


def build_rows(milb_floor: int | None = None) -> tuple[list[dict], dict]:
    """`milb_floor` is handed to efv_vintage_frame.build_frame unchanged: None builds
    the frame as the program reads it; tools/efv_milb_floor_coverage.py passes a floor
    to re-run the balance on a candidate frame (EFV3_B3) without touching this receipt."""
    universe = F.load_universe()
    war = L.war_seasons_table()
    leaky = _leaky_index()
    rows, receipt = [], {"frame_rows": 0, "no_consensus": 0, "label_none": 0,
                         "dropped_rvm_players": 0, "by_how": {},
                         "by_how_and_side": {s: {} for s in F.SIDES}}
    rvm_keys = set()
    for V in F.DEV_VINTAGES:
        F.guard_score_request(V, purpose="identity balance")
        for side in F.SIDES:
            frame = F.build_frame(side, V, universe=universe, milb_floor=milb_floor)
            receipt["frame_rows"] += len(frame)
            labs = L.labels_for_frame(frame, universe=universe, war=war)
            for r, lab in zip(frame, labs):
                if lab.get("debut_year") is not None and \
                        int(lab["debut_year"]) >= F.R_VM_FIRST_DEBUT_YEAR:
                    rvm_keys.add(r["player_key"])
                    continue
                c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
                if c is None:
                    receipt["no_consensus"] += 1
                    continue
                if lab.get("w3") is None:
                    receipt["label_none"] += 1
                    continue
                rec = universe[r["player_key"]]
                receipt["by_how"][r["id_how"]] = receipt["by_how"].get(r["id_how"], 0) + 1
                bhs = receipt["by_how_and_side"][side]
                bhs[r["id_how"]] = bhs.get(r["id_how"], 0) + 1
                lk = _leaky_resolve(rec, V, leaky)
                lv_b, ag_b = _prev(r["mlbam_id"], V)
                lv_l, ag_l = _prev(lk, V)
                a_rec = _age_at(rec.get("birth_date"), V)
                rows.append({
                    "pk": r["player_key"], "V": V, "side": side, "fv": float(c),
                    "w3": float(lab["w3"]), "r3": lab.get("r3"), "route": r["id_how"],
                    "lvl_blind": lv_b, "lvl_leaky": lv_l,
                    "age_blind": a_rec if a_rec == a_rec else ag_b + 1.0,
                    "age_leaky": a_rec if a_rec == a_rec else ag_l + 1.0,
                    "id_unresolved": float(r["mlbam_id"] is None),
                    "milb_absent": float(not r.get("milb")),
                    "level_prev_missing": float(lv_b != lv_b),
                    "age_prev_missing": float(ag_b != ag_b),
                    "acq_unknown_at_v": float(not r.get("acq_known_at_v")),
                    "record_id_missing": float(not rec.get("mlbam_id")),
                    "record_birth_missing": float(not rec.get("birth_date")),
                    "leaky_level_missing": float(lv_l != lv_l),
                })
    receipt["dropped_rvm_players"] = len(rvm_keys)
    receipt["rows_scored"] = len(rows)
    receipt["rows_scored_by_side"] = {s: sum(1 for r in rows if r["side"] == s)
                                      for s in F.SIDES}
    return rows, receipt


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def _within(values, groups) -> np.ndarray:
    v = np.asarray(values, dtype=float)
    out = np.zeros(v.size)
    for g in set(groups):
        ix = np.array([i for i, x in enumerate(groups) if x == g])
        out[ix] = rankdata(v[ix]) / ix.size
    return out


def _clusters(pks: list[str]) -> list[np.ndarray]:
    by: dict[str, list[int]] = {}
    for i, p in enumerate(pks):
        by.setdefault(p, []).append(i)
    return [np.array(v) for _, v in sorted(by.items())]


def balance(rows: list[dict], rng: np.random.Generator, indicators=INDICATORS) -> dict:
    out: dict = {}
    for side in F.SIDES:
        d = [r for r in rows if r["side"] == side]
        u = _within([r["fv"] for r in d], [r["V"] for r in d])
        ypos = np.array([float(r["w3"] > 0) for r in d])
        r3 = np.array([np.nan if r["r3"] is None else float(r["r3"]) for r in d])
        vs = sorted({r["V"] for r in d})
        dummies = np.column_stack([[float(r["V"] == v) for r in d] for v in vs[1:]]) \
            if len(vs) > 1 else np.zeros((len(d), 0))
        cl = _clusters([r["pk"] for r in d])
        side_out = {}
        for name, _desc in indicators:
            x = np.array([r[name] for r in d])
            n1 = int(x.sum())
            blk = {"n": len(d), "n_with": n1, "n_without": len(d) - n1}
            if n1 == 0 or n1 == len(d):
                blk.update({"verdict": "CONSTANT", "partial": None, "ci95": None})
                side_out[name] = blk
                continue
            m1, m0 = x == 1, x == 0
            blk["w3_pos_share_with"] = round(float(ypos[m1].mean()), 4)
            blk["w3_pos_share_without"] = round(float(ypos[m0].mean()), 4)
            blk["w3_pos_gap"] = round(float(ypos[m1].mean() - ypos[m0].mean()), 4)
            ok = ~np.isnan(r3)
            if (ok & m1).any() and (ok & m0).any():
                blk["r3_share_with"] = round(float(r3[ok & m1].mean()), 4)
                blk["r3_share_without"] = round(float(r3[ok & m0].mean()), 4)
            X = np.column_stack([np.ones(len(d)), u, u ** 2, dummies, x])

            def coef(ix):
                b, *_ = np.linalg.lstsq(X[ix], ypos[ix], rcond=None)
                return float(b[-1])
            point = coef(np.arange(len(d)))
            draws = []
            for _ in range(B_BAL):
                pick = rng.integers(0, len(cl), len(cl))
                ix = np.concatenate([cl[j] for j in pick])
                if x[ix].min() == x[ix].max():
                    continue
                draws.append(coef(ix))
            lo, hi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
            blk.update({"partial": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)],
                        "B_used": len(draws),
                        "verdict": "BALANCED" if lo <= 0 <= hi else "IMBALANCED"})
            side_out[name] = blk
        out[side] = side_out
    return out


def tiebreak_balance(rows: list[dict], rng: np.random.Generator) -> dict:
    """Part 3: each tiebreak route read as an indicator (the rows it resolved against
    the rest), by side, plus the probe verdict: BALANCED when every side with rows on
    the route has a CI95 covering zero, CONSTANT when no side has such rows."""
    flagged = [dict(r, **{name: float(r["route"] == how) for name, how, _ in TIEBREAK_ROUTES})
               for r in rows]
    by_side = balance(flagged, rng, [(n, d) for n, _h, d in TIEBREAK_ROUTES])
    probes = {}
    for name, how, desc in TIEBREAK_ROUTES:
        sides = {s: by_side[s][name] for s in F.SIDES}
        read = {s: v for s, v in sides.items() if v["verdict"] != "CONSTANT"}
        verdict = ("CONSTANT" if not read else
                   "BALANCED" if all(v["verdict"] == "BALANCED" for v in read.values())
                   else "IMBALANCED")
        probes[f"DS-03:tiebreak.{how}"] = {
            "tag": f"DS-03:tiebreak.{how}", "verdict": verdict, "indicator": desc,
            "rows_resolved": {s: sides[s]["n_with"] for s in F.SIDES},
            "partial": {s: sides[s].get("partial") for s in F.SIDES},
            "ci95": {s: sides[s].get("ci95") for s in F.SIDES}}
    return {"indicators": {n: d for n, _h, d in TIEBREAK_ROUTES}, "by_side": by_side,
            "probes": probes}


def _design(d: list[dict], feats: list[str], q: np.ndarray) -> np.ndarray:
    cols = [q, q ** 2, q ** 3]
    for f in feats:
        v = np.array([r[f] for r in d], dtype=float)
        m = np.isnan(v)
        mu = float(np.nanmean(v)) if (~m).any() else 0.0
        sd = float(np.nanstd(v)) if (~m).any() else 1.0
        v = (np.where(m, mu, v) - mu) / (sd if sd > 0 else 1.0)
        cols += [v, v * (q - 0.5)]
        if m.any():
            cols.append(m.astype(float))
    return np.column_stack(cols)


def _folds(pks: list[str]) -> np.ndarray:
    from sklearn.model_selection import GroupKFold
    fold = np.zeros(len(pks), int)
    for k, (_tr, te) in enumerate(GroupKFold(FOLDS).split(np.zeros(len(pks)),
                                                          groups=pks)):
        fold[te] = k
    return fold


def _oof(d: list[dict], feats: list[str], y: np.ndarray, q: np.ndarray,
         fold: np.ndarray) -> np.ndarray:
    X = _design(d, feats, q)
    p = np.full(len(d), np.nan)
    for k in range(FOLDS):
        tr, te = fold != k, fold == k
        Xtr = np.c_[np.ones(tr.sum()), X[tr]]
        pen = RIDGE * np.eye(Xtr.shape[1])
        pen[0, 0] = 0.0
        beta = np.linalg.solve(Xtr.T @ Xtr + pen, Xtr.T @ y[tr])
        p[te] = np.c_[np.ones(te.sum()), X[te]] @ beta
    return p


def _frho(a: np.ndarray, y: np.ndarray, fold: np.ndarray, ix=None) -> float:
    ix = np.arange(len(y)) if ix is None else ix
    r, w = [], []
    for k in range(FOLDS):
        j = ix[fold[ix] == k]
        if len(j) > 20:
            r.append(spearmanr(a[j], y[j]).statistic)
            w.append(len(j))
    return float(np.average(r, weights=w))


def h1_regression(rows: list[dict], rng: np.random.Generator) -> dict:
    """The age plus level model against consensus under each resolver (I2 H1)."""
    rows = sorted(rows, key=lambda r: (r["side"], r["V"], r["pk"]))
    pks = [r["pk"] for r in rows]
    y_all = np.array([r["w3"] for r in rows])
    out = {}
    for arm, feats in (("leaky_reference", ["age_leaky", "lvl_leaky"]),
                       ("outcome_blind", ["age_blind", "lvl_blind"])):
        pc = np.zeros(len(rows))
        pb = np.zeros(len(rows))
        fold = np.zeros(len(rows), int)
        per_side = {}
        for side in F.SIDES:
            s = np.array([r["side"] == side for r in rows])
            d = [r for r in rows if r["side"] == side]
            q = _within([r["fv"] for r in d], [r["V"] for r in d])
            y = _within([r["w3"] for r in d], [r["V"] for r in d])
            fs = _folds([r["pk"] for r in d])
            pc[s], fold[s] = q, fs
            pb[s] = _oof(d, feats, y, q, fs)
            per_side[side] = {"n": int(s.sum()),
                              "rho_consensus": round(_frho(q, y_all[s], fs), 4),
                              "rho_age_level": round(_frho(pb[s], y_all[s], fs), 4)}
        rc, rb = _frho(pc, y_all, fold), _frho(pb, y_all, fold)
        cl = _clusters(pks)
        draws = []
        for _ in range(B_H1):
            ix = np.concatenate([cl[j] for j in rng.integers(0, len(cl), len(cl))])
            draws.append(_frho(pb, y_all, fold, ix) - _frho(pc, y_all, fold, ix))
        lo, hi = float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
        out[arm] = {"features": feats, "n": len(rows), "by_side": per_side,
                    "rho_consensus": round(rc, 4), "rho_age_level": round(rb, 4),
                    "delta_vs_consensus": round(rb - rc, 4),
                    "ci95": [round(lo, 4), round(hi, 4)],
                    "reading": ("CI95 above zero" if lo > 0 else
                                "CI95 below zero" if hi < 0 else "CI95 spans zero")}
    out["i2_reference"] = {"leaky": {"delta": 0.0304, "ci95": [0.0125, 0.0496],
                                     "n": 6564},
                           "outcome_blind": {"delta": 0.0003, "ci95": [-0.0174, 0.0176],
                                             "n": 6564},
                           "source": ("_finalpass_2026-09-24/efv3/I2_new_information/"
                                      "IDEAS.md H1")}
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def ledger_row(doc: dict, path: Path, *, now_iso: str) -> dict:
    """The one development row for data/efv_progress.json: the resolver's coverage by
    route on lv_dev beside the reads, no score, resolvable none."""
    import efv_progress as P
    rows = doc["rows"]
    by = rows.get("by_how") or {}
    routes = ", ".join(f"{k} {by[k]}" for k in sorted(by))
    row = {"run_id": None, "date": doc["generated_at"][:10], "trigger": "efv_change",
           "model_id": MODEL_ID,
           "model_version": {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
                             "label": doc["label"].get("provider"),
                             "resolved_through": doc["label"].get("resolved_through"),
                             "provider": doc["label"].get("provider")},
           "frame": LEDGER_FRAME, "frame_version": None,
           "role": P.FRAMES[LEDGER_FRAME]["role"],
           "tilted": bool(P.FRAMES[LEDGER_FRAME]["tilted"]),
           "window": [min(F.DEV_VINTAGES), max(F.DEV_VINTAGES)],
           "n": rows["rows_scored"], "n_by_side": dict(rows["rows_scored_by_side"]),
           "raters": {}, "deltas": {}, "resolvable": None,
           "verdict": "balance receipt only, no score", "share": None,
           "sources": [{"path": P._rel(Path(path)), "generated_at": doc["generated_at"],
                        "sha256": P._sha256(path)}],
           "note": (f"outcome-blind resolver with the SIDE and RECENCY tiebreaks, coverage "
                    f"by route: {routes}; tiebreak probes "
                    + ", ".join(f"{k.split('.')[-1]} {v['verdict']}"
                                for k, v in sorted(doc["probes"].items())
                                if k.startswith("DS-03:tiebreak."))
                    + "; no score"),
           "last_verified_at": now_iso}
    row["content_hash"] = P.content_hash(row)
    row["run_id"] = f"{doc['generated_at']}|{LEDGER_FRAME}|{row['content_hash'][:8]}"
    return row


def append_ledger(path: Path = OUT, *, ledger_path=None) -> dict:
    import efv_progress as P
    doc = json.loads(path.read_text(encoding="utf-8"))
    now_iso = P._now_iso()
    sb_path = P.DATA_DIR / P.SB_NAME
    sb = P._load_json(sb_path) if sb_path.exists() else None
    row = ledger_row(doc, path, now_iso=now_iso)
    return P.commit_rows([row], ledger_path=ledger_path, sb=sb, now_iso=now_iso)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["ledger"]:
        res = append_ledger()
        print(json.dumps({"ledger": res}, indent=1))
        return 0
    guards = _guards()
    rng = np.random.default_rng(SEED)
    rows, receipt = build_rows()
    bal = balance(rows, rng)
    h1 = h1_regression(rows, rng)
    tb = tiebreak_balance(rows, rng)
    admitted = {side: sorted(k for k, v in bal[side].items()
                             if v.get("verdict") == "BALANCED") for side in F.SIDES}
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    sidecars = {k: prev[k] for k in SIDECAR_KEYS if k in prev}
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    blind, leaky = h1["outcome_blind"], h1["leaky_reference"]
    probes = {}
    for side in F.SIDES:
        for name, _d in INDICATORS:
            v = bal[side][name]
            probes[f"DS-03:balance.{name}:{side}"] = {
                "tag": f"DS-03:balance.{name}:{side}", "verdict": v["verdict"],
                "partial": v.get("partial"), "ci95": v.get("ci95")}
    for arm in ("leaky_reference", "outcome_blind"):
        probes[f"DS-03:h1.{arm}"] = {
            "tag": f"DS-03:h1.{arm}", "verdict": h1[arm]["reading"].upper()
            .replace(" ", "_"), "delta_vs_consensus": h1[arm]["delta_vs_consensus"],
            "ci95": h1[arm]["ci95"]}
    probes.update(tb["probes"])
    doc = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_identity_balance.py",
        "role": "development",
        "adjudicates": "nothing; a validity receipt for the outcome-blind resolver",
        "frame": "lv_dev (F-LV, list vintages 2011 to 2019), W3 on the eWAR v2 label",
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through()},
        "guards": guards,
        "resolver": {"module": "efv_identity.py", "sha256": _sha(ROOT / "efv_identity.py"),
                     "rule": ("printed name matched against people in affiliated minor "
                              "league ball before V (StatsAPI sports 11 to 16 through "
                              "V - 1, draft classes through V - 1); one candidate "
                              "resolves; several pass the SIDE tiebreak (candidates "
                              "whose pre-V exposure sits in the row's own group) and "
                              "then the RECENCY tiebreak (a stat line in V - 1 or "
                              "V - 2), each resolving when it leaves exactly one"),
                     "tiebreak_prior": ("lane A s1.8, counted on lv_dev before the rules "
                                        "were written: 412 ambiguous, 127 by side, 140 "
                                        "by recency, 141 remaining, 4 with no recent "
                                        "candidate"),
                     "by_how_and_side": receipt["by_how_and_side"]},
        "code": {"commit": commit, "tool_sha256": _sha(Path(__file__))},
        "rows": receipt,
        "indicators": dict(INDICATORS),
        "balance": bal,
        "timing_head_admissible": admitted,
        "h1_regression": h1,
        "h1_regression_holds": bool(leaky["ci95"][0] > 0
                                    and blind["ci95"][0] <= 0 <= blind["ci95"][1]),
        "tiebreaks": {"indicators": tb["indicators"], "by_side": tb["by_side"],
                      "never_timing_head_inputs": True},
        "probes": probes,
        "n_probes": len(probes),
        "not_in_efv_progress": ("these reads score no eFV and no candidate, so the "
                                "progress chart (eFV minus consensus) carries none of "
                                "them; they are counted in data/xfv_arm_ledger.json"),
        "seed": SEED, "B": {"h1": B_H1, "balance": B_BAL},
        **sidecars,
    }
    print(json.dumps({"rows": receipt, "h1": {k: h1[k] for k in
                      ("leaky_reference", "outcome_blind")},
                      "admissible": admitted, "tiebreak_probes": tb["probes"]}, indent=1))
    if "--dry-run" not in argv:
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
