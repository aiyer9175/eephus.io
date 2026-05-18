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

CREATE TABLE IF NOT EXISTS statcast_metrics (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized StatcastMetrics dataclass
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


def upsert_birth_date(player_key: str, birth_date: str) -> None:
    """
    Set a player's birth_date. Idempotent — only writes if currently NULL,
    so a one-time fetch wins and we never re-fetch unnecessarily.
    """
    if not birth_date:
        return
    with connect() as con:
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


def upsert_statcast_metrics(metrics: dict[str, "StatcastMetrics"], season: int) -> int:
    """Upsert Statcast metrics. One row per player."""
    n = 0
    with connect() as con:
        for key, sc in metrics.items():
            con.execute(
                """INSERT INTO statcast_metrics (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(asdict(sc)), sc.fetched_at),
            )
            n += 1
    return n


def load_statcast_metrics() -> dict[str, dict]:
    """Return {player_key: metrics_dict} for all stored Statcast metrics."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM statcast_metrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


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


def export_timeseries_json(timeseries: list[PlayerTimeseries], out_path: Path,
                          statlines: dict[str, dict] | None = None,
                          pitch_arsenals: dict[str, dict] | None = None,
                          statcast_metrics: dict[str, dict] | None = None,
                          trades_by_player: dict[str, list[dict]] | None = None,
                          top_n_active: int | None = None):
    """
    Serialize for the front-end widget.

    Each player now carries:
      - statline      : slash line / ERA at the highest level this season
      - pitch_arsenal : pitch mix and velo for pitchers (may be None)
      - statcast      : exit velo, hard-hit %, launch angle, barrel % (may be None)
      - trades        : list of trade events
      - birth_date + age + age_vs_level
    """
    statlines = statlines or {}
    pitch_arsenals = pitch_arsenals or {}
    statcast_metrics = statcast_metrics or {}
    trades_by_player = trades_by_player or {}
    birth_dates = load_birth_dates()
    from stats import compute_age_decimal
    from age_level import score_age_vs_level
    from eta import estimate_eta

    PITCHER_POS_SET = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}

    def _serialize(p: PlayerTimeseries) -> dict:
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        sl = statlines.get(p.player_key)
        level = sl.get("level") if sl else None
        avl = score_age_vs_level(age, level)
        pa = pitch_arsenals.get(p.player_key)
        sc = statcast_metrics.get(p.player_key)
        is_pitcher = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        latest_fv = p.points[-1].consensus_fv_raw if p.points else None
        eta = estimate_eta(level, age, is_pitcher, latest_fv, sl)
        return {
            "player_key": p.player_key,
            "player_name": p.player_name,
            "position": p.position,
            "org": p.org,
            "status": p.status,
            "graduation_date": p.graduation_date,
            "birth_date": bd,
            "age": age,
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
            "statline": sl,
            "pitch_arsenal": pa,
            "statcast": sc,
            "trades": trades_by_player.get(p.player_key, []),
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
        if latest_date < cutoff:
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
        org = p.org or "?"
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        latest = p.points[-1]
        fv_raw = latest.consensus_fv_raw
        fv_lab = latest.consensus_fv_label
        stock_dir = p.points[-1].consensus_fv_raw - p.points[0].consensus_fv_raw if len(p.points) > 1 else 0.0
        sl = statlines.get(p.player_key)
        level = sl.get("level") if sl else None
        avl = score_age_vs_level(age, level)
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
    # ────────────────────────────────────────────────────────────────────────

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run": latest_run_summary(),
        "total_tracked": len(timeseries),
        "active_count": len(actives),
        "inactive_count": len(inactives),
        "graduate_count": len(grads),
        "inactive_cutoff": cutoff.isoformat(),
        "players":    [_serialize(p) for p in actives],
        "inactive":   [_serialize(p) for p in inactives],
        "graduates":  [_serialize(p) for p in grads],
        "org_summary": org_summary,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path
