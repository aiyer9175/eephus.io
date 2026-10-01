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

PROPS GRADE OFF THE BOX SCORE, NOT THE RUN SCORE (2026-08-19). A player count
cannot be read out of a final score, which is why every props row stayed OPEN
until this grader existed (docs/diamond-betting.md section 7c calls it the
named unlock). `grade_props` reads the player's statline out of the cached
StatsAPI game feed (.cache/game_feeds/<game_pk>.json), the same bytes the rest
of the pipeline already trusts, and `settle_props` walks both ledgers' open
props rows in the same pass `run` already makes for the team markets.

THE VOID IS NOT A PUSH AND NEITHER IS A LOSS. A player who never appears in
the box score of a FINAL game, or appears with no statline in the market's
facet (a listed batter who never batted, a pitcher who never threw), is a
voided bet: the stake comes back, exactly like a push, and the row settles as
"void" so it can never be re-graded or counted as evidence. A name the feed
cannot match unambiguously stays OPEN instead: an ambiguous or missing match
could be a normalization failure, and grading it void would quietly discard
evidence.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("betting_settle")

ROOT = Path(__file__).resolve().parent

#: Results a graded side may take. "push" is a real outcome, not a failure.
RESULTS = ("won", "lost", "push")

#: Results a graded PROPS side may take. "void" is the book convention for a
#: player with no action in a finished game: stake returned, no evidence
#: created. Team sides never void, so the tuple is separate on purpose.
PROPS_RESULTS = ("won", "lost", "push", "void")

#: Clamp for the log loss. A model probability of exactly 0 or 1 on a side that
#: lost would be an infinite penalty, which would make the mean unreadable and
#: hand one row veto power over the whole ledger. 1e-6 caps a single wrong
#: certainty at 13.8 nats, which is punishing without being infinite.
LOG_LOSS_EPS = 1e-6

#: THE POSTSEASON VOCABULARY (owner decision 2026-10-01, INT-A1; task
#: BET_POSTSEASON_PRICING; docs/diamond-betting.md section 8a). /betting/ prices
#: postseason games although the model has never been fitted or graded on one.
#: It lives HERE because this is the one module every ledger already imports:
#: the public record, the paper ledger and the calibration ledger read one
#: definition of "a postseason row", so no two of them can disagree about which
#: rows are their own sub-ledger.
#:
#: StatsAPI gameType codes: F wild card, D division series, L league
#: championship series, W World Series. A row with no `game_type` field is a
#: REGULAR-SEASON row, because every row written before 2026-10-01 came off a
#: board that carried regular-season games only (fantasy_schedule fetched
#: gameType=R), and the field is written on postseason rows alone so that a
#: regular-season row is byte-identical to the rows before it.
POSTSEASON_GAME_TYPES = ("F", "D", "L", "W")
REGULAR_SEASON_GAME_TYPE = "R"

#: The visible label every postseason card, slot, paper row and record row
#: carries, verbatim. The orchestrator's binding condition 1 names the words.
POSTSEASON_LABEL = "never graded on a postseason game"

#: Human names for the four codes, for copy only. Nothing branches on them.
POSTSEASON_ROUND_NAMES = {"F": "Wild Card Series", "D": "Division Series",
                          "L": "League Championship Series", "W": "World Series"}


def game_type_of(row: dict | None) -> str:
    """The StatsAPI gameType a ledger row or board card was written for.

    Absent reads as R: see POSTSEASON_GAME_TYPES for why that reading is a
    fact about the rows already on disk and not a guess."""
    gt = str((row or {}).get("game_type") or "").strip().upper()
    return gt or REGULAR_SEASON_GAME_TYPE


def is_postseason(row: dict | None) -> bool:
    """True for a row written off a postseason game (F, D, L or W)."""
    return game_type_of(row) in POSTSEASON_GAME_TYPES


def postseason_fields(game_type) -> dict:
    """The two keys a postseason row carries, or {} for any other game type.

    Empty for a regular-season game ON PURPOSE: the keys are absent rather
    than null so a regular-season row, card or record line is byte-identical
    to the ones written before postseason pricing existed."""
    gt = str(game_type or "").strip().upper()
    if gt not in POSTSEASON_GAME_TYPES:
        return {}
    return {"game_type": gt, "postseason_label": POSTSEASON_LABEL}


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


# ---------------------------------------------------------------------------
# props: box-score grading (2026-08-19, the section 7c named unlock)
# ---------------------------------------------------------------------------
#: Where the StatsAPI game feeds already live. The props grader reads the SAME
#: cache betting_model's completed-game walk reads, so a props result and a
#: team result on one game come out of one set of bytes.
PROPS_FEED_DIR = ROOT / ".cache" / "game_feeds"

PROPS_PREFIX = "props_"

#: The four registered props markets (docs/diamond-betting.md section 7c,
#: betting_ingest.PROPS_MARKETS with the props_ prefix) -> which box-score
#: facet and which StatsAPI stat key settles them. Restated rather than
#: imported so this module keeps zero heavy dependencies; test_props_grader.py
#: pins the correspondence against betting_ingest.PROPS_MARKETS so the copies
#: cannot drift. A market not in this table is a market this module does not
#: understand, and it grades None, never a guess.
PROPS_STAT_KEYS = {
    "props_pitcher_strikeouts": ("pitching", "strikeOuts"),
    "props_batter_total_bases": ("batting", "totalBases"),
    "props_batter_hits": ("batting", "hits"),
    "props_batter_home_runs": ("batting", "homeRuns"),
}

#: Generational suffixes the odds feed and StatsAPI disagree about carrying.
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def norm_player(name) -> str:
    """One casefolded, accent-stripped, punctuation-free key for a player name.

    The odds feed writes "Ronald Acuna Jr." where StatsAPI writes "Ronald
    Acuña Jr."; NFKD plus dropping the combining marks makes those the same
    key. Periods and commas go too (J.D. vs JD). This is a MATCHING key, never
    a display string."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace(".", "").replace(",", "").casefold()
    return re.sub(r"\s+", " ", s).strip()


def _strip_suffix(norm: str) -> str:
    parts = norm.split(" ")
    if len(parts) > 2 and parts[-1] in _NAME_SUFFIXES:
        return " ".join(parts[:-1])
    return norm


def load_boxscore(game_pk, *, feed_dir=None) -> dict | None:
    """The per-player statlines of one cached game feed, or None.

    None covers a missing feed and an unparseable one, both of which mean the
    row stays open and the next pass retries: the feed cache fills as its own
    job runs, and "not cached yet" must never grade anything.

    `final` is carried rather than filtered on, so the caller can distinguish
    "the feed says the game is still live" (stay open) from "no feed at all"
    with one read. Player keys are `norm_player` keys mapped to LISTS: two
    players with one normalized name in one game is a real (rare) state, and
    collapsing them would grade one man's bet on another man's night."""
    p = Path(feed_dir or PROPS_FEED_DIR) / f"{game_pk}.json"
    if not p.exists():
        return None
    try:
        feed = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("betting_settle: game feed %s will not parse (%s); props "
                    "rows on it stay open", p.name, exc)
        return None
    status = ((feed.get("gameData") or {}).get("status") or {})
    live = feed.get("liveData") or {}
    ls_teams = ((live.get("linescore") or {}).get("teams") or {})
    players: dict[str, list] = {}
    stripped: dict[str, list] = {}
    for side in ("home", "away"):
        team = (((live.get("boxscore") or {}).get("teams") or {}).get(side) or {})
        for pl in (team.get("players") or {}).values():
            nm = norm_player((pl.get("person") or {}).get("fullName"))
            if not nm:
                continue
            stats = pl.get("stats") or {}
            entry = {"name": (pl.get("person") or {}).get("fullName"),
                     "batting": stats.get("batting") or {},
                     "pitching": stats.get("pitching") or {}}
            players.setdefault(nm, []).append(entry)
            stripped.setdefault(_strip_suffix(nm), []).append(entry)
    return {
        "game_pk": game_pk,
        "final": status.get("abstractGameState") == "Final",
        "home_runs": (ls_teams.get("home") or {}).get("runs"),
        "away_runs": (ls_teams.get("away") or {}).get("runs"),
        "players": players,
        "players_stripped": stripped,
    }


def props_actual(box: dict, *, market: str, player) -> tuple:
    """("ok", count) | ("void", reason) | ("open", reason) for one player.

    void  the game is final and the book's rule says no action: the player is
          not in the box score at all (scratched, not on the roster), or is
          there with an EMPTY statline in the market's facet (a bench bat who
          never hit, a listed arm that never threw).
    open  this function cannot say: an empty or ambiguous name key, two
          players whose names normalize identically, or a statline missing
          the market's key. Every one of those could be a matching failure,
          and a matching failure graded as void would silently discard
          evidence, so the row waits for a human instead."""
    group, key = PROPS_STAT_KEYS[market]
    nm = norm_player(player)
    if not nm:
        return ("open", "row carries no player name")
    hits = (box.get("players") or {}).get(nm)
    if not hits:
        hits = (box.get("players_stripped") or {}).get(_strip_suffix(nm))
    if not hits:
        return ("void", "player is not in the final box score (no action)")
    if len(hits) > 1:
        return ("open", f"{len(hits)} box-score players normalize to {nm!r}; "
                        "refusing to guess which one was bet")
    stats = hits[0].get(group) or {}
    if not stats:
        return ("void", f"player has no {group} line in the final box score "
                        "(no action in this market's facet)")
    val = stats.get(key)
    if val is None:
        return ("open", f"the {group} statline carries no {key!r} key")
    try:
        return ("ok", int(val))
    except (TypeError, ValueError):
        return ("open", f"{key} is not a count: {val!r}")


def grade_props(*, market: str | None, side: str | None, point=None,
                player=None, box: dict | None = None) -> str | None:
    """"won" / "lost" / "push" / "void", or None when this cannot be graded.

    The same contract as `grade_side`, one level down: None is a real answer
    (no feed, a live game, an unknown market, a missing line, an ambiguous
    name) and every None leaves the row OPEN. The push is the whole-number
    line landing exactly, the same convention `total` uses. The void is the
    no-action case, and only a FINAL game may void: a scratch is only a
    scratch once the game it was scratched from is over."""
    if not box or not box.get("final"):
        return None
    if market not in PROPS_STAT_KEYS or side not in ("over", "under"):
        return None
    if point is None:
        return None
    try:
        line = float(point)
    except (TypeError, ValueError):
        return None
    status, actual = props_actual(box, market=market, player=player)
    if status == "open":
        return None
    if status == "void":
        return "void"
    diff = float(actual) - line
    if abs(diff) < 1e-9:
        return "push"
    over = diff > 0
    won = over if side == "over" else (not over)
    return "won" if won else "lost"


def settle_props(*, shadow_path=None, cal_path=None, feed_dir=None,
                 log_fn=None) -> dict:
    """Grade every open props row in both ledgers against the box scores.

    INERT-SAFE BY CONSTRUCTION: with zero props rows stored (the state on
    2026-08-19) this reads the two ledgers it was going to read anyway, finds
    no open props row, and returns without touching a feed file, writing a
    byte, or logging a line. The min_edge clocks per props tag start ONLY
    when rows exist AND settle here; nothing about this function can start
    them early.

    Both ledgers settle through the ONE grader above, the same rule that put
    the team markets' grading in this module: two graders drift, and drift
    shows up as two ledgers disagreeing about the same statline. The shadow
    write goes through betting_shadow.write, so its append-or-settle check
    still proves only settlement fields moved; the calibration write goes
    through betting_calibration.append as PHASE_SETTLED events, so its phase
    field discipline still holds."""
    import betting_shadow
    out = {"shadow": {"settled": 0, "open": 0, "void": 0},
           "calibration": {"settled": 0, "open": 0, "void": 0},
           "reason": "ok"}

    sh_rows = betting_shadow.load(shadow_path)
    sh_open = [r for r in sh_rows
               if str(r.get("market") or "").startswith(PROPS_PREFIX)
               and not r.get("result")]

    try:
        from tools import betting_calibration
    except Exception as exc:                                    # noqa: BLE001
        betting_calibration = None
        cal_open = []
        out["calibration"] = {"settled": 0, "open": 0, "void": 0,
                              "reason": f"unavailable: {exc}"}
    if betting_calibration is not None:
        cal_rows = betting_calibration.rows(path=cal_path)
        cal_open = [r for r in cal_rows
                    if str(r.get("market") or "").startswith(PROPS_PREFIX)
                    and not r.get("result")]

    if not sh_open and not cal_open:
        out["reason"] = "no open props rows in any ledger"
        return out

    # One feed read per game, shared by both ledgers, the same one-read rule
    # `run` applies to the schedule.
    boxes: dict = {}
    for r in sh_open + cal_open:
        pk = r.get("game_pk")
        if pk is not None and pk not in boxes:
            boxes[pk] = load_boxscore(pk, feed_dir=feed_dir)

    # --- shadow ledger ---
    updated, n_sh, n_sh_void = [], 0, 0
    for r in sh_rows:
        if (not str(r.get("market") or "").startswith(PROPS_PREFIX)
                or r.get("result") or r.get("game_pk") is None):
            updated.append(r)
            continue
        box = boxes.get(r["game_pk"])
        res = grade_props(market=r.get("market"), side=r.get("side"),
                          point=r.get("point"), player=r.get("player"),
                          box=box)
        if not res:
            updated.append(r)
            continue
        updated.append({**r, "result": res, "settled_at": _now(),
                        "profit_units": profit_units(
                            result=res, decimal=r.get("decimal"),
                            odds=r.get("odds_at_post"),
                            stake_units=float(r.get("stake_units") or 1.0)),
                        "final_home_runs": box.get("home_runs"),
                        "final_away_runs": box.get("away_runs")})
        n_sh += 1
        n_sh_void += 1 if res == "void" else 0
    if n_sh:
        betting_shadow.write(updated, path=shadow_path)
    out["shadow"] = {"settled": n_sh, "void": n_sh_void,
                     "open": sum(1 for r in updated
                                 if str(r.get("market") or "").startswith(PROPS_PREFIX)
                                 and not r.get("result"))}

    # --- calibration ledger ---
    if betting_calibration is not None:
        events, n_cal_void = [], 0
        written_at = _now()
        for r in cal_open:
            box = boxes.get(r.get("game_pk"))
            res = grade_props(market=r.get("market"), side=r.get("side"),
                              point=r.get("point"), player=r.get("player"),
                              box=box)
            if not res:
                continue
            scores = binary_scores(r.get("model_prob"), res)
            events.append({
                "cal_id": r["cal_id"],
                "phase": betting_calibration.PHASE_SETTLED,
                "written_at": written_at, "result": res,
                "brier": scores["brier"], "log_loss": scores["log_loss"],
                "final_home_runs": (box or {}).get("home_runs"),
                "final_away_runs": (box or {}).get("away_runs"),
                "settled_at": written_at,
            })
            n_cal_void += 1 if res == "void" else 0
        n_cal = betting_calibration.append(events, path=cal_path)
        out["calibration"] = {"settled": n_cal, "void": n_cal_void,
                              "open": len(cal_open) - n_cal}

    if log_fn and (n_sh or out["calibration"].get("settled")):
        log_fn(f"betting_settle: settled {n_sh} props paper bet(s) and "
               f"{out['calibration'].get('settled', 0)} props calibration "
               "side(s) off the box scores")
    return out


def profit_units(*, result: str, decimal=None, odds=None,
                 stake_units: float = 1.0):
    """Net units on a settled side, or None when no price can be recovered.

    A row with no usable price is NOT worth zero: zero is a graded break-even
    and would be counted as evidence. None keeps it out of every rate.

    A VOID RETURNS THE STAKE, exactly like a push. It is listed separately
    because it is a different fact (the bet never had action, rather than the
    line being hit exactly), but the money is the same money."""
    if result in ("push", "void"):
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
        games = bm.completed_games(season) if season else bm.completed_games()
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_settle: completed games unavailable (%s)", exc)
        return []
    # POSTSEASON FINALS SETTLE POSTSEASON ROWS (2026-10-01, INT-A1). They come
    # from their own cache, `betting_model.postseason_finals`, and are joined
    # HERE, on the settlement path only: completed_games() is the coefficient
    # fit's input and stays regular-season, so no postseason score can reach a
    # refit, a backtest or any gate's frame through this list. A failure leaves
    # the postseason rows open with "game not final", which is a named reason.
    try:
        post = bm.postseason_finals(season)
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_settle: postseason finals unavailable (%s)", exc)
        post = []
    have = {g.get("game_pk") for g in games}
    return list(games) + [g for g in post if g.get("game_pk") not in have]


def run(*, games=None, log_fn=None) -> dict:
    """Settle every ledger that grades against a final score, in one pass.

    ONE READ OF THE SCHEDULE for both ledgers, which is not an optimisation:
    two reads a few seconds apart can straddle a feed update and grade the same
    game two ways. Each ledger is settled inside its own try, so a calibration
    failure cannot stop the paper bets from settling and vice versa.

    PROPS SETTLE FIRST (2026-08-19), in the same pass, off the box scores.
    First because the two team legs below skip any row that already carries a
    result: a props row graded here is invisible to them, while a props row
    graded after them would have already tripped the shadow leg's "finished
    game, ungradeable market" warning on every nightly. With zero props rows
    stored the leg is a silent no-op and the output says so."""
    if games is None:
        games = load_completed()
    out: dict = {"n_games": len(games or []), "props": None, "shadow": None,
                 "calibration": None}

    try:
        out["props"] = settle_props(log_fn=log_fn)
    except Exception as exc:                                    # noqa: BLE001
        log.exception("betting_settle: props settlement failed")
        out["props"] = {"settled": 0, "reason": f"failed: {exc}"}

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
