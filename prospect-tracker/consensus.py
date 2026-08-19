# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Consensus engine, v5 (forward-filled, Bayesian-shrunk).

Anchored to the FanGraphs scouting primer:
  https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/

Design (v5)
-----------
Sources that publish an explicit 20-80 FV grade are combined into a mean that
CAN be accuracy-weighted but today is not. Weights load from
data/source_weights.json (shrunk toward equal from the resolved-outcome
backtest) and default to 1.0, one equal vote. That file is currently EMPTY and
every source votes at 1.0: the previous FanGraphs 0.939 / MLB Pipeline 1.061
pair was reverted 2026-07-25 as unearned, because the forward-chained A/B
measured d_rho -0.0012 against an MDE95 of 0.0068, i.e. nothing to weight on.
The ship gate in source_backtest.py now demands a gain larger than the test can
resolve. (The same question was measured again at the TOOL level on 2026-07-31
and refused for a different reason, non-replication:
docs/efv-2026-07-30/TOOL_NORMALIZATION_VERDICT.md.) The cohort-conditioned
variant of the same question was tested 2026-08-09 and is also closed; the
weighting question is not re-narrated here, it lives in
data/source_cohort_accuracy.json.

FV-PUBLISHING SOURCES. Counted off `snapshots` on 2026-08-09; `rows` is snapshot
rows (not players), `fv` is the subset carrying an explicit FV.

  source                        rows      fv    first        last
  fangraphs                   24,503  24,501   2017-02-15   2026-08-02
  mlb_pipeline                18,978  18,440   2011-01-22   2026-08-09
  tjstats                      4,702   4,698   2026-01-22   2026-08-09
  baseballamerica              1,635   1,535   2023-02-15   2026-06-03
  espn                           252     252   2025-08-20   2026-05-22
  mlb_pipeline_international     246     246   2021-01-15   2026-08-09
  draft_signing                  138     138   2026-07-23   2026-08-09
  just_baseball                  126     126   2026-03-04   2026-06-04

BASEBALL AMERICA VOTES AS AN FV SOURCE. Not rank-only: 1,535 of its 1,635 rows
(93.9%) carry an FV over four February vintages (2023 through 2026, 383 to 385
rows each, distinct FV 30 through 70). Only the single 2026-06-03 list is
rank-only, 100 rows. This docstring asserted the opposite until 2026-08-09.

THE ATHLETIC IS NOT A SOURCE HERE, and never was: 0 rows, as are Keith Law and
Prospects Live. `SELECT DISTINCT source FROM snapshots` returns exactly eleven
values, the eight above plus three that publish no opinion:
performance_ingest (2,893 rows, a constant FV 35 auto-track anchor, see
CONSTANT_ANCHOR_SOURCES), auto_detect (2,504 rows, 0 with an FV) and
baseballamerica_statcast_by_age (41 rows, 0 with an FV).

Rank-only ROWS survive inside FV-publishing sources (538 mlb_pipeline, 100
baseballamerica, 4 tjstats). They contribute via rank -> implied-FV mapping ONLY
when a player has no explicit FV grades from any source; once at least one
source has graded the player, the FV mean wins and the ranks are used only for
the informational avg_rank field.

Forward-fill (v5)
-----------------
Real-world sources publish on different dates. To prevent a player whose
two grades arrive on different days from showing only the most recent
single source, each ConsensusPoint at date D uses the *latest known
snapshot from every source* up to D. New snapshots overwrite stale ones
from the same source; sources that have never graded the player simply
don't contribute.

Bayesian shrinkage (v5)
-----------------------
Low-information FVs get pulled toward the prospect-pool mean, with the
prior fading to zero as coverage approaches the maximum number of
FV-publishing sources:

    k_eff       = k * max(0, (N_full - n) / N_full)
    adjusted_fv = (n / (n + k_eff)) * raw_fv
                + (k_eff / (n + k_eff)) * mean_fv

  n      — number of sources contributing to raw_fv (explicit-FV count, or
           rank-only count when only rank-implied FVs are available)
  k      — tuning constant (default 2)
  N_full — source-count at which a player is "fully covered" and gets
           zero shrinkage (default 5: FG, ESPN, JB, TJ, MLB Pipeline)
  mean_fv— global mean of every player's latest pre-shrinkage raw FV

Weight on the raw value by n (with k=2, N_full=5):
   n=1 → 38%   n=2 → 63%   n=3 → 79%   n=4 → 91%   n=5 → 100% (no pull)

So an IFA-only Pipeline grade gets pulled hard, a 2-source prospect like
Asigen sees a moderate correction, and a five-source consensus like
Jesús Made keeps essentially its raw FV.

Per (player, date) we compute:

  a. avg_fv                       — simple mean of explicit FV grades
                                     from sources that published one
  b. avg_rank                     — simple mean of ordinal ranks
  c. rank_implied_fv              — mean of rank-converted FVs
  d. consensus_fv_pre_shrinkage   — avg_fv if any explicit FV present,
                                     otherwise rank_implied_fv
  e. consensus_fv_raw             — pre_shrinkage value pulled toward
                                     mean_fv per the Bayesian formula
  f. consensus_fv                 — rounded post-shrinkage value on the
                                     20-80 scale

Candlestick fields (fv_high / fv_low / fv_open / fv_close) ride on the
PlayerTimeseries object so the front-end can render a candle without
re-aggregating per-snapshot data.

Stock movement is "delta since the most recent prior update," not
"delta from first observation." A graduated player or a player with
only one update reads as "flat."
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, replace as _dc_replace
from datetime import date

from scrapers import Snapshot


# Bayesian-shrinkage defaults. k controls how fast the prior fades as more
# sources contribute; N_FULL is the source-count at which a player is
# considered "fully covered" and shrinkage decays to zero. N_FULL is
# intentionally < the number of FV-grading outlets (5) so a top prospect
# graded by 4 of the 5 majors still escapes the prior — shrinkage exists
# to discipline thinly-covered players (e.g. 2026 IFAs with only one
# source), not to penalize well-known names just because one outlet has
# only ranked, not FV-graded, them. See `_shrinkage_n` for how the count
# itself is determined.
# Lowered from 2.0 → 1.5 in 2026-05 to ease the 40-tier clustering. With
# k=2.0 a 1-source prospect got 38% weight on the raw FV; the prior
# (population mean ≈ 40) dominated and most weakly-covered prospects
# collapsed onto a 40 tier regardless of what the source actually said.
# At k=1.5 a 1-source FV gets ~45% raw weight; 2-source ~70% — moves
# the marginal cases off 40 without affecting well-covered prospects.
# INERT since 2026-05. These three drive apply_shrinkage / compute_prior_mean_fv,
# which build_timeseries no longer calls; they are defaults on dead keyword args.
# Changing them changes NOTHING on the board. The live knob is SINGLE_SOURCE_K below.
DEFAULT_SHRINKAGE_K = 1.5
DEFAULT_N_FULL = 4
FALLBACK_PRIOR_FV = 45.0

# v27 repair flags. Each is a one-line revert and each is exercised by the
# wave-2 lab (tools/consensus_gate_lab.py --wave2), which flips them to build
# the comparison arms. Gate doc: docs/efv-2026-08-07b/CONSENSUS_REPAIR.md.
#
# ORG_RANK_VALUE_DETECTOR -- split org positions from global ranks by their
#   arithmetic structure instead of by interval_label, which cannot express the
#   split because a FanGraphs board carries both under ONE label.
# ASOF_FV_INSTANCES — count a player's published-FV instances as of the point
#   being computed, not over their whole future history.
# DROPOFF_SHRINK_ENABLED — master switch for the (fv+30)/2 drop-off shrink,
#   which has never fired in production because its detector was matching a
#   slug that does not exist. Turning it on is a live grade change, so it is
#   kept separately revertible from the detector repair itself.
# Detector acceptance bars. A board that misses any of them keeps today's
# behaviour (every rank treated as global), which is the conservative
# direction. These are NOT in the lane plan; they are mine, and section 8 of
# the gate doc records what they were set from.
MIN_GLOBAL_PREFIX = 20          # a board with a tiny top block is not a board
MIN_PREFIX_COVERAGE = 0.95      # 1..G may have holes; a sparse "prefix" is not one
MIN_OFFSET_EXACT_FRAC = 0.90    # orgs whose first position is exactly g+1
MAX_OFFSET_UNDER = 1            # a position EARLIER than g+1 is a contradiction

ORG_RANK_VALUE_DETECTOR = True
ASOF_FV_INSTANCES = True
DROPOFF_SHRINK_ENABLED = False

# Single-source uncertainty pull-down — applied inside
# compute_consensus_point when exactly one source published an explicit
# FV. Bayesian shrinkage toward FV 35 with k=0.5:
#   adjusted = weight · raw + (1 − weight) · PRIOR, weight = 1 / (1 + K) = 2/3
# Higher raws get pulled harder (a 65 → 55, a 50 → 45). The prior sits
# at FV 35 deliberately: it's the "barely-a-prospect" floor — pulling
# toward it expresses "without corroboration we're not confident this
# is actually a real prospect-grade player". Multi-source consensus is
# completely untouched (weight = 1.0 in that branch).
SINGLE_SOURCE_PRIOR = 35.0
SINGLE_SOURCE_K = 0.5

# Adopt the cross-source grade-normalized consensus as the LIVE board FV
# (grade_normalization.build_remapper): each source's FV is quantile-mapped onto the
# FanGraphs scale BEFORE it enters the consensus mean, so a materially hot/cold
# grader (e.g. ESPN, MLB Pipeline in 2026) is de-biased. The PIPELINE entrypoints
# pass normalize=ADOPT_NORMALIZED_CONSENSUS to build_timeseries; unit tests call it
# with the default (normalize=False) so their exact consensus_fv fixtures stay
# valid. Flip to False to revert the board to the raw per-source mean. NOTE: this
# moves the live scale, so on the next full pipeline run the append-only history
# (metric_snapshots, farm_grade_history) gains a scale seam at the adoption date,
# and eFV (which reads consensus_fv_raw) settles over one run.
ADOPT_NORMALIZED_CONSENSUS = True

# As-of grade normalization. OFF, and it is off on purpose.
#
# The remapper's thin-cell fallback pools a (source, role, year) cell across ALL
# years including years later than the point being computed, so a 2021 grade is
# normalized partly off 2026 information. grade_normalization gained an
# as_of_year cap on 2026-08-09 (see that module's docstring for the full
# measurement); this flag is the only thing that would turn it on IN THIS FILE.
#
# FLIP CHECKLIST (call sites verified 2026-08-09b). The flag reaches exactly one
# construction, build_timeseries below. FIVE other places build the remapper
# DIRECTLY and would keep the uncapped basis, which is how the board and the
# analysis end up on two different normalizations:
#   surplus_backtest_real.py:133      build_remapper(aliases=_cons.SOURCE_ALIASES)
#   tools/consensus_recency_lab.py:319
#   tools/efv_gradenorm_basis_lab.py:658
#   tools/ba_consensus_lab.py:139
#   tools/consensus_gate_lab.py:660
# surplus_backtest_real is the binding one: it prices the backtest prospect_surplus
# is validated against, so flipping here alone puts the SERVED BOARD and the SURPLUS
# BACKTEST on two different normalization bases. tools/consensus_gate_lab.py also
# carries its own re-implementation of the remapper (:73-139, _paired_dists_from at
# :104 and build_remapper_asof at :122) that mirrors the uncapped pooling cell for
# cell and needs the same cap.
# All five take as_of_year, so the flip is: pass the cutoff into all six, then
# rebuild. grade_normalization's three analysis views (quantile_map, drift_row,
# normalized_consensus) take as_of_year too, and any caller of those that is meant
# to describe the served scale has to pass it as well.
#
# It is a BASIS CHANGE, not a no-op. consensus_fv_raw is simultaneously eFV's
# dominant feature and eFV's baseline, so anything that moves it must be gated
# on its own. Measured 2026-08-09 by rebuilding the timeseries of the 98
# affected players under both remappers: 183 of their 1,401 historical
# consensus points move, mean +1.3407 FV (max +4.66), and the LATEST (served)
# point moves for 11 players, mean +0.8927 FV, flipping the displayed
# consensus_fv on 6 of them. All 11 are 2021-2023 MLB Pipeline International
# hitters, which is the only cohort the cap reaches.
# RE-MEASURED 2026-08-09b on the full 56,018-snapshot pool (9,721 players, both
# remappers): 5 served consensus_fv values flip, not 6. The corpus moved, the cap
# did not. Treat the size of this basis change as a per-vintage measurement, not a
# constant, and re-measure before flipping.
#
# STALE CLAUSE REMOVED 2026-08-14, and the correction matters more than the
# removal. This block used to end "Pre-2017 is exempt inside grade_normalization
# and is a separate, larger question (3,478 units, ~+3.9 FV)". That exemption was
# REMOVED on 2026-08-14: build_remapper used to hand pre-reference cells a cap of
# None, which made the era floor landed on 2026-08-13 unreachable for exactly the
# cells it was built for, so the flip would have been a silent no-op there. See
# docs/efv-2026-08-13/C4_REACHABILITY_DEFECT.md.
#
# So a reader of the old text would have planned a flip believing the pre-2017
# block does not move. IT NOW MOVES, all 3,478 units of it, and DOWNWARD rather
# than up. Re-measured 2026-08-14 on the live corpus, the two populations move in
# OPPOSITE directions and must never be netted:
#
#   pre-2017 (era floor):   3,478 served units, unit-weighted mean  -0.2396 FV
#   2017+    (as-of cap):      99 served units, unit-weighted mean  +2.1004 FV
#
# The dense grid reports 2,824 of 6,048 probe cells moving with a tail out to
# +7.02 FV, and that headline is misleading on its own: 128 of the 143 moved
# (source, role, year) cells serve ZERO units. They exist only because the
# uncapped pool reached forward into 2026 for sources with no rows that early
# (baseballamerica starts 2023, espn 2025, just_baseball and tjstats 2026). Under
# the cap they lose every pair and drop to raw, which IS the leak closing, on
# cells nobody is graded by. Quote the 3,577 served units, never the 2,824 cells.
#
# When it is on, build_timeseries caps at the newest snapshot year in the pool,
# which yields a per-cell as-of table (cap = each cell's own year). The cutoff is
# taken from the data, never from the clock, so a rebuild is reproducible.
GRADE_NORM_AS_OF = True


def grade_norm_cutoff(snapshots=None) -> int | None:
    """The as-of cutoff for the grade-normalization remapper, or None when the flag
    is off. THE SINGLE POINT OF TRUTH for that derivation.

    It exists because the flip checklist above lists five other places that build
    the remapper directly, and the failure mode it warns about is precisely that
    one of them keeps the old basis and puts the served board and the analysis on
    two different normalizations. Five copies of `max(snapshot year)` guarded by
    five copies of an `if` is how that happens. Callers ask this function instead,
    so the flag reaches every site by construction and a future change to the
    derivation cannot land in some of them and not others.

    Derived from the DATA, never from the clock: the cutoff is the newest snapshot
    year in the pool being normalized, so a rebuild of a fixed corpus is
    reproducible and a rebuild that happens to run after midnight on New Year's Eve
    does not silently re-base every grade.

    Pass `snapshots=None` to read the newest year straight from the DB. The lab
    scripts each load their pool differently and several do not hold a Snapshot
    list at the point they build the remapper, so without this they would each
    hand-roll the query, which is the duplication this function exists to prevent.
    """
    if not GRADE_NORM_AS_OF:
        return None
    if snapshots is None:
        try:
            import storage as _st
            with _st.connect() as con:
                row = con.execute(
                    "SELECT MAX(substr(snapshot_date,1,4)) FROM snapshots "
                    "WHERE snapshot_date IS NOT NULL").fetchone()
            return int(row[0]) if row and row[0] and str(row[0]).isdigit() else None
        except Exception:
            return None
    yrs = [int(str(s.snapshot_date)[:4]) for s in snapshots
           if getattr(s, "snapshot_date", None) and str(s.snapshot_date)[:4].isdigit()]
    return max(yrs) if yrs else None

# Source aliases — outlets that publish multiple separate lists but
# count as one editorial voice. MLB Pipeline splits its yearly coverage
# into the Top 100 (`mlb_pipeline`) and the International Top 50
# (`mlb_pipeline_international`); a 16-year-old who appears on both
# lists would otherwise show up as "2 sources" and dodge the single-
# source pull-down. Keys = source string emitted by the scraper, values
# = the canonical source name we collapse to for consensus + per_source.
SOURCE_ALIASES = {
    "mlb_pipeline_international": "mlb_pipeline",
}

PLAYER_KEY_ALIASES = {
    "josh_kurodagrauer": {
        "player_key": "joshua_kurodagrauer",
        "player_name": "Joshua Kuroda-Grauer",
    },
    # v9 — FanGraphs published this player as "Yeremi Cabrera" in 2024,
    # then switched to the "Yeremy" spelling starting Feb 2025. MLB
    # Pipeline also uses "Yeremy". Same player (same DOB / Nats CF/OF
    # via TEX→WSN), just a spelling change that fragmented the history
    # into two cards (one stale-inactive on TEX, one active on WSN).
    # Collapse to the current "Yeremy" key.
    "yeremi_cabrera": {
        "player_key": "yeremy_cabrera",
        "player_name": "Yeremy Cabrera",
    },
    "george_lombard": {
        "player_key": "george_lombard_jr",
        "player_name": "George Lombard Jr.",
    },
    "leonardo_bernal": {
        "player_key": "leo_bernal",
        "player_name": "Leo Bernal",
    },
    # 2026-08-04 - the same shape as yeremi_cabrera above, and the ONLY
    # remaining critical_active identity collision. The draft-signing feed
    # spells him "Jack Natili" (that is the wording of the 2026-07-20 Rockies
    # transaction), FanGraphs and MLBAM spell him "Jackson", and the two
    # spellings fragmented one human into two active cards. Same DOB
    # 2005-03-10, same club, same position, same draft pick (2026, round 3,
    # pick 76). He was reaching the SERVED board TWICE, at ranks 155 and 320
    # with grades 45 and 42, and his surplus was double counted at $16.7M plus
    # $3.8M.
    #
    # Fixed HERE rather than by re-keying the database on purpose. This table
    # canonicalises at READ time (_canonicalize_player_snapshot), so the merge
    # happens every rebuild and is undone by deleting these four lines. The
    # alternative - a DB key remap - cannot be cleanly undone, and the survey
    # in docs/identity-2026-08-04/JACK_NATILI_REMAP_PROPOSAL.md found it would
    # also have thrown on 23 of 30 rows, because both keys hold snapshots on
    # the same dates under PK(player_key, snapshot_date).
    "jack_natili": {
        "player_key": "jackson_natili",
        "player_name": "Jackson Natili",
    },
    # 2026-08-10 - four live spelling/suffix splits found by the BA midseason
    # verification sweep. Each pair shares an identical stored birth_date and
    # an identical org, and each is one human whose history fragmented across
    # two keys when a source changed the printed form of the name.
    #
    # The White Sox SS, b. 2004-10-20. FanGraphs and BA print "William
    # Bergolla" while MLB Pipeline prints "William Bergolla Jr."; both keys
    # were live in August 2026. The suffixed key is canonical per the
    # eric_booth_jr / george_lombard_jr convention. NOTE the 2026-07 incident
    # ledger records a DIFFERENT bergolla failure (resolution to William
    # Contreras); this entry is the same human on both sides, verified on
    # DOB + org + club position.
    "william_bergolla": {
        "player_key": "william_bergolla_jr",
        "player_name": "William Bergolla Jr.",
    },
    # The Phillies RHP reliever, b. 2002-09-19. FanGraphs itself moved from
    # "Wen Hui Pan" (last row 2024-08-01) to "Wen-Hui Pan" (2026-08-02), the
    # same shape as yeremi_cabrera above. The BA 2026-08-01 row landed on the
    # stale key and folds in here at read time.
    "wen_hui_pan": {
        "player_key": "wenhui_pan",
        "player_name": "Wen-Hui Pan",
    },
    # The Mets LHP, b. 2002-01-17. Current FanGraphs and Pipeline print
    # "Zac"; the stale key carries the "Zach" form plus the BA 2026-08-01 row.
    "zach_thornton": {
        "player_key": "zac_thornton",
        "player_name": "Zac Thornton",
    },
    # The Rangers INF/OF, b. 2003-02-06. Current FanGraphs and Pipeline print
    # "Cam"; the stale key carries the "Cameron" form plus the BA row.
    "cameron_cauley": {
        "player_key": "cam_cauley",
        "player_name": "Cam Cauley",
    },
    # The Orioles 3B, b. 2007-02-10. One human in two spacings: "Jaiden
    # Lo Re" carries mlbam 828318, the statline, and four live sources
    # (Pipeline 2026-08-09, FanGraphs 2026-08-02, BA 2026-08-01); "Jaiden
    # LoRe" is a single stale 2025-07-31 FanGraphs row.
    "jaiden_lore": {
        "player_key": "jaiden_lo_re",
        "player_name": "Jaiden Lo Re",
    },
    # The Dodgers LHP, b. 2004-02-06. BOTH keys bind mlbam 702539, which
    # settles one-human beyond argument. Pipeline and BA print "Zach" and
    # hold the statline; FanGraphs prints "Zachary". The Pipeline form wins
    # incumbency (statline plus two current sources).
    "zachary_root": {
        "player_key": "zach_root",
        "player_name": "Zach Root",
    },

    # 2026-08-14 - two keys per human, surfaced as CLASS C of the MLB Pipeline
    # vintage audit (docs/efv-2026-08-13/PIPELINE_VINTAGE_CONTAMINATION.md).
    # They presented as "rows > distinct ranks" on eight labels, the same
    # symptom as the accretion and the wrong-list write that audit also found,
    # and they are deliberately NOT repaired the same way: deleting a row fixes
    # one label, an alias fixes every consumer that keys on player_key.
    #
    # The Twins 3B/2B/1B. Both keys carry the SAME rank in all seven labels
    # they share (2017-2022 Twins Top 30 plus the 2022 Top 100), which is the
    # signature of one human printed two ways rather than two players.
    # "jose_miranda" is incumbent on every count: 18 snapshots against 8, three
    # sources including FanGraphs against two, and the clean printed form.
    # "Jose F Miranda" is Pipeline carrying a middle initial.
    "jose_f_miranda": {
        "player_key": "jose_miranda",
        "player_name": "Jose Miranda",
    },
    # The Athletics RHP. NOTE the direction is the OPPOSITE of the pair above,
    # and it is worth stating why rather than letting it read as a slip. Here
    # the SUFFIXED key is the live one: "lou_trivino_iii" holds the
    # performance_ingest statline and runs current to 2026-01-01 with a
    # resolved position, while "lou_trivino" is a single positionless
    # mlb_pipeline row from the 2018 Athletics Top 30. Incumbency follows the
    # statline, per the zachary_root and jaiden_lore entries above, not the
    # shorter spelling.
    "lou_trivino": {
        "player_key": "lou_trivino_iii",
        "player_name": "Lou Trivino III",
    },

    # 2026-08-09 - the Baseball America 2026 MIDSEASON org Top 30 drop, 30
    # boards, 900 rows. BA prints the SHORT form of a name where this database
    # holds the suffixed or fuller form, so 15 correctly-parsed rows for players
    # the database already knows would otherwise have been reported unresolved
    # and never ingested.
    #
    # ADMISSION BAR, applied to all 18 unresolved rows and failed by 3 of them:
    # the board org must match, AND at least one signal independent of the name
    # must agree. In practice every entry below cleared more than that. The
    # physicals are FanGraphs' own bats/throws/height/weight off tools._extras,
    # published by a different outlet than BA and never keyed on either spelling,
    # so they are a genuinely independent check rather than a restatement.
    #
    # BA's "Age" is a SEASON age, measured here against a ~2026-06-01 reference:
    # over the 829 rows of this drop that resolved AND carry a DB birth_date, it
    # is exact on 787 (94.93%) at that reference and on only 644 (77.68%) at the
    # board's own 2026-08-01 date. So an age one year under the board-date
    # arithmetic is the NORM, not a red flag, and it is read that way below.
    #
    # THE THREE THAT DID NOT CLEAR THE BAR ARE DELIBERATELY ABSENT, and the
    # nearest miss is the reason the bar exists: BA's Pirates rank 7 "Triston
    # Gray" (3B/1B, age 22, R-R, Fresno State) is NOT the database's
    # `tristan_gray`, who is a 30-year-old L-R 1B last seen at TBR in 2023. The
    # spelling is one letter away and everything else disagrees. BA's own capsule
    # even says "Gray, whose first name is Triston". Michael Addari (HOU 25) and
    # Kyle Jones (MIL 23, a 2026 third-rounder) have no candidate in `players` at
    # all. All three stay unresolved.
    "eric_booth": {
        # BAL = BAL. FanGraphs has him L-L at 6'0", BA has L-L at 6'0". BA's own
        # prose settles the suffix twice: "Booth Jr. is a lefthanded hitter", and
        # the same capsule names his father, "Eric Booth Sr. was a running back".
        "player_key": "eric_booth_jr",
        "player_name": "Eric Booth Jr.",
    },
    "enrique_bradfield": {
        # BAL = BAL, OF = OF, L-L = L-L, age 24 = 24. Vanderbilt, signed by the
        # Orioles, on both sides.
        "player_key": "enrique_bradfield_jr",
        "player_name": "Enrique Bradfield Jr.",
    },
    "james_tibbs": {
        # 41 of his 44 stored snapshots carry LAD, matching the board org; the
        # `players.org` on this key reads "Okla. City", the Dodgers' Triple-A
        # affiliate, which is a separate pre-existing wart and not a contradiction.
        # L-L at 6'0" on both sides. BA settles the suffix itself: its GIANTS
        # board writes "After selecting James Tibbs III in the first round" about
        # the same 2024 pick the Dodgers capsule describes.
        "player_key": "james_tibbs_iii",
        "player_name": "James Tibbs III",
    },
    "eli_serrano": {
        # NYM = NYM, OF = OF, L-L = L-L, 6'5" = 6'5", age 23 = 23.
        "player_key": "eli_serrano_iii",
        "player_name": "Eli Serrano III",
    },
    "miguel_sime": {
        # WSN = WSN, RHP = RHP, R-R and 235 lb on both sides. BA settles the
        # suffix itself: its own Nationals board names "Miguel Sime Jr." inside
        # another capsule's account of the draft class.
        "player_key": "miguel_sime_jr",
        "player_name": "Miguel Sime Jr.",
    },
    "kamden_durnin": {
        # HOU = HOU, SS = SS, R-R = R-R, 6'1" and 200 lb match exactly, age
        # 21 = 21. Kam is the short form of Kamden.
        "player_key": "kam_durnin",
        "player_name": "Kam Durnin",
    },
    "danny_thompson": {
        # TOR = TOR, RHP = RHP, age 23 = 23. The decisive signal is prose from a
        # DIFFERENT outlet: MLB Pipeline's stored report for `danny_thompson_jr`
        # says "Division III North Carolina Wesleyan and transferred to UNC
        # Greensboro", and BA's capsule says "two seasons with D-III North
        # Carolina Wesleyan before transferring to UNC Greensboro".
        "player_key": "danny_thompson_jr",
        "player_name": "Danny Thompson Jr.",
    },
    "nicolas_perez": {
        # LAD = LAD, 2B/3B = 2B/3B, R-R = R-R, 175 lb = 175 lb, age 21 = 21.
        "player_key": "nico_perez",
        "player_name": "Nico Perez",
    },
    "camden_kozeal": {
        # MIA = MIA, age 21 = 21, and L-R on both sides, an uncommon pairing.
        # BA lists SS against the database's 2B, the same middle infield.
        "player_key": "cam_kozeal",
        "player_name": "Cam Kozeal",
    },
    "tyler_head": {
        # BAL = BAL, L-L = L-L, 6'3" and 205 lb match exactly, and BA ranks him
        # 9th in an org where FanGraphs ranks Ty Head 11th and 13th. He is the
        # only Head in the Baltimore system.
        # DISCLOSED DISCREPANCY, the only one in this batch: BA prints age 20
        # against a stored DOB of 2005-05-25, which is 21 even at the ~June
        # reference. That is a BA age error of one year, inside the 32 of 829
        # rows that miss by one at that reference. Every other signal is exact,
        # so the row is admitted and the discrepancy is recorded rather than
        # smoothed over.
        "player_key": "ty_head",
        "player_name": "Ty Head",
    },
    "kevin_roberts": {
        # BAL = BAL, R-R = R-R, 6'5" and 220 lb match exactly, age 17 = 17 at
        # BA's reference. BA lists OF against the database's 1B.
        "player_key": "kevin_roberts_jr",
        "player_name": "Kevin Roberts Jr.",
    },
    "gabriel_rincones": {
        # PHI = PHI, L-R = L-R, 6'3" and 225 lb match exactly, age 25 = 25.
        # Florida Atlantic and the 2022 draft on both sides.
        "player_key": "gabriel_rincones_jr",
        "player_name": "Gabriel Rincones Jr.",
    },
    "charles_king": {
        # PHI = PHI, age 28 = 28 against a stored DOB of 1998-01-06, and P
        # against BA's RHP. He is the ONLY King in the Philadelphia system, and
        # Chuck is the standard short form of Charles. This is the thinnest entry
        # here: the key holds a single snapshot, from performance_ingest, with no
        # physicals to check, so it rests on org plus age plus role.
        "player_key": "chuck_king",
        "player_name": "Chuck King",
    },
    "rafael_flores": {
        # PIT = PIT, C/1B = C/1B, R-R = R-R, age 25 = 25. His stored history
        # carries 3 NYY snapshots before 7 PIT ones, matching BA's account that
        # the Yankees signed him undrafted out of junior college.
        "player_key": "rafael_flores_jr",
        "player_name": "Rafael Flores Jr.",
    },
    "leonardo_balcazar": {
        # CIN = CIN, R-R = R-R, 190 lb = 190 lb, age 21 = 21. BA lists 3B against
        # the database's SS/2B, the same infield.
        "player_key": "leo_balcazar",
        "player_name": "Leo Balcazar",
    },
    "lamar_king": {
        # SDP = SDP, catcher on both sides, R-R = R-R, 6'3" and 215 lb match
        # exactly, age 22 = 22. BA settles the suffix in prose without printing
        # it: "the son of a former NFL defensive end of the same name". He is the
        # only King in the San Diego system other than Michael King, an RHP.
        #
        # This row only became visible once the unpopulated-header carve-out let
        # the Padres board parse at all. It is the 19th unresolved name of a drop
        # whose first pass reported 18, which is worth stating: a refused board
        # hides its identity work as well as its grades.
        "player_key": "lamar_king_jr",
        "player_name": "Lamar King Jr.",
    },

    # 2026-08-19 - the C7 name-variant residue batch, routed by
    # tools/repair_identity_residue_2026_08_19.py. Each pair shares an
    # identical stored (birth_date, org, side) and NO pair carries the same
    # source on the same date on both keys (one list cannot rank one human
    # twice; the script verifies both bars before calling a route safe).
    # Canonical key = the member holding the MLBAM photo binding and the
    # fresher snapshot history. dom_keegan / dominic_keegan is deliberately
    # ABSENT: the dom_keegan key's own 2026 snapshots flip org BAL/TBR
    # inside one cycle, so it may itself hold two humans and stays open.
    "bj_murray_jr": {
        # The Cubs 3B, b. 2000-01-05. The bare key binds 681230 and runs
        # current (FG 2026 + Pipeline 2026-08-19); the suffixed key is the
        # FG 2024-2025 form.
        "player_key": "bj_murray",
        "player_name": "BJ Murray",
    },
    "ben_cowles": {
        # The Cubs INF, b. 2000-02-15. "Benjamin" binds 701496 and holds
        # FG + BA; "Ben" is a single Pipeline 2025-01-22 row.
        "player_key": "benjamin_cowles",
        "player_name": "Benjamin Cowles",
    },
    "javi_vaz": {
        # The Royals 2B, b. 2000-09-22. "Javier" binds 805834 and holds
        # eight FG/BA rows; "Javi" is the Pipeline 2024-2025 form.
        "player_key": "javier_vaz",
        "player_name": "Javier Vaz",
    },
    "zach_thornton__noid": {
        # The __noid twin of the zach_thornton key routed 2026-08-10; one
        # stale FG 2023-08-01 row. Same human, the Mets LHP b. 2002-01-17.
        "player_key": "zac_thornton",
        "player_name": "Zac Thornton",
    },
    "alex_santos": {
        # The Astros RHP, b. 2002-02-10. The suffixed key binds 691012 and
        # runs 2021-2025; the bare key is the FG 2020-2021 form.
        "player_key": "alex_santos_ii",
        "player_name": "Alex Santos II",
    },
    "jay_allen": {
        # The Reds CF, b. 2002-11-22. The suffixed key binds 695481 and
        # runs current to 2026-08-19; the bare key is the 2021-2023 form.
        "player_key": "jay_allen_ii",
        "player_name": "Jay Allen II",
    },
    "lonnie_jr_white": {
        # The Pirates OF, b. 2002-12-31. The stale key is a comma-mangled
        # parse ("Lonnie, Jr. White") of the 2021-2022 FG rows.
        "player_key": "lonnie_white_jr",
        "player_name": "Lonnie White Jr.",
    },
    "jared_jones__sa3034881": {
        # The Pirates 1B, b. 2003-08-01, LSU. The CollegeSavant interim key
        # holds his FG 2025-07-31 row; his own mlbam key binds 702262. The
        # OTHER Jared Jones keys (683003) are untouched.
        "player_key": "jared_jones_702262",
        "player_name": "Jared Jones",
    },
    "dennis_colleran": {
        # The Royals RHP, b. 2003-08-20. The suffixed key binds 701207 and
        # runs current (FG 2026 + Pipeline 2026-08-12).
        "player_key": "dennis_colleran_jr",
        "player_name": "Dennis Colleran Jr.",
    },
    "dennis_colleran__noid": {
        # The same human's __noid fork, a single FG 2024-08-01 row.
        "player_key": "dennis_colleran_jr",
        "player_name": "Dennis Colleran Jr.",
    },
    "leonardo_bernal__noid": {
        # The __noid twin of the leonardo_bernal route above; one stale FG
        # 2021-02-26 row. The Cardinals C, b. 2004-02-13.
        "player_key": "leo_bernal",
        "player_name": "Leo Bernal",
    },
    "junior_garcia_815010": {
        # The Braves OF, b. 2005-07-13. The ingest forked this key while
        # the bare slug was mis-bound to mlbam 642371 (a 2012 HOU IFA LHP,
        # another human); the same repair moved 642371's rows to
        # junior_garcia_642371 and re-bound 815010, the OF's own id, to the
        # bare key. This entry folds the fork back onto his board history.
        "player_key": "junior_garcia",
        "player_name": "Junior Garcia",
    },
}

CANONICAL_PLAYER_NAMES = {
    alias["player_key"]: alias["player_name"]
    for alias in PLAYER_KEY_ALIASES.values()
    if alias.get("player_key") and alias.get("player_name")
}


def _canonicalize_player_snapshot(s: Snapshot) -> Snapshot:
    alias = PLAYER_KEY_ALIASES.get(s.player_key)
    if not alias:
        return s
    return _dc_replace(
        s,
        player_key=alias["player_key"],
        player_name=alias.get("player_name") or s.player_name,
    )


def _canonical_player_name(player_key: str, fallback: str) -> str:
    return CANONICAL_PLAYER_NAMES.get(player_key) or fallback


def _dedupe_source_aliases(day_snaps: list[Snapshot]) -> list[Snapshot]:
    """Collapse multi-list outlets (e.g. MLB Pipeline Top 100 + Pipeline
    International) into a single canonical source per outlet.

    When the player appears on BOTH lists, we keep the canonical one
    (Pipeline Top 100) and drop the alias (Pipeline International) so
    the aggregator doesn't count them twice. When the player only
    appears on the alias list, we relabel it to the canonical source
    name so per_source / avg_fv_n / sources_contributing reflect "one
    Pipeline grade" rather than "one Pipeline International grade".
    """
    if not day_snaps or not SOURCE_ALIASES:
        return day_snaps
    canonical_present = {s.source for s in day_snaps}
    out: list[Snapshot] = []
    for s in day_snaps:
        target = SOURCE_ALIASES.get(s.source)
        if target is None:
            out.append(s)
            continue
        if target in canonical_present:
            # Canonical outlet's row exists — drop the alias entirely.
            continue
        # Canonical outlet missing — keep the alias but relabel it so
        # downstream code treats it as the canonical source.
        out.append(_dc_replace(s, source=target))
    return out


def _alias_grade_sources(day_snaps: list[Snapshot]) -> dict:
    """{(player_key, canonical_source): originating_alias_source} for exactly the
    rows _dedupe_source_aliases RELABELS (alias present, canonical absent).

    Why this exists (2026-07-25). _dedupe_source_aliases runs FIRST, so by the time
    grade normalization is applied below it only ever sees `mlb_pipeline` and the
    (mlb_pipeline_international, *, year) cells of the remapper are unreachable by
    construction. Collapsing to one editorial VOICE is right for vote counting; it
    is wrong for SCALE. Measured on the same players in the same cycle, Pipeline's
    International Top 50 runs +7.279 FV [+6.438, +8.075] hotter than that outlet's
    own main lists (n 147), so an intl-only prospect was being de-biased with the
    main list's -3.70 offset instead of the intl list's -11.89: a ~8 FV
    under-correction landing entirely on IFA-only prospects. Symptom on the live
    board: in the 2026 cycle the intl-ONLY cohort (the players who did NOT make an
    org top-30) was served +2.18 FV ABOVE the cohort that did, from the same
    outlet's grades. This map re-attaches the originating list for normalization
    only; vote counting, per_source and the single-source pull are untouched."""
    if not day_snaps or not SOURCE_ALIASES:
        return {}
    present = {s.source for s in day_snaps}
    out: dict = {}
    for s in day_snaps:
        target = SOURCE_ALIASES.get(s.source)
        if target is None or target in present:
            continue
        out[(s.player_key, target)] = s.source
    return out


# ---------------------------------------------------------------------------
# Snap helper — consensus FV is always a whole number on the 20-80 scale.
# ---------------------------------------------------------------------------
# Sources may publish "+" tiers (e.g. "55+" → 57.5 on ingest, see
# scrapers._parse_fv), but once aggregated we round to the nearest whole
# integer. An average of 58.75 becomes 59, not "60+".

def snap_to_grade(raw_fv: float) -> tuple[float, str]:
    """Ceiling-round a raw averaged FV to a whole number on the 20-80 scale.

    User preference is "hard round up": 50.2 reads as 51, not 50. FV
    grades are conventionally integers and a fractional reading
    shouldn't suppress to the lower tier when displayed.
    """
    import math
    raw_fv = max(20.0, min(80.0, raw_fv))
    rounded = int(math.ceil(raw_fv))
    return float(rounded), str(rounded)


# ---------------------------------------------------------------------------
# Rank -> implied FV
# ---------------------------------------------------------------------------

def implied_fv_from_rank(rank: int | None) -> float | None:
    if rank is None:
        return None
    if rank == 1:
        return 70.0
    if rank <= 15:
        return 60.0
    if rank <= 40:
        return 55.0
    if rank <= 110:
        return 50.0
    if rank <= 200:
        return 45.0
    return 40.0


# v18 — Match human-readable org-list interval labels like
# "MLB Pipeline 2021 Nationals Top 30". The `\b` word-boundary +
# end-of-string anchor lets "Top 30" / "Top 25" / "Top 20" / "Top 10"
# match without false-positives on "Top 100" / "Top 200" / "Top 300".
#
# DO NOT WIDEN THIS. The narrowness is deliberate and is relied on as a
# bad-paste tripwire at baseballamerica_csv.py:604-625; widening the digit
# alternation to a generic 2-digit form breaks
# test_baseballamerica_csv.py::test_a_board_whose_size_the_guard_does_not_accept_is_refused_loudly,
# which is parametrized over n = 3/29/31/100. The org/global split that this
# regex CANNOT see is handled at the VALUE level instead, by
# _org_ranked_snapshot_keys below.
_ORG_LIST_LABEL_RE = re.compile(r"\bTop\s+(?:10|20|25|30)\b\s*$")

# v27 -- Org-list slug extraction for the drop-off detector. Two label formats
# exist in the corpus and only the LEGACY one was ever matched (see
# _dropped_off_pairs). The human-readable grammar is
# "<source> <yyyy> <org> Top <n>". The org token is BOUNDED to the 30 real club
# nicknames rather than to the Top-N suffix, for two reasons:
#   * an unbounded org token classifies "JustBaseball 2026 Midseason Top 100"
#     as org "Midseason", which is harmless only until a second midseason list
#     lands and the two get diffed against each other, and
#   * two clubs publish a "Top 50" org list, so bounding the SUFFIX to
#     {10,20,25,30} would silently drop real org lists.
_CLUB_NICKNAMES = frozenset({
    "Angels", "Astros", "Athletics", "Blue Jays", "Braves", "Brewers",
    "Cardinals", "Cubs", "Diamondbacks", "Dodgers", "Giants", "Guardians",
    "Mariners", "Marlins", "Mets", "Nationals", "Orioles", "Padres",
    "Phillies", "Pirates", "Rangers", "Rays", "Red Sox", "Reds", "Rockies",
    "Royals", "Tigers", "Twins", "White Sox", "Yankees",
})
_ORG_LABEL_HUMAN_RE = re.compile(
    r"^(?P<src>.*?)\s+(?P<yr>\d{4})\s+(?P<org>.+?)\s+Top\s+(?P<n>\d+)$"
)


def org_slug_from_label(label: str | None) -> str | None:
    """Return the org slug for a team-specific list label, else None.

    Accepts the legacy internal slug ("<source>_<year>_org_<slug>") and the
    human-readable grammar with a bounded club nickname. Anything else,
    including a global Top 100 and a non-club token like "Midseason", is None.
    """
    if not label:
        return None
    if "_org_" in label:
        try:
            return label.split("_org_", 1)[1]
        except IndexError:
            return None
    m = _ORG_LABEL_HUMAN_RE.match(label)
    if m is None:
        return None
    org = m.group("org").strip()
    return org if org in _CLUB_NICKNAMES else None


# ---------------------------------------------------------------------------
# v27 -- VALUE-LEVEL org/global rank split.
#
# The problem the label guard structurally cannot solve. A FanGraphs board
# stores TWO DIFFERENT QUANTITIES in one `rank` column under ONE interval_label
# (e.g. "2026updated" on 2026-08-02 carries 1,384 ranked rows). The board is a
# set of per-org Top-N lists; for the players in an org who ALSO make the global
# board, FanGraphs prints the GLOBAL rank in place of that player's org
# position. So on a single label, rank 1 means "best prospect in baseball" for
# one row and "best prospect in Arizona" for another.
#
# The generating rule leaves two independent fingerprints that have to agree:
#
#   1. The global rows are a COMPLETE PREFIX. Their ranks are exactly
#      {1, ..., G}, each value once, board-wide.
#   2. The org rows are OFFSET BY the org's own global count. If an org has g
#      globally-ranked players, its own positions start at g + 1, because those
#      g players occupy org slots 1..g and are printed at their global rank
#      instead. Checked per org, on every org that has any org rows.
#
# The split is carried by FV: the global prefix is the top of the board by FV,
# so the detector searches the board's own FV values for the threshold where
# BOTH fingerprints hold, and prefers the threshold that leaves the MOST rows
# classified global, which is the least aggressive, closest-to-unrepaired
# answer. If no threshold satisfies both, the board falls back to "everything
# is global", which is the pre-v27 served behaviour.
#
# NOTE ON A REJECTED SIMPLER RULE. The obvious version of fingerprint 2 is
# "inside an org the positions run g+1 .. n and the two kinds of value tile
# 1..n exactly once". That is what three hand-read orgs (MIL, ARI, BAL) look
# like and it is WRONG on the full board: real org lists have holes (PHI is
# missing position 36) and can run past n (SEA carries a position 41 in a
# 31-row org). Seven of thirty orgs fail it. Only the START offset is reliable.
#
# This reads `rank`, `org` and `fv`. It never reads interval_label, so it
# composes with the label guard instead of replacing it.
# ---------------------------------------------------------------------------

def classify_board_org_ranks(rows: list[tuple]) -> tuple[set, dict]:
    """Split one board's ranked rows into org positions and global ranks.

    `rows` is a list of (row_id, org, rank, fv) for a single
    (source, interval_label, snapshot_date) board. Returns
    (set_of_row_ids_that_are_ORG_positions, diagnostics).
    """
    diag = {
        "n_rows": len(rows), "n_orgs": 0, "eligible": False, "validated": False,
        "n_org_rows": 0, "n_global_rows": 0, "global_prefix_G": None,
        "prefix_coverage": None, "offset_orgs_checked": 0,
        "offset_exact_frac": None, "offset_worst_under": 0, "reason": "",
    }
    by_org: dict[str, list[tuple]] = defaultdict(list)
    for row in rows:
        by_org[row[1]].append(row)
    diag["n_orgs"] = len(by_org)
    diag["n_null_fv"] = sum(1 for r in rows if r[3] is None)
    if len(by_org) < 2:
        diag["reason"] = "fewer than 2 orgs"
        return set(), diag

    # Step 1 — eligibility. A rank value carried by two DISTINCT orgs is
    # impossible on a single global list, so it is the board-level tell.
    orgs_per_rank: dict[int, set] = defaultdict(set)
    for _rid, org, rank, _fv in rows:
        orgs_per_rank[rank].add(org)
    if not any(len(v) > 1 for v in orgs_per_rank.values()):
        diag["reason"] = "no rank value shared across orgs"
        return set(), diag
    diag["eligible"] = True

    # Step 2 — the global prefix runs 1..G. G is the largest rank on the board:
    # no org's own list is anywhere near as long as the global board, and the
    # coverage check below refuses the board if that ever stops being true.
    ranked = [r for r in rows if r[2] > 0]
    if not ranked:
        diag["reason"] = "no positive ranks"
        return set(), diag
    g_max = max(r[2] for r in ranked)
    present = {r[2] for r in ranked}
    coverage = sum(1 for v in range(1, g_max + 1) if v in present) / g_max
    diag["global_prefix_G"] = g_max
    diag["prefix_coverage"] = round(coverage, 4)
    if g_max < MIN_GLOBAL_PREFIX or coverage < MIN_PREFIX_COVERAGE:
        diag["reason"] = "no usable 1..G global prefix"
        return set(), diag

    # Step 3 — at each rank value in the prefix, exactly one row is the global
    # one. FanGraphs orders an org list by FV descending and the org's
    # globally-ranked players are its best, so at a shared value the higher FV
    # is the global row. Ties resolve on row id, purely for determinism.
    by_rank: dict[int, list[tuple]] = defaultdict(list)
    for r in ranked:
        by_rank[r[2]].append(r)
    global_ids: set = set()
    for v in range(1, g_max + 1):
        grp = by_rank.get(v)
        if not grp:
            continue
        global_ids.add(max(
            grp, key=lambda r: ((r[3] if r[3] is not None else -1e9), str(r[0]))
        )[0])

    # Step 4 — fingerprint 2, the independent check. An org whose g players are
    # printed at their global rank has vacated its own slots 1..g, so its first
    # remaining position is g+1. A hole in the org list can push that later; a
    # position EARLIER than g+1 is a logical contradiction and is counted
    # separately.
    n_exact = n_off = 0
    worst_under = 0
    for org, items in by_org.items():
        pos = [r for r in items if r[0] not in global_ids and r[2] > 0]
        if not pos:
            continue
        g_here = sum(1 for r in items if r[0] in global_ids)
        lo = min(r[2] for r in pos)
        if lo == g_here + 1:
            n_exact += 1
        else:
            n_off += 1
            if lo < g_here + 1:
                worst_under = max(worst_under, (g_here + 1) - lo)
    n_checked = n_exact + n_off
    frac = (n_exact / n_checked) if n_checked else 0.0
    diag["offset_orgs_checked"] = n_checked
    diag["offset_exact_frac"] = round(frac, 4)
    diag["offset_worst_under"] = worst_under
    if n_checked < 2 or frac < MIN_OFFSET_EXACT_FRAC or worst_under > MAX_OFFSET_UNDER:
        diag["reason"] = "org start-offset fingerprint did not hold"
        return set(), diag

    # A rank <= 0 is not a rank at all (it occurs on two boards). It is neither
    # global nor a real org position; excluding it is strictly better than the
    # status quo, where implied_fv_from_rank(0) hands it FV 60.
    org_ids = {r[0] for r in rows if r[0] not in global_ids}
    diag["validated"] = True
    diag["n_org_rows"] = len(org_ids)
    diag["n_global_rows"] = len(global_ids)
    diag["reason"] = "ok"
    return org_ids, diag


def _org_ranked_snapshot_keys(snapshots: list[Snapshot]) -> tuple[set, dict]:
    """Run classify_board_org_ranks over every board in the corpus.

    Returns (set of (player_key, source, interval_label, snapshot_date) whose
    `rank` is an ORG position, per-board diagnostics).
    """
    boards: dict[tuple, list[tuple]] = defaultdict(list)
    for s in snapshots:
        if s.rank is None:
            continue
        boards[(s.source, s.interval_label or "", s.snapshot_date)].append(
            ((s.player_key, s.source, s.interval_label or "", s.snapshot_date),
             s.org or "", int(s.rank), s.fv)
        )
    org_keys: set = set()
    diags: dict = {}
    for board_key, rows in boards.items():
        ids, diag = classify_board_org_ranks(rows)
        org_keys |= ids
        diags["|".join(board_key)] = diag
    return org_keys, diags


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ConsensusPoint:
    snapshot_date: str
    interval_label: str

    avg_fv: float | None
    avg_fv_n: int

    avg_rank: float | None
    rank_implied_fv: float | None
    avg_rank_n: int

    # Post-shrinkage consensus. Until apply_shrinkage runs these mirror
    # consensus_fv_pre_shrinkage.
    consensus_fv: float
    consensus_fv_label: str
    consensus_fv_raw: float

    # Pre-shrinkage raw value (avg_fv or rank_implied_fv fallback). Surfaced
    # so the front-end can show "raw vs. adjusted" when useful.
    consensus_fv_pre_shrinkage: float

    # n / (n+k) — the weight Bayesian shrinkage placed on the player's
    # observations vs. the population mean. 1.0 means no shrinkage applied
    # (e.g. shrinkage skipped); lower values mean the prior pulled harder.
    shrinkage_weight: float

    sources_contributing: list[str]
    per_source: dict

    # Disagreement fields — computed only from explicit FV grades. Surface
    # how much sources agree on this player. None when fewer than two
    # sources published an explicit FV (a single number has no spread).
    # fv_min / fv_max are snapped to whole 20-80 grades so the UI can
    # render them next to the integer consensus_fv without mixed precision.
    fv_min: float | None = None
    fv_max: float | None = None
    fv_spread: float | None = None      # = fv_max - fv_min, on the raw scale
    fv_stddev: float | None = None      # population stddev of explicit FVs

    # Per-tool consensus, keyed by canonical tool name (hit, game_pwr,
    # raw_pwr, speed, field, throw, fb, sl, cb, ch, cmd). Each tool's
    # consensus is the unweighted mean across the sources that published
    # that tool on this date. Tools absent from every contributing source
    # are simply omitted from the dict — None never appears as a value.
    # Empty dict = no source published any tool grade on this date.
    tools_consensus: dict = field(default_factory=dict)
    # Per-tool spread (max - min) across publishing sources, for the UI
    # disagreement read. Only populated when ≥2 sources graded the tool.
    tools_spread: dict = field(default_factory=dict)

    # v14 — Sources whose published FV was Bayesian-pulled toward 30 on this
    # point because the player dropped off the source's most recent team
    # Top-30 list (e.g. MLB Pipeline Angels 2026 omits a player it graded
    # 55 on the 2025 list). The shrinkage is `new_fv = (prior_fv + 30) / 2`.
    # The UI surfaces a ↓ mark on those source's FV badge.
    dropped_off_sources: list[str] = field(default_factory=list)

    # v26 — True when any source contributing to THIS point published a
    # "+" upside marker (e.g. one source gave "55+" while others gave 50).
    # The numeric consensus_fv stays purely numeric; the boolean rides
    # alongside so the displayed label gets a "+" suffix and sort
    # comparators can break ties (42+ > 42).
    consensus_fv_plus: bool = False

    # Point-in-time org — the MLB org the prospect was in AS OF this snapshot.
    # The Time Machine (an explicitly point-in-time view) resolves its logo from
    # this, not the player's current org. FanGraphs records the historical org
    # per snapshot; other sources stamp the current org, so we don't trust theirs.
    # None on a genuine gap — the UI shows a neutral placeholder, never a wrong
    # current-org logo. Live/Statcast surfaces ignore this (they want current org).
    org: str | None = None


@dataclass
class PlayerTimeseries:
    player_key: str
    player_name: str
    position: str | None
    org: str | None

    points: list[ConsensusPoint]
    status: str

    # Candlestick fields (computed in build_timeseries)
    fv_high: float           # peak consensus_fv across this player's history
    fv_high_label: str
    fv_high_date: str
    fv_low: float            # trough consensus_fv across this player's history
    fv_low_label: str
    fv_low_date: str
    fv_open: float           # consensus_fv at the FIRST observation (candle "open")
    fv_close: float          # consensus_fv at the LATEST observation (candle "close")
    # v26 — '+' upside flag on the latest observation. Tracks whether the
    # most recent consensus point inherits the upside marker from any of
    # its contributing sources. Used by sort comparators to break ties
    # (42+ ranks above 42 but below 43) and by the frontend to render
    # "42+" on aggregate displays anchored on fv_close.
    fv_close_plus: bool = False

    # Total (source, snapshot_date) pairs across the player's history where
    # an explicit FV was published. Drives the single-instance shrinkage
    # trigger and the frontend "1" mark on the FV badge.
    fv_total_instances: int = 0

    # Set when status == "debuted". Renamed graduation_date → debut_date
    # (v20) — the field's semantics are now "MLB debut date", driven by
    # roster_status.mlb_debut_date in storage._derived_graduation_date.
    # The old name leaked the AB/IP-threshold-based graduation concept that
    # we no longer use.
    debut_date: str | None = None


# ---------------------------------------------------------------------------
# Core compute — one (player, date) bucket
# ---------------------------------------------------------------------------

def _pit_org(day_snaps, event_date):
    """Point-in-time org for a consensus point: the org the prospect was actually
    in AS OF this snapshot, not their current org.

    Two trustworthy point-in-time signals: FanGraphs records the historical org
    per snapshot (every other source stamps "now"), and a per-team list LABEL
    names the org ("… Astros Top 30" → HOU). We prefer signals published AT this
    snapshot date over stale forward-fills, so a just-published team list reflects
    a recent trade (e.g. a Jan list that already moved a prospect to his new org)
    rather than the last FanGraphs ranking. Returns None on a genuine gap so the
    Time Machine shows a neutral placeholder, never a wrong current-org logo."""
    from trades import canonical_org           # lazy import — avoid a cycle

    def _ok(o):                                     # a real 2-4 char org code
        return o if (o and len(o) <= 4 and o.isupper()) else None

    def _fg(snaps):
        fg = [s for s in snaps if s.source == "fangraphs" and s.org]
        if not fg:
            return None
        # FanGraphs abbreviates some orgs mixed-case ("StL"); upper-case first so
        # canonical_org's code path normalizes it (StL → STL).
        return _ok(canonical_org(max(fg, key=lambda s: s.snapshot_date or "").org.upper()))

    def _label(snaps):
        for s in snaps:
            o = _ok(canonical_org(getattr(s, "interval_label", "") or ""))
            if o:                                   # a team name in the label resolved
                return o
        return None

    fresh = [s for s in day_snaps if s.snapshot_date == event_date]
    return _fg(fresh) or _label(fresh) or _fg(day_snaps) or _label(day_snaps)


def load_source_weights() -> dict[str, float]:
    """Accuracy-derived relative vote weights (model-audit WS-5, shipped
    behind the vintage-disciplined A/B in data/consensus_weight_eval.json).
    Sources absent from the file vote at 1.0 — new sources are never
    punished for being new. Missing file = equal weighting everywhere."""
    import json as _json
    from pathlib import Path as _Path
    p = _Path(__file__).parent / "data" / "source_weights.json"
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in (d.get("weights") or {}).items()}
    except (OSError, ValueError):
        return {}


# Loaded once per process — the weights file is vintage-frozen (it only
# changes when a new base year resolves), so no within-run jitter.
_SOURCE_WEIGHTS = load_source_weights()


# Sources whose "FV" is a CONSTANT, not a published opinion.
#
#   performance_ingest  storage.upsert_unranked_active_player stamps a flat
#                       35.0 on every auto-discovered player. Measured
#                       2026-07-31: 2,808 rows, DISTINCT fv = {35.0}.
#   auto_detect         debut/roster tracker; carries no FV at all today
#                       (0 of 2,483 rows), listed so it can never start.
#
# `draft_signing` is deliberately NOT here even though
# grade_normalization._SYNTHETIC_SOURCES lists it: that flag only tells the
# quantile map to pass its scale through raw. Its VALUE is a real published
# draft-board FV (138 rows, varying), so it keeps its vote.
#
# WHY THEY MUST NOT VOTE ALONGSIDE A REAL GRADE
# ---------------------------------------------
# The equal-weight mean below gives every source 1.0 (data/source_weights.json
# has weights={} since 2026-07-25, and absent sources vote at 1.0). So for the
# 32 players who have BOTH a real published FV and an auto-discovery stamp, a
# fabricated 35 was averaged into the consensus at FanGraphs' weight - the
# same defect class as the fabricated BA-statcast FV-40 removed on 2026-07-30.
# A published 40 became a served 36.
#
# The constant is still the ONLY thing standing between ~2,776 genuinely
# ungraded auto-tracked players and having no consensus point at all
# (performance_ingest rows are written with rank = NULL, so there is no
# rank-implied fallback for them). It therefore stays as a LAST RESORT: it
# votes only when no real source published an FV at this point.
CONSTANT_ANCHOR_SOURCES = frozenset({"performance_ingest", "auto_detect"})


def compute_consensus_point(
    day_snaps: list[Snapshot],
    *,
    event_date: str | None = None,
    event_label: str | None = None,
    single_source_k: float = SINGLE_SOURCE_K,
    total_fv_instances: int | None = None,
    dropped_off_pairs: set[tuple[str, str]] | None = None,
    source_weights: dict[str, float] | None = None,
    grade_norm=None,
    org_ranked_rows: set | None = None,
) -> ConsensusPoint | None:
    """
    Aggregate one player's snapshots into a ConsensusPoint.

    `day_snaps` may come from a single calendar date OR — as it does after
    forward-fill in build_timeseries — be the latest snapshot from each
    source as of some event date. The aggregation is the same either way:
    one equal vote per source.

    Sources that publish only a rank contribute to avg_rank (and to a
    rank-implied FV fallback that is only used when zero sources published
    an explicit FV).

    Single-instance shrinkage: when `total_fv_instances` is provided
    (build_timeseries passes the player-level count of explicit-FV
    snapshots across history), the FV-35 pull only fires when the player
    has accumulated 1 instance ever — a FanGraphs-only prospect re-graded
    over 5 snapshots is well-observed and escapes the pull. When the
    kwarg is omitted (legacy callers + per-point unit tests), falls back
    to the older per-point trigger (`len(explicit_fvs) == 1`).
    """

    # Collapse multi-list outlets (Pipeline Top 100 + Pipeline
    # International, etc.) into one canonical source per outlet before
    # any aggregation logic runs — see _dedupe_source_aliases. Capture which rows
    # get RELABELED first, so grade normalization can still price them against the
    # list they were actually published on (see _alias_grade_sources).
    _alias_grade_src = _alias_grade_sources(day_snaps)
    day_snaps = _dedupe_source_aliases(day_snaps)

    explicit_fvs: list[float] = []
    _fv_weights: list[float] = []     # WS-5: per-vote relative weights (1.0 = equal)
    # Constant-anchor votes are collected SEPARATELY and folded back in only
    # if no real source published an FV here (see CONSTANT_ANCHOR_SOURCES).
    _synthetic_fvs: list[float] = []
    _synthetic_weights: list[float] = []
    _synthetic_sources: set[str] = set()
    ranks: list[int] = []
    rank_implied_fvs: list[float] = []

    per_source: dict[str, dict] = {}
    contributing_sources: set[str] = set()
    dropped_off_in_point: list[str] = []

    # Per-tool aggregation across sources. tools_by_key[key] is a list
    # of (source, grade) pairs; we never average values across multiple
    # snapshots from the same source — compute_consensus_point already
    # receives at most one row per source (forward-fill picks the
    # latest), so duplicates are impossible at this layer.
    tools_by_key: dict[str, list[float]] = {}

    pairs = dropped_off_pairs or set()
    for s in day_snaps:
        # v14 — if (player_key, source) appears in dropped_off_pairs, the
        # source's published FV is Bayesian-shrunk halfway to 30 BEFORE it
        # enters the consensus average. The penalty is k=1 (equal weight on
        # the negative observation), so a 55 → 42.5 and a 70 → 50. The
        # original published value is preserved on per_source.fv_published
        # for transparency; per_source.fv_adjusted carries the post-shrink
        # value, and per_source.dropped_off flags the source.
        source_dropped = (s.player_key, s.source) in pairs
        # Grade normalization (adopted 2026-07): quantile-map this source's FV onto
        # the FanGraphs scale BEFORE it enters the consensus, and before the dropped-
        # off shrink, so a hot/cold grader is de-biased on the same scale. Falls back
        # to the raw fv when there is no usable overlap. The per_source entry below
        # still records the RAW published grade (what the source actually said).
        base_fv = s.fv
        if grade_norm is not None and base_fv is not None:
            try:
                _yr = int(str(s.snapshot_date)[:4])
                _gsrc = _alias_grade_src.get((s.player_key, s.source), s.source)
                _nm = grade_norm(base_fv, _gsrc, s.position, _yr)
                if _nm is not None:
                    base_fv = _nm
            except (TypeError, ValueError):
                base_fv = s.fv
        fv_for_consensus = base_fv
        fv_adjusted = None
        if source_dropped and base_fv is not None:
            fv_adjusted = (float(base_fv) + 30.0) / 2.0
            fv_for_consensus = fv_adjusted
            dropped_off_in_point.append(s.source)
        # v10 — When the same source publishes MULTIPLE lists with the
        # same date (e.g. MLB Pipeline drops Top 100 + Org Top 30 both
        # dated 2026-01-22 — Theo Gillen is #1 on Rays Top 30, #43 on
        # Top 100, both at FV 55), keep the FIRST one as the primary
        # per_source entry and append the rest to `extras`. The source-
        # by-source FV history UI walks primary + extras so both
        # publications surface; the FV stays in `explicit_fvs` exactly
        # once because both entries carry the same FV from the same
        # outlet (averaging the same value twice doesn't help).
        entry = {
            "rank": s.rank,
            "fv_published": s.fv,
            "fv_adjusted": fv_adjusted,
            "dropped_off": source_dropped,
            "interval_label": s.interval_label,
            "status": s.status,
            "snapshot_date": s.snapshot_date,
            "tools": dict(s.tools) if s.tools else None,
            # v26 — Per-source '+' upside marker. Carried through to the
            # JSON export so per-source breakdown rows can render "FG: 55+".
            "fv_plus": bool(getattr(s, "fv_plus", False)),
        }
        already = per_source.get(s.source)
        if already is None:
            per_source[s.source] = entry
            if fv_for_consensus is not None:
                if s.source in CONSTANT_ANCHOR_SOURCES:
                    # Park it. It is a placeholder constant, not an opinion;
                    # it only gets to vote if nothing real graded this player.
                    _synthetic_fvs.append(fv_for_consensus)
                    _synthetic_weights.append((source_weights or {}).get(s.source, 1.0))
                    _synthetic_sources.add(s.source)
                else:
                    explicit_fvs.append(fv_for_consensus)
                    _fv_weights.append((source_weights or {}).get(s.source, 1.0))
                    contributing_sources.add(s.source)
        else:
            # Same-date same-source duplicate. Surface in `extras` so
            # the UI can render it as a second publication row; do NOT
            # contribute another vote to the consensus FV.
            already.setdefault("extras", []).append(entry)
        if s.rank is not None:
            # v15/v18 — Exclude team-Top-N ranks from the consensus
            # avg_rank + rank-implied FV math. Org-specific lists rank
            # "best in this org" not "best overall," so a #1 on the
            # Marlins list isn't comparable to a #1 on a global Top-100.
            # Two label formats to catch:
            #   * internal slug: "..._org_..." (legacy)
            #   * human-readable: "MLB Pipeline 2021 Nationals Top 30"
            # The Top-N suffix uses end-of-string anchoring so "Top 30"
            # matches but "Top 300" wouldn't, and "Top 100" / "Top 200"
            # never trigger. Bryan Sanchez was the canary — his only
            # signal was rank 30 on the 2021 Nationals Top-30, and the
            # legacy check missed the label format → rank 30 inflated
            # to FV 55 → he sorted #19 overall despite zero published FVs.
            #
            # v27 -- a THIRD case the label cannot express: a FanGraphs board
            # carries org positions and global ranks under ONE label, so no
            # label test can separate them. `org_ranked_rows` is the
            # value-level classification from _org_ranked_snapshot_keys; it
            # only ever ADDS exclusions, so the two label formats above keep
            # working exactly as before.
            _lbl = s.interval_label or ""
            is_org_list = ("_org_" in _lbl) or _ORG_LIST_LABEL_RE.search(_lbl) is not None
            if not is_org_list and org_ranked_rows:
                is_org_list = (
                    s.player_key, s.source, _lbl, s.snapshot_date
                ) in org_ranked_rows
            if not is_org_list:
                implied = implied_fv_from_rank(s.rank)
                if implied is not None:
                    ranks.append(s.rank)
                    rank_implied_fvs.append(implied)
                    contributing_sources.add(s.source)
        if s.tools:
            for k, v in s.tools.items():
                # `_extras` is a sibling metadata dict, not a tool grade —
                # passes through per_source.tools._extras via the dict
                # copy at line 343, must not enter numeric aggregation.
                if k == "_extras":
                    continue
                tools_by_key.setdefault(k, []).append(v)
                contributing_sources.add(s.source)

    # LAST-RESORT fold-back of the constant anchor. If no outlet published an
    # FV at this point, the placeholder is all we have and it must still stand
    # in, or the ~2,776 auto-discovered players whose only FV row is the
    # synthetic 35 would lose their ConsensusPoint entirely and vanish from
    # the board (their rows carry rank = NULL, so there is no rank fallback).
    # Once ANY real grade exists, the constant stays out of the average.
    if not explicit_fvs and _synthetic_fvs:
        explicit_fvs = _synthetic_fvs
        _fv_weights = _synthetic_weights
        contributing_sources |= _synthetic_sources

    if not explicit_fvs and not rank_implied_fvs:
        return None

    # WS-5 — accuracy-weighted mean (weights are all 1.0 unless the
    # shipped source_weights file says otherwise; the dispersion stats
    # below stay unweighted — disagreement is disagreement).
    if explicit_fvs:
        _wsum = sum(_fv_weights) or float(len(explicit_fvs))
        avg_fv = sum(w * v for w, v in zip(_fv_weights, explicit_fvs)) / _wsum
    else:
        avg_fv = None
    avg_rank = sum(ranks) / len(ranks) if ranks else None
    rank_implied_fv = (
        sum(rank_implied_fvs) / len(rank_implied_fvs)
        if rank_implied_fvs else None
    )

    # Disagreement only meaningful with ≥2 explicit FV grades. fv_min /
    # fv_max get snapped to whole grades for display consistency with
    # consensus_fv; fv_spread/fv_stddev stay raw so a "2.5-grade spread"
    # doesn't get hidden by rounding.
    if len(explicit_fvs) >= 2:
        raw_min, raw_max = min(explicit_fvs), max(explicit_fvs)
        fv_min_snapped, _ = snap_to_grade(raw_min)
        fv_max_snapped, _ = snap_to_grade(raw_max)
        fv_min = fv_min_snapped
        fv_max = fv_max_snapped
        fv_spread = round(raw_max - raw_min, 2)
        fv_stddev = round(statistics.pstdev(explicit_fvs), 2)
    else:
        fv_min = fv_max = fv_spread = fv_stddev = None

    # Consensus = the accuracy-weighted mean of explicit FVs computed above.
    # Fall back to the rank-implied mean ONLY when no source published an FV grade —
    # otherwise a player ranked only by Baseball America / The Athletic
    # would have no consensus FV at all.
    pre_shrinkage = avg_fv if avg_fv is not None else rank_implied_fv
    assert pre_shrinkage is not None

    # Single-instance uncertainty pull. When the player has accumulated
    # only ONE explicit-FV instance across their entire history (1
    # snapshot, 1 source, ever — typically a brand-new 2026 IFA appearing
    # only on Pipeline's Top 50), shrink the consensus toward FV 35 using
    # a Bayesian prior with k=0.5. This pulls a 65 → 55, a 50 → 45, etc.
    # Higher grades get pulled harder, which matches the principle that
    # the variance on a high-end singleton is wider than on a corroborated
    # grade. A player re-graded over multiple snapshots — even by a
    # single source — escapes the pull because the source has confirmed
    # the grade over time. Multi-source consensus also stays untouched.
    # The pre-shrinkage value is preserved on the point for transparency.
    #
    # Legacy callers (per-point unit tests) that omit total_fv_instances
    # fall back to the older per-point trigger so synthetic fixtures
    # keep working without plumbing a player-level count.
    if total_fv_instances is not None:
        should_shrink = total_fv_instances <= 1 and explicit_fvs and single_source_k > 0
    else:
        should_shrink = len(explicit_fvs) == 1 and single_source_k > 0
    if should_shrink:
        shrinkage_weight_val = 1.0 / (1.0 + single_source_k)  # = 2/3 at K=0.5
        consensus_fv_raw_value = (
            shrinkage_weight_val * pre_shrinkage
            + (1.0 - shrinkage_weight_val) * SINGLE_SOURCE_PRIOR
        )
    else:
        shrinkage_weight_val = 1.0
        consensus_fv_raw_value = pre_shrinkage
    consensus_fv, consensus_label = snap_to_grade(consensus_fv_raw_value)

    # Default snapshot_date / interval_label come from the latest snapshot
    # in `day_snaps` (forward-fill yields a heterogeneous mix); callers
    # forward-filling across event dates pass explicit overrides.
    if event_date is None or event_label is None:
        latest_snap = max(day_snaps, key=lambda s: s.snapshot_date)
        event_date = event_date or latest_snap.snapshot_date
        event_label = event_label or latest_snap.interval_label

    # Per-tool consensus = unweighted mean across publishing sources.
    # Round to 0.5 grade — matches the precision of FanGraphs' published
    # tool grids and keeps the UI from showing 57.33-style noise.
    tools_consensus: dict[str, float] = {}
    tools_spread: dict[str, float] = {}
    for k, grades in tools_by_key.items():
        if not grades:
            continue
        mean = sum(grades) / len(grades)
        tools_consensus[k] = round(mean * 2) / 2
        if len(grades) >= 2:
            tools_spread[k] = round(max(grades) - min(grades), 2)
    # v12 — synthesize a unified `pwr` consensus from game_pwr + raw_pwr
    # so downstream displays only show ONE power grade per prospect.
    # Mean when both are present; pass-through when only one is.
    if "pwr" not in tools_consensus:
        g = tools_consensus.get("game_pwr")
        r = tools_consensus.get("raw_pwr")
        if g is not None and r is not None:
            tools_consensus["pwr"] = round(((g + r) / 2) * 2) / 2
        elif g is not None:
            tools_consensus["pwr"] = g
        elif r is not None:
            tools_consensus["pwr"] = r

    # v17 — Fold FG physical grades (Frame / Athl / Delivery) into the
    # consensus tools dict as 20-80 FV equivalents so the active-list
    # chip strip and per-tool grid surface them alongside the 20-80
    # scouted grades. FG publishes on a -2..+2 plus/minus scale; we map
    # -2→30, -1→40, 0→50, +1→60, +2→70 so the chip-tier color ramp
    # works without a special case. Only FG publishes these so we look
    # only at the FG per-source _extras dict (other sources omit them).
    def _pm_to_fv(pm):
        if pm is None: return None
        try: v = int(pm)
        except (TypeError, ValueError): return None
        if v < -2 or v > 2: return None
        return float(50 + 10 * v)
    for s in day_snaps:
        if s.source != "fangraphs" or not s.tools:
            continue
        ex = s.tools.get("_extras") if isinstance(s.tools, dict) else None
        if not isinstance(ex, dict):
            continue
        for phys_key in ("frame", "athl", "delivery"):
            if phys_key in tools_consensus:
                continue
            fv = _pm_to_fv(ex.get(phys_key))
            if fv is not None:
                tools_consensus[phys_key] = fv

    # v27 — Aggregate '+' upside flag: if ANY source contributing to this
    # point published a "+" grade (e.g. one source said "55+"), the
    # consensus point inherits the flag. The flag drives a hot-pink chip
    # indicator (matched by chart dots) on the frontend; the displayed
    # label itself stays a plain integer (e.g. "55") — no "+" suffix on
    # the text, since the visual mark carries the signal.
    consensus_fv_plus = any(
        bool(getattr(s, "fv_plus", False))
        for s in day_snaps if s.source in contributing_sources
    )
    return ConsensusPoint(
        snapshot_date=event_date,
        interval_label=event_label,
        avg_fv=round(avg_fv, 2) if avg_fv is not None else None,
        avg_fv_n=len(explicit_fvs),
        avg_rank=round(avg_rank, 1) if avg_rank is not None else None,
        rank_implied_fv=rank_implied_fv,
        avg_rank_n=len(ranks),
        consensus_fv=consensus_fv,
        consensus_fv_label=consensus_label,
        consensus_fv_raw=round(consensus_fv_raw_value, 2),
        consensus_fv_pre_shrinkage=round(pre_shrinkage, 2),
        shrinkage_weight=shrinkage_weight_val,
        sources_contributing=sorted(contributing_sources),
        per_source=per_source,
        fv_min=fv_min,
        fv_max=fv_max,
        fv_spread=fv_spread,
        fv_stddev=fv_stddev,
        tools_consensus=tools_consensus,
        tools_spread=tools_spread,
        dropped_off_sources=sorted(set(dropped_off_in_point)),
        consensus_fv_plus=consensus_fv_plus,
        org=_pit_org(day_snaps, event_date),
    )


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------

def _shrinkage_n(point: ConsensusPoint) -> int:
    """Total number of sources providing *any* signal on this player.

    Uses the union of (a) sources that published an explicit FV and (b)
    sources that ranked the player without an FV. Both kinds of signal
    are real coverage — if Baseball America or Just Baseball ranks a
    prospect #4 without grading them, that's still strong evidence we
    "know who this player is" and the prior shouldn't pull as hard.

    This is more generous than the old rule (`avg_fv_n` only, falling
    back to `avg_rank_n` only when zero explicit FVs exist), which under-
    counted prospects like Jesús Made: graded by 4 outlets and ranked by
    a 5th, but `n` came in at 4 and the prior nudged him down a tier.
    """
    return len(point.sources_contributing)


# DEAD CODE, DELIBERATELY KEPT (v27). Neither apply_shrinkage nor
# compute_prior_mean_fv has a production caller: build_timeseries stopped
# calling them in 2026-05 when the population prior was removed, and the
# three constants they default from (DEFAULT_SHRINKAGE_K, DEFAULT_N_FULL,
# FALLBACK_PRIOR_FV) are inert for the same reason. They are NOT deleted:
# test_consensus.py imports them at module scope, so removing them breaks a
# test and buys nothing. Do not wire them back in without a gate.
def apply_shrinkage(
    point: ConsensusPoint,
    mean_fv: float,
    k: float = DEFAULT_SHRINKAGE_K,
    n_full: int = DEFAULT_N_FULL,
) -> None:
    """Mutate `point` in place to fold Bayesian shrinkage into consensus_fv.

        k_eff    = k * max(0, (n_full - n) / n_full)
        adjusted = (n / (n + k_eff)) * raw + (k_eff / (n + k_eff)) * mean_fv

    When n >= n_full, k_eff = 0 and the raw value passes through unchanged.
    Pre-shrinkage fields stay readable via consensus_fv_pre_shrinkage.
    """
    n = _shrinkage_n(point)
    raw = point.consensus_fv_pre_shrinkage
    # Snap the pre-shrinkage value first so the no-pull branches below are
    # idempotent: re-running apply_shrinkage on an already-shrunk point
    # (e.g. when tuning the formula and re-patching exported JSON) doesn't
    # leave stale post-shrinkage values in consensus_fv when the new
    # parameters say "no pull at all".
    raw_snapped, raw_label = snap_to_grade(raw)
    point.consensus_fv = raw_snapped
    point.consensus_fv_label = raw_label
    point.consensus_fv_raw = round(raw, 2)
    if n <= 0 or k <= 0 or n_full <= 0:
        # Nothing to shrink toward, or shrinkage disabled. Leave defaults.
        point.shrinkage_weight = 1.0
        return
    k_eff = k * max(0.0, (n_full - n) / n_full)
    if k_eff == 0.0:
        # Full coverage — no prior pull.
        point.shrinkage_weight = 1.0
        return
    weight = n / (n + k_eff)
    adjusted = weight * raw + (1.0 - weight) * mean_fv
    point.consensus_fv_raw = round(adjusted, 2)
    snapped, label = snap_to_grade(adjusted)
    point.consensus_fv = snapped
    point.consensus_fv_label = label
    point.shrinkage_weight = round(weight, 4)


# DEAD CODE, DELIBERATELY KEPT (v27). See the note above apply_shrinkage.
def compute_prior_mean_fv(
    timeseries: list["PlayerTimeseries"],
    fallback: float = FALLBACK_PRIOR_FV,
) -> float:
    """Mean of each player's latest pre-shrinkage consensus FV.

    Each player contributes one data point (their most recent point's
    pre-shrinkage value), so a single source that grades a hundred
    prospects can't dominate the prior.
    """
    vals: list[float] = []
    for p in timeseries:
        if not p.points:
            continue
        v = p.points[-1].consensus_fv_pre_shrinkage
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else fallback


# ---------------------------------------------------------------------------
# Time-series & candlestick assembly
# ---------------------------------------------------------------------------

def _dropped_off_pairs(snapshots: list[Snapshot]) -> set[tuple[str, str]]:
    """Detect (player_key, source) pairs that fell off a source's most recent
    team-Top-30 list relative to that source's prior team-Top-30 list.

    Only team-specific lists are scoped: a global Top 100 dropping a player
    isn't an "off the org list" event and is captured by the existing
    single-source / freshness signals.

    v27 -- this used to require the LEGACY internal slug "_org_" literally, and
    that slug occurs zero times in the snapshot corpus, so this function
    returned the empty set on every run and the (fv+30)/2 drop-off shrink in
    compute_consensus_point had never once fired in production. It is the same
    two-label-format hazard that was found and fixed for the rank-implied-FV
    path ~300 lines above and never propagated down here. Slug extraction now
    goes through org_slug_from_label, which accepts both formats and bounds the
    org token to a real club.

    Algorithm:
      1. Group snapshots by (source, org-slug-from-interval-label).
      2. Within each group, take the two most-recent distinct
         interval_label values by max(snapshot_date).
      3. The diff "in prior list but not in latest list" is the
         dropped-off set for that (source, org).
      4. Union across all (source, org) groups → returned set.

    Edge cases:
      - Source has only ever published one team Top-30 list: no pairs.
      - Player appears in both lists: not flagged.
      - Player was traded between lists (org A → org B): treated as
        dropped-off from source's org-A list. Acceptable — the trade is
        independent signal and the shrinkage is mild (k=1).
    """
    if not snapshots:
        return set()
    # group: {(source, org_slug): {interval_label: (latest_date, set(player_keys))}}
    grouped: dict[tuple[str, str], dict[str, tuple[str, set[str]]]] = {}
    for s in snapshots:
        org_slug = org_slug_from_label(s.interval_label)
        if org_slug is None:
            continue
        key = (s.source, org_slug)
        bucket = grouped.setdefault(key, {})
        prev = bucket.get(s.interval_label)
        if prev is None:
            bucket[s.interval_label] = (s.snapshot_date, {s.player_key})
        else:
            latest_date, players = prev
            players.add(s.player_key)
            if s.snapshot_date > latest_date:
                latest_date = s.snapshot_date
            bucket[s.interval_label] = (latest_date, players)

    pairs: set[tuple[str, str]] = set()
    for (source, _org_slug), labels in grouped.items():
        if len(labels) < 2:
            continue
        # Sort interval_labels by their latest snapshot_date descending —
        # the top 2 are the latest & prior lists for this (source, org).
        sorted_labels = sorted(labels.items(),
                               key=lambda kv: kv[1][0], reverse=True)
        latest_players = sorted_labels[0][1][1]
        prior_players = sorted_labels[1][1][1]
        for pk in prior_players - latest_players:
            pairs.add((pk, source))
    return pairs


def _dropped_off_timeline(snapshots: list[Snapshot]) -> dict[str, set]:
    """As-of pair sets: {event_date -> pairs known using data up to that date}.

    v27 -- _dropped_off_pairs takes the two most recent org lists over the WHOLE
    corpus and the result was applied to every historical point, so a 2019
    consensus point would have been shrunk on the basis of a 2025 list. That was
    inert while the detector was dead; the moment the detector works it is a
    future-derived input to the dominant eFV feature, so it is fixed in the same
    change rather than left as a fresh leak.

    Cost: the pair set can only change on a date that actually carries org-list
    rows, so the diff runs on those dates only (a few hundred) and every other
    date forward-fills the same set object. It is NOT one recompute per player,
    which is what would make this quadratic.
    """
    org_rows = [s for s in snapshots if org_slug_from_label(s.interval_label)]
    all_dates = sorted({s.snapshot_date for s in snapshots})
    if not org_rows:
        return {d: set() for d in all_dates}
    by_date: dict[str, list[Snapshot]] = defaultdict(list)
    for s in org_rows:
        by_date[s.snapshot_date].append(s)

    timeline: dict[str, set] = {}
    cur: set = set()
    running: list[Snapshot] = []
    for d in all_dates:
        if d in by_date:
            running.extend(by_date[d])
            cur = _dropped_off_pairs(running)
        timeline[d] = cur
    return timeline


def normalize_name_for_dedup(name: str) -> str:
    """Module-level twin of the name key build_timeseries dedupes on."""
    if not name:
        return ""
    cleaned = name.lower().replace(",", "").replace(".", "")
    cleaned = cleaned.replace("’", "'").replace("‘", "'")
    return " ".join(cleaned.split())


def same_name_collisions(snapshots: list[Snapshot]) -> list[dict]:
    """REPORT same-name player_key clusters that build_timeseries would merge.

    v27 (D16). `_SAME_NAME_NOT_DUPES` is empty, so every same-name pair is
    merged unconditionally and one player's points land on another's consensus.
    This function does NOT change that: it reports, so the allowlist can be
    populated by hand. It never merges and never splits.

    A cluster is flagged `provably_different_players` when two of its keys carry
    DIFFERENT trailing numeric ids, which are external player ids, not slug
    disambiguators. `windows_overlap` says whether the two keys were graded in
    overlapping date ranges, which is the softer tell.

    Counts are deliberately NOT written into this docstring. They move with the
    corpus; read them from the artifact.
    """
    by_key: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_key[s.player_key].append(s)
    by_name: dict[str, set] = defaultdict(set)
    for key, snaps in by_key.items():
        nm = normalize_name_for_dedup(_canonical_player_name(key, snaps[-1].player_name))
        if nm:
            by_name[nm].add(key)

    out: list[dict] = []
    for nm, keys in sorted(by_name.items()):
        if len(keys) < 2:
            continue
        detail = []
        for key in sorted(keys):
            snaps = by_key[key]
            dates = sorted(s.snapshot_date for s in snaps)
            detail.append({
                "player_key": key,
                "n_snaps": len(snaps),
                "first": dates[0],
                "last": dates[-1],
                "orgs": sorted({s.org for s in snaps if s.org}),
                "sources": sorted({s.source for s in snaps}),
            })
        ids = sorted({
            k.rsplit("_", 1)[-1] for k in keys
            if k.rsplit("_", 1)[-1].isdigit()
        })
        overlap = any(
            a["first"] <= b["last"] and b["first"] <= a["last"]
            for i, a in enumerate(detail) for b in detail[i + 1:]
        )
        out.append({
            "normalized_name": nm,
            "keys": sorted(keys),
            "distinct_numeric_ids": ids,
            "windows_overlap": overlap,
            "any_noid_key": any(k.endswith("__noid") for k in keys),
            "provably_different_players": len(ids) >= 2,
            "detail": detail,
        })
    return out


def _latest_meta(snaps: list[Snapshot]) -> tuple[str, str | None, str | None]:
    snaps_sorted = sorted(snaps, key=lambda s: s.snapshot_date, reverse=True)
    # FanGraphs forward-projects positions — they publish where a
    # prospect is *expected* to land long-term (incl. SP / SIRP / MIRP
    # role designations), not just the current MiLB roster slot. Prefer
    # FG when present; fall back to latest-non-null from any source
    # otherwise. The team-org and player-name resolution stay on the
    # latest-non-null heuristic (no source has a meaningful claim to be
    # more authoritative on org/name).
    #
    # EXCEPTION — graduated players: once a player reaches MLB the
    # forward-projection rationale flips. FG's prospect-era guess (e.g.
    # Xavier Edwards "CF" in 2023) gets out-of-date against the actual
    # major-league role. For grads, prefer the latest snapshot from a
    # depth-chart-faithful source (MLB Pipeline / Baseball America /
    # ESPN). FanGraphs is excluded because it forward-projects; the
    # `auto_detect` source is excluded because it inherits whichever
    # source flagged graduation (which on Edwards' record was the same
    # FG snapshot that pegged him at CF), so trusting auto_detect would
    # just relaunder the FG projection.
    is_graduated = any(s.status == "debuted" for s in snaps)
    if is_graduated:
        _EXCLUDED_FOR_GRAD_POS = {"fangraphs", "auto_detect"}
        non_fg_pos = next((s.position for s in snaps_sorted
                           if s.source not in _EXCLUDED_FOR_GRAD_POS and s.position), None)
        if non_fg_pos:
            return (
                snaps_sorted[0].player_name,
                non_fg_pos,
                next((s.org for s in snaps_sorted if s.org), None),
            )
    # NB: FG's MIRP/SIRP role projections get a usage correction (rule
    # D: current-season MiLB GS-share >= 0.50, IP/G >= 3.0, IP >= 20
    # flips the label to SP) downstream at the storage export seam via
    # role_usage.usage_position_override. It cannot happen here:
    # Snapshot/PlayerTimeseries carry no mlbam id, and consensus.py
    # cannot import storage (storage imports consensus).
    fg_pos = next((s.position for s in snaps_sorted
                   if s.source == "fangraphs" and s.position), None)
    any_pos = next((s.position for s in snaps_sorted if s.position), None)
    return (
        snaps_sorted[0].player_name,
        fg_pos or any_pos,
        next((s.org for s in snaps_sorted if s.org), None),
    )


def _candle_fields(points: list[ConsensusPoint]) -> dict:
    """Compute high / low / open / close from the consensus_fv sequence."""
    if not points:
        return {
            "fv_high": 0.0, "fv_high_label": "—", "fv_high_date": "",
            "fv_low":  0.0, "fv_low_label":  "—", "fv_low_date":  "",
            "fv_open": 0.0, "fv_close": 0.0,
            "fv_close_plus": False,
        }
    high_pt = max(points, key=lambda p: p.consensus_fv)
    low_pt  = min(points, key=lambda p: p.consensus_fv)
    return {
        "fv_high":       high_pt.consensus_fv,
        "fv_high_label": high_pt.consensus_fv_label,
        "fv_high_date":  high_pt.snapshot_date,
        "fv_low":        low_pt.consensus_fv,
        "fv_low_label":  low_pt.consensus_fv_label,
        "fv_low_date":   low_pt.snapshot_date,
        "fv_open":       points[0].consensus_fv,
        "fv_close":      points[-1].consensus_fv,
        # v26 — Track '+' on the latest observation so sort comparators
        # can break ties (42+ > 42). consensus_fv_label already carries
        # the suffix for label-based rendering.
        "fv_close_plus": bool(getattr(points[-1], "consensus_fv_plus", False)),
    }


# Slug-collision detection thresholds. A genuine prospect is graded across a <=7-year window,
# so the two signals that a player_key actually holds TWO different people are: (a) a gap too
# long for one prospect career, or (b) a pitcher<->hitter flip across a multi-year gap (a person
# does not switch sides). Same-side medium gaps are left ALONE -- they are usually one player who
# fell off the boards and re-emerged (e.g. a slow-developing IFA), and we must not drop real
# history. Conservative by design: only the unambiguous collisions are split.
_GAP_BIG_DAYS = 8 * 365      # >8yr apart cannot be the same prospect-era player (different person)
_GAP_FLIP_DAYS = 4 * 365     # >4yr apart AND a pitcher<->hitter flip = different person
_PITCHER_TOKENS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "P", "CL", "CP", "RHP/", "LHP/"}


def _is_pitcher_pos(pos: str | None) -> bool:
    return bool(pos) and pos.split("/")[0].strip().upper() in _PITCHER_TOKENS


def _prune_collision_cluster(snaps: list[Snapshot]) -> list[Snapshot]:
    """Same-name slug collisions merge two different people under one player_key (e.g. the late
    RHP José Fernández + a current SS Jose Fernandez both slug to 'jose_fernandez', polluting the
    live player with a decade-old FV-70). Keep only the most-recent cluster and drop everything
    before the last gap that is UNAMBIGUOUSLY a different person: a gap > 8yr (too long for one
    prospect career) OR a gap > 4yr that flips pitcher<->hitter. Same-side medium gaps are kept
    (likely one re-emergent player). No-op otherwise."""
    from datetime import date as _date
    dated = []
    for s in snaps:
        try:
            dated.append((_date.fromisoformat((s.snapshot_date or "")[:10]), s))
        except ValueError:
            continue
    if len(dated) < 2:
        return snaps
    dated.sort(key=lambda t: t[0])
    cut = None
    for (d_prev, s_prev), (d_cur, s_cur) in zip(dated, dated[1:]):
        gap = (d_cur - d_prev).days
        if gap <= _GAP_FLIP_DAYS:
            continue
        flip = (s_prev.position and s_cur.position
                and _is_pitcher_pos(s_prev.position) != _is_pitcher_pos(s_cur.position))
        if gap > _GAP_BIG_DAYS or flip:
            cut = s_cur.snapshot_date            # start of the most-recent (live) cluster
    if cut is None:
        return snaps
    return [s for s in snaps if (not s.snapshot_date) or s.snapshot_date >= cut]


def build_timeseries(
    snapshots: list[Snapshot],
    *,
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    shrinkage_n_full: int = DEFAULT_N_FULL,
    prior_mean_fv: float | None = None,
    single_source_k: float = SINGLE_SOURCE_K,
    normalize: bool = False,
) -> list[PlayerTimeseries]:
    """Build per-player FV time-series with forward-filled sources.

    Forward-fill: at each event date, the consensus aggregates the latest
    snapshot from every source that has ever graded the player up to that
    date. This is what fixes the Asigen case — FG snaps on 5/17 + Pipeline
    Intl snaps on 5/19 produce a 5/19 point that averages BOTH grades, not
    just the most recent single source.

    SHRINKAGE — read this before tuning anything. `shrinkage_k`,
    `shrinkage_n_full` and `prior_mean_fv` are INERT. They are kept only so
    pre-2026-05 callers still import; the body never reads them, and neither
    apply_shrinkage nor compute_prior_mean_fv is wired in (see the note above
    the `for p in result:` loop at the end of this function, where the
    population prior was removed in 2026-05). This docstring previously
    claimed the population prior was "applied uniformly across every point",
    which is false and cost a later audit real time.

    The ONE live shrinkage is `single_source_k` (SINGLE_SOURCE_K = 0.5, pulling
    toward SINGLE_SOURCE_PRIOR = FV 35), applied inside compute_consensus_point
    when the player has exactly one explicit-FV instance across all history.
    Measured 2026-07-25: that pull fires on 2,818 of 4,477 active players with a
    published FV (62.9% of the live board) but on only 56 of 5,347 rows (1.0%)
    of the 2017-2023 resolved backtest window, because attrition drops exactly
    the thinly-covered players it exists to discipline. A k sweep on that window
    is therefore near-powerless: over k in [0.25, 0.75] the mean cross-year
    Spearman against realized WAR moves by <= 0.0006 and raising k to 1.0/2.0
    sits inside a zero-information placebo band (p95 |d_rho| 0.0021). Turning
    the pull OFF (k=0) is the only resolvable move and it is a WASH -
    d_rho -0.0045 [-0.0077, -0.0016] but d_auc +0.0048 [+0.0026, +0.0077], the
    two metrics disagreeing in sign. Leave both constants alone until the
    backtest universe stops dropping non-debuts.
    """
    snapshots = [_canonicalize_player_snapshot(s) for s in snapshots]
    # Grade normalization (adopted 2026-07): build the quantile-mapping remapper ONCE
    # here (single DB pass) and pass the PURE closure into every consensus point, so
    # the hot path stays free of per-point DB hits. None when disabled -> raw scale.
    grade_norm = None
    if normalize:
        try:
            from grade_normalization import build_remapper
            # as_of_year = the newest snapshot year in this pool, so every cell is
            # capped at its own year and none pools a cycle that had not happened.
            # Data-derived, not clock-derived, so the build stays reproducible.
            grade_norm = build_remapper(aliases=SOURCE_ALIASES,
                                        as_of_year=grade_norm_cutoff(snapshots))
        except Exception:
            grade_norm = None   # degrade to the raw scale rather than crash the build
    # v14 — drop-off detection runs ONCE across the full snapshot pool so
    # every player-level compute_consensus_point call shares the same view
    # of "which (player, source) pairs lost a Top-30 spot." Stays out of
    # the per-player loop to avoid O(N×M) recomputation.
    #
    # v27 -- the pair set is now an as-of TIMELINE (see _dropped_off_timeline),
    # and it is gated behind DROPOFF_SHRINK_ENABLED because repairing the
    # detector turns a shrink that has never fired into a live grade change.
    dropped_timeline: dict[str, set] = {}
    if DROPOFF_SHRINK_ENABLED:
        dropped_timeline = _dropped_off_timeline(snapshots)
    # v27 -- value-level org/global rank split, computed ONCE over the whole
    # corpus for the same reason the drop-off pass is: it is a board-level
    # property and recomputing it per player would be O(N*M).
    org_ranked_rows: set = set()
    if ORG_RANK_VALUE_DETECTOR:
        org_ranked_rows, _org_rank_diags = _org_ranked_snapshot_keys(snapshots)
    by_player: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_player[s.player_key].append(s)

    result: list[PlayerTimeseries] = []
    for player_key, player_snaps in by_player.items():
        # Guard against same-name slug collisions (a retired player + a current prospect under
        # one key): keep only the most-recent contiguous grading cluster. No-op for normal players.
        player_snaps = _prune_collision_cluster(player_snaps)
        name, pos, org = _latest_meta(player_snaps)
        name = _canonical_player_name(player_key, name)

        by_date: dict[str, list[Snapshot]] = defaultdict(list)
        for s in player_snaps:
            by_date[s.snapshot_date].append(s)

        # Single-instance shrinkage trigger: count how many published-FV
        # observations the player has accumulated across their entire
        # history (deduped per (source, snapshot_date)). With ≥2 instances
        # the player is considered well-observed and the FV-35 pull does
        # NOT fire at any of their points — even single-source players
        # who have been re-graded over time escape the pull. Brand-new
        # prospects with exactly one published grade still get pulled,
        # which is the intended uncertainty signal.
        #
        # 2026-07-31 - constant-anchor rows are NOT observations. Counting a
        # performance_ingest stamp here let a fabricated FV 35 buy a real
        # single-source grade an escape from the very uncertainty pull it is
        # supposed to trigger (measured: 25 of the 32 affected players had
        # exactly one real grade plus one synthetic stamp, so they read as
        # "2 instances, well observed"). Same reasoning as
        # CONSTANT_ANCHOR_SOURCES in compute_consensus_point. A player whose
        # ONLY rows are synthetic lands at 0 instances, which still trips the
        # pull - and pulling 35 toward a prior of 35 is a no-op, so nothing
        # moves for that cohort.
        #
        # 2026-08-07 (v27) - AS-OF. This count used to be taken over the
        # player's ENTIRE history and then handed unchanged to every event
        # date, so whether the FV-35 pull fired on a 2019 point depended on
        # whether the player happened to be re-graded in 2024. Computing a
        # historical point from the future is wrong on its own terms, so the
        # count is now accumulated inside the chronological event-date walk
        # below. The accumulation is one set insertion per snapshot, i.e. the
        # same asymptotic cost as this pre-pass; a naive recount inside the
        # loop would have been quadratic. Measured effect at adoption: 117 of
        # 3,933 eFV matrix rows, mean abs 3.10 FV, max 10.42 FV.
        seen_fv_keys: set[tuple[str, str]] = set()
        for s in player_snaps:
            if s.fv is not None and s.source not in CONSTANT_ANCHOR_SOURCES:
                seen_fv_keys.add((s.source, s.snapshot_date))
        total_fv_instances = len(seen_fv_keys)
        asof_fv_keys: set[tuple[str, str]] = set()

        # Walk event dates chronologically, forward-filling per source.
        # `latest_by_source` holds the most recent Snapshot(s) seen from
        # each source up to (and including) the current event date.
        #
        # v10 — Value is a LIST so multiple same-date publications from
        # the same source survive (e.g. MLB Pipeline drops Top 100 +
        # Org Top 30 both dated 2026-01-22). When a NEWER date arrives,
        # the list is replaced wholesale (the new date's set is the
        # most-recent for that source). compute_consensus_point handles
        # the duplicates by surfacing them as `extras` in per_source
        # without re-counting the FV.
        points: list[ConsensusPoint] = []
        latest_by_source: dict[str, list[Snapshot]] = {}
        for snap_date in sorted(by_date):
            for s in by_date[snap_date]:
                if s.fv is not None and s.source not in CONSTANT_ANCHOR_SOURCES:
                    asof_fv_keys.add((s.source, s.snapshot_date))
                prev_list = latest_by_source.get(s.source)
                if not prev_list:
                    latest_by_source[s.source] = [s]
                    continue
                prev_date = prev_list[0].snapshot_date
                if s.snapshot_date > prev_date:
                    # Strictly newer snapshot — replace the list.
                    latest_by_source[s.source] = [s]
                elif s.snapshot_date == prev_date:
                    # Same date — append as supplementary publication.
                    # Skip if it's identical to one already in the list
                    # (forward-fill repeats the same snapshot many times).
                    already = any(
                        (e.interval_label == s.interval_label and e.fv == s.fv
                         and e.rank == s.rank)
                        for e in prev_list
                    )
                    if not already:
                        latest_by_source[s.source].append(s)
                # Older snapshot than the latest — ignore.

            event_label = by_date[snap_date][-1].interval_label
            # Flatten the lists for compute_consensus_point's day_snaps.
            day_snaps_flat = [s for lst in latest_by_source.values() for s in lst]
            pt = compute_consensus_point(
                day_snaps_flat,
                event_date=snap_date,
                event_label=event_label,
                single_source_k=single_source_k,
                total_fv_instances=(
                    len(asof_fv_keys) if ASOF_FV_INSTANCES else total_fv_instances
                ),
                dropped_off_pairs=dropped_timeline.get(snap_date) or set(),
                source_weights=_SOURCE_WEIGHTS,
                grade_norm=grade_norm,
                org_ranked_rows=org_ranked_rows,
            )
            if pt is not None:
                points.append(pt)

        # Graduation logic: a player is considered graduated as soon as ANY
        # source (typically FanGraphs' graduates page) marks them so. Once
        # set, the status sticks — we don't "ungraduate" them if a stale
        # rank-only source still has them on a midseason list.
        status = "active"
        debut_date = None
        for s in sorted(player_snaps, key=lambda x: x.snapshot_date):
            if s.status == "debuted":
                status = "debuted"
                debut_date = s.snapshot_date
                break  # earliest debut signal wins
        if status != "debuted" and points and by_date:
            latest_day = sorted(by_date)[-1]
            statuses = [s.status for s in by_date[latest_day]]
            if "injured_list" in statuses:
                status = "injured_list"

        # Candle fields are populated after shrinkage is applied below.
        result.append(PlayerTimeseries(
            player_key=player_key, player_name=name,
            position=pos, org=org,
            points=points, status=status,
            debut_date=debut_date,
            fv_high=0.0, fv_high_label="—", fv_high_date="",
            fv_low=0.0,  fv_low_label="—",  fv_low_date="",
            fv_open=0.0, fv_close=0.0,
            fv_total_instances=total_fv_instances,
        ))

    # v7 — collapse duplicate (player_name) entries. FanGraphs CSV
    # ingest synthesizes `__noid`-suffixed player_keys whenever two
    # players collide on the FG id field; the result here ends up with
    # two PlayerTimeseries rows for the same person (e.g. Travis
    # Sykora, Chase DeLauter, Bryce Rainer). Merge them by preferring
    # the canonical (no-suffix) key and pooling points + graduation
    # state.
    #
    # v17 — Normalize names before dedup so "Homer Bush Jr." and
    # "Homer Bush, Jr." collapse to the same key. Common variants:
    # comma-separated suffix, period/no-period on suffix, smart-quote
    # apostrophes. Suffix variants (Jr/Sr/II/III) are preserved on the
    # kept entry; only the lookup key is normalized.
    def _normalize_name_for_dedup(name: str) -> str:
        if not name:
            return ""
        # Lowercase, strip commas + periods, collapse whitespace.
        cleaned = name.lower().replace(",", "").replace(".", "")
        # Normalize smart quotes to ascii.
        cleaned = cleaned.replace("’", "'").replace("‘", "'")
        return " ".join(cleaned.split())

    # A `_SAME_NAME_NOT_DUPES` allowlist carves out legit same-name pairs.
    # It is EMPTY, and the merge below is therefore unconditional on a name
    # collision. That is not free: same-name pairs DO surface in this corpus and
    # a merge pools one player's points onto another's consensus. v27 adds
    # same_name_collisions() as a REPORT so the population is visible; it
    # deliberately does not auto-merge or auto-split, because deciding which
    # same-name pairs are one person is an identity question, not a
    # consensus-engine question. Populate this set from that report, by hand.
    _SAME_NAME_NOT_DUPES: set[tuple[str, str]] = set()

    by_name: dict[str, PlayerTimeseries] = {}
    for p in result:
        norm_key = _normalize_name_for_dedup(p.player_name)
        canon = by_name.get(norm_key)
        if canon is None:
            by_name[norm_key] = p
            continue
        # Allowlist escape — same name BUT confirmed-distinct via
        # different player_keys (rare; not currently populated).
        if (canon.player_key, p.player_key) in _SAME_NAME_NOT_DUPES \
                or (p.player_key, canon.player_key) in _SAME_NAME_NOT_DUPES:
            by_name[f"{norm_key}#{p.player_key}"] = p
            continue
        # Prefer the entry whose key does NOT end with __noid.
        if not canon.player_key.endswith("__noid"):
            keep, drop = canon, p
        else:
            keep, drop = p, canon
        # Merge points — dedupe by (snapshot_date, interval_label) so
        # the same source-snap doesn't get double-counted.
        seen: set[tuple[str, str]] = set()
        merged: list = []
        for pt in (keep.points + drop.points):
            key = (pt.snapshot_date, getattr(pt, "interval_label", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(pt)
        merged.sort(key=lambda pt: pt.snapshot_date)
        keep.points = merged
        # Pull through the more authoritative status / debut_date.
        if keep.status != "debuted" and drop.status == "debuted":
            keep.status = drop.status
            keep.debut_date = drop.debut_date
        # Pool the per-snapshot FV-instance count so the "n instances"
        # badge reflects the full publication history.
        keep.fv_total_instances = (
            (keep.fv_total_instances or 0) + (drop.fv_total_instances or 0)
        )
        # Position / org — prefer the canonical entry's value but fill
        # in from the duplicate if canon is missing.
        if not keep.position and drop.position:
            keep.position = drop.position
        if not keep.org and drop.org:
            keep.org = drop.org
        by_name[norm_key] = keep
    result = list(by_name.values())

    # Population-prior Bayesian shrinkage was removed (2026-05): the
    # pull-toward-prior was compressing single-source prospects (90% of
    # actives) into a giant 40-FV cluster. compute_consensus_point now
    # produces the final consensus_fv values directly — multi-source
    # consensus = arithmetic mean (no shrinkage), single-source = the
    # targeted FV-35 pull (see SINGLE_SOURCE_PRIOR / SINGLE_SOURCE_K).
    # The legacy apply_shrinkage / compute_prior_mean_fv functions stay
    # defined for back-compat callers but are no longer wired in.
    for p in result:
        for attr, val in _candle_fields(p.points).items():
            setattr(p, attr, val)

    # v26 — Sort by (numeric FV, '+' flag) so 42+ ranks above 42 but
    # below 43. The '+' is the secondary key (only matters when FVs tie).
    result.sort(
        key=lambda p: (
            p.points[-1].consensus_fv if p.points else 0,
            1 if (p.points and getattr(p.points[-1], "consensus_fv_plus", False)) else 0,
        ),
        reverse=True,
    )
    return result


# ---------------------------------------------------------------------------
# Stock movement — *delta since the most recent prior update*
# ---------------------------------------------------------------------------

def stock_movement(player: PlayerTimeseries) -> dict:
    """v12 — Top movers calculated over the **trailing 1-year window**
    instead of the single most-recent update.

    Anchor: the latest snapshot's consensus_fv_raw.
    Prior:  the snapshot nearest to (latest_date − 365 days) that
            actually exists in the player's history. Falls back to the
            EARLIEST snapshot when the player has <1y of history so a
            recent debut still surfaces.

    Returns:
        {
            "direction": "up_strong" | "up" | "flat" | "down" | "down_strong" | "debuted",
            "delta": float,         # consensus_fv_raw delta (1y window)
            "from_label": str,      # consensus_fv_label at the anchor prior
            "to_label": str,        # consensus_fv_label at the latest
            "from_date": str,
            "to_date": str,
        }
    """
    if player.status == "debuted":
        return {
            "direction": "debuted",
            "delta": 0.0, "from_label": "—", "to_label": "—",
            "from_date": "", "to_date": "",
        }
    if len(player.points) < 2:
        return {
            "direction": "flat",
            "delta": 0.0, "from_label": "—", "to_label": "—",
            "from_date": "", "to_date": "",
        }
    from datetime import date, timedelta
    latest = player.points[-1]
    try:
        latest_d = date.fromisoformat(latest.snapshot_date)
    except (ValueError, TypeError):
        # Date parse failure → fall back to the prior-snapshot behavior.
        prior = player.points[-2]
    else:
        cutoff = latest_d - timedelta(days=365)
        # Pick the snapshot whose date is the CLOSEST to (latest - 365)
        # without going past `latest`. Iterate from oldest forward; the
        # first snap >= cutoff is the one we want (anything earlier
        # would over-extend the window). Falls back to the earliest
        # snapshot when no snap clears the cutoff.
        prior = player.points[0]
        for pt in player.points[:-1]:
            try:
                pt_d = date.fromisoformat(pt.snapshot_date)
            except (ValueError, TypeError):
                continue
            if pt_d <= cutoff:
                prior = pt   # keep walking forward while still ≤ cutoff
            else:
                # First snap past the cutoff: keep `prior` as the last
                # one that was AT-OR-BEFORE the cutoff (anchor closest
                # to 1y back from current). Stop walking.
                break
    delta = latest.consensus_fv_raw - prior.consensus_fv_raw
    if delta >= 4:
        direction = "up_strong"
    elif delta >= 1.5:
        direction = "up"
    elif delta <= -4:
        direction = "down_strong"
    elif delta <= -1.5:
        direction = "down"
    else:
        direction = "flat"
    return {
        "direction": direction,
        "delta": round(delta, 2),
        "from_label": prior.consensus_fv_label,
        "to_label": latest.consensus_fv_label,
        "from_date": prior.snapshot_date,
        "to_date": latest.snapshot_date,
    }
