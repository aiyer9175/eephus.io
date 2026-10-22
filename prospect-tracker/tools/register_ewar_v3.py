# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v3's flip records (docs/ebr-2026-09-30/EBR_GATE.md 11.10.5 and part 12.2's
registry bullet; task EWAR_V3_ASSEMBLE):

  - registry rows ewar_v3 and ewar_v3_realized (provisional, measurement_only),
    swar_bat, swar_pit, swar_fld and swar_pos (provisional, measured_not_adopted),
    and updates to ewar (eWAR v2 is now a reference), eabs (the owner override) and
    rpw_fit (the team guard computed, candidate (c) carried);
  - glossary entries ewar (rewritten for eWAR v3), ewar_realized (new) and eabs
    (no persistence sentence, the eWAR part named);
  - data/swar_eval.json: the FILTERED copy of the tracked record
    docs/ebr-2026-09-30/swar_eval.json that 11.2.4 allows (the team guard's
    NON-INFERIOR flags and margin, never an r against club runs or wins).

Idempotent: a second run changes nothing. Keeps each file's line endings and
one-space indent; refuses when a plain round trip would rewrite either file.
Reads data/ewar_v3.json for its numbers (build it first). Then:

    python tools/register_ewar_v3.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "glossary.json"
REGISTRY = ROOT / "data" / "model_registry.json"
ARTIFACT = ROOT / "data" / "ewar_v3.json"
RECORD = ROOT / "docs" / "ebr-2026-09-30" / "swar_eval.json"
RECORD_COPY = ROOT / "data" / "swar_eval.json"

#: keys dropped from every team_guard block of the served copy (11.2.4: the r
#: values and dT live only in part 12.2 and the tracked record)
GUARD_DROP = ("r_frame", "r_part", "dT", "r_bwar_reference", "r_part_minus_bwar", "sd",
              "half_width95", "lower")


def _render(raw: bytes, doc) -> bytes:
    crlf = b"\r\n" in raw
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    if raw.endswith(b"\n"):
        text += "\r\n" if crlf else "\n"
    return text.encode("utf-8")


def filtered_record(rec: dict) -> dict:
    """The served copy: every team_guard block keeps its NON-INFERIOR flags,
    counts and underpowered marks; r values, dT and their intervals go, and the
    same-season team wins leg goes whole."""
    out = copy.deepcopy(rec)

    def walk(o, in_guard=False):
        if isinstance(o, dict):
            for k in list(o):
                if k == "team_wins":
                    del o[k]
                    continue
                if in_guard and k in GUARD_DROP:
                    del o[k]
                    continue
                walk(o[k], in_guard or k == "team_guard")
        elif isinstance(o, list):
            for v in o:
                walk(v, in_guard)
    walk(out)
    out["served_copy"] = ("filtered copy of docs/ebr-2026-09-30/swar_eval.json (EBR_GATE.md 11.2.4): the team "
                          "guard carries its NON-INFERIOR flags and margin only; no r against club runs or wins")
    return out


def _abs_numbers(art: dict) -> dict:
    c = (art.get("checks") or {}).get("2026") or {}
    r = c.get("abs_receipt") or {}
    rows = []
    for mid, by in (art.get("players") or {}).items():
        a = (((by.get("2026") or {}).get("parts") or {}).get("abs") or {})
        for side, v in a.items():
            rows.append((float(v.get("wins") or 0.0), side))
    bat = [w for w, s in rows if s == "bat"]
    pit = [w for w, s in rows if s == "pit"]
    return {"challenges": r.get("challenges"), "catcher_won": r.get("catcher_won_runs"),
            "fail": r.get("failure_cost_runs"), "rpw": c.get("rpw"),
            "bat_min": min(bat) if bat else None, "bat_max": max(bat) if bat else None,
            "pit_min": min(pit) if pit else None, "pit_max": max(pit) if pit else None,
            "n_bat": len(bat), "n_pit": len(pit)}


def glossary_entries(art: dict) -> list[dict]:
    n = _abs_numbers(art)
    rpw = n["rpw"]
    ewar = {
        "id": "ewar",
        "term": "eephusWAR (eWAR)",
        "category": "custom-index",
        "section": "Prospects",
        "module": ["prospx", "projections", "fa", "mlbstats", "franchise"],
        "aliases": ["eWAR", "eephusWAR", "eephus WAR", "eWAR v3", "eWAR v2"],
        "priority": 5,
        "definition": (
            "eephusWAR (eWAR), the site's WAR: FanGraphs' published WAR (fWAR, frozen per season) plus the site's "
            "named departures, each summing to zero across the league in its season. From 2026 one departure is "
            "carried, the ABS challenge part: a catcher's overturned ball and strike calls, measured against an "
            "average catcher per inning caught, move runs from his pitchers to him, and every failed challenge is "
            "charged to the player who made it. Every other component (batting, baserunning, fielding and framing, "
            "the positional adjustment, pitching) is FanGraphs' own. A season with no challenge term equals the "
            "player's fWAR. Beside it on player pages and in Awards, eWAR realized is the same frame with pitchers "
            "priced on the runs they allowed. The reference columns are eWAR v2 (Baseball-Reference's WAR with "
            "pitching re-priced on FIP, the site's WAR until 2026-10-21), FanGraphs WAR and bWAR. Every realized "
            "WAR a reader sees (career totals, per-season lines, WAR sorts and boards) reads eWAR, except where a "
            "page pins another series and names it: the /hof/ boards and the Franchises HISTORY line stay on bWAR. "
            "The TRAINING label (eFV labels, WAG's observed leg, the arbitration model's WAR spine, the projections) "
            "is published fWAR (see WAR). Coloured on the value ruler at 6 / 4 / 3 / 2.5 / 1.5 per season, with red "
            "under zero."),
        "methodology": (
            "Base: FanGraphs' published WAR per player and season, read from a frozen copy of MLB's sabermetrics "
            "feed (2000 to 2026), never refetched. Seasons before 2000 show eWAR v2 or bWAR and say so.\n\n"
            "Candidate departures: each one is admitted only by its own pre-registered test. The site's baserunning "
            "metric eBR, its positional ladder, the shrunk batting (HEM+ and xHEM+), pitching (SEM+ and REM+) and "
            "fielding (DEM+, the triangulated fielding and Statcast catcher runs) parts and the two pitch-economy "
            "parts were each built and tested in October 2026; none was admitted, so FanGraphs' own component stays "
            "in place for each.\n\n"
            "The ABS challenge part (from 2026, by the owner's decision): each zone challenge is valued on the "
            "season's run expectancy by count (the eABS values). A catcher's overturned calls are credited to him "
            "against an average catcher per inning caught and charged to the pitchers they were won for, against "
            "an average pitcher per inning, the way framing is handled; a failed challenge's cost (the value of the "
            "challenge it spent) is charged to the challenger and credited back across his side. A batter's own "
            "overturned calls are already in his batting runs and are not added again. Each term sums to zero per "
            "season on each side, so the league's hitter and pitcher totals are FanGraphs'. "
            + (f"2026: {n['challenges']:,} challenges, {n['catcher_won']:.1f} runs won by catchers, failed-challenge "
               f"cost {n['fail']:.1f} runs; the part moves hitters by {n['bat_min']:+.2f} to {n['bat_max']:+.2f} and "
               f"pitchers by {n['pit_min']:+.2f} to {n['pit_max']:+.2f} wins. " if n["challenges"] else "")
            + (f"Runs convert to wins at {rpw:.2f} runs per win, the slope of club wins on run differential, chosen "
               "over FanGraphs' closed form on held-out club seasons.\n\n" if rpw else "\n\n")
            + "The companion, eWAR realized (from 2016), is the same frame with each pitcher's pitching priced on his runs allowed, "
            "adjusted for park, his club's defense and the runners he inherited and left behind, re-centred so the "
            "pitchers' total is FanGraphs'. It records the season that happened; eWAR is the number every page "
            "leads with.\n\n"
            "Cadence: eWAR moves only when data/ewar_v3.json is rebuilt by hand (python tools/build_ewar_v3.py "
            "--write); its fWAR base is frozen per season. The eWAR v2 reference column still rebuilds its "
            "live season nightly and freezes each season on November 1. A player-season the file does not list "
            "carries fWAR on both series. Registration: docs/ebr-2026-09-30/EBR_GATE.md parts 9 and 11.10."),
        "formula": ("eWAR = fWAR + (ABS part runs) / RPW, the ABS part from 2026\n"
                    "ABS part, catcher: (runs his overturned calls won - innings at C x league rate) "
                    "- (his failed-challenge cost - PA x league rate)\n"
                    "ABS part, pitcher: -(runs his catchers' overturned calls won on his pitches - IP x league rate) "
                    "- (his failed-challenge cost - IP x league rate)\n"
                    "eWAR realized = eWAR + (pitchers) the runs-allowed departure, from 2016"),
        "example": ("Jose Trevino 2026: fWAR 0.05, eWAR 0.47 (his overturned calls ran well above an average "
                    "catcher's for his innings). Gabriel Moreno 2026: fWAR 5.37, eWAR 4.90. A regular who made no "
                    "challenges reads his fWAR plus a few hundredths: the league's failed-challenge cost is credited "
                    "back per plate appearance (686 PA: +0.07)."),
        "seeAlso": ["war", "ewar_realized", "eabs", "xfv", "wag", "fv_to_war_table", "war_pa_plus", "war_ip_plus_sp"],
        "shelf": "ark",
        "origin": ("Arkmetric, original to eephus.io. Built on FanGraphs' published WAR (via MLB's StatsAPI "
                   "sabermetrics feed); the challenge values are the site's own run expectancy by count."),
    }
    realized = {
        "id": "ewar_realized",
        "term": "eWAR realized",
        "category": "custom-index",
        "section": "Players & Stats",
        "module": ["projections", "hof"],
        "aliases": ["eWAR realized", "realized eWAR"],
        "priority": 6,
        "definition": (
            "The companion of eWAR on the same frame: what a season was worth in the runs that scored. "
            "Pitchers are priced on the runs they allowed, adjusted for park, their club's defense and the runners "
            "they inherited and left behind, in place of FanGraphs' FIP-based pitching; everything else, the ABS "
            "challenge part included, is eWAR's. Shown beside eWAR on player pages and in Awards; it never sorts, "
            "ranks or sums anything there."),
        "methodology": (
            "From 2016. For each pitcher-season the runs he was charged with are corrected for the runners he "
            "left on base who later scored and for the inherited runners who scored on him, each against the "
            "league's scoring rate for that base and out, then park-adjusted, with his club's fielding runs put "
            "back in proportion to the batters he faced. That runs-allowed rate replaces FIP in FanGraphs' own "
            "pitcher WAR chain, and the change is re-centred so the pitchers' league total equals FanGraphs'. "
            "Hitters' eWAR realized equals their eWAR. Registration: docs/ebr-2026-09-30/EBR_GATE.md 11.3.3 and "
            "11.10.3."),
        "formula": "eWAR realized = eWAR + (pitchers) runs-allowed WAR - FIP WAR on FanGraphs' chain, re-centred per season",
        "seeAlso": ["ewar", "war", "ra9_based_war", "fip_based_war"],
        "shelf": "ark",
        "origin": "Arkmetric, original to eephus.io, on FanGraphs' published pitcher WAR chain.",
    }
    return [ewar, realized]


def eabs_entry(cur: dict) -> dict:
    e = dict(cur)
    e["definition"] = (
        "What a player's challenges of ball and strike calls were worth this season, in runs, for batters, "
        "catchers and pitchers. eABS raw is the runs his overturned challenges won minus what his failed ones "
        "cost; eABS compares that with what the league's overturn rate on the same mix of counts would have "
        "earned. Descriptive: what happened, not a forecast. From 2026 eWAR carries a challenge part built from "
        "the same values (see eWAR).")
    meth = str(cur.get("methodology") or "")
    cut = " Season-to-season persistence was tested once on AAA 2022 to 2026 against a shuffled twin; the board says whether it held."
    meth = meth.replace(cut, "")
    add = (" eWAR's challenge part uses these values: a catcher's overturned calls against an average catcher's per "
           "inning caught, moved from his pitchers, and every failed challenge's cost charged to the challenger.")
    if add.strip() not in meth:
        meth += add
    e["methodology"] = meth
    sa = list(cur.get("seeAlso") or [])
    if "ewar" not in sa:
        sa.append("ewar")
    e["seeAlso"] = sa
    return e


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def registry_rows(art: dict, rec: dict, cur: dict) -> list[dict]:
    n = _abs_numbers(art)
    meta = art.get("meta") or {}
    rpw = meta.get("rpw") or {}
    adm = (rec.get("look") or {}).get("admission") or {}
    gen = art.get("generated_at")
    vid = art.get("fwar_vintage_id")
    base_notes = (f"Assembled by tools/build_ewar_v3.py (task EWAR_V3_ASSEMBLE, folding EBR_3_EWAR_V3) on fWAR vintage "
                  f"{vid}, build {gen}; registered in docs/ebr-2026-09-30/EBR_GATE.md parts 9.2, 9.7 and 11.10 "
                  "(11.10 committed alone before any number). After the outcome look (12.1), the skill look (12.2) and "
                  "the holdout (12.3) no look-decided part is admitted. ")
    abs_note = (f"The ABS part (candidate part 8) is carried by OWNER OVERRIDE EW3-32 of a NULL stability read, from "
                f"2026: {n['challenges']:,} zone challenges, {n['catcher_won']:.1f} catcher-won runs moved against an "
                f"average catcher per inning at C and charged to pitchers per IP, {n['fail']:.1f} runs of failure cost "
                f"charged to challengers and re-centred per side; hitters move {n['bat_min']:+.3f} to {n['bat_max']:+.3f} "
                f"wins ({n['n_bat']} rows), pitchers {n['pit_min']:+.3f} to {n['pit_max']:+.3f} ({n['n_pit']} rows). "
                if n["challenges"] else "")
    rpw_note = (f"Runs per win: form {rpw.get('form')} (RPW_GATE.md candidate (c), 10.6261), team guard "
                f"{(rpw.get('guard') or {}).get('status')} as an identity (no departure on predictor seasons 2021 to "
                "2024). ")
    ident = ("Identities refused at every build: each departure sums to zero per season and side (headline and "
             "realized), the ABS raw move equals the eABS frame's catcher-won runs, and data/ewar.json's sha256 is "
             "unchanged. No accuracy claim: eWAR is a measurement on FanGraphs' frame.")
    v3 = {
        "model_id": "ewar_v3",
        "summary": ("Measured, not a prediction: the displayed eWAR, FanGraphs' published WAR plus the ABS challenge "
                    "part from 2026 (owner override); no look-decided part was admitted."),
        "surface": ("The displayed WAR site-wide behind war_source.EWAR_V3_LIVE (career totals, season lines, MLB "
                    "player cards, the MLB Stats boards and Earned board, Awards, PAL history, the trade lookup); "
                    "data/ewar_v3.json"),
        "predicts": "Nothing forward: WAR on FanGraphs' frame with named, zero-sum departures, published per player and part",
        "champion": ("ewar_v3_1 (tools/build_ewar_v3.py, ewar_v3.py): the frozen fWAR vintage plus candidate part 8 "
                     "(ABS, 2026 on) at RPW 10.6261; eBR, the ladder, the EM+ skill parts and pitch economy not admitted"),
        "baseline": "published fWAR on identical rows: every player-season the artifact does not list equals it",
        "metric": ("Refusing identities, no forward claim: zero-sum departures per season and side; league side totals "
                   "equal fWAR's; the ABS raw move reconciles with the eABS frame"),
        "eval_artifact": "data/ewar_v3.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": base_notes + abs_note + rpw_note + ident,
    }
    real = {
        "model_id": "ewar_v3_realized",
        "summary": ("Measured, not a prediction: eWAR realized, eWAR with pitchers priced on runs allowed adjusted for "
                    "park, defense and inherited runners (R2, 2016 on); shown beside eWAR."),
        "surface": "Beside eWAR on MLB player pages and in Awards (war_real, realized_display); data/ewar_v3.json dr",
        "predicts": "Nothing forward: the season that happened, on the same frame (EBR_GATE.md 11.2.8: no forward target, no look)",
        "champion": ("eWAR plus R2's re-pinned Delta_r (EBR_GATE.md 11.3.3) on the replica's feed-only pitcher chain, "
                     "read from the swar preview the looks read"),
        "baseline": "eWAR on identical rows",
        "metric": "Accounting checks only: Delta_r sums to zero per season within the preview's 6-decimal rounding; the ABS part as for ewar_v3",
        "eval_artifact": "data/ewar_v3.json",
        "verdict": "provisional",
        "provisional_kind": "measurement_only",
        "notes": base_notes + "R2 source: " + json.dumps((meta.get("parts") or {}).get("r2", {}).get("source") or {},
                                                         sort_keys=True)[:400] + ". " + abs_note,
    }

    def swar(mid, part, label, extra):
        a = adm.get(part) or {}
        return {
            "model_id": mid,
            "summary": f"Measured, not adopted: eWAR v3's {label} candidate part; the skill look of 2026-10-19 did not admit it.",
            "surface": "None served as a number: data/swar_eval.json (the filtered record) and EBR_GATE.md part 12.2",
            "predicts": f"The candidate part's forward ranking of next-season realized {label} runs (EBR_GATE.md 11.2)",
            "champion": "none admitted; eWAR v3 keeps FanGraphs' own component",
            "baseline": "B0, the component's own realized runs in season Y; B1, a uniformly shrunk B0",
            "metric": ("Spearman gap on next-season realized runs, convention v2 primary, B 2,000, seed 20261008, margin "
                       "+0.02, twin, team guard (11.2.4), secondary estimand on fWAR(Y+1) reported"),
            "eval_artifact": "data/swar_eval.json",
            "verdict": "provisional",
            "provisional_kind": "measured_not_adopted",
            "notes": (f"Skill look 2026-10-19 (owner-waived early read, EW3-5), holdout 2026-10-21; admission: "
                      f"{a.get('reason') or 'not admitted'}. {extra}"),
        }
    rows = [v3, real,
            swar("swar_bat", "batting", "batting", "No arm is named: neither the HEM+ nor the xHEM+ arm qualified."),
            swar("swar_pit", "pitching", "pitching", "The home-run term is hr_fwar: the HR-arm clause failed."),
            swar("swar_fld", "fielding", "fielding", "Catcher component S3c not admitted either."),
            swar("swar_pos", "position", "position (our ladder)", "Judged on the ladder's held-out dMAE (11.2.3).")]
    # updates to existing rows
    up = []
    e = dict(cur.get("ewar") or {})
    if e:
        e["surface"] = ("A reference column (eWAR v2) beside the displayed eWAR (ewar_v3) on MLB player pages since "
                        "the eWAR v3 flip (EBR_GATE.md 11.10.5); F-DEF's input file; data/ewar.json keeps building "
                        "nightly")
        tag = "2026-10-21 EWAR_V3_ASSEMBLE:"
        if tag not in str(e.get("notes") or ""):
            e["notes"] = (str(e.get("notes") or "") + "\n\n" + tag + " eWAR v3 (row ewar_v3) became the displayed "
                          "eWAR behind war_source.EWAR_V3_LIVE; eWAR v2 is a reference column and the series, its "
                          "artifact and its nightly are unchanged.")
        up.append(e)
    a = dict(cur.get("eabs") or {})
    if a:
        a["summary"] = ("Measured, not a prediction: each player's ABS challenge runs this season on RE288, failed "
                        "challenges charged their option value; eWAR carries a challenge part built from it.")
        tag = "2026-10-21 EWAR_V3_ASSEMBLE:"
        notes = str(a.get("notes") or "")
        notes = notes.replace(" Not admitted into eWAR: the owner chooses (EW3-19); the reattribution-only part is "
                              "designed in gate part 7.", "")
        if tag not in notes:
            notes += (" " + tag + " OWNER OVERRIDE EW3-32 (EABS_GATE.md 9.2): the reattribution part enters eWAR v3 "
                      "and eWAR realized from 2026 although the stability read was NULL for both roles; the site "
                      "carries no stability caveat and no validated claim; this row stays provisional, never "
                      "validated. Built in EBR_GATE.md 11.10.2.")
        a["notes"] = notes
        up.append(a)
    r = dict(cur.get("rpw_fit") or {})
    if r:
        r["summary"] = ("Measured: runs per win fitted from club wins; the wins-on-run-differential slope beat the "
                        "FanGraphs closed form out of sample (lo95 +0.0135 wins) and converts eWAR v3's runs to wins.")
        r["surface"] = "eWAR v3's runs-to-wins conversion (data/ewar_v3.json meta.rpw); no page prints it"
        r["champion"] = ("(c) the slope of wins on run differential through the origin, RPW 10.6261 for every season, "
                         "admitted to eWAR v3 by EWAR_V3_ASSEMBLE after the team guard read NON-INFERIOR")
        tag = "2026-10-21 EWAR_V3_ASSEMBLE:"
        if tag not in str(r.get("notes") or ""):
            r["notes"] = (str(r.get("notes") or "") + " " + tag + " the EBR_GATE 11.2.4 team guard was computed once "
                          "as an identity: eWAR v3 carries no departure on predictor seasons 2021 to 2024, so the "
                          "candidate's roster sums equal the frame's on every club-season and dT is 0 under both "
                          "bootstraps (NON-INFERIOR, measuring no departure); no WAR sum was related to a club outcome. "
                          "(c) is carried; RPW_GATE.md part 12.2 records it.")
        up.append(r)
    return rows + up


def war_rate_summaries(cur: dict) -> list[dict]:
    """The four WAR-rate rows' summaries re-derived from data/war_rate_plus_eval.json,
    which the flip reran on the served basis (bullpen_export.join_war_rate_3yr's ONE
    BASIS rule): the dated numbers they printed were measured on eWAR v2."""
    p = ROOT / "data" / "war_rate_plus_eval.json"
    if not p.exists():
        return []
    ev = json.loads(p.read_text(encoding="utf-8"))
    day = str(ev.get("generated_at") or "")[:10]
    prov = ev.get("war_provider")

    def g(pool):
        po = (ev.get("pools") or {}).get(pool) or {}
        v = ((po.get("results_by_convention") or {}).get("v2") or {})
        return po, v
    out = []
    hp, hv = g("hit")
    sp, sv = g("SP")
    rp, rv = g("RP")
    def gap(v, k):
        return ((v.get("gap_ci_primary_minus_baseline") or {}).get(k) or {}).get("lo95")
    texts = {
        "war_pa_plus": (f"Unvalidated, G2 lost: season WAR forecasts next-year WAR/PA better ({day} on {prov}: "
                        f"{hv['rho_baselines']['war_total']:.4f} vs {hv['rho_primary']:.4f}, n {hp['n_forward_pairs']:,}, "
                        f"lo95 {gap(hv, 'war_total'):+.4f}); a descriptive index."),
        "war_ip_plus_sp": (f"Unvalidated: beats season WAR ({day} on {prov}: {sv['rho_primary']:.4f} vs "
                           f"{sv['rho_baselines']['war_total']:.4f}, n {sp['n_forward_pairs']:,}, lo95 "
                           f"{gap(sv, 'war_total'):+.4f}) but ties the raw rate (lo95 {gap(sv, 'rate'):+.4f}), so G2 "
                           "fails; descriptive."),
        "war_ip_plus_rp": (f"Unvalidated: ties season WAR at forecasting next-year WAR/IP ({day} on {prov}: "
                           f"{rv['rho_primary']:.4f} vs {rv['rho_baselines']['war_total']:.4f}, n "
                           f"{rp['n_forward_pairs']:,}, lo95 {gap(rv, 'war_total'):+.4f}), so G2 fails; a descriptive index."),
    }
    wg = ((hp.get("window_gate") or {}).get("results_by_convention") or {}).get("v2") or {}
    if wg.get("rho_window") is not None:
        texts["war_rate_plus_3yr"] = (f"Unvalidated: 3-year beats 1-year for hitters only ({day} on {prov}: "
                                      f"{wg['rho_window']:.4f} vs {hv['rho_primary']:.4f}, lo95 "
                                      f"{(wg.get('gap_ci_window_minus_one') or {}).get('lo95'):+.4f}); starters and "
                                      "relievers fail. Values are a frozen vintage.")
    for mid, s in texts.items():
        row = dict(cur.get(mid) or {})
        if row:
            row["summary"] = s
            out.append(row)
    return out


def _upsert(rows: list, key: str, new: dict, after: str) -> bool:
    cur = next((r for r in rows if r.get(key) == new[key]), None)
    if cur == new:
        return False
    if cur is not None:
        rows[rows.index(cur)] = dict(new)
    else:
        idx = next((i for i, r in enumerate(rows) if r.get(key) == after), len(rows) - 1)
        rows.insert(idx + 1, dict(new))
    return True


def main() -> int:
    if not ARTIFACT.exists():
        print("refusing: data/ewar_v3.json is not built (python tools/build_ewar_v3.py --write first)")
        return 2
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    rec = _record()

    raw = GLOSSARY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite glossary.json")
        return 2
    ents = doc["entries"]
    changed = False
    ew, real = glossary_entries(art)
    changed |= _upsert(ents, "id", ew, "war")
    changed |= _upsert(ents, "id", real, "ewar")
    cur_eabs = next((e for e in ents if e.get("id") == "eabs"), None)
    if cur_eabs is not None:
        changed |= _upsert(ents, "id", eabs_entry(cur_eabs), "abs_challenge")
    if changed:
        GLOSSARY.write_bytes(_render(raw, doc))
        print("glossary.json: wrote ewar, ewar_realized, eabs")
    else:
        print("glossary.json: nothing to write")

    raw = REGISTRY.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if _render(raw, doc) != raw:
        print("refusing: a plain round trip would rewrite model_registry.json")
        return 2
    models = doc["models"]
    cur = {m.get("model_id"): m for m in models}
    changed = False
    after = "ewar"
    for row in registry_rows(art, rec, cur) + war_rate_summaries(cur):
        if row["model_id"] in cur:
            changed |= _upsert(models, "model_id", row, row["model_id"])
        else:
            changed |= _upsert(models, "model_id", row, after)
            after = row["model_id"]
    if changed:
        REGISTRY.write_bytes(_render(raw, doc))
        print("model_registry.json: wrote ewar_v3, ewar_v3_realized, swar_*, and updated ewar, eabs, rpw_fit")
    else:
        print("model_registry.json: nothing to write")

    text = json.dumps(filtered_record(rec), indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    if not RECORD_COPY.exists() or RECORD_COPY.read_text(encoding="utf-8") != text:
        RECORD_COPY.write_text(text, encoding="utf-8")
        print("data/swar_eval.json: wrote the filtered copy")
    else:
        print("data/swar_eval.json: nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
