# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pWOBA xwOBA blend flip (owner NOV15-PWOBA-FLIP = (a), 2026-10-14):
move the registry rows pwoba_blend_regate and phem_marcel_lite and the
glossary entry pwoba onto the served blend, idempotently.

    python tools/register_pwoba_flip.py
    python tools/gen_audit_docs.py

Every number written here is READ from data/pwoba_blend_regate_eval.json;
nothing is typed. A second run changes nothing. Keeps each file's own line
endings and its one-space indent, and refuses a file whose serialization it
cannot reproduce byte for byte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
GLOSSARY = ROOT / "data" / "glossary.json"
ART = "data/pwoba_blend_regate_eval.json"
FLIP_DATE = "2026-10-14"
MARK = f"SERVED ({FLIP_DATE} owner flip"


def _read(path: Path):
    raw = path.read_bytes()
    crlf = (b"\r\n" in raw, raw.endswith(b"\n"))
    doc = json.loads(raw.decode("utf-8"))
    if _dump(doc, crlf) != raw:
        sys.exit(f"{path.name} does not round-trip through indent=1; refusing to reformat it")
    return doc, crlf


def _dump(doc, like) -> bytes:
    crlf, trailing = like
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if trailing:
        text += "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def _numbers() -> dict:
    art = json.loads((ROOT / ART).read_text(encoding="utf-8"))
    reg = art["registered_regate"]
    if art["verdict"]["status"] != "PASS":
        sys.exit("the re-gate artifact does not read PASS; nothing to flip")
    return {
        "n": reg["n"],
        "blend": reg["rhos_v1"]["output_blend"],
        "inc": reg["rhos_v1"]["fa_projection"],
        "lo1": reg["gap_ci_blend_minus_incumbent_v1"]["lo95"],
        "lo2": reg["gap_ci_blend_minus_incumbent_v2"]["lo95"],
        "years": f"{min(reg['pred_years'])}-{max(reg['pred_years'])}",
    }


def registry(doc: dict, k: dict) -> bool:
    rows = {m["model_id"]: m for m in doc["models"]}
    changed = False
    row = rows["pwoba_blend_regate"]
    if MARK not in (row.get("notes") or ""):
        row["summary"] = (
            f"Re-gate PASS at the extended n: frozen blend rho {k['blend']} vs pWOBA "
            f"{k['inc']} (n {k['n']:,}, lo95 {k['lo1']:+.4f}); served as pWOBA since the "
            f"owner flip ({FLIP_DATE}).")
        row["surface"] = "/mlbstats/ Hitter Leaderboards pWOBA column (the served blend)"
        row["champion"] = ("pWOBA = 0.8 x fa_projection woba_proj + 0.2 x current-season "
                           "Savant est_woba (PA >= 100), else woba_proj; frozen b=0.2 "
                           "(hitter_export._join_pwoba)")
        row["notes"] = (row.get("notes") or "").replace(
            "PRODUCTION DIFF (recorded, NOT applied)", "PRODUCTION DIFF (applied at the flip below)"
        ) + (
            f" {MARK}, NOV15-PWOBA-FLIP = (a)): hitter_export.pwoba_xwoba_blend_on() now "
            "defaults ON and EEPHUS_PWOBA_XWOBA_BLEND stays only as an off switch (0, off, "
            "false or no), so the nightly serves the blend with no environment change; "
            "data/hitter_leaderboards.json regenerated with the blend.")
        changed = True
    row = rows["phem_marcel_lite"]
    note = (f" {MARK}): the served pWOBA is now the frozen xwOBA output blend on top of "
            "this engine's woba_proj; its gate is registry row pwoba_blend_regate.")
    if MARK not in (row.get("notes") or ""):
        row["notes"] = (row.get("notes") or "") + note
        changed = True
    return changed


def glossary(doc: dict, k: dict) -> bool:
    e = next(x for x in doc["entries"] if x["id"] == "pwoba")
    if "est_woba" in (e.get("formula") or ""):
        return False
    e["definition"] = (
        "A hitter's projected NEXT-season wOBA: the site's FA-engine Marcel (the engine that "
        "prices the FA class board and drives MLB Projections) blended one part in five with "
        "the hitter's current-season Statcast xwOBA. Read it like wOBA: ~.310 league average, "
        ".370 a star season, .400+ elite.")
    e["methodology"] = e["methodology"].replace(
        "A purpose-built multi-year challenger lost the same gate. ",
        "A purpose-built multi-year challenger lost the same gate. The served number then "
        "blends that projection with the current season's Savant expected wOBA (xwOBA) at a "
        "frozen weight of 0.2, for hitters with 100+ PA on the Savant leaderboard; everyone "
        "else keeps the engine projection. The blend passed its registered re-gate "
        f"(data/pwoba_blend_regate_eval.json): over predictor seasons {k['years']} and "
        f"{k['n']} held-out pairs it reads a Spearman rho of {k['blend']} "
        f"against {k['inc']} for the engine projection alone, paired-bootstrap floor "
        f"{k['lo1']:+.4f} above zero, {k['lo2']:+.4f} under the player-clustered bootstrap. ")
    e["formula"] = e["formula"].replace(
        "\npWOBA = the projected components reassembled with fixed run-value weights;",
        "\nwOBA_proj = the projected components reassembled with fixed run-value weights\n"
        "pWOBA = 0.8 x wOBA_proj + 0.2 x current-season xwOBA (Savant est_woba, 100+ PA), "
        "else wOBA_proj;")
    if "est_woba" not in e["formula"] or "pwoba_blend_regate_eval" not in e["methodology"]:
        sys.exit("the pwoba glossary entry no longer has the anchors this script edits")
    e["example"] = (
        "Trailing component rates worth wOBA .355 / .345 / .330 blend to about .347; the "
        "league pull and a year of aging settle the engine near .340, and a current-season "
        "xwOBA of .360 lifts pWOBA to 0.8 x .340 + 0.2 x .360 = .344.")
    return True


def main() -> int:
    k = _numbers()
    for path, fn in ((REG, registry), (GLOSSARY, glossary)):
        doc, crlf = _read(path)
        if fn(doc, k):
            path.write_bytes(_dump(doc, crlf))
            print(f"updated {path.relative_to(ROOT)}")
        else:
            print(f"unchanged {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
