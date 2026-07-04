# Post-Launch Frontier Roadmap

Specs for the frontier ideas NOT built pre-launch, plus the launch-polish
backlog. Written so post-launch work starts from paper, not memory. Feasibility
comes from the 2026-07-03 discovery pass (docs/audit/); "blocked" means the data
we would need is not currently ingested.

Tier 1 (all five: Report Cards v0, Window Alignment, Sortino, FV Tape, Draft War
Room) shipped pre-launch and are not repeated here.

## Down-tiered: largely already built (small display/rollup adds)

These came back as "frontier" ideas but the engine already exists; only a
surface is missing. Cheapest post-launch wins.

- **Crunch Index (#11).** Rule 5 exposure, option years, 40-man math per org.
  `bayes_trade_value.py` already derives `rule5_urgency_mm`, `on_40_man`,
  `options_used`, `service_days` (from `stats.py:2464-2693` transaction codes).
  Build: a per-org Crunch score (count of must-protect / squeezed players) + a
  per-player exposure chip. Effort S. No new data.
- **Portfolio Frontier (#22).** `value_framework.system_surplus_distribution`
  already does the single-factor copula (within-org correlation) + concentration
  cap + Monte Carlo (mean/percentiles/variance; `test_portfolio.py`). Build: an
  expected-surplus-vs-variance scatter + a Herfindahl concentration index by
  position/ETA bucket. Effort S. The optimization/viz layer is the only new part.
- **Prospect Greeks (#14).** Delta from the existing FV->surplus curve
  (`value_framework.surplus_value_mm`), Vega from source disagreement
  (`test_source_disagreement.py`), Theta from ETA-snapshot drift. Effort S;
  mostly repackaging existing curves. UX risk more than data risk.
- **IFA Efficiency Index (#19).** Dollars per unit realized eFV by intl class /
  country / bonus tier from `data/ifa_timeseries.json` + `ifa_export.py`.
  Effort S. Caveat: bonus coverage gaps (506/712 signings carry a bonus in
  2026); disclose the covered share.

## Tier 2: first month post-launch (real models, existing data)

- **Dev+ org development alpha (#6).** Hierarchical model of how much each org
  moves players beyond expectation: outcome deltas (FV change + realized perf vs
  eFV-implied baseline) with org random effects, controlling for acquisition
  talent (`acquisition_classify.py`) and level. Data: `xfv_history.json` (dated
  per-player FV), `scout_reports.json` (per-source dated), `prospect_path.py`
  snapshots, graduate outcomes. Math: a mixed-effects / partial-pooling fit; the
  org intercept is Dev+. Open question: grade histories are dense only for
  tracked prospects, so org-level survivorship/selection bias needs a correction
  (weight by coverage, or restrict to a covered cohort). Feasible: yes, effort M.
- **Savant Bridge AAA->MLB (#8).** Extend the CollegeSavant matched-pair delta
  method to AAA Statcast: how EV / contact / chase / whiff translate on
  promotion, ABS-regime-partitioned for anything called-strike based. Data:
  `stuff_plus_aaa.py` per-pitch AAA (2023+), `export_aaa_ball_by_ball.py`,
  `xwoba.py`. Output: eFV features + an "MLB-equivalent line" on prospect pages.
  Open question: AAA per-pitch is retained lean (count/plate-loc dropped); a
  fuller pull or a feed re-walk is needed for the plate-discipline half.
  Feasible: yes, effort M.
- **Source Alpha / lead-lag (#21).** Which FV sources move first before
  consensus follows, from grade-change histories (`prospect_path.py:98`,
  `source_backtest.py`, `data/wire_fv_first_seen.json`). Output feeds the
  source-calibration loop as informativeness weights; could surface a "who saw
  it first" panel. Open question: sparse/irregular publish cadence per source;
  source-name normalization across snapshots. Feasible: yes, effort M.
- **REM+ extensions (#13).** Leverage-weighted deployment efficiency (compare a
  bullpen's actual gmLI assignment to an optimal one via a small per-game
  assignment solve) + a multi-inning fireman index. Data: `mlb_leverage.py`
  (gmLI/WPA/SD-MD per pitcher), `backfill_win_prob.py`. Open question: leverage
  is persisted as season aggregates; per-appearance/multi-inning needs a re-walk
  of the cached winProbability feed. Feasible: partial, effort M.
- **Transmutation / Conversion+ (#15).** Realized outcome value vs the value
  implied by tool grades alone, at player and org level (org-level
  cross-validates Dev+). Data: `storage._compute_tool_deltas`, `tool_deltas` in
  timeseries, `test_tool_dev.py`. Open question: tool histories dense only for
  well-covered prospects. Feasible: yes, effort S. Sober alt name: Conversion+.

## Tier 3: spec now, build later (ambitious / partially blocked)

- **Environment Engine (#7).** One shared park/league/era factor layer. Ship the
  level/league/era unification (`level_norms.py`, `refit_overseas_factors.py`,
  `era_shrink_unification_lab.py` already exist); the **park sub-layer is blocked**
  (no venue-attributable full-population MiLB batted-ball data;
  `milb_park_factors.py` output is currently dead, see research_check RC-9).
  Feasible: partial, effort L.
- **aStuff+ v2 deception (#12).** Add arm-angle interactions, release-point
  consistency across pitch types, and movement-vs-spin-expectation gaps; publish
  the sub-score as aDeception so aStuff+ stays interpretable. Data: arm_angle is
  ingested for AAA (`stuff_plus_aaa.py`) but NOT wired into the MLB tjStuff+
  feature set (`mlb_stuff_plus.py`); movement-vs-spin must be engineered.
  MLB-only where arm angle/bat tracking is required; disclose coverage.
  Feasible: partial, effort M.
- **Attrition Curves (#10).** Discrete-time hazard model on flameout/stall:
  age-vs-level, position/role, perf trend, gap-detection from game logs as an
  injury proxy. Data: `stats.py` transactions + `roster_status.injury_history`,
  `derive_level_changes`, `build_leaderboard_gamelogs.py`. Honest limit: MiLB
  injury data is thin, so this is a partial-signal model and must say so. Feeds
  the surplus engine's bust states + a survival band on player pages. Effort M.
- **Posting Clock (#20).** Extend the overseas contract projection with
  option-exercise timing (when posting maximizes joint value). Data:
  `overseas_export.py` tracks a posting WINDOW countdown but NOT an age/service
  eligibility clock (NPB 9-yr FA / age-25 intl-amateur rules not ingested). A
  clean dynamic-programming spec on top of the existing age-branching model.
  Feasible: partial, effort M.

## Blocked (need data we do not ingest) - spec, do not start

- **Catcher Value 2.0 + Challenge Value (#9).** Reprice catchers for the ABS
  era: framing shrinks by the share of marginal calls now correctable; add
  Challenge Value (leverage-weighted overturn value above an expected-challenge
  baseline) and a team challenge-policy (option-timing) view. **BLOCKED:** zero
  catcher-defense metrics (framing/blocking/throwing runs) and zero ABS-challenge
  data are ingested today. Un-block via the existing Savant CSV pattern (Savant
  publishes the ABS Challenge Dashboard + overturns-vs-expected). Timely and
  on-brand once the data lands.
- **Exploitability / sequencing (#16), Judgment / swing decisions (#17),
  Fingerprint Matchups (#18).** All need per-pitch SEQUENCES / count-conditional
  per-pitch retention; today only season/level aggregates are stored
  (`statcast_metrics.py`, `export_aaa_ball_by_ball.py` retain rows but not a
  sequence store). Un-block by building a pitch-sequence store from the cached
  game feeds (~156k cached). Heavy data-engineering; credit prior art in the
  glossary (SEAGER for Judgment).

## Glossary reclamation: deferred (from Section B)

Shipped pre-launch: shelves + attribution + 5 missing entries + rendering.
Deferred to avoid permalink/alias churn 8 days from launch:
- Rewrite the 41 weak-quality foundation stubs to the full template (what it
  measures / scale+direction / how it works / when to trust / origin).
- 7 near-duplicate merges (CPX/Complex league, the two comp-pick variants,
  rarity-tier duplicates, wide-spread indicator/mark) with alias redirects so
  old `#g=` permalinks survive.
- Disambiguate the 13 aliases that resolve to multiple entries (SUR+, "verdict",
  "Plate Discipline", "Consensus FV", K%/BB% hitter-vs-pitcher, CPX/Complex...)
  so `resolve()` binds deterministically.
- Wire the ~199 entries reachable only via the browse page to in-context
  `data-gl` tooltips where their metric renders (close the loop both ways).

## Launch-polish backlog (from Section D, deferred)

- **Money-formatter consolidation.** 4+ divergent `$M` renderers (`fa.js:46`,
  `projections.js:25`, `trademachine.js` inline, `build_site.py`) -> the shared
  `EEPHUS_HUB.money`. Correctness-adjacent; medium blast radius (changes rounding
  on several surfaces), so gate on an output-diff.
- **Dash-glyph + fvCeil centralization.** Unify the missing-data dash; route all
  grade display through `EEPHUS_HUB.fvCeil` (epsilon-guarded) so the fallback
  path cannot round differently.
- **Ark-vs-industry origin badges on leaderboards.** A small column tag that
  advertises the glossary shelf split (the glossary now carries the `shelf`
  field to drive it).
- **Qualifier / shrinkage chips + uncertainty cues.** Bring Projections/FA up to
  MLB Stats' "min PA/IP, regressed" disclosure; add a P10/P90 cue to the
  Projections surplus cell (the band exists on FA + PROSPX).
- **Nav / masthead name consistency.** "Free Agency" vs "MLB Free Agency" vs "$
  Free Agency"; "Developers" vs "About"; "Data Sources" vs "Data Sources &
  Attribution". Reconcile carefully (test_collegesavant_nav_in_sync guards the
  nav copy).
- **PROSPX tooltip unification.** PROSPX uses a bespoke `data-term` mechanism (27
  spans); the rest of the site uses `data-gl` + `EEPHUS_GL.wire`. Unify post-launch.
