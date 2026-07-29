# scratch lab (lane: discover) -- PRE-REGISTERED theory-driven archetypes.
#
# These definitions are fixed BEFORE any outcome is inspected. Every threshold is
# either a fixed scouting-scale constant (20-80 grades) or a fixed level-relative
# rate constant. NONE is tuned on outcomes, and none is a quantile of the test
# fold. Buckets are evaluated in the order listed, first match wins, so the
# partition is exhaustive and mutually exclusive.
#
# HITTERS
#  H1 SPEED_FIRST_NO_POWER   the Bradfield class. Elite run tool, no game power,
#                            at-or-below-level ISO. Hypothesis: over-graded, because
#                            speed and defense carry a low WAR ceiling once the bat
#                            fails to play, and the model prices tool_speed +1.
#  H2 OLD_FOR_LEVEL_GRINDER  >= 1 year old for level at AA/AAA with sub-level OPS.
#                            Hypothesis: over-graded (the owner's stated concern).
#  H3 POWER_ONLY_SWING_MISS  55+ game power with worse-than-level whiffs.
#                            Hypothesis: over-graded by scouts, but eFV already
#                            omits power on purpose, so possibly already priced.
#  H4 CONTACT_NO_POWER_SLAP  better-than-level contact, below-level ISO, <= 45 power.
#                            Hypothesis: over-graded (empty batting average).
#  H5 YOUNG_AND_TOOLSY       >= 1 year young for level with a 55+ speed or raw-power tool.
#                            Hypothesis: under-graded.
#  H6 POLISHED_COLLEGE_PERF  college bat performing above level at A+/AA/AAA.
#                            Hypothesis: under-graded (fast-mover discount).
#  H7 PROJECTABLE_TEEN_FRAME <= 19.5 at complex/A ball. Hypothesis: high variance.
#  H8 CATCHER_DEF_FIRST      catcher with a 50+ field tool. Hypothesis: under-graded
#                            (the model has no catcher-defense term).
#  H9 OTHER
#
# PITCHERS
#  P1 POWER_ARM_NO_COMMAND   60+ fastball, worse-than-level walks. over-graded?
#  P2 OLD_FOR_LEVEL_ORG_ARM  >= 1 year old for level at AA/AAA. over-graded?
#  P3 PITCHABILITY_LOW_VELO  <= 50 fastball, better-than-level walks, no bat-missing.
#  P4 YOUNG_HIGH_K           >= 1 year young for level with better-than-level Ks.
#  P5 POLISHED_COLLEGE_SP    college arm at A+/AA/AAA with better-than-level ERA.
#  P6 PROJECTABLE_TEEN_ARM   <= 19.5 at complex/A.
#  P7 OTHER
from __future__ import annotations


def theory_hit(f, pos):
    p = (pos or "").split("/")[0].strip().upper()
    if f["tool_speed"] >= 60 and f["tool_game_pwr"] <= 40 and f["iso_rel"] <= 0:
        return "H1_SPEED_FIRST_NO_POWER"
    if f["age_rel_level"] >= 1.0 and f["level_rank"] >= 4 and f["ops_rel"] <= 0:
        return "H2_OLD_FOR_LEVEL_GRINDER"
    if f["tool_game_pwr"] >= 55 and f["k_rel"] >= 0.03:
        return "H3_POWER_ONLY_SWING_MISS"
    if f["k_rel"] <= -0.03 and f["iso_rel"] <= -0.02 and f["tool_game_pwr"] <= 45:
        return "H4_CONTACT_NO_POWER_SLAP"
    if f["age_rel_level"] <= -1.0 and (f["tool_speed"] >= 55 or f["tool_raw_pwr"] >= 55):
        return "H5_YOUNG_AND_TOOLSY"
    if f["is_college"] >= 0.5 and f["ops_rel"] >= 0.05 and f["level_rank"] >= 3:
        return "H6_POLISHED_COLLEGE_PERF"
    if f["age"] <= 19.5 and f["level_rank"] <= 2:
        return "H7_PROJECTABLE_TEEN_FRAME"
    if p == "C" and f["tool_field"] >= 50:
        return "H8_CATCHER_DEF_FIRST"
    return "H9_OTHER"


def theory_pit(f, pos=None):
    if f["tool_fb"] >= 60 and f["bb_rel"] >= 0.02:
        return "P1_POWER_ARM_NO_COMMAND"
    if f["age_rel_level"] >= 1.0 and f["level_rank"] >= 4:
        return "P2_OLD_FOR_LEVEL_ORG_ARM"
    if f["tool_fb"] <= 50 and f["bb_rel"] <= -0.01 and f["k_rel"] <= 0:
        return "P3_PITCHABILITY_LOW_VELO"
    if f["age_rel_level"] <= -1.0 and f["k_rel"] >= 0.03:
        return "P4_YOUNG_HIGH_K"
    if f["is_college"] >= 0.5 and f["level_rank"] >= 3 and f["era_rel"] <= 0:
        return "P5_POLISHED_COLLEGE_SP"
    if f["age"] <= 19.5 and f["level_rank"] <= 2:
        return "P6_PROJECTABLE_TEEN_ARM"
    return "P7_OTHER"
