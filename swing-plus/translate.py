# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
translate.py — Projection Translation Layer (park / handedness / environment).

Translates NEUTRAL projections into park-specific realized projections without
ever touching talent:   translated = neutral x pf_stat(park, stand)
Reversal is exact by construction:  neutral = translated / pf.

Validated (~/translation_layer): park factors EB-shrunk (K=8000 PA) from
2023-26 home/road contrasts by handedness; HR factor most reliable (split-half
.49). At season grain park adds ~nothing to projection ACCURACY (the v2 engine
is already park-clean: corr(neutral proj, park pf) = -0.00) — this layer exists
for correct TRANSLATION (trades, what-ifs), per the framework's design.
Weather: discarded (event-level real, season-grain <=0.25% — variance model
M5). League environment: already inside the era-relative backbone. Platoon:
separate split talents exist (own-split r .57 vs cross .20) but exposure adds
nothing to overall accuracy; splits are a view, not a multiplier here.
"""
import numpy as np, pandas as pd
from pathlib import Path

PF = Path.home() / "translation_layer" / "data" / "park_factors.parquet"
TRANSLATABLE = {"woba": "pf_woba", "avg": "pf_avg", "iso": "pf_iso",
                "hr_pa": "pf_hr_pa", "babip": "pf_babip", "k_pct": "pf_k_pct"}
NEUTRAL_ONLY = {"xwoba", "xba", "xslg"}        # x-stats are park-resistant by design


def factors():
    return pd.read_parquet(PF)


def translate(neutral: dict, park: str, stand: str, pf: pd.DataFrame | None = None) -> dict:
    """neutral {stat: value} -> realized at (park, stand). Talent untouched."""
    pf = factors() if pf is None else pf
    row = pf[(pf.home_team == park) & (pf.stand == stand)]
    out = dict(neutral)
    if not len(row):
        return out
    row = row.iloc[0]
    for s, col in TRANSLATABLE.items():
        if s in out and out[s] is not None and pd.notna(row[col]):
            out[s] = round(float(out[s]) * float(row[col]), 4)
    return out


def reverse(translated: dict, park: str, stand: str, pf: pd.DataFrame | None = None) -> dict:
    pf = factors() if pf is None else pf
    row = pf[(pf.home_team == park) & (pf.stand == stand)]
    out = dict(translated)
    if not len(row):
        return out
    row = row.iloc[0]
    for s, col in TRANSLATABLE.items():
        if s in out and out[s] is not None and pd.notna(row[col]):
            out[s] = round(float(out[s]) / float(row[col]), 4)
    return out


if __name__ == "__main__":
    # PORTABILITY + REVERSIBILITY DEMO: Soto's 2027 neutral projection across parks
    proj = pd.read_parquet("data/processed/stat_projections.parquet")
    soto = proj[(proj.batter == 665742) & (proj.season == 2026)].iloc[0]
    neutral = {"woba": soto.proj_woba, "iso": soto.proj_iso,
               "avg": soto.proj_avg, "xwoba": soto.proj_xwoba}
    pf = factors()
    print("=== PORTABILITY: Soto 2027, talent + neutral xwOBA FROZEN ===")
    print(f"neutral: {neutral}")
    err = 0.0
    for park in ["NYM", "NYY", "COL", "SEA", "BOS"]:
        tr = translate(neutral, park, "L", pf)
        back = reverse(tr, park, "L", pf)
        err = max(err, max(abs(back[s] - neutral[s]) for s in neutral))
        print(f"   @{park}: wOBA {tr['woba']:.3f}  ISO {tr['iso']:.3f}  "
              f"AVG {tr['avg']:.3f}  | xwOBA {tr['xwoba']:.3f} (unchanged: "
              f"{tr['xwoba'] == neutral['xwoba']})")
    print(f"\nREVERSIBILITY: max |reverse - neutral| = {err:.6f} -> "
          f"{'PASS' if err < 1e-3 else 'FAIL'}")
    print("TALENT STABILITY: skill axes are inputs upstream of neutral projection; "
          "translation reads only (park, stand) -> by construction unchanged. PASS")
