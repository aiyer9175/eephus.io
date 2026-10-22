# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The label-only blast radius of the core eWAR label epoch, measured once
(docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 5).

    python tools/ewar_core_label_blast.py --write

LABELS ONLY: the list-vintage frame's development vintages 2011 to 2019, both sides,
with W3 and L6 from efv_labels.labels_for_frame on the stored career_war table (the
fWAR label) and on that table re-expressed on the core label and on the realized-core
sensitivity (war_source.row_on_provider). No grade, consensus FV, model output or FV
cell is read: the frame rows supply player_key and vintage and nothing else is used.
The reserved vintages and the 2025 and later debut cohorts stay behind the labels
module's own guards.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "efv-2026-10-22" / "ewar_core_label_blast.json"
W_STAR_DEV = 1.19      # the development contributor threshold on W3 (efv_v2_dev_read, labels only)


def _tables() -> dict:
    import war_source
    stored = war_source.career_war_table(provider="fwar")
    fw, core, real = {}, {}, {}
    for pk, row in stored.items():
        r_f = war_source.row_on_provider(row, "fwar")
        r_c = war_source.row_on_provider(row, "ewar_core")
        def _num(m):
            try:
                return {int(y): float(w) for y, w in (m or {}).items() if w is not None}
            except (TypeError, ValueError):
                return {}
        fw[pk] = _num(r_f.get("seasons"))
        core[pk] = _num(r_c.get("seasons"))
        real[pk] = _num(r_c.get("seasons_ewar_core_realized") or r_c.get("seasons"))
    return {"fwar": fw, "core": core, "realized_core": real}


def _stats(pairs: list[tuple[float, float]], contrib: bool) -> dict:
    n = len(pairs)
    if n < 3:
        return {"n": n}
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    d = [b - a for a, b in pairs]
    md = sum(d) / n
    sd = math.sqrt(sum((v - md) ** 2 for v in d) / (n - 1))
    out = {"n": n, "pearson_r": (sxy / math.sqrt(sxx * syy)) if sxx > 0 and syy > 0 else None,
           "mean_change": md, "sd_change": sd,
           "rows_changed": sum(1 for v in d if abs(v) >= 0.005),
           "rows_move_0_5": sum(1 for v in d if abs(v) >= 0.5),
           "rows_move_1_0": sum(1 for v in d if abs(v) >= 1.0),
           "label_sd_fwar": math.sqrt(sxx / (n - 1))}
    if contrib:
        out["contributor_flags_changed"] = sum(1 for a, b in pairs if (a >= W_STAR_DEV) != (b >= W_STAR_DEV))
    return out


def build(log=print) -> dict:
    import efv_labels as L
    import efv_vintage_frame as F
    universe = F.load_universe()
    tabs = _tables()
    out: dict = {}
    for side in F.SIDES:
        rows = []
        for v in F.DEV_VINTAGES:
            rows += [{"player_key": r["player_key"], "vintage": r["vintage"]}
                     for r in F.build_frame(side, v, universe=universe, milb=False, sidecars=False)]
        labs = {k: L.labels_for_frame(rows, universe=universe, war=t) for k, t in tabs.items()}
        blk = {"frame_rows": len(rows)}
        for alt in ("core", "realized_core"):
            for lab in ("w3", "l6"):
                pairs = [(a[lab], b[lab]) for a, b in zip(labs["fwar"], labs[alt])
                         if a[lab] is not None and b[lab] is not None]
                blk[f"{alt}:{lab}"] = _stats(pairs, contrib=(lab == "w3"))
        out[side] = blk
        log(f"  {side}: {len(rows)} frame rows; core W3 {blk['core:w3']}")
    import ewar_core_label
    return {"schema": 1, "registration": "docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 5",
            "label_vintage_id": ewar_core_label.vintage_id(),
            "built_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
            "vintages": list(F.DEV_VINTAGES), "w_star_dev": W_STAR_DEV,
            "field_key": ("per side and '<label>:<w3|l6>': rows resolved on both labels, Pearson r with the "
                          "fWAR label, mean and sd of (label - fWAR label), rows changed by 0.005 or more, "
                          "rows moving 0.5 and 1.0 WAR or more, the fWAR label's sd, and W3 contributor "
                          "flags at w* that change; labels only, no grade read"),
            "sides": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if a.write and OUT.exists():
        print(f"REFUSED: {OUT} exists; measured once")
        return 2
    rec = build()
    print(json.dumps(rec["sides"], indent=1))
    if a.write:
        OUT.write_text(json.dumps(rec, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
