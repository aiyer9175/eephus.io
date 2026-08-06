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

AND THE PAYLOAD HAS TO SAY SO IN STRUCTURE, NOT JUST IN PROSE. betting_model
now grades in TWO labelled modes (contaminated and vintage) and puts `min_edge`
behind three named gates, and none of that reached the reader while this file
lifted nine keys out of the eval artifact and dropped the rest. `model.validation`
carries it through: which mode produced each graded block, how much vintage
history exists and how many games the honest mode could grade with it, and each
gate with its need, its have and its open/closed state. `pick_blockers` carries
EVERY reason there is no pick rather than the first one hit, because a reader
told only about the missing odds feed would reasonably assume the model itself
was ready.

CLI:
    python betting_export.py            # build the payload (offline-safe)
    python betting_export.py --summary  # print what it wrote
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
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

# Game states that are neither bettable nor allowed to anchor a closing window.
# fantasy_schedule stores StatsAPI's `abstractGameState` ("Preview" / "Live" /
# "Final" / "Other"); the detailed states are folded in because a postponement
# reports abstractGameState "Final" on some feeds and "Other" on others, and
# because a future producer may pass the detailed string straight through.
# Compared case-insensitively. See `is_bettable` for why the match is a DENY
# list and not an allow list.
NOT_BETTABLE_STATES = frozenset({
    "final", "game over", "completed early", "live", "in progress",
    "postponed", "cancelled", "canceled", "suspended", "forfeit", "other",
})

# The SUBSET of the above that means the game is BEING PLAYED right now rather
# than resolved or called off. A game in one of these states is still listed by
# the book, at an IN-GAME price; a Final or postponed game has left the board
# entirely. That difference is the whole of `anchors_close_window`, and it is
# load-bearing nowhere else.
IN_PROGRESS_STATES = frozenset({"live", "in progress", "suspended"})

# How far a parsed odds event's `commence_time` may sit from a schedule row's
# first pitch and still be that game. The two games of a doubleheader are about
# three and a half hours apart (game two starts roughly 30 minutes after game
# one ends) and a split doubleheader is about seven, so three hours is wide
# enough to absorb the routine disagreement between the book's posted start and
# StatsAPI's, and far too narrow to cross-match the halves of a doubleheader.
EVENT_MATCH_MAX_MINUTES = 180

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

# ---------------------------------------------------------------------------
# WHAT THE EVAL ARTIFACT IS ALLOWED TO PUT ON A PUBLIC PAGE
# ---------------------------------------------------------------------------
# Keys lifted verbatim out of data/betting_model_eval.json. Two things are
# deliberately NOT here:
#   * vintage_coverage["dir"], an absolute path on the build box. A filesystem
#     path is not a fact about the model and has no business being served.
#   * vintage_coverage["bytes"], which measures the store and not the evidence.
BACKTEST_KEYS = ("generated_at", "model_version", "n_games", "validated",
                 "contaminated", "contamination", "modes", "headline_mode",
                 "in_sample", "forward", "vintage", "split_date", "note")
COVERAGE_KEYS = ("schema", "n_vintages", "n_vintages_with_parks",
                 "n_vintages_neutral_park", "first", "last", "missing_dates",
                 "span_days", "latest_cutoff", "earliest_gradable_game_date", "note")
# Per-block fields the client needs to print a mode-labelled row. `n` and
# `n_graded` are both read because the vintage block reports its sample under
# `n_graded` and only grows an `n` on the day it actually grades something.
BLOCK_KEYS = ("label", "mode", "honest", "status", "n", "n_graded", "brier",
              "brier_flat_500", "brier_home_base", "accuracy", "note")

# The two modes in one sentence each, so the reader never has to infer what
# "contaminated" means from the word alone.
MODE_MEANING = {
    "contaminated": ("Team inputs are season-to-date leaderboards, so every graded game "
                     "sits inside its own features. This measures calibration, not skill, "
                     "and it cannot validate anything."),
    "vintage": ("Every game is priced on a leaderboard snapshot whose knowledge cutoff is "
                "strictly before that game: team offense, team run prevention, the listed "
                "probable and the park index all come out of that snapshot. A game with no "
                "such snapshot is skipped, not graded on today's numbers, and a game whose "
                "snapshot predates the stored park column is priced with the park term at "
                "neutral rather than on the live index. This is the only mode that can "
                "validate the model."),
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


CLV_PATH = DATA_DIR / "betting_clv.json"


def _close_price_for(row: dict, events: list[dict]):
    """The closing American price for the exact side this pick was posted on.

    Matched on the BOOK THE PICK WAS TAKEN AT, not the best close across books.
    That distinction is the whole measurement: CLV asks whether the price you
    actually got beat where that market settled. Grading a DraftKings bet
    against FanDuel's close would manufacture value out of a book disagreement
    the bettor never had access to.

    Returns (price, why_not). Exactly one is None, so a caller can never mistake
    "no close found" for a graded zero."""
    market = (row.get("market") or "").strip()
    sel = (row.get("selection") or "").strip()
    book = (row.get("book") or "").strip().lower()
    if not (market and sel and book):
        return None, "row is missing market, selection or book"

    # totals carry the side in the selection text ("Under 8.5"); h2h/spreads
    # carry an org code that has to be matched against the event's two teams.
    side, point = None, None
    if market == "totals":
        parts = sel.split()
        if len(parts) >= 2 and parts[0].lower() in ("over", "under"):
            side, point = parts[0].lower(), parts[1]
        if side is None:
            return None, f"could not read an over/under side from {sel!r}"

    for ev in events or []:
        if market in ("h2h", "spreads"):
            if sel == ev.get("home_org"):
                side = "home"
            elif sel == ev.get("away_org"):
                side = "away"
            else:
                continue
        b = (ev.get("books") or {}).get(book)
        if not isinstance(b, dict):
            continue
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        cell = m.get(side)
        if cell is None:
            continue
        price = cell.get("price") if isinstance(cell, dict) else cell
        if market == "totals":
            got = cell.get("point") if isinstance(cell, dict) else None
            # A total graded against a DIFFERENT number is not the same bet.
            if point is not None and got is not None and str(got) != str(point):
                continue
        if price is not None:
            return price, None
    return None, f"{book} posted no closing {market} price for {sel!r}"


def grade_record_clv(*, rows: list[dict] | None = None, write: bool = True,
                     path: Path | None = None) -> dict:
    """Grade every published pick against its slate's CLOSING snapshot, into a
    SIDECAR artifact.

    WHY A SIDECAR AND NOT THE RECORD ITSELF. The closing line does not exist
    when a pick is posted; it arrives hours later. Writing it back into the
    published row would be precisely the edit `check_append_only` exists to
    forbid, and loosening that check to allow "only CLV fields" would put a hole
    in the one guarantee that makes the record worth reading. So the record
    stays immutable and the grade lives beside it, keyed by bet_id.

    The sidecar is DERIVED and rebuildable from the immutable pair (the record,
    the snapshot cache). It is never the only copy of a price, and deleting it
    loses nothing but compute.

    An ungradeable pick is RECORDED AS UNGRADED WITH ITS REASON rather than
    skipped. A pick silently missing from this file would read as "no bets that
    day", which is the empty-but-valid failure this codebase keeps getting bitten
    by. The commonest real reason is a missing close snapshot, and that is
    unrecoverable after the fact: it means the close job did not fire."""
    rows = rows if rows is not None else load_record()
    graded: dict[str, dict] = {}
    reasons: Counter = Counter()
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(str(r.get("slate_date") or "")[:10], []).append(r)

    for day, day_rows in sorted(by_date.items()):
        snap = bi.closing_snapshot(day) if day else None
        events = bi.parse_events(snap) if snap else []
        for r in day_rows:
            bid = r.get("bet_id")
            if not bid:
                reasons["row carries no bet_id"] += 1
                continue
            if not snap:
                graded[bid] = {"bet_id": bid, "slate_date": day, "graded": False,
                               "reason": "no closing snapshot for this slate; the "
                                         "close job did not fire and CLV is "
                                         "unrecoverable after the fact"}
                reasons["no closing snapshot"] += 1
                continue
            close, why = _close_price_for(r, events)
            if close is None:
                graded[bid] = {"bet_id": bid, "slate_date": day, "graded": False,
                               "reason": why}
                reasons[why or "unmatched"] += 1
                continue
            g = grade_clv(r.get("odds_at_post"), close)
            graded[bid] = {"bet_id": bid, "slate_date": day, "graded": True,
                           "book": r.get("book"), "market": r.get("market"),
                           "selection": r.get("selection"),
                           "odds_at_post": r.get("odds_at_post"),
                           "odds_at_close": close, **g}
            reasons["graded"] += 1

    ok = [g for g in graded.values() if g.get("graded")]
    beat = [g for g in ok if g.get("beat_close")]
    clvs = [g["clv_pct"] for g in ok if isinstance(g.get("clv_pct"), (int, float))]
    payload = {
        "generated_at": _now(),
        "source": "derived from betting_record.json + the closing snapshot cache",
        "n_rows": len(rows),
        "n_graded": len(ok),
        "n_ungraded": len(graded) - len(ok),
        # None, not 0.0, on an empty set: a rate over zero bets is not a rate.
        "beat_close_rate": round(len(beat) / len(ok), 4) if ok else None,
        "avg_clv_pct": round(sum(clvs) / len(clvs), 3) if clvs else None,
        "ungraded_reasons": dict(sorted(reasons.items())),
        "picks": [graded[k] for k in sorted(graded)],
    }
    if write:
        _write(Path(path or CLV_PATH), payload)
    return payload


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
def is_bettable(game: dict) -> bool:
    """Can this schedule row still be priced and still anchor a closing line?

    THE DEFECT THIS CLOSES. `slate_games` filtered by DATE only, though every
    row carries `status` (StatsAPI's abstractGameState, written by
    fantasy_schedule). Two things went wrong with that. A finished or wiped game
    was published on the board with live-looking prices and an edge. Worse, the
    close job takes `min(datetime)` over the slate, so a POSTPONED 1:05 game
    anchored the closing-snapshot window for the entire slate: the job fired six
    hours early against a board nobody could bet, spent the credits, and the
    real closing lines were never captured. CLV is unrecoverable after the fact,
    so that one is not a cosmetic bug.

    UNKNOWN STATES ARE BETTABLE. The list below names states we KNOW are dead;
    anything else (including a missing status on an older payload) passes, so a
    StatsAPI vocabulary change degrades to the previous behaviour instead of
    blanking the board."""
    st = str((game or {}).get("status") or "").strip().lower()
    return st not in NOT_BETTABLE_STATES


def anchors_close_window(game: dict) -> bool:
    """Does this row's first pitch bound the close-snapshot window?

    "CAN IT BE BET" AND "MAY A CLOSE SNAPSHOT BE TAKEN AFTER IT" ARE DIFFERENT
    QUESTIONS, and the close job answered the second with `is_bettable` on
    2026-08-05. `is_bettable` drops a game the moment StatsAPI flips it to Live,
    so the earliest first pitch on the bettable slate JUMPS FORWARD past every
    game already under way. The refusal boundary moved with it: with a 22:35Z
    game and a 22:40Z game on the card, the 22:35Z game leaves the slate at
    22:35Z, the boundary becomes 22:40Z, and the job is free to fire at 22:39Z.
    That capture is a genuine closing line for the later games and an IN-GAME
    line for the one being played, stamped "close" and graded as CLV. There is
    no way to tell the two apart afterwards and no way to recapture the real
    close, so this is not a cosmetic bug.

    THE RAW SLATE IS NOT THE ANSWER EITHER. Measured on today's file:
    data/fantasy.json's 2026-08-05 block holds 15 games, 4 of them Final with
    first pitches from 18:10Z to 19:10Z and 11 Preview from 22:35Z on. Anchoring
    the boundary on the unfiltered list puts it at 18:10Z, which has passed by
    early afternoon, so every fire that evening refuses and all 11 night games
    lose their closing lines entirely. Postponements are worse: a called-off 1:05
    game would hold the boundary in the early afternoon forever, which is the
    same defect that used to fire the capture six hours early, wearing the
    opposite sign.

    So the anchor set is "still bettable OR being played right now". Final,
    postponed and cancelled games have already left the book's board and cannot
    be captured at any price, in-game or otherwise; Live and suspended games are
    still listed at a live price and are exactly what must stop a capture.
    Staleness is safe in the only direction it can move: a schedule block
    refreshed before first pitch still reads Preview, which is bettable, which
    keeps the game in the anchor set and keeps the boundary early."""
    st = str((game or {}).get("status") or "").strip().lower()
    return is_bettable(game) or st in IN_PROGRESS_STATES


def slate_games(on_date: str | None = None, *, include_unbettable: bool = False) -> list[dict]:
    """Today's BETTABLE games from data/fantasy.json's schedule block. That block
    is already refreshed by run_monthly step 9d, so /betting/ costs the pipeline
    zero extra StatsAPI calls.

    The slate date is the earliest date that still has a bettable game, not the
    earliest date on file: an evening build on a day whose games are all Final
    should show tomorrow's board rather than a board of finished scores. Pass
    `include_unbettable=True` for a raw read (nothing in the pipeline wants
    one; it exists so a diagnosis can compare the two counts)."""
    fan = _load("fantasy.json") or {}
    games = ((fan.get("schedule") or {}).get("games")) or []
    if not games:
        return []
    live = games if include_unbettable else [g for g in games if is_bettable(g)]
    if on_date:
        return [g for g in live if g.get("date") == on_date]
    dated = [g for g in live if g.get("date")]
    if not dated:
        # Every game on file is Final/postponed. That is a real state (a late
        # build on the last day of a homestand), not a missing schedule, and the
        # caller distinguishes them by re-reading with include_unbettable.
        log.info("betting_export: schedule holds %d games and none are bettable "
                 "(all Final, postponed or in progress)", len(games))
        return []
    day = min(g["date"] for g in dated)
    return [g for g in dated if g["date"] == day]


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


def _stamp(s) -> datetime | None:
    """An ISO stamp (either producer's) -> aware UTC, or None."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def match_event(game: dict, candidates: list[dict] | None) -> dict | None:
    """The odds event for THIS game, not for this org pair.

    THE DEFECT. `team_bets` keyed parsed events by `(home_org, away_org)` into a
    plain dict. A doubleheader is TWO schedule rows and TWO odds events for one
    org pair, so the second event OVERWROTE the first and both slate rows were
    joined to the same prices. At least one of the two games then published a
    wrong price, edge, EV and Kelly on a public page, and nothing about the row
    looked unusual. Keying to a LIST and matching on first pitch fixes it: the
    two games are hours apart, so the nearest `commence_time` is unambiguous.

    THE SINGLE-CANDIDATE SHORTCUT IS DELIBERATE. One event for the pair on a
    non-doubleheader date is the ordinary case and takes the event without a
    time check, because a book that posts a start time five minutes off ours
    must not blank an otherwise healthy row. The check is required exactly where
    it can be wrong: two candidates, or a row the schedule flagged as a
    doubleheader (books sometimes post only one half early, and taking it for
    both games is the same defect wearing one event).

    Returns None rather than a guess when nothing matches, which drops the game
    to a model-only fair line. That is the safe direction: an unpriced row is
    visibly unpriced, a mispriced row is not."""
    cands = [c for c in (candidates or []) if c]
    if not cands:
        return None
    if len(cands) == 1 and not game.get("double_header"):
        return cands[0]
    t0 = _stamp(game.get("datetime"))
    if t0 is None:
        log.warning("betting_export: %s @ %s has %d candidate odds events and no first "
                    "pitch stamp to tell them apart; leaving the game unpriced",
                    (game.get("away") or {}).get("org"), (game.get("home") or {}).get("org"),
                    len(cands))
        return None
    scored = []
    for c in cands:
        t = _stamp(c.get("commence_time"))
        if t is not None:
            scored.append((abs((t - t0).total_seconds()) / 60.0, c))
    if not scored:
        log.warning("betting_export: no candidate odds event for %s @ %s carries a "
                    "usable commence_time; leaving the game unpriced",
                    (game.get("away") or {}).get("org"), (game.get("home") or {}).get("org"))
        return None
    scored.sort(key=lambda r: r[0])
    delta, best = scored[0]
    if delta > EVENT_MATCH_MAX_MINUTES:
        log.warning("betting_export: nearest odds event for %s @ %s is %.0f min from "
                    "first pitch (limit %d); refusing to price this game off it",
                    (game.get("away") or {}).get("org"), (game.get("home") or {}).get("org"),
                    delta, EVENT_MATCH_MAX_MINUTES)
        return None
    return best


def team_bets(games: list[dict], events: list[dict], *, teams=None, parks=None,
              starters=None) -> list[dict]:
    """Every game on the slate: model probabilities, the market when a snapshot
    exists, and the edge between them."""
    teams = teams if teams is not None else bm.team_inputs()
    parks = parks if parks is not None else bm.park_index()
    starters = starters if starters is not None else bm.starter_inputs()
    # A LIST per org pair, not one event. See `match_event`: a doubleheader puts
    # two events under one key and a dict silently kept the last one parsed.
    by_pair: dict[tuple, list] = {}
    for ev in events or []:
        by_pair.setdefault((ev.get("home_org"), ev.get("away_org")), []).append(ev)

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
        ev = match_event(g, by_pair.get((ho, ao)))
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
            "status": g.get("status"),
            "double_header": bool(g.get("double_header")),
            # WHICH odds event priced this row. On a doubleheader the org pair
            # is not a key, so the event id and its start are the only way a
            # reader (or a test) can prove game two was not priced off game one.
            "odds_event_id": (ev or {}).get("event_id"),
            "odds_commence_time": (ev or {}).get("commence_time"),
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
# VINTAGE STATE: what the honest mode can grade, and which gates are shut
# ===========================================================================
def _graded_block(evald: dict, key: str) -> dict | None:
    """One mode-labelled row of the backtest for the client's table.

    `n` is the sample the row was graded on. The contaminated blocks carry it
    directly; the vintage block carries `n_graded`, which equals `n` on the day
    it grades and is 0 (with no `n` at all) before then, so both are read and
    the honest count wins."""
    b = evald.get(key)
    if not isinstance(b, dict):
        return None
    row = {k: b.get(k) for k in BLOCK_KEYS if k in b}
    row["key"] = key
    n = b.get("n_graded") if key == "vintage" else b.get("n")
    row["n"] = n if n is not None else b.get("n_graded")
    skill = b.get("skill_vs_home_base") or {}
    # The significance, not just the point estimate. The forward split beats the
    # home-field baseline on the number and does NOT clear the one-sided 95%
    # bar, and a page that prints the first without the second is claiming a
    # result the artifact does not contain.
    row["skill_vs_home_base"] = {
        "delta": skill.get("delta"), "sd": skill.get("sd"), "t": skill.get("t"),
        "beats_baseline_95": skill.get("beats_baseline_95"),
        "n_for_95": skill.get("n_for_95"), "baseline": skill.get("baseline"),
    } if skill else None
    return row


def validation_state(evald: dict | None) -> dict:
    """The block that answers three questions without leaving the page: is
    there a pick, is the model validated, and when will it be.

    EVERY value here is READ from data/betting_model_eval.json. Nothing is
    computed, projected or filled in. If the artifact has not been written the
    state says exactly that, because "no artifact" and "artifact says zero" are
    different facts and a reader is entitled to tell them apart.

    One thing deliberately absent: a calendar date for validation. The gates
    give a count (600 vintage-graded games, 0 in hand) and the coverage gives
    the first game date a vintage can price. Turning those into "expect it in
    March" needs a games-per-night rate the artifact does not carry, and a
    projected date is exactly the kind of number this module refuses to
    invent."""
    evald = evald or {}
    if not evald:
        return {
            "available": False,
            "artifact": "data/betting_model_eval.json",
            "reason": ("the backtest artifact has not been written in this build, so the "
                       "validation state is unknown rather than clean"),
            "validated": False,
            "min_edge": None,
        }
    cov = evald.get("vintage_coverage") or {}
    gate = evald.get("min_edge_gate") or {}
    blocks = [b for b in (_graded_block(evald, k)
                          for k in ("in_sample", "forward", "vintage")) if b]
    vintage = evald.get("vintage") or {}
    return {
        "available": True,
        "artifact": "data/betting_model_eval.json",
        "generated_at": evald.get("generated_at"),
        "model_version": evald.get("model_version"),
        "validated": bool(evald.get("validated")),
        "gates_picks": bool(evald.get("gates_picks")),
        "min_edge": evald.get("min_edge"),
        "modes": evald.get("modes") or [],
        "headline_mode": evald.get("headline_mode"),
        "mode_meaning": MODE_MEANING,
        "graded_blocks": blocks,
        "vintage": {
            "status": vintage.get("status"),
            "n_vintages": vintage.get("n_vintages"),
            "n_gradable": vintage.get("n_gradable"),
            "n_graded": vintage.get("n_graded"),
            "n_skipped_no_vintage": vintage.get("n_skipped_no_vintage"),
            "min_fit_games": vintage.get("min_fit_games"),
            "min_eval_games": vintage.get("min_eval_games"),
            "min_graded_games_for_min_edge": vintage.get("min_graded_games_for_min_edge"),
            "first_graded_date": vintage.get("first_graded_date"),
            "last_graded_date": vintage.get("last_graded_date"),
            # WHICH park index priced the honest sample. Null on an artifact
            # written before the park column existed, which is the correct
            # reading of that artifact: it does not know, and it may not claim
            # the games were park-dated when they were not.
            "park_basis": vintage.get("park_basis"),
            "note": vintage.get("note"),
        },
        "coverage": {k: cov[k] for k in COVERAGE_KEYS if k in cov},
        "n_games_completed": evald.get("n_games"),
        "gate": {
            "all_gates_open": gate.get("all_gates_open"),
            "gates": gate.get("gates") or [],
            "n_open": sum(1 for g in (gate.get("gates") or []) if g.get("open")),
            "n_gates": len(gate.get("gates") or []),
            "odds_snapshot_dates": gate.get("odds_snapshot_dates"),
            "sweep": gate.get("sweep"),
            "policy": gate.get("policy"),
        } if gate else None,
        "note": evald.get("note"),
    }


# ===========================================================================
# pick of the day
# ===========================================================================
def pick_blockers(*, min_edge: float | None, odds_configured: bool,
                  gate: dict | None = None) -> list[dict]:
    """EVERY reason there is no pick, not just the first one.

    The old shape returned the first blocker and stopped, so on a day with no
    odds feed the payload said "no odds feed" and never mentioned that the
    model has no measured threshold either. Both are true today. A reader told
    only the first would reasonably conclude that a key on the build box is all
    that stands between him and a published pick, which is wrong by two gates."""
    out = []
    if not odds_configured:
        out.append({
            "id": "odds_feed", "open": False,
            "need": "a cached odds snapshot to price against",
            "have": "none",
            "reason": "no odds feed is configured, so there is no market to have an edge against",
        })
    if min_edge is None:
        closed = [g for g in ((gate or {}).get("gates") or []) if not g.get("open")]
        n_gates = len((gate or {}).get("gates") or [])
        if closed:
            first = closed[0]
            have = first.get("have")
            have_txt = "none measured" if have is None else str(have)
            out.append({
                "id": "min_edge", "open": False,
                "need": first.get("need"),
                "have": have,
                "gates_closed": [g.get("id") for g in closed],
                "n_closed": len(closed), "n_gates": n_gates,
                "reason": (f"the model is unvalidated: the minimum-edge threshold sits behind "
                           f"{n_gates} gates and {len(closed)} are closed, starting with "
                           f"{first.get('need')} against {have_txt} in hand"),
            })
        else:
            out.append({
                "id": "min_edge", "open": False,
                "need": "a clean out-of-sample test that measures a minimum edge",
                "have": None,
                "reason": ("the model is unvalidated: the backtest is contaminated by "
                           "season-to-date team inputs, so no minimum-edge threshold has "
                           "been measured and no pick is published"),
            })
    return out


def pick_of_the_day(bets: list[dict], *, min_edge: float | None,
                    odds_configured: bool,
                    gate: dict | None = None) -> tuple[dict | None, str]:
    """The highest-EV qualifying edge, or None with every reason it is absent.

    Two hard gates, both of which are currently closed:
      * no odds feed means no market to have an edge against, and
      * no measured `min_edge` means no threshold, and a threshold invented to
        make a pick appear is the oldest trick in this industry.

    `gate` is the eval artifact's `min_edge_gate` block when one exists; it
    turns the second reason from "unvalidated" into the named count that is
    missing."""
    blockers = pick_blockers(min_edge=min_edge, odds_configured=odds_configured, gate=gate)
    if blockers:
        return None, "; ".join(b["reason"] for b in blockers)
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
# WHY THE BOARD IS EMPTY, AND WHAT MAY BE PUBLISHED WHEN IT IS
# ===========================================================================
def team_input_failure_reason(sources: dict) -> str:
    """Name WHICH team input was missing, with the counts, instead of asserting
    a build that did happen never happened.

    THE PUBLISHED FALSE DIAGNOSIS. This module shipped
    "team leaderboards have not been built yet" on a day when
    data/hitter_leaderboards.json, data/starter_leaderboards.json and
    data/bullpen_leaderboards.json each held 30 teams. The claim was not a
    measurement, it was an inference from one bit: `bm.team_inputs()` returned
    empty. That function returns the INTERSECTION of three org sets, so it goes
    empty for at least three different reasons that need three different fixes
    (a file that would not parse, a source whose rows carry no plus stat, and
    two org code sets that do not overlap), and only one of them is "not built
    yet". A reader who acted on the published reason would have rebuilt
    leaderboards that were already correct.

    So this reports what was actually observed: the file behind each of the
    three inputs, whether it parsed, and how many orgs it yielded."""
    src = sources or {}
    parts = []
    for key in ("offense", "rotation", "bullpen"):
        s = src.get(key) or {}
        if not s.get("present"):
            parts.append(f"{key}: {s.get('file')} missing or unreadable")
        else:
            parts.append(f"{key}: {s.get('n_orgs', 0)} orgs from {s.get('file')}")
    empty = [k for k in ("offense", "rotation", "bullpen")
             if not (src.get(k) or {}).get("n_orgs")]
    if empty:
        lead = (f"the team model needs all three team leaderboards and "
                f"{', '.join(empty)} yielded no orgs")
    else:
        lead = ("all three team leaderboards yielded orgs but their org codes do not "
                "intersect, so no club has a complete offense/rotation/bullpen row")
    return f"{lead} ({'; '.join(parts)})"


def _record_board_anomaly(reason: str, n_prev: int) -> None:
    """Raise an empty board into the ingest-health RED ledger.

    Best-effort by design: reporting must never be the reason a build fails. The
    ledger is what the deploy shell prints as `!!! INGEST RED`, so a board that
    went dark becomes visible on the run that broke it rather than whenever
    somebody next opens /betting/."""
    try:
        from run_monthly import _record_ingest
        _record_ingest(
            "betting_export", ok=False,
            message=(f"the betting board priced 0 games ({reason}); "
                     f"kept the previous {n_prev}-game board rather than publishing "
                     f"an empty one"),
        )
    except Exception:
        log.debug("betting_export: could not record the empty-board anomaly", exc_info=True)


def _hours_since(stamp) -> float | None:
    """Hours between an ISO stamp and now, or None if it will not parse."""
    dt = _stamp(stamp)
    if dt is None:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 1)


def _carry_previous_board(payload: dict, reason: str, *, log_fn=None) -> dict:
    """Never let an empty build OVERWRITE a populated board.

    Straight off the fantasy_export EMPTY-FETCH GUARD, for the same reason and
    with the same trade. Losing a day of freshness is recoverable on the next
    run; publishing a blank board is what a reader sees, and a blank board with
    a plausible-sounding empty_reason reads as "no games today" rather than as
    "this pipeline is broken".

    The MODEL, the VALIDATION STATE and the RECORD stay fresh: they are the
    honest half of the page and they did not fail. Only the slate half is
    carried, and it is stamped with the slate date it belongs to plus
    `stale_board`, so nothing on the page claims to be tonight's.

    THE STAMP WAS NOT ENOUGH, AND THAT MADE THIS GUARD LESS HONEST THAN THE
    EMPTY BOARD IT REPLACED. Measured against assets/betting.js as it ships
    today: `status.empty_reasons` renders ONLY through `renderTeam`'s
    `if (!bets.length)` branch, and this function's whole purpose is to make
    `bets.length` non-zero. `status.stale_board*` is matched by nothing in that
    file at all. So every stale-board key landed in a payload no reader could
    see, and a day-old set of prices rendered as an ordinary board with
    live-looking edges. The only field that changed on screen was the slate date
    in the banner, which reads as a date, not as a warning.

    Two things fix that, and they are deliberately independent:

      * `status.stale_board_notice` is ONE render-ready sentence, the field the
        client binds (one line, guarded by `status.stale_board`). Everything
        else here stays machine-shaped for a chip or a tooltip.
      * the staleness is ALSO pushed into `pick_blockers` and `pick_reason`,
        which the client already renders unconditionally on its landing tab
        ("potd") through the `<ul class="bt-list">` blocker list. That path
        needs no client change at all, so the honesty ships with this build
        rather than with a future one. A carried board always has an empty
        `bets` list at the moment the pick is decided, so `pick_of_the_day` is
        necessarily null and the blocker list is necessarily what renders."""
    prev = _load(OUT_PATH.name)
    prev_bets = (prev or {}).get("team_bets") or []
    if not prev_bets:
        return payload                      # nothing to protect; publish the empty state
    payload["team_bets"] = prev_bets
    payload["n_games"] = len(prev_bets)
    payload["slate_date"] = prev.get("slate_date") or payload.get("slate_date")
    payload["props_fair_lines"] = prev.get("props_fair_lines") or payload["props_fair_lines"]
    payload["parlay_context"] = parlay_context(prev_bets)
    prev_status = (prev or {}).get("status") or {}
    age_h = _hours_since(prev.get("generated_at"))
    age_txt = (f"built {age_h:g} hour{'' if age_h == 1 else 's'} ago" if age_h is not None
               else "built at an unrecorded time")
    # The sentence a reader must not be able to miss. It leads with the fact
    # (these are old prices), gives the age, and refuses the reading that makes
    # a stale board dangerous: that an edge on it is an edge now.
    notice = (f"STALE BOARD: these are the {payload['slate_date']} slate's prices, "
              f"{age_txt}, and they are NOT live. This build could not price a single "
              f"game, so the last board that could be built is standing in for tonight's. "
              f"No number on it is a current market and no edge on it is a current edge.")
    payload["status"]["stale_board"] = True
    payload["status"]["stale_board_notice"] = notice
    payload["status"]["stale_board_slate_date"] = payload["slate_date"]
    payload["status"]["stale_board_built_at"] = prev.get("generated_at")
    payload["status"]["stale_board_age_hours"] = age_h
    # WHICH capture produced the prices on screen. `status.odds_captured_at`
    # describes the snapshot THIS build read, which can be minutes old while the
    # board is a day old, and a fresh capture time next to stale prices is the
    # exact misreading this block exists to prevent.
    payload["status"]["stale_board_odds_captured_at"] = prev_status.get("odds_captured_at")
    payload["status"]["stale_board_reason"] = (
        f"this build priced 0 games ({reason}), so the board below is the last one that "
        f"could be built, for the {payload['slate_date']} slate. It is NOT tonight's "
        f"board and no price on it should be treated as live.")
    # Mutated IN PLACE: build() holds this same list object and hands it to the
    # preview slice, so the free tier and the full payload cannot disagree about
    # whether the board is stale.
    blockers = payload.get("pick_blockers")
    if isinstance(blockers, list) and not any((b or {}).get("id") == "stale_board"
                                              for b in blockers):
        blockers.append({
            "id": "stale_board", "open": False,
            "need": "a board priced from tonight's slate",
            "have": f"the {payload['slate_date']} board, {age_txt}",
            "reason": notice,
        })
    # The other half of the same honesty: the client falls back to `pick_reason`
    # whenever the blocker list is empty, so the sentence has to be in both.
    prev_reason = str(payload.get("pick_reason") or "").strip()
    if "STALE BOARD" not in prev_reason:
        payload["pick_reason"] = (f"{notice} The rest of this build reports: {prev_reason}"
                                  if prev_reason else notice)
    if log_fn:
        log_fn(f"betting_export: priced 0 games ({reason}); kept the previous "
               f"{len(prev_bets)}-game board rather than publishing an empty one")
    log.error("betting_export: board priced 0 games (%s); kept the previous %d-game "
              "board and stamped it stale", reason, len(prev_bets))
    _record_board_anomaly(reason, len(prev_bets))
    return payload


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
    # `team_inputs_detail`, not `team_inputs`: the per-source org counts are the
    # difference between naming the broken input and guessing at it. See
    # team_input_failure_reason for the published false diagnosis that forced it.
    team_detail = bm.team_inputs_detail()
    teams, team_sources = team_detail["teams"], team_detail["sources"]
    parks, starters = bm.park_index(), bm.starter_inputs()
    ctx = bm.league_context()
    coeffs = bm.coefficients()
    evald = _load("betting_model_eval.json") or {}

    bets = team_bets(games, events, teams=teams, parks=parks, starters=starters) if games else []
    min_edge = evald.get("min_edge")          # None until a clean test measures one
    gate = evald.get("min_edge_gate")
    odds_configured = bool(status.get("configured") and events)
    validation = validation_state(evald)
    # ONE derivation of "validated", read by status.model, model.validated and
    # (through the payload) the client's banner chip, so the three can never
    # disagree on the page. It takes BOTH halves: the artifact's gates open AND
    # a measured threshold. "All gates open" with a null min_edge is a
    # contradiction, and this resolves it the safe way.
    validated = bool(validation.get("validated") and min_edge is not None)
    blockers = pick_blockers(min_edge=min_edge, odds_configured=odds_configured, gate=gate)
    pick, pick_reason = pick_of_the_day(bets, min_edge=min_edge,
                                        odds_configured=odds_configured, gate=gate)
    record = load_record()

    empty_reasons = []
    if not teams:
        empty_reasons.append(team_input_failure_reason(team_sources))
    if not games:
        # Distinguish "the schedule is empty" from "every game on the schedule is
        # already Final or postponed". The old copy asserted the first and would
        # have sent a reader hunting a schedule refresh that ran perfectly.
        n_raw = len(slate_games(on_date, include_unbettable=True))
        if n_raw:
            empty_reasons.append(f"the schedule holds {n_raw} game(s) for this date and "
                                 "none are bettable (all Final, postponed or in progress)")
        else:
            empty_reasons.append("no slate found in data/fantasy.json; the schedule refresh "
                                 "has not run today")
    elif not bets:
        empty_reasons.append(f"{len(games)} game(s) are on the slate and none could be "
                             "priced; the model returned no row for any matchup")
    if not events:
        # `status["note"]` reads "odds feed configured" on a configured box, which
        # published as the literal empty_reason "odds feed configured" - a state,
        # not a reason, and it told the reader nothing about why there are no
        # prices. Name the missing artifact instead.
        if status.get("configured"):
            empty_reasons.append("the odds feed is configured but no snapshot is cached "
                                 "yet; betting_ingest has not captured one")
        else:
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
            "model": "validated" if validated else "unvalidated",
            "model_mode": validation.get("headline_mode"),
            # The observation behind any empty-board reason, so the claim on the
            # page can be checked against the files rather than believed.
            "team_input_sources": team_sources,
            "n_slate_games": len(games),
            "stale_board": False,
            "empty_reasons": empty_reasons,
        },
        "model": {
            "version": bm.MODEL_VERSION,
            "validated": validated,
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
            "backtest": {k: evald.get(k) for k in BACKTEST_KEYS if k in evald} or None,
            # The vintage state, the coverage behind it and the three gates on
            # min_edge, so the client can say WHICH number it is showing and
            # WHY there is no pick without guessing at either.
            "validation": validation,
            "min_edge": min_edge,
        },
        "disclaimer": DISCLAIMER,
        "pick_of_the_day": pick,
        "pick_reason": pick_reason,
        "pick_blockers": blockers,
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

    # REFUSE TO OVERWRITE A POPULATED BOARD WITH AN EMPTY ONE. This runs before
    # the preview is sliced and before either file is written, so the preview and
    # the full payload can never disagree about which slate is on the page.
    if not bets:
        payload = _carry_previous_board(
            payload, "; ".join(empty_reasons) or "no reason recorded", log_fn=log_fn)
    bets = payload["team_bets"]

    preview = {
        "generated_at": payload["generated_at"],
        "slate_date": payload["slate_date"],
        "status": payload["status"],
        # The free slice carries the FULL validation state. Whatever a future
        # gate hides, "why is there no pick and is this thing validated" is not
        # it: that answer is the reason a reader can trust the paid half.
        "model": {k: payload["model"][k] for k in
                  ("version", "validated", "stage", "min_edge", "validation")},
        "disclaimer": DISCLAIMER,
        # READ BACK OFF THE PAYLOAD, not off the locals that built it. The
        # stale-board guard above appends a blocker and rewrites the pick
        # reason, and a preview built from `pick_reason`/`blockers` would ship
        # the free tier a board with the staleness edited out of it.
        "pick_of_the_day": payload["pick_of_the_day"],
        "pick_reason": payload["pick_reason"],
        "pick_blockers": payload["pick_blockers"],
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
                   f"({len(bets)} games, odds={payload['status']['odds_feed']}"
                   f"{', STALE BOARD' if payload['status'].get('stale_board') else ''})")
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
        v = p["model"]["validation"]
        print(json.dumps({
            "slate_date": p["slate_date"], "n_games": p["n_games"],
            "status": p["status"], "pick": p["pick_of_the_day"],
            "pick_reason": p["pick_reason"],
            "pick_blockers": [b["id"] for b in p["pick_blockers"]],
            "validated": v.get("validated"),
            "headline_mode": v.get("headline_mode"),
            "vintages": (v.get("coverage") or {}).get("n_vintages"),
            "vintage_graded": (v.get("vintage") or {}).get("n_graded"),
            "gates_open": f"{(v.get('gate') or {}).get('n_open')} of "
                          f"{(v.get('gate') or {}).get('n_gates')}",
            "record": p["record"],
            "n_prop_pitchers": len(p["props_fair_lines"]["pitchers"]),
            "n_prop_hitters": len(p["props_fair_lines"]["hitters"]),
            "n_parlay_legs": len(p["parlay_context"]["legs"]),
        }, indent=1))
