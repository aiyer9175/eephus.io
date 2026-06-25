# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time glossary update for the FA v2 / MLB Projections overhaul
(2026-06-10). Slugs are permalinks and NEVER change; display names and
definitions do: mYears -> projLength, mGuarantee -> projGuarantee,
mAAV -> projAAV, Deal+ -> verdict framing, convex rational value,
fit v2 (payroll/will-spend + MLB incumbent blockers), prospect surplus
re-anchor, and the new MLB Projections module entries. Provenance
tooling — data/glossary.json stays the hand-maintained canonical file."""

from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).parent / "data" / "glossary.json"


def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in d["entries"]}

    def upd(slug: str, **kw) -> None:
        e = by_id[slug]
        for k, v in kw.items():
            if k == "add_aliases":
                cur = e.setdefault("aliases", [])
                for a in v:
                    if a not in cur:
                        cur.append(a)
            else:
                e[k] = v

    upd("m_years", term="projLength", add_aliases=["projLength", "mYears", "projected length"],
        definition="Predicted contract length in years (P10-P90 banded), from a log-years model "
                   "with comps stacking and a prime-years-remaining term. Formerly displayed as mYears.",
        methodology="Contract length is modeled before money (teams trade years against AAV). The "
                    "stage predicts log(years) with curvature terms (WAR squared, age x WAR), prime "
                    "years remaining (max(0, 30 - age) — the buyable seasons behind long deals), and "
                    "the nearest-comps median length stacked as a feature; it beat the comps baseline "
                    "0.441 vs 0.485 MAE across nine held-out winters (Gate 2, fa_mkt_v2).")
    upd("m_guarantee", term="projGuarantee", add_aliases=["projGuarantee", "mGuarantee"],
        definition="Predicted total contract guarantee for a free agent, from the market model "
                   "(what teams WILL pay, not what the production is worth). Formerly displayed as mGuarantee.")
    e = by_id["m_guarantee"]
    e["methodology"] = (e.get("methodology") or "").replace("mGuarantee is the market model",
                                                            "projGuarantee is the market model")
    upd("m_aav", term="projAAV", add_aliases=["projAAV", "mAAV"],
        definition="Predicted average annual value: projGuarantee / projLength, with its own "
                   "P10-P90 band. Formerly displayed as mAAV.",
        methodology="Both framings of a contract are projected: the per-year price (projAAV) and the "
                    "total value / length (projGuarantee / projLength). projAAV bands ride the "
                    "guarantee band at the point-estimate term.")
    upd("deal_plus", term="Deal verdict (Deal+)",
        add_aliases=["verdict", "deal verdict", "value", "overpay"],
        definition="The surfaces render a plain-English VERDICT — value (projected underpaid), "
                   "market (priced about right), overpay (projected overpaid) — backed by Deal+, "
                   "the 100-scale index of rational value against price.",
        methodology="Deal+ = 100 x rational value / predicted (or actual) guarantee. Verdict band "
                    "edges are EMPIRICALLY CENTERED on the 2015-2026 corpus terciles, not symmetric "
                    "around 100: Deal+ under convex pricing is right-skewed (corpus p33 = 81, median "
                    "= 121, p67 = 186), so value is >= 185, overpay is < 85, market is the middle "
                    "tercile. Each verdict named exactly a third of twelve winters of real contracts; "
                    "a class that skews one way against these fixed bands is information.")
    upd("rational_value",
        definition="The NPV of a free agent's projected WAR path: each season priced CONVEXLY "
                   "through the platform's tier curve at the winter's ex-ante FA $/WAR level, "
                   "escalated per season and discounted at the platform's 9% rate. One of the "
                   "platform's two independently derived numbers — what the production is worth, "
                   "never what the market will pay.",
        methodology="Rational value shares the same NPV currency as PROSPX prospect surplus — and, "
                    "since v2, the same CONVEX season pricing (value_framework's tier curve, rescaled "
                    "to the winter's $/WAR level): a 1-WAR season and the third win of a 3-WAR season "
                    "are not the same product, and a flat rate graded the entire bottom of the class "
                    "as a bargain (measured: class median Deal+ 220 under flat pricing). It is "
                    "deliberately computed with no reference to the market model: the gap between the "
                    "two numbers (Contract Surplus) only means something because neither side peeks "
                    "at the other.")
    upd("fit_components",
        definition="The five 0-1 scores behind every FA team fit: need (displacement WAR gap at the "
                   "position, discounted when a near-ETA PROSPX prospect blocks it; MLB incumbents "
                   "block through the gap itself and are NAMED in the blocked-by list), window "
                   "(marginal playoff leverage at the club's baseline wins), afford (CBT-basis tax "
                   "space against the predicted AAV, with a documented floor for habitual taxpayers), "
                   "park (batted-side park factor — deliberately the smallest weight, a tiebreaker "
                   "not a driver), and behavior (WILL they spend: biggest-ever guarantee vs this "
                   "price, recent 3-winter outlay, $100M-deal participation).",
        methodology="v2 reweight: need 0.31 / window 0.19 / afford 0.22 / park 0.04 / behavior 0.24. "
                    "Park was cut from 0.12 after the measured failure mode — the most suppressive "
                    "park topped EVERY pitcher's fit list because park alone separated otherwise-"
                    "similar clubs. Afford reads Spotrac's CBT-basis tax space (the number front "
                    "offices budget against) and floors at 0.4 for clubs over the line that keep "
                    "signing nine-figure deals; behavior blends deal-scale history (0.5), recency-"
                    "weighted three-winter FA outlay (0.3), and $100M-deal count (0.2). Blocked-by "
                    "names both kinds of blocker: PX = a near-ETA PROSPX prospect (FV >= 50), MLB = "
                    "a contracted incumbent projecting >= 2.5 WAR at the slot the signing would "
                    "displace.")
    # PROSPX surplus value + $/WAR (tiered) — the v3 re-anchor.
    if "surplus_value" in by_id:
        e = by_id["surplus_value"]
        e["methodology"] = ((e.get("methodology") or "") + "\n\nv3 — the $/WAR LEVEL re-anchors at "
                            "load to the FA module's signings-implied series (data/fa_dpw_series.json: "
                            "what clubs actually paid per discounted projected win on the open market, "
                            "the Gate-2-validated estimator), trailing-3-winter mean, tier shape "
                            "preserved. Open-market $/WAR is the right basis for surplus: it prices "
                            "what the wins would otherwise cost to BUY. Each control season still "
                            "escalates with $/WAR inflation and discounts at 9%.").strip()
    if "dpw_tier" in by_id:
        e = by_id["dpw_tier"]
        e["methodology"] = ((e.get("methodology") or "") + "\n\nSince the v3 re-anchor the tier "
                            "rates rescale at load to the FA signings-implied level (trailing 3 "
                            "winters; shape preserved) — one market, one price of a win, shared by "
                            "prospect surplus, FA rational value, and MLB Projections.").strip()

    new_entries = [
        {"id": "proj_buckets", "term": "Probability buckets (floor / mean / ceiling)",
         "category": "fa", "module": ["fa", "platform"],
         "aliases": ["floor", "ceiling", "P10/P90 WAR path", "probability bucketing"],
         "priority": 76,
         "definition": "Every projected WAR path ships three variants: mean, floor (P10) and "
                       "ceiling (P90). Veterans take the Gate-1 empirical year-1 residual quantile "
                       "for their reliability bucket, applied to the year-1 WAR and decayed along "
                       "the SAME aging curves — uncertainty propagates the way talent does. "
                       "Prospects take the 10th/90th-percentile OUTCOME BUCKET of the calibrated "
                       "P(bucket|FV) categorical — a prospect's downside is busting, not a ribbon.",
         "methodology": "The quantiles come from the committed Gate-1 artifact "
                        "(fa_gate1_eval.json band_quantiles, empirical per side x exposure tier), "
                        "so the bands carry the measured 0.80 P10-P90 coverage rather than a "
                        "parametric assumption. Surplus buckets price the floor/ceiling paths "
                        "through the same convex curve as the mean — the surplus range on a player "
                        "card is the same machinery, never a separate model.",
         "seeAlso": ["p10_p90_bands", "fa_projection_engine", "rational_value"]},
        {"id": "mlb_projections", "term": "MLB Projections (module)",
         "category": "site-feature", "module": ["platform"],
         "aliases": ["projections module", "/projections/"],
         "priority": 85,
         "definition": "The /projections/ surface: the FA module's Gate-1-validated projection "
                       "engine applied to every MLB player with recent history — five-year bWAR "
                       "paths with floor/mean/ceiling probability buckets — plus PROSPX prospects "
                       "joining at their projected ETA via the calibrated FV outcome model.",
         "methodology": "Veterans: the same Marcel engine, aging curves and fitted WAR map the FA "
                        "class board prices contracts with (one engine, gate-checked once, consumed "
                        "twice). Prospects: P(bucket|FV) x per-bucket WAR trajectories scaled by FV "
                        "and shaped by projected debut age — bust-inclusive means, outcome-bucket "
                        "floor/ceiling. Seasons are priced through the convex tier curve at the "
                        "ex-ante FA $/WAR level, escalating per season; veteran surplus exists ONLY "
                        "on salary-known (Spotrac-contracted) seasons and discounts at the platform "
                        "9%; arb/pre-arb seasons carry projections but no surplus claim. Prospect "
                        "surplus is the platform surplus value — never a parallel number.",
         "seeAlso": ["fa_projection_engine", "proj_buckets", "winter_dpw", "surplus_value"]},
    ]
    ids = {e["id"] for e in d["entries"]}
    for e in new_entries:
        if e["id"] not in ids:
            d["entries"].append(e)
    # cross-reference integrity
    idset = {e["id"] for e in d["entries"]}
    for e in d["entries"]:
        if e.get("seeAlso"):
            e["seeAlso"] = [s for s in e["seeAlso"] if s in idset]
    d["version"] = "2026-06-10.2"
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"updated {PATH} — {len(d['entries'])} entries")


if __name__ == "__main__":
    main()
