"""Lane: prospect. (c) NEVER-SUM-ML-QUANTILE-POINTS audit, served-payload evidence."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))

mp = L("mlb_projections.json")
vets = mp["vets"]; pros = mp["prospects"]

print("=== /projections/ VET rows: is warTotalP10 the sum of the per-year P10 array? ===")
hit = 0; tot = 0; mism = 0
for v in vets:
    if v.get("warP10") and v.get("warTotalP10") is not None:
        tot += 1
        s = round(sum(v["warP10"][:mp["horizon"]]), 1)
        if abs(s - v["warTotalP10"]) < 0.051:
            hit += 1
        else:
            mism += 1
print(f"  vets with a band: {tot}   warTotalP10 == sum(per-year P10): {hit}   other: {mism}")

print("\n=== /projections/ PROSPECT rows: warTotalP10 is a BUCKET PATH total, not a quantile sum ===")
ph = 0; pt = 0
for p in pros:
    if p.get("warP10") and p.get("warTotalP10") is not None:
        pt += 1
        # in-window sum of the SAME bucket path -> legitimate scenario total
        w = max(0, mp["horizon"] - (p["eta"] - mp["first_season"]))
        if abs(round(sum(p["warP10"][:w]), 1) - p["warTotalP10"]) < 0.051:
            ph += 1
print(f"  prospects with a band: {pt}  totals that are in-window sums of ONE bucket path: {ph}")
print("  -> the prospect P10/P90 are whole scenario paths (paths[lo_b]/paths[hi_b]),")
print("     comonotone by construction, so summing them is NOT a quantile-point sum.")

# --- FA copula comparison for the same MLB players -------------------------
try:
    fa = L("fa_class.json")
except Exception:
    fa = None
print("\n=== /fa/ same-player comparison (copula total vs comonotone quantile sum) ===")
if fa:
    def walk(o, out):
        if isinstance(o, dict):
            if "warTotalP10" in o or "warTotalP10Comon" in o:
                out.append(o)
            for v in o.values():
                walk(v, out)
        elif isinstance(o, list):
            for v in o:
                walk(v, out)
    rows = []
    walk(fa, rows)
    both = [r for r in rows if r.get("warTotalP10") is not None
            and r.get("warTotalP10Comon") is not None]
    print(f"  fa rows carrying both totals: {len(both)} of {len(rows)}")
    if both:
        import statistics
        wid_c = [r["warTotalP90"] - r["warTotalP10"] for r in both
                 if r.get("warTotalP90") is not None]
        wid_s = [r["warTotalP90Comon"] - r["warTotalP10Comon"] for r in both
                 if r.get("warTotalP90Comon") is not None]
        print(f"  median copula band width  = {statistics.median(wid_c):.2f} WAR")
        print(f"  median summed band width  = {statistics.median(wid_s):.2f} WAR")
        print(f"  the summed band is {statistics.median(wid_s)/statistics.median(wid_c):.2f}x wider")
        names = {}
        for r in both:
            names[r.get("name") or r.get("player_name") or r.get("key")] = r
        keyset = {v.get("key") or v.get("name") for v in vets}
        ov = [nm for nm in names if nm in keyset]
        print(f"  FA names that also appear as /projections/ vets: {len(ov)}")
        for nm in list(ov)[:6]:
            r = names[nm]
            vv = next((v for v in vets if (v.get("key") or v.get("name")) == nm), None)
            if vv and vv.get("warTotalP10") is not None:
                print(f"    {str(nm)[:24]:24s} /fa/ band [{r['warTotalP10']},{r['warTotalP90']}]"
                      f"  /projections/ band [{vv['warTotalP10']},{vv['warTotalP90']}]")
