# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The starter-workload stage-1 lab: expected outs and pitches per start, read once on pre-2026 corpus starts.

Registration: docs/diamond-betting.md, the section "Starter workload: expected outs and
pitches per start" (pre-registered 2026-09-30, plan candidate N6(d), owner ask 16). This
file is stage 1 of that section and nothing else: a workload estimand (the starter's own
outs, then his own pitches) on `.cache/pbp_corpus` seasons 2018, 2019 and 2021 to 2025.
Built 2026-10-08 (task Q10_04a, checklist PM-08) and tested on fixtures only; no real
corpus row has been read by it. The one run is a separate task.

Modes:
  python -u tools/starter_workload_lab.py --run [--tee PATH]
      THE RUN. Once. Refused before 2026-10-11 (the owner's PM-Q3 answer), on a
      registered look day, without a step Z entry in part 9 of the fWAR label epoch gate,
      when data/starter_workload_eval.json exists, and when the section already carries a
      "### Stage 1 result" heading. Writes data/starter_workload_eval.json in three steps
      (the frozen burn-in priors, then the floor, then the result), so the floor is on
      disk before any 2024 row is read, then appends the result heading to the section.
  python tools/starter_workload_lab.py --dry-run --out PATH
      The whole reporting path on the built-in synthetic fixture with nulls (a probable
      with no prior start, an opener, no 2024 season). Refuses a path under data/.

What is registered and is not a choice here: the candidate (budget, ppo, the opposing
lineup ratio r_L, xouts = min(27, budget / (ppo x r_L))), the comparators A0, C1, D1 and
D2, the prior grids k_b {2, 4, 8, 16, 32}, k_o {15, 30, 60, 120, 240}, k_l {100, 300,
1000, 3000} and k_c on the k_b grid, chosen by outs MAE on the 2019 starts with ties to
the smallest priors in the order listed; the 365-day and 30-day windows; the anchors from
the prior complete corpus season, pooled sum over sum; the floor (1 percent of A0's outs
MAE on 2021 to 2023); the game-clustered bootstrap (B 2000, seed 20260930, the lower
bound the 5th percentile); the four PASS criteria; the attribution family T1 and T2
(Holm, m = 2, one-sided 0.05: the smaller p at 0.025, the larger at 0.05).

What it never reads: a 2026 game (as a scored row or as history); the third-time-through
batters-faced column, the rest-days column or any management column, board, ledger or
module; a vintage record, a price, a market capture or any betting artifact. Its quantities
are named budget, ppo and xouts, never by the dark capture's column names. It relates
nothing to a game result, a price, an edge, a slot or a ledger row.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
import sys
import traceback
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
ARTIFACT = DATA / "starter_workload_eval.json"
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
CACHE = ROOT / ".cache"
CORPUS_DIR = CACHE / "pbp_corpus"
WIN_PROB_DIR = CACHE / "win_prob"
WIN_PROB_INDEX = CACHE / "mlbstats_games" / "win_prob_index.json"
WAR_BAT = CACHE / "war_daily" / "bat.parquet"

SECTION_TITLE = "Starter workload: expected outs and pitches per start"
REGISTRY_ROW = "starter_workload_xouts"
STAGE1_HEADING_RE = re.compile(r"^### Stage 1 result\b", re.M)

# ---------------------------------------------------------------------------
# Registered constants (the section's own numbers; pinned by the tests)
# ---------------------------------------------------------------------------
GRID_KB = (2, 4, 8, 16, 32)            # starts
GRID_KO = (15, 30, 60, 120, 240)       # outs
GRID_KL = (100, 300, 1000, 3000)       # plate appearances
GRID_KC = GRID_KB                      # C1 takes its prior from the k_b grid
WINDOW_DAYS = 365                      # the starter's own trailing window
LINEUP_DAYS = 30                       # the opposing club's trailing hitting line
OUTS_CAP = 27
A0_CLIP_IP = (2.0, 7.5)                # the served props clip
A0_FALLBACK_IP = 5.2                   # the served float, 15.6 outs
OPENER_OUTS = 6.0                      # a trailing 365-day mean under 6 outs per start
FLOOR_SHARE = 0.01                     # 1 percent of A0's outs MAE on 2021 to 2023
BOOT_B = 2000
BOOT_SEED = 20260930
LB_PERCENTILE = 5.0
HOLM_ALPHAS = (0.025, 0.05)            # m = 2, family alpha 0.05 one-sided
TIE_DECIMALS = 9                       # MAEs equal to 9 decimals are a tie

SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
BURN_IN_HISTORY = (2018,)              # history and anchors only, never scored
BURN_IN_SCORED = (2019,)               # the burn-in scores the 2019 starts
FLOOR_SEASONS = (2021, 2022, 2023)
SCORED_SEASONS = (2024, 2025)
FIRST_REFUSED_SEASON = 2026
FIRST_REFUSED_DATE = "2026-01-01"
#: The 2020 regular season, absent from the corpus. A 2021 start whose 365-day window
#: begins on or before its last day "reaches into the absent 2020 season".
ABSENT_2020 = (_dt.date(2020, 7, 23), _dt.date(2020, 9, 27))

#: The 2025 corpus parity the section disclosed (4,860 starts, 85.0 pitches per start).
#: Checked after the floor is written and before any 2024 or 2025 start is scored.
PARITY_2025 = {"starts": 4860, "pitches_per_start": 85.0}

EARLIEST_RUN = _dt.date(2026, 10, 11)
#: Registered look days of other gates (docs/*GATE*.md, plan Part 8 8.B, Part 9): the lab
#: never runs on one. The run task checks the gate documents again before it starts.
BLOCKED_DAYS = tuple(_dt.date.fromisoformat(d) for d in (
    "2026-10-05", "2026-10-07", "2026-10-21", "2026-10-23", "2026-10-28", "2026-11-06",
    "2026-11-13", "2026-11-20", "2026-11-24", "2026-11-25", "2026-12-01", "2026-12-03",
    "2026-12-08", "2026-12-10", "2027-01-12"))

VERDICTS = ("PASS", "FAIL", "PASS-BELOW-FLOOR")
ARMS_OUTS = ("a0", "candidate", "d1", "d2", "c1")
ARMS_PITCHES = ("budget", "season_mean")
WORDING_NO_T2 = "starts-only length over a 365-day window"
WORDING_NO_T1 = "nothing credits the opposing lineup's P/PA"

PLAY_COLS = ("game_pk", "season", "half", "at_bat_index", "batter_id", "pitcher_id",
             "event_type", "outs_before", "outs_after")
PITCH_COLS = ("game_pk", "season", "at_bat_index", "is_pitch")
WAR_COLS = ("mlb_ID", "year_ID", "team_ID", "PA")


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


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


# ---------------------------------------------------------------------------
# Guards: the clock, the one run, the section
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


def check_clock(today: _dt.date | None = None, epoch_text: str | None = None) -> dict:
    """Refuse before 2026-10-11, on a registered look day, and inside the epoch's gap."""
    today = today or _dt.date.today()
    z = step_z_entry(epoch_text)
    if z is None:
        raise LabRefused("refused: part 9 of FWAR_LABEL_EPOCH_GATE.md records no step Z "
                         "entry; nothing runs between the epoch's step A and step Z")
    if today in BLOCKED_DAYS:
        raise LabRefused(f"refused: {today} is another gate's registered look day")
    if today < EARLIEST_RUN:
        raise LabRefused(f"refused: today {today} is before the registered earliest run "
                         f"{EARLIEST_RUN} (the owner's PM-Q3 answer)")
    return {"today": today.isoformat(), "earliest_run": EARLIEST_RUN.isoformat(),
            "step_z_entry": z}


def section_text(doc_text: str | None = None) -> str:
    """The section's text, from its level-2 heading to the next level-2 heading."""
    if doc_text is None:
        doc_text = GATE_DOC.read_text(encoding="utf-8")
    text = doc_text.replace("\r\n", "\n")
    hits = list(re.finditer(r"^## [^\n]*" + re.escape(SECTION_TITLE) + r"[^\n]*$", text,
                            flags=re.M))
    if len(hits) != 1:
        raise LabRefused(f"refused: expected one section titled {SECTION_TITLE!r} in "
                         f"docs/diamond-betting.md, found {len(hits)}")
    start = hits[0].start()
    nxt = re.search(r"^## ", text[hits[0].end():], flags=re.M)
    return text[start:] if nxt is None else text[start:hits[0].end() + nxt.start()]


def check_one_run(artifact_path: Path = ARTIFACT, doc_text: str | None = None) -> None:
    """The one-run guard reads both the artifact and the section's results block."""
    p = Path(artifact_path)
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise LabRefused(f"refused: {p.name} exists and does not parse; stage 1 runs "
                             "once and a broken artifact is a question for the owner")
        if isinstance(doc, dict) and "stage1" in doc:
            raise LabRefused(f"refused: {p.name} already holds a stage-1 block "
                             f"(status {doc['stage1'].get('status')!r}); stage 1 runs once")
        raise LabRefused(f"refused: {p.name} exists; stage 1 runs once")
    if STAGE1_HEADING_RE.search(section_text(doc_text)):
        raise LabRefused("refused: the section already carries a '### Stage 1 result' "
                         "heading; stage 1 runs once")


def check_out_path(out: Path) -> Path:
    """A dry run never writes under data/."""
    out = Path(out).resolve()
    try:
        out.relative_to(DATA.resolve())
    except ValueError:
        return out
    raise LabRefused(f"refused: a dry run writes nothing under data/ ({out})")


# ---------------------------------------------------------------------------
# Sources: the corpus (the run) and a fixture (tests and the dry run)
# ---------------------------------------------------------------------------
def _refuse_season(season) -> int:
    s = int(season)
    if s >= FIRST_REFUSED_SEASON:
        raise LabRefused(f"refused: season {s}; stage 1 never reads a 2026 game, neither as "
                         "a scored row nor as history")
    if s not in SEASONS:
        raise LabRefused(f"refused: season {s} is not a registered stage-1 season {SEASONS}")
    return s


class CorpusSource:
    """`.cache/pbp_corpus` plays and pitches, dates off the payload index, clubs off the
    daily WAR frame's batter-club plate appearances. Reads named columns only."""

    kind = "corpus"

    def __init__(self, corpus_dir: Path = CORPUS_DIR, win_prob_index: Path = WIN_PROB_INDEX,
                 win_prob_dir: Path = WIN_PROB_DIR, war_bat: Path = WAR_BAT):
        self.corpus_dir = Path(corpus_dir)
        self.win_prob_index = Path(win_prob_index)
        self.win_prob_dir = Path(win_prob_dir)
        self.war_bat = Path(war_bat)
        self._dates = None
        self._war = None

    def _path(self, table: str, season: int) -> Path:
        return self.corpus_dir / table / str(season) / f"{table}-{season}.parquet"

    def manifest(self) -> dict:
        try:
            return json.loads((self.corpus_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def check_seasons(self, seasons) -> dict:
        man = self.manifest().get("seasons") or {}
        out = {}
        for s in seasons:
            s = _refuse_season(s)
            row = man.get(str(s)) or {}
            if not row.get("complete"):
                raise LabRefused(f"refused: the corpus manifest does not mark {s} complete")
            for t in ("plays", "pitches"):
                if not self._path(t, s).exists():
                    raise LabRefused(f"refused: {t}-{s}.parquet is missing")
            out[str(s)] = {"games": row.get("games"), "complete": True}
        return out

    def has(self, season: int) -> bool:
        return self._path("plays", int(season)).exists()

    def preflight(self, seasons) -> dict:
        """Schemas and file presence only, no value: the named columns exist in every
        season's tables and in the daily WAR frame, and the payload index parses."""
        import pyarrow.parquet as pq
        need = {"plays": PLAY_COLS, "pitches": PITCH_COLS}
        for s in seasons:
            s = _refuse_season(s)
            for t, cols in need.items():
                names = set(pq.read_schema(self._path(t, s)).names)
                miss = [c for c in cols if c not in names]
                if miss:
                    raise LabRefused(f"refused: {t}-{s}.parquet lacks columns {miss}")
        names = set(pq.read_schema(self.war_bat).names)
        miss = [c for c in WAR_COLS if c not in names]
        if miss:
            raise LabRefused(f"refused: the daily WAR frame lacks columns {miss}")
        if not self.win_prob_index.exists():
            raise LabRefused("refused: the payload index is missing")
        return {"schemas": "ok", "seasons": [int(s) for s in seasons]}

    def tables(self, season: int):
        import pandas as pd
        s = _refuse_season(season)
        plays = pd.read_parquet(self._path("plays", s), columns=list(PLAY_COLS))
        pitches = pd.read_parquet(self._path("pitches", s), columns=list(PITCH_COLS))
        return plays, pitches

    def dates(self, pks) -> dict:
        from mlbstats_games import game_date, sniff_start
        if self._dates is None:
            self._dates = {}
            try:
                idx = json.loads(self.win_prob_index.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                idx = {}
            for name, v in (idx.get("files") or {}).items():
                try:
                    pk = int(Path(name).stem)
                except ValueError:
                    continue
                # only the registered seasons' start times are kept
                if (isinstance(v, list) and len(v) >= 4 and v[3]
                        and v[2] in SEASONS):
                    self._dates[pk] = game_date(v[3])
        out = {}
        for pk in pks:
            pk = int(pk)
            d = self._dates.get(pk)
            if d is None:
                f = self.win_prob_dir / f"{pk}.json"
                if f.exists():
                    _s, st = sniff_start(f)
                    d = game_date(st)
            out[pk] = d
        return out

    def weights(self, season: int):
        import pandas as pd
        if self._war is None:
            self._war = pd.read_parquet(self.war_bat, columns=list(WAR_COLS))
        return self._war[self._war["year_ID"] == int(season)]

    def describe(self) -> dict:
        man = self.manifest()
        return {"source": "corpus", "corpus_built_at": man.get("built_at"),
                "corpus_schema_version": man.get("schema_version"),
                "dates": "first play startTime on the US Eastern calendar "
                         "(.cache/mlbstats_games/win_prob_index.json, a head sniff of the "
                         "payload when the index lacks the game)",
                "clubs": "the modal club of each half's batters, weighted by each batter's "
                         "plate-appearance share per club that season (.cache/war_daily/"
                         "bat.parquet), through trades.canonical_org",
                "game_type": "the corpus is built from the payload cache, which the "
                             "season walk fills with gameType R games",
                "pitch_attribution": "a pitch belongs to the pitcher of its play "
                                     "(matchup), the rule of the disclosed parity read"}


class FixtureSource:
    """In-memory tables in the corpus's own shape, for tests and the dry run."""

    kind = "fixture"

    def __init__(self, tables: dict, dates: dict, weights, on_tables=None):
        self._tables = tables          # season -> (plays, pitches)
        self._dates = {int(k): v for k, v in dates.items()}
        self._weights = weights
        self.on_tables = on_tables
        self.requested = []

    def check_seasons(self, seasons) -> dict:
        for s in seasons:
            _refuse_season(s)
        return {str(s): {"games": None, "complete": self.has(s)} for s in seasons}

    def has(self, season: int) -> bool:
        return int(season) in self._tables

    def tables(self, season: int):
        s = _refuse_season(season)
        self.requested.append(s)
        if self.on_tables is not None:
            self.on_tables(s)
        return self._tables[s]

    def dates(self, pks) -> dict:
        return {int(pk): self._dates.get(int(pk)) for pk in pks}

    def weights(self, season: int):
        return self._weights[self._weights["year_ID"] == int(season)]

    def describe(self) -> dict:
        return {"source": "fixture"}


# ---------------------------------------------------------------------------
# Extraction: corpus-shaped tables to per-game records
# ---------------------------------------------------------------------------
def club_map(plays, weights, season: int) -> tuple[dict, dict]:
    """{game_pk: (home, away)}: each half's batters vote for their clubs, weighted by
    their plate-appearance share per club that season; the bottom half bats home. A game
    whose halves vote for one club, or that has a half with no vote, is unresolved."""
    import pandas as pd
    from trades import canonical_org

    w = weights.loc[:, list(WAR_COLS)].dropna(subset=["mlb_ID", "team_ID"]).copy()
    w = w[w["team_ID"].astype(str) != "TOT"]
    w["club"] = w["team_ID"].astype(str).map(canonical_org)
    w["mlb_ID"] = w["mlb_ID"].astype("int64")
    w["PA"] = pd.to_numeric(w["PA"], errors="coerce").fillna(0.0)
    g = w.groupby(["mlb_ID", "club"], as_index=False)["PA"].sum()
    tot = g.groupby("mlb_ID")["PA"].transform("sum")
    g["w"] = (g["PA"] / tot).where(tot > 0, 0.0)
    pl = plays.loc[:, ["game_pk", "half", "batter_id"]].dropna().copy()
    pl["batter_id"] = pl["batter_id"].astype("int64")
    j = pl.merge(g, left_on="batter_id", right_on="mlb_ID", how="inner")
    votes = j.groupby(["game_pk", "half", "club"], as_index=False)["w"].sum()
    votes = votes.sort_values(["game_pk", "half", "w", "club"],
                              ascending=[True, True, False, True], kind="mergesort")
    votes = votes.drop_duplicates(["game_pk", "half"])
    top = dict(zip(votes.loc[votes["half"] == "top", "game_pk"],
                   votes.loc[votes["half"] == "top", "club"]))
    bot = dict(zip(votes.loc[votes["half"] == "bottom", "game_pk"],
                   votes.loc[votes["half"] == "bottom", "club"]))
    out, n_games, n_ok = {}, 0, 0
    for pk in sorted(set(int(x) for x in plays["game_pk"].dropna().unique())):
        n_games += 1
        home, away = bot.get(pk), top.get(pk)
        if isinstance(home, str) and isinstance(away, str) and home != away:
            out[pk] = (home, away)
            n_ok += 1
    return out, {"season": int(season), "games": n_games, "resolved": n_ok}


def games_from_tables(plays, pitches, dates: dict, clubs: dict, season: int) -> tuple:
    """(games, counters). A game record holds its date, its clubs, the first pitcher of
    each fielding half, every pitcher's outs and pitches by half, and each batting half's
    pitches seen and plate appearances. Outs on a play are outs_after minus outs_before;
    a pitch belongs to the pitcher of its play."""
    import pandas as pd
    from mlbstats_games import is_pa_event

    c = Counter()
    p = plays.loc[:, ["game_pk", "half", "at_bat_index", "pitcher_id", "event_type",
                      "outs_before", "outs_after"]].copy()
    if "season" in plays.columns:
        bad = plays["season"].dropna().astype(int)
        if (bad >= FIRST_REFUSED_SEASON).any():
            raise LabRefused("refused: a play row carries a 2026 season")
        c["play_rows_other_season"] = int((bad != int(season)).sum())
        p = p[plays["season"].astype("float64") == float(season)]
    pt = pitches
    if "is_pitch" in pt.columns:
        pt = pt[pt["is_pitch"].fillna(False).astype(bool)]
    npc = pt.groupby(["game_pk", "at_bat_index"]).size().rename("np")
    p = p.join(npc, on=["game_pk", "at_bat_index"])
    p["np"] = p["np"].fillna(0).astype("int64")
    ob = pd.to_numeric(p["outs_before"], errors="coerce").astype("float64").fillna(0.0)
    oa = pd.to_numeric(p["outs_after"], errors="coerce").astype("float64")
    oa = oa.where(oa.notna(), ob)
    p["outs"] = (oa - ob).clip(lower=0).astype("int64")
    # a missing event type is no plate appearance (str(NaN) would read as one)
    p["pa"] = p["event_type"].fillna("").map(is_pa_event).astype("int64")
    p = p[p["half"].isin(("top", "bottom"))]
    p = p.sort_values(["game_pk", "at_bat_index"], kind="mergesort")

    first = p.drop_duplicates(["game_pk", "half"])[["game_pk", "half", "pitcher_id"]]
    lines = (p.dropna(subset=["pitcher_id"])
             .groupby(["game_pk", "half", "pitcher_id"], as_index=False)
             .agg(outs=("outs", "sum"), pitches=("np", "sum")))
    bat = p.groupby(["game_pk", "half"], as_index=False).agg(pitches=("np", "sum"),
                                                             pa=("pa", "sum"))
    pks = sorted(set(int(x) for x in p["game_pk"].unique()))
    games = {}
    for pk in pks:
        d = dates.get(pk)
        if not d:
            c["games_without_date"] += 1
            continue
        if d >= FIRST_REFUSED_DATE:
            raise LabRefused(f"refused: game {pk} is dated {d}; stage 1 never reads a 2026 game")
        if d[:4] != str(int(season)):
            c["games_dated_outside_season"] += 1
            continue
        home, away = clubs.get(pk, (None, None))
        games[pk] = {"game_pk": pk, "season": int(season), "date": d,
                     "ord": _dt.date.fromisoformat(d).toordinal(),
                     "home": home, "away": away,
                     "starters": {}, "lines": {"top": {}, "bottom": {}},
                     "batting": {}}
    for r in first.itertuples(index=False):
        g = games.get(int(r.game_pk))
        if g is not None:
            g["starters"][r.half] = None if pd.isna(r.pitcher_id) else int(r.pitcher_id)
    for r in lines.itertuples(index=False):
        g = games.get(int(r.game_pk))
        if g is not None:
            g["lines"][r.half][int(r.pitcher_id)] = {"outs": int(r.outs),
                                                      "pitches": int(r.pitches)}
    for r in bat.itertuples(index=False):
        g = games.get(int(r.game_pk))
        if g is not None:
            g["batting"][r.half] = {"pitches": int(r.pitches), "pa": int(r.pa)}
    out = sorted(games.values(), key=lambda g: (g["ord"], g["game_pk"]))
    c["games"] = len(out)
    c["games_unresolved_clubs"] = sum(1 for g in out if not (g["home"] and g["away"]))
    c["halves_without_starter"] = sum(1 for g in out for h in ("top", "bottom")
                                      if g["starters"].get(h) is None)
    return out, dict(c)


def load_season(source, season: int) -> tuple[list, dict]:
    """One season's game records through every refusal: never 2026, never a 2026 date."""
    s = _refuse_season(season)
    plays, pitches = source.tables(s)
    pks = sorted(set(int(x) for x in plays["game_pk"].dropna().unique()))
    dates = source.dates(pks)
    clubs, club_counts = club_map(plays, source.weights(s), s)
    games, counts = games_from_tables(plays, pitches, dates, clubs, s)
    counts["clubs"] = club_counts
    return games, counts


def league_anchors(games: list) -> dict | None:
    """The prior complete season's league rates, pooled (sum over sum): pitches per
    start, pitches per out in starts, outs per start and pitches per plate appearance."""
    starts = sp = so = bp = bpa = 0
    season = None
    for g in games:
        season = g["season"]
        for h in ("top", "bottom"):
            pid = g["starters"].get(h)
            line = g["lines"][h].get(pid) if pid is not None else None
            if line is not None:
                starts += 1
                sp += line["pitches"]
                so += line["outs"]
            b = g["batting"].get(h)
            if b:
                bp += b["pitches"]
                bpa += b["pa"]
    if not starts or not so or not bpa:
        return None
    return {"season": season, "starts": starts, "L_pgs": sp / starts, "L_ppo": sp / so,
            "L_opg": so / starts, "L_ppa": bp / bpa}


def parity_read(games: list) -> dict:
    """Starts (first pitcher of each fielding half) and pitches per start, one season."""
    starts = pitches = 0
    for g in games:
        for h in ("top", "bottom"):
            pid = g["starters"].get(h)
            line = g["lines"][h].get(pid) if pid is not None else None
            if line is not None:
                starts += 1
                pitches += line["pitches"]
    return {"starts": starts,
            "pitches_per_start": round(pitches / starts, 1) if starts else None,
            "pitches_per_start_raw": _r(pitches / starts, 4) if starts else None}


def check_parity(read: dict, expected: dict) -> bool:
    return (read.get("starts") == expected["starts"]
            and read.get("pitches_per_start") == expected["pitches_per_start"])


# ---------------------------------------------------------------------------
# The walk forward: price every start on D from games dated before D, then fold D
# ---------------------------------------------------------------------------
class Walk:
    """Running windows. Every start on date D is priced from games dated strictly before
    D, and only then do D's games fold into the history, so a start's own outs and
    pitches (and every other game of its date) never enter its inputs."""

    def __init__(self):
        self.p_q = defaultdict(deque)                   # pitcher -> (ord, pitches, outs)
        self.p_sum = defaultdict(lambda: [0, 0, 0])     # n, pitches, outs
        self.c_q = defaultdict(deque)                   # club -> (ord, pitches, pa)
        self.c_sum = defaultdict(lambda: [0, 0])        # pitches, pa
        self.std = defaultdict(lambda: [0, 0, 0, 0])    # outs all, gs, start outs, start pitches
        self.last_ord = None
        self.counts = Counter()

    def _pitcher_window(self, pid, d):
        """(n, pitches, outs) over the pitcher's starts dated D - 365 to D - 1."""
        q, s = self.p_q[pid], self.p_sum[pid]
        while q and q[0][0] < d - WINDOW_DAYS:
            _o, pit, outs = q.popleft()
            s[0] -= 1
            s[1] -= pit
            s[2] -= outs
        return s[0], s[1], s[2]

    def _club_window(self, club, d):
        """(pitches seen, PA) over the club's games dated D - 30 to D - 1."""
        q, s = self.c_q[club], self.c_sum[club]
        while q and q[0][0] < d - LINEUP_DAYS:
            _o, pit, pa = q.popleft()
            s[0] -= pit
            s[1] -= pa
        return s[0], s[1]

    def price(self, g: dict, half: str, anchors: dict | None) -> dict | None:
        pid = g["starters"].get(half)
        line = g["lines"][half].get(pid) if pid is not None else None
        if line is None:
            self.counts["starts_without_starter"] += 1
            return None
        d = g["ord"]
        n, wp, wo = self._pitcher_window(pid, d)
        opp = g["away"] if half == "top" else g["home"]
        if opp:
            op, opa = self._club_window(opp, d)
        else:
            op = opa = None
        std = self.std[(pid, g["season"])]
        lo = _dt.date.fromordinal(d - WINDOW_DAYS)
        return {"game_pk": g["game_pk"], "season": g["season"], "date": g["date"],
                "month": int(g["date"][5:7]), "half": half, "pitcher": pid,
                "opp_club": opp, "n": n, "w_pitches": wp, "w_outs": wo,
                "opp_pitches": op, "opp_pa": opa,
                "std_outs_all": std[0], "std_gs": std[1], "std_start_outs": std[2],
                "std_start_pitches": std[3],
                "label_outs": line["outs"], "label_pitches": line["pitches"],
                "anchors": anchors,
                "reaches_2020": bool(g["season"] == 2021 and lo <= ABSENT_2020[1])}

    def fold(self, g: dict) -> None:
        d = g["ord"]
        for h in ("top", "bottom"):
            pid = g["starters"].get(h)
            for p, line in g["lines"][h].items():
                st = self.std[(p, g["season"])]
                st[0] += line["outs"]
                if p == pid:
                    st[1] += 1
                    st[2] += line["outs"]
                    st[3] += line["pitches"]
                    self.p_q[p].append((d, line["pitches"], line["outs"]))
                    s = self.p_sum[p]
                    s[0] += 1
                    s[1] += line["pitches"]
                    s[2] += line["outs"]
            club = g["away"] if h == "top" else g["home"]
            b = g["batting"].get(h)
            if club and b:
                self.c_q[club].append((d, b["pitches"], b["pa"]))
                cs = self.c_sum[club]
                cs[0] += b["pitches"]
                cs[1] += b["pa"]

    def feed(self, games: list, anchors: dict | None, score: bool) -> list:
        """Walk one season's games in date order. Returns the priced starts when `score`."""
        rows = []
        games = sorted(games, key=lambda g: (g["ord"], g["game_pk"]))
        if games and self.last_ord is not None and games[0]["ord"] <= self.last_ord:
            raise LabRefused("refused: games fed out of date order; a start would see "
                             "history from its own date or later")
        i = 0
        while i < len(games):
            d = games[i]["ord"]
            j = i
            while j < len(games) and games[j]["ord"] == d:
                j += 1
            day = games[i:j]
            if score:
                for g in day:
                    for h in ("top", "bottom"):
                        row = self.price(g, h, anchors)
                        if row is not None:
                            rows.append(row)
            for g in day:
                self.fold(g)
            self.last_ord = d
            i = j
        return rows


# ---------------------------------------------------------------------------
# The candidate and the comparators (vectorised over priced starts)
# ---------------------------------------------------------------------------
def as_arrays(rows: list) -> dict:
    def col(key, fn=float):
        return np.array([fn(r[key]) for r in rows], dtype="float64")

    def anc(key):
        return np.array([r["anchors"][key] for r in rows], dtype="float64")

    if not rows:
        empty = np.zeros(0, dtype="float64")
        keys = ("n", "w_pitches", "w_outs", "opp_pitches", "opp_pa", "std_outs_all",
                "std_gs", "std_start_outs", "std_start_pitches", "label_outs",
                "label_pitches", "L_pgs", "L_ppo", "L_ppa", "L_opg")
        out = {k: empty.copy() for k in keys}
        out.update(season=np.zeros(0, dtype="int64"), month=np.zeros(0, dtype="int64"),
                   game_pk=np.zeros(0, dtype="int64"),
                   reaches_2020=np.zeros(0, dtype=bool))
        return out
    out = {k: col(k) for k in ("n", "w_pitches", "w_outs", "opp_pitches", "opp_pa",
                               "std_outs_all", "std_gs", "std_start_outs",
                               "std_start_pitches", "label_outs", "label_pitches")}
    for k in ("L_pgs", "L_ppo", "L_ppa", "L_opg"):
        out[k] = anc(k)
    out["season"] = np.array([r["season"] for r in rows], dtype="int64")
    out["month"] = np.array([r["month"] for r in rows], dtype="int64")
    out["game_pk"] = np.array([r["game_pk"] for r in rows], dtype="int64")
    out["reaches_2020"] = np.array([r["reaches_2020"] for r in rows], dtype=bool)
    return out


def a0_outs(outs_all, gs):
    """The incumbent: 3 x clip(season-to-date IP / GS over ALL appearances, 2.0, 7.5),
    5.2 (15.6 outs) when the pitcher has no start yet that season."""
    outs_all, gs = np.asarray(outs_all, float), np.asarray(gs, float)
    ip = np.divide(outs_all / 3.0, gs, out=np.full_like(outs_all, A0_FALLBACK_IP),
                   where=gs > 0)
    return 3.0 * np.where(gs > 0, np.clip(ip, *A0_CLIP_IP), A0_FALLBACK_IP)


def d1_outs(start_outs, gs):
    """D1, reported only: A0's form on starts only."""
    return a0_outs(start_outs, gs)


def budget(w_pitches, n, L_pgs, k_b):
    return (np.asarray(w_pitches, float) + k_b * np.asarray(L_pgs, float)) / (
        np.asarray(n, float) + k_b)


def ppo(w_pitches, w_outs, L_ppo, k_o):
    return (np.asarray(w_pitches, float) + k_o * np.asarray(L_ppo, float)) / (
        np.asarray(w_outs, float) + k_o)


def lineup_ratio(opp_pitches, opp_pa, L_ppa, k_l):
    L_ppa = np.asarray(L_ppa, float)
    return ((np.asarray(opp_pitches, float) + k_l * L_ppa)
            / (np.asarray(opp_pa, float) + k_l)) / L_ppa


def xouts(b, p, r):
    return np.minimum(float(OUTS_CAP), np.asarray(b, float) / (np.asarray(p, float)
                                                               * np.asarray(r, float)))


def c1_outs(w_outs, n, L_opg, k_c):
    return (np.asarray(w_outs, float) + k_c * np.asarray(L_opg, float)) / (
        np.asarray(n, float) + k_c)


def season_mean_pitches(start_pitches, gs, L_pgs):
    """Criterion 4's comparator: the season-to-date pitches-per-start mean, L_pgs when
    the pitcher has no start yet that season."""
    sp, gs = np.asarray(start_pitches, float), np.asarray(gs, float)
    return np.divide(sp, gs, out=np.asarray(L_pgs, float).copy(), where=gs > 0)


def predictions(A: dict, pri: dict) -> dict:
    b = budget(A["w_pitches"], A["n"], A["L_pgs"], pri["k_b"])
    p = ppo(A["w_pitches"], A["w_outs"], A["L_ppo"], pri["k_o"])
    r = lineup_ratio(A["opp_pitches"], A["opp_pa"], A["L_ppa"], pri["k_l"])
    return {"a0": a0_outs(A["std_outs_all"], A["std_gs"]),
            "candidate": xouts(b, p, r),
            "d1": d1_outs(A["std_start_outs"], A["std_gs"]),
            "d2": xouts(b, p, 1.0),
            "c1": c1_outs(A["w_outs"], A["n"], A["L_opg"], pri["k_c"]),
            "budget": b,
            "season_mean": season_mean_pitches(A["std_start_pitches"], A["std_gs"],
                                               A["L_pgs"]),
            "r_l": r}


def err_stats(pred, actual) -> dict | None:
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    if pred.size == 0:
        return None
    e = pred - actual
    return {"n": int(e.size), "mae": _r(np.mean(np.abs(e))),
            "rmse": _r(math.sqrt(float(np.mean(e * e)))), "bias": _r(np.mean(e))}


def _mae(pred, actual) -> float | None:
    pred = np.asarray(pred, float)
    return None if pred.size == 0 else float(np.mean(np.abs(pred - np.asarray(actual, float))))


def report_block(A: dict, P: dict, mask) -> dict | None:
    mask = np.asarray(mask, bool)
    n = int(mask.sum())
    if n == 0:
        return None
    lo, lp = A["label_outs"][mask], A["label_pitches"][mask]
    blk = {"n": n,
           "outs": {arm: err_stats(P[arm][mask], lo) for arm in ARMS_OUTS},
           "pitches": {arm: err_stats(P[arm][mask], lp) for arm in ARMS_PITCHES}}
    blk["improvement_a0_minus_candidate"] = _r(_mae(P["a0"][mask], lo)
                                               - _mae(P["candidate"][mask], lo))
    return blk


# ---------------------------------------------------------------------------
# The burn-in: priors chosen once, on the 2019 starts, ties to the smallest
# ---------------------------------------------------------------------------
def select_priors(A: dict) -> tuple[dict, list, list]:
    """(priors, grid table, C1 grid table) by outs MAE on the 2019 starts only."""
    seasons = set(int(s) for s in A["season"])
    if seasons - set(BURN_IN_SCORED):
        raise LabRefused(f"refused: the burn-in reads only {BURN_IN_SCORED}, got "
                         f"{sorted(seasons)}")
    lo = A["label_outs"]
    if lo.size == 0:
        raise LabRefused("refused: the burn-in holds no 2019 start")
    table = []
    for kb in GRID_KB:
        b = budget(A["w_pitches"], A["n"], A["L_pgs"], kb)
        for ko in GRID_KO:
            p = ppo(A["w_pitches"], A["w_outs"], A["L_ppo"], ko)
            for kl in GRID_KL:
                r = lineup_ratio(A["opp_pitches"], A["opp_pa"], A["L_ppa"], kl)
                table.append({"k_b": kb, "k_o": ko, "k_l": kl,
                              "mae_outs": _mae(xouts(b, p, r), lo)})
    grid_c = [{"k_c": kc, "mae_outs": _mae(c1_outs(A["w_outs"], A["n"], A["L_opg"], kc), lo)}
              for kc in GRID_KC]

    def key(t, names):
        return (round(t["mae_outs"], TIE_DECIMALS),) + tuple(t[k] for k in names)

    best = min(table, key=lambda t: key(t, ("k_b", "k_o", "k_l")))
    best_c = min(grid_c, key=lambda t: key(t, ("k_c",)))
    pri = {"k_b": best["k_b"], "k_o": best["k_o"], "k_l": best["k_l"], "k_c": best_c["k_c"]}
    for t in table + grid_c:
        t["mae_outs"] = _r(t["mae_outs"])
    return pri, table, grid_c


# ---------------------------------------------------------------------------
# The bootstrap, the attribution family and the verdict
# ---------------------------------------------------------------------------
def clustered_bootstrap(game_pk, abs_err: dict, B: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Games resampled with replacement (both starts of a game together), the same draws
    for every contrast. Each replicate improvement is (sum |e| of the comparator minus
    sum |e| of the candidate) over the drawn starts, divided by their count."""
    game_pk = np.asarray(game_pk)
    if game_pk.size == 0:
        return {"games": 0, "B": B, "seed": seed, "reps": None}
    games, inv = np.unique(game_pk, return_inverse=True)
    G = games.size
    cnt = np.bincount(inv, minlength=G).astype("float64")
    sums = {k: np.bincount(inv, weights=np.asarray(v, float), minlength=G)
            for k, v in abs_err.items()}
    rng = np.random.default_rng(seed)
    reps = {k: np.empty(B) for k in ("a0", "d2", "c1")}
    for b in range(B):
        idx = rng.integers(0, G, size=G)
        n = cnt[idx].sum()
        sc = sums["candidate"][idx].sum()
        for k in reps:
            reps[k][b] = (sums[k][idx].sum() - sc) / n
    return {"games": int(G), "B": B, "seed": seed, "reps": reps}


def one_sided_p(reps) -> float | None:
    """(1 + replicates with an improvement at or below 0) / (B + 1)."""
    if reps is None:
        return None
    reps = np.asarray(reps, float)
    return float((1 + int(np.sum(reps <= 0))) / (reps.size + 1))


def holm_two(p_t1, p_t2) -> dict:
    """Holm step-down, m = 2: the smaller p at 0.025, the larger at 0.05; a failure at
    the first step fails both."""
    ps = {"T1": p_t1, "T2": p_t2}
    out = {"T1": False, "T2": False}
    if any(v is None for v in ps.values()):
        return out
    order = sorted(ps, key=lambda k: (ps[k], k))
    if ps[order[0]] <= HOLM_ALPHAS[0]:
        out[order[0]] = True
        if ps[order[1]] <= HOLM_ALPHAS[1]:
            out[order[1]] = True
    return out


def decide(lb, imp_2024, imp_2025, imp_pooled, floor, mae_budget, mae_season_mean) -> dict:
    """The four criteria and the final verdict. A null criterion is not met."""
    c1 = lb is not None and lb > 0
    c2 = (imp_2024 is not None and imp_2024 > 0) and (imp_2025 is not None and imp_2025 > 0)
    c3 = imp_pooled is not None and floor is not None and imp_pooled >= floor
    c4 = (mae_budget is not None and mae_season_mean is not None
          and mae_budget <= mae_season_mean)
    if c1 and c2 and c4:
        verdict = "PASS" if c3 else "PASS-BELOW-FLOOR"
    else:
        verdict = "FAIL"
    return {"criteria": {"1_bootstrap_lower_bound_above_0": c1,
                         "2_positive_in_2024_and_2025": c2,
                         "3_at_or_above_floor": c3,
                         "4_pitches_budget_no_worse": c4},
            "verdict": verdict}


def wording(t1_pass: bool, t2_pass: bool) -> dict:
    return {"T1_pass": bool(t1_pass), "T2_pass": bool(t2_pass),
            "credit": "pitch rates" if t2_pass else WORDING_NO_T2,
            "lineup": ("T1 credits the opposing lineup's P/PA" if t1_pass
                       else WORDING_NO_T1)}


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------
def write_artifact(art: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(art, indent=1, allow_nan=False, ensure_ascii=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, path)


def _definitions() -> dict:
    return {
        "unit": "a start: the first pitcher of each fielding half (archive-reconstruct "
                "provenance, owner decision O22)",
        "estimand": "outs recorded by the starter in the start (primary), pitches he threw "
                    "(secondary)",
        "candidate": "xouts = min(27, budget / (ppo x r_L)); budget = (pitches over the n "
                     "starts in the 365 days before D + k_b L_pgs) / (n + k_b); ppo = "
                     "(those pitches + k_o L_ppo) / (those outs + k_o); r_L = [(pitches seen "
                     "by the opposing club's hitters over its games in the 30 days before D "
                     "+ k_l L_ppa) / (their PA + k_l)] / L_ppa; xIP = xouts / 3; xPitches = "
                     "budget",
        "a0": "3 x clip(season-to-date IP / GS over all appearances before D, 2.0, 7.5); "
              "15.6 with no start yet that season",
        "d1": "A0's form on starts only (reported, never tested)",
        "d2": "the candidate with r_L = 1 (tested, T1)",
        "c1": "(outs over the 365-day starts + k_c L_opg) / (n + k_c) (tested, T2)",
        "season_mean": "criterion 4's comparator: season-to-date pitches per start before "
                       "D, L_pgs with no start yet that season",
        "windows": "365 days: dates D - 365 to D - 1; 30 days: dates D - 30 to D - 1",
        "anchors": "the prior complete corpus season, pooled sum over sum (2019 for 2021)",
        "april_may": "starts dated Opening Day through May 31",
        "openers": "starts whose trailing 365-day mean is under 6 outs per start (n > 0)",
        "scored_set": "starts with a resolved opposing club and anchors; the rest are "
                      "counted under counts",
    }


def _season_masks(A: dict, seasons) -> dict:
    return {str(s): A["season"] == s for s in seasons}


def run_stage1(source, out_path: Path, *, mode: str, clock: dict | None = None,
               parity: dict | None = PARITY_2025, log=print) -> dict:
    """Stage 1 in its registered order: the burn-in priors frozen and written, then the
    floor written, and only then the 2024 and 2025 seasons read and scored once."""
    out_path = Path(out_path)
    art = {"artifact": "starter_workload_eval", "section": SECTION_TITLE,
           "registry_row": REGISTRY_ROW, "mode": mode, "generated_at": _now(),
           "stage1": {"status": "started", "clock": clock,
                      "source": source.describe(), "definitions": _definitions(),
                      "registered": {"grid_k_b": list(GRID_KB), "grid_k_o": list(GRID_KO),
                                     "grid_k_l": list(GRID_KL), "grid_k_c": list(GRID_KC),
                                     "B": BOOT_B, "seed": BOOT_SEED,
                                     "lower_bound_percentile": LB_PERCENTILE,
                                     "floor_share": FLOOR_SHARE,
                                     "holm_alphas": list(HOLM_ALPHAS)}}}
    st = art["stage1"]
    walk, loaded, counts = Walk(), {}, {}

    def load(s):
        games, cts = load_season(source, s)
        loaded[s] = games
        counts[str(s)] = cts
        return games

    def anchors_for(s):
        prior = [x for x in loaded if x < s and loaded[x]]
        return league_anchors(loaded[max(prior)]) if prior else None

    def scored(rows):
        keep = [r for r in rows if r["anchors"] is not None and r["opp_club"]]
        c = Counter()
        for r in rows:
            if r["anchors"] is None:
                c["starts_without_anchor"] += 1
            elif not r["opp_club"]:
                c["starts_unresolved_opponent"] += 1
        return keep, c

    st["corpus_seasons"] = source.check_seasons(SEASONS)
    pre = getattr(source, "preflight", None)
    if pre is not None:
        st["preflight"] = pre(SEASONS)
    # From this first write on, the artifact exists and the one-run guard holds: any
    # exception below is recorded in it and the lab is never rerun (the crash protocol).
    write_artifact(art, out_path)
    try:
        # ---- burn-in: 2018 history, 2019 scored --------------------------------------
        for s in BURN_IN_HISTORY:
            walk.feed(load(s), None, score=False)
        anchors = {}
        burn_rows = []
        for s in BURN_IN_SCORED:
            anchors[str(s)] = anchors_for(s)
            burn_rows += walk.feed(load(s), anchors[str(s)], score=True)
        keep, excl = scored(burn_rows)
        A19 = as_arrays(keep)
        pri, grid, grid_c = select_priors(A19)
        P19 = predictions(A19, pri)
        st["burn_in"] = {"scored_season": list(BURN_IN_SCORED),
                         "history_seasons": list(BURN_IN_HISTORY),
                         "starts": len(burn_rows), "scored": len(keep),
                         "excluded": dict(excl), "anchors": dict(anchors),
                         "priors": pri, "grid": grid, "grid_c1": grid_c,
                         "in_sample_2019": report_block(A19, P19, np.ones(len(keep), bool)),
                         "frozen_at": _now()}
        st["status"] = "burn_in_frozen"
        write_artifact(art, out_path)
        log(f"burn-in frozen: k_b {pri['k_b']} k_o {pri['k_o']} k_l {pri['k_l']} "
            f"k_c {pri['k_c']} on {len(keep)} starts of {BURN_IN_SCORED}")

        # ---- floor: 2021 to 2023, written before any 2024 row is read ---------------
        rows = []
        for s in FLOOR_SEASONS:
            if not source.has(s):
                counts[str(s)] = {"absent": True}
                continue
            anchors[str(s)] = anchors_for(s)
            rows += walk.feed(load(s), anchors[str(s)], score=True)
        keep_f, excl_f = scored(rows)
        AF = as_arrays(keep_f)
        PF = predictions(AF, pri)
        mae_a0 = _mae(PF["a0"], AF["label_outs"])
        st["floor"] = {"seasons": list(FLOOR_SEASONS), "scored": len(keep_f),
                       "excluded": dict(excl_f), "a0_outs_mae": _r(mae_a0),
                       "floor": _r(FLOOR_SHARE * mae_a0) if mae_a0 is not None else None,
                       "fixed_at": _now()}
        st["status"] = "floor_fixed"
        write_artifact(art, out_path)
        log(f"floor fixed: {st['floor']['floor']} (1 percent of A0's outs MAE "
            f"{st['floor']['a0_outs_mae']} on {len(keep_f)} starts)")

        # ---- the scored seasons, read once ---------------------------------------------
        srows = []
        for s in SCORED_SEASONS:
            if not source.has(s):
                counts[str(s)] = {"absent": True}
                continue
            anchors[str(s)] = anchors_for(s)
            games = load(s)
            if s == 2025:
                pr = parity_read(games)
                pr["expected"] = parity
                pr["ok"] = None if parity is None else check_parity(pr, parity)
                st["parity_2025"] = pr
                if pr["ok"] is False:
                    st["status"] = "stopped_parity"
                    write_artifact(art, out_path)
                    raise LabRefused(f"refused: 2025 corpus parity {pr} does not reproduce "
                                     f"{parity}; no 2024 or 2025 start is scored")
            srows += walk.feed(games, anchors[str(s)], score=True)
        keep_s, excl_s = scored(srows)
        A_all = as_arrays(keep_f + keep_s)
        P_all = predictions(A_all, pri)
        AS = as_arrays(keep_s)
        PS = predictions(AS, pri)
        lo = AS["label_outs"]

        by_season = {k: report_block(A_all, P_all, m) for k, m in
                     _season_masks(A_all, FLOOR_SEASONS + SCORED_SEASONS).items()}
        april_may = {k: report_block(A_all, P_all, m & (A_all["month"] <= 5)) for k, m in
                     _season_masks(A_all, FLOOR_SEASONS + SCORED_SEASONS).items()}
        opener = (AS["n"] > 0) & (AS["w_outs"] < OPENER_OUTS * np.maximum(AS["n"], 1))
        opener_all = (A_all["n"] > 0) & (A_all["w_outs"] < OPENER_OUTS
                                         * np.maximum(A_all["n"], 1))
        pooled = report_block(AS, PS, np.ones(lo.size, bool))
        abs_err = {k: np.abs(PS[k] - lo) for k in ("a0", "candidate", "d2", "c1")}
        boot = clustered_bootstrap(AS["game_pk"], abs_err)
        reps = boot.pop("reps")
        lb = float(np.percentile(reps["a0"], LB_PERCENTILE)) if reps else None
        p_t1 = one_sided_p(reps["d2"]) if reps else None
        p_t2 = one_sided_p(reps["c1"]) if reps else None
        holm = holm_two(p_t1, p_t2)
        imp = {str(s): (by_season.get(str(s)) or {}).get("improvement_a0_minus_candidate")
               for s in SCORED_SEASONS}
        imp_pooled = (pooled or {}).get("improvement_a0_minus_candidate")
        mae_b = _mae(PS["budget"], AS["label_pitches"])
        mae_m = _mae(PS["season_mean"], AS["label_pitches"])
        dec = decide(lb, imp["2024"], imp["2025"], imp_pooled, st["floor"]["floor"],
                     mae_b, mae_m)
        st["anchors"] = anchors
        st["results"] = {
            "scored_seasons": list(SCORED_SEASONS), "scored": len(keep_s),
            "excluded": dict(excl_s),
            "pooled_2024_2025": pooled,
            "by_season": by_season,
            "april_may": april_may,
            "april_may_pooled_2024_2025": report_block(AS, PS, AS["month"] <= 5),
            "openers_pooled_2024_2025": report_block(AS, PS, opener),
            "openers_by_season": {k: report_block(A_all, P_all, m & opener_all) for k, m in
                                  _season_masks(A_all, FLOOR_SEASONS + SCORED_SEASONS).items()},
            "counts": {"starts_n0_by_season": {
                           str(s): int(np.sum((A_all["season"] == s) & (A_all["n"] == 0)))
                           for s in FLOOR_SEASONS + SCORED_SEASONS},
                       "starts_2021_window_reaches_absent_2020": int(np.sum(
                           A_all["reaches_2020"])),
                       "walk": dict(walk.counts),
                       "per_season": counts},
        }
        st["criteria"] = {
            "improvement_pooled": imp_pooled,
            "improvement_2024": imp["2024"], "improvement_2025": imp["2025"],
            "bootstrap_lower_bound": _r(lb),
            "floor": st["floor"]["floor"],
            "pitches_mae_budget": _r(mae_b), "pitches_mae_season_mean": _r(mae_m),
            "bootstrap": boot,
            **dec["criteria"]}
        st["attribution"] = {
            "family": "T1 (candidate against D2) and T2 (candidate against C1), Holm m = 2, "
                      "one-sided 0.05; they decide wording only, never the verdict",
            "T1_p": _r(p_t1), "T2_p": _r(p_t2),
            "T1_improvement": _r(_mae(PS["d2"], lo) - _mae(PS["candidate"], lo))
            if lo.size else None,
            "T2_improvement": _r(_mae(PS["c1"], lo) - _mae(PS["candidate"], lo))
            if lo.size else None,
            "holm": holm,
            "wording": wording(holm["T1"], holm["T2"])}
        st["verdict"] = dec["verdict"]
        st["status"] = "complete"
        st["completed_at"] = _now()
        write_artifact(art, out_path)
        log(f"stage 1 verdict: {dec['verdict']}")
        return art
    except LabRefused as exc:
        if st.get("status") != "stopped_parity":
            st["status"] = "refused"
        st["refusal"] = str(exc)
        _record_stop(art, out_path)
        raise
    except Exception as exc:                     # noqa: BLE001 - the crash protocol
        st["status"] = "crashed"
        st["crash"] = {"error": repr(exc), "traceback": traceback.format_exc()[-4000:]}
        _record_stop(art, out_path)
        raise


def _record_stop(art: dict, out_path: Path) -> None:
    art["stage1"]["protocol"] = ("stopped after the first write: never rerun; the question "
                                 "goes to the owner")
    try:
        write_artifact(art, out_path)
    except Exception:                            # noqa: BLE001 - the original error wins
        pass


# ---------------------------------------------------------------------------
# The section's result heading
# ---------------------------------------------------------------------------
def result_heading(art: dict) -> str:
    st = art["stage1"]
    run = (st.get("clock") or {}).get("today") or st.get("completed_at", "")[:10]
    return f"### Stage 1 result (run {run}, once): {st['verdict']}"


def result_text(art: dict) -> str:
    st = art["stage1"]
    cr, at, pri = st["criteria"], st["attribution"], st["burn_in"]["priors"]

    def f(x):
        return "none (no scored start)" if x is None else f"{x}"

    lines = [
        result_heading(art), "",
        f"Written by tools/starter_workload_lab.py into data/starter_workload_eval.json. "
        f"Priors frozen on the 2019 starts: k_b {pri['k_b']}, k_o {pri['k_o']}, "
        f"k_l {pri['k_l']}, k_c {pri['k_c']}. Floor {f(cr['floor'])} outs. Pooled "
        f"2024-2025 improvement MAE(A0) minus MAE(candidate) {f(cr['improvement_pooled'])} "
        f"outs (2024 {f(cr['improvement_2024'])}, 2025 {f(cr['improvement_2025'])}), "
        f"bootstrap lower bound {f(cr['bootstrap_lower_bound'])}; pitches MAE of budget "
        f"{f(cr['pitches_mae_budget'])} against {f(cr['pitches_mae_season_mean'])}. T1 p "
        f"{f(at['T1_p'])}, T2 p {f(at['T2_p'])}: credit reads "
        f"\"{at['wording']['credit']}\"; {at['wording']['lineup']}.",
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
# The synthetic fixture (the dry run and the tests): a probable with no prior start,
# an opener, no 2024 season
# ---------------------------------------------------------------------------
FIXTURE_CLUBS = ("BOS", "NYY", "TOR", "BAL")
FIXTURE_SEASONS = (2018, 2019, 2021, 2022, 2023, 2025)


def synthetic_tables(seed: int = 7, seasons=FIXTURE_SEASONS, dates_per_season: int = 24,
                     late_seed: int | None = None):
    """(tables, dates, weights) in the corpus's own shape. `late_seed` re-draws the
    seasons from 2021 on without touching 2018 and 2019."""
    import pandas as pd

    tables, dates, wrows = {}, {}, []
    pk = 900000
    for season in seasons:
        sseed = seed * 10000 + season
        if late_seed is not None and season >= 2021:
            sseed = late_seed * 10000 + season
        rng = np.random.default_rng(sseed)
        plays, pitches = [], []
        for ci, club in enumerate(FIXTURE_CLUBS):
            for j in range(9):
                wrows.append({"mlb_ID": float(500000 + ci * 100 + j), "year_ID": season,
                              "team_ID": club, "PA": 450})
        club_games = Counter()
        lineup_pos = Counter()
        d0 = _dt.date(season, 3, 30)
        for k in range(dates_per_season):
            d = d0 + _dt.timedelta(days=3 * k)
            pairs = (((0, 1), (2, 3)), ((2, 0), (3, 1)), ((0, 3), (1, 2)))[k % 3]
            for hi, ai in pairs:
                pk += 1
                dates[pk] = d.isoformat()
                fielders = {}
                for side, ci in (("top", hi), ("bottom", ai)):   # top: home fields
                    g_no = club_games[ci]
                    club_games[ci] += 1
                    slot = g_no % 4
                    starter = 600000 + ci * 100 + slot
                    target = int(min(27, max(6, (18, 16, 15, 13)[slot]
                                             + rng.integers(-3, 4))))
                    if ci == 1 and g_no == 4:
                        starter = 600000 + ci * 100 + 50 + season % 100   # a debut
                    if ci == 2 and g_no % 4 == 3:
                        starter, target = 600000 + ci * 100 + 9, 3       # an opener
                    fielders[side] = {"starter": starter, "target": target, "slot": slot,
                                      "outs": 0, "done": False,
                                      "pen": 700000 + ci * 100 + int(rng.integers(0, 4))}
                abi = 0
                for inning in range(1, 10):
                    for side in ("top", "bottom"):
                        f = fielders[side]
                        bat_ci = ai if side == "top" else hi
                        outs = 0
                        while outs < 3:
                            pitcher = f["pen"] if f["done"] else f["starter"]
                            r = rng.random()
                            n_p = int(rng.integers(1, 7)) + (f["slot"] % 2 if not f["done"]
                                                             else 0)
                            if r < 0.03:
                                event, out, n_p = "caught_stealing_2b", 1, 1
                            elif r < 0.70:
                                event, out = ("strikeout" if r < 0.25 else "field_out"), 1
                            else:
                                event, out = ("single" if r < 0.9 else "walk"), 0
                            batter = 500000 + bat_ci * 100 + lineup_pos[bat_ci] % 9
                            if event != "caught_stealing_2b":
                                lineup_pos[bat_ci] += 1
                            plays.append({"game_pk": pk, "season": season, "half": side,
                                          "inning": inning, "at_bat_index": abi,
                                          "batter_id": batter, "pitcher_id": pitcher,
                                          "event_type": event, "outs_before": outs,
                                          "outs_after": outs + out})
                            for pn in range(n_p):
                                pitches.append({"game_pk": pk, "season": season,
                                                "at_bat_index": abi, "is_pitch": True})
                            abi += 1
                            outs += out
                            if not f["done"]:
                                f["outs"] += out
                                if f["outs"] >= f["target"]:
                                    f["done"] = True
        tables[season] = (pd.DataFrame(plays), pd.DataFrame(pitches))
    return tables, dates, pd.DataFrame(wrows)


def synthetic_source(seed: int = 7, **kw) -> FixtureSource:
    tables, dates, weights = synthetic_tables(seed=seed, **kw)
    return FixtureSource(tables, dates, weights)


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
    ap.add_argument("--out", type=Path, help="dry run: the artifact path (never under data/)")
    ap.add_argument("--tee", type=Path, help="copy stdout and stderr to this file first")
    args = ap.parse_args(argv)
    fh = None
    saved = sys.stdout, sys.stderr
    if args.tee:
        args.tee.parent.mkdir(parents=True, exist_ok=True)
        fh = open(args.tee, "a", encoding="utf-8")
        sys.stdout, sys.stderr = _Tee(sys.stdout, fh), _Tee(sys.stderr, fh)
    try:
        if args.dry_run:
            if args.out is None:
                ap.error("--dry-run needs --out")
            out = check_out_path(args.out)
            art = run_stage1(synthetic_source(), out, mode="dry_run_fixture", parity=None)
            print(result_text(art))
            return 0
        clock = check_clock()
        check_one_run(ARTIFACT)
        art = run_stage1(CorpusSource(), ARTIFACT, mode="run", clock=clock)
        append_result(GATE_DOC, art)
        print(result_text(art))
        print(f"next: the run commit sets {REGISTRY_ROW} to "
              f"{'provisional (dark)' if art['stage1']['verdict'] == 'PASS' else 'deprecated'}"
              f" with eval_artifact data/starter_workload_eval.json")
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
