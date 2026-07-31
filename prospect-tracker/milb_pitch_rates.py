# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MiLB pitch-result rates (SwStr% / CSW%) from the StatsAPI play-by-play feed.

MiLB has no Hawk-Eye below AAA, but pitch RESULT (what the scorer typed for each
pitch) needs no tracking hardware, so `/api/v1/game/{gamePk}/playByPlay` carries a
per-pitch description at every affiliated level. This module aggregates those
descriptions into per (pitcher, season, level) pitch counts, then into
level-and-season-relative rates built the SAME way `efv_dataset._season_rates`
builds `k_rel` (subtract the contemporaneous season+level median, shrink by
exposure/(exposure+K)), so the output is comparable to the shipped rate block and
leakage-safe by construction.

## Description vocabulary (ENUMERATED from the crawl, not assumed)

The mapping was written only after counting `details.description` over every
`playEvents[]` entry with `isPitch == true` in the crawled games. See
`_VOCAB_OBSERVED` below for the counts this build actually saw.

Counted as a SWINGING STRIKE (`_SWINGING`):
    "Swinging Strike", "Swinging Strike (Blocked)", "Foul Tip", "Missed Bunt",
    "Bunt Foul Tip"
  Foul Tip (and its bunt form) is a pitch the batter got a piece of and the
  catcher caught in flight: a strike by rule, an out on strike three, NOT a foul.
  Swinging Strike (Blocked) is a whiff the catcher did not glove. Missed Bunt is
  a swing and miss with a bunt attempt.
Counted as a CALLED STRIKE (`_CALLED`):
    "Called Strike"
  "Automatic Strike" (pitch-clock / ABS-era administrative strike) is deliberately
  EXCLUDED: no pitch is thrown, so it belongs in neither numerator nor denominator
  of a per-pitch rate. It is stripped from the denominator in `summarize`.
Everything else ("Ball", "Foul", "Foul Bunt", "In play, out(s)", "In play, no out",
"In play, run(s)", "Ball In Dirt", "Hit By Pitch", "Intent Ball", "Pitchout", ...)
counts toward the pitch DENOMINATOR only.

    SwStr% = swinging strikes / pitches
    CSW%   = (called strikes + swinging strikes) / pitches

## Log-completeness gate (the reason low-level coverage is NOT what it looks like)

A pitch log is only usable if the scorer logged EVERY pitch. Measured pitches-per-
plate-appearance from randomly drawn games, 4 games per (season, sportId), verified
twice on independent draws:

    sportId 11/12/13 (AAA/AA/A+): 3.4-4.1 in every season 2015-2025  -> COMPLETE
    sportId 14 (A):               1.97 in 2015; 3.14-3.95 in 2016+   -> complete 2016+
    sportId 16 (CPX/DSL):  2018 2.08 | 2019 1.98 | 2021 2.00 | 2022 1.96 |
                           2023 1.90 | 2024 2.73 | 2025 3.55        -> PARTIAL <= 2024

A complete log runs ~3.8 pitches per PA, so the complex-level logs are missing
roughly half their pitches through 2024. They are not merely THIN, they are BIASED:
the retained subset is enriched with plate-appearance-ENDING pitches, which shows up
as a measured SwStr% of 25.9-32.8% at sportId 16 in those seasons against 10.0-15.8%
at the same-season full-log levels. A rate built on that subset is a strikeout-rate
proxy wearing a pitch-rate label, so `_MIN_PPBF` drops any game whose own pitches/BF
falls below 3.0.

This is the finding that kills the headline motivation. "CSW% reaches the levels
Statcast cannot" is TRUE for 2025 forward and FALSE for every season the eFV pitcher
eval can currently score: the complex leagues Statcast cannot reach are exactly the
ones whose pitch log was not fully kept. Zero DSL or CPX rows survive the gate for
2018-2023, so the thin-sample / low-level hypothesis this module was built to test
cannot be tested at DSL/CPX at all until the 2025+ cohorts resolve (~2031).

## STATUS: DATA ASSET, NOT A MODEL INPUT

Tested as an eFV pitcher feature on 2026-07-25 and REJECTED as a measured null. The
candidate `csw_rel` moved pooled OOS Spearman by +0.0059 against a pre-registered
floor of 0.016 (docs/EFV_GATE_STANDARD.md), landed INSIDE its own permutation null
band (p95 +0.0090), and carried a paired-bootstrap CI95 straddling zero. Nothing here
is wired into `efv_dataset` or `efv_model`, and this artifact must not be read by the
scorer. The cause is not measurement quality but redundancy: csw_rel correlates 0.80
with the shipped `k_rel` (R^2 0.64 on the k_rel + peak_k_rel block), so it is largely
a restatement of a rate the model already prices.

## Cost / scope

`/schedule` reports 10.5k-13k affiliated games per season, so a full 2015-2023
ladder crawl is ~100k requests (>27h at 1 req/sec) and is NOT attempted here.
Scope is instead PLAYER-TARGETED: for each pitcher in the eFV pitcher matrix, pull
the game log for his primary pre-decision MiLB season at that season's level, then
fetch play-by-play for exactly those games. Every pitcher appearing in a fetched
game is aggregated (not just the target), which is what supplies the league norm
population for free.

Network manners: identifying UA, a hard 1 request/second token bucket for the whole
module, retry/backoff on 429/5xx, per-game disk cache (games are immutable once
final), fail-soft, resumable.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from feed_cache import atomic_write_json

log = logging.getLogger(__name__)

BASE = "https://statsapi.mlb.com/api/v1"
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = Path(__file__).parent / ".cache" / "milb_pbp"
OUT_PATH = DATA_DIR / "milb_pitch_rates.json"
# Crawl frontier (which games the targets played in). An intermediate build
# artifact, not a product one, so it lives beside the cache rather than in data/.
INDEX_PATH = Path(__file__).parent / ".cache" / "milb_pitch_game_index.json"

_UA = {"User-Agent": "eephus-prospect-tracker/1.0 (+https://eephus.io; arkndjl@gmail.com)"}

# Level -> the sportId(s) that level lives under. Short-season A (15) folded into
# "A" pre-2021, matching milb_history.SPORT_LEVEL. Complex (16) splits DSL vs CPX
# by league name, exactly as milb_history._level16 does.
LEVEL_SPORT = {"AAA": (11,), "AA": (12,), "A+": (13,), "A": (14, 15),
               "CPX": (16,), "DSL": (16,)}
SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A", 16: "CPX"}

_SWINGING = frozenset({
    "Swinging Strike", "Swinging Strike (Blocked)", "Foul Tip",
    "Bunt Foul Tip", "Missed Bunt",
})
_CALLED = frozenset({"Called Strike"})
# Administrative "pitches" with no pitch thrown -- removed from the DENOMINATOR so a
# pitch-clock violation cannot dilute a rate. (An "Automatic Ball" is the pitcher's
# violation, an "Automatic Strike" the batter's; neither is a delivery.)
_NON_PITCH = frozenset({"Automatic Ball", "Automatic Strike"})

# Minimum pitches-per-batter-faced for a game's log to count as COMPLETE. A fully
# logged game runs ~3.5-4.3; the partial complex-level logs run 1.67-2.03. 3.0 sits
# in the empty gap between those two populations.
_MIN_PPBF = 3.0

# Reliability shrink constant, in PITCHES. efv_dataset._K_REL_BF is 40 batters
# faced; at the measured ~3.85 pitches per PA that is ~154 pitches, so the pitch
# feature is shrunk on the same amount of real playing time as k_rel. Any other
# choice would make csw_rel and k_rel non-comparable at the fringe.
K_REL_PITCH = 154.0

# A pitcher needs this many PITCHES in a (season, level) to enter the league-norm
# median. milb_history.league_norms uses >=100 BF, which is ~385 pitches, but this
# crawl is player-TARGETED: a pitcher who is not himself a target only shows up in
# the games he happened to share with one, so a 385-pitch qualifier would empty
# most cells. 150 is the working compromise. The quantity being estimated is a
# MEDIAN of per-pitcher rates, and per-pitcher sampling noise at 150 pitches
# (sd ~ sqrt(.28*.72/150) = 0.037) is symmetric, so it widens the rate
# distribution without meaningfully moving its median.
_NORM_MIN_PITCHES = 150
_NORM_MIN_N = 30             # matching milb_history.league_norms

# Stamped into the artifact so no downstream reader can mistake this for a feed the
# model consumes. See the module docstring for the gate that produced it.
STATUS = {
    "role": "DATA ASSET - NOT A MODEL INPUT",
    "efv_gate": "REJECTED 2026-07-25 as a measured null under docs/EFV_GATE_STANDARD.md",
    "delta_pooled_rho": 0.0059,
    "floor_required": 0.016,
    "bootstrap_ci95": [-0.0179, 0.0271],
    "permutation_null_p95": 0.0090,
    "reason": "csw_rel is 0.80-correlated with the shipped k_rel (R^2 0.64 on the "
              "k_rel + peak_k_rel block); the incremental contribution is not "
              "resolvable at this pool size.",
    "coverage_limit": "No DSL/CPX rows survive the log-completeness gate before 2025, "
                      "so the low-level hypothesis is untestable on any cohort the "
                      "eval can currently score.",
    "do_not": "Do not wire into efv_dataset.py / efv_model.py without a fresh gate.",
}


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=4, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)))

_RATE_SEC = 1.0
_rate_lock = threading.Lock()
_last_fetch = [0.0]


def _throttled_get(url: str, timeout: int = 45):
    """One GET under a process-wide 1 request/second token bucket."""
    with _rate_lock:
        wait = _RATE_SEC - (time.time() - _last_fetch[0])
        if wait > 0:
            time.sleep(wait)
        _last_fetch[0] = time.time()
    resp = SESSION.get(url, headers=_UA, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# per-game pitch lines
# ---------------------------------------------------------------------------

_PBP_FIELDS = ("allPlays,playEvents,isPitch,details,description,"
               "matchup,pitcher,id,result,eventType")


def _parse_game(payload: dict, game_pk: int) -> dict:
    """Reduce a playByPlay payload to per-pitcher description histograms.

    Stores the FULL description histogram rather than pre-summed swstr/csw so the
    swinging-strike mapping can be revised without re-crawling."""
    plays = payload.get("allPlays") or []
    pitchers: dict[str, dict] = {}
    pitch_total = bf_total = 0
    for pl in plays:
        pid = ((pl.get("matchup") or {}).get("pitcher") or {}).get("id")
        if pid is None:
            continue
        key = str(int(pid))
        rec = pitchers.setdefault(key, {"bf": 0, "desc": {}})
        if (pl.get("result") or {}).get("eventType"):
            rec["bf"] += 1
            bf_total += 1
        for ev in (pl.get("playEvents") or []):
            if not ev.get("isPitch"):
                continue
            d = ((ev.get("details") or {}).get("description") or "?")
            rec["desc"][d] = rec["desc"].get(d, 0) + 1
            pitch_total += 1
    ppbf = (pitch_total / bf_total) if bf_total else 0.0
    return {"game_pk": int(game_pk), "bf": bf_total, "pitches": pitch_total,
            "ppbf": round(ppbf, 3), "pitchers": pitchers}


def game_pitch_lines(game_pk: int, *, fetch: bool = True) -> dict | None:
    """Per-pitcher pitch-description histogram for one game, disk-cached forever.

    Final MiLB games are immutable, so a cached parse is never re-fetched. Returns
    None when uncached and fetch=False, or when the fetch fails (fail-soft)."""
    game_pk = int(game_pk)
    path = CACHE_DIR / f"{game_pk}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if not fetch:
        return None
    try:
        payload = _throttled_get(f"{BASE}/game/{game_pk}/playByPlay?fields={_PBP_FIELDS}")
    except Exception as e:                                    # noqa: BLE001
        log.warning("milb_pitch_rates: playByPlay %s failed: %s", game_pk, e)
        return None
    rec = _parse_game(payload, game_pk)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, rec)
    return rec


GAMELOG_DIR = Path(__file__).parent / ".cache" / "milb_gamelog"


def player_game_pks(mlbam: int, season: int, sport_id: int, *,
                    fetch: bool = True) -> list[dict]:
    """[{game_pk, date}] for one pitcher's appearances in one (season, sportId).

    The StatsAPI gameLog endpoint rejects multi-sport ids (HTTP 400), so callers
    pass one sportId at a time. Disk-cached: a completed season's game log is
    immutable, and re-deriving the crawl frontier must not cost a second pass of
    ~900 requests."""
    path = GAMELOG_DIR / f"{int(mlbam)}_{int(season)}_{int(sport_id)}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if not fetch:
        return []
    url = (f"{BASE}/people/{int(mlbam)}/stats?stats=gameLog&group=pitching"
           f"&season={int(season)}&sportId={int(sport_id)}"
           f"&fields=stats,splits,game,gamePk,date")
    try:
        d = _throttled_get(url)
    except Exception as e:                                    # noqa: BLE001
        log.warning("milb_pitch_rates: gameLog %s/%s/%s failed: %s",
                    mlbam, season, sport_id, e)
        return []
    out, seen = [], set()
    for b in (d.get("stats") or []):
        for s in (b.get("splits") or []):
            g = s.get("game") or {}
            pk = g.get("gamePk")
            if pk and pk not in seen:
                seen.add(pk)
                out.append({"game_pk": int(pk), "date": s.get("date")})
    GAMELOG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, out)
    return out


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

def summarize(desc: dict) -> dict:
    """{pitches, swstr, called, csw} from a description histogram."""
    pitches = sum(int(v) for k, v in desc.items() if k not in _NON_PITCH)
    sw = sum(int(v) for k, v in desc.items() if k in _SWINGING)
    cs = sum(int(v) for k, v in desc.items() if k in _CALLED)
    return {"pitches": pitches, "swstr": sw, "called": cs, "csw": sw + cs}


def vocabulary(limit: int | None = None) -> dict:
    """{description: count} over every cached game -- the enumeration the mapping
    is justified by. Run this before trusting `_SWINGING`."""
    out: dict[str, int] = {}
    for i, p in enumerate(sorted(CACHE_DIR.glob("*.json"))):
        if limit is not None and i >= limit:
            break
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for pr in (rec.get("pitchers") or {}).values():
            for k, v in (pr.get("desc") or {}).items():
                out[k] = out.get(k, 0) + int(v)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def aggregate(game_index: dict[int, dict], *, min_ppbf: float = _MIN_PPBF) -> dict:
    """Roll cached per-game lines up to per (pitcher, season, level).

    `game_index`: {game_pk: {"season": int, "level": str}}. Games whose own log
    fails the completeness gate are DROPPED entirely (both from player lines and
    from the norm population) so a partial log can never masquerade as a rate."""
    out: dict[str, dict] = {}
    kept = dropped = missing = 0
    for pk, meta in game_index.items():
        rec = game_pitch_lines(pk, fetch=False)
        if rec is None:
            missing += 1
            continue
        if (rec.get("ppbf") or 0.0) < min_ppbf:
            dropped += 1
            continue
        kept += 1
        season, level = meta["season"], meta["level"]
        for pid, pr in (rec.get("pitchers") or {}).items():
            s = summarize(pr.get("desc") or {})
            if not s["pitches"]:
                continue
            key = f"{pid}|{season}|{level}"
            cur = out.setdefault(key, {"mlbam": int(pid), "season": int(season),
                                       "level": level, "games": 0, "bf": 0,
                                       "pitches": 0, "swstr": 0, "called": 0})
            cur["games"] += 1
            cur["bf"] += int(pr.get("bf") or 0)
            cur["pitches"] += s["pitches"]
            cur["swstr"] += s["swstr"]
            cur["called"] += s["called"]
    log.info("milb_pitch_rates.aggregate: %d games kept, %d dropped (partial log), "
             "%d uncached -> %d pitcher-season-levels",
             kept, dropped, missing, len(out))
    return {"lines": out, "games_kept": kept, "games_dropped_partial": dropped,
            "games_uncached": missing}


def compute_norms(lines: dict, *, min_pitches: int = _NORM_MIN_PITCHES,
                  min_n: int = _NORM_MIN_N) -> dict:
    """{"season|level": {csw, swstr, n}} -- the contemporaneous season+level MEDIAN
    of per-pitcher rates, over pitchers clearing the exposure qualifier.

    Same shape as milb_history.league_norms (median of qualified per-player rates,
    n>=30 or the cell is refused), so csw_rel is the same KIND of quantity k_rel is."""
    buckets: dict[str, dict[str, list]] = {}
    for rec in lines.values():
        p = rec.get("pitches") or 0
        if p < min_pitches:
            continue
        cell = f"{rec['season']}|{rec['level']}"
        b = buckets.setdefault(cell, {"csw": [], "swstr": [], "tot_csw": [],
                                      "tot_sw": [], "tot_p": []})
        b["csw"].append((rec["swstr"] + rec["called"]) / p)
        b["swstr"].append(rec["swstr"] / p)
        b["tot_csw"].append(rec["swstr"] + rec["called"])
        b["tot_sw"].append(rec["swstr"])
        b["tot_p"].append(p)
    out = {}
    for cell, b in buckets.items():
        if len(b["csw"]) < min_n:
            continue
        out[cell] = {"csw": round(statistics.median(b["csw"]), 5),
                     "swstr": round(statistics.median(b["swstr"]), 5),
                     "n": len(b["csw"]),
                     "pooled_csw": round(sum(b["tot_csw"]) / sum(b["tot_p"]), 5),
                     "pooled_swstr": round(sum(b["tot_sw"]) / sum(b["tot_p"]), 5)}
    return out


def _resolved_norm(season: int, level: str, norms: dict) -> dict | None:
    """Contemporaneous same-level norm, falling back to the PRIOR season's same-level
    norm. Mirrors efv_dataset._resolved_norms, and is leakage-safe for the same
    reason: it only ever looks backwards from the decision point. There is no static
    prior fallback here -- an un-normed cell returns None and the row simply has no
    pitch feature, rather than letting a RAW rate masquerade as a level edge."""
    return norms.get(f"{season}|{level}") or norms.get(f"{season - 1}|{level}")


def rel_rates(rec: dict, norms: dict, *, k: float = K_REL_PITCH) -> dict | None:
    """Level-and-season-relative, exposure-shrunk csw_rel / swstr_rel for one line.

    Identical algebra to efv_dataset._season_rates:
        w = pitches / (pitches + K); rel = w * (raw rate - contemporaneous median)
    Returns None when the cell has no qualified norm (never subtract 0 -- that is
    the bug that made un-normed rates read as raw edges)."""
    p = rec.get("pitches") or 0
    n = _resolved_norm(int(rec["season"]), rec["level"], norms)
    if not p or not n:
        return None
    w = p / (p + k)
    csw = (rec["swstr"] + rec["called"]) / p
    swstr = rec["swstr"] / p
    return {"csw_raw": round(csw, 5), "swstr_raw": round(swstr, 5),
            "csw_rel": round(w * (csw - n["csw"]), 6),
            "swstr_rel": round(w * (swstr - n["swstr"]), 6),
            "pitches": p, "bf": rec.get("bf") or 0, "games": rec.get("games") or 0,
            "shrink_w": round(w, 4)}


# ---------------------------------------------------------------------------
# targeted crawl driver
# ---------------------------------------------------------------------------

def _targets_from_matrix(matrix_path: Path) -> list[dict]:
    """[{mlbam, season, level}] -- one row per pitcher-matrix row that carries a
    resolved primary pre-decision MiLB season. That season+level is exactly the row
    _season_rates read for k_rel, so the pitch feature lines up with it."""
    rows = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    seen, out = set(), []
    for r in rows:
        m = r.get("milb") or {}
        mlbam, season, level = r.get("mlbam_id"), m.get("milb_season"), m.get("milb_level")
        if not (mlbam and season and level):
            continue
        key = (int(mlbam), int(season), level)
        if key in seen:
            continue
        seen.add(key)
        out.append({"mlbam": int(mlbam), "season": int(season), "level": level,
                    "player_key": r.get("player_key")})
    return out


CRAWL_SHUFFLE_SEED = 20260725


def resolve_targets(targets: list[dict], *, index_path: Path | None = None,
                    log_every: int = 50) -> dict:
    """Turn targets into {"games": {pk: {season, level, date}},
                          "players": {"mlbam|season|level": [pk, ...]}}.

    Game-log responses are disk-cached, so a re-resolve is free."""
    index_path = index_path or INDEX_PATH
    games: dict[str, dict] = {}
    players: dict[str, list] = {}
    for i, t in enumerate(targets):
        sig = f"{t['mlbam']}|{t['season']}|{t['level']}"
        pks = []
        for sport in LEVEL_SPORT.get(t["level"], ()):
            # sportId 16 carries BOTH complex leagues; the DSL/CPX split is a league
            # property, not a sport property (milb_history._level16), so a sport-16
            # game keeps the target's own level label rather than collapsing to CPX.
            lvl = t["level"] if sport == 16 else SPORT_LEVEL.get(sport, t["level"])
            for g in player_game_pks(t["mlbam"], t["season"], sport):
                pk = str(g["game_pk"])
                games.setdefault(pk, {"season": t["season"], "level": lvl,
                                      "date": g.get("date")})
                pks.append(int(g["game_pk"]))
        players[sig] = sorted(set(pks))
        if i % log_every == 0:
            log.info("milb_pitch_rates: resolved %d/%d targets, %d unique games",
                     i + 1, len(targets), len(games))
            atomic_write_json(index_path, {"games": games, "players": players})
    atomic_write_json(index_path, {"games": games, "players": players})
    return {"games": games, "players": players}


def crawl(targets: list[dict], *, index_path: Path | None = None,
          max_games: int | None = None) -> dict:
    """Resolve each target's game list, then fetch + cache every game's pitch log.

    Resumable in both phases (game logs and per-game pitch lines are each disk
    cached, so a killed run re-enters where it stopped). The FETCH ORDER is a
    SEEDED SHUFFLE, deliberately: a crawl that runs out of budget then leaves every
    pitcher with a RANDOM subset of his games rather than every pitcher before some
    cutoff with all of his and everyone after with none. A random subset is handled
    correctly by the exposure shrink (w = pitches/(pitches+K) simply falls), whereas
    a chronological or per-player cutoff would put a systematic hole in the pool.
    Returns {game_pk: {season, level}}."""
    index_path = index_path or INDEX_PATH
    idx = resolve_targets(targets, index_path=index_path)
    games = idx["games"]

    todo = [int(pk) for pk in games if not (CACHE_DIR / f"{int(pk)}.json").exists()]
    import random
    random.Random(CRAWL_SHUFFLE_SEED).shuffle(todo)
    log.info("milb_pitch_rates.crawl: %d games total, %d to fetch (~%.1f h at 1 req/s)",
             len(games), len(todo), len(todo) / 3600.0)
    fetched = 0
    for j, pk in enumerate(todo):
        if max_games is not None and fetched >= max_games:
            log.info("milb_pitch_rates.crawl: hit max_games=%d, stopping", max_games)
            break
        if game_pitch_lines(pk) is not None:
            fetched += 1
        if j % 250 == 0:
            log.info("milb_pitch_rates.crawl: fetched %d/%d games", j, len(todo))
    return games


def build(matrix_path: Path | None = None, *, max_games: int | None = None) -> dict:
    """Full pipeline: targets -> crawl -> aggregate -> norms -> data/milb_pitch_rates.json."""
    matrix_path = matrix_path or (DATA_DIR / "xfv_pitcher_matrix.json")
    targets = _targets_from_matrix(matrix_path)
    log.info("milb_pitch_rates.build: %d pitcher-season-level targets", len(targets))
    games = crawl(targets, max_games=max_games)
    game_index = {int(pk): {"season": int(v["season"]), "level": v["level"]}
                  for pk, v in games.items()}
    agg = aggregate(game_index)
    lines = agg["lines"]
    norms = compute_norms(lines)
    feats = {}
    for key, rec in lines.items():
        rr = rel_rates(rec, norms)
        if rr:
            feats[key] = rr
    payload = {
        "generated": time.strftime("%Y-%m-%d"),
        "status": STATUS,
        "source": "statsapi /api/v1/game/{gamePk}/playByPlay",
        "swinging_strike_descriptions": sorted(_SWINGING),
        "called_strike_descriptions": sorted(_CALLED),
        "min_pitches_per_bf": _MIN_PPBF,
        "shrink_k_pitches": K_REL_PITCH,
        "norm_min_pitches": _NORM_MIN_PITCHES,
        "games_kept": agg["games_kept"],
        "games_dropped_partial_log": agg["games_dropped_partial"],
        "games_uncached": agg["games_uncached"],
        "norms": norms,
        "lines": lines,
        "features": feats,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(OUT_PATH, payload)
    log.info("milb_pitch_rates.build: wrote %s (%d lines, %d normed features, %d norm cells)",
             OUT_PATH.name, len(lines), len(feats), len(norms))
    return payload


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--aggregate-only", action="store_true")
    a = ap.parse_args()
    if a.aggregate_only:
        idx_path = INDEX_PATH
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        gi = {int(pk): {"season": int(v["season"]), "level": v["level"]}
              for pk, v in (idx.get("games") or {}).items()}
        ag = aggregate(gi)
        nm = compute_norms(ag["lines"])
        ft = {k: rel_rates(v, nm) for k, v in ag["lines"].items()}
        ft = {k: v for k, v in ft.items() if v}
        atomic_write_json(OUT_PATH, {
            "generated": time.strftime("%Y-%m-%d"),
            "source": "statsapi /api/v1/game/{gamePk}/playByPlay",
            "swinging_strike_descriptions": sorted(_SWINGING),
            "called_strike_descriptions": sorted(_CALLED),
            "min_pitches_per_bf": _MIN_PPBF, "shrink_k_pitches": K_REL_PITCH,
            "norm_min_pitches": _NORM_MIN_PITCHES,
            "games_kept": ag["games_kept"],
            "games_dropped_partial_log": ag["games_dropped_partial"],
            "games_uncached": ag["games_uncached"],
            "norms": nm, "lines": ag["lines"], "features": ft})
        print(f"lines={len(ag['lines'])} feats={len(ft)} norms={len(nm)}")
    else:
        build(max_games=a.max_games)
