"""Scratch: fetch StatsAPI /people height+weight for every mlbam id in the eFV
FIT and SERVED pools, measure real coverage, and quantify the AS-OF drift against
the draft-time listing in draft_players. Read-only w.r.t. the repo; writes a cache
to the scratchpad only.
"""
from __future__ import annotations
import json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "tools" / "_arch_bio_cache.json")


def pools():
    out = {}
    for side, mp, lp in (("hit", "xfv_hitter_matrix.json", "xfv_live_hitter_matrix.json"),
                         ("pit", "xfv_pitcher_matrix.json", "xfv_live_pitcher_matrix.json")):
        rows = json.loads((DATA / mp).read_text(encoding="utf-8"))
        is_pit = side == "pit"
        fit = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
               and not (r.get("kind") == "bust" and r.get("bust_recent"))
               and r.get("target_censored") is not None
               and r.get("consensus_fv_raw") is not None]
        live = json.loads((DATA / lp).read_text(encoding="utf-8"))
        served = [r for r in live if r.get("milb") and r.get("consensus_fv_raw") is not None]
        out[side] = (fit, served)
    return out


def fetch(ids):
    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    todo = [i for i in ids if str(i) not in cache]
    print(f"ids={len(ids)} cached={len(ids)-len(todo)} todo={len(todo)}")
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        url = ("https://statsapi.mlb.com/api/v1/people?personIds="
               + ",".join(str(b) for b in batch))
        try:
            with urllib.request.urlopen(url, timeout=40) as fh:
                d = json.loads(fh.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print("  batch fail", i, e)
            continue
        got = {str(p["id"]): p for p in d.get("people", [])}
        for b in batch:
            p = got.get(str(b))
            cache[str(b)] = ({"h": p.get("height"), "w": p.get("weight"),
                              "pos": (p.get("primaryPosition") or {}).get("abbreviation"),
                              "bd": p.get("birthDate")} if p else None)
        print(f"  {i+len(batch)}/{len(todo)}")
        time.sleep(0.15)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def h_in(h):
    if not h:
        return None
    try:
        s = str(h).replace('"', "").replace("'", " ").split()
        return float(s[0]) * 12 + (float(s[1]) if len(s) > 1 else 0.0)
    except (ValueError, IndexError):
        return None


if __name__ == "__main__":
    P = pools()
    ids = set()
    for side, (fit, served) in P.items():
        for pool in (fit, served):
            for r in pool:
                if r.get("mlbam_id"):
                    ids.add(int(r["mlbam_id"]))
    cache = fetch(sorted(ids))
    print()
    for side, (fit, served) in P.items():
        for nm, pool in (("FIT", fit), ("SERVED", served)):
            n = len(pool)
            hw = 0
            for r in pool:
                c = cache.get(str(r.get("mlbam_id"))) if r.get("mlbam_id") else None
                if c and c.get("w") and h_in(c.get("h")):
                    hw += 1
            print(f"{side} {nm}: n={n} statsapi height+weight={hw} ({100*hw/n:.1f}%)")
