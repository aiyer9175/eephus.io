# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Build F-SCORE, the seven-season franchise score (fscore.json), dark behind FSCORE_LIVE.

THE ASK (owner ask B, 2026-09-30): a franchise score on the club pages, the
Franchises board and the MLB Stats Teams tab that rounds up what the site
already knows about each club (regular-season wins, division titles, deep
postseason runs and titles, team strength and run differential, the farm and
player development, payroll) over a seven-season trailing window. The design
is the F-SCORE lane (Part 8 bundle fscore.md sections 2 to 4) as the plan
XWAR_FSCORE_PLAN.md amends it (F1 to F12); the owner's answers FS-Q1 to FS-Q4
(2026-10-01) set the constants below.

WHAT IT IS. A DESCRIPTIVE league-relative score. Four pillars, each a
population z across the 30 clubs:
  * RESULTS: per club-season V = (W - L) / 2 + 8 x division title + the
    postseason ladder (8 wins a step: a berth 8, the division series or a bye
    16, the LCS 24, a World Series loss 32, a title 40), centred on the
    season's league mean of the division and ladder part, so the 30 values of
    a season sum to zero. Steps not yet played count nothing until they are;
    a season whose postseason is running is flagged in_progress.
  * STRENGTH: run differential per 162 games over the same seasons (0.50),
    the Franchise ROSTER score (0.30) and the Franchise OUTLOOK score (0.20),
    the last two computed HERE from the same served values the Franchise
    exporter reads (war_leaderboards teams war; mlb_projections team_outlook
    wins) through franchise_export._score_100, never read off
    franchise_board.json (the board embeds this payload, so that would be
    circular).
  * PIPELINE: the Franchise FARM score of the PROSPX farm composite (0.60)
    and 7yDvM+ as served in org_summary (0.40).
  * OPERATIONS: wins above a replacement-level club (REPLACEMENT_PCT of games,
    47.7 of 162) per million dollars of Spotrac total payroll above a 26-man
    league-minimum floor (2020 prorated with its payroll), read as a normal
    score of the within-season rank (van der Waerden, rank / 31) because the
    ratio is right-skewed. Read through the cache-only payroll reader
    (fa_sources.read_cached_payroll_history, Q9_16): never a second Spotrac
    parser, never a network call. A season whose page resolves fewer than 30
    clubs puts OPERATIONS dark, and then the scheme's DECLARED dark vector
    applies and is printed; nothing is redistributed pro rata at runtime.
The index is the weighted pillar mean re-standardised to 100 + 10z
(franchise_export._score_100) before any rank or letter is taken, exactly as
the Franchise Index is; letters follow rank (storage._letter_grade).

THE WINDOW. The seven most recent seasons whose regular season is complete
(2020 to 2026 from 2026-09-28), weighted with a three-season half-life
(FS-Q2): w(s) proportional to 0.5 ** ((newest - s) / 3). 2020 counts as
played (recorded default): its 60 games of wins and runs, its division titles
and postseason in full; OPERATIONS weights it 60/162 of its recency weight.

THE LADDER IS A PUBLISHED CHOICE, NOT AN ESTIMATE. No scale was fitted and no
F-SCORE quantity is related to wins anywhere. For the record (this docstring
and the plan only, never served, plan Part 8 8.A and ruling X9): in the
twelve-club seasons 2022 to 2025 the spread of wins above .500 across the 30
clubs (sd 14.44, 12.90, 12.28, 11.50) and the spread of the division plus
postseason part under 8 wins a step (12.96, 12.45, 13.12, 13.44) came out
alike, which is what informed the choice of 8; it is a spread match, not a
value of a round.

MANAGEMENT IS SHOWN, NOT SCORED (FS-Q3). In-game management is shown under
DUGOUT and not scored: the one decision family the site has gated, the running
game, did not repeat between halves of a club's own season (per-agent decision
value). THE ADMISSION RULE, written here before any number exists: a decision
family that passes its own frozen split-half gate enters OPERATIONS at 0.05 of
the index, taken from RESULTS (RESULTS 0.45 under scheme A), as that family's
season-controlled realized value, never a cross-family mWPA total, never a
decision-quality grade and never a manager skill claim. Until a family passes,
nothing from management_board.json enters this module. FSCORE_DUGOUT_LINK is
the FS-Q3 switch: True prints the DUGOUT sentence, False leaves management out
of F-SCORE's copy and changes nothing else.

THE FLAG (plan X9, Part 8 class 2). FSCORE_LIVE = False: main() writes
.cache/fscore/preview/fscore.json and nothing under data/; franchise_export
embeds nothing and keeps pennants and titles forbidden; team_stats_export adds
no column. FS_2F_FLIP turns it on in one commit with the registry row, the
glossary entries and the catalog row.

build() returns the document and never writes; main() writes it and exits 2
on FscoreRefusal, leaving the previous file standing (the franchise_export
pattern). Every identity of fscore.md 2.12 is asserted before any write.
Deterministic apart from generated_at; never opens a socket.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
CACHE = ROOT / ".cache"
OUT_NAME = "fscore.json"
LIVE_OUT = DATA / OUT_NAME
PREVIEW_OUT = CACHE / "fscore" / "preview" / OUT_NAME

SCHEMA = 1
N_CLUBS = 30

#: The flag (plan X9). False: the preview file only, nothing served moves.
FSCORE_LIVE = False

#: FS-Q1 (owner, 2026-10-01): scheme A, results-heavy.
SCHEME = "A"
PILLARS = ("results", "strength", "pipeline", "operations")
PILLAR_WEIGHTS = {"results": 0.50, "strength": 0.25, "pipeline": 0.20, "operations": 0.05}
#: The declared vector while OPERATIONS is dark (fscore.md 2.9), never pro rata.
DARK_WEIGHTS = {"results": 0.53, "strength": 0.26, "pipeline": 0.21, "operations": 0.0}
LEG_WEIGHTS = {"strength": {"rd162": 0.50, "roster": 0.30, "outlook": 0.20},
               "pipeline": {"farm": 0.60, "dvm7": 0.40}}
#: Linear ladder: each step reached is worth per_step regular-season wins; a
#: division title adds `division`. Round 0 missed, 1 berth, 2 division series
#: or bye, 3 LCS, 4 World Series, 5 title.
LADDER = {"kind": "linear", "per_step": 8, "division": 8}
#: FS-Q2 (owner, 2026-10-01): a three-season half-life.
HALF_LIFE = 3.0
WINDOW_LEN = 7
#: Recorded default (plan section 10): 2020 counts as played.
RULE_2020 = "played"
GAMES_2020 = 60
#: Wins of a replacement-level club per game: (2430 - 1000) / 30 / 162, the
#: Team Outlook league accounting (team_outlook_eval league_sum_accounting).
REPLACEMENT_PCT = 0.2944
ROSTER_FLOOR = 26
#: OPERATIONS is built live because the Q9_16 cache-only payroll reader
#: (fa_sources.read_cached_payroll_history) exists; a season that parses under
#: 30 clubs still puts it dark on the declared vector at runtime.
OPERATIONS_LIVE = True
#: FS-Q3 (owner, 2026-10-01): management shown beside F-SCORE, not scored.
FSCORE_DUGOUT_LINK = True
#: The admission rule's weight and its donor pillar (docstring above).
MGMT_ADMISSION = {"weight": 0.05, "taken_from": "results"}

#: Display names of the war_source provider ids the served boards stamp.
PROVIDER_LABEL = {"ewar_v2": "eWAR v2", "fwar": "fWAR", "bwar": "bWAR",
                  "ewar_merged": "eWAR (merged)"}

#: Key names the writer refuses anywhere in the payload (fscore.md 2.12 item 9).
FORBIDDEN_KEYS = {"revenue", "revenues", "valuation", "valuations", "decision_quality",
                  "manager_skill"}
_GRADE_KEY = re.compile(r"(^|_)(e?fv|consensus|grades?)(_|$)")
FORECAST_WORDS = ("will", "predicts", "due", "on pace", "expected to", "luck",
                  "regress", "trending", "sleeper")

ROUND_WORD = {2: "division series", 4: "World Series"}
LEAGUE_OF = {103: "AL", 104: "NL"}

SEASON_COLS = ["season", "w", "l", "rd", "div", "round", "series_won", "value", "weight",
               "ops_z", "in_progress", "post_text"]

DUGOUT_SENTENCE = ("In-game management is shown under DUGOUT and not scored: the one decision "
                   "family the site has gated, the running game, did not repeat between halves "
                   "of a club's own season (per-agent decision value), so a score built on it "
                   "would rank noise.")


class FscoreRefusal(RuntimeError):
    """A club, a completed season or a bracket is missing or broken, a pillar
    resolves fewer than 30 clubs, or an identity fails. The caller keeps the
    previous file and files a red under fscore_export."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _j(name: str, base: Path = DATA):
    try:
        return json.loads((Path(base) / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _r(v, nd):
    return None if v is None else round(float(v), nd)


def _z(values: dict) -> dict:
    """Population z across the values (statistics.pstdev, as _score_100)."""
    xs = [float(v) for v in values.values()]
    mu, sd = statistics.mean(xs), statistics.pstdev(xs)
    return {k: (0.0 if sd == 0 else (float(v) - mu) / sd) for k, v in values.items()}


def _pool(values: dict) -> dict:
    xs = [float(v) for v in values.values() if v is not None]
    return {"n": len(xs), "mean": _r(statistics.mean(xs), 3) if xs else None,
            "sd": _r(statistics.pstdev(xs), 3) if xs else None}


def recency_weights(seasons, half_life: float = HALF_LIFE) -> dict:
    """{season: weight}, w(s) proportional to 0.5 ** ((newest - s) / half_life),
    normalised to sum to 1 over the window."""
    newest = max(seasons)
    raw = {s: 0.5 ** ((newest - s) / half_life) for s in seasons}
    tot = sum(raw.values())
    return {s: v / tot for s, v in raw.items()}


def season_games_factor(season: int) -> float:
    """The share of a full season a season's payroll and OPERATIONS weight
    carry: 60/162 for 2020 as played, 1 otherwise."""
    return GAMES_2020 / 162.0 if (int(season) == 2020 and RULE_2020 == "played") else 1.0


def ladder_value(rnd: int) -> float:
    if LADDER["kind"] != "linear":
        raise FscoreRefusal(f"ladder kind {LADDER['kind']!r} is not built")
    return float(LADDER["per_step"]) * int(rnd)


def ladder_steps() -> list:
    return [ladder_value(r) for r in range(6)]


def normal_scores(values: dict) -> dict:
    """Within-season rank read as a normal score: ascending value, ties broken
    by code, z = Phi^-1(rank / (n + 1))."""
    nd = statistics.NormalDist()
    order = sorted(values, key=lambda c: (values[c], c))
    n = len(order)
    return {c: nd.inv_cdf((i + 1) / (n + 1)) for i, c in enumerate(order)}


_ON_DISK = object()


def window_seasons(today: date | None = None, *, season_now: int | None = None,
                   regular_season_end=_ON_DISK,
                   live_bracket_on_disk: bool | None = None) -> list:
    """The seven most recent seasons whose regular season is complete. The live
    season counts once today is past its regularSeasonEndDate (the cached
    /seasons payload, read unless `regular_season_end` is passed; None means no
    date); with no date, once its postseason bracket is cached
    (postseason.fetch never runs before the regular season ends)."""
    import franchise_export as fe
    today = today or date.today()
    now = int(season_now if season_now is not None else fe.SEASON_NOW)
    if regular_season_end is _ON_DISK:
        try:
            from mgmt_decisions import regular_season_end_on_disk
            regular_season_end = regular_season_end_on_disk(now)
        except Exception:                                      # noqa: BLE001
            regular_season_end = None
    if regular_season_end:
        done = today.isoformat() > str(regular_season_end)[:10]
    else:
        if live_bracket_on_disk is None:
            import postseason
            live_bracket_on_disk = postseason.cache_path(now).exists()
        done = bool(live_bracket_on_disk)
    newest = now if done else now - 1
    return list(range(newest - WINDOW_LEN + 1, newest + 1))


def roster_label(war_board: dict, stamp_boards: dict) -> tuple[str, str]:
    """(label, where) of the WAR the roster leg is on, read from a served
    provider stamp, never typed (plan X14): war_leaderboards.json's own
    war_provider when it carries one, else the WAR-rate stamp the /mlbstats/
    boards serve beside the same displayed WAR. Refuses when no stamp is on
    disk or the id is unknown."""
    cands = [("war_leaderboards.json", (war_board or {}).get("war_provider")),
             ("war_leaderboards.json team_basis",
              ((war_board or {}).get("team_basis") or {}).get("war_provider"))]
    for name in ("hitter_leaderboards.json", "bullpen_leaderboards.json"):
        blob = stamp_boards.get(name) or {}
        for blk in ("multiyear_war_rate", "multiyear"):
            cands.append((f"{name} {blk}", (blob.get(blk) or {}).get("war_provider")))
    for where, prov in cands:
        if prov:
            if prov not in PROVIDER_LABEL:
                raise FscoreRefusal(f"roster leg: provider {prov!r} ({where}) has no display name")
            return PROVIDER_LABEL[prov], f"{where}.war_provider = {prov}"
    raise FscoreRefusal("roster leg: no served WAR provider stamp on disk")


def _round_name(rnd: int, best_of, league: str | None) -> str:
    if rnd == 1:
        return "wild card game" if best_of == 1 else "wild card series"
    if rnd == 3:
        return f"{league}CS" if league else "LCS"
    return ROUND_WORD.get(rnd, "postseason")


def post_text(rnd: int, bye: bool, alive: bool, best_of_by_round: dict, league: str | None) -> str:
    """The Postseason cell in words: missed; won the World Series; lost the
    NLCS; bye, lost the division series; in the wild card series."""
    if rnd <= 0:
        return "missed"
    pre = "bye, " if bye else ""
    if rnd >= 5:
        return pre + "won the World Series"
    name = _round_name(rnd, best_of_by_round.get(rnd), league)
    return pre + (f"in the {name}" if alive else f"lost the {name}")


# --------------------------------------------------------------------------
# inputs (disk) and the computation (pure)
# --------------------------------------------------------------------------

def load_inputs(seasons: list) -> dict:
    """Everything build() reads, from disk, as one dict compute() takes.
    Read-only: standings and postseason caches, the served boards, the
    cache-only payroll reader, the league minimum table, the registry."""
    import franchise_export as fe
    import postseason
    import salary_path

    standings, _ids, disagreements = fe._standings()
    post = {}
    for y in seasons:
        try:
            post[y] = postseason.load(y)
        except postseason.PostseasonError as exc:
            raise FscoreRefusal(f"postseason {y}: the bracket breaks: {exc}") from None
    war = _j("war_leaderboards.json") or {}
    proj = _j("mlb_projections.json") or {}
    ts = _j("timeseries.json") or {}
    stamp_boards = {n: _j(n) or {} for n in ("hitter_leaderboards.json", "bullpen_leaderboards.json")}
    payroll = None
    if OPERATIONS_LIVE:
        import fa_sources
        hist = fa_sources.read_cached_payroll_history(seasons)
        payroll = {}
        for y, rec in (hist.get("seasons") or {}).items():
            rows = {}
            for r in rec.get("payroll") or []:
                c = fe._canon(r.get("team"))
                if c and r.get("total_payroll_usd") is not None:
                    rows[c] = float(r["total_payroll_usd"])
            payroll[int(y)] = {"rows": rows, "fetched": rec.get("payroll_fetched")}
    return {
        "standings": standings,
        "flag_disagreements": [r for r in disagreements if r[0] in seasons],
        "postseason": post,
        "roster": {c: r.get("war") for c, r in fe._team_rows(war).items()},
        "outlook": {fe._canon(r.get("team")): r.get("wins") for r in proj.get("team_outlook") or []
                    if fe._canon(r.get("team"))},
        "farm": {fe._canon(o.get("org")): o.get("farm_score") for o in ts.get("org_summary") or []
                 if fe._canon(o.get("org"))},
        "dvm7": {fe._canon(o.get("org")): (o.get("dvm_plus") or {}).get("7y")
                 for o in ts.get("org_summary") or [] if fe._canon(o.get("org"))},
        "roster_label": roster_label(war, stamp_boards),
        "roster_as_of": war.get("as_of"),
        "payroll": payroll,
        "league_min": {y: salary_path.league_min_usd(y) for y in seasons},
        "registry": _j("model_registry.json") or {},
        "stamps": {"war_leaderboards": war.get("generated_at"),
                   "mlb_projections": proj.get("generated_at"),
                   "timeseries": ts.get("generated_at")},
    }


def _need30(name: str, values: dict, codes: list) -> dict:
    missing = sorted(c for c in codes if values.get(c) is None)
    if missing:
        raise FscoreRefusal(f"{name}: {len(codes) - len(missing)} of {N_CLUBS} clubs resolve; "
                            f"missing {missing}")
    return {c: float(values[c]) for c in codes}


def compute(inp: dict, seasons: list, *, today: date) -> dict:
    """The F-SCORE document from the inputs (pure; tests call it on fixtures)."""
    import franchise_export as fe

    seasons = sorted(int(s) for s in seasons)
    if len(seasons) != WINDOW_LEN or seasons != list(range(seasons[0], seasons[0] + WINDOW_LEN)):
        raise FscoreRefusal(f"the window must be {WINDOW_LEN} consecutive seasons: {seasons}")
    if RULE_2020 != "played":
        raise FscoreRefusal(f"2020 rule {RULE_2020!r} is not built")
    newest = seasons[-1]
    st = inp["standings"]

    # ---- the clubs: every window season must carry the same thirty -----------------
    codes = sorted(c for c, by in st.items() if newest in by)
    if len(codes) != N_CLUBS:
        raise FscoreRefusal(f"standings {newest}: {len(codes)} clubs, expected {N_CLUBS}")
    for y in seasons:
        missing = [c for c in codes if y not in (st.get(c) or {})]
        if missing:
            raise FscoreRefusal(f"standings {y}: missing club(s) {missing}")

    # ---- per season: standings, bracket, values -------------------------------------
    rw = recency_weights(seasons)
    ow_raw = {y: rw[y] * season_games_factor(y) for y in seasons}
    ow = {y: v / sum(ow_raw.values()) for y, v in ow_raw.items()}
    ops_live, ops_reason = bool(OPERATIONS_LIVE), None
    if ops_live:
        pay = inp.get("payroll") or {}
        thin = [y for y in seasons if len(set((pay.get(y) or {}).get("rows") or {}) & set(codes)) < N_CLUBS]
        if thin:
            ops_live = False
            ops_reason = f"payroll pages resolve fewer than {N_CLUBS} clubs for {thin}"
    else:
        ops_reason = "OPERATIONS_LIVE is False: the payroll-history reader is not wired"

    facts, in_progress = {}, []
    rows = {c: [] for c in codes}
    values = {c: {} for c in codes}
    rd162 = {c: {} for c in codes}
    opsz = {c: {} for c in codes}
    counts = {c: {"w": 0, "l": 0, "rd": 0, "division_titles": 0, "berths": 0, "series_won": 0,
                  "pennants": 0, "titles": 0} for c in codes}
    for y in seasons:
        ps = inp["postseason"].get(y)
        if ps is None:
            raise FscoreRefusal(f"postseason {y}: no bracket on disk")
        if y < newest and not ps.get("complete"):
            raise FscoreRefusal(f"postseason {y}: a completed season's bracket is not complete")
        if ps.get("complete"):
            bad = []
            reached = [v["round_reached"] for v in ps["clubs"].values()]
            if sum(1 for r in reached if r >= 5) != 1:
                bad.append("champions")
            if sum(1 for r in reached if r >= 4) != 2:
                bad.append("pennants")
            if bad:
                raise FscoreRefusal(f"postseason {y}: broken bracket ({', '.join(bad)})")
        live_post = not ps.get("complete")
        if live_post:
            in_progress.append(y)
        best_of = {}
        won_round = {}
        for s in ps.get("series") or []:
            rnd, bo, a, b, winner = s[1], s[2], s[3], s[4], s[7]
            for cl in (a, b):
                if cl:
                    best_of.setdefault(cl, {})[rnd] = bo
            if winner:
                won_round[winner] = max(won_round.get(winner, 0), rnd)
        div = {c: 1 if st[c][y].get("div_champ") else 0 for c in codes}
        if sum(div.values()) != 6:
            raise FscoreRefusal(f"standings {y}: {sum(div.values())} division champions, expected 6")
        rnd_of, alive_of, bye_of, sw_of = {}, {}, {}, {}
        for c in codes:
            pc = (ps.get("clubs") or {}).get(c) or {}
            rr = int(pc.get("round_reached") or 0)
            if c in won_round:
                rr = max(rr, min(won_round[c] + 1, 5))
            rnd_of[c], bye_of[c], sw_of[c] = rr, bool(pc.get("bye")), int(pc.get("series_won") or 0)
            alive_of[c] = bool(pc.get("in_progress")) and live_post and rr < 5
        extra = {c: LADDER["division"] * div[c] + ladder_value(rnd_of[c]) for c in codes}
        mean_extra = statistics.mean(extra.values())
        v = {}
        for c in codes:
            r = st[c][y]
            if r.get("w") is None or r.get("l") is None or r.get("rd") is None or not r.get("gp"):
                raise FscoreRefusal(f"standings {y} {c}: a record field is missing")
            v[c] = (r["w"] - r["l"]) / 2.0 + extra[c] - mean_extra
        if abs(sum(v.values())) > 1e-9:
            raise FscoreRefusal(f"identity: the season values of {y} sum to {sum(v.values())}, not 0")
        if ops_live:
            lmin = float(inp["league_min"][y])
            floor = ROSTER_FLOOR * lmin * season_games_factor(y)
            eff = {}
            for c in codes:
                r = st[c][y]
                over = max(inp["payroll"][y]["rows"][c] - floor, 1e6) / 1e6
                eff[c] = (r["w"] - REPLACEMENT_PCT * r["gp"]) / over
            ns = normal_scores(eff)
        for c in codes:
            r = st[c][y]
            values[c][y] = v[c]
            rd162[c][y] = float(r["rd"]) if (y == 2020 and RULE_2020 == "played") else r["rd"] * 162.0 / r["gp"]
            if ops_live:
                opsz[c][y] = ns[c]
            lg = LEAGUE_OF.get(r.get("league_id"))
            text = post_text(rnd_of[c], bye_of[c], alive_of[c], best_of.get(c, {}), lg)
            rows[c].append([y, r["w"], r["l"], r["rd"], div[c], rnd_of[c], sw_of[c], _r(v[c], 1),
                            _r(rw[y], 4), _r(opsz[c].get(y), 2) if ops_live else None,
                            bool(alive_of[c]), text])
            k = counts[c]
            k["w"] += r["w"]
            k["l"] += r["l"]
            k["rd"] += r["rd"]
            k["division_titles"] += div[c]
            k["berths"] += 1 if rnd_of[c] >= 1 else 0
            k["series_won"] += sw_of[c]
            k["pennants"] += 1 if rnd_of[c] >= 4 else 0
            k["titles"] += 1 if rnd_of[c] >= 5 else 0
        facts[str(y)] = {
            "complete": bool(ps.get("complete")),
            "champion": next((c for c in codes if rnd_of[c] >= 5), None),
            "pennants": sorted(c for c in codes if rnd_of[c] >= 4),
            "division_champions": sorted(c for c in codes if div[c]),
            "berths": sum(1 for c in codes if rnd_of[c] >= 1),
            "byes": sorted(c for c in codes if bye_of[c]),
            "flag_disagreements": [[r[1], r[2], r[3]] for r in inp.get("flag_disagreements") or []
                                   if r[0] == y],
            "source": ps.get("source"), "fetched_at": ps.get("fetched_at"),
        }

    # ---- window means -----------------------------------------------------------------
    res_w = {c: sum(rw[y] * values[c][y] for y in seasons) for c in codes}
    rd_w = {c: sum(rw[y] * rd162[c][y] for y in seasons) for c in codes}
    ops_w = {c: sum(ow[y] * opsz[c][y] for y in seasons) for c in codes} if ops_live else None

    # ---- today: the Franchise branch scores on the same served values ----------------
    v_roster = _need30("roster (war_leaderboards teams war)", inp["roster"], codes)
    v_outlook = _need30("outlook (mlb_projections team_outlook wins)", inp["outlook"], codes)
    v_farm = _need30("farm (timeseries org_summary farm_score)", inp["farm"], codes)
    v_dvm = _need30("dvm7 (timeseries org_summary dvm_plus 7y)", inp["dvm7"], codes)
    s_roster, s_outlook, s_farm = fe._score_100(v_roster), fe._score_100(v_outlook), fe._score_100(v_farm)
    roster_z = {c: (s_roster[c] - 100.0) / 10.0 for c in codes}
    outlook_z = {c: (s_outlook[c] - 100.0) / 10.0 for c in codes}
    farm_z = {c: (s_farm[c] - 100.0) / 10.0 for c in codes}
    dvm_z = _z(v_dvm)
    rd_z = _z(rd_w)

    ls, lp = LEG_WEIGHTS["strength"], LEG_WEIGHTS["pipeline"]
    strength_raw = {c: ls["rd162"] * rd_z[c] + ls["roster"] * roster_z[c] + ls["outlook"] * outlook_z[c]
                    for c in codes}
    pipeline_raw = {c: lp["farm"] * farm_z[c] + lp["dvm7"] * dvm_z[c] for c in codes}
    pz = {"results": _z(res_w), "strength": _z(strength_raw), "pipeline": _z(pipeline_raw),
          "operations": _z(ops_w) if ops_live else None}
    applied = dict(PILLAR_WEIGHTS) if ops_live else dict(DARK_WEIGHTS)
    raw = {c: sum(applied[p] * pz[p][c] for p in PILLARS if pz[p] is not None) for c in codes}
    score = fe._score_100(raw)
    rank = fe._rank_desc(score)

    clubs = {}
    for c in codes:
        pillars = {}
        for p in PILLARS:
            z = pz[p][c] if pz[p] is not None else None
            pillars[p] = {"z": _r(z, 3), "score": _r(100.0 + 10.0 * z, 1) if z is not None else None}
        clubs[c] = {
            "score": score[c], "rank": rank[c], "letter": fe.letter_for_rank(rank[c]),
            "raw": _r(raw[c], 4),
            "pillars": pillars,
            "legs": {"results_wins": _r(res_w[c], 2), "rd162": _r(rd_w[c], 1),
                     "roster_z": _r(roster_z[c], 3), "outlook_z": _r(outlook_z[c], 3),
                     "farm_z": _r(farm_z[c], 3), "dvm7": v_dvm[c], "dvm7_z": _r(dvm_z[c], 3),
                     "ops": _r(ops_w[c], 3) if ops_live else None},
            "counts": counts[c],
            "in_progress": any(r[10] for r in rows[c]),
            "seasons": rows[c],
        }

    label, label_src = inp["roster_label"]
    oldest = seasons[0]
    pct = {p: int(round(100 * applied[p])) for p in PILLARS}
    copy = {
        "fscore_sentence": ("Seven seasons and today, re-standardised across 30 clubs. "
                            "Descriptive, not a forecast."),
        "fscore_vs_index": ("Franchise Index: the club today (roster, 2027 outlook, farm). "
                            "F-SCORE: the last seven seasons plus today."),
        "fscore_teams_past": "F-SCORE is a seven-season score as of today; it prints on the current season only.",
        "fscore_overlap": ("RESULTS and STRENGTH overlap by design: wins and run differential come "
                           "from the same seasons."),
        "fscore_honesty": ("Descriptive: a weighted summary of what the club did in the last seven "
                           "seasons and where it stands today. The weights and the postseason ladder "
                           "are a published choice, not an estimate, and nothing here forecasts wins, "
                           "a playoff berth or a title. One leg, 2027 wins, is a provisional projection."),
        "board_tooltip": ("F-SCORE: seven seasons and today. 100 = league average, 10 = one standard "
                          "deviation. Descriptive, not a forecast."),
        "weights_foot": (", ".join(f"{p.upper()} {pct[p]}%" for p in PILLARS if applied[p])
                         + ("" if ops_live else ", OPERATIONS dark")),
        "ladder_note": (f"A division title adds {LADDER['division']} wins and each postseason step "
                        f"reached adds {LADDER['per_step']}: a berth {ladder_steps()[1]:.0f}, the "
                        f"division series or a bye {ladder_steps()[2]:.0f}, the LCS "
                        f"{ladder_steps()[3]:.0f}, the World Series {ladder_steps()[4]:.0f}, a title "
                        f"{ladder_steps()[5]:.0f}. A published choice, not an estimate."),
        "recency_note": (f"The seasons {oldest} to {newest} are averaged with a "
                         f"{HALF_LIFE:g}-season half-life: {newest} counts "
                         f"{round(100 * rw[newest])} percent, {oldest} {round(100 * rw[oldest])} percent."),
        "rule_2020_note": ("2020 counts as played: its 60 games of wins and runs, its division titles "
                           "and its postseason in full."),
        "roster_leg": f"team {label} on the current roster, {inp.get('roster_as_of')}",
        "operations_note": ("OPERATIONS: wins above a replacement-level club per million dollars of "
                            "Spotrac payroll above a minimum roster, ranked within each season."
                            if ops_live else
                            f"OPERATIONS is dark ({ops_reason}); the declared weights "
                            f"{', '.join(f'{p.upper()} {pct[p]}%' for p in PILLARS if applied[p])} apply."),
    }
    if in_progress:
        copy["fscore_in_progress"] = (f"{in_progress[-1]} postseason in progress: each round counts "
                                      "once it is played.")
    if FSCORE_DUGOUT_LINK:
        copy["fscore_dugout"] = DUGOUT_SENTENCE

    reg_rows = {m.get("model_id"): m for m in (inp.get("registry") or {}).get("models") or []}
    # [{model_id, verdict}] rows, not keys: a model id is a name, never a grouping.
    registry = [{"model_id": mid, "verdict": (reg_rows.get(mid) or {}).get("verdict")}
                for mid in ("franchise_score", "ewar", "team_win_projections", "farm_grades",
                            "dvm_plus_org")]

    doc = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": today.isoformat(),
        "live": bool(FSCORE_LIVE),
        "window": {"seasons": seasons, "newest": newest, "half_life": HALF_LIFE,
                   "weights": {str(y): _r(rw[y], 4) for y in seasons},
                   "operations_weights": {str(y): _r(ow[y], 4) for y in seasons},
                   "rule_2020": RULE_2020, "in_progress": in_progress},
        "scheme": {"id": SCHEME, "pillars": dict(PILLAR_WEIGHTS), "dark": dict(DARK_WEIGHTS),
                   "applied": applied, "operations_live": ops_live,
                   "operations_dark_reason": ops_reason,
                   "legs": {k: dict(v) for k, v in LEG_WEIGHTS.items()},
                   "ladder": {"kind": LADDER["kind"], "per_step": LADDER["per_step"],
                              "division": LADDER["division"], "steps": ladder_steps()},
                   "replacement_pct": REPLACEMENT_PCT, "roster_floor": ROSTER_FLOOR},
        "league": {"n": N_CLUBS, "score": _pool(score), "raw_sd": _r(statistics.pstdev(raw.values()), 3),
                   "pillar_pools": {"results_wins": _pool(res_w), "rd162": _pool(rd_w),
                                    "strength_raw": _pool(strength_raw),
                                    "pipeline_raw": _pool(pipeline_raw), "dvm7": _pool(v_dvm),
                                    "ops": _pool(ops_w) if ops_live else None}},
        "facts": facts,
        "season_cols": list(SEASON_COLS),
        "clubs": clubs,
        "copy": copy,
        "sources": {
            "standings": f"StatsAPI standings cache {oldest}-{newest} through franchise_export._standings",
            "postseason": {str(y): {"source": facts[str(y)]["source"], "fetched_at": facts[str(y)]["fetched_at"]}
                           for y in seasons},
            "roster": f"war_leaderboards teams war ({label_src})",
            "outlook": "mlb_projections team_outlook wins (team_win_projections, provisional)",
            "farm": "timeseries org_summary farm_score, re-standardised as the Franchise FARM score",
            "dvm7": "timeseries org_summary dvm_plus 7y",
            "payroll": ({str(y): (inp["payroll"].get(y) or {}).get("fetched") for y in seasons}
                        if inp.get("payroll") else None),
            "generated_at": dict(inp.get("stamps") or {}),
        },
        "registry": registry,
        "what_fscore_does_not_claim": [
            "a forecast of wins, a berth or a title",
            "a measured weighting: the weights and the ladder are a published choice",
            "a decision-quality grade: in-game management is shown, not scored",
            "postseason skill: rounds are counted as results, not as evidence a club is built for October",
            "revenue, attendance or a franchise valuation: not sourced",
        ],
        "accountability": {
            "management": {"scored": False,
                           "admission_rule": ("a decision family that passes its own frozen split-half "
                                              "gate enters OPERATIONS at 0.05 of the index, taken from "
                                              "RESULTS; none has passed")},
            "overlaps": ["the newest season enters as a record and as the roster that produced it",
                         "DvM+ also sits inside the farm composite"],
            "standings_flag_disagreements": [r for r in inp.get("flag_disagreements") or []],
        },
    }
    return doc


# --------------------------------------------------------------------------
# identities (fscore.md 2.12 as amended), asserted before every write
# --------------------------------------------------------------------------

def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, str(k)
            yield from _walk_keys(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def identity_failures(doc: dict, inp: dict | None = None) -> list:
    """Every identity the document breaks, as sentences; [] when all hold."""
    import franchise_export as fe
    bad = []
    clubs = doc.get("clubs") or {}
    if len(clubs) != N_CLUBS:
        bad.append(f"{len(clubs)} clubs, expected {N_CLUBS}")
        return bad
    sc = [c["score"] for c in clubs.values()]
    if abs(statistics.mean(sc) - 100.0) > 0.05 or abs(statistics.pstdev(sc) - 10.0) > 0.05:
        bad.append(f"score mean {statistics.mean(sc):.3f} sd {statistics.pstdev(sc):.3f}")
    for p in PILLARS:
        zs = [c["pillars"][p]["z"] for c in clubs.values()]
        if all(z is None for z in zs):
            if p != "operations" or doc["scheme"]["operations_live"]:
                bad.append(f"pillar {p} resolves no club")
            continue
        if any(z is None for z in zs):
            bad.append(f"pillar {p} resolves fewer than {N_CLUBS} clubs")
            continue
        if abs(statistics.mean(zs)) > 0.005 or abs(statistics.pstdev(zs) - 1.0) > 0.005:
            bad.append(f"pillar {p} z mean {statistics.mean(zs):.4f} sd {statistics.pstdev(zs):.4f}")
    order = sorted(clubs.items(), key=lambda kv: kv[1]["rank"])
    if [c["rank"] for _k, c in order] != list(range(1, N_CLUBS + 1)):
        bad.append("ranks are not 1 to 30")
    for (_a, x), (_b, y) in zip(order, order[1:]):
        if x["score"] < y["score"]:
            bad.append(f"rank not monotone in score at {_a} {x['score']} / {_b} {y['score']}")
    for code, c in clubs.items():
        if c["letter"] != fe.letter_for_rank(c["rank"]):
            bad.append(f"{code}: letter {c['letter']} against rank {c['rank']}")
    sch = doc["scheme"]
    for name, w in (("pillars", sch["pillars"]), ("dark", sch["dark"]), ("applied", sch["applied"])):
        if abs(sum(w.values()) - 1.0) > 1e-9:
            bad.append(f"scheme {name} weights sum to {sum(w.values())}")
    for k, w in sch["legs"].items():
        if abs(sum(w.values()) - 1.0) > 1e-9:
            bad.append(f"{k} leg weights sum to {sum(w.values())}")
    win = doc["window"]
    if len(win["seasons"]) != WINDOW_LEN:
        bad.append(f"the window holds {len(win['seasons'])} seasons")
    for name in ("weights", "operations_weights"):
        if abs(sum(win[name].values()) - 1.0) > 1e-3:
            bad.append(f"window {name} sum to {sum(win[name].values())}")
    for y, f in (doc.get("facts") or {}).items():
        if len(f["division_champions"]) != 6:
            bad.append(f"{y}: {len(f['division_champions'])} division champions")
        if f["complete"] and (f["champion"] is None or len(f["pennants"]) != 2):
            bad.append(f"{y}: a complete season without one champion and two pennants")
    if inp is not None:
        st = inp["standings"]
        for code, c in clubs.items():
            for row in c["seasons"]:
                r = st[code][row[0]]
                if (row[1], row[2], row[3]) != (r["w"], r["l"], r["rd"]):
                    bad.append(f"{code} {row[0]}: record {row[1:4]} against the standings cache")
    for path, k in _walk_keys(doc):
        kl = k.lower()
        if kl in FORBIDDEN_KEYS:
            bad.append(f"forbidden key {path}")
        if "mwpa" in kl:
            bad.append(f"management value key {path}")
        if _GRADE_KEY.search(kl):
            bad.append(f"grade-grouped key {path}")
    txt = json.dumps(doc, ensure_ascii=False)
    if chr(0x2014) in txt or chr(0x2013) in txt:
        bad.append("a banned dash reached the payload")
    for s in _strings([doc.get("copy"), doc.get("what_fscore_does_not_claim"),
                       doc.get("accountability")]):
        for w in FORECAST_WORDS:
            if re.search(r"\b" + re.escape(w) + r"\b", s, re.IGNORECASE):
                bad.append(f"forecast word {w!r} in copy")
    return bad


def assert_identities(doc: dict, inp: dict | None = None) -> None:
    bad = identity_failures(doc, inp)
    if bad:
        raise FscoreRefusal("identity: " + "; ".join(bad[:8]))


def build(today: date | None = None) -> dict:
    """The document, every identity asserted. Never writes."""
    today = today or date.today()
    seasons = window_seasons(today)
    inp = load_inputs(seasons)
    doc = compute(inp, seasons, today=today)
    assert_identities(doc, inp)
    return doc


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def out_path() -> Path:
    """data/fscore.json only once FSCORE_LIVE is True; the preview until then."""
    return LIVE_OUT if FSCORE_LIVE else PREVIEW_OUT


def write(doc: dict, out: Path | None = None) -> int:
    p = Path(out or out_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, p)
    return len(raw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="F-SCORE, the seven-season franchise score")
    ap.add_argument("--out", type=Path, default=None, help="write here instead of the flag's path")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else None
    try:
        doc = build(today)
    except FscoreRefusal as exc:
        print(f"REFUSED: {exc}; the previous {OUT_NAME} stands")
        return 2
    out = Path(args.out) if args.out else out_path()
    n = write(doc, out)
    where = "served" if (FSCORE_LIVE and not args.out) else "not served"
    print(f"wrote {out} ({n / 1e3:.1f} KB, {where}); window {doc['window']['seasons'][0]}-"
          f"{doc['window']['newest']}, in progress {doc['window']['in_progress']}, "
          f"OPERATIONS {'live' if doc['scheme']['operations_live'] else 'dark'}")
    order = sorted(doc["clubs"].items(), key=lambda kv: kv[1]["rank"])
    for code, c in order[:3] + order[-1:]:
        p = c["pillars"]
        print(f"  #{c['rank']} {code} {c['score']} ({c['letter']}); "
              + " ".join(f"{k} {p[k]['score']}" for k in PILLARS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
