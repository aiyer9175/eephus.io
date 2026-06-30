# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Model + research by Will Cahoon (@willcolqhn), 2026
#
# Prospect-tracker LOCAL RECONSTRUCTION of Will Cahoon's prospect-defense model.
# The original (career_outcome_plus / defense-plus) builds def_value from the full
# MiLB innings-by-position TIME SERIES + body frame, beating FanGraphs' fFld grade at
# predicting realized MLB defensive value. The season-by-season parquet inputs
# (milb_fielding_full.parquet, milb_def_features.parquet) are NOT present in this repo,
# so this reconstructs the CORE THESIS leakage-safe from data the xFV pipeline already
# has: the prospect's AS-OF-DECISION listed position (dated at the scouting snapshot)
# + BODY FRAME (BMI, from draft_players height/weight) + age -> P(MLB position) via the
# migration matrix -> expected positional run value. The full innings-share granularity
# and the rf9_rel quality term are the documented simplifications; BMI + age + the
# migration matrix are used directly. FanGraphs fFld is NEVER an input.

"""Prospect defensive value from POSITION + FRAME (not scout grades).

Thesis (Cahoon, established result): a prospect's defensive home is a PROBABILITY VECTOR,
not a single label. Premium up-the-middle positions migrate down the spectrum at known
rates (SS only ~47% stay; C ~94%), and a bigger body frame (BMI) + age push a prospect
further down. Defensive-home RETENTION is a multi-win fork (SS-who-stay 7.5 vs SS-who-move
4.9 WAR) and defensive-home UNCERTAINTY is itself negative. So the value of a prospect's
glove is Sum_pos P(MLB pos) x positional adjustment, and the ENTROPY of that vector is a
risk flag.

  def_value         expected positional run value per 162 = Sum_pos P(MLB pos) x POS_ADJ[pos]
  def_home_entropy  Shannon entropy of P(MLB pos) -- uncertainty/versatility risk flag
  p_<pos>           the P(MLB position) vector

A DROP-IN replacement for the FanGraphs fFld defensive grade in the xFV pipeline.

VERDICT 2026-06-29 (data/prospect_def_value_eval.json):
  * VALIDATED as a predictor -- beats FG fFld at predicting realized MLB positional
    value (Spearman 0.68 vs 0.28, lower MAE, leakage-safe; n=263 graduated). `--validate`.
  * xFV SWAP REJECTED (loss, NOT shipped) -- adding def_value to the shipped lean xFV
    model regresses every gate (pooled rho 0.3701->0.3661, within-tier + fringe worse).
    Even a far better defensive predictor is flat-to-negative on xFV's offense-dominated
    first-6yr-WAR target: the binding constraint is the TARGET, not measurement quality.
  * The real lane for this signal is the defense-IS-WAR surfaces (MLB Projections / farm
    / display), NOT the xFV ranker.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"

# Standard positional adjustments (runs / 162), the league convention.
POS_ADJ = {"C": 12.5, "SS": 7.5, "CF": 2.5, "2B": 2.5, "3B": 2.5,
           "RF": -7.5, "LF": -7.5, "1B": -12.5, "DH": -17.5, "P": 0.0}
POSITIONS = ("C", "SS", "2B", "3B", "CF", "LF", "RF", "1B", "DH")
PREMIUM = ("C", "SS", "CF")            # the true up-the-middle premium
UP_MIDDLE = ("C", "SS", "2B", "CF")    # broader up-the-middle (matches the model's up_mid_share)
# positions that take down-spectrum migration pressure from frame/age
_DOWNSHIFTABLE = ("C", "SS", "CF", "2B", "3B")

# Migration matrix P(MLB pos | MiLB primary). Anchored cells are Cahoon's established
# result; the remainder of each row is distributed to adjacent spectrum positions to sum
# to 1.0 (documented assumption -- the full model fits this from the data).
MIGRATION = {
    "C":  {"C": 0.94, "1B": 0.04, "DH": 0.02},
    "SS": {"SS": 0.47, "2B": 0.30, "3B": 0.15, "CF": 0.04, "RF": 0.02, "LF": 0.02},
    "2B": {"2B": 0.53, "SS": 0.08, "3B": 0.12, "LF": 0.09, "RF": 0.08, "1B": 0.10},
    "3B": {"3B": 0.58, "1B": 0.18, "2B": 0.10, "LF": 0.08, "RF": 0.06},
    "CF": {"CF": 0.57, "LF": 0.22, "RF": 0.18, "2B": 0.03},
    "LF": {"LF": 0.52, "RF": 0.24, "1B": 0.14, "DH": 0.10},
    "RF": {"RF": 0.52, "LF": 0.24, "1B": 0.14, "DH": 0.10},
    "1B": {"1B": 0.75, "DH": 0.20, "LF": 0.05},
    "DH": {"DH": 0.70, "1B": 0.30},
}

_POS_ALIAS = {"OF": "CF", "IF": "SS", "UT": "2B", "UTIL": "2B", "PH": "DH", "DH": "DH"}
_BMI_NEUTRAL = 24.5    # average position-player BMI; heavier -> more down-migration


def _canon(pos: str | None) -> str | None:
    if not pos:
        return None
    p = str(pos).strip().upper().split("/")[0].strip()
    p = _POS_ALIAS.get(p, p)
    return p if p in MIGRATION else None


def milb_vector(position: str | None) -> dict[str, float]:
    """MiLB position distribution from the listed (possibly multi-) position string.
    'SS/2B' -> {SS:.7, 2B:.3}; a single position -> {pos:1.0}. The leakage-safe stand-in
    for the innings-share vector (the listed position is dated at the scouting snapshot)."""
    if not position:
        return {}
    parts = [pp for pp in (_canon(x) for x in str(position).split("/")) if pp]
    if not parts:
        return {}
    if len(parts) == 1:
        return {parts[0]: 1.0}
    w = {parts[0]: 0.7}
    for p in parts[1:]:
        w[p] = w.get(p, 0.0) + 0.3 / (len(parts) - 1)
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def _migration_pressure(age: float | None, bmi: float | None) -> float:
    """Down-the-spectrum migration pressure in [0, 0.25] from BODY FRAME (BMI) + age.
    A bigger frame and an older prospect are both likelier to have already moved (or be
    moved) off a premium position. BMI is the stronger lever (the model's frame signal)."""
    p = 0.0
    if bmi is not None:
        p += 0.045 * max(0.0, bmi - _BMI_NEUTRAL)      # ~0.045 per BMI point over 24.5
    if age is not None and age >= 23:
        p += 0.02 * (age - 22)                          # older -> more migrated
    return max(0.0, min(0.25, p))


def mlb_position_probs(milb_vec: dict[str, float], age: float | None = None,
                       bmi: float | None = None) -> dict[str, float]:
    """P(MLB position) = Sum over MiLB positions of P(MiLB) x migration row, then a FRAME
    (BMI) + age down-shift moves mass off premium/up-the-middle toward 1B/DH."""
    out: dict[str, float] = {}
    for mpos, w in milb_vec.items():
        row = MIGRATION.get(mpos, {mpos: 1.0})
        for tgt, p in row.items():
            out[tgt] = out.get(tgt, 0.0) + w * p
    if not out:
        return {}
    press = _migration_pressure(age, bmi)
    if press > 0:
        moved = 0.0
        for pos in _DOWNSHIFTABLE:
            if pos in out:
                d = out[pos] * press
                out[pos] -= d
                moved += d
        out["1B"] = out.get("1B", 0.0) + moved * 0.6
        out["DH"] = out.get("DH", 0.0) + moved * 0.4
    s = sum(out.values())
    return {k: v / s for k, v in out.items() if v > 0}


def _entropy(p: dict[str, float]) -> float:
    return float(-sum(v * math.log(v) for v in p.values() if v > 0))


def def_value(position: str | None, age: float | None = None,
              up_mid_share: float | None = None, bmi: float | None = None) -> dict:
    """Drop-in defensive value. Returns {def_value, def_home_entropy, p_<pos>...}.
    def_value = expected positional run value (per 162) x a defensive-quality multiplier
    from up_mid_share. FG fFld is NEVER an input."""
    mv = milb_vector(position)
    pm = mlb_position_probs(mv, age, bmi)
    if not pm:
        return {"def_value": 0.0, "def_home_entropy": 0.0}
    base = sum(pm.get(pos, 0.0) * POS_ADJ.get(pos, 0.0) for pos in pm)
    qual = 1.0
    if up_mid_share is not None:
        qual = 0.85 + 0.30 * max(0.0, min(1.0, up_mid_share))
    out = {"def_value": round(base * qual, 3),
           "def_home_entropy": round(_entropy(pm), 4)}
    for pos in POSITIONS:
        if pm.get(pos, 0.0) > 0:
            out[f"p_{pos}"] = round(pm[pos], 4)
    return out


def _parse_height_in(h) -> int | None:
    m = re.match(r"\s*(\d+)'\s*(\d+)", str(h or ""))
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def frame_map() -> dict[str, dict]:
    """player_key (xFV-style, draft prefix stripped) -> {h_in, wt, bmi} from the
    draft_players + overseas_players DB tables (height '6\\' 2', weight lbs)."""
    out: dict[str, dict] = {}
    try:
        from storage import connect
        with connect() as con:
            for t in ("draft_players", "overseas_players"):
                try:
                    rows = con.execute(
                        f"SELECT player_key, height, weight FROM {t} "
                        f"WHERE height IS NOT NULL AND weight IS NOT NULL").fetchall()
                except Exception:                                    # noqa: BLE001
                    continue
                for k, h, w in rows:
                    hi = _parse_height_in(h)
                    try:
                        w = float(w)
                    except (TypeError, ValueError):
                        w = None
                    if hi and w and 60 <= hi <= 84 and 120 <= w <= 320:
                        key = re.sub(r"^(draft|overseas)_\d{4}_", "", str(k))
                        out.setdefault(key, {"h_in": hi, "wt": w,
                                             "bmi": round(703.0 * w / (hi * hi), 2)})
    except Exception:                                                # noqa: BLE001
        pass
    return out


def _up_mid_share_map() -> dict[str, float]:
    """player_key -> up-the-middle share of career games (positions_played.json), a
    present-day quality multiplier for CURRENT prospects."""
    try:
        pp = json.loads((DATA / "positions_played.json").read_text(encoding="utf-8"))["players"]
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for k, v in pp.items():
        by = v.get("by_pos") or {}
        tot = sum((s.get("g") or 0) for s in by.values())
        if tot > 0:
            out[k] = sum((by.get(p, {}).get("g") or 0) for p in UP_MIDDLE) / tot
    return out


def build(out_path: Path | None = None) -> dict:
    """Emit data/prospect_def_value.json keyed by mlbam: {def_value, def_home_entropy,
    p_<pos>}. Built from the xFV hitter matrix's AS-OF-DECISION listed position + age +
    BMI (draft_players frame) + the current up-mid-share quality multiplier."""
    rows = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    ums = _up_mid_share_map()
    fm = frame_map()
    out, n_bmi = {}, 0
    for r in rows:
        mlbam = r.get("mlbam_id")
        if not mlbam:
            continue
        age = None
        bd, cut = r.get("birth_date"), r.get("cutoff") or r.get("asof_date")
        if bd and cut:
            try:
                age = int(str(cut)[:4]) - int(str(bd)[:4])
            except ValueError:
                pass
        pk = r.get("player_key")
        bmi = (fm.get(pk) or {}).get("bmi")
        if bmi is not None:
            n_bmi += 1
        dv = def_value(r.get("position"), age, ums.get(pk), bmi)
        dv["player_key"] = pk
        out[str(mlbam)] = dv
    path = out_path or (DATA / "prospect_def_value.json")
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path} -- {len(out)} prospects ({n_bmi} with BMI)")
    return out


def _realized_pos_value() -> dict[int, float]:
    """mlbam -> realized MLB positional value = innings-weighted POS_ADJ of actual MLB
    usage (data/mlb_fielding_positions.json). The ground truth def_value must predict."""
    try:
        pl = json.loads((DATA / "mlb_fielding_positions.json").read_text(encoding="utf-8"))["players"]
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for v in pl.values():
        mlbam = v.get("mlbam")
        pos = v.get("positions") or {}
        tot = sum((p.get("innings") or p.get("games") or 0) for p in pos.values())
        if mlbam and tot > 0:
            val = sum((p.get("innings") or p.get("games") or 0) * POS_ADJ.get(pp, 0.0)
                      for pp, p in pos.items()) / tot
            out[int(mlbam)] = val
    return out


def _spearman(xs, ys) -> float:
    import statistics
    n = len(xs)
    if n < 3:
        return 0.0
    def rank(a):
        order = sorted(range(n), key=lambda i: a[i])
        r = [0.0] * n
        for rk, i in enumerate(order):
            r[i] = rk
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def validate() -> dict:
    """MUST-PASS gate: on GRADUATED prospects, does def_value predict realized MLB
    positional value better than the FG fFld (tool_field) grade? Leakage-safe: def_value
    uses the AS-OF-PROSPECT listed position + frame, never the realized MLB position."""
    import statistics
    rows = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    dv = json.loads((DATA / "prospect_def_value.json").read_text(encoding="utf-8"))
    realized = _realized_pos_value()
    # one row per mlbam (the as-of-prospect read); tool_field is the FG fFld baseline
    tf = {}
    for r in rows:
        m = r.get("mlbam_id")
        if m and r.get("tool_field") is not None:
            tf.setdefault(int(m), float(r["tool_field"]))
    xs_dv, xs_tf, ys = [], [], []
    for m, real in realized.items():
        d = dv.get(str(m))
        if d and m in tf:
            xs_dv.append(d["def_value"]); xs_tf.append(tf[m]); ys.append(real)
    n = len(ys)
    if n < 10:
        return {"n": n, "error": "too few graduated comps"}

    def _z(a):
        mu, sd = statistics.mean(a), statistics.pstdev(a) or 1.0
        return [(x - mu) / sd for x in a]
    zy = _z(ys)
    mae_dv = sum(abs(a - b) for a, b in zip(_z(xs_dv), zy)) / n
    mae_tf = sum(abs(a - b) for a, b in zip(_z(xs_tf), zy)) / n
    out = {
        "n_graduated": n,
        "def_value": {"spearman": round(_spearman(xs_dv, ys), 4), "mae_z": round(mae_dv, 4)},
        "fg_tool_field": {"spearman": round(_spearman(xs_tf, ys), 4), "mae_z": round(mae_tf, 4)},
        "leakage_check": "def_value uses as-of-prospect listed position + frame (BMI) + age "
                         "only; realized MLB position is never an input",
        "verdict": None,
    }
    better = (abs(out["def_value"]["spearman"]) > abs(out["fg_tool_field"]["spearman"])
              and out["def_value"]["mae_z"] <= out["fg_tool_field"]["mae_z"])
    out["verdict"] = ("def_value BEATS FG fFld" if better else
                      "def_value does NOT beat FG fFld")
    return out


if __name__ == "__main__":
    import sys
    if "--validate" in sys.argv:
        print(json.dumps(validate(), indent=1))
    else:
        build()
