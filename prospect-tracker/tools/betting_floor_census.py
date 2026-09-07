# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""How many sides actually clear the floor, measured instead of estimated.

WHY THIS EXISTS. Every volume decision downstream of it (how many paper bets a
slate logs, how many slate days it takes a per-tag min-edge sweep to reach 100
settled rows, whether a calibration ledger is 10 rows a night or 50) was about
to be built on ONE number: a live replay of a single snapshot that returned 84
priced sides and 22 clearing a 6 percent floor.

That 22 is not a measurement of the current pipeline. It was produced BEFORE:

  * the in-game event filter (a book keeps a started game listed at an in-game
    price, and those sides came out as the largest edges on the board),
  * the whole-number total push adjustment (EV was overstated by 1/(1-p_push)),
  * the minimum-hold de-vig book choice and its staleness/consensus guards,
  * the agreed-line rule that stopped two books' different runlines being fused
    into one row.

Each of those removes edge, none of them adds any. So this tool replays EVERY
cached snapshot through the CURRENT betting_export code path and publishes the
distribution that comes out, per snapshot and per slate date, with the counts
that feed the three ledgers.

WHAT IT IS NOT. It is not a backtest and it grades nothing. It counts sides. The
model probabilities come from `betting_model.inputs_as_of(slate)`, so the
leaderboards are the vintage strictly before the slate and the count is not
contaminated by the games being priced; when no vintage exists the row says so
and is counted separately rather than quietly pooled.

THE SLATE UNIT. A capture is labelled by its earliest event, so one snapshot
routinely carries two slate dates (measured: 2026-08-07-2229 holds 15 events on
the 08-07 slate and 15 on 08-08). A cell here is therefore (snapshot, slate
date), and the per-slate arrival rate takes the LATEST snapshot that still has
pregame coverage of that slate, which is the one a nightly at capture time would
have priced against.

RUN IT:
    python tools/betting_floor_census.py
    python tools/betting_floor_census.py --floor 0.06 --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import betting_export as be                                    # noqa: E402
import betting_ingest as bi                                    # noqa: E402
import betting_model as bm                                     # noqa: E402

ODDS_DIR = ROOT / ".cache" / "odds"
COMPLETED = ROOT / ".cache" / "betting" / "completed_games.json"

#: The shared floor both published slots read. Imported rather than retyped so
#: this census can never drift from the number the page uses.
DEFAULT_FLOOR = be.PROVISIONAL_MIN_EDGE

MARKETS = ("moneyline", "runline", "total")

#: A cell counts as a full slate when this share of the slate's events were
#: still pregame at capture time. 0.8 rather than 1.0 because one early
#: afternoon game being under way does not make the other fourteen a partial
#: board, and rather than 0.5 because half a slate priced is not a slate.
FULL_SLATE_COVERAGE = 0.8

#: The slate size the per-event rate is projected onto. 15 is a full MLB day,
#: and every number derived from it is labelled a projection.
TYPICAL_SLATE_GAMES = 15


def _stamp(s):
    return be._stamp(s)


def _completed_index() -> dict:
    """(date, home_org, away_org) -> the finished game, for the probables.

    The starters here are the ones who ACTUALLY started, not the probables that
    were posted at capture time. For a count of priced sides that is a fair
    substitute and it is stated rather than hidden: a scratch changes one
    game's lambda, it does not change how many sides a board carries."""
    try:
        rows = json.loads(COMPLETED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for r in rows or []:
        k = (r.get("date"), r.get("home_org"), r.get("away_org"))
        if all(k):
            out[k] = r
    return out


def _games_for(events: list[dict], slate: str, finals: dict) -> tuple[list[dict], dict]:
    """Schedule rows for the pregame events on this slate.

    Built FROM the odds events on purpose. A census of "how many sides did this
    snapshot price" must not also be a test of the schedule join: the historical
    slates are not in data/fantasy.json (that block is refreshed forward every
    night), so a schedule read would return zero games for every date but today
    and the census would measure nothing. `datetime` is the event's own
    commence_time, which makes `match_event` a no-op rather than a variable."""
    games, stats = [], {"n_no_final": 0, "n_no_probables": 0}
    for e in events:
        row = finals.get((slate, e.get("home_org"), e.get("away_org")))
        if row is None:
            stats["n_no_final"] += 1
        if row is not None and not (row.get("home_sp") and row.get("away_sp")):
            stats["n_no_probables"] += 1
        games.append({
            "game_pk": (row or {}).get("game_pk") or e.get("event_id"),
            "date": slate,
            "datetime": e.get("commence_time"),
            "status": "Scheduled",
            "double_header": False,
            "venue": {"name": None},
            "home": {"org": e.get("home_org"), "team": e.get("home_team"),
                     "probable": {"mlbam": (row or {}).get("home_sp")}},
            "away": {"org": e.get("away_org"), "team": e.get("away_team"),
                     "probable": {"mlbam": (row or {}).get("away_sp")}},
        })
    return games, stats


def _sides(bets: list[dict]):
    """Every priced side on a board, flattened, with its market named."""
    for b in bets or []:
        for market, rows in (("moneyline", b.get("moneyline") or []),
                             ("runline", b.get("runline") or []),
                             ("total", (b.get("total") or {}).get("sides") or [])):
            for r in rows or []:
                yield market, b, r


def census_cell(snap: dict, events: list[dict], slate: str, *, floor: float,
                finals: dict) -> dict:
    """One (snapshot, slate) cell: how many sides were priced and how many cleared.

    `now` is the snapshot's own capture time, which is what makes this a replay
    rather than a re-run: `team_bets` drops events already under way, and judging
    that against the wall clock today would drop every event in the cache."""
    captured = _stamp(snap.get("captured_at"))
    on_slate = [e for e in events if be._event_slate_date(e) == slate]
    pregame = [e for e in on_slate
               if (_stamp(e.get("commence_time")) or captured) > captured]
    games, gstats = _games_for(pregame, slate, finals)

    inp = bm.inputs_as_of(slate)
    parks = inp.get("parks")
    if not parks:
        parks = {}
    stats: dict = {}
    bets = be.team_bets(games, pregame, teams=inp["teams"], parks=parks,
                        starters=inp["starters"], now=captured, stats=stats) if games else []

    n_priced = 0
    by_market = Counter()
    clearing_by_market = Counter()
    edges: list[float] = []
    clearing: list[dict] = []
    for market, b, r in _sides(bets):
        if r.get("edge") is None or r.get("odds") is None or not r.get("book"):
            continue
        n_priced += 1
        by_market[market] += 1
        edges.append(float(r["edge"]))
        if float(r["edge"]) >= floor:
            clearing_by_market[market] += 1
            clearing.append({"market": market, "game_pk": b.get("game_pk"),
                             "side": r.get("side"), "label": r.get("label"),
                             "odds": r.get("odds"), "edge": round(float(r["edge"]), 5),
                             "ev_per_unit": r.get("ev_per_unit")})

    # The two published slots, decided by the SAME function the page calls, so
    # the per-tag arrival rate below is the rule and not a re-implementation.
    evald = be._load("betting_model_eval.json") or {}
    slots, _reason, meta = be.provisional_picks(
        bets, odds_priceable=bool(pregame), evald=evald)
    n_potd = 1 if slots.get("pick_of_the_day") else 0
    n_longshot = 1 if slots.get("longshot_of_the_day") else 0

    edges.sort()
    def _q(p):
        if not edges:
            return None
        i = min(len(edges) - 1, max(0, int(round(p * (len(edges) - 1)))))
        return round(edges[i], 5)

    # COVERAGE IS THE FIELD THAT STOPS THIS BEING MEASURED WRONG. A capture
    # taken at 01:33 UTC is late evening US local, so most of that slate has
    # already started and the board it prices is one game, not fifteen. Averaging
    # a 1-event cell beside a 15-event cell answers "how many sides did the
    # cache happen to hold", which is a fact about this box's cron, not about
    # the board. Every count below is therefore ALSO reported per pregame event,
    # which is coverage invariant and is the only number worth extrapolating.
    n_pre = len(pregame)
    coverage = (round(n_pre / len(on_slate), 4) if on_slate else None)

    return {
        "snapshot": snap.get("_name"),
        "captured_at": snap.get("captured_at"),
        "slate_date": slate,
        "floor": floor,
        "n_events_on_slate": len(on_slate),
        "n_events_pregame": n_pre,
        "coverage": coverage,
        "is_full_slate": bool(coverage is not None and coverage >= FULL_SLATE_COVERAGE),
        "n_games_priced": len(bets),
        "n_priced_sides": n_priced,
        "n_clearing": len(clearing),
        "clear_rate": (round(len(clearing) / n_priced, 4) if n_priced else None),
        "priced_per_pregame_event": (round(n_priced / n_pre, 4) if n_pre else None),
        "clearing_per_pregame_event": (round(len(clearing) / n_pre, 4) if n_pre else None),
        "by_market": dict(sorted(by_market.items())),
        "clearing_by_market": dict(sorted(clearing_by_market.items())),
        "edge_quantiles": {"p50": _q(0.50), "p90": _q(0.90), "p95": _q(0.95),
                           "max": (round(edges[-1], 5) if edges else None)},
        "inputs_source": inp.get("source"),
        "inputs_vintage_date": inp.get("vintage_date"),
        "inputs_contaminated": bool(inp.get("contaminated")),
        "parks_resolved": bool(inp.get("parks_resolved")),
        "n_events_dropped_in_progress": stats.get("n_events_dropped_in_progress"),
        "n_games_no_final_row": gstats["n_no_final"],
        "n_games_missing_probables": gstats["n_no_probables"],
        # THE THREE LEDGERS' ARRIVAL RATES, per slate day, on this cell.
        "arrival": {
            "published": n_potd + n_longshot,
            "potd_band": n_potd,
            "longshot": n_longshot,
            # The EV-ranked remainder inside MAX_PER_SLATE, which is the budget
            # the shipped ledger runs on.
            "ev_rank": max(0, min(len(clearing), _max_per_slate()) - (n_potd + n_longshot)),
            # Uncapped: every side that cleared. This is the "board_all" tag.
            "board_all": len(clearing),
            # The calibration ledger is not a bet ledger and has no floor: it
            # scores every priced side.
            "calibration": n_priced,
        },
        "pick_basis": meta.get("basis"),
        "clearing": clearing,
    }


def _max_per_slate() -> int:
    try:
        import betting_shadow
        return int(betting_shadow.MAX_PER_SLATE)
    except Exception:                                          # noqa: BLE001
        return 5


def run(*, floor: float | None = None) -> dict:
    floor = DEFAULT_FLOOR if floor is None else float(floor)
    finals = _completed_index()
    cells = []
    for p in sorted(ODDS_DIR.glob("*.json")):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        snap["_name"] = p.name
        events = bi.parse_events(snap)
        slates = sorted({s for s in (be._event_slate_date(e) for e in events) if s})
        for slate in slates:
            cells.append(census_cell(snap, events, slate, floor=floor, finals=finals))

    # PER SLATE DATE: the cell a nightly would actually have used, which is the
    # newest snapshot still carrying pregame events on that slate. A cell with
    # zero pregame events is a capture taken after first pitch and is kept in
    # `cells` (it is the honest record of what the cache holds) and excluded
    # here, because a board was never built from it.
    per_slate: dict[str, dict] = {}
    for c in sorted(cells, key=lambda c: (c["slate_date"], c["captured_at"] or "")):
        if c["n_events_pregame"] <= 0:
            continue
        per_slate[c["slate_date"]] = c

    # THE SECOND VIEW, and the one the volume design should be read off. Per
    # slate date, the cell with the MOST pregame events: the most complete board
    # that any capture on that date could have priced. The `per_slate` rule
    # above answers "what would the nightly that actually ran have seen", which
    # on this box includes two captures taken after most first pitches, and
    # averaging those in biases every arrival rate DOWN.
    best_slate: dict[str, dict] = {}
    for c in cells:
        cur = best_slate.get(c["slate_date"])
        if cur is None or c["n_events_pregame"] > cur["n_events_pregame"]:
            best_slate[c["slate_date"]] = c
    best = [c for c in best_slate.values() if c["n_events_pregame"] > 0]
    full = [c for c in cells if c["is_full_slate"] and c["n_events_pregame"] > 0]

    usable = list(per_slate.values())
    n = len(usable)
    def _mean(key, sub=None, over=None):
        src = usable if over is None else over
        vals = [(c["arrival"][sub] if sub else c[key]) for c in src]
        vals = [v for v in vals if v is not None]
        return (round(sum(vals) / len(vals), 3) if vals else None)

    def _rate_block(src, label):
        per_ev = [c["clearing_per_pregame_event"] for c in src
                  if c["clearing_per_pregame_event"] is not None]
        priced_ev = [c["priced_per_pregame_event"] for c in src
                     if c["priced_per_pregame_event"] is not None]
        mean_clear = (round(sum(per_ev) / len(per_ev), 4) if per_ev else None)
        mean_priced = (round(sum(priced_ev) / len(priced_ev), 4)
                       if priced_ev else None)
        return {
            "basis": label,
            "n_cells": len(src),
            "clearing_per_pregame_event": mean_clear,
            "clearing_per_pregame_event_range": ([round(min(per_ev), 4),
                                                  round(max(per_ev), 4)]
                                                 if per_ev else None),
            "priced_per_pregame_event": mean_priced,
            "projected_clearing_on_a_15_game_slate": (
                round(mean_clear * TYPICAL_SLATE_GAMES, 2) if mean_clear else None),
            "projected_priced_on_a_15_game_slate": (
                round(mean_priced * TYPICAL_SLATE_GAMES, 2) if mean_priced else None),
            "projection_note": (f"a measured per-event rate multiplied by "
                                f"{TYPICAL_SLATE_GAMES}. It is a projection and is "
                                "labelled one; nothing here observed a full "
                                f"{TYPICAL_SLATE_GAMES}-game slate end to end."),
        }

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "floor": floor,
        "floor_source": "betting_export.PROVISIONAL_MIN_EDGE",
        "n_snapshots_in_cache": len(list(ODDS_DIR.glob("*.json"))),
        "n_cells": len(cells),
        "n_slate_days_usable": n,
        "slate_days": sorted(per_slate),
        "mean_per_slate_day": {
            "priced_sides": _mean("n_priced_sides"),
            "clearing": _mean("n_clearing"),
            "published": _mean(None, "published"),
            "ev_rank": _mean(None, "ev_rank"),
            "board_all": _mean(None, "board_all"),
            "calibration": _mean(None, "calibration"),
        },
        "range_per_slate_day": {
            "clearing": ([min(c["n_clearing"] for c in usable),
                          max(c["n_clearing"] for c in usable)] if usable else None),
            "priced_sides": ([min(c["n_priced_sides"] for c in usable),
                              max(c["n_priced_sides"] for c in usable)] if usable else None),
        },
        # The same counts over the MOST COMPLETE capture on each slate date,
        # which is the board a nightly firing before first pitch would price.
        "n_full_slate_cells": len(full),
        "mean_per_best_capture": {
            "priced_sides": _mean("n_priced_sides", over=best),
            "clearing": _mean("n_clearing", over=best),
            "board_all": _mean(None, "board_all", over=best),
            "calibration": _mean(None, "calibration", over=best),
        },
        "range_per_best_capture": {
            "clearing": ([min(c["n_clearing"] for c in best),
                          max(c["n_clearing"] for c in best)] if best else None),
        },
        # COVERAGE INVARIANT, and the only rate worth extrapolating.
        "per_event_rates": {
            "all_cells": _rate_block([c for c in cells if c["n_events_pregame"] > 0],
                                     "every cell with any pregame coverage"),
            "full_slate_cells": _rate_block(full,
                                            f"cells with >= {FULL_SLATE_COVERAGE:.0%} "
                                            "of the slate still pregame"),
        },
        "caveat": (
            f"{n} slate day(s) of cached snapshots, {len(full)} of {len(cells)} "
            "cells covering a full slate. This is a development box's capture "
            "cadence, not a season. Read the per-event rate, not the per-slate "
            "mean: two captures here were taken after most first pitches and "
            "they drag every per-slate average down."),
        "per_slate_day": per_slate,
        "best_capture_per_slate_day": best_slate,
        "cells": cells,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--floor", type=float, default=None,
                    help=f"edge floor (default {DEFAULT_FLOOR}, the shared page floor)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="also write the full result to this path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    out = run(floor=args.floor)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    if args.quiet:
        return 0

    print(f"FLOOR CENSUS at {out['floor']:.1%} "
          f"({out['n_snapshots_in_cache']} cached snapshots, "
          f"{out['n_cells']} (snapshot, slate) cells, "
          f"{out['n_slate_days_usable']} usable slate day(s))")
    print()
    hdr = (f"{'slate':<12}{'snapshot':<22}{'evt':>4}{'pre':>4}{'cov':>6}"
           f"{'priced':>8}{'clear':>7}{'rate':>7}{'ml':>4}{'rl':>4}{'tot':>5}"
           f"{'pub':>5}{'evrk':>6}{'clr/ev':>8}{'full':>6}")
    print(hdr)
    print("-" * len(hdr))
    for c in out["cells"]:
        cb = c["clearing_by_market"]
        rate = f"{c['clear_rate']:.3f}" if c["clear_rate"] is not None else "-"
        cov = f"{c['coverage']:.2f}" if c["coverage"] is not None else "-"
        cpe = (f"{c['clearing_per_pregame_event']:.2f}"
               if c["clearing_per_pregame_event"] is not None else "-")
        print(f"{c['slate_date']:<12}{(c['snapshot'] or ''):<22}"
              f"{c['n_events_on_slate']:>4}{c['n_events_pregame']:>4}{cov:>6}"
              f"{c['n_priced_sides']:>8}{c['n_clearing']:>7}{rate:>7}"
              f"{cb.get('moneyline', 0):>4}{cb.get('runline', 0):>4}{cb.get('total', 0):>5}"
              f"{c['arrival']['published']:>5}{c['arrival']['ev_rank']:>6}"
              f"{cpe:>8}{('yes' if c['is_full_slate'] else 'no'):>6}")
    print()
    m = out["mean_per_slate_day"]
    print("PER SLATE DAY (the cell a nightly would actually have priced):")
    print(f"  priced sides   mean {m['priced_sides']}   range {out['range_per_slate_day']['priced_sides']}")
    print(f"  clearing       mean {m['clearing']}   range {out['range_per_slate_day']['clearing']}")
    print(f"  published      mean {m['published']}  (<= 2 by rule)")
    print(f"  ev_rank        mean {m['ev_rank']}")
    print(f"  board_all      mean {m['board_all']}  (uncapped)")
    print(f"  calibration    mean {m['calibration']}  (every priced side, no floor)")
    print()
    b = out["mean_per_best_capture"]
    print("PER BEST CAPTURE ON EACH SLATE DAY (the most complete board available):")
    print(f"  priced sides   mean {b['priced_sides']}")
    print(f"  clearing       mean {b['clearing']}   range {out['range_per_best_capture']['clearing']}")
    print(f"  calibration    mean {b['calibration']}")
    print()
    print("PER PREGAME EVENT (coverage invariant; the only rate worth projecting):")
    for key in ("all_cells", "full_slate_cells"):
        r = out["per_event_rates"][key]
        print(f"  {key:<18} n={r['n_cells']:<3} clearing/event "
              f"{r['clearing_per_pregame_event']} "
              f"range {r['clearing_per_pregame_event_range']}, "
              f"priced/event {r['priced_per_pregame_event']}")
        print(f"  {'':<18} -> projected on a {TYPICAL_SLATE_GAMES}-game slate: "
              f"{r['projected_clearing_on_a_15_game_slate']} clearing, "
              f"{r['projected_priced_on_a_15_game_slate']} priced")
    print()
    print("  " + out["caveat"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
