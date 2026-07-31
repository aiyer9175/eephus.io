"""VERIFY lane: independently re-derive the survivorship scoping question.
Read-only. Writes only to tools/_gn_verify_out/.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
OUT = ROOT / "tools" / "_gn_verify_out"
OUT.mkdir(exist_ok=True)


def keys_of(obj):
    if isinstance(obj, list):
        recs = obj
    else:
        recs = obj.get("players") or []
    return recs


ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
deb = json.loads((DATA / "debuts.json").read_text(encoding="utf-8"))
ina = json.loads((DATA / "inactive.json").read_text(encoding="utf-8"))

ts_r, deb_r, ina_r = keys_of(ts), keys_of(deb), keys_of(ina)
K = lambda rs: {r.get("player_key") for r in rs if r.get("player_key")}
kts, kdeb, kina = K(ts_r), K(deb_r), K(ina_r)

res = {}
res["counts"] = {"ts": len(ts_r), "deb": len(deb_r), "ina": len(ina_r),
                 "ts_keys": len(kts), "deb_keys": len(kdeb), "ina_keys": len(kina)}
res["overlaps"] = {"ts&deb": len(kts & kdeb), "ts&ina": len(kts & kina),
                   "deb&ina": len(kdeb & kina), "union": len(kts | kdeb | kina)}

# debut_date presence in each slice
def dstats(rs, name):
    n_dd = sum(1 for r in rs if r.get("debut_date"))
    n_cw = sum(1 for r in rs if (r.get("career_war") or {}).get("career_war") is not None)
    return {"n": len(rs), "with_debut_date": n_dd, "with_career_war": n_cw}
res["debut_flags"] = {"ts": dstats(ts_r, "ts"), "deb": dstats(deb_r, "deb"),
                      "ina": dstats(ina_r, "ina")}

# eFV matrices provenance
prov = {}
for side, p in (("hit", DATA / "xfv_hitter_matrix.json"), ("pit", DATA / "xfv_pitcher_matrix.json")):
    rows = json.loads(p.read_text(encoding="utf-8"))
    kinds = {}
    for r in rows:
        kinds[r.get("kind")] = kinds.get(r.get("kind"), 0) + 1
    bust_keys = {r["player_key"] for r in rows if r.get("kind") == "bust"}
    deb_keys = {r["player_key"] for r in rows if r.get("kind") == "debuted"}
    prov[side] = {
        "n_rows": len(rows), "kinds": kinds,
        "bust_in_inactive": len(bust_keys & kina),
        "bust_in_ts": len(bust_keys & kts),
        "bust_in_debuts": len(bust_keys & kdeb),
        "bust_orphan": len(bust_keys - kina - kts - kdeb),
        "debuted_in_debuts": len(deb_keys & kdeb),
        "debuted_in_ina": len(deb_keys & kina),
        "debuted_in_ts": len(deb_keys & kts),
        "bust_censored_nonzero": sum(1 for r in rows if r.get("kind") == "bust"
                                     and float(r.get("target_censored") or 0.0) != 0.0),
        "bust_recent": sum(1 for r in rows if r.get("kind") == "bust" and r.get("bust_recent")),
    }
prov["combined_bust_keys"] = len(
    {r["player_key"] for p in (DATA / "xfv_hitter_matrix.json", DATA / "xfv_pitcher_matrix.json")
     for r in json.loads(p.read_text(encoding="utf-8")) if r.get("kind") == "bust"})
res["efv_matrix_provenance"] = prov

(OUT / "scope_a.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
