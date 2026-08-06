# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lane E4: test the owner's three anthropometric claims, honestly.

THE CLAIMS, stated by the owner and pre-registered here before any fitting:

  H1  A short hitter is a poor first baseman.        height  -> P(1B)
  H2  An elite arm suits third base.                 throw   -> P(3B)
  H3  A weak arm pushes a player to second base.     throw   -> P(2B)

WHY THIS IS A MEASUREMENT AND NOT A MODEL. docs/master-plan-2026-08-05-omnibus2.md E4 is
explicit that positional_fit.py is already a validated engine for MOVE SIZE with a NULL on
who-gets-demoted, that a previous arm gate NO-SHIPPED because raw arm-by-position is
confounded by throw context (1.94 mph context-adjusted spread against a 3.80 within-position
SD), and that OAA already contains arm and legs so an additive anthro bonus would double
count. It also predicts these infield effects will be SMALL, and instructs: if the prior
fails its gate, ship the measurement as the deliverable.

So this file does not fit a shipping model. It tests three stated beliefs against the data
and reports what is there, including the answer that one of them is not supported.

PRE-REGISTRATION (fixed before running; see docs/prereg-e4-anthro-position.md)
  Population   prospects with a scouted grade who later recorded MLB fielding innings.
  Exposure     H1 height in inches, from the board's own _extras.
               H2/H3 the scouted `throw` grade on the 20-80 scale.
  Outcome      share of a player's career MLB innings at the position in question.
  Estimator    Spearman rho between exposure and that share, which is scale-free and does
               not assume the relationship is linear.
  Null         permutation: shuffle the exposure against the outcome 2,000 times and read
               the two-sided p as the share of |rho_perm| >= |rho_observed|.
  Interval     2,000-resample bootstrap percentile CI on rho.
  Control      a zero-information exposure (uniform noise) run through the identical
               pipeline. It must come back null, or the harness itself is broken.
  VERDICT RULE a claim is SUPPORTED only when the permutation p < 0.05 AND the bootstrap
               95% CI excludes zero AND the sign matches the claim. Two of three is not a
               pass. A claim that fails is reported as REFUTED or NOT SUPPORTED, not
               quietly dropped, and that outcome is a valid deliverable.

WHAT WOULD MAKE US REFUSE TO SHIP A MODEL FROM THIS, also fixed in advance: any claim whose
CI includes zero, or whose effect is smaller than the within-position spread the earlier arm
verdict measured. A pre-registration that can only succeed is not one.

Usage:
    python tools/anthro_position_lab.py            # writes data/anthro_position_eval.json
    python tools/anthro_position_lab.py --quiet
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "prospects.db"
INNINGS = ROOT / "data" / "fielding_innings.json"
OUT = ROOT / "data" / "anthro_position_eval.json"

N_BOOT = 2000
N_PERM = 2000
SEED = 4137

#: The infield positions the owner's claims name.
CLAIMS = (
    {"id": "H1_short_is_a_poor_1B", "exposure": "height_in", "position": "1B",
     "expect": "+", "claim": "a short hitter is a poor first baseman, so height should "
                             "rise with first-base share"},
    {"id": "H2_elite_arm_suits_3B", "exposure": "throw", "position": "3B",
     "expect": "+", "claim": "an elite arm suits third base, so arm grade should rise "
                             "with third-base share"},
    {"id": "H3_weak_arm_pushes_2B", "exposure": "throw", "position": "2B",
     "expect": "-", "claim": "a weak arm pushes a player to second base, so arm grade "
                             "should FALL as second-base share rises"},
)


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
_HT = re.compile(r"^\s*(\d+)\s*'\s*(\d+(?:\.\d+)?)?")


def height_inches(raw) -> float | None:
    """The boards write height as "6' 2". Anything else is dropped rather than
    guessed: a mis-parsed height is a fabricated exposure."""
    if raw is None:
        return None
    m = _HT.match(str(raw))
    if not m:
        return None
    feet = int(m.group(1))
    inches = float(m.group(2) or 0)
    total = feet * 12 + inches
    # Real position players sit well inside this. Anything outside is a parse
    # artifact, not a short shortstop.
    return total if 58.0 <= total <= 84.0 else None


def anthro_by_player() -> dict:
    """{player_key: {height_in, throw}} from the most recent snapshot carrying each.

    Taken per FIELD rather than per snapshot, because height and arm are reported
    by different sources at different times and requiring one row to carry both
    would cut the sample from 6,077 players to 1,112 for no methodological gain.
    Height is a body fact and the scouted arm grade is close to one; neither is
    a within-season quantity."""
    out: dict[str, dict] = defaultdict(dict)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = ("select player_key, snapshot_date, tools_json from snapshots "
         "where tools_json is not null and tools_json != '' order by snapshot_date")
    for pk, _d, tj in con.execute(q):
        try:
            t = json.loads(tj)
        except (TypeError, ValueError):
            continue
        if not isinstance(t, dict):
            continue
        ex = t.get("_extras") if isinstance(t.get("_extras"), dict) else {}
        h = height_inches(ex.get("height"))
        if h is not None:
            out[pk]["height_in"] = h          # later rows win: ordered by date
        try:
            th = float(t.get("throw"))
        except (TypeError, ValueError):
            th = None
        if th is not None and 20.0 <= th <= 80.0:
            out[pk]["throw"] = th
    con.close()
    return dict(out)


#: The player_key -> mlbam bridge is not in one place. `players` carries no mlbam
#: column at all, and the mapping is spread across these, widest last so it wins
#: a tie. Using only one of them would silently shrink the sample and, worse,
#: shrink it NON-RANDOMLY: draft_players is draftees, fa_class_players is free
#: agents, and a claim tested on either alone is a claim about that cohort.
_BRIDGES = ("draft_players", "overseas_players", "fa_class_players",
            "tjstats_snapshots", "player_photos")


def mlbam_by_player() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    have = {r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")}
    out = {}
    for t in _BRIDGES:
        if t not in have:
            continue
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
        key = "mlbam_id" if "mlbam_id" in cols else (
            "mlbam" if "mlbam" in cols else None)
        if not key or "player_key" not in cols:
            continue
        for pk, mid in con.execute(
                f"select player_key, {key} from {t} "
                f"where {key} is not null and player_key is not null"):
            try:
                out[pk] = str(int(mid))
            except (TypeError, ValueError):
                continue
    con.close()
    if not out:
        raise SystemExit("no player_key to mlbam bridge found in any known table")
    return out


def position_players() -> set:
    """player_keys that are NOT pitchers.

    THE CONFOUND THIS REMOVES, found on the first run and worth recording because
    the zero-information control did NOT catch it. Left unfiltered, 55.4% of the
    height sample were pitchers, who average 74.64 inches against a hitter's
    72.62 and who record essentially no innings at first base. That combination
    alone manufactures a negative height-to-1B correlation, and the first run duly
    reported H1 CONTRADICTED at p = 0.0005: a real-looking effect, entirely an
    artifact of who was in the sample.

    The control could not see it. A uniform-noise exposure tests whether the
    ESTIMATOR is honest; it says nothing about whether the POPULATION is the one
    the claim is about. Those are different failures and only the second was
    present."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {pk for pk, isp in con.execute(
        "select player_key, is_pitcher from players") if not isp}
    con.close()
    return out


def innings_shares() -> dict:
    """{mlbam: {POS: share of career innings}} over every season on file.

    Career share rather than a single season on purpose: the claims are about
    where a player ENDS UP, and one season is mostly noise about where a club
    happened to need him that year."""
    doc = json.loads(INNINGS.read_text(encoding="utf-8"))
    tot: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for _season, players in (doc.get("seasons") or {}).items():
        for mid, bypos in (players or {}).items():
            for pos, rec in (bypos or {}).items():
                if pos == "DH":
                    continue          # not a fielding position
                try:
                    tot[str(mid)][pos] += float((rec or {}).get("inn") or 0.0)
                except (TypeError, ValueError):
                    continue
    out = {}
    for mid, bypos in tot.items():
        s = sum(bypos.values())
        if s <= 0:
            continue
        out[mid] = {p: v / s for p, v in bypos.items()}
    return out


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def evaluate(xs, ys, rng) -> dict:
    rho = spearman(xs, ys)
    if rho is None:
        return {"n": len(xs), "rho": None, "reason": "degenerate exposure or outcome"}
    n = len(xs)

    boots = []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        r = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if r is not None:
            boots.append(r)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else None
    hi = boots[int(0.975 * len(boots)) - 1] if boots else None

    hits = 0
    shuffled = list(ys)
    for _ in range(N_PERM):
        rng.shuffle(shuffled)
        r = spearman(xs, shuffled)
        if r is not None and abs(r) >= abs(rho):
            hits += 1
    p = (hits + 1) / (N_PERM + 1)

    return {"n": n, "rho": round(rho, 5),
            "ci95": [None if lo is None else round(lo, 5),
                     None if hi is None else round(hi, 5)],
            "perm_p": round(p, 5)}


def verdict(res: dict, expect: str) -> tuple[str, str]:
    """SUPPORTED needs all three: significance, an interval clear of zero, and
    the sign the claim predicts. Two of three is not a pass."""
    if res.get("rho") is None:
        return "INCONCLUSIVE", res.get("reason", "no estimate")
    lo, hi = res["ci95"]
    sig = res["perm_p"] < 0.05
    clears = lo is not None and hi is not None and (lo > 0 or hi < 0)
    signed = (res["rho"] > 0) if expect == "+" else (res["rho"] < 0)
    if sig and clears and signed:
        return "SUPPORTED", "significant, interval clears zero, sign as claimed"
    if sig and clears and not signed:
        return "CONTRADICTED", ("a real effect in the OPPOSITE direction to the claim")
    if not clears:
        return "NOT SUPPORTED", "the 95% interval includes zero"
    return "NOT SUPPORTED", f"permutation p = {res['perm_p']}"


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    def say(*m):
        if not a.quiet:
            print(*m)

    rng = random.Random(SEED)
    anthro = anthro_by_player()
    mlbam = mlbam_by_player()
    shares = innings_shares()
    hitters = position_players()
    # Every claim is about where a HITTER ends up on the diamond. A pitcher in
    # the sample contributes a tall body with no infield innings and biases all
    # three the same way.
    anthro = {pk: v for pk, v in anthro.items() if pk in hitters}
    say(f"anthro players {len(anthro)} (position players only), "
        f"mlbam-mapped {len(mlbam)}, players with MLB innings {len(shares)}")

    results = []
    for c in CLAIMS:
        xs, ys = [], []
        for pk, rec in anthro.items():
            v = rec.get(c["exposure"])
            mid = mlbam.get(pk)
            if v is None or not mid:
                continue
            sh = shares.get(mid)
            if not sh:
                continue
            xs.append(float(v))
            ys.append(float(sh.get(c["position"], 0.0)))
        res = evaluate(xs, ys, rng)
        v, why = verdict(res, c["expect"])
        row = {**{k: c[k] for k in ("id", "claim", "exposure", "position", "expect")},
               **res, "verdict": v, "why": why}
        results.append(row)
        say(f"  {c['id']:26s} n={res.get('n'):5} rho={res.get('rho')} "
            f"ci={res.get('ci95')} p={res.get('perm_p')} -> {v}")

    # ZERO-INFORMATION CONTROL. Uniform noise through the identical pipeline. If
    # this ever comes back SUPPORTED the harness is broken and no verdict above
    # can be trusted.
    ctrl_xs, ctrl_ys = [], []
    for pk, rec in anthro.items():
        mid = mlbam.get(pk)
        if not mid or "height_in" not in rec:
            continue
        sh = shares.get(mid)
        if not sh:
            continue
        ctrl_xs.append(rng.random())
        ctrl_ys.append(float(sh.get("1B", 0.0)))
    ctrl = evaluate(ctrl_xs, ctrl_ys, rng)
    ctrl_v, ctrl_why = verdict(ctrl, "+")
    say(f"  {'CONTROL_zero_information':26s} n={ctrl.get('n'):5} "
        f"rho={ctrl.get('rho')} p={ctrl.get('perm_p')} -> {ctrl_v}")

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lane": "E4",
        "what_this_is": ("a pre-registered test of three stated beliefs about body type "
                         "and infield position, not a shipping model"),
        "preregistration": "docs/prereg-e4-anthro-position.md",
        "n_boot": N_BOOT, "n_perm": N_PERM, "seed": SEED,
        "verdict_rule": ("SUPPORTED requires permutation p < 0.05 AND a 95% bootstrap CI "
                         "clear of zero AND the sign the claim predicts"),
        "claims": results,
        "zero_information_control": {**ctrl, "verdict": ctrl_v, "why": ctrl_why},
        "control_ok": ctrl_v != "SUPPORTED",
        "population": "position players only; pitchers are excluded",
        "caveats": [
            "FIRST-RUN ERROR, recorded rather than hidden: with pitchers left in, "
            "55.4% of the height sample were pitchers, 2.0 inches taller on average "
            "and with no first-base innings, which produced a spurious H1 at "
            "p = 0.0005 in the WRONG direction. The zero-information control passed "
            "on that run: it validates the estimator, not the population.",
            "Career innings share is an OUTCOME of club decisions, not a measure of "
            "ability. A club that believes the same folk wisdom will produce exactly "
            "this correlation whether or not the wisdom is true, so a SUPPORTED verdict "
            "here means 'clubs behave as if this is true', not 'this is true'.",
            "Scouted arm grades are known to be confounded by throw context: the earlier "
            "arm gate measured a 1.94 mph context-adjusted spread against a 3.80 "
            "within-position SD, which is why raw arm-by-position was refused before.",
            "OAA already contains arm and legs, so nothing here may be added to the "
            "positional fit as a bonus without double counting.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    say(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
