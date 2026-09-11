# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""war_rate_plus_lab - the gate + frozen-vintage lab for WAR/PA+ and WAR/IP+.

Two new Arkmetrics on the /mlbstats/ boards: WAR/PA+ (hitters, batting WAR per
plate appearance) and WAR/IP+ (pitchers, pitching WAR per inning, shipped TWICE
on two separate role-anchored pools). WAR is the SERVED series (war_source's
default provider, eWAR v2 since the 2026-09-03 epoch); the lab was re-pointed
from bWAR on 2026-09-11 (audit F10-01, owner decision), see the AMENDMENT below
the RESULT. Convention 3 of docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:
100 + 10z, ten points per population standard deviation. A ratio-to-mean index
is UNDEFINED here because league mean WAR/PA is about +0.0025 and WAR goes
negative, so there is no HEM_SPREAD_GAIN analog and none is added.

Harness: tools/plus_lab_harness.py v2 (unrounded predictors, complete-outcome-
season pairs only, player-clustered season-stratified bootstrap, dual-convention
artifact). This is a NEW gate, so per the harness contract it PRE-DECLARES its
convention: v2 is primary. v1 rides alongside for comparability with the
REM+/SEM+/HEM+ family.

===========================================================================
PRE-REGISTRATION (written before any arm was run; 2026-07-29)
===========================================================================

METRIC. Per season, per pool:

    rate       = side bWAR / denominator      (bat WAR / PA, pit WAR / IP)
    war_x_plus = 100 + 10 * (rate - mu_pool) / sd_pool

mu_pool / sd_pool are the mean and standard deviation of `rate` over the ANCHOR
POOL of that same season. The index is a SINGLE LEG, so its pool z is unit-sd by
construction and needs no re-standardization step (contrast fwdHEM+, a 0.7/0.3
blend of two z legs, whose pool sd is below 1 and which therefore does need one).

WAR SOURCE. bWAR with the two sides kept SEPARATE
(mlb_player_export._war_daily). Batting WAR over plate appearances, pitching WAR
over innings. Never a summed side: summing would divide a two-way player's
pitching WAR by his plate appearances.

ANCHOR POOLS, and why pitchers get two. Three pools, never pooled together:
hitters, qualified-role starters, relievers. A starter-anchored and a
reliever-anchored value must never share one column
(ARKMETRIC_SCALE_CONVENTIONS.md:77), exactly as SEM+ and REM+ coexist as two
metrics rather than one.

VOLUME FLOORS, two tiers (house pattern):

    pool floor (contributes to mu/sd)   50 PA  |  20 IP
    display gate (gets a value)        100 PA  |  40 IP starters, 30 IP relievers

The pool floor is wider than the display gate on purpose: mu/sd are the
population parameters of the 50-PA/20-IP pool, which is the pool the glossary
entry names. The displayed subset is narrower, so its own spread is NARROWER
than 10 points - that is a selection effect of the display gate, not a
denominator defect, and both numbers are reported in the artifact so the
distinction is never silent.

SHRINK: NO. Pre-registered decision, with the reasons stated up front.

  1. The two-tier volume floor is the house instrument for sample control on a
     descriptive index. HEM+ shrinks its wOBA COMPONENTS because wOBA is a
     rate built from six component rates; a WAR rate has no components to
     shrink, only a single noisy numerator.
  2. Shrink is NOT monotone across players: it reorders players who differ in
     sample size, so it cannot ride a "the ranking is preserved" defence the
     way fwdHEM+'s re-standardization or HEM+'s spread gain can. It therefore
     needs its own forward evidence, and no such evidence exists yet.
  3. A descriptive index must describe. Regressing a banked-WAR rate toward the
     league mean makes the number neither a description of what happened nor a
     validated forward estimate.
  4. If shrink were applied, mu and sd would HAVE to come from the SHRUNK pool.
     Taking them from the unshrunk pool is registered defect C3 (aStuff+ ships
     7.16 points per sigma against an advertised 10). Not shrinking removes
     that whole failure mode from the surface.

  The shrink arm is still MEASURED here as arm S, with mu/sd correctly taken
  from the shrunk pool, and the decision rule was fixed before it ran:

     SHIP SHRUNK only if rho(shrunk) - rho(unshrunk) has bootstrap lo95 > 0
     under the primary convention. Otherwise ship unshrunk. A tie is a loss.

NO CLAMPS. True-to-model policy (tools/plus_metric_recal_lab.py:16-21). If a
display cap is ever wanted it goes in as the AP+ two-field pattern
(`*_display` beside the model value), never as a silent clamp.

FORWARD GATE. Does WAR/PA+ in season Y predict the WAR rate in Y+1 better than a
naive baseline? Predictor season Y, outcome season Y+1, both seasons at or above
the DISPLAY gate (the index as shipped), pitchers additionally required to hold
the SAME role in both seasons.

  primary   war_x_plus(Y), unrounded
  target    rate(Y+1); v1 raw pooled, v2 z-scored within the outcome season
  baselines
    rate_pooled  the raw WAR rate in Y with NO within-season standardization.
                 This is the arm that tests whether the standardization earns
                 anything. Within a single season the index is a monotone
                 transform of the rate, so a one-season comparison would be a
                 tautology; across pooled seasons it is not, because the raw
                 rate carries a season-length and run-environment term.
    war_total    total bWAR in Y. The "just look at WAR" baseline.
    ops_plus     hitters: the industry rate index from the same bWAR file.
    ra9_inv      pitchers: negated runs allowed per nine, from the same file.
    placebo      the primary shuffled within predictor season (seeded). The
                 zero-information control; rho must sit at 0.

  GATES, fixed before the run:
    G1 sanity    rho(primary) beats rho(placebo), gap lo95 > 0.
    G2 SHIP      rho(primary) beats the BEST of the real baselines AND that
                 paired gap has lo95 > 0. PASS -> the registry rows carry the
                 artifact. FAIL -> the metric ships as an UNVALIDATED DISPLAY
                 INDEX, eval_artifact null, this artifact cited on the rows as
                 the measurement ledger. Expected outcome is stated here in
                 advance: the rate_pooled baseline is the hard one, because it
                 differs from the index only by a within-season affine, and a
                 loss against it is the LIKELY result. Say so either way.
    G3 shrink    as above.
    G4 3yr       rho(3yr window) beats rho(1yr) on the SAME pair set with gap
                 lo95 > 0 -> the 3yr companion is forward-supported. Otherwise
                 it is a descriptive longer-window read and is registered as
                 one.

WINDOW. Predictor seasons 2012-2024, outcome 2013-2025, 2020 excluded on both
sides (COVID short season). Pairs whose outcome season is incomplete are dropped
by the harness rule, which today removes every 2025->2026 pair.

FROZEN 3-YEAR VINTAGE. proposed_values blocks carry the trailing-window index
for the live season, denominator-weighted across the window, exactly like
hem_plus_3yr: `established` needs 2+ seasons and 600 PA (hitters) / 120 IP
(starters) / 40 IP (relievers) in the window, otherwise `provisional`. The
exporters read those values VERBATIM. Nothing recomputes them at export time.

===========================================================================
RESULT (2026-07-29, and it is a loss on the ship gate)
===========================================================================

G1 PASSES on all three pools: every index beats a zero-information control by a
wide margin (hitters gap lo95 +0.3183, starters +0.1365, relievers +0.0233), so
these numbers carry real signal about the player.

G2 FAILS on all three pools. Plain season bWAR forward-predicts next season's
WAR RATE better than the WAR rate does:

    pool        n      WAR-rate+   season bWAR   gap lo95
    hitters     3845   0.3711      0.4058        -0.0479   resolvable loss
    starters    1396   0.2688      0.2799        -0.0307   CI spans zero
    relievers   1621   0.0886      0.0899        -0.0145   CI spans zero

Mechanism, stated plainly: a season of playing time is itself a talent signal,
and a per-trip rate throws it away. Clubs give innings and plate appearances to
players they believe in, and that belief carries forward. Relievers barely
forward-predict at all on either arm (0.09), which is the same volatility REM+
measured when it landed at 0.236 against a much easier target.

So both metrics ship as UNVALIDATED DISPLAY INDEXES with a null eval artifact,
this file cited on the registry rows as the measurement ledger. That is the
sanctioned path for a descriptive index and the accurate statement, not a
demotion.

G3 fired on hitters (+0.0100) and relievers (+0.0002) and not on starters. The
ship is UNSHRUNK anyway, which is an override of the rule as written, and it is
argued rather than assumed in `shrink_ruling`, with the owner call left open.

G4 PASSES on hitters (0.4022 vs 0.3711, lo95 +0.0116) and relievers (0.1335 vs
0.0886, lo95 +0.0117) and FAILS on starters (0.2965 vs 0.2688, lo95 -0.0076).
The 3-year window ships on all three surfaces for consistency of the board, with
the starter case registered as unresolved rather than claimed.

===========================================================================
AMENDMENT 2026-09-11: THE WAR SOURCE IS THE SERVED PROVIDER (audit F10-01)
===========================================================================

The pre-registration above is left as written; this amends one input, by owner
decision, and nothing else. Every gate, floor, window, seed and decision rule
is unchanged. What moved is the SERIES.

The registration named bWAR because bWAR was the site-wide series on
2026-07-29. From the 2026-09-03 epoch the 1-year board columns read eWAR
(war_source's default provider, via bullpen_export._side_war_by_season) while
this lab kept reading pybaseball's bWAR files directly, so the FROZEN 3-year
columns sat on a different series from the 1-year columns beside them under
copy asserting one scale (measured: 4.0 points mean for starters, 5.1 for
relievers; the batting side is numerically identical because eWAR v2 replaces
only pitching). load_frames now reads war_source.stint_frame on the served
provider: the same war_daily frame with WAR replaced per player-season by the
eWAR side total, every other column (PA, OPS+, IPouts, G, GS, RA) untouched.
Read "bWAR" above as "the served WAR series" for every arm, war_total included.
Both artifacts stamp the basis (`war_provider` and `ewar_generated_at`, the
eWAR build, from bullpen_export.served_war_basis), rerun_window refuses a ledger
measured on another basis, and bullpen_export.join_war_rate_3yr refuses to
serve a multiyear artifact whose provider OR eWAR build is not the one the
1-year columns read. Run the lab after the eWAR artifact is current (see
load_frames): the frozen 3-year value keeps whatever live-season numerator it
was built on.

RE-MEASURED ON eWAR (2026-09-11, same pairs, seed and bootstrap; the frames
for completed seasons are pinned to the eWAR artifact, so these reproduce):

    pool       n     index   season WAR   raw rate   G2 gap lo95   3yr vs 1yr (lo95)
    hitters   3845   0.3711    0.4058      0.3713     -0.0479      0.4022 / 0.3711 (+0.0116)
    starters  1396   0.4726    0.4496      0.4705     -0.0027      0.4766 / 0.4726 (-0.0231)
    relievers 1621   0.2323    0.2267      0.2319     -0.0033      0.2590 / 0.2323 (-0.0035)

Hitters do not move at all (eWAR v2 leaves the batting side equal to bWAR).
Pitchers persist far better on the FIP-priced series (starters 0.2688 -> 0.4726,
relievers 0.0886 -> 0.2323, the ewar_eval gate-2 persistence story), and the
indexes now clear season WAR for starters (gap lo95 +0.0054) but tie the same
rate left unstandardized, so G2 still FAILS on every pool and the rows stay
unvalidated display indexes. Two verdicts flip: arm S no longer fires on
relievers (lo95 -0.0016; it still fires on hitters), and G4 no longer passes on
relievers, so the reliever 3-year column is now a longer window rather than a
forward-supported one, like the starter column already was.

Run: `python tools/war_rate_plus_lab.py`  (writes both artifacts)
     `python tools/war_rate_plus_lab.py --gate-only`   (no artifact write)
     `python tools/war_rate_plus_lab.py --restamp`     (re-derive verdicts only)
"""
from __future__ import annotations

import bisect
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import plus_lab_harness as H   # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
EVAL_PATH = DATA / "war_rate_plus_eval.json"
MULTIYR_PATH = DATA / "war_rate_plus_multiyear_eval.json"

SEED = 20260729
BOOT = 2000

# window
FIRST_PRED, LAST_PRED = 2012, 2024
EXCLUDE_SEASONS = {2020}

# floors (mirrored by the exporters; see bullpen_export.WAR_RATE_* constants)
POOL_MIN_PA, DISPLAY_MIN_PA = 50.0, 100.0
POOL_MIN_IP, DISPLAY_MIN_SP_IP, DISPLAY_MIN_RP_IP = 20.0, 40.0, 30.0
PER_SIGMA = 10.0

# trailing-window "established" thresholds (mirror hem/sem/rem _3yr)
WINDOW_YEARS = 3
EST_MIN_SEASONS = 2
EST_MIN_PA, EST_MIN_SP_IP, EST_MIN_RP_IP = 600.0, 120.0, 40.0


# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #
def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def served_war_basis() -> dict:
    """{war_provider, ewar_generated_at} of the series the SERVED one-year
    columns read, from bullpen_export.served_war_basis, the same function the
    3-year join compares the artifact's stamp against. One definition, so the
    lab cannot stamp a basis the join reads differently."""
    import bullpen_export
    return bullpen_export.served_war_basis()


def war_provider() -> str:
    """The WAR provider the SERVED one-year columns read (bullpen_export
    _side_war_by_season -> war_source.side_war_by_season on the facade default).
    The lab reads the same one, so the 3-year columns and the 1-year columns
    beside them are one series (audit F10-01)."""
    return served_war_basis()["war_provider"]


def _stint_frames(provider: str | None = None):
    """(batting, pitching) war_daily stint frames on `provider` (default: the
    served one). Through war_source, never pybaseball directly: reading
    pybaseball here is how the lab stayed on bWAR for a week after every board
    beside it moved to eWAR."""
    import war_source
    prov = provider or war_provider()
    return (war_source.stint_frame("bat", provider=prov),
            war_source.stint_frame("pit", provider=prov))


def load_frames(provider: str | None = None, *, frames=None) -> dict:
    """{'hit': {(mlbam, season): row}, 'pit': {...}} from the war_daily stint
    frames on the SERVED WAR provider, one row per player-season with the stints
    summed.

    WAR BASIS (audit F10-01, re-pointed 2026-09-11 by owner decision). This read
    pybaseball's bWAR files directly, so after the 2026-09-03 epoch the frozen
    3-year columns stayed bWAR while the 1-year columns beside them moved to
    eWAR. It now reads war_source.stint_frame on the facade default, the same
    provider bullpen_export._side_war_by_season serves: the frame is the
    identical war_daily download with WAR replaced per player-season by the
    eWAR artifact's side total, every other column (PA, OPS+, IPouts, G, GS,
    RA) untouched. Summed over a player-season's stints it reproduces the
    side value the 1-year column divides.

    RUN IT AFTER THE eWAR ARTIFACT IS CURRENT. The numerator is whatever
    data/ewar.json holds for each season, the denominators are today's
    war_daily. For completed seasons the two agree whatever day the lab runs;
    for the live season a stale artifact (the 2026-09-03 hand build, until the
    nightly rebuild of owner decision D11 is running) pairs an old numerator
    with a current denominator and understates this season's rate in the
    frozen 3-year value. The 1-year column carries the same numerator and
    discloses it (war_source.ewar_vintage); the frozen value does not refresh,
    so the lab should follow the eWAR rebuild, not precede it.

    Numerator and denominator come from the SAME source frame, so a stint that
    war_daily carries and StatsAPI does not (or the reverse) can never produce a
    rate with a mismatched denominator. Batting rows flagged as pitchers are
    dropped from the hitter frame: a pitcher's plate appearances are not a
    hitter's sample, and in the universal-DH era they are all far under the pool
    floor anyway.

    `frames` = an already-read (batting, pitching) pair, for a caller that must
    not touch the network (a measurement on the last-good cache)."""
    out = {"hit": {}, "pit": {}}
    bat_df, pit_df = frames if frames is not None else _stint_frames(provider)

    df = bat_df
    for r in df.itertuples(index=False):
        mid, yr, war = _f(r.mlb_ID), _f(r.year_ID), _f(r.WAR)
        if mid is None or yr is None or war is None:
            continue
        if str(getattr(r, "pitcher", "N")).upper().startswith("Y"):
            continue
        k = (int(mid), int(yr))
        c = out["hit"].setdefault(k, {"pa": 0.0, "war": 0.0, "ops_plus_num": 0.0,
                                      "ops_plus_den": 0.0})
        pa = _f(r.PA) or 0.0
        c["pa"] += pa
        c["war"] += war
        op = _f(getattr(r, "OPS_plus", None))
        if op is not None and pa > 0:
            c["ops_plus_num"] += op * pa
            c["ops_plus_den"] += pa

    df = pit_df
    for r in df.itertuples(index=False):
        mid, yr, war = _f(r.mlb_ID), _f(r.year_ID), _f(r.WAR)
        if mid is None or yr is None or war is None:
            continue
        k = (int(mid), int(yr))
        c = out["pit"].setdefault(k, {"ipouts": 0.0, "war": 0.0, "g": 0.0,
                                      "gs": 0.0, "ra": 0.0})
        c["ipouts"] += _f(r.IPouts) or 0.0
        c["war"] += war
        c["g"] += _f(r.G) or 0.0
        c["gs"] += _f(r.GS) or 0.0
        c["ra"] += _f(r.RA) or 0.0

    for k, c in out["hit"].items():
        c["ops_plus"] = (c["ops_plus_num"] / c["ops_plus_den"]
                         if c["ops_plus_den"] else None)
    for k, c in out["pit"].items():
        c["ip"] = c["ipouts"] / 3.0
        # sem_plus.MIN_START_SHARE: GS/G at or above 0.50 is a starter
        c["role"] = "SP" if (c["g"] and c["gs"] / c["g"] >= 0.50) else "RP"
        c["ra9"] = (c["ra"] * 27.0 / c["ipouts"]) if c["ipouts"] else None
    return out


# --------------------------------------------------------------------------- #
# the index
# --------------------------------------------------------------------------- #
def _mu_sd(vals):
    n = len(vals)
    if n < 2:
        return None, None
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5
    return mu, (sd or None)


def index_season(frame: dict, season: int, *, pool: str) -> dict:
    """{mlbam: {rate, plus, plus_shrunk, denom, war, ...}} for one season and one
    anchor pool. `pool` is 'hit' | 'SP' | 'RP'."""
    side = "hit" if pool == "hit" else "pit"
    dkey = "pa" if side == "hit" else "ip"
    floor = POOL_MIN_PA if side == "hit" else POOL_MIN_IP
    rows = {}
    for (mid, yr), c in frame[side].items():
        if yr != season:
            continue
        if side == "pit" and c["role"] != pool:
            continue
        d = c[dkey]
        if d < floor or d <= 0:
            continue
        rows[mid] = dict(c, denom=d, rate=c["war"] / d)
    if len(rows) < 2:
        return {}
    mu, sd = _mu_sd([r["rate"] for r in rows.values()])
    if sd is None:
        return {}
    # arm S companion: regress the rate toward the pool rate by sample size,
    # K = the pool MEDIAN denominator, then take mu/sd from the SHRUNK pool
    # (defect C3: never from the unshrunk one).
    dens = sorted(r["denom"] for r in rows.values())
    K = dens[len(dens) // 2]
    pool_rate = sum(r["war"] for r in rows.values()) / sum(r["denom"] for r in rows.values())
    for r in rows.values():
        r["rate_shrunk"] = (r["war"] + pool_rate * K) / (r["denom"] + K)
    mu_s, sd_s = _mu_sd([r["rate_shrunk"] for r in rows.values()])
    for r in rows.values():
        r["plus"] = 100.0 + PER_SIGMA * (r["rate"] - mu) / sd
        r["plus_shrunk"] = (100.0 + PER_SIGMA * (r["rate_shrunk"] - mu_s) / sd_s
                            if sd_s else None)
    return {"players": rows, "mu": mu, "sd": sd, "n": len(rows),
            "shrink_K": K, "pool_rate": pool_rate, "mu_shrunk": mu_s,
            "sd_shrunk": sd_s}


def _display_min(pool: str) -> float:
    return {"hit": DISPLAY_MIN_PA, "SP": DISPLAY_MIN_SP_IP,
            "RP": DISPLAY_MIN_RP_IP}[pool]


# --------------------------------------------------------------------------- #
# forward gate
# --------------------------------------------------------------------------- #
def forward_pairs(frame: dict, pool: str, *, today: date | None = None) -> list[dict]:
    """Y -> Y+1 pairs at or above the DISPLAY gate in both seasons (the index as
    shipped), same role in both seasons for pitchers, outcome season complete."""
    gate = _display_min(pool)
    seasons = [y for y in range(FIRST_PRED, LAST_PRED + 1) if y not in EXCLUDE_SEASONS]
    idx = {}
    for y in set(seasons) | {y + 1 for y in seasons}:
        if y in EXCLUDE_SEASONS:
            continue
        idx[y] = index_season(frame, y, pool=pool)
    out = []
    for y in seasons:
        y2 = y + 1
        if y2 in EXCLUDE_SEASONS or not idx.get(y) or not idx.get(y2):
            continue
        if not H.season_complete(y2, today):
            continue
        a, b = idx[y]["players"], idx[y2]["players"]
        for mid, ra in a.items():
            rb = b.get(mid)
            if rb is None:
                continue
            if ra["denom"] < gate or rb["denom"] < gate:
                continue
            out.append({
                "mlbam": mid, "pred_season": y, "out_season": y2,
                "plus": ra["plus"], "plus_shrunk": ra["plus_shrunk"],
                "rate": ra["rate"], "war_total": ra["war"], "denom": ra["denom"],
                "ops_plus": ra.get("ops_plus"), "ra9": ra.get("ra9"),
                "target": rb["rate"],
            })
    return out


def _cols(pairs: list[dict], pool: str) -> tuple[dict, list[str], list[dict]]:
    """Predictor columns for the gate.

    A pair missing ANY arm's value is dropped from the whole comparison, so every
    arm scores on one identical row set. Nothing is mean-imputed: filling a
    missing predictor with the pool mean is the registered fabrication trick
    (the mean-impute sensitivity block in data/xfv_wrc_eval.json)."""
    names = ["plus", "plus_shrunk", "rate", "war_total"]
    names.append("ops_plus" if pool == "hit" else "ra9_inv")
    keep = []
    for p in pairs:
        if pool == "hit":
            p["ops_plus_v"] = p.get("ops_plus")
            extra = p["ops_plus_v"]
        else:
            p["ra9_inv"] = (-p["ra9"]) if p.get("ra9") is not None else None
            extra = p["ra9_inv"]
        if p["plus"] is None or p["plus_shrunk"] is None or extra is None:
            continue
        keep.append(p)
    cols = {
        "plus": [p["plus"] for p in keep],
        "plus_shrunk": [p["plus_shrunk"] for p in keep],
        "rate": [p["rate"] for p in keep],
        "war_total": [p["war_total"] for p in keep],
    }
    cols["ops_plus" if pool == "hit" else "ra9_inv"] = [
        (p["ops_plus_v"] if pool == "hit" else p["ra9_inv"]) for p in keep]
    return cols, names, keep


def gate_pool(frame: dict, pool: str, *, today: date | None = None) -> dict:
    pairs = forward_pairs(frame, pool, today=today)
    cols, names, keep = _cols(pairs, pool)
    n = len(keep)
    if n < 50:
        return {"n_forward_pairs": n, "error": "too few pairs to gate"}
    tgt_raw = [p["target"] for p in keep]
    out_seasons = [p["out_season"] for p in keep]
    pred_seasons = [p["pred_season"] for p in keep]
    players = [p["mlbam"] for p in keep]
    tgt_z = H.zscore_within(out_seasons, tgt_raw)

    # zero-information control: shuffle the primary WITHIN predictor season
    rng = random.Random(SEED)
    by_season: dict = {}
    for i, s in enumerate(pred_seasons):
        by_season.setdefault(s, []).append(i)
    placebo = [None] * n
    for s, idxs in by_season.items():
        vals = [cols["plus"][i] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            placebo[i] = v
    cols["placebo"] = placebo

    base_names = [x for x in names if x != "plus"] + ["placebo"]
    res = {}
    for conv, tgt in (("v1", tgt_raw), ("v2", tgt_z)):
        rho_p = H.spearman(cols["plus"], tgt)
        rhos = {b: H.spearman(cols[b], tgt) for b in base_names}
        baselines = {b: cols[b] for b in base_names}
        if conv == "v1":
            gaps = H.iid_boot_gaps(cols["plus"], baselines, tgt, BOOT, SEED)
        else:
            gaps = H.cluster_boot_gaps(cols["plus"], baselines, tgt, players,
                                       pred_seasons, BOOT, SEED)
        # arm S: shrunk as the primary, unshrunk as its baseline
        rho_s = H.spearman(cols["plus_shrunk"], tgt)
        if conv == "v1":
            s_gap = H.iid_boot_gaps(cols["plus_shrunk"], {"plus": cols["plus"]},
                                    tgt, BOOT, SEED)
        else:
            s_gap = H.cluster_boot_gaps(cols["plus_shrunk"], {"plus": cols["plus"]},
                                        tgt, players, pred_seasons, BOOT, SEED)
        res[conv] = {
            "rho_primary": round(rho_p, 4),
            "rho_baselines": {k: (round(v, 4) if v is not None else None)
                              for k, v in rhos.items()},
            "gap_ci_primary_minus_baseline": gaps,
            "arm_S_shrunk": {"rho": round(rho_s, 4),
                             "gap_ci_shrunk_minus_unshrunk": s_gap["plus"]},
        }
        if conv == "v2":
            res[conv]["cluster"] = H.cluster_summary(players, pred_seasons)
    return {
        "n_forward_pairs": n,
        "pred_seasons": sorted(set(pred_seasons)),
        "out_seasons": sorted(set(out_seasons)),
        "results_by_convention": res,
        "g3b_volume_control": _volume_control(cols, keep, tgt_z, players, pred_seasons),
    }


def _volume_control(cols: dict, keep: list[dict], tgt_z: list[float],
                    players: list, pred_seasons: list) -> dict:
    """POST-HOC diagnostic, added AFTER arm S fired, and labelled as post-hoc.

    Arm S (shrink) beats the unshrunk index on forward rho. The question this
    answers is WHY. Shrinking a rate toward the pool by sample size mixes the
    denominator into the number: a 100-PA hitter is pulled most of the way to
    league average, a 600-PA hitter barely at all, so the shrunk column is part
    rate and part volume. If that is the whole story, then arm S wins for the
    same reason `war_total` wins, the gain is a VOLUME LEAK rather than a better
    rate estimate, and it does not license shrinking a rate index.

    Two measurements, no preference:
      (a) each arm's rank correlation with the predictor denominator itself;
      (b) the shrunk-minus-unshrunk gap inside predictor-volume TERCILES, where
          both arms see a narrow band of denominators.
    If (a) orders the arms the same way forward rho orders them, and (b) shows
    the gap concentrated in the low-volume tercile, the leak reading holds."""
    dens = [p.get("denom") for p in keep]
    ok = [i for i, d in enumerate(dens) if isinstance(d, (int, float)) and d > 0]
    if len(ok) < 60:
        return {"error": "no usable denominator column"}
    dv = [dens[i] for i in ok]
    out = {"post_hoc": True,
           "rho_with_predictor_denominator": {
               k: (lambda r: round(r, 4) if r is not None else None)(
                   H.spearman([cols[k][i] for i in ok], dv))
               for k in ("plus", "plus_shrunk", "war_total")}}
    cuts = sorted(dv)
    lo, hi = cuts[len(cuts) // 3], cuts[2 * len(cuts) // 3]
    bands = {"low": lambda d: d <= lo, "mid": lambda d: lo < d <= hi,
             "high": lambda d: d > hi}
    tercile = {}
    for name, pred in bands.items():
        sel = [i for i in ok if pred(dens[i])]
        if len(sel) < 60:
            tercile[name] = {"n": len(sel), "error": "too few"}
            continue
        t = [tgt_z[i] for i in sel]
        ru = H.spearman([cols["plus"][i] for i in sel], t)
        rs = H.spearman([cols["plus_shrunk"][i] for i in sel], t)
        gap = H.cluster_boot_gaps([cols["plus_shrunk"][i] for i in sel],
                                  {"plus": [cols["plus"][i] for i in sel]}, t,
                                  [players[i] for i in sel],
                                  [pred_seasons[i] for i in sel], 400, SEED)
        tercile[name] = {
            "n": len(sel),
            "denominator_range": [round(min(dens[i] for i in sel), 1),
                                  round(max(dens[i] for i in sel), 1)],
            "rho_unshrunk": round(ru, 4) if ru is not None else None,
            "rho_shrunk": round(rs, 4) if rs is not None else None,
            "gap_ci_shrunk_minus_unshrunk": gap["plus"],
        }
    out["by_predictor_volume_tercile"] = tercile
    return out


def _lo95(ci: dict | None) -> float:
    v = (ci or {}).get("lo95")
    return float(v) if isinstance(v, (int, float)) else -9.0


def verdict_for(block: dict, *, conv: str = "v2") -> dict:
    """Apply the pre-registered G1/G2/G3 rules to one pool's gate block."""
    if "error" in block:
        return {"g1_sanity": None, "g2_ship": None, "shrink": "no (unmeasurable)",
                "status": "unresolved", "note": block["error"]}
    r = block["results_by_convention"][conv]
    rp = r["rho_primary"]
    gaps = r["gap_ci_primary_minus_baseline"]
    g1 = _lo95(gaps.get("placebo")) > 0
    # G2's baseline set is the PRE-REGISTERED one: rate_pooled, war_total, and
    # the side's rate-skill index. `plus_shrunk` is scored in the same sweep for
    # convenience but it is arm S, an ALTERNATE PRIMARY, not a naive baseline, so
    # it belongs to G3 and must not be eligible to become G2's "best baseline".
    _NOT_A_BASELINE = ("placebo", "plus_shrunk")
    real = {k: v for k, v in r["rho_baselines"].items() if k not in _NOT_A_BASELINE}
    best = max(real, key=lambda k: (real[k] if real[k] is not None else -9))
    g2_gap = gaps.get(best) or {}
    g2 = bool(rp > (real[best] if real[best] is not None else -9)
              and _lo95(g2_gap) > 0)
    s = r["arm_S_shrunk"]["gap_ci_shrunk_minus_unshrunk"] or {}
    g3 = _lo95(s) > 0
    return {
        "convention": conv,
        "g1_sanity_vs_placebo": {"pass": g1, "gap": gaps.get("placebo")},
        "g2_ship_vs_best_baseline": {"pass": g2, "best_baseline": best,
                                     "baseline_set": sorted(real),
                                     "rho_primary": rp,
                                     "rho_baseline": real[best],
                                     "gap": g2_gap},
        "g3_shrink": {"pre_registered_rule_fired": g3,
                      "gap_shrunk_minus_unshrunk": s,
                      "rho_shrunk": r["arm_S_shrunk"]["rho"],
                      "rho_unshrunk": rp},
        "status": "validated" if g2 else "unvalidated_display_index",
    }


def shrink_ruling(block: dict, *, conv: str = "v2") -> dict:
    """The shipped shrink decision, with the pre-registration conflict stated
    rather than buried.

    Arm S's pre-registered rule ("ship shrunk if the forward gap lo95 > 0") FIRED
    on some pools. The shipped index is nonetheless UNSHRUNK, and this block is
    the argument, so an owner can overturn it from one place:

      1. Shrinking changes what the number MEANS. The column is titled WAR per
         plate appearance. With K at the pool median denominator, a player right
         at the 100-PA display gate would publish about 70 percent league average,
         so `war / pa` on his own row would no longer reproduce his index. The
         conventions doc's rule for that situation is to give the two numbers
         different names, not to let them differ silently.
      2. The measured gain sits at or under this repo's own noise floor: a lo95
         of +0.0002 is exactly the "small win" that the gate standard calls a
         NULL.
      3. It does not survive a volume control. Pooled, shrink wins; inside
         predictor-volume terciles, where both arms see a narrow band of
         denominators, the gain collapses and mostly fails to clear zero. The
         pooled win is between-band reordering (low-volume players pushed toward
         100 and therefore under high-volume ones), which is the same information
         `war_total` carries, not a better rate estimate.
      4. G2 FAILED, so the shipped surface makes no forward claim at all. Tuning
         a descriptive index for a forward rho it does not advertise is optimising
         the wrong thing.

    Reasons 1 and 4 were available before the run; reason 3 comes from the
    post-hoc g3b diagnostic and is labelled as such."""
    if "error" in block:
        return {"shipped": "unshrunk", "note": block["error"]}
    v = verdict_for(block, conv=conv)
    g3 = v["g3_shrink"]
    vc = block.get("g3b_volume_control") or {}
    terciles = vc.get("by_predictor_volume_tercile") or {}
    within = {k: (t.get("gap_ci_shrunk_minus_unshrunk") or {}).get("mean")
              for k, t in terciles.items() if "error" not in t}
    cleared = [k for k, t in terciles.items()
               if "error" not in t and _lo95(t.get("gap_ci_shrunk_minus_unshrunk")) > 0]
    return {
        "shipped": "unshrunk",
        "pre_registered_rule_fired": g3["pre_registered_rule_fired"],
        "pooled_gap": g3["gap_shrunk_minus_unshrunk"],
        "within_volume_tercile_gap_means": within,
        "terciles_clearing_zero": cleared,
        "post_hoc_control": True,
        "g2_failed_so_no_forward_claim_is_shipped":
            not verdict_for(block, conv=conv)["g2_ship_vs_best_baseline"]["pass"],
        "owner_call": (
            "OPEN. The pre-registered rule as written says ship shrunk on this "
            "pool, and the ship is unshrunk on the four reasons in "
            "shrink_ruling.__doc__. Registered here as a measured candidate rather "
            "than acted on silently."
            if g3["pre_registered_rule_fired"] else
            "NONE. The pre-registered rule did not fire on this pool, so the "
            "unshrunk default stands with nothing to override."),
    }


# --------------------------------------------------------------------------- #
# G4 + the frozen trailing-window vintage
# --------------------------------------------------------------------------- #
def window_values(frame: dict, pool: str, season: int, years: int = WINDOW_YEARS) -> dict:
    """{mlbam: {value, n_seasons, denom_total, tag}} - the denominator-weighted
    mean of the per-season index over the trailing `years` seasons ending at
    `season` (the hem_plus_3yr recipe: weight each season by its own sample).

    Contributing seasons must clear the DISPLAY gate, not just the pool floor. The
    3-year column is a mean of the values the board would publish, so admitting a
    55-PA season the 1-year column refuses to print would let a player hold a
    3-year value while his 1-year cell sits blank, and would put small-sample
    noise at the top of the 3-year board. The pool floor still governs mu and sd,
    because that is what anchors the scale."""
    gate = _display_min(pool)
    ws = [season - i for i in range(years)]
    idx = {y: index_season(frame, y, pool=pool) for y in ws}
    est_min = {"hit": EST_MIN_PA, "SP": EST_MIN_SP_IP, "RP": EST_MIN_RP_IP}[pool]
    acc: dict = {}
    for y in ws:
        blk = idx.get(y) or {}
        for mid, r in (blk.get("players") or {}).items():
            if r["denom"] < gate:
                continue
            a = acc.setdefault(mid, {"num": 0.0, "den": 0.0, "n_seasons": 0})
            a["num"] += r["plus"] * r["denom"]
            a["den"] += r["denom"]
            a["n_seasons"] += 1
    out = {}
    for mid, a in acc.items():
        if a["den"] <= 0:
            continue
        est = a["n_seasons"] >= EST_MIN_SEASONS and a["den"] >= est_min
        out[mid] = {"value": a["num"] / a["den"], "n_seasons": a["n_seasons"],
                    "denom_total": round(a["den"], 1),
                    "tag": "established" if est else "provisional"}
    return out


def gate_window(frame: dict, pool: str, *, today: date | None = None) -> dict:
    """G4: trailing-window index at Y vs single-season index at Y, on the SAME
    pair set, against the Y+1 rate."""
    gate = _display_min(pool)
    seasons = [y for y in range(FIRST_PRED, LAST_PRED + 1) if y not in EXCLUDE_SEASONS]
    rows = []
    for y in seasons:
        y2 = y + 1
        if y2 in EXCLUDE_SEASONS or not H.season_complete(y2, today):
            continue
        one = index_season(frame, y, pool=pool)
        nxt = index_season(frame, y2, pool=pool)
        if not one or not nxt:
            continue
        win = window_values(frame, pool, y)
        for mid, r in one["players"].items():
            rb = nxt["players"].get(mid)
            w = win.get(mid)
            if rb is None or w is None:
                continue
            if r["denom"] < gate or rb["denom"] < gate:
                continue
            rows.append({"mlbam": mid, "pred_season": y, "out_season": y2,
                         "one": r["plus"], "win": w["value"], "target": rb["rate"]})
    n = len(rows)
    if n < 50:
        return {"n_forward_pairs": n, "error": "too few pairs to gate"}
    tgt_raw = [r["target"] for r in rows]
    outs = [r["out_season"] for r in rows]
    preds = [r["pred_season"] for r in rows]
    players = [r["mlbam"] for r in rows]
    tgt_z = H.zscore_within(outs, tgt_raw)
    res = {}
    for conv, tgt in (("v1", tgt_raw), ("v2", tgt_z)):
        prim = [r["win"] for r in rows]
        base = {"one_season": [r["one"] for r in rows]}
        if conv == "v1":
            gap = H.iid_boot_gaps(prim, base, tgt, BOOT, SEED)
        else:
            gap = H.cluster_boot_gaps(prim, base, tgt, players, preds, BOOT, SEED)
        res[conv] = {"rho_window": round(H.spearman(prim, tgt), 4),
                     "rho_one_season": round(H.spearman(base["one_season"], tgt), 4),
                     "gap_ci_window_minus_one": gap["one_season"]}
    g4 = bool(_lo95(res["v2"]["gap_ci_window_minus_one"]) > 0
              and res["v2"]["rho_window"] > res["v2"]["rho_one_season"])
    return {"n_forward_pairs": n, "window_years": WINDOW_YEARS,
            "results_by_convention": res,
            "g4_window_beats_one_season": {"pass": g4, "convention": "v2"}}


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #
_POOL_META = {
    "hit": ("war_pa_plus", "WAR/PA+", "hitters with 50+ PA", "pa"),
    "SP": ("war_ip_plus", "WAR/IP+ (starter pool)", "starters with 20+ IP", "ip"),
    "RP": ("war_ip_plus", "WAR/IP+ (reliever pool)", "relievers with 20+ IP", "ip"),
}


def _pct_map(vals: dict) -> dict:
    xs = sorted(v["value"] for v in vals.values())
    n = len(xs)
    out = {}
    for mid, v in vals.items():
        lo = bisect.bisect_left(xs, v["value"])
        hi = bisect.bisect_right(xs, v["value"])
        out[mid] = int(round(100.0 * ((lo + hi) / 2.0) / n)) if n else None
    return out


def build_multiyear(frame: dict, season: int) -> dict:
    blocks = {}
    for pool, key in (("hit", "hit"), ("SP", "sp"), ("RP", "rp")):
        metric, disp, anchor, dkey = _POOL_META[pool]
        vals = window_values(frame, pool, season)
        pcts = _pct_map(vals)
        est_min = {"hit": EST_MIN_PA, "SP": EST_MIN_SP_IP, "RP": EST_MIN_RP_IP}[pool]
        blocks[key] = {
            "season": season,
            "window": [season - i for i in range(WINDOW_YEARS)][::-1],
            "metric": f"{metric}_3yr",
            "display_name": f"{disp} 3yr",
            "anchor_pool": anchor,
            "definition": (
                f"{dkey.upper()}-weighted mean {disp} over the trailing "
                f"{WINDOW_YEARS} seasons. Steadier than one season because a "
                f"WAR rate carries fielding and baserunning on top of the bat "
                f"or the arm. tag is 'established' with {EST_MIN_SEASONS}+ "
                f"seasons and {est_min:g} {dkey.upper()} in the window, "
                f"otherwise 'provisional'."),
            "n_with_value": len(vals),
            "players": {str(mid): {
                f"{metric}_3yr": int(round(v["value"])),
                f"{metric}_3yr_raw": round(v["value"], 2),
                "pct": pcts[mid], "tag": v["tag"],
                "n_seasons": v["n_seasons"], "denom_total": v["denom_total"],
            } for mid, v in vals.items()},
        }
    return blocks


def _basis_stamp(provider: str) -> dict:
    """What series the artifact was measured on: served_war_basis(), i.e.
    `war_provider` plus `ewar_generated_at` (the eWAR build, which a hand
    rebuild moves and the nightly does not). bullpen_export.join_war_rate_3yr
    compares both with the series the 1-year columns serve and refuses a
    mismatch, so a stale artifact on another provider OR another eWAR build
    blanks the 3-year columns instead of sitting beside them under one scale."""
    basis = served_war_basis()
    if basis["war_provider"] != provider:
        raise RuntimeError(f"frames were read on {provider} but the served "
                           f"provider is {basis['war_provider']}")
    return basis


def main(argv: list[str], *, frames=None) -> int:
    """`frames`: an already-read (batting, pitching) stint-frame pair on the
    served provider, for a measurement that must not touch the network."""
    t0 = time.time()
    gate_only = "--gate-only" in argv
    prov = war_provider()
    print(f"loading WAR frames (provider {prov})...")
    frame = load_frames(prov, frames=frames)
    print(f"  hit {len(frame['hit'])} player-seasons, pit {len(frame['pit'])}")

    season = date.today().year
    pools = {}
    for pool in ("hit", "SP", "RP"):
        print(f"gating pool {pool}...")
        blk = gate_pool(frame, pool)
        blk["verdict"] = verdict_for(blk)
        blk["window_gate"] = gate_window(frame, pool)
        # live-season anchor descriptives: the proof that 10 points is one sd of
        # the ANCHOR pool, plus the narrower spread of the DISPLAYED subset.
        live = index_season(frame, season, pool=pool)
        if live:
            gatev = _display_min(pool)
            shown = [r["plus"] for r in live["players"].values()
                     if r["denom"] >= gatev]
            mu_s, sd_s = _mu_sd(shown)
            pool_mu, pool_sd = _mu_sd([r["plus"] for r in live["players"].values()])
            blk["live_season_scale_check"] = {
                "season": season,
                "advertised_points_per_sigma": PER_SIGMA,
                "anchor_pool_n": live["n"],
                "anchor_pool_plus_mean": round(pool_mu, 3),
                # = points delivered per anchor-pool sigma. This is the exact
                # number aStuff+ gets wrong (7.16 against an advertised 10).
                "measured_points_per_anchor_pool_sigma": round(pool_sd, 3),
                "displayed_n": len(shown),
                "displayed_plus_mean": round(mu_s, 2) if mu_s else None,
                "measured_points_per_displayed_sigma": round(sd_s, 2) if sd_s else None,
                "note": ("measured_points_per_anchor_pool_sigma must equal 10: the "
                         "index is a single leg z-scored against this pool's own "
                         "mu/sd, so there is nothing to re-standardize. The "
                         "displayed subset is narrower because the display gate "
                         "removes the noisy low-volume tail, which is selection, "
                         "not a denominator defect."),
            }
        blk["shrink_ruling"] = shrink_ruling(blk)
        pools[pool] = blk
        v = blk["verdict"]
        print(f"  n={blk.get('n_forward_pairs')} "
              f"rho={v.get('g2_ship_vs_best_baseline', {}).get('rho_primary')} "
              f"G1={v.get('g1_sanity_vs_placebo', {}).get('pass')} "
              f"G2={v.get('g2_ship_vs_best_baseline', {}).get('pass')} "
              f"G3fired={v.get('g3_shrink', {}).get('pre_registered_rule_fired')} "
              f"G4win={blk['window_gate'].get('g4_window_beats_one_season', {}).get('pass')}")

    art = {
        "generated_at": date.today().isoformat(),
        "experiment": "WAR-RATE-1",
        "model": "war_pa_plus / war_ip_plus",
        "seed": SEED,
        "harness": H.convention_meta(
            "next-season WAR rate (raw, pooled across seasons)",
            "next-season WAR rate",
            primary="v2"),
        "conventions": {
            "scale": "100 + 10z (ARKMETRIC_SCALE_CONVENTIONS convention 3)",
            "war_source": (f"{prov} (war_source.stint_frame on the provider the "
                           "1-year board columns serve), batting and pitching "
                           "sides kept SEPARATE; never a summed side. bWAR until "
                           "the 2026-09-11 re-point (audit F10-01)"),
            "denominators": "PA for hitters, IP for pitchers",
            "anchor_pools": ("three, never pooled: hitters, starters (GS/G >= 0.50), "
                             "relievers. A starter-anchored and a reliever-anchored "
                             "value never share a column."),
            "floors": {"pool_min_pa": POOL_MIN_PA, "display_min_pa": DISPLAY_MIN_PA,
                       "pool_min_ip": POOL_MIN_IP,
                       "display_min_sp_ip": DISPLAY_MIN_SP_IP,
                       "display_min_rp_ip": DISPLAY_MIN_RP_IP},
            "shrink": "NONE (pre-registered; arm S measured and reported per pool)",
            "clamp": "none (true-to-model policy)",
            "excluded": "2020",
            "predictors": "unrounded index values; display rounding never enters the gate",
            "imputation": "NONE. A pair missing any arm's value is dropped from every arm.",
        },
        "pools": pools,
        **_basis_stamp(prov),
    }
    art["verdict"] = _overall(pools)
    print("\n" + art["verdict"]["summary"])
    art["runtime_seconds"] = round(time.time() - t0, 1)

    if not gate_only:
        EVAL_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print(f"wrote {EVAL_PATH.relative_to(ROOT)}")
        my = {
            "generated_at": date.today().isoformat(),
            "experiment": "WAR-RATE-1 trailing window",
            "model": "war_pa_plus_3yr / war_ip_plus_3yr",
            "note": ("FROZEN VINTAGE. The exporters read these values VERBATIM; "
                     "nothing recomputes them at export time, so a board can show "
                     "a same-day 1-year value beside a 3-year value frozen "
                     "earlier. Three blocks because the three anchor pools are "
                     "three separate metrics."),
            "gates": {p: pools[p]["window_gate"].get("g4_window_beats_one_season")
                      for p in pools},
            **_basis_stamp(prov),
            "proposed_values": build_multiyear(frame, season),
        }
        MULTIYR_PATH.write_text(json.dumps(my, indent=1), encoding="utf-8")
        for k, b in my["proposed_values"].items():
            print(f"  multiyear {k}: {b['n_with_value']} players")
        print(f"wrote {MULTIYR_PATH.relative_to(ROOT)}")
    return 0


def _overall(pools: dict) -> dict:
    g1 = {p: pools[p]["verdict"].get("g1_sanity_vs_placebo", {}).get("pass")
          for p in pools}
    g2 = {p: pools[p]["verdict"].get("g2_ship_vs_best_baseline", {}).get("pass")
          for p in pools}
    g3 = {p: pools[p]["verdict"].get("g3_shrink", {}).get("pre_registered_rule_fired")
          for p in pools}
    g4 = {p: pools[p]["window_gate"].get("g4_window_beats_one_season", {}).get("pass")
          for p in pools}
    any_ship = any(bool(v) for v in g2.values())
    fired = [p for p in g3 if g3[p]]
    return {
        "g1_beats_zero_information_control_by_pool": g1,
        "g2_by_pool": g2,
        "g3_shrink_rule_fired_by_pool": g3,
        "g4_window_by_pool": g4,
        "shrink_decision": (
            "UNSHRUNK on every pool. " + (
                f"The pre-registered arm-S rule FIRED on {fired} and is being "
                f"overridden, not ignored: see pools[*].shrink_ruling for the "
                f"argument and the open owner call."
                if fired else
                "Arm S did not clear its lo95 > 0 bar on any pool, so the "
                "pre-registered default stands with nothing to override.")),
        "summary": _summary(pools, g1, g2, any_ship),
    }


_POOL_NAMES = {"hit": "Hitters (WAR/PA+)", "SP": "Starters (WAR/IP+)",
               "RP": "Relievers (WAR/IP+)"}
_BASELINE_NAMES = {"war_total": "plain season WAR on the same series",
                   "rate": "the same rate left unstandardized",
                   "ops_plus": "OPS+", "ra9_inv": "negated runs allowed per nine"}


def _summary(pools: dict, g1: dict, g2: dict, any_ship: bool) -> str:
    """The ledger's headline, DERIVED per pool from verdict_for() rather than
    typed once for all three. A fixed sentence ("they do not beat plain season
    WAR ... a per-trip rate throws playing time away") was true on bWAR for every
    pool and is false on eWAR for starters, whose index clears season WAR and
    loses only to the unstandardized rate. So each pool names its own binding
    baseline and gap, and the playing-time mechanism is stated only for pools
    where season WAR is the baseline that binds."""
    def _f(x, sign=False):
        return "n/a" if not isinstance(x, (int, float)) else (
            f"{x:+.4f}" if sign else f"{x:.4f}")

    lines, playing_time = [], []
    for p in pools:
        v = pools[p].get("verdict") or {}
        g = v.get("g2_ship_vs_best_baseline") or {}
        if not g:
            lines.append(f"{_POOL_NAMES.get(p, p)}: unmeasurable.")
            continue
        best = g.get("best_baseline")
        s = (f"{_POOL_NAMES.get(p, p)}: index {_f(g.get('rho_primary'))} vs "
             f"{_BASELINE_NAMES.get(best, best)} {_f(g.get('rho_baseline'))} "
             f"(gap lo95 {_f((g.get('gap') or {}).get('lo95'), True)}), "
             f"G2 {'PASS' if g.get('pass') else 'FAIL'}")
        if best != "war_total":
            r = pools[p]["results_by_convention"][v.get("convention", "v2")]
            wt = (r.get("gap_ci_primary_minus_baseline") or {}).get("war_total") or {}
            lo = wt.get("lo95")
            s += (f"; against season WAR ({_f(r['rho_baselines'].get('war_total'))}) "
                  f"it {'clears' if isinstance(lo, (int, float)) and lo > 0 else 'does not clear'} "
                  f"(lo95 {_f(lo, True)})")
        elif not g.get("pass"):
            playing_time.append(_POOL_NAMES.get(p, p).split(" ")[0].lower())
        lines.append(s + ".")
    sig = [_POOL_NAMES.get(p, p).split(" ")[0].lower() for p in pools if g1.get(p)]
    head = ("PASS on at least one pool. " if any_ship else "NO PASS on the ship gate. ")
    head += (f"The indexes carry real signal (they beat a zero-information "
             f"control) on {', '.join(sig) if sig else 'no pool'}. ")
    tail = (" They ship as validated where G2 passed and as unvalidated display "
            "indexes elsewhere." if any_ship else
            " They ship as UNVALIDATED DISPLAY INDEXES with eval_artifact null, "
            "which is the sanctioned path for a descriptive index. This artifact "
            "is the measurement ledger, cited on the registry rows.")
    if playing_time:
        tail += (f" Where season WAR itself is the binding baseline "
                 f"({', '.join(playing_time)}), the mechanism is worth stating "
                 f"plainly: a season of playing time is itself a talent signal, "
                 f"and a per-trip rate throws it away.")
    return head + " ".join(lines) + tail


def rerun_window(argv: list[str] | None = None) -> int:
    """Re-measure ONLY the trailing-window gate (G4) and rebuild the frozen
    multiyear artifact, patching them into the committed eval file.

    Exists because the window definition changed (contributing seasons must clear
    the display gate) and G4 is the only gate that reads it: gate_pool's arms are
    single-season and are not touched, so re-running them would be recomputation
    for its own sake. Everything else in the artifact is left exactly as
    measured."""
    art = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    served = served_war_basis()
    prov = served["war_provider"]
    had = {"war_provider": art.get("war_provider") or "bwar",
           "ewar_generated_at": art.get("ewar_generated_at")}
    if had != served:
        # The single-season arms this path keeps were measured on another
        # series (another provider, or another eWAR build); patching only the
        # window gate would ship a mixed-basis ledger.
        print(f"REFUSED: the committed ledger was measured on {had} and the "
              f"served series is {served}; run the full lab "
              f"(python tools/war_rate_plus_lab.py)")
        return 2
    print(f"loading WAR frames (provider {prov})...")
    frame = load_frames(prov)
    season = date.today().year
    for pool in ("hit", "SP", "RP"):
        print(f"re-measuring the window gate for {pool}...")
        blk = art["pools"][pool]
        blk["window_gate"] = gate_window(frame, pool)
        blk["window_gate"]["contributing_season_floor"] = (
            f"display gate ({_display_min(pool):g}), not the pool floor")
        blk["shrink_ruling"] = shrink_ruling(blk)
        w = blk["window_gate"]
        print(f"  n={w.get('n_forward_pairs')} "
              f"{w.get('results_by_convention', {}).get('v2')} "
              f"G4={w.get('g4_window_beats_one_season', {}).get('pass')}")
    art["verdict"] = _overall(art["pools"])
    art["restamped_at"] = date.today().isoformat()
    art["restamp_note"] = (
        "Window gate (G4) re-measured 2026-07-29 after the trailing-window "
        "definition was tightened so a contributing season must clear the DISPLAY "
        "gate rather than the pool floor. The single-season arms (G1, G2, arm S, "
        "the volume control) do not read the window and are unchanged from their "
        "original measurement. Arm S was also removed from G2's baseline set, "
        "where the pre-registration never put it.")
    EVAL_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(f"wrote {EVAL_PATH.relative_to(ROOT)}")
    my = json.loads(MULTIYR_PATH.read_text(encoding="utf-8"))
    my["generated_at"] = date.today().isoformat()
    my["gates"] = {p: art["pools"][p]["window_gate"].get("g4_window_beats_one_season")
                   for p in art["pools"]}
    my.update(_basis_stamp(prov))
    my["proposed_values"] = build_multiyear(frame, season)
    MULTIYR_PATH.write_text(json.dumps(my, indent=1), encoding="utf-8")
    for k, b in my["proposed_values"].items():
        print(f"  multiyear {k}: {b['n_with_value']} players")
    print(f"wrote {MULTIYR_PATH.relative_to(ROOT)}")
    print(art["verdict"]["summary"])
    return 0


def restamp(argv: list[str] | None = None) -> int:
    """Re-derive the verdict blocks from the ALREADY MEASURED numbers in the
    committed artifact and rewrite it. No arm re-runs, no bootstraps, nothing
    measured again: this exists so a correction to the pre-registered DECISION
    RULE (for example excluding arm S from G2's baseline set, where it never
    belonged) can be applied without pretending to a fresh measurement."""
    art = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    for pool, blk in art["pools"].items():
        blk["verdict"] = verdict_for(blk)
        blk["shrink_ruling"] = shrink_ruling(blk)
    art["verdict"] = _overall(art["pools"])
    art["restamped_at"] = date.today().isoformat()
    art["restamp_note"] = ("Verdict blocks re-derived from the measured numbers "
                           "already in this file. Arm S (shrink) was removed from "
                           "G2's baseline set, where the pre-registration never put "
                           "it: it is an alternate primary and belongs to G3. No "
                           "rho, gap or bootstrap was recomputed.")
    EVAL_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(art["verdict"]["summary"])
    print(art["verdict"]["shrink_decision"])
    for p, b in art["pools"].items():
        g2 = b["verdict"]["g2_ship_vs_best_baseline"]
        print(f"  {p}: best baseline {g2['best_baseline']} "
              f"{g2['rho_baseline']} vs primary {g2['rho_primary']} "
              f"(gap lo95 {(g2['gap'] or {}).get('lo95')}) -> G2 {g2['pass']}")
    return 0


if __name__ == "__main__":
    if "--restamp" in sys.argv[1:]:
        sys.exit(restamp(sys.argv[1:]))
    if "--window-only" in sys.argv[1:]:
        sys.exit(rerun_window(sys.argv[1:]))
    sys.exit(main(sys.argv[1:]))
