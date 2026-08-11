# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One grader for every ledger, so three ledgers cannot disagree about a game.

WHY THIS EXISTS. There are now three records of the same slate and they answer
three different questions:

    published record     the picks the site stands behind        <= 2 a day
    paper bet ledger     what the model would have bet           per tag
    calibration ledger   the model probability on EVERY side     ~44 a day

They must never disagree about whether TBR +1.5 covered. Before this module the
grading logic lived inside `betting_shadow._settle_one` and could only be reused
by importing the paper-bet ledger, which is the wrong dependency for a file that
holds no bets. A second copy would be worse: two graders drift, and the drift
shows up as a ledger that says the model was right and another that says it was
wrong, on the same game, on the same night.

WHAT IT REFUSES TO DO. It never invents a final score, never grades a market it
does not understand, and returns None rather than guessing. `None` is a real
answer here: the caller leaves the row OPEN and reports the count, which is how
an ungradeable market becomes visible instead of becoming a loss.

THE PUSH IS NOT A LOSS. A push returns the stake. Scoring it as a loss would
understate every threshold's ROI and make gate 3 harder to clear for a reason
that has nothing to do with skill. On the calibration side a push is not a
binary outcome at all: the bet did not resolve, so it carries no Brier and no
log loss rather than carrying a zero.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

log = logging.getLogger("betting_settle")

#: Results a graded side may take. "push" is a real outcome, not a failure.
RESULTS = ("won", "lost", "push")

#: Clamp for the log loss. A model probability of exactly 0 or 1 on a side that
#: lost would be an infinite penalty, which would make the mean unreadable and
#: hand one row veto power over the whole ledger. 1e-6 caps a single wrong
#: certainty at 13.8 nats, which is punishing without being infinite.
LOG_LOSS_EPS = 1e-6


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def grade_side(*, market: str | None, side: str | None, point=None,
               home_runs=None, away_runs=None) -> str | None:
    """"won" / "lost" / "push", or None when this cannot be graded.

    None covers all of: no final score, a market this module does not know, and
    a spread or total with no line attached. Every one of those is a reason to
    leave the row open, and none of them is a reason to pick a side."""
    if home_runs is None or away_runs is None:
        return None
    try:
        hr, ar = int(home_runs), int(away_runs)
    except (TypeError, ValueError):
        return None

    if market == "moneyline":
        if hr == ar:
            # A finished regulation-length tie is not a real MLB outcome, but a
            # feed can carry a suspended game this way. Refunding is the only
            # answer that cannot invent a winner.
            return "push"
        won = (hr > ar) if side == "home" else (ar > hr)
        return "won" if won else "lost"

    if market == "runline":
        if point is None:
            return None
        margin = (hr - ar) if side == "home" else (ar - hr)
        adj = margin + float(point)
        if abs(adj) < 1e-9:
            return "push"
        return "won" if adj > 0 else "lost"

    if market == "total":
        if point is None:
            return None
        tot = hr + ar
        if abs(tot - float(point)) < 1e-9:
            return "push"
        over = tot > float(point)
        won = over if side == "over" else (not over)
        return "won" if won else "lost"

    return None


def profit_units(*, result: str, decimal=None, odds=None,
                 stake_units: float = 1.0):
    """Net units on a settled side, or None when no price can be recovered.

    A row with no usable price is NOT worth zero: zero is a graded break-even
    and would be counted as evidence. None keeps it out of every rate."""
    if result == "push":
        return 0.0
    dec = decimal
    if not dec and odds is not None:
        try:
            import betting_ingest as bi
            dec = bi.american_to_decimal(odds)
        except Exception:                                       # noqa: BLE001
            dec = None
    if not dec:
        return None
    stake = float(stake_units or 0.0)
    return round(stake * (float(dec) - 1.0), 4) if result == "won" else -stake


def binary_scores(model_prob, result: str) -> dict:
    """Brier and log loss for one side's binary outcome.

    NOT a bet score: no stake and no price enters here. A push carries neither,
    because the binary never resolved. This is the only scoring the calibration
    ledger does, and keeping it separate from `profit_units` is what stops a
    probability ledger from quietly becoming a P&L."""
    if result not in ("won", "lost") or model_prob is None:
        return {"brier": None, "log_loss": None}
    try:
        p = float(model_prob)
    except (TypeError, ValueError):
        return {"brier": None, "log_loss": None}
    y = 1.0 if result == "won" else 0.0
    pc = min(1.0 - LOG_LOSS_EPS, max(LOG_LOSS_EPS, p))
    return {
        "brier": round((p - y) ** 2, 6),
        "log_loss": round(-(y * math.log(pc) + (1.0 - y) * math.log(1.0 - pc)), 6),
    }


def index_games(games) -> dict:
    """game_pk -> the finished game. Rows with no pk are dropped rather than
    keyed on something that is not an identity."""
    return {g.get("game_pk"): g for g in (games or []) if g.get("game_pk")}


def load_completed(season: str | None = None) -> list[dict]:
    """Completed games, or [] with a warning. Best effort on purpose: a
    settlement pass that cannot read the schedule must leave every row open,
    not crash the nightly that also has a board to publish."""
    try:
        import betting_model as bm
        return bm.completed_games(season) if season else bm.completed_games()
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_settle: completed games unavailable (%s)", exc)
        return []


def run(*, games=None, log_fn=None) -> dict:
    """Settle every ledger that grades against a final score, in one pass.

    ONE READ OF THE SCHEDULE for both ledgers, which is not an optimisation:
    two reads a few seconds apart can straddle a feed update and grade the same
    game two ways. Each ledger is settled inside its own try, so a calibration
    failure cannot stop the paper bets from settling and vice versa."""
    if games is None:
        games = load_completed()
    out: dict = {"n_games": len(games or []), "shadow": None, "calibration": None}

    try:
        import betting_shadow
        out["shadow"] = betting_shadow.settle(games=games, log_fn=log_fn)
    except Exception as exc:                                    # noqa: BLE001
        log.exception("betting_settle: shadow ledger settlement failed")
        out["shadow"] = {"settled": 0, "reason": f"failed: {exc}"}

    try:
        from tools import betting_calibration
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_settle: calibration ledger unavailable (%s)", exc)
        out["calibration"] = {"settled": 0, "reason": f"unavailable: {exc}"}
        return out
    try:
        out["calibration"] = betting_calibration.settle(games=games, log_fn=log_fn)
    except Exception as exc:                                    # noqa: BLE001
        log.exception("betting_settle: calibration settlement failed")
        out["calibration"] = {"settled": 0, "reason": f"failed: {exc}"}
    return out


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default=None)
    args = ap.parse_args(argv)
    res = run(games=load_completed(args.season) if args.season else None,
              log_fn=print)
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
