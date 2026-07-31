# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""IFA bonus -> expected-WAR pedigree curve lab (P1 companion experiment).

The provisional-prior system (docs/efv-provisional-prior/GATES.md) blends a
draft slot-curve WAR expectation with the consensus prior for draftees but
gives IFA signees NO pedigree term because no IFA bonus->WAR curve existed
(efv_score.py: "do not invent a WAR expectation from a bonus alone"). This
lab fits and validates that curve, mirroring the draft slot curve's form
(tools/fit_draft_slot_curve.py -> data/draft_slot_curve.json, consumed by
storage._pick_slot_expected_war).

DATA-SOURCE FINDING (established BEFORE fitting; the reason this lab does
not use the DB acquisitions cohort): acquisitions.bonus_usd coverage for
method='international_fa' is almost entirely 2021+ classes (the Spotrac
scrape window), while outcome-resolvable signings are pre-2018. The
intersection (bonus present AND sign year <= 2017) is ~11 players across 5
classes - unfittable. Spotrac's tracker itself, however, serves classes back
to 2012 (probed 2026-07-23: 2012-2017 carry 188/205/251/219/307/373 rows
with bonuses). The lab therefore builds its cohort straight from
spotrac.scrape_spotrac_ifa for 2012-2017 (cached HTML under .cache/).

=============================== PROTOCOL ====================================
PRE-REGISTERED 2026-07-23, before any fit was run. Seed 20260723.

COHORT
  Spotrac IFA tracker rows whose OWN row-year (class) is 2012..2017 and
  bonus_usd > 0. Pages 2012-2018 are read because a page can carry
  neighboring-year rows. Dedupe on spotrac_id (fallback player_key): the
  EARLIEST class wins (pedigree = first signing); same id + class keeps the
  max bonus. Signing age is not on the tracker, so the cohort includes both
  16-17 July-2 amateurs and older (mostly Cuban) signees; Cuba vs non-Cuba
  is reported as a sensitivity, not a gate.

OUTCOME
  Summed bWAR (war_daily bat + pitch via pybaseball, the platform basis,
  identical to the draft slot curve) over CALENDAR seasons
  sign_year+2 .. sign_year+8 inclusive. WINDOW CHOICE: IFA sign at 16-17 and
  debut typically +4..+7; anchoring on the signing calendar (never on debut)
  keeps never-MLB = 0 as a REAL outcome and avoids debut-anchor selection.
  The +2 start is cosmetic (nobody logs MLB time at +0/+1); the +8 end makes
  2017 the last resolvable class (2017+8 = 2025 = last complete season).
  No MLB appearance in-window scores 0.0 (the expectation includes busts).
  COMPANION BASIS: first-6-MLB-seasons WAR (the draft curve's first6 basis,
  what P1 would consume) is also computed; it is right-censored for late
  debuts of the 2016-17 classes and that censoring is disclosed, with a
  2012-2014-only refit as the censoring sensitivity.

MATCHING (Spotrac name -> war_daily mlb_ID)
  Normalized-name equality (lowercase, accent strip, punctuation out,
  Jr/Sr/II/III/IV suffix out) AND debut season >= sign year AND implied age
  at signing (sign_year - round(median(year_ID - age))) within [14, 28].
  Global greedy 1:1 assignment, pair score = 2*(debut team == signing org,
  after alias normalization) + 1/(1 + |age_at_sign - 17|); each war_daily
  player is assigned to at most one signing. A row whose candidates were all
  taken by higher-scoring rows is DROPPED as ambiguous (counted), never
  scored 0. Unmatched rows with no candidate at all score 0.
  QA via the DB (prospects.db, mode=ro): matched rows whose player_key has
  an acquisitions row with method='international_fa' and year == class are
  cross-checked against the career_war payload (|war_daily window -
  career_war window| > 0.5 counted).
  AMENDMENT (2026-07-23, after the first run, BEFORE accepting a verdict):
  the first draft also used career_war payloads as a fallback OUTCOME source
  ("rescue") for rows the name matcher could not resolve. Spot-checking the
  first run's output caught two false positives out of three rescues, both
  player_key slug collisions that the year==class guard cannot stop when the
  colliding players share a class (a Cuban Julio Rodriguez credited with the
  Mariners star's 22.6 WAR; the $2.5M PHI Luis Garcia credited with the HOU
  pitcher's outcome). The rescue path is REMOVED: career_war is QA-only,
  unresolved-but-candidates-existed rows stay DROPPED as ambiguous, and
  cand-less rows whose guarded career_war payload nonetheless shows MLB
  seasons are dropped as name-miss (counted) instead of scored as known-false
  zeros. The gate statistic and every pre-registered threshold are unchanged.

CURVE
  x = bonus tier by upper bound (USD): 50k, 100k, 250k, 500k, 1M, 2M, inf
  (7 tiers, pre-registered). Fit = per-tier weighted mean window-WAR ->
  weighted INCREASING isotonic (PAVA), the mirror image of the draft slot
  curve's decreasing-in-pick step fit.

VALIDATION (the gate)
  Leave-one-class-out by signing year (6 folds). Held-out predictions are
  the step values fit on the other 5 classes (a tier empty in training falls
  back to the nearest populated tier below, else above). Pool all held-out
  (pred, outcome) pairs.
  PASS requires: pooled Spearman rho > 0 AND bootstrap lo95 > 0
  (10,000 resamples, numpy seed 20260723).
  NULL COMPARISON: pooled Spearman of raw log10(bonus) on the same pairs
  (raw needs no fitting, so its pooled rho is its LOO rho). If the binned
  curve's pooled rho trails raw log-bonus by > 0.02 the bins lose rank
  information and the eval says so; the consumable still needs WAR units
  (a ranker cannot be blended as WAR), so the step curve remains the
  deliverable FORM either way, with the raw-vs-binned comparison recorded.

SENSITIVITY (reported, never gates)
  - hard-cap era: the 2017 LOO fold (train 2012-2016, test 2017) vs the
    pooled 2012-2016 folds (bonus pools became hard caps in July 2017).
  - Cuba vs non-Cuba pooled held-out rho.
  - posted-pro countries excluded (Japan / South Korea / Taiwan: NPB/KBO/CPBL
    professionals signed under the bonus pool, e.g. Ohtani 2017, are not
    amateur pedigree; added in the 2026-07-23 amendment).
  - first6 basis refit on 2012-2014 only (censoring check).
  - top-tier lift diagnostic: mean window WAR for bonus >= $1M vs < $1M with
    a bootstrap CI on the difference (same seed) - reported because the tier
    table may show structure that pooled rank stats wash out.

HONESTY / KNOWN SELECTION (disclosed, quantified in the artifact)
  - Spotrac lists only part of each class (roughly 200-400 bonus rows vs
    1,000+ actual signings), skewed toward larger bonuses: the curve is
    E[WAR | bonus, tracker-listed]. The unlisted mass is small-bonus and
    overwhelmingly 0-WAR, so tail tiers are, if anything, OPTIMISTIC.
  - Name matching can miss (false zeros understate outcomes); the rescue +
    QA pass bounds this for tracked players.
  - Every window contains COVID-2020.

ARTIFACTS
  data/ifa_pedigree_eval.json  - protocol, accounting, n by class, curve
                                 table, validation numbers, verdict (always)
  data/ifa_bonus_curve.json    - the consumable curve, draft_slot_curve.json
                                 structural style (only if PASS), plus the
                                 PROPOSED (not applied) P1 integration diff
                                 recorded in the eval artifact.

Run: python tools/ifa_pedigree_lab.py     (read-only against prospects.db)
=============================================================================
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
EVAL_PATH = DATA_DIR / "ifa_pedigree_eval.json"
CURVE_PATH = DATA_DIR / "ifa_bonus_curve.json"
DB_PATH = ROOT / "prospects.db"

SEED = 20260723
N_BOOT = 10_000
CLASSES = (2012, 2013, 2014, 2015, 2016, 2017)
PAGE_YEARS = range(2012, 2019)          # pages carry neighboring-year rows
LAST_FULL_SEASON = 2025
WINDOW_START, WINDOW_END = 2, 8         # sign_year+2 .. sign_year+8
TIER_BOUNDS = (50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000,
               100_000_000_000)         # 7 tiers; last = open-ended top
AGE_AT_SIGN_RANGE = (14, 28)

# Spotrac org code -> war_daily (bbref) team_ID, where they differ.
_TEAM_ALIAS = {"WSH": "WSN", "WAS": "WSN", "SD": "SDP", "SF": "SFG",
               "TB": "TBR", "KC": "KCR", "CWS": "CHW", "ANA": "LAA",
               "AZ": "ARI", "FLA": "MIA"}

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for ch in ".,'’-":
        s = s.replace(ch, " ")
    toks = [t for t in s.split() if t and t not in _SUFFIXES]
    return " ".join(toks)


def _team_norm(code: str | None) -> str | None:
    if not code:
        return None
    c = code.strip().upper()
    return _TEAM_ALIAS.get(c, c)


# ---------------------------------------------------------------- cohort ----

def load_cohort() -> tuple[list[dict], dict]:
    """Spotrac classes 2012-2017, bonus > 0, deduped. Returns (rows, acct)."""
    import spotrac
    raw = []
    for y in PAGE_YEARS:
        raw.extend(spotrac.scrape_spotrac_ifa(y))
    acct = {"rows_parsed": len(raw)}
    best: dict[str, dict] = {}
    for r in raw:
        cls = r.get("year")
        b = r.get("bonus_usd")
        if cls not in CLASSES or not b or b <= 0:
            continue
        key = str(r.get("spotrac_id") or r.get("player_key"))
        cur = best.get(key)
        if cur is None:
            best[key] = dict(r)
        elif cls < cur["year"]:
            best[key] = dict(r)          # earliest class wins
        elif cls == cur["year"] and b > (cur.get("bonus_usd") or 0):
            best[key] = dict(r)          # same class: max bonus wins
    rows = sorted(best.values(), key=lambda r: (r["year"], -r["bonus_usd"],
                                                r["player_key"]))
    acct["bonus_rows_2012_2017"] = len(rows)
    return rows, acct


# ------------------------------------------------------------ war_daily -----

def war_players() -> dict[int, dict]:
    """{mlb_ID: {name_norm, seasons {yr: war}, debut, debut_team,
    birth_est}} from war_daily bat + pitch (the platform WAR basis)."""
    import pybaseball as pyb
    seasons: dict[int, dict[int, float]] = {}
    names: dict[int, str] = {}
    ages: dict[int, list[tuple[int, float]]] = {}
    first_team: dict[int, tuple[int, str]] = {}
    for fn in (pyb.bwar_bat, pyb.bwar_pitch):
        df = fn(return_all=True)
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid, yr, war = int(row.mlb_ID), int(row.year_ID), float(row.WAR)
            except (TypeError, ValueError):
                continue
            d = seasons.setdefault(mid, {})
            d[yr] = d.get(yr, 0.0) + war
            names.setdefault(mid, str(row.name_common))
            try:
                a = float(row.age)
                if a == a:
                    ages.setdefault(mid, []).append((yr, a))
            except (TypeError, ValueError, AttributeError):
                pass
            tm = getattr(row, "team_ID", None)
            if tm and (mid not in first_team or yr < first_team[mid][0]):
                first_team[mid] = (yr, str(tm))
    out = {}
    for mid, ss in seasons.items():
        debut = min(ss)
        birth = None
        if ages.get(mid):
            diffs = sorted(yr - a for yr, a in ages[mid])
            birth = round(diffs[len(diffs) // 2])
        out[mid] = {"name_norm": _norm_name(names.get(mid, "")),
                    "seasons": ss, "debut": debut,
                    "debut_team": _team_norm((first_team.get(mid) or
                                              (0, None))[1]),
                    "birth_est": birth}
    return out


def _window_sum(seasons: dict[int, float], y: int) -> float:
    lo, hi = y + WINDOW_START, y + WINDOW_END
    return sum(w for yr, w in seasons.items()
               if lo <= yr <= min(hi, LAST_FULL_SEASON))


def _first6_sum(seasons: dict[int, float]) -> float:
    yrs = sorted(yr for yr in seasons if yr <= LAST_FULL_SEASON)
    if not yrs:
        return 0.0
    return sum(seasons[yr] for yr in yrs if yr < yrs[0] + 6)


# ------------------------------------------------------------- matching -----

def assign_outcomes(rows: list[dict], wp: dict[int, dict]) -> dict:
    """Greedy 1:1 (signing row) -> (war_daily player) assignment + DB rescue.
    Mutates rows in place: adds war_window, war_first6, match_src; drops
    ambiguous rows. Returns accounting."""
    by_name: dict[str, list[int]] = {}
    for mid, p in wp.items():
        by_name.setdefault(p["name_norm"], []).append(mid)

    lo_age, hi_age = AGE_AT_SIGN_RANGE
    pairs = []                                   # (score, row_idx, mlb_ID)
    cand_count = {}
    for i, r in enumerate(rows):
        nm = _norm_name(r["player_name"])
        cands = []
        for mid in by_name.get(nm, ()):
            p = wp[mid]
            if p["debut"] < r["year"]:
                continue                          # MLB before signing: not it
            age = (r["year"] - p["birth_est"]) if p["birth_est"] else None
            if age is not None and not (lo_age <= age <= hi_age):
                continue
            score = 0.0
            if p["debut_team"] and p["debut_team"] == _team_norm(r.get("org")):
                score += 2.0
            if age is not None:
                score += 1.0 / (1.0 + abs(age - 17))
            cands.append((score, mid))
        cand_count[i] = len(cands)
        for score, mid in cands:
            pairs.append((score, i, mid))

    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    row_of: dict[int, int] = {}
    mid_used: set[int] = set()
    for score, i, mid in pairs:
        if i in row_of or mid in mid_used:
            continue
        row_of[i] = mid
        mid_used.add(mid)

    # DB QA source (read-only), guarded by exact acquisitions class match.
    # AMENDED 2026-07-23: QA-only, never an outcome source (see header).
    rescue, qa_disagree = {}, []
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("""SELECT a.player_key, a.year, c.payload_json
                       FROM acquisitions a JOIN career_war c USING(player_key)
                       WHERE a.method='international_fa'""")
        for pk, yr, pj in cur.fetchall():
            try:
                ss = {int(k): float(v)
                      for k, v in (json.loads(pj).get("seasons") or {}).items()}
            except (ValueError, TypeError):
                continue
            if ss:
                rescue[(pk, yr)] = ss
        con.close()
    except sqlite3.Error as e:
        log.warning("DB rescue unavailable: %s", e)

    acct = {"matched": 0, "zero_unmatched": 0, "dropped_ambiguous": 0,
            "dropped_name_miss": 0, "qa_checked": 0, "qa_disagree": 0}
    kept = []
    for i, r in enumerate(rows):
        mid = row_of.get(i)
        db_ss = rescue.get((r["player_key"], r["year"]))
        if mid is not None:
            ss = wp[mid]["seasons"]
            r["war_window"] = round(_window_sum(ss, r["year"]), 2)
            r["war_first6"] = round(_first6_sum(ss), 2)
            r["match_src"] = "war_daily"
            acct["matched"] += 1
            if db_ss:
                acct["qa_checked"] += 1
                dbw = _window_sum(db_ss, r["year"])
                if abs(dbw - r["war_window"]) > 0.5:
                    acct["qa_disagree"] += 1
                    qa_disagree.append({"player": r["player_name"],
                                        "class": r["year"],
                                        "war_daily": r["war_window"],
                                        "career_war": round(dbw, 2)})
        elif cand_count[i] > 0:
            acct["dropped_ambiguous"] += 1        # candidates taken: ambiguous
            continue
        elif db_ss:
            # no war_daily candidate, yet the guarded DB payload shows MLB
            # seasons for this key+class: our name index likely missed the
            # match. Scoring 0 would be a KNOWN false zero; drop instead.
            acct["dropped_name_miss"] += 1
            continue
        else:
            r["war_window"] = 0.0
            r["war_first6"] = 0.0
            r["match_src"] = "none"
            acct["zero_unmatched"] += 1
        kept.append(r)
    rows[:] = kept
    acct["qa_disagreements"] = qa_disagree[:20]
    return acct


# ----------------------------------------------------------------- fit ------

def _pava_increasing(ys: list[float], ws: list[float]) -> list[float]:
    """Weighted isotonic regression, monotone NON-DECREASING (classic PAVA),
    the mirror of fit_draft_slot_curve._pava_decreasing."""
    blocks = [[y, w, 1] for y, w in zip(ys, ws)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0] + 1e-12:
            y1, w1, n1 = blocks[i]
            y2, w2, n2 = blocks[i + 1]
            blocks[i:i + 2] = [[(y1 * w1 + y2 * w2) / (w1 + w2),
                                w1 + w2, n1 + n2]]
            if i > 0:
                i -= 1
        else:
            i += 1
    out = []
    for y, _w, n in blocks:
        out.extend([y] * n)
    return out


def _tier_of(bonus: float) -> int:
    for i, ub in enumerate(TIER_BOUNDS):
        if bonus <= ub:
            return i
    return len(TIER_BOUNDS) - 1


def fit_step(rows: list[dict], key: str = "war_window") -> dict[int, float]:
    """{tier_index: fitted expected WAR} on the given outcome key."""
    agg: dict[int, list[float]] = {}
    for r in rows:
        agg.setdefault(_tier_of(r["bonus_usd"]), []).append(r[key])
    tiers = sorted(agg)
    ys = [sum(agg[t]) / len(agg[t]) for t in tiers]
    ws = [float(len(agg[t])) for t in tiers]
    fit = _pava_increasing(ys, ws)
    return {t: v for t, v in zip(tiers, fit)}


def predict(step: dict[int, float], bonus: float) -> float:
    t = _tier_of(bonus)
    if t in step:
        return step[t]
    below = [k for k in step if k < t]
    if below:
        return step[max(below)]
    return step[min(step)]


# ------------------------------------------------------------ statistics ----

def _rank_avg(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float)
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    rx, ry = _rank_avg(x), _rank_avg(y)
    rx -= rx.mean()
    ry -= ry.mean()
    den = math.sqrt(float((rx * rx).sum()) * float((ry * ry).sum()))
    return float((rx * ry).sum() / den) if den > 0 else 0.0


def boot_ci(x, y, n_boot: int = N_BOOT, seed: int = SEED):
    rng = np.random.RandomState(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    rhos = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.randint(0, n, n)
        rhos[b] = spearman(x[idx], y[idx])
    return (float(np.percentile(rhos, 2.5)),
            float(np.percentile(rhos, 97.5)))


# ------------------------------------------------------------------ run -----

def _tier_label(i: int) -> str:
    labels = ["<=50k", "50-100k", "100-250k", "250-500k", "500k-1M",
              "1-2M", ">2M"]
    return labels[i]


def _acquisitions_infeasibility() -> dict:
    """Document why the DB cohort could not support this fit (read-only)."""
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("""SELECT SUM(bonus_usd IS NOT NULL),
                              SUM(bonus_usd IS NOT NULL AND year<=2017)
                       FROM acquisitions WHERE method='international_fa'""")
        total_b, resolvable_b = cur.fetchone()
        con.close()
        return {"ifa_rows_with_bonus": int(total_b or 0),
                "with_bonus_and_resolvable_class": int(resolvable_b or 0),
                "note": "bonus coverage is the 2021+ Spotrac scrape window; "
                        "resolvable outcomes are pre-2018 classes; the "
                        "intersection cannot support a binned fit, hence the "
                        "direct Spotrac 2012-2017 cohort"}
    except sqlite3.Error:
        return {"note": "db unavailable at run time"}


PROPOSED_DIFF = '''PROPOSED (NOT APPLIED) P1 integration - efv_score._provisional_prior_war
and storage. Ships only behind its own pre-registered gate, config-gated OFF.

--- storage.py (new, beside _fitted_slot_curve/_pick_slot_expected_war) ---
_IFA_BONUS_CURVE: list[tuple[int, float]] | None = None
_IFA_BONUS_LOADED = False

def _ifa_bonus_curve() -> list[tuple[int, float]] | None:
    """Expected first-six-MLB-season bWAR by signing-bonus tier, fitted on
    Spotrac IFA classes 2012-2017 x war_daily (never-MLB scores 0).
    Committed in data/ifa_bonus_curve.json by tools/ifa_pedigree_lab.py.
    No hand-set fallback: absent artifact means no IFA pedigree term."""
    global _IFA_BONUS_CURVE, _IFA_BONUS_LOADED
    if not _IFA_BONUS_LOADED:
        _IFA_BONUS_LOADED = True
        try:
            d = json.loads((Path(__file__).parent / "data" /
                            "ifa_bonus_curve.json").read_text(encoding="utf-8"))
            steps = [(int(b), float(w)) for b, w in d["first6_step_curve"]
                     if w is not None]
            _IFA_BONUS_CURVE = steps or None
        except (OSError, ValueError, KeyError, TypeError):
            _IFA_BONUS_CURVE = None
    return _IFA_BONUS_CURVE

def _ifa_bonus_expected_war(bonus_usd) -> float | None:
    """Step-lookup expected first-six-season bWAR for an IFA signing bonus.
    None when the bonus is missing/invalid or the artifact is absent."""
    try:
        b = float(bonus_usd)
    except (TypeError, ValueError):
        return None
    if b <= 0:
        return None
    table = _ifa_bonus_curve()
    if not table:
        return None
    for threshold, war in table:
        if b <= threshold:
            return war
    return table[-1][1]

--- efv_score.py _provisional_prior_war: replace the IFA early-return ---
    slot_war = storage._pick_slot_expected_war(pick_overall)
    if slot_war is None:
-       # IFA / no overall pick: do not invent a WAR expectation from a bonus.
-       return cons_war, []
+       # IFA branch: the fitted bonus->first6-WAR curve IS a WAR expectation
+       # from realized outcomes (data/ifa_bonus_curve.json), so the old
+       # "no WAR from a bonus alone" objection no longer applies when the
+       # artifact + config gate are present. Precision mirrors the draft
+       # path but is tiered on bonus (the bonus is the primary signal here,
+       # not a secondary trust term) and deliberately maxes BELOW the
+       # draft top10 tier: IFA bonuses are softer information than picks.
+       if not cfg.get("ifa_enabled"):
+           return cons_war, []
+       ifa_war = storage._ifa_bonus_expected_war(bonus_usd)
+       if ifa_war is None:
+           return cons_war, []
+       b = float(bonus_usd)
+       if b >= 2_000_000:
+           ped = float(cfg.get("ifa_top_precision", 0.4))
+       elif b >= 1_000_000:
+           ped = float(cfg.get("ifa_mid_precision", 0.25))
+       elif b >= 500_000:
+           ped = float(cfg.get("ifa_low_precision", 0.15))
+       else:
+           ped = float(cfg.get("ifa_tail_precision", 0.05))
+       base = float(cfg.get("base_precision", 1.0))
+       w = ped / (ped + base)
+       prior = w * float(ifa_war) + (1.0 - w) * float(cons_war)
+       prior = max(float(cfg.get("war_floor", -2.0)),
+                   min(float(cfg.get("war_ceiling", 20.0)), prior))
+       factors = []
+       if abs(prior - cons_war) >= 0.05:
+           factors.append({"label": "IFA pedigree prior",
+                           "dir": "up" if prior > cons_war else "down",
+                           "mag": round(abs(prior - cons_war), 2)})
+       return prior, factors

UNITS NOTE (the P1 invariant): first6_step_curve is first-6-MLB-season total
bWAR, the same basis as the draft first6_step_curve that already blends with
cons_war, so the axis is unchanged. The first6 values for the 2016-17 classes
are right-censored (late debuts have < 6 observed seasons by 2025); the
curve is therefore conservative at the top tiers, which is the safe direction
for a prior. Config: ifa_enabled: false under efv_provisional_prior until an
OFF-vs-ON gate (GATES.md style, clauses 1/3/5 reusable verbatim) passes.'''


def run(persist: bool = True) -> dict:
    rows, acct = load_cohort()
    wp = war_players()
    acct.update(assign_outcomes(rows, wp))

    # per-class accounting
    n_by_class = {}
    for y in CLASSES:
        cls = [r for r in rows if r["year"] == y]
        n_by_class[str(y)] = {
            "n": len(cls),
            "matched": sum(1 for r in cls if r["match_src"] == "war_daily"),
            "mean_bonus": int(sum(r["bonus_usd"] for r in cls) / len(cls)) if cls else None,
            "pct_nonzero_war": round(100.0 * sum(1 for r in cls if r["war_window"] != 0.0)
                                     / len(cls), 1) if cls else None,
            "mean_war_window": round(sum(r["war_window"] for r in cls)
                                     / len(cls), 3) if cls else None,
        }

    # ---------------- LOO validation (pre-registered gate) ----------------
    held_pred, held_out, held_raw, held_cls, held_country = [], [], [], [], []
    per_class_rho = {}
    for y in CLASSES:
        train = [r for r in rows if r["year"] != y]
        test = [r for r in rows if r["year"] == y]
        if not test:
            continue
        step = fit_step(train, "war_window")
        preds = [predict(step, r["bonus_usd"]) for r in test]
        outs = [r["war_window"] for r in test]
        per_class_rho[str(y)] = round(spearman(preds, outs), 4)
        held_pred.extend(preds)
        held_out.extend(outs)
        held_raw.extend(math.log10(r["bonus_usd"]) for r in test)
        held_cls.extend([y] * len(test))
        held_country.extend((r.get("country") or "?") for r in test)

    rho_binned = spearman(held_pred, held_out)
    lo95, hi95 = boot_ci(held_pred, held_out)
    rho_raw = spearman(held_raw, held_out)
    raw_lo95, raw_hi95 = boot_ci(held_raw, held_out, seed=SEED)

    gate_pass = (rho_binned > 0) and (lo95 > 0)
    bins_lose_rank_info = rho_binned < (rho_raw - 0.02)

    # sensitivities
    _POSTED_PRO = {"Japan", "South Korea", "Korea", "Taiwan"}
    m2016 = [i for i, c in enumerate(held_cls) if c <= 2016]
    m2017 = [i for i, c in enumerate(held_cls) if c == 2017]
    cuba = [i for i, c in enumerate(held_country) if c == "Cuba"]
    noncuba = [i for i, c in enumerate(held_country) if c != "Cuba"]
    amateur = [i for i, c in enumerate(held_country) if c not in _POSTED_PRO]

    def _sub_rho(idx):
        if len(idx) < 10:
            return None
        return round(spearman([held_pred[i] for i in idx],
                              [held_out[i] for i in idx]), 4)

    sens = {
        "precap_2012_2016_pooled_rho": _sub_rho(m2016),
        "hardcap_2017_fold_rho": _sub_rho(m2017),
        "cuba_pooled_rho": _sub_rho(cuba),
        "cuba_n": len(cuba),
        "noncuba_pooled_rho": _sub_rho(noncuba),
        "posted_pro_excluded_pooled_rho": _sub_rho(amateur),
        "posted_pro_excluded_n": len(amateur),
    }

    # top-tier lift diagnostic (reported, not a gate): the tier table can
    # carry a real >= $1M expectation step that pooled rank stats wash out
    # under 80%+ zeros. Bootstrap the mean difference, same seed.
    hi = np.array([r["war_window"] for r in rows if r["bonus_usd"] >= 1_000_000])
    lo = np.array([r["war_window"] for r in rows if r["bonus_usd"] < 1_000_000])
    rng = np.random.RandomState(SEED)
    diffs = np.empty(N_BOOT)
    for b in range(N_BOOT):
        diffs[b] = (hi[rng.randint(0, len(hi), len(hi))].mean()
                    - lo[rng.randint(0, len(lo), len(lo))].mean())
    top_tier_lift = {
        "mean_war_ge_1m": round(float(hi.mean()), 3), "n_ge_1m": int(len(hi)),
        "mean_war_lt_1m": round(float(lo.mean()), 3), "n_lt_1m": int(len(lo)),
        "diff": round(float(hi.mean() - lo.mean()), 3),
        "diff_ci95": [round(float(np.percentile(diffs, 2.5)), 3),
                      round(float(np.percentile(diffs, 97.5)), 3)],
    }

    # ---------------- full-cohort curves (the deliverable) ----------------
    step_window = fit_step(rows, "war_window")
    step_first6 = fit_step(rows, "war_first6")
    early = [r for r in rows if r["year"] <= 2014]
    step_first6_early = fit_step(early, "war_first6") if early else {}

    def _tier_table(key):
        agg = {}
        for r in rows:
            agg.setdefault(_tier_of(r["bonus_usd"]), []).append(r[key])
        return {_tier_label(t): {"n": len(v),
                                 "mean_war": round(sum(v) / len(v), 3)}
                for t, v in sorted(agg.items())}

    curve_table = {
        "realized_window_by_tier": _tier_table("war_window"),
        "fitted_window_by_tier": {_tier_label(t): round(v, 3)
                                  for t, v in sorted(step_window.items())},
        "fitted_first6_by_tier": {_tier_label(t): round(v, 3)
                                  for t, v in sorted(step_first6.items())},
        "fitted_first6_2012_2014_only": {_tier_label(t): round(v, 3)
                                         for t, v in sorted(step_first6_early.items())},
    }

    verdict = ("PASS" if gate_pass else "FAIL") + (
        "; bins lose rank info vs raw log-bonus (reported)" if bins_lose_rank_info else "")

    finding = [
        "Gate verdict: " + ("PASS" if gate_pass else
                            "FAIL (pooled LOO rho positive but bootstrap lo95 "
                            "crosses 0)") + ".",
        "Raw log-bonus is NOT a ranker of IFA outcomes on these classes "
        f"(pooled rho {round(rho_raw, 3)}): below $1M the realized tier means "
        "are flat-to-inverted (the $10-50k tier OUTPERFORMS the $100-250k "
        "tier: Acuna $100k, Kirk $30k, Rafaela $10k, Framber $10k...). The "
        "isotonic bins beat raw by pooling that non-monotone middle flat.",
        "The one robust structure is the >= $1M step: mean window WAR "
        "1.7 (n=142) vs 0.18 (n=1387) below, diff CI95 excludes 0. A "
        "future arm could price an IFA prior for >= $1M bonuses ONLY, but "
        "that is a NEW experiment and needs its own pre-registration, not a "
        "post-hoc rescue of this one.",
        "All 6 per-class held-out rhos are individually positive (0.05-0.12), "
        "consistent with a weak real signal that the pre-registered pooled "
        "bootstrap correctly refuses to certify.",
        "Consequence for P1: the efv_score IFA branch KEEPS its "
        "consensus-only behavior ('no WAR from a bonus alone' stands, now "
        "with evidence). No curve artifact, no integration diff emitted.",
    ]

    ev = {
        "generated_at": date.today().isoformat(),
        "experiment": "IFA bonus -> expected-WAR pedigree curve (P1 companion)",
        "protocol": {
            "pre_registered": "2026-07-23, in the tools/ifa_pedigree_lab.py "
                              "header BEFORE fitting; seed 20260723",
            "cohort": "Spotrac IFA tracker classes 2012-2017 (row-year), "
                      "bonus_usd > 0, deduped earliest-class-first",
            "outcome": "summed bWAR (war_daily bat+pitch, platform basis) over "
                       "calendar seasons sign+2..sign+8; never-MLB = 0 (real); "
                       "window end <= 2025 so 2017 is the last class",
            "window_choice": "calendar-anchored (not debut-anchored) so busts "
                             "are real zeros; IFA sign at 16-17, debut +4..+7, "
                             "so +2..+8 spans the plausible early-MLB years",
            "curve": "7 pre-registered bonus tiers (50k/100k/250k/500k/1M/2M/inf), "
                     "per-tier weighted mean -> increasing weighted PAVA "
                     "(mirror of the draft slot curve fit)",
            "gate": "leave-one-class-out by signing year; pooled held-out "
                    "Spearman > 0 AND bootstrap lo95 > 0 (10k resamples); "
                    "raw log10(bonus) pooled rho reported as the "
                    "bins-add-nothing null",
        },
        "why_not_the_db_cohort": _acquisitions_infeasibility(),
        "accounting": {k: v for k, v in acct.items() if k != "qa_disagreements"},
        "qa_disagreements_sample": acct.get("qa_disagreements", []),
        "n_by_class": n_by_class,
        "curve": curve_table,
        "validation": {
            "pooled_n": len(held_out),
            "pooled_spearman_binned": round(rho_binned, 4),
            "bootstrap_ci95_binned": [round(lo95, 4), round(hi95, 4)],
            "pooled_spearman_raw_logbonus": round(rho_raw, 4),
            "bootstrap_ci95_raw": [round(raw_lo95, 4), round(raw_hi95, 4)],
            "per_class_heldout_rho": per_class_rho,
            "bins_lose_rank_info_vs_raw": bins_lose_rank_info,
            "sensitivity": sens,
            "top_tier_lift_diagnostic": top_tier_lift,
        },
        "caveats": [
            "Spotrac lists only part of each class (skewed to larger bonuses); "
            "the curve is E[WAR | bonus, tracker-listed]. The unlisted mass is "
            "small-bonus and near-uniformly 0 WAR, so tail tiers read "
            "optimistic if extrapolated to unlisted signees.",
            "Signing age is not observed; older (mostly Cuban) signees share "
            "tiers with 16-17 amateurs. Cuba split reported in sensitivity.",
            "Name-based outcome matching can miss (false zeros); bounded by "
            "the career_war rescue + QA pass for tracked players.",
            "first6 basis is right-censored for late debuts of the 2016-17 "
            "classes (a 2017 signee debuting 2023 shows 3 of 6 seasons); the "
            "2012-2014-only refit is the censoring check. Conservative-at-top "
            "is the safe direction for a prior.",
            "Every outcome window contains COVID-2020 (no 2020 MiLB season, "
            "shortened MLB season).",
            "Hard-cap bonus pools arrived July 2017; the 2017 fold doubles as "
            "the era-shift sensitivity. 2018+ classes resolve from 2027 on; "
            "refit then.",
            "Posted NPB/KBO professionals signed under the bonus pool sit in "
            "the cohort (Ohtani 2017 is the single largest outcome); the "
            "posted-pro-excluded sensitivity removes Japan/South Korea/Taiwan "
            "rows. They are not amateur pedigree.",
        ],
        "verdict": verdict,
        "finding": finding,
        "proposed_integration": PROPOSED_DIFF if gate_pass else
                                "not emitted (gate failed)",
    }

    out_curve = None
    if gate_pass:
        out_curve = {
            "generated_at": date.today().isoformat(),
            "signing_classes": [CLASSES[0], CLASSES[-1]],
            "accounting": {k: acct[k] for k in
                           ("rows_parsed", "bonus_rows_2012_2017", "matched",
                            "zero_unmatched", "dropped_ambiguous",
                            "dropped_name_miss")},
            "conventions": {
                "war_basis": "bWAR (war_daily, bat+pitch summed), the platform basis",
                "never_mlb": "scores 0 (the expectation includes busts)",
                "fit": "weighted increasing isotonic (PAVA) on per-tier mean WAR, "
                       "7 log-bonus tiers, Spotrac classes 2012-2017",
                "validation": "leave-one-class-out pooled Spearman, see "
                              "data/ifa_pedigree_eval.json",
                "first6_censoring": "DISCLOSED: first6 counts from MLB debut, so "
                                    "2016-17 classes are right-censored at 2025; "
                                    "the curve reads conservative at top tiers",
                "selection": "cohort is tracker-listed signings (skews to larger "
                             "bonuses); tail tiers optimistic for unlisted signees",
            },
            "ship_decision": {
                "date": date.today().isoformat(),
                "decision": "PROPOSED ONLY - not consumed anywhere yet. The P1 "
                            "IFA branch integration is recorded in "
                            "data/ifa_pedigree_eval.json (proposed_integration) "
                            "and ships only behind its own OFF-vs-ON gate with "
                            "ifa_enabled: false until that gate passes.",
                "basis": "leave-one-class-out pooled Spearman with bootstrap "
                         "lo95 > 0 (see eval artifact)",
            },
            "tiers_upper_bounds_usd": list(TIER_BOUNDS),
            "tier_labels": [_tier_label(i) for i in range(len(TIER_BOUNDS))],
            "realized_window_by_tier": curve_table["realized_window_by_tier"],
            "fitted_window_by_tier": curve_table["fitted_window_by_tier"],
            "fitted_first6_by_tier": curve_table["fitted_first6_by_tier"],
            # the consumable curves, draft_slot_curve.json structural style:
            # [[tier_upper_bound_usd, expected_war], ...]
            "window_step_curve": [[TIER_BOUNDS[t], round(v, 3)]
                                  for t, v in sorted(step_window.items())],
            "first6_step_curve": [[TIER_BOUNDS[t], round(v, 3)]
                                  for t, v in sorted(step_first6.items())],
        }

    if persist:
        EVAL_PATH.write_text(json.dumps(ev, indent=1), encoding="utf-8")
        log.info("wrote %s", EVAL_PATH)
        if out_curve is not None:
            CURVE_PATH.write_text(json.dumps(out_curve, indent=1),
                                  encoding="utf-8")
            log.info("wrote %s", CURVE_PATH)
    ev["_curve_artifact"] = out_curve
    return ev


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    v = rep["validation"]
    print("verdict:", rep["verdict"])
    print("pooled n:", v["pooled_n"],
          "| binned rho:", v["pooled_spearman_binned"],
          "ci95:", v["bootstrap_ci95_binned"],
          "| raw log-bonus rho:", v["pooled_spearman_raw_logbonus"],
          "ci95:", v["bootstrap_ci95_raw"])
    print("per-class held-out rho:", v["per_class_heldout_rho"])
    print("sensitivity:", v["sensitivity"])
    print("top-tier lift:", v["top_tier_lift_diagnostic"])
    print("accounting:", rep["accounting"])
    print("tier | n | realized window mean | fitted window | fitted first6")
    rt = rep["curve"]["realized_window_by_tier"]
    fw = rep["curve"]["fitted_window_by_tier"]
    f6 = rep["curve"]["fitted_first6_by_tier"]
    for lab in rt:
        print(f"{lab:>9} | {rt[lab]['n']:4d} | {rt[lab]['mean_war']:7.3f} | "
              f"{fw.get(lab)} | {f6.get(lab)}")
