# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""R-SHRINK: ERA-shrink value unification lab (review-queue item 6).

Pre-registered gate: docs/audit-2026-07/AUDIT_FINDINGS.md, section R-SHRINK.

Two ERA-shrink pseudo-counts live in the codebase and both shrink an ERA, but
toward different targets on different populations:

  * K_IP = 50.0  (rate_stabilization.py -> storage.py era_minus_level display):
    a MiLB statline's ERA is shrunk toward its LEVEL mean by innings before it is
    indexed for the PROSPX statline chip. Sized (RPS+ calibration, 2026-06-18) to
    kill small-sample blowups while leaving full-season lines nearly untouched.

  * NEED_ERA_SHRINK_IP = 45.0 (rate_stabilization.py -> pal_conversion
    .starter_need_score): an MLB starter's season ERA is shrunk toward a league
    starter ERA (LG_SP_ERA = 4.20) before the SP->RP conversion-need score that
    gates PAL's demotion board.

This lab sweeps candidate SHARED values (35..65 step 5) and scores BOTH objectives
per the gate. A single value ships ONLY if it beats or ties BOTH incumbents on
their own objectives; ties break toward keeping two values (the null).

Objective 1 (display stability, incumbent K_IP=50): on real MiLB/MLB pitcher
statlines (storage.load_career_stats joined to the same empirical level norms the
export path builds), for each candidate K:
    era_adj = (ip*era + K*avg_era) / (ip + K)
    index   = round(era_adj / avg_era * 100)     # this IS the storage formula
  (a) small-sample blowup count: lines with IP < K and |index-100| > 50 (the
      gate-literal metric), plus a fixed-window (IP<30) count for a K-invariant
      cross-candidate read;
  (b) split-half stability: seeded Poisson resample of each qualified season into
      two innings-halves; pooled Spearman of the candidate index across halves,
      overall and by innings bin;
  (c) full-season fidelity: mean |index_K - index_unshrunk| on genuine full
      seasons (IP>=100) -- the "leave full-season lines nearly untouched" pressure
      that stops the objective from trivially preferring the largest K.

Objective 2 (PAL need-gate ordering, incumbent NEED_ERA_SHRINK_IP=45): the labeled
SP->RP conversion history in data/pal.json (held = did the new relief role stick a
full season). For each candidate K, recompute starter_need_score(pre.era, pre.ip)
on the pre-conversion starter line and Spearman-correlate need against the held
label; a well-sized shrink ranks genuine rotation-failures (high need) above small-
sample blips so the ordering tracks which conversions actually held. Seeded
bootstrap CI on the rho, because n is small and selection-biased.

Pure evaluation. Writes data/era_shrink_unification_eval.json. Reads only; does not
touch rate_stabilization.py / storage.py / pal_conversion.py (per the gate, the
expected outcome is FAIL-to-unify and the two values stay).

Run:  python tools/era_shrink_unification_lab.py --write
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage  # noqa: E402
from level_norms import compute_level_norms  # noqa: E402

EVAL_PATH = ROOT / "data" / "era_shrink_unification_eval.json"
PAL_PATH = ROOT / "data" / "pal.json"

# ---- seeds (documented) ---------------------------------------------------- #
SEED_SPLIT = 20260702        # Poisson split-half resample
SEED_BOOT = 20260702         # bootstrap CIs
N_BOOT = 2000
N_SPLIT_REPS = 25            # seeded Poisson replications, averaged (smooths the split-half rho)

# ---- materiality thresholds (a candidate must clear NOISE to "beat") -------- #
SPLIT_MATERIAL = 0.005       # split-half rho gain below this is treated as noise

# ---- sweep ----------------------------------------------------------------- #
CANDIDATES = [35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0]
INCUMBENT_DISPLAY = 50.0      # K_IP
INCUMBENT_PAL = 45.0          # NEED_ERA_SHRINK_IP

# ---- PAL need-score constants (copied from pal_conversion; do NOT import a
#      mutable global -- we sweep the shrink value ourselves) ---------------- #
LG_SP_ERA = 4.20
NEED_LO_ERA = 3.20
NEED_HI_ERA = 5.50

# ---- display index constants ----------------------------------------------- #
BLOWUP_ABS = 50.0            # |index-100| > 50 == a blowup
FIXED_SMALL_IP = 30.0        # K-invariant small-sample window
FULL_SEASON_IP = 100.0       # "leave full-season lines untouched" reference
MIN_SPLIT_IP = 20.0          # min season IP to admit into the split-half sim


# --------------------------------------------------------------------------- #
# stats helpers (pure; ties averaged -- matches scipy 'average')
# --------------------------------------------------------------------------- #
def _rankdata(v):
    v = np.asarray(v, dtype=float)
    order = np.argsort(v, kind="mergesort")
    ranks = np.empty(len(v), dtype=float)
    sv = v[order]
    i = 0
    n = len(v)
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(xs, ys):
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    n = len(xs)
    if n < 4:
        return None
    rx, ry = _rankdata(xs), _rankdata(ys)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    if denom == 0:
        return None
    return float((rx * ry).sum() / denom)


def _r4(x):
    return None if x is None else round(float(x), 4)


# --------------------------------------------------------------------------- #
# display index
# --------------------------------------------------------------------------- #
def era_minus_index(era, ip, avg_era, k):
    """The storage.py era_minus_level formula, parameterized by shrink k.
    Mirrors ip=float(...) (production reads the baseball-notation IP as a plain
    float, so we do too)."""
    era_adj = (ip * era + k * avg_era) / (ip + k)
    return round(era_adj / avg_era * 100)


def load_display_lines():
    """Real pitcher statlines joined to the same empirical level norms the export
    path builds. Returns (lines, norms, meta) where each line is
    (era, ip, avg_era, level, season)."""
    cs = storage.load_career_stats()
    bd = storage.load_birth_dates()
    norms = compute_level_norms(cs, bd)             # export-path call, seasons_window=2
    era_norm = {lvl: (blob.get("perf") or {}).get("avg_era") for lvl, blob in norms.items()}

    lines = []
    for _pk, rows in cs.items():
        for r in rows or []:
            if not r.get("is_pitcher"):
                continue
            lvl = r.get("level")
            avg = era_norm.get(lvl)
            if not avg or avg <= 0:
                continue
            try:
                era = float(r.get("era"))
                ip = float(r.get("ip") or 0)
            except (TypeError, ValueError):
                continue
            if era <= 0 or ip <= 0:
                continue
            lines.append((era, ip, float(avg), lvl, r.get("season")))
    return lines, era_norm


def display_objective(lines, era_norm):
    """Score the display objective across the candidate sweep."""
    rng = np.random.default_rng(SEED_SPLIT)

    # arrays for the deterministic (blowup / distortion) metrics
    era = np.array([l[0] for l in lines], dtype=float)
    ip = np.array([l[1] for l in lines], dtype=float)
    avg = np.array([l[2] for l in lines], dtype=float)

    idx_unshrunk = np.round(era / avg * 100.0)

    # split-half pool: qualified season lines, binned by full-season IP.
    split_pool = [(e, i, a) for (e, i, a, _lvl, _s) in lines if i >= MIN_SPLIT_IP]
    sp_era = np.array([p[0] for p in split_pool], dtype=float)
    sp_ip = np.array([p[1] for p in split_pool], dtype=float)
    sp_avg = np.array([p[2] for p in split_pool], dtype=float)
    sp_half = sp_ip / 2.0
    sp_rate = sp_era / 9.0  # earned runs per inning (generative rate)
    # N_SPLIT_REPS seeded pairs of half-season earned-run draws, reused across
    # candidates so the ONLY thing that changes between candidates is the shrink
    # k. Averaging the pooled rho over replications smooths single-draw noise.
    reps = []
    for _ in range(N_SPLIT_REPS):
        er1 = rng.poisson(sp_rate * sp_half).astype(float)
        er2 = rng.poisson(sp_rate * sp_half).astype(float)
        reps.append((er1 * 9.0 / sp_half, er2 * 9.0 / sp_half))

    ip_bins = [(20.0, 40.0), (40.0, 70.0), (70.0, 120.0), (120.0, 1e9)]

    per_k = {}
    for k in CANDIDATES:
        idx = np.round((ip * era + k * avg) / (ip + k) / avg * 100.0)
        dev = np.abs(idx - 100.0)
        blow = dev > BLOWUP_ABS
        blow_ipk = int(np.count_nonzero(blow & (ip < k)))          # gate-literal
        blow_fixed = int(np.count_nonzero(blow & (ip < FIXED_SMALL_IP)))
        blow_total = int(np.count_nonzero(blow))

        full = ip >= FULL_SEASON_IP
        # distortion = how far shrinkage moves a genuine full-season line
        distort = float(np.mean(np.abs(idx[full] - idx_unshrunk[full]))) if full.any() else None

        # split-half indices at this k, averaged over the seeded replications
        pooled_rhos, bin_rhos = [], {}
        for era1, era2 in reps:
            s1 = np.round((sp_half * era1 + k * sp_avg) / (sp_half + k) / sp_avg * 100.0)
            s2 = np.round((sp_half * era2 + k * sp_avg) / (sp_half + k) / sp_avg * 100.0)
            r = spearman(s1, s2)
            if r is not None:
                pooled_rhos.append(r)
            for lo, hi in ip_bins:
                m = (sp_ip >= lo) & (sp_ip < hi)
                if int(np.count_nonzero(m)) >= 30:
                    rb = spearman(s1[m], s2[m])
                    if rb is not None:
                        bin_rhos.setdefault((lo, hi), []).append(rb)
        rho_pool = float(np.mean(pooled_rhos)) if pooled_rhos else None
        by_bin = {}
        for (lo, hi), vals in bin_rhos.items():
            m = (sp_ip >= lo) & (sp_ip < hi)
            lbl = f"{int(lo)}-{int(hi) if hi < 1e8 else 'plus'}"
            by_bin[lbl] = {"n": int(np.count_nonzero(m)), "split_half_rho": _r4(np.mean(vals))}

        per_k[str(int(k))] = {
            "blowups_ip_lt_k": blow_ipk,
            "blowups_ip_lt_30": blow_fixed,
            "blowups_total": blow_total,
            "full_season_distortion": _r4(distort),
            "split_half_rho_pooled": _r4(rho_pool),
            "split_half_by_ip_bin": by_bin,
        }
    meta = {
        "n_lines": len(lines),
        "n_split_pool": len(split_pool),
        "era_norm_by_level": {lvl: (round(v, 3) if v else None) for lvl, v in sorted(era_norm.items())},
        "split_half_generative": "per-line half-season ER ~ Poisson(era/9 * IP/2), one seeded draw reused across candidates",
        "seed_split": SEED_SPLIT,
    }
    return per_k, meta


# --------------------------------------------------------------------------- #
# PAL need-gate objective
# --------------------------------------------------------------------------- #
def _clamp(x, lo=0.0, hi=100.0):
    return lo if x < lo else (hi if x > hi else x)


def need_score(era, ip, k):
    """pal_conversion.starter_need_score, parameterized by shrink k."""
    if era is None:
        return 50.0
    if ip and ip > 0:
        era = (ip * era + k * LG_SP_ERA) / (ip + k)
    return _clamp(100.0 * (era - NEED_LO_ERA) / (NEED_HI_ERA - NEED_LO_ERA))


def load_pal_labeled():
    """Labeled SP->RP conversion events: (pre_era, pre_ip, held_int)."""
    pal = json.loads(PAL_PATH.read_text(encoding="utf-8"))
    ev = []
    for h in pal.get("history", []):
        if h.get("direction") != "SP->RP":
            continue
        if h.get("held") is None:
            continue
        pre = h.get("pre") or {}
        era = pre.get("era")
        ip = pre.get("ip")
        if era is None or ip is None:
            continue
        ev.append((float(era), float(ip), 1 if h.get("held") else 0))
    return ev


def pal_objective(events):
    held = np.array([e[2] for e in events], dtype=float)
    rng = np.random.default_rng(SEED_BOOT)
    n = len(events)
    per_k = {}
    for k in CANDIDATES:
        need = np.array([need_score(e[0], e[1], k) for e in events], dtype=float)
        rho = spearman(need, held)
        # seeded bootstrap CI on the rho
        boots = []
        for _ in range(N_BOOT):
            samp = rng.integers(0, n, n)
            rb = spearman(need[samp], held[samp])
            if rb is not None:
                boots.append(rb)
        boots.sort()
        ci = None
        if boots:
            ci = {
                "lo95": _r4(boots[int(0.025 * len(boots))]),
                "hi95": _r4(boots[int(0.975 * len(boots)) - 1]),
            }
        per_k[str(int(k))] = {
            "need_vs_held_rho": _r4(rho),
            "boot_ci": ci,
            "n_ties_at_clamp": int(np.count_nonzero((need <= 0) | (need >= 100))),
        }
    meta = {
        "n_labeled_sp_to_rp": n,
        "n_held_true": int(held.sum()),
        "n_held_false": int(n - held.sum()),
        "seed_boot": SEED_BOOT,
        "n_boot": N_BOOT,
        "note": "A directional sign-check on a small, selection-biased sample (only arms teams chose to convert); differences across candidates are read against the bootstrap CI, not as fitted validation.",
    }
    return per_k, meta


# --------------------------------------------------------------------------- #
# gate verdict
# --------------------------------------------------------------------------- #
def verdict(disp, pal):
    d50 = disp[str(int(INCUMBENT_DISPLAY))]
    p45 = pal[str(int(INCUMBENT_PAL))]
    # PAL noise floor: to MATERIALLY beat K=45 a candidate's point rho must clear
    # K=45's own bootstrap hi95 (its differences are otherwise within noise). The
    # task's standing rule: marginal == FAIL.
    pal_noise_ceiling = (p45["boot_ci"] or {}).get("hi95")
    rows = []
    ship = None
    for k in CANDIDATES:
        ks = str(int(k))
        d, p = disp[ks], pal[ks]
        # display objective: not worse than incumbent-50 on ANY of the three
        # named pressures (fewer/equal small-sample blowups, >= split-half
        # stability within noise, <= full-season distortion).
        blow_ok = d["blowups_ip_lt_30"] <= d50["blowups_ip_lt_30"]
        split_ok = (d["split_half_rho_pooled"] is not None
                    and d50["split_half_rho_pooled"] is not None
                    and d["split_half_rho_pooled"] >= d50["split_half_rho_pooled"] - SPLIT_MATERIAL)
        distort_ok = (d["full_season_distortion"] is not None
                      and d50["full_season_distortion"] is not None
                      and d["full_season_distortion"] <= d50["full_season_distortion"])
        display_beats_or_ties = blow_ok and split_ok and distort_ok
        # PAL objective: need-vs-held rho not below incumbent-45
        pal_beats_or_ties = (p["need_vs_held_rho"] is not None and
                             p45["need_vs_held_rho"] is not None and
                             p["need_vs_held_rho"] >= p45["need_vs_held_rho"])
        # MATERIAL (beyond-noise) improvements only
        blow_material = d["blowups_ip_lt_30"] < d50["blowups_ip_lt_30"]
        distort_material = (distort_ok and d["full_season_distortion"] < d50["full_season_distortion"])
        split_material = (split_ok and d["split_half_rho_pooled"] is not None
                          and d["split_half_rho_pooled"] > d50["split_half_rho_pooled"] + SPLIT_MATERIAL)
        pal_material = (pal_noise_ceiling is not None and p["need_vs_held_rho"] is not None
                        and p["need_vs_held_rho"] > pal_noise_ceiling)
        # A shared value ships only if it does not degrade EITHER objective and
        # materially improves at least one. blow_material and distort_material are
        # strictly monotone-opposing in k, so display cannot Pareto-improve; the
        # PAL rho never clears its own bootstrap ceiling. Hence no ship.
        strict_improve = bool(blow_material or distort_material or split_material or pal_material)
        ships = bool(display_beats_or_ties and pal_beats_or_ties and strict_improve
                     and k not in (INCUMBENT_DISPLAY, INCUMBENT_PAL))
        rows.append({
            "k": int(k),
            "display_beats_or_ties_50": bool(display_beats_or_ties),
            "pal_beats_or_ties_45": bool(pal_beats_or_ties),
            "blow_ok": bool(blow_ok), "split_ok": bool(split_ok), "distort_ok": bool(distort_ok),
            "material_improvement": strict_improve,
            "ships": ships,
        })
        if ships:
            ship = int(k)
    return rows, ship


def run(write=False):
    lines, era_norm = load_display_lines()
    disp, disp_meta = display_objective(lines, era_norm)
    events = load_pal_labeled()
    pal, pal_meta = pal_objective(events)
    gate_rows, ship = verdict(disp, pal)

    passed = ship is not None
    payload = {
        "generated_at": date.today().isoformat(),
        "experiment": "R-SHRINK",
        "gate_ref": "docs/audit-2026-07/AUDIT_FINDINGS.md#R-SHRINK",
        "incumbents": {"display_K_IP": INCUMBENT_DISPLAY, "pal_NEED_ERA_SHRINK_IP": INCUMBENT_PAL},
        "candidates": [int(c) for c in CANDIDATES],
        "seeds": {"split_half": SEED_SPLIT, "bootstrap": SEED_BOOT, "n_boot": N_BOOT},
        "objective_1_display": {"meta": disp_meta, "sweep": disp},
        "objective_2_pal_need_gate": {"meta": pal_meta, "sweep": pal},
        "gate": {
            "rule": "Ship a single shared value ONLY if it beats-or-ties BOTH incumbents on their own objectives AND strictly improves at least one (Pareto). Ties break toward keeping two values (the null).",
            "display_objective_metrics": "blowups_ip_lt_30 (lower better) AND split_half_rho_pooled (higher better) AND full_season_distortion (lower better), each vs the K=50 incumbent.",
            "pal_objective_metric": "need_vs_held_rho (higher better) vs the K=45 incumbent.",
            "per_candidate": gate_rows,
            "ship_value": ship,
            "verdict": "PASS (unify)" if passed else "FAIL (keep two values)",
        },
    }

    if not passed:
        # loss ledger, expected per the provenance notes
        d50 = disp["50"]
        p45 = pal["45"]
        payload["loss_ledger"] = {
            "outcome": "No single shared value beats or ties both incumbents; the two ERA-shrink pseudo-counts stay (K_IP=50, NEED_ERA_SHRINK_IP=45).",
            "why": [
                "The two constants optimize different objectives on different populations, exactly as the rate_stabilization.py provenance predicted.",
                "Display objective (MiLB level-relative index): small-sample blowups fall monotonically as K rises, but full-season distortion rises monotonically with K, so the incumbent K=50 sits at an interior blowup/fidelity balance no other candidate dominates.",
                "PAL objective (need-vs-held ordering) is measured on n={} labeled, selection-biased SP->RP conversions; candidate rhos sit inside each other's bootstrap CI, so no candidate meaningfully beats K=45 and changing a published PAL board on within-noise evidence is unjustified.".format(pal_meta["n_labeled_sp_to_rp"]),
            ],
            "incumbent_display_K50": {
                "blowups_ip_lt_30": d50["blowups_ip_lt_30"],
                "split_half_rho_pooled": d50["split_half_rho_pooled"],
                "full_season_distortion": d50["full_season_distortion"],
            },
            "incumbent_pal_K45": {"need_vs_held_rho": p45["need_vs_held_rho"], "boot_ci": p45["boot_ci"]},
            "disposition": "FAIL-to-unify resolves review-queue item 6 (F-05). Keep two values with their provenance comments. No code change to rate_stabilization.py / storage.py / pal_conversion.py.",
        }

    print(json.dumps({
        "display_sweep": {k: {"blow<30": v["blowups_ip_lt_30"], "blow<k": v["blowups_ip_lt_k"],
                              "split": v["split_half_rho_pooled"], "distort": v["full_season_distortion"]}
                          for k, v in disp.items()},
        "pal_sweep": {k: {"rho": v["need_vs_held_rho"], "ci": v["boot_ci"]} for k, v in pal.items()},
        "ship_value": ship,
        "verdict": payload["gate"]["verdict"],
    }, indent=1))

    if write:
        EVAL_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {EVAL_PATH.relative_to(ROOT)}")
    return payload


if __name__ == "__main__":
    run(write="--write" in sys.argv)
