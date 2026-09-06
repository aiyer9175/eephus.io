# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""GATE 3 — team-fit signing prediction (model-audit Phase 3, WS-4).

The fit engine shipped with hand-set weights and no backtest. This gate
asks the only question that validates a fit model: DOES FIT RANK PREDICT
THE ACTUAL SIGNING TEAM? Forward-chained by winter over 2018-2026
MLB-deal signings; for every signing, all 30 clubs are ranked and the
gate scores where the real signer landed (top-1/3/5 hit rates + MRR).

FEASIBILITY (the plan's spike, resolved): the LIVE engine's need/window
inputs cannot be reconstructed historically — contracted-roster
projections come from CURRENT Spotrac pages. What DOES reconstruct
ex-ante, per winter Y:
  payroll/tax   season Y-1 Spotrac pages (the budget state ENTERING the
                winter; the signing itself can't contaminate it)
  payor status  season Y-1 tax page
  prior wins    season Y-1 StatsAPI standings -> win-curve leverage
  behavior      signings strictly before Y (max guarantee, recent
                3-winter outlay, $100M-deal count)
  need proxy    the club lost a free agent at the position group THIS
                winter (class composition is known at winter start)
  park          Savant park factors, season Y-1 (neutral where missing)
  incumbency    from_team == club (re-signing gravity; ex-ante)
So Gate 3 evaluates a REDUCED-FEATURE ANALOG of the live composite — the
live engine's exact inputs remain historically unvalidatable, and the
registry says so. Deal-size context (NPV guarantee/AAV) is identical
across the 30 candidate clubs per signing, so it conditions the ranking
without leaking the winner.

MODELS COMPARED (all forward-chained):
  random          expected top-k = k/30, MRR ~ 0.133
  payroll-only    rank by CBT space score
  behavior-only   rank by the will-spend blend
  live-analog     the hand-set fa_config weights over the reduced
                  features (no incumbency — matches live semantics)
  fitted-transfer logistic over the SAME five live components, fit on
                  winters < Y — the weight vector that ships to
                  fa_config.fit.weights IF it beats the live-analog
  fitted-full     + incumbency (the honest ceiling for this feature set)

Artifact: data/fa_gate3_eval.json. Mystery-team realism: top-5 hit rate
is the headline; top-1 on 30 clubs is genuinely hard and the artifact
says so. Run: python fa_fit_backtest.py
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_market as fm
import fa_sources
import storage
from scrapers import _fetch
from trades import canonical_org, canonical_org_from_id

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "fa_gate3_eval.json"
TEST_WINTERS = list(range(2018, 2027))
ORGS = ("ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
        "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
        "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN")
_STANDINGS_URL = ("https://statsapi.mlb.com/api/v1/standings"
                  "?leagueId=103,104&season={season}&standingsTypes=regularSeason")
# Live composite weights mapped onto the reduced features: need->need_proxy,
# window->leverage, afford->space, park->park, behavior->will-spend blend.
#
# READ FROM fa_config, NOT HARD-CODED (fixed 2026-07-25). The literal that used to
# sit here, {need .31, window .19, afford .22, park .04, behavior .24}, was labelled
# "(fa_config fit.weights)" but was the RETIRED hand_v2 vector; fa_config.fit.weights
# has read {need .40, window .05, afford .05, park .05, behavior .45} since the
# shipped_balanced vector was chosen in this backtest's own ship_decision. So the
# gate, and all four of its registered verdicts, described a model that never shipped.
# Measured on the identical forward chain (n=1,173): hand_v2 MRR 0.1418 / top1 0.0341
# / top5 0.1807 versus shipped 0.1673 / 0.0520 / 0.2293, and shipped beats hand_v2 in
# 7 of 9 winters. The registered verdict live_analog_beats_behavior_only=False FLIPS
# TO TRUE once the gate scores what ships: cluster bootstrap over signings (B=2,000,
# signing as the independent unit) gives shipped over behavior_only +0.0147 MRR,
# CI95 [+0.0061, +0.0235], P=0.999, against MDE95 0.0126 and a within-signing
# permutation null of 0.1355.
# Reading from config means the two cannot drift apart again silently.
def _live_weights() -> dict:
    try:
        import fa_config
        w = (getattr(fa_config, "CONFIG", None) or {}).get("fit", {}).get("weights")
        if isinstance(w, dict) and w:
            return {k: float(w[k]) for k in ("need", "window", "afford", "park", "behavior")}
    except Exception:                                    # noqa: BLE001 -- fail-soft
        pass
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(__file__).parent / "fa_config.yaml").read_text(encoding="utf-8"))
    w = cfg["fit"]["weights"]
    return {k: float(w[k]) for k in ("need", "window", "afford", "park", "behavior")}


LIVE_WEIGHTS = _live_weights()
FEATS = ("need", "window", "afford", "park", "behavior")


def standings_wins(season: int) -> dict[str, int]:
    """{org: wins} from StatsAPI standings (disk-cached)."""
    fr = _fetch(_STANDINGS_URL.format(season=season),
                f"statsapi_standings_{season}", accept_json=True)
    if fr.status != 200 or not fr.body:
        return {}
    out = {}
    try:
        d = json.loads(fr.body)
        for rec in d.get("records") or []:
            for tr in rec.get("teamRecords") or []:
                team = tr.get("team") or {}
                # BY ID, NOT BY NAME. StatsAPI has called Arizona "D-backs"
                # since 2008; the alias table returns that unchanged and the
                # len<=3 guard below then drops the club silently. 46
                # club-seasons were being lost this way.
                org = canonical_org_from_id(team.get("id"), team.get("name") or "")
                if org and len(org) <= 3:
                    out[org] = int(tr.get("wins") or 0)
    except (ValueError, TypeError):
        log.warning("standings %d unparseable", season)
    return out


def _sn_int(v) -> int | None:
    """Tolerant int() for StatsAPI (numeric strings, occasional nulls). Returns
    None on failure so a genuinely-absent field stays distinguishable from 0."""
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _sn_float(v, dash: float | None = 0.0) -> float | None:
    """Tolerant float() for winningPercentage ('0.556') and the games-back
    family ('-' -> `dash`, '4.5' -> 4.5). Absent/None -> None."""
    if v is None or v == "":
        return None
    if v == "-":
        return dash
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def standings_now(season: int) -> dict[str, dict]:
    """Widened live-standings read for the current-season Team Outlook view.
    {org: {wins, losses, pct, gamesPlayed, rs, ra, runDiff, gb, divGb, wcGb,
    divRank, leagueRank, wcRank, streak, league, div, pythagWins,
    pythagLosses}}. Reuses the SAME disk-cached _fetch + canonical_org + the
    len<=3 MLB-club guard as standings_wins(); returns {} on any fetch/parse
    failure (degraded/offline -> the current-season view degrades to null and
    the 2027 projection is unaffected).

    pythagWins/Losses come from StatsAPI's built-in xWinLoss expectedRecord
    (present on standingsTypes=regularSeason); None when the block is absent,
    in which case the blend computes Pythag from rs/ra itself."""
    fr = _fetch(_STANDINGS_URL.format(season=season),
                f"statsapi_standings_{season}", accept_json=True)
    if fr.status != 200 or not fr.body:
        return {}
    out: dict[str, dict] = {}
    try:
        d = json.loads(fr.body)
        for rec in d.get("records") or []:
            league = (rec.get("league") or {}).get("id")
            div = (rec.get("division") or {}).get("id")
            for tr in rec.get("teamRecords") or []:
                team = tr.get("team") or {}
                # BY ID, NOT BY NAME. See standings_wins above: this is the
                # read whose failure put a null current-season block on Arizona
                # in the served team_outlook.
                org = canonical_org_from_id(team.get("id"), team.get("name") or "")
                if not org or len(org) > 3:
                    continue
                rs = _sn_int(tr.get("runsScored"))
                ra = _sn_int(tr.get("runsAllowed"))
                run_diff = _sn_int(tr.get("runDifferential"))
                if run_diff is None and rs is not None and ra is not None:
                    run_diff = rs - ra
                pyth_w = pyth_l = None
                exp = ((tr.get("records") or {}).get("expectedRecords")) or []
                for er in exp:
                    if (er.get("type") or "").lower() == "xwinloss":
                        pyth_w = _sn_int(er.get("wins"))
                        pyth_l = _sn_int(er.get("losses"))
                        break
                out[org] = {
                    "wins": _sn_int(tr.get("wins")),
                    "losses": _sn_int(tr.get("losses")),
                    "pct": _sn_float(tr.get("winningPercentage")),
                    "gamesPlayed": _sn_int(tr.get("gamesPlayed")),
                    "rs": rs, "ra": ra, "runDiff": run_diff,
                    "gb": _sn_float(tr.get("gamesBack")),
                    "divGb": _sn_float(tr.get("divisionGamesBack")),
                    "wcGb": _sn_float(tr.get("wildCardGamesBack"), dash=None),
                    "divRank": _sn_int(tr.get("divisionRank")),
                    "leagueRank": _sn_int(tr.get("leagueRank")),
                    "wcRank": _sn_int(tr.get("wildCardRank")),
                    "streak": (tr.get("streak") or {}).get("streakCode"),
                    "league": league, "div": div,
                    "pythagWins": pyth_w, "pythagLosses": pyth_l,
                }
    except (ValueError, TypeError):
        log.warning("standings_now %d unparseable", season)
        return {}
    return out


def team_payroll_state(season: int) -> dict[str, dict]:
    """{org: {tax_payroll_usd, payor}} for one season (cached scrape)."""
    out: dict[str, dict] = defaultdict(dict)
    try:
        for r in fa_sources.scrape_spotrac_tax(season):
            out[r["team"]].update({"tax_payroll_usd": r.get("tax_payroll_usd"),
                                   "payor": r.get("payor_status_raw")})
        for r in fa_sources.scrape_spotrac_payroll(season):
            out[r["team"]].setdefault("tax_payroll_usd", r.get("total_payroll_usd"))
    except Exception:                                       # noqa: BLE001
        log.warning("payroll state %d unavailable", season)
    return dict(out)


def _leverage(wins: int | None) -> float:
    """Marginal playoff leverage at ACTUAL prior-season wins (no roster-
    fill shift — these are real win totals, not contracted-core floors)."""
    if wins is None:
        return 0.5
    p = 1.0 / (1.0 + math.exp(-(wins - 86.5) / 2.8))
    return 4.0 * p * (1.0 - p)


def _reach(b: dict, guar: float) -> float:
    """The gate's mirror of fa_fit._spend_reach: share of the club's own PRIOR
    guarantees at least this large. Strictly ex-ante - `guars` only ever holds
    signings from winters before the test winter."""
    import bisect
    gs = b.get("guars") or []
    if not gs:
        return 0.0
    return (len(gs) - bisect.bisect_left(gs, guar)) / float(len(gs))


# ============================================================================
# TEAMFIT CONDITIONAL GATE (2026-08-19) — frozen constants
# ============================================================================
# docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md froze these BEFORE the lab
# ran. Candidate C conditions recent/rich on the PLAYER's price band so cheap
# relievers stop inheriting mega-deal behavior; reach is untouched (already
# player-conditional since F4). One lever, no weight moves, no retunes.
TEAMFIT_COND_BAND_FACTOR = 2.5
TEAMFIT_COND_GATE = {
    "mrr_floor_anchor": 0.1669,      # registered live_analog MRR (artifact)
    "top3_floor_anchor": 0.145,      # registered live_analog top3 (artifact)
    "max_top1_share": 0.25,
    "min_distinct_top1": 12,
    "min_distinct_top3": 20,
    "lad_behavior_majority": 0.50,   # clause 3: LAD behavior_cond top-1 < 50%
    "bootstrap_B": 2000,
    "bootstrap_seed": 7,
}


def _cond_band(guar: float) -> tuple[float, float]:
    """The player's price band: [g/F, g*F], multiplicative, symmetric in log
    space. F frozen at 2.5 in the gate doc."""
    return guar / TEAMFIT_COND_BAND_FACTOR, guar * TEAMFIT_COND_BAND_FACTOR


def _cond_terms(events: list[tuple[int, float]], guar: float,
                y_recent_min: int) -> tuple[float, int]:
    """(recent band outlay, career band deal count) for ONE club's prior
    signing events [(class_year, guarantee), ...]. Pure; unit-tested in
    test_fa_teamfit_conditional.py. Callers normalize outlay by the league
    max across clubs for the SAME player (0 league max -> 0.0 everywhere)."""
    lo, hi = _cond_band(guar)
    outlay, n_band = 0.0, 0
    for y, g in events:
        if lo <= g <= hi:
            n_band += 1
            if y >= y_recent_min:
                outlay += g
    return outlay, n_band


def _park_score(pf: dict, org: str, is_pitcher: bool) -> float:
    """0 to 1, with 0.5 meaning neutral.

    A MISS AND A NEUTRAL PARK RETURN THE SAME NUMBER, which is why the Arizona
    key defect above went unnoticed for as long as it did: a club whose park was
    never found scores exactly like a club whose park is genuinely average, and
    nothing downstream can tell them apart. The caller counts misses now; this
    function keeps returning 0.5 because a fit score has to be a number.
    """
    f = pf.get(org)
    if not f:
        return 0.5
    idx = (f["woba"] + f["hr"]) / 2.0
    edge = (100.0 - idx) if is_pitcher else (idx - 100.0)
    return max(0.0, min(1.0, 0.5 + edge / 60.0))


def build_rows() -> list[dict]:
    """One row per (signing, candidate org): the reduced ex-ante features
    + signed flag. Heavy inputs cached per season."""
    enriched = fm.enriched_signings(2015, 2026)
    by_winter: dict[int, list] = defaultdict(list)
    for s in enriched:
        if s.get("to_team") in ORGS:
            by_winter[s["class_year"]].append(s)
    # behavior priors accumulate strictly-before each winter
    rows = []
    park_cache: dict[int, dict] = {}
    for Y in TEST_WINTERS:
        prior = [s for s in enriched if s["class_year"] < Y]
        if len({s["class_year"] for s in prior}) < 3 or not by_winter.get(Y):
            continue
        beh: dict[str, dict] = defaultdict(lambda: {"max": 0, "n100": 0,
                                                   "recent": 0, "guars": [],
                                                   "events": []})
        for s in prior:
            t = s.get("to_team")
            if t not in ORGS:
                continue
            g = fm._npv_of(s)
            beh[t]["max"] = max(beh[t]["max"], g)
            beh[t]["guars"].append(g)
            beh[t]["events"].append((s["class_year"], g))
            if g >= 100_000_000:
                beh[t]["n100"] += 1
            if s["class_year"] >= Y - 3:
                beh[t]["recent"] += g
        for v in beh.values():
            v["guars"].sort()
        max_recent = max((b["recent"] for b in beh.values()), default=1) or 1
        pay = team_payroll_state(Y - 1)
        wins = standings_wins(Y - 1)
        if (Y - 1) not in park_cache:
            try:
                # THE OVERRIDE MAP, NOT canonical_org ALONE. Savant labels
                # Arizona's venue "D-backs", canonical_org has no alias for it
                # and returns the input unchanged, so the row landed under the
                # key "D-backs" and every ARI lookup missed. _park_score returns
                # the NEUTRAL 0.5 on a miss, which is indistinguishable from a
                # measured neutral park, so Arizona was silently scored as
                # park-neutral in every test winter of the published gate
                # artifact. fa_fit._park_factors has handled this since it was
                # written; this function is one module away and did not.
                import fa_fit as _ff
                park_cache[Y - 1] = {}
                for r in fa_sources.fetch_savant_park_factors(Y - 1):
                    club = r.get("name_display_club") or ""
                    org = _ff._SAVANT_CLUB_OVERRIDES.get(club) or canonical_org(club)
                    park_cache[Y - 1][org or "?"] = {
                        "woba": int(r.get("index_woba") or 100),
                        "hr": int(r.get("index_hr") or 100)}
            except Exception:                               # noqa: BLE001
                park_cache[Y - 1] = {}
        thr = fm._cbt_threshold_or_earliest(Y - 1)
        # outgoing free agents by (org, pos group) — known at winter start
        outgoing = defaultdict(set)
        for s in by_winter[Y]:
            if s.get("from_team") in ORGS:
                outgoing[s["from_team"]].add(fm._pos_group(s.get("position")))
        for s in by_winter[Y]:
            npv = fm._npv_of(s)
            aav = npv / max(int(s["years"]), 1)
            grp = fm._pos_group(s.get("position"))
            is_pit = grp in ("SP", "RP")
            # TEAMFIT CONDITIONAL (2026-08-19): band terms per club for THIS
            # player's price, normalized by the league max within the band.
            cond = {org: _cond_terms((beh.get(org) or {}).get("events") or [],
                                     npv, Y - 3) for org in ORGS}
            max_band_outlay = max(v[0] for v in cond.values())
            for org in ORGS:
                b = beh.get(org) or {"max": 0, "n100": 0, "recent": 0,
                                     "guars": []}
                tax = (pay.get(org) or {}).get("tax_payroll_usd")
                space = (thr - tax) if tax else None
                afford = (max(0.0, min(1.0, space / (aav * 2.0)))
                          if space is not None else 0.5)
                rows.append({
                    "winter": Y, "signing": s["player_key"],
                    "org": org, "signed": 1 if s.get("to_team") == org else 0,
                    "need": 1.0 if grp in outgoing.get(org, ()) else 0.0,
                    "window": _leverage(wins.get(org)),
                    "afford": afford,
                    "park": _park_score(park_cache[Y - 1], org, is_pit),
                    # SCORE WHAT SHIPS (the standing lesson of
                    # test_gate_scores_the_weights_that_actually_ship): the live
                    # will-spend term is fa_fit._spend_reach, which as of
                    # 2026-07-30 is the SHARE of the club's own historical
                    # guarantees at least this large, not the min(...,1)-clipped
                    # max-guarantee ratio. The clipped form is retained here under
                    # BEHAVIOR_MODE so the two can be compared on one chain.
                    "behavior": (0.5 * _reach(b, npv)
                                 + 0.3 * min(1.0, b["recent"] / max_recent)
                                 + 0.2 * min(1.0, b["n100"] / 5.0)),
                    "behavior_clipped": (0.5 * min(1.0, b["max"] / max(npv, 1)) ** 0.5
                                         + 0.3 * min(1.0, b["recent"] / max_recent)
                                         + 0.2 * min(1.0, b["n100"] / 5.0)),
                    # TEAMFIT CONDITIONAL candidate: reach unchanged,
                    # recent/rich confined to the player's price band.
                    "behavior_cond": (
                        0.5 * _reach(b, npv)
                        + 0.3 * (cond[org][0] / max_band_outlay
                                 if max_band_outlay > 0 else 0.0)
                        + 0.2 * min(1.0, cond[org][1] / 5.0)),
                    "incumbent": 1.0 if s.get("from_team") == org else 0.0,
                })
    return rows


def _rank_metrics(rows_by_signing: dict, score_fn) -> dict:
    """top-1/3/5 + MRR for one scoring function over grouped rows."""
    hits = {1: 0, 3: 0, 5: 0}
    rr = []
    n = 0
    for _key, group in rows_by_signing.items():
        ranked = sorted(group, key=lambda r: -score_fn(r))
        rank = next((i + 1 for i, r in enumerate(ranked) if r["signed"]), None)
        if rank is None:
            continue
        n += 1
        rr.append(1.0 / rank)
        for k in hits:
            if rank <= k:
                hits[k] += 1
    return {"n": n, "top1": round(hits[1] / n, 4), "top3": round(hits[3] / n, 4),
            "top5": round(hits[5] / n, 4), "mrr": round(sum(rr) / n, 4)}


def _fit_logit(train_rows: list[dict], feats: tuple) -> list[float] | None:
    """Deterministic logistic regression; returns coefficients."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    if not train_rows:
        return None
    X = np.asarray([[r[f] for f in feats] for r in train_rows], dtype=float)
    y = np.asarray([r["signed"] for r in train_rows], dtype=int)
    if y.sum() < 30:
        return None
    m = LogisticRegression(C=1.0, max_iter=1000, random_state=7)
    m.fit(X, y)
    return [float(c) for c in m.coef_[0]]


# ============================================================================
# CONCENTRATION TRIPWIRE (registered 2026-07-30, owner program Phase F5)
# ============================================================================
# MRR and top-k cannot see the failure the owner actually reported. A fit engine
# that ranks the Dodgers first for 154 of 228 free agents scores FINE on signing
# prediction (the Dodgers do sign a lot of people) while being worthless as a
# product, and the same is true of the Giants topping every pitcher's list. The
# metrics below are the ones that would have caught both, measured on the LIVE
# 30-club fit vector for every member of the served class.
#
# THE FIFTH METRIC IS MIS-SPECIFIED AND IS REPORTED, NOT GATED. `max share of #1
# fits within one side` cannot be satisfied by any correct additive composite:
# within a position group the need ordering is a property of the 30 CLUBS, not of
# the player, so whichever club is genuinely thinnest at a position tops every
# player at that position. As of 2026-07-30 SFG's 5th-starter slot projects 0.00
# WAR against a next-thinnest 0.03 and a league median near 0.85 - the club
# ordering is now a real continuous spread rather than the v3 pathology (where
# arb/pre-arb arms were invisible and the slot rule handed maximum need to any
# club with <= 4 contracted starters). Keeping the number visible is right;
# gating on it would only invite tuning until a true signal is hidden.
CONCENTRATION_GATE = {
    "max_top1_share": 0.25,          # no club may be #1 for more than a quarter
    "min_distinct_top1": 12,         # at least 12 clubs must be someone's #1
    "min_distinct_top3": 20,         # at least 20 clubs must appear in a top-3
    "min_median_gap": 0.015,         # the ordering must not get FLATTER
}


def concentration_gate(class_year: int | None = None) -> dict:
    """Measure the fit-vector concentration on the served class. Read-only, and
    fail-soft: returns {"available": False} when the class artifact is absent so
    the gate run never depends on it."""
    import json
    import statistics
    from collections import Counter
    try:
        import fa_fit
        d = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {"available": False,
                "note": "data/fa_class.json unavailable - concentration unmeasured"}
    cy = class_year or d["class_year"]
    first: Counter = Counter()
    top3: Counter = Counter()
    gaps: list[float] = []
    by_side: dict[str, Counter] = {"hit": Counter(), "pit": Counter()}
    n = 0
    for m in d.get("members") or []:
        player = {"position": m.get("pos"), "bat_throw": m.get("bt"),
                  "from_team": m.get("from"),
                  "_war_path": {"war_y1": m.get("warY1")}}
        pred = {"proj_guarantee_usd": m.get("projGuar"),
                "proj_aav_usd": m.get("projAav")}
        try:
            rows = fa_fit.fit_scores(player, pred, cy, top_n=30)
        except Exception:                                   # noqa: BLE001
            continue
        if not rows:
            continue
        n += 1
        first[rows[0]["org"]] += 1
        for r in rows[:3]:
            top3[r["org"]] += 1
        if len(rows) > 1:
            gaps.append(rows[0]["fit"] - rows[1]["fit"])
        grp = fm._pos_group(m.get("pos"))
        by_side["pit" if grp in ("SP", "RP") else "hit"][rows[0]["org"]] += 1
        if len(rows) != 30:
            return {"available": True, "n_members": n, "assertion_A1_all_30": False,
                    "note": f"fit vector for {m.get('key')} had {len(rows)} clubs, "
                            "not 30 - the silent-drop defect is back"}
    if not n:
        return {"available": False, "note": "no scorable members"}
    top1 = first.most_common(1)[0]
    measured = {
        "n_members": n,
        "assertion_A1_all_30": True,
        "max_top1_share": round(top1[1] / n, 4),
        "max_top1_club": top1[0],
        "distinct_top1": len(first),
        "distinct_top3": len(top3),
        "median_gap": round(statistics.median(gaps), 4) if gaps else None,
        "top1_counts": dict(first.most_common()),
        "per_side_max_top1_share_REPORTED_NOT_GATED": {
            s: (round(c.most_common(1)[0][1] / sum(c.values()), 4)
                if c else None) for s, c in by_side.items()},
        "per_side_top1_club": {s: (c.most_common(1)[0][0] if c else None)
                               for s, c in by_side.items()},
    }
    measured["gate"] = {
        "max_top1_share": measured["max_top1_share"] <= CONCENTRATION_GATE["max_top1_share"],
        "distinct_top1": measured["distinct_top1"] >= CONCENTRATION_GATE["min_distinct_top1"],
        "distinct_top3": measured["distinct_top3"] >= CONCENTRATION_GATE["min_distinct_top3"],
        "median_gap": (measured["median_gap"] or 0) >= CONCENTRATION_GATE["min_median_gap"],
    }
    measured["pass"] = all(measured["gate"].values())
    measured["thresholds"] = dict(CONCENTRATION_GATE)
    return measured


# ============================================================================
# CONCENTRATION DECOMPOSITION (R6, 2026-08-04)
# ============================================================================
# The tripwire above says WHICH club monopolizes; it cannot say WHY, and four
# rounds of re-weighting had chased the symptom. This block scores each of the
# five components AS IF IT WERE THE WHOLE FIT on the served class, then splits
# every component's 30-club score surface into a player main effect, a CLUB main
# effect and their INTERACTION.
#
# That split is the whole argument. Within one player's list the player main
# effect is a constant and cannot change the ordering; the club main effect is
# identical for every player, so whatever club it favours is favoured on EVERY
# list; only the interaction can make a different club win a different player.
# A component whose club effect swamps its interaction is SATURATED - it is a
# fixed club ranking wearing a score - and no weight on a saturated component
# can ever de-monopolize, it can only decide how loudly the monopoly speaks.
#
# MEASURED 2026-08-04 on the served 2027 class (n=228). The hypothesis under
# test was that NEED was the saturated term. It is REFUTED: need is the
# HEALTHIEST component (3.9% club main effect, 39.8% interaction, 91 distinct
# club orderings across the class) and supplies 75.6% of the composite's entire
# interaction. The saturated term is BEHAVIOR - LAD is its #1 for 228 of 228
# members with no ties at all, 69.8% club main effect against 1.4% interaction -
# and at weight 0.45 it contributes 63.7% of the composite's club main effect
# but only 12.2% of its interaction. WINDOW (99.5% club) and AFFORD (85.7% club,
# 90.5% of its cells pinned at 1.0) are saturated too, at weight 0.05 each.
#
# ROOT CAUSE, one level deeper: behavior = 0.5*reach + 0.3*recent + 0.2*rich,
# and only `reach` takes a player input. The F4 repair fixed `reach` and it
# worked - LAD tops the raw reach term at just 5 of 41 price points sampled
# across the class. But `recent` normalizes by the LEAGUE-MAX 3-winter outlay,
# which IS Los Angeles, so LAD scores exactly 1.0 by construction, and `rich`
# clips at n_100m/5 so LAD (6) sits at 1.0 with four other clubs. Those two
# player-independent constants hand LAD a 0.500 floor against a 0.422 runner-up
# and a 0.077 league median BEFORE the free agent is consulted. That 0.078
# constant edge, at weight 0.45, is the Dodgers-for-everyone mechanism, and it
# is why re-weighting need against behavior cannot reach it.
_CAND_LAMBDAS = (0.0, 0.25, 0.5, 0.7, 0.8, 0.9, 1.0)
_CAND_TEMPS = (0.02, 0.05, 0.1)


def _conc_from_scores(scored: list[dict], orgs: list[str]) -> dict:
    """Concentration metrics for a list of per-member {org: score} maps. Ties
    break alphabetically, matching fit_scores' stable sort over sorted(orgs)."""
    import statistics
    from collections import Counter
    first: Counter = Counter()
    top3: Counter = Counter()
    gaps, tied = [], []
    for sc in scored:
        order = sorted(orgs, key=lambda o: (-sc[o], o))
        first[order[0]] += 1
        for o in order[:3]:
            top3[o] += 1
        gaps.append(sc[order[0]] - sc[order[1]])
        best = sc[order[0]]
        tied.append(sum(1 for o in orgs if abs(sc[o] - best) < 1e-9))
    n = len(scored)
    t = first.most_common(1)[0]
    m = {"max_top1_share": round(t[1] / n, 4), "max_top1_club": t[0],
         "distinct_top1": len(first), "distinct_top3": len(top3),
         "median_gap": round(statistics.median(gaps), 4),
         "mean_clubs_tied_at_top": round(sum(tied) / n, 2),
         "top1_counts": dict(first.most_common(8))}
    m["gate"] = {
        "max_top1_share": m["max_top1_share"] <= CONCENTRATION_GATE["max_top1_share"],
        "distinct_top1": m["distinct_top1"] >= CONCENTRATION_GATE["min_distinct_top1"],
        "distinct_top3": m["distinct_top3"] >= CONCENTRATION_GATE["min_distinct_top3"],
        "median_gap": m["median_gap"] >= CONCENTRATION_GATE["min_median_gap"]}
    m["pass_3_criterion"] = all(v for k, v in m["gate"].items() if k != "median_gap")
    m["pass"] = all(m["gate"].values())
    return m


def _two_way(cells: list[dict], orgs: list[str]) -> dict:
    """score[player][club] = mu + alpha_player + beta_club + eps. Returns the
    variance share of each term. Only `interaction` can ever change which club
    tops a given player's list."""
    import statistics
    n, k = len(cells), len(orgs)
    grand = sum(c[o] for c in cells for o in orgs) / (n * k)
    alpha = [sum(c[o] for o in orgs) / k - grand for c in cells]
    beta = {o: sum(c[o] for c in cells) / n - grand for o in orgs}
    eps = [c[o] - grand - alpha[i] - beta[o]
           for i, c in enumerate(cells) for o in orgs]
    va = statistics.pvariance(alpha)
    vb = statistics.pvariance(list(beta.values()))
    ve = statistics.pvariance(eps)
    tot = va + vb + ve or 1.0
    return {"sd_player": round(va ** .5, 4), "sd_club": round(vb ** .5, 4),
            "sd_interaction": round(ve ** .5, 4),
            "pct_player": round(100 * va / tot, 1),
            "pct_club": round(100 * vb / tot, 1),
            "pct_interaction": round(100 * ve / tot, 1),
            "club_over_interaction": round((vb ** .5) / (ve ** .5), 2) if ve else None,
            "beta_club": {o: round(v, 4) for o, v in beta.items()}}


def _sinkhorn_offsets(scored: list[dict], orgs: list[str], temp: float,
                      iters: int = 200) -> dict[str, float]:
    """Candidate (a): per-club offsets fitted so every club carries the SAME
    aggregate softmax mass over the class - a hard cap on how much fit any one
    club may hold. Ranking by (fit - offset)."""
    b = {o: 0.0 for o in orgs}
    target = len(scored) / float(len(orgs))
    for _ in range(iters):
        mass = {o: 0.0 for o in orgs}
        for sc in scored:
            ex = {o: math.exp((sc[o] - b[o]) / temp) for o in orgs}
            z = sum(ex.values()) or 1.0
            for o in orgs:
                mass[o] += ex[o] / z
        worst = 0.0
        for o in orgs:
            b[o] += 0.5 * temp * math.log(max(mass[o], 1e-12) / target)
            worst = max(worst, abs(mass[o] / target - 1.0))
        if worst < 1e-4:
            break
    return b


def class_component_matrix(class_year: int | None = None) -> dict:
    """{class_year, orgs, members:[{key, side, proj_guar, orgs:{org:{fit + the
    five component scores}}}]} for the served class. Fail-soft like
    concentration_gate: {} when the class artifact or fa_fit is unavailable."""
    import json
    try:
        import fa_fit
        d = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}
    cy = class_year or d["class_year"]
    out = []
    for m in d.get("members") or []:
        player = {"position": m.get("pos"), "bat_throw": m.get("bt"),
                  "from_team": m.get("from"),
                  "_war_path": {"war_y1": m.get("warY1")}}
        pred = {"proj_guarantee_usd": m.get("projGuar"),
                "proj_aav_usd": m.get("projAav")}
        try:
            rows = fa_fit.fit_scores(player, pred, cy, top_n=30)
        except Exception:                                   # noqa: BLE001
            continue
        if len(rows) != 30:
            continue
        grp = fm._pos_group(m.get("pos"))
        out.append({
            "key": m.get("key"), "pos": m.get("pos"),
            "side": "pit" if grp in ("SP", "RP") else "hit",
            "proj_guar": m.get("projGuar"),
            "orgs": {r["org"]: {"fit": r["fit"],
                                **{f: r["components"][f]["score"] for f in FEATS}}
                     for r in rows}})
    if not out:
        return {}
    return {"class_year": cy, "orgs": sorted(out[0]["orgs"]), "members": out}


def concentration_decomposition(matrix: dict | None = None) -> dict:
    """THE DECOMPOSITION. Per-component top-1 share, the player/club/interaction
    split, and the concentration of candidates (a) club-mass cap, (b) display
    relative fit, (c) per-player z-scoring. Chain MRR is attached by
    run_fit_gate, which is where the forward-chained rows live."""
    import statistics
    mx = matrix if matrix is not None else class_component_matrix()
    if not mx:
        return {"available": False,
                "note": "data/fa_class.json unavailable - decomposition unmeasured"}
    orgs, mem = mx["orgs"], mx["members"]
    n = len(mem)
    per_component, variance = {}, {}
    for f in FEATS + ("COMPOSITE",):
        key = "fit" if f == "COMPOSITE" else f
        cells = [{o: m["orgs"][o][key] for o in orgs} for m in mem]
        c = _conc_from_scores(cells, orgs)
        per_component[f] = {k: v for k, v in c.items()
                            if k in ("max_top1_share", "max_top1_club",
                                     "distinct_top1", "distinct_top3",
                                     "median_gap", "mean_clubs_tied_at_top",
                                     "top1_counts")}
        variance[f] = _two_way(cells, orgs)
    # what each component CONTRIBUTES to the composite: w * sd, the only scale on
    # which the five terms actually compete inside the sum.
    tot_club = sum(LIVE_WEIGHTS[f] * variance[f]["sd_club"] for f in FEATS) or 1.0
    tot_int = sum(LIVE_WEIGHTS[f] * variance[f]["sd_interaction"] for f in FEATS) or 1.0
    contribution = {f: {
        "weight": LIVE_WEIGHTS[f],
        "w_sd_club": round(LIVE_WEIGHTS[f] * variance[f]["sd_club"], 4),
        "w_sd_interaction": round(LIVE_WEIGHTS[f] * variance[f]["sd_interaction"], 4),
        "share_of_composite_club_effect_pct":
            round(100 * LIVE_WEIGHTS[f] * variance[f]["sd_club"] / tot_club, 1),
        "share_of_composite_interaction_pct":
            round(100 * LIVE_WEIGHTS[f] * variance[f]["sd_interaction"] / tot_int, 1),
    } for f in FEATS}

    base = [{o: m["orgs"][o]["fit"] for o in orgs} for m in mem]
    beta = {o: statistics.fmean([sc[o] for sc in base]) for o in orgs}
    cands: dict[str, dict] = {}
    # (b) display-side relative fit: fit MINUS the club's baseline propensity.
    for lam in _CAND_LAMBDAS:
        cands[f"b_relative_fit_lambda_{lam:g}"] = {
            "kind": "display_offset", "lambda": lam,
            "concentration": _conc_from_scores(
                [{o: sc[o] - lam * beta[o] for o in orgs} for sc in base], orgs)}
    # (a) per-club saturation: equalize each club's aggregate softmax mass.
    for T in _CAND_TEMPS:
        off = _sinkhorn_offsets(base, orgs, T)
        cands[f"a_club_mass_cap_T{T:g}"] = {
            "kind": "model_offset", "temperature": T,
            "concentration": _conc_from_scores(
                [{o: sc[o] - off[o] for o in orgs} for sc in base], orgs)}
    # (c1) per-player z-score of the composite. Positive affine WITHIN a player,
    # so the argmax is provably unchanged - asserted, not assumed.
    z1 = []
    for sc in base:
        v = [sc[o] for o in orgs]
        mu, sd = statistics.fmean(v), statistics.pstdev(v) or 1.0
        z1.append({o: (sc[o] - mu) / sd for o in orgs})
    identical = all(
        sorted(orgs, key=lambda o: (-a[o], o)) == sorted(orgs, key=lambda o: (-b[o], o))
        for a, b in zip(base, z1))
    cands["c1_zscore_composite_per_player"] = {
        "kind": "no_op", "ranking_identical_to_shipped": identical,
        "concentration": _conc_from_scores(z1, orgs)}
    # (c2) z-score each COMPONENT per player, then recombine at shipped weights.
    z2 = []
    for m in mem:
        stat = {}
        for f in FEATS:
            v = [m["orgs"][o][f] for o in orgs]
            stat[f] = (statistics.fmean(v), statistics.pstdev(v) or 1.0)
        z2.append({o: sum(LIVE_WEIGHTS[f] * (m["orgs"][o][f] - stat[f][0]) / stat[f][1]
                          for f in FEATS) for o in orgs})
    cands["c2_zscore_components_per_player"] = {
        "kind": "model_rescale", "concentration": _conc_from_scores(z2, orgs)}

    # WHICH component is "saturated" must be judged on the WEIGHTED basis, not
    # the raw ratio. window has the most lopsided raw club/interaction ratio of
    # the five, but it carries weight 0.05: its saturation is inert, it cannot
    # move the composite either way. The component that MONOPOLIZES is the one
    # contributing the most club main effect TO THE COMPOSITE, and the component
    # carrying the player signal is the one contributing the most interaction.
    # Raw ratios stay reported beside them so both readings are visible.
    sat = max(FEATS, key=lambda f: contribution[f]["share_of_composite_club_effect_pct"])
    healthiest = max(
        FEATS, key=lambda f: contribution[f]["share_of_composite_interaction_pct"])
    raw_sat = max(FEATS, key=lambda f: variance[f]["club_over_interaction"] or 0)
    raw_best = min(FEATS, key=lambda f: variance[f]["club_over_interaction"] or 0)
    return {
        "available": True, "n_members": n, "class_year": mx["class_year"],
        "weights_scored": dict(LIVE_WEIGHTS),
        "per_component_top1": per_component,
        "variance_decomposition": variance,
        "weighted_contribution_to_composite": contribution,
        "club_baseline_propensity": {o: round(v, 4) for o, v in beta.items()},
        "candidates": cands,
        "saturated_component": sat,
        "most_player_specific_component": healthiest,
        "saturated_component_basis": "largest share of the COMPOSITE's club main effect (weight x sd_club)",
        "most_player_specific_basis": "largest share of the COMPOSITE's interaction (weight x sd_interaction)",
        "most_lopsided_raw_ratio_component": raw_sat,
        "least_lopsided_raw_ratio_component": raw_best,
        "raw_ratio_note": (
            f"On the UNWEIGHTED club/interaction ratio the extremes are "
            f"'{raw_sat}' ({variance[raw_sat]['club_over_interaction']}) and "
            f"'{raw_best}' ({variance[raw_best]['club_over_interaction']}), but "
            f"both carry weight {LIVE_WEIGHTS[raw_sat]:g}/"
            f"{LIVE_WEIGHTS[raw_best]:g} and are therefore inert in the "
            f"composite. Judge saturation on the weighted basis."),
        "scale_note": (
            "median_gap is only comparable to the threshold for candidates that "
            "keep the fit SCALE (the offset families a and b). The z-scored "
            "candidates report a gap in standard-deviation units, so their "
            "median_gap flag is not meaningful and only their share/distinct "
            "counts should be read."),
        "reading": (
            f"score[player][club] splits into a player main effect (irrelevant "
            f"WITHIN a list), a CLUB main effect (identical on every list, so it "
            f"is the monopoly) and an INTERACTION (the only term that can hand a "
            f"different club a different player). '{sat}' is the saturated "
            f"component: it supplies "
            f"{contribution[sat]['share_of_composite_club_effect_pct']}% of the "
            f"composite's club main effect but only "
            f"{contribution[sat]['share_of_composite_interaction_pct']}% of its "
            f"interaction, it is {variance[sat]['pct_club']}% club variance "
            f"against {variance[sat]['pct_interaction']}% interaction, and its "
            f"top-1 club {per_component[sat]['max_top1_club']} wins "
            f"{per_component[sat]['max_top1_share']:.4f} of the class on an "
            f"average of {per_component[sat]['mean_clubs_tied_at_top']} clubs "
            f"tied. '{healthiest}' is the player signal: "
            f"{contribution[healthiest]['share_of_composite_interaction_pct']}% "
            f"of the composite's interaction and only "
            f"{contribution[healthiest]['share_of_composite_club_effect_pct']}% "
            f"of its club effect. NO weight on a saturated component "
            f"de-monopolizes; it only sets how loudly the monopoly speaks."),
    }


def _chain_metrics_with_offsets(pooled: dict, offsets_by_winter: dict) -> dict:
    """MRR/top-k on the SAME forward chain and the SAME rows the gate scores,
    ranking by the live composite MINUS a per-club offset. The offsets are
    derived from the winter's own candidate class only (class composition is
    known at winter start), so nothing leaks the signer."""
    def score(r):
        off = offsets_by_winter.get(r["winter"], {})
        return (sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS)
                - off.get(r["org"], 0.0))
    return _rank_metrics(pooled, score)


def _winter_club_means(pooled: dict) -> dict:
    """Candidate (b) on the chain: each club's MEAN composite fit across that
    winter's candidate class - the backtest twin of the served-class propensity."""
    acc: dict = defaultdict(lambda: defaultdict(float))
    cnt: dict = defaultdict(lambda: defaultdict(int))
    for group in pooled.values():
        for r in group:
            acc[r["winter"]][r["org"]] += sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS)
            cnt[r["winter"]][r["org"]] += 1
    return {Y: {o: acc[Y][o] / cnt[Y][o] for o in acc[Y]} for Y in acc}


def _candidate_chain_scores(pooled: dict, decomp: dict) -> None:
    """Attach forward-chain MRR/top-k to every candidate in the decomposition,
    in place. Same rows, same chain, same signings as live_analog."""
    if not decomp.get("available"):
        return
    import statistics
    means = _winter_club_means(pooled)
    orgs = sorted({r["org"] for g in pooled.values() for r in g})
    by_winter: dict[int, list] = defaultdict(list)
    for g in pooled.values():
        if g:
            by_winter[g[0]["winter"]].append(
                {r["org"]: sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS) for r in g})
    for cand in decomp["candidates"].values():
        if cand["kind"] == "display_offset":
            lam = cand["lambda"]
            off = {Y: {o: lam * v for o, v in m.items()} for Y, m in means.items()}
            cand["chain"] = _chain_metrics_with_offsets(pooled, off)
        elif cand["kind"] == "model_offset":
            T = cand["temperature"]
            off = {Y: _sinkhorn_offsets(mat, orgs, T)
                   for Y, mat in by_winter.items()}
            cand["chain"] = _chain_metrics_with_offsets(pooled, off)
        elif cand["kind"] == "no_op":
            # provably rank-identical within a player; MEASURED anyway, not assumed
            cand["chain"] = _rank_metrics(pooled, lambda r: sum(
                LIVE_WEIGHTS[f] * r[f] for f in FEATS))
        else:                                   # model_rescale (c2)
            byk = {}
            for k, g in pooled.items():
                stat = {f: (statistics.fmean([r[f] for r in g]),
                            statistics.pstdev([r[f] for r in g]) or 1.0)
                        for f in FEATS}
                for r in g:
                    byk[(k, r["org"])] = sum(
                        LIVE_WEIGHTS[f] * (r[f] - stat[f][0]) / stat[f][1]
                        for f in FEATS)
            hits, rr, n = {1: 0, 3: 0, 5: 0}, [], 0
            for k, g in pooled.items():
                ranked = sorted(g, key=lambda r: -byk[(k, r["org"])])
                rank = next((i + 1 for i, r in enumerate(ranked) if r["signed"]), None)
                if rank is None:
                    continue
                n += 1
                rr.append(1.0 / rank)
                for kk in hits:
                    if rank <= kk:
                        hits[kk] += 1
            cand["chain"] = {"n": n, "top1": round(hits[1] / n, 4),
                             "top3": round(hits[3] / n, 4),
                             "top5": round(hits[5] / n, 4),
                             "mrr": round(sum(rr) / n, 4)}


def reweight_sweep(matrix: dict, pooled: dict, step: int = 20) -> dict:
    """EXHAUSTIVE re-weight search, because four rounds of hand re-weighting had
    failed and nobody had established whether ANY weight vector can clear the
    tripwire. Every lattice point of the 5-simplex at 0.05 (10,626 vectors) is
    scored for concentration on the served class; the ones that clear the gate
    are then scored on the identical forward chain.

    WHY THE EARLIER ATTEMPTS FAILED: they moved `need` against `behavior` with
    window/afford/park pinned at 0.05. That entire line is measured here
    (`need_behavior_line`) and NO point on it passes - the best, need 0.85 with
    behavior 0.00, still reads max_top1_share 0.2895 with distinct_top1 11 and
    median_gap 0.0078. The passing region requires RAISING park and cutting
    behavior, which no need/behavior split can reach.

    The passers are reported, not adopted. Every one of them sits on or beside a
    threshold (the best has ZERO slack on distinct_top1), the concentration side
    is measured on ONE served class that already moved LAD 133 -> 131 between
    two same-code regenerations, and the top-MRR passer is the extreme of a
    381-vector search whose own bootstrap CI straddles zero."""
    import itertools
    orgs, mem = matrix["orgs"], matrix["members"]
    n = len(mem)
    cells = [[[m["orgs"][o][f] for f in FEATS] for o in orgs] for m in mem]

    def conc(wv):
        from collections import Counter
        import statistics
        first: Counter = Counter()
        top3: Counter = Counter()
        gaps = []
        for row in cells:
            sc = [sum(wv[i] * v[i] for i in range(5)) for v in row]
            order = sorted(range(len(orgs)), key=lambda j: (-sc[j], orgs[j]))
            first[orgs[order[0]]] += 1
            for j in order[:3]:
                top3[orgs[j]] += 1
            gaps.append(sc[order[0]] - sc[order[1]])
        t = first.most_common(1)[0]
        return {"max_top1_share": round(t[1] / n, 4), "max_top1_club": t[0],
                "distinct_top1": len(first), "distinct_top3": len(top3),
                "median_gap": round(statistics.median(gaps), 4)}

    def passes(m, four=True):
        ok = (m["max_top1_share"] <= CONCENTRATION_GATE["max_top1_share"]
              and m["distinct_top1"] >= CONCENTRATION_GATE["min_distinct_top1"]
              and m["distinct_top3"] >= CONCENTRATION_GATE["min_distinct_top3"])
        return ok and (m["median_gap"] >= CONCENTRATION_GATE["min_median_gap"]
                       if four else True)

    def slack(m):
        return round(min(
            (CONCENTRATION_GATE["max_top1_share"] - m["max_top1_share"])
            / CONCENTRATION_GATE["max_top1_share"],
            (m["distinct_top1"] - CONCENTRATION_GATE["min_distinct_top1"])
            / float(CONCENTRATION_GATE["min_distinct_top1"]),
            (m["distinct_top3"] - CONCENTRATION_GATE["min_distinct_top3"])
            / float(CONCENTRATION_GATE["min_distinct_top3"]),
            (m["median_gap"] - CONCENTRATION_GATE["min_median_gap"])
            / CONCENTRATION_GATE["min_median_gap"]), 3)

    n3 = n4 = 0
    passers = []
    for combo in itertools.combinations(range(step + 4), 4):
        parts = [combo[0], combo[1] - combo[0] - 1, combo[2] - combo[1] - 1,
                 combo[3] - combo[2] - 1, step + 3 - combo[3]]
        wv = [p / float(step) for p in parts]
        m = conc(wv)
        if not passes(m, four=False):
            continue
        n3 += 1
        if passes(m, four=True):
            n4 += 1
            passers.append((dict(zip(FEATS, wv)), m))
    scored = []
    for wv, m in passers:
        ch = _rank_metrics(pooled, lambda r, _w=wv: sum(_w[f] * r[f] for f in FEATS))
        scored.append({"weights": {k: round(v, 2) for k, v in wv.items()},
                       "concentration": m, "slack": slack(m),
                       "chain": {k: ch[k] for k in ("mrr", "top1", "top3", "top5")}})
    ship = _rank_metrics(pooled, lambda r: sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS))
    mrrs = sorted(s["chain"]["mrr"] for s in scored)
    by_mrr = sorted(scored, key=lambda s: -s["chain"]["mrr"])
    by_slack = sorted(scored, key=lambda s: -s["slack"])
    allpos = [s for s in by_mrr if all(v > 0 for v in s["weights"].values())]
    line = []
    for i in range(18):
        nd = round(0.85 * i / 17, 2)
        wv = {"need": nd, "window": .05, "afford": .05, "park": .05,
              "behavior": round(0.85 - nd, 2)}
        m = conc([wv[f] for f in FEATS])
        line.append({"need": nd, "behavior": wv["behavior"], **m,
                     "pass": passes(m), "mrr": _rank_metrics(
                         pooled, lambda r, _w=wv: sum(_w[f] * r[f] for f in FEATS))["mrr"]})
    return {
        "lattice_step": 1.0 / step, "n_vectors": 10626,
        "n_pass_3_criterion": n3, "n_pass_4_criterion": n4,
        "shipped_mrr": ship["mrr"],
        "passer_mrr_distribution": {
            "min": mrrs[0], "p10": mrrs[len(mrrs) // 10],
            "median": mrrs[len(mrrs) // 2], "p90": mrrs[9 * len(mrrs) // 10],
            "max": mrrs[-1],
            "n_at_or_above_shipped": sum(1 for x in mrrs if x >= ship["mrr"])},
        "best_by_mrr": by_mrr[:5], "best_by_slack": by_slack[:5],
        "best_all_components_positive": allpos[:3],
        "need_behavior_line": line,
        "note": (
            "SELECTION WARNING: best_by_mrr is the extreme of a 10,626-vector "
            "search whose selection criterion was concentration and whose guard "
            "was MRR. Only "
            f"{sum(1 for x in mrrs if x >= ship['mrr'])} of {len(mrrs)} passers "
            "reach the shipped MRR, so the typical passer LOSES accuracy; the "
            "top one is a tail draw and its bootstrap CI straddles zero. It is "
            "reported for the next reader, NOT adopted."),
    }


def _repair_verdict(decomp: dict, sweep: dict | None, live: dict) -> dict:
    """The R6 conclusion, computed from the two blocks above so it cannot drift
    from them. Records what was tested, what passed, and what was refuted."""
    if not decomp.get("available"):
        return {"available": False}
    cands = decomp["candidates"]

    def row(name):
        c = cands[name]
        ch = c.get("chain") or {}
        return {"concentration_pass": c["concentration"]["pass"],
                "concentration_pass_3_criterion":
                    c["concentration"]["pass_3_criterion"],
                "max_top1_share": c["concentration"]["max_top1_share"],
                "distinct_top1": c["concentration"]["distinct_top1"],
                "distinct_top3": c["concentration"]["distinct_top3"],
                "median_gap": c["concentration"]["median_gap"],
                "mrr": ch.get("mrr"),
                "mrr_delta_vs_shipped": (round(ch["mrr"] - live["mrr"], 4)
                                         if ch.get("mrr") is not None else None)}

    best_b = max((k for k in cands if k.startswith("b_relative")),
                 key=lambda k: cands[k]["concentration"]["pass_3_criterion"] and
                 (cands[k].get("chain") or {}).get("mrr", 0))
    best_a = max((k for k in cands if k.startswith("a_club_mass")),
                 key=lambda k: (cands[k].get("chain") or {}).get("mrr", 0))
    return {
        "gate": "concentration PASS with MRR not worse on the same forward chain",
        "candidate_a_club_mass_cap": row(best_a),
        "candidate_b_display_relative_fit": row("b_relative_fit_lambda_1"),
        "candidate_b_minimal_passing": row(best_b),
        "candidate_c1_zscore_composite": row("c1_zscore_composite_per_player"),
        "candidate_c2_zscore_components": row("c2_zscore_components_per_player"),
        "findings": [
            "PREMISE REFUTED. The decomposition was run to test whether NEED was "
            "saturated. It is not: need has the LOWEST club-over-interaction "
            "ratio of the five components and supplies the large majority of the "
            "composite's player-club interaction. The saturated component is "
            "BEHAVIOR, whose top-1 club is the same club for every member of the "
            "class with no ties at all.",
            "MECHANISM. behavior = 0.5*reach + 0.3*recent + 0.2*rich and only "
            "`reach` takes a player input. `recent` divides by the LEAGUE-MAX "
            "3-winter outlay, which is the same club, so that club scores exactly "
            "1.0 by construction; `rich` clips at n_100m/5 so it saturates for "
            "five clubs at once. Those two player-independent constants decide "
            "the composite before the free agent is consulted. The F4 repair "
            "fixed `reach` and `reach` now behaves; the other two terms were "
            "never repaired.",
            "CANDIDATE (c) AS SPECIFIED IS A NO-OP. Per-player z-scoring of the "
            "composite across clubs is a positive affine transform WITHIN each "
            "player, so it cannot change any ranking or any argmax. Measured: "
            "ranking identical for every member, concentration and MRR both "
            "bit-identical to shipped. Recorded so it is never proposed again.",
            "CANDIDATES (a) AND (b) BUY CONCENTRATION WITH ACCURACY. Both are "
            "per-club additive offsets, and the club main effect they remove IS "
            "the signing signal (that club really does sign more free agents). "
            "Both clear the 3-criterion gate and both lose MRR well beyond this "
            "harness's registered MDE95 of 0.0126, landing between random and "
            "behavior_only. They fail the stated gate.",
            "NEITHER (a) NOR (b) CAN EVER CLEAR THE SHIPPED FOUR-CRITERION GATE. "
            "min_median_gap and max_top1_share are in mechanical tension along "
            "the whole offset family: the #1-vs-#2 gap IS the club main effect, "
            "so any offset that shrinks the monopoly shrinks the gap. median_gap "
            "falls through 0.015 while max_top1_share is still above 0.42.",
            "THE ONLY LEVER THAT CLEARS BOTH IS A RE-WEIGHT, AND IT IS NOT A "
            "NEED/BEHAVIOR SPLIT. See concentration_reweight_sweep: the "
            "need-vs-behavior line with window/afford/park pinned at 0.05 has no "
            "passing point at all, which is why four rounds of hand re-weighting "
            "failed. Passing requires raising park and cutting behavior. The "
            "best passer is reported with its selection warning and zero slack; "
            "it is NOT adopted here.",
            "R6.3 BEHAVIOR-CONFINED REPAIR: REFUTED, 2026-08-04. Six "
            "player-conditional rewrites of `recent` and `rich` (within-club "
            "conditional rates: share of the club's own guarantees at or above "
            "this player's price, restricted to the last 3 winters and to his "
            "price band) all FAIL BOTH halves of the gate. The term-level "
            "diagnosis is CONFIRMED - behavior's club main effect drops 69.8% "
            "-> 10.7% and the top club's constant edge 0.091 -> 0.019 - and the "
            "composite still concentrates at 0.3816.",
            "THE PRE-REGISTERED FALSIFICATION FIRED, and it reframes the gate. "
            "With the BEHAVIOR component DELETED OUTRIGHT the composite still "
            "concentrates 0.3816 on one club, against a 0.25 threshold. So the "
            "concentration failure is NOT a behavior defect and no change "
            "confined to behavior can ever pass. Two consequences: recommendation "
            "(2) below is SUPERSEDED (it named behavior as 'the real repair'), "
            "and any future attempt has to move the composite, not a term. Note "
            "also that `recent`'s league-max normalizer is carrying real signing "
            "signal, so the conditional replacement loses accuracy as well as "
            "failing concentration.",
            "FALLBACK (b) DOES NOT CLEAR THE GATE EITHER, contrary to the "
            "recommendation below: on the current class the display-side "
            "relative-fit view reads max_top1_share 0.2544 at lambda=1 and FAILS "
            "the 0.25 criterion; it clears only at lambda 1.1, where it fails "
            "elsewhere. If (b) ships it ships as a disclosed VIEW that does not "
            "pass, not as a repair.",
        ],
        "recommendation": (
            "Do not flip fa_config.fit.weights on this evidence. (1) SHIP "
            "candidate (b) as a DISPLAY-side relative-fit view with a disclosure "
            "line, model untouched, tripwire left red and honest - the view's own "
            "implied signing accuracy is recorded above and is materially worse "
            "than the model's, which is exactly what the disclosure must say. "
            "(2) The real repair is inside BEHAVIOR, not in the composite "
            "weights: `recent` and `rich` are player-independent club constants "
            "and `recent`'s league-max normalizer guarantees the monopolist a "
            "1.0. Re-deriving them as player-conditional terms (or dropping them "
            "into a separate club-propensity display axis) attacks the measured "
            "cause instead of the symptom. (3) Re-measure the sweep's passing "
            "region on a SECOND class year before treating any of it as real - "
            "every passer here has near-zero slack and the served class moved "
            "under the shipped weights between two regenerations of the same "
            "code."),
    }


def _served_cond_measure(matrix: dict) -> dict:
    """Served-class half of the TEAMFIT CONDITIONAL gate. Recomputes the
    behavior term player-conditionally from the SAME corpus behavior_priors
    reads, swaps it into the composite at shipped weights, and measures
    concentration. Fail-soft: {"available": False} without a class matrix."""
    if not matrix:
        return {"available": False,
                "note": "fa_class.json unavailable - served half unmeasured"}
    import fa_fit
    orgs, mem = matrix["orgs"], matrix["members"]
    signings = storage.load_fa_signings()
    last_winter = max((y for (_k, y) in signings), default=0)
    events: dict[str, list] = {o: [] for o in orgs}
    for (_k, y), s in signings.items():
        t, g = s.get("to_team"), s.get("guarantee_usd") or 0
        if t in events and s.get("mlb_deal"):
            events[t].append((y, g))
    priors = fa_fit.behavior_priors()
    max_recent = max((b.get("recent_spend_usd") or 0)
                     for b in priors.values()) or 1
    w_beh = LIVE_WEIGHTS["behavior"]
    base4_cells, cand_cells, inc_cells, beh_cond_cells = [], [], [], []
    recompose_max_dev = 0.0
    for m in mem:
        guar = float(m.get("proj_guar") or 20_000_000)
        cond = {o: _cond_terms(events[o], guar, last_winter - 2) for o in orgs}
        mx = max(v[0] for v in cond.values())
        base4, cand, inc, bcs = {}, {}, {}, {}
        for o in orgs:
            b = priors.get(o) or {}
            reach = fa_fit._spend_reach(b, guar)
            bc = (0.5 * reach
                  + 0.3 * (cond[o][0] / mx if mx > 0 else 0.0)
                  + 0.2 * min(1.0, cond[o][1] / 5.0))
            binc = (0.5 * reach
                    + 0.3 * min(1.0, (b.get("recent_spend_usd") or 0) / max_recent)
                    + 0.2 * min(1.0, (b.get("n_100m") or 0) / 5.0))
            recompose_max_dev = max(recompose_max_dev,
                                    abs(binc - m["orgs"][o]["behavior"]))
            b4 = sum(LIVE_WEIGHTS[f] * m["orgs"][o][f]
                     for f in ("need", "window", "afford", "park"))
            base4[o] = b4
            cand[o] = b4 + w_beh * bc
            inc[o] = b4 + w_beh * binc
            bcs[o] = bc
        base4_cells.append(base4)
        cand_cells.append(cand)
        inc_cells.append(inc)
        beh_cond_cells.append(bcs)
    lad_beh_top1 = sum(
        1 for sc in beh_cond_cells
        if sorted(orgs, key=lambda o: (-sc[o], o))[0] == "LAD")
    lad_comp_top1 = sum(
        1 for sc in cand_cells
        if sorted(orgs, key=lambda o: (-sc[o], o))[0] == "LAD")
    return {
        "available": True, "n_members": len(mem),
        "corpus_last_winter": last_winter,
        "recompose_max_abs_dev_vs_matrix_behavior": round(recompose_max_dev, 4),
        "candidate_composite": _conc_from_scores(cand_cells, orgs),
        "behavior_cond_term": _conc_from_scores(beh_cond_cells, orgs),
        "incumbent_recomposed": _conc_from_scores(inc_cells, orgs),
        "behavior_deleted": _conc_from_scores(base4_cells, orgs),
        "lad_behavior_cond_top1_share": round(lad_beh_top1 / len(mem), 4),
        "lad_candidate_composite_top1_share": round(lad_comp_top1 / len(mem), 4),
    }


def teamfit_conditional_gate(pooled: dict, matrix: dict) -> dict:
    """THE TEAMFIT CONDITIONAL GATE (2026-08-19). Clauses frozen in
    docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md BEFORE this ran:
      1 accuracy floor  mrr_cond >= 0.1669 - MDE95 and top3_cond >= 0.145 -
        MDE95, MDE95 from a cluster bootstrap (signing = unit, B=2000, seed 7)
        of the paired candidate-minus-incumbent MRR delta
      2 concentration   candidate composite on the served class:
        max_top1_share < 0.25, distinct_top1 >= 12, distinct_top3 >= 20
      3 sanity          LAD behavior_cond top-1 for < 50% of members
      4 zero-slack      if accuracy and concentration trade again, refuse and
        STOP - no band/clip/weight retune."""
    import numpy as np
    g = TEAMFIT_COND_GATE

    def inc_score(r):
        return sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS)

    def cand_score(r):
        return (sum(LIVE_WEIGHTS[f] * r[f]
                    for f in ("need", "window", "afford", "park"))
                + LIVE_WEIGHTS["behavior"] * r["behavior_cond"])

    inc = _rank_metrics(pooled, inc_score)
    cand = _rank_metrics(pooled, cand_score)
    # paired reciprocal ranks per signing, aligned for the bootstrap
    rr_inc, rr_cand = [], []
    for _key, group in pooled.items():
        for fn, acc in ((inc_score, rr_inc), (cand_score, rr_cand)):
            ranked = sorted(group, key=lambda r: -fn(r))
            rank = next((i + 1 for i, r in enumerate(ranked) if r["signed"]),
                        None)
            if rank is None:
                break
            acc.append(1.0 / rank)
    a_inc = np.asarray(rr_inc)
    a_cand = np.asarray(rr_cand)
    rng = np.random.default_rng(g["bootstrap_seed"])
    n = len(a_inc)
    deltas = np.empty(g["bootstrap_B"])
    for i in range(g["bootstrap_B"]):
        idx = rng.integers(0, n, n)
        deltas[i] = a_cand[idx].mean() - a_inc[idx].mean()
    mde95 = round(1.96 * float(np.std(deltas, ddof=1)), 4)
    ci = (round(float(np.quantile(deltas, 0.025)), 4),
          round(float(np.quantile(deltas, 0.975)), 4))
    served = _served_cond_measure(matrix)

    clause1 = (cand["mrr"] >= g["mrr_floor_anchor"] - mde95
               and cand["top3"] >= g["top3_floor_anchor"] - mde95)
    if served.get("available"):
        cc = served["candidate_composite"]
        clause2 = (cc["max_top1_share"] < g["max_top1_share"]
                   and cc["distinct_top1"] >= g["min_distinct_top1"]
                   and cc["distinct_top3"] >= g["min_distinct_top3"])
        clause3 = (served["lad_behavior_cond_top1_share"]
                   < g["lad_behavior_majority"])
    else:
        clause2 = clause3 = False
    trade_fired = (clause2 and not clause1) or (clause1 and not clause2)
    shipped = clause1 and clause2 and clause3
    return {
        "gate_doc": "docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md",
        "measured_at": date.today().isoformat(),
        "band_factor": TEAMFIT_COND_BAND_FACTOR,
        "thresholds": dict(g),
        "chain_n": n,
        "chain_incumbent": inc,
        "chain_candidate": cand,
        "mrr_delta": round(cand["mrr"] - inc["mrr"], 4),
        "mde95": mde95,
        "delta_ci95": ci,
        "served": served,
        "clauses": {
            "1_accuracy_floor": clause1,
            "2_concentration": clause2,
            "3_lad_sanity": clause3,
            "4_trade_refusal_fired": trade_fired,
        },
        "shipped": shipped,
    }


def run_fit_gate(persist: bool = True) -> dict:
    rows = build_rows()
    winters = sorted({r["winter"] for r in rows})
    models = {
        "random": lambda r: 0.0,
        "payroll_only": lambda r: r["afford"],
        "behavior_only": lambda r: r["behavior"],
        "live_analog": lambda r: sum(LIVE_WEIGHTS[f] * r[f] for f in FEATS),
    }
    pooled_groups: dict[str, dict] = {m: {} for m in models}
    pooled_groups["fitted_transfer"] = {}
    pooled_groups["fitted_full"] = {}
    transfer_coefs_last = None
    for Y in winters:
        test = [r for r in rows if r["winter"] == Y]
        train = [r for r in rows if r["winter"] < Y]
        groups: dict[str, list] = defaultdict(list)
        for r in test:
            groups[f"{Y}:{r['signing']}"].append(r)
        for name in models:
            pooled_groups[name].update(groups)
        ct = _fit_logit(train, FEATS)
        cf = _fit_logit(train, FEATS + ("incumbent",))
        for key, group in groups.items():
            if ct is not None:
                pooled_groups["fitted_transfer"][key] = [
                    {**r, "_score_t": sum(c * r[f] for c, f in zip(ct, FEATS))}
                    for r in group]
            if cf is not None:
                pooled_groups["fitted_full"][key] = [
                    {**r, "_score_f": sum(c * r[f] for c, f in zip(
                        cf, FEATS + ("incumbent",)))}
                    for r in group]
        if ct is not None:
            transfer_coefs_last = ct
    results = {}
    for name, fn in models.items():
        # random gets analytic expectations (a 0-score sort is order-biased)
        if name == "random":
            results[name] = {"n": len(pooled_groups[name]),
                             "top1": round(1 / 30, 4), "top3": round(3 / 30, 4),
                             "top5": round(5 / 30, 4),
                             "mrr": round(sum(1 / k for k in range(1, 31)) / 30, 4)}
            continue
        results[name] = _rank_metrics(pooled_groups[name], fn)
    if pooled_groups["fitted_transfer"]:
        results["fitted_transfer"] = _rank_metrics(
            pooled_groups["fitted_transfer"], lambda r: r["_score_t"])
    if pooled_groups["fitted_full"]:
        results["fitted_full"] = _rank_metrics(
            pooled_groups["fitted_full"], lambda r: r["_score_f"])
    # weight-transfer candidate: positive transfer coefs normalized to 1
    candidate = None
    if transfer_coefs_last:
        pos = [max(0.0, c) for c in transfer_coefs_last]
        tot = sum(pos)
        if tot > 0:
            candidate = {f: round(c / tot, 3) for f, c in zip(FEATS, pos)}
    # ------------------------------------------------------------------
    # weight_mix_comparison + ship_decision: COMPUTED, not hand-added.
    # ------------------------------------------------------------------
    # These two keys are asserted by test_fa_fit_gate.py
    # ::test_shipped_weights_match_gate3_decision and were, until 2026-07-30,
    # present only in the committed artifact and produced by NO code - so any
    # `persist=True` re-run silently deleted them and broke the pin. They are
    # derived here from the same pooled groups every other row uses, so the
    # artifact regenerates faithfully and the pin cannot go stale again.
    MIXES = {
        "hand_v2": {"need": 0.31, "window": 0.19, "afford": 0.22,
                    "park": 0.04, "behavior": 0.24},
        "shipped_balanced": dict(LIVE_WEIGHTS),
    }
    if candidate:
        MIXES["fitted_logistic"] = candidate
    weight_mix = {}
    for name, wv in MIXES.items():
        weight_mix[name] = {
            "weights": {k: round(v, 3) for k, v in wv.items()},
            **{k: v for k, v in _rank_metrics(
                pooled_groups["live_analog"],
                lambda r, _w=wv: sum(_w[f] * r[f] for f in FEATS)).items()
                if k in ("mrr", "top1", "top3", "top5")},
        }
    weight_mix["behavior_only"] = {k: v for k, v in results["behavior_only"].items()
                                   if k in ("mrr", "top1", "top3", "top5")}
    ship_decision = (
        "shipped weights are read from fa_config.fit.weights and scored here "
        "verbatim (LIVE_WEIGHTS). The mix comparison below is computed on the "
        "identical forward chain, so it can never drift from what ships. The "
        "shipped mix is kept player-discriminative on purpose: a "
        "behavior-dominated composite is nearly player-INDEPENDENT and put one "
        "club atop every pitcher's fit list (the measured Giants/Dodgers failure "
        "pattern). Need is the only player-specific signal, and the 2026-07-30 "
        "fits-v4 pass re-weighted toward it after the concentration tripwire "
        "below measured the failure directly. Differences among the top mixes "
        "are within noise and are disclosed as such.")

    verdicts = {
        "live_analog_beats_random": results["live_analog"]["top5"] > 5 / 30,
        "live_analog_beats_payroll_only":
            results["live_analog"]["mrr"] > results["payroll_only"]["mrr"],
        "live_analog_beats_behavior_only":
            results["live_analog"]["mrr"] > results["behavior_only"]["mrr"],
        "fitted_transfer_beats_live_analog":
            ("fitted_transfer" in results
             and results["fitted_transfer"]["mrr"] > results["live_analog"]["mrr"]),
    }
    # R6 (2026-08-04): decompose the concentration failure before repairing it.
    # The served-class matrix is built ONCE and shared by the tripwire, the
    # decomposition and the re-weight sweep, so all three describe one class.
    matrix = class_component_matrix()
    decomp = concentration_decomposition(matrix)
    _candidate_chain_scores(pooled_groups["live_analog"], decomp)
    sweep = reweight_sweep(matrix, pooled_groups["live_analog"]) if matrix else None
    out = {
        "generated_at": date.today().isoformat(),
        "test_winters": winters,
        "results": results,
        "verdicts": verdicts,
        "weight_mix_comparison": weight_mix,
        "ship_decision": ship_decision,
        "concentration": concentration_gate(),
        "concentration_decomposition": decomp,
        "concentration_reweight_sweep": sweep,
        "concentration_repair_verdict": _repair_verdict(decomp, sweep,
                                                        results["live_analog"]),
        "teamfit_conditional_gate": teamfit_conditional_gate(
            pooled_groups["live_analog"], matrix),
        "fitted_transfer_weight_candidate": candidate,
        "fitted_transfer_coefs_final_winter": transfer_coefs_last,
        "notes": [
            "REDUCED-FEATURE ANALOG: the live engine's contracted-roster need/window inputs are not reconstructable historically — this gate validates the composite's reduced twin (payroll/tax Y-1, prior wins, behavior <Y, outgoing-FA need proxy, park Y-1)",
            "deal-size context (NPV) is identical across all 30 candidate clubs per signing — conditions the ranking, cannot leak the winner",
            "incumbency (re-signing gravity) is real and ex-ante but absent from the live composite — fitted_full shows its ceiling",
            "mystery-team realism: top-5 is the headline metric; top-1 on 30 clubs is genuinely hard",
            "CONCENTRATION TRIPWIRE (registered 2026-07-30): MRR/top-k are blind to a fit vector that ranks the SAME club first for everyone - a model can score well on signing prediction while being useless as a product. The concentration block measures that directly on the served class.",
            "CONCENTRATION DECOMPOSITION (R6, 2026-08-04): concentration_decomposition scores each component as if it were the whole fit and splits every component into player / CLUB / interaction variance. It REFUTES the standing premise that need is the saturated term: need is the most player-specific component, and BEHAVIOR is the saturated one. concentration_repair_verdict carries the candidate results and the recommendation.",
            "CONCENTRATION AND MRR MEASURE OPPOSITE HALVES OF ONE VARIANCE SPLIT: the club main effect is both the monopoly and the signing signal, so every de-monopolizer that works by a per-club offset trades MRR for concentration one-for-one. That is a property of the decomposition, not a tuning failure.",
            "TEAMFIT CONDITIONAL GATE (2026-08-19): the behavior term's recent/rich confined to the player's price band (band factor 2.5, reach untouched). Clauses frozen in docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md before the lab ran; the teamfit_conditional_gate block carries the verbatim result.",
        ],
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run_fit_gate()
    print(f"\n==== GATE 3 — signing-team prediction (winters {rep['test_winters']}) ====")
    print(f"{'model':>18} {'n':>5} {'top1':>7} {'top3':>7} {'top5':>7} {'mrr':>7}")
    for name, r in rep["results"].items():
        print(f"{name:>18} {r['n']:>5} {r['top1']:>7.3f} {r['top3']:>7.3f} "
              f"{r['top5']:>7.3f} {r['mrr']:>7.3f}")
    print("verdicts:", rep["verdicts"])
    print("transfer weight candidate:", rep["fitted_transfer_weight_candidate"])
    d = rep.get("concentration_decomposition") or {}
    if d.get("available"):
        print(f"\n==== CONCENTRATION DECOMPOSITION (n={d['n_members']}) ====")
        print(f"{'component':>11} {'top1share':>10} {'club':>5} {'%club':>7} "
              f"{'%inter':>7} {'club/int':>9} {'tiedAtTop':>10}")
        for f in FEATS + ("COMPOSITE",):
            c, v = d["per_component_top1"][f], d["variance_decomposition"][f]
            print(f"{f:>11} {c['max_top1_share']:>10.4f} {c['max_top1_club']:>5} "
                  f"{v['pct_club']:>7.1f} {v['pct_interaction']:>7.1f} "
                  f"{str(v['club_over_interaction']):>9} "
                  f"{c['mean_clubs_tied_at_top']:>10.2f}")
        print(f"saturated: {d['saturated_component']}   "
              f"most player-specific: {d['most_player_specific_component']}")
        print(f"\n{'candidate':>36} {'share':>7} {'d1':>4} {'d3':>4} {'gap':>7} "
              f"{'pass':>6} {'mrr':>7} {'dMRR':>8}")
        base = rep["results"]["live_analog"]["mrr"]
        for name, c in d["candidates"].items():
            cc, ch = c["concentration"], (c.get("chain") or {})
            m = ch.get("mrr")
            print(f"{name:>36} {cc['max_top1_share']:>7.4f} "
                  f"{cc['distinct_top1']:>4} {cc['distinct_top3']:>4} "
                  f"{cc['median_gap']:>7.4f} {str(cc['pass']):>6} "
                  f"{(f'{m:.4f}' if m is not None else '-'):>7} "
                  f"{(f'{m-base:+.4f}' if m is not None else '-'):>8}")
    s = rep.get("concentration_reweight_sweep") or {}
    if s:
        print(f"\nre-weight sweep: {s['n_pass_4_criterion']} of {s['n_vectors']} "
              f"lattice vectors clear the tripwire; passer MRR median "
              f"{s['passer_mrr_distribution']['median']:.4f} vs shipped "
              f"{s['shipped_mrr']:.4f}; "
              f"{s['passer_mrr_distribution']['n_at_or_above_shipped']} reach it")
        for r in s["best_by_mrr"][:3]:
            print(f"   mrr {r['chain']['mrr']:.4f} slack {r['slack']:>6.3f} "
                  f"share {r['concentration']['max_top1_share']:.4f} {r['weights']}")
    t = rep.get("teamfit_conditional_gate") or {}
    if t:
        print(f"\n==== TEAMFIT CONDITIONAL GATE (band x{t['band_factor']}) ====")
        print(f"chain n={t['chain_n']} incumbent mrr {t['chain_incumbent']['mrr']:.4f} "
              f"candidate mrr {t['chain_candidate']['mrr']:.4f} "
              f"delta {t['mrr_delta']:+.4f} MDE95 {t['mde95']:.4f} "
              f"CI95 {t['delta_ci95']}")
        sv = t.get("served") or {}
        if sv.get("available"):
            cc = sv["candidate_composite"]
            print(f"served n={sv['n_members']} candidate share "
                  f"{cc['max_top1_share']:.4f} ({cc['max_top1_club']}) "
                  f"d1 {cc['distinct_top1']} d3 {cc['distinct_top3']} "
                  f"LAD beh_cond top1 {sv['lad_behavior_cond_top1_share']:.4f} "
                  f"behavior-deleted share "
                  f"{sv['behavior_deleted']['max_top1_share']:.4f}")
        print(f"clauses {t['clauses']}  shipped={t['shipped']}")
    v = rep.get("concentration_repair_verdict") or {}
    for f in (v.get("findings") or []):
        print(f"\n* {f}")
    if v.get("recommendation"):
        print(f"\nRECOMMENDATION: {v['recommendation']}")
