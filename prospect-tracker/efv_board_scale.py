"""W-SIDESCALE -- THE board grade scale. One definition, one place.

WHAT THIS IS
------------
A PER-SIDE AFFINE recalibration of the raw eFV grade (`xfv_grade`) onto a single
cross-side comparable scale, so that a given board number means the same expected
outcome whether the player is a hitter or a pitcher.

    board = clamp(a_side + b_side * raw_grade, 20, 80)

Affine => strictly order-preserving WITHIN a side, so the visible grade column stays
monotonic in board order. That property is why the 2026-07-25 unification onto one
number happened at all (storage.BOARD_GRADE_FIELD) and it is non-negotiable here.

WHY IT IS APPLIED AT THE ARTIFACT SEAM (and not in three readers)
-----------------------------------------------------------------
`stamp_doc` rewrites data/xfv.json in place: the pre-calibration value is preserved
as `xfv_grade_model_raw` and `xfv_grade` becomes the calibrated board number. So
every consumer -- storage.py `_board_grade`, build_site.py `_load_xfv_grades`,
prospx/index.html `efvBoardValue`, and the ~30 other prospx reads of `x.xfv_grade`
-- keeps reading ONE field and cannot disagree. Putting the arithmetic in each
reader instead would have created exactly the second scale definition that
BOARD_GRADE_FIELD exists to prevent, and would have left the direct `x.xfv_grade`
reads in prospx on the old scale.

Idempotency: `raw_grade()` prefers `xfv_grade_model_raw` whenever it is present, so
stamping an already-stamped document re-derives from the raw value and can never
double-correct. Same discipline as `xfv_grade_display_preside` in efv_score.

HOW THE COEFFICIENTS WERE FIT (provenance)
------------------------------------------
Fit data: the labeled (resolved-outcome) eFV pools, data/xfv_scored.json (hitters)
+ data/xfv_scored_pitcher.json (pitchers), joined to the cohort matrices for the
as-of year. Outcome = `realized_war_6yr`, first-6yr summed bWAR on the KM-censored
target -- the same WAR metric the standing F-SIDE line uses, and the model's own
currency (`xfv_grade` is `realized_implied_fv(E[6yr WAR])`).

Method -- equating on OUTCOMES, not on distribution shape:
  1. Per side, OLS of realized first-6yr WAR on the raw grade: E[W|g,s] = a_s + b_s*g.
  2. Pooled anchor line over both sides on the same rows: E[W|g] = A + B*g.
  3. Equate: e_s(g) = (a_s - A)/B + (b_s/B)*g  -- the grade on the anchor scale with
     the SAME expected outcome. Identity by construction when the sides share a line,
     so two sides with genuinely different outcome distributions are NOT forced to
     the same shape; only the outcome MEANING of a number is equalised.
  4. Gauge fix. Equating identifies only the BETWEEN-side map; the common location
     and scale are free. One common affine is applied to both sides so the fit
     pool's calibrated grades keep the raw pooled mean and sd. This is gauge-only:
     it cannot change the cross-side gap or any ordering, it just stops the whole
     board from sliding off the familiar 20-80 range.

FIT BAND: raw grade in [45.0, 59.0].
  * 59.0 is the COMMON SUPPORT ceiling -- the highest raw grade any labeled pitcher
    has. Above it there is no pitcher data at all and a per-side line is pure
    extrapolation. Fitting the full range instead lets the hitter-only 60-75 tail
    set the hitter slope and flips the estimate's sign (+3.14 instead of -1.87 at
    g=55). That sign flip is an extrapolation artifact, not a finding.
  * 45.0 is the repo's standing fringe boundary (the t45 cut in
    docs/EFV_GATE_STANDARD.md), chosen a priori, not tuned. E[WAR|grade] is convex,
    so an affine cannot be right everywhere; the band is where the board's ordering
    is actually decided. Sensitivity: the estimate keeps its sign at every cut from
    35.0 to 52.5 (gap@55 between -0.40 and -1.87 on this outcome).

GATE RECORD (docs/EFV_GATE_STANDARD.md) -- READ THIS BEFORE TRUSTING IT
-----------------------------------------------------------------------
Reproduce with `python tools/efv_board_scale_lab.py` -> data/xfv_board_scale_eval.json.
Every number below is read back from that artifact; none of it is hand-entered.

Statistic: `gap@55` = the calibrated hitter grade minus the calibrated pitcher grade
at raw grade 55 (gauge-invariant). Negative = pitchers lifted relative to hitters.
Band n = 518 hitters / 403 pitchers.

  PRIMARY, expected first-6yr WAR (this module's shipped coefficients):
    point                        -1.87
    paired bootstrap, refit/draw -1.86  CI90 [-5.15, +1.31]  sd 1.99  B=2000
                                 -> CI CONTAINS 0
    zero-information control     +0.01  CI90 [-2.72, +2.69]  (side label permuted)
                                 the candidate sits INSIDE the control band
    permutation null             CI90 [-2.72, +2.60]  two-sided p = 0.259
    5 cohort-year time splits    +1.34, -8.31, -2.47, +4.21, -8.82
                                 cross-split mean -2.81, sign agreement 3/5

  ==> ON ITS OWN THE PRIMARY SPECIFICATION IS A **NULL**. It does not resolve
      against its own zero-information control. Do not cite it as a measured win.

  Corroboration (same band, same method, tail-insensitive outcome functionals):
    sqrt(WAR)     -2.57  CI90 [-5.30, -0.16]  perm p = 0.0495  folds 4/5  mean -3.13
    P(WAR >= 3)   -2.76  CI90 [-5.41, -0.33]  perm p = 0.0350  folds 4/5  mean -3.62
  Both resolve, both agree in sign with the primary, and both sit outside their own
  control bands. The disagreement is confined to the extreme tail: E[WAR] is
  dominated by superstar hitters (the labeled pitcher pool has one 34.6-WAR arm and
  12 rows above raw 56), so the identity functional cannot resolve at this n.
  Two of three functionals resolving at p ~ 0.04 is NOT a ship on rank grounds and
  is not claimed as one.

WHAT JUSTIFIES SHIPPING IT ANYWAY IS NOT A RANK LIFT
-----------------------------------------------------
It is cross-side COMPARABILITY, cross-checked against the standing F-SIDE line's own
calibration-honest reference. F-SIDE (data/xfv_side_fairness_eval.json) reports the
top-25 pitcher share as 0.36 on the retired quantile display board against 0.09 on
its rank_war (calibration-honest) frame -- a 4.0x inflation. Measured on the live
active board (n=4477):
    retired quantile basis   top-25  19H / 6P   (pitcher share 0.24)
    raw xfv_grade basis      top-25  24H / 1P   (pitcher share 0.04)
    THIS calibration         top-25  22H / 3P   (pitcher share 0.12)
The raw basis overshot F-SIDE's reference in the opposite direction; the calibrated
basis is the one that lands near it. Max served move on the live board is well
inside the standing 3.0 FV served-move ceiling (efv_score.SFF_MOVE_CAP_FV).

DEFAULT IS OFF. Turning it ON is a served-number change with two hard prerequisites:
  1. data/xfv_history.json is on the RAW scale. Serving a calibrated today against a
     raw history makes every player show a phantom eFV move. Restamp the history or
     accept the movement engine reporting the one-time rescale as real movement.
  2. storage.BOARD_RANK_BASIS_EPOCH must be bumped to the flip date, exactly as it
     was for the 2026-07-25 raw-grade flip, or the first post-flip export publishes
     the one-time re-rank as player movement.
SUPERSEDED 2026-07-25: the flip HAS happened (ENABLED_DEFAULT is True, owner-directed)
and both prerequisites were re-checked at enable time; see the block above
ENABLED_DEFAULT for the resolution of each. Leaving this paragraph reading "neither is
done here" made one file assert two contradictory things about its own live state.

STILL OPEN, and NOT resolved by either prerequisite above -- data/xfv_history.json is on
a THIRD basis. score_history._build_grade_map builds the historical grade map from
`xfv_grade_display` (the retired per-side quantile field), so the history, the FV-history
chart and movement.xfv_movement all run on the quantile scale while the board serves
`xfv_grade`. Verified on the live artifacts: every player's last history point equals
xfv_grade_quantile exactly, not xfv_grade (Bradfield 46.60 vs served 50.97; Jesus Made
59.00 vs 64.24; Ryan Sloan 54.80 vs 56.52).
This is NOT a W-SIDESCALE bug -- the gap predates it and comes from the same-day
BOARD_GRADE_FIELD flip to raw xfv_grade -- but anyone re-reading prerequisite (1) should
know the affine is the SMALL part of the discrepancy. Repointing the map at board_value
is the fix, and it needs a one-time history restamp with grade movement suppressed for
that transition, because the owner's primary movement signal is the eFV delta and a
rebasing would otherwise publish 4-5 FV of phantom moves board-wide. That is a
coordinated operation, not a one-line change.

RELATIONSHIP TO W-FSIDE (efv_score.SIDE_FAIRNESS_FIX_DEFAULT) -- NO DOUBLE-CORRECTION
--------------------------------------------------------------------------------------
W-FSIDE is ACTIVE (efv_score.py `SIDE_FAIRNESS_FIX_DEFAULT = True`) but it writes
ONLY `xfv_grade_display`, the retired per-side quantile field
(`efv_score._apply_side_fairness_fix`, which assigns to `row["xfv_grade_display"]`
and never to `row["xfv_grade"]`). The board stopped reading that field on
2026-07-25. So W-FSIDE applies NO side adjustment to `xfv_grade` and this module is
the first and only side correction on the board number. Layering them is not
possible today; if the board is ever moved back onto the display field, exactly one
of the two must be switched off.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# ── THE SCALE ───────────────────────────────────────────────────────────────
# Do not add a second copy of these numbers anywhere. Server code calls
# board_value(); the client gets them applied through the stamped artifact.
# ENABLED 2026-07-25 (owner): "by the Clemens framework, hitter/pitcher FVs translate to
# different outcomes" - i.e. one FV number does not mean one expected outcome across sides,
# which is precisely what a per-side calibration onto a common outcome scale corrects.
# Justified on CORRECTNESS, not on a rank gain: the primary gate (gap@55 on E[6yr WAR]) is a
# measured NULL (-1.87, CI90 [-5.15,+1.31], perm p 0.259); two tail-insensitive corroborations
# resolve and agree in sign (sqrt(WAR) p 0.0495, P(WAR>=3) p 0.035). Do not cite a rank lift.
# Prerequisites checked at enable time: (1) xfv_history basis - prospx efvPrevGrade REBASES on
# each player's own latest history point, which cancels a per-side affine exactly as it cancels
# the quantile/raw offset, so no phantom grade moves; (2) BOARD_RANK_BASIS_EPOCH is already
# "2026-07-25" with a STRICTLY-AFTER gate, so every row stamped today is excluded from the
# movement engine and the first admitted snapshot is already on this basis. No bump needed.
ENABLED_DEFAULT = True           # env override: EEPHUS_BOARD_SIDE_SCALE
ENV_FLAG = "EEPHUS_BOARD_SIDE_SCALE"

FIT_BAND = (45.0, 59.0)          # (t45 fringe cut, common-support ceiling)
SCALE_MIN, SCALE_MAX = 20.0, 80.0
OUTCOME = "realized_war_6yr (first-6yr summed bWAR, KM-censored target)"
FIT_POOL = "data/xfv_scored.json + data/xfv_scored_pitcher.json, cohorts 2011-2024"
FIT_N = {"hit": 518, "pit": 403}

# board = a + b * raw_grade, per side. Fitted 2026-07-25; see GATE RECORD above.
COEFFS: dict[str, tuple[float, float]] = {
    "hit": (-2.603487, 1.036284),
    "pit": (-0.579380, 1.032470),
}

GATE = {
    "statistic": "gap@55 = calibrated hit grade - calibrated pit grade at raw 55",
    "artifact": "data/xfv_board_scale_eval.json",
    "lab": "tools/efv_board_scale_lab.py",
    "primary": {"outcome": "E[first-6yr WAR]", "point": -1.87,
                "boot_mean": -1.86, "boot_ci90": [-5.15, 1.31], "boot_b": 2000,
                "zero_info_control_ci90": [-2.72, 2.69],
                "permutation_p_two_sided": 0.259,
                "time_splits": [1.34, -8.31, -2.47, 4.21, -8.82],
                "verdict": "NULL -- does not resolve against its own control"},
    "corroboration": {"sqrt_war": {"point": -2.57, "ci90": [-5.30, -0.16], "perm_p": 0.0495},
                      "p_war_ge_3": {"point": -2.76, "ci90": [-5.41, -0.33], "perm_p": 0.0350}},
    "justification": "cross-side comparability, not a rank lift; a rank null is expected",
}

_SIDE = {"H": "hit", "P": "pit", "hit": "hit", "pit": "pit"}


def enabled() -> bool:
    env = os.environ.get(ENV_FLAG)
    if env is not None:
        return env.strip() == "1"
    return ENABLED_DEFAULT


def side_key(side) -> str | None:
    return _SIDE.get(side) if side is not None else None


def raw_grade(rec: dict):
    """The PRE-calibration model grade for an xfv.json record. Prefers the stamped
    `xfv_grade_model_raw` so re-stamping is idempotent and cannot double-correct."""
    if not rec:
        return None
    g = rec.get("xfv_grade_model_raw")
    if g is None:
        g = rec.get("xfv_grade")
    return float(g) if isinstance(g, (int, float)) else None


def calibrate(raw, side) -> float | None:
    """raw model grade -> THE board number. Identity when disabled or side unknown."""
    if raw is None:
        return None
    raw = float(raw)
    s = side_key(side)
    if not enabled() or s not in COEFFS:
        return raw
    a, b = COEFFS[s]
    return min(SCALE_MAX, max(SCALE_MIN, a + b * raw))


def board_value(rec: dict) -> float | None:
    """THE board number for an xfv.json record (calibrated, clamped, unrounded)."""
    return calibrate(raw_grade(rec), (rec or {}).get("side"))


def scale_meta() -> dict:
    """Provenance block stamped into xfv.json meta, so the served artifact carries
    its own scale definition and an auditor never has to guess which basis it is on."""
    return {"name": "W-SIDESCALE per-side affine outcome calibration",
            "module": "efv_board_scale.py",
            "enabled": enabled(),
            "coeffs": {s: {"a": a, "b": b} for s, (a, b) in COEFFS.items()},
            "form": "board = clamp(a_side + b_side * xfv_grade_model_raw, 20, 80)",
            "fit_band": list(FIT_BAND), "fit_pool": FIT_POOL, "fit_n": FIT_N,
            "outcome": OUTCOME, "gate": GATE,
            "raw_field": "xfv_grade_model_raw",
            "note": ("xfv_grade IS the board number (display, sort, overall_rank). When "
                     "enabled it is the calibrated value and the pre-calibration model "
                     "grade is kept at xfv_grade_model_raw. W-FSIDE "
                     "(efv_score.SIDE_FAIRNESS_FIX_DEFAULT) touches xfv_grade_display "
                     "only and never this field, so there is no double correction.")}


def stamp_doc(doc: dict) -> int:
    """Apply the scale to a loaded xfv.json document IN PLACE. Idempotent. Returns
    the number of records whose board number changed."""
    changed = 0
    for rec in (doc.get("by_player") or {}).values():
        if not rec:
            continue
        raw = raw_grade(rec)
        if raw is None:
            continue
        val = calibrate(raw, rec.get("side"))
        rec["xfv_grade_model_raw"] = round(raw, 4)
        # QUANTIZE TO THE 0.1 GRID, not 4dp. eFV grades have always been stamped on a
        # 0.1 grid (test_efv_score::test_committed_grades_carry_the_round_to_nearest
        # _signature pins it, and uses it to prove eFV rounds to NEAREST rather than
        # being integer-ceiled like a scouting FV). Stamping the affine output at 4dp
        # broke that contract on 2026-07-25 and emitted false precision: an affine on
        # a 0.1-grid input cannot carry four honest decimals. The pre-scale grade was
        # already on this grid, and the board sorted on it for months, so restoring it
        # costs no ordering resolution the board ever had.
        new = round(val, 1)
        if rec.get("xfv_grade") != new:
            rec["xfv_grade"] = new
            changed += 1
    doc.setdefault("meta", {})["board_scale"] = scale_meta()
    return changed


def stamp_file(path: Path | str | None = None) -> int:
    p = Path(path) if path else (DATA_DIR / "xfv.json")
    doc = json.loads(p.read_text(encoding="utf-8"))
    n = stamp_doc(doc)
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return n


# ── audit / refit ───────────────────────────────────────────────────────────
def _ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    return my - b * mx, b


def fit_from_artifacts(band=FIT_BAND, data_dir: Path | None = None) -> dict:
    """Re-derive COEFFS from the labeled artifacts. Audit entry point: this is the
    exact recipe the shipped constants came from, so a reviewer can reproduce them
    rather than trust them. Returns {'hit': (a, b), 'pit': (a, b), 'n': {...}}."""
    d = Path(data_dir) if data_dir else DATA_DIR
    lo, hi = band
    rows = []
    for side, fn in (("hit", "xfv_scored.json"), ("pit", "xfv_scored_pitcher.json")):
        for r in json.loads((d / fn).read_text(encoding="utf-8")):
            g, w = r.get("xfv_grade"), r.get("realized_war_6yr")
            if g is None or w is None or not (lo <= float(g) <= hi):
                continue
            rows.append((side, float(g), float(w)))
    fits = {}
    for s in ("hit", "pit", "pool"):
        sub = rows if s == "pool" else [r for r in rows if r[0] == s]
        fits[s] = _ols([r[1] for r in sub], [r[2] for r in sub])
    A, B = fits["pool"]
    eq = {s: ((fits[s][0] - A) / B, fits[s][1] / B) for s in ("hit", "pit")}
    # gauge: one COMMON affine so the fit pool keeps its raw pooled mean and sd
    gs = [r[1] for r in rows]
    es = [eq[r[0]][0] + eq[r[0]][1] * r[1] for r in rows]

    def _sd(v):
        m = sum(v) / len(v)
        return (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    v = _sd(gs) / _sd(es)
    u = sum(gs) / len(gs) - v * (sum(es) / len(es))
    out = {s: (round(u + v * eq[s][0], 6), round(v * eq[s][1], 6)) for s in ("hit", "pit")}
    out["n"] = {s: sum(1 for r in rows if r[0] == s) for s in ("hit", "pit")}
    return out


def top_n_side_mix(pool: dict, ns=(10, 25, 50, 100)) -> dict:
    """PERMANENT GATE. Top-N hitter/pitcher counts on the board number. The
    2026-07-25 raw-grade unification shipped a 25H/0P top 25 and no check caught it;
    this is that check. `pool` = xfv.json by_player (or a subset)."""
    rows = []
    for k, rec in (pool or {}).items():
        v = board_value(rec)
        if v is not None:
            rows.append((v, k, (rec or {}).get("side")))
    rows.sort(key=lambda r: (-r[0], r[1]))
    out = {}
    for n in ns:
        top = rows[:n]
        h = sum(1 for r in top if r[2] == "H")
        out[f"top{n}"] = {"H": h, "P": sum(1 for r in top if r[2] == "P"),
                          "pit_share": round((len(top) - h) / len(top), 3) if top else None}
    return out


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="W-SIDESCALE board grade scale")
    ap.add_argument("--fit", action="store_true", help="re-derive coefficients from artifacts")
    ap.add_argument("--stamp", action="store_true", help="apply the scale to data/xfv.json")
    ap.add_argument("--mix", action="store_true", help="top-N side mix gate on the live board")
    a = ap.parse_args()
    if a.fit:
        f = fit_from_artifacts()
        print("refit:", json.dumps(f, indent=1))
        print("shipped:", json.dumps({s: list(c) for s, c in COEFFS.items()}, indent=1))
        ok = all(abs(f[s][i] - COEFFS[s][i]) < 5e-5 for s in COEFFS for i in (0, 1))
        print("reproduces shipped constants:", ok)
    if a.stamp:
        print("enabled:", enabled(), "records changed:", stamp_file())
    if a.mix:
        doc = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
        bp = doc.get("by_player") or {}
        act = {k: v for k, v in bp.items() if (v or {}).get("kind") == "active"}
        print("enabled:", enabled())
        print("active board:", json.dumps(top_n_side_mix(act)))
        print("all rows    :", json.dumps(top_n_side_mix(bp)))


if __name__ == "__main__":
    _cli()
