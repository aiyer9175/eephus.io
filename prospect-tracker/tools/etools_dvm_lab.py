# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ETOOLS_DVM switch read (owner decision EW3-34), built to
docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md, which was committed alone before this
lab computed anything.

THE QUESTION. Should per-tool DvM+ (HitDvM+, PowerDvM+, PitchSel, BatCtrl, FB, Cmd) be built
on eTool grade changes instead of consensus grade changes? Per tool group, two reads:

  (a) persistence   an org's per-tool DvM+ in calendar year W against W + 1, Spearman across
                    the clubs, mean over window pairs; eTool minus consensus, club-clustered
                    bootstrap; NOT WORSE when the lower bound is above -0.05.
  (b) validity      a player's grade gain in a window against his later MLB outcome stat
                    beyond his starting grade (incremental out-of-fold Spearman); eTool minus
                    consensus with a lower bound above 0 (Holm over the groups), and the
                    eTool gain itself above zero (the zero comparator: no development credit).

Planted recovery runs first on synthetic outcomes (no outcome is read); a group whose
recovery fails is NOT RESOLVABLE. A group SWITCHES only when recovery holds and (a) and (b)
pass. The eTool for (b) comes from player-disjoint refits so no player is scored on an eTool
fit to his own outcome.

BANS. No pair with an endpoint dated in 2020 or 2021 (R-LV); no (b) row with a first MLB
season after 2024 (R-VM); no outcome season after 2026; no input season after its as-of
date (etool_history asserts it); no grouping, key, filter or weight by consensus FV or any
source's FV (docs/PROSPECT_ANCHOR_GATE.md). Never backtest.run_backtest, run_monthly or
build_site; nothing served moves from here.

Run:  python tools/etools_dvm_lab.py --check                 (inputs, parity, row counts; no statistic)
      python tools/etools_dvm_lab.py --dry-run               (the statistics on fixtures)
      python tools/etools_dvm_lab.py --read --gate-sha SHA   (the one read)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

import etool_history as EH  # noqa: E402
import etools as E  # noqa: E402

GATE_DOC = EH.GATE_DOC
OUT_PATH = EH.LAB_DIR / "etools_dvm_read.json"
SEED = 20261031                       # 3.4, 4.3, 4.5
REC_SEED_B = 20261101                 # 5.1
REC_SEED_A = 20261102                 # 5.2
B = 2000
REC_R = 40
REC_B = 400
MARGIN_A = -0.05                      # 3.5
MIN_CLUBS = 10                        # 3.3
N_FOLDS = 5                           # 4.3
ALPHA = 0.05                          # 4.6
R_LV = (2020, 2021)
MAX_FIRST = 2024
PLANT_BETA = 0.25                     # 5.1
PLANT_NOISE = 2.0
PLANT_TAU = 0.2                       # 5.2
REC_POWER = 0.80
REC_FALSE = 0.10
GROUPS = EH.GROUPS
#: storage.TOOL_GROUPS (every group, for the descriptive composite)
ALL_GROUPS = {"hit": "hit", "pwr": "pwr", "speed": "speed", "field": "field", "arm": "throw",
              "pitch_sel": "pitch_sel", "bat_ctrl": "bat_ctrl", "fb": "fb", "sl": "sl", "cb": "cb",
              "ch": "ch", "cmd": "cmd", "ct": "ct"}
LABEL_TOOL = dict(EH.GROUP_TOOL)          # pwr reads game power's label (ISO)
_HIT_BUCKET = {"C": "C", "1B": "INF", "2B": "INF", "3B": "INF", "SS": "INF", "INF": "INF", "MI": "INF",
               "UTIL": "INF", "DH": "INF", "OF": "OF", "LF": "OF", "CF": "OF", "RF": "OF"}
_PIT_BUCKET = {"SP": "SP", "RHP": "SP", "LHP": "SP", "RP": "RP", "MIRP": "RP", "SIRP": "RP", "CL": "RP", "CP": "RP"}


class GuardError(RuntimeError):
    pass


#: receipts gathered while the inputs are built (written into the read's artifact)
RECEIPT: dict = {}


def _r(v, nd=4):
    return E._r(v, nd)


def pos_bucket(pos) -> str | None:
    if not pos:
        return None
    first = str(pos).upper().split("/")[0].strip()
    return _HIT_BUCKET.get(first) or _PIT_BUCKET.get(first)


def fold_of(pid: int) -> int:
    h = hashlib.sha256(f"{SEED}:{int(pid)}".encode()).hexdigest()
    return int(h[:8], 16) % N_FOLDS


def holm(ps: list) -> list:
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    m = len(idx)
    prev = 0.0
    for rank, i in enumerate(sorted(idx, key=lambda i: ps[i])):
        prev = max(prev, min(1.0, (m - rank) * ps[i]))
        out[i] = round(prev, 6)
    return out


# ---------------------------------------------------------------------------
# the served club aggregation, mirrored (gate 2.1, 3.2)
# ---------------------------------------------------------------------------
def club_index(entries: dict) -> dict:
    """{org: [credit, ...]} -> {org: int DvM+ or None}: at least 3 prospects, the mean
    rounded to 2 dp, the k = 2 shrink toward the league mean, z against the unshrunk
    population sd, 100 + 10 z, the 1.35 stretch, rounded (storage's per-tool league pass)."""
    import storage as S
    vals = {}
    for org, xs in entries.items():
        if len(xs) >= 3:
            vals[org] = (round(sum(xs) / len(xs), 2), len(xs))
    out = {org: None for org in entries}
    if len(vals) < 2:
        return out
    pop = [v for v, _ in vals.values()]
    mu = sum(pop) / len(pop)
    sd = (sum((v - mu) ** 2 for v in pop) / len(pop)) ** 0.5
    if sd < 1e-6:
        return out
    for org, (v, n) in vals.items():
        w = n / (n + 2)
        z = ((w * v + (1 - w) * mu) - mu) / sd
        out[org] = int(round(S._stretch_composite(100 + 10 * z)))
    return out


def weighted_spearman(x, y, Wc) -> np.ndarray:
    """Spearman of x and y re-ranked on each weighted draw (rows of Wc are draw counts)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    Wc = np.atleast_2d(np.asarray(Wc, float))
    rp, ry = E.weighted_midranks(x, Wc), E.weighted_midranks(y, Wc)
    sw = Wc.sum(axis=1)
    d = np.where(sw > 0, sw, 1.0)
    mx, my = (Wc * rp).sum(axis=1) / d, (Wc * ry).sum(axis=1) / d
    sxx = (Wc * rp * rp).sum(axis=1) / d - mx * mx
    syy = (Wc * ry * ry).sum(axis=1) / d - my * my
    sxy = (Wc * rp * ry).sum(axis=1) / d - mx * my
    den = np.sqrt(np.clip(sxx, 0, None) * np.clip(syy, 0, None))
    return np.where(den > 1e-12, sxy / np.where(den > 0, den, 1.0), 0.0)


def persistence(idx_by_w: dict, clubs: list, pairs: list, Wc=None) -> np.ndarray | float | None:
    """Mean over window pairs of the across-club Spearman (3.3); with Wc (B x clubs draw
    counts) the bootstrap draws."""
    if not pairs:
        return None
    pos = {c: i for i, c in enumerate(clubs)}
    acc = []
    for w0, w1 in pairs:
        a, b = idx_by_w.get(w0) or {}, idx_by_w.get(w1) or {}
        cs = [c for c in clubs if a.get(c) is not None and b.get(c) is not None]
        x = [a[c] for c in cs]
        y = [b[c] for c in cs]
        if Wc is None:
            acc.append(float(weighted_spearman(x, y, np.ones((1, len(cs))))[0]))
        else:
            acc.append(weighted_spearman(x, y, Wc[:, [pos[c] for c in cs]]))
    return float(np.mean(acc)) if Wc is None else np.mean(np.vstack(acc), axis=0)


def window_pairs(idx_v: dict, clubs: list) -> list:
    """Consecutive (W, W + 1) with at least MIN_CLUBS clubs carrying a value in both, in
    every version (fixed on the full sample)."""
    ws = sorted(set.intersection(*[set(d) for d in idx_v.values()])) if idx_v else []
    out = []
    for w in ws:
        if w + 1 not in ws:
            continue
        ok = True
        for d in idx_v.values():
            n = sum(1 for c in clubs if (d[w].get(c) is not None and d[w + 1].get(c) is not None))
            ok = ok and n >= MIN_CLUBS
        if ok:
            out.append((w, w + 1))
    return out


def club_draws(n_clubs: int, Bn: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_clubs, np.full(n_clubs, 1.0 / n_clubs), size=Bn).astype(float)


def read_a(idx: dict, clubs: list, *, Bn: int = B, seed: int = SEED) -> dict:
    """idx: {version: {W: {org: DvM+}}}. P per version, Delta = E - C, rule (a)."""
    pairs = window_pairs(idx, clubs)
    out = {"window_pairs": [list(p) for p in pairs], "n_window_pairs": len(pairs)}
    if not pairs:
        out.update({"computable": False, "verdict": "NOT COMPUTABLE"})
        return out
    Wc = club_draws(len(clubs), Bn, seed)
    pts = {v: persistence(idx[v], clubs, pairs) for v in ("C", "E")}
    dr = {v: persistence(idx[v], clubs, pairs, Wc) for v in ("C", "E")}
    for v in ("C", "E"):
        out[f"P_{v}"] = E.summarize_draws(pts[v], dr[v])
    d = pts["E"] - pts["C"]
    out["delta"] = E.summarize_draws(d, dr["E"] - dr["C"])
    lb = out["delta"].get("lb95")
    out["computable"] = True
    out["not_worse"] = bool(lb is not None and lb > MARGIN_A)
    out["verdict"] = "NOT WORSE" if out["not_worse"] else "WORSE OR UNRESOLVED"
    return out


# ---------------------------------------------------------------------------
# read (b): incremental out-of-fold Spearman of the gain (gate 4.4, 4.5)
# ---------------------------------------------------------------------------
def b_preds(rows: dict) -> dict:
    y, yr, pid = rows["y"], rows["W"], rows["pid"]
    out = {}
    for v in ("C", "E"):
        out[f"{v}_full"] = E.loyo_oof([rows[f"start_{v}"], rows[f"gain_{v}"]], y, yr, pid)
        out[f"{v}_base"] = E.loyo_oof([rows[f"start_{v}"]], y, yr, pid)
    return out


def b_stats(rows: dict, preds: dict, *, Bn: int, seed: int) -> dict:
    y, yr, pid = rows["y"], rows["W"], rows["pid"]
    ok = np.all(np.vstack([np.isfinite(p) for p in preds.values()]), axis=0) & np.isfinite(y)
    rho = {k: E.within_rho(p[ok], y[ok], yr[ok]) for k, p in preds.items()}
    if any(v is None for v in rho.values()):
        return {"computable": False}
    dC = rho["C_full"] - rho["C_base"]
    dE = rho["E_full"] - rho["E_base"]
    draws = {k: [] for k in preds}
    left, k = int(Bn), 0
    while left > 0:
        nb = min(E.B_CHUNK, left)
        Wd = E.cluster_weights(pid[ok], nb, seed + k)
        for name, p in preds.items():
            draws[name].append(E.within_rho(p[ok], y[ok], yr[ok], Wd))
        left -= nb
        k += 1
    dr = {n: np.concatenate(v) for n, v in draws.items()}
    drC = dr["C_full"] - dr["C_base"]
    drE = dr["E_full"] - dr["E_base"]
    return {"computable": True, "n": int(ok.sum()), "players": int(np.unique(pid[ok]).size),
            "rho": {k: _r(v) for k, v in rho.items()},
            "d_C": E.summarize_draws(dC, drC), "d_E": E.summarize_draws(dE, drE),
            "D": E.summarize_draws(dE - dC, drE - drC)}


def b_rule(st: dict) -> tuple[bool, bool]:
    """(D lower bound above 0, d_E lower bound above 0)."""
    if not st.get("computable"):
        return False, False
    lbD, lbE = (st["D"] or {}).get("lb95"), (st["d_E"] or {}).get("lb95")
    return bool(lbD is not None and lbD > 0), bool(lbE is not None and lbE > 0)


def _z(x):
    x = np.asarray(x, float)
    s = x.std()
    return (x - x.mean()) / s if s > 0 else x * 0.0


def recovery_b(rows: dict, *, R: int = REC_R, Bn: int = REC_B, log=print) -> dict:
    """Gate 5.1 on the real (b) design with synthetic outcomes."""
    zsC, zsE, zgC, zgE = (_z(rows[k]) for k in ("start_C", "start_E", "gain_C", "gain_E"))
    scen = {"PLANT_E": lambda e: zsE + PLANT_BETA * zgE + PLANT_NOISE * e,
            "PLANT_C": lambda e: zsC + PLANT_BETA * zgC + PLANT_NOISE * e,
            "NULL": lambda e: 0.5 * zsC + 0.5 * zsE + PLANT_NOISE * e}
    out = {}
    for name, f in scen.items():
        passes = 0
        for r in range(R):
            rng = np.random.default_rng(REC_SEED_B + r)
            eps = rng.standard_normal(rows["y"].size)
            syn = dict(rows)
            syn["y"] = f(eps)
            st = b_stats(syn, b_preds(syn), Bn=Bn, seed=REC_SEED_B + 1000 * (r + 1))
            pD, pE = b_rule(st)
            passes += int(pD and pE)
        out[name] = {"replicates": R, "passes": passes, "rate": round(passes / R, 4)}
    out["holds"] = bool(out["PLANT_E"]["rate"] >= REC_POWER and out["PLANT_C"]["rate"] <= REC_FALSE
                        and out["NULL"]["rate"] <= REC_FALSE)
    log(f"    recovery (b): PLANT_E {out['PLANT_E']['rate']}, PLANT_C {out['PLANT_C']['rate']}, "
        f"NULL {out['NULL']['rate']} -> {'holds' if out['holds'] else 'FAILS'}")
    return out


def recovery_a(entries: dict, clubs: list, *, R: int = REC_R, Bn: int = REC_B, log=print) -> dict:
    """Gate 5.2. entries: {version: {W: [(org, credit), ...]}}."""
    out = {}
    for name, tau in (("PLANT", PLANT_TAU), ("NULL", 0.0)):
        lbE_pos = ni_pass = 0
        for r in range(R):
            rng = np.random.default_rng(REC_SEED_A + r + (0 if tau else 5000))
            theta = {c: rng.standard_normal() for c in clubs}
            idx = {}
            for v in ("C", "E"):
                idx[v] = {}
                for W, ent in entries[v].items():
                    if not ent:
                        continue
                    xs = np.array([x for _o, x in ent], float)
                    sdw = float(xs.std()) if xs.size > 1 else 0.0
                    perm = rng.permutation(xs)
                    by = defaultdict(list)
                    for (org, _x), px in zip(ent, perm):
                        by[org].append(float(px) + tau * sdw * theta.get(org, 0.0))
                    idx[v][W] = club_index(dict(by))
            res = read_a(idx, clubs, Bn=Bn, seed=REC_SEED_A + 1000 * (r + 1))
            lbE = (res.get("P_E") or {}).get("lb95")
            lbE_pos += int(lbE is not None and lbE > 0)
            ni_pass += int(bool(res.get("not_worse")))
        out[name] = {"replicates": R, "P_E_lb_above_0": round(lbE_pos / R, 4),
                     "not_worse_rate": round(ni_pass / R, 4)}
    out["holds"] = bool(out["PLANT"]["P_E_lb_above_0"] >= REC_POWER and out["PLANT"]["not_worse_rate"] >= REC_POWER
                        and out["NULL"]["P_E_lb_above_0"] <= REC_FALSE)
    log(f"    recovery (a): PLANT P_E>0 {out['PLANT']['P_E_lb_above_0']}, not-worse {out['PLANT']['not_worse_rate']}, "
        f"NULL P_E>0 {out['NULL']['P_E_lb_above_0']} -> {'holds' if out['holds'] else 'FAILS'}")
    return out


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def load_infos(log=print) -> tuple[dict, dict]:
    """{player_key: PlayerInfo} and {player_key: position} from the three served pools
    (debuts.json: debuted; timeseries.json: active; inactive.json: inactive), the
    current club the row's org, the listed club the latest point org on or before the debut."""
    import dev_attribution as DA
    from trades import canonical_org as co
    infos, pos = {}, {}
    for fn, status in (("debuts.json", "debuted"), ("inactive.json", "inactive"), ("timeseries.json", "active")):
        p = EH.DATA / fn
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        recs = doc if isinstance(doc, list) else (doc.get("players") or [])
        for r in recs:
            pk = r.get("player_key")
            if not pk or pk in infos:
                continue
            debut = (r.get("debut_date") or None) if status == "debuted" else None
            listed = None
            for pt in reversed(r.get("points") or []):
                if pt.get("org") and (not debut or (pt.get("snapshot_date") or "") <= debut):
                    listed = co(pt["org"])
                    break
            infos[pk] = DA.PlayerInfo(pk, co(r["org"]) if r.get("org") else None, status, debut, listed)
            pos[pk] = r.get("position")
    log(f"  pools: {len(infos)} players")
    return infos, pos


def load_trades(con, keys) -> dict:
    out, seen = defaultdict(list), set()
    for pk, d, f, to in con.execute("SELECT player_key, trade_date, from_org, to_org FROM trades "
                                    "ORDER BY trade_date, id"):
        if pk not in keys or not d:
            continue
        k = (pk, str(d)[:10], f, to)
        if k in seen:
            continue
        seen.add(k)
        out[pk].append({"trade_date": str(d)[:10], "from_org": f, "to_org": to})
    return dict(out)


def level_weight(prof: dict, pid, W: int) -> float:
    import storage as S
    if pid is None:
        return 1.0
    p = prof.get(int(pid)) or {}
    lv = (p.get(W) or {}).get("level") or (p.get(W - 1) or {}).get("level")
    if lv == "A-":
        lv = "A"
    return S._TOOL_DEV_LEVEL_WEIGHTS.get(lv, 1.0) if lv else 1.0


def build_inputs(*, log=print) -> dict:
    import dev_attribution as DA
    t0 = time.time()
    con = sqlite3.connect(f"file:{EH.db_path().as_posix()}?mode=ro", uri=True)
    try:
        board = EH.board_snapshots(con)
        ids, id_counts = EH.identities(board, log=log)
        infos, pos = load_infos(log=log)
        keys = set(infos)
        obs = DA.load_observations(con, keys)
        txs = DA.load_transactions(con, keys)
        team_org = DA.load_team_org_map(con)
        trades = load_trades(con, keys)
        blocks_needed = EH.observation_players(con)
    finally:
        con.close()
    today = date.today().isoformat()
    attr = DA.build(list(infos.values()), trades_by_player=trades, acquisitions={}, observations=obs,
                    transactions=txs, team_org=team_org, today=today)
    # the calendar ends at the end of development (VAL_4): pairs after a debut never count
    obs_f = {}
    for pk, srcs in obs.items():
        info = infos[pk]
        end = info.debut_date[:10] if (info.status == "debuted" and info.debut_date) else today
        obs_f[pk] = {s: [o for o in rows if o[0] <= end] for s, rows in srcs.items()}
    log(f"  calendars: {attr.diagnostics}; inputs in {time.time() - t0:.0f} s")
    return {"board": board, "ids": ids, "id_counts": id_counts, "infos": infos, "pos": pos, "obs": obs_f,
            "attr": attr, "blocks_needed": blocks_needed, "today": today,
            "prof": {"hit": E.player_profile("hit"), "pit": E.player_profile("pit")},
            "mlb_first": E.mlb_first_seasons()}


def dev_frames(*, log=print) -> tuple[dict, dict]:
    """The look's development frame (gate 4.3), checked against the look's universe."""
    look = json.loads(EH.EVAL_PATH.read_text(encoding="utf-8"))
    board = E.load_board(E.DEV_YEARS)
    rows, counts = E.build_universe(board, E.DEV_YEARS, log=log)
    E.attach_candidates(rows, last_season=max(E.DEV_YEARS) - 1, log=log)
    E.attach_labels(rows, log=log)
    if counts.get("rows") != (look.get("universe") or {}).get("rows"):
        raise GuardError(f"development universe {counts} differs from the look's {look.get('universe')}")
    # the row count must match; fold_fits then demands the look's final fit to 5e-6
    RECEIPT["dev_universe_now"] = counts
    RECEIPT["dev_universe_look"] = look.get("universe")
    return E.tool_frames(rows), look


def fold_fits(frames: dict, fits: dict, *, log=print) -> dict:
    """{k: {tool: Fit}} player-disjoint refits (gate 4.3); the all-rows fit must reproduce
    the look's final fit first."""
    out = {k: {} for k in range(N_FOLDS)}
    for tool, fit in fits.items():
        fr = frames[tool]
        Z = np.column_stack([fr.cands[c] for c in fit.admitted])
        full = E.etool_fit(fr.gc, Z, fr.y, np.ones(fr.n, dtype=bool))
        if full is None:
            raise GuardError(f"{tool}: no fit on the development frame")
        # receipt: today's label caches carry more MLB seasons than the look's did, so the
        # all-rows refit is compared with the look's final fit and the gap recorded
        RECEIPT.setdefault("final_fit_gap", {})[tool] = {
            "c_now": [_r(x, 6) for x in full["c"]], "c_look": [_r(x, 6) for x in fit.c],
            "max_abs_c_gap": _r(float(np.max(np.abs(np.array(full["c"]) - np.array(fit.c)))), 6),
            "n_fit_now": full["n_fit"]}
        folds = np.array([fold_of(p) for p in fr.pid])
        for k in range(N_FOLDS):
            tr = folds != k
            f = E.etool_fit(fr.gc, Z, fr.y, tr)
            U = E.etool_residuals(fr.gc, Z, f["lines"])
            mu = E._present_mean(U, Z, tr)
            out[k][tool] = EH.Fit(tool, list(fit.admitted), [(a, b, ok) for a, b, ok in f["lines"]],
                                  [float(x) for x in f["c"]], [float(x) for x in mu], label=f"fold{k}")
    log(f"  fold refits: {N_FOLDS} folds x {len(fits)} tools")
    return out


def parity(frames: dict, fits: dict, bank: EH.SubDrivers) -> dict:
    """Gate 4.3: the history's sub-driver values equal the development frame's candidates."""
    n = bad = 0
    worst = None
    for tool, fit in fits.items():
        fr = frames[tool]
        side = EH.TOOL_SIDE[tool]
        for i in range(fr.n):
            z = bank.values(int(fr.pid[i]), side, int(fr.year[i]) - 1)
            for name in fit.admitted:
                a = fr.cands[name][i]
                b = z.get(name)
                b = np.nan if b is None else float(b)
                n += 1
                if (np.isnan(a) != np.isnan(b)) or (not np.isnan(a) and abs(a - b) > 1e-9):
                    bad += 1
                    worst = worst or [tool, int(fr.pid[i]), int(fr.year[i]), name, None if np.isnan(a) else a, b]
    if bad:
        raise GuardError(f"parity: {bad} of {n} sub-driver values differ from the development frame, e.g. {worst}")
    return {"values_checked": n, "differ": 0}


# ---------------------------------------------------------------------------
# the growth frames (gate 3.1, 3.2, 4.1, 4.2)
# ---------------------------------------------------------------------------
def make_grade(asofs: dict, inp: dict):
    """grade(version, fit_key, pk, t, tools, group) -> grade or None."""
    def grade(v, fk, pk, t, tools, g):
        if not tools:
            return None
        key = ALL_GROUPS[g]
        if v == "C" or g not in EH.GROUP_TOOL:
            return tools.get(key)
        tool = EH.GROUP_TOOL[g]
        base = tools.get(tool)
        if base is None:
            return tools.get(key)
        return asofs[fk].value(pk, tool, t, base)
    return grade


def growth_frames(inp: dict, asofs: dict, *, groups_a=tuple(ALL_GROUPS), log=print) -> tuple[dict, dict, dict]:
    """(entries_a, rows_b, counts). entries_a: {group: {version: {W: [(org, credit, bucket)]}}};
    rows_b: {group: list of dicts}."""
    import dev_attribution as DA
    import storage as S
    value_fn = S._fv_to_expected_war
    grade = make_grade(asofs, inp)
    mlb30 = DA._mlb30()
    entries = {g: {"C": defaultdict(list), "E": defaultdict(list)} for g in groups_a}
    rows_b = {g: [] for g in GROUPS}
    counts = defaultdict(int)
    for pk, srcs in inp["obs"].items():
        pa = inp["attr"].get(pk)
        tenures = pa.tenures if pa else []
        if not tenures:
            counts["no_calendar"] += 1
            continue
        idn = inp["ids"].get(pk)
        pid = idn[0] if idn else None
        fk_b = f"fold{fold_of(pid)}" if pid is not None else None
        bucket = pos_bucket(inp["pos"].get(pk))
        # per (group, version, W): tenure accumulators for (a); per outlet start/gain for (b)
        acc = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))     # (g,v,W) -> i -> src -> g
        seen = defaultdict(lambda: defaultdict(set))                         # (g,v,W) -> i -> {src}
        bst = defaultdict(dict)                                              # (g,v,W) -> src -> [start_t, start, gain]
        for src, rows in srcs.items():
            for (da, _fa, ta), (db, _fb, tb) in zip(rows, rows[1:]):
                if not ta or not tb:
                    continue
                if int(da[:4]) in R_LV or int(db[:4]) in R_LV:
                    counts["pairs_dropped_rlv"] += 1
                    continue
                W = int(db[:4])
                parts = DA.split_pair(da, db, tenures)
                for g in groups_a:
                    for v in ("C", "E"):
                        x = grade(v, "final", pk, da, ta, g)
                        y = grade(v, "final", pk, db, tb, g)
                        if x is None or y is None:
                            continue
                        wx, wy = value_fn(x), value_fn(y)
                        if wx is None or wy is None:
                            continue
                        for i, f in parts:
                            acc[(g, v, W)][i][src] += (wy - wx) * f
                            seen[(g, v, W)][i].add(src)
                    if g in GROUPS and fk_b is not None:
                        for v in ("C", "E"):
                            fk = "final" if v == "C" else fk_b
                            x = grade(v, fk, pk, da, ta, g)
                            y = grade(v, fk, pk, db, tb, g)
                            if x is None or y is None:
                                continue
                            wx, wy = value_fn(x), value_fn(y)
                            dw = (wy - wx) if (wx is not None and wy is not None) else 0.0
                            rec = bst[(g, v, W)].get(src)
                            if rec is None:
                                bst[(g, v, W)][src] = [da, x, y - x, dw]
                            else:
                                if da < rec[0]:
                                    rec[0], rec[1] = da, x
                                rec[2] += y - x
                                rec[3] += dw
        # (a) entries: one per (player, club) per window, summed over the club's tenures
        for (g, v, W), by_i in acc.items():
            per_org = defaultdict(float)
            for i, by_src in by_i.items():
                org = tenures[i].org
                if not org or org not in mlb30:
                    continue
                srcs_i = seen[(g, v, W)][i]
                per_org[org] += sum(by_src[s] for s in srcs_i) / len(srcs_i)
            lw = level_weight(inp["prof"][idn[1]] if idn else {}, pid, W)
            for org, cr in per_org.items():
                entries[g][v][W].append((org, cr * lw, bucket))
        # (b) rows
        if pid is None:
            continue
        fm = inp["mlb_first"].get(pid)
        for g in GROUPS:
            for W in sorted({k[2] for k in bst if k[0] == g}):
                if fm is None or fm < W or fm > MAX_FIRST:
                    continue
                c, e = bst.get((g, "C", W)), bst.get((g, "E", W))
                if not c or not e or set(c) != set(e):
                    continue
                rows_b[g].append({"pk": pk, "pid": pid, "W": W, "first": fm,
                                  "start_C": float(np.mean([r[1] for r in c.values()])),
                                  "gain_C": float(np.mean([r[2] for r in c.values()])),
                                  "start_E": float(np.mean([r[1] for r in e.values()])),
                                  "gain_E": float(np.mean([r[2] for r in e.values()])),
                                  "gainW_C": float(np.mean([r[3] for r in c.values()])),
                                  "gainW_E": float(np.mean([r[3] for r in e.values()]))})
    counts = dict(counts)
    log(f"  growth frames: {counts}")
    return ({g: {v: dict(d) for v, d in vv.items()} for g, vv in entries.items()}, rows_b, counts)


def attach_b_labels(rows_b: dict, *, log=print) -> dict:
    data = E.load_mlb_label_data()
    out = {}
    for g, rows in rows_b.items():
        keep = []
        for r in rows:
            if r["first"] > MAX_FIRST:
                raise GuardError("an R-VM row reached the labels")
            y = E.mlb_label(LABEL_TOOL[g], r["pid"], r["W"], data)
            if y is None:
                continue
            keep.append(dict(r, y=float(y)))
        out[g] = {"y": np.array([r["y"] for r in keep], float), "W": np.array([r["W"] for r in keep]),
                  "pid": np.array([r["pid"] for r in keep]),
                  **{k: np.array([r[k] for r in keep], float)
                     for k in ("start_C", "gain_C", "start_E", "gain_E", "gainW_C", "gainW_E")}}
        log(f"    (b) {g}: {len(keep)} rows with a label of {len(rows)}")
    return out


def club_indices(entries: dict, clubs: list) -> dict:
    """{group: {version: {W: {org: DvM+}}}} (3.2)."""
    out = {}
    for g, vv in entries.items():
        out[g] = {}
        for v, byW in vv.items():
            out[g][v] = {}
            for W, ent in byW.items():
                by = defaultdict(list)
                for org, cr, _b in ent:
                    by[org].append(cr)
                out[g][v][W] = club_index(dict(by))
    return out


BUCKETS = ("C", "INF", "OF", "SP", "RP")


def composite_indices(entries: dict, idx: dict, clubs: list) -> dict:
    """Descriptive (3.7): ToolDvM+ per club and window built as storage builds it: every
    bucket carries every group's bucket-restricted index (None where thin), the counts are
    keyed by the outlet tool key, and storage._bucket_weighted_tool_dvm blends them."""
    import storage as S
    out = {"C": {}, "E": {}}
    windows = sorted({W for g in entries for W in entries[g]["C"]})
    for v in ("C", "E"):
        for W in windows:
            bidx = {}
            bcnt = defaultdict(lambda: defaultdict(dict))
            for b in BUCKETS:
                for g in entries:
                    by = defaultdict(list)
                    for org, cr, bk in entries[g][v].get(W) or []:
                        if bk == b:
                            by[org].append(cr)
                    full = {c: by.get(c, []) for c in clubs}
                    bidx[(b, g)] = club_index(full)
                    for org, xs in by.items():
                        if len(xs) >= 3:
                            bcnt[org][b][ALL_GROUPS[g]] = {"n_prospects": len(xs)}
            res = {}
            for org in clubs:
                per = {g: (idx[g][v].get(W) or {}).get(org) for g in entries}
                if not any(x is not None for x in per.values()):
                    res[org] = None
                    continue
                bb = {b: {g: bidx[(b, g)].get(org) for g in entries} for b in BUCKETS}
                res[org] = S._bucket_weighted_tool_dvm(per, bb, bcnt.get(org) or {})
            out[v][W] = res
    return out


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------
def prepare(*, log=print) -> dict:
    fits = EH.load_fits()
    inp = build_inputs(log=log)
    bank = EH.SubDrivers(EH.all_subdrivers(fits), log=log)
    frames, look = dev_frames(log=log)
    par = parity(frames, fits, bank)
    log(f"  parity: {par}")
    folds = fold_fits(frames, fits, log=log)
    asofs = {}
    res = EH.build_asof(fits, bank=bank, board=inp["board"], ids=inp["ids"],
                        blocks_needed=inp["blocks_needed"], log=log)
    asofs["final"] = _asof(res)
    for k, fk in folds.items():
        r = EH.build_asof(fk, bank=bank, board=inp["board"], ids=inp["ids"],
                          blocks_needed=inp["blocks_needed"], log=log)
        asofs[f"fold{k}"] = _asof(r)
    entries, rows_b, gcounts = growth_frames(inp, asofs, log=log)
    return {"fits": fits, "inp": inp, "bank": bank, "parity": par, "asofs": asofs, "entries": entries,
            "rows_b": rows_b, "growth_counts": gcounts, "look": look,
            "block_deltas": {t: {str(S): {"delta": [_r(x, 5) for x in v["delta"]], "n_cohort": v["n_cohort"]}
                                 for S, v in d.items()} for t, d in res["deltas"].items()}}


def _asof(res: dict) -> EH.AsOf:
    return EH.AsOf({"players": {pk: {"t": {t: {str(S): list(p) for S, p in per.items()}
                                           for t, per in v["t"].items()}}
                                for pk, v in res["players"].items()}})


def counts_only(prep: dict) -> dict:
    out = {}
    for g in ALL_GROUPS:
        ent = prep["entries"][g]["C"]
        out[g] = {"a_windows": {str(W): len(v) for W, v in sorted(ent.items())}}
    for g in GROUPS:
        out[g]["b_rows_before_labels"] = len(prep["rows_b"][g])
    out["_receipt"] = RECEIPT
    out["_growth_counts"] = prep["growth_counts"]
    return out


def read(gate_sha: str, *, log=print) -> dict:
    if OUT_PATH.exists():
        d = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if d.get("spent"):
            raise GuardError(f"{OUT_PATH} carries a spent marker ({d.get('spent_at')})")
    if not E.gate_sha_ok(gate_sha, GATE_DOC):
        raise GuardError(f"{gate_sha} does not name a commit carrying {GATE_DOC} as REGISTERED")
    E.guard_no_fv(["W", "club", "bucket", "tool_group", "fold"])
    shas_start = E.input_shas()
    t0 = time.time()
    started = E._now()
    prep = prepare(log=log)
    clubs = sorted(__import__("dev_attribution")._mlb30())
    doc = {"item": EH.ITEM, "tool": "tools/etools_dvm_lab.py", "role": "development", "gate_doc": GATE_DOC,
           "gate_sha": gate_sha, "head": E._git("rev-parse", "HEAD"), "started": started,
           "survivorship": E.SURVIVORSHIP, "parity": prep["parity"], "growth_counts": prep["growth_counts"],
           "id_counts": prep["inp"]["id_counts"], "block_deltas": prep["block_deltas"],
           "receipt": RECEIPT, "calendars": prep["inp"]["attr"].diagnostics,
           "constants": {"B": B, "seed": SEED, "rec_R": REC_R, "rec_B": REC_B, "margin_a": MARGIN_A,
                         "min_clubs": MIN_CLUBS, "folds": N_FOLDS, "alpha_holm": ALPHA,
                         "plant_beta": PLANT_BETA, "plant_noise": PLANT_NOISE, "plant_tau": PLANT_TAU},
           "spent": True, "spent_at": E._now(), "groups": {}}
    # the read is spent from here: an exception is recorded, never rerun
    try:
        rows_b = attach_b_labels(prep["rows_b"], log=log)
        idx = club_indices(prep["entries"], clubs)
        log("  part 5: planted recovery")
        rec = {}
        for g in GROUPS:
            ra = recovery_a({v: {W: [(o, c) for o, c, _b in ent] for W, ent in prep["entries"][g][v].items()}
                             for v in ("C", "E")}, clubs, log=log)
            rb = recovery_b(rows_b[g], log=log) if E.computable(rows_b[g]["W"], rows_b[g]["pid"]) else \
                {"holds": False, "why": "not computable"}
            rec[g] = {"a": ra, "b": rb}
        log("  part 3: persistence")
        ra_all = {g: read_a(idx[g], clubs) for g in ALL_GROUPS}
        comp = composite_indices(prep["entries"], idx, clubs)
        ra_comp = read_a(comp, clubs)
        log("  part 4: predictive validity")
        rb_all = {}
        for g in GROUPS:
            rows = rows_b[g]
            if not E.computable(rows["W"], rows["pid"]):
                rb_all[g] = {"computable": False, "n": int(rows["y"].size)}
                continue
            st = b_stats(rows, b_preds(rows), Bn=B, seed=SEED)
            st["counts_by_window"] = {str(int(w)): int((rows["W"] == w).sum()) for w in np.unique(rows["W"])}
            # 4.7: the gain on the expected-WAR scale (the DvM+ credit unit), reported, not deciding
            rw = dict(rows, gain_C=rows["gainW_C"], gain_E=rows["gainW_E"])
            st["secondary_war_scale_gain"] = b_stats(rw, b_preds(rw), Bn=B, seed=SEED)
            rb_all[g] = st
        ps = [(rb_all[g].get("D") or {}).get("p") if rb_all[g].get("computable") else None for g in GROUPS]
        hp = holm(ps)
        for g, p in zip(GROUPS, hp):
            if rb_all[g].get("computable"):
                rb_all[g]["D_p_holm"] = p
        for g in GROUPS:
            a, b, r = ra_all[g], rb_all[g], rec[g]
            pD, pE = b_rule(b)
            b_better = bool(pD and pE and b.get("D_p_holm") is not None and b["D_p_holm"] <= ALPHA)
            if not b.get("computable"):
                verdict, why = "NOT COMPUTABLE", "read (b) not computable (gate 4.6)"
            elif not (r["a"]["holds"] and r["b"]["holds"]):
                verdict, why = "NOT RESOLVABLE", "planted recovery fails on " + \
                    ", ".join(x for x in ("a", "b") if not r[x]["holds"])
            elif not a.get("not_worse"):
                verdict, why = "KEEP CONSENSUS", "read (a): persistence lower bound at or below -0.05"
            elif not b_better:
                verdict, why = "KEEP CONSENSUS", "read (b): " + ", ".join(
                    w for w, ok in (("D lower bound not above 0", pD), ("eTool gain does not beat zero", pE),
                                    ("Holm p above 0.05", (b.get("D_p_holm") or 1) <= ALPHA)) if not ok)
            else:
                verdict, why = "SWITCH", "recovery holds, (a) not worse, (b) better"
            doc["groups"][g] = {"verdict": verdict, "why": why, "a": a, "b": b, "recovery": r}
            log(f"  {g:9s} {verdict}: {why}")
        doc["descriptive"] = {"persistence_other_groups": {g: ra_all[g] for g in ALL_GROUPS if g not in GROUPS},
                              "persistence_composite": ra_comp}
        doc["switch"] = [g for g in GROUPS if doc["groups"][g]["verdict"] == "SWITCH"]
    except Exception as exc:                                    # noqa: BLE001
        doc["exception"] = "".join(traceback.format_exception(exc))
        log(doc["exception"])
    doc["inputs_sha256_start"] = shas_start
    doc["inputs_sha256_end"] = E.input_shas()
    doc["seconds"] = round(time.time() - t0, 1)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, indent=1, default=_json_default), encoding="utf-8", newline="\n")
    log(f"  wrote {OUT_PATH} ({doc['seconds']} s)")
    return doc


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


# ---------------------------------------------------------------------------
# fixtures (the dry run and the tests)
# ---------------------------------------------------------------------------
def fixture_b(seed: int = 3, n_players: int = 500, signal: float = 0.4) -> dict:
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_players):
        for W in rng.choice(np.arange(2012, 2020), size=2, replace=False):
            sC = rng.normal(50, 5)
            gC = rng.normal(0, 3)
            stat = rng.normal(0, 2)
            sE, gE = sC + rng.normal(0, 1), 0.5 * gC + stat
            y = 0.1 * sE + signal * stat + rng.normal(0, 1.5)
            rows.append((p, W, sC, gC, sE, gE, y))
    a = np.array(rows, float)
    return {"pid": a[:, 0].astype(int), "W": a[:, 1].astype(int), "start_C": a[:, 2], "gain_C": a[:, 3],
            "start_E": a[:, 4], "gain_E": a[:, 5], "y": a[:, 6]}


def fixture_a(seed: int = 5, clubs=None, persistent: float = 1.0) -> dict:
    rng = np.random.default_rng(seed)
    clubs = clubs or [f"C{i:02d}" for i in range(30)]
    eff = {c: rng.normal() for c in clubs}
    idx = {"C": {}, "E": {}}
    for v in ("C", "E"):
        for W in range(2012, 2020):
            by = {c: [persistent * eff[c] + rng.normal(0, 1) for _ in range(12)] for c in clubs}
            idx[v][W] = club_index(by)
    return idx


def dry_run(log=print) -> dict:
    clubs = [f"C{i:02d}" for i in range(30)]
    a = read_a(fixture_a(clubs=clubs), clubs, Bn=200)
    rows = fixture_b()
    st = b_stats(rows, b_preds(rows), Bn=200, seed=SEED)
    log(f"  dry run (a): P_C {a['P_C']['d']} P_E {a['P_E']['d']} delta {a['delta']['d']} -> {a['verdict']}")
    log(f"  dry run (b): d_C {st['d_C']['d']} d_E {st['d_E']['d']} D {st['D']['d']} (LB {st['D']['lb95']})")
    return {"a": a, "b": st}


def check(log=print) -> dict:
    prep = prepare(log=log)
    c = counts_only(prep)
    log(json.dumps(c, indent=1))
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--gate-sha")
    a = ap.parse_args(argv)
    if a.dry_run:
        dry_run()
        return 0
    if a.check:
        check()
        return 0
    if a.read:
        if not a.gate_sha:
            ap.error("--read needs --gate-sha")
        read(a.gate_sha)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
