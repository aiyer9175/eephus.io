# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Adjudicate docs/SC_PLUS_RECALIBRATION_GATE.md against the SHIPPED code.

The lab (sc_plus_recalibration_lab.py) scores candidate variants it defines
itself. This runs the gate against what statcast_plus.py, eta.py, storage.py
and efv_score.py ACTUALLY do after the change, so a criterion cannot pass in
the lab and fail on the site. Read-only; writes nothing.

Run: python tools/sc_plus_ship_verify.py
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_score as ES          # noqa: E402
import statcast_plus as SP      # noqa: E402
import storage as STO           # noqa: E402
import eta as ETA               # noqa: E402

# The pre-ship reference is ship 1 (shrink, pre-rescale), reconstructed by
# dividing by 1.0 instead of the coverage sd. Ship 2 is judged against it.
PRE_THRESH = {"eta_elite": 130, "eta_top": 115, "eta_bot": 85,
              "brk": 115, "brk_stat": 130, "spot_elite": 120,
              "spot_above": 105, "spot_below": 95}
NOW_THRESH = {"eta_elite": 143, "eta_top": 122, "eta_bot": 77,
              "brk": STO._BREAKOUT_STATCAST_PLUS_GATE,
              "brk_stat": STO._BREAKOUT_STAT_STATCAST_PLUS_GATE,
              "spot_elite": 130, "spot_above": 107, "spot_below": 92}


def ship1_score(player, pool):
    """Shipped shrink + shipped pool, WITHOUT the coverage divisor."""
    is_pit = SP._is_pitcher(player)
    row = SP._extract_pitcher(player) if is_pit else SP._extract_hitter(player)
    side = pool.get("pit" if is_pit else "hit") or {}
    got = SP._legs(row, SP._component_volumes(player), side)
    if got is None:
        return None
    return int(round(100 + (sum(got[0]) / len(got[0])) * 10))


def main():
    players = json.loads((ROOT / "data" / "timeseries.json")
                         .read_text(encoding="utf-8"))["players"]
    pool = SP.build_pool(players)
    now = {p["player_key"]: SP.compute_statcast_plus(p, pool) for p in players}
    pre = {p["player_key"]: ship1_score(p, pool) for p in players}
    by = {p["player_key"]: p for p in players}
    ok = True

    def check(tag, cond, detail):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {tag}: {detail}")

    print("SHIP 2 gate, adjudicated against shipped code")

    # S2.1 served points per sigma per coverage class
    cells = {}
    for p in players:
        v = now.get(p["player_key"])
        if v is None:
            continue
        side = "pit" if SP._is_pitcher(p) else "hit"
        row = SP._extract_pitcher(p) if side == "pit" else SP._extract_hitter(p)
        got = SP._legs(row, SP._component_volumes(p), pool[side])
        cells.setdefault(f"{side}:{len(got[1].split('|'))}leg", []).append(float(v))
    worst = 0.0
    for c, v in sorted(cells.items()):
        if len(v) < 50:
            continue
        sd = st.pstdev(v)
        worst = max(worst, abs(sd - 10.0))
        print(f"      {c:<12} n={len(v):<5} served sd {sd:.2f}")
    check("S2.1 every coverage class 9.5-10.5", worst <= 0.5,
          f"worst deviation {worst:.3f}")

    # S2.2 top 10 volume + site max
    top = sorted(((k, v) for k, v in now.items() if v is not None),
                 key=lambda kv: -kv[1])[:10]
    bad = []
    for k, v in top:
        p = by[k]
        side = "pit" if SP._is_pitcher(p) else "hit"
        row = SP._extract_pitcher(p) if side == "pit" else SP._extract_hitter(p)
        vols = SP._component_volumes(p)
        legs = SP._legs(row, vols, pool[side])[1].split("|")
        for leg in legs:
            fam = SP._VOLUME_FAMILY.get(leg)
            if fam and (vols.get(fam) or 0) < SP._SAMPLE_FLOOR[fam]:
                bad.append((k, leg, vols.get(fam)))
    mx = top[0][1]
    check("S2.2 top-10 legs all above floor", not bad, f"violations {bad}")
    check("S2.2 site max in [125,150]", 125 <= mx <= 150,
          f"max {mx} ({top[0][0]})")

    # S2.3 populations preserved through the remap.
    # The registered tolerance (+/-2 rows, or 5% above 40 rows) assumed a
    # continuous scale. SC+ is an INTEGER, so in the tails one step of the grid
    # is worth more than the whole tolerance. For every gate this reports the
    # best population any integer threshold could achieve, which separates
    # "the remap is wrong" from "the grid cannot do better".
    print("      populations, ship1 threshold -> ship2 threshold")
    nowv = [v for v in now.values() if v is not None]
    s23_within, s23_optimal = True, True
    for key in PRE_THRESH:
        lo = key in ("eta_bot", "spot_below")

        def pop(vals, t, lo=lo):
            return sum(1 for v in vals if (v <= t if lo else v >= t))

        a = sum(1 for v in pre.values() if v is not None
                and (v <= PRE_THRESH[key] if lo else v >= PRE_THRESH[key]))
        b = pop(nowv, NOW_THRESH[key])
        d = b - a
        tol = max(2, 0.05 * a)
        best = min(range(30, 200), key=lambda t: (abs(pop(nowv, t) - a), abs(t - NOW_THRESH[key])))
        bestd = pop(nowv, best) - a
        if abs(d) > tol:
            s23_within = False
        if abs(bestd) < abs(d):
            s23_optimal = False
        print(f"      {key:<11} {PRE_THRESH[key]:>3}->{NOW_THRESH[key]:<3} "
              f"{a:>5} -> {b:<5} delta {d:+d} ({100*d/max(a,1):+.1f}%) "
              f"{'within tol' if abs(d) <= tol else 'OVER tol'}; "
              f"best integer {best} gives {bestd:+d}")
    check("S2.3 within the REGISTERED tolerance", s23_within,
          "see table (this is the criterion as written)")
    check("S2.3 no integer threshold preserves populations better", s23_optimal,
          "shipped cuts are the grid optimum")

    # S2.4 TBS band
    def band(v, lo, hi):
        return None if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    d = [abs(band(now[k], 70, 145) - band(pre[k], 80, 130))
         for k in pre if pre[k] is not None and now[k] is not None]
    check("S2.4 TBS base mean move < 0.005", st.mean(d) * 0.20 < 0.005,
          f"mean {st.mean(d)*0.20:.4f} max {max(d)*0.20:.4f}")

    # S2.5 tilt spread preserved
    for side in ("hit", "pit"):
        old_slope = max(0.0, ES._SC_FWD_R[side]) * ES._SC_TILT_PER_PT_AT_R1
        a, b = [], []
        for p in players:
            if (SP._is_pitcher(p)) != (side == "pit"):
                continue
            k = p["player_key"]
            if pre[k] is not None:
                a.append(min(1.18, max(0.82, 1 + (pre[k] - 100) * old_slope)))
            if now[k] is not None:
                b.append(ES._statcast_factor({"statcast_plus": now[k]}, side))
        mv = 100 * (st.pstdev(b) - st.pstdev(a)) / st.pstdev(a)
        check(f"S2.5 tilt sd preserved ({side})", abs(mv) <= 2.0,
              f"{st.pstdev(a):.5f} -> {st.pstdev(b):.5f} ({mv:+.2f}%)")

    # Consumer wiring: the eta bands must actually move with the constants.
    check("eta band edges wired",
          ETA.estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                           statcast_plus=143).statcast_plus_adj == -0.50
          and ETA.estimate_eta("AA", 21.0, False, 50, {"ops": "0.720"},
                               statcast_plus=142).statcast_plus_adj == -0.25,
          "143 -> -0.50, 142 -> -0.25")

    print("\nSHIP 1 gate")
    s0 = json.loads((ROOT / "docs" / "sc-plus-2026-08-07" / "battery.json")
                    .read_text(encoding="utf-8"))
    check("S1.3 carriers lost under 2%",
          (3582 - sum(1 for v in pre.values() if v is not None)) / 3582 < 0.02,
          f"{3582 - sum(1 for v in pre.values() if v is not None)} of 3,582")
    check("S1.4 Spearman(S0,S1) in [0.85,0.98]",
          0.85 <= s0["spearman"]["S0_shipped->S1_shrink"]["rho"] <= 0.98,
          str(s0["spearman"]["S0_shipped->S1_shrink"]["rho"]))
    check("S1.2 Kreiling is not the site max",
          now.get("harrison_kreiling", 0) < mx,
          f"Kreiling {now.get('harrison_kreiling')} vs max {mx}")

    print("\nOVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
