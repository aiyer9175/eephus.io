# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Shared numeric constants: stabilization / shrinkage pseudo-counts plus the
replacement-wins baseline (audit findings F-05 / F-06, 2026-07-01).

One home with provenance, values byte-identical to the scattered literals they
replaced. This module imports NOTHING from the project: storage.py (imported
nearly everywhere) imports it, so it must sit at the very bottom of the import
graph.

The look-alike values are intentionally NOT unified (K_IP=50 vs
NEED_ERA_SHRINK_IP=45 both shrink an ERA, toward different targets on
different populations). Each was tuned where it lives, and changing any value
changes published numbers. Value unification is a review-queue item
(docs/audit-2026-07/AUDIT_FINDINGS.md, F-05), not a refactor.
"""

# ---- level-relative display indexes (storage.py export path) --------------- #
# Empirical-Bayes pseudo-counts for the PROSPX MiLB statline chips
# (ops_plus_level / era_minus_level / level_plus_pct): the raw stat is shrunk
# toward its LEVEL mean by sample size before indexing, so a 4-AB line no
# longer reads OPS+ 374 and a few-IP line no longer reads an extreme ERA-.
# Values set in the RPS+ calibration pass (2026-06-18, commit 9179d0f), sized
# to kill small-sample blowups while leaving full-season lines nearly
# untouched.

# OPS stabilization scale in AB: at 170 AB the displayed index is half stat,
# half level mean.
K_AB = 170.0

# ERA stabilization scale in IP: at 50 IP the displayed index is half stat,
# half level mean. The number is smaller than K_AB only because IP and AB are
# different denominations; both sit near half a season of everyday exposure.
K_IP = 50.0

# ---- PAL SP->RP need gate (pal_conversion.starter_need_score) -------------- #
# IP pseudo-count shrinking an MLB STARTER's season ERA toward the league
# starter mean (LG_SP_ERA, kept next to the gate in pal_conversion) before
# the conversion-need score. Added in the pre-Beta model-fix pass
# (2026-07-01, e2395a1, finding M4): raw ERA is the slowest-stabilizing
# pitching stat, and without the shrink a 30-40 IP unlucky ace scored ~100
# need and topped the demotion board. Deliberately NOT the same value as
# K_IP: K_IP steadies a MiLB display index against its level mean, while this
# gates a roster decision on the MLB starter pool, sized so a full-season
# struggler still clears the gate but a small-sample blip does not. Unifying
# the two would change published PAL boards (F-05 review queue).
NEED_ERA_SHRINK_IP = 45.0

# ---- college -> Single-A translation (college_translation.py) -------------- #
# Not a shrinkage constant, a unit conversion: league-average batters faced
# per 9 innings (about 4.2 per inning). Converts a Single-A pitcher's K/9 and
# BB/9 into the K% / BB% units the college TrackMan side carries, and only as
# a FALLBACK when the statline's stored BF-denominated rates are missing
# (the 2026-07-01 M12 de-bias made stored rates the preferred path).
BF_PER_9 = 38.0

# Slope-shrinkage pseudo-count for the matched-pair regression:
# slope = ols_slope * n / (n + SLOPE_SHRINK_K). Chosen in the CollegeSavant
# translation build (2026-06-20) so the strong n=77 hitter K% fit keeps most
# of its OLS slope while a ~30-pair cell is pulled hard toward pure
# regression-to-the-mean. Kept an int on purpose: it is written verbatim into
# data/college_translation_eval.json.
SLOPE_SHRINK_K = 20

# ---- team win roll-ups (proj_export.py / proj_backtest.py) ------------------ #
# bWAR replacement baseline for team roll-ups: the wins a team of pure
# replacement players banks before roster WAR is added. bWAR is calibrated so
# the league's players sum to ~1,000 WAR each season and a full season is
# 2,430 wins (30 teams x 162 games / 2), so (2430 - 1000) / 30 = 47.67,
# rounded to the B-Ref convention of 47.7 (equivalently a .294 replacement
# winning percentage x 162). Shared by the live Team Outlook export and the
# retro backtest that validates it. The FA module reads the same 47.7 from
# fa_config.yaml (replacement_wins), which stays config-driven by design.
REPLACEMENT_WINS = 47.7
