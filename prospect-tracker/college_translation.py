# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""College -> Single-A statistical translation for CollegeSavant.

Honest matched-pair translation: it answers "what does this college line project
to against Single-A pitching" with an uncertainty band, never a fake precise
forecast. Built from OUR OWN data: CollegeSavant TrackMan players joined by name
to draft_players -> their later Single-A statline in prospects.db.

Tiers (per the owner-approved methodology):
  * Tier 1 - matched-pair regression for K% and BB% (the only rates carried on
    both the college tracked side and the Single-A conventional side). A
    regression-to-the-mean form (predicted = pop_mean + shrunk_slope * (college
    - col_mean)) so a weak relationship pulls hard toward the level mean.
  * Tier 2 - EXPERIMENTAL production (hitter OPS from college xwOBA): shipped
    only because the owner asked; in our data it carries almost no signal
    (r^2 ~ 0.01), so it is a near-flat projection with a very wide band and is
    labeled experimental.
  * Tier 3 - the pure tracked skills stay the CS+ index (college-relative), not
    a Single-A projection; computed in the frontend, not here.

Every translated stat carries an expected value and a P10-P90 band that widens
with thinner matched support. SOS / park are NOT adjusted (we hold no
conference / park table); that is stated plainly in the output and the UI.

Outputs (written by build()):
  data/college_translation_eval.json  - fitted factors, sample sizes, and the
                                         leave-one-out backtest (MAE + coverage)
  data/collegesavant_translation.js    - window.CS_TRANSLATION, per-player
                                         translated lines keyed by name slug,
                                         lazily merged by the CollegeSavant apps
  data/collegesavant_milb_equiv.json   - the PROSPX BRIDGE: by_player_key ->
                                         {side, headline:[{label,value,band,flag}]}
                                         for each college player that matches a
                                         draft prospect (~476), keyed by the
                                         draft player_key

PROSPX consumption (the clean hook, owner-applied so PROSPX is not rebuilt here):
PROSPX lazily fetches collegesavant_milb_equiv.json and, on a draft prospect
detail, looks up by_player_key[p.player_key]; if present it renders the headline
chips as a "Projected Single-A (CollegeSavant)" block in the existing College
Stats tab (the same {label,value} chip path p.college_stats already uses). The
file is additive and safe-when-empty: an absent or partial file leaves the draft
section unchanged, and name-only matches that don't resolve are simply omitted.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import storage
# BF_PER_9: K/9, BB/9 -> K%, BB% fallback conversion. SLOPE_SHRINK_K: slope
# = ols_slope * n / (n + K), pulls thin fits toward pure regression-to-the-
# mean. Both live in rate_stabilization with their provenance.
from rate_stabilization import BF_PER_9, SLOPE_SHRINK_K

ROOT = Path(__file__).parent
CS = ROOT / "collegesavant"

# One low-signal rule for every leg and every surface: a factor whose r2 is
# below this is flagged (the per-player low_confidence band flag, the PROSPX
# bridge chip, and the CollegeSavant accuracy table and trust copy, which read
# the same threshold off the eval). It was already the BB% rule; K% now obeys
# it too, because on the pitcher side K% is the leg that falls under it.
LOW_SIGNAL_R2 = 0.10


def _low_signal(factor: dict) -> bool:
    return factor["r2"] < LOW_SIGNAL_R2

_DEC = json.JSONDecoder()


def _first_array(path: Path, marker: str):
    text = path.read_text(encoding="utf-8", errors="replace")
    i = text.find(marker)
    i = text.find("[", i)
    return _DEC.raw_decode(text[i:])[0]


def slugify_cs(name: str) -> str:
    """Mirror the CollegeSavant frontend slugify() exactly so the translation
    sidecar keys match each player's `slug` for a direct client-side lookup:
    lowercase, non-alphanumeric runs -> '-', trim leading/trailing '-'."""
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", (name or "").lower()))


def norm_name(n: str) -> str:
    """'Last, First' / 'First Last' -> a normalized join key."""
    if not n:
        return ""
    n = n.strip()
    if "," in n:
        parts = [p.strip() for p in n.split(",")]
        n = (parts[1] + " " + parts[0]) if len(parts) > 1 else parts[0]
    n = n.lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", n)
    n = re.sub(r"[^a-z ]", "", n)
    return re.sub(r"\s+", " ", n).strip()


# --------------------------------------------------------------------------- #
# Load the college (CollegeSavant) side
# --------------------------------------------------------------------------- #
def load_cs_hitters() -> dict:
    """name_slug -> best (latest-year) college tracked line for the join."""
    rows = _first_array(CS / "hitter_year_data.js", "window.HITTER_DATA")
    out = {}
    for r in sorted(rows, key=lambda x: x.get("year", 0)):
        out[norm_name(r.get("hitter_name"))] = {
            "name": r.get("hitter_name"),
            "team": r.get("team"),
            "k_pct": r.get("k_pct"),
            "bb_pct": r.get("bb_pct"),
            "xwoba": r.get("xwoba"),
            "year": r.get("year"),
        }
    return out


def load_cs_pitchers() -> dict:
    rows = _first_array(CS / "pitcher_data.js", "window.PITCHER_DATA")
    out = {}
    for r in rows:
        slug = norm_name(r.get("pitcher_name"))
        if not slug or r.get("k_pct") is None:
            continue  # only the 2024/2025 outcome rows carry K% / BB%
        pc = r.get("pitch_count") or 0
        if slug not in out or pc > out[slug]["pitch_count"]:
            out[slug] = {
                "name": r.get("pitcher_name"),
                "pitcher_id": r.get("pitcher_id"),
                "team": r.get("team"),
                "k_pct": r.get("k_pct"),
                "bb_pct": r.get("bb_pct"),
                "pitch_count": pc,
                "year": r.get("year"),
            }
    return out


# --------------------------------------------------------------------------- #
# Load the pro (Single-A) side from prospects.db, keyed by normalized name
# --------------------------------------------------------------------------- #
def _key_to_name(con) -> dict:
    out = {}
    for k, nm in con.execute("SELECT player_key, player_name FROM players"):
        out[k] = norm_name(nm)
    return out


def _draft_keys(con) -> dict:
    """normalized college name -> the draft prospect's player_key, so a college
    translation can be attached to the matching PROSPX draft record."""
    out = {}
    for pk, nm in con.execute("SELECT player_key, player_name FROM draft_players"):
        out.setdefault(norm_name(nm), pk)
    return out


def _ncaa_box_to_display(payload, season, school):
    """An NCAA batting payload (from college_stats) -> the hitter player-page box
    shape. NCAA bb%/k% arrive as percentages (12.5); the panel expects the decimal
    convention (0.125) draft_statlines uses. woba/wRC+ are not derivable from box
    rows, so they read blank."""
    p = payload or {}
    def _pct(x):
        return x / 100 if x is not None else None
    return {"season": season, "level": "NCAA", "team": school,
            "avg": p.get("avg"), "obp": p.get("obp"), "slg": p.get("slg"),
            "iso": p.get("iso"), "woba": None, "wrc_plus": None,
            "bb_pct": _pct(p.get("bb_pct")), "k_pct": _pct(p.get("k_pct")),
            "hr": p.get("hr"), "pa": p.get("pa")}


def _rate_to_decimal(x):
    """A walk/strikeout rate to the decimal convention (0.131), tolerant of values
    stored as percentages (13.1). None passes through."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v / 100.0 if v > 1 else v


def _draft_statlines(con):
    """player_key -> latest-season conventional COLLEGE box score (FG / NCAA),
    split hit vs pit, so CollegeSavant can show real AVG/OBP/SLG/ISO (hitters) or
    ERA/K9/BB9 (pitchers) for the players we already hold box scores for."""
    hit, pit = {}, {}
    for pk, pj in con.execute("SELECT player_key, payload_json FROM draft_statlines ORDER BY player_key, "
                              "json_extract(payload_json, '$.season')"):
        try:
            d = json.loads(pj)
        except ValueError:
            continue
        base = {"season": d.get("season"), "level": d.get("level"), "team": d.get("team")}
        if d.get("avg") is not None or d.get("obp") is not None:
            # draft_statlines bb%/k% arrive in MIXED units: FanGraphs as decimals
            # (0.131) but the NCAA box pull as percentages (13.1). Normalize both to
            # the decimal convention the box panel + Draft Prospects board expect, so
            # a 13.1% walk rate never renders as 1310%. A real rate as a decimal is
            # 0-1; anything above 1 is a stored percentage, so divide it down.
            hit[pk] = {**base, "pa": d.get("pa"), "avg": d.get("avg"), "obp": d.get("obp"),
                       "slg": d.get("slg"), "iso": d.get("iso"), "woba": d.get("woba"),
                       "wrc_plus": d.get("wrc_plus"), "bb_pct": _rate_to_decimal(d.get("bb_pct")),
                       "k_pct": _rate_to_decimal(d.get("k_pct")), "hr": d.get("hr"), "sb": d.get("sb")}
        elif d.get("era") is not None or d.get("k_per_9") is not None:
            pit[pk] = {**base, "ip": d.get("ip"), "era": d.get("era"), "fip": d.get("fip"),
                       "xfip": d.get("xfip"), "k_per_9": d.get("k_per_9"),
                       "bb_per_9": d.get("bb_per_9"), "w": d.get("w"), "l": d.get("l")}
    return hit, pit


def _draft_prospect_export(con, box_hit, box_pit, pk_to_cs=None, F=None):
    """The reverse of the tracking universe: draft prospects (each year) brought
    INTO CollegeSavant by their conventional college box score, for the ones we
    already hold stats for - including prospects with no TrackMan tracking. Keyed
    nowhere; emitted as two ranked lists (hitters / pitchers) the frontend filters
    by draft year. Carries the consensus FV + board rank so the section reads as a
    draft board, not just a stat dump."""
    meta = {}
    for pk, name, pos, school, ptype, year, bats, throws in con.execute(
            "SELECT player_key, player_name, position, school, player_type, draft_year, "
            "bats, throws FROM draft_players"):
        meta[pk] = {"name": name, "pos": pos, "school": school, "type": ptype,
                    "year": year, "bats": bats, "throws": throws}
    fv = {}  # latest consensus FV + board rank per player_key
    for pk, f, rk in con.execute(
            "SELECT player_key, fv, rank FROM draft_snapshots WHERE fv IS NOT NULL "
            "ORDER BY snapshot_date"):
        fv[pk] = {"fv": f, "rank": rk}

    cs_links = pk_to_cs or {}

    def _entry(pk, box):
        m = meta.get(pk) or {}
        e = {"name": m.get("name"), "school": m.get("school"), "pos": m.get("pos"),
             "year": m.get("year"), "type": m.get("type"), "bats": m.get("bats"),
             "throws": m.get("throws"), "box": box}
        if pk in fv:
            e["fv"] = fv[pk]["fv"]
            e["rank"] = fv[pk]["rank"]
        if pk in cs_links:  # this prospect also has a CollegeSavant tracked page
            e["cs"] = cs_links[pk]
        proj = _box_project(box, F or {})  # Single-A projection from the college box
        if proj:
            e["proj"] = proj
        return e

    def _rank_key(x):
        return (-(x.get("fv") or 0), x.get("rank") or 99999, x.get("name") or "")

    hitters = sorted((_entry(pk, b) for pk, b in box_hit.items() if pk in meta), key=_rank_key)
    pitchers = sorted((_entry(pk, b) for pk, b in box_pit.items() if pk in meta), key=_rank_key)
    return {"hitters": hitters, "pitchers": pitchers}


def _equiv_headline(sa: dict, side: str) -> list[dict]:
    """The Single-A equivalent as PROSPX-renderable {label, value, band, flag}
    chips, mirroring the draft_export college_stats headline shape."""
    chips = []

    def chip(label, b, fmt, flag):
        if not b:
            return
        if fmt == "pct":
            val = f"{b['exp']:.1f}%"
            band = f"{round(b['lo'])}-{round(b['hi'])}%"
        else:
            val = f"{b['exp']:.3f}".lstrip("0")
            band = f"{b['lo']:.3f}".lstrip("0") + "-" + f"{b['hi']:.3f}".lstrip("0")
        chips.append({"label": label, "value": val, "band": band, "flag": flag})

    chip("Proj A K%", sa.get("k_pct"), "pct",
         "low confidence" if (sa.get("k_pct") or {}).get("low_confidence") else None)
    chip("Proj A BB%", sa.get("bb_pct"), "pct",
         "low confidence" if (sa.get("bb_pct") or {}).get("low_confidence") else None)
    if side == "hit":
        chip("Proj A OPS", sa.get("ops"), "dec", "experimental")
    return chips


def load_single_a(con, key_name: dict):
    """Return {slug: {hit:{k_pct,bb_pct,ops}, pit:{k_pct,bb_pct}}} from the
    earliest qualifying Single-A (A / A+) season on file. Pitcher K%/BB% use the
    stored rate (from actual batters faced) when present, falling back to the
    K/9, BB/9 via BF_PER_9 conversion only when it is missing. Pitcher seasons
    gated at >= 20 IP."""
    hit, pit = {}, {}
    for pk, pj in con.execute("SELECT player_key, payload_json FROM statlines"):
        try:
            d = json.loads(pj)
        except ValueError:
            continue
        if d.get("level") not in ("A", "A+"):
            continue
        slug = key_name.get(pk)
        if not slug:
            continue
        season = d.get("season") or 0
        if d.get("is_pitcher"):
            try:
                ip = float(d.get("ip") or 0)
            except (TypeError, ValueError):
                ip = 0.0
            if ip < 20:
                continue
            # Prefer the stored K%/BB% (computed from actual batters faced); only
            # fall back to the K/9, BB/9 -> rate conversion via BF_PER_9 when a
            # stored rate is missing. The fixed 38-BF assumption biased the
            # derived K% ~1.4 pts high (M12), flattening the pitcher fit against
            # the college side (which already uses stored rates); 96% of A/A+
            # pitcher seasons carry k_pct/bb_pct, so that is the path for nearly
            # all rows and the conversion survives only as a thin fallback.
            kp = d.get("k_pct")
            if kp is None:
                if d.get("k_per_9") is None:
                    continue
                kp = float(d["k_per_9"]) / BF_PER_9 * 100.0
            else:
                kp = float(kp)
            bp = d.get("bb_pct")
            if bp is None:
                bb9 = d.get("bb_per_9")
                bp = (float(bb9) / BF_PER_9 * 100.0) if bb9 is not None else None
            else:
                bp = float(bp)
            pit.setdefault(slug, []).append((season, kp, bp))
        else:
            if d.get("k_pct") is None or d.get("bb_pct") is None:
                continue
            ops = None
            try:
                ops = float(str(d.get("ops"))) if d.get("ops") is not None else None
            except ValueError:
                ops = None
            hit.setdefault(slug, []).append(
                (season, float(d["k_pct"]), float(d["bb_pct"]), ops))
    # keep the earliest qualifying season per player (closest to the college line)
    hit = {s: sorted(v)[0] for s, v in hit.items()}
    pit = {s: sorted(v)[0] for s, v in pit.items()}
    return hit, pit


# --------------------------------------------------------------------------- #
# The fit: regression-to-the-mean with slope shrinkage + a residual band
# --------------------------------------------------------------------------- #
def _fit(xs: list[float], ys: list[float]) -> dict | None:
    """Fit y ~ x and return a regression-to-the-mean factor:
       predicted = y_mean + slope * (x - x_mean), slope shrunk toward 0.
    Plus the residual std (the 1-sigma band) and r^2 / n for honesty."""
    n = len(xs)
    if n < 8:
        return None
    xm = sum(xs) / n
    ym = sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs)
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    ols = sxy / sxx if sxx else 0.0
    slope = ols * n / (n + SLOPE_SHRINK_K)
    resid = [y - (ym + slope * (x - xm)) for x, y in zip(xs, ys)]
    rmse = math.sqrt(sum(r * r for r in resid) / n)
    syy = sum((y - ym) ** 2 for y in ys)
    ols_resid = [y - (ym + ols * (x - xm)) for x, y in zip(xs, ys)]
    r2 = 1 - sum(r * r for r in ols_resid) / syy if syy else 0.0
    return {"x_mean": round(xm, 3), "y_mean": round(ym, 3),
            "slope": round(slope, 4), "ols_slope": round(ols, 4),
            "band_sd": round(rmse, 3), "r2": round(r2, 3), "n": n}


def _pairs(cs: dict, pro: dict, cs_key: str, pro_idx: int):
    xs, ys = [], []
    for slug, v in cs.items():
        if slug in pro and v.get(cs_key) is not None and pro[slug][pro_idx] is not None:
            xs.append(float(v[cs_key]))
            ys.append(float(pro[slug][pro_idx]))
    return xs, ys


def _predict(factor: dict, x: float) -> float:
    return factor["y_mean"] + factor["slope"] * (x - factor["x_mean"])


def _loo_mae_cov(cs, pro, cs_key, pro_idx):
    """Leave-one-out MAE + P10-P90 coverage: refit without each pair, predict it,
    score |err| and whether the actual lands inside the band. The honest test."""
    items = [(float(v[cs_key]), float(pro[s][pro_idx]))
             for s, v in cs.items()
             if s in pro and v.get(cs_key) is not None and pro[s][pro_idx] is not None]
    n = len(items)
    if n < 12:
        return None
    abs_err, null_err, inside = [], [], 0
    y_sum = sum(b for _, b in items)
    for i in range(n):
        train = items[:i] + items[i + 1:]
        f = _fit([a for a, _ in train], [b for _, b in train])
        if not f:
            continue
        x, y = items[i]
        pred = _predict(f, x)
        abs_err.append(abs(y - pred))
        # The registry baseline, scored on the same held-out pair: predict the
        # Single-A mean of the OTHER pairs (no college information).
        null_err.append(abs(y - (y_sum - y) / (n - 1)))
        lo, hi = pred - 1.2816 * f["band_sd"], pred + 1.2816 * f["band_sd"]
        if lo <= y <= hi:
            inside += 1
    m = len(abs_err)
    # skill = null MAE - model MAE (positive = the college rate helps); its se
    # is the paired standard error of the per-pair gains.
    gains = [b - a for a, b in zip(abs_err, null_err)]
    g_mean = sum(gains) / m
    g_sd = math.sqrt(sum((g - g_mean) ** 2 for g in gains) / (m - 1)) if m > 1 else 0.0
    return {"mae": round(sum(abs_err) / m, 3),
            "null_mae": round(sum(null_err) / m, 3),
            "skill": round(g_mean, 3), "skill_se": round(g_sd / math.sqrt(m), 3),
            "p10_p90_coverage": round(inside / m, 3),
            "target_coverage": 0.80, "n": m}


# --------------------------------------------------------------------------- #
# W4 COL-XRV (gated 2026-07-23, default OFF): usage-weighted college Stuff+
# covariate in the pitcher K% translation. Behind env flag EEPHUS_COL_XRV;
# with the flag unset this whole block is inert and the outputs are
# byte-identical. Gate ledger: data/college_stuff_translation_eval.json
# (registration docs/wills-2026-07-23/GATES.md section W4; lab
# tools/college_stuff_translation_lab.py, model key college_stuff_translation).
# --------------------------------------------------------------------------- #
_PITCH_STUFF_PAYLOADS = [
    (2024, "pitcher_pitch_data_2024.js", "window.PITCHER_PITCH_DATA_2024"),
    (2025, "pitcher_pitch_data_2025.js", "window.PITCHER_PITCH_DATA_2025"),
    (2026, "pitcher_pitch_data_2026.js", "window.PITCHER_PITCH_DATA_2026"),
]


def load_cs_pitch_stuff() -> dict:
    """(pitcher_id, year) -> usage-weighted college Stuff+ across that pitcher's
    pitch types (weights = pitch_count; rows with null stuff_plus or zero count
    excluded from numerator AND weights). Same-season join only: the covariate
    must describe the same tracked season as the K% outcome row."""
    out = {}
    for year, fname, marker in _PITCH_STUFF_PAYLOADS:
        path = CS / fname
        if not path.exists():
            continue
        acc = {}
        for r in _first_array(path, marker):
            sp, pc = r.get("stuff_plus"), r.get("pitch_count") or 0
            pid = str(r.get("pitcher_id") or "")
            if sp is None or pc <= 0 or not pid:
                continue
            w, s = acc.get(pid, (0.0, 0.0))
            acc[pid] = (w + pc, s + float(sp) * pc)
        for pid, (w, s) in acc.items():
            if w > 0:
                out[(pid, year)] = s / w
    return out


def _fit2(rows: list[tuple]) -> dict | None:
    """rows = [(x1, x2, y)] -> bivariate regression-to-the-mean factor: joint
    OLS via 2x2 normal equations, BOTH slopes shrunk by n/(n+SLOPE_SHRINK_K)
    (the incumbent univariate convention extended; registered a priori)."""
    n = len(rows)
    if n < 8:
        return None
    x1m = sum(r[0] for r in rows) / n
    x2m = sum(r[1] for r in rows) / n
    ym = sum(r[2] for r in rows) / n
    s11 = sum((r[0] - x1m) ** 2 for r in rows)
    s22 = sum((r[1] - x2m) ** 2 for r in rows)
    s12 = sum((r[0] - x1m) * (r[1] - x2m) for r in rows)
    s1y = sum((r[0] - x1m) * (r[2] - ym) for r in rows)
    s2y = sum((r[1] - x2m) * (r[2] - ym) for r in rows)
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-9:
        return None
    shrink = n / (n + SLOPE_SHRINK_K)
    b1 = (s22 * s1y - s12 * s2y) / det * shrink
    b2 = (s11 * s2y - s12 * s1y) / det * shrink
    resid = [r[2] - (ym + b1 * (r[0] - x1m) + b2 * (r[1] - x2m)) for r in rows]
    rmse = math.sqrt(sum(e * e for e in resid) / n)
    return {"x1_mean": round(x1m, 3), "x2_mean": round(x2m, 3),
            "y_mean": round(ym, 3), "b1": round(b1, 4), "b2": round(b2, 4),
            "band_sd": round(rmse, 3), "n": n}


def _predict2(f: dict, x1: float, x2: float) -> float:
    return f["y_mean"] + f["b1"] * (x1 - f["x1_mean"]) + f["b2"] * (x2 - f["x2_mean"])


def col_xrv_enabled() -> bool:
    """EEPHUS_COL_XRV: default OFF; any non-empty value enables the covariate."""
    return bool(os.environ.get("EEPHUS_COL_XRV"))


# --------------------------------------------------------------------------- #
# Translate one player + build the artifacts
# --------------------------------------------------------------------------- #
def _band(pred: float, sd: float, lo_clip=None, hi_clip=None, ndigits=1):
    lo, hi = pred - 1.2816 * sd, pred + 1.2816 * sd
    if lo_clip is not None:
        lo = max(lo_clip, lo)
    if hi_clip is not None:
        hi = min(hi_clip, hi)
    return {"exp": round(pred, ndigits), "lo": round(lo, ndigits), "hi": round(hi, ndigits)}


def _translate_hitter(v, F):
    out = {}
    if v.get("k_pct") is not None and F.get("hit_k"):
        out["k_pct"] = _band(_predict(F["hit_k"], v["k_pct"]), F["hit_k"]["band_sd"], 0, 100)  # C2/C3b: hi_clip -> true [0,100] domain (display band widened to LOO-validated coverage)
        if _low_signal(F["hit_k"]):
            out["k_pct"]["low_confidence"] = True
    if v.get("bb_pct") is not None and F.get("hit_bb"):
        b = _band(_predict(F["hit_bb"], v["bb_pct"]), F["hit_bb"]["band_sd"], 0, 100)
        b["low_confidence"] = _low_signal(F["hit_bb"])
        out["bb_pct"] = b
    if v.get("xwoba") is not None and F.get("hit_ops"):
        o = _band(_predict(F["hit_ops"], v["xwoba"]), F["hit_ops"]["band_sd"], 0.3, 1.2, ndigits=3)
        o["experimental"] = True
        out["ops"] = o
    return out


def _translate_pitcher(v, F, stuff_wt=None):
    out = {}
    if v.get("k_pct") is not None and F.get("pit_k_stuff") and stuff_wt is not None:
        # W4 COL-XRV covariate path: only reachable when EEPHUS_COL_XRV is set
        # (build() fits pit_k_stuff and passes stuff_wt only then), so the
        # flag-OFF output stays byte-identical.
        f2 = F["pit_k_stuff"]
        out["k_pct"] = _band(_predict2(f2, v["k_pct"], stuff_wt), f2["band_sd"], 0, 100)
    elif v.get("k_pct") is not None and F.get("pit_k"):
        out["k_pct"] = _band(_predict(F["pit_k"], v["k_pct"]), F["pit_k"]["band_sd"], 0, 100)
        # K% carries the flag only when it fires (BB% always carries the key),
        # so the 4,500-row sidecar does not grow a false on every row.
        if _low_signal(F["pit_k"]):
            out["k_pct"]["low_confidence"] = True
    if v.get("bb_pct") is not None and F.get("pit_bb"):
        b = _band(_predict(F["pit_bb"], v["bb_pct"]), F["pit_bb"]["band_sd"], 0, 100)
        b["low_confidence"] = _low_signal(F["pit_bb"])
        out["bb_pct"] = b
    return out


def _box_project(box, F):
    """Project a Single-A K%/BB% line from a draft prospect's CONVENTIONAL college
    box score (so prospects with no TrackMan tracking still get a projection). The
    box bb%/k% are decimals; the box_k / box_bb factors are fit in percent, so
    scale up before predicting. Returns None when no factor or no box rate."""
    if not box:
        return None
    out = {}
    if box.get("k_pct") is not None and F.get("box_k"):
        out["k_pct"] = _band(_predict(F["box_k"], box["k_pct"] * 100), F["box_k"]["band_sd"], 0, 100)
        if _low_signal(F["box_k"]):
            out["k_pct"]["low_confidence"] = True
    if box.get("bb_pct") is not None and F.get("box_bb"):
        b = _band(_predict(F["box_bb"], box["bb_pct"] * 100), F["box_bb"]["band_sd"], 0, 100)
        b["low_confidence"] = _low_signal(F["box_bb"])
        out["bb_pct"] = b
    return out or None


def build(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or (ROOT / "data")
    with storage.connect() as con:
        key_name = _key_to_name(con)
        cs_h, cs_p = load_cs_hitters(), load_cs_pitchers()
        sa_h, sa_p = load_single_a(con, key_name)

        F = {}
        for key, cs, pro, ck, pi in [
            ("hit_k", cs_h, sa_h, "k_pct", 1),
            ("hit_bb", cs_h, sa_h, "bb_pct", 2),
            ("hit_ops", cs_h, sa_h, "xwoba", 3),
            ("pit_k", cs_p, sa_p, "k_pct", 1),
            ("pit_bb", cs_p, sa_p, "bb_pct", 2),
        ]:
            xs, ys = _pairs(cs, pro, ck, pi)
            f = _fit(xs, ys)
            if f:
                f["loo"] = _loo_mae_cov(cs, pro, ck, pi)
                F[key] = f

        # W4 COL-XRV (default OFF): with EEPHUS_COL_XRV set, fit the pitcher K%
        # translation with the usage-weighted college Stuff+ covariate on the
        # covered matched pairs (same-season (pitcher_id, year) join). Flag
        # unset: cs_stuff stays empty, F never carries pit_k_stuff, and every
        # output byte matches the incumbent path.
        cs_stuff = load_cs_pitch_stuff() if col_xrv_enabled() else {}
        if cs_stuff and F.get("pit_k"):
            rows2 = []
            for slug, v in cs_p.items():
                if slug not in sa_p or v.get("k_pct") is None or sa_p[slug][1] is None:
                    continue
                sw = cs_stuff.get((str(v.get("pitcher_id")), v.get("year")))
                if sw is not None:
                    rows2.append((float(v["k_pct"]), sw, float(sa_p[slug][1])))
            f2 = _fit2(rows2)
            if f2:
                f2["covariate"] = "usage_weighted_college_stuff_plus"
                f2["eval_artifact"] = "college_stuff_translation_eval.json"
                F["pit_k_stuff"] = f2

        # NB: the accountability eval artifact is written AFTER the box_k/box_bb
        # factors are fitted below (they are live-in-production but were omitted from
        # the artifact when it was written here, before that block).

        # Key the per-player sidecar by the frontend slug (slugify of the raw
        # "Last, First" name) so each CollegeSavant player looks up their own.
        # Also build the PROSPX BRIDGE sidecar keyed by the matching draft
        # prospect's player_key, so PROSPX can merge a Single-A-equivalent block
        # onto its draft records with no rebuild. Additive and safe-when-empty.
        draft_keys = _draft_keys(con)
        box_hit, box_pit = _draft_statlines(con)

        # Box-stat -> Single-A factors: project a Single-A line for the Draft
        # Prospects board from a prospect's conventional college box (K%/BB%),
        # matched by name to the same Single-A side the tracked model uses. Lets
        # prospects with no TrackMan tracking still get an honest projection.
        draft_name = {pk: norm_name(nm) for pk, nm in
                      con.execute("SELECT player_key, player_name FROM draft_players")}
        box_cs = {}
        for pk, b in box_hit.items():
            nm = draft_name.get(pk)
            if nm and (b.get("k_pct") is not None or b.get("bb_pct") is not None):
                box_cs[nm] = {"k_pct": b["k_pct"] * 100 if b.get("k_pct") is not None else None,
                              "bb_pct": b["bb_pct"] * 100 if b.get("bb_pct") is not None else None}
        for bkey, bck, bpi in [("box_k", "k_pct", 1), ("box_bb", "bb_pct", 2)]:
            bxs, bys = _pairs(box_cs, sa_h, bck, bpi)
            bf = _fit(bxs, bys)
            if bf:
                bf["loo"] = _loo_mae_cov(box_cs, sa_h, bck, bpi)
                F[bkey] = bf

        # Accountability eval artifact -- written HERE, after ALL factors (including
        # box_k / box_bb) are in F, so the artifact matches what production actually uses.
        eval_doc = {
            "method": "matched-pair regression-to-the-mean (college -> Single-A), "
                      "our-data join: CollegeSavant name -> draft_players -> statlines (A/A+)",
            "bf_per_9": BF_PER_9, "slope_shrink_k": SLOPE_SHRINK_K,
            "low_signal_r2": LOW_SIGNAL_R2,
            "competition_park_adjusted": False,
            "caveat": "Not adjusted for strength of schedule or park (no conference/park "
                      "table held). Bands are P10-P90 and widen with thinner support. "
                      "hit_ops is experimental: college tracked data barely forecasts "
                      "Single-A production in our matched sample.",
            "factors": F,
            "matched_pairs": {
                "hitters_with_single_a": sum(1 for s in cs_h if s in sa_h),
                "pitchers_with_single_a": sum(1 for s in cs_p if s in sa_p),
            },
        }
        (out_dir / "college_translation_eval.json").write_text(
            json.dumps(eval_doc, indent=1), encoding="utf-8")

        translations, bridge = {}, {}
        pk_to_cs = {}  # draft player_key -> {slug, year, side}: prospects that ALSO
        n_box = 0      # have a CollegeSavant tracked page, so the board can link to it
        for slug_norm, v in cs_h.items():
            t = _translate_hitter(v, F)
            if not t:
                continue
            slug = slugify_cs(v["name"])
            entry = {"side": "hit", "single_a": t}
            pk = draft_keys.get(slug_norm)
            if pk and pk in box_hit:
                entry["box"] = box_hit[pk]
                n_box += 1
            translations[slug] = entry
            if pk:
                bridge[pk] = {"side": "hit", "headline": _equiv_headline(t, "hit"), "name": v["name"]}
                pk_to_cs.setdefault(pk, {"slug": slug, "year": v.get("year"), "side": "hit"})
        for slug_norm, v in cs_p.items():
            stuff_wt = (cs_stuff.get((str(v.get("pitcher_id")), v.get("year")))
                        if cs_stuff else None)
            t = _translate_pitcher(v, F, stuff_wt)
            if not t:
                continue
            # The pitcher frontend slug is slugify(name-pitcher_id) (it disambiguates
            # same-named arms), so key pitcher translations the same way or the
            # client-side T[pitcher.slug] lookup misses and the board renders empty.
            slug = slugify_cs("{}-{}".format(v["name"], v.get("pitcher_id")))
            if slug not in translations:
                entry = {"side": "pit", "single_a": t}
                pk = draft_keys.get(slug_norm)
                if pk and pk in box_pit:
                    entry["box"] = box_pit[pk]
                    n_box += 1
                translations[slug] = entry
            pk = draft_keys.get(slug_norm)
            if pk and pk not in bridge:
                bridge[pk] = {"side": "pit", "headline": _equiv_headline(t, "pit"), "name": v["name"]}
            if pk:
                pk_to_cs.setdefault(pk, {"slug": slug, "year": v.get("year"), "side": "pit"})
        # CollegeSavant-universe NCAA box scores (tracked players who are NOT
        # draft prospects), attached by slug where we have no draft-prospect box.
        # NCAA bb%/k% arrive as percentages; rescale to the decimal convention the
        # player-page panel uses. woba/wRC+ are not computable from box rows.
        try:
            from storage import load_collegesavant_box_scores
            cs_box = {}
            for r in load_collegesavant_box_scores():
                cs_box.setdefault((r["player_slug"], r["side"]), r)

            for slug, entry in translations.items():
                if entry.get("box") or entry.get("side") != "hit":
                    continue
                r = cs_box.get((slug, "batting"))
                if r:
                    entry["box"] = _ncaa_box_to_display(r.get("payload"), r.get("season"),
                                                        r.get("school"))
        except Exception:
            pass

        # Compact backtest summary for the frontend "how accurate is this" panel.
        eval_summary = {k: {"r2": f.get("r2"), "n": f.get("n"), "band_sd": f.get("band_sd"),
                            "mae": (f.get("loo") or {}).get("mae"),
                            "null_mae": (f.get("loo") or {}).get("null_mae"),
                            "skill_se": (f.get("loo") or {}).get("skill_se"),
                            "coverage": (f.get("loo") or {}).get("p10_p90_coverage")}
                        for k, f in F.items()}
        payload = {"generated_from": "college_translation.build", "translations": translations,
                   "eval": eval_summary, "low_signal_r2": LOW_SIGNAL_R2,
                   "caveat": eval_doc["caveat"]}
        (out_dir / "collegesavant_translation.js").write_text(
            "window.CS_TRANSLATION = " + json.dumps(payload) + ";\n", encoding="utf-8")

        # The reverse direction: draft prospects (each year) carried into
        # CollegeSavant by the college box scores we already hold, FV-ranked.
        prospects = _draft_prospect_export(con, box_hit, box_pit, pk_to_cs, F)
        prospects["generated_from"] = "college_translation.build"
        (out_dir / "collegesavant_draft_prospects.js").write_text(
            "window.CS_DRAFT_PROSPECTS = " + json.dumps(prospects) + ";\n", encoding="utf-8")

        # PROSPX bridge: keyed by draft prospect player_key. PROSPX lazily merges
        # it onto its draft records. Additive; an absent/empty file changes nothing.
        (out_dir / "collegesavant_milb_equiv.json").write_text(
            json.dumps({"generated_from": "college_translation.build",
                        "label": "Projected Single-A (CollegeSavant)",
                        "caveat": eval_doc["caveat"],
                        "by_player_key": bridge}, indent=1), encoding="utf-8")
        eval_doc["bridge_count"] = len(bridge)
        return eval_doc


if __name__ == "__main__":
    doc = build()
    print(json.dumps({"factors": {k: {kk: v[kk] for kk in ("slope", "r2", "n", "band_sd", "loo") if kk in v}
                                  for k, v in doc["factors"].items()},
                      "matched_pairs": doc["matched_pairs"]}, indent=1))
