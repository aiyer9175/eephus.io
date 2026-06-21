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
import re
from pathlib import Path

import storage

ROOT = Path(__file__).parent
CS = ROOT / "collegesavant"

# Pitcher Single-A statlines carry K/9 + BB/9, not K% / BB%. Convert with a
# standard batters-faced-per-9-innings estimate so the pitcher translation runs
# in the same K% / BB% units as the college side and the hitter model.
BF_PER_9 = 38.0

# Slope shrinkage pseudo-count: predicted slope = ols_slope * n / (n + K). Pulls
# thin / weak fits toward pure regression-to-the-mean. K=20 keeps a strong n=77
# fit near its OLS slope while heavily damping a 30-pair cell.
SLOPE_SHRINK_K = 20

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

    chip("Proj A K%", sa.get("k_pct"), "pct", None)
    chip("Proj A BB%", sa.get("bb_pct"), "pct",
         "low confidence" if (sa.get("bb_pct") or {}).get("low_confidence") else None)
    if side == "hit":
        chip("Proj A OPS", sa.get("ops"), "dec", "experimental")
    return chips


def load_single_a(con, key_name: dict):
    """Return {slug: {hit:{k_pct,bb_pct,ops}, pit:{k_pct,bb_pct}}} from the
    earliest qualifying Single-A (A / A+) season on file. Pitcher K%/BB% are
    derived from K/9, BB/9 via BF_PER_9. Pitcher seasons gated at >= 20 IP."""
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
            if d.get("k_per_9") is None:
                continue
            try:
                ip = float(d.get("ip") or 0)
            except (TypeError, ValueError):
                ip = 0.0
            if ip < 20:
                continue
            k9 = float(d["k_per_9"])
            bb9 = d.get("bb_per_9")
            row = (season, k9 / BF_PER_9 * 100.0,
                   (float(bb9) / BF_PER_9 * 100.0) if bb9 is not None else None)
            pit.setdefault(slug, []).append(row)
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
    abs_err, inside = [], 0
    for i in range(n):
        train = items[:i] + items[i + 1:]
        f = _fit([a for a, _ in train], [b for _, b in train])
        if not f:
            continue
        x, y = items[i]
        pred = _predict(f, x)
        abs_err.append(abs(y - pred))
        lo, hi = pred - 1.2816 * f["band_sd"], pred + 1.2816 * f["band_sd"]
        if lo <= y <= hi:
            inside += 1
    return {"mae": round(sum(abs_err) / len(abs_err), 3),
            "p10_p90_coverage": round(inside / len(abs_err), 3),
            "target_coverage": 0.80, "n": len(abs_err)}


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
        out["k_pct"] = _band(_predict(F["hit_k"], v["k_pct"]), F["hit_k"]["band_sd"], 0, 60)
    if v.get("bb_pct") is not None and F.get("hit_bb"):
        b = _band(_predict(F["hit_bb"], v["bb_pct"]), F["hit_bb"]["band_sd"], 0, 30)
        b["low_confidence"] = F["hit_bb"]["r2"] < 0.10
        out["bb_pct"] = b
    if v.get("xwoba") is not None and F.get("hit_ops"):
        o = _band(_predict(F["hit_ops"], v["xwoba"]), F["hit_ops"]["band_sd"], 0.3, 1.2, ndigits=3)
        o["experimental"] = True
        out["ops"] = o
    return out


def _translate_pitcher(v, F):
    out = {}
    if v.get("k_pct") is not None and F.get("pit_k"):
        out["k_pct"] = _band(_predict(F["pit_k"], v["k_pct"]), F["pit_k"]["band_sd"], 0, 50)
    if v.get("bb_pct") is not None and F.get("pit_bb"):
        b = _band(_predict(F["pit_bb"], v["bb_pct"]), F["pit_bb"]["band_sd"], 0, 25)
        b["low_confidence"] = F["pit_bb"]["r2"] < 0.10
        out["bb_pct"] = b
    return out


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

        eval_doc = {
            "method": "matched-pair regression-to-the-mean (college -> Single-A), "
                      "our-data join: CollegeSavant name -> draft_players -> statlines (A/A+)",
            "bf_per_9": BF_PER_9, "slope_shrink_k": SLOPE_SHRINK_K,
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

        # Key the per-player sidecar by the frontend slug (slugify of the raw
        # "Last, First" name) so each CollegeSavant player looks up their own.
        # Also build the PROSPX BRIDGE sidecar keyed by the matching draft
        # prospect's player_key, so PROSPX can merge a Single-A-equivalent block
        # onto its draft records with no rebuild. Additive and safe-when-empty.
        draft_keys = _draft_keys(con)
        translations, bridge = {}, {}
        for slug_norm, v in cs_h.items():
            t = _translate_hitter(v, F)
            if not t:
                continue
            translations[slugify_cs(v["name"])] = {"side": "hit", "single_a": t}
            pk = draft_keys.get(slug_norm)
            if pk:
                bridge[pk] = {"side": "hit", "headline": _equiv_headline(t, "hit"),
                              "name": v["name"]}
        for slug_norm, v in cs_p.items():
            t = _translate_pitcher(v, F)
            if not t:
                continue
            translations.setdefault(slugify_cs(v["name"]), {"side": "pit", "single_a": t})
            pk = draft_keys.get(slug_norm)
            if pk and pk not in bridge:
                bridge[pk] = {"side": "pit", "headline": _equiv_headline(t, "pit"),
                              "name": v["name"]}
        payload = {"generated_from": "college_translation.build", "translations": translations,
                   "caveat": eval_doc["caveat"]}
        (out_dir / "collegesavant_translation.js").write_text(
            "window.CS_TRANSLATION = " + json.dumps(payload) + ";\n", encoding="utf-8")

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
