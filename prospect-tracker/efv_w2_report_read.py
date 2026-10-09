# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4 item 3, the read half (EFV4_REPORT_LLM_EXTRACTION; owner decisions EW2-8 to
EW2-12, 2026-10-08: new sources only, chosen on the development frames, read once more
on the spent reserved frames, labelled as such, choosing nothing).

WHAT THIS READS. The twelve structured fields the extractor read off each redacted,
as-of scouting report (efv_w2_report_llm.py builds the corpus, the store and the
columns; this module never calls a model and never sees a document's text), as 22
one-column arms: each field column of each side offered to one V2 head under V2's own
DS-06 admission rule inside every fold.

THE HEADS (leakage protocol step 6). txt_arrival and txt_role_floor go to the timing
head. Every other field is a grade-side column: it goes to the skill head of a side
only when report_absent (the row has no corpus document) reads BALANCED under the DS-03
probe on the FROZEN fWAR label, on the text vintages (2013 on) of the lv_dev training
rows; otherwise to the timing head. resolve_heads() runs that probe before any arm is
read; it reads no field.

THE CONTROLS, before any arm.
  (a) Test-retest and redaction agreement (efv_w2_report_llm.control_receipt): no
      outcome.
  (b) Name-redaction invariance (protocol step 3): on the 300 invariance documents, the
      partial correlation of each field with the outcome (the within-(side, V) W3
      percentile on the frozen label) given u_c (a quadratic in the consensus percentile
      and side-by-vintage effects), with the names redacted and with the names left in,
      on the same rows. A field is WITHHELD (its arms are not read) when the names-in
      point lies outside the redacted reading's CI95, or when the paired difference
      between the two runs has a CI95 that excludes zero (player-clustered bootstrap;
      DEFAULT: the research text's "must not differ beyond its interval between the
      two runs" read as either test, the stricter of the two).
  (c) The shuffled-document twin (protocol step 4): every arm's full-frame twin (the
      column permuted across players inside each vintage, the screening lab's twin)
      must read inside the head's floor; the floors are the registered wave-1 run's
      (data/xfv_screen_wave1.json, the same lv_dev frame and frozen label, checked).

THE READS. Development (the choice): lv_dev through the screening lab's own Frame and
measure_arm, and vm_dev at vm2 through tools/efv_v3_backtest's development Inputs (base
parity asserted there), each against the V2 base and PROSPX consensus with E_cond CI95.
Spent (EW2-10): R-LV and R-VM through efv_v3_backtest.build_reserved on the gate sha
the 10-08 confirmation read used; every block carries SPENT_NOTE, chooses and tunes
nothing, and lands no progress-ledger row.

AS OF. A list-vintage row reads its own in-window document dated on or before its list
date. A debut-cohort row (vm), and a list row of a later vintage (the spent R-LV),
CARRY the player's latest development-vintage value whose document date is on or before
the row's own read date (efv_w2_report_llm.carried_value); no document of a reserved
vintage exists or is built. A row with no value is None and the fit imputes the fold's
observed training mean.

BANS. No served number moves: nothing served imports this module and no flag exists.
Nothing groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md); u_c enters only as a continuous control. No model call
and no network.

Run:  python efv_w2_report_read.py --controls   (control receipts, no arm)
      python efv_w2_report_read.py --read       (controls, development and spent reads)
      python efv_w2_report_read.py --ledger     (this module's development ledger rows)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import efv_vintage_frame as F
import efv_w2_report_llm as R

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "_labs" / "efv_w2" / "efv_w2_report_llm.json"
CONFIRM_PATH = DATA_DIR / "_labs" / "efv_v3" / "efv_v3_confirm.json"
WAVE1_PATH = DATA_DIR / "xfv_screen_wave1.json"
TOOL = "efv_w2_report_read.py"
ITEM = R.ITEM
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"
FROZEN_PROVIDER = "fwar"
SPENT_NOTE = "spent frame, read after the 10-08 confirmation"
NOTE = ("eFV v4 (EFV4_REPORT_LLM_EXTRACTION), development read only: selects and "
        "adjudicates nothing")
#: Bootstrap draws and seed of the invariance control.
B_CONTROL = 2000
SEED_CONTROL = 20261008


def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _key(arm: dict) -> str:
    import efv_v2_model as H
    return f"{H.V2_SCREEN_PREFIX}{arm['name']}"


# ---------------------------------------------------------------------------
# the store, read once per run
# ---------------------------------------------------------------------------

class Store:
    """The manifest, the extraction store and the extractor id, read once."""

    def __init__(self, manifest: dict | None = None, store: list[dict] | None = None):
        self.manifest = R.load_manifest() if manifest is None else manifest
        self.rows = R.read_store() if store is None else store
        self.model_id = R.store_model_id(self.rows)
        self._lv: dict = {}

    def lv(self, side: str, frames: dict) -> dict:
        """efv_w2_report_llm.lv_values on the development frames, memoised by side."""
        key = (side, id(frames))
        if key not in self._lv:
            rec: dict = {}
            vals = R.lv_values(side, frames, manifest_rows=self.manifest["rows"],
                               store=self.rows, model_id=self.model_id, receipt=rec)
            self._lv[key] = (vals, rec)
        return self._lv[key][0]

    def lv_receipt(self, side: str, frames: dict) -> dict:
        self.lv(side, frames)
        return self._lv[(side, id(frames))][1]


def arm_values(store: Store, arm: dict, frames: dict) -> dict:
    """{(V, player_key): value | None} of one arm on its side's lv frame rows."""
    col = arm["field_column"]
    out = {}
    for slot, v in store.lv(arm["side"], frames).items():
        x = None if v is None else v.get(col)
        out[slot] = None if x is None else float(x)
    return out


# ---------------------------------------------------------------------------
# heads (protocol step 6) and the invariance control (step 3)
# ---------------------------------------------------------------------------

def report_absent_probe(frame, store: Store, frames: dict) -> dict:
    """{side: DS-03 probe} of report_absent (no corpus document) on the lv_dev
    training rows of the text vintages, on the frame's (frozen) label."""
    _tools()
    import efv_screen_lab as LAB
    out = {}
    for side in F.SIDES:
        vals = store.lv(side, frames)
        rows = [r for r in frame.train[side]
                if int(r["decision_year"]) in R.CORPUS_VINTAGES]
        ind = {(int(r["decision_year"]), r["player_key"]):
               (1.0 if vals.get((int(r["decision_year"]), r["player_key"])) is None else 0.0)
               for r in rows}
        out[side] = LAB.balance_probe(SimpleNamespace(train={side: rows}), side, ind,
                                      seed=LAB._seed_for(f"balance:report_absent:{side}"))
        out[side]["vintages"] = [min(R.CORPUS_VINTAGES), max(R.CORPUS_VINTAGES)]
    return out


def resolve_heads(probe: dict, arms=R.ARMS) -> list[dict]:
    """The arms with the head each is read in: the declared head, except that a
    skill-head column of a side whose report_absent probe is not BALANCED goes to the
    timing head."""
    out = []
    for a in arms:
        b = dict(a)
        v = (probe.get(a["side"]) or {}).get("verdict")
        if a["head"] == "skill" and v != "BALANCED":
            b["head"] = "timing"
            b["head_note"] = f"report_absent reads {v} on the fWAR label: timing head"
        out.append(b)
    return out


def _resid(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ b


def _partial(x, y, X) -> float | None:
    rx, ry = _resid(X, x), _resid(X, y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def invariance_outcome(store: Store, frames: dict, *, B: int = B_CONTROL,
                       seed: int = SEED_CONTROL) -> dict:
    """The outcome side of the name-redaction invariance control on the 300
    invariance documents: per field, the partial correlation with the within-(side, V)
    W3 percentile given a quadratic in the consensus percentile and side-by-vintage
    effects, names redacted (the main extraction of the paired redacted document) and
    names left in (the control extraction), on the same rows, with player-clustered
    bootstrap CI95. A field is withheld when its names-in point is outside the redacted
    CI95 or the paired difference's CI95 excludes zero. writer_level stands for txt_writer_minus_stated (the same reading before
    the group gap); the injury enum is its 0/1 flag."""
    import efv_v2_model as H
    main = {r["doc_id"]: r["fields"] for r in store.rows if not r.get("control_id")
            and r["model_id"] == store.model_id and r["prompt_sha256"] == R.PROMPT_SHA}
    ctl = {r["control_id"]: r["fields"] for r in store.rows if r.get("control_id")
           and r["model_id"] == store.model_id and r["prompt_sha256"] == R.PROMPT_SHA}
    ypct, upct = {}, {}
    for side in F.SIDES:
        for V, (rows, labs) in (frames.get(side) or {}).items():
            V = int(V)
            if V not in R.CORPUS_VINTAGES:
                continue
            have = [(r["player_key"], float(lab["w3"]), float(r["grades"][R.CONSENSUS_KEY]))
                    for r, lab in zip(rows, labs) if lab.get("w3") is not None
                    and (r.get("grades") or {}).get(R.CONSENSUS_KEY) is not None]
            if not have:
                continue
            g = [0] * len(have)
            yp = H.within_pct([h[1] for h in have], g)
            up = H.within_pct([h[2] for h in have], g)
            for (pk, _w, _c), a, b in zip(have, yp, up):
                ypct[(side, V, pk)] = float(a)
                upct[(side, V, pk)] = float(b)
    recs = []
    for c in (store.manifest.get("controls") or {}).get("invariance") or ():
        k = (c["side"], int(c["vintage"]), c["player_key"])
        red, raw = main.get(c["paired_doc_id"]), ctl.get(c["control_id"])
        if k not in ypct or red is None or raw is None:
            continue
        recs.append({"key": k, "red": red, "raw": raw})
    out: dict = {"n_documents": len((store.manifest.get("controls") or {})
                                    .get("invariance") or ()),
                 "n_scored": len(recs), "B": B, "seed": seed,
                 "rule": ("withheld when the names-in partial lies outside the redacted "
                          "partial's CI95, or when the paired difference (names in minus "
                          "redacted) has a CI95 that excludes zero"), "fields": {}}
    if not recs:
        return out
    groups = sorted({f"{r['key'][0]}|{r['key'][1]}" for r in recs})
    rng_seed = seed
    for f in R.FIELD_ORDER:
        rows = [r for r in recs if R.field_value(f, r["red"].get(f)) is not None
                and R.field_value(f, r["raw"].get(f)) is not None]
        if len(rows) < 20:
            out["fields"][f] = {"n": len(rows), "withheld": False,
                                "reason": "too few rows to read"}
            continue
        y = np.array([ypct[r["key"]] for r in rows])
        u = np.array([upct[r["key"]] for r in rows])
        gs = [f"{r['key'][0]}|{r['key'][1]}" for r in rows]
        dummies = np.column_stack([[float(g == gg) for g in gs] for gg in groups[1:]]
                                  ) if len(groups) > 1 else np.zeros((len(rows), 0))
        X = np.column_stack([np.ones(len(rows)), u, u ** 2, dummies])
        xr = np.array([R.field_value(f, r["red"][f]) for r in rows])
        xn = np.array([R.field_value(f, r["raw"][f]) for r in rows])
        pr, pn = _partial(xr, y, X), _partial(xn, y, X)
        by: dict = {}
        for i, r in enumerate(rows):
            by.setdefault(r["key"][2], []).append(i)
        cl = [np.array(v) for _k, v in sorted(by.items())]
        rng = np.random.default_rng(rng_seed)
        dr, dd = [], []
        for _ in range(int(B)):
            pick = rng.integers(0, len(cl), len(cl))
            ix = np.concatenate([cl[j] for j in pick])
            a, b = _partial(xr[ix], y[ix], X[ix]), _partial(xn[ix], y[ix], X[ix])
            if a is None or b is None:
                continue
            dr.append(a)
            dd.append(b - a)
        blk = {"n": len(rows), "partial_redacted": None if pr is None else round(pr, 4),
               "partial_names_in": None if pn is None else round(pn, 4)}
        if pr is None or pn is None or len(dr) < 2:
            blk.update({"withheld": False, "reason": "constant field on the control rows"})
        else:
            lo, hi = float(np.percentile(dr, 2.5)), float(np.percentile(dr, 97.5))
            dlo, dhi = float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))
            blk.update({"ci95_redacted": [round(lo, 4), round(hi, 4)],
                        "diff": round(pn - pr, 4), "diff_ci95": [round(dlo, 4),
                                                                 round(dhi, 4)],
                        "B_used": len(dr),
                        "names_in_outside_ci": bool(not lo <= pn <= hi),
                        "diff_ci_excludes_zero": bool(not dlo <= 0 <= dhi)})
            blk["withheld"] = blk["names_in_outside_ci"] or blk["diff_ci_excludes_zero"]
        out["fields"][f] = blk
    return out


def withheld_columns(inv: dict) -> set[str]:
    return {R.COLUMN_OF[f] for f, b in (inv.get("fields") or {}).items() if b.get("withheld")}


# ---------------------------------------------------------------------------
# lv_dev: the screening lab's own Frame and measure_arm
# ---------------------------------------------------------------------------

def wave1_floors(label_id: str, path: Path = WAVE1_PATH) -> dict:
    """The registered wave-1 run's floors (the same lv_dev frame), only when that run
    read the same frozen label."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    lab = (doc.get("label") or {}).get("id")
    if lab != label_id:
        raise RuntimeError(f"wave-1 floors were derived on {lab!r}, not {label_id!r}")
    return doc["floors"]


def _cand(arm: dict) -> dict:
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = (f"{arm['field_column']}: the extracted report field "
                   f"(efv_w2_report_llm, {arm['head']} head)")
    return out


def lv_read(arms, store: Store, frame, frames: dict, *, B: int, floors: dict,
            log=print) -> dict:
    """Every arm on lv_dev (list vintages 2017 to 2019) through the lab's Frame and
    measure_arm: DS-06 refit inside every fold with the column offered to the arm's
    head, the full-frame twin, the DS-03 probe on the column's missingness, the
    consensus leg, the wave-1 floors. No permutation null: a development read forms no
    verdict."""
    _tools()
    import efv_screen_lab as LAB
    base_vs_cons = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        base_vs_cons[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    out = {"frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                     "w_star_dev": frame.w_star, "label": frame.label},
           "floors_from": "data/xfv_screen_wave1.json (same frame and label)",
           "coverage": {s: store.lv_receipt(s, frames) for s in F.SIDES}, "arms": {}}
    for arm in arms:
        t1 = time.time()
        values = arm_values(store, arm, frames)
        a = LAB.measure_arm(frame, _cand(arm), values, floors, B=B, n_perm=0,
                            base_vs_cons=base_vs_cons)
        a.pop("_order", None)
        a.pop("permutation_null", None)
        a["tag"] = f"SCREEN-W{WAVE}:{arm['side']}.{arm['head']}.{arm['name']}"
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        if arm.get("head_note"):
            a["head_note"] = arm["head_note"]
        out["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv_dev {arm['name']} ({arm['head']}): admitted {a['admitted_folds']}/"
            f"{a['n_folds']}, vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus "
            f"{vc.get('delta')} {vc.get('ci95')}, twin {a['twin']['within'].get('delta')} "
            f"inside {a['twin'].get('inside_floor')} ({time.time() - t1:.0f} s)")
    return out


# ---------------------------------------------------------------------------
# the Inputs path (vm_dev, and the spent R-LV and R-VM frames)
# ---------------------------------------------------------------------------

COMPARISONS = (("candidate_vs_efv_v2_base", "efv_v3", "efv_v2"),
               ("candidate_vs_prospx_consensus", "efv_v3", "prospx_consensus"),
               ("efv_v2_base_vs_prospx_consensus", "efv_v2", "prospx_consensus"))
_RATER_NAMES = {"efv_v3": "efv_v2_candidate", "efv_v2": "efv_v2_base"}


@contextmanager
def registered_columns(arms):
    """The arms as efv_v3 W2_COLUMNS entries (their resolved heads) for one read;
    removed afterwards, so the v3 selection menu is never widened."""
    import efv_v3 as V3
    added = []
    for arm in arms:
        if arm["name"] in V3.W2_COLUMNS:
            continue
        V3.W2_COLUMNS[arm["name"]] = {"side": arm["side"], "head": arm["head"],
                                      "module": R.MODULE, "arg": arm["field_column"],
                                      "key": _key(arm)}
        added.append(arm["name"])
    try:
        yield
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


@contextmanager
def _frames_fixed(frames_lv: dict | None):
    _tools()
    import efv_v2_assemble as ASM
    orig = ASM.build_frames
    if frames_lv is not None:
        ASM.build_frames = lambda *a, **k: frames_lv
    try:
        yield
    finally:
        ASM.build_frames = orig


def frame_block(rows: list[dict], *, B: int, frame_version: str, note: str) -> dict:
    _tools()
    import efv_v2_stat as S
    import efv_v3_backtest as BT
    blk = BT.frame_block(rows, B=B, stats=("within", "pooled", "auc"),
                         comparisons=COMPARISONS, scopes=("both",))
    raters = {_RATER_NAMES.get(k, k): v for k, v in blk["raters"].items()}
    years = sorted({int(str(g).split("|")[1]) for g in blk["groups"]})
    deltas = blk["deltas"]
    return {"frame_version": frame_version,
            "window": [min(years), max(years)] if years else None,
            "n": blk["n"], "n_by_side": blk["n_by_side"], "n_players": blk["n_players"],
            "groups": blk["groups"], "statistic": S.STAT_LABEL[S.PRIMARY],
            "raters": raters, "deltas": deltas,
            "secondary": {"statistic": S.STAT_LABEL["pooled"],
                          "raters": {n: r.get("pooled") for n, r in raters.items()},
                          "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                         "ci95": (d.get("pooled") or {}).get("ci95"),
                                         "mde95": (d.get("pooled") or {}).get("mde95"),
                                         "reading": (d.get("pooled") or {}).get("reading")}
                                     for n, d in deltas.items()}},
            "verdict": None, "note": note}


def _vm_asof(side: str) -> tuple[dict, dict]:
    """(raw matrix rows by player_key, pinned preseason read date by player_key)."""
    import efv_v2_model as H
    raw = {r["player_key"]: r for r in json.loads(
        H._matrix_path(side).read_text(encoding="utf-8"))}
    mine: dict = {}
    H.pinned_inputs(side, H.matrix_training_rows(side), mine)
    return raw, {pk: rec.get("asof_date") for pk, rec in mine.items()}


def _cov_add(cov: dict, year: int, v) -> None:
    c = cov.setdefault(str(year), {"rows": 0, "with_value": 0})
    c["rows"] += 1
    c["with_value"] += int(v is not None)


def inputs_columns(inp, fid: str, kind: str, store: Store, frames_lv: dict, arms, *,
                   lv_rows: dict | None = None) -> tuple[dict, dict]:
    """({side: {arm name: {(year, player_key, train|test): value}}}, coverage) on one
    Inputs frame. Every value is a carry of the player's latest development-vintage
    value whose document date is on or before the row's read date: an lv row's list
    date (lv_rows {(side, V, player_key): frame row}; a development-vintage row reads
    its own vintage's document, the lv_dev rule), a vm training row's matrix asof_date,
    a vm test row's pinned preseason read."""
    cols: dict = {s: {} for s in F.SIDES}
    cov: dict = {s: {} for s in F.SIDES}
    for side in F.SIDES:
        lvv = store.lv(side, frames_lv)
        raw = pinned = None
        if kind == "vm":
            raw, pinned = _vm_asof(side)
        vals: dict = {}
        for fold, blk in inp.frames[fid]["by_side"][side].items():
            for part in ("train", "test"):
                for r in blk[part]:
                    y, pk = int(r["decision_year"]), r["player_key"]
                    if kind == "lv":
                        if y in R.CORPUS_VINTAGES or y < min(R.CORPUS_VINTAGES):
                            v = lvv.get((y, pk))
                        else:
                            fr = (lv_rows or {}).get((side, y, pk))
                            if fr is None:
                                raise KeyError(f"{fid} {side} {y} {pk}: no frame row")
                            v = R.carried_value(lvv, pk, fr.get("asof_date"))
                    else:
                        rw = raw.get(pk) or {}
                        asof = rw.get("asof_date") if part == "train" else pinned.get(pk)
                        v = R.carried_value(lvv, pk, asof)
                    vals[(y, pk, part)] = v
                    _cov_add(cov[side], y, v)
        for arm in arms:
            if arm["side"] == side:
                col = arm["field_column"]
                cols[side][arm["name"]] = {
                    k: (None if v is None or v.get(col) is None else float(v[col]))
                    for k, v in vals.items()}
    return cols, cov


def read_inputs_arm(inp, fid: str, arm: dict, *, B: int, frame_version: str,
                    note: str) -> dict:
    """One arm on one Inputs frame: the V2 base with the column offered to the arm's
    head under DS-06 in every fold, scored on the frame's rows."""
    import efv_v3 as V3
    cfg = V3.base_config()
    head = arm["head"]
    cfg["add"][arm["side"]][head].append(arm["name"])
    V3.validate_config(cfg)
    orders, _rec = inp.orders(fid, cfg, sides=(arm["side"],))
    rows = inp.rows_with(fid, orders, sides=(arm["side"],))
    key = _key(arm)
    folds = {}
    for fold in inp.frames[fid]["by_side"][arm["side"]]:
        m = inp.fold_fit(fid, arm["side"], fold, cfg)["model"]
        t = m.get(head) or {}
        adm = (t.get("admission") or {}).get(key) or {}
        beta = None
        if key in (t.get("keys") or []):
            beta = round(float(t["beta"][list(t["keys"]).index(key)]), 5)
        folds[str(fold)] = {"offered": m.get(head) is not None,
                            "admitted": key in (t.get("keys") or []),
                            "reason": adm.get("reason") or m.get("consensus_only_reason"),
                            "per_vintage_signs": adm.get("per_vintage_signs"),
                            "mean_abs_t": adm.get("mean_abs_t"), "beta_std": beta,
                            "head_keys": list(t.get("keys") or [])}
    return {"name": arm["name"], "side": arm["side"], "head": head, "folds": folds,
            "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
            "n_folds": len(folds),
            "frame": frame_block(rows, B=B, frame_version=frame_version, note=note)}


def _log_arm(log, label: str, a: dict, t1: float) -> None:
    d = a["frame"]["deltas"]
    w, vc = d["candidate_vs_efv_v2_base"]["spearman"], \
        d["candidate_vs_prospx_consensus"]["spearman"]
    log(f"  {label} {a['name']} ({a['head']}): admitted {a['admitted_folds']}/"
        f"{a['n_folds']}, vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus "
        f"{vc.get('delta')} {vc.get('ci95')} ({time.time() - t1:.0f} s)")


def vm_read(arms, store: Store, frames_lv: dict, *, B: int, log=print) -> dict:
    """Every arm on vm_dev (frame version vm2) through efv_v3_backtest's development
    Inputs: base parity with DS-16 and v3-at-base parity are asserted there."""
    _tools()
    import efv_v3_backtest as BT
    t0 = time.time()
    orig = BT.w2_values_dev
    BT.w2_values_dev = lambda inputs, fl, log=print: {fid: {s: {} for s in F.SIDES}
                                                       for fid in BT.FRAMES_DEV}
    try:
        with _frames_fixed(frames_lv):
            inp = BT.build_dev(log=log)
    finally:
        BT.w2_values_dev = orig
    years = sorted(int(y) for y in inp.frames["vm_dev"]["by_side"]["hit"])
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"vm_dev inputs built in {time.time() - t0:.0f} s")
    cols, cov = inputs_columns(inp, "vm_dev", "vm", store, frames_lv, arms)
    inp.cols = {"vm_dev": cols}
    out = {"frame": {"id": "vm_dev", "frame_version": "vm2", "fold_years": years,
                     "n_scored": len(inp.scored("vm_dev")),
                     "base_parity": inp.meta.get("base_parity", {}).get("reproduces"),
                     "v3_base_parity": inp.meta.get("v3_base_parity")},
           "coverage": cov, "arms": {},
           "carry_note": ("each row carries the player's latest development-vintage "
                          "report value dated on or before its read date")}
    with registered_columns(arms):
        for arm in arms:
            t1 = time.time()
            a = read_inputs_arm(inp, "vm_dev", arm, B=B, frame_version="vm2", note=NOTE)
            out["arms"][arm["name"]] = a
            _log_arm(log, "vm_dev", a, t1)
    return out


def gate_sha_from_confirm(path: Path = CONFIRM_PATH) -> str:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sha = (doc.get("gate") or {}).get("sha")
    if not F.gate_sha_committed(sha):
        raise F.ReservedFrameError(f"the confirmation artifact's gate sha {sha!r} is not "
                                   "the committed registration")
    return sha


def spent_read(arms, store: Store, frames_lv: dict, *, B: int, log=print) -> dict:
    """Every arm on the SPENT reserved frames through efv_v3_backtest.build_reserved on
    the confirmation's gate sha; v3-at-base parity is asserted first. Values are carries
    of development-vintage documents only. Labelled SPENT_NOTE; chooses nothing."""
    _tools()
    import efv_v3 as V3
    import efv_v3_backtest as BT
    gate_sha = gate_sha_from_confirm()
    t0 = time.time()
    with _frames_fixed(frames_lv):
        inp = BT.build_reserved(V3.base_config(), gate_sha=gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    log(f"spent inputs built in {time.time() - t0:.0f} s; v3 base parity {parity}")
    lv_rows = {}
    for side in F.SIDES:
        for V, blk in inp.frames["lv_res"]["by_side"][side].items():
            for pk, r in blk["frame_rows"].items():
                lv_rows[(side, int(V), pk)] = r
    cols_lv, cov_lv = inputs_columns(inp, "lv_res", "lv", store, frames_lv, arms,
                                     lv_rows=lv_rows)
    cols_vm, cov_vm = inputs_columns(inp, "vm_pros", "vm", store, frames_lv, arms)
    inp.cols = {"lv_res": cols_lv, "vm_pros": cols_vm}
    out = {"note": SPENT_NOTE, "gate_sha": gate_sha, "v3_base_parity": parity,
           "guards": inp.guards, "frames": {}}
    names = {"lv_res": ("R-LV", "lv1_v2", cov_lv), "vm_pros": ("R-VM", "vm2", cov_vm)}
    with registered_columns(arms):
        for fid, (label, fv, cov) in names.items():
            blk = {"frame": {"id": fid, "label": label, "frame_version": fv,
                             "folds": sorted(int(y) for y in
                                             inp.frames[fid]["by_side"]["hit"]),
                             "n_scored": len(inp.scored(fid)), "note": SPENT_NOTE},
                   "coverage": cov, "arms": {}}
            for arm in arms:
                t1 = time.time()
                a = read_inputs_arm(inp, fid, arm, B=B, frame_version=fv, note=SPENT_NOTE)
                blk["arms"][arm["name"]] = a
                _log_arm(log, f"{label} (spent)", a, t1)
            out["frames"][fid] = blk
    return out


# ---------------------------------------------------------------------------
# the artifact, the summary and the ledger rows
# ---------------------------------------------------------------------------

def _leg(blk: dict, comp: str) -> list:
    d = ((blk.get("deltas") or {}).get(comp) or {}).get("spearman") or {}
    return [d.get("delta"), d.get("ci95")]


def summary(doc: dict) -> list[dict]:
    """One line per arm: rows, admitted folds, within delta vs V2 and vs consensus
    with CI95 on every frame read. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "head": arm["head"],
               "column": arm["field_column"]}
        if arm.get("withheld"):
            row["withheld"] = arm["withheld"]
        blocks = [("lv_dev", (doc.get("lv_dev") or {}).get("arms")),
                  ("vm_dev", (doc.get("vm_dev") or {}).get("arms"))]
        for fid, b in ((doc.get("spent") or {}).get("frames") or {}).items():
            blocks.append((fid, b.get("arms")))
        for fid, arms in blocks:
            a = (arms or {}).get(n)
            if not a:
                continue
            row[fid] = {"n": a["frame"]["n"],
                        "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                        "vs_v2": _leg(a["frame"], "candidate_vs_efv_v2_base"),
                        "vs_consensus": _leg(a["frame"], "candidate_vs_prospx_consensus")}
            if fid == "lv_dev":
                row[fid]["twin_within"] = (a.get("twin") or {}).get("within", {}).get("delta")
                row[fid]["twin_inside_floor"] = (a.get("twin") or {}).get("inside_floor")
            if fid in ("lv_res", "vm_pros"):
                row[fid]["note"] = SPENT_NOTE
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, development frame) in the shape
    efv_progress.build_dev_rows reads. The spent frames land no row. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(arm["name"])
            if not a:
                continue
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{arm['name']}:{arm['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": {"wave": f"{WAVE} ({fid})", "exploratory": False,
                                      "development_only": True, "adjudicates": False,
                                      "selects": False, "head": arm["head"],
                                      "statistic_column": arm["field_column"],
                                      "admitted_folds": a["admitted_folds"],
                                      "n_folds": a["n_folds"]},
                        "frames": {fid: a["frame"]}})
    return out


def update_ledger(doc: dict | None = None, *, path: Path = OUT_PATH, ledger_path=None,
                  out_path=None, trigger: str = "efv_change") -> dict:
    """Append this module's development rows (and only them) to data/efv_progress.json
    through efv_progress.build_dev_rows and commit_rows. Idempotent."""
    import efv_progress as P
    doc = doc if doc is not None else json.loads(Path(path).read_text(encoding="utf-8"))
    now_dt = datetime.now(timezone.utc)
    now_iso = P._now_iso(now_dt)
    src = [{"path": P._rel(Path(path)), "generated_at": doc.get("generated_at"),
            "sha256": _sha(path)}]
    cands = []
    for d in ledger_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now_dt.date().isoformat(),
                                  trigger=trigger, now_iso=now_iso,
                                  frames=tuple(d["frames"]), raters=P.SCREEN_RATERS,
                                  deltas=P.SCREEN_DELTAS, statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no development rows"}
    res = P.commit_rows(cands, out_path=out_path, ledger_path=ledger_path,
                        sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def read(*, B: int | None = None, out: Path = OUT_PATH, spent: bool = True,
         log=print) -> dict:
    """Controls, then the development read of every unwithheld arm on lv_dev and
    vm_dev, then the spent read; writes the artifact."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    if L.provider() != FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not the frozen "
                           f"{FROZEN_PROVIDER!r}")
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    store = Store()
    frame, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s; extractor {store.model_id}")
    floors = wave1_floors(LAB.label_id())
    controls = R.control_receipt(store.manifest, store.rows, store.model_id)
    probe = report_absent_probe(frame, store, frames)
    log("report_absent on the fWAR label: " + ", ".join(
        f"{s} {probe[s].get('verdict')} {probe[s].get('partial')} {probe[s].get('ci95')}"
        for s in F.SIDES))
    inv = invariance_outcome(store, frames)
    withheld = withheld_columns(inv)
    log(f"invariance control: {inv['n_scored']} rows; withheld {sorted(withheld)}")
    arms = resolve_heads(probe)
    for a in arms:
        if a["field_column"] in withheld:
            a["withheld"] = "name-redaction invariance control (protocol step 3)"
    readable = [a for a in arms if not a.get("withheld")]
    doc = {"schema": 1, "item": ITEM,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": ("EW2-8 to EW2-12 (2026-10-08): new sources only; choose on "
                              "the development frames; the reserved frames are spent"),
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "builder_sha256": _sha(ROOT / "efv_w2_report_llm.py"),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "extraction": {"model_id": store.model_id, "prompt_sha256": R.PROMPT_SHA,
                          "store": "data/_labs/efv_w2/report_extract.jsonl",
                          "store_sha256": _sha(R.STORE_PATH), "store_rows": len(store.rows),
                          "manifest_sha256": _sha(R.MANIFEST_PATH),
                          "n_documents": store.manifest.get("n_documents"),
                          "n_row_documents": store.manifest.get("n_row_documents")},
           "controls": {"agreement": controls, "report_absent_fwar": probe,
                        "invariance_outcome": inv,
                        "twin": ("each arm's full-frame twin (column permuted across "
                                 "players inside each vintage) against the wave-1 "
                                 "floor of its head and side; see lv_dev arms")},
           "arms_declared": [{k: a.get(k) for k in ("name", "field_column", "side", "head",
                                                    "head_note", "withheld")}
                             for a in arms],
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "corpus_vintages": list(R.CORPUS_VINTAGES),
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False}}
    doc["lv_dev"] = lv_read(readable, store, frame, frames, B=B, floors=floors, log=log)
    doc["vm_dev"] = vm_read(readable, store, frames, B=B, log=log)
    if spent:
        doc["spent"] = spent_read(readable, store, frames, B=B, log=log)
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


def controls_only(*, log=print) -> dict:
    """The control receipts alone: agreement (no outcome), the report_absent probe and
    the invariance outcome control on the frozen label. No arm is read."""
    _tools()
    import efv_screen_lab as LAB
    store = Store()
    frame, frames = LAB.real_frame()
    return {"agreement": R.control_receipt(store.manifest, store.rows, store.model_id),
            "report_absent_fwar": report_absent_probe(frame, store, frames),
            "invariance_outcome": invariance_outcome(store, frames)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--controls", action="store_true", help="control receipts only")
    ap.add_argument("--read", action="store_true",
                    help="controls, development and spent reads; writes the artifact")
    ap.add_argument("--no-spent", action="store_true", help="skip the spent read")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args(argv)
    if not (a.controls or a.read or a.ledger):
        a.read = a.ledger = True

    def log(msg):
        print(msg, flush=True)
    if a.controls:
        log(json.dumps(controls_only(log=log), indent=1, default=str))
    if a.read:
        res = read(B=a.B, out=Path(a.out), spent=not a.no_spent, log=log)
        log(json.dumps(res["summary"], indent=1))
    if a.ledger:
        log(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                       indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
