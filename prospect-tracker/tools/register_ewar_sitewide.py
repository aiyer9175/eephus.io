# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR site-wide calibration's flip records
(docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md part 7, task EWAR_SITEWIDE_CALIBRATION):

  --part wag      glossary wag and warwag name eWAR as WAG's basis; the registry row wag
                  records the switch (storage.WAG_EWAR_HEADLINE) and its check (part 3.3).
  --part awards   glossary ewar_realized names the read on eWAR realized; the registry gains
                  the row awards_realized_read (provisional, measurement_only) and awards_selection
                  records the read beside the frozen selection (part 4).

Idempotent: a second run changes nothing. Keeps each file's line endings and one-space
indent; refuses when a plain round trip would rewrite either file. Then:

    python tools/register_ewar_sitewide.py --part wag
    python tools/register_ewar_sitewide.py --part awards
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
DOC = "docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md"

WAG_OLD = ("WAR basis: the training label, published fWAR, from the 2026-10 epoch (eWAR v2 from the "
           "2026-09 epoch, bWAR before it), the same currency as the FV-to-WAR anchors WAG is measured "
           "against. A position player's WAG is unchanged by the epoch; a pitcher's moves with his FIP "
           "re-pricing within role.")
WAG_NEW = ("WAR basis: eWAR, the series the card shows, from 2026-10-22 (published fWAR from the 2026-10 "
           "epoch, eWAR v2 from the 2026-09 epoch, bWAR before it). eWAR equals FanGraphs WAR in every "
           "season before 2026, so the FV-to-WAR anchors WAG is measured against are in the same currency; "
           "from 2026 it adds the ABS challenge part.")
WARWAG_OLD = "WAR basis: the training label, published fWAR, from the 2026-10 epoch."
WARWAG_NEW = "WAR basis: eWAR for both terms, the series the card shows."
REAL_OLD = "Shown beside eWAR on player pages and in Awards; it never sorts, ranks or sums anything there."
REAL_NEW = ("Shown beside eWAR on player pages and in Awards, where it also ranks a second read of the Awards "
            "rules: the same rules applied to eWAR realized, with a measurement band. It sorts and sums nothing "
            "else.")

WAG_TAG = "2026-10-22 EWAR_SITEWIDE_CALIBRATION:"
WAG_NOTE = (WAG_TAG + " the observed leg reads the headline eWAR (storage.WAG_EWAR_HEADLINE = True; owner "
            "EW3-18 and EW3-20; " + DOC + " part 3): the stored career_war total plus that row's headline "
            "departures from data/ewar_v3.json, which are zero before 2026. The expected leg, the exposure "
            "gate and the debuted value are unchanged. Part 3.3's accounting check (C-1 to C-3) held before "
            "the flip; no accuracy claim follows from the basis change.")
SEL_TAG = "2026-10-22 EWAR_SITEWIDE_CALIBRATION:"
SEL_NOTE = (SEL_TAG + " beside the frozen selection the page serves the same rules on eWAR realized "
            "(row awards_realized_read; " + DOC + " part 4); the selection, its freeze and the closed season "
            "files do not move.")


#: The band constants measured by the registered check (part 9, 2026-10-22), recorded in the
#: row's notes; the exporter recomputes them on every run into data/awards_eval.json.
BAND = {"bat": {"k": 0.000525, "n": 8592}, "pit": {"k": 0.003787, "n": 8221}}


def realized_read_row(band: dict | None = None) -> dict:
    b = band or BAND
    kb = (b.get("bat") or {}).get("k")
    kp = (b.get("pit") or {}).get("k")
    nums = (f" Band constants measured 2026-10-22: k_bat {kb:.6f} wins^2 per PA ({(b.get('bat') or {}).get('n'):,} player-seasons), "
            f"k_pit {kp:.6f} wins^2 per IP ({(b.get('pit') or {}).get('n'):,})." if kb and kp else "")
    return {
        "model_id": "awards_realized_read",
        "summary": ("Measured, not a forecast: the Awards rules applied to eWAR realized, each place with a "
                    "measurement band, and whether the first leads by more than the band."),
        "surface": "/awards/: the 'The rule on eWAR realized' panel on each MVP, Cy Young and Rookie card (2021 on)",
        "predicts": "nothing: who led each award on eWAR realized under the module's own floors and rookie test",
        "champion": ("awards_core.deserved_block (payload key realized_read): the rule's top 5 on eWAR "
                     "realized; band realized +/- 1.645 sigma, "
                     "sigma^2 = k_bat * PA + k_pit * IP, k = sum (fWAR - bWAR)^2 / (2 * sum exposure) over "
                     "player-seasons 2015 to 2025 without 2020; 'too close to call' when another place is within "
                     "1.645 * sqrt(sigma_1^2 + sigma_i^2) of the first"),
        "baseline": "n/a: descriptive; the frozen selection on the displayed series stands beside it",
        "metric": ("Accounting checks only (D-1 to D-4 of part 4.4): realized league totals reconcile with the "
                   "artifact, the pool equals the selection rule's, k is finite from at least 1,000 player-seasons, "
                   "closed season files byte-identical. The band is the disagreement between two published WAR "
                   "systems, not a confidence interval."),
        "eval_artifact": "data/awards_eval.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "owner": "Awards / HoF module",
        "notes": ("Registered in " + DOC + " part 4 (committed alone before any number; owner EW3-20 'the Awards "
                  "module shows who deserved each award on eWAR realized with its uncertainty band'; the page "
                  "words it neutrally under the module's copy rules). No rate or "
                  "count of writers' winners inside or outside the band is computed." + nums),
    }


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def _swap(entry: dict, old: str, new: str) -> bool:
    """Replace `old` by `new` once in the entry's text fields; True when it changed."""
    for k in ("definition", "methodology", "formula", "example"):
        v = entry.get(k)
        if isinstance(v, str) and old in v:
            entry[k] = v.replace(old, new, 1)
            return True
    return False


def glossary(part: str) -> bool:
    raw = GLOSSARY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        raise SystemExit("refusing: a plain round trip would rewrite glossary.json")
    ents = {e.get("id"): e for e in doc["entries"]}
    swaps = ([("wag", WAG_OLD, WAG_NEW), ("warwag", WARWAG_OLD, WARWAG_NEW)] if part == "wag"
             else [("ewar_realized", REAL_OLD, REAL_NEW)])
    changed = False
    for eid, old, new in swaps:
        e = ents.get(eid)
        if e is None:
            raise SystemExit(f"refusing: glossary entry {eid} is missing")
        text = json.dumps(e, ensure_ascii=False)
        if new in text:
            continue
        if not _swap(e, old, new):
            raise SystemExit(f"refusing: glossary entry {eid} no longer carries the sentence this script replaces")
        changed = True
    if changed:
        GLOSSARY.write_bytes(_render(raw, doc))
    return changed


def registry(part: str, band: dict | None) -> bool:
    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        raise SystemExit("refusing: a plain round trip would rewrite model_registry.json")
    models = doc["models"]
    cur = {m.get("model_id"): m for m in models}
    changed = False
    if part == "wag":
        row = cur.get("wag")
        if row is None:
            raise SystemExit("refusing: registry row wag is missing")
        if WAG_TAG not in str(row.get("notes") or ""):
            row["notes"] = (str(row.get("notes") or "") + " || " + WAG_NOTE).strip(" |")
            changed = True
    else:
        sel = cur.get("awards_selection")
        if sel is None:
            raise SystemExit("refusing: registry row awards_selection is missing")
        if SEL_TAG not in str(sel.get("notes") or ""):
            sel["notes"] = (str(sel.get("notes") or "") + " " + SEL_NOTE).strip()
            changed = True
        new = realized_read_row(band)
        if cur.get("awards_realized_read") != new:
            if "awards_realized_read" in cur:
                models[models.index(cur["awards_realized_read"])] = new
            else:
                models.insert(models.index(sel) + 1, new)
            changed = True
    if changed:
        REGISTRY.write_bytes(_render(raw, doc))
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--part", choices=("wag", "awards"), required=True)
    a = ap.parse_args(argv)
    band = None
    g = glossary(a.part)
    r = registry(a.part, band)
    print(f"glossary.json: {'wrote' if g else 'nothing to write'}; "
          f"model_registry.json: {'wrote' if r else 'nothing to write'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
