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
from trades import canonical_org

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
                org = canonical_org((tr.get("team") or {}).get("name") or "")
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
                org = canonical_org((tr.get("team") or {}).get("name") or "")
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


def _park_score(pf: dict, org: str, is_pitcher: bool) -> float:
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
        beh: dict[str, dict] = defaultdict(lambda: {"max": 0, "n100": 0, "recent": 0})
        for s in prior:
            t = s.get("to_team")
            if t not in ORGS:
                continue
            g = fm._npv_of(s)
            beh[t]["max"] = max(beh[t]["max"], g)
            if g >= 100_000_000:
                beh[t]["n100"] += 1
            if s["class_year"] >= Y - 3:
                beh[t]["recent"] += g
        max_recent = max((b["recent"] for b in beh.values()), default=1) or 1
        pay = team_payroll_state(Y - 1)
        wins = standings_wins(Y - 1)
        if (Y - 1) not in park_cache:
            try:
                park_cache[Y - 1] = {
                    canonical_org(r.get("name_display_club") or "") or "?":
                        {"woba": int(r.get("index_woba") or 100),
                         "hr": int(r.get("index_hr") or 100)}
                    for r in fa_sources.fetch_savant_park_factors(Y - 1)}
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
            for org in ORGS:
                b = beh.get(org) or {"max": 0, "n100": 0, "recent": 0}
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
                    "behavior": (0.5 * min(1.0, b["max"] / max(npv, 1)) ** 0.5
                                 + 0.3 * min(1.0, b["recent"] / max_recent)
                                 + 0.2 * min(1.0, b["n100"] / 5.0)),
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
    out = {
        "generated_at": date.today().isoformat(),
        "test_winters": winters,
        "results": results,
        "verdicts": verdicts,
        "fitted_transfer_weight_candidate": candidate,
        "fitted_transfer_coefs_final_winter": transfer_coefs_last,
        "notes": [
            "REDUCED-FEATURE ANALOG: the live engine's contracted-roster need/window inputs are not reconstructable historically — this gate validates the composite's reduced twin (payroll/tax Y-1, prior wins, behavior <Y, outgoing-FA need proxy, park Y-1)",
            "deal-size context (NPV) is identical across all 30 candidate clubs per signing — conditions the ranking, cannot leak the winner",
            "incumbency (re-signing gravity) is real and ex-ante but absent from the live composite — fitted_full shows its ceiling",
            "mystery-team realism: top-5 is the headline metric; top-1 on 30 clubs is genuinely hard",
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
