# Scratch: SERVED-LEVEL before/after for the projections-lane ships.
# Re-runs the live serve path (fm.contract_war_path with the shipped bundle)
# over the committed vet universe under four configurations. Writes nothing.
from __future__ import annotations
import json, os, random, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fa_market as fm
import fa_projection as fp
import proj_ml
import proj_export as pe

pay = json.loads((ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
vets = pay["vets"]
FS, H = pe.FIRST_SEASON, pe.HORIZON
corpus = fp.build_corpus()
league = corpus["league"]
curves, war_map = fp.fitted_models(corpus, FS - 1)
in_prog = (FS - 1, fp.season_fraction(league, FS - 1))
print("season_fraction(%d) = %.4f  (committed payload was built at 0.4839)"
      % (FS - 1, in_prog[1]))

by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
for side in ("hit", "pit"):
    for r in corpus[side]:
        if r.get("mlbam") and r["season"] >= FS - 3:
            by_player[side][r["mlbam"]][r["season"]] = r

ids = [v["mlbam"] for v in vets if v.get("mlbam")]
random.Random(7).shuffle(ids)
ids = ids[:400]
models = proj_ml.load()
mb = dict(models["meta"].get("mean_blend") or {})


def run(ipage: bool, meanblend: bool):
    prev = os.environ.get("EEPHUS_PIT_IP_AGE")
    os.environ["EEPHUS_PIT_IP_AGE"] = "1" if ipage else "0"
    models["meta"]["mean_blend"] = mb if meanblend else None
    proj_ml._LOADED = models
    y1 = y1c = tot = 0.0
    n = 0
    try:
        for m in ids:
            for side in ("hit", "pit"):
                seasons = by_player[side].get(m) or {}
                hist = [seasons[t] for t in (FS - 1, FS - 2, FS - 3) if t in seasons]
                if not hist:
                    continue
                ar = next((h for h in hist if h.get("age")), None)
                age = (ar["age"] + (FS - ar["season"])) if ar else None
                cp = fm.contract_war_path(hist, side, FS, H, age, curves, war_map,
                                          league, in_progress=in_prog, ml_models=models)
                if cp is None:
                    continue
                n += 1
                y1 += cp["war_by_year"][0]
                y1c += (cp.get("war_by_year_champ") or cp["war_by_year"])[0]
                tot += sum(cp["war_by_year"][:H])
    finally:
        if prev is None:
            os.environ.pop("EEPHUS_PIT_IP_AGE", None)
        else:
            os.environ["EEPHUS_PIT_IP_AGE"] = prev
        models["meta"]["mean_blend"] = mb
    return n, y1, y1c, tot


print(f"{'config':<34} {'n':>5} {'y1 served':>10} {'y1 champ':>9} {'5y served':>10}")
for lbl, a, b in (("PRE  (ipage off, blend inert)", False, False),
                  ("+ P-IPAGE only", True, False),
                  ("+ P-MBLEND only", False, True),
                  ("POST (both, as shipped)", True, True)):
    n, y1, y1c, tot = run(a, b)
    print(f"{lbl:<34} {n:>5} {y1:>10.1f} {y1c:>9.1f} {tot:>10.1f}")
print("\ncommitted payload (all 1270 vets): y1 war 602.8, y1 warChamp 984.4")
