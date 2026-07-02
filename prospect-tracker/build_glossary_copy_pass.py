# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time glossary copy pass (2026-07-01): closes audit item A3 plus F-03.

The Phase-1 ledger (docs/glossary-copy-audit.md) carried 24 open verdicts
(8 LIGHT / 3 REWRITE / 13 RESTRUCTURE). Twenty-two of them had already been
fixed at build time by build_glossary_data.py's DEFINITION_FIXES / LONG_FIXES /
RESTRUCTURE tables; the ledger was never reconciled. This script:

  1. VERIFIES those 22 fixes are still present in the live payload (hard
     asserts, so the ledger's PASS verdicts are machine-checked, not vibes);
  2. applies the two remaining real fixes:
     - stock_arrow: methodology now LEADS with the computation (the LIGHT
       diagnosis), instead of burying it behind the filter note;
     - breakout_indicator: the one REWRITE whose long was still a single
       147-word wall gets the same paragraph treatment as the 13 RESTRUCTURE
       entries (content unchanged, breaks added);
  3. marks PWR+ as a retired legacy alias of POW+ inside the pwr_plus entry
     (the alias list keeps it findable; the prose now says which name is
     canonical);
  4. re-stamps the payload via build_glossary_data.glossary_version(), the
     single source for the version stamp (F-03: no hand-set literals).

Idempotent: every mutation is guarded, so a re-run is a no-op apart from the
version stamp. Deterministic: no stochastic steps. data/glossary.json stays
the canonical payload; this script is kept for provenance like its siblings
(build_glossary_data.py, build_glossary_v2_update.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from build_glossary_data import glossary_version

PATH = Path(__file__).parent / "data" / "glossary.json"

# stock_arrow (LIGHT): lead with the computation. Same sentences, new order.
STOCK_OLD = ("Drives the 'Up' / 'Down' filter on the Active list. "
             "Stock reads as 'delta since the most recent prior update' - "
             "a player with only one update reads as 'flat'. "
             "Movements ≥ 1.5 grade-points show in the row's meta line.")
STOCK_NEW = ("Stock is the consensus-FV delta since the most recent prior "
             "update - a player with only one update reads as 'flat'. "
             "Drives the 'Up' / 'Down' filter on the Active list; movements "
             "≥ 1.5 grade-points show in the row's meta line.")

# breakout_indicator (REWRITE, restructure half): break the (a)/(b)/(c) wall
# into scannable paragraphs. Text content unchanged.
BREAKOUT_BREAKS = [
    ("): (a) ", "):\n\n(a) "),
    ("; (b) ", ";\n\n(b) "),
    ("; (c) ", ";\n\n(c) "),
    ("read as a prospect breakout). Tuned",
     "read as a prospect breakout).\n\nTuned"),
]

# pwr_plus: the retired label survives as a search alias only.
PWR_LEGACY_NOTE = ("PWR+ is the retired legacy label for this metric and "
                   "survives only as a search alias here; POW+ is the "
                   "canonical name on every surface.")

# Phrases the Phase-1 fixes removed. None may reappear (ledger closure is
# asserted, not assumed).
DEAD_PHRASES = [
    "Equally-weighted",            # tool (LIGHT)
    "published a published",       # upside_indicator (LIGHT)
    "Designed to surface",         # breakout_indicator (REWRITE)
    "Designed to mirror",          # sur_plus / OrgSur+ (LIGHT)
    "Note that a fair trade",      # trade (LIGHT)
    "Stock is computed as",        # stock_arrow (LIGHT)
]

# The 13 RESTRUCTURE slugs plus breakout_indicator must all render as
# multi-paragraph methodology (the frontend splits on blank lines).
MULTI_PARA = ["statcast_plus", "tiebreaker_score", "rps_plus",
              "tools_dvm_plus", "pwr_plus", "tvi", "wag", "farm_report_card",
              "farm_grade_acquisition_strategy", "farm_grade_financial",
              "farm_grade_mlb_production", "eta_half_season",
              "spotlight_age_cap", "breakout_indicator"]


def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in d["entries"]}

    # --- 1+2. the two remaining real fixes (guarded, idempotent) -----------
    e = by_id["stock_arrow"]
    if e.get("methodology") == STOCK_OLD:
        e["methodology"] = STOCK_NEW
        print("stock_arrow: methodology now leads with the computation")
    assert "Stock is computed as" not in (e.get("methodology") or "")

    e = by_id["breakout_indicator"]
    m = e.get("methodology") or ""
    if "\n\n" not in m:
        for old, new in BREAKOUT_BREAKS:
            assert old in m, f"breakout_indicator drifted; expected {old!r}"
            m = m.replace(old, new)
        e["methodology"] = m
        print("breakout_indicator: methodology wall broken into paragraphs")

    # --- 3. PWR+ legacy-alias note -----------------------------------------
    e = by_id["pwr_plus"]
    assert "PWR+" in e.get("aliases", []), "pwr_plus lost its PWR+ alias"
    if "retired legacy label" not in (e.get("methodology") or ""):
        e["methodology"] = (e.get("methodology") or "").rstrip() + \
            "\n\n" + PWR_LEGACY_NOTE
        print("pwr_plus: PWR+ marked as a retired legacy alias of POW+")

    # --- verify the 22 already-landed Phase-1 fixes -------------------------
    blob = json.dumps(d, ensure_ascii=False)
    for phrase in DEAD_PHRASES:
        assert phrase not in blob, f"Phase-1 fix regressed: {phrase!r}"
    for slug in MULTI_PARA:
        mm = by_id[slug].get("methodology") or ""
        assert "\n\n" in mm, f"{slug}: methodology is a single wall again"
    # spot definitions the LIGHT/REWRITE verdicts targeted
    assert "Unweighted power-mean (p=4)" in by_id["tool"]["definition"]
    assert "SIGNING club forfeits" in by_id["qualifying_offer"]["definition"]
    assert "20+ MLB innings pitched AND" in by_id["two_way_player"]["definition"]
    assert "bWAR" in by_id["war"]["definition"]
    assert "exclusive-negotiation" in by_id["free_agency"]["definition"]
    assert "minimum" in by_id["il_10_15_60"]["definition"]
    assert "Mirrors the wRC+/OPS+ shape" in by_id["sur_plus"]["methodology"]
    assert "A fair trade" in by_id["trade"]["methodology"]

    # no em/en-dashes may enter the payload through this pass
    assert "—" not in blob and "–" not in blob

    # --- 4. single-sourced version stamp (F-03) -----------------------------
    d["version"] = glossary_version()
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"wrote {PATH} - {len(d['entries'])} entries, "
          f"version {d['version']}")


if __name__ == "__main__":
    main()
