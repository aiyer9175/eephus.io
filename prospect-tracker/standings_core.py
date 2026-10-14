# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Scores / Standings: the pure standings core (STANDINGS_1_CORE_RULES, plan
STANDINGS_PLAN.md sections 4.2, 4.6 and 6).

Standard library only AT RUNTIME, not only at import: this module imports the
standard library and `scores_core` and nothing else. It never imports `trades`
(which pulls in requests, scrapers with bs4, and stats) and never imports or
calls `franchise_export` (whose `division_champions` imports `trades` inside
its body). The division champion rule of FS_1 is applied here through the
SCORES_1 club literal, and `test_standings_core.py` alone imports both modules
to pin the two rules equal. No network, no clock: every payload, every date
stamp and every path is passed in by the caller (the scores job, STANDINGS_2).

The eleven items of plan 4.6:

  1. `STANDINGS_LIVE` and `STANDINGS_CHARTS` (both False; LIVE may be True only
     when `scores_core.SCORES_LIVE` is, CHARTS only when LIVE is);
  2. `parse_standings(payload, as_of)`: StatsAPI /api/v1/standings
     `records[].teamRecords[]` into rows keyed by MLBAM id through the club
     literal, with the renamed keys (no `record*` key ever leaves here);
  3. computed `gb`, `wcgb`, `e` and the leader's magic fallback, served beside
     the feed values, every disagreement listed in
     `accountability.feed_disagreements`;
  4. the marks rule and `division_champions(records, live)`;
  5. `x_wl` copied from xWinLoss and `x_exp` 1.83 only while T9 reproduces
     every row;
  6. `FORMAT[season]`;
  7. `tiebreak_text(season)` and `head_to_head(games, a, b)`;
  8. `build_race(games, season, snapshots)` and `race_matches_snapshots`;
  9. the four file builders, one compact writer and the validator (scores_core
     rules 1, 5, 6, 7, 9, 10, 11; rule 4 amended for a top-level `copyright`
     key holding StatsAPI's line verbatim; T1 to T20 of plan 6);
 10. `write_labs_copy()`, the tracked unpublished copy of the final tables;
 11. the served derivations (`rdg`, `rs_g`, `ra_g`, `w_xw`, `left`, `l10_seq`,
     `opening_day`, `k90`) and the seeds (`seed`, `qualified`,
     `qualified_text`), so the page derives none of them.

The WCGB convention here keeps MLB's printed form: the feed's "+9.5" (ahead of
the cutoff) is `wcgb` 9.5 with `wc_ahead` true. The nightly reader
`fa_fit_backtest.standings_now` serves a signed number for its numeric readers
instead; the two differ on purpose (plan C20).
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

import scores_core as sc

# --------------------------------------------------------------------------- #
# 1. Flags
# --------------------------------------------------------------------------- #
#: Class 2 module flag (Part 8 8.A). True only when scores_core.SCORES_LIVE is
#: True; only STANDINGS_7_FLIP turns it on. While False the job writes standings
#: files only under its preview OUT and nothing standings-related is served.
STANDINGS_LIVE = False
#: The Charts view and the Race disclosures. True only when STANDINGS_LIVE is.
STANDINGS_CHARTS = False

SCHEMA = 1

# --------------------------------------------------------------------------- #
# Literals
# --------------------------------------------------------------------------- #
#: StatsAPI's copyright line, verbatim (two spaces after "L.P."); the year is
#: the payload's own. Rule 4 as amended exempts exactly this line in a
#: top-level `copyright` key of a standings file, and nothing else.
COPYRIGHT_RE = re.compile(
    r"^Copyright \d{4} MLB Advanced Media, L\.P\.  Use of any content on this page "
    r"acknowledges agreement to the terms posted here "
    + re.escape(sc.MLB_TERMS_URL) + r"$")

LEAGUE_CODE = {103: "AL", 104: "NL"}
DIVISION_CODE = {201: "ALE", 202: "ALC", 200: "ALW", 204: "NLE", 205: "NLC", 203: "NLW"}
DIVISION_LEAGUE = {201: 103, 202: 103, 200: 103, 204: 104, 205: 104, 203: 104}

#: Club -> (league id, division id) from 2013 on (Houston moved to the AL West
#: in 2013). Pinned by a test to the tracked copy of every season 2000 to 2025.
_DIVISION_OF_ID = {
    110: 201, 111: 201, 147: 201, 139: 201, 141: 201,      # AL East
    145: 202, 114: 202, 116: 202, 118: 202, 142: 202,      # AL Central
    117: 200, 108: 200, 133: 200, 136: 200, 140: 200,      # AL West
    144: 204, 146: 204, 121: 204, 143: 204, 120: 204,      # NL East
    112: 205, 113: 205, 158: 205, 134: 205, 138: 205,      # NL Central
    109: 203, 115: 203, 119: 203, 135: 203, 137: 203,      # NL West
}


def division_of(team_id, season: int) -> int | None:
    """The division id of an MLBAM club id in a season (1998 on): Houston
    (117) is NL Central before 2013."""
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return None
    if tid == 117 and int(season) < 2013:
        return 205
    return _DIVISION_OF_ID.get(tid)


#: 6. The season format (plan 4.6 item 6). wild-card spots per league: 1 for
#: 1995 to 2011, 2 for 2012 to 2019 and 2021, 3 from 2022; 2020's field was the
#: top two of each division plus two wild cards per league; byes for the top
#: two division winners from 2022; 162 games scheduled, 60 in 2020 (and 144 in
#: the strike-shortened 1995).
NOTE_2020 = "2020: a 60-game season; eight clubs per league reached the postseason."


def _format_row(season: int) -> dict:
    if season == 2020:
        wc, div_spots, sched, notes = 2, 2, 60, [NOTE_2020]
    elif season >= 2022:
        wc, div_spots, sched, notes = 3, 1, 162, []
    elif season >= 2012:
        wc, div_spots, sched, notes = 2, 1, 162, []
    else:
        wc, div_spots, sched, notes = 1, 1, (144 if season == 1995 else 162), []
    return {"wc_spots": wc, "division_spots": div_spots, "per_league": 3 * div_spots + wc,
            "byes": 2 if season >= 2022 else 0, "scheduled": sched, "notes": notes}


FORMAT = {y: _format_row(y) for y in range(1995, 2027)}


def format_for(season) -> dict:
    """FORMAT[season], and the from-2022 rule for a season after the table."""
    y = int(season)
    if y in FORMAT:
        return dict(FORMAT[y])
    if y > max(FORMAT):
        return _format_row(y)
    raise KeyError(f"no format for season {y}")


#: 7. Tiebreak text, keyed by SEASON (2020 broke ties by rule with no extra
#: game, so an era split at 2022 would misstate it).
TIEBREAK_BY_RULE = ("Ties for a postseason spot are broken by rule, not by an extra game, "
                    "head-to-head record first. The order on this page is MLB's own.")
TIEBREAK_2020 = ("Ties for a postseason spot were broken by rule, not by an extra game. "
                 "The order on this page is MLB's own.")
TIEBREAK_EXTRA_GAME = ("Ties for a postseason spot were settled by an extra game, counted in the "
                       "standings. The order on this page is MLB's own.")


def tiebreak_text(season) -> str:
    y = int(season)
    if y >= 2022:
        return TIEBREAK_BY_RULE
    if y == 2020:
        return TIEBREAK_2020
    return TIEBREAK_EXTRA_GAME


#: 11. How a seeded club qualified, final file and in season (never typed in
#: the page).
QUALIFIED_TEXT = {
    "final": {"division": "Division winner", "division_second": "Division second place",
              "wild_card": "Wild card"},
    "in_season": {"division": "Leads the division", "division_second": "Second in the division",
                  "wild_card": "Holds a wild card spot"},
}

#: 5. MLB's expected record: Pythagorean at this exponent over W + L games.
X_EXPONENT = 1.83

#: The ten split types read, renamed (plan 4.6 item 2).
SPLIT_KEYS = (("home", "home"), ("away", "away"), ("oneRun", "one_run"), ("extraInning", "extra"),
              ("winners", "winners"), ("left", "vs_l"), ("right", "vs_r"), ("day", "day"),
              ("night", "night"))
_SPLIT_TYPES = tuple(t for t, _k in SPLIT_KEYS) + ("lastTen",)

# --------------------------------------------------------------------------- #
# File kinds (rule 6 budgets as test-time pins, ceilings four times larger)
# --------------------------------------------------------------------------- #
_KB = 1024
KIND_SEASON = "standings_season"
KIND_RACE = "standings_race"
KIND_PHIST = "standings_phist"
KIND_SNAPSHOT = "standings_snapshot"
STANDINGS_KINDS = (KIND_SEASON, KIND_RACE, KIND_PHIST, KIND_SNAPSHOT)
sc.register_file_kind(KIND_SEASON, budget=40 * _KB, name_re=r"^standings/\d{4}\.json$",
                      copyright_exempt=True)
sc.register_file_kind(KIND_RACE, budget=160 * _KB, name_re=r"^standings/\d{4}-race\.json$",
                      copyright_exempt=True)
sc.register_file_kind(KIND_PHIST, budget=256 * _KB, name_re=r"^standings/\d{4}-phist\.json$",
                      copyright_exempt=True)
sc.register_file_kind(KIND_SNAPSHOT, budget=40 * _KB,
                      name_re=r"^standings/\d{4}/\d{4}-\d{2}-\d{2}\.json$", copyright_exempt=True)

PHIST_REGULAR_FIELDS = ("p_div", "p_post", "p_bye", "p_pennant", "p_ws")
PHIST_POST_FIELDS = ("p_pennant", "p_ws")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _int(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        return int(str(x).strip())
    except (TypeError, ValueError):
        return None


def _half(x: Fraction) -> float:
    """An exact half-game quantity as a float (halves are exact in binary)."""
    return float(x)


def round2(num, den):
    """num / den rounded half up to two decimals; None when den is 0."""
    if not den:
        return None
    q = (Decimal(int(num)) / Decimal(int(den))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)


def _gb_str(s):
    """A feed games-back string as a number and an ahead flag: '-' 0.0, '+9.5'
    (9.5, True), '4.5' (4.5, False); None for a missing entry."""
    if s is None:
        return None, False
    s = str(s).strip()
    if s in ("-", ""):
        return 0.0, False
    ahead = s.startswith("+")
    try:
        return float(s.lstrip("+")), ahead
    except ValueError:
        return None, False


def _num_or_e(s):
    """A feed magic or elimination number: an int, "E", or None for '-' or a
    missing key."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "E":
        return "E"
    return _int(s)


def _wl(d) -> list | None:
    if not isinstance(d, dict):
        return None
    w, l = _int(d.get("wins")), _int(d.get("losses"))
    if w is None or l is None:
        return None
    return [w, l]


def _team_records(payload):
    """(record, teamRecord, feed order) in the feed's order."""
    i = 0
    for rec in (payload or {}).get("records") or []:
        for tr in rec.get("teamRecords") or []:
            yield rec, tr, i
            i += 1


def _season_of(payload, as_of) -> int:
    for _rec, tr, _i in _team_records(payload):
        y = _int(tr.get("season"))
        if y:
            return y
    return int(str(as_of)[:4])


# --------------------------------------------------------------------------- #
# 4. The division champion (FS_1's rule, applied here through the literal)
# --------------------------------------------------------------------------- #
def division_champions(records, live: bool) -> dict:
    """{division id: club code or None} by FS_1's rule (franchise_export
    .division_champions, pinned equal by a test): a completed season (live
    False) gives the unique divisionRank-1 club of each division; the live
    season (live True) gives that club only once its clinchIndicator is 'y' or
    'z'. Zero or two rank-1 clubs give None. Never `divisionChamp`, never
    `clinched` (the 2026 feed flags the wild-card Phillies; the 2012 feed leaves
    `clinched` false on clinched clubs)."""
    out: dict = {}
    for rec in records or []:
        div = (rec.get("division") or {}).get("id")
        if div is None:
            continue
        firsts = [tr for tr in rec.get("teamRecords") or [] if str(tr.get("divisionRank") or "") == "1"]
        champ = None
        if len(firsts) == 1:
            tr = firsts[0]
            if not live or tr.get("clinchIndicator") in ("y", "z"):
                champ = sc.club_code((tr.get("team") or {}).get("id"))
        out[div] = champ
    return out


# --------------------------------------------------------------------------- #
# 2 to 5, 11. Parse one standings response into rows
# --------------------------------------------------------------------------- #
def _xw(n: int, rs: int, ra: int, exp: float = X_EXPONENT) -> int:
    """MLB's expected wins over `n` games played (W + L + T: a tie game counts,
    which the 2016 Cubs' 108-54 needs; 107 over W + L)."""
    if n == 0 or (rs == 0 and ra == 0):
        return 0 if n == 0 else sc.round_half_up(n / 2)
    a, b = float(rs) ** exp, float(ra) ** exp
    return sc.round_half_up(n * a / (a + b))


def t9_holds(rows) -> bool:
    """T9 on every row: xWinLoss is Pythagorean at 1.83 over the games played
    (its W + L equals W + L + T). A club with no game yet carries no
    xWinLoss (probe p3) and has nothing to reproduce."""
    return bool(rows) and all(
        (r.get("x_wl") is None and r["gp"] == 0) or (
            r.get("x_wl") is not None and r["x_wl"][0] + r["x_wl"][1] == r["w"] + r["l"] + r["t"]
            and r["x_wl"][0] == _xw(r["w"] + r["l"] + r["t"], r["rs"], r["ra"])) for r in rows)


def _games_ahead(a: tuple, b: tuple) -> Fraction:
    """Signed games a is ahead of b ((Wa - La) - (Wb - Lb)) / 2."""
    return Fraction((a[0] - a[1]) - (b[0] - b[1]), 2)


def _disagree(out: list, field: str, code, feed, served, why: str) -> None:
    out.append({"field": field, "code": code, "feed": feed, "served": served, "why": why})


def parse_standings(payload, as_of, *, final: bool = False) -> dict:
    """One StatsAPI standings response as of `as_of` (the `date` the job sent,
    never MLB's lastUpdated) into `{season, as_of, final, copyright, rows,
    feed_disagreements}`. Rows keep the feed's order and carry the renamed keys
    of plan 4.6 item 2, the computed values of item 3, the marks of item 4,
    the expected record of item 5 and the seeds of item 11. The game-list
    derivations (`left`, `l10_seq`) are set by `build_season_file`."""
    season = _season_of(payload, as_of)
    fmt = format_for(season)
    dis: list = []
    rows: list = []
    order: dict = {}
    raw_by_code: dict = {}
    for rec, tr, i in _team_records(payload):
        tid = _int((tr.get("team") or {}).get("id"))
        code = sc.club_code(tid)
        if code is None:
            _disagree(dis, "team_id", None, tid, None, "an id outside the 30-club literal is dropped")
            continue
        div_id = _int((rec.get("division") or {}).get("id"))
        lg_id = _int((rec.get("league") or {}).get("id")) or DIVISION_LEAGUE.get(div_id)
        recs = tr.get("records") or {}
        splits = {s.get("type"): _wl(s) for s in recs.get("splitRecords") or [] if isinstance(s, dict)}
        lg_recs = recs.get("leagueRecords") or []
        own_lg = next((x for x in lg_recs if _int((x.get("league") or {}).get("id")) == lg_id), None)
        other_lg = next((x for x in lg_recs if _int((x.get("league") or {}).get("id")) not in (lg_id, None)), None)
        own_div = next((x for x in recs.get("divisionRecords") or []
                        if _int((x.get("division") or {}).get("id")) == div_id), None)
        xr = next((x for x in recs.get("expectedRecords") or [] if x.get("type") == "xWinLoss"), None)
        w, l = _int(tr.get("wins")) or 0, _int(tr.get("losses")) or 0
        rs, ra = _int(tr.get("runsScored")) or 0, _int(tr.get("runsAllowed")) or 0
        pct_s = tr.get("winningPercentage")
        try:
            pct = float(pct_s) if pct_s not in (None, "", "-", ".---") else None
        except (TypeError, ValueError):
            pct = None
        row = {
            "code": code, "team_id": tid,
            "lg": LEAGUE_CODE.get(lg_id), "div": DIVISION_CODE.get(div_id),
            "w": w, "l": l, "t": _int((tr.get("leagueRecord") or {}).get("ties")) or 0,
            "gp": _int(tr.get("gamesPlayed")) or 0, "pct": pct,
            "rs": rs, "ra": ra, "rd": _int(tr.get("runDifferential")),
            "gb": None, "gb_feed": tr.get("divisionGamesBack"),
            "wcgb": None, "wc_ahead": False, "wcgb_feed": tr.get("wildCardGamesBack"),
            "lgb": _gb_str(tr.get("leagueGamesBack"))[0], "mlbgb": _gb_str(tr.get("sportGamesBack"))[0],
            "ranks": {"div": _int(tr.get("divisionRank")), "lg": _int(tr.get("leagueRank")),
                      "mlb": _int(tr.get("sportRank")), "wc": _int(tr.get("wildCardRank"))},
            "mark": tr.get("clinchIndicator") if tr.get("clinchIndicator") in ("x", "y", "z", "w") else None,
            "e": False,
            "magic": None, "elim_div": _num_or_e(tr.get("eliminationNumberDivision")),
            "elim_wc": _num_or_e(tr.get("wildCardEliminationNumber")),
            "streak": (tr.get("streak") or {}).get("streakCode"),
            "l10": splits.get("lastTen"),
            "split": {k: splits.get(t) for t, k in SPLIT_KEYS},
            "vs_div": _wl(own_div), "vs_lg": _wl(own_lg), "intr": _wl(other_lg),
            "x_wl": _wl(xr), "x_exp": None,
            "rdg": None, "rs_g": None, "ra_g": None, "w_xw": None, "left": None, "l10_seq": None,
            "seed": None, "qualified": None, "qualified_text": None,
        }
        row["_div_id"], row["_lg_id"], row["_magic_feed"] = div_id, lg_id, tr.get("magicNumber")
        if row["mark"] is None and tr.get("clinchIndicator") not in (None, ""):
            _disagree(dis, "mark", code, tr.get("clinchIndicator"), None, "an unknown clinch letter is not served")
        order[code] = i
        raw_by_code[code] = tr
        rows.append(row)

    by_div: dict = {}
    by_lg: dict = {}
    for r in rows:
        by_div.setdefault(r["_div_id"], []).append(r)
        by_lg.setdefault(r["_lg_id"], []).append(r)

    # ---- 3. GB from the division's best W minus L (T5) -----------------
    for div_rows in by_div.values():
        best = max(r["w"] - r["l"] for r in div_rows)
        for r in div_rows:
            r["gb"] = _half(Fraction(best - (r["w"] - r["l"]), 2))
            feed, _a = _gb_str(r["gb_feed"])
            if feed is not None and feed != r["gb"]:
                _disagree(dis, "gb", r["code"], r["gb_feed"], r["gb"],
                          "games back from the division's best W minus L")

    # ---- 3. WCGB from the last qualifying wild card (T6) ---------------
    for lg_rows in by_lg.values():
        cut = fmt["wc_spots"]
        cands = sorted((r for r in lg_rows if r["ranks"]["wc"] is not None),
                       key=lambda r: (r["ranks"]["wc"], order[r["code"]]))
        ref = next((r for r in cands if r["ranks"]["wc"] == cut), None)
        if ref is None and len(cands) >= cut:
            ref = cands[cut - 1]
            _disagree(dis, "wcgb", ref["code"], None, None,
                      f"no club holds wildCardRank {cut}; the {cut}th wild-card club in feed order is the line")
        for r in lg_rows:
            if r["ranks"]["wc"] is None or ref is None:
                r["wcgb"], r["wc_ahead"] = None, False
            else:
                ahead = _games_ahead((r["w"], r["l"]), (ref["w"], ref["l"]))
                r["wcgb"], r["wc_ahead"] = _half(abs(ahead)), bool(ahead > 0)
            feed, feed_ahead = _gb_str(r["wcgb_feed"])
            if r["wcgb"] is None:
                continue
            if feed is None or feed != r["wcgb"] or (feed_ahead != r["wc_ahead"] and r["wcgb"] != 0):
                _disagree(dis, "wcgb", r["code"], r["wcgb_feed"],
                          ("+" if r["wc_ahead"] else "") + f"{r['wcgb']:.1f}",
                          "games from the club holding the last wild card spot")

    # ---- 3. The leader's magic number fallback (T7) ---------------------
    for div_rows in by_div.values():
        clinched = any(r["mark"] in ("y", "z") for r in div_rows)
        runner = next((r for r in div_rows if r["ranks"]["div"] == 2), None)
        for r in div_rows:
            m = _num_or_e(r["_magic_feed"])
            r["magic"] = m if isinstance(m, int) else None
            if (r["ranks"]["div"] == 1 and str(r["_magic_feed"]).strip() == "-" and not clinched
                    and runner is not None and isinstance(runner["elim_div"], int)):
                r["magic"] = runner["elim_div"]
                _disagree(dis, "magic", r["code"], "-", r["magic"],
                          "the division is not clinched; the runner-up's division elimination number")

    # ---- 4. The marks rule ---------------------------------------------
    for r in rows:
        r["e"] = bool(r["mark"] is None and (r["elim_wc"] == "E" or final))
        if r["e"] and r["elim_wc"] != "E":
            _disagree(dis, "e", r["code"], tr_wc_elim(raw_by_code[r["code"]]), True,
                      "the season is complete and the club holds no mark")

    # ---- 5. Expected record (T9) ---------------------------------------
    t9 = t9_holds(rows)
    for r in rows:
        r["x_exp"] = X_EXPONENT if t9 else None

    # ---- 11. Per-row derivations that need no game list ----------------
    for r in rows:
        r["rdg"] = round2(r["rd"], r["gp"]) if r["rd"] is not None else None
        r["rs_g"] = round2(r["rs"], r["gp"])
        r["ra_g"] = round2(r["ra"], r["gp"])
        r["w_xw"] = (r["w"] - r["x_wl"][0]) if r["x_wl"] is not None else None
        if final:
            r["left"] = 0

    # ---- 11. Seeds -----------------------------------------------------
    _assign_seeds(rows, by_div, by_lg, fmt, order, final, dis)

    # ---- 3. T7: MLB's magic and elimination numbers outside the band ---
    for code, label, value, want in t7_misses(rows, fmt):
        _disagree(dis, label.replace(" ", "_"), code, value, value,
                  f"MLB's number is served; G + 1 - W - L gives {want} (or one less)")

    for r in rows:
        for k in ("_div_id", "_lg_id", "_magic_feed"):
            r.pop(k, None)
    return {"season": season, "as_of": str(as_of) if as_of is not None else None, "final": bool(final),
            "copyright": (payload or {}).get("copyright"), "rows": rows, "feed_disagreements": dis}


def tr_wc_elim(tr: dict):
    return tr.get("wildCardEliminationNumber")


def _assign_seeds(rows, by_div, by_lg, fmt, order, final, dis) -> None:
    texts = QUALIFIED_TEXT["final" if final else "in_season"]

    def ordered(rs, key):
        rs = sorted(rs, key=lambda r: (key(r) if key(r) is not None else 10 ** 6, order[r["code"]]))
        for a, b in zip(rs, rs[1:]):
            if key(a) is not None and key(a) == key(b):
                _disagree(dis, "seed", b["code"], key(b), None,
                          f"a repeated rank at a cut; ordered after {a['code']} by the feed's order")
        return rs

    for lg_id, lg_rows in by_lg.items():
        leaders = []
        for div_id in sorted({r["_div_id"] for r in lg_rows}):
            div_rows = [r for r in by_div[div_id]]
            firsts = [r for r in div_rows if r["ranks"]["div"] == 1]
            if len(firsts) != 1:
                pick = sorted(firsts or div_rows, key=lambda r: ((r["ranks"]["div"] or 99), order[r["code"]]))[0]
                _disagree(dis, "seed", pick["code"], len(firsts), None,
                          "not exactly one divisionRank-1 club; the first in the feed's order leads")
                firsts = [pick]
            leaders.append(firsts[0])
        seeded = [(r, "division") for r in ordered(leaders, lambda r: r["ranks"]["lg"])]
        taken = {r["code"] for r, _q in seeded}
        if fmt["division_spots"] == 2:
            seconds = [r for r in lg_rows if r["ranks"]["wc"] is None and r["code"] not in taken]
            seeded += [(r, "division_second") for r in ordered(seconds, lambda r: r["ranks"]["lg"])]
            taken |= {r["code"] for r in seconds}
        wcs = [r for r in lg_rows if r["code"] not in taken and r["ranks"]["wc"] is not None
               and r["ranks"]["wc"] <= fmt["wc_spots"]]
        wcs = ordered(wcs, lambda r: r["ranks"]["wc"])
        if len(wcs) != fmt["wc_spots"]:
            _disagree(dis, "seed", None, len(wcs), fmt["wc_spots"],
                      f"{LEAGUE_CODE.get(lg_id)}: wild-card ranks 1 to {fmt['wc_spots']} name {len(wcs)} clubs")
            wcs = wcs[:fmt["wc_spots"]]
        seeded += [(r, "wild_card") for r in wcs]
        for n, (r, q) in enumerate(seeded, start=1):
            r["seed"], r["qualified"], r["qualified_text"] = n, q, texts[q]


# --------------------------------------------------------------------------- #
# Games: the normalised list, game state, left, last ten, head to head
# --------------------------------------------------------------------------- #
def games_from_schedule(payload) -> list[dict]:
    """A StatsAPI /api/v1/schedule payload (gameType R) as the normalised game
    list: `{pk, date, official, start, gn, away, home, away_r, home_r,
    state}` in the schedule's order, one item per schedule entry. `date` is
    the date bucket the entry sits under (a suspended game appears under the
    date it was suspended and again under the date it became final), falling
    back to `officialDate`; `official` is the entry's `officialDate`; `state`
    is scores_core's state rule."""
    out = []
    for d in (payload or {}).get("dates") or []:
        for g in d.get("games") or []:
            if g.get("gameType") not in (None, "R"):
                continue
            teams = g.get("teams") or {}
            a, h = teams.get("away") or {}, teams.get("home") or {}
            state, _reason = sc.game_state(g.get("status"))
            out.append({"pk": _int(g.get("gamePk")), "date": d.get("date") or g.get("officialDate"),
                        "official": g.get("officialDate"), "start": g.get("gameDate"), "gn": _int(g.get("gameNumber")) or 1,
                        "away": _int((a.get("team") or {}).get("id")),
                        "home": _int((h.get("team") or {}).get("id")),
                        "away_r": _int(a.get("score")), "home_r": _int(h.get("score")), "state": state})
    return out


def final_games(games) -> list[dict]:
    """Each game once, counted on the date it became final, ordered by date,
    then game number, then start time, then pk (doubleheaders kept in order).
    A suspended entry is never counted; a pk with a final entry counts once.
    When the schedule lists one game as final under two dates, the entry under
    its own officialDate wins (StatsAPI's 2026 schedule lists 824912 final
    under 2026-06-16 and 2026-06-17, officialDate 2026-06-16, and MLB's
    standings count it through 2026-06-16); otherwise the later date."""
    def rank(g):
        own = g.get("official") is not None and str(g.get("date")) == str(g.get("official"))
        return (own, str(g.get("date")))

    finals: dict = {}
    for g in games or []:
        if g.get("state") != "final" or g.get("away_r") is None or g.get("home_r") is None:
            continue
        pk = g.get("pk")
        prev = finals.get(pk)
        if prev is None or rank(g) > rank(prev):
            finals[pk] = g
    return sorted(finals.values(), key=lambda g: (str(g.get("date")), g.get("gn") or 1,
                                                   str(g.get("start") or ""), g.get("pk") or 0))


def _team_id(x):
    """A club as an MLBAM id, from an id or a site code."""
    if isinstance(x, str) and not x.isdigit():
        for tid, code in sc.CLUB_BY_ID.items():
            if code == x:
                return tid
        return None
    return _int(x)


def games_left(games, team, as_of) -> int:
    """Regular-season games of `team` in the game list that are not final as
    of `as_of` and are neither postponed nor cancelled: a pk that became final
    after `as_of` counts, a pk with no final entry counts unless every entry is
    postponed or cancelled (a postponement never made up counts 0)."""
    tid = _team_id(team)
    by_pk: dict = {}
    for g in games or []:
        if tid not in (g.get("away"), g.get("home")):
            continue
        by_pk.setdefault(g.get("pk"), []).append(g)
    n = 0
    for entries in by_pk.values():
        fin = [g for g in entries if g.get("state") == "final"]
        if fin:
            if min(str(g.get("date")) for g in fin) > str(as_of):
                n += 1
            continue
        if any(g.get("state") not in ("postponed", "cancelled") for g in entries):
            n += 1
    return n


def last_results(games, team, as_of=None, n: int = 10) -> str:
    """The last `n` results of `team` through `as_of`, oldest first, as W and
    L letters (a tie, rare, is left out)."""
    tid = _team_id(team)
    seq = []
    for g in final_games(games):
        if as_of is not None and str(g["date"]) > str(as_of):
            break
        if tid == g["away"]:
            mine, theirs = g["away_r"], g["home_r"]
        elif tid == g["home"]:
            mine, theirs = g["home_r"], g["away_r"]
        else:
            continue
        if mine != theirs:
            seq.append("W" if mine > theirs else "L")
    return "".join(seq[-n:])


def streak_code(games, team, as_of=None) -> str | None:
    """MLB's streak code ("W4", "L2") of `team` from the final games through
    `as_of`: the run of the latest result (a tie, rare, is skipped); None
    before the club's first decision."""
    seq = last_results(games, team, as_of, n=10 ** 6)
    if not seq:
        return None
    n = len(seq) - len(seq.rstrip(seq[-1]))
    return f"{seq[-1]}{n}"


def last_and_next(games, team, as_of=None) -> dict:
    """{last, next} of `team`, each `{pk, d}` or None: the last final game
    through `as_of`, and the first game of the list with no final entry that is
    still to be played (scheduled, pregame, live or delayed), by date, game
    number, start time and pk. A postponed, cancelled or suspended entry is
    never the next game."""
    tid = _team_id(team)
    last = None
    for g in final_games(games):
        if as_of is not None and str(g["date"]) > str(as_of):
            break
        if tid in (g["away"], g["home"]):
            last = {"pk": g["pk"], "d": str(g["date"])}
    done = {g.get("pk") for g in games or [] if g.get("state") == "final"}
    todo = sorted((g for g in games or [] if tid in (g.get("away"), g.get("home")) and g.get("pk") not in done
                   and g.get("state") in ("scheduled", "pregame", "live", "delayed")),
                  key=lambda g: (str(g.get("date")), g.get("gn") or 1, str(g.get("start") or ""), g.get("pk") or 0))
    nxt = {"pk": todo[0]["pk"], "d": str(todo[0]["date"])} if todo else None
    return {"last": last, "next": nxt}


def race_extras(games, season, *, last_next: bool = True) -> dict:
    """The per-club sequences the race file carries beside `last10` (plan 4.1:
    streaks, last and next game), from the same game list: `streak {code:
    "W4" or None}` and, with `last_next`, `last_game` and `next_game {code:
    {pk, d} or None}` (the live seasons only, whose games have pages on
    /scores/)."""
    ids = sorted(sc.CLUB_BY_ID)
    out = {"streak": {sc.CLUB_BY_ID[t]: streak_code(games, t) for t in ids}}
    if last_next:
        ln = {sc.CLUB_BY_ID[t]: last_and_next(games, t) for t in ids}
        out["last_game"] = {c: v["last"] for c, v in ln.items()}
        out["next_game"] = {c: v["next"] for c, v in ln.items()}
    return out


def head_to_head(games, a, b, as_of=None) -> dict:
    """{a: [W, L], b: [W, L]} between two clubs (codes or ids) in the final
    games through `as_of`: each game of a doubleheader counts, a suspended game
    counts once, clubs that never met give 0-0, and the two mirror."""
    ta, tb = _team_id(a), _team_id(b)
    wa = wb = 0
    for g in final_games(games):
        if as_of is not None and str(g["date"]) > str(as_of):
            break
        if {g["away"], g["home"]} != {ta, tb} or g["away_r"] == g["home_r"]:
            continue
        win = g["away"] if g["away_r"] > g["home_r"] else g["home"]
        if win == ta:
            wa += 1
        else:
            wb += 1
    ka = sc.club_code(ta) or str(a)
    kb = sc.club_code(tb) or str(b)
    return {ka: [wa, wb], kb: [wb, wa]}


# --------------------------------------------------------------------------- #
# 8. The race
# --------------------------------------------------------------------------- #
def _snapshot_rows(snap, as_of) -> list[dict]:
    """Rows of a by-date snapshot given as a raw StatsAPI payload, a parsed
    result of parse_standings or a built file, or a list of rows."""
    if isinstance(snap, list):
        return snap
    if isinstance(snap, dict) and "records" in snap:
        return parse_standings(snap, as_of)["rows"]
    if isinstance(snap, dict) and "rows" in snap:
        return snap["rows"]
    return []


def build_race(games, season, snapshots=None, *, copyright=None, generated_at=None) -> dict:
    """The race of one season from its game list (plan 4.6 item 8):
    `{schema, season, generated_at, copyright, dates, clubs, wc_gap, last10,
    events}`. `clubs[code]` holds `[W, L, RS, RA]` after each date; `wc_gap`
    the signed games from the club holding the last wild card spot that date
    (+ ahead), null for a club qualifying outside the wild card that date
    (division leaders; in 2020 the top two of each division), the leaders read
    from that date's snapshot `divisionRank` where one exists and otherwise
    every club tied for a lead counted as one; `last10` the last ten results
    oldest first; `events` the first date each mark appears in the snapshots."""
    season = int(season)
    fmt = format_for(season)
    snaps = {str(d): _snapshot_rows(s, str(d)) for d, s in (snapshots or {}).items()}
    fins = final_games(games)
    dates = sorted({str(g["date"]) for g in fins})
    ids = sorted(sc.CLUB_BY_ID)
    tot = {tid: [0, 0, 0, 0] for tid in ids}
    by_date: dict = {}
    for g in fins:
        by_date.setdefault(str(g["date"]), []).append(g)
    clubs = {sc.CLUB_BY_ID[t]: [] for t in ids}
    gaps = {sc.CLUB_BY_ID[t]: [] for t in ids}
    div_of = {t: division_of(t, season) for t in ids}
    for d in dates:
        for g in by_date[d]:
            for me, opp, mr, orr in ((g["away"], g["home"], g["away_r"], g["home_r"]),
                                     (g["home"], g["away"], g["home_r"], g["away_r"])):
                if me not in tot:
                    continue
                t = tot[me]
                if mr > orr:
                    t[0] += 1
                elif mr < orr:
                    t[1] += 1
                t[2] += mr
                t[3] += orr
        for t in ids:
            clubs[sc.CLUB_BY_ID[t]].append(list(tot[t]))
        gap = _wc_gaps(tot, div_of, fmt, snaps.get(d))
        for t in ids:
            gaps[sc.CLUB_BY_ID[t]].append(gap.get(t))
    last10 = {sc.CLUB_BY_ID[t]: last_results(games, t) for t in ids}
    events = []
    seen: dict = {}
    for d in sorted(snaps):
        for r in snaps[d]:
            for mark in ([r.get("mark")] if r.get("mark") else []) + (["e"] if r.get("e") else []):
                if mark not in seen.setdefault(r["code"], set()):
                    seen[r["code"]].add(mark)
                    events.append({"d": d, "code": r["code"], "mark": mark})
    return {"schema": SCHEMA, "season": season, "generated_at": generated_at, "copyright": copyright,
            "dates": dates, "clubs": clubs, "wc_gap": gaps, "last10": last10, "events": events}


def _wc_gaps(tot: dict, div_of: dict, fmt: dict, snap_rows) -> dict:
    out: dict = {}
    snap = {r["team_id"]: r for r in snap_rows} if snap_rows else None
    for lg in (103, 104):
        members = [t for t in tot if DIVISION_LEAGUE.get(div_of.get(t)) == lg]
        leaders: set = set()
        for div in {div_of[t] for t in members}:
            dm = [t for t in members if div_of[t] == div]
            if snap is not None and all(t in snap for t in dm):
                keep = {1, 2} if fmt["division_spots"] == 2 else {1}
                leaders |= {t for t in dm if (snap[t].get("ranks") or {}).get("div") in keep}
            else:
                diffs = sorted({tot[t][0] - tot[t][1] for t in dm}, reverse=True)
                bar = diffs[min(fmt["division_spots"], len(diffs)) - 1]
                leaders |= {t for t in dm if tot[t][0] - tot[t][1] >= bar}
        rest = [t for t in members if t not in leaders]
        ref = None
        if snap is not None and all(t in snap for t in rest):
            ref = next((t for t in rest if (snap[t].get("ranks") or {}).get("wc") == fmt["wc_spots"]), None)
        if ref is None:
            def key(t):
                w, l = tot[t][0], tot[t][1]
                return (-(Fraction(w, w + l) if w + l else Fraction(1, 2)), -(w - l), t)
            rest_sorted = sorted(rest, key=key)
            if len(rest_sorted) >= fmt["wc_spots"]:
                ref = rest_sorted[fmt["wc_spots"] - 1]
        for t in members:
            if t in leaders or ref is None:
                out[t] = None
            else:
                out[t] = _half(_games_ahead((tot[t][0], tot[t][1]), (tot[ref][0], tot[ref][1])))
    return out


def race_value_at(race: dict, code: str, date: str):
    """The race tuple of a club at a date: the last race date on or before it
    (a date with no game holds the previous totals); [0, 0, 0, 0] before."""
    idx = None
    for i, d in enumerate(race.get("dates") or []):
        if d <= str(date):
            idx = i
        else:
            break
    if idx is None:
        return [0, 0, 0, 0]
    return race["clubs"][code][idx]


def race_matches_snapshots(race: dict, snapshots: dict) -> list[tuple]:
    """Every (date, club, field) where the race differs from a by-date
    snapshot in W, L, RS or RA, at every snapshot date (T13)."""
    out = []
    for key in sorted(snapshots or {}, key=str):
        d = str(key)
        rows = _snapshot_rows(snapshots[key], d)
        for r in rows:
            got = race_value_at(race, r["code"], d)
            for i, f in enumerate(("w", "l", "rs", "ra")):
                if got[i] != r.get(f):
                    out.append((d, r["code"], f))
    return out


# --------------------------------------------------------------------------- #
# 9. Builders and the one compact writer
# --------------------------------------------------------------------------- #
def _cut_ties(rows: list[dict], games, fmt: dict, as_of) -> list[dict]:
    """Ties at a cut line (the division lead, the bye line, the last wild card
    spot) with the head-to-head W-L where a game list exists."""
    def tied(a, b):
        return a["w"] * (b["w"] + b["l"]) == b["w"] * (a["w"] + a["l"])

    out = []
    by_lg: dict = {}
    for r in rows:
        by_lg.setdefault(r["lg"], []).append(r)

    def add(cut, lg, inside, pool, is_in):
        group = [x for x in pool if x is inside or tied(x, inside)]
        if len(group) < 2 or all(is_in(x) for x in group) or not any(is_in(x) for x in group):
            return
        group.sort(key=lambda x: (x["seed"] if x["seed"] is not None else 99, x["code"]))
        item = {"cut": cut, "lg": lg, "clubs": [r["code"] for r in group]}
        if games is not None:
            item["h2h"] = [[a["code"], b["code"], head_to_head(games, a["code"], b["code"], as_of)[a["code"]]]
                           for i, a in enumerate(group) for b in group[i + 1:]]
        out.append(item)

    for lg, lg_rows in sorted(by_lg.items(), key=lambda kv: str(kv[0])):
        seeded = sorted((r for r in lg_rows if r["seed"] is not None), key=lambda r: r["seed"])
        for r in seeded:
            if r["qualified"] == "division":
                add("division", lg, r, [x for x in lg_rows if x["div"] == r["div"]],
                    lambda x: x["qualified"] == "division")
        if fmt["byes"] and len(seeded) > fmt["byes"]:
            line = seeded[fmt["byes"] - 1]
            add("bye", lg, line, [x for x in seeded if x["qualified"] == "division"],
                lambda x: x["seed"] <= fmt["byes"])
        if seeded and seeded[-1]["qualified"] == "wild_card":
            add("wild_card", lg, seeded[-1], [x for x in lg_rows if x["qualified"] in ("wild_card", None)],
                lambda x: x["seed"] is not None)
    return out


def build_season_file(payload, *, as_of, final: bool, generated_at, fetched_at=None,
                      games=None, race=None, snapshot: bool = False) -> dict:
    """The season file `OUT/standings/<Y>.json` (or, with `snapshot=True`, the
    by-date file `OUT/standings/<Y>/<D>.json`, the row shape with no `ours`).
    `games` is the season's game list (the race schedule, extended in season
    by the job's date files), used for `left`, `l10_seq` and the head-to-head
    at a cut; `race` gives `opening_day` (its first date)."""
    p = parse_standings(payload, as_of, final=final)
    fmt = format_for(p["season"])
    rows = p["rows"]
    for r in rows:
        if games is not None:
            r["l10_seq"] = last_results(games, r["team_id"], as_of)
            if not final:
                r["left"] = games_left(games, r["team_id"], as_of)
        if final:
            r["left"] = 0
    x_exp = rows[0]["x_exp"] if rows else None
    obj = {
        "schema": SCHEMA, "season": p["season"], "as_of": p["as_of"], "fetched_at": fetched_at,
        "generated_at": generated_at, "final": bool(final),
        "opening_day": (race or {}).get("dates", [None])[0] if race else None,
        "copyright": p["copyright"],
        "format": fmt,
        "tiebreak": {"text": tiebreak_text(p["season"]), "cut_ties": _cut_ties(rows, games, fmt, as_of)},
        "k90": round(math.pow(72 / 90, 1 / x_exp), 3) if x_exp else None,
        "rows": rows,
    }
    if not snapshot:
        obj["ours"] = None
        obj["registry"] = []
    obj["accountability"] = {"feed_disagreements": p["feed_disagreements"]}
    return obj


def build_snapshot_file(payload, *, as_of, final: bool, generated_at, fetched_at=None, games=None,
                        race=None) -> dict:
    return build_season_file(payload, as_of=as_of, final=final, generated_at=generated_at,
                             fetched_at=fetched_at, games=games, race=race, snapshot=True)


def build_race_file(games, season, snapshots=None, *, copyright=None, generated_at=None) -> dict:
    return build_race(games, season, snapshots, copyright=copyright, generated_at=generated_at)


def build_phist_file(season, *, generated_at, copyright=None, regular=None, post=None,
                     switch_as_of=None, closed: bool = False) -> dict:
    """`OUT/standings/<Y>-phist.json`, packed by column (plan 4.2 and 4.7):
    `regular` and `post` always present (empty, `switch_as_of` null and
    `closed` false by default); `phist_blocks` fills them."""
    reg = {"source": None, "missing": [], "fields": list(PHIST_REGULAR_FIELDS), "as_of": [], "clubs": {}}
    reg.update(regular or {})
    pst = {"fields": list(PHIST_POST_FIELDS), "as_of": [], "sha256": [], "clubs": {}}
    pst.update(post or {})
    return {"schema": SCHEMA, "season": int(season), "generated_at": generated_at, "copyright": copyright,
            "switch_as_of": switch_as_of, "closed": bool(closed), "regular": reg, "post": pst}


# --------------------------------------------------------------------------- #
# 4.7 Our columns: copied, never recomputed (STANDINGS_3_OURS_JOIN)
# --------------------------------------------------------------------------- #
MODEL_REGULAR = "playoff_odds_sim"
MODEL_POST = "postseason_bracket_sim"
#: The caption label of each odds model; no registry field holds one, so the
#: page builds its caption from this label and the copied verdict.
MODEL_LABEL = {MODEL_REGULAR: "Eephus season simulator", MODEL_POST: "Eephus bracket simulator"}
#: frame_from where the job's state has none (plan 4.7 "The frame bound"):
#: FIRST_SEASON has read 2027 since 427a6484 (2026-06-10), before the futures
#: ledger's first entry (2026-09-06), so every season-2026 entry on disk came
#: from the 2026 frame. No later season is seeded.
FRAME_FROM_SEED = {2026: "2026-09-06"}
PHIST_REGULAR_SOURCE = "futures ledger on this machine"
#: futures.json clubs[] keys and their `ours` names (plan 4.7). The club's
#: `record` and `impliedAmerican*` are never copied (the American numbers are
#: prices); `record` is read by proj_basis for the comparison only.
FUTURES_KEYS = (("divisionPct", "p_div"), ("playoffPct", "p_post"), ("byePct", "p_bye"),
                ("pennantPct", "p_pennant"), ("wsPct", "p_ws"), ("projWins", "proj_w"),
                ("winTotalP10", "proj_p10"), ("winTotalP90", "proj_p90"))
#: futures_ledger.json entries[].clubs[] keys, in PHIST_REGULAR_FIELDS order.
LEDGER_KEYS = FUTURES_KEYS[:5]
#: bracket_sim.json clubs[] (and the record's outputs.clubs) keys, in
#: PHIST_POST_FIELDS order.
BRACKET_KEYS = (("pennant_pct", "p_pennant"), ("ws_pct", "p_ws"))
#: mlb_projections.json team_outlook[].current keys, inside the SOS window only.
SOS_KEYS = (("sos", "sos"), ("sosRank", "sos_rank"))
#: Every key of one club's `ours` entry, in written order.
OURS_CLUB_KEYS = tuple(k for _s, k in FUTURES_KEYS) + (
    "proj_w_int", "proj_l", "proj_basis_ok", "proj_basis_w", "proj_basis_l", "sos", "sos_rank")
#: Postseason game types (Wild Card Series, Division Series, LCS, World Series).
POST_GAME_TYPES = ("F", "D", "L", "W")
_WL_RE = re.compile(r"^(\d+)-(\d+)$")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def parse_wl(text) -> tuple:
    """(w, l) from a "W-L" string such as futures.json's club `record`, else
    (None, None)."""
    m = _WL_RE.match(text) if isinstance(text, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def proj_w_int(proj_w):
    """`proj_w` rounded half up, math.floor(proj_w + 0.5): never Python's
    round, which gives 92 for 92.5. None when `proj_w` is not a number."""
    return math.floor(proj_w + 0.5) if _num(proj_w) else None


def proj_basis(futures_club, row) -> dict:
    """The projection's basis (plan 4.7): futures.json's club `record`, read
    for this comparison only and never copied, parsed into two integers and
    compared with the row's `w` and `l`. No time order is claimed either way."""
    bw, bl = parse_wl((futures_club or {}).get("record"))
    ok = bw is not None and bw == row.get("w") and bl == row.get("l")
    return {"proj_basis_ok": ok, "proj_basis_w": bw, "proj_basis_l": bl}


def sos_window_open(as_of, opening_day, regular_season_end) -> bool:
    """The SOS window of plan 4.7: the season file's `as_of` from
    `opening_day` to futures.json's `regular_season_end`, both inclusive."""
    if not (as_of and opening_day and regular_season_end):
        return False
    return str(opening_day) <= str(as_of) <= str(regular_season_end)


def registry_block(models, ids) -> list[dict]:
    """[{model_id, verdict, last_checked, label}] for `ids`, copied from the
    served registry's rows (`last_checked` may be null) plus MODEL_LABEL."""
    by = {m.get("model_id"): m for m in (models or []) if isinstance(m, dict)}
    out = []
    for mid in ids:
        m = by.get(mid)
        if m is None or not m.get("verdict"):
            continue
        out.append({"model_id": mid, "verdict": m.get("verdict"), "last_checked": m.get("last_checked"),
                    "label": MODEL_LABEL[mid]})
    return out


def bracket_serves(bracket, season) -> bool:
    """bracket_sim.json is this season's and says it serves."""
    return (isinstance(bracket, dict) and bracket.get("season") == season
            and (bracket.get("serve") or {}).get("on") is True and isinstance(bracket.get("clubs"), list))


def build_ours(obj: dict, *, futures, bracket=None, october: bool = False, sos=None, registry=None) -> tuple:
    """(`ours`, `registry`) for the season file `obj` (plan 4.7), every value
    copied from its source and never recomputed, except the two derived
    integers `proj_w_int` and `proj_l` (4.6 item 11). `futures` is
    futures.json (or the job's extract of it), `bracket` bracket_sim.json,
    `sos` mlb_projections.json, `registry` the served registry's `models`.

    (None, []) under the season guard (futures.json's top-level `season` is
    not the file's) or when the served registry has no `playoff_odds_sim` row
    (an odds cell is never served without its verdict). With `october` true
    (from the season's first postseason game to its last) `p_pennant` and
    `p_ws` come from bracket_sim.json when it serves this season, and are
    null otherwise; the other three chances, PROJ and its band stay
    futures.json's. SOS is copied only inside the SOS window and for a club
    with `left` above 0, never in October."""
    y = obj.get("season")
    if not isinstance(futures, dict) or futures.get("season") != y or not isinstance(futures.get("clubs"), list):
        return None, []
    reg_all = registry_block(registry, (MODEL_REGULAR, MODEL_POST))
    if not any(r["model_id"] == MODEL_REGULAR for r in reg_all):
        return None, []
    post_ok = bool(october) and bracket_serves(bracket, y) and any(r["model_id"] == MODEL_POST for r in reg_all)
    fut_by = {c.get("team"): c for c in futures["clubs"] if isinstance(c, dict)}
    br_by = {c.get("team"): c for c in bracket["clubs"] if isinstance(c, dict)} if post_ok else {}
    sos_rows = (sos or {}).get("team_outlook") if isinstance(sos, dict) else None
    sos_by = {r.get("team"): (r.get("current") or {}) for r in (sos_rows or []) if isinstance(r, dict)}
    sos_open = (not october) and sos_window_open(obj.get("as_of"), obj.get("opening_day"),
                                                 futures.get("regular_season_end"))
    clubs = {}
    for row in obj.get("rows") or []:
        code = row.get("code")
        fc = fut_by.get(code)
        c = {k: (fc.get(s) if fc else None) for s, k in FUTURES_KEYS}
        if october:
            bc = br_by.get(code)
            for s, k in BRACKET_KEYS:
                c[k] = bc.get(s) if bc else None
        c.update(proj_basis(fc, row))
        left = row.get("left")
        wi = proj_w_int(c["proj_w"]) if c["proj_basis_ok"] and isinstance(left, int) else None
        c["proj_w_int"] = wi
        c["proj_l"] = row["w"] + row["l"] + left - wi if wi is not None else None
        cur = sos_by.get(code) if sos_open and isinstance(left, int) and left > 0 else None
        for s, k in SOS_KEYS:
            c[k] = cur.get(s) if cur else None
        clubs[code] = {k: c[k] for k in OURS_CLUB_KEYS}
    pw_model = MODEL_POST if post_ok else (None if october else MODEL_REGULAR)
    ours = {
        "proj_made_at": futures.get("generated_at"),
        "phase": "postseason" if october else "regular",
        "regular": {"model_id": MODEL_REGULAR, "generated_at": futures.get("generated_at"),
                    "regular_season_end": futures.get("regular_season_end")},
        "postseason": ({"model_id": MODEL_POST, "as_of": bracket.get("as_of"),
                        "generated_at": bracket.get("generated_at"), "label": bracket.get("label"),
                        "method_version": bracket.get("method_version")} if post_ok else None),
        "models": {"p_div": MODEL_REGULAR, "p_post": MODEL_REGULAR, "p_bye": MODEL_REGULAR,
                   "p_pennant": pw_model, "p_ws": pw_model, "proj": MODEL_REGULAR, "sos": MODEL_REGULAR},
        "sos_window": {"open": sos_open, "from": obj.get("opening_day"), "to": futures.get("regular_season_end"),
                       "generated_at": (sos or {}).get("generated_at") if isinstance(sos, dict) else None},
        "clubs": clubs,
    }
    used = (MODEL_REGULAR, MODEL_POST) if post_ok else (MODEL_REGULAR,)
    return ours, [r for r in reg_all if r["model_id"] in used]


def ours_copy_mismatches(obj: dict, *, futures, bracket=None, sos=None) -> list[tuple[str, str]]:
    """T11 on the `ours` block: every copied value byte-equal (as written by
    `encode`) to its source key at the stamped `generated_at`."""
    ours = obj.get("ours")
    if not isinstance(ours, dict):
        return []
    out = []
    if ours.get("proj_made_at") != (futures or {}).get("generated_at"):
        out.append(("T11", "proj_made_at is not futures.json's generated_at"))
    fut_by = {c.get("team"): c for c in (futures or {}).get("clubs") or [] if isinstance(c, dict)}
    post = ours.get("postseason")
    br_by = {c.get("team"): c for c in (bracket or {}).get("clubs") or [] if isinstance(c, dict)} if post else {}
    if post and post.get("as_of") != (bracket or {}).get("as_of"):
        out.append(("T11", "the postseason block's as_of is not bracket_sim.json's"))
    sos_by = {r.get("team"): (r.get("current") or {}) for r in ((sos or {}).get("team_outlook") or [])
              if isinstance(r, dict)}
    october = ours.get("phase") == "postseason"
    for code, c in (ours.get("clubs") or {}).items():
        fc = fut_by.get(code) or {}
        for s, k in FUTURES_KEYS:
            if october and k in ("p_pennant", "p_ws"):
                src = (br_by.get(code) or {}).get(dict((b, a) for a, b in BRACKET_KEYS)[k])
            else:
                src = fc.get(s)
            if encode(c.get(k)) != encode(src):
                out.append(("T11", f"{code}: {k} {c.get(k)!r} is not its source's {src!r}"))
        for s, k in SOS_KEYS:
            if c.get(k) is not None and encode(c.get(k)) != encode(sos_by.get(code, {}).get(s)):
                out.append(("T11", f"{code}: {k} {c.get(k)!r} is not mlb_projections.json's"))
    return out


def seed_mismatches(obj: dict, bracket) -> list[tuple[str, str]]:
    """T19 against bracket_sim.json for the season file's own season: its
    clubs[].seed, joined by team, equals the served `seed`, and the seeded
    clubs are exactly the bracket's. Empty when the bracket is another
    season's or absent."""
    if not isinstance(bracket, dict) or bracket.get("season") != obj.get("season"):
        return []
    want = {c.get("team"): c.get("seed") for c in bracket.get("clubs") or [] if isinstance(c, dict)}
    if not want:
        return []
    got = {r["code"]: r.get("seed") for r in obj.get("rows") or [] if r.get("seed") is not None}
    out = []
    for code in sorted(set(want) | set(got)):
        if want.get(code) != got.get(code):
            out.append(("T19", f"{code}: served seed {got.get(code)!r} differs from bracket_sim.json's "
                               f"{want.get(code)!r}"))
    return out


def postseason_span(dated_cards) -> dict:
    """{first, last} from the job's own date files: `first` the first date
    holding a postseason card (gameType F, D, L or W), `last` the date of the
    World Series game that gives a club its fourth win (state final), None
    while that game is unplayed. `dated_cards` is [(officialDate, card)]."""
    first, last = None, None
    wins: dict = {}
    for d, c in sorted(dated_cards or [], key=lambda t: (str(t[0]), str((t[1] or {}).get("start") or ""))):
        if not isinstance(c, dict) or c.get("type") not in POST_GAME_TYPES:
            continue
        first = first or str(d)
        if c.get("type") != "W" or c.get("state") != "final" or last is not None:
            continue
        a, h = c.get("away") or {}, c.get("home") or {}
        if not (_num(a.get("r")) and _num(h.get("r"))) or a.get("r") == h.get("r"):
            continue
        win = (h if h["r"] > a["r"] else a).get("code") or (h if h["r"] > a["r"] else a).get("team_id")
        wins[win] = wins.get(win, 0) + 1
        if wins[win] == 4:
            last = str(d)
    return {"first": first, "last": last}


def _dates_between(a: str, b: str) -> list[str]:
    d0, d1 = _dt.date.fromisoformat(a), _dt.date.fromisoformat(b)
    return [(d0 + _dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _one_per_date(entries) -> list[tuple[str, dict]]:
    by = {}
    for e in entries:
        by[str(e["as_of"])] = e
    return sorted(by.items())


def phist_blocks(ledger, record, season, opening_day, last_post_date, frame_from) -> dict:
    """The two odds blocks of `<Y>-phist.json` (plan 4.7 "The two odds blocks"
    and "The frame bound"), packed by column, every value copied as its
    source holds it.

    `post`: the record's good entries (top-level `entries[]`; each entry's
    `as_of`, its `sha256` and `outputs.clubs`, a dict by club code) whose
    `season` is Y and whose `as_of` is on or before `last_post_date` (every
    one while it is None). `switch_as_of` = post.as_of[0], None while post is
    empty. `regular`: the ledger's entries (top-level `entries[]`; `as_of` and
    `clubs`, a list keyed by `team`) whose `season` is Y, dated on or after
    the later of `opening_day` and `frame_from` (none while either is unset)
    and before `switch_as_of`. `frame_from` is a date or the job's
    {"<Y>": date} map. `regular.missing` lists the calendar dates between the
    first and the last regular entry with no ledger entry, plus every
    season-Y ledger entry on or after `opening_day` (and before the switch)
    that the frame bound skips."""
    y = int(season)
    ff = frame_from.get(str(y)) if isinstance(frame_from, dict) else frame_from
    post_src = [e for e in (record or []) if isinstance(e, dict) and e.get("season") == y and e.get("as_of")
                and e.get("kind", "good") == "good"
                and isinstance((e.get("outputs") or {}).get("clubs"), dict)
                and (last_post_date is None or str(e["as_of"]) <= str(last_post_date))]
    post_e = _one_per_date(post_src)
    switch = post_e[0][0] if post_e else None
    bound = max(str(opening_day), str(ff)) if (opening_day and ff) else None
    reg_e, skipped = [], []
    for d, e in _one_per_date(e for e in (ledger or []) if isinstance(e, dict) and e.get("season") == y
                               and e.get("as_of") and isinstance(e.get("clubs"), list)):
        if not opening_day or d < str(opening_day) or (switch is not None and d >= switch):
            continue
        if bound is None or d < bound:
            skipped.append(d)
            continue
        reg_e.append((d, e))
    reg_as = [d for d, _e in reg_e]
    have = set(reg_as)
    gaps = [d for d in _dates_between(reg_as[0], reg_as[-1]) if d not in have] if reg_as else []
    rclubs: dict = {}
    for i, (_d, e) in enumerate(reg_e):
        for item in e["clubs"]:
            if isinstance(item, dict) and item.get("team"):
                rclubs.setdefault(item["team"], [None] * len(reg_e))[i] = [item.get(s) for s, _k in LEDGER_KEYS]
    pclubs: dict = {}
    for i, (_d, e) in enumerate(post_e):
        for code, v in e["outputs"]["clubs"].items():
            if isinstance(v, dict):
                pclubs.setdefault(code, [None] * len(post_e))[i] = [v.get(s) for s, _k in BRACKET_KEYS]
    regular = {"source": PHIST_REGULAR_SOURCE, "missing": sorted(set(gaps) | set(skipped)),
               "fields": list(PHIST_REGULAR_FIELDS), "as_of": reg_as,
               "clubs": {k: rclubs[k] for k in sorted(rclubs)}}
    post = {"fields": list(PHIST_POST_FIELDS), "as_of": [d for d, _e in post_e],
            "sha256": [e.get("sha256") for _d, e in post_e], "clubs": {k: pclubs[k] for k in sorted(pclubs)}}
    return {"regular": regular, "post": post, "switch_as_of": switch}


def phist_copy_mismatches(ph: dict, ledger, record) -> list[tuple[str, str]]:
    """T11 on a phist file: every packed value byte-equal (as written by
    `encode`) to its ledger or record entry, a club missing from an entry
    stored as null, and every post sha256 the entry's own."""
    out = []
    led = {}
    for e in ledger or []:
        if isinstance(e, dict) and e.get("season") == ph.get("season"):
            led[str(e.get("as_of"))] = {c.get("team"): c for c in e.get("clubs") or [] if isinstance(c, dict)}
    reg = ph.get("regular") or {}
    for i, d in enumerate(reg.get("as_of") or []):
        src = led.get(d)
        if src is None:
            out.append(("T11", f"regular {d}: no ledger entry of this season"))
            continue
        for code, col in (reg.get("clubs") or {}).items():
            want = [src[code].get(s) for s, _k in LEDGER_KEYS] if code in src else None
            if encode(col[i]) != encode(want):
                out.append(("T11", f"regular {d} {code}: {col[i]!r} is not the ledger's {want!r}"))
        if set(src) - set(reg.get("clubs") or {}):
            out.append(("T11", f"regular {d}: a ledger club is not packed"))
    rec = {}
    for e in record or []:
        if isinstance(e, dict) and e.get("season") == ph.get("season") and e.get("kind", "good") == "good":
            rec[str(e.get("as_of"))] = e
    pst = ph.get("post") or {}
    for i, d in enumerate(pst.get("as_of") or []):
        e = rec.get(d)
        if e is None:
            out.append(("T11", f"post {d}: no record entry of this season"))
            continue
        if (pst.get("sha256") or [None] * (i + 1))[i] != e.get("sha256"):
            out.append(("T11", f"post {d}: sha256 is not the entry's"))
        src = (e.get("outputs") or {}).get("clubs") or {}
        for code, col in (pst.get("clubs") or {}).items():
            want = [src[code].get(s) for s, _k in BRACKET_KEYS] if code in src else None
            if encode(col[i]) != encode(want):
                out.append(("T11", f"post {d} {code}: {col[i]!r} is not the record's {want!r}"))
    return out


def encode(obj) -> bytes:
    """The one serialiser of every standings file: compact separators, no
    indent, UTF-8 characters kept, NaN refused, key order as built."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def write_file(path, obj) -> int:
    """Write `obj` to `path` through a temp file and os.replace (0644);
    returns the byte count."""
    data = encode(obj)
    path = os.fspath(path)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            os.chmod(tmp, 0o644)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(data)


# --------------------------------------------------------------------------- #
# 9. The validator: scores_core's file-independent rules plus T1 to T20
# --------------------------------------------------------------------------- #
def _band(value, formula) -> bool:
    return isinstance(value, int) and value in (formula, formula - 1)


def t7_misses(rows, fmt) -> list[tuple]:
    """(code, label, value, band top) for every magic or elimination number
    outside G + 1 - W_ref - L or one less (T7): the leader's magic against the
    runner-up's losses, a division elimination number against the leader's
    wins, a wild card elimination number against the wins of the club holding
    the last spot."""
    G = fmt["scheduled"]
    by_div: dict = {}
    by_lg: dict = {}
    for r in rows:
        by_div.setdefault(r.get("div"), []).append(r)
        by_lg.setdefault(r.get("lg"), []).append(r)
    out = []
    for div_rows in by_div.values():
        lead = next((r for r in div_rows if r["ranks"]["div"] == 1), None)
        runner = next((r for r in div_rows if r["ranks"]["div"] == 2), None)
        for r in div_rows:
            if isinstance(r.get("magic"), int) and runner is not None:
                want = G + 1 - r["w"] - runner["l"]
                if not _band(r["magic"], want):
                    out.append((r["code"], "magic", r["magic"], want))
            if isinstance(r.get("elim_div"), int) and lead is not None and r is not lead:
                want = G + 1 - lead["w"] - r["l"]
                if not _band(r["elim_div"], want):
                    out.append((r["code"], "division elimination", r["elim_div"], want))
    for lg_rows in by_lg.values():
        ref = next((r for r in lg_rows if r["ranks"]["wc"] == fmt["wc_spots"]), None)
        for r in lg_rows:
            if isinstance(r.get("elim_wc"), int) and ref is not None and r is not ref and r["ranks"]["wc"] is not None:
                want = G + 1 - ref["w"] - r["l"]
                if not _band(r["elim_wc"], want):
                    out.append((r["code"], "wild card elimination", r["elim_wc"], want))
    return out


def check_rows(obj: dict, *, games=None, race=None, source=None, logged: list | None = None) -> list[tuple[str, str]]:
    """The laws of plan 6 over a season or snapshot file (T1 to T9, T11, T13,
    T15, T17, T19, T20; T12 on an `ours` block when one is present). A T7 band
    miss is appended to `logged`, never refused: once the season is over
    MLB's numbers are leftovers (2020's Reds read a division elimination
    number of 2 after the last game), and early in a season MLB's own magic
    and elimination numbers sit far below the band (STANDINGS_2's 2026
    by-date backfill: NYY magic 129 on 2026-04-04 where G + 1 - W - L gives
    152), so the served value stays MLB's and the parser lists every miss in
    `accountability.feed_disagreements`."""
    out: list = []
    t7 = logged if logged is not None else []
    rows = obj.get("rows") or []
    season = obj.get("season")
    try:
        fmt = format_for(season)
    except (KeyError, TypeError, ValueError):
        return [("1", f"season {season!r} has no format")]
    final = bool(obj.get("final"))
    if obj.get("format") != fmt:
        out.append(("T6", "format block differs from FORMAT[season]"))
    if (obj.get("tiebreak") or {}).get("text") != tiebreak_text(season):
        out.append(("T17", "tiebreak text is not the season's literal"))
    if len(rows) != 30 or len({r.get("code") for r in rows}) != 30:
        out.append(("1", f"{len(rows)} rows, 30 distinct clubs expected"))
    for r in rows:
        if not isinstance(r.get("team_id"), int) or sc.club_code(r.get("team_id")) != r.get("code"):
            out.append(("1", f"row {r.get('code')!r} team_id {r.get('team_id')!r} is not the literal's"))
    by_div: dict = {}
    by_lg: dict = {}
    for r in rows:
        by_div.setdefault(r.get("div"), []).append(r)
        by_lg.setdefault(r.get("lg"), []).append(r)
    # T1, T3, T4
    for r in rows:
        c = r.get("code")
        if r["w"] + r["l"] + r["t"] != r["gp"]:
            out.append(("T1", f"{c}: W + L + T {r['w'] + r['l'] + r['t']} != GP {r['gp']}"))
        if r["w"] + r["l"] and r.get("pct") is not None and abs(r["pct"] - r["w"] / (r["w"] + r["l"])) > 0.0006:
            out.append(("T3", f"{c}: PCT {r['pct']} != W / (W + L)"))
        if r.get("rd") != r["rs"] - r["ra"]:
            out.append(("T4", f"{c}: RD {r.get('rd')} != RS - RA"))
    # T2
    sw, sl = sum(r["w"] for r in rows), sum(r["l"] for r in rows)
    if sw != sl:
        out.append(("T2", f"league W {sw} != L {sl}"))
    if final and rows:
        lo, hi = (898, 898) if season == 2020 else (2425, 2431)
        if not lo <= sw <= hi:
            out.append(("T2", f"a final season's {sw} decided games outside {lo} to {hi}"))
    # T5
    for div_rows in by_div.values():
        best = max(r["w"] - r["l"] for r in div_rows)
        for r in div_rows:
            if r.get("gb") != (best - (r["w"] - r["l"])) / 2:
                out.append(("T5", f"{r['code']}: GB {r.get('gb')} is not from the division's best W - L"))
    # T6 and T15 (wcgb sign)
    for lg_rows in by_lg.values():
        ref = next((r for r in lg_rows if r["ranks"]["wc"] == fmt["wc_spots"]), None)
        for r in lg_rows:
            if r["ranks"]["wc"] is None:
                if r.get("wcgb") is not None:
                    out.append(("T6", f"{r['code']}: a club outside the wild-card ranks carries WCGB"))
                continue
            if ref is not None:
                want = ((r["w"] - r["l"]) - (ref["w"] - ref["l"])) / 2
                got = r.get("wcgb") if not r.get("wc_ahead") else None
                signed = (r["wcgb"] if r.get("wc_ahead") else -r["wcgb"]) if r.get("wcgb") is not None else None
                if signed is None or signed != want or (got is not None and got < 0):
                    out.append(("T6", f"{r['code']}: WCGB {r.get('wcgb')} ahead {r.get('wc_ahead')} != {want}"))
    # T7: magic and elimination bands (logged, never refused: see t7_misses)
    for code, label, value, _want in t7_misses(rows, fmt):
        t7.append(("T7", f"{code}: {label} {value} outside its band"))
    # T8: marks
    for r in rows:
        if r.get("mark") and r.get("e"):
            out.append(("T8", f"{r['code']}: both marked and e"))
        want_e = r.get("mark") is None and (r.get("elim_wc") == "E" or final)
        if bool(r.get("e")) != want_e:
            out.append(("T8", f"{r['code']}: e {r.get('e')} is not the marks rule"))
    # a division clinched (y or z) leaves every UNMARKED rival at division E;
    # a rival holding its own mark (w or x) carries MLB's "-" or a leftover
    # number instead (15 club-seasons 2000 to 2025, 2000 SEA to 2025 NYY)
    for div_rows in by_div.values():
        for r in div_rows:
            if r.get("mark") in ("y", "z"):
                for o in div_rows:
                    if o is not r and not o.get("mark") and o.get("elim_div") != "E":
                        out.append(("T8", f"{r['code']} clinched the division but {o['code']} is not at E"))
    if final and rows and sum(1 for r in rows if r.get("mark") or r.get("e")) != 30:
        out.append(("T8", "a final file does not partition 30 = marked + e"))
    # T9
    t9 = t9_holds(rows)
    for r in rows:
        if r.get("x_exp") != (X_EXPONENT if t9 else None):
            out.append(("T9", f"{r['code']}: x_exp {r.get('x_exp')} while T9 {'holds' if t9 else 'fails'}"))
            break
    x_exp = rows[0].get("x_exp") if rows else None
    want_k = round(math.pow(72 / 90, 1 / x_exp), 3) if x_exp else None
    if obj.get("k90") != want_k:
        out.append(("T15", f"k90 {obj.get('k90')} != {want_k}"))
    # T15: served derivations
    for r in rows:
        c = r["code"]
        for key, num in (("rdg", r.get("rd")), ("rs_g", r["rs"]), ("ra_g", r["ra"])):
            want = round2(num, r["gp"]) if num is not None else None
            if r.get(key) != want:
                out.append(("T15", f"{c}: {key} {r.get(key)} != {want}"))
        if r.get("x_wl") is not None and r.get("w_xw") != r["w"] - r["x_wl"][0]:
            out.append(("T15", f"{c}: w_xw {r.get('w_xw')} != W - xW"))
        if final and r.get("left") != 0:
            out.append(("T15", f"{c}: left {r.get('left')} in a final file"))
        if games is not None and not final and r.get("left") != games_left(games, r["team_id"], obj.get("as_of")):
            out.append(("T15", f"{c}: left {r.get('left')} is not the game list's"))
        seq = r.get("l10_seq")
        if seq is not None:
            if len(seq) > 10 or set(seq) - {"W", "L"}:
                out.append(("T15", f"{c}: l10_seq {seq!r} malformed"))
            elif r.get("l10") is not None and seq.count("W") != r["l10"][0] and len(seq) == sum(r["l10"]):
                out.append(("T15", f"{c}: l10_seq wins {seq.count('W')} != L10 wins {r['l10'][0]}"))
    # T13 and T15 against the race
    if race is not None:
        dates = race.get("dates") or []
        if obj.get("opening_day") != (dates[0] if dates else None):
            out.append(("T15", f"opening_day {obj.get('opening_day')} != the race's first date"))
        if dates and dates[-1] <= str(obj.get("as_of")):
            for r in rows:
                got = race["clubs"][r["code"]][-1]
                if got != [r["w"], r["l"], r["rs"], r["ra"]]:
                    out.append(("T13", f"{r['code']}: race {got} != the file's W L RS RA"))
                if dates[-1] == str(obj.get("as_of")):
                    gap = race["wc_gap"][r["code"]][-1]
                    want = None if r.get("wcgb") is None else (r["wcgb"] if r.get("wc_ahead") else -r["wcgb"])
                    if gap != want:
                        out.append(("T15", f"{r['code']}: wc_gap {gap} != signed WCGB {want}"))
    # T19: seeds
    texts = QUALIFIED_TEXT["final" if final else "in_season"]
    for lg, lg_rows in by_lg.items():
        seeds = sorted(r["seed"] for r in lg_rows if r.get("seed") is not None)
        if seeds != list(range(1, fmt["per_league"] + 1)):
            out.append(("T19", f"{lg}: seeds {seeds} are not 1 to {fmt['per_league']}"))
        for r in lg_rows:
            if (r.get("seed") is None) != (r.get("qualified") is None) or \
                    (r.get("qualified") is not None and r.get("qualified_text") != texts.get(r["qualified"])) or \
                    (r.get("qualified") is None and r.get("qualified_text") is not None):
                out.append(("T19", f"{r['code']}: seed, qualified and qualified_text disagree"))
        top = sorted((r for r in lg_rows if r.get("qualified") == "division"), key=lambda r: r["seed"])
        if [r["seed"] for r in top] != [1, 2, 3] or any(r["ranks"]["div"] != 1 for r in top):
            out.append(("T19", f"{lg}: seeds 1 to 3 are not the divisionRank-1 clubs"))
    if final and rows:
        if {r["code"] for r in rows if r.get("seed")} != {r["code"] for r in rows if r.get("mark")}:
            out.append(("T19", "a final file's seeded set differs from its marked set"))
    # T20: league records
    for r in rows:
        if r.get("vs_lg") is None or r.get("intr") is None:
            continue
        if r["vs_lg"][0] + r["intr"][0] != r["w"] or r["vs_lg"][1] + r["intr"][1] != r["l"]:
            out.append(("T20", f"{r['code']}: LG plus INTR != W-L"))
    # T11: W to RA equal the saved response
    if source is not None:
        raw = {}
        for _rec, tr, _i in _team_records(source):
            raw[sc.club_code((tr.get("team") or {}).get("id"))] = tr
        for r in rows:
            tr = raw.get(r["code"]) or {}
            for f, k in (("w", "wins"), ("l", "losses"), ("rs", "runsScored"), ("ra", "runsAllowed")):
                if r.get(f) != _int(tr.get(k)):
                    out.append(("T11", f"{r['code']}: {f} {r.get(f)} != the saved response's {tr.get(k)}"))
        if obj.get("copyright") != (source or {}).get("copyright"):
            out.append(("T11", "copyright is not the saved response's line"))
    # T12: the copied odds block, when one exists
    ours = obj.get("ours")
    if isinstance(ours, dict):
        for code, o in (ours.get("clubs") or {}).items():
            ps = {k: o.get(k) for k in PHIST_REGULAR_FIELDS}
            if any(v is not None and not 0 <= v <= 1 for v in ps.values()):
                out.append(("T12", f"{code}: a probability outside [0, 1]"))
            def ge(a, b):
                return ps[a] is None or ps[b] is None or ps[a] + 1e-9 >= ps[b]
            if not (ge("p_post", "p_div") and ge("p_post", "p_bye") and ge("p_post", "p_pennant")
                    and ge("p_pennant", "p_ws")):
                out.append(("T12", f"{code}: the probability order fails"))
        out += check_ours(obj)
    elif ours is not None:
        out.append(("1", "ours is neither an object nor null"))
    return out


def check_ours(obj: dict) -> list[tuple[str, str]]:
    """T10 and T18 on a season file's `ours` block, plus its registry block.
    T10 applies only where the projection's basis agrees with the row: there
    `proj_w_int` = floor(`proj_w` + 0.5), `proj_w_int` + `proj_l` = W + L +
    LEFT and W <= `proj_w_int` <= W + LEFT (a failure refuses the file);
    elsewhere both integers are null and a mismatch never refuses. T18: SOS
    is null outside the window and for a club with LEFT 0."""
    out: list = []
    ours = obj.get("ours") or {}
    rows = {r.get("code"): r for r in obj.get("rows") or []}
    clubs = ours.get("clubs") or {}
    if set(clubs) != set(rows):
        out.append(("T11", "ours clubs are not the file's 30 rows"))
    sos_open = bool((ours.get("sos_window") or {}).get("open"))
    for code, c in clubs.items():
        r = rows.get(code)
        if r is None:
            continue
        if list(c) != list(OURS_CLUB_KEYS):
            out.append(("1", f"{code}: ours keys {sorted(c)} are not the plan's"))
            continue
        bw, bl = c["proj_basis_w"], c["proj_basis_l"]
        if (bw is None) != (bl is None) or c["proj_basis_ok"] is not (bw is not None and bw == r["w"] and bl == r["l"]):
            out.append(("T10", f"{code}: proj_basis_ok {c['proj_basis_ok']} is not the basis {bw}-{bl} "
                               f"against {r['w']}-{r['l']}"))
        left, wi, pl = r.get("left"), c["proj_w_int"], c["proj_l"]
        if c["proj_basis_ok"] and _num(c["proj_w"]) and isinstance(left, int):
            if wi != math.floor(c["proj_w"] + 0.5):
                out.append(("T10", f"{code}: proj_w_int {wi} is not proj_w {c['proj_w']} rounded half up"))
            elif pl is None or wi + pl != r["w"] + r["l"] + left:
                out.append(("T10", f"{code}: PROJ {wi}-{pl} does not sum to W + L + LEFT"))
            elif not r["w"] <= wi <= r["w"] + left:
                out.append(("T10", f"{code}: proj_w_int {wi} outside W {r['w']} to W + LEFT {r['w'] + left}"))
        elif wi is not None or pl is not None:
            out.append(("T10", f"{code}: PROJ served where the basis disagrees or is unread"))
        if (c["sos"] is not None or c["sos_rank"] is not None) and (not sos_open or not left):
            out.append(("T18", f"{code}: SOS served outside the window or with LEFT {left}"))
    want_ids = {"playoff_odds_sim"} | ({"postseason_bracket_sim"} if ours.get("postseason") else set())
    reg = obj.get("registry") or []
    if {x.get("model_id") for x in reg} != want_ids:
        out.append(("T11", f"registry models {[x.get('model_id') for x in reg]} are not the block's {sorted(want_ids)}"))
    for x in reg:
        if x.get("label") != MODEL_LABEL.get(x.get("model_id")) or not x.get("verdict") or set(x) != {
                "model_id", "verdict", "last_checked", "label"}:
            out.append(("T11", f"registry row {x.get('model_id')!r} is not copied plus MODEL_LABEL"))
    return out


def _check_race(obj: dict) -> list[tuple[str, str]]:
    out = []
    dates = obj.get("dates") or []
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        out.append(("T13", "race dates are not strictly increasing"))
    for code, series in (obj.get("clubs") or {}).items():
        if len(series) != len(dates) or len((obj.get("wc_gap") or {}).get(code) or []) != len(dates):
            out.append(("T13", f"{code}: a series length differs from the dates"))
            continue
        prev = [0, 0, 0, 0]
        for v in series:
            if any(a < b for a, b in zip(v, prev)):
                out.append(("T13", f"{code}: a cumulative count falls"))
                break
            prev = v
    for code, s in (obj.get("last10") or {}).items():
        if len(s) > 10 or set(s) - {"W", "L"}:
            out.append(("T15", f"{code}: last10 {s!r} malformed"))
    for code, s in (obj.get("streak") or {}).items():
        if s is not None and not re.match(r"^[WL][1-9]\d*$", str(s)):
            out.append(("T15", f"{code}: streak {s!r} malformed"))
        elif s is not None and not (obj.get("last10") or {}).get(code, "").endswith(s[0]):
            out.append(("T15", f"{code}: streak {s!r} disagrees with last10"))
    for key in ("last_game", "next_game"):
        for code, g in (obj.get(key) or {}).items():
            if g is not None and (not isinstance(g.get("pk"), int)
                                  or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(g.get("d")))):
                out.append(("T15", f"{code}: {key} {g!r} malformed"))
    return out


def _check_phist(obj: dict) -> list[tuple[str, str]]:
    out = []
    reg, pst = obj.get("regular") or {}, obj.get("post") or {}
    ra, pa = reg.get("as_of") or [], pst.get("as_of") or []
    if set(ra) & set(pa):
        out.append(("T11", "an as_of appears in both blocks"))
    if obj.get("switch_as_of") != (pa[0] if pa else None):
        out.append(("T11", "switch_as_of is not post.as_of[0]"))
    if pa and any(d >= pa[0] for d in ra):
        out.append(("T11", "a regular entry on or after switch_as_of"))
    if ra != sorted(ra) or pa != sorted(pa):
        out.append(("T11", "as_of lists are not in date order"))
    if len(pst.get("sha256") or []) != len(pa):
        out.append(("T11", "post sha256 list length differs from its as_of list"))
    miss = reg.get("missing") or []
    if miss != sorted(set(miss)) or set(miss) & set(ra):
        out.append(("T11", "regular.missing is not a sorted list of dates outside regular.as_of"))
    if ra and reg.get("source") != PHIST_REGULAR_SOURCE:
        out.append(("T11", f"regular.source {reg.get('source')!r} is not {PHIST_REGULAR_SOURCE!r}"))
    if list(reg.get("fields") or []) != list(PHIST_REGULAR_FIELDS) or \
            list(pst.get("fields") or []) != list(PHIST_POST_FIELDS):
        out.append(("T11", "a block's fields are not the plan's"))
    for blk, n_fields, n in ((reg, len(reg.get("fields") or []), len(ra)), (pst, len(pst.get("fields") or []), len(pa))):
        for code, vals in (blk.get("clubs") or {}).items():
            if len(vals) != n or any(v is not None and len(v) != n_fields for v in vals):
                out.append(("T11", f"{code}: a packed column does not match its as_of list"))
            if any(x is not None and not 0 <= x <= 1 for v in vals if v for x in v):
                out.append(("T12", f"{code}: a probability outside [0, 1]"))
    return out


def validate_standings(kind: str, obj, *, name: str | None = None, games=None, race=None, source=None,
                       disk_generated_at: str | None = None, copied_from: dict | None = None) -> dict:
    """Validate one standings payload: scores_core's file-independent rules (1
    names, 5 NaN, 6 budgets and ceilings, 7 disk age when `disk_generated_at`
    is given, 9 forbidden keys, 10 dashes; rule 11 is `revs_match`), rule 4 as
    amended (a top-level `copyright` key holding StatsAPI's line verbatim is
    exempt; MLB's terms URL anywhere else is refused), and the laws of plan 6
    for the kind. `copied_from` (STANDINGS_3) holds the served sources a
    season file's `ours` or a phist file was copied from ({futures, bracket,
    sos} or {ledger, record, opening_day, last_post_date}): every copied
    value is then checked byte-equal (T11), and a season file's seeds
    against bracket_sim.json's for the same season (T19). Returns
    `{ok, refused, logged, bytes}`."""
    if kind not in STANDINGS_KINDS:
        return {"ok": False, "refused": [("0", f"not a standings kind {kind!r}")], "logged": [], "bytes": 0}
    res = sc.validate_payload(kind, obj, name=name, disk_generated_at=disk_generated_at)
    refused, logged = list(res["refused"]), list(res["logged"])
    if not isinstance(obj, dict):
        refused.append(("1", "payload is not an object"))
        return {"ok": False, "refused": refused, "logged": logged, "bytes": res["bytes"]}
    if res["bytes"] == 0 and refused:
        return {"ok": False, "refused": refused, "logged": logged, "bytes": 0}
    # rule 4, amended: only StatsAPI's line verbatim, only at the top level
    cr = obj.get("copyright")
    if cr is not None and not (isinstance(cr, str) and COPYRIGHT_RE.match(cr)):
        refused.append(("4", "copyright is not StatsAPI's line verbatim"))
    # rule 1: schema, season and the file name
    if obj.get("schema") != SCHEMA:
        refused.append(("1", f"schema {obj.get('schema')!r} is not {SCHEMA}"))
    if not isinstance(obj.get("season"), int):
        refused.append(("1", f"season {obj.get('season')!r} is not an int"))
    base = str(name).replace("\\", "/") if name is not None else None
    if base is not None:
        want = {KIND_SEASON: f"standings/{obj.get('season')}.json",
                KIND_RACE: f"standings/{obj.get('season')}-race.json",
                KIND_PHIST: f"standings/{obj.get('season')}-phist.json",
                KIND_SNAPSHOT: f"standings/{obj.get('season')}/{obj.get('as_of')}.json"}[kind]
        if not base.endswith(want):
            refused.append(("1", f"file name {name!r} does not match {want!r}"))
    if kind in (KIND_SEASON, KIND_SNAPSHOT):
        if kind == KIND_SNAPSHOT and "ours" in obj:
            refused.append(("1", "a snapshot carries no ours block"))
        refused += check_rows(obj, games=games, race=race, source=source, logged=logged)
        if kind == KIND_SEASON and copied_from is not None:
            refused += ours_copy_mismatches(obj, futures=copied_from.get("futures"),
                                            bracket=copied_from.get("bracket"), sos=copied_from.get("sos"))
            refused += seed_mismatches(obj, copied_from.get("bracket"))
    elif kind == KIND_RACE:
        refused += _check_race(obj)
    else:
        refused += _check_phist(obj)
        if copied_from is not None:
            refused += phist_copy_mismatches(obj, copied_from.get("ledger"), copied_from.get("record"))
            od, lp = copied_from.get("opening_day"), copied_from.get("last_post_date")
            if any(not od or d < od for d in (obj.get("regular") or {}).get("as_of") or []):
                refused.append(("T11", f"a regular as_of before opening_day {od}"))
            if lp and any(d > lp for d in (obj.get("post") or {}).get("as_of") or []):
                refused.append(("T11", f"a post as_of after the last postseason game {lp}"))
    return {"ok": not refused, "refused": refused, "logged": logged, "bytes": res["bytes"]}


def revs_match(entries: list[dict], read_bytes) -> list[tuple[str, str]]:
    """Rule 11 for the standings entries of `latest.json` and `index.json`:
    each `{season, rev, race_rev, phist_rev}` equals scores_core.rev_of over
    the bytes on disk; `read_bytes(name)` returns those bytes or None."""
    out = []
    for e in entries or []:
        y = e.get("season")
        for key, name in (("rev", f"standings/{y}.json"), ("race_rev", f"standings/{y}-race.json"),
                          ("phist_rev", f"standings/{y}-phist.json")):
            if e.get(key) is None:
                continue
            data = read_bytes(name)
            if data is None or sc.rev_of(data) != e[key]:
                out.append(("11", f"{key} of {y} does not hash the bytes on disk"))
    return out


# --------------------------------------------------------------------------- #
# 10. The tracked copy of the final tables
# --------------------------------------------------------------------------- #
_KEEP_TOP = ("wins", "losses", "gamesPlayed", "winningPercentage", "divisionGamesBack", "wildCardGamesBack",
             "leagueGamesBack", "sportGamesBack", "divisionRank", "leagueRank", "sportRank", "wildCardRank",
             "clinchIndicator", "magicNumber", "eliminationNumberDivision", "wildCardEliminationNumber",
             "runsScored", "runsAllowed", "runDifferential", "season")


def trim_payload(payload, keep_extra=()) -> dict:
    """A standings response trimmed to the fields `parse_standings` reads, plus
    the copyright line (and any `keep_extra` team keys a fixture documents)."""
    recs = []
    for rec in (payload or {}).get("records") or []:
        trs = []
        for tr in rec.get("teamRecords") or []:
            t = {"team": {"id": (tr.get("team") or {}).get("id")}}
            for k in _KEEP_TOP + tuple(keep_extra):
                if k in tr:
                    t[k] = tr[k]
            if "leagueRecord" in tr:
                t["leagueRecord"] = {"ties": (tr.get("leagueRecord") or {}).get("ties")}
            if "streak" in tr:
                t["streak"] = {"streakCode": (tr.get("streak") or {}).get("streakCode")}
            r = tr.get("records") or {}
            t["records"] = {
                "splitRecords": [{"type": s.get("type"), "wins": s.get("wins"), "losses": s.get("losses")}
                                 for s in r.get("splitRecords") or [] if s.get("type") in _SPLIT_TYPES],
                "divisionRecords": [{"wins": s.get("wins"), "losses": s.get("losses"),
                                     "division": {"id": (s.get("division") or {}).get("id")}}
                                    for s in r.get("divisionRecords") or []],
                "leagueRecords": [{"wins": s.get("wins"), "losses": s.get("losses"),
                                   "league": {"id": (s.get("league") or {}).get("id")}}
                                  for s in r.get("leagueRecords") or []],
                "expectedRecords": [{"type": s.get("type"), "wins": s.get("wins"), "losses": s.get("losses")}
                                    for s in r.get("expectedRecords") or [] if s.get("type") == "xWinLoss"],
            }
            trs.append(t)
        recs.append({"league": {"id": (rec.get("league") or {}).get("id")},
                     "division": {"id": (rec.get("division") or {}).get("id")}, "teamRecords": trs})
    return {"copyright": (payload or {}).get("copyright"), "records": recs}


LABS_FIRST, LABS_LAST = 2000, 2025


class MissingCache(Exception):
    """A season's standings cache is absent: the caller STOPs, never fetches."""


def write_labs_copy(cache_dir, out_dir, seasons=range(LABS_FIRST, LABS_LAST + 1)) -> dict:
    """Write the tracked, unpublished `data/_labs/standings/
    statsapi_standings_<Y>.json` for each season from the local
    `<cache_dir>/statsapi_standings_<Y>.json`, trimmed to the fields item 2
    reads plus copyright, with `_source` naming the cache file and its
    modification time (UTC). Never fetches: a missing cache raises
    MissingCache. Returns {season: bytes written}."""
    sizes = {}
    for y in seasons:
        src = os.path.join(os.fspath(cache_dir), f"statsapi_standings_{y}.json")
        if not os.path.exists(src):
            raise MissingCache(f"standings cache {y} missing")
        with open(src, encoding="utf-8") as fh:
            payload = json.load(fh)
        mtime = _dt.datetime.fromtimestamp(os.path.getmtime(src), _dt.timezone.utc)
        obj = {"_source": {"file": f".cache/statsapi_standings_{y}.json",
                           "mtime": mtime.isoformat(timespec="seconds")}}
        obj.update(trim_payload(payload))
        sizes[y] = write_file(os.path.join(os.fspath(out_dir), f"statsapi_standings_{y}.json"), obj)
    return sizes


__all__ = [
    "STANDINGS_LIVE", "STANDINGS_CHARTS", "SCHEMA", "COPYRIGHT_RE", "FORMAT", "format_for", "NOTE_2020",
    "TIEBREAK_BY_RULE", "TIEBREAK_2020", "TIEBREAK_EXTRA_GAME", "tiebreak_text", "QUALIFIED_TEXT",
    "X_EXPONENT", "division_of", "division_champions", "parse_standings", "games_from_schedule",
    "final_games", "games_left", "last_results", "head_to_head", "build_race", "race_value_at",
    "race_matches_snapshots", "t7_misses", "streak_code", "last_and_next", "race_extras", "build_season_file", "build_snapshot_file", "build_race_file",
    "build_phist_file", "encode", "write_file", "check_rows", "validate_standings", "revs_match",
    "trim_payload", "write_labs_copy", "MissingCache", "KIND_SEASON", "KIND_RACE", "KIND_PHIST",
    "KIND_SNAPSHOT", "round2",
]
