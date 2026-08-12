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
from datetime import datetime, timezone
from pathlib import Path

import betting_settle

log = logging.getLogger("betting_shadow")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

#: THE LEDGER LIVES OUTSIDE data/ FOR THE SAME REASON THE RECORD DOES
#: (2026-08-09). data/betting_shadow.json was untracked AND not gitignored, which
#: is the worst of the three states: `git checkout -- .` could not touch it
#: today, and one `git add -A` would track it and arm exactly the defect that
#: destroyed the public record - a row written at 21:00 reverted to the committed
#: copy at 03:10 with no error anywhere. It also would not survive a box rebuild,
#: because only `.cache/` is on the documented backup list.
#:
#: So `.cache/betting/shadow.json` is the SOURCE OF TRUTH (untracked via
#: `.cache/`, inside the directory deploy/WEBMASTER.md tells the webmaster to
#: back up) and `data/betting_shadow.json` is a DERIVED re-render, published by
#: rsync because data_catalog advertises it, and safe to lose.
#:
#: IT IS A JSON ARRAY AND NOT A JSONL LOG, unlike the public record, and the
#: difference is not laziness: settlement legitimately fills `result`,
#: `profit_units` and the final scores in on rows already written (see
#: SETTLEMENT_FIELDS), which a one-line-per-append log cannot express without an
#: envelope-per-mutation format this ledger does not have. The append-or-settle
#: rule is enforced in process by `check_append_or_settle` instead, and the
#: durability the storage seam buys is the part that was missing.
BETTING_CACHE_DIR = ROOT / ".cache" / "betting"
SHADOW_CACHE_PATH = BETTING_CACHE_DIR / "shadow.json"
SHADOW_DERIVED_PATH = DATA_DIR / "betting_shadow.json"

#: The default every path-less call resolves to. Kept as a module constant
#: because it is the name every reader already looks for.
SHADOW_PATH = SHADOW_CACHE_PATH

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

#: THE FOURTH TAG, added 2026-08-09. "every side on the board that cleared the
#: floor", uncapped.
#:
#: WHY A FOURTH TAG AND NOT A BIGGER CAP. The three tags above are capped, and a
#: cap is part of a selection rule: `ev_rank` means "the best three by EV that
#: the two slots did not already take", so its ROI is a statement about the top
#: of the board and not about the board. Raising MAX_PER_SLATE would silently
#: rewrite what `ev_rank` means, and every row already on disk would be
#: reinterpreted under a rule its writer never applied. So the uncapped
#: population gets its own name instead, and the three existing tags keep the
#: budgets they have always had. `board_all` is the ONE sweep that can
#: legitimately set a threshold for a "best side on the board" rule, because it
#: is the only tag whose membership is not truncated.
#:
#: MEASURED COST (tools/betting_floor_census.py, 2026-08-09, 4 cached snapshots,
#: 7 (snapshot, slate) cells): a full slate carries 15 to 19 sides over the 6%
#: floor, 8.6 per slate day averaged over the partial captures too. So board_all
#: reaches 100 settled rows in roughly 7 to 12 slate days, while ev_rank at 3 a
#: day needs 34 and each single-pick slot needs about 100.
BOARD_ALL_TAG = "board_all"

#: How many rows a slate may contribute PER TAG. None means uncapped.
#:
#: The three capped budgets sum to MAX_PER_SLATE and are exactly the split the
#: shipped selector already applied (two slot picks, then the top three by EV),
#: written down so it can be read instead of inferred from the loop below.
MAX_PER_SLATE_BY_TAG = {
    "potd_band": 1,
    "longshot": 1,
    DEFAULT_SLOT_TAG: 3,
    BOARD_ALL_TAG: None,
}

#: Every tag a row may be a member of, plus the pre-tag era's bucket.
KNOWN_TAGS = (*sorted(SLOT_TAGS.values()), DEFAULT_SLOT_TAG, BOARD_ALL_TAG)
UNTAGGED = "untagged"

#: The sweep's sample-size floor, per tag. Named here because the per-tag rule
#: is what makes the number expensive: 100 settled rows POOLED is one clock, 100
#: PER TAG is four clocks running at four different speeds, and the slowest of
#: them is roughly 3x slower to open than the pooled number it replaces. That
#: cost is accepted deliberately - a threshold fitted to a mixture of four
#: selection rules is wrong for every one of them.
MIN_BETS_FOR_SWEEP = 100


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
    history it could not read.

    TWO BACKENDS, ONE ANSWER, exactly like `betting_export.load_record`. With no
    explicit path the durable copy under `.cache/betting/` wins whenever it
    exists; when it does not, the legacy `data/betting_shadow.json` is read, so
    a box that already has rows there loses none of them and the first write
    moves them across. An explicit `path` is honoured verbatim, which is what
    every test in this module passes."""
    if path is None:
        path = SHADOW_CACHE_PATH if SHADOW_CACHE_PATH.exists() else SHADOW_DERIVED_PATH
    p = Path(path)
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


def _write_one(rows: list[dict], path: Path) -> None:
    path = Path(path)
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


def _write(rows: list[dict], path: Path | None = None) -> None:
    """Write the DURABLE copy, then re-render the derived one.

    Durable first, and the order is load-bearing: a crash between the two leaves
    the authoritative ledger correct and the published copy one write stale,
    which the next build fixes. The other order would leave the published copy
    claiming rows the ledger cannot prove."""
    if path is not None:
        _write_one(list(rows), Path(path))
        return
    _write_one(list(rows), SHADOW_CACHE_PATH)
    try:
        _write_one(list(rows), SHADOW_DERIVED_PATH)
    except OSError:
        log.warning("betting_shadow: could not re-render the derived %s; the "
                    "durable ledger at %s is unaffected",
                    SHADOW_DERIVED_PATH.name, SHADOW_CACHE_PATH)


def write(rows: list[dict], *, path: Path | None = None) -> list[dict]:
    existing = load(path)
    check_append_or_settle(existing, list(rows))
    _write(list(rows), path)
    return list(rows)


def ensure_ledger() -> dict:
    """Make the DURABLE ledger exist, migrating whatever data/ already holds.

    NOT A WRITE OF EVIDENCE and it cannot become one: it copies exactly the rows
    the ledger already has. It exists because migration would otherwise only
    happen on a night that actually logged something, and a slate on which
    nothing cleared the floor is a normal outcome - so a box could sit for a week
    with its only ledger in the undurable place while every night reported
    success."""
    if SHADOW_CACHE_PATH.exists():
        return {"created": False, "migrated": 0, "path": str(SHADOW_CACHE_PATH)}
    legacy = load(SHADOW_DERIVED_PATH)
    _write_one(legacy, SHADOW_CACHE_PATH)
    log.info("betting_shadow: created the durable ledger at %s (migrated %d row(s) "
             "out of %s)", SHADOW_CACHE_PATH, len(legacy), SHADOW_DERIVED_PATH.name)
    return {"created": True, "migrated": len(legacy), "path": str(SHADOW_CACHE_PATH)}


def storage() -> dict:
    """WHICH copy of the paper ledger is authoritative right now.

    Reported by the nightly and by `summary()`, because "the evidence base for
    gate 3 is stored somewhere a checkout or a box rebuild can delete" is a
    finding, not a footnote."""
    durable = SHADOW_CACHE_PATH.exists()
    return {
        "backend": "cache" if durable else "data_fallback",
        "authoritative_path": str(SHADOW_CACHE_PATH if durable else SHADOW_DERIVED_PATH),
        "derived_path": str(SHADOW_DERIVED_PATH),
        "durable": durable,
        "n_rows": len(load()),
        "why": ("the ledger lives under .cache/betting/, which is gitignored (so no "
                "`git add -A` can arm the reverted-by-checkout defect) and is on the "
                "documented backup list in deploy/WEBMASTER.md"
                if durable else
                "no durable ledger exists yet; the rows are being read from "
                "data/betting_shadow.json, which is not on the backup list. The next "
                "write moves them to .cache/betting/shadow.json"),
    }


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
                          slots: dict | None = None,
                          include_board_all: bool = False,
                          budget_by_tag: dict | None = None) -> list[dict]:
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
    so the sweep can separate the two rules later.

    `include_board_all` adds the UNCAPPED tag: every remaining side that cleared
    the floor is returned too, tagged `board_all`, and the capped rows pick up
    `board_all` as a second membership so the uncapped population is genuinely
    every clearing side and not just the ones the cap rejected.

    IT IS OFF BY DEFAULT AND THAT IS DELIBERATE. Turning it on triples the rows
    a slate writes (measured: 8.6 clearing sides a slate day against a 5-row
    budget), which is a volume policy and belongs at the call site where the
    cost is visible, not in a default that changes what every existing caller
    does. With it off nothing about this function's output changes, down to the
    absence of the `tags` key."""
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

    # THE PER-TAG BUDGET IS ENFORCED HERE, and until 2026-08-12 it was not.
    # MAX_PER_SLATE_BY_TAG has always declared ev_rank: 3 and the comment above
    # it claims that is "exactly the split the shipped selector already
    # applied". The selector never read the dict: it filled to the GLOBAL
    # max_per_slate, so on any slate where the two slots did not both pick,
    # ev_rank absorbed the difference. Measured on the live ledger, slate
    # 2026-08-09 is potd_band 1 + ev_rank 4, and one of those four ev_rank rows
    # is a quarter of that tag's entire sweepable evidence for gate 3.
    #
    # This is not cosmetic: a cap is part of a selection rule. `ev_rank` is
    # defined two screens up as "the best three by EV that the two slots did not
    # already take", and its ROI is only a statement about the top of the board
    # if that is what it holds. Rows already on disk are NOT retagged - they
    # were selected under the unenforced rule and rewriting them would reinterpret
    # evidence under a rule its writer never applied, which is the exact hazard
    # BOARD_ALL_TAG was introduced to avoid.
    budget = dict(MAX_PER_SLATE_BY_TAG if budget_by_tag is None else budget_by_tag)

    def _room(tag: str, taken: dict) -> bool:
        cap = budget.get(tag, None)
        return cap is None or taken.get(tag, 0) < cap

    picked, seen, taken = [], set(), {}
    for cand in out:
        k = _row_key(cand)
        if k in tagged and k not in seen and _room(tagged[k], taken):
            picked.append({**cand, "slot": tagged[k]})
            seen.add(k)
            taken[tagged[k]] = taken.get(tagged[k], 0) + 1
    for cand in out:
        if len(picked) >= max_per_slate:
            break
        k = _row_key(cand)
        if k in seen or not _room(DEFAULT_SLOT_TAG, taken):
            continue
        picked.append(cand)
        seen.add(k)
        taken[DEFAULT_SLOT_TAG] = taken.get(DEFAULT_SLOT_TAG, 0) + 1
    picked = picked[:max_per_slate]
    seen = {_row_key(c) for c in picked}

    if not include_board_all:
        return picked
    # Every capped row is also on the board, so it is a board_all member too.
    # `tags` is the membership list; `slot` stays the CAPPED rule that chose the
    # row, so nothing about the existing three tags is widened.
    out_rows = [{**c, "tags": sorted({c.get("slot") or DEFAULT_SLOT_TAG,
                                      BOARD_ALL_TAG})} for c in picked]
    for cand in out:
        if _row_key(cand) in seen:
            continue
        out_rows.append({**cand, "slot": BOARD_ALL_TAG, "tags": [BOARD_ALL_TAG]})
    return out_rows


def record_slate(payload: dict, *, min_edge: float, gate_state: dict | None = None,
                 slots: dict | None = None, include_board_all: bool = False,
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

    # THE BUDGET IS PER SLATE, NOT PER CALL. The ledger is loaded BEFORE the
    # candidates are chosen so the slate's remaining room can be handed to the
    # selector. It used to be loaded after, and each call got a fresh full
    # budget: the pipeline runs more than once a day, and slate 2026-08-11 ended
    # up with 7 capped rows against MAX_PER_SLATE 5 (ev_rank 5 against its 3),
    # the second pass adding rows off a LATER board at a different capture time.
    # "The top three by EV for this slate" then meant "the top three of build 1
    # plus the top two of build 2", which is not a selection rule anyone
    # registered. A second pass can still add board_all rows, which are uncapped
    # by design and are the tag whose whole justification is that its membership
    # is not truncated.
    existing = load(path)
    used: dict[str, int] = {}
    for r in existing:
        if r.get("slate_date") != slate:
            continue
        tag = r.get("slot") or DEFAULT_SLOT_TAG
        used[tag] = used.get(tag, 0) + 1
    remaining = {t: (None if MAX_PER_SLATE_BY_TAG.get(t) is None
                     else max(0, MAX_PER_SLATE_BY_TAG[t] - used.get(t, 0)))
                 for t in MAX_PER_SLATE_BY_TAG}
    room = MAX_PER_SLATE - sum(
        n for t, n in used.items() if MAX_PER_SLATE_BY_TAG.get(t) is not None)

    cands = candidates_from_board(payload, min_edge=min_edge, slots=slots,
                                  include_board_all=include_board_all,
                                  max_per_slate=max(0, room),
                                  budget_by_tag=remaining)
    if not cands:
        # TWO different empty results, and they must not share a sentence. With
        # a per-slate budget an empty candidate list no longer implies nothing
        # cleared the floor: on a re-run the sides are all still there and the
        # budget is simply spent. Reporting that as "no side cleared" would read
        # as a dead board on exactly the nights the board was fine.
        # Ask the board directly rather than inferring from the budget
        # arithmetic: the global room can still be positive while the only tag
        # with candidates is spent, which is exactly the re-run case.
        cleared_ignoring_budget = candidates_from_board(
            payload, min_edge=min_edge, slots=slots,
            include_board_all=include_board_all,
            budget_by_tag={t: None for t in MAX_PER_SLATE_BY_TAG})
        if used and cleared_ignoring_budget:
            return {"written": 0, "slate_date": slate,
                    "reason": "every capped row for this slate is already "
                              "logged and its per-tag budget is spent; a later "
                              "pass may only add uncapped board_all rows"}
        return {"written": 0, "slate_date": slate,
                "reason": f"no side cleared the {min_edge:.1%} floor on this slate"}

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
    this function cannot grade, which is recorded rather than guessed.

    THE GRADING ITSELF LIVES IN betting_settle (2026-08-09), because there are
    now three ledgers over the same slate and they may never disagree about
    whether a side covered. This wrapper keeps the dict-returning shape the rest
    of this file and its tests were written against."""
    res = betting_settle.grade_side(
        market=row.get("market"), side=row.get("side"), point=row.get("point"),
        home_runs=game.get("home_runs"), away_runs=game.get("away_runs"))
    return {"result": res} if res else None


def _profit(row: dict, result: str) -> float | None:
    return betting_settle.profit_units(
        result=result, decimal=row.get("decimal"), odds=row.get("odds_at_post"),
        stake_units=float(row.get("stake_units") or STAKE_UNITS))


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
def row_tags(row: dict) -> set:
    """Which tag populations one row belongs to.

    A row's memberships are the ones its writer STAMPED, never ones inferred
    later. `tags` is the explicit list; a row with only `slot` belongs to that
    one tag; a row with neither is from the pre-tag era and belongs to
    `untagged` alone.

    THE THING THIS REFUSES TO DO is fold the old five-a-slate rows into
    `board_all` on the grounds that they cleared the floor too. They did, but
    they were selected under a cap, so their population is censored at the top
    of the EV ranking. Pooling a censored sample into an uncapped tag is the
    same defect as pooling the tags, one level down."""
    tags = row.get("tags")
    if isinstance(tags, (list, tuple, set)) and tags:
        return {str(t) for t in tags}
    slot = row.get("slot")
    return {slot} if slot else {UNTAGGED}


def graded_bets(*, slot: str | None = None, path: Path | None = None) -> list[dict]:
    """Settled shadow bets as {edge, decimal, won} rows, which is exactly what
    `betting_model.sweep_min_edge` consumes.

    `slot` NAMES THE TAG TO CONDITION ON, and passing one is what makes the
    result a sweepable sample. docs/diamond-betting.md section 7a: "a pooled ROI
    measures a mixture nobody bet". The four tags select on four different
    quantities - model probability inside a price band, EV at a long price, EV
    anywhere inside a cap, and every side over the floor - so a threshold fitted
    to their union is wrong for each of them separately.

    `slot=None` STILL RETURNS THE POOLED SET, unchanged, and that is not an
    endorsement of it. It is the shape `betting_model._shadow_graded_bets` has
    always called, and quietly redefining it here would change what an existing
    caller measures without that caller's code moving. The fix belongs at the
    gate: see `graded_bets_by_tag` and the patch it exists to serve. Anything
    that SETS A THRESHOLD from the pooled set is a defect.

    Pushes are EXCLUDED rather than scored as losses. A push returns the stake,
    so counting it as a loss would understate every threshold's ROI and make the
    gate harder to clear for a reason that has nothing to do with skill."""
    out = []
    for r in load(path):
        if r.get("result") not in ("won", "lost"):
            continue
        if slot is not None and slot not in row_tags(r):
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


def graded_bets_by_tag(*, path: Path | None = None) -> dict:
    """{tag: sweepable rows} for every tag that has at least one settled row.

    This is what gate 3 should sweep over: one threshold per tag, each opening
    on its own evidence. A tag with 4 settled rows stays shut while another with
    120 opens, which is the correct behaviour and the reason the pooled version
    looked further along than it was."""
    rows = load(path)
    tags = sorted({t for r in rows for t in row_tags(r)})
    return {t: graded_bets(slot=t, path=path) for t in tags}


def sweep_readiness(*, path: Path | None = None) -> dict:
    """Per tag: how many settled rows it has, how many it needs, and whether it
    may be swept at all. No rates, no projections - this is a counter."""
    by_tag = graded_bets_by_tag(path=path)
    return {t: {"n": len(rws), "need": MIN_BETS_FOR_SWEEP,
                "ready": len(rws) >= MIN_BETS_FOR_SWEEP,
                "max_per_slate": MAX_PER_SLATE_BY_TAG.get(t, "n/a")}
            for t, rws in sorted(by_tag.items())}


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

    # BY TAG, which is not the same partition as `by_slot` and must not be read
    # as one. `slot` is the single rule that CHOSE a row, so `by_slot` is a
    # partition and its counts sum to n_rows. `by_tag` is MEMBERSHIP, and a row
    # chosen by the EV cap is also a member of board_all, so these buckets
    # OVERLAP and their counts do not sum to anything. That is the correct shape
    # for the question gate 3 asks - "does this tag, on its own, have enough
    # settled rows to sweep" - and the wrong shape for "how big is the ledger".
    tag_buckets: dict[str, list[dict]] = {}
    for r in rows:
        for t in row_tags(r):
            tag_buckets.setdefault(t, []).append(r)
    out["by_tag"] = {k: _tally(v) for k, v in sorted(tag_buckets.items())}
    out["by_tag_note"] = ("membership, not a partition: a capped row is also a "
                          "board_all row, so these counts overlap by design")

    # The number the third gate is actually waiting on, PER TAG. The pooled
    # count is kept beside it because it is what the un-patched gate still
    # reads, and seeing the two apart is how the difference gets noticed.
    out["sweep_readiness"] = sweep_readiness(path=path)
    out["n_for_min_edge_sweep"] = len(graded_bets(path=path))
    out["n_for_min_edge_sweep_pooled_is_not_sweepable"] = (
        "the pooled count mixes four selection rules; a threshold fitted to it "
        "is wrong for every tag it would be applied to")
    out["min_bets_for_sweep"] = MIN_BETS_FOR_SWEEP
    # WHERE THE EVIDENCE IS STORED, beside the counts it produced. A ledger that
    # cannot survive a checkout is not evidence, however many rows it holds.
    if path is None:
        out["storage"] = storage()
    return out
