"""Lane: prospect. (b) C2/C6: the Trade Machine Grade column orders by a
quantity it does not display, and it is a DIFFERENT eFV grade than the one
PROSPX shows for the same player."""
import json, statistics
from pathlib import Path
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

xfv = L("xfv.json")["by_player"]
tv = L("trade_values.json")["players"]

# --- how far apart are the two eFV grades that the two surfaces show? -------
pairs = [(k, x["xfv_grade_quantile"], x["xfv_grade_model_raw"])
         for k, x in xfv.items()
         if x.get("xfv_grade_quantile") is not None
         and x.get("xfv_grade_model_raw") is not None]
q = [a for _, a, _ in pairs]; r = [b for _, _, b in pairs]
print("n =", len(pairs))
print("Spearman(quantile grade, raw grade) =", round(spearmanr(q, r).correlation, 6))
d = [abs(a - b) for _, a, b in pairs]
print("mean|diff| =", round(statistics.mean(d), 3), " p95 =", round(sorted(d)[int(.95*len(d))], 2),
      " max =", round(max(d), 2))
print("pct with |diff| >= 5 grade pts:", round(100*sum(1 for v in d if v >= 5)/len(d), 1))

# --- the served Grade COLUMN: letter from trade_value_mm, sort key xfv_grade --
def letter(mm):
    # mirror assets/trademachine.js _tbGrade thresholds
    return mm
rows = [p for p in tv if p.get("xfv_grade") is not None and p.get("trade_value_mm") is not None]
rows.sort(key=lambda p: (-p["xfv_grade"], -p["trade_value_mm"]))
inv = sum(1 for a, b in zip(rows, rows[1:]) if b["trade_value_mm"] > a["trade_value_mm"] + 1e-9)
print("\nGrade-column sort (desc by xfv_grade): n =", len(rows),
      "adjacent pairs where the DISPLAYED $ (and hence letter) INCREASES going down:",
      inv, f"({round(100*inv/(len(rows)-1),1)}%)")
worst = sorted(zip(rows, rows[1:]), key=lambda ab: ab[0]["trade_value_mm"] - ab[1]["trade_value_mm"])[:8]
for a, b in worst:
    print(f"   row {a['player_name']:22s} eFVraw {a['xfv_grade']:5.1f} ${a['trade_value_mm']:7.1f}M"
          f"   ABOVE   {b['player_name']:22s} eFVraw {b['xfv_grade']:5.1f} ${b['trade_value_mm']:7.1f}M")

# --- board grade vs prospx grade, worst offenders ---------------------------
j = [(p["player_name"], p["player_key"], p["xfv_grade"],
      xfv[p["player_key"]]["xfv_grade_quantile"])
     for p in tv if p.get("xfv_grade") is not None and p["player_key"] in xfv
     and xfv[p["player_key"]].get("xfv_grade_quantile") is not None]
j.sort(key=lambda t: -abs(t[2] - t[3]))
print("\nlargest board-vs-prospx eFV grade disagreements (same player, same day):")
for nm, k, b, qq in j[:12]:
    print(f"   {nm:26s} trade board {b:5.1f}   prospx {qq:5.1f}   delta {b-qq:+.1f}")
