# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools for stale-graded players: eTools amendment 4 (owner decision EW3-46, 2026-10-19),
built to docs/tools-2026-10/ETOOLS_AMENDMENT_4.md, which was committed alone before this
module scored anything.

WHAT IT ASKS. The served eTools (etools.py) cover only players with a tool grade on a 2026
list. The eFV board carries older grades forward: a player whose last tool grade is from an
earlier list (justin_riemer: FanGraphs only, 2024-08-01) shows that consensus grade. Does
the eTool's gain over the consensus tool grade HOLD when that grade is stale? Each passing
eTool (hit, game power, pitch selection, bat control, fastball, command) is rebuilt on
development rows whose consensus grade predates the board-year lists: the latest grade of
each outlet dated before the board-year window (the carried-forward consensus), the
admitted sub-drivers read as of the board year exactly as for fresh rows, the fit trained
on fresh rows of the other board years and re-centred on the test year's fresh rows (the
served construction). The deciding stratum is the rows whose grade was 12 or more months
old at the read date (May 1 of the board year). Zero comparator, permuted null and planted
recovery beside every verdict.

WHAT IT SERVES. A tool that HOLDS on the stale rows (one-sided 95% lower bound above 0 on
both labels, the null not clearing) is served for live eFV-board players whose latest
consensus grade for it predates the 2026 lists, with the grade's date and age carried
beside it; every other tool keeps the consensus grade for those players. The live stale
records use the look's final fit and the live fresh cohort's re-centring shift unchanged,
so no fresh player's eTool moves.

BANS. Development board years only; no grade from a 2020 or 2021 list is read on a
development row (R-LV); no grouping, key, filter or weight by consensus FV or any source's
FV (docs/PROSPECT_ANCHOR_GATE.md); never backtest.run_backtest, run_monthly or build_site
from the runner; no network request.

Run:  python etools_stale.py --check                      (rows, ages, label presence; no statistic)
      python etools_stale.py --dry-run                    (the read's path on fixtures)
      python etools_stale.py --run --amend-sha SHA        (the one read)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import etools as E  # noqa: E402

AMEND_DOC = "docs/tools-2026-10/ETOOLS_AMENDMENT_4.md"
READS_PATH = E.LAB_DIR / "etools_stale_reads.json"
XFV_PATH = E.DATA / "xfv.json"
#: the deciding stratum: grade age at the read date of 365 days or more
STALE_DAYS = 365
#: the development read date: the end of the gate 1.2 window (May 1 of the board year)
READ_MMDD = "-05-01"
#: R-LV list vintages: no development row reads a grade from these list years
RESERVED_LIST_YEARS = (2020, 2021)
NULL_SEED = 20261025
PLANT_SEED = 20261026
PLANT_LOAD = 0.25


class StaleGuard(RuntimeError):
    """An amendment 4 guard failed."""


# ---------------------------------------------------------------------------
# the carried-forward board
# ---------------------------------------------------------------------------
def _snapshots() -> dict:
    """{(source, player_key): [(date, tools, position), ...]} ascending by date, tools
    parsed exactly as etools.load_board (future grades in [20, 80], the Pipeline report
    grades, FanGraphs arm as throw)."""
    import efv_w2_scout as SC
    con = sqlite3.connect(f"file:{E.db_path().as_posix()}?mode=ro", uri=True)
    out: dict = defaultdict(list)
    try:
        q = ("SELECT source, snapshot_date, player_key, position, tools_json FROM snapshots "
             "WHERE source IN (?, ?, ?) AND tools_json IS NOT NULL AND tools_json != '' "
             "ORDER BY snapshot_date ASC")
        for src, sd, pk, pos, tj in con.execute(q, E.SOURCES):
            sd = str(sd or "")[:10]
            if not pk or len(sd) < 10:
                continue
            try:
                t = json.loads(tj)
            except ValueError:
                continue
            if not isinstance(t, dict):
                continue
            ex = t.get("_extras") if isinstance(t.get("_extras"), dict) else {}
            tools = {k: E._parse_grade(v) for k, v in t.items() if k != "_extras"}
            tools = {k: v for k, v in tools.items() if v is not None}
            if src == "mlb_pipeline":
                fut, _pre = SC.report_grades(ex.get("report"))
                for k, v in fut.items():
                    if k not in tools and v is not None:
                        tools[k] = float(v)
            if src == "fangraphs" and "throw" not in tools:
                arm = E._parse_grade(ex.get("arm"))
                if arm is not None:
                    tools["throw"] = arm
            out[(src, pk)].append((sd, tools, pos))
    finally:
        con.close()
    return out


def latest_before(snaps: list, cutoff: str, *, skip_years=()) -> dict:
    """Per tool the latest grade dated before `cutoff`: {tool: (grade, date)}; with
    skip_years, a tool whose latest grade falls in a skipped list year maps to
    (None, date) so the caller can drop the row (never an older substitute)."""
    out: dict = {}
    for sd, tools, _pos in snaps:
        if sd >= cutoff:
            break
        for k, v in tools.items():
            out[k] = (v, sd)
    if skip_years:
        out = {k: ((None, d) if int(d[:4]) in skip_years else (v, d)) for k, (v, d) in out.items()}
    return out


def stale_board(fresh: dict, years, *, live: bool = False, snaps: dict | None = None) -> tuple[dict, dict]:
    """The carried-forward board: {(Y, source, player_key): {"tools", "dates", "extras",
    "position", "date"}} holding, per (Y, player), only the tools NO outlet graded on the
    board-year lists (the fresh board); each outlet's latest grade dated before the
    window (live: before etools.LIVE_FROM). Development rows whose carried-forward grade
    for a tool would come from a 2020 or 2021 list drop that tool (counted)."""
    snaps = _snapshots() if snaps is None else snaps
    fresh_tools: dict = defaultdict(set)
    for (Y, _src, pk), slot in fresh.items():
        fresh_tools[(Y, pk)].update(slot["tools"])
    counts: dict = defaultdict(int)
    by_pk: dict = defaultdict(dict)
    for (src, pk), lst in snaps.items():
        by_pk[pk][src] = lst
    out: dict = {}
    for Y in years:
        cutoff = E.LIVE_FROM if live else f"{Y}-01-01"
        Yk = 0 if live else Y
        for pk, per in by_pk.items():
            lat = {src: latest_before(lst, cutoff, skip_years=() if live else RESERVED_LIST_YEARS)
                   for src, lst in per.items()}
            tools_any = set().union(*[set(v) for v in lat.values()]) if lat else set()
            stale_tools = tools_any - fresh_tools.get((Yk, pk), set())
            if not stale_tools:
                continue
            drop = {t for t in stale_tools if any((v.get(t) or (0, ""))[0] is None and t in v for v in lat.values())}
            counts["tools_dropped_reserved_list_year"] += len(drop)
            stale_tools -= drop
            if not stale_tools:
                continue
            for src, v in lat.items():
                tl = {t: v[t][0] for t in stale_tools if t in v}
                if not tl:
                    continue
                dates = {t: v[t][1] for t in tl}
                pos = None
                for sd, _tools, p in per[src]:
                    if sd >= cutoff:
                        break
                    pos = p or pos
                out[(Yk, src, pk)] = {"tools": tl, "dates": dates, "extras": {}, "position": pos,
                                      "date": max(dates.values())}
    counts["slots"] = len(out)
    return out, dict(counts)


def read_date(Y: int) -> str:
    return f"{Y}{READ_MMDD}"


def age_days(grade_date: str, asof: str) -> int:
    return (date.fromisoformat(asof[:10]) - date.fromisoformat(grade_date[:10])).days


def attach_grade_dates(rows: list[dict], board: dict, *, asof_live: str | None = None) -> None:
    """Per row and tool: the carried-forward consensus grade's date (the latest date among
    the outlets averaged) and its age in days at the read date."""
    for r in rows:
        Yk = r["year"]
        gd: dict = {}
        for src in E.SOURCES:
            slot = board.get((Yk, src, r["player_key"]))
            if not slot:
                continue
            for t, d in slot["dates"].items():
                if gd.get(t) is None or d > gd[t]:
                    gd[t] = d
        asof = asof_live if (Yk == 0 and asof_live) else read_date(Yk)
        r["grade_date"] = gd
        r["grade_age_days"] = {t: age_days(d, asof) for t, d in gd.items()}


def side_conflicts(stale_rows: list[dict], fresh_rows: list[dict]) -> list[dict]:
    """Drop a stale row whose (year, player) has a fresh row on the other side (an old
    hitter grade on a player the board-year lists grade as a pitcher, and so on)."""
    side = {(r["year"], r["pid"]): r["side"] for r in fresh_rows}
    return [r for r in stale_rows if side.get((r["year"], r["pid"]), r["side"]) == r["side"]]


# ---------------------------------------------------------------------------
# the frames
# ---------------------------------------------------------------------------
def dev_frames(*, log=print) -> dict:
    """Fresh rows (the look's frame, unchanged) and stale rows, candidates attached once
    over both (no PASS-tool candidate depends on the row set), labels on both."""
    E.guard_years(E.DEV_YEARS)
    fresh_board = E.load_board(E.DEV_YEARS)
    st_board, st_counts = stale_board(fresh_board, E.DEV_YEARS)
    fresh_rows, counts = E.build_universe(fresh_board, E.DEV_YEARS, log=log)
    stale_rows, s_counts = E.build_universe(st_board, E.DEV_YEARS, log=log)
    n0 = len(stale_rows)
    stale_rows = side_conflicts(stale_rows, fresh_rows)
    s_counts = dict(s_counts, side_conflict_dropped=n0 - len(stale_rows), **st_counts)
    for r in stale_rows:
        r["stale"] = True
    E.attach_candidates(fresh_rows + stale_rows, last_season=max(E.DEV_YEARS) - 1, log=log)
    E.attach_labels(fresh_rows + stale_rows, log=log)
    attach_grade_dates(stale_rows, st_board)
    for r in fresh_rows + stale_rows:
        if r["year"] in E.RESERVED_BOARD_YEARS:
            raise StaleGuard("reserved board year in the frame")
        for _t, v in (r.get("labels") or {}).items():
            if v.get("mlb") is not None and (r.get("mlb_first") is None or r["mlb_first"] > E.MAX_DEBUT_YEAR):
                raise StaleGuard("an L_MLB row whose first MLB season is after 2024")
    for r in stale_rows:
        for t, d in r["grade_date"].items():
            if int(d[:4]) in RESERVED_LIST_YEARS:
                raise StaleGuard(f"a development row reads a {d[:4]} list grade")
            if d >= f"{r['year']}-01-01":
                raise StaleGuard("a stale grade dated inside the board-year window")
    ff, sf = E.tool_frames(fresh_rows), E.tool_frames(stale_rows)
    ages = {}
    by_key = {(r["year"], r["pid"]): r for r in stale_rows}
    for tool, fr in sf.items():
        ages[tool] = np.array([by_key[k]["grade_age_days"].get(tool, np.nan) for k in fr.keys], float)
    T = E.um_tables(E.ANY_LEVELS, tracked=False)
    y_any = {}
    for tool in E.PASS_TOOLS:
        if tool not in E.ANY_TOOLS:
            continue
        y_any[tool] = {}
        for name, frames, rws in (("fresh", ff, fresh_rows), ("stale", sf, stale_rows)):
            side = {(r["year"], r["pid"]): r["side"] for r in rws}
            vals = [E.um_label(tool, pid, Y, side[(Y, pid)], T) for (Y, pid) in frames[tool].keys]
            y_any[tool][name] = np.array([np.nan if v is None else v for v in vals], float)
    return {"fresh": ff, "stale": sf, "ages": ages, "y_any": y_any, "fresh_counts": counts,
            "stale_counts": s_counts}


def check(log=print) -> dict:
    """Counts only: stale rows per passing tool, by board year and age class, with label
    presence. No grade or candidate is paired with a label."""
    d = dev_frames(log=log)
    out = {"fresh_universe": d["fresh_counts"], "stale_universe": d["stale_counts"], "per_tool": {}}
    for tool in E.PASS_TOOLS:
        st, ag = d["stale"][tool], d["ages"][tool]
        old = ag >= STALE_DAYS
        rec = {"stale_rows": st.n, "players": int(np.unique(st.pid).size),
               "age12_rows": int(old.sum()), "under12_rows": int((~old).sum()),
               "age_days_quartiles": [int(v) for v in np.percentile(ag, [25, 50, 75])] if st.n else None,
               "by_year": {int(y): int((st.year == y).sum()) for y in np.unique(st.year)},
               "by_year_age12": {int(y): int(((st.year == y) & old).sum()) for y in np.unique(st.year)}}
        adm = None
        try:
            look = json.loads(E.EVAL_PATH.read_text(encoding="utf-8"))
            adm = list(look["etools"][tool]["admitted"])
        except (OSError, ValueError, KeyError):
            pass
        labs = dict(st.y)
        if tool in d["y_any"]:
            labs["any"] = d["y_any"][tool]["stale"]
        for lb, yv in labs.items():
            has = np.isfinite(yv)
            rec[f"label_{lb}"] = {"rows": int(has.sum()), "age12_rows": int((has & old).sum()),
                                  "age12_players": int(np.unique(st.pid[has & old]).size),
                                  "age12_years_20plus": int(sum(1 for y in np.unique(st.year[has & old])
                                                                if ((st.year == y) & has & old).sum() >= E.THIN))}
        if adm:
            Z = np.column_stack([st.cands[c] for c in adm])
            rec["age12_rows_with_a_subdriver"] = int((old & np.any(np.isfinite(Z), axis=1)).sum())
        out["per_tool"][tool] = rec
    out["live"] = live_check(log=log)
    return out


# ---------------------------------------------------------------------------
# the live stale cohort
# ---------------------------------------------------------------------------
def board_keys() -> set:
    """The eFV board's live prospects (data/xfv.json, kind active)."""
    try:
        d = json.loads(XFV_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {k for k, v in (d.get("by_player") or {}).items() if (v or {}).get("kind") == "active"}


def live_stale_rows(*, asof: str | None = None, log=print) -> list[dict]:
    """Live eFV-board players with a tool whose latest consensus grade predates the 2026
    lists: the carried-forward grades, candidates read through season 2026."""
    asof = asof or date.today().isoformat()
    fresh = E.load_board(live_from=E.LIVE_FROM)
    st_board, _c = stale_board(fresh, (0,), live=True)
    keys = board_keys()
    st_board = {k: v for k, v in st_board.items() if k[2] in keys}
    rows, _counts = E.build_universe(st_board, (E.LAST_MLB_SEASON + 1,), log=log, live=True)
    fresh_rows, _fc = E.build_universe(fresh, (E.LAST_MLB_SEASON + 1,), log=lambda *a, **k: None, live=True)
    rows = side_conflicts(rows, fresh_rows)
    E.attach_candidates(rows, last_season=E.LAST_MLB_SEASON, log=log)
    attach_grade_dates(rows, st_board, asof_live=asof)
    return rows


def live_check(log=print) -> dict:
    rows = live_stale_rows(log=log)
    out = {}
    for tool in E.PASS_TOOLS:
        spec = E.TOOLS[tool]
        sel = [r for r in rows if r["side"] == spec["side"]
               and any((v or {}).get(tool) is not None for v in r["per_source"].values())]
        ages = [r["grade_age_days"][tool] for r in sel if tool in r["grade_age_days"]]
        out[tool] = {"players": len(sel), "age12": int(sum(a >= STALE_DAYS for a in ages)),
                     "age_days_quartiles": [int(v) for v in np.percentile(ages, [25, 50, 75])] if ages else None}
    return out


# ---------------------------------------------------------------------------
# the read (amendment 4, section 3 to 5)
# ---------------------------------------------------------------------------
def stale_oof(fr, st, admitted: list[str], *, Zf=None, Zs=None) -> dict:
    """Per test board year Y with stale rows: the gate 5.1 fit on FRESH rows of the other
    board years with every year-Y player (fresh or stale) removed, applied to the stale
    year-Y rows; re-centred (amendment 2 F1.5) with delta = the mean residual over the
    FRESH year-Y rows minus the training mean (the served construction). Returns the
    re-centred and uncentred predictions on the stale rows, and the fits' c."""
    Zf = np.column_stack([fr.cands[c] for c in admitted]) if Zf is None else Zf
    Zs = np.column_stack([st.cands[c] for c in admitted]) if Zs is None else Zs
    pred_rc = np.full(st.n, np.nan)
    pred_unc = np.full(st.n, np.nan)
    cs = {}
    for Y in np.unique(st.year):
        te_s = st.year == Y
        te_f = fr.year == Y
        players = np.union1d(np.unique(fr.pid[te_f]), np.unique(st.pid[te_s]))
        tr = (fr.year != Y) & ~np.isin(fr.pid, players)
        fit = E.etool_fit(fr.gc, Zf, fr.y, tr)
        if fit is None:
            continue
        U = E.etool_residuals(fr.gc, Zf, fit["lines"])
        delta = E._present_mean(U, Zf, te_f) - E._present_mean(U, Zf, tr)
        rc, _ = E.etool_centred(st.gc[te_s], Zs[te_s], fit["lines"], fit["c"], delta)
        pred_rc[te_s] = rc
        pred_unc[te_s] = E.etool_apply(st.gc[te_s], Zs[te_s], fit)
        cs[int(Y)] = [E._r(v, 5) for v in fit["c"]]
    return {"pred_rc": pred_rc, "pred_unc": pred_unc, "c": cs}


def _masked(y, mask):
    y = np.asarray(y, float).copy()
    y[~np.asarray(mask, bool)] = np.nan
    return y


def stratum_read(st, pred, mask, labels: dict, second: str | None, *, Bn: int = E.B) -> dict:
    """Gate 5.2 on the stale rows in `mask`: d_E = rho_w(eTool) - rho_w(G_s) per label, the
    amendment 2 F3.2 bootstrap. HOLDS (section 4.2) when the lower bound is above 0 on L_UM
    and on the second label."""
    out = {}
    for lb, y in labels.items():
        out[lb] = E.paired_d(pred, st.gc, _masked(y, mask), st.year, st.pid, Bn=Bn)
    out["holds"] = bool(second is not None and E._lb_pos(out.get("um")) and E._lb_pos(out.get(second)))
    return out


def second_label(st, mask, labels: dict) -> str | None:
    """Section 4.2: L_MLB when computable on the stratum, else L_ANY when the tool has it and
    it is computable; None when L_UM or both are not computable (presence only)."""
    def comp(lb):
        y = labels.get(lb)
        if y is None:
            return False
        m = mask & np.isfinite(y)
        return E.computable(st.year[m], st.pid[m])
    if not comp("um"):
        return None
    if comp("mlb"):
        return "mlb"
    if comp("any"):
        return "any"
    return None


def normal_rank_score(y, year) -> np.ndarray:
    """Per board year, the normal score of each row's rank among the rows carrying y;
    0 where y is missing."""
    from scipy.stats import norm, rankdata
    y = np.asarray(y, float)
    out = np.zeros(y.size)
    for Y in np.unique(year):
        m = (year == Y) & np.isfinite(y)
        n = int(m.sum())
        if n < 2:
            continue
        out[m] = norm.ppf((rankdata(y[m]) - 0.5) / n)
    return out


def planted_candidate(year, y_um, y_second, carrier, seed: int) -> np.ndarray:
    """Section 5.3: 0.25 x (z rank L_UM + z rank of the second label) + sqrt(1 - 0.125) x
    noise, on the rows carrying the tool's first admitted sub-driver."""
    rng = np.random.default_rng(seed)
    s = PLANT_LOAD * (normal_rank_score(y_um, year) + normal_rank_score(y_second, year))
    s = s + np.sqrt(1.0 - 2 * PLANT_LOAD ** 2) * rng.standard_normal(s.size)
    return np.where(np.isfinite(carrier), s, np.nan)


def tool_read(fr, st, ages, admitted: list[str], *, y_any: dict | None = None, Bn: int = E.B) -> dict:
    """One passing tool: S12 (deciding), U12, ALL and the two S12 age cells; the zero
    comparator, the permuted null and planted recovery on S12. y_any = {"fresh", "stale"}
    L_ANY arrays for the tools that have it."""
    old = np.isfinite(ages) & (ages >= STALE_DAYS)
    young = np.isfinite(ages) & (ages < STALE_DAYS)
    labels = {"mlb": st.y["mlb"], "um": st.y["um"]}
    if y_any is not None:
        labels["any"] = y_any["stale"]
    second = second_label(st, old, labels)
    Zf = np.column_stack([fr.cands[c] for c in admitted])
    Zs = np.column_stack([st.cands[c] for c in admitted])
    o = stale_oof(fr, st, admitted, Zf=Zf, Zs=Zs)
    shift = (o["pred_rc"] - st.gc)[old & np.isfinite(o["pred_rc"])]
    rec = {"admitted": admitted, "rows": st.n, "age12_rows": int(old.sum()), "under12_rows": int(young.sum()),
           "second_label": second, "fold_c": o["c"],
           "rows_with_a_subdriver_age12": int((old & np.any(np.isfinite(Zs), axis=1)).sum()),
           "mean_shift_age12": E._r(float(shift.mean()), 3) if shift.size else None,
           "sd_shift_age12": E._r(float(shift.std()), 3) if shift.size else None}
    rec["S12"] = stratum_read(st, o["pred_rc"], old, labels, second, Bn=Bn)
    rec["S12_uncentred"] = stratum_read(st, o["pred_unc"], old, labels, second, Bn=Bn)
    rec["U12"] = stratum_read(st, o["pred_rc"], young, labels, second, Bn=Bn)
    rec["ALL"] = stratum_read(st, o["pred_rc"], old | young, labels, second, Bn=Bn)
    rec["S12_age_365_729"] = stratum_read(st, o["pred_rc"], old & (ages < 730), labels, second, Bn=Bn)
    rec["S12_age_730_plus"] = stratum_read(st, o["pred_rc"], old & (ages >= 730), labels, second, Bn=Bn)
    # 5.1 zero comparator: every sub-driver contribution 0, so the eTool is G_s and d is 0
    zc = np.zeros(len(admitted))
    zero_pred = np.full(st.n, np.nan)
    for Y in np.unique(st.year):
        te = st.year == Y
        zero_pred[te], _ = E.etool_centred(st.gc[te], Zs[te], [(0.0, 0.0, False)] * len(admitted), zc, zc)
    rec["zero_comparator"] = {lb: E.paired_d(zero_pred, st.gc, _masked(y, old), st.year, st.pid, Bn=0).get("d")
                              for lb, y in labels.items()}
    # 5.2 permuted null: each stale row's sub-driver vector shuffled within board year
    rng = np.random.default_rng(NULL_SEED)
    Zn = Zs.copy()
    for Y in np.unique(st.year):
        mm = np.flatnonzero(st.year == Y)
        Zn[mm] = Zs[rng.permutation(mm)]
    on = stale_oof(fr, st, admitted, Zf=Zf, Zs=Zn)
    rec["null"] = stratum_read(st, on["pred_rc"], old, labels, second, Bn=Bn)
    # 5.3 planted recovery: one synthetic sub-driver on fresh and stale rows
    if second is not None:
        f_second = fr.y["mlb"] if second == "mlb" else (y_any or {}).get("fresh")
        pf = planted_candidate(fr.year, fr.y["um"], f_second, Zf[:, 0], PLANT_SEED)
        ps = planted_candidate(st.year, st.y["um"], labels[second], Zs[:, 0], PLANT_SEED + 1)
        op = stale_oof(fr, st, ["planted"], Zf=pf[:, None], Zs=ps[:, None])
        rec["planted"] = stratum_read(st, op["pred_rc"], old, labels, second, Bn=Bn)
    else:
        rec["planted"] = {"holds": False, "computable": False}
    rec["verdict"] = verdict(rec)
    return rec


def verdict(rec: dict) -> str:
    """Section 5.4: NOT COMPUTABLE, VOID, HOLDS, DOES NOT HOLD; UNDERPOWERED or DOES NOT HOLD."""
    if rec.get("second_label") is None:
        return "NOT COMPUTABLE"
    if rec["null"].get("holds"):
        return "VOID"
    if rec["S12"].get("holds"):
        return "HOLDS"
    if not rec["planted"].get("holds"):
        return "DOES NOT HOLD; UNDERPOWERED"
    return "DOES NOT HOLD"


def amend_sha_ok(sha: str | None) -> bool:
    return E.gate_sha_ok(sha, AMEND_DOC)


def reads_spent() -> str | None:
    if READS_PATH.exists():
        try:
            d = json.loads(READS_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return f"{READS_PATH} is unparseable"
        if d.get("spent"):
            return f"{READS_PATH} carries a spent marker ({d.get('spent_at')})"
    return None


def input_shas() -> dict:
    s = E.input_shas()
    s[XFV_PATH.name] = E.sha256_of(XFV_PATH)
    return s


def run(amend_sha: str, *, log=print) -> dict:
    why = reads_spent()
    if why:
        raise StaleGuard(f"the read is spent: {why}")
    if not amend_sha_ok(amend_sha):
        raise StaleGuard(f"{amend_sha} does not name a commit carrying {AMEND_DOC} as REGISTERED")
    look = json.loads(E.EVAL_PATH.read_text(encoding="utf-8"))
    flip = json.loads(E.FLIP_PATH.read_text(encoding="utf-8"))
    E.guard_no_fv(["board_year", "grade_age"])
    shas_start = input_shas()
    t0 = time.time()
    d = dev_frames(log=log)
    if d["fresh_counts"].get("rows") != (look.get("universe") or {}).get("rows"):
        raise StaleGuard(f"fresh rows {d['fresh_counts'].get('rows')} differ from the look's "
                         f"{(look.get('universe') or {}).get('rows')}")
    started = E._now()
    log(f"  inputs built in {time.time() - t0:.0f} s; the read begins")
    reads, repro = {}, {}
    try:
        for tool in E.PASS_TOOLS:
            fr = d["fresh"][tool]
            adm = list(look["etools"][tool]["admitted"])
            det = E.etool_oof_detail(fr, adm)
            for lb in E.LABELS:
                want = flip["F1_drift_recentring"][tool]["recentred_vs_consensus"][lb]["d"]
                got = E.paired_d(det["pred_rc"], fr.gc, fr.y[lb], fr.year, fr.pid, Bn=0).get("d")
                repro[f"{tool}:{lb}"] = {"flip_prep": want, "now": got}
                if got is None or abs(got - want) > 5e-5:
                    raise StaleGuard(f"{tool} {lb}: fresh d {got} does not reproduce the flip prep's {want}")
            rec = tool_read(fr, d["stale"][tool], d["ages"][tool], adm, y_any=d["y_any"].get(tool))
            rec["fresh_reference"] = {lb: flip["F1_drift_recentring"][tool]["recentred_vs_consensus"][lb]
                                      for lb in E.LABELS}
            reads[tool] = rec
            log(f"  {tool:9s} S12 " + "; ".join(f"{lb} d {v.get('d')} lb {v.get('lb95')}"
                                              for lb, v in rec["S12"].items() if isinstance(v, dict))
                + f"; second {rec['second_label']}; {rec['verdict']}")
    except Exception as exc:                                         # noqa: BLE001
        E.LAB_DIR.mkdir(parents=True, exist_ok=True)
        READS_PATH.write_text(json.dumps({"item": "ETOOLS_STALE_GRADES", "spent": True, "spent_at": E._now(),
                                          "amendment_sha": amend_sha, "error": f"{type(exc).__name__}: {exc}",
                                          "traceback": traceback.format_exc(), "started": started}, indent=1),
                              encoding="utf-8", newline="\n")
        raise
    doc = {"item": "ETOOLS_STALE_GRADES", "tool": "etools_stale.py", "spent": True, "spent_at": E._now(),
           "started": started, "amendment_doc": AMEND_DOC, "amendment_sha": amend_sha,
           "head": (E._git("rev-parse", "HEAD") or "").strip(), "survivorship": E.SURVIVORSHIP,
           "constants": {"B": E.B, "seed": E.SEED, "stale_days": STALE_DAYS, "read_date": "board year" + READ_MMDD,
                         "reserved_list_years": RESERVED_LIST_YEARS, "null_seed": NULL_SEED,
                         "plant_seed": PLANT_SEED, "plant_load": PLANT_LOAD},
           "fresh_universe": d["fresh_counts"], "stale_universe": d["stale_counts"], "reproduction": repro,
           "reads": reads, "serve": {t: reads[t]["verdict"] == "HOLDS" for t in reads},
           "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
           "seconds": round(time.time() - t0, 1)}
    if doc["inputs_sha256_start"] != doc["inputs_sha256_end"]:
        doc["input_drift"] = True
    E.LAB_DIR.mkdir(parents=True, exist_ok=True)
    READS_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    log(f"  wrote {READS_PATH} ({time.time() - t0:.0f} s)")
    return doc


# ---------------------------------------------------------------------------
# serving (amendment 4, section 6): the live stale records
# ---------------------------------------------------------------------------
def served_tools() -> set:
    """The tools whose read HOLDS (empty while the read has not run)."""
    try:
        d = json.loads(READS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not d.get("spent") or d.get("error"):
        return set()
    return {t for t, ok in (d.get("serve") or {}).items() if ok}


def month_label(d: str) -> str:
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{months[int(d[5:7]) - 1]} {d[:4]}"


def extend_preview(players: dict, tool_fits: dict, *, asof: str | None = None, log=print,
                   rows: list[dict] | None = None, tools: set | None = None) -> dict:
    """Add the stale-graded eFV-board players to the preview's `players` for each tool that
    HOLDS. tool_fits[tool] = {"admitted", "lines", "c", "delta", "sigma"}: the look's final
    fit and the LIVE FRESH cohort's re-centring shift, exactly as build_preview applied them.
    A player already carrying the tool (a 2026 grade) is never touched. Returns counts."""
    tools = served_tools() if tools is None else tools
    tools = {t for t in tools if t in tool_fits}
    if not tools:
        return {"tools": [], "players_added": 0, "records": 0}
    asof = asof or date.today().isoformat()
    rows = live_stale_rows(asof=asof, log=log) if rows is None else rows
    added_players, n_rec = 0, 0
    per_tool_n: dict = defaultdict(int)
    for tool in sorted(tools):
        f = tool_fits[tool]
        adm = f["admitted"]
        keep, gc, Z = E.live_tool_arrays(rows, tool, adm)
        if not keep:
            continue
        e, contrib = E.etool_centred(gc, Z, f["lines"], f["c"], f["delta"])
        sig = f.get("sigma") or 0.0
        for i, r in enumerate(keep):
            pk = r["player_key"]
            key = E.TOOLS[tool]["key"]
            p = players.get(pk)
            if p is not None and key in (p.get("tools") or {}):
                continue
            if p is None:
                p = players[pk] = {"name": r.get("name"), "mlbam": r["pid"], "side": r["side"], "tools": {}}
                added_players += 1
            ev = float(e[i])
            gd = r["grade_date"].get(tool)
            drivers = [{"key": j, "label": E.SUBDRIVER_LABELS.get(j, j), "value": E._r(Z[i, k], 3),
                        "points": E._r(float(contrib[i, k]), 2)} for k, j in enumerate(adm) if np.isfinite(Z[i, k])]
            p["tools"][key] = {"consensus": float(gc[i]), "consensus_display": E.display_grade(float(gc[i])),
                               "verdict": "PASS", "etool": E._r(ev, 2), "etool_display": E.etool_shown(E._r(ev, 2)),
                               "band80": [E._r(max(20.0, ev - E.BAND_Z * sig), 2), E._r(min(80.0, ev + E.BAND_Z * sig), 2)],
                               "construction": "recentred", "drivers": drivers, "basis": "etool",
                               "stale": True, "grade_date": gd,
                               "grade_age_months": round(r["grade_age_days"][tool] / 30.4375, 1)}
            n_rec += 1
            per_tool_n[tool] += 1
    log(f"  stale-graded: {n_rec} eTools on {added_players} added players ({dict(per_tool_n)})")
    return {"tools": sorted(tools), "players_added": added_players, "records": n_rec, "per_tool": dict(per_tool_n)}


# ---------------------------------------------------------------------------
# fixtures and the dry run
# ---------------------------------------------------------------------------
def fixture(seed: int = 11, n_players: int = 400):
    """A fresh and a stale frame for one tool with a planted sub-driver gain."""
    rng = np.random.default_rng(seed)
    fr_rows, st_rows = [], []
    years = (2014, 2015, 2016, 2017, 2018)
    for i in range(n_players):
        talent = rng.normal()
        for Y in years:
            if rng.random() < 0.5:
                continue
            stat = talent + rng.normal(scale=0.7)
            gc = round(2 * (50 + 6 * (0.6 * talent + 0.8 * rng.normal()))) / 2
            ys = {"mlb": talent + rng.normal(scale=0.8) if rng.random() < 0.5 else None,
                  "um": talent + rng.normal(scale=0.6)}
            row = {"year": Y, "pid": i, "gc": gc, "src": {"fangraphs": gc}, "cands": {"k_rw": stat},
                   "y": ys, "group": "", "level_cell": "", "band": ""}
            (st_rows if rng.random() < 0.4 else fr_rows).append(row)
    ff = E.ToolFrame("hit", fr_rows)
    sf = E.ToolFrame("hit", st_rows)
    ages = rng.integers(200, 900, size=sf.n).astype(float)
    return ff, sf, ages


def dry_run(log=print) -> dict:
    ff, sf, ages = fixture()
    rec = tool_read(ff, sf, ages, ["k_rw"], Bn=200)
    return {"verdict": rec["verdict"], "S12": rec["S12"], "zero": rec["zero_comparator"],
            "null_holds": rec["null"]["holds"], "planted_holds": rec["planted"]["holds"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--amend-sha")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.check:
        txt = json.dumps(check(), indent=1, default=str)
        if a.out:
            Path(a.out).write_text(txt, encoding="utf-8")
        print(txt)
        return 0
    if a.dry_run:
        print(json.dumps(dry_run(), indent=1, default=str))
        return 0
    if a.run:
        run(a.amend_sha)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
