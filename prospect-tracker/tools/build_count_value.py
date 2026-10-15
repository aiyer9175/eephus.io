#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_count_value - RE288, the count-state run value table (count_value_v1).

docs/ewar-2026-10-15/RE288_COUNT_VALUE_GATE.md. Reads, never writes:
  .cache/pbp_corpus/pitches/<Y>, events/<Y>, plays/<Y>   (the corpus)
  .cache/pbp_runners/plays/<Y>                           (the eBR runner record)
  .cache/ebr/frozen/ebr_v1_pool.json                     (eBR's frozen RE24 pool)
Writes:
  .cache/count_value/frozen/count_value_v1_pool.json     (the frozen pool, once)
  data/count_value.json                                  (the table and its receipts)

Every invariant of gate part 5 and every refusing receipt of part 6 is checked before
anything is written; a miss raises count_value.CountValueRefusal and writes nothing.

Run:  python tools/build_count_value.py [--seasons 2018,2019,2021-2026] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import count_value as cv  # noqa: E402
import ebr  # noqa: E402

CORPUS = ROOT / ".cache" / "pbp_corpus"
RECORD = ROOT / ".cache" / "pbp_runners"
EBR_POOL = ROOT / ".cache" / "ebr" / "frozen" / f"{ebr.EBR_VERSION}_pool.json"
EBR_PREVIEW = ROOT / ".cache" / "ebr" / "preview" / "ebr.json"
FROZEN_DIR = ROOT / ".cache" / "count_value" / "frozen"
OUT = ROOT / "data" / "count_value.json"
FREEZE_MONTH_DAY = (11, 1)
DIGITS = 4


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def season_complete(season: int, today: _dt.date | None = None) -> bool:
    t = today or _dt.date.today()
    return t >= _dt.date(int(season), *FREEZE_MONTH_DAY)


def _write_json(path: Path, obj, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent, sort_keys=True,
                              separators=(",", ":") if indent is None else (",", ": ")),
                   encoding="utf-8")
    tmp.replace(path)


def _isna(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v) in ("<NA>", "nan")


def _r(x, d=DIGITS):
    return None if x is None else round(float(x), d)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _slices(game, abi):
    """{(game_pk, at_bat_index): (start, stop)} over arrays already sorted by key."""
    import numpy as np
    key = game.astype(np.int64) * 10000 + abi.astype(np.int64)
    if len(key) == 0:
        return {}
    brk = np.flatnonzero(np.diff(key)) + 1
    starts = np.concatenate([[0], brk])
    stops = np.concatenate([brk, [len(key)]])
    return {int(key[a]): (int(a), int(b)) for a, b in zip(starts, stops)}


def load_season(season: int, corpus: Path = CORPUS, record: Path = RECORD) -> dict:
    import pandas as pd
    man = json.loads((Path(record) / "manifest.json").read_text(encoding="utf-8"))
    blk = (man.get("seasons") or {}).get(str(season))
    if not blk:
        raise cv.CountValueRefusal(f"season {season}: the runner record does not hold it")
    pa = pd.read_parquet(Path(record) / blk["files"]["pa"])
    pit = pd.read_parquet(Path(corpus) / "pitches" / str(season) / f"pitches-{season}.parquet",
                          columns=["game_pk", "at_bat_index", "pitch_number", "call_code"])
    ev = pd.read_parquet(Path(corpus) / "events" / str(season) / f"events-{season}.parquet",
                         columns=["game_pk", "at_bat_index", "index", "type", "description"])
    plays = pd.read_parquet(Path(corpus) / "plays" / str(season) / f"plays-{season}.parquet",
                            columns=["game_pk", "at_bat_index", "outs_before", "on_first",
                                     "on_second", "on_third", "runs_scored_on_play"])
    return {"pa": pa, "pitches": pit, "events": ev, "plays": plays,
            "record_built_at": man.get("built_at") or man.get("generated_at"),
            "record_pa_sha256": blk.get("pa_sha256")}


# --------------------------------------------------------------------------
# one season's walk
# --------------------------------------------------------------------------
def walk_season(season: int, d: dict, re24=None) -> dict:
    """Observations (fit set), steps (fit set) and the receipts of one season.

    An observation row is (balls, strikes, bits, outs, ros, y): ros the runs to the end
    of the half-inning, y the count departure of gate 11.1 against ``re24`` (an
    ebr.RE lookup; y is NaN without one)."""
    import numpy as np
    pa = d["pa"]
    pit = d["pitches"].sort_values(["game_pk", "at_bat_index", "pitch_number"], kind="stable")
    ev = d["events"].sort_values(["game_pk", "at_bat_index", "index"], kind="stable")
    psl = _slices(pit["game_pk"].to_numpy(), pit["at_bat_index"].to_numpy())
    esl = _slices(ev["game_pk"].to_numpy(), ev["at_bat_index"].to_numpy())
    codes = pit["call_code"].to_numpy(dtype=object)
    e_idx = ev["index"].to_numpy()
    e_type = ev["type"].to_numpy(dtype=object)
    e_desc = ev["description"].to_numpy(dtype=object)

    fit = ebr.fit_mask(pa)
    ros_start = ebr.runs_to_end(pa).to_numpy()
    start_bits = ebr.base_code(pa).to_numpy()
    end_bits = (pa["end_on_first"].notna().astype(int) + 2 * pa["end_on_second"].notna().astype(int)
                + 4 * pa["end_on_third"].notna().astype(int)).to_numpy()
    cols = {c: pa[c].to_numpy(dtype=object) for c in
            ("game_pk", "at_bat_index", "outs_before", "end_outs", "runs_scored_on_play",
             "final_pitch_index", "fp_balls", "fp_strikes", "states_json")}

    obs_rows, step_rows, step_play = [], [], []
    play_change = []          # per fit play: (start_bits, start_outs, end_bits, end_outs, runs)
    counters = {}
    rec = {"r1_n": 0, "r1_ok": 0, "r2_n": 0, "r2_ok": 0, "r3_n": 0, "r3_ok": 0,
           "end_n": 0, "end_ok": 0, "plays": int(len(pa)), "plays_no_pitch": 0,
           "pitches": int(len(pit)), "observations": 0, "fit_plays": 0}
    for j in range(len(pa)):
        gk, ab = int(cols["game_pk"][j]), int(cols["at_bat_index"][j])
        key = gk * 10000 + ab
        a, b = psl.get(key, (0, 0))
        pcodes = list(codes[a:b])
        ea, eb = esl.get(key, (0, 0))
        evs = [(int(e_idx[k]), e_type[k], e_desc[k]) for k in range(ea, eb)]
        sj = cols["states_json"][j]
        states = json.loads(sj) if isinstance(sj, str) and sj else []
        o0 = int(cols["outs_before"][j])
        w = cv.walk_play(int(start_bits[j]), o0, pcodes, evs, states)
        for k_, v_ in w["counters"].items():
            counters[k_] = counters.get(k_, 0) + v_
        rec["observations"] += len(w["obs"])
        fpi = cols["final_pitch_index"][j]
        if not pcodes:
            rec["plays_no_pitch"] += 1
        if not (_isna(fpi) and not pcodes):
            rec["r1_n"] += 1
            rec["r1_ok"] += int((not _isna(fpi)) and w["last_pitch_index"] == int(fpi))
        if pcodes and not _isna(cols["fp_balls"][j]):
            rec["r2_n"] += 1
            rec["r2_ok"] += int(w["count_before_last"] == (int(cols["fp_balls"][j]),
                                                           int(cols["fp_strikes"][j])))
        runs = int(cols["runs_scored_on_play"][j] or 0)
        rec["r3_n"] += 1
        rec["r3_ok"] += int(w["runs"] == runs)
        eo = cols["end_outs"][j]
        rec["end_n"] += 1
        rec["end_ok"] += int((not _isna(eo)) and w["end"] == (int(end_bits[j]), int(eo)))
        if not fit[j]:
            continue
        rec["fit_plays"] += 1
        pi = len(play_change)
        play_change.append((int(start_bits[j]), o0, int(end_bits[j]),
                            int(eo) if not _isna(eo) else 3, runs))
        rs = float(ros_start[j])
        eb_, eo_ = int(end_bits[j]), (int(eo) if not _isna(eo) else 3)
        v_end = (0.0 if eo_ >= 3 else re24(eb_, eo_)) if re24 is not None else float("nan")
        for (bb, ss, bits, outs, rb) in w["obs"]:
            y = (runs - rb + v_end - re24(bits, outs)) if re24 is not None else float("nan")
            obs_rows.append((bb, ss, bits, outs, rs - rb, y))
        for (bf, af, r) in w["steps"]:
            step_rows.append((bf[0], bf[1], bf[2], bf[3], int(bf[4]),
                              af[0], af[1], af[2], af[3], int(af[4]), r))
            step_play.append(pi)
    obs = np.array(obs_rows, dtype=float).reshape(-1, 6)
    steps = np.array(step_rows, dtype=np.int16).reshape(-1, 11)
    return {"obs": obs, "steps": steps, "step_play": np.array(step_play, dtype=np.int64),
            "play_change": np.array(play_change, dtype=np.int64).reshape(-1, 5),
            "counters": counters, "receipts": rec}


def corpus_agreement(d: dict) -> dict:
    """R4: the corpus plays table against the record on keys, start state and runs."""
    pa = d["pa"][["game_pk", "at_bat_index", "outs_before", "on_first", "on_second", "on_third",
                  "runs_scored_on_play"]].copy()
    pl = d["plays"].copy()
    for df in (pa, pl):
        df["_b"] = ebr.base_code(df)
        df["game_pk"] = df["game_pk"].astype("int64")
        df["at_bat_index"] = df["at_bat_index"].astype("int64")
    m = pa.merge(pl, on=["game_pk", "at_bat_index"], how="outer", suffixes=("_r", "_c"),
                 indicator=True)
    both = m[m["_merge"] == "both"]
    agree = ((both["_b_r"] == both["_b_c"])
             & (both["outs_before_r"].astype(int) == both["outs_before_c"].astype(int))
             & (both["runs_scored_on_play_r"].astype(int) == both["runs_scored_on_play_c"].astype(int)))
    return {"record_only": int((m["_merge"] == "left_only").sum()),
            "corpus_only": int((m["_merge"] == "right_only").sum()),
            "both": int(len(both)), "agree": int(agree.sum()),
            "agree_share": (round(float(agree.mean()), 6) if len(both) else None)}


# --------------------------------------------------------------------------
# the ledger over a season (vectorized gate part 4)
# --------------------------------------------------------------------------
def _arrays(table288: dict, table24: dict):
    import numpy as np
    T = np.zeros((4, 3, 8, 3))
    for b, s in cv.COUNTS:
        for base, o in cv.BASE_OUT:
            T[b, s, base, o] = table288[cv.cell(b, s, base, o)]
    R = np.zeros((8, 4))
    for base, o in cv.BASE_OUT:
        R[base, o] = table24[f"{base}|{o}"]
    return T, R


def _value(T, R, b, s, bits, outs, ended):
    import numpy as np
    o = np.minimum(outs, 3)
    re = R[bits, o]
    t = T[np.minimum(b, 3), np.minimum(s, 2), bits, np.minimum(o, 2)]
    use24 = (ended == 1) | ((b == 0) & (s == 0))
    v = np.where(use24, re, t)
    return np.where(o >= 3, 0.0, v)


def ledger_identity(walked: dict, table288: dict, table24: dict) -> dict:
    """Invariant 3 over the season's fit-set plays."""
    import numpy as np
    T, R = _arrays(table288, table24)
    st = walked["steps"].astype(np.int64)
    pc = walked["play_change"]
    n_play = len(pc)
    if n_play == 0:
        return {"plays": 0, "exact": 0, "share": None, "max_abs": None}
    vb = _value(T, R, st[:, 0], st[:, 1], st[:, 2], st[:, 3], st[:, 4])
    va = _value(T, R, st[:, 5], st[:, 6], st[:, 7], st[:, 8], st[:, 9])
    delta = va - vb + st[:, 10]
    sums = np.bincount(walked["step_play"], weights=delta, minlength=n_play)
    sb, so, eb, eo, runs = (pc[:, k] for k in range(5))
    so_ = np.minimum(so, 3)
    eo_ = np.minimum(eo, 3)
    change = runs + np.where(eo_ >= 3, 0.0, R[eb, eo_]) - np.where(so_ >= 3, 0.0, R[sb, so_])
    err = np.abs(sums - change)
    exact = int((err <= cv.IDENTITY_TOL).sum())
    return {"plays": int(n_play), "exact": exact, "share": round(exact / n_play, 6),
            "max_abs": round(float(err.max()), 6),
            "steps": int(len(st)), "delta_sum": round(float(delta.sum()), 4),
            "change_sum": round(float(change.sum()), 4)}


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------
def load_ebr_pool(path: Path = EBR_POOL) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ebr.check_frozen_pool(doc)
    return doc


def pool_path(frozen_dir: Path = FROZEN_DIR) -> Path:
    return Path(frozen_dir) / f"{cv.COUNT_VALUE_VERSION}_pool.json"


def load_or_build_pool(raw: dict, lambdas: dict, frozen_dir: Path = FROZEN_DIR) -> tuple[dict, bool]:
    """(pool document, computed now). A new document is written by build() only
    after every invariant passes."""
    fresh = cv.frozen_pool_document(raw, lambdas)
    cv.check_frozen_pool(fresh)
    path = pool_path(frozen_dir)
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        cv.check_frozen_pool(doc)
        if fresh["sha256"] != doc["sha256"]:
            raise cv.CountValueRefusal(
                f"the recomputed pool {fresh['sha256'][:12]} differs from the frozen "
                f"{doc['sha256'][:12]}")
        return doc, False
    return fresh, True


def build(seasons=cv.POOL_SEASONS, *, out: Path = OUT, frozen_dir: Path = FROZEN_DIR,
          today: _dt.date | None = None, generated_at: str | None = None, log=print) -> dict:
    t0 = time.time()
    pool24 = load_ebr_pool()
    K24 = float(pool24["K"])
    prev = {}
    try:
        for blk in (json.loads(EBR_PREVIEW.read_text(encoding="utf-8")).get("re24") or {}).items():
            prev[str(blk[0])] = blk[1]
    except (OSError, ValueError, AttributeError):
        prev = {}
    walked, raw, raw_ros, re24, agree, meta = {}, {}, {}, {}, {}, {}
    lambdas = {int(s): float(v) for s, v in (pool24.get("lambda") or {}).items()}
    for s in seasons:
        ts = time.time()
        d = load_season(s)
        raw24 = ebr.season_raw(d["pa"])
        re24[s] = ebr.shrunk_table(raw24, pool24["re_pool"], K24, s)
        w = walk_season(s, d, ebr.RE(re24[s]))
        o = w["obs"]
        raw[s] = cv.raw_cells(o[:, 0], o[:, 1], o[:, 2], o[:, 3], o[:, 5])
        raw_ros[s] = cv.raw_cells(o[:, 0], o[:, 1], o[:, 2], o[:, 3], o[:, 4])
        agree[s] = corpus_agreement(d)
        meta[s] = {"record_built_at": d["record_built_at"], "record_pa_sha256": d["record_pa_sha256"]}
        walked[s] = w
        log(f"  {s}: {w['receipts']['pitches']:,} pitches, {len(o):,} fit-set observations, "
            f"{time.time() - ts:.1f}s")
    pool_doc, pool_new = load_or_build_pool(raw, lambdas, frozen_dir)
    d_pool = {c: float(pool_doc["d_pool"][c]) for c in cv.CELLS}
    pool = cv.assemble({c: float(v) for c, v in pool24["re_pool"].items()}, d_pool)
    K = float(pool_doc["K"])
    if not (cv.K_CLIP[0] <= K <= cv.K_CLIP[1]):
        raise cv.CountValueRefusal(f"K {K} is outside {cv.K_CLIP}")

    refusals = []
    pool_mono = cv.count_monotone_violations(pool)
    if pool_mono:
        refusals.append(f"pool: not monotone in the count ({pool_mono[:8]}, {len(pool_mono)} total)")
    by_season = {}
    for s in seasons:
        t24 = re24[s]
        t = cv.assemble(t24, cv.pooled_departure(d_pool, lambdas[s]))
        T288, T24 = cv.Table(t), ebr.RE(t24)
        mono = cv.count_monotone_violations(t)
        if mono:
            refusals.append(f"season {s}: not monotone in the count ({mono[:8]}, {len(mono)} total)")
        zz = cv.zero_zero_check(t, t24, raw[s])
        if not zz["pass"]:
            refusals.append(f"season {s}: the 0-0 row misses RE24 (max {zz['max_abs']:.4f} at "
                            f"{zz['worst_cell']}, weighted {zz['wmad']:.4f})")
        ident = ledger_identity(walked[s], t, t24)
        if ident["share"] is not None and ident["share"] < cv.IDENTITY_SHARE:
            refusals.append(f"season {s}: per-event values sum to the RE24 change on only "
                            f"{ident['share']} of fit-set plays")
        rc = walked[s]["receipts"]
        shares = {k: (round(rc[f"{k}_ok"] / rc[f"{k}_n"], 6) if rc[f"{k}_n"] else None)
                  for k in ("r1", "r2", "r3", "end")}
        for k, label in (("r1", "R1 index"), ("r2", "R2 count"), ("r3", "R3 runs")):
            if shares[k] is not None and shares[k] < cv.RECEIPT_SHARE:
                refusals.append(f"season {s}: {label} agreement {shares[k]} is below {cv.RECEIPT_SHARE}")
        bo = cv.base_out_violations(t)
        marg = cv.count_marginal(t, raw[s], T288, T24, raw_ros=raw_ros[s])
        sha24 = ebr.table_sha(t24)
        prev_blk = prev.get(str(s)) or {}
        by_season[str(s)] = {
            "season_complete": season_complete(s, today),
            "lambda": lambdas[s],
            "sha256": cv.table_sha(t),
            "re288": {c: _r(t[c]) for c in cv.CELLS},
            "n": {c: int((raw[s].get(c) or {}).get("n", 0)) for c in cv.CELLS},
            "d_raw": {c: _r((raw[s].get(c) or {}).get("mean")) for c in cv.CELLS},
            "re24": {c: _r(t24[c]) for c in ebr.CELLS},
            "re24_sha256": sha24,
            "re24_matches_ebr_preview": (prev_blk.get("sha256") == sha24) if prev_blk else None,
            "count_marginal": {k: {"n": v["n"], "re_mean": _r(v["re_mean"]),
                                   "rv_vs_00": _r(v["rv_vs_00"]), "called_value": _r(v["called_value"])}
                               for k, v in marg.items()},
            "invariants": {
                "zero_zero": {"max_abs": _r(zz["max_abs"], 5), "worst_cell": zz["worst_cell"],
                              "wmad": _r(zz["wmad"], 5), "pass": zz["pass"]},
                "count_monotone_violations": len(mono),
                "ledger_identity": ident,
            },
            "base_out_monotone_violations": {"n": len(bo), "first": bo[:10]},
            "receipts": {
                "plays": rc["plays"], "fit_plays": rc["fit_plays"], "pitches": rc["pitches"],
                "observations": rc["observations"], "fit_set_observations": int(len(walked[s]["obs"])),
                "plays_no_pitch": rc["plays_no_pitch"],
                "r1_index": {"n": rc["r1_n"], "agree": rc["r1_ok"], "share": shares["r1"]},
                "r2_count": {"n": rc["r2_n"], "agree": rc["r2_ok"], "share": shares["r2"]},
                "r3_runs": {"n": rc["r3_n"], "agree": rc["r3_ok"], "share": shares["r3"]},
                "end_state": {"n": rc["end_n"], "agree": rc["end_ok"], "share": shares["end"]},
                "r4_corpus_plays": agree[s],
                "walk_counters": dict(sorted(walked[s]["counters"].items())),
            },
            "record": meta[s],
        }
    if refusals:
        raise cv.CountValueRefusal("; ".join(refusals))
    if pool_new:
        _write_json(pool_path(frozen_dir), pool_doc, indent=1)

    # the pooled marginal: the pool table with pooled occupancy weights
    raw_pool = {c: {"n": int(pool_doc["n_pool"][c]), "mean": pool[c], "var": 0.0}
                for c in cv.CELLS if int(pool_doc["n_pool"][c]) > 0}
    ros_pool = {}
    for c in cv.CELLS:
        n = sum((raw_ros[s].get(c) or {}).get("n", 0) for s in seasons)
        if n:
            ros_pool[c] = {"n": n, "mean": sum((raw_ros[s].get(c) or {}).get("n", 0)
                                               * (raw_ros[s].get(c) or {}).get("mean", 0.0)
                                               for s in seasons) / n, "var": 0.0}
    pool_marg = cv.count_marginal(pool, raw_pool, raw_ros=ros_pool)
    doc = {
        "count_value_version": cv.COUNT_VALUE_VERSION,
        "generated_at": generated_at or _now(),
        "gate_doc": cv.GATE_DOC,
        "what": ("RE288: mean runs from a pitch to the end of its half-inning by the state before "
                 "the pitch (balls, strikes, 3-bit base code, outs), per MLB regular season: "
                 "RE24 plus a count departure measured against RE24 of the play's end state, "
                 "pooled over 2018 to 2026 and frozen. Descriptive, measurement only; no player "
                 "value."),
        "estimator": pool_doc["estimator"],
        "season_table": ("RE24_s + lambda_s x the pooled count departure (gate 11.2, owner "
                         "question RE288-Q1 default (a)); d_raw is each season's raw departure"),
        "cell_key": "balls-strikes|base|outs; base bits: 1 first, 2 second, 4 third",
        "units": "runs",
        "seasons": [int(s) for s in seasons],
        "pool_seasons": list(cv.POOL_SEASONS),
        "K": K, "K_raw": pool_doc["K_raw"], "W": pool_doc["W"], "tau2": pool_doc["tau2"],
        "k_clip": list(cv.K_CLIP), "cells_used_for_K": pool_doc["cells_used"],
        "pool_sha256": pool_doc["sha256"],
        "re24_basis": {"ebr_version": ebr.EBR_VERSION, "ebr_pool_sha256": pool24["sha256"],
                       "K": K24},
        "tolerances": {"zero_zero_max_abs": cv.ZERO_ZERO_MAX_ABS, "zero_zero_wmad": cv.ZERO_ZERO_WMAD,
                       "identity_tol": cv.IDENTITY_TOL, "identity_share": cv.IDENTITY_SHARE,
                       "receipt_share": cv.RECEIPT_SHARE},
        "ledger_convention": ("state value: three outs 0; count 0-0 or ended RE24; otherwise RE288. "
                              "Event value = value(after) - value(before) + runs at its index."),
        "pool": {"re288": {c: _r(pool[c]) for c in cv.CELLS},
                 "n": {c: int(pool_doc["n_pool"][c]) for c in cv.CELLS},
                 "count_marginal": {k: {"n": v["n"], "re_mean": _r(v["re_mean"]),
                                        "rv_vs_00": _r(v["rv_vs_00"])} for k, v in pool_marg.items()},
                 "d": {c: _r(d_pool[c]) for c in cv.CELLS},
                 "lambda": pool_doc["lambda"]},
        "by_season": by_season,
        "build_seconds": round(time.time() - t0, 1),
        "pool_computed_this_run": pool_new,
    }
    _write_json(Path(out), doc, indent=1)
    return doc


def _parse_seasons(s: str) -> list:
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += [y for y in range(int(a), int(b) + 1) if y != 2020]
        elif part:
            out.append(int(part))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    seasons = tuple(_parse_seasons(a.seasons)) if a.seasons else cv.POOL_SEASONS
    try:
        doc = build(seasons, out=Path(a.out))
    except cv.CountValueRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    print(f"wrote {a.out}: K {doc['K']}, pool {doc['pool_sha256'][:12]}, "
          f"{doc['build_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
