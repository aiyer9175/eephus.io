# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every column of the condensed PROSPX Leaderboards resolves to a Library entry.

Task PROSPX_3_LB_LIBRARY (sitepass plan 5.2, LANE_SURFACES 2.1 L16 and 2.2
"Stat definitions"). The stat-sheet table puts data-gl="<id>" on each stat
header, and the chip titles that carried their own definitions go away with
the chips, so the Library has to hold every definition the table needs.

HEADER_GL is the header list of LANE_SURFACES 2.2 (side, view, label) with the
glossary id each header points at. It is the contract PROSPX_2 builds the
headers from. Identity and count columns (Rk, Player, Age, Org, Lvl, PA, G, HR,
IP, BBE, Pitches, Tracked) carry an abbr title only and are listed in NO_GL.

The entries come from build_glossary_data.PROSPX_LB_ENTRIES and
PROSPX_LB_EXTENSIONS (merge_prospx_lb); data/glossary.json is never edited by
hand. Reads data/, never writes it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_glossary_data as BG  # noqa: E402
import copy_lint  # noqa: E402

GLOSSARY = ROOT / "data" / "glossary.json"

HEADER_GL = [
    ("both", "identity", "eFV", "xfv"),
    ("hit", "Standard", "AVG", "avg"),
    ("hit", "Standard", "OBP", "obp"),
    ("hit", "Standard", "SLG", "slg"),
    ("hit", "Standard", "OPS", "ops"),
    ("hit", "Standard", "ISO", "iso"),
    ("hit", "Standard", "BB%", "bb_pct"),
    ("hit", "Standard", "K%", "k_pct"),
    ("hit", "Standard", "SB", "sb"),
    ("hit", "Level-relative", "OPS+ lvl", "ops_plus"),
    ("hit", "Level-relative", "ISO+", "iso_plus"),
    ("hit", "Level-relative", "PD+", "pd_plus"),
    ("hit", "Level-relative", "POW+", "pwr_plus"),
    ("hit", "Level-relative", "RPS+", "rps_plus"),
    ("hit", "Level-relative", "SC+", "statcast_plus"),
    ("hit", "Level-relative", "$DvM+", "fin_dollar_dvm"),
    ("hit", "Batted ball", "Avg EV", "exit_velocity"),
    ("hit", "Batted ball", "90th EV", "p90_ev"),
    ("hit", "Batted ball", "Max EV", "max_ev"),
    ("hit", "Batted ball", "Hard%", "hard_hit_pct"),
    ("hit", "Batted ball", "Brl%", "barrel_pct"),
    ("hit", "Batted ball", "Pull-air%", "pull_air_pct"),
    ("hit", "Batted ball", "xwOBA est", "xwoba_est"),
    ("hit", "Batted ball", "xwOBAcon est", "xwoba_est"),
    ("hit", "Swing decisions", "Z-Swing%", "z_swing_pct"),
    ("hit", "Swing decisions", "Z-Con%", "z_contact_pct"),
    ("hit", "Swing decisions", "Chase%", "chase_pct"),
    ("pit", "Standard", "ERA", "era"),
    ("pit", "Standard", "FIP", "fip"),
    ("pit", "Standard", "WHIP", "whip"),
    ("pit", "Standard", "K%", "k_pct_pitcher"),
    ("pit", "Standard", "BB%", "bb_pct_pitcher"),
    ("pit", "Standard", "K-BB%", "k_bb_pct"),
    ("pit", "Standard", "HR/9", "hr_per_9"),
    ("pit", "Level-relative", "ERA- lvl", "era_minus"),
    ("pit", "Level-relative", "pStuff+", "stf_plus"),
    ("pit", "Level-relative", "KRP+", "krp_plus"),
    ("pit", "Pitch data", "FB velo", "fb_velo"),
    ("pit", "Pitch data", "FB IVB", "fb_ivb"),
    ("pit", "Pitch data", "Whiff%", "whiff_pct"),
    ("pit", "Pitch data", "Chase%", "chase_pct"),
    ("pit", "Pitch data", "Z-Swing%", "z_swing_pct"),
    ("pit", "Pitch data", "Z-Con%", "z_contact_pct"),
    ("pit", "Contact allowed", "Avg EVa", "exit_velocity"),
    ("pit", "Contact allowed", "HardA%", "hard_hit_pct"),
    ("pit", "Contact allowed", "BrlA%", "barrel_pct"),
    ("both", "control", "Qualified", "prospx_lb_qualified"),
]

NO_GL = ("Rk", "Player", "Age", "Org", "Lvl", "PA", "G", "HR", "IP", "BBE",
         "Pitches", "Tracked")

NEW_IDS = ("sb", "z_swing_pct", "p90_ev", "max_ev", "pull_air_pct", "fb_ivb",
           "prospx_lb_qualified", "xwoba_est")

# Pitcher columns that share a hitter entry: the entry has to say how the
# pitcher reading goes.
PITCHER_LINES = ("z_contact_pct", "chase_pct", "exit_velocity", "hard_hit_pct",
                 "barrel_pct")

TEXT_FIELDS = ("term", "definition", "methodology", "formula", "example",
               "caveat", "origin")


def _entries() -> dict:
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    return {e["id"]: e for e in g["entries"]}


def _prose(e: dict) -> str:
    return " ".join(str(e.get(k) or "") for k in TEXT_FIELDS)


def test_every_header_resolves_to_an_entry():
    entries = _entries()
    missing = [(side, view, label, gid) for side, view, label, gid in HEADER_GL
               if gid not in entries]
    assert not missing, f"headers with no Library entry: {missing}"


def test_header_list_covers_lane_design_columns():
    labels = {label for _s, _v, label, _g in HEADER_GL}
    # The design's stat columns (LANE_SURFACES 2.2), none dropped.
    for label in ("SB", "OPS+ lvl", "ERA- lvl", "Z-Swing%", "90th EV", "Max EV",
                  "Pull-air%", "FB IVB", "Z-Con%", "xwOBA est", "xwOBAcon est",
                  "Avg EVa", "HardA%", "BrlA%", "Qualified"):
        assert label in labels, label
    assert not labels & set(NO_GL)


def test_new_entries_are_served_and_complete():
    entries = _entries()
    for gid in NEW_IDS:
        e = entries.get(gid)
        assert e is not None, gid
        assert "prospx" in e["module"], gid
        assert e.get("definition") and e.get("methodology") and e.get("formula"), gid
        assert e.get("shelf") in ("ark", "industry", "foundation"), gid
        if e["shelf"] in ("ark", "industry"):
            assert e.get("origin"), gid
        if e["shelf"] == "ark":
            assert "eephus.io" in e["origin"], gid
        for s in e.get("seeAlso") or []:
            assert s in entries, (gid, s)


def test_header_labels_resolve_by_name_too():
    """A reader who types the header label into the Library search lands on
    the entry (eephus-gl resolve: id, term, then alias, case-insensitive)."""
    entries = _entries()
    for _side, _view, label, gid in HEADER_GL:
        if label in ("Qualified", "xwOBA est", "xwOBAcon est"):
            continue
        e = entries[gid]
        names = {e["id"].lower(), e["term"].lower()} | {a.lower() for a in e["aliases"]}
        assert label.lower() in names, (label, gid)


def test_new_aliases_are_unique_across_the_glossary():
    owner: dict = {}
    for e in _entries().values():
        for n in {e["id"], e["term"], *e.get("aliases", [])}:
            owner.setdefault(n.lower(), set()).add(e["id"])
    for gid in NEW_IDS:
        e = _entries()[gid]
        for a in e["aliases"]:
            assert owner[a.lower()] == {gid}, (a, owner[a.lower()])
    for gid, ext in BG.PROSPX_LB_EXTENSIONS.items():
        for a in ext.get("aliases") or []:
            assert owner[a.lower()] == {gid}, (a, owner[a.lower()])


def test_pitcher_columns_have_a_pitcher_line():
    entries = _entries()
    for gid in PITCHER_LINES:
        assert "for a pitcher" in entries[gid]["methodology"].lower(), gid


def test_xwoba_est_names_its_estimator_and_xwoba_is_split():
    entries = _entries()
    est = entries["xwoba_est"]
    text = _prose(est).lower()
    assert "k-nearest-neighbour" in text and "k = 61" in text
    assert "launch speed" in text and "launch angle" in text
    xw = entries["xwoba"]
    assert "reconstruction" not in xw["methodology"]
    assert "Est. xwOBA (PROSPX)" in xw["methodology"]
    assert "xwoba_est" in xw["seeAlso"]


def test_estimator_constants_match_the_producer():
    """The xwoba_est formula states the producer's constants, so a change to
    the estimator fails here instead of leaving the Library behind."""
    import statcast_metrics as sm
    f = _entries()["xwoba_est"]["formula"]
    assert f"{sm._XWOBA_K} nearest" in f
    assert f"d_i + {sm._XWOBA_EPS}" in f
    assert f"/ {sm._XWOBA_EV_SCALE:g})" in f and f"/ {sm._XWOBA_LA_SCALE:g})" in f
    for w in ("0.88", "1.25", "1.58", "2.03"):
        assert w in f
    assert sorted(sm._BIP_WOBA_WEIGHTS.values()) == [0.0, 0.88, 1.25, 1.58, 2.03]


def test_qualifier_entry_matches_the_export_rule():
    import prospx_leaderboard_export as px
    e = _entries()["prospx_lb_qualified"]
    assert f"{px.PA_PER_TEAM_GAME:g} plate appearances per team game" in e["definition"]
    assert f"{px.IP_PER_TEAM_GAME:g} innings per team game" in e["definition"]
    assert f"PA >= {px.PA_PER_TEAM_GAME:g} x team games" in e["formula"]
    assert f"IP >= {px.IP_PER_TEAM_GAME:g} x team games" in e["formula"]


def test_level_relative_entries_state_the_served_shrink():
    import storage
    entries = _entries()
    assert f"K = {storage.K_WRC_PA:g} PA" in entries["ops_plus"]["methodology"]
    assert f"K = {storage.K_IP:g} IP" in entries["era_minus"]["methodology"]


@pytest.mark.parametrize("gid", NEW_IDS)
def test_new_entry_copy_lint(gid):
    e = _entries()[gid]
    text = _prose(e)
    assert copy_lint.EM not in text and "–" not in text, gid
    assert not copy_lint.BAN_RE.search(text), (gid, copy_lint.BAN_RE.search(text))
    recs: list = []
    for k in copy_lint.GLOSSARY_FIELDS:
        if e.get(k):
            copy_lint._rec(recs, "glossary", "data/glossary.json", f"{gid}.{k}",
                           "glossary", e[k])
    assert recs, gid
    for r in recs:
        hard, _soft = copy_lint.rule_hits(r)
        assert not hard, (gid, hard, r["text"])


def test_extension_paragraphs_copy_lint():
    for gid, ext in BG.PROSPX_LB_EXTENSIONS.items():
        paras = [ext.get("methodology")]
        if ext.get("replace"):
            paras.append(ext["replace"][2])
        for p in filter(None, paras):
            assert copy_lint.EM not in p and "–" not in p, gid
            assert not copy_lint.BAN_RE.search(p), gid
            recs: list = []
            copy_lint._rec(recs, "glossary", "data/glossary.json", gid, "glossary", p)
            for r in recs:
                hard, _soft = copy_lint.rule_hits(r)
                assert not hard, (gid, hard, r["text"])


def test_merge_is_idempotent_on_the_served_file(tmp_path):
    """The served glossary already holds everything the build source adds: a
    merge over a copy changes no byte."""
    copy = tmp_path / "glossary.json"
    shutil.copyfile(GLOSSARY, copy)
    before = copy.read_bytes()
    res = BG.merge_prospx_lb(copy)
    assert res["added"] == [] and res["extended"] == []
    assert copy.read_bytes() == before


def test_merge_adds_and_extends_from_a_bare_glossary(tmp_path):
    """From a glossary without the new terms the merge adds all eight, applies
    every extension once, and keeps CRLF line endings."""
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    g["entries"] = [e for e in g["entries"] if e["id"] not in NEW_IDS]
    for e in g["entries"]:
        ext = BG.PROSPX_LB_EXTENSIONS.get(e["id"])
        if not ext:
            continue
        for key in ("aliases", "module", "seeAlso"):
            if key in e:
                e[key] = [v for v in e[key] if v not in (ext.get(key) or [])]
        if ext.get("methodology"):
            e["methodology"] = e["methodology"].replace("\n\n" + ext["methodology"], "")
        if ext.get("replace"):
            field, old, new = ext["replace"]
            e[field] = e[field].replace(new, old)
    bare = tmp_path / "glossary.json"
    bare.write_bytes(json.dumps(g, ensure_ascii=False, indent=1).replace("\n", "\r\n").encode("utf-8") + b"\r\n")
    res = BG.merge_prospx_lb(bare)
    assert sorted(res["added"]) == sorted(NEW_IDS)
    assert sorted(res["extended"]) == sorted(BG.PROSPX_LB_EXTENSIONS)
    out = json.loads(bare.read_text(encoding="utf-8"))
    served = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    assert {e["id"]: e for e in out["entries"]} == {e["id"]: e for e in served["entries"]}
    raw = bare.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")
    assert BG.merge_prospx_lb(bare) == {"added": [], "extended": [], "n_entries": len(out["entries"])}
