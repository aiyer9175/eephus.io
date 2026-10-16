#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""xhem_ppa_shrink_lab: the xHEM+ P/PA walk-shrink forward test (xhem_ppa_shrink_v1).

Registration: docs/ewar/XHEM_PPA_SHRINK_GATE.md, committed alone before any number
(task XHEM_PPA_SHRINK_TEST, owner decision EW3-32 item 2, "Run it (owner override)":
the pitch-economy lab's trigger (h) missed by 0.0002 and the owner overrode it).

  N  the NULL comparator: the unmodified xHEM+ (served construction, unrounded).
  V  the variant: shrunk P/PA sets the unintentional-walk shrink target, the shrunk
     walk rate replaces the raw one inside Savant xwOBA, then the xHEM+ ratio scale.
  P  the permuted-P/PA twin (must fail).
  M  reported only: the same walk shrink toward the league (b = 0).

Harness v2 (tools/plus_lab_harness.py): v1 pooled raw target with the iid paired
bootstrap, v2 within-outcome-season z target with the player-clustered,
season-stratified bootstrap; B 2000, seed 20261015; MDE95 = 1.645 * bootstrap sd.

Never: a 2026 row, an FV cell, a betting artifact, price or game result.

Run:
  python tools/xhem_ppa_shrink_lab.py --dry-run --out DIR   fixtures (nulls, planted, null)
  python -u tools/xhem_ppa_shrink_lab.py --run              THE RUN (writes data/_labs/)
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hem_plus  # noqa: E402
import plus_lab_harness as plh  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "data" / "_labs" / "xhem_ppa_shrink_eval.json"
GATE_DOC = "docs/ewar/XHEM_PPA_SHRINK_GATE.md"

# ---- frozen by the registration (parts 1 to 5); a change is a new registration ---- #
PRED_YEARS = (2016, 2017, 2018, 2021, 2022, 2023, 2024)
SAVANT_YEARS = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
FIT_YEARS = (2013, 2014, 2015)
PAIR_MIN_PA = 200.0
SERVED_MIN_PA = 100.0          # hitter_export._join_xhem_plus _XHEM_MIN_PA
FIT_MIN_PA = 300.0
FIT_MIN_N = 300
K_PPA = 100.0                  # pitch-economy lab part 4 prior P/PA shrink
K_UBB = 120.0                  # hem_plus.K_UBB
GAIN = hem_plus.HEM_SPREAD_GAIN
B = 2000
SEED = 20261015
PERM_SEED = 20261018
MDE_Z = 1.645
ARMS = ("N", "V", "P", "M")
CONTROLS = ("V", "P", "M")

TARGET_V1 = "Savant wOBA in Y+1 (raw, pooled across seasons)"
TARGET_V2 = "Savant wOBA in Y+1"

OVERRIDE = {
    "decision": "EW3-32 item 2 (owner 2026-10-15)",
    "verbatim": "Run it (owner override)",
    "what_was_overridden": ("docs/ewar/PITCH_ECONOMY_LAB.md part 8 trigger (h): partial Spearman "
                            "of P/PA(Y) with wOBA(Y+1) after BB%, K% and xwOBA(Y) read +0.0563, "
                            "CI95 -0.0002 to +0.1161, a miss by 0.0002"),
    "scope": "the trigger only; every rule of the registration binds as written",
}


class LabRefused(RuntimeError):
    pass


def _r(x, d=6):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, d) if math.isfinite(v) else None


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


# =========================================================================== #
# loaders (caches only; nothing is fetched)
# =========================================================================== #
def load_savant(year: int) -> dict:
    """{mlbam: (woba, est_woba, pa)} from the cached Savant expected-statistics
    leaderboard. A row with any missing field is skipped."""
    if int(year) >= 2026:
        raise LabRefused("2026 never enters this test")
    path = CACHE / "savant_mlb" / f"expected_batter_{int(year)}.csv"
    if not path.exists():
        raise LabRefused(f"missing Savant cache {path.name}")
    out = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]), float(r["pa"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def lines_from_splits(splits) -> dict:
    out = {}
    for s in splits:
        st = s.get("stat") or {}
        try:
            pid = int(s["player"]["id"])
        except (TypeError, ValueError, KeyError):
            continue
        row = {"pa": _num(st.get("plateAppearances")), "pitches": _num(st.get("numberOfPitches")),
               "ab": _num(st.get("atBats")), "bb": _num(st.get("baseOnBalls")),
               "ibb": _num(st.get("intentionalWalks")), "hbp": _num(st.get("hitByPitch")),
               "sf": _num(st.get("sacFlies")),
               "pos": (s.get("position") or {}).get("abbreviation")}
        if pid not in out or row["pa"] > out[pid]["pa"]:
            out[pid] = row
    return out


def load_lines(year: int) -> dict:
    if int(year) >= 2026:
        raise LabRefused("2026 never enters this test")
    path = CACHE / f"fa_statsapi_hitting_{int(year)}.json"
    if not path.exists():
        raise LabRefused(f"missing StatsAPI cache {path.name}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    return lines_from_splits((doc.get("stats") or [{}])[0].get("splits") or [])


def load_w_ubb(year: int) -> float:
    import league_constants as lc  # noqa: PLC0415
    c = lc.constants(int(year)) or {}
    if c.get("season") != int(year):
        raise LabRefused(f"league constants for {year} are not that season's own")
    return float(c["woba_weights"]["ubb"])


# =========================================================================== #
# the construction (registration part 3)
# =========================================================================== #
def ubb(line: dict) -> float:
    return max(0.0, line["bb"] - line["ibb"])


def denom(line: dict) -> float:
    return line["ab"] + line["bb"] - line["ibb"] + line["sf"] + line["hbp"]


def line_ok(line) -> bool:
    return bool(line) and line["pa"] > 0 and line["pitches"] > 0 and denom(line) > 0


def league(lines: dict) -> dict:
    """L (pitches per PA) and lgBB (uBB per wOBA denominator) over every row with PA
    above 0 and pitches above 0."""
    p = pa = u = d = 0.0
    for ln in lines.values():
        if ln["pa"] > 0 and ln["pitches"] > 0:
            p += ln["pitches"]
            pa += ln["pa"]
            u += ubb(ln)
            d += max(0.0, denom(ln))
    if pa <= 0 or d <= 0:
        raise LabRefused("empty league")
    return {"L": p / pa, "lgBB": u / d}


def fit_slope(lines_by_year: dict) -> dict:
    """b: the pooled within-season least-squares slope of r_raw on P/PA over hitter-
    seasons with PA >= 300, position players only."""
    sxy = sxx = 0.0
    n = 0
    by = {}
    for y in sorted(lines_by_year):
        pts = []
        for ln in lines_by_year[y].values():
            if ln.get("pos") == "P" or ln["pa"] < FIT_MIN_PA or not line_ok(ln):
                continue
            pts.append((ln["pitches"] / ln["pa"], ubb(ln) / denom(ln)))
        if len(pts) < 2:
            continue
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        a = sum((x - mx) * (yv - my) for x, yv in pts)
        c = sum((x - mx) ** 2 for x, _ in pts)
        sxy += a
        sxx += c
        n += len(pts)
        by[str(y)] = {"n": len(pts), "slope": _r(a / c if c else None)}
    b = sxy / sxx if sxx > 0 else float("nan")
    if not math.isfinite(b) or n < FIT_MIN_N:
        raise LabRefused(f"slope fit refused: b={b!r}, n={n}")
    return {"b": b, "n": n, "by_season": by}


def sppa(line: dict, L: float) -> float:
    return (line["pitches"] + K_PPA * L) / (line["pa"] + K_PPA)


def shrunk_xwoba(xw: float, line: dict, s: float, lg: dict, b: float, w_ubb: float) -> float:
    """xw' = est_woba + w_ubb * (r_shr - r_raw), r_shr shrunk toward T(sPPA)."""
    d = denom(line)
    r_raw = ubb(line) / d
    t = max(0.0, lg["lgBB"] + b * (s - lg["L"]))
    r_shr = (ubb(line) + K_UBB * t) / (d + K_UBB)
    return xw + w_ubb * (r_shr - r_raw)


def xhem(xw: float, pool: float) -> float:
    return 100.0 + GAIN * (100.0 * xw / pool - 100.0)


def season_arms(sav: dict, lines: dict, w_ubb: float, b: float, perm_rng: random.Random) -> dict:
    """{arm: {mlbam: unrounded xHEM+}} over the season's served pool, plus counts.
    The P arm's sPPA is the season's served-pool sPPA list shuffled (hitters ordered
    by MLBAM id). Every arm re-anchors on its own Savant-PA-weighted pool mean."""
    lg = league(lines)
    pool_ids = sorted(m for m, (_w, x, pa) in sav.items() if pa >= SERVED_MIN_PA and x > 0)
    joined = [m for m in pool_ids if line_ok(lines.get(m))]
    s_true = {m: sppa(lines[m], lg["L"]) for m in joined}
    perm_vals = [s_true[m] for m in joined]
    perm_rng.shuffle(perm_vals)
    s_perm = dict(zip(joined, perm_vals))
    xw = {"N": {}, "V": {}, "P": {}, "M": {}}
    for m in pool_ids:
        x = sav[m][1]
        xw["N"][m] = x
        if m in s_true:
            ln = lines[m]
            xw["V"][m] = shrunk_xwoba(x, ln, s_true[m], lg, b, w_ubb)
            xw["P"][m] = shrunk_xwoba(x, ln, s_perm[m], lg, b, w_ubb)
            xw["M"][m] = shrunk_xwoba(x, ln, s_true[m], lg, 0.0, w_ubb)
        else:
            for a in CONTROLS:
                xw[a][m] = x
    out = {}
    pools = {}
    for a in ARMS:
        num = sum(xw[a][m] * sav[m][2] for m in pool_ids)
        den = sum(sav[m][2] for m in pool_ids)
        pool = num / den if den else None
        if not pool:
            raise LabRefused("empty served pool")
        pools[a] = pool
        out[a] = {m: xhem(xw[a][m], pool) for m in pool_ids}
    return {"arms": out, "league": lg, "pool_means": pools, "served_pool": len(pool_ids),
            "served_pool_unjoined": len(pool_ids) - len(joined), "w_ubb": w_ubb}


# =========================================================================== #
# bootstrap with the draws kept (harness draw construction, asserted in run)
# =========================================================================== #
def iid_draws(series: dict, tgt: list, boot: int, seed: int) -> dict:
    n = len(tgt)
    rng = random.Random(seed)
    rhos = {a: [] for a in series}
    for _ in range(boot):
        samp = [rng.randrange(n) for _ in range(n)]
        st = [tgt[i] for i in samp]
        rr = {a: plh.spearman([series[a][i] for i in samp], st) for a in series}
        if any(v is None for v in rr.values()):
            continue
        for a in series:
            rhos[a].append(rr[a])
    return rhos


def cluster_draws(series: dict, tgt: list, players: list, strata_key: list,
                  boot: int, seed: int) -> dict:
    by_player: dict = {}
    first: dict = {}
    for i, p in enumerate(players):
        by_player.setdefault(p, []).append(i)
        s = strata_key[i]
        if p not in first or s < first[p]:
            first[p] = s
    strata: dict = {}
    for p, s in first.items():
        strata.setdefault(s, []).append(p)
    strata = {s: sorted(strata[s], key=str) for s in sorted(strata)}
    rng = random.Random(seed)
    rhos = {a: [] for a in series}
    for _ in range(boot):
        idx: list = []
        for s in strata:
            pl = strata[s]
            m = len(pl)
            for _ in range(m):
                idx.extend(by_player[pl[rng.randrange(m)]])
        st = [tgt[i] for i in idx]
        rr = {a: plh.spearman([series[a][i] for i in idx], st) for a in series}
        if any(v is None for v in rr.values()):
            continue
        for a in series:
            rhos[a].append(rr[a])
    return rhos


def _sd(xs):
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def gap_cell(series: dict, tgt: list, rhos: dict, arm: str) -> dict:
    draws = [a - b for a, b in zip(rhos[arm], rhos["N"])]
    c = plh.ci(draws)
    sd = _sd(draws)
    rp = plh.spearman(series[arm], tgt)
    rb = plh.spearman(series["N"], tgt)
    return {
        "rho_arm": _r(rp, 4), "rho_null": _r(rb, 4),
        "gap_point": _r(rp - rb if rp is not None and rb is not None else None, 4),
        "gap_ci": c,
        "gap_sd_bootstrap": _r(sd, 4),
        "mde95_in_run": _r(MDE_Z * sd, 4) if sd else None,
        "share_draws_at_or_below_0": _r(sum(1 for d in draws if d <= 0) / len(draws), 4) if draws else None,
        "n_boot_draws": len(draws),
        "lo95_gt_0": bool(c and c["lo95"] > 0),
    }


def verdict(cells: dict) -> dict:
    """Registration part 6. cells[conv][arm] = gap_cell."""
    v1 = cells["v1"]["V"]["lo95_gt_0"]
    v2 = cells["v2"]["V"]["lo95_gt_0"]
    twin_fails = (not cells["v1"]["P"]["lo95_gt_0"]) and (not cells["v2"]["P"]["lo95_gt_0"])
    if v1 and v2 and twin_fails:
        status = "VALIDATED"
    elif v1 and v2:
        status = "VOID"
    elif (v1 or v2) and twin_fails:
        status = "PROVISIONAL"
    else:
        status = "NOT VALIDATED"
    return {"status": status, "v1_lo95_gt_0": v1, "v2_lo95_gt_0": v2, "twin_fails": twin_fails,
            "holm": {"k": 1, "family": ["V vs N"],
                     "note": "k = 1, so Holm leaves the 95 percent interval as it is"},
            "builds_dark": status == "VALIDATED"}


# =========================================================================== #
# the core (pure given its inputs)
# =========================================================================== #
def core(savant: dict, lines: dict, w_ubb: dict, fit_lines: dict, *, pred_years=PRED_YEARS,
         boot: int = B, seed: int = SEED, perm_seed: int = PERM_SEED, log=print,
         assert_harness: bool = True) -> dict:
    t0 = time.time()
    fit = fit_slope(fit_lines)
    b = fit["b"]
    log(f"slope b = {b:.6f} on n = {fit['n']} hitter-seasons ({', '.join(sorted(fit['by_season']))})")

    perm_rng = random.Random(perm_seed)
    seasons = {}
    for y in sorted(pred_years):
        seasons[y] = season_arms(savant[y], lines[y], w_ubb[y], b, perm_rng)

    series = {a: [] for a in ARMS}
    tgt, mids, pys, oys = [], [], [], []
    dropped_no_line = dropped_partial = 0
    for y in sorted(pred_years):
        cur, nxt = savant[y], savant.get(y + 1) or {}
        arms = seasons[y]["arms"]
        for m in sorted(cur):
            w0, x0, pa0 = cur[m]
            nn = nxt.get(m)
            if nn is None or pa0 < PAIR_MIN_PA or nn[2] < PAIR_MIN_PA:
                continue
            if not plh.season_complete(y + 1):
                dropped_partial += 1
                continue
            if not line_ok(lines[y].get(m)) or m not in arms["N"]:
                dropped_no_line += 1
                continue
            for a in ARMS:
                series[a].append(arms[a][m])
            tgt.append(nn[0])
            mids.append(m)
            pys.append(y)
            oys.append(y + 1)
    n = len(tgt)
    log(f"pairs: {n} ({len(set(mids))} hitters); dropped {dropped_no_line} without a StatsAPI "
        f"line, {dropped_partial} with a partial outcome season")
    if n < 20:
        raise LabRefused(f"too few pairs ({n})")
    tgt_v2 = plh.zscore_within(oys, tgt)

    rhos_v1 = iid_draws(series, tgt, boot, seed)
    rhos_v2 = cluster_draws(series, tgt_v2, mids, pys, boot, seed)
    cells = {"v1": {a: gap_cell(series, tgt, rhos_v1, a) for a in CONTROLS},
             "v2": {a: gap_cell(series, tgt_v2, rhos_v2, a) for a in CONTROLS}}
    if assert_harness:
        h1 = plh.iid_boot_gaps(series["V"], {"N": series["N"]}, tgt, boot, seed)["N"]
        h2 = plh.cluster_boot_gaps(series["V"], {"N": series["N"]}, tgt_v2, mids, pys, boot, seed)["N"]
        if h1 != cells["v1"]["V"]["gap_ci"] or h2 != cells["v2"]["V"]["gap_ci"]:
            raise LabRefused(f"draws disagree with the harness: {h1} vs {cells['v1']['V']['gap_ci']}, "
                             f"{h2} vs {cells['v2']['V']['gap_ci']}")
        log("harness reproduction: the V minus N intervals match plus_lab_harness exactly")

    by_season = {}
    for y in sorted(set(pys)):
        idx = [i for i in range(n) if pys[i] == y]
        tt = [tgt[i] for i in idx]
        by_season[str(y)] = {"pairs": len(idx), **{
            a: _r(plh.spearman([series[a][i] for i in idx], tt), 4) for a in ARMS}}
    dv = [series["V"][i] - series["N"][i] for i in range(n)]
    desc = {
        "rank_agreement_V_N": _r(plh.spearman(series["V"], series["N"]), 4),
        "rank_agreement_P_N": _r(plh.spearman(series["P"], series["N"]), 4),
        "rank_agreement_M_N": _r(plh.spearman(series["M"], series["N"]), 4),
        "V_minus_N_xhem_points_sd": _r(_sd(dv), 3),
        "V_minus_N_xhem_points_max_abs": _r(max(abs(d) for d in dv), 3),
    }
    ver = verdict(cells)
    seasons_out = {str(y): {"league_ppa": _r(s["league"]["L"]), "league_ubb_rate": _r(s["league"]["lgBB"]),
                            "w_ubb": s["w_ubb"], "served_pool": s["served_pool"],
                            "served_pool_unjoined": s["served_pool_unjoined"],
                            "pool_means": {a: _r(v) for a, v in s["pool_means"].items()}}
                   for y, s in seasons.items()}
    return {
        "slope_fit": {"b": _r(b, 8), "n": fit["n"], "by_season": fit["by_season"],
                      "seasons": list(FIT_YEARS)},
        "seasons": seasons_out,
        "pairs": {"n": n, "hitters": len(set(mids)),
                  "by_predictor_season": {str(y): pys.count(y) for y in sorted(set(pys))},
                  "dropped_no_statsapi_line": dropped_no_line,
                  "dropped_partial_outcome": dropped_partial,
                  "cluster": plh.cluster_summary(mids, pys)},
        "results_by_convention": cells,
        "rho_by_predictor_season": by_season,
        "descriptive": desc,
        "verdict": ver,
        "runtime_seconds": round(time.time() - t0, 1),
    }


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def payload_of(res: dict, *, fixture: str | None = None) -> dict:
    return {
        "lab": "xhem_ppa_shrink_v1",
        "registration": GATE_DOC,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "git_head": _git_head(),
        "fixture": fixture,
        "override": OVERRIDE,
        "frozen": {"pred_years": list(PRED_YEARS), "pair_min_pa": PAIR_MIN_PA,
                   "served_min_pa": SERVED_MIN_PA, "k_ppa": K_PPA, "k_ubb": K_UBB,
                   "gain": GAIN, "fit_min_pa": FIT_MIN_PA, "boot": B, "seed": SEED,
                   "perm_seed": PERM_SEED, "mde_z": MDE_Z},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        **res,
    }


def run(out: Path = OUT, *, log=print) -> dict:
    if plh.season_complete_override():
        raise LabRefused("a season-complete override is set; the registration forbids it")
    if K_UBB != hem_plus.K_UBB:
        raise LabRefused("K_UBB no longer matches hem_plus.K_UBB")
    fit_lines = {y: load_lines(y) for y in FIT_YEARS}
    savant = {y: load_savant(y) for y in SAVANT_YEARS}
    lines = {y: load_lines(y) for y in PRED_YEARS}
    w = {y: load_w_ubb(y) for y in PRED_YEARS}
    res = core(savant, lines, w, fit_lines, log=log)
    payload = payload_of(res)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    log(f"wrote {out}")
    return payload


# =========================================================================== #
# fixtures (registration part 7)
# =========================================================================== #
def fixture(kind: str, *, n_players: int = 500, seed: int = 7) -> tuple:
    """Synthetic seasons. kind: 'planted' (P/PA carries walk talent, the outcome
    carries walk talent), 'null' (P/PA unrelated to walks) or 'nulls' (planted plus
    missing lines, zero pitches, blank Savant rows and one-season hitters)."""
    rng = random.Random(seed)
    players = []
    for i in range(n_players):
        t = min(0.2, max(0.02, rng.gauss(0.08, 0.03)))
        c = rng.gauss(0.24, 0.008)
        players.append((100000 + i, t, c))
    years = sorted(set(FIT_YEARS) | set(SAVANT_YEARS))
    savant = {y: {} for y in SAVANT_YEARS}
    lines = {y: {} for y in years}
    for y in years:
        for k, (m, t, c) in enumerate(players):
            if kind == "nulls" and k % 37 == 0 and y != 2016:
                continue                       # a hitter in one season only
            pa = float(rng.randint(150, 650))
            hbp = float(round(pa * 0.01))
            sf = float(round(pa * 0.008))
            ibb = float(rng.randint(0, 3))
            u = float(sum(1 for _ in range(int(pa)) if rng.random() < t))
            bb = u + ibb
            ab = pa - bb - hbp - sf
            if kind == "null":
                ppa = rng.gauss(3.85, 0.15)
            else:
                ppa = 3.2 + 8.0 * t + rng.gauss(0.0, 0.02)
            pitches = round(pa * ppa)
            ln = {"pa": pa, "pitches": float(pitches), "ab": ab, "bb": bb, "ibb": ibb,
                  "hbp": hbp, "sf": sf, "pos": "RF"}
            if kind == "nulls" and k % 23 == 0:
                ln["pitches"] = 0.0           # a line without pitches
            if not (kind == "nulls" and k % 29 == 0):
                lines[y][m] = ln               # some hitters have no StatsAPI line
            if y in savant:
                d = denom(ln)
                xw = c + 0.69 * (u / d) + rng.gauss(0.0, 0.004)
                wo = xw + rng.gauss(0.0, 0.01)
                if kind == "nulls" and k % 31 == 0:
                    continue                   # a blank Savant row
                savant[y][m] = (wo, xw, pa)
    w = {y: 0.69 for y in PRED_YEARS}
    fit_lines = {y: lines[y] for y in FIT_YEARS}
    return savant, {y: lines[y] for y in PRED_YEARS}, w, fit_lines


def dry_run(out_dir: Path, *, boot: int = 200, log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for kind in ("nulls", "planted", "null"):
        sav, lines, w, fit_lines = fixture(kind)
        res = core(sav, lines, w, fit_lines, boot=boot, log=log)
        pay = payload_of(res, fixture=kind)
        (out_dir / f"dry_run_{kind}.json").write_text(json.dumps(pay, indent=1) + "\n",
                                                       encoding="utf-8")
        cv = res["results_by_convention"]
        summary[kind] = {"b": res["slope_fit"]["b"], "pairs": res["pairs"]["n"],
                         "V_v1": cv["v1"]["V"]["gap_ci"], "V_v2": cv["v2"]["V"]["gap_ci"],
                         "P_v1": cv["v1"]["P"]["gap_ci"], "status": res["verdict"]["status"]}
        log(f"dry run {kind}: {json.dumps(summary[kind])}")
    planted = summary["planted"]
    if not (planted["V_v1"]["lo95"] > 0 and planted["V_v2"]["lo95"] > 0):
        raise LabRefused("planted recovery failed: V does not beat N on the planted fixture")
    log("planted recovery: V beats N under v1 and v2 on the planted fixture")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.dry_run:
        if a.out is None:
            ap.error("--dry-run needs --out DIR")
        dry_run(a.out)
        return 0
    payload = run()
    print(json.dumps({"verdict": payload["verdict"],
                      "v1": payload["results_by_convention"]["v1"],
                      "v2": payload["results_by_convention"]["v2"],
                      "slope_fit": payload["slope_fit"], "pairs": payload["pairs"]["n"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
