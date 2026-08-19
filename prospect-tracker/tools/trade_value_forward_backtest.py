"""First trade-value forward backtest: instrument-maturation eval.

Reads prospects.db trade_value_history and computes the three pre-registered
descriptive statistics frozen in docs/trade-2026-08-19/TRADE_FORWARD_GATE.md:

  S1 value stability: pooled Spearman of value(T) vs value(T+~30d), player-
     clustered bootstrap CI (B=1000).
  S2 movement signal: Spearman of value(T) vs DELTA(T..T+~30d) against a
     zero-information within-date shuffle control (B=1000). DELTA contains
     -value(T) by construction, so the raw rho is mechanically coupled; the
     control's |rho| distribution bounds what pairing arithmetic alone makes.
  S3 coverage accounting: pairs formed, drops by reason.

NO win claims. S2 inside the control band means "no evidence surplus predicts
short-horizon movement; horizon too short or instrument too young", NOT
"trade values are wrong". Expected at 30d.

Writes results as a forward_backtest block INSIDE data/trade_machine_eval.json
(house convention: neutral/failed results live as blocks in the parent
artifact), preserving every existing key, and fills generated_at.

Usage:
    python tools/trade_value_forward_backtest.py            # run + write
    python tools/trade_value_forward_backtest.py --dry-run  # run, no write

Refuses to run with fewer than 2 snapshot dates (gate G-T3).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = _ROOT / "prospects.db"
ARTIFACT = _ROOT / "data" / "trade_machine_eval.json"

SEED = 20260819
B_BOOT = 1000
B_SHUFFLE = 1000
GAP_LO, GAP_HI, GAP_TARGET = 25, 35, 30

INTERPRETATION_S1 = (
    "Stability reading of the instrument, not an accuracy reading. High rho "
    "means the board's value ordering is not churning noise at 30d. Neither "
    "outcome says trade values are right or wrong."
)
INTERPRETATION_S2_NULL = (
    "No evidence surplus predicts short-horizon movement; horizon too short "
    "or instrument too young. NOT 'trade values are wrong'. Expected at 30d."
)
INTERPRETATION_S2_EXCESS = (
    "Observed |rho| exceeds the control band; reported as a descriptive "
    "excess only. No win claim: a 30d value delta is not an outcome, it is "
    "the instrument talking to itself."
)


class TooFewSnapshots(RuntimeError):
    """Raised when trade_value_history has fewer than 2 snapshot dates."""


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rho via average ranks + Pearson. Handles ties."""
    from scipy.stats import rankdata

    rx = rankdata(x)
    ry = rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    if denom == 0:
        return float("nan")
    return float((rx * ry).sum() / denom)


def load_history(db_path: Path = DB_PATH):
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT player_key, snapshot_date, trade_value_mm "
            "FROM trade_value_history"
        ).fetchall()
    finally:
        con.close()
    return rows


def pair_snapshots(dates: list[str]) -> dict[str, str]:
    """Map each origin date T to its partner T' with gap in [25,35]d,
    minimizing |gap-30|, ties to the earlier T'."""
    ds = sorted(dates)
    dobj = {d: _dt.date.fromisoformat(d) for d in ds}
    partner: dict[str, str] = {}
    for t in ds:
        best = None
        for t2 in ds:
            gap = (dobj[t2] - dobj[t]).days
            if GAP_LO <= gap <= GAP_HI:
                key = (abs(gap - GAP_TARGET), t2)
                if best is None or key < best[0]:
                    best = (key, t2)
        if best is not None:
            partner[t] = best[1]
    return partner


def run_lab(db_path: Path = DB_PATH, b_boot: int = B_BOOT,
            b_shuffle: int = B_SHUFFLE, seed: int = SEED) -> dict:
    rows = load_history(db_path)
    dates = sorted({r[1] for r in rows})
    if len(dates) < 2:
        raise TooFewSnapshots(
            f"trade_value_history has {len(dates)} snapshot date(s); "
            "need at least 2 to form any forward pair. Refusing to run."
        )

    by_date: dict[str, dict[str, float | None]] = {d: {} for d in dates}
    for pk, d, v in rows:
        by_date[d][pk] = v

    partner = pair_snapshots(dates)
    unpartnered = [d for d in dates if d not in partner]
    rows_at_unpartnered = sum(len(by_date[d]) for d in unpartnered)

    # Build the pooled pair frame.
    players: list[str] = []
    date_idx: list[int] = []
    v_t: list[float] = []
    v_t2: list[float] = []
    n_candidates = 0
    drop_absent = 0
    drop_null_t = 0
    drop_null_t2 = 0
    origin_dates = sorted(partner)
    for di, t in enumerate(origin_dates):
        t2 = partner[t]
        snap_t, snap_t2 = by_date[t], by_date[t2]
        for pk, val in snap_t.items():
            n_candidates += 1
            if val is None:
                drop_null_t += 1
                continue
            if pk not in snap_t2:
                drop_absent += 1
                continue
            val2 = snap_t2[pk]
            if val2 is None:
                drop_null_t2 += 1
                continue
            players.append(pk)
            date_idx.append(di)
            v_t.append(float(val))
            v_t2.append(float(val2))

    n_pairs = len(v_t)
    if n_pairs == 0:
        raise TooFewSnapshots(
            "No (player, T) pair has a partner snapshot in "
            f"[{GAP_LO},{GAP_HI}]d. Instrument too young for this lab."
        )

    x = np.asarray(v_t)
    y = np.asarray(v_t2)
    date_arr = np.asarray(date_idx)
    uniq_players, player_arr = np.unique(players, return_inverse=True)
    n_players = len(uniq_players)
    rng = np.random.default_rng(seed)

    # --- S1: pooled Spearman + player-clustered bootstrap -----------------
    s1_rho = _spearman(x, y)
    # Precompute row indices per player for the clustered resample.
    order = np.argsort(player_arr, kind="stable")
    sorted_pl = player_arr[order]
    starts = np.searchsorted(sorted_pl, np.arange(n_players))
    ends = np.searchsorted(sorted_pl, np.arange(n_players), side="right")
    boot = np.empty(b_boot)
    for b in range(b_boot):
        drawn = rng.integers(0, n_players, n_players)
        idx = np.concatenate([order[starts[p]:ends[p]] for p in drawn])
        boot[b] = _spearman(x[idx], y[idx])
    s1_ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]

    # --- S2: movement signal vs within-date shuffle control ---------------
    delta = y - x
    s2_rho = _spearman(x, delta)
    # Row indices per origin date for within-date permutation.
    dorder = np.argsort(date_arr, kind="stable")
    n_dates = len(origin_dates)
    dstarts = np.searchsorted(date_arr[dorder], np.arange(n_dates))
    dends = np.searchsorted(date_arr[dorder], np.arange(n_dates), side="right")
    ctrl = np.empty(b_shuffle)
    for b in range(b_shuffle):
        x_sh = x.copy()
        for di in range(n_dates):
            grp = dorder[dstarts[di]:dends[di]]
            x_sh[grp] = x_sh[grp[rng.permutation(len(grp))]]
        ctrl[b] = _spearman(x_sh, y - x_sh)
    ctrl_abs = np.abs(ctrl)
    ctrl_abs_hi = float(np.percentile(ctrl_abs, 97.5))
    exceeds = bool(abs(s2_rho) > ctrl_abs_hi)

    result = {
        "s3_coverage": {
            "snapshot_dates_total": len(dates),
            "snapshot_date_range": [dates[0], dates[-1]],
            "origin_dates_with_partner": len(origin_dates),
            "origin_date_range": [origin_dates[0], origin_dates[-1]],
            "origin_dates_without_partner": len(unpartnered),
            "rows_at_unpartnered_dates": rows_at_unpartnered,
            "candidate_rows_at_partnered_dates": n_candidates,
            "dropped_player_absent_at_t2": drop_absent,
            "dropped_null_value_at_t": drop_null_t,
            "dropped_null_value_at_t2": drop_null_t2,
            "n_pairs": n_pairs,
            "n_players": n_players,
            "retained_fraction": round(n_pairs / n_candidates, 4),
        },
        "s1_value_stability": {
            "spearman": round(s1_rho, 6),
            "ci95_player_clustered_bootstrap": [round(c, 6) for c in s1_ci],
            "bootstrap_B": b_boot,
            "seed": seed,
            "n_pairs": n_pairs,
            "n_players": n_players,
            "n_origin_dates": len(origin_dates),
            "interpretation": INTERPRETATION_S1,
        },
        "s2_movement_signal": {
            "spearman_value_vs_delta": round(s2_rho, 6),
            "abs_rho": round(abs(s2_rho), 6),
            "control": {
                "design": "within-date shuffle of value(T), same pairing; "
                          "delta recomputed off the shuffled value so the "
                          "mechanical -value(T) coupling stays in the null",
                "B": b_shuffle,
                "seed": seed,
                "rho_mean": round(float(ctrl.mean()), 6),
                "rho_pct_2_5": round(float(np.percentile(ctrl, 2.5)), 6),
                "rho_pct_97_5": round(float(np.percentile(ctrl, 97.5)), 6),
                "abs_rho_pct_97_5": round(ctrl_abs_hi, 6),
            },
            "observed_abs_rho_exceeds_control": exceeds,
            "n_pairs": n_pairs,
            "interpretation": (
                INTERPRETATION_S2_EXCESS if exceeds else INTERPRETATION_S2_NULL
            ),
        },
    }
    return result


def print_lab(result: dict) -> None:
    s3 = result["s3_coverage"]
    s1 = result["s1_value_stability"]
    s2 = result["s2_movement_signal"]
    c = s2["control"]
    print("S3 coverage:")
    print(f"  snapshot dates total: {s3['snapshot_dates_total']} "
          f"({s3['snapshot_date_range'][0]} .. {s3['snapshot_date_range'][1]})")
    print(f"  origin dates with a partner: {s3['origin_dates_with_partner']} "
          f"({s3['origin_date_range'][0]} .. {s3['origin_date_range'][1]})")
    print(f"  origin dates without a partner in [25,35]d: "
          f"{s3['origin_dates_without_partner']} "
          f"(rows at those dates: {s3['rows_at_unpartnered_dates']})")
    print(f"  candidate (player,T) rows at partnered origin dates: "
          f"{s3['candidate_rows_at_partnered_dates']}")
    print(f"  dropped, player absent at T': {s3['dropped_player_absent_at_t2']}")
    print(f"  dropped, NULL value at T: {s3['dropped_null_value_at_t']}")
    print(f"  dropped, NULL value at T': {s3['dropped_null_value_at_t2']}")
    print(f"  pooled pairs: {s3['n_pairs']}")
    print(f"  distinct players in pool: {s3['n_players']}")
    print(f"  retained fraction of partnered-origin rows: "
          f"{s3['retained_fraction']}")
    print()
    print("S1 value stability (value T vs value T+~30d):")
    print(f"  spearman rho = {s1['spearman']}")
    print(f"  player-clustered bootstrap B={s1['bootstrap_B']} seed={s1['seed']}")
    print(f"  95% CI = {s1['ci95_player_clustered_bootstrap']}")
    print(f"  n_pairs = {s1['n_pairs']}, n_players = {s1['n_players']}, "
          f"n_origin_dates = {s1['n_origin_dates']}")
    print()
    print("S2 movement signal (value T vs DELTA T..T+~30d):")
    print(f"  observed rho = {s2['spearman_value_vs_delta']}  "
          f"|rho| = {s2['abs_rho']}")
    print(f"  control (within-date shuffle, B={c['B']} seed={c['seed']}):")
    print(f"    mean rho = {c['rho_mean']}")
    print(f"    rho pct [2.5, 97.5] = [{c['rho_pct_2_5']}, {c['rho_pct_97_5']}]")
    print(f"    |rho| pct 97.5 = {c['abs_rho_pct_97_5']}")
    print(f"    observed |rho| > control |rho| p97.5: "
          f"{s2['observed_abs_rho_exceeds_control']}")
    print(f"  interpretation: {s2['interpretation']}")


def write_artifact(result: dict, artifact_path: Path = ARTIFACT) -> None:
    with open(artifact_path, encoding="utf-8") as f:
        existing = json.load(f)
    block = {
        "generated_at": _dt.date.today().isoformat(),
        "kind": "instrument_maturation",
        "gate_doc": "docs/trade-2026-08-19/TRADE_FORWARD_GATE.md",
        "source": "prospects.db trade_value_history",
        "horizon_days": [GAP_LO, GAP_HI],
        "no_win_claims": True,
    }
    block.update(result)
    existing["forward_backtest"] = block
    existing["generated_at"] = _dt.date.today().isoformat()
    tmp = artifact_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")
    tmp.replace(artifact_path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="run the lab, print results, write nothing")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args(argv)
    try:
        result = run_lab(Path(args.db))
    except TooFewSnapshots as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print_lab(result)
    if not args.dry_run:
        write_artifact(result)
        print(f"\nwrote forward_backtest block into {ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
