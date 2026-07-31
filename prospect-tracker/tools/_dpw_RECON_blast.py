"""RECONCILE (b)+(c): blast radius on SERVED consumers + the coherence trade test.
Validates its own harness against the SERVED artifact before reporting any delta."""
import sys, json, copy
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import numpy as np, value_framework as vf

cfg = vf._config(); ORIG = copy.deepcopy(cfg)
def restore():
    cfg.clear(); cfg.update(copy.deepcopy(ORIG)); vf._reset_derived_caches()
def set_arm(fa_on, infl=None, disc=None):
    restore()
    if fa_on:
        cfg["dollars_per_war"]["fa_implied"]["enabled"] = True
        vf._apply_fa_implied_reanchor(cfg)
    if infl is not None: cfg["dollars_per_war_inflation"] = infl
    if disc is not None: cfg["discount_rate"] = disc
    vf._reset_derived_caches()

# ---------- harness validation against the SERVED board ----------
board = json.loads((HERE/"data"/"xfv.json").read_text())["by_player"]
rows = [(k, v) for k, v in board.items()
        if v.get("surplus_mm") is not None and v.get("xfv_grade_quantile") is not None]
print(f"served rows with surplus: {len(rows)}")
def priced(k_is_pit_grade):
    g, is_pit = k_is_pit_grade
    raw = vf.expected_surplus_usd(g, is_pit, None)
    return float(vf.apply_calibration((raw or 0.0)/1e6, g, is_pit))
restore()
recon = np.array([priced((v["xfv_grade_quantile"], v.get("side") == "P")) for _, v in rows])
served = np.array([float(v["surplus_mm"]) for _, v in rows])
d = recon - served
print(f"HARNESS CHECK vs served surplus_mm: mean|d| {np.abs(d).mean():.4f}M  median|d| {np.median(np.abs(d)):.4f}M  "
      f"p95|d| {np.percentile(np.abs(d),95):.4f}M  frac within 0.05M {np.mean(np.abs(d)<=0.05):.3f}")
print("  (age/eta kwargs are not on the served payload, so exact reproduction is not expected;")
print("   this quantifies how good the proxy is BEFORE any delta is reported.)")

# ---------- blast radius on the board ----------
grades = [(v["xfv_grade_quantile"], v.get("side") == "P") for _, v in rows]
names  = [k for k, _ in rows]
def board_prices():
    return np.array([priced(g) for g in grades])
ARMS = [("A production", False, None, None),
        ("B fa_implied", True, None, None),
        ("C +infl .0483", True, 0.0483099, None),
        ("D coherent gross", True, 0.0483099, 0.10)]
base = None; out = {}
for nm, fa, infl, disc in ARMS:
    set_arm(fa, infl, disc)
    p = board_prices()
    if base is None: base = p
    out[nm] = p
    tot = p.sum(); r = p/np.where(base > 0, base, np.nan)
    print(f"\n{nm:17s} aggregate ${tot:,.0f}M  ({100*(tot/base.sum()-1):+.2f}% vs A)")
    if nm != "A production":
        dd = p - base
        print(f"  per player: mean {dd.mean():+.3f}M  median {np.median(dd):+.3f}M  p95 {np.percentile(dd,95):+.3f}M  max {dd.max():+.3f}M")
        idx = np.argsort(-dd)[:6]
        print("  biggest movers: " + ", ".join(f"{names[i]} {base[i]:.1f}->{p[i]:.1f}" for i in idx))
        print(f"  players moving >$1M: {(np.abs(dd)>1).sum()}  >$5M: {(np.abs(dd)>5).sum()}  unchanged: {(np.abs(dd)<1e-9).sum()}")
restore()
P = Path(r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
np.save(P/"board_arms.npy", np.vstack([out[a[0]] for a in ARMS]))
(P/"board_names.json").write_text(json.dumps(names))
print("\nWROTE board arrays")
