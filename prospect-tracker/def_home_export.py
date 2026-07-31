# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# ============================================================================
# RISK-CONTEXT DISPLAY ONLY. Never a grade, rank, or sort input.
#
# data/prospect_def_value.json is a deploy-excluded model internal
# (deploy/data_exclude.txt), so the prospx "Defensive home" chip needs this
# SMALL published sidecar. It never imports from efv_* / proj_* / fa_* /
# valuation code. The chip it feeds is risk context beside the grade,
# visibly separate from it, and touches no served number.
#
# Two row bases, flagged per record:
#   live_listed   - the existing artifact covers ONLY the eFV training
#                   cohort (mostly graduated; zero current top prospects),
#                   so rows for tracked ACTIVE hitters are computed with
#                   prospect_def_value.def_value(), the same pure
#                   migration-matrix function build() uses, over the
#                   CURRENT listed position + age + games shares + frame.
#                   No fit, no training - a deterministic lookup.
#   artifact_asof - pass-through rows from data/prospect_def_value.json for
#                   players outside the live set (as-of-decision vectors).
# ============================================================================
"""Defensive-home certainty sidecar: data/def_home.json.

Per premium-position hitter (listed C / SS / CF / 2B / 3B, OF read as CF
per the source model's own alias):
  p_hold        P(primary MLB home = the listed position) from the
                migration-matrix position-probability vector
  band          Likely stays / Split risk / Likely moves - tercile cuts of
                p_hold among SAME-listed-position prospects in the current
                artifact (n >= 30, else the global terciles); the cuts ship
                with each record so the tooltip can state them
  entropy_band  low / mid / high - global terciles of def_home_entropy
                (position-distribution uncertainty)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SRC_PATH = DATA / "prospect_def_value.json"
OUT_PATH = DATA / "def_home.json"
DB_PATH = ROOT / "prospects.db"

PREMIUM = ("C", "SS", "CF", "2B", "3B")
_ALIAS = {"OF": "CF"}          # the source model's own listed-pos alias
MIN_POS_N = 30                 # per-position tercile floor
BANDS = ("Likely moves", "Split risk", "Likely stays")


def _canon_primary(position: str | None) -> str | None:
    """Primary listed position -> chip position. Only raw C/SS/CF/2B/3B/OF
    qualify (no UT/IF stretches - a utility listing has no single home to
    hold)."""
    if not position:
        return None
    p = str(position).strip().upper().split("/")[0].strip()
    p = _ALIAS.get(p, p)
    return p if p in PREMIUM else None


def _terciles(vals: list[float]) -> tuple[float, float]:
    v = sorted(vals)
    n = len(v)
    return v[n // 3], v[(2 * n) // 3]


def run(persist: bool = True) -> dict:
    import prospect_def_value as pdv   # pure def_value() only; no build()

    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    today = date.today()
    with sqlite3.connect(DB_PATH) as con:
        live = con.execute(
            "SELECT player_key, position, birth_date FROM players "
            "WHERE COALESCE(is_pitcher, 0) = 0").fetchall()
        pos_by_key = dict(con.execute(
            "SELECT player_key, position FROM players "
            "WHERE COALESCE(is_pitcher, 0) = 0"))
        key2mlbam: dict[str, int] = {}
        for pk, pj in con.execute(
                "SELECT player_key, payload_json FROM statlines"):
            try:
                mid = (json.loads(pj) or {}).get("mlbam_id")
            except (TypeError, ValueError):
                continue
            if mid:
                key2mlbam[pk] = int(mid)

    ums = pdv._up_mid_share_map()
    frames = pdv.frame_map()

    rows, seen = [], set()
    for pk, position, bd in live:            # live tracked active hitters
        pos = _canon_primary(position)
        mid = key2mlbam.get(pk)
        if pos is None or not mid:
            continue
        age = None
        if bd:
            try:
                y, m, d = str(bd)[:10].split("-")
                age = (today - date(int(y), int(m), int(d))).days / 365.25
            except (TypeError, ValueError):
                pass
        vec = pdv.def_value(position, age, ums.get(pk),
                            (frames.get(pk) or {}).get("bmi"))
        p_hold, ent = vec.get(f"p_{pos}"), vec.get("def_home_entropy")
        if p_hold is None or ent is None:
            continue
        rows.append({"mlbam": str(mid), "player_key": pk,
                     "listed_pos": pos, "p_hold": float(p_hold),
                     "entropy": float(ent), "basis": "live_listed"})
        seen.add(str(mid))

    for mid, rec in src.items():             # as-of artifact pass-through
        if str(mid) in seen:
            continue
        pk = rec.get("player_key")
        pos = _canon_primary(pos_by_key.get(pk))
        if pos is None:
            continue
        p_hold = rec.get(f"p_{pos}")
        ent = rec.get("def_home_entropy")
        if p_hold is None or ent is None:
            continue
        rows.append({"mlbam": str(mid), "player_key": pk,
                     "listed_pos": pos, "p_hold": float(p_hold),
                     "entropy": float(ent), "basis": "artifact_asof"})

    ent_lo, ent_hi = _terciles([r["entropy"] for r in rows])
    global_cuts = _terciles([r["p_hold"] for r in rows])
    by_pos: dict[str, list] = {}
    for r in rows:
        by_pos.setdefault(r["listed_pos"], []).append(r["p_hold"])
    cuts = {pos: (_terciles(v) if len(v) >= MIN_POS_N else global_cuts)
            for pos, v in by_pos.items()}

    by_mlbam: dict[str, dict] = {}
    for r in rows:
        t_lo, t_hi = cuts[r["listed_pos"]]
        band = BANDS[2] if r["p_hold"] >= t_hi else (
            BANDS[1] if r["p_hold"] >= t_lo else BANDS[0])
        eb = "low" if r["entropy"] <= ent_lo else (
            "mid" if r["entropy"] <= ent_hi else "high")
        by_mlbam[r["mlbam"]] = {
            "player_key": r["player_key"],
            "listed_pos": r["listed_pos"],
            "p_hold": round(r["p_hold"], 3),
            "band": band,
            "t_lo": round(t_lo, 3), "t_hi": round(t_hi, 3),
            "entropy": round(r["entropy"], 4),
            "entropy_band": eb,
            "basis": r["basis"],
        }

    out = {
        "generated_at": date.today().isoformat(),
        "source": "data/prospect_def_value.json (deploy-excluded model "
                  "internal; this sidecar reshapes it, no model re-run)",
        "meta": {
            "contract": "risk-context display only; never a grade, rank, or "
                        "sort input anywhere on the site",
            "positions": list(PREMIUM),
            "band_rule": "tercile cuts of p_hold among same-listed-position "
                         "prospects in the current artifact (n >= 30, else "
                         "global terciles); cuts ship per record",
            "entropy_rule": "global terciles of def_home_entropy",
            "per_pos_cuts": {p: [round(c[0], 3), round(c[1], 3)]
                             for p, c in sorted(cuts.items())},
            "entropy_cuts": [round(ent_lo, 4), round(ent_hi, 4)],
            "n": len(by_mlbam),
            "n_by_basis": {
                b: sum(1 for v in by_mlbam.values() if v["basis"] == b)
                for b in ("live_listed", "artifact_asof")},
            "basis_note": "live_listed = current listed position + age + "
                          "games shares + frame through the model's pure "
                          "def_value() function (the training-cohort "
                          "artifact holds zero current prospects); "
                          "artifact_asof = as-of-decision pass-through",
        },
        "by_mlbam": {k: by_mlbam[k] for k in sorted(by_mlbam, key=int)},
        "key_to_mlbam": {v["player_key"]: int(k)
                         for k, v in by_mlbam.items() if v["player_key"]},
    }
    if persist:
        text = json.dumps(out, indent=0) + "\n"
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != text:
            OUT_PATH.write_text(text, encoding="utf-8")
            log.info("wrote %s (%d players)", OUT_PATH, len(by_mlbam))
        else:
            log.info("%s unchanged (%d players)", OUT_PATH, len(by_mlbam))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print(json.dumps(rep["meta"], indent=1))
