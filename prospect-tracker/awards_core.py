# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The selection rules of the Awards module (AWARDS_2_RULES_CORE; AWARDS_PLAN 4.2
'The selection rules', 4.3 'Superlatives', 4.4 'data/awards.json' label fields,
5.15 'Copy and credits', 6 'Invariants and tests').

Pure functions over inputs passed in: nothing here opens a socket, reads a served
file or writes one. awards_export.py (AWARDS_3) reads the files and hands the rows
in; build_site and the page read the payload the exporter writes.

THE FLAG. AWARDS_LIVE defaulted False and AWARDS_11_FLIP_RENAME set it True.
While it is False nothing renames, no awards page is written into the published
tree, the exporter writes only under .cache/awards/preview/ (except --freeze), and
publish paths, glossary and registry carry no awards entry.

THE PROVIDER. Every WAR number here is on the DISPLAY provider, passed in
explicitly by the caller as `war_provider`, which the exporter reads from
bullpen_export.served_war_basis()['war_provider'] (display_war_provider() below):
eWAR v2 today, eWAR v3 once EBR_3 flips it. The training default of war_source is
never read here, because the fWAR label epoch turns it to the training label
(EPOCH-Q4-IMPL) while the displayed WAR stays eWAR v2 (EPOCH-Q4). Every WAR unit
label and the 'does not claim' line (5) are built from the block's war_provider
through war_unit_label(), never typed (WAR_UNIT_LABELS is the one map).

THE LEAGUE SPLIT. war_source.stint_frame(side, provider=<display provider>) is one
row per player, club and stint with lg_ID; the provider frame spreads each
player-season's unrounded side total (data/ewar.json ewb, ewp on ewar_v2) over his
stints by PA or IPouts, so the league shares of a side sum back to the side total
(invariant I1). A player with rows in both leagues is a candidate in each league
with that league's share only, flagged split_season, and his row prints both shares.

THE FOUR RULES (floors scaled by G, the scheduled games: 162, 60 in 2020):
  MVP     in-league WAR, batting plus pitching summed before rounding; floor
          in-league PA >= ceil(1.55 G) or IP >= ceil(0.5 G); ties by unrounded
          score, in-league WPA, MLBAM id ascending.
  CY      in-league pitching WAR; floor in-league IP >= ceil(0.25 G); ties by score,
          in-league IP, SEM+ (starter) or REM+ (reliever) raw, MLBAM id.
  ROY     in-league WAR, both sides, among players rookies.json calls eligible
          (AWARDS_1); floor PA >= ROY_MIN_PA or IP >= ROY_MIN_IP (the war board's
          qualified cut); ties as MVP; players removed by the days proxy alone are
          listed with their days.
  MOY     the club-season (no manager on disk, F14; AW-Q1 recommended, no floor):
          W minus (REPLACEMENT_WINS + war_earned) x GP / 162, the team_win_projections
          identity, decomposed into W minus Pythagorean W ("sequencing") and
          Pythagorean W minus (REPLACEMENT_WINS + war_earned) x GP / 162 ("runs
          against player value"); Pythagorean W = pythagPct x gamesPlayed of the
          served team_outlook; ties by score, W minus Pythagorean W, club code.
          Clubs join through trades.canonical_org (boards speak StatsAPI codes,
          team_outlook and war_daily Baseball-Reference codes).
Each returns the full BBWAA-length ballot (BALLOT_RULES), rank 1 first.

ROUNDING. Every score is computed unrounded and printed through score_display(),
a copy of war_board_export._blank_free (1 dp, never -0.0). It is a copy because
importing war_board_export pulls hitter_export and bullpen_export (live StatsAPI
readers) into sys.modules; test_awards_core.py pins equality on 10,000 random
values. ROY_MIN_PA / ROY_MIN_IP copy war_board_export.QUAL_MIN_PA / QUAL_MIN_IP
and ROOKIE_* copy awards_rookies' lines for the same reason; the same test pins
each.

THE FRAME GUARDS (AWARDS_PLAN F10 to F12, I7). The prospect superlatives pair eFV
at debut with a season's WAR for one player at a time and only on debut cohorts the
reserved eFV frames leave open: debut seasons before min(efv_vintage_frame.RESERVED_LV)
(2020; RESERVED_LV holds LIST vintages, and R-LV members debut in 2020 or later),
plus the cohorts OPEN_LATE_COHORTS names once the look record each entry cites
exists in its gate document (a later commit extends it: 2020 to 2024 at the R-LV
look record, each cohort from R_VM_FIRST_DEBUT_YEAR at its R-VM look record). The
projection superlatives are dark for PROJ_DARK_SEASONS (2026: no preseason file
exists and label season 2026 is a reserved frame of three registered looks) and
for any season whose PROJ_LOOKS entry is missing or not yet recorded.
preseason_read() (AWARDS_13) is the one reader of M15's frozen Opening Day file
(docs/PROJ_FORWARD_VINTAGE_GATE.md): it asks the look gate FIRST and opens the
file only when every look on the label season is recorded, then checks the
file's sha256 against the freeze log, so no projected number is loaded while a
look is pending. The Manager card's preseason column (W minus the frozen wins)
reads the same file under the same gate plus the club look; it never replaces
the score. Nothing here groups any realized number by FV, eFV or consensus
band and nothing reads the realized FV anchor (docs/PROSPECT_ANCHOR_GATE.md);
test_awards_guards.py scans this source for both.

COPY. No em or en dash; nothing in tools/copy_lint.py's BAN list; none of the
verdict words of AWARDS_PLAN 5.15 (VERDICT_WORDS) in any string a page could
serve; numbers and dates in copy come from fields. verdict_hits(text) is the scan
the exporter and the tests run over every served string.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#: The module flag (AWARDS_PLAN 3 'The flag'). Only AWARDS_11_FLIP_RENAME sets it True,
#: and it did (2026-10-09): /awards/ is served and the module reads "Awards / HoF".
AWARDS_LIVE = True
#: The module's display name once the flag is True (AWARDS_PLAN 3, C1).
MODULE_LABEL = "Awards / HoF"

AWARDS = ("MVP", "CY", "ROY", "MOY")
LEAGUES = ("AL", "NL")
AWARD_NAMES = {"MVP": "Most Valuable Player", "CY": "Cy Young", "ROY": "Rookie of the Year",
               "MOY": "Manager of the Year"}

#: BBWAA ballot lengths and points (AWARDS_PLAN 4.2 'BBWAA ballot rules').
BALLOT_RULES = {
    "MVP": {"n": 10, "points": [14, 9, 8, 7, 6, 5, 4, 3, 2, 1]},
    "CY": {"n": 5, "points": [7, 4, 3, 2, 1]},
    "ROY": {"n": 3, "points": [5, 3, 1]},
    "MOY": {"n": 3, "points": [5, 3, 1]},
}

#: Scheduled games per club: the floors scale by G (AWARDS_PLAN 4.2 notation).
FULL_SEASON_GAMES = 162
SHORT_SEASONS = {2020: 60}

#: MVP floor: PA >= ceil(1.55 G) or IP >= ceil(0.5 G) (252 PA or 81 IP at 162).
MVP_PA_PER_GAME = 1.55
MVP_IP_PER_GAME = 0.5
#: Cy Young floor: IP >= ceil(0.25 G) (41 at 162); relievers stay eligible.
CY_IP_PER_GAME = 0.25
#: Rookie floor: the war board's qualified cut (war_board_export.QUAL_MIN_PA /
#: QUAL_MIN_IP), copied so this module imports no live reader; pinned by test.
ROY_MIN_PA = 100
ROY_MIN_IP = 30
#: The rookie lines (awards_rookies.PRIOR_AB_MAX, PRIOR_IP_MAX, PROXY_DAYS_MAX,
#: NEAR_TOKEN), copied for the labels and pinned by test.
ROOKIE_PRIOR_AB_MAX = 130
ROOKIE_PRIOR_IP_MAX = 50.0
ROOKIE_PROXY_DAYS_MAX = 45
ROOKIE_NEAR_TOKEN = "near_45_day_line"

#: Superlative floors (AWARDS_PLAN 4.3).
SL_MIN_PA = 300
SL_MIN_IP = 80
GLOVE_MIN_INN = 400.0
RELIEF_MIN_IP = 40.0
RELIEF_MIN_GMLI = 1.2
PITCHING_CHANGES_MIN_N = 100
#: The eFV scale floor; a prospect row graded there carries graded_at_floor.
EFV_FLOOR = 20.0
#: Rows per superlative card (the page shows 3 at phone width and 5 from 768 px).
SL_TOP_N = 5

try:
    from rate_stabilization import REPLACEMENT_WINS
except Exception:   # noqa: BLE001 - the platform's one home for it; the identity's constant
    REPLACEMENT_WINS = 47.7

#: The one map from a war_provider id to the unit a page prints. Every WAR unit
#: label is built through war_unit_label(); no label string is typed elsewhere.
WAR_UNIT_LABELS = {"ewar_v2": "eWAR v2", "ewar_v3": "eWAR", "fwar": "fWAR", "bwar": "bWAR"}

#: The unit of the eWAR realized column printed beside a ballot score while the
#: displayed eWAR is eWAR v3 (owner answer EW3-20; EBR_GATE.md 11.10.5).
REALIZED_UNIT_LABEL = "eWAR realized"

#: The registry row the selection cards cite (lands at AWARDS_11).
SELECTION_REGISTRY = "awards_selection"

#: The deserved read on eWAR realized (docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md
#: part 4; owner decision EW3-20). Off: the band constants and the deserved ballots are
#: built into awards_eval.json only; on: awards.json also serves them under `deserved`,
#: keyed by season, so the frozen selection and the closed season files never move.
#: FLIPPED 2026-10-22 after the registered check (part 4.4, recorded in part 9.1) held.
AWARDS_DESERVED_LIVE = True
#: Places on each deserved ballot, and the band's multiplier (part 4.2 and 4.3).
DESERVED_N = 5
DESERVED_Z = 1.645
#: The awards that carry a deserved read (Manager of the Year carries no WAR).
DESERVED_AWARDS = ("MVP", "CY", "ROY")
#: The band's frame: player-seasons 2015 to 2025, 2020 excluded (part 4.2).
BAND_SEASONS = tuple(s for s in range(2015, 2026) if s != 2020)
#: D-3: each side's band constant needs at least this many player-seasons.
BAND_MIN_N = 1000

#: Lamp ladder presentation per award: value per lamp (shared by both leagues and
#: every season of an award so cards compare) and the tick spacing, in the
#: award's unit. The exporter widens lamp_unit when a value would need more
#: than 60 lamps, never the SVG (AWARDS_PLAN 5.2).
LAMP_UNITS = {"MVP": 0.2, "CY": 0.2, "ROY": 0.2, "MOY": 0.5}
TICK_EVERY = {"MVP": 1.0, "CY": 1.0, "ROY": 1.0, "MOY": 5.0}
SCORE_DECIMALS = 1

#: The eleven measured superlative titles (AWARDS_PLAN 4.3, C9). Two carry the
#: next season as a field; sl_title() formats them.
SL_TITLES = {
    "prospect_above": "Former prospects: furthest above the grade at debut",
    "prospect_below": "Former prospects: furthest below the grade at debut",
    "proj_above": "Furthest above the preseason projection",
    "proj_below": "Furthest below the preseason projection",
    "next_rise": "Largest projected rise for {next_season}",
    "next_drop": "Largest projected drop for {next_season}",
    "glove": "Highest DEM+",
    "contact_ahead": "Contact quality ahead of results",
    "results_ahead": "Results ahead of contact quality",
    "relief": "Highest REM+ in high-leverage relief",
    "pitching_changes": "Most realized value from pitching changes",
}
SL_IDS = tuple(SL_TITLES)

#: Debut cohorts at or after min(RESERVED_LV) that a LATER commit opens, each
#: naming the gate document and the results heading where its look record sits:
#:   {2020: {"gate_doc": "docs/efv-v2/EFV_V2_GATE.md", "results_heading": "## 9. Results",
#:           "record": "R-LV"}, ...}
#: 2020 to 2024 join once the R-LV look record exists; each cohort from
#: R_VM_FIRST_DEBUT_YEAR once its R-VM look record exists. An entry whose record
#: does not exist keeps its cohort closed and fails test_awards_guards.py.
OPEN_LATE_COHORTS: dict[int, dict] = {}

#: Seasons whose projection superlatives are dark by decision (AW-Q3, F12).
PROJ_DARK_SEASONS = frozenset({2026})
#: The two readers of the frozen file: the player pair (proj_above, proj_below)
#: and the Manager card's preseason column.
PROJ_SCOPES = ("players", "clubs")
#: Per label season, the registered looks that must all be recorded before the
#: frozen Opening Day file is read (AWARDS_PLAN 4.2, 4.3, C6): {season: ({...}, ...)}.
#: Each entry names its gate document, the results heading its record sits under,
#: `record` (the name blocked_on lists) and `record_re`, the line pattern only the
#: look's own result row matches (a dated row; an amendment, slip or VOID row never
#: matches), and `scope`, the readers it holds closed. An entry whose document is
#: not at HEAD carries `pending` and no heading: it is never recorded, so the card
#: stays closed, and test_awards_guards.py fails once the document lands, so its
#: heading is filled from the document. 2027: the forward gate's season-end score
#: (M15), AG_16, PJ_11, and TM_9 for the club column.
PROJ_LOOKS: dict[int, tuple] = {
    2027: (
        {"gate_doc": "docs/PROJ_FORWARD_VINTAGE_GATE.md",
         "results_heading": "## 9. The append-only record",
         "record": "PROJ_FORWARD_VINTAGE 2027 season-end score",
         "record_re": (r"^(?!.*\b(?:[Aa]mend\w*|[Ss]lip\w*|VOID|MISSED|no_season)\b)"
                       r"(?=.*\b\d{4}-\d{2}-\d{2}\b)(?=.*\b2027\b)(?=.*\bscore)"
                       r"(?=.*\b(?:AHEAD|BEHIND|NOT_RESOLVED)\b)"),
         "scope": PROJ_SCOPES},
        {"gate_doc": "docs/AGING_V3_ML_FORWARD_GATE.md",
         "results_heading": None,
         "record": "AG_16 aging v3 ML forward look, label season 2027",
         "record_re": None,
         "pending": "registered by AG_14_ML_V3_FORWARD_REGISTRATION; not at HEAD",
         "scope": PROJ_SCOPES},
        {"gate_doc": "docs/PROJ_COMPONENTS_GATE.md",
         "results_heading": "## 9. The append-only record",
         "record": "PJ_11 PJ-W result, label season 2027",
         "record_re": r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*PJ-W\s*\|\s*(?:PASS|FAIL|UNDERPOWERED)\b",
         "scope": PROJ_SCOPES},
        {"gate_doc": "docs/TEAM_PROJECTIONS_GATE.md",
         "results_heading": "## 8. The append-only record",
         "record": "TM_9 FORWARD result, label season 2027",
         "record_re": (r"^(?!.*\b(?:[Aa]mend\w*|[Ss]lip\w*|VOID)\b)(?=.*\b\d{4}-\d{2}-\d{2}\b)"
                       r"(?=.*\b(?:TM_9|TM_9_TEAM_LOOK_2027|forward_2027)\b)"),
         "scope": ("clubs",)},
    ),
}

#: AWARDS_PLAN 5.15: never in served copy or a payload string (whole words).
VERDICT_WORDS = (
    "snub", "snubbed", "robbed", "deserve", "deserved", "deserving", "undeserving",
    "should have won", "wrong", "correct", "right call", "mistake", "lock", "shoo-in",
    "frontrunner", "favorite", "favourite", "clear winner", "runaway", "worthy", "unworthy",
    "overrated", "underrated", "overperformer", "underperformer", "overachiever",
    "underachiever", "breakout", "bust", "disappointment", "luck", "lucky", "unlucky",
    "clutch", "choke", "best player", "predict", "prediction", "projected winner", "odds",
    "chance to win", "pick", "regress", "trending", "sleeper",
)
VERDICT_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in VERDICT_WORDS) + r")\b", re.IGNORECASE)
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)

#: Credit lines (AWARDS_PLAN 5.15); the exporter serves only the lines whose data
#: the page shows. The MLB line takes the feed's copyright string verbatim; the
#: FanGraphs line takes its reference column's unit from WAR_UNIT_LABELS.
CREDIT_LINES = {
    "mlb": "Rosters and the writers' award results come from MLB's public StatsAPI feed. {mlb_copyright}",
    "bref": "eWAR starts from Baseball-Reference's WAR file, with pitching re-priced by the site.",
    "bref_v3": ("Rosters by league and club come from Baseball-Reference's WAR file; eWAR starts from "
                "FanGraphs' published WAR, with the site's ABS challenge part from 2026."),
    "fangraphs": "The {fwar} reference column and the fielding inputs to DEM+ are FanGraphs' published values.",
    "savant": "Expected-stat inputs to xHEM+ and xSEM+ come from Baseball Savant (MLB).",
    "eephus": "Every selection, superlative and percentile is computed by eephus.io.",
}


class ProviderMismatch(ValueError):
    """The projection bundle and the realized side are on different WAR providers;
    the caller keeps yesterday's block (AWARDS_PLAN 4.3 next_rise / next_drop, I8)."""


# --- providers, games, rounding -------------------------------------------------

def display_war_provider() -> str:
    """The WAR series the site displays: bullpen_export.served_war_basis()['war_provider'].
    The exporter calls this once and passes the string down; nothing in this module
    reads war_source's training default."""
    import bullpen_export
    return str(bullpen_export.served_war_basis()["war_provider"])


def war_unit_label(war_provider: str) -> str:
    """The unit a page prints for a WAR-bearing block, from its war_provider."""
    if war_provider is None or not str(war_provider):
        raise ValueError("a WAR-bearing block needs a war_provider")
    return WAR_UNIT_LABELS.get(str(war_provider), f"WAR ({war_provider})")


def scheduled_games(season: int) -> int:
    """G: 162, 60 in 2020."""
    return SHORT_SEASONS.get(int(season), FULL_SEASON_GAMES)


def score_display(v):
    """1 dp and never -0.0: a copy of war_board_export._blank_free (see the module
    docstring for why it is a copy); test_awards_core.py pins equality."""
    if v is None:
        return None
    r = round(float(v), SCORE_DECIMALS)
    return 0.0 if r == 0 else r


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


def _club_code(raw) -> str | None:
    """A canonical club code through trades.canonical_org, else the raw string."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        from trades import canonical_org
        return canonical_org(s) or s
    except Exception:   # noqa: BLE001 - a fixture world without trades keeps its codes
        return s


def floors(award: str, season: int) -> dict:
    """The playing-time floor of an award in season S: {"pa": n|None, "ip": n|None, "g": G}."""
    g = scheduled_games(season)
    if award == "MVP":
        return {"pa": math.ceil(MVP_PA_PER_GAME * g), "ip": math.ceil(MVP_IP_PER_GAME * g), "g": g}
    if award == "CY":
        return {"pa": None, "ip": math.ceil(CY_IP_PER_GAME * g), "g": g}
    if award == "ROY":
        return {"pa": ROY_MIN_PA, "ip": ROY_MIN_IP, "g": g}
    if award == "MOY":
        return {"pa": None, "ip": None, "g": g}
    raise ValueError(f"unknown award {award!r}")


def clears_floor(award: str, row: dict, season: int) -> bool:
    f = floors(award, season)
    pa = _num(row.get("pa")) or 0.0
    ip = _num(row.get("ip")) or 0.0
    if f["pa"] is None and f["ip"] is None:
        return True
    return (f["pa"] is not None and pa >= f["pa"]) or (f["ip"] is not None and ip >= f["ip"])


# --- the league split ------------------------------------------------------------

_EXPOSURE_COL = {"bat": "PA", "pit": "IPouts"}


def _records(rows) -> list[dict]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return rows.to_dict("records")
    return [dict(r) for r in rows]


def league_split(frames: dict, *, season: int, war_provider: str) -> list[dict]:
    """One row per player and league from the provider stint frames.

    `frames` is {"bat": rows, "pit": rows}: war_source.stint_frame(side,
    provider=war_provider) as a DataFrame or its records (mlb_ID, year_ID, lg_ID,
    team_ID, stint_ID, PA or IPouts, WAR, name_common, age). Rows of other seasons
    and rows without an mlbam or a WAR value are skipped.

    Each row: {mlbam, name, age, league, bat, pit, pa, ip, clubs, split_season,
    share, war_provider}; `bat` and `pit` are the unrounded in-league shares, `pa`
    and `ip` the in-league exposure, `clubs` the league's clubs in stint order,
    `share` {"AL": {"bat", "pit"}, "NL": {...}} on a split season (both leagues)
    and None otherwise. Sorted by mlbam, then league."""
    if not war_provider:
        raise ValueError("league_split needs the display war_provider passed in")
    season = int(season)
    acc: dict = {}
    names: dict = {}
    for side in ("bat", "pit"):
        expo_col = _EXPOSURE_COL[side]
        for r in _records(frames.get(side)):
            yr = _num(r.get("year_ID"))
            mid = _num(r.get("mlb_ID"))
            war = _num(r.get("WAR"))
            if yr is None or int(yr) != season or mid is None or war is None:
                continue
            lg = str(r.get("lg_ID") or "").strip().upper()
            if lg not in LEAGUES:
                continue
            mlbam = int(mid)
            cell = acc.setdefault(mlbam, {}).setdefault(
                lg, {"bat": 0.0, "pit": 0.0, "pa": 0, "ip": 0.0, "clubs": [], "stints": []})
            cell[side] += war
            real = _num(r.get("WAR_realized"))
            if real is not None:
                # eWAR realized beside the displayed series (provider ewar_v3 only)
                cell[side + "_real"] = cell.get(side + "_real", 0.0) + real
            expo = _num(r.get(expo_col)) or 0.0
            if side == "bat":
                cell["pa"] += int(round(expo))
            else:
                cell["ip"] += expo / 3.0
            club = _club_code(r.get("team_ID"))
            stint = _num(r.get("stint_ID")) or 0
            if club:
                cell["stints"].append((stint, club))
            nm = r.get("name_common")
            if nm and mlbam not in names:
                names[mlbam] = {"name": str(nm), "age": _num(r.get("age"))}
    out = []
    for mlbam in sorted(acc):
        leagues = acc[mlbam]
        split = all(lg in leagues for lg in LEAGUES)
        share = ({lg: {"bat": leagues[lg]["bat"], "pit": leagues[lg]["pit"]} for lg in LEAGUES}
                 if split else None)
        for lg in LEAGUES:
            if lg not in leagues:
                continue
            c = leagues[lg]
            clubs = []
            for _, club in sorted(c["stints"], key=lambda t: t[0]):
                if club not in clubs:
                    clubs.append(club)
            out.append({
                "mlbam": mlbam,
                "name": names.get(mlbam, {}).get("name"),
                "age": names.get(mlbam, {}).get("age"),
                "league": lg,
                "bat": c["bat"], "pit": c["pit"],
                **{k: c[k] for k in ("bat_real", "pit_real") if k in c},
                "pa": c["pa"], "ip": round(c["ip"], 3),
                "clubs": clubs,
                "split_season": split,
                "share": copy.deepcopy(share),
                "war_provider": war_provider,
            })
    return out


def side_totals(league_rows: list[dict]) -> dict:
    """{mlbam: {"bat": AL + NL batting share, "pit": AL + NL pitching share}}: the
    sums I1 checks against the provider artifact's side totals."""
    out: dict = {}
    for r in league_rows:
        t = out.setdefault(int(r["mlbam"]), {"bat": 0.0, "pit": 0.0})
        t["bat"] += float(r.get("bat") or 0.0)
        t["pit"] += float(r.get("pit") or 0.0)
    return out


# --- the four rules ---------------------------------------------------------------

def _player_row(rank: int, r: dict, score: float, *, pos=None, flags=None, realized=None) -> dict:
    mlbam = int(r["mlbam"])
    club = (r.get("clubs") or [None])[-1]
    row = {
        "rank": rank, "mlbam": mlbam, "name": r.get("name"), "club_code": club,
        "pos": pos, "score": float(score), "score_display": score_display(score),
        "bat": float(r.get("bat") or 0.0), "pit": float(r.get("pit") or 0.0),
        "pa": r.get("pa"), "ip": r.get("ip"),
        "share": copy.deepcopy(r.get("share")),
        "flags": list(flags or []),
        "links": {"overview": f"/projections/#player={mlbam}"},
    }
    if r.get("split_season") and "split_season" not in row["flags"]:
        row["flags"].append("split_season")
    if realized is not None:
        # eWAR realized on the same rule, printed beside the score (EW3-20);
        # it never ranks, sorts or breaks a tie
        row["realized"] = float(realized)
        row["realized_display"] = score_display(realized)
    return row


def _realized(r: dict, sides) -> float | None:
    """The row's in-league eWAR realized over `sides`, or None when the frame
    carried no realized column (any provider but ewar_v3)."""
    if not any((s + "_real") in r for s in sides):
        return None
    return sum(float(r.get(s + "_real") or 0.0) for s in sides)


def _mark_ties(rows: list[dict]) -> None:
    for i, r in enumerate(rows):
        tied = ((i > 0 and rows[i - 1]["score"] == r["score"])
                or (i + 1 < len(rows) and rows[i + 1]["score"] == r["score"]))
        if tied and "tie" not in r["flags"]:
            r["flags"].append("tie")


def _ballot(award: str, rows: list[dict], n: int | None) -> list[dict]:
    n = BALLOT_RULES[award]["n"] if n is None else int(n)
    top = rows[:n]
    _mark_ties(top)
    return top


def _wpa(wpa: dict | None, mlbam: int) -> float:
    if not wpa:
        return 0.0
    return _num(wpa.get(mlbam, wpa.get(str(mlbam)))) or 0.0


def mvp_ballot(league_rows: list[dict], league: str, season: int, *,
               wpa: dict | None = None, pos: dict | None = None,
               n: int | None = None) -> dict:
    """MVP in league L: in-league WAR, both sides, floor PA >= ceil(1.55 G) or
    IP >= ceil(0.5 G); ties by unrounded score, in-league WPA, MLBAM id."""
    return _war_ballot("MVP", league_rows, league, season, wpa=wpa, pos=pos, n=n)


def rookie_ballot(league_rows: list[dict], league: str, season: int, *,
                  rookies: dict | list, wpa: dict | None = None, pos: dict | None = None,
                  n: int | None = None) -> dict:
    """Rookie of the Year in league L: as MVP among the players rookies.json calls
    eligible for S, floor PA >= ROY_MIN_PA or IP >= ROY_MIN_IP. `rookies` is the
    season block of data/_labs/awards/rookies.json (its `columns` and `rows`) or
    the rows alone. `excluded` lists every player above the floor whom the block
    carries as not eligible, with his reason and proxy days: the block lists only
    players under the at-bat and innings lines, so each of them was removed by the
    days proxy alone."""
    status = rookie_status(rookies)
    return _war_ballot("ROY", league_rows, league, season, wpa=wpa, pos=pos, n=n, rookies=status)


def rookie_status(rookies: dict | list) -> dict:
    """{mlbam: {"eligible", "reason", "proxy_days", "prior_ab", "prior_ip", "near"}}
    from a rookies.json season block or its rows."""
    if isinstance(rookies, dict):
        cols = rookies.get("columns") or ["mlbam", "prior_ab", "prior_ip", "proxy_days",
                                          "eligible", "reason"]
        rows = rookies.get("rows") or []
    else:
        cols = ["mlbam", "prior_ab", "prior_ip", "proxy_days", "eligible", "reason"]
        rows = rookies or []
    out = {}
    for r in rows:
        d = dict(zip(cols, r)) if isinstance(r, (list, tuple)) else dict(r)
        reason = str(d.get("reason") or "")
        out[int(d["mlbam"])] = {
            "eligible": bool(d.get("eligible")), "reason": reason,
            "proxy_days": d.get("proxy_days"), "prior_ab": d.get("prior_ab"),
            "prior_ip": d.get("prior_ip"), "near": ROOKIE_NEAR_TOKEN in reason,
        }
    return out


def _war_ballot(award: str, league_rows: list[dict], league: str, season: int, *,
                wpa=None, pos=None, n=None, rookies: dict | None = None) -> dict:
    if league not in LEAGUES:
        raise ValueError(f"league must be AL or NL, not {league!r}")
    pos = pos or {}
    pool, excluded = [], []
    for r in league_rows:
        if r.get("league") != league or not clears_floor(award, r, season):
            continue
        mlbam = int(r["mlbam"])
        if rookies is not None:
            st = rookies.get(mlbam)
            if st is None:
                continue
            if not st["eligible"]:
                excluded.append({"mlbam": mlbam, "name": r.get("name"), "reason": st["reason"],
                                 "proxy_days": st["proxy_days"]})
                continue
        pool.append(r)
    scored = []
    for r in pool:
        score = float(r.get("bat") or 0.0) + float(r.get("pit") or 0.0)
        scored.append((score, r))
    scored.sort(key=lambda t: (-t[0], -_wpa(wpa, int(t[1]["mlbam"])), int(t[1]["mlbam"])))
    rows = []
    for i, (score, r) in enumerate(scored, 1):
        flags = []
        if rookies is not None and rookies[int(r["mlbam"])]["near"]:
            flags.append(ROOKIE_NEAR_TOKEN)
        rows.append(_player_row(i, r, score, pos=pos.get(int(r["mlbam"])), flags=flags,
                                realized=_realized(r, ("bat", "pit"))))
    top = _ballot(award, rows, n)
    excluded.sort(key=lambda e: (-(_num(e.get("proxy_days")) or 0.0), e["mlbam"]))
    war_provider = (league_rows[0].get("war_provider") if league_rows else None)
    return {"award": award, "league": league, "season": int(season), "top": top,
            "n_pool": len(pool), "floor": floors(award, season),
            "excluded": excluded if rookies is not None else [],
            "war_provider": war_provider,
            "lead": lead_sentence(award, top, war_provider),
            "tiebreak_sentence": tiebreak_sentence(award, top)}


def cy_young_ballot(league_rows: list[dict], league: str, season: int, *,
                    skill_raw: dict | None = None, pos: dict | None = None,
                    n: int | None = None) -> dict:
    """Cy Young in league L: in-league pitching WAR, floor IP >= ceil(0.25 G);
    ties by unrounded score, in-league IP, SEM+ or REM+ raw (`skill_raw`, by
    mlbam; a missing value sorts last among equals), MLBAM id."""
    if league not in LEAGUES:
        raise ValueError(f"league must be AL or NL, not {league!r}")
    pos = pos or {}
    skill_raw = skill_raw or {}
    pool = [r for r in league_rows
            if r.get("league") == league and clears_floor("CY", r, season)]

    def _skill(mlbam: int) -> float:
        v = _num(skill_raw.get(mlbam, skill_raw.get(str(mlbam))))
        return float("-inf") if v is None else v

    scored = [(float(r.get("pit") or 0.0), r) for r in pool]
    scored.sort(key=lambda t: (-t[0], -(_num(t[1].get("ip")) or 0.0),
                               -_skill(int(t[1]["mlbam"])), int(t[1]["mlbam"])))
    rows = [_player_row(i, r, score, pos=pos.get(int(r["mlbam"])), realized=_realized(r, ("pit",)))
            for i, (score, r) in enumerate(scored, 1)]
    top = _ballot("CY", rows, n)
    war_provider = (league_rows[0].get("war_provider") if league_rows else None)
    return {"award": "CY", "league": league, "season": int(season), "top": top,
            "n_pool": len(pool), "floor": floors("CY", season), "excluded": [],
            "war_provider": war_provider,
            "lead": lead_sentence("CY", top, war_provider),
            "tiebreak_sentence": tiebreak_sentence("CY", top)}


# --- the deserved read on eWAR realized (EWAR_SITEWIDE_CALIBRATION.md part 4) ------------

def band_constants(stints: dict, fwar: dict, seasons=BAND_SEASONS) -> dict:
    """The measurement band's constants per side (part 4.2).

    `stints` is {"bat": records, "pit": records} of an eWAR stint frame (year_ID,
    mlb_ID, PA or IPouts, WAR_bwar); `fwar` is {"bat": {(mlbam, season): published
    fWAR}, "pit": {...}} from the frozen vintage. Per side, over the player-seasons
    of `seasons` the vintage carries with exposure above 0:
    k = sum (FanGraphs WAR - Baseball-Reference WAR)^2 / (2 * sum exposure), exposure PA
    (bat) or IP (pit).
    Returns {"bat": {k, n, sum_e, unit, terciles}, "pit": {...}, "seasons", "z"};
    a side with no usable row carries k None."""
    seasons = {int(s) for s in seasons}
    out = {"seasons": sorted(seasons), "z": DESERVED_Z,
           "how": ("k = sum (FanGraphs WAR - Baseball-Reference WAR)^2 / (2 * sum exposure) over "
                   "player-seasons the frozen FanGraphs vintage carries; sigma^2 = k_bat * PA + k_pit * IP")}
    for side, unit, col in (("bat", "PA", "PA"), ("pit", "IP", "IPouts")):
        agg: dict = {}
        for r in stints.get(side) or []:
            y, m = _num(r.get("year_ID")), _num(r.get("mlb_ID"))
            if y is None or m is None or int(y) not in seasons:
                continue
            b = _num(r.get("WAR_bwar"))
            e = _num(r.get(col)) or 0.0
            cell = agg.setdefault((int(m), int(y)), [0.0, 0.0])
            cell[0] += b if b is not None else 0.0
            cell[1] += e / 3.0 if side == "pit" else e
        pairs = []
        for key, (b, e) in agg.items():
            f = (fwar.get(side) or {}).get(key)
            if f is None or e <= 0:
                continue
            pairs.append((e, float(f) - b))
        n = len(pairs)
        sum_e = sum(e for e, _ in pairs)
        k = (sum(d * d for _, d in pairs) / (2.0 * sum_e)) if sum_e > 0 else None
        terc = []
        if n >= 3:
            pairs.sort(key=lambda t: t[0])
            cuts = [0, n // 3, (2 * n) // 3, n]
            for a, b_ in zip(cuts[:-1], cuts[1:]):
                part = pairs[a:b_]
                se = sum(e for e, _ in part)
                terc.append({"e_lo": round(part[0][0], 1), "e_hi": round(part[-1][0], 1),
                             "n": len(part),
                             "k": (sum(d * d for _, d in part) / (2.0 * se)) if se > 0 else None})
        out[side] = {"k": k, "n": n, "sum_e": round(sum_e, 1), "unit": unit, "terciles": terc}
    return out


def band_ok(k: dict) -> bool:
    """D-3: both sides' k finite and positive, each from at least BAND_MIN_N player-seasons."""
    for side in ("bat", "pit"):
        blk = (k or {}).get(side) or {}
        v = blk.get("k")
        if v is None or not math.isfinite(float(v)) or float(v) <= 0 or int(blk.get("n") or 0) < BAND_MIN_N:
            return False
    return True


def band_sigma(k: dict, award: str, pa, ip) -> float:
    """sigma of one ballot row: k_bat * PA + k_pit * IP (the Cy Young reads pitching only)."""
    kb = float(((k or {}).get("bat") or {}).get("k") or 0.0)
    kp = float(((k or {}).get("pit") or {}).get("k") or 0.0)
    v = kp * float(ip or 0.0)
    if award != "CY":
        v += kb * float(pa or 0.0)
    return math.sqrt(max(v, 0.0))


def realized_rows(league_rows: list[dict]) -> list[dict] | None:
    """The same player rows with each side's WAR replaced by its eWAR realized share,
    or None when the frame carried no realized column (any provider but ewar_v3)."""
    if not any(("bat_real" in r or "pit_real" in r) for r in league_rows or []):
        return None
    out = []
    for r in league_rows:
        x = {k: v for k, v in r.items() if k not in ("bat_real", "pit_real")}
        x["headline"] = float(r.get("bat") or 0.0) + float(r.get("pit") or 0.0)
        x["headline_pit"] = float(r.get("pit") or 0.0)
        x["bat"] = float(r.get("bat_real", r.get("bat")) or 0.0)
        x["pit"] = float(r.get("pit_real", r.get("pit")) or 0.0)
        out.append(x)
    return out


def deserved_block(award: str, ballot: dict, rows: list[dict], k: dict, *,
                   writers_id=None) -> dict:
    """One ballot on eWAR realized (part 4.3) from the rule's ballot on realized rows:
    the top DESERVED_N with each row's band, the places within the band of the
    first, the verdict, and the writers' winner's standing where it exists."""
    by_id = {int(r["mlbam"]): r for r in rows}
    z = DESERVED_Z
    top = []
    for r in (ballot.get("top") or [])[:DESERVED_N]:
        src = by_id.get(int(r["mlbam"])) or {}
        sig = band_sigma(k, award, r.get("pa"), r.get("ip"))
        head = src.get("headline_pit") if award == "CY" else src.get("headline")
        top.append({"rank": r["rank"], "mlbam": r["mlbam"], "name": r.get("name"),
                    "club_code": r.get("club_code"), "pos": r.get("pos"),
                    "score": r["score"], "score_display": score_display(r["score"]),
                    "sigma": round(sig, 4),
                    "lo_display": score_display(r["score"] - z * sig),
                    "hi_display": score_display(r["score"] + z * sig),
                    "ewar_display": score_display(head) if head is not None else None,
                    "flags": list(r.get("flags") or [])})
    within = []
    if top:
        lead = top[0]
        for r in top[1:]:
            gap = lead["score"] - r["score"]
            r["within_band"] = gap < z * math.sqrt(lead["sigma"] ** 2 + r["sigma"] ** 2)
            if r["within_band"]:
                within.append(r["mlbam"])
        lead["within_band"] = True
    verdict = None if not top else ("clear" if not within else "too_close")
    out = {"award": award, "top": top, "verdict": verdict, "within_band_of_first": within,
           "n_pool": ballot.get("n_pool"), "unit_label": REALIZED_UNIT_LABEL}
    if writers_id is not None and top:
        if writers_id == top[0]["mlbam"]:
            standing = "first"
        elif writers_id in within:
            standing = "within_band"
        else:
            standing = "outside_band"
        out["writers"] = {"id": writers_id, "standing": standing}
    out["sentence"] = deserved_sentence(out)
    return out


def deserved_sentence(blk: dict) -> str:
    """The verdict in one plain sentence (no forecast word, no claim about the vote)."""
    top = blk.get("top") or []
    if not top:
        return "No player cleared the rule's floor on eWAR realized."
    lead = top[0]
    if blk.get("verdict") == "clear":
        s = (f"{lead['name']} leads on eWAR realized by more than the band: a clear first "
             f"({lead['score_display']}).")
    else:
        names = [r["name"] for r in top if r["mlbam"] in blk.get("within_band_of_first", [])]
        s = (f"Too close to call on eWAR realized: {lead['name']} ({lead['score_display']}) leads, "
             f"with {', '.join(names)} within the band.")
    w = blk.get("writers")
    if w:
        s += {"first": " The writers' winner is the first on eWAR realized.",
              "within_band": " The writers' winner is within the band of the first.",
              "outside_band": " The writers' winner is outside the band of the first."}[w["standing"]]
    return s


DESERVED_BAND_SENTENCE = (
    "The band is the disagreement between two published WAR systems (FanGraphs and "
    "Baseball-Reference) for a season of this playing time, halved in variance on the "
    "assumption that their errors are independent and equal; it is not a confidence interval.")


def _earned_map(war_earned) -> dict:
    if isinstance(war_earned, dict):
        items = war_earned.items()
    else:
        items = ((t.get("team"), t.get("war_earned")) for t in (war_earned or []))
    out = {}
    for code, v in items:
        c = _club_code(code)
        if c and _num(v) is not None:
            out[c] = float(v)
    return out


def manager_scores(standings: list[dict], team_outlook: list[dict], war_earned,
                   season: int, *, war_provider: str) -> list[dict]:
    """Every club-season's Manager score (AWARDS_PLAN 4.2 'Manager, the agent').

    standings     [{"club", "league", "w", "l", "gp"?}] (any club dialect; gp = w + l when absent)
    team_outlook  the served team_outlook rows ({"team", "current": {"pythagPct", "gamesPlayed"}})
    war_earned    war_leaderboards teams[] ({"team", "war_earned"}) or {club: war_earned}
    Clubs join through trades.canonical_org. A club missing its Pythagorean block
    or its earned WAR is returned with score None and a `missing` list, never a zero."""
    pyth = {}
    for t in team_outlook or []:
        cur = t.get("current") or {}
        c = _club_code(t.get("team"))
        pct, gp = _num(cur.get("pythagPct")), _num(cur.get("gamesPlayed"))
        if c and pct is not None and gp is not None:
            pyth[c] = pct * gp
    earned = _earned_map(war_earned)
    out = []
    for s in standings or []:
        c = _club_code(s.get("club") or s.get("team"))
        w, l = _num(s.get("w")), _num(s.get("l"))
        gp = _num(s.get("gp"))
        if gp is None and w is not None and l is not None:
            gp = w + l
        row = {"club": c, "club_code": s.get("club") or s.get("team"),
               "league": s.get("league"), "season": int(season),
               "w": w, "l": l, "gp": gp, "pythag_w": pyth.get(c),
               "war_earned": earned.get(c), "war_provider": war_provider,
               "score": None, "parts": None, "missing": []}
        if w is None or gp is None:
            row["missing"].append("standings")
        if c not in pyth:
            row["missing"].append("pythag")
        if c not in earned:
            row["missing"].append("war_earned")
        if not row["missing"]:
            expected = (REPLACEMENT_WINS + earned[c]) * gp / FULL_SEASON_GAMES
            seq = w - pyth[c]
            rvv = pyth[c] - expected
            row["score"] = w - expected
            row["parts"] = {"sequencing": seq, "runs_vs_player_value": rvv,
                            "expected_wins": expected}
        out.append(row)
    return out


def manager_ballot(standings: list[dict], team_outlook: list[dict], war_earned,
                   league: str, season: int, *, war_provider: str,
                   n: int | None = None, preseason: dict | None = None) -> dict:
    """Manager of the Year in league L on club-seasons, no floor (AW-Q1); ties by
    unrounded score, W minus Pythagorean W, club code. With `preseason` (the
    "clubs" read of preseason_read, or {} to ask the gate alone) the result carries
    `preseason_column` (manager_preseason); the order never reads it."""
    if league not in LEAGUES:
        raise ValueError(f"league must be AL or NL, not {league!r}")
    scores = [r for r in manager_scores(standings, team_outlook, war_earned, season,
                                        war_provider=war_provider)
              if r.get("league") == league]
    pool = [r for r in scores if r["score"] is not None]
    unscored = [r for r in scores if r["score"] is None]
    pool.sort(key=lambda r: (-r["score"], -r["parts"]["sequencing"], r["club"]))
    rows = []
    for i, r in enumerate(pool, 1):
        rows.append({
            "rank": i, "club": r["club"], "name": r["club"], "club_code": r["club"],
            "pos": None, "score": float(r["score"]), "score_display": score_display(r["score"]),
            "parts": {"sequencing": r["parts"]["sequencing"],
                      "sequencing_display": score_display(r["parts"]["sequencing"]),
                      "runs_vs_player_value": r["parts"]["runs_vs_player_value"],
                      "runs_vs_player_value_display": score_display(r["parts"]["runs_vs_player_value"]),
                      "expected_wins": r["parts"]["expected_wins"]},
            "w": r["w"], "l": r["l"], "gp": r["gp"], "pythag_w": r["pythag_w"],
            "war_earned": r["war_earned"], "flags": [],
            "links": {"management": f"/management/#team={r['club']}",
                      "franchise": f"/franchise/#team={r['club']}"},
        })
    column = (manager_preseason(rows, preseason or None, season)
              if preseason is not None else None)
    top = _ballot("MOY", rows, n)
    out = {"award": "MOY", "league": league, "season": int(season), "top": top,
           "n_pool": len(pool), "floor": floors("MOY", season), "excluded": [],
           "unscored": [{"club": r["club"], "missing": r["missing"]} for r in unscored],
           "war_provider": war_provider,
           "lead": lead_sentence("MOY", top, war_provider),
           "tiebreak_sentence": tiebreak_sentence("MOY", top)}
    if column is not None:
        out["preseason_column"] = column
    return out


# --- superlatives -------------------------------------------------------------------

def sl_title(sl_id: str, season: int | None = None) -> str:
    t = SL_TITLES[sl_id]
    if "{next_season}" in t:
        if season is None:
            raise ValueError(f"{sl_id} needs the season")
        return t.format(next_season=int(season) + 1)
    return t


def midrank_percentiles(values: list[float]) -> list[float]:
    """Mid-rank percentiles inside a pool, ties shared: 100 x (count below + half
    the count equal) / n, so a unique minimum reads 50 / n and a unique maximum
    100 minus 50 / n."""
    n = len(values)
    if n == 0:
        return []
    srt = sorted(values)
    import bisect
    out = []
    for v in values:
        lo = bisect.bisect_left(srt, v)
        hi = bisect.bisect_right(srt, v)
        out.append(100.0 * (lo + 0.5 * (hi - lo)) / n)
    return out


def _playing_time(r: dict) -> tuple:
    return (-(_num(r.get("pa")) or 0.0), -(_num(r.get("ip")) or 0.0))


def _sl_rows(rows: list[tuple], *, largest_first: bool, top_n: int) -> list[dict]:
    """rows: (value, source row, extra fields) -> ranked superlative rows."""
    sign = -1.0 if largest_first else 1.0
    rows = sorted(rows, key=lambda t: (sign * t[0],) + _playing_time(t[1]) + (_id_key(t[1]),))
    out = []
    for i, (value, r, extra) in enumerate(rows[:top_n], 1):
        row = {"rank": i, "id": _row_id(r), "name": r.get("name"),
               "club_code": r.get("club_code") or r.get("club"),
               "from": None, "to": None, "value": float(value),
               "value_display": None, "flags": [], "links": _links(r)}
        row.update(extra)
        out.append(row)
    return out


def _id_key(r: dict):
    if r.get("mlbam") is not None:
        return (0, int(r["mlbam"]))
    return (1, str(r.get("club") or r.get("club_code") or ""))


def _row_id(r: dict):
    if r.get("mlbam") is not None:
        return int(r["mlbam"])
    return "c" + str(r.get("club") or r.get("club_code") or "").lower()


def _links(r: dict) -> dict:
    if r.get("mlbam") is not None:
        out = {"overview": f"/projections/#player={int(r['mlbam'])}"}
        if r.get("player_key"):
            out["prospx"] = f"/prospx/#player={r['player_key']}"
        return out
    club = str(r.get("club") or r.get("club_code") or "")
    return {"management": f"/management/#team={club}", "franchise": f"/franchise/#team={club}"}


def _sl_block(sl_id: str, season: int, rows: list[dict], *, kind: str, family, lamp_unit,
              producer: str, registry, war_provider, n_pool: int, definition: str,
              floor_label: str, frame_label: str, blocked_on: str | None = None,
              caption: str | None = None) -> dict:
    return {"id": sl_id, "title": sl_title(sl_id, season), "definition": definition,
            "floor_label": floor_label, "frame_label": frame_label, "kind": kind,
            "family": family, "lamp_unit": lamp_unit, "producer": producer,
            "registry": registry, "war_provider": war_provider, "n_pool": n_pool,
            "blocked_on": blocked_on, "caption": caption, "rows": rows}


def _signed(v: float, decimals: int) -> str:
    s = f"{v:+.{decimals}f}"
    return s.replace("-0." + "0" * decimals, "0." + "0" * decimals) if float(s) == 0 else s


def _sl_player_floor(r: dict) -> bool:
    return ((_num(r.get("pa")) or 0.0) >= SL_MIN_PA) or ((_num(r.get("ip")) or 0.0) >= SL_MIN_IP)


def sl_player_floor_label() -> str:
    return f"Floor: PA of at least {SL_MIN_PA} or IP of at least {SL_MIN_IP} in the season."


# the prospect pair (frame guards)

def reserved_frames() -> dict:
    """{"lv_first": min(RESERVED_LV), "vm_first": R_VM_FIRST_DEBUT_YEAR} from
    efv_vintage_frame, imported here so the pool guard reads the frame's own pins."""
    import efv_vintage_frame as V
    return {"lv_first": min(V.RESERVED_LV), "vm_first": int(V.R_VM_FIRST_DEBUT_YEAR)}


def look_record_exists(entry: dict, root: Path | None = None) -> bool:
    """True when the gate document `entry['gate_doc']` has the section under
    `entry['results_heading']` and that section carries a line naming
    `entry['record']` that is not the empty placeholder. With `record_re` the
    line must match that pattern instead (the look's own result row). A
    `pending` entry, or one with no heading, is never recorded."""
    if entry.get("pending") or not entry.get("results_heading"):
        return False
    root = Path(root) if root is not None else ROOT
    path = root / entry["gate_doc"]
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    heading = entry["results_heading"].strip()
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    except StopIteration:
        return False
    level = len(heading) - len(heading.lstrip("#"))
    body = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if s.startswith("#") and (len(s) - len(s.lstrip("#"))) <= level:
            break
        body.append(s)
    pattern = entry.get("record_re")
    rx = re.compile(pattern) if pattern else None
    record = str(entry["record"])
    for s in body:
        if not s or s.startswith("(Empty"):
            continue
        if (rx.search(s) if rx is not None else record in s):
            return True
    return False


def prospect_pool_open(debut_season: int, *, root: Path | None = None,
                       record_exists=look_record_exists, frames: dict | None = None) -> bool:
    """The POOL GUARD: a debut cohort enters the prospect superlatives only when
    it debuted before min(RESERVED_LV) or OPEN_LATE_COHORTS names it and the look
    record its entry cites exists."""
    frames = frames or reserved_frames()
    y = int(debut_season)
    if y < frames["lv_first"]:
        return True
    entry = OPEN_LATE_COHORTS.get(y)
    if entry is None:
        return False
    return bool(record_exists(entry, root))


def prospect_frame_label(frames: dict | None = None) -> str:
    frames = frames or reserved_frames()
    opened = sorted(y for y in OPEN_LATE_COHORTS if prospect_pool_open(y, frames=frames))
    base = (f"Debut seasons before {frames['lv_first']}: the site holds out the prospect "
            f"list vintages from {frames['lv_first']} and the debut cohorts from "
            f"{frames['vm_first']} for registered checks of eFV, and each opens once "
            f"its check is recorded.")
    if opened:
        base += " Open since their checks were recorded: " + ", ".join(str(y) for y in opened) + "."
    return base


def _prospect_pair(rows: list[dict], season: int, *, war_provider: str, largest_first: bool,
                   top_n: int, root, record_exists, frames) -> dict:
    frames = frames or reserved_frames()
    pool = []
    for r in rows:
        if not _sl_player_floor(r):
            continue
        efv = _num(r.get("efv_at_debut"))
        war = _num(r.get("war"))
        debut = r.get("debut_season")
        if efv is None or war is None or debut is None:
            continue
        if not prospect_pool_open(int(debut), root=root, record_exists=record_exists, frames=frames):
            continue
        pool.append((r, efv, war))
    pct_efv = midrank_percentiles([p[1] for p in pool])
    pct_war = midrank_percentiles([p[2] for p in pool])
    scored = []
    for (r, efv, war), pe, pw in zip(pool, pct_efv, pct_war):
        gap = pw - pe
        flags = ["graded_at_floor"] if efv <= EFV_FLOOR else []
        scored.append((gap, r, {"from": pe, "to": pw, "efv_at_debut": efv, "war": war,
                                "war_display": score_display(war), "debut_season": int(r["debut_season"]),
                                "value_display": _signed(gap, 1), "flags": flags}))
    sl_id = "prospect_above" if largest_first else "prospect_below"
    unit = war_unit_label(war_provider)
    return _sl_block(
        sl_id, season, _sl_rows(scored, largest_first=largest_first, top_n=top_n),
        kind="dumbbell", family=None, lamp_unit=None,
        producer="xfv.json by_player[].xfv_grade_at_debut; ewar.json", registry="xfv_backgrade",
        war_provider=war_provider, n_pool=len(pool),
        definition=(f"Where a player's season {unit} places him in the pool (percentile) minus "
                    f"where his eFV at debut placed him, one player at a time; ties share a rank."),
        floor_label=sl_player_floor_label() + " A PROSPX debuted row with an eFV at debut.",
        frame_label=prospect_frame_label(frames))


def prospect_above(rows, season, *, war_provider, top_n=SL_TOP_N, root=None,
                   record_exists=look_record_exists, frames=None) -> dict:
    """Former prospects furthest above the grade at debut. Rows: {mlbam, name,
    club_code, player_key, debut_season, efv_at_debut, war, pa, ip}."""
    return _prospect_pair(rows, season, war_provider=war_provider, largest_first=True,
                          top_n=top_n, root=root, record_exists=record_exists, frames=frames)


def prospect_below(rows, season, *, war_provider, top_n=SL_TOP_N, root=None,
                   record_exists=look_record_exists, frames=None) -> dict:
    """Former prospects furthest below the grade at debut (the same gap, smallest first)."""
    return _prospect_pair(rows, season, war_provider=war_provider, largest_first=False,
                          top_n=top_n, root=root, record_exists=record_exists, frames=frames)


# the projection pair (dark until its looks are recorded)

def proj_looks(season: int, scope: str = "players") -> tuple:
    """The PROJ_LOOKS entries on label season S that hold `scope` closed (an entry
    with no `scope` holds both readers)."""
    if scope not in PROJ_SCOPES:
        raise ValueError(f"scope must be one of {PROJ_SCOPES}, not {scope!r}")
    return tuple(e for e in PROJ_LOOKS.get(int(season), ())
                 if scope in (e.get("scope") or PROJ_SCOPES))


def proj_looks_pending(season: int, *, scope: str = "players", root: Path | None = None,
                       record_exists=look_record_exists) -> list[str]:
    """The `record` names of the looks on label season S not yet recorded for `scope`."""
    return [str(e.get("record")) for e in proj_looks(season, scope)
            if not record_exists(e, root)]


def proj_blocked_on(season: int, *, root: Path | None = None,
                    record_exists=look_record_exists, scope: str = "players") -> str | None:
    """The sentence that keeps proj_above / proj_below (scope "players") or the
    Manager card's preseason column (scope "clubs") dark for S, or None when every
    registered look on label season S for that scope is recorded."""
    s = int(season)
    if s in PROJ_DARK_SEASONS:
        return (f"No projection was saved before the {s} season. From {s + 1} this card reads "
                f"the projection frozen the day before Opening Day, once that season's "
                f"registered checks are recorded.")
    if not proj_looks(s, scope):
        return (f"The {s} preseason projection has no registered check on file. This card "
                f"reads the projection frozen the day before Opening Day once every "
                f"registered check on the {s} label season is recorded.")
    if proj_looks_pending(s, scope=scope, root=root, record_exists=record_exists):
        return (f"The frozen projection for {s} is checked against {s}'s results after its "
                f"registered looks; this card opens when they are recorded.")
    return None


def _first_of(seq):
    return seq[0] if isinstance(seq, list) and seq else None


def preseason_read(season: int, *, scope: str = "players", root: Path | None = None,
                   vintage_dir: Path | None = None, record_exists=look_record_exists) -> dict:
    """The one reader of M15's frozen Opening Day file for label season S
    (docs/PROJ_FORWARD_VINTAGE_GATE.md sections 3 and 7). Never writes, never
    projects anything of its own.

    Order: the look gate for `scope` first (2026 and any season with a pending
    look return here, before the freeze log or the file is opened); then the
    season's one freeze log entry, which must be `frozen` and verify
    (proj_forward_vintage.entry_problems); then the file's bytes, whose sha256
    must equal the logged one. Scope "players" returns vets {mlbam: {war, p10,
    p90, key}} from vets[] war[0], warP10[0], warP90[0] and needs the entry's
    `label_provider` (the WAR series the frozen file was trained on); scope
    "clubs" returns clubs {club: wins} from team_outlook[].byYear[0].wins, joined
    through trades.canonical_org. A closed read carries `blocked_on` and empty maps."""
    s = int(season)
    out = {"season": s, "scope": scope, "blocked_on": None, "file": None, "sha256": None,
           "frozen_at": None, "label_provider": None, "vets": {}, "clubs": {}}
    blocked = proj_blocked_on(s, root=root, record_exists=record_exists, scope=scope)
    if blocked:
        out["blocked_on"] = blocked
        return out
    import proj_forward_vintage as pfv
    vdir = Path(vintage_dir) if vintage_dir is not None else pfv.VINTAGE_DIR
    closed_hash = (f"The frozen projection file for {s} does not match the hash in its "
                   f"freeze log, so this card stays closed.")
    try:
        entries = [e for e in pfv.load_log(vdir)["entries"] if e.get("season") == s]
    except ValueError:
        out["blocked_on"] = closed_hash
        return out
    if not entries:
        out["blocked_on"] = (f"No projection for {s} was frozen before Opening Day, so this "
                             f"card stays closed.")
        return out
    if len(entries) > 1:
        out["blocked_on"] = closed_hash
        return out
    entry = entries[0]
    if entry.get("status") == "no_season":
        out["blocked_on"] = (f"No {s} regular-season game was played, so no projection for "
                             f"{s} was frozen and this card stays closed.")
        return out
    if entry.get("status") != "frozen" or pfv.entry_problems(entry, vdir):
        out["blocked_on"] = closed_hash
        return out
    raw = (vdir / str(entry["file"])).read_bytes()
    if pfv.sha256_bytes(raw) != entry.get("sha256"):
        out["blocked_on"] = closed_hash
        return out
    label = entry.get("label_provider")
    if scope == "players" and not label:
        out["blocked_on"] = (f"The freeze log for {s} does not name the WAR series the frozen "
                             f"projection was trained on, so this card stays closed.")
        return out
    payload = json.loads(raw.decode("utf-8"))
    out.update(file=str(entry["file"]), sha256=entry["sha256"], frozen_at=entry.get("frozen_at"),
               label_provider=label)
    if scope == "players":
        for v in payload.get("vets") or []:
            m = _num(v.get("mlbam"))
            war = _num(_first_of(v.get("war")))
            if m is None or war is None:
                continue
            out["vets"][int(m)] = {"war": war, "p10": _num(_first_of(v.get("warP10"))),
                                   "p90": _num(_first_of(v.get("warP90"))), "key": v.get("key")}
    else:
        for t in payload.get("team_outlook") or []:
            c = _club_code(t.get("team"))
            wins = _num(((t.get("byYear") or [None])[0] or {}).get("wins"))
            if c and wins is not None:
                out["clubs"][c] = wins
    return out


def _proj_pair(rows, season, *, war_provider, largest_first, top_n, root, record_exists,
               blocked_on=None, displayed_provider=None) -> dict:
    sl_id = "proj_above" if largest_first else "proj_below"
    unit = war_unit_label(war_provider)
    blocked = blocked_on or proj_blocked_on(season, root=root, record_exists=record_exists)
    definition = (f"Season {unit} minus the {unit} projected for the season in the file frozen "
                  f"the day before Opening Day, with that file's P10 to P90 band as context.")
    caption = ("A season lost to injury falls under the floor, not on this list."
               if not largest_first else None)
    common = dict(kind="dumbbell", family="war", lamp_unit=None,
                  producer="the frozen Opening Day projection file; ewar.json",
                  registry="mlb_projections_vets", war_provider=war_provider,
                  definition=definition, floor_label=sl_player_floor_label() + " A row in the frozen file.",
                  frame_label=(f"Lit only when every registered check on the {int(season)} label "
                               f"season is recorded."), caption=caption)
    if blocked:
        # No row is scored, so no realized-minus-projected number exists anywhere.
        block = _sl_block(sl_id, season, [], n_pool=0, blocked_on=blocked, **common)
    else:
        scored = []
        for r in rows:
            if not _sl_player_floor(r):
                continue
            real, proj = _num(r.get("war_realized")), _num(r.get("war_proj"))
            if real is None or proj is None:
                continue
            d = real - proj
            extra = {"from": proj, "to": real, "value_display": _signed(d, 1),
                     "p10": _num(r.get("p10")), "p90": _num(r.get("p90")),
                     "realized_display": score_display(real),
                     "projected_display": score_display(proj)}
            if _num(r.get("displayed")) is not None:
                extra["displayed_display"] = score_display(r["displayed"])
            scored.append((d, r, extra))
        block = _sl_block(sl_id, season, _sl_rows(scored, largest_first=largest_first, top_n=top_n),
                          n_pool=len(scored), **common)
    if displayed_provider:
        block["displayed_provider"] = displayed_provider
    return block


def proj_above(rows, season, *, war_provider, top_n=SL_TOP_N, root=None,
               record_exists=look_record_exists, blocked_on=None, displayed_provider=None) -> dict:
    """Furthest above the preseason projection; rows {mlbam, name, club_code,
    war_realized, war_proj, p10, p90, pa, ip, displayed?} with war_realized on the
    frozen file's own WAR series (`war_provider`). Dark while proj_blocked_on(S) is
    set or the caller passes the reader's `blocked_on`."""
    return _proj_pair(rows, season, war_provider=war_provider, largest_first=True,
                      top_n=top_n, root=root, record_exists=record_exists,
                      blocked_on=blocked_on, displayed_provider=displayed_provider)


def proj_below(rows, season, *, war_provider, top_n=SL_TOP_N, root=None,
               record_exists=look_record_exists, blocked_on=None, displayed_provider=None) -> dict:
    return _proj_pair(rows, season, war_provider=war_provider, largest_first=False,
                      top_n=top_n, root=root, record_exists=record_exists,
                      blocked_on=blocked_on, displayed_provider=displayed_provider)


def manager_preseason(rows: list[dict], pre: dict | None, season: int) -> dict:
    """The Manager card's preseason column (AWARDS_PLAN 4.2, from 2027): W minus the
    club's wins in the frozen Opening Day file, scaled by GP / 162 as the score's
    expected wins are, so it reads W minus the frozen wins over a full season. Lit
    only on an open "clubs" read; otherwise no row gets a value. Adds
    `vs_preseason`, `vs_preseason_display` and `wins_preseason` to each row in
    place and returns the column block. It never replaces the score."""
    s = int(season)
    if pre is None:
        pre = {"blocked_on": proj_blocked_on(s, scope="clubs")}
    col = {"label": "W minus the wins in the projection frozen before Opening Day",
           "blocked_on": pre.get("blocked_on"), "file": pre.get("file"),
           "sha256": pre.get("sha256"), "frozen_at": pre.get("frozen_at"), "n_rows": 0}
    if col["blocked_on"]:
        return col
    clubs = pre.get("clubs") or {}
    for r in rows:
        wins = clubs.get(r.get("club"))
        w, gp = _num(r.get("w")), _num(r.get("gp"))
        if wins is None or w is None or gp is None:
            continue
        v = w - wins * gp / FULL_SEASON_GAMES
        r["wins_preseason"] = wins
        r["vs_preseason"] = v
        r["vs_preseason_display"] = _signed(v, 1)
        col["n_rows"] += 1
    return col


# next season's path

def _next_pair(rows, season, *, bundle_provider, realized_provider, largest_first, top_n) -> dict:
    if not bundle_provider or not realized_provider:
        raise ProviderMismatch("next_rise / next_drop need both the bundle's war_provider "
                               "and the realized side's provider")
    if str(bundle_provider) != str(realized_provider):
        raise ProviderMismatch(
            f"the projection bundle is on {bundle_provider} and the realized side on "
            f"{realized_provider}; the block keeps its last build")
    unit = war_unit_label(bundle_provider)
    scored = []
    for r in rows:
        if not _sl_player_floor(r):
            continue
        real, nxt = _num(r.get("war_realized")), _num(r.get("war_next"))
        if real is None or nxt is None:
            continue
        d = nxt - real
        extra = {"from": real, "to": nxt, "value_display": _signed(d, 1),
                 "realized_display": score_display(real), "projected_display": score_display(nxt)}
        if _num(r.get("displayed")) is not None:
            # the displayed series' season total, printed beside when the bundle's differs
            extra["displayed_display"] = score_display(r["displayed"])
        scored.append((d, r, extra))
    sl_id = "next_rise" if largest_first else "next_drop"
    return _sl_block(
        sl_id, season, _sl_rows(scored, largest_first=largest_first, top_n=top_n),
        kind="dumbbell", family="war", lamp_unit=None,
        producer="mlb_projections.json vets[].war[0]; ewar.json", registry="mlb_projections_vets",
        war_provider=str(bundle_provider), n_pool=len(scored),
        definition=(f"The {unit} projected for {int(season) + 1} minus the season's realized "
                    f"{unit}, both on the same WAR series."),
        floor_label=sl_player_floor_label() + " A row in the projection bundle.",
        frame_label=f"Realized {int(season)} and the path for {int(season) + 1} on {unit}.",
        caption=("The engine's path pulls unusual seasons back toward a player's longer "
                 "record, so both lists are mostly that."))


def next_rise(rows, season, *, bundle_provider, realized_provider, top_n=SL_TOP_N) -> dict:
    """Largest projected rise for S+1: vets[].war[0] minus realized S on THE SAME
    provider; raises ProviderMismatch when the two differ (I8). Rows: {mlbam, name,
    club_code, war_realized, war_next, pa, ip}."""
    return _next_pair(rows, season, bundle_provider=bundle_provider,
                      realized_provider=realized_provider, largest_first=True, top_n=top_n)


def next_drop(rows, season, *, bundle_provider, realized_provider, top_n=SL_TOP_N) -> dict:
    return _next_pair(rows, season, bundle_provider=bundle_provider,
                      realized_provider=realized_provider, largest_first=False, top_n=top_n)


# the five from the boards

def glove(fielders, season, *, top_n=SL_TOP_N) -> dict:
    """Highest DEM+: defense_leaderboards fielders[] qualified with inn >= 400,
    ranked by dem_plus_raw, printed dem_plus; context def_runs, pos, inn."""
    scored = []
    for r in fielders:
        inn = _num(r.get("inn")) or 0.0
        raw = _num(r.get("dem_plus_raw"))
        if raw is None or not r.get("qualified", True) or inn < GLOVE_MIN_INN:
            continue
        scored.append((raw, dict(r, ip=None, pa=inn), {
            "value_display": r.get("dem_plus"), "pos": r.get("pos"), "inn": inn,
            "def_runs": r.get("def_runs"), "club_code": r.get("team") or r.get("club_code")}))
    return _sl_block(
        "glove", season, _sl_rows(scored, largest_first=True, top_n=top_n),
        kind="index", family="dem_plus", lamp_unit=1.0,
        producer="defense_leaderboards.json fielders[].dem_plus_raw", registry="dem_plus",
        war_provider=None, n_pool=len(scored),
        definition="DEM+ on the season's defensive innings; the printed value is the board's.",
        floor_label=f"Floor: qualified on the board, at least {int(GLOVE_MIN_INN)} innings.",
        frame_label=f"Season {int(season)}, every qualified fielder.")


def _contact_pair(hitters, season, *, largest_first, top_n) -> dict:
    scored = []
    for r in hitters:
        pa = _num(r.get("pa")) or 0.0
        gap = _num(r.get("luck_gap"))
        if gap is None or pa < SL_MIN_PA:
            continue
        scored.append((gap, dict(r, ip=None), {
            "xwoba_minus_woba": gap, "value_display": _signed(gap, 3),
            "xwoba": r.get("xwoba"), "woba": r.get("woba"), "pa": pa,
            "club_code": r.get("team") or r.get("club_code")}))
    sl_id = "contact_ahead" if largest_first else "results_ahead"
    return _sl_block(
        sl_id, season, _sl_rows(scored, largest_first=largest_first, top_n=top_n),
        kind="signed", family=None, lamp_unit=0.005,
        producer="hitter_leaderboards.json hitters[], the Savant xwOBA minus wOBA column, served as xwoba_minus_woba",
        registry="xhem_plus", war_provider=None, n_pool=len(scored),
        definition=("Savant xwOBA minus wOBA in wOBA points, unshrunk: "
                    + ("contact quality above the results it produced."
                       if largest_first else "results above the contact quality behind them.")),
        floor_label=f"Floor: at least {SL_MIN_PA} PA.",
        frame_label=f"Season {int(season)}; the Savant join starts in 2026.")


def contact_ahead(hitters, season, *, top_n=SL_TOP_N) -> dict:
    """Contact quality ahead of results: the board's luck_gap (xwOBA minus wOBA),
    largest first, served under the key xwoba_minus_woba."""
    return _contact_pair(hitters, season, largest_first=True, top_n=top_n)


def results_ahead(hitters, season, *, top_n=SL_TOP_N) -> dict:
    """Results ahead of contact quality: the same key, most negative first."""
    return _contact_pair(hitters, season, largest_first=False, top_n=top_n)


def relief(relievers, season, *, top_n=SL_TOP_N) -> dict:
    """Highest REM+ in high-leverage relief: bullpen_leaderboards relievers[]
    qualified with IP >= 40 and gmLI >= 1.2, ranked by rem_plus_raw, printed rem_plus."""
    scored = []
    for r in relievers:
        ip = _num(r.get("ip")) or 0.0
        gmli = _num(r.get("gmli"))
        raw = _num(r.get("rem_plus_raw"))
        if raw is None or gmli is None or not r.get("qualified", True):
            continue
        if ip < RELIEF_MIN_IP or gmli < RELIEF_MIN_GMLI:
            continue
        scored.append((raw, dict(r, pa=None), {
            "value_display": r.get("rem_plus"), "ip": ip, "gmli": gmli,
            "wpa": r.get("wpa"), "saves": r.get("saves"),
            "club_code": r.get("team") or r.get("club_code")}))
    return _sl_block(
        "relief", season, _sl_rows(scored, largest_first=True, top_n=top_n),
        kind="index", family="rem_plus", lamp_unit=1.0,
        producer="bullpen_leaderboards.json relievers[].rem_plus_raw", registry="rem_plus",
        war_provider=None, n_pool=len(scored),
        definition="REM+ among relievers used in high-leverage innings; the printed value is the board's.",
        floor_label=(f"Floor: qualified on the board, at least {int(RELIEF_MIN_IP)} IP and a "
                     f"gmLI of at least {RELIEF_MIN_GMLI}."),
        frame_label=f"Season {int(season)}, every qualified reliever.")


def pitching_changes(club_rows, season, *, top_n=SL_TOP_N) -> dict:
    """Most realized value from pitching changes: management_board clubs.rows[]
    for S, mwpa_pitching_change with n_pitching_change >= 100, one family only."""
    scored = []
    for r in club_rows:
        if int(r.get("season") or 0) != int(season):
            continue
        n = _num(r.get("n_pitching_change")) or 0.0
        v = _num(r.get("mwpa_pitching_change"))
        if v is None or n < PITCHING_CHANGES_MIN_N:
            continue
        scored.append((v, {"club": r.get("club"), "club_code": r.get("club"), "name": r.get("club"),
                           "pa": n, "ip": None},
                       {"value_display": _signed(v, 2), "n_pitching_change": int(n)}))
    return _sl_block(
        "pitching_changes", season, _sl_rows(scored, largest_first=True, top_n=top_n),
        kind="signed", family=None, lamp_unit=0.25,
        producer="management_board.json clubs.rows[].mwpa_pitching_change", registry="mgmt_decision_ledger",
        war_provider=None, n_pool=len(scored),
        definition=("Realized win probability added by the club's pitching changes, one family "
                    "only and never summed with another; realized value, not skill."),
        floor_label=f"Floor: at least {PITCHING_CHANGES_MIN_N} pitching changes in the season.",
        frame_label=f"Season {int(season)}; the decision ledger covers 2018, 2019 and 2021 on.")


# --- what a superlative card prints beside its numbers (AWARDS_8) --------------------

#: The value ruler an index card's lamps are tiered on: the boards' own ladders
#: (DEM+ on z, REM+ on run, as the compare strip reads them). The block's
#: `family` names the metric; `ruler` names the EephusTiers ladder.
SL_RULERS = {"glove": "z", "relief": "run"}
SL_UNITS = {"pitching_changes": "WPA"}


def _f(v, spec: str):
    n = _num(v)
    return None if n is None else format(n, spec)


def _rate(v):
    s = _f(v, ".3f")
    return None if s is None else (s[1:] if s.startswith("0.") else s)


def _sl_context(sid: str, r: dict, S: int, wu, du) -> str | None:
    def part(v, text):
        return text if _num(v) is not None else None
    if sid.startswith("prospect_"):
        parts = [f"debut {r['debut_season']}" if r.get("debut_season") else None,
                 part(r.get("efv_at_debut"), f"eFV at debut {_f(r.get('efv_at_debut'), '.1f')}"),
                 part(r.get("war_display"), f"{_f(r.get('war_display'), '.1f')} {wu}")]
    elif sid.startswith("proj_"):
        parts = [part(r.get("projected_display"), f"projected {_f(r.get('projected_display'), '.1f')}, "
                      f"realized {_f(r.get('realized_display'), '.1f')} {wu}"),
                 part(r.get("p10"), f"P10 to P90 {_f(r.get('p10'), '.1f')} to {_f(r.get('p90'), '.1f')}")
                 if _num(r.get("p90")) is not None else None,
                 part(r.get("displayed_display"), f"the page's {du} {_f(r.get('displayed_display'), '.1f')}")
                 if du else None]
    elif sid.startswith("next_"):
        parts = [part(r.get("realized_display"), f"{S} {_f(r.get('realized_display'), '.1f')}, "
                      f"{S + 1} {_f(r.get('projected_display'), '.1f')} {wu}"),
                 part(r.get("displayed_display"), f"the page's {du} {_f(r.get('displayed_display'), '.1f')}")
                 if du else None]
    elif sid == "glove":
        parts = [r.get("pos"), part(r.get("inn"), f"{_f(r.get('inn'), '.0f')} innings"),
                 part(r.get("def_runs"), f"{_f(r.get('def_runs'), '+.1f')} defensive runs")]
    elif sid in ("contact_ahead", "results_ahead"):
        parts = [part(r.get("xwoba"), f"xwOBA {_rate(r.get('xwoba'))}"),
                 part(r.get("woba"), f"wOBA {_rate(r.get('woba'))}"),
                 part(r.get("pa"), f"{_f(r.get('pa'), '.0f')} PA")]
    elif sid == "relief":
        parts = [part(r.get("ip"), f"{_f(r.get('ip'), '.1f')} IP"),
                 part(r.get("gmli"), f"gmLI {_f(r.get('gmli'), '.2f')}"),
                 part(r.get("wpa"), f"WPA {_f(r.get('wpa'), '+.2f')}"),
                 part(r.get("saves"), f"{r.get('saves')} saves")]
    elif sid == "pitching_changes":
        parts = [part(r.get("n_pitching_change"), f"{r.get('n_pitching_change')} pitching changes")]
    else:
        parts = []
    return ", ".join(p for p in parts if p) or None


def sl_present(block: dict, season: int) -> dict:
    """A copy of a superlative block with what the page prints beside its numbers:
    `unit` (the value's unit), `war_unit`, `axis_label` (the dumbbell's two ends),
    `ruler` and each row's `context` line, each built from the block's own fields
    and its war_provider. Idempotent; the exporter applies it to the live, frozen
    and closed lists, so a frozen record is read and never rewritten."""
    b = copy.deepcopy(block)
    sid, S = str(b.get("id")), int(season)
    prov = b.get("war_provider")
    wu = war_unit_label(prov) if prov else None
    disp = b.get("displayed_provider")
    du = war_unit_label(disp) if disp and disp != prov else None
    unit, axis = SL_UNITS.get(sid), None
    if sid.startswith("prospect_") and wu:
        unit = "pts"
        axis = f"Pool percentile: hollow at the eFV at debut, filled at the season's {wu}."
    elif sid.startswith("proj_") and wu:
        unit = wu
        axis = f"{wu}: hollow at the preseason projection, filled at the season."
    elif sid.startswith("next_") and wu:
        unit = wu
        axis = f"{wu}: hollow at {S}, filled at the {S + 1} projection."
    for r in b.get("rows") or []:
        r["context"] = _sl_context(sid, r, S, wu, du)
    b.update(unit=unit, war_unit=wu, axis_label=axis, ruler=SL_RULERS.get(sid))
    return b


# --- labels (every string a card prints, built from fields) ---------------------------

def rule_text(award: str, war_provider: str) -> str:
    unit = war_unit_label(war_provider)
    if award == "MVP":
        return f"in-league {unit}, batting plus pitching, summed before rounding"
    if award == "CY":
        return f"in-league pitching {unit}"
    if award == "ROY":
        return f"in-league {unit}, both sides, among players who pass the rookie test"
    if award == "MOY":
        return f"club-season wins above the club's own earned {unit}"
    raise ValueError(f"unknown award {award!r}")


def rule_label(award: str, war_provider: str) -> str:
    """'The eephus selection by <rule>. Not a forecast of the BBWAA vote.'"""
    return f"The eephus selection by {rule_text(award, war_provider)}. Not a forecast of the BBWAA vote."


def floor_label(award: str, season: int) -> str:
    f = floors(award, season)
    if award == "MVP":
        return (f"Floor: in-league PA of at least {f['pa']} or IP of at least {f['ip']} "
                f"({MVP_PA_PER_GAME} PA and {MVP_IP_PER_GAME} IP per scheduled game, {f['g']} games).")
    if award == "CY":
        return (f"Floor: in-league IP of at least {f['ip']} ({CY_IP_PER_GAME} IP per scheduled "
                f"game, {f['g']} games); relievers stay eligible.")
    if award == "ROY":
        return f"Floor: PA of at least {f['pa']} or IP of at least {f['ip']} in the season."
    if award == "MOY":
        return "No floor: every club in the league is ranked."
    raise ValueError(f"unknown award {award!r}")


TIEBREAKS = {
    "MVP": ("unrounded score", "in-league WPA", "MLBAM id ascending"),
    "CY": ("unrounded score", "in-league IP", "SEM+ or REM+ raw", "MLBAM id ascending"),
    "ROY": ("unrounded score", "in-league WPA", "MLBAM id ascending"),
    "MOY": ("unrounded score", "wins minus Pythagorean wins", "club code"),
}


def tie_label(award: str) -> str:
    return "Ties: " + ", then ".join(TIEBREAKS[award]) + "."


def two_way_label(award: str, war_provider: str) -> str | None:
    unit = war_unit_label(war_provider)
    if award in ("MVP", "ROY"):
        return f"Two-way: batting and pitching {unit} both count; the row prints the split."
    if award == "CY":
        return "Pitching side only."
    return None


def eligibility_label(award: str) -> str | None:
    if award == "ROY":
        return (f"Rookie status: at-bats and innings from MLB's season lines; the "
                f"{ROOKIE_PROXY_DAYS_MAX}-day roster test is the site's estimate from MLB's "
                f"transaction log until the site measures service time.")
    if award == "MOY":
        return "Club-season. Manager names join when the manager ledger (M-MWAR-2) lands."
    return None


def rookie_gates_label() -> str:
    return (f"The rookie test: career MLB at-bats through the prior season of at most "
            f"{ROOKIE_PRIOR_AB_MAX}, career innings of at most {ROOKIE_PRIOR_IP_MAX:g}, and "
            f"an estimate of active-roster days of at most {ROOKIE_PROXY_DAYS_MAX}.")


def split_label(row: dict, war_provider: str) -> str | None:
    """'Split season: 3.1 eWAR v2 in the AL and 2.2 eWAR v2 in the NL.' from the row's shares."""
    share = row.get("share")
    if not share:
        return None
    unit = war_unit_label(war_provider)
    parts = []
    for lg in LEAGUES:
        s = share.get(lg) or {}
        tot = float(s.get("bat") or 0.0) + float(s.get("pit") or 0.0)
        parts.append(f"{score_display(tot)} {unit} in the {lg}")
    return "Split season: " + " and ".join(parts) + "."


def excluded_label(entry: dict) -> str:
    """'Outside the rookie test: Name (45-day estimate: 53 days).'"""
    days = entry.get("proxy_days")
    tail = (f" ({ROOKIE_PROXY_DAYS_MAX}-day estimate: {int(days)} days)"
            if _num(days) is not None else "")
    return f"Outside the rookie test: {entry.get('name')}{tail}."


def lead_sentence(award: str, top: list[dict], war_provider) -> str | None:
    """'1st leads 2nd by 2.5 eWAR v2.' or, on a tie, '1st and 2nd are tied on the
    rule; ordered by in-league WPA.' None with fewer than two rows."""
    if len(top) < 2:
        return None
    unit = "wins" if award == "MOY" else war_unit_label(war_provider)
    a, b = float(top[0]["score"]), float(top[1]["score"])
    if a == b:
        return f"1st and 2nd are tied on the rule; ordered by {TIEBREAKS[award][1]}."
    d = score_display(a - b)
    if d == 0.0:
        return f"1st leads 2nd by under {10 ** -SCORE_DECIMALS:.{SCORE_DECIMALS}f} {unit}."
    return f"1st leads 2nd by {d} {unit}."


def tiebreak_sentence(award: str, top: list[dict]) -> str | None:
    """Names every tie on the unrounded score inside the ballot, else None."""
    groups: dict = {}
    for r in top:
        groups.setdefault(float(r["score"]), []).append(r)
    tied = [g for g in groups.values() if len(g) > 1]
    if not tied:
        return None
    parts = []
    for g in tied:
        names = ", ".join(str(r.get("name") or r.get("club")) for r in g)
        parts.append(f"{names} at {score_display(g[0]['score'])}")
    return "Tied on the rule: " + "; ".join(parts) + f"; ordered by {TIEBREAKS[award][1]}."


def selection_caption(season: int, frozen: bool) -> str:
    """The hero caption: 'The eephus selection, 1st place, <season>' once frozen,
    'Current leaders on the rule, <season>' before."""
    return (f"The eephus selection, 1st place, {int(season)}" if frozen
            else f"Current leaders on the rule, {int(season)}")


def drift_unit_label(war_provider: str) -> str:
    """'Now, eWAR': the drift column's unit from its own block's provider."""
    return f"Now, {war_unit_label(war_provider)}"


def drift_tooltip(frozen_at: str) -> str:
    return f"The score on today's files. The selection stays as frozen on {frozen_at}."


def rules_block(award: str, season: int, war_provider: str, *, blocked_on: str | None = None) -> dict:
    """The payload's rules[award] entry (AWARDS_PLAN 4.4), every label built here."""
    unit = "wins" if award == "MOY" else war_unit_label(war_provider)
    return {
        "name": AWARD_NAMES[award],
        "label": rule_label(award, war_provider),
        "floor_label": floor_label(award, season),
        "tie_label": tie_label(award),
        "two_way_label": two_way_label(award, war_provider),
        "eligibility_label": eligibility_label(award),
        "blocked_on": blocked_on,
        "family": None if award == "MOY" else "war",
        "unit": unit,
        "decimals": SCORE_DECIMALS,
        "lamp_unit": LAMP_UNITS[award],
        "tick_every": TICK_EVERY[award],
        "registry": SELECTION_REGISTRY,
        "war_provider": war_provider,
    }


def ballot_rules_payload() -> dict:
    return copy.deepcopy(BALLOT_RULES)


def does_not_claim_lines(selection_provider: str, *, frozen_at: str | None = None,
                         now_provider: str | None = None) -> list[str]:
    """'What this page does not claim' (AWARDS_PLAN 5.15), line (5) built from the
    providers of the selection and of the drift column."""
    unit = war_unit_label(selection_provider)
    if frozen_at:
        line5 = f"The selection reads {unit}, as frozen {frozen_at}"
        if now_provider:
            line5 += f"; Now values read {war_unit_label(now_provider)}."
        else:
            line5 += "."
    else:
        line5 = f"The selection reads {unit} on today's files."
    return [
        "The eephus selection is not a forecast of the BBWAA vote, and the page prints no "
        "probability of winning.",
        "It is not a statement about who merits an award, only the order one published rule gives.",
        f"The Rookie test estimates MLB's {ROOKIE_PROXY_DAYS_MAX}-day roster count from the "
        f"transaction log until the site measures service time.",
        "Manager of the Year ranks club-seasons, a result players, coaches and the front office "
        "share; the decision values on In-Game Management are realized value, not skill, and "
        "are never summed across families.",
        line5,
        "Superlatives measure distance from a grade or a projection and say nothing about "
        "effort or character.",
        "My Ballot keeps choices in this browser only; the site collects no ballots.",
    ]


def credit_lines(shows, *, mlb_copyright: str | None = None, war_provider: str | None = None) -> list[str]:
    """The credits whose data the page shows, in CREDIT_LINES order. Under the
    displayed provider ewar_v3 the "bref" line names eWAR's FanGraphs base."""
    shows = set(shows)
    if war_provider == "ewar_v3" and "bref" in shows:
        shows.discard("bref")
        shows.add("bref_v3")
    out = []
    for key, line in CREDIT_LINES.items():
        if key not in shows:
            continue
        if key == "mlb":
            line = line.format(mlb_copyright=(mlb_copyright or "")).rstrip()
        elif key == "fangraphs":
            line = line.format(fwar=war_unit_label("fwar"))
        out.append(line)
    return out


# --- the copy scan -------------------------------------------------------------------

def verdict_hits(text) -> list[str]:
    """Every verdict word of AWARDS_PLAN 5.15, every tools/copy_lint.py BAN hit and
    every em or en dash in `text` (a string, or anything whose strings are walked)."""
    hits: list[str] = []
    for s in _strings(text):
        for m in VERDICT_RE.finditer(s):
            hits.append(f"verdict:{m.group(0)}")
        for m in _ban_re().finditer(s):
            hits.append(f"ban:{m.group(0)}")
        if EM_DASH in s:
            hits.append("dash:em")
        if EN_DASH in s:
            hits.append("dash:en")
    return hits


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _strings(v)


_BAN_RE = None


def _ban_re():
    global _BAN_RE
    if _BAN_RE is None:
        tools = str(ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import copy_lint
        _BAN_RE = copy_lint.BAN_RE
    return _BAN_RE
