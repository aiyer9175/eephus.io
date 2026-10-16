# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball America's grade inside PROSPX consensus (BA_GRADE_IN_CONSENSUS; owner EW3-36,
2026-10-16): raw, risk-adjusted or excluded, read on the development frames only. The rule is
fixed in docs/efv-v2/BA_GRADE_IN_CONSENSUS.md (committed alone before this file existed).

    --check   build the frames and the served arm, run the parity checks P1 to P4, and stop.
              No outcome is read.
    --run     the registered read, once: arms S, R, A, A2, X, the nulls N1 and N2, the planted
              checks PL1 and PL2, the board effect, written to
              data/_labs/ba_grade/ba_grade_consensus_read.json.

Every arm is a full rebuild of the consensus time series through the served code
(storage.load_all_snapshots, consensus.build_timeseries with the adopted normalization) with ONLY
Baseball America's grade changed, in the snapshot corpus AND in the normalizer's paired table
(grade_normalization._all_latest, re-derived from the same database rows). Nothing served is
written. No row is grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the groups are
frame, side and year. Only lv_dev and vm_dev are read; a reserved row is refused.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

import baseballamerica_csv as BAC  # noqa: E402

TASK = "BA_GRADE_IN_CONSENSUS"
DOC = "docs/efv-v2/BA_GRADE_IN_CONSENSUS.md"
ARTIFACT = ROOT / "data" / "_labs" / "ba_grade" / "ba_grade_consensus_read.json"
BA = "baseballamerica"
#: BA's first board in the database; no consensus point before it can carry BA (P3).
FIRST_BA_DATE = "2023-02-15"
#: The only BA board season a development row can reach (section 0 of the document).
DEV_BA_SEASON = 2023
FRAMES = ("lv_dev", "vm_dev")
ARMS = ("S", "R", "A", "A2", "X")
ARM_LABEL = {"S": "served (raw before 2026, adjusted from 2026)", "R": "raw in every season",
             "A": "risk-adjusted, crosswalk by position", "A2": "risk-adjusted, crosswalk by label",
             "X": "excluded"}
#: Section 3: penalties for BA's older risk ladder (2023 to 2025). Neither is BA's own.
OLD_LADDER = {
    "A": {"low": 0.0, "medium": 5.0, "high": 10.0, "very high": 15.0, "extreme": 20.0},
    "A2": {"low": 0.0, "medium": 10.0, "high": 15.0, "very high": 17.5, "extreme": 20.0},
}
NULL_K = 100
PERM_SEED = 20261016
P_NULL = 0.05
PL1_QUANTILE = 0.95
PL2_QUANTILE = 0.975
CONS_KEY = "prospx_consensus"
DROP = object()


# ---------------------------------------------------------------------------
# BA's value on one row, per arm
# ---------------------------------------------------------------------------

def season_of(date: str | None) -> int | None:
    try:
        return int(str(date)[:4])
    except (TypeError, ValueError):
        return None


def penalty(season: int | None, risk: str | None, ladder: str = "A") -> float | None:
    """The risk penalty in FV points: BA's published 2026 ladder from 2026, the section 3
    crosswalk before. None when the label has no penalty."""
    if not risk or season is None:
        return None
    if season >= BAC.ADJUSTED_GRADE_FIRST_SEASON:
        return BAC.risk_penalty(risk)
    return OLD_LADDER[ladder].get(str(risk).strip().lower())


def arm_value(arm: str, season: int | None, stored, raw, risk):
    """BA's grade on one row under an arm, or DROP. A row with no raw grade (the rank-only
    list) keeps its stored value (None) in every arm but X."""
    if arm == "X":
        return DROP
    if arm == "S" or raw is None:
        return stored
    if arm == "R":
        return float(raw)
    if arm in OLD_LADDER:
        pen = penalty(season, risk, arm)
        return stored if pen is None else float(raw) - pen
    raise ValueError(f"unknown arm {arm!r}")


def extras_of(tools) -> dict:
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except (TypeError, ValueError):
            tools = None
    ex = (tools or {}).get("_extras") if isinstance(tools, dict) else None
    return ex if isinstance(ex, dict) else {}


class Transform:
    """BA's grade per row: an arm, optionally with per-unit overrides of the raw grade or
    of the penalty. A unit is (canonical player key, snapshot date)."""

    def __init__(self, arm: str, *, raw_over: dict | None = None, pen_over: dict | None = None):
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm!r}")
        self.arm = arm
        self.raw_over = dict(raw_over or {})
        self.pen_over = dict(pen_over or {})

    def __call__(self, pk: str, date: str, stored, tools):
        ex = extras_of(tools)
        raw = ex.get("ba_raw_grade")
        unit = (pk, str(date))
        if raw is not None and unit in self.raw_over:
            raw = self.raw_over[unit]
        if raw is not None and unit in self.pen_over:
            return float(raw) - float(self.pen_over[unit])
        return arm_value(self.arm, season_of(date), stored, raw, ex.get("ba_risk"))


# ---------------------------------------------------------------------------
# the normalizer's paired table, re-derived with the arm's BA value
# ---------------------------------------------------------------------------

def db_rows(db: Path | None = None) -> list[tuple]:
    """The rows grade_normalization._all_latest reads, in its order, plus tools_json."""
    import grade_normalization as G
    path = Path(db) if db else G._DB
    con = sqlite3.connect(str(path))
    try:
        return con.execute(
            "SELECT source, player_key, position, snapshot_date, fv, tools_json FROM snapshots "
            "WHERE fv IS NOT NULL").fetchall()
    finally:
        con.close()


def latest_table(rows: list[tuple], transform=None, canon=None) -> dict:
    """grade_normalization._all_latest's table, line for line, with BA's fv replaced by
    transform(canonical key, date, fv, tools_json) (DROP removes the row)."""
    import grade_normalization as G
    tmp: dict = {}
    for src, pk, pos, date, fv, tj in rows:
        if not src or not pk or not date:
            continue
        if src == BA and transform is not None:
            v = transform(canon(pk) if canon else pk, str(date), fv, tj)
            if v is DROP or v is None:
                continue
            fv = v
        try:
            yr = int(str(date)[:4])
            fvf = float(fv)
        except (TypeError, ValueError):
            continue
        role = "pitcher" if G._is_pitcher(pos) else "hitter"
        k = (role, yr, pk, src)
        if k not in tmp or date > tmp[k][0]:
            tmp[k] = (date, fvf)
    out: dict = {}
    for (role, yr, pk, src), (_d, fvf) in tmp.items():
        out.setdefault((role, yr), {}).setdefault(pk, {})[src] = fvf
    return out


@contextlib.contextmanager
def normalizer(table: dict):
    """Serve `table` as grade_normalization._all_latest for the duration; restored after."""
    import grade_normalization as G
    orig = G._all_latest
    G._paired_dists.cache_clear()
    G._all_latest = lambda: table
    try:
        yield
    finally:
        G._all_latest = orig
        G._paired_dists.cache_clear()


def transform_snapshots(snaps: list, transform) -> list:
    out = []
    for s in snaps:
        if s.source != BA:
            out.append(s)
            continue
        v = transform(s.player_key, str(s.snapshot_date), s.fv, s.tools)
        if v is DROP:
            continue
        out.append(s if v == s.fv else dataclasses.replace(s, fv=v))
    return out


def build(snaps: list, rows: list[tuple], transform, canon) -> list:
    """One arm: the consensus time series through the served code."""
    import consensus as C
    table = latest_table(rows, transform, canon)
    with normalizer(table):
        return C.build_timeseries(transform_snapshots(snaps, transform),
                                  normalize=C.ADOPT_NORMALIZED_CONSENSUS)


# ---------------------------------------------------------------------------
# reading an arm on the frames and on the board
# ---------------------------------------------------------------------------

def window_value(points: list, year: int) -> tuple:
    """(consensus_fv_raw, carries BA) of the latest point in [year-01-01, year-05-01), the
    rule source_backtest._rater_grades_for_year applies to a vm_dev debut year."""
    lo, hi = f"{int(year)}-01-01", f"{int(year)}-05-01"
    win = [p for p in points if p.snapshot_date and lo <= p.snapshot_date < hi]
    if not win:
        return None, False
    p = sorted(win, key=lambda q: q.snapshot_date)[-1]
    v = p.consensus_fv_raw if p.consensus_fv_raw is not None else p.consensus_fv
    return (None if v is None else float(v)), BA in (p.per_source or {})


def read_arm(ts: list, vm_rows: list[dict], board_keys) -> dict:
    by = {p.player_key: p for p in ts}
    vm = {}
    reach = set()
    for c in vm_rows:
        p = by.get(c["key"])
        v, has = window_value(p.points if p else [], int(c["year"]))
        vm[(c["side"], int(c["year"]), c["key"])] = v
        if has:
            reach.add((c["side"], int(c["year"]), c["key"]))
    board = {}
    for k in board_keys:
        p = by.get(k)
        if p and p.points:
            last = p.points[-1]
            v = last.consensus_fv_raw if last.consensus_fv_raw is not None else last.consensus_fv
            board[k] = (None if v is None else float(v), BA in (last.per_source or {}))
    return {"vm": vm, "reach": reach, "board": board}


def pre_ba_points(ts: list) -> dict:
    """{(player, date): consensus_fv_raw} of every point dated before FIRST_BA_DATE (P3)."""
    return {(p.player_key, q.snapshot_date): q.consensus_fv_raw
            for p in ts for q in p.points if q.snapshot_date and q.snapshot_date < FIRST_BA_DATE}


def p3_check(pre: dict, dev_keys: set) -> dict:
    """P3 as amended (section 7a): no pre-BA point of a development player moves between
    arms; every other moved point is listed."""
    moved = []
    base = pre["S"]
    for a, pts in pre.items():
        if a == "S":
            continue
        for k in sorted(set(pts) | set(base)):
            if pts.get(k) != base.get(k):
                moved.append({"arm": a, "player": k[0], "date": k[1], "S": base.get(k),
                              "arm_value": pts.get(k)})
    dev = [m for m in moved if m["player"] in dev_keys]
    return {"dev_points_moved": len(dev), "other_points_moved": len(moved) - len(dev),
            "moved": moved[:50]}


# ---------------------------------------------------------------------------
# nulls and plants (units are (canonical key, date) of BA's DEV_BA_SEASON rows)
# ---------------------------------------------------------------------------

def ba_units(snaps: list, season: int = DEV_BA_SEASON) -> list[dict]:
    """One record per (player, date) BA row of `season` with a raw grade, with its role."""
    import grade_normalization as G
    seen = {}
    for s in snaps:
        if s.source != BA or season_of(s.snapshot_date) != season:
            continue
        ex = extras_of(s.tools)
        if ex.get("ba_raw_grade") is None:
            continue
        u = (s.player_key, str(s.snapshot_date))
        if u in seen:
            continue
        seen[u] = {"unit": u, "key": s.player_key, "raw": float(ex["ba_raw_grade"]),
                   "pen": penalty(season, ex.get("ba_risk"), "A"),
                   "role": "pitcher" if G._is_pitcher(s.position) else "hitter"}
    return list(seen.values())


def permute_within_role(units: list[dict], field: str, rng) -> dict:
    """{unit: value} with `field` permuted among units of the same role."""
    out = {}
    for role in sorted({u["role"] for u in units}):
        grp = [u for u in units if u["role"] == role and u[field] is not None]
        vals = np.array([u[field] for u in grp], dtype=np.float64)
        perm = rng.permutation(vals.size)
        for u, j in zip(grp, perm):
            out[u["unit"]] = float(vals[j])
    return out


def planted(units: list[dict], reached: list[dict], field: str, *, high_first: bool) -> dict:
    """{unit: value}: within each side, the reached players' own `field` values re-assigned
    in order of their outcome. high_first True gives the largest value to the highest
    outcome (an informative grade); False gives it to the lowest (an informative penalty).
    Ties in outcome break by player key."""
    by_key: dict = {}
    for u in units:
        by_key.setdefault(u["key"], []).append(u)
    out = {}
    for side in sorted({r["side"] for r in reached}):
        rr = [r for r in reached if r["side"] == side and r["key"] in by_key]
        rr = [r for r in rr if by_key[r["key"]][0][field] is not None]
        vals = sorted((by_key[r["key"]][0][field] for r in rr), reverse=True)
        order = sorted(rr, key=lambda r: (-r["war"], r["key"]) if high_first
                       else (r["war"], r["key"]))
        for r, v in zip(order, vals):
            for u in by_key[r["key"]]:
                out[u["unit"]] = float(v)
    return out


# ---------------------------------------------------------------------------
# statistics and the reading rule
# ---------------------------------------------------------------------------

def delta(rows: list[dict], a: str, b: str, *, B: int, seed: int, statistic: str = "within"):
    import efv_v2_stat as S
    sel = [r for r in rows if r["v"].get(a) is not None and r["v"].get(b) is not None]
    return S.paired_delta([r["key"] for r in sel], [r["group"] for r in sel],
                          [r["war"] for r in sel], [r["contrib"] for r in sel],
                          [r["v"][a] for r in sel], [r["v"][b] for r in sel],
                          [r["v"]["S"] for r in sel], statistic=statistic, B=B, seed=seed)


def within_of(rows: list[dict], arm: str) -> dict:
    import efv_v2_stat as S
    sel = [r for r in rows if r["v"].get(arm) is not None]
    st = S.rater_stats([r["v"][arm] for r in sel], [r["war"] for r in sel],
                       [r["contrib"] for r in sel], [r["group"] for r in sel],
                       [r["v"]["S"] for r in sel])
    return {"n": st["n"], "within": st["within"], "pooled": st["pooled"], "auc": st["auc"],
            "within_rows": st["within_rows"], "within_groups": st["within_groups"]}


def p_null(obs: float | None, null: list[float], *, two_sided: bool) -> float | None:
    if obs is None or not null:
        return None
    n = np.asarray(null, dtype=np.float64)
    if two_sided:
        hits = int((np.abs(n) >= abs(obs)).sum())
    elif obs >= 0:
        hits = int((n >= obs).sum())
    else:
        hits = int((n <= obs).sum())
    return round((1 + hits) / (1 + n.size), 4)


def ci_excludes_zero(d: dict) -> bool:
    ci = d.get("ci95")
    return isinstance(ci, list) and len(ci) == 2 and (ci[0] > 0 or ci[1] < 0)


def plant_passes(d: dict, null: list[float], q: float, *, absolute: bool) -> dict:
    n = np.asarray(null, dtype=np.float64)
    thr = float(np.quantile(np.abs(n) if absolute else n, q)) if n.size else None
    ci = d.get("ci95")
    ok = (isinstance(ci, list) and ci[0] > 0 and thr is not None and d.get("delta") is not None
          and d["delta"] > thr)
    return {"delta": d.get("delta"), "ci95": ci, "null_threshold": None if thr is None else
            round(thr, 5), "null_quantile": q, "passes": bool(ok)}


def resolves(d: dict, p: float | None, plant_ok: bool) -> dict:
    ok = bool(ci_excludes_zero(d) and p is not None and p < P_NULL and plant_ok)
    sign = None if d.get("delta") is None else ("positive" if d["delta"] > 0 else "negative")
    return {"resolves": ok, "direction": sign if ok else None,
            "reading": ("RESOLVED " + sign) if ok else "UNRESOLVED",
            "ci_excludes_zero": ci_excludes_zero(d), "p_null": p, "planted_passed": plant_ok}


def recommendation(c1: dict, c2: dict, c3: dict) -> dict:
    """Section 8's default, from the three adjudicated readings."""
    if c3["resolves"] and c3["direction"] == "positive":
        return {"default": "KEEP", "why": "C3 resolves positive: adjusted beats raw"}
    if c3["resolves"] and c3["direction"] == "negative":
        return {"default": "RAW", "why": "C3 resolves negative: raw beats adjusted"}
    if (c1["resolves"] and c1["direction"] == "negative" and c2["resolves"]
            and c2["direction"] == "negative"):
        return {"default": "EXCLUDE", "why": "C1 and C2 resolve negative: BA's vote hurts"}
    return {"default": "KEEP", "why": "nothing resolves: no served change without a resolved read"}


def board_effect(arm: dict, base: dict, side_of: dict) -> dict:
    out = {}
    for side in ("hit", "pit"):
        d = []
        for k, (v0, has) in base.items():
            if side_of.get(k) != side or not has or v0 is None:
                continue
            v1 = (arm.get(k) or (None, False))[0]
            if v1 is not None:
                d.append(v1 - v0)
        a = np.asarray(d, dtype=np.float64)
        out[side] = ({"n_with_ba": int(a.size), "mean": round(float(a.mean()), 3),
                      "sd": round(float(a.std(ddof=1)), 3) if a.size > 1 else None,
                      "mean_abs": round(float(np.abs(a).mean()), 3),
                      "largest_up": round(float(a.max()), 2), "largest_down": round(float(a.min()), 2),
                      "moved_1fv_or_more": int((np.abs(a) >= 1.0).sum())}
                     if a.size else {"n_with_ba": 0})
    return out


# ---------------------------------------------------------------------------
# guards and inputs
# ---------------------------------------------------------------------------

def registration_sha() -> str | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%H", "--", DOC], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return None
    return out or None


def guard_rows(scored: dict) -> None:
    """Only the development frames, and no reserved year inside them."""
    import efv_vintage_frame as F
    bad = set(scored) - set(FRAMES)
    if bad:
        raise RuntimeError(f"refused: frames {sorted(bad)} are not development frames")
    for c in scored.get("lv_dev", []):
        if int(c["year"]) in F.RESERVED_LV:
            raise RuntimeError(f"refused: reserved list vintage {c['year']}")
    for c in scored.get("vm_dev", []):
        if int(c["year"]) >= F.R_VM_FIRST_DEBUT_YEAR:
            raise RuntimeError(f"refused: reserved debut cohort {c['year']}")


def dev_rows(log=print) -> tuple[dict, dict]:
    """The scored rows of lv_dev and vm_dev exactly as efv_w2_anchor.build makes them."""
    import efv_w2_anchor as W2A
    built = W2A.build(log=log)
    frames = built["inputs"]["frames"]
    scored = {fid: [c for side, by in frames[fid]["by_side"].items()
                    for _V, blk in by.items() for c in blk["scored"]] for fid in FRAMES}
    guard_rows(scored)
    return scored, built["inputs"].get("guards") or {}


def stat_rows(scored: dict, vals: dict) -> list[dict]:
    """Rows for the statistics: lv_dev rows carry the frame's own consensus in every arm
    (P3: no arm can move a point before FIRST_BA_DATE); vm_dev rows carry each arm's value."""
    out = []
    for fid in FRAMES:
        for c in scored[fid]:
            k = (c["side"], int(c["year"]), c["key"])
            if fid == "lv_dev":
                v = {a: float(c["grades"][CONS_KEY]) for a in vals}
            else:
                v = {a: vals[a].get(k) for a in vals}
            out.append({"fid": fid, "key": c["key"], "side": c["side"], "year": int(c["year"]),
                        "group": f"{fid}|{c['group']}", "war": float(c["outcome"]["war"]),
                        "contrib": bool(c["outcome"]["contributor"]),
                        "stored": float(c["grades"][CONS_KEY]), "v": v})
    return out


def primary(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["fid"] == "vm_dev" and r["year"] == DEV_BA_SEASON]


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _r(v, n=5):
    return None if v is None else round(float(v), n)


def run(*, check_only: bool = False, null_k: int = NULL_K, B: int | None = None,
        log=print) -> dict:
    import efv_labels as L
    import efv_v2_stat as S
    import efv_v2_model_class_screen as MCS
    import grade_normalization as G
    import storage
    t0 = time.time()
    sha = registration_sha()
    if not sha:
        raise RuntimeError(f"refused: {DOC} is not committed")
    if L.provider() != "fwar":
        raise RuntimeError(f"refused: label provider is {L.provider()!r}, not the frozen 'fwar'")
    B = S.B_DEFAULT if B is None else int(B)
    seed = S.SEED_DEFAULT
    scored, guards = dev_rows(log=log)
    vm_rows = scored["vm_dev"]
    log(f"frames: lv_dev {len(scored['lv_dev'])}, vm_dev {len(vm_rows)} scored rows "
        f"({round(time.time() - t0, 1)} s)")
    xfv = {k: r for k, r in json.loads((ROOT / "data" / "xfv.json").read_text(
        encoding="utf-8"))["by_player"].items()
           if r.get("kind") == "active" and (r.get("efv_v2") or {}).get("group")}
    side_of = {k: ("pit" if r.get("side") == "P" else "hit") for k, r in xfv.items()}
    snaps = storage.load_all_snapshots()
    rows = db_rows()
    canon = storage.canonical_player_key
    # P1
    p1 = latest_table(rows, Transform("S"), canon) == G._all_latest()
    if not p1:
        raise RuntimeError("P1 failed: the re-derived paired table differs from the served one")
    log("P1: the re-derived paired table equals grade_normalization._all_latest()")
    arms: dict = {}
    pre: dict = {}
    for a in ARMS:
        t = time.time()
        ts = build(snaps, rows, Transform(a), canon)
        arms[a] = read_arm(ts, vm_rows, xfv.keys())
        pre[a] = pre_ba_points(ts)
        del ts
        log(f"arm {a}: built ({round(time.time() - t, 1)} s)")
    dev_keys = {c["key"] for fid in FRAMES for c in scored[fid]}
    p3 = p3_check(pre, dev_keys)
    if p3["dev_points_moved"]:
        raise RuntimeError(f"P3 failed: {p3['dev_points_moved']} points before the first BA "
                           "board of development players moved between arms")
    log(f"P3: no development player's point before {FIRST_BA_DATE} moves; other moved points: "
        f"{p3['other_points_moved']}")
    del pre
    reached_keys = arms["S"]["reach"]
    p4_rows = [k for k in arms["S"]["vm"] if arms["S"]["vm"][k] != arms["R"]["vm"][k]]
    if p4_rows:
        raise RuntimeError(f"P4 failed: R differs from S on {len(p4_rows)} development rows")
    out_of_season = sorted({k[1] for k in reached_keys if k[1] != DEV_BA_SEASON})
    if out_of_season:
        raise RuntimeError(f"BA reaches development years {out_of_season}; the registration "
                           "names 2023 only")
    vals = {a: arms[a]["vm"] for a in ARMS}
    srows = stat_rows(scored, vals)
    eq = [abs(r["v"]["S"] - r["stored"]) <= 1e-9 for r in srows
          if r["fid"] == "vm_dev" and r["v"]["S"] is not None]
    diffs = [abs(r["v"]["S"] - r["stored"]) for r in srows
             if r["fid"] == "vm_dev" and r["v"]["S"] is not None]
    p2 = {"vm_dev_rows": len(eq), "equal_within_1e9": int(sum(eq)),
          "largest_abs_difference": _r(max(diffs) if diffs else None, 6),
          "missing_in_rebuild": sum(1 for r in srows if r["fid"] == "vm_dev" and r["v"]["S"] is None)}
    log(f"P2: arm S equals the frames' stored consensus on {p2['equal_within_1e9']} of "
        f"{p2['vm_dev_rows']} vm_dev rows (largest difference {p2['largest_abs_difference']})")
    units = ba_units(snaps)
    prim = primary(srows)
    reach_n = {s: sum(1 for k in reached_keys if k[0] == s) for s in ("hit", "pit")}
    doc: dict = {
        "task": TASK, "document": DOC, "registration_sha": sha,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": MCS._label(), "frames_guards": guards,
        "parity": {"P1": True, "P2": p2, "P3": p3, "P4": True},
        "reach": {"rows": len(reached_keys), "by_side": reach_n,
                  "primary_scope_rows": len(prim),
                  "primary_scope_by_side": {s: sum(1 for r in prim if r["side"] == s)
                                            for s in ("hit", "pit")},
                  "ba_units_2023": len(units)},
        "arms": ARM_LABEL, "crosswalks": OLD_LADDER,
    }
    if check_only:
        doc["check_only"] = True
        log(f"check done ({round(time.time() - t0, 1)} s); no outcome was read")
        return doc
    # --- the read ---------------------------------------------------------------
    rng = np.random.default_rng(PERM_SEED)
    vm23 = [c for c in vm_rows if int(c["year"]) == DEV_BA_SEASON]
    n1: list[float] = []
    n2: list[float] = []
    for k in range(int(null_k)):
        t = time.time()
        ts = build(snaps, rows, Transform("R", raw_over=permute_within_role(units, "raw", rng)),
                   canon)
        v = read_arm(ts, vm23, ())["vm"]
        del ts
        rr = stat_rows({"lv_dev": [], "vm_dev": vm23}, {"S": vals["S"], "X": vals["X"], "N": v})
        n1.append(delta(rr, "N", "X", B=0, seed=seed)["delta"])
        ts = build(snaps, rows, Transform("R", pen_over=permute_within_role(units, "pen", rng)),
                   canon)
        v = read_arm(ts, vm23, ())["vm"]
        del ts
        rr = stat_rows({"lv_dev": [], "vm_dev": vm23}, {"S": vals["S"], "R": vals["R"], "N": v})
        n2.append(delta(rr, "N", "R", B=0, seed=seed)["delta"])
        if k % 10 == 0 or k == null_k - 1:
            log(f"null draw {k + 1}/{null_k} ({round(time.time() - t, 1)} s)")
    # planted
    reached = [r for r in prim if (r["side"], r["year"], r["key"]) in reached_keys]
    pl1 = planted(units, reached, "raw", high_first=True)
    pl2 = planted(units, reached, "pen", high_first=False)
    ts = build(snaps, rows, Transform("R", raw_over=pl1), canon)
    v_pl1 = read_arm(ts, vm23, ())["vm"]
    ts = build(snaps, rows, Transform("R", pen_over=pl2), canon)
    v_pl2 = read_arm(ts, vm23, ())["vm"]
    del ts
    vals_all = dict(vals, PL1={**vals["S"], **v_pl1}, PL2={**vals["S"], **v_pl2})
    srows = stat_rows(scored, vals_all)
    prim = primary(srows)
    d_pl1 = delta(prim, "PL1", "X", B=B, seed=seed)
    d_pl2 = delta(prim, "PL2", "R", B=B, seed=seed)
    pl1_ok = plant_passes(d_pl1, n1, PL1_QUANTILE, absolute=False)
    pl2_ok = plant_passes(d_pl2, n2, PL2_QUANTILE, absolute=True)
    log(f"PL1 {pl1_ok}  PL2 {pl2_ok}")
    comps = {"C1": ("R", "X", n1, False, pl1_ok["passes"]),
             "C2": ("A", "X", n1, False, pl1_ok["passes"]),
             "C3": ("A", "R", n2, True, pl2_ok["passes"]),
             "C4": ("A2", "R", n2, True, pl2_ok["passes"])}
    read: dict = {}
    for name, (a, b, null, two, pok) in comps.items():
        d = delta(prim, a, b, B=B, seed=seed)
        p = p_null(d.get("delta"), null, two_sided=two)
        blk = {"a": a, "b": b, "within": {k: d.get(k) for k in
                                          ("a", "b", "delta", "ci95", "sd", "mde95", "p_gt_0",
                                           "n", "n_clusters", "groups_kept", "B_used", "status")},
               "secondary": {}, "per_side": {}, "context_all_dev_rows": {}}
        blk.update(resolves(d, p, pok))
        for st in ("pooled", "auc"):
            ds = delta(prim, a, b, B=B, seed=seed, statistic=st)
            blk["secondary"][st] = {k: ds.get(k) for k in ("a", "b", "delta", "ci95", "status")}
        for side in ("hit", "pit"):
            ds = delta([r for r in prim if r["side"] == side], a, b, B=B, seed=seed)
            blk["per_side"][side] = {k: ds.get(k) for k in ("a", "b", "delta", "ci95", "n",
                                                            "status")}
        dc = delta(srows, a, b, B=B, seed=seed)
        blk["context_all_dev_rows"] = {k: dc.get(k) for k in ("a", "b", "delta", "ci95", "n",
                                                              "status")}
        read[name] = blk
        log(f"{name} {a}-{b}: within {d.get('delta')} CI95 {d.get('ci95')} p_null {p} "
            f"-> {blk['reading']}")
    doc["read"] = read
    doc["recommendation"] = recommendation(read["C1"], read["C2"], read["C3"])
    doc["nulls"] = {
        "K": int(null_k), "seed": PERM_SEED,
        "N1_minus_X": {"mean": _r(np.mean(n1)), "sd": _r(np.std(n1, ddof=1)),
                       "p2_5": _r(np.quantile(n1, 0.025)), "p95": _r(np.quantile(n1, 0.95)),
                       "p97_5": _r(np.quantile(n1, 0.975))},
        "N2_minus_R": {"mean": _r(np.mean(n2)), "sd": _r(np.std(n2, ddof=1)),
                       "abs_p95": _r(np.quantile(np.abs(n2), 0.95)),
                       "abs_p97_5": _r(np.quantile(np.abs(n2), 0.975))},
        "N1_draws": [_r(x) for x in n1], "N2_draws": [_r(x) for x in n2]}
    doc["planted"] = {"PL1": pl1_ok, "PL2": pl2_ok,
                      "PL1_units": len(pl1), "PL2_units": len(pl2)}
    doc["arms_within"] = {"primary_scope": {a: within_of(prim, a) for a in ARMS},
                          "vm_dev": {a: within_of([r for r in srows if r["fid"] == "vm_dev"], a)
                                     for a in ARMS},
                          "lv_dev_served": within_of([r for r in srows if r["fid"] == "lv_dev"],
                                                     "S"),
                          "vm_dev_frames_stored": within_of(
                              [dict(r, v={"S": r["stored"]}) for r in srows
                               if r["fid"] == "vm_dev"], "S")}
    # --- board effect (outcome-free) -------------------------------------------
    base = arms["S"]["board"]
    doc["board_effect"] = {a: board_effect(arms[a]["board"], base, side_of)
                           for a in ARMS if a != "S"}
    jordan = "dylan_jordan"
    doc["example"] = {"player": jordan,
                      "consensus_fv_raw": {a: _r((arms[a]["board"].get(jordan) or (None,))[0], 3)
                                           for a in ARMS},
                      "served_consensus_fv": (xfv.get(jordan) or {}).get("consensus_fv"),
                      "served_efv": (xfv.get(jordan) or {}).get("xfv_grade")}
    doc["ba_vs_outlets_2026"] = outlet_correlations(rows, canon)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def outlet_correlations(rows: list[tuple], canon) -> dict:
    """On the 2026 cycle (latest grade per player and source), Pearson correlation of BA's
    stored and raw grade with FanGraphs and MLB Pipeline, by role. Outcome-free."""
    stored = latest_table(rows, Transform("S"), canon)
    raw = latest_table(rows, Transform("R"), canon)
    out = {}
    for role in ("hitter", "pitcher"):
        s_ = stored.get((role, 2026), {})
        r_ = raw.get((role, 2026), {})
        blk = {}
        for ref in ("fangraphs", "mlb_pipeline"):
            ks = [k for k, d in s_.items() if BA in d and ref in d and BA in r_.get(k, {})]
            if len(ks) < 3:
                continue
            a = np.array([s_[k][BA] for k in ks])
            b = np.array([r_[k][BA] for k in ks])
            f = np.array([s_[k][ref] for k in ks])
            blk[ref] = {"n": len(ks), "stored": round(float(np.corrcoef(a, f)[0, 1]), 3),
                        "raw": round(float(np.corrcoef(b, f)[0, 1]), 3)}
        out[role] = blk
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="parity checks only; no outcome read")
    g.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--null-k", type=int, default=NULL_K)
    ap.add_argument("--out", default=str(ARTIFACT))
    a = ap.parse_args(argv)
    doc = run(check_only=a.check, null_k=a.null_k)
    if a.run:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(json.dumps({k: doc[k] for k in ("parity", "reach")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
