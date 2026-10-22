# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline label check's label-only blast radius
(docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 5).

    python tools/ewar_headline_label_blast.py            # print
    python tools/ewar_headline_label_blast.py --write    # write the record

From the stored career_war table alone: per season, the rows whose eFV label value moves
under the switch (war_source.efv_label_seasons with EFV_LABEL_PROVIDER "ewar_headline"
against the table as stored), with the mean, standard deviation and largest absolute change;
and per player, the change in the summed label seasons. Reads no grade, consensus FV, model
output or FV cell, and splits no row by cohort or level.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECORD = ROOT / "docs" / "efv-2026-10-22" / "ewar_headline_label_blast.json"


def _summ(v: list[float]) -> dict:
    a = np.asarray(v, float)
    if not len(a):
        return {"n": 0, "mean": None, "sd": None, "max_abs": None, "n_abs_ge_0_1": 0, "n_abs_ge_0_5": 0}
    return {"n": int(len(a)), "mean": round(float(a.mean()), 4),
            "sd": round(float(a.std(ddof=1)), 4) if len(a) > 1 else 0.0,
            "max_abs": round(float(np.abs(a).max()), 4),
            "n_abs_ge_0_1": int(np.sum(np.abs(a) >= 0.1 - 1e-12)),
            "n_abs_ge_0_5": int(np.sum(np.abs(a) >= 0.5 - 1e-12))}


def measure(table: dict) -> dict:
    import ewar_headline_label as H
    by_season: dict[int, list[float]] = {}
    per_player: list[float] = []
    sources: dict[str, int] = {}
    rows_moved = 0
    for pk, row in table.items():
        row = row or {}
        sources[str(row.get("source") or "")] = sources.get(str(row.get("source") or ""), 0) + 1
        stored = row.get("seasons") or {}
        lab = H.label_series(row)
        moved = False
        tot = 0.0
        for y, v in stored.items():
            if v is None or lab.get(y) is None:
                continue
            d = float(lab[y]) - float(v)
            if d != 0.0:
                by_season.setdefault(int(y), []).append(d)
                moved = True
                tot += d
        if moved:
            rows_moved += 1
            per_player.append(tot)
    return {
        "rows": len(table), "rows_by_source": dict(sorted(sources.items())), "rows_moved": rows_moved,
        "seasons_moved": {str(s): _summ(v) for s, v in sorted(by_season.items())},
        "per_player_sum_change": _summ(per_player),
        "label_vintage_id": H.vintage_id(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    import storage
    import war_source
    table = war_source.career_war_table(provider=war_source.DEFAULT_PROVIDER)
    rec = measure(table)
    db = Path(storage.DB_PATH) if hasattr(storage, "DB_PATH") else None
    rec = {"generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
           "registration": "docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 5",
           "what": "label-only: stored career_war rows re-read on the headline label; no grade, FV or model",
           "db_sha256": hashlib.sha256(db.read_bytes()).hexdigest() if db and db.exists() else None,
           **rec}
    print(json.dumps(rec, indent=1))
    if a.write:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(rec, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"written {RECORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
