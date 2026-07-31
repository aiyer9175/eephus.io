"""Bradfield-specific: what the biometric lane would and would not do to him."""
import sys, json
import numpy as np
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\tools")
panel = json.load(open("tools/_arch_bio_panel.json"))
feat = json.load(open("tools/_arch_bio_feat.json"))
xf = json.load(open("data/xfv.json"))["by_player"]

hits = [k for k in panel if "bradfield" in k]
print("panel keys:", hits)
for k in hits:
    for o in panel[k]:
        print("  ", o["vintage"], "ht", o["h"], "wt", o["w"], "frame", o["frame"],
              "athl", o["athl"], "levers", o["levers"], o["slug"])
    if k in xf:
        v = xf[k]
        print("  SERVED:", {a: v.get(a) for a in
                            ("xfv_grade_quantile", "consensus_fv", "p_bust", "xfv_war_6yr")})

# where does he sit on the body axes among SERVED hitters with as-of bio?
served_bmi = []
for k, v in xf.items():
    if v.get("side") != "H":
        continue
    obs = panel.get(k)
    if not obs:
        continue
    h = next((o["h"] for o in reversed(obs) if o["h"]), None)
    w = next((o["w"] for o in reversed(obs) if o["w"]), None)
    if h and w:
        served_bmi.append((k, 703.0 * w / (h * h), h, w))
served_bmi.sort(key=lambda x: x[1])
print("\nserved hitters with ht+wt:", len(served_bmi))
for k, b, h, w in served_bmi:
    if "bradfield" in k:
        pct = 100.0 * [x[0] for x in served_bmi].index(k) / len(served_bmi)
        print("  Bradfield BMI %.2f (%d in, %d lb) = %.1fth percentile of the served hitter board"
              % (b, h, w, pct))
arr = np.array([x[1] for x in served_bmi])
print("  served hitter BMI: mean %.2f sd %.2f  terciles %.2f / %.2f"
      % (arr.mean(), arr.std(), np.quantile(arr, 1/3), np.quantile(arr, 2/3)))
