#!/usr/bin/env python
"""The In-Game Management DECISION LEDGER: every decision the play corpus can name,
the window each one governed, and the win probability that actually moved inside it.

REALIZED VALUE, NOT SKILL. Every family here is priced as the win probability that
moved after the decision, credited to the club that made it, from the decision to the
last play it governed. What the alternative would have produced (the reliever not
used, the batter not lifted, the pitch not thrown) is not observed, so nothing on this
surface ranks a club or a manager by decision QUALITY. RIV+ was deprecated for exactly
that overreach, and a manager WPA figure is the same trap. The only families with a
priced counterfactual are the steal (management.py) and the sacrifice bunt
(mgmt_bunt.py), and the steal's per-club value FAILED its gate (bounded null).

THE AGENT IS THE CLUB-SEASON. There is no manager entity anywhere on disk; the manager
ledger is a network ingest (plan lane M-MWAR-2) and until it lands every row here is a
club-season and says so. The 92 ejection rows that name a manager with an mlbam id are
the ingest's validation fixture, published as a count, never a source.

WINDOW VALUE IS AN ENDPOINT DIFFERENCE, NEVER A SUM OF wpa_home ROWS. wpa_home equals
wp_home_after minus wp_home_before on every play, but consecutive plays do NOT chain:
in-PA events (steals, wild pitches, pickoffs) move the state between plays and are
credited to neither, so summing wpa_home over a game misses part of the game's 50-point
journey. The realized value of a window is therefore

    mWPA(d) = s(club, half) * (wp_home_after[p1] - wp_home_before[p0]) / 100

with s = +1 for the home club and -1 for the away club, wp in percentage points. The
share of plays where the chain breaks is measured at CHAIN_TOL and published with it.

THE STATE THE MANAGER DECIDED FROM IS PRE-PLAY. The corpus score columns are POST-play
(audit F07-02); the pre-play score comes from win_expectancy.pre_play_score_diff. Base
occupancy is notna() on on_first / on_second / on_third (float ids, NaN empty;
bool(NaN) is True). leverage_index is null on the leadoff plate appearance of every
game and is carried as null, never 0.

Offline. Reads .cache/pbp_corpus, .cache/war_daily (names and club attribution),
.cache/win_prob (game dates only, first play's startTime), data/management_bunt.json
(the bunt DV cell beside each bunt's realized figure) and data/management_gate_eval.json
(the steal family's gate verdict). Writes data/management_decisions.json, the per
club-season shards under data/mgmt_decisions/ (mgmt_shards.py) and, through
mgmt_baseline.py, data/management_baseline.json.

    python mgmt_decisions.py [--seasons 2024,2025] [--no-shards]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS = ROOT / ".cache" / "pbp_corpus"
WIN_PROB = ROOT / ".cache" / "win_prob"
WAR_DAILY = ROOT / ".cache" / "war_daily"
PLAYER_LINKS = ROOT / "data" / "player_links.json"
BUNT = ROOT / "data" / "management_bunt.json"
GATE_EVAL = ROOT / "data" / "management_gate_eval.json"
DATES_CACHE = ROOT / ".cache" / "mgmt_game_dates.json"
OUT = ROOT / "data" / "management_decisions.json"
SHARD_DIR = ROOT / "data" / "mgmt_decisions"

log = logging.getLogger(__name__)

#: Tolerance at which two consecutive plays are said to chain (the previous play's
#: wp_home_after equals this play's wp_home_before). The chain-break share is
#: tolerance-dependent, so the constant travels in the payload beside the share.
CHAIN_TOL = 1e-9

#: The nine families the corpus can name. Order is the page order.
FAMILIES = ("pitching_change", "pinch_hit", "pinch_run", "defensive_sub",
            "intentional_walk", "bunt", "steal", "mound_visit", "ejection")
#: Families with a realized window.
WINDOW_FAMILIES = ("pitching_change", "pinch_hit", "pinch_run", "defensive_sub",
                   "intentional_walk", "bunt", "steal")
#: Families whose realized value is summed on a club-season row. The defensive
#: sub's rest-of-game window is dominated by everything but the glove, so it is
#: stored on each decision and never summed (spec 3.4).
SUMMED_FAMILIES = ("pitching_change", "pinch_hit", "pinch_run", "intentional_walk",
                   "bunt", "steal")
COUNTED_ONLY = ("mound_visit", "ejection")

LABEL = {"pitching_change": "Pitching changes", "pinch_hit": "Pinch hitters",
         "pinch_run": "Pinch runners", "defensive_sub": "Defensive subs",
         "intentional_walk": "Intentional walks", "bunt": "Bunts", "steal": "Steals",
         "mound_visit": "Mound visits", "ejection": "Ejections"}

#: Sample floors: a club-season row shows a family's realized figure only at or
#: above the floor (spec 6.1). Published in the payload so the page reads them.
FLOORS = {"pitching_change": 100, "pinch_hit": 40, "pinch_run": 15,
          "intentional_walk": 8, "bunt": 20, "steal": 30, "defensive_sub": 30}
#: Games managed for a manager row to appear at all (club-seasons are complete
#: seasons and always clear it; 2026 is partial and is tagged).
GAMES_FLOOR = 40
#: A club-season with fewer games than this is tagged partial (the current season
#: ends at the corpus rebuild date).
PARTIAL_GAMES = 150

WINDOW_RULE = {
    "pitching_change": ("from the plate appearance the reliever enters to the last one "
                        "he pitches: the next pitching change for that side, or the end "
                        "of the game"),
    "pinch_hit": "the plate appearance",
    "pinch_run": "from the plate appearance at entry to the last play of the half-inning",
    "defensive_sub": ("from the plate appearance at entry to the end of the game; stored "
                      "on each decision and never summed into a leaderboard"),
    "intentional_walk": ("the walk plus the on-deck plate appearance, or the half's last "
                         "play if it ends sooner"),
    "bunt": "the plate appearance",
    "steal": "the plate appearance",
    "mound_visit": "none; counted only",
    "ejection": "none; counted only",
}

COUNTERFACTUAL = {
    "pitching_change": ("The pitcher not used is not observed. Pricing him needs the "
                        "availability model and the per-plate-appearance model, neither "
                        "built, so this family carries realized value only."),
    "pinch_hit": ("The batter not lifted is not observed. Pricing him needs the per-plate-"
                  "appearance model, not built, so this family carries realized value only."),
    "pinch_run": ("The runner not replaced is not observed. Pricing him needs the steal "
                  "model and sprint speed, so this family carries realized value only."),
    "defensive_sub": ("The glove not used is not observed, and the rest-of-game window is "
                      "dominated by everything but the glove, so this family ships timing "
                      "and usage only; its window value is stored and never summed."),
    "intentional_walk": ("Pitching to the batter is not observed. The state-matched league "
                         "baseline is measured over the hitters a manager was willing to "
                         "face, so it is biased for the walk; stated, not solved."),
    "bunt": ("The swing not taken is priced league-wide per state as the bunt DV "
             "(mgmt_bunt.py), a different quantity from the realized figure beside it; "
             "the bunt sign is not observable and the attempt is a proxy."),
    "steal": ("The hold is priced with a league-average runner as the steal DV "
              "(management.py); the model's realized change and the feed's realized "
              "mWPA are two estimators of one quantity and both ship."),
    "mound_visit": "Counted, never valued: a visit governs no play of its own.",
    "ejection": "Counted, never valued.",
}

#: Verbatim (spec 4.3). The page prints it on every leaderboard and club page.
REALIZED_SENTENCE = (
    "Realized value, not skill. Each figure is the win probability that actually moved "
    "after the decision, credited to the club that made it, from the decision to the last "
    "play it governed. What the alternative would have produced, the reliever not used, "
    "the batter not lifted, the pitch not thrown, is not observed, so this is a record of "
    "what happened after a manager acted and not a measure of how well he chose. A "
    "reliever who pitched well after a poor choice and a hitter who homered after a bad "
    "matchup are both in these numbers.")
AGENT_SENTENCE = (
    "The agent is the club-season until the manager ledger lands; a club that changed "
    "managers during a season is one row here and two in reality.")
STYLE_SENTENCE = (
    "Style, not skill: each is a signed z-score across the thirty club-seasons of its "
    "season, sign as measured. Not an index, no ladder, no plus sign; a frequency has no "
    "good direction, and these repeat because they are policy.")
SINGLE_PA_CAVEAT = (
    "For the single-plate-appearance families (pinch hit, bunt, steal) the league "
    "baseline is the mean realized change over every plate appearance from the same "
    "state, which a calibrated win model puts near zero, so value above state there is "
    "the realized figure plus the feed model's local miscalibration and is not an "
    "independent second number. It differs materially only for the stint-length windows "
    "(pitching change, pinch run, intentional walk).")
OVERLAP_NOTE = (
    "No cross-family total exists on any row. The family windows overlap: a club's "
    "intentional-walk window sits inside its own reliever's stint window, a pinch-hit "
    "plate appearance can contain that club's bunt or steal, and a pinch-run window "
    "overlaps the pinch hit before it, so one composite per club-season would double "
    "count. Per-family sums only.")
DVS_NOTE = (
    "Value above state removes the level of the state, so a club that faced many "
    "high-leverage spots is not credited for the spots. It does not remove player "
    "quality or selection (the manager chooses when to act), so it is realized value "
    "above what the league realized from the same spot: still descriptive, still not "
    "skill. It lives on the drill-down and the League census only, never on a club-"
    "season or manager row.")
LI_NOTE = (
    "Leverage is a cut and a style axis, never a weight in the value column: a high-"
    "leverage state already moves win probability more by itself, so multiplying by "
    "leverage would count it twice.")
INHERITED_DERIVATION = (
    "derived: the corpus carries no per-runner scoring id, so each inherited runner is "
    "tracked through on_first / on_second / on_third across the half-inning's later "
    "plays and counted as scored on the play where his id leaves the bases while "
    "runs_scored_on_play covers him, lead runner first; a runner who leaves with no run "
    "while the half continues was out, and a pinch runner continues the man he replaced.")
REMOVED_DERIVATION = (
    "derived: the events table carries replaced_player_id on about one pitching change in "
    "a hundred, and on a double switch that field names the lineup-slot occupant leaving, "
    "not the pitcher. The removed pitcher is the pitcher of the most recent plate "
    "appearance for the same fielding side before the change (or, when the previous change "
    "for that side sits at the same plate appearance, that change's entering pitcher); the "
    "derivation is checked against the description's replaces-NAME clause on every row and "
    "against the field on the rows whose description says replacing pitcher NAME.")

BUNT_RESULTS = ("Sac Bunt", "Bunt Groundout", "Bunt Pop Out", "Bunt Lineout",
                "Sac Bunt Double Play", "Bunt Ground Out", "Bunt Popout")
BUNT_CODES = ("L", "M", "O")           # foul bunt, missed bunt, bunt foul tip

_SWITCH_DH = re.compile(r" remains in the game as the designated hitter")
_SWITCH_FIELD = re.compile(r" remains in the game as the (right fielder|left fielder|"
                           r"first baseman|second baseman|center fielder|third baseman|"
                           r"catcher|shortstop|pitcher)")
_SWITCH_MOVE = re.compile(r"^Defensive switch from ")
_EJECT_ROLES = ("manager", "bench coach", "pitching coach", "hitting coach",
                "first base coach", "third base coach", "bullpen coach",
                "assistant hitting coach", "coach", "first baseman", "second baseman",
                "third baseman", "shortstop", "catcher", "pitcher", "left fielder",
                "center fielder", "right fielder", "designated hitter", "pinch hitter",
                "pinch runner", "outfielder", "infielder", "player")
_EJECT_RE = re.compile(r"^(?P<club>.+?) (?P<role>" + "|".join(
    re.escape(r) for r in sorted(_EJECT_ROLES, key=len, reverse=True))
    + r") (?P<name>.+?) ejected by")
_NICK_EXTRA = {"d-backs": "ARI", "dbacks": "ARI", "diamondbacks": "ARI",
               "athletics": "ATH", "a's": "ATH", "guardians": "CLE", "indians": "CLE"}

HOOK_BINS = list(range(0, 131, 10))   # starter pitch count at removal, 10-pitch bins


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------

def _r(v, nd=4):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else round(f, nd)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else int(f)
    except (TypeError, ValueError):
        return None


def _canon(code):
    try:
        import trades
        return trades.canonical_org(code) or code
    except Exception:                                   # noqa: BLE001
        return code


def window_mwpa(wp_before_p0, wp_after_p1, home_deciding: bool):
    """The rule of spec 4.1, in wins: s * (wp_home_after[p1] - wp_home_before[p0]) / 100.

    wp_* are PERCENTAGE POINTS (0.1 to 99.9). The sign flips to the deciding club: +1
    for the home club, -1 for the away club. An endpoint difference, never a sum of
    per-play wpa rows."""
    if wp_before_p0 is None or wp_after_p1 is None:
        return None
    a, b = float(wp_before_p0), float(wp_after_p1)
    if a != a or b != b:
        return None
    return (1.0 if home_deciding else -1.0) * (b - a) / 100.0


def deciding_club_is_home(half, side: str) -> bool:
    """Offensive decisions belong to the batting club (home in the bottom half);
    pitching and defensive decisions to the fielding club (home in the top half)."""
    bot = str(half).startswith("bot")
    return bot if side == "bat" else (not bot)


def base_code(on_first, on_second, on_third) -> int:
    """notna() occupancy, never bool(): the columns hold a runner id as a float with
    NaN for empty, and bool(NaN) is True."""
    def occ(v):
        return v is not None and v == v
    return (1 if occ(on_first) else 0) + (2 if occ(on_second) else 0) + (4 if occ(on_third) else 0)


def chain_break_stats(pl) -> dict:
    """Finding 0.3, measured: the per-play identity, the game endpoints and the share
    of consecutive plays that do not chain at CHAIN_TOL."""
    import numpy as np
    pl = pl.sort_values(["game_pk", "at_bat_index"])
    ident = float((pl["wpa_home"] - (pl["wp_home_after"] - pl["wp_home_before"])).abs().max())
    gp = pl["game_pk"].to_numpy()
    wb = pl["wp_home_before"].to_numpy(dtype=float)
    wa = pl["wp_home_after"].to_numpy(dtype=float)
    same = gp[1:] == gp[:-1]
    gap = np.abs(wb[1:] - wa[:-1])[same]
    breaks = gap > CHAIN_TOL
    first = pl.groupby("game_pk")["wp_home_before"].first()
    last = pl.groupby("game_pk")["wp_home_after"].last()
    summed = pl.groupby("game_pk")["wpa_home"].sum().abs()
    journey = (last - first).abs()
    missing = (journey - summed).abs()
    terminal = np.isin(np.round(last.to_numpy(dtype=float), 6), [0.0, 100.0])
    return {
        "per_play_identity_max_abs_error": _r(ident, 12),
        "games": int(len(first)),
        "games_start_at_fifty": bool(np.allclose(first.to_numpy(dtype=float), 50.0)),
        "games_end_at_zero_or_hundred": bool(np.all(terminal)),
        # a game still open at the corpus rebuild (suspended, or in progress on the
        # current season's last day) ends where it stopped; counted, and its windows
        # close at that last play
        "games_not_terminal": int((~terminal).sum()),
        "tolerance": CHAIN_TOL,
        "share_of_plays_not_chained": _r(float(breaks.mean()) if len(breaks) else None, 5),
        "max_gap_points": _r(float(gap.max()) if len(gap) else None, 3),
        "row_sum_misses_median_points": _r(float(missing.median()), 3),
        "row_sum_misses_p90_points": _r(float(missing.quantile(0.9)), 3),
        "row_sum_misses_p99_points": _r(float(missing.quantile(0.99)), 3),
        "note": ("consecutive plays do not chain because in-PA events move the state "
                 "between plays and are credited to neither, so a window is valued as "
                 "an endpoint difference, never a sum of wpa_home rows."),
    }


# ----------------------------------------------------------------------------
# names and dates (no network)
# ----------------------------------------------------------------------------

def names_map(war_daily: Path | None = None, links: Path | None = None) -> dict:
    """mlbam id -> name, from the daily WAR frames (every player who appeared) with
    player_links.json as the override. Never fetched."""
    import pandas as pd
    out: dict = {}
    d = Path(war_daily or WAR_DAILY)
    for f in ("pit.parquet", "bat.parquet"):
        p = d / f
        if not p.exists():
            continue
        try:
            w = pd.read_parquet(p, columns=["mlb_ID", "year_ID", "name_common"])
        except Exception:                               # noqa: BLE001
            continue
        w = w.dropna(subset=["mlb_ID", "name_common"]).sort_values("year_ID")
        for mid, nm in zip(w["mlb_ID"].astype("int64"), w["name_common"]):
            out[int(mid)] = str(nm)
    p = Path(links or PLAYER_LINKS)
    try:
        by = (json.loads(p.read_text(encoding="utf-8")).get("byMlbam") or {})
        for k, v in by.items():
            try:
                out[int(k)] = str(v.get("name") or out.get(int(k)) or "")
            except (TypeError, ValueError):
                continue
    except (OSError, ValueError):
        pass
    return out


_START_RE = re.compile(r'"startTime"\s*:\s*"(\d{4}-\d{2}-\d{2}T[0-9:.]+Z)"')


def game_dates(game_pks, *, win_prob: Path | None = None, cache: Path | None = None) -> dict:
    """game_pk -> local calendar date (America/New_York) of the first play, read from
    the head of the raw win_prob feed. No schedule cache exists offline for 2018-2025;
    the feed's first play startTime is the only date on disk. Cached, additive."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
    except Exception:                                   # noqa: BLE001
        tz = None
    wp = Path(win_prob or WIN_PROB)
    cpath = Path(cache or DATES_CACHE)
    got: dict = {}
    try:
        got = json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = {}
    new = 0
    for pk in game_pks:
        k = str(int(pk))
        if k in got:
            continue
        f = wp / f"{k}.json"
        date = None
        try:
            with f.open("r", encoding="utf-8") as fh:
                head = fh.read(4000)
            m = _START_RE.search(head)
            if m:
                t = _dt.fromisoformat(m.group(1).replace("Z", "+00:00"))
                date = (t.astimezone(tz) if tz else t).date().isoformat()
        except OSError:
            date = None
        got[k] = date
        new += 1
    if new:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(got, separators=(",", ":")), encoding="utf-8")
        except OSError:
            pass
    return {int(k): v for k, v in got.items()}


# ----------------------------------------------------------------------------
# the season context: arrays a decision can be resolved against
# ----------------------------------------------------------------------------

class SeasonCtx:
    """The plays of one season as aligned arrays, with the indices a window needs."""

    def __init__(self, season: int, plays, events, pitches, tmap: dict):
        import numpy as np
        import pandas as pd
        import win_expectancy as wx

        self.season = int(season)
        pl = plays.sort_values(["game_pk", "at_bat_index"]).reset_index(drop=True)
        pl["score_diff"] = wx.pre_play_score_diff(pl)
        pl["base"] = (pl["on_first"].notna().astype(int) + 2 * pl["on_second"].notna().astype(int)
                      + 4 * pl["on_third"].notna().astype(int))
        self.pl = pl
        self.n = len(pl)
        self.gp = pl["game_pk"].to_numpy(dtype="int64")
        self.ab = pl["at_bat_index"].to_numpy(dtype="int64")
        self.half = pl["half"].astype(str).to_numpy()
        self.bot = np.char.startswith(self.half.astype(str), "bot")
        self.inning = pl["inning"].to_numpy(dtype="int64")
        self.outs = pl["outs_before"].to_numpy(dtype="int64")
        self.outs_after = pl["outs_after"].to_numpy(dtype="int64")
        self.base = pl["base"].to_numpy(dtype="int64")
        self.sd = pl["score_diff"].to_numpy(dtype="int64")
        self.li = pl["leverage_index"].to_numpy(dtype=float)
        self.wpb = pl["wp_home_before"].to_numpy(dtype=float)
        self.wpa = pl["wp_home_after"].to_numpy(dtype=float)
        self.pitcher = pl["pitcher_id"].to_numpy(dtype=float)
        self.batter = pl["batter_id"].to_numpy(dtype=float)
        self.bside = pl["bat_side"].astype(object).to_numpy()
        self.phand = pl["pitch_hand"].astype(object).to_numpy()
        self.on1 = pl["on_first"].to_numpy(dtype=float)
        self.on2 = pl["on_second"].to_numpy(dtype=float)
        self.on3 = pl["on_third"].to_numpy(dtype=float)
        self.runs = pl["runs_scored_on_play"].fillna(0).to_numpy(dtype="int64")
        self.event = pl["event"].astype(object).to_numpy()
        self.etype = pl["event_type"].astype(object).to_numpy()
        # (game_pk, at_bat_index) -> row
        self.pos = {(int(g), int(a)): i for i, (g, a) in enumerate(zip(self.gp, self.ab))}
        # last row of the game and of the half-inning, per row
        idx = np.arange(self.n)
        g_last = pd.Series(idx).groupby(self.gp).transform("max").to_numpy()
        self.g_end = g_last
        hkey = pd.Series(list(zip(self.gp, self.inning, self.bot)))
        self.h_end = pd.Series(idx).groupby(hkey.astype(str)).transform("max").to_numpy()
        self.h_start = pd.Series(idx).groupby(hkey.astype(str)).transform("min").to_numpy()
        # rows per (game, fielding side): the half parity identifies the side
        self.side_rows: dict = {}
        for (g, b), grp in pd.Series(idx).groupby([self.gp, self.bot]):
            self.side_rows[(int(g), bool(b))] = grp.to_numpy()
        self.side_pos: dict = {}
        for key, rows in self.side_rows.items():
            for k, r in enumerate(rows):
                self.side_pos[int(r)] = (key, k)
        # pitches per plate appearance (is_pitch only) -> per row
        npitch = np.zeros(self.n, dtype="int64")
        if pitches is not None and len(pitches):
            pc = pitches[pitches["is_pitch"]].groupby(["game_pk", "at_bat_index"]).size()
            for (g, a), c in pc.items():
                i = self.pos.get((int(g), int(a)))
                if i is not None:
                    npitch[i] = int(c)
        self.npitch = npitch
        # per (game, pitcher): pitches thrown and batters faced
        dfp = pd.DataFrame({"g": self.gp, "p": self.pitcher, "np": npitch})
        dfp = dfp[dfp["p"].notna()]
        agg = dfp.groupby(["g", "p"])["np"].agg(["sum", "size"])
        self.pitch_count = {(int(g), int(p)): int(s) for (g, p), s in agg["sum"].items()}
        self.bf = {(int(g), int(p)): int(s) for (g, p), s in agg["size"].items()}
        self.pitchers_of_game: dict = {}
        for (g, p) in self.pitch_count:
            self.pitchers_of_game.setdefault(g, set()).add(p)
        # bunt attempt plate appearances from pitch codes
        self.bunt_attempt_pa: set = set()
        if pitches is not None and len(pitches):
            bp = pitches[pitches["call_code"].isin(BUNT_CODES)][["game_pk", "at_bat_index"]].drop_duplicates()
            self.bunt_attempt_pa = {(int(g), int(a)) for g, a in zip(bp["game_pk"], bp["at_bat_index"])}
        self.events = events.sort_values(["game_pk", "at_bat_index", "index"]).reset_index(drop=True)
        # pinch-runner alias per game: replaced runner id -> new runner id
        self.pr_alias: dict = {}
        pr = self.events[(self.events["event_type"] == "offensive_substitution")
                         & (self.events["position_code"].astype(str) == "12")]
        for g, a, o, n_ in zip(pr["game_pk"], pr["at_bat_index"], pr["replaced_player_id"], pr["player_id"]):
            if o == o and n_ == n_:
                self.pr_alias.setdefault(int(g), {})[int(o)] = int(n_)
        self.tmap = tmap
        # most recent batter side per (game, batter): read from the plays rows
        self.bat_side_of: dict = {}
        for g, b, s in zip(self.gp, self.batter, self.bside):
            if b == b:
                self.bat_side_of[(int(g), int(b))] = s

    # -- club of record ------------------------------------------------------
    def clubs(self, i: int):
        m = self.tmap.get(int(self.gp[i])) or {}
        return m.get("home"), m.get("away")

    def deciding(self, i: int, side: str):
        """(club, opponent, is_home) for the decision at row i."""
        home, away = self.clubs(i)
        is_home = deciding_club_is_home(self.half[i], side)
        club = home if is_home else away
        opp = away if is_home else home
        return club, opp, is_home

    def mwpa(self, i: int, j: int, is_home: bool):
        return window_mwpa(self.wpb[i], self.wpa[j], is_home)

    def window(self, i: int, j: int) -> list:
        """[ab, event, wp_before, wp_after] per play governed (arrays keep a shard small)."""
        out = []
        for k in range(int(i), int(j) + 1):
            out.append([int(self.ab[k]), str(self.event[k]), _r(self.wpb[k], 1), _r(self.wpa[k], 1)])
        return out

    def state(self, i: int) -> dict:
        li = self.li[i]
        return {"half": "bottom" if self.bot[i] else "top", "inning": int(self.inning[i]),
                "outs": int(self.outs[i]), "base": int(self.base[i]),
                "sd_home": int(self.sd[i]), "li": None if li != li else round(float(li), 3)}

    # -- runner tracking (derivation, spec 3.1 / 3.3) --------------------------
    def runner_fates(self, i: int, ids) -> dict:
        """Track runner ids from row i to the end of the half-inning.

        Returns id -> {"fate": scored|out|stranded|on_base, "max_base": int}. The lead
        runner scores first; a runner who leaves the bases with no run while the half
        continues was out; runners still on at the half's last play are stranded unless
        the play's outs cover them. A pinch runner continues the man he replaced."""
        alias = self.pr_alias.get(int(self.gp[i]), {})
        track = {int(x): int(x) for x in ids if x == x}      # current id -> original id
        out = {int(x): {"fate": "on_base", "max_base": 0} for x in ids if x == x}
        end = int(self.h_end[i])
        for k in range(int(i), end + 1):
            pre = {}
            for b, arr in ((1, self.on1), (2, self.on2), (3, self.on3)):
                v = arr[k]
                if v == v:
                    pre[int(v)] = b
            for cur, orig in list(track.items()):
                if cur in pre:
                    out[orig]["max_base"] = max(out[orig]["max_base"], pre[cur])
            if k < end:
                nxt = set()
                for arr in (self.on1, self.on2, self.on3):
                    v = arr[k + 1]
                    if v == v:
                        nxt.add(int(v))
            else:
                nxt = set()
            # aliases: the replaced runner continues as the pinch runner
            for cur, orig in list(track.items()):
                if cur not in nxt and cur in alias and alias[cur] in nxt:
                    track[alias[cur]] = orig
                    del track[cur]
            departed = [(cur, pre.get(cur, 0)) for cur, orig in track.items()
                        if cur in pre and cur not in nxt]
            if not departed:
                continue
            departed.sort(key=lambda t: -t[1])           # lead runner first
            batter = self.batter[k]
            batter_scored = 1 if str(self.etype[k]) == "home_run" else 0
            runner_runs = max(0, int(self.runs[k]) - batter_scored)
            o_added = int(self.outs_after[k]) - int(self.outs[k])
            batter_on = (batter == batter) and int(batter) in nxt
            batter_out = 1 if (not batter_on and not batter_scored and o_added >= 1) else 0
            runner_outs = max(0, o_added - batter_out)
            for n_, (cur, b) in enumerate(departed):
                orig = track.pop(cur)
                if n_ < runner_runs:
                    out[orig]["fate"] = "scored"
                    out[orig]["max_base"] = 4
                elif k < end or (n_ - runner_runs) < runner_outs:
                    out[orig]["fate"] = "out"
                else:
                    out[orig]["fate"] = "stranded"
        for cur, orig in track.items():
            if out[orig]["fate"] == "on_base":
                out[orig]["fate"] = "stranded"
        return out


# ----------------------------------------------------------------------------
# detection, one family at a time
# ----------------------------------------------------------------------------

def _switch_kind(desc: str):
    if _SWITCH_MOVE.search(desc or ""):
        return "position_move"
    if _SWITCH_DH.search(desc or ""):
        return "dh_retained"
    if _SWITCH_FIELD.search(desc or ""):
        return "stayed_in_field"
    if (desc or "").startswith("Defensive Substitution:"):
        # three rows across eight seasons: the feed typed a substitution under the
        # switch event type; they are substitutions and are counted as such
        return "substitution_text"
    return None


def classify_switches(events) -> dict:
    """Tag every defensive_switch row (spec 3.4). Every row must classify."""
    ds = events[events["event_type"] == "defensive_switch"]
    kinds = ds["description"].astype(str).map(_switch_kind)
    counts = kinds.value_counts(dropna=False).to_dict()
    return {"n": int(len(ds)),
            "dh_retained": int(counts.get("dh_retained", 0)),
            "position_move": int(counts.get("position_move", 0)),
            "stayed_in_field": int(counts.get("stayed_in_field", 0)),
            "substitution_text": int(counts.get("substitution_text", 0)),
            "unclassified": int(kinds.isna().sum())}


def _stayed_in_ids(ctx: SeasonCtx) -> dict:
    """game -> {player_id: (ab, index)} of players named by a remains-in-the-game switch
    or a defensive substitution (the roster consequence of a pinch hit / run)."""
    ev = ctx.events
    ds = ev[ev["event_type"].isin(["defensive_switch", "defensive_substitution"])]
    out: dict = {}
    for g, a, ix, pid, et, desc in zip(ds["game_pk"], ds["at_bat_index"], ds["index"],
                                        ds["player_id"], ds["event_type"], ds["description"]):
        if pid != pid:
            continue
        if et == "defensive_switch" and _switch_kind(str(desc)) == "position_move":
            continue
        out.setdefault(int(g), {}).setdefault(int(pid), []).append((int(a), int(ix)))
    return out


_PC_DESC_RE = re.compile(r"^Pitching Change: (.+?) replaces (.+?)(?:, batting .*|\.)?$")
_PC_REPLACING_RE = re.compile(r"replacing pitcher (.+?)\.?$")


def _norm_name(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def detect_pitching_changes(ctx: SeasonCtx, names: dict | None = None) -> tuple[list, dict]:
    """Every pitching_substitution row, with the removed pitcher DERIVED.

    MEASURED 2026-09-23 on 2025: replaced_player_id sits on 163 of 16,027 rows and on
    124 of them it names the LINEUP-SLOT occupant leaving on a double switch (the
    description reads "X replaces Y, batting 6th" and the field carries the position
    player, not Y). The removed pitcher is therefore the pitcher of the most recent
    plate appearance for the same fielding side before the change, or, when the
    previous change for that side sits at the same plate appearance (an arm hurt before
    facing a batter), that change's entering pitcher. The derivation is checked against
    the description's "replaces NAME" on every row that carries one and against the
    field on the rows whose description says "replacing pitcher NAME"; both rates ship.
    """
    names = names or {}
    ev = ctx.events
    ps = ev[ev["event_type"] == "pitching_substitution"]
    rows = []
    agree = {"rows_with_field": 0, "field_names_lineup_occupant": 0,
             "replacing_pitcher_clause_rows": 0, "replacing_pitcher_clause_agree": 0,
             "description_checked": 0, "description_agree": 0, "unresolved": 0,
             "already_pitching": 0}
    # changes per (game, side), in order
    per_side: dict = {}
    for g, a, ix, pid, rid, desc in zip(ps["game_pk"], ps["at_bat_index"], ps["index"],
                                        ps["player_id"], ps["replaced_player_id"],
                                        ps["description"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        key = (int(g), bool(ctx.bot[i]))
        per_side.setdefault(key, []).append((i, int(ix), pid, rid, str(desc)))
    for key, lst in per_side.items():
        lst.sort(key=lambda t: (t[0], t[1]))
        side_rows = ctx.side_rows[key]
        starter_bf = int(ctx.side_pos[lst[0][0]][1])    # rows of the side before the hook
        for n_, (i, ix, pid, rid, desc) in enumerate(lst):
            _, k = ctx.side_pos[i]
            nxt = lst[n_ + 1][0] if n_ + 1 < len(lst) else None
            if nxt is not None:
                _, kn = ctx.side_pos[nxt]
                j = int(side_rows[kn - 1]) if kn - 1 >= k else None
            else:
                j = int(side_rows[-1])
            prev = lst[n_ - 1] if n_ >= 1 else None
            if prev is not None and prev[0] == i and prev[2] == prev[2]:
                removed = int(prev[2])                  # the arm before him never faced a batter
            elif k >= 1 and ctx.pitcher[side_rows[k - 1]] == ctx.pitcher[side_rows[k - 1]]:
                removed = int(ctx.pitcher[side_rows[k - 1]])
            else:
                removed = None
            if removed is None:
                agree["unresolved"] += 1
            m = _PC_DESC_RE.match(desc)
            if m and removed is not None:
                agree["description_checked"] += 1
                if _norm_name(names.get(removed)) == _norm_name(m.group(2)):
                    agree["description_agree"] += 1
            flags = []
            if rid == rid:
                agree["rows_with_field"] += 1
                m2 = _PC_REPLACING_RE.search(desc)
                if m2:
                    agree["replacing_pitcher_clause_rows"] += 1
                    if removed is not None and int(rid) == removed:
                        agree["replacing_pitcher_clause_agree"] += 1
                if removed is not None and int(rid) != removed:
                    agree["field_names_lineup_occupant"] += 1
                    flags.append("double_switch")
            g = int(ctx.gp[i])
            if pid == pid and removed is not None and int(pid) == removed:
                flags.append("already_pitching")      # entered the batting order, no new arm
                agree["already_pitching"] += 1
                j = None
            if j is None and "already_pitching" not in flags:
                flags.append("no_pa")
            if pid == pid and ctx.pitcher[i] == ctx.pitcher[i] and int(ctx.pitcher[i]) != int(pid):
                flags.append("credited_to_prior")
            inherited = [v for v in (ctx.on1[i], ctx.on2[i], ctx.on3[i]) if v == v]
            fates = ctx.runner_fates(i, inherited) if inherited else {}
            inh_scored = sum(1 for f in fates.values() if f["fate"] == "scored")
            kind = "starter_hook" if n_ == 0 else "reliever_change"
            if n_ == 0:
                # opener tag (plan M-PIT-7): the first pitcher faced at most nine
                # batters and the second recorded at least nine outs
                second_outs = 0
                if j is not None:
                    for kk in range(i, j + 1):
                        second_outs += int(ctx.outs_after[kk]) - int(ctx.outs[kk])
                if starter_bf <= 9 and second_outs >= 9:
                    flags.append("opener")
            rows.append({
                "family": "pitching_change", "kind": kind, "i": i, "j": j, "idx": int(ix),
                "side": "field", "in_id": _int(pid), "out_id": removed, "flags": flags,
                "pitch_count": ctx.pitch_count.get((g, removed)) if removed is not None else None,
                "tto": (ctx.bf.get((g, removed), 0) // 9 + 1) if removed is not None else None,
                "inherited": len(inherited), "inherited_scored": int(inh_scored),
                "first_pa_mwpa": None,     # filled in finalise
                "batter_side": ctx.bside[i], "pitcher_hand": ctx.phand[i],
                "due_id": _int(ctx.batter[i]),
            })
    return rows, agree


def detect_pinch_hits(ctx: SeasonCtx) -> list:
    ev = ctx.events
    ph = ev[(ev["event_type"] == "offensive_substitution") & (ev["position_code"].astype(str) == "11")]
    stayed = _stayed_in_ids(ctx)
    rows = []
    for g, a, ix, pid, rid, bo in zip(ph["game_pk"], ph["at_bat_index"], ph["index"],
                                      ph["player_id"], ph["replaced_player_id"], ph["batting_order"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        g = int(g)
        flags = []
        if pid == pid and ctx.batter[i] == ctx.batter[i] and int(ctx.batter[i]) != int(pid):
            flags.append("credited_to_prior")
        out_id = _int(rid)
        if out_id is not None and out_id in ctx.pitchers_of_game.get(g, set()):
            flags.append("pitcher_spot")
        later = [(aa, xx) for (aa, xx) in stayed.get(g, {}).get(_int(pid) or -1, [])
                 if (aa, xx) > (int(a), int(ix))]
        if later:
            flags.append("stayed_in")
        slot = None
        try:
            slot = int(str(bo)[:-2]) if bo and str(bo) != "nan" else None
        except ValueError:
            slot = None
        rows.append({
            "family": "pinch_hit", "kind": "pinch_hit", "i": i, "j": i, "idx": int(ix),
            "side": "bat", "in_id": _int(pid), "out_id": out_id, "flags": flags, "slot": slot,
            "batter_side": ctx.bside[i], "pitcher_hand": ctx.phand[i],
            "out_side": ctx.bat_side_of.get((g, out_id)) if out_id is not None else None,
            "pitcher_id": _int(ctx.pitcher[i]),
        })
    return rows


def detect_pinch_runs(ctx: SeasonCtx) -> list:
    ev = ctx.events
    pr = ev[(ev["event_type"] == "offensive_substitution") & (ev["position_code"].astype(str) == "12")]
    stayed = _stayed_in_ids(ctx)
    rows = []
    for g, a, ix, pid, rid, b in zip(pr["game_pk"], pr["at_bat_index"], pr["index"],
                                     pr["player_id"], pr["replaced_player_id"], pr["base"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        g = int(g)
        j = int(ctx.h_end[i])
        fate = {"fate": "unknown", "max_base": 0}
        if pid == pid:
            fate = ctx.runner_fates(i, [pid]).get(int(pid), fate)
        flags = []
        if fate["fate"] == "scored":
            flags.append("scored")
        if fate["fate"] == "out":
            flags.append("out_on_bases")
        entry_base = _int(b) or 0
        if fate["max_base"] > entry_base:
            flags.append("advanced")
        later = [(aa, xx) for (aa, xx) in stayed.get(g, {}).get(_int(pid) or -1, [])
                 if (aa, xx) > (int(a), int(ix))]
        if later:
            flags.append("stayed_in")
        rows.append({
            "family": "pinch_run", "kind": f"on_{entry_base}B" if entry_base else "pinch_run",
            "i": i, "j": j, "idx": int(ix), "side": "bat", "in_id": _int(pid),
            "out_id": _int(rid), "flags": flags, "entry_base": entry_base,
        })
    return rows


def detect_defensive_subs(ctx: SeasonCtx) -> list:
    ev = ctx.events
    rows = []
    ds = ev[ev["event_type"] == "defensive_substitution"]
    for g, a, ix, pid, rid, pc, bo in zip(ds["game_pk"], ds["at_bat_index"], ds["index"],
                                          ds["player_id"], ds["replaced_player_id"],
                                          ds["position_code"], ds["batting_order"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        slot = None
        try:
            slot = int(str(bo)[:-2]) if bo and str(bo) != "nan" else None
        except ValueError:
            slot = None
        rows.append({"family": "defensive_sub", "kind": "substitution", "i": i,
                     "j": int(ctx.g_end[i]), "idx": int(ix), "side": "field",
                     "in_id": _int(pid), "out_id": _int(rid), "pos": str(pc) if pc else None,
                     "slot": slot, "flags": []})
    sw = ev[ev["event_type"] == "defensive_switch"]
    for g, a, ix, pid, rid, pc, desc in zip(sw["game_pk"], sw["at_bat_index"], sw["index"],
                                            sw["player_id"], sw["replaced_player_id"],
                                            sw["position_code"], sw["description"]):
        kind = _switch_kind(str(desc))
        if kind not in ("position_move", "substitution_text"):
            continue
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        rows.append({"family": "defensive_sub",
                     "kind": "position_move" if kind == "position_move" else "substitution",
                     "i": i, "j": int(ctx.g_end[i]), "idx": int(ix), "side": "field",
                     "in_id": _int(pid), "out_id": _int(rid) if kind != "position_move" else None,
                     "pos": str(pc) if pc else None, "slot": None, "flags": []})
    return rows


def detect_intentional_walks(ctx: SeasonCtx) -> list:
    import numpy as np
    rows = []
    for i in np.flatnonzero(ctx.etype == "intent_walk"):
        i = int(i)
        j = i + 1 if i + 1 <= int(ctx.h_end[i]) else i
        flags = []
        if int(ctx.base[i]) == 7:
            flags.append("forces_run")
        rows.append({"family": "intentional_walk", "kind": "intent_walk", "i": i, "j": j,
                     "idx": -1, "side": "field", "in_id": _int(ctx.batter[i]),
                     "out_id": None, "flags": flags,
                     "batter_side": ctx.bside[i], "pitcher_hand": ctx.phand[i],
                     "pitcher_id": _int(ctx.pitcher[i]),
                     "ondeck_id": _int(ctx.batter[j]) if j != i else None,
                     "ondeck_side": ctx.bside[j] if j != i else None,
                     "walk_only_mwpa": None})
    return rows


def _bunt_cells() -> dict:
    try:
        d = json.loads(BUNT.read_text(encoding="utf-8"))
        return {(int(c["outs"]), int(c["base"])): float(c["dv_per_bunt"])
                for c in (d.get("cells") or [])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def detect_bunts(ctx: SeasonCtx, cells: dict | None = None) -> list:
    import numpy as np
    cells = _bunt_cells() if cells is None else cells
    rows = []
    is_result = np.isin(ctx.event.astype(str), BUNT_RESULTS)
    seen = set()
    for i in np.flatnonzero(is_result):
        i = int(i)
        ev = str(ctx.event[i])
        kind = "sac_bunt" if ev == "Sac Bunt" else "bunt_out"
        flags = []
        key = (int(ctx.gp[i]), int(ctx.ab[i]))
        seen.add(key)
        if key in ctx.bunt_attempt_pa:
            flags.append("attempt_codes")
        if int(ctx.base[i]) != 0 and int(ctx.outs[i]) < 2:
            flags.append("sign_proxy")
        rows.append({"family": "bunt", "kind": kind, "i": i, "j": i, "idx": -1, "side": "bat",
                     "in_id": _int(ctx.batter[i]), "out_id": None, "flags": flags,
                     "batter_side": ctx.bside[i], "pitcher_hand": ctx.phand[i],
                     "dv_cell": cells.get((int(ctx.outs[i]), int(ctx.base[i])))
                     if int(ctx.outs[i]) < 2 else None})
    for key in sorted(ctx.bunt_attempt_pa - seen):
        i = ctx.pos.get(key)
        if i is None:
            continue
        flags = ["attempt_codes"]
        if int(ctx.base[i]) != 0 and int(ctx.outs[i]) < 2:
            flags.append("sign_proxy")
        rows.append({"family": "bunt", "kind": "bunt_attempt_abandoned", "i": i, "j": i,
                     "idx": -1, "side": "bat", "in_id": _int(ctx.batter[i]), "out_id": None,
                     "flags": flags, "batter_side": ctx.bside[i], "pitcher_hand": ctx.phand[i],
                     "dv_cell": None})
    return rows


def detect_steals(ctx: SeasonCtx, attempts) -> list:
    """The priced rows of management.attempts() for this season, as-is, plus the feed's
    realized mWPA of the play as a second, labelled realized number."""
    rows = []
    if attempts is None or len(attempts) == 0:
        return rows
    a = attempts[(attempts["season"].astype(int) == ctx.season) & attempts["dv"].notna()]
    origin = {"2B": ctx.on1, "3B": ctx.on2, "HOME": ctx.on3}
    for r in a.itertuples(index=False):
        i = ctx.pos.get((int(r.game_pk), int(r.at_bat_index)))
        if i is None:
            continue
        flags = [] if bool(r.success) else ["caught"]
        runner = origin.get(str(r.target))
        rows.append({"family": "steal", "kind": str(r.target), "i": i, "j": i, "idx": -1,
                     "side": "bat", "in_id": _int(runner[i]) if runner is not None else None,
                     "out_id": None, "flags": flags,
                     "dv": _r(r.dv, 5), "er": _r(r.er, 5), "realized_delta": _r(r.realized_delta, 5),
                     "breakeven_p": _r(r.breakeven_p, 4), "success": bool(r.success)})
    return rows


def detect_mound_visits(ctx: SeasonCtx, changes: list | None = None) -> list:
    """Counted, never valued. The pitcher visited is the plays row's pitcher unless a
    pitching change follows in the same plate appearance, in which case it is the
    pitcher that change removed (the plays row credits the PA to the new arm)."""
    ev = ctx.events
    mv = ev[ev["event_type"] == "mound_visit"]
    later_change: dict = {}
    for c in changes or []:
        later_change.setdefault(c["i"], []).append((c["idx"], c.get("out_id")))
    rows = []
    for g, a, ix in zip(mv["game_pk"], mv["at_bat_index"], mv["index"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            continue
        pitcher = _int(ctx.pitcher[i])
        for cidx, removed in sorted(later_change.get(i, [])):
            if cidx > int(ix) and removed is not None:
                pitcher = removed
                break
        rows.append({"family": "mound_visit", "kind": "mound_visit", "i": i, "j": None,
                     "idx": int(ix), "side": "field", "in_id": None, "out_id": None,
                     "flags": [], "pitcher_id": pitcher})
    return rows


def parse_ejection(description: str) -> dict | None:
    m = _EJECT_RE.match(description or "")
    if not m:
        return None
    club = m.group("club").strip()
    interim = club.lower().endswith(" interim")
    if interim:
        club = club[: -len(" interim")].strip()
    return {"club_name": club, "role": m.group("role"), "name": m.group("name").strip(),
            "interim": interim}


def _club_from_nickname(name: str, candidates) -> str | None:
    low = (name or "").strip().lower()
    code = _NICK_EXTRA.get(low)
    if code is None:
        try:
            import trades
            code = trades.canonical_org(name)
        except Exception:                               # noqa: BLE001
            code = None
    if code in candidates:
        return code
    return None


_EJECT_LOOSE_RE = re.compile(r"^(?P<who>.+?) ejected by")


def parse_ejection_loose(description: str, candidates) -> dict | None:
    """The fallback for a description with no role word.

    58 of the 1,474 ejection rows across eight seasons fail _EJECT_RE: 43 name a
    club and nobody ("Phillies ejected by 3B umpire .", 42 of them in 2018) and 15
    name a person with no role, or with a staff title the feed writes free-form
    ("Twins Ryan Jeffers ejected by ...", "Angels coordinator, run production Tim
    Laker ejected by ..."). Every one opens with the club nickname, so the club is
    read off the first one or two words against the game's two clubs, and whatever
    follows up to "ejected by" is the person as the feed wrote them, role unknown.
    Dropping these rows had the League census undercount the family against the
    Managers tab on the same page (1,416 against 1,474)."""
    m = _EJECT_LOOSE_RE.match(description or "")
    if not m:
        return None
    words = m.group("who").split(" ")
    for k in (1, 2):
        if len(words) < k:
            break
        head = " ".join(words[:k])
        club = _club_from_nickname(head, candidates)
        if club is not None:
            rest = " ".join(words[k:]).strip()
            return {"club_name": head, "club": club, "role": "other" if rest else "unnamed",
                    "name": rest or None, "interim": False}
    return None


def detect_ejections(ctx: SeasonCtx) -> tuple[list, dict]:
    ev = ctx.events
    ej = ev[ev["event_type"] == "ejection"]
    rows = []
    fixture = {"n": int(len(ej)), "managers": 0, "managers_with_id": 0, "unattributed": 0,
               "unpositioned": 0, "no_role_word": 0, "names": []}
    for g, a, ix, pid, desc in zip(ej["game_pk"], ej["at_bat_index"], ej["index"],
                                   ej["player_id"], ej["description"]):
        i = ctx.pos.get((int(g), int(a)))
        if i is None:
            fixture["unpositioned"] += 1
            continue
        home, away = ctx.clubs(i)
        p = parse_ejection(str(desc))
        club = _club_from_nickname(p["club_name"], {home, away}) if p else None
        if p is None:
            # no role word: the club nickname opens the description, the rest is the person
            p = parse_ejection_loose(str(desc), {home, away})
            club = p["club"] if p else None
            if p is not None:
                fixture["no_role_word"] += 1
        flags = []
        is_mgr = bool(p and p["role"] == "manager")
        if is_mgr:
            flags.append("manager")
            fixture["managers"] += 1
            if pid == pid:
                fixture["managers_with_id"] += 1
                if len(fixture["names"]) < 200:
                    fixture["names"].append({"mlbam": int(pid), "name": p["name"], "club": club,
                                             "game_pk": int(g), "interim": p["interim"]})
        if p and p["interim"]:
            flags.append("interim")
        if club is None:
            fixture["unattributed"] += 1
        rows.append({"family": "ejection", "kind": (p["role"] if p else "unparsed"), "i": i,
                     "j": None, "idx": int(ix), "side": None, "club_override": club,
                     "in_id": _int(pid) if is_mgr else None, "out_id": None, "flags": flags,
                     "ejected_name": p["name"] if p else None})
    return rows, fixture


# ----------------------------------------------------------------------------
# finalise a season's rows: club, sign, window, state, id
# ----------------------------------------------------------------------------

def finalise(ctx: SeasonCtx, rows: list, names: dict, dates: dict, with_window: bool = True) -> list:
    out = []
    for d in rows:
        i = int(d["i"])
        j = d.get("j")
        if d.get("family") == "ejection":
            home, away = ctx.clubs(i)
            club = d.get("club_override")
            if club is None:
                continue
            is_home = club == home
            opp = away if is_home else home
        else:
            club, opp, is_home = ctx.deciding(i, d["side"])
            if club is None:
                continue
        st = ctx.state(i)
        mw = ctx.mwpa(i, int(j), is_home) if j is not None else None
        sd_club = st["sd_home"] if is_home else -st["sd_home"]
        g = int(ctx.gp[i])
        row = {
            "id": f"{g}:{int(ctx.ab[i])}:{int(d['idx'])}",
            "date": dates.get(g), "game_pk": g, "ab": int(ctx.ab[i]), "idx": int(d["idx"]),
            "season": ctx.season, "club": club, "opp": opp, "home": bool(is_home),
            "half": st["half"], "inning": st["inning"], "outs": st["outs"], "base": st["base"],
            "score_diff": int(sd_club), "li": st["li"],
            "family": d["family"], "kind": d.get("kind"),
            "in_id": d.get("in_id"), "out_id": d.get("out_id"),
            "in_name": names.get(d.get("in_id")) if d.get("in_id") is not None else None,
            "out_name": names.get(d.get("out_id")) if d.get("out_id") is not None else None,
            "slot": d.get("slot"), "pos": d.get("pos"),
            "mwpa": _r(mw, 4), "dvs": None,
            "win_len": (int(j) - i + 1) if j is not None else 0,
            "flags": list(d.get("flags") or []),
        }
        if with_window:
            row["window"] = ctx.window(i, int(j)) if j is not None else []
        fam = d["family"]
        if fam == "pitching_change":
            row.update({"pitch_count": d.get("pitch_count"), "tto": d.get("tto"),
                        "inherited": d.get("inherited"), "inherited_scored": d.get("inherited_scored"),
                        "first_pa_mwpa": _r(ctx.mwpa(i, i, is_home), 4) if j is not None else None,
                        "batter_side": d.get("batter_side"), "pitcher_hand": d.get("pitcher_hand"),
                        "due_id": d.get("due_id"), "due_name": names.get(d.get("due_id"))})
        elif fam == "pinch_hit":
            row.update({"batter_side": d.get("batter_side"), "out_side": d.get("out_side"),
                        "pitcher_hand": d.get("pitcher_hand"), "pitcher_id": d.get("pitcher_id"),
                        "pitcher_name": names.get(d.get("pitcher_id"))})
        elif fam == "pinch_run":
            row.update({"entry_base": d.get("entry_base")})
        elif fam == "intentional_walk":
            row.update({"batter_side": d.get("batter_side"), "pitcher_hand": d.get("pitcher_hand"),
                        "pitcher_id": d.get("pitcher_id"), "pitcher_name": names.get(d.get("pitcher_id")),
                        "ondeck_id": d.get("ondeck_id"), "ondeck_name": names.get(d.get("ondeck_id")),
                        "ondeck_side": d.get("ondeck_side"),
                        "walk_only_mwpa": _r(ctx.mwpa(i, i, is_home), 4)})
        elif fam == "bunt":
            row.update({"batter_side": d.get("batter_side"), "pitcher_hand": d.get("pitcher_hand"),
                        "dv_cell": _r(d.get("dv_cell"), 5)})
        elif fam == "steal":
            row.update({"dv": d.get("dv"), "er": d.get("er"), "realized_delta": d.get("realized_delta"),
                        "breakeven_p": d.get("breakeven_p"), "success": d.get("success")})
        elif fam == "mound_visit":
            row.update({"pitcher_id": d.get("pitcher_id"), "pitcher_name": names.get(d.get("pitcher_id"))})
        elif fam == "ejection":
            row.update({"ejected_name": d.get("ejected_name")})
        # null-valued keys are dropped: a shard row reads the same and weighs less
        out.append({k: v for k, v in row.items() if v is not None})
    return out


# ----------------------------------------------------------------------------
# the season loader
# ----------------------------------------------------------------------------

def load_season(corpus: Path, season) -> tuple:
    import pandas as pd
    s = str(season)
    pl = pd.concat([pd.read_parquet(f) for f in sorted((corpus / "plays" / s).glob("*.parquet"))],
                   ignore_index=True)
    ev = pd.concat([pd.read_parquet(f) for f in sorted((corpus / "events" / s).glob("*.parquet"))],
                   ignore_index=True)
    pf = sorted((corpus / "pitches" / s).glob("*.parquet"))
    pi = pd.concat([pd.read_parquet(f, columns=["game_pk", "at_bat_index", "call_code", "is_pitch"])
                    for f in pf], ignore_index=True) if pf else None
    return pl, ev, pi


def seasons_on_disk(corpus: Path) -> list:
    d = corpus / "plays"
    return sorted(int(p.name) for p in d.iterdir() if p.is_dir() and p.name.isdigit()) if d.exists() else []


def build_season(ctx: SeasonCtx, names: dict, dates: dict, attempts=None, bunt_cells=None,
                 with_window: bool = True) -> tuple[list, dict]:
    """Every decision of one season, finalised. Returns (rows, meta)."""
    meta = {}
    pc, agree = detect_pitching_changes(ctx, names)
    meta["removed_pitcher"] = agree
    rows = list(pc)
    rows += detect_pinch_hits(ctx)
    rows += detect_pinch_runs(ctx)
    rows += detect_defensive_subs(ctx)
    rows += detect_intentional_walks(ctx)
    rows += detect_bunts(ctx, bunt_cells)
    rows += detect_steals(ctx, attempts)
    rows += detect_mound_visits(ctx, pc)
    ej, fixture = detect_ejections(ctx)
    rows += ej
    meta["ejections"] = fixture
    meta["switches"] = classify_switches(ctx.events)
    out = finalise(ctx, rows, names, dates, with_window=with_window)
    return out, meta


# ----------------------------------------------------------------------------
# club-season rows, style z, census
# ----------------------------------------------------------------------------

def style_z(values: dict) -> dict:
    """{club: x} -> {club: z}, population sd (ddof 0) so the thirty clubs of a season
    have mean zero and sd one exactly. A constant column is all zero."""
    import numpy as np
    keys = [k for k, v in values.items() if v is not None and v == v]
    if not keys:
        return {}
    x = np.array([float(values[k]) for k in keys])
    sd = float(x.std(ddof=0))
    if sd == 0:
        return {k: 0.0 for k in keys}
    m = float(x.mean())
    return {k: round(float((values[k] - m) / sd), 2) for k in keys}


def club_games(tmap: dict) -> dict:
    out: dict = {}
    for g in tmap.values():
        s = int(g["season"])
        for c in (g["home"], g["away"]):
            out[(_canon(c), s)] = out.get((_canon(c), s), 0) + 1
    return out


def club_rows(ledger, tmap: dict, seasons_complete: dict | None = None) -> list:
    """The 6.1 columns per club-season. Key discipline: no key contains "dv" or
    "decision" (the gate test scans this block); counts are n_all / n_<family>; realized
    columns are mwpa_<family> and never a cross-family total; style columns are z_*."""
    import numpy as np
    import pandas as pd
    games = club_games(tmap)
    rows = []
    if ledger is None or len(ledger) == 0:
        return rows
    df = ledger
    for (club, season), g in df.groupby(["club", "season"]):
        n_games = games.get((club, int(season)), 0)
        row = {"club": str(club), "season": int(season), "agent": "club-season",
               "games": int(n_games), "n_all": int(len(g))}
        for f in FAMILIES:
            gf = g[g["family"] == f]
            row[f"n_{f}"] = int(len(gf))
        li = g["li"].dropna()
        row["mean_li"] = _r(float(li.mean()), 3) if len(li) else None
        row["share_li_high"] = _r(float((li >= 1.5).mean()), 3) if len(li) else None
        for f in SUMMED_FAMILIES:
            gf = g[(g["family"] == f) & g["mwpa"].notna()]
            n = int(len(gf))
            row[f"mwpa_{f}"] = _r(float(gf["mwpa"].sum()), 3) if n >= FLOORS[f] else None
        hooks = g[(g["family"] == "pitching_change") & (g["kind"] == "starter_hook")]["pitch_count"].dropna()
        row["hook_median_pitches"] = _r(float(hooks.median()), 1) if len(hooks) else None
        per_game = (lambda n: _r(n / n_games, 3) if n_games else None)
        row["pen_per_game"] = per_game(row["n_pitching_change"])
        row["bench_per_game"] = per_game(row["n_pinch_hit"] + row["n_pinch_run"])
        row["ibb_per_game"] = per_game(row["n_intentional_walk"])
        row["visit_per_game"] = per_game(row["n_mound_visit"])
        ok = g[g["family"].isin(SUMMED_FAMILIES) & g["mwpa"].notna()]
        if len(ok):
            b = ok.loc[ok["mwpa"].idxmax()]
            w = ok.loc[ok["mwpa"].idxmin()]
            row["best"] = {"id": b["id"], "family": b["family"], "game_pk": int(b["game_pk"]),
                           "ab": int(b["ab"]), "mwpa": _r(b["mwpa"], 4), "date": b.get("date")}
            row["worst"] = {"id": w["id"], "family": w["family"], "game_pk": int(w["game_pk"]),
                            "ab": int(w["ab"]), "mwpa": _r(w["mwpa"], 4), "date": w.get("date")}
        else:
            row["best"] = row["worst"] = None
        # A partial season: the corpus says it is incomplete, or the club played
        # fewer than PARTIAL_GAMES games (2026 ends at the corpus rebuild date).
        row["partial"] = bool((seasons_complete is not None
                               and not seasons_complete.get(int(season), True))
                              or n_games < PARTIAL_GAMES)
        rows.append(row)
    # style z per season across the clubs of that season
    by_season: dict = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(r)
    for season, rs in by_season.items():
        for key, src in (("z_hook", "hook_median_pitches"), ("z_pen", "pen_per_game"),
                         ("z_bench", "bench_per_game"), ("z_ibb", "ibb_per_game"),
                         ("z_visit", "visit_per_game")):
            # A season in which the feed carried no event of the kind (mound visits
            # enter the feed in 2023) has no style figure for it: null, not zero.
            if key == "z_visit" and sum(r["n_mound_visit"] for r in rs) == 0:
                for r in rs:
                    r[key] = None
                continue
            z = style_z({r["club"]: r.get(src) for r in rs})
            for r in rs:
                r[key] = z.get(r["club"])
    rows.sort(key=lambda r: (-r["n_all"], -r["season"], r["club"]))
    return rows


def hook_histogram(ledger) -> dict:
    """League histogram of the starter's pitch count at the hook, per season, so a club
    page can draw its own against the league without recomputing it."""
    import numpy as np
    out = {"bins": HOOK_BINS, "by_season": {}}
    if ledger is None or len(ledger) == 0:
        return out
    h = ledger[(ledger["family"] == "pitching_change") & (ledger["kind"] == "starter_hook")]
    for season, g in h.groupby("season"):
        x = g["pitch_count"].dropna().to_numpy(dtype=float)
        counts, _ = np.histogram(np.clip(x, 0, HOOK_BINS[-1] + 9), bins=HOOK_BINS + [HOOK_BINS[-1] + 10])
        out["by_season"][str(int(season))] = [int(c) for c in counts]
    return out


def families_block(ledger, baseline: dict | None, gate_status: dict, thin_by_family: dict,
                   ejection_meta: dict | None = None) -> dict:
    out = {}
    if ledger is None or len(ledger) == 0:
        return out
    for f in FAMILIES:
        g = ledger[ledger["family"] == f]
        by_season = {str(int(s)): int(n) for s, n in g.groupby("season").size().items()}
        ok = g[g["mwpa"].notna()]
        # A league sum exists for the SUMMED families only. A defensive sub's window
        # is stored on the decision and never summed anywhere (spec 3.4), so the
        # census prints "stored, not summed" for it rather than a total.
        sums = ({str(int(s)): _r(float(v), 3) for s, v in ok.groupby("season")["mwpa"].sum().items()}
                if f in SUMMED_FAMILIES else {})
        bf = ((baseline or {}).get("families") or {}).get(f) or {}
        within = ("none" if f in COUNTED_ONLY
                  else "disjoint" if f in ("pinch_hit", "bunt", "steal")
                  else "can overlap" if f in ("pinch_run", "intentional_walk", "defensive_sub")
                  else "partition of each side's plate appearances once the starter's stint is included; "
                  "the decision windows alone leave the starter's stint out")
        out[f] = {
            "label": LABEL[f], "n": int(len(g)), "n_by_season": by_season,
            "floor": FLOORS.get(f), "window_rule": WINDOW_RULE[f],
            "counterfactual_sentence": COUNTERFACTUAL[f],
            "has_window": f in WINDOW_FAMILIES, "summed": f in SUMMED_FAMILIES,
            "counted_only": f in COUNTED_ONLY,
            "league_sum_mwpa_by_season": sums,
            "within_family_windows": within,
            "dvs_identity_max_abs": bf.get("identity_max_abs"),
            "thin_cells": thin_by_family.get(f),
            "mean_li": _r(float(g["li"].dropna().mean()), 3) if g["li"].notna().any() else None,
            "gate_status": gate_status.get(f, "not run"),
        }
        if f == "pitching_change":
            hooks = g[g["kind"] == "starter_hook"]["pitch_count"].dropna()
            out[f]["hook_pitch_count"] = {
                "median": _r(float(hooks.median()), 1) if len(hooks) else None,
                "p10": _r(float(hooks.quantile(0.1)), 1) if len(hooks) else None,
                "p90": _r(float(hooks.quantile(0.9)), 1) if len(hooks) else None,
                "n": int(len(hooks))}
            inh = g["inherited"].fillna(0).sum()
            out[f]["inherited_runners"] = {
                "inherited": int(inh), "scored": int(g["inherited_scored"].fillna(0).sum()),
                "derivation": INHERITED_DERIVATION}
            out[f]["mid_pa"] = None
            out[f]["mid_pa_note"] = ("null until the corpus rebuild lands the count at the "
                                     "action (Wave B); the window starts at the plays row")
        if f in COUNTED_ONLY:
            with_events = sorted(int(s) for s, n in by_season.items() if n > 0)
            out[f]["first_season_with_events"] = with_events[0] if with_events else None
            out[f]["seasons_without_events"] = sorted(
                int(s) for s in ledger["season"].unique() if by_season.get(str(int(s)), 0) == 0)
        if f == "ejection" and ejection_meta:
            # The census prints the family against the corpus it was read from, so the
            # League tab and the Managers tab (whose fixture counts every ejection row)
            # print one number; a row the parser could not place reads "attributed of".
            corpus_by_season = {str(s): int((m or {}).get("n", 0)) for s, m in ejection_meta.items()}
            out[f]["n_corpus_rows"] = int(sum(corpus_by_season.values()))
            out[f]["n_corpus_rows_by_season"] = corpus_by_season
            for k in ("unattributed", "unpositioned", "no_role_word"):
                out[f][k] = int(sum(int((m or {}).get(k, 0)) for m in ejection_meta.values()))
        if f == "steal":
            out[f]["two_realized_estimators"] = {
                "model": "realized_delta (management.py: DV + ER)",
                "feed": "mwpa (StatsAPI wp columns, endpoint difference)",
                "note": "two estimators of one quantity; both ship, never averaged"}
        if f == "bunt":
            out[f]["kinds"] = {str(k): int(n) for k, n in g.groupby("kind").size().items()}
            out[f]["sign_note"] = ("the bunt sign is not observable; an attempt with a runner "
                                   "on and fewer than two outs is the closest proxy and is "
                                   "flagged sign_proxy")
    return out


def gate_status_by_family() -> dict:
    out = {f: "not run" for f in FAMILIES}
    try:
        g = json.loads(GATE_EVAL.read_text(encoding="utf-8"))
        v = str(g.get("verdict") or "")
        pub = ((g.get("gate_1_split_half") or {}).get("published") or {})
        if pub.get("clears_null") is True:
            out["steal"] = "clears"
        elif "DESCRIPTIVE" in v or pub.get("clears_null") is False:
            out["steal"] = "bounded null"
    except (OSError, ValueError):
        pass
    return out


def split_agent_at_change(game_pks_in_order, change_after_pk) -> tuple[list, list]:
    """The rule the manager ingest (Wave C) will apply: a club-season splits into two
    agents at the change game. Games through change_after_pk (inclusive) belong to the
    first agent; every later game to the second. Pure, so the fixture can pin it now."""
    first, second = [], []
    seen = False
    for pk in game_pks_in_order:
        (second if seen else first).append(pk)
        if pk == change_after_pk:
            seen = True
    return first, second


# ----------------------------------------------------------------------------
# the build
# ----------------------------------------------------------------------------

def build(*, corpus: Path | None = None, seasons=None, shards: bool = True,
          shard_dir: Path | None = None, baseline_out: Path | None = None,
          write_baseline: bool = True) -> dict:
    """Build the ledger over every season on disk, write the shards and the baseline,
    and return the summary artifact (data/management_decisions.json)."""
    import pandas as pd
    import mgmt_baseline
    import mgmt_shards
    import mgmt_teams
    import management as M

    corpus = Path(corpus or CORPUS)
    if not (corpus / "plays").exists():
        return {"status": f"not built: no corpus at {corpus}"}
    want = [int(s) for s in seasons] if seasons else seasons_on_disk(corpus)
    tmap_raw = mgmt_teams.build_map(corpus=corpus)
    tmap = {g: {"home": _canon(v["home"]), "away": _canon(v["away"]), "season": v["season"]}
            for g, v in tmap_raw.items()}
    truth = mgmt_teams.validate_against_ground_truth(tmap_raw)
    names = names_map()
    dates = game_dates(sorted(tmap))
    attempts = M.attempts(corpus=corpus)
    bunt_cells = _bunt_cells()
    slim_cols = ["id", "date", "game_pk", "ab", "idx", "season", "club", "opp", "home", "half",
                 "inning", "outs", "base", "score_diff", "li", "family", "kind", "mwpa", "dvs",
                 "win_len", "flags", "pitch_count", "tto", "inherited", "inherited_scored",
                 "first_pa_mwpa"]
    slim = []
    chain = {}
    meta_by_season = {}
    baseline_frames = {}
    thin_by_family: dict = {}
    index = []
    sdir = Path(shard_dir or SHARD_DIR)
    written = set()
    for season in want:
        pl, ev, pi = load_season(corpus, season)
        if pl.empty:
            continue
        ctx = SeasonCtx(season, pl, ev, pi, tmap)
        chain[str(season)] = chain_break_stats(pl)
        rows, meta = build_season(ctx, names, dates, attempts, bunt_cells, with_window=shards)
        meta_by_season[str(season)] = meta
        # baseline: league windows of the same shape, then DVS per decision
        cells = mgmt_baseline.season_cells(ctx)
        baseline_frames[str(season)] = cells
        n_thin_hits = {}
        for r in rows:
            f = r["family"]
            if f not in WINDOW_FAMILIES or r.get("mwpa") is None:
                continue
            cell = (mgmt_baseline.cell_key(season, r["inning"], r["half"], r["outs"], r["base"],
                                            r["score_diff"] if r["home"] else -r["score_diff"]))
            c = (cells.get(f) or {}).get(cell)
            if c and c["n"] >= mgmt_baseline.MIN_CELL:
                r["dvs"] = _r(r["mwpa"] - c["mean_mwpa"], 4)
            else:
                n_thin_hits[f] = n_thin_hits.get(f, 0) + 1
        for f, n in n_thin_hits.items():
            thin_by_family.setdefault(f, {"decisions_in_thin_cells": 0})
            thin_by_family[f]["decisions_in_thin_cells"] += n
        if shards:
            idx_rows = mgmt_shards.write_season(rows, sdir, season)
            index.extend(idx_rows)
            written |= {(e["season"], e["club"]) for e in idx_rows}
        for r in rows:
            slim.append({k: r.get(k) for k in slim_cols})
        log.info("mgmt_decisions: %s %d decisions", season, len(rows))
        del ctx, pl, ev, pi, rows
    if shards:
        mgmt_shards.prune(sdir, written)
    ledger = pd.DataFrame(slim)
    if len(ledger):
        ledger["flags"] = ledger["flags"].map(lambda v: ",".join(v) if isinstance(v, list) else (v or ""))
    baseline = mgmt_baseline.assemble(baseline_frames)
    for f, bf in (baseline.get("families") or {}).items():
        thin_by_family.setdefault(f, {"decisions_in_thin_cells": 0})
        thin_by_family[f]["cells_thin"] = bf.get("thin_cells")
        thin_by_family[f]["cells_total"] = bf.get("n_cells")
    if write_baseline:
        bo = Path(baseline_out or mgmt_baseline.OUT)
        bo.write_text(json.dumps(baseline, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    manifest = {}
    try:
        manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    seasons_seen = sorted(int(s) for s in ledger["season"].unique()) if len(ledger) else []
    through = {}
    complete = {}
    for s in seasons_seen:
        ds = ledger.loc[ledger["season"] == s, "date"].dropna()
        through[str(s)] = str(ds.max()) if len(ds) else None
        complete[s] = bool(((manifest.get("seasons") or {}).get(str(s)) or {}).get("complete", True))
    gate = gate_status_by_family()
    ej_named = sum(m["ejections"]["managers_with_id"] for m in meta_by_season.values())
    removed = {"rows_with_field": 0, "field_names_lineup_occupant": 0,
               "replacing_pitcher_clause_rows": 0, "replacing_pitcher_clause_agree": 0,
               "description_checked": 0, "description_agree": 0, "unresolved": 0,
               "already_pitching": 0}
    for m in meta_by_season.values():
        for k in removed:
            removed[k] += int(m["removed_pitcher"].get(k, 0))
    switches = {"n": 0, "dh_retained": 0, "position_move": 0, "stayed_in_field": 0,
                "substitution_text": 0, "unclassified": 0}
    for m in meta_by_season.values():
        for k in switches:
            switches[k] += int(m["switches"].get(k, 0))
    rows = club_rows(ledger, tmap, complete)
    try:
        import trades
        sapi = {c: trades.statsapi_code(c) for c in sorted({r["club"] for r in rows})}
    except Exception:                                   # noqa: BLE001
        sapi = {}
    steal_excluded = dict(attempts.attrs.get("excluded") or {}) if attempts is not None and len(attempts) else {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "mgmt_decisions.py",
        "status": "built",
        "corpus_built_at": manifest.get("built_at"),
        "corpus_schema_version": manifest.get("schema_version"),
        "seasons": seasons_seen,
        "through_by_season": through,
        "n_all": int(len(ledger)),
        "chain_break": {"tolerance": CHAIN_TOL, "by_season": chain,
                        "share_of_plays_not_chained": _r(float(pd.Series(
                            [c["share_of_plays_not_chained"] for c in chain.values()
                             if c.get("share_of_plays_not_chained") is not None]).mean()), 5)
                        if chain else None,
                        "note": ("wpa_home equals wp_home_after minus wp_home_before on every "
                                 "play, every game starts at 50.0 and ends at 0.0 or 100.0, "
                                 "and consecutive plays do not chain on the published share "
                                 "of plays at the published tolerance; so a window is valued "
                                 "as an endpoint difference, never a row sum.")},
        "families": families_block(ledger, baseline, gate, thin_by_family,
                                   {s: m.get("ejections") for s, m in meta_by_season.items()}),
        "gate_status_by_family": gate,
        "floors": FLOORS, "games_floor": GAMES_FLOOR,
        "realized_sentence": REALIZED_SENTENCE,
        "agent_sentence": AGENT_SENTENCE,
        "style_sentence": STYLE_SENTENCE,
        "single_pa_caveat": SINGLE_PA_CAVEAT,
        "overlap_note": OVERLAP_NOTE,
        "dvs_note": DVS_NOTE,
        "li_note": LI_NOTE,
        "no_cross_family_total": True,
        "plus_metric": False,
        "units": {"mwpa": "wins, realized value, not skill (wp percentage points divided by 100)",
                  "dvs": "wins above state, realized, selection not removed",
                  "li": "leverage index, MLB feed basis; null on the leadoff plate appearance",
                  "z": "signed style z-score, not an index, not skill"},
        "removed_pitcher": {**removed,
                            "description_agreement_rate": _r(removed["description_agree"] / removed["description_checked"], 4)
                            if removed["description_checked"] else None,
                            "derivation": REMOVED_DERIVATION},
        "switch_classification": switches,
        "hook_hist": hook_histogram(ledger),
        "steal_excluded": steal_excluded,
        "club_attribution": {"games": len(tmap), "ground_truth": truth},
        "managers_fixture": {"ejection_named_managers": int(ej_named),
                             "ejections": int(sum(m["ejections"]["n"] for m in meta_by_season.values())),
                             "note": ("the ejection rows that name a manager with an mlbam id "
                                      "are the manager ingest's validation fixture, not a source")},
        "clubs": {"status": "built", "n_rows": len(rows), "rows": rows,
                  "statsapi_codes": sapi,
                  "not_summed": ["defensive_sub"],
                  "columns_are_realized_not_skill": REALIZED_SENTENCE,
                  "agent_sentence": AGENT_SENTENCE,
                  "style_sentence": STYLE_SENTENCE,
                  "sort_default": ["n_all", "season"],
                  "realized_header_tag": "realized",
                  "sort_by_realized_is_a_rank_by_what_happened": (
                      "sorting a realized column ranks club-seasons by what happened after "
                      "their decisions, not by how well they chose")},
        "shards": {"dir": "data/mgmt_decisions", "path_template": "/data/mgmt_decisions/{season}-{club}.json",
                   "index": index, "schema_note": mgmt_shards.SCHEMA_NOTE},
        "baseline_artifact": "data/management_baseline.json",
    }


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default=None, help="comma-separated, default every season")
    ap.add_argument("--no-shards", action="store_true")
    ap.add_argument("--corpus", default=None)
    a = ap.parse_args(argv)
    seasons = [s.strip() for s in a.seasons.split(",")] if a.seasons else None
    d = build(corpus=Path(a.corpus) if a.corpus else None, seasons=seasons, shards=not a.no_shards)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e3:.0f} KB): status {d.get('status')}")
    if d.get("status") == "built":
        print(f"  {d['n_all']:,} decisions over {len(d['seasons'])} seasons; "
              f"{d['clubs']['n_rows']} club-seasons; {len(d['shards']['index'])} shards")
        for f, blk in d["families"].items():
            print(f"  {f:18s} n={blk['n']:>7,}  gate={blk['gate_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
