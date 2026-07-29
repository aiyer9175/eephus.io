# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Resolve mlbam ids for the never-MLB "bust" pool (data/inactive.json).

Busts never debuted, so there is no mlbDebutDate to validate on. Instead we
validate strictly on NAME + BIRTHDATE and require the candidate to have NO
mlbDebutDate (a bust never reached MLB).

Validator (strict, to keep match error near zero):
  For each inactive rec with player_name + birth_date and no mlbam_id, query
    https://statsapi.mlb.com/api/v1/people/search?names=<urlencoded name>
  Each candidate returns id, fullName, birthDate, mlbDebutDate. BIND only if
  EXACTLY ONE candidate has birthDate == the rec's birth_date AND that
  candidate's mlbDebutDate is null/empty. If multiple candidates share the
  birthDate (ambiguous) or the lone birthDate match already carries an
  mlbDebutDate (they debuted -> not a bust), do NOT bind.

Cohort: acquisition.year in [2011, 2020] (debut_date is null for every bust,
so acquisition year is the old-cohort analog of the debuted resolver's
debut_year). Recs missing birth_date are skipped (name-only is too noisy for
obscure busts).

Writes data/sources/mlbam_id_overrides_busts.json = {player_key: mlbam}.
Lands a data asset only; does not touch inactive.json / debuts.json / the model.
"""
import json, time, sys, urllib.parse, urllib.request, unicodedata
from pathlib import Path

DATA = Path("data")
OUT = DATA / "sources" / "mlbam_id_overrides_busts.json"
UA = {"User-Agent": "eephus-io-datasourcing/1.0 (bust-id-resolver)"}
SEARCH = "https://statsapi.mlb.com/api/v1/people/search?names="
YEAR_LO, YEAR_HI = 2011, 2020


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def acq_year(rec):
    return (rec.get("acquisition") or {}).get("year")


inactive = json.loads((DATA / "inactive.json").read_text(encoding="utf-8"))

targets, skipped_no_bd = [], 0
for rec in inactive:
    name = rec.get("player_name")
    mlbam = rec.get("mlbam_id")
    bd = rec.get("birth_date")
    ay = acq_year(rec)
    if not name or mlbam or ay is None or not (YEAR_LO <= ay <= YEAR_HI):
        continue
    if not bd:                       # skip name-only: too noisy for obscure busts
        skipped_no_bd += 1
        continue
    targets.append((rec.get("player_key"), name, ay, bd))

print(f"bust targets (acq {YEAR_LO}-{YEAR_HI}, name+birth_date, no mlbam): {len(targets)}",
      flush=True)
print(f"skipped (in range, no birth_date): {skipped_no_bd}", flush=True)

cache_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/bust_id_resolve_cache.json")
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

overrides = {}
ambiguous, debuted_skip, failed = [], [], []
for i, (pk, name, ay, bd) in enumerate(targets):
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
    if isinstance(res, dict):        # transport error
        failed.append((pk, name, res.get("error")))
        continue
    bd_match = [c for c in res if c.get("birth") == bd]
    if len(bd_match) == 1:
        c = bd_match[0]
        if not c.get("debut"):       # exactly one birthdate match, never debuted -> BIND
            overrides[pk] = c["id"]
        else:                        # matched a player who DID debut -> not our bust, skip
            debuted_skip.append((pk, name, bd, c["id"], c["debut"]))
    elif len(bd_match) > 1:          # several candidates share the birthdate -> ambiguous
        ambiguous.append((pk, name, bd, [(c["id"], c["debut"]) for c in bd_match]))
    else:                            # zero birthdate matches among candidates
        failed.append((pk, name, f"{len(res)} cands, none birthDate=={bd}"))

cache_path.write_text(json.dumps(cache))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(overrides, indent=0))

n = len(targets)
rate = (len(overrides) / n * 100) if n else 0.0
print(f"\nRESOLVED: {len(overrides)}  AMBIGUOUS: {len(ambiguous)}  "
      f"DEBUTED-SKIP: {len(debuted_skip)}  FAILED: {len(failed)}")
print(f"match rate: {len(overrides)}/{n} = {rate:.1f}%")
print(f"wrote {OUT}")
print("\nsample resolved:", dict(list(overrides.items())[:6]))
print("\nambiguous (first 8):")
for a in ambiguous[:8]:
    print("  ", a)
print("\ndebuted-skip (first 8):")
for a in debuted_skip[:8]:
    print("  ", a)
print("\nfailed (first 10):")
for a in failed[:10]:
    print("  ", a)
