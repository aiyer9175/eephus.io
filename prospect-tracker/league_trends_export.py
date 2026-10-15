# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""league_trends_export - the League Trends payload (plan 4.3 to 4.5, 5.1 and
5.2; task TR_3_EXPORT_PIPELINE_DARK).

WHAT IT WRITES. One file, ``league_trends.json``: the Players list (a change in
a player's own measured trait that clears its family's calibrated bar, as of
the frame's last game date), the three rule events (rotation, new pitch,
lineup), the Teams rows and the League cards. While MLBSTATS_TRENDS_LIVE is
False it writes only ``.cache/league_trends/preview/league_trends.json`` and
nothing under data/ (class 2, plan 1 item 8).

AS OF. ``as_of`` equals ``covers_through``, the last game date the trend frame
(trend_frames.pitch_game_frame) holds, never a build date. ``coverage`` is
{games, expected} so the page's banner renders it unchanged (plan 4.5).

THE FALSE RATE IS COMPUTED, NEVER TYPED. Each family carries the per-test
placebo tail at its bar from the eval artifact and the number of tests run
today; ``false_per_day = tail_per_test x tests_today``. A family that also ran
prior-season tests (plan 3.8, early season only) carries them apart in
``prior`` with their own tail, tests and false_per_day. ``method.false_per_day``
is the sum over families of both (plan 3.4, ruling T1).

THE BARS ARE THE ARTIFACT'S. trend_detect.BARS must equal the eval artifact's
bars (and the placebo SDs its placebo_sd); otherwise the export refuses.

REFUSES, KEEPING THE LAST GOOD FILE, on: a stale frame (as_of more than
MAX_LAG_DAYS before the boards' last game date, compared by GAME dates, never
build stamps; the off-season is therefore never stale), a missing eval
artifact, a bar in code that differs from the artifact, club identity under
mgmt_teams.MIN_RESOLVED_SHARE (trend_frames refuses), no sidecar table for the
live season, or a payload over the 60 KB raw budget.

LEAVES OFF, NEVER REFUSES: a family whose monthly live_check failed (the
eval artifact's live_check block), and the swing families when a needed swing
season is missing (named in ``swing_missing`` and in the ingest row) or, in
season, when the swing source's latest game date (D_swing, carried as
families[].as_of) is more than SWING_MAX_LAG_DAYS before as_of.

TEAMS. Run differential over the last 10 and 30 club games with the chance
band from the eval artifact's rd_band, bullpen relief counts over 3 and 7
days, and the club's cards and events. Nothing in Teams is computed while
rd_band is null (plan 4.3: the eval artifact leaves it null until
docs/diamond-betting.md records the 5c-A look and the 5d and 5k reads or their
closures); build_teams is exercised on fixtures until then.

LEAGUE. Strikeout rate, walk rate and home runs per PA read P8.2's series
(series_ref, the live season included); pitches per PA and starter innings per
start (the starts-only sp_ip_per_gs, never ip_per_gs) read it for COMPLETED
seasons only and cite section 5m's Disqualification paragraph of
docs/diamond-betting.md (ruling R5); the stolen-base attempts per club game
card and the three pitch-environment cards carry their own values by season
(the eval artifact's league_env for completed seasons, the sidecar for the live
season; no series_ref, ruling R4). The notable rule runs on completed seasons
only.

WHAT IT NEVER DOES. Relate a trend, a club series or a league series to a game
result, a price, a ledger row or a later value of the same trait; build a
per-hand or grade output; build a pitch-count, innings-per-start or
pitches-per-PA trend at the player or club level; read a betting cache, a
vintage, a lineup, odds, weather or game-feed cache. Club identity comes from
trend_frames (the half-inning vote), never the corpus map builder.

Run:
    python league_trends_export.py            (writes the preview while dark)
    python league_trends_export.py --dry-run  (builds, prints, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

import trend_detect as TD
import trend_frames as TF

#: The flag. False: the payload goes under .cache/league_trends/preview/ only.
MLBSTATS_TRENDS_LIVE = False

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
PREVIEW_DIR = CACHE_DIR / "league_trends" / "preview"
NOSWING_MEMO_DIR = CACHE_DIR / "league_trends" / "frames_noswing"
OUT_NAME = "league_trends.json"
EVAL_NAME = "league_trends_eval.json"
SERIES_NAME = "mlb_league_series.json"
SCHEMA = 1
SOURCE = "league_trends_export"

#: The frame may trail the boards' last game by this many days (game dates).
MAX_LAG_DAYS = 2
#: In season, the swing families are left off when D_swing trails as_of by more.
SWING_MAX_LAG_DAYS = 7
#: Sparkline points: the last 20 game values (plan 4.2).
SPARK_N = 20
#: Raw payload budget (plan 4.5).
BUDGET_RAW = 60_000
#: Days walked back to find a listed change's first flagged date.
EPISODE_LOOKBACK_DAYS = 60
#: The 30-day context window (plan 4.2).
CONTEXT_DAYS = 30
#: The season is final once the frame holds this share of the expected games
#: and its last game is at least two days old.
FINAL_SHARE = 0.995

BOARDS = (("hitter_leaderboards", "hitters", "hem_plus", "HEM+"),
          ("starter_leaderboards", "starters", "sem_plus", "SEM+"),
          ("bullpen_leaderboards", "relievers", "rem_plus", "REM+"),
          ("defense_leaderboards", "fielders", None, None))

# --------------------------------------------------------------------------- #
# copy
# --------------------------------------------------------------------------- #
NOUN = {"sp_velo": "Fastball velocity", "rp_velo": "Fastball velocity",
        "sp_ivb": "Fastball induced vertical break", "rp_ivb": "Fastball induced vertical break",
        "sp_hb": "Fastball horizontal break", "rp_hb": "Fastball horizontal break",
        "sp_spin": "Fastball spin", "rp_spin": "Fastball spin",
        "sp_ext": "Fastball extension", "rp_ext": "Fastball extension",
        "bat_speed": "Bat speed", "swing_length": "Swing length",
        "attack_angle": "Attack angle"}
TYPE = {"sp_velo": "velocity", "rp_velo": "velocity", "mix": "mix", "rp_entry_li": "role",
        "bat_speed": "swing", "swing_length": "swing", "attack_angle": "swing"}
UNIT_WORD = {"mph": "mph", "in": "in", "rpm": "rpm", "ft": "ft", "deg": "degrees"}
DECIMALS = {"mph": 1, "in": 1, "rpm": 0, "ft": 2, "deg": 1, "share": 1, "log LI": 2}
NOISE = {"SP": "start-to-start", "RP": "outing-to-outing", "H": "game-to-game"}
GAMES_WORD = {"SP": ("start", "starts"), "RP": ("outing", "outings"), "H": ("game", "games")}
GROUP_LABEL = {"FF": "a four-seam fastball", "SI": "a sinker", "FC": "a cutter",
               "SL": "a slider or sweeper", "CU": "a curveball", "CH": "a changeup or splitter",
               "KN": "a knuckleball", "EP": "an eephus"}
FOLD = ("Each change is measured against the player's own earlier games this season and net "
        "of the league-wide change over the same dates. A change is listed when it clears a "
        "bar set so that, in 2023 to 2025 for pitchers and 2024 to 2025 for swings, about 1 "
        "listed change in {one_in} came from game-to-game noise alone; today's list expects "
        "about {false_per_day} from noise. Descriptive: this is what changed, not what comes "
        "next.")
CONTEXT_NOTE = ("Shown as context: in 2023 to 2025 no results measure separated real changes "
                "from chance well enough to be listed.")
FIVE_M_NOTE = ("One league-wide value per completed season, read from the League Averages "
               "series. No season-to-date value is shown: the Disqualification paragraph of "
               "section 5m of docs/diamond-betting.md names season-to-date and club-level "
               "forms of starter workload as close variants of a registered betting "
               "candidate.")
TEAMS_NOTE = ("The Teams view is not computed yet: its chance band waits on records the "
              "betting registration has not made.")

# --------------------------------------------------------------------------- #
# the League cards (plan 4.4)
# --------------------------------------------------------------------------- #
#: (key, label, side, series key, unit word, scale, decimals, completed seasons only)
SERIES_CARDS = (
    ("k_rate", "Strikeout rate", "hit", "k_pct", "percent of plate appearances", 100.0, 1, False),
    ("bb_rate", "Walk rate", "hit", "bb_pct", "percent of plate appearances", 100.0, 1, False),
    ("hr_rate", "Home runs per plate appearance", "hit", "hr_pct",
     "percent of plate appearances", 100.0, 2, False),
    ("p_per_pa", "Pitches per plate appearance", "hit", "p_per_pa", "pitches", 1.0, 2, True),
    ("sp_ip_per_gs", "Starter innings per start", "pit", "sp_ip_per_gs", "innings", 1.0, 2, True),
)
#: Cards that show completed seasons only (plan 4.4, ruling R5).
COMPLETED_ONLY = frozenset(card[0] for card in SERIES_CARDS if card[-1])
#: (key, label, league_env field, unit word, decimals)
OWN_CARDS = (
    ("sba_per_club_game", "Stolen-base attempts per club game", "sba_per_club_game",
     "attempts", 2),
    ("ff_velo", "Four-seam velocity", "ff_mph", "mph", 2),
    ("st_share", "Sweeper share, as labelled in MLB's feed", "st_pct", "percent of pitches", 2),
    ("fs_share", "Splitter share, as labelled in MLB's feed", "fs_pct", "percent of pitches", 2),
)
#: P8.2's series: year-to-year changes into these seasons are left out of the
#: notable SD, which runs over the changes into 2001 to 2025.
SERIES_EXCLUDED = (2020, 2021)
SERIES_SD_FIRST, SERIES_SD_LAST = 2001, 2025
#: The sidecar's own family (2018, 2019, 2021 on): the changes from 2021 to
#: 2022 on enter the notable SD; 2019 to 2021 is excluded (plan 4.4).
OWN_EXCLUDED = (2021,)
OWN_SD_FIRST = 2022


class Refused(Exception):
    """Nothing is written; the last good file stands."""


# --------------------------------------------------------------------------- #
# paths and inputs
# --------------------------------------------------------------------------- #
def out_dir() -> Path:
    """data/ only once the flag is flipped; the preview directory until then."""
    return DATA_DIR if MLBSTATS_TRENDS_LIVE else PREVIEW_DIR


def eval_path() -> Path:
    """The eval artifact beside the payload (the lab's own rule)."""
    return (DATA_DIR if MLBSTATS_TRENDS_LIVE else PREVIEW_DIR) / EVAL_NAME


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _r(v, nd: int):
    """Round to nd decimals; never a negative zero."""
    f = _num(v)
    if f is None:
        return None
    out = round(f, nd) + 0.0
    return int(out) if nd == 0 else out


def _fmt(v, nd: int) -> str:
    return f"{abs(float(v)):.{nd}f}"


def _minus(d: str, days: int) -> str:
    return (date.fromisoformat(str(d)[:10]) - timedelta(days=int(days))).isoformat()


def live_boards(data_dir: Optional[Path] = None) -> dict:
    """{"season", "as_of", "rows": {board: rows}} off the live boards (names,
    positions and season indexes)."""
    d = Path(data_dir or DATA_DIR)
    out = {"season": None, "as_of": None, "rows": {}}
    for name, block, _f, _l in BOARDS:
        blob = _read_json(d / f"{name}.json") or {}
        if blob.get("season") is None:
            continue
        s = int(blob["season"])
        if out["season"] is None or s > out["season"]:
            out["season"] = s
        a = blob.get("as_of")
        if a and (out["as_of"] is None or str(a)[:10] > out["as_of"]):
            out["as_of"] = str(a)[:10]
        out["rows"][name] = (s, blob.get(block) or [])
    out["rows"] = {n: rows for n, (s, rows) in out["rows"].items() if s == out["season"]}
    return out


def live_season(data_dir: Optional[Path] = None) -> int:
    """The boards' season, else the calendar year."""
    s = live_boards(data_dir).get("season")
    return int(s) if s else date.today().year


def boards_last_game_date(as_of: Optional[str], game_dates) -> Optional[str]:
    """The latest game date on or before the boards' as_of."""
    if not as_of:
        return None
    eligible = [str(d) for d in game_dates if d and str(d) <= str(as_of)[:10]]
    return max(eligible) if eligible else None


def stale_reason(covers_through: Optional[str], boards_last_game: Optional[str],
                 max_lag_days: int = MAX_LAG_DAYS) -> Optional[str]:
    """Why the frame is too far behind the boards to export, or None. GAME
    dates only, never a build stamp."""
    if not covers_through:
        return "the trend frame covers no game of the live season"
    if not boards_last_game:
        return None
    lag = (date.fromisoformat(boards_last_game) - date.fromisoformat(covers_through)).days
    if lag > max_lag_days:
        return (f"the trend frame covers games through {covers_through}, {lag} days before the "
                f"boards' last game on {boards_last_game} (more than {max_lag_days})")
    return None


def bars_mismatch(art: dict) -> Optional[str]:
    """Why trend_detect's bars disagree with the eval artifact, or None."""
    pol = TD.BAR_POLICY
    if TD.BARS_PROVISIONAL:
        return "trend_detect.BARS is still the provisional table"
    code = {k: float(v) for k, v in TD.BARS[pol].items()}
    have = {k: float(v) for k, v in ((art.get("bars") or {}).get(pol) or {}).items()}
    if code != have:
        diff = sorted(set(code.items()) ^ set(have.items()))
        return f"the {pol} bars in trend_detect differ from the eval artifact: {diff}"
    psd = art.get("placebo_sd") or {}
    for k in have:
        a = _num(psd.get(k))
        if a is None or abs(TD.phi_for(k) - a) > 5e-5:
            return f"{k}: the placebo SD in trend_detect ({TD.phi_for(k)}) differs from the artifact ({a})"
    extra = sorted(set(art.get("served") or []) - set(have))
    if extra:
        return f"the eval artifact serves families with no {pol} bar: {extra}"
    return None


def production_fit(art: dict, key: str) -> Optional[dict]:
    """The production shrink fit of one family, as trend_detect.flag takes it."""
    rec = ((art.get("shrink") or {}).get("fits") or {}).get(key)
    if not rec:
        return None
    fit = {"kind": rec["kind"], "pi0": float(rec["pi0"]), "tau": float(rec["tau"]),
           "identified": bool(rec.get("identified")), "seasons": rec.get("seasons")}
    if rec["kind"] == "mix_selected_null":
        mn = art.get("mix_null") or {}
        if not mn.get("t"):
            fit["identified"] = False
        else:
            fit["null"] = {"t": np.asarray(mn["t"], dtype="float64"), "h": float(mn["h"])}
    return fit


# --------------------------------------------------------------------------- #
# detection at a date
# --------------------------------------------------------------------------- #
def _flags(frame, prior, D: str, key: str, art: dict, swing_ok: bool) -> tuple:
    """(in-season tests, prior-season tests, flagged rows) for one family at D."""
    fam = TD.FAMILIES[key]
    phi = TD.phi_for(key)
    bar = float(TD.bar_for(key))
    tests = TD.detect(frame, D, fam, phi=phi)
    fl = TD.flag(tests, fam, bar, production_fit(art, key), phi=phi)
    fl = fl.assign(mode="in_season")
    tp = None
    if prior is not None and key not in TD.PRIOR_EXCLUDED and fam.kind != "mix" \
            and (fam.kind != "swing" or swing_ok):
        tp = TD.detect_prior(frame, prior, D, fam, phi=phi, swing_ok=swing_ok)
        if len(tp):
            fp = TD.flag(tp, fam, float(TD.PRIOR_SEASON_BAR), None, phi=phi)
            fp = fp.assign(mode="prior_season")
            fl = pd.concat([fl, fp], ignore_index=True) if len(fl) else fp
    hit = fl[fl["flag"].astype(bool)] if len(fl) else fl
    return tests, (tp if tp is not None else TD._empty_tests(["mode"])), hit


def first_flagged(frame, prior, D: str, key: str, art: dict, swing_ok: bool,
                  pids, lookback: int = EPISODE_LOOKBACK_DAYS) -> dict:
    """{pid: first date of the run of consecutive daily flags ending at D}."""
    first = {int(p): D for p in pids}
    live = set(first)
    d = D
    for _ in range(int(lookback)):
        if not live:
            break
        d = _minus(d, 1)
        _t, _p, hit = _flags(frame, prior, d, key, art, swing_ok)
        on = set(int(x) for x in hit["pid"]) if len(hit) else set()
        for p in list(live):
            if p in on:
                first[p] = d
            else:
                live.discard(p)
    return first


# --------------------------------------------------------------------------- #
# the player cards
# --------------------------------------------------------------------------- #
def _names(boards: dict) -> dict:
    out: dict = {}
    for name, rows in boards.get("rows", {}).items():
        for r in rows:
            m = r.get("mlbam")
            if m is None:
                continue
            e = out.setdefault(int(m), {})
            if r.get("name") and not e.get("name"):
                e["name"] = r["name"]
            if name == "defense_leaderboards" and r.get("pos") and not e.get("pos"):
                e["pos"] = r["pos"]
            for bname, _b, field, label in BOARDS:
                if bname == name and field and r.get(field) is not None:
                    e.setdefault("index", {})[label] = r.get(field)
    return out


def _pal_sets(pal: Optional[dict]) -> dict:
    out = {}
    for k in ("rp2sp", "sp2rp", "pitch_add"):
        out[k] = {int(r["mlbam"]) for r in (pal or {}).get(k) or [] if r.get("mlbam") is not None}
    return out


def _last_club(frame, pid: int, D: str, side: str) -> Optional[str]:
    t = frame.bat if side == "H" else frame.pit
    col = "batter" if side == "H" else "pitcher"
    u = t[(t[col] == pid) & (t["date"] <= D) & t["club"].notna()]
    if not len(u):
        return None
    return str(u.sort_values("game_seq", kind="mergesort")["club"].iloc[-1])


def _context(frame, pid: int, D: str, side: str, idx: dict) -> dict:
    """The 30-day OBP (hitters) or K-BB% per batter faced (pitchers) against
    the earlier games, and the season index; context only (plan 4.2)."""
    lo = _minus(D, CONTEXT_DAYS - 1)
    out: dict = {"note": CONTEXT_NOTE}
    if side == "H":
        u = frame.bat[(frame.bat["batter"] == pid) & (frame.bat["date"] <= D)]
        w, b = u[u["date"] >= lo], u[u["date"] < lo]

        def obp(x):
            num = x["h"].sum() + x["bb"].sum() + x["hbp"].sum()
            den = x["ab"].sum() + x["bb"].sum() + x["hbp"].sum() + x["sf"].sum()
            return _r(num / den, 3) if den else None
        out["obp_30d"] = {"window": obp(w), "before": obp(b), "pa_window": int(w["pa"].sum()),
                          "pa_before": int(b["pa"].sum())}
        lab = "HEM+"
    else:
        u = frame.pit[(frame.pit["pitcher"] == pid) & (frame.pit["date"] <= D)]
        w, b = u[u["date"] >= lo], u[u["date"] < lo]

        def kbb(x):
            bf = x["bf"].sum()
            return _r(100.0 * (x["so"].sum() - x["bb"].sum()) / bf, 1) if bf else None
        out["k_bb_30d"] = {"window": kbb(w), "before": kbb(b), "bf_window": int(w["bf"].sum()),
                           "bf_before": int(b["bf"].sum())}
        lab = "SEM+" if side == "SP" else "REM+"
    ix = (idx or {}).get(lab)
    if ix is None and side != "H":
        alt = "REM+" if lab == "SEM+" else "SEM+"
        if (idx or {}).get(alt) is not None:
            ix, lab = idx[alt], alt
    out["index"] = {"label": lab, "value": None if ix is None else int(math.floor(float(ix) + 0.5))}
    return out


def _spark(frame, D: str, key: str, row, prior_frame=None) -> dict:
    """The last SPARK_N game values to D, the window's count among them and
    the baseline mean, in the card's display units. A prior-season card takes
    this season's values the way prior-season mode reads them (its player is
    under the in-season baseline floor)."""
    fam = TD.FAMILIES[key]
    pid = int(row["pid"])
    nd = DECIMALS.get(fam.unit, 2)
    if fam.kind == "mix":
        w = TD.mix_values(frame, D)
        w = w[w["pid"] == pid]
        sel = row.get("fam_sel")
        g = w.groupby(["game_seq"])[[sel, "tot"]].sum().sort_index()
        vals = (100.0 * g[sel] / g["tot"]).to_numpy(dtype="float64")
        base = 100.0 * float(row["share_b"])
    else:
        if row["mode"] == "prior_season" and prior_frame is not None:
            vt = TD._prior_values(frame, prior_frame, D, fam)[0]
        else:
            vt = TD.game_values(frame, D, fam)
        vt = vt[vt["pid"] == pid].sort_values("game_seq", kind="mergesort")
        vals = vt["value"].to_numpy(dtype="float64")
        base = float(row["mean_b"])
        if fam.log_value:
            vals, base = np.exp(vals), math.exp(base)
    v = [_r(x, nd) for x in vals[-SPARK_N:]]
    return {"v": v, "w": int(min(int(row["nW"]), len(v))), "base": _r(base, nd)}


def _card_numbers(key: str, row) -> dict:
    """Display numbers of one flagged test, rounded as printed."""
    fam = TD.FAMILIES[key]
    nd = DECIMALS.get(fam.unit, 2)
    sh = _num(row.get("shrunk"))
    if fam.kind == "mix":
        return {"window": _r(100.0 * row["share_w"], 1), "baseline": _r(100.0 * row["share_b"], 1),
                "change": _r(100.0 * row["raw"], 1), "drift": _r(100.0 * row["drift"], 1),
                "net": _r(100.0 * row["d"], 1),
                "shrunk": _r(100.0 * sh, 1) if sh is not None else None,
                "expected": _r(100.0 * row["expected_w"], 1)}
    if fam.log_value:
        return {"window": _r(math.exp(row["mean_w"]), 2), "baseline": _r(math.exp(row["mean_b"]), 2),
                "change": _r(math.exp(row["raw"]), 2), "drift": _r(math.exp(row["drift"]), 2),
                "net": _r(math.exp(row["d"]), 2),
                "shrunk": _r(math.exp(sh), 2) if sh is not None else None}
    return {"window": _r(row["mean_w"], nd), "baseline": _r(row["mean_b"], nd),
            "change": _r(row["raw"], nd), "drift": _r(row["drift"], nd), "net": _r(row["d"], nd),
            "shrunk": _r(sh, nd) if sh is not None else None}


def card_sentence(c: dict) -> str:
    """The card's sentence from its own fields (every number is a field)."""
    key, role = c["family"], c["role"]
    one, many = GAMES_WORD[role]
    nW, nB = c["window"]["n"], c["baseline"]["n"]
    w, b = c["window"]["value"], c["baseline"]["value"]
    fam = TD.FAMILIES[key]
    nd = DECIMALS.get(fam.unit, 2)
    if c["mode"] == "prior_season":
        ps = c["prior_season"]
        noun = NOUN[key]
        word = "changed by" if key.endswith("_hb") else ("up" if c["dir"] > 0 else "down")
        over = (f"over the last {c['window_days']} days" if fam.kind == "swing"
                else f"over his last {nW} {many if nW != 1 else one}")
        return (f"{noun} {word} {_fmt(c['change'], nd)} {UNIT_WORD[fam.unit]} from {ps}: "
                f"{_fmt(w, nd)} {over} against {_fmt(b, nd)} in {nB} {many} of {ps}.")
    if fam.kind == "mix":
        more = "more" if c["dir"] > 0 else "fewer"
        s = (f"Throwing {more} {TD.MIX_LABEL[c['mix']['group']]}: {_fmt(w, 1)} percent of his "
             f"pitches over his last {nW} {many} against {_fmt(b, 1)} percent in {nB} earlier "
             f"{many} ({_fmt(c['mix']['expected'], 1)} percent expected for the batters he "
             f"faced)")
        if c.get("shrunk") is not None:
            s += (f"; shrunk toward no change for game-to-game noise, "
                  f"{_fmt(c['shrunk'], 1)} points")
        return s + "."
    if fam.log_value:
        hl = "higher" if c["dir"] > 0 else "lower"
        s = (f"First-batter Leverage Index {hl}: a typical {_fmt(w, 2)} over his last {nW} "
             f"outings against {_fmt(b, 2)} in {nB} earlier outings")
        if c.get("shrunk") is not None:
            s += (f"; shrunk toward no change for outing-to-outing noise, a factor of "
                  f"{_fmt(c['shrunk'], 2)}")
        return s + "."
    noun = NOUN[key]
    word = "changed by" if key.endswith("_hb") else ("up" if c["dir"] > 0 else "down")
    unit = UNIT_WORD[fam.unit]
    if fam.kind == "swing":
        s = (f"{noun} {word} {_fmt(c['change'], nd)} {unit}: {_fmt(w, nd)} on competitive "
             f"swings over the last {c['window_days']} days ({nW} games) against "
             f"{_fmt(b, nd)} in {nB} earlier games")
    else:
        s = (f"{noun} {word} {_fmt(c['change'], nd)} {unit}: {_fmt(w, nd)} over his last "
             f"{nW} {many} against {_fmt(b, nd)} in his {nB} earlier {many}")
    if c.get("shrunk") is not None:
        s += (f"; shrunk toward no change for {NOISE[role]} noise, "
              f"{_fmt(c['shrunk'], nd)} {unit}")
    return s + "."


def _strength(az: float, bar: float) -> int:
    return 1 + int(az >= bar + 1.0) + int(az >= bar + 2.0)


def _links(pid: int, role: str, key: str, pal: dict) -> dict:
    board = {"SP": "starters", "RP": "bullpen", "H": "hitters"}[role]
    p = None
    if TYPE.get(key) == "velocity" or key == "rotation":
        p = ("/pal/#rp2sp" if pid in pal["rp2sp"] else
             "/pal/#sp2rp" if pid in pal["sp2rp"] else None)
    elif key in ("mix", "new_pitch") and pid in pal["pitch_add"]:
        p = "/pal/#pitchadd"
    return {"board": f"/mlbstats/#section={board}&player={pid}", "pal": p}


def player_card(frame, D: str, key: str, row, first: str, names: dict, pal: dict,
                prior_season: Optional[int], prior_frame=None) -> dict:
    fam = TD.FAMILIES[key]
    pid = int(row["pid"])
    role = str(row["role"])
    nums = _card_numbers(key, row)
    bar = float(TD.PRIOR_SEASON_BAR if row["mode"] == "prior_season" else TD.bar_for(key))
    az = abs(float(row["z_adj"]))
    info = names.get(pid, {})
    c = {
        "id": f"{key}:{pid}:{first}", "mlbam": pid, "name": info.get("name"),
        "club": _last_club(frame, pid, D, role),
        "pos": role if role in ("SP", "RP") else info.get("pos"),
        "role": role, "family": key, "type": TYPE.get(key, "shape"),
        "mode": row["mode"],
        "dir": 1 if float(row["d"]) > 0 else -1,
        "z": _r(float(row["z_adj"]), 1), "bar": bar, "strength": _strength(az, bar),
        "first_flagged": first, "unit": fam.unit,
        "window": {"value": nums["window"], "n": int(row["nW"]),
                   "from": str(row["w_first"])[:10], "to": str(row["w_last"])[:10]},
        "baseline": {"value": nums["baseline"], "n": int(row["nB"])},
        "change": nums["change"], "drift": nums["drift"], "net": nums["net"],
        "shrunk": nums["shrunk"] if row["mode"] == "in_season" else None,
    }
    if fam.kind == "swing":
        c["window_days"] = int(fam.window["H"][1])
    if row["mode"] == "prior_season":
        c["prior_season"] = int(prior_season) if prior_season else None
    if fam.kind == "mix":
        c["mix"] = {"group": row["fam_sel"], "label": TD.MIX_LABEL[row["fam_sel"]],
                    "expected": nums["expected"]}
    c["spark"] = _spark(frame, D, key, row, prior_frame)
    c["sentence"] = card_sentence(c)
    c["context"] = _context(frame, pid, D, role, info.get("index") or {})
    c["links"] = _links(pid, role, key, pal)
    return c


# --------------------------------------------------------------------------- #
# the rule events (plan 3.7)
# --------------------------------------------------------------------------- #
def event_sentence(e: dict) -> str:
    if e["rule"] == "rotation":
        if e["direction"] == "into":
            return (f"Moved into the rotation: {e['window']} straight starts after "
                    f"{e['earlier_relief']} relief outings.")
        return (f"Moved out of the rotation: {e['window']} straight relief outings after "
                f"{e['earlier_starts']} starts.")
    if e["rule"] == "new_pitch":
        many = GAMES_WORD[e["role"]][1]
        return (f"New pitch: {GROUP_LABEL.get(e['group'], 'a new pitch type')}, "
                f"{_fmt(e['share_w'], 1)} percent of his pitches over his last {e['window_games']} "
                f"{many} after {_fmt(e['share_b'], 1)} percent of {e['n_b_tot']} earlier pitches.")
    word = "In" if e["direction"] == "in" else "Out of"
    return (f"{word} the lineup: started {e['started_w']} of his club's last "
            f"{e['window_games']} games after starting {_fmt(e['share_b'], 0)} percent of the "
            f"{e['available_b']} games he was available for.")


def rule_events(frame, D: str, names: dict, pal: dict) -> list:
    out = []
    roles = TD.roles_as_of(frame, D)
    for _, r in TD.rotation_switch(frame, D).iterrows():
        pid = int(r["pid"])
        out.append({"id": f"rotation:{pid}:{D}", "rule": "rotation", "type": "role",
                    "mlbam": pid, "role": "SP" if r["direction"] == "into" else "RP",
                    "direction": r["direction"], "window": int(r["window"]),
                    "earlier": int(r["earlier"]), "earlier_starts": int(r["earlier_starts"]),
                    "earlier_relief": int(r["earlier_relief"])})
    for _, r in TD.new_pitch(frame, D).iterrows():
        pid = int(r["pid"])
        role = str(roles.get(pid, "RP"))
        k = TD.FAMILIES["mix"].window[role][1]
        out.append({"id": f"new_pitch:{pid}:{r['group']}:{D}", "rule": "new_pitch",
                    "type": "new_pitch", "mlbam": pid, "role": role, "group": r["group"],
                    "window_games": int(k), "share_w": _r(100.0 * r["share_w"], 1),
                    "n_w": int(r["n_w"]), "share_b": _r(100.0 * r["share_b"], 1),
                    "n_b_tot": int(r["n_b_tot"]), "speed_w": _r(r["speed_w"], 1)})
    for _, r in TD.playing_time(frame, D).iterrows():
        pid = int(r["pid"])
        out.append({"id": f"playing_time:{pid}:{D}", "rule": "playing_time",
                    "type": "playing_time", "mlbam": pid, "role": "H",
                    "direction": r["direction"], "window_games": int(TD.PT_WINDOW),
                    "started_w": int(r["started_w"]), "appeared_w": int(r["appeared_w"]),
                    "share_b": _r(100.0 * r["share_b"], 0),
                    "available_b": int(r["available_b"])})
    for e in out:
        info = names.get(e["mlbam"], {})
        e["name"] = info.get("name")
        e["club"] = _last_club(frame, e["mlbam"], D, e["role"])
        e["pos"] = e["role"] if e["role"] in ("SP", "RP") else info.get("pos")
        e["date"] = D
        e["sentence"] = event_sentence(e)
        e["links"] = _links(e["mlbam"], e["role"], e["rule"], pal)
    return out


# --------------------------------------------------------------------------- #
# Teams (plan 4.3): built only when the eval artifact carries rd_band
# --------------------------------------------------------------------------- #
def team_sentence(t: dict) -> str:
    rd = t["rd"]
    a, b = rd["l10"], rd["before_l10"]
    return (f"Last {a['n']} games: {_fmt(a['rs'], 1)} runs scored and {_fmt(a['ra'], 1)} allowed "
            f"a game, against {_fmt(b['rs'], 1)} and {_fmt(b['ra'], 1)} in {b['n']} games before. "
            f"A {a['n']}-game stretch of run differential moves by about "
            f"{_fmt(rd['band_l10'], 1)} runs a game by chance alone.")


def build_teams(frame, D: str, rd_band: dict, cards: list, events: list) -> list:
    """One row per club: run differential over the last 10 and 30 club games
    against its earlier games with the chance band, bullpen relief outs and
    pitches over 3 and 7 days ranked across clubs, and the club's card and
    event ids. Counts and runs only; nothing flags a club."""
    sig = float(rd_band["sigma_m"])
    g = frame.games[(frame.games["date"] <= D) & frame.games["home"].notna()
                    & frame.games["away"].notna()]
    g = g.dropna(subset=["home_score", "away_score"])
    rows = pd.concat([
        pd.DataFrame({"club": g["home"], "seq": g["game_seq"], "rs": g["home_score"],
                      "ra": g["away_score"]}),
        pd.DataFrame({"club": g["away"], "seq": g["game_seq"], "rs": g["away_score"],
                      "ra": g["home_score"]})]).sort_values(["club", "seq"], kind="mergesort")
    rel = frame.pit[(frame.pit["date"] <= D) & (~frame.pit["start"].astype(bool))
                    & frame.pit["club"].notna()]
    pen = {}
    for days in (3, 7):
        u = rel[rel["date"] >= _minus(D, days - 1)]
        pen[days] = u.groupby("club")[["outs", "np"]].sum()
    out = []
    for club in sorted(set(rows["club"])):
        r = rows[rows["club"] == club]
        rd = {}
        for k in (10, 30):
            last, before = r.iloc[-k:], r.iloc[:-k]
            nb = len(before)
            rd[f"l{k}"] = {"n": int(len(last)), "rs": _r(last["rs"].mean(), 1),
                           "ra": _r(last["ra"].mean(), 1),
                           "rd": _r((last["rs"] - last["ra"]).mean(), 1)}
            rd[f"before_l{k}"] = {"n": int(nb),
                                  "rs": _r(before["rs"].mean(), 1) if nb else None,
                                  "ra": _r(before["ra"].mean(), 1) if nb else None,
                                  "rd": _r((before["rs"] - before["ra"]).mean(), 1) if nb else None}
            rd[f"band_l{k}"] = (_r(sig * math.sqrt(1.0 / len(last) + 1.0 / nb), 1)
                                if nb and len(last) else None)
        t = {"club": club, "rd": rd, "pen": {}}
        for days in (3, 7):
            s = pen[days]
            t["pen"][f"relief_outs_{days}d"] = int(s["outs"].get(club, 0)) if len(s) else 0
            t["pen"][f"relief_pitches_{days}d"] = int(s["np"].get(club, 0)) if len(s) else 0
        t["card_ids"] = [c["id"] for c in cards if c.get("club") == club]
        t["event_ids"] = [e["id"] for e in events if e.get("club") == club]
        out.append(t)
    for days in (3, 7):
        for f in (f"relief_outs_{days}d", f"relief_pitches_{days}d"):
            vals = sorted((t["pen"][f] for t in out), reverse=True)
            med = float(np.median(vals)) if vals else None
            for t in out:
                t["pen"][f"{f}_rank"] = 1 + sum(1 for v in vals if v > t["pen"][f])
                t["pen"][f"{f}_median"] = _r(med, 1)
    for t in out:
        ok = t["rd"]["before_l10"]["n"] and t["rd"]["band_l10"] is not None
        t["sentence"] = team_sentence(t) if ok else None
    return out


# --------------------------------------------------------------------------- #
# League (plan 4.4)
# --------------------------------------------------------------------------- #
def _notable(hist: dict, season: int, excluded: tuple, sd_first: int, sd_last: int) -> dict:
    """The notable rule on a completed season: a change of at least twice the
    SD of the year-to-year changes (into sd_first to sd_last, the excluded
    seasons left out), a run of three or more same-direction seasons, or a high
    or low of every season on file."""
    ys = sorted(hist)
    ch = []
    for a, b in zip(ys, ys[1:]):
        if b < sd_first or b > sd_last or b in excluded:
            continue
        ch.append(hist[b] - hist[a])
    sd = float(np.std(ch, ddof=1)) if len(ch) >= 3 else None
    i = ys.index(season)
    prev = ys[i - 1] if i > 0 else None
    change = hist[season] - hist[prev] if prev is not None else None
    run = 0
    if change is not None and change != 0:
        sgn = 1 if change > 0 else -1
        j = i
        while j > 0:
            d = hist[ys[j]] - hist[ys[j - 1]]
            if d == 0 or (1 if d > 0 else -1) != sgn:
                break
            run += 1
            j -= 1
    upto = [hist[y] for y in ys[:i + 1]]
    why = []
    if sd and change is not None and abs(change) >= 2.0 * sd:
        why.append("big_change")
    if run >= 3:
        why.append("run")
    if len(upto) >= 3 and hist[season] >= max(upto):
        why.append("high")
    if len(upto) >= 3 and hist[season] <= min(upto):
        why.append("low")
    return {"prev_season": prev, "run": run, "sd_change": sd, "why": why}


def league_sentence(c: dict, in_season: bool = True) -> str:
    nd = c["decimals"]
    so_far = " so far" if (not c["complete"] and in_season) else ""
    s = f"{c['label']}: {_fmt(c['value'], nd)} {c['unit']} in {c['season']}{so_far}"
    if c.get("prev") is not None:
        s += f", against {_fmt(c['prev'], nd)} in {c['prev_season']}"
    s += "."
    why = c.get("notable_why") or []
    if "high" in why:
        s += f" The highest of every season on file since {c['first_season']}."
    elif "low" in why:
        s += f" The lowest of every season on file since {c['first_season']}."
    if "run" in why:
        word = "up" if c["value"] > (c["prev"] or 0) else "down"
        s += f" {word.capitalize()} in each of the last {c['run']} seasons."
    if "big_change" in why:
        s += " A change at least twice the typical year-to-year change."
    return s


def _card(key, label, unit, nd, hist: dict, season: int, complete: bool, first: int,
          excluded: tuple, sd_first: int, sd_last: int, in_season: bool) -> dict:
    c = {"key": key, "label": label, "unit": unit, "decimals": nd, "season": int(season),
         "complete": bool(complete), "value": _r(hist[season], nd), "first_season": int(first)}
    ys = sorted(hist)
    i = ys.index(season)
    prev = ys[i - 1] if i > 0 else None
    c["prev_season"] = prev
    c["prev"] = _r(hist[prev], nd) if prev is not None else None
    before = [hist[y] for y in ys[:i]][-5:]
    c["mean5"] = _r(float(np.mean(before)), nd) if len(before) == 5 else None
    if complete:
        n = _notable(hist, season, excluded, sd_first, sd_last)
        c["run"] = n["run"]
        c["notable_why"] = n["why"]
        c["notable"] = bool(n["why"])
    else:
        c["run"] = None
        c["notable_why"] = []
        c["notable"] = False
    c["notable_rule"] = "completed seasons only"
    c["sentence"] = league_sentence(c, in_season)
    return c


def build_league(series: Optional[dict], env: Optional[dict], live_env: Optional[dict],
                 season: int, in_season: bool = True) -> list:
    out = []
    seasons = (series or {}).get("seasons") or {}
    stats = (series or {}).get("stats") or {}
    for key, label, side, skey, unit, scale, nd, completed_only in SERIES_CARDS:
        if not any(s.get("key") == skey for s in stats.get(side) or []):
            continue                       # never ip_per_gs in place of sp_ip_per_gs
        hist, done = {}, {}
        for y, blk in seasons.items():
            v = _num((((blk or {}).get(side) or {}).get("all") or {}).get(skey))
            if v is None:
                continue
            hist[int(y)] = v * scale
            done[int(y)] = bool((blk or {}).get("complete"))
        if completed_only:
            hist = {y: v for y, v in hist.items() if done[y]}
        if not hist:
            continue
        shown = max(hist)
        c = _card(key, label, unit, nd, hist, shown, done.get(shown, False), min(hist),
                  SERIES_EXCLUDED, SERIES_SD_FIRST, SERIES_SD_LAST, in_season)
        c["series_ref"] = f"{SERIES_NAME}#{side}/{skey}"
        c["completed_only"] = bool(completed_only)
        if completed_only:
            c["footnote"] = FIVE_M_NOTE
        out.append(c)
    env_seasons = (env or {}).get("seasons") or {}
    for key, label, field, unit, nd in OWN_CARDS:
        hist, done = {}, {}
        for y, blk in env_seasons.items():
            v = _num((blk or {}).get(field))
            if v is not None:
                hist[int(y)], done[int(y)] = v, True
        lv = _num(((live_env or {}).get(str(season)) or {}).get(field))
        if lv is not None and int(season) not in hist:
            hist[int(season)], done[int(season)] = lv, False
        if not hist:
            continue
        shown = max(hist)
        last_done = max((y for y in hist if done[y]), default=OWN_SD_FIRST)
        c = _card(key, label, unit, nd, hist, shown, done[shown], min(hist),
                  OWN_EXCLUDED, OWN_SD_FIRST, last_done, in_season)
        c["values"] = {str(y): _r(v, nd) for y, v in sorted(hist.items())}
        c["completed"] = sorted(str(y) for y in hist if done[y])
        c["source"] = ("the pitch sidecar's runner events: (SB + CS) / (2 x games)"
                       if key == "sba_per_club_game"
                       else "the pitch sidecar, as labelled in MLB's feed")
        out.append(c)
    return out


def live_league_env(season: int, physics_dir: Optional[Path] = None) -> dict:
    """The live season's four League values from the sidecar, by the eval
    lab's own formula."""
    from tools import league_trends_calibrate as L
    try:
        return L.league_env(seasons=(int(season),), physics_dir=physics_dir)["seasons"]
    except (OSError, ValueError, KeyError):
        return {}


# --------------------------------------------------------------------------- #
# the payload
# --------------------------------------------------------------------------- #
def _family_entry(key: str, art: dict, tests: int, prior_tests: int, as_of: Optional[str],
                  listed: int) -> dict:
    fam = TD.FAMILIES[key]
    ch = art["families"][key]["chosen"][TD.BAR_POLICY]
    tail = float(ch["tail_per_test"])
    wins = sorted({f"last {v[1]} {'days' if v[0] == 'days' else GAMES_WORD[r][1]}"
                   for r, v in fam.window.items()}, reverse=True)
    e = {"key": key, "label": fam.label, "unit": fam.unit, "type": TYPE.get(key, "shape"),
         "roles": list(fam.roles), "window": " or ".join(wins), "bar": float(TD.bar_for(key)),
         "size_floor": _r(fam.size_floor, 4), "phi": TD.phi_for(key),
         "tail_per_test": tail, "tests_today": int(tests),
         "false_per_day": _r(tail * int(tests), 4),
         "pooled_flags": int(ch["flag_count"]), "real_share": _r(ch.get("real"), 4),
         "listed": int(listed)}
    if prior_tests:
        pf = ((art.get("prior_season") or {}).get("families") or {}).get(key) or {}
        ptail = float(((pf.get("pooled") or {}).get("tail_per_test")) or 0.0)
        e["prior"] = {"bar": float(TD.PRIOR_SEASON_BAR), "tests_today": int(prior_tests),
                      "tail_per_test": ptail, "false_per_day": _r(ptail * int(prior_tests), 4)}
    if fam.kind == "swing":
        e["pool"] = (art.get("pool") or {}).get("label") or fam.pool
        e["as_of"] = as_of
    return e


def _season_mode(frame_meta: dict, expected: int, today: str) -> str:
    games = int(frame_meta.get("games") or 0)
    ct = frame_meta.get("covers_through")
    old = bool(ct) and (date.fromisoformat(today) - date.fromisoformat(str(ct))).days >= 2
    return "final" if (expected and games >= FINAL_SHARE * expected and old) else "in_season"


def build(*, art: Optional[dict] = None, frame=None, prior=None, boards: Optional[dict] = None,
          game_dates=None, series: Optional[dict] = None, pal: Optional[dict] = None,
          live_env: Optional[dict] = None, swing_missing: Optional[dict] = None,
          data_dir: Optional[Path] = None, today: Optional[str] = None,
          log: Callable = print) -> dict:
    """The payload. Raises Refused (nothing is written)."""
    d = Path(data_dir or DATA_DIR)
    if art is None:
        art = _read_json(eval_path())
        if not art:
            raise Refused(f"no eval artifact at {eval_path()}; run "
                          "python tools/league_trends_calibrate.py")
    why = bars_mismatch(art)
    if why:
        raise Refused(why)
    if boards is None:
        boards = live_boards(d)
    season = boards.get("season")
    if season is None:
        raise Refused("no live board carries a season")
    season = int(season)
    swing_missing = dict(swing_missing or {})
    if frame is None:
        try:
            frame = TF.pitch_game_frame(season, log=log)
        except FileNotFoundError as e:
            raise Refused(str(e)) from e
        except ValueError as e:                       # club identity under the floor
            raise Refused(str(e)) from e
        except TF.SwingSeasonsMissing as e:
            swing_missing = {int(s): str(e.detail.get(s, "")) for s in e.seasons}
            log(f"  league trends: swing seasons missing ({e}); the swing families are left off")
            try:
                frame = TF.pitch_game_frame(season, with_swings=False,
                                            memo_dir=NOSWING_MEMO_DIR, log=log)
            except (FileNotFoundError, ValueError) as e2:
                raise Refused(str(e2)) from e2
    covers = frame.meta.get("covers_through")
    if game_dates is None:
        import mlbstats_games
        game_dates = mlbstats_games.season_game_dates(season)
    dates = set(str(x) for x in game_dates) | set(frame.games["date"].dropna().astype(str))
    last = boards_last_game_date(boards.get("as_of"), dates)
    why = stale_reason(covers, last)
    if why:
        raise Refused(why)
    as_of = str(covers)
    today = today or datetime.now(timezone.utc).date().isoformat()
    if series is None:
        series = _read_json(d / SERIES_NAME)
    gpt = ((((series or {}).get("seasons") or {}).get(str(season)) or {}).get("games_per_team")) or 162
    expected = int(15 * int(gpt))
    mode = _season_mode(frame.meta, expected, today)
    if pal is None:
        pal = _read_json(d / "pal.json")
    pal_sets = _pal_sets(pal)
    names = _names(boards)

    if prior is None:
        try:
            prior = TF.pitch_game_frame(season - 1, log=log)
        except (FileNotFoundError, ValueError, TF.SwingSeasonsMissing) as e:
            log(f"  league trends: no {season - 1} frame for prior-season mode ({e})")
            prior = None
    prior_season = season - 1 if prior is not None else None
    swing_ok = ((art.get("prior_season") or {}).get("swing_ok") or {})

    verdicts = ((art.get("live_check") or {}).get("families") or {})
    d_swing = (frame.meta.get("swing") or {}).get("as_of")
    families, cards, left_off = [], [], []
    for key in art.get("served") or []:
        fam = TD.FAMILIES[key]
        if verdicts.get(key) == "left off":
            left_off.append({"key": key, "label": fam.label,
                             "reason": "left off by the monthly live check until the next "
                                       "season's calibration"})
            continue
        D = as_of
        if fam.kind == "swing":
            if swing_missing:
                left_off.append({"key": key, "label": fam.label,
                                 "reason": "swing source seasons missing: "
                                           + " ".join(str(s) for s in sorted(swing_missing))})
                continue
            if not d_swing:
                left_off.append({"key": key, "label": fam.label,
                                 "reason": "no tracked swing in the live season yet"})
                continue
            lag = (date.fromisoformat(as_of) - date.fromisoformat(str(d_swing))).days
            if mode == "in_season" and lag > SWING_MAX_LAG_DAYS:
                left_off.append({"key": key, "label": fam.label,
                                 "reason": f"the swing source's last game date {d_swing} trails "
                                           f"{as_of} by {lag} days (more than {SWING_MAX_LAG_DAYS})"})
                continue
            D = min(as_of, str(d_swing))
        ok = bool(swing_ok.get(key)) if fam.kind == "swing" else True
        tests, ptests, hit = _flags(frame, prior, D, key, art, ok)
        any_prior = bool(len(hit)) and bool((hit["mode"] == "prior_season").any())
        first = (first_flagged(frame, prior if any_prior else None, D, key, art, ok,
                               hit["pid"].tolist()) if len(hit) else {})
        fam_cards = [player_card(frame, D, key, row, first[int(row["pid"])], names, pal_sets,
                                 prior_season, prior) for _, row in hit.iterrows()]
        cards.extend(fam_cards)
        families.append(_family_entry(key, art, len(tests), len(ptests),
                                      D if fam.kind == "swing" else None, len(fam_cards)))
    # strength first, then the newest first flagged, then the id
    cards.sort(key=lambda c: c["id"])
    cards.sort(key=lambda c: c["first_flagged"], reverse=True)
    cards.sort(key=lambda c: -c["strength"])
    events = rule_events(frame, as_of, names, pal_sets)

    rd_band = art.get("rd_band")
    if rd_band:
        teams = build_teams(frame, as_of, rd_band, cards, events)
        teams_note, teams_blocker = None, None
    else:
        teams = []
        teams_note = TEAMS_NOTE
        teams_blocker = art.get("rd_band_note") or "the eval artifact carries no rd_band"
    if live_env is None:
        live_env = live_league_env(season)
    league = build_league(series, art.get("league_env"), live_env, season,
                          in_season=(mode == "in_season"))

    fpd = _r(sum((f["false_per_day"] or 0.0) + ((f.get("prior") or {}).get("false_per_day") or 0.0)
                 for f in families), 3)
    real = _num(((art.get("totals") or {}).get(TD.BAR_POLICY) or {}).get("real"))
    one_in = int(round(1.0 / (1.0 - real))) if real is not None and real < 1 else None
    method = {"policy": TD.BAR_POLICY, "false_per_day": fpd, "one_in": one_in,
              "eval": f"data/{EVAL_NAME}",
              "fit_seasons": (art.get("shrink") or {}).get("seasons"),
              "eval_generated_at": art.get("generated_at"),
              "fold": FOLD.format(one_in=one_in, false_per_day=f"{fpd:.2f}")}
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": season, "mode": mode, "as_of": as_of, "covers_through": as_of,
        "boards_last_game": last, "max_lag_days": MAX_LAG_DAYS,
        "coverage": {"games": int(frame.meta.get("games") or len(frame.games)),
                     "expected": expected},
        "verdict": "descriptive",
        "flag": {"MLBSTATS_TRENDS_LIVE": MLBSTATS_TRENDS_LIVE},
        "method": method,
        "families": families, "left_off": left_off,
        "swing_missing": {str(k): v for k, v in sorted(swing_missing.items())},
        "players": cards, "events": events,
        "teams": teams, "teams_note": teams_note, "teams_blocker": teams_blocker,
        "league": league,
    }


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_bytes() == raw:
            return
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def encode(doc: dict) -> bytes:
    return (json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def export(*, write: bool = True, out: Optional[Path] = None, log: Callable = print,
           **kw) -> dict:
    """Build and write the payload. A refusal writes nothing and the last good
    file stands. Returns a summary dict (``refused`` is the reason or None)."""
    t0 = time.time()
    path = Path(out) if out is not None else out_dir() / OUT_NAME
    try:
        doc = build(log=log, **kw)
        raw = encode(doc)
        if len(raw) > BUDGET_RAW:
            raise Refused(f"the payload is {len(raw):,} bytes raw, over the {BUDGET_RAW:,} budget")
    except Refused as exc:
        log(f"  league trends: refused ({exc}); keeping the last good file")
        return {"out": str(path), "refused": str(exc), "written": False}
    if write:
        _write(path, raw)
    summary = {"out": str(path), "refused": None, "written": bool(write), "bytes": len(raw),
               "as_of": doc["as_of"], "mode": doc["mode"], "players": len(doc["players"]),
               "events": len(doc["events"]), "teams": len(doc["teams"]),
               "league": len(doc["league"]), "families": len(doc["families"]),
               "left_off": [f["key"] for f in doc["left_off"]],
               "swing_missing": sorted(doc["swing_missing"]),
               "false_per_day": doc["method"]["false_per_day"],
               "seconds": round(time.time() - t0, 1)}
    log(f"  league trends: {summary['players']} cards, {summary['events']} events, "
        f"{summary['teams']} clubs, {summary['league']} league cards, as of {summary['as_of']} "
        f"({summary['mode']}), {summary['bytes']:,} bytes, false per day "
        f"{summary['false_per_day']}, to {path}")
    return summary


def main(argv=None) -> int:                 # pragma: no cover - the CLI
    ap = argparse.ArgumentParser(description="League Trends payload.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    res = export(write=not a.dry_run, out=a.out)
    print(json.dumps(res, indent=1))
    return 2 if res.get("refused") else 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())
