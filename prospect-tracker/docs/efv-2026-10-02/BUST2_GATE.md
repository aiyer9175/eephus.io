# BUST2: the bust redesign's pre-registration (committed 2026-10-02)

STATUS: REGISTERED, RESULTS EMPTY. Committed ALONE, docs only, under
`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` section 3.5 item 3 ("Before the
epoch: commit BUST2 alone"), BEFORE any lab code exists. No number in this document was
computed at this commit: the counts quoted inside the registered text are the plan's own
2026-09-11 label-only descriptives and carry that date.

- Plan: `docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`, section 3 (the bust
  redesign). Section 3.2 holds the recorded conventions (REACHED, BUST-MLB, BUST-NEVER,
  CENSORED-NEVER, NON-BUST) and section 3.4 the text registered below, verbatim.
- Owner answer that executes it: EPOCH-Q3 (O7), `DECISIONS_FOR_OWNER.md`, answered
  2026-09-30: "R, A1 and A2, each shipping only if its own clauses pass, no L1 flooring,
  Arm R's flag built in the gap".
- **Arm R RIDES the fWAR label epoch as a matrix arm** (`docs/efv-2026-09-17/
  FWAR_LABEL_EPOCH_GATE.md` part 6, the ride list, row "Arm R, the never-MLB resolution
  fix"; clause (i) factor F3). It is never run alone. Its flag is
  `efv_dataset.NEVER_RESOLUTION_ARM_R`, default False, built in the gap by task
  EPOCH_ARMS_LAB; the arm matrices builder is `tools/efv_fwar_epoch_arms.py` and the
  epoch lab that prints Arm R's clauses is `tools/efv_fwar_label_epoch_lab.py`.
- **Arm S does NOT ride the epoch.** FWAR_LABEL_EPOCH_GATE.md part 6 lists "BUST2 Arm S"
  under "May NOT ride". Arm S is an odds change and goes to its own lane after the epoch
  (plan 3.5 item 5), with its own look under this registration's primary and secondary
  clauses.
- Arm R's own clauses are the Arm R paragraph of the registered text below: the
  resolved-to-censored count is reported FIRST; STOP if the full-pool bust share moves more
  than 10 points; the rank clause is E_cond pooled Spearman non-inferior to E0 at the 0.02
  TOST margin per side, on floors re-derived on the final frame, scored against BOTH the E0
  evaluation label and the Arm R label, both published. Under clause (i)'s leave-one-out
  reading the comparison is `Q(E*) - Q(E* minus Arm R)`; "E0" in the paragraph names the
  incumbent pool rule (every never-MLB row resolved except `bust_recent`).
- The window Arm R reads. Section 3.2 says "no affiliated line in either of the two latest
  seasons with MiLB data on disk (id known)"; FWAR gate part 6 says "no affiliated line in
  either of the two latest seasons with MiLB data on disk at the build". The two agree: "id
  known" names the row condition and "at the build" names when the on-disk seasons are read.
  The registered text below does not restate the window and so cannot differ from either.
- The union invariant the registered text requires ("BUST-NEVER plus BUST-MLB reproduces the
  served realized-bust event on every resolved row") is `test_bust2_union_invariant.py`,
  with a fixture part that always runs and a live part over the current matrices. EPOCH_RUN
  runs the live part at step F before the Arm R arm is built; a failure there makes Arm R a
  FAILED ARM (clause (i) point 5).
- The L1 flooring (debuted negatives floored at 0) does NOT ride: plan 3.3 and FWAR gate
  part 6 ("May NOT ride"). Negative six-season labels stay negative on every arm.
- Nothing above the Results heading may be edited once anything is written below it (the
  `EPOCH_2026_PREREGISTRATION.md` pattern).

## The registered text (plan section 3.4, verbatim)

> **BUST2 pre-registration.** Written before any fit, lab or look. Any change to a
> definition, threshold, frame, metric or margin after the first candidate score
> DISQUALIFIES the candidate.
>
> **Definitions** are the recorded conventions of section 3.2. The union BUST-NEVER plus
> BUST-MLB reproduces the served realized-bust event on every resolved row (an invariant
> test, asserted before the lab runs).
>
> **Two arms, Holm across the family.**
> **Arm R** (never-resolution) is a LABEL change. It rides the eFV label epoch as its own
> matrix arm, never alone. Report the resolved-to-censored count FIRST (395 full-weight
> still-affiliated rows today). STOP if the full-pool bust share moves more than 10 points.
> Rank clause: E_cond pooled Spearman non-inferior to E0 at the 0.02 TOST margin per side, on
> floors re-derived on the final frame (runbook step G), scored against BOTH the E0
> evaluation label and the Arm R label, with both published.
> **Arm S** (the split) is an ODDS change. Heads: P(REACHED) and P(BUST-MLB given REACHED),
> each a function of the served odds grade and the side only (no new covariates).
>
> **Frame:** forward-chained by decision year over 2014 through the last decision year
> whose six-season windows are all closed under the RESOLVED_THROUGH in force at the run
> (2020 at RT 2025, 2021 at RT 2026). Served-comparable rows only, each fold trained strictly
> on earlier years. Power is stated in advance and re-published on the final label.
>
> **Primary (Arm S):** three-class multinomial log loss, pooled over folds. Paired bootstrap
> B = 2000, resampling the TRAIN frame and REFITTING on every draw, seed 20260807. The
> candidate must beat ALL THREE comparators with the CI95 of the difference excluding zero:
> C0, the incumbent served p_bust split by the train-fold constant P(never given bust);
> C1, the train-fold three-class base rate; C2, the candidate with its conditioning column
> row-permuted within fold. It must also exceed the p95 of a label-permutation null band.
> **Secondary, all must hold:**
> (i) the implied binary P(any bust) is non-inferior to the served p_bust at 0.005 Brier and
> 0.02 log loss;
> (ii) Murphy resolution rises with a CI95 above zero, and reliability worsens by no more
> than 0.005;
> (iii) per-category reliability tables (8 equal-count bins, Wilson CIs) are published per
> side;
> (iv) P(BUST-MLB given REACHED) beats the train-fold constant conditional rate on log loss
> on resolved debuted rows alone;
> (v) a test asserts zero rows move `xfv_grade`, rank, `xfv_war_6yr` or `surplus_mm`.
> **Not a criterion:** pooled bust ECE (a zero-information constant reproduced 152.7% of a
> candidate's ECE gain in `xfv_dist_recalibration`).
> **On failure:** the split may ship only as a DISCLOSURE (the served p_bust with its
> base-rate decomposition, labelled as a base rate), never as a model.
> **Label-source clause:** results bind the label they were measured on. The category churn
> table on the final label is published before any score.

## Results

**EMPTY AT REGISTRATION.** No count, share, margin, interval or disposition has been
computed under this registration at this commit. The first entry here is dated and names
the commit and the label it was measured on (the label-source clause binds).
