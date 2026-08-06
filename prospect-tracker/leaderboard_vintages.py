# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""leaderboard_vintages.py - dated snapshots of the team inputs the betting
model consumes, so a game can be priced on numbers that were true BEFORE it.

THE PROBLEM THIS EXISTS TO SOLVE. `betting_model` reads the team leaderboards
(offense_plus, rotation_plus, bullpen_plus, per-pitcher SEM+/REM+) and the park
index. Those are SEASON-TO-DATE aggregates. Grading a June game against them means the features
already contain that June game's result. The forward split in `backtest()`
refits the coefficients on an earlier window, which removes COEFFICIENT
leakage, but the features stay contaminated. That is the single reason
/betting/ ships with `min_edge: null` and no pick of the day.

There is no way to reconstruct what the leaderboards said on 2026-05-14. The
leaderboards are a full recompute over the season to date; nothing keeps the
intermediate states. So the fix is not a backfill, it is a CLOCK: start
writing down what the inputs say each night, and wait. A game on date D is
then priced on the newest snapshot whose knowledge cutoff is strictly before
D, and nothing that happened on or after D can reach it.

THE STORE: ONE FILE PER DATE, under .cache/, never in git.

  .cache/leaderboard_vintages/2026-08-05.json      ~24 KB
  .cache/leaderboard_vintages/2026-08-06.json      ~24 KB

Three decisions, each for a reason:

  ONE FILE PER DATE, not a single file keyed by date. A single keyed file is
  rewritten in full every night, so one bad write costs the entire archive.
  Per-date files cost one night. The archive is evidence that cannot be
  regenerated, so the failure mode that loses all of it is the one to design
  out. Measured at 24.4 KB per night compact (30 teams, ~690 pitchers), a
  180-night season is ~4.4 MB. That is small enough that nothing clever is
  needed on top.

  UNDER .cache/, NOT data/. `deploy/nightly-build.sh` runs `git checkout -- .`
  before every pull, which reverts every TRACKED file the pipeline wrote. A
  tracked vintage store would therefore be destroyed each night and would only
  ever hold the most recent run. .cache/ is the box-persistent, gitignored
  state the deploy README already names (alongside prospects.db). The archive
  accumulates there and survives. The cost is that it lives on one box: see
  the runbook in docs/diamond-betting.md for the backup note.

  FIRST WRITE WINS. Re-running on a date that already has a file is a no-op
  that returns the existing record. A snapshot is evidence behind a claim
  about what was knowable; letting a later run overwrite it would let a
  better-informed copy replace a less-informed one, which is exactly the
  leakage this module removes. `force=True` exists for a repair and says so in
  the log.

THE KNOWLEDGE CUTOFF, which is the whole safety property. Each record carries
`covers_through` = max(the source leaderboards' own `as_of` dates, the date
the snapshot was written). A record is eligible to price a game on date D only
when `covers_through < D`. Using the WRITE date in that max is deliberately
conservative: a file written on 2026-08-05 cannot prove it excludes games
played on 2026-08-05, so the earliest game it may price is 2026-08-06. With a
nightly snapshot that costs nothing in steady state (a game on D uses the
snapshot from D-1); without one it is the difference between an honest
backtest and a dishonest one.

WHAT A RECORD HOLDS: the three team columns, the per-pitcher columns, and (from
schema 2) the PARK INDEX. The park was the one model input that was never dated,
and betting_model read the live one for vintage games; see PARK_SOURCE below for
the leak and why no backfill is needed. `parks` is null on schema 1 records and
the reader must price those games on a neutral park, not on today's index.

ORG CODES ARE CANONICALIZED AT WRITE TIME. The leaderboards carry StatsAPI
abbreviations (SD, SF, TB, KC, AZ, CWS, WSH); park factors and the game feeds
carry the Baseball-Reference set (SDP, SFG, TBR, KCR, ARI, CHW, WSN). Every
key in a stored record has already been through `trades.canonical_org`, so a
reader joins directly and cannot silently drop eight clubs.

CLI:
    python leaderboard_vintages.py --snapshot     # write tonight's vintage
    python leaderboard_vintages.py --coverage     # how far from an honest grade
    python leaderboard_vintages.py --as-of 2026-08-07
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("leaderboard_vintages")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
VINTAGE_DIR = ROOT / ".cache" / "leaderboard_vintages"

# SCHEMA 2 (2026-08-05) added the `parks` block. See PARK_SOURCE below for why:
# schema 1 records carry no park column at all, and a reader must fall back to a
# NEUTRAL park for them rather than to the live index.
SCHEMA = 2

# The reduced record keeps only what betting_model actually consumes. Column
# order is part of the on-disk contract; a reader must go through
# team_row()/pitcher_row() rather than index into the arrays by hand.
TEAM_COLUMNS = ("offense_plus", "rotation_plus", "bullpen_plus",
                "starter_ip", "relief_ip")
PITCHER_COLUMNS = ("plus", "ip_per_gs", "org", "role")

SOURCES = ("hitter_leaderboards.json", "starter_leaderboards.json",
           "bullpen_leaderboards.json")

# THE FOURTH INPUT, and the one that was leaking (2026-08-05).
#
# betting_model prices a game on four things: team offense, team run prevention,
# the listed probable, and THE PARK. The first three were vintage-dated by this
# module from day one; the park was not, so `backtest()` in vintage mode read
# `park_index()` -> data/fa_meta.json -> `fa_fit.park_factors(CLASS_YEAR - 1)`,
# which is the IN-PROGRESS season. Every eval-window game therefore contributed
# to the park index used to fit and to price it, while the mode label claimed
# "features dated strictly before each game; no leakage". One input made that
# false, and the contamination grows with the 600-game validation clock rather
# than shrinking, because a longer eval window is a larger share of the park
# sample it is graded against.
#
# NO BACKFILL IS NEEDED and none is possible. Park factors are near-static
# inside a season (they are a multi-year regressed index the FA engine rebuilds
# monthly, not a daily aggregate), so tonight's value is a fair reading of what
# was knowable last night. Records written before this schema bump simply have
# no park column, and betting_model prices them on a NEUTRAL park and marks the
# games, which is the conservative direction: it drops the park term rather than
# inventing a dated one.
PARK_SOURCE = "fa_meta.json park_factors"
PARK_UNITS = "runs index / 100 (1.00 = neutral), the same units betting_model.park_index returns"


# ---------------------------------------------------------------------------
# io helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _org(name: str | None) -> str | None:
    """StatsAPI or BBRef team code -> the canonical 3-letter org. See the
    module docstring: mixing the two code sets silently drops eight clubs."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def _today() -> str:
    return date.today().isoformat()


def _iso_date(s) -> str | None:
    """Anything date-shaped -> 'YYYY-MM-DD', or None. Tolerates a full ISO
    timestamp, which is what some leaderboard `generated_at` fields carry."""
    if not s:
        return None
    t = str(s).strip()
    if len(t) >= 10 and t[4] == "-" and t[7] == "-":
        head = t[:10]
        try:
            datetime.strptime(head, "%Y-%m-%d")
        except ValueError:
            return None
        return head
    return None


def park_snapshot(data_dir: Path | None = None) -> dict | None:
    """{canonical org: runs index / 100} for the record, or None.

    NONE IS A SENTINEL AND AN EMPTY DICT IS FORBIDDEN. `{}` would be written to
    disk, read back as "these are the parks", and price every game at a flat
    1.00 while being indistinguishable from a genuinely neutral league. None
    says "this record has no park column", which is exactly what the reader
    needs in order to fall back explicitly and mark the games it affected.
    Missing a park does NOT make the whole block None: `betting_model` already
    resolves an absent org to neutral at lookup (ATH has no Savant entry), and
    dropping 29 measured parks over the 30th would be the same mistake in
    reverse."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    meta = _load_json(dd / "fa_meta.json")
    pf = (meta or {}).get("park_factors") if isinstance(meta, dict) else None
    if not isinstance(pf, dict) or not pf:
        return None
    out: dict[str, float] = {}
    for org, v in pf.items():
        o = _org(org)
        if not o or not isinstance(v, dict):
            continue
        try:
            out[o] = round(float(v.get("runs") or 100) / 100.0, 4)
        except (TypeError, ValueError):
            continue
    return out or None


# ---------------------------------------------------------------------------
# reduce the live leaderboards to a record
# ---------------------------------------------------------------------------
def reduce_current(*, on_date: str | None = None, data_dir: Path | None = None) -> dict | None:
    """The live leaderboards, reduced to the fields the betting model reads.

    None when the leaderboards are absent or do not cover all three sides,
    because a half-populated vintage is worse than no vintage: it would be
    silently eligible to price games and would price them on a broken
    prevention blend."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    vintage_date = on_date or _today()

    src_meta, blobs = {}, {}
    for name in SOURCES:
        d = _load_json(dd / name)
        if not isinstance(d, dict):
            return None
        blobs[name] = d
        # `as_of` is stamped with TODAY on every write, including a write that
        # kept the previous run's block because this run produced nothing. So
        # as_of alone cannot tell a fresh board from a carried-over one, and a
        # staleness check built on it would never fire. The boards record the
        # honest signal separately, in team_rollup, and that is what gets
        # carried into the vintage.
        _roll = d.get("team_rollup") if isinstance(d.get("team_rollup"), dict) else {}
        src_meta[name] = {
            "as_of": _iso_date(d.get("as_of")) or _iso_date(d.get("generated_at")),
            "season": str(d.get("season") or "") or None,
            "stale": bool(_roll.get("stale")),
            "kept_from": _roll.get("kept_from"),
        }

    hit = blobs["hitter_leaderboards.json"]
    rot = blobs["starter_leaderboards.json"]
    pen = blobs["bullpen_leaderboards.json"]

    teams: dict[str, list] = {}

    def _slot(org: str) -> list:
        return teams.setdefault(org, [None] * len(TEAM_COLUMNS))

    for t in hit.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("offense_plus") is not None:
            _slot(o)[0] = round(float(t["offense_plus"]), 3)
    for t in rot.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("rotation_plus") is not None:
            row = _slot(o)
            row[1] = round(float(t["rotation_plus"]), 3)
            row[3] = round(float(t.get("starter_ip") or 0.0), 1)
    for t in pen.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("bullpen_plus") is not None:
            row = _slot(o)
            row[2] = round(float(t["bullpen_plus"]), 3)
            row[4] = round(float(t.get("relief_ip") or 0.0), 1)

    # A club missing any of the three sides is dropped rather than defaulted.
    # betting_model.team_inputs already intersects the three leaderboards; the
    # vintage must not be more permissive than the live path or a backtest
    # would grade games the live model would refuse to price.
    teams = {o: r for o, r in teams.items()
             if r[0] is not None and r[1] is not None and r[2] is not None}
    if not teams:
        return None

    pitchers: dict[str, list] = {}
    for r in rot.get("starters") or []:
        mid, plus = r.get("mlbam"), r.get("sem_plus")
        if not mid or plus is None:
            continue
        ipgs = r.get("ip_per_gs")
        pitchers[str(int(mid))] = [
            round(float(plus), 3),
            round(float(ipgs), 3) if ipgs else None,
            _org(r.get("team")),
            r.get("role") or "SP",
        ]
    for r in pen.get("relievers") or []:
        mid, plus = r.get("mlbam"), r.get("rem_plus")
        if not mid or plus is None or str(int(mid)) in pitchers:
            continue
        # REM+ is on the same 100/10z scale as SEM+, which is what lets the
        # prevention blend treat an opener the same way it treats a starter.
        pitchers[str(int(mid))] = [round(float(plus), 3), None,
                                   _org(r.get("team")), "RP"]

    as_ofs = [m["as_of"] for m in src_meta.values() if m["as_of"]]
    covers_through = max(as_ofs + [vintage_date])

    # An absent park index does NOT abort the snapshot. The team and pitcher
    # columns are the irreplaceable evidence (they cannot be reconstructed for a
    # past date at all); parks are near-static, so a night without them costs a
    # neutral park term on the games that read this record and nothing else. The
    # reader is told which it got by the presence of the block, never by a zero.
    parks = park_snapshot(data_dir=dd)
    if parks is None:
        log.warning("leaderboard_vintages: no park factors in %s/fa_meta.json; the %s "
                    "vintage is stored WITHOUT a park column and games priced on it "
                    "will use a neutral park", dd, vintage_date)

    return {
        "schema": SCHEMA,
        "vintage_date": vintage_date,
        "covers_through": covers_through,
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "season": src_meta["hitter_leaderboards.json"]["season"],
        "org_codes": "canonical (trades.canonical_org)",
        "team_columns": list(TEAM_COLUMNS),
        "pitcher_columns": list(PITCHER_COLUMNS),
        "sources": src_meta,
        "n_teams": len(teams),
        "n_pitchers": len(pitchers),
        "n_parks": len(parks) if parks else 0,
        "teams": teams,
        "pitchers": pitchers,
        "parks": parks,
        "park_source": PARK_SOURCE if parks else None,
        "park_units": PARK_UNITS,
        "cutoff_note": ("covers_through is the max of the source leaderboards' as_of "
                        "dates and the date this file was written; a record may price "
                        "only games dated strictly after it"),
        "park_note": ("parks is null on schema 1 records and on any night fa_meta.json "
                      "was unreadable; a reader must price those games on a NEUTRAL "
                      "park and mark them, never on the live index"),
    }


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------
def vintage_path(on_date: str, *, vintage_dir: Path | None = None) -> Path:
    return (Path(vintage_dir) if vintage_dir else VINTAGE_DIR) / f"{on_date}.json"


def snapshot(*, on_date: str | None = None, force: bool = False,
             vintage_dir: Path | None = None, data_dir: Path | None = None,
             log_fn=None) -> dict:
    """Write one dated vintage. IDEMPOTENT: a date that already has a file is
    a no-op returning the record on disk.

    Returns {"written": bool, "path": str, "date": ..., "record": {...}} or a
    {"written": False, "reason": ...} when the leaderboards cannot be reduced.
    Never raises into the pipeline."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    d = on_date or _today()
    path = vintage_path(d, vintage_dir=vdir)

    if path.exists() and not force:
        rec = _load_json(path)
        if isinstance(rec, dict):
            if log_fn:
                log_fn(f"leaderboard_vintages: {d} already captured "
                       f"(covers_through {rec.get('covers_through')}), no-op")
            return {"written": False, "path": str(path), "date": d,
                    "reason": "already captured", "record": rec}
        # Unreadable file: treat as absent and rewrite, since an unparseable
        # vintage is not evidence of anything.
        if log_fn:
            log_fn(f"leaderboard_vintages: {path.name} is unreadable, rewriting")

    rec = reduce_current(on_date=d, data_dir=data_dir)
    if not rec:
        if log_fn:
            log_fn("leaderboard_vintages: leaderboards absent or incomplete, "
                   "nothing captured")
        return {"written": False, "path": str(path), "date": d,
                "reason": "leaderboards absent or incomplete", "record": None}

    # STALE SOURCE WARNING. covers_through is a MAX over the three source as_of
    # dates and today's write date, so a board that failed to rebuild is frozen
    # at an old as_of while the record still gets stamped with tonight's date.
    # That is safe in the leakage direction, since the snapshot then knows LESS
    # than its stamp claims and can never see the future. It is not safe for
    # quality: the model would price tonight's games on a month-old view of the
    # league, on the input it weights most, and the coverage report would call
    # the archive perfectly healthy because it counts files and dates.
    #
    # So name it. A vintage whose sources lag its own date is a degraded
    # vintage, and the only way anyone finds out is if it says so.
    # Two ways a source can be behind, and as_of only catches the first:
    #   1. the file was not rewritten at all, so its as_of really is older
    #   2. the export ran, produced nothing, and KEPT the previous block while
    #      stamping as_of with today. team_rollup.stale is the only witness.
    _lagging = {
        name: (m.get("kept_from") or m.get("as_of"))
        for name, m in (rec.get("sources") or {}).items()
        # `d` is snapshot()'s vintage date. `vintage_date` is reduce_current's
        # local and does not exist here; using it raised NameError inside a
        # best-effort pipeline step, which would have swallowed it silently.
        if m.get("stale") or (m.get("as_of") and m["as_of"] < d)
    }
    if _lagging:
        log.warning(
            "leaderboard_vintages: %s is being written with STALE sources %s. "
            "Its covers_through will still read %s, so games priced on it get a "
            "current-looking stamp over an older view of the league. Check that "
            "run_daily step 9e-pre0 rebuilt the boards.",
            path.name, _lagging, rec.get("covers_through"))
        rec["stale_sources"] = _lagging

    vdir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    reset_cache()
    if log_fn and _lagging:
        log_fn(f"leaderboard_vintages: WARNING {path.name} has stale sources "
               f"{_lagging}; the vintage is degraded, not fresh")
    if log_fn:
        # The park count is printed even when it is zero. "0 parks" in a nightly
        # log is the whole point of counting: a silent absence is what let the
        # vintage backtest read the live index for months.
        log_fn(f"leaderboard_vintages: wrote {path.name} "
               f"({rec['n_teams']} teams, {rec['n_pitchers']} pitchers, "
               f"{rec['n_parks']} parks, covers_through {rec['covers_through']})")
    return {"written": True, "path": str(path), "date": d, "record": rec}


# Read caches. A backtest resolves a vintage for every completed game, inside
# a solver that sweeps a grid: without these, the 96-file directory scan and
# the 25 KB JSON parse run tens of thousands of times and the backtest never
# finishes. Keyed by directory so a test pointing at a tmp dir is not served
# the production store. `reset_cache()` clears them; every write goes through
# `snapshot`, which clears them itself.
_INDEX_CACHE: dict[str, list[tuple[str, str]]] = {}
_REC_CACHE: dict[tuple[str, str], dict | None] = {}


def reset_cache() -> None:
    """Drop the memoized index and records. Call after writing a vintage
    outside `snapshot`, or when a test repoints the store."""
    _INDEX_CACHE.clear()
    _REC_CACHE.clear()


def vintage_dates(*, vintage_dir: Path | None = None) -> list[str]:
    """Every captured date, ascending. Filenames only; nothing is parsed."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    if not vdir.exists():
        return []
    out = []
    for p in vdir.glob("*.json"):
        d = _iso_date(p.stem)
        if d:
            out.append(d)
    return sorted(out)


def load_vintage(on_date: str, *, vintage_dir: Path | None = None) -> dict | None:
    key = (str(vintage_dir or VINTAGE_DIR), on_date)
    if key not in _REC_CACHE:
        rec = _load_json(vintage_path(on_date, vintage_dir=vintage_dir))
        _REC_CACHE[key] = rec if isinstance(rec, dict) else None
    return _REC_CACHE[key]


def _index(vintage_dir: Path | None = None) -> list[tuple[str, str]]:
    """[(covers_through, vintage_date)] for every readable record, ascending by
    cutoff. Built by reading the files: an index sidecar would be one more
    thing that can disagree with the archive it describes, and 180 x 24 KB is
    not worth defending against. Memoized, because the backtest asks for a
    vintage once per game per solver step."""
    key = str(vintage_dir or VINTAGE_DIR)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    out = []
    for d in vintage_dates(vintage_dir=vintage_dir):
        rec = load_vintage(d, vintage_dir=vintage_dir)
        if not rec:
            continue
        ct = _iso_date(rec.get("covers_through")) or d
        out.append((ct, d))
    out.sort()
    _INDEX_CACHE[key] = out
    return out


def as_of(on_date: str, *, vintage_dir: Path | None = None) -> dict | None:
    """The newest vintage whose knowledge cutoff is STRICTLY BEFORE `on_date`.

    None when no such vintage exists, which is every date until the nightly
    snapshot has been running for a while. Callers must treat None as "I have
    no honest features for this game" and say so; silently falling back to the
    live leaderboards is the leak this module was written to close, so the
    fallback lives in `betting_model.inputs_as_of` where it is flagged."""
    q = _iso_date(on_date)
    if not q:
        return None
    eligible = [(ct, d) for ct, d in _index(vintage_dir) if ct < q]
    if not eligible:
        return None
    return load_vintage(eligible[-1][1], vintage_dir=vintage_dir)


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------
def coverage(*, vintage_dir: Path | None = None) -> dict:
    """How much history the store holds, and where the holes are.

    `missing_dates` counts calendar days inside the captured span with no
    file. A hole is not fatal (a game just falls back to an older vintage,
    which is still strictly-before and therefore still honest) but a run of
    them means the nightly step is not firing."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    dates = vintage_dates(vintage_dir=vdir)
    total_bytes = 0
    for d in dates:
        try:
            total_bytes += vintage_path(d, vintage_dir=vdir).stat().st_size
        except OSError:
            pass
    # How many stored records actually carry a park column. A schema 1 record is
    # priced on a NEUTRAL park, so this is the number that says how much of the
    # archive can be graded with the park term switched on at all.
    n_with_parks = 0
    for d in dates:
        rec = load_vintage(d, vintage_dir=vdir)
        if rec and isinstance(rec.get("parks"), dict) and rec["parks"]:
            n_with_parks += 1
    out = {
        "dir": str(vdir),
        "schema": SCHEMA,
        "n_vintages": len(dates),
        "n_vintages_with_parks": n_with_parks,
        "n_vintages_neutral_park": len(dates) - n_with_parks,
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "bytes": total_bytes,
        "missing_dates": [],
        "earliest_gradable_game_date": None,
    }
    if not dates:
        out["note"] = ("no vintages captured yet; every backtest is contaminated "
                       "until the nightly snapshot has been running")
        return out
    d0 = datetime.strptime(dates[0], "%Y-%m-%d").date()
    d1 = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    have = set(dates)
    missing = []
    cur = d0
    while cur <= d1:
        s = cur.isoformat()
        if s not in have:
            missing.append(s)
        cur += timedelta(days=1)
    out["missing_dates"] = missing
    out["span_days"] = (d1 - d0).days + 1
    idx = _index(vdir)
    if idx:
        # The first game date any vintage can price: one day past the earliest
        # knowledge cutoff in the store.
        first_cut = datetime.strptime(idx[0][0], "%Y-%m-%d").date()
        out["earliest_gradable_game_date"] = (first_cut + timedelta(days=1)).isoformat()
        out["latest_cutoff"] = idx[-1][0]
    out["note"] = (f"{len(dates)} vintages, {len(missing)} missing days inside the span; "
                   "a game is gradable when a vintage cutoff is strictly before it")
    return out


def run(*, log_fn=None) -> dict:
    """Pipeline entry point. Never raises; the daily step wraps it anyway."""
    try:
        return snapshot(log_fn=log_fn)
    except Exception:                                            # pragma: no cover
        log.exception("leaderboard_vintages: snapshot failed")
        return {"written": False, "reason": "exception", "record": None}


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(
        description="Dated snapshots of the betting model's team inputs.")
    ap.add_argument("--snapshot", action="store_true", help="capture tonight's vintage")
    ap.add_argument("--force", action="store_true", help="overwrite an existing date")
    ap.add_argument("--date", default=None, help="stamp date (default: today)")
    ap.add_argument("--coverage", action="store_true", help="how much history exists")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="show the vintage a game on this date would be priced on")
    args = ap.parse_args()

    if args.snapshot:
        r = snapshot(on_date=args.date, force=args.force, log_fn=print)
        rec = r.get("record") or {}
        print(json.dumps({k: v for k, v in r.items() if k != "record"}, indent=1))
        if rec:
            print(f"  covers_through={rec.get('covers_through')} "
                  f"teams={rec.get('n_teams')} pitchers={rec.get('n_pitchers')}")
    if args.coverage:
        print(json.dumps(coverage(), indent=1))
    if args.as_of:
        rec = as_of(args.as_of)
        if not rec:
            print(f"no vintage strictly before {args.as_of}; a game that day cannot "
                  "be graded honestly")
        else:
            print(json.dumps({k: v for k, v in rec.items()
                              if k not in ("teams", "pitchers")}, indent=1))
