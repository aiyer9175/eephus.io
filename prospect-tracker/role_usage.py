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


def usage_position_override(position, mlbam, season):
    """Rule D applied to a consensus position label.

    Returns "SP" when `position` is a relief-role label (MIRP / SIRP /
    a slash-combo of the two, case-insensitive) AND the player's
    current-season MiLB usage is starter-shaped per starter_by_usage.
    Every other case (non-relief label, missing mlbam, uncached season,
    reliever-shaped usage) returns the input unchanged. Defensive by
    construction: no data ever flips a label.
    """
    if not position or mlbam is None:
        return position
    tokens = [t.strip().upper() for t in str(position).split("/") if t.strip()]
    if not tokens or not set(tokens) <= _RELIEF_ROLE_TOKENS:
        return position
    line = current_season_pitching(mlbam, season)
    if not line:
        return position
    if starter_by_usage(line.get("g"), line.get("gs"), line.get("ip")):
        return "SP"
    return position
