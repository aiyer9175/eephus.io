# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PORT_RED_TESTS_TRIAGE (owner P-8, 2026-10-22): the glossary and registry
copy that the red tests measured against their artifacts, re-derived.

Idempotent: a second run changes nothing. Keeps each file's line endings and
the one-space indent the other glossary scripts write. `--check` exits 1 when
either file would change.

data/glossary.json
  - the six WAR-rate entries (war_pa_plus, war_ip_plus_sp, war_ip_plus_rp and
    their 3yr companions) quote data/war_rate_plus_eval.json, which the eWAR v3
    flip (aff642bd) regenerated on provider ewar_v3; every quoted figure is
    read off the artifact here, and the source sentence names the v3 frame;
  - ewar: the one-series claim names the industry tables it does not cover
    again (L13-15), which the v3 rewrite dropped;
  - positional_ladder: the Arkmetric origin names the platform;
  - fb_ivb: the alias that duplicated the induced_vertical_break entry's term
    goes (the source table in build_glossary_data.py drops it in the same
    commit);
  - then tools/glossary_sections.py restates every section from its rule.
data/model_registry.json
  - provisional_v2: the row's notes quote the artifact regenerated at a6c407a6;
  - efv_v2 and source_track_record: the two committed companion artifacts
    with no row (data/efv_v2_pricing_calibration_eval.json, the MC-5 pricing
    read; data/efv_vm3_frame_eval.json, the vm3 frame and the Pipeline-only
    panel) are cited on their parent rows' ledgers, as the registry rule
    allows for a companion that carries no verdict of its own.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
RATE_EVAL = ROOT / "data" / "war_rate_plus_eval.json"
PROV_EVAL = ROOT / "data" / "provisional_v2_eval.json"

V3_SOURCE = "FanGraphs' published WAR plus the site's ABS challenge part from 2026"
OLD_SOURCE_HIT = "Baseball-Reference run frame with pitching re-priced on FIP; the batting side equals bWAR"
OLD_SOURCE_PIT = "Baseball-Reference run frame with pitching re-priced on FIP within role"
EWAR_COVERAGE = (" Industry tables are not on it: Star Odds, the FV badge's peak WAR/yr and the "
                 "published half of the FV-to-WAR anchor that prices surplus stay on the FanGraphs "
                 "frame, which eWAR equals outside the ABS part.")
LADDER_ORIGIN = ("Arkmetric, original to eephus.io: fit here from Baseball-Reference's positional "
                 "runs. The position-switcher ladder (v2) is measured from Baseball-Reference, "
                 "FanGraphs and Statcast fielding runs.")
COMPANIONS = {
    "efv_v2": (" Companion: data/efv_v2_pricing_calibration_eval.json, the MC-5 pricing read "
               "(EFV3_C05, 2026-10-04) on the frozen fWAR label, selected nowhere."),
    "source_track_record": (" Companion: data/efv_vm3_frame_eval.json, the vm3 vintage-matched "
                            "development frame and the Pipeline-only panel (EFV3_A5, 2026-10-09), "
                            "built beside the vm2 headline and served nowhere."),
}


def _load(path: Path):
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), b"\r\n" in raw


def _dump(doc, crlf: bool) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def _f4(x: float) -> str:
    """Four decimals with no trailing zeros past the first: the copy's own style."""
    s = f"{x:.4f}".rstrip("0")
    return s if s[-1] != "." else s + "0"


def _rate_figures() -> dict:
    a = json.loads(RATE_EVAL.read_text(encoding="utf-8"))
    out = {}
    for pool in ("hit", "SP", "RP"):
        r = a["pools"][pool]["results_by_convention"]["v2"]
        w = a["pools"][pool]["window_gate"]["results_by_convention"]["v2"]
        out[pool] = {"rho": r["rho_primary"], "war_total": r["rho_baselines"]["war_total"],
                     "rate": r["rho_baselines"]["rate"], "placebo": r["rho_baselines"]["placebo"],
                     "window": w["rho_window"], "one": w["rho_one_season"]}
    return out


def _sub(entry: dict, old: str, new: str) -> bool:
    """Replace `old` with `new` in every text field of `entry`; True on a change."""
    hit = False
    for k in ("definition", "methodology", "formula", "example"):
        v = entry.get(k)
        if isinstance(v, str) and old in v and old != new:
            entry[k] = v.replace(old, new)
            hit = True
    return hit


def _rate_copy(by: dict, fig: dict) -> list[str]:
    changed = []
    h, s, r = fig["hit"], fig["SP"], fig["RP"]
    plan = {
        "war_pa_plus": [
            (f"(" + OLD_SOURCE_HIT + ")", f"({V3_SOURCE})"),
            ("Spearman correlation of 0.3711, while plain season WAR predicts the same thing at "
             "0.4058 (measured on eWAR, which on the batting side reads the same as bWAR)",
             f"Spearman correlation of {_f4(h['rho'])}, while plain season WAR predicts the same "
             f"thing at {_f4(h['war_total'])} (measured on eWAR)"),
            ("control on the same pairs scores 0.0011", f"control on the same pairs scores {_f4(h['placebo'])}"),
        ],
        "war_ip_plus_sp": [
            (f"(" + OLD_SOURCE_PIT + ")", f"({V3_SOURCE})"),
            ("Spearman correlation of 0.4726", f"Spearman correlation of {_f4(s['rho'])}"),
            ("plain season WAR (0.4496, paired gap floor above zero)",
             f"plain season WAR ({_f4(s['war_total'])}, paired gap floor above zero)"),
            ("unstandardized (0.4705, gap floor below zero)", f"unstandardized ({_f4(s['rate'])}, gap floor below zero)"),
            ("control on the same pairs scores 0.0167", f"control on the same pairs scores {_f4(s['placebo'])}"),
        ],
        "war_ip_plus_rp": [
            (f"(" + OLD_SOURCE_PIT + ")", f"({V3_SOURCE})"),
            ("Spearman correlation of 0.2323", f"Spearman correlation of {_f4(r['rho'])}"),
            ("plain season WAR (0.2267)", f"plain season WAR ({_f4(r['war_total'])})"),
            ("unstandardized (0.2319)", f"unstandardized ({_f4(r['rate'])})"),
            ("control on the same pairs scores -0.0025", f"control on the same pairs scores {_f4(r['placebo'])}"),
        ],
        "war_pa_plus_3yr": [
            ("Spearman correlation of 0.4022 against 0.3711 for one season",
             f"Spearman correlation of {_f4(h['window'])} against {_f4(h['one'])} for one season"),
        ],
        "war_ip_plus_sp_3yr": [
            ("Spearman correlation of 0.4766 against 0.4726 for one season",
             f"Spearman correlation of {_f4(s['window'])} against {_f4(s['one'])} for one season"),
        ],
        "war_ip_plus_rp_3yr": [
            ("Spearman correlation of 0.259 against 0.2323 for one season",
             f"Spearman correlation of {_f4(r['window'])} against {_f4(r['one'])} for one season"),
        ],
    }
    repoint_old = "(the lab was re-pointed from bWAR on 2026-09-11)"
    repoint_new = "(the lab was re-pointed from bWAR on 2026-09-11 and re-read on eWAR v3 on 2026-10-21)"
    for gid in ("war_pa_plus_3yr", "war_ip_plus_sp_3yr", "war_ip_plus_rp_3yr"):
        plan[gid].append((repoint_old, repoint_new))
    for gid, pairs in plan.items():
        for old, new in pairs:
            if _sub(by[gid], old, new):
                changed.append(f"{gid}: {old[:48]}")
    return changed


def apply_glossary(doc: dict) -> list[str]:
    by = {e["id"]: e for e in doc["entries"]}
    changed = _rate_copy(by, _rate_figures())
    e = by["ewar"]
    if "Star Odds" not in e["definition"]:
        anchor = " Coloured on the value ruler"
        assert anchor in e["definition"], "the ewar definition lost its ruler sentence"
        e["definition"] = e["definition"].replace(anchor, EWAR_COVERAGE + anchor, 1)
        changed.append("ewar: coverage sentence")
    if by["positional_ladder"].get("origin") != LADDER_ORIGIN:
        by["positional_ladder"]["origin"] = LADDER_ORIGIN
        changed.append("positional_ladder: origin")
    al = by["fb_ivb"].get("aliases") or []
    if "Induced vertical break" in al:
        by["fb_ivb"]["aliases"] = [a for a in al if a != "Induced vertical break"]
        changed.append("fb_ivb: alias")
    return changed


def apply_registry(doc: dict) -> list[str]:
    by = {m["model_id"]: m for m in doc["models"]}
    changed = []
    ev = json.loads(PROV_EVAL.read_text(encoding="utf-8"))
    a = ev["backcast"]["oct"]["T1"]["ANY_W12"]["pooled"]
    f = ev["backcast"]["oct"]["T2"]["FG"]["pooled"]
    lv = ev["freeze_reproduction"]["live_inputs"]
    import re
    row = by["provisional_v2"]
    notes = row.get("notes") or ""
    for pat, new in (
        (r"AUC 0\.\d+ against the level-rank null 0\.\d+",
         f"AUC {a['auc']:.3f} against the level-rank null {a['null_level_rank_auc']:.3f}"),
        (r"Brier from 0\.\d+ to 0\.\d+", f"Brier from {a['brier_raw']} to {a['brier_shifted']}"),
        (r"FanGraphs first FV MAE \d\.\d+ against \d\.\d+",
         f"FanGraphs first FV MAE {f['mae']} against {f['mae_const']}"),
        (r"Spearman 0\.\d+ on [\d,]+ matched rows",
         f"Spearman {lv['p_g12']['spearman']} on {lv['matched']:,} matched rows"),
    ):
        notes2 = re.sub(pat, new, notes, count=1)
        if notes2 != notes:
            notes = notes2
            changed.append(f"provisional_v2: {new[:32]}")
    row["notes"] = notes
    for mid, sentence in COMPANIONS.items():
        n = by[mid].get("notes") or ""
        if sentence.strip() not in n:
            by[mid]["notes"] = n.rstrip() + sentence
            changed.append(f"{mid}: companion")
    return changed


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    rc = 0
    for path, apply in ((GLOSSARY, apply_glossary), (REGISTRY, apply_registry)):
        doc, crlf = _load(path)
        changed = apply(doc)
        if changed:
            if check:
                print(f"{path.name}: would change {changed}")
                rc = 1
            else:
                path.write_bytes(_dump(doc, crlf))
                print(f"{path.name}: wrote {changed}")
        else:
            print(f"{path.name}: nothing to change")
    if not check:
        sys.path.insert(0, str(ROOT / "tools"))
        import glossary_sections
        glossary_sections.main([])
    return rc


if __name__ == "__main__":
    sys.exit(main())
