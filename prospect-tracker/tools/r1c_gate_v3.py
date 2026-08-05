"""R1c gate, THIRD design. Built from the CONTROL SET, not from a candidate.

WHY THE FIRST TWO FAILED, because the third has to not repeat it. Both started
from whichever leg had convicted the last candidate and tried to make that leg
fairer. Attempt 1 (level-neutral MAE) was refuted on paper: de-meaning erases a
pure level injection, so it passes shape by construction. Attempt 2 (RMSE + an
exposure leg) was refuted in practice: leg (d) measures EXPOSURE and a level
injection moves the PREDICTION, so it was blind to the control it had to survive.

SO THIS TIME THE CONTROL COMES FIRST AND THE LEG IS DERIVED FROM IT.

The question a gate for "did this repair the model" must answer is not "did the
number move" but "did it move for a REASON". State that as a testable property:

    An informative arm reduces error on the ROWS THAT WERE WRONG.
    An information-free arm moves the level and leaves the row pattern alone.

That is directly testable with the arm's own adjustment as its own null: shuffle
the per-row adjustment within (season, side) cells, holding the marginal fixed,
and ask whether the REAL placement reduces error more than a random placement of
the SAME adjustments. A constant shift is invariant under that shuffle, so it
scores z ~ 0 BY CONSTRUCTION. That is the property the first two attempts lacked.

PRE-REGISTERED, in grading order:

  (0) INFORMATION, graded FIRST and disqualifying. Total absolute error over the
      graded population must fall more under the real arm than under its own
      permutation null: z >= +3 over 200 seeded shuffles. An arm that cannot
      beat a reshuffle of its own adjustment is not a repair regardless of what
      it does to the level.
  (a) LEVEL: |D_2025| < 34.556 on the de-duplicated basis (D0 = -69.11).
  (b) SHAPE on RMSE, eleven objects, seeded paired bootstrap, FAIL if any object
      has delta > 0 AND > 2*SE. RMSE because leg (a) is a mean objective.
  (c) TEAM: recentered 2025 team MAE not worse. Recorded as blind to a pure
      level shift, so passing is not evidence in favour.
  (d) EXPOSURE: played-row PA/IP bias not worse in absolute terms.

  VACUITY REQUIREMENT: all three information-free arms must FAIL. If any passes,
  this design joins the other two in the ledger and NO candidate is graded.

PREDICTION, recorded before running: the three injections fail leg (0) at z ~ 0.
C1b and C1c pass leg (0) (their published permutation z are +20.51 and +12.02 on
the level move) and are then decided by (b) and (d), where C1b's played-row PA
bias 10.02 -> 39.77 should fail (d). Expected end state: NO candidate ships, and
the gate rejects for a defensible reason for the first time.
"""
import json, os, sys
import numpy as np

LANE = r"C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/9578cc36-1e62-41cf-8a3f-f9e44a766e1e/scratchpad/R1c"
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LANE)
import arms                       # noqa: E402
import bench as B                 # noqa: E402

b = B.Bench()
rows = b.rows
base = np.asarray(b.base_pred, float)
act_pub = np.asarray(b.act_pub, float)
act_ded = np.asarray(b.act_dedup, float)
asg = np.asarray(b.assigned, bool)
t25 = np.asarray([r["target"] == 2025 for r in rows], bool)
side = np.asarray([r["side"] for r in rows])
season = np.asarray([r["target"] for r in rows])
hit, pit = side == "hit", side == "pit"
expo_act = np.asarray([r.get("expo_act") or 0.0 for r in rows], float)
expo_base = np.asarray(arms.base_expo(rows), float)

D0 = float((base - act_ded)[asg & t25].sum())
BAR = abs(D0) / 2.0
GRADED = asg & t25          # the population leg (a) is graded on
Z_INFO = 3.0
NPERM = 200
SEED = 20260804


def leg0_information(pred):
    """Does the REAL placement of this arm's adjustment beat a reshuffle of it?

    Shuffle within (season, side) cells so the marginal is untouched and only
    the row-to-row ASSIGNMENT is randomised. Metric is total absolute error over
    the graded population: an arm that fixes the rows that were wrong reduces it
    more than a random placement of the same numbers does."""
    adj = np.asarray(pred, float) - base
    err_base = float(np.abs(base - act_pub)[GRADED].sum())
    real = err_base - float(np.abs(base + adj - act_pub)[GRADED].sum())
    rng = np.random.default_rng(SEED)
    cells = [(s, sd) for s in np.unique(season) for sd in ("hit", "pit")]
    null = np.empty(NPERM)
    for k in range(NPERM):
        sh = adj.copy()
        for s, sd in cells:
            m = np.where((season == s) & (side == sd))[0]
            if m.size > 1:
                sh[m] = rng.permutation(sh[m])
        null[k] = err_base - float(np.abs(base + sh - act_pub)[GRADED].sum())
    mu, sd_ = float(null.mean()), float(null.std(ddof=1))
    z = (real - mu) / sd_ if sd_ > 1e-12 else 0.0
    return {"real_err_reduction": round(real, 3), "null_mean": round(mu, 3),
            "null_sd": round(sd_, 3), "z": round(z, 2), "pass": bool(z >= Z_INFO)}


def _objects(pred):
    out = {"pooled": (np.abs(pred - act_pub), np.abs(base - act_pub))}
    m = np.asarray(b.idx_assigned_loose, int)
    out["assigned_teamtable"] = (np.abs(pred - act_pub)[m], np.abs(base - act_pub)[m])
    for c, idx in b.idx_cohort.items():
        i = np.asarray(idx, int)
        out[c] = (np.abs(pred - act_pub)[i], np.abs(base - act_pub)[i])
    return out


def leg_b(pred, nboot=1000):
    rng = np.random.default_rng(SEED + 1)
    worst = None
    for name, (en, eb) in _objects(pred).items():
        d = float(np.sqrt((en ** 2).mean()) - np.sqrt((eb ** 2).mean()))
        n = len(en)
        bs = np.empty(nboot)
        for k in range(nboot):
            i = rng.integers(0, n, n)
            bs[k] = np.sqrt((en[i] ** 2).mean()) - np.sqrt((eb[i] ** 2).mean())
        se = float(bs.std(ddof=1)) or 1e-12
        z = d / se
        if worst is None or z > worst[2]:
            worst = (name, d, z)
    return {"object": worst[0], "delta": round(worst[1], 4), "z": round(worst[2], 2),
            "pass": bool(worst[1] <= 0 or worst[2] <= 2.0)}


def leg_d(expo_new):
    out, ok = {}, True
    for lab, mask in (("hit", hit), ("pit", pit)):
        m = mask & t25 & (expo_act > 0)
        if m.sum() < 20:
            continue
        bb = float((expo_base - expo_act)[m].mean())
        nn = float((np.asarray(expo_new, float) - expo_act)[m].mean())
        w = abs(nn) > abs(bb) + 1e-9
        out[lab] = {"base": round(bb, 2), "arm": round(nn, 2), "worse": bool(w)}
        ok = ok and not w
    out["pass"] = ok
    return out


def grade(name, pred, expo_new):
    pred = np.asarray(pred, float)
    g0 = leg0_information(pred)
    D = float((pred - act_ded)[GRADED].sum())
    ga = abs(D) < BAR
    gb = leg_b(pred)
    gd = leg_d(expo_new if expo_new is not None else expo_base)
    ships = bool(g0["pass"] and ga and gb["pass"] and gd["pass"])
    return {"arm": name, "leg0_info": g0, "D": round(D, 2), "leg_a": bool(ga),
            "leg_b_rmse": gb, "leg_d": gd, "SHIPS": ships}


print(f"D0={D0:.2f}  leg(a) bar=|D|<{BAR:.3f}  leg(0) needs z>={Z_INFO}\n")
need = float(-D0)
n_at = int(GRADED.sum())
controls = [
    ("VACUITY per-exposure (zeroes D)",
     base + need * (expo_base / expo_base[GRADED].sum()) * GRADED, expo_base),
    ("VACUITY per-row constant (zeroes D)",
     base + np.where(GRADED, need / n_at, 0.0), expo_base),
    ("VACUITY per-row constant (half-way)",
     base + np.where(GRADED, need / (2 * n_at), 0.0), expo_base),
]
rep = {"D0": round(D0, 2), "bar": round(BAR, 3), "z_info_threshold": Z_INFO}
print("CONTROLS (all must FAIL):")
cres = []
for nm, pr, ex in controls:
    g = grade(nm, pr, ex)
    cres.append(g)
    print(f"  {nm[:38]:40s} leg0 z={g['leg0_info']['z']:+7.2f} {'PASS' if g['leg0_info']['pass'] else 'fail':4s}"
          f" | a={g['leg_a']!s:5s} b={g['leg_b_rmse']['pass']!s:5s} d={g['leg_d']['pass']!s:5s}"
          f" -> SHIPS={g['SHIPS']}")
rep["controls"] = cres
rep["vacuity_ok"] = all(not c["SHIPS"] for c in cres)
print(f"\nVACUITY REQUIREMENT MET: {rep['vacuity_ok']}")

if rep["vacuity_ok"]:
    print("\nCANDIDATES:")
    cands = []
    s, _d = arms.fit_c1b(b)          # fit_c1b returns (s, deficit)
    pr_c1b, e = arms.c1_deshrink(b, s, "hit")   # returns (pred, expo)
    cands.append((f"C1b hit de-shrink s={s:.2f}", pr_c1b, e))
    off, dq = arms.fit_c1c(b)
    for sc in (1.0, 4.0):
        pr, ee = arms.apply_c1c(b, off, dq, "hit", scale=sc)
        cands.append((f"C1c decile PT scale {sc:.2f}", pr, ee))
    d2, _n2 = arms.fit_c2(b)
    pr2, _dm = arms.apply_c2(b, d2, "pit", scale=1.0)
    cands.append(("C2 pit rate by ROLE", pr2, expo_base))
    out = []
    for nm, pr, ex in cands:
        g = grade(nm, pr, ex)
        out.append(g)
        print(f"  {nm[:34]:36s} leg0 z={g['leg0_info']['z']:+8.2f} {'PASS' if g['leg0_info']['pass'] else 'fail':4s}"
              f" | a={g['leg_a']!s:5s} b={g['leg_b_rmse']['pass']!s:5s}"
              f" d={g['leg_d']['pass']!s:5s} -> SHIPS={g['SHIPS']}")
        if not g["leg_d"]["pass"]:
            for k in ("hit", "pit"):
                if k in g["leg_d"] and g["leg_d"][k]["worse"]:
                    print(f"        leg(d) {k}: {g['leg_d'][k]['base']:+.2f} -> {g['leg_d'][k]['arm']:+.2f}")
    rep["candidates"] = out
    rep["any_ship"] = any(c["SHIPS"] for c in out)
    print(f"\nANY CANDIDATE SHIPS: {rep['any_ship']}")
else:
    print("\n*** DESIGN 3 ALSO VACUOUS - no candidate graded ***")
open(os.path.join(OUT, "design.json"), "w", encoding="utf-8").write(json.dumps(rep, indent=1))
print("\nwrote design.json")
