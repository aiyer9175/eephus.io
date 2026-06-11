# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time builder for data/glossary.json - the unified definitions layer.

Extracts the legacy inline PROSPX GLOSSARY + the FA glossary, applies the
Phase-1 copy-audit fixes (docs/glossary-copy-audit.md), restructures the
methodology walls into scannable paragraphs, and registers the new entries
the audit found missing. After this runs once, data/glossary.json is the
CANONICAL hand-edited source - this script is kept for provenance and is
not part of any pipeline.

Slug stability: legacy ids (pwr_plus → POW+, tvi → Sur+, sur_plus → OrgSur+,
farm_report_card → Farm grade tree…) are permalinks (#g=) and are preserved
verbatim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent

# Categories → display groups (mirrors the legacy _GLOSSARY_BASECAT_TO_GROUP
# intent; the unified page navigates by these).
GROUPS = {
    "scouting":      "Prospect Grades & Scouting",
    "definition":    "Prospect Grades & Scouting",
    "custom-index":  "Arkmetrics",
    "farm":          "Arkmetrics",
    "methodology":   "Platform & Methodology",
    "site-feature":  "Platform & Methodology",
    "indicators":    "Badges & Indicators",
    "status":        "Badges & Indicators",
    "hitter-stat":   "Statistical Foundations",
    "pitcher-stat":  "Statistical Foundations",
    "standard-stat": "Statistical Foundations",
    "general-stat":  "Statistical Foundations",
    "statcast":      "Statcast & Tracking",
    "level":         "Levels & Leagues",
    "mlb-rules":     "MLB Rules & Transactions",
    "transactions":  "MLB Rules & Transactions",
    "financial":     "MLB Rules & Transactions",
    "fa":            "Free Agency",
}

FOUNDATION_CATS = {"hitter-stat", "pitcher-stat", "standard-stat", "general-stat",
                   "statcast", "level", "mlb-rules", "transactions", "financial"}

# ---- Phase-1 copy fixes (REWRITE + LIGHT verdicts) --------------------------
DEFINITION_FIXES = {
    "qualifying_offer":
        "One-year contract a club may offer its departing free agent at the mean "
        "of MLB's top-125 salaries (~$21M in 2024). If the player declines and "
        "signs elsewhere, the SIGNING club forfeits draft-pick compensation and "
        "the former club gains a comp pick - the offer itself costs the old club "
        "nothing beyond the one-year salary risk.",
    "two_way_player":
        "Official MLB designation: 20+ MLB innings pitched AND 20+ MLB games "
        "started as a position player or DH with at least 3 plate appearances "
        "in each. Qualifying exempts the player from the pitcher-usage rules "
        "that bar position players from pitching in competitive games.",
    "breakout_indicator":
        "Rare active-prospect flag: tool/FV velocity AND a strong performance "
        "gate, with an age cap. Surfaces roughly 10-40 prospects league-wide.",
    "tool":
        "Unweighted power-mean (p=4) of every scouted 20-80 tool a prospect "
        "carries, plus FG physical grades - the high exponent rewards extreme "
        "tools, so one elite grade lifts the composite more than balanced "
        "mediocrity. Expressed on the 20-80 scouting scale.",
    "upside_indicator":
        "Soft-pink ^ mark in the top-right corner of an FV badge - at least one "
        "source published a '+' upside marker on the latest snapshot.",
    "war":
        "Wins Above Replacement - Baseball-Reference's implementation (bWAR) is "
        "the one WAR source used site-wide. Single-number value estimate "
        "covering offense, defense, baserunning, and position.",
    "free_agency":
        "Players with 6+ years of MLB service may sign with any club once the "
        "World Series ends; the first five days are an exclusive-negotiation "
        "window with the incumbent club and the qualifying-offer period.",
    "il_10_15_60":
        "Three IL durations: 10-day (position players), 15-day (the minimum "
        "for pitchers and two-way players, post-2022), and 60-day, which also "
        "frees the player's 40-man roster spot.",
}

LONG_FIXES = {
    "sur_plus": ("Designed to mirror the wRC+/OPS+ shape",
                 "Mirrors the wRC+/OPS+ shape"),
    "breakout_indicator": ("Designed to surface ~10-40 prospects league-wide",
                           "Tuned to surface ~10-40 prospects league-wide"),
    "trade": ("Note that a fair trade", "A fair trade"),
    "stock_arrow": ("Stock is computed as", "Stock reads as"),
}

# Methodology walls (>130 words, unstructured) - paragraph-break every ~2
# sentences. Content unchanged; presentation becomes scannable.
RESTRUCTURE = {"statcast_plus", "tiebreaker_score", "rps_plus", "tools_dvm_plus",
               "pwr_plus", "tvi", "wag", "farm_report_card",
               "farm_grade_acquisition_strategy", "farm_grade_financial",
               "farm_grade_mlb_production", "eta_half_season", "spotlight_age_cap"}

# ---- New entries the audit found missing ------------------------------------
NEW_ENTRIES = [
    {"id": "rational_value", "term": "Rational value", "category": "fa",
     "aliases": ["rational value", "NPV value"], "priority": 59,
     "definition": "The NPV of a free agent's projected WAR path: aging-curve-decayed, playing-time-weighted production times escalated $/WAR, discounted at the platform's 9% rate. One of the platform's two independently derived numbers - what the production is worth, never what the market will pay.",
     "methodology": "Rational value shares the same NPV currency as PROSPX prospect surplus, which is what lets qualifying-offer pick costs subtract directly and lets a free agent and a prospect be compared on one axis. It is deliberately computed with no reference to the market model: the gap between the two numbers (Contract Surplus) only means something because neither side peeks at the other.",
     "seeAlso": ["contract_surplus", "deal_plus", "m_guarantee"]},
    {"id": "p10_p90_bands", "term": "P10-P90 bands", "category": "fa",
     "aliases": ["bands", "percentile bands"], "priority": 66,
     "definition": "The 10th-90th percentile range shown around every FA market prediction. Empirical residual quantiles from the forward-chained backtest - not parametric intervals, which failed the coverage gate (0.858 vs the 0.75-0.85 target) and were rejected.",
     "seeAlso": ["m_guarantee", "fa_gates"]},
    {"id": "enter_prob", "term": "P(enter)", "category": "fa",
     "aliases": ["enter probability", "exercise probability"], "priority": 67,
     "definition": "Probability that an option-holding player actually reaches the free-agent class, from a documented v1 heuristic: the option price against the player's market anchor through a logistic. Mutual options carry a fixed empirical prior; rows with no anchor show no number rather than a guess.",
     "seeAlso": ["m_guarantee", "cba_carry_forward"]},
    {"id": "cba_carry_forward", "term": "CBA carry-forward", "category": "fa",
     "aliases": ["carry-forward", "carry forward"], "priority": 68,
     "definition": "The 2022 CBA expired 2026-12-01, so every 2027 threshold, tax band, and QO figure is the last known rule carried forward, not a bargained number. Every surface that consumes one of these figures carries the carry-forward flag rather than presenting it as settled.",
     "seeAlso": ["qualifying_offer", "qo_tax"]},
    {"id": "winter_dpw", "term": "$/WAR (winter, ex-ante)", "category": "fa",
     "aliases": ["winter $/WAR", "dollars per WAR"], "priority": 69,
     "definition": "The per-winter price of a win implied by that winter's actual FA signings: guaranteed dollars over projected WAR delivered, carried forward ex-ante so a prediction never sees its own winter. Distinct from the PROSPX $/WAR (tiered) figure, which is a 3-tier rolling market price used for prospect valuation - the two serve different models and are not interchangeable.",
     "seeAlso": ["dollars_per_war", "rational_value"]},
    {"id": "thin_platform", "term": "Thin platform", "category": "fa",
     "aliases": ["thin platform year"], "priority": 70,
     "definition": "Disclosure badge on FA projections whose platform season is missing or injury-shortened - below 30% of a role-aware full season, scaled by how much of the season has elapsed. A projection riding old seasons is the model's weakest case (the Burnes/Bieber rehab class); the badge says so instead of hiding it.",
     "seeAlso": ["rational_value", "m_guarantee"]},
    {"id": "fit_components", "term": "Team-fit components", "category": "fa",
     "aliases": ["need", "window", "afford", "park fit", "behavior prior"], "priority": 71,
     "definition": "The five 0-1 scores behind every FA team fit: need (displacement WAR gap at the position, discounted when a near-ETA PROSPX prospect blocks it), window (marginal playoff leverage at the club's baseline wins), afford (CBT space against the predicted AAV), park (batted-side park factor), and behavior (the club's largest-ever guarantee against the predicted price).",
     "seeAlso": ["m_guarantee", "rational_value"]},
    {"id": "first_seen_dates", "term": "First-seen dates", "category": "fa",
     "aliases": ["observation stamps"], "priority": 72,
     "definition": "Winter events (signings, option decisions, qualifying offers) are dated the day the pipeline first observed them, because the source publishes terms without dates. Stamps are append-only and never revised - the same no-lookahead discipline the models train under.",
     "seeAlso": ["fa_gates"]},
    {"id": "fa_gates", "term": "Gate 1 / Gate 2", "category": "fa",
     "aliases": ["hard gates", "backtest gates"], "priority": 73,
     "definition": "The FA module's two shipping blockers: Gate 1, the projection engine against ten held-out seasons (beat the naive baseline; P10-P90 coverage in 0.75-0.85); Gate 2, the market model against nine forward-chained winters (beat the nearest-comps baseline on guarantee, AAV, and years). Both verdicts render verbatim on the Free Agency Model Accountability page - misses included.",
     "seeAlso": ["p10_p90_bands", "nearest_comps"]},
    {"id": "nearest_comps", "term": "Nearest comps", "category": "fa",
     "aliases": ["comps", "contract comps"], "priority": 74,
     "definition": "The most similar real historical contracts to a free agent's profile, by standardized feature distance over the 2014-15-to-present signing corpus. Always actual deals, never fabricated; they anchor the market model and appear on every board row so a prediction can be sanity-checked against what comparable players actually signed for.",
     "seeAlso": ["m_guarantee", "fa_gates"]},
    {"id": "fa_projection_engine", "term": "FA projection engine", "category": "fa",
     "aliases": ["Marcel", "aging curves"], "priority": 75,
     "definition": "A Marcel-style weighted-rates projection mapped to bWAR through a fitted rate-to-WAR model, decayed along survivorship-corrected aging curves fit on the 2000-2026 corpus. Deliberately conservative on marquee names - a no-lookahead engine cannot price record-setters, and the accountability page says so rather than tuning toward them.",
     "seeAlso": ["war", "rational_value", "fa_gates"]},
    {"id": "era_minus", "term": "ERA-", "category": "pitcher-stat",
     "aliases": ["ERA minus"], "priority": 80,
     "definition": "Park- and league-adjusted ERA scaled so 100 = MLB average; lower is better. 90 reads as 10% better than league; the run-prevention twin of FIP-.",
     "seeAlso": ["fip_minus", "era"]},
    {"id": "woba", "term": "wOBA", "category": "hitter-stat",
     "aliases": ["weighted on-base average"], "priority": 81,
     "definition": "On-base average with each event weighted by its actual run value (a walk is worth less than a double, which OBP ignores). Scaled to look like OBP: ~.320 is league average, .400 elite.",
     "seeAlso": ["wrc_plus", "obp"]},
    {"id": "module_stages", "term": "Module stages (α / β)", "category": "site-feature",
     "aliases": ["alpha", "beta", "stage badges"], "priority": 82,
     "definition": "Lifecycle markers on module names site-wide: α = newly launched, numbers may still shift as the model matures; β = established but in beta. The bordered chip on a module masthead and the superscript in navs are the same marker.",
     "seeAlso": []},
    {"id": "wire_ticker", "term": "WIRE", "category": "site-feature",
     "aliases": ["prospect wire", "ticker"], "priority": 83,
     "definition": "The homepage event feed and scrolling ticker: debuts, promotions, trades, IL moves, real FV changes, and free-agency winter events, each dated and color-coded by type. FV items are real grade changes only - composite movement scores never masquerade as news.",
     "seeAlso": ["stock_arrow", "first_seen_dates"]},
    {"id": "active_pool", "term": "Active prospect pool", "category": "methodology",
     "aliases": ["active pool"], "priority": 84,
     "definition": "The set of currently-tracked, non-graduated MiLB prospects that every ranking, farm grade, and Arkmetric is computed over. Pool integrity is a platform invariant: MLB-side modules (Free Agency) read prospect data read-only and may not write into it.",
     "seeAlso": ["consensus_fv", "debut_rule"]},
]


def _split_wall(text: str) -> str:
    """Insert paragraph breaks every ~2 sentences for the methodology walls."""
    parts = re.split(r"(?<=[.!?]) (?=[A-Z(])", text)
    out, buf = [], []
    for s in parts:
        buf.append(s)
        if len(buf) >= 2 and sum(len(x) for x in buf) > 180:
            out.append(" ".join(buf)); buf = []
    if buf:
        out.append(" ".join(buf))
    return "\n\n".join(out)


def extract_prospx() -> list[dict]:
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    body = re.search(r"const GLOSSARY = \{(.*?)\n\};", src, re.S).group(1)
    entries = []
    for m in re.finditer(r'\n  "([a-z0-9_]+)": \{(.*?)\n  \},', body, re.S):
        slug, blk = m.group(1), m.group(2)

        def g(k):
            mm = re.search(k + r': "((?:[^"\\]|\\.)*)"', blk)
            return mm.group(1).replace('\\"', '"').replace("\\n", "\n") if mm else None

        am = re.search(r"aliases: \[(.*?)\]", blk, re.S)
        aliases = re.findall(r'"((?:[^"\\]|\\.)*)"', am.group(1)) if am else []
        rm = re.search(r"related: \[(.*?)\]", blk, re.S)
        related = re.findall(r'"([a-z0-9_]+)"', rm.group(1)) if rm else []
        pm = re.search(r"priority: (\d+)", blk)
        vm = re.search(r"visual_html: '((?:[^'\\]|\\.)*)'", blk)
        cat = g("category") or "?"
        definition = DEFINITION_FIXES.get(slug, g("short") or "")
        long = g("long") or ""
        if slug in LONG_FIXES:
            long = long.replace(*LONG_FIXES[slug])
        if slug in RESTRUCTURE and long:
            long = _split_wall(long)
        e = {"id": slug, "term": g("name") or slug, "category": cat,
             "module": ["foundations"] if cat in FOUNDATION_CATS
                       else (["platform"] if cat in ("site-feature", "methodology")
                             else ["prospx"]),
             "aliases": aliases, "priority": int(pm.group(1)) if pm else 99,
             "definition": definition}
        if long:
            e["methodology"] = long
        for k in ("formula", "example"):
            v = g(k)
            if v:
                e[k] = v
        if related:
            e["seeAlso"] = related
        if vm:
            e["visual"] = vm.group(1).replace("\\'", "'")
        entries.append(e)
    return entries


def extract_fa() -> list[dict]:
    # FA terms re-keyed to their ORIGINAL prospx-era slugs (permalink continuity).
    fa = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    body = re.search(r"const GLOSSARY = \[(.*?)\n  \];", fa, re.S).group(1)
    SLUGS = {"mGuarantee": "m_guarantee", "mAAV": "m_aav", "mYears": "m_years",
             "Deal+": "deal_plus", "Contract Surplus ($)": "contract_surplus",
             "QO pick tax": "qo_tax"}
    SEE = {"m_guarantee": ["m_aav", "m_years", "deal_plus", "contract_surplus"],
           "m_aav": ["m_guarantee", "m_years"],
           "m_years": ["m_guarantee", "m_aav"],
           "deal_plus": ["contract_surplus", "m_guarantee", "rational_value"],
           "contract_surplus": ["deal_plus", "m_guarantee", "qo_tax", "rational_value"],
           "qo_tax": ["contract_surplus", "qualifying_offer", "fv"]}
    out = []
    pr = 60
    for m in re.finditer(r'\["([^"]+)",\s*\n?\s*"((?:[^"\\]|\\.)*)",\s*\n?\s*"((?:[^"\\]|\\.)*)"\]', body):
        name = m.group(1)
        sid = SLUGS[name]
        out.append({"id": sid, "term": name, "category": "fa", "module": ["fa"],
                    "aliases": [name], "priority": pr,
                    "definition": m.group(2).replace("\\'", "'"),
                    "methodology": m.group(3).replace("\\'", "'"),
                    "seeAlso": SEE[sid]})
        pr += 1
    return out


def main() -> None:
    entries = extract_prospx() + extract_fa()
    for e in NEW_ENTRIES:
        e.setdefault("module", ["fa"] if e["category"] == "fa"
                     else (["platform"] if e["category"] in ("site-feature", "methodology")
                           else ["foundations"]))
        e.setdefault("aliases", [])
    entries += NEW_ENTRIES
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate ids"
    # cross-reference integrity: drop dangling seeAlso targets
    idset = set(ids)
    for e in entries:
        if e.get("seeAlso"):
            e["seeAlso"] = [s for s in e["seeAlso"] if s in idset]
    payload = {"version": "2026-06-10", "groups": GROUPS, "entries": entries}
    out = ROOT / "data" / "glossary.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} - {len(entries)} entries")


if __name__ == "__main__":
    main()
