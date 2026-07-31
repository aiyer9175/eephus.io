"""DIAGNOSTIC (throwaway): horizon/latency tradeoff for the pitcher label instrument.

(a) run_gate with a univariate isotonic (window WAR -> true6) at span=3,4,5.
(b) production censoring census: observable spans for debut years 2021-2024.
No shipped file is touched. Read-only.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.isotonic import IsotonicRegression  # noqa: E402

import tools.efv_pitcher_label_harness as H  # noqa: E402

DATA = ROOT / "data"


# ---------------------------------------------------------------------------
# (a) univariate isotonic candidate
# ---------------------------------------------------------------------------
def make_iso(span):
    def fit(train_rows):
        x = [H.window(r, span)["war"] for r in train_rows]
        y = [r["true6"] for r in train_rows]
        iso = IsotonicRegression(out_of_bounds="clip", increasing=True)
        iso.fit(x, y)
        return iso

    def predict(state, rec, sp):
        return float(state.predict([H.window(rec, sp)["war"]])[0])

    return fit, predict


def part_a():
    results = {}
    for span in (3, 4, 5):
        print("=" * 78)
        print(f"### SPAN = {span}")
        fit, pred = make_iso(span)
        out = H.run_gate({"ISO_war_univariate": (fit, pred)}, span=span, side="pit")
        results[span] = out
    print("=" * 78)
    print("\nSUMMARY: % of oracle headroom captured by univariate isotonic")
    print(f"{'span':>5} {'KM_blend':>9} {'iso_blend':>10} {'oracle':>9} {'headroom':>9} {'gain':>8} {'pct':>7}")
    for span, out in results.items():
        km = out["model"]["A_KM_baseline"]["blend"]["spearman"]
        iso = out["model"]["ISO_war_univariate"]["blend"]["spearman"]
        orc = out["model"]["C_oracle"]["blend"]["spearman"]
        hr = orc - km
        gain = iso - km
        pct = (gain / hr * 100) if hr else float("nan")
        print(f"{span:>5} {km:>9.4f} {iso:>10.4f} {orc:>9.4f} {hr:>9.4f} {gain:>+8.4f} {pct:>6.1f}%")
        # label fidelity too
    print("\nLABEL FIDELITY by span (mid cohorts vs TRUE 6yr WAR)")
    print(f"{'span':>5} {'KM_rho':>8} {'KM_mae':>8} {'iso_rho':>8} {'iso_mae':>8}")
    for span, out in results.items():
        lf = out["label_fidelity"]
        print(f"{span:>5} {lf['KM_baseline']['spearman']:>8.4f} {lf['KM_baseline']['mae']:>8.3f} "
              f"{lf['ISO_war_univariate']['spearman']:>8.4f} {lf['ISO_war_univariate']['mae']:>8.3f}")
    return results


# ---------------------------------------------------------------------------
# (b) production censoring census
# ---------------------------------------------------------------------------
def part_b():
    rows = json.loads((DATA / "xfv_pitcher_matrix.json").read_text(encoding="utf-8"))
    cw = H._career_war()
    ov = H._overrides()
    midx = H._mlb_pitch_index()

    cens = [r for r in rows if r.get("censored") and r.get("kind") == "debuted"]
    print("\n" + "=" * 78)
    print(f"### PRODUCTION CENSORED PITCHER ROWS  n={len(cens)}")
    print(f"(total pitcher matrix rows = {len(rows)}; resolved debuted pool = "
          f"{sum(1 for r in rows if r['kind']=='debuted' and not r.get('censored'))})")

    by_dy = defaultdict(list)
    for r in cens:
        by_dy[r.get("debut_year")].append(r)

    print("\nA) NOMINAL observable span (matrix `observed_seasons`), per debut year")
    print(f"{'debut_yr':>9} {'n':>5}  observed_seasons distribution")
    for dy in sorted(by_dy):
        c = Counter(r.get("observed_seasons") for r in by_dy[dy])
        print(f"{dy:>9} {len(by_dy[dy]):>5}  {dict(sorted(c.items()))}")

    print("\nB) ACTUAL seasons WITH MLB pitching data in the window "
          "(nominal span; how many of those calendar seasons the arm actually appeared)")
    print(f"{'debut_yr':>9} {'n':>5} {'span':>5} {'mlbam%':>7}  seasons_pitched distribution   mean")
    for dy in sorted(by_dy):
        grp = by_dy[dy]
        span = 2025 - dy + 1
        have_id = 0
        dist = Counter()
        vals = []
        for r in grp:
            pk = r["player_key"]
            mid_ = r.get("mlbam_id") or ov.get(pk)
            if mid_:
                have_id += 1
            lines = midx.get(int(mid_), {}) if mid_ else {}
            seen = sum(1 for i in range(span) if lines.get(dy + i))
            dist[seen] += 1
            vals.append(seen)
        mean = sum(vals) / len(vals)
        print(f"{dy:>9} {len(grp):>5} {span:>5} {have_id/len(grp):>6.0%}  "
              f"{dict(sorted(dist.items()))}   {mean:.2f}")

    print("\nC) ACTUAL seasons with NON-ZERO career WAR recorded in the window")
    print(f"{'debut_yr':>9} {'n':>5} {'span':>5}  war-seasons distribution   mean_obs_war")
    for dy in sorted(by_dy):
        grp = by_dy[dy]
        span = 2025 - dy + 1
        dist = Counter()
        wsum = []
        for r in grp:
            sw = cw.get(r["player_key"]) or {}
            seen = sum(1 for i in range(span) if (dy + i) in sw)
            dist[seen] += 1
            wsum.append(sum(H._f(sw.get(dy + i)) for i in range(span)))
        print(f"{dy:>9} {len(grp):>5} {span:>5}  {dict(sorted(dist.items()))}   "
              f"{sum(wsum)/len(wsum):+.2f}")

    print("\nD) How many censored rows each span requirement would COVER "
          "(instrument needs >= span seasons of nominal observation)")
    tot = len(cens)
    for need in (2, 3, 4, 5):
        elig = [r for r in cens if (2025 - r["debut_year"] + 1) >= need]
        yrs = sorted({r["debut_year"] for r in elig})
        print(f"  span>={need}: {len(elig):>4}/{tot} rows ({len(elig)/tot:>5.1%})  debut years {yrs}")

    print("\nE) LATENCY: earliest calendar year a span-N instrument can label each cohort")
    for dy in sorted(by_dy):
        row = [f"span{n}->{dy+n-1} season resolves (label available {dy+n})" for n in (3, 4, 5)]
        print(f"  debut {dy} (n={len(by_dy[dy])}): " + " | ".join(row))


if __name__ == "__main__":
    part_a()
    part_b()
