"""Lane: prospect. (b) ETA coherence across surfaces + remaining reproductions."""
import json, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
import eta

print("=" * 80)
print("E-COH  is the shipped LEVEL_BIAS_ADJ applied on every surface that shows an ETA?")
print("=" * 80)
print("  eta.LEVEL_BIAS_ADJ =", getattr(eta, "LEVEL_BIAS_ADJ", "ABSENT"))
import inspect
src = inspect.getsource(eta)
print("  estimate_eta signature:", str(inspect.signature(eta.estimate_eta)))
callers = {}
for mod in ("storage.py", "proj_export.py", "bayes_trade_value.py", "eta_backtest.py",
            "efv_export.py", "build_site.py", "farm_grade_backtest.py"):
    p = ROOT / mod
    if not p.exists():
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    n_call = t.count("estimate_eta(")
    n_adj = t.count("level_bias_adj")
    if n_call:
        callers[mod] = (n_call, n_adj)
print("  callers of estimate_eta (calls, level_bias_adj mentions):")
for m, v in callers.items():
    print(f"     {m:28s} {v}")

print()
print("=" * 80)
print("E-COH2  /projections/ prospect eta vs the eta the same player carries elsewhere")
print("=" * 80)
mp = L("mlb_projections.json")
pr = {r["key"]: r for r in mp["prospects"]}
tv = {r["player_key"]: r for r in L("trade_values.json")["players"]}
print("  proj prospects with eta:", sum(1 for r in pr.values() if r.get("eta")))
print("  trade_values carries no eta field:", "eta" not in next(iter(tv.values())))
# remaining control years vs eta: a prospect's control window should START at eta
rc = [(k, pr[k]["eta"], (tv.get(k) or {}).get("remaining_control_years"))
      for k in pr if tv.get(k)]
rc = [r for r in rc if r[2] is not None]
print(f"  prospects with both eta and remaining_control_years: {len(rc)}")
if rc:
    vals = sorted({r[2] for r in rc})
    print("  distinct remaining_control_years values on prospects:", vals[:12])
    print("  -> the board prices every prospect on a single control length regardless of ETA"
          if len(vals) <= 2 else "  -> control length varies with ETA")

print()
print("=" * 80)
print("A-REPRO  advancement_pace QC + prospect_def_value")
print("=" * 80)
ape = L("advancement_pace_eval.json")
apd = L("advancement_pace.json")
print("  eval says n_scored_latest_asof =", ape.get("n_scored_latest_asof"),
      " distribution:", ape.get("distribution_ap_plus_display_latest"))
players = apd.get("players") if isinstance(apd, dict) else None
if isinstance(players, (list, dict)):
    vals = []
    it = players.values() if isinstance(players, dict) else players
    for r in it:
        v = r.get("ap_plus_display") or r.get("ap_plus") or r.get("ap_plus_latest")
        if v is not None:
            vals.append(float(v))
    print(f"  re-derived from the served payload: n={len(vals)} "
          f"mean={statistics.mean(vals):.2f} sd={statistics.pstdev(vals):.2f} "
          f"median={statistics.median(vals):.2f}" if vals else "  no ap_plus field found")
    if isinstance(players, dict):
        k0 = next(iter(players)); print("  payload sample:", k0, json.dumps(players[k0])[:300])
    elif players:
        print("  payload sample:", json.dumps(players[0])[:300])
else:
    print("  advancement_pace.json top keys:", list(apd.keys()) if isinstance(apd, dict) else type(apd))

dve = L("prospect_def_value_eval.json")
print("\n  prospect_def_value_eval keys:", list(dve.keys()))
print(json.dumps(dve, indent=1)[:1500])
