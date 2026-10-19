# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""C6, the fresh hitter-lean test (task SG_6 of the efv2026 plan, item N8; owner answer
efv2026 OQ5 = A with OQ2 = A). A DESCRIPTIVE PROBE: not a driver, not a ledger row and not
a read of docs/efv-v2/SURROGATE_2026_GATE.md, which records it in its s9 as a spent read of
the production component on the rows it touched. It is read ONCE.

The test (pre-declared in data/_labs/hitter_lean_c6/PREDECLARED.md before any outcome was
read): on the 2025 FanGraphs report list's hitters, does LEAN (leaner than expected for
height and age) predict LESS forward MiLB ISO over 2025 and 2026 than the scouts' power
grades imply? The 2026-09-25 frame-projectability lane found that sign after looking
(-0.086 SD on the 2017-2019 and 2022-2024 lists); this is its fresh slice.

Order of work (the one-look crash protocol of the SG_6 spec):
1. efv_surrogate_guard.blocked_day() before anything else; it raises on a blocked day.
2. Preconditions: the gate's REGISTERED commit is an ancestor of HEAD and its header
   records efv2026 OQ2 = A and OQ5 = A.
3. Inputs (no outcome): list rows, index, outcome-blind identity, the lv_2026 and R-VM
   exclusions, controls. `--inputs-only` stops here.
4. "SCORING BEGINS" is printed and logged; from then an exception is logged as a spent
   read and re-raised, and nothing is re-run.

Rules: every lv_2026 player leaves the rows and is counted (OQ2 = A, never included); a
2026 debutant leaves and is counted (no rvm_look_2 record); a 2025 debutant stays only
while look_records() holds rvm_look_1. No MLB stat is read (MLB event ids only). No WAR.
No 2020 or 2021 list row. Nothing groups rows by consensus-FV level: consensus is a
continuous control only (docs/PROSPECT_ANCHOR_GATE.md). Writes only under --lane-dir.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_surrogate_guard as G  # noqa: E402

DATA_DIR = ROOT / "data"
FRAME_2026 = DATA_DIR / "efv_surrogate_frame_2026.json"

LIST_LABEL = "2025report"
OVERLAP_LABEL = "2024report"
V = 2025
OUTCOME_SEASONS = (2025, 2026)
BASE_SEASON = 2024
FIRST_EVENT_SEASON = 2014
MIN_PA = 150.0
BASE_MIN_PA = 100.0
B = 2000
SEED = 20260925
STRATUM_MIN_N = 20
LV = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
CONTROLS = ("raw", "game", "hit", "p_raw", "p_game", "age", "cons")
FIRST_LINE = ("SG_6 C6 hitter-lean probe: DESCRIPTIVE, not a driver, not a ledger row, "
              "not a read of the surrogate gate; read once.")
MODELS = {
    "primary_LEAN_given_TALL": (("TALL", "LEAN"), "LEAN"),
    "secondary_PROJ": (("PROJ",), "PROJ"),
    "secondary_LEAN_alone": (("LEAN",), "LEAN"),
}
STRATA = ("side", "age_band", "last_level", "route", "bonus_band")


# ---------------------------------------------------------------------------
# the reporting path (pure; the tests run it on None and NaN fixtures)
# ---------------------------------------------------------------------------

def _bad(v) -> bool:
    return v is None or (isinstance(v, float) and not math.isfinite(v))


def fmt(v, nd: int = 4) -> str:
    """One printed cell. None, NaN and infinities print NA."""
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if _bad(v):
        return "NA"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:+.{nd}f}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x, nd) for x in v) + "]"
    return str(v)


def clean(obj):
    """JSON-safe copy: NaN and infinities become None, numpy scalars plain numbers."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def verdict(coef, hi) -> str:
    """The pre-declared reading of the primary LEAN coefficient (predicted negative)."""
    if _bad(coef) or _bad(hi):
        return "UNDEFINED"
    if coef < 0 and hi < 0:
        return "REPLICATED"
    if coef < 0:
        return "SAME SIGN, NOT RESOLVED"
    return "NOT REPLICATED"


def count_lines(counts: dict) -> list[str]:
    return [f"  {k}: {fmt(v)}" for k, v in counts.items()]


def fit_lines(name: str, res: dict | None) -> list[str]:
    res = res or {}
    ci = res.get("ci95") or [None, None]
    return [f"{name}: coef {fmt(res.get('coef'))} CI95 {fmt(ci[0])} to {fmt(ci[1])} "
            f"ols_t {fmt(res.get('ols_t'), 2)} n {fmt(res.get('n'))} "
            f"players {fmt(res.get('n_players'))}"]


def strata_lines(strata: dict) -> list[str]:
    out = []
    for dim, cells in (strata or {}).items():
        for cell, st in (cells or {}).items():
            st = st or {}
            out.append(f"  {dim}={cell}: n {fmt(st.get('n'))} "
                       f"rho(LEAN, resid) {fmt(st.get('rho'), 3)}")
    return out


def emit(lines, out=print) -> None:
    for ln in ([lines] if isinstance(lines, str) else lines):
        out(ln)


def log_probe(path: Path, **kw) -> None:
    rec = {"logged_at": datetime.now().isoformat(timespec="seconds"), **kw}
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean(rec), allow_nan=False) + "\n")


def write_result(path: Path, doc: dict) -> None:
    Path(path).write_text(json.dumps(clean(doc), indent=1, allow_nan=False) + "\n",
                          encoding="utf-8")


# ---------------------------------------------------------------------------
# inputs (no outcome)
# ---------------------------------------------------------------------------

def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def registered_sha() -> str | None:
    for sha in (_git("log", "--format=%H", "--", G.SURROGATE_GATE_DOC) or "").split():
        if G.gate_sha_committed_for(sha, G.SURROGATE_GATE_DOC):
            return sha
    return None


def ht(s):
    m = re.match(r"\s*(\d)\s*'\s*(\d{1,2})", str(s)) if s is not None else None
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def fl(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def zs(a) -> np.ndarray:
    a = np.asarray(a, float)
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else np.full_like(a, np.nan)


def fg_list(label: str) -> list[dict]:
    """FanGraphs hitter rows of one list (read-only). Never a 2020 or 2021 list."""
    from efv_vintage_frame import RESERVED_LV
    y = int(label[:4])
    if y in RESERVED_LV:
        raise RuntimeError(f"list {label} is reserved (R-LV)")
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    rows = []
    try:
        for pk, name, fv, tj in con.execute(
                "select player_key, player_name, fv, tools_json from snapshots "
                "where source='fangraphs' and interval_label=?", (label,)):
            t = json.loads(tj or "{}")
            if "raw_pwr" not in t:
                continue
            x = t.get("_extras") or {}
            pr = x.get("present") or {}
            rows.append(dict(key=pk, name=name, fg_fv=fl(fv), h=ht(x.get("height")),
                             w=fl(x.get("weight")), age=fl(x.get("age")),
                             raw=fl(t.get("raw_pwr")), game=fl(t.get("game_pwr")),
                             hit=fl(t.get("hit")), p_raw=fl(pr.get("raw_pwr")),
                             p_game=fl(pr.get("game_pwr"))))
    finally:
        con.close()
    return rows


def add_index(rows: list[dict]) -> tuple[list[dict], int]:
    """LEAN, TALL, YOUNG, PROJ on every eligible row (the original lane's formulas)."""
    req = ("h", "w", "age", "raw", "game", "hit", "p_raw", "p_game")
    keep = [dict(r) for r in rows if all(r.get(k) is not None for k in req) and r["h"] > 60]
    if not keep:
        return [], len(rows)
    h = np.array([r["h"] for r in keep], float)
    w = np.array([r["w"] for r in keep], float)
    age = np.array([r["age"] for r in keep], float)
    bmi = 703 * w / h ** 2
    X = np.column_stack([np.ones_like(h), h, age])
    beta, *_ = np.linalg.lstsq(X, bmi, rcond=None)
    lean = zs(-(bmi - X @ beta))
    tall = zs(h)
    young = zs(-age)
    proj = zs(tall + lean)
    for i, r in enumerate(keep):
        r.update(bmi=float(bmi[i]), LEAN=float(lean[i]), TALL=float(tall[i]),
                 YOUNG=float(young[i]), PROJ=float(proj[i]))
    return keep, len(rows) - len(keep)


def lv2026_sets(path: Path = FRAME_2026) -> dict[str, set]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    keys, pids, rids = set(), set(), set()
    for side_rows in (doc.get("rows") or {}).values():
        for r in side_rows:
            if r.get("player_key"):
                keys.add(r["player_key"])
            for k, dst in (("person_id", pids), ("mlbam_id", pids), ("record_mlbam_id", rids)):
                v = r.get(k)
                if v is not None:
                    try:
                        dst.add(int(v))
                    except (TypeError, ValueError):
                        pass
    return {"keys": keys, "pids": pids, "rids": rids}


def _lines(S, season: int, pid: int) -> list[dict]:
    out = []
    for ln in S._season_index(season, "hitting").get(int(pid), []):
        lv = S._line_level(ln, season, "gate")
        if lv in LV:
            out.append(dict(ln["row"], _lv=lv))
    return out


def iso_rel(S, pid: int, seasons, min_pa: float):
    """PA-weighted ISO minus the pure level-season norm ISO; (None, pa) under min_pa."""
    tot = pa_sum = 0.0
    for s in seasons:
        for r in _lines(S, s, pid):
            pa, slg, avg = fl(r.get("pa")), fl(r.get("slg")), fl(r.get("avg"))
            if not pa or slg is None or avg is None:
                continue
            nm = S._pure_norms(s, r["_lv"], "hitting") or {}
            if fl(nm.get("iso")) is None:
                continue
            tot += pa * ((slg - avg) - nm["iso"])
            pa_sum += pa
    return (tot / pa_sum if pa_sum >= min_pa else None), pa_sum


def top_level(S, pid: int, season: int):
    best = None
    for r in _lines(S, season, pid):
        if best is None or LV[r["_lv"]] > LV[best]:
            best = r["_lv"]
    return best


def first_mlb_season(S, pid: int):
    for s in range(FIRST_EVENT_SEASON, max(OUTCOME_SEASONS) + 1):
        if s in S.NO_MILB_SEASONS:
            continue
        if any(int(pid) in S._mlb_event_ids(s, g) for g in ("hitting", "pitching")):
            return s
    return None


def age_band(age):
    if age is None:
        return "unknown"
    return "20_or_under" if age < 21 else ("21_to_22" if age < 23 else "23_or_over")


def level_band(lv):
    if lv is None:
        return "none"
    return {"DSL": "DSL_CPX", "CPX": "DSL_CPX", "A": "A_Aplus", "A+": "A_Aplus",
            "AA": "AA_AAA", "AAA": "AA_AAA"}[lv]


def route_of(acq: dict | None, birth) -> str:
    import efv_dataset as D
    if not acq or acq.get("year") is None or int(acq["year"]) >= V:
        return "other_or_unknown"
    m = acq.get("method")
    if m == "international_fa":
        return "international_fa"
    if m == "draft":
        return "college_draft" if D._cohort_flags(m, acq["year"], birth)[1] else "hs_draft"
    return "other_or_unknown"


def bonus_band(acq: dict | None) -> str:
    if not acq or acq.get("year") is None or int(acq["year"]) >= V:
        return "unknown"
    b = fl(acq.get("bonus_usd"))
    if b is None:
        return "unknown"
    return "under_250k" if b < 250_000 else ("250k_to_1M" if b < 1_000_000 else "1M_or_over")


def build_inputs(S, F, ID, D, SB) -> tuple[list[dict], dict, dict]:
    """Eligible, identity-resolved, non-excluded rows with every control. No outcome."""
    raw = fg_list(LIST_LABEL)
    rows, n_missing = add_index(raw)
    U = F.load_universe()
    index = ID.build_index(V - 1)
    non_rater, constant = F._real_sources()
    excl = frozenset(non_rater | constant)
    lv = lv2026_sets()
    recs = set(G.look_records())
    counts = {"list_rows_hitters": len(raw), "dropped_missing_inputs": n_missing,
              "index_rows": len(rows)}
    absent, in_lv, lv_by_key_absent, vm26, vm25_kept, vm25_left = 0, 0, 0, 0, 0, 0
    keep = []
    for r in rows:
        rec = U.get(r["key"])
        ident = ID.resolve_record(rec, V, index, "hit") if rec else None
        pid = ident.person_id if ident else None
        if pid is None:
            absent += 1
            lv_by_key_absent += r["key"] in lv["keys"]
            continue
        rid = fl((rec or {}).get("mlbam_id"))
        if (r["key"] in lv["keys"] or int(pid) in lv["pids"]
                or (rid is not None and int(rid) in lv["rids"])):
            in_lv += 1
            continue
        dy = first_mlb_season(S, pid)
        if dy == 2026:
            vm26 += 1
            continue
        if dy == 2025:
            if G.LOOK_1 in recs:
                vm25_kept += 1
            else:
                vm25_left += 1
                continue
        r = dict(r, pid=int(pid), id_how=ident.how, debut_season=dy,
                 birth=(rec or {}).get("birth_date"))
        fr = F.frame_row(rec, "hit", V, excl=excl, milb=False, index=index)
        c = ((fr or {}).get("grades") or {}).get(SB.CONSENSUS_KEY)
        r["cons"] = fl(c) if fl(c) is not None else r["fg_fv"]
        r["cons_src"] = "consensus" if fl(c) is not None else "fg_fv"
        r["base"], _ = iso_rel(S, pid, [BASE_SEASON], BASE_MIN_PA)
        r["lvl"] = top_level(S, pid, BASE_SEASON)
        keep.append(r)
    acq, _il = D._load_sidecars({r["key"] for r in keep}) if keep else ({}, {})
    for r in keep:
        a = acq.get(r["key"])
        r["side"] = "hit"
        r["age_band"] = age_band(r["age"])
        r["last_level"] = level_band(r["lvl"])
        r["route"] = route_of(a, r.get("birth"))
        r["bonus_band"] = bonus_band(a)
    counts.update({
        "ABSENT_IDENTITY": absent,
        "ABSENT_IDENTITY_also_lv2026_by_key": lv_by_key_absent,
        "lv2026_excluded": in_lv,
        "rvm_2026_cohort_left": vm26,
        "rvm_2025_cohort_kept": vm25_kept,
        "rvm_2025_cohort_left": vm25_left,
        "candidate_rows": len(keep),
        "cons_from_consensus": sum(r["cons_src"] == "consensus" for r in keep),
        "cons_from_fg_fv": sum(r["cons_src"] == "fg_fv" for r in keep),
        "baseline_iso_missing": sum(r["base"] is None for r in keep),
    })
    overlap_keys = {r["key"] for r in fg_list(OVERLAP_LABEL)}
    info = {"look_records": sorted(recs), "lv2026_keys": len(lv["keys"]),
            "lv2026_person_ids": len(lv["pids"]), "overlap_keys_2024": overlap_keys}
    return keep, counts, info


# ---------------------------------------------------------------------------
# models (outcome side)
# ---------------------------------------------------------------------------

def design(rows: list[dict], feats) -> tuple[np.ndarray, list[str]]:
    cols, names = [np.ones(len(rows))], ["const"]
    for k in CONTROLS:
        cols.append(np.array([r[k] for r in rows], float))
        names.append(k)
    base = np.array([np.nan if r["base"] is None else r["base"] for r in rows], float)
    miss = np.isnan(base)
    base[miss] = np.nanmean(base) if (~miss).any() else 0.0
    cols += [base, miss.astype(float)]
    names += ["base", "base_miss"]
    for lv in ("CPX", "A", "A+", "AA", "AAA"):
        cols.append(np.array([1.0 if r["lvl"] == lv else 0.0 for r in rows]))
        names.append("lv_" + lv)
    cols.append(np.array([1.0 if r["lvl"] is None else 0.0 for r in rows]))
    names.append("lv_none")
    for f in feats:
        cols.append(np.array([r[f] for r in rows], float))
        names.append(f)
    X = np.column_stack(cols)
    keep = X.std(0) > 0
    keep[0] = True
    return X[:, keep], [n for n, k in zip(names, keep) if k]


def ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    n, k = X.shape
    s2 = res @ res / max(n - k, 1)
    cov = s2 * np.linalg.pinv(X.T @ X)
    return beta, np.sqrt(np.clip(np.diag(cov), 0, None)), res


def fit(rows: list[dict], feats, target: str) -> dict:
    out = {"n": len(rows), "n_players": len({r["pid"] for r in rows}), "coef": None,
           "ols_t": None, "ci95": [None, None], "feats": list(feats), "target": target}
    if len(rows) < 30:
        return out
    y = zs([r["O1"] for r in rows])
    X, names = design(rows, feats)
    if target not in names or X.shape[0] <= X.shape[1] + 1:
        return out
    beta, se, _ = ols(X, y)
    j = names.index(target)
    rng = np.random.default_rng(SEED)
    by: dict[int, list[int]] = {}
    for i, r in enumerate(rows):
        by.setdefault(r["pid"], []).append(i)
    keys = list(by)
    bs = []
    for _ in range(B):
        pick = rng.integers(0, len(keys), len(keys))
        idx = [i for p in pick for i in by[keys[p]]]
        bb, *_ = np.linalg.lstsq(X[idx], y[idx], rcond=None)
        bs.append(bb[j])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    out.update(coef=float(beta[j]), ols_t=float(beta[j] / se[j]) if se[j] > 0 else None,
               ci95=[float(lo), float(hi)])
    return out


def strata(rows: list[dict]) -> dict:
    from scipy.stats import spearmanr
    out = {d: {} for d in STRATA}
    if len(rows) < 30:
        return out
    y = zs([r["O1"] for r in rows])
    X, _ = design(rows, ())
    _, _, resid = ols(X, y)
    for d in STRATA:
        cells: dict[str, list[int]] = {}
        for i, r in enumerate(rows):
            cells.setdefault(str(r[d]), []).append(i)
        for cell, idx in sorted(cells.items()):
            st = {"n": len(idx), "rho": None}
            if len(idx) >= STRATUM_MIN_N:
                rho = spearmanr([rows[i]["LEAN"] for i in idx], resid[idx])[0]
                st["rho"] = float(rho)
            out[d][cell] = st
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lane-dir", required=True, type=Path)
    ap.add_argument("--inputs-only", action="store_true",
                    help="build and count the inputs; read no outcome")
    a = ap.parse_args(argv)
    G.blocked_day()                       # the first action, before any row is read
    emit(FIRST_LINE)
    t0 = time.time()
    lane = a.lane_dir
    probes = lane / "PROBES.jsonl"
    if not probes.exists():
        raise SystemExit("the lane's row policy (PROBES.jsonl) must exist before any number")
    sha = registered_sha()
    if sha is None:
        raise SystemExit("STOP: no REGISTERED commit of the surrogate gate")
    oq2, oq5 = G.gate_header_records(sha, "OQ2"), G.gate_header_records(sha, "OQ5")
    if oq5 != "A" or oq2 != "A":
        raise SystemExit(f"STOP: this probe runs under OQ5 = A with OQ2 = A only "
                         f"(header OQ2 {oq2}, OQ5 {oq5})")
    emit(f"gate REGISTERED at {sha}; header OQ2 {oq2}, OQ5 {oq5}")

    import efv_dataset as D
    import efv_identity as ID
    import efv_surrogate as S
    import efv_vintage_frame as F
    import source_backtest as SB

    rows, counts, info = build_inputs(S, F, ID, D, SB)
    emit(f"look records: {info['look_records']}; lv_2026 keys {info['lv2026_keys']}, "
         f"person ids {info['lv2026_person_ids']}")
    emit("inputs (no outcome read):")
    emit(count_lines(counts))
    if a.inputs_only:
        log_probe(probes, kind="inputs_dry_run", what="input-side counts, no outcome read",
                  counts=counts)
        emit(f"inputs only; elapsed {time.time() - t0:.1f}s")
        return 0

    emit("SCORING BEGINS")
    log_probe(probes, kind="read_started", what="C6 hitter-lean read, outcome seasons "
              f"{list(OUTCOME_SEASONS)}", gate_sha=sha, counts=counts)
    try:
        scored, short = [], 0
        for r in rows:
            v, pa = iso_rel(S, r["pid"], OUTCOME_SEASONS, MIN_PA)
            if v is None:
                short += 1
                continue
            scored.append(dict(r, O1=v, O1_pa=pa))
        counts["O1_under_150_pa"] = short
        counts["analysis_rows"] = len(scored)
        counts["analysis_players"] = len({r["pid"] for r in scored})
        counts["analysis_also_on_2024_list"] = sum(r["key"] in info["overlap_keys_2024"]
                                                   for r in scored)
        counts["analysis_rvm_2025_cohort"] = sum(r["debut_season"] == 2025 for r in scored)
        emit("analysis rows:")
        emit(count_lines({k: counts[k] for k in ("O1_under_150_pa", "analysis_rows",
                                                 "analysis_players",
                                                 "analysis_also_on_2024_list",
                                                 "analysis_rvm_2025_cohort")}))
        fits = {name: fit(scored, feats, tgt) for name, (feats, tgt) in MODELS.items()}
        prim = fits["primary_LEAN_given_TALL"]
        read = verdict(prim["coef"], prim["ci95"][1])
        for name, res in fits.items():
            emit(fit_lines(name, res))
            log_probe(probes, kind="probe", what=f"C6 {name}", frame="FG 2025report "
                      "hitters, lv_2026 and 2026 debutants excluded, fwd MiLB ISO_rel "
                      "2025-2026 on pure norms", n=res["n"], metric="std coef, player "
                      "cluster bootstrap CI95", result=res["coef"], ci95=res["ci95"],
                      declared=True)
        st = strata(scored)
        emit("descriptive strata (no CI, no verdict):")
        emit(strata_lines(st))
        log_probe(probes, kind="probe", what="C6 descriptive strata: Spearman of LEAN with "
                  "the controls-only O1 residual", n=len(scored), result=st, declared=True)
        emit(f"PRIMARY READING (predicted sign negative): {read}")
        doc = {
            "task": "SG_6_HITTER_LEAN_C6_READ",
            "what": FIRST_LINE,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "gate_sha": sha, "owner_answers": {"efv2026 OQ2": oq2, "efv2026 OQ5": oq5},
            "look_records": info["look_records"],
            "list": LIST_LABEL, "outcome_seasons": list(OUTCOME_SEASONS),
            "min_pa": MIN_PA, "bootstrap": {"B": B, "seed": SEED},
            "counts": counts, "fits": fits, "primary_reading": read, "strata": st,
            "selected_subset": "every lv_2026 player is excluded (OQ2 = A), so the rows "
                               "are players on no 2026 rater list plus released 2025 "
                               "debutants: a selected subset, not the 2025 list",
            "elapsed_s": round(time.time() - t0, 1),
        }
        write_result(lane / "sg6_result.json", doc)
        log_probe(probes, kind="read_spent", what="C6 read complete; spent on the rows it "
                  "touched", analysis_rows=len(scored), primary_reading=read)
        emit(f"elapsed {doc['elapsed_s']}s")
    except BaseException:
        log_probe(probes, kind="read_spent_crash", what="exception after scoring began; "
                  "the read is spent and is not re-run", traceback=traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
