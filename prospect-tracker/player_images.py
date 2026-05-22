"""Image-URL helpers for the Draft + Overseas sections.

All functions are pure URL builders — no network I/O, no caching.
The frontend `<img>` tags use a `loading="lazy"` + `onerror=` fallback
chain so a 404 just degrades to text-only display.

Three families:
  * `player_headshot_url(player)` — best-effort headshot.
       1. MLB.com image CDN by mlbam_id (drafted / signed players)
       2. FG player-page photo by fg_player_id (amateur / overseas pros)
       3. None — frontend renders a colored initial chip instead
  * `college_logo_url(school)` — ESPN NCAA team logo by school name
       Stable URL pattern: https://a.espncdn.com/i/teamlogos/ncaa/500/<teamId>.png
       Backed by a static name→teamId map covering ~90% of D-1 power
       conferences. Returns None for HS players / D-3 / unknown schools.
  * `country_flag_svg_url(country_code)` — flagcdn.com SVG flag

Designed to be safe to call on every prospect during export without
slowing things down; the resulting URLs are evaluated lazily by the
browser.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Headshots
# ---------------------------------------------------------------------------

# MLB.com headshot CDN. The `d_people:generic:headshot:67:current.png`
# default fallback is what MLB.com serves for prospects without a photo
# yet — kicks in transparently when the player ID has no headshot.
_MLB_HEADSHOT_TEMPLATE = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/"
    "d_people:generic:headshot:67:current.png/"
    "w_213,q_auto:best/v1/people/{mlbam}/headshot/67/current"
)

# FG player photo. Observed at the URL pattern below for ranked
# prospects; some 404 (small sample / older entries) — the <img>'s
# onerror fallback handles that gracefully.
_FG_PHOTO_TEMPLATE = "https://www.fangraphs.com/players/photo/{fg_id}.jpg"


def player_headshot_url(player: dict | None) -> str | None:
    """Return a best-effort headshot URL or None.

    Reads `mlbam_id` (preferred) then `fg_player_id` from the player
    dict. Either field missing → falls through to the next; both
    missing → returns None."""
    if not player:
        return None
    mlbam = player.get("mlbam_id")
    if mlbam:
        try:
            return _MLB_HEADSHOT_TEMPLATE.format(mlbam=int(mlbam))
        except (TypeError, ValueError):
            pass
    fg_id = player.get("fg_player_id")
    if fg_id and isinstance(fg_id, str) and fg_id.strip():
        return _FG_PHOTO_TEMPLATE.format(fg_id=fg_id.strip())
    return None


# ---------------------------------------------------------------------------
# College logos
# ---------------------------------------------------------------------------

_ESPN_NCAA_TEMPLATE = "https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png"

# School name → ESPN team ID. Covers Power 5 + most major D-1 programs
# that produce regular MLB draftees. Names use the form FG ships in the
# draft CSV's School column. Add entries as new schools land in the
# data — the lookup is fail-soft.
_COLLEGE_TEAM_IDS: dict[str, int] = {
    # SEC
    "Alabama":         333,
    "Arkansas":        8,
    "Auburn":          2,
    "Florida":         57,
    "Georgia":         61,
    "Kentucky":        96,
    "LSU":             99,
    "Mississippi State": 344,
    "Missouri":        142,
    "Ole Miss":        145,
    "South Carolina":  2579,
    "Tennessee":       2633,
    "Texas":           251,
    "Texas A&M":       245,
    "Vanderbilt":      238,
    "Oklahoma":        201,
    # ACC
    "Boston College":  103,
    "Clemson":         228,
    "Duke":            150,
    "Florida State":   52,
    "Georgia Tech":    59,
    "Louisville":      97,
    "Miami":           2390,    # Miami (FL)
    "NC State":        152,
    "North Carolina":  153,
    "Notre Dame":      87,
    "Pittsburgh":      221,
    "Stanford":        24,
    "Syracuse":        183,
    "Virginia":        258,
    "Virginia Tech":   259,
    "Wake Forest":     154,
    "California":      25,      # Cal
    "Cal":             25,
    "SMU":             2567,
    # Big 12
    "Arizona":         12,
    "Arizona State":   9,
    "Baylor":          239,
    "BYU":             252,
    "Cincinnati":      2132,
    "Houston":         248,
    "Iowa State":      66,
    "Kansas":          2305,
    "Kansas State":    2306,
    "Oklahoma State":  197,
    "TCU":             2628,
    "Texas Tech":      2641,
    "UCF":             2116,
    "Utah":            254,
    "West Virginia":   277,
    # Big Ten
    "Illinois":        356,
    "Indiana":         84,
    "Iowa":            2294,
    "Maryland":        120,
    "Michigan":        130,
    "Michigan State":  127,
    "Minnesota":       135,
    "Nebraska":        158,
    "Northwestern":    77,
    "Ohio State":      194,
    "Oregon":          2483,
    "Oregon State":    204,
    "Penn State":      213,
    "Purdue":          2509,
    "Rutgers":         164,
    "UCLA":            26,
    "USC":             30,
    "Washington":      264,
    "Wisconsin":       275,
    # Sun Belt / AAC / etc — common draft pipelines
    "Coastal Carolina": 324,
    "ECU":             151,
    "East Carolina":   151,
    "Memphis":         235,
    "South Florida":   58,
    "Tulane":          2655,
    "UAB":             5,
    "UConn":           41,
    "App State":       2026,
    "Appalachian State": 2026,
    "James Madison":   256,
    "Marshall":        276,
    "Old Dominion":    295,
    # Other notable feeders
    "Rice":            242,
    "Wichita State":   2724,
    "Long Beach State": 299,
    "Cal State Fullerton": 2239,
    "UC Santa Barbara": 2540,
    "UC Irvine":       2542,
    "Fresno State":    278,
    "San Diego State": 21,
    "Hawaii":          62,
    "Liberty":         2335,
    "Dallas Baptist":  2169,
    "Sam Houston":     2534,
    "Troy":            2653,
    "Vandy":           238,
}

# A few common alias variations FG uses interchangeably with the
# canonical school name above.
_SCHOOL_ALIASES = {
    "Mississippi":            "Ole Miss",
    "Mississippi (Ole Miss)": "Ole Miss",
    "USC Trojans":            "USC",
    "U. of Miami":            "Miami",
    "Miami (FL)":             "Miami",
    "U. of California":       "California",
    "Cal Berkeley":           "California",
    "Penn St.":               "Penn State",
    "Ohio St.":               "Ohio State",
}


def _normalize_school(school: str) -> str:
    """Strip parens, trailing 'University'/'College', normalize whitespace."""
    if not school:
        return ""
    s = school.strip()
    s = re.sub(r"\s*\(.*?\)\s*$", "", s).strip()    # strip "(FL)" "(CA)" etc.
    s = re.sub(r"\s+", " ", s)
    return _SCHOOL_ALIASES.get(s, s)


def college_logo_url(school: str | None) -> str | None:
    """Return an ESPN NCAA logo URL for a known D-1 program, or None.

    HS players + D-3 / unknown schools → None (frontend renders a
    colored initial chip in that case)."""
    if not school:
        return None
    name = _normalize_school(school)
    # HS players: any "HS" / "High School" in the string → no logo.
    if re.search(r"\b(HS|High School)\b", name, re.IGNORECASE):
        return None
    team_id = _COLLEGE_TEAM_IDS.get(name)
    if not team_id:
        return None
    return _ESPN_NCAA_TEMPLATE.format(team_id=team_id)


# ---------------------------------------------------------------------------
# Country flags (used by overseas + any drafted player with a non-US country)
# ---------------------------------------------------------------------------

_FLAGCDN_TEMPLATE = "https://flagcdn.com/{cc}.svg"


def country_flag_svg_url(country_code: str | None) -> str | None:
    """Return a flagcdn.com SVG URL or None when the code is missing."""
    if not country_code:
        return None
    cc = country_code.strip().lower()
    if not re.fullmatch(r"[a-z]{2}", cc):
        return None
    return _FLAGCDN_TEMPLATE.format(cc=cc)
