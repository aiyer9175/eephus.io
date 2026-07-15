# Verify the patched value_framework:
#  (1) incumbent p_bucket_given_fv output is IDENTICAL to production,
#  (2) p_bucket_given_fv_age reproduces the lab head exactly,
#  (3) fallbacks (hitter / age None / unfitted band) equal the incumbent,
#  (4) patched efv_score.py byte-compiles and diffs only at the one call site.
from __future__ import annotations

import importlib.util
import json
import py_compile
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
SANDBOX = HERE / "verify_sandbox"

sys.path.insert(0, str(REPO))
import value_framework as vf_prod  # noqa: E402
import gate_lab as gl  # noqa: E402

# --- sandbox assembly (patched module + the config/data it reads) -----------
SANDBOX.mkdir(exist_ok=True)
(SANDBOX / "data").mkdir(exist_ok=True)
shutil.copy(HERE / "patched" / "value_framework.py", SANDBOX / "value_framework.py")
shutil.copy(REPO / "value_framework_config.yaml", SANDBOX / "value_framework_config.yaml")
for f in ("value_framework_fitted.json", "fa_dpw_series.json"):
    if (REPO / "data" / f).exists():
        shutil.copy(REPO / "data" / f, SANDBOX / "data" / f)
shutil.copy(REPO / "valuation_sets.py", SANDBOX / "valuation_sets.py")
for extra in (REPO / "data" / "valuation_sets.json",):
    if extra.exists():
        shutil.copy(extra, SANDBOX / "data" / extra.name)
shutil.copy(HERE / "patched" / "data" / "xfv_bucket_age_head.json",
            SANDBOX / "data" / "xfv_bucket_age_head.json")

sys.path.insert(0, str(SANDBOX))
spec = importlib.util.spec_from_file_location("vf_patched", SANDBOX / "value_framework.py")
vf_p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vf_p)

fvs = [x / 4.0 for x in range(80, 321)]          # 20.0 .. 80.0 step 0.25
ages = [19.0, 21.0, 22.99, 23.0, 23.9, 24.99, 25.0, 26.9, 31.0]

# (1) incumbent identical
worst = 0.0
for fv in fvs:
    for pit in (True, False):
        a = vf_prod.p_bucket_given_fv(fv, pit)
        b = vf_p.p_bucket_given_fv(fv, pit)
        worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
print("(1) incumbent max abs diff prod vs patched:", worst)
assert worst == 0.0, "incumbent p_bucket_given_fv output changed!"

# (2) head parity vs the lab
pool = gl.load_pool()
cells = gl.fit_head(pool)
worst2 = 0.0
for fv in fvs:
    for age in ages:
        lab = gl.head_prob(cells, fv, age)
        mod = vf_p.p_bucket_given_fv_age(fv, True, age=age)
        worst2 = max(worst2, max(abs(float(x) - float(y)) for x, y in zip(lab, mod)))
print("(2) head max abs diff lab vs patched module:", worst2)
assert worst2 < 1e-12, "patched head does not reproduce the lab head"

# (3) fallbacks equal incumbent
ok = True
for fv in (25.0, 45.0, 57.5):
    ok &= vf_p.p_bucket_given_fv_age(fv, False, age=26.9) == vf_p.p_bucket_given_fv(fv, False)
    ok &= vf_p.p_bucket_given_fv_age(fv, True, age=None) == vf_p.p_bucket_given_fv(fv, True)
ok &= vf_p.p_bucket_given_fv_age(22.0, True, age=26.9) == vf_p.p_bucket_given_fv(22.0, True)  # no fv20 cell
ok &= vf_p.p_bucket_given_fv_age(None, True, age=26.9) is None
print("(3) fallback identity checks:", "OK" if ok else "FAILED")
assert ok

# Moore spot value through the patched module
m = vf_p.p_bucket_given_fv_age(45.8, True, age=26.9)
print("(2b) patched Moore p_bust @(45.8, 26.9):", round(m[0], 3))

# (4) efv_score compiles; diff surface
py_compile.compile(str(HERE / "patched" / "efv_score.py"), doraise=True)
orig = (REPO / "efv_score.py").read_text(encoding="utf-8").splitlines()
patt = (HERE / "patched" / "efv_score.py").read_text(encoding="utf-8").splitlines()
import difflib
changed = [l for l in difflib.unified_diff(orig, patt, lineterm="", n=0)
           if l[:1] in "+-" and l[:3] not in ("+++", "---")]
print("(4) efv_score.py compiles; changed lines:", len(changed))
for l in changed:
    print("   ", l)
print("\nALL PATCH VERIFICATIONS PASSED")
