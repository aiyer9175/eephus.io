# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Per-hand HEM+ platoon-ratio shrink fit (estimator platoon_ratio_v1).

Pre-registered in docs/diamond-betting.md section 5e ("The per-hand estimator
platoon_ratio_v1") and the hem_plus.py module docstring BEFORE this file ran:

  data    StatsAPI statSplits (sitCodes vl and vr, group hitting, gameType R,
          playerPool All) and sports/1/players batSide, seasons 2016, 2017 and
          2018 only. Raw responses are cached under .cache/hem_split_ratio_fit/
          so the fit reruns offline byte for byte.
  sample  per hitter-season: q = wOBA_vsL / wOBA_vsR - 1 and
          n = d_L * d_R / (d_L + d_R) (wOBA denominators), via the same
          hem_plus helpers the served estimator uses.
  rule    positional_fit.fit_signal (the DEM+ precedent): pairs are the same
          hitter in consecutive seasons (2016 to 2017, 2017 to 2018) on the same
          bat side with n >= 50 both years; r = Pearson(q_Y, q_Y+1) clamped to
          [0.05, 0.95]; hm = mean over pairs of 2 / (1/n_Y + 1/n_Y+1);
          K = hm * (1 - r) / r, rounded to the nearest 10. A side with fewer
          than 30 pairs takes the all-hitter K.
  mu      the frozen league ratio by side: pooled wOBA_vsL / pooled wOBA_vsR
          minus 1 over every 2016-2018 hitter-season of that side with both
          lines.

Nothing from 2019 on is read, no game outcome is read, and this is run once: the
output is frozen into hem_plus.K_PLATOON / MU_PLATOON_FROZEN, and a rerun that
disagrees is reported as drift, never silently re-frozen.

Run: python tools/hem_split_ratio_lab.py   (writes .cache/hem_split_ratio_fit/fit.json)
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))

import hem_plus as H  # noqa: E402

FIT_SEASONS = (2016, 2017, 2018)
FIT_MIN_N = 50.0
FIT_MIN_PAIRS = 30
R_CLAMP = (0.05, 0.95)
CACHE = ROOT / ".cache" / "hem_split_ratio_fit"
OUT = CACHE / "fit.json"


def _guard(season: int) -> int:
    if int(season) not in FIT_SEASONS:
        raise ValueError(f"season {season} is outside the pre-registered fit window "
                         f"{FIT_SEASONS}")
    return int(season)


def _cached(name: str, path: str, params: dict) -> dict:
    p = CACHE / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    import bullpen_export as be
    data = be._get_json(path, params)
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data


def load_season(season: int) -> tuple[dict, dict]:
    """({'L': {mlbam: counts}, 'R': {...}}, {mlbam: batSide}) for one fit season."""
    season = _guard(season)
    lines: dict = {}
    for hand, sit in (("L", "vl"), ("R", "vr")):
        data = _cached(f"{season}_{sit}.json", "stats", {
            "stats": "statSplits", "sitCodes": sit, "group": "hitting",
            "season": season, "gameType": "R", "sportId": 1,
            "playerPool": "All", "limit": 5000})
        rows = {}
        for sp in ((data.get("stats") or [{}])[0].get("splits") or []):
            pid = (sp.get("player") or {}).get("id")
            st = sp.get("stat")
            if pid and isinstance(st, dict):
                rows[int(pid)] = st
        if not rows:
            raise RuntimeError(f"no {sit} rows for {season}")
        lines[hand] = rows
    ppl = _cached(f"{season}_players.json", "sports/1/players", {"season": season})
    bats = {int(p["id"]): (p.get("batSide") or {}).get("code")
            for p in (ppl.get("people") or []) if p.get("id")}
    return lines, bats


def observations(lines: dict, bats: dict) -> dict:
    """{mlbam: {'side', 'q', 'n'}} for hitters with both lines."""
    out = {}
    for mid in set(lines["L"]) & set(lines["R"]):
        q, n = H.platoon_ratio(H._line_hitter(lines["L"][mid]),
                               H._line_hitter(lines["R"][mid]))
        if q is None:
            continue
        out[mid] = {"side": H.platoon_side(bats.get(mid)), "q": q, "n": n}
    return out


def _pearson(xs, ys) -> float:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def fit(obs_by_season: dict) -> dict:
    pairs: dict = {s: [] for s in H.PLATOON_SIDES + ("ALL",)}
    for y in FIT_SEASONS[:-1]:
        a, b = obs_by_season[y], obs_by_season[y + 1]
        for mid in set(a) & set(b):
            o1, o2 = a[mid], b[mid]
            if o1["side"] != o2["side"] or o1["side"] == "ALL":
                continue
            if o1["n"] < FIT_MIN_N or o2["n"] < FIT_MIN_N:
                continue
            hm = 2.0 / (1.0 / o1["n"] + 1.0 / o2["n"])
            rec = (o1["q"], o2["q"], hm)
            pairs[o1["side"]].append(rec)
            pairs["ALL"].append(rec)
    out = {}
    for side, ps in pairs.items():
        row = {"n_pairs": len(ps)}
        if len(ps) >= 2:
            r_raw = _pearson([p[0] for p in ps], [p[1] for p in ps])
            r = min(max(r_raw, R_CLAMP[0]), R_CLAMP[1])
            hm = statistics.fmean(p[2] for p in ps)
            row.update({"r_raw": round(r_raw, 4), "r": round(r, 4),
                        "hm": round(hm, 1),
                        "k_fit": float(round(hm * (1.0 - r) / r / 10.0) * 10.0)})
        out[side] = row
    for side in H.PLATOON_SIDES:
        row = out[side]
        if row["n_pairs"] < FIT_MIN_PAIRS or "k_fit" not in row:
            row["k"] = out["ALL"].get("k_fit")
            row["k_source"] = f"ALL (under {FIT_MIN_PAIRS} pairs)"
        else:
            row["k"] = row["k_fit"]
            row["k_source"] = "own fit"
    out["ALL"]["k"] = out["ALL"].get("k_fit")
    out["ALL"]["k_source"] = "own fit"
    return out


def frozen_mu(lines_by_season: dict, bats_by_season: dict) -> dict:
    """Pooled 2016-2018 league ratio by side (each season's own batSide)."""
    acc = {s: [0.0, 0.0, 0.0, 0.0] for s in H.PLATOON_SIDES + ("ALL",)}
    for y in FIT_SEASONS:
        lines, bats = lines_by_season[y], bats_by_season[y]
        for mid in set(lines["L"]) & set(lines["R"]):
            nl, dl = H._woba_parts(H._line_hitter(lines["L"][mid]))
            nr, dr = H._woba_parts(H._line_hitter(lines["R"][mid]))
            if dl <= 0 or dr <= 0:
                continue
            for s in {H.platoon_side(bats.get(mid)), "ALL"}:
                a = acc[s]
                a[0] += nl
                a[1] += dl
                a[2] += nr
                a[3] += dr
    return {s: round((a[0] / a[1]) / (a[2] / a[3]) - 1.0, 4) for s, a in acc.items()}


def main() -> dict:
    lines_by, bats_by, obs_by = {}, {}, {}
    for y in FIT_SEASONS:
        lines_by[y], bats_by[y] = load_season(y)
        obs_by[y] = observations(lines_by[y], bats_by[y])
    res = {
        "estimator": H.SPLIT_ESTIMATOR,
        "fit_seasons": list(FIT_SEASONS),
        "rule": ("positional_fit.fit_signal: same-side consecutive-season pairs, "
                 f"n >= {FIT_MIN_N:g} both years, r clamped to {list(R_CLAMP)}, "
                 "K = hm (1 - r) / r rounded to 10, a side under "
                 f"{FIT_MIN_PAIRS} pairs takes ALL"),
        "n_hitter_seasons": {str(y): len(obs_by[y]) for y in FIT_SEASONS},
        "k": fit(obs_by),
        "mu_frozen": frozen_mu(lines_by, bats_by),
    }
    res["frozen_matches_module"] = {
        "k": {s: res["k"][s]["k"] == H.K_PLATOON.get(s) for s in res["k"]},
        "mu": {s: abs(res["mu_frozen"][s] - H.MU_PLATOON_FROZEN.get(s, 9)) < 5e-5
               for s in res["mu_frozen"]},
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    main()
