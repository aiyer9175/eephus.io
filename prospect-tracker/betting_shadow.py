# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The shadow ledger: paper bets that build the evidence a real pick needs.

WHY THIS EXISTS. The betting model's third validation gate, `graded_price_history`,
wants settled bets carrying a taken price: `betting_model.sweep_min_edge` needs at
least 100 of them before any edge threshold can clear an ROI lower bound. Nothing
produced those rows. `min_edge_gate(..., graded_bets=None)` was never passed
anything, and the loop was closed against itself:

    publishing a pick needs min_edge
    min_edge needs settled picks
    settled picks need a published pick

So the ledger records what the model WOULD have bet, at the price actually on the
board, and settles it against the result. No money, no recommendation, no claim.
It is the only way to accumulate a price history without first pretending to a
confidence the model has not earned.

WHAT MAKES IT HONEST, and each of these is load-bearing:

  1. A shadow row is written BEFORE first pitch, at the price captured in that
     slate's open snapshot. A paper record assembled after the fact is worthless
     and this file refuses to build one: `settle` never invents a price, and a
     slate with no pre-game snapshot is skipped with its reason recorded.
  2. It is APPEND-ONLY, on the same discipline as the public record. A paper
     ledger that can be edited is worth less than no ledger, because it looks
     like evidence.
  3. It is stored SEPARATELY from data/betting_record.json and is never merged
     into it. The public record is bets the site stood behind; these are not.
     Anything reading the two together has to opt in.
  4. Every row carries `provisional: true`, the gate state at the time it was
     written, and (since 2026-08-07) the SLOT RULE that selected it, so a row
     logged under a policy floor can never later be misread as one logged under
     a measured threshold, and rows chosen by three different rules can never be
     pooled into one ROI by accident.

HOW THE MODEL IMPROVES FROM IT. As games resolve, three things move on their own:
the coefficients refit nightly on completed games, the vintage-graded sample grows
toward its 600, and this ledger accumulates settled prices. When all three gates
open, `sweep_min_edge` returns a MEASURED threshold and the provisional floor in
betting_export stops being used. Nothing here has to be re-run by hand for that
to happen.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("betting_shadow")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SHADOW_PATH = DATA_DIR / "betting_shadow.json"

#: Flat stake, always, exactly as the public record does it. A varying stake
#: would let a losing ledger be rescued by sizing after the fact.
STAKE_UNITS = 1.0

#: How many sides a slate may contribute. The gate needs 100 settled bets and a
#: season is ~180 slates, so one per slate would take two seasons. Five keeps
#: the sample honest (still the top of the board, not everything) while
#: reaching a usable n inside one season.
#:
#: RAISED FROM 3 ON 2026-08-07, when the page went to two published slots. The
#: budget is two slot picks plus the top three by EV, so a slate cannot log
#: fewer rows than it publishes: a published pick that never reached the ledger
#: would be a claim with no evidence trail behind it, which is the failure this
#: whole file exists to close.
MAX_PER_SLATE = 5

#: Which selection rule put a row in the ledger. Frozen at write time, on NEW
#: rows only, and never backfilled onto the rows already on disk: those were
#: written under a one-slot rule and stamping them now would assert a fact the
#: writer did not know.
#:
#: THE POINT OF THE TAG is that the future min-edge sweep can condition on it.
#: The three tags select on three different quantities (model probability inside
#: a price band, EV at a long price, EV anywhere), so pooling their ROI would
#: measure a mixture nobody bet, and a threshold fitted to that mixture would be
#: wrong for every slot it was applied to.
SLOT_TAGS = {"pick_of_the_day": "potd_band", "longshot_of_the_day": "longshot"}
DEFAULT_SLOT_TAG = "ev_rank"


class ShadowLedgerError(RuntimeError):
    """The ledger would have been mutated rather than appended to."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def shadow_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def load(path: Path | None = None) -> list[dict]:
    """The ledger as a list. A missing file is an empty ledger. A file that will
    not parse RAISES, for the same reason the public record does: returning []
    there hands the caller a blank baseline and lets the next write erase a
    history it could not read."""
    p = Path(path or SHADOW_PATH)
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShadowLedgerError(
            f"{p.name} exists but will not parse ({exc}); refusing to treat an "
            "unreadable ledger as an empty one") from exc
    if not isinstance(rows, list):
        raise ShadowLedgerError(f"{p.name} is not a JSON array")
    return rows


def _canon(row) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


#: Fields a settlement is allowed to fill in later. Everything else about a
#: published row is frozen: the price, the side, the edge and the date are the
#: claim, and a ledger that can revise them proves nothing.
SETTLEMENT_FIELDS = frozenset({
    "result", "settled_at", "profit_units", "final_home_runs", "final_away_runs",
})


def check_append_or_settle(existing: list[dict], proposed: list[dict]) -> None:
    """Raise unless `proposed` is `existing` plus new rows, where the only edits
    to existing rows are settlement fields moving from absent to present.

    This is looser than the public record's rule on purpose, and the looseness
    is bounded to exactly the fields a result fills in. A shadow bet is written
    before first pitch and cannot know its own outcome, so a strict
    append-only rule would make settlement impossible; allowing arbitrary edits
    would make the ledger meaningless. Neither is acceptable, so the seam is
    named explicitly and tested."""
    if len(proposed) < len(existing):
        raise ShadowLedgerError(
            f"ledger would shrink from {len(existing)} to {len(proposed)} rows")
    for i, old in enumerate(existing):
        new = proposed[i]
        if _canon(old) == _canon(new):
            continue
        changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
        illegal = changed - SETTLEMENT_FIELDS
        if illegal:
            raise ShadowLedgerError(
                f"row {i} (shadow_id={old.get('shadow_id')!r}) would change "
                f"{sorted(illegal)}; only {sorted(SETTLEMENT_FIELDS)} may be "
                "filled in after a row is written")
        for k in changed:
            if old.get(k) is not None and old.get(k) != new.get(k):
                raise ShadowLedgerError(
                    f"row {i}: {k} is already settled as {old.get(k)!r} and may "
                    f"not be changed to {new.get(k)!r}")
    seen = {r.get("shadow_id") for r in existing if r.get("shadow_id")}
    for r in proposed[len(existing):]:
        sid = r.get("shadow_id")
        if sid and sid in seen:
            raise ShadowLedgerError(f"shadow_id {sid!r} is already in the ledger")
        seen.add(sid)


def _write(rows: list[dict], path: Path | None = None) -> None:
    path = Path(path or SHADOW_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        try:
            from storage import _atomic_replace
        except Exception:                                     # noqa: BLE001
            _atomic_replace = None
        if _atomic_replace is not None:
            _atomic_replace(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def write(rows: list[dict], *, path: Path | None = None) -> list[dict]:
    existing = load(path)
    check_append_or_settle(existing, list(rows))
    _write(list(rows), path)
    return list(rows)


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------
def _row_key(r: dict) -> tuple:
    """What makes two references to the same side the same bet."""
    pt = r.get("point")
    return (r.get("game_pk"), r.get("market"), r.get("side"),
            None if pt is None else float(pt))


def candidates_from_board(payload: dict, *, min_edge: float,
                          max_per_slate: int = MAX_PER_SLATE,
                          slots: dict | None = None) -> list[dict]:
    """The sides this slate would have bet: the published slots, then the rest
    by EV.

    Reads the SAME board the page shows, so a shadow bet is never priced on
    numbers a reader could not have seen. A side with no book price is skipped
    rather than filled in from the model's own fair line: a paper bet at a
    price nobody offered is the one thing that would make this ledger a lie.

    `slots` is the payload's published slots keyed by their payload key
    (`pick_of_the_day`, `longshot_of_the_day`). They are taken FIRST, ahead of
    the EV ranking, because a slot pick can sit outside the top of the board on
    EV by construction: the headline slot selects on model probability inside a
    price band, and the whole point of the ledger is to make the published
    claims gradeable. Every other row still enters on EV and is tagged as such,
    so the sweep can separate the two rules later."""
    slate = payload.get("slate_date")
    out: list[dict] = []
    for b in payload.get("team_bets") or []:
        matchup = f"{(b.get('away') or {}).get('org')} at {(b.get('home') or {}).get('org')}"
        for market, rows in (("moneyline", b.get("moneyline") or []),
                             ("runline", b.get("runline") or []),
                             ("total", (b.get("total") or {}).get("sides") or [])):
            for r in rows or []:
                edge, odds = r.get("edge"), r.get("odds")
                if edge is None or odds is None or edge < min_edge:
                    continue
                if not r.get("book"):
                    continue
                out.append({
                    "slate_date": slate,
                    "game_pk": b.get("game_pk"),
                    "matchup": matchup,
                    "market": market,
                    "side": r.get("side"),
                    "selection": r.get("label"),
                    "point": r.get("point"),
                    "book": r.get("book"),
                    "odds_at_post": odds,
                    "decimal": r.get("decimal"),
                    "edge": round(float(edge), 5),
                    "model_prob": r.get("model_prob"),
                    "market_fair_prob": r.get("market_fair_prob"),
                    "ev_per_unit": r.get("ev_per_unit"),
                    "slot": DEFAULT_SLOT_TAG,
                })
    out.sort(key=lambda r: (r.get("ev_per_unit") is None, -(r.get("ev_per_unit") or 0)))

    tagged: dict[tuple, str] = {}
    for key, row in (slots or {}).items():
        tag = SLOT_TAGS.get(key)
        if not row or not tag:
            continue
        tagged.setdefault(_row_key(row), tag)
    if not tagged:
        return out[:max_per_slate]

    picked, seen = [], set()
    for cand in out:
        k = _row_key(cand)
        if k in tagged and k not in seen:
            picked.append({**cand, "slot": tagged[k]})
            seen.add(k)
    for cand in out:
        if len(picked) >= max_per_slate:
            break
        k = _row_key(cand)
        if k in seen:
            continue
        picked.append(cand)
        seen.add(k)
    return picked[:max_per_slate]


def record_slate(payload: dict, *, min_edge: float, gate_state: dict | None = None,
                 slots: dict | None = None,
                 path: Path | None = None, log_fn=None) -> dict:
    """Append this slate's shadow bets. Idempotent per (slate, game, market, side).

    Returns a summary rather than raising when there is nothing to record: an
    empty slate is a normal outcome and has to be distinguishable from a
    failure, which is why `reason` is always populated."""
    slate = payload.get("slate_date")
    if not slate:
        return {"written": 0, "reason": "payload carries no slate_date"}
    if (payload.get("status") or {}).get("odds_feed") != "ok":
        # No captured price means no honest paper bet. Recording the model's
        # own fair line here would be inventing the market.
        return {"written": 0, "slate_date": slate,
                "reason": "no odds snapshot for this slate; a shadow bet without "
                          "a real captured price is not evidence"}

    if slots is None:
        slots = {k: payload.get(k) for k in SLOT_TAGS}
    cands = candidates_from_board(payload, min_edge=min_edge, slots=slots)
    if not cands:
        return {"written": 0, "slate_date": slate,
                "reason": f"no side cleared the {min_edge:.1%} floor on this slate"}

    existing = load(path)
    seen = {r.get("shadow_id") for r in existing}
    posted = _now()
    new = []
    for c in cands:
        sid = shadow_id(c["slate_date"], c["game_pk"], c["market"], c["side"],
                        c.get("point"))
        if sid in seen:
            continue
        new.append({
            "shadow_id": sid,
            "posted_at": posted,
            "provisional": True,
            "stake_units": STAKE_UNITS,
            # The threshold and gate state AT THE TIME OF WRITING. Without this
            # a row logged under a policy floor is indistinguishable later from
            # one logged under a measured threshold, and the sample would mix
            # two different selection rules.
            "min_edge_used": round(float(min_edge), 5),
            "gate_state": gate_state or {},
            "result": None, "settled_at": None, "profit_units": None,
            **c,
        })
    if not new:
        return {"written": 0, "slate_date": slate,
                "reason": "every qualifying side for this slate is already logged"}

    write(existing + new, path=path)
    by_slot = {}
    for r in new:
        by_slot[r.get("slot") or DEFAULT_SLOT_TAG] = \
            by_slot.get(r.get("slot") or DEFAULT_SLOT_TAG, 0) + 1
    if log_fn:
        log_fn(f"betting_shadow: logged {len(new)} paper bet(s) for {slate} "
               f"at a {min_edge:.1%} floor "
               f"({', '.join(f'{k} {v}' for k, v in sorted(by_slot.items()))})")
    return {"written": len(new), "slate_date": slate, "reason": "ok",
            "by_slot": by_slot, "rows": new}


# ---------------------------------------------------------------------------
# settlement
# ---------------------------------------------------------------------------
def _settle_one(row: dict, game: dict) -> dict | None:
    """Grade one shadow bet against a final score. None when the market is one
    this function cannot grade, which is recorded rather than guessed."""
    hr, ar = game.get("home_runs"), game.get("away_runs")
    if hr is None or ar is None:
        return None
    hr, ar = int(hr), int(ar)
    side, market = row.get("side"), row.get("market")
    point = row.get("point")

    if market == "moneyline":
        if hr == ar:
            return {"result": "push"}
        won = (hr > ar) if side == "home" else (ar > hr)
        return {"result": "won" if won else "lost"}

    if market == "runline":
        if point is None:
            return None
        margin = (hr - ar) if side == "home" else (ar - hr)
        adj = margin + float(point)
        if abs(adj) < 1e-9:
            return {"result": "push"}
        return {"result": "won" if adj > 0 else "lost"}

    if market == "total":
        if point is None:
            return None
        tot = hr + ar
        if abs(tot - float(point)) < 1e-9:
            return {"result": "push"}
        over = tot > float(point)
        won = over if side == "over" else (not over)
        return {"result": "won" if won else "lost"}

    return None


def _profit(row: dict, result: str) -> float | None:
    if result == "push":
        return 0.0
    stake = float(row.get("stake_units") or STAKE_UNITS)
    dec = row.get("decimal")
    if not dec:
        try:
            import betting_ingest as bi
            dec = bi.american_to_decimal(row.get("odds_at_post"))
        except Exception:                                     # noqa: BLE001
            dec = None
    if not dec:
        return None
    return round(stake * (float(dec) - 1.0), 4) if result == "won" else -stake


def settle(*, games: list[dict] | None = None, path: Path | None = None,
           log_fn=None) -> dict:
    """Fill in results for any shadow bet whose game has finished.

    Idempotent: a row already carrying a result is left exactly as it is, and
    check_append_or_settle would refuse the write anyway."""
    rows = load(path)
    if not rows:
        return {"settled": 0, "open": 0, "reason": "ledger is empty"}

    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games()
        except Exception as exc:                              # noqa: BLE001
            log.warning("betting_shadow: could not load completed games (%s); "
                        "nothing settled", exc)
            return {"settled": 0, "open": sum(1 for r in rows if not r.get("result")),
                    "reason": f"completed games unavailable: {exc}"}

    by_pk = {g.get("game_pk"): g for g in (games or []) if g.get("game_pk")}
    out, n_settled, ungradeable = [], 0, 0
    for r in rows:
        if r.get("result") or not r.get("game_pk"):
            out.append(r)
            continue
        g = by_pk.get(r["game_pk"])
        if not g:
            out.append(r)
            continue
        verdict = _settle_one(r, g)
        if not verdict:
            ungradeable += 1
            out.append(r)
            continue
        res = verdict["result"]
        out.append({**r, "result": res, "settled_at": _now(),
                    "profit_units": _profit(r, res),
                    "final_home_runs": g.get("home_runs"),
                    "final_away_runs": g.get("away_runs")})
        n_settled += 1

    if n_settled:
        write(out, path=path)
        if log_fn:
            log_fn(f"betting_shadow: settled {n_settled} paper bet(s)")
    if ungradeable:
        log.warning("betting_shadow: %d row(s) have a finished game but a market "
                    "this module cannot grade; they stay open rather than being "
                    "guessed", ungradeable)
    return {"settled": n_settled,
            "open": sum(1 for r in out if not r.get("result")),
            "ungradeable": ungradeable,
            "reason": "ok"}


# ---------------------------------------------------------------------------
# the shape betting_model.sweep_min_edge wants
# ---------------------------------------------------------------------------
def graded_bets(*, path: Path | None = None) -> list[dict]:
    """Settled shadow bets as {edge, decimal, won} rows, which is exactly what
    `betting_model.sweep_min_edge` consumes.

    Pushes are EXCLUDED rather than scored as losses. A push returns the stake,
    so counting it as a loss would understate every threshold's ROI and make the
    gate harder to clear for a reason that has nothing to do with skill."""
    out = []
    for r in load(path):
        if r.get("result") not in ("won", "lost"):
            continue
        dec = r.get("decimal")
        if not dec:
            try:
                import betting_ingest as bi
                dec = bi.american_to_decimal(r.get("odds_at_post"))
            except Exception:                                 # noqa: BLE001
                dec = None
        if r.get("edge") is None or not dec:
            continue
        out.append({"edge": float(r["edge"]), "decimal": float(dec),
                    "won": r["result"] == "won"})
    return out


def _tally(rows: list[dict]) -> dict:
    """Won/lost/push, net units and the two rates over one set of rows.

    Every rate is None until there is something to divide by. A 0% win rate over
    zero settled bets is a lie that looks like a measurement, and this module
    exists to produce evidence, so it may not manufacture any."""
    settled = [r for r in rows if r.get("result") in ("won", "lost", "push")]
    wins = sum(1 for r in settled if r["result"] == "won")
    losses = sum(1 for r in settled if r["result"] == "lost")
    pushes = sum(1 for r in settled if r["result"] == "push")
    profits = [r["profit_units"] for r in settled
               if isinstance(r.get("profit_units"), (int, float))]
    staked = sum(float(r.get("stake_units") or STAKE_UNITS)
                 for r in settled if r["result"] != "push")
    net = round(sum(profits), 3) if profits else None
    gradeable = [r for r in settled if r["result"] in ("won", "lost")]
    return {
        "n_rows": len(rows),
        "n_open": len(rows) - len(settled),
        "n_settled": len(settled),
        "won": wins, "lost": losses, "push": pushes,
        "net_units": net,
        "roi": (round(net / staked, 4) if net is not None and staked else None),
        "win_rate": (round(wins / len(gradeable), 4) if gradeable else None),
    }


def summary(*, path: Path | None = None) -> dict:
    """What the ledger has accumulated, for the page and for the gate.

    `by_slot` splits the same tally by the selection rule that wrote each row.
    It is reported and NOT pooled anywhere, because the tags name three
    different selection rules and a pooled ROI would measure a mixture nobody
    bet. Rows written before 2026-08-07 carry no tag and are counted under
    `untagged`, which is honest about what they are: rows from the one-slot era,
    selected on EV alone."""
    rows = load(path)
    out = _tally(rows)
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r.get("slot") or "untagged", []).append(r)
    out["by_slot"] = {k: _tally(v) for k, v in sorted(buckets.items())}
    # The number the third gate is actually waiting on.
    out["n_for_min_edge_sweep"] = len(graded_bets(path=path))
    out["min_bets_for_sweep"] = 100
    return out
