# scratch diagnostic: role conditioning for the pitcher label instrument
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.efv_pitcher_label_harness import build_pool, window, EARLY, MID, TEST  # noqa: E402
from prospect_path import _spearman  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402

SPAN = 3


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def late_window(rec, lo=3, hi=6):
    """Realized role over seasons-since-debut lo..hi-1 (the UNOBSERVED tail)."""
    g = gs = ip = 0.0
    seen = 0
    for i in range(lo, hi):
        ln = rec["lines"].get(i)
        if not ln:
            continue
        seen += 1
        for k, acc in (("g", "g"), ("gs", "gs"), ("ip", "ip")):
            pass
        g += float(ln.get("g") or 0.0)
        gs += float(ln.get("gs") or 0.0)
        ip += float(ln.get("ip") or 0.0)
    return {"g": g, "gs": gs, "ip": ip, "seasons": seen,
            "gs_ratio": (gs / g) if g else None}


def role_of(gs_ratio, thresh=0.5):
    if gs_ratio is None:
        return None
    return "SP" if gs_ratio >= thresh else "RP"


def main():
    pool = build_pool("pit")
    print(f"pool n={len(pool)}  span={SPAN}")
    have_lines = [r for r in pool if window(r, SPAN)["seasons_pitched"] > 0]
    print(f"with MLB pitching lines in first {SPAN} seasons: {len(have_lines)} "
          f"({len(have_lines)/len(pool):.1%})  -> role is UNDEFINED for the rest")

    recs = []
    for r in have_lines:
        w = window(r, SPAN)
        if w["g"] <= 0:
            continue
        recs.append({"rec": r, "w": w, "gsr": w["gs_ratio"], "war3": w["war"],
                     "true6": r["true6"], "dy": r["dy"]})
    print(f"usable (g>0): {len(recs)}")

    # ---------------- 1. gs_ratio distribution / bimodality ----------------
    print("\n=== 1. gs_ratio distribution over the first %d seasons ===" % SPAN)
    bins = [0] * 10
    for x in recs:
        b = min(9, int(x["gsr"] * 10))
        bins[b] += 1
    n = len(recs)
    for i, c in enumerate(bins):
        lo, hi = i / 10, (i + 1) / 10
        print(f"  [{lo:.1f},{hi:.1f}) {c:5d}  {c/n:6.1%}  {'#' * int(60*c/max(bins))}")
    mid_band = sum(1 for x in recs if 0.2 <= x["gsr"] <= 0.8)
    ends = sum(1 for x in recs if x["gsr"] < 0.1 or x["gsr"] > 0.9)
    print(f"  mass in middle band [0.20,0.80]: {mid_band} ({mid_band/n:.1%})")
    print(f"  mass at the two ends (<0.1 or >0.9): {ends} ({ends/n:.1%})")

    # ---------------- 2. per-role stats ----------------
    print("\n=== 2. role split (SP = gs_ratio >= 0.5) ===")
    for th in (0.5,):
        sp = [x for x in recs if x["gsr"] >= th]
        rp = [x for x in recs if x["gsr"] < th]
        print(f"  {'role':4} {'n':>5} {'mean_true6':>11} {'sd_true6':>9} "
              f"{'mean_war3':>10} {'rho(war3,true6)':>16} {'pearson':>8} {'mean_ip3':>9}")
        for nm, grp in (("SP", sp), ("RP", rp), ("ALL", recs)):
            t = [x["true6"] for x in grp]
            w3 = [x["war3"] for x in grp]
            print(f"  {nm:4} {len(grp):>5} {mean(t):>11.3f} {sd(t):>9.3f} "
                  f"{mean(w3):>10.3f} {_spearman(w3, t):>16.4f} {pearson(w3, t):>8.4f} "
                  f"{mean([x['w']['ip'] for x in grp]):>9.1f}")
        # cohort sanity
        for nm, lo, hi in (("early", *EARLY), ("mid", *MID), ("test", *TEST)):
            g = [x for x in recs if lo <= x["dy"] <= hi]
            gsp = sum(1 for x in g if x["gsr"] >= th)
            print(f"    cohort {nm:5} {lo}-{hi}: n={len(g):4d} SP={gsp:4d} RP={len(g)-gsp:4d}")

    th = 0.5
    sp = [x for x in recs if x["gsr"] >= th]
    rp = [x for x in recs if x["gsr"] < th]

    # ---------------- 3. pooled isotonic calibration by role ----------------
    print("\n=== 3. pooled isotonic war3 -> true6: is it mis-calibrated by role? ===")
    early = [x for x in recs if EARLY[0] <= x["dy"] <= EARLY[1]]
    heldout = [x for x in recs if MID[0] <= x["dy"] <= TEST[1]]
    print(f"  fit on early {EARLY} n={len(early)}; evaluate on mid+test n={len(heldout)}")

    iso = IsotonicRegression(out_of_bounds="clip").fit(
        [x["war3"] for x in early], [x["true6"] for x in early])

    def resid_report(grp, label):
        if not grp:
            print(f"  {label:24} n=0")
            return
        pred = list(iso.predict([x["war3"] for x in grp]))
        t = [x["true6"] for x in grp]
        res = [a - b for a, b in zip(t, pred)]
        m, s = mean(res), sd(res)
        se = s / math.sqrt(len(res))
        mae = mean([abs(r) for r in res])
        print(f"  {label:24} n={len(grp):4d} mean_true6={mean(t):7.3f} "
              f"pooled_pred={mean(pred):7.3f} bias={m:+7.3f} (se {se:.3f}, t={m/se if se else 0:+6.2f}) "
              f"mae={mae:6.3f}")
        return m

    ho_sp = [x for x in heldout if x["gsr"] >= th]
    ho_rp = [x for x in heldout if x["gsr"] < th]
    resid_report(heldout, "held-out ALL")
    resid_report(ho_sp, "held-out SP")
    resid_report(ho_rp, "held-out RP")

    print("  -- same, sliced by war3 bucket (bias = true6 - pooled_pred) --")
    edges = [(-99, 0.0), (0.0, 1.0), (1.0, 3.0), (3.0, 6.0), (6.0, 99)]
    print(f"  {'war3 bucket':14} {'SP n':>5} {'SP bias':>9} {'RP n':>5} {'RP bias':>9}")
    for lo, hi in edges:
        s_ = [x for x in ho_sp if lo <= x["war3"] < hi]
        r_ = [x for x in ho_rp if lo <= x["war3"] < hi]
        ps = list(iso.predict([x["war3"] for x in s_])) if s_ else []
        pr = list(iso.predict([x["war3"] for x in r_])) if r_ else []
        bs = mean([x["true6"] - p for x, p in zip(s_, ps)]) if s_ else float("nan")
        br = mean([x["true6"] - p for x, p in zip(r_, pr)]) if r_ else float("nan")
        print(f"  [{lo:>5.1f},{hi:>5.1f}) {len(s_):>5} {bs:>9.3f} {len(r_):>5} {br:>9.3f}")

    # role-conditioned isotonic vs pooled, honest held-out
    print("\n  -- does a ROLE-CONDITIONED isotonic beat the pooled one out of sample? --")
    e_sp = [x for x in early if x["gsr"] >= th]
    e_rp = [x for x in early if x["gsr"] < th]
    iso_sp = IsotonicRegression(out_of_bounds="clip").fit(
        [x["war3"] for x in e_sp], [x["true6"] for x in e_sp])
    iso_rp = IsotonicRegression(out_of_bounds="clip").fit(
        [x["war3"] for x in e_rp], [x["true6"] for x in e_rp])
    pooled_pred = list(iso.predict([x["war3"] for x in heldout]))
    cond_pred = []
    for x in heldout:
        m = iso_sp if x["gsr"] >= th else iso_rp
        cond_pred.append(float(m.predict([x["war3"]])[0]))
    t = [x["true6"] for x in heldout]
    for nm, p in (("pooled iso", pooled_pred), ("role-cond iso", cond_pred)):
        print(f"    {nm:16} rho={_spearman(p, t):.4f} mae={mean([abs(a-b) for a, b in zip(p, t)]):.3f} "
              f"bias={mean([b-a for a, b in zip(p, t)]):+.3f}")
    # KM reference on the same held-out set
    km = [x["war3"] * (6.0 / SPAN) for x in heldout]
    print(f"    {'KM (war3*2)':16} rho={_spearman(km, t):.4f} mae={mean([abs(a-b) for a, b in zip(km, t)]):.3f} "
          f"bias={mean([b-a for a, b in zip(km, t)]):+.3f}")

    # ---------------- 4. role stability early -> seasons 4-6 ----------------
    print("\n=== 4. role STABILITY: first %d seasons vs seasons 4-6 ===" % SPAN)
    trans = {}
    for x in recs:
        lw = late_window(x["rec"])
        late = role_of(lw["gs_ratio"], th)
        early_r = role_of(x["gsr"], th)
        key = (early_r, late if late else "GONE")
        trans.setdefault(key, []).append(x)
    print(f"  {'early':6} {'late(4-6)':10} {'n':>5} {'share':>7} {'mean_true6':>11} "
          f"{'mean_war3':>10} {'mean_war4_6':>12}")
    for early_r in ("SP", "RP"):
        base = [x for x in recs if role_of(x["gsr"], th) == early_r]
        for late in ("SP", "RP", "GONE"):
            grp = trans.get((early_r, late), [])
            if not grp:
                continue
            t_ = [x["true6"] for x in grp]
            w3_ = [x["war3"] for x in grp]
            w46 = [sum(x["rec"]["war"].get(i, 0.0) for i in range(3, 6)) for x in grp]
            print(f"  {early_r:6} {late:10} {len(grp):>5} {len(grp)/len(base):>7.1%} "
                  f"{mean(t_):>11.3f} {mean(w3_):>10.3f} {mean(w46):>12.3f}")

    print("\n  -- role CHANGE effect, controlling for war3 bucket (mean true6) --")
    print(f"  {'war3 bucket':14} {'SP->SP':>16} {'SP->RP':>16} {'RP->RP':>16} {'RP->SP':>16}")
    for lo, hi in edges:
        cells = []
        for key in (("SP", "SP"), ("SP", "RP"), ("RP", "RP"), ("RP", "SP")):
            grp = [x for x in trans.get(key, []) if lo <= x["war3"] < hi]
            cells.append(f"n={len(grp):3d} {mean([x['true6'] for x in grp]):6.2f}"
                         if grp else f"n=  0    ---")
        print(f"  [{lo:>5.1f},{hi:>5.1f}) " + " ".join(f"{c:>16}" for c in cells))

    # is the change itself predictive net of war3? residual vs pooled iso
    print("\n  -- bias vs pooled iso, by transition (held-out cohorts only) --")
    for key in (("SP", "SP"), ("SP", "RP"), ("RP", "RP"), ("RP", "SP"), ("SP", "GONE"), ("RP", "GONE")):
        grp = [x for x in trans.get(key, []) if MID[0] <= x["dy"] <= TEST[1]]
        if len(grp) < 5:
            print(f"    {key[0]}->{key[1]:5} n={len(grp):4d}  (too few)")
            continue
        p = list(iso.predict([x["war3"] for x in grp]))
        res = [x["true6"] - pp for x, pp in zip(grp, p)]
        s = sd(res); se = s / math.sqrt(len(res))
        print(f"    {key[0]}->{key[1]:5} n={len(grp):4d} bias={mean(res):+7.3f} (se {se:.3f}, "
              f"t={mean(res)/se if se else 0:+6.2f})")

    # ---------------- 5. can EARLY-only info see the change coming? ----------
    print("\n=== 5. is early role even INFORMATIVE net of war3? (held-out) ===")
    # partial: rho of gs_ratio vs residual(true6 - pooled iso(war3))
    p = list(iso.predict([x["war3"] for x in heldout]))
    res = [x["true6"] - pp for x, pp in zip(heldout, p)]
    for feat in ("gs_ratio", "ip", "ip_per_season", "g", "seasons_pitched", "k_pct", "era"):
        v = [x["w"][feat] for x in heldout]
        print(f"    rho(residual, {feat:16}) = {_spearman(v, res):+.4f}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# gate arm: does role conditioning move the ACTUAL scoreboard (model lift)?
# ---------------------------------------------------------------------------

def _gate():
    from tools.efv_pitcher_label_harness import run_gate

    TH = 0.5

    def _feat(rec, span):
        w = window(rec, span)
        return w["war"], (w["gs_ratio"] if w["g"] > 0 else None), w

    def fit_pooled(rows):
        xs = [window(r, SPAN)["war"] for r in rows]
        return IsotonicRegression(out_of_bounds="clip").fit(xs, [r["true6"] for r in rows])

    def pred_pooled(st, rec, span):
        return float(st.predict([window(rec, span)["war"]])[0])

    def fit_role(rows):
        out = {}
        for nm, sel in (("SP", lambda w: w["g"] > 0 and w["gs_ratio"] >= TH),
                        ("RP", lambda w: not (w["g"] > 0 and w["gs_ratio"] >= TH))):
            g = [r for r in rows if sel(window(r, SPAN))]
            out[nm] = IsotonicRegression(out_of_bounds="clip").fit(
                [window(r, SPAN)["war"] for r in g], [r["true6"] for r in g])
        return out

    def pred_role(st, rec, span):
        w = window(rec, span)
        m = st["SP"] if (w["g"] > 0 and w["gs_ratio"] >= TH) else st["RP"]
        return float(m.predict([w["war"]])[0])

    def fit_offset(rows):
        iso = fit_pooled(rows)
        res = {"SP": [], "RP": []}
        for r in rows:
            w = window(r, SPAN)
            k = "SP" if (w["g"] > 0 and w["gs_ratio"] >= TH) else "RP"
            res[k].append(r["true6"] - float(iso.predict([w["war"]])[0]))
        return {"iso": iso, "off": {k: (sum(v) / len(v) if v else 0.0) for k, v in res.items()}}

    def pred_offset(st, rec, span):
        w = window(rec, span)
        k = "SP" if (w["g"] > 0 and w["gs_ratio"] >= TH) else "RP"
        return float(st["iso"].predict([w["war"]])[0]) + st["off"][k]

    def fit_km_role(rows):
        """KM * per-role multiplicative correction fit on early."""
        num = {"SP": [0.0, 0.0], "RP": [0.0, 0.0]}
        for r in rows:
            w = window(r, SPAN)
            k = "SP" if (w["g"] > 0 and w["gs_ratio"] >= TH) else "RP"
            num[k][0] += r["true6"]
            num[k][1] += w["war"] * (6.0 / SPAN)
        return {k: (v[0] / v[1] if v[1] else 1.0) for k, v in num.items()}

    def pred_km_role(st, rec, span):
        w = window(rec, span)
        k = "SP" if (w["g"] > 0 and w["gs_ratio"] >= TH) else "RP"
        return w["war"] * (6.0 / span) * st[k]

    run_gate({
        "B_iso_pooled": (fit_pooled, pred_pooled),
        "D_iso_role_split": (fit_role, pred_role),
        "E_iso_plus_role_off": (fit_offset, pred_offset),
        "F_km_x_role_scale": (fit_km_role, pred_km_role),
    }, span=SPAN, side="pit")
