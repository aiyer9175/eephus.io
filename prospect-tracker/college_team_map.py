# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Verified CollegeSavant team-code map (owner answer M20-1, census M03-11).

CollegeSavant rows carry a team code built from the school and the mascot
("TEX_LON", "OSU_BUC"). The old collegesavant/team_names.js named a code from
hand dictionaries, composing a school part with a three-letter mascot part, so
it printed "Arizona State Wildcats" for Arizona, "Nevada Wolverines" and
"Georgia Panthers" for Georgia State. This module generates team_names.js and
names a code only when the name is verified:

  learned+ncaa   the school the code's own players were drafted from
                 (college_stats._learn_code_schools: at least 2 votes and a
                 60% share) is on the NCAA D-I list AND fits the code's
                 school letters. Two independent sources agree.
  dict+ncaa      no usable learned school; the hand dictionary's per-code
                 entry (or its school-letters entry) names exactly one NCAA
                 D-I school, that school fits the code's letters, and, for a
                 school-letters entry, it is the ONLY D-I school those letters
                 fit. One exact match, noted per row.
  learned+dict   a non-D-I program: the learned school and the hand
                 dictionary's per-code entry are the same school.

Every other code prints as the code (commit 2add0c0a). The printed name is the
school only: no mascot part is verified by either source. ESPN NCAA team ids
for logos come from player_images._COLLEGE_TEAM_IDS, the map the PROSPX draft
cards read. Provenance per code is written to
data/collegesavant_team_map.json.

Run: python college_team_map.py   (offline: reads the cached NCAA list)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
CS = ROOT / "collegesavant"
NCAA_YEAR = 2026

LEGACY_TEAM_CODE_NAMES = {
    "ALV_CCO": "Alvin Community College",
    "ANG_STA": "Angelo State University",
    "BOC_EAG": "Boston College",
    "BUT_COL1": "Butler Community College",
    "CAT_IND": "Catawba College",
    "CSD_TRI": "UC San Diego",
    "CUM_PAT": "Cumberland College",
    "CYP_CHR": "Cypress College",
    "DIX_STE": "Utah Tech University",
    "FAI_STA": "Fairfield University",
    "FGCU": "Florida Gulf Coast",
    "FRA_MAR1": "Francis Marion University",
    "GAR_RUN": "Gardner Webb University",
    "Gol_W": "Gold West College",
    "HOL_CRU": "Holy Cross",
    "ILL_ILL": "Illinois Fighting Illini",
    "ILL_WES": "Illinois Wesleyan College",
    "IU": "Indiana Hoosiers",
    "IOW_CEN": "Iowa Central Community College",
    "IOW_HAW": "Iowa Hawkeyes",
    "IWC": "Incarnate Word",
    "JAC_GAM": "Jacksonville State",
    "JOH_LOG": "John A. Logan College",
    "JUD": "Jacksonville University",
    "KS_GF": "Kent State",
    "LIN_CCW": "Linfield University",
    "LIN_MEM": "Lincoln Memorial University",
    "LIN_TCO": "Lincoln Trail College",
    "MAR_TER": "Maryland Terrapins",
    "MIC_SPA": "Michigan State Spartans",
    "MIC_WOL": "Michigan Wolverines",
    "MID_GEO": "Middle Georgia State",
    "MIN_GOL": "Minnesota Golden Gophers",
    "MIS_COL1": "Mississippi College",
    "MOU_OLV": "Mount Olive University",
    "MSM_MTN": "Mt. St. Mary's",
    "MSU_BDG": "Mississippi State",
    "MT": "Memphis University",
    "NCB": "Northern Colorado University",
    "NEB": "Nebraska Cornhuskers",
    "NOK_NOR": "Northern Kentucky University",
    "NOR_CAT": "Northwestern Wildcats",
    "ORE_DUC": "Oregon Ducks",
    "OSU_BUC": "Ohio State Buckeyes",
    "PAR_JUN": "Paris Junior College",
    "PAT_HEN": "Patrick & Henry Community College",
    "PEN_NIT": "Penn State Nittany Lions",
    "PEP_WAV": "Pepperdine University",
    "PER_STA": "Peru State College",
    "PRE_BLH": "Presbyterian College",
    "PUR_BOI": "Purdue Boilermakers",
    "QUN_RYL": "Queens University Charlotte",
    "RAD_HIG": "Radford University",
    "RIV_CIT": "Riverside City College",
    "RUT_SCA": "Rutgers Scarlet Knights",
    "SAC_PIO": "Sacred Heart University",
    "SAN_AZT": "San Diego State University",
    "SAN_BRO": "Santa Clara College",
    "SAN_DON": "University of San Francisco",
    "SAN_GAU": "UC Santa Barbara",
    "SAN_TOR": "University of San Diego",
    "SBU_SEA": "Stony Brook University",
    "SIU_SAL": "Southern Illinois University",
    "SLC_CCB": "Salt Lake Community College",
    "SOU_GAM": "University of South Carolina",
    "SOU_GOL": "Southern Mississippi",
    "SOU_IND16": "Southern Indiana",
    "SOU_TRO": "USC Trojans",
    "SOU_WES": "Southwestern University",
    "ST._EDW": "St. Edwards University",
    "STB_BON": "St. Bonaventure",
    "STE_HAT": "Stetson University",
    "STE_LUM": "Stephen F. Austin",
    "STM_RAT": "St. Mary's University Texas",
    "TCU_HFG": "TCU",
    "TEM_LEO": "Temple College",
    "THO_M": "St. Thomas University",
    "TOL_ROC": "Toledo University",
    "TRO_TRJ": "Troy University",
    "TUS_PIO": "Tusculum University",
    "UCF_KNI": "UCF",
    "UCLA": "UCLA",
    "UMASS_RIV": "UMass Lowell",
    "UMA_AMH": "Umass Amherst",
    "UMBC_RET": "UMBC",
    "UNC_SEA": "UNC Wilmington",
    "UNI_NOR1": "Northwestern Ohio",
    "UNI_PIK": "UPike",
    "UNI_TEX": "UT Tyler",
    "USC_UPS": "USC Upstate",
    "UTA_UTE": "Utah",
    "UTR_VAQ": "UT Rio Grande Valley",
    "UTS_ROA": "UT San Antonio",
    "VAL_CRU": "Valparaiso University",
    "VIR_CAV": "Virginia",
    "VIR_KEY": "Virginia Military Institute",
    "VIR_TEC": "Virginia Tech",
    "VIR_WIS": "Virginia University at Wise",
    "WAK_DEA": "Wake Forest",
    "WAS_HUS": "Washington Huskies",
    "WCC": "Western Carolina",
    "WES_HIL": "Western Kentucky",
    "WES_MOU": "West Virginia",
    "WES_TEX": "West Texas A&M",
    "WHA_JUC": "Wharton County JUCO",
    "WIU_LEA": "Western Illinois",
    "WMI_BRO": "Western Michigan",
    "WM_TRI": "William & Mary",
    "WRI_RAI": "Wright State",
    "YSU_PEN": "Youngstown State",
}


LEGACY_SCHOOL_NAMES = {
    "ABI": "Abilene Christian",
    "AIR": "Air Force",
    "ALA": "Alabama",
    "ALB": "Albany",
    "ARI": "Arizona State",
    "ARK": "Arkansas",
    "AUB": "Auburn",
    "BAY": "Baylor",
    "BEL": "Belmont",
    "BGS": "Bowling Green",
    "BIN": "Binghamton",
    "BOS": "Boston College",
    "BRA": "Bradley",
    "BRO": "Brown",
    "BRY": "Bryant",
    "BYU": "BYU",
    "CAL": "California",
    "CAM": "Campbell",
    "CAN": "Canisius",
    "CAR": "Carson-Newman",
    "CEN": "Central Arkansas",
    "CHA": "Charlotte",
    "CIN": "Cincinnati",
    "CIT": "The Citadel",
    "CLE": "Clemson",
    "COA": "Coastal Carolina",
    "COL": "College of Charleston",
    "CON": "Connecticut",
    "CSU": "Cal State Bakersfield",
    "DAL": "Dallas Baptist",
    "DAR": "Dartmouth",
    "DAY": "Dayton",
    "DEL": "Delaware",
    "DUK": "Duke",
    "ECU": "East Carolina",
    "EKU": "Eastern Kentucky",
    "ELO": "Elon",
    "EMU": "Eastern Michigan",
    "EVA": "Evansville",
    "FAU": "Florida Atlantic",
    "FLA": "Florida",
    "FLO": "Florida State",
    "FOR": "Fordham",
    "FRE": "Fresno State",
    "GEO": "Georgia",
    "GIT": "Georgia Tech",
    "GON": "Gonzaga",
    "GRA": "Grand Canyon",
    "HAR": "Harvard",
    "HBU": "Houston Christian",
    "HOF": "Hofstra",
    "HOU": "Houston",
    "IND": "Indiana State",
    "ION": "Iona",
    "JMU": "James Madison",
    "KAN": "Kansas",
    "KEN": "Kennesaw State",
    "LAF": "Lafayette",
    "LAM": "Lamar",
    "LIB": "Liberty",
    "LIP": "Lipscomb",
    "LOU": "Louisville",
    "LOY": "Loyola Marymount",
    "LSU": "LSU",
    "MAI": "Maine",
    "MAR": "Marshall",
    "MCN": "McNeese",
    "MER": "Mercer",
    "MEX": "New Mexico",
    "MIA": "Miami",
    "MIL": "Milwaukee",
    "MIZ": "Missouri",
    "MON": "Monmouth",
    "MOR": "Morehead State",
    "MTSU": "Middle Tennessee",
    "MUR": "Murray State",
    "NAV": "Navy",
    "NEV": "Nevada",
    "NEW": "New Orleans",
    "NIC": "Nicholls",
    "NIU": "Northern Illinois",
    "NMS": "New Mexico State",
    "NOR": "North Carolina",
    "NOT": "Notre Dame",
    "OAK": "Oakland",
    "OHI": "Ohio",
    "OKL": "Oklahoma",
    "OLD": "Old Dominion",
    "OLE": "Ole Miss",
    "ORE": "Oregon",
    "PAC": "Pacific",
    "PEN": "Penn State",
    "RUT": "Rutgers",
    "SEA": "Seattle",
    "TEX": "Texas",
    "TEN": "Tennessee",
    "USC": "USC Upstate",
    "VIR": "Virginia",
    "WOF": "Wofford",
    "XAV": "Xavier",
}


LEGACY_MASCOT_NAMES = {
    "ACE": "Purple Aces",
    "AGG": "Aggies",
    "BEA": "Bears",
    "BIS": "Bison",
    "BLA": "Black Bears",
    "BLU": "Blue Raiders",
    "BOB": "Bobcats",
    "BOI": "Boilermakers",
    "BRA": "Braves",
    "BRU": "Bruins",
    "BUC": "Buccaneers",
    "BUL": "Bulldogs",
    "CAM": "Camels",
    "CAR": "Cardinals",
    "CAT": "Wildcats",
    "CHA": "Chanticleers",
    "COL": "Colonels",
    "COM": "Commodores",
    "COU": "Cougars",
    "COW": "Cowboys",
    "DUC": "Ducks",
    "DUK": "Dukes",
    "EAG": "Eagles",
    "FAL": "Falcons",
    "FLA": "Flames",
    "FLY": "Flyers",
    "GAE": "Gaels",
    "GAT": "Gators",
    "GRE": "Green Wave",
    "GRI": "Golden Griffins",
    "GWI": "George Washington",
    "HAW": "Hawkeyes",
    "HFG": "Horned Frogs",
    "HOY": "Hoyas",
    "HUS": "Huskies",
    "IRI": "Fighting Irish",
    "JAY": "Jayhawks",
    "LAN": "Lancers",
    "LEP": "Leopards",
    "LIO": "Lions",
    "LON": "Longhorns",
    "LOB": "Lobos",
    "MAV": "Mavericks",
    "MID": "Midshipmen",
    "MON": "Monarchs",
    "MUS": "Musketeers",
    "NIT": "Nittany Lions",
    "OWL": "Owls",
    "PAN": "Panthers",
    "PHO": "Phoenix",
    "PIR": "Pirates",
    "PRI": "Privateers",
    "RAC": "Racers",
    "RAM": "Rams",
    "RAZ": "Razorbacks",
    "REB": "Rebels",
    "RED": "Redhawks",
    "SCA": "Scarlet Knights",
    "SEM": "Seminoles",
    "SPA": "Spartans",
    "SUN": "Sun Devils",
    "TAR": "Tar Heels",
    "TER": "Terrapins",
    "TIG": "Tigers",
    "TRO": "Trojans",
    "UNI": "Panthers",
    "UNI2": "Panthers",
    "VOL": "Volunteers",
    "WAR": "Warhawks",
    "WIL": "Wildcats",
    "WOL": "Wolverines",
    "YEL": "Yellow Jackets",
}


# Mascot phrases a per-code dictionary entry may end with ("Nebraska
# Cornhuskers"); stripped before the school is matched, never printed.
_MASCOT_PHRASES = set(LEGACY_MASCOT_NAMES.values()) | {
    "Cornhuskers", "Fighting Illini", "Hoosiers", "Golden Gophers", "Buckeyes",
    "Boilermakers", "Scarlet Knights", "Nittany Lions", "Wolverines", "Spartans",
    "Hawkeyes", "Terrapins", "Huskies", "Trojans", "Ducks", "Wildcats",
}

# NCAA list abbreviations, expanded before matching ("Central Ark." ->
# "Central Arkansas"). "St." is State at the end of a name, Saint elsewhere.
_ABBR = {
    "ark.": "arkansas", "conn.": "connecticut", "mich.": "michigan", "ky.": "kentucky",
    "ill.": "illinois", "fla.": "florida", "ga.": "georgia", "tenn.": "tennessee",
    "miss.": "mississippi", "la.": "louisiana", "ala.": "alabama", "colo.": "colorado",
    "caro.": "carolina", "ind.": "indiana", "mo.": "missouri", "val.": "valley",
    "so.": "southern", "col.": "college", "u.": "university",
}

# Other names the same D-I school goes by in the draft store and the hand
# dictionary, keyed by the NCAA list's own spelling. Only same-institution
# names; a bare name two schools share ("St. Mary's", "St. Thomas") is left out.
_ALIASES = {
    "A&M-Corpus Christi": ["Texas A&M-Corpus Christi"],
    "App State": ["Appalachian State"],
    "Army West Point": ["Army"],
    "BYU": ["Brigham Young"],
    "CSU Bakersfield": ["Cal State Bakersfield"],
    "CSUN": ["Cal State Northridge"],
    "Cal St. Fullerton": ["Cal State Fullerton"],
    "Central Conn. St.": ["Central Connecticut"],
    "Col. of Charleston": ["College of Charleston"],
    "DBU": ["Dallas Baptist"],
    "ETSU": ["East Tennessee State"],
    "FDU": ["Fairleigh Dickinson"],
    "FGCU": ["Florida Gulf Coast"],
    "FIU": ["Florida International"],
    "Gardner-Webb": ["Gardner Webb"],
    "Hawaii": ["Hawai'i"],
    "Houston Christian": ["Houston Baptist"],
    "LIU": ["Long Island"],
    "LMU (CA)": ["Loyola Marymount", "LMU"],
    "LSU": ["Louisiana State"],
    "Lamar University": ["Lamar"],
    "Little Rock": ["Arkansas-Little Rock"],
    "Louisiana": ["Louisiana-Lafayette", "UL Lafayette"],
    "Massachusetts": ["UMass", "UMass Amherst"],
    "McNeese": ["McNeese State"],
    "Miami (FL)": ["Miami"],
    "Miami (OH)": ["Miami Ohio"],
    "Middle Tenn.": ["Middle Tennessee State", "MTSU"],
    "Mississippi Val.": ["Mississippi Valley State"],
    "Mount St. Mary's": ["Mt. St. Mary's", "Mount Saint Mary's"],
    "N.C. A&T": ["North Carolina A&T"],
    "NC State": ["North Carolina State"],
    "NIU": ["Northern Illinois"],
    "Nicholls": ["Nicholls State"],
    "Missouri": ["Mizzou"],
    "Ole Miss": ["Mississippi"],
    "Omaha": ["Nebraska-Omaha"],
    "Penn": ["Pennsylvania"],
    "Prairie View": ["Prairie View A&M"],
    "Presbyterian": ["Presbyterian College"],
    "Queens (NC)": ["Queens University Charlotte", "Queens"],
    "SFA": ["Stephen F. Austin"],
    "SIUE": ["SIU Edwardsville"],
    "Sam Houston": ["Sam Houston State"],
    "Seattle U": ["Seattle"],
    "South Fla.": ["USF"],
    "Southeast Mo. St.": ["SEMO"],
    "Southern California": ["USC"],
    "Southern Miss.": ["Southern Miss"],
    "St. John's (NY)": ["St. John's"],
    "TCU": ["Texas Christian"],
    "UAB": ["Alabama-Birmingham"],
    "UAlbany": ["Albany"],
    "UC Irvine": ["California-Irvine"],
    "UC Santa Barbara": ["California-Santa Barbara"],
    "UCF": ["Central Florida"],
    "UConn": ["Connecticut"],
    "UIC": ["Illinois-Chicago"],
    "UIW": ["Incarnate Word"],
    "ULM": ["Louisiana-Monroe"],
    "UMES": ["Maryland-Eastern Shore"],
    "UMass Lowell": ["Massachusetts-Lowell"],
    "UNCW": ["UNC Wilmington", "North Carolina-Wilmington"],
    "UNLV": ["Nevada-Las Vegas"],
    "UT Arlington": ["Texas-Arlington"],
    "UT Martin": ["Tennessee-Martin"],
    "UTRGV": ["UT Rio Grande Valley", "Texas-Rio Grande Valley"],
    "UTSA": ["UT San Antonio", "Texas-San Antonio"],
    "Utah Tech": ["Dixie State"],
    "VCU": ["Virginia Commonwealth"],
    "VMI": ["Virginia Military Institute"],
}

_STOP = {"of", "the", "at", "and", "university", "college"}


def _expand(name: str) -> str:
    """Spell out the NCAA list's abbreviations, lowercased."""
    words = (name or "").replace("&", " and ").replace("-", " ").split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw == "st.":
            out.append("state" if i == len(words) - 1 else "saint")
        else:
            out.append(_ABBR.get(lw, lw))
    return " ".join(out)


def _canon(name: str) -> str:
    """Matching key: expanded, punctuation and boilerplate words dropped. A
    state qualifier stays in the key ("St. Thomas (MN)" is not "St. Thomas")."""
    s = re.sub(r"[^a-z ]", " ", _expand(name))
    return "".join(w for w in s.split() if w not in ("university", "of", "the", "at"))


def _tokens(name: str) -> list[str]:
    s = re.sub(r"\([^)]*\)", " ", _expand(name))
    return [w for w in re.sub(r"[^a-z ]", " ", s).split() if w]


def _letters(code: str) -> str:
    """The code's school letters: its first part, letters only, lowercased."""
    return re.sub(r"[^a-z]", "", code.split("_")[0].lower())


def fits(code: str, names, loose: bool = True) -> bool:
    """True when the code's school letters can come from one of the names: a
    word of the name starts with them, or the name's initials (optionally with
    a U for University) do ("LSU", "UCF", "ETS"). loose also accepts the
    letters in order inside the name ("FLA", "GIT"), leading letters plus
    initials ("BOC") and initials plus mascot letters ("WCC"). The uniqueness
    test for a school-letters dictionary entry runs strict (word start or
    initials only), so a looser rule never makes a guess look unique."""
    p = _letters(code)
    if not p:
        return False
    for nm in names:
        toks = _tokens(nm)
        if any(t.startswith(p) for t in toks):
            return True
        ini = "".join(t[0] for t in toks if t not in _STOP)
        if any(x.startswith(p) for x in (ini, ini + "u", "u" + ini)):
            return True
        # Leading letters of the first word, then initials ("BOC" for Boston
        # College, "MSM" for Mount St. Mary's).
        if not loose:
            continue
        rest = "".join(t[0] for t in toks[1:])
        if toks and any((toks[0][:k] + rest).startswith(p) for k in range(1, len(toks[0]) + 1)):
            return True
        # Two or more initials, then mascot letters ("WCC" for Western
        # Carolina Catamounts, "NCB" for Northern Colorado Bears).
        if len(ini) >= 2 and p.startswith(ini):
            return True
        # The letters in order inside the name, from its first letter ("FLA"
        # for Florida, "GIT" for Georgia Tech).
        flat = "".join(t for t in toks if t not in _STOP)
        if flat and flat[0] == p[0] and _subseq(p, flat):
            return True
    return False


def _subseq(p: str, s: str) -> bool:
    it = iter(s)
    return all(ch in it for ch in p)


def ncaa_index(rows) -> dict:
    """canon name -> {ncaa, team_id, names}; every alias of a school keys it."""
    idx = {}
    for school, tid in rows:
        names = [school] + _ALIASES.get(school, [])
        rec = {"ncaa": school, "team_id": tid, "names": names}
        for n in names:
            idx.setdefault(_canon(n), rec)
    return idx


def _strip_mascot(name: str) -> str:
    for m in sorted(_MASCOT_PHRASES, key=len, reverse=True):
        if name.endswith(" " + m):
            return name[: -len(m) - 1]
    return name


def _legacy(code: str):
    """(school name, kind) from the hand dictionaries, kind 'code' for a
    per-code entry and 'letters' for a school-letters entry, else (None, None)."""
    if code in LEGACY_TEAM_CODE_NAMES:
        return _strip_mascot(LEGACY_TEAM_CODE_NAMES[code]), "code"
    parts = code.split("_")
    s = LEGACY_SCHOOL_NAMES.get(parts[0])
    if s and (len(parts) == 1 or parts[1] in LEGACY_MASCOT_NAMES):
        return s, "letters"
    return None, None


def _espn_id(names) -> int | None:
    from player_images import _COLLEGE_TEAM_IDS, _normalize_school
    by_canon = {_canon(k): v for k, v in _COLLEGE_TEAM_IDS.items()}
    for n in names:
        tid = _COLLEGE_TEAM_IDS.get(_normalize_school(n)) or by_canon.get(_canon(n))
        if tid:
            return tid
    return None


def verify_code(code: str, idx: dict, learned: str | None, siblings: dict | None = None) -> dict:
    """One code's verdict: {name, source, note, ncaa, espn_id} or {source: None}."""
    out = {"code": code, "name": None, "source": None, "note": None, "ncaa": None,
           "espn_id": None, "learned": learned}
    lrec = idx.get(_canon(learned)) if learned else None
    learned_ok = bool(lrec) and fits(code, lrec["names"] + [learned])
    if learned and lrec and not learned_ok:
        out["note"] = f"learned school {learned!r} does not fit the code letters; ignored"
    if learned_ok:
        out.update(name=learned, source="learned+ncaa", ncaa=lrec["ncaa"],
                   note=f"draft-roster vote {learned!r} is NCAA D-I {lrec['ncaa']!r}")
        out["espn_id"] = _espn_id(lrec["names"] + [learned])
        return out
    dname, kind = _legacy(code)
    if not dname:
        return out
    drec = idx.get(_canon(dname))
    if drec and fits(code, drec["names"] + [dname]):
        if kind == "letters":
            fitting = {r["ncaa"] for r in idx.values() if fits(code, r["names"], loose=False)}
            if fitting != {drec["ncaa"]}:
                out["note"] = (f"letters {_letters(code).upper()!r} fit {len(fitting)} D-I schools; "
                               f"dictionary {dname!r} not unique")
                return out
            # A non-D-I program can share the letters ("NAV_COL" beside
            # "NAV_MID"), so the letters must also belong to one payload code.
            if siblings and siblings.get(_letters(code), 0) > 1:
                out["note"] = (f"{siblings[_letters(code)]} payload codes share the letters "
                               f"{_letters(code).upper()!r}; dictionary {dname!r} not unique")
                return out
        # A learned school off the D-I list that names another program is a
        # conflict; a D-I learned school that failed the letters was a
        # transfer vote and is already ignored above.
        if learned and not lrec and _canon(learned) != _canon(dname):
            out["note"] = f"dictionary {dname!r} and learned {learned!r} disagree"
            return out
        out.update(name=dname, source="dict+ncaa", ncaa=drec["ncaa"],
                   note=(f"dictionary {'entry' if kind == 'code' else 'letters entry'} "
                         f"{dname!r} is NCAA D-I {drec['ncaa']!r}"
                         + ("" if kind == "code" else ", the only D-I school its letters fit")))
        out["espn_id"] = _espn_id(drec["names"] + [dname])
        return out
    if kind == "code" and learned and _canon(learned) == _canon(dname):
        out.update(name=dname, source="learned+dict",
                   note=f"draft-roster vote and dictionary entry agree on {dname!r} (not on the D-I list)")
        return out
    if out["note"] is None:
        out["note"] = (f"dictionary {dname!r} does not fit the code letters" if drec
                       else f"dictionary {dname!r} is not one NCAA D-I school")
    return out


def payload_codes() -> Counter:
    """Distinct team codes in the served hitter and pitcher payloads, with row counts."""
    import college_translation as ct
    c = Counter()
    for f, var in (("hitter_year_data.js", "window.HITTER_DATA"), ("pitcher_data.js", "window.PITCHER_DATA")):
        for r in ct._first_array(CS / f, var):
            code = (r.get("team") or "").strip()
            if code:
                c[code] += 1
    return c


def build(year: int = NCAA_YEAR) -> dict:
    import college_stats as cst
    rows = cst.d1_team_list(year, cache_only=True)
    if not rows:
        raise SystemExit(f"no cached NCAA D-I list for {year}; refusing to write an empty map")
    idx = ncaa_index(rows)
    learned = cst._learn_code_schools(cst._cs_universe())
    codes = payload_codes()
    siblings = Counter(_letters(c) for c in codes)
    table = [verify_code(c, idx, learned.get(c), siblings) for c in sorted(codes)]
    for t in table:
        t["rows"] = codes[t["code"]]
    mapped = [t for t in table if t["source"]]
    return {
        "generated_from": "college_team_map.build",
        "ncaa_list": {"year": year, "schools": len(rows)},
        "learned_codes": len(learned),
        "codes": len(table), "mapped": len(mapped),
        "rows": sum(codes.values()), "mapped_rows": sum(t["rows"] for t in mapped),
        "by_source": dict(Counter(t["source"] for t in mapped)),
        "with_espn_logo": sum(1 for t in mapped if t["espn_id"]),
        "table": table,
    }


def _js_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_js(doc: dict) -> str:
    mapped = [t for t in doc["table"] if t["source"]]
    lines = [
        "// CollegeSavant shared team-name resolver, GENERATED by college_team_map.py",
        "// (owner answer M20-1, census M03-11). Do not hand-edit: rerun the generator.",
        "// A code is named only when verified against the NCAA D-I list and the",
        "// learned code-to-school map (the generator writes the per-code",
        "// provenance beside its other outputs); every other code prints as the code.",
        "// Loaded before app.js and pitcher_app.js on both pages.",
        "",
        "// code: [school, ESPN NCAA team id or 0]",
        "const TEAM_MAP = {",
    ]
    for t in mapped:
        key = t["code"] if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t["code"]) else _js_str(t["code"])
        lines.append(f"  {key}: [{_js_str(t['name'])}, {t['espn_id'] or 0}],")
    lines += [
        "};",
        "",
        f"const TEAM_MAP_META = {{ codes: {doc['codes']}, mapped: {doc['mapped']}, rows: {doc['rows']}, "
        f"mapped_rows: {doc['mapped_rows']}, ncaa_year: {doc['ncaa_list']['year']} }};",
        "",
        "// Local logo files (collegesavant/logos) win over the ESPN CDN.",
        "const LOCAL_TEAM_LOGOS = new Set([" + ", ".join(_js_str(c) for c in LOCAL_LOGO_CODES) + "]);",
        "",
        "function isMappedTeam(team) {",
        "  const code = String(team || \"\").trim();",
        "  return !!code && Object.prototype.hasOwnProperty.call(TEAM_MAP, code);",
        "}",
        "",
        "function formatTeamName(team) {",
        "  const code = String(team || \"\").trim();",
        "  if (!code) return \"Team\";",
        "  if (isMappedTeam(code)) return TEAM_MAP[code][0];",
        "  return code.replace(/_/g, \" \").toUpperCase();",
        "}",
        "",
        "// The published coverage line for the Teams views.",
        "function teamMapNote() {",
        "  const m = TEAM_MAP_META;",
        "  return `School names: ${m.mapped} of ${m.codes} team codes (${m.mapped_rows.toLocaleString()} of ${m.rows.toLocaleString()} player rows) are verified against the NCAA D-I list and the learned code-to-school map; every other code prints as the code.`;",
        "}",
        "",
        "// A logo URL for a code, or null: the local file when one ships, else the",
        "// ESPN NCAA logo of a verified school with an id (the PROSPX draft-card map).",
        "function teamLogoUrl(team) {",
        "  const code = String(team || \"\").trim();",
        "  if (LOCAL_TEAM_LOGOS.has(code)) return \"logos/\" + code + \".png\";",
        "  const id = isMappedTeam(code) ? TEAM_MAP[code][1] : 0;",
        "  return id ? \"https://a.espncdn.com/i/teamlogos/ncaa/500/\" + id + \".png\" : null;",
        "}",
        "",
    ]
    return "\n".join(lines)


LOCAL_LOGO_CODES = sorted(p.stem for p in (CS / "logos").glob("*.png"))


def write(doc: dict) -> None:
    js = render_js(doc).replace("\n", "\r\n")
    (CS / "team_names.js").write_bytes(js.encode("utf-8"))
    (ROOT / "data" / "collegesavant_team_map.json").write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    d = build()
    write(d)
    print(json.dumps({k: v for k, v in d.items() if k != "table"}, indent=1))
