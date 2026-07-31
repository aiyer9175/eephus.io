# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W-SCREEN lab: AAA pitcher physics forward screen (ONE SHOT) + the
bounded VAA refetch.

Registration pointer: docs/efv-2026-07-24/GATES.md, section
"W-SCREEN (Phase 3b): pitcher physics forward screen (one shot)".
Registered bar: per-candidate incremental Spearman vs next-season
outcome AFTER residualizing on pooled aStuff+, survivor bar lo95 > 0,
2000 player-clustered bootstrap reps, seed 20260724, ONE attempt,
marginal = FAIL. Survivors become W-OVERLAY-R legs with coefficients
frozen from this screen. Artifact: data/aaa_physics_screen_eval.json.

================================ FROZEN PROTOCOL =============================
Everything in this block was written BEFORE any correlation was computed
and is never edited afterward (the one-shot discipline).

CANDIDATES (exactly as registered):
  velo, ivb, hb_abs, spin, ext, rel_ht, arm_angle, mix_entropy,
  stuff_spread, velo_adj_ivb, vaa, vaaoe (vaa/vaaoe only if the bounded
  refetch lands; absence recorded, not a STOP).
  Feature values = the pitcher-season blocks of data/aaa_physics.json
  (all-pitch means; velo_adj_ivb uses the sidecar's pooled fit).

OUTCOME MAPPING (frozen a priori, the registered whiff-family split):
  K%  (whiff family): velo, ivb, spin, vaa, vaaoe, velo_adj_ivb
  ERA (all others)  : hb_abs, ext, rel_ht, arm_angle, mix_entropy,
                      stuff_spread
  K%  = next-season AAA sum(SO) / sum(BF).
  ERA = next-season AAA 9 * sum(ER_est) / sum(IP_era), ER_est per row =
        era * ip / 9 (rows lacking era or ip drop from the ERA sums only).
  Outcome orientation: higher = better. K% enters raw; ERA enters
  NEGATED (era_inv = -ERA, the stuff_plus_aaa.forward_eval convention).
  Features enter in natural units with NO sign flips: a candidate whose
  residual correlation with the better-is-higher outcome is negative
  FAILS, however large in magnitude (one attempt, marginal fails).

SAMPLE:
  AAA pitchers with consecutive-season pairs 2023->2024 and 2024->2025
  (complete next seasons only). Qualification: sidecar n_pitches >= 100
  in BOTH seasons of the pair AND next-season AAA outcome exposure
  >= 40 IP. Outcome source: .cache/milb_stats/pitching_11_{year}.json
  (statsapi season aggregates, sportId 11 = AAA, written by
  milb_history.py), rows aggregated per mlbam across leagues; IP parsed
  from baseball .1/.2 thirds notation. A pitcher may contribute both
  pairs; the bootstrap clusters on the pitcher so that dependence is
  respected. Per-candidate rows additionally require a non-null feature
  value, a non-null astuff_pool, and the outcome legs (BF > 0 for K%,
  IP_era > 0 for ERA); per-candidate n recorded.

RESIDUALIZATION (the "incremental" construction):
  OLS residual of the feature on the feature-season astuff_pool AND OLS
  residual of the outcome on the same astuff_pool, then Spearman of the
  two residual vectors. astuff_pool = data/aaa_physics.json per-season
  pooled aStuff+ (the shipped stuff_plus_aaa bundle under score()'s
  exact conventions; served-json agreement max_abs_diff 0.0). Both OLS
  fits are REFIT inside every bootstrap replicate (full-pipeline
  bootstrap; the residualization is part of the estimator).

BAR AND BOOTSTRAP:
  Survivor bar: lo95 > 0 STRICTLY. CI = percentile [2.5, 97.5] over
  2000 player-clustered bootstrap replicates: resample the unique
  pitcher (mlbam) clusters with replacement, keep every row of each
  sampled cluster (duplicates kept). rng = numpy.random.default_rng(
  20260724), a fresh generator per candidate (order-independent,
  deterministic). Replicates with degenerate inputs (constant vector,
  nan rho) are skipped and counted in n_reps_effective.

VAA (only if the bounded refetch lands):
  Per pitch, from .cache/aaa_pitches_vaa CSVs:
    vy_f = -sqrt(vy0^2 - 2 * ay * (y0 - yf)),  y0 = 50 ft, yf = 17/12 ft
    t = (vy_f - vy0) / ay ;  vz_f = vz0 + az * t
    VAA = -atan(vz_f / vy_f) * 180 / pi
  (the platform's canonical formula, vaa.py calculate_vaa, copied here
  so the lab does not import that module's fetch stack).
  Pitcher-season vaa = mean per-pitch VAA over ALL VAA-computable
  pitches. VAAOE: per pitch, VAA minus a pooled OLS fit of VAA on
  plate_z and release_pos_z; fit pool = every VAA-computable pitch of
  the screen sample's FEATURE pitcher-seasons (board-arm extras are
  excluded from the fit); coefficients recorded in the artifact meta.
  Pitcher-season vaaoe = mean per-pitch VAAOE.
  LANDING CRITERION (frozen): vaa_status = "landed" if >= 70 percent of
  the screen sample's feature pitcher-seasons have >= 50 VAA-computable
  cached pitches; otherwise "absent" (vaa/vaaoe not judged, reason
  recorded; registered: absence is not a STOP).

ONE SHOT:
  --screen REFUSES to run if data/aaa_physics_screen_eval.json already
  exists. There is no force flag. The artifact is written exactly once.

SURVIVOR COEFFICIENTS (what W-OVERLAY-R consumes):
  For every candidate (echoed in the survivors block for passers), the
  FULL-sample fit, frozen here and never refit downstream:
    resid_fit_on_astuff: {intercept, slope} of feature ~ astuff_pool
    resid_sd: SD of the full-sample feature residuals (the z-scale)
    feat_mean, feat_sd: raw feature moments for reference
    rho, lo95, hi95, n, outcome
==============================================================================

Run:  python tools/aaa_physics_screen_lab.py --sample
      python tools/aaa_physics_screen_lab.py --fetch-vaa [--budget-s 9000]
      python tools/aaa_physics_screen_lab.py --screen

============================ SUB-AAA FROZEN PROTOCOL =========================
W-SCREEN-SUB (owner addendum, registered in docs/efv-2026-07-24/GATES.md
BEFORE any sub-AAA arm ran). Everything in this block was written BEFORE
any sub-AAA correlation was computed and is never edited afterward. The
AAA frozen protocol above is untouched.

SOURCE + EXTRACTION (.cache/game_feeds, walked offline; accumulator cache
.cache/aaa_physics_sub/, checkpointed + resumable, extraction capped at
~2 hours wall - a cap hit is recorded as COVERAGE, never a STOP):
  Every cached StatsAPI game feed is classified by home-team sport id +
  season; sports 11/12/13/14/15/16, seasons 2023-2025 are kept. TRACKED
  pitch = isPitch with pitchData.startSpeed AND coordinates.vY0 present
  (the full-vector definition; untracked parks are absent = coverage,
  never imputed). Frozen field sources per tracked pitch:
    velo    = pitchData.startSpeed (mph)
    ivb     = pitchData.breaks.breakVerticalInduced (in, the Savant IVB
              convention; feed pfxZ is NOT used - different reference)
    hb_abs  = |pitchData.breaks.breakHorizontal| (in)
    spin    = pitchData.breaks.spinRate (rpm)
    rel_ht  = pitchData.coordinates.z0 (ft, registered "from x0/z0")
    type    = details.type.code (mix_entropy = Shannon bits over tracked
              typed usage shares, all types)
    vaa     = calculate_vaa(vY0, vZ0, aY, aZ, y0=coordinates.y0 else 50)
  VAA/VAAOE are accumulated as per-pitcher-season moment sums so the
  pooled VAAOE fit (VAA ~ 1 + pZ + z0, normal equations over the screen
  feature rows' pitches) and the per-row means need no pitch-level store.

CANDIDATES (exactly as registered, the feed-derivable subset):
  velo, ivb, hb_abs, spin, rel_ht, mix_entropy, vaa + vaaoe where
  coordinate vectors exist.
OUTCOME MAPPING (frozen a priori; same whiff-family rule as W-SCREEN):
  K%  (whiff family): velo, ivb, spin, vaa, vaaoe
  ERA (others)      : hb_abs, rel_ht, mix_entropy
  Outcomes = NEXT-season MiLB pooled across ALL levels (sports
  11/12/13/14/15/16 milb_stats aggregates - sub-AAA pitchers promote, so
  the destination is the ladder, not one level): K% = sum(SO)/sum(BF);
  ERA = 9*sum(era*ip/9)/sum(ip_era); orientation higher-is-better (K%
  raw, ERA negated); features natural units, NO sign flips.

SAMPLE (registered floors):
  Feature season s in {2023, 2024}; feature physics = the pitcher's
  pooled A + CPX (sports 14 + 16) tracked pitches in s, >= 150 tracked.
  Season s+1 tracked exposure >= 150 pitches at ANY kept sport (the
  "both seasons" tracked floor; promotion keeps a pitcher tracked only
  where the feed cache covers him - coverage, recorded).
  Outcome exposure >= 40 IP pooled next season. Per-candidate rows need
  a non-null feature, a ridge yhat, and the outcome legs. vaa/vaaoe row
  floor: >= 50 VAA-computable pitches (the AAA convention); landing bar:
  >= 70 percent of sample rows covered, else vaa_status absent.

RESIDUALIZER (the registered "frozen stat-line ridge from the line-4
lab", named here BEFORE any correlation ran):
  The S-XLINE-4 pitcher baseline construction, reimplemented verbatim
  from tools/efv_statcast_line2_lab.py (_ridge_crossfit + _pit_dataset
  conventions): closed-form ridge, lambda 1.0, 5 folds BY PLAYER (fold
  permutation seed 20260723, the line-4 lab seed), features standardized
  on the train fold, intercept via train-fold centering. Features =
  (k_pct_a, bb_pct_a, era_z, age_for_level) from the FEATURE-season
  A/CPX stat line: the pitcher's max-BF sport among 14/16, rows
  aggregated within it, BF >= 150 (the line-4 MIN_BF convention), era_z
  = z within the (sport, season) ridge-universe pool. Trained on the
  FULL stat-line-eligible pair universe (feed-covered or not - the
  line-4 "strongest baseline" convention, biases AGAINST a false pass),
  predicting the candidate family's raw outcome (K% resp. era_inv).
  Incremental construction, the sub-AAA analog of the aStuff+
  residualization: OLS-residualize the candidate feature AND the outcome
  on the out-of-fold yhat, Spearman of the residuals. The cross-fit runs
  ONCE per outcome family; bootstrap replicates (2000 player-clustered,
  seed 20260724, percentile CI) refit ONLY the OLS residualizations
  (yhat held fixed - the line-4 leakage-guard convention).
BAR: lo95 > 0 STRICTLY, one attempt, marginal = FAIL. Closed lanes stay
closed: no K-measurement-shaped candidate is judged vs raw K% (the
candidate list above is physics-only).
ARTIFACT: sub_aaa block inside data/aaa_physics_screen_eval.json (the
registered same-file placement). One shot: --sub-screen REFUSES to run
if the artifact already carries a sub_aaa block. Survivors feed
W-OVERLAY-R (coverage-gated to tracked-park players) with coefficients
frozen from this screen: resid_fit_on_yhat {intercept, slope}, resid_sd,
feat moments, plus the ridge spec + VAAOE fit needed to rebuild yhat
and features at serve time.
COVERAGE HONESTY: the artifact records the stat-line-eligible qualifying
pair universe N alongside the feed-covered screen n (the covered
fraction), extraction completeness (feeds walked / feeds cached), and
per-(sport, season) game counts.

Run:  python tools/aaa_physics_screen_lab.py --sub-extract [--cap-s 7200]
      python tools/aaa_physics_screen_lab.py --sub-sample
      python tools/aaa_physics_screen_lab.py --sub-screen
==============================================================================
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

DATA_DIR = _ROOT / "data"
PHYSICS_PATH = DATA_DIR / "aaa_physics.json"
OUT_PATH = DATA_DIR / "aaa_physics_screen_eval.json"
MILB_STATS_DIR = _ROOT / ".cache" / "milb_stats"
VAA_CACHE_DIR = _ROOT / ".cache" / "aaa_pitches_vaa"
PITCH_CACHE_DIR = _ROOT / ".cache" / "aaa_pitches"
DB_PATH = _ROOT / "prospects.db"

PAIRS = ((2023, 2024), (2024, 2025))
MIN_PAIR_PITCHES = 100
MIN_NEXT_IP = 40.0
SEED = 20260724
N_REPS = 2000
VAA_MIN_PITCHES = 50
VAA_COVERAGE_BAR = 0.70
Y0_FT = 50.0
YF_FT = 17.0 / 12.0

# frozen candidate -> outcome family (see FROZEN PROTOCOL above)
K_FAMILY = ("velo", "ivb", "spin", "vaa", "vaaoe", "velo_adj_ivb")
ERA_FAMILY = ("hb_abs", "ext", "rel_ht", "arm_angle", "mix_entropy",
              "stuff_spread")
CANDIDATES = K_FAMILY[:3] + ("hb_abs", "ext", "rel_ht", "arm_angle",
                             "mix_entropy", "stuff_spread", "velo_adj_ivb",
                             "vaa", "vaaoe")

VAA_KEEP = ("pitch_type", "release_speed", "vy0", "vz0", "ay", "az",
            "plate_z", "release_pos_z", "p_throws")
THROTTLE_S = 1.2
DEFAULT_BUDGET_S = 9000          # the ~2.5 hour hard cap
MAX_CONSEC_ERRORS = 15
CHECKPOINT_EVERY = 25


# ----------------------------------------------------------------- helpers --

def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _ip_float(s):
    """Baseball thirds notation: '123.2' -> 123 + 2/3."""
    if s in (None, ""):
        return None
    try:
        w, _, frac = str(s).partition(".")
        return int(w) + {"": 0, "0": 0, "1": 1, "2": 2}[frac] / 3.0
    except (ValueError, KeyError):
        return None


def calculate_vaa(vy0, vz0, ay, az, y0=Y0_FT, yf=YF_FT):
    """Canonical platform formula (vaa.py calculate_vaa, copied verbatim
    so this lab does not pull in that module's game-feed fetch stack)."""
    disc = (vy0 * vy0) - (2 * ay * (y0 - yf))
    if disc < 0 or ay == 0:
        return None
    vy_f = -math.sqrt(disc)
    t = (vy_f - vy0) / ay
    vz_f = vz0 + (az * t)
    return -math.atan(vz_f / vy_f) * (180 / math.pi)


# ------------------------------------------------------------------ sample --

def _outcomes(year: int) -> dict[int, dict]:
    """Next-season AAA outcome aggregates per mlbam (frozen definition)."""
    rows = json.loads(
        (MILB_STATS_DIR / f"pitching_11_{year}.json").read_text("utf-8"))
    agg: dict[int, dict] = {}
    for r in rows:
        if r.get("level") != "AAA" or not r.get("mlbam"):
            continue
        a = agg.setdefault(int(r["mlbam"]),
                           {"ip": 0.0, "er": 0.0, "ip_era": 0.0,
                            "so": 0, "bf": 0})
        ip = _ip_float(r.get("ip")) or 0.0
        a["ip"] += ip
        era = _f(r.get("era"))
        if era is not None and ip > 0:
            a["er"] += era * ip / 9.0
            a["ip_era"] += ip
        a["so"] += int(r.get("so") or 0)
        a["bf"] += int(r.get("bf") or 0)
    return agg


def build_sample() -> list[dict]:
    """Qualified pair rows: one per (pitcher, feature-season)."""
    players = json.loads(PHYSICS_PATH.read_text("utf-8"))["players"]
    rows = []
    for s, s_next in PAIRS:
        nxt = _outcomes(s_next)
        for smid, seasons in players.items():
            b1 = seasons.get(str(s))
            b2 = seasons.get(str(s_next))
            if not b1 or not b2:
                continue
            if (b1["n_pitches"] < MIN_PAIR_PITCHES
                    or b2["n_pitches"] < MIN_PAIR_PITCHES):
                continue
            o = nxt.get(int(smid))
            if not o or o["ip"] < MIN_NEXT_IP:
                continue
            k_pct = (o["so"] / o["bf"]) if o["bf"] > 0 else None
            era = (9.0 * o["er"] / o["ip_era"]) if o["ip_era"] > 0 else None
            rows.append({"mlbam": int(smid), "season": s,
                         "next_season": s_next, "feat": b1,
                         "k_pct": k_pct,
                         "era_inv": (-era) if era is not None else None,
                         "next_ip": round(o["ip"], 1)})
    return rows


# -------------------------------------------------------------- vaa refetch --

def _board_arm_targets() -> list[tuple[int, int]]:
    """Current-board arms (latest-season statcast_metrics payloads) with an
    existing AAA pitch cache 2023-2025."""
    import sqlite3
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        row = cur.execute(
            "select max(season) from statcast_metrics").fetchone()
        if not row or row[0] is None:
            return []
        season = row[0]
        mids = set()
        for (pj,) in cur.execute(
                "select payload_json from statcast_metrics where season = ?",
                (season,)):
            p = json.loads(pj)
            if p.get("is_pitcher") and p.get("mlbam_id"):
                mids.add(int(p["mlbam_id"]))
    finally:
        con.close()
    out = []
    for mid in sorted(mids):
        for s in (2023, 2024, 2025):
            if (PITCH_CACHE_DIR / f"{mid}_{s}.csv").exists():
                out.append((mid, s))
    return out


def _fetch_vaa_one(mid: int, season: int) -> bool:
    """One pitcher-season VAA CSV into the cache. True on success."""
    from stuff_plus_aaa import SEARCH   # read-only reuse of the URL skeleton
    url = SEARCH.format(season=season, mlbam=mid)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8-sig", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=VAA_KEEP)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in VAA_KEEP})
    (VAA_CACHE_DIR / f"{mid}_{season}.csv").write_text(
        buf.getvalue(), encoding="utf-8")
    return True


def fetch_vaa(budget_s: float = DEFAULT_BUDGET_S) -> dict:
    """Bounded, checkpointed refetch. Priority: screen feature
    pitcher-seasons first, then current-board arms. Skips existing files
    (closed seasons immutable). Stops at the budget or on a persistent
    endpoint refusal; both are graceful (absence is not a STOP)."""
    VAA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sample = build_sample()
    primary = sorted({(r["mlbam"], r["season"]) for r in sample})
    board = [t for t in _board_arm_targets() if t not in set(primary)]
    targets = primary + board
    todo = [t for t in targets
            if not (VAA_CACHE_DIR / f"{t[0]}_{t[1]}.csv").exists()]
    state = {"started_at": datetime.now(timezone.utc).isoformat(),
             "budget_s": budget_s, "n_targets": len(targets),
             "n_primary": len(primary), "n_board": len(board),
             "n_pre_cached": len(targets) - len(todo),
             "done": 0, "errors": 0, "stopped_reason": None}
    t0 = time.time()
    consec = 0
    last = 0.0
    for i, (mid, season) in enumerate(todo):
        if time.time() - t0 > budget_s:
            state["stopped_reason"] = "budget_exhausted"
            break
        dt = time.time() - last
        if dt < THROTTLE_S:
            time.sleep(THROTTLE_S - dt)
        last = time.time()
        try:
            _fetch_vaa_one(mid, season)
            state["done"] += 1
            consec = 0
        except Exception as e:                                # noqa: BLE001
            state["errors"] += 1
            consec += 1
            log.warning("vaa fetch failed %s/%s: %s", mid, season, e)
            if consec >= MAX_CONSEC_ERRORS:
                state["stopped_reason"] = "endpoint_refused"
                break
        if (i + 1) % CHECKPOINT_EVERY == 0:
            state["elapsed_s"] = round(time.time() - t0, 1)
            (VAA_CACHE_DIR / "_state.json").write_text(
                json.dumps(state, indent=1), encoding="utf-8")
            log.info("vaa fetch %d/%d (errors %d, %.0fs)",
                     state["done"], len(todo), state["errors"],
                     time.time() - t0)
    else:
        state["stopped_reason"] = state["stopped_reason"] or "complete"
    state["stopped_reason"] = state["stopped_reason"] or "complete"
    state["elapsed_s"] = round(time.time() - t0, 1)
    (VAA_CACHE_DIR / "_state.json").write_text(
        json.dumps(state, indent=1), encoding="utf-8")
    return state


# ------------------------------------------------------------- vaa loading --

def _load_vaa_season(mid: int, season: int):
    """[(vaa, plate_z, rel_ht)] for one cached pitcher-season (computable
    pitches only)."""
    path = VAA_CACHE_DIR / f"{mid}_{season}.csv"
    if not path.exists():
        return []
    out = []
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
        vy0, vz0 = _f(r.get("vy0")), _f(r.get("vz0"))
        ay, az = _f(r.get("ay")), _f(r.get("az"))
        pz, rh = _f(r.get("plate_z")), _f(r.get("release_pos_z"))
        if None in (vy0, vz0, ay, az, pz, rh):
            continue
        v = calculate_vaa(vy0, vz0, ay, az)
        if v is not None:
            out.append((v, pz, rh))
    return out


def _attach_vaa(sample: list[dict]) -> dict:
    """Compute the landing criterion; if landed, attach per-row vaa/vaaoe
    and return the status block (with the pooled VAAOE fit)."""
    import numpy as np
    per_row_pitches = []
    for r in sample:
        per_row_pitches.append(_load_vaa_season(r["mlbam"], r["season"]))
    covered = sum(1 for p in per_row_pitches if len(p) >= VAA_MIN_PITCHES)
    coverage = covered / len(sample) if sample else 0.0
    status = {"criterion": f">= {VAA_COVERAGE_BAR:.0%} of feature "
                           f"pitcher-seasons with >= {VAA_MIN_PITCHES} "
                           "VAA-computable cached pitches",
              "n_rows": len(sample), "n_covered": covered,
              "coverage": round(coverage, 4)}
    if coverage < VAA_COVERAGE_BAR:
        status["status"] = "absent"
        status["reason"] = ("bounded refetch did not reach the frozen "
                           "coverage bar")
        return status
    # pooled VAAOE fit over every computable pitch of the feature rows
    allp = [p for pitches in per_row_pitches for p in pitches]
    A = np.array([[1.0, pz, rh] for _v, pz, rh in allp])
    b = np.array([v for v, _pz, _rh in allp])
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    for r, pitches in zip(sample, per_row_pitches):
        if len(pitches) >= VAA_MIN_PITCHES:
            vaas = [v for v, _pz, _rh in pitches]
            oes = [v - (coef[0] + coef[1] * pz + coef[2] * rh)
                   for v, pz, rh in pitches]
            r["feat"] = dict(r["feat"])
            r["feat"]["vaa"] = float(np.mean(vaas))
            r["feat"]["vaaoe"] = float(np.mean(oes))
    status["status"] = "landed"
    status["vaaoe_fit"] = {"intercept": round(float(coef[0]), 4),
                           "plate_z": round(float(coef[1]), 4),
                           "rel_ht": round(float(coef[2]), 4),
                           "n_pitches": len(allp),
                           "fit_pool": "all VAA-computable pitches of the "
                                       "screen feature pitcher-seasons"}
    return status


# ------------------------------------------------------------------ screen --

def _ols_resid(y, x):
    """Residual of y on [1, x] (numpy arrays)."""
    import numpy as np
    if float(np.var(x)) <= 0:
        return y - float(np.mean(y))
    b = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
    a = float(np.mean(y)) - b * float(np.mean(x))
    return y - (a + b * x)


def _screen_candidate(name: str, rows: list[dict]):
    """One candidate: full-sample point estimate + clustered bootstrap CI.
    Residualization refit inside every replicate (frozen protocol)."""
    import numpy as np
    from scipy.stats import spearmanr
    outcome = "k_pct" if name in K_FAMILY else "era_inv"
    data = []
    for r in rows:
        f = r["feat"].get(name)
        s = r["feat"].get("astuff_pool")
        y = r[outcome]
        if f is None or s is None or y is None:
            continue
        data.append((r["mlbam"], float(f), float(s), float(y)))
    n = len(data)
    if n < 30:
        return {"outcome": outcome, "n": n, "verdict": "FAIL",
                "reason": "insufficient rows (< 30)"}
    mids = np.array([d[0] for d in data])
    feat = np.array([d[1] for d in data])
    stuff = np.array([d[2] for d in data])
    y = np.array([d[3] for d in data])

    def _rho(idx):
        rf = _ols_resid(feat[idx], stuff[idx])
        ry = _ols_resid(y[idx], stuff[idx])
        if float(np.var(rf)) <= 0 or float(np.var(ry)) <= 0:
            return None
        r = spearmanr(rf, ry).statistic
        return None if (r != r) else float(r)

    full_idx = np.arange(n)
    rho = _rho(full_idx)
    clusters = np.unique(mids)
    idx_by_cluster = {c: np.flatnonzero(mids == c) for c in clusters}
    rng = np.random.default_rng(SEED)
    reps = []
    for _ in range(N_REPS):
        picks = rng.choice(clusters, size=len(clusters), replace=True)
        idx = np.concatenate([idx_by_cluster[c] for c in picks])
        r = _rho(idx)
        if r is not None:
            reps.append(r)
    reps = np.array(reps)
    if len(reps) < N_REPS // 2:
        return {"outcome": outcome, "n": n, "verdict": "FAIL",
                "reason": "degenerate bootstrap (under half the reps usable)"}
    lo95 = float(np.percentile(reps, 2.5))
    hi95 = float(np.percentile(reps, 97.5))
    verdict = "PASS" if (rho is not None and lo95 > 0) else "FAIL"
    # full-sample frozen coefficients (what W-OVERLAY-R consumes)
    if float(np.var(stuff)) > 0:
        slope = float(np.cov(stuff, feat, bias=True)[0, 1] / np.var(stuff))
    else:
        slope = 0.0
    inter = float(np.mean(feat)) - slope * float(np.mean(stuff))
    resid = feat - (inter + slope * stuff)
    return {"outcome": outcome, "n": n,
            "n_clusters": int(len(clusters)),
            "rho": round(rho, 4) if rho is not None else None,
            "lo95": round(lo95, 4), "hi95": round(hi95, 4),
            "n_reps_effective": int(len(reps)),
            "verdict": verdict,
            "resid_fit_on_astuff": {"intercept": round(inter, 6),
                                    "slope": round(slope, 6)},
            "resid_sd": round(float(np.std(resid)), 6),
            "feat_mean": round(float(np.mean(feat)), 6),
            "feat_sd": round(float(np.std(feat)), 6)}


def screen() -> dict:
    """THE one-shot gate run. Refuses to rerun over an existing artifact."""
    if OUT_PATH.exists():
        raise SystemExit(f"REFUSED: {OUT_PATH} already exists - W-SCREEN is "
                         "a one-shot gate and has already been attempted.")
    sample = build_sample()
    vaa_status = _attach_vaa(sample)
    judged = list(CANDIDATES)
    if vaa_status["status"] != "landed":
        judged = [c for c in judged if c not in ("vaa", "vaaoe")]
    results = {}
    for name in judged:
        results[name] = _screen_candidate(name, sample)
        log.info("%-13s %-7s n=%-4s rho=%-8s lo95=%-8s %s",
                 name, results[name]["outcome"], results[name]["n"],
                 results[name].get("rho"), results[name].get("lo95"),
                 results[name]["verdict"])
    survivors = {k: {kk: vv for kk, vv in v.items()
                     if kk in ("outcome", "n", "rho", "lo95", "hi95",
                               "resid_fit_on_astuff", "resid_sd",
                               "feat_mean", "feat_sd")}
                 for k, v in results.items() if v["verdict"] == "PASS"}
    n_pair = {f"{a}->{b}": sum(1 for r in sample if r["season"] == a)
              for a, b in PAIRS}
    out = {
        "generated_at": date.today().isoformat(),
        "registration": "docs/efv-2026-07-24/GATES.md W-SCREEN (Phase 3b): "
                        "one shot, survivor bar lo95 > 0, 2000 "
                        "player-clustered reps, seed 20260724, marginal = "
                        "FAIL; survivors feed W-OVERLAY-R with coefficients "
                        "frozen here",
        "one_shot": {"attempted_at": datetime.now(timezone.utc).isoformat(),
                     "note": "single attempt; the lab refuses to rerun over "
                             "this artifact"},
        "frozen_protocol": {
            "mapping": {"k_pct": list(K_FAMILY), "era_inv": list(ERA_FAMILY)},
            "orientation": "outcomes higher-is-better (K% raw, ERA negated); "
                           "features natural units, NO sign flips; negative "
                           "rho fails regardless of magnitude",
            "residualization": "OLS residual of feature AND outcome on the "
                               "feature-season astuff_pool "
                               "(data/aaa_physics.json, shipped "
                               "stuff_plus_aaa bundle, served-json agreement "
                               "max_abs_diff 0.0); refit in every bootstrap "
                               "replicate",
            "sample": "consecutive AAA pairs 2023->2024 + 2024->2025; "
                      f">= {MIN_PAIR_PITCHES} sidecar pitches both seasons; "
                      f"next-season AAA >= {int(MIN_NEXT_IP)} IP",
            "outcome_source": ".cache/milb_stats/pitching_11_{year}.json "
                              "(statsapi sportId 11 aggregates via "
                              "milb_history.py); K% = SO/BF; ERA = "
                              "9*sum(era*ip/9)/sum(ip) over era-bearing "
                              "rows; IP thirds notation parsed",
            "bootstrap": f"{N_REPS} reps, cluster = mlbam, percentile CI, "
                         f"numpy default_rng({SEED}) fresh per candidate",
            "vaa": "formula = vaa.py calculate_vaa (y0 50ft, plate 17/12); "
                   "pitcher-season mean over all computable pitches; vaaoe "
                   "= residual on pooled OLS(plate_z, release_pos_z) fit "
                   "over feature-row pitches; landing bar >= 70 pct rows "
                   f"with >= {VAA_MIN_PITCHES} computable pitches"},
        "sample": {"n_rows": len(sample),
                   "n_pitchers": len({r["mlbam"] for r in sample}),
                   "pairs": n_pair},
        "vaa_status": vaa_status,
        "candidates": results,
        "survivors": survivors,
    }
    OUT_PATH.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    log.info("wrote %s (%d candidates, %d survivors)", OUT_PATH,
             len(results), len(survivors))
    return out


# ================================ SUB-AAA ====================================
# W-SCREEN-SUB implementation. Protocol frozen in the module docstring
# (SUB-AAA FROZEN PROTOCOL) before any correlation ran.

SUB_CACHE_DIR = _ROOT / ".cache" / "aaa_physics_sub"
SUB_ACC_PATH = SUB_CACHE_DIR / "acc.pkl"
SUB_STATE_PATH = SUB_CACHE_DIR / "_state.json"
SUB_SPORTS = (11, 12, 13, 14, 15, 16)
SUB_FEATURE_SPORTS = (14, 16)            # A + CPX
SUB_SEASONS = (2023, 2024, 2025)
SUB_MIN_TRACKED = 150                    # registered, both seasons
SUB_MIN_NEXT_IP = 40.0                   # registered IP-proxy floor
SUB_MIN_BF_STATLINE = 150                # line-4 MIN_BF convention (ridge)
SUB_RIDGE_LAMBDA = 1.0                   # line-4 RIDGE_LAMBDA
SUB_N_FOLDS = 5                          # line-4 N_FOLDS
SUB_FOLD_SEED = 20260723                 # line-4 lab SEED (fold permutation)
SUB_EXTRACT_CAP_S = 7200                 # ~2h extraction cap (addendum)
SUB_K_FAMILY = ("velo", "ivb", "spin", "vaa", "vaaoe")
SUB_ERA_FAMILY = ("hb_abs", "rel_ht", "mix_entropy")
SUB_CANDIDATES = ("velo", "ivb", "hb_abs", "spin", "rel_ht", "mix_entropy",
                  "vaa", "vaaoe")
SUB_FIELDS = ("velo", "ivb", "hb_abs", "spin", "rel_ht")
_VAA_MOMENTS = ("n_vaa", "s_vaa", "s_pz", "s_z0", "s_pz2", "s_z02",
                "s_pzz0", "s_vaapz", "s_vaaz0")


def _sub_new_entry() -> dict:
    e = {"n_events": 0, "n_tracked": 0, "types": {}}
    for f in SUB_FIELDS:
        e[f"s_{f}"] = 0.0
        e[f"n_{f}"] = 0
    for m in _VAA_MOMENTS:
        e[m] = 0.0
    return e


def _sub_extract_feed(data: dict, acc: dict) -> str | None:
    """One cached feed into the accumulator. Returns 'sport_season' key or
    None when the feed is out of scope. Frozen field sources per the
    SUB-AAA FROZEN PROTOCOL."""
    gd = data.get("gameData") or {}
    sport = (((gd.get("teams") or {}).get("home") or {}).get("sport")
             or {}).get("id")
    try:
        season = int((gd.get("game") or {}).get("season") or 0)
    except (TypeError, ValueError):
        return None
    if sport not in SUB_SPORTS or season not in SUB_SEASONS:
        return None
    plays = ((data.get("liveData") or {}).get("plays") or {}).get(
        "allPlays", [])
    per = acc["per"]
    for play in plays:
        pitcher = int(((play.get("matchup") or {}).get("pitcher")
                       or {}).get("id") or 0)
        if not pitcher:
            continue
        key = (pitcher, season, sport)
        e = per.get(key)
        if e is None:
            e = per[key] = _sub_new_entry()
        for ev in play.get("playEvents", []):
            if not ev.get("isPitch"):
                continue
            e["n_events"] += 1
            pd = ev.get("pitchData") or {}
            co = pd.get("coordinates") or {}
            velo = _f(pd.get("startSpeed"))
            vy0 = _f(co.get("vY0"))
            if velo is None or vy0 is None:
                continue                       # untracked = coverage
            e["n_tracked"] += 1
            br = pd.get("breaks") or {}
            pt = ((ev.get("details") or {}).get("type") or {}).get("code")
            if pt:
                e["types"][pt] = e["types"].get(pt, 0) + 1
            vals = {"velo": velo,
                    "ivb": _f(br.get("breakVerticalInduced")),
                    "hb_abs": (abs(_f(br.get("breakHorizontal")))
                               if _f(br.get("breakHorizontal")) is not None
                               else None),
                    "spin": _f(br.get("spinRate")),
                    "rel_ht": _f(co.get("z0"))}
            for f, v in vals.items():
                if v is not None:
                    e[f"s_{f}"] += v
                    e[f"n_{f}"] += 1
            vz0, ay, az = _f(co.get("vZ0")), _f(co.get("aY")), _f(co.get("aZ"))
            pz, z0 = _f(co.get("pZ")), _f(co.get("z0"))
            if None in (vz0, ay, az, pz, z0):
                continue
            y0 = _f(co.get("y0")) or Y0_FT
            v = calculate_vaa(vy0, vz0, ay, az, y0=y0)
            if v is None:
                continue
            e["n_vaa"] += 1
            e["s_vaa"] += v
            e["s_pz"] += pz
            e["s_z0"] += z0
            e["s_pz2"] += pz * pz
            e["s_z02"] += z0 * z0
            e["s_pzz0"] += pz * z0
            e["s_vaapz"] += v * pz
            e["s_vaaz0"] += v * z0
    return f"{sport}_{season}"


def sub_extract(cap_s: float = SUB_EXTRACT_CAP_S) -> dict:
    """Offline walk of the cached game feeds (zero fetches). Checkpointed +
    resumable; capped; a cap hit is recorded coverage, never a STOP."""
    import pickle
    import feed_cache as fc
    SUB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if SUB_ACC_PATH.exists():
        with SUB_ACC_PATH.open("rb") as fh:
            acc = pickle.load(fh)
    else:
        acc = {"per": {}, "done_pks": set(), "games": {}, "parse_errors": 0}
    files = sorted(fc.CACHE_DIR.glob("*.json"))
    todo = [p for p in files if p.stem not in acc["done_pks"]]
    t0 = time.time()
    stopped = "complete"
    for i, path in enumerate(todo):
        if time.time() - t0 > cap_s:
            stopped = "cap_exhausted"
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = _sub_extract_feed(data, acc)
            if key:
                acc["games"][key] = acc["games"].get(key, 0) + 1
        except Exception:                                     # noqa: BLE001
            acc["parse_errors"] += 1
        acc["done_pks"].add(path.stem)
        if (i + 1) % 1000 == 0:
            with SUB_ACC_PATH.open("wb") as fh:
                pickle.dump(acc, fh, protocol=pickle.HIGHEST_PROTOCOL)
            log.info("sub extract %d/%d feeds (%.0fs, %d pitcher-season-"
                     "sport keys)", i + 1, len(todo), time.time() - t0,
                     len(acc["per"]))
    with SUB_ACC_PATH.open("wb") as fh:
        pickle.dump(acc, fh, protocol=pickle.HIGHEST_PROTOCOL)
    state = {"finished_at": datetime.now(timezone.utc).isoformat(),
             "feeds_cached": len(files), "feeds_walked": len(acc["done_pks"]),
             "stopped_reason": stopped, "elapsed_s": round(time.time() - t0, 1),
             "in_scope_games": acc["games"], "parse_errors": acc["parse_errors"],
             "pitcher_season_sport_keys": len(acc["per"])}
    SUB_STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return state


def _sub_load_acc() -> dict:
    import pickle
    with SUB_ACC_PATH.open("rb") as fh:
        return pickle.load(fh)


def _sub_pool_entries(entries: list[dict]) -> dict:
    out = _sub_new_entry()
    for e in entries:
        out["n_events"] += e["n_events"]
        out["n_tracked"] += e["n_tracked"]
        for pt, c in e["types"].items():
            out["types"][pt] = out["types"].get(pt, 0) + c
        for f in SUB_FIELDS:
            out[f"s_{f}"] += e[f"s_{f}"]
            out[f"n_{f}"] += e[f"n_{f}"]
        for m in _VAA_MOMENTS:
            out[m] += e[m]
    return out


def _sub_features(e: dict) -> dict:
    feat = {}
    for f in SUB_FIELDS:
        feat[f] = (e[f"s_{f}"] / e[f"n_{f}"]) if e[f"n_{f}"] else None
    total = sum(e["types"].values())
    feat["mix_entropy"] = (
        -sum((c / total) * math.log2(c / total)
             for c in e["types"].values() if c) if total else None)
    return feat


def _sub_outcomes(year: int) -> dict[int, dict]:
    """Next-season pooled MiLB outcomes across all kept sports."""
    agg: dict[int, dict] = {}
    for sport in SUB_SPORTS:
        p = MILB_STATS_DIR / f"pitching_{sport}_{year}.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text("utf-8")):
            if not r.get("mlbam"):
                continue
            a = agg.setdefault(int(r["mlbam"]),
                               {"ip": 0.0, "er": 0.0, "ip_era": 0.0,
                                "so": 0, "bf": 0})
            ip = _ip_float(r.get("ip")) or 0.0
            a["ip"] += ip
            era = _f(r.get("era"))
            if era is not None and ip > 0:
                a["er"] += era * ip / 9.0
                a["ip_era"] += ip
            a["so"] += int(r.get("so") or 0)
            a["bf"] += int(r.get("bf") or 0)
    return agg


def _sub_statline(season: int) -> dict[int, dict]:
    """Feature-season A/CPX stat line per pitcher: max-BF sport among
    14/16, rows aggregated within it (ridge features; line-4 conventions)."""
    per_sport: dict[int, dict[int, dict]] = {}
    for sport in SUB_FEATURE_SPORTS:
        p = MILB_STATS_DIR / f"pitching_{sport}_{season}.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text("utf-8")):
            if not r.get("mlbam"):
                continue
            a = per_sport.setdefault(int(r["mlbam"]), {}).setdefault(
                sport, {"bf": 0, "so": 0, "bb": 0, "er": 0.0, "ip_era": 0.0,
                        "age": None})
            a["bf"] += int(r.get("bf") or 0)
            a["so"] += int(r.get("so") or 0)
            a["bb"] += int(r.get("bb") or 0)
            ip = _ip_float(r.get("ip")) or 0.0
            era = _f(r.get("era"))
            if era is not None and ip > 0:
                a["er"] += era * ip / 9.0
                a["ip_era"] += ip
            if a["age"] is None and r.get("age") is not None:
                a["age"] = r["age"]
    out = {}
    for mid, sports in per_sport.items():
        sport, a = max(sports.items(), key=lambda kv: kv[1]["bf"])
        if a["bf"] < SUB_MIN_BF_STATLINE or a["ip_era"] <= 0:
            continue
        if a["age"] is None:
            continue
        out[mid] = {"sport": sport, "bf": a["bf"],
                    "k_pct_a": a["so"] / a["bf"],
                    "bb_pct_a": a["bb"] / a["bf"],
                    "era": 9.0 * a["er"] / a["ip_era"],
                    "age": float(a["age"])}
    return out


def _sub_ridge_universe() -> list[dict]:
    """FULL stat-line-eligible pair universe (feed-covered or not): the
    ridge training rows, with era_z within (sport, season) pools."""
    rows = []
    for s in (2023, 2024):
        lines = _sub_statline(s)
        nxt = _sub_outcomes(s + 1)
        pools: dict[int, list[float]] = {}
        for mid, r in lines.items():
            pools.setdefault(r["sport"], []).append(r["era"])
        stats = {}
        for sport, vals in pools.items():
            if len(vals) >= 20:
                m = sum(vals) / len(vals)
                sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
                if sd > 0:
                    stats[sport] = (m, sd)
        for mid, r in lines.items():
            o = nxt.get(mid)
            st = stats.get(r["sport"])
            if not o or o["ip"] < SUB_MIN_NEXT_IP or st is None:
                continue
            k_pct = (o["so"] / o["bf"]) if o["bf"] > 0 else None
            era = (9.0 * o["er"] / o["ip_era"]) if o["ip_era"] > 0 else None
            rows.append({"mid": mid, "season": s,
                         "x": [r["k_pct_a"], r["bb_pct_a"],
                               (r["era"] - st[0]) / st[1], r["age"]],
                         "k_pct": k_pct,
                         "era_inv": (-era) if era is not None else None})
    return rows


def _sub_ridge_crossfit(X, y, groups):
    """Verbatim reimplementation of tools/efv_statcast_line2_lab.py
    _ridge_crossfit (lambda 1.0, 5 player folds, permutation seed 20260723,
    train-fold standardization + centering). Reimplemented so this lab does
    not import that module (its import has os.chdir/scratch side effects)."""
    import numpy as np
    rng = np.random.default_rng(SUB_FOLD_SEED)
    uids = np.unique(groups)
    perm = rng.permutation(len(uids))
    fold_of = {uid: int(perm[i] % SUB_N_FOLDS) for i, uid in enumerate(uids)}
    fold = np.asarray([fold_of[g] for g in groups])
    yhat = np.full(len(y), np.nan)
    for f in range(SUB_N_FOLDS):
        tr, te = fold != f, fold == f
        if te.sum() == 0 or tr.sum() < 8:
            continue
        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd = np.where(sd == 0, 1.0, sd)
        xtr, xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        ym = float(y[tr].mean())
        a = xtr.T @ xtr + SUB_RIDGE_LAMBDA * np.eye(X.shape[1])
        beta = np.linalg.solve(a, xtr.T @ (y[tr] - ym))
        yhat[te] = ym + xte @ beta
    return yhat


def sub_build_sample():
    """(screen rows, qualifying-universe count, coverage diagnostics).
    Screen row = stat-line pair row that ALSO clears the tracked-feed
    floors; features from pooled A+CPX tracked pitches."""
    acc = _sub_load_acc()
    per = acc["per"]
    tracked_any: dict[tuple[int, int], int] = {}
    feature_entries: dict[tuple[int, int], list] = {}
    for (mid, season, sport), e in per.items():
        k = (mid, season)
        tracked_any[k] = tracked_any.get(k, 0) + e["n_tracked"]
        if sport in SUB_FEATURE_SPORTS:
            feature_entries.setdefault(k, []).append(e)
    universe = _sub_ridge_universe()
    rows = []
    n_no_feed = 0
    for u in universe:
        mid, s = u["mid"], u["season"]
        ents = feature_entries.get((mid, s))
        pooled = _sub_pool_entries(ents) if ents else None
        if (pooled is None or pooled["n_tracked"] < SUB_MIN_TRACKED
                or tracked_any.get((mid, s + 1), 0) < SUB_MIN_TRACKED):
            n_no_feed += 1
            continue
        feat = _sub_features(pooled)
        rows.append({"mlbam": mid, "season": s, "next_season": s + 1,
                     "feat": feat, "entry": pooled,
                     "x": u["x"], "k_pct": u["k_pct"],
                     "era_inv": u["era_inv"]})
    cov = {"qualifying_universe": len(universe),
           "screen_rows": len(rows),
           "covered_fraction": round(len(rows) / len(universe), 4)
           if universe else None,
           "dropped_feed_floors": n_no_feed}
    return rows, universe, cov


def _sub_attach_vaa(rows: list[dict]) -> dict:
    """Landing criterion + per-row vaa/vaaoe from the accumulated moments
    (pooled VAAOE normal-equation fit over covered feature rows)."""
    import numpy as np
    covered = [r for r in rows if r["entry"]["n_vaa"] >= VAA_MIN_PITCHES]
    coverage = len(covered) / len(rows) if rows else 0.0
    status = {"criterion": f">= {VAA_COVERAGE_BAR:.0%} of screen rows with "
                           f">= {VAA_MIN_PITCHES} VAA-computable pitches",
              "n_rows": len(rows), "n_covered": len(covered),
              "coverage": round(coverage, 4)}
    if coverage < VAA_COVERAGE_BAR:
        status["status"] = "absent"
        status["reason"] = "tracked-feed VAA coverage under the frozen bar"
        return status
    # pooled normal equations: sum over covered rows' pitches
    S = {m: sum(r["entry"][m] for r in covered) for m in _VAA_MOMENTS}
    A = np.array([[S["n_vaa"], S["s_pz"], S["s_z0"]],
                  [S["s_pz"], S["s_pz2"], S["s_pzz0"]],
                  [S["s_z0"], S["s_pzz0"], S["s_z02"]]])
    b = np.array([S["s_vaa"], S["s_vaapz"], S["s_vaaz0"]])
    coef = np.linalg.solve(A, b)
    for r in rows:
        e = r["entry"]
        if e["n_vaa"] >= VAA_MIN_PITCHES:
            mv = e["s_vaa"] / e["n_vaa"]
            r["feat"]["vaa"] = mv
            r["feat"]["vaaoe"] = mv - (coef[0] + coef[1] * e["s_pz"] / e["n_vaa"]
                                       + coef[2] * e["s_z0"] / e["n_vaa"])
        else:
            r["feat"]["vaa"] = None
            r["feat"]["vaaoe"] = None
    status["status"] = "landed"
    status["vaaoe_fit"] = {"intercept": round(float(coef[0]), 4),
                           "plate_z": round(float(coef[1]), 4),
                           "rel_ht_z0": round(float(coef[2]), 4),
                           "n_pitches": int(S["n_vaa"]),
                           "fit_pool": "all VAA-computable pitches of the "
                                       "covered screen feature rows"}
    return status


def _sub_screen_candidate(name: str, rows: list[dict], universe: list[dict]):
    """One sub-AAA candidate: line-4 ridge yhat (single cross-fit on the
    FULL universe), OLS-residualize feature + outcome on yhat over screen
    rows, Spearman, player-clustered bootstrap (OLS refit per rep, yhat
    fixed)."""
    import numpy as np
    from scipy.stats import spearmanr
    outcome = "k_pct" if name in SUB_K_FAMILY else "era_inv"
    uni = [u for u in universe if u.get(outcome) is not None]
    if len(uni) < 30:
        return {"outcome": outcome, "n": 0, "verdict": "FAIL",
                "reason": "ridge universe too small"}
    Xu = np.asarray([u["x"] for u in uni], float)
    yu = np.asarray([u[outcome] for u in uni], float)
    gu = np.asarray([u["mid"] for u in uni])
    yh = _sub_ridge_crossfit(Xu, yu, gu)
    yhat_map = {(u["mid"], u["season"]): float(yh[i])
                for i, u in enumerate(uni) if yh[i] == yh[i]}
    data = []
    for r in rows:
        f = r["feat"].get(name)
        h = yhat_map.get((r["mlbam"], r["season"]))
        y = r[outcome]
        if f is None or h is None or y is None:
            continue
        data.append((r["mlbam"], float(f), float(h), float(y)))
    n = len(data)
    if n < 30:
        return {"outcome": outcome, "n": n, "verdict": "FAIL",
                "reason": "insufficient rows (< 30)"}
    mids = np.array([d[0] for d in data])
    feat = np.array([d[1] for d in data])
    yhat = np.array([d[2] for d in data])
    y = np.array([d[3] for d in data])

    def _rho(idx):
        rf = _ols_resid(feat[idx], yhat[idx])
        ry = _ols_resid(y[idx], yhat[idx])
        if float(np.var(rf)) <= 0 or float(np.var(ry)) <= 0:
            return None
        r = spearmanr(rf, ry).statistic
        return None if (r != r) else float(r)

    rho = _rho(np.arange(n))
    clusters = np.unique(mids)
    idx_by = {c: np.flatnonzero(mids == c) for c in clusters}
    rng = np.random.default_rng(SEED)
    reps = []
    for _ in range(N_REPS):
        picks = rng.choice(clusters, size=len(clusters), replace=True)
        r_ = _rho(np.concatenate([idx_by[c] for c in picks]))
        if r_ is not None:
            reps.append(r_)
    reps = np.array(reps)
    if len(reps) < N_REPS // 2:
        return {"outcome": outcome, "n": n, "verdict": "FAIL",
                "reason": "degenerate bootstrap (under half the reps usable)"}
    lo95 = float(np.percentile(reps, 2.5))
    hi95 = float(np.percentile(reps, 97.5))
    verdict = "PASS" if (rho is not None and lo95 > 0) else "FAIL"
    if float(np.var(yhat)) > 0:
        slope = float(np.cov(yhat, feat, bias=True)[0, 1] / np.var(yhat))
    else:
        slope = 0.0
    inter = float(np.mean(feat)) - slope * float(np.mean(yhat))
    resid = feat - (inter + slope * yhat)
    oof_rho = float(spearmanr(yhat, y).statistic)
    return {"outcome": outcome, "n": n, "n_clusters": int(len(clusters)),
            "ridge_universe_n": int(len(uni)),
            "ridge_oof_spearman_vs_outcome": (round(oof_rho, 4)
                                              if oof_rho == oof_rho else None),
            "rho": round(rho, 4) if rho is not None else None,
            "lo95": round(lo95, 4), "hi95": round(hi95, 4),
            "n_reps_effective": int(len(reps)), "verdict": verdict,
            "resid_fit_on_yhat": {"intercept": round(inter, 6),
                                  "slope": round(slope, 6)},
            "resid_sd": round(float(np.std(resid)), 6),
            "feat_mean": round(float(np.mean(feat)), 6),
            "feat_sd": round(float(np.std(feat)), 6)}


def sub_screen() -> dict:
    """THE one-shot sub-AAA run. Appends the sub_aaa block to the existing
    W-SCREEN artifact; refuses if the block already exists."""
    if not OUT_PATH.exists():
        raise SystemExit("REFUSED: the AAA W-SCREEN artifact does not exist "
                         "yet - run --screen first (registered order).")
    artifact = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    if "sub_aaa" in artifact:
        raise SystemExit("REFUSED: sub_aaa block already present - "
                         "W-SCREEN-SUB is one shot and has been attempted.")
    state = (json.loads(SUB_STATE_PATH.read_text(encoding="utf-8"))
             if SUB_STATE_PATH.exists() else {})
    rows, universe, cov = sub_build_sample()
    vaa_status = _sub_attach_vaa(rows)
    judged = list(SUB_CANDIDATES)
    if vaa_status["status"] != "landed":
        judged = [c for c in judged if c not in ("vaa", "vaaoe")]
    results = {}
    for name in judged:
        results[name] = _sub_screen_candidate(name, rows, universe)
        log.info("[sub] %-12s %-7s n=%-4s rho=%-8s lo95=%-8s %s",
                 name, results[name]["outcome"], results[name]["n"],
                 results[name].get("rho"), results[name].get("lo95"),
                 results[name]["verdict"])
    survivors = {k: {kk: vv for kk, vv in v.items()
                     if kk in ("outcome", "n", "rho", "lo95", "hi95",
                               "resid_fit_on_yhat", "resid_sd",
                               "feat_mean", "feat_sd")}
                 for k, v in results.items() if v["verdict"] == "PASS"}
    block = {
        "registration": "docs/efv-2026-07-24/GATES.md W-SCREEN-SUB (owner "
                        "addendum 2026-07-23): A/CPX physics from cached "
                        "StatsAPI feeds, tracked parks only, one shot, "
                        "lo95 > 0, 2000 player-clustered reps seed "
                        "20260724; survivors feed W-OVERLAY-R "
                        "coverage-gated to tracked-park players",
        "one_shot": {"attempted_at": datetime.now(timezone.utc).isoformat(),
                     "note": "single attempt; the lab refuses a rerun while "
                             "this block exists"},
        "frozen_protocol": {
            "mapping": {"k_pct": list(SUB_K_FAMILY),
                        "era_inv": list(SUB_ERA_FAMILY)},
            "orientation": "outcomes higher-is-better (K% raw, ERA "
                           "negated); features natural units, no sign flips",
            "field_sources": "velo=startSpeed; ivb=breaks."
                             "breakVerticalInduced (Savant IVB convention); "
                             "hb_abs=|breaks.breakHorizontal|; spin=breaks."
                             "spinRate; rel_ht=coordinates.z0; tracked "
                             "pitch = startSpeed AND vY0 present; untracked "
                             "parks = absence, never imputed",
            "residualizer": "line-4 frozen stat-line ridge (lambda 1.0, 5 "
                            "player folds, fold permutation seed 20260723, "
                            "features k_pct_a/bb_pct_a/era_z/age_for_level "
                            "from the feature-season max-BF A/CPX stat "
                            "line, BF >= 150), trained on the FULL "
                            "stat-line-eligible pair universe predicting "
                            "the candidate family's raw outcome; feature "
                            "AND outcome OLS-residualized on the "
                            "out-of-fold yhat; bootstrap refits OLS only "
                            "(yhat fixed, the line-4 leakage guard)",
            "sample": "A/CPX pairs 2023->2024 + 2024->2025; >= 150 tracked "
                      "feed pitches both seasons (feature = pooled sports "
                      "14+16; season-2 = any cached sport); next-season "
                      "pooled MiLB >= 40 IP (sports 11-16 milb_stats)",
            "outcome_source": ".cache/milb_stats/pitching_{sport}_{year}"
                              ".json pooled across sports 11/12/13/14/15/16 "
                              "(promotion-proof destination); K% = SO/BF; "
                              "ERA = 9*sum(era*ip/9)/sum(ip); IP thirds "
                              "notation parsed",
            "bootstrap": f"{N_REPS} reps, cluster = mlbam, percentile CI, "
                         f"numpy default_rng({SEED}) fresh per candidate",
            "vaa": "formula = vaa.py calculate_vaa, y0 = per-pitch "
                   "coordinates.y0 else 50; vaaoe = residual on pooled "
                   "OLS(pZ, z0) via accumulated normal equations; landing "
                   f"bar >= 70 pct rows with >= {VAA_MIN_PITCHES} "
                   "computable pitches"},
        "extraction": state,
        "coverage": cov,
        "sample": {"n_rows": len(rows),
                   "n_pitchers": len({r["mlbam"] for r in rows}),
                   "pairs": {f"{a}->{a + 1}":
                             sum(1 for r in rows if r["season"] == a)
                             for a in (2023, 2024)}},
        "vaa_status": vaa_status,
        "candidates": results,
        "survivors": survivors,
    }
    artifact["sub_aaa"] = block
    OUT_PATH.write_text(json.dumps(artifact, indent=1) + "\n",
                        encoding="utf-8")
    log.info("wrote sub_aaa block -> %s (%d candidates, %d survivors)",
             OUT_PATH, len(results), len(survivors))
    return block


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--sample" in sys.argv:
        rows = build_sample()
        by = {}
        for r in rows:
            by.setdefault(f"{r['season']}->{r['next_season']}", []).append(r)
        print(json.dumps({
            "n_rows": len(rows),
            "n_pitchers": len({r["mlbam"] for r in rows}),
            "pairs": {k: len(v) for k, v in sorted(by.items())},
            "with_k": sum(1 for r in rows if r["k_pct"] is not None),
            "with_era": sum(1 for r in rows if r["era_inv"] is not None),
        }, indent=1))
    elif "--fetch-vaa" in sys.argv:
        budget = DEFAULT_BUDGET_S
        if "--budget-s" in sys.argv:
            budget = float(sys.argv[sys.argv.index("--budget-s") + 1])
        print(json.dumps(fetch_vaa(budget), indent=1))
    elif "--screen" in sys.argv:
        rep = screen()
        print(json.dumps({k: {"outcome": v["outcome"], "n": v["n"],
                              "rho": v.get("rho"), "lo95": v.get("lo95"),
                              "hi95": v.get("hi95"),
                              "verdict": v["verdict"]}
                          for k, v in rep["candidates"].items()}, indent=1))
        print("survivors:", sorted(rep["survivors"]))
        print("vaa_status:", rep["vaa_status"]["status"])
    elif "--sub-extract" in sys.argv:
        cap = SUB_EXTRACT_CAP_S
        if "--cap-s" in sys.argv:
            cap = float(sys.argv[sys.argv.index("--cap-s") + 1])
        print(json.dumps(sub_extract(cap), indent=1))
    elif "--sub-sample" in sys.argv:
        rows, universe, cov = sub_build_sample()
        print(json.dumps({
            "coverage": cov,
            "n_rows": len(rows),
            "n_pitchers": len({r["mlbam"] for r in rows}),
            "pairs": {f"{a}->{a + 1}":
                      sum(1 for r in rows if r["season"] == a)
                      for a in (2023, 2024)},
            "vaa_covered": sum(1 for r in rows
                               if r["entry"]["n_vaa"] >= VAA_MIN_PITCHES),
        }, indent=1))
    elif "--sub-screen" in sys.argv:
        blk = sub_screen()
        print(json.dumps({k: {"outcome": v["outcome"], "n": v["n"],
                              "rho": v.get("rho"), "lo95": v.get("lo95"),
                              "hi95": v.get("hi95"), "verdict": v["verdict"]}
                          for k, v in blk["candidates"].items()}, indent=1))
        print("sub survivors:", sorted(blk["survivors"]))
        print("sub vaa_status:", blk["vaa_status"]["status"])
    else:
        print("usage: --sample | --fetch-vaa [--budget-s N] | --screen | "
              "--sub-extract [--cap-s N] | --sub-sample | --sub-screen")
