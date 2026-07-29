"""Resolve mlbam ids for old (2011-2018) debuted eFV rows that lack them.
Validator: /people/search by name -> require candidate mlbDebutDate YEAR == row
debut_year (day is often a placeholder); birthDate exact match breaks collisions.
Near-zero error rate for DEBUTED players (they provably reached MLB).
Writes data/mlbam_id_overrides.json = {player_key: mlbam}.
"""
import json, time, sys, urllib.parse, urllib.request, unicodedata
from pathlib import Path

DATA = Path("data")
UA = {"User-Agent": "eephus-io-datasourcing/1.0"}
SEARCH = "https://statsapi.mlb.com/api/v1/people/search?names="

def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("'", "").split())

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())

debuts = json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))

targets = []
for rec in debuts:
    dd = rec.get("debut_date"); mlbam = rec.get("mlbam_id")
    name = rec.get("player_name")
    if not dd or mlbam or not name: continue
    dy = int(dd[:4])
    if 2011 <= dy <= 2018:
        targets.append((rec.get("player_key"), name, dy, rec.get("birth_date")))

print(f"debuted 2011-2018 no-mlbam targets: {len(targets)}", flush=True)

cache_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/id_resolve_cache.json")
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

overrides, ambiguous, failed = {}, [], []
for i, (pk, name, dy, bd) in enumerate(targets):
    if pk in cache:
        res = cache[pk]
    else:
        try:
            d = fetch(SEARCH + urllib.parse.quote(name))
            res = [{"id": p.get("id"), "name": p.get("fullName"),
                    "debut": p.get("mlbDebutDate"), "birth": p.get("birthDate")}
                   for p in (d.get("people") or [])]
        except Exception as e:
            res = {"error": str(e)}
        cache[pk] = res
        time.sleep(0.25)
        if i % 25 == 0:
            cache_path.write_text(json.dumps(cache))
            print(f"  {i}/{len(targets)}", flush=True)
    if isinstance(res, dict):  # error
        failed.append((pk, name, res.get("error"))); continue
    # candidates that reached MLB in the right year
    yr_match = [c for c in res if (c.get("debut") or "")[:4] == str(dy)]
    # birthDate exact match (strongest)
    if bd:
        bd_match = [c for c in res if c.get("birth") == bd and c.get("debut")]
        if len(bd_match) == 1:
            overrides[pk] = bd_match[0]["id"]; continue
    if len(yr_match) == 1:
        overrides[pk] = yr_match[0]["id"]; continue
    if len(res) == 1 and res[0].get("debut") and res[0]["debut"][:4] == str(dy):
        overrides[pk] = res[0]["id"]; continue
    if yr_match:
        ambiguous.append((pk, name, dy, [(c["id"], c["debut"], c["birth"]) for c in yr_match]))
    else:
        failed.append((pk, name, f"{len(res)} cands, none debut-year {dy}"))

cache_path.write_text(json.dumps(cache))
(DATA / "mlbam_id_overrides.json").write_text(json.dumps(overrides, indent=0))
print(f"\nRESOLVED: {len(overrides)}  AMBIGUOUS: {len(ambiguous)}  FAILED: {len(failed)}")
print("sample resolved:", dict(list(overrides.items())[:6]))
print("\nambiguous (first 8):")
for a in ambiguous[:8]: print("  ", a)
print("\nfailed (first 10):")
for f in failed[:10]: print("  ", f)
