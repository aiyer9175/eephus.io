# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools+ (ETOOLS_PLUS, owner decision EW3-28; docs/tools-2026-10/ETOOLS_PLUS.md).

What these pin:
  * the weights are the re-weight fit's candidate E tool-slot weights, normalized within
    side; a tool without a slot weighs 0 (section 1);
  * the scale on a fixture: 100 + 10 z of the weighted mean of the tool z scores, nearest,
    a missing tool takes the weighted mean of the available ones, coverage reported;
  * the served sidecar: built from the served data/etools.json (sha pinned, so a stale
    sidecar fails), each side centred on 100 with sd 10, every player's tool points plus
    the centring term summing to his unrounded number, no em-dash;
  * PROSPX prints the sidecar's number on the strip chip with a tooltip naming each tool's
    weight and push and the zero-weight tools, and sorts the board on it;
  * the glossary and registry text derive from the sidecar and make no comparative claim.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import pytest

import etools_plus as EP
from test_etools_sitewide import _PX_FUNCS, _PX_OBJECTS, _PX_STATEMENTS, _const, _extract, _runtime

ROOT = Path(__file__).parent
PROSPX = ROOT / "prospx" / "index.html"
SIDE = json.loads(EP.SERVED_PATH.read_text(encoding="utf-8"))
FIT = json.loads(EP.WEIGHTS_PATH.read_text(encoding="utf-8"))


def test_weights_are_candidate_e_slots_normalized_within_side():
    W = EP.weights(FIT)
    rows = FIT["production"]["E"]["tool_weights"]
    assert W["hit"]["game_pwr"] == pytest.approx(1.0)
    assert all(W["hit"][t] == 0 for t in W["hit"] if t != "game_pwr")
    fb = next(r["weight_pct_equiv"] for r in rows["pit"] if r["driver"] == "e5_fb_pit")
    cmd = next(r["weight_pct_equiv"] for r in rows["pit"] if r["driver"] == "e5_cmd_pit")
    assert W["pit"]["fb"] == pytest.approx(fb / (fb + cmd))
    assert W["pit"]["cmd"] == pytest.approx(cmd / (fb + cmd))
    assert W["pit"]["sl"] == W["pit"]["cb"] == W["pit"]["ch"] == 0
    for s in W:
        assert sum(W[s].values()) == pytest.approx(1.0)
        assert set(W[s]) == set(EP.DEFINITION[s])


def test_compose_scale_missing_tool_and_coverage():
    w = {"a": 0.75, "b": 0.25, "z": 0.0}
    vals = {"p1": {"a": 40.0, "b": 50.0}, "p2": {"a": 50.0, "b": 60.0}, "p3": {"a": 60.0, "b": 40.0},
            "p4": {"b": 70.0}, "p5": {}}
    res = EP.compose(vals, w)
    P = res["players"]
    assert "p5" not in P                                  # no weighted tool: no eTools+
    assert P["p4"]["coverage"] == pytest.approx(0.25)     # only b on file
    assert P["p4"]["z"].keys() == {"b"}                   # the weighted mean of what he has
    raw = [r["plus_raw"] for r in P.values()]
    m = sum(raw) / len(raw)
    sd = math.sqrt(sum((x - m) ** 2 for x in raw) / len(raw))
    assert m == pytest.approx(100.0) and sd == pytest.approx(10.0)
    for r in P.values():
        assert r["plus"] == EP.round_nearest(r["plus_raw"])
        assert sum(r["points"].values()) + r["centring"] == pytest.approx(r["plus_raw"] - 100.0)
    assert EP.round_nearest(104.5) == 105 and EP.round_nearest(95.5) == 96


def test_served_sidecar_is_fresh_and_centred():
    assert SIDE["etools_sha256"] == EP._sha(EP.ETOOLS_PATH), "rerun python etools_plus.py"
    assert SIDE["weights_sha256"] == EP._sha(EP.WEIGHTS_PATH)
    et = json.loads(EP.ETOOLS_PATH.read_text(encoding="utf-8"))["players"]
    for side in ("hit", "pit"):
        ps = [p for p in SIDE["players"].values() if p["side"] == side]
        assert len(ps) == SIDE["sides"][side]["pool_n"] > 500
        plus = [p["plus"] for p in ps]
        m = sum(plus) / len(plus)
        sd = math.sqrt(sum((x - m) ** 2 for x in plus) / len(plus))
        assert abs(m - 100) < 0.5 and abs(sd - 10) < 0.5
    for pk, p in SIDE["players"].items():
        assert pk in et and et[pk]["side"] == p["side"]
        pts = [x[3] for x in p["parts"] if x[3] is not None]
        assert abs(sum(pts) + p["centring"] + 100 - p["plus"]) <= 0.5 + 0.01 * len(pts) + 0.01
        for t, w, shown, _pts in p["parts"]:
            assert w > 0
            if shown is not None:
                assert shown == et[pk]["tools"][t]["shown"]
    blob = EP.SERVED_PATH.read_text(encoding="utf-8")
    assert chr(0x2014) not in blob and chr(0x2013) not in blob


def test_check_summary_is_descriptive_and_never_cut_by_fv():
    c = SIDE["check"]
    assert c and c["role"] == "descriptive" and c["adjudicates"] == "nothing"
    assert set(c["frames"]) == {"lv_dev", "vm_dev"}
    lab = json.loads(EP.CHECK_PATH.read_text(encoding="utf-8"))
    for fid, blk in lab["frames"].items():
        for side, b in blk.items():
            for k, v in b.items():
                if not isinstance(v, dict):
                    continue
                for stat in v.values():
                    for g in stat["groups"]:
                        assert g.split("|")[0] in ("hit", "pit") and g.split("|")[1].isdigit()


def test_glossary_and_registry_derive_from_the_sidecar():
    import importlib.util
    spec = importlib.util.spec_from_file_location("reg_etp", ROOT / "tools" / "register_etools_plus.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    glo = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "etools_plus")
    ent = next(e for e in glo["entries"] if e["id"] == "etools_plus")
    assert row == R.registry_row(SIDE)
    assert ent == R.glossary_entry(SIDE)
    assert row["verdict"] == "provisional" and row["eval_artifact"] == "data/etools_plus.json"
    for text in (row["summary"], ent["definition"]):
        for word in ("beats", "better", "outperform", "validated"):
            assert word not in text.lower()


_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-3);
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function ensureETools() {}
var _ETOOLS_UI = true;
eval(fs.readFileSync(args[0], "utf8"));
var side = JSON.parse(fs.readFileSync(args[1], "utf8"));
var keys = JSON.parse(fs.readFileSync(args[2], "utf8"));
var _ETOOLS = { players: {}, byMlbam: {}, tools: {}, labels: {}, plus: _indexETPlus(side) };
var out = keys.map(function (k) {
  var rec = side.players[k];
  var p = { player_key: k, mlbam_id: null, tools: { grades: {} }, statline: { is_pitcher: rec.side === "pit" } };
  var q = { player_key: "nobody", mlbam_id: rec.mlbam, tools: { grades: {} } };
  return { key: k, chip: eToolsPlusChipHTML(p), tip: eToolsPlusTip(_eToolsPlusFor(p)), detail: eToolsPlusDetailHTML(p),
           by_mlbam: (_eToolsPlusFor(q) || {}).plus };
});
_ETOOLS_UI = false;
out.push({ off: eToolsPlusChipHTML({ player_key: keys[0], tools: { grades: {} } }) });
process.stdout.write(JSON.stringify(out));
"""


def test_prospx_chip_tooltip_detail_and_sort(tmp_path):
    js = PROSPX.read_text(encoding="utf-8")
    assert '<option value="etools_plus">eTools+ (highest)</option>' in js
    assert 'state.sort === "etools_plus"' in js and '"xfv", "etools_plus",' in js
    assert 'fetch("/data/etools_plus.json"' in js
    assert "${eToolsPlusDetailHTML(p)}" in js and "const etPlusChip = eToolsPlusChipHTML(p);" in js
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    parts = [_extract(js, c) + ";" for c in _PX_OBJECTS] + [_const(js, c) for c in _PX_STATEMENTS]
    parts += [_extract(js, f"function {n}(") for n in _PX_FUNCS + ["_indexETPlus", "eToolsPlusDetailHTML"]]
    src = tmp_path / "px.js"
    src.write_text("\n".join(parts), encoding="utf-8")
    (tmp_path / "side.json").write_text(json.dumps(SIDE), encoding="utf-8")
    keys = sorted(k for k, p in SIDE["players"].items() if p["side"] == "hit")[:5]
    keys += sorted(k for k, p in SIDE["players"].items() if p["side"] == "pit")[:5]
    keys += [k for k, p in SIDE["players"].items() if p["coverage"] < 1][:1]
    (tmp_path / "keys.json").write_text(json.dumps(keys), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", _STUB, str(src), str(tmp_path / "side.json"), str(tmp_path / "keys.json")],
                         capture_output=True, text=True, env=dict(os.environ, **extra), timeout=120)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got[-1]["off"] == ""                          # eTools flag off: no chip
    for r in got[:-1]:
        rec = SIDE["players"][r["key"]]
        assert f'<span class="tg-code">eT+</span><span class="tg-val">{rec["plus"]}</span>' in r["chip"]
        assert r["tip"].startswith(f"eTools+ {rec['plus']}:") and "not a forecast" in r["tip"]
        assert "Weight 0, contributes nothing:" in r["tip"]
        for t, w, _s, _p in rec["parts"]:
            assert f"{SIDE['keys'][t]} " in r["tip"] and f"(weight {round(w * 100)}%)" in r["tip"]
        assert f'<span class="fv-badge size-sm">{rec["plus"]}</span>' in r["detail"]
        assert r["by_mlbam"] == rec["plus"] or rec["mlbam"] is None
        if rec["coverage"] < 1:
            assert "Coverage" in r["tip"] and "coverage" in r["detail"]
