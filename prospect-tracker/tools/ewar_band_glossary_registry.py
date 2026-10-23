# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR uncertainty band's glossary entry and registry row
(docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md part 10 and amendment 13.1; owner decision
EW3-50; task EWAR_UNCERTAINTY_BAND built it, the flip applies it).

PREPARED DARK, APPLIED IN THE FLIP COMMIT (FLIP RULE AG4-Q: the flip carries the flag,
the registry, the glossary, the copy and the tests). Refuses while ewar_band.BAND_LIVE
is False, so nothing lands before the flag does.

    python tools/ewar_band_glossary_registry.py --check   # what would change; writes nothing
    python tools/ewar_band_glossary_registry.py           # apply (idempotent)
    python tools/gen_audit_docs.py                        # then regenerate the generated docs

What it writes:
  data/glossary.json        a new entry `ewar_band` after `ewar_realized`
  data/model_registry.json  a new row `ewar_band` after `ewar_v3_realized` (provisional,
                            measurement_only)
  test_methodology_freshness.py  MODEL_GLOSSARY gains ewar_band -> [ewar_band, ewar]

Every number in the copy is read from the read's tracked record
(data/_labs/ewar_uncertainty_band/record.json), never typed. Keeps each file's line
endings, one-space indent, non-ASCII and trailing newline; refuses when a plain round
trip would rewrite a file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewar_band as EB  # noqa: E402

GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
FRESHNESS = ROOT / "test_methodology_freshness.py"


def _span(record: dict) -> tuple[float, float]:
    cov = [float(c["coverage"]) for c in record["cells"]]
    return min(cov), max(cov)


def entry(record: dict) -> dict:
    lo, hi = _span(record)
    return {
        "id": "ewar_band",
        "term": "eWAR band (+/-)",
        "category": "custom-index",
        "section": "Players & Stats",
        "module": ["projections", "mlbstats", "awards"],
        "aliases": ["eWAR uncertainty band", "eWAR +/-", "the band"],
        "priority": 7,
        "definition": ("The +/- printed beside eWAR and eWAR realized: how far a season's number could sit "
                       "from another measure of the same season. It adds two spreads: how much the "
                       "season's own events vary (batting, baserunning and pitching runs measured on two "
                       "halves of the season, odd and even games) and how far two published WAR systems "
                       "(FanGraphs and Baseball-Reference) disagree for the same playing time. On seasons "
                       f"held out from its constants it covered the other measure {lo * 100:.0f} to "
                       f"{hi * 100:.0f} percent of the time in every playing-time band, for a stated 80 "
                       "percent. It is not a range for a player's talent."),
        "methodology": ("Per component, the noise per plate appearance or inning comes from the two halves of "
                        "each season (2011 on for batting and baserunning, 2018 on for pitching); the method "
                        "spread comes from FanGraphs WAR minus Baseball-Reference WAR, halved in variance, "
                        "2000 on. Fielding's own sampling noise has no half-season split in the site's data, "
                        "so it rides in the method spread. Each spread is then rescaled per playing-time "
                        "band so its coverage on the fitting seasons is 80 percent. The check read held-out "
                        "seasons once: every 5th to 95th percentile interval of coverage, by playing-time "
                        "band, sat between 70 and 90 percent. A side under 20 plate appearances or 5 innings "
                        "carries no band."),
        "formula": ("band = eWAR +/- 1.2816 x sqrt( [batting + baserunning noise per PA x PA + pitching noise "
                    "per IP x IP] / RPW^2 + method spread per PA x PA + per IP x IP ), each term rescaled by "
                    "its playing-time band"),
        "seeAlso": ["ewar", "ewar_realized", "war"],
        "shelf": "ark",
        "origin": "Arkmetric, original to eephus.io, on FanGraphs' and Baseball-Reference's published WAR.",
    }


def registry_row(record: dict) -> dict:
    lo, hi = _span(record)
    k = record["constants"]["k"]
    return {
        "model_id": "ewar_band",
        "summary": ("Measured, not a prediction: an 80 percent +/- beside eWAR and eWAR realized from "
                    "split-half component noise plus fWAR and bWAR disagreement, coverage-checked by "
                    "playing-time band on held-out seasons."),
        "surface": ("Beside eWAR and eWAR realized on MLB player pages (war_pm, war_real_pm), on the MLB Stats "
                    "eWAR board (war_pm) and beside eWAR realized in Awards (realized_pm_display); "
                    "data/ewar_band.json"),
        "predicts": "Nothing forward: the spread of a season's measured value, same season",
        "champion": (f"sigma^2 = [m^2 k_bat PA + m^2 k_ebr PA + m^2 k_pit IP] / RPW^2 + m^2 k_src,bat PA + "
                     f"m^2 k_src,pit IP; k_bat {k['bat']:.4f}, k_ebr {k['ebr']:.4f}, k_fip {k['fip']:.4f}, "
                     f"k_ra {k['ra']:.4f} runs^2 per PA or IP; k_src {k['src_bat']:.6f} per PA and "
                     f"{k['src_pit']:.6f} per IP (wins^2); split-conformal m per playing-time band"),
        "baseline": ("N0, an exposure-blind band of one width per family, and N1, the Awards measurement band "
                     "with no sampling term"),
        "metric": ("TEST coverage by playing-time band (24 cells) under player- and club-clustered bootstraps, "
                   "B 4,000, seed 20261023; interval score against N0 and N1; the planted check"),
        "eval_artifact": "data/ewar_band.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (f"Registered alone in {EB.GATE_DOC} (2026-10-22); amended before the read (13.1: constants and "
                  "multipliers on FIT and CAL together, the multiplier always applied, equivalence range "
                  "[0.70, 0.90]) after the planted check failed the registered design; read once 2026-10-22: "
                  f"PASS, TEST coverage {lo:.3f} to {hi:.3f} across the 24 cells, planted truth "
                  f"{record['planted']['truth_pass']} of 20 and broken {record['planted']['broken_pass']} of 20. "
                  "Under the registered range [0.75, 0.85] five cells would sit outside. The Awards realized "
                  "read keeps its measurement band for its verdicts (owner question EWUB-Q1)."),
    }


FRESH_ANCHOR = '    "ewar": ["ewar"],\n'
FRESH_LINE = '    "ewar_band": ["ewar_band", "ewar"],\n'


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def _apply_glossary(doc: dict, record: dict) -> list[str]:
    rows = doc["entries"]
    by = {e.get("id"): e for e in rows}
    new = entry(record)
    cur = by.get(new["id"])
    if cur == new:
        return []
    if cur is not None:
        rows[rows.index(cur)] = new
    else:
        idx = next(i for i, r in enumerate(rows) if r.get("id") == "ewar_realized")
        rows.insert(idx + 1, new)
    return [new["id"]]


def _apply_registry(doc: dict, record: dict) -> list[str]:
    rows = doc["models"]
    by = {m.get("model_id"): m for m in rows}
    new = registry_row(record)
    cur = by.get(new["model_id"])
    if cur == new:
        return []
    if cur is not None:
        rows[rows.index(cur)] = new
    else:
        idx = next((i for i, r in enumerate(rows) if r.get("model_id") == "ewar_v3_realized"), len(rows) - 1)
        rows.insert(idx + 1, new)
    return [new["model_id"]]


def main(argv=None, *, glossary: Path = GLOSSARY, registry: Path = REGISTRY, freshness: Path = FRESHNESS) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report what would change; write nothing")
    a = ap.parse_args(argv)
    if not EB.BAND_LIVE:
        print("refusing: ewar_band.BAND_LIVE is False; this runs in the flip commit, after the flag")
        return 2
    record = json.loads(EB.RECORD.read_text(encoding="utf-8"))
    if record.get("disposition") != "PASS":
        print(f"refusing: the read recorded {record.get('disposition')!r}, not PASS")
        return 2
    plans = []
    for path, fn in ((glossary, _apply_glossary), (registry, _apply_registry)):
        raw = Path(path).read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if _render(raw, doc) != raw:
            print(f"refusing: a plain round trip would rewrite {Path(path).name}")
            return 2
        plans.append((Path(path), raw, doc, fn(doc, record)))
    fresh_txt = Path(freshness).read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in fresh_txt else "\n"
    anchor, line = FRESH_ANCHOR.replace("\n", nl), FRESH_LINE.replace("\n", nl)
    fresh_todo = line not in fresh_txt
    if fresh_todo and fresh_txt.count(anchor) != 1:
        print("refusing: the MODEL_GLOSSARY anchor for ewar is not in test_methodology_freshness.py once")
        return 2
    for path, _raw, _doc, done in plans:
        print(f"{path.name}: {', '.join(done) if done else 'nothing to change'}")
    print(f"{Path(freshness).name}: {'ewar_band mapping' if fresh_todo else 'nothing to change'}")
    if a.check:
        return 0
    for path, raw, doc, done in plans:
        if done:
            path.write_bytes(_render(raw, doc))
    if fresh_todo:
        Path(freshness).write_bytes(fresh_txt.replace(anchor, anchor + line).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
