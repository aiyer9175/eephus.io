# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Draft slot-curve refit (model-audit Phase 4b, WS-8) — the first
backtest of the hardcoded pick-slot expected-WAR table.

storage._PICK_SLOT_EXPECTED_WAR shipped as an "industry research" step
table and was never checked against realized outcomes; it also seeds
the QO pick-tax pricing chain. This tool fits the realized curve:

  DATA       StatsAPI draft history 2005-2018 (pickNumber, mlbam) x
             Baseball-Reference war_daily (pybaseball bwar_bat/pitch,
             per-season bWAR by mlb_ID — the platform's WAR basis).
  SIGNED     a pick is treated UNSIGNED (excluded — the value returns
             via the re-draft) when the same person reappears in a
             LATER draft. StatsAPI carries no signed flag pre-2017;
             re-entry is the observable consequence of not signing.
  TARGETS    career bWAR through the last complete season, fitted on
             the 2005-2014 cohorts (11+ observation years — careers
             effectively resolved); first-6y and first-8y windows on
             ALL cohorts (complete through 2018+8=2026). Never-MLB
             picks score 0 — the expectation must include busts.
  FIT        isotonic (PAVA), monotone DECREASING in pick number,
             weighted by per-pick sample, picks 1-500.
  HOLDOUT    the fitted first-8y curve (trained 2005-2014) scored
             against realized first-8y WAR by bucket on 2015-2018 —
             the shape check on cohorts the career fit never saw.

Artifact: data/draft_slot_curve.json — consumed by
storage._pick_slot_expected_war (career basis, with the old table as
fallback) and fa_market.qo_tax_usd (first-6y basis -> implied FV ->
the platform surplus machinery).

Run: python tools/fit_draft_slot_curve.py   (one-time fit; refit when
a new cohort's window completes — yearly at most)
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "draft_slot_curve.json"
CACHE_DIR = ROOT / ".cache" / "draft_history"

DRAFT_YEARS = range(2005, 2019)
CAREER_FIT_YEARS = range(2005, 2015)     # careers resolved (11+ yrs)
LAST_FULL_SEASON = 2025
MAX_PICK = 500
# bucket upper-bounds — the incumbent step table's breakpoints, kept so
# the before/after comparison is bucket-by-bucket
BUCKETS = (1, 5, 10, 20, 35, 50, 75, 100, 150, 200, 300, 500)


def draft_picks(year: int) -> list[dict]:
    """[{pick, mlbam, name}] for one draft year, cached."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = f"https://statsapi.mlb.com/api/v1/draft/{year}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    out = []
    for rnd in (d.get("drafts") or {}).get("rounds") or []:
        for p in rnd.get("picks") or []:
            person = p.get("person") or {}
            if p.get("isPass") or not person.get("id") or not p.get("pickNumber"):
                continue
            out.append({"pick": int(p["pickNumber"]),
                        "mlbam": int(person["id"]),
                        "name": person.get("fullName")})
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("draft %s: %d picks cached", year, len(out))
    return out


def war_by_player(provider: str | None = None) -> dict[int, dict[int, float]]:
    """{mlbam: {season: WAR}} from the war_daily stint frames (bat + pitch
    summed), read through the war_source facade on ``provider`` (None = the
    facade DEFAULT, eWAR v2 since 2026-09-03), so the slot curve prices picks
    on the served basis; provider='bwar' reproduces the shipped fit's inputs.
    Under eWAR only pitcher-seasons move (FIP re-pricing within role); the
    batting side equals bWAR until the SDR defense drop. The refit itself is
    the rebuild wave's (re-anchor cascade), not this lane's."""
    import war_source
    provider = provider or war_source.DEFAULT_PROVIDER
    out: dict[int, dict[int, float]] = {}
    for side in ("bat", "pit"):
        df = war_source.stint_frame(side, provider=provider)
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid, yr, war = int(row.mlb_ID), int(row.year_ID), float(row.WAR)
            except (TypeError, ValueError):
                continue
            seasons = out.setdefault(mid, {})
            seasons[yr] = seasons.get(yr, 0.0) + war
    return out


def _window_war(seasons: dict[int, float], n: int | None) -> float:
    """Sum of bWAR over the first n MLB seasons (None = career through
    the last complete season). Empty seasons dict -> 0 (never reached)."""
    if not seasons:
        return 0.0
    yrs = sorted(y for y in seasons if y <= LAST_FULL_SEASON)
    if not yrs:
        return 0.0
    if n is None:
        return sum(seasons[y] for y in yrs)
    debut = yrs[0]
    return sum(seasons[y] for y in yrs if y < debut + n)


def _pava_decreasing(xs: list[int], ys: list[float],
                     ws: list[float]) -> list[float]:
    """Weighted isotonic regression, monotone DECREASING in x (xs sorted
    ascending). Classic pool-adjacent-violators on the negated sequence."""
    blocks = [[-y, w, 1] for y, w in zip(ys, ws)]   # negate -> increasing
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0] + 1e-12:
            y1, w1, n1 = blocks[i]
            y2, w2, n2 = blocks[i + 1]
            merged = [(y1 * w1 + y2 * w2) / (w1 + w2), w1 + w2, n1 + n2]
            blocks[i:i + 2] = [merged]
            if i > 0:
                i -= 1
        else:
            i += 1
    out = []
    for y, _w, n in blocks:
        out.extend([-y] * n)
    return out


def fit_curve(rows: list[tuple[int, float]]) -> dict[int, float]:
    """{pick: fitted expected WAR} — per-pick means -> decreasing PAVA."""
    by_pick: dict[int, list[float]] = {}
    for pick, war in rows:
        by_pick.setdefault(pick, []).append(war)
    xs = sorted(by_pick)
    ys = [sum(by_pick[x]) / len(by_pick[x]) for x in xs]
    ws = [float(len(by_pick[x])) for x in xs]
    fit = _pava_decreasing(xs, ys, ws)
    return {x: round(v, 3) for x, v in zip(xs, fit)}


def _bucket_of(pick: int) -> int:
    for b in BUCKETS:
        if pick <= b:
            return b
    return BUCKETS[-1]


def _bucket_table(rows: list[tuple[int, float]]) -> dict[int, dict]:
    agg: dict[int, list[float]] = {}
    for pick, war in rows:
        if pick <= MAX_PICK:
            agg.setdefault(_bucket_of(pick), []).append(war)
    return {b: {"n": len(v), "mean_war": round(sum(v) / len(v), 3)}
            for b, v in sorted(agg.items())}


def _curve_bucket_means(curve: dict[int, float]) -> dict[int, float]:
    agg: dict[int, list[float]] = {}
    for pick, v in curve.items():
        agg.setdefault(_bucket_of(pick), []).append(v)
    return {b: round(sum(v) / len(v), 3) for b, v in sorted(agg.items())}


def run(persist: bool = True) -> dict:
    import storage
    incumbent = {b: w for b, w in storage._PICK_SLOT_EXPECTED_WAR}

    picks_by_year = {y: draft_picks(y) for y in DRAFT_YEARS}
    # unsigned detection: person reappears in a later draft
    last_drafted: dict[int, int] = {}
    for y, picks in picks_by_year.items():
        for p in picks:
            last_drafted[p["mlbam"]] = max(last_drafted.get(p["mlbam"], 0), y)
    import war_source
    war_provider = war_source.DEFAULT_PROVIDER
    wars = war_by_player(war_provider)

    rows = {"career": [], "first6": [], "first8": [], "first8_holdout": []}
    acct = {"picks_seen": 0, "unsigned_excluded": 0, "scored": 0}
    for y, picks in picks_by_year.items():
        for p in picks:
            if p["pick"] > MAX_PICK:
                continue
            acct["picks_seen"] += 1
            if last_drafted[p["mlbam"]] > y:
                acct["unsigned_excluded"] += 1
                continue
            seasons = wars.get(p["mlbam"]) or {}
            acct["scored"] += 1
            if y in CAREER_FIT_YEARS:
                rows["career"].append((p["pick"], _window_war(seasons, None)))
                rows["first6"].append((p["pick"], _window_war(seasons, 6)))
                rows["first8"].append((p["pick"], _window_war(seasons, 8)))
            else:
                rows["first8_holdout"].append((p["pick"], _window_war(seasons, 8)))

    curve_career = fit_curve(rows["career"])
    curve_first6 = fit_curve(rows["first6"])
    curve_first8 = fit_curve(rows["first8"])

    realized_career = _bucket_table(rows["career"])
    realized_hold = _bucket_table(rows["first8_holdout"])
    fit8_buckets = _curve_bucket_means(curve_first8)
    holdout_check = {}
    abs_err_fit, abs_err_inc = [], []
    for b, obs in realized_hold.items():
        fitted = fit8_buckets.get(b)
        inc = incumbent.get(b)
        holdout_check[b] = {"realized_first8": obs["mean_war"], "n": obs["n"],
                            "fitted_first8_2005_14": fitted,
                            "incumbent_career_step": inc}
        if fitted is not None:
            abs_err_fit.append(abs(fitted - obs["mean_war"]))
        if inc is not None:
            abs_err_inc.append(abs(inc - obs["mean_war"]))

    out = {
        "generated_at": date.today().isoformat(),
        "draft_years": [min(DRAFT_YEARS), max(DRAFT_YEARS)],
        "career_fit_years": [min(CAREER_FIT_YEARS), max(CAREER_FIT_YEARS)],
        "accounting": acct,
        "conventions": {
            "war_basis": (f"war_source provider {war_provider} (war_daily stint frames, "
                          "bat+pitch summed), the platform basis; eWAR v2 = FIP-repriced "
                          "pitching within role, position players equal bWAR until the SDR drop"),
            "unsigned": "excluded when the person reappears in a later draft",
            "never_mlb": "scores 0 (the expectation includes busts)",
            "fit": "weighted decreasing isotonic (PAVA) on per-pick means, picks 1-500",
            "holdout": "first-8y curve (fit 2005-14) vs realized first-8y by bucket on 2015-18 — NB incumbent steps are CAREER-basis, so its holdout column is a scale reference, not a like-for-like error",
            "holdout_confounds": "DISCLOSED: windows count from MLB DEBUT, so 2015-18 cohorts are right-censored (a 2018 pick debuting 2022 has only 4 observed seasons by 2025) and every window contains COVID-2020 — the holdout reads structurally low and is a diagnostic, NOT the ship criterion",
        },
        "ship_decision": {
            "date": "2026-06-11",
            "decision": "SHIP the fitted FIRST-6-SEASON curve into "
                        "storage._pick_slot_expected_war (the org draft-value "
                        "leaf compares graduates' career-to-date WAR, almost "
                        "always <= 6 MLB seasons) and into the QO pick tax "
                        "(fa_market: expected first-6 path through the "
                        "service-time surplus machinery, eta-lagged 3y). The "
                        "hand-set table stays as artifact-absent fallback.",
            "basis": "the incumbent was never realized-anchored and "
                     "undershoots resolved 2005-14 career means ~3x at every "
                     "slot; monotonicity is enforced by the fit; the holdout "
                     "is censoring-confounded (see conventions) and not used "
                     "as the criterion",
        },
        "buckets_upper_bounds": list(BUCKETS),
        "realized_career_by_bucket_2005_14": {str(k): v for k, v in realized_career.items()},
        "incumbent_step_table": {str(k): v for k, v in incumbent.items()},
        "fitted_career_by_bucket": {str(k): v for k, v in _curve_bucket_means(curve_career).items()},
        "fitted_first6_by_bucket": {str(k): v for k, v in _curve_bucket_means(curve_first6).items()},
        "fitted_first8_by_bucket": {str(k): v for k, v in fit8_buckets.items()},
        "holdout_2015_18_first8": {str(k): v for k, v in holdout_check.items()},
        "holdout_mae": {
            "fitted_first8": round(sum(abs_err_fit) / len(abs_err_fit), 3) if abs_err_fit else None,
            "incumbent_career_steps_as_first8_proxy":
                round(sum(abs_err_inc) / len(abs_err_inc), 3) if abs_err_inc else None,
        },
        # the consumable curves: bucket-step form, same shape as the
        # incumbent table — [[bucket_upper_bound, expected_war], ...]
        "career_step_curve": [[b, _curve_bucket_means(curve_career).get(b)]
                              for b in BUCKETS],
        "first6_step_curve": [[b, _curve_bucket_means(curve_first6).get(b)]
                              for b in BUCKETS],
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("accounting:", rep["accounting"])
    print("bucket | realized career 05-14 | incumbent | fitted career | fitted 6y")
    for b in rep["buckets_upper_bounds"]:
        rc = rep["realized_career_by_bucket_2005_14"].get(str(b)) or {}
        print(f"{b:5d}  | {rc.get('mean_war')} (n={rc.get('n')})"
              f" | {rep['incumbent_step_table'].get(str(b))}"
              f" | {rep['fitted_career_by_bucket'].get(str(b))}"
              f" | {rep['fitted_first6_by_bucket'].get(str(b))}")
    print("holdout MAE:", rep["holdout_mae"])
