# SCRATCH (not shipped): eFV -> WAR -> $ surplus chain diagnostics.
# STAGE A: deterministic structure of the served surplus (no refits, no sampling).
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf   # noqa: E402  (read-only)

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)


def load(side):
    f = "xfv_scored_pitcher.json" if side == "pit" else "xfv_scored.json"
    return json.loads((ROOT / "data" / f).read_text("utf-8"))


def spear(a, b):
    from scipy.stats import rankdata
    a = np.asarray(a, float); b = np.asarray(b, float)
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean(); rb = rb - rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else np.nan


def main():
    res = {}
    for side in ("hit", "pit"):
        rows = load(side)
        is_pit = side == "pit"
        d = [r for r in rows if r.get("surplus_mm") is not None]
        war = np.array([r["xfv_war_6yr"] for r in d])
        disp = np.array([r["xfv_grade_display"] for r in d])
        realg = np.array([r["xfv_grade"] for r in d])
        cons = np.array([r["consensus_fv"] for r in d])
        sm = np.array([r["surplus_mm"] for r in d])
        csm = np.array([r["consensus_surplus_mm"] if r.get("consensus_surplus_mm") is not None
                        else np.nan for r in d])
        rank_war = np.array([r["rank_war"] for r in d])

        # (1) what does the served $ actually track?
        res[f"{side}_rho_surplus_vs"] = {
            "display_grade": spear(sm, disp),
            "realized_grade(xfv_grade)": spear(sm, realg),
            "model_war(xfv_war_6yr)": spear(sm, war),
            "rank_war(blend)": spear(sm, rank_war),
            "consensus_fv": spear(sm, cons),
        }

        # (2) the grade round trip: model WAR vs the WAR the served grade implies
        implied = np.array([(vf.fv_to_6yr_avg_war(float(g)) or 0.0) * 6 for g in disp])
        implied_realg = np.array([(vf.fv_to_6yr_avg_war(float(g)) or 0.0) * 6 for g in realg])
        res[f"{side}_roundtrip"] = {
            "n": len(d),
            "model_war_mean": float(war.mean()),
            "implied_war_at_display_mean": float(implied.mean()),
            "implied_war_at_realized_grade_mean": float(implied_realg.mean()),
            "mean_abs_gap_display": float(np.abs(implied - war).mean()),
            "mean_gap_display(signed)": float((implied - war).mean()),
            "rho_implied_vs_model": spear(implied, war),
        }
        # by display tier
        tiers = [(0, 40), (40, 45), (45, 50), (50, 55), (55, 60), (60, 100)]
        bt = []
        for lo, hi in tiers:
            m = (disp >= lo) & (disp < hi)
            if m.sum() < 5:
                continue
            bt.append({"tier": f"{lo}-{hi}", "n": int(m.sum()),
                       "model_war": round(float(war[m].mean()), 2),
                       "implied_war_at_display": round(float(implied[m].mean()), 2),
                       "gap": round(float((implied[m] - war[m]).mean()), 2),
                       "surplus_mm": round(float(sm[m].mean()), 1)})
        res[f"{side}_roundtrip_by_tier"] = bt

        # (3) total board dollars: eFV display vs each player's own consensus FV
        ok = ~np.isnan(csm)
        res[f"{side}_board_totals_musd"] = {
            "n": int(ok.sum()),
            "sum_efv_display": round(float(sm[ok].sum()), 1),
            "sum_consensus": round(float(csm[ok].sum()), 1),
            "ratio": round(float(sm[ok].sum() / csm[ok].sum()), 4) if csm[ok].sum() else None,
            "note": ("eFV display grades are a rank-preserving quantile map onto the pool's own "
                     "consensus-FV multiset, so the served grade DISTRIBUTION is the consensus "
                     "distribution by construction; only the pairing of player->grade differs."),
        }
        # grade multiset identity check
        res[f"{side}_display_multiset_vs_consensus"] = {
            "sorted_display_mean": round(float(np.sort(disp).mean()), 3),
            "sorted_consensus_mean": round(float(np.sort(cons).mean()), 3),
            "max_abs_diff_sorted": round(float(np.abs(np.sort(disp) - np.sort(cons)).max()), 3),
            "mean_abs_diff_sorted": round(float(np.abs(np.sort(disp) - np.sort(cons)).mean()), 4),
        }

        # (4) LEVEL-INVARIANCE: rescale the model's WAR level, keep its ranking.
        # Served display grade = f(order of rank_war, sorted consensus multiset).
        # Show that an arbitrary monotone level change with the SAME ranking gives
        # byte-identical served grades (=> identical dollars).
        target = np.sort(cons)
        order = np.argsort(rank_war, kind="stable")
        m = len(d)
        gr = np.empty(m)
        for pos_i, i in enumerate(order):
            p = pos_i / (m - 1) if m > 1 else 0.0
            pp = p * (m - 1)
            lo = int(pp); hi = min(m - 1, lo + 1); fr = pp - lo
            gr[i] = target[lo] * (1 - fr) + target[hi] * fr
        res[f"{side}_quantile_map_reproduction_max_err"] = round(
            float(np.abs(np.round(gr, 1) - disp).max()), 4)
        for k in (0.5, 2.0):
            gr2 = np.empty(m)
            order2 = np.argsort(rank_war * k, kind="stable")   # monotone, rank-identical
            for pos_i, i in enumerate(order2):
                p = pos_i / (m - 1) if m > 1 else 0.0
                pp = p * (m - 1)
                lo = int(pp); hi = min(m - 1, lo + 1); fr = pp - lo
                gr2[i] = target[lo] * (1 - fr) + target[hi] * fr
            res.setdefault(f"{side}_level_invariance", {})[f"scale_{k}_max_grade_move"] = round(
                float(np.abs(gr2 - gr).max()), 6)

    print(json.dumps(res, indent=1))
    (OUT / "_surplus_stageA.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
