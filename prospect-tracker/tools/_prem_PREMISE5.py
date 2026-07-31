"""PREMISE ATTACK part 5: how often does the truncated label call a real
major-leaguer a bust? And does label truncation attenuate the premium-vs-WAR
correlation the lead used to declare the premium 'unearned'?"""
import json, collections, statistics, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import storage, efv_dataset as ed
rows = json.load(open(os.path.join(ROOT, "data", "xfv_hitter_matrix.json")))
cw = {}
with storage.connect() as con:
    for r in con.execute("SELECT player_key, payload_json FROM career_war"):
        try:
            p = json.loads(r["payload_json"])
        except Exception:
            continue
        s = p.get("seasons") or p
        d = {}
        for k, v in (s.items() if isinstance(s, dict) else []):
            try:
                d[int(k)] = float(v)
            except Exception:
                pass
        if d:
            cw[r["player_key"]] = d

RT = ed.RESOLVED_THROUGH
E = [r for r in rows if r["kind"] == "debuted" and r.get("debut_year")
     and r["debut_year"] + 5 <= RT and r["player_key"] in cw]
def psum(r, k):
    s = cw[r["player_key"]]
    dy = r["debut_year"]
    return sum(s.get(dy + i, 0.0) for i in range(k))

print("=== FALSE-BUST RATE OF THE TRUNCATED LABEL (n=%d elapsed hitter debuts) ===" % len(E))
print("%3s %10s %10s %12s %12s" % ("k", "P(bust_k)", "P(bust_6)", "P(bust_k|not6)", "P(not6|bust_k)"))
for k in (1, 2, 3, 4, 5, 6):
    for thr, lbl in ((0.5, "lead's summed<0.5"), (3.0, "shipped 6yr-avg<0.5 == summed<3.0")):
        pass
    for thr in (0.5, 3.0):
        bk = [psum(r, k) < thr for r in E]
        b6 = [psum(r, 6) < thr for r in E]
        pk = sum(bk) / len(E)
        p6 = sum(b6) / len(E)
        # of players the truncated label calls a bust, how many are NOT busts at 6 years
        fb = sum(1 for a, b in zip(bk, b6) if a and not b) / max(1, sum(bk))
        print("k=%d thr=%.1f  P(bust_k) %.3f  P(bust_6) %.3f  FALSE-BUST rate %.3f"
              % (k, thr, pk, p6, fb))

print()
print("=== how the lead's n=69 is composed by observed_seasons ===")
def m(r):
    return r.get("milb") or {}
S = [r for r in rows
     if m(r).get("level_rank") == 5.0 and (m(r).get("age") or 0) >= 23.5
     and (m(r).get("ops_rel") is not None and m(r)["ops_rel"] < 0)]
c = collections.Counter(r.get("observed_seasons") for r in S)
tot = len(S)
for k in sorted(c):
    print("  observed_seasons=%s : %2d rows (%.1f%%)" % (k, c[k], 100.0 * c[k] / tot))
eff = sum((r.get("observed_seasons") or 6) for r in S if r["kind"] == "debuted")
nd = sum(1 for r in S if r["kind"] == "debuted")
print("  mean observed seasons across the 62 debuted rows: %.2f of 6" % (eff / nd))

print()
print("=== ATTENUATION: label truncation vs premium-WAR correlation ===")
# Simulate: take the elapsed population, compute rank corr between the TRUE 6yr
# label and a k-truncated label. That is the ceiling on any correlation measured
# against a truncated label.
def spearman(a, b):
    def rk(v):
        idx = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(idx):
            j = i
            while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for t in range(i, j + 1):
                r[idx[t]] = avg
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    return num / (da * db) if da and db else 0.0
t6 = [psum(r, 6) for r in E]
for k in (1, 2, 3, 4, 5):
    tk = [psum(r, k) for r in E]
    print("  rank corr(truncated k=%d label, TRUE 6yr label) = %.4f"
          "   -> any correlation measured against the k=%d label is attenuated by this factor"
          % (k, spearman(tk, t6), k))
