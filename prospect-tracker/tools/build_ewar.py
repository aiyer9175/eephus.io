# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Build eWAR v2 -> data/ewar.json + data/ewar_eval.json.

    python tools/build_ewar.py                 # build + gates, print, write nothing
    python tools/build_ewar.py --write         # ...and commit both artifacts
    python tools/build_ewar.py --first 2011 --last 2026 --write
    python tools/build_ewar.py --no-sensitivity --write
    python tools/build_ewar.py --nightly               # the daily step, dry run
    python tools/build_ewar.py --nightly --write       # ...and write data/ewar.json

THE NIGHTLY (owner decision D11, 2026-09-11: nightly; run_monthly run_daily step
d8b, before the d9 timeseries rebuild, and monthly step 3-pre, before the
monthly's first WAR reader: the runbook puts step B ahead of every reader).
`--nightly` never runs the full build. It carries every COMPLETED season forward
byte for byte, re-prices only the live season, and writes ONLY data/ewar.json
(plus its own untracked copy, CARRY_PATH):
  - completed seasons are frozen: war_source.EWAR_FREEZE_MONTH_DAY of a season's
    own year completes it, the first nightly on or after that date prices it
    one last time, and from then on its blocks are copied, never rebuilt. Each
    frozen season's sha256 (war_source.ewar_season_digest) is recorded in
    meta.cadence and the nightly refuses to write if one would change. A HAND
    build carries no cadence: the seasons it froze are the ones complete on the
    day it was BUILT, so a season it priced in progress is re-priced, not frozen
    at those numbers, however late the file is read;
  - the box restores the COMMITTED data/ewar.json before every run
    (deploy/nightly-build.sh `git checkout -- .`), which would throw away every
    night's state. So each write is also copied to CARRY_PATH (.cache, never
    tracked), and the next night starts from that copy whenever it descends
    from the committed build (same generated_at, digests agreeing, a later live
    build); the copy is put back on disk BEFORE anything is priced, so a night
    that fails serves the last good nightly, not the committed hand build;
  - the live season is priced on that night's inputs or not at all: the
    war_daily frames the rest of the night serves (war_source.stint_frame; a
    last-good-cache fallback REFUSES), the StatsAPI season stats behind its FIP
    re-read on the nightly's own cache key (the shared FA corpus pickle is up
    to fa_projection.CORPUS_TTL_DAYS old and is neither read for that season
    nor rewritten), and the standings blob behind its replacement level. An
    input older than the one the carried live season was priced on refuses, so
    the live season never moves backwards;
  - `generated_at` (the frozen series' build, the label term of the board
    fingerprint) is carried forward; `live_built_at` stamps the live season;
  - data/ewar_eval.json is NOT rewritten: its gates score 2016 to the last
    completed season, which the nightly does not move;
  - the fitted artifacts downstream of runbook step B (outcome curve, anchors,
    draft slot curve, war_rate_plus vintages, eFV matrices and floors, the
    career_war rebase) read completed seasons only, so none rebuilds nightly.
A hand full build (`--write` without `--nightly`) is still the only way to
re-price a completed season, and it is the runbook cascade. A refusal returns 2
and leaves the best known artifact on disk; it never stops the pipeline.

Measured 2026-09-11 on the on-disk frames: a one-season build equals that
season's slice of the full build exactly (2025 and 2026), and a full rebuild
reproduced every 2011-2025 block of the 2026-09-03 artifact byte for byte, so
freezing changes no completed-season number; it makes that structural.

The full build's only network call is pybaseball's cached bwar_bat / bwar_pitch
static CSV pull (--force-fetch to bypass the local 7-day pickle cache). Everything
else - the FIP corpus, Statcast OAA, fielding innings, the k_inn constants, the
standings used by the team-wins gate - is read from disk. The nightly reads
war_daily through war_source (the served download), and the live season's
StatsAPI pitching lines and standings through the shared scraper cache (at most
one request each when the cache is over a day old).

TWO WINDOWS, on purpose, since 2026-09-03.
  * BUILD window (--first/--last, default 2011..current year): the seasons the
    artifact carries. 2011 is the first season the eFV first-6yr label pool
    reaches (debuts.json backfill), and the FIP corpus prices it in full:
    707/707, 721/723, 724/729, 743/748, 808/810 war_daily pitcher rows FIP-
    priced for 2011..2015, ip_share 1.0000 each season (build 2026-09-03).
    Fielding is all-fallback before 2016 (no Statcast OAA), which at the
    shipped fielding_blend_w of 0.0 changes nothing: position players carry
    bWAR exactly in EVERY season until the SDR defense drop lands.
  * GATE window (--eval-first/--eval-last, default 2016..last completed
    season): the seasons the validity gates score. It stays 2016-2025 so the
    gate record (team wins r 0.8595 vs 0.8803, persistence 0.3617 vs 0.1768)
    remains comparable across rebuilds; extending the BUILD window must not
    silently move the GATE window, which is what evaluate()'s default (first =
    the model's first season) would do.
  The full-build accounting (league sum per season over EVERY built season) is
  printed and written beside the windowed block so the pre-2016 seasons are
  still checked, just not scored.

OWNER DECISION 2026-09-03: eWAR v2 becomes the SERVED and LABEL WAR site-wide
(the basis shift). bWAR remains the INPUT frame this is built on. The build is
arithmetic on inputs, so that decision changes nothing here except that the
artifact must now cover the label window; the consumer wiring is other lanes.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as _dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ewar                              # noqa: E402
import war_source                        # noqa: E402

# First season the served artifact must carry. The eFV first-6yr label pool
# reaches back to 2011 debuts, and the label series has to exist for every
# season a label sums over, so the artifact starts where the labels start.
# ewar.DEFAULT_FIRST_SEASON (2016) stays the GATE anchor: it is the OAA era
# the shipped gate record was measured on, not the label window.
LABEL_FIRST_SEASON = 2011


def _fmt_gate1(g: dict) -> str:
    if not g.get("n_team_seasons"):
        return f"  gate 1: {g.get('note')}"
    e, b = g["ewar"], g["bwar"]
    return (f"  gate 1 TEAM WINS  n={g['n_team_seasons']} team-seasons "
            f"{g['seasons'][0]}-{g['seasons'][1]}\n"
            f"    r            eWAR {e['r']:+.4f}   bWAR {b['r']:+.4f}\n"
            f"    MAE (fit)    eWAR {e['mae_fit']:.3f}    bWAR {b['mae_fit']:.3f}\n"
            f"    MAE (0-par)  eWAR {e['mae_zero_param']:.3f}    "
            f"bWAR {b['mae_zero_param']:.3f}\n"
            f"    verdict      {g['verdict']}")


def _fmt_gate2(g: dict) -> str:
    if g.get("n_pairs", 0) < 30:
        return f"  gate 2: {g.get('note')} (n={g.get('n_pairs')})"
    f = g["forecast_next_year_actual_runs"]
    return (f"  gate 2 PITCHER PERSISTENCE  n={g['n_pairs']} pairs, "
            f"min {g['min_ip']:.0f} IP both years\n"
            f"    self r (y -> y+1)          FIP {g['self_r_ewar_fip']:+.4f}   "
            f"RA {g['self_r_bwar_ra']:+.4f}\n"
            f"    predicts next-year actual  FIP {f['from_ewar_fip']:+.4f}   "
            f"RA {f['from_bwar_ra']:+.4f}\n"
            f"    verdict                    {g['verdict']}")


def _fmt_gate3(g: dict) -> str:
    lines = ["  gate 3 COVERAGE"]
    for season, blk in g["fielding"]["by_season"].items():
        lines.append(f"    {season}  innings covered {blk['share_within_oaa_positions']:.3f} "
                     f"within the 7 OAA positions / "
                     f"{blk['fielding_innings_share_covered']:.3f} of all defense   "
                     f"non-pitcher player-seasons with a read "
                     f"{blk['n_with_statcast_read']}/"
                     f"{blk['n_non_pitcher_player_seasons']}")
    p = g["pitching"]
    lines.append(f"    pitching: {p['n_fip_priced']}/{p['n_rows']} rows FIP-priced, "
                 f"{p['ip_share_fip_priced']:.4f} of IP")
    return "\n".join(lines)


def _fmt_build(model: dict, payload: dict) -> str:
    """Per built season: player-seasons in the artifact, pitcher rows and the
    FIP-priced share. This is the coverage table for the WHOLE build, printed
    because gate 3 only reports the gate window."""
    per: dict[int, int] = {}
    for by_year in payload["players"].values():
        for s in by_year:
            per[int(s)] = per.get(int(s), 0) + 1
    pit = model["meta"]["pitching"]["by_season"]
    lines = ["  BUILD  player-seasons and FIP coverage per season"]
    for season in sorted(per):
        p = pit.get(season) or pit.get(str(season)) or {}
        lines.append(f"    {season}  player-seasons {per[season]:>5}   "
                     f"pitcher rows FIP-priced {p.get('n_covered', 0):>4}/"
                     f"{p.get('n_rows', 0):<4}  ip_share {p.get('ip_share', 0.0):.4f}")
    return "\n".join(lines)


def _fmt_sum(g: dict, title: str = "league WAR sum per season") -> str:
    lines = [f"  ACCOUNTING  {title}"]
    for season, blk in g["by_season"].items():
        lines.append(f"    {season}  target {blk['target']:>7.1f}   "
                     f"bWAR {blk['bwar_sum']:>7.1f}   "
                     f"eWAR pre {blk['ewar_sum_pre_rescale']:>7.1f}   "
                     f"eWAR {blk['ewar_sum']:>7.1f}   "
                     f"rep x{blk['replacement_scale']:.4f}")
    lines.append(f"    max |eWAR sum - target| = {g['max_abs_deviation_from_target']}")
    return "\n".join(lines)


# ================================================================ the nightly
#: The live season's replacement scale reads near 1.0 only when the war_daily
#: pull and the standings blob are from the same day (see the build-window
#: accounting note in main()); outside this band the nightly says so.
LIVE_SCALE_BAND = (0.95, 1.05)

#: The nightly's own state, outside git. The box restores the COMMITTED
#: data/ewar.json before every run, so without this copy each night would start
#: from the hand build again (and, from the freeze date on, freeze a season at
#: the hand build's in-progress numbers).
CARRY_PATH = Path(ewar.CACHE_DIR) / "ewar" / "nightly.json"

#: The scraper-cache key the nightly reads the live season's StatsAPI pitching
#: stats under. Its own key, so the refresh does not touch fa_statsapi_* (a
#: newer source file would make fa_projection rebuild the shared FA corpus,
#: which would change that corpus's cadence as a side effect).
LIVE_STATS_KEY = "ewar_nightly_statsapi_pitching"

#: A re-read of a season's StatsAPI pitching lines is accepted when it carries
#: at least this share of the rows the corpus pickle holds for it (a season's
#: pitcher list only grows, so a short read is a failed or truncated fetch).
LIVE_STATS_MIN_ROW_SHARE = 0.9


def nightly_plan(prev: dict, today: _dt.date, frame_seasons) -> dict:
    """Which seasons the nightly re-prices and which it freezes. Pure.

    frozen before  meta.cadence.frozen_seasons on a nightly artifact; on a
                   HAND build, the seasons that were complete on the day it
                   was built (war_source.ewar_complete_at_build), never the
                   seasons complete today: a hand build read after a season's
                   freeze date priced that season in progress
    rebuild        every season of the window that is not frozen and has
                   war_daily rows, plus a new season the frames have begun
    freeze now     the rebuilt seasons that are complete today (their last
                   pricing: the freeze pass)
    live           the rebuilt season that is still in progress, if any"""
    lo, hi = (int(x) for x in (prev.get("seasons") or [0, -1])[:2])
    have = {int(s) for s in frame_seasons}
    cad = ((prev.get("meta") or {}).get("cadence") or {})
    if cad.get("mode") == "nightly" and cad.get("frozen_seasons") is not None:
        frozen = {int(s) for s in cad["frozen_seasons"]}
    else:
        frozen = set(war_source.ewar_complete_at_build(prev))
    rebuild = [s for s in range(lo, hi + 1) if s not in frozen and s in have]
    cur = today.year
    if cur > hi and cur in have and not war_source.ewar_season_complete(cur, today):
        rebuild.append(cur)
    freeze_now = [s for s in rebuild if war_source.ewar_season_complete(s, today)]
    live = [s for s in rebuild if s not in freeze_now]
    return {"frozen_before": sorted(frozen), "rebuild": sorted(rebuild),
            "freeze_now": sorted(freeze_now), "live": max(live) if live else None,
            "frozen_after": sorted(frozen | set(freeze_now))}


def choose_base(tracked: dict, carried: dict | None) -> tuple[dict, str, list[str]]:
    """(artifact to start from, "tracked" | "carried", notes). Pure.

    The carried copy wins only when it DESCENDS from the committed build: the
    same generated_at, a nightly whose every frozen season is on its digest,
    agreeing with the committed file on every season both have frozen, and a
    later live build than the committed file's. Anything else means the repo
    moved (a new hand build was committed, or a nightly was committed from
    another machine) or the copy is damaged, and the committed file wins."""
    notes: list[str] = []
    if not carried:
        return tracked, "tracked", notes
    if carried.get("generated_at") != tracked.get("generated_at"):
        notes.append(f"carried copy is of build {carried.get('generated_at')}, the committed "
                     f"file is build {tracked.get('generated_at')}: the committed build wins")
        return tracked, "tracked", notes
    ccad = war_source.ewar_cadence(carried)
    if ccad.get("mode") != "nightly":
        notes.append("carried copy is not a nightly build: ignored")
        return tracked, "tracked", notes
    cdig = ccad.get("frozen_digests") or {}
    for s in ccad.get("frozen_seasons") or []:
        if cdig.get(str(s)) != war_source.ewar_season_digest(carried, s):
            notes.append(f"carried copy's frozen season {s} is off its digest: ignored")
            return tracked, "tracked", notes
    tcad = war_source.ewar_cadence(tracked)
    if tcad.get("mode") == "nightly":
        tdig = tcad.get("frozen_digests") or {}
        both = set(map(int, tcad.get("frozen_seasons") or [])) & set(
            map(int, ccad.get("frozen_seasons") or []))
        for s in sorted(both):
            if tdig.get(str(s)) != cdig.get(str(s)):
                notes.append(f"carried copy and committed file disagree on frozen season {s}: "
                             f"the committed file wins")
                return tracked, "tracked", notes
        if str(ccad.get("live_built_at") or "") <= str(tcad.get("live_built_at") or ""):
            return tracked, "tracked", notes
    return carried, "carried", notes


def _season_meta_keys(meta: dict) -> None:
    """Recompute the window totals of meta.pitching from its per-season blocks,
    so a merged artifact's aggregate agrees with the seasons it carries."""
    pit = meta.get("pitching") or {}
    by = pit.get("by_season") or {}
    if not by:
        return
    n_rows = sum(int(b.get("n_rows") or 0) for b in by.values())
    n_cov = sum(int(b.get("n_covered") or 0) for b in by.values())
    ip_t = sum(float(b.get("ip_total") or 0.0) for b in by.values())
    ip_c = sum(float(b.get("ip_covered") or 0.0) for b in by.values())
    pit.update({"n_rows": n_rows, "n_covered": n_cov, "ip_total": round(ip_t, 1),
                "ip_covered": round(ip_c, 1),
                "ip_share": round(ip_c / ip_t, 4) if ip_t else 0.0})


def merge_nightly(prev: dict, rebuilt: dict, plan: dict, *, now_iso: str,
                  frames: dict | None = None) -> dict:
    """The nightly artifact: `prev` with the rebuilt seasons swapped in. Pure.

    `rebuilt` is {season: export_payload of a one-season build}, already JSON
    round-tripped (string keys). Every season not rebuilt is carried as the same
    objects, so its blocks serialise to the same bytes. Players and seasons are
    laid out in numeric order so the file is deterministic night to night."""
    rebuilt = {int(s): p for s, p in rebuilt.items()}
    keep: dict = {}
    for mid, by in (prev.get("players") or {}).items():
        rest = {s: b for s, b in by.items() if int(s) not in rebuilt}
        if rest:
            keep[mid] = rest
    for s, pay in rebuilt.items():
        for mid, by in (pay.get("players") or {}).items():
            if str(s) in by:
                keep.setdefault(mid, {})[str(s)] = by[str(s)]
    players = {mid: {s: keep[mid][s] for s in sorted(keep[mid], key=int)}
               for mid in sorted(keep, key=int)}

    meta = copy.deepcopy(prev.get("meta") or {})
    for s, pay in rebuilt.items():
        pm = pay.get("meta") or {}
        k = str(s)
        for path in (("by_season",), ("pitching", "by_season"), ("fielding", "by_season"),
                     ("rpw_by_season",)):
            src, dst = pm, meta
            for key in path[:-1]:
                src, dst = src.get(key) or {}, dst.setdefault(key, {})
            leaf = path[-1]
            val = (src.get(leaf) or {}).get(k)
            if val is not None:
                dst.setdefault(leaf, {})[k] = val
    _season_meta_keys(meta)
    seasons_all = sorted({int(s) for by in players.values() for s in by})
    window = [min(seasons_all), max(seasons_all)] if seasons_all else list(prev.get("seasons") or [])
    meta["seasons"] = window
    prev_cad = meta.get("cadence") or {}
    digests = dict(prev_cad.get("frozen_digests") or {})
    built = dict(prev_cad.get("frozen_built_at") or {})
    carrier = {"players": players}
    for s in plan["frozen_after"]:
        if str(s) not in digests:
            digests[str(s)] = war_source.ewar_season_digest(carrier, s)
        if str(s) not in built:
            # priced tonight (the freeze pass) or by the build the artifact came from
            built[str(s)] = now_iso if int(s) in rebuilt else prev.get("generated_at")
    live = plan.get("live")
    live_scale = None
    if live is not None:
        live_scale = ((meta.get("by_season") or {}).get(str(live)) or {}).get("replacement_scale")
    meta["cadence"] = {
        "mode": "nightly",
        "command": war_source.EWAR_NIGHTLY_CMD,
        "freeze_rule": ("a season is complete from %02d-%02d of its own year; the first "
                        "nightly on or after it prices the season one last time and "
                        "freezes it" % war_source.EWAR_FREEZE_MONTH_DAY),
        "label_build_at": prev.get("generated_at"),
        "live_season": live,
        "live_built_at": now_iso if live is not None else prev_cad.get("live_built_at"),
        "live_replacement_scale": live_scale,
        "rebuilt_seasons": sorted(rebuilt),
        "frozen_now": plan["freeze_now"],
        "frozen_seasons": plan["frozen_after"],
        "frozen_digests": {k: digests[k] for k in sorted(digests, key=int)},
        "frozen_built_at": {k: built[k] for k in sorted(built, key=int)},
        "frames": frames or {},
    }
    src = rebuilt[max(rebuilt)] if rebuilt else prev
    out = {
        "model": src.get("model", prev.get("model")),
        # the FROZEN series' build: storage's board fingerprint reads this, so it
        # moves only when a hand build re-prices completed seasons
        "generated_at": prev.get("generated_at"),
        "live_built_at": meta["cadence"]["live_built_at"],
        "seasons": window,
        "consumers": src.get("consumers", prev.get("consumers")),
        "field_key": src.get("field_key", prev.get("field_key")),
        "meta": meta,
        "n_player_seasons": sum(len(by) for by in players.values()),
        "players": players,
    }
    return out


def check_nightly(prev: dict, new: dict, plan: dict) -> list[str]:
    """Why the nightly must NOT write, or []. Pure. The frozen seasons of the
    previous artifact must hash identically in the new one, the label build must
    not move, and a live season must carry blocks."""
    problems = []
    for s in plan["frozen_before"]:
        if war_source.ewar_season_digest(prev, s) != war_source.ewar_season_digest(new, s):
            problems.append(f"frozen season {s} would change")
    if new.get("generated_at") != prev.get("generated_at"):
        problems.append("generated_at (the frozen series' build) would move")
    if plan.get("live") is not None:
        n = sum(1 for by in new["players"].values() if str(plan["live"]) in by)
        if n == 0:
            problems.append(f"live season {plan['live']} has no player-seasons")
    return problems


def input_regressions(prev: dict, frames: dict, plan: dict) -> list[str]:
    """Why tonight's inputs are OLDER than the ones the artifact's live season
    was last priced on, or []. Pure. A build on older inputs would move the live
    season backwards, which is worse than serving the carried copy one more
    night and saying so (ewar_cadence_status)."""
    live = plan.get("live")
    cad = war_source.ewar_cadence(prev)
    if live is None or cad.get("live_season") != live:
        return []
    was = cad.get("frames") or {}
    out = []
    for key, what in (("fip_source_at", "StatsAPI season stats behind the live FIP"),
                      ("standings_at", "standings blob")):
        a, b = was.get(key), frames.get(key)
        if a and b and str(b) < str(a):
            out.append(f"the {what} ({b}) are older than the ones the carried live season "
                       f"was priced on ({a})")
    return out


def _move_report(prev: dict, new: dict, seasons) -> dict:
    """What the nightly moved, per rebuilt season: blocks before and after,
    eWAR values that changed, the largest change, pitcher sides that changed."""
    rep = {}
    for s in seasons:
        k = str(s)
        a = {m: by[k] for m, by in prev["players"].items() if k in by}
        b = {m: by[k] for m, by in new["players"].items() if k in by}
        ids = set(a) | set(b)
        dew = [abs(float((b.get(m) or {}).get("ew", 0.0)) - float((a.get(m) or {}).get("ew", 0.0)))
               for m in ids]
        rep[k] = {"blocks_before": len(a), "blocks_after": len(b),
                  "added": len(set(b) - set(a)), "removed": len(set(a) - set(b)),
                  "blocks_changed": sum(1 for m in ids if a.get(m) != b.get(m)),
                  "ew_changed": sum(1 for d in dew if d > 0.0),
                  "ewp_changed": sum(1 for m in ids if (a.get(m) or {}).get("ewp")
                                     != (b.get(m) or {}).get("ewp")),
                  "max_abs_ew_change": round(max(dew), 2) if dew else 0.0}
    return rep


def _mtime_iso(p: Path) -> str | None:
    try:
        return _dt.datetime.fromtimestamp(Path(p).stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


@contextlib.contextmanager
def _frames_from_war_source():
    """Price the live season on the frames the rest of the night serves.

    ewar.bwar_frames keeps its own 7-day pickle of the war_daily download, so a
    nightly built through it could price the live season on a week-old frame
    while every exporter reads today's. war_source.stint_frame is the served
    download, read once per side here, so the artifact's bwp/bwb match the frame
    the transform later reads and ewar_frame_diagnostics' live-season drift is
    zero after the step. Its last-good fallback is recorded in `served_stale`,
    and the caller refuses on it."""
    bat = war_source.stint_frame("bat", provider="bwar")
    pit = war_source.stint_frame("pit", provider="bwar")
    now = _dt.datetime.now().isoformat(timespec="seconds")
    info = {"source": "war_source.stint_frame(provider='bwar')",
            "read_at": now,
            "served_stale": {k: v for k, v in war_source.served_stale().items()
                             if k in ("bat", "pit")},
            "rows": {"bat": int(len(bat)), "pit": int(len(pit))}}
    orig = ewar.bwar_frames
    ewar.bwar_frames = lambda force=False: (bat, pit)
    try:
        yield bat, pit, info
    finally:
        ewar.bwar_frames = orig


def _warm_standings(season: int) -> str | None:
    """Refresh the live season's standings blob through the shared scraper
    cache before the build reads it. ewar.build re-derives the live season's
    replacement level from team-games in that blob; a blob a day behind the
    frames skews the league-sum target (the build-window note in main()). d9's
    projections export reads the same cache key later in the night, so this
    moves the request earlier rather than adding one. Returns the blob's mtime,
    or None when it could not be read (the build then uses what is on disk)."""
    try:
        from fa_fit_backtest import standings_now   # noqa: PLC0415 - network-touching
        standings_now(int(season))
    except Exception as exc:   # noqa: BLE001 - a stale blob is disclosed, not fatal
        print(f"  standings warm for {season} failed ({type(exc).__name__}); using the cached blob")
    return _mtime_iso(Path(ewar.CACHE_DIR) / f"statsapi_standings_{int(season)}.json")


def _fetch_live_pitching(first: int, last: int, force: bool = False,
                         max_workers: int = 6) -> dict:
    """fa_sources.fetch_statsapi_season_range's return shape, pitching only, on
    the nightly's own cache key (LIVE_STATS_KEY): the same URL and the same
    shared scraper cache rules (24 hours for the current season)."""
    import fa_sources                  # noqa: PLC0415
    import scrapers                    # noqa: PLC0415
    out: dict = {}
    for s in range(int(first), int(last) + 1):
        out[(s, "hitting")] = []
        url = fa_sources._STATSAPI_SEASON_URL.format(group="pitching", season=s)
        fr = scrapers._fetch(url, f"{LIVE_STATS_KEY}_{s}", force=force, accept_json=True)
        splits: list = []
        if fr.status == 200 and fr.body:
            try:
                stats = json.loads(fr.body).get("stats") or []
                splits = (stats[0].get("splits") or []) if stats else []
            except (ValueError, KeyError, AttributeError, IndexError):
                splits = []
        out[(s, "pitching")] = splits
    return out


def live_fip_corpus(seasons) -> tuple[dict, dict]:
    """(corpus for ewar.build, vintage) with the rebuilt seasons' pitcher FIP
    rows and league blocks re-read tonight.

    ewar reads FIP from fa_projection's corpus pickle, which is up to
    CORPUS_TTL_DAYS old in season and is only rebuilt after this step, so a
    nightly on the pickle alone would stamp today's build on a FIP numerator up
    to three days behind the innings beside it. The rebuilt seasons are run
    through fa_projection.build_corpus itself (the platform's one FIP
    convention: per season, constant set so league FIP equals league ERA) on
    that night's StatsAPI pitching lines, in memory: the shared pickle is
    neither read for those seasons nor written, and the WAR and age labels the
    FIP does not use are not joined. A season whose re-read is short keeps the
    pickle's rows, and the vintage says so."""
    import tempfile                    # noqa: PLC0415
    import fa_projection as fp         # noqa: PLC0415
    seasons = sorted({int(s) for s in seasons})
    base = ewar._corpus()
    pickle_at = _mtime_iso(fp.CORPUS_CACHE)
    fresh = None
    err = None
    if seasons:
        orig = (fp.CORPUS_CACHE, fp._war_age_maps, fp.fa_sources.fetch_statsapi_season_range)
        try:
            with tempfile.TemporaryDirectory() as td:
                fp.CORPUS_CACHE = Path(td) / "ewar_nightly_corpus.pkl"
                fp._war_age_maps = lambda provider=None: ({}, {})
                fp.fa_sources.fetch_statsapi_season_range = _fetch_live_pitching
                try:
                    fresh = fp.build_corpus(first_season=seasons[0], last_season=seasons[-1])
                finally:
                    (fp.CORPUS_CACHE, fp._war_age_maps,
                     fp.fa_sources.fetch_statsapi_season_range) = orig
        except Exception as exc:   # noqa: BLE001 - the pickle is the fallback, disclosed
            err = f"{type(exc).__name__}: {exc}"
            fresh = None
    import scrapers                    # noqa: PLC0415
    merged = dict(base)
    pit = list(base.get("pit") or [])
    league = dict(base.get("league") or {})
    vintage: dict = {"fip_source_by_season": {}}
    for s in seasons:
        have = sum(1 for r in pit if int(r.get("season") or 0) == s)
        rows = [r for r in (fresh or {}).get("pit", []) if int(r.get("season") or 0) == s]
        lg = ((fresh or {}).get("league") or {}).get(s) or {}
        src_at = _mtime_iso(Path(scrapers.CACHE_DIR) / f"{LIVE_STATS_KEY}_{s}.json")
        if rows and lg.get("era") is not None and len(rows) >= LIVE_STATS_MIN_ROW_SHARE * have:
            pit = [r for r in pit if int(r.get("season") or 0) != s] + rows
            league = {k: v for k, v in league.items() if int(k) != s}
            league[s] = lg
            vintage["fip_source_by_season"][str(s)] = {
                "source": "StatsAPI season pitching re-read by the nightly", "at": src_at,
                "rows": len(rows), "pickle_rows": have}
        else:
            shared = _mtime_iso(Path(scrapers.CACHE_DIR) / f"fa_statsapi_pitching_{s}.json")
            # the pickle can only hold a source it was built after
            at = min(x for x in (pickle_at, shared) if x) if (pickle_at or shared) else None
            vintage["fip_source_by_season"][str(s)] = {
                "source": "fa_corpus.pkl (the nightly re-read failed or came back short)",
                "at": at, "rows": have, "reread_rows": len(rows), "error": err}
    merged["pit"] = pit
    merged["league"] = league
    return merged, vintage


@contextlib.contextmanager
def _corpus_for_build(corpus: dict):
    """ewar.build reads the corpus through ewar._corpus(); serve it `corpus`."""
    orig = ewar._corpus
    ewar._corpus = lambda: corpus
    try:
        yield
    finally:
        ewar._corpus = orig


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path):
    """(text, payload) or (None, None) when absent or unreadable."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        return text, json.loads(text)
    except (OSError, ValueError):
        return None, None


def run_nightly(write: bool, today: _dt.date | None = None) -> int:
    """The daily step. Returns 0, or 2 when it refuses. A refusal leaves the best
    known artifact on disk: the carried nightly when one descends from the
    committed build, the committed file otherwise. It never raises SystemExit
    (ewar's input loaders do, on an unreadable data file) and never runs the
    full build."""
    today = today or _dt.date.today()
    out_path = Path(ewar.OUT)
    tracked_text, tracked = _read_json(out_path)
    if tracked is None:
        print(f"  NIGHTLY REFUSED: no readable {out_path}; the nightly only carries a built "
              f"artifact forward. Build it by hand: {war_source.EWAR_BUILD_CMD}, then the "
              f"runbook cascade.")
        return 2
    carried_text, carried = _read_json(CARRY_PATH)
    prev, base, notes = choose_base(tracked, carried)
    for n in notes:
        print(f"  {n}")
    if base == "carried" and write and carried_text != tracked_text:
        # serve the last good nightly while tonight's is priced: a refusal or a
        # crash below leaves it on disk, not the committed hand build
        _write_atomic(out_path, carried_text)
        ewar._CACHE = None
        print(f"  restored the carried nightly (live season built "
              f"{war_source.ewar_cadence(carried).get('live_built_at')}) over the committed file")
    try:
        return _run_nightly_body(prev, base, write, today)
    except SystemExit as exc:
        print(f"  NIGHTLY REFUSED: the build stopped on an input ({exc}); "
              f"{out_path.name} keeps the {base} artifact")
        return 2


def _run_nightly_body(prev: dict, base: str, write: bool, today: _dt.date) -> int:
    import pandas as pd                   # noqa: PLC0415
    with _frames_from_war_source() as (bat, pit, frames):
        if frames["served_stale"]:
            print(f"  NIGHTLY REFUSED: war_daily came from the last-good cache "
                  f"({frames['served_stale']}); pricing the live season on it could move it "
                  f"backwards. The {base} artifact stays.")
            return 2
        have = set(pd.to_numeric(pit["year_ID"], errors="coerce").dropna().astype(int)) \
            | set(pd.to_numeric(bat["year_ID"], errors="coerce").dropna().astype(int))
        plan = nightly_plan(prev, today, have)
        print(f"eWAR nightly {today} (from the {base} artifact): frozen "
              f"{plan['frozen_before'][:1]}..{plan['frozen_before'][-1:]} "
              f"({len(plan['frozen_before'])} seasons), rebuild {plan['rebuild']}, "
              f"freeze now {plan['freeze_now']}, live {plan['live']}")
        if not plan["rebuild"]:
            print("  nothing to re-price: every season of the window is frozen and no "
                  "new season has begun; the artifact on disk is left as it is")
            return 0
        corpus, fip_vintage = live_fip_corpus(plan["rebuild"])
        frames["fip"] = fip_vintage
        focus = plan["live"] if plan["live"] is not None else max(plan["rebuild"])
        frames["fip_source_at"] = (fip_vintage["fip_source_by_season"].get(str(focus)) or {}).get("at")
        frames["standings_at"] = _warm_standings(focus)
        regress = input_regressions(prev, frames, plan)
        if regress:
            for r in regress:
                print(f"  NIGHTLY REFUSED: {r}")
            return 2
        rebuilt = {}
        with _corpus_for_build(corpus):
            for s in plan["rebuild"]:
                model = ewar.build(first=s, last=s, shrink=True)
                rebuilt[s] = json.loads(json.dumps(ewar.export_payload(model)))
    now_iso = _dt.datetime.now().isoformat(timespec="seconds")
    new = merge_nightly(prev, rebuilt, plan, now_iso=now_iso, frames=frames)
    problems = check_nightly(prev, new, plan)
    for k, v in _move_report(prev, new, plan["rebuild"]).items():
        print(f"  {k}: blocks {v['blocks_before']} -> {v['blocks_after']} "
              f"(+{v['added']} -{v['removed']}), changed {v['blocks_changed']}, "
              f"eWAR changed {v['ew_changed']}, pitcher side changed {v['ewp_changed']}, "
              f"max |change| {v['max_abs_ew_change']}")
    scale = new["meta"]["cadence"].get("live_replacement_scale")
    if scale is not None and not (LIVE_SCALE_BAND[0] <= float(scale) <= LIVE_SCALE_BAND[1]):
        print(f"  WARNING live replacement scale {scale} outside {LIVE_SCALE_BAND}: the "
              f"war_daily pull and the standings blob are from different days")
    if problems:
        for p in problems:
            print(f"  NIGHTLY REFUSED: {p}")
        return 2
    status = war_source.ewar_cadence_status(new, today)
    print(f"  cadence status ok={status['ok']} problems={status['problems']}")
    if write:
        text = json.dumps(new, separators=(",", ":"))
        _write_atomic(Path(ewar.OUT), text)
        _write_atomic(CARRY_PATH, text)
        ewar._CACHE = None
        print(f"  wrote {ewar.OUT} ({Path(ewar.OUT).stat().st_size / 1e6:.2f} MB) and its "
              f"carried copy; data/ewar_eval.json untouched")
    else:
        print("  (dry run; pass --write to write data/ewar.json)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=LABEL_FIRST_SEASON,
                    help="first BUILT season (default 2011, the label window)")
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--write", action="store_true", help="write both artifacts")
    ap.add_argument("--force-fetch", action="store_true",
                    help="bypass the local bwar pickle cache")
    ap.add_argument("--no-sensitivity", action="store_true",
                    help="skip the unshrunk-fielding sensitivity build")
    ap.add_argument("--eval-first", type=int, default=ewar.DEFAULT_FIRST_SEASON,
                    help="first season the GATES score (default 2016, the OAA "
                         "era the shipped gate record was measured on)")
    ap.add_argument("--eval-last", type=int, default=None,
                    help="last COMPLETED season for the gates (default: last year)")
    ap.add_argument("--nightly", action="store_true",
                    help="the daily step: re-price the live season only, carry every "
                         "completed season forward byte for byte, write data/ewar.json only")
    args = ap.parse_args()
    if args.nightly:
        return run_nightly(write=args.write)
    if args.eval_first < args.first:
        ap.error(f"--eval-first {args.eval_first} precedes --first {args.first}; "
                 f"the gates cannot score seasons that were not built")

    model = ewar.build(first=args.first, last=args.last,
                       shrink=True, force_fetch=args.force_fetch)
    print(f"eWAR v2: {len(model['rows'])} war_daily rows, "
          f"seasons {model['meta']['seasons']}")

    unshrunk, arms = None, None
    if not args.no_sensitivity:
        # AT w=1.0 EXPLICITLY, for the same reason fielding_swap_only is, and
        # this line got the trap the comment below was written about. The OAA
        # reliability shrinkage multiplies the STATCAST fielding term; at the
        # shipped w of 0.0 that term is multiplied by zero, so an unshrunk build
        # at the default is bit-identical to the shipped build and the whole
        # sensitivity block reproduced gate 1 to the last decimal while claiming
        # to test something. Verified: r 0.8595 / mae0 4.306 in BOTH arms.
        # The shrinkage question only exists where the Statcast read is used.
        unshrunk = ewar.build(first=args.first, last=args.last, shrink=False,
                              fielding_blend_w=1.0)
        arms = {
            # AT w=1.0 EXPLICITLY. The shipped default became 0.0 on 2026-08-04
            # (the w grid found both forward legs monotone decreasing in w), so
            # an arm built at the default would apply no Statcast fielding at
            # all and come back as bWAR wearing the label "fielding_swap_only".
            # That reads as "the fielding swap is fine now" and is the exact
            # opposite of what was measured. This arm exists to answer "what
            # does the Statcast fielding swap DO", so it must ask at full
            # strength regardless of what the default happens to be.
            "fielding_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_pitching=False,
                                             fielding_blend_w=1.0),
            "pitching_swap_only": ewar.build(first=args.first, last=args.last,
                                             swap_fielding=False),
        }

    ev = ewar.evaluate(model, unshrunk, first=args.eval_first,
                       last=args.eval_last, arms=arms)
    # The gates are windowed (eval_window). The accounting identity has to hold
    # on every season the artifact SERVES, so it is also run on the whole build
    # and written beside the windowed block under its own key.
    ev["accounting_league_sum_build_window"] = {
        "build_window": list(model["meta"]["seasons"]),
        "why": "eval_window scores the gates; this block checks the league-sum "
               "identity on every built season, including the pre-2016 label "
               "seasons the gates do not score. The in-progress last season "
               "is scaled against season-to-date team-games, so its "
               "replacement_scale reads near 1.0 only when the war_daily pull "
               "and the standings blob are from the same day (2026-09-03: "
               "0.9997 fresh, 1.2672 with an Aug 4 pull against a Sep 3 "
               "blob). A scale far from 1.0 there says refresh the pull; it "
               "is not a break in the identity.",
        **ewar.gate_league_sum(model),
    }
    print(_fmt_gate1(ev["gate_1_team_wins"]))
    print(_fmt_gate2(ev["gate_2_pitcher_persistence"]))
    print(_fmt_gate3(ev["gate_3_coverage_identity"]))
    print(_fmt_sum(ev["accounting_league_sum"],
                   f"league WAR sum per season, gate window {ev['eval_window']}"))
    print(_fmt_sum(ev["accounting_league_sum_build_window"],
                   f"league WAR sum per season, build window {model['meta']['seasons']}"))
    if "attribution_gate_1" in ev:
        a = ev["attribution_gate_1"]
        print("  ATTRIBUTION (gate 1, same rows)")
        for label in ("bwar_baseline", "fielding_swap_only",
                      "pitching_swap_only", "both_swaps_shipped"):
            blk = a.get(label) or {}
            print(f"    {label:<20} r {blk.get('r')}   "
                  f"MAE0 {blk.get('mae_zero_param')}   "
                  f"next-season r {blk.get('next_season_r')}")
    n = (ev["gate_1_team_wins"].get("next_season_wins") or {})
    if n:
        print(f"  NEXT-SEASON WINS  n={n['n']}  eWAR {n['r_ewar']:+.4f}   "
              f"bWAR {n['r_bwar']:+.4f}")
    if unshrunk is not None:
        s = ev["sensitivity_unshrunk_fielding"]["gate_1_team_wins"]
        print(f"  SENSITIVITY unshrunk fielding: gate 1 r {s['ewar']['r']:+.4f} "
              f"(shipped shrunk {ev['gate_1_team_wins']['ewar']['r']:+.4f}, "
              f"bWAR {s['bwar']['r']:+.4f})")
    print(f"  gates passed: {len(ev['gates_passed'])}, "
          f"failed: {len(ev['gates_failed'])}")
    for line in ev["gates_failed"]:
        print(f"    FAILED  {line}")

    payload = ewar.export_payload(model)
    print(_fmt_build(model, payload))
    print(f"  artifact: {payload['n_player_seasons']} player-seasons")
    if args.write:
        ewar.OUT.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        ewar.EVAL_OUT.write_text(json.dumps(ev, indent=1), encoding="utf-8")
        print(f"  wrote {ewar.OUT.relative_to(ROOT)} "
              f"({ewar.OUT.stat().st_size / 1e6:.2f} MB)")
        print(f"  wrote {ewar.EVAL_OUT.relative_to(ROOT)} "
              f"({ewar.EVAL_OUT.stat().st_size / 1e3:.1f} KB)")
    else:
        print("  (dry run; pass --write to commit the artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
