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

## Results

PENDING. Data-blocked at registration (2026-08-18). MiLB SDR coverage is
UNKNOWN (the intake request asks whether defense-plus's 15_milb_translation
stage produces player-level MiLB SDR at all).
