# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v2 - "eephus WAR" -> data/ewar.json + data/ewar_eval.json.

WHY THIS EXISTS
    The site currently serves Baseball-Reference bWAR. The owner asked for
    something better: FIP-based pitching and a real defensive metric. fWAR is
    not obtainable from this machine (FanGraphs is Cloudflare-403; see
    docs/efv-2026-07-30/DEFENSIVE_SOURCE_PROBE.md and the note in stats.py
    around fetch_career_war_bulk), so this module BUILDS the better WAR out of
    inputs already on disk instead of importing one.

    SERVED SINCE THE 2026-09-03 EPOCH: war_source.DEFAULT_PROVIDER is ewar_v2, so
    the career_war funnel, MLB player cards, the WAR-rate boards, PAL, the arb
    spine and the FA corpus labels read this series (eFV labels, anchors, surplus
    and projections follow at the label epoch, docs/efv-2026-09-03/). That is an
    OWNER BASIS DECISION, not an accuracy claim: the gate record below is
    unchanged and R3a/R3b remain the accuracy statement.

    THE OWNER'S HYPOTHESIS WAS "a better WAR label makes eFV more accurate."
    Both consumer gates have now been run and neither supports a swap.

    R3a, eFV first-6yr label swap (2026-08-04). Decision quantity is the
    model-versus-consensus MARGIN with BOTH scored on the SAME labels, because
    swapping the label changes what "right" means and absolute rho is therefore
    uninterpretable. DELTA = -0.0011 (hit) and -0.0115 (pit), both NEGATIVE,
    against MDE floors of 0.017 and 0.016. Coverage was not the obstacle: 98.6%
    of hit and 99.1% of pit test-fold rows carry an eWAR label, because the
    scored folds are debut years 2020-2023 and eWAR starts in 2016.
    IMPORTANT, and the reason this is a NO-SHIP rather than a CLOSED question:
    the null is NOT tight enough to exclude a floor-sized effect on the pitching
    side. The lane's own bootstrap held both fitted models FIXED, but the eWAR
    arm refits ridge and OLS on the new label, so model-estimation variance
    belongs in the sampling distribution. Adding it moves pit sd 0.0164 ->
    0.0210 and the CI90 upper bound to +0.0206, which is ABOVE the 0.016 floor;
    the original single-seed CI90 upper of +0.0147 also sits within Monte Carlo
    error of the floor, and 10 of 40 reseeds put it at or above. So: no evidence
    of benefit, do NOT flip, and do not write down that the hypothesis is
    closed. It is unsupported, which is a weaker and more honest claim.

    HIGHER-POWERED RE-TEST, pitching only, owner-authorised and run 2026-08-04.
    It did NOT close the question, and it weakened the headline rather than the
    reverse. Pre-registered design: add the 2019 fold (test n=71, train n=80),
    taking the scored population from 434 to 505 rows, and raise the full-refit
    paired bootstrap from B=400 to B=2000. 2024 was deliberately NOT added
    despite being the larger fold, because a 2024 debut has only 2 of its 6
    label seasons resolved against 6 for 2019.
      * The base 4-fold arm REPRODUCES exactly, DELTA -0.0115.
      * On 5 folds DELTA is -0.0001. The "moved the wrong way on pitchers"
        reading is FOLD-DEPENDENT and should not be quoted as though it were
        stable.
      * sd went 0.0210 -> 0.02393, WIDER. The pre-registered prediction was
        that +16% n would shrink it about 7%; that was wrong because it treated
        all rows as equally informative. The 2019 fold trains on 80 rows
        against 151+ for the folds it joins, so it carries more noise than
        information and the pooled margin over consensus falls from +0.0286 to
        +0.0104 on the bWAR label too.
      * CI90 [-0.0469, +0.0311]. The upper bound is still well above the 0.016
        floor, so a floor-sized effect remains UNEXCLUDED.
    CONSEQUENCE FOR ANY FUTURE ATTEMPT: this cohort cannot be re-sliced into
    enough power. The only fold that would add clean information is one whose
    six label seasons are fully resolved, which means WAITING for debut years to
    mature, not re-partitioning what is already here.

    R3b, fa_backtest Gate 1 (2026-08-04). Margin over the Marcel carry-forward
    baseline, both scored on the same labels: -0.0387 WAR on pitchers against a
    pre-registered floor of +0.020, CI95 [-0.0472, -0.0309], negative in all six
    scored targets. THE MECHANISM IS THE INTERESTING PART and it generalises:
    the eWAR pitching label really IS more forecastable (label r 0.5033 ->
    0.5779, persistence 0.4528 -> 0.5823), but a 5/4/3 carry-forward IS a
    persistence bet, so a more persistent label helps the NAIVE BASELINE more
    than it helps the model. A cleaner label raises the floor before it raises
    the ceiling. Expect this anywhere a model is scored as margin-over-carry.

THE FRAME
    eWAR stays on the Baseball-Reference run-value frame. v1 replaced two
    components; v2 replaces exactly ONE. Everything else - offense,
    baserunning, double plays, the positional adjustment, replacement level,
    reliever leverage - is B-Ref's, untouched, so the accounting identity stays
    closed and the difference between eWAR and bWAR is attributable to the
    pitching swap and nothing else.

        eWAR(row) = bWAR(row) + delta_pitch(row)/RPW        (v2, shipped)
        eWAR(row) = bWAR(row) + delta_pitch/RPW + delta_field/RPW   (v1)

    THE FIELDING SWAP WAS MEASURED AND REMOVED on 2026-08-04. The blend weight
    `fielding_blend_w` defaults to 0.0, which makes delta_field identically
    zero. The machinery below is retained because it is the axis the decision
    was swept on, not because any of it is live. See the w grid in
    _reading().what_would_change_the_verdict.

    RELIEVER LEVERAGE, precisely, because "untouched" is doing real work in
    that sentence. B-Ref's reliever leverage chaining lives in war_daily's
    WAA_adj term, and the identity WAR = WAA + WAA_adj + WAR_rep holds to a
    residual sd of 0.0029. build() ingests WAR whole and never decomposes it,
    so the FIP swap re-prices runs WITHOUT disturbing the leverage credit.
    Verified 2026-08-04 (lane R2e.3), and the alternative was killed on the
    same pass: our own gmLI (mlb_leverage) and B-Ref's are the same number,
    r = 0.9947 on 993 reliever-seasons. Do not re-propose crediting relievers
    with our gmLI; it is a measured null, not an untried idea.

    1. PITCHING: B-Ref prices a pitcher on RUNS ALLOWED (runs_above_avg_adj =
       xRA_final - RA, league-centred). eWAR re-prices him on FIP - his own
       K / BB / HBP / HR over his own innings - using the SAME FIP constant
       construction fa_projection.build_corpus already ships (fa_projection.py
       ~line 297: fip_const = lgERA - lgFIPcore, so lgFIP == lgERA by
       construction). FIP is on an ERA scale, so it is carried to the RA9 scale
       the B-Ref frame prices in by lgRA9/lgERA, park-adjusted with the row's
       own PPF, and RE-CENTRED per (season, role) so the SP total and the RP
       total match B-Ref's exactly. Centring per role is deliberate: B-Ref's
       xRA_sprp_adj already prices the starter/reliever role difference, and
       eWAR keeps that judgement rather than re-litigating it on a FIP basis.
       So the pitching swap is a pure WITHIN-ROLE redistribution.

    2. FIELDING: B-Ref's rfield is its weakest component. Where Statcast covers
       the player-position-season (data/savant_oaa.json, 2016+, seven positions,
       no catchers), eWAR uses Savant FRP instead, centred within
       (season, position) - Savant does NOT centre the outfield rungs against
       each other, so raw FRP would double-count B-Ref's runs_position - and
       shrunk toward the position average by playing time using the per-position
       reliability constants k_inn already fitted in data/positional_fit.json
       (fit.signal.*.k_inn, reliability = inn / (inn + k_inn)).
       Anything Statcast does not cover - every season before 2016, every
       CATCHER, every pitcher's own glove, and any position-season with no
       innings on record - falls back to B-Ref rfield, pro-rated by the
       uncovered innings share. The coverage split is reported per season and
       per position in the eval artifact.

    3. REPLACEMENT LEVEL is re-derived per season so the league total lands
       where the platform says it must: REPLACEMENT_WINS 47.7 on a .294
       baseline (rate_stabilization.py), i.e. league eWAR = (0.5 - 47.7/162) x
       total team-games, which is 999.0 for a 30 x 162 season and scales for
       1994/2020-style short ones. The correction is applied proportionally to
       each row's own replacement component, so it is a level move and not a
       re-ranking. A WAR that does not sum to the league's wins above
       replacement is not a WAR.

INPUTS (all on disk; the only network call is pybaseball's cached static CSVs)
    pybaseball.bwar_bat / bwar_pitch  the B-Ref war_daily frames, full run
                                      decomposition, same pull stats.py uses
    .cache/fa_corpus.pkl              per player-season FIP + the per-season
                                      league means/FIP constant (fa_projection)
    data/savant_oaa.json              13,001 player-position-seasons of OAA/FRP
    data/fielding_innings.json        defensive innings by player-position-season
    data/positional_fit.json          fit.signal.<pos>.k_inn reliability constants
    .cache/statsapi_standings_*.json  actual team wins, for the validity gate

PUBLIC API
    build(...)          -> the full model (rows + per-season meta)
    export_payload(...) -> the serialisable data/ewar.json shape
    load()              -> read data/ewar.json
    ewar_for(mlbam, season) -> per (player, season) eWAR + its components.
                               THIS is the call a future D0 facade makes.
    evaluate(...)       -> the three validity gates -> data/ewar_eval.json

Run: python tools/build_ewar.py --write
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import pickle
import time
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
OUT = DATA_DIR / "ewar.json"
EVAL_OUT = DATA_DIR / "ewar_eval.json"

MODEL = "ewar_v2"

# Statcast OAA covers these seven. C returns zero rows from the leaderboard
# (savant_oaa.json "blind_spots"), DH has no defense, P is not on the board.
OAA_POSITIONS = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")
FIRST_OAA_SEASON = 2016
DEFAULT_FIRST_SEASON = 2016     # the OAA era; earlier seasons build but are all-fallback

# Replacement-wins convention. Imported rather than re-typed: rate_stabilization
# is the platform's one home for it (REPLACEMENT_WINS 47.7 on a .294 baseline),
# and it imports nothing from the project so this stays cheap.
try:
    from rate_stabilization import REPLACEMENT_WINS
except ImportError:                                  # pragma: no cover - defensive
    REPLACEMENT_WINS = 47.7
FULL_SEASON_GAMES = 162

# Runs-per-win guards. B-Ref's own implied RPW (runs_above_avg / WAA) sits at
# 8.0-11.2 per team-season across 2016-2025; anything outside this band is an
# estimation artifact of a near-zero WAA denominator, not a run environment.
RPW_MIN, RPW_MAX = 7.0, 13.0
RPW_FALLBACK = 9.7
RPW_MIN_WAA = 0.3        # rows below this |WAA| are rounding noise in the ratio

# A (season, role) FIP centring cell needs this many covered rows to be solved;
# below it every row in the cell falls back to B-Ref's own pricing.
MIN_ROLE_CELL_ROWS = 20

BWAR_CACHE_TTL_S = 7 * 86400     # the war_daily CSVs are static; refresh weekly

# StatsAPI club name -> Baseball-Reference team_ID (war_daily uses the modern
# abbreviations). 'Indians'/'Guardians' and 'OAK'/'ATH' are the only two
# renames inside the 2016-2026 window.
_CLUB_TO_BREF = {
    "Angels": "LAA", "Astros": "HOU", "Athletics": "OAK", "Blue Jays": "TOR",
    "Braves": "ATL", "Brewers": "MIL", "Cardinals": "STL", "Cubs": "CHC",
    "D-backs": "ARI", "Diamondbacks": "ARI", "Dodgers": "LAD", "Giants": "SFG",
    "Guardians": "CLE", "Indians": "CLE", "Mariners": "SEA", "Marlins": "MIA",
    "Mets": "NYM", "Nationals": "WSN", "Orioles": "BAL", "Padres": "SDP",
    "Phillies": "PHI", "Pirates": "PIT", "Rangers": "TEX", "Rays": "TBR",
    "Red Sox": "BOS", "Reds": "CIN", "Rockies": "COL", "Royals": "KCR",
    "Tigers": "DET", "Twins": "MIN", "White Sox": "CHW", "Yankees": "NYY",
}
# war_daily switched the Athletics' code with the 2025 relocation; the standings
# club name did not change. Fold to one franchise key for the team roll-up.
_TEAM_ID_FOLD = {"ATH": "OAK"}


# ============================================================ input loading
def _load_json(name: str) -> dict:
    p = DATA_DIR / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ewar: cannot read data/{name} ({exc}). "
                         f"Run the ingest that produces it first.")


def shrinkage_constants() -> dict[str, float]:
    """{pos: k_inn} - the per-position reliability constants positional_fit.py
    fitted from year-over-year persistence at matched exposure. Reliability of a
    single-season read is inn / (inn + k_inn); at 1B (k=2539) a full season of
    1200 innings is only 32% signal, at CF (k=632) it is 66%."""
    fit = _load_json("positional_fit.json").get("fit", {}).get("signal", {})
    out = {}
    for p in OAA_POSITIONS:
        k = (fit.get(p) or {}).get("k_inn")
        if k is None or float(k) <= 0:
            raise SystemExit(f"ewar: positional_fit.json has no k_inn for {p}; "
                             f"re-run positional_fit.py before building eWAR.")
        out[p] = float(k)
    return out


def _corpus() -> dict:
    """fa_projection's season corpus: per player-season FIP on the shipped
    constant, plus the per-season league means. Read from the pickle it already
    writes so a build never triggers a network rebuild; only if the pickle is
    missing do we import fa_projection and let it build one."""
    pkl = CACHE_DIR / "fa_corpus.pkl"
    if pkl.exists():
        with open(pkl, "rb") as fh:
            return pickle.load(fh)
    log.warning("ewar: .cache/fa_corpus.pkl missing - building it via fa_projection")
    import fa_projection as fp          # noqa: PLC0415 - lazy, network-touching
    return fp.build_corpus()


def corpus_fip(hr_shrink_k: float | None = None) -> tuple[dict, dict]:
    """({(mlbam, season): fip}, {season: league_block}).

    The FIP is fa_projection's, verbatim: (13HR + 3(BB+HBP) - 2K)/IP plus the
    season's fitted FIP constant, which is defined so league FIP == league ERA.
    Re-deriving it here would be a second convention; the platform has one.

    hr_shrink_k turns on the HOME-RUN REGRESSION VARIANT (default off, so the
    shipped map is untouched). HR is the noisiest of FIP's three inputs, and the
    standard fix is xFIP: replace a pitcher's actual home runs with his fly balls
    times the league home-run-per-fly-ball rate. THAT IS NOT COMPUTABLE HERE -
    the projection corpus carries k_pct, bb_pct, hr_bf, bf, ip and no batted-ball
    profile at all, so there is no fly-ball denominator. Rather than fake one,
    this variant regresses the HR RATE itself toward the season's league rate by
    exposure, hr' = (hr_bf*bf + lg_hr_bf*k) / (bf + k), which tests the same
    hypothesis (a pitcher's home-run total is largely noise, so damping it should
    improve year-to-year persistence) without inventing a batted-ball input.
    It is deliberately NOT called xFIP anywhere, because it is not xFIP.

    The adjustment is applied as a DELTA to the existing FIP rather than by
    recomputing it: FIP is linear in home runs, so dFIP = 13*(HR' - HR)/IP is
    exact, and this keeps the platform's single FIP-constant convention intact
    (see the warning above - re-deriving it here is precisely what must not
    happen).

    MEASURED at k=400 over the 19,324-row corpus, so neither of these is a
    surprise at gate time:
      * DIRECTION IS RIGHT. The three highest home-run rates move -1.14, -0.93
        and -0.67 FIP; the three lowest move +0.53, +0.57 and +0.30.
      * THE LEAGUE LEVEL MOVES, 4.997 -> 4.734. Shrinking is mean-preserving in
        the RATE but not in the FIP delta, because dFIP carries a bf/IP factor
        that varies by pitcher. This is HARMLESS HERE and only here: the
        pitching component SOLVES its centring constant per (season, role) so
        the role total is preserved by construction, which means a level shift
        in the FIP input is absorbed and the swap stays a within-role
        redistribution. Any other consumer of this map would need to handle it.
      * THE TAIL IS WILD ON TINY SAMPLES, min dFIP -71. That is arithmetic, not
        a bug: a pitcher who allowed 2 home runs in 5 batters faced has roughly
        1.9 of them regressed away over a third of an inning. His FIP was
        meaningless before the adjustment and is meaningless after; the
        component's centring is IP-weighted, so he moves nothing. Do not "fix"
        this by clamping, which would silently un-regress exactly the pitchers
        the variant exists to regress.

    GATED 2026-08-04 (lane R2e.2): NO SHIP, stays default-off, and the reason is
    NOT that it failed. It PASSED its own pre-registered rule in sample. The
    forecast leg (gate_pitcher_persistence.forecast_next_year_actual_runs,
    min_ip 50, 1825 pairs) runs smooth and single-peaked in k:

        k        None    100     200     400     800     1600
        forecast 0.2548  0.2665  0.2725  0.2782  0.2782  ~peak

    and two discriminating controls rule out the cheap explanation that this is
    generic reliability weighting rather than a home-run effect: the SAME
    exposure shrink applied to all three FIP rates gives 0.2222 at k=800 (WORSE
    than doing nothing) and applied to the K rate alone gives 0.1825, against
    0.2782 for HR-only. The effect is home-run specific, exactly as the
    hypothesis predicted.

    It is declined on two grounds that the in-sample curve cannot see.
      1. IT DOES NOT TRANSPORT. On a temporal holdout the gain is +0.0017, and
         the argmax moves from k=1600 to k=400 between eras. A parameter whose
         optimum is that unstable across time is fitting the era, not the noise.
      2. IT COLLIDES WITH THE w=0 DECISION. Turning it on drives the team
         next-season-wins leg monotonically DOWN past bWAR (0.2421 at k=400,
         0.2380 at k=800). That leg is already a null at k=None (see build());
         this would turn a null into a loss.
    Re-open only with a shrink target that is not a single global k, e.g. one
    fit per role or per era with its own transport test.
    """
    cor = _corpus()
    rows = cor.get("pit", [])
    league = {int(k): v for k, v in (cor.get("league") or {}).items()}

    lg_hr_bf: dict[int, float] = {}
    if hr_shrink_k:
        hr_sum: dict[int, float] = defaultdict(float)
        bf_sum: dict[int, float] = defaultdict(float)
        for r in rows:
            try:
                s = int(r["season"]); bf = float(r.get("bf") or 0.0)
                hr = float(r.get("hr_bf") or 0.0) * bf
            except (TypeError, ValueError, KeyError):
                continue
            if bf > 0:
                hr_sum[s] += hr
                bf_sum[s] += bf
        lg_hr_bf = {s: hr_sum[s] / bf_sum[s] for s in bf_sum if bf_sum[s] > 0}

    fip = {}
    for r in rows:
        mid, season, f = r.get("mlbam"), r.get("season"), r.get("fip")
        if mid is None or season is None or f is None:
            continue
        try:
            key = (int(mid), int(season))
            val = float(f)
        except (TypeError, ValueError):
            continue
        if hr_shrink_k:
            try:
                bf = float(r.get("bf") or 0.0)
                ip = float(r.get("ip") or 0.0)
                rate = float(r.get("hr_bf") or 0.0)
                lg = lg_hr_bf.get(int(season))
            except (TypeError, ValueError):
                bf = ip = 0.0
                lg = None
            if lg is not None and bf > 0 and ip > 0:
                shrunk = (rate * bf + lg * hr_shrink_k) / (bf + hr_shrink_k)
                val += 13.0 * (shrunk - rate) * bf / ip
        fip[key] = val
    return fip, league


def bwar_frames(force: bool = False):
    """(bat_df, pit_df) - Baseball-Reference war_daily via pybaseball.

    Two static ~5MB CSVs, the same pull stats.fetch_career_war_bulk makes, with
    a local pickle cache on top so the eval harness re-runs offline. This is the
    ONLY network call in the module, and it is the one the pipeline already
    makes routinely."""
    import pandas as pd                 # noqa: PLC0415 - heavy, only needed here
    CACHE_DIR.mkdir(exist_ok=True)
    bat_p, pit_p = CACHE_DIR / "ewar_bwar_bat.pkl", CACHE_DIR / "ewar_bwar_pit.pkl"
    fresh = (bat_p.exists() and pit_p.exists()
             and (time.time() - bat_p.stat().st_mtime) < BWAR_CACHE_TTL_S)
    if fresh and not force:
        return pd.read_pickle(bat_p), pd.read_pickle(pit_p)
    import pybaseball as pyb            # noqa: PLC0415
    log.info("ewar: pulling bwar_bat / bwar_pitch")
    bat = pyb.bwar_bat(return_all=True)
    pit = pyb.bwar_pitch(return_all=True)
    bat.to_pickle(bat_p)
    pit.to_pickle(pit_p)
    return bat, pit


def standings(seasons) -> dict[int, dict[str, dict]]:
    """{season: {bref_team_id: {"w", "l", "rs", "ra"}}} from the StatsAPI
    standings blobs fa_fit_backtest already caches under .cache/. Read-only:
    a missing season is skipped, never fetched.

    Runs scored / allowed come free in the same cached blob and are carried for
    gate_team_runs. They are what the components CAUSE; wins are what the
    components cause AFTER the Pythagorean relation adds noise neither series
    controls. Scoring against runs is therefore the sharper test, and it is the
    only place a fielding change is big enough to be visible at all.
    """
    out: dict[int, dict[str, dict]] = {}
    for y in seasons:
        p = CACHE_DIR / f"statsapi_standings_{y}.json"
        if not p.exists():
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows: dict[str, dict] = {}
        for rec in blob.get("records") or []:
            for tr in rec.get("teamRecords") or []:
                name = ((tr.get("team") or {}).get("name") or "").strip()
                tid = _CLUB_TO_BREF.get(name)
                if tid is None:
                    tid = next((v for k, v in _CLUB_TO_BREF.items()
                                if name.endswith(k)), None)
                if tid is None:
                    continue
                try:
                    rows[tid] = {"w": int(tr.get("wins") or 0),
                                 "l": int(tr.get("losses") or 0),
                                 "rs": _num(tr.get("runsScored"), None),
                                 "ra": _num(tr.get("runsAllowed"), None)}
                except (TypeError, ValueError):
                    continue
        if rows:
            out[int(y)] = rows
    return out


def _fold_team(tid) -> str:
    t = str(tid or "").strip().upper()
    return _TEAM_ID_FOLD.get(t, t)


def _num(v, default: float = 0.0) -> float:
    """float() that treats NaN/None/'' as `default`. `x or 0.0` does NOT: NaN is
    truthy, so a missing war_daily cell would propagate a NaN through the sum."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) else f


def _median(xs):
    xs = sorted(x for x in xs if x is not None and isinstance(x, (int, float))
                and math.isfinite(x))
    if not xs:
        return float("nan")
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


# ====================================================== fielding component
def fielding_component(first: int, last: int, shrink: bool = True) -> tuple[dict, dict]:
    """({(mlbam, season): row}, coverage_meta).

    row = {"runs": shrunk centred FRP over the covered positions,
           "covered_inn", "total_inn", "share", "positions": {...}}

    The centring is innings-weighted WITHIN (season, position). Savant centres
    OAA within a position's own opportunity set but not against the other
    positions - in 2019 the league CF pool sums to +158 FRP while the LF pool
    sums to -160 - so handing raw FRP to a frame that already carries B-Ref's
    runs_position would pay the outfield ladder twice.

    The shrinkage is toward the position average, by playing time, with the
    k_inn constants positional_fit.py fitted. Set shrink=False for the
    sensitivity arm the eval reports.
    """
    oaa = _load_json("savant_oaa.json").get("by_mlbam", {})
    innings = _load_json("fielding_innings.json").get("seasons", {})
    k_inn = shrinkage_constants()

    # ---- pass 1: raw reads, and the innings-weighted per (season, pos) mean
    reads: dict[tuple[int, int], dict[str, dict]] = defaultdict(dict)
    pool_frp: dict[tuple[int, str], float] = defaultdict(float)
    pool_inn: dict[tuple[int, str], float] = defaultdict(float)
    for mid_s, by_year in oaa.items():
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        for y_s, by_pos in by_year.items():
            try:
                season = int(y_s)
            except (TypeError, ValueError):
                continue
            if season < first or season > last:
                continue
            inn_row = (innings.get(y_s) or {}).get(mid_s) or {}
            for pos, rec in by_pos.items():
                if pos.startswith("_") or pos not in OAA_POSITIONS:
                    continue
                inn = float((inn_row.get(pos) or {}).get("inn") or 0.0)
                if inn <= 0:
                    continue          # no exposure on record -> not covered
                frp = float(rec.get("frp") or 0.0)
                reads[(mid, season)][pos] = {"frp": frp, "inn": inn,
                                             "oaa": float(rec.get("oaa") or 0.0)}
                pool_frp[(season, pos)] += frp
                pool_inn[(season, pos)] += inn
    mu = {k: (pool_frp[k] * 1000.0 / pool_inn[k]) for k in pool_inn if pool_inn[k] > 0}

    # ---- pass 2: centre, shrink, sum over the player's covered positions
    out: dict[tuple[int, int], dict] = {}
    for (mid, season), by_pos in reads.items():
        inn_row = (innings.get(str(season)) or {}).get(str(mid)) or {}
        # denominator: every defensive inning on record except DH (which is not
        # defense). Pitcher innings stay IN, so a pitcher's own glove keeps
        # B-Ref's rfield rather than being silently zeroed.
        total_inn = sum(float((v or {}).get("inn") or 0.0)
                        for p, v in inn_row.items() if p != "DH")
        runs = 0.0
        detail = {}
        covered_inn = 0.0
        for pos, rec in by_pos.items():
            inn, frp = rec["inn"], rec["frp"]
            rate = frp * 1000.0 / inn
            centred = rate - mu.get((season, pos), 0.0)
            rel = inn / (inn + k_inn[pos]) if shrink else 1.0
            r = centred * rel * inn / 1000.0
            runs += r
            covered_inn += inn
            detail[pos] = {"inn": round(inn, 1), "frp": round(frp, 1),
                           "oaa": round(rec["oaa"], 1), "rel": round(rel, 3),
                           "runs": round(r, 2)}
        share = min(1.0, covered_inn / total_inn) if total_inn > 0 else 0.0
        out[(mid, season)] = {"runs": runs, "covered_inn": covered_inn,
                              "total_inn": total_inn, "share": share,
                              "positions": detail}

    # ---- coverage bookkeeping, by season and by position, over ALL innings
    cov: dict[int, dict] = {}
    for y_s, by_mid in innings.items():
        try:
            season = int(y_s)
        except (TypeError, ValueError):
            continue
        if season < first or season > last:
            continue
        blk = cov.setdefault(season, {"inn_total": 0.0, "inn_covered": 0.0,
                                      "by_pos": {}, "n_player_seasons": 0,
                                      "n_position_player_seasons": 0,
                                      "n_with_read": 0})
        for mid_s, by_pos in by_mid.items():
            blk["n_player_seasons"] += 1
            if any(p not in ("P", "DH") and float((v or {}).get("inn") or 0.0) > 0
                   for p, v in by_pos.items()):
                blk["n_position_player_seasons"] += 1
            has = False
            for pos, v in by_pos.items():
                if pos == "DH":
                    continue
                inn = float((v or {}).get("inn") or 0.0)
                if inn <= 0:
                    continue
                pb = blk["by_pos"].setdefault(pos, {"inn": 0.0, "inn_covered": 0.0,
                                                    "n": 0, "n_covered": 0})
                pb["inn"] += inn
                pb["n"] += 1
                blk["inn_total"] += inn
                rd = reads.get((int(mid_s), season), {}).get(pos)
                if rd is not None:
                    pb["inn_covered"] += inn
                    pb["n_covered"] += 1
                    blk["inn_covered"] += inn
                    has = True
            if has:
                blk["n_with_read"] += 1
    for season, blk in cov.items():
        blk["share"] = round(blk["inn_covered"] / blk["inn_total"], 4) if blk["inn_total"] else 0.0
        blk["inn_total"] = round(blk["inn_total"], 1)
        blk["inn_covered"] = round(blk["inn_covered"], 1)
        for pb in blk["by_pos"].values():
            pb["share"] = round(pb["inn_covered"] / pb["inn"], 4) if pb["inn"] else 0.0
            pb["inn"] = round(pb["inn"], 1)
            pb["inn_covered"] = round(pb["inn_covered"], 1)
    return out, {"by_season": cov,
                 "k_inn": {p: round(v, 1) for p, v in k_inn.items()},
                 "position_centering": {f"{s}:{p}": round(v, 4)
                                        for (s, p), v in sorted(mu.items())},
                 "shrunk": bool(shrink)}


# ====================================================== pitching component
def pitching_component(pit, fip_map: dict, league: dict) -> tuple[dict, dict]:
    """({row_index: raa_fip}, meta) - FIP-priced runs above average.

    Per (season, role): FIPR9 = FIP x lgRA9/lgERA carries the pitcher's own FIP
    from the ERA scale onto the runs-allowed scale the B-Ref frame prices in.
    The centring constant C is SOLVED, not assumed, so that

        sum_i (C x PPF_i/100 - FIPR9_i) x IP_i / 9  ==  sum_i runs_above_avg_adj_i

    over the covered rows of that cell. The FIP swap therefore moves runs
    BETWEEN pitchers of the same role and never changes the role's total, which
    keeps B-Ref's starter/reliever pricing (xRA_sprp_adj) and its replacement
    level exactly as they are, and makes the comparison a clean within-role
    redistribution rather than a level argument.
    """
    import numpy as np                  # noqa: PLC0415
    import pandas as pd                 # noqa: PLC0415

    d = pit.copy()
    for c in ("IPouts", "IPouts_start", "RA", "runs_above_avg_adj", "PPF"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["mid"] = pd.to_numeric(d["mlb_ID"], errors="coerce")
    d["IP"] = d["IPouts"] / 3.0
    d["role"] = np.where(d["IPouts_start"] / d["IPouts"].replace(0, np.nan) >= 0.5,
                         "SP", "RP")
    d["role"] = d["role"].fillna("RP")
    # PPF 100 = neutral; a missing/zero factor means "no park read", not "no park".
    ppf = d["PPF"].where(d["PPF"] > 0, 100.0).fillna(100.0)

    meta = {"by_season": {}, "n_rows": int(len(d)), "n_covered": 0,
            "ip_total": 0.0, "ip_covered": 0.0}
    raa: dict = {}
    for season, sub in d.groupby(d["year_ID"].astype(int)):
        lg = league.get(int(season)) or {}
        lg_era = lg.get("era")
        ip_sum = float(sub["IP"].sum())
        ra_sum = float(sub["RA"].sum())
        lg_ra9 = 9.0 * ra_sum / ip_sum if ip_sum > 0 else None
        blk = {"lg_ra9": round(lg_ra9, 4) if lg_ra9 else None,
               "lg_era": round(float(lg_era), 4) if lg_era else None,
               "ip_total": round(ip_sum, 1), "ip_covered": 0.0,
               "n_rows": int(len(sub)), "n_covered": 0, "cells": {}}
        meta["ip_total"] += ip_sum
        if not lg_era or not lg_ra9:
            blk["skipped"] = "no league ERA (corpus) or no innings"
            meta["by_season"][int(season)] = blk
            continue
        scale = lg_ra9 / float(lg_era)
        blk["ra9_per_era_scale"] = round(scale, 5)
        for role, cell in sub.groupby("role"):
            idx, fipr9, ip_i, ppf_i, tgt = [], [], [], [], 0.0
            for i, r in cell.iterrows():
                f = fip_map.get((int(r["mid"]), int(season))) if pd.notna(r["mid"]) else None
                ip = float(r["IP"]) if pd.notna(r["IP"]) else 0.0
                tgt_i = r["runs_above_avg_adj"]
                if f is None or ip <= 0 or pd.isna(tgt_i):
                    continue
                idx.append(i)
                fipr9.append(float(f) * scale)
                ip_i.append(ip)
                ppf_i.append(float(ppf.loc[i]) / 100.0)
                tgt += float(tgt_i)
            if len(idx) < MIN_ROLE_CELL_ROWS:
                blk["cells"][role] = {"n": len(idx), "solved": False,
                                      "why": "cell below MIN_ROLE_CELL_ROWS"}
                continue
            fipr9 = np.array(fipr9); ip_i = np.array(ip_i); ppf_i = np.array(ppf_i)
            den = float((ip_i * ppf_i).sum())
            if den <= 0:
                blk["cells"][role] = {"n": len(idx), "solved": False,
                                      "why": "zero park-weighted innings"}
                continue
            C = (9.0 * tgt + float((fipr9 * ip_i).sum())) / den
            vals = (C * ppf_i - fipr9) * ip_i / 9.0
            for i, v in zip(idx, vals):
                raa[i] = float(v)
            blk["cells"][role] = {
                "n": len(idx), "solved": True,
                "centre_ra9": round(C, 4),
                "centre_vs_lg_ra9": round(C - lg_ra9, 4),
                "bref_raa_total": round(tgt, 2),
                "ewar_raa_total": round(float(vals.sum()), 2),
                "ip": round(float(ip_i.sum()), 1),
            }
            blk["n_covered"] += len(idx)
            blk["ip_covered"] += float(ip_i.sum())
            meta["n_covered"] += len(idx)
            meta["ip_covered"] += float(ip_i.sum())
        blk["ip_covered"] = round(blk["ip_covered"], 1)
        blk["ip_share"] = round(blk["ip_covered"] / ip_sum, 4) if ip_sum else 0.0
        meta["by_season"][int(season)] = blk
    meta["ip_share"] = round(meta["ip_covered"] / meta["ip_total"], 4) if meta["ip_total"] else 0.0
    meta["ip_total"] = round(meta["ip_total"], 1)
    meta["ip_covered"] = round(meta["ip_covered"], 1)
    return raa, meta


# ============================================================= runs per win
def runs_per_win(bat, pit) -> tuple[dict, dict]:
    """({(season, team_id): rpw}, {season: rpw}).

    B-Ref does not publish its runs-per-win, but it publishes both sides of the
    conversion on every row, so we recover it rather than inventing a formula:
    a least-squares slope through the origin of runs-above-average on
    wins-above-average, per team-season, over rows whose |WAA| is large enough
    that the published rounding is not the dominant term. Recovered values run
    8.0-11.2 across 2016-2025, which is the right band for a 4.3-4.9 RA9 league.
    """
    import pandas as pd                 # noqa: PLC0415

    frames = []
    b = bat[["year_ID", "team_ID", "runs_above_avg", "WAA"]].copy()
    b.columns = ["season", "team", "raa", "waa"]
    frames.append(b)
    p = pit[["year_ID", "team_ID", "runs_above_avg_adj", "WAA"]].copy()
    p.columns = ["season", "team", "raa", "waa"]
    frames.append(p)
    d = pd.concat(frames, ignore_index=True)
    d["season"] = pd.to_numeric(d["season"], errors="coerce")
    d["raa"] = pd.to_numeric(d["raa"], errors="coerce")
    d["waa"] = pd.to_numeric(d["waa"], errors="coerce")
    d["team"] = d["team"].map(_fold_team)
    d = d.dropna(subset=["season", "raa", "waa"])
    d = d[d["waa"].abs() >= RPW_MIN_WAA]

    def _tls(g):
        den = float((g["waa"] ** 2).sum())
        return float((g["raa"] * g["waa"]).sum()) / den if den > 0 else float("nan")

    by_team = {}
    for (season, team), g in d.groupby(["season", "team"]):
        v = _tls(g)
        if math.isfinite(v) and RPW_MIN <= v <= RPW_MAX:
            by_team[(int(season), team)] = v
    by_season = {}
    for season, g in d.groupby("season"):
        v = _tls(g)
        by_season[int(season)] = v if math.isfinite(v) and RPW_MIN <= v <= RPW_MAX else RPW_FALLBACK
    return by_team, by_season


# ================================================================== assembly
def build(first: int = DEFAULT_FIRST_SEASON, last: int | None = None,
          shrink: bool = True, force_fetch: bool = False,
          swap_fielding: bool = True, swap_pitching: bool = True,
          fielding_blend_w: float | None = None,
          fip_hr_shrink_k: float | None = None) -> dict:
    """The model. Returns {"rows": [...], "meta": {...}}.

    A row is one war_daily stint (player x season x team x side), carrying both
    series so every downstream comparison is on identical rows by construction.

    swap_fielding / swap_pitching turn the two component replacements off
    independently. Both default True (that is eWAR v1); the eval runs the two
    single-swap arms so the gate movement is ATTRIBUTABLE to a component
    instead of being one undifferentiated number.

    fielding_blend_w is the weight on the STATCAST read over the innings it
    covers; rfield takes the remainder. w=0.0 reproduces bWAR's fielding exactly
    and w=1.0 reproduces eWAR v1 exactly; both endpoints are asserted by
    test_ewar_fielding_blend.py and were confirmed on real rows (max diff 0.0 to
    ten decimals over 6,640 batter-seasons).

    THE DEFAULT IS NOW 0.0, i.e. eWAR v2 DOES NOT USE STATCAST FIELDING AT ALL.
    That is a measured decision, not a preference. Grid over 2016-2025, 300
    team-seasons, pitching swap on throughout so w=0 is the pitching-only arm:

        w      wins r   wins mae0   next-yr r   next-yr r   prevention |r|
                                    (pooled)    (full sched)
        0.00   0.8595     4.306      0.2524       0.5920        0.3780
        0.25   0.8636     4.260      0.2491       0.5894        0.3759
        0.50   0.8667     4.251      0.2452       0.5856        0.3718
        0.75   0.8684     4.277      0.2408       0.5805        0.3652
        1.00   0.8686     4.347      0.2359       0.5740        0.3559
        bWAR   0.8803     3.787      0.2481       0.5913        0.4290

    Both FORWARD-LOOKING legs are monotone decreasing in w: every increment of
    Statcast fielding costs next-season signal AND run-prevention correlation.
    The blend was built to rescue the fielding swap and instead established that
    the optimum is not to use it. THAT ORDERING IS ROBUST: it is monotone on the
    pooled pairs AND on full-schedule pairs only, so it is not an artifact of
    the 2020 scale problem described next. w=0.0 is the measured optimum.

    WHAT w=0 DOES **NOT** BUY, corrected 2026-08-04 after this docstring
    briefly claimed the opposite. The pooled next-yr column is
    SCALE-CONTAMINATED: 60 of its 270 pairs straddle the 60-game 2020 season,
    putting a 60-game season on one axis and a 162-game season on the other.
    Those 60 pairs correlate about -0.53 and drag the pooled r from roughly
    0.59 to 0.25. On full-schedule pairs (n=210) eWAR reads 0.5920 against
    bWAR's 0.5913, a delta of +0.0006, i.e. NOTHING. A zero-information control
    that shuffles the per-team eWAR-minus-bWAR delta across teams produces an
    absolute delta at least as large 82.3% of the time and beats bWAR outright
    in 27.3% of shuffles; per year-pair eWAR wins 4 of 9 and loses the four most
    recent, with the pooled edge carried by 2016->2017 and the COVID pair. So
    eWAR v2 is a NULL against bWAR at the TEAM level in both directions of
    time, and its real case is at the PITCHER level (gate 2), where the
    persistence gain is 2.1x and survives its controls. Do not quote the pooled
    0.2524 as a win.

    The forward number is also fragile to the pitching variant: turning on
    fip_hr_shrink_k at k>=200 drives it BELOW bWAR (0.2421 at k=400, 0.2380 at
    k=800), which is one of the two reasons that variant stays default-off.
    See corpus_fip for the full sweep.

    The offense arm is an exact null control at every w (r 0.3132 for both
    series), so no component leaked and the gate can be trusted.

    The machinery stays because the DECISION is re-testable, not permanent: the
    reason Statcast fielding loses here is that Savant's read is range-only
    while rfield also carries arm, framing, blocking and the double-play pivot,
    so it is a better metric for a NARROWER quantity. If an arm-value and
    catcher-framing run model ever lands, re-run this grid before assuming the
    answer is still 0.
    """
    import numpy as np                  # noqa: PLC0415
    import pandas as pd                 # noqa: PLC0415

    last = int(last or _dt.date.today().year)
    first = int(first)
    bat_all, pit_all = bwar_frames(force=force_fetch)
    bat = bat_all[(pd.to_numeric(bat_all.year_ID, errors="coerce") >= first)
                  & (pd.to_numeric(bat_all.year_ID, errors="coerce") <= last)].copy()
    pit = pit_all[(pd.to_numeric(pit_all.year_ID, errors="coerce") >= first)
                  & (pd.to_numeric(pit_all.year_ID, errors="coerce") <= last)].copy()
    for c in ("PA", "G", "Inn", "runs_bat", "runs_br", "runs_dp", "runs_field",
              "runs_position", "runs_position_p", "runs_replacement",
              "runs_above_avg", "WAA", "WAR", "WAR_rep"):
        bat[c] = pd.to_numeric(bat[c], errors="coerce")
    for c in ("G", "GS", "IPouts", "IPouts_start", "RA", "runs_above_avg",
              "runs_above_avg_adj", "WAA", "WAA_adj", "WAR", "WAR_rep", "PPF"):
        pit[c] = pd.to_numeric(pit[c], errors="coerce")
    bat["mid"] = pd.to_numeric(bat["mlb_ID"], errors="coerce")
    pit["mid"] = pd.to_numeric(pit["mlb_ID"], errors="coerce")
    bat["year_ID"] = pd.to_numeric(bat["year_ID"], errors="coerce").astype(int)
    pit["year_ID"] = pd.to_numeric(pit["year_ID"], errors="coerce").astype(int)

    fld, fld_meta = fielding_component(first, last, shrink=shrink)
    fip_map, league = corpus_fip(hr_shrink_k=fip_hr_shrink_k)
    praa, pit_meta = pitching_component(pit, fip_map, league)
    rpw_team, rpw_season = runs_per_win(bat, pit)

    def _rpw(season: int, team: str) -> float:
        return rpw_team.get((season, _fold_team(team))) or rpw_season.get(season, RPW_FALLBACK)

    # ---- fielding: the swap is a player-SEASON quantity (OAA is), the frame is
    # a stint. Allocate the season delta across the player's stints by their
    # defensive innings, which is the only split the war_daily frame publishes.
    bat_field_season: dict[tuple[int, int], float] = defaultdict(float)
    bat_inn_season: dict[tuple[int, int], float] = defaultdict(float)
    bat_pa_season: dict[tuple[int, int], float] = defaultdict(float)
    for r in bat.itertuples(index=False):
        if not np.isfinite(r.mid):
            continue
        key = (int(r.mid), int(r.year_ID))
        bat_field_season[key] += _num(r.runs_field)
        bat_inn_season[key] += _num(r.Inn)
        bat_pa_season[key] += _num(r.PA)

    field_delta_season: dict[tuple[int, int], float] = {}
    field_src: dict[tuple[int, int], tuple[str, float]] = {}
    # DEFAULT 0.0 since 2026-08-04: no Statcast fielding. See build()'s docstring
    # for the w grid that decided it (both forward legs monotone decreasing in w).
    w_blend = 0.0 if fielding_blend_w is None else float(fielding_blend_w)
    for key, bref in bat_field_season.items():
        rec = fld.get(key) if swap_fielding else None
        if rec is None or rec["share"] <= 0:
            field_delta_season[key] = 0.0
            field_src[key] = ("bref", 0.0)
            continue
        share = rec["share"]
        # v1 REPLACED rfield with the Statcast read wherever Statcast covered the
        # innings. v2 BLENDS the two over the covered fraction instead, because
        # they do not measure the same quantity: Savant FRP is range, while
        # B-Ref rfield also carries arm, catcher framing and blocking, scoops and
        # the double-play pivot. A replacement therefore trades a better metric
        # for a NARROWER one and drops real value, which is what the v1
        # attribution arms measured - the fielding swap alone lost BOTH gates
        # (same-season r 0.8777 and next-season 0.2255, against a bWAR baseline
        # of 0.8803 / 0.2481) while the pitching swap paid for itself.
        #
        # Only the COVERED fraction is blended; uncovered innings keep rfield
        # pro-rated exactly as before. The two endpoints are the harness's
        # validity checks and must hold exactly:
        #   w = 1.0  ->  rec["runs"] + bref*(1-share)      = eWAR v1
        #   w = 0.0  ->  bref*share  + bref*(1-share)      = bWAR
        covered_e = w_blend * rec["runs"] + (1.0 - w_blend) * (bref * share)
        e_field = covered_e + bref * (1.0 - share)
        field_delta_season[key] = e_field - bref
        src = "bref" if w_blend <= 0.0 else ("oaa" if share >= 0.95 else "mixed")
        if 0.0 < w_blend < 1.0 and src != "bref":
            src = "blend"
        field_src[key] = (src, share)

    rows = []
    for r in bat.itertuples(index=False):
        season = int(r.year_ID)
        team = _fold_team(r.team_ID)
        rpw = _rpw(season, team)
        key = (int(r.mid), season) if np.isfinite(r.mid) else None
        d_field = 0.0
        if key is not None and field_delta_season.get(key):
            tot_inn = bat_inn_season.get(key, 0.0)
            if tot_inn > 0:
                w = _num(r.Inn) / tot_inn
            else:                                  # no innings anywhere: split by PA
                pa_tot = bat_pa_season.get(key, 0.0)
                w = (_num(r.PA) / pa_tot) if pa_tot > 0 else 0.0
            d_field = field_delta_season[key] * w
        src, share = field_src.get(key, ("bref", 0.0)) if key else ("bref", 0.0)
        bw = _num(r.WAR)
        rows.append({
            "mid": int(r.mid) if np.isfinite(r.mid) else None,
            "name": r.name_common, "season": season, "team": team, "side": "bat",
            "pa": _num(r.PA), "ip": 0.0,
            "bwar": bw, "ewar_raw": bw + d_field / rpw,
            "rep": _num(r.WAR_rep), "rpw": rpw,
            "rbat": _num(r.runs_bat), "rbr": _num(r.runs_br),
            "rdp": _num(r.runs_dp),
            "rpos": _num(r.runs_position) + _num(r.runs_position_p),
            "rrep": _num(r.runs_replacement),
            "rfield_bref": _num(r.runs_field),
            "rfield_ewar": _num(r.runs_field) + d_field,
            "field_src": src, "field_cov": share,
            "praa_bref": None, "praa_ewar": None,
        })

    for i, r in pit.iterrows():
        season = int(r["year_ID"])
        team = _fold_team(r["team_ID"])
        rpw = _rpw(season, team)
        base = r["runs_above_avg_adj"]
        base_ok = pd.notna(base)
        e_raa = praa.get(i) if swap_pitching else None
        bw = _num(r["WAR"])
        if e_raa is None or not base_ok:
            d_pitch, e_raa_out, src = 0.0, (float(base) if base_ok else None), "bref"
        else:
            d_pitch = e_raa - float(base)
            e_raa_out, src = e_raa, "fip"
        ip = _num(r["IPouts"]) / 3.0
        rows.append({
            "mid": int(r["mid"]) if pd.notna(r["mid"]) else None,
            "name": r["name_common"], "season": season, "team": team, "side": "pit",
            "pa": 0.0, "ip": ip,
            "bwar": bw, "ewar_raw": bw + d_pitch / rpw,
            "rep": _num(r["WAR_rep"]), "rpw": rpw,
            "rbat": 0.0, "rbr": 0.0, "rdp": 0.0, "rpos": 0.0, "rrep": 0.0,
            "rfield_bref": 0.0, "rfield_ewar": 0.0,
            "field_src": None, "field_cov": None,
            "praa_bref": float(base) if np.isfinite(base) else None,
            "praa_ewar": e_raa_out, "pitch_src": src,
        })

    # ---- replacement re-derivation: land the league total on the platform's
    # own convention, by scaling each row's replacement component.
    stand = standings(range(first, last + 1))
    season_meta: dict[int, dict] = {}
    by_season: dict[int, list] = defaultdict(list)
    for row in rows:
        by_season[row["season"]].append(row)
    for season, srows in sorted(by_season.items()):
        games = sum(v["w"] + v["l"] for v in (stand.get(season) or {}).values())
        target = ((0.5 - REPLACEMENT_WINS / FULL_SEASON_GAMES) * games) if games else None
        sum_b = sum(r["bwar"] for r in srows)
        sum_e_pre = sum(r["ewar_raw"] for r in srows)
        sum_rep = sum(r["rep"] for r in srows)
        if target is not None and sum_rep > 0:
            rep_scale = 1.0 + (target - sum_e_pre) / sum_rep
        else:
            rep_scale = 1.0
        for r in srows:
            r["ewar"] = r["ewar_raw"] + (rep_scale - 1.0) * r["rep"]
        season_meta[season] = {
            "team_games": games or None,
            "league_war_target": round(target, 2) if target is not None else None,
            "bwar_league_sum": round(sum_b, 2),
            "ewar_league_sum_pre_rescale": round(sum_e_pre, 2),
            "ewar_league_sum": round(sum(r["ewar"] for r in srows), 2),
            "replacement_wins_total": round(sum_rep, 2),
            "replacement_scale": round(rep_scale, 5),
            "rpw_median": round(_median([r["rpw"] for r in srows]), 4) if srows else None,
            "n_rows": len(srows),
        }

    meta = {
        "model": MODEL,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "seasons": [first, last],
        "shrunk_fielding": bool(shrink),
        "swap_fielding": bool(swap_fielding),
        "swap_pitching": bool(swap_pitching),
        # Weight on the Statcast read over the innings it covers; rfield takes
        # the rest. 1.0 is the v1 full replacement. Recorded so a served payload
        # always states which fielding configuration produced it.
        "fielding_blend_w": (0.0 if fielding_blend_w is None else float(fielding_blend_w)),
        # Home-run regression strength on the FIP leg (None = off, which is
        # the shipped model). Recorded so a payload states its own variant.
        "fip_hr_shrink_k": (None if fip_hr_shrink_k is None else float(fip_hr_shrink_k)),
        "replacement_wins": REPLACEMENT_WINS,
        "fielding": fld_meta,
        "pitching": pit_meta,
        "by_season": season_meta,
        "rpw_by_season": {k: round(v, 4) for k, v in sorted(rpw_season.items())},
    }
    return {"rows": rows, "meta": meta}


# ================================================================== artifact
def export_payload(model: dict) -> dict:
    """The data/ewar.json shape: one block per (mlbam, season), stints summed.

    Field key (all runs unless noted):
      ew  eWAR (wins)            bw  bWAR (wins)
      ewb/bwb  batting-side wins  ewp/bwp  pitching-side wins
      fe  eWAR fielding runs      fb  B-Ref rfield
      fs  fielding source: oaa | mixed | bref
      fc  covered innings share (0-1)
      pe  eWAR pitching runs above average (FIP)
      pb  B-Ref runs_above_avg_adj
      ps  pitching source: fip | bref
      rb/rr/rd/rp/rv  runs_bat / runs_br / runs_dp / positional / replacement
      pa  plate appearances      ip  innings pitched
      tm  team_IDs
    """
    players: dict[str, dict] = {}
    acc: dict[tuple[int, int], dict] = {}
    for r in model["rows"]:
        if r["mid"] is None:
            continue
        key = (r["mid"], r["season"])
        a = acc.setdefault(key, {"ew": 0.0, "bw": 0.0, "ewb": 0.0, "bwb": 0.0,
                                 "ewp": 0.0, "bwp": 0.0, "fe": 0.0, "fb": 0.0,
                                 "pe": 0.0, "pb": 0.0, "rb": 0.0, "rr": 0.0,
                                 "rd": 0.0, "rp": 0.0, "rv": 0.0, "pa": 0.0,
                                 "ip": 0.0, "tm": [], "fs": None, "ps": None,
                                 "fc": None, "name": r["name"],
                                 "has_bat": False, "has_pit": False})
        a["has_bat"] = a["has_bat"] or r["side"] == "bat"
        a["has_pit"] = a["has_pit"] or r["side"] == "pit"
        a["ew"] += r["ewar"]
        a["bw"] += r["bwar"]
        if r["side"] == "bat":
            a["ewb"] += r["ewar"]; a["bwb"] += r["bwar"]
            a["fe"] += r["rfield_ewar"]; a["fb"] += r["rfield_bref"]
            a["rb"] += r["rbat"]; a["rr"] += r["rbr"]; a["rd"] += r["rdp"]
            a["rp"] += r["rpos"]; a["rv"] += r["rrep"]
            a["pa"] += r["pa"]
            if r["field_src"]:
                a["fs"] = r["field_src"]
                a["fc"] = r["field_cov"]
        else:
            a["ewp"] += r["ewar"]; a["bwp"] += r["bwar"]
            if r["praa_ewar"] is not None:
                a["pe"] += r["praa_ewar"]
            if r["praa_bref"] is not None:
                a["pb"] += r["praa_bref"]
            a["ip"] += r["ip"]
            a["ps"] = r.get("pitch_src") or a["ps"]
        if r["team"] not in a["tm"]:
            a["tm"].append(r["team"])
    for (mid, season), a in acc.items():
        blk = {"ew": round(a["ew"], 2), "bw": round(a["bw"], 2)}
        # the block is emitted whenever a war_daily row of that side EXISTS, not
        # whenever it is non-zero, so ew == ewb + ewp always holds.
        if a["has_bat"]:
            blk.update({"ewb": round(a["ewb"], 2), "bwb": round(a["bwb"], 2),
                        "fe": round(a["fe"], 1), "fb": round(a["fb"], 1),
                        "fs": a["fs"] or "bref",
                        "rb": round(a["rb"], 1), "rr": round(a["rr"], 1),
                        "rd": round(a["rd"], 1), "rp": round(a["rp"], 1),
                        "rv": round(a["rv"], 1), "pa": int(round(a["pa"]))})
            if a["fc"] is not None:
                blk["fc"] = round(a["fc"], 3)
        if a["has_pit"]:
            blk.update({"ewp": round(a["ewp"], 2), "bwp": round(a["bwp"], 2),
                        "pe": round(a["pe"], 1), "pb": round(a["pb"], 1),
                        "ps": a["ps"] or "bref", "ip": round(a["ip"], 1)})
        blk["tm"] = a["tm"]
        players.setdefault(str(mid), {})[str(season)] = blk
    meta = dict(model["meta"])
    # the position-centering table is a build diagnostic, not a served field
    meta["fielding"] = {k: v for k, v in meta["fielding"].items()
                        if k != "position_centering"}
    return {
        "model": MODEL,
        "generated_at": meta["generated_at"],
        "seasons": meta["seasons"],
        "consumers": "SERVED: war_source DEFAULT_PROVIDER ewar_v2 since the "
                     "2026-09-03 epoch (owner basis decision; gates unchanged). "
                     "The two consumer gates measured 2026-08-04 (R3a eFV label "
                     "swap, R3b fa_backtest Gate 1) remain the accuracy record.",
        "field_key": {
            "ew": "eWAR (wins)", "bw": "Baseball-Reference bWAR (wins)",
            "ewb": "eWAR batting side", "bwb": "bWAR batting side",
            "ewp": "eWAR pitching side", "bwp": "bWAR pitching side",
            "fe": "eWAR fielding runs (Statcast FRP where covered, else rfield)",
            "fb": "B-Ref rfield", "fs": "fielding source (oaa|mixed|bref)",
            "fc": "share of defensive innings with a Statcast read",
            "pe": "eWAR pitching runs above average (FIP basis)",
            "pb": "B-Ref runs_above_avg_adj (runs-allowed basis)",
            "ps": "pitching source (fip|bref)",
            "rb": "runs_bat", "rr": "runs_br", "rd": "runs_dp",
            "rp": "positional adjustment runs", "rv": "replacement runs",
            "pa": "plate appearances", "ip": "innings pitched",
            "tm": "team_IDs",
        },
        "meta": meta,
        "n_player_seasons": len(acc),
        "players": players,
    }


_CACHE: dict | None = None


def load(path: Path | None = None) -> dict:
    """Read data/ewar.json (memoised)."""
    global _CACHE
    if _CACHE is None or path is not None:
        p = path or OUT
        blob = json.loads(p.read_text(encoding="utf-8"))
        if path is not None:
            return blob
        _CACHE = blob
    return _CACHE


def ewar_for(mlbam: int, season: int, payload: dict | None = None) -> dict | None:
    """THE PUBLIC READ. Per (player, season): eWAR plus its components, or None
    when the player-season is not in the artifact.

    A future D0 facade calls exactly this and nothing else:

        rec = ewar.ewar_for(660271, 2024)
        rec["ewar"], rec["bwar"], rec["fielding_runs"], rec["pitching_raa"]
    """
    try:
        blob = payload or load()
    except (OSError, ValueError):
        return None
    blk = ((blob.get("players") or {}).get(str(int(mlbam))) or {}).get(str(int(season)))
    if not blk:
        return None
    return {
        "mlbam": int(mlbam), "season": int(season),
        "ewar": blk.get("ew"), "bwar": blk.get("bw"),
        "ewar_bat": blk.get("ewb"), "ewar_pit": blk.get("ewp"),
        "bwar_bat": blk.get("bwb"), "bwar_pit": blk.get("bwp"),
        "runs_bat": blk.get("rb"), "runs_br": blk.get("rr"),
        "runs_dp": blk.get("rd"), "runs_position": blk.get("rp"),
        "runs_replacement": blk.get("rv"),
        "fielding_runs": blk.get("fe"), "fielding_runs_bref": blk.get("fb"),
        "fielding_source": blk.get("fs"), "fielding_coverage": blk.get("fc"),
        "pitching_raa": blk.get("pe"), "pitching_raa_bref": blk.get("pb"),
        "pitching_source": blk.get("ps"),
        "pa": blk.get("pa"), "ip": blk.get("ip"), "teams": blk.get("tm"),
    }


# ===================================================================== gates
def _pearson(xs, ys) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((a - mx) ** 2 for a in xs)
    if sxx <= 0:
        return my, 0.0
    slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sxx
    return my - slope * mx, slope


def _team_season_points(model: dict, first: int, last: int) -> list[dict]:
    """One point per team-season with standings on disk: summed eWAR and bWAR
    over identical rows, the record and the replacement level."""
    stand = standings(range(first, last + 1))
    tot: dict[tuple[int, str], dict] = defaultdict(lambda: {"e": 0.0, "b": 0.0})
    for r in model["rows"]:
        if r["season"] < first or r["season"] > last:
            continue
        t = tot[(r["season"], r["team"])]
        t["e"] += r["ewar"]
        t["b"] += r["bwar"]
    pts = []
    for (season, team), v in sorted(tot.items()):
        rec = (stand.get(season) or {}).get(team)
        if not rec:
            continue
        games = rec["w"] + rec["l"]
        pts.append({"season": season, "team": team, "wins": rec["w"],
                    "games": games, "ewar": v["e"], "bwar": v["b"],
                    "repl": REPLACEMENT_WINS * games / FULL_SEASON_GAMES})
    return pts


def gate_team_wins(model: dict, first: int, last: int) -> dict:
    """GATE 1 - the standard WAR validity test. Team-season WAR against actual
    team wins, eWAR and bWAR on IDENTICAL rows."""
    pts = _team_season_points(model, first, last)
    if not pts:
        return {"n": 0, "note": "no standings on disk for this window"}

    def _series(key):
        xs = [p[key] for p in pts]
        ys = [float(p["wins"]) for p in pts]
        r = _pearson(xs, ys)
        a, b = _ols(xs, ys)
        mae_fit = sum(abs(y - (a + b * x)) for x, y in zip(xs, ys)) / len(xs)
        rmse_fit = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / len(xs))
        # zero-parameter calibration: replacement wins + team WAR
        pred = [p["repl"] + p[key] for p in pts]
        mae_abs = sum(abs(y - q) for y, q in zip(ys, pred)) / len(ys)
        bias_abs = sum(q - y for y, q in zip(ys, pred)) / len(ys)
        return {"r": round(r, 4) if r is not None else None,
                "r2": round(r * r, 4) if r is not None else None,
                "mae_fit": round(mae_fit, 3), "rmse_fit": round(rmse_fit, 3),
                "fit_intercept": round(a, 3), "fit_slope": round(b, 4),
                "mae_zero_param": round(mae_abs, 3),
                "bias_zero_param": round(bias_abs, 3)}

    out = {"n_team_seasons": len(pts), "seasons": [first, last],
           "ewar": _series("ewar"), "bwar": _series("bwar")}

    # The same-season test rewards DESCRIBING what happened. The companion test
    # rewards CARRYING SIGNAL: does this year's team WAR predict next year's
    # wins? Same rosters-change noise for both series, same rows.
    idx = {(p["season"], p["team"]): p for p in pts}
    nxt = [(p, idx[(p["season"] + 1, p["team"])]) for p in pts
           if (p["season"] + 1, p["team"]) in idx]
    if len(nxt) >= 30:
        ys = [float(b["wins"]) for _, b in nxt]
        out["next_season_wins"] = {
            "n": len(nxt),
            "r_ewar": round(_pearson([a["ewar"] for a, _ in nxt], ys) or float("nan"), 4),
            "r_bwar": round(_pearson([a["bwar"] for a, _ in nxt], ys) or float("nan"), 4),
            "reading": "team WAR in season y against actual wins in season y+1",
        }
        # THE POOLED NUMBER ABOVE IS SCALE-CONTAMINATED AND MUST NOT BE QUOTED
        # ALONE. A pair that straddles 2020 puts a 60-game season on one axis
        # and a 162-game season on the other, so the pair is not measuring
        # persistence at all: those 60 pairs correlate NEGATIVELY (about -0.53)
        # and drag the pooled r from roughly 0.59 down to 0.25. Report the
        # full-schedule subset beside it. This is the number to read.
        full = [(a, b) for a, b in nxt
                if a["games"] >= 140 and b["games"] >= 140]
        if len(full) >= 30:
            fy = [float(b["wins"]) for _, b in full]
            re_ = _pearson([a["ewar"] for a, _ in full], fy)
            rb_ = _pearson([a["bwar"] for a, _ in full], fy)
            out["next_season_wins_full_schedule_only"] = {
                "n": len(full),
                "n_dropped_short_season_pairs": len(nxt) - len(full),
                "r_ewar": round(re_, 4) if re_ is not None else None,
                "r_bwar": round(rb_, 4) if rb_ is not None else None,
                "delta": round(re_ - rb_, 4) if (re_ is not None and rb_ is not None) else None,
                "reading": "same test, restricted to pairs where BOTH seasons "
                           "ran a full schedule (>=140 team games). The pooled "
                           "row above mixes 60-game and 162-game seasons.",
            }
    per = {}
    for season in sorted({p["season"] for p in pts}):
        sub = [p for p in pts if p["season"] == season]
        if len(sub) < 5:
            continue
        ys = [float(p["wins"]) for p in sub]
        per[season] = {
            "n": len(sub),
            "r_ewar": round(_pearson([p["ewar"] for p in sub], ys) or float("nan"), 4),
            "r_bwar": round(_pearson([p["bwar"] for p in sub], ys) or float("nan"), 4),
            "mae0_ewar": round(sum(abs(y - (p["repl"] + p["ewar"]))
                                   for p, y in zip(sub, ys)) / len(sub), 3),
            "mae0_bwar": round(sum(abs(y - (p["repl"] + p["bwar"]))
                                   for p, y in zip(sub, ys)) / len(sub), 3),
        }
    out["by_season"] = per
    out["verdict"] = ("eWAR better" if out["ewar"]["r"] > out["bwar"]["r"]
                      else "bWAR better" if out["ewar"]["r"] < out["bwar"]["r"]
                      else "tie")
    return out


def gate_team_runs(model: dict, first: int, last: int) -> dict:
    """GATE 1b - score the components against what they actually CAUSE.

    Team wins are runs filtered through the Pythagorean relation, which adds
    sequencing and one-run-game luck that NEITHER series controls. That noise is
    shared, so gate 1 is fair, but it is also large enough to bury a component
    whose whole effect is a few runs a season. Fielding is exactly that
    component: swapping the entire league's fielding basis moves a team by a
    handful of runs, which is a fraction of a win, so gate 1 literally cannot
    resolve it. Runs scored and runs allowed can.

    Three regressions, eWAR and bWAR on IDENTICAL team-seasons:
      offense      (runs_bat + runs_br + runs_dp)  vs actual runs SCORED
      prevention   (fielding + pitching RAA)        vs actual runs ALLOWED
      total        (offense + prevention)           vs actual run DIFFERENTIAL

    SIGN: the components are runs-above-average, so more is better, while runs
    ALLOWED is lower-is-better. The prevention correlation is therefore expected
    to be NEGATIVE, and the comparison between the two series is on |r|. This is
    stated rather than hidden by flipping a sign, because a prevention r that
    came back positive would be a bug, not a result, and flipping would mask it.

    NOTE the offense arm is identical between the two series by construction:
    eWAR only replaces pitching and fielding, so runs_bat / runs_br / runs_dp are
    B-Ref's in both. It is reported anyway as a NULL CONTROL - if the offense
    arms ever differ, something has leaked across components.
    """
    stand = standings(range(first, last + 1))
    tot: dict[tuple[int, str], dict] = defaultdict(
        lambda: {"off": 0.0, "prev_e": 0.0, "prev_b": 0.0, "off_b": 0.0})
    for r in model["rows"]:
        if r["season"] < first or r["season"] > last:
            continue
        t = tot[(r["season"], r["team"])]
        off = _num(r.get("rbat")) + _num(r.get("rbr")) + _num(r.get("rdp"))
        t["off"] += off
        t["off_b"] += off
        t["prev_e"] += _num(r.get("rfield_ewar")) + _num(r.get("praa_ewar"))
        t["prev_b"] += _num(r.get("rfield_bref")) + _num(r.get("praa_bref"))

    pts = []
    for (season, team), v in sorted(tot.items()):
        rec = (stand.get(season) or {}).get(team)
        if not rec or rec.get("rs") is None or rec.get("ra") is None:
            continue
        pts.append({"season": season, "team": team,
                    "rs": float(rec["rs"]), "ra": float(rec["ra"]),
                    "rd": float(rec["rs"]) - float(rec["ra"]), **v})
    if len(pts) < 30:
        return {"n": len(pts),
                "note": "not enough cached standings with runs for this window"}

    def _arm(xkey, ykey):
        xs = [p[xkey] for p in pts]
        ys = [p[ykey] for p in pts]
        r = _pearson(xs, ys)
        a, b = _ols(xs, ys)
        mae = sum(abs(y - (a + b * x)) for x, y in zip(xs, ys)) / len(xs)
        return {"r": round(r, 4) if r is not None else None,
                "abs_r": round(abs(r), 4) if r is not None else None,
                "mae_fit": round(mae, 2), "slope": round(b, 4)}

    out = {
        "n_team_seasons": len(pts), "seasons": [first, last],
        "offense_vs_runs_scored": {
            "ewar": _arm("off", "rs"), "bwar": _arm("off_b", "rs"),
            "note": "NULL CONTROL: identical by construction; a difference is a leak",
        },
        "prevention_vs_runs_allowed": {
            "ewar": _arm("prev_e", "ra"), "bwar": _arm("prev_b", "ra"),
            "note": "r is expected NEGATIVE (runs above average vs runs allowed); "
                    "compare on abs_r",
        },
    }
    for p in pts:
        p["tot_e"] = p["off"] + p["prev_e"]
        p["tot_b"] = p["off_b"] + p["prev_b"]
    out["total_vs_run_differential"] = {
        "ewar": _arm("tot_e", "rd"), "bwar": _arm("tot_b", "rd"),
    }

    pe = out["prevention_vs_runs_allowed"]["ewar"]["abs_r"]
    pb = out["prevention_vs_runs_allowed"]["bwar"]["abs_r"]
    te = out["total_vs_run_differential"]["ewar"]["abs_r"]
    tb = out["total_vs_run_differential"]["bwar"]["abs_r"]
    off_leak = (out["offense_vs_runs_scored"]["ewar"]["r"]
                != out["offense_vs_runs_scored"]["bwar"]["r"])
    out["verdict"] = {
        "prevention_winner": ("ewar" if (pe or 0) > (pb or 0) else
                              "bwar" if (pb or 0) > (pe or 0) else "tie"),
        "total_winner": ("ewar" if (te or 0) > (tb or 0) else
                         "bwar" if (tb or 0) > (te or 0) else "tie"),
        "offense_control_clean": not off_leak,
    }
    return out


def gate_pitcher_persistence(model: dict, min_ip: float = 50.0) -> dict:
    """GATE 2 - year-over-year self-correlation of the PITCHING component,
    eWAR (FIP basis) vs bWAR (runs-allowed basis), on the same pitcher-seasons.
    FIP-based pitching should persist better; that is its entire case.

    Also runs the FORECAST version, which is the one that actually matters: does
    this year's FIP-priced value predict NEXT year's actual runs prevented
    better than this year's actual runs prevented does?
    """
    pairs = _persistence_pairs(model, min_ip)
    if len(pairs) < 30:
        return {"n_pairs": len(pairs), "note": "too few pairs to measure"}
    r_e = _pearson([p["e0"] for p in pairs], [p["e1"] for p in pairs])
    r_b = _pearson([p["b0"] for p in pairs], [p["b1"] for p in pairs])
    r_fore_e = _pearson([p["e0"] for p in pairs], [p["b1"] for p in pairs])
    r_fore_b = _pearson([p["b0"] for p in pairs], [p["b1"] for p in pairs])
    r_war_e = _pearson([p["ew0"] for p in pairs], [p["ew1"] for p in pairs])
    r_war_b = _pearson([p["bw0"] for p in pairs], [p["bw1"] for p in pairs])
    return {
        "n_pairs": len(pairs), "min_ip": min_ip,
        "units": "runs above average per 9 IP",
        "self_r_ewar_fip": round(r_e, 4), "self_r_bwar_ra": round(r_b, 4),
        "forecast_next_year_actual_runs": {
            "from_ewar_fip": round(r_fore_e, 4),
            "from_bwar_ra": round(r_fore_b, 4),
            "reading": "correlation of season-y value with season-(y+1) ACTUAL "
                       "runs above average (B-Ref runs-allowed basis)",
        },
        "season_war_self_r": {"ewar": round(r_war_e, 4), "bwar": round(r_war_b, 4)},
        "verdict": ("FIP persists better" if r_e > r_b else
                    "runs-allowed persists better" if r_e < r_b else "tie"),
    }


def _persistence_pairs(model: dict, min_ip: float = 50.0) -> list[dict]:
    """Consecutive pitcher-season pairs, both seasons over `min_ip` and fully
    FIP-priced, in runs above average per 9 IP on both bases."""
    agg: dict[tuple[int, int], dict] = defaultdict(lambda: {"ip": 0.0, "e": 0.0, "b": 0.0,
                                                            "ew": 0.0, "bw": 0.0, "cov": True})
    for r in model["rows"]:
        if r["side"] != "pit":
            continue
        if r["mid"] is None:
            continue
        a = agg[(r["mid"], r["season"])]
        a["ip"] += r["ip"]
        a["e"] += r["praa_ewar"] or 0.0
        a["b"] += r["praa_bref"] or 0.0
        a["ew"] += r["ewar"]
        a["bw"] += r["bwar"]
        if r.get("pitch_src") != "fip":
            a["cov"] = False
    pairs = []
    for (mid, season), a in agg.items():
        nxt = agg.get((mid, season + 1))
        if not nxt or a["ip"] < min_ip or nxt["ip"] < min_ip:
            continue
        if not a["cov"] or not nxt["cov"]:
            continue
        pairs.append({
            "e0": 9.0 * a["e"] / a["ip"], "e1": 9.0 * nxt["e"] / nxt["ip"],
            "b0": 9.0 * a["b"] / a["ip"], "b1": 9.0 * nxt["b"] / nxt["ip"],
            "ew0": a["ew"], "ew1": nxt["ew"], "bw0": a["bw"], "bw1": nxt["bw"],
            "season": season, "mid": mid,
        })
    return pairs


def team_wins_gap_ci(model: dict, first: int, last: int) -> dict | None:
    """LIBRARY_14: the paired interval on gate 1's gap, eWAR's r with team wins
    minus bWAR's, team-clustered (a franchise's seasons are drawn together)."""
    import numpy as np
    import gap_intervals as gi
    pts = _team_season_points(model, first, last)
    if not pts:
        return None
    e = np.array([p["ewar"] for p in pts], float)
    b = np.array([p["bwar"] for p in pts], float)
    w = np.array([p["wins"] for p in pts], float)

    def gaps(idx):
        re_, rb_ = gi.pearson(e[idx], w[idx]), gi.pearson(b[idx], w[idx])
        return {"r": None if re_ is None or rb_ is None else re_ - rb_}

    return gi.paired_cluster_interval(
        [_fold_team(p["team"]) for p in pts], gaps, seed=gi.SEED,
        cluster="team (franchise): a club's seasons are drawn together")


def persistence_gap_ci(model: dict, min_ip: float = 50.0) -> dict | None:
    """LIBRARY_14: the paired interval on gate 2's gap, the year-to-year r of
    FIP-based pitching minus that of runs-allowed pitching, player-clustered
    (a pitcher's season pairs are drawn together)."""
    import numpy as np
    import gap_intervals as gi
    pairs = _persistence_pairs(model, min_ip)
    if len(pairs) < 30:
        return None
    e0, e1 = (np.array([p[k] for p in pairs], float) for k in ("e0", "e1"))
    b0, b1 = (np.array([p[k] for p in pairs], float) for k in ("b0", "b1"))

    def gaps(idx):
        re_, rb_ = gi.pearson(e0[idx], e1[idx]), gi.pearson(b0[idx], b1[idx])
        return {"r": None if re_ is None or rb_ is None else re_ - rb_}

    return gi.paired_cluster_interval(
        [p["mid"] for p in pairs], gaps, seed=gi.SEED,
        cluster="player (mlbam): a pitcher's season pairs are drawn together")


def gate_coverage(model: dict) -> dict:
    """GATE 3 - how many player-seasons got a real Statcast fielding read vs a
    bWAR rfield fallback, by season and by position; and the pitching coverage."""
    fld = model["meta"]["fielding"]
    pit = model["meta"]["pitching"]
    by_season = {}
    for season, blk in sorted(fld["by_season"].items()):
        # the 0.777 league share is 1 - (pitcher innings + catcher innings);
        # WITHIN the seven positions Statcast covers, coverage is near total,
        # and that is the number that says whether the swap actually happened.
        oaa_inn = sum(v["inn"] for p, v in blk["by_pos"].items() if p in OAA_POSITIONS)
        oaa_cov = sum(v["inn_covered"] for p, v in blk["by_pos"].items()
                      if p in OAA_POSITIONS)
        by_season[season] = {
            "fielding_innings_share_covered": blk["share"],
            "share_within_oaa_positions": round(oaa_cov / oaa_inn, 4) if oaa_inn else 0.0,
            "n_player_seasons_with_defense": blk["n_player_seasons"],
            "n_non_pitcher_player_seasons": blk["n_position_player_seasons"],
            "n_with_statcast_read": blk["n_with_read"],
            "by_position": {p: {"inn": v["inn"], "share": v["share"],
                                "n": v["n"], "n_covered": v["n_covered"]}
                            for p, v in sorted(blk["by_pos"].items())},
        }
    src = defaultdict(lambda: defaultdict(int))
    for r in model["rows"]:
        if r["side"] == "bat":
            src[r["season"]]["bat_" + (r["field_src"] or "bref")] += 1
        else:
            src[r["season"]]["pit_" + (r.get("pitch_src") or "bref")] += 1
    return {
        "fielding": {
            "by_season": by_season,
            "k_inn": fld["k_inn"],
            "shrunk": fld["shrunk"],
            "structural_blind_spots": [
                "CATCHER: the Savant OAA leaderboard returns zero rows for C, so "
                "every catcher-season in eWAR carries B-Ref rfield unchanged",
                "PITCHER glove: not on the OAA board; falls back to rfield",
                "pre-2016: no Statcast OAA at all",
            ],
            # PROBED 2026-08-04 and REFUSED. The obvious repair for the catcher
            # hole is Savant's catcher-framing leaderboard, and it does respond:
            #   /leaderboard/catcher-framing?year=YYYY&team=&min=1&csv=true
            # returns 62 catchers with rv_tot = framing runs (verified internally:
            # the per-zone rv_11..rv_19 integers sum to rv_tot).
            # BUT the season parameter is INERT. year=2016, year=2019, year=2024,
            # year=2026, season=YYYY and startYear/endYear all return the SAME
            # payload, md5 b389177d5e, byte for byte, and the payload carries no
            # season stamp of its own - so there is no way to learn which season
            # it describes. Ingesting it would assign one undated snapshot's
            # framing runs to every season in the window, which is a fabricated
            # feature wearing a real column name. The catcher hole therefore
            # stays open and honest. Do not re-probe these spellings; if this is
            # revisited, the question to answer FIRST is where a season-resolved
            # framing source lives, not how to parse this one.
            # ANSWERED 2026-09-24/25 (final pass X05-02): /catcher_framing?year=Y
            # (no /leaderboard/ prefix) resolves by season (2019 and 2024 return
            # different payloads), and the catcher-blocking and catcher-throwing
            # boards stamp start_year on every row. savant_catcher.py reads the
            # last two for display on the Defense board. eWAR's catcher hole is
            # unchanged: putting any of them into eWAR is a model change.
            "catcher_framing_probe": {
                "date": "2026-08-04",
                "endpoint": "baseballsavant.mlb.com/leaderboard/catcher-framing",
                "reachable": True,
                "n_rows": 62,
                "runs_column": "rv_tot (validated: per-zone rv_* sum to it)",
                "blocker": "season parameter inert - year/season/startYear all "
                           "return one identical undated payload (md5 b389177d5e)",
                "decision": "NOT ingested; a single undated snapshot cannot be "
                            "assigned to ten seasons",
            },
        },
        "pitching": {
            "n_rows": pit["n_rows"], "n_fip_priced": pit["n_covered"],
            "ip_share_fip_priced": pit["ip_share"],
            "by_season": {s: {"n_rows": b["n_rows"], "n_covered": b["n_covered"],
                              "ip_share": b.get("ip_share"),
                              "lg_ra9": b.get("lg_ra9"), "lg_era": b.get("lg_era"),
                              "ra9_per_era_scale": b.get("ra9_per_era_scale"),
                              "cells": b.get("cells")}
                          for s, b in sorted(pit["by_season"].items())},
        },
        "row_sources_by_season": {s: dict(v) for s, v in sorted(src.items())},
    }


def face_validity(model: dict, n: int = 12) -> dict:
    """The named-player check. A WAR that moves the RIGHT players is checkable
    by a human in a way a correlation is not: the pitcher-seasons where bWAR and
    fWAR famously disagree should be exactly the ones eWAR moves, and in the
    fWAR direction."""
    pit: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"e": 0.0, "b": 0.0, "ip": 0.0, "name": ""})
    fld: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"e": 0.0, "b": 0.0, "pa": 0.0, "name": "", "cov": 0.0})
    for r in model["rows"]:
        if r["mid"] is None:
            continue
        k = (r["mid"], r["season"])
        if r["side"] == "pit":
            a = pit[k]
            a["e"] += r["ewar"]; a["b"] += r["bwar"]; a["ip"] += r["ip"]
            a["name"] = r["name"]
        else:
            a = fld[k]
            a["e"] += r["rfield_ewar"]; a["b"] += r["rfield_bref"]
            a["pa"] += r["pa"]; a["name"] = r["name"]
            a["cov"] = max(a["cov"], r["field_cov"] or 0.0)

    def _top(d, key, floor_key, floor):
        rows = [{"name": v["name"], "season": s, "delta": round(v["e"] - v["b"], 2),
                 "ewar": round(v["e"], 2), "bwar": round(v["b"], 2)}
                for (_m, s), v in d.items() if v[floor_key] >= floor]
        rows.sort(key=lambda r: -abs(r["delta"]))
        return rows[:key]

    fld_rows = [{"name": v["name"], "season": s,
                 "fielding_runs_ewar": round(v["e"], 1),
                 "rfield_bref": round(v["b"], 1),
                 "delta": round(v["e"] - v["b"], 1)}
                for (_m, s), v in fld.items() if v["pa"] >= 450 and v["cov"] >= 0.95]
    fld_rows.sort(key=lambda r: -r["fielding_runs_ewar"])
    return {
        "pitchers_moved_most": {
            "units": "season WAR, eWAR minus bWAR",
            "min_ip": 120,
            "rows": _top(pit, n, "ip", 120.0),
        },
        "best_fielders_by_ewar": {
            "units": "fielding runs, full-time (450+ PA) seasons with >=95% "
                     "Statcast coverage",
            "rows": fld_rows[:n],
        },
        "worst_fielders_by_ewar": {"rows": fld_rows[-n:][::-1]},
    }


def gate_league_sum(model: dict) -> dict:
    """The accounting gate: eWAR must sum to the league's wins above
    replacement, season by season."""
    out = {}
    worst = 0.0
    for season, blk in sorted(model["meta"]["by_season"].items()):
        out[season] = {
            "team_games": blk["team_games"],
            "target": blk["league_war_target"],
            "bwar_sum": blk["bwar_league_sum"],
            "ewar_sum_pre_rescale": blk["ewar_league_sum_pre_rescale"],
            "ewar_sum": blk["ewar_league_sum"],
            "replacement_scale": blk["replacement_scale"],
        }
        if blk["league_war_target"]:
            worst = max(worst, abs(blk["ewar_league_sum"] - blk["league_war_target"]))
    return {"by_season": out, "max_abs_deviation_from_target": round(worst, 3),
            "convention": (f"REPLACEMENT_WINS {REPLACEMENT_WINS} on a .294 baseline; "
                           f"league target = (0.5 - {REPLACEMENT_WINS}/162) x team-games")}


def _window_model(model: dict, first: int, last: int) -> dict:
    """Return a shallow copy of `model` carrying only seasons in [first, last].

    Every per-season block a gate reads gets filtered, not just `rows`:
    gate_league_sum reads meta.by_season, gate_coverage reads
    meta.fielding.by_season and meta.pitching.by_season. Season keys are ints
    in memory and strings once the payload has been through JSON, so both are
    accepted. If the model is already inside the window this is close to a
    no-op and the gates see exactly what they saw before.
    """
    def _in(k) -> bool:
        try:
            return first <= int(k) <= last
        except (TypeError, ValueError):
            return True

    def _filt(d):
        return {k: v for k, v in d.items() if _in(k)} if isinstance(d, dict) else d

    meta = dict(model["meta"])
    meta["seasons"] = [first, last]
    if isinstance(meta.get("by_season"), dict):
        meta["by_season"] = _filt(meta["by_season"])
    for comp in ("fielding", "pitching"):
        blk = meta.get(comp)
        if isinstance(blk, dict) and isinstance(blk.get("by_season"), dict):
            blk = dict(blk)
            blk["by_season"] = _filt(blk["by_season"])
            meta[comp] = blk
    out = dict(model)
    out["meta"] = meta
    out["rows"] = [r for r in model["rows"] if _in(r.get("season"))]
    return out


def evaluate(model: dict, model_unshrunk: dict | None = None,
             first: int | None = None, last: int | None = None,
             arms: dict | None = None) -> dict:
    """The three gates plus the accounting check -> data/ewar_eval.json.

    `arms` is {label: model} for the single-swap attribution builds.
    """
    lo, hi = model["meta"]["seasons"]
    first = int(first if first is not None else lo)
    # the last season is usually in progress; the gates need completed seasons
    last = int(last if last is not None else min(hi, _dt.date.today().year - 1))
    # WINDOW THE MODEL ONCE, then hand the SAME rows to every block.
    #
    # Until 2026-08-04 this line computed `last` and then passed it to
    # gate_team_wins and gate_team_runs ONLY. The other four blocks took the
    # unwindowed model, so the artifact declared eval_window [2016, 2025] while
    # persistence, coverage, accounting and face-validity all ran 2016-2026 on
    # a season three weeks old. It was not cosmetic: 148 of 1825 gate-2 pairs
    # (8.1%) had the in-progress 2026 as their y+1 target, at a mean 89.6 IP
    # against 98.9 in 2025, and accounting_league_sum reported a 2026 row with
    # only 3364 team-games inside a "max_abs_deviation_from_target 0.0" pass.
    # Excluding 2026 the persistence direction is unchanged (self-r 0.3619 vs
    # 0.1766, forecast 0.2574 vs 0.1766), so no verdict moves; what was wrong
    # was the artifact describing a population it did not measure.
    windowed = _window_model(model, first, last)
    ev = {
        "model": MODEL,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "eval_window": [first, last],
        "population": "every Baseball-Reference war_daily row in the window; "
                      "eWAR and bWAR are always measured on IDENTICAL rows; "
                      "EVERY block below is windowed to eval_window, including "
                      "persistence, coverage, accounting and face validity",
        "gate_1_team_wins": gate_team_wins(windowed, first, last),
        "gate_1b_team_runs": gate_team_runs(windowed, first, last),
        "gate_2_pitcher_persistence": gate_pitcher_persistence(windowed),
        "gate_3_coverage_identity": gate_coverage(windowed),
        "accounting_league_sum": gate_league_sum(windowed),
        "face_validity": face_validity(windowed),
    }
    # LIBRARY_14: each gate's paired interval sits beside the points it was
    # measured on, on the same windowed rows. Nothing above reads it.
    g1_ci = team_wins_gap_ci(windowed, first, last)
    if g1_ci is not None:
        ev["gate_1_team_wins"]["gap_ci_vs_bwar"] = g1_ci
    g2_ci = persistence_gap_ci(windowed)
    if g2_ci is not None:
        ev["gate_2_pitcher_persistence"]["gap_ci_vs_bwar_ra"] = g2_ci
    if arms:
        att = {"why": "the two component swaps run one at a time, so a gate "
                      "movement is attributable to a component and not to "
                      "'eWAR' as an undifferentiated whole. Same rows, same "
                      "replacement re-derivation, same window.",
               "bwar_baseline": {
                   "r": ev["gate_1_team_wins"]["bwar"]["r"],
                   "mae_zero_param": ev["gate_1_team_wins"]["bwar"]["mae_zero_param"],
                   "mae_fit": ev["gate_1_team_wins"]["bwar"]["mae_fit"],
                   "next_season_r": (ev["gate_1_team_wins"].get("next_season_wins")
                                     or {}).get("r_bwar"),
                   # the reference series the arms' by_season_* are read against
                   "by_season_r": {s: b.get("r_bwar") for s, b in
                                   sorted((ev["gate_1_team_wins"].get("by_season") or {}).items())},
                   "by_season_mae0": {s: b.get("mae0_bwar") for s, b in
                                      sorted((ev["gate_1_team_wins"].get("by_season") or {}).items())}}}
        for label, m in arms.items():
            g = gate_team_wins(m, first, last)
            att[label] = {"r": g["ewar"]["r"],
                          "mae_zero_param": g["ewar"]["mae_zero_param"],
                          "mae_fit": g["ewar"]["mae_fit"],
                          "next_season_r": (g.get("next_season_wins") or {}).get("r_ewar"),
                          # PER-SEASON, because the mechanism story is testable.
                          # The account for why the fielding swap loses is that
                          # Savant's fielding read is range-only while rfield also
                          # carries arm, framing and the rest. If that is the whole
                          # story, the loss should SHRINK in the seasons after
                          # Savant folded outfield arm into its fielding run value,
                          # and stay flat before. A flat profile across eras means
                          # the range-only account is incomplete and the blend
                          # weight should NOT be made era-aware on the strength of
                          # a story the seasons do not support.
                          "by_season_r": {s: b.get("r_ewar")
                                          for s, b in sorted((g.get("by_season") or {}).items())},
                          "by_season_mae0": {s: b.get("mae0_ewar")
                                             for s, b in sorted((g.get("by_season") or {}).items())}}
        att["both_swaps_shipped"] = {
            "r": ev["gate_1_team_wins"]["ewar"]["r"],
            "mae_zero_param": ev["gate_1_team_wins"]["ewar"]["mae_zero_param"],
            "mae_fit": ev["gate_1_team_wins"]["ewar"]["mae_fit"],
            "next_season_r": (ev["gate_1_team_wins"].get("next_season_wins")
                              or {}).get("r_ewar")}
        ev["attribution_gate_1"] = att
    if model_unshrunk is not None:
        ev["sensitivity_unshrunk_fielding"] = {
            "what": "identical build with the OAA reliability shrinkage OFF "
                    "(raw centred FRP instead of FRP x inn/(inn+k_inn))",
            "gate_1_team_wins": gate_team_wins(model_unshrunk, first, last),
            "accounting_league_sum": gate_league_sum(
                _window_model(model_unshrunk, first, last)),
        }
        # A CONTROL THAT CANNOT MOVE IS NOT A CONTROL. At the shipped
        # fielding_blend_w of 0.0 the only shrink-sensitive term is multiplied
        # by zero, so an unshrunk build is bit-identical to the shipped one and
        # this whole block was reproducing gate 1 to the last decimal while
        # claiming to vary something. The caller now pins the arm at w=1.0
        # (tools/build_ewar.py); assert the block is live rather than trusting
        # the caller, because the failure mode is silent and reads as a pass.
        _sh = ev["gate_1_team_wins"]["ewar"]
        _un = ev["sensitivity_unshrunk_fielding"]["gate_1_team_wins"]["ewar"]
        ev["sensitivity_unshrunk_fielding"]["degenerate"] = bool(_sh == _un)
        if _sh == _un:
            ev["sensitivity_unshrunk_fielding"]["what"] += (
                " -- DEGENERATE ON THIS RUN: identical to the shipped gate, so "
                "it varies nothing. Build the arm at fielding_blend_w=1.0 to "
                "make the shrinkage question answerable.")
    g1, g2 = ev["gate_1_team_wins"], ev["gate_2_pitcher_persistence"]
    passed = []
    failed = []
    if g1.get("n_team_seasons"):
        (passed if g1["ewar"]["r"] >= g1["bwar"]["r"] else failed).append(
            f"gate 1 team wins: r {g1['ewar']['r']} vs bWAR {g1['bwar']['r']}")
        (passed if g1["ewar"]["mae_zero_param"] <= g1["bwar"]["mae_zero_param"]
         else failed).append(
            f"gate 1 zero-param MAE: {g1['ewar']['mae_zero_param']} vs "
            f"bWAR {g1['bwar']['mae_zero_param']}")
    if g2.get("n_pairs", 0) >= 30:
        (passed if g2["self_r_ewar_fip"] >= g2["self_r_bwar_ra"] else failed).append(
            f"gate 2 persistence: r {g2['self_r_ewar_fip']} vs "
            f"bWAR {g2['self_r_bwar_ra']}")
        f = g2["forecast_next_year_actual_runs"]
        (passed if f["from_ewar_fip"] >= f["from_bwar_ra"] else failed).append(
            f"gate 2 forecast: r {f['from_ewar_fip']} vs bWAR {f['from_bwar_ra']}")
    ev["gates_passed"] = passed
    ev["gates_failed"] = failed
    ev["reading"] = _reading(ev)
    return ev


def _reading(ev: dict) -> dict:
    """The honest interpretation, written INTO the artifact so the numbers
    cannot be quoted without it."""
    g1 = ev.get("gate_1_team_wins") or {}
    g2 = ev.get("gate_2_pitcher_persistence") or {}
    att = ev.get("attribution_gate_1") or {}
    if not g1.get("n_team_seasons"):
        return {"verdict": "unmeasured"}
    e, b = g1["ewar"], g1["bwar"]
    fore = g2.get("forecast_next_year_actual_runs") or {}
    nxt = g1.get("next_season_wins") or {}
    nxf = g1.get("next_season_wins_full_schedule_only") or {}
    return {
        "verdict": "provisional - eWAR v2 (FIP pitching ONLY, the Statcast "
                   "fielding swap was measured and REMOVED) LOSES the "
                   "descriptive gate, WINS the pitcher persistence gate, and "
                   "is a NULL against bWAR on team forward-looking wins; it "
                   "serves as the site WAR by owner basis decision (2026-09-03), "
                   "which these gates neither support nor oppose on accuracy",
        "headline": (
            f"Gate 1 (team wins, {g1['n_team_seasons']} team-seasons): eWAR r "
            f"{e['r']} vs bWAR {b['r']}, zero-parameter MAE {e['mae_zero_param']} "
            f"vs {b['mae_zero_param']}. eWAR is a WORSE description of the wins "
            f"a team actually banked."),
        "why_that_was_expected": (
            "Gate 1 rewards DESCRIBING the season that happened. B-Ref prices "
            "pitchers on the runs they actually allowed, which is most of what "
            "decided the games, so a runs-allowed WAR is close to mechanically "
            "fitted to team wins. FIP deliberately throws away sequencing and "
            "balls in play, so it must fit worse in-sample. Any FIP-based WAR "
            "(fWAR included) loses this test to a runs-allowed WAR. Losing it "
            "is not evidence the pitching swap is wrong; it is the price the "
            "swap is supposed to pay."),
        "what_it_bought": (
            f"Gate 2: the FIP-priced pitching component self-correlates "
            f"{g2.get('self_r_ewar_fip')} year to year against "
            f"{g2.get('self_r_bwar_ra')} for the runs-allowed component "
            f"({g2.get('n_pairs')} pitcher-season pairs, same rows), and it "
            f"predicts NEXT year's actual runs above average better than this "
            f"year's actual runs above average does ({fore.get('from_ewar_fip')} "
            f"vs {fore.get('from_bwar_ra')}). That is a 2.1x persistence gain "
            f"and the entire case for a FIP basis."),
        "what_it_did_NOT_buy": (
            f"A TEAM-LEVEL forward-looking win. Measured 2026-08-04 and stated "
            f"here because the opposite was briefly claimed: on team WAR in "
            f"year y against wins in y+1, eWAR reads {nxt.get('r_ewar')} against "
            f"bWAR {nxt.get('r_bwar')}, and that gap is NOT real. Three "
            f"independent reasons. (1) SCALE CONTAMINATION: "
            f"{nxf.get('n_dropped_short_season_pairs')} of {nxt.get('n')} pairs "
            f"straddle the 60-game 2020 season and correlate NEGATIVELY, "
            f"dragging the pooled r down; on full-schedule pairs only "
            f"(n {nxf.get('n')}) it is {nxf.get('r_ewar')} vs {nxf.get('r_bwar')}, "
            f"a delta of {nxf.get('delta')}. (2) A zero-information control that "
            f"SHUFFLES the per-team eWAR-minus-bWAR delta across teams produces "
            f"an absolute delta at least as large 82.3% of the time, and beats "
            f"bWAR outright in 27.3% of shuffles. (3) Per year-pair, eWAR wins "
            f"4 of 9 and LOSES the four most recent; the pooled edge is carried "
            f"by 2016->2017 (+0.176) and the COVID pair 2020->2021 (+0.119). "
            f"The pitching component's forward case is at the PITCHER level "
            f"(gate 2), where it is large and survives controls. It does not "
            f"survive aggregation to the team."),
        "the_component_that_was_removed": (
            "THE STATCAST FIELDING SWAP IS NOT IN THE v2 BUILD (shipped "
            "fielding_blend_w = 0.0, so eWAR carries B-Ref rfield unchanged). "
            "This block is the COUNTERFACTUAL that removed it, not a "
            "description of what ships: the fielding_swap_only arm is built at "
            "fielding_blend_w=1.0 on purpose so it answers 'what would the swap "
            "do', which is why it still appears below. "
            "The ATTRIBUTION arms separate the two swaps. The FIP swap costs "
            f"same-season r ({att.get('pitching_swap_only', {}).get('r')} vs "
            f"{b['r']}) and BUYS next-season signal "
            f"({att.get('pitching_swap_only', {}).get('next_season_r')} vs "
            f"{att.get('bwar_baseline', {}).get('next_season_r')}). The Statcast "
            "fielding swap loses BOTH: same-season "
            f"{att.get('fielding_swap_only', {}).get('r')} and next-season "
            f"{att.get('fielding_swap_only', {}).get('next_season_r')}. That is a "
            "real finding with a mechanical cause: Statcast OAA is a RANGE "
            "metric. It carries no outfield or infield ARM value, no catcher "
            "framing or blocking, no first-base scoops, no double-play pivot. "
            "B-Ref rfield does carry those. Swapping OAA in for rfield is "
            "therefore not 'a better defensive metric for the same quantity', "
            "it is a BETTER metric for a NARROWER quantity, and the value it "
            "drops is real value. data/savant_arm.json exists but is arm "
            "STRENGTH in mph from 2020 on, not runs, so it cannot close the gap "
            "without a model that does not exist yet."),
        "what_would_change_the_verdict": [
            "an arm-value and catcher-framing run model, so the fielding swap "
            "covers the same quantity rfield does instead of a subset",
            "CLOSED 2026-08-04, do NOT re-run: a BLEND of OAA and rfield "
            "rather than a replacement was built and swept. w = 0.00 / 0.25 / "
            "0.50 / 0.75 / 1.00 gives a forward-leg delta against bWAR of "
            "+0.0006 / -0.0019 / -0.0057 / -0.0108 / -0.0173 on full-schedule "
            "pairs (and +0.0043 / +0.0009 / -0.0029 / -0.0073 / -0.0122 on the "
            "contaminated pooled set). MONOTONE DECREASING IN w ON BOTH "
            "BASES, so the 2020 contamination does not drive the ordering and "
            "no positive weight pays for itself. The blend is now the axis the "
            "decision was made on, not a candidate: w=0.0 IS v2. Re-open only "
            "if an arm-value or catcher-framing run model lands, which would "
            "change what the Statcast read MEASURES rather than how it is "
            "weighted",
            "gate 1 re-run against team RUNS ALLOWED and RUNS SCORED separately "
            "instead of wins, which separates component accuracy from the "
            "Pythagorean noise both series inherit",
        ],
        "safe_to_use_today": (
            "The pitching component. It reproduces the known bWAR/fWAR "
            "divergences by name (Aaron Nola 2018 9.69 -> 6.15, Mike Minor 2019 "
            "7.99 -> 4.68, both toward their published fWAR), it persists 2.1x "
            "better, and it forecasts next-year run prevention better than "
            "actual run prevention does. Since 2026-09-03 the whole site reads it "
            "through war_source (owner basis decision). v2 already "
            "took the second of the two exits named here: the Statcast fielding "
            "swap was DROPPED (w=0.0) rather than repaired, so what remains is "
            "a one-component model. Two consumer gates have since been measured "
            "and neither supports a swap on accuracy grounds: the eFV first-6yr "
            "label swap (lane R3a) and fa_backtest Gate 1 (lane R3b). The flip "
            "is a basis decision made with that record in view."),
    }
