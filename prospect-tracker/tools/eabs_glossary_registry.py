"""The eABS glossary entry and registry row (docs/eabs-2026-10-15/EABS_GATE.md part 8).

Idempotent: a second run changes nothing. Keeps each file's line endings, its
one-space indent and the glossary's non-ASCII and trailing newline; refuses when a
plain round trip would rewrite either file. Then regenerate the generated docs:

    python tools/eabs_glossary_registry.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
GLOSSARY_AFTER = "abs_challenge"
REGISTRY_AFTER = "count_value"

ENTRY = {
    "id": "eabs",
    "term": "eABS (ABS challenge runs)",
    "category": "custom-index",
    "section": "Players & Stats",
    "module": ["mlbstats"],
    "aliases": ["eABS", "eABS raw", "ABS challenge runs", "challenge runs"],
    "priority": 27,
    "definition": "What a player's challenges of ball and strike calls were worth this season, in runs, for batters, catchers and pitchers. eABS raw is the runs his overturned challenges won minus what his failed ones cost; eABS compares that with what the league's overturn rate on the same mix of counts would have earned. Descriptive: what happened, not a forecast. From 2026 eWAR carries a challenge part built from the same values (see eWAR).",
    "methodology": "Every ABS zone challenge of the MLB regular season is read from MLB's game feeds, and each club's totals match MLB's own count in every game. An overturned call is worth a ball against a strike at the challenged count, bases and outs, on that season's run expectancy by count (RE288). A batter's win turns a strike into a ball; a catcher's or pitcher's turns a ball into a strike. A call that stands is worth nothing by itself, but it spends one of the club's two challenges (a successful one is kept). That cost is the value of a held challenge at that half-inning, score margin and number of challenges left. It is measured as the extra runs clubs went on to gain from their challenges with one more in hand. eABS weighs each challenge by how far its result sits from the league's overturn rate for the same side of the ball and count, so a player who only challenges full-count pitches is measured against full-count challenges. eWAR's challenge part uses these values: a catcher's overturned calls against an average catcher's per inning caught, moved from his pitchers, and every failed challenge's cost charged to the challenger.",
    "formula": "eABS raw = runs won - failed-challenge cost; eABS = sum over challenges of (overturned - league rate for the cell) x (run value + failure cost)",
    "seeAlso": ["abs_challenge", "run_expectancy", "ewar"],
    "shelf": "ark",
    "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
}


def _row(stab: dict | None, payload: dict | None) -> dict:
    disp = ""
    if stab:
        prim = stab.get("primary") or {}
        bits = []
        for role in ("batter", "catcher"):
            r = prim.get(role) or {}
            re_ = r.get("real") or {}
            if re_.get("rho") is not None:
                bits.append(f"{role}s {r.get('disposition')} (rho {re_['rho']:.4f}, lo95 {re_['lo95']:.4f}, "
                            f"MDE95 {re_['mde95']:.4f}, {re_['n_obs']} pair observations)")
        disp = "; ".join(bits)
    lg = ((payload or {}).get("league") or {}).get("all") or {}
    vals = (payload or {}).get("values") or {}
    return {
        "model_id": "eabs",
        "summary": "Measured, not a prediction: each player's ABS challenge runs this season on RE288, failed challenges charged their option value; eWAR carries a challenge part built from it.",
        "surface": "/mlbstats/ Challenges tab (batters, catchers, pitchers), data/eabs_leaderboards.json",
        "predicts": "Nothing: eABS raw (runs won minus failed-challenge cost) and eABS (against the league overturn rate on the same mix of side and count), descriptive season totals",
        "champion": "none. v = RE288 called-pitch value at the challenged state; failed-challenge cost = the option value of a held challenge by half-inning, challenges held and score margin (gate part 2.3); the constant C0 carried beside it",
        "baseline": "the league overturn rate per cell (side, balls, strikes): eABS is 0 for a league-average challenger on the same mix",
        "metric": "Refusing invariants, no forward claim: board counts reconcile with the ABS ledger per role; eABS raw equals runs won minus cost per row; per cell, overturned minus rate sums to 0; no negative value or cost; budget walk violations at most 1 percent. Stability (gate part 5, reported, deciding no served number): AAA 2022 to 2026 self-persistence, Spearman, permuted twin, planted recovery, MDE95",
        "eval_artifact": "data/eabs_leaderboards.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": (
            "Registered 2026-10-15 in docs/eabs-2026-10-15/EABS_GATE.md (task EWAR_T4_EABS, ewar-map plan T4 steps 2 and 3, owner decisions EW3-16 to EW3-20), "
            "committed alone before any number. Built from the ABS challenge ledger (EWAR_T4_ABS_LEDGER) and RE288 (count_value). "
            + (f"MLB 2026: {lg.get('n')} zone challenges, {lg.get('won')} overturned, {lg.get('rg')} runs won, failed-challenge cost {lg.get('fc')} runs "
               f"(mean {vals.get('mean_fail_cost')} per failure; the constant C0 is {vals.get('c0')}). " if lg else "")
            + (f"Stability check, run once (data/_labs/eabs/stability.json): {disp}. " if disp else "")
            + "2026-10-21 EWAR_V3_ASSEMBLE: OWNER OVERRIDE EW3-32 (EABS_GATE.md 9.2): the reattribution part enters eWAR v3 and eWAR realized from 2026 although the stability read was NULL for both roles; the site carries no stability caveat and no validated claim; this row stays provisional, never validated. Built in EBR_GATE.md 11.10.2."
        ),
    }


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def main() -> int:
    stab_p = ROOT / "data" / "_labs" / "eabs" / "stability.json"
    pay_p = ROOT / "data" / "eabs_leaderboards.json"
    stab = json.loads(stab_p.read_text(encoding="utf-8")) if stab_p.exists() else None
    payload = json.loads(pay_p.read_text(encoding="utf-8")) if pay_p.exists() else None
    if payload is None:
        print("refusing: data/eabs_leaderboards.json is not built (python eabs_export.py first)")
        return 2

    for path, key, coll, after, new in ((GLOSSARY, "id", "entries", GLOSSARY_AFTER, ENTRY),
                                        (REGISTRY, "model_id", "models", REGISTRY_AFTER, _row(stab, payload))):
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if _render(raw, doc) != raw:
            print(f"refusing: a plain round trip would rewrite {path.name}")
            return 2
        rows = doc[coll]
        cur = next((r for r in rows if r.get(key) == new[key]), None)
        if cur == new:
            print(f"{path.name} already carries {new[key]}; nothing written")
            continue
        if cur is not None:
            rows[rows.index(cur)] = dict(new)
        else:
            idx = next((i for i, r in enumerate(rows) if r.get(key) == after), len(rows) - 1)
            rows.insert(idx + 1, dict(new))
        path.write_bytes(_render(raw, doc))
        print(f"{path.name}: wrote {new[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
