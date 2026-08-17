# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The calibration ledger: the model probability on EVERY priced side, scored.

THIS IS NOT A BET LEDGER, AND THAT IS THE ENTIRE POINT.

docs/diamond-betting.md section 7a forbids pooling the slot tags, because the
tags name three different SELECTION rules and a pooled ROI measures a mixture
nobody bet. That rule binds any ledger that carries a stake. This one does not
carry a stake, so the rule does not bind it, and it is the only ledger that can
grow fast enough to make "the model improves each day" a measurement rather
than a slogan:

    published record     picks the site stands behind   <= 2 a day
    paper bet ledger     what the model would have bet   8 to 14 a day, per tag
    calibration ledger   every priced side, scored      ~44 binaries a day

Measured on the cached snapshots (tools/betting_floor_census.py, 2026-08-09):
44.4 priced sides per slate day on average, 66 to 90 on a full slate.

WHAT KEEPS IT OUTSIDE THE TAG RULE, enforced and not merely intended:

  * NO stake, NO bet_id, NO ROI, NO profit, EVER. `_FORBIDDEN_KEYS` is checked
    on every write and the write RAISES. A probability ledger that grows a P&L
    column has silently become a fourth betting record with no selection rule
    attached, and its number would be quoted as if it were one.
  * The closing-price move is called `market_move_pct`, NEVER `clv_pct`. CLV is
    a property of a POSITION - it says what the price you took was worth. This
    file holds no positions. Two different names is what stops the two being
    concatenated by a later reader who sees the same units.
  * It is scored with Brier and log loss on the binary outcome only. Those are
    the losses a probability has; ROI is a loss a bet has.

SAY THIS OUT LOUD WHEREVER IT IS PUBLISHED: model calibration is NOT gate 1.
Gate 1 is the vintage-graded moneyline sample beating the home-field baseline on
games the model could not see. A well calibrated board tells you the
probabilities are honest; it does not tell you they beat a constant, and it
never licenses a pick.

THE FILE FORMAT. .cache/betting/calibration.jsonl, append-only, one JSON object
per line, each carrying a `phase`:

    open     written before first pitch, from the same board the page shows
    close    the closing price at the SAME book the open row's best price came
             from, appended by the close job
    settled  the result and the two binary losses

A folded read (`rows()`) returns one row per priced side per slate with every
field filled in. Nothing is ever rewritten, so a settlement cannot quietly edit
a price: a later phase may only fill the fields that phase owns, and an attempt
to touch an earlier phase's field is DROPPED and counted in `n_field_conflicts`.

RUN IT:
    python tools/betting_calibration.py --summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import betting_settle as bset                                   # noqa: E402

log = logging.getLogger("betting_calibration")

LEDGER_PATH = ROOT / ".cache" / "betting" / "calibration.jsonl"

PHASE_OPEN = "open"
PHASE_CLOSE = "close"
PHASE_SETTLED = "settled"

#: Fields each phase is allowed to write. A later phase may fill only its own.
OPEN_FIELDS = frozenset({
    "cal_id", "phase", "written_at", "slate_date", "captured_at", "game_pk",
    "matchup", "market", "side", "label", "point", "model_prob", "p_push",
    "market_fair_prob", "fair_book", "hold_pct", "best_odds", "best_book",
    "best_decimal", "n_books_on_line", "inputs_vintage_date",
    # 2026-08-16, section 7c: props rows name their player. Team rows never
    # carry the key, which is what keeps the two populations separable.
    "player",
})
CLOSE_FIELDS = frozenset({
    "cal_id", "phase", "written_at", "close_odds", "close_decimal",
    "close_book", "market_move_pct", "closed_at",
})
SETTLE_FIELDS = frozenset({
    "cal_id", "phase", "written_at", "result", "brier", "log_loss",
    "final_home_runs", "final_away_runs", "settled_at",
})
PHASE_FIELDS = {PHASE_OPEN: OPEN_FIELDS, PHASE_CLOSE: CLOSE_FIELDS,
                PHASE_SETTLED: SETTLE_FIELDS}

#: Keys that would turn this into a bet ledger. Checked on EVERY write.
#: `clv_pct` is here beside the money keys on purpose: it is the name the
#: published record uses for a position's closing line value, and letting it
#: appear here is what would allow the two to be pooled.
_FORBIDDEN_KEYS = frozenset({
    "stake", "stake_units", "bet_id", "shadow_id", "profit", "profit_units",
    "roi", "net_units", "units", "clv_pct", "kelly", "kelly_full", "slot",
    "edge", "ev_per_unit",
})


class CalibrationLedgerError(RuntimeError):
    """A write would have made this a bet ledger, or rewritten history."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cal_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _check_clean(row: dict) -> None:
    bad = sorted(set(row) & _FORBIDDEN_KEYS)
    if bad:
        raise CalibrationLedgerError(
            f"calibration row carries {bad}; this ledger holds probabilities, "
            "not positions. A stake, a bet id, an ROI or a clv_pct here would "
            "make it a fourth betting record with no selection rule attached.")


def _check_phase(row: dict) -> None:
    phase = row.get("phase")
    allowed = PHASE_FIELDS.get(phase)
    if allowed is None:
        raise CalibrationLedgerError(f"unknown phase {phase!r}")
    extra = sorted(set(row) - allowed)
    if extra:
        raise CalibrationLedgerError(
            f"phase {phase!r} may not write {extra}; each phase owns its own "
            "fields so a settlement can never edit a price")


# ---------------------------------------------------------------------------
# raw append-only log
# ---------------------------------------------------------------------------
def append(events: list[dict], *, path: Path | None = None) -> int:
    """Append events. Never rewrites, never reorders, never deduplicates.

    Deduplication is the CALLER's job via `rows()`, because dropping a
    duplicate at write time would need a read of the whole file on every
    append and would make the writer's behaviour depend on what is already
    there. An append-only log that a writer can be talked out of appending to
    is not append-only."""
    p = Path(path or LEDGER_PATH)
    if not events:
        return 0
    for e in events:
        _check_clean(e)
        _check_phase(e)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(e, sort_keys=True, separators=(",", ":"),
                               default=str) + "\n" for e in events)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)
        fh.flush()
        os.fsync(fh.fileno())
    return len(events)


def read_events(*, path: Path | None = None) -> list[dict]:
    """Every event, in file order. A line that will not parse is SKIPPED and
    counted in the log rather than raising: a truncated final line from a
    killed process must not make the whole history unreadable, which is the one
    failure mode an append-only text log actually has."""
    p = Path(path or LEDGER_PATH)
    if not p.exists():
        return []
    out, bad = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
    if bad:
        log.warning("betting_calibration: skipped %d unparseable line(s) in %s",
                    bad, p.name)
    return out


def rows(*, path: Path | None = None) -> list[dict]:
    """The folded view: one row per priced side per slate, every phase merged.

    Order is first-seen order, which is slate order, which is deterministic."""
    folded: dict[str, dict] = {}
    order: list[str] = []
    conflicts = 0
    for e in read_events(path=path):
        cid = e.get("cal_id")
        if not cid:
            continue
        phase = e.get("phase")
        allowed = PHASE_FIELDS.get(phase) or frozenset()
        if cid not in folded:
            if phase != PHASE_OPEN:
                # A close or settle event with no open row is orphaned. Keeping
                # it would create a row with a result and no probability, which
                # would then be scored.
                continue
            folded[cid] = {}
            order.append(cid)
        cur = folded[cid]
        for k, v in e.items():
            if k in ("phase", "written_at"):
                continue
            if k not in allowed:
                conflicts += 1
                continue
            if phase != PHASE_OPEN and k in OPEN_FIELDS and k != "cal_id":
                conflicts += 1
                continue
            cur[k] = v
    if conflicts:
        log.warning("betting_calibration: dropped %d out-of-phase field write(s)",
                    conflicts)
    return [folded[c] for c in order]


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------
def _sides(payload: dict):
    """Every priced side on the board, flattened, with the market named and the
    game's de-vig receipts carried along."""
    for b in payload.get("team_bets") or []:
        mk = b.get("market") or {}
        matchup = (f"{(b.get('away') or {}).get('org')} at "
                   f"{(b.get('home') or {}).get('org')}")
        for market, rws in (("moneyline", b.get("moneyline") or []),
                            ("runline", b.get("runline") or []),
                            ("total", (b.get("total") or {}).get("sides") or [])):
            fair_book = mk.get(f"{market}_fair_book")
            hold = mk.get(f"{market}_hold_pct")
            n_books = ((mk.get("n_books_rejected") or {}).get(market) or {}).get("on_line")
            for r in rws or []:
                yield {"market": market, "matchup": matchup, "bet": b, "row": r,
                       "fair_book": fair_book, "hold_pct": hold,
                       "n_books_on_line": n_books}


def record_slate(payload: dict, *, path: Path | None = None,
                 log_fn=None) -> dict:
    """One open row per priced side on this slate.

    NO FLOOR. That is the difference between this and the paper ledger: a side
    the model rated at 0.31 against a market fair 0.33 is worthless as a bet and
    is exactly as informative about calibration as the one it liked. Filtering
    to the sides the model liked would produce a calibration curve measured only
    where the model disagrees with the market, which is the sample least able to
    tell you whether the probabilities are honest.

    Idempotent per (slate, game, market, side, point): a re-run appends nothing
    because `rows()` already holds those ids."""
    slate = payload.get("slate_date")
    if not slate:
        return {"written": 0, "reason": "payload carries no slate_date"}
    if (payload.get("status") or {}).get("odds_feed") != "ok":
        return {"written": 0, "slate_date": slate,
                "reason": "no odds snapshot for this slate; a market_fair_prob "
                          "the board never showed is not a calibration row"}

    known = {r.get("cal_id") for r in rows(path=path)}
    captured = ((payload.get("status") or {}).get("odds_captured_at")
                or payload.get("generated_at"))
    # The date the team inputs were true, which is what a later re-scoring
    # needs in order to know which model produced this probability.
    vintage = (((payload.get("status") or {}).get("team_input_sources") or {})
               .get("offense") or {}).get("as_of")
    written_at = _now()
    events, n_unpriced = [], 0
    for s in _sides(payload):
        r, b = s["row"], s["bet"]
        if r.get("model_prob") is None:
            continue
        if r.get("odds") is None or not r.get("book"):
            # A fair line with no book behind it is a model output, not a
            # market observation. It is still scoreable in principle, and it is
            # left out anyway: the row would have no market_fair_prob to be
            # calibrated AGAINST and would silently change what the per-market
            # hold and move blocks are averaging over.
            n_unpriced += 1
            continue
        cid = cal_id(slate, b.get("game_pk"), s["market"], r.get("side"),
                     r.get("point"))
        if cid in known:
            continue
        known.add(cid)
        events.append({
            "cal_id": cid, "phase": PHASE_OPEN, "written_at": written_at,
            "slate_date": slate, "captured_at": captured,
            "game_pk": b.get("game_pk"), "matchup": s["matchup"],
            "market": s["market"], "side": r.get("side"),
            "label": r.get("label"), "point": r.get("point"),
            "model_prob": r.get("model_prob"),
            "p_push": r.get("p_push"),
            "market_fair_prob": r.get("market_fair_prob"),
            "fair_book": s["fair_book"], "hold_pct": s["hold_pct"],
            "best_odds": r.get("odds"), "best_book": r.get("book"),
            "best_decimal": r.get("decimal"),
            "n_books_on_line": s["n_books_on_line"],
            "inputs_vintage_date": vintage,
        })
    n = append(events, path=path)
    if log_fn and n:
        log_fn(f"betting_calibration: logged {n} priced side(s) for {slate} "
               f"(no floor; {n_unpriced} unpriced side(s) skipped)")
    return {"written": n, "slate_date": slate,
            "n_unpriced_skipped": n_unpriced,
            "reason": "ok" if n else "every priced side for this slate is already logged"}


def record_props_slate(props_value: dict, *, path: Path | None = None,
                       log_fn=None) -> dict:
    """One open row per priced PROPS side (2026-08-16, section 7c).

    Same discipline as record_slate: NO floor (both sides of every priced
    pair, liked or not), idempotent on the cal_id, and the market name is the
    props_<key> form so these rows can never pool into a team market's
    statistic by key collision. betting_settle cannot grade a player count
    off a run score, so these rows stay OPEN rather than being guessed; the
    section 7b table says so wherever their n appears."""
    pv = props_value or {}
    slate = pv.get("slate_date")
    if not slate:
        return {"written": 0, "reason": "props_value carries no slate_date"}
    rows_in = pv.get("rows") or []
    if not rows_in:
        return {"written": 0, "slate_date": slate,
                "reason": "no priced props sides on this build"}
    known = {r.get("cal_id") for r in rows(path=path)}
    written_at = _now()
    events = []
    for r in rows_in:
        if r.get("model_prob") is None:
            continue
        if r.get("odds") is None or not r.get("book"):
            continue
        market = r.get("market")
        if market not in PROPS_CAL_MARKETS:
            continue
        cid = cal_id(slate, r.get("game_pk"), market, r.get("player"),
                     r.get("side"), r.get("point"))
        if cid in known:
            continue
        known.add(cid)
        events.append({
            "cal_id": cid, "phase": PHASE_OPEN, "written_at": written_at,
            "slate_date": slate, "captured_at": r.get("captured_at"),
            "game_pk": r.get("game_pk"), "matchup": r.get("matchup"),
            "market": market, "side": r.get("side"), "player": r.get("player"),
            "label": r.get("label"), "point": r.get("point"),
            "model_prob": r.get("model_prob"), "p_push": r.get("p_push"),
            "market_fair_prob": r.get("market_fair_prob"),
            "fair_book": r.get("fair_book"), "hold_pct": r.get("hold_pct"),
            "best_odds": r.get("odds"), "best_book": r.get("book"),
            "best_decimal": r.get("decimal"),
            "n_books_on_line": r.get("n_books_on_line"),
        })
    n = append(events, path=path)
    if log_fn and n:
        log_fn(f"betting_calibration: logged {n} priced props side(s) for {slate}")
    return {"written": n, "slate_date": slate,
            "reason": "ok" if n else "every priced props side is already logged"}


def append_close(events_by_key: dict, *, path: Path | None = None,
                 log_fn=None) -> dict:
    """Attach the closing price to every open row that has one.

    `events_by_key` is {(game_pk, market, side, point): {"odds":, "decimal":,
    "book":}} built by the caller from the CLOSE snapshot, priced at the SAME
    book the open row's best price came from. The book match is the caller's
    job and this function verifies it: a close taken at a different book is a
    different market, and the difference between two books is not a move.

    `market_move_pct` is (implied_prob_at_close / implied_prob_at_open - 1) in
    percent, so a POSITIVE number means the market moved TOWARD the side. It is
    deliberately not clv_pct: this ledger holds no position, so there is no
    price anybody took and no value to have captured."""
    out, n_no_close, n_book_mismatch = [], 0, 0
    written_at = _now()
    for r in rows(path=path):
        if r.get("close_odds") is not None:
            continue
        key = (r.get("game_pk"), r.get("market"), r.get("side"),
               None if r.get("point") is None else float(r["point"]))
        c = (events_by_key or {}).get(key)
        if not c:
            n_no_close += 1
            continue
        if c.get("book") and r.get("best_book") and c["book"] != r["best_book"]:
            n_book_mismatch += 1
            continue
        dec_open, dec_close = r.get("best_decimal"), c.get("decimal")
        move = None
        if dec_open and dec_close:
            move = round(((1.0 / float(dec_close)) / (1.0 / float(dec_open)) - 1.0)
                         * 100.0, 3)
        out.append({"cal_id": r["cal_id"], "phase": PHASE_CLOSE,
                    "written_at": written_at, "close_odds": c.get("odds"),
                    "close_decimal": dec_close, "close_book": c.get("book"),
                    "market_move_pct": move, "closed_at": c.get("captured_at")})
    n = append(out, path=path)
    if log_fn and n:
        log_fn(f"betting_calibration: attached {n} closing price(s)")
    return {"closed": n, "n_no_close": n_no_close,
            "n_book_mismatch": n_book_mismatch, "reason": "ok"}


def settle(*, games=None, path: Path | None = None, log_fn=None) -> dict:
    """Grade every open row whose game has finished, and score the binary.

    Uses betting_settle so this can never disagree with the paper ledger about
    the same game."""
    cur = rows(path=path)
    if not cur:
        return {"settled": 0, "open": 0, "reason": "ledger is empty"}
    if games is None:
        games = bset.load_completed()
    by_pk = bset.index_games(games)

    out, ungradeable = [], 0
    written_at = _now()
    for r in cur:
        if r.get("result") or not r.get("game_pk"):
            continue
        g = by_pk.get(r["game_pk"])
        if not g:
            continue
        res = bset.grade_side(market=r.get("market"), side=r.get("side"),
                              point=r.get("point"),
                              home_runs=g.get("home_runs"),
                              away_runs=g.get("away_runs"))
        if not res:
            ungradeable += 1
            continue
        scores = bset.binary_scores(r.get("model_prob"), res)
        out.append({"cal_id": r["cal_id"], "phase": PHASE_SETTLED,
                    "written_at": written_at, "result": res,
                    "brier": scores["brier"], "log_loss": scores["log_loss"],
                    "final_home_runs": g.get("home_runs"),
                    "final_away_runs": g.get("away_runs"),
                    "settled_at": written_at})
    n = append(out, path=path)
    if log_fn and n:
        log_fn(f"betting_calibration: settled {n} side(s)")
    return {"settled": n,
            "open": sum(1 for r in cur if not r.get("result")) - n,
            "ungradeable": ungradeable, "reason": "ok"}


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
#: Ten equal bins on model probability. Ten because the brief asked for ten and
#: because a decile is the coarsest grid on which a board that is 0.05 too hot
#: in one region is still visible; finer bins on ~44 rows a day would be noise
#: with a label on it.
N_BINS = 10

#: The props market names this ledger logs as DISTINCT markets (2026-08-16,
#: section 7c). Restated from betting_ingest.PROPS_MARKETS with the props_
#: prefix rather than imported, for the same reason GATE_MIN_GAMES is
#: restated: this module keeps its single betting_settle dependency, and the
#: props tests pin the correspondence so the copies cannot drift.
PROPS_CAL_MARKETS = ("props_pitcher_strikeouts", "props_batter_total_bases",
                     "props_batter_hits", "props_batter_home_runs")

#: One side per market, for the statistics that both sides make degenerate.
#: BOTH sides of every market are in this ledger on purpose - that is what makes
#: it a calibration ledger and not a bet ledger - and the price of it is that a
#: pooled mean probability and a pooled hit rate are 0.5 by arithmetic. Scoring
#: the home side, the home runline and the over recovers a real measurement,
#: and the choice is fixed rather than data dependent so it cannot be picked
#: after the fact to flatter the number. Props markets score the OVER, fixed
#: here 2026-08-16 before any props row existed.
CANONICAL_SIDES = {"moneyline": "home", "runline": "home", "total": "over",
                   **{m: "over" for m in PROPS_CAL_MARKETS}}


def _mean(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 6) if vals else None


def calibration_bins(settled: list[dict], *, n_bins: int = N_BINS) -> list[dict]:
    """Predicted vs realised in each decile of model probability.

    Every bin is reported, INCLUDING the empty ones, with n and nulls. A
    calibration table that silently drops its empty bins hides exactly the
    information a reader needs, which is where the board has no mass."""
    buckets: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in settled:
        p = r.get("model_prob")
        if p is None or r.get("result") not in ("won", "lost"):
            continue
        i = min(n_bins - 1, max(0, int(float(p) * n_bins)))
        buckets[i].append(r)
    out = []
    for i, rws in enumerate(buckets):
        lo, hi = i / n_bins, (i + 1) / n_bins
        won = sum(1 for r in rws if r["result"] == "won")
        out.append({
            "bin": f"{lo:.1f}-{hi:.1f}", "n": len(rws),
            "pred": _mean([r.get("model_prob") for r in rws]),
            "actual": (round(won / len(rws), 4) if rws else None),
            "brier": _mean([r.get("brier") for r in rws]),
        })
    return out


def summary(*, path: Path | None = None) -> dict:
    """What the ledger knows, per market and pooled.

    POOLED IS LEGITIMATE HERE and nowhere else in the betting module: these are
    probabilities on every side, not bets chosen by a rule, so there is no
    selection to condition on. That is stated rather than assumed because the
    identical word means the opposite thing one file over."""
    cur = rows(path=path)
    settled = [r for r in cur if r.get("result") in ("won", "lost")]
    pushes = [r for r in cur if r.get("result") == "push"]
    closed = [r for r in cur if r.get("market_move_pct") is not None]

    def _block(rws):
        s = [r for r in rws if r.get("result") in ("won", "lost")]
        c = [r for r in s if CANONICAL_SIDES.get(r.get("market")) == r.get("side")]
        c_mean = _mean([r.get("model_prob") for r in c])
        c_hit = (round(sum(1 for r in c if r["result"] == "won") / len(c), 4)
                 if c else None)
        return {
            "n_rows": len(rws),
            "n_settled": len(s),
            # Brier and log loss ARE meaningful over both sides. Brier(p) +
            # Brier(1-p) = 2(p-y)^2, so the mean over the pair is exactly the
            # per-game score; nothing is double counted and nothing cancels.
            "brier": _mean([r.get("brier") for r in s]),
            "log_loss": _mean([r.get("log_loss") for r in s]),
            "mean_hold_pct": _mean([r.get("hold_pct") for r in rws]),
            # A MEAN PROBABILITY AND A HIT RATE OVER BOTH SIDES ARE 0.5 BY
            # CONSTRUCTION and are not reported at all. Both sides of a binary
            # are in this ledger, their model probabilities sum to 1, and
            # exactly one of them wins, so the two numbers are arithmetic, not
            # measurement. They are computed on ONE canonical side per market
            # instead, where the gap between them is the model's actual bias.
            "canonical_side": {
                "n": len(c),
                "sides": dict(CANONICAL_SIDES),
                "mean_model_prob": c_mean,
                "mean_market_fair_prob": _mean([r.get("market_fair_prob") for r in c]),
                "hit_rate": c_hit,
                "bias": (round(c_mean - c_hit, 4)
                         if c_mean is not None and c_hit is not None else None),
                "note": ("one side per market (home, home runline, over) so the mean "
                         "probability and the hit rate are not forced to 0.5 by the "
                         "presence of both sides"),
            },
        }

    by_market: dict[str, dict] = {}
    for m in ("moneyline", "runline", "total"):
        by_market[m] = _block([r for r in cur if r.get("market") == m])

    slates = sorted({r.get("slate_date") for r in cur if r.get("slate_date")})
    return {
        "n_rows": len(cur),
        "n_settled": len(settled),
        "n_push": len(pushes),
        "n_open": len(cur) - len(settled) - len(pushes),
        "n_with_close": len(closed),
        "n_slate_days": len(slates),
        "slate_days": slates,
        "pooled": _block(cur),
        "by_market": by_market,
        "bins": calibration_bins(settled),
        "market_move_pct": {
            "n": len(closed),
            "mean": _mean([r.get("market_move_pct") for r in closed]),
            "share_positive": (round(sum(1 for r in closed
                                         if r["market_move_pct"] > 0) / len(closed), 4)
                               if closed else None),
            "note": ("the market's own move between the open and close price at the "
                     "SAME book. This is not CLV: no position was taken, so there is "
                     "nothing whose value could have been captured. Never pool this "
                     "with the published record's clv_pct."),
        },
        "not_gate_1": ("calibration is NOT the model's first validation gate. Gate 1 "
                       "is the vintage-graded moneyline sample beating the home-field "
                       "baseline on games the model could not see. Honest "
                       "probabilities do not license a pick."),
    }


# ---------------------------------------------------------------------------
# the market-level publishability statistic (docs/diamond-betting.md 7b)
# ---------------------------------------------------------------------------
#: The three constants of the section 7b ledger leg, pre-registered 2026-08-16
#: BEFORE this code was written. GATE_MIN_GAMES mirrors
#: betting_shadow.MIN_BETS_FOR_SWEEP so the module carries one small-sample
#: floor rather than two, and GATE_Z is betting_model.Z_95_ONE_SIDED; both are
#: restated here rather than imported so this ledger module keeps its single
#: betting_settle dependency, and test_betting_market_gate.py pins the equality
#: so the copies cannot drift. The dwell and trailing window live in
#: betting_export beside the state they govern.
GATE_MIN_GAMES = 100
GATE_Z = 1.645

GATE_MARKETS = ("moneyline", "runline", "total") + PROPS_CAL_MARKETS


def canonical_settled_games(rws: list[dict]) -> dict:
    """{market: [one settled canonical-side row per GAME, ledger order]}.

    Both sides of every market are in this ledger on purpose, and Brier(p)
    equals Brier(1-p), so the two sides of one game are the same evidence
    twice: a gate that counted per-side rows would reach any n-floor at half
    the games it claims. One row per (market, game_pk), the CANONICAL_SIDES
    side only, first occurrence kept so a second priced line on the same game
    cannot count the game again.

    Props rows (2026-08-16, section 7c) add the PLAYER to the key: ten
    batter_hits players in one game are ten pieces of evidence, while one
    player at two lines is one, the same rationale that counts one team game
    at two totals once. Team rows carry no player key, so their dedup is
    byte-identical to what it was."""
    out: dict[str, list[dict]] = {m: [] for m in GATE_MARKETS}
    seen: set[tuple] = set()
    for r in rws:
        m = r.get("market")
        if m not in out:
            continue
        if r.get("result") not in ("won", "lost"):
            continue
        if CANONICAL_SIDES.get(m) != r.get("side"):
            continue
        key = (m, r.get("game_pk"), r.get("player"))
        if key in seen:
            continue
        seen.add(key)
        out[m].append(r)
    return out


def _gate_stats(games: list[dict]) -> dict:
    """The section 7b statistic over one market's canonical games.

    delta_vs_coin is mean per-game Brier minus 0.25, POSITIVE meaning worse
    than a coin; t is that delta over its standard error; worse_than_coin_95
    needs the n floor AND the one-sided 95% lower bound above zero. The n
    floor is part of the verdict, not a separate flag, because a t of 3.0 on
    12 games is not a resolution and must not read as one."""
    briers = [float(r["brier"]) for r in games
              if isinstance(r.get("brier"), (int, float))]
    n = len(briers)
    if n == 0:
        return {"n_games": 0, "brier": None, "delta_vs_coin": None, "t": None,
                "worse_than_coin_95": False}
    mean = sum(briers) / n
    delta = mean - 0.25
    t = None
    if n >= 2:
        var = sum((b - mean) ** 2 for b in briers) / (n - 1)
        sd = var ** 0.5
        if sd > 0:
            t = delta / (sd / n ** 0.5)
    return {
        "n_games": n,
        "brier": round(mean, 6),
        "delta_vs_coin": round(delta, 6),
        "t": (round(t, 4) if t is not None else None),
        "worse_than_coin_95": bool(n >= GATE_MIN_GAMES
                                   and t is not None and t >= GATE_Z),
    }


def market_gate(*, path: Path | None = None, trailing: int | None = None) -> dict:
    """Per-market {n_games, brier, delta_vs_coin, t, worse_than_coin_95} from
    the settled CANONICAL-SIDE games (docs/diamond-betting.md section 7b).

    `trailing` restricts each market to its LAST that-many settled canonical
    games in ledger order, which is the re-open form of the statistic; None is
    the full-sample form the closure test runs on. This function is a
    measurement only: the dwell, the state and the publish decision live in
    betting_export, so the ledger module cannot be talked into holding an
    opinion about what may be published."""
    by_market = canonical_settled_games(rows(path=path))
    out = {}
    for m in GATE_MARKETS:
        games = by_market[m]
        if trailing is not None:
            games = games[-int(trailing):]
        stats = _gate_stats(games)
        stats["n_min"] = GATE_MIN_GAMES
        stats["z"] = GATE_Z
        if trailing is not None:
            stats["trailing"] = int(trailing)
        out[m] = stats
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--settle", action="store_true")
    ap.add_argument("--market-gate", action="store_true", dest="market_gate")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)
    if args.settle:
        print(json.dumps(settle(log_fn=print), indent=1, default=str))
    if args.market_gate:
        print(json.dumps({"full": market_gate(),
                          "trailing_200": market_gate(trailing=200)},
                         indent=1, default=str))
        return 0
    out = summary()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    if args.summary or not args.settle:
        print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
