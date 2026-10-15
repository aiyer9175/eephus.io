# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV on the 2026 season: the one holdout read (docs/efv-v2/EFV_2026_HOLDOUT.md).

Owner decision EW3-13 (2026-10-15, TEST ONCE, THEN TRAIN) under the waiver EW3-5. The
registration was committed alone before this module existed; this module is its method and
nothing else. It scores six raters, every one frozen at the 2026 opening day (CUTOFF), on
the 2026 regular season:

    F-2026-LIST    the preseason 2026 lists: efv_vintage_frame.frame_row at V 2026 with the
                   window [2026-01-01, 2026-03-26), MiLB at the served floor (primary)
    F-2026-DEBUT   the 2025 debut class's 2026 season and the 2026 debut class's first
                   season, graded at the latest board point in [2025-01-01, 2026-03-26)
                   (secondary; conditions on reaching the majors)

    raters         eFV v5 COMBINED (served) and eFV V2 and eFV v1, each refit on a training
                   pool whose labels stop at the 2025 season (truncated_matrix), v5's
                   candidate columns read by efv5_combined.live_columns as of CUTOFF;
                   PROSPX consensus; MLB Pipeline and FanGraphs (latest point per source)
    labels         R2026 (arrival only), WAR2026 on the frozen fWAR label, the rate per
                   600 PA / 150 IP for debutants, MiLB2026 through the surrogate guard only
    statistic      within-side Spearman and AUC, rater minus consensus on identical rows,
                   paired percentile bootstrap B 4000 seed 20261021, player-clustered and
                   club-clustered; one-sided 95 percent bounds
    pass rule      served eFV minus consensus, WAR2026, pooled sides of F-2026-LIST: the
                   one-sided 95 percent lower bound above 0 under BOTH clusterings

ONE READ. run() refuses while data/efv_2026_holdout.json exists. The R-VM cohorts (2025
and 2026 debuts) are opened through efv_vintage_frame.guard_vm_request on the committed
gate sha only; source_backtest.CANDIDATE_YEARS and efv_model.SCORED_YEARS are never
widened. Nothing served moves: the read writes its artifact, a per-row lab file (not
shipped) and one row of data/efv_progress.json in the holdout_2026 frame, which the served
claim never reads.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are side, list year and
debut class. Nothing here groups, counts or averages rows by consensus-FV level.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import efv_dataset as D
import efv_vintage_frame as F
import source_backtest as SB

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv2026"
OUT_PATH = DATA_DIR / "efv_2026_holdout.json"
ROWS_PATH = LAB_DIR / "efv_2026_holdout_rows.json"
LEDGER_PATH = ROOT / ".cache" / "efv_2026_holdout" / "progress_ledger.jsonl"
DOC = "docs/efv-v2/EFV_2026_HOLDOUT.md"
RESULTS_DOC = "docs/efv-v2/EFV_2026_HOLDOUT_RESULTS.md"
TOOL = "efv_2026_holdout.py"
ITEM = "EFV_2026_HOLDOUT_READ"

#: The 2026 opening day: every rater input is dated on or before it.
CUTOFF = "2026-03-25"
#: The exclusive end of every board window (CUTOFF plus one day).
WINDOW_END = "2026-03-26"
LIST_YEAR = 2026
SEASON = 2026
LIST_WINDOW = ("2026-01-01", WINDOW_END)
DEBUT_WINDOW = ("2025-01-01", WINDOW_END)
DEBUT_CLASSES = (2025, 2026)
#: The input cut of the injured-list and MiLB reads (the list year's start).
INPUT_CUT = "2026-01-01"
#: The training labels stop at this season (no 2026 data in any fit).
TRAIN_RESOLVED_THROUGH = 2025
#: The frozen label the read must use.
LABEL_VINTAGE_ID = "2026-10-02-0341299c20ec"
#: The committed REGISTERED gate (docs/efv-v2/EFV_V2_GATE.md) that opens the R-VM cohorts.
GATE_SHA = "e7931ce4e13110eebb53555bff455ff13ca7c502"
B = 4000
SEED = 20261021
MIN_GROUP_ROWS = 20
CLUSTERINGS = ("player", "club")
UNKNOWN_CLUB = "UNK"
CONSENSUS = "prospx_consensus"
SOURCES = ("mlb_pipeline", "fangraphs")
SERVED = "efv_v5_combined"
EFV_RATERS = (SERVED, "efv_v2", "efv_v1")
RATERS = EFV_RATERS + (CONSENSUS,) + SOURCES
#: The progress-ledger frame and role (registered in efv_progress.FRAMES).
PROGRESS_FRAME = "holdout_2026"
PROGRESS_ROLE = "holdout_2026"
VERDICTS = ("beats", "ties", "trails")
#: Rate denominators (the secondary label).
RATE_PA = 600.0
RATE_IP = 150.0
SIDES = F.SIDES


def _quiet(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# the one-read guard
# ---------------------------------------------------------------------------

class AlreadyRead(RuntimeError):
    """The holdout has been read; the frame is spent."""


def guard_one_read(path: Path | None = None) -> None:
    p = OUT_PATH if path is None else Path(path)
    if p.exists():
        raise AlreadyRead(f"{p.name} exists: the 2026 holdout was read once and is spent "
                          f"({DOC} s9)")


# ---------------------------------------------------------------------------
# board reads (no outcome)
# ---------------------------------------------------------------------------

def _day(p: dict) -> str:
    return str(p.get("snapshot_date") or "")[:10]


def window_points(points, lo: str, hi: str) -> list[dict]:
    """Board points dated in [lo, hi), oldest first."""
    pts = [p for p in points or () if p.get("snapshot_date") and lo <= _day(p) < hi]
    return sorted(pts, key=_day)


def source_grades(points, lo: str, hi: str) -> dict:
    """{source: grade} for MLB Pipeline and FanGraphs, each read on the latest point in
    [lo, hi) that carries a grade of that source (the largest when two points share that
    date), and the consensus of the latest point in the window (consensus_fv_raw, else
    consensus_fv). A source with no grade in the window is absent."""
    pts = window_points(points, lo, hi)
    out: dict = {}
    for src in SOURCES:
        best, vals = None, []
        for p in pts:
            v = ((p.get("per_source") or {}).get(src) or {}).get("fv_published")
            if v is None:
                continue
            d = _day(p)
            if best is None or d > best:
                best, vals = d, [float(v)]
            elif d == best:
                vals.append(float(v))
        if vals:
            out[src] = max(vals)
    if pts:
        c = pts[-1].get("consensus_fv_raw", pts[-1].get("consensus_fv"))
        if c is not None:
            out[CONSENSUS] = float(c)
    return out


def club_of(point: dict | None) -> str:
    code = str((point or {}).get("org") or "").strip().upper()
    return code or UNKNOWN_CLUB


@contextlib.contextmanager
def _window_end(mmdd: str):
    """source_backtest's preseason window end, for frame_row's window (in process only)."""
    old = SB._WINDOW_END_MMDD
    SB._WINDOW_END_MMDD = mmdd
    try:
        yield
    finally:
        SB._WINDOW_END_MMDD = old


def _decorate(row: dict, rec: dict, lo: str, hi: str) -> dict | None:
    """The as-of point, club, constant-anchor flag and the latest-per-source grades."""
    pts = window_points(rec.get("points"), lo, hi)
    if not pts:
        return None
    asof = pts[-1]
    g = source_grades(rec.get("points"), lo, hi)
    row["board_window"] = [lo, hi]
    row["asof_point_date"] = _day(asof)
    row["club"] = club_of(asof)
    row["constant_only"] = bool(D._anchor_is_constant_only(asof))
    row["scores_board"] = g
    return row


def build_list_frame(side: str, universe: dict, index) -> tuple[list[dict], dict]:
    """F-2026-LIST for one side: efv_vintage_frame.frame_row at V 2026 with the window
    [2026-01-01, 2026-03-26) and the served MiLB floor, plus the sidecars."""
    F.guard_score_request(LIST_YEAR, purpose="2026 holdout frame")
    non_rater, constant = F._real_sources()
    excl = frozenset(non_rater | constant)
    rows, acct = [], {"frame_rows": 0, "no_consensus": 0, "constant_only": 0}
    with _window_end(WINDOW_END[4:]):
        for rec in universe.values():
            r = F.frame_row(rec, side, LIST_YEAR, excl=excl, milb=True, index=index,
                            milb_floor=D.MILB_FLOOR_DEFAULT)
            if r is None:
                continue
            acct["frame_rows"] += 1
            r = _decorate(r, rec, r["window"][0], r["window"][1])
            if r is None or r["scores_board"].get(CONSENSUS) is None:
                acct["no_consensus"] += 1
                continue
            if r["constant_only"]:
                acct["constant_only"] += 1
                continue
            r["frame"] = "list"
            r["group"] = f"{side}|{LIST_YEAR}"
            rows.append(r)
    rows.sort(key=lambda r: r["player_key"])
    F._attach_sidecars(rows)
    acct["rows"] = len(rows)
    return rows, acct


def debut_row(rec: dict, side: str, cls: int, index, excl: frozenset) -> dict | None:
    """The F-2026-DEBUT row of one record (None when he is not in the frame): a real grader
    published inside [2025-01-01, 2026-03-26), the as-of point is the latest point there,
    inputs keyed on the outcome-blind id through 2025, MiLB through 2025."""
    if not D._side_match(rec, side):
        return None
    lo, hi = DEBUT_WINDOW
    pts = window_points(rec.get("points"), lo, hi)
    if not pts:
        return None
    real = set()
    for p in pts:
        for s, ps in (p.get("per_source") or {}).items():
            if not F._is_real_grader(s, ps, excl):
                continue
            sd = str((ps or {}).get("snapshot_date") or p["snapshot_date"])[:10]
            if lo <= sd < hi:
                real.add(s)
    if not real:
        return None
    asof = pts[-1]
    ident = _idmod().resolve_record(rec, LIST_YEAR, index, side)
    row = {"player_key": rec.get("player_key"), "mlbam_id": ident.person_id,
           "id_how": ident.how, "id_candidates": ident.n_candidates,
           "record_mlbam_id": rec.get("mlbam_id"), "side": side, "vintage": LIST_YEAR,
           "window": [INPUT_CUT, WINDOW_END], "debut_class": int(cls),
           "birth_date": rec.get("birth_date"), "position": rec.get("position"),
           "real_sources": sorted(real), "asof_date": _day(asof),
           "prior": D._prior_features(rec, asof, side), "milb_floor": D.MILB_FLOOR_DEFAULT}
    feats = D._milb_features(ident.person_id, LIST_YEAR, rec.get("birth_date"), side,
                             cutoff=INPUT_CUT, first_season_floor=D.MILB_FLOOR_DEFAULT)
    row["milb"] = feats
    row["milb_last_season"] = (feats or {}).get("milb_season")
    return _decorate(row, rec, lo, hi)


def _idmod():
    import efv_identity
    return efv_identity


def build_debut_frame(side: str, universe: dict, index, classes: dict) -> tuple[list[dict], dict]:
    """F-2026-DEBUT for one side; `classes` is {player_key: effective debut year}."""
    non_rater, constant = F._real_sources()
    excl = frozenset(non_rater | constant)
    rows, acct = [], {"candidates": 0, "no_board": 0, "no_consensus": 0, "constant_only": 0}
    for pk, cls in sorted(classes.items()):
        rec = universe.get(pk)
        if rec is None or not D._side_match(rec, side):
            continue
        acct["candidates"] += 1
        r = debut_row(rec, side, cls, index, excl)
        if r is None:
            acct["no_board"] += 1
            continue
        if r["scores_board"].get(CONSENSUS) is None:
            acct["no_consensus"] += 1
            continue
        if r["constant_only"]:
            acct["constant_only"] += 1
            continue
        r["frame"] = "debut"
        r["group"] = f"{side}|{cls}"
        rows.append(r)
    F._attach_sidecars(rows)
    acct["rows"] = len(rows)
    return rows, acct


# ---------------------------------------------------------------------------
# labels (the only outcome reads)
# ---------------------------------------------------------------------------

def label_vintage() -> dict:
    import fwar_vintage as FV
    blob = FV.load()
    vid = blob.get("vintage_id")
    if vid != LABEL_VINTAGE_ID:
        raise RuntimeError(f"the frozen label is {vid!r}, not {LABEL_VINTAGE_ID!r}")
    if SEASON not in FV.fwar_seasons(blob):
        raise RuntimeError(f"season {SEASON} is not frozen in the label vintage")
    return blob


def season_war(blob: dict, season: int = SEASON) -> dict[int, float]:
    """{mlbam: hitting war + pitching war} at one frozen season."""
    import fwar_vintage as FV
    out: dict[int, float] = {}
    for g in FV.GROUPS:
        for mid, w in FV.war_by_group(blob, season, g).items():
            out[mid] = out.get(mid, 0.0) + w
    return out


def _ip(v) -> float:
    s = str(v or "0")
    if "." in s:
        whole, frac = s.split(".", 1)
        return float(int(whole or 0)) + int((frac or "0")[:1]) / 3.0
    return float(s)


def mlb_exposure(season: int = SEASON) -> dict[str, dict[int, float]]:
    """{"hit": {mlbam: PA}, "pit": {mlbam: IP}} over the sport-1 regular-season lines."""
    import milb_history as mh
    out = {"hit": {}, "pit": {}}
    for r in mh.season_splits(1, season, "hitting", fetch=False):
        if r.get("mlbam"):
            m = int(r["mlbam"])
            out["hit"][m] = out["hit"].get(m, 0.0) + float(r.get("pa") or 0)
    for r in mh.season_splits(1, season, "pitching", fetch=False):
        if r.get("mlbam"):
            m = int(r["mlbam"])
            out["pit"][m] = out["pit"].get(m, 0.0) + _ip(r.get("ip"))
    return out


def _rid(rec: dict) -> int | None:
    try:
        return int(rec.get("mlbam_id")) if rec.get("mlbam_id") else None
    except (TypeError, ValueError):
        return None


def label_row(rec: dict, seasons: dict | None, war26: dict[int, float], expo: dict,
              side: str, frame: str) -> dict:
    """R2026, WAR2026 and the rate for one row (see the registration, s5)."""
    import efv_labels as L
    dy, _ld, status = L.effective_debut(rec, seasons)
    out = {"status": status, "debut_year": dy, "r2026": None, "war2026": None,
           "rate": None, "war_row": None, "exposure": None}
    if status == "identity_conflict":
        return out
    if frame == "list" and status == "ok" and dy is not None and dy < SEASON:
        out["status"] = "identity_conflict"
        return out
    reached = status == "ok" and dy == SEASON
    out["r2026"] = 1 if reached else 0
    rid = _rid(rec)
    if frame == "list" and not reached:
        out["war2026"] = 0.0
        return out
    w = war26.get(rid) if rid is not None else None
    if w is None and (seasons or {}).get(SEASON) is not None:
        w = float(seasons[SEASON])
    out["war_row"] = w is not None
    out["war2026"] = float(w) if w is not None else 0.0
    ex = expo[side].get(rid) if rid is not None else None
    out["exposure"] = ex
    if ex:
        out["rate"] = out["war2026"] / ex * (RATE_PA if side == "hit" else RATE_IP)
    return out


def debut_classes(universe: dict, war: dict) -> dict[str, int]:
    """{player_key: effective debut year} for the 2025 and 2026 classes (status ok). Opens
    the R-VM cohorts through the committed gate sha only."""
    import efv_labels as L
    F.guard_vm_request(DEBUT_CLASSES, gate_sha=GATE_SHA, purpose="2026 holdout debut classes")
    out = {}
    for pk, rec in universe.items():
        dy, _ld, status = L.effective_debut(rec, war.get(pk))
        if status == "ok" and dy in DEBUT_CLASSES:
            out[pk] = int(dy)
    return out


def milb2026_attempt(rows_by_side: dict) -> dict:
    """MiLB2026 through efv_surrogate's public path and its guard only. Returns the outcome
    rows, or the guard's refusal verbatim (the registration, s5)."""
    import efv_surrogate as S
    import efv_surrogate_guard as G
    sha = _git(["log", "-1", "--format=%H", "--", "docs/efv-v2/SURROGATE_2026_GATE.md"])
    try:
        out = {}
        for side, rows in rows_by_side.items():
            out[side] = S.build_outcomes(side, LIST_YEAR, rows, gate_sha=sha,
                                         look_records=G.look_records(),
                                         purpose="lv2026_surrogate")
        return {"status": "read", "rows": out}
    except Exception as e:                                         # noqa: BLE001
        return {"status": "refused", "error": type(e).__name__, "message": str(e),
                "gate_sha_tried": sha}


# ---------------------------------------------------------------------------
# the training pool with no 2026 data
# ---------------------------------------------------------------------------

def career_war_seasons() -> dict[str, dict[int, float]]:
    """{player_key: {season: war}} from the career_war table, read as efv_dataset.build_matrix
    reads it (the series the matrix labels were summed from)."""
    import storage
    out = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                payload = json.loads(r["payload_json"]) or {}
            except ValueError:
                continue
            seasons, _fb = D._label_seasons(payload)
            out[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    return out


@contextlib.contextmanager
def _resolved_through(rt: int):
    old = D.RESOLVED_THROUGH
    D.RESOLVED_THROUGH = int(rt)
    try:
        yield
    finally:
        D.RESOLVED_THROUGH = old


_LABEL_FIELDS = ("target_resolved", "target_censored", "censored", "weight",
                 "observed_seasons")


def relabel(rows: list[dict], cw: dict, term: dict, *, rt: int, term_cap: str) -> tuple[list[dict], dict]:
    """The matrix rows with every debuted row of a debut year before `rt` relabelled at
    RESOLVED_THROUGH `rt` (efv_dataset._label_6yr on the same career_war seasons), a
    career-terminal transaction resolving a row only when dated on or before `term_cap`,
    and a recent-bust row whose terminal transaction falls after `term_cap` restored to its
    recent-bust state. Rows of later debut years and busts are otherwise untouched."""
    acct = {"relabelled": 0, "no_seasons": 0, "terminal_resolved": 0,
            "terminal_after_cap": 0, "bust_recent_restored": 0, "changed": 0}
    out = []
    with _resolved_through(rt):
        for r0 in rows:
            r = dict(r0)
            if r.get("kind") == "debuted" and r.get("debut_year") is not None \
                    and int(r["debut_year"]) < int(rt):
                s = cw.get(r["player_key"])
                if not s:
                    acct["no_seasons"] += 1
                    out.append(r)
                    continue
                t_res, t_cens, cflag, w, n = D._label_6yr(s, int(r["debut_year"]), None)
                r.update(target_resolved=t_res, target_censored=t_cens, censored=cflag,
                         weight=w, observed_seasons=n)
                r.pop("terminal_resolved", None)
                td = term.get(r["player_key"])
                if td and cflag and D._terminal_resolves(td):
                    if str(td)[:10] <= term_cap:
                        r.update(target_censored=t_res, censored=False, weight=1.0,
                                 observed_seasons=D.TARGET_SEASONS, terminal_resolved=td)
                        acct["terminal_resolved"] += 1
                    else:
                        acct["terminal_after_cap"] += 1
                acct["relabelled"] += 1
            elif r.get("kind") == "bust" and r.get("terminal_resolved") \
                    and str(r["terminal_resolved"])[:10] > term_cap:
                r["bust_recent"] = True
                r["weight"] = 0.5
                r.pop("terminal_resolved", None)
                acct["bust_recent_restored"] += 1
            if any(r.get(k) != r0.get(k) for k in _LABEL_FIELDS + ("bust_recent",)):
                acct["changed"] += 1
            out.append(r)
    return out, acct


def truncated_matrix(side: str, *, cw: dict, drop_keys=frozenset()) -> tuple[list[dict], dict]:
    """The side's matrix with labels stopped at TRAIN_RESOLVED_THROUGH (the registration,
    s4.1), after the reproduction check at the matrix's own RESOLVED_THROUGH, with every
    player in `drop_keys` left out."""
    rows = json.loads(D.matrix_path(side).read_text(encoding="utf-8"))
    term = D._load_terminal_dates({r["player_key"] for r in rows if r.get("player_key")})
    same, chk = relabel(rows, cw, term, rt=int(D.RESOLVED_THROUGH), term_cap="9999-12-31")
    mism = sum(1 for a, b in zip(rows, same)
               if any(a.get(k) != b.get(k) for k in _LABEL_FIELDS))
    out, acct = relabel(rows, cw, term, rt=TRAIN_RESOLVED_THROUGH, term_cap=CUTOFF)
    kept = [r for r in out if r.get("player_key") not in drop_keys]
    acct.update(rows=len(rows), dropped_in_frame=len(out) - len(kept),
                reproduction_rt=int(D.RESOLVED_THROUGH), reproduction_mismatches=mism,
                reproduction_no_seasons=chk["no_seasons"])
    return kept, acct


def late_first_debuts(universe: dict, war: dict) -> int:
    """Players who left the lists by 2023 and first reached the majors in 2026: busts as of
    the cutoff with no row in the matrices (disclosed in s4.1, not repaired)."""
    import efv_labels as L
    n = 0
    for pk, rec in universe.items():
        last = max((_day(p)[:4] for p in rec.get("points") or () if _day(p)), default="")
        if not last or last > "2023":
            continue
        dy, _ld, status = L.effective_debut(rec, war.get(pk))
        if status == "ok" and dy == SEASON:
            n += 1
    return n


@contextlib.contextmanager
def matrix_paths(paths: dict[str, Path]):
    """efv_dataset.matrix_path (and every loaded module's imported copy) points at `paths`
    for the life of the block."""
    orig = D.matrix_path

    def patched(side: str = "hit"):
        return Path(paths[side])
    swapped = [m for m in list(sys.modules.values())
               if m is not None and getattr(m, "matrix_path", None) is orig]
    for m in swapped:
        m.matrix_path = patched
    try:
        yield
    finally:
        for m in swapped:
            m.matrix_path = orig


# ---------------------------------------------------------------------------
# the raters
# ---------------------------------------------------------------------------

def model_rows(rows: list[dict], side: str, panel) -> list[dict]:
    """Frame rows as live-board V2 rows (efv_v2_serve.live_rows' shape): v1's feature view
    of the as-of row, BMI as of the as-of point, decision year 2026."""
    import efv_drivers as DRV
    import efv_model as V1
    import efv_v2_model as H
    out = []
    for r in rows:
        feats = V1._vec(H.lv_model_row(r), side)
        extra = {"bmi": DRV.bmi_asof(r["player_key"], r.get("asof_date"), panel)}
        out.append({"player_key": r["player_key"], "decision_year": LIST_YEAR,
                    "fv": float(r["scores_board"][CONSENSUS]), "feats": feats,
                    "extra": extra, "v2": H.v2_row(feats, extra), "frame": "live",
                    "has_milb": bool(r.get("milb")), "mlbam_id": r.get("mlbam_id"),
                    "asof_date": r.get("asof_date")})
    return out


def score_group(side: str, rows: list[dict], models: dict, *, exclude_ids, panel,
                receipts: dict, tag: str) -> dict[str, dict[str, float]]:
    """{player_key: {rater: score}} for the eFV raters on one group of frame rows (one
    side, one list year or debut class): v5 COMBINED's order index with its candidate
    columns as of CUTOFF (the call efv_v2_serve.score_live makes), V2's order index, v1's
    blend."""
    import efv5_combined as V5C
    import efv_v2_model as H
    mrows = model_rows(rows, side, panel)
    rec: dict = {}
    raw = {r["player_key"]: {"asof_date": r.get("asof_date"), "mlbam_id": r.get("mlbam_id")}
           for r in mrows}
    cols = V5C.live_columns(side, mrows, today=CUTOFF, raw_by_key=raw,
                            exclude_ids=exclude_ids, receipt=rec, log=_quiet)
    v5rows = V5C.attach(mrows, side, cols, V5C.LIVE_KIND)
    group = int(rows[0]["group"].split("|")[1])
    for x in v5rows + mrows:
        x["decision_year"] = group
    p5 = H.predict_v2(models[SERVED], v5rows)
    alt = V5C.predict_combined(models[SERVED], v5rows)
    p2 = H.predict_v2(models["efv_v2"], mrows)
    v1 = models["efv_v1"](mrows)
    out = {}
    for r, a, b, c in zip(mrows, p5, p2, v1):
        out[r["player_key"]] = {SERVED: a["order_idx"], "efv_v2": b["order_idx"],
                                "efv_v1": float(c), "efv_v5_grade": a["efv_grade"]}
    fams = {f: {k: v for k, v in n.items() if k in ("status", "reason")}
            for f, n in (rec.get("families") or {}).items()}
    receipts[tag] = {"rows": len(rows), "families": fams,
                     "withheld": rec.get("withheld"), "clipped": rec.get("clipped"),
                     "predict_v2_vs_predict_combined_max_abs":
                         round(float(max((abs(a["order_idx"] - b["order_idx"])
                                          for a, b in zip(p5, alt)), default=0.0)), 9),
                     "rows_moved_by_candidates": int(sum(
                         1 for a, b in zip(p5, p2) if abs(a["order_idx"] - b["order_idx"]) > 1e-12))}
    return out


def fit_models(side: str, *, drop_keys) -> dict:
    """The three eFV fits on the truncated pool (called inside matrix_paths)."""
    import efv5_combined as V5C
    import efv_v2_model as H
    w = H.load_weights()
    m5 = V5C.production_fit(side, weights=w, log=_quiet)
    train2 = [r for r in H.matrix_training_rows(side)
              if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
    m2 = H.fit_v2(train2, side, frame="vm", weights=w)
    train1 = [r for r in H.training_rows(side)
              if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
    v1 = H.v1_fold_scorer(train1, side)
    if v1 is None:
        raise RuntimeError(f"{side}: v1 could not fit on the truncated pool")
    if any(r["player_key"] in drop_keys for r in train2 + train1):
        raise RuntimeError(f"{side}: a frame player is in a training pool")
    return {SERVED: m5, "efv_v2": m2, "efv_v1": v1,
            "_receipt": {"n_train_v5": m5.get("n_train"), "n_train_v2": len(train2),
                         "n_train_v1": len(train1),
                         "train_years": sorted({int(r["decision_year"]) for r in train2}),
                         "v5_lambda": (m5.get("config") or {}).get("lam"),
                         "w_skill": {"v5": m5.get("w_skill"), "v2": m2.get("w_skill")},
                         "w_time": {"v5": m5.get("w_time"), "v2": m2.get("w_time")}}}


# ---------------------------------------------------------------------------
# the statistic
# ---------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    return SB._ranks_np(np, a)


def _rho(a: np.ndarray, y: np.ndarray) -> float | None:
    if a.size < 3:
        return None
    return SB._corr_np(np, _rank(a), _rank(y))


def _auc(a: np.ndarray, y: np.ndarray) -> float | None:
    return SB._auc_np(np, a, y.astype(bool))


STATS = {"spearman": _rho, "auc": _auc}


def kept_groups(codes: np.ndarray, mask: np.ndarray, scope) -> list[str]:
    """Groups with at least MIN_GROUP_ROWS rows of the leg, inside the scope (None: all)."""
    u, c = np.unique(codes[mask], return_counts=True)
    keep = [str(g) for g, n in zip(u, c) if n >= MIN_GROUP_ROWS]
    if scope is not None:
        keep = [g for g in keep if g.startswith(scope) or g.endswith(scope)]
    return keep


def within_pair(stat, a, b, y, codes, keep, idx) -> tuple[float | None, float | None]:
    """Paired size-weighted within statistic over the kept groups on rows idx (a group
    counts only when both raters have a value there)."""
    f = STATS[stat]
    gc = codes[idx]
    ta = tb = 0.0
    n = 0
    for g in keep:
        m = idx[gc == g]
        if m.size < 3:
            continue
        ra, rb = f(a[m], y[m]), f(b[m], y[m])
        if ra is None or rb is None:
            continue
        ta += ra * m.size
        tb += rb * m.size
        n += m.size
    if not n:
        return None, None
    return ta / n, tb / n


def cluster_draws(keys, *, B_: int, seed: int) -> list[np.ndarray]:
    """B_ cluster-resampled row index sets (source_backtest's resampler)."""
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(seed)
    return [SB._cluster_draw(np, rng, order, starts, lens) for _ in range(int(B_))]


def interval(diffs: list[float]) -> dict:
    if len(diffs) < 50:
        return {"status": "not derived: too few usable draws", "B_used": len(diffs)}
    d = np.asarray(diffs, dtype=np.float64)
    q = np.quantile(d, [0.025, 0.05, 0.95, 0.975])
    return {"lb95": round(float(q[1]), 4), "ub95": round(float(q[2]), 4),
            "ci95": [round(float(q[0]), 4), round(float(q[3]), 4)],
            "sd": round(float(d.std(ddof=1)), 5), "p_gt_0": round(float((d > 0).mean()), 4),
            "B_used": len(diffs), "status": "derived"}


def verdict(leg: dict) -> str:
    """beats / trails / ties on one delta leg (the registration, s7)."""
    try:
        lbs = [float(leg[c]["lb95"]) for c in CLUSTERINGS]
        ubs = [float(leg[c]["ub95"]) for c in CLUSTERINGS]
    except (KeyError, TypeError):
        return "ties"
    if all(v > 0 for v in lbs):
        return "beats"
    if all(v < 0 for v in ubs):
        return "trails"
    return "ties"


def run_legs(rows: list[dict], legs: list[dict], *, B_: int = B, seed: int = SEED,
             log=print) -> dict:
    """Every leg's point values and its paired intervals under both clusterings; all legs
    read the same draws. A leg: {name, stat, a, b, label, scope, mask}."""
    n = len(rows)
    codes = np.asarray([r["group"] for r in rows])
    out = {}
    prepared = []
    for lg in legs:
        a = np.asarray([np.nan if r["scores"].get(lg["a"]) is None else r["scores"][lg["a"]]
                        for r in rows], dtype=np.float64)
        b = np.asarray([np.nan if r["scores"].get(lg["b"]) is None else r["scores"][lg["b"]]
                        for r in rows], dtype=np.float64)
        y = np.asarray([np.nan if r["labels"].get(lg["label"]) is None
                        else r["labels"][lg["label"]] for r in rows], dtype=np.float64)
        mask = np.isfinite(a) & np.isfinite(b) & np.isfinite(y)
        if lg.get("subset") is not None:
            mask &= np.asarray([bool(lg["subset"](r)) for r in rows])
        keep = kept_groups(codes, mask, lg.get("scope"))
        full = np.nonzero(mask)[0]
        pa, pb = within_pair(lg["stat"], a, b, y, codes, keep, full)
        res = {"stat": lg["stat"], "label": lg["label"], "a_rater": lg["a"],
               "b_rater": lg["b"], "scope": lg.get("scope") or "pooled",
               "set": lg.get("set", "all"), "n": int(sum(int((codes[full] == g).sum())
                                                         for g in keep)),
               "groups": keep,
               "n_by_group": {g: int((codes[full] == g).sum()) for g in keep},
               "a": None if pa is None else round(pa, 5),
               "b": None if pb is None else round(pb, 5),
               "delta": None if (pa is None or pb is None) else round(pa - pb, 5)}
        out[lg["name"]] = res
        prepared.append((lg, a, b, y, mask, keep, res))
    for cl in CLUSTERINGS:
        keys = [r["player_key"] if cl == "player" else r["club"] for r in rows]
        t0 = time.time()
        draws = cluster_draws(keys, B_=B_, seed=seed)
        diffs = {lg["name"]: [] for lg in legs}
        for idx in draws:
            for lg, a, b, y, mask, keep, res in prepared:
                if res["delta"] is None:
                    continue
                sub = idx[mask[idx]]
                if sub.size < 8:
                    continue
                xa, xb = within_pair(lg["stat"], a, b, y, codes, keep, sub)
                if xa is not None and xb is not None:
                    diffs[lg["name"]].append(xa - xb)
        for name, d in diffs.items():
            out[name][cl] = interval(d) if out[name]["delta"] is not None else {
                "status": "not derived: undefined point"}
        log(f"  {cl}-clustered: {len(draws)} draws over {n} rows, "
            f"{len(set(keys))} clusters ({round(time.time() - t0, 1)} s)")
    return out


def own_values(rows: list[dict], label: str, stat: str) -> dict:
    """Every rater's own within value on its own rows (point only), by side and pooled."""
    codes = np.asarray([r["group"] for r in rows])
    out = {}
    for rater in RATERS:
        s = np.asarray([np.nan if r["scores"].get(rater) is None else r["scores"][rater]
                        for r in rows], dtype=np.float64)
        y = np.asarray([np.nan if r["labels"].get(label) is None else r["labels"][label]
                        for r in rows], dtype=np.float64)
        mask = np.isfinite(s) & np.isfinite(y)
        keep = kept_groups(codes, mask, None)
        full = np.nonzero(mask)[0]
        v, _ = within_pair(stat, s, s, y, codes, keep, full)
        per = {}
        for g in keep:
            m = full[codes[full] == g]
            r_ = STATS[stat](s[m], y[m])
            per[g] = {"n": int(m.size), stat: None if r_ is None else round(r_, 4)}
        out[rater] = {"n": int(mask.sum()), stat: None if v is None else round(v, 4),
                      "by_group": per}
    return out


def legs_for(frame: str) -> list[dict]:
    """The registered legs (s6): every eFV rater against consensus on all rows, v5 against
    V2, each source against consensus on its own rows, and all five against consensus on
    the common set; by scope (pooled, then each side)."""
    legs = []

    def have(src):
        def f(r):
            return r["scores"].get(src) is not None
        return f

    def common(r):
        return all(r["scores"].get(s) is not None for s in SOURCES)
    scopes = (None, "hit", "pit")
    labels = (("war2026", "spearman"), ("r2026", "auc"), ("rate", "spearman")) \
        if frame == "list" else (("war2026", "spearman"),)
    if frame == "debut":
        scopes = (None, "hit", "pit", "2025", "2026")
    for label, stat in labels:
        for sc in scopes:
            tag = f"{label}|{stat}|{sc or 'pooled'}"
            for rater in EFV_RATERS:
                legs.append({"name": f"{tag}|{rater}-consensus", "stat": stat, "a": rater,
                             "b": CONSENSUS, "label": label, "scope": sc})
            legs.append({"name": f"{tag}|{SERVED}-efv_v2", "stat": stat, "a": SERVED,
                         "b": "efv_v2", "label": label, "scope": sc})
            for src in SOURCES:
                legs.append({"name": f"{tag}|{src}-consensus", "stat": stat, "a": src,
                             "b": CONSENSUS, "label": label, "scope": sc,
                             "subset": have(src), "set": f"{src} graded"})
        for rater in EFV_RATERS + SOURCES:
            legs.append({"name": f"{label}|{stat}|pooled|common|{rater}-consensus",
                         "stat": stat, "a": rater, "b": CONSENSUS, "label": label,
                         "scope": None, "subset": common, "set": "common"})
    return legs


PASS_LEG = f"war2026|spearman|pooled|{SERVED}-consensus"


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _git(args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode().strip() or None if r.returncode == 0 else None


def _round_scores(sc: dict) -> dict:
    return {k: (None if v is None else round(float(v), 6)) for k, v in sc.items()}


def build(*, log=print) -> dict:
    """Frames, fits, scores and labels. No statistic is computed here."""
    import efv_drivers as DRV
    import efv_identity as IDM
    import efv_labels as L
    t0 = time.time()
    blob = label_vintage()
    universe = F.load_universe()
    index = IDM.build_index(LIST_YEAR - 1)
    seasons_tab = L.war_seasons_table()
    classes = debut_classes(universe, seasons_tab)
    frames: dict = {"list": {}, "debut": {}}
    acct: dict = {"list": {}, "debut": {}}
    for side in SIDES:
        frames["list"][side], acct["list"][side] = build_list_frame(side, universe, index)
        frames["debut"][side], acct["debut"][side] = build_debut_frame(side, universe, index,
                                                                        classes)
        log(f"  frames {side}: list {acct['list'][side]['rows']}, "
            f"debut {acct['debut'][side]['rows']} ({round(time.time() - t0, 1)} s)")
    in_frame = {r["player_key"] for fr in frames.values() for rows in fr.values() for r in rows}
    excl_ids = sorted({int(r["mlbam_id"]) for fr in frames.values() for rows in fr.values()
                       for r in rows if r.get("mlbam_id")})
    cw = career_war_seasons()
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    paths, trunc = {}, {}
    for side in SIDES:
        rows, a = truncated_matrix(side, cw=cw, drop_keys=frozenset(in_frame))
        p = LAB_DIR / f"train_matrix_{side}_rt{TRAIN_RESOLVED_THROUGH}.json"
        p.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        paths[side], trunc[side] = p, a
        log(f"  truncated pool {side}: {a}")
    trunc["late_first_debuts_2026"] = late_first_debuts(universe, seasons_tab)
    panel = DRV.load_bio_panel()
    scores: dict = {}
    receipts: dict = {"live_columns": {}, "fits": {}}
    with matrix_paths(paths):
        for side in SIDES:
            models = fit_models(side, drop_keys=frozenset(in_frame))
            receipts["fits"][side] = models.pop("_receipt")
            log(f"  fits {side}: {receipts['fits'][side]} ({round(time.time() - t0, 1)} s)")
            groups: dict = {}
            for fr in ("list", "debut"):
                for r in frames[fr][side]:
                    groups.setdefault((fr, r["group"]), []).append(r)
            for (fr, g), rows in sorted(groups.items()):
                got = score_group(side, rows, models, exclude_ids=excl_ids, panel=panel,
                                  receipts=receipts["live_columns"], tag=f"{fr}|{g}")
                for r in rows:
                    sc = dict(r["scores_board"])
                    sc.update(got[r["player_key"]])
                    scores[(fr, side, r["player_key"])] = sc
                log(f"  scored {fr} {g}: {len(rows)} ({round(time.time() - t0, 1)} s)")
    war26 = season_war(blob)
    expo = mlb_exposure()
    out_rows = {"list": [], "debut": []}
    lab_acct: dict = {}
    for fr in ("list", "debut"):
        for side in SIDES:
            for r in frames[fr][side]:
                rec = universe[r["player_key"]]
                lab = label_row(rec, seasons_tab.get(r["player_key"]), war26, expo, side, fr)
                a = lab_acct.setdefault(f"{fr}|{side}", {"rows": 0, "identity_conflict": 0,
                                                          "r2026": 0, "war_row_missing": 0,
                                                          "rate_rows": 0})
                a["rows"] += 1
                if lab["status"] == "identity_conflict":
                    a["identity_conflict"] += 1
                if lab["r2026"]:
                    a["r2026"] += 1
                if lab["war_row"] is False and (lab["r2026"] or fr == "debut"):
                    a["war_row_missing"] += 1
                if lab["rate"] is not None:
                    a["rate_rows"] += 1
                labels = {"r2026": lab["r2026"], "war2026": lab["war2026"],
                          "rate": lab["rate"] if (fr == "debut" or lab["r2026"]) else None}
                if lab["status"] == "identity_conflict":
                    labels = {"r2026": None, "war2026": None, "rate": None}
                out_rows[fr].append({
                    "player_key": r["player_key"], "side": side, "group": r["group"],
                    "club": r["club"], "asof_point_date": r["asof_point_date"],
                    "mlbam_id": r.get("mlbam_id"), "record_mlbam_id": r.get("record_mlbam_id"),
                    "id_how": r.get("id_how"), "debut_class": r.get("debut_class"),
                    "label_status": lab["status"], "debut_year": lab["debut_year"],
                    "exposure": lab["exposure"],
                    "scores": _round_scores(scores[(fr, side, r["player_key"])]),
                    "labels": labels})
    rec_ids = {"list": {}, "debut": {}}
    for fr in ("list", "debut"):
        for side in SIDES:
            rows = frames[fr][side]
            rec_ids[fr][side] = {
                "rows": len(rows),
                "outcome_blind_id": sum(1 for r in rows if r.get("mlbam_id")),
                "record_id": sum(1 for r in rows if r.get("record_mlbam_id")),
                "agree": sum(1 for r in rows if r.get("mlbam_id") and r.get("record_mlbam_id")
                             and int(r["mlbam_id"]) == int(r["record_mlbam_id"]))}
    milb = milb2026_attempt({s: frames["list"][s] for s in SIDES})
    return {"rows": out_rows, "accounting": acct, "label_accounting": lab_acct,
            "identity": rec_ids, "training": trunc, "receipts": receipts,
            "milb2026": {k: v for k, v in milb.items() if k != "rows"},
            "label": {"vintage_id": blob.get("vintage_id"), "season": SEASON,
                      "provider": "fwar"},
            "excluded_ids_population_fit": len(excl_ids), "seconds_build": round(time.time() - t0, 1)}


def statistics(built: dict, *, B_: int = B, seed: int = SEED, log=print) -> dict:
    frames = {}
    for fr in ("list", "debut"):
        rows = [r for r in built["rows"][fr]]
        log(f" statistics on {fr}: {len(rows)} rows")
        legs = run_legs(rows, legs_for(fr), B_=B_, seed=seed, log=log)
        own = {"war2026": own_values(rows, "war2026", "spearman")}
        if fr == "list":
            own["r2026"] = own_values(rows, "r2026", "auc")
            own["rate"] = own_values(rows, "rate", "spearman")
        frames[fr] = {"n": len(rows),
                      "n_by_side": {s: sum(1 for r in rows if r["side"] == s) for s in SIDES},
                      "legs": legs, "own": own}
    leg = frames["list"]["legs"][PASS_LEG]
    word = verdict(leg)
    return {"frames": frames, "pass_leg": PASS_LEG, "verdict": word,
            "pass": word == "beats"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_doc(built: dict, stats: dict, *, B_: int, seed: int) -> dict:
    return {"item": ITEM, "tool": TOOL, "registration": DOC, "generated_at": _now(),
            "code": {"commit": _git(["rev-parse", "--short=8", "HEAD"])},
            "owner": ("EW3-13 (2026-10-15): test once on the 2026 season, then train; "
                      "EW3-5 waiver; R-VM opened on the committed gate sha"),
            "gate_sha": GATE_SHA, "cutoff": CUTOFF, "label": built["label"],
            "train_resolved_through": TRAIN_RESOLVED_THROUGH,
            "bootstrap": {"B": int(B_), "seed": int(seed), "clusterings": list(CLUSTERINGS),
                          "intervals": ("percentile; lb95/ub95 one-sided 95 percent, ci95 "
                                        "two-sided"),
                          "min_group_rows": MIN_GROUP_ROWS},
            "pass_rule": ("served eFV v5 COMBINED minus PROSPX consensus, within-side "
                          "Spearman on WAR2026, pooled sides of F-2026-LIST: one-sided 95 "
                          "percent lower bound above 0 under both clusterings"),
            "pass_leg": stats["pass_leg"], "verdict": stats["verdict"], "pass": stats["pass"],
            "frames": stats["frames"],
            "accounting": built["accounting"], "label_accounting": built["label_accounting"],
            "identity": built["identity"], "training": built["training"],
            "receipts": built["receipts"], "milb2026": built["milb2026"],
            "excluded_ids_population_fit": built["excluded_ids_population_fit"],
            "seconds_build": built["seconds_build"],
            "spent": ("F-2026-LIST and F-2026-DEBUT are SPENT by this read: no later model "
                      "is claimed on the 2026-season outcomes of these rows")}


def ledger_row(doc: dict, *, artifact: Path, now_iso: str) -> dict:
    """The one holdout_2026 row of data/efv_progress.json: the WAR2026 within-side
    Spearman legs of F-2026-LIST, copied from the artifact (nothing computed here)."""
    import efv_progress as P
    fr = doc["frames"]["list"]
    legs = fr["legs"]
    raters = {}
    names = (("efv", SERVED), ("efv_v2_base", "efv_v2"), ("efv_v1", "efv_v1"),
             ("prospx_consensus", CONSENSUS), ("mlb_pipeline", "mlb_pipeline"),
             ("fangraphs", "fangraphs"))
    for name, rater in names:
        o = (fr["own"]["war2026"].get(rater) or {})
        raters[name] = {"spearman": o.get("spearman"), "auc": None, "n": o.get("n")}

    def leg(key):
        lg = legs[key]
        p = lg.get("player") or {}
        c = lg.get("club") or {}
        return {"delta": lg.get("delta"), "ci95": p.get("ci95"),
                "mde95": None if p.get("sd") is None else round(SB._Z95 * p["sd"], 4),
                "mde95_estimator": "percentile bootstrap, player-clustered",
                "ci95_estimator": (f"percentile bootstrap, paired, player-clustered, B {B}, "
                                   f"seed {SEED}"),
                "lb95_player": p.get("lb95"), "lb95_club": c.get("lb95"),
                "ci95_club": c.get("ci95"), "resolvable": None,
                "reading": f"2026 holdout, read once; verdict word {verdict(lg)}",
                "key": f"frames.list.legs.{key}"}
    base = "war2026|spearman|pooled"
    deltas = {"vs_prospx_consensus": {"spearman": leg(f"{base}|{SERVED}-consensus")},
              "vs_efv_v2_base": {"spearman": leg(f"{base}|{SERVED}-efv_v2")}}
    arr = legs[f"r2026|auc|pooled|{SERVED}-consensus"]
    src = [{"path": P._rel(Path(artifact)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(artifact))}]
    pl = legs[PASS_LEG]
    note = (f"Read once on 2026-10-15 (owner EW3-13): preseason 2026 lists frozen at the "
            f"2026-03-25 opening day, scored on 2026 regular-season fWAR; eFV refit on labels "
            f"through 2025. One-sided 95 percent lower bound of eFV minus consensus: "
            f"{(pl.get('player') or {}).get('lb95')} player-clustered, "
            f"{(pl.get('club') or {}).get('lb95')} club-clustered. Arrival read (R2026 AUC, "
            f"tilted, not value): eFV minus consensus {arr.get('delta')}. Spent: no later "
            f"model is claimed on this frame.")
    row = {"run_id": None, "date": doc["generated_at"][:10], "trigger": "look",
           "model_id": SERVED,
           "model_version": {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
                             "label": f"fwar@{doc['label']['vintage_id']}",
                             "resolved_through": TRAIN_RESOLVED_THROUGH, "provider": "fwar"},
           "frame": PROGRESS_FRAME, "frame_version": "f2026_list", "role": PROGRESS_ROLE,
           "tilted": False, "window": [LIST_YEAR, SEASON], "n": fr["n"],
           "n_by_side": fr["n_by_side"], "raters": raters, "deltas": deltas,
           "resolvable": None, "verdict": doc["verdict"], "share": None, "sources": src,
           "note": note, "last_verified_at": now_iso,
           "statistic": "within-side Spearman on WAR2026, size-weighted"}
    P._finish(row)
    row["run_id"] = f"{doc['generated_at']}|{PROGRESS_FRAME}|{row['content_hash'][:8]}"
    return row


def append_ledger(doc: dict, *, artifact: Path, ledger_path: Path | None = None) -> dict:
    import efv_progress as P
    if P.FRAMES.get(PROGRESS_FRAME, {}).get("role") != PROGRESS_ROLE:
        raise RuntimeError(f"{PROGRESS_FRAME} is not registered in efv_progress.FRAMES")
    now_iso = P._now_iso()
    row = ledger_row(doc, artifact=artifact, now_iso=now_iso)
    led = LEDGER_PATH if ledger_path is None else Path(ledger_path)
    led.parent.mkdir(parents=True, exist_ok=True)
    return P.commit_rows([row], data_dir=P.DATA_DIR, ledger_path=led,
                         sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)


def run(*, B_: int = B, seed: int = SEED, log=print, ledger: bool = True) -> dict:
    guard_one_read()
    if F.reserved_vm_pins():
        raise RuntimeError(f"R-VM pins violated: {F.reserved_vm_pins()}")
    built = build(log=log)
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROWS_PATH.write_text(json.dumps({"generated_at": _now(), "cutoff": CUTOFF,
                                     "rows": built["rows"]}, indent=0) + "\n",
                         encoding="utf-8")
    stats = statistics(built, B_=B_, seed=seed, log=log)
    doc = make_doc(built, stats, B_=B_, seed=seed)
    OUT_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    if ledger:
        doc["_ledger"] = append_ledger(doc, artifact=OUT_PATH)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="store_true", help="the one read")
    ap.add_argument("--B", type=int, default=B)
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 2
    doc = run(B_=a.B)
    leg = doc["frames"]["list"]["legs"][PASS_LEG]
    print(json.dumps({"verdict": doc["verdict"], "pass_leg": {k: leg.get(k) for k in
                      ("a", "b", "delta", "n", "player", "club")}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
