# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV text family: the scouting-report text column for the screening lab (EFV3_B2;
SP/efv3/EFV3_PLAN.md s4, LANE_B.md F-B2, F-B3, F-B12 and the text rule in s3).

WHAT THIS BUILDS. For every F-LV row (efv_vintage_frame.build_frame) the scouting
report text that was published INSIDE the row's own window, cleaned of everything that
is a grade or a date, and per fold (side, V) one scalar per head:

    txt_skill_<side>   a tf-idf ridge from the cleaned report to the within-(side, V)
                       percentile residual of the skill target on the consensus
                       percentile offset u_c
    txt_time_<side>    the same document vector against the timing event residual on
                       u_c (the V2 timing head's target)

The columns are handed to the screening lab's candidate list (EFV3_B1) and to nothing
else: no served number, no ledger row, no progress row.

SOURCE. prospects.db `snapshots` rows whose source is in the row's `real_sources`
(a grader that published inside the window), whose snapshot_date lies inside the
window [V-01-01, min(V-05-01, debut)) and whose tools_json._extras.report exceeds
MIN_REPORT_CHARS. Sources with report text on a development vintage today:
mlb_pipeline (2011 on) and fangraphs (2019 on). Baseball America (2023 on), ESPN (2025
on), Just Baseball (2026) and TJStats (2026, tjstats_snapshots.writeup) never reach a
development or reserved vintage and are listed as "no rows" (NO_ROW_SOURCES).

THE VINTAGE RULE (LANE_B s3, F-B3). List vintages 2011 and 2012 are dropped outright:
128 of 152 (84.2 percent) of the 2011 Pipeline reports and 278 of 453 (61.4 percent) of
the 2012 reports name a year later than their own, i.e. a later page attached to an old
rank (VERIFY_round1.md b19). From 2013 on the residual is 1 to 3 percent (2013 8 of 696,
2014 13 of 676, 2015 19 of 993, 2016 25 of 997, 2017 31 of 996, 2018 31 of 995, 2019
27 of 995; 22,127 report rows, median 1,431 characters) and a per-report filter
applies: a report naming a four-digit year later than V (or an apostrophe year such as
'21 later than V) is DROPPED. The filter reads the year tokens before they are
stripped, so a later year anywhere in the text drops the report. On a surviving report
the tokens ETA and ETA:, every four-digit year, the present/future grade string
("Scouting Grades* (present/future): Hit: 3/4 | ... | Overall: 4/5", "Pitching grades:
Fastball: 80 | ... | Overall: 70"), every n/n pair and every FV token are removed
before tokenizing, so the column carries what the grade does not. The tokenizer keeps
letter tokens only: no year, grade, age or velocity digit ever enters the vocabulary.
The report's own date and length are recorded on the row (report_date, report_len), as
is byte-identical carried-forward text (report_carried: the same source published the
same bytes before the window).

THE FOLD (GATE s4.5). Tokenizer, vocabulary, idf and the ridge are fit on training
vintages strictly below V with every V-frame player excluded; fold_columns raises on
either violation. V rows only are scored. sklearn TfidfVectorizer (min_df MIN_DF) plus
Ridge (RIDGE_ALPHA) and nothing else: no embedding service, no network.

MISSINGNESS. report_absent is emitted on every row; tools/efv_text_balance.py runs the
DS-03 balance probe on it and writes the verdict under the key "text" of
data/efv_identity_balance.json. offered_columns() reads that verdict: on a side where
report_absent is not BALANCED the skill column is withheld and only the timing column
is offered.

BANS. This module reads no WAR, debut, label or major league column: labels and the
timing event arrive from the caller as arrays (the lab joins them, as
efv_v2_model.lv_training_rows does), the window the row carries is the only date
bound, and test_efv_text_features.py scans the source and poisons every outcome field.
Reserved list vintages 2020 and 2021 raise through efv_vintage_frame's guard. Nothing
groups, counts or averages rows by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md);
consensus enters only as the within-(side, V) percentile u_c.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import numpy as np

import efv_vintage_frame as F

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "prospects.db"
BALANCE_PATH = DATA_DIR / "efv_identity_balance.json"
#: The key the DS-03 probe on report_absent is written under in the balance receipt.
BALANCE_KEY = "text"

#: A report shorter than this is a stub (a one-line note), not a report.
MIN_REPORT_CHARS = 120
#: List vintages whose report text is backfilled (F-B3) and dropped outright.
DROPPED_VINTAGES: tuple[int, ...] = (2011, 2012)
#: The first list vintage with contemporaneous report text.
FIRST_TEXT_VINTAGE = 2013
#: Sources with report text on a development vintage (first vintage with text).
TEXT_SOURCES: dict[str, int] = {"mlb_pipeline": 2011, "fangraphs": 2019}
#: Text sources that reach no development or reserved vintage, with the first year
#: their text exists. Listed, never read.
NO_ROW_SOURCES: dict[str, str] = {
    "baseballamerica": "text from 2023",
    "espn": "text from 2025",
    "just_baseball": "text from 2026",
    "tjstats": "tjstats_snapshots.writeup, 2026 only",
}
#: Vectorizer and ridge settings (the only two sklearn objects used).
MIN_DF = 5
RIDGE_ALPHA = 1.0
#: Letter tokens of two or more characters: a digit never becomes a feature.
TOKEN_PATTERN = r"(?u)\b[a-z][a-z']+\b"
#: The column names per side and head.
COLUMN_HEADS: tuple[str, ...] = ("skill", "time")


def column_name(head: str, side: str) -> str:
    if head not in COLUMN_HEADS:
        raise ValueError(f"head must be one of {COLUMN_HEADS}, got {head!r}")
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    return f"txt_{head}_{side}"


# ---------------------------------------------------------------------------
# cleaning
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"(?<!\d)(20[0-4]\d)(?!\d)")
_ANY_YEAR_RE = re.compile(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)")
_APOS_YEAR_RE = re.compile(r"'(\d\d)(?!\d)")
_ETA_RE = re.compile(r"\bETA:?", re.IGNORECASE)
_GRADE_HEADER_RE = re.compile(
    r"(Scouting Grades\*?|Pitching grades|Hitting grades|Scouting grades)"
    r"\s*(\(present/future\))?\s*:?", re.IGNORECASE)
_TOOL_GRADE_RE = re.compile(
    r"\b[A-Z][A-Za-z]+(?: [A-Za-z]+)?:?\s*\d{1,2}(?:/\d{1,2})?\s*\|?")
_PIPE_RE = re.compile(r"\s*\|\s*")
_PAIR_RE = re.compile(r"(?<!\d)\d{1,2}/\d{1,2}(?!\d)")
_FV_RE = re.compile(r"(?<!\d)\d{2}\s*(?:/\s*\d{2}\s*)?FV\b|\bFV\b")
_WS_RE = re.compile(r"\s+")


def later_years(text: str, vintage: int) -> list[int]:
    """Every year the raw text names that is later than V: four-digit years and
    apostrophe years ('21 reads 2021, '98 reads 1998). Read BEFORE any stripping."""
    V = int(vintage)
    found = {int(m) for m in _YEAR_RE.findall(text or "")}
    for m in _APOS_YEAR_RE.findall(text or ""):
        nn = int(m)
        found.add(2000 + nn if nn <= 49 else 1900 + nn)
    return sorted(y for y in found if y > V)


def strip_grades_and_dates(text: str) -> str:
    """The report without its grade string, n/n pairs, FV tokens, ETA tokens and
    four-digit years, whitespace collapsed."""
    t = text or ""
    t = _GRADE_HEADER_RE.sub(" ", t)
    t = _TOOL_GRADE_RE.sub(" ", t)
    t = _FV_RE.sub(" ", t)
    t = _PAIR_RE.sub(" ", t)
    t = _ETA_RE.sub(" ", t)
    t = _ANY_YEAR_RE.sub(" ", t)
    t = _APOS_YEAR_RE.sub(" ", t)
    t = _PIPE_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()


def clean_report(text: str, vintage: int) -> dict:
    """{"text": cleaned or None, "dropped": bool, "later_years": [...]} for one report
    read at list vintage V. A report naming a later year is dropped whole."""
    later = later_years(text, vintage)
    if later:
        return {"text": None, "dropped": True, "later_years": later}
    return {"text": strip_grades_and_dates(text), "dropped": False, "later_years": []}


# ---------------------------------------------------------------------------
# the source rows
# ---------------------------------------------------------------------------

def _report_of(tools_json: str | None) -> str | None:
    if not tools_json:
        return None
    try:
        t = json.loads(tools_json)
    except (TypeError, ValueError):
        return None
    rep = ((t.get("_extras") or {}).get("report")) if isinstance(t, dict) else None
    if not isinstance(rep, str) or len(rep) <= MIN_REPORT_CHARS:
        return None
    return rep


def load_reports(sources=tuple(TEXT_SOURCES), *, db_path: Path | str = DB_PATH,
                 lo: str | None = None, hi: str | None = None) -> dict[str, list[dict]]:
    """{player_key: [{"source", "date", "text"}, ...]} for every `snapshots` row of a
    text source whose report exceeds MIN_REPORT_CHARS, dated in [lo, hi) when given.
    Read-only; the only database access in this module."""
    srcs = tuple(sources)
    q = ("SELECT player_key, source, snapshot_date, tools_json FROM snapshots "
         "WHERE source IN (%s) AND tools_json LIKE '%%report%%'" % ",".join("?" * len(srcs)))
    args: list = list(srcs)
    if lo:
        q += " AND snapshot_date >= ?"
        args.append(str(lo))
    if hi:
        q += " AND snapshot_date < ?"
        args.append(str(hi))
    q += " ORDER BY player_key, source, snapshot_date"
    out: dict[str, list[dict]] = {}
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        for pk, src, d, tj in con.execute(q, args):
            rep = _report_of(tj)
            if rep is None or not pk:
                continue
            out.setdefault(pk, []).append({"source": src, "date": str(d)[:10],
                                           "text": rep})
    finally:
        con.close()
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------

def attach_text(rows: list[dict], reports: dict[str, list[dict]]) -> list[dict]:
    """Each F-LV row with its in-window report text attached, as new dicts:

        report_text      the cleaned text of every included report, joined; None
        report_absent    1.0 when the row carries no text, else 0.0
        report_date      the latest included report's own snapshot_date
        report_len       raw characters over the included reports
        report_sources   [{"source", "date", "len", "carried", "sha256"}] included
        report_dropped   [{"source", "date", "later_years"}] dropped by the filter
        report_in_window 1.0 when any real source had a report inside the window
        report_carried   1.0 when any included report is byte-identical to a report
                         the same source published before the window
        report_vintage_dropped  True on a DROPPED_VINTAGES row (no text, by rule)

    Only a source in the row's real_sources counts, only a report dated inside the
    row's window, and per source the latest such report (the board as it stood).
    Reserved vintages raise. The row's debut is never read here: the window the frame
    row carries already ends at it."""
    out = []
    for r in rows:
        V = int(r["vintage"])
        F.guard_score_request(V, purpose="text")
        lo, hi = r["window"]
        row = dict(r, report_text=None, report_absent=1.0, report_date=None,
                   report_len=0, report_sources=[], report_dropped=[],
                   report_in_window=0.0, report_carried=0.0,
                   report_vintage_dropped=V in DROPPED_VINTAGES)
        if V in DROPPED_VINTAGES:
            out.append(row)
            continue
        real = set(r.get("real_sources") or ())
        pool = reports.get(r.get("player_key"), [])
        latest: dict[str, dict] = {}
        for rep in pool:
            if rep["source"] not in real:
                continue
            d = str(rep["date"])[:10]
            if not (lo <= d < hi):
                continue
            cur = latest.get(rep["source"])
            if cur is None or d > cur["date"]:
                latest[rep["source"]] = dict(rep, date=d)
        if not latest:
            out.append(row)
            continue
        row["report_in_window"] = 1.0
        texts = []
        for src in sorted(latest):
            rep = latest[src]
            c = clean_report(rep["text"], V)
            if c["dropped"]:
                row["report_dropped"].append({"source": src, "date": rep["date"],
                                              "later_years": c["later_years"]})
                continue
            carried = any(e["source"] == src and str(e["date"])[:10] < lo
                          and e["text"] == rep["text"] for e in pool)
            row["report_sources"].append({"source": src, "date": rep["date"],
                                          "len": len(rep["text"]),
                                          "carried": bool(carried),
                                          "sha256": _sha(rep["text"])})
            row["report_len"] += len(rep["text"])
            if carried:
                row["report_carried"] = 1.0
            if c["text"]:
                texts.append(c["text"])
        if texts:
            row["report_text"] = "\n".join(texts)
            row["report_absent"] = 0.0
            row["report_date"] = max(s["date"] for s in row["report_sources"])
        out.append(row)
    return out


def text_rows(side: str, vintages, *, universe: dict | None = None,
              reports: dict[str, list[dict]] | None = None,
              db_path: Path | str = DB_PATH, milb: bool = False,
              sidecars: bool = False) -> dict[int, list[dict]]:
    """{V: F-LV rows with text attached} for development vintages. Reserved vintages
    raise before any read. The frame is built without its MiLB block by default (the
    text builder needs the window, the real sources and the consensus only)."""
    vs = sorted(int(v) for v in vintages)
    for V in vs:
        F.guard_score_request(V, purpose="text")
    universe = universe if universe is not None else F.load_universe()
    if reports is None:
        # one year before the first vintage, so a carried-forward report is seen
        reports = load_reports(db_path=db_path, lo=f"{min(vs) - 1}-01-01",
                               hi=f"{max(vs)}-05-01")
    return {V: attach_text(F.build_frame(side, V, universe=universe, milb=milb,
                                         sidecars=sidecars), reports)
            for V in vs}


# ---------------------------------------------------------------------------
# the coverage receipt
# ---------------------------------------------------------------------------

def coverage_receipt(rows_by_side: dict[str, dict[int, list[dict]]]) -> dict:
    """Counts by (side, vintage) and nothing else: rows, rows with a report in the
    window, rows dropped by the anachronism filter (every in-window report named a
    later year), reports dropped, rows with text, rows whose text is carried-forward
    identical bytes, and the per-source report counts."""
    out: dict = {"by_side_vintage": {}, "sources": {}, "no_row_sources": dict(NO_ROW_SOURCES),
                 "dropped_vintages": list(DROPPED_VINTAGES), "min_report_chars": MIN_REPORT_CHARS}
    src_tot: dict[str, int] = {}
    for side, by_v in rows_by_side.items():
        for V, rows in sorted(by_v.items()):
            blk = {"rows": len(rows),
                   "with_report_in_window": sum(1 for r in rows if r["report_in_window"]),
                   "reports_dropped_later_year": sum(len(r["report_dropped"]) for r in rows),
                   "rows_dropped_later_year": sum(1 for r in rows if r["report_in_window"]
                                                  and r["report_absent"]),
                   "with_text": sum(1 for r in rows if not r["report_absent"]),
                   "carried_identical": sum(1 for r in rows if r["report_carried"]),
                   "vintage_dropped": V in DROPPED_VINTAGES,
                   "by_source": {}}
            for r in rows:
                for s in r["report_sources"]:
                    blk["by_source"][s["source"]] = blk["by_source"].get(s["source"], 0) + 1
                    src_tot[s["source"]] = src_tot.get(s["source"], 0) + 1
            lens = [r["report_len"] for r in rows if r["report_len"]]
            blk["median_report_len"] = int(np.median(lens)) if lens else None
            out["by_side_vintage"][f"{side}:{V}"] = blk
    out["sources"] = {s: src_tot.get(s, 0) for s in TEXT_SOURCES}
    return out


# ---------------------------------------------------------------------------
# the fold fit
# ---------------------------------------------------------------------------

def within_pct(values, groups) -> np.ndarray:
    """Within-group percentile (average rank / group size): the same formula as
    efv_v2_model.within_pct (test-pinned), kept here so the builder imports no model
    module."""
    vals = np.asarray(values, dtype=np.float64)
    out = np.zeros(vals.size)
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    for idx in by.values():
        ix = np.asarray(idx)
        v = vals[ix]
        order = np.argsort(v, kind="mergesort")
        ranks = np.empty(v.size)
        ranks[order] = np.arange(1, v.size + 1, dtype=np.float64)
        for u in np.unique(v):
            m = v == u
            if m.sum() > 1:
                ranks[m] = ranks[m].mean()
        out[ix] = ranks / v.size
    return out


def _offset(u_c: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """OLS of y on [1, u_c]: the consensus offset the text ridge is residual to."""
    X = np.column_stack([np.ones(u_c.size), u_c])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(b[0]), float(b[1])


def fit_vectorizer(docs: list[str], *, min_df: int = MIN_DF):
    """The tf-idf vectorizer fit on `docs` alone (the fold's training documents): its
    vocabulary holds no token absent from them. Raises ValueError on an empty
    vocabulary, as sklearn does."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(min_df=min_df, token_pattern=TOKEN_PATTERN,
                          strip_accents="unicode")
    vec.fit(docs)
    return vec


def fit_text_fold(train_docs: list[str | None], u_c_train, y_train,
                  test_docs: list[str | None], *, alpha: float = RIDGE_ALPHA,
                  min_df: int = MIN_DF) -> tuple[list[float | None], dict]:
    """One head's text scalar: tf-idf (fit on train_docs only) and a ridge from the
    document vector to y_train minus its OLS offset on u_c_train. Returns the ridge
    prediction for each test doc (None for a missing doc) and the fit receipt. The
    vocabulary is the training vocabulary: a token first seen at V is not in it. The
    scalar is the residual the text predicts; consensus is not added back."""
    from sklearn.linear_model import Ridge

    u_c_train = np.asarray(u_c_train, dtype=np.float64)
    y_train = np.asarray(y_train, dtype=np.float64)
    keep = [i for i, d in enumerate(train_docs) if d]
    info = {"n_train_docs": len(keep), "n_train_rows": len(train_docs),
            "alpha": float(alpha), "min_df": int(min_df), "vocab_size": 0,
            "offset": None, "status": "no_fit"}
    if len(keep) < max(2 * min_df, 10):
        return [None] * len(test_docs), info
    a, b = _offset(u_c_train[keep], y_train[keep])
    resid = y_train[keep] - (a + b * u_c_train[keep])
    try:
        vec = fit_vectorizer([train_docs[i] for i in keep], min_df=min_df)
    except ValueError:
        return [None] * len(test_docs), info
    X = vec.transform([train_docs[i] for i in keep])
    info["vocab_size"] = int(len(vec.vocabulary_))
    info["offset"] = {"intercept": round(a, 6), "slope_u_c": round(b, 6)}
    if info["vocab_size"] == 0:
        return [None] * len(test_docs), info
    ridge = Ridge(alpha=alpha)
    ridge.fit(X, resid)
    info["status"] = "ok"
    info["resid_sd_train"] = round(float(resid.std()), 6)
    out: list[float | None] = [None] * len(test_docs)
    tix = [i for i, d in enumerate(test_docs) if d]
    if tix:
        pred = ridge.predict(vec.transform([test_docs[i] for i in tix]))
        for i, p in zip(tix, pred):
            out[i] = float(p)
    info["n_test_docs"] = len(tix)
    info["n_test_rows"] = len(test_docs)
    return out, info


def fold_columns(side: str, vintage: int, train_rows: list[dict], test_rows: list[dict],
                 *, target, event, offered=COLUMN_HEADS, alpha: float = RIDGE_ALPHA,
                 min_df: int = MIN_DF) -> dict:
    """The text columns for fold (side, V).

    train_rows: labelled rows at vintages strictly below V (each with player_key,
    vintage, fv, report_text), every V-frame player excluded; `target` is the skill
    target per training row (its within-(side, vintage) percentile is taken here) and
    `event` the timing event per training row (0/1), both joined by the caller.
    test_rows: the V rows (player_key, vintage, fv, report_text). The training
    percentiles are within vintage over EVERY training row of that vintage, text or
    not, so a row's u_c is the frame's. Returns {"columns": {player_key: {column: value
    or None}}, "fits": {...}, "offered": [...]}; a head not in `offered` is withheld
    (offered_columns)."""
    V = int(vintage)
    F.guard_score_request(V, purpose="text fold")
    if side not in F.SIDES:
        raise ValueError(f"side must be one of {F.SIDES}, got {side!r}")
    tv = {int(r["vintage"]) for r in train_rows}
    if any(v >= V for v in tv):
        raise ValueError(f"training vintages must be strictly below {V}, got {sorted(tv)}")
    if any(v in F.RESERVED_LV for v in tv):
        raise F.ReservedFrameError(f"a reserved vintage is in the training rows: {sorted(tv)}")
    test_keys = {r["player_key"] for r in test_rows}
    leak = sorted(test_keys & {r["player_key"] for r in train_rows})
    if leak:
        raise ValueError(f"{len(leak)} V-frame players are in the training rows "
                         f"(GATE s4.5), first {leak[:3]}")
    if any(int(r["vintage"]) != V for r in test_rows):
        raise ValueError("every test row must be at V")
    target = np.asarray([np.nan if t is None else float(t) for t in target], dtype=np.float64)
    event = np.asarray([np.nan if e is None else float(e) for e in event], dtype=np.float64)
    if target.size != len(train_rows) or event.size != len(train_rows):
        raise ValueError("target and event must align with train_rows")
    u_c_tr = within_pct([float(r["fv"]) for r in train_rows],
                        [int(r["vintage"]) for r in train_rows])
    docs_tr = [r.get("report_text") for r in train_rows]
    docs_te = [r.get("report_text") for r in test_rows]
    heads = {}
    cols = {r["player_key"]: {} for r in test_rows}
    offered = tuple(h for h in COLUMN_HEADS if h in tuple(offered))
    for head in offered:
        name = column_name(head, side)
        if head == "skill":
            ok = ~np.isnan(target)
            y = np.full(target.size, np.nan)
            # the within-(side, vintage) percentile of the skill target, labelled rows
            ix = np.flatnonzero(ok)
            if ix.size:
                y[ix] = within_pct(target[ix], [int(train_rows[i]["vintage"]) for i in ix])
        else:
            ok = ~np.isnan(event)
            y = event
        tr_docs = [d if ok[i] else None for i, d in enumerate(docs_tr)]
        scores, info = fit_text_fold(tr_docs, u_c_tr, np.where(ok, y, 0.0), docs_te,
                                     alpha=alpha, min_df=min_df)
        info["column"] = name
        info["n_train_labelled"] = int(ok.sum())
        heads[name] = info
        for r, s in zip(test_rows, scores):
            cols[r["player_key"]][name] = s
    return {"side": side, "vintage": V, "train_vintages": sorted(tv),
            "offered": [column_name(h, side) for h in offered],
            "columns": cols, "fits": heads}


# ---------------------------------------------------------------------------
# which columns are offered (the DS-03 verdict on report_absent)
# ---------------------------------------------------------------------------

def balance_verdict(side: str, path: Path | None = None) -> str | None:
    """The DS-03 verdict on report_absent for the side from the balance receipt's
    "text" key, or None when the probe has not been run."""
    p = BALANCE_PATH if path is None else Path(path)
    if not p.exists():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    blk = ((doc.get(BALANCE_KEY) or {}).get("balance") or {}).get(side) or {}
    v = (blk.get("report_absent") or {}).get("verdict")
    return str(v) if v else None


def offered_columns(side: str, path: Path | None = None) -> tuple[str, ...]:
    """The heads the text column is offered to on a side: both when report_absent
    reads BALANCED, the timing head alone otherwise (IMBALANCED, CONSTANT or no
    probe yet: a skill column is never offered on an unproven missingness)."""
    v = balance_verdict(side, path)
    return tuple(COLUMN_HEADS) if v == "BALANCED" else ("time",)
