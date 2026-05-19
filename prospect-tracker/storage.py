"""
SQLite storage for the prospect tracker (v3).

Schema is append-only for snapshots; stat lines are upserted monthly.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from scrapers import Snapshot
from consensus import PlayerTimeseries, stock_movement
from stats import StatLine

DB_PATH = Path(__file__).parent / "prospects.db"

# Prospects whose most recent ranking update is older than this many months are
# classified as "inactive" rather than "active". They fell off prospect lists
# without ever being marked graduated — think Wander Franco (suspended) or
# players who quietly aged out of prospect status.
INACTIVE_MONTHS = 18


def _inactive_cutoff() -> date:
    """Return the date before which a player's last update makes them inactive."""
    today = date.today()
    m = today.month - INACTIVE_MONTHS % 12
    y = today.year - INACTIVE_MONTHS // 12
    if m <= 0:
        m += 12
        y -= 1
    try:
        return date(y, m, today.day)
    except ValueError:
        return date(y, m, 28)  # handle short months

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    interval_label  TEXT NOT NULL,
    player_key      TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    org             TEXT,
    rank            INTEGER,
    fv              REAL,
    status          TEXT NOT NULL,
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, interval_label, player_key)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_player ON snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS players (
    player_key   TEXT PRIMARY KEY,
    player_name  TEXT NOT NULL,
    position     TEXT,
    org          TEXT,
    birth_date   TEXT,                  -- ISO date 'YYYY-MM-DD'; immutable once known
    is_pitcher   INTEGER DEFAULT 0,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statlines (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pitch_arsenals (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized PitchArsenal dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sabermetrics (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized Sabermetrics dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS career_stats (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,       -- list of per-season stat rows (most recent first)
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS acquisitions (
    player_key   TEXT PRIMARY KEY,
    method       TEXT NOT NULL,       -- 'draft' | 'international_fa' | 'unknown'
    year         INTEGER,             -- draft year or IFA signing year
    round_label  TEXT,                -- '1', '2', 'CBA', 'CBB', etc.
    pick_round   INTEGER,             -- pick within the round
    pick_overall INTEGER,             -- overall pick number
    bonus_usd    INTEGER,             -- signing bonus in dollars
    team_name    TEXT,                -- drafting / signing team
    school       TEXT,                -- HS/college for draftees
    signing_date TEXT,                -- ISO date when known
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS il_status (
    player_key   TEXT PRIMARY KEY,
    is_on_il     INTEGER NOT NULL,    -- 0/1
    since        TEXT,                 -- ISO date of placement (retroactive when known)
    type         TEXT,                 -- '10-day', '15-day', '60-day', etc.
    description  TEXT,                 -- full transaction text from API
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_key       TEXT NOT NULL,
    trade_date       TEXT NOT NULL,
    from_org         TEXT,
    to_org           TEXT,
    source           TEXT NOT NULL,             -- 'mlb_api' | 'inferred'
    description      TEXT,
    date_range_start TEXT,
    date_range_end   TEXT,
    inserted_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_key, trade_date, source)
);
CREATE INDEX IF NOT EXISTS idx_trades_player ON trades(player_key);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    new_snapshots INTEGER DEFAULT 0,
    stat_lines    INTEGER DEFAULT 0,
    notes         TEXT
);
"""


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        # Migration: add birth_date column to existing players tables.
        # ALTER TABLE ADD COLUMN is a no-op on fresh DBs (column already
        # exists from the CREATE TABLE), but we catch the error if so.
        try:
            con.execute("ALTER TABLE players ADD COLUMN birth_date TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


def insert_snapshots(snapshots: Iterable[Snapshot]) -> int:
    count = 0
    with connect() as con:
        for s in snapshots:
            cur = con.execute(
                """INSERT OR IGNORE INTO snapshots
                   (source, snapshot_date, interval_label, player_key,
                    player_name, position, org, rank, fv, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s.source, s.snapshot_date, s.interval_label, s.player_key,
                 s.player_name, s.position, s.org, s.rank, s.fv, s.status),
            )
            count += cur.rowcount
            con.execute(
                """INSERT INTO players (player_key, player_name, position, org)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                       player_name = excluded.player_name,
                       position    = COALESCE(excluded.position, players.position),
                       org         = COALESCE(excluded.org, players.org),
                       updated_at  = datetime('now')""",
                (s.player_key, s.player_name, s.position, s.org),
            )
    return count


def auto_graduate_player(player_key: str, grad_date: str | None = None) -> None:
    """
    Mark a player as graduated by inserting a synthetic snapshot.

    grad_date — ISO date string for the graduation event (mlbDebutDate
                from the API). Falls back to today if not supplied.

    The pipeline uses the EARLIEST graduation-date snapshot it finds,
    so an accurate debut date here prevents spurious "graduated today"
    entries every run.
    """
    snap_date = grad_date or date.today().isoformat()
    with connect() as con:
        # Pull most recent metadata for this player
        row = con.execute(
            """SELECT player_name, position, org FROM snapshots
               WHERE player_key = ?
               ORDER BY snapshot_date DESC LIMIT 1""",
            (player_key,),
        ).fetchone()
        if not row:
            return
        # Insert the graduation snapshot; ignore if this exact row exists
        con.execute(
            """INSERT OR IGNORE INTO snapshots
               (player_key, player_name, source, snapshot_date, interval_label,
                position, org, rank, fv, status)
               VALUES (?, ?, 'auto_detect', ?, 'Auto-detected MLB debut',
                       ?, ?, NULL, NULL, 'graduated')""",
            (player_key, row["player_name"], snap_date,
             row["position"], row["org"]),
        )


def upsert_birth_date(player_key: str, birth_date: str,
                      overwrite: bool = False) -> None:
    """
    Set a player's birth_date.

    By default this is idempotent (only writes when currently NULL) so a
    one-time fetch wins and we never re-fetch unnecessarily. Pass
    overwrite=True when the caller has authoritative new data (e.g. the
    PlayerIndex just resolved a different MLBAM ID, making any existing
    birth date potentially stale).
    """
    if not birth_date:
        return
    with connect() as con:
        if overwrite:
            con.execute(
                """UPDATE players SET birth_date = ?, updated_at = datetime('now')
                   WHERE player_key = ?""",
                (birth_date, player_key),
            )
        else:
            con.execute(
                """UPDATE players SET birth_date = ?, updated_at = datetime('now')
                   WHERE player_key = ? AND (birth_date IS NULL OR birth_date = '')""",
                (birth_date, player_key),
            )


def load_birth_dates() -> dict[str, str]:
    """Return {player_key: 'YYYY-MM-DD'} for every player whose DOB we know."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, birth_date FROM players WHERE birth_date IS NOT NULL"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["birth_date"] for r in rows}


def upsert_statlines(statlines: dict[str, StatLine], season: int) -> int:
    n = 0
    with connect() as con:
        for key, sl in statlines.items():
            con.execute(
                """INSERT INTO statlines (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                       season       = excluded.season,
                       payload_json = excluded.payload_json,
                       fetched_at   = excluded.fetched_at""",
                (key, season, json.dumps(asdict(sl))),
            )
            n += 1
    return n


def insert_trades(trades) -> int:
    """Append-only insert; the UNIQUE constraint dedupes re-runs."""
    from trades import Trade
    n = 0
    with connect() as con:
        for t in trades:
            cur = con.execute(
                """INSERT OR IGNORE INTO trades
                   (player_key, trade_date, from_org, to_org, source,
                    description, date_range_start, date_range_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (t.player_key, t.trade_date, t.from_org, t.to_org,
                 t.source, t.description, t.date_range_start, t.date_range_end),
            )
            n += cur.rowcount
    return n


def load_trades() -> dict[str, list[dict]]:
    """{player_key: [trade_dict, ...]} sorted by trade_date asc."""
    by_player: dict[str, list[dict]] = {}
    with connect() as con:
        rows = con.execute(
            """SELECT player_key, trade_date, from_org, to_org, source,
                      description, date_range_start, date_range_end
               FROM trades ORDER BY player_key, trade_date"""
        ).fetchall()
    for r in rows:
        d = dict(r)
        by_player.setdefault(d["player_key"], []).append(d)
    return by_player


def load_all_snapshots() -> list[Snapshot]:
    with connect() as con:
        rows = con.execute(
            """SELECT source, snapshot_date, interval_label, player_key,
                      player_name, position, org, rank, fv, status
               FROM snapshots ORDER BY snapshot_date, source"""
        ).fetchall()
    return [Snapshot(**dict(r)) for r in rows]


def load_statlines() -> dict[str, dict]:
    with connect() as con:
        rows = con.execute("SELECT player_key, payload_json FROM statlines").fetchall()
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_pitch_arsenals(arsenals: dict[str, "PitchArsenal"], season: int) -> int:
    """Upsert pitch arsenal data. One row per player (most recent season wins)."""
    n = 0
    with connect() as con:
        for key, pa in arsenals.items():
            con.execute(
                """INSERT INTO pitch_arsenals (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(asdict(pa)), pa.fetched_at),
            )
            n += 1
    return n


def load_pitch_arsenals() -> dict[str, dict]:
    """Return {player_key: arsenal_dict} for all stored arsenals."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM pitch_arsenals"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_sabermetrics(metrics: dict[str, "Sabermetrics"], season: int) -> int:
    """Upsert sabermetrics (wRC+, xFIP, wOBA, FIP, ...). One row per player."""
    n = 0
    with connect() as con:
        for key, sm in metrics.items():
            con.execute(
                """INSERT INTO sabermetrics (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(asdict(sm)), sm.fetched_at),
            )
            n += 1
    return n


def load_sabermetrics() -> dict[str, dict]:
    """Return {player_key: metrics_dict} for all stored sabermetrics."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM sabermetrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_career_stats(career_by_player: dict[str, list[dict]]) -> int:
    """Upsert year-by-year career stats. One row per player."""
    n = 0
    with connect() as con:
        for key, rows in career_by_player.items():
            if not rows:
                continue
            con.execute(
                """INSERT INTO career_stats (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rows)),
            )
            n += 1
    return n


def load_career_stats() -> dict[str, list[dict]]:
    """Return {player_key: [season_rows]} for every stored career history."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM career_stats"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_acquisitions(by_key: dict[str, dict]) -> int:
    """Upsert acquisition rows. Each dict carries:
      method, year, round_label, pick_round, pick_overall, bonus_usd,
      team_name, school, signing_date (all optional except method).

    overwrite is the default — IFA inference + draft fetches both produce
    authoritative records that should replace any prior guess."""
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            con.execute(
                """INSERT INTO acquisitions
                     (player_key, method, year, round_label, pick_round,
                      pick_overall, bonus_usd, team_name, school, signing_date,
                      fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     method=excluded.method,
                     year=excluded.year,
                     round_label=excluded.round_label,
                     pick_round=excluded.pick_round,
                     pick_overall=excluded.pick_overall,
                     bonus_usd=excluded.bonus_usd,
                     team_name=excluded.team_name,
                     school=excluded.school,
                     signing_date=excluded.signing_date,
                     fetched_at=excluded.fetched_at""",
                (key, rec.get("method"), rec.get("year"),
                 rec.get("round_label"), rec.get("pick_round"),
                 rec.get("pick_overall"), rec.get("bonus_usd"),
                 rec.get("team_name"), rec.get("school"),
                 rec.get("signing_date")),
            )
            n += 1
    return n


def load_acquisitions() -> dict[str, dict]:
    """Return {player_key: acquisition_dict} for every prospect with one."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT player_key, method, year, round_label, pick_round,
                          pick_overall, bonus_usd, team_name, school, signing_date
                   FROM acquisitions"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: dict(r) for r in rows}


def upsert_il_status(by_key: dict[str, dict | None]) -> int:
    """Upsert IL status. Pass None as the value to clear a prior IL row
    (player came off IL since the previous run).

    Each non-None dict carries: is_on_il, since, type, description.
    """
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            if rec is None or not rec.get("is_on_il"):
                # Drop any prior row so a stale "on IL" badge doesn't
                # linger after activation.
                con.execute("DELETE FROM il_status WHERE player_key = ?", (key,))
                continue
            con.execute(
                """INSERT INTO il_status
                     (player_key, is_on_il, since, type, description, fetched_at)
                   VALUES (?, 1, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     is_on_il=1,
                     since=excluded.since,
                     type=excluded.type,
                     description=excluded.description,
                     fetched_at=excluded.fetched_at""",
                (key, rec.get("since"), rec.get("type"), rec.get("description")),
            )
            n += 1
    return n


def load_il_status() -> dict[str, dict]:
    """Return {player_key: il_dict} for every prospect currently on IL."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT player_key, is_on_il, since, type, description
                   FROM il_status WHERE is_on_il = 1"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: dict(r) for r in rows}


def load_career_stats_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for every stored career_stats row.

    Used by the monthly pipeline to TTL-skip refetching career stats for
    prospects whose cached row is still fresh.
    """
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM career_stats"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


def start_run() -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.utcnow().isoformat(timespec="seconds"),),
        )
        return cur.lastrowid


def finish_run(run_id: int, new_snapshots: int, stat_lines: int, notes: str = ""):
    with connect() as con:
        con.execute(
            """UPDATE runs SET finished_at = ?, new_snapshots = ?, stat_lines = ?, notes = ?
               WHERE id = ?""",
            (datetime.utcnow().isoformat(timespec="seconds"),
             new_snapshots, stat_lines, notes, run_id),
        )


def latest_run_summary() -> dict | None:
    try:
        with connect() as con:
            row = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist yet — fine for first run or test isolation.
        return None


def _build_org_fv_history(
    players: list[PlayerTimeseries],
    filter_real_trades,
    trades_by_player: dict[str, list[dict]],
) -> dict[str, dict]:
    """
    Build per-org cumulative FV time series + significant events.

    For each player, build a chronological event timeline of:
      - snapshot points (consensus_fv changes over time)
      - real trades (player moves between orgs)
      - graduation (player exits the system)

    Walk each timeline once and emit per-(org, date) deltas. After
    aggregating across all players, the running sum within each org
    produces the cumulative FV chart. Returns a dict keyed by canonical
    org code:

      {
        "ATL": {
          "series": [{"date": "2024-01-04", "total_fv": 240.5}, ...],
          "events": [{"date": "2024-07-30", "kind": "trade", "player_name":
                      "Drew Jones", "fv": 50.0, "other_org": "MIA"},
                     {"date": "2025-04-01", "kind": "graduation",
                      "player_name": "Spencer Schwellenbach", "fv": 55.0},
                      ...],
        },
        ...
      }

    Events power the indicator markers on the farm-system stock chart so
    each dip / spike has an explainable cause.
    """
    from trades import canonical_org
    from collections import defaultdict

    # contribs[(org, date)] = signed FV delta applied that day
    contribs: dict[tuple[str, str], float] = defaultdict(float)
    # events_by_org: list of (date, kind, player_name, fv, other_org)
    events_by_org: dict[str, list[dict]] = defaultdict(list)
    # Track every date any org sees a change so the time series isn't
    # collapsed to only dates where a player was added — graduations and
    # trades show up too.
    dates_by_org: dict[str, set[str]] = defaultdict(set)

    for p in players:
        if not p.points:
            continue
        sorted_points = sorted(p.points, key=lambda pt: pt.snapshot_date)

        # Pre-filter trades to the ones our chart actually surfaces (the
        # same set the prospect transaction history shows). Canonicalize
        # team codes so trade-attribution lines up with org_summary keys.
        raw_trades = trades_by_player.get(p.player_key, []) or []
        real_trades = filter_real_trades(raw_trades)
        trades = []
        for t in real_trades:
            d = t.get("trade_date")
            cf = canonical_org(t.get("from_org"))
            ct = canonical_org(t.get("to_org"))
            if not (d and cf and ct):
                continue
            trades.append({"date": d, "from": cf, "to": ct})
        trades.sort(key=lambda t: t["date"])

        # Initial org: pre-first-trade owner if any trade exists, else
        # the player's current org. Canonicalized to align with the keys
        # used in org_summary.
        current_org = canonical_org(p.org) if p.org else None
        initial_org = trades[0]["from"] if trades else current_org
        if not initial_org:
            continue

        # Merge snapshots + trades into one chronological stream. On a
        # date with both, apply snapshot first (the FV update reflects
        # the source's view as of the publication date), then the trade.
        # Each entry: (date, "snapshot", fv) | (date, "trade", from, to)
        stream: list[tuple] = []
        for pt in sorted_points:
            stream.append((pt.snapshot_date, "snapshot", pt.consensus_fv_raw))
        for t in trades:
            stream.append((t["date"], "trade", t["from"], t["to"]))
        if p.status == "graduated" and p.graduation_date:
            stream.append((p.graduation_date, "graduation"))
        # Stable sort: ties resolved by index in `stream` (snapshots first
        # because they're appended before trades).
        stream.sort(key=lambda x: x[0])

        org_now = initial_org
        fv_now = 0.0
        for ev in stream:
            d = ev[0]
            kind = ev[1]
            if kind == "snapshot":
                new_fv = ev[2]
                delta = new_fv - fv_now
                if delta != 0:
                    contribs[(org_now, d)] += delta
                    dates_by_org[org_now].add(d)
                fv_now = new_fv
            elif kind == "trade":
                from_org, to_org = ev[2], ev[3]
                # Move the player's current FV out of from_org into to_org
                # on the trade date. If from_org doesn't match our tracked
                # org_now (e.g. a stale inference), trust the API record
                # and adjust org_now to from_org first.
                source_org = org_now if org_now == from_org else from_org
                contribs[(source_org, d)] -= fv_now
                contribs[(to_org, d)]     += fv_now
                dates_by_org[source_org].add(d)
                dates_by_org[to_org].add(d)
                events_by_org[source_org].append({
                    "date": d, "kind": "trade", "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                    "other_org": to_org, "direction": "out",
                })
                events_by_org[to_org].append({
                    "date": d, "kind": "trade", "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                    "other_org": source_org, "direction": "in",
                })
                org_now = to_org
            elif kind == "graduation":
                # Removing the player's last FV from their current org —
                # graduates leave the system, so cumulative FV drops by
                # their FV on graduation day.
                contribs[(org_now, d)] -= fv_now
                dates_by_org[org_now].add(d)
                events_by_org[org_now].append({
                    "date": d, "kind": "graduation",
                    "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                })

    # Convert per-org contribs to running-sum series.
    result: dict[str, dict] = {}
    for org, dates in dates_by_org.items():
        running = 0.0
        series = []
        for d in sorted(dates):
            running += contribs[(org, d)]
            series.append({"date": d, "total_fv": round(running, 1)})
        # Drop leading zero-points so charts don't start with a flat line
        # before the org has any tracked prospects yet.
        first_nonzero = next((i for i, s in enumerate(series)
                              if s["total_fv"] > 0.01), 0)
        series = series[first_nonzero:]
        events = sorted(events_by_org.get(org, []),
                        key=lambda e: (e["date"], e["kind"]))
        result[org] = {"series": series, "events": events}
    return result


def export_timeseries_json(timeseries: list[PlayerTimeseries], out_path: Path,
                          statlines: dict[str, dict] | None = None,
                          pitch_arsenals: dict[str, dict] | None = None,
                          sabermetrics: dict[str, dict] | None = None,
                          trades_by_player: dict[str, list[dict]] | None = None,
                          career_stats: dict[str, list[dict]] | None = None,
                          acquisitions: dict[str, dict] | None = None,
                          il_status: dict[str, dict] | None = None,
                          rosters_by_org: dict[str, dict[str, list[dict]]] | None = None,
                          top_n_active: int | None = None):
    """
    Serialize for the front-end widget.

    Each player now carries:
      - statline      : slash line / ERA at the highest level this season
      - pitch_arsenal : pitch mix and velo for pitchers (may be None)
      - sabermetrics  : wRC+ / wOBA (hitters), xFIP / FIP / FIP- / ERA-
                        (pitchers). MLB-only coverage from the MLB Stats
                        API sabermetrics endpoint; None for prospects who
                        have not yet appeared in the majors. The UI falls
                        back to OPS+ (vs level) and ERA- (vs level) — the
                        `ops_plus_level` / `era_minus_level` fields on
                        `statline` — when sabermetrics aren't available.
      - trades        : list of trade events
      - career_stats  : year-by-year stats (most recent first), capped at
                        CAREER_SEASONS_KEPT and collapsed to highest level
                        per season. Drives the prospect detail page.
      - birth_date + age + age_vs_level
    """
    statlines = statlines or {}
    pitch_arsenals = pitch_arsenals or {}
    sabermetrics = sabermetrics or {}
    trades_by_player = trades_by_player or {}
    career_stats = career_stats or {}
    acquisitions = acquisitions or {}
    il_status = il_status or {}
    rosters_by_org = rosters_by_org or {}
    birth_dates = load_birth_dates()
    from stats import compute_age_decimal
    from age_level import score_age_vs_level
    from eta import estimate_eta
    from trades import canonical_org
    from level_norms import (
        compute_level_norms,
        age_baselines_from_norms,
        ops_norms_from_norms,
        era_norms_from_norms,
    )

    # Empirical level baselines computed from the career_stats payload we
    # already have. age_baselines / ops_norms / era_norms feed into the
    # per-player ETA + age-vs-level calls below.
    level_norms = compute_level_norms(career_stats, birth_dates)
    age_baselines = age_baselines_from_norms(level_norms)
    ops_norms = ops_norms_from_norms(level_norms)
    era_norms = era_norms_from_norms(level_norms)

    PITCHER_POS_SET = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}

    graduate_mlb_org_by_key: dict[str, str] = {}
    for org_code, levels in rosters_by_org.items():
        for rec in levels.get("MLB", []) or []:
            key = rec.get("player_key")
            if key:
                graduate_mlb_org_by_key[key] = org_code

    def _derived_graduation_date(p: PlayerTimeseries) -> str | None:
        """
        Display/sort graduation by actual MLB activity when we have it.

        Some historical players were auto-graduated by a later pipeline run,
        which inserted that run date as the snapshot date. For the front end,
        prefer the first MLB season in career_stats. If the stored date is an
        exact MLB-debut date from the same season, keep it.
        """
        rows = career_stats.get(p.player_key, []) or []
        mlb_years = sorted(
            int(r["season"]) for r in rows
            if r.get("level") == "MLB" and r.get("season")
        )
        if not mlb_years:
            return p.graduation_date
        first_year = mlb_years[0]
        if p.graduation_date and p.graduation_date.startswith(f"{first_year}-"):
            return p.graduation_date
        if first_year == date.today().year:
            return date.today().isoformat()
        return f"{first_year}-07-01"

    # Org rebrand pairs that look like cross-org trades but aren't —
    # the Athletics dropped their "Oakland" prefix mid-2024, which made
    # every prospect's snapshots flip OAK↔ATH and the inferred path
    # registered a fake trade for each.
    _REBRAND_PAIRS = {
        ("OAK", "ATH"),
        ("ATH", "OAK"),
    }

    # Verbs that signal a real inter-org player movement. Trades, waiver
    # claims, contract purchases, Rule 5 selections and free-agent signings
    # all qualify. Description must contain at least one to count as
    # "verified". Without this check we'd accept the API's affiliate
    # assignments (e.g. "Toronto Blue Jays optioned RHP Thomas Hatch to
    # Buffalo Bisons.") whenever Toronto's parent-org name happened to
    # canonicalize cleanly — those are intra-org moves, not trades.
    _REAL_TRADE_VERB_PATTERNS = (
        "traded ",                     # X traded ... — definitive
        " off waivers",                # waiver claim ("claimed Y off waivers from X")
        " on waivers",                 # claimed/awarded on waivers (rarer wording)
        "purchased the contract",      # contract purchase between orgs
        "signed as a free agent",      # FA signing (cross-org by definition)
        "returned to ",                # Rule 5 return
    )
    # Verbs that signal a non-trade event. Reject these even when from/to
    # canonicalize to different MLB codes, because the "to" team is usually
    # an affiliate or the player's movement is intra-org.
    _NON_TRADE_VERB_PATTERNS = (
        "optioned",
        "recalled",
        "designated for assignment",
        "selected the contract",       # MiLB→MLB promotion (intra-org)
        "sent outright",
        "sent on a rehab",
        "sent on a development",
        "assigned to",                 # affiliate move
        "activated",
        "reinstated",
        "placed on the",
    )

    def _is_real_trade(t: dict) -> bool:
        """
        True only for VERIFIED inter-org trades.

        Strict rules:
          - source='inferred': always False. Inferred org-changes are
            kept in the DB as a fallback but never displayed; we only
            surface trades the MLB transactions API confirms.
          - source='mlb_api':
              * Both from_org and to_org must canonicalize to distinct
                3-letter MLB codes (filters out affiliate ↔ parent moves).
              * Reject the OAK ↔ ATH rebrand pair.
              * Description (when present) must contain a real-trade verb
                pattern AND not contain any non-trade verb pattern.
        """
        if t.get("source") != "mlb_api":
            return False
        cf = canonical_org(t.get("from_org"))
        ct = canonical_org(t.get("to_org"))
        if not (cf and ct and cf != ct and len(cf) == 3 and len(ct) == 3):
            return False
        if (cf, ct) in _REBRAND_PAIRS:
            return False
        desc = (t.get("description") or "").lower()
        if not desc:
            # No description — accept the cross-org movement on its face,
            # though this path is rare (API normally provides text).
            return True
        if any(v in desc for v in _NON_TRADE_VERB_PATTERNS):
            return False
        return any(v in desc for v in _REAL_TRADE_VERB_PATTERNS)

    def _trade_pref_score(t: dict) -> int:
        """Higher = preferred when collapsing duplicates. Prefer mlb_api
        rows with a description (richest record), then any mlb_api,
        then inferred."""
        if t.get("source") == "mlb_api":
            return 2 if (t.get("description") or "") else 1
        return 0

    def _filter_real_trades(trades: list[dict]) -> list[dict]:
        """
        Collapse duplicate trade records to one entry per real trade event.

        Rule 1: When an API trade exists for a (canonical_from,
                canonical_to) pair, it supersedes any inferred trade with
                the same pair. API records carry the precise transaction
                date plus a description; the inferred path is a fallback
                that can produce stale entries from older snapshot
                evolutions and shouldn't compete once the real record
                arrives. (A genuine re-trade between the same orgs within
                the same season is extremely rare for prospects.)

        Rule 2: API records with identical (date, canonical_from,
                canonical_to) collapse to the richest entry — the one
                with a description, falling back to the earliest date.

        Rule 3: Inferred-only events within a (canonical_from, canonical_to)
                pair collapse on date-range overlap (the snapshot path
                often re-fires across pipeline runs as the snapshot
                history grows). Pick the EARLIEST trade_date in each
                cluster so the marker sits close to when the trade
                actually happened.
        """
        from datetime import date as _date
        from collections import defaultdict

        # Step 1: parse + filter to real trades.
        candidates: list[dict] = []
        for t in trades:
            if not _is_real_trade(t):
                continue
            try:
                td = _date.fromisoformat(t.get("trade_date", ""))
            except (TypeError, ValueError):
                continue
            try:
                rs = _date.fromisoformat(t.get("date_range_start") or "")
            except (TypeError, ValueError):
                rs = td
            try:
                re_ = _date.fromisoformat(t.get("date_range_end") or "")
            except (TypeError, ValueError):
                re_ = td
            candidates.append({
                "_t": t, "td": td, "rs": rs, "re": re_,
                "cf": canonical_org(t.get("from_org")),
                "ct": canonical_org(t.get("to_org")),
            })

        # Step 2: separate API and inferred per (cf, ct).
        api_by_pair: dict[tuple, list[dict]] = defaultdict(list)
        inferred_by_pair: dict[tuple, list[dict]] = defaultdict(list)
        for c in candidates:
            pair = (c["cf"], c["ct"])
            if c["_t"].get("source") == "mlb_api":
                api_by_pair[pair].append(c)
            else:
                inferred_by_pair[pair].append(c)

        chosen: list[dict] = []

        # Rule 1+2: per pair, if there are any API records, keep the best
        # one PER trade-date (API trade-dates are accurate, so distinct
        # dates within the same pair are distinct events).
        for pair, api_list in api_by_pair.items():
            by_date: dict[_date, dict] = {}
            for c in api_list:
                existing = by_date.get(c["td"])
                if existing is None:
                    by_date[c["td"]] = c
                else:
                    if _trade_pref_score(c["_t"]) > _trade_pref_score(existing["_t"]):
                        by_date[c["td"]] = c
            chosen.extend(by_date.values())

        # Rule 3: inferred-only events. Skip any (cf, ct) pair that
        # already has an API record (the API record wins outright).
        for pair, inf_list in inferred_by_pair.items():
            if pair in api_by_pair:
                continue
            # Interval-merge clusters on date_range overlap.
            inf_list.sort(key=lambda x: x["rs"])
            current: list[dict] = []
            current_end: _date | None = None
            clusters: list[list[dict]] = []
            for c in inf_list:
                if current and c["rs"] <= current_end:
                    current.append(c)
                    if c["re"] > current_end:
                        current_end = c["re"]
                else:
                    if current:
                        clusters.append(current)
                    current = [c]
                    current_end = c["re"]
            if current:
                clusters.append(current)
            for cluster in clusters:
                # Earliest trade_date wins.
                cluster.sort(key=lambda x: x["td"])
                chosen.append(cluster[0])

        chosen.sort(key=lambda x: x["td"])
        # Canonicalize from_org / to_org to 3-letter codes for display + the
        # farm-page filter on the front-end. Keep the full original strings
        # in `from_org_full` / `to_org_full` for the description context, and
        # leave the description text alone.
        out: list[dict] = []
        for c in chosen:
            t = dict(c["_t"])
            from_full = t.get("from_org")
            to_full = t.get("to_org")
            t["from_org_full"] = from_full
            t["to_org_full"] = to_full
            t["from_org"] = canonical_org(from_full)
            t["to_org"] = canonical_org(to_full)
            out.append(t)
        return out

    # Verb patterns that classify a trade-table entry into the discrete
    # acquisition methods the front-end filter offers. Order matters —
    # the first pattern that matches wins, so "off waivers" must beat
    # "traded" for waiver-claim transactions that include both verbs in
    # the description.
    _ACQUISITION_VERB_RULES = (
        (("off waivers", " on waivers", "claimed off waivers"),       "waiver"),
        (("purchased the contract", "purchase of the contract"),      "contract_purchase"),
        (("returned to ",),                                           "rule_5"),
        (("selected by",),                                            "rule_5"),
        (("signed as a free agent",),                                 "free_agent"),
        (("traded ",),                                                "trade"),
    )

    def _classify_current_acquisition(filtered_trades: list[dict],
                                      acquisition: dict | None) -> str:
        """How the player's CURRENT org acquired them.

        Returns one of: 'draft', 'international_fa', 'trade', 'waiver',
        'rule_5', 'free_agent', 'contract_purchase', 'unknown'.

        If there are no cross-org events, the answer is the player's
        original acquisition method (draft or IFA). Otherwise the most
        recent inter-org event's verb wins — that's what brought them to
        their current org. Trade description text drives the verb match
        because typeCode alone collapses too many move types onto "TR".
        """
        if not filtered_trades:
            if acquisition:
                m = acquisition.get("method")
                if m in ("draft", "international_fa"):
                    return m
            return "unknown"
        latest = max(filtered_trades, key=lambda t: t.get("trade_date") or "")
        desc = (latest.get("description") or "").lower()
        for patterns, kind in _ACQUISITION_VERB_RULES:
            if any(pat in desc for pat in patterns):
                return kind
        # Cross-org event with no recognized verb — fall back to "trade"
        # (typeCode TR is the dominant unclassified case).
        return "trade"

    def _serialize(p: PlayerTimeseries) -> dict:
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        sl = statlines.get(p.player_key)
        level = sl.get("level") if sl else None
        avl = score_age_vs_level(age, level, baselines=age_baselines)
        pa = pitch_arsenals.get(p.player_key)
        sm = sabermetrics.get(p.player_key)
        is_pitcher = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        latest_fv = p.points[-1].consensus_fv_raw if p.points else None
        eta = estimate_eta(
            level, age, is_pitcher, latest_fv, sl,
            expected_ages=age_baselines,
            ops_norm=ops_norms,
            era_norm=era_norms,
        )
        # Performance-vs-level-median enrichment. wRC+/xFIP aren't on the
        # MLB Stats API, so we compute their conceptual cousins from the
        # per-level baselines we already have:
        #   hitter : OPS+ = round(OPS / level_avg_ops * 100). >100 better.
        #   pitcher: ERA- = round(ERA / level_avg_era * 100). <100 better.
        # `level_plus_pct` is the same number expressed as a signed delta
        # (positive = good for either type) so the UI can drive color +
        # direction without re-branching on stat type.
        sl_out = dict(sl) if sl else None
        if sl_out:
            lvl = sl_out.get("level")
            norms_perf = (level_norms.get(lvl) or {}).get("perf") or {} if lvl else {}
            try:
                if sl_out.get("is_pitcher"):
                    era = float(sl_out.get("era")) if sl_out.get("era") else None
                    avg_era = norms_perf.get("avg_era")
                    if era and avg_era and era > 0:
                        era_minus = round(era / avg_era * 100)
                        sl_out["era_minus_level"] = era_minus
                        sl_out["level_plus_pct"] = round((avg_era - era) / avg_era * 100)
                else:
                    ops_str = sl_out.get("ops")
                    ops = float(ops_str) if ops_str else None
                    avg_ops = norms_perf.get("avg_ops")
                    if ops and avg_ops and avg_ops > 0:
                        ops_plus = round(ops / avg_ops * 100)
                        sl_out["ops_plus_level"] = ops_plus
                        sl_out["level_plus_pct"] = round((ops - avg_ops) / avg_ops * 100)
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        filtered_trades = _filter_real_trades(trades_by_player.get(p.player_key, []))
        acq = acquisitions.get(p.player_key)
        current_acq_method = _classify_current_acquisition(filtered_trades, acq)
        # Surface the specific trade that brought them to their current
        # org (when applicable). The detail page shows it as the
        # "Acquired by <ORG>" line; filters key on `method` only.
        current_acq_event = None
        if current_acq_method not in ("draft", "international_fa", "unknown"):
            latest = max(filtered_trades, key=lambda t: t.get("trade_date") or "") if filtered_trades else None
            if latest:
                current_acq_event = {
                    "date":        latest.get("trade_date"),
                    "from_org":    latest.get("from_org"),
                    "to_org":      latest.get("to_org"),
                    "description": latest.get("description"),
                }
        return {
            "player_key": p.player_key,
            "player_name": p.player_name,
            "position": p.position,
            "org": graduate_mlb_org_by_key.get(p.player_key, p.org) if p.status == "graduated" else p.org,
            "status": p.status,
            "graduation_date": _derived_graduation_date(p) if p.status == "graduated" else p.graduation_date,
            "birth_date": bd,
            "age": age,
            # Position in the FV-sorted active list, plus position within
            # the player's org. None for graduated/inactive (the maps below
            # only carry actives). Drives the rank pills on prospect detail.
            "overall_rank": overall_rank_by_key.get(p.player_key),
            "org_rank": org_rank_by_key.get(p.player_key),
            "org_rank_total": org_size_by_key.get(p.player_key),
            "age_vs_level": {"tier": avl.tier, "diff": avl.diff},
            "fv_high": p.fv_high,
            "fv_high_label": p.fv_high_label,
            "fv_high_date": p.fv_high_date,
            "fv_low": p.fv_low,
            "fv_low_label": p.fv_low_label,
            "fv_low_date": p.fv_low_date,
            "fv_open": p.fv_open,
            "fv_close": p.fv_close,
            "stock": stock_movement(p),
            "statline": sl_out,
            "pitch_arsenal": pa,
            "sabermetrics": sm,
            "trades": filtered_trades,
            "career_stats": career_stats.get(p.player_key, []),
            "acquisition": acq,
            # How the player's CURRENT org acquired them. Powers the
            # acquisition filter on the main prospect list + farm
            # detail roster, and the "Acquired by <ORG>" line on the
            # prospect detail page when distinct from the original
            # acquisition.
            "current_acquisition": {
                "method": current_acq_method,
                "event":  current_acq_event,
            },
            # Current IL stint, if any. Powers the IL badge on prospect
            # cards + the injury duration line on the detail page.
            # Empty dict (not None) when the player is healthy — the UI
            # treats `is_on_il` falsy as healthy regardless.
            "il_status": il_status.get(p.player_key, {}),
            "eta": {
                "year": eta.eta_year,
                "confidence": eta.confidence,
                "base_years": eta.base_years,
                "perf_adj": eta.perf_adj,
                "age_adj": eta.age_adj,
                "fv_adj": eta.fv_adj,
            },
            "points": [
                {
                    "snapshot_date": pt.snapshot_date,
                    "interval_label": pt.interval_label,
                    "consensus_fv": pt.consensus_fv,
                    "consensus_fv_label": pt.consensus_fv_label,
                    "consensus_fv_raw": pt.consensus_fv_raw,
                    "avg_rank": pt.avg_rank,
                    "avg_fv": pt.avg_fv,
                    "rank_implied_fv": pt.rank_implied_fv,
                    "sources_contributing": pt.sources_contributing,
                    "per_source": pt.per_source,
                }
                for pt in p.points
            ],
        }

    cutoff = _inactive_cutoff()

    # Reclassification rules:
    #   1. Status='graduated' from snapshots or auto-graduation → grads.
    #   2. On IL right now → stays active (badge tells the story).
    #   3. Both signals stale (FV cutoff + no games in current/previous
    #      calendar year):
    #        - any MLB game in current/previous year → grads (effective
    #          graduation we missed because rookie-threshold rule hasn't
    #          fired yet)
    #        - otherwise → inactives
    #   4. Anything else → active.
    # Without (2), legitimately-stale-due-to-injury prospects (Painter,
    # for example) would tumble into inactive — defeating the IL badge.
    today = date.today()
    play_cutoff_year = today.year - 1  # must have played current OR last year

    actives: list[PlayerTimeseries] = []
    inactives: list[PlayerTimeseries] = []
    grads: list[PlayerTimeseries] = []

    for p in timeseries:
        if p.status == "graduated":
            grads.append(p)
            continue
        if not p.points:
            inactives.append(p)
            continue
        try:
            latest_date = date.fromisoformat(p.points[-1].snapshot_date)
        except ValueError:
            inactives.append(p)
            continue

        # On IL → stay active no matter how stale the FV is. The IL badge
        # on the player card explains the absence of recent updates and
        # avoids dumping injured-but-real prospects into the inactive bin.
        if (il_status.get(p.player_key) or {}).get("is_on_il"):
            actives.append(p)
            continue

        fv_stale = latest_date < cutoff
        career = (career_stats or {}).get(p.player_key, []) or []
        last_played_year = max(
            (int(row.get("season") or 0) for row in career),
            default=0,
        )
        play_stale = last_played_year < play_cutoff_year
        recent_mlb = any(
            row.get("level") == "MLB"
            and int(row.get("season") or 0) >= play_cutoff_year
            for row in career
        )

        if fv_stale and play_stale:
            if recent_mlb:
                # Effective graduation — they're playing in the show but
                # our auto-graduation hasn't fired yet (sub-rookie-
                # threshold MLB time, or our run is between trips up).
                grads.append(p)
            else:
                inactives.append(p)
        else:
            actives.append(p)

    # Sort actives by latest consensus_fv_raw (smoother than the snapped value
    # for tiebreaking), then by latest avg_rank ascending as secondary key.
    def _active_key(p: PlayerTimeseries):
        latest = p.points[-1]
        rank_key = latest.avg_rank if latest.avg_rank is not None else 999
        return (-latest.consensus_fv_raw, rank_key)
    actives.sort(key=_active_key)
    if top_n_active is not None:
        actives = actives[:top_n_active]

    # Pre-compute overall_rank (position in the FV-sorted active list) and
    # org_rank (position within the player's org by the same ordering).
    # `_serialize` reads these out of the maps below so we don't have to
    # re-sort in the front-end.
    overall_rank_by_key: dict[str, int] = {}
    org_rank_by_key: dict[str, int] = {}
    org_size_by_key: dict[str, int] = {}
    org_counters: dict[str, int] = {}
    org_totals: dict[str, int] = {}
    for p in actives:
        org_totals[p.org or "?"] = org_totals.get(p.org or "?", 0) + 1
    for i, p in enumerate(actives, start=1):
        overall_rank_by_key[p.player_key] = i
        org_key = p.org or "?"
        org_counters[org_key] = org_counters.get(org_key, 0) + 1
        org_rank_by_key[p.player_key] = org_counters[org_key]
        org_size_by_key[p.player_key] = org_totals[org_key]

    # Inactives: most recently seen first
    inactives.sort(key=lambda p: p.points[-1].snapshot_date if p.points else "", reverse=True)

    # Sort graduates by graduation_date desc (most recent first)
    grads.sort(key=lambda p: p.graduation_date or "", reverse=True)

    # ── Org farm summary ────────────────────────────────────────────────────
    # Build per-org aggregate stats from the active list only (not graduates).
    # Position groups: C, 1B, 2B/SS/3B (INF), OF, SP/RP (P).
    PITCHER_POS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}

    def _pos_group(pos: str | None) -> str:
        if not pos:
            return "?"
        p0 = pos.split("/")[0]
        if p0 in PITCHER_POS:
            return "P"
        if p0 == "C":
            return "C"
        if p0 in {"1B"}:
            return "1B"
        if p0 in {"OF", "CF", "LF", "RF"}:
            return "OF"
        # SS, 2B, 3B, UTIL
        return "INF"

    org_map: dict[str, dict] = {}
    for idx, p in enumerate(actives):
        # Skip prospects with no resolved org — they fall through every source
        # without a team label (rare; usually a name-aliasing bug where the
        # prospect is double-counted under a different canonical key with an
        # org). Including them creates a phantom 31st "team" on the farm page.
        if not p.org:
            continue
        org = p.org
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        latest = p.points[-1]
        fv_raw = latest.consensus_fv_raw
        fv_lab = latest.consensus_fv_label
        stock_dir = p.points[-1].consensus_fv_raw - p.points[0].consensus_fv_raw if len(p.points) > 1 else 0.0
        sl = statlines.get(p.player_key)
        level = sl.get("level") if sl else None
        avl = score_age_vs_level(age, level, baselines=age_baselines)
        pos_grp = _pos_group(p.position)

        if org not in org_map:
            org_map[org] = {
                "org": org,
                "prospects": [],
                "total_fv": 0.0,
                "tier_60_plus": 0,
                "tier_55": 0,
                "tier_50": 0,
                "ages": [],
                "pos_groups": {},
                "stock_up": 0,
                "stock_down": 0,
                "stock_flat": 0,
                "very_young_count": 0,
            }
        m = org_map[org]
        m["prospects"].append({
            "name": p.player_name,
            "pos": p.position,
            "age": age,
            "fv_label": fv_lab,
            "fv_raw": round(fv_raw, 1),
            "rank": idx + 1,
        })
        m["total_fv"] += fv_raw
        fv_int = int(fv_raw)
        if fv_int >= 60:
            m["tier_60_plus"] += 1
        elif fv_int >= 55:
            m["tier_55"] += 1
        else:
            m["tier_50"] += 1
        if age is not None:
            m["ages"].append(age)
        m["pos_groups"][pos_grp] = m["pos_groups"].get(pos_grp, 0) + 1
        if stock_dir > 2:
            m["stock_up"] += 1
        elif stock_dir < -2:
            m["stock_down"] += 1
        else:
            m["stock_flat"] += 1
        if avl.tier == "very-young":
            m["very_young_count"] += 1

    # Finalize each org entry
    org_summary = []
    for org, m in sorted(org_map.items()):
        ages = m.pop("ages")
        m["count"] = len(m["prospects"])
        m["total_fv"] = round(m["total_fv"], 1)
        m["avg_age"] = round(sum(ages) / len(ages), 1) if ages else None
        m["top_prospect"] = m["prospects"][0] if m["prospects"] else None
        m["youngest"] = min(m["prospects"], key=lambda x: x["age"] if x["age"] else 99) if m["prospects"] else None
        org_summary.append(m)

    # Sort by total_fv descending — this is the "farm system power ranking"
    org_summary.sort(key=lambda x: -x["total_fv"])
    for rank_i, entry in enumerate(org_summary, start=1):
        entry["farm_rank"] = rank_i

    # Per-level graded prospect counts, sourced from the affiliate-roster
    # map. Drives both the "sort farms by depth at level X" chips on the
    # farm list page and the "graded prospects by level" section on each
    # farm detail page. Only includes prospects with a FV grade — un-graded
    # org filler in the rosters isn't a prospect for our purposes.
    FARM_LEVELS = ("MLB", "AAA", "AA", "A+", "A", "Rk", "DSL")
    for entry in org_summary:
        org_rosters = rosters_by_org.get(entry["org"], {})
        entry["level_counts"] = {
            lvl: sum(1 for r in (org_rosters.get(lvl) or []) if r.get("fv_label"))
            for lvl in FARM_LEVELS
        }

    # Per-org cumulative FV history — running sum of prospect FVs over time,
    # attributed to whichever org owned the prospect on each snapshot date.
    # Drives the farm-system stock chart on the farm list + farm detail
    # pages. Trades show as +/- moves between orgs; graduations subtract a
    # graduate's FV from their org on their graduation date.
    org_fv_history = _build_org_fv_history(
        actives + grads + inactives, _filter_real_trades, trades_by_player,
    )
    for entry in org_summary:
        hist = org_fv_history.get(entry["org"], {})
        entry["fv_history"] = hist.get("series", [])
        entry["fv_events"]  = hist.get("events", [])
    # ────────────────────────────────────────────────────────────────────────

    active_payload = [_serialize(p) for p in actives]
    inactive_payload = [_serialize(p) for p in inactives]
    graduate_payload = [_serialize(p) for p in grads]
    graduate_payload.sort(key=lambda p: p.get("graduation_date") or "", reverse=True)

    from prospect_savant import attach_prospect_savant
    savant_matched = attach_prospect_savant(
        active_payload + inactive_payload + graduate_payload,
        Path(__file__).parent,
    )

    from spotlights import build_spotlights
    spotlight_payload = build_spotlights(active_payload, graduate_payload)

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run": latest_run_summary(),
        "total_tracked": len(timeseries),
        "active_count": len(actives),
        "inactive_count": len(inactives),
        "graduate_count": len(grads),
        "inactive_cutoff": cutoff.isoformat(),
        "prospect_savant_count": savant_matched,
        "players":    active_payload,
        "inactive":   inactive_payload,
        "graduates":  graduate_payload,
        "spotlights": spotlight_payload,
        "org_summary": org_summary,
        "level_norms": level_norms,
        # Per-org affiliate rosters keyed by parent_org_abbr → level → list.
        # Each player record carries an FV grade when the player is one of
        # our tracked prospects, otherwise just basic identity info.
        "rosters_by_org": rosters_by_org,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path
