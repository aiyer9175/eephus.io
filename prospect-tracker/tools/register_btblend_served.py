# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Move the registry for the BT Blend served-construction re-read
(docs/BAT_TRACKING_SERVED_GATE.md), one item per call, idempotently.

    python tools/register_btblend_served.py reread   notes on bat_tracking_hitters
    python tools/register_btblend_served.py flip     new row btblend_plus (only on a PASS)

Every number is read from data/bat_tracking_served_eval.json. A second call
changes nothing (a marker in the notes, or the row already present). Keeps the
file's CRLF line endings and one-space indent. Then: python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = "data/bat_tracking_served_eval.json"
MARK = "SERVED-CONSTRUCTION RE-READ (2026-10-14"


def _ci(c):
    return (f"mean {c['mean']:+.4f} lo95 {c['lo95']:+.4f} hi95 {c['hi95']:+.4f}"
            if c else "none")


def _read_registry():
    raw = REG.read_bytes()
    return json.loads(raw.decode("utf-8")), (b"\r\n" in raw)


def _write_registry(doc, crlf):
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))


def _art() -> dict:
    return json.loads((ROOT / ART).read_text(encoding="utf-8"))


def _result_text(a: dict) -> str:
    d4, d0 = a["ladder"]["D4"], a["ladder"]["D0_original_seed"]
    ds = a["disclosures"]
    xw, xh = ds["d4_vs_raw_xwoba_alone"], ds["d4_vs_served_xhem_plus_integer"]
    return (
        f"BT Blend served construction (D4, integers as served) rho "
        f"{d4['v1']['rho_primary']} vs served xHEM+ Blend {d4['v1']['rho_baseline']} on "
        f"{a['n_pairs']} pairs (arm B's pair set, folds 2024->2025 and 2025->2026), gap v1 "
        f"{_ci(d4['v1']['gap_ci'])} (MDE95 {d4['v1']['mde95_in_run']}), v2 "
        f"{_ci(d4['v2']['gap_ci'])} (MDE95 {d4['v2']['mde95_in_run']}); seed {a['seed']}, "
        f"{a['boot']} reps, k = 1. Verdict {a['decision']['verdict']}. D0 reproduced "
        f"data/bat_tracking_eval.json arm B exactly (v1 {_ci(d0['v1']['gap_ci'])}). "
        f"Disclosures, zero verdict weight: against raw xwOBA(Y) alone v1 "
        f"{_ci(xw['v1']['gap_ci'])}, v2 {_ci(xw['v2']['gap_ci'])}, so it does NOT separate "
        f"from xwOBA alone; against the served xHEM+ integer v1 {_ci(xh['v1']['gap_ci'])}. "
        f"The gate speaks only about the PA >= 200 subset while the board stamps PA >= 100.")


def reread(row: dict) -> bool:
    a = _art()
    if not a.get("owner_waived_early_read") or MARK in (row.get("notes") or ""):
        return False
    row["notes"] = (row.get("notes") or "") + (
        f" {MARK}; OWNER-WAIVED EARLY READ, owner answer NOV15-BT-ARMB = (a), "
        f"docs/BAT_TRACKING_SERVED_GATE.md, artifact {ART}): " + _result_text(a)
        + " This row keeps its verdict for the EVAL construction; the served column "
          "has its own row, btblend_plus, only if the re-read passed.")
    return True


def flip(rows: list, by_id: dict) -> bool:
    a = _art()
    if a["decision"]["verdict"] != "PASS" or "btblend_plus" in by_id:
        return False
    d4 = a["ladder"]["D4"]
    row = {
        "model_id": "btblend_plus",
        "summary": (f"BT Blend served construction: rho {d4['v1']['rho_primary']} vs served "
                    f"xHEM+ Blend {d4['v1']['rho_baseline']} (n {a['n_pairs']}, v1 lo95 "
                    f"{d4['v1']['gap_ci']['lo95']:+.4f}, v2 lo95 "
                    f"{d4['v2']['gap_ci']['lo95']:+.4f}); does not separate from xwOBA alone."),
        "surface": "/mlbstats/ Hitter Leaderboards, Skill view: the BT Blend column (btblend_plus)",
        "predicts": ("Next-season wOBA ranking of hitters with 100 or more Savant PA, from "
                     "xwOBA, the HEM+ core and a bat-tracking contact-quality composite"),
        "champion": ("btblend_plus = 0.595 z(est_woba) + 0.255 z(hem_plus_raw) + 0.15 z(BT "
                     "composite) over the served pool, mapped onto the HEM+ ruler (bat_tracking_blend.py)"),
        "baseline": "the served xHEM+ Blend (fwdhem_plus) on arm B's pair set",
        "metric": ("D4 (integers as served) paired bootstrap gap lo95 > 0 under BOTH v1 and v2, "
                   "seed 20261014, 2000 reps, k = 1"),
        "eval_artifact": ART,
        "verdict": "provisional",
        "notes": (f"{MARK}; OWNER-WAIVED EARLY READ, docs/BAT_TRACKING_SERVED_GATE.md): "
                  + _result_text(a) + " Provisional: two transition folds, small n, the "
                  "lab's own honesty clause; the next read needs the 2026 to 2027 fold "
                  "(complete after 2027-11-15) and its own document. The eval-construction "
                  "row is bat_tracking_hitters (data/bat_tracking_eval.json)."),
    }
    i = next(k for k, r in enumerate(rows) if r["model_id"] == "bat_tracking_hitters")
    rows.insert(i + 1, row)
    return True


def main(argv) -> int:
    if len(argv) != 1 or argv[0] not in ("reread", "flip"):
        print(__doc__)
        return 2
    doc, crlf = _read_registry()
    rows = doc["models"]
    by_id = {r["model_id"]: r for r in rows}
    changed = (reread(by_id["bat_tracking_hitters"]) if argv[0] == "reread"
               else flip(rows, by_id))
    if not changed:
        print(f"{argv[0]}: nothing written (already carried, or the artifact does not allow it)")
        return 0
    _write_registry(doc, crlf)
    sys.path.insert(0, str(ROOT))
    import model_registry
    problems = model_registry.validate(model_registry.load())
    print(f"{argv[0]}: registry written; validate -> {problems or 'clean'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
