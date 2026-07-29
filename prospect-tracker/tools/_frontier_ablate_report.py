# SCRATCH: decision table for the ablation audit.
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from _frontier_ablate import OUT

boot = json.load(open(OUT / "_ablate_boot.json"))
perm = json.load(open(OUT / "_ablate_perm.json"))
stab = json.load(open(OUT / "_ablate_stab.json"))
nullb = json.load(open(OUT / "_ablate_null.json"))
GS = {"hit": {"G_production": 4, "G_contact": 2, "G_onbase": 2, "G_tools": 2, "G_age": 2,
              "G_cohort": 3, "G_track": 2, "G_all_but_fv": 13},
      "pit": {"G_production": 4, "G_k": 2, "G_age": 2, "G_all_but_fv": 7}}


def band(side, k):
    ks = sorted(int(x[1:]) for x in nullb[side] if x.startswith("k"))
    kk = min(ks, key=lambda a: abs(a - k))
    return nullb[side]["k%d" % kk]


for s in ("hit", "pit"):
    S = boot[s]
    base = np.array([v[0] for v in S["base"]])          # side block-rho, rep0 = point
    basep = np.array([v[1] for v in S["base"]])         # pooled block-rho
    noise = [n for n in S if n.startswith("noise:")]
    nb = np.array([[base[i] - S[n][i][0] for i in range(len(base))] for n in noise])
    print("=" * 108)
    print("SIDE %s  base block-rho (side) point %.4f  boot sd %.4f | pooled-both-sides point %.4f"
          % (s, base[0], base[1:].std(ddof=1), basep[0]))
    print("  noise-arm (1 zero-info column) paired-boot: sd of delta %.5f | point deltas across 20 "
          "draws: sd %.5f max|%.4f|" % (nb[:, 1:].std(ddof=1), nb[:, 0].std(ddof=1),
                                        np.abs(nb[:, 0]).max()))
    rows = []
    for n in S:
        if n.startswith("noise:") or n == "base":
            continue
        d = np.array([base[i] - S[n][i][0] for i in range(len(base))])
        pt, bs = d[0], d[1:]
        k = 1
        if n.startswith("dropG:") or n.startswith("min:"):
            k = GS[s].get(n.split(":")[1], 1)
            if n.startswith("min:"):
                k = len(perm[s]["tests"]) and 1
        key = n.split(":")[1]
        pm = perm[s]["tests"].get(key)
        pmb = perm[s]["tests"].get("BLOCK:" + key)
        rows.append((pt, n, bs.mean(), bs.std(ddof=1), np.percentile(bs, 2.5),
                     np.percentile(bs, 97.5), float((bs > 0).mean()),
                     (pm or pmb or {}).get("p"), (pm or pmb or {}).get("effect")))
    rows.sort(reverse=True)
    print("  %-24s %8s %8s %8s %19s %6s %7s %8s" %
          ("arm (delta = base - arm; +ve => the feature HELPS)", "point", "bootMu", "bootSD",
           "CI95", "P(>0)", "permP", "permEff"))
    for pt, n, mu, sd, lo, hi, p, pp, pe in rows:
        print("  %-24s %+8.4f %+8.4f %8.4f [%+.4f,%+.4f] %6.3f %7s %8s" %
              (n, pt, mu, sd, lo, hi, p,
               ("%.3f" % pp) if pp is not None else "-",
               ("%+.4f" % pe) if pe is not None else "-"))
    print("  zero-information null band (add k fresh N(0,1) cols, 200 draws):")
    for kk in sorted(int(x[1:]) for x in nullb[s] if x.startswith("k")):
        b = nullb[s]["k%d" % kk]
        print("     k=%-3d mean %+.4f sd %.4f p95|%.4f| max|%.4f|"
              % (kk, b["mean"], b["sd"], b["p95_abs"], b["max_abs"]))
