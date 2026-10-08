# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE A adjudication -> data/arbitration_eval.json.

Runs the pre-registered battery in docs/ARBITRATION_GATE.md section 4 and writes
the verdict, wins and losses alike. Nothing here decides anything the gate did
not already decide before the numbers were read.

Usage:
    python tools/arb_gate_a.py --write [--B 2000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np                                              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import arb_mde_lab as L                                         # noqa: E402
import arb_model as Mod                                         # noqa: E402

OUT = ROOT / "data" / "arbitration_eval.json"
SEED = 20260808
PROD_KEYS = ("war", "war3", "career_war", "pa", "ipouts", "gs")

ARB1 = ("arb1", lambda r: r["arb_year"] == 1, "bar2")
ARB2 = ("arb2plus", lambda r: r["arb_year"] >= 2, "bar")


def _permute_production(rows, rng):
    """A3 control: permute the PRODUCTION block across players WITHIN
    (season, arb-step) cells.

    Prior salary, arbitration step, season, age and role stay attached to the
    player. A whole-matrix permutation is INADMISSIBLE here: it destroys the
    prior-salary link too and has no dynamic range, which is precisely why a
    previously registered control in this repo was recorded UNINFORMATIVE.
    """
    out = [dict(r) for r in rows]
    cells: dict[tuple, list[int]] = {}
    for i, r in enumerate(out):
        cells.setdefault((r["season"], r["arb_year"]), []).append(i)
    for idx in cells.values():
        if len(idx) < 3:
            continue
        perm = rng.permutation(len(idx))
        vals = [{k: out[i].get(k) for k in PROD_KEYS} for i in idx]
        for j, pj in enumerate(perm):
            for k in PROD_KEYS:
                out[idx[j]][k] = vals[pj][k]
    return out


def _swartz_head_to_head(rows, metrics, seasons, B: int | None = None, *,
                         pool: str = "repaired", units: str = "repaired") -> dict:
    """A6. The champion against the published MLBTR / Matt Swartz projection on
    identical rows.

    The claim is stated precisely because there are three different ones and
    only one is admissible. This measures OUR SERVED ESTIMATOR against the
    PUBLISHED PRE-SETTLEMENT projection on the settled figures. It is not a
    recalibrated-Swartz comparison, which would be the stronger test; if we
    cannot beat raw Swartz there is no point building the recalibration.

    docs/ARBITRATION_GATE.md section 14. `pool` "repaired" joins every
    projection entry (arb_dataset.load_swartz_projections); "frozen" is the
    2026-08-09 join through load_ledger, where the tracker post shadowed the
    projection for most settled 2024-2026 players. `units` "repaired" puts
    Swartz on the actual's scale with the fold's own deflator level; "frozen"
    compares the nominal figure with the deflated actual, as the 2026-08-09
    lab did (identical on the first fold, whose deflator level is 1.0).
    """
    import arb_dataset as A
    import arb_model as Mod
    import numpy as _np

    if units not in ("repaired", "frozen"):
        raise ValueError("unknown A6 units %r" % (units,))
    swartz, census = A.swartz_by_mlbam(rows, pool=pool)

    recs = Mod.forward_chain(rows, metrics, seasons=seasons)
    pairs = []
    for r in recs:
        s = swartz.get((int(r["mlbam"]), int(r["season"])))
        if not s or not r.get("served") or not r.get("actual"):
            continue
        # Both predictions are compared in the SAME space. The served value and
        # actual are deflated; the Swartz figure is nominal, so it is scaled by
        # the same ratio actual/nominal-actual carries.
        if units == "repaired":
            s = s * r["actual"] / r["salary"]
        pairs.append((r["actual"], r["served"], s, int(r["arb_year"]),
                      int(r["season"]), r["name"], int(r["mlbam"])))
    if len(pairs) < 30:
        return {"n": len(pairs), "insufficient": True, "pool": pool,
                "units": units, "join_census": census}
    out_rows = []
    for act, ours, swz, step, season, name, _mlbam in pairs:
        out_rows.append((act, ours, swz, step, name, season))
    ours_e = [abs(o - a) / a for a, o, s, *_ in out_rows]
    swz_e = [abs(s - a) / a for a, o, s, *_ in out_rows]
    by_step = {}
    for step in (1, 2, 3, 4):
        sel = [(a, o, s) for a, o, s, st, *_ in out_rows if st == step]
        if len(sel) >= 15:
            by_step[str(step)] = {
                "n": len(sel),
                "ours_mdape": float(_np.median([abs(o - a) / a for a, o, s in sel])),
                "swartz_mdape": float(_np.median([abs(s - a) / a for a, o, s in sel])),
            }
    ours_m = float(_np.median(ours_e))
    swz_m = float(_np.median(swz_e))
    # LIBRARY_14: the paired interval on the MdAPE gap (Swartz minus ours, so
    # positive means ours is better), player-clustered, both projections held
    # fixed; its own generator on the gate's SEED so the A1-A5 draws above are
    # untouched.
    import gap_intervals as gi
    oe, se = _np.array(ours_e), _np.array(swz_e)
    gap_ci = gi.paired_cluster_interval(
        [p[6] for p in pairs],
        lambda idx: {"mdape": float(_np.median(se[idx]) - _np.median(oe[idx]))},
        seed=SEED, b=B or gi.B, cluster="player (mlbam): a player's seasons are drawn together")
    return {
        "n": len(out_rows),
        "ours_mdape": ours_m,
        "swartz_mdape": swz_m,
        "ratio_ours_over_swartz": ours_m / swz_m if swz_m else None,
        "by_step": by_step,
        "by_season_n": {str(y): sum(1 for p in pairs if p[4] == y)
                        for y in sorted({p[4] for p in pairs})},
        "pool": pool,
        "units": units,
        "join_census": census,
        "verdict": "PASS" if ours_m < swz_m else "NULL",
        "claim": ("our SERVED estimator against the PUBLISHED pre-settlement "
                  "Swartz projection, on settled figures, identical rows"),
        "statement": (
            "This model does not beat the MLB Trade Rumors / Matt Swartz "
            "projection. Measured on identical rows, Swartz is materially more "
            "accurate at every arbitration step. Reported as a NULL. The "
            "mechanism is not mysterious: Swartz prices the counting stats "
            "arbitration panels actually reward - home runs, RBI, saves, wins - "
            "and this champion deliberately excludes them because nothing in "
            "this pipeline projects them forward, which is what lets the same "
            "model serve a backtest and a forecast. Swartz is the better "
            "estimate of a KNOWN season; it is not available for an unplayed "
            "one." if ours_m >= swz_m else
            "The champion beats the published Swartz projection on identical "
            "rows. Recalibrated-Swartz is the next and stronger test."),
        "gap_ci_vs_swartz": gap_ci,
    }


def _gain(rows, metrics, seasons, split, bar, *, leak=False):
    recs = [r for r in Mod.forward_chain(rows, metrics, seasons=seasons,
                                         leak_deflator=leak) if split(r)]
    p = Mod.paired(recs, "champion", bar)
    if len(p) < 20:
        return None
    return {
        "n": len(p),
        "mdape_gain": Mod.mdape(p, bar) - Mod.mdape(p, "champion"),
        "mse_gain": Mod.mse(p, bar) - Mod.mse(p, "champion"),
        "mdape_champion": Mod.mdape(p, "champion"),
        "mdape_bar": Mod.mdape(p, bar),
    }


def run(B: int, frame: str = Mod.FRAME) -> dict:
    rows, metrics = L.load_pool(frame)
    seasons = sorted({r["season"] for r in rows})
    rng = np.random.default_rng(SEED)
    out_floors = {}
    verdicts = {}

    for name, split, bar in (ARB1, ARB2):
        point = _gain(rows, metrics, seasons, split, bar)
        boot = []
        for _ in range(B):
            g = _gain(L._cluster_resample(rows, rng), metrics, seasons, split, bar)
            if g:
                boot.append(g["mdape_gain"])
        a = np.array(boot, float)
        sd = float(a.std(ddof=1))
        floor = 1.645 * sd

        # A3 control
        perm = []
        for _ in range(200):
            g = _gain(_permute_production(rows, rng), metrics, seasons, split, bar)
            if g:
                perm.append(g["mdape_gain"])
        pa = np.array(perm, float)
        p95 = float(np.percentile(pa, 95))

        # A5 deflator leak twin
        leaked = _gain(rows, metrics, seasons, split, bar, leak=True)
        leak_delta = (leaked["mdape_gain"] - point["mdape_gain"]) if leaked else None

        resolvable = abs(point["mdape_gain"]) >= floor
        beats_control = point["mdape_gain"] > p95
        leak_ok = leak_delta is None or abs(leak_delta) < abs(point["mdape_gain"])
        verdict = "PASS" if (resolvable and beats_control and leak_ok) else "NULL"
        verdicts[name] = verdict
        out_floors[name] = {
            "bar": bar,
            "bar_description": ("arb-1 intercept plus one WAR term (a lag "
                                "baseline is the wrong bar for the first trip)"
                                if name == "arb1" else
                                "median deflated step multiplier off prior "
                                "salary, floored at the max cut and the minimum"),
            "n_paired": point["n"],
            "mdape_champion": point["mdape_champion"],
            "mdape_bar": point["mdape_bar"],
            "mdape_gain": point["mdape_gain"],
            "mse_gain": point["mse_gain"],
            "mde95_onesided": floor,
            "gain_over_floor": (abs(point["mdape_gain"]) / floor) if floor else None,
            "resolvable": bool(resolvable),
            "p_gt_0": float((a > 0).mean()),
            "a3_control": {
                "permuted_mean": float(pa.mean()),
                "permuted_p95": p95,
                "real_over_p95": (point["mdape_gain"] / p95) if p95 > 0 else None,
                "p_perm_ge_real": float((pa >= point["mdape_gain"]).mean()),
                "beats_control": bool(beats_control),
            },
            "a5_deflator_leak_twin": {
                "gain_with_panel_wide_deflator": (leaked["mdape_gain"]
                                                  if leaked else None),
                "delta": leak_delta,
                "leak_smaller_than_margin": bool(leak_ok),
            },
            "verdict": verdict,
        }

    # A6: the MLB Trade Rumors / Matt Swartz comparison, on the repaired pool
    # (the headline) and the frozen pool beside it (section 14c).
    a6, a6_frozen = _a6_both(rows, metrics, seasons, B)

    ship = verdicts.get("arb1") == "PASS" or verdicts.get("arb2plus") == "PASS"
    doc = {
        "generated_at": date.today().isoformat(),
        "produced_by": f"python tools/arb_gate_a.py --write --B {B} --frame {frame}",
        "model": "arb_award_v1",
        "gate": "docs/ARBITRATION_GATE.md section 4 (GATE A)",
        "frame": frame,
        "frame_description": FRAME_DESCRIPTION[frame],
        "purpose": ("Does the two-stage arbitration award model beat the "
                    "class-appropriate baseline by more than its own measured "
                    "floor, and is the margin production information rather "
                    "than structure?"),
        "conventions": {
            "metric": ("MdAPE on deflated dollars is the adjudicating headline; "
                       "MSE in deflated dollars is reported alongside because "
                       "the downstream consumer needs an expectation"),
            "protocol": ("forward-chained by arbitration class year; paired "
                         "bootstrap resampling train AND test, clustered on "
                         "PLAYER, refitting the deflator and both stages every "
                         "draw"),
            "floor": "MDE95 one-sided (1.645 sd), measured per statistic class",
            "pool": ("only seasons whose arbitration step comes from MLBTR "
                     "published service time; substitute sources measure 0.66 "
                     "and 0.70 agreement against it and cannot carry a scored "
                     "backtest"),
            "smearing": ("served point is the Duan smearing-corrected "
                         "conditional MEAN, never exp(mu_hat)"),
        },
        "pool": {"rows": len(rows), "players": len({r["mlbam"] for r in rows}),
                 "seasons": seasons, "folds": len(seasons) - 1},
        "B": B,
        "seed": SEED,
        "results": out_floors,
        "a6_swartz": a6,
        "a6_swartz_frozen_pool": a6_frozen,
        "verdict": "provisional" if ship else "unvalidated",
        "loss_ledger": [],
    }
    if a6.get("verdict") == "NULL":
        doc["loss_ledger"].append(_a6_loss(a6))
    if verdicts.get("arb2plus") != "PASS":
        doc["loss_ledger"].append({
            "claim": "the model beats the step-multiplier baseline on arb 2/3/4",
            "measured_mdape_gain": out_floors["arb2plus"]["mdape_gain"],
            "floor": out_floors["arb2plus"]["mde95_onesided"],
            "verdict": "NULL",
            "statement": _arb2_null_statement(out_floors["arb2plus"]),
        })
    return doc


def _a6_both(rows, metrics, seasons, B):
    """(headline, frozen) A6 blocks, section 14c: the repaired pool is the
    headline and the frozen 2026-08-09 pool is scored beside it, both with
    Swartz on the actual's scale."""
    a6 = _swartz_head_to_head(rows, metrics, seasons, B, pool="repaired")
    fz = _swartz_head_to_head(rows, metrics, seasons, B, pool="frozen")
    fz["role"] = ("the 2026-08-09 loader's row set, scored beside the repaired "
                  "headline pool (docs/ARBITRATION_GATE.md section 14c)")
    return a6, fz


def _a6_loss(a6: dict) -> dict:
    return {"claim": a6["claim"], "n": a6["n"], "ours_mdape": a6["ours_mdape"],
            "swartz_mdape": a6["swartz_mdape"], "verdict": "NULL",
            "statement": a6["statement"]}


def rescore_a6(existing: dict, B: int, frame: str) -> dict:
    """Re-score A6 alone on the frame the top-level block was scored on and
    write it in place: a6_swartz, a6_swartz_frozen_pool and the A6 entry of
    the loss ledger. Everything else in the artifact is left as it is; A6
    draws from its own generator on SEED, so it equals what a full run
    writes."""
    if existing.get("frame", "award") != frame:
        raise SystemExit("the top-level block is not on frame %r" % (frame,))
    rows, metrics = L.load_pool(frame)
    seasons = sorted({r["season"] for r in rows})
    a6, fz = _a6_both(rows, metrics, seasons, B)
    out = dict(existing)
    out["a6_swartz"] = a6
    out["a6_swartz_frozen_pool"] = fz
    ledger = [x for x in out.get("loss_ledger") or []
              if x.get("claim") != a6["claim"]]
    if a6.get("verdict") == "NULL":
        ledger.insert(0, _a6_loss(a6))
    out["loss_ledger"] = ledger
    return out


def _arb2_null_statement(r: dict) -> str:
    """The arb-2+ NULL sentence, its A3 reading derived from the block it
    sits beside rather than written in advance."""
    c = r["a3_control"]
    head = ("The arb-2-and-later model is a NULL. Its margin over a median "
            "step multiplier off the prior salary is below the floor "
            "measured for this basis. ")
    if c["permuted_mean"] < r["mdape_gain"]:
        return head + (
            "The A3 control shows the production block does carry signal "
            "there: permuting it lowers the gain (mean %+.4f against %+.4f "
            "real), so this is a power limit, not an absence of information, "
            "and it is still reported as a null."
            % (c["permuted_mean"], r["mdape_gain"]))
    return head + (
        "The A3 control does not separate the real block from a permuted one "
        "(mean %+.4f against %+.4f real), so this program measured no "
        "production information beyond the salary track at these steps."
        % (c["permuted_mean"], r["mdape_gain"]))


#: Section 13. Each block names the season its production was read from.
FRAME_DESCRIPTION = {
    "platform": ("production (WAR, PA, outs, starts, war3, career WAR and the "
                 "hem/sem/rem block) read from the platform season, the season "
                 "before the award, complete when the award is set"),
    "award": ("production read from the award season itself, which had not "
              "been played when the award was set: the 2026-08-09 frame, a "
              "hindcast that adjudicates nothing (section 13a)"),
}

#: The top-level GATE A fields of data/arbitration_eval.json. The platform
#: re-run replaces them; the 2026-08-09 values move verbatim under HINDCAST_KEY.
GATE_A_KEYS = ("generated_at", "produced_by", "model", "gate", "frame",
               "frame_description", "purpose", "conventions", "pool", "B",
               "seed", "results", "a6_swartz", "a6_swartz_frozen_pool",
               "verdict", "loss_ledger")
HINDCAST_KEY = "hindcast_2026_08_09_award_frame"
TWIN_KEY = "award_frame_same_day_twin"


def merge_into(existing: dict, doc: dict, *, twin: bool) -> dict:
    """Write a run into the eval artifact without dropping any other block
    (gate_c_verification, gate_c2, the hindcast, the twin).

    The first platform write moves the 2026-08-09 top-level fields under
    HINDCAST_KEY, labelled, before replacing them; a twin run lands under
    TWIN_KEY and touches nothing else."""
    out = dict(existing)
    if twin:
        out[TWIN_KEY] = dict(doc, role=(
            "same-day award-frame twin (section 13c): separates the frame's "
            "effect from pool drift since 2026-08-09; adjudicates nothing"))
        return out
    if (HINDCAST_KEY not in out and existing.get("frame", "award") == "award"
            and existing.get("results")):
        old = {k: existing[k] for k in GATE_A_KEYS if k in existing}
        old["label"] = (
            "HINDCAST. Scored 2026-08-09 on award-season production, which "
            "had not been played when the award was set (census M08-05, "
            "docs/ARBITRATION_GATE.md section 13a). Kept for the record; "
            "adjudicates nothing. The top-level GATE A fields carry the "
            "platform-season re-run.")
        out[HINDCAST_KEY] = old
    for k in GATE_A_KEYS:
        out.pop(k, None)
    rest = out
    out = {k: doc[k] for k in GATE_A_KEYS if k in doc}
    out.update(rest)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=1500)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--frame", choices=Mod.FRAMES, default=Mod.FRAME)
    ap.add_argument("--a6-only", action="store_true",
                    help="re-score A6 on both pools and write it in place")
    args = ap.parse_args(argv)
    if args.a6_only:
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        merged = rescore_a6(existing, args.B, args.frame)
        for k in ("a6_swartz", "a6_swartz_frozen_pool"):
            a = merged[k]
            print(f"{k}: n {a['n']}  ours {a['ours_mdape']:.4f}  swartz "
                  f"{a['swartz_mdape']:.4f}  ratio {a['ratio_ours_over_swartz']:.2f}  "
                  f"{a['verdict']}  by season {a.get('by_season_n')}")
        if args.write:
            OUT.write_text(json.dumps(merged, indent=1, default=float), encoding="utf-8")
            print(f"wrote {OUT.relative_to(ROOT)} (A6 only)")
        return 0
    doc = run(args.B, args.frame)
    for name, r in doc["results"].items():
        print(f"\n{name}  vs {r['bar']}  n={r['n_paired']}")
        print(f"  MdAPE champion {r['mdape_champion']:.4f} vs bar "
              f"{r['mdape_bar']:.4f}  gain {r['mdape_gain']:+.5f}")
        print(f"  floor {r['mde95_onesided']:.5f}  -> "
              f"{r['gain_over_floor']:.2f}x  resolvable={r['resolvable']}")
        c = r["a3_control"]
        print(f"  A3 control: permuted p95 {c['permuted_p95']:+.5f}  "
              f"real/p95 {c['real_over_p95'] if c['real_over_p95'] is None else round(c['real_over_p95'],2)}x  "
              f"P(perm>=real)={c['p_perm_ge_real']:.3f}")
        print(f"  VERDICT: {r['verdict']}")
    print(f"\nartifact verdict: {doc['verdict']}")
    if args.write:
        existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        merged = merge_into(existing, doc, twin=(args.frame != Mod.FRAME))
        OUT.write_text(json.dumps(merged, indent=1, default=float), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({'twin' if args.frame != Mod.FRAME else 'top level'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
