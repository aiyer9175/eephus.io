# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The game-intensity stage-1 lab: does intensity move games, which team types and archetypes, what wins in October; read once on 2018-2025.

Registration: docs/diamond-betting.md, the section "Game intensity: stakes, matchup
quality and the postseason" (pre-registered 2026-10-08; owner ask 8 of 2026-09-30; plan
Part 8, P8.9, item IX-H3, task Q10_07). This file is stage 1 of that section and nothing
else. Built 2026-10-09 and tested on fixtures only: no real game has been featurized,
fitted, scored or twinned by it. The one run is a separate task (IX-LOOK, Q10_08).

Modes:
  python -u tools/intensity_lab.py --run [--tee PATH] [--workers N]
      THE RUN. Once. Refused before the later of 2026-11-02 and the day after the 2026
      World Series' last game; before each of the 5c-B, 5c-C, 5d, 5k and 7e-D looks is
      recorded in docs/diamond-betting.md or its kill date has passed (5e and 5i-B are
      NOT waited for: they share no game with stage 1); on a registered look day; without
      a step Z entry in part 9 of the fWAR label epoch gate; and as a second run, when
      data/game_intensity_eval.json exists or the section carries a "### Stage 1 result"
      heading. Features are built first (archived under .cache/betting/intensity_archive/
      with provenance "archive-reconstruct" per row); the artifact's first write comes
      before any family is scored; every family block is written before any is printed;
      the result heading is appended to the section last.
  python tools/intensity_lab.py --dry-run --out PATH
      The whole reporting path on the built-in synthetic fixture with nulls (an
      unannounced probable, a game with no Elo, an empty focus month, a postseason game
      with no feed, seasons with no prior-season archetype source). Refuses data/.
  python tools/intensity_lab.py --counts [--fixture] [--out PATH] [--workers N]
      Counts only: games, row-rule drops, stated nulls, focus-set sizes by season and
      month, postseason feed status. No statistic, no S value beside any game, no
      outcome read for any scored quantity. Allowed before the look (the section's
      disqualification paragraph: "counts-only gate-tool runs" are not a relation).
  python tools/intensity_lab.py --g-ref
      Recomputes G_REF from the registered synthetic league (30 equal clubs at 0-0 on
      the 52 / 64 / 46 schedule, 300,000 simulations at seed 20260930, no data) and
      prints it. Run once in this tool's commit; the value is frozen in
      intensity_core.G_REF and recorded in the section. Never computed at a look.

What is registered and is not a choice here: the families and members (IX-ML {IX-A,
IX-A2} m 2; IX-TOT {IX-B} m 1; IX-TYPE {rotation quality, bullpen quality, contact,
power} m 4; IX-ARCH {six archetypes} m 6; IX-E descriptive, intervals only); the split
for IX-A (fit 2018, 2019, 2021, 2022; graded 2023-2025); the focus set |ds| >= 0.05; the
B3 permuted-team twin (200 draws, numpy.random.default_rng(k) for k = 0 to 199, the 95th
percentile bar, strict); the quality re-entry controls; Holm within each family at
0.05; 5k's row rules and CR1 date clusters; the dq prior of 70 games; the type floor
of 20 club games. Choices the text left open are pinned in the section's dated
amendment of 2026-10-09 and in PINNED_CHOICES below.

What it never reads: a 2026 game (as a scored row or as history); bullpen USAGE (5l's
quantities) or team defense (5g's column) as a team type; any dark betting column, vintage
record, price, market capture or betting artifact; .cache/win_prob/ (the regular-season
feed cache the corpus walks). It is the only reader of .cache/win_prob_post/. Its stakes
quantities are named ds, dpo, dws, G and S, never by the dark builder's column names.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import intensity_core as ic  # noqa: E402

DATA = ROOT / "data"
ARTIFACT = DATA / "game_intensity_eval.json"
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
CACHE = ROOT / ".cache"
FINALS_DIR = CACHE / "betting" / "regular_finals"
CORPUS_DIR = CACHE / "pbp_corpus"
POST_FEED_DIR = CACHE / "win_prob_post"
ARCHIVE_DIR = CACHE / "betting" / "intensity_archive"
EXTRA_TOTALS_DIR = CACHE / "intensity_lab"

SECTION_TITLE = "Game intensity: stakes, matchup quality and the postseason"
REGISTRY_ROW = "game_intensity_effects"
STAGE1_HEADING_RE = re.compile(r"^### Stage 1 result\b", re.M)
PROVENANCE = "archive-reconstruct"
LAB_VERSION = 1

# ---------------------------------------------------------------------------
# G_REF: the record of this tool's one computation (the section's dated amendment)
# ---------------------------------------------------------------------------
#: Written by `--g-ref` on 2026-10-09 from the registered synthetic league and frozen
#: as intensity_core.G_REF; the test pins all three to the section's amendment.
G_REF_RECORD = {"value": 0.01158, "unrounded": 0.011575302175191062, "seed": ic.G_REF_SEED,
                "sims": ic.G_REF_SIMS, "recorded": "2026-10-09"}

# ---------------------------------------------------------------------------
# Registered constants (the section's own numbers; pinned by the tests)
# ---------------------------------------------------------------------------
SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
FIT_SEASONS = (2018, 2019, 2021, 2022)
GRADE_SEASONS = (2023, 2024, 2025)
POSTSEASONS_REGISTERED = SEASONS
POSTSEASONS_INT_B1 = tuple(range(2000, 2018))        # owner answer INT-B1 (b)
POSTSEASON_TYPES = ("F", "D", "L", "W")
FIRST_REFUSED_SEASON = 2026
EARLIEST_RUN = _dt.date(2026, 11, 2)
WS_SEASON = 2026

TWIN_DRAWS = 200
TWIN_PERCENTILE = 95.0
ALPHA = 0.05
T_ONE_SIDED = 1.645                                   # rule 4's vintage-leg bar
DQ_PRIOR_GAMES = 70                                   # RD/G x G/(G + 70), a literal
TYPE_MIN_GAMES = 20                                   # types null before 20 club games
TOP_DECILE = 0.90

#: The overlap list: the 2026 looks stage 1 waits for, each by its record or by its own
#: kill date (all 2026-10-31). (look, the heading that opens its text, the heading that
#: closes it, kill date). A record is a "Result" or "Closure" heading inside that text.
OVERLAP_LOOKS = (
    ("5c-B", r"^### 5c-B\.", r"^### 5c-C\.", "2026-10-31"),
    ("5c-C", r"^### 5c-C\.", r"^## ", "2026-10-31"),
    ("5d", r"^## 5d\.", r"^## ", "2026-10-31"),
    ("5k", r"^## 5k\.", r"^## ", "2026-10-31"),
    ("7e-D", r"^### 7e-D\.", r"^## ", "2026-10-31"),
)
#: Never waited for: those two score only 2026 vintage games and stage 1 reads none.
NOT_WAITED = ("5e", "5i-B")
RECORD_HEADING_RE = re.compile(r"^#{3,4} (?:Result|Closure)\b", re.M)

#: Registered look days of other gates (plan Part 8 8.B, Part 9, docs/*GATE*.md): the
#: run never takes one. The run task checks the gate documents again before it starts.
BLOCKED_DAYS = tuple(_dt.date.fromisoformat(d) for d in (
    "2026-10-21", "2026-10-23", "2026-10-28", "2026-11-06", "2026-11-13", "2026-11-20",
    "2026-11-24", "2026-11-25", "2026-12-01", "2026-12-03", "2026-12-08", "2026-12-10",
    "2027-01-12", "2027-10-20", "2027-11-09", "2027-11-16"))

#: The registered run's parameters. The run refuses any other value; the fixture
#: paths override the sample-size floors (a 30-date fixture season has no 250-PA hitter).
REGISTERED_PARAMS = {
    "n_sims": ic.SIMS, "seed": ic.SEED, "twin_draws": TWIN_DRAWS,
    "arch_min_pa": 250, "arch_min_bf": 250, "arch_shrink": 200, "park_regress": 0.5,
    "starter_min_starts": 3, "type_min_games": TYPE_MIN_GAMES, "reliever_min_bf": 100,
}

TYPE_MEMBERS = ("rotation_quality", "bullpen_quality", "contact", "power")
#: Excluded until their own looks are recorded (5l: 2027-07-01 at the earliest; 5g: 2027).
TYPE_EXCLUDED = {"bullpen_usage": "5l look not recorded", "team_defense": "5g look not recorded"}
ARCH_MEMBERS = ("hitter_power", "hitter_contact", "hitter_patience",
                "pitcher_power", "pitcher_command", "pitcher_groundball")

#: Choices the registered text leaves open, fixed here before any real row is read and
#: recorded in the section's dated amendment of 2026-10-09.
PINNED_CHOICES = (
    "Row rules (5k's) apply to every scored set: game_pk deduplicated, season checked, "
    "innings below 9 or missing dropped, every resumed game (a game_pk the schedule listed "
    "on two dates) dropped; each counted.",
    "Standings, Elo and the remaining schedule use every final: a final enters the "
    "knowledge of date D only when its last listed schedule date is before D, so a "
    "resumed game stays in the remaining schedule until it completed.",
    "Venue-season: the finals rows carry no venue, so the venue is the home club's park "
    "(a neutral-site or relocated game is attributed to its home club), counted.",
    "Stage-1 A uses the probables' season-to-date starter (K - BB) per batter faced "
    "before D among starters with 3 or more starts (SEM+ cannot be rebuilt for past "
    "seasons); the probable is the completed-game row's; null when unannounced or off "
    "the board, never zero.",
    "Twins permute per date, dates in ascending order, one rng.permutation per date: "
    "IX-A, IX-A2 and IX-B permute the per-game club slots (two a game) of the scored "
    "games on that date; IX-TYPE permutes each type's club values among the clubs "
    "playing that date; IX-ARCH permutes S among that date's games.",
    "IX-A's twin grades on its own focus set (|ds twin| >= 0.05); a twin with an empty "
    "focus set is dropped from the percentile and counted.",
    "Statistics: IX-A's criterion 1 and Holm p use the per-game paired t (the "
    "_paired_delta form, one-sided normal); the two-sided members use the CR1 date-"
    "clustered t (game-clustered for IX-ARCH) with G - 1 degrees of freedom; a two-sided "
    "member resolves only with a positive point estimate of improvement where the "
    "statistic is an improvement.",
    "Bars: IX-A, IX-A2 and IX-TYPE beat their twins on the graded paired Brier "
    "improvement; IX-B and IX-ARCH on |t|. Controls are compared on the point estimate "
    "on the same rows: improvement for the logistic members, effect per SD for IX-B, "
    "|DiD| for IX-ARCH.",
    "Controls: IX-A dq; IX-A2 Q - Q_bar; IX-TYPE S x (dq z-gap); IX-B A then Q; IX-ARCH "
    "the top decile of Q.",
    "IX-ARCH: wOBA denominator events (IBB, sacrifice bunts and catcher interference "
    "out); qualified 250 PA or 250 batters faced in the prior season; prior rates shrunk "
    "with 200 league-average PA; park factor the home club's prior home over road wOBA "
    "regressed half to 1; platoon by same or opposite hand; residuals centered by season; "
    "top decile of S within each season.",
    "IX-E: the postseason game list and clubs from postseason.py's cache, scores from the "
    "feed's last play; the price the end-of-regular-season Elo where that season's "
    "regular finals are on disk (null otherwise, counted); the venue run level the home "
    "club's regular-season home-game total over its all-games total, times the two clubs' "
    "mean total per game; intervals normal (Wilson for a raw rate), slopes CR1 by series.",
)

EVT_K = ("strikeout", "strikeout_double_play", "strikeout_triple_play")
EVT_BB = ("walk", "intent_walk")
WOBA_VALUE_KEYS = {"walk": "ubb", "hit_by_pitch": "hbp", "single": "1b", "double": "2b",
                   "triple": "3b", "home_run": "hr"}
NOT_WOBA_DEN = ("intent_walk", "sac_bunt", "sac_bunt_double_play", "catcher_interf")
NOT_AB = ("walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_fly_double_play",
          "sac_bunt", "sac_bunt_double_play", "catcher_interf")
TRAJ_BIP = ("ground_ball", "line_drive", "fly_ball", "popup")
NON_PA_PREFIX = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball",
                 "balk", "other_advance", "game_advisory", "runner_double_play",
                 "other_out", "defensive_indiff", "forced_balk")
PLAY_COLS = ("game_pk", "half", "at_bat_index", "batter_id", "pitcher_id", "bat_side",
             "pitch_hand", "event_type", "trajectory")

#: The registered synthetic league's division map, copied from proj_current (the
#: lane's base commit 64bf1bb3, `_DIVISIONS`), member order kept: the synthetic
#: schedule's cross-division extra games pair members by position. 2018-2025 used
#: the same map.
DIVISIONS = {
    "AL_E": ("BAL", "BOS", "NYY", "TBR", "TOR"),
    "AL_C": ("CHW", "CLE", "DET", "KCR", "MIN"),
    "AL_W": ("ATH", "HOU", "LAA", "SEA", "TEX"),
    "NL_E": ("ATL", "MIA", "NYM", "PHI", "WSN"),
    "NL_C": ("CHC", "CIN", "MIL", "PIT", "STL"),
    "NL_W": ("ARI", "COL", "LAD", "SDP", "SFG"),
}
ORG_LEAGUE = {o: d.split("_")[0] for d, m in DIVISIONS.items() for o in m}
ORG_DIV = {o: d for d, m in DIVISIONS.items() for o in m}
ORGS = tuple(o for d in sorted(DIVISIONS) for o in DIVISIONS[d])


class LabRefused(RuntimeError):
    """A guard fired: nothing further is read or written."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _r(x, nd=6):
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _is_pa(et) -> bool:
    """mlbstats_games.is_pa_event, copied: an eventType that closes a plate appearance."""
    et = str(et or "")
    if not et or et == "error":
        return False
    return not et.startswith(NON_PA_PREFIX)


def game_kind(h: str, a: str) -> str:
    if ORG_DIV[h] == ORG_DIV[a]:
        return "division"
    if ORG_LEAGUE[h] == ORG_LEAGUE[a]:
        return "league"
    return "interleague"


def _refuse_season(season) -> int:
    s = int(season)
    if s >= FIRST_REFUSED_SEASON:
        raise LabRefused(f"refused: season {s}; stage 1 never reads a 2026 game, neither as "
                         "a scored row nor as history")
    if s == 2020:
        raise LabRefused("refused: 2020 is excluded from stage 1 throughout")
    return s


# ---------------------------------------------------------------------------
# G_REF from the registered synthetic league (no data)
# ---------------------------------------------------------------------------
def synthetic_schedule() -> list:
    """The registered synthetic 162-game schedule (the lane's `schedule_162`): 13 games
    against each division rival (52), 6 against each other same-league club plus 4
    cross-division extras (64), 3 against each interleague club plus one natural rival
    (46); home and away alternate within each pair."""
    n: dict = {}

    def add(a, b, k):
        key = tuple(sorted((a, b)))
        n[key] = n.get(key, 0) + k

    for a in ORGS:
        for b in ORGS:
            if a >= b:
                continue
            kind = game_kind(a, b)
            add(a, b, 13 if kind == "division" else 6 if kind == "league" else 3)
    for lg in ("AL", "NL"):
        dnames = sorted(d for d in DIVISIONS if d.startswith(lg))
        for i in range(3):
            for j in range(i + 1, 3):
                X, Y = DIVISIONS[dnames[i]], DIVISIONS[dnames[j]]
                for k in range(5):
                    add(X[k], Y[k], 1)
                    add(X[k], Y[(k + 1) % 5], 1)
    al = [o for o in ORGS if ORG_LEAGUE[o] == "AL"]
    nl = [o for o in ORGS if ORG_LEAGUE[o] == "NL"]
    for a, b in zip(al, nl):
        add(a, b, 1)
    pairs = []
    for (a, b), k in sorted(n.items()):
        for i in range(k):
            pairs.append((a, b) if i % 2 == 0 else (b, a))
    return pairs


def opening_day_games(pairs: list) -> dict:
    """{kind: [index into pairs]}: one greedy matching of each kind, in schedule order
    (an Opening Day slate of that kind: no club twice)."""
    out = {}
    for kind in ("division", "league", "interleague"):
        used, idx = set(), []
        for k, (h, a) in enumerate(pairs):
            if game_kind(h, a) == kind and h not in used and a not in used:
                idx.append(k)
                used.update((h, a))
        out[kind] = idx
    return out


def compute_g_ref(n_sims: int = ic.G_REF_SIMS, seed: int = ic.G_REF_SEED) -> dict:
    """G_REF, the mean G of an Opening Day game between average clubs: every listed
    game forced each way under common random numbers over the whole 2,430-game
    schedule (intensity_core.regular_season_stakes, the construction's own simulator,
    six-club format, home edge 0.0345), the kind means weighted 52 / 64 / 46 of 162."""
    pairs = synthetic_schedule()
    want = dict(ic.G_REF_SCHEDULE)
    per = {o: {"division": 0, "league": 0, "interleague": 0} for o in ORGS}
    for h, a in pairs:
        per[h][game_kind(h, a)] += 1
        per[a][game_kind(h, a)] += 1
    if not all(v == want for v in per.values()) or len(ORGS) != ic.G_REF_CLUBS:
        raise LabRefused("refused: the synthetic schedule is not the registered league")
    teams = {o: {"wins": 0, "p": 0.5, "league": ORG_LEAGUE[o], "div": ORG_DIV[o]}
             for o in ORGS}
    od = opening_day_games(pairs)
    listed = [k for kind in ("division", "league", "interleague") for k in od[kind]]
    res = ic.regular_season_stakes(teams, pairs, listed, fmt="six", n_sims=n_sims, seed=seed,
                                   home_edge=ic.HOME_EDGE)
    by_index = {g["index"]: g for g in res["games"]}
    kinds = {}
    for kind in ("division", "league", "interleague"):
        gs = [by_index[k]["G"] for k in od[kind]]
        ses = [by_index[k]["G_se"] for k in od[kind]]
        kinds[kind] = {"games": len(gs), "G_mean": sum(gs) / len(gs),
                       "G_se_mean": sum(ses) / len(ses)}
    mix = {k: want[k] / 162.0 for k in ("division", "league", "interleague")}
    value = sum(mix[k] * kinds[k]["G_mean"] for k in mix)
    return {"g_ref_unrounded": value, "g_ref": round(value, 5), "by_kind": kinds,
            "mix": mix, "n_sims": int(n_sims), "seed": int(seed), "home_edge": ic.HOME_EDGE,
            "fmt": "six", "schedule_games": len(pairs)}


# ---------------------------------------------------------------------------
# Guards: the clock, the overlap list, the one run, the section
# ---------------------------------------------------------------------------
def step_z_entry(text: str | None = None) -> str | None:
    """The dated step Z heading in part 9 of the fWAR label epoch gate, or None."""
    if text is None:
        try:
            text = EPOCH_DOC.read_text(encoding="utf-8")
        except OSError:
            return None
    if "## 9. Results" not in text:
        return None
    part9 = text.split("## 9. Results", 1)[1]
    m = re.search(r"^###\s+(\d{4}-\d{2}-\d{2}):[^\n]*\bstep Z\b", part9, flags=re.M)
    return m.group(1) if m else None


def _doc(doc_text: str | None) -> str:
    if doc_text is None:
        doc_text = GATE_DOC.read_text(encoding="utf-8")
    return doc_text.replace("\r\n", "\n")


def section_text(doc_text: str | None = None) -> str:
    """The section's text, from its level-2 heading to the next level-2 heading."""
    text = _doc(doc_text)
    hits = list(re.finditer(r"^## [^\n]*" + re.escape(SECTION_TITLE) + r"[^\n]*$", text,
                            flags=re.M))
    if len(hits) != 1:
        raise LabRefused(f"refused: expected one section titled {SECTION_TITLE!r} in "
                         f"docs/diamond-betting.md, found {len(hits)}")
    start = hits[0].start()
    nxt = re.search(r"^## ", text[hits[0].end():], flags=re.M)
    return text[start:] if nxt is None else text[start:hits[0].end() + nxt.start()]


def overlap_status(today: _dt.date, doc_text: str | None = None,
                   looks=OVERLAP_LOOKS) -> dict:
    """{look: {"recorded", "kill_date", "satisfied"}}: a look is satisfied by a Result or
    Closure heading inside its own text, or by its kill date having passed."""
    text = _doc(doc_text)
    out = {}
    for name, open_re, close_re, kill in looks:
        m = re.search(open_re, text, flags=re.M)
        recorded = False
        if m is not None:
            rest = text[m.end():]
            e = re.search(close_re, rest, flags=re.M)
            span = rest if e is None else rest[:e.start()]
            recorded = RECORD_HEADING_RE.search(span) is not None
        kill_d = _dt.date.fromisoformat(kill)
        out[name] = {"recorded": recorded, "kill_date": kill,
                     "satisfied": bool(recorded or today > kill_d)}
    return out


def world_series_end(season: int = WS_SEASON, cache_dir: Path | None = None) -> str | None:
    """The officialDate of the last final World Series game of `season`, from
    postseason.py's cache (the full body carries the dates); None while the season has
    no champion on disk."""
    import postseason
    try:
        parsed = postseason.load(season, cache_dir=cache_dir)
    except Exception:                       # noqa: BLE001 - an unreadable file is "not yet"
        return None
    if not parsed or not parsed.get("complete"):
        return None
    try:
        doc = json.loads(postseason.cache_path(season, cache_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dates = []
    for s in ((doc or {}).get("body") or {}).get("series") or []:
        for g in s.get("games") or []:
            if (g.get("gameType") == "W"
                    and ((g.get("status") or {}).get("codedGameState") or "") in ("F", "O")
                    and g.get("officialDate")):
                dates.append(str(g["officialDate"]))
    return max(dates) if dates else None


def check_clock(today: _dt.date | None = None, epoch_text: str | None = None,
                doc_text: str | None = None, ws_end: str | None = "lookup") -> dict:
    """Every date refusal of the run, in order."""
    today = today or _dt.date.today()
    z = step_z_entry(epoch_text)
    if z is None:
        raise LabRefused("refused: part 9 of FWAR_LABEL_EPOCH_GATE.md records no step Z "
                         "entry; nothing runs between the epoch's step A and step Z")
    if today in BLOCKED_DAYS:
        raise LabRefused(f"refused: {today} is another gate's registered look day")
    if today < EARLIEST_RUN:
        raise LabRefused(f"refused: today {today} is before 2026-11-02, the registered "
                         "earliest stage-1 date")
    if ws_end == "lookup":
        ws_end = world_series_end()
    if ws_end is None:
        raise LabRefused("refused: the 2026 World Series has no recorded last game on disk; "
                         "stage 1 waits for the day after it")
    first_ok = _dt.date.fromisoformat(ws_end) + _dt.timedelta(days=1)
    if today < first_ok:
        raise LabRefused(f"refused: today {today} is not after the 2026 World Series' last "
                         f"game ({ws_end})")
    ov = overlap_status(today, doc_text)
    waiting = [k for k, v in ov.items() if not v["satisfied"]]
    if waiting:
        raise LabRefused("refused: stage 1 waits for the overlapping looks "
                         + ", ".join(waiting) + " (record or kill date)")
    return {"today": today.isoformat(), "earliest_run": EARLIEST_RUN.isoformat(),
            "world_series_last_game": ws_end, "step_z_entry": z, "overlap": ov,
            "not_waited": list(NOT_WAITED)}


def check_one_run(artifact_path: Path = ARTIFACT, doc_text: str | None = None) -> None:
    """The one-run guard reads both the artifact and the section's result block."""
    p = Path(artifact_path)
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise LabRefused(f"refused: {p.name} exists and does not parse; stage 1 runs "
                             "once and a broken artifact is a question for the owner")
        if isinstance(doc, dict) and isinstance(doc.get("stage1"), dict):
            raise LabRefused(f"refused: {p.name} already holds a stage-1 block "
                             f"(status {doc['stage1'].get('status')!r}); stage 1 runs once")
        raise LabRefused(f"refused: {p.name} exists; stage 1 runs once")
    if STAGE1_HEADING_RE.search(section_text(doc_text)):
        raise LabRefused("refused: the section already carries a '### Stage 1 result' "
                         "heading; stage 1 runs once")


def check_out_path(out: Path) -> Path:
    """A dry run or a counts run never writes under data/."""
    out = Path(out).resolve()
    try:
        out.relative_to(DATA.resolve())
    except ValueError:
        return out
    raise LabRefused(f"refused: this mode writes nothing under data/ ({out})")


def check_params(params: dict) -> None:
    """The run takes the registered parameters only."""
    bad = {k: v for k, v in params.items() if REGISTERED_PARAMS.get(k) != v}
    if bad or set(params) != set(REGISTERED_PARAMS):
        raise LabRefused(f"refused: the run takes the registered parameters only ({bad})")


# ---------------------------------------------------------------------------
# Sources: the cache (the run, counts) and a fixture (tests, the dry run)
# ---------------------------------------------------------------------------
def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class CacheSource:
    """The regular-season finals (.cache/betting/regular_finals, written by
    tools/intensity_fetch.py), the play corpus (.cache/pbp_corpus, named columns only),
    postseason.py's cached schedule bodies and the postseason feeds
    (.cache/win_prob_post, this lab its only reader)."""

    kind = "cache"

    def __init__(self, finals_dir=FINALS_DIR, corpus_dir=CORPUS_DIR,
                 feed_dir=POST_FEED_DIR, extra_dir=EXTRA_TOTALS_DIR, ps_cache_dir=None):
        self.finals_dir = Path(finals_dir)
        self.corpus_dir = Path(corpus_dir)
        self.feed_dir = Path(feed_dir)
        self.extra_dir = Path(extra_dir)
        self.ps_cache_dir = ps_cache_dir
        self._ids = None

    def finals(self, season: int):
        doc = _read_json(self.finals_dir / f"{int(season)}.json")
        if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
            return None
        return {"rows": doc["rows"], "multi": doc.get("listed_more_than_once") or {},
                "fetched_at": doc.get("fetched_at")}

    def plays(self, season: int):
        p = self.corpus_dir / "plays" / str(int(season)) / f"plays-{int(season)}.parquet"
        if not p.exists():
            return None
        import pandas as pd
        return pd.read_parquet(p, columns=list(PLAY_COLS))

    def weights(self, season: int):
        import league_constants
        w = league_constants.solve_weights(int(season))
        return dict((w or {}).get("woba_weights") or {}) or None

    def extra_totals(self, season: int):
        """Season totals for a season outside the corpus (2017, 2020), when a fetch has
        put them under .cache/intensity_lab/; None otherwise."""
        return _read_json(self.extra_dir / f"season_totals_{int(season)}.json")

    def postseason_games(self, season: int):
        import postseason
        body = None
        for path in (postseason.cache_path(int(season), self.ps_cache_dir),
                     postseason.tracked_path(int(season))):
            doc = _read_json(path)
            body = doc.get("body") if isinstance(doc, dict) else None
            if isinstance(body, dict):
                break
        if not isinstance(body, dict):
            return None
        if self._ids is None:
            self._ids = postseason._clubs_by_id()
        out, seen = [], set()
        for s in body.get("series") or []:
            for g in s.get("games") or []:
                gt = g.get("gameType")
                if gt not in POSTSEASON_TYPES:
                    continue
                if ((g.get("status") or {}).get("codedGameState") or "") not in ("F", "O"):
                    continue
                pk = g.get("gamePk")
                if pk is None or int(pk) in seen:
                    continue
                seen.add(int(pk))
                side = {}
                for k in ("home", "away"):
                    tid = (((g.get("teams") or {}).get(k) or {}).get("team") or {}).get("id")
                    side[k] = self._ids.get(int(tid)) if tid is not None else None
                out.append({"game_pk": int(pk), "game_type": gt,
                            "date": g.get("officialDate"), "home": side["home"],
                            "away": side["away"]})
        return out

    def postseason_feed(self, game_pk: int):
        doc = _read_json(self.feed_dir / f"{int(game_pk)}.json")
        if not isinstance(doc, dict) or not isinstance(doc.get("plays"), list):
            return None
        return doc["plays"]

    def describe(self) -> dict:
        man = _read_json(self.corpus_dir / "manifest.json") or {}
        return {"source": "cache", "finals_dir": ".cache/betting/regular_finals",
                "corpus_built_at": man.get("built_at"),
                "postseason_feeds": ".cache/win_prob_post",
                "venue": "the home club's park (the finals rows carry no venue)"}


class FixtureSource:
    """In-memory tables in the cache's own shapes, for tests and the dry run."""

    kind = "fixture"

    def __init__(self, finals: dict, plays: dict, weights: dict, post_games: dict,
                 feeds: dict, extra: dict | None = None):
        self._finals, self._plays, self._weights = finals, plays, weights
        self._post, self._feeds, self._extra = post_games, feeds, extra or {}
        self.requested = []

    def finals(self, season):
        self.requested.append(("finals", int(season)))
        return self._finals.get(int(season))

    def plays(self, season):
        self.requested.append(("plays", int(season)))
        return self._plays.get(int(season))

    def weights(self, season):
        return self._weights.get(int(season))

    def extra_totals(self, season):
        return self._extra.get(int(season))

    def postseason_games(self, season):
        return self._post.get(int(season))

    def postseason_feed(self, game_pk):
        return self._feeds.get(int(game_pk))

    def describe(self):
        return {"source": "fixture"}


# ---------------------------------------------------------------------------
# One season's finals: validation, knowledge dates, row rules
# ---------------------------------------------------------------------------
def season_games(finals: dict | None, season: int) -> tuple[list, dict]:
    """([game], counts). A game: pk, date, home, away, runs, innings, probables, venue,
    known_on (the last schedule date it was listed on) and resumed. Dropped and counted:
    another season, a duplicate game_pk, no date, no score, a club outside the
    thirty-club field (no Elo can price it)."""
    s = _refuse_season(season)
    c = Counter()
    if not finals:
        return [], {"finals_missing": 1}
    multi = {int(k): [str(d) for d in (v or []) if d] for k, v in
             (finals.get("multi") or {}).items()}
    out, seen = [], set()
    for r in finals.get("rows") or []:
        c["rows"] += 1
        if str(r.get("season")) != str(s):
            c["drop_other_season"] += 1
            continue
        try:
            pk = int(r.get("game_pk"))
        except (TypeError, ValueError):
            c["drop_no_game_pk"] += 1
            continue
        if pk in seen:
            c["drop_duplicate_game_pk"] += 1
            continue
        seen.add(pk)
        d = str(r.get("date") or "")[:10]
        if not d:
            c["drop_no_date"] += 1
            continue
        if d >= f"{FIRST_REFUSED_SEASON}-01-01":
            raise LabRefused(f"refused: game {pk} is dated {d}; stage 1 never reads 2026")
        h, a = r.get("home_org"), r.get("away_org")
        if h not in ORG_DIV or a not in ORG_DIV or h == a:
            c["null_no_elo_outside_field"] += 1
            continue
        if r.get("home_runs") is None or r.get("away_runs") is None:
            c["drop_no_score"] += 1
            continue
        listed = sorted(set(multi.get(pk, []) + [d]))
        out.append({"pk": pk, "season": s, "date": d, "home": h, "away": a,
                    "hr": int(r["home_runs"]), "ar": int(r["away_runs"]),
                    "innings": r.get("innings"), "home_sp": r.get("home_sp"),
                    "away_sp": r.get("away_sp"), "venue": r.get("venue") or None,
                    "known_on": listed[-1], "resumed": len(listed) > 1})
    out.sort(key=lambda g: (g["date"], g["pk"]))
    c["games"] = len(out)
    c["resumed"] = sum(1 for g in out if g["resumed"])
    return out, dict(c)


def row_rule(g: dict) -> str | None:
    """5k's row rules for a scored row: the reason a game leaves, or None."""
    if g["resumed"]:
        return "drop_resumed"
    try:
        inn = int(g["innings"])
    except (TypeError, ValueError):
        return "drop_no_innings"
    if inn < 9:
        return "drop_innings_below_9"
    return None


# ---------------------------------------------------------------------------
# Per-game aggregates from the play corpus (types, the starter board, IX-ARCH)
# ---------------------------------------------------------------------------
def play_aggregates(plays, games: list) -> dict:
    """{pk: {"top": half, "bottom": half}} with, per half: the starter (first pitcher),
    the starter's BF, K and BB, the relievers' BF, K and BB, and the batting side's PA,
    K and HR. Plate appearances only; a game not in `games` is ignored."""
    if plays is None or len(plays) == 0:
        return {}
    keep = {g["pk"] for g in games}
    p = plays.loc[plays["game_pk"].isin(list(keep)),
                  ["game_pk", "half", "at_bat_index", "pitcher_id", "event_type"]].copy()
    p = p[p["half"].isin(("top", "bottom"))]
    p = p.sort_values(["game_pk", "half", "at_bat_index"], kind="mergesort")
    first = p.dropna(subset=["pitcher_id"]).drop_duplicates(["game_pk", "half"])
    starters = {(int(r.game_pk), r.half): int(r.pitcher_id)
                for r in first.itertuples(index=False)}
    p = p[p["event_type"].map(_is_pa)]
    out: dict = {}
    for r in p.itertuples(index=False):
        key = (int(r.game_pk), r.half)
        if key not in starters:
            continue
        h = out.setdefault(int(r.game_pk), {}).setdefault(r.half, {
            "starter": starters[key], "sp_bf": 0, "sp_k": 0, "sp_bb": 0,
            "rp_bf": 0, "rp_k": 0, "rp_bb": 0, "pa": 0, "k": 0, "hr": 0})
        et = r.event_type
        is_sp = (r.pitcher_id == r.pitcher_id) and int(r.pitcher_id) == h["starter"]
        role = "sp" if is_sp else "rp"
        h[f"{role}_bf"] += 1
        h["pa"] += 1
        if et in EVT_K:
            h[f"{role}_k"] += 1
            h["k"] += 1
        elif et in EVT_BB:
            h[f"{role}_bb"] += 1
        if et == "home_run":
            h["hr"] += 1
    return out


# ---------------------------------------------------------------------------
# Features: one walk through each season, strictly before each date
# ---------------------------------------------------------------------------
def _stakes_task(args):
    teams, pairs, listed, fmt, n_sims, seed = args
    return ic.regular_season_stakes(teams, pairs, listed, fmt=fmt, n_sims=n_sims, seed=seed,
                                    home_edge=ic.HOME_EDGE)


def _club_types(acc: dict, min_games: int) -> dict:
    """{type: value or None} from a club's season-to-date sums."""
    if acc.get("games", 0) < min_games:
        return {k: None for k in TYPE_MEMBERS}

    def rate(num, den):
        return (num / den) if den else None

    sp = rate(acc["sp_k"] - acc["sp_bb"], acc["sp_bf"])
    rp = rate(acc["rp_k"] - acc["rp_bb"], acc["rp_bf"])
    kp = rate(acc["k"], acc["pa"])
    hr = rate(acc["hr"], acc["pa"])
    return {"rotation_quality": sp, "bullpen_quality": rp,
            "contact": None if kp is None else -kp, "power": hr}


def season_features(games: list, plays, season: int, params: dict, *, g_ref: float,
                    workers: int = 1, log=None) -> tuple[list, dict, dict]:
    """(rows, club values by date, counts). One row per game in `games`: the Elo price
    and every intensity input as of the start of its date. Reads results only as
    standings, Elo and season-to-date rates of finals known before the date."""
    s = _refuse_season(season)
    fmt = ic.format_for_season(s)
    agg = play_aggregates(plays, games)
    c = Counter()
    by_known = sorted(games, key=lambda g: (g["known_on"], g["date"], g["pk"]))
    dates = sorted({g["date"] for g in games})
    ratings = {o: ic.ELO_BASE for o in ORGS}
    wins, rs, ra, gp = Counter(), Counter(), Counter(), Counter()
    club_acc = {o: Counter() for o in ORGS}
    sp_acc: dict = defaultdict(Counter)
    ptr = 0
    tasks, meta = [], []
    club_by_date: dict = {}

    def apply(g):
        h, a = g["home"], g["away"]
        p = ic.elo_win_prob(ratings[h], ratings[a], ic.ELO_HOME_POINTS)
        y = 1.0 if g["hr"] > g["ar"] else 0.0
        delta = ic.ELO_K * (y - p)
        ratings[h] += delta
        ratings[a] -= delta
        wins[h if y else a] += 1
        rs[h] += g["hr"]
        ra[h] += g["ar"]
        rs[a] += g["ar"]
        ra[a] += g["hr"]
        gp[h] += 1
        gp[a] += 1
        ga = agg.get(g["pk"])
        if ga:
            for half, fld, bat in (("top", h, a), ("bottom", a, h)):
                x = ga.get(half)
                if not x:
                    continue
                fa, ba = club_acc[fld], club_acc[bat]
                for k in ("sp_bf", "sp_k", "sp_bb", "rp_bf", "rp_k", "rp_bb"):
                    fa[k] += x[k]
                for k in ("pa", "k", "hr"):
                    ba[k] += x[k]
                st = sp_acc[x["starter"]]
                st["starts"] += 1
                st["bf"] += x["sp_bf"]
                st["kbb"] += x["sp_k"] - x["sp_bb"]
            for club in (h, a):
                if any(ga.get(hf) for hf in ("top", "bottom")):
                    club_acc[club]["games"] += 1

    for D in dates:
        while ptr < len(by_known) and by_known[ptr]["known_on"] < D:
            apply(by_known[ptr])
            ptr += 1
        remaining = sorted(by_known[ptr:], key=lambda g: (g["date"], g["pk"]))
        listed = [i for i, g in enumerate(remaining) if g["date"] == D]
        teams = {o: {"wins": wins[o], "p": ic.elo_talent(ratings[o]),
                     "league": ORG_LEAGUE[o], "div": ORG_DIV[o]} for o in ORGS}
        board = {pid: v["kbb"] / v["bf"] for pid, v in sp_acc.items()
                 if v["starts"] >= params["starter_min_starts"] and v["bf"] > 0}
        q = {o: (rs[o] - ra[o]) / (gp[o] + DQ_PRIOR_GAMES) for o in ORGS}
        playing = sorted({x for i in listed for x in (remaining[i]["home"],
                                                      remaining[i]["away"])})
        club_by_date[D] = {o: {"q": q[o], **_club_types(club_acc[o], params["type_min_games"])}
                           for o in playing}
        pre = []
        for i in listed:
            g = remaining[i]
            h, a = g["home"], g["away"]
            pre.append({
                "pk": g["pk"], "season": s, "date": D, "month": int(D[5:7]),
                "home": h, "away": a, "kind": game_kind(h, a),
                "div": ic.division_flag(ORG_DIV[h], ORG_DIV[a]),
                "p_base": ic.elo_win_prob(ratings[h], ratings[a], ic.ELO_HOME_POINTS),
                "q_h": q[h], "q_a": q[a],
                "A": ic.starters_score(_int(g["home_sp"]), _int(g["away_sp"]), board),
                "A_null": ("unannounced" if g["home_sp"] is None or g["away_sp"] is None
                           else "off_board" if ic.starters_score(
                               _int(g["home_sp"]), _int(g["away_sp"]), board) is None
                           else None),
                "venue": g["venue"] or h, "venue_from_home": g["venue"] is None,
                "resumed": g["resumed"], "innings": g["innings"],
                "provenance": PROVENANCE,
            })
        tasks.append((teams, [(g["home"], g["away"]) for g in remaining], listed, fmt,
                      int(params["n_sims"]), int(params["seed"])))
        meta.append(pre)

    if workers and workers > 1 and len(tasks) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=int(workers)) as ex:
            results = list(ex.map(_stakes_task, tasks, chunksize=1))
    else:
        results = [_stakes_task(t) for t in tasks]

    rows = []
    for pre, res in zip(meta, results):
        proj = res["proj_wins"]
        for row, gs in zip(pre, res["games"]):
            assert (gs["home"], gs["away"]) == (row["home"], row["away"])
            row.update({"dpo_h": gs["dpo_h"], "dpo_a": gs["dpo_a"], "dws_h": gs["dws_h"],
                        "dws_a": gs["dws_a"], "G": gs["G"], "G_se": gs["G_se"],
                        "S": ic.stakes_score(gs["G"], g_ref),
                        "Q": ic.matchup_quality(proj, row["home"], row["away"])})
            row["ds"] = row["dpo_h"] - row["dpo_a"]
            rows.append(row)
    c["rows"] = len(rows)
    c["A_null_unannounced"] = sum(1 for r in rows if r["A_null"] == "unannounced")
    c["A_null_off_board"] = sum(1 for r in rows if r["A_null"] == "off_board")
    c["venue_from_home_club"] = sum(1 for r in rows if r["venue_from_home"])
    c["games_with_plays"] = sum(1 for g in games if g["pk"] in agg)
    if log:
        log(f"features {s}: {len(rows)} games over {len(dates)} dates")
    return rows, club_by_date, dict(c)


def _int(x):
    try:
        return None if x is None else int(x)
    except (TypeError, ValueError):
        return None


def construction_hash(params: dict, g_ref: float, extra: str = "") -> str:
    blob = json.dumps({"construction": ic.CONSTRUCTION, "lab": LAB_VERSION, "g_ref": g_ref,
                       "params": {k: params[k] for k in sorted(params)},
                       "elo": [ic.ELO_BASE, ic.ELO_K, ic.ELO_HOME_POINTS],
                       "home_edge": ic.HOME_EDGE, "extra": extra}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_features(source, params: dict, *, seasons=SEASONS, g_ref: float | None = None,
                   workers: int = 1, archive_dir: Path | None = None, log=None) -> dict:
    """{season: {"games", "rows", "clubs", "counts"}} for every stage-1 season. With an
    archive directory, a season's rows are kept there (features only, no outcome) and
    reused when its construction hash matches."""
    g_ref = ic.G_REF if g_ref is None else g_ref
    if g_ref is None:
        raise LabRefused("refused: G_REF is not frozen in intensity_core")
    out = {}
    for s in seasons:
        s = _refuse_season(s)
        fin = source.finals(s)
        games, gc = season_games(fin, s)
        h = construction_hash(params, g_ref, str((fin or {}).get("fetched_at")))
        arch = Path(archive_dir) / f"stage1_{s}.json" if archive_dir else None
        doc = _read_json(arch) if arch else None
        if isinstance(doc, dict) and doc.get("hash") == h:
            rows, clubs, fc = doc["rows"], doc["clubs"], doc["counts"]
        else:
            rows, clubs, fc = season_features(games, source.plays(s), s, params, g_ref=g_ref,
                                              workers=workers, log=log)
            if arch:
                from tools.intensity_fetch import check_target
                arch.parent.mkdir(parents=True, exist_ok=True)
                p = check_target(arch)
                tmp = p.with_name(p.name + ".tmp")
                tmp.write_text(json.dumps({"hash": h, "season": s, "provenance": PROVENANCE,
                                           "built_at": _now(), "rows": rows,
                                           "clubs": clubs, "counts": fc}), encoding="utf-8")
                tmp.replace(p)
        out[s] = {"games": games, "rows": rows, "clubs": clubs,
                  "counts": {**gc, **{f"features_{k}": v for k, v in fc.items()}}}
    return out


def outcomes_of(feats: dict) -> dict:
    """{pk: (home win, total runs)}, joined to features only when a family is scored."""
    out = {}
    for s, f in feats.items():
        for g in f["games"]:
            out[g["pk"]] = (1.0 if g["hr"] > g["ar"] else 0.0, float(g["hr"] + g["ar"]))
    return out


def scored_rows(feats: dict, seasons) -> tuple[list, dict]:
    """The rows of `seasons` that pass 5k's row rules, and the drop counts."""
    rows, c = [], Counter()
    for s in seasons:
        for r in (feats.get(s) or {}).get("rows") or []:
            why = row_rule(r)
            if why:
                c[why] += 1
                continue
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["pk"]))
    return rows, dict(c)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def fit_offset_logistic(offset, X, y, max_iter: int = 100, tol: float = 1e-12) -> np.ndarray:
    """Maximum likelihood for logit p = offset + X b, no intercept (Newton). A column
    that is zero on every row gets 0."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    off = np.asarray(offset, dtype=float)
    y = np.asarray(y, dtype=float)
    k = X.shape[1]
    b = np.zeros(k)
    live = np.any(X != 0, axis=0)
    if X.shape[0] == 0 or not live.any():
        return b
    Xl = X[:, live]
    bl = np.zeros(Xl.shape[1])
    for _ in range(max_iter):
        p = _sigmoid(off + Xl @ bl)
        g = Xl.T @ (y - p)
        H = (Xl * (p * (1 - p))[:, None]).T @ Xl
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, g, rcond=None)[0]
        bl = bl + step
        if np.max(np.abs(step)) < tol:
            break
    b[live] = bl
    return b


def brier(p, y):
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def log_loss(p, y):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_delta(incumbent, challenger) -> dict:
    """betting_model._paired_delta's form, copied: incumbent minus challenger per row
    (positive means the challenger is better), population sd, se = sd / sqrt(n), the
    one-sided 95% lower bound at 1.645. `mean` and `t_raw` are unrounded, for decisions."""
    inc = np.asarray(incumbent, dtype=float)
    chal = np.asarray(challenger, dtype=float)
    n = int(inc.size)
    if n < 2:
        return {"n": n, "delta": None, "sd": None, "t": None, "lb95": None, "mean": None,
                "t_raw": None}
    d = inc - chal
    mu = float(d.mean())
    sd = float(math.sqrt(float(((d - mu) ** 2).sum()) / n))
    se = sd / math.sqrt(n) if sd else 0.0
    return {"n": n, "delta": round(mu, 6), "sd": round(sd, 6),
            "t": round(mu / se, 3) if se else None,
            "lb95": round(mu - T_ONE_SIDED * se, 6) if se else None, "mean": mu,
            "t_raw": (mu / se) if se else None}


def _t_sf(t: float, df: int) -> float:
    from scipy import stats
    return float(stats.t.sf(t, df))


def p_one_sided_normal(t) -> float | None:
    if t is None:
        return None
    return 0.5 * math.erfc(float(t) / math.sqrt(2.0))


def cr1_mean(d, clusters) -> dict:
    """5k's CR1 form for a mean: S_g = sum over cluster g of (d_i - dbar),
    SE = sqrt(G / (G - 1) x sum_g S_g^2) / N, t = dbar / SE, df = G - 1."""
    d = np.asarray(d, dtype=float)
    n = int(d.size)
    if n < 2:
        return {"n": n, "G": None, "mean": None, "se": None, "t": None, "df": None,
                "p_two_sided": None}
    _, inv = np.unique(np.asarray(clusters), return_inverse=True)
    G = int(inv.max()) + 1
    mu = float(d.mean())
    if G < 2:
        return {"n": n, "G": G, "mean": mu, "se": None, "t": None, "df": None,
                "p_two_sided": None}
    sg = np.bincount(inv, weights=d - mu)
    se = math.sqrt(G / (G - 1) * float((sg ** 2).sum())) / n
    t = mu / se if se > 0 else None
    return {"n": n, "G": G, "mean": mu, "se": se, "t": t, "df": G - 1,
            "p_two_sided": None if t is None else min(1.0, 2.0 * _t_sf(abs(t), G - 1))}


def cr1_ols(X, e, clusters) -> np.ndarray | None:
    """The CR1 sandwich for OLS coefficients (the 5k factor G / (G - 1)), or None."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    _, inv = np.unique(np.asarray(clusters), return_inverse=True)
    G = int(inv.max()) + 1 if inv.size else 0
    if G < 2:
        return None
    try:
        bread = np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None
    k = X.shape[1]
    sc = np.zeros((G, k))
    for j in range(k):
        sc[:, j] = np.bincount(inv, weights=X[:, j] * e, minlength=G)
    meat = sc.T @ sc
    return G / (G - 1) * bread @ meat @ bread


def holm(pvals: dict, alpha: float = ALPHA) -> dict:
    """Holm's step-down within one family: sort ascending, compare the i-th smallest
    with alpha / (m - i), stop at the first that fails. A missing p is never rejected."""
    m = len(pvals)
    order = sorted(pvals, key=lambda k: (pvals[k] is None, pvals[k] if pvals[k] is not None
                                         else 1.0, k))
    out, stopped = {}, False
    for i, k in enumerate(order):
        thr = alpha / (m - i)
        p = pvals[k]
        rej = (not stopped) and p is not None and p <= thr
        if not rej:
            stopped = True
        out[k] = {"p": _r(p, 8), "step": i + 1, "threshold": _r(thr, 8), "reject": bool(rej)}
    return out


def twin_bar(values) -> dict:
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"draws_used": 0, "p95": None}
    return {"draws_used": int(v.size), "p95": float(np.percentile(v, TWIN_PERCENTILE))}


def beats(stat, bar) -> bool:
    """Strictly above the twin's 95th percentile."""
    return stat is not None and bar.get("p95") is not None and float(stat) > bar["p95"]


def _date_groups(dates) -> list:
    """[(date, indices)] in ascending date order."""
    groups = defaultdict(list)
    for i, d in enumerate(dates):
        groups[d].append(i)
    return [(d, np.asarray(groups[d], dtype=int)) for d in sorted(groups)]


def permute_slots(values, groups, rng) -> np.ndarray:
    """One draw: within each date group (ascending), rng.permutation of its slots."""
    v = np.asarray(values, dtype=float)
    out = v.copy()
    for _, idx in groups:
        out[idx] = v[idx[rng.permutation(idx.size)]]
    return out


def twin_rngs(n: int = TWIN_DRAWS):
    """The registered twin seeds: numpy.random.default_rng(k) for k = 0 to n - 1."""
    for k in range(int(n)):
        yield k, np.random.default_rng(k)


def stakes_scores(G, g_ref: float) -> np.ndarray:
    """intensity_core.stakes_score, vectorized."""
    G = np.clip(np.asarray(G, dtype=float), 0.0, 2.0)
    return np.log1p(G / g_ref) / math.log1p(2.0 / g_ref)


# ---------------------------------------------------------------------------
# IX-ML: IX-A and IX-A2
# ---------------------------------------------------------------------------
def _ml_arrays(rows: list, outcomes: dict) -> dict:
    n = len(rows)
    A = {k: np.asarray([r[k] for r in rows], dtype=float) for k in
         ("p_base", "dpo_h", "dpo_a", "dws_h", "dws_a", "q_h", "q_a", "S", "Q")}
    A["y"] = np.asarray([outcomes[r["pk"]][0] for r in rows], dtype=float)
    A["season"] = np.asarray([r["season"] for r in rows], dtype=int)
    A["month"] = np.asarray([r["month"] for r in rows], dtype=int)
    A["date"] = np.asarray([r["date"] for r in rows])
    A["ds"] = A["dpo_h"] - A["dpo_a"]
    A["dq"] = A["q_h"] - A["q_a"]
    A["n"] = n
    return A


def _grade(off_f, x_f, y_f, off_g, x_g, y_g) -> dict:
    b = fit_offset_logistic(off_f, x_f, y_f)
    xg = np.asarray(x_g, dtype=float)
    if xg.ndim == 1:
        xg = xg[:, None]
    pc = _sigmoid(off_g + xg @ b)
    pi = _sigmoid(off_g)
    return {"b": b, "p_inc": pi, "p_chal": pc, "bi": brier(pi, y_g), "bc": brier(pc, y_g),
            "li": log_loss(pi, y_g), "lc": log_loss(pc, y_g)}


def _focus_table(seasons, months, mask, base_mask) -> dict:
    out = {}
    for s in sorted(set(int(x) for x in seasons[base_mask])) if base_mask.any() else []:
        row = {}
        for m in range(3, 11):
            sel = base_mask & (seasons == s) & (months == m)
            row[str(m)] = {"games": int(sel.sum()), "focus": int((sel & mask).sum())}
        out[str(s)] = row
    return out


def family_ml(fit_rows, grade_rows, outcomes, g_ref, *, draws=TWIN_DRAWS) -> dict:
    """IX-A (asymmetric stakes, one-sided, b > 0) and IX-A2 (home field under symmetric
    stakes, two-sided), fitted on the fit seasons and graded on 2023-2025."""
    F = _ml_arrays(fit_rows, outcomes)
    Gd = _ml_arrays(grade_rows, outcomes)
    out = {"fit_games": F["n"], "graded_games": Gd["n"]}
    if F["n"] < 2 or Gd["n"] < 2:
        out["IX-A"] = {"status": "no data"}
        out["IX-A2"] = {"status": "no data"}
        out["holm"] = holm({"IX-A": None, "IX-A2": None})
        return out
    of, og = _logit(F["p_base"]), _logit(Gd["p_base"])
    all_dates = np.concatenate([F["date"], Gd["date"]])
    nF = F["n"]
    slot_dates = np.concatenate([all_dates, all_dates])

    # IX-A ----------------------------------------------------------------
    focus = np.abs(Gd["ds"]) >= ic.FOCUS_THRESHOLD
    a = _grade(of, F["ds"], F["y"], og, Gd["ds"], Gd["y"])
    c1 = paired_delta(a["bi"][focus], a["bc"][focus])
    c1_cr1 = cr1_mean((a["bi"] - a["bc"])[focus], Gd["date"][focus])
    c2 = paired_delta(a["li"], a["lc"])
    b = float(a["b"][0])
    ctrl = _grade(of, F["dq"], F["y"], og, Gd["dq"], Gd["y"])
    ctrl_c1 = paired_delta(ctrl["bi"][focus], ctrl["bc"][focus])
    two = fit_offset_logistic(of, np.column_stack([F["ds"], F["dq"]]), F["y"])
    groups = _date_groups(slot_dates)
    slots = np.concatenate([np.concatenate([F["dpo_h"], Gd["dpo_h"]]),
                            np.concatenate([F["dpo_a"], Gd["dpo_a"]])])
    m = slots.size // 2
    twins, twin_empty = [], 0
    for _k, rng in twin_rngs(draws):
        pv = permute_slots(slots, groups, rng)
        ds_t = pv[:m] - pv[m:]
        dsf, dsg = ds_t[:nF], ds_t[nF:]
        tg = _grade(of, dsf, F["y"], og, dsg, Gd["y"])
        ft = np.abs(dsg) >= ic.FOCUS_THRESHOLD
        if ft.sum() < 2:
            twin_empty += 1
            twins.append(None)
            continue
        twins.append(float((tg["bi"][ft] - tg["bc"][ft]).mean()))
    bar = twin_bar(twins)
    shift = (a["p_chal"] - a["p_inc"])[focus]
    exp_t = (math.sqrt(int(focus.sum())) * float(np.sqrt((shift ** 2).mean()))
             if focus.any() else None)
    corr = (float(np.corrcoef(Gd["ds"], Gd["dq"])[0, 1])
            if Gd["n"] > 2 and np.std(Gd["ds"]) > 0 and np.std(Gd["dq"]) > 0 else None)
    crit = {
        "c1_focus_brier_t_at_least_1_645": bool(c1["t_raw"] is not None
                                                and c1["t_raw"] >= T_ONE_SIDED),
        "c2_log_loss_not_worse": bool(c2["mean"] is not None and c2["mean"] >= 0),
        "c3_sign_b_positive": bool(b > 0),
        "c4_beats_twin": beats(c1["mean"], bar),
        "c5_beats_control_2": bool(c1["mean"] is not None and ctrl_c1["mean"] is not None
                                   and c1["mean"] > ctrl_c1["mean"]),
    }
    ixa = {
        "term": "logit p' = logit p_Elo + b x ds, ds = dPO_h - dPO_a, no intercept",
        "b": _r(b), "focus_threshold": ic.FOCUS_THRESHOLD,
        "focus_games": int(focus.sum()),
        "criterion_1_focus_brier": _strip(c1), "criterion_1_cr1_date": _cr1_out(c1_cr1),
        "criterion_2_log_loss_all": _strip(c2),
        "twin": {"draws": draws, "seeds": f"numpy.random.default_rng(k), k = 0 to {draws - 1}",
                 "statistic": "graded focus-set paired Brier improvement, twin's own focus set",
                 "empty_focus_draws": twin_empty, **_bar_out(bar)},
        "control_2": {"term": "dq = q_h - q_a, q = RD / (G + 70) through D-1",
                      "b": _r(ctrl["b"][0]), "focus_brier": _strip(ctrl_c1)},
        "two_term_fit": {"b_ds": _r(two[0]), "b_dq": _r(two[1])},
        "corr_ds_dq_graded": _r(corr),
        "expected_t_at_fitted_b": _r(exp_t, 4),
        "focus_by_season_month": {
            "fit": _focus_table(F["season"], F["month"], np.abs(F["ds"]) >= ic.FOCUS_THRESHOLD,
                                np.ones(nF, bool)),
            "graded": _focus_table(Gd["season"], Gd["month"], focus, np.ones(Gd["n"], bool))},
        "criteria": crit,
        "p_holm": p_one_sided_normal(c1["t_raw"]),
    }

    # IX-A2 ---------------------------------------------------------------
    s_bar = float(F["S"].mean())
    a2 = _grade(of, F["S"] - s_bar, F["y"], og, Gd["S"] - s_bar, Gd["y"])
    d2 = a2["bi"] - a2["bc"]
    a2_pd = paired_delta(a2["bi"], a2["bc"])
    a2_cr1 = cr1_mean(d2, Gd["date"])
    a2_ll = paired_delta(a2["li"], a2["lc"])
    q_bar = float(F["Q"].mean())
    a2c = _grade(of, F["Q"] - q_bar, F["y"], og, Gd["Q"] - q_bar, Gd["y"])
    a2c_pd = paired_delta(a2c["bi"], a2c["bc"])
    wslots = np.concatenate([np.concatenate([F["dws_h"], Gd["dws_h"]]),
                             np.concatenate([F["dws_a"], Gd["dws_a"]])])
    twins2 = []
    for _k, rng in twin_rngs(draws):
        pv = permute_slots(wslots, groups, rng)
        S_t = stakes_scores(pv[:m] + pv[m:], g_ref)
        sf, sg = S_t[:nF], S_t[nF:]
        sb = float(sf.mean())
        tg = _grade(of, sf - sb, F["y"], og, sg - sb, Gd["y"])
        twins2.append(float((tg["bi"] - tg["bc"]).mean()))
    bar2 = twin_bar(twins2)
    crit2 = {
        "positive_improvement": bool(a2_pd["mean"] is not None and a2_pd["mean"] > 0),
        "log_loss_not_worse": bool(a2_ll["mean"] is not None and a2_ll["mean"] >= 0),
        "beats_twin": beats(a2_pd["mean"], bar2),
        "beats_quality_control": bool(a2_pd["mean"] is not None and a2c_pd["mean"] is not None
                                      and a2_pd["mean"] > a2c_pd["mean"]),
    }
    ixa2 = {
        "term": "logit p' = logit p_Elo + c x (S - S_bar), S_bar the fit-half mean",
        "c": _r(a2["b"][0]), "S_bar": _r(s_bar),
        "brier_all_graded": _strip(a2_pd), "brier_cr1_date": _cr1_out(a2_cr1),
        "log_loss_all": _strip(a2_ll),
        "twin": {"draws": draws, "statistic": "graded paired Brier improvement",
                 "permuted": "club-level dWS slots within each date", **_bar_out(bar2)},
        "quality_control": {"term": "Q - Q_bar in place of S - S_bar", "c": _r(a2c["b"][0]),
                            "brier_all_graded": _strip(a2c_pd)},
        "criteria": crit2,
        "p_holm": a2_cr1["p_two_sided"],
    }
    h = holm({"IX-A": ixa["p_holm"], "IX-A2": ixa2["p_holm"]})
    ixa["resolved"] = bool(all(crit.values()) and h["IX-A"]["reject"])
    ixa2["resolved"] = bool(all(crit2.values()) and h["IX-A2"]["reject"])
    out.update({"IX-A": ixa, "IX-A2": ixa2, "holm": h, "m": 2})
    return out


def _strip(pd_: dict) -> dict:
    return {k: v for k, v in pd_.items() if k not in ("mean", "t_raw")}


def _cr1_out(c: dict) -> dict:
    return {"n": c["n"], "G": c["G"], "mean": _r(c["mean"], 8), "se": _r(c["se"], 8),
            "t": _r(c["t"], 4), "df": c["df"], "p_two_sided": _r(c["p_two_sided"], 8)}


def _bar_out(bar: dict) -> dict:
    return {"draws_used": bar["draws_used"], "p95": _r(bar["p95"], 8)}


# ---------------------------------------------------------------------------
# IX-TOT: IX-B, the fixed-effects panel on the total
# ---------------------------------------------------------------------------
def fe_design(rows) -> np.ndarray:
    """Club-season (one column per club-season, entered for both participants),
    venue-season and season-month indicators."""
    cs = sorted({(r["season"], c) for r in rows for c in (r["home"], r["away"])})
    vs = sorted({(r["season"], r["venue"]) for r in rows})
    sm = sorted({(r["season"], r["month"]) for r in rows})
    ci = {k: i for i, k in enumerate(cs)}
    vi = {k: len(cs) + i for i, k in enumerate(vs)}
    mi = {k: len(cs) + len(vs) + i for i, k in enumerate(sm)}
    D = np.zeros((len(rows), len(cs) + len(vs) + len(sm)))
    for j, r in enumerate(rows):
        D[j, ci[(r["season"], r["home"])]] += 1.0
        D[j, ci[(r["season"], r["away"])]] += 1.0
        D[j, vi[(r["season"], r["venue"])]] = 1.0
        D[j, mi[(r["season"], r["month"])]] = 1.0
    return D


class Residualizer:
    """Projection off the column space of a design (an orthonormal basis from its SVD,
    rank-deficient columns allowed): the Frisch-Waugh-Lovell step."""

    def __init__(self, D: np.ndarray):
        if D.size == 0:
            self.U = np.zeros((D.shape[0], 0))
        else:
            U, s, _ = np.linalg.svd(D, full_matrices=False)
            r = int((s > s[0] * 1e-10).sum()) if s.size else 0
            self.U = U[:, :r]

    def __call__(self, v):
        v = np.asarray(v, dtype=float)
        return v - self.U @ (self.U.T @ v)


def panel_fit(res: Residualizer, y, X, clusters) -> dict:
    """OLS of y on X net of the fixed effects; CR1 t by date."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    ry, rX = res(y), res(X)
    xtx = rX.T @ rX
    if rX.shape[0] < 3 or np.linalg.matrix_rank(xtx) < rX.shape[1]:
        return {"beta": [None] * rX.shape[1], "t": [None] * rX.shape[1], "G": None,
                "p_two_sided": [None] * rX.shape[1]}
    beta = np.linalg.solve(xtx, rX.T @ ry)
    e = ry - rX @ beta
    V = cr1_ols(rX, e, clusters)
    G = len(set(np.asarray(clusters).tolist()))
    ts, ps = [], []
    for j in range(rX.shape[1]):
        se = math.sqrt(V[j, j]) if V is not None and V[j, j] > 0 else None
        t = beta[j] / se if se else None
        ts.append(t)
        ps.append(None if t is None else min(1.0, 2.0 * _t_sf(abs(t), G - 1)))
    return {"beta": [float(b) for b in beta], "t": ts, "G": G, "p_two_sided": ps}


def family_tot(rows, outcomes, g_ref, *, draws=TWIN_DRAWS) -> dict:
    """IX-B: total = theta(home club-season) + theta(away club-season) + pi(venue-season)
    + mu(season-month) + beta S + e, OLS, CR1 date clusters, two-sided."""
    n = len(rows)
    out = {"games": n, "m": 1}
    if n < 3:
        out["IX-B"] = {"status": "no data"}
        out["holm"] = holm({"IX-B": None})
        return out
    y = np.asarray([outcomes[r["pk"]][1] for r in rows], dtype=float)
    S = np.asarray([r["S"] for r in rows], dtype=float)
    dates = np.asarray([r["date"] for r in rows])
    res = Residualizer(fe_design(rows))
    cand = panel_fit(res, y, S, dates)
    sd_S = float(np.std(S))
    groups = _date_groups(np.concatenate([dates, dates]))
    slots = np.concatenate([[r["dws_h"] for r in rows], [r["dws_a"] for r in rows]])
    twins = []
    for _k, rng in twin_rngs(draws):
        pv = permute_slots(slots, groups, rng)
        St = stakes_scores(pv[:n] + pv[n:], g_ref)
        t = panel_fit(res, y, St, dates)["t"][0]
        twins.append(None if t is None else abs(t))
    bar = twin_bar(twins)

    def control(name):
        keep = [i for i, r in enumerate(rows) if r.get(name) is not None]
        if len(keep) < 3:
            return {"rows": len(keep), "status": "no data"}
        sub = [rows[i] for i in keep]
        rsub = Residualizer(fe_design(sub))
        xs = np.asarray([r[name] for r in sub], dtype=float)
        ss = S[keep]
        fc = panel_fit(rsub, y[keep], xs, dates[keep])
        fs = panel_fit(rsub, y[keep], ss, dates[keep])
        eff_c = None if fc["beta"][0] is None else abs(fc["beta"][0]) * float(np.std(xs))
        eff_s = None if fs["beta"][0] is None else abs(fs["beta"][0]) * float(np.std(ss))
        return {"rows": len(keep), "beta": _r(fc["beta"][0]), "t": _r(fc["t"][0], 4),
                "effect_per_sd": _r(eff_c), "candidate_effect_per_sd_same_rows": _r(eff_s),
                "candidate_beats": bool(eff_s is not None and eff_c is not None
                                        and eff_s > eff_c)}

    ca, cq = control("A"), control("Q")
    keep3 = [i for i, r in enumerate(rows) if r.get("A") is not None]
    three = None
    if len(keep3) >= 4:
        sub = [rows[i] for i in keep3]
        X3 = np.column_stack([S[keep3], [r["A"] for r in sub], [r["Q"] for r in sub]])
        f3 = panel_fit(Residualizer(fe_design(sub)), y[keep3], X3, dates[keep3])
        three = {"rows": len(keep3), "beta_S_A_Q": [_r(b) for b in f3["beta"]],
                 "t_S_A_Q": [_r(t, 4) for t in f3["t"]]}
    t0 = cand["t"][0]
    crit = {"beats_twin_abs_t": beats(None if t0 is None else abs(t0), bar),
            "beats_control_A": bool(ca.get("candidate_beats")),
            "beats_control_Q": bool(cq.get("candidate_beats"))}
    ixb = {"term": "beta x S in the club-season, venue-season and season-month panel",
           "beta": _r(cand["beta"][0]), "beta_per_sd_S": _r(None if cand["beta"][0] is None
                                                            else cand["beta"][0] * sd_S),
           "t_cr1_date": _r(t0, 4), "dates": cand["G"], "p_two_sided": cand["p_two_sided"][0],
           "twin": {"draws": draws, "statistic": "|t|",
                    "permuted": "club-level dWS slots within each date", **_bar_out(bar)},
           "control_A": ca, "control_Q": cq, "three_term_fit": three,
           "venue_from_home_club": sum(1 for r in rows if r["venue_from_home"]),
           "criteria": crit}
    h = holm({"IX-B": ixb["p_two_sided"]})
    ixb["resolved"] = bool(all(crit.values()) and h["IX-B"]["reject"])
    out.update({"IX-B": ixb, "holm": h})
    return out


# ---------------------------------------------------------------------------
# IX-TYPE: team types times stakes
# ---------------------------------------------------------------------------
def _date_z(clubs_by_date: dict, key: str) -> dict:
    """{date: {club: z}}: each club value standardized across the clubs playing that
    date (population sd); a club with no value, or a date with fewer than two values or
    no spread, has no z."""
    out = {}
    for D, clubs in clubs_by_date.items():
        vals = {c: v[key] for c, v in clubs.items() if v.get(key) is not None}
        if len(vals) < 2:
            out[D] = {}
            continue
        arr = np.asarray(list(vals.values()), dtype=float)
        sd = float(arr.std())
        out[D] = {} if sd <= 0 else {c: (v - float(arr.mean())) / sd for c, v in vals.items()}
    return out


def _permute_club_values(clubs_by_date: dict, key: str, rng) -> dict:
    """One twin draw: each date (ascending), the clubs playing it (sorted) permuted."""
    out = {}
    for D in sorted(clubs_by_date):
        clubs = sorted(clubs_by_date[D])
        vals = [clubs_by_date[D][c].get(key) for c in clubs]
        perm = rng.permutation(len(clubs))
        out[D] = {c: {key: vals[perm[i]]} for i, c in enumerate(clubs)}
    return out


def family_type(fit_rows, grade_rows, outcomes, clubs_by_date, *, draws=TWIN_DRAWS) -> dict:
    """IX-TYPE: logit p' = logit p_Elo + b_k x S x (z_k,h - z_k,a), one member per type,
    fitted on the fit seasons, graded on 2023-2025, two-sided, Holm m = 4."""
    out = {"m": 4, "members": {}, "excluded": dict(TYPE_EXCLUDED)}
    pv = {}
    for key in TYPE_MEMBERS:
        z = _date_z(clubs_by_date, key)
        zq = _date_z(clubs_by_date, "q")

        def gap(rows, zz):
            return np.asarray([(zz.get(r["date"], {}).get(r["home"], np.nan)
                                - zz.get(r["date"], {}).get(r["away"], np.nan))
                               for r in rows], dtype=float)

        gf, gg = gap(fit_rows, z), gap(grade_rows, z)
        mf, mg = np.isfinite(gf), np.isfinite(gg)
        rf = [r for r, k in zip(fit_rows, mf) if k]
        rg = [r for r, k in zip(grade_rows, mg) if k]
        if len(rf) < 2 or len(rg) < 2:
            out["members"][key] = {"status": "no data", "fit_games": len(rf),
                                   "graded_games": len(rg)}
            pv[key] = None
            continue
        F, Gd = _ml_arrays(rf, outcomes), _ml_arrays(rg, outcomes)
        of, og = _logit(F["p_base"]), _logit(Gd["p_base"])
        xf, xg = F["S"] * gf[mf], Gd["S"] * gg[mg]
        a = _grade(of, xf, F["y"], og, xg, Gd["y"])
        pdl = paired_delta(a["bi"], a["bc"])
        cr = cr1_mean(a["bi"] - a["bc"], Gd["date"])
        ll = paired_delta(a["li"], a["lc"])
        qf, qg = gap(rf, zq), gap(rg, zq)
        okc = np.isfinite(qf).all() and np.isfinite(qg).all()
        ctrl_pd = None
        if okc:
            c = _grade(of, F["S"] * qf, F["y"], og, Gd["S"] * qg, Gd["y"])
            ctrl_pd = paired_delta(c["bi"], c["bc"])
        twins = []
        for _k, rng in twin_rngs(draws):
            zt = _date_z(_permute_club_values(clubs_by_date, key, rng), key)
            tf, tg_ = gap(rf, zt), gap(rg, zt)
            tf, tg_ = np.nan_to_num(tf), np.nan_to_num(tg_)
            t = _grade(of, F["S"] * tf, F["y"], og, Gd["S"] * tg_, Gd["y"])
            twins.append(float((t["bi"] - t["bc"]).mean()))
        bar = twin_bar(twins)
        crit = {"positive_improvement": bool(pdl["mean"] is not None and pdl["mean"] > 0),
                "log_loss_not_worse": bool(ll["mean"] is not None and ll["mean"] >= 0),
                "beats_twin": beats(pdl["mean"], bar),
                "beats_quality_control": bool(ctrl_pd is not None and pdl["mean"] is not None
                                              and ctrl_pd["mean"] is not None
                                              and pdl["mean"] > ctrl_pd["mean"])}
        out["members"][key] = {
            "b": _r(a["b"][0]), "fit_games": len(rf), "graded_games": len(rg),
            "brier_all_graded": _strip(pdl), "brier_cr1_date": _cr1_out(cr),
            "log_loss_all": _strip(ll),
            "twin": {"draws": draws, "statistic": "graded paired Brier improvement",
                     "permuted": "the type's club values among the clubs playing each date",
                     **_bar_out(bar)},
            "quality_control": {"term": "S x (z_q,h - z_q,a), q = RD / (G + 70)",
                                "brier_all_graded": None if ctrl_pd is None else _strip(ctrl_pd)},
            "criteria": crit, "p_holm": cr["p_two_sided"]}
        pv[key] = cr["p_two_sided"]
    h = holm(pv)
    for key in TYPE_MEMBERS:
        m = out["members"][key]
        m["resolved"] = bool(m.get("criteria") and all(m["criteria"].values())
                             and h[key]["reject"])
    out["holm"] = h
    return out


# ---------------------------------------------------------------------------
# IX-ARCH: prior-season archetypes in top-decile-S games
# ---------------------------------------------------------------------------
def _woba_den(et) -> bool:
    return _is_pa(et) and et not in NOT_WOBA_DEN


def season_totals(plays, games: list, weights: dict | None) -> dict | None:
    """Per-player and league totals of one season from its plays (the prior season of
    an IX-ARCH season): batters, pitchers, league wOBA, platoon and park splits."""
    if plays is None or len(plays) == 0 or not weights:
        return None
    side = {g["pk"]: (g["home"], g["away"]) for g in games}
    p = plays[plays["event_type"].map(_is_pa)].copy()
    p = p[p["game_pk"].isin(list(side))]
    if len(p) == 0:
        return None
    p["den"] = p["event_type"].map(_woba_den).astype(float)
    p["val"] = p["event_type"].map(lambda e: float(weights.get(WOBA_VALUE_KEYS.get(e, ""), 0.0))
                                   if e in WOBA_VALUE_KEYS else 0.0) * p["den"]
    p["ab"] = (p["event_type"].map(lambda e: e not in NOT_AB)).astype(float)
    p["k"] = p["event_type"].isin(EVT_K).astype(float)
    p["bb"] = p["event_type"].isin(EVT_BB).astype(float)
    p["hr"] = (p["event_type"] == "home_run").astype(float)
    p["x2"] = (p["event_type"] == "double").astype(float)
    p["x3"] = (p["event_type"] == "triple").astype(float)
    p["gb"] = (p["trajectory"] == "ground_ball").astype(float)
    p["bip"] = p["trajectory"].isin(TRAJ_BIP).astype(float)
    p["pa"] = 1.0
    bat = p.groupby("batter_id")[["pa", "ab", "k", "bb", "hr", "x2", "x3", "den", "val"]].sum()
    pit = p.groupby("pitcher_id")[["pa", "k", "bb", "gb", "bip", "den", "val"]].sum()
    same = (p["bat_side"] == p["pitch_hand"])
    lg = (float(p["val"].sum()), float(p["den"].sum()))
    plat = {"same": (float(p.loc[same, "val"].sum()), float(p.loc[same, "den"].sum())),
            "opp": (float(p.loc[~same, "val"].sum()), float(p.loc[~same, "den"].sum()))}
    park = {}
    home_of = p["game_pk"].map(lambda k: side[int(k)][0])
    away_of = p["game_pk"].map(lambda k: side[int(k)][1])
    for club in ORGS:
        hm = home_of == club
        rd = away_of == club
        park[club] = {"home": (float(p.loc[hm, "val"].sum()), float(p.loc[hm, "den"].sum())),
                      "road": (float(p.loc[rd, "val"].sum()), float(p.loc[rd, "den"].sum()))}
    return {"batters": {int(k): v for k, v in bat.to_dict("index").items()},
            "pitchers": {int(k): v for k, v in pit.to_dict("index").items()},
            "league": lg, "platoon": plat, "park": park}


def archetypes(tot: dict, params: dict) -> dict:
    """{member: set of player ids} from prior-season totals, qualified players only."""
    out = {k: set() for k in ARCH_MEMBERS}
    bat = {k: v for k, v in tot["batters"].items() if v["pa"] >= params["arch_min_pa"]}
    pit = {k: v for k, v in tot["pitchers"].items() if v["pa"] >= params["arch_min_bf"]}
    if bat:
        iso = {k: ((v["x2"] + 2 * v["x3"] + 3 * v["hr"]) / v["ab"]) if v["ab"] else 0.0
               for k, v in bat.items()}
        kp = {k: v["k"] / v["pa"] for k, v in bat.items()}
        bb = {k: v["bb"] / v["pa"] for k, v in bat.items()}
        q_iso, q_k, q_bb = (np.quantile(list(iso.values()), 0.8),
                            np.quantile(list(kp.values()), 0.2),
                            np.quantile(list(bb.values()), 0.8))
        out["hitter_power"] = {k for k, v in iso.items() if v >= q_iso}
        out["hitter_contact"] = {k for k, v in kp.items() if v <= q_k}
        out["hitter_patience"] = {k for k, v in bb.items() if v >= q_bb}
    if pit:
        kp = {k: v["k"] / v["pa"] for k, v in pit.items()}
        bb = {k: v["bb"] / v["pa"] for k, v in pit.items()}
        gb = {k: (v["gb"] / v["bip"]) if v["bip"] else 0.0 for k, v in pit.items()}
        q_k, q_bb, q_gb = (np.quantile(list(kp.values()), 0.8),
                           np.quantile(list(bb.values()), 0.2),
                           np.quantile(list(gb.values()), 0.8))
        out["pitcher_power"] = {k for k, v in kp.items() if v >= q_k}
        out["pitcher_command"] = {k for k, v in bb.items() if v <= q_bb}
        out["pitcher_groundball"] = {k for k, v in gb.items() if v >= q_gb}
    return out


def pa_residuals(plays, rows: list, tot: dict, weights: dict, params: dict):
    """(DataFrame of scored PAs with residual, game index, batter, pitcher). The PA's
    wOBA value at the season's weights minus the matchup expectation from the prior
    season: lg x (b / lg) x (p / lg) x park x platoon, b and p shrunk with
    `arch_shrink` league-average PA. Residuals centered within the season."""
    import pandas as pd
    by_pk = {r["pk"]: r for r in rows}
    p = plays[plays["game_pk"].isin(list(by_pk)) & plays["event_type"].map(_woba_den)].copy()
    if len(p) == 0:
        return None
    lgv, lgd = tot["league"]
    lg = lgv / lgd if lgd else None
    if not lg:
        return None
    k = params["arch_shrink"]

    def rate(v, d):
        return (v + k * lg) / (d + k)

    b_rate = {pid: rate(x["val"], x["den"]) for pid, x in tot["batters"].items()}
    p_rate = {pid: rate(x["val"], x["den"]) for pid, x in tot["pitchers"].items()}
    plat = {}
    for key, (v, d) in tot["platoon"].items():
        plat[key] = (v / d) / lg if d else 1.0
    park = {}
    for club, x in tot["park"].items():
        (hv, hd), (rv, rd) = x["home"], x["road"]
        pf = ((hv / hd) / (rv / rd)) if (hd and rd and rv) else 1.0
        park[club] = 1.0 + params["park_regress"] * (pf - 1.0)
    p["val"] = p["event_type"].map(lambda e: float(weights.get(WOBA_VALUE_KEYS[e], 0.0))
                                   if e in WOBA_VALUE_KEYS else 0.0)
    br = p["batter_id"].map(lambda x: b_rate.get(int(x), lg) if x == x else lg)
    pr = p["pitcher_id"].map(lambda x: p_rate.get(int(x), lg) if x == x else lg)
    pk_home = p["game_pk"].map(lambda x: by_pk[int(x)]["home"])
    pf = pk_home.map(lambda c: park.get(c, 1.0))
    pl = np.where(p["bat_side"] == p["pitch_hand"], plat.get("same", 1.0), plat.get("opp", 1.0))
    p["exp"] = lg * (br / lg) * (pr / lg) * pf * pl
    p["resid"] = p["val"] - p["exp"]
    p["resid"] = p["resid"] - p["resid"].mean()
    return pd.DataFrame({"game_pk": p["game_pk"].astype(int).values,
                         "batter_id": p["batter_id"].values, "pitcher_id": p["pitcher_id"].values,
                         "resid": p["resid"].values})


def did_fit(r, A, T, game_idx) -> dict:
    """r = a + b1 A + b2 T + b3 A T; b3 is the difference in differences; CR1 by game."""
    A = A.astype(float)
    T = T.astype(float)
    X = np.column_stack([np.ones_like(r), A, T, A * T])
    cells = [(A == a) & (T == t) for a in (0, 1) for t in (0, 1)]
    if any(c.sum() == 0 for c in cells):
        return {"did": None, "t": None, "p_two_sided": None, "G": None}
    beta = np.linalg.lstsq(X, r, rcond=None)[0]
    e = r - X @ beta
    V = cr1_ols(X, e, game_idx)
    G = len(np.unique(game_idx))
    se = math.sqrt(V[3, 3]) if V is not None and V[3, 3] > 0 else None
    t = beta[3] / se if se else None
    return {"did": float(beta[3]), "t": t, "G": G,
            "p_two_sided": None if t is None else min(1.0, 2.0 * _t_sf(abs(t), G - 1))}


def family_arch(feats: dict, source, rows: list, params: dict, *, draws=TWIN_DRAWS) -> dict:
    """IX-ARCH: each archetype's mean PA residual in top-decile-S games minus elsewhere,
    minus the same difference for every other player; game-clustered; Holm m = 6."""
    import pandas as pd
    out = {"m": 6, "members": {}, "seasons": {}, "expected": "null (stated before any read)",
           "no_player_number": "no per-player big-game number is published"}
    frames = []
    for s in SEASONS:
        srows = [r for r in rows if r["season"] == s]
        if not srows:
            out["seasons"][str(s)] = {"status": "no scored games"}
            continue
        prior = s - 1
        tot = None
        if prior in feats:
            tot = season_totals(source.plays(prior), feats[prior]["games"],
                                source.weights(prior))
        else:
            tot = source.extra_totals(prior)
        weights = source.weights(s)
        plays = source.plays(s)
        if not tot or not weights or plays is None:
            out["seasons"][str(s)] = {"status": "no prior-season source" if not tot
                                      else "no weights or plays", "prior": prior}
            continue
        res = pa_residuals(plays, srows, tot, weights, params)
        if res is None:
            out["seasons"][str(s)] = {"status": "no scored plate appearances"}
            continue
        arch = archetypes(tot, params)
        S = np.asarray([r["S"] for r in srows], dtype=float)
        Q = np.asarray([r["Q"] for r in srows], dtype=float)
        res["season"] = s
        frames.append((s, srows, res, arch, float(np.quantile(S, TOP_DECILE)),
                       float(np.quantile(Q, TOP_DECILE))))
        out["seasons"][str(s)] = {"status": "read", "plate_appearances": int(len(res)),
                                  "games": len(srows)}
    if not frames:
        for k in ARCH_MEMBERS:
            out["members"][k] = {"status": "no data"}
        out["holm"] = holm({k: None for k in ARCH_MEMBERS})
        return out
    gpk = [r["pk"] for _, srows, _, _, _, _ in frames for r in srows]
    gidx = {pk: i for i, pk in enumerate(gpk)}
    allrows = [r for _, srows, _, _, _, _ in frames for r in srows]
    S_game = np.asarray([r["S"] for r in allrows], dtype=float)
    Q_game = np.asarray([r["Q"] for r in allrows], dtype=float)
    season_game = np.asarray([r["season"] for r in allrows], dtype=int)
    thr_S = {s: ts for s, _, _, _, ts, _ in frames}
    thr_Q = {s: tq for s, _, _, _, _, tq in frames}
    top_S = S_game >= np.asarray([thr_S[s] for s in season_game])
    top_Q = Q_game >= np.asarray([thr_Q[s] for s in season_game])
    pa = pd.concat([f[2] for f in frames], ignore_index=True)
    g_of_pa = pa["game_pk"].map(gidx).to_numpy()
    r = pa["resid"].to_numpy(dtype=float)
    groups = _date_groups([r_["date"] for r_ in allrows])
    pv = {}
    for k in ARCH_MEMBERS:
        role = "batter_id" if k.startswith("hitter") else "pitcher_id"
        member = np.zeros(len(pa), dtype=bool)
        for s, _, _, arch, _, _ in frames:
            sel = (pa["season"] == s).to_numpy()
            member |= sel & pa[role].isin(sorted(arch[k])).to_numpy()
        cand = did_fit(r, member, top_S[g_of_pa], g_of_pa)
        ctrl = did_fit(r, member, top_Q[g_of_pa], g_of_pa)
        twins = []
        for _k, rng in twin_rngs(draws):
            St = permute_slots(S_game, groups, rng)
            topt = St >= np.asarray([thr_S[s] for s in season_game])
            tt = did_fit(r, member, topt[g_of_pa], g_of_pa)["t"]
            twins.append(None if tt is None else abs(tt))
        bar = twin_bar(twins)
        crit = {"beats_twin_abs_t": beats(None if cand["t"] is None else abs(cand["t"]), bar),
                "beats_quality_control": bool(cand["did"] is not None and ctrl["did"] is not None
                                              and abs(cand["did"]) > abs(ctrl["did"]))}
        out["members"][k] = {
            "plate_appearances_member": int(member.sum()),
            "plate_appearances_top_decile": int(top_S[g_of_pa].sum()),
            "did_woba": _r(cand["did"]), "t_cr1_game": _r(cand["t"], 4), "games": cand["G"],
            "twin": {"draws": draws, "statistic": "|t|",
                     "permuted": "S among the games of each date", **_bar_out(bar)},
            "quality_control": {"term": "top decile of Q in place of S",
                                "did_woba": _r(ctrl["did"]), "t_cr1_game": _r(ctrl["t"], 4)},
            "criteria": crit, "p_holm": cand["p_two_sided"]}
        pv[k] = cand["p_two_sided"]
    h = holm(pv)
    for k in ARCH_MEMBERS:
        m = out["members"][k]
        m["resolved"] = bool(m.get("criteria") and all(m["criteria"].values()) and h[k]["reject"])
    out["holm"] = h
    return out


# ---------------------------------------------------------------------------
# IX-E: the postseasons, descriptive, intervals only
# ---------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.959964) -> tuple | None:
    if n <= 0:
        return None
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (c - hw, c + hw)


def _mean_ci(x) -> dict:
    x = np.asarray(x, dtype=float)
    n = int(x.size)
    if n < 2:
        return {"n": n, "mean": _r(x.mean()) if n else None, "ci95": None}
    m = float(x.mean())
    se = float(x.std(ddof=1)) / math.sqrt(n)
    return {"n": n, "mean": _r(m), "ci95": [_r(m - 1.959964 * se), _r(m + 1.959964 * se)]}


def final_score(plays) -> tuple | None:
    """(home runs, away runs) from a winProbability feed's last play."""
    if not plays:
        return None
    res = (plays[-1] or {}).get("result") or {}
    h, a = res.get("homeScore"), res.get("awayScore")
    if h is None or a is None:
        return None
    return int(h), int(a)


def regular_season_profile(games: list, agg: dict, params: dict) -> dict:
    """End-of-season Elo, run levels and team types of one completed regular season."""
    ratings = {o: ic.ELO_BASE for o in ORGS}
    tot = Counter()
    home_tot, home_n, club_tot, club_n = Counter(), Counter(), Counter(), Counter()
    acc = {o: Counter() for o in ORGS}
    for g in sorted(games, key=lambda g: (g["known_on"], g["date"], g["pk"])):
        h, a = g["home"], g["away"]
        p = ic.elo_win_prob(ratings[h], ratings[a], ic.ELO_HOME_POINTS)
        y = 1.0 if g["hr"] > g["ar"] else 0.0
        ratings[h] += ic.ELO_K * (y - p)
        ratings[a] -= ic.ELO_K * (y - p)
        t = g["hr"] + g["ar"]
        tot["runs"] += t
        tot["games"] += 1
        home_tot[h] += t
        home_n[h] += 1
        for c in (h, a):
            club_tot[c] += t
            club_n[c] += 1
        ga = agg.get(g["pk"]) or {}
        for half, fld, bat in (("top", h, a), ("bottom", a, h)):
            x = ga.get(half)
            if not x:
                continue
            for k in ("sp_bf", "sp_k", "sp_bb", "rp_bf", "rp_k", "rp_bb"):
                acc[fld][k] += x[k]
            for k in ("pa", "k", "hr"):
                acc[bat][k] += x[k]
        if ga:
            for c in (h, a):
                acc[c]["games"] += 1
    types = {o: _club_types(acc[o], 1) for o in ORGS}
    if agg:
        for o in ORGS:
            types[o]["best_reliever"] = None
    return {"elo": ratings, "league_rpg": (tot["runs"] / tot["games"]) if tot["games"] else None,
            "home_rpg": {o: home_tot[o] / home_n[o] for o in ORGS if home_n[o]},
            "club_rpg": {o: club_tot[o] / club_n[o] for o in ORGS if club_n[o]},
            "types": types}


def best_relievers(plays, games: list, min_bf: int) -> dict:
    """{club: the best (K - BB) / BF among its relievers with at least min_bf batters
    faced in relief}, from a completed season's plays."""
    if plays is None or len(plays) == 0:
        return {}
    side = {g["pk"]: (g["home"], g["away"]) for g in games}
    p = plays[plays["game_pk"].isin(list(side))].copy()
    p = p[p["half"].isin(("top", "bottom"))].sort_values(["game_pk", "half", "at_bat_index"],
                                                         kind="mergesort")
    first = p.dropna(subset=["pitcher_id"]).drop_duplicates(["game_pk", "half"])
    sp = {(int(r.game_pk), r.half): r.pitcher_id for r in first.itertuples(index=False)}
    p = p[p["event_type"].map(_is_pa)]
    acc: dict = defaultdict(Counter)
    for r in p.itertuples(index=False):
        if sp.get((int(r.game_pk), r.half)) == r.pitcher_id or r.pitcher_id != r.pitcher_id:
            continue
        h, a = side[int(r.game_pk)]
        club = h if r.half == "top" else a
        x = acc[(club, int(r.pitcher_id))]
        x["bf"] += 1
        if r.event_type in EVT_K:
            x["kbb"] += 1
        elif r.event_type in EVT_BB:
            x["kbb"] -= 1
    best: dict = {}
    for (club, _pid), x in acc.items():
        if x["bf"] >= min_bf:
            v = x["kbb"] / x["bf"]
            best[club] = max(best.get(club, -9.0), v)
    return best


def _slope_ci(resid, x, clusters) -> dict:
    """OLS slope of resid on x with an intercept; CR1 by series; a 95% interval from t
    with G - 1 degrees of freedom."""
    resid = np.asarray(resid, float)
    x = np.asarray(x, float)
    n = int(x.size)
    if n < 4 or float(np.std(x)) == 0:
        return {"n": n, "slope_per_sd": None, "ci95": None}
    sd = float(np.std(x))
    X = np.column_stack([np.ones(n), x / sd])
    beta = np.linalg.lstsq(X, resid, rcond=None)[0]
    e = resid - X @ beta
    V = cr1_ols(X, e, clusters)
    G = len(set(clusters))
    if V is None or V[1, 1] <= 0 or G < 2:
        return {"n": n, "slope_per_sd": _r(beta[1]), "ci95": None}
    from scipy import stats
    q = float(stats.t.ppf(0.975, G - 1))
    se = math.sqrt(V[1, 1])
    return {"n": n, "series": G, "slope_per_sd": _r(beta[1]),
            "ci95": [_r(beta[1] - q * se), _r(beta[1] + q * se)]}


def family_e(source, feats_games: dict, params: dict) -> dict:
    """IX-E: home win rate against the end-of-regular-season Elo price, totals against
    the clubs' regular-season run levels at the venue, and team types; postseasons
    2000-2019 and 2021-2025. Descriptive: intervals only, no verdict."""
    games, c = [], Counter()
    for s in POSTSEASONS_INT_B1 + POSTSEASONS_REGISTERED:
        s = _refuse_season(s)
        lst = source.postseason_games(s)
        if lst is None:
            c["seasons_without_game_list"] += 1
            continue
        reg = feats_games.get(s)
        if reg is None:
            fin = source.finals(s) if s >= 2018 else None
            reg = season_games(fin, s)[0] if fin else None
        prof = None
        if reg:
            plays = source.plays(s) if s >= 2018 else None
            agg = play_aggregates(plays, reg) if plays is not None else {}
            prof = regular_season_profile(reg, agg, params)
            if plays is not None:
                best = best_relievers(plays, reg, params["reliever_min_bf"])
                for o in ORGS:
                    prof["types"][o]["best_reliever"] = best.get(o)
        for g in lst:
            c["games"] += 1
            if g.get("home") not in ORG_DIV or g.get("away") not in ORG_DIV:
                c["null_club_unresolved"] += 1
                continue
            sc = final_score(source.postseason_feed(g["game_pk"]))
            if sc is None:
                c["null_no_feed_or_score"] += 1
                continue
            h, a = g["home"], g["away"]
            row = {"season": s, "frame": "registered" if s in POSTSEASONS_REGISTERED
                   else "int_b1", "round": g["game_type"], "home": h, "away": a,
                   "y": 1.0 if sc[0] > sc[1] else 0.0, "total": float(sc[0] + sc[1]),
                   "series": f"{s}-{g['game_type']}-{'-'.join(sorted((h, a)))}",
                   "p": None, "exp_total": None, "gaps": {}}
            if prof:
                row["p"] = ic.elo_win_prob(prof["elo"][h], prof["elo"][a], ic.ELO_HOME_POINTS)
                lg = prof["league_rpg"]
                if lg and h in prof["home_rpg"] and h in prof["club_rpg"] and a in prof["club_rpg"]:
                    v = prof["home_rpg"][h] / prof["club_rpg"][h]
                    row["exp_total"] = (prof["club_rpg"][h] + prof["club_rpg"][a]) / 2.0 * v
                for key in TYPE_MEMBERS + ("best_reliever",):
                    vals = {o: t.get(key) for o, t in prof["types"].items()
                            if t.get(key) is not None}
                    if len(vals) >= 2 and h in vals and a in vals:
                        arr = np.asarray(list(vals.values()), float)
                        sd = float(arr.std())
                        if sd > 0:
                            row["gaps"][key] = (vals[h] - vals[a]) / sd
            else:
                c["null_no_regular_season_source"] += 1
            games.append(row)

    def frame(rows):
        n = len(rows)
        k = int(sum(r["y"] for r in rows))
        wi = wilson(k, n)
        priced = [r for r in rows if r["p"] is not None]
        tot = [r for r in rows if r["exp_total"] is not None]
        out = {"games": n, "home_wins": k,
               "home_win_rate": _r(k / n) if n else None,
               "home_win_rate_wilson95": None if wi is None else [_r(wi[0]), _r(wi[1])],
               "home_minus_elo_price": _mean_ci([r["y"] - r["p"] for r in priced]),
               "total_minus_run_level": _mean_ci([r["total"] - r["exp_total"] for r in tot]),
               "types": {}}
        for key in TYPE_MEMBERS + ("best_reliever",):
            sub = [r for r in priced if key in r["gaps"]]
            out["types"][key] = _slope_ci([r["y"] - r["p"] for r in sub],
                                          [r["gaps"][key] for r in sub],
                                          [r["series"] for r in sub])
        out["by_round"] = {}
        for rd in POSTSEASON_TYPES:
            sub = [r for r in rows if r["round"] == rd]
            ww = wilson(int(sum(r["y"] for r in sub)), len(sub))
            out["by_round"][rd] = {
                "games": len(sub),
                "home_win_rate_wilson95": None if ww is None else [_r(ww[0]), _r(ww[1])],
                "home_minus_elo_price": _mean_ci([r["y"] - r["p"] for r in sub
                                                  if r["p"] is not None])}
        return out

    return {"descriptive": "intervals only; no verdict, no Holm, no pricing claim",
            "counts": dict(c),
            "frames": {"registered_2018_2025": frame([r for r in games
                                                      if r["frame"] == "registered"]),
                       "int_b1_2000_2017": frame([r for r in games if r["frame"] == "int_b1"]),
                       "all": frame(games)},
            "team_defense": "excluded until the 5g look is recorded (the secret-sauce "
                            "defense leg waits)"}


# ---------------------------------------------------------------------------
# The run, the counts, the artifact
# ---------------------------------------------------------------------------
def write_artifact(art: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(art, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _clubs_all(feats: dict) -> dict:
    out = {}
    for s, f in feats.items():
        for D, clubs in (f.get("clubs") or {}).items():
            out[D] = clubs
    return out


def counts_report(feats: dict, source=None, include_postseason: bool = True) -> dict:
    """Counts only: integers and labels, never a statistic or an outcome."""
    out = {"mode": "counts", "seasons": {}}
    for s, f in feats.items():
        rows = f["rows"]
        kept, drops = scored_rows({s: f}, [s])
        focus = Counter()
        months = Counter()
        for r in kept:
            months[str(r["month"])] += 1
            if abs(r["ds"]) >= ic.FOCUS_THRESHOLD:
                focus[str(r["month"])] += 1
        out["seasons"][str(s)] = {
            "finals_and_features": {k: int(v) for k, v in f["counts"].items()},
            "row_rule_drops": {k: int(v) for k, v in drops.items()},
            "scored_games": len(kept), "featurized_games": len(rows),
            "A_null": sum(1 for r in kept if r["A"] is None),
            "games_by_month": {m: int(months.get(m, 0)) for m in map(str, range(3, 11))},
            "focus_games_by_month": {m: int(focus.get(m, 0)) for m in map(str, range(3, 11))},
            "focus_games": int(sum(focus.values())),
        }
    if include_postseason and source is not None:
        ps = Counter()
        for s in POSTSEASONS_INT_B1 + POSTSEASONS_REGISTERED:
            lst = source.postseason_games(s)
            if lst is None:
                ps["seasons_without_game_list"] += 1
                continue
            for g in lst:
                ps["games"] += 1
                ps["feed_present" if source.postseason_feed(g["game_pk"]) else "feed_missing"] += 1
        out["postseason"] = dict(ps)
    return out


def run_stage1(source, out_path: Path, *, mode: str, params: dict, clock: dict | None = None,
               workers: int = 1, archive_dir: Path | None = None, log=print) -> dict:
    """Features, then the first write, then every family, then the complete write."""
    g_ref = ic.G_REF
    art = {"section": SECTION_TITLE, "construction": ic.CONSTRUCTION,
           "lab": "tools/intensity_lab.py", "lab_version": LAB_VERSION,
           "registry_row": REGISTRY_ROW, "g_ref": g_ref, "g_ref_record": dict(G_REF_RECORD),
           "stage1": {"status": "featurizing", "mode": mode, "clock": clock,
                      "params": dict(params), "started_at": _now(),
                      "inputs": source.describe(), "pinned_choices": list(PINNED_CHOICES),
                      "seasons": list(SEASONS), "fit_seasons": list(FIT_SEASONS),
                      "graded_seasons": list(GRADE_SEASONS)}}
    st = art["stage1"]
    feats = build_features(source, params, g_ref=g_ref, workers=workers,
                           archive_dir=archive_dir, log=log)
    fit_rows, fit_drops = scored_rows(feats, FIT_SEASONS)
    grade_rows, grade_drops = scored_rows(feats, GRADE_SEASONS)
    all_rows, all_drops = scored_rows(feats, SEASONS)
    st["counts"] = counts_report(feats, None, include_postseason=False)
    st["counts"]["fit_games"] = len(fit_rows)
    st["counts"]["graded_games"] = len(grade_rows)
    st["counts"]["panel_games"] = len(all_rows)
    st["status"] = "scoring"
    write_artifact(art, out_path)              # the first write: before any family
    try:
        outcomes = outcomes_of(feats)
        draws = int(params["twin_draws"])
        clubs = _clubs_all(feats)
        fam = {}
        fam["IX-ML"] = family_ml(fit_rows, grade_rows, outcomes, g_ref, draws=draws)
        fam["IX-TOT"] = family_tot(all_rows, outcomes, g_ref, draws=draws)
        fam["IX-TYPE"] = family_type(fit_rows, grade_rows, outcomes, clubs, draws=draws)
        fam["IX-ARCH"] = family_arch(feats, source, all_rows, params, draws=draws)
        st["IX-E"] = family_e(source, {s: f["games"] for s, f in feats.items()}, params)
        st["families"] = fam
        st["resolved"] = sorted(
            [k for k in ("IX-A", "IX-A2") if fam["IX-ML"].get(k, {}).get("resolved")]
            + (["IX-B"] if fam["IX-TOT"].get("IX-B", {}).get("resolved") else [])
            + [f"IX-TYPE {k}" for k, v in fam["IX-TYPE"]["members"].items() if v.get("resolved")]
            + [f"IX-ARCH {k}" for k, v in fam["IX-ARCH"]["members"].items()
               if v.get("resolved")])
        st["status"] = "complete"
        st["completed_at"] = _now()
        write_artifact(art, out_path)          # every block on disk before any is printed
        return art
    except Exception as exc:                   # noqa: BLE001 - the crash protocol
        st["status"] = "crashed"
        st["crash"] = {"error": repr(exc), "traceback": traceback.format_exc()[-4000:]}
        st["protocol"] = "stopped after the first write: never rerun; the question goes to the owner"
        try:
            write_artifact(art, out_path)
        except Exception:                      # noqa: BLE001 - the original error wins
            pass
        raise


def result_heading(art: dict) -> str:
    st = art["stage1"]
    run = ((st.get("clock") or {}).get("today") or str(st.get("completed_at", ""))[:10])
    res = st.get("resolved") or []
    what = ("no member resolved" if not res else "resolved: " + ", ".join(res))
    return f"### Stage 1 result (run {run}, once): {what}"


def result_text(art: dict) -> str:
    st = art["stage1"]
    fam = st["families"]
    a = fam["IX-ML"].get("IX-A", {})
    a2 = fam["IX-ML"].get("IX-A2", {})
    b = fam["IX-TOT"].get("IX-B", {})

    def f(x):
        return "none" if x is None else f"{x}"

    lines = [
        result_heading(art), "",
        "Written by tools/intensity_lab.py into data/game_intensity_eval.json. "
        f"IX-A: b {f(a.get('b'))}, focus games {f(a.get('focus_games'))}, focus Brier t "
        f"{f((a.get('criterion_1_focus_brier') or {}).get('t'))}. IX-A2: c {f(a2.get('c'))}. "
        f"IX-B: beta {f(b.get('beta'))} runs per unit S, CR1 t {f(b.get('t_cr1_date'))}. "
        "IX-TYPE and IX-ARCH members and the IX-E intervals are in the artifact. "
        "Stage 1 licenses no price; IX-E is descriptive.",
    ]
    return "\n".join(lines)


def append_result(doc_path: Path, art: dict) -> None:
    """Append the result under the section, before the rule that closes it. Keeps the
    file's own line endings; refuses when a stage-1 heading is already there."""
    doc_path = Path(doc_path)
    raw = doc_path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    sec = section_text(text)
    if STAGE1_HEADING_RE.search(sec):
        raise LabRefused("refused: the section already carries a stage-1 result")
    start = text.index(sec)
    end = start + len(sec)
    body = sec.rstrip("\n")
    closing = ""
    if body.endswith("\n---"):
        body, closing = body[:-4].rstrip("\n"), "\n---"
    new_sec = body + "\n\n" + result_text(art) + "\n" + closing + "\n\n\n"
    out = text[:start] + new_sec + text[end:].lstrip("\n")
    if crlf:
        out = out.replace("\n", "\r\n")
    doc_path.write_bytes(out.encode("utf-8"))


# ---------------------------------------------------------------------------
# The synthetic fixture (the dry run and the tests)
# ---------------------------------------------------------------------------
FIXTURE_WEIGHTS = {"ubb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.58, "hr": 2.03}
FIXTURE_PARAMS = {**REGISTERED_PARAMS, "n_sims": 24, "arch_min_pa": 60, "arch_min_bf": 40,
                  "reliever_min_bf": 10}
FIXTURE_POSTSEASONS = (2005, 2019, 2023)


def _fixture_dates(season: int) -> list:
    """Twenty dates from 1 April every third day, then ten from 1 July: no June game
    (the empty focus month), and types live from the 21st date on."""
    d0 = _dt.date(season, 4, 1)
    out = [d0 + _dt.timedelta(days=3 * k) for k in range(20)]
    j0 = _dt.date(season, 7, 1)
    out += [j0 + _dt.timedelta(days=3 * k) for k in range(10)]
    return [d.isoformat() for d in out]


def synthetic_fixture(seed: int = 11) -> FixtureSource:
    """Seven fixture seasons on the thirty-club field (450 games each), corpus-shaped
    plays, three postseasons. Nulls on purpose: one unannounced probable, one game
    against a club outside the field (no Elo), one shortened game, one resumed game per
    season; no June game; 2018 and 2021 have no prior-season archetype source; one
    postseason game has no feed and 2005 has no regular-season finals."""
    import pandas as pd

    rng = np.random.default_rng(seed)
    finals, plays_by, post, feeds = {}, {}, {}, {}
    pk = 700000
    idx = {o: i for i, o in enumerate(ORGS)}
    events = ("strikeout", "walk", "single", "double", "triple", "home_run", "field_out",
              "hit_by_pitch", "grounded_into_double_play", "sac_fly", "intent_walk")
    base_p = np.asarray([0.22, 0.08, 0.15, 0.045, 0.005, 0.03, 0.40, 0.01, 0.02, 0.01, 0.01])
    base_p = base_p / base_p.sum()
    traj_of = {"single": ("ground_ball", "line_drive"), "double": ("line_drive", "fly_ball"),
               "triple": ("fly_ball",), "home_run": ("fly_ball", "line_drive"),
               "field_out": ("ground_ball", "fly_ball", "popup", "line_drive"),
               "grounded_into_double_play": ("ground_ball",), "sac_fly": ("fly_ball",)}
    for season in SEASONS:
        talent = {o: float(np.clip(rng.normal(0.5, 0.06), 0.35, 0.65)) for o in ORGS}
        kskill = {o: float(rng.normal(0, 0.04)) for o in ORGS}
        rows, plays = [], []
        games_played = Counter()
        multi = {}
        dates = _fixture_dates(season)
        for di, D in enumerate(dates):
            order = list(rng.permutation(len(ORGS)))
            for j in range(0, len(ORGS), 2):
                h, a = ORGS[order[j]], ORGS[order[j + 1]]
                if rng.random() < 0.5:
                    h, a = a, h
                pk += 1
                ph = ic.p_home_game(talent[h], talent[a])
                hw = rng.random() < ph
                win_r = 1 + int(rng.poisson(4.0))
                lose_r = min(int(rng.poisson(3.5)), win_r - 1)
                hr_, ar_ = (win_r, lose_r) if hw else (lose_r, win_r)
                sp = {}
                for c in (h, a):
                    sp[c] = 600000 + idx[c] * 10 + games_played[c] % 5
                    games_played[c] += 1
                row = {"game_pk": pk, "season": str(season), "date": D, "home_org": h,
                       "away_org": a, "home_runs": hr_, "away_runs": ar_, "innings": 9,
                       "home_sp": sp[h], "away_sp": sp[a]}
                if di == 5 and j == 0:
                    row["home_sp"] = None                       # an unannounced probable
                if di == 8 and j == 2:
                    row["innings"] = 7                          # a shortened game
                if di == 10 and j == 4:
                    multi[str(pk)] = [D, dates[di + 1]]         # a resumed game
                rows.append(row)
                for half, fld, bat in (("top", h, a), ("bottom", a, h)):
                    starter = sp[fld]
                    for n_pa in range(18):
                        pitcher = starter if n_pa < 12 else 700000 + idx[fld] * 10 + n_pa % 3
                        batter = 500000 + idx[bat] * 100 + n_pa % 9
                        pr = base_p.copy()
                        pr[0] = max(0.05, pr[0] + kskill[fld] - kskill[bat] / 2)
                        pr = pr / pr.sum()
                        et = events[int(rng.choice(len(events), p=pr))]
                        tr = traj_of.get(et)
                        plays.append({
                            "game_pk": pk, "half": half, "at_bat_index": len(plays),
                            "batter_id": batter, "pitcher_id": pitcher,
                            "bat_side": "L" if (batter % 2) else "R",
                            "pitch_hand": "R" if (pitcher % 2 == 0) else "L",
                            "event_type": et,
                            "trajectory": None if tr is None else tr[int(rng.integers(len(tr)))]})
            if di == 12:                                        # a game with no Elo
                pk += 1
                rows.append({"game_pk": pk, "season": str(season), "date": D,
                             "home_org": "NYY", "away_org": "XXX", "home_runs": 3,
                             "away_runs": 2, "innings": 9, "home_sp": None, "away_sp": None})
        finals[season] = {"rows": rows, "multi": multi, "fetched_at": "fixture"}
        plays_by[season] = pd.DataFrame(plays)
    for season in FIXTURE_POSTSEASONS:
        lst = []
        clubs = list(ORGS[:8])
        for k in range(12):
            pk += 1
            h, a = clubs[k % 8], clubs[(k + 3) % 8]
            gt = POSTSEASON_TYPES[min(k // 4, 3)]
            lst.append({"game_pk": pk, "game_type": gt, "date": f"{season}-10-{10 + k:02d}",
                        "home": h, "away": a})
            if k == 7 and season == 2019:
                continue                                         # a game with no feed
            hs, as_ = int(rng.integers(0, 9)), int(rng.integers(0, 9))
            if hs == as_:
                hs += 1
            feeds[pk] = [{"result": {"homeScore": 0, "awayScore": 0}},
                         {"result": {"homeScore": hs, "awayScore": as_}}]
        post[season] = lst
    weights = {s: dict(FIXTURE_WEIGHTS) for s in SEASONS}
    return FixtureSource(finals, plays_by, weights, post, feeds)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class _Tee:
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, s):
        self.stream.write(s)
        self.fh.write(s)
        self.fh.flush()
        return len(s)

    def flush(self):
        self.stream.flush()
        self.fh.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="THE RUN, once")
    mode.add_argument("--dry-run", action="store_true",
                      help="the reporting path on the synthetic fixture")
    mode.add_argument("--counts", action="store_true", help="counts only, no statistic")
    mode.add_argument("--g-ref", action="store_true",
                      help="recompute G_REF from the registered synthetic league")
    ap.add_argument("--fixture", action="store_true", help="counts: on the fixture")
    ap.add_argument("--out", type=Path, help="dry run or counts: an output path (not data/)")
    ap.add_argument("--tee", type=Path, help="copy stdout and stderr to this file first")
    ap.add_argument("--workers", type=int, default=1, help="processes for the stakes walk")
    args = ap.parse_args(argv)
    fh = None
    saved = sys.stdout, sys.stderr
    if args.tee:
        args.tee.parent.mkdir(parents=True, exist_ok=True)
        fh = open(args.tee, "a", encoding="utf-8")
        sys.stdout, sys.stderr = _Tee(sys.stdout, fh), _Tee(sys.stderr, fh)
    try:
        if args.g_ref:
            print(json.dumps(compute_g_ref(), indent=1))
            return 0
        if args.dry_run:
            if args.out is None:
                ap.error("--dry-run needs --out")
            out = check_out_path(args.out)
            art = run_stage1(synthetic_fixture(), out, mode="dry_run_fixture",
                             params=dict(FIXTURE_PARAMS))
            print(result_text(art))
            return 0
        if args.counts:
            src = synthetic_fixture() if args.fixture else CacheSource()
            params = dict(FIXTURE_PARAMS if args.fixture else REGISTERED_PARAMS)
            feats = build_features(src, params, workers=args.workers,
                                   archive_dir=None if args.fixture else ARCHIVE_DIR)
            rep = counts_report(feats, src)
            text = json.dumps(rep, indent=1)
            if args.out is not None:
                p = check_out_path(args.out)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0
        clock = check_clock()
        check_one_run(ARTIFACT)
        params = dict(REGISTERED_PARAMS)
        check_params(params)
        art = run_stage1(CacheSource(), ARTIFACT, mode="run", params=params, clock=clock,
                         workers=args.workers, archive_dir=ARCHIVE_DIR)
        append_result(GATE_DOC, art)
        print(result_text(art))
        print(f"next: the run commit sets {REGISTRY_ROW} from unvalidated with "
              "eval_artifact data/game_intensity_eval.json")
        return 0
    except LabRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if fh is not None:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout, sys.stderr = saved
            fh.close()


if __name__ == "__main__":
    sys.exit(main())
