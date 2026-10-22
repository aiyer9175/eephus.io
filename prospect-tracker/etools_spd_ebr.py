# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools amendment 5: level-relative MiLB eBR as a sub-driver of eSPD, the speed eTool
(owner decision EBR-Q6R, 2026-10-21, "Test via eSPD"), built to
docs/tools-2026-10/ETOOLS_AMENDMENT_5.md, which was committed alone before this module
computed any statistic.

WHAT IT ASKS. The eTools look (2026-10-15) left speed on the consensus grade: eSPD on
stolen bases per PA (sb_rel) did not clear the MLB sprint-speed label. This read asks,
once, whether the minor-league baserunning runs of the eBR build (steals, caught stealing
and pickoffs, advancement on hits and outs, outs on base; double plays left out) sharpen
the speed grade: arm A2 (eSPD on sb_rel and ebr_milb) against A1 (eSPD on sb_rel, the
current construction) and A0 (the consensus speed grade), under the eTools machinery
(etools.py, imported unchanged), with a zero comparator, a null comparator and a planted
recovery. MLB baserunning runs per 600 PA (FanGraphs BsR off the frozen fWAR vintage) are
reported beside the deciding labels and decide nothing.

COMPUTABILITY FIRST. The minor-league partition of the runner record covers Rookie and
Single-A from 2023 and the upper levels from 2026 only, so in the development frame
(board years up to 2024) one board year reads an as-of season. The runner counts the
deciding labels first; a label that is not computable stops the read before any
statistic, writes the counts and the verdict NOT COMPUTABLE, and leaves the read unspent,
so the same command runs the same registered read once the record covers the seasons.

BANS. Development board years only (2020 and 2021 never read); no R-VM outcome; no
grouping, key, filter or weight by consensus FV (docs/PROSPECT_ANCHOR_GATE.md); MiLB eBR
is never a direct eFV input (no efv_ module imports this file); never
backtest.run_backtest, run_monthly or build_site; no network request; nothing served
moves.

Run:  python etools_spd_ebr.py --check                 (presence counts; no statistic)
      python etools_spd_ebr.py --dry-run               (the reporting path on fixtures)
      python etools_spd_ebr.py --run --amend-sha SHA   (the one read)
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
import traceback
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

import etools as E  # noqa: E402

AMEND_DOC = "docs/tools-2026-10/ETOOLS_AMENDMENT_5.md"
OUT_PATH = E.LAB_DIR / "etools_spd_ebr_reads.json"
EBR_DIR = E.CACHE / "ebr" / "milb_preview"
EBR_ROWS = EBR_DIR / "ebr_milb.json"
EBR_EVAL = EBR_DIR / "ebr_milb_eval.json"
VINTAGE = E.DATA / "fwar_vintage.json"
ITEM = "ETOOLS_SPD_MILB_EBR"

TOOL = "speed_ebr"            # the amendment's frame name; the grade read is the speed tool's
BASE = "speed"
CUR = "sb_rel"                # the current eSPD sub-driver (look, 2026-10-15)
CAND = "ebr_milb"             # amendment 2.4
MIN_PA = 150                  # 2.1, the card's floor
R_MIN = 0.05                  # 2.4
BSR_MIN_PA = 300.0            # 3.2
DECIDING = ("mlb", "um")      # 3.1, 3.3
REPORTED = "bsr"              # 3.2
LABELS_ALL = DECIDING + (REPORTED,)
COMPONENTS = ("sb", "pk", "xb_adv", "xb_oob")   # 2.2; dp is not in the candidate
NULL_SEED = 20261025
PLANT_SEED = 20261026
PLANT_RHO = 0.25
Z_MDE = 1.6449 + 0.8416       # 4.3: one-sided 5% test, 80% power

TOOLS_SPD = {TOOL: {"side": "hit", "key": "eSPD", "mlb": "sprint speed",
                    "um": "SB per PA over level-season mean", "cands": [CUR, CAND]}}


@contextmanager
def registered_tools():
    """Make the amendment frame visible to etools' machinery (ToolFrame, admit and
    etool_eval read etools.TOOLS) for the duration of a read, then remove it, so nothing
    that builds the served preview ever sees it."""
    added = [t for t in TOOLS_SPD if t not in E.TOOLS]
    for t in added:
        E.TOOLS[t] = TOOLS_SPD[t]
    try:
        yield
    finally:
        for t in added:
            E.TOOLS.pop(t, None)


def amend_spent() -> str | None:
    if OUT_PATH.exists():
        try:
            d = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return f"{OUT_PATH} is unparseable"
        if d.get("spent"):
            return f"{OUT_PATH} carries a spent marker ({d.get('spent_at')})"
    return None


# ---------------------------------------------------------------------------
# the candidate (amendment section 2)
# ---------------------------------------------------------------------------
class EbrMilb:
    """Level-relative MiLB eBR lines -> the as-of candidate. rows: the build's player-season
    rows (fields as in its `fields` list); units: {"level|season": {"complete": bool}};
    reliability: {"level|season": {"spearman_brown": R}}."""

    def __init__(self, rows: list | None = None, fields: list | None = None, units: dict | None = None,
                 reliability: dict | None = None):
        if rows is None:
            d = json.loads(EBR_ROWS.read_text(encoding="utf-8"))
            rows, fields, units = d["rows"], d["fields"], d["units"]
            reliability = json.loads(EBR_EVAL.read_text(encoding="utf-8"))["reliability_split_half"]
        ix = {f: i for i, f in enumerate(fields)}
        self.units = {}
        for key, u in units.items():
            lv, s = key.split("|")
            rel = (reliability.get(key) or {}).get("spearman_brown")
            self.units[(lv, int(s))] = {"complete": bool(u.get("complete")), "R": rel}
        lines = defaultdict(list)                 # unit -> [(pid, r, pa)]
        for row in rows:
            unit = (row[ix["level"]], int(row[ix["season"]]))
            meta = self.units.get(unit)
            if meta is None or not meta["complete"]:
                continue                          # complete units only (2.1)
            pa = float(row[ix["pa"]] or 0)
            if pa < MIN_PA:
                continue
            runs = sum(float(row[ix[c]] or 0.0) for c in COMPONENTS)
            lines[unit].append((int(row[ix["mlbam"]]), runs / pa, pa))
        self.unit_stats = {}
        self.player = defaultdict(list)           # pid -> [(season, level, z, pa, k)]
        for unit, items in sorted(lines.items()):
            R = self.units[unit]["R"]
            if R is None or R <= R_MIN or len(items) < 2:
                self.unit_stats[unit] = {"dropped": "reliability at or below 0.05" if (R is None or R <= R_MIN)
                                         else "under 2 lines", "R": R, "lines": len(items)}
                continue
            v = np.array([x[1] for x in items])
            e = np.array([x[2] for x in items])
            mu = float((v * e).sum() / e.sum())
            sd = float(math.sqrt(max(((e * (v - mu) ** 2).sum() / e.sum()), 0.0)))
            nbar = float(e.mean())
            k = nbar * (1.0 - R) / R
            self.unit_stats[unit] = {"mu": mu, "sd": sd, "nbar": nbar, "R": R, "k": k, "lines": len(items)}
            if sd <= 0:
                continue
            for pid, r, pa in items:
                self.player[pid].append((unit[1], unit[0], (r - mu) / sd, pa, k))

    def complete_seasons(self) -> list[int]:
        return sorted({s for (lv, s), u in self.units.items() if u["complete"]})

    def frame_years(self, years=E.DEV_YEARS) -> tuple[int, ...]:
        """1.1: development board years whose as-of window holds a complete unit."""
        seas = self.complete_seasons()
        return tuple(int(Y) for Y in years
                     if int(Y) not in E.RESERVED_BOARD_YEARS and any(s <= int(Y) - 1 for s in seas))

    def asof(self, pid: int, Y: int) -> tuple[float | None, int | None]:
        """(candidate, last season read) as of board year Y: Marcel (5, 4, 3) and PA
        weighted z over seasons Y - 3 to Y - 1, times E / (E + k)."""
        lst = self.player.get(int(pid)) or []
        num = den = Ex = kw = 0.0
        last = None
        for s, _lv, z, pa, k in lst:
            back = int(Y) - int(s)
            if back <= 0:
                continue                          # never read: at or after the board year
            w = E.MARCEL.get(back)
            if w is None:
                continue
            if s >= Y:
                raise E.GuardError(f"{CAND}: season {s} is not before board year {Y}")
            num += w * pa * z
            den += w * pa
            kw += w * pa * k
            Ex += (w / E.MARCEL[1]) * pa
            last = s if last is None else max(last, s)
        if den <= 0:
            return None, None
        kbar = kw / den
        return (num / den) * (Ex / (Ex + kbar)), last


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------
def load_bsr(path: Path = VINTAGE) -> dict:
    """{pid: {season: (BsR, PA)}} from the frozen fWAR vintage, hitting rows."""
    d = json.loads(path.read_text(encoding="utf-8"))
    fields = d["fields"]["hitting"]
    ib, ip = fields.index("baseRunning"), fields.index("plateAppearances")
    out: dict = defaultdict(dict)
    for s, sd in (d.get("seasons") or {}).items():
        h = (sd or {}).get("hitting") or {}
        rows = h.get("rows") or {}
        for pid, vals in rows.items():
            b, pa = E._f(vals[ib]), E._f(vals[ip])
            if b is None or not pa:
                continue
            out[int(pid)][int(s)] = (b, pa)
    return dict(out)


def bsr_label(pid: int, Y: int, bsr: dict) -> float | None:
    """3.2: BsR per 600 PA over the first three MLB seasons strictly after Y (to 2026)."""
    import tool_accuracy_lab as TAL
    d = bsr.get(int(pid)) or {}
    seasons = TAL.window_seasons([s for s, v in d.items() if v[1] > 0], Y, E.LAST_MLB_SEASON)
    pa = sum(d[s][1] for s in seasons)
    if not seasons or pa < BSR_MIN_PA:
        return None
    return 600.0 * sum(d[s][0] for s in seasons) / pa


def load_labels() -> dict:
    import tool_accuracy_lab as TAL
    return {"sprint": TAL.load_sprint(range(2015, E.LAST_MLB_SEASON + 1)), "um": E.um_tables(tracked=False),
            "bsr": load_bsr()}


def sb_rel_metric():
    """The current eSPD sub-driver, exactly as the look builds it (gate 3.3)."""
    lines = E.milb_lines("hit")
    ln = {k: ((c.get("sb", 0.0) / c["pa"]) if c.get("pa") else None, c.get("pa"), None)
          for k, c in lines.items()}
    return E.ZMetric(CUR, ln, 100.0)


# ---------------------------------------------------------------------------
# the frame (amendment section 1)
# ---------------------------------------------------------------------------
def guard_years(years, allowed) -> None:
    bad = sorted({int(y) for y in years if int(y) not in allowed})
    if bad or any(int(y) in E.RESERVED_BOARD_YEARS for y in years):
        raise E.GuardError(f"board years {bad} are outside the amendment's frame {tuple(allowed)}")
    E.guard_years(years)


def build_rows(years, *, log=print) -> tuple[list[dict], dict]:
    guard_years(years, years)
    board = E.load_board(years)
    rows, counts = E.build_universe(board, years, log=log)
    rows = [r for r in rows if r["side"] == "hit"]
    for r in rows:
        if r["year"] in E.RESERVED_BOARD_YEARS:
            raise E.GuardError("reserved board year in the frame")
    return rows, counts


def attach(rows: list[dict], ebr: EbrMilb, sb, labels: dict | None, *, log=print) -> dict:
    cnt = defaultdict(int)
    for r in rows:
        Y, pid = r["year"], r["pid"]
        c, last = ebr.asof(pid, Y)
        if last is not None and last >= Y:
            raise E.GuardError(f"{CAND} read season {last} for board year {Y}")
        r["spd"] = {"cands": {CUR: sb.asof(pid, Y), CAND: c}, "y": {lb: None for lb in LABELS_ALL}}
        if labels is not None:
            debut = r.get("mlb_first") is not None and r["mlb_first"] <= E.MAX_DEBUT_YEAR
            if debut:
                r["spd"]["y"]["mlb"] = E.mlb_label(BASE, pid, Y, {"sprint": labels["sprint"]})
                r["spd"]["y"]["bsr"] = bsr_label(pid, Y, labels["bsr"])
            r["spd"]["y"]["um"] = E.um_label(BASE, pid, Y, "hit", labels["um"])
        cnt["candidate"] += c is not None
        cnt["sb_rel"] += r["spd"]["cands"][CUR] is not None
        for lb in LABELS_ALL:
            cnt[lb] += r["spd"]["y"][lb] is not None
    log("  attached: " + json.dumps(dict(cnt)))
    return dict(cnt)


def tool_frame(rows: list[dict]) -> E.ToolFrame:
    out, bsr = [], []
    for r in rows:
        src = {s: (r["per_source"].get(s) or {}).get(BASE) for s in E.SOURCES}
        vals = [v for v in src.values() if v is not None]
        if not vals:
            continue
        m = r.get("spd") or {"cands": {}, "y": {}}
        out.append({"year": r["year"], "pid": r["pid"], "gc": E.round_half(sum(vals) / len(vals)),
                    "src": src, "cands": dict(m["cands"]), "y": {lb: m["y"].get(lb) for lb in DECIDING},
                    "group": "", "mlb_first": r.get("mlb_first"), "level_cell": None, "band": None})
        bsr.append(m["y"].get(REPORTED))
    with registered_tools():
        fr = E.ToolFrame(TOOL, out)
    fr.bsr = np.array([np.nan if v is None else v for v in bsr], dtype=float)
    return fr


def label_array(fr: E.ToolFrame, lb: str) -> np.ndarray:
    return fr.bsr if lb == REPORTED else fr.y[lb]


# ---------------------------------------------------------------------------
# counts, computability, censoring, MDE (3.4, 3.5, 4.3)
# ---------------------------------------------------------------------------
def counts(fr: E.ToolFrame) -> dict:
    c = np.isfinite(fr.cands[CAND])
    by_year = {}
    for Y in sorted({int(v) for v in fr.year}):
        m = fr.year == Y
        rec = {"rows": int(m.sum()), "candidate": int((c & m).sum()),
               "candidate_debut_by_2024": int((c & m & fr.debut).sum()),
               "candidate_no_mlb_line_by_2024": int((c & m & ~fr.debut).sum())}
        for lb in LABELS_ALL:
            y = label_array(fr, lb)
            rec[f"candidate_and_{lb}"] = int((c & m & np.isfinite(y)).sum())
        rec["candidate_without_um"] = int((c & m & ~np.isfinite(fr.y["um"])).sum())
        by_year[Y] = rec
    comp = {}
    for lb in LABELS_ALL:
        y = label_array(fr, lb)
        mm = c & np.isfinite(y) & np.isfinite(fr.gc)
        _yrs, cnt = np.unique(fr.year[mm], return_counts=True)
        comp[lb] = {"rows": int(mm.sum()), "players": int(np.unique(fr.pid[mm]).size),
                    "board_years_with_20": int((cnt >= E.THIN).sum()),
                    "computable": bool(E.computable(fr.year[mm], fr.pid[mm]))}
    return {"frame_rows": fr.n, "players": int(np.unique(fr.pid).size), "by_year": by_year,
            "computability": comp}


def look_reference() -> dict:
    """The look's own eSPD read (etools_eval.json): bootstrap sd and players per label."""
    out = {}
    try:
        d = json.loads(E.EVAL_PATH.read_text(encoding="utf-8"))
        lab = d["etools"][BASE]["labels"]
        for lb in DECIDING:
            out[lb] = {"sd": lab[lb]["sd"], "players": lab[lb]["players"], "d": lab[lb]["d"],
                       "lb95": lab[lb]["lb95"]}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return out


def mde_projection(comp: dict, ref: dict) -> dict:
    """4.3 for a label with no bootstrap: the look's sd scaled by sqrt(players ratio)."""
    out = {}
    for lb in DECIDING:
        r, n = ref.get(lb), (comp.get(lb) or {}).get("players") or 0
        if not r or not n:
            out[lb] = {"mde": None, "players": n, "basis": "no players or no look reference"}
            continue
        out[lb] = {"mde": E._r(Z_MDE * r["sd"] * math.sqrt(r["players"] / n)), "players": n,
                   "basis": (f"projection: {Z_MDE:.4f} x look sd {r['sd']} x sqrt({r['players']} / {n}); "
                             "the look's sd is eSPD against consensus on the whole speed frame")}
    return out


# ---------------------------------------------------------------------------
# statistics (sections 4 to 6)
# ---------------------------------------------------------------------------
def _with_cand(fr: E.ToolFrame, values: np.ndarray) -> E.ToolFrame:
    f2 = copy.copy(fr)
    f2.cands = dict(fr.cands)
    f2.cands[CAND] = np.asarray(values, float)
    return f2


def arms(fr: E.ToolFrame) -> dict:
    with registered_tools():
        a1, s1 = E.etool_oof(fr, [CUR])
        a2, s2 = E.etool_oof(fr, [CUR, CAND])
    return {"A0": fr.gc.copy(), "A1": a1, "A2": a2, "sigma": {"A1": s1, "A2": s2}}


def compare(fr: E.ToolFrame, ar: dict, *, Bn: int) -> dict:
    """4.2 on each label over the rows carrying the candidate and the label."""
    c = np.isfinite(fr.cands[CAND])
    out = {}
    for lb in LABELS_ALL:
        y = np.where(c, label_array(fr, lb), np.nan)
        out[lb] = {name: E.paired_d(ar[a], ar[b], y, fr.year, fr.pid, Bn=Bn)
                   for name, (a, b) in (("A2_vs_A1", ("A2", "A1")), ("A2_vs_A0", ("A2", "A0")),
                                        ("A1_vs_A0", ("A1", "A0")))}
        for rec in out[lb].values():
            if rec.get("sd") is not None:
                rec["mde"] = E._r(Z_MDE * rec["sd"])
    return out


def _lb_pos(rec: dict | None) -> bool:
    return bool(rec and rec.get("computable") and rec.get("lb95") is not None and rec["lb95"] > 0)


def rule(cmp: dict) -> dict:
    """Section 5: (a) A2 vs A1 on L_MLB, (b) A2 vs A0 on L_MLB, (c) A2 vs A0 on L_UM."""
    a = cmp["mlb"]["A2_vs_A1"]
    b = cmp["mlb"]["A2_vs_A0"]
    cc = cmp["um"]["A2_vs_A0"]
    comp = all(r.get("computable") for r in (a, b, cc))
    return {"a": _lb_pos(a), "b": _lb_pos(b), "c": _lb_pos(cc), "computable": bool(comp),
            "pass": bool(comp and _lb_pos(a) and _lb_pos(b) and _lb_pos(cc))}


def incr(fr: E.ToolFrame, cand: np.ndarray, *, Bn: int, perm: int) -> dict:
    out = {}
    for lb in LABELS_ALL:
        out[lb] = E.incr_test(fr.gc, np.asarray(cand, float), label_array(fr, lb), fr.year, fr.pid, Bn=Bn,
                              perm=(perm if lb in DECIDING else 0))
    return out


def null_candidate(fr: E.ToolFrame, seed: int = NULL_SEED) -> np.ndarray:
    """6.2: the candidate permuted within board year among the rows carrying it."""
    rng = np.random.default_rng(seed)
    c = fr.cands[CAND].copy()
    for Y in np.unique(fr.year):
        idx = np.flatnonzero((fr.year == Y) & np.isfinite(c))
        if idx.size > 1:
            c[idx] = c[idx[rng.permutation(idx.size)]]
    return c


def within_year_rank_z(y, year) -> np.ndarray:
    from scipy.stats import norm, rankdata
    out = np.full(len(y), np.nan)
    for Y in np.unique(year):
        m = (year == Y) & np.isfinite(y)
        if m.sum() < 2:
            continue
        r = rankdata(y[m])
        out[m] = norm.ppf((r - 0.5) / m.sum())
    return out


def planted_candidate(fr: E.ToolFrame, seed: int = PLANT_SEED) -> np.ndarray:
    """6.3: 0.25 x (z rank L_MLB + z rank L_UM, 0 where missing) + sqrt(1 - 0.125) x noise,
    with the real candidate's missingness."""
    rng = np.random.default_rng(seed)
    have = np.isfinite(fr.cands[CAND])
    sig = np.zeros(fr.n)
    for lb in DECIDING:
        z = within_year_rank_z(fr.y[lb], fr.year)
        sig += np.where(np.isfinite(z), PLANT_RHO * z, 0.0)
    out = sig + math.sqrt(max(1.0 - len(DECIDING) * PLANT_RHO ** 2, 0.0)) * rng.standard_normal(fr.n)
    out[~have] = np.nan
    return out


def _brief(cmp: dict) -> dict:
    return {lb: {k: {f: v.get(f) for f in ("computable", "n", "players", "d", "lb95", "sd")}
                 for k, v in recs.items()} for lb, recs in cmp.items()}


def evaluate(fr: E.ToolFrame, *, Bn: int = E.B, perm: int = E.PERM, log=print) -> dict:
    t0 = time.time()
    out: dict = {"counts": counts(fr)}
    c = np.isfinite(fr.cands[CAND])
    both = c & np.isfinite(fr.cands[CUR])
    if both.sum() >= 3:
        from scipy.stats import spearmanr
        out["spearman_sb_rel_ebr_milb"] = {"rho": E._r(float(spearmanr(fr.cands[CUR][both],
                                                                      fr.cands[CAND][both]).correlation)),
                                           "n": int(both.sum())}
    ar = arms(fr)
    out["fold_sigma"] = ar["sigma"]
    cmp = compare(fr, ar, Bn=Bn)
    out["compare"] = cmp
    out["rule"] = rule(cmp)
    log(f"    arms compared ({time.time() - t0:.0f} s): {json.dumps(out['rule'])}")
    out["incremental"] = {CAND: incr(fr, fr.cands[CAND], Bn=Bn, perm=perm),
                          CUR: incr(fr, fr.cands[CUR], Bn=Bn, perm=perm)}
    # gate 4.4 admission, reported and deciding nothing (BH q within each label family)
    atlas = []
    for lb in DECIDING:
        fam = [(name, out["incremental"][name][lb]) for name in (CUR, CAND)]
        qs = E.bh_q([r.get("p") if (r or {}).get("computable") else None for _n, r in fam])
        for (name, r), q in zip(fam, qs):
            r["q"] = q
            atlas.append({"tool": TOOL, "candidate": name, "label": lb, "cell": "pooled", "cell_value": "all",
                          **r})
    with registered_tools():
        adm = E.admit({TOOL: fr}, atlas)[TOOL]
    out["admission_reported"] = {"admitted": [a["candidate"] for a in adm["admitted"]],
                                 "qualifying": adm["qualifying"]}
    # 6.1 zero comparator
    zf = _with_cand(fr, np.where(c, 0.0, np.nan))
    za = arms(zf)
    zc = compare(zf, za, Bn=0)
    out["zero_comparator"] = {"max_abs_A2_minus_A1": E._r(float(np.nanmax(np.abs(za["A2"] - za["A1"])))
                                                         if np.isfinite(za["A2"]).any() else None, 9),
                              "d_A2_vs_A1": {lb: zc[lb]["A2_vs_A1"].get("d") for lb in LABELS_ALL}}
    # 6.2 null comparator
    nc = null_candidate(fr)
    nf = _with_cand(fr, nc)
    ncmp = compare(nf, arms(nf), Bn=Bn)
    ninc = incr(nf, nc, Bn=Bn, perm=0)
    nrule = rule(ncmp)
    void = bool(nrule["pass"] or any(_lb_pos(ninc[lb]) for lb in DECIDING))
    out["null_comparator"] = {"rule": nrule, "compare": _brief(ncmp),
                              "incremental": {lb: {f: (ninc[lb] or {}).get(f) for f in ("computable", "d", "lb95")}
                                              for lb in DECIDING},
                              "void": void}
    # 6.3 planted recovery
    pc = planted_candidate(fr)
    pf = _with_cand(fr, pc)
    pcmp = compare(pf, arms(pf), Bn=Bn)
    prule = rule(pcmp)
    out["planted"] = {"rule": prule, "compare": _brief(pcmp), "recovered": prule["pass"]}
    # verdict (section 5)
    r = out["rule"]
    if not r["computable"]:
        verdict = "NOT COMPUTABLE"
    elif void:
        verdict = "VOID (the null comparator cleared)"
    elif r["pass"]:
        verdict = "PASS"
    elif not prule["pass"]:
        verdict = "NOT PASS; UNDERPOWERED"
    else:
        verdict = "NOT PASS"
    out["verdict"] = verdict
    with registered_tools():
        final = E.etool_eval(fr, [CUR, CAND], Bn=0)
    out["final_fit"] = final.get("final_fit")
    log(f"  verdict {verdict} ({time.time() - t0:.0f} s)")
    return out


# ---------------------------------------------------------------------------
# fixtures, check, the run
# ---------------------------------------------------------------------------
FIXTURE_YEARS = (2022, 2023, 2024)


def fixture_frame(seed: int = 11, n_players: int = 360, signal: float = 0.6) -> E.ToolFrame:
    rng = np.random.default_rng(seed)
    rows, bsr = [], []
    for p in range(n_players):
        true = rng.normal(0, 1)
        for Y in rng.choice(FIXTURE_YEARS, size=int(rng.integers(1, 3)), replace=False):
            gc = E.round_half(50 + 6 * (0.6 * true + 0.8 * rng.normal()))
            sb = 0.5 * true + rng.normal() if rng.random() < 0.9 else None
            cand = signal * true + rng.normal() if rng.random() < 0.7 else None
            ym = (true + rng.normal()) if rng.random() < 0.6 else None
            rows.append({"year": int(Y), "pid": 7000 + p, "gc": gc,
                         "src": {"fangraphs": gc, "mlb_pipeline": None, "baseballamerica": None},
                         "cands": {CUR: sb, CAND: cand},
                         "y": {"mlb": ym, "um": (true + rng.normal()) if rng.random() < 0.7 else None},
                         "group": "", "mlb_first": 2023 if ym is not None else None,
                         "level_cell": None, "band": None})
            bsr.append(None if ym is None else true + rng.normal())
    with registered_tools():
        fr = E.ToolFrame(TOOL, rows)
    fr.bsr = np.array([np.nan if v is None else v for v in bsr], dtype=float)
    return fr


def dry_run(log=print) -> dict:
    res = evaluate(fixture_frame(), Bn=120, perm=5, log=lambda *_a: None)
    return {"verdict": res["verdict"], "rule": res["rule"], "zero": res["zero_comparator"],
            "null_void": res["null_comparator"]["void"], "planted": res["planted"]["recovered"],
            "d_A2_vs_A1": {lb: res["compare"][lb]["A2_vs_A1"].get("d") for lb in LABELS_ALL}}


def input_shas() -> dict:
    paths = [E.db_path(), E.DATA / "debuts.json", E.DATA / "inactive.json", EBR_ROWS, EBR_EVAL, VINTAGE,
             E.EVAL_PATH]
    paths += sorted((E.CACHE / "savant_sprint").glob("sprint_20*.csv"))
    return {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p.name).replace("\\", "/"): E.sha256_of(p)
            for p in paths}


def _frame(*, labels: bool, log=print):
    ebr = EbrMilb()
    years = ebr.frame_years()
    if not years:
        raise E.GuardError("no development board year reads a complete MiLB eBR season")
    rows, uni = build_rows(years, log=log)
    lab = load_labels() if labels else None
    cov = attach(rows, ebr, sb_rel_metric(), lab, log=log)
    for r in rows:
        y = r["spd"]["y"]
        if (y["mlb"] is not None or y["bsr"] is not None) and (r.get("mlb_first") is None
                                                              or r["mlb_first"] > E.MAX_DEBUT_YEAR):
            raise E.GuardError("an MLB-label row whose first MLB season is after 2024")
    E.guard_no_fv(["year"])
    return ebr, years, uni, cov, tool_frame(rows)


def _unit_table(ebr: EbrMilb) -> dict:
    return {f"{lv}|{s}": {k: (E._r(v, 6) if isinstance(v, float) else v) for k, v in st.items()}
            for (lv, s), st in sorted(ebr.unit_stats.items())}


def check(log=print) -> dict:
    """Rows, candidate coverage and label PRESENCE counts per board year (no label value
    enters any statistic)."""
    ebr, years, uni, cov, fr = _frame(labels=True, log=log)
    comp = counts(fr)
    return {"years": years, "complete_seasons": ebr.complete_seasons(), "units": _unit_table(ebr),
            "universe": uni, "coverage": cov, "counts": comp,
            "mde_projection": mde_projection(comp["computability"], look_reference())}


def _write(doc: dict) -> None:
    E.LAB_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, indent=1, default=_json_default), encoding="utf-8", newline="\n")


def run(amend_sha: str, *, log=print) -> dict:
    why = amend_spent()
    if why:
        raise E.GuardError(f"the read is spent: {why}")
    if not E.gate_sha_ok(amend_sha, AMEND_DOC):
        raise E.GuardError(f"{amend_sha} does not name a commit carrying {AMEND_DOC} as REGISTERED")
    shas_start = input_shas()
    t0 = time.time()
    ebr, years, uni, cov, fr = _frame(labels=True, log=log)
    comp = counts(fr)
    base = {"item": ITEM, "tool": "etools_spd_ebr.py", "amend_doc": AMEND_DOC, "amend_sha": amend_sha,
            "head": (E._git("rev-parse", "HEAD") or "").strip(), "survivorship": E.SURVIVORSHIP,
            "constants": {"years": years, "B": E.B, "seed": E.SEED, "perm": E.PERM, "perm_seed": E.PERM_SEED,
                          "null_seed": NULL_SEED, "plant_seed": PLANT_SEED, "plant_rho": PLANT_RHO,
                          "min_pa": MIN_PA, "bsr_min_pa": BSR_MIN_PA, "r_min": R_MIN, "components": COMPONENTS,
                          "last_um_season": E.LAST_UM_SEASON, "max_debut_year": E.MAX_DEBUT_YEAR,
                          "pool_min": E.POOL_MIN, "thin": E.THIN, "min_years": E.MIN_YEARS},
            "complete_seasons": ebr.complete_seasons(), "units": _unit_table(ebr),
            "universe": uni, "coverage": cov, "counts": comp, "look_reference": look_reference()}
    if not all(comp["computability"][lb]["computable"] for lb in DECIDING):
        doc = {**base, "spent": False, "verdict": "NOT COMPUTABLE",
               "why": [f"{lb}: {comp['computability'][lb]['players']} players, "
                       f"{comp['computability'][lb]['board_years_with_20']} board years of 20 or more rows "
                       f"(needs {E.POOL_MIN} and {E.MIN_YEARS})"
                       for lb in DECIDING if not comp["computability"][lb]["computable"]],
               "mde_projection": mde_projection(comp["computability"], look_reference()),
               "statistics_computed": 0, "checked_at": E._now(),
               "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
               "seconds": round(time.time() - t0, 1)}
        _write(doc)
        log(f"  NOT COMPUTABLE: {doc['why']}; no statistic computed; the read is not spent")
        return doc
    log(f"  inputs built in {time.time() - t0:.0f} s; the read begins")
    started = E._now()
    try:
        res = evaluate(fr, log=log)
    except Exception as exc:                                     # noqa: BLE001
        _write({**base, "spent": True, "spent_at": E._now(), "started": started,
                "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        raise
    doc = {**base, "spent": True, "spent_at": E._now(), "started": started, "verdict": res["verdict"],
           "result": res, "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
           "seconds": round(time.time() - t0, 1)}
    _write(doc)
    log(f"  wrote {OUT_PATH} ({time.time() - t0:.0f} s)")
    return doc


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--amend-sha")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.dry_run:
        print(json.dumps(dry_run(), indent=1, default=_json_default))
        return 0
    if a.check:
        txt = json.dumps(check(), indent=1, default=_json_default)
        if a.out:
            Path(a.out).write_text(txt, encoding="utf-8")
        print(txt)
        return 0
    if a.run:
        doc = run(a.amend_sha)
        print(json.dumps({"verdict": doc.get("verdict"), "spent": doc.get("spent"), "why": doc.get("why")},
                         indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
