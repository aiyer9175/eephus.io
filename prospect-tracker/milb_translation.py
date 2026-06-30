# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MiLB -> first-MLB rate translation (K% / BB%).

Matched-pair regression-to-the-mean (the college_translation template) from a
prospect's final pre-debut level-relative MiLB rates (k_rel / bb_rel vs the level
mean) to his first MLB season's K% / BB%. Fit + leave-one-out validated on the
debuted cohort.

Signal (measured): K% translates with real signal (r2 ~ 0.35); BB% is modest
(r2 ~ 0.15, flagged); OPS / xwOBA do NOT translate across the MiLB->MLB jump
(r2 ~ 0.02), so they are DELIBERATELY not projected - the first-MLB production
level is dominated by selection + survivorship the rates do not carry. eFV is the
prospect->MLB signal for value; this is a descriptive rate translation only.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import college_translation as ct   # reuse _fit / _predict / _band

log = logging.getLogger(__name__)
DATA = Path(__file__).parent / "data"
OUT = DATA / "milb_translation.json"

MIN_MLB_GAMES = 40   # a fuller first season so K% / BB% stabilize


def _f(v):
    try:
        if isinstance(v, str) and v.startswith("."):
            return float("0" + v)
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_pairs() -> dict:
    """{'hit_k','hit_bb','pit_k','pit_bb': [(milb_rel, first_mlb_rate), ...]}."""
    milb = {}
    for f in ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json"):
        try:
            rows = json.loads((DATA / f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            if r.get("kind") == "debuted" and r.get("milb"):
                milb[r["player_key"]] = r["milb"]
    try:
        deb = json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    recs = deb if isinstance(deb, list) else (deb.get("players") or list(deb.values()))
    out = {"hit_k": [], "hit_bb": [], "pit_k": [], "pit_bb": []}
    for r in recs:
        pk = r.get("player_key")
        sl = r.get("statline") or {}
        mb = milb.get(pk)
        if not mb:
            continue
        g = _f(sl.get("games"))
        if g is None or g < MIN_MLB_GAMES:
            continue
        side = "pit" if sl.get("is_pitcher") else "hit"
        kp, bp = _f(sl.get("k_pct")), _f(sl.get("bb_pct"))
        if kp is not None and mb.get("k_rel") is not None:
            out[f"{side}_k"].append((mb["k_rel"], kp))
        if bp is not None and mb.get("bb_rel") is not None:
            out[f"{side}_bb"].append((mb["bb_rel"], bp))
    return out


def _loo(pairs: list) -> dict | None:
    """Leave-one-out MAE + P10-P90 coverage + r2, the honest test."""
    n = len(pairs)
    if n < 30:
        return None
    abs_err, inside = [], 0
    for i in range(n):
        train = pairs[:i] + pairs[i + 1:]
        fac = ct._fit([x for x, _ in train], [y for _, y in train])
        if not fac:
            continue
        x, y = pairs[i]
        pred = ct._predict(fac, x)
        abs_err.append(abs(y - pred))
        lo, hi = pred - 1.2816 * fac["band_sd"], pred + 1.2816 * fac["band_sd"]
        if lo <= y <= hi:
            inside += 1
    full = ct._fit([x for x, _ in pairs], [y for _, y in pairs])
    return {"mae": round(sum(abs_err) / len(abs_err), 3),
            "p10_p90_coverage": round(inside / len(abs_err), 3),
            "target_coverage": 0.80, "r2": full["r2"] if full else None, "n": n}


def _project_actives(fits: dict) -> dict:
    """Apply the fits to active prospects (live-matrix k_rel / bb_rel) -> per-player
    projected first-MLB K% / BB% with P10-P90 bands. Hitter rates only (the only side
    with a fit). BB% carries low_confidence when r2 is weak."""
    out: dict = {}
    try:
        import efv_score
    except ImportError:
        return out
    try:
        rows = json.loads(efv_score.live_matrix_path("hit").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for r in rows:
        mb = r.get("milb") or {}
        proj = {}
        if mb.get("k_rel") is not None and fits.get("hit_k"):
            f = fits["hit_k"]
            proj["k_pct"] = ct._band(ct._predict(f, mb["k_rel"]), f["band_sd"], 0, 60)
        if mb.get("bb_rel") is not None and fits.get("hit_bb"):
            f = fits["hit_bb"]
            b = ct._band(ct._predict(f, mb["bb_rel"]), f["band_sd"], 0, 30)
            b["low_confidence"] = f["r2"] < 0.25
            proj["bb_pct"] = b
        if proj and r.get("player_key"):
            out[r["player_key"]] = proj
    return out


def build(persist: bool = True) -> dict:
    pairs = _load_pairs()
    fits, validation = {}, {}
    for key in ("hit_k", "hit_bb", "pit_k", "pit_bb"):
        ps = pairs.get(key) or []
        fac = ct._fit([x for x, _ in ps], [y for _, y in ps])
        if fac:
            fits[key] = fac
            validation[key] = _loo(ps)
    # OPS / xwOBA: measured r2 ~ 0.02 across the MiLB->MLB jump - not projectable.
    out = {
        "generated_at": date.today().isoformat(),
        "min_mlb_games": MIN_MLB_GAMES,
        "note": ("MiLB final-season level-relative rate -> first-MLB rate. K% real "
                 "signal; BB% modest (flagged); OPS/xwOBA do not translate (not projected)."),
        "fits": fits,
        "validation": validation,
        "projections": _project_actives(fits),
    }
    if persist:
        OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s (%d fits)", OUT, len(fits))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    r = build()
    for k, f in r["fits"].items():
        v = r["validation"].get(k) or {}
        print(f"{k}: slope {f['slope']} r2 {f['r2']} n {f['n']} | LOO MAE {v.get('mae')} cov {v.get('p10_p90_coverage')}")
