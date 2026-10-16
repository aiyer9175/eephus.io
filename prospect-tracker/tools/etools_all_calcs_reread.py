# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The registered re-reads of ETOOLS_ALL_CALCS (docs/tools-2026-10/ETOOLS_ALL_CALCS.md Part 3).

R-TIP (3.1): on the eTools development frame, leave one board year out and player-disjoint,
the eTool is fit on the training rows only and a TIP table (5-point bins, thin under 15,
PAVA) is fit on the training rows twice, at the eTool and at the consensus start G_c; each is
read at its own grade on the test rows. d = MAE(eTool table) - MAE(consensus table), paired
player-clustered bootstrap B 2000 seed 20261030; NON-INFERIOR when the upper 95% bound of d is
at most 5% of the consensus table's MAE.

R-TV (3.3): bayes_trade_value.compute_all_trade_values run twice on the identical players of
the rebuilt export, composite_stuff_plus on the consensus basis (tools.composite_cons) and on
the eTool basis; SWITCH only if every output is identical.

Each read runs once and writes data/_labs/etools/etools_all_calcs_reread.json (role
development, off the webroot). Bans: no 2020 or 2021 list, no 2025 or later debut, no
consensus-FV cell; never backtest.run_backtest.

Run:  python tools/etools_all_calcs_reread.py --tip --gate-sha SHA
      python tools/etools_all_calcs_reread.py --tv  --gate-sha SHA
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GATE_DOC = "docs/tools-2026-10/ETOOLS_ALL_CALCS.md"
OUT_PATH = ROOT / "data" / "_labs" / "etools" / "etools_all_calcs_reread.json"
TIP_TOOLS = ("hit", "game_pwr", "fb", "cmd")
TIP_STAT = {"hit": "MLB K% (negated)", "game_pwr": "MLB ISO", "fb": "pitcher K%", "cmd": "pitcher BB% (negated)"}
SEED = 20261030
B = 2000
CHUNK = 500
MARGIN_SHARE = 0.05


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _r(v, nd=5):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def gate_sha_ok(sha: str | None) -> bool:
    if not sha:
        return False
    try:
        txt = subprocess.run(["git", "show", f"{sha}:prospect-tracker/{GATE_DOC}"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return False
    return "\nRegistration status: REGISTERED\n" in txt.replace("\r\n", "\n")


def _load_out() -> dict:
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_out(doc: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")


def tip_read_at(tip: dict, g: np.ndarray) -> np.ndarray:
    """TIP table read at a grade: linear between the knots, flat beyond (tool_implied 1.2)."""
    return np.interp(np.asarray(g, float), np.asarray(tip["grade"], float), np.asarray(tip["stat"], float))


def tip_fold_preds(gc, Z, ys: dict, y, year, pid, fit_fn, apply_fn, tip_fn, mask_fn):
    """Per test board year: the eTool fit on the training rows, the two TIP tables, the
    out-of-fold reads. Returns (pred_etool, pred_consensus, folds)."""
    pe = np.full(y.size, np.nan)
    pc = np.full(y.size, np.nan)
    folds = {}
    for Y in np.unique(year):
        tr = mask_fn(year, pid, Y)
        te = year == Y
        fit = fit_fn(gc, Z, ys, tr)
        if fit is None:
            folds[int(Y)] = "no eTool fit"
            continue
        e = apply_fn(gc, Z, fit)
        mtr = tr & np.isfinite(y)
        tip_e = tip_fn(e[mtr], y[mtr])
        tip_c = tip_fn(gc[mtr], y[mtr])
        if tip_e is None or tip_c is None:
            folds[int(Y)] = "no TIP table"
            continue
        mte = te & np.isfinite(y)
        pe[mte] = tip_read_at(tip_e, e[mte])
        pc[mte] = tip_read_at(tip_c, gc[mte])
        folds[int(Y)] = int(mte.sum())
    return pe, pc, folds


def mae_gap_draws(ae: np.ndarray, ac: np.ndarray, pid: np.ndarray, *, Bn: int = B, seed: int = SEED) -> np.ndarray:
    """Player-clustered paired bootstrap of MAE(e) - MAE(c), in chunks."""
    players, inv = np.unique(pid, return_inverse=True)
    out = []
    left, k = int(Bn), 0
    while left > 0:
        nb = min(CHUNK, left)
        rng = np.random.default_rng(seed + k)
        cnt = rng.multinomial(players.size, np.full(players.size, 1.0 / players.size), size=nb)
        W = cnt[:, inv].astype(np.float64)
        tot = W.sum(axis=1)
        out.append((W @ ae - W @ ac) / tot)
        left -= nb
        k += 1
    return np.concatenate(out) if out else np.array([])


def tip_verdict(ae: np.ndarray, ac: np.ndarray, pid: np.ndarray, *, Bn: int = B) -> dict:
    mae_e, mae_c = float(ae.mean()), float(ac.mean())
    d = mae_e - mae_c
    draws = mae_gap_draws(ae, ac, pid, Bn=Bn)
    ub = float(np.percentile(draws, 95.0)) if draws.size else None
    margin = MARGIN_SHARE * mae_c
    ok = ub is not None and ub <= margin
    return {"n": int(ae.size), "players": int(np.unique(pid).size), "mae_etool": _r(mae_e, 6),
            "mae_consensus": _r(mae_c, 6), "d": _r(d, 6), "ub95": _r(ub, 6),
            "ci95": [_r(float(np.percentile(draws, 2.5)), 6), _r(float(np.percentile(draws, 97.5)), 6)]
            if draws.size else None,
            "margin": _r(margin, 6), "draws": int(draws.size),
            "verdict": "NON-INFERIOR" if ok else "NOT NON-INFERIOR"}


def run_tip(gate_sha: str, log=print) -> dict:
    import etools as E
    look = json.loads(E.EVAL_PATH.read_text(encoding="utf-8"))
    if not look.get("spent") or "etools" not in look:
        raise SystemExit("no spent eTools look to read the admitted sets from")
    E.guard_years(E.DEV_YEARS)
    if set(E.DEV_YEARS) & {2020, 2021}:
        raise SystemExit("R-LV year in the frame")
    t0 = time.time()
    board = E.load_board(E.DEV_YEARS)
    rows, counts = E.build_universe(board, E.DEV_YEARS, log=log)
    E.attach_candidates(rows, last_season=max(E.DEV_YEARS) - 1, log=log)
    E.attach_labels(rows, log=log)
    if counts != look.get("universe"):
        raise SystemExit(f"universe {counts} differs from the look's {look.get('universe')}")
    frames = E.tool_frames(rows)
    log(f"  frames built in {time.time() - t0:.0f} s")
    out = {}
    for tool in TIP_TOOLS:
        fr = frames[tool]
        v = look["etools"][tool]
        if v.get("verdict") != "PASS":
            out[tool] = {"verdict": "NOT READ", "why": "no passing eTool"}
            continue
        adm = list(v["admitted"])
        Z = np.column_stack([fr.cands[c] for c in adm])
        y = fr.y["mlb"]
        pe, pc, folds = tip_fold_preds(fr.gc, Z, fr.y, y, fr.year, fr.pid,
                                       E.etool_fit, E.etool_apply, E.fit_tip, E.fold_train_mask)
        m = np.isfinite(pe) & np.isfinite(pc) & np.isfinite(y)
        if int(np.isin(fr.year[m], [2020, 2021]).sum()):
            raise SystemExit("R-LV row scored")
        ae, ac = np.abs(pe[m] - y[m]), np.abs(pc[m] - y[m])
        rec = tip_verdict(ae, ac, fr.pid[m])
        rec.update({"stat": TIP_STAT[tool], "admitted": adm, "folds": folds,
                    "board_years": sorted(int(x) for x in np.unique(fr.year[m]))})
        out[tool] = rec
        log(f"  R-TIP {tool:9s} n {rec['n']}: MAE eTool {rec['mae_etool']} vs consensus {rec['mae_consensus']}, "
            f"d {rec['d']} UB95 {rec['ub95']} margin {rec['margin']} -> {rec['verdict']}")
    return {"read": "R-TIP", "ran_at": _now(), "gate_sha": gate_sha, "seed": SEED, "B": B,
            "margin_share": MARGIN_SHARE, "frame": "eTools development frame, L_MLB, LOYO player-disjoint",
            "universe": counts, "seconds": round(time.time() - t0, 1), "tools": out}


def _tv_players(ts_path: Path) -> tuple[list, dict]:
    """The player list tools/export_trade_values.py prices (timeseries plus debuts)."""
    sys.path.insert(1, str(ROOT / "tools"))
    import export_trade_values as ETV
    players, norms = ETV._load_players(ts_path.parent)
    return players, norms or {}


def run_tv(gate_sha: str, log=print) -> dict:
    """R-TV. The export must carry tools.composite_cons (the rebuilt timeseries)."""
    import bayes_trade_value as BT
    ts = ROOT / "data" / "timeseries.json"
    players, norms = _tv_players(ts)
    with_cons = [p for p in players if isinstance((p.get("tools") or {}).get("composite_cons"), dict)]
    if not with_cons:
        raise SystemExit("the export carries no tools.composite_cons: rebuild it with the flag on first")
    n_diff_input = 0
    for p in players:
        t = p.get("tools") or {}
        cc = t.get("composite_cons")
        if isinstance(cc, dict) and cc.get("composite_stuff_plus") != t.get("composite_stuff_plus"):
            n_diff_input += 1
    t0 = time.time()
    keep = BT.POLICY_STUFF_PLUS_BASIS
    try:
        BT.POLICY_STUFF_PLUS_BASIS = "etools"
        BT._reset_cache()
        res_e = BT.compute_all_trade_values(copy.deepcopy(players), level_norms=norms)
        BT.POLICY_STUFF_PLUS_BASIS = "consensus"
        BT._reset_cache()
        res_c = BT.compute_all_trade_values(copy.deepcopy(players), level_norms=norms)
    finally:
        BT.POLICY_STUFF_PLUS_BASIS = keep
    def _key(r):
        return r.get("player_key") or r.get("key") or r.get("name")
    by_c = {_key(r): r for r in res_c}
    diffs = []
    for r in res_e:
        k = _key(r)
        c = by_c.get(k)
        a = json.dumps(r, sort_keys=True, default=str)
        b = json.dumps(c, sort_keys=True, default=str)
        if a != b:
            diffs.append({"player_key": k,
                          "value_etool": r.get("trade_value_mm", r.get("value_mm")),
                          "value_consensus": (c or {}).get("trade_value_mm", (c or {}).get("value_mm")),
                          "tags_etool": (r.get("archetype_policy") or {}).get("tags"),
                          "tags_consensus": ((c or {}).get("archetype_policy") or {}).get("tags")})
    rec = {"read": "R-TV", "ran_at": _now(), "gate_sha": gate_sha, "players": len(res_e),
           "players_whose_stuff_plus_input_differs": n_diff_input,
           "players_whose_output_differs": len(diffs), "differences": diffs[:200],
           "seconds": round(time.time() - t0, 1),
           "verdict": "SWITCH" if not diffs else "KEEP CONSENSUS"}
    log(f"  R-TV {len(res_e)} players, input differs on {n_diff_input}, output differs on {len(diffs)} -> {rec['verdict']}")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tip", action="store_true")
    ap.add_argument("--tv", action="store_true")
    ap.add_argument("--gate-sha", required=True)
    a = ap.parse_args(argv)
    if not gate_sha_ok(a.gate_sha):
        raise SystemExit(f"{a.gate_sha} does not carry {GATE_DOC} as REGISTERED")
    doc = _load_out() or {"item": "ETOOLS_ALL_CALCS", "role": "development", "gate_doc": GATE_DOC}
    if a.tip:
        if (doc.get("R_TIP") or {}).get("ran_at"):
            raise SystemExit("R-TIP is spent")
        doc["R_TIP"] = run_tip(a.gate_sha)
        _write_out(doc)
    if a.tv:
        if (doc.get("R_TV") or {}).get("ran_at"):
            raise SystemExit("R-TV is spent")
        doc["R_TV"] = run_tv(a.gate_sha)
        _write_out(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
