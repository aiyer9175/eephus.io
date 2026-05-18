"""
Seed the database with realistic v3.1 data:

  - 25 prospects spanning consensusFV 70 down to 45
  - Multiple update intervals per source
  - FG graduates entries for players who crossed the rookie threshold
    in 2025 or 2026 (McGonigle, McLean, Wetherholt, Yesavage, etc.)
  - Plausible current-season MiLB stat lines

The sample is intentionally smaller than 100 for the demo (would need
hand-curating 100 real rows per source × per interval = thousands of rows),
but the back-end pipeline handles 100+ identically — `export_timeseries_json`
trims to `top_n_active=100` from whatever it's given.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from scrapers import Snapshot, normalize_key
from stats import StatLine
from storage import (
    init_db, insert_snapshots, upsert_statlines,
    export_timeseries_json, start_run, finish_run, load_all_snapshots,
)
from consensus import build_timeseries


def _s(source, snap_date, label, name, pos, org,
       rank=None, fv=None, status="active"):
    return Snapshot(
        source=source, snapshot_date=snap_date, interval_label=label,
        player_key=normalize_key(name), player_name=name,
        position=pos, org=org, rank=rank, fv=fv, status=status,
    )


# ---------------------------------------------------------------------------
# Per-prospect ranking data
# ---------------------------------------------------------------------------

# Each tuple: (player_name, pos, org, list of (source, date, label, rank, fv, status))
PROSPECT_RANKINGS = [
    # === TIER 1: Top 5 (consensus 65-70) ===
    ("Konnor Griffin", "SS/OF", "PIT", [
        ("fangraphs",         "2024-07-30", "FG 2024 Updated",     45,  50.0, "active"),
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      18,  55.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",      2,  65.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       1,  70.0, "active"),
        ("espn",              "2025-01-28", "ESPN 2025 Preseason", 22,  55.0, "active"),
        ("espn",              "2025-07-15", "ESPN 2025 Midseason",  2,  60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  1,  65.0, "active"),
        ("just_baseball",     "2026-03-04", "JB 2026 Preseason",    1,  65.0, "active"),
        ("tjstats",           "2026-01-27", "TJ 2026 Preseason",    1,  65.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",        1,  70.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          1,  70.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           1,  None, "active"),
        ("mlb_pipeline",     "2026-01-22", "Pipeline 2026",         1,  None, "active"),
        ("the_athletic",     "2026-01-26", "Athletic 2026",         1,  None, "active"),
    ]),
    ("Leo De Vries", "SS", "ATH", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      22, 55.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",      6, 60.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       2, 65.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  3, 60.0, "active"),
        ("just_baseball",     "2026-03-04", "JB 2026 Preseason",    3, 60.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",        2, 65.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          2, 65.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           2, None, "active"),
        ("mlb_pipeline",     "2026-01-22", "Pipeline 2026",         4, None, "active"),
    ]),
    ("Jesus Made", "SS/2B", "MIL", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      35, 50.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     12, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       5, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  5, 60.0, "active"),
        ("just_baseball",     "2026-03-04", "JB 2026 Preseason",    6, 60.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",        4, 60.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          3, 65.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           3, None, "active"),
        ("mlb_pipeline",     "2026-01-22", "Pipeline 2026",         3, None, "active"),
    ]),
    ("Sebastian Walcott", "SS/3B", "TEX", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",       8, 60.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",      3, 65.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       4, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  6, 60.0, "active"),
        ("just_baseball",     "2026-03-04", "JB 2026 Preseason",    8, 55.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",       11, 55.0, "injured_list"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         13, 55.0, "injured_list"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          12, None, "injured_list"),
    ]),
    ("Samuel Basallo", "C/1B", "BAL", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      19, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       7, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  8, 60.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          6, 60.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           6, None, "active"),
        ("the_athletic",     "2026-01-26", "Athletic 2026",         8, None, "active"),
    ]),

    # === TIER 2: 55-60 FV ===
    ("Colt Emerson", "SS", "SEA", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      28, 50.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       9, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 11, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          8, 60.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           7, None, "active"),
    ]),
    ("Ethan Holliday", "SS/3B", "COL", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      10, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  7, 55.0, "active"),
        ("just_baseball",     "2026-03-04", "JB 2026 Preseason",    9, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          9, 55.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           8, None, "active"),
    ]),
    ("Max Clark", "OF", "DET", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      31, 50.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       6, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  9, 60.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          5, 60.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           5, None, "active"),
        ("mlb_pipeline",     "2026-01-22", "Pipeline 2026",         8, None, "active"),
    ]),
    ("Eli Willits", "SS", "WSH", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      11, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 14, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         10, 55.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          10, None, "active"),
    ]),
    ("Bryce Rainer", "SS", "DET", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      22, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 18, 55.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",       24, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         29, 50.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          29, None, "active"),
    ]),
    ("Travis Bazzana", "2B", "CLE", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      14, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      15, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 17, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         13, 55.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          14, None, "active"),
    ]),
    ("Carson Williams", "SS", "TBR", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",       9, 60.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     11, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      14, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 12, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         12, 55.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          11, None, "active"),
    ]),
    ("Trey Yesavage", "RHP", "TOR", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      48, 50.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     19, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      13, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 20, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         14, 55.0, "active"),
    ]),

    # === TIER 3: 50-55 FV ===
    ("Aidan Smith", "OF", "SEA", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      25, 50.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 31, 50.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         28, 50.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          27, None, "active"),
    ]),
    ("Termarr Johnson", "2B", "PIT", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      34, 50.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      45, 50.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 38, 50.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         42, 50.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          41, None, "active"),
    ]),
    ("Jonah Tong", "RHP", "NYM", [
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     58, 50.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      28, 55.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 33, 50.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         25, 55.0, "active"),
    ]),
    ("Coby Mayo", "3B/1B", "BAL", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      30, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      32, 50.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 35, 50.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          30, None, "active"),
    ]),
    ("Roldy Brito", "SS/OF", "COL", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      None, 45.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",        85, 45.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",          68, 50.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",           92, None, "active"),
    ]),
    ("Charlie Condon", "OF/3B", "COL", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      21, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      35, 50.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 28, 55.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         32, 50.0, "active"),
    ]),
    ("Caleb Bonemer", "SS", "CHW", [
        ("fangraphs",         "2026-02-16", "FG 2026 Report",      52, 50.0, "active"),
        ("tjstats",           "2026-04-13", "TJ 2026 April",       47, 50.0, "active"),
        ("tjstats",           "2026-05-13", "TJ 2026 May",         38, 55.0, "active"),
        ("baseball_america", "2026-05-13", "BA 2026 May",          44, None, "active"),
    ]),

    # === GRADUATES (FG graduates page captures the final FV) ===
    ("Kevin McGonigle", "SS", "DET", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      14, 60.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",      4, 65.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       2, 65.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason",  2, 65.0, "active"),
        ("baseball_america", "2026-01-21", "BA 2026 Preseason",     2, None, "active"),
        # The FG graduates page picks him up after he loses rookie status:
        ("fangraphs",         "2026-05-14", "FG 2026 Graduates", None, 65.0, "graduated"),
    ]),
    ("JJ Wetherholt", "INF", "STL", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",       7, 60.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",      8, 60.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       8, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 10, 60.0, "active"),
        ("baseball_america", "2026-01-21", "BA 2026 Preseason",     6, None, "active"),
        ("fangraphs",         "2026-05-14", "FG 2026 Graduates", None, 60.0, "graduated"),
    ]),
    ("Nolan McLean", "RHP", "NYM", [
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     24, 55.0, "active"),
        ("fangraphs",         "2026-02-16", "FG 2026 Report",       3, 60.0, "active"),
        ("espn",              "2026-01-27", "ESPN 2026 Preseason", 15, 55.0, "active"),
        ("tjstats",           "2026-01-27", "TJ 2026 Preseason",   11, 60.0, "active"),
        ("fangraphs",         "2026-05-14", "FG 2026 Graduates", None, 60.0, "graduated"),
    ]),
    ("Bubba Chandler", "RHP", "PIT", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",      12, 60.0, "active"),
        ("fangraphs",         "2025-07-29", "FG 2025 Updated",     14, 55.0, "active"),
        ("espn",              "2025-07-15", "ESPN 2025 Midseason", 18, 55.0, "active"),
        ("fangraphs",         "2025-10-15", "FG 2025 Graduates", None, 55.0, "graduated"),
    ]),
    ("Roki Sasaki", "RHP", "LAD", [
        ("fangraphs",         "2025-02-15", "FG 2025 Report",       1, 65.0, "active"),
        ("espn",              "2025-01-28", "ESPN 2025 Preseason",  1, 60.0, "active"),
        ("baseball_america", "2025-01-20", "BA 2025 Preseason",     1, None, "active"),
        ("fangraphs",         "2025-10-15", "FG 2025 Graduates", None, 65.0, "graduated"),
    ]),
]


def _flatten() -> list[Snapshot]:
    snaps = []
    for name, pos, org, entries in PROSPECT_RANKINGS:
        for source, date_, label, rank, fv, status in entries:
            snaps.append(_s(source, date_, label, name, pos, org,
                            rank=rank, fv=fv, status=status))
    return snaps


# ---------------------------------------------------------------------------
# Plausible MiLB stat lines (active prospects only)
# ---------------------------------------------------------------------------

def _hitter(name, level, games, slash, hr, sb, bb, k):
    return StatLine(
        player_key=normalize_key(name),
        mlbam_id=hash(name) & 0xFFFFFF,
        level=level, games=games,
        avg=slash[0], obp=slash[1], slg=slash[2],
        ops=f"{float(slash[1]) + float(slash[2]):.3f}",
        hr=hr, sb=sb, bb_pct=bb, k_pct=k,
        era=None, fip=None, ip=None, k_per_9=None, bb_per_9=None,
        is_pitcher=False, fetched_at="2026-05-14",
    )


def _pitcher(name, level, games, era, ip, k9, bb9):
    return StatLine(
        player_key=normalize_key(name),
        mlbam_id=hash(name) & 0xFFFFFF,
        level=level, games=games,
        avg=None, obp=None, slg=None, ops=None, hr=None, sb=None,
        bb_pct=None, k_pct=None,
        era=era, fip=None, ip=ip, k_per_9=k9, bb_per_9=bb9,
        is_pitcher=True, fetched_at="2026-05-14",
    )


SEED_STATS = {
    sl.player_key: sl for sl in [
        _hitter("Konnor Griffin",   "AAA", 32, (".311", ".402", ".551"), 8, 18, 12.4, 19.8),
        _hitter("Leo De Vries",     "AA",  34, (".287", ".385", ".512"), 7, 10, 13.1, 22.4),
        _hitter("Jesus Made",       "AA",  35, (".302", ".388", ".498"), 6, 14, 11.8, 18.3),
        _hitter("Samuel Basallo",   "AAA", 30, (".271", ".362", ".510"), 9,  1, 11.2, 23.6),
        _hitter("Colt Emerson",     "AA",  31, (".294", ".395", ".475"), 5,  6, 13.5, 17.9),
        _hitter("Ethan Holliday",   "A+",  33, (".266", ".370", ".468"), 7,  4, 13.8, 22.1),
        _hitter("Max Clark",        "AA",  32, (".298", ".411", ".512"), 6, 11, 14.7, 18.4),
        _hitter("Eli Willits",      "A",   29, (".275", ".384", ".423"), 3,  9, 14.1, 16.2),
        _hitter("Bryce Rainer",     "A+",  18, (".224", ".321", ".384"), 2,  1, 11.5, 28.7),
        _hitter("Travis Bazzana",   "AA",  33, (".302", ".407", ".521"), 8,  8, 14.2, 19.6),
        _hitter("Carson Williams",  "AAA", 32, (".253", ".348", ".471"), 9, 14, 11.6, 31.4),
        _pitcher("Trey Yesavage",   "AA",  8, "2.81", 41.2, 12.4, 3.1),
        _hitter("Aidan Smith",      "A+",  30, (".282", ".381", ".454"), 5,  8, 13.0, 21.7),
        _hitter("Termarr Johnson",  "AAA", 31, (".248", ".376", ".411"), 4,  3, 15.4, 18.9),
        _pitcher("Jonah Tong",      "AA",  7, "2.41", 37.1, 13.6, 2.7),
        _hitter("Coby Mayo",        "AAA", 28, (".284", ".367", ".514"), 8,  1, 10.9, 25.2),
        _hitter("Roldy Brito",      "A",   30, (".334", ".425", ".521"), 4, 22, 14.2, 15.6),
        _hitter("Charlie Condon",   "AA",  28, (".267", ".341", ".472"), 7,  2, 10.1, 26.8),
        _hitter("Caleb Bonemer",    "A",   31, (".291", ".404", ".478"), 6,  9, 15.8, 19.3),
    ]
}


def main():
    init_db()
    run_id = start_run()
    snaps = _flatten()
    new_count = insert_snapshots(snaps)
    print(f"Inserted {new_count} seed snapshots covering "
          f"{len(set(s.player_key for s in snaps))} prospects")

    n_stats = upsert_statlines(SEED_STATS, season=2026)
    print(f"Upserted {n_stats} stat lines")

    all_snaps = load_all_snapshots()
    timeseries = build_timeseries(all_snaps)
    print(f"Built timeseries for {len(timeseries)} players "
          f"({sum(1 for p in timeseries if p.status == 'graduated')} graduated)")

    out = Path(__file__).parent / "data" / "timeseries.json"
    out.parent.mkdir(exist_ok=True)
    sl_dict = {k: asdict(v) for k, v in SEED_STATS.items()}
    export_timeseries_json(timeseries, out, statlines=sl_dict, top_n_active=100)
    print(f"Wrote {out}")

    finish_run(run_id, new_snapshots=new_count, stat_lines=n_stats,
               notes="v3.1 seed: graduates page + top-100 split")


if __name__ == "__main__":
    main()
