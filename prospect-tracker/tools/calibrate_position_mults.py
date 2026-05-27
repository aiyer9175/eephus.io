# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Compute position multipliers from cached Spotrac team-contract data.

Reads the cached spotrac_team_*.html files via spotrac.scrape_all_spotrac_contracts
(no network calls when cache is warm), groups player contracts by primary
position, and computes:

    multiplier(pos) = median_AAV(pos) / median_AAV(overall)

This gives a market-revealed "what does the FA / contract market pay
at each position" signal. We normalize against the OVERALL median
rather than SP because position scarcity should be measured against
the league baseline, not a single position.

Output: data/position_multipliers.json, consumed by value_framework.py
at runtime. To recompute, re-run this script after refreshing the
spotrac cache.

Usage:
    python tools/calibrate_position_mults.py [--force]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from spotrac import scrape_all_spotrac_contracts  # noqa: E402


# Spotrac's `position` field uses a controlled vocabulary. Map their
# codes to our framework's canonical keys (which match the keys used
# in value_framework._POSITION_MULT_DEFAULTS).
_SPOTRAC_POS_MAP = {
    "C":   "C",
    "1B":  "1B",
    "2B":  "2B",
    "3B":  "3B",
    "SS":  "SS",
    "LF":  "LF",
    "CF":  "CF",
    "RF":  "RF",
    "OF":  "OF",
    "DH":  "DH",
    "SP":  "SP",
    "RP":  "RP",
    "P":   "SP",    # Generic "P" -- treat as SP for grouping
    "RHP": "RHP",
    "LHP": "LHP",
    "TWP": "TWP",
}

# Players with AAV below this floor are dropped -- pre-arb / split-contract
# / non-roster invitees that would skew the position medians. $1M is the
# rough boundary between rookie-scale and meaningful contract.
_MIN_AAV_USD = 1_000_000


def _normalize_position(raw: str | None) -> str | None:
    if not raw:
        return None
    primary = raw.split("/")[0].strip().upper()
    return _SPOTRAC_POS_MAP.get(primary)


def calibrate(force: bool = False) -> dict:
    """Walk every team's contract data, group by position, compute the
    per-position median AAV, and normalize against the overall median.
    Returns a dict suitable for serialization."""
    rows = scrape_all_spotrac_contracts(force=force)
    if not rows:
        raise RuntimeError("calibrate: no Spotrac contracts loaded "
                           "(check .cache/spotrac_team_*.html)")
    by_pos: dict[str, list[int]] = {}
    overall: list[int] = []
    skipped_unmapped = 0
    skipped_low_aav = 0
    for r in rows:
        aav = r.get("aav_usd") or 0
        if aav < _MIN_AAV_USD:
            skipped_low_aav += 1
            continue
        pos = _normalize_position(r.get("position"))
        if pos is None:
            skipped_unmapped += 1
            continue
        by_pos.setdefault(pos, []).append(aav)
        overall.append(aav)

    if not overall:
        raise RuntimeError("calibrate: zero qualifying contracts after filters")

    overall_median = statistics.median(overall)

    mults: dict[str, float] = {}
    counts: dict[str, int] = {}
    medians: dict[str, int] = {}
    for pos, aavs in by_pos.items():
        if len(aavs) < 5:
            # Too few samples for a stable median (TWP often only Ohtani).
            continue
        med = statistics.median(aavs)
        mults[pos] = round(med / overall_median, 3)
        counts[pos] = len(aavs)
        medians[pos] = int(med)

    # Pitcher subcategories (RHP/LHP/MIRP/SIRP) often aren't directly
    # in Spotrac's vocabulary. Synthesize defensible defaults relative
    # to the calibrated SP/RP multipliers when missing.
    sp_mult = mults.get("SP") or 1.0
    rp_mult = mults.get("RP") or 0.55
    mults.setdefault("RHP",  sp_mult)
    mults.setdefault("LHP",  round(sp_mult * 1.04, 3))   # small lefty premium
    mults.setdefault("MIRP", round((sp_mult + rp_mult) / 2 * 1.10, 3))
    mults.setdefault("SIRP", round((sp_mult + rp_mult) / 2 * 0.95, 3))
    # TWP almost certainly under-sampled -- carry the Ohtani-driven prior.
    mults.setdefault("TWP",  round(max(sp_mult, mults.get("OF", 1.0)) * 1.15, 3))

    return {
        "version":         "v1.0",
        "anchor":          "median AAV / overall median AAV",
        "min_aav_filter":  _MIN_AAV_USD,
        "overall_median":  int(overall_median),
        "sample_total":    len(overall),
        "sample_unmapped": skipped_unmapped,
        "sample_low_aav":  skipped_low_aav,
        "sample_counts":   counts,
        "position_medians_usd": medians,
        "multipliers":     mults,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="Force re-scrape (bypass cache).")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path (default: data/position_multipliers.json)")
    args = ap.parse_args()
    out = args.out or (_ROOT / "data" / "position_multipliers_calibration_raw.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    result = calibrate(force=args.force)
    out.write_text(json.dumps(result, indent=2, sort_keys=True),
                   encoding="utf-8")
    print(f"wrote {out}")
    print("\nNOTE: this is a RESEARCH artifact, not the production override.")
    print("      value_framework.py uses reasoned defaults that filter out")
    print("      star-driven confounding (where positions like 3B/RF/DH get")
    print("      inflated by 1-3 superstars rather than true scarcity).")
    print("      To promote calibrated values into production, hand-curate")
    print("      a `data/position_multipliers.json` with a {multipliers: {...}}")
    print("      shape using the rows below as input.")
    print(f"\nSample: {result['sample_total']} qualifying contracts "
          f"(>${_MIN_AAV_USD/1e6:.1f}M AAV)")
    print(f"Overall median AAV: ${result['overall_median']/1e6:.2f}M")
    print(f"\nPer-position multipliers (sorted high to low):")
    for pos, m in sorted(result["multipliers"].items(),
                         key=lambda kv: -kv[1]):
        n = result["sample_counts"].get(pos, 0)
        med = result["position_medians_usd"].get(pos, 0)
        n_label = f"n={n}" if n else "synth"
        med_label = f"${med/1e6:>5.2f}M" if med else "  --   "
        print(f"  {pos:>5}: {m:>5.3f}   ({n_label:>6}, median {med_label})")


if __name__ == "__main__":
    main()
