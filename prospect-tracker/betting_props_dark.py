"""Dark grading for the prop sub-models: HR and strikeouts, against base rates.

WHAT THIS DISCHARGES. Owner decision 8 says the prop market set may be extended only after
"the HR and strikeout sub-models have GRADED DARK against base rates". Nothing had. This is
that measurement, and it is the only kind available: ZERO prop odds have ever been captured.
All 22 snapshots in `.cache/odds` are `open` with markets h2h, spreads and totals; there is no
props snapshot file, no props spend ledger, and `EEPHUS_PROPS_CREDITS` is unset. So owner
decision 6's accuracy leg, which is defined against the market, is UNREACHABLE for every prop
market, and a dark grade against a base rate is what can honestly be done instead.

WHAT A DARK GRADE IS NOT. It is not a grade against a market, it cannot open a market, it may
not fill a slot, and nothing here moves a served number. A model that beats a league constant
has cleared the lowest bar there is; the market is a different and much harder opponent.

THE DESIGN, and every piece of it is a leak defence.

  WALK FORWARD BY DATE. For each distinct date in order: FIRST price every row on that date
  from accumulators holding only strictly earlier dates, THEN fold that date's rows in. The two
  operations are separate loops and the order is the whole defence. A single loop that folds
  before pricing lets a batter's home run predict itself.

  BURN-IN IS A FROZEN DATE, NOT A FRACTION. `BURN_IN_CUT_DATE` is a literal. It was chosen as
  the 30th percentile of the distinct dates at the time the design was fixed, but the completed
  games cache GROWS, so a fraction recomputed on each run would silently slide the cut and
  re-fit the constants on a different window every day. Rows before the cut train and are never
  graded.

  SHRINKAGE CONSTANTS ARE FITTED ON THE BURN-IN WINDOW ONLY and then frozen into this file. The
  sweep grid is published in the artifact so the choice is auditable and so its FLATNESS is
  visible: a constant chosen off a flat grid is not doing the work a reader might assume.

  THE BOOTSTRAP RESAMPLES GAMES, NOT ROWS. Batter-games inside one game share the park, the
  weather, the opposing pitcher and the umpire. An independent row bootstrap would understate
  the interval by roughly the square root of the rows per game, which is about five, and that is
  the difference between an interval that excludes zero and one that does not.

  THE HAND ARMS AND THE TOTAL-BASES LADDER (2026-09-11) were pre-registered in
  docs/diamond-betting.md section 5i-C before any of them was scored. They are
  ADDED arms in their own blocks; A0 to A3 and B0 to B2 are computed exactly as
  before. A hand arm must beat the arm it extends AND its swapped twin.

Offline. Reads `.cache/game_feeds/` and `betting_model.completed_games(refresh=False)`.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEEDS = ROOT / ".cache" / "game_feeds"
OUT = ROOT / "data" / "betting_props_dark_eval.json"

log = logging.getLogger("betting_props_dark")

#: FROZEN. The 30th percentile of the distinct completed-game dates at design
#: time. A literal, not a recomputed fraction: the completed-games cache grows
#: every day, so a fraction would slide the cut and refit the constants on a
#: different window on every run, which is a constant chosen by looking at
#: results.
BURN_IN_CUT_DATE = "2026-05-12"

#: The lines the module actually serves.
HR_LINE = 0.5
K_LINE = 5.5
#: Total bases posts at 1.5 (betting_export props_fair_lines prices that line).
TB_LINE = 1.5

#: Source reliability of the per-venue L minus R HR index split at Savant's
#: 3-season window, measured 2026-09-11 from Savant's single-season pages alone
#: (176 stable venue-season pairs, season-to-season r 0.1406, Spearman-Brown to
#: three seasons). The hand arms scale the hand deviation by it. PINNED equal to
#: betting_model.PARK_HAND_SPLIT_RELIABILITY["hr"] by test_betting_ballpark, and
#: fixed in docs/diamond-betting.md section 5i-C BEFORE any hand arm was scored.
HR_HAND_SPLIT_RELIABILITY = 0.3293

#: Prior strengths, FITTED ON THE BURN-IN WINDOW ONLY and frozen here. The sweep
#: that chose them is published in the artifact.
BATTER_PRIOR_PA = 200
PITCHER_PRIOR_BF = 300
BF_PRIOR_STARTS = 8

BOOT_N = 2000
BOOT_SEED = 20260906


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _feed(game_pk):
    p = FEEDS / f"{game_pk}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_tables(*, games=None) -> dict:
    """Per-batter-game and per-starter-game outcome rows from the cached feeds.

    Returns {"batters": [...], "starters": [...], "skipped": {...}}. A game with
    no feed is COUNTED and named, never silently dropped: a shortfall that
    correlates with anything (a date range, a club) would bias every downstream
    rate.
    """
    import betting_model as bm

    rows_b, rows_s = [], []
    skipped = {"no_feed": 0, "no_boxscore": 0, "game_pks_missing": []}
    gs = games if games is not None else bm.completed_games(refresh=False)
    for g in gs:
        pk = g.get("game_pk")
        date = g.get("date")
        d = _feed(pk)
        if d is None:
            skipped["no_feed"] += 1
            if len(skipped["game_pks_missing"]) < 25:
                skipped["game_pks_missing"].append(pk)
            continue
        teams = ((d.get("liveData") or {}).get("boxscore") or {}).get("teams") or {}
        if not teams:
            skipped["no_boxscore"] += 1
            continue
        gd_players = ((d.get("gameData") or {}).get("players")) or {}
        for side in ("home", "away"):
            t = teams.get(side) or {}
            org = g.get("home_org") if side == "home" else g.get("away_org")
            opp = g.get("away_org") if side == "home" else g.get("home_org")
            players = t.get("players") or {}
            # The opposing STARTER's hand, for a switch hitter's side (section
            # 5i-C). The first arm in the opposing boxscore is the starter; his
            # hand is a pregame fact once he is announced, and a realized
            # opener standing in for the probable is the one place this reads
            # the game rather than the preview, stated here rather than hidden.
            opp_t = teams.get("away" if side == "home" else "home") or {}
            opp_sp = (opp_t.get("pitchers") or [None])[0]
            opp_hand = _code(gd_players, opp_sp, "pitchHand")
            for pid in (t.get("batters") or []):
                pl = players.get(f"ID{pid}") or {}
                st = ((pl.get("stats") or {}).get("batting")) or {}
                pa = st.get("plateAppearances")
                if not pa:
                    continue
                hits = int(st.get("hits") or 0)
                d2, d3 = int(st.get("doubles") or 0), int(st.get("triples") or 0)
                hr = int(st.get("homeRuns") or 0)
                rows_b.append({
                    "game_pk": pk, "date": date, "player_id": int(pid),
                    "org": org, "opp": opp, "home_org": g.get("home_org"),
                    "pa": int(pa), "hr": hr,
                    # Schema of the total-bases ladder (section 5i-C): the
                    # three non-HR hit types, singles by subtraction.
                    "b1": max(hits - d2 - d3 - hr, 0), "b2": d2, "b3": d3,
                    "bat_side": effective_bat_side(
                        _code(gd_players, pid, "batSide"), opp_hand),
                })
            for pid in (t.get("pitchers") or []):
                pl = players.get(f"ID{pid}") or {}
                st = ((pl.get("stats") or {}).get("pitching")) or {}
                if not int(st.get("gamesStarted") or 0):
                    continue
                bf = st.get("battersFaced")
                if not bf:
                    continue
                rows_s.append({
                    "game_pk": pk, "date": date, "player_id": int(pid),
                    "org": org, "opp": opp, "home_org": g.get("home_org"),
                    "bf": int(bf), "k": int(st.get("strikeOuts") or 0),
                })
    return {"batters": rows_b, "starters": rows_s, "skipped": skipped,
            "n_games": len(gs)}


def _code(gd_players: dict, pid, key: str) -> str | None:
    """gameData.players[ID].<key>.code ("batSide" or "pitchHand"), or None."""
    if pid is None:
        return None
    rec = (gd_players or {}).get(f"ID{pid}") or {}
    c = ((rec.get(key) or {}).get("code")) if isinstance(rec, dict) else None
    return str(c).upper() if c else None


def effective_bat_side(bats: str | None, opp_hand: str | None) -> str | None:
    """The side a hitter bats from in this game: L or R as listed; a switch
    hitter turns around against the opposing starter's hand. None when the
    switch hitter's opponent hand is unknown or the listing is unreadable,
    never a default side: a guessed side would hand the hand arm a real-looking
    value exactly where it knows nothing."""
    b = str(bats or "").upper()[:1]
    if b in ("L", "R"):
        return b
    if b in ("S", "B") and opp_hand in ("L", "R"):
        return "L" if opp_hand == "R" else "R"
    return None


# ---------------------------------------------------------------------------
# Probability helpers
# ---------------------------------------------------------------------------

def p_at_least_one(rate: float, trials: int) -> float:
    """P(at least one success) under a binomial over `trials`."""
    rate = min(max(rate, 0.0), 1.0)
    return 1.0 - (1.0 - rate) ** max(int(trials), 0)


def p_over_binom(rate: float, trials: int, line: float) -> float:
    """P(count > line) under a binomial. `line` is a half-integer, so the
    comparison is unambiguous and no push is possible."""
    need = int(math.floor(line)) + 1
    n = max(int(trials), 0)
    rate = min(max(rate, 1e-9), 1 - 1e-9)
    if need > n:
        return 0.0
    tail = 0.0
    for k in range(need, n + 1):
        tail += math.comb(n, k) * rate ** k * (1 - rate) ** (n - k)
    return min(max(tail, 0.0), 1.0)


def p_over_poisson(lam: float, line: float) -> float:
    need = int(math.floor(line)) + 1
    lam = max(lam, 1e-9)
    # 1 - P(X <= need-1)
    cum, term = 0.0, math.exp(-lam)
    for k in range(0, need):
        if k:
            term *= lam / k
        cum += term
    return min(max(1.0 - cum, 0.0), 1.0)


def p_over_nb2(mean: float, alpha: float, line: float) -> float:
    """Negative binomial with variance mean + alpha * mean^2."""
    need = int(math.floor(line)) + 1
    mean = max(mean, 1e-9)
    if alpha <= 0:
        return p_over_poisson(mean, line)
    r = 1.0 / alpha
    p = r / (r + mean)
    cum, term = 0.0, p ** r
    for k in range(0, need):
        if k:
            term *= (r + k - 1) / k * (1 - p)
        cum += term
    return min(max(1.0 - cum, 0.0), 1.0)


# ---------------------------------------------------------------------------
# The walk-forward driver
# ---------------------------------------------------------------------------

def _walk_forward(rows, price_fn, *, trials_key, event_key):
    """Price every row from strictly-earlier state, then fold.

    `price_fn(state, row)` returns {arm: probability}. `state` is the mutable
    accumulator dict this function owns; the caller never sees a row before it
    has been priced.
    """
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    state = {
        "lg_num": 0, "lg_den": 0,
        "p_num": defaultdict(int), "p_den": defaultdict(int),
        "starts": defaultdict(int), "bf_sum": defaultdict(int),
        "lg_bf_sum": 0, "lg_starts": 0,
    }
    out = []
    for date in sorted(by_date):
        # 1. PRICE, from strictly-earlier state only.
        for r in by_date[date]:
            priced = price_fn(state, r)
            out.append({**r, "priced": priced})
        # 2. FOLD, only after every row on this date has been priced.
        for r in by_date[date]:
            pid = r["player_id"]
            state["lg_num"] += r[event_key]
            state["lg_den"] += r[trials_key]
            state["p_num"][pid] += r[event_key]
            state["p_den"][pid] += r[trials_key]
            state["starts"][pid] += 1
            state["bf_sum"][pid] += r[trials_key]
            state["lg_starts"] += 1
            state["lg_bf_sum"] += r[trials_key]
    return out


def _lg_rate(state):
    return (state["lg_num"] / state["lg_den"]) if state["lg_den"] else None


def _eb_rate(state, pid, prior):
    lg = _lg_rate(state)
    if lg is None:
        return None
    num = state["p_num"][pid] + lg * prior
    den = state["p_den"][pid] + prior
    return num / den if den else lg


def _park_hr_index(org, park_factors):
    """Park HR index, defaulting to neutral for an org the meta file omits.

    TAKES THE park_factors MAPPING ITSELF, not the whole fa_meta document. The
    first version took the outer document and was handed the inner mapping, so
    `.get("park_factors")` missed, every org defaulted to neutral, and the
    park arm came out BYTE-IDENTICAL to the arm it was supposed to extend. An
    arm that silently becomes a copy of its own baseline reports a perfect null
    and looks like a finding.

    `data/fa_meta.json` carries 29 orgs; ATH is absent and owns real home games
    in this window, so a KeyError would drop them and a zero would invert them.
    Neutral is the only safe default and it is stated rather than implied.
    """
    pf = (park_factors or {}).get(org) or {}
    try:
        return float(pf.get("hr", 100)) / 100.0
    except (TypeError, ValueError):
        return 1.0


def _park_hr_index_hand(org, side, by_hand, park_factors, *, swap: bool = False):
    """(index, resolved) for a batter-game: the park HR index for the side he
    bats from, its hand deviation scaled by HR_HAND_SPLIT_RELIABILITY
    (section 5i-C), on the scale _park_hr_index returns.

        all + rel * (hand - all)

    `by_hand` is fa_meta's `park_factors_by_hand` block ({"L": {org: row},
    "R": {org: row}}). `swap=True` reads the OPPOSITE hand's index, the twin
    that separates a hand-specific signal from a noisier copy of the same park.

    FALLS BACK TO THE ALL-HANDS INDEX, and says so in `resolved`, when the side
    or the by-hand row is missing, so an unresolved row prices exactly like A3
    rather than like a neutral park. A fallback that went neutral would move a
    Coors batter-game off its park and score that as a hand effect."""
    base = _park_hr_index(org, park_factors)
    if side not in ("L", "R") or not isinstance(by_hand, dict):
        return base, False
    use = ("R" if side == "L" else "L") if swap else side
    row = (by_hand.get(use) or {}).get(org) if isinstance(by_hand.get(use), dict) else None
    try:
        hand = float((row or {})["hr"]) / 100.0
    except (KeyError, TypeError, ValueError):
        return base, False
    return base + HR_HAND_SPLIT_RELIABILITY * (hand - base), True


def p_tb_over_1_5(p1: float, p0: float, trials: int) -> float:
    """P(total bases >= 2) over `trials` plate appearances, each PA yielding 0
    (prob p0), 1 (p1) or 2+ bases. Only two outcomes stay under the 1.5 line:
    no base at all, or exactly one single and nothing else, so the tail is exact

        1 - p0^n - n * p1 * p0^(n - 1)

    with no distributional assumption beyond independent PAs."""
    n = max(int(trials), 0)
    p0 = min(max(p0, 0.0), 1.0)
    p1 = min(max(p1, 0.0), 1.0 - p0)
    if n == 0:
        return 0.0
    return min(max(1.0 - p0 ** n - n * p1 * p0 ** (n - 1), 0.0), 1.0)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None


def _logscore(pairs):
    if not pairs:
        return None
    tot = 0.0
    for p, y in pairs:
        p = min(max(p, 1e-9), 1 - 1e-9)
        tot += math.log(p) if y else math.log(1 - p)
    return tot / len(pairs)


def _paired_delta_ci(np, rows, arm, comparator):
    """Paired Brier delta (arm minus comparator) with a GAME-clustered
    bootstrap. Negative favours the arm."""
    by_game = defaultdict(list)
    for r in rows:
        pa, pc = r["priced"].get(arm), r["priced"].get(comparator)
        if pa is None or pc is None:
            continue
        y = r["y"]
        by_game[r["game_pk"]].append((pa - y) ** 2 - (pc - y) ** 2)
    keys = list(by_game)
    if not keys:
        return None, None, None, 0
    flat = [d for k in keys for d in by_game[k]]
    point = sum(flat) / len(flat)
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, len(keys), size=(BOOT_N, len(keys)))
    draws = []
    cache = [by_game[k] for k in keys]
    for row in idx:
        s = n = 0.0
        for j in row:
            g = cache[j]
            s += sum(g)
            n += len(g)
        draws.append(s / n if n else float("nan"))
    arr = np.array([d for d in draws if d == d])
    return (point, float(np.percentile(arr, 2.5)),
            float(np.percentile(arr, 97.5)), len(flat))


def _arm_block(np, rows, arms, comparator):
    out = {}
    for arm in arms:
        pairs = [(r["priced"][arm], r["y"]) for r in rows
                 if r["priced"].get(arm) is not None]
        if not pairs:
            continue
        blk = {
            "n": len(pairs),
            "brier": round(_brier(pairs), 6),
            "log_score": round(_logscore(pairs), 6),
            "mean_predicted": round(sum(p for p, _ in pairs) / len(pairs), 6),
        }
        if arm != comparator:
            pt, lo, hi, n = _paired_delta_ci(np, rows, arm, comparator)
            clears = bool(pt is not None and hi is not None and hi < 0)
            blk.update({
                "paired_delta_vs_" + comparator: round(pt, 6) if pt is not None else None,
                "ci95": [round(lo, 6), round(hi, 6)] if lo is not None else None,
                "n_paired": n,
                "clears": clears,
                "verdict": (
                    "clears: the whole interval favours this arm"
                    if clears else
                    "does NOT clear: the interval contains zero, so on this "
                    "evidence the arm is not distinguishable from its comparator"
                    if pt is not None and lo is not None and lo <= 0 <= hi else
                    "does NOT clear: the interval lies on the WRONG side, so "
                    "this arm is measurably worse than its comparator"),
            })
        out[arm] = blk
    return out


# ---------------------------------------------------------------------------
# The HR ladder
# ---------------------------------------------------------------------------

def _hr_price(park_factors, by_hand=None):
    """Arms for one batter-game. All priced binomial over the SAME realized PA,
    so any difference between them is the RATE and never the trial count.

    A4 and its twin (section 5i-C, 2026-09-11) extend A3 by the batter's side.
    They are ADDED keys: A0 to A3 are computed exactly as before, and the
    artifact scores A4 in its own blocks, so no pre-existing number moves."""
    def price(state, r):
        lg = _lg_rate(state)
        if lg is None:
            return {}
        pa = r["pa"]
        # A0: the walk-forward league constant. The bar every arm must clear.
        a0 = p_at_least_one(lg, pa)
        # A1: the batter's own to-date rate, UNSHRUNK. Included because it is
        # the obvious thing to try and because it is expected to be WORSE than
        # knowing nothing: a batter with 12 plate appearances and one homer
        # reads as a 200-homer pace.
        own = (state["p_num"][r["player_id"]] / state["p_den"][r["player_id"]]
               if state["p_den"][r["player_id"]] else lg)
        a1 = p_at_least_one(own, pa)
        # A2 CHAMPION: empirical Bayes toward the league rate.
        eb = _eb_rate(state, r["player_id"], BATTER_PRIOR_PA)
        a2 = p_at_least_one(eb, pa)
        # A3: A2 times the park HR index of the ballpark actually played in.
        a3 = p_at_least_one(eb * _park_hr_index(r["home_org"], park_factors), pa)
        # A4: A3 with the park read for the side he bats from; A4_swap reads
        # the other side's index, the twin the gate requires.
        side = r.get("bat_side")
        h4, _ = _park_hr_index_hand(r["home_org"], side, by_hand, park_factors)
        hs, _ = _park_hr_index_hand(r["home_org"], side, by_hand, park_factors,
                                    swap=True)
        a4 = p_at_least_one(eb * h4, pa)
        a4s = p_at_least_one(eb * hs, pa)
        return {"A0_league": a0, "A1_unshrunk": a1, "A2_eb": a2, "A3_eb_park": a3,
                "A4_eb_park_hand": a4, "A4_swap": a4s}
    return price


# ---------------------------------------------------------------------------
# The total-bases ladder (section 5i-C, pre-registered 2026-09-11)
# ---------------------------------------------------------------------------
_TB_KEYS = ("b1", "b2", "b3", "hr")


def _walk_forward_tb(rows, price_fn):
    """_walk_forward for a four-component event: price every row on a date from
    strictly earlier state, THEN fold that date in. Same two-loop defence."""
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    state = {"lg": {k: 0 for k in _TB_KEYS}, "lg_pa": 0,
             "p": defaultdict(lambda: {k: 0 for k in _TB_KEYS}),
             "p_pa": defaultdict(int)}
    out = []
    for date in sorted(by_date):
        for r in by_date[date]:
            out.append({**r, "priced": price_fn(state, r)})
        for r in by_date[date]:
            pid = r["player_id"]
            state["lg_pa"] += r["pa"]
            state["p_pa"][pid] += r["pa"]
            for k in _TB_KEYS:
                state["lg"][k] += r[k]
                state["p"][pid][k] += r[k]
    return out


def _tb_rates(state, pid, prior):
    """Per-PA rates of single, double, triple, HR: the league's (prior None)
    or the batter's, each shrunk toward the league by `prior` PA. None before
    any league PA exists."""
    if not state["lg_pa"]:
        return None
    lg = {k: state["lg"][k] / state["lg_pa"] for k in _TB_KEYS}
    if prior is None:
        return lg
    den = state["p_pa"][pid] + prior
    return {k: (state["p"][pid][k] + lg[k] * prior) / den for k in _TB_KEYS}


def _tb_over(rates, pa, hr_mult=1.0):
    """P(TB > 1.5) at per-PA rates, the HR rate scaled by `hr_mult` (the park),
    the extra HR mass taken from the zero-base outcome so the four rates and
    p0 still sum to one."""
    p4 = rates["hr"] * hr_mult
    p0 = 1.0 - rates["b1"] - rates["b2"] - rates["b3"] - p4
    return p_tb_over_1_5(rates["b1"], max(p0, 0.0), pa)


def _tb_price(park_factors, by_hand=None):
    """Arms for one batter-game on the TB 1.5 line, all over the SAME realized PA.

    C0 league per-PA mix; C2 the batter's mix, each component shrunk toward the
    league by BATTER_PRIOR_PA (the HR ladder's frozen constant, reused and not
    re-fitted); C3 C2 with the all-hands park HR index on the HR rate; C4 C3 with
    the hand-read index; C4_swap the opposite hand's index."""
    def price(state, r):
        lg = _tb_rates(state, r["player_id"], None)
        if lg is None:
            return {}
        pa = r["pa"]
        eb = _tb_rates(state, r["player_id"], BATTER_PRIOR_PA)
        pk = _park_hr_index(r["home_org"], park_factors)
        side = r.get("bat_side")
        h4, _ = _park_hr_index_hand(r["home_org"], side, by_hand, park_factors)
        hs, _ = _park_hr_index_hand(r["home_org"], side, by_hand, park_factors,
                                    swap=True)
        return {"C0_league": _tb_over(lg, pa), "C2_eb": _tb_over(eb, pa),
                "C3_eb_park": _tb_over(eb, pa, pk),
                "C4_eb_park_hand": _tb_over(eb, pa, h4),
                "C4_swap": _tb_over(eb, pa, hs)}
    return price


def _hand_coverage(rows, by_hand, park_factors) -> dict:
    """How many batter-games the hand arms actually read a hand for. A COVERAGE
    count, not a measurement: it says the arm has rows to differ on, the way
    section 5c reported its 540 order slots."""
    n_side = sum(1 for r in rows if r.get("bat_side") in ("L", "R"))
    n_res = sum(1 for r in rows
                if _park_hr_index_hand(r["home_org"], r.get("bat_side"), by_hand,
                                       park_factors)[1])
    return {"batter_games": len(rows), "with_bat_side": n_side,
            "with_hand_index": n_res,
            "fallback_to_all_hands": len(rows) - n_res,
            "note": ("a row without a side or a by-hand index prices exactly like "
                     "the all-hands arm, so the hand legs' effective n is "
                     "with_hand_index, not batter_games")}


def _hand_legs(np, ev, by_hand, parks, base_arm, hand_arm, twin_arm) -> dict:
    """The two section 5i-C legs plus their coverage, or a stated absence.

    WITH NO ROW READING A HAND THE LEGS ARE NOT SCORED. Every hand arm then
    equals the arm it extends to the last bit, and _arm_block would publish a
    zero delta with a zero-width interval: the arm-that-becomes-its-own-baseline
    defect this module's docstring names, reporting a perfect null that looks
    like a finding. So the legs are None and the reason says why, and the first
    admissible look is the first run where `with_hand_index` is positive."""
    cov = _hand_coverage(ev, by_hand, parks)
    if not cov["with_hand_index"]:
        why = ("NOT SCORED: no batter-game read a by-hand park index (fa_meta.json "
               "carries no park_factors_by_hand block, or no row resolved a side), "
               "so every hand arm equals the arm it extends; a zero delta here would "
               "be an artifact, not a result")
        return {"hand_leg": None, "hand_twin_leg": None, "hand_coverage": cov,
                "hand_absent_reason": why}
    return {"hand_leg": _arm_block(np, ev, [base_arm, hand_arm], base_arm),
            "hand_twin_leg": _arm_block(np, ev, [twin_arm, hand_arm], twin_arm),
            "hand_coverage": cov}


def _k_price(alpha):
    """Arms for one starter-game, plus the PMF sub-arms at the champion's mean.

    TWO LEGS, REPORTED SEPARATELY. The SHAPE leg asks which distribution fits
    the strikeout count; the LINE leg asks which prices P(K > 5.5) better. They
    can disagree, and collapsing them is how a shipped reason string ends up
    describing the wrong thing.
    """
    def price(state, r):
        lg = _lg_rate(state)
        if lg is None:
            return {}
        pid = r["player_id"]
        bf_real = r["bf"]
        lg_bf = (state["lg_bf_sum"] / state["lg_starts"]) if state["lg_starts"] else bf_real
        # B0: league K/BF over an EXPECTED batters-faced, not the realized one.
        # A baseline that is handed the realized workload is not a baseline.
        b0 = p_over_binom(lg, int(round(lg_bf)), K_LINE)
        own = (state["p_num"][pid] / state["p_den"][pid]
               if state["p_den"][pid] else lg)
        b1 = p_over_binom(own, int(round(lg_bf)), K_LINE)
        eb = _eb_rate(state, pid, PITCHER_PRIOR_BF)
        # Expected batters faced, empirical Bayes toward the league mean.
        s, bfs = state["starts"][pid], state["bf_sum"][pid]
        eb_bf = ((bfs + lg_bf * BF_PRIOR_STARTS) / (s + BF_PRIOR_STARTS)
                 if (s + BF_PRIOR_STARTS) else lg_bf)
        n_bf = max(int(round(eb_bf)), 1)
        b2 = p_over_binom(eb, n_bf, K_LINE)
        mean_k = eb * eb_bf
        return {
            "B0_league": b0, "B1_unshrunk": b1, "B2_eb": b2,
            "B2_binom": b2,
            "B2_poisson": p_over_poisson(mean_k, K_LINE),
            "B2_nb2": p_over_nb2(mean_k, alpha, K_LINE),
        }
    return price


def _fit_nb2_alpha(rows, cut):
    """One dispersion parameter, fitted on the BURN-IN window only.

    Method of moments on the residual of strikeouts about the walk-forward mean,
    which is enough for a shape comparison and does not need an optimiser whose
    convergence would be another thing to check.
    """
    burn = [r for r in rows if r["date"] < cut and r["priced"]]
    if len(burn) < 100:
        return 0.0
    mean = sum(r["k"] for r in burn) / len(burn)
    var = sum((r["k"] - mean) ** 2 for r in burn) / max(len(burn) - 1, 1)
    if mean <= 0 or var <= mean:
        return 0.0
    return (var - mean) / (mean ** 2)


def _sweep(rows, cut, price_factory, arms, key_event, key_trials, grid, label):
    """Fit a prior strength on the BURN-IN window only, and publish the grid.

    The grid is published because its FLATNESS is the thing a reader needs: a
    constant chosen off a flat grid is not doing the work the word 'fitted'
    implies.
    """
    out = []
    for k in grid:
        priced = _walk_forward(rows, price_factory(k),
                               trials_key=key_trials, event_key=key_event)
        burn = [r for r in priced if r["date"] < cut and r["priced"]]
        for r in burn:
            r["y"] = 1 if r[key_event] > (HR_LINE if key_event == "hr" else K_LINE) else 0
        pairs = [(r["priced"][arms], r["y"]) for r in burn
                 if r["priced"].get(arms) is not None]
        out.append({"prior": k, "n_burn_in": len(pairs),
                    "brier": round(_brier(pairs), 6) if pairs else None})
    best = min((o for o in out if o["brier"] is not None),
               key=lambda o: o["brier"], default=None)
    return {"label": label, "grid": out,
            "chosen": best["prior"] if best else None,
            "flatness_note": (
                "the spread across this grid is the honest measure of how much "
                "the fitted constant matters. A flat grid means the choice is "
                "close to arbitrary and the arm's result does not rest on it."),
            "spread": (round(max(o["brier"] for o in out if o["brier"] is not None)
                             - min(o["brier"] for o in out if o["brier"] is not None), 6)
                       if any(o["brier"] is not None for o in out) else None)}


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

def run(*, write: bool = True) -> dict:
    import numpy as np

    tables = build_tables()
    meta = {}
    p_meta = ROOT / "data" / "fa_meta.json"
    if p_meta.exists():
        try:
            meta = json.loads(p_meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    parks = (meta.get("park_factors") or {})
    # The by-hand sibling (section 5i-C). Absent on an fa_meta written before
    # it existed, in which case every hand arm prices exactly like its
    # all-hands arm and the coverage block says so.
    by_hand = meta.get("park_factors_by_hand")
    by_hand = by_hand if isinstance(by_hand, dict) else None

    cut = BURN_IN_CUT_DATE
    art = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "betting_props_dark.py",
        "burn_in_cut_date": cut,
        "lines": {"home_runs": HR_LINE, "strikeouts": K_LINE},
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "resampling_unit": "game_pk",
                      "why": ("batter-games inside one game share the park, the "
                              "weather, the opposing pitcher and the umpire; an "
                              "independent row bootstrap understates the interval "
                              "by roughly the square root of the rows per game")},
        "coverage": {
            "completed_games": tables["n_games"],
            "skipped": tables["skipped"],
            "batter_games": len(tables["batters"]),
            "starter_games": len(tables["starters"]),
            "park_factor_orgs": len(parks),
            "park_by_hand_orgs": ({s: len(by_hand.get(s) or {}) for s in ("L", "R")}
                                  if by_hand else None),
            "park_factor_default": (
                "orgs absent from data/fa_meta.json price at a NEUTRAL 100 index. "
                "ATH is absent and owns real home games in this window; a KeyError "
                "would drop them and a zero would invert them."),
        },
        "what_this_is_not": (
            "NOT a grade against a market. Zero prop odds have ever been "
            "captured: all 22 snapshots in .cache/odds are kind 'open' with "
            "markets h2h, spreads and totals, no props snapshot exists, and "
            "EEPHUS_PROPS_CREDITS is unset. Owner decision 6's accuracy leg is "
            "defined against the market and is therefore UNREACHABLE for every "
            "prop market. Beating a league constant is the lowest bar there is "
            "and clears nothing for publication: no slot, no record row, no "
            "exported edge, no served number."),
    }

    # ---- HR ----------------------------------------------------------------
    hr_rows = tables["batters"]
    art["home_runs"] = {}
    if hr_rows:
        sweep = _sweep(hr_rows, cut,
                       lambda k: _hr_price_with_prior(parks, k),
                       "A2_eb", "hr", "pa", [50, 100, 200, 400],
                       "batter prior strength, in plate appearances")
        priced = _walk_forward(hr_rows, _hr_price(parks, by_hand),
                               trials_key="pa", event_key="hr")
        for r in priced:
            r["y"] = 1 if r["hr"] > HR_LINE else 0
        ev = [r for r in priced if r["date"] >= cut and r["priced"]]
        art["home_runs"] = {
            "n_eval": len(ev),
            "n_burn_in": sum(1 for r in priced if r["date"] < cut),
            "base_rate": round(sum(r["y"] for r in ev) / len(ev), 6) if ev else None,
            "frozen_constants": {"batter_prior_pa": BATTER_PRIOR_PA},
            "burn_in_sweep": sweep,
            "comparator": "A0_league",
            "arms": _arm_block(np, ev, ["A0_league", "A1_unshrunk", "A2_eb",
                                        "A3_eb_park"], "A0_league"),
            # THE STRUCTURE LEG, asked directly. Every arm above is scored
            # against the league constant, which answers "is this better than
            # knowing nothing". That is the wrong question for the park index:
            # what a reader wants to know is whether the park buys anything ON
            # TOP OF the batter rate, and only A3 against A2 answers it.
            "structure_leg": _arm_block(np, ev, ["A2_eb", "A3_eb_park"], "A2_eb"),
            "structure_leg_note": (
                "the park index scored against the batter rate it extends, not "
                "against the league constant. An arm can clear the league bar "
                "purely on the strength of the component it inherits, so a park "
                "arm that clears A0 says nothing about the park."),
            # SECTION 5i-C, pre-registered 2026-09-11 before any of these was
            # computed. Both legs are required and neither is summarized into
            # the other: the hand arm against the arm it extends, and against
            # its own swapped twin.
            **_hand_legs(np, ev, by_hand, parks, "A3_eb_park",
                         "A4_eb_park_hand", "A4_swap"),
            "hand_note": (
                "A4 reads the park HR index for the side the batter hits from, "
                "its deviation from the all-hands index scaled by the measured "
                "source reliability of the split (HR_HAND_SPLIT_RELIABILITY). "
                "It must beat A3 AND its swapped twin; beating A3 alone could be "
                "a noisier copy of the same park. docs/diamond-betting.md 5i-C"),
        }

    # ---- strikeouts --------------------------------------------------------
    k_rows = tables["starters"]
    art["strikeouts"] = {}
    if k_rows:
        pre = _walk_forward(k_rows, _k_price(0.0), trials_key="bf", event_key="k")
        alpha = _fit_nb2_alpha(pre, cut)
        priced = _walk_forward(k_rows, _k_price(alpha),
                               trials_key="bf", event_key="k")
        for r in priced:
            r["y"] = 1 if r["k"] > K_LINE else 0
        ev = [r for r in priced if r["date"] >= cut and r["priced"]]
        art["strikeouts"] = {
            "n_eval": len(ev),
            "n_burn_in": sum(1 for r in priced if r["date"] < cut),
            "base_rate": round(sum(r["y"] for r in ev) / len(ev), 6) if ev else None,
            "frozen_constants": {"pitcher_prior_bf": PITCHER_PRIOR_BF,
                                 "bf_prior_starts": BF_PRIOR_STARTS,
                                 "nb2_alpha_fitted_on_burn_in": round(alpha, 6)},
            "comparator": "B0_league",
            "arms": _arm_block(np, ev, ["B0_league", "B1_unshrunk", "B2_eb"],
                               "B0_league"),
            "pmf_line_leg": _arm_block(np, ev, ["B2_binom", "B2_poisson",
                                                "B2_nb2"], "B2_binom"),
            "pmf_leg_note": (
                "the LINE leg only: which distribution prices P(K > 5.5) better "
                "at the champion's mean. It is not a verdict on which "
                "distribution FITS the strikeout count, which is a different "
                "question with a different answer, and collapsing the two is "
                "how a shipped reason string ends up describing the wrong "
                "thing."),
        }

    # ---- total bases (section 5i-C, pre-registered 2026-09-11) ------------
    art["total_bases"] = {}
    if hr_rows:
        priced = _walk_forward_tb(hr_rows, _tb_price(parks, by_hand))
        for r in priced:
            r["y"] = 1 if (r["b1"] + 2 * r["b2"] + 3 * r["b3"] + 4 * r["hr"]) > TB_LINE else 0
        ev = [r for r in priced if r["date"] >= cut and r["priced"]]
        art["total_bases"] = {
            "n_eval": len(ev),
            "n_burn_in": sum(1 for r in priced if r["date"] < cut),
            "base_rate": round(sum(r["y"] for r in ev) / len(ev), 6) if ev else None,
            "line": TB_LINE,
            "frozen_constants": {"batter_prior_pa": BATTER_PRIOR_PA,
                                 "hr_hand_split_reliability": HR_HAND_SPLIT_RELIABILITY},
            "comparator": "C0_league",
            "arms": _arm_block(np, ev, ["C0_league", "C2_eb", "C3_eb_park"],
                               "C0_league"),
            "structure_leg": _arm_block(np, ev, ["C2_eb", "C3_eb_park"], "C2_eb"),
            **_hand_legs(np, ev, by_hand, parks, "C3_eb_park",
                         "C4_eb_park_hand", "C4_swap"),
            "method_note": (
                "P(TB > 1.5) is exact under independent plate appearances: only "
                "no base at all or exactly one single stays under the line. Rates "
                "per PA for single, double, triple and HR, each shrunk toward the "
                "league by the HR ladder's frozen batter prior; the park scales "
                "the HR rate only and takes the added mass from the zero-base "
                "outcome."),
        }
    if write:
        OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
    return art


def _hr_price_with_prior(parks, prior):
    def price(state, r):
        lg = _lg_rate(state)
        if lg is None:
            return {}
        num = state["p_num"][r["player_id"]] + lg * prior
        den = state["p_den"][r["player_id"]] + prior
        eb = num / den if den else lg
        return {"A2_eb": p_at_least_one(eb, r["pa"])}
    return price


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    a = run(write="--dry-run" not in argv)
    c = a["coverage"]
    print(f"games {c['completed_games']}, batter-games {c['batter_games']:,}, "
          f"starter-games {c['starter_games']:,}, skipped {c['skipped']['no_feed']}")
    for mkt in ("home_runs", "strikeouts", "total_bases"):
        b = a.get(mkt) or {}
        if not b:
            continue
        print(f"\n=== {mkt}  n_eval {b['n_eval']:,}  base rate {b['base_rate']}")
        for arm, v in (b.get("arms") or {}).items():
            d = v.get("paired_delta_vs_" + b["comparator"])
            ci = v.get("ci95")
            extra = (f"  delta {d:+.6f} CI [{ci[0]:+.6f}, {ci[1]:+.6f}] "
                     f"clears={v.get('clears')}" if d is not None else "  (comparator)")
            print(f"   {arm:14s} brier {v['brier']:.6f}{extra}")
        for leg in ("structure_leg", "hand_leg", "hand_twin_leg"):
            for arm, v in (b.get(leg) or {}).items():
                d = next((v[k] for k in v if k.startswith("paired_delta_vs_")), None)
                ci = v.get("ci95")
                if d is None or ci is None:
                    continue
                print(f"   {leg} {arm:16s} delta {d:+.6f} "
                      f"CI [{ci[0]:+.6f}, {ci[1]:+.6f}] clears={v.get('clears')}")
        for arm, v in (b.get("pmf_line_leg") or {}).items():
            d = v.get("paired_delta_vs_B2_binom")
            ci = v.get("ci95")
            extra = (f"  delta {d:+.6f} CI [{ci[0]:+.6f}, {ci[1]:+.6f}] "
                     f"clears={v.get('clears')}" if d is not None else "  (comparator)")
            print(f"   pmf {arm:12s} brier {v['brier']:.6f}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
