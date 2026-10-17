# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The as-of eTool history (ETOOLS_DVM, owner decision EW3-34), built to
docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md, which was committed alone before this
module computed anything.

WHAT IT IS. The eTool (etools.py) is the consensus tool grade plus the weighted residuals of
its admitted MiLB sub-drivers. Until now it existed only as one dated reading (the card's,
data/etools.json). Per-tool DvM+ needs a grade at every list date, so this module gives the
eTool AS OF any date t, reading only the MiLB seasons that had ended by t (gate 1.2):

    season S is readable at t when S-10-01 <= t           (efv_x1_translate's season end)
    z_j(t)       = the look's as-of value at board year S(t) + 1 (X1 features, ZMetric.asof)
    eTool(t; G)  = clamp(G + sum_j c_j (z_j - a_j - b_j G - delta_j(S)), 20, 80)

with the look's final fit (lines a_j + b_j G, weights c_j) and the flip-prep re-centring
delta_j(S) = the block cohort's mean residual minus the fit's training mean (gate 1.4). A
player who carries no sub-driver at S keeps eTool = G. Because the formula is linear in G
inside the clamp, each (player, tool, block S) is stored as two numbers,
K = sum_j c_j (z_j - a_j - delta_j) and Bslope = sum_j c_j b_j, and
eTool(t; G) = clamp(G (1 - Bslope) + K, 20, 80) for ANY base grade G: one outlet's grade
(the DvM+ pairs keep VAL_4's same-source rule), the consensus at a list date (the chart),
or the three-outlet consensus (the cohort).

WHAT IT SERVES. `python etool_history.py --build` writes data/etool_asof.json (a server
input, kept off the webroot by deploy/data_exclude.txt). ETOOLS_DVM_GROUPS names the DvM+
tool groups whose served per-tool DvM+ reads the eTool series: only the groups that passed
the gate's switch read (Part 6). Empty, the served payload is the consensus payload byte for
byte and storage never opens the artifact.

BANS. No outcome is read here. No grouping, key, filter or weight by consensus FV or any
source's FV (docs/PROSPECT_ANCHOR_GATE.md). Every season read is asserted at or before the
block's season, and a block's cohort reads only snapshots dated on or before its start.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

#: The DvM+ tool groups whose served per-tool DvM+ reads the eTool series (gate 6.2).
#: Set from the switch read's verdicts only; empty reproduces the consensus payload.
ETOOLS_DVM_GROUPS: tuple[str, ...] = ()

GATE_DOC = "docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md"
ITEM = "ETOOLS_DVM"
DATA = ROOT / "data"
ASOF_PATH = DATA / "etool_asof.json"
LAB_DIR = DATA / "_labs" / "etools"
EVAL_PATH = LAB_DIR / "etools_eval.json"
FLIP_PATH = LAB_DIR / "etools_flip_prep_reads.json"

#: DvM+ tool group (storage.TOOL_GROUPS key) -> the eTool it reads (gate 1.1).
GROUP_TOOL = {"hit": "hit", "pwr": "game_pwr", "pitch_sel": "pitch_sel", "bat_ctrl": "bat_ctrl",
              "fb": "fb", "cmd": "cmd"}
GROUPS = tuple(GROUP_TOOL)
TOOL_GROUP = {t: g for g, t in GROUP_TOOL.items()}
TOOL_SIDE = {"hit": "hit", "game_pwr": "hit", "pitch_sel": "hit", "bat_ctrl": "hit", "fb": "pit", "cmd": "pit"}
SEASON_END_MMDD = "-10-01"                                   # gate 1.2
COHORT_DAYS = 400                                            # gate 1.4
COHORT_SOURCES = ("fangraphs", "mlb_pipeline", "baseballamerica")
LAST_SEASON = 2026
FIRST_BLOCK = 2005


class LookAheadError(AssertionError):
    """An input dated after the as-of date was about to be read."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def readable_season(t: str) -> int:
    """S(t): the last MiLB season that had ended (1 October) on or before date t."""
    y, m = int(str(t)[:4]), int(str(t)[5:7])
    return y if m >= 10 else y - 1


def season_end(S: int) -> str:
    return f"{int(S)}{SEASON_END_MMDD}"


def clamp(v: float) -> float:
    return min(80.0, max(20.0, float(v)))


def etool_value(G: float | None, params) -> float | None:
    """eTool(t; G) from a block's (K, Bslope); no params (no sub-driver carried) is G."""
    if G is None:
        return None
    if not params:
        return float(G)
    K, Bs = params
    return clamp(float(G) * (1.0 - Bs) + K)


# ---------------------------------------------------------------------------
# the fits (gate 1.1) and the sub-driver values (gate 1.2)
# ---------------------------------------------------------------------------
@dataclass
class Fit:
    tool: str
    admitted: list
    lines: list            # [(a, b, ok)]
    c: list
    train_mu: list         # mean u_j over the fit's training rows carrying j (gate 1.4)
    label: str = "final"

    def sha(self) -> str:
        s = json.dumps([self.tool, self.admitted, self.lines, self.c, self.train_mu])
        return hashlib.sha256(s.encode()).hexdigest()[:16]


def load_fits(eval_path: Path = EVAL_PATH, flip_path: Path = FLIP_PATH) -> dict[str, Fit]:
    """The look's final fits for the six PASS eTools, with the flip-prep training means."""
    look = json.loads(Path(eval_path).read_text(encoding="utf-8"))
    flip = json.loads(Path(flip_path).read_text(encoding="utf-8"))
    f1 = flip.get("F1_drift_recentring") or {}
    out = {}
    for tool in GROUP_TOOL.values():
        v = look["etools"][tool]
        if v.get("verdict") != "PASS":
            raise ValueError(f"{tool} is not a PASS eTool at the look")
        ff = v["final_fit"]
        adm = list(v["admitted"])
        mu = [float(f1[tool]["train_mean_residual"][j]) for j in adm]
        out[tool] = Fit(tool, adm, [(float(a), float(b), bool(ok)) for a, b, ok in ff["lines"]],
                        [float(x) for x in ff["c"]], mu)
    return out


def all_subdrivers(fits: dict[str, Fit]) -> dict[str, list]:
    by_side: dict[str, set] = defaultdict(set)
    for tool, f in fits.items():
        by_side[TOOL_SIDE[tool]].update(f.admitted)
    return {s: sorted(v) for s, v in by_side.items()}


class SubDrivers:
    """z_j(pid, S): the look's as-of value of every admitted sub-driver at board year S + 1
    (seasons up to S only), cached per (pid, side, S)."""

    def __init__(self, names_by_side: dict[str, list], *, last_season: int = LAST_SEASON, log=print):
        import etools as E
        import efv_x1_translate as X1
        self.E, self.X1 = E, X1
        self.names = {s: list(v) for s, v in names_by_side.items()}
        self.x1_names = {"hit": set(E.X1_HIT), "pit": set(E.X1_PIT)}
        self.zm = {s: E.build_zmetrics(s, last_season=last_season, log=log) for s in ("hit", "pit")}
        self.last_season = int(last_season)
        self._cache: dict = {}

    def values(self, pid: int, side: str, S: int) -> dict:
        key = (int(pid), side, int(S))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if S > self.last_season:
            raise LookAheadError(f"season {S} is past the bank's last season {self.last_season}")
        names = self.names.get(side) or []
        out = {}
        Y = int(S) + 1
        if any(n in self.x1_names[side] for n in names):
            f = self.X1.features(int(pid), Y, None, side)
            if f.get("_T") is not None and f["_T"] > S:
                raise LookAheadError(f"X1 read season {f['_T']} for block {S}")
            if any(s > S for s in f.get("_seasons") or []):
                raise LookAheadError(f"X1 read a season after {S}")
            for n in names:
                if n in self.x1_names[side]:
                    out[n] = f.get(n)
        for n in names:
            if n in self.x1_names[side]:
                continue
            out[n] = self.zm[side][n].asof(int(pid), Y)   # ZMetric.asof raises on a season >= Y
        self._cache[key] = out
        return out


def residuals(fit: Fit, G: float, z: dict) -> list:
    """u_j for the sub-drivers carried (None where missing or the line was not fit)."""
    out = []
    for j, name in enumerate(fit.admitted):
        a, b, ok = fit.lines[j]
        v = z.get(name)
        out.append(None if (v is None or not ok or not np.isfinite(v)) else float(v) - (a + b * float(G)))
    return out


def block_params(fit: Fit, z: dict, delta: list) -> tuple[float, float] | None:
    """(K, Bslope) of gate 1.6 for one player and block, or None when no sub-driver is carried."""
    K = Bs = 0.0
    any_ = False
    for j, name in enumerate(fit.admitted):
        a, b, ok = fit.lines[j]
        v = z.get(name)
        if v is None or not ok or not np.isfinite(v):
            continue
        any_ = True
        K += fit.c[j] * (float(v) - a - float(delta[j]))
        Bs += fit.c[j] * b
    return (K, Bs) if any_ else None


# ---------------------------------------------------------------------------
# identity, the three-outlet board and the block cohorts (gate 1.4)
# ---------------------------------------------------------------------------
def db_path() -> Path:
    import etools as E
    return E.db_path()


def board_snapshots(con) -> dict[str, dict[str, list]]:
    """{player_key: {source: [(date, tools, position)]}} for the three cohort outlets,
    oldest first, parsed as etools.load_board parses a board (20 to 80 grades, the MLB
    Pipeline report-text grades where the key is missing, FanGraphs arm as throw)."""
    import efv_w2_scout as SC
    import etools as E
    out: dict = defaultdict(lambda: defaultdict(list))
    q = ("SELECT source, snapshot_date, player_key, position, tools_json FROM snapshots "
         "WHERE source IN (?, ?, ?) AND tools_json IS NOT NULL AND tools_json != '' "
         "ORDER BY snapshot_date ASC")
    for src, sd, pk, pos, tj in con.execute(q, COHORT_SOURCES):
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
        out[pk][src].append((sd, tools, pos))
    return {k: dict(v) for k, v in out.items()}


def identities(board: dict, *, log=print) -> tuple[dict[str, tuple[int, str]], dict]:
    """{player_key: (mlbam, side)} by the live preview's rule (etools.build_universe with
    live True): the outcome-blind name resolution at the latest vintage, a record whose own
    mlbam disagrees dropped."""
    import efv_identity
    import efv_vintage_frame as F
    import etools as E
    recs = F.load_universe()
    idx = efv_identity.build_index(E.LAST_MLB_SEASON)
    out, counts = {}, defaultdict(int)
    for pk, rec in recs.items():
        pos = None
        for src in COHORT_SOURCES:
            rows = (board.get(pk) or {}).get(src) or []
            for _d, _t, p in reversed(rows):
                if p:
                    pos = p
                    break
            if pos:
                break
        pos = pos or rec.get("position")
        side = "pit" if E.is_pitcher(pos) else "hit"
        res = efv_identity.resolve_record(rec, E.LAST_MLB_SEASON + 1, idx, side)
        if res.person_id is None:
            counts[f"identity_{res.how}"] += 1
            continue
        mid = rec.get("mlbam_id")
        if mid is not None and E._f(mid) is not None and int(E._f(mid)) != int(res.person_id):
            counts["identity_disagrees_with_record"] += 1
            continue
        out[pk] = (int(res.person_id), side)
    counts["resolved"] = len(out)
    log(f"  identities: {dict(counts)}")
    return out, dict(counts)


_COHORT_MEMO: dict = {}


def cohort(board: dict, ids: dict, S: int, tool: str, mlb_first: dict) -> list[tuple[int, str, float]]:
    """The block-S cohort for one tool (gate 1.4): (mlbam, side, G_c) for every player with a
    three-outlet snapshot carrying the tool dated in (d_S - 400 days, d_S], no MLB season at
    or before S; G_c the half-grade mean of each outlet's latest such snapshot. A cohort
    depends on no fit, so it is memoized per (board, identities, tool, S)."""
    key = (id(board), id(ids), tool, int(S))
    if key in _COHORT_MEMO:
        return _COHORT_MEMO[key]
    rows = _cohort(board, ids, S, tool, mlb_first)
    _COHORT_MEMO[key] = rows
    return rows


def _cohort(board: dict, ids: dict, S: int, tool: str, mlb_first: dict) -> list[tuple[int, str, float]]:
    import etools as E
    d_hi = season_end(S)
    d_lo = (date.fromisoformat(d_hi) - timedelta(days=COHORT_DAYS)).isoformat()
    side = TOOL_SIDE[tool]
    out = []
    for pk, per in board.items():
        idn = ids.get(pk)
        if idn is None or idn[1] != side:
            continue
        pid = idn[0]
        fm = mlb_first.get(pid)
        if fm is not None and fm <= S:
            continue
        vals = []
        for src in COHORT_SOURCES:
            best = None
            for d, tools, _p in per.get(src) or []:
                if d > d_hi:
                    break                         # oldest first: nothing after d_S is read
                if d > d_lo and tools.get(tool) is not None:
                    best = tools[tool]
            if best is not None:
                vals.append(best)
        if vals:
            out.append((pid, side, E.round_half(sum(vals) / len(vals))))
    return out


def block_delta(fit: Fit, rows: list, bank: SubDrivers, S: int) -> tuple[list, list]:
    """delta_j(S) = (cohort mean u_j over rows carrying j) - (training mean); the counts."""
    J = len(fit.admitted)
    tot, cnt = [0.0] * J, [0] * J
    for pid, side, G in rows:
        z = bank.values(pid, side, S)
        for j, u in enumerate(residuals(fit, G, z)):
            if u is not None:
                tot[j] += u
                cnt[j] += 1
    delta = [(tot[j] / cnt[j]) - fit.train_mu[j] if cnt[j] else 0.0 for j in range(J)]
    return delta, cnt


# ---------------------------------------------------------------------------
# the artifact (gate 1.6) and the served reader
# ---------------------------------------------------------------------------
def observation_players(con) -> dict[str, set]:
    """{player_key: {blocks S}} at which any growth-outlet snapshot sits."""
    import dev_attribution as DA
    q = ("SELECT player_key, snapshot_date FROM snapshots WHERE status = 'active' AND fv IS NOT NULL "
         "AND source IN (%s)" % ",".join("?" * len(DA.GROWTH_SOURCES)))
    out: dict = defaultdict(set)
    for pk, d in con.execute(q, DA.GROWTH_SOURCES):
        if pk and d:
            out[pk].add(readable_season(str(d)[:10]))
    return out


def build_asof(fits: dict[str, Fit], *, bank: SubDrivers | None = None, board: dict | None = None,
               ids: dict | None = None, blocks_needed: dict | None = None, log=print) -> dict:
    """The per-(player, tool, block) parameters for `fits` (the served final fits, or one
    fold's refits in the switch read), every block's delta and cohort size."""
    import etools as E
    t0 = time.time()
    con = sqlite3.connect(f"file:{db_path().as_posix()}?mode=ro", uri=True)
    try:
        board = board if board is not None else board_snapshots(con)
        if ids is None:
            ids, _ = identities(board, log=log)
        blocks_needed = blocks_needed if blocks_needed is not None else observation_players(con)
    finally:
        con.close()
    if bank is None:
        bank = SubDrivers(all_subdrivers(fits), log=log)
    mlb_first = E.mlb_first_seasons()
    blocks = sorted({S for v in blocks_needed.values() for S in v if FIRST_BLOCK <= S <= LAST_SEASON})
    deltas: dict = {}
    for tool, fit in fits.items():
        deltas[tool] = {}
        for S in blocks:
            rows = cohort(board, ids, S, tool, mlb_first)
            d, cnt = block_delta(fit, rows, bank, S)
            deltas[tool][S] = {"delta": d, "n_cohort": len(rows), "n_carrying": cnt}
    players: dict = {}
    for pk, Ss in blocks_needed.items():
        idn = ids.get(pk)
        if idn is None:
            continue
        pid, side = idn
        rec = {}
        for tool, fit in fits.items():
            if TOOL_SIDE[tool] != side:
                continue
            per = {}
            for S in sorted(Ss):
                if not (FIRST_BLOCK <= S <= LAST_SEASON):
                    continue
                p = block_params(fit, bank.values(pid, side, S), deltas[tool][S]["delta"])
                if p is not None:
                    per[S] = p
            if per:
                rec[tool] = per
        if rec:
            players[pk] = {"pid": pid, "side": side, "t": rec}
    log(f"  as-of eTool parameters: {len(players)} players, {len(blocks)} blocks ({time.time() - t0:.0f} s)")
    return {"players": players, "deltas": deltas, "blocks": blocks, "ids": ids}


def write_artifact(res: dict, fits: dict[str, Fit], *, path: Path = ASOF_PATH, log=print) -> Path:
    import etools as E
    doc = {"generated_at": _now(), "item": ITEM, "gate_doc": GATE_DOC,
           "rule": "eTool(t; G) = clamp(G (1 - B) + K, 20, 80), (K, B) of the block S(t); none: G",
           "season_end": SEASON_END_MMDD, "groups": dict(GROUP_TOOL),
           "fits": {t: {"admitted": f.admitted, "sha": f.sha()} for t, f in fits.items()},
           "inputs_sha256": {"etools_eval": E.sha256_of(EVAL_PATH), "flip_prep": E.sha256_of(FLIP_PATH)},
           "blocks": {t: {str(S): {"delta": [round(x, 6) for x in v["delta"]], "n_cohort": v["n_cohort"]}
                          for S, v in d.items()} for t, d in res["deltas"].items()},
           "players": {pk: {"pid": p["pid"], "side": p["side"],
                            "t": {t: {str(S): [round(k, 4), round(b, 6)] for S, (k, b) in per.items()}
                                  for t, per in p["t"].items()}}
                       for pk, p in sorted(res["players"].items())}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8", newline="\n")
    log(f"  wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


class AsOf:
    """The served reader of data/etool_asof.json."""

    def __init__(self, doc: dict):
        self.doc = doc or {}
        self.players = self.doc.get("players") or {}

    @classmethod
    def load(cls, path: Path = ASOF_PATH) -> "AsOf":
        try:
            return cls(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls({})

    def params(self, player_key: str, tool: str, t: str):
        p = self.players.get(player_key)
        if not p:
            return None
        return ((p.get("t") or {}).get(tool) or {}).get(str(readable_season(t)))

    def value(self, player_key: str, tool: str, t: str, G):
        return etool_value(G, self.params(player_key, tool, t))

    def outlet_tools(self, player_key: str, t: str, tools: dict | None, groups) -> dict | None:
        """One outlet's tool map at date t with each group in `groups` read as its eTool
        (gate 1.5 (i)): base = the outlet's own grade of the eTool's tool; the pwr group
        reads game power's eTool and keeps the consolidated pwr where game power is absent."""
        if not tools:
            return tools
        out = dict(tools)
        for g in groups:
            tool = GROUP_TOOL[g]
            base = tools.get(tool)
            if base is None:
                continue
            out[g] = self.value(player_key, tool, t, base)
        return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--build", action="store_true", help="write data/etool_asof.json")
    a = ap.parse_args(argv)
    if a.build:
        fits = load_fits()
        res = build_asof(fits)
        write_artifact(res, fits)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
