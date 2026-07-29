"""PREMISE ATTACK: is the resolved-cohort stratum a valid outcome record?

Read-only. Reproduces the lead's item-1 stratum from the shipped matrix and
decomposes it by row provenance, anchor timing, and calendar era.
"""
import json, collections, statistics, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))

def milb(r):
    return r.get("milb") or {}

def in_stratum(r):
    m = milb(r)
    if not m:
        return False
    if m.get("level_rank") != 5.0:
        return False
    a = m.get("age")
    if a is None or a < 23.5:
        return False
    o = m.get("ops_rel")
    return o is not None and o < 0

def resolved(r):
    return not r.get("censored")

S = [r for r in rows if in_stratum(r) and resolved(r)]
ALL = [r for r in rows if in_stratum(r)]
print("stratum resolved n=%d  (all incl censored n=%d)" % (len(S), len(ALL)))

tgt = [r["target_resolved"] for r in S]
print("mean %.4f  median %.4f" % (statistics.mean(tgt), statistics.median(tgt)))
bust_evt = sum(1 for t in tgt if t < 0.5) / len(tgt)
bust_avg = sum(1 for t in tgt if t < 3.0) / len(tgt)
print("frac target<0.5 (lead's event) %.4f   frac target<3.0 (shipped bust band) %.4f"
      % (bust_evt, bust_avg))

print()
print("=== provenance ===")
c = collections.Counter(r["kind"] for r in S)
print(dict(c))
for k in ("bust", "debuted"):
    sub = [r for r in S if r["kind"] == k]
    if not sub:
        continue
    t = [r["target_resolved"] for r in sub]
    print("  %-8s n=%3d  mean %.3f  median %.3f  min %.2f max %.2f  exactly0: %d"
          % (k, len(sub), statistics.mean(t), statistics.median(t), min(t), max(t),
             sum(1 for x in t if x == 0.0)))

print()
print("=== ANCHOR YEAR (cutoff) x kind ===")
tab = collections.defaultdict(collections.Counter)
for r in S:
    y = (r.get("cutoff") or "????")[:4]
    tab[y][r["kind"]] += 1
for y in sorted(tab):
    print("  %s  bust %2d  debuted %2d" % (y, tab[y]["bust"], tab[y]["debuted"]))

print()
print("=== WINDOW ELAPSE CHECK ===")
RESOLVED_THROUGH = None
import efv_dataset as ed
RESOLVED_THROUGH = ed.RESOLVED_THROUGH
print("RESOLVED_THROUGH =", RESOLVED_THROUGH, " TARGET_SEASONS =", ed.TARGET_SEASONS)
# For busts the "window" is fictional: label is hardcoded 0.0 with observed_seasons=6.
# Define the earliest year the player could plausibly have debuted = anchor year,
# and ask whether anchor+5 <= RESOLVED_THROUGH.
n_unelapsed = 0
for r in S:
    if r["kind"] != "bust":
        continue
    y = (r.get("cutoff") or "")[:4]
    if y.isdigit() and int(y) + ed.TARGET_SEASONS - 1 > RESOLVED_THROUGH:
        n_unelapsed += 1
print("bust rows whose anchor+5 has NOT elapsed: %d of %d busts"
      % (n_unelapsed, sum(1 for r in S if r["kind"] == "bust")))

print()
print("=== the same stratum restricted to GENUINELY ELAPSED rows only ===")
def elapsed(r):
    if r["kind"] == "debuted":
        return (r.get("debut_year") or 9999) + ed.TARGET_SEASONS - 1 <= RESOLVED_THROUGH
    y = (r.get("cutoff") or "")[:4]
    return y.isdigit() and int(y) + ed.TARGET_SEASONS - 1 <= RESOLVED_THROUGH
E = [r for r in S if elapsed(r)]
if E:
    t = [r["target_resolved"] for r in E]
    print("n=%d  mean %.4f  median %.4f  frac<0.5 %.4f  frac<3.0 %.4f  kinds %s"
          % (len(E), statistics.mean(t), statistics.median(t),
             sum(1 for x in t if x < 0.5) / len(t),
             sum(1 for x in t if x < 3.0) / len(t),
             dict(collections.Counter(r["kind"] for r in E))))

print()
print("=== BUST RETENTION inside the stratum's own selection ===")
# A stratum row requires a MiLB block. How many hitter busts/debuts overall have one?
for k in ("bust", "debuted"):
    sub = [r for r in rows if r["kind"] == k]
    have = sum(1 for r in sub if r.get("milb"))
    print("  %-8s total %4d  with milb block %4d  (%.3f)" % (k, len(sub), have, have / len(sub)))
    aaa = sum(1 for r in sub if (r.get("milb") or {}).get("level_rank") == 5.0)
    print("           reached AAA in the block: %4d (%.3f of those with a block)"
          % (aaa, aaa / max(1, have)))
