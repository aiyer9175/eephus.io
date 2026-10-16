# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR's pitching bases beyond S2: the pure core of EBR_GATE.md part 11.3.

Registered in docs/ebr-2026-09-30/EBR_GATE.md part 11.3 (owner decision EW3-20),
which this module implements and does not extend. Nothing here is served: the
preview builder (tools/build_swar.py) writes under .cache/swar/ only and no
exporter imports this module.

S2b, the BLENDED BASIS (the second arm of candidate part 5, 11.3.1). S2's FIP
components on the home-run term the HR-arm clause chose, plus three runs terms
the FIP arm treats as league average, each shrunk toward a zero prior by its own
constant (11.3.2):
  CQ   contact quality beyond the home-run term: the Savant expected-minus-actual
       wOBA gap on contact, added to the actual contact runs above average, less
       the home-run runs the arm already carries;
  B    the BABIP residual: actual minus expected on contact, with the club's
       fielding runs (Fld) put back once, so no fielding run is counted twice;
  L    the strand (LOB%) residual: the runner-adjusted runs RA* minus the runs
       the season's events imply.
G = CQ~ + B~ + L~ (runs) enters the FIP chain as dFIP_b = dFIP(S2) + 9 G / IP.

R2, the REALIZED BASIS (eWAR realized's pitching part, 11.3.3). RA9* of part
11.2.1: runs charged, adjusted for bequeathed and inherited runners, divided by
the chain's park factor, with the club's fielding runs (Fld + Frm) put back, per
9 innings. It replaces pFIPR9 in the same chain; the difference is re-pinned.

THE RUNNER TERMS (11.3.3), read so a season's runs stay exact: a runner's owner
is the pitcher of record when he reached (a pinch runner takes the replaced
runner's owner, a placed extra-inning runner the half-inning's first pitcher).
At each pitching change every runner on base is bequeathed by the leaving
pitcher (BQ, E_BQ at his exit) and inherited by the entering one (IR, E_IR at
his entry). IRS counts inherited runners who scored while the inheritor
pitched; BQS counts owned runners who scored after their owner left. So the sum
of RA* = R - BQS + E_BQ + (IRS - E_IR) over a season equals the sum of R.

PURE: no network, no I/O, no module-level data. It relates nothing to any
next-season quantity; the shrink constants were fitted by tools/pitch_basis_fit.py
under 11.3.2's rule and are frozen below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

PB_VERSION = "pitch_basis/1"

#: The blended arm's preview keys, one per home-run variant of S2 (swar.HR_VARIANTS).
BLEND_PREFIX = "pb_"
REALIZED_KEY = "realized"

#: The three shrink constants of part 11.3.2 (K_CQ and K_BAB in batted balls,
#: K_LOB in runners allowed). FIXED by EWAR_PITCH_BASIS on 2026-10-15 with
#: tools/pitch_basis_fit.py, B1's rule (swar_lab.fit_b1, the DEM+ K_INN
#: precedent) on the 2016 to 2018 predictor pairs of pitchers with 50 or more IP
#: in both seasons, from the three term rates and their exposures only (no S2,
#: no delta, no test value, no target). The fit output is K_FIT_LOG.
#:   cq   pairs 670  players 356  r 0.2090  hm 314.8 batted balls     k 1191
#:   bab  pairs 670  players 356  r 0.0496 (clamped 0.05)  hm 314.8   k 5981
#:   lob  pairs 670  players 356  r 0.0640  hm 129.4 runners allowed  k 1893
#: (vintage 2026-10-02-57bf90f7143e; CQ read on the actual home-run count.)
K_CQ: Optional[float] = 1191.0
K_BAB: Optional[float] = 5981.0
K_LOB: Optional[float] = 1893.0
K_FIT_LOG: Optional[dict] = {
    "fixed_on": "2026-10-15",
    "task": "EWAR_PITCH_BASIS",
    "producer": "python tools/pitch_basis_fit.py",
    "registration": "docs/ebr-2026-09-30/EBR_GATE.md part 11.3.2",
    "rule": ("B1's rule (swar_lab.fit_b1): pooled Pearson r of the term per exposure in Y "
             "and Y+1 on the 2016 to 2018 predictor pairs of pitchers with 50 or more IP "
             "in both seasons, r clamped 0.05 to 0.95, k = hm (1 - r) / r, hm the mean "
             "harmonic exposure, rounded to a whole unit"),
    "reads": "the three raw terms and their exposures only (CQ on the actual home-run count)",
    "fit_seasons": [2016, 2017, 2018],
    "fwar_vintage_id": "2026-10-02-57bf90f7143e",
    "cq": {"exposure": "batted balls", "n_pairs": 670, "n_players": 356, "r": 0.2090,
           "hm": 314.8, "k": 1191.0},
    "bab": {"exposure": "batted balls", "n_pairs": 670, "n_players": 356, "r_raw": 0.0496,
            "r": 0.05, "hm": 314.8, "k": 5981.0},
    "lob": {"exposure": "runners allowed", "n_pairs": 670, "n_players": 356, "r": 0.0640,
            "hm": 129.4, "k": 1893.0},
}

#: The bases a runner may occupy and the outs a play may start with.
BASES = (1, 2, 3)
OUTS = (0, 1, 2)


# --------------------------------------------------------------------------
# the season line
# --------------------------------------------------------------------------

@dataclass
class PitchLine:
    """One pitcher-season's StatsAPI line, the fields 11.3 reads."""
    mlbam: int
    ip: float = 0.0
    tbf: float = 0.0
    ab: float = 0.0
    h: float = 0.0
    doub: float = 0.0
    trip: float = 0.0
    hr: float = 0.0
    bb: float = 0.0
    ibb: float = 0.0
    hbp: float = 0.0
    sf: float = 0.0
    so: float = 0.0
    r: float = 0.0


def contact_count(ln: PitchLine) -> float:
    """C = AB - SO + SF: batted balls, home runs included; never below 0."""
    return max(0.0, float(ln.ab) - float(ln.so) + float(ln.sf))


def singles(ln: PitchLine) -> float:
    return max(0.0, float(ln.h) - float(ln.doub) - float(ln.trip) - float(ln.hr))


def contact_value(ln: PitchLine, w: Mapping[str, float]) -> float:
    """V = W_1B 1B + W_2B 2B + W_3B 3B + W_HR HR on the season's solved weights."""
    return (float(w["1b"]) * singles(ln) + float(w["2b"]) * float(ln.doub)
            + float(w["3b"]) * float(ln.trip) + float(w["hr"]) * float(ln.hr))


def woba_denominator(ln: PitchLine) -> float:
    """D = AB + BB - IBB + SF + HBP."""
    return float(ln.ab) + float(ln.bb) - float(ln.ibb) + float(ln.sf) + float(ln.hbp)


def woba_against(ln: PitchLine, w: Mapping[str, float]) -> Optional[float]:
    """The actual wOBA against on the season's weights; None with no denominator."""
    d = woba_denominator(ln)
    if d <= 0:
        return None
    ubb = max(0.0, float(ln.bb) - float(ln.ibb))
    return (float(w["ubb"]) * ubb + float(w["hbp"]) * float(ln.hbp) + contact_value(ln, w)) / d


def runners_allowed(ln: PitchLine) -> float:
    """N = H + BB + HBP - HR."""
    return max(0.0, float(ln.h) + float(ln.bb) + float(ln.hbp) - float(ln.hr))


@dataclass
class League:
    """The season's league quantities over the pitchers inside the rule."""
    lc: float          # league contact value per batted ball, sum V / sum C
    h: float           # league home runs per batted ball, sum HR / sum C
    r_per_d: float     # league runs per wOBA denominator, sum R / sum D
    lg_woba: float     # league wOBA against, sum numerators / sum D


def league(lines: Iterable[PitchLine], w: Mapping[str, float]) -> League:
    sv = sc = shr = sr = sd = snum = 0.0
    for ln in lines:
        c = contact_count(ln)
        d = woba_denominator(ln)
        sv += contact_value(ln, w)
        sc += c
        shr += float(ln.hr)
        sr += float(ln.r)
        sd += d
        wa = woba_against(ln, w)
        if wa is not None:
            snum += wa * d
    if sc <= 0 or sd <= 0:
        raise ValueError("a season with no batted balls or no wOBA denominator")
    return League(lc=sv / sc, h=shr / sc, r_per_d=sr / sd, lg_woba=snum / sd)


# --------------------------------------------------------------------------
# S2b's three terms (11.3.1)
# --------------------------------------------------------------------------

def savant_gap_runs(est_woba: Optional[float], woba: Optional[float], d: float,
                    scale: float) -> float:
    """X = (est_woba - woba) x D / scale: expected minus actual, in runs, on
    contact; 0 for a pitcher the Savant cache lacks."""
    if est_woba is None or woba is None or d <= 0:
        return 0.0
    return (float(est_woba) - float(woba)) * float(d) / float(scale)


def actual_contact_runs(ln: PitchLine, w: Mapping[str, float], lg: League, scale: float) -> float:
    """A = (V - C lc) / scale."""
    return (contact_value(ln, w) - contact_count(ln) * lg.lc) / float(scale)


def hr_term_runs(hr_count: float, ln: PitchLine, w: Mapping[str, float], lg: League,
                 scale: float) -> float:
    """H* = W_HR (m*_HR - C h) / scale: the home-run runs the arm carries."""
    return float(w["hr"]) * (float(hr_count) - contact_count(ln) * lg.h) / float(scale)


def events_runs(ln: PitchLine, w: Mapping[str, float], lg: League, scale: float) -> float:
    """E = D (R / D)_league + (wOBA - lgwOBA) D / scale: the runs the events imply."""
    d = woba_denominator(ln)
    wa = woba_against(ln, w)
    if wa is None:
        return 0.0
    return d * lg.r_per_d + (wa - lg.lg_woba) * d / float(scale)


def ra_star(r: float, bqs: float = 0.0, e_bq: float = 0.0, irs: float = 0.0,
            e_ir: float = 0.0) -> float:
    """RA* = R - BQS + E_BQ + (IRS - E_IR) (11.2.1)."""
    return float(r) - float(bqs) + float(e_bq) + (float(irs) - float(e_ir))


def terms(ln: PitchLine, w: Mapping[str, float], lg: League, scale: float,
          hr_count: float, x_runs: float, fld_share: float, ra_star_value: float) -> dict:
    """The three raw terms of S2b and their exposures, in runs:
    CQ = Xc - H*, B = -X + fielding put back, L = RA* - E."""
    a = actual_contact_runs(ln, w, lg, scale)
    xc = a + float(x_runs)
    hstar = hr_term_runs(hr_count, ln, w, lg, scale)
    return {"cq": xc - hstar, "bab": -float(x_runs) + float(fld_share),
            "lob": float(ra_star_value) - events_runs(ln, w, lg, scale),
            "c": contact_count(ln), "n": runners_allowed(ln),
            "a": a, "xc": xc, "hstar": hstar}


def shrink(x: float, n: float, k: Optional[float]) -> float:
    """x~ = x n / (n + K): toward a zero prior. K None (infinite) gives 0; n at
    or below 0 gives 0."""
    if k is None or n is None or n <= 0:
        return 0.0
    return float(x) * float(n) / (float(n) + float(k))


def blend_runs(t: Mapping[str, float], k_cq: Optional[float] = None,
               k_bab: Optional[float] = None, k_lob: Optional[float] = None) -> float:
    """G = CQ~ + B~ + L~ in runs (CQ and B on batted balls, L on runners allowed)."""
    return (shrink(t["cq"], t["c"], k_cq) + shrink(t["bab"], t["c"], k_bab)
            + shrink(t["lob"], t["n"], k_lob))


def dfip_blend(dfip_s2: float, g_runs: float, ip: float) -> float:
    """dFIP_b = dFIP(S2) + 9 G / IP; 0 with no innings."""
    if not ip or ip <= 0:
        return 0.0
    return float(dfip_s2) + 9.0 * float(g_runs) / float(ip)


def constants() -> tuple[Optional[float], Optional[float], Optional[float]]:
    """(K_CQ, K_BAB, K_LOB) as frozen; any None means 11.3.2's fit has not landed."""
    return K_CQ, K_BAB, K_LOB


# --------------------------------------------------------------------------
# R2 (11.3.3)
# --------------------------------------------------------------------------

def ra9_star(ra_star_value: float, pf: float, bf: float, fld_frm_share: float,
             ip: float) -> Optional[float]:
    """RA9* = 9 (RA* / PF + share of the club's Fld + Frm) / IP; None with no innings."""
    if not ip or ip <= 0 or not pf:
        return None
    return 9.0 * (float(ra_star_value) / float(pf) + float(fld_frm_share)) / float(ip)


def repin(d: Mapping[int, float], ip: Mapping[int, float], out_rule: Iterable[int] = ()) -> dict:
    """Delta_j = d_j - IP_j (sum d) / (sum IP) over the rows inside the rule; a row
    outside (nopp) carries 0. The deltas inside the rule sum to zero."""
    out_rule = set(int(i) for i in out_rule)
    inside = [i for i in d if int(i) not in out_rule]
    tot_ip = sum(float(ip.get(i) or 0.0) for i in inside)
    c = (sum(float(d[i]) for i in inside) / tot_ip) if tot_ip > 0 else 0.0
    return {i: (0.0 if int(i) in out_rule else float(v) - float(ip.get(i) or 0.0) * c)
            for i, v in d.items()}


# --------------------------------------------------------------------------
# the club's fielding runs, shared by batters faced
# --------------------------------------------------------------------------

def club_runs(runs: Mapping[int, float], inn_by_team: Mapping[int, Mapping[str, float]]) -> dict:
    """{team: runs}: each fielder's season runs split over his clubs by his
    fielding innings there (pitching innings excluded by the caller)."""
    out: dict = {}
    for mid, v in runs.items():
        teams = inn_by_team.get(int(mid)) or {}
        tot = sum(float(x) for x in teams.values() if x and x > 0)
        if tot <= 0 or not v:
            continue
        for t, x in teams.items():
            if x and x > 0:
                out[t] = out.get(t, 0.0) + float(v) * float(x) / tot
    return out


def pitcher_shares(bf: Mapping[int, float], ip_by_team: Mapping[int, Mapping[str, float]]) -> dict:
    """{mlbam: {team: batters faced there}}, the season's batters faced split by
    the pitcher's innings at each club; {} for a pitcher with no club innings."""
    out = {}
    for mid, b in bf.items():
        teams = ip_by_team.get(int(mid)) or {}
        tot = sum(float(x) for x in teams.values() if x and x > 0)
        if tot <= 0:
            out[mid] = {}
            continue
        out[mid] = {t: float(b or 0.0) * float(x) / tot for t, x in teams.items() if x and x > 0}
    return out


def defense_share(bf_by_team: Mapping[str, float], club: Mapping[str, float],
                  club_bf: Mapping[str, float]) -> float:
    """sum over the pitcher's clubs t of BF_jt x F_t / BF_t."""
    tot = 0.0
    for t, b in (bf_by_team or {}).items():
        cb = float(club_bf.get(t) or 0.0)
        if cb > 0:
            tot += float(b) * float(club.get(t) or 0.0) / cb
    return tot


# --------------------------------------------------------------------------
# the runner terms (11.3.3)
# --------------------------------------------------------------------------

def p_table(starts: Iterable[tuple[int, int, bool]]) -> dict:
    """p_s(base, outs): the share of runners on that base with that many outs who
    scored before the half-inning ended, from (base, outs, scored) observations on
    the fit set. A cell with no observation is absent."""
    num: dict = {}
    den: dict = {}
    for b, o, s in starts:
        key = (int(b), int(o))
        den[key] = den.get(key, 0) + 1
        num[key] = num.get(key, 0) + (1 if s else 0)
    return {k: num[k] / den[k] for k in den}


@dataclass
class Play:
    """One plate appearance of a half-inning, in order."""
    ab: int
    pitcher: int
    outs: int
    bases: tuple            # (runner on 1B, on 2B, on 3B), None when empty
    batter: int
    reached: bool           # the batter-runner ended the play on base or scored
    scorers: tuple = ()     # runner ids who scored during this plate appearance


def _blank() -> dict:
    return {"ir": 0.0, "irs": 0.0, "bq": 0.0, "bqs": 0.0, "e_ir": 0.0, "e_bq": 0.0}


def half_runner_terms(plays: list[Play], p: Mapping[tuple, float], acc: dict,
                      subs: Optional[Mapping[int, int]] = None) -> dict:
    """Walk one half-inning and add each pitcher's runner terms into `acc`
    ({pitcher: {ir, irs, bq, bqs, e_ir, e_bq}}). `subs` maps a substitute runner
    to the runner he replaced. Returns counters for the census."""
    subs = subs or {}
    owner: dict = {}        # runner -> the pitcher charged with him
    holder: dict = {}       # inherited runner -> the pitcher who last inherited him
    left: dict = {}         # owned runner left on base -> his owner
    seen_missing = 0
    if not plays:
        return {"missing_owner": 0}
    first = plays[0].pitcher
    cur = None
    for pl in plays:
        on = [(b, r) for b, r in zip(BASES, pl.bases) if r is not None]
        for _b, rid in on:
            if rid in owner:
                continue
            rep = subs.get(rid)
            if rep is not None and rep in owner:
                owner[rid] = owner[rep]
                if rep in holder:
                    holder[rid] = holder[rep]
                if rep in left:
                    left[rid] = left[rep]
            else:
                owner[rid] = first
                seen_missing += 1
        if cur is not None and pl.pitcher != cur:
            for b, rid in on:
                e = float(p.get((b, pl.outs), 0.0))
                acc.setdefault(cur, _blank())
                acc.setdefault(pl.pitcher, _blank())
                acc[cur]["bq"] += 1.0
                acc[cur]["e_bq"] += e
                acc[pl.pitcher]["ir"] += 1.0
                acc[pl.pitcher]["e_ir"] += e
                if owner.get(rid) == cur:
                    left[rid] = cur
                holder[rid] = pl.pitcher
        cur = pl.pitcher
        for rid in pl.scorers:
            if rid in left and left[rid] != cur:
                acc.setdefault(left[rid], _blank())["bqs"] += 1.0
            if holder.get(rid) == cur:
                acc.setdefault(cur, _blank())["irs"] += 1.0
            left.pop(rid, None)
            holder.pop(rid, None)
            owner.pop(rid, None)
        if pl.reached and pl.batter not in pl.scorers:
            owner[pl.batter] = cur
            left.pop(pl.batter, None)
            holder.pop(pl.batter, None)
    return {"missing_owner": seen_missing}


def accounting_gap(acc: Mapping[int, Mapping[str, float]]) -> dict:
    """The two sums that must net to zero over a season: E_BQ - E_IR and IRS - BQS."""
    e = sum(v["e_bq"] - v["e_ir"] for v in acc.values())
    s = sum(v["irs"] - v["bqs"] for v in acc.values())
    return {"e_bq_minus_e_ir": e, "irs_minus_bqs": s}
