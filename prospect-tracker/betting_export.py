# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_export.py - data/betting.json for the /betting/ module.

Joins three things that already exist:
    * the day's slate + announced probables (data/fantasy.json's schedule
      block, written by fantasy_schedule; no second StatsAPI call),
    * the model (betting_model: team Offense+/Bullpen+/rotation SEM+, park
      index, home field, Poisson-difference margin),
    * the odds snapshot (betting_ingest, when a key is configured).

and writes:
    data/betting.json          the module payload
    data/betting_preview.json  the public-preview slice (the gating seam:
                               when DIAMOND_GATING ever flips on, the free
                               tier reads this and members read the full file
                               from a Supabase-served path)
    data/betting_record.json   the APPEND-ONLY public pick record

THE APPEND-ONLY RECORD IS THE WHOLE PRODUCT. A tout's record is worthless
because nobody can prove it was not edited after the fact. Ours is enforced in
code: `write_record` refuses to publish an array whose leading rows differ, in
any byte, from what is already on disk. Deleting a loser, nudging a price,
re-dating a post: all three raise RecordImmutabilityError, and test_betting.py
pins that. Rows carry odds at post, the book, a flat 1-unit stake, and CLV
against the closing snapshot once one exists.

NO PICK SHIPS TODAY. `pick_of_the_day` is null and `model.validated` is false
because the backtest is contaminated (betting_model.backtest explains how).
The threshold that would gate a pick is `min_edge`, and it is null until a
clean forward test measures one. Inventing a "3% edge" threshold would be the
single most dishonest number on the site.

CLI:
    python betting_export.py            # build the payload (offline-safe)
    python betting_export.py --summary  # print what it wrote
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import betting_ingest as bi
import betting_model as bm

log = logging.getLogger("betting_export")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "betting.json"
PREVIEW_PATH = DATA_DIR / "betting_preview.json"
RECORD_PATH = DATA_DIR / "betting_record.json"

STAKE_UNITS = 1.0                 # flat, always, on the public record
PREVIEW_GAMES = 3                 # games the free slice carries

# Expected plate appearances by projected lineup slot. League average is about
# 37.8 PA per team per game; leadoff sees roughly 4.65 and the nine hole about
# 3.85, near enough to a 0.1 step. Used ONLY for prop fair lines, and the
# payload says so, because a real lineup card beats this every time.
SLOT_PA = {s: round(4.65 - 0.10 * (s - 1), 2) for s in range(1, 10)}
DEFAULT_PA = 4.20

# The legal block. ONE definition, rendered by the client on every section, so
# a copy edit can never land on five surfaces and miss the sixth.
DISCLAIMER = {
    "age": "21+ only.",
    "purpose": "Informational and entertainment purposes only. Nothing here is betting advice.",
    "legality": "Sports betting is not legal in all states. Know the rules where you are.",
    "help": "If gambling stops being fun, call 1-800-GAMBLER.",
    "helpline": "1-800-GAMBLER",
    "affiliates": "eephus.io takes no affiliate money from any sportsbook and links to none.",
    "staking": "Every pick on the public record is a flat 1 unit. Kelly is shown as information, never as a stake.",
}

# Correlation rules the parlay builder enforces. A naive parlay multiplies leg
# probabilities, which is only valid for INDEPENDENT legs. Same-game legs are
# not independent, and the direction of the error is always the same: the naive
# number overstates a positively-correlated parlay's price and understates its
# probability, which is exactly why books sell same-game parlays.
CORRELATION_RULES = [
    {"id": "same_game_any", "severity": "warn",
     "when": "two or more legs from the same game",
     "why": "Same-game outcomes share the run environment, the starters and the weather. "
            "Multiplying the legs is not arithmetic, it is an assumption, and it is wrong."},
    {"id": "ml_runline_same_team", "severity": "block",
     "when": "moneyline and runline on the same team",
     "why": "The runline is a subset of the moneyline. These are one bet with two prices, "
            "not two bets, and the product is meaningless."},
    {"id": "ml_and_total", "severity": "warn",
     "when": "a moneyline and the total in the same game",
     "why": "Favourite plus under and dog plus over are both positively correlated. "
            "The naive product is too cheap."},
    {"id": "same_team_props", "severity": "warn",
     "when": "two player props from the same lineup",
     "why": "Teammates share innings and baserunners. Hits and total bases on the same "
            "night rise and fall together."},
    {"id": "sp_k_and_team_ml", "severity": "warn",
     "when": "a starter strikeout prop with that team's moneyline",
     "why": "A dominant start moves both. Correlated legs price differently than the "
            "product suggests."},
]


# ---------------------------------------------------------------------------
# io helpers
# ---------------------------------------------------------------------------
def _load(name: str):
    p = DATA_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("betting_export: unreadable %s", name)
        return None


def _write(path: Path, payload) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ===========================================================================
# THE APPEND-ONLY RECORD
# ===========================================================================
class RecordImmutabilityError(RuntimeError):
    """Raised when a write would change or drop a row that is already
    published. This is not a warning and it is not recoverable by retrying:
    the caller built an array that rewrites history."""


def load_record(path: Path | None = None) -> list[dict]:
    """The published record as a list.

    A MISSING file is an empty record, which is correct: there is nothing to
    protect yet. A file that exists but will not parse RAISES, because
    returning [] there would hand the caller a blank baseline and let the next
    write overwrite a record it could not read. Corruption must stop the
    pipeline, not silently reset the ledger."""
    p = Path(path or RECORD_PATH)
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordImmutabilityError(
            f"{p.name} exists but will not parse ({exc}); refusing to treat an unreadable "
            "record as an empty one") from exc
    if not isinstance(rows, list):
        raise RecordImmutabilityError(f"{p.name} is not a JSON array")
    return rows


def _canon(row) -> str:
    """Byte-stable form of one row, so comparison catches a re-ordered dict as
    equal and a changed value as different."""
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


def check_append_only(existing: list[dict], proposed: list[dict]) -> None:
    """Raise unless `proposed` is `existing` plus zero or more NEW rows.

    Three ways to fail, all of them things a dishonest record does:
      * the proposal is shorter (a row was deleted),
      * a leading row differs (a price, a result or a date was edited),
      * a bet_id that was already published reappears on a different row.
    """
    if len(proposed) < len(existing):
        raise RecordImmutabilityError(
            f"record would shrink from {len(existing)} to {len(proposed)} rows; "
            "the published record is append-only")
    for i, old in enumerate(existing):
        if _canon(old) != _canon(proposed[i]):
            raise RecordImmutabilityError(
                f"row {i} (bet_id={old.get('bet_id')!r}) would change; the published "
                "record is append-only. Append a correction row instead.")
    seen = {r.get("bet_id") for r in existing if r.get("bet_id")}
    for r in proposed[len(existing):]:
        bid = r.get("bet_id")
        if bid and bid in seen:
            raise RecordImmutabilityError(
                f"bet_id {bid!r} is already published; a new row may not reuse it")
        seen.add(bid)


def write_record(rows: list[dict], *, path: Path | None = None) -> list[dict]:
    """Publish the record after proving the write is append-only."""
    path = path or RECORD_PATH
    existing = load_record(path)
    check_append_only(existing, list(rows))
    _write(path, list(rows))
    return list(rows)


def append_record(new_rows: list[dict], *, path: Path | None = None) -> list[dict]:
    """The only sanctioned way to add to the record."""
    path = path or RECORD_PATH
    existing = load_record(path)
    return write_record(existing + list(new_rows or []), path=path)


def bet_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def grade_clv(odds_post, odds_close) -> dict:
    """Closing line value for one pick.

    TWO numbers, because they answer different questions:
      * clv_pct  price CLV: decimal_at_post / decimal_at_close - 1. What the
        posted price was worth relative to the close, in return terms.
      * clv_prob probability CLV: the raw implied probability at close minus at
        post. Positive means the market moved toward the pick.
    `beat_close` is the plain yes/no a reader actually wants."""
    dp = bi.american_to_decimal(odds_post)
    dc = bi.american_to_decimal(odds_close)
    if not dp or not dc:
        return {"beat_close": None, "clv_pct": None, "clv_prob": None}
    return {
        "beat_close": bool(dp > dc),
        "clv_pct": round((dp / dc - 1.0) * 100.0, 3),
        "clv_prob": round((1.0 / dc) - (1.0 / dp), 5),
    }


def record_summary(rows: list[dict] | None = None) -> dict:
    """W-L, net units, ROI, beat-close rate and average CLV. Every field is
    None or zero until the record actually has rows: an empty record reports
    an empty record, it does not report a 0% ROI as if 0 bets were graded."""
    rows = rows if rows is not None else load_record()
    settled = [r for r in rows if r.get("result") in ("won", "lost", "push", "void")]
    wins = sum(1 for r in settled if r.get("result") == "won")
    losses = sum(1 for r in settled if r.get("result") == "lost")
    pushes = sum(1 for r in settled if r.get("result") in ("push", "void"))
    units = 0.0
    staked = 0.0
    for r in settled:
        stake = float(r.get("stake_units") or STAKE_UNITS)
        dec = bi.american_to_decimal(r.get("odds_at_post")) or 1.0
        if r.get("result") == "won":
            units += stake * (dec - 1.0)
            staked += stake
        elif r.get("result") == "lost":
            units -= stake
            staked += stake
    graded = [r for r in rows if r.get("beat_close") is not None]
    clvs = [r.get("clv_pct") for r in rows if isinstance(r.get("clv_pct"), (int, float))]
    return {
        "n_rows": len(rows),
        "n_settled": len(settled),
        "n_open": len(rows) - len(settled),
        "won": wins, "lost": losses, "push": pushes,
        "net_units": round(units, 3) if settled else 0.0,
        "roi_pct": round(100.0 * units / staked, 2) if staked else None,
        "n_clv_graded": len(graded),
        "beat_close_rate": (round(sum(1 for r in graded if r.get("beat_close")) / len(graded), 4)
                            if graded else None),
        "avg_clv_pct": round(sum(clvs) / len(clvs), 3) if clvs else None,
        "stake_policy": "flat 1 unit",
    }


# ===========================================================================
# slate + market join
# ===========================================================================
def slate_games(on_date: str | None = None) -> list[dict]:
    """Today's games from data/fantasy.json's schedule block. That block is
    already refreshed by run_monthly step 9d, so /betting/ costs the pipeline
    zero extra StatsAPI calls."""
    fan = _load("fantasy.json") or {}
    games = ((fan.get("schedule") or {}).get("games")) or []
    if not games:
        return []
    day = on_date or min(g.get("date") or "" for g in games if g.get("date"))
    return [g for g in games if g.get("date") == day]


def _market_view(event: dict | None, market: str, sides: tuple) -> dict | None:
    """Best price per side + the de-vigged fair probabilities for one market.

    De-vigging uses the SINGLE book that posted the best price on the first
    side, not a cross-book mash-up: mixing books manufactures a fake fair line
    with a negative hold. `best_of` records where each price came from."""
    if not event:
        return None
    best = {s: bi.best_price(event, market, s) for s in sides}
    if any(b is None for b in best.values()):
        return None
    # Fair probabilities come from ONE book's two-sided market (the first book
    # that posted both sides), so the de-vig is arithmetically meaningful.
    fair, fair_book, hold = None, None, None
    for bkey, b in (event.get("books") or {}).items():
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        decs = {}
        for s in sides:
            cell = m.get(s)
            price = cell.get("price") if isinstance(cell, dict) else cell
            d = bi.american_to_decimal(price)
            if d:
                decs[s] = d
        if len(decs) == len(sides):
            fair, fair_book, hold = bm.devig(decs), bkey, bm.hold_pct(decs)
            break
    if not fair:
        return None
    return {
        "best": {s: best[s] for s in sides},
        "fair": {s: round(fair[s], 5) for s in sides},
        "fair_book": fair_book,
        "hold_pct": round(hold, 3) if hold is not None else None,
        "devig_method": "proportional",
    }


def _priced_side(side_key: str, label: str, p_model: float, mv: dict | None) -> dict:
    """One bettable side: model probability, market fair probability, edge, EV,
    Kelly. With no market attached, everything market-shaped is None and the
    row is a fair line, which is still worth showing."""
    row = {
        "side": side_key, "label": label,
        "model_prob": round(p_model, 5),
        "fair_odds": bi.decimal_to_american(1.0 / p_model) if p_model > 0 else None,
        "book": None, "odds": None, "decimal": None,
        "implied_prob": None, "market_fair_prob": None,
        "edge": None, "ev_per_unit": None, "kelly_full": None,
    }
    if not mv:
        return row
    b = (mv.get("best") or {}).get(side_key)
    if not b:
        return row
    fair = (mv.get("fair") or {}).get(side_key)
    row.update({
        "book": b.get("book"), "book_title": b.get("book_title"),
        "odds": b.get("price"), "decimal": b.get("decimal"),
        "point": b.get("point"),
        "implied_prob": round(1.0 / b["decimal"], 5) if b.get("decimal") else None,
        "market_fair_prob": fair,
    })
    if fair is not None and b.get("decimal"):
        row["edge"] = round(bm.edge(p_model, fair), 5)
        row["ev_per_unit"] = round(bm.ev_per_unit(p_model, b["decimal"]), 5)
        row["kelly_full"] = round(bm.kelly_fraction(p_model, b["decimal"]), 5)
    return row


def team_bets(games: list[dict], events: list[dict], *, teams=None, parks=None,
              starters=None) -> list[dict]:
    """Every game on the slate: model probabilities, the market when a snapshot
    exists, and the edge between them."""
    teams = teams if teams is not None else bm.team_inputs()
    parks = parks if parks is not None else bm.park_index()
    starters = starters if starters is not None else bm.starter_inputs()
    by_pair = {}
    for ev in events or []:
        by_pair[(ev.get("home_org"), ev.get("away_org"))] = ev

    out = []
    for g in games:
        home, away = (g.get("home") or {}), (g.get("away") or {})
        ho, ao = home.get("org"), away.get("org")
        hp = (home.get("probable") or {}).get("mlbam")
        ap = (away.get("probable") or {}).get("mlbam")
        gp = bm.game_probabilities(ho, ao, home_sp=starters.get(hp), away_sp=starters.get(ap),
                                   teams=teams, parks=parks)
        if not gp:
            log.info("betting_export: no model row for %s @ %s", ao, ho)
            continue
        over_fn = gp.pop("over", None)
        ev = by_pair.get((ho, ao))
        ml = _market_view(ev, "h2h", ("home", "away"))
        rl = _market_view(ev, "spreads", ("home", "away"))
        tot = _market_view(ev, "totals", ("over", "under"))

        # Runline sides are read off the posted point: whichever side carries
        # -1.5 must win by two. Never assume the favourite is the home team.
        rl_rows = None
        if rl:
            hp_point = ((rl["best"].get("home") or {}).get("point"))
            home_is_fav = (hp_point is not None and hp_point < 0)
            p_home_rl = gp["p_home_minus_1_5"] if home_is_fav else gp["p_home_plus_1_5"]
            p_away_rl = gp["p_away_plus_1_5"] if home_is_fav else gp["p_away_minus_1_5"]
            rl_rows = [
                _priced_side("home", f"{ho} {hp_point:+.1f}" if hp_point is not None else ho,
                             p_home_rl, rl),
                _priced_side("away", f"{ao} {-hp_point:+.1f}" if hp_point is not None else ao,
                             p_away_rl, rl),
            ]
        tot_rows, tot_line = None, None
        if tot and over_fn:
            tot_line = ((tot["best"].get("over") or {}).get("point"))
            if tot_line is not None:
                p_over = over_fn(float(tot_line))
                tot_rows = [
                    _priced_side("over", f"Over {tot_line}", p_over, tot),
                    _priced_side("under", f"Under {tot_line}", 1.0 - p_over, tot),
                ]
        out.append({
            "game_pk": g.get("game_pk"),
            "date": g.get("date"),
            "start": g.get("datetime"),
            "venue": (g.get("venue") or {}).get("name"),
            "home": {"org": ho, "team": home.get("team"),
                     "probable": home.get("probable"),
                     "offense_plus": (teams.get(ho) or {}).get("offense_plus"),
                     "bullpen_plus": (teams.get(ho) or {}).get("bullpen_plus")},
            "away": {"org": ao, "team": away.get("team"),
                     "probable": away.get("probable"),
                     "offense_plus": (teams.get(ao) or {}).get("offense_plus"),
                     "bullpen_plus": (teams.get(ao) or {}).get("bullpen_plus")},
            "model": {
                "p_home": gp["p_home"], "p_away": gp["p_away"],
                "lam_home": gp["lam_home"], "lam_away": gp["lam_away"],
                "fair_total": gp["fair_total"],
                "park_index": gp["components"]["park_index"],
                "home_prevention": gp["components"]["home"]["prevention"],
                "away_prevention": gp["components"]["away"]["prevention"],
            },
            "moneyline": ([_priced_side("home", ho, gp["p_home"], ml),
                           _priced_side("away", ao, gp["p_away"], ml)]),
            "runline": rl_rows,
            "total": ({"line": tot_line, "sides": tot_rows} if tot_rows else
                      {"line": None, "sides": None, "fair_total": gp["fair_total"]}),
            "market": {"moneyline_hold_pct": (ml or {}).get("hold_pct"),
                       "total_hold_pct": (tot or {}).get("hold_pct"),
                       "devig_method": "proportional"} if ml or tot else None,
        })
    return out


# ===========================================================================
# props: MODEL FAIR LINES ONLY (free tier has no per-event prop budget)
# ===========================================================================
def _fantasy_index() -> dict:
    fan = _load("fantasy.json") or {}
    by = {}
    for p in fan.get("players") or []:
        by[(p.get("mlbam"), p.get("side"))] = p
    return by


def _poisson_over(lam: float, line: float) -> float:
    """P(count > line) for a half-point line."""
    need = int(line) + 1
    pmf = bm._poisson_pmf(lam, max(30, need + 20))
    return sum(pmf[need:])


def props_fair_lines(games: list[dict], *, starters=None) -> dict:
    """Model fair lines for the core props, with NO book comparison.

    The Odds API free tier prices props through a per-EVENT endpoint that bills
    per event, so a full slate of prop markets costs more credits in two weeks
    than the plan holds in a month. Rather than show a half-slate of stale
    comparisons, the module publishes its own fair number and labels it
    model-only. When a paid tier lands, the book side drops in beside these
    rows without touching the math."""
    starters = starters if starters is not None else bm.starter_inputs()
    fx = _fantasy_index()
    hit_lb = _load("hitter_leaderboards.json") or {}
    orders = {}
    for t in hit_lb.get("teams") or []:
        o = bm._org(t.get("team"))
        if o:
            orders[o] = (t.get("orders") or {}).get("vr") or []

    pitchers, hitters = [], []
    for g in games:
        for side, opp in (("home", "away"), ("away", "home")):
            s = g.get(side) or {}
            org = s.get("org")
            pp = s.get("probable") or {}
            mid = pp.get("mlbam")
            rec = fx.get((mid, "pit")) if mid else None
            ros = (rec or {}).get("ros") or {}
            ip = float(ros.get("ip") or 0.0)
            if mid and ip > 0:
                gs = float(ros.get("gs") or 0.0)
                exp_ip = ((starters.get(mid) or {}).get("ip_per_gs")
                          or (ip / gs if gs > 0 else 5.2))
                exp_ip = max(2.0, min(7.5, float(exp_ip)))
                lam_k = (float(ros.get("k") or 0.0) / ip) * exp_ip
                lam_er = (float(ros.get("er") or 0.0) / ip) * exp_ip
                lam_h = (float(ros.get("h") or 0.0) / ip) * exp_ip
                pitchers.append({
                    "mlbam": mid, "name": pp.get("name") or (rec or {}).get("name"),
                    "org": org, "opp": (g.get(opp) or {}).get("org"),
                    "game_pk": g.get("game_pk"),
                    "expected_ip": round(exp_ip, 2),
                    "props": [
                        _prop_row("Strikeouts", lam_k),
                        _prop_row("Earned runs", lam_er),
                        _prop_row("Hits allowed", lam_h),
                        {"prop": "Outs recorded", "fair_line": round(exp_ip * 3.0, 1),
                         "lam": round(exp_ip * 3.0, 2), "over_line": None, "p_over": None,
                         "note": "fair number only; outs props are priced off the same expected length"},
                    ],
                })
        # Hitters: the projected order against a right-hander, because no
        # lineup card exists this far out. Both the assumption and the PA
        # table are published so the number can be argued with.
        for side in ("home", "away"):
            org = (g.get(side) or {}).get("org")
            for slot_row in (orders.get(org) or [])[:5]:
                key = slot_row.get("key")
                try:
                    mid = int(key)
                except (TypeError, ValueError):
                    continue
                rec = fx.get((mid, "hit"))
                ros = (rec or {}).get("ros") or {}
                pa = float(ros.get("pa") or 0.0)
                if pa <= 0:
                    continue
                exp_pa = SLOT_PA.get(int(slot_row.get("slot") or 0), DEFAULT_PA)
                p_hit = float(ros.get("h") or 0.0) / pa
                p_hr = float(ros.get("hr") or 0.0) / pa
                tb = (float(ros.get("single") or 0.0) + 2 * float(ros.get("double") or 0.0)
                      + 3 * float(ros.get("triple") or 0.0) + 4 * float(ros.get("hr") or 0.0))
                hitters.append({
                    "mlbam": mid, "name": slot_row.get("name"), "org": org,
                    "game_pk": g.get("game_pk"), "slot": slot_row.get("slot"),
                    "expected_pa": exp_pa,
                    "props": [
                        {"prop": "Total bases", "fair_line": round(tb / pa * exp_pa, 2),
                         "lam": round(tb / pa * exp_pa, 2), "over_line": 1.5,
                         "p_over": round(_poisson_over(tb / pa * exp_pa, 1.5), 4)},
                        {"prop": "1+ hits", "fair_line": round(p_hit * exp_pa, 2),
                         "lam": round(p_hit * exp_pa, 2), "over_line": 0.5,
                         "p_over": round(1.0 - (1.0 - p_hit) ** exp_pa, 4)},
                        {"prop": "1+ home runs", "fair_line": round(p_hr * exp_pa, 3),
                         "lam": round(p_hr * exp_pa, 3), "over_line": 0.5,
                         "p_over": round(1.0 - (1.0 - p_hr) ** exp_pa, 4)},
                    ],
                })
    return {
        "model_only": True,
        "no_book_comparison_reason": ("The Odds API free tier bills player props per event; "
                                      "a full slate would burn the monthly budget in about "
                                      "two weeks. These are our fair numbers, not a market read."),
        "method": {
            "pitchers": "rest-of-season rate per inning from the projection engine, times "
                        "the pitcher's measured innings per start",
            "hitters": "rest-of-season rate per plate appearance times expected PA for the "
                       "projected lineup slot",
            "slot_pa": SLOT_PA,
            "lineup_assumption": "projected order against a right-handed starter; a posted "
                                 "lineup card beats this every time",
            "distribution": "Poisson for counting props, which understates the tails of a "
                            "clumped scoring distribution",
        },
        "pitchers": pitchers,
        "hitters": hitters,
    }


def _prop_row(name: str, lam: float) -> dict:
    """A fair line plus the model probability over the nearest half point."""
    line = round(lam * 2) / 2.0
    if line == int(line):
        line += 0.5
    return {"prop": name, "fair_line": round(lam, 2), "lam": round(lam, 2),
            "over_line": line, "p_over": round(_poisson_over(lam, line), 4)}


# ===========================================================================
# parlays
# ===========================================================================
def parlay_context(bets: list[dict]) -> dict:
    """Legs the client calculator can chain, plus the rules that stop it from
    doing naive same-game math."""
    legs = []
    for b in bets:
        for row in (b.get("moneyline") or []):
            if row.get("model_prob") is None:
                continue
            legs.append({
                "leg_id": f"{b.get('game_pk')}:ml:{row['side']}",
                "game_pk": b.get("game_pk"),
                "label": f"{row.get('label')} moneyline",
                "market": "h2h",
                "model_prob": row["model_prob"],
                "odds": row.get("odds"), "book": row.get("book"),
            })
        tot = b.get("total") or {}
        for row in (tot.get("sides") or []):
            legs.append({
                "leg_id": f"{b.get('game_pk')}:tot:{row['side']}",
                "game_pk": b.get("game_pk"),
                "label": f"{b['away']['org']} at {b['home']['org']} {row.get('label')}",
                "market": "totals",
                "model_prob": row.get("model_prob"),
                "odds": row.get("odds"), "book": row.get("book"),
            })
    return {
        "rules": CORRELATION_RULES,
        "legs": legs,
        "featured_parlay": None,
        "featured_reason": ("A featured parlay needs a backtest that survives the "
                            "correlation haircut. There is not one, so there is no "
                            "featured parlay."),
        "math_note": ("Independent legs multiply. Same-game legs do not, and the naive "
                      "product is always too generous to the bettor's story and too cheap "
                      "for the book to sell at that price."),
    }


# ===========================================================================
# pick of the day
# ===========================================================================
def pick_of_the_day(bets: list[dict], *, min_edge: float | None,
                    odds_configured: bool) -> tuple[dict | None, str]:
    """The highest-EV qualifying edge, or None with the reason it is absent.

    Two hard gates, both of which are currently closed:
      * no odds feed means no market to have an edge against, and
      * no measured `min_edge` means no threshold, and a threshold invented to
        make a pick appear is the oldest trick in this industry.
    """
    if not odds_configured:
        return None, "no odds feed configured, so there is no market to price against"
    if min_edge is None:
        return None, ("the model is unvalidated: the backtest is contaminated by "
                      "season-to-date team inputs, so no minimum-edge threshold has been "
                      "measured and no pick is published")
    cands = []
    for b in bets:
        for market, rows in (("moneyline", b.get("moneyline") or []),
                             ("runline", b.get("runline") or []),
                             ("total", (b.get("total") or {}).get("sides") or [])):
            for row in rows:
                if row.get("edge") is None or row["edge"] < min_edge:
                    continue
                cands.append({**row, "market": market, "game_pk": b.get("game_pk"),
                              "matchup": f"{b['away']['org']} at {b['home']['org']}",
                              "start": b.get("start")})
    if not cands:
        return None, f"no side cleared the {min_edge:.1%} minimum edge on this slate"
    best = max(cands, key=lambda r: r.get("ev_per_unit") or -9)
    best["stake_units"] = STAKE_UNITS
    return best, "highest expected value among qualifying edges"


# ===========================================================================
# build
# ===========================================================================
def build(*, on_date: str | None = None, write: bool = True, log_fn=None) -> dict:
    """The whole payload. Offline-safe: absent odds, absent fantasy.json and
    absent leaderboards each degrade to a stated empty state rather than an
    exception."""
    status = bi.write_status()
    snap = bi.latest_snapshot()
    events = bi.parse_events(snap) if snap else []
    games = slate_games(on_date)
    teams, parks, starters = bm.team_inputs(), bm.park_index(), bm.starter_inputs()
    ctx = bm.league_context()
    coeffs = bm.coefficients()
    evald = _load("betting_model_eval.json") or {}

    bets = team_bets(games, events, teams=teams, parks=parks, starters=starters) if games else []
    min_edge = evald.get("min_edge")          # None until a clean test measures one
    pick, pick_reason = pick_of_the_day(bets, min_edge=min_edge,
                                        odds_configured=bool(status.get("configured") and events))
    record = load_record()

    empty_reasons = []
    if not teams:
        empty_reasons.append("team leaderboards have not been built yet")
    if not games:
        empty_reasons.append("no slate found in data/fantasy.json; the schedule refresh "
                             "has not run today")
    if not events:
        empty_reasons.append(status.get("note") or "no odds snapshot cached")

    payload = {
        "generated_at": _now(),
        "slate_date": (games[0].get("date") if games else (on_date or date.today().isoformat())),
        "n_games": len(bets),
        "status": {
            "odds_feed": ("ok" if events else ("not_configured" if not status.get("configured")
                                               else "no_snapshot")),
            "odds_note": status.get("note"),
            "odds_captured_at": (snap or {}).get("captured_at"),
            "odds_kind": (snap or {}).get("kind"),
            "model": "unvalidated",
            "empty_reasons": empty_reasons,
        },
        "model": {
            "version": bm.MODEL_VERSION,
            "validated": False,
            "stage": "Diamond preview",
            "inputs": ["team Offense+ (HEM+ rollup)", "team Bullpen+ (REM+ rollup)",
                       "starter SEM+ for the listed probable", "park runs index",
                       "home field"],
            "coefficients": coeffs,
            "league_context": ctx,
            "devig_method": "proportional",
            "margin_model": "Poisson difference (Skellam) by direct convolution",
            "known_limits": [
                "Poisson underdisperses real run scoring, so runline and total "
                "probabilities sit too close to the middle",
                "team inputs are season-to-date, not vintage-dated, so the backtest "
                "cannot be out of sample",
                "no weather, no umpire, no travel, no injury news beyond what the "
                "leaderboards already absorb",
            ],
            "backtest": {k: evald.get(k) for k in
                         ("generated_at", "n_games", "validated", "contaminated",
                          "contamination", "in_sample", "forward", "split_date", "note")
                         if k in evald} or None,
            "min_edge": min_edge,
        },
        "disclaimer": DISCLAIMER,
        "pick_of_the_day": pick,
        "pick_reason": pick_reason,
        "team_bets": bets,
        "props_fair_lines": props_fair_lines(games, starters=starters) if games else
                            {"model_only": True, "pitchers": [], "hitters": [],
                             "no_book_comparison_reason": "no slate loaded"},
        "parlay_context": parlay_context(bets),
        "record": record_summary(record),
        "record_url": "/data/betting_record.json",
        "record_policy": ("Append only. Rows are never edited or deleted; a correction is "
                          "a new row. betting_export.write_record refuses any other write "
                          "and test_betting.py pins it."),
    }

    preview = {
        "generated_at": payload["generated_at"],
        "slate_date": payload["slate_date"],
        "status": payload["status"],
        "model": {k: payload["model"][k] for k in ("version", "validated", "stage", "min_edge")},
        "disclaimer": DISCLAIMER,
        "pick_of_the_day": pick,
        "pick_reason": pick_reason,
        "n_games": payload["n_games"],
        "team_bets": bets[:PREVIEW_GAMES],
        "record": payload["record"],
        "gating_note": ("Preview slice. Everything is public during the Diamond preview; "
                        "this file is the seam a future gate would read."),
    }

    if write:
        _write(OUT_PATH, payload)
        _write(PREVIEW_PATH, preview)
        if not RECORD_PATH.exists():
            _write(RECORD_PATH, [])
        if log_fn:
            log_fn(f"betting_export: wrote {OUT_PATH.name} "
                   f"({len(bets)} games, odds={payload['status']['odds_feed']})")
    return payload


def refresh_live(log=None) -> dict:
    """Daily-tail entry point. Never raises into the pipeline."""
    try:
        return build(log_fn=log)
    except Exception:                                            # pragma: no cover
        logging.getLogger("betting_export").exception("betting_export: build failed")
        return {}


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build data/betting.json.")
    ap.add_argument("--date", default=None, help="slate date (default: first in the schedule)")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    p = build(on_date=args.date, log_fn=print)
    if args.summary:
        print(json.dumps({
            "slate_date": p["slate_date"], "n_games": p["n_games"],
            "status": p["status"], "pick": p["pick_of_the_day"],
            "pick_reason": p["pick_reason"], "record": p["record"],
            "n_prop_pitchers": len(p["props_fair_lines"]["pitchers"]),
            "n_prop_hitters": len(p["props_fair_lines"]["hitters"]),
            "n_parlay_legs": len(p["parlay_context"]["legs"]),
        }, indent=1))
