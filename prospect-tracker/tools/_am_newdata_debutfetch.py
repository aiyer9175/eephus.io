"""LANE newdata: fetch authoritative mlbDebutDate for every mlbam id in
data/draft_bonus_slot.json (and any extra ids passed in), batched through the
StatsAPI /people endpoint, cached to the scratchpad. Read-only; touches no
repo data file.
"""
import sys, os, json, io, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
OUT = os.path.join(SCRATCH, "nd_people.json")
BATCH = 200


def load_cache():
    if os.path.exists(OUT):
        return json.load(io.open(OUT, encoding="utf-8"))
    return {}


def main():
    db = json.load(io.open(os.path.join(ROOT, "data", "draft_bonus_slot.json"),
                           encoding="utf-8"))
    ids = sorted({int(k) for k in db})
    cache = load_cache()
    todo = [i for i in ids if str(i) not in cache]
    print(f"ids {len(ids)}  cached {len(cache)}  to fetch {len(todo)}")
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        url = ("https://statsapi.mlb.com/api/v1/people?personIds="
               + ",".join(str(x) for x in chunk))
        req = urllib.request.Request(url, headers={"User-Agent": "eephus-io/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                d = json.loads(fh.read().decode("utf-8"))
        except Exception as e:                                   # noqa: BLE001
            print("  batch fail", k, e)
            time.sleep(2)
            continue
        for p in d.get("people", []):
            cache[str(p["id"])] = {
                "debut": p.get("mlbDebutDate"),
                "pos": (p.get("primaryPosition") or {}).get("abbreviation"),
                "birth": p.get("birthDate"),
                "height": p.get("height"),
                "weight": p.get("weight"),
                "bats": (p.get("batSide") or {}).get("code"),
                "throws": (p.get("pitchHand") or {}).get("code"),
            }
        print(f"  fetched {k + len(chunk)}/{len(todo)}  total {len(cache)}")
        time.sleep(0.3)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    got = sum(1 for v in cache.values() if v.get("debut"))
    print(f"WROTE {OUT}  n={len(cache)}  with debut {got}")


if __name__ == "__main__":
    main()
