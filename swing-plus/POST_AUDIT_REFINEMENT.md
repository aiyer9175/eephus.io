# POST-AUDIT REFINEMENT REPORT
**Experiment:** REFINE-2026-06-11 · `pipeline/07_refinement.py` · engine eval harness
(leave-one-transition-out ridge, fixed sample per comparison, n=538) · deterministic ·
**Owner:** @willclq

## Executive summary

Six audit findings tested under the universal gates. **Approved: 2** —
LA-dispersion/adjustability (the thrice-flagged signal is real) and zone-seen
pitcher-respect (the first thing to ever beat BB% history). **Rejected: 3** —
sprint speed (the audit's #1 hypothesis, killed by its own test), B2B+ restructure
(B2B+ vindicated instead), and elite-tail recalibration (tails turned out healthy).
2026 refit checklist prepared. Engine updated to **v2.1** with exactly two new
signals — the smallest set that improves accuracy, per the final rule.

## S1 — Sprint speed: **REJECT** (intuitive ≠ predictive)

Reliability superb (y2y r = .907; ages −0.14 ft/s/yr) — but incremental value
beyond hist+skills is ≤ +0.11 RMSE pts on every target (babip −0.03, avg −0.01,
woba +0.10, iso +0.11). The Edwards/Turang/Hayes residual pattern was real but
its predictive content is already absorbed by history + skills. Ownership answer:
sprint speed stays where the variance model put it (inside e2, vs naive baselines)
and joins **nowhere else**. The system audit's top priority is hereby falsified —
which is the framework working exactly as designed.

## S2 — LA dispersion / adjustability: **APPROVED**

`attack_angle_std` (swing-to-swing launch-shape variability): reliability y2y
**.840** (a stable skill, not noise). Incremental beyond hist+skills:
**BABIP +0.42, xBA +0.25, xwOBA +0.22, AVG +0.14**, K% 0.0 — the largest candidate
gains of this round, exceeding the Aging/Variance/Translation module contributions.
Coefficient **positive**: more dispersion → sustained BABIP — supporting the
**adjustability/contact-shaping** interpretation (Arraez-type hit generation), not
the swing-inconsistency one. Stress: positive in all archetypes for BABIP (power
+0.66); xwOBA negative only in the power tercile (−0.27; ALL +0.22) → shipped on
the contact-shaped targets (avg, xwoba) only. Leakage LOW (year-t bat-tracking
aggregate). The variance model (cons_la_sd ↔ babip posterior −.38), system audit
(resid corr +.13), and this test independently agree. Ownership: engine feature
(adjustability signal); a full Adjustability+ axis is the 2027 question.

## S3 — B2B+ ownership review: **KEEP — vindicated, no restructure**

The other four axes explain only **R² = .03 of B2B+ (97% unique)** — it absolutely
owns its territory (contact-quality damage conversion). The system audit's negative
marginal was a sequential-order artifact: in direct drop tests B2B+ earns its seat
on every target (avg 27.3→27.4 without it, xba 21.3→21.5, xwoba 28.6→28.9,
xslg 52.1→52.7). Collision re-anchor alternatives REJECTED (drop+collision and
keep+collision both worse or equal — consistent with the collision audit's
framework-redundancy verdict). Ownership matrix updated: B2B+ overlap risk
downgraded MED → LOW.

## S4 — Walk skill: **zone_seen APPROVED (BB% only); no new module**

Against the spec's hard bar (beat BB% history): chase +0.14, z-swing −0.13,
Decision+ −0.09, **zone_seen +0.33** (all-candidates +0.20 < zone_seen alone —
collinearity, keep the one). Mechanism: pitcher-respect correction — hitters
currently attacked in-zone more than their profile warrants see the respect (and
the walks) adjust next season. Positive in all archetypes (+0.05/+0.68/+0.57).
Ships for **bb_pct only** (it *hurts* woba/obp/ops: −0.11/−0.13/−0.23). No
walk-skill module is created — one feature, clearly owned, exactly as the spec
prescribes when history is nearly sufficient.

## S5 — Elite-tail calibration: **REJECT (tails are healthy)**

The fusion engine dissolved most of the compression the system audit measured on
the older spec: xwOBA top-10% error +0.0018, top-5% +0.0033; wOBA +0.0060/+0.0077.
CV'd isotonic recalibration makes overall accuracy WORSE (xwOBA 28.6 → 29.4; wOBA
32.7 → 32.8). The variance model's elite-tail carry (2.2×) remains a talent-layer
note, not a calibration patch. Revisit only after the 2026 refit.

## S6 — 2026 refit checklist (prepared, not executed)

When 2026 completes: re-pull raw H2 + collision + sprint + statsapi; re-run in
order: collision audit → contact_v2 → dcv/b2b 2026 finals → variance layer →
aging panel+curves (M8 cascade espec.) → backbone (add 2023→26 transitions) →
engine race (full prior stack RE-TEST at larger n — the overfit verdict may flip)
→ system audit value ladder → benchmark. Diff every verdict pre/post; the
reserved-holdout design means 25→26 graduates into training and 26→27 becomes
the new untouched holdout.

## Updated value-added leaderboard (engine v2.1)

#1 Historical priors+backbone · #2 Swing+ (~70% of skill lift) · #3 DCV+ (~18%) ·
**#4 LA-dispersion (new: +0.14…+0.42 on contact targets)** · #5 Aging cascade ·
**#6 zone_seen (new: +0.33 BB%)** · #7 B2B+ (vindicated, unique-but-small) ·
#8 Variance (constants/display) · #9 Translation (portability) · #10 Decision+/
Contact+ (decomposition & thin-history roles) · REJECTED: sprint speed.

## Updated research priorities

1. **2026 refit** (everything above is v1 on 2½ seasons)
2. Adjustability+ axis exploration (S2 promotes it from backlog to validated signal)
3. Playing time (cleared by the GO; unchanged)
4. Elite-tail: revisit post-refit only
5. De-prioritized permanently: sprint speed (engine), B2B restructure, weather,
   archetype-specific models (0-for-4 now)

## Addendum ADJX (2026-06-11): the Adjustability+ axis question — RESOLVED

**Q1 — why did the discovery audit reject what the engine now accepts?
BASELINE-DEPENDENT, confirmed.** Gain from raw `attack_angle_std` on next BABIP:
**+0.05 on the discovery-era thin baseline** (own-stat history only — exactly
why SDA-M1 rejected) vs **+0.45 on the full v2 stack**; xwOBA −0.10 thin vs
+0.11 full. The signal is a suppressor: it only emerges after the backbone +
skills remove the variance that masks it. SDA-M1's verdict was correct *for its
baseline*; the baseline changed. **New framework rule (added to the 2026 refit
checklist): rejected candidates are baseline-relative — re-screen the rejection
registry whenever the baseline stack materially changes.**

**Q2 — good vs bad variance: the decomposition does NOT beat the raw SD.**
Per-hitter attack-angle ~ pitch-height split (slope = adaptation, residual SD =
"inconsistency"): promotion bar shows champion raw SD +0.14/+0.42/+0.25/+0.22
(avg/babip/xba/xwoba) vs decomposition +0.08/+0.42/+0.21/+0.10; SDA's richer
multi-covariate constructs worse still (+0.04/+0.28/+0.17/+0.07). Both
components carry **positive** coefficients — more height-adaptation (mean slope
−9.7°/zone: steeper on low pitches) AND more residual dispersion both help,
because the "residual" still contains adaptation to location/velocity/pitch-type.
At n=538, every purification discards signal. The dispersion is adaptation,
not noise: reliability ladder agrees (aa_sd .88, slope .86, resid .82 — all skill-stable).

**Q3 — swing-side vs outcome-side: different things, opposite directions.**
corr(attack-angle SD, launch-angle SD) = **−0.40**: hitters who vary the swing
more produce *less* variable batted-ball launch — adaptation in, consistency
out, which is precisely the adjustability mechanism. Outcome-side la_sd is
half noise (y2y .51 vs .88 swing-side) and FAILS as a feature (−0.18 BABIP).
This also reconciles the variance model's cons_la_sd finding: low outcome
dispersion ⇔ high swing adaptation — same skill, viewed from the other end.

**Verdict: no Adjustability+ axis is built. The champion (raw
`attack_angle_std`, engine v2.1) DEFENDS the promotion bar** — the raw form is
the best available carrier of the skill at current sample. Re-pose the axis
question at the 2026 refit with the decomposition re-run at larger n.

## Addendum TAIL (2026-06-11): elite-tail correction — engine v2.2

Two surfaces tested (`pipeline/09_elite_tail.py`):

**A) Skill-layer tier carry (the handoff's 2.2× suggestion): REJECTED.**
Applying carry′ = 2.2 × PA/(PA+k) to top-decile-e2 hitters worsens elite-subset
next-wOBA RMSE in every fold (−1.5/−3.8/−6.1). Diagnosis: the variance model's
0.42 is *residual-on-residual* persistence; the skill estimate already
overshoots elites at the t+1 horizon (league drift + aging live there), so
amplifying the residual compounds the overshoot. The Skill/Luck display layer
stays as-is.

**B) Engine tail hinge (max(0, cur − seasonal P90)): PROMOTED for wOBA + OPS.**
Overall OOS RMSE improves (wOBA +0.06, OPS **+0.64**) AND the real compression
— OPS top-decile bias — drops **+17.4 → +13.6**. xwOBA hinge failed the bias
bar (−0.2 → −1.6) and is not promoted. Effect on 2027: Yordan wOBA .361 → .372,
Judge .353 → .354 — decompression lands on the true tail cases.

Engine = **v2.2**: v2.1 + hinge_woba, hinge_ops. σ(ops) ±.083.

## GO / NO-GO: **GO — engine v2.1 shipped** *(superseded: v2.2, see TAIL addendum)*

avg + xwoba gain `attack_angle_std`, bb_pct gains `zone_seen`; all other specs
unchanged; σ table updated (xwOBA ±.027, BB% ±.021, AVG ±.026). Approved
additions: 2. Rejected: 3. Architecture integrity preserved.
