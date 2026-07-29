# scratch lab: intlalias step 4 -- exact affected population + board movement.
import sys, sqlite3, json, collections
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import grade_normalization as gn
DB = HERE / "prospects.db"
con = sqlite3.connect(str(DB)); cur = con.cursor()

# latest row per (player, source) across ALL history -- what forward-fill sees
rows = cur.execute("""SELECT player_key, player_name, source, snapshot_date, position, fv, org, status
                      FROM snapshots WHERE fv IS NOT NULL""").fetchall()
latest = {}
for pk, nm, src, dt, pos, fv, org, st in rows:
    k = (pk, src)
    if k not in latest or dt > latest[k][0]:
        latest[k] = (dt, nm, pos, fv, org, st)

bypk = collections.defaultdict(dict)
for (pk, src), v in latest.items():
    bypk[pk][src] = v

affected = []
for pk, srcs in bypk.items():
    if "mlb_pipeline_international" in srcs and "mlb_pipeline" not in srcs:
        affected.append(pk)
print("AFFECTED (intl grade present, NO main-pipeline grade ever):", len(affected))

ts = json.load(open(HERE / "data" / "timeseries.json", encoding="utf-8"))
players = ts["players"]
pidx = {p.get("player_key"): p for p in (players if isinstance(players, list) else players.values())}
print("timeseries players:", len(pidx))

remap = gn.build_remapper()

def intl_cell(role, yr):
    s, r, pooled = gn._paired_dists("mlb_pipeline_international", role, yr)
    if len(s) == 0 or not gn._mappable(s, r):
        return None, 0, pooled
    return float(np.mean(s) - np.mean(r)), len(s), pooled

out = []
for pk in affected:
    d = latest[(pk, "mlb_pipeline_international")]
    dt, nm, pos, fv, org, st = d
    yr = int(dt[:4])
    role = "pitcher" if gn._is_pitcher(pos) else "hitter"
    cur_norm = remap(fv, "mlb_pipeline", pos, yr)          # what ships today
    off_i, n_i, pooled_i = intl_cell(role, yr)
    if off_i is None or n_i < gn._MIN_N:
        fixed = cur_norm                                    # guarded fallback -> unchanged
        guard = "FALLBACK(canonical)"
    else:
        fixed = float(min(80.0, max(20.0, fv - off_i)))
        guard = f"intl n={n_i}{' pooled' if pooled_i else ''}"
    tsrec = pidx.get(pk)
    nsrc = None; act = None; cfv = None
    if tsrec:
        act = tsrec.get("status") or tsrec.get("active")
        cfv = tsrec.get("consensus_fv") or tsrec.get("fv")
        ps = tsrec.get("per_source") or {}
        nsrc = len(ps) if isinstance(ps, dict) else None
    out.append(dict(pk=pk, name=nm, org=org, pos=pos, role=role, year=yr, raw=fv,
                    now=cur_norm, fixed=fixed, delta=fixed - cur_norm, guard=guard,
                    in_ts=tsrec is not None, status=act, board_fv=cfv, n_src=nsrc))

out.sort(key=lambda r: r["delta"])
print("\nsource-vote movement (BEFORE consensus aggregation / single-source shrink):")
print(f"{'player':28s} {'org':4s} {'pos':5s} {'yr':5s} {'raw':>5s} {'now':>7s} {'fixed':>7s} {'delta':>7s}  in_ts  guard")
for r in out:
    print(f"{r['name'][:28]:28s} {str(r['org'])[:4]:4s} {str(r['pos'])[:5]:5s} {r['year']:5d} "
          f"{r['raw']:5.1f} {r['now']:7.2f} {r['fixed']:7.2f} {r['delta']:+7.2f}  "
          f"{str(r['in_ts']):5s}  {r['guard']}")

dl = [r["delta"] for r in out]
print(f"\nn={len(dl)}  moved={sum(1 for x in dl if abs(x)>1e-9)}  "
      f"mean={np.mean(dl):+.3f}  min={min(dl):+.3f}  max={max(dl):+.3f}")
on_board = [r for r in out if r["in_ts"]]
print(f"on the live board (in timeseries.json): {len(on_board)}")
print("  statuses:", collections.Counter(r["status"] for r in on_board))
print(f"  their mean vote delta = {np.mean([r['delta'] for r in on_board]):+.3f}")
print("\nn_sources distribution on board:", collections.Counter(r["n_src"] for r in on_board))
json.dump(out, open(HERE / "tools" / "_gn_intlalias_affected.json", "w"), indent=1)
con.close()
