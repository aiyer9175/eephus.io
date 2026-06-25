# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Generate leaderboard CSVs and the standalone browser tool from validated data.

Keeps the old tool's UI concepts (sidebar leaderboard + player detail pane,
search / level filters) but every value comes from the rebuilt pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, OUTPUTS, log_run

TOOL_DIR = OUTPUTS / "tool"
LB_DIR = OUTPUTS / "leaderboards"


def r3(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 3)


def main() -> None:
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    LB_DIR.mkdir(parents=True, exist_ok=True)

    ship = pd.read_parquet(DATA_PROCESSED / "shipped_projections_2026.parquet")
    dec = pd.read_parquet(DATA_PROCESSED / "decision_plus.parquet")
    grids = pd.read_parquet(DATA_PROCESSED / "zone_grids.parquet")
    g26 = grids[grids.season == 2026]
    grid_by_player: dict[tuple[int, str], dict] = {}
    for r in g26.itertuples(index=False):
        key = (int(r.batter_id), r.level)
        grid_by_player.setdefault(key, {})[int(r.zone_final)] = [
            int(r.zpitches), int(r.zswings), int(r.zcontacts),
            int(r.zbip), int(r.ztb)]

    # ---- leaderboard CSVs ----
    cols = ["batter_id", "batter_name", "level", "tier", "age", "age_vs_level",
            "repeat_level", "pa", "pitches", "tracked_share", "k_pct", "bb_pct",
            "decision_plus", "reliability", "posterior_sd", "ci80_lo", "ci80_hi",
            "proj_k_pct", "proj_bb_pct", "mlb_equiv_k_pct", "mlb_equiv_bb_pct",
            "mlb_equiv_decision_plus", "take_ball_shrunk", "ts_called_shrunk",
            "swing_shrunk", "chase_shrunk", "contact_pct", "zone_overlay"]
    full = ship[[c for c in cols if c in ship.columns]].sort_values(
        "decision_plus", ascending=False)
    full.to_csv(LB_DIR / "milb_decision_plus_full_2026.csv", index=False)
    for level in ["AAA", "AA", "A+", "A", "CPX"]:
        full[full.level == level].to_csv(
            LB_DIR / f"milb_decision_plus_{level.replace('+', 'plus')}_2026.csv", index=False)

    # MLB validation board: 2026 MLB Decision+ (descriptive reference only)
    mlb = dec[(dec.season == 2026) & (dec.level == "MLB") & (dec.pitches >= 300)]
    mlb_cols = ["batter_id", "batter_name", "age", "pa", "pitches", "k_pct", "bb_pct",
                "decision_plus", "reliability", "tier", "o_swing_pct", "z_swing_pct"]
    mlb[[c for c in mlb_cols if c in mlb.columns]].sort_values(
        "decision_plus", ascending=False).to_csv(
        LB_DIR / "mlb_decision_plus_reference_2026.csv", index=False)

    # AAA->MLB transition board: 2025 AAA hitters who reached MLB in 2026
    aaa25 = dec[(dec.season == 2025) & (dec.level == "AAA") & (dec.pitches >= 500)]
    mlb26 = dec[(dec.season == 2026) & (dec.level == "MLB") & (dec.pa >= 50)]
    trans = aaa25.merge(mlb26[["batter_id", "k_pct", "bb_pct", "pa", "decision_plus"]],
                        on="batter_id", suffixes=("_aaa25", "_mlb26"))
    trans = trans.rename(columns={"batter_name": "name"})[
        ["batter_id", "name", "age", "pa_aaa25", "k_pct_aaa25", "bb_pct_aaa25",
         "decision_plus_aaa25", "pa_mlb26", "k_pct_mlb26", "bb_pct_mlb26",
         "decision_plus_mlb26"]].sort_values("decision_plus_aaa25", ascending=False)
    trans.to_csv(LB_DIR / "aaa_to_mlb_transition_board.csv", index=False)

    # ---- tool payload ----
    hist = dec[dec.pitches >= 150][
        ["batter_id", "season", "level", "decision_plus", "pitches", "k_pct", "bb_pct"]]
    hist_by_player: dict[int, list] = {}
    for r in hist.itertuples(index=False):
        hist_by_player.setdefault(int(r.batter_id), []).append(
            [int(r.season), r.level, r3(r.decision_plus), int(r.pitches),
             r3(r.k_pct), r3(r.bb_pct)])
    for v in hist_by_player.values():
        v.sort(key=lambda x: (x[0], x[1]))

    players = []
    for r in ship.itertuples(index=False):
        pid = int(r.batter_id)
        players.append({
            "id": pid, "name": r.batter_name, "lvl": r.level, "tier": r.tier,
            "age": r3(r.age), "avl": r3(r.age_vs_level),
            "rep": bool(r.repeat_level), "pa": int(r.pa), "pit": int(r.pitches),
            "trk": r3(r.tracked_share), "k": r3(r.k_pct), "bb": r3(r.bb_pct),
            "dp": r3(r.decision_plus), "rel": r3(r.reliability),
            "lo": r3(r.ci80_lo), "hi": r3(r.ci80_hi),
            "pk": r3(getattr(r, "proj_k_pct", None)),
            "pbb": r3(getattr(r, "proj_bb_pct", None)),
            "mk": r3(getattr(r, "mlb_equiv_k_pct", None)),
            "mbb": r3(getattr(r, "mlb_equiv_bb_pct", None)),
            "mdp": r3(getattr(r, "mlb_equiv_decision_plus", None)),
            "comp": {
                "Take quality": r3(getattr(r, "take_ball_shrunk", None)),
                "2K called-strike": r3(getattr(r, "ts_called_shrunk", None)),
                "Swing rate": r3(getattr(r, "swing_shrunk", None)),
                "First-pitch swing": r3(getattr(r, "fp_swing_shrunk", None)),
                "3-ball swing": r3(getattr(r, "tb_swing_shrunk", None)),
                "Chase (tracked)": r3(getattr(r, "chase_shrunk", None)),
                "Contact%": r3(getattr(r, "contact_pct", None)),
            },
            "hist": hist_by_player.get(pid, []),
            "grid": grid_by_player.get((pid, r.level), {}),
        })

    payload = json.dumps({"built": "2026-06-12", "players": players},
                         separators=(",", ":"))
    html = HTML_TEMPLATE.replace("__PAYLOAD__", payload)
    out_html = TOOL_DIR / "milb_decision_plus_tool.html"
    out_html.write_text(html)
    print(f"tool: {out_html}  ({len(players)} players, {len(payload)//1024} KB payload)")
    print(f"leaderboards: {LB_DIR}")
    print(f"transition board rows: {len(trans)}")
    log_run("tool_v1", n_players=len(players))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiLB Decision+ 2026 (rebuilt)</title>
<style>
:root{--bg:#f6f5f1;--panel:#fff;--ink:#171717;--muted:#696b6a;--line:#d8d7d0;
--accent:#16616b;--accent-soft:#e6f2f2;--red:#b73531;--blue:#2f669e;--gold:#9a6b16}
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink)}
.app{min-height:100vh;display:grid;grid-template-columns:430px minmax(0,1fr)}
aside{border-right:1px solid var(--line);background:#fbfaf7;display:flex;flex-direction:column;height:100vh}
header{padding:16px 16px 10px;border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--muted);font-size:12px;margin:0}
.controls{display:grid;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line)}
input,select{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);padding:0 10px;font-size:13px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
#list{overflow-y:auto;flex:1}
.item{padding:8px 14px;border-bottom:1px solid #eceae3;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px}
.item:hover{background:var(--accent-soft)}.item.sel{background:var(--accent-soft);border-left:3px solid var(--accent)}
.nm{font-size:13px;font-weight:600}.meta{font-size:11px;color:var(--muted)}
.dp{font-size:15px;font-weight:700;color:var(--accent)}
.badge{font-size:10px;padding:1px 6px;border-radius:8px;border:1px solid var(--line);color:var(--muted)}
.badge.A{background:#e7f3e7;color:#22662a;border-color:#bcd9bf}.badge.B{background:#fdf3e2;color:#8a6210;border-color:#e8d3a4}
.badge.C{background:#f6e5e4;color:#8c2f2c;border-color:#e2bab8}
main{padding:22px;overflow-y:auto;height:100vh}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:16px;max-width:980px}
h2{margin:0 0 2px;font-size:22px}h3{margin:0 0 10px;font-size:14px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:12px}
.stat{background:#fafaf7;border:1px solid #ecebe4;border-radius:8px;padding:10px}
.stat .v{font-size:20px;font-weight:700}.stat .l{font-size:11px;color:var(--muted)}
.bar{height:10px;background:#eee;border-radius:5px;position:relative;margin:4px 0 10px}
.bar i{position:absolute;top:0;bottom:0;border-radius:5px;background:var(--accent)}
.warn{color:var(--red);font-size:12px;margin:4px 0}
table{border-collapse:collapse;font-size:12px;width:100%}td,th{padding:4px 8px;border-bottom:1px solid #eee;text-align:right}
td:first-child,th:first-child{text-align:left}
.note{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.5}
</style></head><body>
<div class="app">
<aside>
<header><h1>MiLB Decision+ 2026</h1>
<p class="sub">Rebuilt pipeline &middot; 68,866 games &middot; PA gate PASS &middot; built 2026-06-12</p></header>
<div class="controls">
<input id="q" placeholder="Search player...">
<div class="row2">
<select id="lvl"><option value="">All levels</option><option>AAA</option><option>AA</option><option>A+</option><option>A</option><option>CPX</option></select>
<select id="sort">
<option value="dp">Decision+</option><option value="mdp">MLB-equiv D+</option>
<option value="pk">Proj K% (asc)</option><option value="pbb">Proj BB%</option>
<option value="rel">Reliability</option><option value="pit">Pitches</option>
</select></div>
<div class="row2">
<select id="tier"><option value="">All tiers</option><option>A</option><option>B</option><option>C</option></select>
<select id="minpit"><option value="0">Any pitches</option><option value="300">300+ pitches</option><option value="600" selected>600+ pitches</option><option value="1000">1000+ pitches</option></select>
</div></div>
<div id="list"></div>
</aside>
<main id="detail"><div class="card"><h2>Select a player</h2>
<p class="note">Decision+ core uses call-code components available at every level
(take quality, 2-strike discipline, count-state selectivity). Zone metrics
(chase) appear only where pitch tracking exists &mdash; AAA fully, A-ball partially,
AA/A+ not at all. Values are EB-shrunk; CI80 reflects sample size.</p></div></main>
</div>
<script>
const DATA=__PAYLOAD__;
const P=DATA.players;
const fmt=(x,pct)=>x==null?"–":(pct?(100*x).toFixed(1)+"%":x.toFixed(1));
const list=document.getElementById("list");
let sel=null;
function render(){
  const q=document.getElementById("q").value.toLowerCase();
  const lvl=document.getElementById("lvl").value;
  const tier=document.getElementById("tier").value;
  const minp=+document.getElementById("minpit").value;
  const key=document.getElementById("sort").value;
  let rows=P.filter(p=>(!q||p.name.toLowerCase().includes(q))&&(!lvl||p.lvl===lvl)&&(!tier||p.tier===tier)&&p.pit>=minp);
  rows.sort((a,b)=>key==="pk"?(a.pk??9)-(b.pk??9):(b[key]??-1)-(a[key]??-1));
  list.innerHTML=rows.slice(0,400).map(p=>`<div class="item${sel===p.id?" sel":""}" onclick="show(${p.id})">
  <div><div class="nm">${p.name}</div><div class="meta">${p.lvl} · age ${p.age??"?"} · ${p.pit} pit · rel ${fmt(p.rel)}</div></div>
  <div style="text-align:right"><div class="dp">${fmt(p.dp)}</div><span class="badge ${p.tier}">Tier ${p.tier}</span></div></div>`).join("");
}
function compBar(label,val,pct){
  if(val==null)return "";
  return `<tr><td>${label}</td><td>${fmt(val,pct)}</td></tr>`;
}
// zone heatmap: 3x3 in-zone (1-9, catcher view) + 4 out-zone quadrants (11-14)
function heatColor(v,lo,hi){
  if(v==null)return "#f0efe9";
  const t=Math.max(0,Math.min(1,(v-lo)/(hi-lo)));
  const r=Math.round(238+t*(183-238)),g=Math.round(242+t*(53-242)),b=Math.round(245+t*(49-245));
  return `rgb(${r},${g},${b})`;
}
function zoneSvg(grid,statFn,lo,hi,title,fmtFn){
  const S=190,M=25,IN=(S-2*M)/3;
  let cells="";
  const quad={11:[0,0],12:[S/2,0],13:[0,S/2],14:[S/2,S/2]};
  for(const z of [11,12,13,14]){
    const d=grid[z],v=d?statFn(d):null;
    const[qx,qy]=quad[z];
    cells+=`<rect x="${qx}" y="${qy}" width="${S/2}" height="${S/2}" fill="${heatColor(v,lo,hi)}" stroke="#d8d7d0"><title>zone ${z}: ${v==null?"n/a":fmtFn(v)} (${d?d[0]:0} pitches)</title></rect>`;
    if(v!=null)cells+=`<text x="${qx+(qx?S/2-14:14)}" y="${qy+(qy?S/2-8:16)}" font-size="9" fill="#555" text-anchor="middle">${fmtFn(v)}</text>`;
  }
  for(let row=0;row<3;row++)for(let col=0;col<3;col++){
    const z=1+col+3*row,d=grid[z],v=d?statFn(d):null;
    const x=M+col*IN,y=M+row*IN;
    cells+=`<rect x="${x}" y="${y}" width="${IN}" height="${IN}" fill="${heatColor(v,lo,hi)}" stroke="#999"><title>zone ${z}: ${v==null?"n/a":fmtFn(v)} (${d?d[0]:0} pitches)</title></rect>`;
    if(v!=null)cells+=`<text x="${x+IN/2}" y="${y+IN/2+4}" font-size="11" font-weight="600" fill="#222" text-anchor="middle">${fmtFn(v)}</text>`;
  }
  cells+=`<rect x="${M}" y="${M}" width="${S-2*M}" height="${S-2*M}" fill="none" stroke="#444" stroke-width="1.5"/>`;
  return `<div style="display:inline-block;margin-right:18px;text-align:center">
  <div style="font-size:12px;color:var(--muted);margin-bottom:4px">${title}</div>
  <svg width="${S}" height="${S}">${cells}</svg></div>`;
}
function zoneMaps(p){
  if(!p.grid||Object.keys(p.grid).length===0)return "";
  const sw=d=>d[0]>=5?d[1]/d[0]:null;                 // swing rate
  const dmg=d=>d[1]>=5?d[4]/d[1]:null;                // TB per swing
  const con=d=>d[1]>=5?d[2]/d[1]:null;                // contact per swing
  return `<div class="card"><h3>Zone maps (catcher's view)</h3>
  ${zoneSvg(p.grid,sw,0.15,0.85,"Swing rate",v=>(100*v).toFixed(0)+"%")}
  ${zoneSvg(p.grid,dmg,0,0.6,"Damage (TB per swing)",v=>v.toFixed(2))}
  ${zoneSvg(p.grid,con,0.5,0.95,"Contact per swing",v=>(100*v).toFixed(0)+"%")}
  <p class="note">Zones from official tracking where available, otherwise from
  calibrated stringer coordinates (95.9% in/out holdout agreement; 93.5%+ at
  minor-league parks). Cells with fewer than 5 pitches/swings are blank.</p></div>`;
}
function show(id){
  sel=id;const p=P.find(x=>x.id===id);render();
  const warns=[];
  if(p.tier==="C")warns.push("Tier C: thin behavior sample — interpret with caution.");
  if(p.rel!=null&&p.rel<0.3)warns.push("Low reliability ("+fmt(p.rel)+"): heavy shrinkage applied.");
  if(p.trk!=null&&p.trk<0.5)warns.push("Zone metrics unavailable/partial at this level ("+fmt(p.trk*100)+"% of pitches tracked): chase not shown or park-biased.");
  if(p.pa<200)warns.push("Only "+p.pa+" PA in 2026 so far.");
  const histRows=p.hist.map(h=>`<tr><td>${h[0]} ${h[1]}</td><td>${fmt(h[2])}</td><td>${h[3]}</td><td>${fmt(h[4],1)}</td><td>${fmt(h[5],1)}</td></tr>`).join("");
  document.getElementById("detail").innerHTML=`
  <div class="card"><h2>${p.name}</h2>
  <p class="sub">${p.lvl} · age ${p.age} (${p.avl>0?"+":""}${fmt(p.avl)} vs level) ${p.rep?"· repeat level":""} · ${p.pa} PA · ${p.pit} pitches · Tier ${p.tier}</p>
  ${warns.map(w=>`<div class="warn">⚠ ${w}</div>`).join("")}
  <div class="grid">
  <div class="stat"><div class="v">${fmt(p.dp)}</div><div class="l">Decision+ (CI80 ${fmt(p.lo)}–${fmt(p.hi)})</div></div>
  <div class="stat"><div class="v">${fmt(p.mdp)}</div><div class="l">MLB-equiv Decision+</div></div>
  <div class="stat"><div class="v">${fmt(p.rel)}</div><div class="l">Reliability</div></div>
  <div class="stat"><div class="v">${fmt(p.k,1)} / ${fmt(p.bb,1)}</div><div class="l">2026 K% / BB%</div></div>
  </div></div>
  <div class="card"><h3>Projections (next season)</h3>
  <div class="grid">
  <div class="stat"><div class="v">${fmt(p.pk,1)}</div><div class="l">Proj K% @ ${p.lvl}</div></div>
  <div class="stat"><div class="v">${fmt(p.pbb,1)}</div><div class="l">Proj BB% @ ${p.lvl}</div></div>
  <div class="stat"><div class="v">${fmt(p.mk,1)}</div><div class="l">MLB-equiv K%</div></div>
  <div class="stat"><div class="v">${fmt(p.mbb,1)}</div><div class="l">MLB-equiv BB%</div></div>
  </div>
  <p class="note">Champion models: deep-statline ridge at AAA/AA/CPX; statline+behavior
  components at A+/A (where components add +1.5–3.9pp R²). MLB equivalents via the
  within-player level ladder. Composite Decision+ is descriptive — it does not feed
  the K%/BB% projection at AAA/AA.</p></div>
  <div class="card"><h3>Components (EB-shrunk)</h3>
  <table>${compBar("Take quality (ball share of takes)",p.comp["Take quality"],true)}
  ${compBar("2-strike called-strike share",p.comp["2K called-strike"],true)}
  ${compBar("Swing rate",p.comp["Swing rate"],true)}
  ${compBar("First-pitch swing",p.comp["First-pitch swing"],true)}
  ${compBar("3-ball swing",p.comp["3-ball swing"],true)}
  ${compBar("Chase (tracked only)",p.comp["Chase (tracked)"],true)}
  ${compBar("Contact%",p.comp["Contact%"],true)}</table></div>
  ${zoneMaps(p)}
  <div class="card"><h3>Season history</h3>
  <table><tr><th>Season</th><th>D+</th><th>Pitches</th><th>K%</th><th>BB%</th></tr>${histRows}</table></div>`;
}
["q","lvl","sort","tier","minpit"].forEach(id=>document.getElementById(id).addEventListener("input",render));
render();
</script></body></html>
"""


if __name__ == "__main__":
    main()
