# SCRATCH LAB (combinatorial-archetype lane). READ-ONLY w.r.t. shipped code.
#
# AXIS LAYER ONLY. This module knows NOTHING about outcomes. It loads the eFV matrix,
# assigns every row to a bucket on every pre-registered axis, and stops. It is imported
# by _comb_sweep.py (prereg mode) to emit the candidate list BEFORE any outcome statistic
# is computed, which is what makes the multiplicity denominator honest.
#
# Discretisation policy (pre-registered, outcome-blind):
#   * FIXED baseball cuts wherever the domain supplies an established threshold
#     (scouting 20-80 grades, level ladder, draft rounds, FV tiers, age).
#   * TERCILES of the analysis population for the rate metrics, which have no established
#     threshold. Terciles are computed from the FEATURE distribution only. A cut chosen
#     by looking at outcomes would be leakage.
#   * Rows missing an axis value are EXCLUDED from that axis's strata. They are never
#     lumped into a residual bucket (that would make "missing" an archetype by accident).
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"


# --------------------------------------------------------------------------- helpers
def _tercile_edges(vals):
    v = sorted(float(x) for x in vals if x is not None)
    if len(v) < 30:
        return None

    def q(p):
        i = p * (len(v) - 1)
        lo = int(i)
        hi = min(lo + 1, len(v) - 1)
        return v[lo] + (i - lo) * (v[hi] - v[lo])
    return (q(1 / 3), q(2 / 3))


def _terc(x, edges, lab):
    if x is None or edges is None:
        return None
    return lab[0] if x < edges[0] else (lab[1] if x < edges[1] else lab[2])


def _cut(x, edges, labels):
    """edges ascending; len(labels) == len(edges)+1."""
    if x is None:
        return None
    for i, e in enumerate(edges):
        if x < e:
            return labels[i]
    return labels[-1]


_POS_FINE = {
    "C": "C", "SS": "SS", "2B": "2B", "3B": "3B", "1B": "1B/DH", "DH": "1B/DH",
    "CF": "CF", "LF": "COF", "RF": "COF", "OF": "OF",
    "INF": "UTIL", "UTIL": "UTIL", "IF": "UTIL",
}
_POS_GROUP = {
    "C": "C", "SS": "MIF", "2B": "MIF", "3B": "CIF", "1B/DH": "CIF",
    "CF": "OF", "COF": "OF", "OF": "OF", "UTIL": "UTIL",
}
_LEVEL = {"DSL": "CPX", "CPX": "CPX", "A": "A", "A+": "A+", "AA": "AA", "AAA": "AAA"}


def _pos_fine(pos):
    if not pos:
        return None
    return _POS_FINE.get(str(pos).split("/")[0].strip().upper())


# --------------------------------------------------------------------------- axes
# ("name", tier, "justification"). tier CORE = eligible for 1/2/3-way; EXT = 1/2-way only.
# Capping 3-way membership at the CORE set is a pre-registered complexity control: it
# keeps the triple family from being dominated by near-duplicate axes (pos_fine vs
# pos_group, ops_rel terciles vs its sign cut, obp_rel vs ops_rel), which would inflate
# the denominator without adding independent hypotheses.
AXIS_META = {
    "age":            ("CORE", "milb", "fixed", "20 / 22 / 23.5 are the HS-signing, college-draft and 'old for the upper minors' conventions"),
    "age_rel_level":  ("CORE", "milb", "fixed", "-2 / -0.5 / +1 years vs the level's typical age: very young, young, on time, old"),
    "level":          ("CORE", "milb", "fixed", "the level ladder itself; DSL folded into CPX for n"),
    "n_milb_seasons": ("CORE", "milb", "fixed", "1 / 2-3 / 4+ seasons of track record"),
    "ops_rel":        ("CORE", "milb", "tercile", "no established threshold on level-relative OPS; terciles are outcome-blind and balanced"),
    "k_rel":          ("CORE", "milb", "tercile", "same"),
    "iso_rel":        ("CORE", "milb", "tercile", "same"),
    "prod_trend":     ("CORE", "milb", "tercile", "same"),
    "pos_group":      ("CORE", "free", "fixed", "C / middle infield / corner infield / outfield / utility"),
    "tool_hit":       ("CORE", "free", "fixed", "20-80 scale: below average (<45), average (45-55), plus (60+)"),
    "tool_game_pwr":  ("CORE", "free", "fixed", "same 20-80 bands"),
    "tool_speed":     ("CORE", "free", "fixed", "20-80 bands plus a 70+ 'burner' band, which is the owner's Bradfield case"),
    "acq":            ("CORE", "free", "fixed", "acquisition cohort: international amateur / college draft / high-school draft"),
    "fv":             ("CORE", "free", "fixed", "consensus FV tiers 35-/40/45/50+, the industry's own grade bins"),

    "ops_sign":       ("EXT", "milb", "fixed", "above / below the level median: the owner's stated Bradfield cut"),
    "obp_rel":        ("EXT", "milb", "tercile", "no established threshold"),
    "bb_rel":         ("EXT", "milb", "tercile", "no established threshold"),
    "peak_ops_rel":   ("EXT", "milb", "tercile", "best-season production, no established threshold"),
    "peak_k_rel":     ("EXT", "milb", "tercile", "same"),
    "pos_fine":       ("EXT", "free", "fixed", "the nine primary-position buckets"),
    "tool_raw_pwr":   ("EXT", "free", "fixed", "20-80 bands"),
    "tool_field":     ("EXT", "free", "fixed", "20-80 bands"),
    "tool_throw":     ("EXT", "free", "fixed", "20-80 bands"),
    "pick":           ("EXT", "free", "fixed", "draft rounds: top 10, rest of round 1 plus comp, rounds 2-3, day 2/3"),
    "bonus":          ("EXT", "free", "tercile", "signing bonus among rows that report one; no established threshold"),
    "n_sources":      ("EXT", "free", "fixed", "1 / 2 / 3+ ranking outlets on the consensus"),
    "fv_trend":       ("EXT", "free", "tercile", "grade momentum, no established threshold"),
    "il_any_pre":     ("EXT", "free", "fixed", "any pre-decision injured-list stint"),

    # pitcher-only axes (the replication family)
    "era_rel":        ("CORE", "milb", "tercile", "level-relative ERA, no established threshold"),
    "role":           ("CORE", "free", "fixed", "starter vs reliever, the single biggest pitcher role split"),
    "tool_fb":        ("CORE", "free", "fixed", "20-80 fastball bands"),
    "tool_cmd":       ("CORE", "free", "fixed", "20-80 command bands"),
    "era_sign":       ("EXT", "milb", "fixed", "better / worse than the level median"),
    "peak_bb_rel":    ("EXT", "milb", "tercile", "best-season walk rate, no established threshold"),
    "tool_sl":        ("EXT", "free", "fixed", "20-80 slider bands"),
    "tool_ch":        ("EXT", "free", "fixed", "20-80 changeup bands"),
    "tool_cb":        ("EXT", "free", "fixed", "20-80 curveball bands"),
    "hand":           ("EXT", "free", "fixed", "throwing hand"),
}


def load_rows(side="hit"):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    return json.loads((DATA / fn).read_text(encoding="utf-8"))


def build_axes(rows, side="hit"):
    """Return {axis: [bucket-or-None per row]} plus the realised level order per axis.
    Terciles are computed over the rows supplied (the analysis population)."""
    mb = [r.get("milb") if isinstance(r.get("milb"), dict) else {} for r in rows]

    def g(k):
        return [m.get(k) for m in mb]

    ed = {}
    for k in ("ops_rel", "k_rel", "iso_rel", "prod_trend", "obp_rel", "bb_rel",
              "peak_ops_rel", "peak_k_rel"):
        ed[k] = _tercile_edges(g(k))
    ed["fv_trend"] = _tercile_edges([r.get("fv_trend") for r in rows])
    ed["bonus"] = _tercile_edges([r.get("bonus_usd") for r in rows if r.get("bonus_usd")])

    T3 = ("T1", "T2", "T3")
    A = {}
    A["age"] = [_cut(x, (20.0, 22.0, 23.5), ("U20", "20-21", "22-23", "23.5+")) for x in g("age")]
    A["age_rel_level"] = [_cut(x, (-2.0, -0.5, 1.0), ("VYNG", "YNG", "ONTIME", "OLD"))
                          for x in g("age_rel_level")]
    A["level"] = [_LEVEL.get(x) for x in g("milb_level")]
    A["n_milb_seasons"] = [_cut(x, (2, 4), ("S1", "S2-3", "S4+")) for x in g("n_milb_seasons")]
    for k in ("ops_rel", "k_rel", "iso_rel", "prod_trend", "obp_rel", "bb_rel",
              "peak_ops_rel", "peak_k_rel"):
        A[k] = [_terc(x, ed[k], T3) for x in g(k)]
    A["ops_sign"] = [None if x is None else ("BELOW" if x < 0 else "ABOVE") for x in g("ops_rel")]

    pf = [_pos_fine(r.get("position")) for r in rows]
    A["pos_fine"] = pf
    A["pos_group"] = [_POS_GROUP.get(p) if p else None for p in pf]
    for k in ("tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_field", "tool_throw"):
        A[k] = [_cut(r.get(k), (45.0, 57.5), ("BLW", "AVG", "PLUS")) for r in rows]
    A["tool_speed"] = [_cut(r.get("tool_speed"), (45.0, 57.5, 67.5),
                            ("BLW", "AVG", "PLUS", "BURNER")) for r in rows]
    A["acq"] = [("IFA" if r.get("is_ifa") else ("COL" if r.get("is_college") else "HS"))
                for r in rows]
    A["pick"] = [_cut(r.get("pick_overall"), (11, 41, 101), ("TOP10", "R1", "R2-3", "DAY2+"))
                 if r.get("pick_overall") else None for r in rows]
    A["bonus"] = [_terc(r.get("bonus_usd"), ed["bonus"], T3) if r.get("bonus_usd") else None
                  for r in rows]
    A["fv"] = [_cut(r.get("consensus_fv_raw"), (37.5, 42.5, 47.5),
                    ("FV35-", "FV40", "FV45", "FV50+")) for r in rows]
    A["n_sources"] = [_cut(r.get("n_sources"), (2, 3), ("SRC1", "SRC2", "SRC3+"))
                      for r in rows]
    A["fv_trend"] = [_terc(r.get("fv_trend"), ed["fv_trend"], T3) for r in rows]
    A["il_any_pre"] = [("IL" if r.get("il_any_pre") else "NOIL") for r in rows]

    if side == "pit":
        for k in ("iso_rel", "ops_rel", "ops_sign", "obp_rel", "peak_ops_rel",
                  "tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_speed",
                  "tool_field", "tool_throw", "pos_fine", "pos_group"):
            A.pop(k, None)
        ed["era_rel"] = _tercile_edges(g("era_rel"))
        ed["peak_bb_rel"] = _tercile_edges(g("peak_bb_rel"))
        A["era_rel"] = [_terc(x, ed["era_rel"], T3) for x in g("era_rel")]
        A["era_sign"] = [None if x is None else ("BETTER" if x < 0 else "WORSE")
                         for x in g("era_rel")]
        A["peak_bb_rel"] = [_terc(x, ed["peak_bb_rel"], T3) for x in g("peak_bb_rel")]
        for k in ("tool_fb", "tool_cmd", "tool_sl", "tool_ch", "tool_cb"):
            A[k] = [_cut(r.get(k), (45.0, 57.5), ("BLW", "AVG", "PLUS")) for r in rows]
        A["role"] = [("RP" if "RP" in str(r.get("position") or "").upper() else "SP")
                     for r in rows]
        A["hand"] = [("L" if str(r.get("position") or "").upper().startswith("L")
                      else ("R" if str(r.get("position") or "").upper().startswith("R")
                            else None)) for r in rows]
    return A, ed
