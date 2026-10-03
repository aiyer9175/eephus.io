"""Cohort-conditioned source accuracy: is "which source is best for THIS prospect" answerable?

The owner question is "which prospect source is most accurate for each position, for
pitchers versus hitters, for draft versus international, for each archetype". This module
answers it, and the answer for most cells is NOT ANSWERABLE AT THIS POWER. Publishing that
with its confidence intervals is the deliverable. No weight ships from here: nothing in this
file writes data/source_weights.json, data/draft_source_weights.json, or touches how
consensus.py computes anything.

Pre-registered in docs/efv-2026-08-09/COHORT_WEIGHT_GATE.md (accuracy, multiplicity, the
cohort A/B, the oracle ceiling, coverage selection) and
docs/efv-2026-08-09/SOURCE_PRECISION_GATE.md (the label-free precision route, calibration
drift). Both docs were written in full before this file existed.

ESTIMAND. For a cell c,

    d_rho(c) = rho_fangraphs(c) - rho_mlb_pipeline(c)

with rho = Spearman(preseason published FV, realized cumulative bWAR) on the COMMON set.
Negative means MLB Pipeline orders that cell better. A cell is ANSWERABLE only when
abs(d_rho) >= mde95, where mde95 = 1.96 * sd of a player bootstrap of d_rho. The sign of a
point estimate is not an answer.

BASIS. source_backtest is imported, never reimplemented, so every overlapping number
reproduces data/source_backtest.json exactly (test_source_cohort_accuracy asserts the six
archetype per-source Spearmans to 4 decimals). Resolved preseason window from
_resolved_years at MIN_LAG_YEARS 3 (2017 to 2023 on the 2026-08-09 export), common set
deduped to ONE ROW PER PLAYER at the latest pre-debut read, matching the dedup at
source_backtest.py:952-967. That dedup is load-bearing: the pooled common set carries one
row per base year and weights stable prospects up to 2.4x in the international bat cell,
which has already flipped a head-to-head AUC cell (OBS-1, 2026-07-24e).

LEVEL AT GRADING DOES NOT EXIST on this data. `snapshots` carries no level column,
`statlines` holds only season 2026, and timeseries `current_level` is a TODAY value that
would leak later development into a supposedly preseason cut. AGE AT GRADING (base year
minus birth year) is the substitute and the artifact says so. A level cut built from
`current_level` would be a defect, not an improvement.

Writes data/source_cohort_accuracy.json. Every failed arm is a BLOCK inside that one
artifact rather than a second *_eval.json, because a new data/*_eval.json without a
model_registry row fails the suite.
"""
from __future__ import annotations

import itertools
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import chi2, rankdata

from source_backtest import (
    ARCH_MIN_N,
    CANDIDATE_YEARS,
    CONSENSUS_KEY,
    FV_TIERS,
    MIN_LAG_YEARS,
    SCORED_SOURCES,
    SPEARMAN_FLOOR,
    WEIGHT_CLAMP,
    WEIGHT_SHRINK_K,
    _archetype,
    _ARCH_ORDER,
    _auc,
    _load_universe,
    _outcome,
    _PITCH_POS,
    _rater_grades_for_year,
    _resolved_years,
    _spearman,
    frozen_fv_tier_block,
    fv_tier_freeze_chip,
    fv_tier_frozen,
)

log = logging.getLogger("source_cohort_accuracy")

DATA_DIR = Path(__file__).parent / "data"
PRODUCED_BY = "source_cohort_accuracy.run_source_cohort_accuracy"

# Determinism (standing rule 6). One seed, fixed iteration orders taken from explicit
# tuples, never from a set and never from hash().
SEED = 20260809
BOOT_B = 2000          # player bootstrap draws per accuracy cell
PERM_B = 2000          # archetype-label permutations for the family-level test
COHORT_PERM_B = 200    # cohort-label permutations for the A/B control (refit per draw)
EM_BOOT_B = 200        # EM bootstrap draws; smaller than BOOT_B because each draw refits EM

# The INCUMBENT ship gate, lifted from source_backtest.run_consensus_weight_ab. This lane
# does not get to invent a friendlier floor for its own arm.
SHIP_MIN_RHO_GAIN = 0.0068
SHIP_MIN_AUC_GAIN = 0.0052

FANGRAPHS, PIPELINE = SCORED_SOURCES
# The only third instrument with published FVs on enough shared rows. This is a fact about
# the database, not a preference: espn/just_baseball/tjstats publish compressed ranges (see
# _precision_label_free) and are reported with a sigma and NO weight.
TRIAD = (FANGRAPHS, PIPELINE, "baseballamerica")
# Rows the THIRD instrument must carry before the measurement-error model is
# identified at all. Two sources are underdetermined regardless of n, so this
# is an identification floor, not a power floor: below it the block reports
# identified=False instead of estimating. 30 mirrors grade_normalization._MIN_N,
# the repo's existing "a cell this thin is not a measurement" threshold.
_PRECISION_MIN_TRIAD_ROWS = 30
RESTRICTED_SOURCES = ("espn", "just_baseball", "tjstats")
ALL_PRECISION_SOURCES = TRIAD + RESTRICTED_SOURCES

# Published FVs sit on a 5-point lattice. Sheppard's correction for a uniform quantizer is
# h^2/12. Reported as its own column and NEVER subtracted from a weight: the served
# aggregator observes the QUANTIZED grade, so that variance is real noise in the quantity
# being combined.
FV_LATTICE = 5.0
SHEPPARD_VARIANCE = FV_LATTICE ** 2 / 12.0

AGE_BUCKETS = (("<=18", None, 18), ("19-20", 19, 20), ("21-22", 21, 22),
               ("23-24", 23, 24), (">=25", 25, None))
POS_GROUPS = ("C", "IF", "OF", "SP", "RP", "P_unspecified", "other")
_IF_POS = {"1B", "2B", "3B", "SS", "IF", "INF"}
_OF_POS = {"OF", "LF", "CF", "RF", "COF"}
_RP_POS = {"RP", "SIRP", "MIRP"}


# --------------------------------------------------------------------------
# Vectorised stats. The pure-python source_backtest._spearman/_auc stay the
# authority for every published point estimate (that is how the artifact
# reproduces data/source_backtest.json); these are the bootstrap inner loop.
# _rho1 is asserted equal to _spearman on the full pool at run time.
# --------------------------------------------------------------------------
def _rho_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise Spearman for (B, n) matrices. Average ranks, matching _rankdata."""
    ra = rankdata(a, axis=1).astype(float)
    rb = rankdata(b, axis=1).astype(float)
    ra -= ra.mean(axis=1, keepdims=True)
    rb -= rb.mean(axis=1, keepdims=True)
    num = (ra * rb).sum(axis=1)
    den = np.sqrt((ra * ra).sum(axis=1) * (rb * rb).sum(axis=1))
    out = np.full(a.shape[0], np.nan)
    ok = den > 0
    out[ok] = num[ok] / den[ok]
    return out


def _rho1(a: np.ndarray, b: np.ndarray) -> float:
    return float(_rho_rows(np.asarray(a, float)[None, :], np.asarray(b, float)[None, :])[0])


def _auc1(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney AUC, ties at 0.5. Same statistic as source_backtest._auc."""
    labels = np.asarray(labels, bool)
    npos, nneg = int(labels.sum()), int((~labels).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    r = rankdata(np.asarray(scores, float))
    return float((r[labels].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def _r(v, nd=4):
    if v is None:
        return None
    v = float(v)
    return None if not np.isfinite(v) else round(v, nd)


def _boot_p(d_star: np.ndarray) -> float:
    """Two-sided bootstrap p for 'd differs from 0'. (count + 1) / (B + 1) on each tail so
    p is never exactly 0 at finite B."""
    d_star = d_star[np.isfinite(d_star)]
    if d_star.size == 0:
        return float("nan")
    b = d_star.size
    lo = (float((d_star <= 0).sum()) + 1.0) / (b + 1.0)
    hi = (float((d_star >= 0).sum()) + 1.0) / (b + 1.0)
    return float(min(1.0, 2.0 * min(lo, hi)))


def _holm(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """Holm-Bonferroni step-down. Family = the cells of ONE partition."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: (pvals[i] if np.isfinite(pvals[i]) else 2.0))
    out = [False] * m
    for rank_pos, i in enumerate(order):
        p = pvals[i]
        if not np.isfinite(p) or p > alpha / (m - rank_pos):
            break
        out[i] = True
    return out


# --------------------------------------------------------------------------
# Universe -> rows
# --------------------------------------------------------------------------
def _pos_group(pos_token: str) -> str:
    p = (pos_token or "").upper()
    if p == "C":
        return "C"
    if p in _IF_POS:
        return "IF"
    if p in _OF_POS:
        return "OF"
    if p == "SP":
        return "SP"
    if p in _RP_POS:
        return "RP"
    if p in _PITCH_POS:
        return "P_unspecified"
    return "other"


def _age_bucket(age: int | None) -> str | None:
    if age is None:
        return None
    for label, lo, hi in AGE_BUCKETS:
        if (lo is None or age >= lo) and (hi is None or age <= hi):
            return label
    return None


def _tier_label(fv: float) -> str:
    for lo, hi, label in FV_TIERS:
        if fv >= lo and (hi is None or fv < hi):
            return label
    return "<45"


def _build_common_rows(universe: list[dict], years: list[int]) -> tuple[list[dict], dict]:
    """Pooled common-set rows (one per player-year) plus each source's own-coverage rows.

    Common-set membership is source_backtest's rule verbatim: every rater graded the player
    that preseason. `own[s]` additionally keeps the rows only s graded, which the coverage
    block needs and which the accuracy blocks must never touch.
    """
    raters = list(SCORED_SOURCES) + [CONSENSUS_KEY]
    pooled: list[dict] = []
    own: dict[str, list[dict]] = {s: [] for s in SCORED_SOURCES}
    for p in universe:
        out = _outcome(p)
        key = p.get("player_key")
        pos_token = (p.get("position") or "").upper().split("/")[0]
        birth = (p.get("birth_date") or "")[:4]
        birth_year = int(birth) if birth.isdigit() else None
        arch = _archetype(p)
        method = (p.get("acquisition") or {}).get("method")
        for y in years:
            grades = _rater_grades_for_year(p, y)
            if not grades:
                continue
            for s in SCORED_SOURCES:
                if s in grades:
                    own[s].append({"key": key, "year": y, "fv": grades[s],
                                   "war": out["war"], "debuted": out["debuted"]})
            if not all(r in grades for r in raters):
                continue
            pooled.append({
                "key": key, "year": y,
                "fg": grades[FANGRAPHS], "mp": grades[PIPELINE],
                "cons": grades[CONSENSUS_KEY],
                "war": out["war"], "contributor": out["contributor"],
                "debuted": out["debuted"], "debut_year": out["debut_year"],
                "archetype": arch,
                "side": "arm" if pos_token in _PITCH_POS else "bat",
                "acquisition": ("draft_hs" if arch and arch.startswith("hs_") else
                                "draft_college" if arch and arch.startswith("college_") else
                                "international" if method == "international_fa" else None),
                "pos_group": _pos_group(pos_token),
                "age_at_grading": (y - birth_year) if birth_year else None,
            })
    return pooled, own


def _dedup_latest_predebut(rows: list[dict]) -> list[dict]:
    """ONE ROW PER PLAYER: the latest PRE-DEBUT read. Byte-identical in rule to
    source_backtest.py:952-967. A base year equal to the debut year is still a preseason
    read and stays eligible."""
    latest: dict = {}
    for c in rows:
        dy = c.get("debut_year")
        if dy is not None and (c.get("year") or 0) > dy:
            continue
        k = c.get("key")
        if k is None:
            continue
        if k not in latest or (c.get("year") or 0) > (latest[k].get("year") or 0):
            latest[k] = c
    return [latest[k] for k in sorted(latest)]


# --------------------------------------------------------------------------
# Block 1: accuracy by cohort
# --------------------------------------------------------------------------
def _cell(rows: list[dict], cell_index: int, min_n: int = ARCH_MIN_N) -> dict:
    """One partition cell: per-source rho, d_rho, player-bootstrap CI, MDE95, answerable.

    The bootstrap resamples PLAYERS. On the deduped basis one row is one player, so a row
    bootstrap and a cluster bootstrap coincide; the rows are still addressed by player so
    the property survives a future change of basis.
    """
    n = len(rows)
    fg = np.array([c["fg"] for c in rows], float)
    mp = np.array([c["mp"] for c in rows], float)
    cons = np.array([c["cons"] for c in rows], float)
    war = np.array([c["war"] for c in rows], float)
    contrib = np.array([c["contributor"] for c in rows], bool)

    rec: dict = {"n": n, "raters": {}}
    if n < min_n:
        rec["scored"] = False
        rec["note"] = f"n below the {min_n}-row floor ARCH_MIN_N sets; not scored"
        return rec
    rec["scored"] = True
    exact: dict = {}
    for name, vals in ((FANGRAPHS, fg), (PIPELINE, mp), (CONSENSUS_KEY, cons)):
        rho = _spearman(list(vals), list(war))
        auc = _auc(list(vals), list(contrib))
        exact[name] = rho
        rec["raters"][name] = {
            "n": n, "spearman": _r(rho), "auc": _r(auc),
            # Every rater here is scored on the rows it graded inside the common set, and
            # the consensus is a FUNCTION of the two sources, so its number is in-sample by
            # construction. Named on every row so no reader mistakes it for an OOS score.
            "basis": "in_sample_common_set",
        }
    rho_fg = exact[FANGRAPHS]
    rho_mp = exact[PIPELINE]
    if rho_fg is None or rho_mp is None:
        # _spearman returns None on a degenerate cell (every grade tied, or no outcome
        # spread). Position groups can hit this: the "other" bucket is small and its grades
        # can be constant. A degenerate cell is not scored rather than crashed on.
        rec["scored"] = False
        rec["note"] = "degenerate cell: a rank correlation is undefined on these rows"
        return rec
    # UNROUNDED, deliberately (2026-08-09b). This used to read the two published
    # `spearman` fields, which are rounded to 4 dp, so the estimand was quantized to
    # 1e-4 while the bootstrap CI and mde95 beside it were computed off unrounded
    # rhos: `answerable` compared a quantized point estimate against an unquantized
    # floor. Measured on the 2026-08-09 vintage, 25 of the 26 scored cells move
    # (pooled -0.02920 -> -0.02925, largest move 8e-5 at by_archetype:hs_bat) and
    # ZERO answerable verdicts flip, because the closest cell to its own mde95 sits
    # +0.01378 away (by_acquisition:draft_hs). So the defect was LATENT, not live.
    # Downstream, multiplicity.archetype_heterogeneity reads these values: Cochran Q
    # 6.4421 -> 6.4362, chi2_p 0.2655 -> 0.2661, weighted mean -0.02536 -> -0.02533,
    # tau2 0.000603 -> 0.000601, I2 22.4 -> 22.3 percent. No verdict there moves either.
    d_rho = float(rho_fg - rho_mp)

    rng = np.random.default_rng([SEED, cell_index])
    d_star = np.empty(BOOT_B)
    filled = 0
    while filled < BOOT_B:
        chunk = min(250, BOOT_B - filled)
        idx = rng.integers(0, n, size=(chunk, n))
        d_star[filled:filled + chunk] = (_rho_rows(fg[idx], war[idx])
                                         - _rho_rows(mp[idx], war[idx]))
        filled += chunk
    good = d_star[np.isfinite(d_star)]
    sd = float(good.std(ddof=1)) if good.size > 1 else float("nan")
    mde95 = 1.96 * sd
    answerable = bool(np.isfinite(mde95) and abs(d_rho) >= mde95)
    rec.update({
        "d_rho": _r(d_rho, 5),
        "d_rho_ci": [_r(np.percentile(good, 2.5), 5), _r(np.percentile(good, 97.5), 5)],
        "d_rho_boot_sd": _r(sd, 5),
        "mde95": _r(mde95, 5),
        "answerable": answerable,
        "boot_p_two_sided": _r(_boot_p(good), 4),
        "winner": (PIPELINE if (answerable and d_rho < 0) else
                   FANGRAPHS if (answerable and d_rho > 0) else "not_resolvable"),
        "boot_b": BOOT_B, "seed": SEED,
    })
    return rec


def _partition(rows: list[dict], key: str, order: tuple, start_index: int,
               min_n: int = ARCH_MIN_N) -> tuple[dict, int]:
    out = {}
    idx = start_index
    for label in order:
        cell = [c for c in rows if c.get(key) == label]
        if not cell:
            continue
        out[label] = _cell(cell, idx, min_n=min_n)
        idx += 1
    return out, idx


def _accuracy_block(ded: list[dict], frozen_tiers: dict | None = None) -> dict:
    """Six partitions plus the pooled cell. Cell indices are assigned from a FIXED order so
    the seeds do not move when a cell empties out. `frozen_tiers` (the served run under
    the FV-tier freeze) replaces the by_fv_tier partition with the frozen block."""
    idx = 0
    acc: dict = {}
    acc["pooled"] = _cell(ded, idx)
    idx += 1
    acc["by_side"], idx = _partition(ded, "side", ("bat", "arm"), idx)
    acc["by_acquisition"], idx = _partition(
        ded, "acquisition", ("draft_hs", "draft_college", "international"), idx)
    acc["by_archetype"], idx = _partition(ded, "archetype", _ARCH_ORDER, idx)
    acc["by_position_group"], idx = _partition(ded, "pos_group", POS_GROUPS, idx)
    # SELECTION CAVEAT, found in the run and not anticipated by the brief. The SP / RP /
    # SIRP / MIRP tokens are FanGraphs-authored ROLE designations, so the pitcher cut of
    # this partition conditions on a judgment made by one of the two graders being compared.
    # The RP cell is the only pitcher cell that resolves, and its rows are 27.0% debuted,
    # so the label is a projection of role and not a realized one. The SP cell cannot be
    # scored at all on this basis: all 50 of its deduped rows carry WAR 0 (none debuted),
    # so no rank correlation exists on either source.
    acc["by_position_group_selection_caveat"] = (
        "SP, RP, SIRP and MIRP are FanGraphs-authored role designations. Conditioning the "
        "pitcher cells on them conditions on one grader's own judgment, which is not a "
        "neutral partition of the population. The RP cell is 27.0 percent debuted, so the "
        "tag is projected role, not realized role. Read the RP result as a cut defined by "
        "FanGraphs rather than as a fact about relief prospects. Non-pitcher cells (C, IF, "
        "OF) do not carry this problem.")

    tier_order = tuple(label for _lo, _hi, label in FV_TIERS)
    for c in ded:
        c["fv_tier"] = _tier_label(c["cons"])
    if frozen_tiers is not None:
        # SERVED FROZEN (lane D E3-Q3 = A, 2026-10-02; source_backtest.fv_tier_frozen)
        # until the anchor look record exists: the block and its warning are copied
        # from data/efv_fv_tier_frozen.json. The cell index still advances by the
        # frozen cell count so the partitions after it keep their seeds.
        acc["by_fv_tier"] = frozen_tiers.get("by_fv_tier") or {}
        acc["by_fv_tier_range_restriction_warning"] = frozen_tiers.get(
            "by_fv_tier_range_restriction_warning")
        acc["by_fv_tier_freeze"] = fv_tier_freeze_chip("source_cohort_accuracy")
        idx += len(acc["by_fv_tier"])
    else:
        acc["by_fv_tier"], idx = _partition(ded, "fv_tier", tier_order, idx)
        tier_rhos = [v for t in acc["by_fv_tier"].values() if t.get("scored")
                     for v in (t["raters"][FANGRAPHS]["spearman"],
                               t["raters"][PIPELINE]["spearman"]) if v is not None]
        acc["by_fv_tier_range_restriction_warning"] = (
            "SCIENTIFICALLY WEAK, emitted with the warning attached rather than omitted. The "
            "tier is a bin on the CONSENSUS, which is a function of BOTH graders, so within a "
            "tier the two grades are nearly equal by construction. That is range restriction, "
            "and it drives every within-tier rho toward zero: observed range "
            f"{min(tier_rhos):.4f} to {max(tier_rhos):.4f} against a pooled "
            f"{acc['pooled']['raters'][FANGRAPHS]['spearman']:.4f} / "
            f"{acc['pooled']['raters'][PIPELINE]['spearman']:.4f}. Do not read these cells as "
            "evidence about tier-specific accuracy.")

    for c in ded:
        c["age_bucket"] = _age_bucket(c.get("age_at_grading"))
    acc["by_age_at_grading"], idx = _partition(
        ded, "age_bucket", tuple(b[0] for b in AGE_BUCKETS), idx)
    acc["level_at_grading"] = {
        "available": False,
        "substitute": "age_at_grading",
        "note": ("LEVEL AT GRADING DOES NOT EXIST on this data. snapshots carries no level "
                 "column, statlines holds only season 2026, and timeseries current_level is "
                 "a TODAY value whose use would leak post-grading development into a "
                 "preseason cut. Age at grading (base year minus birth year) is the "
                 "substitute. No level cut is invented."),
    }
    acc["cells_tested"] = idx
    return acc


# --------------------------------------------------------------------------
# Block 2: multiplicity
# --------------------------------------------------------------------------
def _multiplicity(acc: dict, ded: list[dict], pooled_rows: list[dict]) -> dict:
    partitions = ("by_side", "by_acquisition", "by_archetype", "by_position_group",
                  "by_fv_tier", "by_age_at_grading")
    per_partition = {}
    total_cells = 0
    total_flagged = 0
    survivors = []
    for part in partitions:
        cells = [(lab, c) for lab, c in acc[part].items() if c.get("scored")]
        if not cells:
            continue
        pv = [c["boot_p_two_sided"] for _lab, c in cells]
        keep = _holm(pv)
        for (lab, c), k in zip(cells, keep):
            c["survives_holm"] = bool(k)
            total_cells += 1
            if c["answerable"]:
                total_flagged += 1
            if k:
                survivors.append(f"{part}:{lab}")
        per_partition[part] = {
            "m": len(cells),
            "raw_flagged_answerable": sum(1 for _l, c in cells if c["answerable"]),
            "survives_holm": [lab for (lab, _c), k in zip(cells, keep) if k],
        }

    # Family-level heterogeneity on the six archetypes: inverse-bootstrap-variance weights,
    # Cochran Q against chi2 on k-1 df, plus the assumption-free permutation of the LABELS.
    arch = [(a, acc["by_archetype"][a]) for a in _ARCH_ORDER
            if a in acc["by_archetype"] and acc["by_archetype"][a].get("scored")]
    d = np.array([c["d_rho"] for _a, c in arch], float)
    v = np.array([c["d_rho_boot_sd"] ** 2 for _a, c in arch], float)
    w = 1.0 / v
    dbar = float((w * d).sum() / w.sum())
    q = float((w * (d - dbar) ** 2).sum())
    df = len(d) - 1
    s1, s2 = float(w.sum()), float((w * w).sum())
    tau2 = max(0.0, (q - df) / (s1 - s2 / s1)) if (s1 - s2 / s1) > 0 else 0.0
    i2 = max(0.0, (q - df) / q) if q > 0 else 0.0

    labels = [c["archetype"] for c in ded if c.get("archetype") in dict(arch)]
    lab_rows = [c for c in ded if c.get("archetype") in dict(arch)]
    fg = np.array([c["fg"] for c in lab_rows], float)
    mp = np.array([c["mp"] for c in lab_rows], float)
    war = np.array([c["war"] for c in lab_rows], float)
    lab_arr = np.array(labels)
    wmap = {a: w[i] for i, (a, _c) in enumerate(arch)}
    rng = np.random.default_rng([SEED, 9001])
    q_perm = np.empty(PERM_B)
    for b in range(PERM_B):
        perm = rng.permutation(lab_arr)
        dv, wv = [], []
        for a, _c in arch:
            m = perm == a
            dv.append(_rho1(fg[m], war[m]) - _rho1(mp[m], war[m]))
            wv.append(wmap[a])
        dv, wv = np.array(dv), np.array(wv)
        mu = (wv * dv).sum() / wv.sum()
        q_perm[b] = (wv * (dv - mu) ** 2).sum()
    perm_p = float(((q_perm >= q).sum() + 1.0) / (PERM_B + 1.0))

    # Base-year stability on the SAME two sources. A weight fitted on a quantity whose sign
    # is not stable across adjacent vintages is fitting noise, and this leg is disqualifying
    # on its own.
    per_year = []
    for y in sorted({c["year"] for c in pooled_rows}):
        yr = [c for c in pooled_rows if c["year"] == y]
        if len(yr) < ARCH_MIN_N:
            continue
        rf = _spearman([c["fg"] for c in yr], [c["war"] for c in yr])
        rm = _spearman([c["mp"] for c in yr], [c["war"] for c in yr])
        per_year.append({"year": y, "n": len(yr), "rho_fangraphs": _r(rf),
                         "rho_mlb_pipeline": _r(rm), "d_rho": _r(rf - rm, 5),
                         "sign": int(np.sign(rf - rm))})
    signs = [r["sign"] for r in per_year]
    flips = sum(1 for a, b in zip(signs, signs[1:]) if a != 0 and b != 0 and a != b)

    return {
        "cells_tested": total_cells,
        "cells_flagged_answerable": total_flagged,
        "expected_false_positives_at_alpha_05": _r(0.05 * total_cells, 2),
        "per_partition_holm": per_partition,
        "holm_survivors": survivors,
        # DERIVED, not hardcoded. This note used to say "three partitions" and
        # "Three survivors" in prose while the count beside it was interpolated
        # from the artifact. On 2026-08-11 hs_arm became a fourth survivor and
        # the page rendered "4 survive ... Three survivors is not three
        # independent findings" in one paragraph. The claim being made is about
        # OVERLAP, so it has to count the same list the page prints.
        "survivors_overlap_note": (
            "The survivors are largely THE SAME PLAYERS seen through "
            f"{len({s.split(':', 1)[0] for s in survivors})} partitions: a "
            "high-school arm is a draft-HS row and sits in a young age bucket. "
            f"{len(survivors)} survivors is not {len(survivors)} independent "
            "findings."),
        "archetype_heterogeneity": {
            "k": len(d), "df": df,
            "d_rho": {a: _r(c["d_rho"], 5) for a, c in arch},
            "weighted_mean_d_rho": _r(dbar, 5),
            "cochran_q": _r(q, 4),
            "chi2_p": _r(float(chi2.sf(q, df)), 4),
            "permutation_p_labels": _r(perm_p, 4),
            "permutation_draws": PERM_B,
            "tau2": _r(tau2, 6), "tau": _r(tau2 ** 0.5, 4),
            "i2_percent": _r(100.0 * i2, 1),
            "reading": ("Q p and the label permutation are the family-level test. A "
                        "survivor count is not one: 40 cells at alpha 0.05 produce about 2 "
                        "false positives by construction."),
        },
        "base_year_stability": {
            "per_year": per_year,
            "sign_flips_across_adjacent_vintages": flips,
            "note": ("d_rho on the pooled common set, one entry per base vintage, same two "
                     "sources throughout. The sign is the quantity a cohort weight would "
                     "have to be stable in."),
        },
    }


# --------------------------------------------------------------------------
# Block 3: the cohort A/B
# --------------------------------------------------------------------------
def _ab_rows(universe: list[dict], present_years: list[int]) -> list[dict]:
    """Rows the A/B derives weights from and scores on: every player-year in
    CANDIDATE_YEARS that BOTH scored sources graded. Same admission rule as
    source_backtest.derive_source_weights, which does NOT require the consensus."""
    rows = []
    for p in universe:
        out = _outcome(p)
        arch = _archetype(p)
        pos_token = (p.get("position") or "").upper().split("/")[0]
        for y in present_years:
            g = _rater_grades_for_year(p, y)
            if not g or not all(s in g for s in SCORED_SOURCES):
                continue
            rows.append({"key": p.get("player_key"), "year": y,
                         "fg": g[FANGRAPHS], "mp": g[PIPELINE],
                         "war": out["war"], "contributor": out["contributor"],
                         "archetype": arch or "unknown",
                         "side": "arm" if pos_token in _PITCH_POS else "bat"})
    return rows


def _raw_relative(rho_fg: float, rho_mp: float) -> float:
    """FanGraphs' relative-accuracy vote before shrink/clamp. With two sources
    raw_fg + raw_mp = 2 exactly, so the whole weight is one number."""
    a = max(SPEARMAN_FLOOR, rho_fg if rho_fg is not None else SPEARMAN_FLOOR)
    b = max(SPEARMAN_FLOOR, rho_mp if rho_mp is not None else SPEARMAN_FLOOR)
    return 2.0 * a / (a + b)


def _raw_variance(rho_fg: float, rho_mp: float, n: int) -> float:
    """Delta-method variance of raw_fg, treating the two rhos as independent. They are
    positively correlated (same outcome vector), so this OVERSTATES the variance, which
    makes the empirical-Bayes arm pool MORE. Stated because it biases the EB arm toward the
    global weight, i.e. toward the null this lane is testing against."""
    a = max(SPEARMAN_FLOOR, rho_fg if rho_fg is not None else SPEARMAN_FLOOR)
    b = max(SPEARMAN_FLOOR, rho_mp if rho_mp is not None else SPEARMAN_FLOOR)
    if n <= 4:
        return 1.0
    va = (1 - a * a) ** 2 / (n - 1)
    vb = (1 - b * b) ** 2 / (n - 1)
    s = (a + b) ** 2
    return float((2 * b / s) ** 2 * va + (2 * a / s) ** 2 * vb)


def _cohort_weights(train: list[dict], label_key: str, labels: tuple,
                    k: float, use_eb: bool) -> dict:
    """{cohort: alpha_fg} from pooled Spearman inside each cohort on the TRAIN vintage.

    Returns alphas (w_fg / (w_fg + w_mp)) rather than raw weights, because a two-source
    blend depends only on that ratio. The shipped clamp is applied in weight space first so
    the arm inherits the incumbent's clamp exactly.
    """
    fgv = np.array([r["fg"] for r in train], float)
    mpv = np.array([r["mp"] for r in train], float)
    war = np.array([r["war"] for r in train], float)
    lab = np.array([r[label_key] for r in train])
    n_all = len(train)
    if n_all < 60:
        return {}
    g_raw = _raw_relative(_rho1(fgv, war), _rho1(mpv, war))

    per: dict[str, tuple[float, int, float]] = {}
    for c in labels:
        m = lab == c
        n_c = int(m.sum())
        if n_c < 60:
            continue
        rf, rm = _rho1(fgv[m], war[m]), _rho1(mpv[m], war[m])
        per[c] = (_raw_relative(rf, rm), n_c, _raw_variance(rf, rm, n_c))

    if use_eb and len(per) >= 2:
        raws = np.array([per[c][0] for c in sorted(per)])
        vs = np.array([per[c][2] for c in sorted(per)])
        tau2 = max(0.0, float(raws.var(ddof=1) - vs.mean()))
        for c in sorted(per):
            raw, n_c, v_c = per[c]
            lam = tau2 / (tau2 + v_c) if (tau2 + v_c) > 0 else 0.0
            per[c] = (g_raw + lam * (raw - g_raw), n_c, v_c)

    out = {}
    for c in sorted(per):
        raw, n_c, _v = per[c]
        w_fg = (n_c * raw + k * 1.0) / (n_c + k)
        w_mp = (n_c * (2.0 - raw) + k * 1.0) / (n_c + k)
        w_fg = min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], w_fg))
        w_mp = min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], w_mp))
        out[c] = w_fg / (w_fg + w_mp)
    # The global fallback, used for cohorts with no vintage-legal history and for the
    # "unknown" cohort. Falling back to the global weight is what a deployment would do.
    w_fg = (n_all * g_raw + k) / (n_all + k)
    w_mp = (n_all * (2.0 - g_raw) + k) / (n_all + k)
    w_fg = min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], w_fg))
    w_mp = min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], w_mp))
    out["__global__"] = w_fg / (w_fg + w_mp)
    return out


def _score_ab(rows: list[dict], years: list[int], label_key: str, labels: tuple,
              k: float, use_eb: bool, recentre: bool) -> dict:
    """One A/B arm. VINTAGE RULE identical to run_consensus_weight_ab: weights for board
    year Y see only base years <= Y - MIN_LAG_YEARS."""
    eq_all, wt_all, war_all, con_all, yrs_used = [], [], [], [], []
    per_year = []
    for Y in years:
        vintage_max = Y - MIN_LAG_YEARS
        train = [r for r in rows if r["year"] <= vintage_max]
        alphas = _cohort_weights(train, label_key, labels, k, use_eb)
        if not alphas or all(abs(a - 0.5) < 1e-12 for a in alphas.values()):
            continue      # flat weights cannot differentiate A from B; skip the year
        score = [r for r in rows if r["year"] == Y]
        if len(score) < ARCH_MIN_N:
            continue
        eq = np.array([(r["fg"] + r["mp"]) / 2.0 for r in score], float)
        a_row = np.array([alphas.get(r[label_key], alphas["__global__"]) for r in score])
        wt = a_row * np.array([r["fg"] for r in score], float) + \
            (1 - a_row) * np.array([r["mp"] for r in score], float)
        if recentre:
            # Cross-cohort recentring: inside each cohort, affine-map the weighted blend to
            # the equal blend's mean and sd. Uses GRADES ONLY (no outcome), so it is legal
            # at board time. It exists because consensus FV is a globally comparable number
            # and cohort-specific mixing breaks that comparability (see oracle_ceiling).
            lab = np.array([r[label_key] for r in score])
            for c in sorted(set(lab.tolist())):
                m = lab == c
                if m.sum() < 5:
                    continue
                sw, se = wt[m].std(), eq[m].std()
                if sw <= 1e-9:
                    continue
                wt[m] = eq[m].mean() + (wt[m] - wt[m].mean()) * (se / sw)
        war = np.array([r["war"] for r in score], float)
        con = np.array([r["contributor"] for r in score], bool)
        per_year.append({"year": Y, "n": len(score), "weights_vintage_max_base": vintage_max,
                         "alpha_fg": {c: _r(a, 4) for c, a in sorted(alphas.items())},
                         "equal": {"spearman": _r(_rho1(eq, war)), "auc": _r(_auc1(eq, con))},
                         "weighted": {"spearman": _r(_rho1(wt, war)), "auc": _r(_auc1(wt, con))}})
        eq_all.append(eq)
        wt_all.append(wt)
        war_all.append(war)
        con_all.append(con)
        yrs_used.append(Y)
    if not eq_all:
        return {"scored_years": [], "ship": False, "note": "no year had vintage-legal weights"}
    eq = np.concatenate(eq_all)
    wt = np.concatenate(wt_all)
    war = np.concatenate(war_all)
    con = np.concatenate(con_all)
    d_rho = _rho1(wt, war) - _rho1(eq, war)
    d_auc = _auc1(wt, con) - _auc1(eq, con)
    return {
        "scored_years": yrs_used, "pooled_n": int(eq.size),
        "equal": {"spearman": _r(_rho1(eq, war)), "auc": _r(_auc1(eq, con))},
        "weighted": {"spearman": _r(_rho1(wt, war)), "auc": _r(_auc1(wt, con))},
        "d_rho": _r(d_rho, 5), "d_auc": _r(d_auc, 5),
        "gate": {"min_d_rho": SHIP_MIN_RHO_GAIN, "min_d_auc": SHIP_MIN_AUC_GAIN},
        "ship": bool(d_rho >= SHIP_MIN_RHO_GAIN and d_auc >= SHIP_MIN_AUC_GAIN),
        "per_year": per_year,
    }


def _cohort_ab(universe: list[dict], present_years: list[int], years: list[int]) -> dict:
    rows = _ab_rows(universe, present_years)
    arch_labels = _ARCH_ORDER + ("unknown",)
    side_labels = ("bat", "arm")
    variants = (
        ("archetype_shrunk", "archetype", arch_labels, WEIGHT_SHRINK_K, False, False),
        ("archetype_eb", "archetype", arch_labels, WEIGHT_SHRINK_K, True, False),
        ("archetype_recentre", "archetype", arch_labels, WEIGHT_SHRINK_K, False, True),
        ("archetype_eb_recentre", "archetype", arch_labels, WEIGHT_SHRINK_K, True, True),
        ("side_shrunk", "side", side_labels, WEIGHT_SHRINK_K, False, False),
        ("side_recentre", "side", side_labels, WEIGHT_SHRINK_K, False, True),
    )
    arms = {}
    for name, key, labels, k, eb, rc in variants:
        arms[name] = _score_ab(rows, years, key, labels, k, eb, rc)
    scored = [(n, a) for n, a in arms.items() if a.get("d_rho") is not None]
    if not scored:
        # No board year had vintage-legal cohort weights, so there is no arm to control or
        # to sweep. The block still reports the gate and the alpha mapping: a lane that
        # cannot run its A/B says so rather than emitting a half-populated result.
        lo, hi = WEIGHT_CLAMP
        return {"rows_n": len(rows), "arms": arms, "best_arm": None, "ship": False,
                "note": "no board year had vintage-legal cohort weights; the A/B did not run",
                "gate": {"min_d_rho": SHIP_MIN_RHO_GAIN, "min_d_auc": SHIP_MIN_AUC_GAIN},
                "alpha_parameterisation": {
                    "definition": "alpha = w_fg / (w_fg + w_mp)",
                    "shipped_clamp": list(WEIGHT_CLAMP),
                    "implied_alpha_range": [_r(lo / (lo + hi), 4), _r(hi / (hi + lo), 4)]}}
    best_name, best = max(scored, key=lambda kv: kv[1]["d_rho"])

    # CONTROL. Permute the COHORT LABELS across rows and REFIT the weights per draw. If
    # random labels do as well as real ones, the arm measures the fitting procedure.
    key, labels, k, eb, rc = next((v[1], v[2], v[3], v[4], v[5])
                                  for v in variants if v[0] == best_name)
    lab_arr = np.array([r[key] for r in rows])
    rng = np.random.default_rng([SEED, 7001])
    null = np.empty(COHORT_PERM_B)
    for b in range(COHORT_PERM_B):
        perm = rng.permutation(lab_arr)
        prows = [dict(r, **{key: perm[i]}) for i, r in enumerate(rows)]
        res = _score_ab(prows, years, key, labels, k, eb, rc)
        null[b] = res.get("d_rho") if res.get("d_rho") is not None else np.nan
    null = null[np.isfinite(null)]
    obs = best["d_rho"]
    perm_p = float(((null >= obs).sum() + 1.0) / (null.size + 1.0))

    sens = []
    for kk in (0, 25, 50, 150, 400, 1000):
        res = _score_ab(rows, years, key, labels, float(kk), eb, rc)
        sens.append({"k": kk, "d_rho": res.get("d_rho"), "d_auc": res.get("d_auc")})
    mono_rho = all(a["d_rho"] <= b["d_rho"] for a, b in zip(sens, sens[1:])
                   if a["d_rho"] is not None and b["d_rho"] is not None)
    mono_auc = all(a["d_auc"] <= b["d_auc"] for a, b in zip(sens, sens[1:])
                   if a["d_auc"] is not None and b["d_auc"] is not None)
    # Strict monotonicity is brittle at this effect size (the whole k grid spans about
    # 1e-3, i.e. a seventh of the ship gate), so the trend is also reported as a rank
    # correlation against k. That is the statement that survives a single 8e-5 dip.
    kk_grid = np.array([s["k"] for s in sens], float)
    trend_rho = _rho1(kk_grid, np.array([s["d_rho"] for s in sens], float))
    trend_auc = _rho1(kk_grid, np.array([s["d_auc"] for s in sens], float))

    lo, hi = WEIGHT_CLAMP
    return {
        "rows_n": len(rows),
        "vintage_rule": f"weights for board year Y use base years <= Y - {MIN_LAG_YEARS} only",
        "gate": {"min_d_rho": SHIP_MIN_RHO_GAIN, "min_d_auc": SHIP_MIN_AUC_GAIN,
                 "source": "source_backtest.run_consensus_weight_ab incumbent constants"},
        "arms": arms,
        "best_arm": best_name,
        "ship": bool(any(a.get("ship") for a in arms.values())),
        "permutation_control": {
            "target_arm": best_name, "draws": int(null.size),
            "permuted": "cohort labels across rows, weights refit per draw",
            "null_mean": _r(float(null.mean()), 5), "null_sd": _r(float(null.std(ddof=1)), 5),
            "null_p95": _r(float(np.percentile(null, 95)), 5),
            "observed_d_rho": _r(obs, 5), "p": _r(perm_p, 4),
            "reading": ("p is the share of RANDOM cohort labelings that match or beat the "
                        "real one. Above 0.5 means random labels do better."),
        },
        "shrink_sensitivity": {
            "arm": best_name, "k_grid": sens,
            "monotone_increasing_in_k_rho": bool(mono_rho),
            "monotone_increasing_in_k_auc": bool(mono_auc),
            "rank_corr_k_vs_d_rho": _r(trend_rho),
            "rank_corr_k_vs_d_auc": _r(trend_auc),
            "reading": ("Improvement as k grows toward equal weight is the signature of "
                        "zero signal: the best amount of the weight is none of it. The two "
                        "estimands trend in OPPOSITE directions here, and the whole grid "
                        "spans about 1e-3 against a 0.0068 gate, so neither trend is a "
                        "result on its own."),
        },
        "alpha_parameterisation": {
            "definition": "alpha = w_fg / (w_fg + w_mp); a two-source blend depends only on this ratio",
            "shipped_clamp": list(WEIGHT_CLAMP),
            "implied_alpha_range": [_r(lo / (lo + hi), 4), _r(hi / (hi + lo), 4)],
            "note": ("The clamp is stored in weight space and nowhere translated. In alpha "
                     "space it is the interval recorded here, which is what actually bounds "
                     "the blend."),
        },
    }


# --------------------------------------------------------------------------
# Block 4: oracle ceiling
# --------------------------------------------------------------------------
_ALPHA_GRID = np.round(np.arange(0.0, 1.0005, 0.005), 4)


def _best_alpha(fg: np.ndarray, mp: np.ndarray, war: np.ndarray) -> tuple[float, float]:
    best_a, best_r = 0.5, -2.0
    for a in _ALPHA_GRID:
        r = _rho1(a * fg + (1 - a) * mp, war)
        if np.isfinite(r) and r > best_r:
            best_a, best_r = float(a), float(r)
    return best_a, best_r


def _oracle(rows: list[dict], label_key: str, labels: tuple, tag: str) -> dict:
    fg = np.array([r["fg"] for r in rows], float)
    mp = np.array([r["mp"] for r in rows], float)
    war = np.array([r["war"] for r in rows], float)
    lab = np.array([r.get(label_key) or "unknown" for r in rows])
    eq = _rho1(0.5 * fg + 0.5 * mp, war)
    a_star, r_star = _best_alpha(fg, mp, war)

    per_cohort = {}
    a_row = np.full(len(rows), a_star)
    for c in labels:
        m = lab == c
        if m.sum() < ARCH_MIN_N:
            continue
        ac, rc = _best_alpha(fg[m], mp[m], war[m])
        per_cohort[c] = {"n": int(m.sum()), "oracle_alpha": _r(ac, 4),
                         "within_rho": _r(rc), "equal_rho": _r(_rho1(0.5 * fg[m] + 0.5 * mp[m], war[m])),
                         "within_gain": _r(rc - _rho1(0.5 * fg[m] + 0.5 * mp[m], war[m]), 5)}
        a_row[m] = ac
    pooled_cohort_rho = _rho1(a_row * fg + (1 - a_row) * mp, war)
    # The comparability arithmetic, stated as two numbers rather than as a claim: how much
    # of the within-cohort oracle gain survives being scored POOLED. Consensus FV is a
    # globally comparable number; cohort-specific mixing moves each cohort's level and
    # scale, so ordering bought inside a cohort is paid for across cohorts.
    n_cov = sum(v["n"] for v in per_cohort.values())
    within = (sum(v["n"] * v["within_gain"] for v in per_cohort.values()) / n_cov
              if n_cov else float("nan"))
    pooled_gain = pooled_cohort_rho - eq
    return {
        "basis": tag, "n": len(rows),
        "equal_rho": _r(eq),
        "global_oracle_alpha": _r(a_star, 4),
        "global_oracle_rho": _r(r_star),
        "global_oracle_gain": _r(r_star - eq, 5),
        "global_oracle_gain_vs_ship_gate": _r(r_star - eq - SHIP_MIN_RHO_GAIN, 5),
        "global_oracle_clears_ship_gate": bool((r_star - eq) >= SHIP_MIN_RHO_GAIN),
        "per_cohort": per_cohort,
        "cohort_oracle_pooled_rho": _r(pooled_cohort_rho),
        "cohort_oracle_pooled_gain": _r(pooled_gain, 5),
        "cohort_oracle_within_gain_n_weighted": _r(within, 5),
        "cohort_oracle_share_surviving_pooling": (
            _r(pooled_gain / within, 4) if within and np.isfinite(within) and within > 0 else None),
        "cohort_oracle_clears_ship_gate": bool(pooled_gain >= SHIP_MIN_RHO_GAIN),
        "corr_fg_mp_pearson": _r(float(np.corrcoef(fg, mp)[0, 1])),
        "sd_fangraphs": _r(float(fg.std(ddof=1))),
        "sd_mlb_pipeline": _r(float(mp.std(ddof=1))),
        "geometry_note": (
            "Two near-collinear predictors of similar scale have a nearly flat response "
            "surface in the mixing weight. A flat oracle is GEOMETRY, not sample size, and "
            "more base years cannot change it. Where the cohort oracle scores NEGATIVE "
            "pooled while every within-cohort oracle is non-negative, cohort-specific "
            "mixing has broken the global comparability of consensus FV faster than it "
            "bought within-cohort ordering."),
    }


# --------------------------------------------------------------------------
# Block 5: label-free precision
# --------------------------------------------------------------------------
def _precision_rows(universe: list[dict]) -> list[dict]:
    """One row per (player, board year) carrying each source's max published FV that year.

    NOT restricted to the preseason window, unlike the accuracy blocks. Precision uses no
    outcome, so there is no lookahead to guard against, and the window would cut Just
    Baseball from 126 usable rows to 26 (it publishes in season), which would decide the
    range-restriction question by sampling rather than by measurement.
    """
    rows = []
    for p in universe:
        per: dict[tuple[int, str], float] = {}
        for pt in (p.get("points") or []):
            sd = pt.get("snapshot_date")
            if not sd:
                continue
            try:
                y = int(sd[:4])
            except (TypeError, ValueError):
                continue
            for s, ps in (pt.get("per_source") or {}).items():
                if s not in ALL_PRECISION_SOURCES:
                    continue
                v = (ps or {}).get("fv_published")
                if v is None:
                    continue
                k = (y, s)
                per[k] = max(per[k], float(v)) if k in per else float(v)
        for y in sorted({k[0] for k in per}):
            rec = {"key": p.get("player_key"), "year": y,
                   "archetype": _archetype(p)}
            for s in ALL_PRECISION_SOURCES:
                if (y, s) in per:
                    rec[s] = per[(y, s)]
            rows.append(rec)
    return rows


def _centered_matrix(rows: list[dict], sources: tuple) -> tuple[np.ndarray, dict]:
    """Per-(source, year) mean centering. REQUIRED, not optional: a_s is a free intercept
    per source and a source that rebases its published scale between vintages has that
    rebase read as variance. Baseball America is the case (see calibration_drift)."""
    tot: dict = {}
    cnt: dict = {}
    for r in rows:
        for s in sources:
            if s in r:
                tot[(s, r["year"])] = tot.get((s, r["year"]), 0.0) + r[s]
                cnt[(s, r["year"])] = cnt.get((s, r["year"]), 0) + 1
    mean = {k: tot[k] / cnt[k] for k in sorted(tot)}
    X = np.full((len(rows), len(sources)), np.nan)
    for i, r in enumerate(rows):
        for j, s in enumerate(sources):
            if s in r:
                X[i, j] = r[s] - mean[(s, r["year"])]
    return X, mean


def _pairwise_cov(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = X.shape[1]
    C = np.zeros((d, d))
    N = np.zeros((d, d), dtype=int)
    for a in range(d):
        for b in range(d):
            m = ~np.isnan(X[:, a]) & ~np.isnan(X[:, b])
            N[a, b] = int(m.sum())
            if m.sum() > 3:
                C[a, b] = float(np.cov(X[m, a], X[m, b])[0, 1])
    return C, N


def _em_mvn(X: np.ndarray, max_iter: int = 400, tol: float = 1e-9) -> tuple[np.ndarray, np.ndarray, int]:
    """EM / FIML for a multivariate normal with arbitrary missing patterns.

    Patterns are visited in a FIXED sorted order so the fit is bit-reproducible. Rows with
    no observed entry are dropped. Returns (mu, Sigma, iterations).
    """
    keep = ~np.all(np.isnan(X), axis=1)
    X = X[keep]
    n, d = X.shape
    mu = np.nan_to_num(np.nanmean(X, axis=0))
    C, _N = _pairwise_cov(X - mu)
    C = (C + C.T) / 2.0
    w, V = np.linalg.eigh(C)
    Sigma = V @ np.diag(np.maximum(w, 1e-6)) @ V.T      # PSD projection of the init
    patterns: dict[tuple, list[int]] = {}
    for i in range(n):
        patterns.setdefault(tuple(bool(v) for v in ~np.isnan(X[i])), []).append(i)
    order = sorted(patterns)
    it = 0
    for it in range(1, max_iter + 1):
        T1 = np.zeros(d)
        T2 = np.zeros((d, d))
        for pat in order:
            idx = patterns[pat]
            o = [j for j in range(d) if pat[j]]
            m = [j for j in range(d) if not pat[j]]
            xb = X[idx]
            xh = np.tile(mu, (len(idx), 1))
            xh[:, o] = xb[:, o]
            corr = np.zeros((d, d))
            if m:
                Soo = Sigma[np.ix_(o, o)]
                B = np.linalg.solve(Soo, Sigma[np.ix_(o, m)]).T
                xh[:, m] = mu[m] + (xb[:, o] - mu[o]) @ B.T
                Cmm = Sigma[np.ix_(m, m)] - B @ Sigma[np.ix_(o, m)]
                corr[np.ix_(m, m)] = len(idx) * Cmm
            T1 += xh.sum(axis=0)
            T2 += xh.T @ xh + corr
        mu_new = T1 / n
        Sigma_new = T2 / n - np.outer(mu_new, mu_new)
        Sigma_new = (Sigma_new + Sigma_new.T) / 2.0
        delta = float(np.abs(Sigma_new - Sigma).max() + np.abs(mu_new - mu).max())
        mu, Sigma = mu_new, Sigma_new
        if delta < tol:
            break
    return mu, Sigma, it


def _triad(C: np.ndarray, names: tuple) -> dict:
    """Closed-form 3-instrument factor solution.

        b_1^2 = C_12 * C_13 / C_23 (and cyclic),  sigma_s^2 = Var(x_s) - b_s^2

    Var(mu) = 1 fixes the scale. A negative sigma^2 is a HEYWOOD case: the model is refuted,
    not the source perfected.
    """
    v = np.diag(C).astype(float)
    pairs = ((0, 1, 2), (1, 0, 2), (2, 0, 1))
    b2 = np.zeros(3)
    for s, a, bb in pairs:
        denom = C[a, bb]
        b2[s] = (C[s, a] * C[s, bb] / denom) if abs(denom) > 1e-12 else np.nan
    heywood = bool(np.any(~np.isfinite(b2)) or np.any(b2 < 0) or np.any(v - b2 < 0))
    out = {"sources": list(names), "heywood": heywood,
           "var_observed": [_r(x, 4) for x in v]}
    if heywood:
        out["note"] = "triad refuted on these rows: negative loading or negative residual variance"
        return out
    b = np.sqrt(b2)
    sig2 = v - b2
    sig = np.sqrt(sig2)
    w = b / sig2
    out.update({
        "b": [_r(x, 4) for x in b],
        "sigma": [_r(x, 4) for x in sig],
        "sigma2": [_r(x, 4) for x in sig2],
        "reliability": [_r(b2[i] / v[i], 4) for i in range(3)],
        "gls_weight": [_r(x, 5) for x in w],
        "alpha_fg": _r(float(w[0] / (w[0] + w[1])), 4),
        "sheppard_variance_h2_over_12": _r(SHEPPARD_VARIANCE, 4),
        "sheppard_share_of_sigma2": [_r(SHEPPARD_VARIANCE / s, 4) for s in sig2],
    })
    return out


def _precision_label_free(universe: list[dict], arch_d_rho: dict, arch_answerable: dict,
                          ab_years: list[int], live_k1: dict) -> dict:
    rows = _precision_rows(universe)
    ba_years = sorted({r["year"] for r in rows if TRIAD[2] in r})
    triad_rows = [r for r in rows if r["year"] in ba_years
                  and sum(1 for s in TRIAD if s in r) >= 1]

    # TWO SOURCES ARE NOT IDENTIFIED, and the honest response is to say so
    # rather than to emit a number. The triad identity b_1^2 = C_12 C_13 / C_23
    # needs a THIRD instrument; with only FanGraphs and MLB Pipeline the system
    # is underdetermined and every downstream quantity (sigma, reliability, the
    # GLS weight, alpha_fg) is undefined rather than merely imprecise.
    #
    # This is not hypothetical: the third instrument is Baseball America, a
    # subscription source ingested from owner-supplied board pastes, so there
    # is a real window with no BA rows every time it is purged for a re-ingest
    # (2026-08-10 was one). Before this guard the module raised
    # "need at least one array to concatenate" from an empty bootstrap, three
    # frames deep, which reads as a code fault rather than as absent evidence.
    n_triad = sum(1 for r in triad_rows if TRIAD[2] in r)
    if n_triad < _PRECISION_MIN_TRIAD_ROWS:
        return {
            "identified": False,
            "reason": (
                f"the third instrument ({TRIAD[2]}) carries {n_triad} usable "
                f"rows, below the {_PRECISION_MIN_TRIAD_ROWS} this block needs. "
                "Two sources cannot identify a measurement-error model: the "
                "triad identity needs a third. No precision estimate, no GLS "
                "weight and no alpha are computed, because the right answer is "
                "that the data cannot support one."),
            "third_instrument": TRIAD[2],
            "n_third_instrument_rows": n_triad,
            "min_rows_required": _PRECISION_MIN_TRIAD_ROWS,
            "sources_present": sorted({s for r in rows for s in TRIAD if s in r}),
            "restores_when": (
                f"{TRIAD[2]} boards are re-ingested; this block recomputes with "
                "no code change."),
        }

    # Pattern census over the triad, on the years the third instrument exists.
    pat_counts: dict[str, int] = {}
    for r in triad_rows:
        pat = tuple(s for s in TRIAD if s in r)
        if len(pat) >= 2:
            pat_counts["+".join(pat)] = pat_counts.get("+".join(pat), 0) + 1
    complete = pat_counts.get("+".join(TRIAD), 0)
    usable = sum(pat_counts.values())

    X_raw = np.full((len(triad_rows), 3), np.nan)
    for i, r in enumerate(triad_rows):
        for j, s in enumerate(TRIAD):
            if s in r:
                X_raw[i, j] = r[s]
    Xc, _mean = _centered_matrix(triad_rows, TRIAD)
    uncentered_var = [_r(float(np.nanvar(X_raw[:, j], ddof=1)), 3) for j in range(3)]
    centered_var = [_r(float(np.nanvar(Xc[:, j], ddof=1)), 3) for j in range(3)]

    cc_mask = ~np.isnan(Xc).any(axis=1)
    Xcc = Xc[cc_mask]
    C_cc = np.cov(Xcc, rowvar=False)
    cc = _triad(C_cc, TRIAD)
    cc["n"] = int(Xcc.shape[0])

    mu_em, S_em, iters = _em_mvn(Xc)
    em = _triad(S_em, TRIAD)
    em["n_rows_used"] = int((~np.all(np.isnan(Xc), axis=1)).sum())
    em["iterations"] = iters
    em["mu"] = [_r(x, 4) for x in mu_em]

    # Bootstrap over PLAYERS. Complete case gets the full B; EM gets EM_BOOT_B because each
    # draw refits the whole EM.
    keys_cc = np.array([triad_rows[i]["key"] for i in np.where(cc_mask)[0]])
    uk = np.array(sorted(set(keys_cc.tolist())))
    kidx: dict = {}
    for i, k in enumerate(keys_cc):
        kidx.setdefault(k, []).append(i)
    rng = np.random.default_rng([SEED, 5001])
    a_boot = []
    for _b in range(BOOT_B):
        pick = rng.integers(0, uk.size, size=uk.size)
        sel = np.concatenate([kidx[uk[j]] for j in pick])
        Cb = np.cov(Xcc[sel], rowvar=False)
        t = _triad(Cb, TRIAD)
        if not t["heywood"]:
            a_boot.append(t["alpha_fg"])
    a_boot = np.array(a_boot, float)
    cc["alpha_fg_ci95"] = [_r(float(np.percentile(a_boot, 2.5)), 4),
                           _r(float(np.percentile(a_boot, 97.5)), 4)] if a_boot.size else None
    cc["bootstrap_draws_non_heywood"] = int(a_boot.size)

    all_keys = np.array(sorted({r["key"] for r in triad_rows if r["key"]}))
    rowsby: dict = {}
    for i, r in enumerate(triad_rows):
        rowsby.setdefault(r["key"], []).append(i)
    rng2 = np.random.default_rng([SEED, 5002])
    a_em = []
    for _b in range(EM_BOOT_B):
        pick = rng2.integers(0, all_keys.size, size=all_keys.size)
        sel = np.concatenate([rowsby[all_keys[j]] for j in pick])
        try:
            _m, Sb, _i = _em_mvn(Xc[sel])
            t = _triad(Sb, TRIAD)
        except np.linalg.LinAlgError:
            continue
        if not t["heywood"]:
            a_em.append(t["alpha_fg"])
    a_em = np.array(a_em, float)
    em["alpha_fg_ci95"] = [_r(float(np.percentile(a_em, 2.5)), 4),
                           _r(float(np.percentile(a_em, 97.5)), 4)] if a_em.size else None
    em["bootstrap_draws_non_heywood"] = int(a_em.size)
    em["bootstrap_draws"] = EM_BOOT_B

    # Per board year: is the triad estimable at all?
    per_year = {}
    for y in ba_years:
        yr = [r for r in triad_rows if r["year"] == y]
        Xy, _ = _centered_matrix(yr, TRIAD)
        m = ~np.isnan(Xy).any(axis=1)
        rec = {"complete_case_n": int(m.sum()),
               "pairwise_n": {f"{TRIAD[a]}+{TRIAD[b]}":
                              int((~np.isnan(Xy[:, a]) & ~np.isnan(Xy[:, b])).sum())
                              for a, b in ((0, 1), (0, 2), (1, 2))}}
        if m.sum() >= 60:
            t = _triad(np.cov(Xy[m], rowvar=False), TRIAD)
            rec["estimable"] = not t["heywood"]
            rec["alpha_fg"] = t.get("alpha_fg")
            rec["heywood"] = t["heywood"]
        else:
            rec["estimable"] = False
            rec["heywood"] = None
            rec["reason"] = "complete-case n below 60"
        per_year[str(y)] = rec

    estimable_years = [int(y) for y in ba_years if per_year[str(y)]["estimable"]]
    first_est = min(estimable_years) if estimable_years else None
    # A precision weight for board year Y is vintage-legal only if some estimable year is
    # <= Y - MIN_LAG_YEARS, matching the A/B's own rule. That is what makes the two sets
    # disjoint: it is structural, not a power problem.
    weightable = [y for y in range(2000, 2041)
                  if first_est is not None and first_est <= y - MIN_LAG_YEARS]
    overlap = sorted(set(weightable) & set(ab_years))

    # Range-restricted instruments: sigma and n, NO weight.
    Xall, _m6 = _centered_matrix(rows, ALL_PRECISION_SOURCES)
    C6, N6 = _pairwise_cov(Xall)
    sd6 = np.sqrt(np.diag(C6))
    eig = np.linalg.eigvalsh((C6 + C6.T) / 2.0)
    bad_pairs = []
    for a in range(6):
        for b in range(a + 1, 6):
            if sd6[a] > 0 and sd6[b] > 0:
                rr = C6[a, b] / (sd6[a] * sd6[b])
                if abs(rr) > 1.0:
                    bad_pairs.append({"pair": [ALL_PRECISION_SOURCES[a], ALL_PRECISION_SOURCES[b]],
                                      "cov": _r(C6[a, b], 3),
                                      "max_admissible_cov": _r(sd6[a] * sd6[b], 3),
                                      "implied_corr": _r(rr, 4)})
    restricted = {}
    fg_sd = float(sd6[0])
    for j, s in enumerate(ALL_PRECISION_SOURCES):
        if s not in RESTRICTED_SOURCES:
            continue
        n_s = int((~np.isnan(Xall[:, j])).sum())
        restricted[s] = {
            "n": n_s, "sigma_centered": _r(float(sd6[j]), 4),
            "sd_ratio_vs_fangraphs": _r(float(sd6[j]) / fg_sd, 4),
            "range_restricted": bool(float(sd6[j]) < 0.85 * fg_sd),
            "weight": None,
            "why_no_weight": ("range restriction deflates variance and covariance in "
                              "OPPOSITE directions relative to the factor model, so a triad "
                              "solved with this instrument in it is biased in a direction "
                              "the triad cannot detect from within"),
        }
    # The checkable version of that claim: swap the third instrument and watch FanGraphs'
    # own loading move. If the six series were reads of one latent variable on one
    # population, b_fangraphs would not depend on which instrument completes the triad.
    swap = {}
    for third in (TRIAD[2],) + RESTRICTED_SOURCES:
        j = ALL_PRECISION_SOURCES.index(third)
        sub = np.array([[C6[0, 0], C6[0, 1], C6[0, j]],
                        [C6[1, 0], C6[1, 1], C6[1, j]],
                        [C6[j, 0], C6[j, 1], C6[j, j]]])
        t = _triad(sub, (FANGRAPHS, PIPELINE, third))
        swap[third] = {"b_fangraphs": (t.get("b") or [None])[0],
                       "reliability_fangraphs": (t.get("reliability") or [None])[0],
                       "reliability_third": (t.get("reliability") or [None, None, None])[2],
                       "heywood": t["heywood"],
                       "pairwise_n_third_vs_fg": int(N6[0, j])}

    # precision versus accuracy, per archetype.
    pv = []
    for a in _ARCH_ORDER:
        ar = [r for r in triad_rows if r.get("archetype") == a]
        Xa, _ = _centered_matrix(ar, TRIAD)
        m = ~np.isnan(Xa).any(axis=1)
        if m.sum() < 60:
            pv.append({"archetype": a, "n": int(m.sum()), "alpha_fg": None,
                       "d_rho": arch_d_rho.get(a)})
            continue
        t = _triad(np.cov(Xa[m], rowvar=False), TRIAD)
        pv.append({"archetype": a, "n": int(m.sum()),
                   "alpha_fg": None if t["heywood"] else t["alpha_fg"],
                   "heywood": t["heywood"], "d_rho": arch_d_rho.get(a)})
    ok = [p for p in pv if p["alpha_fg"] is not None and p["d_rho"] is not None]
    r_pa = perm_p = None
    if len(ok) >= 3:
        av = np.array([p["alpha_fg"] for p in ok], float)
        dv = np.array([p["d_rho"] for p in ok], float)
        r_pa = float(np.corrcoef(av, dv)[0, 1])
        # Exact permutation over all orderings: k! is at most 720 here, so no RNG.
        perms = list(itertools.permutations(range(len(ok))))
        stats = np.array([abs(float(np.corrcoef(av, dv[list(pp)])[0, 1])) for pp in perms])
        perm_p = float((stats >= abs(r_pa) - 1e-12).mean())
    resolvable_cells = []
    for p in pv:
        if not arch_answerable.get(p["archetype"]) or p["alpha_fg"] is None:
            continue
        resolvable_cells.append({
            "archetype": p["archetype"],
            "accuracy_winner": (PIPELINE if p["d_rho"] < 0 else FANGRAPHS),
            "accuracy_d_rho": p["d_rho"],
            "precision_alpha_fg": p["alpha_fg"],
            "precision_prefers": (FANGRAPHS if p["alpha_fg"] > 0.5 else PIPELINE),
            "agree": bool((p["d_rho"] > 0) == (p["alpha_fg"] > 0.5)),
        })

    return {
        # Stated POSITIVELY on both returns so a consumer can branch on one key.
        # The unidentified early return above emits identified=False; without this
        # the populated return carried no such key, so a reader testing
        # `identified !== true` would render the not-identified empty state
        # forever after the third instrument came back. Found by the /glossary/
        # source-accuracy view, 2026-08-10.
        "identified": True,
        "basis": ("player-year rows, ALL snapshots (no preseason window), per-(source, year) "
                  "mean centering"),
        "board_years_with_third_instrument": ba_years,
        "patterns": pat_counts,
        "complete_case_n": complete,
        "usable_at_least_2_of_3": usable,
        "em_leverage_vs_complete_case": _r(usable / complete, 3) if complete else None,
        "intercept_absorption": {
            "required": True,
            "uncentered_variance": dict(zip(TRIAD, uncentered_var)),
            "centered_variance": dict(zip(TRIAD, centered_var)),
            "why": ("a_s is a free per-source intercept. Without per-(source, year) "
                    "centering a source that rebases its published scale between vintages "
                    "has the rebase read as variance."),
        },
        "estimator_primary_em_fiml": em,
        "estimator_robustness_complete_case": cc,
        "gls_weight_form": ("w_s proportional to b_s / sigma_s^2, NOT 1 / sigma_s^2. The "
                            "naive inverse variance rewards range compression: a source "
                            "that publishes a narrow range has a small b_s AND a small raw "
                            "variance, so inverse variance upweights the source expressing "
                            "the least information."),
        "sheppard": {"h": FV_LATTICE, "h2_over_12": _r(SHEPPARD_VARIANCE, 4),
                     "subtracted_from_weight": False,
                     "why_not": ("the served aggregator observes the QUANTIZED grade, so "
                                 "lattice noise is real noise in the quantity being "
                                 "combined")},
        "two_source_identification": {
            "identified": False,
            "why": ("two sources give three second moments (two variances, one covariance) "
                    "against four unknowns (b_1, b_2, sigma_1, sigma_2). Any split of the "
                    "shared variance fits. No number is attached to the two-source case."),
        },
        "vintage_availability": {
            "precision_estimable_by_board_year": per_year,
            "estimable_years": estimable_years,
            "first_estimable_year": first_est,
            "ab_eligible_board_years": ab_years,
            "weightable_board_years": weightable[:12],
            "first_weightable_board_year": (min(weightable) if weightable else None),
            "overlap_with_ab_eligible": overlap,
            "first_year_a_precision_weight_can_be_ab_tested": (
                (min(weightable) + MIN_LAG_YEARS) if weightable else None),
            "structural_note": (
                "A precision weight for board year Y is vintage-legal only when an estimable "
                "year sits at or before Y - " + str(MIN_LAG_YEARS) + ". The A/B can only "
                "score board years whose outcomes have resolved. Those two sets do not "
                "intersect, so the label-free route cannot be validated against an outcome "
                "on this data at all. STRUCTURAL, not a power problem: no number of extra "
                "players changes it."),
        },
        "range_restricted_sources": restricted,
        "six_source_covariance_diagnostic": {
            "sources": list(ALL_PRECISION_SOURCES),
            "pairwise_complete_cov": [[_r(C6[a, b], 3) for b in range(6)] for a in range(6)],
            "pairwise_n": [[int(N6[a, b]) for b in range(6)] for a in range(6)],
            "eigenvalues": [_r(x, 4) for x in eig],
            "psd": bool(eig.min() > -1e-8),
            "pairs_with_implied_corr_above_1": bad_pairs,
            "third_instrument_swap": swap,
            "reading": ("Pairwise-complete covariance is not constrained to be PSD when the "
                        "pairs come from different populations. Whether or not an eigenvalue "
                        "goes negative, the swap table is the binding evidence: if the six "
                        "series were reads of ONE latent variable on ONE population, "
                        "b_fangraphs would not depend on which instrument completes the "
                        "triad."),
        },
        "precision_vs_accuracy": {
            "per_archetype": pv,
            "pearson_r": _r(r_pa, 4),
            "permutation_p_two_sided": _r(perm_p, 4),
            "permutation": "exact, all k! orderings",
            "on_the_resolvable_cells": resolvable_cells,
            "reading": ("Precision and accuracy are uncorrelated across archetypes. Where "
                        "accuracy IS resolvable, precision does not point the same way, so "
                        "a precision weight would have been wrong exactly where it "
                        "mattered. alpha_fg above 0.5 means precision prefers FanGraphs; "
                        "d_rho below 0 means accuracy prefers MLB Pipeline."),
        },
        "lambda_k_block": {
            "status": "NULL",
            "is_a_lane": False,
            "reasons": [
                "Lane M4 (2026-08-08) measured coverage dependence at p 0.048 pre-shrinkage "
                "and p 0.944 post-shrinkage: the incumbent SINGLE_SOURCE_K=0.5 already "
                "absorbs it.",
                "lambda_k is a continuous-in-k reparameterisation of the SAME estimand M4 "
                "already tested, not a new one.",
                "its proposed interaction gate needs roughly n=2000 in the k=1 stratum; the "
                "outcome-resolvable window supplies "
                + str(live_k1.get("resolvable_window_k1")) + ".",
                "its input sigma_pub has no vintage estimate before "
                + str(first_est if first_est else "the first third-instrument vintage")
                + ", so it cannot be computed on any year the A/B can score.",
            ],
            "k1_stratum": live_k1,
        },
    }


# --------------------------------------------------------------------------
# Block 6: coverage selection
# --------------------------------------------------------------------------
def _coverage_selection(pooled: list[dict], own: dict) -> dict:
    cslots = {(c["key"], c["year"]) for c in pooled}
    common_players = {c["key"] for c in pooled}
    per_source = {}
    all_players = set()
    cut_rows_all = []
    for s in SCORED_SOURCES:
        rows = own[s]
        all_players |= {r["key"] for r in rows}
        cut = [r for r in rows if (r["key"], r["year"]) not in cslots]
        kept = [r for r in rows if (r["key"], r["year"]) in cslots]
        cut_rows_all.extend(cut)
        rho_own = _spearman([r["fv"] for r in rows], [r["war"] for r in rows])
        rho_common = _spearman([r["fv"] for r in kept], [r["war"] for r in kept])
        per_source[s] = {
            "rows_own": len(rows), "rows_common": len(kept), "rows_cut": len(cut),
            "players_cut": len({r["key"] for r in cut}),
            "rho_own": _r(rho_own), "rho_common": _r(rho_common),
            "delta_own_minus_common": _r(rho_own - rho_common, 5),
            "cut_mean_fv": _r(float(np.mean([r["fv"] for r in cut])), 2) if cut else None,
            "cut_debut_rate": _r(float(np.mean([r["debuted"] for r in cut])), 3) if cut else None,
            "kept_mean_fv": _r(float(np.mean([r["fv"] for r in kept])), 2) if kept else None,
            "kept_debut_rate": _r(float(np.mean([r["debuted"] for r in kept])), 3) if kept else None,
        }
    union_slots = len(cslots) + sum(per_source[s]["rows_cut"] for s in SCORED_SOURCES)
    kept_fv = [c[k] for c in pooled for k in ("fg", "mp")]
    return {
        "per_source": per_source,
        "row_retention": _r(len(cslots) / union_slots, 4),
        "player_retention": _r(len(common_players) / len(all_players), 4),
        "union_player_year_slots": union_slots,
        "kept_pooled_mean_source_fv": _r(float(np.mean(kept_fv)), 2),
        "kept_pooled_debut_rate": _r(float(np.mean([c["debuted"] for c in pooled])), 3),
        "cut_pooled_mean_source_fv": (_r(float(np.mean([r["fv"] for r in cut_rows_all])), 2)
                                      if cut_rows_all else None),
        "cut_pooled_debut_rate": (_r(float(np.mean([r["debuted"] for r in cut_rows_all])), 3)
                                  if cut_rows_all else None),
        "selection_model": {
            "built": False,
            "why_not": ("the cut rows carry ZERO paired contrast: no second source graded "
                        "them, so they contain no information about d_rho under any model "
                        "that does not assume the missingness is ignorable. The mean-grade "
                        "imbalance between kept and cut rows makes that assumption not "
                        "credible. Naming the exclusion and publishing its size IS the "
                        "honest form of recovering this evidence."),
        },
    }


# --------------------------------------------------------------------------
# Block 7: calibration drift
# --------------------------------------------------------------------------
DRIFT_FLAG_FV = 3.0


def _calibration_drift(universe: list[dict], reference: str = FANGRAPHS) -> dict:
    """Per-source offset against `reference` on same-quarter common slots.

    grade_normalization already handles a level shift correctly (per calendar cycle, all
    cells at n >= 30), so the SERVED consensus is not at risk today. What does not exist is
    DETECTION: nothing in the pipeline notices when a source rebases its scale. This block
    is the tripwire, not a repair.
    """
    slot: dict = {}
    for p in universe:
        k = p.get("player_key")
        for pt in (p.get("points") or []):
            sd = pt.get("snapshot_date")
            if not sd:
                continue
            y, mth = int(sd[:4]), int(sd[5:7])
            q = (mth - 1) // 3 + 1
            for s, ps in (pt.get("per_source") or {}).items():
                if s not in ALL_PRECISION_SOURCES:
                    continue
                v = (ps or {}).get("fv_published")
                if v is None:
                    continue
                kk = (k, y, q, s)
                slot[kk] = max(slot[kk], float(v)) if kk in slot else float(v)
    out = {"reference": reference, "flag_threshold_fv": DRIFT_FLAG_FV, "sources": {}}
    flags = []
    for s in ALL_PRECISION_SOURCES:
        if s == reference:
            continue
        by_year: dict[int, list[float]] = {}
        by_yq: dict[tuple, list[float]] = {}
        for (k, y, q, src), v in sorted(slot.items()):
            if src != s:
                continue
            ref = slot.get((k, y, q, reference))
            if ref is None:
                continue
            by_year.setdefault(y, []).append(v - ref)
            by_yq.setdefault((y, q), []).append(v - ref)
        if not by_year:
            continue
        years = sorted(by_year)
        rec = {"per_year": {str(y): {"n": len(by_year[y]),
                                     "offset_fv": _r(float(np.mean(by_year[y])), 3)}
                            for y in years},
               "per_year_quarter": {f"{y}Q{q}": {"n": len(v),
                                                 "offset_fv": _r(float(np.mean(v)), 3)}
                                    for (y, q), v in sorted(by_yq.items())}}
        moves = []
        for a, b in zip(years, years[1:]):
            mv = float(np.mean(by_year[b]) - np.mean(by_year[a]))
            moves.append({"from": a, "to": b, "move_fv": _r(mv, 3),
                          "flagged": bool(abs(mv) >= DRIFT_FLAG_FV)})
            if abs(mv) >= DRIFT_FLAG_FV:
                flags.append({"source": s, "year": b, "move_fv": _r(mv, 3)})
        rec["year_over_year"] = moves
        out["sources"][s] = rec
    out["flagged"] = flags
    out["note"] = ("Offsets are on same-quarter common slots against the reference, so a "
                   "move is a scale change and not a coverage change. grade_normalization "
                   "absorbs the level shift per cycle; nothing DETECTS it. This is the most "
                   "likely future silent-corruption vector for the consensus.")
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def _reproduction(ded: list[dict], accuracy: dict, data_dir: Path) -> dict:
    """Prove the archetype numbers against source_backtest, two ways.

    LEG 1 (binding): recompute source_backtest._archetype_accuracy, unmodified, on THIS
    lane's deduped rows reshaped into its input format. Any difference is a bug here.

    LEG 2 (informational): compare to the SERVED data/source_backtest.json. It can be stale
    against its own inputs, and on the 2026-08-09 export it is: source_backtest.json was
    written 13:56, debuts.json 14:07 and timeseries.json 14:24, so the served archetype
    table was built on a universe that no longer exists. The same failure mode is on record
    in docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md section 6.0.1, where a live recompute on
    the same inputs was made binding for exactly this reason. Leg 2 therefore reports a
    staleness flag; it does not gate.
    """
    from source_backtest import _archetype_accuracy   # local: only this leg needs it
    shaped = [{"grades": {FANGRAPHS: c["fg"], PIPELINE: c["mp"], CONSENSUS_KEY: c["cons"]},
               "outcome": {"war": c["war"], "contributor": c["contributor"]},
               "archetype": c["archetype"]} for c in ded]
    live = {r["archetype"]: r for r in _archetype_accuracy(
        shaped, [FANGRAPHS, PIPELINE, CONSENSUS_KEY])}
    code_diffs = []
    for arch, cell in accuracy["by_archetype"].items():
        if not cell.get("scored") or arch not in live:
            continue
        for s in (FANGRAPHS, PIPELINE, CONSENSUS_KEY):
            mine = cell["raters"][s]["spearman"]
            theirs = live[arch]["raters"][s]["spearman"]
            if mine != theirs or cell["n"] != live[arch]["n"]:
                code_diffs.append({"archetype": arch, "source": s, "mine": mine,
                                   "source_backtest": theirs,
                                   "n_mine": cell["n"], "n_theirs": live[arch]["n"]})
    served_diffs = []
    served_path = data_dir / "source_backtest.json"
    served_n = {}
    if served_path.exists():
        try:
            served = json.loads(served_path.read_text(encoding="utf-8"))
            for row in ((served.get("accuracy") or {}).get("by_archetype") or []):
                arch = row.get("archetype")
                served_n[arch] = row.get("n")
                cell = accuracy["by_archetype"].get(arch)
                if not cell or not cell.get("scored"):
                    continue
                for s in (FANGRAPHS, PIPELINE, CONSENSUS_KEY):
                    theirs = ((row.get("raters") or {}).get(s) or {}).get("spearman")
                    if cell["raters"][s]["spearman"] != theirs:
                        served_diffs.append({"archetype": arch, "source": s,
                                             "mine": cell["raters"][s]["spearman"],
                                             "served": theirs, "n_mine": cell["n"],
                                             "n_served": row.get("n")})
        except ValueError:
            served_diffs.append({"error": "served source_backtest.json is not valid JSON"})
    return {
        "matches_source_backtest_code": not code_diffs,
        "code_diffs": code_diffs,
        "matches_served_source_backtest_json": not served_diffs,
        "served_diffs": served_diffs,
        "served_artifact_stale": bool(served_diffs),
        "served_cell_n": served_n,
        "note": ("Leg 1 recomputes source_backtest._archetype_accuracy on this lane's rows "
                 "and is binding. Leg 2 compares to the served artifact and is "
                 "informational, because the served artifact can predate its own inputs."),
    }


def _k1_stratum(universe: list[dict], years: list[int], data_dir: Path) -> dict:
    """Size of the k=1 (single contributing source) stratum, in the outcome-resolvable
    window and on the live board. The lambda_k block cites these counts as its reason."""
    lo, hi = "-01-01", "-05-01"
    seen: dict = {}
    for p in universe:
        out = _outcome(p)
        for y in years:
            win = [pt for pt in (p.get("points") or [])
                   if pt.get("snapshot_date") and f"{y}{lo}" <= pt["snapshot_date"] < f"{y}{hi}"]
            if not win:
                continue
            dy = out["debut_year"]
            if dy is not None and y > dy:
                continue
            last = sorted(win, key=lambda pt: pt["snapshot_date"])[-1]
            k = p.get("player_key")
            if k is None:
                continue
            if k not in seen or y > seen[k][0]:
                seen[k] = (y, len(last.get("sources_contributing") or []))
    res_k1 = sum(1 for v in seen.values() if v[1] == 1)
    live_k1 = live_n = 0
    ts = data_dir / "timeseries.json"
    if ts.exists():
        for p in (json.loads(ts.read_text(encoding="utf-8")).get("players") or []):
            pts = p.get("points") or []
            if not pts:
                continue
            last = sorted(pts, key=lambda x: x.get("snapshot_date") or "")[-1]
            live_n += 1
            if len(last.get("sources_contributing") or []) == 1:
                live_k1 += 1
    return {"resolvable_window_k1": res_k1, "resolvable_window_n": len(seen),
            "live_board_k1": live_k1, "live_board_n": live_n,
            "interaction_gate_needs_n": 2000}


def run_source_cohort_accuracy(data_dir: Path = DATA_DIR, write: bool = True) -> dict:
    universe = _load_universe(data_dir)
    as_of = date.today()
    years = _resolved_years(universe, as_of.year)
    present = sorted({int(pt["snapshot_date"][:4]) for p in universe
                      for pt in (p.get("points") or []) if pt.get("snapshot_date")})
    present_candidates = [y for y in CANDIDATE_YEARS if y in present]

    pooled, own = _build_common_rows(universe, years)
    ded = _dedup_latest_predebut(pooled)

    # Guard: the vectorised rho used in every bootstrap must agree with the pure-python
    # _spearman that produces the published point estimates. A silent divergence here would
    # move the CIs without moving anything a reader can see.
    chk_a = _spearman([c["fg"] for c in ded], [c["war"] for c in ded])
    chk_b = _rho1(np.array([c["fg"] for c in ded]), np.array([c["war"] for c in ded]))
    rho_impl_max_abs_diff = abs(chk_a - chk_b)

    accuracy = _accuracy_block(
        ded, frozen_fv_tier_block("source_cohort_accuracy") if fv_tier_frozen(data_dir) else None)
    arch_d = {a: accuracy["by_archetype"][a]["d_rho"]
              for a in _ARCH_ORDER
              if a in accuracy["by_archetype"] and accuracy["by_archetype"][a].get("scored")}
    multiplicity = _multiplicity(accuracy, ded, pooled)
    cohort_ab = _cohort_ab(universe, present_candidates, years)
    ab_rows = _ab_rows(universe, present_candidates)
    ab_scored_years = ((cohort_ab["arms"].get(cohort_ab.get("best_arm")) or {})
                       .get("scored_years") or years)
    oracle = {
        "ab_pooled": _oracle([r for r in ab_rows if r["year"] in ab_scored_years],
                             "archetype", _ARCH_ORDER + ("unknown",), "cohort_ab pooled rows"),
        "deduped_common": _oracle(ded, "archetype", _ARCH_ORDER,
                                  "deduped common set, one row per player"),
    }
    k1 = _k1_stratum(universe, years, data_dir)
    arch_answerable = {a: accuracy["by_archetype"][a]["answerable"] for a in arch_d}
    precision = _precision_label_free(universe, arch_d, arch_answerable, years, k1)
    coverage = _coverage_selection(pooled, own)
    drift = _calibration_drift(universe)
    reproduction = _reproduction(ded, accuracy, data_dir)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "produced_by": PRODUCED_BY,
        "as_of_date": as_of.isoformat(),
        "ships_a_weight": False,
        # Composed from the measured values, not typed in, so it cannot drift away from the
        # blocks below on a future vintage.
        "headline": (
            "The owner question is UNANSWERABLE in most cells. "
            f"{multiplicity['cells_flagged_answerable']} of "
            f"{multiplicity['cells_tested']} scored cells clear their own MDE95, against "
            f"{multiplicity['expected_false_positives_at_alpha_05']} expected by "
            "construction at alpha 0.05. The GLOBAL head-to-head is itself not resolvable "
            f"(d_rho {accuracy['pooled']['d_rho']}, MDE95 {accuracy['pooled']['mde95']}). "
            "Archetype heterogeneity does not reject one common difference (Cochran Q p "
            f"{multiplicity['archetype_heterogeneity']['chi2_p']}, label permutation p "
            f"{multiplicity['archetype_heterogeneity']['permutation_p_labels']}, I2 "
            f"{multiplicity['archetype_heterogeneity']['i2_percent']} percent). All six "
            "cohort-weight arms lose to equal weight, random cohort labels do no worse "
            f"(permutation p {(cohort_ab.get('permutation_control') or {}).get('p')}), "
            "and the in-sample "
            "global oracle gain "
            f"{oracle['deduped_common']['global_oracle_gain']} sits below the "
            f"{SHIP_MIN_RHO_GAIN} ship gate, so estimation error is not the binding "
            "constraint. No weight ships and none should."),
        "basis": {
            "window_years": years,
            "min_lag_years": MIN_LAG_YEARS,
            "pooled_common_rows": len(pooled),
            "deduped_players": len(ded),
            "dedup_rule": ("one row per player, latest PRE-DEBUT read; identical rule to "
                           "source_backtest.py:952-967"),
            "estimand": ("d_rho = rho_fangraphs - rho_mlb_pipeline; negative means MLB "
                         "Pipeline orders the cell better"),
            "uncertainty": (f"player bootstrap B={BOOT_B}, seed {SEED}; "
                            "mde95 = 1.96 * sd(bootstrap d_rho); answerable when "
                            "abs(d_rho) >= mde95"),
            "reproduces": ("data/source_backtest.json accuracy.by_archetype per-source "
                           "spearman, asserted in test_source_cohort_accuracy.py"),
            "rho_implementation_max_abs_diff": _r(rho_impl_max_abs_diff, 12),
            "pre_registration": ["docs/efv-2026-08-09/COHORT_WEIGHT_GATE.md",
                                 "docs/efv-2026-08-09/SOURCE_PRECISION_GATE.md"],
        },
        "reproduction": reproduction,
        "accuracy": {**accuracy, "coverage_selection": coverage},
        "multiplicity": multiplicity,
        "cohort_ab": cohort_ab,
        "oracle_ceiling": oracle,
        "precision_label_free": precision,
        "calibration_drift": drift,
    }
    if write:
        out_path = data_dir / "source_cohort_accuracy.json"
        out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
        log.info("wrote %s (deduped n=%d, cells=%d)", out_path, len(ded),
                 accuracy["cells_tested"])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    res = run_source_cohort_accuracy()
    a = res["accuracy"]
    print("deduped n", res["basis"]["deduped_players"])
    print("pooled", {k: v["spearman"] for k, v in a["pooled"]["raters"].items()},
          "d_rho", a["pooled"]["d_rho"], "ci", a["pooled"]["d_rho_ci"],
          "mde", a["pooled"]["mde95"], "answerable", a["pooled"]["answerable"])
    for part in ("by_side", "by_acquisition", "by_archetype", "by_position_group",
                 "by_fv_tier", "by_age_at_grading"):
        print("--", part)
        for lab, c in a[part].items():
            if c.get("scored"):
                print("  ", lab, "n", c["n"], "d", c["d_rho"], "ci", c["d_rho_ci"],
                      "mde", c["mde95"], c["winner"])
    print("multiplicity", json.dumps(res["multiplicity"]["archetype_heterogeneity"], indent=1))
    print("stability", res["multiplicity"]["base_year_stability"]["sign_flips_across_adjacent_vintages"])
    print("ab", {k: (v.get("d_rho"), v.get("d_auc"), v.get("ship")) for k, v in res["cohort_ab"]["arms"].items()})
    print("control", res["cohort_ab"]["permutation_control"])
    print("sens", res["cohort_ab"]["shrink_sensitivity"]["k_grid"])
    print("oracle", json.dumps(res["oracle_ceiling"]["ab_pooled"], indent=1)[:1200])
    print("precision em", res["precision_label_free"]["estimator_primary_em_fiml"])
    print("precision cc", res["precision_label_free"]["estimator_robustness_complete_case"])
