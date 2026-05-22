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

from scrapers import (
    Snapshot, canonical_player_key,
    HITTER_TOOL_KEYS, PITCHER_TOOL_KEYS, ALL_TOOL_KEYS,
)
from consensus import PlayerTimeseries, stock_movement
from stats import StatLine

DB_PATH = Path(__file__).parent / "prospects.db"

# Prospects whose most recent ranking update is older than this many months are
# classified as "inactive" rather than "active". They fell off prospect lists
# without ever being marked graduated — think Wander Franco (suspended) or
# players who quietly aged out of prospect status.
INACTIVE_MONTHS = 18

# After this many days since a source's most recent tool publication,
# we flag that source as "stale" in tools.source_recency. The UI uses
# the flag to visually de-emphasize the source in the history dropdown
# without removing it from Tools+ (Tools+ always uses each source's
# latest publication regardless of age).
TOOL_FRESHNESS_DAYS = 365


def _index_plus(value: float | None, mean: float | None, stdev: float | None) -> int | None:
    """Generic 'X+' normalization shared by RPS+, DvM+, and ToolGrade+.

    Returns `100 + 10 * (value - mean) / stdev`, rounded to int and
    clamped to [0, 250] so a perverse one-prospect cohort never produces
    a nonsense ±400 reading. Returns None when any input is missing or
    when stdev is zero (no variance → every prospect plots at 100, which
    is informationally useless but not wrong).
    """
    if value is None or mean is None or stdev is None or stdev <= 0:
        return None
    plus = round(100 + 10 * (value - mean) / stdev)
    return max(0, min(250, plus))


def _round_half(grade: float | None) -> float | None:
    """Snap a 20-80 grade to the nearest 0.5 — matches FG's published tool grid."""
    if grade is None:
        return None
    return round(grade * 2) / 2


_TOOLS_POWER_MEAN_P = 3.0  # >1 biases composite toward outliers


def _compute_peripheral_stf_plus(sl: dict | None,
                                 norms_perf: dict | None) -> int | None:
    """Z-score composite of K%, BB%, and HR/9 vs the level mean.

    Workload-stable peripheral STF+. Per-batter K%/BB% replace per-9 rates
    so a starter and a reliever can be compared on the same footing.

      stf = 100 + 10 · (0.55·z_K − 0.30·z_BB − 0.15·z_HR9)

    where z scores are (value − μ) / σ and σ is approximated as 15% of
    the level mean (the level_norms blocks don't ship a real stdev; the
    15%-of-mean rule of thumb matches the spread observed across
    pitchers at every level on this site). Walks and HRs are subtracted
    so a low rate (good) raises the composite.

    Returns None when:
      - The pitcher's sample is below the gate (<20 IP and <30 BF).
      - K%, BB%, and HR/9 are all missing.
      - The level baselines aren't available.
    """
    if not sl or not norms_perf or not sl.get("is_pitcher"):
        return None
    try:
        ip = float(sl.get("ip") or 0)
    except (TypeError, ValueError):
        ip = 0
    try:
        bf = float(sl.get("batters_faced") or sl.get("tbf") or 0)
    except (TypeError, ValueError):
        bf = 0
    if ip < 20 and bf < 30:
        return None
    def _z(val_key, mu_key, std_key, invert=False):
        # Phase A3 — prefer the level's empirical sigma when level_norms
        # has enough samples to compute it; fall back to the 0.15×mu
        # rule of thumb otherwise. The empirical sigma is meaningfully
        # tighter for K%/BB% (the real per-level distribution is
        # narrower than 15% of the mean) and looser for HR/9 (real
        # spread is wider) — so the z-scores get more honest at both ends.
        try:
            v = sl.get(val_key)
            mu = norms_perf.get(mu_key)
            if v is None or mu is None or mu == 0:
                return None
            v = float(v)
            empirical_sigma = norms_perf.get(std_key)
            if empirical_sigma is not None and float(empirical_sigma) > 0:
                sigma = float(empirical_sigma)
            else:
                sigma = 0.15 * float(mu)
            if sigma <= 0:
                return None
            z = (v - mu) / sigma
            return -z if invert else z
        except (TypeError, ValueError):
            return None
    z_k  = _z("k_pct",     "avg_pitcher_k_pct",  "std_pitcher_k_pct")
    z_bb = _z("bb_pct",    "avg_pitcher_bb_pct", "std_pitcher_bb_pct", invert=True)
    z_hr = _z("hr_per_9",  "avg_hr_per_9",       "std_hr_per_9",       invert=True)
    parts = [(0.55, z_k), (0.30, z_bb), (0.15, z_hr)]
    parts = [(w, z) for w, z in parts if z is not None]
    if not parts:
        return None
    weight_sum = sum(w for w, _ in parts)
    composite = sum(w * z for w, z in parts) / weight_sum
    stf = round(100 + 10 * composite)
    return max(0, min(250, stf))


def _power_mean(vals: list[float], p: float = _TOOLS_POWER_MEAN_P) -> float | None:
    """Lₚ power mean — biases the composite toward outliers when p > 1.

    p=1 reduces to arithmetic mean; p→∞ approaches max. p=3 is a
    moderate "rewards a standout tool" bias: a 70+50+50+50 hitter
    goes from 55 (arith mean) to ~57.6 (power-3). A uniform 50/50/50/50
    profile stays at 50. Operates in the FV-grade space (20-80) and
    returns a value in the same band.
    """
    if not vals:
        return None
    n = len(vals)
    return (sum(v ** p for v in vals) / n) ** (1.0 / p)


def _compute_tool_composites(grades: dict[str, float] | None,
                              is_pitcher: bool) -> dict | None:
    """Build the raw (pre-Tools+) tools sub-object from per-tool consensus grades.

    Returns a dict with `grades` (the input, copied + rounded to 0.5),
    the composites (off/def for hitters, stuff/cmd for pitchers, and
    overall in both cases), or None when no tools are graded.
    Composites are computed only over the grades that are present —
    a hitter with hit + power but no field/throw still gets a
    `composite_off` but no `composite_def`. The off/def composites use
    a power mean (p=3) so a single standout tool lifts the composite
    more than balanced average tools — better captures "toolsy".
    """
    if not grades:
        return None
    cleaned: dict[str, float] = {}
    for k, v in grades.items():
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f < 20 or f > 80:
            continue
        cleaned[k] = _round_half(f)
    if not cleaned:
        return None

    def _avg(keys):
        # Outlier-biased power mean (Lₚ, p=3). Falls back to None when
        # none of the keys are present in `cleaned`.
        vals = [cleaned[k] for k in keys if k in cleaned]
        if not vals:
            return None
        result = _power_mean(vals)
        return round(result, 2) if result is not None else None

    out: dict = {"grades": cleaned}
    if is_pitcher:
        stuff = _avg(("fb", "sl", "cb", "ch"))
        cmd = cleaned.get("cmd")
        out["composite_stuff"] = stuff
        out["composite_cmd"] = cmd
        # Overall = 0.65 stuff + 0.35 cmd; fall back to whichever side
        # is present so a "stuff-only" prospect still gets an overall.
        if stuff is not None and cmd is not None:
            out["composite_overall"] = round(0.65 * stuff + 0.35 * cmd, 2)
        else:
            out["composite_overall"] = stuff if stuff is not None else cmd
        out["composite_off"] = None
        out["composite_def"] = None
    else:
        # Speed counts toward BOTH composites — it shapes offense (range
        # on the bases, BABIP, taking the extra base) and defense (range
        # in the field, jumps, recovery). Including it on both sides
        # avoids penalizing burner CFs whose defensive value is range-
        # driven rather than arm-driven.
        # pitch_sel + bat_ctrl are plate-discipline / barrel-control
        # tools (FG-published); they belong on the offensive side.
        off = _avg(("hit", "game_pwr", "raw_pwr", "speed",
                    "pitch_sel", "bat_ctrl"))
        deff = _avg(("field", "throw", "speed"))
        out["composite_off"] = off
        out["composite_def"] = deff
        if off is not None and deff is not None:
            out["composite_overall"] = round(0.7 * off + 0.3 * deff, 2)
        else:
            out["composite_overall"] = off if off is not None else deff
        out["composite_stuff"] = None
        out["composite_cmd"] = None
    return out


def _attach_tool_plus_indices(payloads: list[dict]) -> None:
    """Second-pass population normalization for tool composites.

    Iterates over every serialized prospect once to compute per-composite
    mean/stdev (across all prospects that have a non-None value for that
    composite), then back-fills `composite_*_plus` on each tools dict
    in-place. Mirrors how RPS+ buckets are built in the frontend, but at
    storage time so the JSON ships with the indices baked in.

    Hitter and pitcher composites use the SAME cohort norms — every
    prospect in the comparison, regardless of role — so a 60-grade hit
    tool reads the same way relative to peers as a 60-grade fastball
    reads relative to pitchers. (If a future iteration wants role-split
    norms, this is the one place to change.)
    """
    composite_keys = ("composite_off", "composite_def",
                      "composite_stuff", "composite_cmd", "composite_overall")
    samples: dict[str, list[float]] = {k: [] for k in composite_keys}
    for pl in payloads:
        t = pl.get("tools")
        if not t:
            continue
        for k in composite_keys:
            v = t.get(k)
            if v is not None:
                samples[k].append(float(v))
    cohort_stats: dict[str, tuple[float, float]] = {}
    for k, vals in samples.items():
        if len(vals) < 2:
            cohort_stats[k] = (None, None)
            continue
        m = sum(vals) / len(vals)
        var = sum((x - m) ** 2 for x in vals) / len(vals)
        cohort_stats[k] = (m, var ** 0.5 if var > 0 else None)
    for pl in payloads:
        t = pl.get("tools")
        if not t:
            continue
        for k in composite_keys:
            mean, stdev = cohort_stats[k]
            t[f"{k}_plus"] = _index_plus(t.get(k), mean, stdev)
        # Two-way players: stamp the same indices on hitter_payload /
        # pitcher_payload sub-dicts so each Tools card renders its own
        # Tools+ numbers against the shared cohort norms.
        for sub_key in ("hitter_payload", "pitcher_payload"):
            sub = t.get(sub_key)
            if not sub:
                continue
            for k in composite_keys:
                mean, stdev = cohort_stats[k]
                sub[f"{k}_plus"] = _index_plus(sub.get(k), mean, stdev)
        # Composite-driven green/red flags piggyback on the X+ pass —
        # the per-tool compute_tool_flags call inside _serialize ran
        # before X+ values existed, so we append composite flags here.
        overall_plus = t.get("composite_overall_plus")
        off_plus = t.get("composite_off_plus")
        stuff_plus = t.get("composite_stuff_plus")
        tool_flags = pl.setdefault("tool_flags", [])
        for plus_key, plus_val, label in (
            ("composite_overall_plus", overall_plus, "Overall tools"),
            ("composite_off_plus",     off_plus,     "Offensive tools"),
            ("composite_stuff_plus",   stuff_plus,   "Stuff"),
        ):
            if plus_val is None:
                continue
            if plus_val >= 115:
                tool_flags.append({
                    "stat": label,
                    "direction": "green",
                    "value": plus_val,
                    "value_display": f"{label} {plus_val:+d}",
                    "level": None,
                    "level_avg": 100,
                    "delta": plus_val - 100,
                    "delta_display": f"{plus_val - 100:+d}",
                    "category": "composite",
                    "polarity": "above_good",
                    "note": f"{label} index {plus_val} — above-cohort toolset.",
                })
        if overall_plus is not None and overall_plus <= 85:
            tool_flags.append({
                "stat": "Overall tools",
                "direction": "red",
                "value": overall_plus,
                "value_display": f"Overall tools {overall_plus:+d}",
                "level": None,
                "level_avg": 100,
                "delta": overall_plus - 100,
                "delta_display": f"{overall_plus - 100:+d}",
                "category": "composite",
                "polarity": "below_good",
                "note": f"Overall tools index {overall_plus} — below-cohort toolset.",
            })


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

-- Per-graduate career WAR aggregated from FanGraphs (bulk batting_stats /
-- pitching_stats pull via pybaseball). payload_json is a dict:
--   {"seasons": {"2023": 1.5, "2024": 2.8, ...},
--    "career_war": 4.3,
--    "war_per_yr": 2.15,
--    "war_seasons_count": 2,
--    "source": "fangraphs"}
-- Only populated for graduates / inactives that have at least one MLB
-- season on file; actives skip this fetch entirely (no value-add yet).
CREATE TABLE IF NOT EXISTS career_war (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
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

-- Per-player raw transactions cache (MLB Stats API /transactions?playerId=).
-- Drives within-season promotion/demotion detection AND the options /
-- service-time heuristics. One row per player; payload_json is the list
-- of {date, type_code, description, from_team_id, from_team_name,
-- to_team_id, to_team_name} dicts sorted ascending by date.
CREATE TABLE IF NOT EXISTS player_transactions (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Derived MLB roster timeline per player. Computed from the transactions
-- cache + career_stats: {debut_date, options_used, on_40_man, service_days,
-- service_years_decimal, arb_year (0=pre-arb, 1-3=arb, 4+=post-arb)}.
CREATE TABLE IF NOT EXISTS roster_status (
    player_key      TEXT PRIMARY KEY,
    payload_json    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now'))
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

-- ===========================================================================
-- Draft prospects (amateurs — HS/college players in upcoming MLB drafts)
-- ===========================================================================
-- Parallel track to the snapshots/players tables. Column-level firewall:
-- no draft player ever appears in `snapshots`, `players`, `statlines`,
-- `sabermetrics`, etc. until they're DRAFTED (see draft_promotion.py),
-- at which point a single MiLB snapshot row is created in the standard
-- tables. RPS+ and other MiLB-cohort metrics are structurally excluded.

CREATE TABLE IF NOT EXISTS draft_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,        -- 'fangraphs' | 'espn_draft' | 'mlb_pipeline_draft' | 'manual'
    snapshot_date   TEXT NOT NULL,
    interval_label  TEXT NOT NULL,
    player_key      TEXT NOT NULL,        -- draft_<year>_<name_slug>
    player_name     TEXT NOT NULL,
    position        TEXT,
    school          TEXT,                 -- HS or college name
    college_commit  TEXT,                 -- HS commits (NULL for college players)
    player_type     TEXT,                 -- 'HSh'|'HSp'|'COLh'|'COLp'
    draft_year      INTEGER NOT NULL,
    rank            INTEGER,              -- per-source rank within the class
    fv              REAL,
    risk            TEXT,
    status          TEXT NOT NULL,        -- 'draft_active' | 'drafted' | 'unsigned' | 'transferred'
    tools_json      TEXT,                 -- {tools_future, tools_present, report, video, ...}
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, interval_label, player_key)
);
CREATE INDEX IF NOT EXISTS idx_draft_snap_year   ON draft_snapshots(draft_year);
CREATE INDEX IF NOT EXISTS idx_draft_snap_player ON draft_snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_draft_snap_date   ON draft_snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS draft_players (
    player_key      TEXT PRIMARY KEY,
    player_name     TEXT NOT NULL,
    position        TEXT,
    school          TEXT,
    college_commit  TEXT,
    player_type     TEXT,
    draft_year      INTEGER NOT NULL,
    birth_date      TEXT,
    bats            TEXT,
    throws          TEXT,
    height          TEXT,
    weight          INTEGER,
    fg_player_id    TEXT,
    mlbam_id        INTEGER,
    promoted_key    TEXT,                  -- canonical MiLB player_key after draft (NULL until drafted)
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Post-draft picks + signing bonuses. One row per (year, pick_overall).
CREATE TABLE IF NOT EXISTS draft_results (
    draft_year     INTEGER NOT NULL,
    pick_overall   INTEGER NOT NULL,
    round_label    TEXT,                  -- '1', '2', 'CBA', 'CBB', 'PPI', etc.
    pick_in_round  INTEGER,
    team           TEXT NOT NULL,         -- canonical org code
    player_key     TEXT,                  -- draft_<year>_<name_slug> when matched
    player_name    TEXT NOT NULL,
    school         TEXT,
    slot_usd       INTEGER,
    bonus_usd      INTEGER,
    signed         INTEGER NOT NULL DEFAULT 0,
    source         TEXT,                  -- 'fg_draft_csv' | 'mlb_draft_tracker' | 'manual'
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_year, pick_overall)
);
CREATE INDEX IF NOT EXISTS idx_draft_results_team   ON draft_results(team);
CREATE INDEX IF NOT EXISTS idx_draft_results_player ON draft_results(player_key);

-- Mock drafts: one row per (source, snapshot, year, pick).
CREATE TABLE IF NOT EXISTS draft_mocks (
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    draft_year      INTEGER NOT NULL,
    pick_overall    INTEGER NOT NULL,
    team            TEXT NOT NULL,
    player_key      TEXT,
    player_name     TEXT NOT NULL,
    PRIMARY KEY (source, snapshot_date, draft_year, pick_overall)
);
CREATE INDEX IF NOT EXISTS idx_draft_mocks_year ON draft_mocks(draft_year);

-- Draft order — the assigned pick sequence (1-30 first round + comp picks)
-- for a given year. Pre-draft this drives the "Draft Order & Slots" panel;
-- post-draft it's redundant with draft_results.team but we keep it so the
-- mock-draft view can show team logos before draft day.
CREATE TABLE IF NOT EXISTS draft_order (
    draft_year     INTEGER NOT NULL,
    pick_overall   INTEGER NOT NULL,
    round_label    TEXT,
    pick_in_round  INTEGER,
    team           TEXT NOT NULL,
    slot_usd       INTEGER,
    source         TEXT NOT NULL,         -- 'mlb_draft_pool' | 'manual'
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_year, pick_overall)
);

-- Maps draft_<year>_<name> player_keys to canonical MiLB keys after
-- promotion. Read at promotion time + by the Draft UI to surface a
-- "DRAFTED — see MiLB profile" link.
CREATE TABLE IF NOT EXISTS draft_canonical_keys (
    draft_key      TEXT PRIMARY KEY,
    milb_key       TEXT NOT NULL,
    promoted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_draft_canonical_milb ON draft_canonical_keys(milb_key);
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
        # Migration: add tools_json column to snapshots for per-source
        # 20-80 tool grades. Older snapshots keep NULL — consensus + the
        # serializer treat NULL identically to "source didn't publish tools".
        try:
            con.execute("ALTER TABLE snapshots ADD COLUMN tools_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


def insert_snapshots(snapshots: Iterable[Snapshot]) -> int:
    # UPSERT — re-ingest of a (source, interval_label, player_key) tuple
    # overwrites the prior row's FV / rank / status / name. This is the
    # only way to correct stale snapshots (e.g. a wrong FV written by an
    # earlier buggy ingest path); the previous INSERT OR IGNORE silently
    # skipped re-runs and let bad data persist forever.
    #
    # position / org preserve the prior non-null value because some
    # sources don't republish them on every refresh; tools_json behaves
    # the same so a re-run with no tools doesn't wipe ones we already had.
    count = 0
    with connect() as con:
        for s in snapshots:
            tools_json = json.dumps(s.tools) if s.tools else None
            cur = con.execute(
                """INSERT INTO snapshots
                   (source, snapshot_date, interval_label, player_key,
                    player_name, position, org, rank, fv, status, tools_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                       snapshot_date = excluded.snapshot_date,
                       player_name   = excluded.player_name,
                       position      = COALESCE(excluded.position, snapshots.position),
                       org           = COALESCE(excluded.org,      snapshots.org),
                       rank          = excluded.rank,
                       fv            = excluded.fv,
                       status        = excluded.status,
                       tools_json    = COALESCE(excluded.tools_json, snapshots.tools_json)""",
                (s.source, s.snapshot_date, s.interval_label, s.player_key,
                 s.player_name, s.position, s.org, s.rank, s.fv, s.status,
                 tools_json),
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


def revalidate_auto_graduations(qualified_keys: set[str]) -> int:
    """Delete `auto_detect` 'graduated' snapshots for players who don't
    currently meet the rookie-eligibility rules.

    Earlier versions of the pipeline auto-graduated any prospect with an
    MLB debut date, regardless of whether they'd crossed the 130-AB /
    50-IP / options-exhausted threshold. Those over-eager rows persist
    in the DB across runs and `consensus.build_timeseries` reads them as
    canonical graduations — so a cup-of-coffee prospect from a prior run
    still shows as a graduate even after we tightened the rules.

    `qualified_keys` is the set of player_keys that DO meet the current
    rules (passed in by run_monthly from roster_status). Any auto_detect
    grad snapshot whose key is NOT in that set is removed. FanGraphs-
    sourced graduated snapshots are left alone — those are external
    authority.

    Returns the number of rows deleted.
    """
    with connect() as con:
        rows = con.execute(
            """SELECT player_key FROM snapshots
               WHERE source = 'auto_detect' AND status = 'graduated'"""
        ).fetchall()
        if not rows:
            return 0
        to_delete = [r["player_key"] for r in rows
                     if r["player_key"] not in qualified_keys]
        if not to_delete:
            return 0
        # Use executemany with a single-key clause so SQLite's parameter
        # list cap (~999) doesn't become a footgun when a lot of legacy
        # rows need to clear.
        con.executemany(
            """DELETE FROM snapshots
               WHERE source = 'auto_detect' AND status = 'graduated'
                 AND player_key = ?""",
            [(k,) for k in to_delete],
        )
        return len(to_delete)


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
                      player_name, position, org, rank, fv, status, tools_json
               FROM snapshots ORDER BY snapshot_date, source"""
        ).fetchall()
    snapshots: list[Snapshot] = []
    for r in rows:
        d = dict(r)
        d["player_key"] = canonical_player_key(d["player_key"])
        tools_json = d.pop("tools_json", None)
        tools = None
        if tools_json:
            try:
                parsed = json.loads(tools_json)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict) and parsed:
                tools = {}
                for k, v in parsed.items():
                    if v is None:
                        continue
                    # `_extras` is a nested dict of source-specific
                    # non-grade metadata (FG ships height, weight, sits,
                    # tops, fb_type, tj_date, frame, athl, perf, levers,
                    # arm, delivery, contact_style, hard_hit_pct, etc.).
                    # Pass it through verbatim so per_source.tools._extras
                    # reaches the UI.
                    if k == "_extras" and isinstance(v, dict):
                        tools["_extras"] = v
                        continue
                    try:
                        tools[k] = float(v)
                    except (TypeError, ValueError):
                        continue
                # Backwards-compat lift: pitch_sel and bat_ctrl were
                # historically stored under _extras; they are now
                # canonical hitter tools. Pull them up so legacy DB rows
                # don't need a re-ingest to participate in consensus
                # aggregation and composite_off / Tools+.
                extras = tools.get("_extras") if isinstance(tools.get("_extras"), dict) else None
                if extras:
                    for lifted_key in ("pitch_sel", "bat_ctrl"):
                        if lifted_key in tools:
                            continue
                        raw = extras.get(lifted_key)
                        if raw is None:
                            continue
                        try:
                            f = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if 20 <= f <= 80:
                            tools[lifted_key] = f
                if not tools:
                    tools = None
        d["tools"] = tools
        snapshots.append(Snapshot(**d))
    return snapshots


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


def upsert_career_war(by_key: dict[str, dict]) -> int:
    """Upsert one career-WAR aggregate per graduate. Skips empty payloads.

    Caller is expected to wrap each aggregate as:
      {"seasons": {"2023": 1.5, "2024": 2.8, ...},
       "career_war": 4.3,
       "war_per_yr": 2.15,
       "war_seasons_count": 2,
       "source": "fangraphs"}
    """
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            if not rec:
                continue
            con.execute(
                """INSERT INTO career_war (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rec)),
            )
            n += 1
    return n


def load_career_war() -> dict[str, dict]:
    """Return {player_key: war_aggregate_dict} for every cached graduate."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM career_war"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_career_war_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} so the pipeline can decide
    whether the cached WAR aggregate is fresh enough to skip refetching."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM career_war"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


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


# ===========================================================================
# Draft prospects (amateurs) — parallel track to snapshots/players
# ===========================================================================

def insert_draft_snapshots(snapshots: Iterable) -> int:
    """Upsert draft prospect snapshots. Accepts any iterable of objects
    with the standard Snapshot field set plus draft-specific extras
    (school, college_commit, player_type, draft_year). Either a
    `DraftSnapshot` dataclass instance or a plain dict works."""
    count = 0
    with connect() as con:
        for s in snapshots:
            if hasattr(s, "__dict__"):
                d = s.__dict__
            elif hasattr(s, "_asdict"):
                d = s._asdict()
            else:
                d = dict(s)
            tools = d.get("tools")
            tools_json = json.dumps(tools) if tools else None
            cur = con.execute(
                """INSERT INTO draft_snapshots
                     (source, snapshot_date, interval_label, player_key,
                      player_name, position, school, college_commit, player_type,
                      draft_year, rank, fv, risk, status, tools_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                       snapshot_date  = excluded.snapshot_date,
                       player_name    = excluded.player_name,
                       position       = COALESCE(excluded.position, draft_snapshots.position),
                       school         = COALESCE(excluded.school, draft_snapshots.school),
                       college_commit = COALESCE(excluded.college_commit, draft_snapshots.college_commit),
                       player_type    = COALESCE(excluded.player_type, draft_snapshots.player_type),
                       draft_year     = excluded.draft_year,
                       rank           = excluded.rank,
                       fv             = excluded.fv,
                       risk           = COALESCE(excluded.risk, draft_snapshots.risk),
                       status         = excluded.status,
                       tools_json     = COALESCE(excluded.tools_json, draft_snapshots.tools_json)""",
                (d.get("source"), d.get("snapshot_date"), d.get("interval_label"),
                 d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("school"), d.get("college_commit"), d.get("player_type"),
                 d.get("draft_year"), d.get("rank"), d.get("fv"),
                 d.get("risk"), d.get("status", "draft_active"), tools_json),
            )
            count += cur.rowcount
            con.execute(
                """INSERT INTO draft_players
                     (player_key, player_name, position, school, college_commit,
                      player_type, draft_year, birth_date, bats, throws,
                      height, weight, fg_player_id, mlbam_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                       player_name    = excluded.player_name,
                       position       = COALESCE(excluded.position, draft_players.position),
                       school         = COALESCE(excluded.school, draft_players.school),
                       college_commit = COALESCE(excluded.college_commit, draft_players.college_commit),
                       player_type    = COALESCE(excluded.player_type, draft_players.player_type),
                       draft_year     = excluded.draft_year,
                       birth_date     = COALESCE(excluded.birth_date, draft_players.birth_date),
                       bats           = COALESCE(excluded.bats, draft_players.bats),
                       throws         = COALESCE(excluded.throws, draft_players.throws),
                       height         = COALESCE(excluded.height, draft_players.height),
                       weight         = COALESCE(excluded.weight, draft_players.weight),
                       fg_player_id   = COALESCE(excluded.fg_player_id, draft_players.fg_player_id),
                       mlbam_id       = COALESCE(excluded.mlbam_id, draft_players.mlbam_id),
                       updated_at     = datetime('now')""",
                (d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("school"), d.get("college_commit"), d.get("player_type"),
                 d.get("draft_year"), d.get("birth_date"),
                 d.get("bats"), d.get("throws"),
                 d.get("height"), d.get("weight"),
                 d.get("fg_player_id"), d.get("mlbam_id")),
            )
    return count


def load_draft_snapshots(draft_year: int | None = None) -> list[dict]:
    """Return draft_snapshots rows. Filter by draft_year if given."""
    q = """SELECT id, source, snapshot_date, interval_label, player_key,
                  player_name, position, school, college_commit, player_type,
                  draft_year, rank, fv, risk, status, tools_json, inserted_at
           FROM draft_snapshots"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, snapshot_date DESC, rank ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d.get("tools_json"):
            try:
                d["tools"] = json.loads(d["tools_json"])
            except (ValueError, TypeError):
                d["tools"] = None
        else:
            d["tools"] = None
        out.append(d)
    return out


def load_draft_players(draft_year: int | None = None) -> dict[str, dict]:
    """Return {player_key: draft_player_dict} for the named draft year
    (or every year when draft_year is None)."""
    q = """SELECT player_key, player_name, position, school, college_commit,
                  player_type, draft_year, birth_date, bats, throws,
                  height, weight, fg_player_id, mlbam_id, promoted_key
           FROM draft_players"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: dict(r) for r in rows}


def upsert_draft_results(rows: Iterable[dict]) -> int:
    """Upsert post-draft pick rows. Each dict carries:
      draft_year, pick_overall, round_label, pick_in_round, team,
      player_key (optional), player_name, school, slot_usd, bonus_usd,
      signed, source.
    UNIQUE on (draft_year, pick_overall) — re-runs overwrite."""
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_results
                     (draft_year, pick_overall, round_label, pick_in_round,
                      team, player_key, player_name, school,
                      slot_usd, bonus_usd, signed, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, pick_overall) DO UPDATE SET
                     round_label   = COALESCE(excluded.round_label, draft_results.round_label),
                     pick_in_round = COALESCE(excluded.pick_in_round, draft_results.pick_in_round),
                     team          = excluded.team,
                     player_key    = COALESCE(excluded.player_key, draft_results.player_key),
                     player_name   = excluded.player_name,
                     school        = COALESCE(excluded.school, draft_results.school),
                     slot_usd      = COALESCE(excluded.slot_usd, draft_results.slot_usd),
                     bonus_usd     = COALESCE(excluded.bonus_usd, draft_results.bonus_usd),
                     signed        = excluded.signed,
                     source        = excluded.source,
                     inserted_at   = datetime('now')""",
                (r.get("draft_year"), r.get("pick_overall"),
                 r.get("round_label"), r.get("pick_in_round"),
                 r.get("team"), r.get("player_key"),
                 r.get("player_name"), r.get("school"),
                 r.get("slot_usd"), r.get("bonus_usd"),
                 1 if r.get("signed") else 0, r.get("source")),
            )
            n += 1
    return n


def load_draft_results(draft_year: int | None = None) -> list[dict]:
    q = """SELECT draft_year, pick_overall, round_label, pick_in_round,
                  team, player_key, player_name, school,
                  slot_usd, bonus_usd, signed, source
           FROM draft_results"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, pick_overall ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def upsert_draft_order(rows: Iterable[dict]) -> int:
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_order
                     (draft_year, pick_overall, round_label, pick_in_round,
                      team, slot_usd, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, pick_overall) DO UPDATE SET
                     round_label   = COALESCE(excluded.round_label, draft_order.round_label),
                     pick_in_round = COALESCE(excluded.pick_in_round, draft_order.pick_in_round),
                     team          = excluded.team,
                     slot_usd      = COALESCE(excluded.slot_usd, draft_order.slot_usd),
                     source        = excluded.source,
                     inserted_at   = datetime('now')""",
                (r.get("draft_year"), r.get("pick_overall"),
                 r.get("round_label"), r.get("pick_in_round"),
                 r.get("team"), r.get("slot_usd"), r.get("source")),
            )
            n += 1
    return n


def load_draft_order(draft_year: int | None = None) -> list[dict]:
    q = """SELECT draft_year, pick_overall, round_label, pick_in_round,
                  team, slot_usd, source
           FROM draft_order"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, pick_overall ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def upsert_draft_mocks(rows: Iterable[dict]) -> int:
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_mocks
                     (source, snapshot_date, draft_year, pick_overall,
                      team, player_key, player_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, snapshot_date, draft_year, pick_overall)
                   DO UPDATE SET
                     team        = excluded.team,
                     player_key  = COALESCE(excluded.player_key, draft_mocks.player_key),
                     player_name = excluded.player_name""",
                (r.get("source"), r.get("snapshot_date"), r.get("draft_year"),
                 r.get("pick_overall"), r.get("team"),
                 r.get("player_key"), r.get("player_name")),
            )
            n += 1
    return n


def load_draft_mocks(draft_year: int | None = None) -> list[dict]:
    q = """SELECT source, snapshot_date, draft_year, pick_overall,
                  team, player_key, player_name
           FROM draft_mocks"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY snapshot_date DESC, pick_overall ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def link_draft_to_milb(draft_key: str, milb_key: str) -> None:
    """Record a promotion: draft prospect -> MiLB player_key."""
    with connect() as con:
        con.execute(
            """INSERT INTO draft_canonical_keys (draft_key, milb_key)
               VALUES (?, ?)
               ON CONFLICT(draft_key) DO UPDATE SET
                 milb_key    = excluded.milb_key,
                 promoted_at = datetime('now')""",
            (draft_key, milb_key),
        )
        con.execute(
            """UPDATE draft_players SET promoted_key = ?, updated_at = datetime('now')
               WHERE player_key = ?""",
            (milb_key, draft_key),
        )


def load_draft_canonical_keys() -> dict[str, str]:
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT draft_key, milb_key FROM draft_canonical_keys"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["draft_key"]: r["milb_key"] for r in rows}


# ===========================================================================
# IL status (existing functionality below)
# ===========================================================================

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


def upsert_player_transactions(by_player: dict[str, list[dict]]) -> int:
    """Upsert per-player transaction lists. One row per player.

    Each list value is the full payload from the MLB Stats API per-player
    transactions endpoint, normalized to {date, type_code, description,
    from_team_id, from_team_name, to_team_id, to_team_name}. Pass an empty
    list to record "we asked, nothing was returned" without rewriting a
    prior populated row (we keep the old payload in that case).
    """
    n = 0
    with connect() as con:
        for key, rows in by_player.items():
            if not rows:
                # Touch fetched_at only — keeps TTL skip working without
                # erasing a previously-populated payload.
                con.execute(
                    """UPDATE player_transactions
                       SET fetched_at = datetime('now')
                       WHERE player_key = ?""",
                    (key,),
                )
                continue
            con.execute(
                """INSERT INTO player_transactions
                     (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rows)),
            )
            n += 1
    return n


def load_player_transactions() -> dict[str, list[dict]]:
    """Return {player_key: [tx_rows]} for every stored player transaction history."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM player_transactions"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_player_transactions_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for every stored player_transactions row."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM player_transactions"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


def upsert_roster_status(by_player: dict[str, dict]) -> int:
    """Upsert derived roster-status dicts (debut/options/service time)."""
    n = 0
    with connect() as con:
        for key, rec in by_player.items():
            if not rec:
                continue
            con.execute(
                """INSERT INTO roster_status
                     (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rec)),
            )
            n += 1
    return n


def load_roster_status() -> dict[str, dict]:
    """Return {player_key: roster_status_dict} for every stored row."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM roster_status"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


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


# ---------------------------------------------------------------------------
# Farm-system grading
# ---------------------------------------------------------------------------
# Each org gets a report card with four component scores plus an overall
# letter grade. The previous system (60% total_fv + 30% 90-day delta + 10%
# grad count) had three problems we explicitly fix here:
#
#   1. Raw total_fv treats a 35 FV org-filler the same as a real prospect.
#      → Replaced with tiered FV-to-points (an 80 is worth ~100x a 40).
#
#   2. 90-day delta was dominated by whichever single source happened to
#      update inside the window — a noisy proxy for "trajectory".
#      → Replaced with a smoothed mean-of-recent vs mean-near-cutoff
#        comparison that survives any one source's swing.
#
#   3. Recent grad count was binary — graduating Roki Sasaki counted the
#      same as graduating a 40 FV bench bat.
#      → Replaced with FV-weighted grads in the last 12 months.
#
# Component scores (each rescaled to a 0-100 scale across the 30 orgs):
#   * top_end_points — sum of tiered points for the org's top 5 prospects
#                      (45% weight, the dominant signal)
#   * depth_points   — sum of tiered points for prospects #6-25  (25%)
#   * trajectory     — smoothed change in cumulative FV           (15%)
#   * grad_pipeline  — FV-weighted graduations in trailing 12 mo  (15%)
#
# The four 0-100 scores blend linearly into a `farm_score`; the overall
# letter grade is the bucket that score lands in among the 30 orgs.

FARM_TRAJECTORY_LOOKBACK_DAYS = 365
FARM_TRAJECTORY_SMOOTH_WINDOW = 3   # avg last 3 fv_history points vs 3 near cutoff
FARM_GRAD_PIPELINE_MONTHS     = 12

# Multi-window trajectories. The list page lets the user toggle between
# these to ask "who's been developing prospects best over the last X?".
# The 1y entry matches FARM_TRAJECTORY_LOOKBACK_DAYS and feeds the
# canonical `trajectory_score` (which keeps the report-card grading
# anchored to the 1y window). Longer windows surface orgs whose growth
# only shows up over a draft cycle or two.
FARM_TRAJECTORY_WINDOWS = {
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
}

FARM_TOP_END_COUNT  = 5             # top N prospects feeding the "stars" score
FARM_DEPTH_START    = 5             # prospects #6 ...
FARM_DEPTH_END      = 25            # ... through #25 feed the "depth" score

# Farm-score blend weights — 10 components, sum to 1.0. The "big-4"
# (Top-End + Depth + DvM+ + Grad Pipeline) still control ~70%; WAG and
# Financial ROI add the MLB-impact lens (~18%); the three "Profile"
# components (Tools+ / IFA depth / Readiness / Health) provide
# secondary signal worth a combined ~12%. DvM+ REPLACED the raw
# Trajectory weight (DvM+ is the z-scored, league-mean-anchored
# version of the same delta — strictly more informative).
FARM_WEIGHT_TOP_END             = 0.28
FARM_WEIGHT_DEPTH               = 0.18
FARM_WEIGHT_DVM_PLUS            = 0.12   # was FARM_WEIGHT_TRAJECTORY
FARM_WEIGHT_GRAD                = 0.12
FARM_WEIGHT_TALENT_TRANSLATION  = 0.10   # NEW — per-org WAG mean
FARM_WEIGHT_FINANCIAL_ROI       = 0.08   # NEW — WAR per million spent
FARM_WEIGHT_TOOLS_QUALITY       = 0.06   # NEW — top-10 mean composite_overall
FARM_WEIGHT_INTL_DEPTH          = 0.03   # NEW — IFA % + multi-year span
FARM_WEIGHT_READINESS           = 0.02   # NEW — (very_young - very_old) %
FARM_WEIGHT_HEALTH              = 0.01   # NEW — INVERSE (lower burden = better)
# Back-compat alias — kept so external imports don't break. The blend
# no longer uses FARM_WEIGHT_TRAJECTORY directly; DvM+ took its slot.
FARM_WEIGHT_TRAJECTORY  = FARM_WEIGHT_DVM_PLUS

# ────────────────────────────────────────────────────────────────────────
# Farm Grade Tree (v2 composite — replaces the flat 10-component blend)
#
# Five main grades, each composed of 2 sub-grades, rolling into one
# composite. Weighted by signal strength: Development (controllable
# skill) and MLB Production (outcome proof) carry the most weight;
# Transactions is intentionally light because trade-acumen signal is
# real but small-sample. See `farm_report_card` glossary entry for the
# full tree shape.
# ────────────────────────────────────────────────────────────────────────
# v3 weights — merged Acquisitions + Transactions into a single
# "Acquisition Strategy" branch. Tree drops from 5 → 4 main branches.
# Development stays top-weighted (controllable skill); Acquisition
# Strategy and MLB Production tie at 25% (both are outcome axes).
FARM_TREE_WEIGHT_ACQUISITION_STRATEGY = 0.25
FARM_TREE_WEIGHT_DEVELOPMENT          = 0.35
FARM_TREE_WEIGHT_FINANCIAL            = 0.15
FARM_TREE_WEIGHT_MLB_PRODUCTION       = 0.25
# Back-compat aliases — anything that imported the v2 constants still
# works. The composite blend below uses the v3 names exclusively.
FARM_TREE_WEIGHT_ACQUISITIONS = FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
FARM_TREE_WEIGHT_TRANSACTIONS = 0.0   # rolled into Acquisition Strategy
# Sub-grades inside each parent — 50/50 for all parents in v1.
FARM_TREE_SUB_WEIGHT_EQUAL = 0.5

# Tiered FV → points. Anchored so an 80 ≈ "franchise piece" (worth ~100
# org-filler prospects) and 40 ≈ "pulse, barely". The shape is roughly
# geometric — each tier up is ~1.7-2× the previous. Tunable; the curve
# matters more than exact values.
FV_POINTS = {
    80: 100.0, 75: 70.0, 70: 50.0, 65: 30.0,
    60:  18.0, 55: 10.0, 50:  5.0, 45:  2.5,
    40:   1.0, 35:  0.3, 30:  0.1, 25: 0.05, 20: 0.0,
}


def _fv_to_points(fv: float | int | None) -> float:
    """Tiered FV → points. Interpolates linearly between tier boundaries so
    a 57.5 (between 55 and 60) returns the midpoint between FV_POINTS[55]
    and FV_POINTS[60]. Returns 0.0 for None / sub-20 inputs."""
    if fv is None:
        return 0.0
    try:
        v = float(fv)
    except (TypeError, ValueError):
        return 0.0
    if v <= 20:
        return 0.0
    if v >= 80:
        return FV_POINTS[80]
    lo = int(v // 5) * 5
    hi = lo + 5
    lo_pts = FV_POINTS.get(lo, 0.0)
    hi_pts = FV_POINTS.get(hi, lo_pts)
    frac = (v - lo) / 5.0
    return round(lo_pts + (hi_pts - lo_pts) * frac, 3)


# Hardcoded industry-standard FV → expected career WAR mapping.
# Anchored to FanGraphs / public research:
# https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/
# Each FV tier maps to a typical career WAR projection at MLB retirement.
# Used by _grad_wag() to compute WAR Above Grade per graduate, which then
# rolls up to the per-org Talent Translation report-card grade.
FV_EXPECTED_WAR = {
    80: 60.0,   # HOF-tier (10+ year stars)
    75: 40.0,
    70: 25.0,   # Perennial All-Star
    65: 17.0,
    60: 12.0,   # Strong everyday regular
    55:  6.0,
    50:  3.0,   # Average regular
    45:  1.5,
    40:  0.5,
    35:  0.1,
    30:  0.0,
    25:  0.0,
    20:  0.0,
}


def _fv_to_expected_war(fv: float | int | None) -> float | None:
    """Linear-interpolate FV (20-80) → expected career WAR via FV_EXPECTED_WAR.
    Returns None for None / out-of-range inputs so the caller can distinguish
    'no projection' from 'projected 0 WAR' (which is a valid 35-FV projection)."""
    if fv is None:
        return None
    try:
        v = float(fv)
    except (TypeError, ValueError):
        return None
    if v < 20 or v > 80:
        return None
    keys = sorted(FV_EXPECTED_WAR.keys())
    if v <= keys[0]:
        return FV_EXPECTED_WAR[keys[0]]
    if v >= keys[-1]:
        return FV_EXPECTED_WAR[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= v <= hi:
            t = (v - lo) / (hi - lo) if hi > lo else 0
            return round(FV_EXPECTED_WAR[lo] + t * (FV_EXPECTED_WAR[hi] - FV_EXPECTED_WAR[lo]), 2)
    return None


# Industry-standard draft pick-slot value curve (career WAR expectations
# based on FanGraphs / Baseball America surplus-value research). A
# 1st-overall pick has historically averaged ~9 career WAR; the curve
# decays steeply through the supplemental + 2nd round and tails to ~0
# by the late rounds. Used to compute "draft pick value above
# expectation" = actual_war − slot_expected_war, which credits orgs
# that beat the market at each pick slot (e.g., a 28th-rounder making
# the majors counts more than a #1 overall reaching the same outcome).
_PICK_SLOT_EXPECTED_WAR: list[tuple[int, float]] = [
    (1,    9.00),   # 1st overall — historical Trout-tier ceiling
    (5,    6.00),   # top 5 — All-Star floor
    (10,   4.00),   # top 10 — regular floor
    (20,   2.50),   # 1st round
    (35,   1.80),   # supplemental / late 1st
    (50,   1.20),   # mid-2nd
    (75,   0.80),   # late 2nd / 3rd
    (100,  0.55),   # 3rd-4th
    (150,  0.35),   # 4th-5th
    (200,  0.22),   # mid-rounds
    (300,  0.13),   # 6th-10th
    (500,  0.07),   # late rounds
    (10_000, 0.03), # undrafted / non-tracked tail
]


def _pick_slot_expected_war(pick_overall) -> float | None:
    """Step-lookup the historical expected career WAR for a draft slot.
    Returns None when the pick number is missing/invalid (e.g., IFA
    signing with no overall pick). The step function is a deliberate
    simplification over the smooth power curve — pick slots already
    quantize into round groupings, and the step boundaries align with
    common round breakpoints (top-5, top-10, 1st round, 2nd, etc.)."""
    if pick_overall is None:
        return None
    try:
        p = int(pick_overall)
    except (TypeError, ValueError):
        return None
    if p < 1:
        return None
    for threshold, war in _PICK_SLOT_EXPECTED_WAR:
        if p <= threshold:
            return war
    return _PICK_SLOT_EXPECTED_WAR[-1][1]


def _grad_wag(graduate_payload: dict) -> float | None:
    """WAG (WAR Above Grade) for one graduate: actual career WAR minus
    the FV-implied expected WAR at the time of graduation.

      WAG > 0 → graduate has outperformed their final prospect grade.
      WAG < 0 → graduate has underperformed.
      WAG = 0 → graduate is on the FV-implied trajectory.

    Returns None when career_war is unknown OR when fv_close is missing
    (e.g., a player who was never publicly graded). Distinct from
    'returned a 0' — None means 'no projection possible'."""
    cw = graduate_payload.get("career_war") or {}
    total_war = cw.get("career_war")
    fv_close = graduate_payload.get("fv_close_raw")
    if fv_close is None:
        fv_close = graduate_payload.get("fv_close")
    if total_war is None or fv_close is None:
        return None
    expected = _fv_to_expected_war(fv_close)
    if expected is None:
        return None
    return round(float(total_war) - expected, 2)


def _compute_breakout_score(points: list, tool_deltas: dict,
                            stat_flags: list, age_vs_level_diff: float | None) -> int | None:
    """0-100 composite identifying prospects positioned to break out
    next year. Equal-weight blend (Phase B1) of four signals:

      1. FV growth in last 12 months — latest consensus_fv_raw minus
         the most-recent point ≥ 365 days earlier. Scaled so +5 grade
         pts in 12mo maxes the axis.
      2. Age-vs-level (negative diff = young-for-level → bonus).
         Scaled so −2y maxes the axis, +2y zeroes it.
      3. Tool-development delta — mean across `tool_deltas[*].delta`.
         Scaled so a +5 mean grade move maxes the axis.
      4. Active green stat flags — count of `stat_flags[*].direction ==
         "up"`. Scaled so 4+ green flags max the axis.

    Each axis normalized to [0, 1], then averaged → multiplied by 100.
    Returns None when too few inputs are available to be meaningful
    (need at least 2 of the 4 axes resolvable).
    """
    from datetime import datetime, timedelta

    def _clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    axes: list[float] = []

    # 1. FV growth in last 12 months
    if points and len(points) >= 2:
        latest = points[-1]
        try:
            latest_dt = datetime.strptime(latest.snapshot_date, "%Y-%m-%d")
            cutoff = latest_dt - timedelta(days=365)
            prior = None
            for pt in reversed(points[:-1]):
                pt_dt = datetime.strptime(pt.snapshot_date, "%Y-%m-%d")
                if pt_dt <= cutoff:
                    prior = pt; break
            if prior is None:
                prior = points[0]  # fall back to oldest
            if (latest.consensus_fv_raw is not None
                    and prior.consensus_fv_raw is not None):
                delta_fv = latest.consensus_fv_raw - prior.consensus_fv_raw
                # +5 grade pts → 1.0; -5 → 0; linear between.
                axes.append(_clamp01((delta_fv + 5.0) / 10.0))
        except (ValueError, AttributeError):
            pass

    # 2. Age-vs-level
    if age_vs_level_diff is not None:
        # diff < 0 means YOUNG for level. -2y → 1.0; +2y → 0.0.
        axes.append(_clamp01((-age_vs_level_diff + 2.0) / 4.0))

    # 3. Tool-development delta mean
    if tool_deltas:
        deltas = [td.get("delta") for td in tool_deltas.values()
                  if td and td.get("delta") is not None]
        if deltas:
            mean_delta = sum(deltas) / len(deltas)
            # +5 mean grade pts → 1.0; -5 → 0.
            axes.append(_clamp01((mean_delta + 5.0) / 10.0))

    # 4. Green stat flags
    if stat_flags:
        n_green = sum(1 for f in stat_flags
                      if (f.get("direction") or "").lower() == "up")
        # 4+ green flags → 1.0; 0 → 0.0.
        axes.append(_clamp01(n_green / 4.0))

    # Require at least 2 axes resolvable for a meaningful composite.
    if len(axes) < 2:
        return None
    return int(round(sum(axes) / len(axes) * 100))


def _compute_tool_deltas(player_points: list[dict]) -> dict[str, dict]:
    """Per-tool lifetime delta for one prospect.

    Walks `player_points[i].tools_consensus` across the prospect's full
    history; for each tool with ≥2 observations, returns first/last
    grade, delta (latest − earliest), the dates that bracket the window,
    and the observation count. Tools with only one snapshot are skipped
    (no delta computable).

    Used downstream by:
      * `export_timeseries_json` → enrich each player payload with
        `tool_deltas`; the UI shows a +N / -N chip next to each tool
        grade on the prospect-detail page.
      * `_per_org_tool_dev_aggregates` → feed the per-org DvM+ rollup
        (HitDvM+, PowerDvM+, …, ToolsDvM+).
    """
    by_tool: dict[str, list[tuple[str, float]]] = {}
    for pt in player_points or []:
        tc = pt.get("tools_consensus") or {}
        date = pt.get("snapshot_date")
        for k, v in tc.items():
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            by_tool.setdefault(k, []).append((date, fv))
    out: dict[str, dict] = {}
    for k, obs in by_tool.items():
        if len(obs) < 2:
            continue
        obs.sort(key=lambda x: (x[0] or ""))
        first_date, first_v = obs[0]
        last_date, last_v = obs[-1]
        out[k] = {
            "delta":      round(last_v - first_v, 2),
            "first":      first_v,
            "last":       last_v,
            "first_date": first_date,
            "last_date":  last_date,
            "n_obs":      len(obs),
        }
    return out


# Per-tool DvM+ grouping. Most keys are 1:1 to a canonical tool from
# scrapers.HITTER_TOOL_KEYS / PITCHER_TOOL_KEYS; "power" averages
# game_pwr + raw_pwr for a single Power index that doesn't double-count.
TOOL_GROUPS: dict[str, list[str]] = {
    "hit":       ["hit"],
    "power":     ["game_pwr", "raw_pwr"],
    "speed":     ["speed"],
    "field":     ["field"],
    "arm":       ["throw"],
    "pitch_sel": ["pitch_sel"],
    "bat_ctrl":  ["bat_ctrl"],
    "fb":        ["fb"],
    "sl":        ["sl"],
    "cb":        ["cb"],
    "ch":        ["ch"],
    "cmd":       ["cmd"],
    "ct":        ["ct"],
}


def _top_end_points(prospects: list[dict], n: int = FARM_TOP_END_COUNT) -> float:
    """Sum of tiered points for the org's top N prospects (FV-sorted).
    Prospects list is expected pre-sorted by fv_raw descending — that
    matches how `m["prospects"]` is populated in `export_timeseries_json`."""
    return round(sum(_fv_to_points(p.get("fv_raw")) for p in prospects[:n]), 2)


def _depth_points(prospects: list[dict],
                  start: int = FARM_DEPTH_START,
                  end: int = FARM_DEPTH_END) -> float:
    """Sum of tiered points for prospects ranked `start+1` through `end`."""
    return round(sum(_fv_to_points(p.get("fv_raw")) for p in prospects[start:end]), 2)


def _trajectory_score(fv_history: list[dict],
                      lookback_days: int = FARM_TRAJECTORY_LOOKBACK_DAYS,
                      smooth_window: int = FARM_TRAJECTORY_SMOOTH_WINDOW,
                      as_of: "date | None" = None) -> float:
    """Smoothed FV trajectory: mean of last `smooth_window` history points
    minus mean of `smooth_window` points ending at/near the lookback cutoff.

    Smoothing on both ends dilutes any single source's update — the user
    complaint about the old `_rolling_fv_delta` was that one swing from
    one source dominated the signal. Averaging 3 points on each end
    reduces that to ~33% of the result."""
    if not fv_history or len(fv_history) < 2:
        return 0.0
    today = as_of or date.today()
    cutoff = (today - timedelta(days=lookback_days)).isoformat()

    k = min(smooth_window, len(fv_history))
    recent_mean = sum(p["total_fv"] for p in fv_history[-k:]) / k

    baseline_candidates = [p for p in fv_history if p["date"] <= cutoff]
    if not baseline_candidates:
        # Whole history is inside the window — baseline against the earliest
        # points so we still report a directionally-correct change.
        baseline_candidates = fv_history[:k]
    bk = min(smooth_window, len(baseline_candidates))
    baseline_mean = sum(p["total_fv"] for p in baseline_candidates[-bk:]) / bk

    return round(recent_mean - baseline_mean, 1)


def _grad_pipeline_score(fv_events: list[dict],
                         months: int = FARM_GRAD_PIPELINE_MONTHS,
                         as_of: "date | None" = None) -> float:
    """FV-weighted graduations in the trailing window. Each grad's FV at
    graduation time contributes its tiered point value — so promoting a
    60 FV is worth ~18 points and a 40 FV is worth 1."""
    if not fv_events:
        return 0.0
    today = as_of or date.today()
    cutoff = (today - timedelta(days=months * 30)).isoformat()
    total = 0.0
    for e in fv_events:
        if e.get("kind") != "graduation":
            continue
        if (e.get("date") or "") < cutoff:
            continue
        total += _fv_to_points(e.get("fv"))
    return round(total, 2)


def _rank_percentile(values: list[float]) -> list[float]:
    """Convert a list of scores to rank percentiles in [0, 1] where 1.0 is
    the best (highest input). Ties get the average percentile of the tied
    rank block so two identical farms don't fight over a tiebreaker that
    isn't really there.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    indexed = sorted(range(n), key=lambda i: values[i], reverse=True)
    pct = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        # tied block covers ranks [i+1 .. j+1]; assign the average percentile
        avg_rank = (i + j) / 2 + 1  # 1-based midpoint
        share = (n - avg_rank) / (n - 1)
        for k in range(i, j + 1):
            pct[indexed[k]] = share
        i = j + 1
    return pct


def _normalize_to_100(values: list[float]) -> list[float]:
    """Map values to a 0-100 scale anchored at the 5th/95th percentile of
    the input list. Values outside that range clamp to 0 or 100. Percentile
    anchors (instead of min/max) keep one outlier from flattening the rest
    of the distribution into a tiny band."""
    if not values:
        return []
    if len(values) == 1:
        return [100.0]
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lo_idx = max(0, int(round(n * 0.05)) - 1)
    hi_idx = min(n - 1, int(round(n * 0.95)) - 1)
    if hi_idx <= lo_idx:
        lo_idx, hi_idx = 0, n - 1
    lo = sorted_vals[lo_idx]
    hi = sorted_vals[hi_idx]
    rng = hi - lo
    if rng <= 0:
        return [50.0] * len(values)
    return [round(max(0.0, min(100.0, (v - lo) / rng * 100.0)), 1) for v in values]


# Letter-grade buckets calibrated for ~30 orgs. The skew is intentional —
# A+ is reserved for the #1 farm, "A" tier covers the top ~20%, and the
# bottom ~7% gets a D. We don't issue Fs (in a 30-team distribution it
# feels punitive for what's just "the worst of the bunch").
def _letter_grade(rank: int, n: int) -> str:
    if n <= 0 or rank is None:
        return "—"
    if rank == 1:
        return "A+"
    if n == 1:
        return "A+"
    pct = (rank - 1) / (n - 1)
    if pct < 0.10: return "A"
    if pct < 0.20: return "A-"
    if pct < 0.30: return "B+"
    if pct < 0.45: return "B"
    if pct < 0.60: return "B-"
    if pct < 0.72: return "C+"
    if pct < 0.85: return "C"
    if pct < 0.95: return "C-"
    return "D"


def _rank_descending(values: list[float]) -> list[int]:
    """Return 1-based ranks where the largest input gets rank 1. Ties get
    the same rank (their shared best-of-block rank — `[5, 5, 3]` →
    `[1, 1, 3]`)."""
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(range(n), key=lambda i: values[i], reverse=True)
    ranks = [0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[indexed[k]] = i + 1
        i = j + 1
    return ranks


def _build_org_fv_history(
    players: list[PlayerTimeseries],
    filter_real_trades,
    trades_by_player: dict[str, list[dict]],
) -> dict[str, dict]:
    """
    Build per-org cumulative **development** FV time series + events.

    The series tracks how each org's prospects grow ABOVE their baseline
    FV at the time they entered the org — so incoming acquisitions
    (trades, draft, IFA) contribute zero on the day they arrive; only
    subsequent FV growth (or decline) shows up on the line.

    Algorithm:
      1. Walk each player's chronological stream (snapshots + trades +
         graduations).
      2. On the FIRST snapshot we see while a player is in a given org,
         record that org's entry baseline for the player (no contribution
         to the running total on that date — just plant a marker).
      3. On subsequent snapshots in the same org, contribute the delta
         from the prior snapshot (`new_fv - prev_fv`). This is the org's
         development credit for that player.
      4. On a trade, the source org's accumulated development credit
         stays in their cumulative chart (development credit is
         permanent — an org doesn't lose past credit for trading a
         developed prospect away). The receiving org records a new
         entry baseline at the player's current FV and only future
         snapshots in that org count.
      5. Graduations don't subtract — the org keeps credit for whatever
         development happened before the player exited the system.

    Returns:
      {
        "ATL": {
          "series": [{"date": "2024-01-04", "total_fv": 0.0}, ...],
          "events": [{"date": "2024-07-30", "kind": "trade", "player_name":
                      "Drew Jones", "fv": 50.0, "other_org": "MIA"},
                     {"date": "2025-04-01", "kind": "graduation",
                      "player_name": "Spencer Schwellenbach", "fv": 55.0},
                      ...],
        },
        ...
      }

    `series.total_fv` here is interpreted as "cumulative DEVELOPMENT-FV"
    rather than "cumulative roster FV". Event markers (trade in/out,
    graduation) still annotate the chart even though they don't move
    the line.
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
        # Per-org "have we set the baseline yet?" flag. The first
        # snapshot we see for the player in a given org plants the
        # baseline (no contribution); subsequent snapshots credit the
        # delta. Trades-in reset this for the receiving org so the
        # acquisition itself contributes nothing — only future
        # development credits the new org.
        baselined: set[str] = set()
        for ev in stream:
            d = ev[0]
            kind = ev[1]
            if kind == "snapshot":
                new_fv = ev[2]
                if org_now not in baselined:
                    # First snapshot for this player while in this org —
                    # plant the entry baseline. Add the date to the org's
                    # series so the chart has a starting point on the day
                    # the org first "saw" the player, but contribute 0.
                    baselined.add(org_now)
                    dates_by_org[org_now].add(d)
                else:
                    delta = new_fv - fv_now
                    if delta != 0:
                        contribs[(org_now, d)] += delta
                        dates_by_org[org_now].add(d)
                fv_now = new_fv
            elif kind == "trade":
                from_org, to_org = ev[2], ev[3]
                # If from_org doesn't match our tracked org_now (rare,
                # e.g. stale inference), trust the API record.
                source_org = org_now if org_now == from_org else from_org
                # Development credit is PERMANENT — the source org keeps
                # whatever development they earned before the trade. The
                # receiving org records a baseline at the player's current
                # FV and only future snapshots count. Both sides get an
                # event marker for chart annotation; neither side moves
                # the cumulative line on this date.
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
                # Treat the receiving org as "baselined" immediately —
                # the trade itself sets the baseline (fv_now), and the
                # next snapshot will credit only growth above it.
                baselined.add(to_org)
            elif kind == "graduation":
                # Graduation is a successful exit — the org keeps the
                # development credit they earned, the line stays flat
                # through the event. Marker is annotated for the chart.
                events_by_org[org_now].append({
                    "date": d, "kind": "graduation",
                    "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                })

    # Convert per-org contribs to running-sum series.
    # Under the development-only model the line legitimately starts at
    # 0 (no development credit yet) and may stay flat for stretches —
    # so we keep every recorded date, including leading zeroes, rather
    # than skipping ahead to the first non-zero point.
    result: dict[str, dict] = {}
    for org, dates in dates_by_org.items():
        running = 0.0
        series = []
        for d in sorted(dates):
            running += contribs[(org, d)]
            series.append({"date": d, "total_fv": round(running, 1)})
        events = sorted(events_by_org.get(org, []),
                        key=lambda e: (e["date"], e["kind"]))
        result[org] = {"series": series, "events": events}
    return result


def export_timeseries_json(timeseries: list[PlayerTimeseries], out_path: Path,
                          statlines: dict[str, dict] | None = None,
                          pitch_arsenals: dict[str, dict] | None = None,
                          sabermetrics: dict[str, dict] | None = None,
                          trades_by_player: dict[str, list[dict]] | None = None,
                          transactions_by_player: dict[str, list[dict]] | None = None,
                          career_stats: dict[str, list[dict]] | None = None,
                          career_war: dict[str, dict] | None = None,
                          acquisitions: dict[str, dict] | None = None,
                          il_status: dict[str, dict] | None = None,
                          rosters_by_org: dict[str, dict[str, list[dict]]] | None = None,
                          level_changes: dict[str, list[dict]] | None = None,
                          roster_status: dict[str, dict] | None = None,
                          ifa_spending_by_org: dict[str, dict[int, dict]] | None = None,
                          contracts_by_key: dict[str, dict] | None = None,
                          draft_pools: dict | None = None,
                          player_ids: dict[str, int] | None = None,
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
    transactions_by_player = transactions_by_player or {}
    career_stats = career_stats or {}
    career_war = career_war or {}
    acquisitions = acquisitions or {}
    il_status = il_status or {}
    rosters_by_org = rosters_by_org or {}
    level_changes = level_changes or {}
    roster_status = roster_status or {}
    ifa_spending_by_org = ifa_spending_by_org or {}
    contracts_by_key = contracts_by_key or {}
    draft_pools = draft_pools or {}
    player_ids = player_ids or {}
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
    from stat_flags import compute_stat_flags, compute_tool_flags

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

    roster_org_by_key: dict[str, str] = {}
    for org_code, levels in rosters_by_org.items():
        for recs in levels.values():
            for rec in recs or []:
                key = rec.get("player_key")
                if key and key not in roster_org_by_key:
                    roster_org_by_key[key] = org_code

    def _derived_graduation_date(p: PlayerTimeseries) -> str | None:
        """
        Resolve a graduate's displayed graduation date.

        Priority (highest first):
          1. roster_status.mlb_debut_date — the MLB API's authoritative
             mlbDebutDate (via PlayerIndex). Trusted directly; the
             `_display_graduation_date` wrapper below converts an
             obviously-offseason October–December date to a mid-season
             placeholder because in practice those values mean "40-man
             selection" rather than "first MLB game".
          2. The stored graduation_date IF it falls inside the player's
             first MLB season — a FG "graduates" snapshot taken mid-
             season of the debut year is the cleanest signal we have
             when the API has no debut date for the player.
          3. {first_MLB_season}-07-01 — last-resort mid-season placeholder.
          4. p.graduation_date as-is for the very rare case where we
             have nothing else to anchor to (international free agents
             like Senga / Yoshida with no MiLB rows in our cache).
        """
        rs = roster_status.get(p.player_key) or {}
        api_debut = rs.get("mlb_debut_date")

        rows = career_stats.get(p.player_key, []) or []
        mlb_years = sorted(
            int(r["season"]) for r in rows
            if r.get("level") == "MLB" and r.get("season")
        )

        if api_debut:
            try:
                api_d = date.fromisoformat(api_debut)
            except ValueError:
                api_d = None
            # Rule 5 protection trap: the MLB API sometimes stores the
            # Rule 5 deadline (~Nov 18-20) as mlbDebutDate for players
            # who were 40-man-added that day but didn't actually play
            # until the following season. Detect this when the API date
            # is in the offseason AND career_stats shows the player's
            # first MLB season is a later year — roll forward to that
            # season's mid-year placeholder so dozens of players don't
            # clump onto the same Rule 5 deadline date.
            if (api_d and api_d.month >= 10
                    and mlb_years and mlb_years[0] > api_d.year):
                first_year = mlb_years[0]
                if first_year == date.today().year:
                    return date.today().isoformat()
                return f"{first_year}-07-01"
            return api_debut

        if not mlb_years:
            return p.graduation_date
        first_year = mlb_years[0]
        if p.graduation_date and p.graduation_date.startswith(f"{first_year}-"):
            return p.graduation_date
        if first_year == date.today().year:
            return date.today().isoformat()
        return f"{first_year}-07-01"

    def _display_graduation_date(p: PlayerTimeseries) -> str | None:
        """
        Avoid showing an obviously-offseason snapshot date as the
        graduation date.

        Two distinct offseason patterns to defend against:
          * FG's "Graduates" page is sometimes captured in October or
            November — that snapshot date is not the player's debut.
          * The MLB API occasionally stores a Rule 5 protection day
            (mid-November) as `mlbDebutDate`.

        We only collapse to a {year}-07-01 placeholder when the
        offseason date does NOT correspond to a real MLB season the
        player actually played in. Legit late-season debuts (Oct 1-5 is
        the regular-season end week) are kept as-is.
        """
        grad = _derived_graduation_date(p)
        if not grad:
            return grad
        try:
            d = date.fromisoformat(grad)
        except ValueError:
            return grad
        if d.month < 10:
            return grad
        # Offseason-looking date. Trust it if career_stats shows the
        # player actually played MLB that same year — otherwise collapse
        # to the mid-season placeholder.
        rows = career_stats.get(p.player_key, []) or []
        mlb_years = {
            int(r["season"]) for r in rows
            if r.get("level") == "MLB" and r.get("season")
        }
        if d.year in mlb_years:
            return grad
        return f"{d.year}-07-01"

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
        "purchased contract",          # Rule 5 wording omits "the"
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
        (("purchased the contract", "purchased contract",
          "purchase of the contract"),                                "contract_purchase"),
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

    def _latest_post_graduation_org(p: PlayerTimeseries,
                                    filtered_trades: list[dict]) -> str | None:
        """Pick the org a graduate is currently on by walking every
        post-graduation move on record.

        Today's bug surfaced via Otto Lopez: he was traded TOR → SFG on
        2024-02-13 (a real bilateral trade), then DFA'd by SFG on
        2024-04-01, then claimed off waivers by MIA on 2024-04-04. The
        waiver claim is on `p.transactions[]`, NOT `filtered_trades`
        (which only carries bilateral trades). Looking at trades alone
        returned SFG — leaving Otto on the Giants in the UI when he was
        actually a Marlin.

        Fix: union the post-grad cross-org events from BOTH sources,
        sort by date, take the latest. Then collapse short bounce chains
        — if the latest event came from an intermediate org the player
        only briefly belonged to (< 90 days), surface the stable origin
        instead. Otto's chain becomes TOR → MIA rather than SFG → MIA.
        """
        grad = _display_graduation_date(p) or p.graduation_date
        if not grad:
            return None
        events: list[tuple[str, str, str]] = []  # (date, from_org, to_org)
        for t in filtered_trades or []:
            d = t.get("trade_date") or ""
            if d > grad and t.get("to_org"):
                events.append((d, t.get("from_org") or "", t.get("to_org")))
        cross_org_kinds = ("rule_5_return", "waiver_claim",
                           "contract_purchase", "signed_free_agent",
                           "rule_5", "waiver")
        tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        for tx in tx_rows:
            kind = tx.get("kind")
            if kind not in cross_org_kinds:
                continue
            d = tx.get("date") or ""
            if d <= grad:
                continue
            to_code = (canonical_org(tx.get("to_team_name"))
                       or canonical_org(tx.get("to_team")))
            from_code = (canonical_org(tx.get("from_team_name"))
                         or canonical_org(tx.get("from_team")))
            if not to_code or to_code == from_code:
                continue
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            events.append((d, from_code or "", to_code))
        if not events:
            return None
        events.sort()  # latest is last
        return events[-1][2]

    # Bounce-chain collapse window — when a player passes through a
    # short-tenure intermediate org en route to their current home, we
    # roll the org-change message up to the stable prior org. 90 days
    # captures DFA→trade→DFA→waiver chains without lumping in a real
    # half-season stint at the intermediate club.
    _BOUNCE_WINDOW_DAYS = 90

    def _collapse_bounce_chain(latest_event: dict | None,
                               all_events: list[dict]) -> dict | None:
        """Walk backward from `latest_event` through events where the
        chosen `from_org` was itself acquired by that org within
        _BOUNCE_WINDOW_DAYS earlier. Returns a copy of `latest_event`
        with `from_org` replaced by the stable origin (and a
        `bounce_via` list recording the skipped intermediaries with
        their durations) — or the original event if no collapse fires.
        """
        from datetime import date as _date
        if not latest_event:
            return latest_event
        events = sorted(
            [e for e in (all_events or []) if e.get("date") and e.get("to_org")],
            key=lambda e: e["date"],
        )
        cur = dict(latest_event)
        bounce_via: list[dict] = []
        max_loops = 5  # cheap safety against pathological data
        while max_loops:
            max_loops -= 1
            from_org = cur.get("from_org")
            if not from_org:
                break
            # Find the most recent earlier event where the player ARRIVED
            # at `from_org`. If that arrival date is < window days before
            # `cur.date`, the from_org was a brief stopover — collapse.
            cur_d = cur.get("date") or ""
            try:
                cur_dt = _date.fromisoformat(cur_d)
            except (TypeError, ValueError):
                break
            prior = None
            for e in events:
                if (e.get("to_org") == from_org
                        and e.get("date") and e["date"] < cur_d):
                    prior = e  # iterate forward so last match wins
            if not prior:
                break
            try:
                prior_dt = _date.fromisoformat(prior["date"])
            except (TypeError, ValueError):
                break
            gap_days = (cur_dt - prior_dt).days
            if gap_days >= _BOUNCE_WINDOW_DAYS:
                break  # this from_org was a real tenure, stop walking
            bounce_via.append({
                "org": from_org,
                "days": gap_days,
                "arrived": prior["date"],
            })
            cur["from_org"] = prior.get("from_org") or ""
        if bounce_via:
            cur["bounce_via"] = bounce_via
        return cur

    # Static allowlist of MLB 3-letter org codes used to gate the
    # transaction-based org override. `canonical_org()` passes through
    # affiliate names it can't resolve (e.g. "Sugar Land Space Cowboys"
    # stays as that string), so we whitelist by the known MLB codes
    # rather than trusting the canonicalization output blind.
    _MLB_ORG_CODES_FOR_OVERRIDE = frozenset({
        "ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE",
        "COL", "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN",
        "NYM", "NYY", "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR",
        "TEX", "TOR", "WSN",
    })

    def _latest_cross_org_transaction(p: PlayerTimeseries) -> str | None:
        """Return the to_org of the player's most-recent cross-org
        transaction (Rule 5 return, waiver claim, contract purchase
        across teams, FA signing) IF that transaction post-dates every
        snapshot we have on file AND resolves to a known MLB-org code.

        The snapshot-derived `p.org` lags reality for events the
        ranking sources haven't refreshed against yet — most commonly
        Rule 5 returns mid-season, where a player gets shipped back to
        his original org but the FV-ranking sites still show him with
        the team that drafted him. We bridge the gap by trusting the
        MLB Stats API transaction record. The MLB-code gate prevents
        accidentally writing an affiliate name (e.g. a Triple-A team
        name from a contract-purchase to Sugar Land) into the org
        field."""
        tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        if not tx_rows:
            return None
        cross_org_kinds = ("rule_5_return", "waiver_claim", "contract_purchase",
                           "signed_free_agent")
        relevant = []
        for tx in tx_rows:
            if tx.get("kind") not in cross_org_kinds:
                continue
            from_code = canonical_org(tx.get("from_team_name"))
            to_code = canonical_org(tx.get("to_team_name"))
            if not from_code or not to_code:
                continue
            if from_code == to_code:
                continue
            # Both endpoints must resolve to known MLB codes — affiliate
            # names that canonical_org passes through get rejected here.
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            relevant.append((tx, to_code))
        if not relevant:
            return None
        latest_tx, latest_code = max(relevant, key=lambda x: x[0].get("date") or "")
        latest_date = latest_tx.get("date") or ""
        if not latest_date:
            return None
        # Only override when the transaction is newer than EVERY snapshot
        # we have on file. If the rankings already moved the player, we
        # trust them (they may have caught a subsequent trade).
        latest_snap_date = max(
            (pt.snapshot_date for pt in p.points if pt.snapshot_date),
            default="",
        )
        if latest_date <= latest_snap_date:
            return None
        return latest_code

    # Phrases that flag the underlying surgery in an IL stint's
    # description / reason text. Matched case-insensitively; substring
    # match is fine because the API descriptions are verbose ("recovery
    # from Tommy John surgery", "Left UCL surgery", etc.). "UCL sprain"
    # is intentionally NOT in this set — a sprain isn't a confirmed TJ.
    _TJ_PHRASES = (
        "tommy john",
        "ucl surgery",
        "ulnar collateral ligament surgery",
        "internal brace",          # often the modern hybrid UCL repair
        "ucl reconstruction",
    )

    def _derive_health_profile(injury_history: list[dict],
                                today: "date | None" = None) -> dict:
        """Derive aggregate injury signals used by the UI + ETA model.

        Looks at:
          * Number of distinct IL stints in the trailing 12 months —
            anything >= 3 indicates a chronic injury pattern.
          * Total IL days in the trailing 12 months — separate signal
            from stint count so a single multi-month IL still counts.
          * Whether the player has had Tommy-John-class elbow surgery
            on record (any stint description matches _TJ_PHRASES). The
            chip on the prospect page surfaces this prominently, and
            ETA can be padded for the typical 12-18 month recovery.

        Open stints (active === True) count toward both metrics
        because an actively-injured player is currently lost playing
        time — but the days for an open stint reflect what's elapsed
        so far, not the full eventual stint length.
        """
        from datetime import date as _date, timedelta as _td
        today = today or _date.today()
        cutoff = today - _td(days=365)
        recent_stints = 0
        recent_days = 0
        tj_dates: list[str] = []
        for stint in injury_history or []:
            since_str = stint.get("since") or ""
            try:
                since = _date.fromisoformat(since_str)
            except (TypeError, ValueError):
                continue
            if since >= cutoff:
                recent_stints += 1
                days = stint.get("days") or 0
                if not days and stint.get("active"):
                    # Open stint without a closed-stint days field — estimate
                    # as (today - since). Cap at the trailing-window length
                    # (~365d) so a stale open stint whose activation row
                    # never landed in the API can't blow the total up.
                    days = max(0, (today - since).days)
                # Cap any single stint at the 12-month window length to
                # prevent old data anomalies from inflating the headline.
                _MAX_PER_STINT_DAYS = 365
                if days > _MAX_PER_STINT_DAYS:
                    days = _MAX_PER_STINT_DAYS
                recent_days += int(days or 0)
            desc = " ".join([
                str(stint.get("description") or ""),
                str(stint.get("reason") or ""),
            ]).lower()
            if any(p in desc for p in _TJ_PHRASES):
                tj_dates.append(since_str)
        tj_latest = max(tj_dates) if tj_dates else None
        # Final aggregate cap: the trailing-12-month window is itself ~365
        # days long, so the SUM of IL days within that window can't
        # exceed 365. Multiple overlapping stints (rare but possible from
        # transferred 15→60 day rows) could otherwise double-count.
        if recent_days > 365:
            recent_days = 365
        return {
            "il_stints_12mo": recent_stints,
            "il_days_12mo":   recent_days,
            "is_post_tj":     bool(tj_dates),
            # Latest TJ-class surgery date. The UI uses it to label the
            # chip ("Post-TJ · 2024-09-03"); the ETA helper checks it
            # against today to decide whether to apply a recovery delay.
            "tj_surgery_date": tj_latest,
        }

    def _active_display_org(p: PlayerTimeseries) -> str | None:
        # Canonicalize at the display layer so historical snapshots with
        # pre-rename codes (e.g. "OAK" before the Athletics dropped Oakland)
        # collapse onto the current canonical key ("ATH") rather than
        # showing up as a second farm-page entry.
        #
        # A recent cross-org transaction (Rule 5 return, waiver claim,
        # contract purchase across teams) overrides the snapshot-derived
        # org because the FV-ranking sources usually lag those moves by
        # weeks; trusting the MLB transactions record keeps the team
        # logo on the player card pointing at where they actually play.
        tx_override = _latest_cross_org_transaction(p)
        if tx_override:
            return tx_override
        return canonical_org(p.org or roster_org_by_key.get(p.player_key))

    def _display_org(p: PlayerTimeseries,
                     filtered_trades: list[dict]) -> str | None:
        if p.status == "graduated":
            return canonical_org(
                _latest_post_graduation_org(p, filtered_trades)
                or graduate_mlb_org_by_key.get(p.player_key)
                or roster_org_by_key.get(p.player_key)
                or p.org
            )
        return _active_display_org(p)

    def _level_changes_with_debut(player_key: str) -> list[dict]:
        """Return the player's level_changes with a `kind: "debut"` row
        pointing at the prospect's actual MLB debut date.

        We gate on `roster_status.mlb_debut_date` being set — that field
        is sourced from the MLB API's authoritative `mlbDebutDate` and
        falls back to the first contract-selection date only when the
        career rows confirm real MLB activity. A 40-man-only Rule 5
        protection will NOT have a debut date, so no debut row gets
        rendered even though the SE transaction may have produced a
        spurious MiLB→MLB promotion in level_changes.
        """
        rows = list(level_changes.get(player_key, []) or [])
        rs = roster_status.get(player_key) or {}
        debut_date = rs.get("mlb_debut_date")
        if not debut_date:
            return rows

        # Find the level_changes row dated closest to the debut date —
        # usually the contract-selection row will match exactly. If we
        # find one within a few days of the authoritative debut date,
        # convert it in place. Otherwise prepend a synthetic row.
        from datetime import date as _date
        try:
            debut_d = _date.fromisoformat(debut_date)
        except ValueError:
            debut_d = None
        match_idx = None
        if debut_d is not None:
            best_diff = 8  # days
            for i, r in enumerate(rows):
                if r.get("to_level") != "MLB":
                    continue
                try:
                    d = _date.fromisoformat(r.get("date") or "")
                except ValueError:
                    continue
                diff = abs((d - debut_d).days)
                if diff <= best_diff:
                    best_diff = diff
                    match_idx = i

        if match_idx is not None:
            marked = dict(rows[match_idx])
            marked["kind"] = "debut"
            marked["is_debut"] = True
            marked["date"] = debut_date  # snap to the authoritative date
            rows[match_idx] = marked
        else:
            rows.append({
                "date": debut_date,
                "kind": "debut",
                "is_debut": True,
                "from_level": None,
                "to_level": "MLB",
                "from_team": None,
                "to_team": None,
            })
        return rows

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
        # Health profile: 12-month IL stints + days + Tommy-John flag.
        # Computed once from the cached injury_history so the rest of
        # the pipeline (ETA model, stat_flags injury-prone rule, UI
        # chip) can pull from one dict instead of re-parsing dates.
        rs = roster_status.get(p.player_key) or {}
        health = _derive_health_profile(rs.get("injury_history") or [])
        eta = estimate_eta(
            level, age, is_pitcher, latest_fv, sl,
            expected_ages=age_baselines,
            ops_norm=ops_norms,
            era_norm=era_norms,
            health=health,
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
                    # Peripheral STF+ (K%, BB%, HR/9 vs level mean). Replaces
                    # the scouting-grade composite as the headline STF+ chip;
                    # the scouting composite is still computed in tools.* but
                    # gets relabeled "Stuff grade+" in the UI.
                    stf_periph = _compute_peripheral_stf_plus(sl_out, norms_perf)
                    if stf_periph is not None:
                        sl_out["stf_plus_periph"] = stf_periph
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

        # Scouting flags — green/red rate-stat indicators driven by the
        # current statline + the level norms we already built. Skipped for
        # players whose statline didn't pass the sample-size gate (see
        # stat_flags.MIN_GAMES_HITTER / MIN_IP_PITCHER); the function
        # returns [] in that case so the field is safe to render
        # unconditionally on the prospect detail page.
        flags = compute_stat_flags(sl_out, level_norms, health=health)

        # Tool grades — consensus across sources at the latest point.
        # `tools.grades` carries the per-tool 20-80 consensus; `tools.
        # composite_*` are derived in _compute_tool_composites. The X+
        # indices are stamped in a second pass once cohort norms are
        # known (see _attach_tool_plus_indices at the end of this
        # function). `tool_flags` mirror stat_flags shape and ride the
        # same green/red renderer in the UI.
        latest_point = p.points[-1] if p.points else None
        tool_consensus_grades = (
            dict(latest_point.tools_consensus)
            if latest_point and latest_point.tools_consensus
            else None
        )
        tools_payload = _compute_tool_composites(tool_consensus_grades, is_pitcher)
        if tools_payload is not None:
            publishing = []
            if latest_point:
                for src, info in (latest_point.per_source or {}).items():
                    if info and info.get("tools"):
                        publishing.append(src)
            tools_payload["publishing_sources"] = sorted(publishing)
            if latest_point and latest_point.tools_spread:
                tools_payload["spread"] = dict(latest_point.tools_spread)
            else:
                tools_payload["spread"] = {}
            # Two-way player detection: when both hitter AND pitcher
            # canonical tool keys appear in the consensus grades, emit
            # both payloads so the UI can render two Tools cards stacked
            # (e.g., Reggie Crawford, Ohtani). The position-inferred
            # default payload (above) stays populated for legacy UI paths.
            if tool_consensus_grades:
                has_hitter = any(k in tool_consensus_grades for k in HITTER_TOOL_KEYS)
                has_pitcher = any(k in tool_consensus_grades for k in PITCHER_TOOL_KEYS)
                if has_hitter and has_pitcher:
                    hitter_payload = _compute_tool_composites(
                        tool_consensus_grades, is_pitcher=False)
                    pitcher_payload = _compute_tool_composites(
                        tool_consensus_grades, is_pitcher=True)
                    if hitter_payload is not None:
                        tools_payload["hitter_payload"] = hitter_payload
                    if pitcher_payload is not None:
                        tools_payload["pitcher_payload"] = pitcher_payload
            # Time-series + per-source history. The UI uses these to
            # render the "Source-by-source tool history" dropdown and to
            # disclose that Tools+ uses each source's most recent
            # publication (older rows are kept for context, not math).
            #
            # `history`: consensus tool grades at each snapshot date.
            # `source_history`: per-source publication timeline.
            # `source_recency`: latest publication date + stale flag per source.
            history_entries: list[dict] = []
            source_history: dict[str, list[dict]] = {}
            for pt in (p.points or []):
                pt_per_src = pt.per_source or {}
                pt_consensus = pt.tools_consensus or {}
                # Walk each source's published tools at this point.
                for src, info in pt_per_src.items():
                    if not info:
                        continue
                    src_tools = info.get("tools") or {}
                    if not isinstance(src_tools, dict):
                        continue
                    # Filter out _extras + non-numeric junk.
                    numeric = {k: v for k, v in src_tools.items()
                               if k != "_extras" and isinstance(v, (int, float))}
                    if not numeric:
                        continue
                    # Use the SOURCE's actual publication date (info.snapshot_date),
                    # not the consensus-point date (pt.snapshot_date). Forward-fill
                    # carries each source's latest snapshot into every later
                    # consensus point — without this, a stale source would appear
                    # to have published at every consensus date after its last
                    # real update, corrupting the LATEST/STALE logic.
                    src_snapshot_date = info.get("snapshot_date") or pt.snapshot_date
                    source_history.setdefault(src, []).append({
                        "snapshot_date": src_snapshot_date,
                        "interval_label": info.get("interval_label")
                                          or pt.interval_label,
                        "grades": numeric,
                        "extras_present": bool(
                            isinstance(src_tools.get("_extras"), dict)
                            and src_tools["_extras"]
                        ),
                    })
                # Consensus snapshot — append once per point that produced
                # any tool consensus.
                if pt_consensus:
                    contributing = [src for src, info in pt_per_src.items()
                                    if info and info.get("tools")]
                    history_entries.append({
                        "snapshot_date": pt.snapshot_date,
                        "interval_label": pt.interval_label,
                        "consensus": dict(pt_consensus),
                        "sources": sorted(contributing),
                    })
            # Dedupe source_history per source by (date, interval_label) —
            # forward-fill carries the same snapshot forward many times.
            for src in list(source_history.keys()):
                seen = set()
                deduped = []
                for entry in source_history[src]:
                    key = (entry["snapshot_date"], entry["interval_label"])
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(entry)
                # Newest-first so the latest row sits at the top of the
                # rendered table.
                deduped.sort(key=lambda e: e["snapshot_date"], reverse=True)
                source_history[src] = deduped
            if history_entries:
                # Newest-first for the consensus timeline too.
                history_entries.sort(key=lambda e: e["snapshot_date"], reverse=True)
                tools_payload["history"] = history_entries
            if source_history:
                tools_payload["source_history"] = source_history
                # Recency: latest publication per source + stale flag.
                today_iso = date.today().isoformat()
                source_recency: dict[str, dict] = {}
                for src, entries in source_history.items():
                    if not entries:
                        continue
                    latest = entries[0]["snapshot_date"]
                    try:
                        d_latest = date.fromisoformat(latest)
                        stale_days = (date.fromisoformat(today_iso) - d_latest).days
                    except ValueError:
                        stale_days = None
                    source_recency[src] = {
                        "latest_date": latest,
                        "stale_days": stale_days,
                        "is_stale": (stale_days is not None
                                     and stale_days > TOOL_FRESHNESS_DAYS),
                    }
                tools_payload["source_recency"] = source_recency
        tool_flags = compute_tool_flags(tools_payload, is_pitcher)

        filtered_trades = _filter_real_trades(trades_by_player.get(p.player_key, []))
        acq = acquisitions.get(p.player_key)
        # Build the unified post-acquisition event list: real trades +
        # cross-org transactions (waivers, Rule 5, contract purchases,
        # FA signings). Sorted by date so [-1] is the latest. Each entry
        # carries a `kind` so the method classifier can prefer the
        # transaction-derived label over verb-matching the trade
        # description when there's a more recent non-trade event.
        _all_acq_events: list[dict] = []
        for t in filtered_trades:
            _all_acq_events.append({
                "kind": "trade",
                "date": t.get("trade_date"),
                "from_org": t.get("from_org"),
                "to_org": t.get("to_org"),
                "description": t.get("description"),
            })
        _cross_org_tx_kinds = ("rule_5_return", "waiver_claim",
                               "contract_purchase", "signed_free_agent",
                               "rule_5", "waiver")
        _tx_method_map = {
            "waiver_claim": "waiver", "waiver": "waiver",
            "rule_5": "rule_5", "rule_5_return": "rule_5",
            "contract_purchase": "contract_purchase",
            "signed_free_agent": "free_agent",
        }
        for tx in (transactions_by_player or {}).get(p.player_key, []):
            kind = tx.get("kind")
            if kind not in _cross_org_tx_kinds:
                continue
            to_code = (canonical_org(tx.get("to_team_name"))
                       or canonical_org(tx.get("to_team")))
            from_code = (canonical_org(tx.get("from_team_name"))
                         or canonical_org(tx.get("from_team")))
            if not to_code or to_code == from_code:
                continue
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            _all_acq_events.append({
                "kind": _tx_method_map.get(kind, "trade"),
                "date": tx.get("date"),
                "from_org": from_code,
                "to_org": to_code,
                "description": tx.get("description"),
            })
        _all_acq_events.sort(key=lambda e: e.get("date") or "")

        # Classify method from the latest unified event when available
        # (catches waiver-then-no-trade cases like Otto Lopez), otherwise
        # fall back to the original trade-only classifier for backwards
        # compatibility with the rest of the pipeline.
        if _all_acq_events:
            latest_acq = _all_acq_events[-1]
            if latest_acq["kind"] != "trade":
                current_acq_method = latest_acq["kind"]
            else:
                current_acq_method = _classify_current_acquisition(filtered_trades, acq)
        else:
            current_acq_method = _classify_current_acquisition(filtered_trades, acq)

        display_org = _display_org(p, filtered_trades)
        # Surface the specific event that brought them to their current
        # org. Picks the latest from the unified events list (trade or
        # transaction), then runs the result through _collapse_bounce_chain
        # so short-tenure intermediates (e.g., Otto Lopez's 51-day SFG
        # stopover en route from TOR to MIA) get rolled up to the
        # stable prior org. The full bounce path is preserved on
        # `bounce_via` for the detail-page tooltip.
        current_acq_event = None
        if current_acq_method not in ("draft", "international_fa", "unknown") and _all_acq_events:
            latest_event = _all_acq_events[-1]
            collapsed = _collapse_bounce_chain(latest_event, _all_acq_events)
            current_acq_event = {
                "date":        collapsed.get("date"),
                "from_org":    collapsed.get("from_org"),
                "to_org":      collapsed.get("to_org"),
                "description": collapsed.get("description"),
            }
            if collapsed.get("bounce_via"):
                current_acq_event["bounce_via"] = collapsed["bounce_via"]
        # mlbam_id at top-level so every consumer (UI headshot, link to
        # MLB.com, etc.) can read it without digging into the statline —
        # graduates / inactives sometimes lack a current-season statline
        # but still need their MLB headshot to render.
        _mlbam = player_ids.get(p.player_key)
        if _mlbam is None and sl_out:
            _mlbam = sl_out.get("mlbam_id")
        return {
            "player_key": p.player_key,
            "player_name": p.player_name,
            "mlbam_id": _mlbam,
            "position": p.position,
            "org": display_org,
            "status": p.status,
            "graduation_date": _display_graduation_date(p) if p.status == "graduated" else p.graduation_date,
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
            # Unsnapped post-shrinkage FV at the latest snapshot. Lets the
            # UI distinguish a "high 40" (e.g. 42.3) from a "low 40"
            # (e.g. 37.8) — both round to the 40 tier label but the raw
            # value clarifies how much the shrinkage moved them.
            "fv_close_raw": (round(p.points[-1].consensus_fv_raw, 2)
                             if p.points else None),
            # Total (source, snapshot_date) instances where a published FV
            # exists across the player's full history. When 1, the FV
            # consensus is pulled toward FV 35 (Bayesian shrinkage); when
            # ≥2 the player is "well-observed" and escapes the pull —
            # including single-source players who've been re-graded over
            # multiple snapshots. Frontend `is-single-source` outline +
            # corner mark read off this field.
            "fv_total_instances": getattr(p, "fv_total_instances", 0),
            "stock": stock_movement(p),
            "statline": sl_out,
            "stat_flags": flags,
            # Scouting tool grades — consensus per-tool 20-80 grades,
            # three composites (offensive/defensive/overall for hitters;
            # stuff/command/overall for pitchers), and X+ indices (100 =
            # cohort mean, 10 pts = 1 stdev). `publishing_sources` lists
            # the sources that contributed grades. Empty/None when no
            # source has published tools for this player.
            "tools": tools_payload,
            # Green/red callouts for plus-plus or well-below-average
            # tools. Same {direction, stat, value, ...} shape as
            # stat_flags so one frontend renderer handles both.
            "tool_flags": tool_flags,
            # 12-month injury aggregate + Tommy-John flag. Drives the
            # IL-section roster, the "Post-TJ" chip on the prospect
            # header, the Injury-prone red flag, and the ETA-delay
            # adjustment in eta.estimate_eta.
            "health_profile": health,
            # Non-trade transactions: waiver claims, releases, DFAs,
            # contract purchases, Rule 5 selections/returns, FA signings.
            # Trades stay in their own `trades` field with stricter
            # cross-org dedup logic (see trades.py + reconcile_trades).
            # Each row is decorated with from_org / to_org (canonical
            # 3-letter codes) so farm-page consumers can filter events
            # that touch a given org without re-resolving team names.
            "transactions": [
                {**tx,
                 "from_org": canonical_org(tx.get("from_team")) if tx.get("from_team") else None,
                 "to_org":   canonical_org(tx.get("to_team"))   if tx.get("to_team")   else None}
                for tx in transactions_by_player.get(p.player_key, [])
            ],
            "pitch_arsenal": pa,
            "sabermetrics": sm,
            "trades": filtered_trades,
            "career_stats": career_stats.get(p.player_key, []),
            # Aggregated FanGraphs WAR for everyone who's touched MLB —
            # populated by the bulk career-WAR fetch in run_monthly. Carries
            # {seasons: {year: war}, career_war, war_per_yr,
            # war_seasons_count, source}. Empty dict when no MLB time on
            # file (every active prospect who hasn't debuted).
            "career_war": career_war.get(p.player_key, {}),
            # Within-season + cross-season level changes derived from the
            # MLB Stats API per-player transactions endpoint. One record
            # per real level transition (lateral affiliate swaps filtered
            # out). The earliest MLB promotion is tagged as the MLB debut
            # (kind == "debut") so the transaction-history block can
            # render it distinctly. Drives promotion/demotion markers on
            # the FV chart.
            "level_changes": _level_changes_with_debut(p.player_key),
            # MLB roster status: debut, options used, 40-man state,
            # accumulated service time, arb cycle bucket. Empty dict if
            # the player has not yet appeared in the majors.
            "roster_status": roster_status.get(p.player_key, {}),
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
            # Spotrac-sourced active contract. Populated only when the
            # player has a current MLB contract on file (active roster /
            # IL / dead-money tables on Spotrac's yearly team page).
            # Absent for prospects still in MiLB or anyone Spotrac
            # doesn't list. Drives the realized-surplus calc on
            # graduate detail pages — current-year salary slot reads
            # from `aav_usd` when present; prior seasons still use the
            # league-min + arb-fraction model.
            **({"current_contract": {
                "aav_usd":         _ct.get("aav_usd"),
                "salary_usd":      _ct.get("salary_usd"),
                "total_usd":       _ct.get("total_usd"),
                "salary_by_year":  _ct.get("salary_by_year"),
                "years_remaining": _ct.get("years_remaining"),
                "signed_through":  _ct.get("signed_through"),
                "spotrac_id":      _ct.get("spotrac_id"),
            }} if (_ct := contracts_by_key.get(p.player_key)) else {}),
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
                "health_adj": eta.health_adj,
            },
            # Per-tool lifetime delta map (first observation → latest).
            # `{hit: {delta, first, last, first_date, last_date, n_obs}, ...}`
            # Tools with <2 consensus observations are omitted. Powers the
            # +N / -N delta chips in the prospect-detail Tools section and
            # the "Tool development" wide card.
            "tool_deltas": _compute_tool_deltas([
                {"snapshot_date": pt.snapshot_date,
                 "tools_consensus": pt.tools_consensus}
                for pt in p.points
            ]),
            # Phase B1 — Breakout Signal: 0-100 composite that highlights
            # prospects with upward FV trajectory + young-for-level + tool
            # development + active stat-flag green signals. UI surfaces a
            # "BREAKOUT" pill when score ≥ 75.
            "breakout_score": _compute_breakout_score(
                p.points,
                _compute_tool_deltas([
                    {"snapshot_date": pt.snapshot_date,
                     "tools_consensus": pt.tools_consensus}
                    for pt in p.points
                ]),
                flags,
                (avl.diff if avl else None),
            ),
            "points": [
                {
                    "snapshot_date": pt.snapshot_date,
                    "interval_label": pt.interval_label,
                    "consensus_fv": pt.consensus_fv,
                    "consensus_fv_label": pt.consensus_fv_label,
                    "consensus_fv_raw": pt.consensus_fv_raw,
                    "consensus_fv_pre_shrinkage": pt.consensus_fv_pre_shrinkage,
                    "shrinkage_weight": pt.shrinkage_weight,
                    "avg_rank": pt.avg_rank,
                    "avg_fv": pt.avg_fv,
                    "avg_fv_n": pt.avg_fv_n,
                    "rank_implied_fv": pt.rank_implied_fv,
                    "sources_contributing": pt.sources_contributing,
                    "per_source": pt.per_source,
                    "fv_min": pt.fv_min,
                    "fv_max": pt.fv_max,
                    "fv_spread": pt.fv_spread,
                    "fv_stddev": pt.fv_stddev,
                    # Per-tool consensus + per-tool spread on this point.
                    # `per_source[src].tools` is already carried inside
                    # per_source above, so the UI can show "Pipeline says
                    # 60 hit / FanGraphs says 55 hit" without joining.
                    "tools_consensus": dict(pt.tools_consensus) if pt.tools_consensus else {},
                    "tools_spread": dict(pt.tools_spread) if pt.tools_spread else {},
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

        # Stale + not playing → inactive. We do NOT treat "any MLB time
        # this year" as automatic graduation anymore — that flipped
        # cup-of-coffee players (sub-130-AB / sub-50-IP) to graduates as
        # soon as their FV reporters lost interest, which is wrong by
        # both MLB rookie-eligibility rules and the user-facing semantics.
        # The real graduation paths run earlier:
        #   * derive_roster_status sets rookie_exhausted when career MLB
        #     totals cross 130 AB / 50 IP OR when minor-league options
        #     are used up.
        #   * detect_graduations_from_career checks the same thresholds
        #     against the cached career payload.
        # Both feed auto_graduate_player in run_monthly, so by the time
        # we get here a legitimately graduated player already has
        # p.status == "graduated" and was peeled off above.
        if fv_stale and play_stale:
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
        org_key = _active_display_org(p) or "?"
        org_totals[org_key] = org_totals.get(org_key, 0) + 1
    for i, p in enumerate(actives, start=1):
        overall_rank_by_key[p.player_key] = i
        org_key = _active_display_org(p) or "?"
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
        org = _active_display_org(p)
        if not org:
            continue
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
                # Companion of very_young_count — drives the Readiness
                # report-card grade. Net (very_young - very_old) per org.
                "very_old_count": 0,
                # Accumulators for the extended report-card grades
                # added in the Farm System Overhaul. Populated below and
                # finalized in the second pass after the actives loop.
                "_active_keys": [],
                "_ifa_years":  [],
                "_ifa_count":  0,
                "_post_tj_count": 0,
                "_il_days_sum":   0,
                "_il_days_count": 0,
                # Per-org tool-development accumulator (Step 3 of the
                # ToolsDvM+ plan). Keyed by canonical tool name (hit,
                # game_pwr, etc.) — each entry holds the per-prospect
                # lifetime delta (latest − first consensus grade) for
                # every active prospect with ≥2 observations of that
                # tool. Finalized in the second pass into mean_delta per
                # tool, then league-normalized into HitDvM+ / PowerDvM+
                # / etc. in `_attach_per_tool_dvm_plus`.
                "_tool_dev_sums": {},
                # Tree v3 — Draft Ceiling Hits accumulator. Counter of
                # drafted actives whose FV ≥ 60 within 3yr of draft.
                # Pulled into the Draft Pick Performance leaf's 2nd
                # sub-input (50/50 z-blend with pick-slot-adjusted WAR).
                "_draft_actives_count": 0,
                "_draft_ceiling_hits":  0,
            }
        m = org_map[org]
        m["prospects"].append({
            "name": p.player_name,
            "player_key": p.player_key,
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
        elif avl.tier == "very-old":
            m["very_old_count"] += 1

        # Tools+ Quality accumulator — composite_overall (raw 20-80
        # power-mean of per-tool grades). Computed directly from the
        # latest consensus tools dict so it's available BEFORE the X+
        # cohort normalization pass. We aggregate the raw composite,
        # which is the right axis for "how good are the prospects'
        # tools?" — the X+ normalization is for peer comparison, not
        # cross-org quality.
        is_pitcher_p = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        _comp = _compute_tool_composites(
            dict(p.points[-1].tools_consensus) if p.points[-1].tools_consensus else None,
            is_pitcher_p,
        )
        if _comp and _comp.get("composite_overall") is not None:
            m.setdefault("_tools_comp_overall", []).append(float(_comp["composite_overall"]))

        # Per-prospect tool deltas (latest − first consensus grade for each
        # tool with ≥2 observations). Sum into the org bucket so the
        # second pass can produce mean-delta-per-tool and the league
        # normalization can produce HitDvM+ / PowerDvM+ / etc.
        _td = _compute_tool_deltas([
            {"snapshot_date": pt.snapshot_date,
             "tools_consensus": pt.tools_consensus}
            for pt in p.points
        ])
        for _tk, _info in _td.items():
            m["_tool_dev_sums"].setdefault(_tk, []).append(_info["delta"])

        # Extended report-card accumulators (Farm Overhaul Step 5/6/7).
        m["_active_keys"].append(p.player_key)
        acq_rec = (acquisitions or {}).get(p.player_key) or {}
        if acq_rec.get("method") == "international_fa":
            m["_ifa_count"] += 1
            y = acq_rec.get("year")
            if y is not None:
                m["_ifa_years"].append(y)
        # Tree v3 — Draft Ceiling Hits: count drafted actives whose
        # current consensus FV ≥ 60 and whose draft year is within the
        # last 3 years. Captures whether the org's recent draft classes
        # produced high-ceiling prospects (not just whether grads beat
        # the slot in retrospect). Denominator: all drafted actives.
        if acq_rec.get("method") == "draft":
            m["_draft_actives_count"] = m.get("_draft_actives_count", 0) + 1
            draft_yr = acq_rec.get("year")
            today_yr = date.today().year
            if (draft_yr is not None
                    and today_yr - int(draft_yr) <= 3
                    and fv_raw is not None
                    and fv_raw >= 60.0):
                m["_draft_ceiling_hits"] = m.get("_draft_ceiling_hits", 0) + 1
        # Health profile (reuse the same helper the per-prospect path uses).
        rs_player = (roster_status or {}).get(p.player_key) or {}
        hp = _derive_health_profile(rs_player.get("injury_history") or [])
        if hp.get("is_post_tj"):
            m["_post_tj_count"] += 1
        il_days = int(hp.get("il_days_12mo") or 0)
        m["_il_days_sum"]   += il_days
        m["_il_days_count"] += 1

    # ── Per-org graduate aggregates (Farm Overhaul Steps 2 & 3) ──
    # Walk graduates ONCE to compute:
    #   - WAG sum + count (per-grad WAG via _grad_wag)
    #   - Total career WAR (across grads with a value)
    #   - Total bonus USD (across grads with bonus on file)
    # All grouped by graduate's CURRENT org (per user's choice).
    grad_agg: dict[str, dict] = {}
    for gp in grads:
        if not gp.points:
            continue
        # Resolve graduate's display org via the same helper actives use,
        # falling back to the player's source org if needed.
        gp_org = canonical_org(
            _latest_post_graduation_org(gp, []) or
            graduate_mlb_org_by_key.get(gp.player_key) or
            roster_org_by_key.get(gp.player_key) or
            gp.org
        )
        if not gp_org:
            continue
        # Build a minimal payload that _grad_wag can read.
        cw = (career_war or {}).get(gp.player_key) or {}
        fv_close_raw = (round(gp.points[-1].consensus_fv_raw, 2)
                        if gp.points else None)
        wag = _grad_wag({
            "career_war":   cw,
            "fv_close_raw": fv_close_raw,
            "fv_close":     gp.fv_close,
        })
        career_war_val = cw.get("career_war")
        gp_acq = (acquisitions or {}).get(gp.player_key, {}) or {}
        bonus_usd = gp_acq.get("bonus_usd")
        gp_method = gp_acq.get("method")  # "draft" | "international_fa" | "unknown"
        gp_is_pitcher = bool(gp.position
                             and gp.position.split("/")[0] in PITCHER_POS)
        gp_contract = (contracts_by_key or {}).get(gp.player_key) or {}
        gp_aav = gp_contract.get("aav_usd")

        bucket = grad_agg.setdefault(gp_org, {
            "wag_sum": 0.0, "wag_count": 0,
            "war_sum": 0.0, "war_count": 0,
            "bonus_sum": 0, "bonus_count": 0,
            # Tree v2 splits — same WAG but partitioned by acquisition
            # method (IFA vs Draft) and position type (Hitter vs Pitcher)
            # so the grade tree's Acquisitions and MLB Production
            # branches can each grade their own sub-axis.
            "ifa_wag_sum": 0.0,   "ifa_wag_count":   0,
            "draft_wag_sum": 0.0, "draft_wag_count": 0,
            "hit_wag_sum": 0.0,   "hit_wag_count":   0,
            "pit_wag_sum": 0.0,   "pit_wag_count":   0,
            # Grad-Contract Surplus — current AAV − (bonus amortized over
            # 6 years, the rough cost-controlled window before the player
            # would have hit arb/FA). Positive = grad's MLB salary value
            # exceeds the org's signing-bonus outlay.
            "contract_surplus_sum": 0.0, "contract_surplus_count": 0,
            # Pick-slot-adjusted draft performance (v2 of Draft Pick
            # Performance). actual_war − slot_expected_war per drafted
            # grad. Credits orgs that beat the market at each pick slot;
            # strictly more informative than raw WAG for the "did this
            # org draft well?" question.
            "draft_pick_value_sum": 0.0, "draft_pick_value_count": 0,
            # Tree v3 splits — supplemental WAR/yr + cumulative WAR
            # aggregators per IFA / hitter / pitcher subset. The 3-input
            # composite (WAG + WAR/yr + cumulative WAR) is the v3 leaf
            # score for IFA Performance + Hitter MLB Production + Pitcher
            # MLB Production. Captures peak rate (WAR/yr) and total
            # impact (cumulative WAR), not just the WAG expectation delta.
            "ifa_war_per_yr_sum":  0.0, "ifa_war_per_yr_count":  0,
            "ifa_career_war_sum":  0.0, "ifa_career_war_count":  0,
            "hit_war_per_yr_sum":  0.0, "hit_war_per_yr_count":  0,
            "hit_career_war_sum":  0.0, "hit_career_war_count":  0,
            "pit_war_per_yr_sum":  0.0, "pit_war_per_yr_count":  0,
            "pit_career_war_sum":  0.0, "pit_career_war_count":  0,
        })
        if wag is not None:
            bucket["wag_sum"] += wag
            bucket["wag_count"] += 1
            # Acquisition-method split
            if gp_method == "international_fa":
                bucket["ifa_wag_sum"] += wag
                bucket["ifa_wag_count"] += 1
            elif gp_method == "draft":
                bucket["draft_wag_sum"] += wag
                bucket["draft_wag_count"] += 1
            # Position split for MLB Production branch
            if gp_is_pitcher:
                bucket["pit_wag_sum"] += wag
                bucket["pit_wag_count"] += 1
            else:
                bucket["hit_wag_sum"] += wag
                bucket["hit_wag_count"] += 1
        if career_war_val is not None:
            bucket["war_sum"] += float(career_war_val)
            bucket["war_count"] += 1
        # Tree v3 — cumulative WAR + WAR-per-year splits for IFA /
        # Hitter / Pitcher subsets. Per `career_war` payload shape:
        # `career_war` (total) + `war_per_yr` (career_war /
        # war_seasons_count). The 3-input composite at the leaf level
        # blends WAG + WAR/yr + cumulative WAR equally.
        war_per_yr = cw.get("war_per_yr")
        if career_war_val is not None or war_per_yr is not None:
            cval = float(career_war_val) if career_war_val is not None else None
            yval = float(war_per_yr)     if war_per_yr     is not None else None
            if gp_method == "international_fa":
                if cval is not None:
                    bucket["ifa_career_war_sum"]  += cval
                    bucket["ifa_career_war_count"] += 1
                if yval is not None:
                    bucket["ifa_war_per_yr_sum"]   += yval
                    bucket["ifa_war_per_yr_count"] += 1
            if gp_is_pitcher:
                if cval is not None:
                    bucket["pit_career_war_sum"]  += cval
                    bucket["pit_career_war_count"] += 1
                if yval is not None:
                    bucket["pit_war_per_yr_sum"]   += yval
                    bucket["pit_war_per_yr_count"] += 1
            else:
                if cval is not None:
                    bucket["hit_career_war_sum"]  += cval
                    bucket["hit_career_war_count"] += 1
                if yval is not None:
                    bucket["hit_war_per_yr_sum"]   += yval
                    bucket["hit_war_per_yr_count"] += 1
        if bonus_usd is not None:
            bucket["bonus_sum"] += int(bonus_usd)
            bucket["bonus_count"] += 1
        # Grad-Contract Surplus accumulator. 6-year amortization mirrors
        # the typical pre-FA cost-controlled window for a graduate; longer
        # extensions get credited yearly via aav_usd, not the bonus.
        if gp_aav and bonus_usd:
            try:
                surplus_yr = float(gp_aav) - (float(bonus_usd) / 6.0)
                bucket["contract_surplus_sum"]   += surplus_yr
                bucket["contract_surplus_count"] += 1
            except (TypeError, ValueError):
                pass
        # Pick-slot-adjusted draft value (v2 of Acquisitions/Draft).
        # Requires both a draft method AND a numeric pick_overall AND a
        # career_war on file. The delta is positive when the org
        # extracted more MLB value from that pick slot than the league
        # historically gets — credits late-round hits more than #1
        # overalls reaching the majors. Falls back silently when any
        # piece is missing (Spotrac-only graduates, IFA signings, etc.)
        if gp_method == "draft" and career_war_val is not None:
            slot_exp = _pick_slot_expected_war(gp_acq.get("pick_overall"))
            if slot_exp is not None:
                bucket["draft_pick_value_sum"]   += float(career_war_val) - slot_exp
                bucket["draft_pick_value_count"] += 1

    # Finalize each org entry
    org_summary = []
    for org, m in sorted(org_map.items()):
        ages = m.pop("ages")
        m["count"] = len(m["prospects"])
        m["total_fv"] = round(m["total_fv"], 1)
        m["avg_age"] = round(sum(ages) / len(ages), 1) if ages else None
        m["top_prospect"] = m["prospects"][0] if m["prospects"] else None
        m["youngest"] = min(m["prospects"], key=lambda x: x["age"] if x["age"] else 99) if m["prospects"] else None

        # ── Farm Overhaul: per-org extended report-card aggregates ──
        # Talent Translation (WAG) — mean of grad WAG values. Orgs with
        # fewer than 3 graduates with valid WAG get None so they grade
        # as "—" rather than D (no data isn't the same as bad data).
        gagg = grad_agg.get(org) or {}
        wag_count = gagg.get("wag_count") or 0
        m["talent_translation"] = {
            "wag_mean": (round(gagg["wag_sum"] / wag_count, 2)
                         if wag_count >= 3 else None),
            "wag_sum":  round(gagg.get("wag_sum") or 0.0, 2),
            "grad_count": wag_count,
        }
        # Financial ROI — WAR per million USD spent on the grads who
        # have both signing bonus AND career WAR on file. Requires the
        # bonus union (we use a separate bonus_count gate so a free
        # agent without a published bonus doesn't drag the ratio down).
        bonus_sum = gagg.get("bonus_sum") or 0
        war_sum = gagg.get("war_sum") or 0.0
        m["financial_roi"] = {
            "war_per_million": (round(war_sum / (bonus_sum / 1_000_000), 3)
                                if bonus_sum >= 1_000_000 else None),
            "total_career_war":  round(war_sum, 2),
            "total_bonus_usd":   bonus_sum,
            "grad_count_with_bonus": gagg.get("bonus_count") or 0,
        }
        # Tools+ Quality — top-10 mean of raw composite_overall (the
        # 20-80 power-mean of per-tool grades). Top-10 (not all) so a
        # top-heavy farm with raw-tools stars isn't dragged down by
        # un-graded depth. NOTE: the value here is on the 20-80 scale,
        # NOT the X+ (z-scored 100-anchored) scale — see Tools+ Quality
        # glossary entry for why.
        _comp_overalls = sorted(m.pop("_tools_comp_overall", []) or [], reverse=True)
        m["tools_quality"] = {
            "top10_mean":  round(sum(_comp_overalls[:10]) / len(_comp_overalls[:10]), 2)
                            if _comp_overalls else None,
            "mean":        round(sum(_comp_overalls) / len(_comp_overalls), 2)
                            if _comp_overalls else None,
            "graded_count": len(_comp_overalls),
        }
        # International Depth — IFA % and year-span across actives.
        n_actives = len(m["prospects"]) or 1
        ifa_year_span = len(set(m.pop("_ifa_years") or []))
        ifa_count = m.pop("_ifa_count") or 0
        m["international_depth"] = {
            "ifa_pct":  round(ifa_count / n_actives, 3) if n_actives else 0,
            "ifa_count": ifa_count,
            "year_span": ifa_year_span,
        }
        # Readiness — (very_young - very_old) / total actives. Can go
        # negative for organizationally over-age systems.
        m["readiness"] = {
            "pct_signal":       round((m["very_young_count"] - m["very_old_count"]) / n_actives, 3),
            "very_young_count": m["very_young_count"],
            "very_old_count":   m["very_old_count"],
        }
        # Health burden (LOWER IS BETTER) — combines post-TJ % and
        # mean trailing 12-month IL days. The ranking layer below
        # inverts so the LOWEST burden gets the BEST letter grade.
        post_tj_count = m.pop("_post_tj_count") or 0
        il_days_sum = m.pop("_il_days_sum") or 0
        il_days_count = m.pop("_il_days_count") or 0
        post_tj_pct = post_tj_count / n_actives if n_actives else 0
        il_days_mean = (il_days_sum / il_days_count) if il_days_count else 0
        m["health_burden"] = {
            "score":       round(100 * post_tj_pct + il_days_mean, 2),
            "post_tj_pct": round(post_tj_pct, 3),
            "il_days_mean": round(il_days_mean, 1),
            "post_tj_count": post_tj_count,
        }
        # Per-tool development — mean lifetime delta across actives that
        # have ≥2 consensus observations of each tool. Sparse-data gate:
        # tools with fewer than 3 contributing prospects are dropped (a
        # 1-prospect mean is too noisy to compare across orgs). The
        # per-tool DvM+ + composite ToolsDvM+ are computed in a second
        # league-wide pass below, once every org's mean_delta is known.
        _tool_sums = m.pop("_tool_dev_sums") or {}
        per_tool: dict[str, dict] = {}
        for _tk, _deltas in _tool_sums.items():
            if len(_deltas) < 3:
                continue
            per_tool[_tk] = {
                "mean_delta":  round(sum(_deltas) / len(_deltas), 2),
                "n_prospects": len(_deltas),
            }
        m["tool_dev"] = {
            "per_tool":          per_tool,
            "per_tool_dvm_plus": {},   # filled in the league pass below
            "tools_dvm_plus":    None,
        }

        # ── Farm Grade Tree v2 sub-grades — leaf-level metrics ──
        # All grade-tree leaves get their underlying values stamped here.
        # The 100-anchored league-normalized versions + composites are
        # computed in a separate pass below (once league mean+stdev are
        # known across every org's leaf values). Sparse-data gates apply
        # at the leaf level (count threshold per leaf).
        _wag_sum = gagg.get("wag_sum") or 0.0
        # Helper: gated mean per (sum_key, count_key, min_count).
        def _gated_mean(sk, ck, gate=3, prec=2):
            n = gagg.get(ck) or 0
            return round(gagg[sk] / n, prec) if n >= gate else None
        # Draft Ceiling Hits — % of recent (≤3yr) drafted actives with FV ≥ 60.
        _draft_actives_n = m.pop("_draft_actives_count", 0) or 0
        _draft_ceiling_n = m.pop("_draft_ceiling_hits",  0) or 0
        _draft_ceiling_pct = (round(_draft_ceiling_n / _draft_actives_n, 3)
                              if _draft_actives_n >= 3 else None)
        m["tree"] = {
            # ACQUISITION STRATEGY branch (v3 — merged Acquisitions + Transactions).
            # IFA Performance — 3-input composite. WAG + WAR-per-year +
            # cumulative WAR over IFA-method graduates. Captures expectation
            # delta, peak rate, and total impact.
            "acq_ifa": {
                "wag_mean":         _gated_mean("ifa_wag_sum",        "ifa_wag_count"),
                "war_per_yr_mean":  _gated_mean("ifa_war_per_yr_sum", "ifa_war_per_yr_count"),
                "career_war_mean":  _gated_mean("ifa_career_war_sum", "ifa_career_war_count"),
                "wag_sum":   round(gagg.get("ifa_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("ifa_wag_count") or 0,
            },
            # Draft Performance — pick-slot-adjusted WAR (existing) + Draft
            # Ceiling Hits (new sub-input).
            "acq_draft": {
                "wag_mean": _gated_mean("draft_wag_sum", "draft_wag_count"),
                "wag_sum":  round(gagg.get("draft_wag_sum") or 0.0, 2),
                "pick_value_mean":  _gated_mean("draft_pick_value_sum", "draft_pick_value_count"),
                "pick_value_count": gagg.get("draft_pick_value_count") or 0,
                # New v3 sub-input — recent draft ceiling hits as a %
                # of recent drafted actives. Z-blended 50/50 with the
                # pick-slot-adjusted value at the leaf-scoring layer.
                "ceiling_hits_pct":   _draft_ceiling_pct,
                "ceiling_hits_count": _draft_ceiling_n,
                "draft_actives_count": _draft_actives_n,
                "grad_count": gagg.get("draft_wag_count") or 0,
            },
            # DEVELOPMENT branch — hitter/pitcher composites filled by
            # the per-tool DvM+ league pass below.
            "dev_hitter": {"dvm_plus": None, "n_groups": 0},
            "dev_pitcher": {"dvm_plus": None, "n_groups": 0},
            # Trade + Waiver scoreboards (filled by the v2 pass below).
            # In v3 these are leaves under Acquisition Strategy.
            "tx_trades":  {"net_fv": None, "fv_in": 0.0, "fv_out": 0.0,
                           "in_count": 0, "out_count": 0,
                           # v3 enhancer — fills in the WAR-delta pass below.
                           "war_delta": None, "war_in": 0.0, "war_out": 0.0},
            "tx_waivers": {"net_fv": None, "fv_in": 0.0, "fv_out": 0.0,
                           "in_count": 0, "out_count": 0,
                           # v3 enhancer — fills in the hit-rate pass below.
                           "hit_rate": None, "claims_total": 0, "claims_with_mlb": 0},
            # FINANCIAL branch — war_per_million reused from financial_roi;
            # grad-contract surplus mean computed here.
            "fin_war_per_m": {
                "value": m["financial_roi"]["war_per_million"],
                "grad_count": m["financial_roi"]["grad_count_with_bonus"],
            },
            "fin_contract_surplus": {
                "mean_usd_per_yr": (round(gagg["contract_surplus_sum"] / gagg["contract_surplus_count"], 0)
                                    if (gagg.get("contract_surplus_count") or 0) >= 3 else None),
                "grad_count": gagg.get("contract_surplus_count") or 0,
            },
            # MLB PRODUCTION branch — 3-input composites per position.
            # Hitter MLB Production blends Hitter WAG + Hitter WAR/yr +
            # Hitter Cumulative WAR across hitter graduates. Same shape
            # for the pitcher leaf with pitcher grads.
            "mlb_hitter_wag": {
                "wag_mean":        _gated_mean("hit_wag_sum",        "hit_wag_count"),
                "war_per_yr_mean": _gated_mean("hit_war_per_yr_sum", "hit_war_per_yr_count"),
                "career_war_mean": _gated_mean("hit_career_war_sum", "hit_career_war_count"),
                "wag_sum":  round(gagg.get("hit_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("hit_wag_count") or 0,
            },
            "mlb_pitcher_wag": {
                "wag_mean":        _gated_mean("pit_wag_sum",        "pit_wag_count"),
                "war_per_yr_mean": _gated_mean("pit_war_per_yr_sum", "pit_war_per_yr_count"),
                "career_war_mean": _gated_mean("pit_career_war_sum", "pit_career_war_count"),
                "wag_sum":  round(gagg.get("pit_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("pit_wag_count") or 0,
            },
        }

        # _active_keys stays for the Tools+ second pass; popped later.
        org_summary.append(m)

    # Stable sort by total_fv for the moment — the composite farm_rank
    # below overwrites this ordering once the rolling-window signals are
    # available. We do it here so downstream code that wants the raw
    # FV-only rank (e.g. the "Total FV" sort chip on the front-end) can
    # still recover it by re-sorting on total_fv directly.
    org_summary.sort(key=lambda x: -x["total_fv"])

    # ── Per-tool DvM+ league pass (HitDvM+, PowerDvM+, …, ToolsDvM+) ──
    # For each TOOL_GROUP, gather every org's mean_delta on the tools in
    # that group (averaged for multi-tool groups like Power = mean of
    # game_pwr + raw_pwr). Compute league mean μ + stdev σ across orgs
    # that have data; convert each org's value to a 100-anchored index
    # via 100 + 10·z. Mirrors the wRC+-style anchoring used by `dvm_plus`
    # elsewhere in the report card. Orgs without data for a given group
    # get None; tool groups with fewer than 3 orgs reporting are dropped
    # entirely (no statistical anchor possible).
    def _group_mean_delta_for_org(per_tool: dict, keys: list[str]) -> tuple[float | None, int]:
        """Returns (group mean_delta, total prospects contributing).
        The n is the prospect count used to shrink small-sample orgs
        toward the league mean (Phase A4)."""
        vals_n = [(per_tool[k]["mean_delta"], per_tool[k].get("n_prospects", 0))
                  for k in keys
                  if k in per_tool and per_tool[k].get("mean_delta") is not None]
        if not vals_n:
            return (None, 0)
        return (sum(v for v, _ in vals_n) / len(vals_n),
                sum(n for _, n in vals_n))

    # Bayesian shrinkage strength. k=2 means an org with n=3 prospects
    # gets 60% weight on its own mean_delta + 40% on the league mean.
    # n=10 → 83% own + 17% mean. n=30 → 94% own + 6% mean. Tuned so
    # small samples don't get dragged out of contention by one outlier
    # but big samples retain their actual signal.
    _DVM_SHRINK_K = 2

    for grp_name, tool_keys in TOOL_GROUPS.items():
        org_vals: list[tuple[str, float | None, int]] = []
        for e in org_summary:
            v, n = _group_mean_delta_for_org(e["tool_dev"]["per_tool"], tool_keys)
            org_vals.append((e["org"], v, n))
        populated = [v for _, v, _ in org_vals if v is not None]
        # Lowered gate from <3 → <2 (Phase A4). With just 2 orgs
        # reporting we can still anchor a (low-confidence) mean +
        # surface a DvM+ for both; the per-org shrinkage below
        # protects against single-prospect noise.
        if len(populated) < 2:
            for org_code, _, _ in org_vals:
                _entry = next(e for e in org_summary if e["org"] == org_code)
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = None
            continue
        mu = sum(populated) / len(populated)
        var = sum((v - mu) ** 2 for v in populated) / len(populated)
        sd = var ** 0.5
        for org_code, v, n in org_vals:
            _entry = next(e for e in org_summary if e["org"] == org_code)
            if v is None or sd < 1e-6:
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = None
            else:
                # Bayesian shrinkage toward the league mean before
                # z-scoring. shrunk = (n/(n+k))·v + (k/(n+k))·μ
                weight = n / (n + _DVM_SHRINK_K) if n > 0 else 0.0
                shrunk_v = weight * v + (1 - weight) * mu
                z = (shrunk_v - mu) / sd
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = int(round(100 + 10 * z))

    # Composite ToolsDvM+ — unweighted mean of the per-group DvM+ values
    # an org actually has. Orgs missing every group entry get None.
    _composite_vals: list[tuple[str, int | None]] = []
    for entry in org_summary:
        per_grp = entry["tool_dev"].get("per_tool_dvm_plus") or {}
        vs = [v for v in per_grp.values() if v is not None]
        composite = int(round(sum(vs) / len(vs))) if vs else None
        entry["tool_dev"]["tools_dvm_plus"] = composite
        _composite_vals.append((entry["org"], composite))

    # Rank for the composite — descending (higher composite = rank 1).
    # `_rank_descending` doesn't take None; do the present-filter inline
    # (mirrors the `_rank_with_none` helper defined later inside the
    # same parent function).
    _present_idx = [i for i, (_, v) in enumerate(_composite_vals) if v is not None]
    _present_vals = [_composite_vals[i][1] for i in _present_idx]
    _sub_ranks = _rank_descending(_present_vals)
    _ranks: list[int | None] = [None] * len(_composite_vals)
    for i, r in zip(_present_idx, _sub_ranks):
        _ranks[i] = r
    for (org_code, _), r in zip(_composite_vals, _ranks):
        _entry = next(e for e in org_summary if e["org"] == org_code)
        _entry["tool_dev"]["tools_dvm_plus_rank"] = r

    # ── Tree v2: Hitter / Pitcher Tools DvM+ composites ──
    # Filter the per_tool_dvm_plus dict (just computed) into hitter-only
    # and pitcher-only groupings, average within each. These feed the
    # Development branch of the grade tree.
    _HITTER_TOOL_DVM_KEYS = {"hit", "power", "speed", "field", "arm",
                             "pitch_sel", "bat_ctrl"}
    _PITCHER_TOOL_DVM_KEYS = {"fb", "sl", "cb", "ch", "cmd", "ct"}
    for entry in org_summary:
        per_grp = entry["tool_dev"].get("per_tool_dvm_plus") or {}
        h_vals = [v for k, v in per_grp.items()
                  if k in _HITTER_TOOL_DVM_KEYS and v is not None]
        p_vals = [v for k, v in per_grp.items()
                  if k in _PITCHER_TOOL_DVM_KEYS and v is not None]
        entry["tree"]["dev_hitter"]["dvm_plus"]  = int(round(sum(h_vals) / len(h_vals))) if h_vals else None
        entry["tree"]["dev_hitter"]["n_groups"]  = len(h_vals)
        entry["tree"]["dev_pitcher"]["dvm_plus"] = int(round(sum(p_vals) / len(p_vals))) if p_vals else None
        entry["tree"]["dev_pitcher"]["n_groups"] = len(p_vals)

    # Per-level graded prospect counts, sourced from the affiliate-roster
    # map. Drives both the "sort farms by depth at level X" chips on the
    # farm list page and the "graded prospects by level" section on each
    # farm detail page. Only includes prospects with a FV grade — un-graded
    # org filler in the rosters isn't a prospect for our purposes.
    FARM_LEVELS = ("MLB", "AAA", "AA", "A+", "A", "CPX", "DSL")
    for entry in org_summary:
        org_rosters = rosters_by_org.get(entry["org"], {})
        entry["level_counts"] = {
            lvl: sum(1 for r in (org_rosters.get(lvl) or []) if r.get("fv_label"))
            for lvl in FARM_LEVELS
        }

    # Per-org cumulative FV history — running sum of prospect FVs over time,
    # attributed to whichever org owned the prospect on each snapshot date.
    # Drives the farm-system stock chart on the farm list + farm detail
    # pages. Trades show as +/- moves between orgs; graduations are
    # graduation-neutral — the cumulative line stays flat through them so
    # a productive farm isn't punished for promoting its top prospects.
    org_fv_history = _build_org_fv_history(
        actives + grads + inactives, _filter_real_trades, trades_by_player,
    )
    for entry in org_summary:
        hist = org_fv_history.get(entry["org"], {})
        entry["fv_history"] = hist.get("series", [])
        entry["fv_events"]  = hist.get("events", [])

    # ── Tree v3: Trade Acumen scoreboard (FV + WAR delta) ──
    # Two co-equal sub-inputs feed this leaf:
    #   1. Net FV (sum of incoming FV − outgoing FV at trade date)
    #   2. Trade WAR Delta (career WAR of acquired grads − career WAR
    #      of traded-away grads). Captures retrospective trade value,
    #      not just the league's FV consensus at the trade moment.
    for entry in org_summary:
        in_fv = 0.0;  out_fv = 0.0
        in_n  = 0;    out_n  = 0
        in_war = 0.0; out_war = 0.0
        in_war_n = 0; out_war_n = 0
        for ev in (entry["fv_events"] or []):
            if ev.get("kind") != "trade":
                continue
            fv = ev.get("fv") or 0.0
            pkey = ev.get("player_key")
            cw = ((career_war or {}).get(pkey) or {}).get("career_war")
            if ev.get("direction") == "in":
                in_fv += fv; in_n += 1
                if cw is not None:
                    in_war += float(cw); in_war_n += 1
            elif ev.get("direction") == "out":
                out_fv += fv; out_n += 1
                if cw is not None:
                    out_war += float(cw); out_war_n += 1
        entry["tree"]["tx_trades"] = {
            "net_fv":    round(in_fv - out_fv, 1) if (in_n + out_n) else None,
            "fv_in":     round(in_fv, 1),
            "fv_out":    round(out_fv, 1),
            "in_count":  in_n,
            "out_count": out_n,
            # WAR-delta enhancer (only meaningful with ≥1 grad each side).
            "war_delta": round(in_war - out_war, 2) if (in_war_n + out_war_n) >= 3 else None,
            "war_in":    round(in_war, 2),
            "war_out":   round(out_war, 2),
        }

    # Waivers sub-grade — walk transactions_by_player for non-trade
    # cross-org events (waiver_claim, rule_5_return, contract_purchase,
    # signed_free_agent).
    #
    # Phase A2 (2026-05): switched from the always-LATEST-FV proxy to a
    # transaction-date FV lookup. The prior approach over-valued waiver
    # claims that bloomed years AFTER the claim (e.g., a 2021 waiver of
    # a prospect now at FV 50 was credited at FV 50, not the FV ~38 the
    # claiming org actually saw). Walks player.points[] once per player
    # and indexes by snapshot_date so the per-tx lookup is O(log n).
    _WAIVER_KINDS = {"waiver_claim", "rule_5_return", "contract_purchase",
                     "signed_free_agent"}
    _waiver_in_by_org:  dict[str, list[float]] = {}
    _waiver_out_by_org: dict[str, list[float]] = {}
    # v3 hit-rate accumulators — per-org claimed-into-org count + count
    # of those that reached MLB. Used to compute Waiver Hit Rate as a
    # 50/50 z-blend partner to net_fv at the leaf-scoring layer.
    _waiver_claims_by_org:    dict[str, int] = {}
    _waiver_mlb_hits_by_org:  dict[str, int] = {}
    # Build a per-player chronological FV history (sorted ascending by
    # snapshot_date) so fv_at_date is a simple right-bisect. Skip
    # players with no points or no FV data at all.
    _player_fv_history: dict[str, list[tuple[str, float]]] = {}
    for p in actives + grads + inactives:
        hist: list[tuple[str, float]] = []
        for pt in (p.points or []):
            if pt.consensus_fv_raw is not None:
                hist.append((pt.snapshot_date, float(pt.consensus_fv_raw)))
        if hist:
            # points are already date-ordered upstream, but sort
            # defensively in case of out-of-order ingest.
            hist.sort(key=lambda t: t[0])
            _player_fv_history[p.player_key] = hist

    def _fv_at_date(pkey: str, cutoff_date: str) -> float | None:
        """Return the most-recent consensus_fv_raw at-or-before cutoff
        for this player, or None if no point exists by that date.
        Falls back to the OLDEST point when cutoff predates all points
        (rare — usually a Rule-5/waiver before the player was published)."""
        hist = _player_fv_history.get(pkey)
        if not hist:
            return None
        # Right-bisect: find the last point where date <= cutoff_date.
        import bisect
        idx = bisect.bisect_right([t[0] for t in hist], cutoff_date) - 1
        if idx < 0:
            # Cutoff predates all snapshots — use the OLDEST FV as the
            # best available proxy (better than dropping the tx).
            return hist[0][1]
        return hist[idx][1]

    _txs = transactions_by_player or {}
    # Tally distinct kinds we encounter for a debug log — surfaces drift
    # if a new transaction type slips through derive_transactions
    # without being grouped here.
    _waiver_kinds_seen: dict[str, int] = {}
    for pkey, txs in _txs.items():
        if pkey not in _player_fv_history:
            continue
        # Reached-MLB signal — career_war present + any season recorded
        # means the player landed on a big-league roster at some point.
        cw_entry = (career_war or {}).get(pkey) or {}
        _player_reached_mlb = bool(cw_entry.get("career_war") is not None
                                   or (cw_entry.get("seasons") or {}))
        for tx in (txs or []):
            kind = tx.get("kind")
            if kind not in _WAIVER_KINDS:
                continue
            _waiver_kinds_seen[kind] = _waiver_kinds_seen.get(kind, 0) + 1
            # Transaction-date FV — what the claiming org actually saw,
            # not the retrospective FV. Falls back to the player's
            # oldest FV when the tx predates all snapshots.
            tx_date = tx.get("date") or ""
            fv = _fv_at_date(pkey, tx_date)
            if fv is None:
                continue
            # IMPORTANT: derive_transactions in stats.py emits the
            # `from_team` / `to_team` keys (not `_team_name`). An earlier
            # version of this loop used the wrong field names and silently
            # produced an empty scoreboard for all 30 orgs. The fix below
            # tracks the canonical field shape that stats.py actually
            # ships.
            from_team = tx.get("from_team")
            to_team   = tx.get("to_team")
            from_org  = canonical_org(from_team) if from_team else None
            to_org    = canonical_org(to_team)   if to_team   else None
            if from_org:
                _waiver_out_by_org.setdefault(from_org, []).append(fv)
            if to_org:
                _waiver_in_by_org.setdefault(to_org, []).append(fv)
                _waiver_claims_by_org[to_org] = _waiver_claims_by_org.get(to_org, 0) + 1
                if _player_reached_mlb:
                    _waiver_mlb_hits_by_org[to_org] = _waiver_mlb_hits_by_org.get(to_org, 0) + 1
    # _waiver_kinds_seen tally available for debug if a future kind
    # silently drops out of the filter — print or log on demand.
    for entry in org_summary:
        org_code = entry["org"]
        in_list  = _waiver_in_by_org.get(org_code, [])
        out_list = _waiver_out_by_org.get(org_code, [])
        in_fv  = round(sum(in_list), 1)
        out_fv = round(sum(out_list), 1)
        claims_total   = _waiver_claims_by_org.get(org_code, 0)
        claims_mlb_hit = _waiver_mlb_hits_by_org.get(org_code, 0)
        entry["tree"]["tx_waivers"] = {
            "net_fv":    round(in_fv - out_fv, 1) if (in_list or out_list) else None,
            "fv_in":     in_fv,
            "fv_out":    out_fv,
            "in_count":  len(in_list),
            "out_count": len(out_list),
            # v3 — Waiver Hit Rate (% claimed-into-org who reached MLB).
            # Sparse-data gate: <3 claims → None.
            "hit_rate":        (round(claims_mlb_hit / claims_total, 3)
                                if claims_total >= 3 else None),
            "claims_total":    claims_total,
            "claims_with_mlb": claims_mlb_hit,
        }

    # ── Farm report card ────────────────────────────────────────────────────
    # Four raw component scores per org, each then rescaled to a 0-100 band
    # across the 30 orgs and blended into a single farm_score. The blend
    # weights are FARM_WEIGHT_* above. Each component also gets a letter
    # grade (its rank's bucket); the overall letter is the bucket the
    # blended farm_score lands in.
    today_iso = date.today()
    for entry in org_summary:
        entry["top_end_points"] = _top_end_points(entry["prospects"])
        entry["depth_points"]   = _depth_points(entry["prospects"])
        # Trajectory at each available window. The 1y value is also
        # surfaced as `trajectory_score` so the report-card grading (which
        # is intentionally anchored to 1y) keeps using it without having
        # to know about the dict.
        entry["trajectories"] = {
            key: _trajectory_score(
                entry["fv_history"], lookback_days=days, as_of=today_iso,
            )
            for key, days in FARM_TRAJECTORY_WINDOWS.items()
        }
        entry["trajectory_score"] = entry["trajectories"]["1y"]
        entry["grad_pipeline_score"] = _grad_pipeline_score(
            entry["fv_events"], as_of=today_iso,
        )

    # Mean trajectory per window across all orgs. The list-page chart
    # subtracts a linear baseline of `mean * t/window_days` from each
    # org's series so the line shows "growth above the average farm",
    # not raw FV — that's the comparison the user actually wants when
    # ranking dev pipelines. Mean (not median) so the metric responds
    # to outliers — a system that's well above league mean reflects
    # real dev outperformance, not just being above the middle of the
    # pack. Standard deviation is also exported so DvM+ can use it to
    # convert raw deltas into a wRC+-style 100-anchored scale.
    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _stdev(vals: list[float], mu: float) -> float:
        if len(vals) < 2:
            return 0.0
        return (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5

    farm_trajectory_means = {
        key: round(_mean([e["trajectories"][key] for e in org_summary]), 2)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    farm_trajectory_stdevs = {
        key: round(
            _stdev(
                [e["trajectories"][key] for e in org_summary],
                farm_trajectory_means[key],
            ),
            4,
        )
        for key in FARM_TRAJECTORY_WINDOWS
    }
    for entry in org_summary:
        entry["delta_above_mean"] = {
            key: round(entry["trajectories"][key] - farm_trajectory_means[key], 2)
            for key in FARM_TRAJECTORY_WINDOWS
        }
        # DvM+ — wRC+/OPS+-style metric anchored at 100 = league mean.
        # 10 points = 1 stdev, mirroring the OPS+ convention. Stable
        # under sparse league spread (returns 100 when stdev ≈ 0).
        entry["dvm_plus"] = {}
        for key in FARM_TRAJECTORY_WINDOWS:
            sd = farm_trajectory_stdevs[key]
            delta = entry["delta_above_mean"][key]
            if sd > 1e-6:
                entry["dvm_plus"][key] = round(100 + 10 * (delta / sd))
            else:
                entry["dvm_plus"][key] = 100

    # Helper: normalize a list where some entries may be None (small-
    # sample orgs without enough data). None values get the cohort
    # median, so they sit dead-center in the blend instead of dragging
    # the org to either extreme.
    def _normalize_with_none(values: list[float | None]) -> list[float]:
        present = [v for v in values if v is not None]
        if not present:
            return [50.0] * len(values)
        norm = _normalize_to_100(present)
        med = sorted(norm)[len(norm) // 2] if norm else 50.0
        out: list[float] = []
        idx = 0
        for v in values:
            if v is None:
                out.append(med)
            else:
                out.append(norm[idx]); idx += 1
        return out

    top_end_100 = _normalize_to_100([e["top_end_points"]      for e in org_summary])
    depth_100   = _normalize_to_100([e["depth_points"]        for e in org_summary])
    # DvM+ replaces raw trajectory in the blend. The 1y window is the
    # default report-card axis (matches the old behavior of using the
    # 1y trajectory). DvM+ values are already 100-anchored, but we
    # rescale them through _normalize_to_100 so the 0-100 band is
    # consistent with the other components.
    dvm_plus_100 = _normalize_to_100([e["dvm_plus"]["1y"]     for e in org_summary])
    grad_100     = _normalize_to_100([e["grad_pipeline_score"] for e in org_summary])
    # Also expose trajectory_100 for back-compat (UI tooltip still shows
    # the raw value even though it no longer drives the letter grade).
    traj_100     = _normalize_to_100([e["trajectory_score"]    for e in org_summary])

    # New components — None-safe normalization for small-sample orgs.
    wag_100    = _normalize_with_none([(e["talent_translation"] or {}).get("wag_mean")        for e in org_summary])
    roi_100    = _normalize_with_none([(e["financial_roi"]      or {}).get("war_per_million") for e in org_summary])
    tools_100  = _normalize_with_none([(e["tools_quality"]      or {}).get("top10_mean")      for e in org_summary])
    # International depth: 0.7 * IFA% + 0.3 * (year_span / 10), capped.
    def _intl_score(e):
        d = e["international_depth"] or {}
        return 0.7 * (d.get("ifa_pct") or 0) + 0.3 * min((d.get("year_span") or 0) / 10.0, 1.0)
    intl_100   = _normalize_to_100([_intl_score(e) for e in org_summary])
    ready_100  = _normalize_to_100([(e["readiness"] or {}).get("pct_signal", 0) for e in org_summary])
    # Health is INVERTED — lower burden score = better. Negate before
    # normalization so the LOWEST burden gets the HIGHEST 100-score.
    health_100 = _normalize_to_100([-(e["health_burden"] or {}).get("score", 0) for e in org_summary])

    for entry, te, dp, dvm, gr, tr, wg, ro, tq, intl, rd, hl in zip(
        org_summary, top_end_100, depth_100, dvm_plus_100, grad_100, traj_100,
        wag_100, roi_100, tools_100, intl_100, ready_100, health_100,
    ):
        entry["score_components"] = {
            "top_end_100":             te,
            "depth_100":               dp,
            "dvm_plus_100":            dvm,
            "grad_100":                gr,
            "trajectory_100":          tr,   # back-compat / tooltip
            "talent_translation_100":  wg,
            "financial_roi_100":       ro,
            "tools_quality_100":       tq,
            "intl_depth_100":          intl,
            "readiness_100":           rd,
            "health_burden_100":       hl,
        }
        # Legacy 10-component blend — preserved on entry so anything that
        # already references farm_score before the tree composite below
        # overwrites it keeps a value to fall back to.
        entry["farm_score_legacy"] = round(
            FARM_WEIGHT_TOP_END             * te
          + FARM_WEIGHT_DEPTH               * dp
          + FARM_WEIGHT_DVM_PLUS            * dvm
          + FARM_WEIGHT_GRAD                * gr
          + FARM_WEIGHT_TALENT_TRANSLATION  * wg
          + FARM_WEIGHT_FINANCIAL_ROI       * ro
          + FARM_WEIGHT_TOOLS_QUALITY       * tq
          + FARM_WEIGHT_INTL_DEPTH          * intl
          + FARM_WEIGHT_READINESS           * rd
          + FARM_WEIGHT_HEALTH              * hl,
            1,
        )
        # farm_score gets overwritten with the tree composite below; we
        # set it here so the field exists if downstream code reads it
        # before the tree pass finishes.
        entry["farm_score"] = entry["farm_score_legacy"]

    # Per-component ranks (1 = best) feed the component letter grades on
    # the report card. The overall rank/letter come from farm_score.
    n_orgs = len(org_summary)
    top_end_rank = _rank_descending([e["top_end_points"]       for e in org_summary])
    depth_rank   = _rank_descending([e["depth_points"]         for e in org_summary])
    dvm_rank     = _rank_descending([e["dvm_plus"]["1y"]       for e in org_summary])
    traj_rank    = _rank_descending([e["trajectory_score"]     for e in org_summary])
    grad_rank    = _rank_descending([e["grad_pipeline_score"]  for e in org_summary])
    overall_rank = _rank_descending([e["farm_score"]           for e in org_summary])

    # Helper to rank a sparse list (None → rank=None, gets "—" letter).
    def _rank_with_none(values: list[float | None]) -> list[int | None]:
        present_idx = [i for i, v in enumerate(values) if v is not None]
        present_vals = [values[i] for i in present_idx]
        sub_ranks = _rank_descending(present_vals)
        out: list[int | None] = [None] * len(values)
        for i, r in zip(present_idx, sub_ranks):
            out[i] = r
        return out

    wag_rank    = _rank_with_none([(e["talent_translation"] or {}).get("wag_mean")        for e in org_summary])
    roi_rank    = _rank_with_none([(e["financial_roi"]      or {}).get("war_per_million") for e in org_summary])
    tools_rank  = _rank_with_none([(e["tools_quality"]      or {}).get("top10_mean")      for e in org_summary])
    intl_rank   = _rank_descending([_intl_score(e)                                          for e in org_summary])
    ready_rank  = _rank_descending([(e["readiness"]      or {}).get("pct_signal", 0)        for e in org_summary])
    # Health rank: LOWEST burden score = rank 1 (best). _rank_descending
    # ranks highest first, so negate the score before passing.
    health_rank = _rank_descending([-(e["health_burden"] or {}).get("score", 0)             for e in org_summary])
    n_with_wag    = sum(1 for r in wag_rank   if r is not None)
    n_with_roi    = sum(1 for r in roi_rank   if r is not None)
    n_with_tools  = sum(1 for r in tools_rank if r is not None)

    for entry, te_r, dp_r, dvm_r, gr_r, tr_r, ov_r, wg_r, ro_r, tq_r, intl_r, rd_r, hl_r in zip(
        org_summary, top_end_rank, depth_rank, dvm_rank, grad_rank, traj_rank, overall_rank,
        wag_rank, roi_rank, tools_rank, intl_rank, ready_rank, health_rank,
    ):
        entry["component_ranks"] = {
            "top_end":            te_r,
            "depth":              dp_r,
            "dvm_plus":           dvm_r,
            "trajectory":         tr_r,
            "grad":               gr_r,
            "talent_translation": wg_r,
            "financial_roi":      ro_r,
            "tools_quality":      tq_r,
            "intl_depth":         intl_r,
            "readiness":          rd_r,
            "health_burden":      hl_r,
        }
        # Letter grades. None ranks → "—" (insufficient data). Small
        # samples for WAG / ROI / Tools+ also get "—" via the same
        # gate so a 1-graduate org doesn't get an A or D off a single
        # data point.
        entry["grades"] = {
            "top_end":            _letter_grade(te_r, n_orgs),
            "depth":              _letter_grade(dp_r, n_orgs),
            "dvm_plus":           _letter_grade(dvm_r, n_orgs),
            "trajectory":         _letter_grade(tr_r, n_orgs),
            "grad":               _letter_grade(gr_r, n_orgs),
            "talent_translation": (_letter_grade(wg_r, n_with_wag)
                                    if wg_r is not None
                                    and (entry["talent_translation"]["grad_count"] or 0) >= 3 else "—"),
            "financial_roi":      (_letter_grade(ro_r, n_with_roi)
                                    if ro_r is not None
                                    and (entry["financial_roi"]["grad_count_with_bonus"] or 0) >= 3 else "—"),
            "tools_quality":      (_letter_grade(tq_r, n_with_tools)
                                    if tq_r is not None
                                    and (entry["tools_quality"]["graded_count"] or 0) >= 5 else "—"),
            "intl_depth":         _letter_grade(intl_r, n_orgs),
            "readiness":          _letter_grade(rd_r, n_orgs),
            "health_burden":      _letter_grade(hl_r, n_orgs),
            "overall":            _letter_grade(ov_r, n_orgs),
        }

    # ────────────────────────────────────────────────────────────────────────
    # ── Farm Grade Tree v2 — main grade composites + new farm_score ──
    # ────────────────────────────────────────────────────────────────────────
    # 11 leaf metrics, each independently z-normalized across orgs.
    # Sparse-data orgs get None for that leaf and the parent main grade
    # falls back to the mean of its present sub-grades. Composite
    # farm_score = weighted sum of the 5 main-grade 100-anchored scores.

    def _zscore_to_100(values: list[float | None],
                       higher_is_better: bool = True) -> list[float | None]:
        """Per-org list → 100-anchored z-score list. None stays None.
        Mirrors the wRC+/OPS+ 100-anchor (μ → 100, +1σ → 110)."""
        present = [v for v in values if v is not None]
        if len(present) < 3:
            return [None] * len(values)
        mu = sum(present) / len(present)
        var = sum((v - mu) ** 2 for v in present) / len(present)
        sd = var ** 0.5
        if sd < 1e-6:
            return [100.0 if v is not None else None for v in values]
        sign = 1.0 if higher_is_better else -1.0
        out: list[float | None] = []
        for v in values:
            if v is None:
                out.append(None)
            else:
                out.append(round(100 + 10 * sign * (v - mu) / sd, 1))
        return out

    # ── v3 leaf scoring with multi-input composites ──
    # Some leaves blend 2-3 z-scored sub-inputs (e.g. IFA Performance =
    # WAG + WAR/yr + Cumulative WAR). Each sub-input is anchored at 100
    # across orgs with present data; the leaf score is the mean of
    # present sub-input scores per org. Single-input leaves use the
    # existing 1-input z-score path.
    LEAF_SPECS: dict[str, list[tuple[str, callable]]] = {
        # IFA Performance — 3 inputs (WAG / WAR-per-year / cumulative WAR)
        "acq_ifa": [
            ("wag",        lambda e: (e["tree"]["acq_ifa"] or {}).get("wag_mean")),
            ("war_per_yr", lambda e: (e["tree"]["acq_ifa"] or {}).get("war_per_yr_mean")),
            ("cum_war",    lambda e: (e["tree"]["acq_ifa"] or {}).get("career_war_mean")),
        ],
        # Draft Performance — pick-slot-adjusted value + ceiling-hits %
        "acq_draft": [
            ("pick_value", lambda e: ((e["tree"]["acq_draft"] or {}).get("pick_value_mean")
                                      or (e["tree"]["acq_draft"] or {}).get("wag_mean"))),
            ("ceiling_pct", lambda e: (e["tree"]["acq_draft"] or {}).get("ceiling_hits_pct")),
        ],
        # Trade Acumen — net FV + retrospective WAR delta
        "tx_trades": [
            ("net_fv",    lambda e: (e["tree"]["tx_trades"] or {}).get("net_fv")),
            ("war_delta", lambda e: (e["tree"]["tx_trades"] or {}).get("war_delta")),
        ],
        # Waiver Claims — net FV + reach-MLB hit rate
        "tx_waivers": [
            ("net_fv",   lambda e: (e["tree"]["tx_waivers"] or {}).get("net_fv")),
            ("hit_rate", lambda e: (e["tree"]["tx_waivers"] or {}).get("hit_rate")),
        ],
        # Development — single-input (per-tool DvM+ composite)
        "dev_hitter":  [("dvm_plus", lambda e: (e["tree"]["dev_hitter"]  or {}).get("dvm_plus"))],
        "dev_pitcher": [("dvm_plus", lambda e: (e["tree"]["dev_pitcher"] or {}).get("dvm_plus"))],
        # Financial — single-input each
        "fin_war_per_m":        [("war_per_m", lambda e: (e["tree"]["fin_war_per_m"]        or {}).get("value"))],
        "fin_contract_surplus": [("surplus",   lambda e: (e["tree"]["fin_contract_surplus"] or {}).get("mean_usd_per_yr"))],
        # MLB Production — 3 inputs each (WAG / WAR-per-year / cumulative WAR)
        "mlb_hitter_wag": [
            ("wag",        lambda e: (e["tree"]["mlb_hitter_wag"] or {}).get("wag_mean")),
            ("war_per_yr", lambda e: (e["tree"]["mlb_hitter_wag"] or {}).get("war_per_yr_mean")),
            ("cum_war",    lambda e: (e["tree"]["mlb_hitter_wag"] or {}).get("career_war_mean")),
        ],
        "mlb_pitcher_wag": [
            ("wag",        lambda e: (e["tree"]["mlb_pitcher_wag"] or {}).get("wag_mean")),
            ("war_per_yr", lambda e: (e["tree"]["mlb_pitcher_wag"] or {}).get("war_per_yr_mean")),
            ("cum_war",    lambda e: (e["tree"]["mlb_pitcher_wag"] or {}).get("career_war_mean")),
        ],
    }
    # Compute each leaf's 100-anchored per-org list. Multi-input leaves
    # z-score each sub-input independently then average the present
    # z-scores per org (so sparse sub-inputs don't drag the leaf to None
    # if at least one is present).
    leaf_100: dict[str, list[float | None]] = {}
    leaf_raw: dict[str, list[float | None]] = {}  # back-compat for tests
    for leaf_key, specs in LEAF_SPECS.items():
        sub_z_lists = []
        for _, getter in specs:
            raw = [getter(e) for e in org_summary]
            sub_z_lists.append(_zscore_to_100(raw, higher_is_better=True))
        # Per-org leaf score = mean of present sub-input z-scores.
        per_org_scores: list[float | None] = []
        for i in range(len(org_summary)):
            present = [z[i] for z in sub_z_lists if z[i] is not None]
            per_org_scores.append(round(sum(present) / len(present), 1)
                                  if present else None)
        leaf_100[leaf_key] = per_org_scores
        # Back-compat: leaf_raw[k] points to the FIRST sub-input's raw
        # values (used by some legacy test inspections).
        leaf_raw[leaf_key] = [specs[0][1](e) for e in org_summary]

    # Stamp leaf 100-anchored scores onto each org for display.
    for i, entry in enumerate(org_summary):
        for k, vs in leaf_100.items():
            entry["tree"][k]["score_100"] = vs[i]

    # Build main-grade scores by averaging the 100-anchored leaves
    # present for that parent. Orgs with NO present leaves under a
    # parent get None for that main grade (rare — usually only when
    # all sub-grades sparse-gated out).
    # v3 tree shape — Acquisition Strategy absorbs both the prior
    # Acquisitions (IFA + Draft) and Transactions (Trade + Waiver)
    # branches. Four main parents, ten leaves total.
    TREE_PARENTS = {
        "acquisition_strategy": ["acq_ifa", "acq_draft", "tx_trades", "tx_waivers"],
        "development":          ["dev_hitter", "dev_pitcher"],
        "financial":            ["fin_war_per_m", "fin_contract_surplus"],
        "mlb_production":       ["mlb_hitter_wag", "mlb_pitcher_wag"],
    }
    # Legacy parent aliases — kept so any UI or test still reading
    # entry["acquisitions_score"] / entry["transactions_score"]
    # resolves to a sensible value (the parent's score, or None).
    for i, entry in enumerate(org_summary):
        for parent, leaves in TREE_PARENTS.items():
            vs = [leaf_100[k][i] for k in leaves if leaf_100[k][i] is not None]
            entry[f"{parent}_score"] = (
                round(sum(vs) / len(vs), 1) if vs else None
            )
        # Composite farm_score from the 4 main grades (v3), weighted.
        # Orgs missing a main grade contribute its weight at 100 (league
        # mean) so the overall doesn't get crushed by data-sparse axes.
        weights = {
            "acquisition_strategy": FARM_TREE_WEIGHT_ACQUISITION_STRATEGY,
            "development":          FARM_TREE_WEIGHT_DEVELOPMENT,
            "financial":            FARM_TREE_WEIGHT_FINANCIAL,
            "mlb_production":       FARM_TREE_WEIGHT_MLB_PRODUCTION,
        }
        composite = 0.0
        for parent, w in weights.items():
            v = entry.get(f"{parent}_score")
            composite += w * (v if v is not None else 100.0)
        entry["farm_score"] = round(composite, 1)
        # Back-compat: legacy field names (acquisitions_score,
        # transactions_score) resolve to the merged Acquisition Strategy
        # value so any UI reading the old keys still gets a number.
        entry["acquisitions_score"] = entry.get("acquisition_strategy_score")
        entry["transactions_score"] = entry.get("acquisition_strategy_score")

    # Letter grades for the 11 leaves + 5 main + composite (17 total).
    # Sparse-data leaves get "—"; sparse parents and composite always grade
    # (since they fall back to 100 for missing children).
    def _rank_list(values: list[float | None]) -> list[int | None]:
        idx = [i for i, v in enumerate(values) if v is not None]
        sub = _rank_descending([values[i] for i in idx])
        ranks: list[int | None] = [None] * len(values)
        for i, r in zip(idx, sub):
            ranks[i] = r
        return ranks

    leaf_ranks = {k: _rank_list(vs) for k, vs in leaf_100.items()}
    parent_ranks = {
        parent: _rank_list([e.get(f"{parent}_score") for e in org_summary])
        for parent in TREE_PARENTS
    }
    composite_rank = _rank_list([e["farm_score"] for e in org_summary])

    n_orgs_tree = len(org_summary)
    for i, entry in enumerate(org_summary):
        # Update entry["grades"] with the v3 tree grades. Existing legacy
        # grades stay so the report-card glossary references still resolve.
        g = entry.get("grades") or {}
        # 4 main grades + back-compat aliases for the old 5-branch names
        for parent in TREE_PARENTS:
            r = parent_ranks[parent][i]
            present_n = sum(1 for x in parent_ranks[parent] if x is not None)
            g[parent] = _letter_grade(r, present_n) if r is not None else "—"
        # Back-compat: legacy keys still readable by old UI code paths.
        g["acquisitions"] = g.get("acquisition_strategy", "—")
        g["transactions"] = g.get("acquisition_strategy", "—")
        # 10 sub-grades — keyed identically to leaf_raw
        for k in leaf_raw:
            r = leaf_ranks[k][i]
            present_n = sum(1 for x in leaf_ranks[k] if x is not None)
            g[k] = _letter_grade(r, present_n) if r is not None else "—"
        # Composite (overwrites the legacy `overall` letter so the
        # displayed grade matches the displayed farm_score).
        r = composite_rank[i]
        g["overall"] = _letter_grade(r, n_orgs_tree) if r is not None else "—"
        entry["grades"] = g
        # Also stamp the ranks so the UI can read off them directly.
        cr = entry.get("component_ranks") or {}
        for parent in TREE_PARENTS:
            cr[parent] = parent_ranks[parent][i]
        cr["acquisitions"] = cr.get("acquisition_strategy")  # back-compat
        cr["transactions"] = cr.get("acquisition_strategy")  # back-compat
        for k in leaf_raw:
            cr[k] = leaf_ranks[k][i]
        cr["overall"] = composite_rank[i]
        entry["component_ranks"] = cr

    # Final sort + farm_rank assignment off of farm_score. Tiebreak by
    # top_end_points so the org with better stars edges out an equal one.
    org_summary.sort(key=lambda x: (-x["farm_score"], -x["top_end_points"]))
    for rank_i, entry in enumerate(org_summary, start=1):
        entry["farm_rank"] = rank_i
    # ────────────────────────────────────────────────────────────────────────

    # ── Per-org draft spending (computed from our acquisitions table) ──
    # The acquisitions table records `bonus_usd` for every drafted player
    # we know about — sum by org × year to produce a comparison set for
    # the IFA spending totals fed in by Spotrac. Pulls from EVERY drafted
    # player on file (graduates included), not just current actives, so
    # the multi-year history reflects each org's full cycle spending.
    draft_spending_by_org: dict[str, dict[int, dict]] = {}
    for key, rec in acquisitions.items():
        if (rec or {}).get("method") != "draft":
            continue
        bonus = rec.get("bonus_usd")
        year = rec.get("year")
        if bonus is None or year is None:
            continue
        # Resolve the player's CURRENT org. For drafted prospects the
        # acquiring team is on the rec, but trades may have moved them
        # elsewhere — we credit the *acquiring* org rather than the
        # current one because that's the spending-decision attribution
        # that matches what Spotrac's per-year IFA tracker does.
        team_name = rec.get("team_name")
        from trades import canonical_org
        org_code = canonical_org(team_name) if team_name else None
        if not org_code:
            continue
        bucket = draft_spending_by_org.setdefault(org_code, {}).setdefault(year, {
            "total_usd": 0, "signings": 0, "top_bonus": 0, "top_player": None,
        })
        bucket["total_usd"] += bonus
        bucket["signings"]  += 1
        if bonus > bucket["top_bonus"]:
            bucket["top_bonus"]  = bonus
            # Look up the player name — acquisitions records don't carry
            # it directly, but the player_key works well enough as a
            # display fallback (the farm page can resolve to full name
            # via the active/grad maps if needed).
            bucket["top_player"] = key

    # Attach IFA + draft spending to each org_summary entry so the farm
    # detail page can render a side-by-side comparison without joining
    # back to top-level payload structures.
    for entry in org_summary:
        org_code = entry["org"]
        entry["ifa_spending"]   = ifa_spending_by_org.get(org_code, {})
        entry["draft_spending"] = draft_spending_by_org.get(org_code, {})

    active_payload = [_serialize(p) for p in actives]
    inactive_payload = [_serialize(p) for p in inactives]
    graduate_payload = [_serialize(p) for p in grads]
    graduate_payload.sort(key=lambda p: p.get("graduation_date") or "", reverse=True)

    # X+ tool composites need cohort mean/stdev. Use the union of all
    # serialized prospects so a single norm anchors actives / inactives /
    # grads consistently — a graduate's last tool grade still reads
    # "+12 vs cohort mean" the same way it would have the day before
    # he graduated. Single call ensures every payload's composite_*_plus
    # references the same baseline.
    _attach_tool_plus_indices(active_payload + inactive_payload + graduate_payload)

    # Cleanup: `_active_keys` was retained on org_summary entries for
    # potential post-serialization joins (now unused after Tools+ moved
    # into the actives loop). Drop the field so the JSON doesn't carry
    # an internal-only key.
    for entry in org_summary:
        entry.pop("_active_keys", None)

    from prospect_savant import attach_prospect_savant
    savant_matched = attach_prospect_savant(
        active_payload + inactive_payload + graduate_payload,
        Path(__file__).parent,
    )

    from spotlights import build_spotlights
    spotlight_payload = build_spotlights(active_payload, graduate_payload)

    # Split the export into a boot-critical file plus three lazy-loaded
    # sidecars so a first-paint download doesn't drag along ~40MB of
    # graduate / inactive / affiliate-roster data that the user typically
    # doesn't need until they navigate to those tabs.
    #
    #   timeseries.json   — meta + active players + spotlights + org
    #                       summaries + level/trajectory norms (boot path)
    #   graduates.json    — graduate-player payloads
    #   inactive.json     — inactive-player payloads
    #   rosters_by_org.json — per-org affiliate rosters (farm-detail only)
    #
    # The boot file carries `_slices` so the frontend knows which sidecars
    # exist and can fetch them on first tab-switch. Counts are duplicated
    # into the boot meta so empty-state copy can render before the slice
    # arrives.
    # NOTE: the boot JSON intentionally omits `graduates`, `inactive`, and
    # `rosters_by_org` — those slices live in sidecar files and the frontend
    # fetches them on demand. Tests that want a single dict can call
    # `load_export_unified(out_path)` to reassemble them.
    # ── Scout-reports extraction (Tier 2 perf — slice splitting) ──
    # The FanGraphs scout report prose lives inside per_source.fangraphs.
    # tools._extras.report on most snapshots. Across all players it's
    # ~11MB of repeated prose (same text often carries across cycles for
    # a single prospect). Extract the LATEST report per source per
    # player into a separate sidecar so the boot file shrinks ~17%.
    # Strip the `report` string from every per_source._extras dict in
    # the boot payload to dedupe.
    scout_reports_sidecar: dict[str, dict[str, dict]] = {}
    def _harvest_and_strip_reports(player_payload):
        pkey = player_payload.get("player_key")
        latest_by_src: dict[str, dict] = {}
        for pt in (player_payload.get("points") or []):
            for src, info in (pt.get("per_source") or {}).items():
                tools = (info or {}).get("tools") or {}
                ex = tools.get("_extras") or {}
                rpt = ex.get("report")
                if rpt:
                    # Snapshot the newest report per source (loop walks
                    # in date order — later iterations overwrite earlier).
                    latest_by_src[src] = {
                        "date": pt.get("snapshot_date"),
                        "label": pt.get("interval_label"),
                        "text": rpt,
                    }
                    # Strip the report from the inline _extras so it
                    # doesn't bloat the boot payload.
                    ex["report"] = None
        if latest_by_src:
            scout_reports_sidecar[pkey] = latest_by_src
    for p in active_payload:
        _harvest_and_strip_reports(p)
    for p in graduate_payload:
        _harvest_and_strip_reports(p)
    for p in inactive_payload:
        _harvest_and_strip_reports(p)

    boot = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run": latest_run_summary(),
        "total_tracked": len(timeseries),
        "active_count": len(actives),
        "inactive_count": len(inactives),
        "graduate_count": len(grads),
        "inactive_cutoff": cutoff.isoformat(),
        "prospect_savant_count": savant_matched,
        "players":    active_payload,
        "spotlights": spotlight_payload,
        "org_summary": org_summary,
        "farm_trajectory_means": farm_trajectory_means,
        "farm_trajectory_stdevs": farm_trajectory_stdevs,
        "level_norms": level_norms,
        # MLB Draft bonus-pool ceilings + per-pick slot values, scraped
        # from MLB.com per year. Keyed by year (int). Drives the
        # spending-block utilization caption on the farm detail page.
        "mlb_draft_pools": draft_pools,
        "_slices": {
            "graduates":      "graduates.json",
            "inactive":       "inactive.json",
            "rosters_by_org": "rosters_by_org.json",
            "scout_reports":  "scout_reports.json",
        },
    }
    out_dir = out_path.parent
    # Compact JSON (no indent, no spaces in separators) — cuts the boot
    # payload roughly in half. The files are still valid JSON, just not
    # human-readable. Open in a browser DevTools console + JSON.parse if
    # you need to inspect interactively.
    _compact = {"separators": (",", ":")}
    out_path.write_text(json.dumps(boot, **_compact))
    (out_dir / "graduates.json").write_text(json.dumps(graduate_payload, **_compact))
    (out_dir / "inactive.json").write_text(json.dumps(inactive_payload, **_compact))
    (out_dir / "rosters_by_org.json").write_text(json.dumps(rosters_by_org, **_compact))
    (out_dir / "scout_reports.json").write_text(json.dumps(scout_reports_sidecar, **_compact))
    return out_path


def load_export_unified(boot_path: Path) -> dict:
    """Inverse of `export_timeseries_json`'s split — reads the boot JSON
    and inlines `graduates` / `inactive` / `rosters_by_org` /
    `scout_reports` from the sidecar files (if they exist) so callers
    (mostly tests) can work with a single dict.

    Returns the boot dict unchanged when the sidecars aren't present
    (legacy monolithic export, or a partial run).
    """
    boot_path = Path(boot_path)
    payload = json.loads(boot_path.read_text())
    out_dir = boot_path.parent
    for slice_name in ("graduates", "inactive", "rosters_by_org", "scout_reports"):
        if slice_name in payload:
            continue
        sidecar = out_dir / f"{slice_name}.json"
        if sidecar.exists():
            payload[slice_name] = json.loads(sidecar.read_text())
        else:
            # Empty default keeps test assertions like `for g in
            # payload["graduates"]` from raising KeyError when the slice
            # is genuinely empty for this run.
            payload[slice_name] = [] if slice_name == "graduates" or slice_name == "inactive" else {}
    return payload
