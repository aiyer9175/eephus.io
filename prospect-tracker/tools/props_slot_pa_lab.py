# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""props_slot_pa_lab - the PA-by-lineup-slot table the hitter props price on.

WHAT THIS IS. A COUNT, not a fitted model and not a betting estimand. It reads
the cached play-by-play corpus and answers one question: how many plate
appearances does the batter who starts in slot k of a batting order actually
take in that game. Nothing here is estimated from, or scored against, a game
result, a price, a market or any pre-registered dark column. Running it makes
no network request.

WHY IT EXISTS. betting_export.SLOT_PA is the binomial TRIAL COUNT for the
1+ hits and 1+ home runs props and the lambda scale for total bases. Until
2026-09-17 it was a hand rule, 4.65 at the leadoff spot falling a flat 0.10 a
slot, which hands nine starters 38.25 plate appearances out of the roughly 37.8
a team-game carries (audit finding L17-F3). Every Over was priced a little
high, on every hitter row at once.

PRE-REGISTRATION (B-PA-DIST, docs/master-plan-2026-09-05-opus.md:785, frozen
before any of the numbers below were computed). "Fit PA per game by slot 1-9
from the corpus, split by home/away (ninth-inning censoring), run environment
and extra innings; replace SLOT_PA only if the fitted table beats it on PA
MAE." The plan's repair 8 adds the level leg: the nine slots must sum to less
than the league plate appearances a team gets in a game.

WHAT THIS LAB DOES AND DOES NOT DO AGAINST THAT BRIEF.
  - slot 1 to 9: done, on the order of first appearance, which is the starting
    nine in batting order.
  - home versus away: done, and it is the largest conditioning term in the
    brief. The home club does not bat in the ninth when it leads, so its
    starters are censored at every slot, by 0.16 to 0.20 PA.
  - run environment and extra innings: NOT conditioned on. Both are properties
    of a game that has not been played when a props row is priced, so a table
    conditioned on either could not be read at pricing time without first
    forecasting the thing itself. They are absorbed into the mean. This is a
    deliberate departure from the registered brief and it is recorded here, in
    the betting_export comment and in the served basis string, rather than
    left silent.

PROTOCOL, fixed before results.
  - FIT seasons 2022, 2023 and 2024. Universal-DH seasons only: in 2018-2021 a
    pitcher bats ninth in half the league and slot 9 reads about 2.79, which
    answers a different question.
  - HOLD-OUT season 2025, used once, for acceptance, and never fitted on.
  - The season being served (2026) is neither fitted nor held out on. It is
    read only as a level check, and the gap it shows is published as a residual
    rather than corrected into the table.
  - ACCEPTANCE leg 1, accuracy: on the hold-out, mean absolute error of the
    candidate table against each starter's realized plate appearances, beaten
    against the incumbent hand rule. Reported pooled, per slot, per side, and
    over slots 1 to 5, which is the population the props table actually prices
    (props_fair_lines walks order[:5]). The paired t is clustered by team-game,
    because the nine starters of one game share that game's length.
  - ACCEPTANCE leg 2, level: the nine slots of a table must sum to less than
    the league plate appearances per team-game of the population it describes.
    A side table is checked against its own side's league number.
  - MAE is the registered criterion and it is minimised by the median, while
    the table ships the MEAN. The mean is the functional a trial count needs:
    the props pmf is a mixture of Binomial(floor(pa)) and Binomial(ceil(pa))
    whose mean is exactly lambda only when pa is the expected PA. RMSE, which
    the mean does minimise, is reported beside MAE so both are on the record.

USAGE
    python tools/props_slot_pa_lab.py [--out data/betting_props_slot_pa_eval.json]
"""
import argparse
import collections
import json
import math
import os
import statistics

CORPUS = os.path.join(".cache", "pbp_corpus", "plays")

# Events that are not a plate appearance: they are runner events recorded while
# the same plate appearance continues.
NON_PA_PREFIX = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch",
                 "passed_ball", "balk", "other_out", "defensive_indiff",
                 "game_advisory", "runner")

FIT_SEASONS = ("2022", "2023", "2024")
HOLDOUT_SEASON = "2025"
SERVE_SEASON = "2026"
PRE_DH_SEASONS = ("2018", "2019", "2021")
PRICED_SLOTS = (1, 2, 3, 4, 5)
LINEAR = {s: round(4.65 - 0.10 * (s - 1), 2) for s in range(1, 10)}


def is_pa(ev):
    return bool(ev) and not ev.startswith(NON_PA_PREFIX)


def read_season(season, root=CORPUS):
    """[(side, slot, pa, game_pk)], {(pk, half): team_pa} for one season.

    The starting nine is the order of first appearance within a (game, half),
    which is the batting order as it was posted: a pinch hitter cannot come up
    before the man he replaces.
    """
    import pyarrow.parquet as pq
    path = os.path.join(root, season, "plays-%s.parquet" % season)
    t = pq.read_table(path, columns=["game_pk", "half", "at_bat_index",
                                     "batter_id", "event_type"])
    rows = list(zip(t.column("game_pk").to_pylist(),
                    t.column("half").to_pylist(),
                    t.column("at_bat_index").to_pylist(),
                    t.column("batter_id").to_pylist(),
                    t.column("event_type").to_pylist()))
    rows.sort(key=lambda r: (r[0], r[2]))
    order = collections.defaultdict(list)
    seen = collections.defaultdict(set)
    pa = collections.Counter()
    team_pa = collections.Counter()
    for pk, half, _abi, bid, ev in rows:
        key = (pk, half)
        if bid not in seen[key]:
            seen[key].add(bid)
            order[key].append(bid)
        if is_pa(ev):
            pa[(pk, half, bid)] += 1
            team_pa[key] += 1
    out = []
    for key, ids in order.items():
        if len(ids) < 9:
            continue
        pk, half = key
        side = "away" if half == "top" else "home"
        for i, bid in enumerate(ids[:9]):
            out.append((side, i + 1, pa[(pk, half, bid)], pk))
    return out, team_pa


def gather(seasons, root=CORPUS):
    starters, team_pa = [], {}
    for s in seasons:
        a, b = read_season(s, root)
        starters.extend(a)
        for k, v in b.items():
            team_pa[(s,) + k] = v
    return starters, team_pa


def tables(starters):
    """({pop: {slot: mean PA}}, {pop: {slot: n}}) over pooled, home and away."""
    buckets = collections.defaultdict(list)
    for side, slot, pa, _pk in starters:
        buckets[("pooled", slot)].append(pa)
        buckets[(side, slot)].append(pa)
    out, counts = {}, {}
    for pop in ("pooled", "home", "away"):
        out[pop] = {s: round(statistics.mean(buckets[(pop, s)]), 4)
                    for s in range(1, 10)}
        counts[pop] = {s: len(buckets[(pop, s)]) for s in range(1, 10)}
    return out, counts


def league_pa(team_pa):
    pooled = list(team_pa.values())
    # The key is (pk, half) from read_season and (season, pk, half) from
    # gather, so the half is read off the END and one caller cannot silently
    # get the other's answer.
    away = [v for k, v in team_pa.items() if k[-1] == "top"]
    home = [v for k, v in team_pa.items() if k[-1] == "bottom"]
    return {"pooled": round(statistics.mean(pooled), 4),
            "away": round(statistics.mean(away), 4),
            "home": round(statistics.mean(home), 4),
            "team_games": len(pooled)}


def errors(starters, table_of, slots=tuple(range(1, 10)), side=None):
    """(mae, rmse, n) for one candidate over a hold-out population."""
    ae, se, n = 0.0, 0.0, 0
    slots = set(slots)
    for s_side, slot, pa, _pk in starters:
        if slot not in slots or (side and s_side != side):
            continue
        d = pa - table_of(s_side, slot)
        ae += abs(d)
        se += d * d
        n += 1
    if not n:
        return float("nan"), float("nan"), 0
    return ae / n, math.sqrt(se / n), n


def clustered_t(starters, a_of, b_of, slots=tuple(range(1, 10))):
    """Paired t of (error under b) minus (error under a), clustered by
    team-game: the nine starters of one game are one observation, not nine."""
    slots = set(slots)
    per = collections.defaultdict(list)
    for side, slot, pa, pk in starters:
        if slot not in slots:
            continue
        per[(pk, side)].append(abs(pa - b_of(side, slot))
                               - abs(pa - a_of(side, slot)))
    means = [statistics.mean(v) for v in per.values()]
    m, sd, n = statistics.mean(means), statistics.stdev(means), len(means)
    return m, m / (sd / math.sqrt(n)), n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        "data", "betting_props_slot_pa_eval.json"))
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    fit, fit_tpa = gather(FIT_SEASONS, args.corpus)
    hold, hold_tpa = gather([HOLDOUT_SEASON], args.corpus)
    serve, serve_tpa = gather([SERVE_SEASON], args.corpus)
    pre, pre_tpa = gather(PRE_DH_SEASONS, args.corpus)

    fit_tab, fit_n = tables(fit)
    hold_tab, _ = tables(hold)
    serve_tab, _ = tables(serve)
    pre_tab, _ = tables(pre)
    fit_lg, hold_lg = league_pa(fit_tpa), league_pa(hold_tpa)
    serve_lg, pre_lg = league_pa(serve_tpa), league_pa(pre_tpa)

    def linear_of(_side, slot):
        return LINEAR[slot]

    def pooled_of(_side, slot):
        return fit_tab["pooled"][slot]

    def split_of(side, slot):
        return fit_tab[side][slot]

    cands = {"linear": linear_of, "pooled": pooled_of, "split": split_of}
    acc = {}
    for name, f in cands.items():
        mae, rmse, n = errors(hold, f)
        acc[name] = {
            "mae": round(mae, 5), "rmse": round(rmse, 5), "n": n,
            "mae_by_slot": {s: round(errors(hold, f, [s])[0], 5)
                            for s in range(1, 10)},
            "mae_by_side": {sd: round(errors(hold, f, range(1, 10), sd)[0], 5)
                            for sd in ("home", "away")},
            "mae_priced_slots": round(errors(hold, f, PRICED_SLOTS)[0], 5),
            "mae_priced_slots_by_side": {
                sd: round(errors(hold, f, PRICED_SLOTS, sd)[0], 5)
                for sd in ("home", "away")},
            "sum_nine": (round(sum(LINEAR.values()), 4) if name == "linear"
                         else {p: round(sum(fit_tab[p].values()), 4)
                               for p in ("pooled", "home", "away")}),
        }

    ts = {}
    for name in ("pooled", "split"):
        m, t, nclu = clustered_t(hold, cands[name], linear_of)
        mp, tp, _ = clustered_t(hold, cands[name], linear_of, PRICED_SLOTS)
        ts[name + "_vs_linear"] = {"mean_gain": round(m, 5), "t": round(t, 2),
                                   "clusters": nclu,
                                   "mean_gain_priced_slots": round(mp, 5),
                                   "t_priced_slots": round(tp, 2)}
    m, t, nclu = clustered_t(hold, split_of, pooled_of)
    mp, tp, _ = clustered_t(hold, split_of, pooled_of, PRICED_SLOTS)
    ts["split_vs_pooled"] = {"mean_gain": round(m, 5), "t": round(t, 2),
                             "clusters": nclu,
                             "mean_gain_priced_slots": round(mp, 5),
                             "t_priced_slots": round(tp, 2)}

    art = {
        "model_id": "betting_props_slot_pa",
        "generated_by": "tools/props_slot_pa_lab.py",
        "what": ("expected plate appearances by starting lineup slot, counted "
                 "on the cached play-by-play corpus. A count, not a fit "
                 "against any outcome, price or market."),
        "fit_seasons": list(FIT_SEASONS),
        "holdout_season": HOLDOUT_SEASON,
        "served_season_context_only": SERVE_SEASON,
        "table": fit_tab,
        "table_n_starter_games": fit_n,
        "league_pa_per_team_game": {"fit": fit_lg, "holdout": hold_lg,
                                    "served_season": serve_lg,
                                    "pre_dh_2018_2021": pre_lg},
        "holdout_table_for_reference": hold_tab,
        "served_season_table_for_reference": serve_tab,
        "pre_dh_table_for_reference": pre_tab,
        "incumbent_linear_rule": LINEAR,
        "acceptance": acc,
        "acceptance_clustered_t": ts,
        "priced_slots": list(PRICED_SLOTS),
        "conditioning_dropped": ("run environment and extra innings, neither "
                                 "knowable when a row is priced"),
    }
    txt = json.dumps(art, indent=1, sort_keys=True)
    if not args.no_write:
        # No newline argument: the artifact is written the way a checkout
        # on this platform reads it, and git's own normalisation owns the
        # rest, so a regen does not show up as a whole-file diff.
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
