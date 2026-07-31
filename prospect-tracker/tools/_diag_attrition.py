# scratch diagnostic (not shipped): is pitcher 6yr WAR an ATTRITION problem?
from __future__ import annotations
import sys, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from efv_pitcher_label_harness import build_pool, window, EARLY, MID, TEST  # noqa: E402
from prospect_path import _spearman  # noqa: E402


def pearson(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def auc(scores, labels):
    """Mann-Whitney AUC of `scores` for binary `labels` (1=positive)."""
    pairs = sorted(zip(scores, labels))
    # rank with ties averaged
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    npos = sum(1 for _, l in pairs if l == 1)
    nneg = len(pairs) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    spos = sum(r for r, (_, l) in zip(ranks, pairs) if l == 1)
    return (spos - npos * (npos + 1) / 2.0) / (npos * nneg)


def partial_rho(x, y, z):
    """Spearman partial correlation of x,y controlling for z."""
    rxy, rxz, rzy = _spearman(x, y), _spearman(x, z), _spearman(z, y)
    den = math.sqrt(max(1e-12, (1 - rxz ** 2) * (1 - rzy ** 2)))
    return (rxy - rxz * rzy) / den


pool = build_pool("pit")
print(f"pool n={len(pool)}  cohorts {min(r['dy'] for r in pool)}-{max(r['dy'] for r in pool)}")
print(f"mlbam coverage {sum(1 for r in pool if r['mlbam'])/len(pool):.1%}")

for r in pool:
    r["early3"] = sum(r["war"].get(i, 0.0) for i in range(3))
    r["late3"] = sum(r["war"].get(i, 0.0) for i in range(3, 6))
    r["sum6"] = r["early3"] + r["late3"]
    ip_late = 0.0
    seen_late = 0
    for i in (3, 4, 5):
        ln = r["lines"].get(i)
        if ln:
            try:
                ip_late += float(ln.get("ip") or 0.0)
            except (TypeError, ValueError):
                pass
            seen_late += 1
    r["ip_late"] = ip_late
    r["seasons_late"] = seen_late
    # survival: threw MLB innings in seasons 4-6 (index 3..5)
    r["surv_ip"] = 1 if ip_late > 0 else 0
    r["surv_war"] = 1 if abs(r["late3"]) > 1e-9 else 0

# sanity: does early+late reconstruct true6?
d = [abs(r["sum6"] - r["true6"]) for r in pool]
print(f"|war(0..5) - true6| : mean {sum(d)/len(d):.3f}  max {max(d):.3f}  "
      f"n_exact(<0.05) {sum(1 for x in d if x < 0.05)}/{len(d)}")

# ---------------------------------------------------------------- decomposition
E = [r["early3"] for r in pool]
L = [r["late3"] for r in pool]
T = [r["true6"] for r in pool]
n = len(pool)


def var(v):
    m = sum(v) / len(v)
    return sum((x - m) ** 2 for x in v) / len(v)


vE, vL, vT = var(E), var(L), var(T)
cov = sum((a - sum(E) / n) * (b - sum(L) / n) for a, b in zip(E, L)) / n
print("\n=== DECOMPOSITION of true6 into war(0..2) and war(3..5) ===")
print(f"  mean  early3 {sum(E)/n:6.3f}   late3 {sum(L)/n:6.3f}   true6 {sum(T)/n:6.3f}")
print(f"  MASS  share of total WAR in late window: {sum(L)/max(1e-9,sum(T)):.1%}  "
      f"(early {sum(E)/max(1e-9,sum(T)):.1%})")
print(f"  SD    early3 {math.sqrt(vE):.3f}  late3 {math.sqrt(vL):.3f}  true6 {math.sqrt(vT):.3f}")
print(f"  VAR   decomposition of Var(true6)={vT:.3f}: "
      f"Var(early)={vE:.3f} ({vE/vT:.1%})  Var(late)={vL:.3f} ({vL/vT:.1%})  "
      f"2Cov={2*cov:.3f} ({2*cov/vT:.1%})")
print(f"  corr(early3, late3): pearson {pearson(E,L):.4f}   spearman {_spearman(E,L):.4f}")
print(f"  corr(early3, true6): pearson {pearson(E,T):.4f}   spearman {_spearman(E,T):.4f}")
print(f"  corr(late3,  true6): pearson {pearson(L,T):.4f}   spearman {_spearman(L,T):.4f}")

# ---------------------------------------------------------------- attrition counts
van_war = sum(1 for r in pool if abs(r["late3"]) < 0.1)
van_ip = sum(1 for r in pool if r["ip_late"] <= 0)
have_lines = [r for r in pool if r["mlbam"]]
van_ip_cov = sum(1 for r in have_lines if r["ip_late"] <= 0)
acc = [r for r in pool if r["late3"] >= 1.0]
print("\n=== ATTRITION ===")
print(f"  |late3 WAR| < 0.1 (vanished/replacement): {van_war}/{n} = {van_war/n:.1%}")
print(f"  late3 WAR >= 1.0 (kept accruing):         {len(acc)}/{n} = {len(acc)/n:.1%}")
print(f"  zero MLB IP in seasons 4-6 (all rows):    {van_ip}/{n} = {van_ip/n:.1%}")
print(f"  zero MLB IP in seasons 4-6 (mlbam rows):  {van_ip_cov}/{len(have_lines)} = "
      f"{van_ip_cov/max(1,len(have_lines)):.1%}")
surv = [r for r in pool if r["surv_war"] == 1]
print(f"  survivors (any late WAR): n={len(surv)}  mean late3 {sum(x['late3'] for x in surv)/max(1,len(surv)):.3f}"
      f"  share of all late WAR {sum(x['late3'] for x in surv)/max(1e-9,sum(L)):.0%}")
# how much of true6 SPREAD is decided by survival alone
s1 = [r["true6"] for r in pool if r["surv_war"] == 1]
s0 = [r["true6"] for r in pool if r["surv_war"] == 0]
print(f"  mean true6 | survived {sum(s1)/max(1,len(s1)):6.3f} (n={len(s1)})  "
      f"| vanished {sum(s0)/max(1,len(s0)):6.3f} (n={len(s0)})")
print(f"  AUC of the survival flag for ranking true6: "
      f"{auc([r['surv_war'] for r in pool],[1 if r['true6']>=sorted(T)[len(T)//2] else 0 for r in pool]):.4f}")

# ---------------------------------------------------------------- signals
print("\n=== EARLY-WINDOW (span=3) SIGNALS vs LATE WAR and vs LATE SURVIVAL ===")
sub = [r for r in pool if r["mlbam"]]           # need MLB lines for rate/role features
for r in sub:
    r["w"] = window(r, 3)
    ln0 = r["lines"].get(0)
    a = None
    if ln0 is not None:
        try:
            a = float(ln0.get("age"))
        except (TypeError, ValueError):
            a = None
    r["age_debut"] = a
print(f"  subset with MLB lines: n={len(sub)}  "
      f"(zero-IP-late {sum(1 for r in sub if r['ip_late']<=0)/len(sub):.1%})")

SIGNALS = ["war", "war_per_season", "ip", "ip_per_season", "g", "gs", "gs_ratio",
           "k_pct", "bb_pct", "kbb", "era", "war_per_ip", "seasons_pitched",
           "tj_in_window", "tj_pre_debut"]

Ls = [r["late3"] for r in sub]
Ss = [r["surv_ip"] for r in sub]
Es = [r["early3"] for r in sub]
print(f"\n  {'signal':16} {'n':>4} {'rho_late':>9} {'rho|earlyWAR':>13} "
      f"{'AUC_surv':>9} {'rho_surv':>9} {'AUCsurv|earlyWARresid':>0}")
rows_out = []
for s in SIGNALS:
    xs = [r["w"][s] for r in sub]
    if len(set(xs)) < 2:
        print(f"  {s:16} {len(xs):>4}   constant")
        continue
    rl = _spearman(xs, Ls)
    pl = partial_rho(xs, Ls, Es)
    a_ = auc(xs, Ss)
    rs = _spearman(xs, [float(v) for v in Ss])
    ps = partial_rho(xs, [float(v) for v in Ss], Es)
    rows_out.append((s, len(xs), rl, pl, a_, rs, ps))
    print(f"  {s:16} {len(xs):>4} {rl:>9.4f} {pl:>13.4f} {a_:>9.4f} {rs:>9.4f} {ps:>9.4f}")

# age at debut (realized, from the MLB debut-season line)
sub_age = [r for r in sub if r["age_debut"] is not None]
if len(sub_age) >= 20:
    xs = [r["age_debut"] for r in sub_age]
    rl = _spearman(xs, [r["late3"] for r in sub_age])
    pl = partial_rho(xs, [r["late3"] for r in sub_age], [r["early3"] for r in sub_age])
    a_ = auc(xs, [r["surv_ip"] for r in sub_age])
    rs = _spearman(xs, [float(r["surv_ip"]) for r in sub_age])
    ps = partial_rho(xs, [float(r["surv_ip"]) for r in sub_age],
                     [r["early3"] for r in sub_age])
    print(f"  {'age_debut':16} {len(xs):>4} {rl:>9.4f} {pl:>13.4f} {a_:>9.4f} {rs:>9.4f} {ps:>9.4f}")

# baseline: early WAR itself
print(f"\n  BASELINE early3 WAR: rho_late {_spearman(Es, Ls):.4f}  "
      f"AUC_surv {auc(Es, Ss):.4f}  rho_surv {_spearman(Es,[float(v) for v in Ss]):.4f}")
km3 = [r["w"]["war"] * 2.0 for r in sub]
print(f"  BASELINE KM(3)->6  : rho_true6 {_spearman(km3,[r['true6'] for r in sub]):.4f}")

# ---------------------------------------------------------------- conditional on survival
print("\n=== AMONG SURVIVORS ONLY (any MLB IP in seasons 4-6) ===")
sv = [r for r in sub if r["surv_ip"] == 1]
if len(sv) >= 20:
    Lv = [r["late3"] for r in sv]
    Ev = [r["early3"] for r in sv]
    print(f"  n={len(sv)}   rho(early3, late3)={_spearman(Ev,Lv):.4f}")
    for s in SIGNALS:
        xs = [r["w"][s] for r in sv]
        if len(set(xs)) < 2:
            continue
        print(f"  {s:16} rho_late {_spearman(xs,Lv):>8.4f}   partial|early {partial_rho(xs,Lv,Ev):>8.4f}")

# ---------------------------------------------------------------- cohort split check
print("\n=== COHORT SPLIT (harness windows) ===")
for nm, (lo, hi) in (("early", EARLY), ("mid", MID), ("test", TEST)):
    g = [r for r in pool if lo <= r["dy"] <= hi]
    if not g:
        continue
    gl = [r["late3"] for r in g]
    print(f"  {nm:5} {lo}-{hi} n={len(g):3}  late-mass {sum(gl)/max(1e-9,sum(r['true6'] for r in g)):6.1%}"
          f"  vanished(|late|<0.1) {sum(1 for r in g if abs(r['late3'])<0.1)/len(g):5.1%}"
          f"  rho(early3,late3) {_spearman([r['early3'] for r in g], gl):6.3f}")

# ---------------------------------------------------------------- combined check
print("\n=== CAN EARLY SIGNALS ADD TO EARLY WAR? (fit on early 2011-2015, eval on mid+test) ===")
try:
    import numpy as np
except ImportError:
    np = None
if np is not None:
    fit_g = [r for r in sub if EARLY[0] <= r["dy"] <= EARLY[1]]
    ev_g = [r for r in sub if MID[0] <= r["dy"] <= TEST[1]]

    def X(rows, cols):
        return np.array([[1.0] + [float(r["w"][c]) if c in r["w"] else float(r[c] or 0.0)
                                  for c in cols] for r in rows])

    def ols_eval(cols, y_key, label):
        A, b = X(fit_g, cols), np.array([float(r[y_key]) for r in fit_g])
        beta = np.linalg.lstsq(A, b, rcond=None)[0]
        p = (X(ev_g, cols) @ beta).tolist()
        yv = [float(r[y_key]) for r in ev_g]
        print(f"    {label:52} rho={_spearman(p, yv):.4f}"
              + (f"  AUC={auc(p, yv):.4f}" if y_key in ("surv_ip",) else ""))
        return p

    print(f"  n_fit={len(fit_g)} n_eval={len(ev_g)}")
    print("  -> LATE-window WAR (seasons 4-6)")
    ols_eval(["war"], "late3", "early WAR only")
    ols_eval(["war", "ip_per_season", "seasons_pitched"], "late3", "+ IP/season + seasons_pitched")
    ols_eval(["war", "ip_per_season", "seasons_pitched", "kbb", "gs_ratio", "era"], "late3",
             "+ kbb + gs_ratio + era")
    print("  -> SURVIVAL (any MLB IP in seasons 4-6)")
    ols_eval(["war"], "surv_ip", "early WAR only")
    ols_eval(["war", "ip_per_season", "seasons_pitched"], "surv_ip", "+ IP/season + seasons_pitched")
    ols_eval(["war", "ip_per_season", "seasons_pitched", "kbb", "gs_ratio", "era"], "surv_ip",
             "+ kbb + gs_ratio + era")
    print("  -> TRUE 6yr WAR directly (vs the shipped KM x2 rule)")
    yv = [r["true6"] for r in ev_g]
    print(f"    {'KM label  war(0..2)*2':52} rho={_spearman([r['w']['war']*2 for r in ev_g], yv):.4f}")
    A, b = X(fit_g, ["war"]), np.array([r["true6"] for r in fit_g])
    beta = np.linalg.lstsq(A, b, rcond=None)[0]
    print(f"    {'OLS true6 ~ early WAR':52} rho={_spearman((X(ev_g,['war'])@beta).tolist(), yv):.4f}")
    cols = ["war", "ip_per_season", "seasons_pitched", "kbb", "gs_ratio", "era"]
    A = X(fit_g, cols)
    beta = np.linalg.lstsq(A, b, rcond=None)[0]
    print(f"    {'OLS true6 ~ early WAR + attrition signals':52} rho={_spearman((X(ev_g,cols)@beta).tolist(), yv):.4f}")

# -------------------------------------------------- two-part (hazard x magnitude)
print("\n=== TWO-PART STRUCTURE: true6_hat = early3 + P(survive)*E[late|survive] ===")
if np is not None:
    def Xm(rows, cols):
        return np.array([[1.0] + [float(r["w"][c]) for c in cols] for r in rows])
    SURVC = ["war", "ip_per_season", "seasons_pitched", "kbb", "gs_ratio", "era"]
    MAGC = ["war", "ip_per_season", "gs_ratio", "kbb"]
    bs = np.linalg.lstsq(Xm(fit_g, SURVC), np.array([float(r["surv_ip"]) for r in fit_g]), rcond=None)[0]
    sv_fit = [r for r in fit_g if r["surv_ip"] == 1]
    bm = np.linalg.lstsq(Xm(sv_fit, MAGC), np.array([r["late3"] for r in sv_fit]), rcond=None)[0]
    p = np.clip(Xm(ev_g, SURVC) @ bs, 0.0, 1.0)
    m = Xm(ev_g, MAGC) @ bm
    hat = np.array([r["w"]["war"] for r in ev_g]) + p * m
    yv = [r["true6"] for r in ev_g]
    print(f"  n_eval={len(ev_g)}  survival-AUC of P(survive)={auc(p.tolist(), [r['surv_ip'] for r in ev_g]):.4f}")
    print(f"    {'KM  war(0..2)*2':44} rho={_spearman([r['w']['war']*2 for r in ev_g], yv):.4f}"
          f"  mae={sum(abs(r['w']['war']*2-r['true6']) for r in ev_g)/len(ev_g):.3f}")
    print(f"    {'TWO-PART early + P(surv)*E[late|surv]':44} rho={_spearman(hat.tolist(), yv):.4f}"
          f"  mae={float(np.mean(np.abs(hat-np.array(yv)))):.3f}")
    # oracle-ish ceilings for orientation
    print(f"    {'ORACLE-SURV early + surv_flag*E[late|surv]':44} "
          f"rho={_spearman((np.array([r['w']['war'] for r in ev_g]) + np.array([r['surv_ip'] for r in ev_g])*m).tolist(), yv):.4f}")
    print(f"    {'ORACLE-LATE early + true late3 (=true6)':44} "
          f"rho={_spearman([r['true6'] for r in ev_g], yv):.4f}")

# -------------------------------------------------- where does the KM label err?
print("\n=== KM LABEL ERROR (war(0..2)*2 - true6), by late-window survival ===")
for grp, nm in ((1, "survived (IP in yrs 4-6)"), (0, "vanished")):
    g = [r for r in sub if r["surv_ip"] == grp]
    err = [r["w"]["war"] * 2 - r["true6"] for r in g]
    print(f"  {nm:26} n={len(g):3}  mean_err {sum(err)/len(err):+7.3f}  "
          f"mae {sum(abs(e) for e in err)/len(err):6.3f}  "
          f"mean_true6 {sum(r['true6'] for r in g)/len(g):6.3f}")
errs = [r["w"]["war"] * 2 - r["true6"] for r in sub]
print(f"  ALL                        n={len(sub)}  mean_err {sum(errs)/len(errs):+7.3f}  "
      f"mae {sum(abs(e) for e in errs)/len(errs):6.3f}")
print(f"  rho(KM error, survival flag) = {_spearman(errs, [float(r['surv_ip']) for r in sub]):.4f}")
print(f"  rho(KM error, late3 WAR)     = {_spearman(errs, [r['late3'] for r in sub]):.4f}")

print("\n=== SPAN SENSITIVITY: how much of true6 is already observed at span s ===")
for s in (1, 2, 3, 4):
    obs = [sum(r["war"].get(i, 0.0) for i in range(s)) for r in pool]
    rest = [r["true6"] - o for r, o in zip(pool, obs)]
    print(f"  span={s}  observed-mass {sum(obs)/max(1e-9,sum(T)):5.1%}  "
          f"rho(obs, true6) {_spearman(obs, T):.4f}  "
          f"rho(obs, remaining) {_spearman(obs, rest):.4f}  "
          f"KM rho {_spearman([o*6.0/s for o in obs], T):.4f}")
