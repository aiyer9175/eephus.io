# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The glossary copy for the DvM+ difficulty arm, prepared for the owner's flip (DVM-6).

DVM-5 (the served build behind storage.DVM_DIFFICULTY_ARM) drafts the glossary rewrites
and the new dvm_expected_growth entry here and writes NOTHING into data/glossary.json:
they describe the arm-on method, so they land only in the flip commit, together with the
flag, the look's data/ files and the registry rows (lane design dvm_difficulty.md F.6).

    python tools/dvm_difficulty_glossary_flip.py --check          lint the drafted copy
    python tools/dvm_difficulty_glossary_flip.py --apply [--version YYYY-MM-DD]

--apply is idempotent (a second run changes nothing), keeps the file's own line endings
and its indent, and refuses a glossary whose serialization it could not reproduce byte
for byte. The flip also updates test_dvm_copy_truth.py (its glossary pins name the
retiring basis: "eFV retrospective", the ToolDvM+ "two standard deviations" example),
the dvm_plus_org / dvm_plus_tools / dvm_plus_dollar registry notes and MODEL_REGISTRY.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"

#: tools/copy_lint.py's banned words, mirrored so --check needs no import of the linter.
BANNED_WORDS = ("leverage", "seamless", "robust", "delve", "comprehensive", "crucial",
                "essential", "powerful", "showcase", "utilize", "unlock", "elevate",
                "game-changing", "cutting-edge", "tapestry", "meticulous", "underscore",
                "harness")
#: Forecast words that may not sit on a descriptive number (Part 8 copy rule).
FORECAST_WORDS = ("luck", "due", "regress", "trending", "clutch", "sleeper")
DASHES = (chr(0x2014), chr(0x2013))

ORIGIN = "Arkmetric, original to eephus.io."

#: The new entry, in full (F.6).
NEW_ENTRIES: dict[str, dict] = {
    "dvm_expected_growth": {
        "id": "dvm_expected_growth",
        "term": "Expected growth",
        "category": "custom-index",
        "section": "Prospects",
        "module": ["prospx"],
        "aliases": ["Expected growth", "Development difficulty", "dvm_expected_growth"],
        "priority": 9,
        "definition": (
            "Expected growth: the grade change a prospect's peers usually make in a year on the "
            "same source's list, for the same origin (high school, college, international), "
            "starting grade, age and level. DvM+ counts how far a farm's prospects beat that, in "
            "expected-WAR value, averaged per farm and scaled so 100 is the league mean and 10 "
            "points is one standard deviation."),
        "methodology": (
            "Fitted once a year on the spent, non-reserved history of same-source preseason list "
            "pairs (Pipeline, FanGraphs, BA; 12-month horizon), registered under "
            "docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md and frozen into "
            "data/dvm_difficulty.json. Weighted least squares on grade growth and on value growth "
            "with a source-by-year term, a source-by-side-by-starting-rung term, origin, level "
            "band, age for level and a shrunk origin-by-rung interaction; a missing end read is "
            "coded by a rule fixed before the read (a graduate at his last read before the debut, "
            "a dropped player one rung under the source's lowest printed grade). At serve time "
            "each source and step year is re-centered to a league mean residual of zero. The "
            "Development tab's Expected vs actual strip prints a farm's actual growth, the growth "
            "expected for its mix and the gap; the Development difficulty table prints the "
            "league's one-rung and two-rung rise rates by starting grade. No WAR, debut, bust or "
            "eFV quantity enters, and the grade shown beside every DvM+ number stays eFV."),
        "formula": (
            "expected grade growth E = a[source, year] + b[source, side, starting rung] + "
            "c[side, origin] + d[side, level] + e[side] x age for level + u[side, origin, rung]\n"
            "expected value growth E^W = the same model with value growth on FV_EXPECTED_WAR as "
            "the outcome\n"
            "credit (value arm) = value growth - E^W; credit (difficulty arm) = (grade growth - E) "
            "/ spread of the starting rung"),
        "example": (
            "A 45 FV high-school hitter in A ball whose peers usually gain 2 grade points in a "
            "year and who gains 5 earns credit for the 3 points above expected, valued on the FV "
            "table; a 60 FV college arm whose peers usually hold their grade earns credit for "
            "the whole of a 5-point rise."),
        "seeAlso": ["dvm_plus", "tools_dvm_plus", "fin_dollar_dvm", "farm_grade_development", "fv"],
        "shelf": "ark",
        "origin": ORIGIN,
    },
}

#: Fields replaced on existing entries (every other field of the entry is kept).
REWRITES: dict[str, dict] = {
    "dvm_plus": {
        "definition": (
            "Farm development index, difficulty-adjusted: how far a farm's prospects beat the "
            "grade growth expected for prospects like them, in expected-WAR value. 100 = the "
            "league-mean farm, 10 points = one standard deviation across the 30 orgs. Feeds the "
            "Development branch of the farm grade and the farm tiebreaker."),
        "methodology": (
            "Each farm's credit over a trailing window of annual preseason steps (1y through 8y; "
            "7y is the principal window). A step is one source's grade for a prospect on its "
            "preseason list against the same source's grade a year later (Pipeline, FanGraphs or "
            "BA, each read on its own published grades; the grade shown beside the number stays "
            "eFV). The step's value growth is its change on the fixed FV-to-expected-career-WAR "
            "table (FV_EXPECTED_WAR), so a 60 to 70 step is worth 13.0 and a 40 to 50 step 2.5 "
            "before adjustment. Expected growth (dvm_expected_growth) is what prospects with the "
            "same origin, starting grade, age for level, level and source usually gain in that "
            "year, from the frozen table in data/dvm_difficulty.json; the credit is the value "
            "growth minus that expectation, re-centered to a league mean of zero within each "
            "source and year. A step is split across clubs by the days each held the prospect "
            "(his org tenures), a stretch outside affiliated ball credits nobody, a graduate's "
            "step ends at his last read before the debut, and a player-year counts once however "
            "many sources list him. A farm's figure is the weighted mean of its credits, shrunk "
            "toward zero by its effective number of steps, then indexed 100 + 10z across the 30 "
            "orgs; a window with fewer than 10 effective steps prints a dash. The eFV "
            "retrospective series, the previous basis, is no longer read, so an eFV refit does "
            "not rewrite development history. The blended trajectory_score weights the principal "
            "7y window 60%, 3y 30% and 1y 10%."),
        "formula": (
            "step value growth = W(grade a year later) - W(starting grade), W = FV_EXPECTED_WAR\n"
            "credit = step value growth - expected value growth for the prospect's origin, "
            "starting grade, age, level and source\n"
            "farm credit = sum over steps of tenure share x source weight x credit / sum of the "
            "weights, shrunk by n_eff / (n_eff + k)\n"
            "DvM+ = 100 + 10 x (farm credit - league mean) / league standard deviation\n"
            "trajectory_score = 0.60 x 7y + 0.30 x 3y + 0.10 x 1y"),
        "example": (
            "An org at 7yDvM+ 120 saw its prospects gain two standard deviations more "
            "expected-WAR value over seven years than prospects of the same origin, starting "
            "grade, age and level usually gain, with acquisitions credited only for the days "
            "held and graduations neutral."),
    },
    "tools_dvm_plus": {
        "definition": (
            "Org tool-development composite, difficulty-adjusted and weighted by what each "
            "position needs. 100 = league-mean pace. Its per-tool legs are 100 + 10z across the "
            "orgs; the composite is a weighted mean of them, so its own spread is narrower (see "
            "the example)."),
        "methodology": (
            "Position-weighted blend of the org's per-tool DvM+ (HitDvM+, PowerDvM+, SpeedDvM+, "
            "FieldDvM+, ArmDvM+ for hitters; FBDvM+, SLDvM+, CBDvM+, CHDvM+, CmdDvM+ for pitchers). "
            "Each per-tool DvM+ starts from the same annual same-source steps as DvM+, one tool "
            "at a time: a step's tool-grade growth minus the growth expected for the prospect's "
            "starting tool grade, starting FV, origin, age, level and source, in units of that "
            "starting grade's spread, credited to each club by the days it held him. No "
            "FV-to-WAR transform, level weight or stretch applies: age and level sit in the "
            "expectation, and a single tool has no value on the FV table. The org mean over the "
            "principal 7y window is shrunk toward zero by its effective number of steps and "
            "indexed 100 + 10z across the orgs. Each tool is weighted by its importance to the "
            "position bucket: catchers' Field and Arm, outfielders' Speed, starters' Fastball "
            "and Command.\n\nComputed per bucket (C / INF / OF / SP / RP) from the bucket's own "
            "per-tool DvM+ (org-wide value when a cell is sparse), then blended across buckets "
            "by how many prospects the org develops in each. Pitch selection, bat control and "
            "control carry no expectation model and print a dash.\n\nFanGraphs physical grades "
            "are excluded (static values with no multi-snapshot history). The composite itself "
            "is display only, but the per-bucket per-tool values it is built from are the Tool "
            "leg of each position bucket's development blend, which feeds the Development "
            "leaves of farm_score."),
        "example": (
            "An org that develops Field and Arm in its catchers and Fastball and Command in its "
            "starters outscores an equal-on-average org whose gains came in low-importance "
            "tools. The composite averages legs that only partly agree, so its spread across the "
            "30 orgs is narrower than its legs': read a composite against the composite column, "
            "not as 10 points per standard deviation."),
    },
    "tool_specific_dvm_plus": {
        "definition": (
            "Per-tool org development index, difficulty-adjusted. 100 = league mean; +10 = one "
            "standard deviation across the orgs."),
        "methodology": (
            "Same shape as DvM+, one tool at a time. For each tool group (Hit, Power = game and "
            "raw power, Speed, Field, Arm, FB, SL, CB, CH, Cmd), every annual same-source step's "
            "tool-grade growth minus the growth expected for the prospect's starting tool grade, "
            "starting FV, origin, age, level and source, in units of the starting grade's "
            "spread, credited to the club that held him for the days of the step; the org's "
            "weighted mean over the principal 7y window, shrunk by its effective number of "
            "steps, anchored 100 + 10z across the league. PitchSel, BatCtrl and Ct have no "
            "expectation model and print a dash."),
        "formula": (
            "credit = (tool grade a year later - starting tool grade - expected growth) / spread "
            "of the starting grade\n"
            "ToolDvM+_tool = 100 + 10 x (org mean credit - league mean) / league standard "
            "deviation"),
        "example": (
            "An org at HitDvM+ 119 and PowerDvM+ 124: its hitters' Hit and Power grades rose "
            "about two standard deviations more than prospects with the same starting grades, "
            "origin, age and level usually manage."),
    },
    "tool_delta": {
        "methodology": (
            "For each tool with 2 or more consensus snapshots: delta = last grade - first grade. "
            "Feeds the +N / -N chip beside each tool on the prospect page and the Tool "
            "development table. The org roll-ups (HitDvM+, PowerDvM+, ..., ToolDvM+) no longer "
            "read it: they read annual same-source steps against expected growth "
            "(tool_specific_dvm_plus). A tool observed once has no delta (not enough signal), "
            "which is different from no change."),
    },
    "fin_dollar_dvm": {
        "term": "Org DvM+ (player)",
        "aliases": ["Org DvM+ (player)", "DvM+ (player)", "Org $DvM+", "$DvM+", "Financial DvM",
                    "fin_dollar_dvm"],
        "definition": (
            "The org-level roll-up of its active prospects' DvM+ (player): how far each one's own "
            "grade growth beat the growth expected for his origin, starting grade, age and "
            "level, indexed to 100. It reads no dollars."),
        "methodology": (
            "Mean of the DvM+ (player) of an org's active prospects. Each prospect's figure is "
            "the mean of his own difficulty-adjusted credits over his last three annual "
            "preseason steps (one credit per step, sources weighted so a player-year counts "
            "once), shrunk toward zero by n / (n + 2) and scored 100 + 10 x value / spread across "
            "all active prospects, with no tier pool and no clamp. It replaces the FV-tier pace "
            "index served before the flip; the payload key is unchanged. Feeds the Value branch "
            "at 10% beside WAR per $M and contract surplus."),
        "formula": (
            "per-prospect credit per step = value growth - expected value growth (see dvm_plus)\n"
            "DvM+ (player) = 100 + 10 x (mean credit over the last 3 steps x n / (n + 2)) / "
            "spread across actives; no clamp\n"
            "Org DvM+ (player) = mean of the org's actives' DvM+ (player)\n"
            "feeds the Value branch as the fin_dollar_dvm leaf (weight 0.10)"),
        "example": (
            "An org whose actives average DvM+ (player) 108 reads Org DvM+ (player) 108: its "
            "prospects' grades moved further than prospects like them usually move."),
    },
    "farm_grade_development": {
        "methodology": (
            "Development branch of the farm grade tree, the mean of four leaves: (a) Hitter "
            "development and (b) Pitcher development, each the org's principal-window (7y) DvM+ "
            "at weight 2 plus that side's development blend at weight 1, both scored against "
            "the league; the side blend is a position-bucket weighted mean (C 35%, INF 40%, OF "
            "25%; SP 80%, RP 20%) in which each bucket blends FV-DvM+ and Tool-DvM+ (together "
            "75%, Tool taking 30% of that slice and 40% to 60% once FV-DvM+ leads Tool-DvM+ by "
            "15 to 35 points or more) with Statcast DvM+ (25%); (c) Health Management; and (d) "
            "Statcast Quality (the org's aggregate SC+). DvM+ legs are 100-anchored (+10 = 1 "
            "standard deviation). Growth is not counted the same at every starting grade: each "
            "FV step is credited at its value on the FV-to-expected-WAR table (a 60 to 70 step "
            "is worth 13.0, a 40 to 50 step 2.5) minus the value growth expected for the "
            "prospect's origin, starting grade, age and level, and each tool step is its growth "
            "above the expected growth for that starting tool grade, in spread units "
            "(dvm_expected_growth)."),
    },
    "farm_tiebreaker": {
        "methodology": (
            "A z-blend across the 30 orgs: 0.40 total active surplus + 0.25 7yDvM+ (the principal "
            "window, difficulty-adjusted) + 0.35 raw graduate WAR, re-standardized by the blend's "
            "own spread and anchored 100 + 10z. Surplus and DvM+ are the dollar and indexed views "
            "of one controlled-value concept, so they share weight; raw graduate WAR adds "
            "realized MLB output. The weighted sum of z-scores has a spread of about 0.70, so "
            "without the re-standardization the score moved about 7 points per blend sigma; the "
            "division changes no org order. Shown under each letter with a component breakdown "
            "and a continuous 1-30 rank."),
    },
}


def _texts() -> list[tuple[str, str]]:
    out = []
    for gid, fields in list(REWRITES.items()) + list(NEW_ENTRIES.items()):
        for k, v in fields.items():
            if isinstance(v, str):
                out.append((f"{gid}.{k}", v))
            elif isinstance(v, list):
                out.extend((f"{gid}.{k}[{i}]", s) for i, s in enumerate(v) if isinstance(s, str))
    return out


def _load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def _dump(doc: dict, like: bytes) -> bytes:
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if like.endswith(b"\n"):
        text += "\n"
    if b"\r\n" in like:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def check(path: Path = GLOSSARY) -> list[str]:
    """Problems with the drafted copy: a dash, a banned or forecast word, a seeAlso that
    does not resolve, a rewrite of an entry that does not exist, a new entry that already
    exists, or a glossary whose bytes --apply could not reproduce."""
    problems: list[str] = []
    for where, text in _texts():
        for d in DASHES:
            if d in text:
                problems.append(f"{where}: dash")
        low = text.lower()
        for w in BANNED_WORDS + FORECAST_WORDS:
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                problems.append(f"{where}: {w!r}")
    if path.exists():
        doc, raw = _load(path)
        ids = {e["id"] for e in doc["entries"]}
        for gid in REWRITES:
            if gid not in ids:
                problems.append(f"rewrite of a missing entry {gid}")
        for gid, entry in NEW_ENTRIES.items():
            if gid in ids:
                problems.append(f"new entry {gid} already exists")
            for ref in entry.get("seeAlso", []):
                if ref not in ids and ref not in NEW_ENTRIES:
                    problems.append(f"{gid}.seeAlso {ref} does not resolve")
        if _dump(doc, raw) != raw:
            problems.append("the glossary does not round-trip through indent=1; refusing to reformat it")
    return problems


def apply(path: Path = GLOSSARY, *, version: str | None = None) -> int:
    """Write the rewrites and the new entry; returns the number of entries changed (0 on a
    second run). The version stamp moves only when an entry changes."""
    problems = [p for p in check(path) if not p.startswith("new entry")]
    if problems:
        raise SystemExit("refusing to apply: " + "; ".join(problems))
    doc, raw = _load(path)
    changed = 0
    by_id = {e["id"]: e for e in doc["entries"]}
    for gid, fields in REWRITES.items():
        entry = by_id[gid]
        new = dict(entry)
        new.update(fields)
        if new != entry:
            entry.clear()
            entry.update(new)
            changed += 1
    for gid, entry in NEW_ENTRIES.items():
        if gid in by_id:
            if by_id[gid] != entry:
                by_id[gid].clear()
                by_id[gid].update(entry)
                changed += 1
            continue
        anchor = next((i for i, e in enumerate(doc["entries"]) if e["id"] == "dvm_plus"), None)
        doc["entries"].insert(anchor + 1 if anchor is not None else len(doc["entries"]), entry)
        changed += 1
    if changed:
        if version:
            doc["version"] = version
        path.write_bytes(_dump(doc, raw))
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="lint the drafted copy; writes nothing")
    ap.add_argument("--apply", action="store_true", help="write data/glossary.json (the flip commit only)")
    ap.add_argument("--version", default=None, help="the glossary version stamp to set on a change")
    ap.add_argument("--path", default=str(GLOSSARY))
    a = ap.parse_args(argv)
    path = Path(a.path)
    if a.apply:
        n = apply(path, version=a.version)
        print(f"{path}: {n} entries changed")
        return 0
    problems = check(path)
    for p in problems:
        print("PROBLEM", p)
    print("dvm_difficulty_glossary_flip: " + ("clean" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
