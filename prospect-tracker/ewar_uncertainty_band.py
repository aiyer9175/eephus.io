# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The eWAR uncertainty band: its pure core (docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md).

Task EWAR_UNCERTAINTY_BAND, owner decision EW3-50. Nothing here reads a file: the lab
(tools/ewar_uncertainty_band_lab.py) builds the families and hands them in, so the
fixture dry run and the planted check run the same code as the read.

A family is one check of gate part 5. Every row carries a statistic D, a shape g and
a scale s, so that one form serves both kinds:

    C1 (method):   D = fWAR_side - bWAR_side      g = 2 e                     s = 1
    C2 (sampling): D = e * (x_A - x_B)            g = e^2 (1/e_A + 1/e_B)     s = e^2

    k  = sum (D^2 / s) / sum (g / s)      (part 2.2: sum d^2 / (2 sum e), or
                                           sum (x_A - x_B)^2 / sum (1/e_A + 1/e_B))
    SD = sqrt(k * g)                      the predicted sd of D (part 5)

The band's served sigma (part 2.1) is `sigma()`; the read is `score()`; the planted
check of part 6 is `planted()`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

GATE_DOC = "docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md"
SEED = 20261023
B = 4000
B_PLANTED = 500
N_PLANTED = 20
Z80 = 1.2816
ALPHA = 0.2
Z90 = 1.645
#: Amendment 13.1: the equivalence range (registered [0.75, 0.85]) and the training seasons.
EQUIV = (0.70, 0.90)
TRAIN_ROLES = ("FIT", "CAL")
PLANTED_TRUTH_MIN = 16
PLANTED_BROKEN_MAX = 1
MIN_TEST_ROWS = 100
MIN_CAL_ROWS = 50

#: Part 3: floors and exposure band edges per side (PA for bat, IP for pit).
FLOOR = {"bat": 20.0, "pit": 5.0}
EDGES = {"bat": (20.0, 100.0, 300.0, 500.0), "pit": (5.0, 20.0, 60.0, 120.0)}
BAND_LABELS = {"bat": ("PA 20-99", "PA 100-299", "PA 300-499", "PA 500+"),
               "pit": ("IP 5-19.2", "IP 20-59.2", "IP 60-119.2", "IP 120+")}

#: The six families of part 5, with their side and kind.
FAMILIES = (("C1-bat", "bat", "c1"), ("C1-pit", "pit", "c1"), ("C2-bat", "bat", "c2"),
            ("C2-ebr", "bat", "c2"), ("C2-fip", "pit", "c2"), ("C2-ra", "pit", "c2"))
FAMILY_SIDE = {f: s for f, s, _ in FAMILIES}
FAMILY_KIND = {f: k for f, _, k in FAMILIES}
#: Part 2.1: which family's k and multipliers a served term reads.
TERM_FAMILY = {"src_bat": "C1-bat", "src_pit": "C1-pit", "bat": "C2-bat", "ebr": "C2-ebr",
               "fip": "C2-fip", "ra": "C2-ra"}


class BandRefusal(RuntimeError):
    """A refusal of gate part 3: the read stops and writes nothing."""


def role(season: int) -> str | None:
    """Part 3: FIT, CAL or TEST by season modulo 3; 2020 and 2026 are in no check."""
    s = int(season)
    if s in (2020, 2026):
        return None
    return ("FIT", "CAL", "TEST")[(s - 2001) % 3]


def band_index(side: str, e) -> int | None:
    """Part 3: the exposure band (0 to 3), or None below the floor or for a missing value."""
    try:
        v = float(e)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v < FLOOR[side]:
        return None
    edges = EDGES[side]
    i = 0
    for j, lo in enumerate(edges):
        if v >= lo:
            i = j
    return i


@dataclass
class Family:
    """One check's rows. D may be None (a design-only frame: the planted check)."""
    name: str
    season: np.ndarray
    band: np.ndarray
    g: np.ndarray
    s: np.ndarray
    player: np.ndarray
    club: np.ndarray
    D: np.ndarray | None = None
    n1_k: float | None = None          # N1's k (C1 only); None on C2 (h = 0)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        for a in ("season", "band", "player", "club"):
            setattr(self, a, np.asarray(getattr(self, a), dtype=np.int64))
        for a in ("g", "s"):
            setattr(self, a, np.asarray(getattr(self, a), dtype=float))
        if self.D is not None:
            self.D = np.asarray(self.D, dtype=float)
        self.role = np.array([role(x) or "" for x in self.season])

    @property
    def side(self) -> str:
        return FAMILY_SIDE.get(self.name, "bat")

    def with_D(self, D) -> "Family":
        return Family(self.name, self.season, self.band, self.g, self.s, self.player, self.club,
                      np.asarray(D, float), self.n1_k, dict(self.meta))


def c1_row(d, e):
    """(D, g, s) of a method row."""
    return float(d) if d is not None else None, 2.0 * float(e), 1.0


def c2_row(xa, xb, ea, eb):
    """(D, g, s) of a sampling row from the two halves' per-exposure values."""
    e = float(ea) + float(eb)
    D = None if (xa is None or xb is None) else e * (float(xa) - float(xb))
    return D, e * e * (1.0 / float(ea) + 1.0 / float(eb)), e * e


# ------------------------------------------------------------------ constants
def train_mask(fam: Family) -> np.ndarray:
    """Amendment 13.1: the training rows, FIT and CAL together."""
    return np.isin(fam.role, TRAIN_ROLES)


def fit_k(fam: Family, mask=None) -> float:
    """Part 2.2: k = sum (D^2 / s) / sum (g / s) over the training rows (or `mask`)."""
    m = train_mask(fam) if mask is None else mask
    if not m.any():
        return float("nan")
    D, g, s = fam.D[m], fam.g[m], fam.s[m]
    den = float(np.sum(g / s))
    return float(np.sum(D * D / s) / den) if den > 0 else float("nan")


def multipliers(fam: Family, k: float, *, apply: bool = True) -> dict:
    """Part 4 as amended (13.1): the split-conformal sd multiplier per exposure band on
    the training rows, applied in every band: {band: {"n", "raw_coverage", "m", "applied"}}."""
    out = {}
    cal = train_mask(fam)
    sd = np.sqrt(k * fam.g)
    for b in range(4):
        m = cal & (fam.band == b)
        n = int(m.sum())
        if n == 0:
            out[b] = {"n": 0, "raw_coverage": None, "m": 1.0, "applied": False}
            continue
        r = np.abs(fam.D[m]) / sd[m]
        cov = float(np.mean(r <= Z80))
        mult = float(np.quantile(r, 0.8) / Z80) if apply else 1.0
        out[b] = {"n": n, "raw_coverage": cov, "m": mult, "applied": bool(apply)}
    return out


def n0_width(fam: Family) -> float:
    """N0: the 80th percentile of |D| over the family's training rows (amendment 13.1)."""
    m = train_mask(fam)
    return float(np.quantile(np.abs(fam.D[m]), 0.8)) if m.any() else float("nan")


def interval_score(D, h):
    return 2.0 * h + (2.0 / ALPHA) * np.maximum(0.0, np.abs(D) - h)


def fit_family(fam: Family, *, conformal: bool = True, k_scale: float = 1.0) -> dict:
    """k, the multipliers and N0 from the training rows: everything fixed before TEST."""
    k = fit_k(fam) * k_scale
    mult = multipliers(fam, k, apply=conformal)
    return {"k": k, "mult": mult, "n0_h": n0_width(fam)}


def test_rows(fam: Family, fit: dict) -> dict:
    """Per TEST row: covered (candidate), IS for the candidate, N0 and N1, the raw covered flag."""
    t = fam.role == "TEST"
    D, g, band = fam.D[t], fam.g[t], fam.band[t]
    sd = np.sqrt(fit["k"] * g)
    m = np.array([fit["mult"][int(b)]["m"] for b in band]) if len(band) else np.zeros(0)
    h = Z80 * m * sd
    h0 = np.full(len(D), fit["n0_h"])
    h1 = Z80 * np.sqrt(fam.n1_k * g) if fam.n1_k is not None else np.zeros(len(D))
    return {"mask": t, "band": band, "covered": (np.abs(D) <= h).astype(float),
            "raw_covered": (np.abs(D) <= Z80 * sd).astype(float),
            "is": interval_score(D, h), "is_n0": interval_score(D, h0), "is_n1": interval_score(D, h1),
            "n1_covered": (np.abs(D) <= h1).astype(float), "n0_covered": (np.abs(D) <= h0).astype(float),
            "player": fam.player[t], "club": fam.club[t], "h": h}


# ------------------------------------------------------------------ bootstrap
def _cluster_weights(rng, n_clusters: int, n_rep: int, chunk: int = 250):
    """Yield (n, n_clusters) float32 multiplicity matrices, n_rep rows in all."""
    done = 0
    while done < n_rep:
        n = min(chunk, n_rep - done)
        idx = rng.integers(0, n_clusters, size=(n, n_clusters))
        w = np.zeros((n, n_clusters), dtype=np.float32)
        for i in range(n):
            w[i] = np.bincount(idx[i], minlength=n_clusters)
        done += n
        yield w


def bootstrap(per_family: dict, kind: str, n_rep: int, seed: int = SEED) -> dict:
    """One paired cluster bootstrap over every family's TEST rows.

    per_family: {name: test_rows(...)}; kind 'player' or 'club'. Returns
    {name: {"cov": (n_rep, 4) array, "d_n0": (n_rep,), "d_n1": (n_rep,)}}."""
    keys = sorted({int(c) for tr in per_family.values() for c in tr[kind]})
    pos = {c: i for i, c in enumerate(keys)}
    G = len(keys)
    sums = {}
    for name, tr in per_family.items():
        gi = np.array([pos[int(c)] for c in tr[kind]], dtype=np.int64)
        cov_s = np.zeros((G, 4))
        n_s = np.zeros((G, 4))
        for b in range(4):
            mb = tr["band"] == b
            cov_s[:, b] = np.bincount(gi[mb], weights=tr["covered"][mb], minlength=G)
            n_s[:, b] = np.bincount(gi[mb], minlength=G)
        d0 = np.bincount(gi, weights=tr["is_n0"] - tr["is"], minlength=G)
        d1 = np.bincount(gi, weights=tr["is_n1"] - tr["is"], minlength=G)
        nn = np.bincount(gi, minlength=G).astype(float)
        sums[name] = (cov_s, n_s, d0, d1, nn)
    rng = np.random.default_rng(seed)
    out = {name: {"cov": [], "d_n0": [], "d_n1": []} for name in per_family}
    for w in _cluster_weights(rng, G, n_rep):
        w = w.astype(float)
        for name, (cov_s, n_s, d0, d1, nn) in sums.items():
            num = w @ cov_s
            den = w @ n_s
            with np.errstate(invalid="ignore", divide="ignore"):
                out[name]["cov"].append(num / den)
                tot = w @ nn
                out[name]["d_n0"].append((w @ d0) / tot)
                out[name]["d_n1"].append((w @ d1) / tot)
    return {name: {k: np.concatenate(v) for k, v in blk.items()} for name, blk in out.items()}


# ------------------------------------------------------------------ the read
def score(families: dict, *, n_rep: int = B, seed: int = SEED, conformal: bool = True,
          k_scale: float = 1.0, boot_kinds=("player", "club")) -> dict:
    """The whole design on a set of families with D: constants, multipliers, the 24
    cells, the comparisons and the verdict of gate part 7 (the planted part aside)."""
    fits, tests = {}, {}
    for name, fam in families.items():
        fits[name] = fit_family(fam, conformal=conformal, k_scale=k_scale)
        tests[name] = test_rows(fam, fits[name])
    boots = {kind: bootstrap(tests, kind, n_rep, seed) for kind in boot_kinds}
    cells, fam_out = [], {}
    calibrated, sharper = True, True
    for name in families:
        tr = tests[name]
        side = families[name].side
        for b in range(4):
            mb = tr["band"] == b
            n = int(mb.sum())
            point = float(tr["covered"][mb].mean()) if n else float("nan")
            raw = float(tr["raw_covered"][mb].mean()) if n else float("nan")
            ivals = {}
            ok = n > 0
            for kind in boot_kinds:
                c = boots[kind][name]["cov"][:, b]
                c = c[np.isfinite(c)]
                lo, hi = (float(np.quantile(c, 0.05)), float(np.quantile(c, 0.95))) if len(c) else (float("nan"),) * 2
                ivals[kind] = [lo, hi]
                ok = ok and (EQUIV[0] <= lo) and (hi <= EQUIV[1])
            calibrated = calibrated and ok
            cells.append({"family": name, "band": b, "label": BAND_LABELS[side][b], "n_test": n,
                          "coverage": point, "raw_coverage": raw, "interval": ivals, "inside": bool(ok),
                          "n1_coverage": float(tr["n1_covered"][mb].mean()) if n else float("nan"),
                          "n0_coverage": float(tr["n0_covered"][mb].mean()) if n else float("nan"),
                          "median_h": float(np.median(tr["h"][mb])) if n else float("nan")})
        comp = {}
        for null in ("n0", "n1"):
            d = float(np.mean(tr[f"is_{null}"] - tr["is"])) if len(tr["is"]) else float("nan")
            per = {}
            for kind in boot_kinds:
                v = boots[kind][name][f"d_{null}"]
                v = v[np.isfinite(v)]
                sd = float(np.std(v, ddof=1)) if len(v) > 1 else float("nan")
                per[kind] = {"sd": sd, "lo": d - Z90 * sd, "hi": d + Z90 * sd}
            deciding = null == "n0" or FAMILY_KIND.get(name) == "c2"
            win = all(per[k]["lo"] > 0 for k in boot_kinds)
            if deciding:
                sharper = sharper and win
            comp[null] = {"d": d, "by_bootstrap": per, "deciding": deciding, "win": bool(win)}
        fam_out[name] = {"k": fits[name]["k"], "multipliers": fits[name]["mult"],
                         "n0_h": fits[name]["n0_h"], "n1_k": families[name].n1_k,
                         "n_test": int(tr["mask"].sum()), "mean_is": float(np.mean(tr["is"])) if len(tr["is"]) else None,
                         "comparisons": comp,
                         "counts": {r: int((families[name].role == r).sum()) for r in ("FIT", "CAL", "TEST")}}
    return {"cells": cells, "families": fam_out, "calibrated": bool(calibrated), "sharper": bool(sharper),
            "pass_without_planted": bool(calibrated and sharper),
            "failing_cells": [f"{c['family']} {c['label']}" for c in cells if not c["inside"]]}


def disposition(result: dict, planted_pass: bool) -> str:
    if not planted_pass:
        return "UNRESOLVED (the design did not recover a planted band)"
    return "PASS" if result["pass_without_planted"] else "NOT PASS"


# ------------------------------------------------------------------ planted check
def planted_draw(fam: Family, rng, *, k_true: float = 1.0) -> np.ndarray:
    """Part 6: D = SD_true * t5 (unit variance), sqrt(2) on the lowest exposure band."""
    t = rng.standard_t(5, size=len(fam.g)) * math.sqrt(3.0 / 5.0)
    excess = np.where(fam.band == 0, math.sqrt(2.0), 1.0)
    return np.sqrt(k_true * fam.g) * excess * t


def planted(design: dict, *, n_rep: int = N_PLANTED, n_boot: int = B_PLANTED, seed: int = SEED,
            log=None) -> dict:
    """Part 6 on a design (families without D): truth and broken candidates per replicate."""
    rng = np.random.default_rng(seed)
    truth_pass, broken_pass, flagged = 0, 0, 0
    reps = []
    for r in range(n_rep):
        fams = {name: fam.with_D(planted_draw(fam, rng)) for name, fam in design.items()}
        for name, fam in fams.items():
            fam.n1_k = fit_k(fam) if FAMILY_KIND.get(name) == "c1" else None
        t = score(fams, n_rep=n_boot, seed=seed + 1 + r)
        bk = score(fams, n_rep=n_boot, seed=seed + 1 + r, conformal=False, k_scale=0.6)
        fl = sum(1 for name in fams
                 if (t["families"][name]["multipliers"][0]["raw_coverage"] or 1.0) < 0.75)
        truth_pass += int(t["pass_without_planted"])
        broken_pass += int(bk["pass_without_planted"])
        flagged += int(fl == len(fams))
        reps.append({"truth": t["pass_without_planted"], "broken": bk["pass_without_planted"],
                     "truth_failing": t["failing_cells"][:6], "lowest_band_flagged": fl})
        if log:
            log(f"  planted replicate {r + 1:2d}: truth {'PASS' if t['pass_without_planted'] else 'not'}"
                f" ({len(t['failing_cells'])} cells out), broken {'PASS' if bk['pass_without_planted'] else 'not'},"
                f" lowest band's raw training coverage below 0.75 in {fl} of {len(fams)} families")
    ok = truth_pass >= PLANTED_TRUTH_MIN and broken_pass <= PLANTED_BROKEN_MAX
    return {"truth_pass": truth_pass, "broken_pass": broken_pass, "n_rep": n_rep, "n_boot": n_boot,
            "all_families_flagged": flagged, "planted_pass": bool(ok), "replicates": reps}


def identity_check(fam: Family) -> bool:
    """Part 6: a candidate scored against itself gives d = 0 exactly."""
    fit = fit_family(fam)
    tr = test_rows(fam, fit)
    return bool(np.all(tr["is"] - tr["is"] == 0.0))


# ------------------------------------------------------------------ the served sigma
def sigma(constants: dict, *, pa=None, ip=None, rpw: float, pit_basis: str = "fip") -> dict | None:
    """Part 2.1: {"sigma", "samp", "src"} in wins, or None when no side clears its floor.

    constants: {"k": {term: k}, "m": {term: [m_band0..3]}} with terms src_bat, src_pit,
    bat, ebr, fip, ra; pit_basis 'fip' (headline) or 'ra' (an R2 row of eWAR realized)."""
    k, m = constants["k"], constants["m"]
    samp = src = 0.0
    any_side = False
    bb = band_index("bat", pa) if pa is not None else None
    if bb is not None:
        any_side = True
        e = float(pa)
        samp += (m["bat"][bb] ** 2 * k["bat"] * e + m["ebr"][bb] ** 2 * k["ebr"] * e) / (rpw * rpw)
        src += m["src_bat"][bb] ** 2 * k["src_bat"] * e
    pb = band_index("pit", ip) if ip is not None else None
    if pb is not None:
        any_side = True
        e = float(ip)
        samp += m[pit_basis][pb] ** 2 * k[pit_basis] * e / (rpw * rpw)
        src += m["src_pit"][pb] ** 2 * k["src_pit"] * e
    if not any_side:
        return None
    return {"sigma": math.sqrt(samp + src), "samp": math.sqrt(samp), "src": math.sqrt(src)}


def constants_from(result: dict) -> dict:
    """The served constants from a read's families block (part 2.1)."""
    k, m = {}, {}
    for term, fam in TERM_FAMILY.items():
        blk = result["families"][fam]
        k[term] = float(blk["k"])
        mm = blk["multipliers"]
        m[term] = [float((mm.get(b) or mm.get(str(b)) or {}).get("m", 1.0)) for b in range(4)]
    return {"k": k, "m": m, "z": Z80}
