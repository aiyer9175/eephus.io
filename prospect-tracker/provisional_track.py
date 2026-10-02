# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Score frozen provisional grades against the first source grades that arrive after
the freeze (PV-04; spec _finalpass_2026-09-24/provisional/PROVISIONAL_V2.md section 4).

A ported copy of the research scorer (lane PG3 score_freeze.py), with repo-relative
paths, one label-dating repair (below) and an append-only artifact. It reads GRADES
ONLY: prospects.db snapshots plus three identity maps. It never reads WAR, and no
stratum here is named after a consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md).

WHAT IS SCORED.
  Freezes   every data/provisional_freeze/FREEZE_provisional_<date>.json (pinned by
            test_provisional_freeze_pin.py; nothing here writes them), scored per
            window (W6 2027-04-15, W12 2027-10-15 unless the freeze names its own).
  Label     the first label-source opinion (FanGraphs, MLB Pipeline incl.
            international, Baseball America, ESPN, Just Baseball) dated strictly after
            frozen_at and on or before the window end. Sets ANY, FG, MLBP, BA.
            FanGraphs 35+ / 40+ code as the half step (+2.5).
  Identity  the freeze key, then mlbam -> player_key through timeseries.json, xfv.json
            and rosters_by_org.json. Name-only matches are never scored. A row with any
            label-source opinion dated on or before frozen_at is dropped at score time,
            which also catches lists backfilled later.
  Metrics   selection: AUC, AP, precision at 50 and 200, Brier raw and at the fixed x2
            factor (neither gated); zero-fit nulls level-rank and younger. Level, on the
            graded subset: Spearman with CI95, MAE, bias, share within 2.5 FV, MAE of the
            freeze's own constant. Lead in days. Coverage.
  Claims    computed only where a verdict may be read (a closed window, or the spent
            backdated replay): a LEVEL claim needs MAE below the constant with a paired
            bootstrap CI95 clear of 0; a SELECTION claim needs AUC above the level-rank
            null AND above the incumbent grade, each with a paired CI95 clear of 0.

THE LABEL-DATING REPAIR. The daily MLB Pipeline per-team Top 30 capture
(run_monthly d0b-ii) upserts each row in place and BUMPS its snapshot_date to the
capture day, while inserted_at keeps the day the row first appeared. Dated by
snapshot_date alone, a Pipeline grade first published in August reads as new on every
capture day: on 2026-10-01 the replay below lost all 52 of its Pipeline labels past a
2026-09-24 window end, and today's freeze showed 38 "first opinions" that were all
re-stamped old rows. The label date is therefore the earliest evidence the opinion
existed: min(snapshot_date, the UTC date of inserted_at). With it the backdated replay
reproduces the lane exactly (97 pairs, median lead 48 days, AUC 0.826) and today's
freeze scores 0 labels.

THE ARTIFACT. data/provisional_track_eval.json, append-only per (leg, freeze, window):
a row is appended when the measured content changes, otherwise only that row's
last_verified_at moves (as efv_progress.py does). Each row carries its as_of and the
date it is scored through. Before a window closes the row says "window open until
<date>" and carries no claims; verdicts are read only at window end. Every row is
also appended to .cache/provisional_track/ledger.jsonl (untracked) and merged back
before each write, because the deploy box runs `git checkout -- .` nightly.

THE RECEIPTS (PV-08). The artifact also carries `by_player`: per committed freeze, one
compact row per eligible frozen player with the frozen served grade and, once it exists,
the first label-source opinion after the freeze (date, source, FV, days later). It is the
latest state, rebuilt on every write and never appended; the PROSPX card prints it as
"Frozen <date> at X; first graded <date> by <source> at Y, N days later", or "window open
until <date>" before a first grade.

THE SERVED RETROSPECTIVE. The 2026-06-23 served artifact (git f6dc2c8a) rebuilt as a
backdated freeze and scored to 2026-09-24 is the only served record with labels. It is
SPENT (the freezes' constants and recalibration were fitted on it), kept as leg
"served_backdated", and never adjudicates a window.

Run: python provisional_track.py            nightly update (as of today)
     python provisional_track.py --print    print the latest rows, write nothing
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import logging
import random
import sqlite3
import statistics
import subprocess
from pathlib import Path

log = logging.getLogger("provisional_track")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "prospects.db"
FREEZE_DIR = DATA_DIR / "provisional_freeze"
OUT_PATH = DATA_DIR / "provisional_track_eval.json"
LEDGER_PATH = ROOT / ".cache" / "provisional_track" / "ledger.jsonl"

SCHEMA = 1
MODEL_ID = "provisional_first_grade"
SCORER_VERSION = "pg3-port-1"
WINDOWS = {"W6": "2027-04-15", "W12": "2027-10-15"}
SETS = {"ANY": ("fangraphs", "mlb_pipeline", "mlb_pipeline_international", "baseballamerica",
                "espn", "just_baseball"),
        "FG": ("fangraphs",), "MLBP": ("mlb_pipeline", "mlb_pipeline_international"),
        "BA": ("baseballamerica",)}
LV = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
LABEL_RULE = ("first label-source opinion dated strictly after frozen_at and on or before the "
              "window end; an opinion's date is min(snapshot_date, UTC date of inserted_at), "
              "because the daily Pipeline Top 30 capture bumps snapshot_date in place")
CLAIM_RULES = {
    "level": "MAE below the freeze's constant with a paired bootstrap CI95 clear of 0",
    "selection": "AUC above the level-rank null and above the incumbent grade, each paired CI95 clear of 0",
    "read": "verdicts are read only at window end; an interim row says window open until <date>",
}
#: The served 2026-06-23 artifact, rebuilt as a backdated freeze (lane PG3 build_backdated.py).
BACKDATED = {"commit": "f6dc2c8a", "path": "prospect-tracker/data/xfv_ungraded.json",
             "frozen_at": "2026-06-23", "window_end": "2026-09-24",
             "nulls": {"ANY": 35.0, "FG": 37.5, "MLBP": 40.0, "BA": 35.0}}
CLAIM_SEED = 20260925


# ---------------------------------------------------------------------------
# the lane scorer's statistics, verbatim except the private RNG

def canon_rows(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: str(r["key"])), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def rk(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for t in range(i, j + 1):
            r[o[t]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 5:
        return None
    a, b = rk(x), rk(y)
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = (sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** .5
    return num / den if den else None


def auc(s, y):
    pos = sum(y)
    neg = len(y) - pos
    if not pos or not neg:
        return None
    r = rk(s)
    return (sum(ri for ri, yi in zip(r, y) if yi) - pos * (pos + 1) / 2) / (pos * neg)


def ap(s, y):
    o = sorted(range(len(s)), key=lambda i: -s[i])
    hit = 0
    tot = 0.0
    for n, i in enumerate(o, 1):
        if y[i]:
            hit += 1
            tot += hit / n
    return tot / max(1, sum(y))


def boot(rows, f, B=1000, seed=7):
    """The lane's percentile bootstrap. random.Random(seed) draws the same sequence the
    lane's random.seed(seed) did, without touching the process-wide generator."""
    rng = random.Random(seed)
    v = []
    for _ in range(B):
        s = [rng.choice(rows) for _ in rows]
        x = f(s)
        if x is not None:
            v.append(x)
    v.sort()
    return [round(v[int(.025 * len(v))], 3), round(v[int(.975 * len(v)) - 1], 3)] if v else None


# ---------------------------------------------------------------------------
# inputs

def identity(data_dir: Path | None = None) -> dict[str, str]:
    """mlbam -> player_key from the three served identity maps (never by name)."""
    d = Path(data_dir) if data_dir is not None else DATA_DIR
    m2k: dict[str, str] = {}
    try:
        ts = json.loads((d / "timeseries.json").read_text(encoding="utf-8"))
        for p in ts.get("players") or []:
            if p.get("mlbam_id") and p.get("player_key"):
                m2k[str(p["mlbam_id"])] = p["player_key"]
    except (OSError, ValueError):
        log.warning("provisional_track: timeseries.json unreadable; identity map thinner")
    try:
        bp = json.loads((d / "xfv.json").read_text(encoding="utf-8")).get("by_player") or {}
        for k, e in bp.items():
            if e.get("mlbam_id") and not k.startswith("mlbam_"):
                m2k.setdefault(str(e["mlbam_id"]), k)
    except (OSError, ValueError):
        log.warning("provisional_track: xfv.json unreadable; identity map thinner")
    try:
        ro = json.loads((d / "rosters_by_org.json").read_text(encoding="utf-8"))
        for _org, lv in ro.items():
            for _level, ps in (lv or {}).items():
                if isinstance(ps, list):
                    for p in ps:
                        if p.get("mlbam_id") and p.get("player_key"):
                            m2k.setdefault(str(p["mlbam_id"]), p["player_key"])
    except (OSError, ValueError, AttributeError):
        log.warning("provisional_track: rosters_by_org.json unreadable; identity map thinner")
    return m2k


def opinions(db_path: Path | None = None) -> dict[str, list]:
    """player_key -> [(first-seen date, source, fv)] for every label-source row that
    carries a grade or a rank. See THE LABEL-DATING REPAIR in the module docstring."""
    allsrc = SETS["ANY"]
    con = sqlite3.connect(f"file:{Path(db_path or DB_PATH).as_posix()}?mode=ro", uri=True)
    try:
        q = ("select player_key, source, snapshot_date, substr(inserted_at, 1, 10), fv, rank, "
             "fv_plus from snapshots where source in (%s)" % ",".join("?" * len(allsrc)))
        opin = collections.defaultdict(list)
        for pk, s, d, ins, fv, r, plus in con.execute(q, allsrc):
            if fv is not None and plus and s == "fangraphs":
                fv = fv + 2.5
            if fv is not None or r is not None:
                day = min(d, ins) if ins else d
                opin[pk].append((day, s, fv))
        return opin
    finally:
        con.close()


def backdated_freeze(commit: str = BACKDATED["commit"], *, repo: Path | None = None) -> dict:
    """The served 2026-06-23 artifact as a freeze, exactly as lane PG3 built it."""
    raw = subprocess.run(["git", "-C", str(repo or ROOT), "show",
                          f"{commit}:./data/xfv_ungraded.json"],
                         capture_output=True, check=True).stdout
    doc = json.loads(raw.decode("utf-8"))
    rows = [{"key": k, "mlbam": e.get("mlbam_id"), "name": e.get("player_name") or e.get("name"),
             "side": e.get("side"), "level": e.get("level"), "age": e.get("age"),
             "grade": e.get("xfv_grade")}
            for k, e in doc["by_player"].items() if e.get("xfv_grade") is not None]
    return {"frozen_at": BACKDATED["frozen_at"],
            "source": f"git {commit} data/xfv_ungraded.json (generated 2026-06-23)",
            "nulls": dict(BACKDATED["nulls"]), "sha256_rows": canon_rows(rows), "rows": rows}


# ---------------------------------------------------------------------------
# the scorer

def score(freeze: dict, window_end: str, B: int = 1000, *, m2k: dict | None = None,
          opin: dict | None = None, data_dir: Path | None = None,
          db_path: Path | None = None) -> dict:
    """Score one freeze through `window_end`. Pass m2k / opin to reuse one load."""
    F = freeze["frozen_at"]
    rows = freeze["rows"]
    h = canon_rows(rows)
    if freeze.get("sha256_rows") and freeze["sha256_rows"] != h:
        raise ValueError("freeze rows do not match their recorded hash: refuse to score")
    m2k = identity(data_dir) if m2k is None else m2k
    opin = opinions(db_path) if opin is None else opin
    nulls = freeze.get("nulls", {})
    res = {"frozen_at": F, "window_end": window_end, "n_rows": len(rows), "sha256_rows": h}
    elig = []
    drop = collections.Counter()
    for r in rows:
        k = str(r["key"])
        pk = k if not k.startswith("mlbam_") else m2k.get(str(r.get("mlbam") or k[6:]))
        if pk is None:
            drop["unresolved_kept_as_ungraded"] += 1
        ops = opin.get(pk, []) if pk else []
        if any(d <= F for d, _, _ in ops):
            drop["opinion_on_or_before_freeze"] += 1
            continue
        elig.append((r, pk, ops))
    res["eligible"] = len(elig)
    res["dropped"] = dict(drop)
    k2m = {v: k for k, v in m2k.items()}
    matched = {pk for _, pk, _ in elig if pk}
    newly = [pk for pk, ops in opin.items() if F < min(d for d, _, _ in ops) <= window_end]
    um = [pk for pk in newly if pk not in matched]
    res["coverage"] = {"first_opinion_in_window": len(newly), "matched_to_freeze": len(newly) - len(um),
                       "unmatched_with_known_mlbam": sum(1 for pk in um if pk in k2m),
                       "unmatched_no_mlbam": sum(1 for pk in um if pk not in k2m)}
    score_cols = [c for c in ("p_g12", "p_g6", "grade", "p_al_g12")
                  if any(r.get(c) is not None for r, _, _ in elig)]
    labelled = {}
    for S, srcs in SETS.items():
        lab = []
        for r, pk, ops in elig:
            fvs = [(d, fv) for d, s, fv in ops if s in srcs and fv is not None and F < d <= window_end]
            anyop = [d for d, s, fv in ops if s in srcs and F < d <= window_end]
            first = None
            if fvs:
                d0 = min(d for d, _ in fvs)
                first = (d0, statistics.mean(fv for d, fv in fvs if d == d0))
            lab.append((r, 1 if anyop else 0, first))
        labelled[S] = lab
        y = [l_[1] for l_ in lab]
        out = {"n": len(lab), "graded_in_window": sum(y), "base_rate": round(sum(y) / max(1, len(y)), 4)}
        sel = {}
        for c in score_cols:
            sub = [(l_[0][c], l_[1]) for l_ in lab if l_[0].get(c) is not None]
            if not sub:
                continue
            s_, y_ = [a for a, _ in sub], [b for _, b in sub]
            o = sorted(range(len(s_)), key=lambda i: -s_[i])
            a_ = auc(s_, y_)
            sel[c] = {"n": len(sub), "auc": round(a_, 4) if a_ is not None else None,
                      "ap": round(ap(s_, y_), 4),
                      "prec_at_50": round(sum(y_[i] for i in o[:50]) / 50, 3),
                      "prec_at_200": round(sum(y_[i] for i in o[:200]) / 200, 3)}
            if c.startswith("p_"):
                sel[c]["brier_raw"] = round(statistics.mean((p - t) ** 2 for p, t in sub), 5)
                sel[c]["brier_x2"] = round(statistics.mean((min(1, 2 * p) - t) ** 2 for p, t in sub), 5)
                sel[c]["sum_p_raw"] = round(sum(s_), 1)
        lvl = [(LV.get(l_[0].get("level")), l_[1]) for l_ in lab]
        lvl = [(a, b) for a, b in lvl if a is not None]
        if lvl:
            a_ = auc([a for a, _ in lvl], [b for _, b in lvl])
            sel["null_level_rank"] = {"auc": round(a_, 4) if a_ is not None else None}
        ag = [(-l_[0]["age"], l_[1]) for l_ in lab if l_[0].get("age") is not None]
        if ag:
            a_ = auc([a for a, _ in ag], [b for _, b in ag])
            sel["null_younger"] = {"auc": round(a_, 4) if a_ is not None else None}
        out["selection"] = sel
        g = [l_ for l_ in lab if l_[2] is not None]
        lev = {"n_first_fv": len(g)}
        if g:
            Y = [l_[2][1] for l_ in g]
            lead = [(datetime.date.fromisoformat(l_[2][0]) - datetime.date.fromisoformat(F)).days for l_ in g]
            lev.update({"mean_first_fv": round(statistics.mean(Y), 2), "median_lead_days": statistics.median(lead),
                        "label_dates": dict(collections.Counter(l_[2][0] for l_ in g).most_common(8))})
            const = nulls.get(S, nulls.get("ANY"))
            for c in ("grade", "grade_recal", "fv_fg_pred"):
                P = [(l_[0].get(c), l_[2][1]) for l_ in g if l_[0].get(c) is not None]
                if len(P) < 5:
                    continue
                X = [a for a, _ in P]
                Yc = [b for _, b in P]
                rho = spearman(X, Yc)
                lev[c] = {"n": len(P), "spearman": round(rho, 3) if rho is not None else None,
                          "spearman_ci95": boot(P, lambda s: spearman([a for a, _ in s], [b for _, b in s]), B)
                          if len(P) >= 10 else None,
                          "mae": round(statistics.mean(abs(a - b) for a, b in P), 2),
                          "bias": round(statistics.mean(a - b for a, b in P), 2),
                          "level_hit_share_2p5": round(statistics.mean(abs(a - b) <= 2.5 for a, b in P), 3)}
                if const is not None:
                    lev[c]["mae_null_const"] = round(statistics.mean(abs(const - b) for b in Yc), 2)
                    lev[c]["null_const"] = const
        out["level"] = lev
        if S == "ANY":
            col = "p_g12" if "p_g12" in score_cols else "grade"
            top = sorted(lab, key=lambda l_: -(l_[0].get(col) if l_[0].get(col) is not None else -1))[:50]
            out["top50_col"] = col
            out["top50_hits"] = [{"key": l_[0]["key"], "name": l_[0].get("name"), col: l_[0].get(col),
                                  "first": l_[2]} for l_ in top if l_[1]]
        res[S] = out
    res["_labelled"] = labelled            # consumed by claims(); never written
    return res


# ---------------------------------------------------------------------------
# claims (closed windows and the spent replay only)

def _np_auc(s, y):
    import numpy as np
    from scipy.stats import rankdata
    y = np.asarray(y, dtype=bool)
    pos = int(y.sum())
    neg = len(y) - pos
    if not pos or not neg:
        return None
    r = rankdata(s)
    return float((r[y].sum() - pos * (pos + 1) / 2) / (pos * neg))


def _ci(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return [round(v[int(.025 * len(v))], 4), round(v[int(.975 * len(v)) - 1], 4)]


def claims(res: dict, freeze: dict, B: int = 1000, seed: int = CLAIM_SEED) -> dict:
    """Paired player-bootstrap CIs for the two claim rules on the ANY set."""
    import numpy as np
    rng = np.random.default_rng(seed)
    lab = res["_labelled"]["ANY"]
    out = {"set": "ANY", "B": B, "seed": seed, "level": {}, "selection": {}}
    # LEVEL: delta = |pred - y| - |const - y|, negative favours the prediction.
    const = (freeze.get("nulls") or {}).get("ANY")
    g = [l_ for l_ in lab if l_[2] is not None]
    for c in ("grade", "grade_recal", "fv_fg_pred"):
        P = [(l_[0].get(c), l_[2][1]) for l_ in g if l_[0].get(c) is not None]
        if len(P) < 10 or const is None:
            continue
        d = np.array([abs(a - b) - abs(const - b) for a, b in P])
        bs = [float(d[rng.integers(0, len(d), len(d))].mean()) for _ in range(B)]
        ci = _ci(bs)
        out["level"][c] = {"n": len(P), "mae_minus_const": round(float(d.mean()), 3), "ci95": ci,
                           "claim": bool(ci and ci[1] < 0)}
    # SELECTION: AUC(col) - AUC(level-rank null), and - AUC(incumbent grade).
    rows = [(l_[0], l_[1]) for l_ in lab if LV.get(l_[0].get("level")) is not None]
    for c in ("grade", "p_g12", "p_g6"):
        sub = [(r, y) for r, y in rows if r.get(c) is not None and r.get("grade") is not None]
        if len(sub) < 50 or not any(y for _, y in sub):
            continue
        s = np.array([r[c] for r, _ in sub], dtype=float)
        lv = np.array([LV[r["level"]] for r, _ in sub], dtype=float)
        inc = np.array([r["grade"] for r, _ in sub], dtype=float)
        y = np.array([y for _, y in sub], dtype=int)
        point = {"auc": _np_auc(s, y), "auc_level_null": _np_auc(lv, y), "auc_incumbent": _np_auc(inc, y)}
        d_lv, d_inc = [], []
        for _ in range(B):
            ix = rng.integers(0, len(y), len(y))
            a = _np_auc(s[ix], y[ix])
            b = _np_auc(lv[ix], y[ix])
            d_lv.append(None if a is None or b is None else a - b)
            if c != "grade":
                i2 = _np_auc(inc[ix], y[ix])
                d_inc.append(None if a is None or i2 is None else a - i2)
        ci_lv = _ci(d_lv)
        ci_inc = _ci(d_inc) if c != "grade" else None
        beats_inc = True if c == "grade" else bool(ci_inc and ci_inc[0] > 0)
        out["selection"][c] = {
            "n": len(y), "auc": round(point["auc"], 4) if point["auc"] is not None else None,
            "minus_level_null": round(point["auc"] - point["auc_level_null"], 4)
            if None not in (point["auc"], point["auc_level_null"]) else None,
            "minus_level_null_ci95": ci_lv,
            "minus_incumbent": (round(point["auc"] - point["auc_incumbent"], 4)
                                if c != "grade" and None not in (point["auc"], point["auc_incumbent"]) else None),
            "minus_incumbent_ci95": ci_inc,
            "claim": bool(ci_lv and ci_lv[0] > 0 and beats_inc),
            "note": "the incumbent is itself; only the level-rank null applies" if c == "grade" else None,
        }
    return out


# ---------------------------------------------------------------------------
# the append-only artifact

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def content_hash(row: dict) -> str:
    keep = {k: row.get(k) for k in ("leg", "freeze", "freeze_sha256_rows", "window", "window_end",
                                    "verdict_readable", "scorer_version", "result", "claims")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _strip(res: dict) -> dict:
    out = {k: v for k, v in res.items() if k not in ("_labelled", "window_end")}
    return json.loads(json.dumps(out, default=str))


def freeze_files(freeze_dir: Path | None = None) -> list[Path]:
    d = Path(freeze_dir) if freeze_dir is not None else FREEZE_DIR
    return sorted(p for p in d.glob("FREEZE_provisional_*.json") if not p.name.endswith(".manifest.json"))


def build_rows(as_of: str, *, freeze_dir=None, data_dir=None, db_path=None, B: int = 1000,
               retrospective: bool = True, now_iso: str | None = None,
               m2k: dict | None = None, opin: dict | None = None) -> list[dict]:
    now_iso = now_iso or _now_iso()
    m2k = identity(data_dir) if m2k is None else m2k
    opin = opinions(db_path) if opin is None else opin
    out = []

    def _row(leg, name, fz, window, wend, status, readable):
        through = wend if readable else min(as_of, wend)
        res = score(fz, through, B, m2k=m2k, opin=opin)
        row = {"run_id": f"{leg}|{name}|{window}|{as_of}", "leg": leg, "freeze": name,
               "frozen_at": fz["frozen_at"], "freeze_sha256_rows": res["sha256_rows"],
               "window": window, "window_end": wend, "as_of": as_of, "scored_through": through,
               "status": status, "verdict_readable": readable, "scorer_version": SCORER_VERSION,
               "result": _strip(res), "claims": claims(res, fz, B) if readable else None,
               "first_seen_at": now_iso, "last_verified_at": now_iso}
        row["content_hash"] = content_hash(row)
        return row

    for p in freeze_files(freeze_dir):
        fz = json.loads(p.read_text(encoding="utf-8"))
        for window, wend in sorted((fz.get("windows") or WINDOWS).items(), key=lambda kv: kv[1]):
            if as_of <= fz["frozen_at"]:
                continue
            closed = as_of >= wend
            status = f"window closed {wend}" if closed else f"window open until {wend}"
            out.append(_row("prospective", p.name, fz, window, wend, status, closed))
    if retrospective:
        try:
            fz = backdated_freeze()
        except (OSError, subprocess.CalledProcessError, ValueError) as e:
            log.warning("provisional_track: backdated freeze unavailable (%s); kept rows stand", e)
        else:
            out.append(_row("served_backdated", f"git:{BACKDATED['commit']}", fz, "spent",
                            BACKDATED["window_end"],
                            "spent: the served 2026-06-23 artifact replayed to 2026-09-24", True))
    return out


#: Source names as a receipt prints them.
SOURCE_NAMES = {"fangraphs": "FanGraphs", "mlb_pipeline": "MLB Pipeline",
                "mlb_pipeline_international": "MLB Pipeline", "baseballamerica": "Baseball America",
                "espn": "ESPN", "just_baseball": "Just Baseball"}
RECEIPT_COLUMNS = ["grade", "first_date", "first_source", "first_fv", "first_label", "lead_days",
                   "player_key"]


def _fv_label(source: str, fv) -> str | None:
    """The first grade as its source published it: FanGraphs 35+ is coded 37.5 by
    opinions(), so it prints back as 35+; any other grade rounds UP (the FV rule)."""
    if fv is None:
        return None
    fv = float(fv)
    if source == "fangraphs" and abs((fv - 2.5) % 5) < 1e-9:
        return f"{int(round(fv - 2.5))}+"
    import math
    return str(int(math.ceil(fv - 1e-9)))


def receipts(as_of: str, *, freeze_dir=None, m2k: dict | None = None,
             opin: dict | None = None, data_dir=None, db_path=None) -> dict:
    """PV-08 card receipts: for every eligible row of every committed freeze, the frozen
    served grade and, once it exists, the first label-source opinion after the freeze
    (date, source, FV, days later), scored through min(as_of, the freeze's last window
    end). Latest state only: rebuilt on every write, never appended. Reads the same
    opinions and identity maps as score(), so a receipt and the scored row cannot
    disagree about who was graded or when."""
    m2k = identity(data_dir) if m2k is None else m2k
    opin = opinions(db_path) if opin is None else opin
    srcs = set(SETS["ANY"])
    out = {}
    for p in freeze_files(freeze_dir):
        fz = json.loads(p.read_text(encoding="utf-8"))
        F = fz["frozen_at"]
        if as_of <= F:
            continue
        wins = fz.get("windows") or WINDOWS
        wend = max(wins.values())
        through = min(as_of, wend)
        rows = {}
        n_first = 0
        for r in fz["rows"]:
            k = str(r["key"])
            pk = k if not k.startswith("mlbam_") else m2k.get(str(r.get("mlbam") or k[6:]))
            ops = opin.get(pk, []) if pk else []
            if any(d <= F for d, _, _ in ops):
                continue
            after = sorted((d, s, fv) for d, s, fv in ops if s in srcs and F < d <= through)
            first = None
            if after:
                d0 = after[0][0]
                same = [o for o in after if o[0] == d0]
                withfv = [o for o in same if o[2] is not None]
                first = (withfv or same)[0]
                n_first += 1
            g = r.get("grade")
            row = [round(float(g), 1) if g is not None else None]
            if first:
                lead = (datetime.date.fromisoformat(first[0]) - datetime.date.fromisoformat(F)).days
                row += [first[0], first[1], first[2], _fv_label(first[1], first[2]), lead]
            else:
                row += [None, None, None, None, None]
            row.append(pk if (pk and pk != k) else None)
            rows[k] = row
        out[p.name] = {"frozen_at": F, "windows": dict(sorted(wins.items(), key=lambda kv: kv[1])),
                       "scored_through": through, "n_rows": len(rows), "n_first_graded": n_first,
                       "rows": rows}
    return {"as_of": as_of, "columns": list(RECEIPT_COLUMNS), "source_names": dict(SOURCE_NAMES),
            "note": ("one row per eligible frozen player, keyed by the freeze key: the frozen "
                     "served grade, then the first label-source opinion after the freeze "
                     "(null until one arrives); player_key is set where the freeze key is an "
                     "mlbam key that now resolves. Latest state, rebuilt on every write."),
            "freezes": out}


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return rows
    for ln in text.splitlines():
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except ValueError:
                log.warning("provisional_track: unreadable ledger line skipped")
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def merge_rows(served: list[dict], durable: list[dict]) -> list[dict]:
    have = {r.get("run_id") for r in served}
    out = list(served) + [r for r in durable if r.get("run_id") not in have]
    return sorted(out, key=lambda r: (r.get("as_of") or "", r.get("leg") or "", r.get("freeze") or "",
                                      r.get("window") or ""))


def apply(rows: list[dict], candidates: list[dict], now_iso: str) -> tuple[list[dict], list[dict]]:
    """Append a candidate whose content differs from the last row of its
    (leg, freeze, window); otherwise move that row's last_verified_at."""
    rows = [dict(r) for r in rows]
    appended = []
    for cand in candidates:
        same_id = next((r for r in rows if r.get("run_id") == cand["run_id"]), None)
        if same_id is not None:
            same_id["last_verified_at"] = now_iso
            continue
        last = None
        for r in reversed(rows):
            if (r.get("leg"), r.get("freeze"), r.get("window")) == (cand["leg"], cand["freeze"], cand["window"]):
                last = r
                break
        if last is not None and last.get("content_hash") == cand["content_hash"]:
            last["last_verified_at"] = now_iso
            continue
        rows.append(cand)
        appended.append(cand)
    return rows, appended


def _latest(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        out[f"{r['leg']}|{r['freeze']}|{r['window']}"] = r["run_id"]
    return out


def _doc(rows: list[dict], now_iso: str, by_player: dict | None = None) -> dict:
    doc = {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "model_id": MODEL_ID,
        "producer": "provisional_track.py (run_monthly daily step d9a)",
        "spec": ("_finalpass_2026-09-24/provisional/PROVISIONAL_V2.md section 4; ported from lane "
                 "PG3 score_freeze.py"),
        "windows": dict(WINDOWS),
        "label_sources": list(SETS["ANY"]),
        "label_rule": LABEL_RULE,
        "claim_rules": dict(CLAIM_RULES),
        "legs": {"prospective": "a committed freeze under data/provisional_freeze/, scored per window",
                 "served_backdated": ("the served 2026-06-23 artifact (git " + BACKDATED["commit"]
                                      + ") replayed to 2026-09-24; SPENT, never adjudicates a window")},
        "rule": ("append-only per (leg, freeze, window): a row is added when the measured content "
                 "changes, otherwise only its last_verified_at moves; the untracked "
                 ".cache/provisional_track/ledger.jsonl copy is merged back on every write"),
        "reads_no_war": True,
        "latest": _latest(rows),
        "rows": rows,
    }
    if by_player is not None:
        doc["by_player"] = by_player
    return doc


def _dumps(doc: dict) -> str:
    """indent=1 like every other eval artifact, except each receipt row, which prints on
    one line (6,000 rows at eight lines each would bloat the file for no reader)."""
    blocks = {}
    bp = doc.get("by_player")
    if isinstance(bp, dict):
        doc = dict(doc, by_player=dict(bp, freezes={}))
        for i, (name, fz) in enumerate((bp.get("freezes") or {}).items()):
            tok = f"__RECEIPT_ROWS_{i}__"
            blocks[tok] = fz.get("rows") or {}
            doc["by_player"]["freezes"][name] = dict(fz, rows=tok)
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    for tok, rows in blocks.items():
        body = ",\n".join(f"     {json.dumps(k, ensure_ascii=False)}: "
                           f"{json.dumps(v, separators=(',', ':'), ensure_ascii=False)}"
                           for k, v in rows.items())
        text = text.replace(json.dumps(tok), ("{\n" + body + "\n    }") if rows else "{}")
    return text + "\n"


def _paths(out_path, ledger_path, data_dir):
    d = Path(data_dir) if data_dir is not None else DATA_DIR
    real = d.resolve() == DATA_DIR.resolve()
    out = Path(out_path) if out_path else (OUT_PATH if real else d / "provisional_track_eval.json")
    led = Path(ledger_path) if ledger_path else (LEDGER_PATH if real else d / ".provisional_track_ledger.jsonl")
    return out, led


def commit_rows(cands: list[dict], *, out_path=None, ledger_path=None, data_dir=None,
                now_iso: str | None = None, by_player: dict | None = None) -> dict:
    out, led = _paths(out_path, ledger_path, data_dir)
    now_iso = now_iso or _now_iso()
    try:
        prev = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    durable = _read_jsonl(led)
    rows = merge_rows(list(prev.get("rows") or []), durable)
    rows, appended = apply(rows, cands, now_iso)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    if by_player is None:
        by_player = prev.get("by_player")
    tmp.write_text(_dumps(_doc(rows, now_iso, by_player)), encoding="utf-8")
    tmp.replace(out)
    in_ledger = {r.get("run_id") for r in durable}
    _append_jsonl(led, [r for r in rows if r.get("run_id") not in in_ledger])
    return {"status": "ok", "appended": [r["run_id"] for r in appended], "n_rows": len(rows),
            "out": str(out), "ledger": str(led)}


def update(as_of: str | None = None, *, out_path=None, ledger_path=None, data_dir=None,
           db_path=None, freeze_dir=None, B: int = 1000, retrospective: bool = True,
           now_iso: str | None = None) -> dict:
    """The nightly entry point: score every freeze as of today and append what changed."""
    as_of = as_of or datetime.date.today().isoformat()
    now_iso = now_iso or _now_iso()
    m2k = identity(data_dir)
    opin = opinions(db_path)
    cands = build_rows(as_of, freeze_dir=freeze_dir, data_dir=data_dir, db_path=db_path, B=B,
                       retrospective=retrospective, now_iso=now_iso, m2k=m2k, opin=opin)
    rec = receipts(as_of, freeze_dir=freeze_dir, m2k=m2k, opin=opin)
    res = commit_rows(cands, out_path=out_path, ledger_path=ledger_path, data_dir=data_dir,
                      now_iso=now_iso, by_player=rec)
    res["as_of"] = as_of
    res["n_candidates"] = len(cands)
    return res


def summary_line(res: dict) -> str:
    if res.get("status") != "ok":
        return str(res.get("status"))[:120]
    return (f"as of {res.get('as_of')}: {len(res.get('appended') or [])} row(s) appended of "
            f"{res.get('n_candidates')}, {res.get('n_rows')} total")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if "--print" in sys.argv:
        for r in build_rows(datetime.date.today().isoformat(), B=200):
            a = r["result"]["ANY"]
            print(r["run_id"], r["status"], "graded", a["graded_in_window"],
                  "pairs", a["level"]["n_first_fv"], "lead", a["level"].get("median_lead_days"),
                  "auc", (a["selection"].get("grade") or {}).get("auc"))
    else:
        print(summary_line(update()))
