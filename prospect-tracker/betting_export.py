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

TWO PROVISIONAL SLOTS SHIP, AND `model.validated` IS STILL FALSE. The backtest
is contaminated (betting_model.backtest explains how), so the measured
threshold `min_edge` stays null. What the slates publish against is a POLICY
floor, `PROVISIONAL_MIN_EDGE`, and every surface says so in that word.
`pick_of_the_day` takes the highest model win probability inside a normal price
band and `longshot_of_the_day` takes the highest EV at +200 or longer. Both
read the SAME floor, `resolve_min_edge`. Inventing a second, lower floor so
that the longshot slot always has something in it would be the single most
dishonest number on the site, so an empty slot stays empty and names the floor
it could not clear.

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
import math
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import betting_ingest as bi
import betting_model as bm

log = logging.getLogger("betting_export")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "betting.json"
PREVIEW_PATH = DATA_DIR / "betting_preview.json"

#: THE RECORD LIVES OUTSIDE data/ AND THAT IS THE WHOLE POINT (2026-08-09).
#:
#: data/betting_record.json is GIT-TRACKED and deploy/nightly-build.sh runs
#: `git checkout -- .` before every pipeline. So a row appended on production at
#: 21:00 was DESTROYED at 03:10 the next morning, silently and with no error
#: anywhere: the checkout restored the committed `[]`, `load_record` read that as
#: "the record is empty", and `check_append_only` then waved through a one-row
#: proposal as a perfectly legal append. The immutability guarantee held on every
#: individual write and the ledger still could not survive a night.
#:
#: The fix is a storage seam, not a looser check. `.cache/betting/record.jsonl`
#: is the SOURCE OF TRUTH: untracked (`.cache/` is gitignored), append-only one
#: JSON object per line, each line carrying the chain hash of everything before
#: it. `data/betting_record.json` becomes DERIVED - re-rendered from the JSONL on
#: every build, published by rsync, and safe to lose.
BETTING_CACHE_DIR = ROOT / ".cache" / "betting"
RECORD_JSONL = BETTING_CACHE_DIR / "record.jsonl"
RECORD_PATH = DATA_DIR / "betting_record.json"

#: THE CHAIN ANCHOR, AND WHY IT IS NOT IN data/ EITHER (2026-08-09).
#:
#: `record_publish_blockers` asks whether the record still contains the chain
#: hash the LAST build published, which is the only check that can tell an append
#: apart from a quiet rewrite. That previous value was read back out of
#: data/betting.json, which is GIT-TRACKED, so on production the nightly
#: `git checkout -- .` restored a committed board whose `record` block has no
#: `chain_sha` at all. `published_chain_sha` then arrived as None on every single
#: build, `chain_extends(None, rows)` returns True by construction, and the half
#: of the `record_storage` blocker that detects a rewrite was permanently
#: disarmed while reporting itself open.
#:
#: The anchor therefore lives beside the record it anchors, under `.cache/`,
#: which the checkout cannot touch and which deploy/WEBMASTER.md tells the
#: webmaster to back up. data/betting.json stays the fallback for a box that has
#: never written an anchor, so nothing regresses on a first build.
PUBLISHED_CHAIN_PATH = BETTING_CACHE_DIR / "published_chain.json"
SETTLEMENT_PATH = DATA_DIR / "betting_settlement.json"

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

# States that mean THE DAY HAS ALREADY STARTED, so the date they sit on can no
# longer be a whole board. Read by `_slate_is_open`; see `resolve_slate` for the
# 1-of-15 board that forced it.
#
# Postponed, cancelled and "other" are deliberately NOT here. A called-off game
# is not evidence that the rest of its card is under way - the 2026-08-05 close
# window analysis in `anchors_close_window` turns on exactly that distinction -
# and treating one postponement as a started slate would push the board a day
# forward on a card that has not thrown a pitch.
SLATE_STARTED_STATES = frozenset({
    "live", "in progress", "suspended", "final", "game over",
    "completed early", "forfeit",
})

# How far a parsed odds event's `commence_time` may sit from a schedule row's
# first pitch and still be that game. The two games of a doubleheader are about
# three and a half hours apart (game two starts roughly 30 minutes after game
# one ends) and a split doubleheader is about seven, so three hours is wide
# enough to absorb the routine disagreement between the book's posted start and
# StatsAPI's, and far too narrow to cross-match the halves of a doubleheader.
EVENT_MATCH_MAX_MINUTES = 180

# The hold band a two-sided quote must sit in to be trusted as THE de-vig source
# for a market. See `_market_view`. Below zero is an arbitrage, which no single
# book posts on purpose and which means one of the two prices is stale; above
# the ceiling is a quote the book is not really making.
#
# WHERE 12 COMES FROM. .cache/odds/2026-08-09-0133.json holds 466 two-sided
# book-markets. The widest hold on a PREGAME event is 6.268%, and the four above
# 12% (19.010%, 15.957%, 15.320%, 12.715%) are all one book on games already in
# progress. So on the board this module actually prices, the ceiling rejects
# nothing and exists for the stale quote that has not happened yet. Inclusive at
# both ends.
DEVIG_HOLD_MIN_PCT = 0.0
DEVIG_HOLD_MAX_PCT = 12.0

# HOW FAR BEHIND THE MARKET A QUOTE MAY BE AND STILL SET THE DENOMINATOR.
#
# The min-hold rule shipped on 2026-08-09 rewards the tightest two-sided quote,
# and a book that simply has not reposted looks tight for free: its two prices
# are a snapshot of a market that has since moved, and nothing in a hold
# calculation can tell that apart from a genuinely efficient price. The fair
# probabilities that come out then set every edge in the game.
#
# WHERE 15 COMES FROM. Measured across both cached snapshots, on the PREGAME
# events - the only population `team_bets` ever prices - and per book-market,
# as minutes behind the FRESHEST book on that same market:
#   .cache/odds/2026-08-09-0133.json, 298 candidate book-markets: p50 0.20,
#     p90 1.02, max 1.017.
#   .cache/odds/2026-08-09-1822.json, 166 candidate book-markets: p50 0.58,
#     p95 1.35, max 5.083 (2 of 166 above 3 minutes).
# So 15 is roughly three times the largest lag either real board contains and
# rejects nothing on them. Like DEVIG_HOLD_MAX_PCT it exists for the stale quote
# that has not happened yet, and it is deliberately loose because the books that
# WIN this rule are the reduced-juice books (lowvig, betonlineag, betus) and
# those are also the slowest to repost: on the in-progress half of the 1822 file
# they run 5.8 to 11.5 minutes behind. A tight threshold would hand the
# denominator to a 6.5% hold book, which is the defect wearing the other sign.
#
# A book with no `last_update` is NOT rejected. The stamp is the book's own and a
# missing one is the parser's silence, not evidence of staleness.
STALE_BOOK_MAX_LAG_MINUTES = 15.0

# HOW FAR A QUOTE MAY SIT FROM THE MARKET'S OWN CONSENSUS.
#
# The second half of the same defect, and the half a timestamp cannot catch: a
# book can repost a price this second and still be quoting a game nobody else is
# quoting. Its de-vigged fair probability is then far from every other book's,
# the hold can still be tight, and the edge that comes out is manufactured by the
# denominator rather than found in the market.
#
# WHERE 0.05 COMES FROM. Same population, |fair(side 0) - median fair across the
# books on the agreed line|, only where at least CONSENSUS_MIN_BOOKS books are on
# it (with two books the median IS the midpoint and every book is equidistant, so
# the test is vacuous):
#   0133, 298 book-markets: p50 0.0019, p95 0.0139, p99 0.0202, max 0.0253.
#   1822, 166 book-markets: p50 0.0014, p95 0.0145, p99 0.0215, max 0.0242.
# Zero of the 464 exceed 0.03. 0.05 is about twice the largest real disagreement
# and rejects nothing on either board, while capping how much of an edge a single
# rogue denominator can invent at well under the 0.06 provisional floor.
#
# The measurement is deliberately taken on PREGAME markets only. On the
# in-progress half of the 1822 file the same statistic reaches 0.155 (CLE at CHW
# h2h: betus/lowvig/betonlineag at fair_home 0.456-0.459 against a median of
# 0.304, 11.3 to 11.5 minutes behind the freshest book), which is what a real
# stale quote looks like and is why both guards exist. Those events never reach
# the board: `team_bets` drops them.
CONSENSUS_FAIR_MAX_DISTANCE = 0.05
CONSENSUS_MIN_BOOKS = 3

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
    # "row", not the p-word: the 2026-08-16 Model Watch ruling retires it from
    # payload prose while the gates are closed, and "row" is the accurate word
    # in both frames, so this constant does not need to change when they open.
    "staking": "Every row on the public record is a flat 1 unit. Kelly is shown as information, never as a stake.",
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
# The provenance counts and `vintage_age_days` are on this list because leaving
# them off SILENTLY DROPPED THEM. leaderboard_vintages.coverage() grew them, this
# allowlist did not, and /betting/ kept serving the blended `n_vintages` that
# docs/diamond-betting.md section 6 says a reader must never quote alone: a
# backfilled vintage is evidence about a git blob, a live one is evidence that
# the nightly step fired, and the leakage check in section 5a grades the two arms
# against each other. Measured 2026-08-09: the live store holds 15 vintages, 10
# backfilled and 5 live, and the page said "15".
#
# `n_vintages_unknown_provenance` is here for the same reason: without it the two
# named arms need not add up to the total and a reader cannot tell whether the
# remainder is live or unclassified. Every key is guarded by `if k in cov`, so an
# artifact written before any of them existed still publishes cleanly.
COVERAGE_KEYS = ("schema", "n_vintages", "n_vintages_backfilled", "n_vintages_live",
                 "n_vintages_unknown_provenance", "n_vintages_with_parks",
                 "n_vintages_neutral_park", "first", "last", "missing_dates",
                 "span_days", "latest_cutoff", "earliest_gradable_game_date",
                 "vintage_age_days", "note")
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


def _public_path(p) -> str:
    """A path as the PAYLOAD may carry it: POSIX-style, relative to the site
    checkout root.

    Until 2026-08-16 the payload published four filesystem paths verbatim
    (status.feed_health.source, record_storage.authoritative_path and
    .derived_path, record_chain_anchor.source), and on the build box a verbatim
    path is absolute: data/betting.json served the OS username to every reader
    as part of "C:\\Users\\<name>\\...". A path on a public artifact is only
    ever there to say WHICH file inside the checkout answered, and the checkout
    root is the whole of the context a reader has, so that is the basis every
    published path uses now. Absolute paths still go to logs, where they belong.

    A path outside the checkout root has no honest relative form and is
    returned verbatim: the only callers that can produce one are tests pointing
    the module at tmp fixtures (test_betting.py pins the verbatim echo), and a
    production path that ever landed outside the root would be its own defect
    to fix at the source, not to disguise here."""
    try:
        return Path(p).resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


# ===========================================================================
# THE APPEND-ONLY RECORD
# ===========================================================================
class RecordImmutabilityError(RuntimeError):
    """Raised when a write would change or drop a row that is already
    published. This is not a warning and it is not recoverable by retrying:
    the caller built an array that rewrites history."""


def _canon(row) -> str:
    """Byte-stable form of one row, so comparison catches a re-ordered dict as
    equal and a changed value as different."""
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


#: The chain hash of an EMPTY record. Published as `chain_sha` on a record with
#: no rows, so "nothing has been claimed yet" is a value a reader can archive
#: and compare against, not an absent field.
CHAIN_GENESIS = "0" * 64


def chain_sha(rows: list[dict]) -> str:
    """A rolling hash over the record, folded row by row.

        h(0) = CHAIN_GENESIS
        h(i) = sha256( h(i-1) + "|" + canonical(row i) )

    WHAT IT BUYS A READER. `check_append_only` protects a write inside this
    process. It cannot help somebody reading the published file, who has no way
    to tell an append from a quiet rewrite of a record he saw yesterday: both
    arrive as a longer JSON array. The chain hash closes that. Archive today's
    value, and tomorrow's record either still contains it as one of its prefix
    hashes (an append: every earlier row is byte-identical) or it does not (a
    rewrite, whatever the row count says). `chain_extends` is that check.

    Deterministic by construction: `_canon` sorts keys, so a re-serialized row
    hashes the same, and no set or dict iteration order enters the fold."""
    h = CHAIN_GENESIS
    for row in rows or []:
        h = hashlib.sha256(f"{h}|{_canon(row)}".encode("utf-8")).hexdigest()
    return h


def chain_history(rows: list[dict]) -> list[str]:
    """Every prefix hash, oldest first, starting at CHAIN_GENESIS. len is
    len(rows) + 1: element i is the chain hash of the first i rows."""
    out = [CHAIN_GENESIS]
    for row in rows or []:
        out.append(hashlib.sha256(f"{out[-1]}|{_canon(row)}".encode("utf-8")).hexdigest())
    return out


def chain_extends(prev_sha: str | None, rows: list[dict]) -> bool:
    """Does `rows` extend a record whose chain hash was `prev_sha`?

    True when prev_sha is absent (nothing to extend), is the genesis value, or
    appears among this record's prefix hashes. False is a REWRITE: some row a
    reader has already seen is no longer byte-identical."""
    if not prev_sha or prev_sha == CHAIN_GENESIS:
        return True
    return prev_sha in chain_history(rows)


def _read_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    """(rows, envelopes) from the append-only JSONL, oldest first.

    An envelope is {seq, appended_at, prev_sha, chain_sha, row}. The chain is
    VERIFIED on read, not trusted: a line whose recorded chain_sha does not
    match the hash recomputed from the rows before it means the file was edited
    in place, and that raises rather than returning a plausible list. A blank
    line is skipped (a half-flushed append); a line that will not parse raises,
    for the same reason an unreadable JSON record does."""
    p = Path(path)
    if not p.exists():
        return [], []
    rows: list[dict] = []
    envs: list[dict] = []
    h = CHAIN_GENESIS
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except ValueError as exc:
            raise RecordImmutabilityError(
                f"{p.name} line {n} will not parse ({exc}); refusing to treat a corrupt "
                "append-only log as an empty record") from exc
        if not isinstance(env, dict) or not isinstance(env.get("row"), dict):
            raise RecordImmutabilityError(
                f"{p.name} line {n} is not an envelope carrying a `row` object")
        nxt = hashlib.sha256(f"{h}|{_canon(env['row'])}".encode("utf-8")).hexdigest()
        got = env.get("chain_sha")
        if got and got != nxt:
            raise RecordImmutabilityError(
                f"{p.name} line {n} carries chain_sha {got[:12]}... but the rows before it "
                f"hash to {nxt[:12]}...; the log was edited in place, which is the one "
                "thing an append-only record may never survive silently")
        rows.append(env["row"])
        envs.append({**env, "chain_sha": nxt, "prev_sha": h})
        h = nxt
    return rows, envs


def _append_jsonl(path: Path, existing: list[dict], new_rows: list[dict]) -> None:
    """Append `new_rows` to the log, chained onto `existing`.

    APPEND MODE, one line at a time, flushed per line. The file is never
    rewritten and never truncated, so a crash midway leaves a shorter valid log
    rather than a corrupt one, and a process that dies between two rows loses
    the second row and nothing else. This is deliberately NOT the atomic
    tmp-then-replace `_write` uses for derived artifacts: replacing the record
    wholesale is exactly the operation that must be impossible."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    h = chain_sha(existing)
    seq = len(existing)
    with p.open("a", encoding="utf-8") as fh:
        for row in new_rows:
            prev = h
            h = hashlib.sha256(f"{prev}|{_canon(row)}".encode("utf-8")).hexdigest()
            fh.write(json.dumps({"seq": seq, "appended_at": _now(),
                                 "prev_sha": prev, "chain_sha": h, "row": row},
                                sort_keys=True, separators=(",", ":"),
                                default=str) + "\n")
            fh.flush()
            seq += 1


def load_record(path: Path | None = None) -> list[dict]:
    """The published record as a list.

    TWO BACKENDS, ONE ANSWER. With no explicit path, the append-only JSONL at
    `.cache/betting/record.jsonl` wins whenever it exists, because it is the
    copy that survives the nightly `git checkout -- .`. When it does not exist
    the committed data/betting_record.json is read instead, which is what keeps
    a fresh box (and the two committed test fixtures) working unchanged: the
    first build on a box with rows in the JSON migrates nothing and loses
    nothing, it simply reads them and re-renders.

    An explicit `path` is honoured verbatim - tests write a JSON array into
    tmp_path and expect it back - and a `.jsonl` suffix selects the log reader.

    A MISSING file is an empty record, which is correct: there is nothing to
    protect yet. A file that exists but will not parse RAISES, because
    returning [] there would hand the caller a blank baseline and let the next
    write overwrite a record it could not read. Corruption must stop the
    pipeline, not silently reset the ledger."""
    if path is None:
        if RECORD_JSONL.exists():
            return _read_jsonl(RECORD_JSONL)[0]
        path = RECORD_PATH
    p = Path(path)
    if p.suffix == ".jsonl":
        return _read_jsonl(p)[0]
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


def ensure_record_log() -> dict:
    """Make the durable log EXIST, migrating whatever the JSON fallback holds.

    THIS IS NOT A PUBLISH AND IT CANNOT BECOME ONE. It creates a log with
    exactly as many rows as the record already has (today: zero), which is why
    it can run unconditionally on every build. Without it the `record_storage`
    blocker deadlocks: the log is created by the first append, and the first
    append is refused because there is no log.

    Migration is one-way and one-time. Rows sitting in the committed
    data/betting_record.json are moved INTO the log, because that file is the
    one a nightly checkout reverts and rows left there are already living on
    borrowed time."""
    if RECORD_JSONL.exists():
        return {"created": False, "migrated": 0, "path": str(RECORD_JSONL)}
    legacy = load_record(RECORD_PATH)
    BETTING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RECORD_JSONL.touch()
    if legacy:
        _append_jsonl(RECORD_JSONL, [], legacy)
    log.info("betting_export: created the append-only record log at %s "
             "(migrated %d row(s) out of the git-tracked JSON)",
             RECORD_JSONL, len(legacy))
    return {"created": True, "migrated": len(legacy), "path": str(RECORD_JSONL)}


def read_published_chain() -> dict:
    """The chain hash the previous build published, and where it came from.

    Returns {"chain_sha", "source", "durable", "armed", "published_at",
    "n_rows"}. `chain_sha` is None when nothing has ever been published, which
    is the honest answer and the one `chain_extends` treats as "nothing to
    extend". `durable` says whether the anchor file itself answered; `armed`
    says whether the rewrite check this value feeds can actually detect a
    rewrite, and when it cannot, `unarmed_reason` names why.

    THE FALLBACK IS DELIBERATELY KEPT and is not a hedge: a box upgrading to the
    durable anchor has a real previous value sitting in data/betting.json and
    throwing it away would lose one build's worth of rewrite detection. It is
    used ONLY while no anchor file exists, and the source is reported so a reader
    can tell which one answered.

    BUT THE FALLBACK MAY NOT MANUFACTURE A PASS (found 2026-08-16). The
    git-tracked betting.json's committed `record.chain_sha` is genesis, and a
    nightly `git checkout -- .` restores exactly that copy, so on production
    this function answered genesis-or-None forever and
    `chain_extends(None, rows)` is True by construction: the rewrite half of the
    record_storage blocker reported itself open while it could not detect
    anything. So when the durable anchor is absent, the fallback yields no
    usable value AND the record already holds rows, the state is reported as
    UNARMED, and `chain_anchor_closed_reason` turns that into a closed blocker.
    An empty record keeps the old behaviour: genesis is legitimate when there
    is nothing to protect yet."""
    p = PUBLISHED_CHAIN_PATH
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("betting_export: unreadable %s; falling back to the board",
                        p.name)
            obj = None
        if isinstance(obj, dict) and obj.get("chain_sha"):
            return {"chain_sha": obj.get("chain_sha"), "source": _public_path(p),
                    "durable": True, "armed": True,
                    "published_at": obj.get("published_at"),
                    "n_rows": obj.get("n_rows")}
    board = (_load("betting.json") or {}).get("record") or {}
    out = {"chain_sha": board.get("chain_sha"),
           "source": ("data/betting.json (git-tracked fallback; a nightly "
                      "`git checkout -- .` reverts it, so this value is absent on "
                      "production until the durable anchor is written)"),
           "durable": False, "armed": True,
           "published_at": None, "n_rows": board.get("n_rows")}
    reason = chain_anchor_closed_reason(out, load_record())
    if reason:
        out["armed"] = False
        out["unarmed_reason"] = reason
    return out


def chain_anchor_closed_reason(anchor: dict | None, rows: list[dict]) -> str | None:
    """None when the rewrite check is armed; otherwise the reason the chain
    half of the record_storage blocker must be CLOSED.

    One function, read by both the anchor report and the blocker, so the payload
    can never say "armed" while the blocker decides "vacuous". The three ways to
    be armed:
      * the record is empty, so there is no history to rewrite and genesis is a
        legitimate previous value;
      * the durable anchor answered, whose value is a real claim written at the
        end of the last publishing build (genesis there means "the record was
        empty when last published", and an append from it verifies);
      * the fallback carries a real non-genesis hash, the upgrading-box case the
        fallback exists for.
    Anything else means `chain_extends` would return True by construction while
    rows already exist, which is the vacuous pass found 2026-08-16."""
    anchor = anchor or {}
    if not rows:
        return None
    if anchor.get("durable"):
        return None
    sha = anchor.get("chain_sha")
    if sha and sha != CHAIN_GENESIS:
        return None
    return (f"the record already holds {len(rows)} row(s) but no durable chain "
            "anchor exists at .cache/betting/published_chain.json and the "
            "git-tracked fallback carries no usable chain_sha, so "
            "chain_extends would pass by construction without being able to "
            "detect a rewrite; the check is fail-closed until the next build "
            "that writes the anchor")


def write_published_chain(rows: list[dict], *, path: Path | None = None) -> dict:
    """Stamp the anchor with the chain hash this build is publishing.

    Called at the END of a build, after the publish decision has already been
    made against the PREVIOUS value. Writing it earlier would make the blocker a
    tautology: it would be comparing the record against itself."""
    p = Path(path or PUBLISHED_CHAIN_PATH)
    out = {"chain_sha": chain_sha(rows), "n_rows": len(rows),
           "published_at": _now(),
           "what": ("the chain hash of the public betting record as of the build "
                    "that wrote this file. record_publish_blockers checks the NEXT "
                    "build's record against it, which is how a rewrite is told "
                    "apart from an append.")}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return out


def record_storage() -> dict:
    """WHICH copy of the record is authoritative right now, and its chain hash.

    Published on the payload and read by `record_publish_blockers`, because
    "the record is stored somewhere a nightly checkout can delete" is a
    publish blocker and not a footnote."""
    jsonl = RECORD_JSONL.exists()
    rows = load_record()
    # The two paths ride through `_public_path`: this block lands verbatim on
    # data/betting.json AND data/betting_preview.json, and until 2026-08-16 both
    # published the build box's absolute paths, OS username included.
    return {
        "backend": "jsonl" if jsonl else "json_fallback",
        "authoritative_path": _public_path(RECORD_JSONL if jsonl else RECORD_PATH),
        "durable": bool(jsonl),
        "n_rows": len(rows),
        "chain_sha": chain_sha(rows),
        "derived_path": _public_path(RECORD_PATH),
        "path_basis": "relative to the site checkout root",
        "why": ("the append-only log under .cache/ is untracked, so the nightly "
                "`git checkout -- .` cannot revert it; data/betting_record.json is "
                "re-rendered from it every build"
                if jsonl else
                "no append-only log exists yet; the record is being read from "
                "data/betting_record.json. That file was git-tracked until "
                "2026-08-09, when a nightly `git checkout -- .` would have reverted "
                "a row appended there to the committed `[]`; it is now untracked "
                "and gitignored, so the checkout can no longer destroy it, but it "
                "is still not on the backup list and a box rebuild takes it with "
                "everything else under data/. `ensure_record_log` creates the log "
                "on the next build that writes"),
    }


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


def render_record(rows: list[dict] | None = None, *, path: Path | None = None) -> list[dict]:
    """Re-render the DERIVED data/betting_record.json from the log.

    Idempotent and safe to run on every build. It is not a publish and it
    cannot be one: it writes whatever the authoritative log already says. The
    nightly checkout reverting this file between builds costs nothing because
    of that."""
    rows = list(rows if rows is not None else load_record())
    _write(Path(path or RECORD_PATH), rows)
    return rows


def write_record(rows: list[dict], *, path: Path | None = None) -> list[dict]:
    """Publish the record after proving the write is append-only.

    With no explicit path the append lands in the JSONL log and the derived
    JSON is re-rendered from it, so the two can never disagree. An explicit
    path keeps the old single-file behaviour (a `.jsonl` suffix selects the
    log), which is what the tmp_path tests exercise."""
    if path is not None:
        p = Path(path)
        existing = load_record(p)
        check_append_only(existing, list(rows))
        if p.suffix == ".jsonl":
            _append_jsonl(p, existing, list(rows)[len(existing):])
        else:
            _write(p, list(rows))
        return list(rows)

    existing = load_record()
    check_append_only(existing, list(rows))
    _append_jsonl(RECORD_JSONL, existing, list(rows)[len(existing):])
    render_record(list(rows))
    return list(rows)


def append_record(new_rows: list[dict], *, path: Path | None = None,
                  ledger_closed: frozenset | None = None) -> list[dict]:
    """The only sanctioned way to add to the record.

    SEAM 2 of 2 for the dispersion exclusion AND for the section 7b ledger
    leg, and both are enforced HERE rather than at the call sites because this
    function is documented as the only sanctioned way in. A guard at the
    funnel cannot be bypassed by a future caller that does not know about it,
    which is the C-6 lesson: a suppression is not shipped until every path
    that could publish the suppressed quantity is guarded, and the cheapest
    way to guarantee that is to guard the funnel.

    THE VOCABULARY REPAIR (2026-08-16). Record rows built by `record_row`
    carry `market` in the FEED vocabulary (h2h / spreads / totals) with the
    board name beside it as `board_market`, and the dispersion guard here
    tested the raw `market` key, which the feed vocabulary walks straight
    past: `market_is_publishable("spreads")` is True because the exclusion
    list holds board names. Seam 1 masked it, since a runline can never win a
    slot while excluded, but a funnel guard that only works when the seam in
    front of it already did the job is not a guard. Every row's market now
    goes through `board_market()` before either leg is consulted.

    The record is empty today (five publish blockers are open), so this changes
    nothing now. It is here so both exclusions are already true on the first
    nightly that clears those blockers, rather than being remembered then.
    """
    if ledger_closed is None:
        ledger_closed = ledger_closed_markets()
    rows = list(new_rows or [])
    gated = bm.SLOT_MARKET_POLICY != "any"
    kept, refused_dispersion, refused_ledger = [], [], []
    for r in rows:
        mk = board_market(r) or r.get("market")
        if gated and not bm.market_is_publishable(mk):
            refused_dispersion.append(mk)
        elif gated and mk in ledger_closed:
            refused_ledger.append(mk)
        else:
            # POLICY "any" (2026-09-05): the row is kept and carries both legs as
            # disclosure, computed on the BOARD name so the feed vocabulary (h2h /
            # spreads / totals) cannot walk past either.
            r = {**r,
                 "dispersion_sensitive": bool(bm.market_is_dispersion_sensitive(mk)),
                 "evidence_closed": bool(mk in ledger_closed),
                 "market_policy": bm.SLOT_MARKET_POLICY}
            kept.append(r)
    if refused_dispersion:
        log.warning("betting_record: refused %d row(s) on a market excluded "
                    "while the dispersion correction is unserved: %s",
                    len(refused_dispersion), dict(Counter(refused_dispersion)))
    if refused_ledger:
        log.warning("betting_record: refused %d row(s) on a LEDGER-CLOSED "
                    "market (section 7b): %s",
                    len(refused_ledger), dict(Counter(refused_ledger)))
    existing = load_record(path) if path is not None else load_record()
    return write_record(existing + kept, path=path)


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

#: THE TWO MARKET VOCABULARIES, AND THE MAP BETWEEN THEM (2026-08-09).
#:
#: The board and the shadow ledger speak moneyline|runline|total. The odds feed,
#: the snapshot cache and therefore the CLV grader speak h2h|spreads|totals.
#: Nothing translated. A published slot stamped `market: "runline"` reached
#: `_close_price_for`, which branches on the feed's names, matched no branch, and
#: fell through to "no closing price" forever: SPREADS COULD NEVER BE GRADED, on
#: any row, and the sidecar reported it as a missing price rather than as a
#: vocabulary mismatch. The record now carries the FEED name in `market` (which
#: is what the two committed fixtures already used) and the BOARD name in
#: `board_market`, so each consumer reads the one it speaks.
BOARD_TO_FEED_MARKET = {"moneyline": "h2h", "runline": "spreads", "total": "totals"}
FEED_TO_BOARD_MARKET = {v: k for k, v in BOARD_TO_FEED_MARKET.items()}


def feed_market(row: dict) -> str | None:
    """The odds-feed market key for a row written in either vocabulary."""
    m = (row.get("market") or "").strip()
    if m in FEED_TO_BOARD_MARKET:
        return m
    return BOARD_TO_FEED_MARKET.get(m)


def board_market(row: dict) -> str | None:
    """The board/ledger market key for a row written in either vocabulary."""
    m = (row.get("board_market") or row.get("market") or "").strip()
    if m in BOARD_TO_FEED_MARKET:
        return m
    return FEED_TO_BOARD_MARKET.get(m)


def _side_and_point(row: dict, ev: dict | None):
    """(side, point, why_not) for one record row against one event.

    MACHINE FIELDS FIRST, LABEL ONLY AS A FALLBACK. `selection` is DISPLAY copy
    ("TBR +1.5", "Under 8.5", "NYM") and parsing it was the source of two
    separate grading failures: a runline selection is a label the h2h/spreads
    branch tried to match against an org code and never could, and a total's
    number had to be recovered from text. A row that carries `side` is read
    directly and its label is never touched.

    The fallback exists for LEGACY ROWS ONLY - anything published before the
    machine fields shipped - and it is exactly the old parser, so those rows
    keep grading exactly as they did."""
    mk = feed_market(row)
    side = (row.get("side") or "").strip().lower() or None
    point = row.get("point")

    if side:
        if mk == "totals" and side not in ("over", "under"):
            return None, None, f"side {side!r} is not over/under on a total"
        if mk in ("h2h", "spreads") and side not in ("home", "away"):
            return None, None, f"side {side!r} is not home/away on a {mk}"
        return side, point, None

    # ---- legacy label parsing -------------------------------------------
    sel = (row.get("selection") or "").strip()
    if not sel:
        return None, None, "row carries neither a machine `side` nor a selection label"
    if mk == "totals":
        parts = sel.split()
        if len(parts) >= 2 and parts[0].lower() in ("over", "under"):
            return parts[0].lower(), parts[1], None
        return None, None, f"could not read an over/under side from {sel!r}"
    if ev is None:
        return None, None, "legacy row needs an event to resolve its org label"
    if sel == ev.get("home_org"):
        return "home", point, None
    if sel == ev.get("away_org"):
        return "away", point, None
    return None, None, f"{sel!r} is neither team on this event"


def _same_point(want, got) -> bool:
    """Is a closing line the SAME NUMBER the pick was taken at?

    Absent on either side is not a mismatch (a moneyline has no number, and a
    legacy row may not carry one). Compared numerically, so 8.5 and "8.5" and
    8.50 are one line and -1.5 and +1.5 are two different bets."""
    if want is None or got is None:
        return True
    try:
        return abs(float(want) - float(got)) < 1e-9
    except (TypeError, ValueError):
        return str(want) == str(got)


def _close_price_for(row: dict, events: list[dict]):
    """The closing American price for the exact side this pick was posted on.

    Matched on the BOOK THE PICK WAS TAKEN AT, not the best close across books.
    That distinction is the whole measurement: CLV asks whether the price you
    actually got beat where that market settled. Grading a DraftKings bet
    against FanDuel's close would manufacture value out of a book disagreement
    the bettor never had access to.

    AND ON THE SAME NUMBER, IN EVERY MARKET. The totals branch always checked
    the point; the spreads branch never did. A +1.5 pick would therefore have
    graded against a -1.5 close - two opposite bets, one of them roughly +130
    and the other roughly -160 - and produced a CLV figure with no relationship
    to the wager. `_same_point` is now applied to spreads and totals alike.

    Returns (price, why_not). Exactly one is None, so a caller can never mistake
    "no close found" for a graded zero."""
    mk = feed_market(row)
    book = (row.get("book") or "").strip().lower()
    if not (mk and book):
        return None, "row is missing a recognised market or a book"
    what = row.get("selection") or row.get("side") or "?"

    # A row carrying machine fields resolves ONCE, with no event needed. Only a
    # legacy label row has to be re-resolved per event, because an org code only
    # means "home" or "away" relative to a particular matchup.
    fixed = None
    if (row.get("side") or "").strip() or feed_market(row) == "totals":
        side0, point0, why0 = _side_and_point(row, None)
        if side0 is None and (row.get("side") or "").strip():
            return None, why0
        if side0 is not None:
            fixed = (side0, point0)

    last_why = None
    for ev in events or []:
        if fixed is not None:
            side, point, why = fixed[0], fixed[1], None
        else:
            side, point, why = _side_and_point(row, ev)
        if side is None:
            last_why = why
            continue
        b = (ev.get("books") or {}).get(book)
        if not isinstance(b, dict):
            continue
        m = b.get(mk)
        if not isinstance(m, dict):
            continue
        cell = m.get(side)
        if cell is None:
            continue
        price = cell.get("price") if isinstance(cell, dict) else cell
        if mk in ("spreads", "totals"):
            got = cell.get("point") if isinstance(cell, dict) else None
            # A spread or a total graded against a DIFFERENT number is not the
            # same bet. This is a `continue`, not a match, so a book that moved
            # the line reads as "no close for THIS bet" rather than as value.
            if not _same_point(point, got):
                continue
        if price is not None:
            return price, None
    if last_why:
        return None, f"{book} posted no closing {mk} price for {what!r}: {last_why}"
    return None, f"{book} posted no closing {mk} price for {what!r}"


def close_events_for_calibration(day: str, open_rows: list[dict]) -> dict:
    """Build `tools.betting_calibration.append_close`'s `events_by_key` for one
    slate, off that slate's CLOSE snapshot.

    WHY THIS EXISTS. append_close shipped with no production caller at all: the
    only invocations in the tree were two tests, so `phase: close` rows were
    never written, `market_move_pct` was permanently null, and the learning
    artifact published a blocked_by naming a repair that would not have
    repaired it. The close job is the only moment the closing line is
    guaranteed on disk, which is where this is called from.

    Priced at the SAME BOOK the open row's best price came from, which
    `_close_price_for` already enforces for the public record and which
    append_close verifies again on the way in: a close taken at another book is
    a different market, and the gap between two books is not a move.

    Returns {} when the slate has no close snapshot, which is the ordinary
    state for every slate before the cron was installed."""
    snap = bi.closing_snapshot(day) if day else None
    if not snap:
        return {}
    events = bi.parse_events(snap) or []
    captured = snap.get("captured_at") if isinstance(snap, dict) else None
    out: dict = {}
    for r in open_rows or []:
        if r.get("game_pk") is None:
            continue
        book = (r.get("best_book") or "").strip().lower()
        if not book:
            continue
        # _close_price_for reads `book`; the calibration ledger names the same
        # field best_book because it is the best price ACROSS books at open.
        shim = {"market": r.get("market"), "book": book, "side": r.get("side"),
                "point": r.get("point"), "selection": r.get("label"),
                "game_pk": r.get("game_pk")}
        price, _why = _close_price_for(shim, events)
        if price is None:
            continue
        out[(r.get("game_pk"), r.get("market"), r.get("side"),
             None if r.get("point") is None else float(r["point"]))] = {
            "odds": price,
            "decimal": bi.american_to_decimal(price),
            "book": book,
            "captured_at": captured,
        }
    return out


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


# ===========================================================================
# THE SETTLEMENT SIDECAR
# ===========================================================================
#: A row older than this with no settlement is a publish blocker. Every MLB game
#: is final inside 12 hours of first pitch and the settling job runs nightly, so
#: 36 hours is two clear chances to grade and a wide margin for a late West
#: Coast finish. Past it, an ungraded row means the settling path is broken and
#: the published record is quietly reporting fewer results than it has.
SETTLE_STALE_HOURS = 36.0


def load_settlement(path: Path | None = None) -> dict:
    """The settlement sidecar as {bet_id: entry}. Missing or unreadable is an
    empty dict: settlement is DERIVED and rebuildable from the record plus the
    completed-game cache, so losing it costs compute and nothing else."""
    p = Path(path or SETTLEMENT_PATH)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("betting_export: unreadable %s", p.name)
        return {}
    return {e["bet_id"]: e for e in (payload.get("picks") or [])
            if isinstance(e, dict) and e.get("bet_id")}


def settle_record(*, rows: list[dict] | None = None, games: list[dict] | None = None,
                  write: bool = True, path: Path | None = None) -> dict:
    """Grade every published pick against its final score, into a SIDECAR.

    WHY A SIDECAR AND NOT THE RECORD ITSELF, again. The result does not exist
    when a pick is posted. Writing it back into the published row is the exact
    edit `check_append_only` forbids, and loosening that check for "only the
    result field" would put a hole in the one guarantee that makes the record
    worth reading. So the record stays byte-immutable and `record_summary` joins
    record + settlement + CLV at read time.

    THE GRADING ITSELF IS NOT DUPLICATED. The shadow ledger's `_settle_one` and
    `_profit` were extracted into betting_settle (as `grade_side` and
    `profit_units`) so every ledger grades a runline the same way. If that
    module is not on the box yet this function reports the missing dependency
    and settles NOTHING: a second implementation of "did a +1.5 cover" is how
    two surfaces end up disagreeing about the same bet."""
    rows = rows if rows is not None else load_record()
    try:
        import betting_settle as bs
    except ImportError as exc:
        payload = {
            "generated_at": _now(),
            "source": "derived from the record + the completed-game cache",
            "available": False,
            "n_rows": len(rows), "n_settled": 0,
            "n_open": len(rows), "n_ungradeable": 0,
            "blocked_reason": (f"betting_settle is not importable ({exc}); the record "
                               "cannot be settled without it and this module will not "
                               "reimplement _settle_one, because two implementations of "
                               "'did the runline cover' is how two surfaces come to "
                               "disagree about one bet"),
            "unsettled_reasons": {"betting_settle missing": len(rows)},
            "picks": [],
        }
        if write:
            _write(Path(path or SETTLEMENT_PATH), payload)
        return payload

    if games is None:
        games = bs.load_completed()
    by_pk = bs.index_games(games)

    picks: list[dict] = []
    reasons: Counter = Counter()
    for r in rows:
        bid = r.get("bet_id")
        if not bid:
            reasons["row carries no bet_id"] += 1
            continue
        g = by_pk.get(r.get("game_pk"))
        if not g:
            picks.append({"bet_id": bid, "slate_date": r.get("slate_date"),
                          "settled": False,
                          "reason": ("no completed game on file for game_pk "
                                     f"{r.get('game_pk')!r}; either it has not finished "
                                     "or the completed-game cache has not refreshed")})
            reasons["game not final"] += 1
            continue
        # `grade_side` speaks the BOARD vocabulary (moneyline/runline/total) and
        # the record row's `market` is the FEED key, so the translation happens
        # here rather than in either module. See BOARD_TO_FEED_MARKET.
        res = bs.grade_side(market=board_market(r), side=r.get("side"),
                            point=r.get("point"),
                            home_runs=g.get("home_runs"), away_runs=g.get("away_runs"))
        if not res:
            picks.append({"bet_id": bid, "slate_date": r.get("slate_date"),
                          "settled": False,
                          "reason": ("betting_settle cannot grade this market, side and "
                                     "point combination; it is recorded ungraded rather "
                                     "than guessed")})
            reasons["market not gradeable"] += 1
            continue
        stake = float(r.get("stake_units") or STAKE_UNITS)
        picks.append({
            "bet_id": bid, "slate_date": r.get("slate_date"), "settled": True,
            "result": res, "settled_at": _now(),
            "profit_units": bs.profit_units(result=res, decimal=r.get("decimal"),
                                            odds=r.get("odds_at_post"),
                                            stake_units=stake),
            "stake_units": stake,
            "final_home_runs": g.get("home_runs"), "final_away_runs": g.get("away_runs"),
        })
        reasons["settled"] += 1

    done = [p for p in picks if p.get("settled")]
    payload = {
        "generated_at": _now(),
        "source": "derived from the record + the completed-game cache",
        "available": True,
        "grader": "betting_settle.grade_side / profit_units (shared with every ledger)",
        "n_rows": len(rows),
        "n_settled": len(done),
        "n_open": len(rows) - len(done),
        "n_ungradeable": len(picks) - len(done),
        "unsettled_reasons": dict(sorted(reasons.items())),
        "picks": sorted(picks, key=lambda p: p["bet_id"]),
    }
    if write:
        _write(Path(path or SETTLEMENT_PATH), payload)
    return payload


def _merged_rows(rows: list[dict], clv: dict | None, settlement: dict | None) -> list[dict]:
    """Record rows with their sidecars joined on bet_id, for READING only.

    The sidecar wins where it has an answer, and the row's own legacy fields
    (records published before the sidecars existed carry `result`, `beat_close`
    and `clv_pct` inline) are the fallback. Nothing here is ever written back."""
    out = []
    for r in rows:
        bid = r.get("bet_id")
        merged = dict(r)
        s = (settlement or {}).get(bid) or {}
        if s.get("settled") and s.get("result"):
            merged["result"] = s["result"]
            if s.get("profit_units") is not None:
                merged["profit_units"] = s["profit_units"]
        c = (clv or {}).get(bid) or {}
        if c.get("graded"):
            for k in ("beat_close", "clv_pct", "clv_prob", "odds_at_close"):
                if c.get(k) is not None:
                    merged[k] = c[k]
        out.append(merged)
    return out


def record_summary(rows: list[dict] | None = None, clv: dict | None = None,
                   settlement: dict | None = None) -> dict:
    """W-L, net units, ROI, beat-close rate and average CLV. Every field is
    None or zero until the record actually has rows: an empty record reports
    an empty record, it does not report a 0% ROI as if 0 bets were graded.

    THE JOIN IS THE FIX (2026-08-09). This function read `r["beat_close"]` and
    `r["clv_pct"]` off the record, and by construction neither key can ever be
    on a record row: the record is byte-immutable and CLV lands hours after the
    pick is posted, which is why the sidecar exists at all. So `n_clv_graded`
    counted 0 forever and the page printed "not graded yet" over a fully graded
    record. Both sidecars are now joined on bet_id before anything is counted.

    `clv` and `settlement` are {bet_id: entry} maps; passing None loads them
    from disk, and passing {} deliberately measures the record alone."""
    rows = rows if rows is not None else load_record()
    clv = load_clv() if clv is None else clv
    settlement = load_settlement() if settlement is None else settlement
    merged = _merged_rows(rows, clv, settlement)

    settled = [r for r in merged if r.get("result") in ("won", "lost", "push", "void")]
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
    graded = [r for r in merged if r.get("beat_close") is not None]
    clvs = [r.get("clv_pct") for r in merged if isinstance(r.get("clv_pct"), (int, float))]
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
        # The rolling hash of the record these numbers were computed over, so a
        # reader who archived yesterday's value can prove today's record extends
        # it rather than having been quietly rewritten. See `chain_sha`.
        "chain_sha": chain_sha(rows),
        "chain_note": ("sha256 folded row by row over the record; a record that "
                       "still contains an archived value as one of its prefix "
                       "hashes is an append, and one that does not is a rewrite"),
    }


def load_clv(path: Path | None = None) -> dict:
    """The CLV sidecar as {bet_id: entry}. Same derived-and-rebuildable status
    as the settlement sidecar, so missing is empty rather than fatal."""
    p = Path(path or CLV_PATH)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("betting_export: unreadable %s", p.name)
        return {}
    return {e["bet_id"]: e for e in (payload.get("picks") or [])
            if isinstance(e, dict) and e.get("bet_id")}


# ===========================================================================
# CLOSE-CAPTURE HEALTH, MEASURED OFF THE CACHE THAT SURVIVES THE NIGHT
# ===========================================================================
#: A close capture older than this means the close job has not fired for a
#: slate that has already been played, and CLV for it is unrecoverable.
CLOSE_STALE_HOURS = 36.0

#: Written by tools/betting_close_job.py on EVERY invocation, refusals included.
#: Read here so the RED can say whether the job is running at all, which is a
#: different repair from the job running and never firing. Kept under .cache/
#: for the same reason the snapshots are: deploy/nightly-build.sh runs
#: `git checkout -- .`, so a tracked heartbeat cannot survive to be read.
CLOSE_HEARTBEAT_PATH = ROOT / ".cache" / "betting" / "close_job_heartbeat.json"


def _hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 3600.0, 2)


def snapshot_health(days: int = 14, *, now: datetime | None = None) -> dict:
    """Per-slate open/close snapshot coverage off `.cache/odds/`.

    WHY THE CACHE AND NOT A HEARTBEAT. data/job_heartbeat.json is GIT-TRACKED,
    so `git checkout -- .` reverts it before every pipeline: a heartbeat written
    by the 19:00 close job is gone by the time the 03:10 build could read it,
    and the artifact would report the job as never having run whether it ran or
    not. The odds cache is under `.cache/`, which is gitignored and untouched by
    the checkout, and it is the same evidence CLV grading reads. Health measured
    off the evidence cannot disagree with the grade.

    `diagnosis` names the REPAIR, not the symptom. "0 close snapshots" is a
    symptom; "the close cron is not installed or is running in the wrong
    timezone window" is something an operator can act on tonight."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=max(1, int(days)))).date().isoformat()

    slates: dict[str, dict] = {}
    n_unreadable = 0
    last_close: datetime | None = None
    last_open: datetime | None = None
    for meta in bi.list_snapshots():
        # Filename dates are UTC and a slate can straddle UTC midnight, so widen
        # by a day before deciding a file is outside the window. See
        # betting_ingest.slate_date_of for the same one-day widening.
        if bi._day_delta(meta["date"], cutoff) < -1:
            continue
        wrap = bi.load_snapshot(meta["path"])
        if not wrap:
            n_unreadable += 1
            continue
        slate = wrap.get("slate_date") or meta["date"]
        kind = wrap.get("kind") or "unknown"
        cap = _stamp(wrap.get("captured_at"))
        s = slates.setdefault(slate, {"slate_date": slate, "open": 0, "close": 0,
                                      "unknown": 0, "first_capture": None,
                                      "last_capture": None})
        s[kind if kind in ("open", "close") else "unknown"] += 1
        if cap:
            iso = cap.replace(microsecond=0).isoformat()
            if s["first_capture"] is None or iso < s["first_capture"]:
                s["first_capture"] = iso
            if s["last_capture"] is None or iso > s["last_capture"]:
                s["last_capture"] = iso
            if kind == "close" and (last_close is None or cap > last_close):
                last_close = cap
            if kind == "open" and (last_open is None or cap > last_open):
                last_open = cap

    rows = [dict(s, clv_gradable=bool(s["close"])) for s in
            sorted(slates.values(), key=lambda r: r["slate_date"])]
    n_with_close = sum(1 for r in rows if r["close"])
    n_missing = len(rows) - n_with_close
    hours_since_close = _hours_between(last_close, now)
    hours_since_open = _hours_between(last_open, now)

    # THE HEARTBEAT SEPARATES TWO REPAIRS THAT USED TO SHARE ONE SENTENCE.
    # "the close cron is either not installed or is running in the wrong
    # timezone window" names two very different jobs of work, and nothing on
    # disk could tell them apart: a job that runs 96 times a day and correctly
    # no-ops 95 of them leaves no trace until the night it fires. So the job now
    # stamps .cache/betting/close_job_heartbeat.json on every invocation, and
    # this reads it. Absent means the scheduler is not reaching the job at all;
    # present but never firing means the job runs and its window never opens,
    # which is a different bug in a different file.
    hb, hb_age_h = None, None
    try:
        hb = json.loads(CLOSE_HEARTBEAT_PATH.read_text(encoding="utf-8"))
        hb_age_h = _hours_between(_stamp(hb.get("last_run_utc")), now)
    except Exception:
        hb = None

    if not rows:
        diagnosis = ("no odds snapshot of any kind is cached in the window, so the "
                     "open pull is not running either: check EEPHUS_ODDS_API_KEY is "
                     "visible to the pipeline and that run_monthly step 9e reached "
                     "betting_ingest.run")
    elif n_with_close == 0 and hb is None:
        diagnosis = ("no close snapshot has ever been captured AND the close job "
                     "has never run on this machine (no heartbeat at "
                     ".cache/betting/close_job_heartbeat.json), so the scheduler "
                     "is not reaching it: install the entry from "
                     "deploy/betting-crontab.example with `crontab -e` on the box, "
                     "then confirm with `python tools/betting_close_job.py --why`. "
                     "CLV is unrecoverable for every slate above")
    elif n_with_close == 0 and hb_age_h is not None and hb_age_h > 24:
        diagnosis = (f"no close snapshot has ever been captured and the close job "
                     f"last ran {hb_age_h:.1f} hours ago, so its schedule has "
                     f"stopped rather than never started: check the cron entry is "
                     f"still installed and that the box has not been asleep. CLV is "
                     f"unrecoverable for every slate above")
    elif n_with_close == 0:
        diagnosis = ("no close snapshot has ever been captured even though the close "
                     "job IS running (last seen "
                     f"{hb.get('last_run_utc')}, last decision: "
                     f"{hb.get('reason')!r}), so this is not a scheduling problem: "
                     "its firing window is never opening. Read that decision, then "
                     "`python tools/betting_close_job.py --why` on the box. CLV is "
                     "unrecoverable for every slate above")
    elif hours_since_close is not None and hours_since_close > CLOSE_STALE_HOURS:
        diagnosis = (f"the newest close snapshot is {hours_since_close:.1f} hours old and "
                     f"{n_missing} slate(s) in the window have none; CLV for those is "
                     "unrecoverable. Re-install the close cron entry from "
                     "deploy/betting-crontab.example (TZ=UTC, every 15 minutes, all day) "
                     "and check `tools/betting_close_job.py --why` on the box")
    elif n_missing:
        diagnosis = (f"{n_missing} of {len(rows)} slate(s) in the window carry an open "
                     "snapshot and no close; those are ungradeable for CLV. Check "
                     "logs/betting-close.log for the STALE SLATE and unreadable-snapshot "
                     "exits, which are the two the job reports non-zero")
    else:
        diagnosis = (f"every one of the {len(rows)} slate(s) in the window carries a close "
                     "snapshot; CLV is gradeable throughout")

    return {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "window_days": int(days),
        # `_public_path`, not str(): this block is published verbatim as
        # status.feed_health on both payload files, and the absolute form of the
        # odds cache dir carried the build box's OS username (found 2026-08-16).
        "source": _public_path(bi.CACHE_DIR),
        "n_slates": len(rows),
        "n_slates_with_close": n_with_close,
        "n_slates_missing_close": n_missing,
        "n_unreadable_files": n_unreadable,
        "ever_captured_close": bool(n_with_close),
        "hours_since_last_close": hours_since_close,
        "hours_since_last_open": hours_since_open,
        "close_stale_hours": CLOSE_STALE_HOURS,
        # Proof of life for the job itself, so a reader can tell "not scheduled"
        # from "scheduled and never firing" without shelling onto the box.
        "close_job_last_run": (hb or {}).get("last_run_utc"),
        "close_job_last_reason": (hb or {}).get("reason"),
        "close_job_hours_since_run": hb_age_h,
        "close_job_ever_ran": hb is not None,
        "red": bool(n_with_close == 0 or n_missing or
                    (hours_since_close is not None and hours_since_close > CLOSE_STALE_HOURS)),
        "slates": rows,
        "diagnosis": diagnosis,
        "why_not_a_heartbeat": ("data/job_heartbeat.json is git-tracked and "
                                "deploy/nightly-build.sh reverts it before every "
                                "pipeline, so a close-job heartbeat cannot survive to "
                                "be read; this is measured off .cache/odds/ instead"),
    }


# ===========================================================================
# THE PROVISIONAL LABEL AND THE PUBLISH BLOCKERS
# ===========================================================================
REGISTRY_PATH = DATA_DIR / "model_registry.json"


def model_verdict(evald: dict | None, *, registry: dict | None = None) -> dict:
    """The ONE place the model's two verdict words come from.

    Until 2026-08-16 three surfaces each derived their own copy: status.model
    hardcoded its enum in build(), the record label hardcoded "unvalidated" in
    its sentence, and the registry's verdict ("provisional", a different word
    answering a different question) reached the page not at all. Three
    derivations of one state is how a page comes to disagree with itself, so
    every surface now reads this function.

    Two words, deliberately kept apart because they measure different things:
      * gate_state comes from the EVAL ARTIFACT's gates, exactly the derivation
        build() used: "validated" only when the artifact says validated AND a
        measured min_edge exists. "All gates open" with a null min_edge is a
        contradiction, resolved the safe way.
      * registry_verdict is data/model_registry.json's word for the
        betting_game_prob row (its enum: validated / provisional / unvalidated /
        deprecated). "Provisional" there means measured and short of its sample
        gate, not working.

    `registry` is an injection seam for tests; the default reads the file. A
    missing file or row degrades to None rather than to a guessed word."""
    evald = evald or {}
    gate_state = ("validated"
                  if bool(evald.get("validated")) and evald.get("min_edge") is not None
                  else "unvalidated")

    if registry is None:
        try:
            registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            registry = {}
    row = next((m for m in (registry or {}).get("models") or []
                if isinstance(m, dict) and m.get("model_id") == "betting_game_prob"),
               None)
    registry_verdict = (row or {}).get("verdict")

    if gate_state == "validated":
        gate_half = ("the eval artifact's gates are open and a minimum edge "
                     "is measured, so the served state is validated")
    else:
        gate_half = ("the eval artifact's gates are closed and no minimum edge "
                     "is measured, so the served state is unvalidated")
    if registry_verdict is None:
        reg_half = ("the model registry carries no verdict for betting_game_prob, "
                    "so no second word is shown")
    else:
        reg_half = (f"the model registry's verdict is \"{registry_verdict}\""
                    + (", which there means measured but short of its sample "
                       "gate, not working" if registry_verdict == "provisional" else ""))
    return {
        "gate_state": gate_state,
        "registry_verdict": registry_verdict,
        "sentence": f"{gate_half}; {reg_half}.",
    }


def honest_backtest_progress(evald: dict | None) -> dict:
    """(graded, needed) for the honest backtest, READ FROM THE ARTIFACT.

    Neither number may be hardcoded. `n` moves every night the vintage snapshot
    runs, and a label carrying a frozen count is a false claim about how much
    evidence exists the moment the next vintage lands."""
    evald = evald or {}
    vint = evald.get("vintage") or {}
    gate = evald.get("min_edge_gate") or {}
    graded = vint.get("n_graded")
    needed = vint.get("min_graded_games_for_min_edge")
    if graded is None or needed is None:
        for g in gate.get("gates") or []:
            if g.get("id") == "vintage_sample":
                if graded is None:
                    graded = g.get("have")
                if needed is None:
                    # "600 vintage-graded games" -> 600. Read, never assumed.
                    tok = str(g.get("need") or "").split()
                    needed = next((int(t) for t in tok if t.isdigit()), None)
    return {"n_graded": graded, "n_needed": needed,
            "source": "data/betting_model_eval.json vintage block"}


def provisional_record_label(evald: dict | None, *, min_edge: float,
                             provisional: bool) -> str | None:
    """The sentence that rides on the row AND on the record header.

    It is one string in one place so the two surfaces cannot drift, and the
    counts inside it come out of the eval artifact on every build."""
    if not provisional:
        return None
    prog = honest_backtest_progress(evald)
    n, need = prog["n_graded"], prog["n_needed"]
    if n is None or need is None:
        got = ("the eval artifact does not report how many games the honest backtest "
               "has graded")
    else:
        got = f"{n} of the {need} games the honest backtest needs are graded"
    # The verdict word comes from model_verdict, the same function status.model
    # reads, so the label and the status chip cannot drift apart. Today that
    # word is "unvalidated". "Selection", not the pick noun: this label only
    # exists while provisional is true, which is exactly the gates-closed state
    # the 2026-08-16 ruling covers.
    state = model_verdict(evald)["gate_state"]
    return (f"Provisional. This selection clears a {min_edge:.1%} floor that was chosen "
            f"as policy, not measured. The model is {state}: {got}, and no "
            "minimum-edge threshold exists. This row is in the public record because "
            "a claim that is not written down before the result is not a claim.")


def record_publish_blockers(*, payload: dict | None = None,
                            rows: list[dict] | None = None,
                            evald: dict | None = None,
                            health: dict | None = None,
                            settlement: dict | None = None,
                            published_chain_sha: str | None = None,
                            chain_anchor: dict | None = None,
                            now: datetime | None = None) -> list[dict]:
    """EVERY condition a pick must clear before it enters the PUBLIC record.

    Pre-registered on purpose, and shipped in the payload whether it passes or
    not: the list is a claim about what the site refuses to publish, and a
    reader can only hold it to that if he can see it before the first row
    exists. All five are returned with an `open` flag; publishing needs all
    five open, and `record_publish_ok` is that conjunction.

    THE FIVE:
      close_snapshot     a close capture exists for this slate. Without it the
                         pick can never be CLV-graded, and CLV is the only
                         honest read on an unvalidated model's decisions.
      odds_slate         the board is priced against ITS OWN slate. A pick
                         taken off another slate's snapshot is not a pick.
      dispersion_gate    betting_model's dispersion gate has RUN. Not passed:
                         run. An unrun gate means nobody knows which margin
                         model the published probability came from.
      record_storage     the authoritative record is the untracked JSONL and
                         its chain extends the last published hash. This is
                         the go-live blocker, and BOTH halves of it are real:
                         on the JSON alone the row lives only under data/,
                         which no backup covers and which a `git add -A` could
                         re-track into the checkout defect that deleted it
                         before; and without a DURABLE anchor for the last
                         published hash the chain half passes by construction,
                         because `chain_extends(None, rows)` is True. The
                         anchor is `.cache/betting/published_chain.json` - it
                         used to be read out of the git-tracked
                         data/betting.json, which the nightly checkout reverted
                         to a committed copy carrying no chain_sha at all.
      settlement_current every row older than SETTLE_STALE_HOURS has a
                         settlement entry, or the reason it does not is named.
    """
    now = now or datetime.now(timezone.utc)
    payload = payload or {}
    rows = rows if rows is not None else load_record()
    health = snapshot_health() if health is None else health
    settlement = load_settlement() if settlement is None else settlement
    status = payload.get("status") or {}
    slate = payload.get("slate_date")
    # The verdict word in the prose below comes from the one function every
    # surface reads, not from a copy of it here. The noun follows the
    # 2026-08-16 Model Watch ruling: "selection" while the gates are closed,
    # "pick" once resolve_min_edge reports a measured threshold.
    verdict_state = model_verdict(evald)["gate_state"]
    noun = _selection_noun(resolve_min_edge(evald)[2])

    out: list[dict] = []

    snap = bi.closing_snapshot(slate) if slate else None
    out.append({
        "id": "close_snapshot", "open": bool(snap),
        "need": f"a close odds snapshot for slate {slate}",
        "have": ((snap or {}).get("captured_at") if snap else
                 f"{health.get('n_slates_with_close')} of {health.get('n_slates')} "
                 f"slates in the last {health.get('window_days')} days have one"),
        "reason": (f"a close snapshot exists, so this {noun} can be CLV-graded"
                   if snap else
                   f"no close snapshot for this slate, so the {noun} could never be "
                   f"CLV-graded and the only honest read on an {verdict_state} model's "
                   "decisions would be missing. " + str(health.get("diagnosis") or "")),
    })

    mismatch = bool(status.get("odds_slate_mismatch"))
    out.append({
        "id": "odds_slate", "open": not mismatch,
        "need": "the board priced against its own slate's snapshot",
        "have": (status.get("odds_slate") or {}).get("reason") if mismatch else "matched",
        "reason": ("the snapshot the board was priced from belongs to this slate"
                   if not mismatch else
                   f"the cached snapshot cannot price this board's slate; a {noun} "
                   f"against another slate's prices is worse than no {noun}"),
    })

    disp = ((evald or {}).get("run_dispersion") or {})
    disp_ran = disp.get("status") == "ran"
    out.append({
        "id": "dispersion_gate", "open": bool(disp_ran),
        "need": "betting_model's run-dispersion gate to have RUN (not to have passed)",
        "have": disp.get("status") or "never run",
        "reason": (f"the dispersion gate ran on {disp.get('n_eval_games')} held-out "
                   f"games and reported passed={disp.get('passed')}, so the margin "
                   "model behind the published probability is known"
                   if disp_ran else
                   "the dispersion gate has not run, so nobody knows whether the "
                   "published probability came from the Poisson or the negative "
                   "binomial margin model"),
    })

    store = record_storage()
    chain_ok = chain_extends(published_chain_sha, rows)
    # THE VACUOUS PASS, FAIL-CLOSED (found 2026-08-16). With no durable anchor
    # the previous chain value used to be read off the git-tracked betting.json,
    # whose committed chain_sha is genesis, so `chain_extends(None, rows)`
    # returned True by construction on every production build and the rewrite
    # half of this blocker was disarmed while reporting itself open. A
    # None-or-genesis previous value over a NON-EMPTY record is only trustable
    # when the durable anchor itself asserted it; anything else closes the
    # blocker with the reason named. An empty record keeps the old behaviour,
    # because genesis is legitimate when there is nothing to protect yet.
    anchor_closed = None
    if rows and (not published_chain_sha or published_chain_sha == CHAIN_GENESIS):
        anchor = chain_anchor if chain_anchor is not None else read_published_chain()
        anchor_closed = chain_anchor_closed_reason(anchor, rows)
    store_open = bool(store["durable"] and chain_ok and not anchor_closed)
    out.append({
        "id": "record_storage", "open": store_open,
        "need": ("the append-only JSONL under .cache/betting/ to be authoritative, "
                 "and its chain to extend the last published chain_sha"),
        "have": {"backend": store["backend"], "chain_sha": store["chain_sha"],
                 "published_chain_sha": published_chain_sha,
                 "chain_extends": chain_ok,
                 "chain_check_armed": not anchor_closed},
        "reason": (store["why"] if not store["durable"] else
                   (anchor_closed if anchor_closed else
                    ("the record is the untracked append-only log and its chain extends "
                     "the last published value"
                     if chain_ok else
                     f"the last published chain_sha {str(published_chain_sha)[:12]}... is "
                     "not a prefix hash of the current record; something rewrote history "
                     "rather than appending to it"))),
    })

    stale = []
    for r in rows:
        if (r.get("bet_id") or "") in settlement and settlement[r["bet_id"]].get("settled"):
            continue
        posted = _stamp(r.get("posted_at"))
        age = _hours_between(posted, now)
        if age is not None and age > SETTLE_STALE_HOURS:
            entry = settlement.get(r.get("bet_id")) or {}
            stale.append({"bet_id": r.get("bet_id"), "age_hours": age,
                          "why_not": entry.get("reason") or "no settlement entry at all"})
    named = [s for s in stale if s["why_not"] != "no settlement entry at all"]
    unnamed = [s for s in stale if s["why_not"] == "no settlement entry at all"]
    out.append({
        "id": "settlement_current", "open": not unnamed,
        "need": (f"every record row older than {SETTLE_STALE_HOURS:.0f}h settled, or the "
                 "reason it is not settled named on the sidecar"),
        "have": {"n_rows": len(rows), "n_stale": len(stale),
                 "n_stale_named": len(named), "n_stale_unnamed": len(unnamed)},
        "reason": ("every row past the settlement deadline is graded or carries a named "
                   "reason it is not"
                   if not unnamed else
                   f"{len(unnamed)} row(s) are past {SETTLE_STALE_HOURS:.0f}h with no "
                   "settlement entry at all; the record would report fewer results than "
                   "it has and the ROI on the page would be wrong"),
        "stale": sorted(stale, key=lambda s: -(s["age_hours"] or 0))[:10],
    })
    return out


def record_publish_ok(blockers: list[dict]) -> bool:
    """Publishing needs EVERY blocker open. One conjunction, one place."""
    return bool(blockers) and all(b.get("open") for b in blockers)


def record_row(slot_row: dict, *, slate_date: str, evald: dict | None,
               posted_at: str | None = None) -> dict:
    """One published slot -> one record row, with MACHINE FIELDS.

    `selection` is display copy from here on and nothing parses it. `market` is
    the ODDS-FEED key so the CLV grader matches; `board_market` is the board key
    so betting_settle grades the same bet; `side` and `point` are the machine
    pair both of them actually branch on. That triple is the whole of D8: a
    runline row used to carry the label "TBR +1.5" into a grader that compared
    it against org codes, so spreads could never be graded at all.

    `bet_id` is a hash of the bet's identity, NOT of its price, so the same side
    of the same game cannot enter the record twice under two ids if a rebuild
    re-reads a moved line."""
    bm_key = slot_row.get("market")
    point = slot_row.get("point")
    return {
        "bet_id": bet_id(slate_date, slot_row.get("game_pk"), bm_key,
                         slot_row.get("side"), point),
        "posted_at": posted_at or _now(),
        "slate_date": slate_date,
        "game_pk": slot_row.get("game_pk"),
        "matchup": slot_row.get("matchup"),
        "start": slot_row.get("start"),
        # THE TWO VOCABULARIES, BOTH ON THE ROW. See BOARD_TO_FEED_MARKET.
        "market": BOARD_TO_FEED_MARKET.get(bm_key, bm_key),
        "board_market": bm_key,
        "side": slot_row.get("side"),
        "point": point,
        # DISPLAY ONLY. Never parsed when `side` is present.
        "selection": slot_row.get("label"),
        "book": slot_row.get("book"),
        "book_title": slot_row.get("book_title"),
        "odds_at_post": slot_row.get("odds"),
        "decimal": slot_row.get("decimal"),
        "stake_units": STAKE_UNITS,
        "slot": slot_row.get("slot"),
        "edge": slot_row.get("edge"),
        "model_prob": slot_row.get("model_prob"),
        "market_fair_prob": slot_row.get("market_fair_prob"),
        "ev_per_unit": slot_row.get("ev_per_unit"),
        "min_edge_used": slot_row.get("min_edge_used"),
        "provisional": bool(slot_row.get("provisional")),
        "model_version": bm.MODEL_VERSION,
        "label": provisional_record_label(
            evald, min_edge=float(slot_row.get("min_edge_used") or PROVISIONAL_MIN_EDGE),
            provisional=bool(slot_row.get("provisional"))),
    }
    # NOTE: no `result`, no `beat_close`, no `clv_pct`. Those arrive hours later
    # and live in the two sidecars; putting a placeholder here would invite the
    # in-place edit `check_append_only` exists to forbid.


def maybe_publish_record(payload: dict, *, evald: dict | None = None,
                         health: dict | None = None,
                         settlement: dict | None = None,
                         published_chain_sha: str | None = None,
                         chain_anchor: dict | None = None,
                         write: bool = True, now: datetime | None = None,
                         log_fn=None) -> dict:
    """Evaluate the blockers and, ONLY if every one is open, append this slate's
    published slots to the record.

    THE FIRST ROW IS WRITTEN BY THE FIRST NIGHTLY THAT CLEARS EVERY BLOCKER.
    Nothing here is armed by a flag or a date; the machinery is live and the
    blocker list is the authority. That is deliberate: a human deciding when the
    record starts is a human deciding which slate looked good enough to start
    it on.

    Idempotent per (slate, game, market, side, point) through `bet_id`, so a
    rebuild of the same slate re-proposes the same rows and
    `check_append_only` sees nothing new."""
    rows = load_record()
    blockers = record_publish_blockers(
        payload=payload, rows=rows, evald=evald, health=health,
        settlement=settlement, published_chain_sha=published_chain_sha,
        chain_anchor=chain_anchor, now=now)
    slate = payload.get("slate_date")
    slots = [payload.get(k) for k in ("pick_of_the_day", "longshot_of_the_day")]
    cands = [record_row(s, slate_date=slate, evald=evald) for s in slots if s]
    seen = {r.get("bet_id") for r in rows}
    fresh = [c for c in cands if c["bet_id"] not in seen]

    state = {
        "blockers": blockers,
        "n_blockers": len(blockers),
        "n_closed": sum(1 for b in blockers if not b.get("open")),
        "closed": [b["id"] for b in blockers if not b.get("open")],
        "ok": record_publish_ok(blockers),
        "n_candidates": len(cands),
        "n_new": len(fresh),
        "written": 0,
        # The noun follows the 2026-08-16 ruling and lifts with the gates.
        "policy": (f"a {_selection_noun(resolve_min_edge(evald)[2])} enters the "
                   "public record only when every blocker is open; the first row "
                   "is written by the first nightly that clears all of them, and "
                   "nothing else arms it"),
    }
    if not state["ok"]:
        state["reason"] = ("blocked: " + "; ".join(
            f"{b['id']} ({b['reason']})" for b in blockers if not b.get("open")))
        return state
    if not fresh:
        state["reason"] = ("every blocker is open and this slate's published slots are "
                           "already on the record" if cands else
                           "every blocker is open and no slot was published on this slate")
        return state
    if not write:
        state["reason"] = f"every blocker is open; {len(fresh)} row(s) would be appended"
        return state
    append_record(fresh)
    state["written"] = len(fresh)
    state["reason"] = f"appended {len(fresh)} row(s) to the public record"
    if log_fn:
        log_fn(f"betting_export: PUBLIC RECORD +{len(fresh)} row(s) for {slate} "
               f"(chain {chain_sha(rows + fresh)[:12]})")
    return state


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


#: THE POINT WHERE A CARD STOPS BEING A BOARD. A policy constant, not a
#: measurement, and it is named as one for the same reason PROVISIONAL_MIN_EDGE
#: is: it is the share of a date's card that must still be ahead of you for the
#: date to be worth pricing, and nothing in this repo can derive it. Half is the
#: reading that "most of this card is still to come" stops being true.
SLATE_OPEN_MIN_PREGAME_SHARE = 0.5


def _slate_is_open(day: str, games: list[dict], now: datetime | None = None,
                   counts: dict | None = None) -> tuple[bool, str | None]:
    """Is MOST of this calendar date's card still ahead of us, judged on the
    UNFILTERED rows?

    `slate_games` asks "which rows can be bet" and answers it row by row. That is
    the right question for the close job and the wrong one for the board, because
    a date whose card is nine tenths played still has a bettable row on it and
    still wins `min(date)`. Measured on the 2026-08-08 local build: the board
    priced ONE game of fifteen and said nothing about the other fourteen.

    THE FIRST FIX OVERSHOT, AND IT OVERSHOT ON THE SAME QUANTITY. This returned
    False on `n_started >= 1`, so a Sunday card died at 1:05pm with NINE of its
    eleven games still pregame and four of them at night, and the board rolled to
    tomorrow, whose lines the books had not posted yet. One of fifteen left is a
    fragment; nine of eleven left is a board. A count of started games cannot
    tell those apart, because the thing that separates them is a PROPORTION.

    So the date is open while at least `SLATE_OPEN_MIN_PREGAME_SHARE` of its card
    is still pregame. A game counts as started on either of two signals:
      * a row in SLATE_STARTED_STATES: the card is under way or over,
      * a first pitch at or before `now`: the same fact read off the clock rather
        than off StatsAPI, which catches a schedule block refreshed before a game
        started and not since.

    `counts` is filled in with the two numbers behind the verdict so the served
    candidate row shows the call rather than asserting it.

    Returns (open, why_not). `why_not` is None exactly when open is True."""
    now = now or datetime.now(timezone.utc)
    rows = [g for g in (games or []) if g.get("date") == day]
    if counts is not None:
        counts.update(n_started=0, n_pregame=0, pregame_share=None)
    if not rows:
        return False, f"{day} carries no games on the schedule"
    n_started = 0
    for g in rows:
        st = str(g.get("status") or "").strip().lower()
        t = _stamp(g.get("datetime"))
        if st in SLATE_STARTED_STATES or (t is not None and t <= now):
            n_started += 1
    n_pre = len(rows) - n_started
    share = n_pre / len(rows)
    if counts is not None:
        counts.update(n_started=n_started, n_pregame=n_pre,
                      pregame_share=round(share, 4))
    if share < SLATE_OPEN_MIN_PREGAME_SHARE:
        return False, (f"{day} holds {len(rows)} game(s), {n_started} have already "
                       f"started or finished and {n_pre} are still to come, so less "
                       f"than half of the card is left and what remains is a fragment "
                       f"rather than a board")
    return True, None


def resolve_slate(on_date: str | None = None, *, now: datetime | None = None,
                  stats: dict | None = None) -> tuple[str | None, list[dict]]:
    """(slate date, bettable rows) for the board, and the audit trail behind it.

    THE DEFECT THIS CLOSES. `build` took whatever `slate_games` returned, which
    is `min(date)` over the bettable rows, so ONE straggler Preview game on a
    date whose card is otherwise finished wins the whole board. The 2026-08-08
    local build priced 1 game of 15 and the payload carried no field that said
    so: `n_slate_games` read 1, which is indistinguishable from a one-game
    Monday.

    THE WALK. Candidate dates in order; the first one that is still whole wins.
    A date that has started is skipped WITH ITS REASON RECORDED, so the choice
    can be argued with instead of inferred. If no date is whole the old
    behaviour stands - the earliest date with a bettable game - and `stats`
    carries `partial_slate` naming what the board is a fragment of, because a
    fragment that says so is worth more than an empty page.

    `slate_games` IS DELIBERATELY NOT CHANGED. tools/betting_close_job.py calls
    it with no date and takes `min(date)` over the result to decide which slate
    to capture a closing line for. Rolling that forward to tomorrow whenever
    tonight has a game in progress would make `decide()` report "the next
    bettable slate is tomorrow" and never fire, and a missed close is CLV that
    cannot be recovered afterwards. The two callers are asking different
    questions - "what can still be bet" against "what is a whole board" - which
    is the same split `is_bettable` and `anchors_close_window` already carry."""
    now = now or datetime.now(timezone.utc)
    if stats is None:
        stats = {}
    if on_date:
        stats["slate_rule"] = "explicit_date"
        stats["slate_candidates"] = []
        stats["partial_slate"] = None
        return on_date, slate_games(on_date)

    fan = _load("fantasy.json") or {}
    allg = ((fan.get("schedule") or {}).get("games")) or []
    days = sorted({g["date"] for g in allg if g.get("date")})
    cands, chosen, rule = [], None, None
    for day in days:
        rows = [g for g in allg if g.get("date") == day]
        bettable = [g for g in rows if is_bettable(g)]
        counts: dict = {}
        is_open, why_not = _slate_is_open(day, allg, now, counts=counts)
        cands.append({"date": day, "n_games": len(rows),
                      "n_bettable": len(bettable), "open": is_open,
                      "n_started": counts.get("n_started"),
                      "n_pregame": counts.get("n_pregame"),
                      "pregame_share": counts.get("pregame_share"),
                      "min_pregame_share": SLATE_OPEN_MIN_PREGAME_SHARE,
                      "why_not": why_not})
        # An open date with nothing bettable on it is every game postponed. It
        # is open and it is not a board, so the walk keeps going.
        if is_open and bettable and chosen is None:
            chosen, rule = day, "first_open_slate"

    stats["slate_candidates"] = cands
    stats["partial_slate"] = None
    if chosen is None:
        dated = [g for g in allg if is_bettable(g) and g.get("date")]
        if dated:
            chosen, rule = min(g["date"] for g in dated), "earliest_bettable_partial"
            row = next((c for c in cands if c["date"] == chosen), {})
            stats["partial_slate"] = {
                "slate_date": chosen,
                "n_games_on_date": row.get("n_games"),
                "n_bettable": row.get("n_bettable"),
                "reason": (f"no date on the schedule is still a whole card, so the board "
                           f"is the earliest date with a bettable game. {row.get('why_not')}"),
            }
    stats["slate_rule"] = rule
    if chosen is None:
        return None, []
    return chosen, [g for g in allg if g.get("date") == chosen and is_bettable(g)]


def _event_slate_date(ev: dict) -> str | None:
    """The US slate an odds event belongs to, on betting_ingest.slate_date_of's
    fixed EDT offset. Same convention on purpose: a board slate and a snapshot
    slate compared under two different rules would disagree at midnight."""
    t = _stamp((ev or {}).get("commence_time"))
    return None if t is None else (t - timedelta(hours=4)).strftime("%Y-%m-%d")


def resolve_snapshot(slate: str | None, *, now: datetime | None = None
                     ) -> tuple[dict | None, list[dict], dict]:
    """The odds snapshot FOR THIS BOARD SLATE, plus what it took to get one.

    THE DEFECT THIS CLOSES. `build` called `bi.latest_snapshot()` with no filter
    and joined whatever came back to whatever slate the board had resolved to.
    Nothing compared the two. When the morning ingest fails, the newest cached
    snapshot is last night's and tonight's board is priced off it; the only thing
    on the page that changes is a timestamp, which reads as a timestamp and not
    as a warning.

    THREE OUTCOMES, and the second is the ordinary one:
      * `slate_label`: a cached snapshot's own `slate_date` is this board's
        slate. Nothing more to check.
      * `carries_slate_events`: no snapshot is LABELLED with this slate, but the
        newest one lists games on it that have not started. That is not a defect,
        it is how the feed works: a capture is labelled by its EARLIEST event, so
        an evening capture is stamped today while carrying tomorrow's card, and a
        board that has rolled forward to tomorrow can never match a label. The
        prices are the market at capture time and are legitimate.
      * `mismatch`: the snapshot lists NO pregame game on the board slate, so
        there is no market for this board at all. Both slots are emptied and the
        reason is named. A pick against yesterday's prices is worse than no pick.

    WHAT THIS DOES NOT CATCH, stated because a reader is entitled to it: a
    snapshot that carries tonight's games but was captured many hours ago passes
    `carries_slate_events` while every price on it is old. The honest test for
    that is capture age, and the four captures in .cache/odds are 31.2, 27.1 and
    16.8 hours apart, which is a development box's cadence and not a number a
    production threshold can be derived from. `snapshot_age_hours` is published
    instead of being gated on."""
    now = now or datetime.now(timezone.utc)
    state = {"board_slate": slate, "snapshot_slate": None,
             "snapshot_captured_at": None, "snapshot_age_hours": None,
             "matched": False, "match_rule": None,
             "n_pregame_events_on_board_slate": 0, "mismatch": False, "reason": None}
    snap = bi.latest_snapshot(on_date=slate) if slate else None
    labelled = snap is not None
    if snap is None:
        snap = bi.latest_snapshot()
    if snap is None:
        state["reason"] = "no odds snapshot is cached, so there is nothing to price against"
        return None, [], state

    events = bi.parse_events(snap)
    state["snapshot_slate"] = snap.get("slate_date")
    state["snapshot_captured_at"] = snap.get("captured_at")
    state["snapshot_age_hours"] = _hours_since(snap.get("captured_at"))
    n_pre = 0
    for e in events:
        t = _stamp(e.get("commence_time"))
        if slate and _event_slate_date(e) == slate and t is not None and t > now:
            n_pre += 1
    state["n_pregame_events_on_board_slate"] = n_pre

    if labelled:
        state.update(matched=True, match_rule="slate_label")
        state["reason"] = f"the cached snapshot is stamped for the {slate} slate"
    elif slate and n_pre:
        state.update(matched=True, match_rule="carries_slate_events")
        state["reason"] = (f"the newest snapshot is stamped for the "
                           f"{state['snapshot_slate']} slate and carries {n_pre} game(s) "
                           f"on the {slate} board that have not started; a capture is "
                           f"labelled by its earliest event, so this is the normal shape "
                           f"of an evening board")
    else:
        state["mismatch"] = True
        state["reason"] = (
            f"ODDS SLATE MISMATCH: the board is the {slate} slate and the newest cached "
            f"snapshot is stamped {state['snapshot_slate']}, captured "
            f"{state['snapshot_captured_at']}, and carries no game on the board slate that "
            f"has not already started. Every price below is for a different slate, so no "
            f"pick is published against it")
    return snap, events, state


def _consensus_point(event: dict, market: str, sides: tuple):
    """The line the market agrees on, or None for a market that carries no point.

    WHY THIS IS NEEDED (2026-08-06). Books do not all post the same runline
    side. Measured on a live snapshot for NYM at CLE: eight books had the home
    side at -1.5, and FanDuel had it at +1.5. Shopping each side for its best
    price independently then fused Bovada's -1.5 line with FanDuel's price for
    the OTHER line, and the row that came out paired a model probability for
    "NYM +1.5" (0.7255) with a price whose implied probability was 0.3521. That
    is a 38.8 point edge conjured out of a line mismatch, and it was the highest
    "edge" on the board.

    Totals have the same exposure: Over 8.5 at one book and Under 9.5 at another
    are not two sides of one bet.

    So the line is decided FIRST, by book count, and prices are shopped only
    among books posting it. Ties break toward the numerically lower point, which
    is arbitrary but deterministic, and any tie here means the market is
    genuinely split and the row is thin evidence either way."""
    from collections import Counter
    key = sides[0]
    pts = Counter()
    for b in (event.get("books") or {}).values():
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        cell = m.get(key)
        pt = cell.get("point") if isinstance(cell, dict) else None
        if pt is not None:
            pts[float(pt)] += 1
    if not pts:
        return None
    top = max(pts.values())
    return min(p for p, n in pts.items() if n == top)


def _best_price_on_line(event: dict, market: str, side: str, want):
    """Best price for one side, restricted to books posting `want` for it.

    `want` is None for a pointless market (h2h), which reduces this to the
    plain best price."""
    best = None
    for bkey, b in (event.get("books") or {}).items():
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        cell = m.get(side)
        if cell is None:
            continue
        price = cell.get("price") if isinstance(cell, dict) else cell
        pt = cell.get("point") if isinstance(cell, dict) else None
        if want is not None:
            if pt is None or abs(float(pt) - float(want)) > 1e-9:
                continue
        dec = bi.american_to_decimal(price)
        if dec is None:
            continue
        if best is None or dec > best["decimal"]:
            best = {"book": bkey, "book_title": b.get("title"), "price": price,
                    "decimal": round(dec, 4), "point": pt,
                    "last_update": b.get("last_update")}
    return best


def _market_view(event: dict | None, market: str, sides: tuple) -> dict | None:
    """Best price per side + the de-vigged fair probabilities for one market.

    Both sides are read off ONE agreed line; see _consensus_point for the
    mismatch that made this necessary.

    De-vigging uses a SINGLE book's two-sided market, not a cross-book mash-up:
    mixing books manufactures a fake fair line with a negative hold.

    WHICH book was decided by dict iteration order until 2026-08-09, which is
    API response order. That book sets the denominator of every edge on the
    page. Measured on .cache/odds/2026-08-09-0133.json: h2h hold ranged from
    1.00% to 6.38% inside a single game, and on CHC at KCR the book that
    happened to be first (draftkings, 6.377% hold) gave fair_home 0.9277 while
    the tightest book on the same market (fanduel, 1.000%) gave 0.9505. A 2.28
    point swing in the denominator, decided by nothing, against a 6 point floor.

    So the de-vig book is now the MINIMUM-HOLD book among those posting both
    sides ON THE AGREED LINE, ties broken by book key so the choice is fixed for
    a fixed snapshot. Tight hold is the closest thing a two-way quote gives to
    an efficient price; it is not a claim that the book is right.

    A quote whose hold falls outside DEVIG_HOLD_MIN_PCT..DEVIG_HOLD_MAX_PCT is
    rejected as stale or bogus rather than treated as a market: the same file
    carries betrivers at a 19.010% hold on CIN at WSN totals (Over +400 against
    Under -10000) and a negative hold is an arbitrage, which no single book
    posts on purpose. If every candidate is rejected the block falls back to the
    old first-book choice and says so in `fair_book_rule`.

    A TIGHT HOLD CAN BE A BOOK THAT HAS NOT UPDATED (2026-08-09, second pass).
    Hold measures the two prices against each other and nothing else, so a quote
    frozen before the market moved scores as efficient for free and then sets the
    denominator of every edge in the game. Two guards close that, and they catch
    different failures:
      * STALENESS, `last_update` against the freshest book on the same market.
        The stamp was parsed and carried into `best` all along and was never read
        for this decision. See STALE_BOOK_MAX_LAG_MINUTES.
      * CONSENSUS DISTANCE, this book's de-vigged fair probability against the
        median of the books on the agreed line. A quote can be a second old and
        still price a game nobody else is pricing, which a timestamp cannot see.
        See CONSENSUS_FAIR_MAX_DISTANCE.
    Both thresholds are set above anything either cached snapshot contains on a
    pregame market, so neither rejects a real book on today's board; the
    measurements are on the constants. Each rejection is counted and published,
    because a rule that silently drops a book is a rule a reader cannot check."""
    if not event:
        return None
    line = _consensus_point(event, market, sides)
    # For a two-sided spread the far side carries the mirrored point.
    want = {}
    for i, s in enumerate(sides):
        if line is None:
            want[s] = None
        elif market == "spreads":
            want[s] = line if i == 0 else -line
        else:
            want[s] = line
    best = {s: _best_price_on_line(event, market, s, want[s]) for s in sides}
    if any(b is None for b in best.values()):
        return None
    # Fair probabilities come from ONE book's two-sided market, so the de-vig is
    # arithmetically meaningful. Candidates are collected in snapshot order and
    # the choice is made below on hold, not on arrival.
    cands = []
    for bkey, b in (event.get("books") or {}).items():
        m = b.get(market)
        if not isinstance(m, dict):
            continue
        decs = {}
        off_line = False
        for s in sides:
            cell = m.get(s)
            price = cell.get("price") if isinstance(cell, dict) else cell
            pt = cell.get("point") if isinstance(cell, dict) else None
            # A book on a different line cannot supply the fair probabilities
            # for this one: its two-sided market prices a different bet.
            if want.get(s) is not None and (
                    pt is None or abs(float(pt) - float(want[s])) > 1e-9):
                off_line = True
                break
            d = bi.american_to_decimal(price)
            if d:
                decs[s] = d
        if off_line or len(decs) != len(sides):
            continue
        f = bm.devig(decs)
        cands.append({"book": bkey, "decs": decs, "hold": bm.hold_pct(decs),
                      "stamp": _stamp(b.get("last_update")),
                      "fair0": (f or {}).get(sides[0])})
    if not cands:
        return None
    holds = [c["hold"] for c in cands if c["hold"] is not None]

    # STALENESS, relative to the market and not to the wall clock. The freshest
    # book on THIS market is the reference, so a snapshot taken at any hour is
    # judged against itself.
    stamps = [c["stamp"] for c in cands if c["stamp"] is not None]
    freshest = max(stamps) if stamps else None
    for c in cands:
        c["lag_min"] = (round((freshest - c["stamp"]).total_seconds() / 60.0, 3)
                        if freshest is not None and c["stamp"] is not None else None)

    # CONSENSUS DISTANCE. The median is taken over EVERY candidate on the line,
    # including the wide ones: it is a rank statistic, so one rogue quote cannot
    # drag it, and using the full set keeps n as large as it can be.
    fairs = sorted(c["fair0"] for c in cands if c["fair0"] is not None)
    med = None
    if len(fairs) >= CONSENSUS_MIN_BOOKS:
        n = len(fairs)
        med = fairs[n // 2] if n % 2 else 0.5 * (fairs[n // 2 - 1] + fairs[n // 2])
    for c in cands:
        c["consensus_distance"] = (round(abs(c["fair0"] - med), 5)
                                   if med is not None and c["fair0"] is not None else None)

    # ONE reason per rejected candidate, in a fixed order, so the three counts
    # sum to the number rejected and a reader can add them up.
    def _why_not(c):
        if c["lag_min"] is not None and c["lag_min"] > STALE_BOOK_MAX_LAG_MINUTES:
            return "stale"
        if c["hold"] is None or not (DEVIG_HOLD_MIN_PCT <= c["hold"] <= DEVIG_HOLD_MAX_PCT):
            return "hold"
        if (c["consensus_distance"] is not None
                and c["consensus_distance"] > CONSENSUS_FAIR_MAX_DISTANCE):
            return "consensus"
        return None

    for c in cands:
        c["rejected"] = _why_not(c)
    ok = [c for c in cands if c["rejected"] is None]
    n_rej = Counter(c["rejected"] for c in cands if c["rejected"])
    if ok:
        # (hold, book key): the key is the tiebreak, so two books at an
        # identical hold resolve the same way on every rebuild.
        win = min(ok, key=lambda c: (c["hold"], c["book"]))
        rule = "min_hold"
    else:
        win = cands[0]
        # The historical name is kept for the historical case, so a reader who
        # has seen it before is not told a new rule fired.
        rule = ("first_book_all_holds_rejected"
                if set(n_rej) == {"hold"} else "first_book_all_candidates_rejected")
    fair_book, decs, hold = win["book"], win["decs"], win["hold"]
    fair = bm.devig(decs)
    if not fair:
        return None
    lags = [c["lag_min"] for c in cands if c["lag_min"] is not None]
    return {
        "best": {s: best[s] for s in sides},
        "fair": {s: round(fair[s], 5) for s in sides},
        "fair_book": fair_book,
        "hold_pct": round(hold, 3) if hold is not None else None,
        # The audit trail for the choice above: how many books could have set
        # this denominator, how far apart they were, and how many were refused
        # for each of the three reasons. Before 2026-08-09 the hold count was
        # computed and never published, which made a rejection invisible.
        "fair_book_rule": rule,
        "n_books_on_line": len(cands),
        "n_books_hold_rejected": n_rej.get("hold", 0),
        "n_books_stale_rejected": n_rej.get("stale", 0),
        "n_books_consensus_rejected": n_rej.get("consensus", 0),
        "hold_range": ([round(min(holds), 3), round(max(holds), 3)] if holds else None),
        "max_book_lag_minutes": (max(lags) if lags else None),
        "fair_book_lag_minutes": win.get("lag_min"),
        "fair_book_consensus_distance": win.get("consensus_distance"),
        "devig_method": "proportional",
    }


def _priced_side(side_key: str, label: str, p_model: float, mv: dict | None,
                 *, p_push: float | None = None) -> dict:
    """One bettable side: model probability, market fair probability, edge, EV,
    Kelly. With no market attached, everything market-shaped is None and the
    row is a fair line, which is still worth showing.

    `p_push` IS PART OF THE BET, NOT PART OF THE ODDS (2026-08-09). On a
    whole-number total the book returns the stake when the total lands, and
    `bm.ev_per_unit` is a pure two-argument odds primitive that cannot know
    that: given (p, decimal) it charges a full unit for every outcome that is
    not a win, so it prices a refund as a loss. `p_model` here is already
    CONDITIONAL on no push (betting_model.total_side_probabilities returns the
    conditioned pair), so the honest EV is the conditional EV scaled by the
    chance the bet resolves at all:

        (1 - p_push) * [ p_cond * (decimal - 1) - (1 - p_cond) ]

    The overstatement is exactly 1 / (1 - p_push), which measured 1.140x to
    1.163x on the three whole-number totals of the 2026-08-09 board. That is not
    a display error: `_longshot_rank` and `pick_of_the_day` both select on
    `ev_per_unit`, so a whole number outranked a half point at the same edge and
    a different pick was published.

    The adjustment lands HERE and not inside `bm.ev_per_unit`, which is correct
    as written. Kelly is left alone: `bm.kelly_fraction` is a ratio of the same
    two terms and the (1 - p_push) factor cancels out of it."""
    row = {
        "side": side_key, "label": label,
        "model_prob": round(p_model, 5),
        "fair_odds": bi.decimal_to_american(1.0 / p_model) if p_model > 0 else None,
        # The push mass on THIS side's bet, carried on the row so a slot lifted
        # out of the payload still says how often it is a refund. None on a
        # market that cannot push (a moneyline, a half-point line).
        "p_push": (round(float(p_push), 5) if p_push else None),
        "book": None, "odds": None, "decimal": None,
        "implied_prob": None, "market_fair_prob": None,
        "edge": None, "ev_per_unit": None, "ev_per_unit_if_no_push": None,
        "kelly_full": None,
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
        # `ev_per_unit` is the PUBLISHED number every consumer reads (the two
        # slot rankers, the legacy pick_of_the_day, the board table, the shadow
        # ledger), so the push adjustment goes in it rather than beside it. The
        # unadjusted number ships too, under a name that says what it is, so the
        # arithmetic can be checked without recomputing it.
        ev_no_push = bm.ev_per_unit(p_model, b["decimal"])
        pp = float(p_push) if p_push else 0.0
        row["ev_per_unit_if_no_push"] = round(ev_no_push, 5)
        row["ev_per_unit"] = round((1.0 - pp) * ev_no_push, 5)
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

    THE SINGLE-CANDIDATE SHORTCUT WAS A BYPASS, NOT A TOLERANCE (2026-08-09,
    found replaying .cache/odds/2026-08-09-0133.json). It ran no time check at
    all, and one candidate for an org pair does not mean "this game": a snapshot
    legitimately spans two slate dates (that file holds 11 events on the 8/8
    slate and 12 on 8/9), so it means "the only event for this SERIES in the
    file". Measured on that file: TBR at SEA matched an event 1099 minutes
    (18h19m) from first pitch, and HOU at SDP matched one 1504 minutes (25h04m)
    off that was already 2h17m into play. Both then priced the wrong game.

    The TOLERANCE is kept and is the point: a book posting a start time a few
    minutes off ours must not blank an otherwise healthy row, so the gap may run
    to EVENT_MATCH_MAX_MINUTES. Past that, a single candidate is a different
    game in the same series, not a posted-time disagreement.

    Returns None rather than a guess when nothing matches, which drops the game
    to a model-only fair line. That is the safe direction: an unpriced row is
    visibly unpriced, a mispriced row is not."""
    cands = [c for c in (candidates or []) if c]
    if not cands:
        return None
    if len(cands) == 1 and not game.get("double_header"):
        c = cands[0]
        t0, t = _stamp(game.get("datetime")), _stamp(c.get("commence_time"))
        if t0 is None or t is None:
            # Nothing to compare. One event for the pair is still the ordinary
            # case, and refusing it on a missing stamp would blank healthy rows.
            return c
        delta = abs((t - t0).total_seconds()) / 60.0
        if delta > EVENT_MATCH_MAX_MINUTES:
            log.warning("betting_export: the only odds event for %s @ %s starts %.0f min "
                        "from first pitch (limit %d), so it is a DIFFERENT GAME IN THE "
                        "SAME SERIES and not a posted-time disagreement; leaving the "
                        "game unpriced",
                        (game.get("away") or {}).get("org"), (game.get("home") or {}).get("org"),
                        delta, EVENT_MATCH_MAX_MINUTES)
            return None
        return c
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
              starters=None, now=None, stats=None) -> list[dict]:
    """Every game on the slate: model probabilities, the market when a snapshot
    exists, and the edge between them.

    `now` is injectable so a test can pin the pregame filter below. `stats`, if
    given, is filled with the counts build() publishes under status."""
    teams = teams if teams is not None else bm.team_inputs()
    parks = parks if parks is not None else bm.park_index()
    starters = starters if starters is not None else bm.starter_inputs()
    now = now or datetime.now(timezone.utc)
    # A LIST per org pair, not one event. See `match_event`: a doubleheader puts
    # two events under one key and a dict silently kept the last one parsed.
    #
    # AN EVENT THAT HAS ALREADY STARTED CANNOT PRICE THIS BOARD (2026-08-09).
    # A book keeps a game listed once it is under way, at an IN-GAME price. That
    # price is real; it is just not the bet this page describes, and the model
    # probability beside it is a pregame number. Measured on
    # .cache/odds/2026-08-09-0133.json: FanDuel had HOU +1100 and a total of 4.5
    # on a game 2h17m old, and those three sides came out as the largest edges
    # on the whole board. The filter is separate from `match_event` on purpose:
    # game one of a doubleheader being under way is a genuine two-candidate
    # case, and the time-nearest match would still take the started half.
    n_in_progress = 0
    by_pair: dict[tuple, list] = {}
    for ev in events or []:
        t = _stamp(ev.get("commence_time"))
        if t is not None and t <= now:
            n_in_progress += 1
            log.info("betting_export: odds event %s (%s @ %s) started %.0f min ago; "
                     "its prices are in-game and cannot price a pregame board",
                     ev.get("event_id"), ev.get("away_org"), ev.get("home_org"),
                     (now - t).total_seconds() / 60.0)
            continue
        by_pair.setdefault((ev.get("home_org"), ev.get("away_org")), []).append(ev)

    out = []
    n_time_refused = 0                     # games that had a candidate and lost it
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
        gp.pop("over", None)                   # callable; superseded by total_sides
        sides_fn = gp.pop("total_sides", None)
        cands = by_pair.get((ho, ao)) or []
        ev = match_event(g, cands)
        if cands and ev is None:
            n_time_refused += 1
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
        # The Under is NOT 1 - p_over. On a whole number that hands the Under
        # the push mass; betting_model.total_side_probabilities carries the
        # measurement and returns the push-conditioned pair.
        tot_rows, tot_line, tot_push = None, None, None
        if tot and sides_fn:
            tot_line = ((tot["best"].get("over") or {}).get("point"))
            if tot_line is not None:
                ts = sides_fn(float(tot_line))
                p_over, p_under = ts.get("p_over"), ts.get("p_under")
                tot_push = (round(ts["p_push"], 5) if ts.get("p_push") is not None
                            else None)
                if p_over is not None and p_under is not None:
                    # BOTH sides carry the push into their EV. A refund is not a
                    # loss, and pricing it as one overstated the EV of every
                    # whole-number total by 1 / (1 - p_push); see _priced_side.
                    tot_rows = [
                        _priced_side("over", f"Over {tot_line}", p_over, tot,
                                     p_push=tot_push),
                        _priced_side("under", f"Under {tot_line}", p_under, tot,
                                     p_push=tot_push),
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
            # `p_push` is the model's P(total lands exactly on the line): zero on
            # a half point, and the number the page needs to say a whole number
            # refunds some of the time. The two sides beside it are already
            # conditional on it not happening.
            "total": ({"line": tot_line, "sides": tot_rows, "p_push": tot_push}
                      if tot_rows else
                      {"line": None, "sides": None, "p_push": None,
                       "fair_total": gp["fair_total"]}),
            # WHICH book set the denominator of every edge in this game, how
            # many could have, and how far apart they were. Before 2026-08-09
            # the choice was API response order and none of it was published.
            "market": {"moneyline_hold_pct": (ml or {}).get("hold_pct"),
                       "total_hold_pct": (tot or {}).get("hold_pct"),
                       "moneyline_fair_book": (ml or {}).get("fair_book"),
                       "moneyline_hold_range": (ml or {}).get("hold_range"),
                       "moneyline_n_books_on_line": (ml or {}).get("n_books_on_line"),
                       "total_fair_book": (tot or {}).get("fair_book"),
                       "total_hold_range": (tot or {}).get("hold_range"),
                       "total_n_books_on_line": (tot or {}).get("n_books_on_line"),
                       "runline_fair_book": (rl or {}).get("fair_book"),
                       "runline_hold_pct": (rl or {}).get("hold_pct"),
                       "fair_book_rule": ((ml or {}).get("fair_book_rule")
                                          or (tot or {}).get("fair_book_rule")),
                       # HOW MANY BOOKS THE DE-VIG RULES REFUSED, per market.
                       # `n_books_hold_rejected` was computed from the day the
                       # hold band shipped and published nowhere, so a market
                       # that lost four of its five candidate books looked
                       # identical to one that lost none. A rejection nobody can
                       # see is a rule nobody can check.
                       "n_books_rejected": {
                           m: {"hold": (v or {}).get("n_books_hold_rejected"),
                               "stale": (v or {}).get("n_books_stale_rejected"),
                               "consensus": (v or {}).get("n_books_consensus_rejected"),
                               "on_line": (v or {}).get("n_books_on_line")}
                           for m, v in (("moneyline", ml), ("runline", rl),
                                        ("total", tot)) if v},
                       "max_book_lag_minutes": {
                           m: (v or {}).get("max_book_lag_minutes")
                           for m, v in (("moneyline", ml), ("runline", rl),
                                        ("total", tot)) if v},
                       "stale_book_max_lag_minutes": STALE_BOOK_MAX_LAG_MINUTES,
                       "consensus_fair_max_distance": CONSENSUS_FAIR_MAX_DISTANCE,
                       "devig_method": "proportional"} if ml or tot else None,
        })
    if stats is not None:
        stats["n_events_dropped_in_progress"] = n_in_progress
        stats["n_games_unpriced_time_mismatch"] = n_time_refused
    return out


# ===========================================================================
# props: MODEL FAIR LINES ONLY (free tier has no per-event prop budget)
# ===========================================================================
def _fantasy_index() -> dict:
    """(mlbam, side) -> fantasy projection row, ACTIVE ROSTER ONLY.

    fantasy.json deliberately serves players who are off an active roster and
    FLAGS them, because a rest-of-season board is exactly where a manager needs
    to see that his man is out. A prop is the opposite: you cannot bet a hits
    line on a player who is not on the roster tonight, so a projection carrying
    roster_status "off_roster" must never reach a priced market. 156 of 652
    fantasy rows were in that state on the day this landed.

    "unknown" is KEPT. It means the roster walk was not trustworthy (fewer than
    28 of 30 clubs), and dropping every player on a failed feed would empty the
    props board rather than degrade it.
    """
    fan = _load("fantasy.json") or {}
    by = {}
    n_off = 0
    for p in fan.get("players") or []:
        if p.get("roster_status") == "off_roster":
            n_off += 1
            continue
        by[(p.get("mlbam"), p.get("side"))] = p
    if n_off:
        log.info("props: %d off-roster projection(s) withheld from pricing", n_off)
    return by


# ===========================================================================
# ONE PROBABILITY-MASS SOURCE PER PROP MARKET (2026-09-06)
# ===========================================================================
# WHAT THIS IS: a single pmf per prop market, shared by the fair-lines block
# and the value block, so one page cannot quote two probabilities for one bet.
#
# WHAT IT REPLACED, and the size of the disagreement it removed: `1+ hits` and
# `1+ home runs` were priced in props_fair_lines as `1 - (1 - p) ** exp_pa`
# (a per-PA Bernoulli), while props_value_bets priced the SAME two markets
# through _props_side_probabilities as a Poisson at lam = p * exp_pa. Measured
# 2026-09-06 on a slot-1 hitter (exp_pa 4.65, lam 1.60, per-PA rate 0.34409),
# 1+ hits at the 0.5 line:
#
#     fair-lines Bernoulli   P(over) = 0.85929
#     value-block Poisson    P(over) = 0.79810   gap 0.06118
#     one binomial path      P(over) = 0.85630   (-0.00298 / +0.05820)
#
# and at the 1.5 line the two surfaces had no shared answer at all, because
# the fair-lines path only ever priced 0.5: Poisson 0.47507 against the
# binomial's 0.51338, +0.03831 on the Over. On a whole 2.0 line the push mass
# itself was wrong, 0.25843 Poisson against 0.32413 binomial, and the push is
# what `_priced_side` scales EV by. The Poisson was also assigning 0.00604 of
# mass to MORE THAN 5 HITS IN 4.65 PLATE APPEARANCES, an outcome with no
# sample space. Nothing served moved: zero props rows exist anywhere in the
# tree (the pull is inert without both arming variables), which is exactly why
# the repair is free today.
#
# THE SIZE OF IT ON THE WHOLE POPULATION, not one hand-picked hitter. Binomial
# minus Poisson across all 471 projected hitters in data/fantasy.json at
# DEFAULT_PA 4.20 (2026-09-06): at the 0.5 line, median +0.04179 and a range of
# +0.02922 to +0.05293, always positive because the binomial puts less mass on
# a hitless game; at the 1.5 line, median -0.00658 (range -0.01115 to +0.00491),
# the sign flipping with whether lam sits above or below the line. Across the
# 203 projected starters at a 5.2 inning start, strikeouts move a median
# +0.00396 (range -0.00834 to +0.01896), the smaller move because 22 batters
# faced is close enough to unbounded that the binomial and the Poisson nearly
# agree. `bf` is present on 272 of 272 projected pitchers, so the strikeout
# trial count is measured (4.30 batters per inning at the median), not assumed
# at three per inning.
#
# WHAT IT IS NOT: a fitted model. Nothing here is estimated from outcomes; the
# lambdas still come from the projection engine's rest-of-season rates and the
# only decision made here is which counting distribution carries them. It
# REFUSES to claim the distributions are calibrated: no props row has ever
# settled, so there is no graded evidence that a binomial beats a Poisson on
# this board, only the structural argument stated per market below.

#: The model that prices every props row on this page. Stamped on the row as
#: `model_id`, beside `pmf` (which distribution produced the number), so a
#: later sub-model swap is auditable from the payload alone.
PROPS_MODEL_ID = "betting_props_pmf"

#: prop name -> the distribution that prices it AND the reason it is that one.
#: No blanket Poisson: each market declares, and the reason ships in the
#: payload's method block so a reader can argue with the choice.
#:
#: `trials` names what the count is a sum over. When a row supplies that trial
#: count the binomial markets use it; when it does not, the pmf falls back to
#: Poisson and the row SAYS SO in `pmf_basis` rather than pretending.
PROPS_DISTRIBUTIONS = {
    "Strikeouts": {
        "dist": "binomial", "trials": "expected batters faced",
        # THE DISPERSION HALF OF THIS REASON WAS BACKWARDS AND IS NOW MEASURED.
        # It used to say Poisson "over-disperses" as a reason to reject it.
        # Arithmetically that is true against the binomial, and as a
        # JUSTIFICATION it is the wrong way round: measured on 3,376 starts of
        # 20 or more batters faced, the real strikeout count has a variance of
        # 5.635 against the binomial's 4.025 and Poisson's 5.147. The data
        # over-disperses relative to BOTH, by 1.400x against the binomial and
        # only 1.095x against Poisson, so Poisson's extra variance moves toward
        # the truth rather than away from it.
        #
        # The binomial is still the served choice, and now for a reason that
        # survives measurement: on the line this module actually prices, over
        # 5.5, it beats Poisson by a paired Brier of 0.001045 with a
        # game-clustered interval that excludes zero. It fits the shape worse
        # and prices the line better, and those are different questions.
        # data/betting_props_dark_eval.json carries both legs.
        "reason": "a batter faced is struck out or is not, so the count is a "
                  "sum of Bernoulli trials with support capped at batters "
                  "faced, and Poisson puts mass on more strikeouts than "
                  "batters, which cannot happen. On the served 5.5 line the "
                  "binomial also prices better than Poisson, by a paired Brier "
                  "of 0.001045 with an interval excluding zero. It does NOT fit "
                  "the shape better: the real count over-disperses against the "
                  "binomial by 1.400x and against Poisson by only 1.095x. "
                  "Measured in data/betting_props_dark_eval.json",
    },
    "Hits allowed": {
        "dist": "binomial", "trials": "expected batters faced",
        "reason": "one batter faced yields at most one hit, the same Bernoulli "
                  "argument as strikeouts",
    },
    "Earned runs": {
        "dist": "poisson", "trials": None,
        "reason": "earned runs are not a per-batter indicator: one plate "
                  "appearance can score four. The count is a compound sum with "
                  "no per-trial cap, so the binomial argument does not apply "
                  "and Poisson is the stated approximation. It understates the "
                  "tail of a clumped scoring distribution",
    },
    "Total bases": {
        "dist": "poisson", "trials": None,
        "reason": "total bases per plate appearance take values 0 to 4, so the "
                  "count is a compound sum, not a sum of indicators. A binomial "
                  "would be wrong in the other direction, and the extra-base "
                  "mix a compound distribution needs is not carried on the row. "
                  "Poisson stays, now stated rather than assumed",
    },
    "1+ hits": {
        "dist": "binomial", "trials": "expected plate appearances",
        "reason": "a plate appearance yields at most one hit, so hits over a "
                  "game are binomial over plate appearances. This is the market "
                  "the two surfaces disagreed on: the fair line already used "
                  "the Bernoulli reading and the value block used Poisson",
    },
    "1+ home runs": {
        "dist": "binomial", "trials": "expected plate appearances",
        "reason": "at most one home run per plate appearance, the same "
                  "Bernoulli argument as hits",
    },
    "Outs recorded": {
        "dist": None, "trials": None,
        "reason": "published as a fair number only; no over line is priced, so "
                  "no mass function is claimed for it",
    },
}

def _prop_dist(prop_name: str) -> str | None:
    """The declared distribution for a prop name, or None when the market
    publishes a fair number and prices no side."""
    return (PROPS_DISTRIBUTIONS.get(prop_name) or {}).get("dist")


def _binomial_pmf(n: int, p: float, k_max: int | None = None) -> list[float]:
    """pmf[0..n] for Binomial(n, p), exact via math.comb.

    n is small here (about 4 to 5 plate appearances, about 20 to 27 batters
    faced), so the exact form costs nothing and avoids the (1 - p) division of
    the recurrence form blowing up at p = 1."""
    n = max(0, int(n))
    p = min(max(float(p), 0.0), 1.0)
    if p >= 1.0:
        out = [0.0] * n + [1.0]
    elif p <= 0.0:
        out = [1.0] + [0.0] * n
    else:
        q = 1.0 - p
        out = [math.comb(n, k) * (p ** k) * (q ** (n - k)) for k in range(n + 1)]
    if k_max is not None and k_max + 1 > len(out):
        out = out + [0.0] * (k_max + 1 - len(out))
    return out


def _props_pmf(lam: float, *, dist: str | None = None,
               n_trials: float | None = None):
    """(pmf, distribution_name, fallback_basis) for one prop's count.

    THE FRACTIONAL TRIAL COUNT IS A MIXTURE, NOT A ROUNDING. Expected plate
    appearances are fractional by construction (SLOT_PA runs 4.65 down to
    3.85) and a binomial needs an integer n. Rounding 4.65 up to 5 and 4.45
    down to 4 moves P(1+ hits) at lam 1.2 from 0.74645 to 0.75990, a 1.35
    point step off a 0.2 PA difference, which is an artefact of the rounding
    and not of the hitter. So the trial count is treated as what it actually
    is: a random number of trials, 4 with probability 0.35 and 5 with
    probability 0.65 at exp_pa 4.65. The pmf is the matching mixture of
    Binomial(4, p) and Binomial(5, p) with p = lam / exp_pa, which preserves
    the mean at exactly lam (measured: mean 1.600000 at lam 1.6, mass summing
    to 1.000000000000 over a support of 6) and is continuous in exp_pa. The
    mixture reads 0.74781 where the two roundings read 0.74645 and 0.75990.

    Falls back to Poisson, and SAYS SO in the third return value, when a
    declared binomial has no trial count to stand on or when lam exceeds the
    trial count (p > 1 is not a probability, and a market where that happens
    is mis-specified rather than merely awkward)."""
    dist = dist or "poisson"
    lam = float(lam)
    k_cap = max(30, int(lam) + 20)
    if dist == "binomial":
        try:
            n_exp = float(n_trials)
        except (TypeError, ValueError):
            n_exp = 0.0
        if n_exp <= 0:
            return (bm._poisson_pmf(lam, k_cap), "poisson",
                    "binomial declared for this market but no trial count was "
                    "supplied on the row; Poisson used")
        p = lam / n_exp
        if p > 1.0:
            return (bm._poisson_pmf(lam, k_cap), "poisson",
                    f"binomial declared but lam {lam:.3f} exceeds the trial "
                    f"count {n_exp:.2f}, so the per-trial rate is not a "
                    "probability; Poisson used")
        lo = int(math.floor(n_exp))
        w = n_exp - lo
        if w <= 1e-12:
            return _binomial_pmf(lo, p), "binomial", None
        a = _binomial_pmf(lo, p, k_max=lo + 1)
        b = _binomial_pmf(lo + 1, p)
        return ([(1.0 - w) * a[k] + w * b[k] for k in range(lo + 2)],
                "binomial", None)
    return bm._poisson_pmf(lam, k_cap), "poisson", None


def _poisson_over(lam: float, line: float) -> float:
    """P(count > line) for a half-point line, Poisson.

    Kept under the name the pre-2026-09-06 call sites used, now a thin wrapper
    on the single mass source so exactly one tail sum exists in this module."""
    ps = _props_side_probabilities(lam, line)
    return ps["p_over"] if ps else 0.0


def _slate_season(games) -> int:
    """The season the slate belongs to, off the first dated game, so the
    pitch-hand join asks StatsAPI for the right year without a second config."""
    for g in games or []:
        d = str(g.get("date") or "")[:4]
        if d.isdigit():
            return int(d)
    return date.today().year


def _pitch_hands(games) -> dict:
    """{mlbam: 'L'|'R'} for every MLB pitcher, ONE bulk call (2026-08-16, A5a).

    pal_export.load_pitch_hand is lru_cached per season, so the whole slate
    costs one StatsAPI request however many probables it carries. An offline
    box (or a failed fetch) returns {}, which every caller treats as "hand
    unknown, vs-RHP assumed" and LABELS rather than hiding."""
    try:
        import pal_export
        return pal_export.load_pitch_hand(_slate_season(games)) or {}
    except Exception:                                          # noqa: BLE001
        log.warning("betting_export: pitch-hand join unavailable; every props "
                    "order falls back to the vs-RHP assumption", exc_info=True)
        return {}


def props_fair_lines(games: list[dict], *, starters=None,
                     pitch_hands: dict | None = None) -> dict:
    """Model fair lines for the core props, with NO book comparison.

    The Odds API free tier prices props through a per-EVENT endpoint that bills
    per event, so a full slate of prop markets costs more credits in two weeks
    than the plan holds in a month. Rather than show a half-slate of stale
    comparisons, the module publishes its own fair number and labels it
    model-only. When a paid tier lands, the book side drops in beside these
    rows without touching the math.

    THE ORDER IS PICKED BY THE OPPOSING PROBABLE'S HAND (2026-08-16, A5a).
    hitter_leaderboards publishes BOTH projected orders (`orders.vr` and
    `orders.vl`) and this function read `vr` alone while its published
    assumption said "against a right-handed starter" for every game, including
    the ones whose announced probable throws left. The hand is resolved for
    the whole slate in ONE bulk call (`pal_export.load_pitch_hand`), the order
    set follows it, and every hitter row now carries `vs_hand` plus
    `vs_hand_basis` so the assumption is on the row, not in a footnote. An
    unknown hand (no probable announced, or the bulk join unavailable) falls
    back to the vs-RHP order and SAYS SO in `vs_hand_basis`."""
    starters = starters if starters is not None else bm.starter_inputs()
    fx = _fantasy_index()
    hit_lb = _load("hitter_leaderboards.json") or {}
    orders = {}
    for t in hit_lb.get("teams") or []:
        o = bm._org(t.get("team"))
        if o:
            ords = t.get("orders") or {}
            orders[o] = {"vr": ords.get("vr") or [], "vl": ords.get("vl") or []}
    if pitch_hands is None:
        pitch_hands = _pitch_hands(games)

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
                # THE TRIAL COUNT FOR THE BERNOULLI MARKETS. Strikeouts and
                # hits allowed are per-batter indicators, so their binomial
                # needs batters faced, not innings. `bf` is carried on the
                # projection engine's rest-of-season line beside ip, so the
                # rate is measured rather than assumed at three per inning; a
                # record without it prices Poisson and the row says so.
                bf = float(ros.get("bf") or 0.0)
                exp_bf = (bf / ip) * exp_ip if bf > 0 else None
                pitchers.append({
                    "mlbam": mid, "name": pp.get("name") or (rec or {}).get("name"),
                    "org": org, "opp": (g.get(opp) or {}).get("org"),
                    "game_pk": g.get("game_pk"),
                    "expected_ip": round(exp_ip, 2),
                    "expected_bf": (round(exp_bf, 2) if exp_bf else None),
                    "props": [
                        _prop_row("Strikeouts", lam_k, n_trials=exp_bf),
                        _prop_row("Earned runs", lam_er),
                        _prop_row("Hits allowed", lam_h, n_trials=exp_bf),
                        _prop_row("Outs recorded", exp_ip * 3.0, fair_digits=1,
                                  note="fair number only; outs props are priced "
                                       "off the same expected length"),
                    ],
                })
        # Hitters: the projected order AGAINST THE OPPOSING PROBABLE'S HAND,
        # because no lineup card exists this far out; vs-RHP is the fallback
        # when the hand is unknown, and the row says which one it got. Both
        # the assumption and the PA table are published so the number can be
        # argued with.
        for side, opp in (("home", "away"), ("away", "home")):
            org = (g.get(side) or {}).get("org")
            opp_pp = ((g.get(opp) or {}).get("probable") or {})
            opp_mid = opp_pp.get("mlbam")
            hand = pitch_hands.get(int(opp_mid)) if opp_mid else None
            if hand == "L":
                vs_hand, vs_basis = "L", "opposing probable throws L"
            elif hand == "R":
                vs_hand, vs_basis = "R", "opposing probable throws R"
            else:
                vs_hand, vs_basis = "R", "hand unknown, vs-RHP assumed"
            order_set = orders.get(org) or {}
            order = order_set.get("vl" if vs_hand == "L" else "vr") or []
            if vs_hand == "L" and not order:
                # A leaderboard built before the vl order existed still prices,
                # off the only order it has, and the basis says which one.
                order = order_set.get("vr") or []
                vs_basis += "; no vs-LHP order published, vs-RHP order used"
            for slot_row in order[:5]:
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
                    # WHICH order priced this row, and why. The assumption
                    # rides the row so a reader (and the props value machinery)
                    # never has to guess which platoon rates these are.
                    "vs_hand": vs_hand,
                    "vs_hand_basis": vs_basis,
                    # THE OVER LINES ARE THE MARKET'S, NOT THE MODEL'S: total
                    # bases posts at 1.5 and the two 1-plus questions at 0.5,
                    # so the fair-line table answers the question the book
                    # actually asks. All three go through _prop_row, which is
                    # the same mass source the value block prices against.
                    "props": [
                        # No trial count on total bases: it is Poisson by
                        # declaration, and stamping a PA count on a row that
                        # does not use one would imply a binomial.
                        _prop_row("Total bases", tb / pa * exp_pa, over_line=1.5),
                        _prop_row("1+ hits", p_hit * exp_pa, over_line=0.5,
                                  n_trials=exp_pa),
                        _prop_row("1+ home runs", p_hr * exp_pa, over_line=0.5,
                                  n_trials=exp_pa, fair_digits=3, lam_digits=3),
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
            "lineup_assumption": "projected order against the opposing probable's throwing "
                                 "hand: the vs-LHP order when the probable throws left, the "
                                 "vs-RHP order otherwise, resolved for the whole slate in one "
                                 "bulk StatsAPI call. An unknown hand falls back to the vs-RHP "
                                 "order and each hitter row says so in vs_hand_basis. A posted "
                                 "lineup card beats this every time",
            # `distribution` IS A PROSE STRING AND HAS TO STAY ONE. The page
            # renders this key verbatim through one escaper (assets/betting.js,
            # `kv("Distribution", esc(meth.distribution || "-"))`), and an
            # escaper stringifies: a dict here reaches a paying reader as
            # "[object Object]". The per-market table therefore lives in its
            # own key below, which no client reads.
            "distribution": "each prop market declares its own distribution "
                            "and every row carries the one that priced it. The "
                            "value block prices that same function at the "
                            "book's line, so the fair line and the value line "
                            "cannot disagree about a bet. No props row has "
                            "settled yet, so none of these choices is "
                            "calibrated against outcomes",
            # ONE mass function per market, shared with the value block, each
            # with the structural reason it is that one and not a blanket
            # Poisson. Read PROPS_DISTRIBUTIONS in this module for the same
            # table in source form.
            "distribution_by_market": {
                "rule": "each prop market declares one distribution, and the "
                        "row carries which one priced it in `pmf`. The value "
                        "block prices the SAME function at the book's line, so "
                        "the two tables cannot disagree about one bet",
                "model_id": PROPS_MODEL_ID,
                "by_market": {k: {"dist": v["dist"], "trials": v["trials"],
                                  "reason": v["reason"]}
                              for k, v in PROPS_DISTRIBUTIONS.items()},
                "not_claimed": "no props row has ever settled, so none of "
                               "these distributions is calibrated against "
                               "outcomes. The choice is structural, not "
                               "measured",
            },
        },
        "pitchers": pitchers,
        "hitters": hitters,
    }


def _prop_row(name: str, lam: float, *, n_trials: float | None = None,
              over_line: float | None = None, fair_digits: int = 2,
              lam_digits: int = 2, note: str | None = None) -> dict:
    """ONE props fair-line row, priced by the market's declared distribution.

    Every props row on the page is built here, pitcher and hitter alike. The
    hitter rows used to be three inline dict literals with their own
    arithmetic, which is how `1+ hits` came to be a Bernoulli complement on
    this surface and a Poisson on the value surface.

    `over_line` defaults to the nearest half point above lam, never a whole
    number, because a whole-number fair line would push and a fair line has no
    book to refund it. A market that declares no distribution
    (PROPS_DISTRIBUTIONS `dist` None) publishes the fair number alone: no
    line, no probability, and `pmf` null rather than a distribution it does
    not claim.

    `n_trials` is the count the market is a sum over (plate appearances,
    batters faced). It rides on the row so the value block prices the same
    binomial rather than re-deriving one.

    THE ROW IS PRICED AT THE LAMBDA IT PUBLISHES. Rounding after pricing left
    a second, smaller version of the same defect: the fair-line table priced
    the unrounded intermediate while the value block priced the rounded `lam`
    off the row, which read 0.58110 against 0.58029 on the first fixture
    total-bases row (2026-09-06). Rounding first makes the published number
    and the priced number the same number, and the two surfaces agree to the
    last decimal rather than to four."""
    spec = PROPS_DISTRIBUTIONS.get(name) or {}
    dist = spec.get("dist")
    lam_pub = round(float(lam), lam_digits)
    trials = round(float(n_trials), 3) if n_trials else None
    row = {"prop": name, "fair_line": round(float(lam), fair_digits),
           "lam": lam_pub, "n_trials": trials,
           "model_id": PROPS_MODEL_ID, "pmf": None, "pmf_basis": None,
           "over_line": None, "p_over": None}
    if note:
        row["note"] = note
    if dist is None:
        row["pmf_basis"] = spec.get("reason")
        return row
    if over_line is None:
        over_line = round(lam_pub * 2) / 2.0
        if over_line == int(over_line):
            over_line += 0.5
    ps = _props_side_probabilities(lam_pub, over_line, dist=dist,
                                   n_trials=trials)
    row["over_line"] = over_line
    if ps:
        row["p_over"] = round(ps["p_over"], 4)
        row["pmf"] = ps["pmf"]
        row["pmf_basis"] = ps["pmf_basis"]
    else:
        row["pmf_basis"] = ("no mass function: lam is not positive, so no "
                            "probability is published for this row")
    return row


# ===========================================================================
# props VALUE bets (2026-08-16, docs/diamond-betting.md section 7c;
# pre-registered there BEFORE this code, ships INERT without both arming vars)
# ===========================================================================
#: Games a day the props pull may price. Owner band is 2 to 3; 3 is
#: pre-registered in section 7c's table and changing it is this one edit.
PROPS_MAX_GAMES_PER_DAY = 3

#: The Odds API market key -> the props_fair_lines prop name whose lambda
#: prices it. The lambdas already exist (section 4's fair lines, on the A5a
#: vs-hand order); the value machinery evaluates them at the BOOK's line.
#:
#: The prop name is also the key into PROPS_DISTRIBUTIONS, so this map decides
#: the distribution too and there is no second table to drift against it.
#: test_betting_props_pmf pins that every name here has a declared
#: distribution.
PROPS_MARKET_LAMBDAS = {
    "pitcher_strikeouts": ("pitchers", "Strikeouts"),
    "batter_total_bases": ("hitters", "Total bases"),
    "batter_hits": ("hitters", "1+ hits"),
    "batter_home_runs": ("hitters", "1+ home runs"),
}


def props_value_games(bets: list[dict], *, slots: dict | None = None,
                      cap: int = PROPS_MAX_GAMES_PER_DAY) -> list[dict]:
    """The games a props pull would price, DETERMINISTIC (section 7c): the
    watch-slot game first, then the remaining games by their largest
    team-market edge, descending, ties to the lower game_pk. Two identical
    boards select identical games, so the credit spend is reviewable before
    it happens."""
    rows = [b for b in bets or [] if b.get("game_pk") is not None]

    def _best_edge(b):
        best = None
        for rws in (b.get("moneyline") or [], b.get("runline") or [],
                    ((b.get("total") or {}).get("sides") or [])):
            for r in rws or []:
                e = r.get("edge")
                if e is not None and (best is None or e > best):
                    best = e
        return best

    picked, seen = [], set()
    slot_row = (slots or {}).get("pick_of_the_day")
    slot_pk = (slot_row or {}).get("game_pk")
    if slot_pk is not None:
        for b in rows:
            if b["game_pk"] == slot_pk:
                picked.append({**b, "_selection_basis": "watch-slot game"})
                seen.add(slot_pk)
                break
    ranked = sorted((b for b in rows if b["game_pk"] not in seen),
                    key=lambda b: (_best_edge(b) is None,
                                   -(_best_edge(b) or 0.0),
                                   b.get("game_pk") or 0))
    for b in ranked:
        if len(picked) >= cap:
            break
        picked.append({**b, "_selection_basis": "largest team-market edge"})
    return picked[:cap]


def _props_side_probabilities(lam: float, line: float, *,
                              dist: str | None = None,
                              n_trials: float | None = None) -> dict | None:
    """Over, Under and PUSH for one posted props line, off the ONE mass source.

    THIS IS THE ONLY PLACE A PROP PROBABILITY IS COMPUTED. Before 2026-09-06
    the fair-lines block derived `1+ hits` and `1+ home runs` independently as
    a per-PA Bernoulli complement while this function priced the same two
    markets as a Poisson, so /betting/ carried two answers for one bet. Both
    surfaces now call here with the market's declared distribution
    (PROPS_DISTRIBUTIONS) and the trial count the row carries, so they agree
    by construction rather than by review.

    `dist` defaults to Poisson so the two-argument call kept by the older
    tests prices exactly what it priced before.

    The push discipline is unchanged and is the same one
    betting_model.total_side_probabilities carries for totals: on a
    whole-number line the sides are CONDITIONED on the bet resolving and
    `p_push` rides beside them, so `_priced_side` can scale the EV by
    (1 - p_push) exactly as it does for a whole-number total. A half-point
    line cannot push and reports `p_push` None.

    Returns `pmf`, the distribution that actually produced the numbers, and
    `pmf_basis`, non-null only when a declared distribution could not be used
    and the fallback needs stating."""
    try:
        lam, line = float(lam), float(line)
    except (TypeError, ValueError):
        return None
    if lam <= 0 or line < 0:
        return None
    pmf, used, basis = _props_pmf(lam, dist=dist, n_trials=n_trials)
    if abs(line - round(line)) < 1e-9:
        k = int(round(line))
        p_push = pmf[k] if 0 <= k < len(pmf) else 0.0
        denom = 1.0 - p_push
        if denom <= 0:
            return None
        return {"p_over": sum(pmf[k + 1:]) / denom,
                "p_under": sum(pmf[:k]) / denom,
                "p_push": p_push, "pmf": used, "pmf_basis": basis}
    need = int(line) + 1
    p_over = sum(pmf[need:])
    # A finite-support binomial can hand back a hair over or under 1.0 in
    # floating point; the Under is the complement of the Over on a line that
    # cannot push, and it is clamped so no row ever publishes a negative
    # probability or one above 1.
    p_under = min(1.0, max(0.0, 1.0 - p_over))
    return {"p_over": min(1.0, max(0.0, p_over)), "p_under": p_under,
            "p_push": None, "pmf": used, "pmf_basis": basis}


def _props_pricing_index(props_fair: dict) -> dict:
    """{(org, casefolded name, market_key): {lam, dist, n_trials, prop}} out of
    the fair-lines block, so the value pass prices the SAME mass function the
    props tab already shows.

    IT CARRIES THE WHOLE SPEC, NOT THE LAMBDA ALONE (2026-09-06). While this
    index returned a bare float the value block had no way to know a market
    was binomial or what it was binomial over, so it fell back to a Poisson
    for everything and quoted a different number than the table above it. The
    trial count now travels with the lambda.

    The org is in the key because two rosters can carry the same name. The
    lambda read here is the value PUBLISHED on the row, and `_prop_row` prices
    that same published value, so the value row and the fair-line row are the
    identical number rather than two roundings of one."""
    idx = {}
    pf = props_fair or {}
    for mkey, (section, prop_name) in PROPS_MARKET_LAMBDAS.items():
        dist = _prop_dist(prop_name)
        for rec in pf.get(section) or []:
            nm = (rec.get("name") or "").casefold().strip()
            if not nm:
                continue
            for pr in rec.get("props") or []:
                if pr.get("prop") == prop_name and pr.get("lam") is not None:
                    idx[(rec.get("org"), nm, mkey)] = {
                        "lam": float(pr["lam"]),
                        "dist": dist,
                        "n_trials": pr.get("n_trials"),
                        "prop": prop_name,
                    }
    return idx


def _load_props_snapshots(on_date: str | None) -> dict:
    """{event_id: parsed props record} off the cache, pure reads."""
    out = {}
    for meta in bi.list_props_snapshots(on_date):
        wrap = bi.load_snapshot(meta["path"])
        rec = bi.parse_props_snapshot(wrap) if wrap else None
        if rec is None:
            continue
        rec.setdefault("event_id", meta["event_id"])
        rec["_captured_at"] = (wrap or {}).get("captured_at")
        out[str(rec.get("event_id") or meta["event_id"])] = rec
    return out


def props_value_bets(bets: list[dict], props_fair: dict, *,
                     slots: dict | None = None, snapshots: dict | None = None,
                     on_date: str | None = None, evald: dict | None = None,
                     market_table: dict | None = None) -> dict:
    """The props value block: fixture-verified machinery, inert without the
    two arming variables (section 7c).

    PRICING IS A PURE FUNCTION OF CACHED BYTES. Arming gates the PULL (the
    thing that spends credits); anything already in `.cache/odds/` or handed
    in as `snapshots` is priced whether or not the env is armed, which is what
    lets every test run on fixtures with no key in the environment.

    The market discipline is `_market_view` ITSELF, not a copy: each
    (market, player) pair is folded into a one-market pseudo event and priced
    through the same consensus-line, min-hold-fair-book, rejection-ledger path
    the team board uses, then `_priced_side` builds the row with the same
    edge / EV / Kelly / push arithmetic byte for byte."""
    armed = bi.props_armed()
    inert_reason = bi.props_disarmed_reason()
    thr, basis, prov = resolve_min_edge(evald)
    sel = props_value_games(bets, slots=slots)
    if snapshots is None:
        snapshots = _load_props_snapshots(on_date)

    table = ((market_table or {}).get("markets") or {})
    publishability = {}
    for mkey in bi.PROPS_MARKETS:
        row = table.get(f"props_{mkey}") or {}
        publishability[f"props_{mkey}"] = {
            "publishable": row.get("publishable"),
            "reason": row.get("reason") or ("not in this build's "
                                            "market_publishability table"),
        }

    lam_idx = _props_pricing_index(props_fair)
    rows_out, rejections = [], Counter()
    selected_meta = []
    for b in sel:
        eid = str(b.get("odds_event_id") or "")
        matchup = (f"{(b.get('away') or {}).get('org')} at "
                   f"{(b.get('home') or {}).get('org')}")
        selected_meta.append({"game_pk": b.get("game_pk"), "matchup": matchup,
                              "basis": b.get("_selection_basis"),
                              "has_props_snapshot": eid in snapshots})
        snap = snapshots.get(eid)
        if not snap:
            rejections["no_props_snapshot_for_game"] += 1
            continue
        orgs = ((b.get("home") or {}).get("org"), (b.get("away") or {}).get("org"))
        for mkey in bi.PROPS_MARKETS:
            players = sorted({p for bk in (snap.get("books") or {}).values()
                              for p in (bk.get("markets") or {}).get(mkey, {})})
            for player in players:
                pev = {"books": {}}
                for bkey, bk in (snap.get("books") or {}).items():
                    cell = ((bk.get("markets") or {}).get(mkey) or {}).get(player)
                    if not cell:
                        continue
                    pev["books"][bkey] = {"title": bk.get("title"),
                                          "last_update": bk.get("last_update"),
                                          "prop": cell}
                mv = _market_view(pev, "prop", ("over", "under"))
                if not mv:
                    rejections["no_two_sided_market"] += 1
                    continue
                line = ((mv.get("best") or {}).get("over") or {}).get("point")
                if line is None:
                    rejections["no_consensus_line"] += 1
                    continue
                spec = None
                nm = player.casefold().strip()
                for org in orgs:
                    spec = lam_idx.get((org, nm, mkey))
                    if spec is not None:
                        break
                if spec is None:
                    rejections["player_not_in_model_index"] += 1
                    continue
                lam = spec["lam"]
                # THE SAME CALL THE FAIR-LINE ROW MADE, at the book's line
                # instead of ours: same lambda, same distribution, same trial
                # count. Two surfaces, one probability.
                ps = _props_side_probabilities(lam, line, dist=spec["dist"],
                                               n_trials=spec.get("n_trials"))
                if not ps:
                    rejections["no_model_probability"] += 1
                    continue
                p_push = (round(ps["p_push"], 5)
                          if ps.get("p_push") is not None else None)
                common = {
                    "market": f"props_{mkey}", "player": player,
                    "game_pk": b.get("game_pk"), "matchup": matchup,
                    "start": b.get("start"), "lam": round(lam, 3),
                    "line": line, "vs_hand_source": "props_fair_lines (A5a)",
                    # WHICH MODEL AND WHICH DISTRIBUTION PRICED THIS ROW, so a
                    # later sub-model swap is auditable from the payload alone
                    # and no reader has to guess whether a number came from a
                    # Poisson or a binomial.
                    "model_id": PROPS_MODEL_ID,
                    "prop": spec.get("prop"),
                    "pmf": ps.get("pmf"),
                    "pmf_basis": ps.get("pmf_basis"),
                    "n_trials": spec.get("n_trials"),
                    "captured_at": snap.get("_captured_at"),
                    "provisional": prov, "min_edge_used": thr,
                    "fair_book": mv.get("fair_book"),
                    "hold_pct": mv.get("hold_pct"),
                    "fair_book_rule": mv.get("fair_book_rule"),
                    "n_books_on_line": mv.get("n_books_on_line"),
                    "n_books_hold_rejected": mv.get("n_books_hold_rejected"),
                    "n_books_stale_rejected": mv.get("n_books_stale_rejected"),
                    "n_books_consensus_rejected":
                        mv.get("n_books_consensus_rejected"),
                }
                for side, p_model in (("over", ps["p_over"]),
                                      ("under", ps["p_under"])):
                    label = f"{player} {side.capitalize()} {line}"
                    row = _priced_side(side, label, p_model, mv, p_push=p_push)
                    k = row.get("kelly_full")
                    row["kelly_quarter"] = (round(float(k) / 4.0, 5)
                                            if k is not None else None)
                    rows_out.append({**common, **row})

    value_rows = [r for r in rows_out
                  if r.get("edge") is not None and r["edge"] >= thr]
    return {
        "armed": armed,
        "inert_reason": (None if armed else inert_reason),
        "arming": {"key_env": bi.ENV_KEY, "cap_env": bi.ENV_PROPS_CREDITS,
                   "rule": "the pull fires only when BOTH are set; either one "
                           "absent leaves the machinery inert (section 7c)"},
        "slate_date": on_date,
        "max_games_per_day": PROPS_MAX_GAMES_PER_DAY,
        "credits_per_event": bi.props_credits_for(),
        "selection_rule": ("the watch-slot game first, then the remaining "
                           "games by largest team-market edge, capped at "
                           f"{PROPS_MAX_GAMES_PER_DAY} a day"),
        "selected_games": selected_meta,
        "markets": list(bi.PROPS_MARKETS),
        "floor": {"min_edge": thr, "basis": basis, "provisional": prov,
                  "note": "the SAME floor the team slots clear; no props "
                          "floor exists and none may be invented"},
        "rows": rows_out,
        "value_rows": value_rows,
        "n_rows": len(rows_out),
        "n_value_rows": len(value_rows),
        "rejections": dict(rejections),
        "publishability": publishability,
        "method": {
            "market_view": "the team board's _market_view verbatim: consensus "
                           "line by book count, prices shopped on that line "
                           "only, fair probabilities from the minimum-hold "
                           "book, staleness / hold / consensus-distance "
                           "rejections counted per pair",
            "model_prob": "the props fair-line lambda (vs-hand order, A5a) "
                          "evaluated at the BOOK's consensus line through the "
                          "SAME mass function the fair-line table publishes "
                          "(_props_side_probabilities, distribution declared "
                          "per market in PROPS_DISTRIBUTIONS), "
                          "push-conditioned on whole numbers. Every row "
                          "carries `model_id` and `pmf`",
            "one_probability_per_bet": ("before 2026-09-06 this block priced "
                                        "1+ hits and 1+ home runs as a Poisson "
                                        "while the fair-line table priced them "
                                        "as a per-PA Bernoulli, so the page "
                                        "carried two answers for one bet. Both "
                                        "now call one function. No published "
                                        "number moved: no props row has ever "
                                        "been served"),
        },
    }


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
def pick_blockers(*, min_edge: float | None, odds_priceable: bool,
                  gate: dict | None = None, evald: dict | None = None) -> list[dict]:
    """EVERY reason there is no pick, not just the first one.

    The old shape returned the first blocker and stopped, so on a day with no
    odds feed the payload said "no odds feed" and never mentioned that the
    model has no measured threshold either. Both are true today. A reader told
    only the first would reasonably conclude that a key on the build box is all
    that stands between him and a published pick, which is wrong by two gates.

    `evald` exists so the verdict word in the reasons comes from model_verdict
    rather than being hardcoded here; absent, the derivation is the same one
    (no artifact reads as unvalidated), so older callers keep their words."""
    # One derivation of the verdict word for both reasons below, from the same
    # function every other surface reads.
    state = model_verdict(evald)["gate_state"]
    out = []
    if not odds_priceable:
        out.append({
            "id": "odds_feed", "open": False,
            "need": "a cached odds snapshot to price against",
            "have": "none",
            # TRUE WHENEVER IT FIRES, which the old wording was not: it said
            # "no odds feed is configured" off a missing API key while the
            # board carried a full cached market. This fires only on an empty
            # event list, which is the absence of a market and nothing else.
            "reason": "no odds snapshot is cached, so there is no market to have an edge against",
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
                "reason": (f"the model is {state}: the minimum-edge threshold sits behind "
                           f"{n_gates} gates and {len(closed)} are closed, starting with "
                           f"{first.get('need')} against {have_txt} in hand"),
            })
        else:
            out.append({
                "id": "min_edge", "open": False,
                "need": "a clean out-of-sample test that measures a minimum edge",
                "have": None,
                # No pick noun: this branch only fires while the gates are
                # closed, which is exactly when the 2026-08-16 ruling retires
                # the word from payload prose.
                "reason": (f"the model is {state}: the backtest is contaminated by "
                           "season-to-date team inputs, so no minimum-edge threshold has "
                           "been measured and nothing here is promoted as a "
                           "recommendation"),
            })
    return out


#: THE PROVISIONAL FLOOR. Owner decision 2026-08-06: show a Pick of the Day
#: before the model is validated, clearly labelled, rather than showing nothing
#: for a season.
#:
#: This number is a POLICY, not a measurement, and the page says so in those
#: words. It is deliberately far above anything the model can currently justify:
#: the whole in-sample margin over the home-field baseline is 0.0079 Brier
#: (0.24946 -> 0.24156), which is thin, and the out-of-sample margin will be
#: thinner still. Requiring a 6 point edge means a pick appears only when the
#: model disagrees with a de-vigged market by far more than the skill there is
#: any evidence for, so the failure mode is showing NOTHING on most slates
#: rather than showing something weak on all of them.
#:
#: It is NOT the measured `min_edge`. When the three gates open, sweep_min_edge
#: returns a threshold with an ROI lower bound behind it and that one replaces
#: this constant automatically. Nothing here has to be edited for that to
#: happen; see `resolve_min_edge`.
PROVISIONAL_MIN_EDGE = 0.06


def resolve_min_edge(evald: dict | None) -> tuple[float | None, str, bool]:
    """(threshold, basis, provisional) for this slate's pick.

    The measured threshold wins whenever it exists. The provisional floor is
    used only while the gates are shut, and the third element of the tuple is
    what every surface keys its labelling off, so a provisional pick can never
    render as a validated one by omission."""
    gate = (evald or {}).get("min_edge_gate") or {}
    measured = gate.get("min_edge")
    if measured is not None and gate.get("all_gates_open"):
        return float(measured), "measured", False
    return PROVISIONAL_MIN_EDGE, "provisional_policy_floor", True


#: THE PICK-OF-THE-DAY PRICE BAND, in american odds, inclusive on both ends.
#: Owner decision 2026-08-07: the headline slot is the side the model is most
#: confident in among prices a reader recognises as a normal bet, not the side
#: with the fattest number attached to it.
#:
#: Selecting on EV alone, which is what the single slot did, drives the pick to
#: the longest price on the board every time: EV is probability times payout,
#: and payout dominates. On the 2026-08-06 board that put a +304 moneyline with
#: a 32.9% model probability in the headline slot, which is an honest number and
#: a terrible flagship. The band pushes those to their own slot and leaves this
#: one to the sides the model actually likes.
POTD_ODDS_BAND = (-199, 199)

#: A price at or beyond this is a longshot and is judged on EV instead, because
#: at +300 the model is never going to be the confident side and ranking those
#: rows by probability would just pick the shortest of them.
LONGSHOT_MIN_ODDS = 200

#: What the page SUGGESTS per slot, in flat units. This is display only.
#: `stake_units` on the row, on the public record and in the shadow ledger is
#: STAKE_UNITS for every slot, because a published ROI computed over variable
#: stakes cannot be audited from the rows: a reader would have to trust that the
#: sizing was decided before the result and not after it. The suggestion says
#: what a reader might do; the record says what the site is accountable for.
SLOT_DISPLAY_UNITS = {"pick_of_the_day": 1.0, "longshot_of_the_day": 0.5}

SLOT_LABELS = {"pick_of_the_day": "Pick of the Day",
               "longshot_of_the_day": "Longshot Value of the Day"}

#: THE MODEL WATCH FRAME (owner decision 2026-08-16, docs/diamond-betting.md
#: 7a; supersedes the 2026-08-06 provisional-picks framing). While the three
#: gates are closed the slots are presented as the model's largest measured
#: DISAGREEMENTS with the market, not as recommendations, and user-facing
#: prose retires the pick noun. The STRUCTURAL KEYS keep their names: the
#: shadow ledger's slot continuity (SLOT_TAGS) and the record funnel depend on
#: them, and the same decision requires the accrual to continue through the
#: reframe. The self-lift is coded, not remembered: everything below keys off
#: resolve_min_edge's provisional flag, so the day the gates open the pick
#: vocabulary returns with no edit.
SLOT_WATCH_LABELS = {"pick_of_the_day": "Model Watch: largest disagreement",
                     "longshot_of_the_day": "Model Watch: long-price disagreement"}


def slot_presentation(slot: str, provisional: bool) -> dict:
    """label + frame for one slot under the 2026-08-16 ruling."""
    if provisional:
        return {"slot_label": SLOT_WATCH_LABELS[slot], "slot_frame": "watch"}
    return {"slot_label": SLOT_LABELS[slot], "slot_frame": "pick"}


def _selection_noun(provisional: bool) -> str:
    """The noun payload prose uses for a published slot row. "selection" while
    the gates are closed, "pick" once they open: the vocabulary is a claim
    about validation, so it follows the same flag everything else does."""
    return "selection" if provisional else "pick"


def _slot_tag_records() -> dict:
    """{payload slot key: the settled record of ITS OWN shadow tag}, served on
    the slot meta so the watch card can show "this selection rule is 2-4,
    -47.9%" without a second fetch.

    Read from betting_shadow.summary()["by_tag"], never pooled: potd_band and
    longshot select on different quantities and section 7a forbids mixing
    them. `small_n` is derived against the same 100-row floor gate 3 sweeps
    at, so the client's small-sample label and the sweep's readiness cannot
    disagree about what small means."""
    try:
        import betting_shadow as bs
        by_tag = bs.summary().get("by_tag") or {}
        tags = dict(bs.SLOT_TAGS)
        floor = int(bs.MIN_BETS_FOR_SWEEP)
    except Exception:                                          # noqa: BLE001
        log.warning("betting_export: shadow ledger unreadable; slot tag "
                    "records degrade to unavailable", exc_info=True)
        return {k: {"available": False,
                    "reason": "the shadow ledger could not be read"}
                for k in SLOT_LABELS}
    out = {}
    for key, tag in tags.items():
        t = by_tag.get(tag) or {}
        n = t.get("n_settled") or 0
        out[key] = {
            "available": True,
            "tag": tag,
            "n_settled": n,
            "won": t.get("won") or 0,
            "lost": t.get("lost") or 0,
            "push": t.get("push") or 0,
            "net_units": t.get("net_units"),
            "roi": t.get("roi"),
            "small_n": n < floor,
            "sweep_floor": floor,
            "source": "betting_shadow.summary() by_tag",
        }
    return out

#: Attached to any published slot on a runline or total. The Poisson-difference
#: margin underdisperses real run scoring (docs/diamond-betting.md section 11),
#: which pulls those two markets' probabilities toward the middle and therefore
#: inflates the model's confidence on the side of the line the middle sits on.
#: The moneyline is the least exposed of the three. The caveat rides the row so
#: it cannot be lost by a client that renders the pick and not the limits list.
#: Attached to any published slot on a market the section 7b evidence leg has
#: CLOSED (its own settled canonical games resolved worse than a coin for the
#: dwell). Under the any-market policy (2026-09-05) the closure no longer bars the
#: market; this is what the row says instead.
EVIDENCE_CAVEAT = ("this market's own settled paper record resolved worse than a coin "
                   "at the section 7b floor for the closure dwell; it is eligible "
                   "under the any-market slot policy (owner decision 2026-09-05) and "
                   "that record rides here as the disclosure, not as a bar")

POISSON_CAVEAT = ("this is a runline or total, and the margin model is a Poisson "
                  "difference that underdisperses real run scoring, so its "
                  "probabilities sit too close to the middle; treat this edge as "
                  "the softest of the three markets")


# ===========================================================================
# THE MARKET-LEVEL PUBLISHABILITY GATE (docs/diamond-betting.md section 7b)
# ===========================================================================
# Pre-registered 2026-08-16, in the doc BEFORE this code existed. The
# dispersion exclusion is the THEORY leg: it bars the two markets whose margin
# model is known to be mis-shaped. This is the EVIDENCE leg: it bars any
# market whose measured probabilities have RESOLVED worse than a coin on the
# calibration ledger's canonical-side games, and it re-opens the market when
# the trailing sample stops saying so. The two legs are AND-ed at both seams.
MARKET_GATE_STATE_PATH = BETTING_CACHE_DIR / "market_gate_state.json"

#: POLICY, both of them, chosen for hysteresis and not measured (section 7b
#: says so in a table). The dwell keeps one noisy night from flapping a market
#: closed and open again; the trailing window lets a market that improved
#: re-open on recent evidence rather than dragging its whole history.
MARKET_GATE_DWELL = 3
MARKET_GATE_TRAILING = 200

BOARD_MARKETS = ("moneyline", "runline", "total")

#: THE PROPS MARKETS IN THE SAME FRAMEWORK (2026-08-16, section 7c). Each
#: props market is its own row in the publishability table with the same
#: ledger-evidence leg and dwell as the three board markets, so the framework
#: is uniform rather than props being quietly exempt. They are NOT board
#: markets: _floor_clearing_sides never sees them and no props row can fill a
#: team slot or reach the public record.
PROPS_GATED_MARKETS = tuple(f"props_{m}" for m in bi.PROPS_MARKETS)
GATED_MARKETS = BOARD_MARKETS + PROPS_GATED_MARKETS


def _fresh_market_gate_state() -> dict:
    return {
        "schema": 1,
        "last_evaluation_date": None,
        "updated_at": None,
        "markets": {m: {"status": "open", "consecutive_worse": 0,
                        "consecutive_recovered": 0,
                        "closed_at": None, "reopened_at": None}
                    for m in GATED_MARKETS},
        "what": ("dwell state for the section 7b market-level publishability "
                 "gate. The statistics are recomputed every build; these "
                 "consecutive-evaluation counters move at most once per UTC "
                 "day. This lives under .cache/ rather than in the append-only "
                 "learning history because that history is betting_learning.py's "
                 "own series, written by its own build step under its own "
                 "append-only check, and a foreign key written into its "
                 "artifact from here would be dropped on the next nightly "
                 "rebuild (decided 2026-08-16, docs/diamond-betting.md 7b)."),
    }


def load_market_gate_state(path: Path | None = None) -> dict:
    """The persisted dwell state, or a fresh all-open one.

    An unreadable file logs and starts fresh rather than raising: the worst
    that costs is re-earning a closure over three nights, while a build that
    dies on a corrupt sidecar publishes nothing at all."""
    p = Path(path or MARKET_GATE_STATE_PATH)
    if not p.exists():
        return _fresh_market_gate_state()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("betting_export: unreadable %s; the market-gate dwell "
                    "restarts from all-open", p.name)
        return _fresh_market_gate_state()
    if not isinstance(obj, dict) or not isinstance(obj.get("markets"), dict):
        log.warning("betting_export: %s carries no markets block; the "
                    "market-gate dwell restarts from all-open", p.name)
        return _fresh_market_gate_state()
    fresh = _fresh_market_gate_state()
    for m in GATED_MARKETS:
        merged = {**fresh["markets"][m], **(obj["markets"].get(m) or {})}
        obj["markets"][m] = merged
    for k in ("last_evaluation_date", "updated_at", "what", "schema"):
        obj.setdefault(k, fresh[k])
    return obj


def save_market_gate_state(state: dict, path: Path | None = None) -> None:
    p = Path(path or MARKET_GATE_STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(p)


def ledger_closed_markets(state: dict | None = None, *,
                          path: Path | None = None) -> frozenset:
    """The markets the EVIDENCE leg currently bars. Cheap on purpose: the two
    seams call this, and neither may pay for a ledger scan to answer a
    question the persisted state already answers."""
    st = state if state is not None else load_market_gate_state(path)
    return frozenset(m for m, ms in (st.get("markets") or {}).items()
                     if (ms or {}).get("status") == "ledger_closed")


def market_publishability(*, state: dict | None = None, full: dict | None = None,
                          trailing: dict | None = None,
                          cal_path: Path | None = None,
                          state_path: Path | None = None) -> dict:
    """The combined per-market table: dispersion leg AND ledger leg, each with
    its reason, published on the payload. Pure read; nothing here advances the
    dwell (that is market_gate_evaluate's job, once per UTC day)."""
    if full is None or trailing is None:
        from tools import betting_calibration as bc
        full = full if full is not None else bc.market_gate(path=cal_path)
        trailing = (trailing if trailing is not None else
                    bc.market_gate(path=cal_path, trailing=MARKET_GATE_TRAILING))
    st = state if state is not None else load_market_gate_state(state_path)
    n_min = next(iter(full.values()))["n_min"] if full else 100
    z = next(iter(full.values()))["z"] if full else 1.645

    markets = {}
    for m in GATED_MARKETS:
        f = full.get(m) or {}
        tr = trailing.get(m) or {}
        ms = (st.get("markets") or {}).get(m) or {}
        status = ms.get("status") or "open"
        disp_ok = bm.market_theory_ok(m)
        if m in PROPS_GATED_MARKETS:
            # Props are not priced by the margin model, so the theory leg has
            # nothing to say about them; the ledger leg is the whole gate.
            disp_reason = ("props are not in DISPERSION_SENSITIVE_MARKETS: the "
                           "margin model does not price this market, so the "
                           "dispersion leg cannot bar it (section 7c)")
        else:
            disp_reason = ("the margin-shape exclusion does not bar this market"
                           if disp_ok else
                           "excluded while the dispersion correction is unserved "
                           "(section 11a): the margin model that prices this market "
                           "did not clear its pre-registered gate")
        n = f.get("n_games") or 0
        if n < n_min:
            verdict = "unresolved"
            ledger_reason = (f"{n} canonical settled game(s) against the "
                             f"{n_min}-game floor; the ledger leg is unresolved "
                             "and closes nothing")
            if m in PROPS_GATED_MARKETS:
                ledger_reason += (". Props calibration rows cannot settle until "
                                  "a box-score grader exists (section 7c), so "
                                  "this leg stays unresolved by construction "
                                  "for now")
        elif f.get("worse_than_coin_95"):
            verdict = "worse_than_coin"
            ledger_reason = (f"mean Brier {f.get('brier')} on {n} canonical games "
                             f"resolves worse than a coin (t {f.get('t')} at the "
                             f"one-sided 95% bar of {z})")
        else:
            verdict = "not_worse_than_coin"
            ledger_reason = (f"mean Brier {f.get('brier')} on {n} canonical games "
                             "does not resolve worse than a coin")
        if status == "ledger_closed":
            ledger_reason = (f"LEDGER-CLOSED: resolved worse than a coin for "
                             f"{MARKET_GATE_DWELL} consecutive evaluations "
                             f"(closed {ms.get('closed_at')}); re-opens when the "
                             f"trailing {MARKET_GATE_TRAILING} games fail the same "
                             f"test for {MARKET_GATE_DWELL} consecutive "
                             f"evaluations. Today: {ledger_reason}")
        legs_ok = bool(disp_ok and status != "ledger_closed")
        policy_any = bm.SLOT_MARKET_POLICY == "any"
        publishable = bool(legs_ok or policy_any)
        if legs_ok:
            reason = ("publishable: " + disp_reason + ", and " + ledger_reason)
        elif not disp_ok and status == "ledger_closed":
            reason = "excluded by both legs: " + disp_reason + "; " + ledger_reason
        elif not disp_ok:
            reason = disp_reason
        else:
            reason = ledger_reason
        if policy_any and not legs_ok:
            # THE POLICY OVERRIDE (2026-09-05): the legs are still measured and
            # still stated; they ride the published row as disclosure instead of
            # barring the market. The sentence keeps the legs' own words so a
            # reader sees exactly what was overridden.
            reason = ("eligible under the any-market slot policy (owner decision "
                      "2026-09-05, section 7d); the legs ride the row as disclosure: "
                      + reason)
        markets[m] = {
            "market": m,
            "publishable": publishable,
            "policy_override": bool(policy_any and not legs_ok),
            "reason": reason,
            # THE BOTH-LEGS COPY STATE (2026-08-19, pre-decided). True exactly
            # when the evidence leg has CLOSED a market the theory leg already
            # bars, so the page can say "watch-only for two independent
            # reasons" with both numbers read off this table instead of a
            # reader inferring one exclusion from a sentence about the other.
            # Derived from the two fields beside it, never stored: the flag
            # cannot drift from the legs it summarizes.
            "both_legs": bool((not disp_ok) and status == "ledger_closed"),
            "dispersion_leg": {"publishable": disp_ok, "reason": disp_reason},
            "ledger_leg": {
                "status": status,
                "verdict": verdict,
                "n_games": f.get("n_games"), "brier": f.get("brier"),
                "delta_vs_coin": f.get("delta_vs_coin"), "t": f.get("t"),
                "worse_than_coin_95": bool(f.get("worse_than_coin_95")),
                "trailing": {"n_games": tr.get("n_games"), "brier": tr.get("brier"),
                             "delta_vs_coin": tr.get("delta_vs_coin"),
                             "t": tr.get("t"),
                             "worse_than_coin_95": bool(tr.get("worse_than_coin_95")),
                             "window": MARKET_GATE_TRAILING},
                "consecutive_worse": ms.get("consecutive_worse", 0),
                "consecutive_recovered": ms.get("consecutive_recovered", 0),
                "dwell_need": MARKET_GATE_DWELL,
                "reason": ledger_reason,
            },
        }

    under = [f"{m} {(full.get(m) or {}).get('n_games') or 0}"
             for m in GATED_MARKETS
             if ((full.get(m) or {}).get("n_games") or 0) < n_min]
    today_note = (f"no market reaches the {n_min}-game canonical floor yet "
                  f"({', '.join(under)}), so the ledger leg closes nothing on "
                  "this build"
                  if len(under) == len(GATED_MARKETS) else None)
    return {
        "policy": {
            "slot_market_policy": bm.SLOT_MARKET_POLICY,
            "slot_market_policy_note": (
                "any: every priced market may fill a slot and reach the record; the "
                "dispersion and ledger legs below are disclosure on the row (owner "
                "decision 2026-09-05, docs/diamond-betting.md 7d)"
                if bm.SLOT_MARKET_POLICY == "any" else
                "dispersion_gated: a market must clear BOTH legs to fill a slot or "
                "reach the public record"),
            "n_min": n_min, "z": z, "dwell": MARKET_GATE_DWELL,
            "trailing": MARKET_GATE_TRAILING,
            "basis": ("n_min mirrors betting_shadow.MIN_BETS_FOR_SWEEP and z is "
                      "betting_model.Z_95_ONE_SIDED; the dwell of 3 and the "
                      "trailing 200 are POLICY chosen for hysteresis, not "
                      "measured (docs/diamond-betting.md section 7b)"),
        },
        "last_evaluation_date": st.get("last_evaluation_date"),
        "today_note": today_note,
        "note": ("a market must clear BOTH legs to fill a slot or reach the "
                 "public record. The shadow and calibration ledgers keep "
                 "recording closed markets, because they are the only "
                 "instruments that can ever accumulate the evidence to re-open "
                 "one."),
        "markets": markets,
    }


def market_gate_evaluate(*, cal_path: Path | None = None,
                         state_path: Path | None = None,
                         now: datetime | None = None,
                         write: bool = True, log_fn=None) -> dict:
    """ONE nightly evaluation of the section 7b gate, and the only function
    that moves the dwell.

    The counters advance at most once per UTC calendar day: "3 consecutive
    nightly evaluations" means three nights, and a pipeline that runs twice in
    an afternoon must not close a market in one day. A same-day re-run
    refreshes the statistics and leaves the counters alone."""
    from tools import betting_calibration as bc
    full = bc.market_gate(path=cal_path)
    trail = bc.market_gate(path=cal_path, trailing=MARKET_GATE_TRAILING)
    state = load_market_gate_state(state_path)
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    advanced = state.get("last_evaluation_date") != today

    for m in GATED_MARKETS:
        ms = state["markets"][m]
        fm = full.get(m) or {"worse_than_coin_95": False,
                             "n_games": 0, "brier": None}
        tm = trail.get(m) or {"worse_than_coin_95": False}
        if not advanced:
            continue
        if ms.get("status") != "ledger_closed":
            ms["consecutive_worse"] = (ms.get("consecutive_worse", 0) + 1
                                       if fm["worse_than_coin_95"] else 0)
            if ms["consecutive_worse"] >= MARKET_GATE_DWELL:
                ms["status"] = "ledger_closed"
                ms["closed_at"] = _now()
                ms["consecutive_recovered"] = 0
                if log_fn:
                    log_fn(f"betting_export: MARKET LEDGER-CLOSED {m} "
                           f"(worse than a coin {MARKET_GATE_DWELL} evaluations "
                           f"running, n={fm['n_games']}, "
                           f"brier={fm['brier']})")
                log.warning("betting_export: market %s is LEDGER-CLOSED "
                            "(section 7b)", m)
        else:
            ms["consecutive_recovered"] = (ms.get("consecutive_recovered", 0) + 1
                                           if not tm["worse_than_coin_95"]
                                           else 0)
            if ms["consecutive_recovered"] >= MARKET_GATE_DWELL:
                ms["status"] = "open"
                ms["reopened_at"] = _now()
                ms["consecutive_worse"] = 0
                if log_fn:
                    log_fn(f"betting_export: market {m} RE-OPENED (trailing "
                           f"{MARKET_GATE_TRAILING} no longer resolve worse "
                           f"than a coin, {MARKET_GATE_DWELL} evaluations "
                           "running)")
    if advanced:
        state["last_evaluation_date"] = today
    state["updated_at"] = _now()
    if write:
        try:
            save_market_gate_state(state, state_path)
        except OSError:
            log.warning("betting_export: could not persist %s; the dwell will "
                        "re-derive from tonight's statistics on the next build",
                        MARKET_GATE_STATE_PATH.name)
    return market_publishability(state=state, full=full, trailing=trail)


def _floor_clearing_sides(bets: list[dict], thr: float, *,
                          ledger_closed: frozenset | None = None,
                          extra_rows: list[dict] | None = None) -> list[dict]:
    """Every side on the BOARD that clears `thr` at a real taken price, plus any
    `extra_rows` (priced props value rows) that clear it.

    THE ENUMERATION MAY NOT RE-PRICE ANYTHING. Each candidate is the board row
    verbatim plus context keys (market, game, matchup, start). Re-reading the
    odds cache here and shopping each side independently is exactly what
    manufactured a 0.38839 edge by fusing one book's runline with another
    book's price for the opposite side (commit 628d04e). The line is chosen
    once, by book count, in `_consensus_point`, and priced only among the books
    posting it, in `_best_price_on_line`. Both slots and the per-game best-value
    badge read the rows that came out of that, so no two surfaces on the page
    can disagree about what a side costs.

    MARKET POLICY (2026-09-05, betting_model.SLOT_MARKET_POLICY). Under "any" no
    market is skipped: the dispersion leg and the section 7b ledger leg stamp the
    candidate (`evidence_closed`) so the published row can carry them as
    disclosure. Under "dispersion_gated" the two seams of 2026-08-14 / 2026-08-16
    apply exactly as before: a dispersion-sensitive market fills no slot while the
    correction is unserved, and a ledger-closed market fills no slot.

    `extra_rows` are props value rows (props_value_bets value_rows): already priced
    off the same _market_view discipline, already carrying market / game_pk /
    matchup / start / label / player. They compete for the slots on the same floor
    and the same rule; nothing about them is special-cased except that they never
    enter the team ledger (record_props_slate keeps them in their own tags).

    `ledger_closed` is the section 7b evidence leg, injectable for tests;
    None reads the persisted dwell state."""
    if ledger_closed is None:
        ledger_closed = ledger_closed_markets()
    gated = bm.SLOT_MARKET_POLICY != "any"
    cands = []
    for b in bets:
        for market, rows in (("moneyline", b.get("moneyline") or []),
                             ("runline", b.get("runline") or []),
                             ("total", (b.get("total") or {}).get("sides") or [])):
            # SEAM 1 of 2 for the dispersion exclusion (2026-08-14) and for the
            # section 7b ledger leg (2026-08-16). Both are POLICY-scoped since
            # 2026-09-05: they bar nothing under "any" and stamp the row instead.
            if gated and not bm.market_is_publishable(market):
                continue
            if gated and market in ledger_closed:
                continue
            for row in rows or []:
                if row.get("edge") is None or row["edge"] < thr:
                    continue
                if row.get("odds") is None or not row.get("book"):
                    continue        # no real price taken, no pick
                cands.append({**row, "market": market, "game_pk": b.get("game_pk"),
                              "matchup": f"{b['away']['org']} at {b['home']['org']}",
                              "start": b.get("start"),
                              "evidence_closed": bool(market in ledger_closed)})
    for row in extra_rows or []:
        market = row.get("market")
        if not market:
            continue
        if gated and market in ledger_closed:
            continue
        if row.get("edge") is None or row["edge"] < thr:
            continue
        if row.get("odds") is None or not row.get("book"):
            continue
        cands.append({**row, "evidence_closed": bool(market in ledger_closed)})
    return cands


def _publish_slot(row: dict, slot: str, *, thr: float, prov: bool) -> dict:
    """Stamp a chosen candidate with everything that makes it self-describing.

    A row lifted out of the payload and pasted anywhere else still carries the
    floor it cleared, whether that floor was policy or measurement, which slot
    rule chose it, what the recorded stake was, and (2026-08-16) which FRAME
    it was published under: watch while the gates are closed, pick once they
    open."""
    out = {**row, "slot": slot, **slot_presentation(slot, prov),
           "stake_units": STAKE_UNITS,
           "suggested_units": SLOT_DISPLAY_UNITS[slot],
           "provisional": prov, "min_edge_used": thr}
    k = row.get("kelly_full")
    # Quarter Kelly, INFORMATIONAL. Full Kelly on an unvalidated model is a way
    # to lose a bankroll quickly, and the served number is a quarter of it so
    # nobody has to do the division under the impression the site endorsed it.
    out["kelly_quarter"] = round(float(k) / 4.0, 5) if k is not None else None
    out["market_policy"] = bm.SLOT_MARKET_POLICY
    if bm.market_is_dispersion_sensitive(row.get("market")):
        out["caveat"] = POISSON_CAVEAT
    if row.get("evidence_closed"):
        out["evidence_caveat"] = EVIDENCE_CAVEAT
    return out


def _potd_rank(row: dict) -> tuple:
    """Sort key for the headline slot: most confident first, then the price
    closest to a standard -110, then the best EV. Every term is deterministic,
    so two identical boards cannot publish two different picks."""
    return (-(row.get("model_prob") or 0.0),
            abs(float(row.get("odds") or 0) + 110.0),
            -(row.get("ev_per_unit") if row.get("ev_per_unit") is not None else -9.0))


def _longshot_rank(row: dict) -> tuple:
    """Sort key for the longshot slot: best EV first, then the higher model
    probability, so a tie on EV goes to the side the model believes more."""
    return (-(row.get("ev_per_unit") if row.get("ev_per_unit") is not None else -9.0),
            -(row.get("model_prob") or 0.0))


def provisional_picks(bets: list[dict], *, odds_priceable: bool,
                      evald: dict | None = None,
                      block_reason: str | None = None,
                      extra_candidates: list[dict] | None = None) -> tuple[dict, str, dict]:
    """Both published slots, chosen from ONE candidate list at ONE floor.

    Returns (slots, reason, meta). `slots` maps the payload key of each slot to
    a row or to None; `reason` is the headline slot's reason, which is what
    `pick_reason` has always carried; `meta` carries the floor and its basis at
    the top level (every surface keys its labelling off that) plus a sub-block
    per slot.

    THE FLOOR IS SHARED AND IT IS NOT NEGOTIABLE PER SLOT. A longshot slot that
    quietly dropped to a lower threshold so it always had something in it would
    be a threshold invented to make a pick appear, which docs/diamond-betting.md
    names as the single most dishonest number this module could publish. When
    nothing at +200 or longer clears the floor, the slot is empty and says which
    floor it failed to clear.

    An absent odds feed is still a hard stop for both slots. A provisional pick
    is a claim about a real market price; without one there is nothing to
    disagree with, and the model's own fair line is not a market.

    `block_reason` is the same hard stop for a market that exists and is the
    WRONG ONE. `resolve_snapshot` passes it when the cached snapshot cannot
    price this board's slate: the board still renders, because a fair line and a
    priced market are worth reading, and both slots stay empty carrying that
    sentence, because a pick against another slate's prices is worse than no
    pick."""
    thr, basis, prov = resolve_min_edge(evald)
    floor_txt = "provisional floor" if prov else "measured threshold"
    noun = _selection_noun(prov)
    tag_records = _slot_tag_records()
    meta = {"provisional": prov, "min_edge": thr, "basis": basis,
            # THE FRAME (owner decision 2026-08-16). "watch" while the gates
            # are closed, "pick" once they open; every client label keys off
            # this and the per-slot presentation fields, so the vocabulary
            # lifts itself the day the gates do.
            "frame": ("watch" if prov else "pick"),
            "frame_note": ("Model Watch framing, owner decision 2026-08-16: "
                           "while the three validation gates are closed the "
                           "slots present the model's largest measured "
                           "disagreements with the market, not "
                           "recommendations. The structural keys keep their "
                           "names for ledger continuity; the vocabulary "
                           "returns automatically when the gates open."
                           if prov else
                           "the three validation gates are open and a measured "
                           "threshold exists, so the pick vocabulary is in "
                           "force"),
            "policy": (("a provisional selection is published against a POLICY "
                        "floor, not a validated threshold; it is labelled as "
                        "such everywhere it appears and it is recorded in the "
                        "shadow ledger so it becomes evidence")
                       if prov else
                       ("the published pick clears the MEASURED minimum-edge "
                        "threshold; the provisional policy floor is retired")),
            "shared_floor_note": ("both slots clear the same floor; no slot is "
                                  "allowed a lower one, because a threshold "
                                  f"lowered to make a {noun} appear is not a "
                                  "threshold"),
            "slots": {}}

    def _slot_meta(slot, *, rule, band, present, reason, n_cands):
        return {"slot": slot, "label": slot_presentation(slot, prov)["slot_label"],
                **slot_presentation(slot, prov), "rule": rule,
                "band": band, "present": present, "reason": reason,
                "n_candidates": n_cands,
                "provisional": prov, "min_edge": thr, "basis": basis,
                "stake_units": STAKE_UNITS,
                "suggested_units": SLOT_DISPLAY_UNITS[slot],
                # The slot's OWN selection rule's settled paper record, so the
                # card can show it without a second fetch (section 7a).
                "tag_record": tag_records.get(slot)}

    lo, hi = POTD_ODDS_BAND
    potd_band = f"american odds from {lo:+d} to {hi:+d}"
    long_band = f"american odds of {LONGSHOT_MIN_ODDS:+d} or longer"
    potd_rule = ("highest model win probability among sides clearing the "
                 f"{floor_txt} on any priced market, restricted to {potd_band}; ties "
                 "go to the price nearest -110, then to the higher expected value")
    long_rule = ("highest expected value per unit among sides clearing the "
                 f"{floor_txt} at {long_band}")

    if not odds_priceable or block_reason:
        why = block_reason or ("no odds snapshot is cached, so there is no market price "
                               "to have an edge against")
        meta["blocked"] = True
        meta["blocked_reason"] = why
        for slot in SLOT_LABELS:
            meta["slots"][slot] = _slot_meta(
                slot, rule=(potd_rule if slot == "pick_of_the_day" else long_rule),
                band=(potd_band if slot == "pick_of_the_day" else long_band),
                present=False, reason=why, n_cands=0)
        return {k: None for k in SLOT_LABELS}, why, meta

    cands = _floor_clearing_sides(bets, thr, extra_rows=extra_candidates)
    meta["n_floor_clearing_sides"] = len(cands)
    meta["market_policy"] = bm.SLOT_MARKET_POLICY
    meta["markets_eligible"] = (
        "any priced market: moneyline, runline, total, props when armed (owner decision "
        "2026-09-05, section 7d); the dispersion and ledger legs ride the row as disclosure"
        if bm.SLOT_MARKET_POLICY == "any" else
        "moneyline while the dispersion correction is unserved; ledger-closed markets excluded")
    in_band = [c for c in cands if lo <= c["odds"] <= hi]
    longshots = [c for c in cands if c["odds"] >= LONGSHOT_MIN_ODDS]

    slots, reasons = {}, {}
    for slot, pool, rank, band in (
            ("pick_of_the_day", in_band, _potd_rank, potd_band),
            ("longshot_of_the_day", longshots, _longshot_rank, long_band)):
        if not cands:
            why = f"no side cleared the {thr:.1%} {floor_txt} on this slate"
            row = None
        elif not pool:
            why = (f"{len(cands)} side(s) cleared the {thr:.1%} {floor_txt} on this "
                   f"slate and none of them are priced at {band}")
            row = None
        else:
            row = _publish_slot(sorted(pool, key=rank)[0], slot, thr=thr, prov=prov)
            # VERBATIM ON THE ROW TOO: a slot lifted out of the payload still
            # carries its own rule's settled record beside its numbers.
            row["tag_record"] = tag_records.get(slot)
            why = (potd_rule if slot == "pick_of_the_day" else long_rule)
        slots[slot] = row
        reasons[slot] = why
        meta["slots"][slot] = _slot_meta(
            slot, rule=(potd_rule if slot == "pick_of_the_day" else long_rule),
            band=band, present=row is not None, reason=why, n_cands=len(pool))
    return slots, reasons["pick_of_the_day"], meta


def pick_of_the_day(bets: list[dict], *, min_edge: float | None,
                    odds_priceable: bool,
                    gate: dict | None = None) -> tuple[dict | None, str]:
    """The highest-EV qualifying edge, or None with every reason it is absent.

    Two hard gates, both of which are currently closed:
      * no odds feed means no market to have an edge against, and
      * no measured `min_edge` means no threshold, and a threshold invented to
        make a pick appear is the oldest trick in this industry.

    `gate` is the eval artifact's `min_edge_gate` block when one exists; it
    turns the second reason from "unvalidated" into the named count that is
    missing."""
    blockers = pick_blockers(min_edge=min_edge, odds_priceable=odds_priceable, gate=gate)
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
    # THE SLATE IS RESOLVED FIRST AND THE SNAPSHOT IS REQUESTED FOR IT. The old
    # order took an unfiltered `latest_snapshot()` and joined it to whatever
    # slate came back, with nothing comparing the two. See `resolve_snapshot`.
    slate_stats: dict = {}
    slate_date, games = resolve_slate(on_date, stats=slate_stats)
    snap, events, odds_slate = resolve_snapshot(slate_date)
    # `team_inputs_detail`, not `team_inputs`: the per-source org counts are the
    # difference between naming the broken input and guessing at it. See
    # team_input_failure_reason for the published false diagnosis that forced it.
    team_detail = bm.team_inputs_detail()
    teams, team_sources = team_detail["teams"], team_detail["sources"]
    parks, starters = bm.park_index(), bm.starter_inputs()
    ctx = bm.league_context()
    coeffs = bm.coefficients()
    evald = _load("betting_model_eval.json") or {}

    # Zeroed up front so the two counts are always integers on the status block,
    # including on a build with no slate: a missing key reads as "not measured".
    bet_stats = {"n_events_dropped_in_progress": 0,
                 "n_games_unpriced_time_mismatch": 0}
    bets = (team_bets(games, events, teams=teams, parks=parks, starters=starters,
                      stats=bet_stats) if games else [])
    min_edge = evald.get("min_edge")          # None until a clean test measures one
    gate = evald.get("min_edge_gate")
    # THE MARKET IS WHAT MAKES AN EDGE POSSIBLE, NOT AN ENVIRONMENT VARIABLE.
    # This read `bool(status.get("configured") and events)`, and `configured` is
    # `EEPHUS_ODDS_API_KEY is not None`. A key gates whether TOMORROW's snapshot
    # can be CAPTURED; it does not un-capture the ones already on disk. So a box
    # with no key published "no odds feed is configured, so there is no market
    # price to have an edge against" on a board whose own rows carried nine books
    # a side and edges to +10.4 points, and because `provisional_picks` gates on
    # the same flag and the client badge reads the floor a blocked build nulls,
    # that one false predicate suppressed the pick AND every value badge.
    #
    # `resolve_snapshot` above is the real test of whether the cached market is
    # THIS board's market, and its mismatch already empties both slots through
    # `block_reason`, so nothing here needs a second opinion. The key keeps
    # mattering where it actually applies: `status.configured` and the status
    # note still say it is unset.
    odds_priceable = bool(events)
    validation = validation_state(evald)
    # ONE derivation of "validated", read by status.model, model.validated and
    # (through the payload) the client's banner chip, so the three can never
    # disagree on the page. It takes BOTH halves: the artifact's gates open AND
    # a measured threshold. "All gates open" with a null min_edge is a
    # contradiction, and this resolves it the safe way. The derivation lives in
    # model_verdict since 2026-08-16, beside the registry's own verdict word,
    # because three surfaces each carried a private copy of it before.
    verdict = model_verdict(evald)
    validated = verdict["gate_state"] == "validated"
    blockers = pick_blockers(min_edge=min_edge, odds_priceable=odds_priceable,
                             gate=gate, evald=evald)
    # PROVISIONAL PICKS (owner decision 2026-08-06, second slot 2026-08-07). The
    # blockers above are kept and published UNCHANGED: they are the honest
    # account of why the model is not validated, and a provisional pick does not
    # make any of them untrue. What changes is that the slate no longer renders
    # empty while they are shut.
    # THE SECTION 7b MARKET GATE, evaluated BEFORE the slots are chosen so the
    # seam below reads tonight's dwell state, not last night's. One evaluation
    # per UTC day; a same-day re-run refreshes the statistics only. write=False
    # keeps a dry build from advancing the nightly counters.
    market_table = market_gate_evaluate(write=write, log_fn=log_fn)
    # PROPS COMPETE FOR THE SLOTS (owner decision 2026-09-05). The props fair lines
    # and the props value rows are priced BEFORE the slots are chosen so a props
    # side can win a slot on the same floor and the same rule as a team side. This
    # first pass takes slots=None, so its game selection is "largest team-market
    # edge" alone; the served props block below is rebuilt AFTER the slots with the
    # watch-slot game first, exactly as before. Pure reads both times: the props
    # pull itself happens in betting_ingest and spends nothing here. Inert while the
    # props machinery is unarmed (value_rows is then empty by construction).
    props_fair = (props_fair_lines(games, starters=starters) if games else
                  {"model_only": True, "pitchers": [], "hitters": [],
                   "no_book_comparison_reason": "no slate loaded"})
    _props_pre = props_value_bets(bets, props_fair, slots=None, on_date=slate_date,
                                  evald=evald, market_table=market_table)
    slots, pick_reason, pick_meta = provisional_picks(
        bets, odds_priceable=odds_priceable, evald=evald,
        block_reason=(odds_slate["reason"] if odds_slate.get("mismatch") else None),
        extra_candidates=list(_props_pre.get("value_rows") or []))
    pick = slots["pick_of_the_day"]
    longshot = slots["longshot_of_the_day"]
    # STORAGE FIRST, BEFORE ANYTHING READS THE RECORD. `ensure_record_log`
    # creates a log holding exactly the rows the record already has, so it makes
    # no claim; it exists because the `record_storage` blocker would otherwise
    # deadlock on a log that only an append could create.
    if write:
        try:
            ensure_record_log()
        except OSError:
            log.warning("betting_export: could not create the append-only record log; "
                        "the record_storage blocker will stay closed")
    record = load_record()
    # THE LAST PUBLISHED CHAIN HASH, read off the DURABLE anchor under .cache/.
    # It is what `record_storage` is checked against: a record that no longer
    # contains yesterday's hash as one of its prefix hashes was rewritten, not
    # appended to, and that is a publish blocker rather than a warning.
    #
    # It used to be read off data/betting.json, which is git-tracked, so the
    # nightly `git checkout -- .` restored a committed board with no chain_sha
    # and this arrived as None on every production build - and
    # `chain_extends(None, rows)` is True by construction, so the rewrite half of
    # the blocker was disarmed while reporting itself open.
    prev_chain_src = read_published_chain()
    prev_chain = prev_chain_src.get("chain_sha")
    feed_health = snapshot_health()
    # The label rides on the row AND on the record header, from one builder, so
    # the two cannot drift. `provisional_picks` has already resolved the floor.
    record_label = provisional_record_label(
        evald, min_edge=float(pick_meta.get("min_edge") or PROVISIONAL_MIN_EDGE),
        provisional=bool(pick_meta.get("provisional")))

    empty_reasons = []
    if not teams:
        empty_reasons.append(team_input_failure_reason(team_sources))
    # NAMED, not implied. A board priced against another slate's snapshot looks
    # exactly like a healthy board apart from a capture timestamp, which is why
    # this is a reason on the page and a hard stop on both slots rather than a
    # field somebody has to notice.
    if odds_slate.get("mismatch"):
        empty_reasons.append(odds_slate["reason"])
    if slate_stats.get("partial_slate"):
        empty_reasons.append(slate_stats["partial_slate"]["reason"])
    if not games:
        # Distinguish "the schedule is empty" from "every game on the schedule is
        # already Final or postponed". The old copy asserted the first and would
        # have sent a reader hunting a schedule refresh that ran perfectly.
        n_raw = len(slate_games(slate_date or on_date, include_unbettable=True))
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
        "slate_date": (slate_date or on_date or date.today().isoformat()),
        "n_games": len(bets),
        "status": {
            "odds_feed": ("ok" if events else ("not_configured" if not status.get("configured")
                                               else "no_snapshot")),
            "odds_note": status.get("note"),
            "odds_captured_at": (snap or {}).get("captured_at"),
            "odds_kind": (snap or {}).get("kind"),
            # The machine enum, from model_verdict, the single source every
            # verdict surface reads. The registry's own word rides beside it
            # because the two answer different questions and a reader shown
            # only one would over- or under-trust the model.
            "model": verdict["gate_state"],
            "model_registry_verdict": verdict["registry_verdict"],
            "model_verdict_sentence": verdict["sentence"],
            "model_mode": validation.get("headline_mode"),
            # The observation behind any empty-board reason, so the claim on the
            # page can be checked against the files rather than believed.
            "team_input_sources": team_sources,
            "n_slate_games": len(games),
            # Odds events the snapshot carried that were already under way, so a
            # reader can see why a game on the slate has no prices instead of
            # assuming the feed failed. See team_bets for the in-game measurement.
            "n_events_dropped_in_progress": bet_stats["n_events_dropped_in_progress"],
            "n_games_unpriced_time_mismatch": bet_stats["n_games_unpriced_time_mismatch"],
            # WHICH DATE THE BOARD IS, AND WHY IT IS NOT THE OTHER ONE. Every
            # candidate date with its game count and its disqualifying reason, so
            # a one-game board can be read as a fragment instead of as a Monday.
            "slate_rule": slate_stats.get("slate_rule"),
            "slate_candidates": slate_stats.get("slate_candidates"),
            "partial_slate": slate_stats.get("partial_slate"),
            # WHICH SLATE THE PRICES BELONG TO. `odds_captured_at` above says
            # when; this says what for.
            "odds_slate": odds_slate,
            "odds_slate_mismatch": bool(odds_slate.get("mismatch")),
            "odds_snapshot_age_hours": odds_slate.get("snapshot_age_hours"),
            "stale_board": False,
            # OPEN/CLOSE CAPTURE COVERAGE, measured off .cache/odds/ rather than
            # off a heartbeat the nightly checkout would have reverted. The
            # `diagnosis` string names the repair, not the symptom.
            "feed_health": feed_health,
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
        # THE KEY NAME IS THE CONTRACT. The client, the preview slice and
        # test_betting all read `pick_of_the_day`; the second slot is added
        # beside it rather than the pair being nested under a new key, so an
        # older reader of this payload keeps working and shows one slot instead
        # of none.
        "pick_of_the_day": pick,
        "longshot_of_the_day": longshot,
        "pick_reason": pick_reason,
        # The label the page keys off. Published even when a slot is empty, so
        # a client can render the provisional treatment around an empty slot
        # rather than having to infer it from the row's own fields.
        "pick_meta": pick_meta,
        "pick_blockers": blockers,
        # The section 7b table: dispersion leg + ledger leg + dwell state, one
        # row per market, each with its reason. Published whether or not it
        # bars anything, because a gate a reader cannot see is a gate he
        # cannot hold the site to.
        "market_publishability": market_table,
        "team_bets": bets,
        "props_fair_lines": props_fair,
        # The section 7c value block: inert without both arming variables and
        # it SAYS so, priced off cached per-event snapshots when any exist.
        "props_value": props_value_bets(bets, props_fair, slots=slots,
                                        on_date=slate_date, evald=evald,
                                        market_table=market_table),
        "parlay_context": parlay_context(bets),
        "record": record_summary(record),
        "record_url": "/data/betting_record.json",
        "record_policy": ("Append only. Rows are never edited or deleted; a correction is "
                          "a new row. betting_export.write_record refuses any other write "
                          "and test_betting.py pins it."),
        # THE HEADER SENTENCE, identical to the one on every provisional row.
        "record_label": record_label,
        "record_storage": record_storage(),
        "honest_backtest": honest_backtest_progress(evald),
    }
    # VERBATIM ON THE ROW TOO. A slot lifted out of this payload and rendered
    # anywhere else still carries the qualifier; a client that shows the pick
    # and not the record header cannot drop it.
    for _slot in (pick, longshot):
        if _slot and record_label:
            _slot["provisional_label"] = record_label

    # REFUSE TO OVERWRITE A POPULATED BOARD WITH AN EMPTY ONE. This runs before
    # the preview is sliced and before either file is written, so the preview and
    # the full payload can never disagree about which slate is on the page.
    if not bets:
        payload = _carry_previous_board(
            payload, "; ".join(empty_reasons) or "no reason recorded", log_fn=log_fn)
    bets = payload["team_bets"]

    # SETTLE FIRST, THEN PUBLISH, THEN SUMMARIZE.
    #
    # Settling first is not cosmetic: the `settlement_current` blocker asks
    # whether every row past 36 hours is graded, and running it after the
    # publish decision would answer that question off the PREVIOUS build's
    # sidecar. A settling path that broke this afternoon would then let one more
    # row onto the record before anything noticed. Nothing new can be settled by
    # this pass anyway (a row posted tonight has no final score), so the order
    # costs nothing and closes a one-build blind spot.
    settlement = settle_record(rows=record, write=write)
    settle_map = {e["bet_id"]: e for e in settlement.get("picks") or [] if e.get("bet_id")}
    # THE PUBLIC RECORD. Evaluated after the stale-board guard, which nulls both
    # slots on a carried board by construction, so a day-old price can never be
    # published as tonight's claim. `maybe_publish_record` writes ONLY when every
    # blocker is open; the blocker list ships either way.
    publish = maybe_publish_record(payload, evald=evald, health=feed_health,
                                   settlement=settle_map,
                                   published_chain_sha=prev_chain,
                                   chain_anchor=prev_chain_src,
                                   write=write, log_fn=log_fn)
    payload["record_publish"] = {k: v for k, v in publish.items() if k != "blockers"}
    payload["record_publish_blockers"] = publish["blockers"]
    if publish.get("written"):
        record = load_record()
    payload["record"] = record_summary(record, settlement=settle_map)
    payload["record_storage"] = record_storage()
    # WHERE THE ANCHOR CAME FROM, on the payload, so "the rewrite check is armed"
    # is a claim a reader can check instead of one he has to believe. A `source`
    # still naming data/betting.json means no durable anchor exists yet.
    payload["record_chain_anchor"] = prev_chain_src
    payload["settlement_url"] = "/data/betting_settlement.json"
    payload["clv_url"] = "/data/betting_clv.json"
    # The DERIVED copy, re-rendered from the log on every build. It is published
    # by rsync and it is safe to lose: `git checkout -- .` reverting it between
    # builds costs nothing, which is the whole reason the log exists.
    if write:
        try:
            render_record(record)
        except OSError:
            log.warning("betting_export: could not re-render %s", RECORD_PATH.name)
        # STAMP THE ANCHOR LAST. The publish decision above was already made
        # against the PREVIOUS value; writing it any earlier would compare the
        # record against itself and the blocker would pass by construction.
        try:
            write_published_chain(record)
        except OSError:
            log.warning("betting_export: could not write %s; the next build will "
                        "fall back to the git-tracked board and the rewrite check "
                        "will be unarmed for one night", PUBLISHED_CHAIN_PATH.name)

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
        "longshot_of_the_day": payload["longshot_of_the_day"],
        "pick_reason": payload["pick_reason"],
        # THE LABEL TRAVELS WITH THE PICK. This key was omitted from the preview
        # for as long as the preview existed, so a free-tier reader received a
        # pick with no `provisional` flag, no floor and no basis beside it: the
        # one payload shape this module is built to prevent. It is the free
        # slice's job to carry the qualifier more than anyone's.
        "pick_meta": payload["pick_meta"],
        "pick_blockers": payload["pick_blockers"],
        # The market gate travels with the free slice for the same reason the
        # publish blockers do: it is part of the trust surface.
        "market_publishability": payload["market_publishability"],
        # PRE-REGISTERED, IN THE FREE SLICE. What the site refuses to publish is
        # a claim a reader can only hold it to if he can see it before the first
        # row exists, so it is not behind any gate.
        "record_publish_blockers": payload["record_publish_blockers"],
        "record_label": payload["record_label"],
        "record_storage": payload["record_storage"],
        "honest_backtest": payload["honest_backtest"],
        "n_games": payload["n_games"],
        "team_bets": bets[:PREVIEW_GAMES],
        "record": payload["record"],
        "gating_note": ("Preview slice. Everything is public during the Diamond preview; "
                        "this file is the seam a future gate would read."),
    }

    if write:
        _write(OUT_PATH, payload)
        _write(PREVIEW_PATH, preview)
        if log_fn:
            log_fn(f"betting_export: wrote {OUT_PATH.name} "
                   f"({len(bets)} games, odds={payload['status']['odds_feed']}"
                   f"{', STALE BOARD' if payload['status'].get('stale_board') else ''})")
            log_fn(f"betting_export: public record {payload['record']['n_rows']} row(s), "
                   f"chain {payload['record']['chain_sha'][:12]}, "
                   f"publish {publish['reason']}")
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
            "longshot": p["longshot_of_the_day"],
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
