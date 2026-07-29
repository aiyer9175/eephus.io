# scratch: hyperparameter sweep for roleconditioned.py, scored ONLY on early/mid (no test)
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import efv_pitcher_label_harness as H  # noqa: E402
from prospect_path import _spearman  # noqa: E402
import roleconditioned as RC  # noqa: E402

SPAN = int(sys.argv[1]) if len(sys.argv) > 1 else 3

pool = H.build_pool("pit")
early = [r for r in pool if H.EARLY[0] <= r["dy"] <= H.EARLY[1]]
mid = [r for r in pool if H.MID[0] <= r["dy"] <= H.MID[1]]
tm = [r["true6"] for r in mid]
order = sorted(range(len(mid)), key=lambda i: -tm[i])
topq = order[:len(mid) // 4]
topd = set(order[:len(mid) // 10])


def score(labels, tag):
    rq = _spearman([labels[i] for i in topq], [tm[i] for i in topq])
    pred_top = set(sorted(range(len(mid)), key=lambda i: -labels[i])[:len(topd)])
    rec = len(pred_top & topd) / len(topd)
    mae = sum(abs(labels[i] - tm[i]) for i in range(len(mid))) / len(mid)
    print(f"  {tag:34} rho_all {_spearman(labels, tm):.4f} rho_topQ {rq:.4f} "
          f"topD {rec:.2f} mae {mae:.3f}")


print(f"span={SPAN} early={len(early)} mid={len(mid)} topQ={len(topq)} topD={len(topd)}")
print("KM reference:")
score([H.km_label(r, SPAN) for r in mid], "A_KM")

for alpha in (2.0, 4.0, 8.0, 16.0, 32.0, 64.0):
    RC.RIDGE_A = alpha
    for g0 in (4.0, 10.0, 25.0):
        RC.G0 = g0
        for kb in (30.0, 60.0, 120.0):
            RC.K_BUCKET = kb
            st = RC.fit(early, spans=(SPAN,))
            lab = [RC.predict(st, r, SPAN, "R3") for r in mid]
            score(lab, f"R3 a={alpha:g} G0={g0:g} K={kb:g}")
