# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The control-window SALARY PATH: what a club will owe a player it controls,
season by season, for every season it still controls him.

Owner ask C (2026-09-16): "Since we have an arbitration predictor, can we more
accurately model player surplus value for arbitration players by evaluating the
surplus value relative to their projected arbitration amounts?"

The answer this module ships is COVERAGE, not a better award number. The
platform has priced surplus off projected arbitration salaries since GATE C
(2026-08-09), but only for the projection rows that carry no Spotrac contract
at all - 108 of them. A veteran on a one-year 2026 deal whose 2027 and 2028
arbitration steps are already sitting on /arbitration/ was skipped wholesale,
because the old gate asked "does this ROW have a surplus yet?" instead of "does
this SEASON have a price yet?". 408 more veterans and about 1,400
club-controlled seasons priced at nothing.

ONE PATH PER PLAYER. Every surface that prices a controlled season reads this
module and nothing else, so the same player costs the same on /projections/, on
the player card and in the Trade Machine.

PRECEDENCE, per season, and rule 1 is absolute:

  1. contract      a salary Spotrac has on file. NEVER re-priced by anything
                   below. This is the letter of
                   test_arb_export::test_gate_c_never_overwrites_a_real_contract
                   moved from the ROW to the SEASON; its intent is unchanged.
  2. arb_ladder    the /arbitration/ board's own priced step for that season
                   (pre-arbitration steps are the CBA league minimum BY RULE,
                   arbitration steps are the arb_award chain's projection).
  3. class_closure the arbitration years the last class token implies but
                   Spotrac's status grid does not list yet, chained through the
                   same banded raise estimator the board serves.
  4. none          the season carries a projection and no price, as today.

WHAT THIS MODULE DOES NOT DO
  * It never prices a never-debuted prospect. That population is the prospect
    surplus engine's: since docs/ARBITRATION_GATE.md section 20 (owner answer
    2026-09-25) value_framework prices its arbitration seasons under the
    clemens_2026 set through the same chain the board serves, from a
    league-minimum start (value_framework.arb_rung_usd), where section 6 had kept
    the clemens_2026 fraction ladder. The two stay separate paths.
  * It never invents a season past the end of club control. Where the control
    window is not established (a grid that ends on a pre-arbitration token, or a
    grid with no priced step to chain from) the path is SHORT and says so
    through `truncated`, rather than being extended on a debut+6 proxy.
  * It never re-prices an option season's SALARY. Option years are stamped
    (`opt`) and disclosed; pricing an opt-out needs an opt-out model with its
    own gate (decision D10). The one exception sits downstream of the path, in
    the surplus: a CLUB option season the club would decline prices at zero,
    never below (club_option_floor, owner answer VAL2-Q2).
  * It never reads `active_roster_days`, `debut+6` or `service_phase`.

THE FLAG IS THE REVERT. `SALARY_PATH_MODE` defaults to "full" because the owner
ordered the path served in full on 2026-09-16, before any clause of GATE C2 had
been scored (docs/ARBITRATION_GATE.md section 11a says so in those words). The
"off" path is kept, tested and byte-for-byte identical to the pre-change
payload, so a failed clause moves the served number BACK by one constant plus a
re-run of proj_export / export_trade_values_json / mlb_player_export. Section
11e of the gate doc fixes in advance which clause reverts how far.

KNOWN HOLES, none of them repaired here and all of them published in the
accountability census:
  * every 2027+ arbitration step is a 2022 CBA carry-forward past the
    2026-12-01 expiry, and no interval covers that;
  * the class token is inferred rather than read from published service time on
    709 of 852 board rows, and class closure uses it TWICE - once for the rung
    and once for the horizon;
  * arb-2+ is a served NULL (an empirical step multiplier beat the model), and
    closure runs that same multiplier one to two rungs further;
  * window LENGTH becomes a property of Spotrac's grid depth, so two comparable
    players can carry 2 and 4 priced seasons for no baseball reason.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

# ---------------------------------------------------------------------------
# The one constant. "off" reproduces the pre-2026-09-16 payload byte for byte.
#
#   off      rule 1 only, plus the legacy GATE C whole-row fallback. The revert.
#   ladder   rules 1 + 2: the board's own priced steps, past `signed_through`.
#   closure  rules 1 + 2 + 3: the arbitration years the class token implies.
#   full     + the club's non-tender option, priced by backward induction.
#
# SERVED VALUE: "full" (owner decision, 2026-09-16).
# ---------------------------------------------------------------------------
SALARY_PATH_MODE = "full"

MODES = ("off", "ladder", "closure", "full")

#: The 2022 CBA minimum table, in whole dollars. The config carries the tabled
#: years; anything past the last tabled year CARRIES IT FORWARD, which is the
#: same assumption /arbitration/ publishes in its `rules` block and the same one
#: the board's own pre-arbitration steps are priced on. It is a RULE, not a
#: prediction, and 52.1% of the money this module adds is exactly this line.
LEAGUE_MIN_CURATED = {
    2018: 545_000, 2019: 555_000, 2020: 563_000, 2021: 571_000,
    2022: 700_000, 2023: 720_000, 2024: 740_000, 2025: 760_000, 2026: 780_000,
}

#: Spotrac status-grid token -> (class, super-two). "ARB 3 (S2)" -> (3, True).
_TOK = re.compile(r"^ARB\s*([1-9]\d*)(\s*\(S2\))?$")

#: The band the board publishes on its own arbitration steps: 22% at arb-1,
#: widening 8 points a rung because each rung inherits the previous rung's
#: error. Deliberately NOT a calibrated interval (see the eval artifact), which
#: is why `surSalLo`/`surSalHi` ship as their own field and are never fused
#: into the WAR fan.
BAND_BASE = 0.22
BAND_STEP = 0.08

#: CBA Article VI: a salary cut of more than 20 percent is not an arbitration
#: award. arb_dataset excludes ratios below it from the LABEL set for the same
#: reason. It is a RULE, not a prediction, and it is the only thing in this
#: module that ever overrides a number the /arbitration/ board published.
MAX_CUT = 0.80


def _band_spread(cls: int) -> float:
    return BAND_BASE + BAND_STEP * max(0, int(cls or 1) - 1)


def class_of(tok) -> tuple:
    """('ARB 3 (S2)') -> (3, True); ('PRE-ARB') -> (0, False); (None) -> (None, False)."""
    t = (tok or "").strip().upper()
    if t == "PRE-ARB":
        return 0, False
    m = _TOK.match(t)
    return (int(m.group(1)), bool(m.group(2))) if m else (None, False)


# ---------------------------------------------------------------------------
# Loaders. The only I/O in the module, each memoized, each degrading to empty.
# ---------------------------------------------------------------------------

_BOARD_CACHE = None
_OPTIONS_CACHE = None
_RAISE_CACHE = None
_LEAGUE_MIN_CACHE = None


def board_rows(path=None) -> dict:
    """{"vintage": "YYYY-MM-DD", "rows": {mlbam: row}} from data/arbitration.json,
    keeping lo/hi/token and the row flags.

    The shape proj_export._arb_salary_paths() carried until 2026-09-16 collapsed
    the ladder to {season: usd} and threw the award band and the class token
    away, which is why the old gate could neither publish a salary band nor
    close the control window. Both are kept here.

    Returns empty when the board has not been exported, so a cold tree still
    builds and the accountability census reports the absence rather than the
    pipeline failing.
    """
    global _BOARD_CACHE
    if _BOARD_CACHE is None or path is not None:
        p = Path(path) if path is not None else (DATA_DIR / "arbitration.json")
        rows = {}
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        vintage = doc.get("generated_at")
        for row in doc.get("rows") or []:
            m = row.get("m")
            if not m:
                continue
            steps = []
            for st in row.get("l") or []:
                if not st or st[0] is None:
                    continue
                steps.append({
                    "season": int(st[0]),
                    "usd": int(st[1]) if len(st) > 1 and st[1] else None,
                    "lo": int(st[2]) if len(st) > 2 and st[2] else None,
                    "hi": int(st[3]) if len(st) > 3 and st[3] else None,
                    "tok": st[4] if len(st) > 4 else None,
                })
            steps.sort(key=lambda s: s["season"])
            rows[int(m)] = {"m": int(m), "steps": steps, "c": row.get("c"),
                            "e": row.get("e"), "sv": row.get("sv"),
                            "svy": row.get("svy"), "yl": row.get("yl")}
        out = {"vintage": vintage, "rows": rows}
        if path is not None:
            return out
        _BOARD_CACHE = out
    return _BOARD_CACHE


def options(path=None) -> dict:
    """{player_key: {"club": [season, ...], "player": [season, ...]}}.

    The same data/contract_options.json bayes_trade_value._contract_options
    reads, so the two can never disagree about which seasons carry an option.
    The file is on deploy/data_exclude.txt and never reaches the webroot, which
    is why the option seasons are STAMPED onto the payload here rather than
    looked up client-side.
    """
    global _OPTIONS_CACHE
    if _OPTIONS_CACHE is None or path is not None:
        p = Path(path) if path is not None else (DATA_DIR / "contract_options.json")
        out = {}
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        for key, ent in (doc.get("players") or {}).items():
            club = []
            for o in ent.get("club_options") or []:
                y = o.get("year") if isinstance(o, dict) else o
                if y:
                    club.append(int(y))
            player = [int(y) for y in (ent.get("player_options") or []) if y]
            if club or player:
                out[key] = {"club": sorted(club), "player": sorted(player)}
        if path is not None:
            return out
        _OPTIONS_CACHE = out
    return _OPTIONS_CACHE


def league_min_table() -> dict:
    """The CBA minimum by season, config first, curated fallback. Shared with
    arb_dataset so the board and the path price a pre-arbitration season
    identically."""
    global _LEAGUE_MIN_CACHE
    if _LEAGUE_MIN_CACHE is None:
        out = dict(LEAGUE_MIN_CURATED)
        try:
            import value_framework as vf
            for k, v in (vf._config().get("league_min_by_year") or {}).items():
                out[int(k)] = int(round(float(v) * 1e6))
        except Exception as exc:                  # pragma: no cover - defensive
            _log.warning("salary_path: league minimum config unreadable: %s", exc)
        _LEAGUE_MIN_CACHE = out
    return _LEAGUE_MIN_CACHE


def league_min_usd(season: int, table=None) -> int:
    """The minimum for one season, CARRYING THE LAST TABLED YEAR FORWARD. The
    2022 CBA expires 2026-12-01 and nothing in this tree estimates what
    replaces it, so a 2029 minimum is the 2026 figure with that assumption
    stated, exactly as /arbitration/ states it in its `rules` block."""
    t = table or league_min_table()
    if not t:
        return 0
    s = int(season)
    if s in t:
        return int(t[s])
    last = max(t)
    return int(t[last if s > last else min(t)])


_DEFLATOR_SERIES = None


def arb_deflator_series() -> dict | None:
    """The league-wide arbitration salary index by season (arb_model.fit_deflator
    on the board's panel, the series board_raise_fn re-inflates with), for the
    $/WAR path's companion legs (VAL_5, OD-4 own_trends). Memoized; None on a
    cold tree."""
    global _DEFLATOR_SERIES
    if _DEFLATOR_SERIES is None:
        try:
            import arb_dataset as A
            import arb_model as Mod
            panel = A.build_panel(log=None)
            sc = A.scored_rows(panel["rows"])
            seasons = sorted({r["season"] for r in sc})
            _DEFLATOR_SERIES = dict(Mod.fit_deflator(sc, base_year=seasons[0])) or "unavailable"
        except Exception as exc:                  # pragma: no cover - defensive
            _log.warning("salary_path: arb deflator unavailable: %s", exc)
            _DEFLATOR_SERIES = "unavailable"
    return None if _DEFLATOR_SERIES == "unavailable" else _DEFLATOR_SERIES


def board_raise_fn():
    """The SAME arb-2+ estimator the /arbitration/ board serves, as a callable
    `(prior_usd, cls, season, s2, league_min_usd) -> (pred, lo, hi)`.

    GATE A ruled the per-player model a NULL at arb-2 and later, so the board
    serves the banded empirical step multiplier there and so does class
    closure. Serving a different estimator for the seasons Spotrac has not
    listed yet than for the ones it has would make the two halves of one
    player's ladder incomparable.

    Memoized, and it degrades to None on any failure (a cold tree with no
    panel), in which case closure does not run and the row ships short with its
    reason published rather than extended on a guess.
    """
    global _RAISE_CACHE
    if _RAISE_CACHE is not None:
        return None if _RAISE_CACHE == "unavailable" else _RAISE_CACHE
    try:
        import arb_dataset as A
        import arb_model as Mod
        panel = A.build_panel(log=None)
        sc = A.scored_rows(panel["rows"])
        seasons = sorted({r["season"] for r in sc})
        defl = Mod.fit_deflator(sc, base_year=seasons[0])
        banded = Mod.fit_banded_multipliers(sc, defl)
    except Exception as exc:                      # pragma: no cover - defensive
        _log.warning("salary_path: arb estimator unavailable: %s", exc)
        _RAISE_CACHE = "unavailable"
        return None

    def _raise(prior_usd, cls, season, s2, lm_usd):
        d = Mod.banded_predict({"prior_salary": prior_usd, "arb_year": int(cls),
                                "season": int(season), "league_min": lm_usd},
                               banded, defl)
        if not d:
            return None, None, None
        # Re-inflate exactly the way arb_export.build_board does: the estimator
        # works in deflated dollars and the board multiplies the season's
        # deflator back in, carrying the last known level forward.
        lvl = defl.get(int(season)) or defl[max(defl)]
        pred = d * lvl
        sp = _band_spread(cls)
        # The board's band rule, low end held at the league minimum (owner
        # answer M12-4), so a closure season's band matches a grid season's.
        lo = pred * (1 - sp)
        if lm_usd and lo < lm_usd:
            lo = float(lm_usd)
        return _k(pred), _k(lo), _k(pred * (1 + sp))

    _RAISE_CACHE = _raise
    return _raise


def _reset_caches() -> None:
    """Tests only."""
    global _BOARD_CACHE, _OPTIONS_CACHE, _RAISE_CACHE, _LEAGUE_MIN_CACHE
    _BOARD_CACHE = _OPTIONS_CACHE = _RAISE_CACHE = _LEAGUE_MIN_CACHE = None


def _k(usd):
    """Whole dollars to the nearest thousand - the board's own convention, so a
    closure season and a grid season are the same kind of number."""
    if usd is None:
        return None
    try:
        return int(round(float(usd) / 1000.0) * 1000)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Class closure
# ---------------------------------------------------------------------------

def class_closure(steps, *, horizon_last, raise_fn, league_min=None,
                  anchor=None):
    """The arbitration years the last class token implies and Spotrac's status
    grid does not list yet.

    THE GRID IS NOT THE CONTROL WINDOW. 665 of 852 board rows carry exactly two
    seasons, because Spotrac's status table looks about two years forward; a
    player entering arbitration for the first time is controlled for three more
    (four as a Super Two). Closure extends the window WITHOUT a service-time
    input, by reading the class token the last grid season already carries.

    THREE PROPERTIES, EACH MEASURED ON THE 852 SERVED ROWS:

    1. `K = max(K_s2, k_last)`, never `K = K_s2`. Four rows end on token
       `ARB 4` with no `(S2)` marker (Austin Wynns, Cole Sulser, Garrett
       Stubbs, Steven Wilson; all four join projection veterans). A rule that
       derives K = 3 for them returns add = -1, i.e. it would UNPRICE a season
       the grid observed. The max clamp, plus `max(0, ...)`, is what stops that.
       The token is the more reliable of the two statements here: it was
       observed, K was inferred.

    2. THE PRECONDITION IS A PRICED SEASON TO CHAIN FROM - anywhere in the
       window, not specifically on the grid. Closure raises off a salary, so it
       cannot run where the whole window has none. 87 board rows carry an
       entirely unpriced grid (arb-2-and-later rows with no prior salary on
       file, flag bit 4), but 72 of them have a CONTRACT season sitting beside
       the hole, which is a prior salary; anchoring on the grid alone left
       those 72 with no arbitration years at all and a served line reading "no
       prior salary on file" printed next to the contracted salary. Measured on
       the served board: the rule extends 245 rows by 467 seasons, and 11 rows
       are left genuinely unpriceable and ship `truncated: "no_prior_salary"`,
       counted under their own name in the accountability census.

    3. A GRID THAT ENDS ON PRE-ARB IS NOT EXTENDED (442 rows, 266 of them
       projection veterans). The arbitration START year is what is unknown
       there, and inventing it without service time is the shape of a prior
       failure in this tree. Those rows ship `truncated: "prearb_grid"`.

    `(S2)` is read off ANY arbitration token in the row rather than only the
    last: 0 rows mix `(S2)` across their arb tokens and 0 rows have a
    non-consecutive arb chain, so the two forms agree today and the `any()`
    form is the one that stays correct if a row ever does mix.

    THE ANCHOR IS THE PATH, NOT THE GRID (repair, 2026-09-17). The first shape
    of this rule chained off `steps[-1]` and gave up whenever THAT step carried
    no price, which read the precondition off the wrong object: a row whose
    grid steps are unpriced but whose previous season is bought by a CONTRACT
    has a prior salary sitting right beside the hole. 59 arbitration-eligible
    rows shipped one priced season and a served line reading "no prior salary
    on file" printed next to the contracted salary it could have raised from
    (Elly De La Cruz, Andy Pages, Otto Lopez, Miguel Vargas, Wilyer Abreu) -
    the exact population the owner's ask names. `anchor` is now the last season
    of the ASSEMBLED path that carries a price, contract dollars included, and
    the class of a season is read off the grid's own token line,
    `cls(s) = k_last + (s - last_grid_season)`, so an anchor BEFORE the grid's
    last step walks forward into the grid's own tokens and an anchor after it
    walks past them. `truncated: "no_prior_salary"` now means what it says: no
    season of the path, contract included, carries a price to chain from.
    """
    if not steps:
        return []
    last = steps[-1]
    k, _ = class_of(last.get("tok"))
    if not k:                      # PRE-ARB grid: the arb start year is unknown
        return []
    if raise_fn is None:
        return []
    if anchor is None:
        anchor = ({"season": int(last["season"]), "usd": last["usd"]}
                  if last.get("usd") is not None else None)
    if not anchor or anchor.get("usd") is None:
        return []                  # no prior salary anywhere: no chain to run
    s2 = any(class_of(s.get("tok"))[1] for s in steps if class_of(s.get("tok"))[0])
    K = max(4 if s2 else 3, k)     # never derive a K below an OBSERVED token
    last_grid = int(last["season"])
    out, prior = [], int(anchor["usd"])
    season = int(anchor["season"]) + 1
    while season <= horizon_last:
        cls = k + (season - last_grid)
        if cls > K:
            break
        if cls < 1:                # still pre-arbitration: not this rule's job
            season += 1
            continue
        lm = league_min_usd(season, league_min)
        pred, lo, hi = raise_fn(prior, cls, season, s2, lm)
        if not pred:
            break
        out.append({"season": season, "usd": int(pred),
                    "lo": lo, "hi": hi,
                    "tok": "ARB %d%s" % (cls, " (S2)" if s2 else ""),
                    "cls": cls, "s2": s2, "src": "class_closure"})
        prior = pred
        season += 1
    return out


# ---------------------------------------------------------------------------
# The tender cliff
# ---------------------------------------------------------------------------

def tender_cliff(d_usd, cuttable, r: float = 0.07):
    """The club's non-tender option, by BACKWARD INDUCTION.

    `d_usd[t]` is season t's surplus in UNDISCOUNTED dollars; `cuttable[t]` is
    True only when the club may walk away before season t. Returns
    `(npv_at_t0, cut_index or None)`.

    WHY NOT A FORWARD STOPPING RULE. The first shape of this repair cut at
    `t* = min{t : C_t < 0}`, the first season whose own continuation is
    negative. That is not the decision a club faces. Declining to tender loses
    the player for EVERY later controlled season, so the object is the
    CONTINUATION value, and the decision recurs every December, so the correct
    object is optimal stopping. Worked, r = 0.07, dollars in $M:

        [+10, -1, -30]   backward $10.0M, cut at index 1.   Forward: $0.
        [+10, -1, +30]   backward $35.3M, no cut.           Forward: agrees.
        [ -5, +30, -40]  backward $23.0M, cut at index 2.   Forward: $0.

    The first line is this design's own unit test 6, which the forward rule
    failed; the third is the club tendering through the good year and walking
    after it, which a forward rule cannot express at all.

    WHICH SEASONS ARE CUTTABLE. Arbitration seasons only: `src` in
    {arb_ladder, class_closure} AND a token starting with ARB. A contracted
    season is never cuttable - the club owes the money, which is why a signed
    season can and does carry a negative surplus and the copy says so. A
    PRE-ARBITRATION season is never cuttable either: a club options or
    designates a pre-arb player, it does not decline to tender him, and 52.1%
    of the money this module adds is pre-arb, so a cliff that fired on them
    would be labelling the wrong mechanism on the majority population
    (decision D11 - that abandonment option is NOT priced and its residual
    negative dollars are published instead).

    THE ONE REMAINING CONSERVATISM, and the copy says exactly this and nothing
    more: the cliff is applied to the MEAN projection path, and
    E[max(0, X)] >= max(0, E[X]), so the served number is a LOWER BOUND on what
    the option is worth. Serving the expectation needs a calibrated joint
    distribution over (WAR, award), which this tree does not have.

    Because the loop runs backward, `cut` ends at the EARLIEST season where
    walking is optimal, and every season from there on is abandoned - which is
    what walking means. W[0] is then exactly the discounted sum of the seasons
    BEFORE the cut, so the published invariant `surNpv == NPV(non-null sur)`
    stays true to the dollar and is testable.
    """
    H = len(d_usd)
    W = [0.0] * (H + 1)
    cut = None
    for t in range(H - 1, -1, -1):
        cont = float(d_usd[t]) / ((1.0 + r) ** t) + W[t + 1]
        if cuttable[t] and cont < 0.0:
            W[t], cut = 0.0, t      # walking beats carrying him from here
        else:
            W[t] = cont
    return W[0], cut


def forward_cliff(d_usd, cuttable, r: float = 0.07):
    """The rule R1 replaced, kept so GATE C2's C7'b can score the shipped rule
    against it on every served row. It stops at the first cuttable season whose
    own remaining continuation is negative and abandons everything from there.
    It is one feasible stopping time, so backward induction can never pay less.
    Never used to serve."""
    H = len(d_usd)
    cut = None
    for t in range(H):
        if not cuttable[t]:
            continue
        cont = sum(float(d_usd[u]) / ((1.0 + r) ** u) for u in range(t, H))
        if cont < 0.0:
            cut = t
            break
    end = H if cut is None else cut
    return sum(float(d_usd[t]) / ((1.0 + r) ** t) for t in range(end)), cut


def is_cuttable(season: dict) -> bool:
    """An ARBITRATION season, and nothing else (R2)."""
    return (season.get("src") in ("arb_ladder", "class_closure")
            and str(season.get("tok") or "").upper().startswith("ARB"))


# ---------------------------------------------------------------------------
# The path
# ---------------------------------------------------------------------------

def _contract_prices_window(sal, first_season, horizon) -> bool:
    """Did the contract price ANY season the projection board prices - the
    in-progress season (the rest-of-season leg) or one of the projected ones?

    This is the pure re-statement of the pre-2026-09-16 row-level gate
    ("skip any row that already carries a surplus"), and it is used only by
    mode "off". It is NOT `bool(sal)`: Spotrac lists status rows with an empty
    `salary_by_year`, and 23 of the 108 GATE C rows carry exactly such a row,
    so keying the legacy branch off contract PRESENCE rather than contract
    PRICE would have unpriced them.
    """
    return any((first_season - 1 + t) in sal for t in range(horizon + 1))


def salary_path(mlbam, *, key=None, first_season, horizon, contract=None,
                board_row=None, league_min=None, opts=None, mode=None,
                raise_fn=None, vintage=None, tail_last=None) -> dict:
    """One player's control-window salary path. PURE: every input is passed in.

    `contract` is a Spotrac contract dict (`salary_by_year`, `signed_through`);
    `board_row` is one row of `board_rows()["rows"]`; `opts` is one entry of
    `options()`; `raise_fn` is `board_raise_fn()` (passed in so the unit tests
    can inject a deterministic estimator and so nothing in here does I/O).

    RULE 1 IS ABSOLUTE and it is locked twice on purpose. A season a contract
    prices is taken from the contract before anything else is consulted, and
    rule 2's pool separately drops every season at or before `signed_through`.
    The second lock is deliberately redundant: Spotrac's status grid sometimes
    carries a token for a season an extension also covers, and a token must
    never beat dollars.

    THE CONTRACT TAIL (owner answer 2026-09-25, M05-01 step 2). `tail_last`,
    when it is past the horizon, extends the path through that season with the
    GUARANTEED seasons only: a season past the horizon carries a price exactly
    when the contract lists dollars for it, and no board step, class-closure
    rung or league minimum is ever projected out there. The caller decides how
    far the tail may run (proj_export caps it at the length of the WAR path it
    prices with); None keeps the path at `horizon` seasons, byte for byte.
    """
    mode = mode or SALARY_PATH_MODE
    if mode not in MODES:
        raise ValueError("unknown SALARY_PATH_MODE %r" % (mode,))
    sal = {int(y): int(v)
           for y, v in ((contract or {}).get("salary_by_year") or {}).items()}
    thru = (contract or {}).get("signed_through")
    thru = int(thru) if thru is not None else None
    steps = list((board_row or {}).get("steps") or [])
    last_season = first_season + horizon - 1

    # ---- rule 2 pool: the board's own priced steps ------------------------
    grid = {}
    for st in steps:
        s = st["season"]
        if st["usd"] is None:
            continue
        if mode != "off" and thru is not None and s <= thru:
            continue                      # rule 1's second lock
        grid[s] = st

    # ---- the chain anchor: the LAST PRICED SEASON of the assembled path ---
    # Rules 1 and 2 both put dollars on a season, and whichever of them lands
    # LATEST is the salary an arbitration award raises from. Reading the anchor
    # off `steps[-1]` instead left 59 arbitration-eligible rows with one priced
    # season and a served line reading "no prior salary on file" beside the
    # contracted salary it could have chained from. The in-progress season
    # (`first_season - 1`) counts as an anchor: it is the prior salary in the
    # award model's own sense and the season the rest-of-season leg prices.
    anchor = None
    for s in range(first_season - 1, last_season + 1):
        if s in sal:
            anchor = {"season": s, "usd": int(sal[s])}
        elif s in grid and grid[s].get("usd") is not None:
            anchor = {"season": s, "usd": int(grid[s]["usd"])}

    # ---- rule 3 pool: the seasons the class token implies -----------------
    closed = {}
    truncated = None
    buyout = False
    if steps:
        k_last, _ = class_of(steps[-1].get("tok"))
        if not k_last:
            truncated = "prearb_grid"
        elif anchor is None:
            # NOW A STATEMENT ABOUT THE WHOLE PATH, not about one grid step: no
            # season of this window, contract dollars included, carries a price
            # to raise from.
            truncated = "no_prior_salary"
    # A CONTRACT THAT BUYS OUT THE WHOLE LISTED GRID ENDS THE QUESTION HERE.
    # Where `signed_through` covers the last grid season, the class token
    # describes the status the extension replaced. The guard is a SCOPE line,
    # not a claim about baseball: a club that signed a player through his last
    # listed arbitration year may still control the season after it, and this
    # rule declines to price that season. It is what holds the pre-registered
    # "133 rows signed through 2028+ move exactly $0" invariant (section 9 of
    # FINAL_C), so lifting it is its own measured change; `closure_buyout_rows`
    # in the accountability census counts what it costs.
    if mode in ("closure", "full") and not (
            steps and thru is not None and int(steps[-1]["season"]) <= thru):
        for st in class_closure(steps, horizon_last=last_season,
                                raise_fn=raise_fn, league_min=league_min,
                                anchor=anchor):
            if thru is not None and st["season"] <= thru:
                continue
            closed[st["season"]] = st
    elif mode in ("closure", "full") and steps and thru is not None:
        buyout = True

    opt_seasons = {}
    for kind in ("club", "player"):
        for y in (opts or {}).get(kind) or []:
            opt_seasons.setdefault(int(y), kind)

    seasons = []
    for t in range(horizon):
        s = first_season + t
        cell = {"t": t, "season": s, "usd": None, "lo": None, "hi": None,
                "src": "none", "tok": None, "cls": None, "s2": False,
                "opt": opt_seasons.get(s), "cut": False}
        if s in sal:                                            # rule 1
            cell.update(usd=int(sal[s]), lo=int(sal[s]), hi=int(sal[s]),
                        src="contract", tok="signed")
        elif mode == "off":
            # The pre-2026-09-16 gate: a row the contract join left ENTIRELY
            # unpriced took the whole board ladder, INCLUDING seasons at or
            # before `signed_through`; a row with any contract price at all
            # took nothing. Kept so "off" is a revert and not a
            # re-implementation. The ROW-level half of that rule ("has this row
            # any surplus yet?") lives in the caller, which is where the
            # byte-for-byte guarantee is asserted.
            if not _contract_prices_window(sal, first_season, horizon) and s in grid:
                st = grid[s]
                c, s2 = class_of(st.get("tok"))
                cell.update(usd=st["usd"], lo=st.get("lo"), hi=st.get("hi"),
                            src="arb_ladder", tok=st.get("tok"), cls=c, s2=s2)
        elif s in grid:                                         # rule 2
            st = grid[s]
            c, s2 = class_of(st.get("tok"))
            cell.update(usd=st["usd"], lo=st.get("lo"), hi=st.get("hi"),
                        src="arb_ladder", tok=st.get("tok"), cls=c, s2=s2)
        elif s in closed:                                       # rule 3
            st = closed[s]
            cell.update(usd=st["usd"], lo=st.get("lo"), hi=st.get("hi"),
                        src="class_closure", tok=st.get("tok"),
                        cls=st.get("cls"), s2=st.get("s2"))
        if cell["lo"] is None and cell["usd"] is not None:
            cell["lo"] = cell["hi"] = cell["usd"]
        seasons.append(cell)

    # ---- the contract tail: guaranteed seasons past the horizon ----------
    # Rule 1 alone. A gap year inside the tail stays an unpriced cell so the
    # season index `t` keeps meaning "seasons after first_season" on every cell
    # (the surplus strip and its NPV identity enumerate by position), and the
    # tail is trimmed back to its last priced season.
    tail_end = None
    if tail_last is not None and mode != "off" and int(tail_last) > last_season:
        for s in range(last_season + 1, int(tail_last) + 1):
            cell = {"t": s - first_season, "season": s, "usd": None, "lo": None,
                    "hi": None, "src": "none", "tok": None, "cls": None,
                    "s2": False, "opt": opt_seasons.get(s), "cut": False}
            if s in sal:
                cell.update(usd=int(sal[s]), lo=int(sal[s]), hi=int(sal[s]),
                            src="contract", tok="signed")
            seasons.append(cell)
        while len(seasons) > horizon and seasons[-1]["usd"] is None:
            seasons.pop()
        if len(seasons) > horizon:
            tail_end = seasons[-1]["season"]

    # ---- the CBA maximum-cut floor across a contract-to-arbitration step --
    # The board chains each award off the PANEL's prior salary, which is the
    # salary Spotrac's arbitration table knows about; it does not know about an
    # extension that pays the player more. Juxtaposing the two inside one path
    # produced 14 served rows whose next season CUT the previous one by more
    # than the CBA allows - Brice Turang $9.90M in 2027 against a projected
    # $5.95M award in 2028 - which the design's own acceptance clause C5' fails
    # on. Article VI says that is not an award, so the step is floored at 80%
    # of the salary the club is actually paying, and the floor CARRIES DOWN the
    # chain it repaired (the floored figure is the next rung's prior salary).
    # It fires only where the prior season is CONTRACTED, which is the case the
    # board cannot see; two board-chained steps are left alone so C5' keeps
    # being able to fail on them.
    floored = 0
    if mode != "off":
        prior_usd = sal.get(first_season - 1)
        carry = prior_usd is not None
        for c in seasons:
            if c["usd"] is None:
                continue
            if (c["src"] in ("arb_ladder", "class_closure")
                    and str(c["tok"] or "").upper().startswith("ARB")):
                if carry and prior_usd:
                    fl = _k(MAX_CUT * float(prior_usd))
                    if fl and c["usd"] < fl:
                        c["usd"] = fl
                        c["lo"] = fl if (c["lo"] or 0) < fl else c["lo"]
                        c["hi"] = max(int(c["hi"] or fl), fl)
                        c["cba_floor"] = True
                        floored += 1
            else:
                carry = (c["src"] == "contract")
            prior_usd = c["usd"]

    priced = [c for c in seasons if c["usd"] is not None]
    last_controlled = priced[-1]["season"] if priced else None
    order = ("contract", "arb_ladder", "class_closure")
    mix = [s for s in order if any(c["src"] == s for c in priced)]
    # A window that ran out of HORIZON rather than out of INFORMATION is not
    # truncated: the reader is told the window is short only where it genuinely
    # is not established.
    if truncated and last_controlled is not None and last_controlled >= last_season:
        truncated = None
    return {
        "seasons": seasons,
        "last_controlled": last_controlled,
        "src_mix": "+".join(mix) or None,
        "truncated": truncated if mode != "off" else None,
        "cut_season": None,
        "cba_floored": floored,
        "closure_buyout": buyout,
        # The last guaranteed season the tail priced past the horizon, or None
        # when the path stops at the horizon. control_end reads it: a window
        # priced through its guarantee did not run out of HORIZON.
        "tail_last": tail_end,
        "vintage": vintage,
        "mode": mode,
    }


def apply_cliff(path: dict, d_usd, r: float = 0.07):
    """Run the tender cliff over a priced path and stamp the result.

    `d_usd[t]` is the season surplus in undiscounted dollars, aligned to
    `path["seasons"]`. Mutates the path (`cut` per season, `cut_season`) and
    returns `(npv_usd, cut_index or None)`. A season with no price contributes
    zero and is never cuttable, so a gap in the middle of a window cannot
    trigger a walk.
    """
    seasons = path["seasons"]
    cuttable = [is_cuttable(c) and c["usd"] is not None for c in seasons]
    d = [float(d_usd[t]) if (t < len(d_usd) and d_usd[t] is not None
                             and seasons[t]["usd"] is not None) else 0.0
         for t in range(len(seasons))]
    npv, cut = tender_cliff(d, cuttable, r)
    if cut is not None:
        path["cut_season"] = seasons[cut]["season"]
        for c in seasons[cut:]:
            c["cut"] = True
    return npv, cut


def payload_path(path: dict):
    """`salPath`: one TUPLE per priced season, ordered.

    A tuple rather than an object on purpose: about 48 bytes a season over
    ~1,400 new seasons is ~68KB on a payload already several MB, and the same
    strip rendered from objects would have cost several times that.
    [season, usd, lo, hi, tok, src, cut]
    """
    out = []
    for c in path["seasons"]:
        if c["usd"] is None:
            continue
        out.append([c["season"], c["usd"], c["lo"], c["hi"],
                    c["tok"], c["src"], 1 if c["cut"] else 0])
    return out or None


def control_end(path: dict, thru, first_season: int, horizon: int) -> dict:
    """The last season the club holds this player's rights, and how well we
    know it. THE ONE DERIVED ANSWER; every surface reads this and nothing else.

    `salThru` (``path["last_controlled"]``) is NOT that season. It is the last
    season of the horizon that carries a PRICE, which is a narrower object in
    three ways: it is capped at ``first_season + horizon - 1`` except where the
    contract tail prices a guarantee past it (a tail cut short, or a path built
    without one, reads short), it stops where the published
    arbitration grid stops rather than where control stops (`truncated`), and
    it can sit at or past a season the tender cliff has already stamped `cut`.
    This function is the only place the COPY is allowed to read, because it is
    the only object in this tree that is a statement about CONTROL rather than
    about PRICING.

    Returns a dict:
      end    int or None   the last controlled season, `max(thru, salThru)`,
                           because club control is never SHORTER than the
                           guarantee. That one line is what makes the served
                           cross-module invariant hold on every row
                           (test_served_control_window_coherence).
      open   bool          the platform knows more controlled seasons exist and
                           cannot name them, so the year is a FLOOR: the surface
                           renders `YYYY+` and says "through at least". An
                           INFORMATION failure - a grid that ends on a
                           pre-arbitration token, or no prior salary to chain
                           from - and never a horizon failure.

                           A CLOSURE BUY-OUT IS NOT ONE OF THEM. Where a
                           contract covers the whole published grid, the grid's
                           LAST TOKEN says what follows: on a pre-arbitration
                           token more controlled seasons certainly follow, and
                           `truncated` is already "prearb_grid" for that row, so
                           this function marks it open through that reason. On
                           an ARB rung the next season is FREE AGENCY, and
                           "through at least" would assert controlled seasons
                           that do not exist - on a row whose surplus correctly
                           stops. It is 0 served rows today only because both
                           current buy-out rows end on a pre-arbitration token;
                           the first club that extends an arbitration-eligible
                           player through his last arbitration year is the case,
                           and it renders a plain year and the guarantee word.
      est    bool          a season inside the span is priced on a PROJECTION
                           rather than on a signed contract, so the surface
                           draws it dashed.
      why    str or None   one of `prearb_grid`, `no_prior_salary`,
                           `closure_buyout`, `horizon`, `contract_only`, None.
                           Drives the second sentence of every tip.
      guar   int or None   the guarantee, carried through unchanged. The words
                           "signed" and "guaranteed" belong to THIS field and
                           are never attached to `end`.
      basis  str or None   the path's own source mix, for the CSV column.

    A horizon failure prints a PLAIN year and no `+`, on purpose: it is a
    statement about the five seasons this platform prices, not about the
    player, and every such row already names a season at or past the end of
    everything priced here, so nothing downstream can contradict it. Putting a
    `+` on 39 nine-figure veteran contracts would be the noise that teaches a
    reader to ignore the mark where it matters. Since the contract tail (owner
    answer 2026-09-25) those 39 read `contract_only`: their guarantee is priced
    to its last season.
    """
    last_h = int(first_season) + int(horizon) - 1
    try:
        thru = int(thru) if thru is not None else None
    except (TypeError, ValueError):
        thru = None
    sal_thru = path.get("last_controlled")
    end = max(thru or 0, sal_thru or 0) or None
    est = sal_thru is not None and (not thru or sal_thru > thru)
    if path.get("truncated"):
        why = path["truncated"]
    elif end is None:
        why = None                     # nothing on file at all: the cell says so
    elif end >= last_h and not (path.get("tail_last") and end <= path["tail_last"]):
        # A window whose guarantee the contract tail priced to its last season
        # (owner answer 2026-09-25) stopped where the CONTRACT stops, not where
        # the horizon does, so it falls through to the tests below and reads
        # `contract_only`. A tail cut short of the guarantee is still a horizon
        # failure and still says so.
        # THE HORIZON TEST OUTRANKS THE BUY-OUT TEST. A window that reaches the
        # last priced season ran out of HORIZON whatever else is true of it, and
        # `truncated` is cleared on exactly those rows a few lines above for the
        # same reason; leaving the buy-out test first let a row whose grid was
        # bought out AND priced to the horizon end report a reason about the
        # grid when the only thing that stopped it was this platform's window.
        why = "horizon"
    elif path.get("closure_buyout"):
        why = "closure_buyout"
    elif not sal_thru or (thru and sal_thru <= thru):
        why = "contract_only"
    else:
        why = None                     # an exact, established control end
    # A FLOOR NEEDS A YEAR TO BE A FLOOR. 8 served rows carry
    # `no_prior_salary` with no contract and no priced season at all: nothing is
    # known about them, so there is no "at least YYYY" to render and the cell
    # reads `none`. Flagging them open would be a mark no surface could paint,
    # and it would contradict the cell four characters away. `why` still carries
    # the reason, which is what the tip reads.
    open_ = bool(path.get("truncated")) and end is not None
    return {"end": end, "open": open_, "est": est, "why": why,
            "guar": thru,
            "basis": path.get("src_mix") or ("contract" if thru else None)}


# THE CLUB'S RIGHT (owner answer VAL2-Q2, 2026-09-30). A club option season the
# club would decline prices at zero, never below: the club holds the right to
# walk, so a losing club-option season contributes max(0, surplus). It is the
# ONE rule every surface prices a contract with: proj_export applies it to the
# served surplus (and to the award-band endpoints), and the trade board, the
# Trade Machine and the Club Ledger read that surplus rather than re-pricing.
# PLAYER and MUTUAL options are not club rights and keep their treatment: a
# player option season still prices as if the player stays (the opt-out is not
# modelled), and a mutual option is never a salary-path season (it exists only
# on /fa/'s pending-option rows, priced by fa_class's explicit prior). The
# decision is per season and taken on the mean path, like the tender cliff; the
# curated data/contract_options.json is the only source of club option seasons
# (Bobby Witt Jr. 2035-2037 today). False restores D10 (stamped, priced as
# guaranteed), byte for byte.
CLUB_OPTION_DECLINE = True


def club_option_floor(seasons, d_usd):
    """Apply the club's right to decline: `d_usd[t]` (undiscounted season
    surplus, aligned to `seasons`) is floored at 0 on every priced club option
    season. Returns `(d_usd_floored, declined_seasons)`; the input list is not
    mutated. A season with no price (None) is left alone."""
    out = list(d_usd)
    declined = []
    if not CLUB_OPTION_DECLINE:
        return out, declined
    for t, c in enumerate(seasons):
        if t >= len(out) or out[t] is None or c.get("usd") is None:
            continue
        if c.get("opt") == "club" and out[t] < 0:
            out[t] = 0.0
            declined.append(int(c["season"]))
    return out, declined


def payload_options(path: dict):
    """`salOpt`: [[season, "club"|"player"], ...] for the seasons inside the
    window that carry an option. STAMPED AND DISCLOSED, NOT PRICED (D10).

    WHAT WAS MEASURED, AND WHAT WAS NOT (disclosure repair, 2026-09-17). The
    first wording of this said "0 club options fall inside 2027-2031, so no
    declinable liability is over-priced today", which reads as a claim about
    the league and is a claim about a hand-curated file. data/contract_options
    .json holds SIX players and its own `_note` says it exists because player
    opt-outs and club options are NOT in Spotrac's `years_remaining`. Inside
    2027-2031 it lists 9 player-option seasons on 6 rows and no club option
    (the only club options in the file are Bobby Witt Jr 2035-2037). A club
    option Spotrac folded into `salary_by_year` is invisible here and is priced
    as guaranteed money by rule 1 unless the curated file names it (a named club
    option season the club would decline prices at zero since VAL2-Q2, see
    club_option_floor), because nothing in this tree inventories
    league-wide option years - that inventory is the blocking dependency on
    D10, and the curated row count ships beside the option census so a reader
    can see the coverage.

    The exposure the file DOES show runs the other way: those 9 player-option
    seasons assume the player never opts out. Pricing an opt-out needs an
    opt-out model with its own gate; until then the season says `player option`
    and the tooltip says the opt-out is not modelled.
    """
    out = [[c["season"], c["opt"]] for c in path["seasons"] if c.get("opt")]
    return out or None
