# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools amendment 3: MiLB fielding runs (MFR) as sub-drivers for the field and arm
tools (owner decision EW3-44, 2026-10-19), built to docs/tools-2026-10/ETOOLS_AMENDMENT_3.md,
which was committed alone before this module computed any statistic.

WHAT IT ASKS. The eTools look (ETOOLS_GATE.md, 2026-10-15) left field and arm on the
consensus grade: no candidate qualified and neither tool had an upper-minors label.
MILB_FIELDING_RUNS (gate docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md, read 2026-10-16)
built an in-house MiLB fielding measure in runs. This read asks, once, whether its range
component sharpens the consensus field grade (eFLD) against MLB OAA, and whether its
outfield arm component sharpens the consensus arm grade (eARM) against Savant arm
strength, under the eTools machinery (etools.py, imported unchanged): the gate 4.1
incremental statistic, the gate 4.4 admission rule, the gate 5.1 eTool and the gate 5.2
pass rule (both labels, one-sided 95% lower bound above 0), plus the amendment's zero
comparator, null comparator and planted recovery.

THE UPPER-MINORS ANALOG. The eTools gate defines no minors label for field or arm (gate
2.2). The analog here is the MFR component itself at Double-A and Triple-A over seasons Y
to Y + 2 capped at 2024 (translated to the Triple-A scale by the MFR level factors), as
translated K% is the hit tool's minors label. Like every L_UM it is accuracy AMONG
PROMOTED players.

BANS. Board years 2022 to 2024 only (the development years whose as-of window holds an
MFR season; 2020 and 2021 never read); no R-VM outcome; no grouping, key, filter or
weight by consensus FV (docs/PROSPECT_ANCHOR_GATE.md); never backtest.run_backtest,
run_monthly or build_site; no network request; nothing served moves.

Run:  python etools_mfr.py --check                 (rows and coverage; no statistic)
      python etools_mfr.py --dry-run               (the reporting path on fixtures)
      python etools_mfr.py --run --amend-sha SHA   (the one read)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

import etools as E  # noqa: E402

AMEND_DOC = "docs/tools-2026-10/ETOOLS_AMENDMENT_3.md"
OUT_PATH = E.LAB_DIR / "etools_mfr_reads.json"
TABLES = E.CACHE / "milb_fielding" / "tables"
ITEM = "ETOOLS_FIELD_ARM_MFR"

#: board years: the development years (gate 1.1) whose as-of window holds an MFR season
YEARS: tuple[int, ...] = (2022, 2023, 2024)
MFR_FIRST = 2021
LAST_K_SEASON = 2023          # the reliability constants read seasons up to the last as-of season
UM_SPORTS = (11, 12)          # Triple-A, Double-A
SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "ROK"}
CAND_MIN_INN = 50.0
REF_MIN_INN = 200.0
UM_MIN_INN = 200.0
ARM_RUNS_MIN_INN = 300.0
POS_NAME = {2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF"}
#: position groups (EW3-44): catchers excluded from both tools
FLD_GROUP = {6: "SS", 4: "2B/3B", 5: "2B/3B", 8: "CF", 7: "COF", 9: "COF", 3: "1B"}
ARM_GROUP = {8: "CF", 7: "COF", 9: "COF"}
OF_NAMES = ("LF", "CF", "RF")

NULL_SEED = 20261025
PLANT_SEED = 20261026
PLANT_RHO = 0.25
CELL_PLAYERS = 30
CELL_THIN = 10

TOOLS_MFR: dict[str, dict] = {
    "field_mfr": {"side": "hit", "key": "eFLD", "base": "field", "component": "range_runs",
                  "groups": FLD_GROUP,
                  "mlb": "OAA per 1,000 innings (1B to RF)",
                  "um": "MFR range runs per 1,000 AA/AAA innings (AAA scale)",
                  "cands": ["mfr_range"]},
    "throw_mfr": {"side": "hit", "key": "eARM", "base": "throw", "component": "arm_runs",
                  "groups": ARM_GROUP,
                  "mlb": "arm z (IF/OF)",
                  "um": "MFR outfield arm runs per 1,000 AA/AAA innings (AAA scale)",
                  "cands": ["mfr_arm"]},
}
LABELS = E.LABELS


@contextmanager
def registered_tools():
    """Make the two amendment tools visible to etools' machinery (ToolFrame, admit,
    etool_eval read etools.TOOLS) for the duration of a read, then remove them, so
    nothing that builds the served preview ever sees them."""
    added = [t for t in TOOLS_MFR if t not in E.TOOLS]
    for t in added:
        E.TOOLS[t] = TOOLS_MFR[t]
    try:
        yield
    finally:
        for t in added:
            E.TOOLS.pop(t, None)


def guard_years(years) -> None:
    bad = sorted({int(y) for y in years if int(y) not in YEARS})
    if bad or any(int(y) in E.RESERVED_BOARD_YEARS for y in years):
        raise E.GuardError(f"board years {bad} are outside the amendment's frame {YEARS}")
    E.guard_years(years)


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
# MFR tables (amendment section 2)
# ---------------------------------------------------------------------------
class MFR:
    """The MILB_FIELDING_RUNS build tables: season table, the registered level factors,
    and per component the split-half reliability constant k (seasons up to 2023)."""

    def __init__(self, tables: Path = TABLES, *, st=None, factors=None, k=None):
        import pandas as pd
        if st is None:
            st = pd.read_parquet(tables / "season_table.parquet")
        self.st = st[(st.season >= MFR_FIRST)].copy()
        if factors is None:
            meta = json.loads((tables / "build_meta.json").read_text(encoding="utf-8"))
            factors = {sp: float(meta["levels"]["F"][lv]) for sp, lv in SPORT_LEVEL.items()}
        self.F = dict(factors)
        self.st["f"] = self.st.sport.map(self.F).astype(float)
        self.k = k if k is not None else self._component_k(tables)

    def _component_k(self, tables: Path) -> dict:
        import pandas as pd
        import milb_fielding_runs as MF
        gr = pd.read_parquet(tables / "game_rows.parquet")
        games = pd.read_parquet(tables / "games.parquet")
        gr = gr[(gr.season >= MFR_FIRST) & (gr.season <= LAST_K_SEASON)]
        out = {}
        for tool, spec in TOOLS_MFR.items():
            g = gr[gr.pos.isin(list(spec["groups"]))].copy()
            g["runs"] = g[spec["component"]]
            kk = MF.shrink_k(g, games)
            out[tool] = {int(p): kk[str(p)] for p in spec["groups"]}
        return out

    def k_value(self, tool: str, pos: int) -> float:
        return float(self.k[tool][int(pos)]["k"])

    def _primary(self, sub, tool: str):
        spec = TOOLS_MFR[tool]
        sub = sub.assign(fr=sub[spec["component"]] * sub.f)
        pp = sub.groupby(["pid", "pos"], as_index=False).agg(inn=("inn", "sum"), fr=("fr", "sum"),
                                                             last=("season", "max"), first=("season", "min"))
        prim = pp.sort_values(["pid", "inn", "pos"], ascending=[True, False, True]).drop_duplicates("pid")
        return prim[prim.pos.isin(list(spec["groups"]))].copy()

    def asof(self, tool: str, Y: int) -> dict:
        """{pid: {...}} the candidate as of board year Y: MFR seasons 2021 to Y - 1 only;
        the primary position is the rated position with the most MiLB innings; the value
        is 1,000 x sum_L F_L x component_L / (innings + k_c) at it, then z within the
        position group over the players with 200+ such innings."""
        sub = self.st[(self.st.season < Y)]
        prim = self._primary(sub, tool)
        if len(prim) and int(prim["last"].max()) >= Y:
            raise E.GuardError(f"MFR candidate read season {int(prim['last'].max())} for board year {Y}")
        prim = prim[prim.inn >= CAND_MIN_INN].copy()
        if prim.empty:
            return {}
        groups = TOOLS_MFR[tool]["groups"]
        k = prim.pos.map(lambda p: self.k_value(tool, p)).astype(float)
        prim["v"] = 1000.0 * prim.fr / (prim.inn + k)
        prim["group"] = prim.pos.map(groups)
        ref = prim[prim.inn >= REF_MIN_INN]
        mu = ref.groupby("group").v.mean()
        sd = ref.groupby("group").v.std(ddof=1)
        out = {}
        for r in prim.itertuples(index=False):
            m, s = mu.get(r.group), sd.get(r.group)
            if m is None or s is None or not (s > 0):
                continue
            out[int(r.pid)] = {"z": float((r.v - m) / s), "v": float(r.v), "pos": POS_NAME[int(r.pos)],
                               "group": r.group, "inn": float(r.inn), "last_season": int(r.last)}
        return out

    def um_label(self, tool: str, Y: int) -> dict:
        """{pid: value} the upper-minors analog: Double-A and Triple-A seasons Y to
        min(Y + 2, 2024), the component at the player's primary AA/AAA position (in the
        tool's groups), 200+ innings, 1,000 x sum_L F_L x component_L / innings (raw)."""
        hi = min(Y + 2, E.LAST_UM_SEASON)
        sub = self.st[(self.st.season >= Y) & (self.st.season <= hi) & self.st.sport.isin(UM_SPORTS)]
        prim = self._primary(sub, tool)
        if len(prim) and (int(prim["last"].max()) > E.LAST_UM_SEASON or int(prim["first"].min()) < Y):
            raise E.GuardError("an upper-minors label season outside [Y, 2024]")
        prim = prim[prim.inn >= UM_MIN_INN]
        return {int(r.pid): float(1000.0 * r.fr / r.inn) for r in prim.itertuples(index=False)}


# ---------------------------------------------------------------------------
# MLB labels (gate 2.1 for field and throw) and the two reported labels
# ---------------------------------------------------------------------------
def load_mlb() -> dict:
    import tool_accuracy_lab as TAL
    data = {"oaa": TAL.load_oaa(range(2016, E.LAST_MLB_SEASON + 1)),
            "finn": TAL.load_fielding_innings(),
            "arm": TAL.load_arm(range(2020, E.LAST_MLB_SEASON + 1))}
    fi = json.loads((E.DATA / "fielding_innings.json").read_text(encoding="utf-8"))
    pos_inn: dict = {}
    for season, byp in (fi.get("seasons") or {}).items():
        for pid, byq in byp.items():
            for pos, v in (byq or {}).items():
                inn = E._f((v or {}).get("inn"))
                if inn and pos in ("1B", "2B", "3B", "SS", "LF", "CF", "RF"):
                    pos_inn.setdefault(int(pid), {}).setdefault(int(season), {})[pos] = inn
    data["pos_inn"] = pos_inn
    data["arm_runs"] = load_fg_arm_runs()
    return data


def load_fg_arm_runs() -> dict:
    """{pid: {season: [aFRP, OF innings]}} from the FanGraphs fielding cache (FRP arm runs)."""
    import pandas as pd
    import milb_fielding_runs as MF
    out: dict = {}
    for s in range(2016, E.LAST_MLB_SEASON + 1):
        p = MF.FG_RAW / f"fg_field_full_{s}.csv"
        if not p.exists():
            continue
        f = pd.read_csv(p)
        f = f[f.Pos.isin(list(OF_NAMES))]
        for r in f.itertuples(index=False):
            pid, a = E._f(getattr(r, "xMLBAMID", None)), E._f(getattr(r, "aFRP", None))
            if pid is None or a is None:
                continue
            slot = out.setdefault(int(pid), {}).setdefault(s, [0.0, 0.0])
            slot[0] += a
            slot[1] += MF.fg_ip(r.Inn)
    return out


def mlb_label(tool: str, pid: int, Y: int, data: dict) -> float | None:
    return E.mlb_label(TOOLS_MFR[tool]["base"], pid, Y, data)


def mlb_primary_position(pid: int, Y: int, data: dict) -> str | None:
    """The MLB position with the most innings over the OAA label's window seasons."""
    import tool_accuracy_lab as TAL
    o = TAL.outcome_oaa(pid, Y, data["oaa"], data["finn"])
    if o is None:
        return None
    tot: dict = {}
    for s in o["seasons"]:
        for pos, inn in ((data["pos_inn"].get(pid) or {}).get(s) or {}).items():
            tot[pos] = tot.get(pos, 0.0) + inn
    return max(sorted(tot), key=tot.get) if tot else None


def arm_runs_label(pid: int, Y: int, data: dict) -> float | None:
    """Reported only: FanGraphs FRP arm runs per 1,000 outfield innings over the first
    three MLB seasons after Y (to 2026) with outfield innings, 300+ innings."""
    import tool_accuracy_lab as TAL
    d = data["arm_runs"].get(pid) or {}
    seasons = TAL.window_seasons([s for s, v in d.items() if v[1] > 0], Y, E.LAST_MLB_SEASON)
    inn = sum(d[s][1] for s in seasons)
    if not seasons or inn < ARM_RUNS_MIN_INN:
        return None
    return 1000.0 * sum(d[s][0] for s in seasons) / inn


# ---------------------------------------------------------------------------
# the frame (amendment section 1)
# ---------------------------------------------------------------------------
def build_rows(*, log=print) -> tuple[list[dict], dict]:
    guard_years(YEARS)
    board = E.load_board(YEARS)
    rows, counts = E.build_universe(board, YEARS, log=log)
    rows = [r for r in rows if r["side"] == "hit"]
    for r in rows:
        if r["year"] in E.RESERVED_BOARD_YEARS:
            raise E.GuardError("reserved board year in the frame")
    return rows, counts


def attach(rows: list[dict], mfr: MFR, mlb: dict | None, *, log=print) -> dict:
    """Candidates, groups and labels per (tool, row)."""
    cnt: dict = {}
    for tool, spec in TOOLS_MFR.items():
        asof = {Y: mfr.asof(tool, Y) for Y in YEARS}
        um = {Y: mfr.um_label(tool, Y) for Y in YEARS}
        for r in rows:
            Y, pid = r["year"], r["pid"]
            a = asof[Y].get(pid)
            ym = None
            extra = {}
            if mlb is not None and r.get("mlb_first") is not None and r["mlb_first"] <= E.MAX_DEBUT_YEAR:
                ym = mlb_label(tool, pid, Y, mlb)
                if tool == "field_mfr" and ym is not None:
                    extra["mlb_pos"] = mlb_primary_position(pid, Y, mlb)
                if tool == "throw_mfr":
                    extra["arm_runs"] = arm_runs_label(pid, Y, mlb)
            r.setdefault("mfr", {})[tool] = {
                "cand": None if a is None else a["z"], "group": None if a is None else a["group"],
                "pos": None if a is None else a["pos"], "inn": None if a is None else a["inn"],
                "y": {"mlb": ym, "um": um[Y].get(pid)}, **extra}
            c = cnt.setdefault(tool, {"candidate": 0, "mlb": 0, "um": 0})
            c["candidate"] += a is not None
            c["mlb"] += ym is not None
            c["um"] += um[Y].get(pid) is not None
    log("  attached: " + json.dumps(cnt))
    return cnt


def tool_frame(rows: list[dict], tool: str) -> E.ToolFrame:
    spec = TOOLS_MFR[tool]
    out = []
    for r in rows:
        src = {s: (r["per_source"].get(s) or {}).get(spec["base"]) for s in E.SOURCES}
        vals = [v for v in src.values() if v is not None]
        if not vals:
            continue
        m = (r.get("mfr") or {}).get(tool) or {}
        out.append({"year": r["year"], "pid": r["pid"], "gc": E.round_half(sum(vals) / len(vals)),
                    "src": src, "cands": {spec["cands"][0]: m.get("cand")},
                    "y": dict(m.get("y") or {}), "group": m.get("group") or "",
                    "mlb_first": r.get("mlb_first"), "level_cell": None, "band": None,
                    "_extra": {k: m.get(k) for k in ("mlb_pos", "arm_runs")}})
    with registered_tools():
        fr = E.ToolFrame(tool, out)
    fr.extra = [o["_extra"] for o in out]
    return fr


# ---------------------------------------------------------------------------
# statistics (amendment section 4 and 5)
# ---------------------------------------------------------------------------
def forced_etool(fr: E.ToolFrame, cand_name: str, Bn: int) -> dict:
    """The gate 5.1 eTool built on one candidate and scored by gate 5.2, whether or not
    the candidate was admitted."""
    with registered_tools():
        return E.etool_eval(fr, [cand_name], Bn=Bn)


def _with_cand(fr: E.ToolFrame, name: str, values: np.ndarray) -> E.ToolFrame:
    import copy
    f2 = copy.copy(fr)
    f2.cands = dict(fr.cands)
    f2.cands[name] = np.asarray(values, float)
    return f2


def within_year_rank_z(y, year) -> np.ndarray:
    """z of the within-board-year rank (normal scores of mid-ranks), NaN where y is NaN."""
    from scipy.stats import norm, rankdata
    out = np.full(len(y), np.nan)
    for Y in np.unique(year):
        m = (year == Y) & np.isfinite(y)
        if m.sum() < 2:
            continue
        r = rankdata(y[m])
        out[m] = norm.ppf((r - 0.5) / m.sum())
    return out


def null_candidate(fr: E.ToolFrame, name: str, seed: int = NULL_SEED) -> np.ndarray:
    """The candidate permuted among the rows carrying it within (board year, position group)."""
    rng = np.random.default_rng(seed)
    c = fr.cands[name].copy()
    for Y in np.unique(fr.year):
        for g in sorted(set(fr.group.tolist())):
            idx = np.flatnonzero((fr.year == Y) & (fr.group == g) & np.isfinite(c))
            if idx.size > 1:
                c[idx] = c[idx[rng.permutation(idx.size)]]
    return c


def planted_candidate(fr: E.ToolFrame, name: str, labels: tuple, seed: int = PLANT_SEED) -> np.ndarray:
    """On the rows carrying the real candidate: rho x the sum of the within-year rank z of
    each label in `labels` (0 where that label is missing) plus noise, scaled to unit
    variance; NaN elsewhere (the real candidate's missingness)."""
    rng = np.random.default_rng(seed)
    have = np.isfinite(fr.cands[name])
    sig = np.zeros(fr.n)
    for lb in labels:
        z = within_year_rank_z(fr.y[lb], fr.year)
        sig += np.where(np.isfinite(z), PLANT_RHO * z, 0.0)
    noise_sd = math.sqrt(max(1.0 - len(labels) * PLANT_RHO ** 2, 0.0))
    out = sig + noise_sd * rng.standard_normal(fr.n)
    out[~have] = np.nan
    return out


def cell_test(fr: E.ToolFrame, cand, lb: str, mask, Bn: int) -> dict | None:
    """Descriptive cell (never admitting): the gate 4.1 statistic on the cell's rows
    carrying the candidate and the label, board years with 10+ rows, 30+ players."""
    gc, y, year, pid = fr.gc[mask], fr.y[lb][mask], fr.year[mask], fr.pid[mask]
    c = np.asarray(cand, float)[mask]
    m = np.isfinite(gc) & np.isfinite(c) & np.isfinite(y)
    rec = {"n": int(m.sum()), "players": int(np.unique(pid[m]).size)}
    if rec["players"] < CELL_PLAYERS:
        rec["computable"] = False
        return rec
    gc, c, y, year, pid = gc[m], c[m], y[m], year[m], pid[m]
    aug = E.loyo_oof([gc, c], y, year, pid)
    k = np.isfinite(aug)
    gc, c, y, year, pid, aug = gc[k], c[k], y[k], year[k], pid[k], aug[k]
    ra = E.within_rho(aug, y, year, min_rows=CELL_THIN)
    r0 = E.within_rho(gc, y, year, min_rows=CELL_THIN)
    if ra is None or r0 is None:
        rec["computable"] = False
        return rec
    draws = []
    for b in range(0, Bn, E.B_CHUNK):
        W = E.cluster_weights(pid, min(E.B_CHUNK, Bn - b), E.SEED + b // E.B_CHUNK)
        draws.append(E.within_rho(aug, y, year, W, min_rows=CELL_THIN)
                     - E.within_rho(gc, y, year, W, min_rows=CELL_THIN))
    rec.update({"computable": True, "rho_consensus": E._r(r0), "rho_augmented": E._r(ra)})
    rec.update(E.summarize_draws(ra - r0, np.concatenate(draws)))
    return rec


def read_tool(fr: E.ToolFrame, *, Bn: int = E.B, perm: int = E.PERM, log=print) -> dict:
    """Everything the amendment reads for one tool, except the BH q (taken over the family)."""
    tool = fr.tool
    name = TOOLS_MFR[tool]["cands"][0]
    out: dict = {"tool": tool, "key": TOOLS_MFR[tool]["key"], "candidate": name, "tests": {},
                 "frame": {"rows": fr.n, "players": int(np.unique(fr.pid).size),
                           "by_year": {int(Y): int((fr.year == Y).sum()) for Y in np.unique(fr.year)},
                           "candidate_rows": int(np.isfinite(fr.cands[name]).sum()),
                           "labels": {lb: int(np.isfinite(fr.y[lb]).sum()) for lb in LABELS},
                           "candidate_and_label": {lb: int((np.isfinite(fr.cands[name]) & np.isfinite(fr.y[lb])).sum())
                                                   for lb in LABELS},
                           "promotion_counts": E.promotion_counts(fr)}}
    for lb in LABELS:
        t0 = time.time()
        res = E.incr_test(fr.gc, fr.cands[name], fr.y[lb], fr.year, fr.pid, Bn=Bn, perm=perm)
        out["tests"][lb] = res
        log(f"    {tool} {lb} {name}: n {res.get('n')} d {res.get('d')} lb {res.get('lb95')} "
            f"floor {res.get('perm_floor95')} ({time.time() - t0:.1f} s)")
    # comparators (section 5)
    zero = forced_etool(_with_cand(fr, name, np.where(np.isfinite(fr.cands[name]), 0.0, np.nan)), name, Bn=Bn)
    out["zero_comparator"] = {lb: {k: (zero["labels"].get(lb) or {}).get(k) for k in ("d", "lb95", "n")}
                              for lb in LABELS}
    nc = null_candidate(fr, name)
    fn = _with_cand(fr, name, nc)
    out["null_comparator"] = {"tests": {lb: E.incr_test(fn.gc, nc, fn.y[lb], fn.year, fn.pid, Bn=Bn, perm=0)
                                        for lb in LABELS},
                              "etool": _etool_summary(forced_etool(fn, name, Bn=Bn))}
    planted = {}
    for lb in LABELS:
        pc = planted_candidate(fr, name, (lb,))
        planted[lb] = E.incr_test(fr.gc, pc, fr.y[lb], fr.year, fr.pid, Bn=Bn, perm=perm)
        planted[lb]["recovered"] = _incr_clears(planted[lb])
    pc2 = planted_candidate(fr, name, LABELS)
    pe = _etool_summary(forced_etool(_with_cand(fr, name, pc2), name, Bn=Bn))
    out["planted"] = {"tests": planted, "etool": pe,
                      "etool_recovered": all(_lb_pos((pe.get("labels") or {}).get(lb)) for lb in LABELS)}
    out["forced_etool"] = _etool_summary(forced_etool(fr, name, Bn=Bn))
    # descriptive position-group cells
    cells = []
    for g in sorted(set(fr.group.tolist()) - {""}):
        for lb in LABELS:
            rec = cell_test(fr, fr.cands[name], lb, fr.group == g, Bn)
            if rec is not None:
                cells.append({"group": g, "label": lb, **rec})
    out["cells"] = cells
    return out


def _incr_clears(r: dict | None) -> bool:
    return bool(r and r.get("computable") and (r.get("lb95") or -1) > 0
                and r.get("perm_floor95") is not None and r["d"] > r["perm_floor95"])


def _lb_pos(rec: dict | None) -> bool:
    return bool(rec and rec.get("computable") and rec.get("lb95") is not None and rec["lb95"] > 0)


def _etool_summary(ev: dict) -> dict:
    return {"verdict": ev.get("verdict"), "labels": ev.get("labels"), "final_fit": ev.get("final_fit")}


def sensitivity(fr: E.ToolFrame, ev_pred: np.ndarray | None, Bn: int) -> dict:
    """Reported, deciding nothing: field, the OAA label centred within the MLB primary
    position; throw, FanGraphs FRP arm runs per 1,000 outfield innings."""
    name = TOOLS_MFR[fr.tool]["cands"][0]
    if fr.tool == "field_mfr":
        y = fr.y["mlb"].copy()
        pos = np.array([(e or {}).get("mlb_pos") or "" for e in fr.extra])
        for p in sorted(set(pos.tolist()) - {""}):
            m = (pos == p) & np.isfinite(y)
            if m.any():
                y[m] = y[m] - y[m].mean()
        y[pos == ""] = np.nan
        label = "OAA per 1,000 innings centred within the MLB primary position"
    else:
        y = np.array([np.nan if (e or {}).get("arm_runs") is None else e["arm_runs"] for e in fr.extra])
        label = "FanGraphs FRP arm runs per 1,000 outfield innings"
    out = {"label": label, "n": int(np.isfinite(y).sum()),
           "incremental": E.incr_test(fr.gc, fr.cands[name], y, fr.year, fr.pid, Bn=Bn, perm=0)}
    if ev_pred is not None:
        m = np.isfinite(y) & np.isfinite(ev_pred)
        if E.computable(fr.year[m], fr.pid[m]):
            out["etool"] = E.paired_d(ev_pred[m], fr.gc[m], y[m], fr.year[m], fr.pid[m], Bn=Bn)
    return out


def evaluate(frames: dict, *, Bn: int = E.B, perm: int = E.PERM, log=print) -> dict:
    per = {t: read_tool(fr, Bn=Bn, perm=perm, log=log) for t, fr in frames.items()}
    fam = [(t, lb) for t in frames for lb in LABELS]
    qs = E.bh_q([(per[t]["tests"][lb] or {}).get("p") if (per[t]["tests"][lb] or {}).get("computable") else None
                 for t, lb in fam])
    for (t, lb), q in zip(fam, qs):
        per[t]["tests"][lb]["q"] = q
    atlas = [{"tool": t, "candidate": per[t]["candidate"], "label": lb, "cell": "pooled", "cell_value": "all",
              **per[t]["tests"][lb]} for t, lb in fam]
    with registered_tools():
        adm = E.admit(frames, atlas)
        for t, fr in frames.items():
            names = [a["candidate"] for a in adm[t]["admitted"]]
            ev = E.etool_eval(fr, names, Bn=Bn)
            ev["qualifying"] = adm[t]["qualifying"]
            null_ok = not (any(((per[t]["null_comparator"]["tests"][lb] or {}).get("lb95") or -1) > 0
                               for lb in LABELS)
                           or all(_lb_pos((per[t]["null_comparator"]["etool"].get("labels") or {}).get(lb))
                                  for lb in LABELS))
            under = [lb for lb in LABELS if not per[t]["planted"]["tests"][lb].get("recovered")]
            if not per[t]["planted"]["etool_recovered"]:
                under.append("etool")
            verdict = ev["verdict"]
            if not null_ok:
                verdict = "VOID (the null comparator cleared)"
            elif verdict != "PASS" and under:
                verdict = f"{verdict}; UNDERPOWERED ({', '.join(under)})"
            per[t]["admitted"] = names
            per[t]["etool"] = ev
            per[t]["verdict"] = verdict
            per[t]["basis"] = "etool" if verdict == "PASS" else "consensus"
            pred = None
            if names or per[t]["forced_etool"].get("final_fit"):
                pred, _sig = E.etool_oof(fr, names or [per[t]["candidate"]])
            per[t]["sensitivity"] = sensitivity(fr, pred, Bn)
            log(f"  {t}: admitted {names} -> {verdict}")
    return per


# ---------------------------------------------------------------------------
# fixtures, check, the run
# ---------------------------------------------------------------------------
def fixture_frames(seed: int = 11, n_players: int = 330, signal: float = 0.6) -> dict:
    rng = np.random.default_rng(seed)
    frames = {}
    for tool, spec in TOOLS_MFR.items():
        rows = []
        groups = sorted(set(spec["groups"].values()))
        for p in range(n_players):
            true = rng.normal(0, 1)
            g = groups[p % len(groups)]
            for Y in rng.choice(YEARS, size=int(rng.integers(1, 3)), replace=False):
                gc = E.round_half(50 + 6 * (0.6 * true + 0.8 * rng.normal()))
                cand = signal * true + rng.normal() if rng.random() < 0.7 else None
                rows.append({"year": int(Y), "pid": 5000 + p, "gc": gc,
                             "src": {"fangraphs": gc, "mlb_pipeline": None, "baseballamerica": None},
                             "cands": {spec["cands"][0]: cand},
                             "y": {"mlb": (true + rng.normal()) if rng.random() < 0.6 else None,
                                   "um": (true + rng.normal()) if rng.random() < 0.7 else None},
                             "group": g if cand is not None else "", "mlb_first": 2023,
                             "level_cell": None, "band": None})
        with registered_tools():
            fr = E.ToolFrame(tool, rows)
        fr.extra = [{"mlb_pos": "SS" if r["y"]["mlb"] is not None else None,
                     "arm_runs": r["y"]["mlb"]} for r in rows]
        frames[tool] = fr
    return frames


def dry_run(log=print) -> dict:
    res = evaluate(fixture_frames(), Bn=120, perm=5, log=lambda *_a: None)
    return {t: {"verdict": v["verdict"], "admitted": v["admitted"],
                "d": {lb: v["tests"][lb].get("d") for lb in LABELS}} for t, v in res.items()}


def input_shas() -> dict:
    import milb_fielding_runs as MF
    paths = [E.db_path(), E.DATA / "debuts.json", E.DATA / "inactive.json", E.DATA / "fielding_innings.json",
             TABLES / "season_table.parquet", TABLES / "game_rows.parquet", TABLES / "build_meta.json"]
    paths += sorted((E.CACHE / "savant_oaa").glob("oaa_20*_pos*.csv"))
    paths += sorted((E.CACHE / "savant_arm").glob("arm_20*.csv"))
    paths += sorted(MF.FG_RAW.glob("fg_field_full_20*.csv"))
    return {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p.name).replace("\\", "/"): E.sha256_of(p)
            for p in paths}


def check(log=print) -> dict:
    """Rows, candidate coverage and label PRESENCE counts per board year (no value of a
    label is read into any statistic)."""
    rows, counts = build_rows(log=log)
    mfr = MFR()
    mlb = load_mlb()
    attach(rows, mfr, mlb, log=log)
    out = {"universe": counts, "k": mfr.k, "factors": mfr.F, "tools": {}}
    for tool in TOOLS_MFR:
        fr = tool_frame(rows, tool)
        name = TOOLS_MFR[tool]["cands"][0]
        c = np.isfinite(fr.cands[name])
        out["tools"][tool] = {
            "rows_with_consensus": fr.n,
            "by_year": {int(Y): {"rows": int((fr.year == Y).sum()),
                                 "candidate": int((c & (fr.year == Y)).sum()),
                                 **{f"candidate_and_{lb}": int((c & np.isfinite(fr.y[lb]) & (fr.year == Y)).sum())
                                    for lb in LABELS},
                                 **{lb: int((np.isfinite(fr.y[lb]) & (fr.year == Y)).sum()) for lb in LABELS}}
                        for Y in YEARS},
            "players_candidate_and": {lb: int(np.unique(fr.pid[c & np.isfinite(fr.y[lb])]).size) for lb in LABELS},
            "groups": {g: int(((fr.group == g) & c).sum()) for g in sorted(set(fr.group.tolist()) - {""})}}
    return out


def run(amend_sha: str, *, log=print) -> dict:
    why = amend_spent()
    if why:
        raise E.GuardError(f"the read is spent: {why}")
    if not E.gate_sha_ok(amend_sha, AMEND_DOC):
        raise E.GuardError(f"{amend_sha} does not name a commit carrying {AMEND_DOC} as REGISTERED")
    shas_start = input_shas()
    t0 = time.time()
    rows, counts = build_rows(log=log)
    mfr = MFR()
    mlb = load_mlb()
    cov = attach(rows, mfr, mlb, log=log)
    for r in rows:
        for tool, m in (r.get("mfr") or {}).items():
            if m["y"]["mlb"] is not None and (r.get("mlb_first") is None or r["mlb_first"] > E.MAX_DEBUT_YEAR):
                raise E.GuardError("an L_MLB row whose first MLB season is after 2024")
    frames = {t: tool_frame(rows, t) for t in TOOLS_MFR}
    E.guard_no_fv(["year", "group"])
    log(f"  inputs built in {time.time() - t0:.0f} s; the read begins")
    E.LAB_DIR.mkdir(parents=True, exist_ok=True)
    started = E._now()
    try:
        per = evaluate(frames, log=log)
    except Exception as exc:                                     # noqa: BLE001
        doc = {"item": ITEM, "spent": True, "spent_at": E._now(), "amend_sha": amend_sha,
               "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "started": started}
        OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
        raise
    doc = {"item": ITEM, "tool": "etools_mfr.py", "spent": True, "spent_at": E._now(), "started": started,
           "amend_doc": AMEND_DOC, "amend_sha": amend_sha, "head": (E._git("rev-parse", "HEAD") or "").strip(),
           "survivorship": E.SURVIVORSHIP,
           "constants": {"years": YEARS, "B": E.B, "seed": E.SEED, "perm": E.PERM, "perm_seed": E.PERM_SEED,
                         "null_seed": NULL_SEED, "plant_seed": PLANT_SEED, "plant_rho": PLANT_RHO,
                         "cand_min_inn": CAND_MIN_INN, "ref_min_inn": REF_MIN_INN, "um_min_inn": UM_MIN_INN,
                         "last_k_season": LAST_K_SEASON, "last_um_season": E.LAST_UM_SEASON,
                         "max_debut_year": E.MAX_DEBUT_YEAR, "q_admit": E.Q_ADMIT},
           "k": mfr.k, "factors": {SPORT_LEVEL[s]: v for s, v in mfr.F.items()},
           "universe": counts, "coverage": cov, "tools": per,
           "inputs_sha256_start": shas_start, "inputs_sha256_end": input_shas(),
           "seconds": round(time.time() - t0, 1)}
    OUT_PATH.write_text(json.dumps(doc, indent=1, default=_json_default), encoding="utf-8", newline="\n")
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
        run(a.amend_sha)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
