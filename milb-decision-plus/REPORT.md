# MiLB Swing Decision+ Rebuild — Research Report
**Project:** `~/milb_decision_plus/` · **Date:** 2026-06-12 (v2: universal-zone revamp) · **Data:** MLB Stats API play-by-play, 2021–2026 (6 levels) + statline backbone 2000/2008–2026

---

## v2 Zone Revamp (supersedes the tier/zone claims below where noted)

The v1 conclusion that AA/A+ have "no zone data" was wrong in the way that
matters: tracked pX/pZ don't exist there, but **stringer-entered pixel
coordinates (x/y) cover ~100% of pitches at every level**, with per-batter
strike-zone bounds. v2 re-extracted all 68,866 games capturing them.

- **Calibration** (`scripts/calibrate_zones.py`): pixel→feet transform fit on
  800k dual-system pitches; holdout pX RMSE 1.3 in (R² .983), pZ 2.5 in
  (R² .952). Fitted in/out geometry recovered plate-half-width + ball radius
  (xlim .83 ft, buffer .12 ft) from data. **In/out zone agreement 95.9%**
  holdout; **93.5–95.8% at minor-league tracked parks** (out-of-domain
  stringer test) — minors stringers ≈ MLB stringers.
- **Player-level attenuation QA**: chase% computed from stringer zones vs
  official zones on identical 2025 AAA pitches: **r = 0.991** (MAD 1.35pp);
  z-swing r = 0.991. Pitch-level zone noise washes out at player grain.
- **Coverage guarantee**: 100.00% of players with PA≥20 at every level-season
  have pitch AND zone data (`outputs/coverage/player_zone_coverage.csv`).
  No FV/ranking filter can exist — the extraction unit is the game.
- **EB shrinkage bug found & fixed**: the moment-matching noise term was an
  unweighted mean over players, so tiny-sample players inflated it past the
  observed variance → prior strength k exploded → entire level-seasons of
  components crushed to the mean (this is why take-ball share and early-season
  chase looked dead, and why v1 Model E blew up at MLB BB%). Noise term now weighted
  consistently with the variance estimate; k capped at 5,000.
- **Revised incremental results** (common sample, time holdout, fixed
  shrinkage): components+zone add value at EVERY full-season level —
  A BB% +3.8pp R², A+ BB% +2.7pp, AAA BB% +5.7pp, MLB BB% +7.7pp, K% +0.8 to
  +3.3pp, BBK +2.5 to +3.7pp vs common-sample Model C. **However the deep
  statline backbone (2008+) still beats all short-window component models for
  K%/BB% at AAA/AA by 7–15pp R²** — unchanged champion there.
- **Shipped champion (all ridge)**: AAA/AA/CPX → deep-statline C;
  **A/A+ → Model Z** (statline + decision components + chase/z-take/z-contact;
  beats E on BB% +2.1–2.3pp, ties K%). Race re-run: ridge ≈ elastic > spline >
  GBM; ridge kept (simplicity).
- **Decision+ composite v2**: zone components joined the core (weights:
  z-take +.31, zone-recognition +.21, 2K-called −.17, chase +.13 suppression
  term, swing −.08). Redundancy partials improved (AA +.43, A +.42, CPX
  +.06→+.18). Y2y stability improved: r .56 @700 pitches, .75 @2300+
  (k_eff recalibrated to 800 pitches). Composite remains **descriptive-only**
  as a single feature (Model D ΔR² ≈ 0).
- **Tiers v2**: A = true ball tracking; **B = calibrated stringer zone
  (universal, ~94–96% in/out accuracy)**; C = thin sample; D = inconsistent.
- **Zone graphics shipped**: per-player 13-zone swing-rate, damage (TB/swing),
  and contact grids for all 2,169 current players at every level, rendered as
  inline heatmaps in the tool (`data/processed/zone_grids.parquet`).

## Executive Summary

The MiLB swing-decision project was rebuilt from the data up. The old player-centric
scraper (21% coverage of the proper universe) was discarded and replaced with a
**game-centric extractor**: every completed regular-season game's play-by-play feed,
parsed once, for **68,866 games across MLB/AAA/AA/A+/A/CPX × 2021–2026, with zero
failed games**. Reconstructed PA/K/BB match official statlines essentially perfectly
(K and BB 100% exact at most level-seasons; gate PASS).

Findings, in one paragraph: **MiLB Decision+ is a valid, stable descriptive metric**
(y2y r .30→.64 by sample; partial r +0.30..+0.45 with next-season BB-K after
controlling for current BB%) and the leaderboard surfaces exactly the right names.
As a **projection input, the composite adds nothing** beyond historical K%/BB%+age
(Model D ΔR² ≈ 0 everywhere) — but its **components do**: at A and A+ (where no deep
statline history exists) contact% + take-quality + Decision+ add **+1.5 to +3.9pp R²**
to next-season K%/BB%/BB-K projections. At AAA/AA, the 18-season statline backbone
remains unbeatable for K%/BB% (deep-C R² .57/.36 at AAA); short-window component
models cannot overcome 2021–23 era turbulence (pitch clock, ABS at AAA). The shipped
system therefore uses **per-level champions**: deep-statline ridge at AAA/AA/CPX,
statline+components ridge at A+/A — all simple, calibrated linear models.

## Data Pipeline Validation Report

- Universe: schedule-derived game manifest (gameType=R, state Final), 68,866 games.
- Extraction: one playByPlay fetch per game; pitch rows (call code, pre-pitch count,
  zone/coords where tracked) + PA rows (event type, is_pa flag) written separately so
  PA reconstruction never depends on pitch-tracking completeness.
- 0 failed games; 0 duplicate (gamePk, play_idx) plays; 318 MB raw parquet.
- Official statline reference: one combined split per player-season-level from the
  stats API (verified 100% identical to projection_engine deep_minors on AA 2025).

## PA Reconstruction Report (GATE: **PASS**)

Per level-season vs official lines: PA correlation = 1.000 everywhere; PA exact-match
95.4–100% (residual is ±1 PA on ~1% of players from baserunning-ending/interrupted-PA
event classification); **K, BB, HBP exact-match ≥ 99.6%, mostly 100%**. K%/BB% rate
MAE at PA≥50: ≤ 0.06pp. Full table: `outputs/validation/pa_reconstruction_by_level_season.csv`.

## Data Quality Tier Report

Empirical tracking coverage (share of pitches with zone/coords), measured per player:

| Level | Tracked share | Tier A rows | Tier B rows | Tier C rows |
|---|---|---|---|---|
| MLB | ~100% | 2,429 | 402 | 1,443 |
| AAA | ~100% (2023+), call-code-only 2021–22 | 1,946 | 1,373 | 2,254 |
| AA | **0%** | 0 | 3,033 | 1,426 |
| A+ | **0%** | 0 | 3,086 | 1,377 |
| A | ~30%, park-dependent | 656 | 2,651 | 1,832 |
| CPX | 2–17% by season (incl. DSL) | 0 | 2,751 | 7,390 |

Tier A = coords ≥50% & ≥500 tracked pitches; B = ≥300 pitches call-codes;
C = thinner; D = inconsistent (excluded). **Zone metrics (chase, z-take) are never
imputed where tracking does not exist** — AA/A+ rely on the call-code core
(take quality, 2-strike discipline, count-state selectivity, contact/whiff).
A-level Tier A zone metrics are park-biased (tracked parks only) — documented caveat.

## Ground Truth Audit

Year-over-year (PA≥100 both sides): K% r .60–.79 (most reliable target), BB% .44–.62,
BB-K .52–.69; rises with level. All targets are valid north stars; K% is the
strongest, CPX the noisiest. Full: `outputs/baselines/*_ground_truth_audit.csv`.

## Historical Baseline Report (Models A–E, time holdout train≤2023)

Common-sample ΔR² vs Model C (hist K%+BB%+age+PA):

| Level | D (+Decision+) | E (+components) K% / BB% / BB-K |
|---|---|---|
| AAA | ~0 | +1.3pp / +1.9pp / +3.0pp |
| AA | ~0 | +2.3pp / +2.8pp / +3.5pp |
| A+ | ~0 | +3.2pp / −0.5pp / +3.9pp |
| A | ~0 | +1.5pp / +0.7pp / +1.5pp |
| CPX | ~0 | negative (REJECT components at CPX) |

**But** deep-history Model C (AAA/AA trained 2008–2023) beats common-window E for
K%/BB% at AAA/AA (e.g., AAA K% .571 vs .482, same test set). Residual/fusion stacking
(incl. proper out-of-fold stage-1) could not rescue the components at AAA/AA for
K%/BB% — the 2021–23 era shift (pitch clock, ABS) makes short-window residual
learning unstable. For BB-K at AA, E beats even deep-C (.395 vs .361).

## Decision+ Descriptive Report

- Core components (all levels): take-ball share, 2-strike called-strike share,
  first-pitch/3-ball/overall swing rates. Weights learned by ridge on next-season
  BB-K, train ≤2023 only. Dominant weights: overall passivity (−.41), 2-strike
  called-strike avoidance (−.36).
- EB shrinkage per component within level-season; composite reliability calibrated
  empirically (y2y stability → k_eff ≈ 900 pitches); posterior SD and CI80 shipped.
- Redundancy: r(D+, BB%) = .55–.62 (related, not duplicate); **partial r(D+,
  next-season BB-K | current BB%) = +.30 to +.45** at all full-season levels.
- Face validity: 2026 leaders = Jonah Bride, Matthew Wood (11% K / 22% BB),
  LaMonte Wade Jr.; trailers = extreme hackers (Raylin Heredia 28% K / 3% BB).

## K% Projection Report

Champion (ridge): AAA .571 R² / AA .557 (deep-C), A+ .477 / A .439 (E-components),
CPX .343. Pearson .66–.76 at full-season levels. MAE 3.3–4.9pp by level.
Calibration decile MAE ≤ 0.6pp except top-decile over-projection at AAA/CPX (+2.3pp,
extreme-K mean reversion) — flagged.

## BB% Projection Report

Champion: AAA .355 / AA .367 (deep-C), A+ .254 (C marginal over E), A .282 (E),
CPX .214. BB% is intrinsically less projectable (lower y2y reliability). Known
test-era bias: −1pp at AA/A (walk-environment drift 2024–25 vs train window) —
flagged for season-intercept recentering.

## AAA-to-MLB Translation Report

- Full-history (2008–2026) promotion pairs: AAA→MLB n=4,123, AA→MLB n=1,789.
- Held-out (2021+) AAA→MLB: K% r=.673 (slope .84 — K% translates strongly),
  BB% r=.540 (slope .48 — half-strength). AA→MLB: K% .663, BB% .478.
- Level ladder (within-player same-season): AAA→MLB +4.6pp K / −2.5pp BB;
  internally consistent (AA→MLB direct = sum of steps within 0.2pp).
- 2025-AAA → 2026-MLB movers (n=75): K% r=.689, BB% r=.493; Decision+ transfers as
  behavior (r=.376 with MLB Decision+) and r≈±.25 with realized MLB K%/BB%.
- No MLB swing-decision model used as input or target anywhere (circularity rule).

## Incremental Value Report

Composite Decision+ → **no incremental projection value at any level** (keep
descriptive). Components → **approved as projection inputs at A and A+ only**
(+1.5..+3.9pp R²); rejected at AAA/AA (deep statlines win) and CPX (negative).

## Leakage Audit

All PASS: next-season pairs verified by age progression; zero duplicate
(player,season,level) rows; 2026 partial-season rows never trained on; Decision+
weights trained ≤2023 only; OOF stacking used for residual experiments; translation
is statline-only. Multi-level player-seasons are separate rows by design (level is
part of the grain); player-holdout splits confirmed no inflation
(player-holdout R² ≈ time-holdout R²). File: `outputs/audits/leakage_audit.txt`.

## Calibration Audit

`outputs/audits/calibration_deciles.csv`. Flags: top-decile K% over-projection at
AAA (+2.3pp) and CPX (+2.7pp); broad −1.0 to −1.4pp BB% under-projection at AA/A in
the 2024–25 test window (era drift). Elsewhere decile errors < 1pp.

## Stress Testing Report

`outputs/audits/stress_tests.csv`. Failure modes: (1) high-K hitters — rank
resolution within the extreme group is weak (r .18–.26); (2) high-BB hitters at
AA/A — BB% under-projected by ~1.2–1.7pp (mean-reversion + era drift); (3) CPX —
everything is noisier; components rejected there. Young-for-level and tier-B
subgroups show no degradation beyond their sample sizes.

## Model Strategy Race Report

Ridge vs elastic net vs spline-GAM vs gradient boosting: **GBM loses everywhere**
(mean R² .305 vs ridge .339); splines edge ridge ≤1pp on K% at AAA/AA but calibrate
worse. Per the simplicity rule, **ridge ships everywhere**.
File: `outputs/model_race/strategy_race.csv`.

## Reproducibility Report

Every run appended to `reports/run_log.jsonl` (experiment id, timestamp, data
versions, windows, ns). Pipeline is deterministic (SEED=42), resumable (done.txt
per level-season), and re-runnable end-to-end:
`build_game_manifest → extract_pitches → pull_official_statlines →
build_player_metrics → validate_reconstruction → build_transitions →
build_decision_plus → ground_truth_and_baselines → model_strategy_race →
run_audits → build_level_translation → ship_projections → build_tool`.

## Approved Outputs

- `data/processed/decision_plus.parquet` — descriptive MiLB Decision+ (34,049 rows,
  2021–2026, all levels) with tiers, reliability, CI80, components.
- `data/processed/shipped_projections_2026.parquet` + `outputs/exports/*` —
  2,162 current players with projected K%/BB%, MLB-equivalent K%/BB%/Decision+.
- `outputs/leaderboards/*` — full/per-level boards, MLB reference board,
  AAA→MLB transition board.
- `outputs/tool/milb_decision_plus_tool.html` — rebuilt standalone browser tool.
- Level ladder + promotion translations (`outputs/translation/*`).

## Rejected Outputs

- Composite Decision+ as a projection feature (Model D) — no incremental value.
- Components at AAA/AA for K%/BB% projection — deep statlines win.
- Components at CPX — negative OOS value.
- Whiff% as a model feature alongside contact% — perfect collinearity.
- Residual/fusion stacking on deep-C — era-unstable, no gain.
- Zone-imputation at AA/A+ — no tracking exists; never imputed.

## Next Experiments

1. Season-intercept recentering for BB% projections (fix −1pp era drift at AA/A).
2. Extreme-tail recalibration for K% top decile (AAA/CPX +2.3pp over-projection).
3. Split CPX into complex (ACL/FCL) vs DSL; DSL likely drives the noise.
4. Backfill ages for the 1.1% of players missing from Chadwick (people API).
5. ABS-era zone behavior at AAA 2023–25 as a natural experiment for take quality.
6. Feed `proj_k_pct`/`proj_bb_pct` (A/A+ component-augmented) into the main
   hitter projection engine as the minors K/BB prior; benchmark against its
   current backbone before adopting (integration rule).

## Integration Rule Outcome

Per the governing rule: composite MiLB Decision+ ships **descriptive-only**.
The main projection model should consume **projected K% / BB%** (which already
embed component value where it exists) plus, optionally, the raw components at
A/A+. Exports: `outputs/exports/milb_decision_plus_all_seasons.parquet`,
`outputs/exports/milb_projections_2026.parquet`.
