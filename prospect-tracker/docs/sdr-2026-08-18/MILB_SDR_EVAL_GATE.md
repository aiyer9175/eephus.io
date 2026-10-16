# G-C: milb_sdr_eval, the MiLB SDR validation gate (pre-registered 2026-08-18)

STATUS: REGISTERED, DATA-BLOCKED. This artifact is the source of EVERY public
claim about MiLB SDR. "The most advanced MiLB defensive metric on the market"
may be printed only if a cell in this artifact derives it; hardcoded accuracy
claims are a banned defect class (2026-08-13).

## The question

Does MiLB SDR, measured before a prospect's debut, predict MLB defensive
value (and MLB SDR itself)? The baselines are the two named incumbents from
the record: the FG field grade (Spearman 0.28 on the realized positional
value frame) and prospect_def_value (0.68, validated 2026-06-29). Both
baselines are RE-RUN on this gate's exact frame; their recorded numbers
belong to their own frames and are not the bar.

## Frame (census-dependent, fixed at census commit)

- Decision-year folds restricted to MiLB-SDR-covered years per the census.
  Expect FEW folds. The honest first outcome may be an underpowered null and
  is recorded as UNDERPOWERED, never as "SDR does not predict".
- Forward-chained, the leakage rules of the eFV lab protocol; the label is
  realized MLB defensive value (rfield runs per season over the first 3 MLB
  seasons, plus MLB SDR where covered, reported separately).
- Missingness indicators inadmissible (era proxies).

## Clauses (frozen)

1. C1: Spearman of MiLB SDR (latest pre-debut season, runs per inning) vs
   realized MLB defensive value, per side of the frame, vs BOTH re-run
   baselines on identical rows. Creditable only above a floor derived on
   this frame at measurement time, Holm across cells, noise twin per cell.
2. C2 (only if MLB SDR coverage permits): MiLB SDR vs MLB SDR, the direct
   skill-persistence read.
3. C3 LEVEL VALIDITY (reported): per-level cells (AAA/AA/High-A...) so any
   public per-level board claim has a per-level receipt.

## Consumers this gate feeds (each still owns its own ship gate)

The W2 MiLB SDR chip (display-only, the def_home contract), the W4 eFV
driver attempt (one registered attempt, after W3 defines the label), the W4
fallback COMPONENT model, and every W6 glove-board superlative.

## Amendment 2026-10-15: what the in-house drop can carry for MiLB (owner decisions EW3-18, EW3-5)

Committed alone, docs only, before the drop exists and before any census. Written
from reading Will's code, not from any number.

- **The open question is answered from the method itself.** The registration asked
  whether defense-plus's 15_milb_translation emits player-level MiLB SDR. It does not.
  Its own docstring: "No MiLB tracking exists, so position HISTORY is the signal." It
  builds the AAA (else AA) primary-position to MLB primary-position transition matrix
  from StatsAPI games started; it carries no runs. The only other MiLB output,
  26_prospect_prior.py, is a prior assembled from scouting grades (field, speed) and
  body frame, trained on realized MLB OAA; it measures nothing in the minors and its
  main input is the FG field grade this gate names as a baseline.
- **Rule, fixed now.** G-C's clauses need a pre-debut MiLB SDR in runs per inning. If
  the census of the in-house drop (`sdr_intake`, task EWAR_SDR_INHOUSE) carries zero
  rows with a level other than MLB, G-C is recorded NOT RUN: no predictor exists, so
  C1 to C3 have nothing to score, and the result is not "MiLB SDR does not predict".
  `data/milb_sdr_eval.json` then replaces the stub with that record, the census
  evidence and the 15_milb_translation transition matrix run in-house from cached
  StatsAPI fielding lines (descriptive context, no claim). No public MiLB SDR claim is
  licensed by it.
- **What would re-open it.** A MiLB defensive measurement in runs (Will's or ours)
  registered as its own predictor before any number; the clauses above then run as
  frozen.
- **Timing (EW3-5).** Recorded as an OWNER-WAIVED EARLY READ.

## Results

At registration (2026-08-18): data-blocked; MiLB SDR coverage unknown.

### 2026-10-15: G-C NOT RUN, OWNER-WAIVED EARLY READ (EW3-5)

- **Census** (`data/sdr_census.json`, committed at 133b0566 before any clause): the in-house
  drop holds 3,466 rows, every one MLB; MiLB rows 0. Under the Amendment 2026-10-15 rule
  (committed at 0cffb4be, before the drop existed) G-C is NOT RUN: there is no pre-debut MiLB
  SDR to score, so C1 to C3 have no predictor. This is not a finding that MiLB SDR fails to
  predict MLB defense.
- **Why, from the method.** 15_milb_translation measures position history only (AAA, else AA,
  primary position by games started); 26_prospect_prior is a scouting-grade and body-frame
  prior trained on realized MLB OAA, built from the FG field grade this gate names as a
  baseline. Neither is a minor-league fielding measurement in runs.
- **Context, descriptive, licenses no claim** (`data/milb_sdr_eval.json`). Will's 15 run
  unedited on cached StatsAPI fielding lines (cohort: MLB position players first seen 2015 or
  later with 100+ career starts at the primary position; 487 usable with an AAA or AA primary
  position). Holding the AAA position in MLB: C 96.5% (n 86), CF 69.3% (88), 3B 62.7% (59),
  2B 59.1% (44), SS 53.9% (76); AAA shortstops land at 2B 28.9% and 3B 10.5%. His own
  2026-06-18 run read C 95%, CF 70%, 3B 67%, SS 57%, 2B 56% on 462 players (his usage spine
  is not in the repo; the spine here is StatsAPI games started, 2000 to 2026).
- **What would re-open it.** A MiLB defensive measurement in runs, registered as its own
  predictor before any number (owner question SDR-MILB-Q1 in the task report).
