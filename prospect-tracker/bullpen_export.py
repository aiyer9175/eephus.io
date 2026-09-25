# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Bullpen Leaderboards sidecar (data/bullpen_leaderboards.json).

Assembles the REM+ reliever board + team Bullpen+ + depth charts from REACHABLE
sources (FanGraphs is 403-blocked here):

  SKILL CORE   MLB StatsAPI season pitching leaderboard (playerPool=all) - one
               combined season line per pitcher with the proper team, holds,
               inherited runners, and every FIP input (K/BB/HBP/HR/IP/BF).
               Traded players come back as a single total under their most
               recent club, so there is no same-city ambiguity or multi-stint
               fragmentation (the trap Baseball-Reference's city-name Tm has).
  SwStr%       optional enrichment from pybaseball.pitching_stats_bref (StatsAPI
               has no swinging-strike count); best-effort, null when unavailable.
  LEVERAGE     mlb_leverage.fetch_season_leverage - gmLI / WPA / WPA-LI / SD / MD
               self-computed from the StatsAPI winProbability feed, joined by
               MLBAM id.

These feed rem_plus.score_pool(), which filters to true relievers, anchors REM+
to the reliever pool (100 = average), and rolls up team bullpens.

Run: `python bullpen_export.py [season] [leverage_game_limit]`. Also wired into
run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing fetches at
import; any pull failure logs and returns 0 rather than aborting the caller.
`leverage_game_limit` caps the winProbability walk for a fast partial refresh
(the skill core stays full-season; only the Impact columns are partial, which
the coverage block discloses)."""
from __future__ import annotations

import bisect
import functools
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import feed_cache  # hardened, 429-retrying requests session
import rem_plus
from rem_plus import Reliever

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "bullpen_leaderboards.json"
HISTORY_PATH = DATA_DIR / "bullpen_history.json"
# Yearly reliever-history window: the seasons the /mlbstats/ history tabs offer
# (ex-2020 COVID short season). Cached winProbability makes the walk fast.
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]
EVAL_PATH = DATA_DIR / "rem_plus_eval.json"
# The market line on the REM+ scorecard. It reads the 2026-09-18 re-gate's
# REM+ baseline (one target, canonical identity), never the 271-row
# name-matched block in rem_plus_eval.json: that block's leverage-weighted
# rho is a lab variant no column serves, on a pair set the re-gate superseded.
MARKET_PATH = DATA_DIR / "riv_market_regate_eval.json"
LEVCON_PATH = DATA_DIR / "leverage_consistency_eval.json"
MULTIYR_PATH = DATA_DIR / "rem_plus_multiyear_eval.json"
# frozen trailing-window vintage for WAR/PA+ and WAR/IP+ (all three anchor pools
# live in one artifact, one block each); see join_war_rate_3yr
WAR_RATE_MULTIYR_PATH = DATA_DIR / "war_rate_plus_multiyear_eval.json"

STATSAPI = "https://statsapi.mlb.com/api/v1"


def _war_source_vintage(as_of: Optional[str] = None) -> dict:
    """The served eWAR build stamp, or a stated absence. Never raises: a board
    that cannot report its vintage must still render (audit F10-02). `as_of`
    is the payload's own as_of, so the block dates the drift it measured."""
    try:
        import war_source as _ws
        return _ws.ewar_vintage(as_of=as_of)
    except Exception as e:   # noqa: BLE001 - reporting must not take a board down
        return {"artifact_generated_at": None, "stale": None,
                "reason": f"war_source.ewar_vintage unavailable ({type(e).__name__})"}


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def ip_to_float(ip) -> float:
    """Convert MLB IP notation (X.1 = X+1/3, X.2 = X+2/3) to true decimal."""
    v = _num(ip)
    if v is None:
        return 0.0
    whole = int(v)
    outs = round((v - whole) * 10)
    if outs >= 3:  # guard against a true-decimal input sneaking in
        return v
    return whole + outs / 3.0


# --------------------------------------------------------------------------- #
# data pulls (network-gated: only run inside export())
# --------------------------------------------------------------------------- #
def _get_json(path: str, params: dict) -> dict:
    resp = feed_cache.SESSION.get(f"{STATSAPI}/{path}", params=params, timeout=45)
    resp.raise_for_status()
    return resp.json()


_TMAP_CACHE = Path(__file__).parent / ".cache" / "team_abbrev_map.json"


# --------------------------------------------------------------------------- #
# silent-empty plumbing. guard_nonempty_block is shared by the four /mlbstats/
# exporters; record_ingest / _ingest_red are the export layer's ingest-health
# client generally (ifa_export and fa_export file through them too) so the
# live-module resolution below exists ONCE rather than once per exporter.
# --------------------------------------------------------------------------- #
def _live_pipeline_module():
    """The RUNNING run_monthly module object, or None when no pipeline is up.

    THE DEFECT THIS EXISTS FOR (2026-08-05, found by review the same day the
    guards below shipped). `from run_monthly import _record_ingest` looks like
    it reaches the pipeline. Under the way the pipeline is actually launched -
    deploy/nightly-build.sh runs `python run_monthly.py` - the live module is
    sys.modules["__main__"] and the name "run_monthly" is UNCLAIMED, so that
    import statement builds a SECOND, SEPARATE module object with its own empty
    _INGEST_HEALTH list. write_ingest_health then drains the FIRST list. Every
    red filed that way went into a throwaway: MEASURED 0 of 1 filed rows in the
    drained payload before this fix, 1 of 1 after.

    Resolution order, and why each step is in it:
      1. sys.modules["run_monthly"] - the normal import case, and also the
         script case now that run_monthly claims its own name on startup.
      2. sys.modules["__main__"], but ONLY when that module carries the
         pipeline's own attributes. Any script can be __main__; the
         _record_ingest / write_ingest_health pair is the sentinel that says
         this particular __main__ is the pipeline and owns the ledger being
         drained.
      3. None, and the caller falls back to a fresh import. That path is for a
         standalone `python bullpen_export.py`, where the in-memory ledger has
         no drain to reach anyway but _record_ingest's ok=True side effect
         still stamps the DURABLE source_checks row, which is worth the import.
    """
    mod = sys.modules.get("run_monthly")
    if mod is not None and hasattr(mod, "_record_ingest"):
        return mod
    main = sys.modules.get("__main__")
    if (main is not None and hasattr(main, "_record_ingest")
            and hasattr(main, "write_ingest_health")):
        return main
    return None


def record_ingest(source: str, *, ok: bool, n_rows: int = 0, message: str = "",
                  import_fallback: bool = True) -> None:
    """File one outcome into the run's ingest-health ledger, never raising.

    Resolves the LIVE pipeline module first (see _live_pipeline_module) and
    only re-imports run_monthly when there is no pipeline in the process. Both
    verdicts go through here: the HEALTHY path matters as much as the red one,
    because a present ok=True row is the only thing that distinguishes "ran and
    found nothing" from "never ran" when the ledger is read after the fact.

    `import_fallback=False` says "log this only if a pipeline is already up".
    The HEARTBEAT callers pass it, because importing run_monthly costs the
    whole pipeline import graph (scrapers, storage, every exporter) and a
    standalone `python bullpen_export.py` or a unit test must not pay that just
    to note that a board built normally. A FAILURE still pays it: the fresh
    import stamps nothing on its own, but it is the only way an anomaly from a
    non-pipeline run gets recorded at all.

    Best-effort BY DESIGN, mirroring fantasy_export._record_schedule_anomaly:
    this is a reporting path and must never be the reason an export fails."""
    try:
        mod = _live_pipeline_module()
        if mod is not None:
            mod._record_ingest(source, ok=ok, n_rows=n_rows, message=message)
            return
        if not import_fallback:
            return
        from run_monthly import _record_ingest
        _record_ingest(source, ok=ok, n_rows=n_rows, message=message)
    except Exception:                      # noqa: BLE001 - reporting never breaks a board
        _log.debug("could not record ingest health for %s", source, exc_info=True)


def _ingest_red(source: str, message: str) -> None:
    """File a silent-empty into the ingest-health RED ledger.

    The ledger is what the deploy shell prints as `!!! INGEST RED`, so an empty
    fetch that would otherwise publish as a valid-looking board becomes visible
    on the same run instead of surfacing days later as a dark module. That
    claim is only true because record_ingest resolves the live module and
    because the source is named in run_monthly.SCHEDULED_EXPORTS - a row filed
    under an unwatched name is written to the payload but never reaches red[].
    """
    record_ingest(source, ok=False, message=message)


def _prev_payload(out_path: Path) -> dict:
    """The artifact this run is about to replace, or {} when there is none."""
    try:
        return json.loads(Path(out_path).read_text(encoding="utf-8"))
    except Exception:                      # noqa: BLE001 - missing/corrupt prior == no prior
        return {}


def guard_nonempty_block(fresh: list, out_path: Path, *, key: str, source: str,
                         label: str, log=print) -> tuple[list, dict]:
    """Never publish an EMPTY list over a populated one. Returns (list_to_serve, meta).

    THE OUTAGE THIS EXISTS FOR (2026-08-05). All four /mlbstats/ exporters refuse
    to write when the PLAYER rows come back empty, and none of them checked the
    TEAM ROLLUP. The rollup is keyed off each row's `team` string, so one failed
    _team_abbrev_map fetch blanks every team code, hem_plus/sem_plus/rem_plus
    score_pool skip the empty key, and the export publishes 0 team offenses over
    the 30 that were there. That is what made Offense+ read a flat 100 for every
    opponent on the streamer board and every DFS matchup. Nothing raised, because
    "no teams" and "no data yet" are the same value to every consumer downstream.

    Same posture as fantasy_export.refresh_live's EMPTY-FETCH GUARD: keep the
    PREVIOUS value, stamp it stale (carrying the vintage of what is being served,
    so the staleness is readable and not merely flagged), and file the failure
    into the ingest-health RED ledger. Losing a day of freshness on this block is
    recoverable on the next run; publishing 30 empty rollups is what a reader
    sees. When there is no populated prior to protect, the empty block is served
    as-is - it may be a genuine first run - but the zero is logged at ERROR and
    filed RED so it is never silent."""
    meta = {"key": key, "n": len(fresh), "stale": False}
    if fresh:
        # HEARTBEAT. A ledger that only ever hears from failures cannot tell
        # "this board built fine" from "this board's step never ran at all",
        # which is the exact ambiguity that let the TJStats gap run 8 days.
        # ok=True also stamps the durable source_checks row, so `last OK` on a
        # future red line is a real date instead of "never".
        record_ingest(source, ok=True, n_rows=len(fresh),
                      message=f"{label}: {len(fresh)} {key}",
                      import_fallback=False)
        return fresh, meta
    prev = _prev_payload(out_path)
    prev_block = prev.get(key) or []
    if not prev_block:
        _log.error("%s: '%s' came back EMPTY and there is no populated prior to "
                   "fall back on; the board will serve 0 %s", label, key, key)
        meta["reason"] = f"'{key}' empty and no populated prior artifact"
        _ingest_red(source, f"{label}: 0 {key} and no prior artifact to keep")
        if callable(log):
            log(f"  {label}: WARNING - 0 {key} and no prior to keep")
        return fresh, meta
    kept = prev.get("generated_at") or prev.get("as_of")
    meta.update({
        "stale": True, "n": len(prev_block), "n_fresh": 0, "kept_from": kept,
        "reason": (f"0 {key} this run; serving the previous run's "
                   f"{len(prev_block)} (vintage {kept})"),
    })
    _log.error("%s: '%s' came back EMPTY but the previous artifact had %d; "
               "keeping the older block (vintage %s) rather than publishing empty",
               label, key, len(prev_block), kept)
    if callable(log):
        log(f"  {label}: {key} came back EMPTY but the previous file had "
            f"{len(prev_block)} - keeping the older {key} (vintage {kept}) "
            f"rather than publishing an empty board")
    _ingest_red(source, (f"{label}: 0 {key} this run; kept the previous "
                         f"{len(prev_block)} (vintage {kept}). A zero rollup "
                         f"reads downstream as a flat league-average board."))
    return list(prev_block), meta


def _warn_unresolved_teams(n_unresolved: int, n_rows: int, tmap: dict, label: str) -> None:
    """Make a BLANK team code visible.

    `tmap.get(tid) or ""` is the exact line that manufactured the blank behind
    the 2026-08-05 outage: an empty abbreviation map turns every row's team into
    "", the rollup then finds no teams at all, and Offense+ / Rotation+ /
    Bullpen+ fall back to a flat 100 with nothing in the run reporting a problem.
    The healthy path is untouched (a genuinely unassigned row still serves ""),
    but the count is now logged, at ERROR when EVERY row failed, so "every team
    blank" can never again be silent."""
    if not n_unresolved:
        return
    lvl = _log.error if n_unresolved >= n_rows else _log.warning
    lvl("%s: %d of %d rows could not resolve a team abbreviation (map holds %d "
        "clubs); those rows serve a BLANK team and drop out of the team rollup",
        label, n_unresolved, n_rows, len(tmap))


# ---------------------------------------------------------------------------
# TEAM BASIS. Owner decision 2026-08-05, overriding my recommendation.
#
# StatsAPI season-stat rows carry the team the stats were EARNED with, so a
# deadline acquisition keeps his old club on every board: Tarik Skubal was
# traded to the Dodgers on 2026-08-02 and stayed in Detroit's rotation chart,
# while Detroit simultaneously showed the arms it had acquired. 56 rows were in
# that state (15 of 226 starters, 41 of 464 relievers).
#
# "current_roster" repoints `team` at the club MLB's transaction feed says
# employs the player TODAY, for the charts AND the aggregates.
#
# THE DISSENT, ON THE RECORD (I recommended a dual field instead, and the owner
# chose this): the aggregates are computed from these same rows, so a player
# acquired in August now has his ENTIRE season credited to his new club and
# subtracted from the club he actually pitched for. Rotation+/Bullpen+/Offense+
# therefore change basis, and those three feed betting_model AND the nightly
# leaderboard_vintages the 600-game validation clock is accruing - so vintages
# captured before this change are not on the same basis as vintages after it.
# Flip this constant back to "stats_earned" to revert in one line.
TEAM_BASIS = "current_roster"        # "current_roster" | "stats_earned"


def apply_current_team(rows: list[dict], *, label: str = "") -> int:
    """Repoint each row's `team` at the club MLB's feed says employs the player.

    Returns the number of rows moved. No-op under TEAM_BASIS="stats_earned".

    Two things this is careful about:
      - It compares CANONICALISED orgs on both sides. The leaderboards speak
        StatsAPI ("TB", "AZ", "CWS", "SF", "WSH", "KC") and the transaction feed
        speaks Baseball-Reference ("TBR", "ARI", "CHW", "SFG", "WSN", "KCR").
        A naive comparison reports 51 starter "moves" of which 36 are the same
        club spelled two ways.
      - It emits the new code in the ARTIFACT'S OWN code set, learned from the
        codes already present in these rows, because /mlbstats/ deliberately
        carries StatsAPI codes and rewriting TB into TBR would break its joins.
    """
    if TEAM_BASIS != "current_roster" or not rows:
        return 0
    try:
        from storage import authoritative_org_by_mlbam
        from trades import canonical_org
        auth = authoritative_org_by_mlbam()
    except Exception as e:                       # never break a board over this
        _log.warning("current-team remap unavailable (%s); serving stats-earned teams", e)
        return 0
    if not auth:
        # Same failure as the except branch above, arriving as an EMPTY map instead
        # of an exception, and it used to be the one that returned silently. Under
        # TEAM_BASIS="current_roster" that means every board quietly served
        # stats-earned teams while the payload claimed the current-roster basis, so
        # it gets the same log the exception path already had.
        _log.warning("current-team remap%s: the authoritative org map is EMPTY; "
                     "serving stats-earned teams under a current_roster basis",
                     f" [{label}]" if label else "")
        return 0
    # canonical -> the spelling THIS artifact already uses
    dialect: dict[str, str] = {}
    for r in rows:
        code = r.get("team")
        if code:
            dialect.setdefault(canonical_org(code) or code, code)
    moved = 0
    for r in rows:
        rec = auth.get(r.get("mlbam"))
        if not rec:
            continue
        want = canonical_org(rec[0])
        have = canonical_org(r.get("team")) if r.get("team") else None
        if not want or want == have:
            continue
        r["team"] = dialect.get(want, want)
        r["team_basis"] = "current_roster"
        moved += 1
    if moved:
        _log.info("current-team remap%s: %d row(s) moved to the club MLB's "
                  "transaction feed reports", f" [{label}]" if label else "", moved)
    return moved


def team_basis_meta(rows: list[dict], *, label: str = "",
                    scope: str = "current") -> dict:
    """The team-basis disclosure block each /mlbstats/ board publishes.

    TEAM_BASIS decides whether `team` means "the club the stats were earned with"
    or "the club that employs the player today", and the aggregates
    (Offense+/Rotation+/Bullpen+) are computed from these same rows - so the three
    boards, betting_model, and the nightly leaderboard_vintages all change basis
    with it. That is far too load-bearing to be readable only from a source
    constant, so the basis, the number of rows actually moved, and the number of
    rows serving a blank team ride in the payload where they can be audited.

    The moved count is recovered from the rows themselves: apply_current_team
    stamps `team_basis` on every row it repoints. n_team_unresolved is the same
    blank _warn_unresolved_teams logs, carried into the file: it is the count that
    goes to 100% of rows in the outage this pass exists for."""
    n_moved = sum(1 for r in rows if r.get("team_basis") == "current_roster")
    n_blank = sum(1 for r in rows if not r.get("team"))
    # SCOPE CHANGES WHAT THE SENTENCE HAS TO SAY, not what the basis is. On the
    # CURRENT season the strongest case the convention creates is an August
    # acquisition credited to his new club, which is a few weeks of misattributed
    # line. On a CLOSED season it is a whole career's worth: the same rule points
    # a 2021 season at a 2026 club, and Corbin Burnes' Cy Young year shows under
    # his current club rather than Milwaukee. Measured across the served history
    # artifacts, 2,088 of 6,885 rows (30.3%) are in that state. A reader given the
    # August-acquisition sentence on a history board has been told the mild half.
    history = (scope == "history")
    if TEAM_BASIS != "current_roster":
        note = "The club the stats were earned with, on the charts and in team totals."
    elif history:
        note = ("CLOSED seasons shown under the club MLB's transaction feed lists "
                "today, not the club he played for: a past season can show under a "
                "club he joined later. Charts and team totals both follow it, so "
                "filtering a club shows the players it holds now.")
    else:
        note = ("The club MLB's transaction feed lists today, on the charts and in "
                "team totals, so a traded player's whole season counts for his new "
                "club.")
    note += f" Rows with no club ({n_blank}) are left out of team totals."
    return {
        "basis": TEAM_BASIS,
        "scope": scope,
        "n_rows": len(rows),
        "n_moved_to_current_club": n_moved,
        "n_team_unresolved": n_blank,
        "label": label or None,
        "note": note,
    }


def basis_rows_for(served: list[dict], source_rows: list[dict],
                   key: str = "mlbam") -> list[dict]:
    """The SOURCE rows behind a served board, so the disclosure counts what the
    reader sees.

    apply_current_team stamps `team_basis` on the season rows it repoints, and
    the board rows are rebuilt through dataclasses that do not carry the stamp,
    so a board cannot report its own basis. Joining back on mlbam gives the
    served subset with the stamp intact; counting the whole season pool instead
    would report an n_rows the reader never sees."""
    ids = {r.get(key) for r in served if r.get(key) is not None}
    return [r for r in source_rows if r.get(key) in ids]


@functools.lru_cache(maxsize=1)
def _team_abbrev_map() -> dict:
    """Team id -> abbreviation, with a LAST-GOOD disk fallback.

    This used to return {} on any failure, which looked safe and was not. The
    map is joined onto every hitter and reliever row, so an empty map does not
    degrade gracefully - it blanks EVERY player's team, which makes the team
    rollup produce zero team offenses, which silently drops Offense+ back to the
    neutral 100 for every opponent on the streamer board and every DFS matchup.
    Measured 2026-08-05: one failed fetch turned 30 team offenses into 0 and
    nothing in the run reported an error, because "no teams" is indistinguishable
    from "no data yet" to every consumer downstream.
    The mapping is essentially static (30 clubs, changes on a rebrand), so the
    correct failure behavior is the one `_active_mlbam_ids` below already uses:
    never break the board. We persist the last good map and serve it when the
    fetch fails, and only return {} when we have never succeeded at all."""
    try:
        data = _get_json("teams", {"sportId": 1})
        m = {t["id"]: t.get("abbreviation") for t in data.get("teams", []) if t.get("id")}
        if m:
            try:
                _TMAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
                _TMAP_CACHE.write_text(json.dumps(m), encoding="utf-8")
            except OSError:
                pass                       # cache is an optimization, not a contract
            return m
        _log.warning("team abbreviation map came back EMPTY; falling back to cache")
    except Exception as e:
        _log.warning("team abbreviation map fetch failed (%s); falling back to cache", e)
    try:
        cached = json.loads(_TMAP_CACHE.read_text(encoding="utf-8"))
        # json object keys are strings; the callers join on int team ids
        m = {int(k): v for k, v in cached.items()}
        _log.warning("team abbreviation map served from cache (%d clubs) - team "
                     "offenses and Offense+ would otherwise have been blank", len(m))
        return m
    except Exception:
        _log.error("team abbreviation map unavailable AND uncached: every team "
                   "rollup this run will be empty and Offense+ will read 100")
        return {}


#: A roster walk that misses clubs is worse than one that fails outright: the
#: callers would drop those clubs' players as off-roster. 28 of 30 tolerates a
#: couple of transient fetch failures without letting a half-empty walk through.
MIN_CLUBS_FOR_ROSTER_FILTER = 28


@functools.lru_cache(maxsize=2)
def _active_mlbam_ids(season: int) -> Optional[frozenset]:
    """Set of MLBAM ids on a current ACTIVE roster (26-man), fetched ONCE per
    season and cached. Walks the 30 club active rosters from the StatsAPI teams
    roster endpoint and unions the person ids.

    Returns None on any failure so the caller does NOT filter (never break the
    board): an unreachable roster feed must leave the depth ladders intact rather
    than blank them. rosterType=active (not 40Man) so a demoted arm optioned to
    Triple-A (e.g. Blade Tidwell) is correctly dropped."""
    try:
        teams = _get_json("teams", {"sportId": 1}).get("teams", [])
    except Exception as e:
        _log.warning("active-roster team list fetch failed: %s", e)
        return None
    if not teams:
        return None
    ids: set = set()
    n_clubs_ok = 0
    for t in teams:
        tid = t.get("id")
        if not tid:
            continue
        try:
            data = _get_json(f"teams/{tid}/roster", {"rosterType": "active", "season": int(season)})
        except Exception as e:
            _log.warning("active-roster fetch team %s failed: %s", tid, e)
            continue
        got = 0
        for r in data.get("roster", []):
            pid = (r.get("person") or {}).get("id")
            if pid:
                ids.add(int(pid))
                got += 1
        if got:
            n_clubs_ok += 1
    # A PARTIAL WALK IS WORSE THAN NO WALK, and the old guard did not catch it.
    # It returned the set as soon as ONE club came back, so five failed fetches
    # produced a set missing five rosters and every caller then dropped those
    # clubs' players as "off roster". That is invisible: the board does not go
    # blank, it goes WRONG, on exactly the clubs whose feed failed.
    #
    # This matters more now than when only the bullpen ladders used it: the
    # hitter lineups and the rotation charts filter on the same set, so a partial
    # walk would empty three surfaces at once for the affected clubs. Measured on
    # a healthy walk: 30 of 30 clubs, 27 to 28 players each.
    if n_clubs_ok < MIN_CLUBS_FOR_ROSTER_FILTER:
        _log.error("active-roster walk covered only %d of %d clubs; NOT filtering "
                   "(a partial roster set silently drops the missing clubs' players)",
                   n_clubs_ok, len(teams))
        return None
    return frozenset(ids)


def _apply_roster_filter(teams: list, active_ids: Optional[frozenset]) -> int:
    """Drop depth-ladder entries whose MLBAM (depth row 'key' = str(mlbam)) is not
    on a current active roster. `active_ids` None => roster fetch failed, so do NOT
    filter. An unidentifiable key is KEPT (never over-filter). Returns the number
    of off-roster arms dropped."""
    if not active_ids:
        return 0
    dropped = 0
    for t in teams:
        depth = t.get("depth")
        if not depth:
            continue
        kept = []
        for d in depth:
            try:
                mid = int(d.get("key"))
            except (TypeError, ValueError):
                kept.append(d)   # can't identify the player -> keep
                continue
            if mid in active_ids:
                kept.append(d)
            else:
                dropped += 1
        t["depth"] = kept
    return dropped


def load_season_pitching(season: int, positions: tuple = ("P",)) -> list[dict]:
    """All MLB pitchers' season lines from the StatsAPI leaderboard (playerPool
    'all' so relievers are included). One combined row per player. [] on any
    failure (offline / API change).

    LIVE CALL. The hitter analog (hitter_export.load_season_hitting) reads the
    disk-cached fa_sources fetcher instead, so the hitter side runs offline and
    this one does not - the same asymmetry as pybaseball's cached bwar_bat vs
    uncached bwar_pitch. Callers that need an offline historical sweep should
    fetch splits themselves via fa_sources.fetch_statsapi_season_stats(season,
    "pitching") (disk-cached, 2000-2026 on hand) and hand them to
    rows_from_pitching_splits below, which is the same mapping this function
    applies. arb_metrics does exactly that.
    """
    try:
        data = _get_json("stats", {
            "stats": "season", "group": "pitching", "season": int(season),
            "sportId": 1, "gameType": "R", "playerPool": "all", "limit": 3000})
    except Exception as e:
        _log.warning("StatsAPI season pitching (%s) failed: %s", season, e)
        return []
    stats = data.get("stats") or []
    if not stats:
        return []
    return rows_from_pitching_splits(stats[0].get("splits", []), season, positions)


def rows_from_pitching_splits(splits: list[dict], season: int,
                              positions: tuple = ("P",)) -> list[dict]:
    """StatsAPI pitching `splits` records -> the flat row shape build_starters
    and build_relievers consume. Split out of load_season_pitching so an
    offline caller can supply cached splits and get a byte-identical mapping
    instead of re-implementing 25 field names that would drift.

    `positions` keeps rows whose primary position is in it (default: pitchers
    only, the boards' pool). A caller that wants two-way players (feed position
    TWP) asks for them explicitly; each such row carries `pos` so it can be
    kept out of any pool it must not anchor."""
    if not splits:
        return []
    tmap = _team_abbrev_map()
    out = []
    n_unresolved = 0
    for s in splits:
        st = s.get("stat") or {}
        pl = s.get("player") or {}
        tm = s.get("team") or {}
        pid = pl.get("id")
        if not pid:
            continue
        # drop position players pitching mop-up (their primary position is not P)
        pos = (s.get("position") or {}).get("abbreviation")
        if pos and pos not in positions:
            continue
        # `or ""` is kept (a genuinely unassigned row must still serve a blank),
        # but the blank is COUNTED now: see _warn_unresolved_teams.
        abbr = tmap.get(tm.get("id")) or ""
        if not abbr:
            n_unresolved += 1
        out.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""),
            "team": abbr,
            "G": st.get("gamesPitched"), "GS": st.get("gamesStarted"),
            "SV": st.get("saves"), "HLD": st.get("holds"),
            "IP": st.get("inningsPitched"), "ER": st.get("earnedRuns"),
            "R": st.get("runs"), "BB": st.get("baseOnBalls"),
            "SO": st.get("strikeOuts"), "HR": st.get("homeRuns"),
            "HBP": st.get("hitByPitch"), "BF": st.get("battersFaced"),
            "Pit": st.get("numberOfPitches"),
            "IR": st.get("inheritedRunners"), "IRS": st.get("inheritedRunnersScored"),
            # starter-side context (SEM+): durability + a batted-ball signal
            "CG": st.get("completeGames"), "GO": st.get("groundOuts"),
            "AO": st.get("airOuts"), "Strk": st.get("strikes"),
            **({"pos": pos} if pos and pos != "P" else {}),
        })
    _warn_unresolved_teams(n_unresolved, len(out), tmap, f"pitching {season}")
    apply_current_team(out, label=f"pitching {season}")
    return out


def load_bref_swstr(season: int) -> dict:
    """Optional SwStr% enrichment from Baseball-Reference (StatsAPI has no
    swinging-strike count). {mlbam: swstr_pct}; {} on any failure."""
    try:
        import pybaseball as pyb
        df = pyb.pitching_stats_bref(int(season))
    except Exception as e:
        _log.warning("bref SwStr enrichment unavailable: %s", e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            mid = r.get("mlbID")
            # bref StS is already the swinging-strike RATE (e.g. 0.19), not a count
            sts_rate = _num(r.get("StS"))
            if mid is None or sts_rate is None:
                continue
            try:
                out[int(float(mid))] = round(sts_rate, 4)
            except (TypeError, ValueError):
                continue
    except Exception as e:
        _log.warning("bref SwStr parse failed: %s", e)
    return out


def build_relievers(rows: list[dict], leverage: dict, swstr: Optional[dict] = None) -> list[Reliever]:
    """StatsAPI season rows -> Reliever records, joined to leverage (by MLBAM id)
    and the optional SwStr% enrichment."""
    swstr = swstr or {}
    out: list[Reliever] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        pit = _num(r.get("Pit")) or 0.0
        sw = swstr.get(mlbam)
        # None (not 0.0) when the bref SwStr enrichment is absent: swstr_pct downstream
        # (_safe_div(sts, pit)) then reports null "unknown", not a fake 0% swinging-strike
        # rate that read as a real (terrible) value for every player missing a bref row.
        sts = (sw * pit) if (sw is not None and pit) else None
        rel = Reliever(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            g=_num(r.get("G")) or 0.0, gs=_num(r.get("GS")) or 0.0,
            ip=ip_to_float(r.get("IP")), tbf=_num(r.get("BF")) or 0.0,
            so=_num(r.get("SO")) or 0.0, bb=_num(r.get("BB")) or 0.0,
            hbp=_num(r.get("HBP")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            er=_num(r.get("ER")) or 0.0, r=_num(r.get("R")) or 0.0,
            pit=pit, sts=sts,
            sv=_num(r.get("SV")) or 0.0, hld=_num(r.get("HLD")) or 0.0,
        )
        lev = leverage.get(int(mlbam))
        if lev:
            rel.gmli = lev.get("gmli")
            rel.wpa = lev.get("wpa")
            rel.wpa_li = lev.get("wpa_li")
            rel.sd = lev.get("sd")
            rel.md = lev.get("md")
            rel.entry_inning = lev.get("entry_inning")
        out.append(rel)
    return out


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        v = (j.get("verdict") or {})
        return v.get("status") or "provisional"
    except Exception:
        return "provisional"


def _market_line() -> dict:
    """REM+ against next-winter reliever AAV, read off the re-gate artifact.

    This used to print rem_plus_eval.market_check_aav.rho_leverage_weighted_vs_aav
    (0.5157) under REM+'s name: the rho of a damping-0.5 leverage-weighted lab
    variant, on 271 signings joined by normalized name. REM+ itself read 0.5084
    on that set and reads 0.5665 on the re-gate's 232 matched signings
    (B1_primary.v1.rho_baseline). This copies that stored number; it computes
    nothing, so the next market read stays on its 2027-03-01 clock. A missing
    or unreadable artifact returns {} and the scorecard prints no market line."""
    try:
        j = json.loads(MARKET_PATH.read_text(encoding="utf-8"))
        b1 = j["B1_primary"]
        rho = b1["v1"]["rho_baseline"]
        n = b1["n_matched_signings"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if rho is None or not n:
        return {}
    return {"rho": rho, "n": n, "as_of": j.get("generated_at")}


def _backtest() -> dict:
    """Compact accountability card from data/rem_plus_eval.json - the forward
    chained out-of-sample backtest that earned REM+ its validated verdict. Shown
    to users on /mlbstats/ so a validated model advertises its rigor."""
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fs = j.get("forward_spearman_vs_RA9_next") or {}
    gap = (j.get("gap_ci_vs_RA9_next") or {}).get("vs_era") or {}
    v = j.get("verdict") or {}
    mk = _market_line()
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_rem_plus": fs.get("rem_plus"),
        "rho_fip": fs.get("raw_fip"),
        "rho_era": fs.get("era"),
        "gap_vs_era_lo95": gap.get("lo95"),
        "market_rho": mk.get("rho"),
        "market_n": mk.get("n"),
        "market_as_of": mk.get("as_of"),
        "disclaimer": ("REM+ predicts next-year run prevention out of sample. Leverage (gmLI, "
                       "WPA, SD-MD) sits in the Impact columns: the manager assigns it, so it "
                       "is not skill."),
    }


def _join_leverage_consistency(relievers: list[dict]) -> int:
    """Stamp gmli_3yr / pool percentile / stability tag onto reliever rows
    from the committed leverage-consistency artifact
    (tools/leverage_consistency_eval.py, gate-validated 2026-07: pooled
    Y->Y+1 rho 0.4683 vs the 0.30 bar). Deployment context only - never an
    input to REM+. Missing artifact or unmatched player -> fields absent and
    the column renders blank. Returns the number of rows stamped."""
    try:
        pv = json.loads(LEVCON_PATH.read_text(encoding="utf-8"))["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return 0
    n = 0
    for r in relievers:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r["gmli_3yr"] = p.get("gmli_3yr")
        r["gmli_3yr_pct"] = p.get("pct")
        r["gmli_3yr_tag"] = p.get("tag")
        if r["gmli_3yr"] is not None:   # count only rows that will render
            n += 1
    return n


def _join_rem_plus_3yr(relievers: list[dict]) -> dict:
    """Stamp rem_plus_3yr / percentile / tag onto reliever rows from the committed
    multi-year artifact (tools/rem_plus_lab.py, X-R2: 3-year IP-weighted REM+, a
    more stable talent read than one season). Companion SKILL column - a longer
    window of the same REM+ scale, not a new metric. Missing artifact or unmatched
    player -> fields absent and the column renders blank.

    VINTAGE, NOT PIPELINE OUTPUT. These values are read VERBATIM from a FROZEN
    lab artifact; nothing here recomputes them, so a board row can show a
    same-day 1-year REM+ beside a 3-year REM+ that was frozen weeks earlier, and
    any arm who entered the pool after the lab last ran is simply blank. That
    divergence is real and must not be silent, so this returns the artifact's
    vintage block (generated_at / season / window / pool size) for the payload
    to carry and the frontend to disclose. Computing the window in-pipeline
    would need three seasons of StatsAPI pulls plus the lab's IP-weighting and
    pct/tag banding conventions - a new pipeline stage with its own eval, not a
    correctness fix - so this labels the divergence instead of unifying it."""
    meta = {"source": MULTIYR_PATH.name, "n_stamped": 0, "available": False}
    try:
        art = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
    n = 0
    for r in relievers:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r["rem_plus_3yr"] = p.get("rem_plus_3yr")
        r["rem_plus_3yr_pct"] = p.get("pct")
        r["rem_plus_3yr_tag"] = p.get("tag")
        if r["rem_plus_3yr"] is not None:
            n += 1
    meta.update({
        "available": True,
        "n_stamped": n,
        "generated_at": art.get("generated_at"),
        "season": pv.get("season"),
        "window": pv.get("window"),
        "n_in_artifact": len(players),
        "note": (f"3-year REM+ is FROZEN lab output read verbatim from "
                 f"{MULTIYR_PATH.name}, as of generated_at, not this board's "
                 f"as_of. Arms who joined the pool since have no value."),
    })
    return meta


_XREM_MIN_PA = 80.0   # min Savant batters-faced for a stable xwOBA-allowed read


def _join_xrem_plus(relievers: list[dict], season: int) -> int:
    """Stamp xREM+ (deserved run prevention on Savant expected wOBA-allowed) + Luck
    onto tracked relievers.

    HONEST FRAMING (loss ledger): Statcast xwOBA-allowed was tested against FIP for
    REM+ and did NOT win, so REM+ stays FIP-based. xREM+ is a COMPANION deserved-
    suppression read plus a luck residual, NOT a more predictive replacement. It
    INVERTS the hitter xHEM+ ratio (lower allowed xwOBA = higher +, mirroring
    rem_plus = 100 * poolFIP / playerFIP) and anchors the pool over the RELIEVER
    board (so 100 = the average reliever, matching REM+'s reliever anchor). Luck =
    actual wOBA-allowed minus expected (positive = allowed more than deserved =
    unlucky, room to improve). MLB-only + min-BBE gated; missing -> fields absent
    (column blank). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "pitcher")
    except Exception:   # noqa: BLE001 - best-effort, network/parse anything
        return 0
    board = {int(r["mlbam"]) for r in relievers if r.get("mlbam") is not None}
    xw: dict[int, tuple[float, float]] = {}
    luck_by: dict[int, float] = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if mid not in board or pa < _XREM_MIN_PA or ew <= 0:
            continue
        xw[mid] = (ew, pa)
        try:
            luck_by[mid] = round(float(r["woba"]) - ew, 3)
        except (TypeError, ValueError, KeyError):
            pass
    if not xw:
        return 0
    dtot = sum(pa for _, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    if not pool:
        return 0
    n = 0
    for r in relievers:
        ent = xw.get(int(r["mlbam"])) if r.get("mlbam") is not None else None
        if not ent:
            continue
        r["xrem_plus"] = int(round(100.0 * pool / ent[0]))   # INVERTED: lower allowed = higher
        r["xwoba_against"] = round(ent[0], 3)
        mid = int(r["mlbam"])
        if mid in luck_by:
            r["luck"] = luck_by[mid]
        n += 1
    return n


# --------------------------------------------------------------------------- #
# WAR/PA+ and WAR/IP+ (new Arkmetrics, 2026-07-29)
#
# Convention 3 of docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md: 100 + 10z,
# ten points per anchor-pool standard deviation. A ratio-to-mean index (the HEM+
# / REM+ / SEM+ convention) is UNDEFINED on this rate: league mean WAR/PA is
# about +0.0025 and WAR goes negative, so 100 * player / pool would flip sign and
# blow up. There is therefore no HEM_SPREAD_GAIN analog here and none should be
# added: the index is a SINGLE LEG z-scored against its own anchor pool, so its
# pool spread is already exactly 10 points per sigma and there is nothing left to
# re-standardize. (Contrast fwdHEM+ in hitter_export, a 0.7/0.3 blend of two z
# legs, whose pool sd is BELOW 1 and which does need the extra step.)
#
# This module owns the shared machinery because it is the base of the /mlbstats/
# exporter chain: starter_export and hitter_export already import from here.
# The three anchored surfaces are wired in three places, deliberately:
#   hitter_export   war_pa_plus, anchored on the hitter pool
#   starter_export  war_ip_plus, anchored on the QUALIFIED-STARTER pool
#   bullpen_export  war_ip_plus, anchored on the RELIEVER pool
# Starter-anchored and reliever-anchored values must never share one column
# (ARKMETRIC_SCALE_CONVENTIONS.md:77), exactly as SEM+ and REM+ coexist.
#
# Lab + pre-registration: tools/war_rate_plus_lab.py. Ledger:
# data/war_rate_plus_eval.json.
# --------------------------------------------------------------------------- #
WAR_RATE_PER_SIGMA = 10.0          # convention 3: ten points is one pool sigma
# Two-tier volume floors (house pattern). The pool floor decides who sets mu/sd;
# the display gate decides who gets a value. NO shrink is applied (pre-registered
# in the lab): a WAR rate has no component rates to shrink, shrinkage is not
# monotone across players so it cannot ride a rank-preserved defence, and a
# descriptive index must describe what was banked. The lab measures the shrunk
# arm and reports it; if it is ever shipped, mu/sd MUST come from the shrunk pool
# (gated defect C3, the aStuff+ 7.16-points-per-sigma class).
WAR_RATE_POOL_MIN_PA = 50.0
WAR_RATE_DISPLAY_MIN_PA = 100.0
WAR_RATE_POOL_MIN_IP = 20.0
WAR_RATE_DISPLAY_MIN_SP_IP = 40.0
WAR_RATE_DISPLAY_MIN_RP_IP = 30.0
# A silent WAR fetch failure must never be served as a board of zeros, so the
# join refuses when it cannot see a WAR value for at least this share of the
# pool-eligible rows (the fa_projection.py:191-201 degenerate-fetch pattern).
WAR_RATE_MIN_COVERAGE = 0.50


@functools.lru_cache(maxsize=1)
def _side_war_by_season() -> dict:
    """{mlbam: {season: {"bat": WAR, "pit": WAR}}} with the two sides kept on
    SEPARATE keys, via war_source.side_war_by_season on the facade DEFAULT
    provider (eWAR v2 from the 2026-09 epoch: the pitching side is FIP re-priced
    within role, the batting side equals bWAR until the SDR defense drop; the
    explicit 'bwar' provider is the input frame, delegating to
    mlb_player_export._war_daily).

    The side split is the whole point. fa_projection._war_age_maps SUMS the two
    sides onto one number, which would divide a two-way player's PITCHING WAR by
    his plate appearances. Reading the sides apart means a two-way player
    legitimately carries a batting WAR/PA+ on the hitter board and a pitching
    WAR/IP+ on a pitcher board, two different indexes over two different
    denominators, so no two-way discount factor is needed or wanted here
    (proj_export.TWO_WAY_PIT_PTH_FACTOR exists for a display path that shares one
    denominator; this one does not).

    Cached for the process: the three exporters each ask for it once."""
    import war_source
    return war_source.side_war_by_season()


def score_war_rate(rows: list[dict], season: int, *, side: str, denom_key: str,
                   pool_min: float, display_min: float, out_key: str,
                   anchor: str) -> dict:
    """Stamp `out_key` (100 + 10z of side WAR per denominator) onto `rows`.

    `rows` are already-scored board dicts; `denom_key` is the field holding the
    denominator ('pa' or 'ip'); `side` is 'bat' or 'pit'. Rows at or above
    `pool_min` with a WAR value set mu/sd; rows at or above `display_min` get a
    value. A row with no WAR row of its own gets NO field (not a zero), so the
    column renders blank rather than reading as a real replacement-level season.

    The counting stat `war` (the side's eWAR, 1dp) is NOT behind the display
    gate: every row with a WAR value and a positive denominator carries it, so a
    25-inning arm's eWAR prints even though his WAR/IP+ is blank (a count needs
    no volume floor; the rate does; the reliever gate is 30 IP and `d < 30.0`,
    so 30.0 itself publishes the index). The index fields (`out_key`, `_raw`,
    `_adj`, `_pct`) stay gated and `n_stamped` still counts index rows; `n_war`
    counts `war` rows. A stamped value of exactly zero serves as 0.0, never
    -0.0. A refused pool stamps neither: the refusal is the degenerate-fetch
    detector, and a board of a few surviving WAR values is the failure it
    exists to stop.

    Returns a meta block for the payload: the anchor description, the two floors,
    and the pool rate mean and sd that DEFINE the scale, so a reader of the served
    file can check the "ten points is one pool sigma" claim arithmetically instead
    of taking it on trust. Best-effort: any failure logs and returns an
    unavailable meta without touching a row."""
    meta = {"available": False, "n_stamped": 0, "n_war": 0, "anchor": anchor,
            "per_sigma": WAR_RATE_PER_SIGMA, "pool_min": pool_min,
            "display_min": display_min}
    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("%s unavailable (WAR fetch failed: %s)", out_key, e)
        meta["refused"] = f"WAR fetch failed: {e}"
        return meta

    def _war(r):
        mid = r.get("mlbam")
        if mid is None:
            return None
        return ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)

    elig = [r for r in rows if (_num(r.get(denom_key)) or 0.0) >= pool_min]
    pool = [(r, _war(r)) for r in elig]
    covered = [(r, w) for r, w in pool if w is not None]
    if not elig or len(covered) < WAR_RATE_MIN_COVERAGE * len(elig):
        # Degenerate fetch: pybaseball came back empty or stale, so almost nobody
        # has a WAR row. Refuse rather than anchor a board on a handful of rows.
        _log.warning("%s REFUSED: WAR covers %d of %d pool-eligible rows for %s",
                     out_key, len(covered), len(elig), season)
        meta["refused"] = (f"WAR covered {len(covered)} of {len(elig)} "
                           f"pool-eligible rows (floor {WAR_RATE_MIN_COVERAGE:.0%})")
        meta["pool_n"] = len(covered)
        return meta

    rates = [w / (_num(r.get(denom_key)) or 1.0) for r, w in covered]
    n = len(rates)
    mu = sum(rates) / n
    sd = (sum((x - mu) ** 2 for x in rates) / (n - 1)) ** 0.5 if n > 1 else 0.0
    if not sd:
        meta["refused"] = "degenerate pool spread"
        return meta

    # Sample-size companion (arm S), OWNER CALL CLOSED 2026-07-30:
    # docs/efv-2026-07-30/WAR_RATE_SHRINK_OWNER_CALL.md. The pre-registered rule
    # fired on hit and RP and the ship stayed unshrunk with the call left open;
    # the owner closed it as "ship it, but as a SEPARATE column". So the raw
    # index above is untouched - it still reproduces war/denom against
    # pool_mean_rate on the row, which is the property the override protected -
    # and the regressed variant lands beside it under its own name. Renaming is
    # not cosmetic: an adjusted value no longer reproduces the row's own rate, so
    # serving it under the raw column's name would silently change what a
    # published number means (ARKMETRIC_SCALE_CONVENTIONS.md).
    #
    # K is the pool MEDIAN denominator and mu/sd come from the SHRUNK pool, never
    # the unshrunk one. That second clause is the whole defect-C3 guard: aStuff+
    # shipped 7.16 points per sigma while advertising 10 precisely by z-scoring a
    # shrunk numerator against unshrunk moments (GATED_CANDIDATES.md C3).
    dens = sorted((_num(r.get(denom_key)) or 0.0) for r, _w in covered)
    K = dens[len(dens) // 2] if dens else 0.0
    tot_d = sum(dens)
    pool_rate = (sum(w for _r, w in covered) / tot_d) if tot_d else mu
    adj_rates = [((w + pool_rate * K) / ((_num(r.get(denom_key)) or 1.0) + K))
                 for r, w in covered]
    mu_s = sum(adj_rates) / n
    sd_s = (sum((x - mu_s) ** 2 for x in adj_rates) / (n - 1)) ** 0.5 if n > 1 else 0.0

    stamped = n_war = 0
    for r in rows:
        d = _num(r.get(denom_key)) or 0.0
        w = _war(r)
        if w is None or d <= 0:
            continue                          # absent, never zero
        v = round(w, 1)                       # every covered row: a count needs no floor
        r["war"] = 0.0 if v == 0 else v       # the house -0 rule, in the JSON too
        n_war += 1
        if d < display_min:
            continue                          # the INDEX stays gated
        raw = 100.0 + WAR_RATE_PER_SIGMA * ((w / d) - mu) / sd
        r[out_key] = int(round(raw))          # "+" stats round to nearest
        # pre-display core at the rem_plus_raw / hem_plus_raw precision. The lab
        # never reads this field (it recomputes from the WAR frame), so the harness-v2
        # unrounded-predictor rule is satisfied upstream, not here.
        r[f"{out_key}_raw"] = round(raw, 1)
        if sd_s:
            adj = 100.0 + WAR_RATE_PER_SIGMA * (
                ((w + pool_rate * K) / (d + K)) - mu_s) / sd_s
            r[f"{out_key}_adj"] = int(round(adj))
            r[f"{out_key}_adj_raw"] = round(adj, 1)
        stamped += 1

    # 1yr percentile chip. The 3yr columns already carry one (`*_3yr_pct`) and the
    # 1yr did not, which is why a top-of-board rate read as an unremarkable number:
    # on a 100+10z scale a reader has to do z-arithmetic to learn that 113 is rare.
    # Midrank over the SERVED rows, matching war_rate_plus_lab._pct_map exactly so
    # the two chips mean the same thing on the same row.
    served = sorted(r[out_key] for r in rows if r.get(out_key) is not None)
    if served:
        m = len(served)
        for r in rows:
            v = r.get(out_key)
            if v is None:
                continue
            lo = bisect.bisect_left(served, v)
            hi = bisect.bisect_right(served, v)
            r[f"{out_key}_pct"] = int(round(100.0 * ((lo + hi) / 2.0) / m))
    meta.update({
        "available": True, "n_stamped": stamped, "n_war": n_war, "pool_n": n,
        "pool_mean_rate": round(mu, 6), "pool_sd_rate": round(sd, 6),
        "shrink_K": round(K, 1), "pool_rate": round(pool_rate, 6),
        "adj_mean_rate": round(mu_s, 6), "adj_sd_rate": round(sd_s, 6),
        "note": (f"100 + 10z of eWAR per {denom_key.upper()} over {anchor}: 10 "
                 f"points = 1 pool SD, not the HEM+/REM+/SEM+ ratio scale. eWAR: "
                 f"Baseball-Reference run frame, pitching re-priced on FIP, fielding "
                 f"unchanged pending SDR; position players match bWAR except in "
                 f"seasons they also pitched. No shrink, no clamp; blank under "
                 f"{display_min:g} {denom_key.upper()}."),
        "adj_note": (f"{out_key}_adj shrinks the rate toward the pool rate by "
                     f"sample size (K = pool median {denom_key.upper()} = {K:g}) "
                     f"and re-standardises on the SHRUNK pool. A readability aid "
                     f"for thin samples, not a forward claim: ship gate G2 failed "
                     f"on every pool, and a post-hoc volume control puts most of "
                     f"the shrink gain down to volume. Does NOT reproduce "
                     f"war/{denom_key} on the row."),
    })
    return meta


def stamp_side_war(rows: list[dict], season: int, *, side: str,
                   denom_key: str) -> int:
    """Stamp the counting stat `war` (the side's eWAR, 1dp) on rows that sit
    OUTSIDE a scored pool, such as the two-way card-only starter rows
    (starter_export.score_two_way_card_only), by the same rule as the `war`
    stamp in score_war_rate: a row with no WAR cell for `side` or no positive
    denominator gets no field (absent, never zero). No index is written here.

    The caller stamps only when its board's own score_war_rate pool was not
    refused, so a degenerate fetch still stamps nothing anywhere. A stamped
    value of exactly zero serves as 0.0, never -0.0. Returns the number of rows
    stamped; never raises, an unreadable row included (a payload build must not
    abort over one malformed id)."""
    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("war stamp unavailable (WAR fetch failed: %s)", e)
        return 0
    n = 0
    for r in rows:
        mid = r.get("mlbam")
        if mid is None or (_num(r.get(denom_key)) or 0.0) <= 0:
            continue
        try:
            w = ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)
        except (TypeError, ValueError):   # a non-numeric id is one blank row
            continue
        if w is None:
            continue
        v = round(w, 1)
        r["war"] = 0.0 if v == 0 else v
        n += 1
    return n


#: What a refused season costs the reader, stated in the served payload because
#: the page has nowhere to put it: an eWAR column with no value anywhere in the
#: season is dropped from the history board, so a refusal reads as a column that
#: was never there unless the file says otherwise.
HISTORY_JOIN_REFUSAL_NOTE = ("this season serves no eWAR column at all; an "
                             "all-blank column is dropped from the board, so "
                             "the refusal is stated here and nowhere else")


def stamp_history_war(rows: list[dict], season: int, *, side: str,
                      label: str = "history", log=None) -> dict:
    """The counting stat `war` on a PAST-SEASON board row (E6, owner decision
    O5), joined by (mlbam, season) from the SAME side map the live boards read
    (_side_war_by_season, lru cached for the process, so the four history
    exports share one WAR read).

    THE JOIN IS THE ID AND THE SEASON, nothing else. A history row is already a
    qualified season line and nothing here divides by a denominator, so there is
    no volume gate to apply: the WAR-RATE columns gate because they divide, and
    they are dropped from these boards for a different reason entirely (they are
    standardised on the LIVE pool, which is what makes them unreadable on a 2021
    row). A season count carries no such pool, so it travels. A row the eWAR
    artifact does not cover gets NO field, which is what lets the page drop an
    uncovered column instead of printing one of blanks.

    NO DENOMINATOR GATE, and that REVERSES implementer constraint (b) of the
    spec ("stamp war only where the denominator is positive") on these four
    boards, deliberately and once for all four. The constraint guards the
    WAR-RATE indexes, which DIVIDE by the denominator; no history board carries
    one, and E3 and E4 already stamp the leverage and defense boards with no
    such gate. A history row is a qualified season line, so gating its count on
    innings or plate appearances would blank a value for a reason that does not
    exist on this board.

    THE SIDE IS THE BOARD'S SIDE, exactly as on the live boards: 'pit' on the
    two pitcher history boards and 'bat' on the hitter one, so a two-way
    player's 2021 reads the way his 2026 does. The defense history board wants
    both sides summed onto one row and calls defense_export._stamp_war instead.

    A DEGENERATE WAR READ STAMPS NOTHING FOR THAT SEASON. Coverage below
    WAR_RATE_MIN_COVERAGE of the rows carrying an id is the degenerate-fetch
    pattern score_war_rate refuses on (fa_projection.py:191-201) and this
    refuses with it, PER SEASON: a year the artifact barely covers ships blank
    while the years around it still ship, rather than a handful of values that
    read as a real column (twelve numbers among six hundred blanks is still a
    sortable column). THE REFUSAL IS READABLE ONLY IN THE PAYLOAD, because a
    blank column is dropped from the board: the served `ewar_join` block carries
    the count, the floor and HISTORY_JOIN_REFUSAL_NOTE, and the export log says
    the same line. A stamped value of exactly zero serves as 0.0, never -0.0.

    Returns the meta block the payload discloses, and says the same thing on
    `log` when one is given (the three history exports share the sentence rather
    than each writing their own). Never raises: a failed read leaves every row
    blank and says so."""
    meta = {"season": int(season), "side": side, "n_rows": len(rows),
            "n_with_id": 0, "n_covered": 0, "n_stamped": 0, "available": False}

    def _done(m: dict) -> dict:
        if m.get("refused"):
            m["note"] = HISTORY_JOIN_REFUSAL_NOTE
        if log is not None:
            if m.get("refused"):
                log(f"  {label}: {season} eWAR refused ({m['refused']})")
            else:
                # DENOMINATED ON THE ROWS THE JOIN COULD SEE (n_with_id), the
                # pool the refusal counts too, so the two lines never disagree
                # about what they are a share of.
                log(f"  {label}: {season} eWAR joined for "
                    f"{m['n_stamped']}/{m['n_with_id']} rows")
        return m

    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("history eWAR unavailable for %s (WAR fetch failed: %s)",
                     season, e)
        meta["refused"] = f"WAR fetch failed: {e}"
        return _done(meta)
    cells, n_pool = [], 0
    for r in rows:
        mid = r.get("mlbam")
        if mid is None:
            continue
        n_pool += 1
        try:
            w = ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)
        except (TypeError, ValueError):   # a non-numeric id is one blank row
            continue
        if w is not None:
            cells.append((r, w))
    meta["n_with_id"] = n_pool
    meta["n_covered"] = len(cells)
    if not n_pool or len(cells) < WAR_RATE_MIN_COVERAGE * n_pool:
        _log.warning("history eWAR REFUSED for %s: %d of %d rows covered",
                     season, len(cells), n_pool)
        meta["refused"] = (f"eWAR covered {len(cells)} of {n_pool} rows "
                           f"(floor {WAR_RATE_MIN_COVERAGE:.0%})")
        return _done(meta)
    for r, w in cells:
        v = round(float(w), 1)
        r["war"] = 0.0 if v == 0 else v   # the house -0 rule, in the JSON too
        meta["n_stamped"] += 1
    meta["available"] = True
    return _done(meta)


def stamp_team_war(teams: list[dict], rows: list[dict], season: int, *,
                   side: str) -> dict:
    """Team eWAR on the three club rollups: `team_war` = the sum of one SIDE's
    eWAR over every board row that names the club.

    THE SUM IS OVER THE UNROUNDED SIDE VALUES, not the rows' served `war`, so a
    30-arm pen does not carry 30 rounding errors; the total rounds once, at the
    end, to the 1dp the column prints. Every row of the board counts, qualified
    or not and above or below the WAR-rate display floor, because this is the
    club's production, not a leaderboard cut.

    EVERY ROW MEANS EVERY ROW, including one whose own `war` cell is withheld:
    score_war_rate stamps no `war` on a row with a zero denominator (an arm with
    a pitching eWAR cell and 0 IP), and the club total still carries him, so the
    column does not always reconcile with the visible cells. `team_war_n` counts
    the rows summed, those blank cells included, and the note says so.

    THE CLUB IS THE BOARD'S CLUB. `team` on a row is whatever team_basis says
    (current_roster today), so Team eWAR is the eWAR of the players the club
    holds now, the same basis as Bullpen+/Rotation+/Offense+ beside it. The
    returned block names that basis in the payload so a reader is never left to
    infer it; the eWAR section's `war_earned` is the other basis.

    A club with no covered row gets NEITHER field (absent, never zero): a pen
    whose arms are all missing from the WAR map must render blank rather than
    read as a replacement-level bullpen.

    A DEGENERATE WAR READ STAMPS NOTHING ANYWHERE. Coverage below
    WAR_RATE_MIN_COVERAGE of the rows that name a club is the degenerate-fetch
    pattern score_war_rate already refuses on (fa_projection.py:191-201), and
    this refuses with it: a handful of surviving arms must never print as a club
    total beside player rows that are all blank. A refusal also CLEARS the two
    fields, so a kept-stale rollup never rides an earlier run's total beside
    this run's blanks.

    Returns the meta block for `team_rollup.team_war`. Never raises: a failed
    WAR read stamps nothing and says so."""
    meta = {"side": side, "basis": TEAM_BASIS, "available": False,
            "n_rows_summed": 0, "n_rows_without_war": 0,
            "n_rows_without_team": 0, "n_teams_stamped": 0}

    def _clear():
        for t in teams:
            t.pop("team_war", None)       # absent, never zero, and never stale
            t.pop("team_war_n", None)

    try:
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("team_war unavailable (WAR fetch failed: %s)", e)
        meta["refused"] = f"WAR fetch failed: {e}"
        _clear()
        return meta
    totals: dict[str, list] = {}
    n_pool = 0
    for r in rows:
        team = r.get("team")
        if not team:
            # A teamless row is in no club total. Counted, so the three counts
            # reconcile to len(rows): a failed _team_abbrev_map blanks every
            # team code, and that outage must not read as a clean partial.
            meta["n_rows_without_team"] += 1
            continue
        n_pool += 1
        mid = r.get("mlbam")
        w = None
        if mid is not None:
            try:
                w = ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)
            except (TypeError, ValueError):   # a non-numeric id is one blank row
                w = None
        acc = totals.setdefault(str(team), [0.0, 0])
        if w is None:
            meta["n_rows_without_war"] += 1
            continue
        acc[0] += float(w)
        acc[1] += 1
        meta["n_rows_summed"] += 1
    if not n_pool or meta["n_rows_summed"] < WAR_RATE_MIN_COVERAGE * n_pool:
        _log.warning("team_war REFUSED: eWAR covers %d of %d club rows for %s",
                     meta["n_rows_summed"], n_pool, season)
        meta["refused"] = (f"eWAR covered {meta['n_rows_summed']} of {n_pool} "
                           f"club rows (floor {WAR_RATE_MIN_COVERAGE:.0%})")
        _clear()
        return meta
    for t in teams:
        acc = totals.get(str(t.get("team") or ""))
        if not acc or not acc[1]:
            t.pop("team_war", None)       # absent, never zero
            t.pop("team_war_n", None)
            continue
        v = round(acc[0], 1)
        t["team_war"] = 0.0 if v == 0 else v
        t["team_war_n"] = acc[1]
        meta["n_teams_stamped"] += 1
    meta["available"] = True
    meta["note"] = ("team_war is the sum of the club's board rows' " + side +
                    " eWAR, summed UNROUNDED and rounded once; team_war_n is "
                    "the rows summed, a row whose own eWAR cell is withheld for "
                    "a zero denominator included. A club with no covered row "
                    "carries no value. Same club basis as the Team column (see "
                    "team_basis).")
    return meta


def _join_war_ip_plus(relievers: list[dict], season: int) -> dict:
    """RELIEVER-anchored WAR/IP+: 100 = the average reliever's pitching eWAR per
    inning. The starter board ships its own starter-anchored WAR/IP+; the two are
    separate metrics that happen to share a field name across two different
    payload files, never one pooled column."""
    return score_war_rate(
        relievers, season, side="pit", denom_key="ip",
        pool_min=WAR_RATE_POOL_MIN_IP, display_min=WAR_RATE_DISPLAY_MIN_RP_IP,
        out_key="war_ip_plus", anchor="relievers with 20+ IP")


def _join_war_ip_plus_3yr(relievers: list[dict]) -> dict:
    """Stamp war_ip_plus_3yr / percentile / tag from the frozen multi-year
    artifact (tools/war_rate_plus_lab.py), reliever block.

    VINTAGE, NOT PIPELINE OUTPUT (same contract as _join_rem_plus_3yr): read
    VERBATIM from a frozen lab artifact, never recomputed here, so a row can show
    a same-day 1-year value beside a 3-year value frozen weeks earlier and an arm
    who entered the pool after the lab ran is blank. Returns the vintage block so
    the payload carries it and the frontend can disclose it."""
    return join_war_rate_3yr(relievers, "rp", "war_ip_plus_3yr", "arms")


def served_war_basis() -> dict:
    """The WAR series the 1-year WAR-rate columns serve, as the two fields a
    frozen 3-year artifact must carry to be served beside them.

      war_provider       war_source's facade default, the provider
                         _side_war_by_season reads.
      ewar_generated_at  the eWAR artifact's own generated_at: the BUILD of the
                         frozen series. A hand rebuild (the WAR_BASIS_RUNBOOK
                         cascade) moves it and can re-price completed seasons;
                         the nightly live-season rebuild (owner decision D11)
                         stamps its own time elsewhere and leaves it alone. None
                         on a provider with no artifact. ewar_vintage()'s
                         artifact_generated_at is deliberately NOT used: under
                         the nightly it is the live season's build time and
                         moves every night, so it cannot name a series.

    tools/war_rate_plus_lab.py stamps exactly this dict on both artifacts, so
    the lab and the join read the basis from one place."""
    import war_source
    prov = war_source.DEFAULT_PROVIDER
    gen = None
    if prov != "bwar":
        try:
            import ewar
            gen = (ewar.load() or {}).get("generated_at")
        except Exception:   # noqa: BLE001 - absence is a reportable state
            gen = None
    return {"war_provider": prov, "ewar_generated_at": gen}


def _served_war_provider() -> str:
    """The provider the 1-year WAR-rate columns read (_side_war_by_season ->
    war_source.side_war_by_season on the facade default)."""
    return served_war_basis()["war_provider"]


def join_war_rate_3yr(rows: list[dict], block: str, key: str, who: str) -> dict:
    """Shared frozen-vintage join for the three trailing-window WAR-rate columns
    (hitter / starter / reliever blocks of data/war_rate_plus_multiyear_eval.json).
    Missing artifact, missing block, or unmatched player -> fields absent and the
    column renders blank.

    ONE BASIS OR NOTHING (audit F10-01, re-pointed 2026-09-11 by owner
    decision). The artifact stamps the series it was measured on: `war_provider`
    (an unstamped artifact predates the stamp and is bWAR) and
    `ewar_generated_at` (the eWAR build). If either differs from
    served_war_basis(), the join REFUSES and the column renders blank. The
    provider check closes F10-01 itself: from the 2026-09-03 epoch until this
    repair the 3-year column was bWAR beside an eWAR 1-year column under copy
    asserting one scale, 4 to 5 points apart on the pitcher boards. The build
    check closes its repeat: a full eWAR rebuild inside ewar_v2 would otherwise
    leave the frozen 3-year values on the old build beside a 1-year column on
    the new one with the provider check still passing. A blank column is honest;
    a mixed-basis pair is not. The fix for a refusal is the lab (python
    tools/war_rate_plus_lab.py), never a copy change."""
    meta = {"source": WAR_RATE_MULTIYR_PATH.name, "n_stamped": 0, "available": False,
            "block": block}
    try:
        art = json.loads(WAR_RATE_MULTIYR_PATH.read_text(encoding="utf-8"))
        pv = art["proposed_values"][block]
        players = pv["players"]
    except (OSError, ValueError, KeyError):
        return meta
    basis = {"war_provider": art.get("war_provider") or "bwar",
             "ewar_generated_at": art.get("ewar_generated_at")}
    served = served_war_basis()
    meta.update(basis)
    if basis != served:
        meta["refused"] = (f"{WAR_RATE_MULTIYR_PATH.name} was measured on "
                           f"{basis['war_provider']} (eWAR build "
                           f"{basis['ewar_generated_at']}) and the 1-year column "
                           f"serves {served['war_provider']} (eWAR build "
                           f"{served['ewar_generated_at']}); re-run "
                           f"tools/war_rate_plus_lab.py")
        _log.warning("%s REFUSED: %s", key, meta["refused"])
        return meta
    n = 0
    for r in rows:
        p = players.get(str(r.get("mlbam") or ""))
        if not p:
            continue
        r[key] = p.get(key)
        r[f"{key}_pct"] = p.get("pct")
        r[f"{key}_tag"] = p.get("tag")
        if r[key] is not None:
            n += 1
    meta.update({
        "available": True, "n_stamped": n,
        "generated_at": art.get("generated_at"),
        "season": pv.get("season"), "window": pv.get("window"),
        "anchor_pool": pv.get("anchor_pool"),
        "n_in_artifact": len(players),
        # The basis (war_provider, ewar_generated_at, set above) rides on the
        # block so a page can read it instead of typing it: assets/mlbstats.js
        # carried a hand-typed bWAR sentence because this block had no field.
        "note": (f"The 3-year column is FROZEN lab output read verbatim from "
                 f"{WAR_RATE_MULTIYR_PATH.name}, as of generated_at, not this "
                 f"board's as_of. {who.capitalize()} who joined the pool since "
                 f"have no value."),
    })
    return meta


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export(season: Optional[int] = None, *, leverage_limit: Optional[int] = None,
           out_path: Optional[Path] = None, write: bool = True, log=print,
           today: Optional[str] = None) -> int:
    """Build data/bullpen_leaderboards.json and return the reliever count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  bullpen: loading {season} StatsAPI season pitching...")
    rows = load_season_pitching(season)
    if not rows:
        log(f"  bullpen: no pitching data for {season} (source blocked or empty); skipping")
        return 0
    swstr = load_bref_swstr(season)  # best-effort SwStr% enrichment

    log(f"  bullpen: computing leverage from StatsAPI winProbability"
        + (f" (first {leverage_limit} games)" if leverage_limit else " (full season)") + "...")
    try:
        import mlb_leverage
        leverage, coverage = mlb_leverage.fetch_season_leverage(
            season, limit=leverage_limit,
            progress=lambda i, n: (log(f"    leverage {i}/{n} games") if i % 200 == 0 else None))
    except Exception as e:
        _log.warning("leverage walk failed: %s", e)
        leverage, coverage = {}, {"games": 0, "games_total": 0}

    relievers = build_relievers(rows, leverage, swstr)
    scored = rem_plus.score_pool(relievers)
    n_lev = _join_leverage_consistency(scored["relievers"])
    if n_lev:
        log(f"  bullpen: gmLI-consistency joined for {n_lev} relievers")
    r3_meta = _join_rem_plus_3yr(scored["relievers"])
    if r3_meta.get("n_stamped"):
        log(f"  bullpen: 3-year REM+ joined for {r3_meta['n_stamped']} relievers "
            f"(frozen lab vintage {r3_meta.get('generated_at')})")
    n_xr = _join_xrem_plus(scored["relievers"], season)
    if n_xr:
        log(f"  bullpen: xREM+ (Savant deserved run prevention) joined for {n_xr} relievers")
    wr_meta = _join_war_ip_plus(scored["relievers"], season)
    if wr_meta.get("available"):
        log(f"  bullpen: WAR/IP+ (reliever-anchored) joined for "
            f"{wr_meta['n_stamped']} relievers (pool {wr_meta['pool_n']})")
    elif wr_meta.get("refused"):
        log(f"  bullpen: WAR/IP+ refused ({wr_meta['refused']})")
    wr3_meta = _join_war_ip_plus_3yr(scored["relievers"])
    if wr3_meta.get("n_stamped"):
        log(f"  bullpen: 3-year WAR/IP+ joined for {wr3_meta['n_stamped']} relievers "
            f"(frozen lab vintage {wr3_meta.get('generated_at')})")

    # ZERO-TEAM ROLLUP GUARD. The `if not rows` check above protects the reliever
    # rows and protected nothing else: a blanked team code leaves every row intact
    # and empties scored["teams"], which publishes 0 team pens over the 30 that
    # were there and drops Bullpen+ to a flat 100. See guard_nonempty_block.
    teams, rollup_meta = guard_nonempty_block(
        scored["teams"], out_path, key="teams", source="bullpen_leaderboards",
        label="bullpen", log=log)

    # TEAM eWAR (E5). The club total the Team Bullpens board prints beside
    # Bullpen+: every reliever row that names the club, summed on the PITCHING
    # side unrounded and rounded once. Runs on the SERVED teams, so a kept-stale
    # rollup is stamped from the rows it is served with, and an uncovered club
    # carries no value at all.
    rollup_meta["team_war"] = stamp_team_war(
        teams, scored["relievers"], season, side="pit")
    if rollup_meta["team_war"].get("n_teams_stamped"):
        log(f"  bullpen: team eWAR stamped on "
            f"{rollup_meta['team_war']['n_teams_stamped']} pens "
            f"({rollup_meta['team_war']['n_rows_summed']} rows summed)")

    # Bullpen Charts should show only players actually ON the active roster; drop
    # off-roster arms (demoted / released) from the depth ladders. Roster fetch is
    # a single guarded pass and falls back to NO filtering if it fails. Runs on the
    # SERVED teams, so a kept-stale rollup is still filtered to today's rosters.
    active_ids = _active_mlbam_ids(season)
    if active_ids is None:
        log("  bullpen: active-roster feed unavailable; depth ladders left unfiltered")
    else:
        n_off = _apply_roster_filter(teams, active_ids)
        log(f"  bullpen: active-roster filter kept {len(active_ids)} rostered ids, "
            f"dropped {n_off} off-roster arms from depth ladders")

    payload = {
        "generated_at": today,
        "season": season,
        "as_of": today,
        "coverage": {
            "games": coverage.get("games", 0),
            "expected": coverage.get("games_total", 0),
            "note": (f"gmLI, WPA and SD-MD cover {coverage.get('games', 0)} of "
                     f"{coverage.get('games_total', 0)} games walked; REM+ is "
                     f"full-season."),
        },
        "verdict": _verdict(),
        "backtest": _backtest(),
        # Vintage of the FROZEN 3-year REM+ column (see _join_rem_plus_3yr):
        # it is not regenerated by this run, so the frontend can disclose how
        # old the 3yr number beside a live 1yr number actually is.
        "multiyear": r3_meta,
        # WAR/IP+ scale block (anchor pool + measured pool parameters) and the
        # vintage of its FROZEN 3-year companion, same disclosure contract.
        "war_rate": wr_meta,
        # WHICH BUILD the served eWAR numerator comes from, and whether it has
        # fallen behind the frame under it (audit F10-02 / F11-01). data/ewar.json
        # re-prices its live season nightly; a missed or refused night leaves a
        # current-season WAR behind the innings beside it, and the side-map
        # receipt (war_source.side_war_by_season) makes `stale` say so.
        "ewar_vintage": _war_source_vintage(as_of=today),
        "multiyear_war_rate": wr3_meta,
        # Which club a row's `team` names, how many rows were repointed, and how
        # many serve a blank team (see team_basis_meta), plus the zero-rollup
        # guard's verdict for this run (see guard_nonempty_block).
        "team_basis": team_basis_meta(rows, label=f"pitching {season}"),
        "team_rollup": rollup_meta,
        "pool": scored["pool"],
        "relievers": scored["relievers"],
        "teams": teams,
    }

    n = len(scored["relievers"])
    log(f"  bullpen: {n} relievers ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(teams)} team pens; leverage {coverage.get('games', 0)}/"
        f"{coverage.get('games_total', 0)} games")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        try:
            shown = out_path.relative_to(Path(__file__).parent)
        except ValueError:
            shown = out_path.name
        log(f"  bullpen: wrote {shown}")
    return n


_HISTORY_FIELDS = ("mlbam", "name", "team", "rem_plus", "riv_plus", "role",
                   "ip", "g", "tbf", "era", "fip", "k_pct", "bb_pct", "k_bb_pct",
                   "swstr_pct", "hr9", "gmli", "wpa", "sd", "md", "saves", "holds",
                   "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/bullpen_history.json - per-season reliever boards (qualified
    arms) for the /mlbstats/ yearly history tabs, so users can read past seasons
    and eyeball how REM+ (skill) and RIV+ (realized impact) played forward. One
    compact row per qualified reliever per season; the current live season stays
    in bullpen_leaderboards.json. Cached winProbability keeps the walk fast.

    Each row also carries `war`, that season's PITCHING eWAR, joined per
    (player, season) (E6): the season count travels to a past season the way the
    live-pool WAR-RATE indexes cannot."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    basis_rows: list[dict] = []
    ewar_join: dict[str, dict] = {}
    for y in seasons:
        log(f"  bullpen-history: {y}...")
        rows = load_season_pitching(y)
        if not rows:
            log(f"  bullpen-history: no data for {y}; skipping")
            continue
        swstr = load_bref_swstr(y)
        try:
            import mlb_leverage
            leverage, cov = mlb_leverage.fetch_season_leverage(y)
        except Exception as e:  # noqa: BLE001
            _log.warning("history leverage walk %s failed: %s", y, e)
            leverage, cov = {}, {"games": 0, "games_total": 0}
        scored = rem_plus.score_pool(build_relievers(rows, leverage, swstr))
        qual = [r for r in scored["relievers"] if r.get("qualified")]
        basis_rows.extend(basis_rows_for(qual, rows))
        board = [{k: r.get(k) for k in _HISTORY_FIELDS} for r in qual]
        # eWAR per (player, season), E6. Stamped on the SERVED row rather than
        # listed in _HISTORY_FIELDS: those are read off the scored row with
        # .get, which would write an explicit null on every arm the artifact
        # does not cover, and absent-means-absent is this column's whole rule.
        ewar_join[str(y)] = stamp_history_war(board, y, side="pit",
                                              label="bullpen-history", log=log)
        board.sort(key=lambda r: (r.get("rem_plus") or -999), reverse=True)
        hist[str(y)] = {
            "season": y,
            "leverage_games": cov.get("games", 0),
            "leverage_expected": cov.get("games_total", 0),
            "n_qualified": len(board),
            "relievers": board,
        }
        log(f"  bullpen-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Qualified relievers by season. REM+: run-prevention skill. RIV+: "
                 "realized leverage-weighted impact (deployment, not skill)."),
        "team_basis": team_basis_meta(basis_rows, label="bullpen history",
                                      scope="history"),
        # What the eWAR join did, season by season, including a season it
        # refused: "no column on 2021" and "the WAR read failed" are different
        # facts and the served file states which.
        "ewar_join": ewar_join,
        # WHICH eWAR BUILD the column on these rows comes from. A PAYLOAD
        # RECEIPT, not page copy: the history column titles are static ("eWAR
        # for the season shown"), so no surface renders this block today, and it
        # ships for the reason the audit that created it gave (F10-02: a served
        # number nobody could date). On a PAST season the counter that reads is
        # `bwar_revised_frozen`, a B-Ref restatement re-priced only by a hand
        # run; `bwar_revised_live` is the missed-nightly one and belongs to the
        # live boards. The sibling leverage history ships the same block, so the
        # five history payloads say one thing. It ships iff the column does.
        **({"ewar_vintage": _war_source_vintage(as_of=date.today().isoformat())}
           if any("war" in r for y in hist.values() for r in y["relievers"])
           else {}),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  bullpen-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        _limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        export(_season, leverage_limit=_limit)
