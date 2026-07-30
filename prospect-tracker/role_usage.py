# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Usage-based pitcher role correction (rule D).

Prospect pitcher role labels (SP / MIRP / SIRP) come from FanGraphs'
forward-projection via consensus._latest_meta, which publishes where a
prospect is EXPECTED to land long-term. No usage correction existed, so
a stretched-out starter still carrying a stale MIRP/SIRP projection kept
rendering as a reliever site-wide.

Rule D (data-validated): a MIRP/SIRP-labeled pitcher whose CURRENT-season
MiLB usage shows GS-share >= 0.50 AND IP per appearance >= 3.0 AND
IP >= 20 is really a starter. IP-per-appearance is the opener
discriminator: openers sit at <= ~1.2 IP/G, true starters at >= ~3.0.

The games/starts/innings read comes from the milb_history cache
(.cache/milb_stats/) strictly OFFLINE (fetch=False): this module never
touches the network, and any missing data leaves the label unchanged.
"""

from __future__ import annotations

# Rule D thresholds. Empirical margins from the 2026 MiLB spot-check:
# the rule flips 57 genuine stretched starters (e.g. Alex Clemmey,
# 19 G / 19 GS / 87 IP, IP/G 4.58) while keeping openers (e.g. Alex
# Cook, 28 G / 5 GS / 32 IP, IP/G 1.13). The 3.0 IP/G floor sits well
# clear of both clusters; the 20 IP floor screens early-season cameos.
GS_SHARE_MIN = 0.50
IP_PER_G_MIN = 3.0
IP_MIN = 20.0

# The relief-role labels rule D may override. Compound labels whose
# tokens all live in this set (e.g. "MIRP/SIRP") qualify too.
_RELIEF_ROLE_TOKENS = {"MIRP", "SIRP"}

# --- Rule D generalized (Phase 5.2, DEFAULT OFF) ---------------------------
# The owner ask is that GAMES STARTED decide starter-vs-reliever, which is
# rule D running in BOTH directions rather than only RP -> SP. The reverse
# direction is not symmetric with the forward one and must not be shipped as
# if it were:
#
#   * "GS-share >= 0.50 AND IP/G >= 3.0 AND IP >= 20" was validated as a
#     SUFFICIENT condition for "this arm is really a starter". Its NEGATION is
#     not a validated sufficient condition for "this arm is really a
#     reliever" - it also catches every swingman, every rehabbing starter on
#     a pitch count, and every tandem-rotation arm.
#   * So the reverse direction gets its own, deliberately STRICTER test, with
#     an UNADJUDICATED BAND between the two. GS-share in (0.25, 0.50), or a
#     reliever's GS-share paired with a starter's IP/G, returns None: usage
#     declines to rule and the FanGraphs designation stands.
#
# The opener guard survives unchanged and now runs the direction it always
# implied: an opener (high GS-share, ~1.1 IP/G) fails the SP test, and at
# GS-share <= 0.25 passes the RP test, which is the correct answer for an
# opener. Between 0.25 and 0.50 he keeps his published label.
RP_GS_SHARE_MAX = 0.25

# Labels the reverse direction may overwrite. Split three ways because the
# blast radius differs per group (see docs/efv-2026-07-30/POSITION_ROLE_GATE.md):
#   _STARTER_ROLE_TOKENS  SP -> RP puts a row INTO efv_score._RP_DESIGNATIONS.
#   _ROLELESS_PITCHER_TOKENS  a handedness-only or bare-P label carries no role
#                         at all, so usage is strictly more information than
#                         what is there now - but P -> RP still enters the RP set.
_STARTER_ROLE_TOKENS = {"SP"}
_ROLELESS_PITCHER_TOKENS = {"P", "RHP", "LHP"}

# The label emitted when usage says reliever. Generic "RP" rather than a
# guessed SIRP/MIRP split: choosing between single- and multi-inning would need
# an IP/G cut nobody has validated, and "RP" is already a member of
# efv_score._RP_DESIGNATIONS, so the downstream semantics are exact.
_RP_LABEL = "RP"

# MASTER SWITCH. With it OFF, usage_position_override behaves EXACTLY as shipped
# rule D (RP -> SP only) and this module changes no served number.
#
# TURNED ON 2026-07-30 by OWNER DECISION, with the ship mechanics attached in the
# same commit (storage.BOARD_RANK_BASIS_EPOCH 2026-07-30, and the board basis
# fingerprint EXTENDED to name this switch - see storage.board_basis_fingerprint;
# role resolution is now a board-ordering input, and a fingerprint only guards what
# it names).
#
# Blast radius RE-MEASURED on the 2026-07-30 tree before the flip (not inherited
# from the pre-registration; the nightly regen had moved the artifacts). Full record
# in docs/efv-2026-07-30/POSITION_ROLE_GATE.md PART 3:
#   * regression on the shipped direction: the same 103 arms flip, zero disagreements
#   * 1,269 label changes; 871 rows ENTER efv_score._RP_DESIGNATIONS, 398 gain SP
#   * of those 871, exactly 3 trigger the reliever ceiling (tink_hence, nick_frasso,
#     joe_glassey) and ZERO sit inside the board top 300 (best rank 304)
#   * 5 rows change surplus dollars at all (the rest price at $0 either way)
#   * 0 spotlights change: 546 rows newly meet the RP-age-23 disqualifier and every
#     one of them already failed the FV>=45 floor that gate sits behind
# The one genuinely consequential row is Tink Hence (19 G / 3 GS / 20.3 IP), and the
# flip is TRUE of him.
USAGE_ROLE_BOTH_DIRECTIONS = True


def role_resolution_mode() -> str:
    """Short identity of how pitcher roles are resolved, for the board-basis
    fingerprint (storage.board_basis_fingerprint).

    The role string decides membership of efv_score._RP_DESIGNATIONS, which gates
    the reliever-ceiling haircut on the model WAR leg, which is the board number.
    So the RESOLUTION MODE is part of the board's identity in exactly the way the
    grade field, the side scale and the outcome curve already are. Naming it here
    means flipping the switch back, or widening the reversible-label set, fails the
    coherence test until a human bumps the epoch - which is the whole point of a
    fingerprint that only guards what it names.

    Deliberately a MODE name and not a hash of the thresholds: the thresholds are
    already pinned by test_role_usage / test_position_role_phase5, and a threshold
    tweak that moves no label should not force an epoch bump."""
    return "usage_both" if USAGE_ROLE_BOTH_DIRECTIONS else "usage_rp_to_sp"


def starter_by_usage(g, gs, ip) -> bool:
    """Rule D: is this season line starter-shaped?

    True when GS-share >= GS_SHARE_MIN (0.50) AND IP/G >= IP_PER_G_MIN
    (3.0) AND IP >= IP_MIN (20). Empirical margins: stretched starters
    (Clemmey 19 G / 19 GS / 87 IP -> shares 1.00 / 4.58 IP per G) clear
    every gate with room; openers (Cook 28 G / 5 GS / 32 IP -> 0.18 /
    1.13) fail two of three. IP-per-appearance is the opener
    discriminator (openers <= ~1.2, starters >= ~3.0). Missing or
    non-numeric inputs return False (never flip on bad data).
    """
    try:
        g_f = float(g)
        gs_f = float(gs)
        ip_f = float(ip)
    except (TypeError, ValueError):
        return False
    if g_f <= 0 or ip_f < IP_MIN:
        return False
    return (gs_f / g_f) >= GS_SHARE_MIN and (ip_f / g_f) >= IP_PER_G_MIN


def reliever_by_usage(g, gs, ip) -> bool:
    """The reverse of rule D: is this season line UNAMBIGUOUSLY relief-shaped?

    True only when IP >= IP_MIN (20) AND GS-share <= RP_GS_SHARE_MAX (0.25)
    AND IP/G < IP_PER_G_MIN (3.0). Both share and length must agree, so a
    long-relief swingman (few starts, 3+ IP an outing) and a tandem starter
    (starts a third of the time) are NOT called relievers - they fall in the
    unadjudicated band and keep their published label.

    Deliberately NOT the negation of starter_by_usage. Missing or non-numeric
    inputs return False (never flip on bad data).
    """
    try:
        g_f = float(g)
        gs_f = float(gs)
        ip_f = float(ip)
    except (TypeError, ValueError):
        return False
    if g_f <= 0 or ip_f < IP_MIN:
        return False
    return (gs_f / g_f) <= RP_GS_SHARE_MAX and (ip_f / g_f) < IP_PER_G_MIN


def usage_role(g, gs, ip) -> str | None:
    """"SP" / "RP" / None - what the usage line alone says the role is.

    None is a first-class answer meaning "usage declines to rule": no line, too
    few innings, or a shape inside the unadjudicated swingman band. Callers
    fall back to the published designation on None; they must never read it as
    a reliever.
    """
    if starter_by_usage(g, gs, ip):
        return "SP"
    if reliever_by_usage(g, gs, ip):
        return _RP_LABEL
    return None


def _ip_outs(ip) -> int:
    """Baseball innings notation to outs ('.1' / '.2' are thirds).

    The StatsAPI ships inningsPitched as a string like '87.1' (87 and
    one third). Summing across levels must happen in outs, not naive
    floats ('40.2' + '40.2' is 81.1, not 80.4).
    """
    if ip is None:
        return 0
    try:
        s = str(ip).strip()
        if "." in s:
            whole, frac = s.split(".", 1)
            return int(whole or 0) * 3 + int(frac[:1] or 0)
        return int(s) * 3
    except (TypeError, ValueError):
        return 0


def current_season_pitching(mlbam, season) -> dict | None:
    """Current-season MiLB pitching usage {g, gs, ip} for one mlbam id.

    Reads the milb_history cache OFFLINE (fetch=False; returns whatever
    is on disk, never the network) and sums games / starts / innings
    across every MiLB level for `season`. MLB rows are excluded: the
    rule corrects MiLB-usage-vs-projection drift, and player_index rows
    at level 'MLB' (sport 1) are skipped. Returns None when the cache
    holds no MiLB pitching row for the player (uncached season, hitter,
    or no innings yet).
    """
    try:
        mlbam_i = int(mlbam)
        season_i = int(season)
    except (TypeError, ValueError):
        return None
    try:
        import milb_history
    except ImportError:
        return None
    try:
        rows = milb_history.player_index(season_i, "pitching",
                                         fetch=False).get(mlbam_i) or []
    except Exception:  # noqa: BLE001 - cache read must never propagate
        return None
    g = gs = outs = 0
    found = False
    for r in rows:
        if r.get("level") == "MLB":
            continue
        found = True
        try:
            g += int(r.get("g") or 0)
        except (TypeError, ValueError):
            pass
        try:
            gs += int(r.get("gs") or 0)
        except (TypeError, ValueError):
            pass
        outs += _ip_outs(r.get("ip"))
    if not found:
        return None
    return {"g": g, "gs": gs, "ip": round(outs / 3.0, 2)}


def usage_position_override(position, mlbam, season, both_directions=None):
    """Rule D applied to a consensus position label.

    DEFAULT (both_directions falsy): returns "SP" when `position` is a
    relief-role label (MIRP / SIRP / a slash-combo of the two,
    case-insensitive) AND the player's current-season MiLB usage is
    starter-shaped per starter_by_usage. Every other case (non-relief
    label, missing mlbam, uncached season, reliever-shaped usage)
    returns the input unchanged. Defensive by construction: no data ever
    flips a label.

    BOTH-DIRECTIONS (Phase 5.2, `both_directions=True` or the module
    switch USAGE_ROLE_BOTH_DIRECTIONS): usage becomes the PRIMARY role
    source for pitchers, per the owner ask that games started decide
    starter-vs-reliever. On top of the default behaviour it also
    overwrites an "SP" label with "RP" on unambiguously relief-shaped
    usage, and resolves the role-less pitcher labels ("P", "RHP", "LHP")
    in either direction. The published designation remains the fallback
    for every row usage_role declines to rule on.

    ON since 2026-07-30 (owner decision). The reverse direction moves
    board output - an "RP" label is a member of
    efv_score._RP_DESIGNATIONS and therefore eligible for the
    reliever-ceiling haircut - so the flip shipped with a
    BOARD_RANK_BASIS_EPOCH bump and a board-basis fingerprint that NAMES
    the role-resolution mode. Blast radius measured in
    docs/efv-2026-07-30/POSITION_ROLE_GATE.md.
    """
    if both_directions is None:
        both_directions = USAGE_ROLE_BOTH_DIRECTIONS
    if not position or mlbam is None:
        return position
    tokens = [t.strip().upper() for t in str(position).split("/") if t.strip()]
    if not tokens:
        return position
    tokset = set(tokens)
    is_relief = tokset <= _RELIEF_ROLE_TOKENS
    reversible = bool(both_directions) and (
        tokset <= _STARTER_ROLE_TOKENS or tokset <= _ROLELESS_PITCHER_TOKENS)
    if not is_relief and not reversible:
        return position
    line = current_season_pitching(mlbam, season)
    if not line:
        return position
    role = usage_role(line.get("g"), line.get("gs"), line.get("ip"))
    if role is None:
        return position
    if is_relief:
        # Shipped rule D: relief label, starter usage -> SP. Relief usage
        # on a relief label is a confirmation, not a change.
        return "SP" if role == "SP" else position
    if role == "SP" and tokset <= _STARTER_ROLE_TOKENS:
        return position          # already SP, nothing to say
    return role
