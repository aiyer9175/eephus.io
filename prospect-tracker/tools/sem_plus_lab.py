# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Starter-metric lab (Wave B2). Three pre-registered experiments
(docs/audit-2026-07/AUDIT_FINDINGS.md, section "Wave B2"):

  X-S1  SEM+ skill validation. SEM+ = starter-pool EB-shrunk FIP. GATE (ship):
        forward Spearman vs RA9(Y+1) BEATS ERA (bootstrap gap lo95 > 0) AND is
        not worse than raw FIP (gap lo95 >= -0.01). -> data/sem_plus_eval.json
        (also carries the X-S3 result).

  X-S2  3-year SEM+. IP-weighted trailing-3-season SEM+. GATE: forward Spearman
        vs RA9(Y+1) EXCEEDS single-season SEM+ on the SAME set (bootstrap gap
        lo95 >= 0). -> data/sem_plus_multiyear_eval.json (+ proposed_values for
        the current qualified pool, joined by starter_export like gmli_3yr).

  X-S3  "more than FIP": a ground-ball-adjusted HR expectation in the skill core.
        Ship the adjusted core ONLY if it beats plain FIP forward (gap lo95 >= 0);
        else keep plain FIP, record the loss ledger.

No leverage walk (starters are not leverage-deployed), so this is one StatsAPI
call per season plus a best-effort bref SwStr pull. All stochastic steps seeded.
Run: python tools/sem_plus_lab.py [--no-write] [--seasons 2018,2019,...]
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sem_plus  # noqa: E402
import starter_export as se  # noqa: E402
from rem_plus_backtest import _spearman, _ci, SEASONS as BT_SEASONS  # noqa: E402

DATA = ROOT / "data"
SEM_EVAL = DATA / "sem_plus_eval.json"
MULTI_EVAL = DATA / "sem_plus_multiyear_eval.json"

SEASONS = list(BT_SEASONS)         # 2018,2019,2021..2025 (ex-2020)
MIN_IP_Y = 50.0                    # qualified in the predictor year
MIN_IP_NEXT = 40.0                 # a real sample in the outcome year
BOOT = 2000
SEED = 20260703
TAG_MIN_SEASONS = 2
TAG_MIN_IP = 120.0                 # 3yr "established" bar (starters throw more)


def _r4(v):
    return None if v is None else round(v, 4)


def _raw_fip_starter(s: sem_plus.Starter):
    if s.ip <= 0:
        return None
    return (sem_plus.FIP_HR * s.hr + sem_plus.FIP_BBHBP * (s.bb + s.hbp)
            - sem_plus.FIP_K * s.so) / s.ip  # constant dropped (rank-invariant)


def load_season(y: int) -> dict:
    """MLBAM -> per-starter record for season Y's true-starter pool, carrying
    plain SEM+, the GB-adjusted candidate SEM+, and outcome RA9."""
    rows = se.load_season_pitching(y)
    if not rows:
        return {}
    swstr = se.load_bref_swstr(y)
    starters = se.build_starters(rows, swstr)
    pool = [s for s in starters if sem_plus.is_true_starter(s)]
    for s in pool:
        sem_plus.derive_rates(s)
    p_plain = sem_plus.build_pool(pool, gb_adjust=False)
    p_gb = sem_plus.build_pool(pool, gb_adjust=True)
    out = {}
    for s in pool:
        plain = sem_plus.sem_plus(s, p_plain, gb_adjust=False)
        if plain is None:
            continue
        # candidate SEM+ (GB-adjusted) scored on its own anchor
        f_gb = sem_plus.fip_skill(s, p_gb, gb_adjust=True)
        cand = (100.0 * p_gb.mean_fip / f_gb) if (f_gb and f_gb > 0) else None
        out[s.mlbam] = {
            "name": s.name, "team": s.team, "sem_plus": plain, "cand_sem": cand,
            "raw_fip": _raw_fip_starter(s), "era": s.rates.get("era"),
            "ra9": s.rates.get("ra9"), "ip": s.ip, "gs": s.gs, "tbf": s.tbf,
            "gb_pct": s.rates.get("gb_pct"), "ip_per_gs": s.rates.get("ip_per_gs"),
        }
    print(f"  {y}: {len(out)} starters scored")
    return out


def _boot_gap_ci(a_pred, b_pred, tgt, seed=SEED):
    """Seeded bootstrap CI on rho(a,tgt) - rho(b,tgt)."""
    n = len(tgt)
    rng = random.Random(seed)
    gaps = []
    for _ in range(BOOT):
        samp = [rng.randrange(n) for _ in range(n)]
        ra = _spearman([a_pred[i] for i in samp], [tgt[i] for i in samp])
        rb = _spearman([b_pred[i] for i in samp], [tgt[i] for i in samp])
        if ra is not None and rb is not None:
            gaps.append(ra - rb)
    return _ci(gaps)


def _multiyear_proposed(by_season: dict, cur_season: int) -> dict:
    window = [cur_season - 2, cur_season - 1, cur_season]
    cur = by_season.get(cur_season) or {}
    players, vals = {}, []
    for mid, row in cur.items():
        if row.get("sem_plus") is None:
            continue
        # qualified pool = the current-season qualified starters
        if (row.get("gs") or 0) < sem_plus.QUALIFY_MIN_GS and (row.get("ip") or 0) < sem_plus.QUALIFY_MIN_IP:
            continue
        num = den = 0.0
        seasons_used = 0
        for y in window:
            rec = (by_season.get(y) or {}).get(mid)
            if rec and rec.get("sem_plus") is not None and rec.get("ip"):
                num += rec["sem_plus"] * rec["ip"]; den += rec["ip"]; seasons_used += 1
        if not den:
            continue
        s3 = num / den
        tag = ("established" if seasons_used >= TAG_MIN_SEASONS and den >= TAG_MIN_IP
               else "provisional")
        players[str(mid)] = {
            "name": row.get("name"), "team": row.get("team"),
            "sem_plus_now": row.get("sem_plus"), "sem_plus_3yr": int(round(s3)),
            "seasons_used": seasons_used, "ip_total": round(den, 1), "tag": tag,
        }
        vals.append((str(mid), s3))
    n = len(vals)
    svals = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for s in svals if s < v)
        eq = sum(1 for s in svals if s == v)
        players[mid]["pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / n)) if n else None
    return {
        "season": cur_season, "window": window, "metric": "sem_plus_3yr",
        "display_name": "SEM+ (3yr)",
        "definition": (f"IP-weighted mean SEM+ over {window}. A steadier talent read than a "
                       f"single season. tag is 'established' with {TAG_MIN_SEASONS}+ seasons "
                       f"and {int(TAG_MIN_IP)}+ IP."),
        "n_with_value": len(players), "players": players,
    }


def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    for y in SEASONS + [max(SEASONS) + 1]:
        s = load_season(y)
        if s:
            by_season[y] = s
    print(f"  loaded {len(by_season)} seasons in {round(time.time()-t0,1)}s")

    # ---- X-S1 + X-S3 forward pairs ---- #
    sem, cand, negfip, negera, negra9n = [], [], [], [], []
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["ip"] or 0) < MIN_IP_Y or (b["ip"] or 0) < MIN_IP_NEXT:
                continue
            if a["raw_fip"] is None or a["era"] is None or b["ra9"] is None or a["cand_sem"] is None:
                continue
            sem.append(a["sem_plus"]); cand.append(a["cand_sem"])
            negfip.append(-a["raw_fip"]); negera.append(-a["era"]); negra9n.append(-b["ra9"])
    n1 = len(sem)
    rho_sem = _spearman(sem, negra9n)
    rho_fip = _spearman(negfip, negra9n)
    rho_era = _spearman(negera, negra9n)
    xs1_vs_era = _boot_gap_ci(sem, negera, negra9n)
    xs1_vs_fip = _boot_gap_ci(sem, negfip, negra9n)
    xs1_pass = bool(rho_sem is not None and xs1_vs_era and xs1_vs_era["lo95"] > 0
                    and xs1_vs_fip and xs1_vs_fip["lo95"] >= -0.01)
    rho_cand = _spearman(cand, negra9n)
    xs3_gap = _boot_gap_ci(cand, sem, negra9n)
    xs3_pass = bool(rho_cand is not None and rho_sem is not None
                    and rho_cand > rho_sem and xs3_gap and xs3_gap["lo95"] >= 0)

    # ---- X-S2: 3yr SEM+ forward pairs ---- #
    def _sem3(mid, y):
        num = den = 0.0
        su = 0
        for yy in (y - 2, y - 1, y):
            rec = (by_season.get(yy) or {}).get(mid)
            if rec and rec.get("sem_plus") is not None and rec.get("ip"):
                num += rec["sem_plus"] * rec["ip"]; den += rec["ip"]; su += 1
        return (num / den if den else None), su, den

    one3, three3, ra9_3 = [], [], []
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["ip"] or 0) < MIN_IP_Y or (b["ip"] or 0) < MIN_IP_NEXT or b["ra9"] is None:
                continue
            s3, su, ip3 = _sem3(mid, y)
            if s3 is None or su < TAG_MIN_SEASONS or ip3 < TAG_MIN_IP:
                continue
            one3.append(a["sem_plus"]); three3.append(s3); ra9_3.append(-b["ra9"])
    n3 = len(one3)
    rho_1yr = _spearman(one3, ra9_3)
    rho_3yr = _spearman(three3, ra9_3)
    xs2_gap = _boot_gap_ci(three3, one3, ra9_3) if n3 >= 30 else None
    xs2_pass = bool(rho_3yr is not None and rho_1yr is not None
                    and rho_3yr > rho_1yr and xs2_gap and xs2_gap["lo95"] >= 0)

    cur_season = max(by_season)
    dur = round(time.time() - t0, 1)
    common = {"generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
              "conventions": {"predictor_year": f"year Y qualified (IP>={int(MIN_IP_Y)})",
                              "target": f"-RA9 in year Y+1 (IP>={int(MIN_IP_NEXT)})",
                              "excluded": "2020 (60-game COVID season)"},
              "runtime_seconds": dur}

    sem_payload = dict(common)
    sem_payload.update({
        "experiment": "X-S1 (+ X-S3)", "model": "sem_plus",
        "n_forward_pairs": n1,
        "forward_spearman_vs_RA9_next": {
            "sem_plus": _r4(rho_sem), "raw_fip": _r4(rho_fip), "era": _r4(rho_era)},
        "gap_ci_vs_era": xs1_vs_era, "gap_ci_vs_raw_fip": xs1_vs_fip,
        "gate": {"bar": "beats ERA (gap lo95 > 0) AND not worse than raw FIP (lo95 >= -0.01)",
                 "pass": xs1_pass},
        "gb_adjusted_candidate": {
            "experiment": "X-S3", "candidate_rho": _r4(rho_cand),
            "gap_ci_vs_plain_sem": xs3_gap, "pass": xs3_pass,
            "verdict": ("PASS: the ground-ball-adjusted HR expectation beats plain FIP "
                        "forward; ship the adjusted core."
                        if xs3_pass else
                        "NO SHIP: the GB-adjusted core does not beat plain FIP forward out "
                        "of sample; plain FIP stays. Starter samples are large enough that "
                        "the observed HR rate is already a strong estimate.")},
        "verdict": {"status": "validated" if xs1_pass else "provisional",
                    "summary": (
                        f"Forward-chained OOS over {len(SEASONS)} seasons ({n1} Y->Y+1 pairs): "
                        f"SEM+ predicts next-year RA9 at rho {_r4(rho_sem)} vs raw FIP "
                        f"{_r4(rho_fip)}, ERA {_r4(rho_era)}. CI on the rho gap vs ERA "
                        f"{xs1_vs_era}, vs raw FIP {xs1_vs_fip}. "
                        + ("Shipped VALIDATED: SEM+ beats the ERA baseline and is not worse "
                           "than its raw-FIP parent, so the empirical-Bayes shrinkage + "
                           "starter-pool anchoring earn their place. Durability rides "
                           "separate context columns."
                           if xs1_pass else
                           "Shipped provisional with the r published."))}})

    multi_payload = dict(common)
    multi_payload.update({
        "experiment": "X-S2", "model": "sem_plus_3yr", "n_forward_pairs": n3,
        "sem_1yr_forward_rho_on_3yr_set": _r4(rho_1yr),
        "sem_3yr_forward_rho": _r4(rho_3yr), "gap_ci_3yr_minus_1yr": xs2_gap,
        "gate": {"bar": "3yr rho > 1yr rho on the same set AND bootstrap gap lo95 >= 0",
                 "pass": xs2_pass},
        "verdict": ("PASS: 3-year SEM+ forward-predicts next-year run prevention better than "
                    "one season; ship sem_plus_3yr as a companion column."
                    if xs2_pass else
                    "MARGINAL: 3-year SEM+ does not clear the strict same-set gate; ship "
                    "provisional with the r published (more sample is a steadier read) or hold."),
        "proposed_values": _multiyear_proposed(by_season, cur_season)})

    print(json.dumps({
        "X-S1": {"n": n1, "sem": _r4(rho_sem), "fip": _r4(rho_fip), "era": _r4(rho_era),
                 "vs_era": xs1_vs_era, "vs_fip": xs1_vs_fip, "pass": xs1_pass},
        "X-S3": {"cand": _r4(rho_cand), "gap": xs3_gap, "pass": xs3_pass},
        "X-S2": {"n": n3, "one": _r4(rho_1yr), "three": _r4(rho_3yr), "gap": xs2_gap, "pass": xs2_pass},
    }, indent=1))
    if write:
        for path, pl in ((SEM_EVAL, sem_payload), (MULTI_EVAL, multi_payload)):
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return {SEM_EVAL: sem_payload, MULTI_EVAL: multi_payload}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--seasons" in argv:
        i = argv.index("--seasons")
        SEASONS = [int(x) for x in argv[i + 1].split(",")]
    run(write="--no-write" not in argv)
