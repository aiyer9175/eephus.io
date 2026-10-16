# eFV pitcher audit fixes: harness and wording (EFV_PIT_AUDIT_FIXES)

Registered 2026-10-16, before any number below is computed. Owner decision EW3-36
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 2026-10-16), after the pitcher eFV audit (Dylan
Jordan and the pitchers who grade high): not a bug; the direction of pitcher moves is
validated; the pitcher head ties consensus on ranking; the largest moves are untested. The
owner kept pitcher w_skill at 1.0 and sent the re-basing (EFV_PIT_DRIFT_REBASE), the sign
stability read (EFV_PIT_SIGN_STABILITY) and the BA grade question (BA_GRADE_IN_CONSENSUS) to
their own lanes. This registration covers the harness and wording fixes only.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019,
vm_dev debut cohorts 2017 to 2023); no reserved frame is read; nothing is grouped, counted or
averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); no served number moves; no
model is refitted; no gate constant, blend weight or served claim changes. No em-dashes.

## 1. VAL-1: the cross-fit guard

THE DEFECT. `efv5_refit.cross_fitted` sets each fold's read weights by DS-08's OLS ratio over
the pool with that fold left out. In the re-fit's read (2026-10-15) the pitcher arrival term
e_time is nonzero only in the folds lv_dev pit|2017 (469 scored rows) and vm_dev pit|2017
(16 scored rows). With lv_dev pit|2017 left out, the pitcher arrival weight of that fold was
set from the 16 vm_dev 2017 rows alone (ratio 1.895, clipped to 1.0), and that fold's read
carried an arrival weight the served head does not have (served pitcher w_time is 0).

THE GUARD. A registered minimum `CROSSFIT_MIN_NONZERO = 100`: in `cross_fitted`, for each head
term (e_skill, e_time), the scored rows of the left-out pool with that term nonzero are
counted; under 100, the term is left out of that pool's OLS (as an all-zero term already is)
and its weight is held at 0. The fold's entry records the count and the hold. The weights of
the whole pool (`weights_from`, `_pack_weights`) and the bootstrap are unchanged. Default: hold
at 0, not at the served value, because 0 is what the existing rule already gives a term the
pool cannot estimate, and it needs no served artifact inside the harness.

SCOPE. The guard governs future runs of the harness. The registered read ran once
(`data/_labs/efv5/efv5_refit_fit.json` exists and `--run` refuses); it is not rerun and its
artifact is not rewritten.

## 2. VAL-1: the pitcher re-read at the served weights

What is read, once, from the read's own cached builds (the RT candidate's forward-chained
fold packs and phase 0's V5 orders and scored rows, the EFV_FIX_B_REFIT cache):

- orders on each fold's pitcher test rows: RT at the served pitcher weights (the production
  weights in `data/efv5_refit_weights.json`, today w_skill 1.0 and w_time 0); RT at the
  cross-fitted weights as read; RT at the guarded cross-fitted weights (section 1); V5 as
  served before the re-fit (phase 0); PROSPX consensus;
- statistic: within (side, list year) Spearman, the read's instrument (`efv_v3_backtest.paired`,
  E_cond player-clustered CI95, B 2000, the backtest seed);
- cells: lv_dev, vm_dev and both pooled, pitchers only; lv_dev also by fold (list year), which
  is the read's own fold stratum;
- comparisons: served-weights RT minus V5, minus consensus; as-read RT minus V5; guarded RT
  minus V5, minus consensus.

NULL COMPARATOR. The served-weights order with e_skill permuted among the test rows of each
fold (1,000 permutations, seed 20261016): the distribution of the pooled within Spearman
minus consensus under no skill information. Reported: the null's 2.5 and 97.5 percentiles and
the share of permutations at or above the served value.

PLANTED RECOVERY. On the same pitcher rows, the realized WAR is replaced by a planted outcome
u_c + k * e_skill + noise (Gaussian, SD 0.3, seed 20261016) for k = 0 and k = 1, and the
served-weights order is read against consensus with the same instrument. Recovery holds when
k = 1 gives a served-minus-consensus delta with its CI95 lower bound above 0 and k = 0 gives a
delta at or below 0. If recovery fails, the re-read is reported as uninterpretable and the
attribution is not restated from it.

What it decides: nothing. It restates the attribution of the re-fit's reported pitcher lv_dev
loss in `docs/efv-v2/EFV_V5_REFIT_RESULTS.md` and the program ledger (`docs/efv-v2/STATUS.md`)
as a harness cross-fit effect or not, from these numbers. The served claim and the ledger rows
of `data/efv_progress.json` are untouched.

## 3. DRV-3: the spread test in the drift report

`efv5_combined.support_clip` reports drift only when a column's served nonzero share passes
DRIFT_RATIO (2.0) times its training share. It never compares spread. Added, report only: for
each candidate key, the SD among nonzero values on the production training rows
(`training_support`, new field `nonzero_sd`) and among the served nonzero values before the
clip; their ratio is written to the key's receipt entry (`spread_ratio`) whenever both sides
have at least 20 nonzero values, and the key is flagged `spread` when the ratio passes
`SPREAD_RATIO = DRIFT_RATIO` (2.0, the same 2x rule). A flagged key is listed under its
family note (`spread`) and in `receipt["spread"]`. Values, clips, withholds and family status
are unchanged; nothing served reads the new fields.

Known before registration (the audit, not this lane): the Single-A starter strikeout rate
column's nonzero spread is 1.15 live against 0.92 in training (about 1.25x), so the 2x rule
reports its ratio but does not flag it. Tightening the threshold is an owner choice.

## 4. CON-3: the popup chip text

The chip label of `scr_w2b_pu_p` ("Popup rate allowed") is printed beside an up or down arrow.
Its fitted slope is negative, so a pitcher who allows few popups is moved UP, and a reader of
"Popup rate allowed" with an up arrow reads the opposite. The label is rewritten so it says
that a low popup rate grades up and why (the fit's sign on past WAR with the other drivers
held equal). Text only: the driver, its slope and every number stay.

## 5. PEER-5: eFV against Baseball America

The stored Baseball America grade is the risk-adjusted grade (raw minus 0 to 20); an eFV-vs-BA
comparison on it compares against a different scale. Procedure: scan the module root (Python,
the module assets, prospx) for any computation that sets an eFV grade against a Baseball
America grade; each one found reads `ba_raw_grade` (the raw grade under
`tools._extras.ba_raw_grade`) instead. If none is found, that is recorded with the scan, and
the audit's own eFV-minus-BA table is re-run on the raw grade outside the repo. Whether
consensus should read the raw grade is not decided here (BA_GRADE_IN_CONSENSUS).
