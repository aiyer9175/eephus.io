# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The starter-workload stage-2 look: the candidate innings share on the moneyline, read once in 2027.

Registration: docs/diamond-betting.md, the section "Starter workload: expected outs and
pitches per start" (pre-registered 2026-09-30, plan candidate N6(d), owner ask 16), its
"Stage 2: the moneyline price" list. Stage 1 recorded PASS on 2026-10-14. This file is
stage 2 and nothing else. Built 2026-10-21 (task Q10_21, checklist PM-11) and tested on
fixtures only: no vintage record, no completed game and no outcome has been read by it.
The look itself is a separate session in 2027.

Modes:
  python -u tools/betting_workload_gate.py --run [--tee PATH]
      THE LOOK. Refused before 2027-07-01, without a step Z entry in part 9 of the fWAR
      label epoch gate, without 5l's `mgmt_policy_gate` block (before 2027-08-01), and on
      a second run. Yields (and records the yield) when another registered look falls on
      the day or when criterion 4 does not hold yet; records NOT READ when criterion 4 or
      5l's block still fails on or after 2027-08-01. Writes ONLY the stage2 block of
      data/starter_workload_eval.json, the section's own tracked artifact, then appends
      the "### Stage 2 result" heading under the section.
  python tools/betting_workload_gate.py --dry-run --out PATH [--doc-out PATH]
      The whole reporting path on the built-in synthetic fixture with nulls (games with
      no vintage, a missing probable, a debut with no workload value, a club with no
      lineup value, null third-time-through and dugout neighbours). Refuses a path
      under data/. `--twin-draws N` shortens the twin for a quick dry run and is
      stamped in the output; the run always draws 200.

What is registered and is not a choice here: the candidate share clip(xOuts / 27, 0.25,
0.85) replacing w in `game_prevention_z`, with xOuts = min(27, budget / (ppo x r_L)) from
the dated columns through betting_usage's one candidate function; the fit by
`fit_coefficients` (with the served vintage corrections) on the VINTAGE_FIT_TARGET_GAMES
(300) games before the eval half, side by side with the served arm on the same games;
the moneyline label; criteria (1) to (5) in the 5l form; the N6 Holm family (m = 4, the
smallest p at 0.0125 when no other member is read); the power precondition (2.241 +
0.842) x sd_d / sqrt(600) against the floor 0.0024 Brier, sd_d measured once on the fit
window from the candidate fit before any eval-half game is read; the 2027-07-01 and
2027-08-01 dates.

Choices this file makes where the section names a form without its digits (stated in
every block it writes): the paired t is mean / (sd / sqrt(n)), sd with the n - 1
divisor, and its one-sided p is the normal upper tail (the 1.645 bar is a normal
quantile); the twin draws `numpy.random.default_rng(k)` for k = 0 to 199, one
permutation of the xOuts values across each date's probables per draw, and its bar is
`numpy.percentile(improvements, 95)` (linear), exceeded strictly (the 5k pinned form of
"the 95th percentile"); the VIF rows are the eval half's probable sides, the candidate
share regressed with an intercept on each neighbour alone and on all of them together,
and criterion 5 needs both the innings-share VIF and the joint VIF at or under 5 (a
joint VIF that cannot be computed is reported and does not fail); the VIF neighbours are
read from the section's own criterion (5), so this file cannot drift from it.

What it never reads: a game of any season but the look's (the 305 games of the 2026 fit
window, and every 2026 game, stay unread and ungraded); a posted card; a price, a market
capture, an edge, a slot or a ledger row; data/betting_model_eval.json, except to see
whether 5l's block exists. It never writes data/betting_model_eval.json, which
betting_model.backtest() rebuilds from scratch every night.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import starter_workload_lab as swl                                   # noqa: E402

DATA = ROOT / "data"
ARTIFACT = DATA / "starter_workload_eval.json"
BETTING_EVAL = DATA / "betting_model_eval.json"
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
PRE_EPOCH_DIR = ROOT.parent.parent / "_pre_epoch_fwar_2026-10"

SECTION_TITLE = swl.SECTION_TITLE
REGISTRY_ROW = swl.REGISTRY_ROW
STAGE2_HEADING_RE = re.compile(
    r"^### Stage 2 result \(run (\d{4}-\d{2}-\d{2}), once\): ([A-Z][A-Z -]*[A-Z])\s*$", re.M)
SECTION_5L_RE = r"^## 5l\. [^\n]*$"

# ---------------------------------------------------------------------------
# Registered constants (the section's own numbers; pinned by the tests)
# ---------------------------------------------------------------------------
FIRST_LOOK_SEASON = 2027
EARLIEST_LOOK = _dt.date(2027, 7, 1)
WAIT_FOR_NEXT_SEASON = _dt.date(2027, 8, 1)     # (4) and 5l's block both by then, else 2028
FIT_TARGET_GAMES = 300                          # betting_model.VINTAGE_FIT_TARGET_GAMES
MIN_EVAL_GAMES = 600                            # betting_model.VINTAGE_MIN_GRADED_GAMES
T_BAR = 1.645
N6_MEMBERS = ("F05-07", "F08-01", "G4-02", "G4-10")
N6_SELF = "G4-10"
N6_ALPHA = 0.05                                 # family alpha, one-sided; m = 4
N_TWIN = 200
TWIN_PERCENTILE = 95.0
VIF_BAR = 5.0
POWER_Z_ALPHA = 2.241                           # one-sided 0.0125
POWER_Z_POWER = 0.842                           # 80 percent power
POWER_N = 600
FLOOR_BRIER = 0.0024
SHARE_CLIP = (0.25, 0.85)                       # the served clip in _starter_share
OUTS_PER_GAME = 27.0
LOGLOSS_EPS = 1e-9                              # betting_model._logloss
INNINGS_SHARE_COLUMN = "ip_per_gs"

VERDICTS_FINAL = ("PASS", "FAIL", "PASS-BELOW-FLOOR")
VERDICTS_WAIT = ("UNDERPOWERED", "NOT READ")
#: Other registered looks dated in 2027 (plan Part 9's look days). The run also scans
#: the gate documents for the day (`other_looks_on`).
OTHER_LOOK_DAYS = tuple(_dt.date.fromisoformat(d) for d in (
    "2027-01-12", "2027-10-20", "2027-11-09", "2027-11-16"))
POSTSEASON_TYPES = ("F", "D", "L", "W")

CHOICES = {
    "paired_t": "mean / (sd / sqrt(n)), sd with the n - 1 divisor; one-sided p is the "
                "normal upper tail",
    "holm": "N6, m = 4, conservative: a member with no recorded p sits at p = 1",
    "twin": "numpy.random.default_rng(k), k = 0 to 199; xOuts permuted across each "
            "date's probables (fit window and eval half); bar numpy.percentile(., 95), "
            "linear, exceeded strictly",
    "vif": "eval-half probable sides; candidate share regressed with an intercept on "
           "each neighbour alone and on all of them; criterion 5 needs the innings-share "
           "VIF and the joint VIF at or under 5 (a joint VIF that cannot be computed is "
           "reported and does not fail)",
    "power": "(2.241 + 0.842) x sd_d / sqrt(600); sd_d the n - 1 sd of the per-game paired "
             "Brier difference (served minus candidate) on the fit window, each arm fitted "
             "on that window (in-sample, lenient)",
}


class LookRefused(RuntimeError):
    """A guard fired: nothing is read and nothing is written."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
_r = swl._r


def _now() -> str:
    return swl._now()


def _as_date(v) -> _dt.date:
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _clip_share(x: float) -> float:
    return max(SHARE_CLIP[0], min(SHARE_CLIP[1], float(x)))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section_text(doc_text: str | None = None) -> str:
    return swl.section_text(doc_text)


def _section_5l(doc_text: str) -> str:
    text = doc_text.replace("\r\n", "\n")
    hits = list(re.finditer(SECTION_5L_RE, text, flags=re.M))
    if len(hits) != 1:
        return ""
    nxt = re.search(r"^## ", text[hits[0].end():], flags=re.M)
    return text[hits[0].start():] if nxt is None else text[hits[0].start():hits[0].end()
                                                             + nxt.start()]


def registered_vif_neighbours(doc_text: str | None = None) -> tuple:
    """The neighbours criterion (5) names, read off the section in its own order."""
    sec = _norm(section_text(doc_text))
    m = re.search(r"\(5\) the VIF read against (.*?) \(as dark columns\)", sec)
    if m is None:
        raise LookRefused("refused: the section's criterion (5) does not name its VIF "
                          "neighbours in the registered form")
    names = tuple(re.findall(r"`([A-Za-z0-9_]+)`", m.group(1)))
    if INNINGS_SHARE_COLUMN not in names:
        raise LookRefused("refused: criterion (5) does not name the innings share")
    return names


# ---------------------------------------------------------------------------
# Guards: the clock, the epoch gap, 5l's block, other looks, the one run
# ---------------------------------------------------------------------------
def check_clock(today: _dt.date, epoch_text: str | None = None,
                pre_epoch_dir: Path | None = PRE_EPOCH_DIR) -> dict:
    """Refuse before 2027-07-01, before the 2027 season, and without a step Z entry."""
    today = _as_date(today)
    if today < EARLIEST_LOOK:
        raise LookRefused(f"refused: today {today} is before the registered earliest look "
                          f"{EARLIEST_LOOK}")
    if today.year < FIRST_LOOK_SEASON:                       # pragma: no cover - implied
        raise LookRefused(f"refused: {today.year} is before the first look season")
    z = swl.step_z_entry(epoch_text)
    if z is None:
        where = (" and the pre-epoch bundle directory exists"
                 if pre_epoch_dir is not None and Path(pre_epoch_dir).exists() else "")
        raise LookRefused("refused: part 9 of FWAR_LABEL_EPOCH_GATE.md records no step Z "
                          f"entry{where}; nothing runs between the epoch's step A and "
                          "step Z")
    return {"today": today.isoformat(), "earliest_look": EARLIEST_LOOK.isoformat(),
            "wait_for_next_season": WAIT_FOR_NEXT_SEASON.isoformat(), "step_z_entry": z}


def mgmt_policy_block(doc_text: str | None = None, json_paths=None) -> dict | None:
    """Where 5l's look is recorded, or None: a `mgmt_policy_gate` block in
    data/betting_model_eval.json or in a 5l artifact of its own (data/*mgmt_policy*.json,
    data/*dugout*.json), or a "### Result" heading under 5l (that block is rebuilt away
    nightly in data/betting_model_eval.json, so the section's own record counts too)."""
    if json_paths is None:
        json_paths = [BETTING_EVAL] + sorted(DATA.glob("*mgmt_policy*.json")) + sorted(
            DATA.glob("*dugout*.json"))
    for p in json_paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        blk = doc.get("mgmt_policy_gate") if isinstance(doc, dict) else None
        if isinstance(blk, dict) and blk:
            run = blk.get("run_date") or blk.get("look_date") or (
                (blk.get("clock") or {}).get("today") if isinstance(blk.get("clock"), dict)
                else None)
            return {"where": p.name, "run_date": run}
    if doc_text is None:
        try:
            doc_text = GATE_DOC.read_text(encoding="utf-8")
        except OSError:
            return None
    sec = _section_5l(doc_text)
    m = re.search(r"^### Result \(run (\d{4}-\d{2}-\d{2})[^\n]*$", sec, flags=re.M)
    if m:
        return {"where": "docs/diamond-betting.md 5l result heading", "run_date": m.group(1)}
    return None


def other_looks_on(today: _dt.date, docs=None, *, mgmt: dict | None = None) -> list:
    """Reasons another registered look falls on `today`: a registered 2027 look day, 5l's
    own look date, or a line in a gate document that names the day beside the word look
    (outside this section)."""
    today = _as_date(today)
    iso = today.isoformat()
    out = []
    if today in OTHER_LOOK_DAYS:
        out.append(f"{iso} is a registered look day (plan Part 9)")
    if mgmt and mgmt.get("run_date") == iso:
        out.append(f"{iso} is 5l's own look date")
    if docs is None:
        docs = sorted((ROOT / "docs").glob("*GATE*.md")) + [GATE_DOC]
    for p in docs:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        if Path(p) == GATE_DOC:
            try:
                text = text.replace(section_text(text), "")
            except swl.LabRefused:
                pass
        for line in text.splitlines():
            if iso in line and re.search(r"\blook", line, flags=re.I):
                out.append(f"{Path(p).name}: {line.strip()[:160]}")
    return out


def _load_artifact(path: Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LookRefused(f"refused: {p.name} does not parse; a broken artifact is a "
                          "question for the owner")
    return doc if isinstance(doc, dict) else None


def check_one_run(artifact_path: Path, doc_text: str | None, season: int) -> None:
    """The one-run guard reads the artifact's stage2 block and the section's results."""
    art = _load_artifact(artifact_path) or {}
    s2 = art.get("stage2")
    if isinstance(s2, dict):
        st = s2.get("status")
        if st in ("scoring", "stopped"):
            raise LookRefused(f"refused: the stage2 block is {st!r}; a look that began is "
                              "never rerun")
        if st == "complete":
            if s2.get("verdict") in VERDICTS_FINAL:
                raise LookRefused(f"refused: stage 2 recorded {s2.get('verdict')}, which "
                                  "is final")
            if s2.get("season") == season:
                raise LookRefused(f"refused: stage 2 already recorded {s2.get('verdict')} "
                                  f"for {season}; it waits for the next season")
    check_section_results(doc_text, season)


def check_section_results(doc_text: str | None, season: int) -> None:
    """The section's half of the one-run guard: a final stage-2 heading, or one for this
    season, refuses."""
    for m in STAGE2_HEADING_RE.finditer(section_text(doc_text).replace("\r\n", "\n")):
        run, verdict = m.group(1), m.group(2)
        if verdict in VERDICTS_FINAL:
            raise LookRefused(f"refused: the section records a final stage-2 result "
                              f"({verdict}, run {run})")
        if int(run[:4]) == season:
            raise LookRefused(f"refused: the section records a stage-2 result for "
                              f"{season} ({verdict})")


def check_out_path(out: Path) -> Path:
    return swl.check_out_path(out)


def write_artifact(art: dict, path: Path) -> None:
    """Writes the section's own artifact; never the nightly betting eval."""
    p = Path(path).resolve()
    if p == BETTING_EVAL.resolve() or p.name == BETTING_EVAL.name:
        raise LookRefused("refused: stage 2 never writes data/betting_model_eval.json")
    swl.write_artifact(art, p)


# ---------------------------------------------------------------------------
# Sources: the vintage store (the look) and a fixture (tests and the dry run)
# ---------------------------------------------------------------------------
class DayInputs:
    """One vintage night as the look reads it: the served team, starter and park inputs
    (the same objects the backtest prices on), the league P/PA anchor, and the dated
    pitcher and team columns by name."""

    def __init__(self, teams, starters, parks, l_ppa, pitcher_cols, team_cols,
                 vintage_date=None):
        self.teams, self.starters, self.parks = teams, starters, parks
        self.l_ppa = l_ppa
        self.pitcher_cols = pitcher_cols        # {mlbam int: {column: value}}
        self.team_cols = team_cols              # {org: {column: value}}
        self.vintage_date = vintage_date

    def pitcher(self, mlbam) -> dict:
        return self.pitcher_cols.get(mlbam) or {}

    def team(self, org) -> dict:
        return self.team_cols.get(org) or {}


class VintageSource:
    """The vintage store, through the served readers only: betting_model.inputs_as_of with
    no fallback (never a live file), leaderboard_vintages.as_of for the dated columns by
    the record's own column lists (an older record reads None), and the regular-season
    completed games of the look's season alone."""

    kind = "vintage"

    def __init__(self, team_names=("bat_ppa_l30",), pitcher_names=("sp_budget", "sp_ppo")):
        import betting_model as bm
        import leaderboard_vintages as lv
        self.bm, self.lv = bm, lv
        self.team_names = tuple(team_names)
        self.pitcher_names = tuple(pitcher_names)
        self._days: dict = {}

    def games(self, season: int) -> list:
        return list(self.bm.completed_games(season=str(season), refresh=False))

    @staticmethod
    def _by_cols(rec: dict, kind: str, key, names) -> dict:
        row = ((rec or {}).get(kind) or {}).get(str(key))
        cols = list((rec or {}).get("team_columns" if kind == "teams"
                                    else "pitcher_columns") or ())
        pos = {c: i for i, c in enumerate(cols)}
        if not isinstance(row, list):
            return {n: None for n in names}
        return {n: (row[pos[n]] if n in pos and pos[n] < len(row) else None) for n in names}

    def day(self, date: str) -> DayInputs | None:
        if date in self._days:
            return self._days[date]
        b = self.bm.inputs_as_of(date, allow_fallback=False)
        rec = self.lv.as_of(date)
        if b.get("source") != "vintage" or not b.get("teams") or not rec:
            self._days[date] = None
            return None
        parks = b.get("parks")
        if parks is None:
            parks = self.bm.NEUTRAL_PARK_INDEX
        anchors = ((rec.get("sw_basis") or {}).get("anchors") or {})
        pcols = {}
        for mid in (rec.get("pitchers") or {}):
            try:
                pcols[int(mid)] = self._by_cols(rec, "pitchers", mid, self.pitcher_names)
            except (TypeError, ValueError):
                continue
        tcols = {org: self._by_cols(rec, "teams", org, self.team_names)
                 for org in (rec.get("teams") or {})}
        d = DayInputs(b["teams"], b["starters"], parks, anchors.get("L_ppa"), pcols, tcols,
                      rec.get("vintage_date"))
        self._days[date] = d
        return d


# ---------------------------------------------------------------------------
# Records: features only (no outcome is read to build them)
# ---------------------------------------------------------------------------
def candidate_xouts(budget, ppo, opp_ppa, l_ppa):
    """The one candidate function (betting_usage), never a second definition."""
    import betting_usage as bu
    return bu.starter_workload_xouts_candidate(budget, ppo, opp_ppa, l_ppa)


def _neighbour_value(name: str, day: DayInputs, starter: dict, org: str):
    if name == INNINGS_SHARE_COLUMN:
        import betting_model as bm
        share, _plus, _src = bm._starter_share(day.teams.get(org) or {}, starter)
        return share
    pv = day.pitcher(starter.get("mlbam")) if starter else {}
    if name in pv:
        return pv.get(name)
    return day.team(org).get(name)


def build_records(source, season: int, neighbours) -> tuple[list, dict]:
    """One record per completed regular-season game of `season` whose vintage resolves
    and whose two probables both carry SEM+ and an xOuts. Reads no outcome: the record
    keeps a reference to the game row for the grader and copies no score."""
    counts = Counter()
    recs = []
    games = source.games(season)
    lo, hi = f"{season}-01-01", f"{season + 1}-01-01"
    for g in games:
        d = str(g.get("date") or "")
        if not (lo <= d < hi) or str(g.get("season") or season) != str(season):
            raise LookRefused(f"refused: the source handed a game dated {d!r}; stage 2 "
                              f"reads {season} games only (the 2026 fit window is never "
                              "graded)")
        if g.get("game_type") in POSTSEASON_TYPES:
            counts["postseason_excluded"] += 1
            continue
        counts["games"] += 1
        day = source.day(d)
        if day is None:
            counts["no_vintage"] += 1
            continue
        h, a = day.teams.get(g["home_org"]), day.teams.get(g["away_org"])
        if not h or not a:
            counts["club_missing_from_vintage"] += 1
            continue
        sides = {}
        why = None
        for side, sp_key, opp_org in (("home", "home_sp", g["away_org"]),
                                      ("away", "away_sp", g["home_org"])):
            mid = g.get(sp_key)
            st = day.starters.get(mid) if mid is not None else None
            if mid is None:
                why = why or "probable_not_listed"
                continue
            if not st or st.get("sem_plus") is None:
                why = why or "probable_without_sem_plus"
                continue
            pv = day.pitcher(mid)
            x = candidate_xouts(pv.get("sp_budget"), pv.get("sp_ppo"),
                                day.team(opp_org).get("bat_ppa_l30"), day.l_ppa)
            if x is None:
                why = why or "xouts_null"
                continue
            org = g["home_org"] if side == "home" else g["away_org"]
            sides[side] = {"mlbam": mid, "starter": st, "xouts": float(x), "org": org,
                           "nb": {n: _neighbour_value(n, day, st, org) for n in neighbours}}
        if len(sides) < 2:
            counts[why or "probable_not_populated"] += 1
            continue
        recs.append({"game_pk": g.get("game_pk"), "date": d, "game": g, "day": day,
                     "sides": sides})
    counts["populated"] = len(recs)
    return recs, dict(counts)


def split_records(recs: list) -> dict:
    """The served vintage split, by date: the fit window is the first 300 populated games
    (whole slates), the eval half every later one."""
    import betting_model as bm
    dates = sorted({r["date"] for r in recs})
    if len(dates) < 2:
        return {"cut": None, "fit": [], "eval": [], "dates": len(dates)}
    cut = dates[bm._vintage_cut_index(recs, dates)]
    fit = [r for r in recs if r["date"] < cut]
    ev = [r for r in recs if r["date"] >= cut]
    return {"cut": cut, "fit": fit, "eval": ev, "dates": len(dates)}


def criterion4(n_fit: int, n_eval: int) -> bool:
    return n_fit >= FIT_TARGET_GAMES and n_eval >= MIN_EVAL_GAMES


# ---------------------------------------------------------------------------
# The two arms, through the served grader
# ---------------------------------------------------------------------------
def _starter_for(side: dict, xouts: float | None) -> dict:
    st = side["starter"]
    if xouts is None:
        return st
    c = dict(st)
    c["ip_per_gs"] = float(xouts) / 3.0        # _starter_share: share = xIP / 9 = xOuts / 27
    return c


def _resolver(recs: list, xouts_map: dict | None):
    """resolve(game) -> (teams, {probable: starter}, parks) per game. The incumbent arm
    reads the served starter rows; the candidate arm the same rows with the innings
    share replaced by xOuts / 27 (clipped by _starter_share, the served clip)."""
    by_pk = {}
    for r in recs:
        g = r["game"]
        sts = {}
        for side, key in (("home", "home_sp"), ("away", "away_sp")):
            x = None if xouts_map is None else xouts_map[(r["game_pk"], side)]
            sts[g[key]] = _starter_for(r["sides"][side], x)
        by_pk[r["game_pk"]] = (r["day"].teams, sts, r["day"].parks)
    return lambda g: by_pk.get(g.get("game_pk"))


def served_grader():
    import betting_model as bm
    return bm._backtest_grader({}, {}, {})


def grade_arm(grade_fn, fit: list, ev: list, xouts_map: dict | None, label: str) -> dict:
    out = grade_fn([r["game"] for r in fit], [r["game"] for r in ev], label, "vintage",
                   _resolver(fit + ev, xouts_map))
    if not out:
        return {"p": {}, "fit": None}
    keep = ("coefficients", "home_field_runs_adj", "diff_shrink", "run_dispersion_alpha",
            "extra_inning_home_rate")
    return {"p": dict(out.get("_per_game_p") or {}),
            "fit": {k: out.get(k) for k in keep}}


def xouts_of(recs: list) -> dict:
    return {(r["game_pk"], s): r["sides"][s]["xouts"] for r in recs for s in ("home", "away")}


def permuted_xouts(recs: list, seed: int) -> dict:
    """The twin: each date's xOuts values permuted across that date's probables."""
    rng = np.random.default_rng(seed)
    by_date = defaultdict(list)
    for r in recs:
        for s in ("home", "away"):
            by_date[r["date"]].append(((r["game_pk"], s), r["sides"][s]["xouts"]))
    out = {}
    for d in sorted(by_date):
        items = sorted(by_date[d], key=lambda kv: (str(kv[0][0]), kv[0][1]))
        vals = np.array([v for _k, v in items], dtype=float)
        perm = vals[rng.permutation(len(vals))]
        for (k, _v), pv in zip(items, perm):
            out[k] = float(pv)
    return out


# ---------------------------------------------------------------------------
# The statistics
# ---------------------------------------------------------------------------
def outcome(g: dict) -> int:
    return 1 if g["home_runs"] > g["away_runs"] else 0


def brier(p: float, y: int) -> float:
    return (float(p) - y) ** 2


def logloss(p: float, y: int) -> float:
    p = float(p)
    return -(y * math.log(max(p, LOGLOSS_EPS)) + (1 - y) * math.log(max(1 - p, LOGLOSS_EPS)))


def paired(inc: dict, cand: dict, recs: list) -> dict:
    """Per-game paired Brier and log-loss differences, served minus candidate (a positive
    difference is a candidate improvement), over the games both arms priced."""
    pks = [r["game_pk"] for r in recs if r["game_pk"] in inc and r["game_pk"] in cand]
    ys = {r["game_pk"]: outcome(r["game"]) for r in recs}
    d = [brier(inc[k], ys[k]) - brier(cand[k], ys[k]) for k in pks]
    ll_inc = [logloss(inc[k], ys[k]) for k in pks]
    ll_cand = [logloss(cand[k], ys[k]) for k in pks]
    b_inc = [brier(inc[k], ys[k]) for k in pks]
    return {"pks": pks, "d": d, "ll_inc": ll_inc, "ll_cand": ll_cand, "b_inc": b_inc}


def paired_stats(d) -> dict:
    """mean, sd (n - 1), t = mean / (sd / sqrt(n)), one-sided normal p."""
    d = np.asarray(list(d), dtype=float)
    n = int(d.size)
    if n < 2:
        return {"n": n, "mean": _r(d.mean()) if n else None, "sd": None, "t": None,
                "p_one_sided": None}
    mean = float(d.mean())
    sd = float(d.std(ddof=1))
    if sd <= 0:
        return {"n": n, "mean": _r(mean, 8), "sd": 0.0, "t": None, "p_one_sided": None}
    t = mean / (sd / math.sqrt(n))
    p = 0.5 * math.erfc(t / math.sqrt(2.0))
    return {"n": n, "mean": _r(mean, 8), "sd": _r(sd, 8), "t": _r(t, 6),
            "p_one_sided": _r(p, 8)}


def holm_n6(p_self, others: dict | None = None) -> dict:
    """Holm step-down over N6 (m = 4, family alpha 0.05 one-sided). A member with no
    recorded p cannot be rejected and sits at p = 1; with no other member read the
    candidate's p is read at 0.05 / 4 = 0.0125."""
    others = dict(others or {})
    ps = {m: (others.get(m) if m != N6_SELF else p_self) for m in N6_MEMBERS}
    eff = {m: (1.0 if v is None else float(v)) for m, v in ps.items()}
    order = sorted(N6_MEMBERS, key=lambda m: (eff[m], m))
    m_total = len(N6_MEMBERS)
    rejected = set()
    for i, mem in enumerate(order):
        if ps[mem] is None or eff[mem] > N6_ALPHA / (m_total - i):
            break
        rejected.add(mem)
    threshold_self = N6_ALPHA / (m_total - order.index(N6_SELF))
    return {"m": m_total, "members": {m: ps[m] for m in N6_MEMBERS},
            "not_read": [m for m in N6_MEMBERS if ps[m] is None],
            "threshold_self": _r(threshold_self, 6), "pass": N6_SELF in rejected}


def power_precondition(sd_d) -> dict:
    """(2.241 + 0.842) x sd_d / sqrt(600) against the floor 0.0024; None sd is not
    powered."""
    k = (POWER_Z_ALPHA + POWER_Z_POWER) / math.sqrt(POWER_N)
    if sd_d is None:
        return {"sd_d": None, "multiplier": _r(k, 6), "mde": None, "floor": FLOOR_BRIER,
                "status": "UNDERPOWERED"}
    mde = k * float(sd_d)
    return {"sd_d": _r(sd_d, 8), "multiplier": _r(k, 6), "mde": _r(mde, 8),
            "floor": FLOOR_BRIER, "status": "UNDERPOWERED" if mde > FLOOR_BRIER else "POWERED",
            "basis": "in-sample fit-window sd, lenient"}


def twin_bar(improvements) -> float | None:
    a = np.asarray(list(improvements), dtype=float)
    if a.size == 0:
        return None
    return float(np.percentile(a, TWIN_PERCENTILE))


def vif_one(y, x) -> float | None:
    return vif(y, [x])


def vif(y, xs) -> float | None:
    """1 / (1 - R^2) of y regressed with an intercept on the columns xs (rows already
    complete). None when there are too few rows or the regression is degenerate."""
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(y.size)] + [np.asarray(c, dtype=float) for c in xs])
    if y.size <= X.shape[1] or float(np.var(y)) <= 0:
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1.0 - float((resid ** 2).sum()) / float(((y - y.mean()) ** 2).sum())
    if r2 >= 1.0:
        return math.inf
    return 1.0 / (1.0 - r2)


def vif_table(recs: list, neighbours) -> dict:
    """The candidate share against each neighbour alone and against all of them, over
    the eval half's probable sides with values."""
    rows = []
    for r in recs:
        for s in ("home", "away"):
            side = r["sides"][s]
            rows.append((_clip_share(side["xouts"] / OUTS_PER_GAME), side["nb"]))
    table = {}
    for n in neighbours:
        sub = [(y, nb[n]) for y, nb in rows if nb.get(n) is not None]
        v = vif_one([a for a, _ in sub], [b for _, b in sub]) if sub else None
        table[n] = {"rows": len(sub), "vif": _r(v, 6) if v is not None and math.isfinite(v)
                    else (None if v is None else "inf")}
    present = [n for n in neighbours if table[n]["rows"] > 0]
    full = [(y, nb) for y, nb in rows if all(nb.get(n) is not None for n in present)]
    joint = (vif([a for a, _ in full], [[nb[n] for _, nb in full] for n in present])
             if present and full else None)
    return {"rows": len(rows), "by_neighbour": table,
            "joint": {"neighbours": present, "absent": [n for n in neighbours
                                                         if n not in present],
                      "rows": len(full),
                      "vif": (None if joint is None else
                              (_r(joint, 6) if math.isfinite(joint) else "inf"))}}


def _vif_ok(v) -> bool:
    return v is not None and v != "inf" and float(v) <= VIF_BAR


def criterion5(table: dict) -> bool:
    inn = table["by_neighbour"].get(INNINGS_SHARE_COLUMN, {}).get("vif")
    joint = table["joint"]["vif"]
    return _vif_ok(inn) and (joint is None or _vif_ok(joint))


def decide(c: dict, mean_improvement) -> str:
    """ALL of (1) to (5); a pass of (1) under the floor is PASS-BELOW-FLOOR."""
    if all(c.get(k) for k in ("1_paired_brier_t_and_holm", "2_log_loss_not_worse",
                              "3_permuted_twin", "4_games", "5_vif")):
        return ("PASS" if mean_improvement is not None and mean_improvement >= FLOOR_BRIER
                else "PASS-BELOW-FLOOR")
    return "FAIL"


def share_comparison(recs: list) -> dict:
    cand, served = [], []
    for r in recs:
        for s in ("home", "away"):
            side = r["sides"][s]
            cand.append(_clip_share(side["xouts"] / OUTS_PER_GAME))
            served.append(side["nb"].get(INNINGS_SHARE_COLUMN))
    pairs = [(a, b) for a, b in zip(cand, served) if b is not None]
    if not pairs:
        return {"sides": 0}
    a = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    corr = (float(np.corrcoef(a, b)[0, 1]) if a.size > 1 and a.std() > 0 and b.std() > 0
            else None)
    return {"sides": int(a.size), "candidate_mean": _r(a.mean()), "served_mean": _r(b.mean()),
            "mean_abs_diff": _r(np.abs(a - b).mean()), "correlation": _r(corr),
            "candidate_at_clip": int(((a <= SHARE_CLIP[0]) | (a >= SHARE_CLIP[1])).sum())}


def coverage_per_club(recs: list) -> dict:
    c = Counter()
    for r in recs:
        for s in ("home", "away"):
            c[r["sides"][s]["org"]] += 1
    return dict(sorted(c.items()))


# ---------------------------------------------------------------------------
# The look
# ---------------------------------------------------------------------------
def _base_block(season, clock, mode, neighbours, mgmt) -> dict:
    return {"season": season, "status": None, "verdict": None, "mode": mode,
            "clock": clock, "tool": "tools/betting_workload_gate.py",
            "registered": {"fit_target_games": FIT_TARGET_GAMES,
                           "min_eval_games": MIN_EVAL_GAMES, "t_bar": T_BAR,
                           "n6_members": list(N6_MEMBERS), "n6_alpha": N6_ALPHA,
                           "n_twin": N_TWIN, "twin_percentile": TWIN_PERCENTILE,
                           "vif_bar": VIF_BAR, "floor_brier": FLOOR_BRIER,
                           "power_z": [POWER_Z_ALPHA, POWER_Z_POWER], "power_n": POWER_N,
                           "share_clip": list(SHARE_CLIP),
                           "vif_neighbours": list(neighbours)},
            "choices": dict(CHOICES), "mgmt_policy_gate": mgmt,
            "writes": "this stage2 block only; never data/betting_model_eval.json"}


def _put(art: dict, block: dict, path: Path) -> None:
    prev = art.get("stage2")
    if (isinstance(prev, dict) and prev.get("status") == "complete"
            and prev.get("season") != block.get("season")):
        block.setdefault("prior_seasons", list(prev.get("prior_seasons") or []))
        block["prior_seasons"].append({k: v for k, v in prev.items() if k != "prior_seasons"})
    art["stage2"] = block
    write_artifact(art, path)


def record_yield(art: dict, path: Path, season: int, today: _dt.date, reasons: list) -> dict:
    prev = art.get("stage2") if isinstance(art.get("stage2"), dict) else {}
    if prev.get("season") == season and prev.get("status") == "yielding":
        block = prev
    else:
        block = {"season": season, "status": "yielding", "verdict": None, "yields": []}
        if prev.get("status") == "complete":
            block["prior_seasons"] = list(prev.get("prior_seasons") or []) + [
                {k: v for k, v in prev.items() if k != "prior_seasons"}]
    block.setdefault("yields", []).append({"date": _as_date(today).isoformat(),
                                           "reasons": list(reasons)})
    art["stage2"] = block
    write_artifact(art, path)
    return block


def run_stage2(source, artifact_path: Path, *, today, mode: str, clock: dict | None = None,
               doc_text: str | None = None, mgmt: dict | None = None,
               other_looks: list | None = None, n_twin: int = N_TWIN, grade_fn=None,
               log=print) -> dict:
    """The look after the guards. Returns the stage2 block it wrote (a yield writes only
    its yield)."""
    today = _as_date(today)
    season = today.year
    art = _load_artifact(artifact_path)
    if not art or not isinstance(art.get("stage1"), dict):
        raise LookRefused("refused: the artifact holds no stage-1 block; stage 2 reads the "
                          "stage-1 record first")
    neighbours = registered_vif_neighbours(doc_text)
    block = _base_block(season, clock or {"today": today.isoformat()}, mode, neighbours,
                        mgmt)
    s1 = art["stage1"].get("verdict")
    if s1 != "PASS":
        block.update(status="complete", verdict="NOT READ", completed_at=_now(),
                     reason=f"stage 1 recorded {s1!r}, not PASS; stage 2 is not read")
        _put(art, block, artifact_path)
        return block
    if other_looks:
        log("yield: another registered look falls on this day")
        return record_yield(art, artifact_path, season, today, other_looks)
    if mgmt is None:
        if today < WAIT_FOR_NEXT_SEASON:
            raise LookRefused("refused: 5l's mgmt_policy_gate block does not exist; the "
                              "look waits for it")
        block.update(status="complete", verdict="NOT READ", completed_at=_now(),
                     reason=f"5l's mgmt_policy_gate block did not exist by "
                            f"{WAIT_FOR_NEXT_SEASON}; the look waits for {season + 1}")
        _put(art, block, artifact_path)
        return block

    grade_fn = grade_fn or served_grader()
    recs, counts = build_records(source, season, neighbours)
    sp = split_records(recs)
    fit, ev = sp["fit"], sp["eval"]
    block["counts"] = counts
    block["split"] = {"cut": sp["cut"], "dates": sp["dates"], "n_fit_games": len(fit),
                      "n_eval_games": len(ev),
                      "fit_first_date": fit[0]["date"] if fit else None,
                      "fit_last_date": fit[-1]["date"] if fit else None,
                      "eval_first_date": ev[0]["date"] if ev else None,
                      "eval_last_date": ev[-1]["date"] if ev else None}
    c4 = criterion4(len(fit), len(ev))
    log(f"populated games {len(recs)}: fit {len(fit)}, eval {len(ev)}; criterion 4 "
        f"{'holds' if c4 else 'does not hold'}")
    if not c4:
        if today < WAIT_FOR_NEXT_SEASON:
            return record_yield(art, artifact_path, season, today, [
                f"criterion 4: {len(ev)} eval-half games behind {len(fit)} fit games, "
                f"under {MIN_EVAL_GAMES} behind {FIT_TARGET_GAMES}"])
        block.update(status="complete", verdict="NOT READ", completed_at=_now(),
                     reason=f"criterion 4 did not hold by {WAIT_FOR_NEXT_SEASON}; the look "
                            f"waits for {season + 1}")
        _put(art, block, artifact_path)
        return block

    # Scoring begins: the block is on disk before any outcome is read.
    block["status"] = "scoring"
    block["scoring_began_at"] = _now()
    _put(art, block, artifact_path)
    try:
        xo = xouts_of(fit + ev)
        # The power precondition, on the fit window only, before any eval-half game.
        inc_fit = grade_arm(grade_fn, fit, fit, None, "served arm, fit window in-sample")
        cand_fit = grade_arm(grade_fn, fit, fit, xo, "candidate arm, fit window in-sample")
        pf = paired(inc_fit["p"], cand_fit["p"], fit)
        sd_fit = paired_stats(pf["d"])["sd"]
        power = power_precondition(sd_fit)
        power["n_fit_paired"] = len(pf["d"])
        block["power_precondition"] = power
        _put(art, block, artifact_path)
        log(f"power: sd_d {power['sd_d']}, MDE {power['mde']} against {FLOOR_BRIER}: "
            f"{power['status']}")
        if power["status"] == "UNDERPOWERED":
            block.update(status="complete", verdict="UNDERPOWERED", completed_at=_now(),
                         reason="the power precondition failed; the eval half is not read "
                                f"and the look waits for {season + 1}")
            _put(art, block, artifact_path)
            return block

        inc = grade_arm(grade_fn, fit, ev, None, "served arm")
        cand = grade_arm(grade_fn, fit, ev, xo, "candidate arm")
        pe = paired(inc["p"], cand["p"], ev)
        st = paired_stats(pe["d"])
        holm = holm_n6(st["p_one_sided"])
        ll_inc = float(np.mean(pe["ll_inc"])) if pe["ll_inc"] else None
        ll_cand = float(np.mean(pe["ll_cand"])) if pe["ll_cand"] else None
        twins = []
        for k in range(n_twin):
            tw = grade_arm(grade_fn, fit, ev, permuted_xouts(fit + ev, k), f"twin {k}")
            td = paired(inc["p"], tw["p"], ev)["d"]
            twins.append(float(np.mean(td)) if td else float("nan"))
        bar = twin_bar([t for t in twins if math.isfinite(t)])
        vt = vif_table(ev, neighbours)
        crit = {
            "1_paired_brier_t_and_holm": bool(st["t"] is not None and st["t"] >= T_BAR
                                              and holm["pass"]),
            "2_log_loss_not_worse": bool(ll_inc is not None and ll_cand is not None
                                         and ll_cand <= ll_inc),
            "3_permuted_twin": bool(bar is not None and st["mean"] is not None
                                    and st["mean"] > bar),
            "4_games": bool(c4 and len(pe["d"]) >= MIN_EVAL_GAMES),
            "5_vif": criterion5(vt),
        }
        verdict = decide(crit, st["mean"])
        block.update({
            "n_eval_paired": len(pe["d"]),
            "brier": {"served": _r(np.mean(pe["b_inc"]), 8) if pe["b_inc"] else None,
                      "candidate": _r(np.mean(pe["b_inc"]) - st["mean"], 8)
                      if pe["b_inc"] and st["mean"] is not None else None},
            "paired_brier": st, "holm_n6": holm,
            "log_loss": {"served": _r(ll_inc, 8), "candidate": _r(ll_cand, 8)},
            "twin": {"draws": n_twin, "bar_95": _r(bar, 8),
                     "candidate_rank": int(sum(1 for t in twins if t < (st["mean"] or 0))),
                     "quantiles": {q: _r(np.percentile(twins, q), 8)
                                   for q in (5, 25, 50, 75, 95)} if twins else None,
                     "improvements": [_r(t, 8) for t in twins]},
            "vif": vt,
            "fitted": {"served": inc["fit"], "candidate": cand["fit"]},
            "eval_half_power": {**power_precondition(st["sd"]),
                                "basis": "eval-half sd, a diagnostic beside the "
                                         "precondition; no threshold moves"},
            "share": share_comparison(ev),
            "coverage_per_club": {"fit": coverage_per_club(fit),
                                  "eval": coverage_per_club(ev)},
            "criteria": crit, "verdict": verdict,
            "contaminated_screen": ("not run: on a PASS it runs once, after the look, on "
                                    "the season-to-date form, disqualify-only"),
            "status": "complete", "completed_at": _now(),
        })
        _put(art, block, artifact_path)
        return block
    except Exception:
        block["status"] = "stopped"
        block["protocol"] = ("stopped after scoring began: never rerun; the question goes "
                             "to the owner")
        block["traceback"] = traceback.format_exc()[-2000:]
        try:
            _put(art, block, artifact_path)
        except Exception:                        # noqa: BLE001 - the original error wins
            pass
        raise


# ---------------------------------------------------------------------------
# The section's result heading
# ---------------------------------------------------------------------------
def result_heading(block: dict) -> str:
    run = (block.get("clock") or {}).get("today") or str(block.get("completed_at", ""))[:10]
    return f"### Stage 2 result (run {run}, once): {block['verdict']}"


def result_text(block: dict) -> str:
    def f(x):
        return "none" if x is None else f"{x}"

    lines = [result_heading(block), "",
             "Written by tools/betting_workload_gate.py into the stage2 block of "
             "data/starter_workload_eval.json."]
    if block.get("reason"):
        lines[-1] += f" {block['reason']}."
    sp = block.get("split")
    if sp:
        lines[-1] += (f" Fit window {sp['n_fit_games']} games ({f(sp['fit_first_date'])} to "
                      f"{f(sp['fit_last_date'])}), eval half {sp['n_eval_games']} games with "
                      f"both probables populated.")
    pw = block.get("power_precondition")
    if pw:
        lines[-1] += (f" Power precondition: in-sample sd_d {f(pw['sd_d'])}, MDE "
                      f"{f(pw['mde'])} against the floor {pw['floor']}, {pw['status']}.")
    if block.get("paired_brier"):
        pb, ll, tw = block["paired_brier"], block["log_loss"], block["twin"]
        vt = block["vif"]
        lines[-1] += (
            f" Paired Brier improvement (served minus candidate) {f(pb['mean'])} over "
            f"{pb['n']} games, t {f(pb['t'])}, one-sided p {f(pb['p_one_sided'])} read at "
            f"{f(block['holm_n6']['threshold_self'])} in N6; log loss served "
            f"{f(ll['served'])} against candidate {f(ll['candidate'])}; twin 95th "
            f"percentile {f(tw['bar_95'])} over {tw['draws']} draws; VIF against the "
            f"innings share {f(vt['by_neighbour'][INNINGS_SHARE_COLUMN]['vif'])}, joint "
            f"{f(vt['joint']['vif'])}. Criteria: "
            + ", ".join(f"{k} {'met' if v else 'not met'}" for k, v in
                        block["criteria"].items()) + ".")
    return "\n".join(lines)


def append_result(doc_path: Path, block: dict) -> None:
    """Append the stage-2 result under the section, before the rule that closes it, in
    the file's own line endings; refuses when the section already records one for the
    same season or a final one."""
    doc_path = Path(doc_path)
    raw = doc_path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    check_section_results(text, int(block["season"]))
    sec = section_text(text)
    start = text.index(sec)
    end = start + len(sec)
    body = sec.rstrip("\n")
    closing = ""
    if body.endswith("\n---"):
        body, closing = body[:-4].rstrip("\n"), "\n---"
    new_sec = body + "\n\n" + result_text(block) + "\n" + closing + "\n\n\n"
    out = text[:start] + new_sec + text[end:].lstrip("\n")
    if crlf:
        out = out.replace("\n", "\r\n")
    doc_path.write_bytes(out.encode("utf-8"))


# ---------------------------------------------------------------------------
# The synthetic fixture (the dry run and the tests): games with no vintage, a missing
# probable, a debut with no workload value, a club with no lineup value, null
# third-time-through and dugout neighbours
# ---------------------------------------------------------------------------
FIXTURE_CLUBS = tuple(f"C{i:02d}" for i in range(1, 13))


class FixtureSource:
    kind = "fixture"

    def __init__(self, games, days):
        self._games, self._days = games, days

    def games(self, season: int) -> list:
        return list(self._games)

    def day(self, date: str):
        return self._days.get(date)


def synthetic_source(seed: int = 11, n_dates: int = 172, season: int = FIRST_LOOK_SEASON,
                     neighbours=None, signal: float = 0.0) -> FixtureSource:
    """Twelve clubs, six games a night, five-man rotations. `signal` scales how much the
    starter's own expected outs (rather than the served innings share) carries the run
    prevention in the simulated runs."""
    import betting_model as bm
    neighbours = tuple(neighbours or ())
    extra_team = [n for n in neighbours if n not in (INNINGS_SHARE_COLUMN, "sp_tto3_bf")]
    rng = np.random.default_rng(seed)
    clubs = FIXTURE_CLUBS
    base = {o: {"off": 100 + rng.normal(0, 7), "rot": 100 + rng.normal(0, 7),
                "pen": 100 + rng.normal(0, 7), "ppa": 3.9 + rng.normal(0, 0.08)}
            for o in clubs}
    staff = {}
    for ci, o in enumerate(clubs):
        for s in range(5):
            mid = 600000 + ci * 10 + s
            true_outs = float(np.clip(rng.normal(16.0, 2.5), 9, 21))
            staff[mid] = {"org": o, "plus": 100 + rng.normal(0, 14),
                          "true_outs": true_outs,
                          "ip_per_gs": float(np.clip(true_outs / 3 + rng.normal(0.4, 0.5),
                                                     3.0, 7.5)),
                          "budget": 6.0 * true_outs * float(rng.normal(1.0, 0.04)),
                          "ppo": float(rng.normal(5.4, 0.25))}
    debut = 600000 + 3 * 10 + 4                       # no workload value all season
    games, days = [], {}
    d0 = _dt.date(season, 3, 30)
    pk = 7700000
    turn = Counter()
    for k in range(n_dates):
        d = (d0 + _dt.timedelta(days=k)).isoformat()
        off = {o: base[o]["off"] + rng.normal(0, 2) for o in clubs}
        rots = {o: base[o]["rot"] + rng.normal(0, 2) for o in clubs}
        pens = {o: base[o]["pen"] + rng.normal(0, 2) for o in clubs}
        sip = {o: 500.0 for o in clubs}
        rip = {o: 320.0 for o in clubs}
        extras = {o: {"bat_ppa_l30": (None if (o == "C12" and k < 12)
                                      else round(base[o]["ppa"] + rng.normal(0, 0.03), 5))}
                  for o in clubs}
        teams = bm._assemble_team_inputs(off, rots, pens, sip, rip, extras)
        starters, pcols = {}, {}
        for mid, s in staff.items():
            starters[mid] = {"mlbam": mid, "name": None, "org": s["org"],
                             "sem_plus": float(s["plus"]), "ip_per_gs": s["ip_per_gs"],
                             "role": "SP", "throws": None}
            pcols[mid] = {"sp_budget": None if mid == debut else round(s["budget"], 4),
                          "sp_ppo": None if mid == debut else round(s["ppo"], 5),
                          "sp_tto3_bf": (None if rng.random() < 0.15
                                         else round(4.4 + rng.normal(0, 1.0), 2))}
        tcols = {}
        for o in clubs:
            tcols[o] = {"bat_ppa_l30": extras[o]["bat_ppa_l30"]}
            for n in extra_team:
                tcols[o][n] = (None if (k < 20 or rng.random() < 0.1)
                               else round(88 + rng.normal(0, 5), 1))
        if k >= 2:                                    # the first two nights have no vintage
            days[d] = DayInputs(teams, starters, {o: 1.0 for o in clubs}, 3.9, pcols, tcols,
                                d)
        order = list(clubs)
        rng.shuffle(order)
        for j in range(0, len(order), 2):
            h, a = order[j], order[j + 1]
            sps = {}
            for o in (h, a):
                ci = clubs.index(o)
                sps[o] = 600000 + ci * 10 + turn[o] % 5
                turn[o] += 1
            pk += 1
            home_sp = None if pk % 41 == 0 else sps[h]  # a probable not listed
            lam = {}
            for o, opp in ((h, a), (a, h)):
                st = staff[sps[opp]]
                share = ((1 - signal) * st["ip_per_gs"] / 9.0
                         + signal * st["true_outs"] / 27.0)
                prev = share * st["plus"] + (1 - share) * base[opp]["pen"]
                lam[o] = max(1.5, 4.5 + 0.03 * (off[o] - 100) - 0.03 * (prev - 100)
                             + (0.15 if o == h else 0.0))
            hr, ar = int(rng.poisson(lam[h])), int(rng.poisson(lam[a]))
            innings = 9
            if hr == ar:
                innings = 10
                if rng.random() < 0.52:
                    hr += 1
                else:
                    ar += 1
            games.append({"game_pk": pk, "date": d, "season": str(season),
                          "home_org": h, "away_org": a, "home_sp": home_sp,
                          "away_sp": sps[a], "home_runs": hr, "away_runs": ar,
                          "innings": innings})
    return FixtureSource(games, days)


def fixture_artifact(stage1_verdict: str = "PASS") -> dict:
    return {"artifact": "starter_workload_eval", "section": SECTION_TITLE,
            "registry_row": REGISTRY_ROW, "mode": "dry_run_fixture",
            "stage1": {"status": "complete", "verdict": stage1_verdict}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="THE LOOK, once")
    mode.add_argument("--dry-run", action="store_true",
                      help="the reporting path on the synthetic fixture")
    ap.add_argument("--out", type=Path, help="dry run: the artifact path (never under data/)")
    ap.add_argument("--doc-out", type=Path,
                    help="dry run: a copy of docs/diamond-betting.md to append the heading to")
    ap.add_argument("--twin-draws", type=int, default=N_TWIN,
                    help="dry run only: twin draws (the run always draws 200)")
    ap.add_argument("--tee", type=Path, help="copy stdout and stderr to this file first")
    args = ap.parse_args(argv)
    fh = None
    saved = sys.stdout, sys.stderr
    if args.tee:
        args.tee.parent.mkdir(parents=True, exist_ok=True)
        fh = open(args.tee, "a", encoding="utf-8")
        sys.stdout, sys.stderr = swl._Tee(sys.stdout, fh), swl._Tee(sys.stderr, fh)
    try:
        if args.dry_run:
            if args.out is None:
                ap.error("--dry-run needs --out")
            out = check_out_path(args.out)
            doc_text = GATE_DOC.read_text(encoding="utf-8")
            write_artifact(fixture_artifact(), out)
            nb = registered_vif_neighbours(doc_text)
            today = EARLIEST_LOOK
            block = run_stage2(synthetic_source(neighbours=nb), out, today=today,
                               mode=f"dry_run_fixture (twin draws {args.twin_draws})",
                               doc_text=doc_text,
                               mgmt={"where": "fixture", "run_date": "2027-06-30"},
                               other_looks=[], n_twin=args.twin_draws)
            if block.get("status") == "complete" and args.doc_out is not None:
                doc_out = check_out_path(args.doc_out)
                doc_out.write_bytes(GATE_DOC.read_bytes())
                append_result(doc_out, block)
            print(result_text(block) if block.get("verdict") else json.dumps(block))
            return 0
        today = _dt.date.today()
        clock = check_clock(today)
        doc_text = GATE_DOC.read_text(encoding="utf-8")
        check_one_run(ARTIFACT, doc_text, today.year)
        mgmt = mgmt_policy_block(doc_text)
        others = other_looks_on(today, mgmt=mgmt)
        nb = registered_vif_neighbours(doc_text)
        src = VintageSource(team_names=("bat_ppa_l30",) + tuple(
            n for n in nb if n not in (INNINGS_SHARE_COLUMN, "sp_tto3_bf")),
            pitcher_names=("sp_budget", "sp_ppo", "sp_tto3_bf"))
        block = run_stage2(src, ARTIFACT, today=today, mode="run", clock=clock,
                           doc_text=doc_text, mgmt=mgmt, other_looks=others)
        if block.get("status") == "yielding":
            print(f"yielded on {today}: {block['yields'][-1]['reasons']}")
            return 3
        append_result(GATE_DOC, block)
        print(result_text(block))
        return 0
    except (LookRefused, swl.LabRefused) as exc:
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
