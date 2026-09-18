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
  5. Since 2026-09-06 the MARKET is a first-class dimension beside the tag. The
     tag says which rule chose a row; it never said what was bet. Measured on
     the live ledger that day (255 rows, 223 settled, pooled ROI -13.1%):
     moneyline 44 settled at -27.4%, runline 74 at -3.2%, total 105 at -14.6%.
     The pooled number is none of the three, and totals are 121 of the 255 rows,
     so the pooled read is mostly a statement about totals wearing every
     market's name. Each market now accrues, reports and can open or close on
     its own evidence: see `graded_bets_by_market_tag`.

WHAT THIS FILE REFUSES TO CLAIM. Nothing here is a recommendation, a return, or
a forecast. The tallies are arithmetic over settled paper rows and they measure
the selection rule that wrote those rows, nothing wider.

THE POOLING IS NOT FIXED YET, AND THIS HEADER USED TO SAY IT WAS. What is true
is narrower: no function ADDED for the market dimension returns a sample that
pools two markets, two tags or two budget eras together, because a threshold
fitted to a mixture is wrong for every population inside it. The PRE-EXISTING
samplers still pool markets, and that is precisely the defect
`graded_bets_by_market_tag` exists to replace. Re-run against the live ledger on
2026-09-06, `graded_bets(slot='board_all')` returns a LIST of 214 sweepable
{edge, decimal, won} rows, not a count, and those rows are 43 moneyline, 71
runline and 100 total; `graded_bets(slot=None)` returns 220 rows across the same
three markets; `graded_bets_by_tag` conditions on the tag alone, so its four
cells are cross-market too: board_all 214 rows and ev_rank 45 each span all three
markets, potd_band 15 spans runline and moneyline, and only longshot (4 rows, all
moneyline) is single-market by accident of its own sample. Anything that sets a
threshold from one of those samples is a defect, whichever function produced it.

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

#: WHICH PRICER'S BOARD A ROW WAS TAKEN OFF (2026-09-17).
#:
#: Every row on disk today was selected off a board priced from the club's
#: season Offense+ rollup and the CONSTRUCTED nine. Nothing in the tree prices
#: a posted lineup, and nothing may until 5j passes. The stamp exists so that
#: the day a second basis is served, the two populations are two samples and
#: not one: a ROI pooled across them measures a mixture nobody bet, which is
#: the tag rule of section 7a applied one level down, exactly as `board_all`
#: applies it to the capped tags.
#:
#: `board_all` is the tag that makes this urgent. The capped tags carry a
#: per-slate budget, so a second build of one slate cannot add to them; the
#: uncapped tag is the one an intraday pass CAN extend, and an intraday pass is
#: precisely the pass that would carry a different basis.
#:
#: ROWS WRITTEN BEFORE THIS EXISTED ARE NOT BACKFILLED. They read `unstamped`,
#: the same discipline the pre-2026-08-07 untagged rows get: a writer that did
#: not know a fact does not get to have known it later. `unstamped` is swept
#: WITH `constructed` because no other pricer has ever written to this ledger,
#: and that reading is recorded here rather than left implicit.
PRICING_BASIS_CONSTRUCTED = "constructed"
PRICING_BASIS_POSTED = "posted"
PRICING_BASIS_UNSTAMPED = "unstamped"
PRICING_BASES = (PRICING_BASIS_CONSTRUCTED, PRICING_BASIS_POSTED)

#: The basis the served board prices on today. `_sweep_row` refuses any row
#: stamped with a different one, so a posted-basis row cannot reach a sweep, a
#: gate or a readiness count by default. It is a parameter of the reader, not a
#: filter applied at write time: the rows stay on disk and stay countable.
SERVED_PRICING_BASIS = PRICING_BASIS_CONSTRUCTED


#: THE PROPS TAGS (2026-08-16, docs/diamond-betting.md section 7c). One tag
#: per props market, because the four markets are four different selection
#: populations and pooling them would repeat the exact defect the team tags
#: exist to prevent, one level down. The names are the props market names so
#: a row's tag and its market can never disagree.
#:
#: NEVER POOLED WITH THE TEAM TAGS. A props row is a different instrument on
#: a different bet against a different budget; a min-edge sweep conditions on
#: ONE tag or it measures a mixture nobody bet. The pooled team read
#: (`graded_bets(slot=None)`) EXCLUDES props rows outright, because that
#: shape is the team gate's historical instrument and a props row entering it
#: would silently change what an existing caller measures.
PROPS_TAG_PREFIX = "props_"
PROPS_TAGS = tuple(PROPS_TAG_PREFIX + m for m in (
    "pitcher_strikeouts", "batter_total_bases", "batter_hits",
    "batter_home_runs"))

#: How many rows a slate may contribute PER TAG. None means uncapped.
#:
#: The three capped budgets sum to MAX_PER_SLATE and are exactly the split the
#: shipped selector already applied (two slot picks, then the top three by EV),
#: written down so it can be read instead of inferred from the loop below.
#: The props budgets (3 a slate per tag, mirroring the section 7c games/day
#: cap) are enforced in record_props_slate and are OUTSIDE the team
#: MAX_PER_SLATE arithmetic: a props row must never eat a team row's budget.
MAX_PER_SLATE_BY_TAG = {
    "potd_band": 1,
    "longshot": 1,
    DEFAULT_SLOT_TAG: 3,
    BOARD_ALL_TAG: None,
    **{t: 3 for t in PROPS_TAGS},
}

#: The three team markets a board row can be on. Props rows carry their own
#: market name in the same field (the props tag IS its market), which is the
#: right answer and not a special case: four props markets are four markets.
TEAM_MARKETS = ("moneyline", "runline", "total")

#: A row that somehow carries no market. Measured on the live ledger 2026-09-06:
#: 0 of 255 rows. It exists so a malformed row lands in a named bucket instead
#: of silently joining a real market's evidence.
UNKNOWN_MARKET = "unknown_market"

#: THE PER-MARKET ALLOCATION of a tag's per-slate budget: (market, tag) -> cap.
#: MAX_PER_SLATE_BY_TAG above is UNCHANGED and still governs the total a tag may
#: log on one slate. This dict says how much of that total one market may take
#: before every other market has had its turn.
#:
#: WHY (2026-09-06, plan lane B-SUBLEDGERS, owner decision 6). `ev_rank` ranks
#: the whole board by EV and takes the top three, and totals win that race.
#: Measured on the live ledger: of ev_rank's 49 rows, 36 are totals, 9 runline,
#: 4 moneyline. Four settled moneyline rows across 16 slate days puts that cell
#: roughly a decade from MIN_BETS_FOR_SWEEP, so "each market opens on its own
#: evidence" was unreachable for two markets of three: one market was spending
#: another's budget.
#:
#: IT IS A RESERVATION, NOT A CEILING, and the difference is deliberate. The
#: selector fills the allocations first, one row per market in EV order, and
#: only then spends the seats no market claimed, in EV order, ignoring the
#: allocation. A hard ceiling would cut the tag's volume on a slate where one
#: market is the only thing on the board, which buys nothing: no market was
#: outbid there. MEASURED COUNTERFACTUAL, replaying the recorded clearing sides
#: of all 16 slates on disk: the same 46 ev_rank seats are filled either way,
#: and the market split moves from (4 moneyline, 7 runline, 35 total) to
#: (13, 15, 18). Those 46 are the 49 logged rows less the 3 that the two
#: pre-2026-08-12 slates took before the per-slate budget was enforced at all.
MAX_PER_SLATE_BY_MARKET_TAG = {(m, DEFAULT_SLOT_TAG): 1 for m in TEAM_MARKETS}

#: Every tag a row may be a member of, plus the pre-tag era's bucket.
KNOWN_TAGS = (*sorted(SLOT_TAGS.values()), DEFAULT_SLOT_TAG, BOARD_ALL_TAG,
              *PROPS_TAGS)
UNTAGGED = "untagged"

#: The sweep's sample-size floor, per tag. Named here because the per-tag rule
#: is what makes the number expensive: 100 settled rows POOLED is one clock, 100
#: PER TAG is four clocks running at four different speeds, and the slowest of
#: them is roughly 3x slower to open than the pooled number it replaces. That
#: cost is accepted deliberately - a threshold fitted to a mixture of four
#: selection rules is wrong for every one of them.
MIN_BETS_FOR_SWEEP = 100

#: THE DATE THE PER-MARKET ALLOCATION SHIPPED, and therefore the date the series
#: splits. Rows already on disk were selected under the pooled per-tag cap and
#: are NEVER retagged: a row's selection rule is the one its writer applied, and
#: restamping it would reinterpret evidence under a rule that did not exist when
#: the row was chosen. That is the same hazard BOARD_ALL_TAG was introduced to
#: avoid, and the answer is the same: split the series, name both halves, pool
#: neither.
#:
#: THE COST, stated because it is large. Every ev_rank cell's post-split count
#: starts at zero on this date, and on 2026-09-06 all 223 settled rows sit in
#: the pooled-cap era, so no ev_rank cell can reach MIN_BETS_FOR_SWEEP on
#: post-split evidence for at least 100 settled rows of new slates. The cells
#: whose membership did NOT change are exempt and keep their full history: see
#: `era_split_applies`.
BUDGET_SPLIT_DATE = "2026-09-06"
POOLED_CAP_ERA = "pooled_tag_cap"
PER_MARKET_CAP_ERA = "per_market_cap"
BUDGET_ERAS = (POOLED_CAP_ERA, PER_MARKET_CAP_ERA)


def market_of(row: dict) -> str:
    """Which market's sub-ledger one row belongs to.

    Read off the row's own `market` field and never inferred from the tag or the
    selection text. A props row's market is its props market, which is why props
    rows need no special exclusion once the market dimension exists."""
    m = row.get("market")
    return str(m) if m else UNKNOWN_MARKET


def cell_budget(market: str, tag: str):
    """The per-slate cap for one (market, tag) cell. None means uncapped.

    A cell with no explicit allocation falls back to its TAG's per-slate total,
    which is the same statement as "this tag has no market allocation": the tag
    total is then the only thing binding it."""
    key = (market, tag)
    if key in MAX_PER_SLATE_BY_MARKET_TAG:
        return MAX_PER_SLATE_BY_MARKET_TAG[key]
    return MAX_PER_SLATE_BY_TAG.get(tag)


def era_split_applies(market: str, tag: str) -> bool:
    """Does the 2026-09-06 cap change alter what THIS cell's membership means?

    Computed from the two budget tables rather than asserted by hand: a cell
    splits when its allocation is stricter than its tag's per-slate total. On
    the shipped tables that is the three ev_rank cells and nothing else, and the
    exemptions are the point:

      board_all is uncapped on both sides of the date, so its population is
      identical across the split and its 185 rows (measured 2026-09-06) keep
      accruing into one sample.
      potd_band and longshot are one published pick a slate. Their allocation
      equals their tag total, 1, so the arithmetic cannot change what they hold.
      Measured over the 16 slates on disk: potd_band is exactly 1 on all 16 and
      longshot is 0 or 1 on all 16, so nothing was ever competing there.
      A props tag IS its market, so cell and tag are the same budget."""
    return cell_budget(market, tag) != MAX_PER_SLATE_BY_TAG.get(tag)


def budget_era(row: dict) -> str:
    """Which budget regime chose this row, by the slate it was chosen for.

    Dated on `slate_date` and not `posted_at`, because the budget binds a slate:
    a row logged after midnight UTC for the previous day's board competed under
    that board's allocation. A row carrying neither date is assigned to the
    OLDER era, which is the conservative reading (it predates the change and
    cannot be evidence for the new rule)."""
    d = row.get("slate_date") or str(row.get("posted_at") or "")[:10]
    return PER_MARKET_CAP_ERA if d and str(d) >= BUDGET_SPLIT_DATE else POOLED_CAP_ERA


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
    # Published paths are checkout-relative. This block rode into the published
    # learning artifact as absolute Windows paths carrying the OS username,
    # the same leak betting_export._public_path closed on the board payload
    # (found 2026-08-16). Lazy import: betting_export is heavy and this module
    # is otherwise independent of it.
    from betting_export import _public_path
    return {
        "backend": "cache" if durable else "data_fallback",
        "authoritative_path": _public_path(SHADOW_CACHE_PATH if durable
                                           else SHADOW_DERIVED_PATH),
        "derived_path": _public_path(SHADOW_DERIVED_PATH),
        "path_basis": "relative to the site checkout root",
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
                          budget_by_tag: dict | None = None,
                          budget_by_market_tag: dict | None = None) -> list[dict]:
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

    `budget_by_market_tag` is the per-(market, tag) allocation, defaulting to
    MAX_PER_SLATE_BY_MARKET_TAG. It binds only the FIRST ev_rank pass: each
    market gets its allocated seats before any market takes a second, and the
    spill pass then fills the rest by EV. Passing a map of remaining room is how
    record_slate makes the allocation a per-SLATE budget rather than a per-call
    one, exactly as it already does for `budget_by_tag`.

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
    #
    # THE MARKET ALLOCATION IS THE SECOND BUDGET (2026-09-06). A tag's total is
    # unchanged; what changed is that the first pass hands each market its own
    # seat before any market takes a second. Without it the EV ranking gave
    # ev_rank 36 totals, 9 runlines and 4 moneylines over 16 slate days, which
    # is a sub-ledger that can never open on its own evidence for two markets
    # out of three. The SPILL pass then fills whatever the allocation left
    # unclaimed, so a one-market board still logs its full budget: a seat no
    # market wanted is not a seat any market was denied.
    budget = dict(MAX_PER_SLATE_BY_TAG if budget_by_tag is None else budget_by_tag)
    cells = dict(MAX_PER_SLATE_BY_MARKET_TAG if budget_by_market_tag is None
                 else budget_by_market_tag)

    picked, seen, taken, taken_cell = [], set(), {}, {}

    def _room(tag: str) -> bool:
        cap = budget.get(tag, None)
        return cap is None or taken.get(tag, 0) < cap

    def _cell_room(cand: dict, tag: str) -> bool:
        ck = (market_of(cand), tag)
        # A cell with no allocation falls back to the tag total, so a tag that
        # was never allocated behaves exactly as it did before this existed.
        cap = cells.get(ck, budget.get(tag, None))
        return cap is None or taken_cell.get(ck, 0) < cap

    def _take(cand: dict, tag: str, row: dict) -> None:
        picked.append(row)
        seen.add(_row_key(cand))
        taken[tag] = taken.get(tag, 0) + 1
        ck = (market_of(cand), tag)
        taken_cell[ck] = taken_cell.get(ck, 0) + 1

    for cand in out:
        k = _row_key(cand)
        if (k in tagged and k not in seen and _room(tagged[k])
                and _cell_room(cand, tagged[k])):
            _take(cand, tagged[k], {**cand, "slot": tagged[k]})
    for allocation_binds in (True, False):
        for cand in out:
            if len(picked) >= max_per_slate:
                break
            k = _row_key(cand)
            if k in seen or not _room(DEFAULT_SLOT_TAG):
                continue
            if allocation_binds and not _cell_room(cand, DEFAULT_SLOT_TAG):
                continue
            _take(cand, DEFAULT_SLOT_TAG, cand)
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
                 pricing_basis: str | None = None,
                 path: Path | None = None, log_fn=None) -> dict:
    """Append this slate's shadow bets. Idempotent per (slate, game, market, side).

    Returns a summary rather than raising when there is nothing to record: an
    empty slate is a normal outcome and has to be distinguishable from a
    failure, which is why `reason` is always populated.

    THE BASIS IS READ OFF THE PAYLOAD, NOT TAKEN ON TRUST. The rows this call
    writes come from `payload['team_bets']`, and the board that priced them
    states which pricer it is in `payload['model']['pricing_basis']`. A default
    keyword would be a promise about the caller: an intraday pass priced on a
    posted lineup that forgot the argument would stamp `constructed` on
    posted-basis rows, they would pool into every sweep, and this module never
    backfills a row, so the contamination would be permanent and invisible.
    An explicit `pricing_basis` that DISAGREES with the payload raises rather
    than winning, because one of the two is then wrong about the same board.

    An intraday pass priced on a posted lineup stamps `PRICING_BASIS_POSTED`
    and its rows are a SECOND POPULATION: `_sweep_row` refuses them, so they
    can never be pooled into a threshold with the rows above them. The uncapped
    `board_all` tag is the one an intraday pass can add to at all, which is why
    the stamp lands before such a pass exists rather than after it.

    A payload that states NO basis leaves its rows unstamped. That is what the
    323 rows written before this field existed read as, and inferring a basis
    for them here would assert a fact this module never knew."""
    if pricing_basis is not None and pricing_basis not in PRICING_BASES:
        raise ValueError(f"unknown pricing_basis {pricing_basis!r}; "
                         f"expected one of {', '.join(PRICING_BASES)}")
    declared = ((payload.get("model") or {}).get("pricing_basis")
                if isinstance(payload.get("model"), dict) else None)
    if declared is not None and declared not in PRICING_BASES:
        raise ValueError(
            f"the payload states pricing_basis {declared!r}, which is not one "
            f"of {', '.join(PRICING_BASES)}; a ledger cannot be written off a "
            "board whose basis it cannot name")
    if (pricing_basis is not None and declared is not None
            and pricing_basis != declared):
        raise ValueError(
            f"pricing_basis {pricing_basis!r} was passed for a board that "
            f"states {declared!r}; the row's basis is a fact about the board "
            "and the two may not disagree")
    pricing_basis = declared if declared is not None else pricing_basis
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
    used_cell: dict[tuple, int] = {}
    for r in existing:
        if r.get("slate_date") != slate:
            continue
        tag = r.get("slot") or DEFAULT_SLOT_TAG
        used[tag] = used.get(tag, 0) + 1
        ck = (market_of(r), tag)
        used_cell[ck] = used_cell.get(ck, 0) + 1
    remaining = {t: (None if MAX_PER_SLATE_BY_TAG.get(t) is None
                     else max(0, MAX_PER_SLATE_BY_TAG[t] - used.get(t, 0)))
                 for t in MAX_PER_SLATE_BY_TAG}
    # THE ALLOCATION IS PER SLATE TOO, and for the same reason the tag budget
    # is: the pipeline runs more than once a day, and a second pass that got a
    # fresh allocation would let one market take its seat twice off two
    # different capture times.
    remaining_cell = {}
    for ck in set(MAX_PER_SLATE_BY_MARKET_TAG) | set(used_cell):
        cap = cell_budget(*ck)
        remaining_cell[ck] = (None if cap is None
                              else max(0, cap - used_cell.get(ck, 0)))
    # Props tags are OUTSIDE the team MAX_PER_SLATE arithmetic (2026-08-16,
    # section 7c): they are capped, but against their own budgets, and a props
    # row counted here would shrink the team room by rows that never competed
    # for it.
    room = MAX_PER_SLATE - sum(
        n for t, n in used.items()
        if MAX_PER_SLATE_BY_TAG.get(t) is not None
        and not str(t).startswith(PROPS_TAG_PREFIX))

    cands = candidates_from_board(payload, min_edge=min_edge, slots=slots,
                                  include_board_all=include_board_all,
                                  max_per_slate=max(0, room),
                                  budget_by_tag=remaining,
                                  budget_by_market_tag=remaining_cell)
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
            budget_by_tag={t: None for t in MAX_PER_SLATE_BY_TAG},
            budget_by_market_tag={ck: None for ck in MAX_PER_SLATE_BY_MARKET_TAG})
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
            # WHICH PRICER'S BOARD THIS ROW CAME OFF, stamped AFTER the board
            # row is spread in so the writer's own fact cannot be overwritten by
            # a stray key travelling on a candidate. See PRICING_BASES: the
            # ledger is one sample only for as long as one basis wrote it, and
            # this is what lets a reader tell, row by row, whether that holds.
            # Absent, not null, when the board named no basis: `pricing_basis_of`
            # reads that as `unstamped`, which is what it is.
            **({"pricing_basis": pricing_basis} if pricing_basis else {}),
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
            # WHICH BASIS THESE ROWS CARRY, reported back to the caller that
            # did not pass it. None means the board named none and the rows are
            # unstamped, which a reader has to be able to see without opening
            # the ledger.
            "pricing_basis": pricing_basis,
            "by_slot": by_slot, "rows": new}


def record_props_slate(props_value: dict, *, gate_state: dict | None = None,
                       path: Path | None = None, log_fn=None) -> dict:
    """Append this slate's PROPS paper bets (2026-08-16, section 7c).

    Reads the served `props_value` block's floor-clearing sides, the same
    discipline as the team ledger: the board the page shows, a real captured
    price or nothing, idempotent per (slate, game, market, side, point,
    player). Each row's `slot` is its props tag (the market name), so the
    future per-tag sweep conditions on it exactly as it does on the team
    tags, and never across them. The per-tag budget is 3 a slate."""
    pv = props_value or {}
    slate = pv.get("slate_date")
    if not slate:
        return {"written": 0, "reason": "props_value carries no slate_date"}
    cands = [r for r in (pv.get("value_rows") or [])
             if r.get("odds") is not None and r.get("book")
             and str(r.get("market") or "").startswith(PROPS_TAG_PREFIX)]
    if not cands:
        return {"written": 0, "slate_date": slate,
                "reason": "no props side cleared the floor on this build"}

    existing = load(path)
    used: dict[str, int] = {}
    for r in existing:
        if r.get("slate_date") != slate:
            continue
        tag = str(r.get("slot") or "")
        if tag.startswith(PROPS_TAG_PREFIX):
            used[tag] = used.get(tag, 0) + 1
    seen = {r.get("shadow_id") for r in existing}
    posted = _now()
    new = []
    # Deterministic order: best EV first inside each tag, so the budget takes
    # the same rows on every rebuild of the same board.
    cands.sort(key=lambda r: (r.get("market"),
                              r.get("ev_per_unit") is None,
                              -(r.get("ev_per_unit") or 0)))
    for c in cands:
        tag = c["market"]
        cap = MAX_PER_SLATE_BY_TAG.get(tag)
        if cap is not None and used.get(tag, 0) >= cap:
            continue
        sid = shadow_id(slate, c.get("game_pk"), tag, c.get("side"),
                        c.get("point"), c.get("player"))
        if sid in seen:
            continue
        seen.add(sid)
        used[tag] = used.get(tag, 0) + 1
        new.append({
            "shadow_id": sid,
            "posted_at": posted,
            "provisional": True,
            "stake_units": STAKE_UNITS,
            "min_edge_used": round(float(c.get("min_edge_used") or 0.0), 5),
            "gate_state": gate_state or {},
            "result": None, "settled_at": None, "profit_units": None,
            "slate_date": slate,
            "game_pk": c.get("game_pk"),
            "matchup": c.get("matchup"),
            "market": tag,
            "player": c.get("player"),
            "side": c.get("side"),
            "selection": c.get("label"),
            "point": c.get("point"),
            "book": c.get("book"),
            "odds_at_post": c.get("odds"),
            "decimal": c.get("decimal"),
            "edge": (round(float(c["edge"]), 5)
                     if c.get("edge") is not None else None),
            "model_prob": c.get("model_prob"),
            "market_fair_prob": c.get("market_fair_prob"),
            "ev_per_unit": c.get("ev_per_unit"),
            "slot": tag,
        })
    if not new:
        return {"written": 0, "slate_date": slate,
                "reason": "every qualifying props side is already logged or "
                          "its per-tag budget is spent"}
    write(existing + new, path=path)
    by_tag = {}
    for r in new:
        by_tag[r["slot"]] = by_tag.get(r["slot"], 0) + 1
    if log_fn:
        log_fn(f"betting_shadow: logged {len(new)} props paper bet(s) for "
               f"{slate} ({', '.join(f'{k} {v}' for k, v in sorted(by_tag.items()))})")
    return {"written": len(new), "slate_date": slate, "reason": "ok",
            "by_slot": by_tag, "rows": new}


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


def pricing_basis_of(row: dict) -> str:
    """Which pricer's board this row was taken off, as its writer stamped it.

    An unstamped row reads `unstamped` rather than `constructed`: the writer
    did not record a basis and inferring one here would assert a fact it never
    knew. `sweeps_with_served_basis` is where the reading that unstamped rows
    were constructed-basis rows is applied, once, in the open."""
    b = row.get("pricing_basis")
    return str(b) if b else PRICING_BASIS_UNSTAMPED


def sweeps_with_served_basis(row: dict) -> bool:
    """May this row enter a sweep priced on the basis that serves today?

    True for the served basis and for the pre-stamp rows, false for every other
    basis. The whole point is that the false branch is reachable: the day a
    posted-lineup basis is served, its rows accumulate in the ledger and stay
    out of every sweep that has not asked for them by name."""
    return pricing_basis_of(row) in (SERVED_PRICING_BASIS, PRICING_BASIS_UNSTAMPED)


def basis_refusals(rows: list[dict]) -> dict:
    """How many settled rows a sweep refuses on basis grounds, and whose.

    THE DEFECT THIS CLOSES. `_sweep_row` returns None for a row written on a
    basis the served board does not price on, and a `return None` is a silent
    drop: the day a posted-basis row is written, gate 3's per-tag counts stop
    advancing and every counter downstream says only that `n` is lower. A gate
    that stalls has to name its own cause, and a guard that drops instead of
    refusing loudly is the shape this program keeps finding.

    Settled rows only. An open row is not refused by anything yet; it has not
    reached the question a sweep asks."""
    out: dict[str, int] = {}
    for r in rows or []:
        if r.get("result") not in ("won", "lost"):
            continue
        if sweeps_with_served_basis(r):
            continue
        b = pricing_basis_of(r)
        out[b] = out.get(b, 0) + 1
    return dict(sorted(out.items()))


def _sweep_row(r: dict) -> dict | None:
    """One settled row as {edge, decimal, won}, or None when it cannot be swept.

    Factored out of `graded_bets` unchanged (2026-09-06) so the per-cell reader
    and the pooled counter shape rows the same way: two shaping rules would be
    two different samples wearing one name. A push never reaches here, a row
    with no edge or no usable price is dropped rather than defaulted."""
    if r.get("result") not in ("won", "lost"):
        return None
    # THE BASIS REFUSAL (2026-09-17). One shaping seam, so every sweepable read
    # in this module inherits it: the pooled shape, the per-tag shape, the
    # per-(market, tag) cells and the readiness counts all pass through here.
    # Nothing on disk is stamped with a foreign basis today, so this drops zero
    # rows now and drops every row of a second basis the day one is written.
    if not sweeps_with_served_basis(r):
        return None
    dec = r.get("decimal")
    if not dec:
        try:
            import betting_ingest as bi
            dec = bi.american_to_decimal(r.get("odds_at_post"))
        except Exception:                                     # noqa: BLE001
            dec = None
    if r.get("edge") is None or not dec:
        return None
    return {"edge": float(r["edge"]), "decimal": float(dec),
            "won": r["result"] == "won"}


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
    gate harder to clear for a reason that has nothing to do with skill.

    PROPS ROWS NEVER ENTER THE POOLED SET (2026-08-16, section 7c). The
    slot=None shape is the team gate's historical instrument, and a props row
    riding into it would silently change what betting_model's existing caller
    measures without that caller's code moving. A props tag is reachable the
    only honest way: by naming it in `slot`."""
    out = []
    for r in load(path):
        if r.get("result") not in ("won", "lost"):
            continue
        tags = row_tags(r)
        if slot is None:
            if any(str(t).startswith(PROPS_TAG_PREFIX) for t in tags):
                continue
        elif slot not in tags:
            continue
        sw = _sweep_row(r)
        if sw is not None:
            out.append(sw)
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


#: What `sweep_readiness.n` counts, carried on every block so the number and
#: its basis travel together into whatever renders them.
SWEEP_READINESS_BASIS = (
    "n is the largest (market, tag) sub-ledger inside this tag, which is the "
    "sample the 100-row floor is measured against; n_pooled is the tag's whole "
    "census across its markets and is never swept and never compared with need. "
    "n_refused_basis counts the rows that sample refused on pricing-basis "
    "grounds and is measured on the same cell as n; n_refused_basis_pooled is "
    "the tag-wide sum and belongs beside n_pooled")


def sweep_readiness(*, path: Path | None = None) -> dict:
    """Per tag: how far that tag's LARGEST SUB-LEDGER is from its own sweep.

    `n` IS THE LARGEST (MARKET, TAG) CELL, not the tag's pooled count, since
    2026-09-17 (L14-05). The min_edge gate sweeps sub-ledgers, so a tag's
    pooled count is not the quantity its 100-row floor is measured against: on
    the ledger of 2026-09-17 `board_all` held 292 settled rows across three
    markets while the largest sample any sweep could run on was 138, and a
    counter reading 292 against a need of 100 reported "ready" about a unit no
    sweep runs on. The pooled count keeps its own name, `n_pooled`, and is a
    census.

    THE CONSUMER IS betting_learning._price_clock, which copies `n`, `need`,
    `ready` and `max_per_slate` and derives its own arrival rate from them.
    The repair has to land HERE for the served clock to stop disagreeing with
    the gate inside one artifact: `have` in that clock and `have` in gate 3 are
    now the same number by construction, which is what
    docs/diamond-betting.md section 5b means by one artifact, one quantity, one
    denominator.

    THE ETA THAT CLOCK DERIVES IS A PER-TAG ARRIVAL RATE applied to a per-cell
    count, so it is optimistic: rows arrive across all of a tag's markets and
    only some of them land in its biggest cell. That rate is computed in a
    module this counter cannot reach, so the fact is named here rather than
    left for a reader to find. It is a statement about the ETA and not about
    `n`, which is exact.

    No rates and no projections - this is a counter."""
    by_tag = graded_bets_by_tag(path=path)
    cells = sweep_readiness_by_market_tag(path=path)
    # The same cell blocks the gate reads, re-keyed by tag. One rule, one
    # place: `sweepable_n` already carries the budget-era filter, so this
    # counter cannot drift from the sample a sweep would actually run on.
    per_tag: dict[str, dict] = {}
    for m, tags in cells.items():
        for t, block in tags.items():
            per_tag.setdefault(t, {})[m] = block
    out = {}
    for t in sorted(set(by_tag) | set(per_tag)):
        mine = per_tag.get(t) or {}
        ranked = sorted((int(b.get("sweepable_n") or 0), m)
                        for m, b in mine.items())
        n, largest = ranked[-1] if ranked else (0, None)
        # THE REFUSAL TRAVELS WITH THE COUNT, AND WITH ITS OWN DENOMINATOR.
        # betting_learning._price_clock copies `n`, `need` and `ready` off this
        # block; a stalled clock that cannot say why it stalled is exactly the
        # kind of number this section forbids. `n` is the LARGEST (market, tag)
        # cell since L14-05, so the refusal beside it is that cell's, not the
        # tag's: summing the tag's cells there would put a count over three
        # markets next to a count over one, which is the mixture this whole
        # section exists to keep apart. The tag-wide sum is published under a
        # name that says its scope, beside `n_pooled`, which is the count it
        # belongs to.
        refused = dict((mine.get(largest) or {}).get("refused_bases") or {})
        pooled_refused = 0
        for _b in mine.values():
            pooled_refused += int(_b.get("n_refused_basis_cell")
                                  or _b.get("n_refused_basis") or 0)
        out[t] = {
            "n": n,
            "need": MIN_BETS_FOR_SWEEP,
            "ready": n >= MIN_BETS_FOR_SWEEP,
            "largest_cell": (f"{largest}|{t}" if largest else None),
            "n_pooled": len(by_tag.get(t) or []),
            "markets": {m: int(b.get("sweepable_n") or 0)
                        for m, b in sorted(mine.items())},
            "n_markets": len(mine),
            "n_refused_basis": sum(refused.values()),
            "refused_bases": dict(sorted(refused.items())),
            "n_refused_basis_pooled": pooled_refused,
            "sweep_unit": "(market, tag) sub-ledger",
            "basis": SWEEP_READINESS_BASIS,
            "max_per_slate": MAX_PER_SLATE_BY_TAG.get(t, "n/a"),
        }
    return out


class MarketTagCells(dict):
    """{(market, tag): sweepable rows}, and nothing that pools them.

    THE POINT IS WHAT IS ABSENT. There is no key meaning "every market", no
    argument meaning "both eras", and no method that concatenates the cells, so
    a sweep cannot reach a cross-market sample by taking the obvious next step.
    The two-tuple key is the tripwire as well as the address: `cells["ev_rank"]`,
    which is what a reader porting code from `graded_bets_by_tag` would write,
    raises here instead of quietly handing back one tag pooled over three
    markets whose ROIs measured -27.4%, -3.2% and -14.6% on 2026-09-06.

    WHAT IT CANNOT STOP is a caller that builds the mixture on purpose, by
    summing `values()` for instance. No dict can stop that. The refusal is
    named, the reason is written down, and past that it is a choice someone has
    to make in the open rather than one the API makes for them by accident."""

    @staticmethod
    def _check(key) -> None:
        if not (isinstance(key, tuple) and len(key) == 2):
            raise ShadowLedgerError(
                f"cells are keyed by (market, tag); {key!r} is not a cell. There "
                "is no key here that means every market: a threshold fitted "
                "across markets is fitted to a mixture nobody bet")

    def __getitem__(self, key):
        self._check(key)
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        self._check(key)
        return dict.get(self, key, default)

    def pooled(self, *_a, **_k):
        raise ShadowLedgerError(
            "there is no pooled read of the market cells, by design; sweep each "
            "(market, tag) cell separately and let each market open or close on "
            "its own evidence")


def graded_bets_by_market_tag(*, era: str, path: Path | None = None) -> MarketTagCells:
    """{(market, tag): sweepable rows} for one budget era. The shape a per-market
    min-edge sweep may consume, and the only one this module offers.

    `era` IS REQUIRED AND HAS NO "BOTH" VALUE. The 2026-09-06 allocation changed
    what an ev_rank cell holds, so a sample spanning the split is a mixture of
    two selection rules, which is the same defect as pooling two tags one
    dimension over. Naming the era is how a caller states which rule it is
    fitting a threshold for.

    A cell whose membership did NOT change (see `era_split_applies`: board_all,
    the two single-pick slot tags, the props tags) returns its FULL history
    under either era value. That is not double counting: every cell is swept on
    its own and yields its own threshold, so a cell is never summed with
    itself. It is the correct answer, and the alternative, splitting a
    population that did not change, would throw away the 185 board_all rows the
    ledger has already paid for.

    NO PROPS EXCLUSION IS NEEDED HERE, unlike `graded_bets`. That exclusion
    exists because the pooled read has no market dimension and a props row would
    silently join a team sample. Here a props row is in its own market's cell by
    construction, which is what the exclusion was approximating."""
    if era not in BUDGET_ERAS:
        raise ShadowLedgerError(
            f"era must be one of {list(BUDGET_ERAS)}; got {era!r}. There is no "
            "value meaning both: the cap change split the series and a sample "
            "spanning it mixes two selection rules")
    cells: dict[tuple, list] = {}
    for r in load(path):
        sw = _sweep_row(r)
        if sw is None:
            continue
        m = market_of(r)
        for t in row_tags(r):
            if era_split_applies(m, t) and budget_era(r) != era:
                continue
            cells.setdefault((m, t), []).append(sw)
    return MarketTagCells(cells)


def market_span_by_tag(*, era: str, path: Path | None = None) -> dict:
    """{tag: {market: {n_in_era, n_all_eras, era_split}}} over the SWEEPABLE
    rows: the census a gate reads before it lets any sample set a threshold.

    IT EXISTS TO PRODUCE A REFUSAL, not a report. `graded_bets_by_tag`
    conditions on the tag alone, so one tag's rows can span three markets whose
    ROIs are three different numbers (measured 2026-09-06: moneyline -27.4%,
    runline -3.2%, total -14.6%), and a threshold fitted to their union is the
    pooling defect of docs/diamond-betting.md section 7a re-entering one level
    down through a tag name. A gate cannot see that from the swept rows
    themselves: `_sweep_row` keeps {edge, decimal, won} and drops the market, so
    by the time a sweep runs the mixture is invisible. The count is therefore
    taken here, off the rows on disk, and handed to the gate as evidence about
    the SAMPLE rather than about the bets.

    `era` IS REQUIRED AND HAS NO "BOTH" VALUE, exactly as in
    `graded_bets_by_market_tag`, and for the same reason: the two counts a
    caller might want are different quantities and naming one is how a caller
    says which. `n_in_era` is counted under the caller's era by the same rule
    the cells are built with (`era_split_applies`, then `budget_era`), so a
    cell can be checked against its census entry ROW FOR ROW and a cell holding
    more rows than its own entry is holding rows that are not its own.
    `n_all_eras` rides beside it under its own name for the whole history, and
    the two are never added, compared with each other, or compared with a floor.

    THE SECOND IMPLEMENTATION IS THE POINT. This counts the rows again rather
    than reusing `graded_bets_by_market_tag`, because a check built from the
    thing it checks cannot catch a sampler being swapped underneath the gate,
    which is the accident L14-05 describes."""
    if era not in BUDGET_ERAS:
        raise ShadowLedgerError(
            f"era must be one of {list(BUDGET_ERAS)}; got {era!r}. There is no "
            "value meaning both: the cap change split the series and a census "
            "spanning it counts two selection rules as one")
    span: dict[str, dict[str, dict]] = {}
    for r in load(path):
        if _sweep_row(r) is None:
            continue
        m = market_of(r)
        for t in row_tags(r):
            split = era_split_applies(m, t)
            cell = span.setdefault(t, {}).setdefault(
                m, {"n_in_era": 0, "n_all_eras": 0, "era_split": split})
            cell["n_all_eras"] += 1
            if not split or budget_era(r) == era:
                cell["n_in_era"] += 1
    return {t: dict(sorted(ms.items())) for t, ms in sorted(span.items())}


def sweep_readiness_by_market_tag(*, path: Path | None = None) -> dict:
    """{market: {tag: counts}}: how far each sub-ledger is from its own sweep.

    A counter, not a rate and not a projection. `sweepable_n` is the count that
    may set a threshold TODAY: for a cell the cap change split, that is the
    post-split era alone, because the pre-split rows were chosen by a rule this
    selector no longer runs (the same argument that put `untagged` on
    betting_model's do-not-fit list, which still applies on top of this)."""
    rows = load(path)
    cells: dict[tuple, list] = {}
    for r in rows:
        m = market_of(r)
        for t in row_tags(r):
            cells.setdefault((m, t), []).append(r)
    out: dict[str, dict] = {}
    for (m, t), rws in sorted(cells.items()):
        sweepable = [r for r in rws if _sweep_row(r) is not None]
        n_by_era = {e: sum(1 for r in sweepable if budget_era(r) == e)
                    for e in BUDGET_ERAS}
        split = era_split_applies(m, t)
        n_now = n_by_era[PER_MARKET_CAP_ERA] if split else len(sweepable)
        # WHAT THIS CELL REFUSED, beside what it counted, ON THE SAME
        # POPULATION. `sweepable_n` is one budget era when the cap split
        # applies, so a refusal counted over both eras would be a number a
        # reader subtracts from a count it does not belong to: one artifact,
        # one quantity, one denominator. The whole-cell figure keeps its own
        # name. Zero on every cell for as long as one basis writes the ledger;
        # the day a second one does, the clock that stops advancing says which
        # population it is not counting instead of reporting a smaller n and no
        # reason.
        era_rows = ([r for r in rws if budget_era(r) == PER_MARKET_CAP_ERA]
                    if split else rws)
        refused = basis_refusals(era_rows)
        refused_cell = basis_refusals(rws) if split else refused
        out.setdefault(m, {})[t] = {
            "n": len(sweepable),
            "n_by_era": n_by_era,
            "era_split": split,
            "sweepable_n": n_now,
            "need": MIN_BETS_FOR_SWEEP,
            "ready": n_now >= MIN_BETS_FOR_SWEEP,
            "n_refused_basis": sum(refused.values()),
            "refused_bases": refused,
            "n_refused_basis_cell": sum(refused_cell.values()),
            "max_per_slate": cell_budget(m, t),
        }
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
    selected on EV alone.

    SINCE 2026-09-06 it also carries the market dimension: `by_market` (a
    partition, counts sum to n_rows), `by_market_by_tag` (the cell a per-market
    sweep keys on), `budget_split` (the two budget eras, reported apart, and the
    cells the cap change actually split), and `sweep_readiness_by_market_tag`.
    Every one of those is a REPORT. The sweepable shape lives in
    `graded_bets_by_market_tag`, which has no pooled key at all."""
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

    # BY PRICING BASIS (2026-09-17). A partition, and today a partition into
    # one non-empty cell: every row was taken off a board priced on the season
    # rollup and the constructed nine. It is REPORTED so that the day a second
    # basis appears, the page and the gate block both say so without anyone
    # having to notice; `_sweep_row` is what enforces the split.
    basis_buckets: dict[str, list[dict]] = {}
    for r in rows:
        basis_buckets.setdefault(pricing_basis_of(r), []).append(r)
    out["by_pricing_basis"] = {b: _tally(v) for b, v in sorted(basis_buckets.items())}
    out["by_pricing_basis_note"] = (
        "a partition: every row was priced on exactly one basis, so these "
        f"counts sum to n_rows. Only {SERVED_PRICING_BASIS} rows and the "
        "pre-stamp rows are swept; any other basis is a second sample and is "
        "never pooled with this one")

    # BY MARKET (2026-09-06). The tag says which rule chose a row; it never said
    # what was bet, and the two questions have different answers. Measured on
    # the live ledger the day this shipped: moneyline 44 settled at -27.4%,
    # runline 74 at -3.2%, total 105 at -14.6%, pooled -13.1%, with totals 121
    # of the 255 rows. Reported and never pooled, on the same rule the tags get.
    market_buckets: dict[str, list[dict]] = {}
    for r in rows:
        market_buckets.setdefault(market_of(r), []).append(r)
    out["by_market"] = {m: _tally(v) for m, v in sorted(market_buckets.items())}
    out["by_market_note"] = ("a partition: every row is on exactly one market, "
                             "so these counts sum to n_rows. The pooled tally "
                             "above is a mixture of them and may not set a "
                             "threshold for any one market")

    mt_buckets: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        m = market_of(r)
        for t in row_tags(r):
            mt_buckets.setdefault(m, {}).setdefault(t, []).append(r)
    out["by_market_by_tag"] = {m: {t: _tally(v) for t, v in sorted(d.items())}
                               for m, d in sorted(mt_buckets.items())}
    out["by_market_by_tag_note"] = (
        "the cell a per-market sweep would key on: (market, tag). Membership "
        "inside a market, not a partition, because a capped row is also a "
        "board_all row")

    # THE BUDGET SPLIT. The per-market allocation changed what an ev_rank cell
    # holds, and the rows already on disk are not retagged, so the series splits
    # at BUDGET_SPLIT_DATE and both halves are reported separately. Cells whose
    # membership did not change are exempt and are absent from cells_that_split.
    era_buckets: dict[str, list[dict]] = {e: [] for e in BUDGET_ERAS}
    for r in rows:
        era_buckets[budget_era(r)].append(r)
    split_cells = sorted((m, t) for m, d in mt_buckets.items() for t in d
                         if era_split_applies(m, t))
    split_detail: dict[str, dict] = {}
    for m, t in split_cells:
        split_detail.setdefault(m, {})[t] = {
            e: _tally([r for r in mt_buckets[m][t] if budget_era(r) == e])
            for e in BUDGET_ERAS}
    out["budget_split"] = {
        "split_date": BUDGET_SPLIT_DATE,
        "what_changed": ("a tag's per-slate total is unchanged; each market now "
                         "gets its own allocation of it before any market takes "
                         "a second row"),
        "eras": {e: _tally(v) for e, v in era_buckets.items()},
        "cells_that_split": [[m, t] for m, t in split_cells],
        "by_market_by_tag": split_detail,
        "why_not_retagged": ("a row's selection rule is the one its writer "
                             "applied; restamping the rows on disk would "
                             "reinterpret evidence under a rule that did not "
                             "exist when they were chosen"),
    }
    out["sweep_readiness_by_market_tag"] = sweep_readiness_by_market_tag(path=path)

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


#: The DATED, committed read of the sub-ledger, and the registered eval artifact
#: for `betting_shadow_subledger`.
#:
#: WHY A SECOND FILE RATHER THAN A STAMP ON THE LEDGER. `data/betting_shadow.json`
#: is a bare JSON array of rows, and it has to stay one: `load()` reads it as a
#: list and the append-only checks compare list prefixes. There is nowhere to put
#: a top-level date without changing the shape that the no-revision invariant is
#: written against. Worse, a write stamp would answer the wrong question anyway.
#: The age that matters for a ledger is the age of its newest ROW, not the moment
#: somebody last rewrote the file, and those two diverge on exactly the nights
#: this module exists to survive: a slate where nothing cleared the floor
#: rewrites nothing and settles nothing, yet leaves the ledger perfectly current.
#:
#: So the readiness read gets its own file, it carries `generated_at`, and it also
#: carries `newest_row_at` so a reader can tell a fresh render of a stale ledger
#: from a fresh ledger.
READINESS_PATH = DATA_DIR / "betting_subledger.json"


def readiness_artifact(*, path: Path | None = None) -> dict:
    """The per-market, per-tag readiness read, dated, with nothing pooled.

    A COUNTER, NOT A VERDICT, and the distinction is the whole point of the row
    this artifact backs. Every cell reports how many settled rows it holds and
    whether that clears MIN_BETS_FOR_SWEEP. None of them reports a win rate as
    evidence, because a cell below its own floor has no evidence to report and
    printing 2-4 beside a threshold invites exactly the reading the floor exists
    to forbid.
    """
    rows = load(path)
    stamps = [str(r.get("settled_at") or r.get("logged_at") or "")
              for r in rows]
    stamps = sorted(x for x in stamps if x)
    summ = summary(path=path)
    return {
        "generated_at": _now(),
        "newest_row_at": stamps[-1] if stamps else None,
        "oldest_row_at": stamps[0] if stamps else None,
        "n_rows": len(rows),
        "min_bets_for_sweep": MIN_BETS_FOR_SWEEP,
        "by_market": summ.get("by_market"),
        "by_market_by_tag": summ.get("by_market_by_tag"),
        "sweep_readiness_by_market_tag": summ.get("sweep_readiness_by_market_tag"),
        "budget_split": summ.get("budget_split"),
        "reading": ("counts only. A cell is `ready` when its own settled count "
                    "reaches the floor; until then it has no verdict, and the "
                    "won/lost columns beside it are a description of history "
                    "rather than evidence about the next bet."),
        "pooling_is_forbidden": (
            "the markets price different quantities and the tags name different "
            "selection rules, so no cell here may be summed with another to "
            "reach a floor sooner"),
    }


def write_readiness_artifact(*, path: Path | None = None,
                             out: Path | None = None) -> dict:
    """Render `readiness_artifact()` to disk. Never raises on an I/O problem:
    this runs inside a nightly, and a failed render of a REPORT must not take
    down the pipeline that maintains the ledger the report reads."""
    art = readiness_artifact(path=path)
    dest = Path(out) if out is not None else READINESS_PATH
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(art, indent=1) + chr(10), encoding="utf-8")
    except OSError:
        log.warning("betting_shadow: could not write the readiness artifact to "
                    "%s; the ledger itself is unaffected", dest, exc_info=True)
    return art
