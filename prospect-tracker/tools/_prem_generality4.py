# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""GENERALITY LANE, PASS 4. Two things pass 3 leaves on the table.

(1) A BETTER-MOTIVATED FIX. Pass 3 killed "recenter the GRADE onto the stratum's realized
    outcome": harmful out of fold, 0/10 folds, worse than its own permuted twin. But the
    lead's item 3 does not actually claim the grade is wrong in level; it claims the
    PREMIUM OVER SCOUTS is wrong in this stratum (historical mean premium on the profile
    -6.05 FV, Bradfield +6.10). Premium is a DIFFERENCE, so it does not inherit the
    served-grade scale confound that ruined passes 1 and 2, and its stratum mean does not
    require inverting a censored WAR surface into FV units at all. So:

        score(i) = served(i) - [ premium(i) - mean_TRAIN_premium(stratum(i)) ] * shrink

    i.e. pull each player's disagreement with scouts back toward the disagreement the model
    historically ran on that profile. Tested out of fold exactly like pass 3.

(2) THE DESCRIPTIVE ANSWER THE OWNER CAN USE. Independent of any model of outcomes, how
    many live board rows actually match the complaint - old for level, at the high minors,
    hitting below the level median, and carrying a premium over scouts? That count needs no
    outcome surface and therefore survives every bias documented in pass 1 part (d).

Read-only apart from one eval artifact.
"""
from __future__ import annotations

import collections
import json
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
DATA = ROOT / "data"

from _prem_generality import build_cuts, load_side, rank_map, stratum  # noqa: E402
from _prem_generality3 import TEST_COHORTS, spearman  # noqa: E402

random.seed(20260725)
DROP_LEVELS = {"CPX"}
SHRINK_N = 12.0


def prem_offsets(train, permute=False):
    """mean premium (served - consensus) per stratum on TRAIN, shrunk to the global mean."""
    rows = [r for r in train if r["strat"] and r["strat"][0] not in DROP_LEVELS
            and r["served"] is not None and r["cons"] is not None]
    if not rows:
        return {}, 0.0
    labels = [r["strat"] for r in rows]
    if permute:
        labels = labels[:]
        random.shuffle(labels)
    g = st.mean(r["served"] - r["cons"] for r in rows)
    cells = collections.defaultdict(lambda: [0.0, 0.0])
    for r, s in zip(rows, labels):
        c = cells[s]
        c[0] += r["served"] - r["cons"]
        c[1] += 1.0
    return {s: (c[0] + SHRINK_N * g) / (c[1] + SHRINK_N) for s, c in cells.items()}, g


def run(rows_by_side, lam, only=None, permute=False, boot=False):
    ds, brs, crs = [], [], []
    for pit, rows in rows_by_side.items():
        for T in TEST_COHORTS:
            tr = [r for r in rows if (r["cohort"] or 0) < T]
            te = [r for r in rows if (r["cohort"] or 0) == T]
            if len(tr) < 60 or len(te) < 25:
                continue
            if boot:
                tr = [tr[random.randrange(len(tr))] for _ in range(len(tr))]
                te = [te[random.randrange(len(te))] for _ in range(len(te))]
            offs, g = prem_offsets(tr, permute=permute)
            b, c, y = [], [], []
            for r in te:
                if r["served"] is None or r["cons"] is None or r["y"] is None:
                    continue
                s = r["strat"]
                adj = 0.0
                if s and s[0] not in DROP_LEVELS and s in offs and (only is None or s in only):
                    prem = r["served"] - r["cons"]
                    adj = lam * (prem - offs[s])
                b.append(r["served"])
                c.append(r["served"] - adj)
                y.append(r["y"])
            if len(y) < 25:
                continue
            rb, rc = spearman(b, y), spearman(c, y)
            ds.append(rc - rb)
            brs.append(rb)
            crs.append(rc)
    return ds, brs, crs


def gate(rows, lam, name, only=None, B=600):
    d, br, cr = run(rows, lam, only=only)
    if not d:
        print(f"  {name}: no usable folds")
        return None
    bt = []
    for _ in range(B):
        dd, _b, _c = run(rows, lam, only=only, boot=True)
        if dd:
            bt.append(st.mean(dd))
    bt.sort()
    lo, hi = bt[int(0.025 * len(bt))], bt[int(0.975 * len(bt))]
    cd = []
    for _ in range(60):
        dd, _b, _c = run(rows, lam, only=only, permute=True)
        if dd:
            cd.append(st.mean(dd))
    cd.sort()
    m = st.mean(d)
    v = ("WIN" if lo > 0 and m > 0.017 else
         "HARMFUL" if hi < 0 else "MEASURED NULL")
    print(f"  {name:<46} delta {m:+.4f}  CI95 [{lo:+.4f},{hi:+.4f}]  "
          f"ctrl {st.mean(cd):+.4f}  folds {sum(1 for x in d if x > 0)}/{len(d)}  -> {v}")
    return {"name": name, "lam": lam, "delta": round(m, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "control": round(st.mean(cd), 4),
            "control_p95": round(cd[int(0.95 * len(cd))], 4),
            "folds_improved": sum(1 for x in d if x > 0), "n_folds": len(d),
            "base_rho": round(st.mean(br), 4), "cand_rho": round(st.mean(cr), 4),
            "verdict": v}


def main() -> int:
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    sh = {r["player_key"]: r for r in
          json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))}
    sp = {r["player_key"]: r for r in
          json.loads((DATA / "xfv_scored_pitcher.json").read_text(encoding="utf-8"))}
    res_h, act_h = load_side(False)
    res_p, act_p = load_side(True)
    cuts_h, cuts_p = build_cuts(res_h), build_cuts(res_p)

    def prep(res, cuts, sc):
        out = []
        for r in res:
            s = sc.get(r["key"], {})
            g, c = s.get("xfv_grade"), s.get("consensus_fv")
            out.append({"key": r["key"], "y": r["y"], "cohort": r["cohort"],
                        "served": float(g) if isinstance(g, (int, float)) else None,
                        "cons": float(c) if isinstance(c, (int, float)) else None,
                        "strat": stratum(r, cuts)})
        return out

    H = [r for r in prep(res_h, cuts_h, sh) if r["strat"] and r["strat"][0] not in DROP_LEVELS]
    P = [r for r in prep(res_p, cuts_p, sp) if r["strat"] and r["strat"][0] not in DROP_LEVELS]
    rows = {False: H, True: P}

    print("=" * 78)
    print("PASS 4a: recenter the PREMIUM OVER SCOUTS, not the grade")
    print("=" * 78)
    print(f"  served-framing resolved rows: {len(H)} hitters + {len(P)} pitchers")
    print("  lam = how far each player's disagreement with scouts is pulled back toward the")
    print("  disagreement the model historically ran on that stratum (1.0 = all the way).\n")
    out = {"premium_recenter": []}
    for lam in (0.25, 0.5, 1.0):
        r = gate(rows, lam, f"premium recenter, all strata, lam={lam}")
        if r:
            out["premium_recenter"].append(r)
    print()
    for name, sel in (("old-for-level only", lambda s: s[1] == "old"),
                      ("old + lowProd only", lambda s: s[1] == "old" and s[2] == "lowProd"),
                      ("AAA/old/lowProd only (the Bradfield cell)",
                       lambda s: s == ("AAA", "old", "lowProd"))):
        strata = {r["strat"] for rr in rows.values() for r in rr if sel(r["strat"])}
        r = gate(rows, 1.0, f"premium recenter, {name}, lam=1.0", only=strata)
        if r:
            out["premium_recenter"].append(r)

    # ---------------- 4b: descriptive class size, no outcome surface needed
    print("\n" + "=" * 78)
    print("PASS 4b: HOW BIG IS THE COMPLAINT'S CLASS ON THE LIVE BOARD?")
    print("=" * 78)
    print("No outcome model here, so none of the part-(d) biases touch these counts.")
    served = {k: v["xfv_grade"] for k, v in xfv.items()
              if v.get("kind") == "active" and isinstance(v.get("xfv_grade"), (int, float))}
    slot = rank_map(list(served.items()))
    cons = {k: v.get("consensus_fv") for k, v in xfv.items()}

    live = []
    for pit, act in ((False, act_h), (True, act_p)):
        for a in act:
            g = served.get(a["key"])
            c = cons.get(a["key"])
            if g is None:
                continue
            live.append({**a, "served": g, "cons": c, "slot": slot[a["key"]],
                         "prem": (g - c) if isinstance(c, (int, float)) else None})

    print(f"\n  live board rows {len(served)};  matched to a feature row: {len(live)}")

    def count(label, pred, universe=None):
        u = universe if universe is not None else live
        sel = [r for r in u if pred(r)]
        t100 = [r for r in sel if r["slot"] <= 100]
        t300 = [r for r in sel if r["slot"] <= 300]
        prem = [r["prem"] for r in sel if r["prem"] is not None]
        print(f"  {label:<52}{len(sel):>6}{len(t300):>7}{len(t100):>7}"
              f"{(st.mean(prem) if prem else float('nan')):>+9.2f}")
        return sel

    print(f"\n  {'class':<52}{'n':>6}{'top300':>7}{'top100':>7}{'meanPrem':>9}")
    hit = [r for r in live if not r["pit"]]
    count("all active hitters with a MiLB track record",
          lambda r: not r["pit"] and r["lv"], hit)
    aaa = count("hitters at Triple-A", lambda r: not r["pit"] and r["lv"] == "AAA", hit)
    old = count("hitters at Triple-A, milb age >= 23.5",
                lambda r: r["lv"] == "AAA" and (r["age"] or 0) >= 23.5, aaa)
    prof = count("  + below the level median (ops_rel < 0)  THE PROFILE",
                 lambda r: (r["prod"] or 0) < 0, old)
    count("  + carrying ANY premium over scouts (served > consensus)",
          lambda r: r["prem"] is not None and r["prem"] > 0, prof)
    count("  + premium >= +3 FV", lambda r: r["prem"] is not None and r["prem"] >= 3, prof)
    count("  + premium >= +6 FV  (Bradfield is +6.1)",
          lambda r: r["prem"] is not None and r["prem"] >= 6, prof)
    print()
    aa = count("hitters at Double-A, age >= 22.5, ops_rel < 0",
               lambda r: not r["pit"] and r["lv"] == "AA" and (r["age"] or 0) >= 22.5
               and (r["prod"] or 0) < 0, hit)
    count("  + premium >= +3 FV", lambda r: r["prem"] is not None and r["prem"] >= 3, aa)
    pit = [r for r in live if r["pit"]]
    pa = count("pitchers at Triple-A, age >= 23.5, below-median ERA-rel",
               lambda r: r["pit"] and r["lv"] == "AAA" and (r["age"] or 0) >= 23.5
               and (r["prod"] or 0) < 0, pit)
    count("  + premium >= +3 FV", lambda r: r["prem"] is not None and r["prem"] >= 3, pa)

    print("\n  THE PROFILE, enumerated (hitter / AAA / age >= 23.5 / ops_rel < 0):")
    print(f"  {'slot':>5}  {'player':<28}{'served':>7}{'cons':>7}{'prem':>7}"
          f"{'age':>6}{'opsRel':>8}")
    for r in sorted(prof, key=lambda r: r["slot"]):
        print(f"  {r['slot']:>5}  {r['key'][:27]:<28}{r['served']:>7.1f}"
              f"{(r['cons'] if r['cons'] is not None else float('nan')):>7.1f}"
              f"{(r['prem'] if r['prem'] is not None else float('nan')):>+7.1f}"
              f"{(r['age'] or 0):>6.0f}{(r['prod'] or 0):>+8.3f}")

    out["class_sizes"] = {
        "profile_n": len(prof),
        "profile_top300": sum(1 for r in prof if r["slot"] <= 300),
        "profile_top100": sum(1 for r in prof if r["slot"] <= 100),
        "profile": [{"key": r["key"], "slot": r["slot"], "served": round(r["served"], 2),
                     "consensus": r["cons"],
                     "premium": (round(r["prem"], 2) if r["prem"] is not None else None),
                     "age": r["age"], "ops_rel": r["prod"]}
                    for r in sorted(prof, key=lambda r: r["slot"])],
    }
    (DATA / "xfv_generality4_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_generality4_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
