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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent


def glossary_version() -> str:
    """Single source for the data/glossary.json version stamp (audit F-03).

    The stamp is the build date: it moves exactly when a glossary builder
    rewrites the payload, never by hand. Every build_glossary_*.py script
    that writes the payload imports this instead of setting a literal.
    """
    return date.today().isoformat()

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
    "betting":       "Betting & Markets",
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
    # wRC+ - INDUSTRY entry, re-homed here 2026-07-31.
    #
    # The slug already exists in data/glossary.json (priority 5, category
    # hitter-stat, shelf "industry"), inherited from the legacy inline PROSPX
    # GLOSSARY. That block no longer exists in prospx/index.html, so
    # extract_prospx() can no longer produce this entry and this list is now its
    # only registration; there is no duplicate-id risk against the assert in
    # main(). data/glossary.json remains the CANONICAL hand-edited payload, so
    # this copy is the provenance of record, not the served text.
    #
    # Sharpened for the MLB Stats hitter board's new wRC+ column: the entry now
    # says explicitly that the number is displayed and not derived, which is what
    # keeps it consistent with the site's "derives no wRC+" disclosure.
    {"id": "wrc_plus", "term": "wRC+", "category": "hitter-stat",
     "module": ["foundations"], "shelf": "industry", "priority": 5,
     "aliases": ["wRC+", "Weighted Runs Created Plus"],
     "definition": "League- and park-adjusted offensive value, published by MLB. 100 = MLB average, 120 is 20% above, 80 is 20% below. Displayed on this site, never derived by it: the MLB Stats hitter board reads MLB's published figure verbatim and shows it beside HEM+, the offense-rate index the site does compute.",
     "methodology": "Read verbatim from MLB's bulk season-total feed and matched by player id, so a traded hitter reads one season line rather than a single stint, and two internal name keys that collide on the same player cannot produce two different numbers. MLB-only; MiLB equivalents use the level-relative RPS+ proxy instead. It runs wider than HEM+ because it is unshrunk: measured over the pooled 2021-2026 qualified pools (2,069 hitter-seasons), published wRC+ has a standard deviation of 25.3 against HEM+ at 17.7, which is why the two columns are colored on different thresholds rather than sharing one set. The wRC+ column bands at 85, 120 and 145, the round numbers that reproduce the HEM+ band shares on the wider wRC+ distribution.",
     "origin": "Industry metric. Linear-weights framework by Tom Tango and coauthors (The Book); wRC+ implemented by FanGraphs and published by MLB. We display it as the offensive baseline next to our own metrics and compute no version of it.",
     "seeAlso": ["hem_plus", "rps_plus", "ops"]},
    {"id": "active_pool", "term": "Active prospect pool", "category": "methodology",
     "aliases": ["active pool"], "priority": 84,
     "definition": "The set of currently-tracked, non-graduated MiLB prospects that every ranking, farm grade, and Arkmetric is computed over. Pool integrity is a platform invariant: MLB-side modules (Free Agency) read prospect data read-only and may not write into it.",
     "seeAlso": ["consensus_fv", "debut_rule"]},
]

# ---- Betting vocabulary (2026-08-07) ----------------------------------------
# WHY THESE ARE HERE. assets/betting.js leaves every one of these words as plain
# text, and says so in a comment at its gl() helper: pointing a tooltip at a
# near-miss slug on a page about money is a worse failure than no tooltip. The
# betting module is the only surface on the site where a reader can be led into
# a decision by a term he half-understands, so the vocabulary needs its own
# group rather than being scattered into the statistical foundations.
#
# EVERY DEFINITION HERE DESCRIBES WHAT THE SITE ACTUALLY DOES, not the general
# industry meaning. `policy_floor` and `provisional_pick` in particular exist
# because the module publishes picks against a threshold nobody has measured
# yet, and a glossary that explained "minimum edge" in the abstract would let a
# reader assume the number was fitted.
BETTING_ENTRIES = [
    {"id": "bet_edge", "term": "Edge", "category": "betting",
     "aliases": ["edge", "model edge"], "priority": 90,
     "definition": "Model probability minus the de-vigged market probability for the same side of the same bet. A +6% edge means the model gives the side six points more chance than the market does once the book's cut is removed. It is a disagreement, not a profit: the model has to be right about the disagreement for it to be worth anything.",
     "methodology": "Both terms must describe the SAME wager. Books do not all post the same runline or total, so the line is chosen first by book count and prices are shopped only among the books posting it. Pairing one book's line with another book's price for the opposite side once produced a fabricated 38.8 point edge on this site, which is why the pairing is now enforced in code and pinned by a test.",
     "seeAlso": ["devig", "implied_probability", "ev_per_unit", "policy_floor"]},
    {"id": "vig", "term": "Vig", "category": "betting",
     "aliases": ["vigorish", "juice", "hold", "overround"], "priority": 91,
     "definition": "The book's cut, built into the price rather than charged as a fee. Both sides of a coin flip are priced around -110, so the two implied probabilities add to about 105% instead of 100%; that extra 5 points is the vig, also called the hold or the overround.",
     "seeAlso": ["devig", "implied_probability", "fair_line"]},
    {"id": "devig", "term": "De-vig", "category": "betting",
     "aliases": ["de-vig", "devig", "no-vig", "remove the vig"], "priority": 92,
     "definition": "Stripping the book's cut back out of a price to recover what the market actually thinks. This site uses the proportional method: divide each side's implied probability by their sum so the pair adds to 100%.",
     "methodology": "The de-vig is always taken from ONE book's two-sided market. Mixing the best price on one side with a different book's price on the other manufactures a fair line with a negative hold, which is a number no market ever offered. The payload names the book each fair line came from for exactly this reason.",
     "seeAlso": ["vig", "fair_line", "bet_edge"]},
    {"id": "fair_line", "term": "Fair line", "category": "betting",
     "aliases": ["fair price", "fair odds"], "priority": 93,
     "definition": "The price that would exactly match a probability with no cut taken. A 60% chance is a fair line of -150. Two different fair lines appear on the betting board: the model's, from its own probability, and the market's, from the de-vigged book prices.",
     "seeAlso": ["devig", "implied_probability", "bet_edge"]},
    {"id": "implied_probability", "term": "Implied probability", "category": "betting",
     "aliases": ["implied prob", "break-even rate"], "priority": 94,
     "definition": "The win rate a price needs just to break even. -150 implies 60%, +150 implies 40%. Because the vig is inside the price, the implied probabilities of two opposite sides always sum to more than 100%, which is why they are de-vigged before anything is compared to them.",
     "seeAlso": ["vig", "devig", "fair_line"]},
    {"id": "ev_per_unit", "term": "EV per unit", "category": "betting",
     "aliases": ["expected value", "EV", "EV/u"], "priority": 95,
     "definition": "Expected profit on a one-unit bet under the MODEL's probability: p times the profit if it wins, minus (1 - p) times the unit if it loses. +0.20 means the model expects to make a fifth of a unit per bet on average over many repetitions of the same wager.",
     "methodology": "EV is probability times payout, and payout dominates. Ranking a board by EV alone therefore selects the longest price on it almost every time, which is why the headline Pick of the Day is chosen on model probability inside a normal price band and long prices are judged on EV in their own slot. An EV computed from an unvalidated model is an expectation under an assumption, not a forecast.",
     "seeAlso": ["bet_edge", "kelly_criterion", "betting_unit"]},
    {"id": "betting_unit", "term": "Unit", "category": "betting",
     "aliases": ["unit", "1u", "flat stake"], "priority": 96,
     "definition": "One bet's worth of bankroll, whatever size a reader chooses. Results are reported in units so they mean the same thing at any bankroll. Every pick on this site's public record is a flat 1 unit.",
     "methodology": "The stake is flat on the record on purpose. A record kept in variable stakes cannot be audited from its own rows: a reader has to take it on trust that the sizing was decided before the result and not after it. Suggested display units may differ by slot, but the RECORDED stake never does.",
     "seeAlso": ["kelly_criterion", "ev_per_unit"]},
    {"id": "kelly_criterion", "term": "Kelly", "category": "betting",
     "aliases": ["Kelly criterion", "quarter Kelly", "full Kelly"], "priority": 97,
     "definition": "The stake fraction that maximizes long-run bankroll growth given a probability and a price. This site shows it as INFORMATION and never as a recommendation, and it shows a quarter of it.",
     "methodology": "Full Kelly is only optimal if the probability is right. It is brutally sensitive to overestimating an edge, and an unvalidated model is by definition a model whose edge estimate has not been checked, so a full-Kelly stake on one of these picks is a fast way to lose a bankroll. Quarter Kelly is served pre-divided so nobody has to do the arithmetic under the impression the site endorsed the larger number.",
     "seeAlso": ["betting_unit", "ev_per_unit", "provisional_pick"]},
    {"id": "moneyline", "term": "Moneyline", "category": "betting",
     "aliases": ["money line", "ML", "h2h"], "priority": 98,
     "definition": "A bet on which team wins the game, with no margin attached. Priced in American odds: -150 means risk 150 to win 100, +150 means risk 100 to win 150.",
     "seeAlso": ["runline", "total_line", "implied_probability"]},
    {"id": "runline", "term": "Runline", "category": "betting",
     "aliases": ["run line", "spread"], "priority": 99,
     "definition": "Baseball's spread, almost always 1.5 runs. The favourite at -1.5 has to win by two or more; the underdog at +1.5 wins the bet by losing by one or winning outright.",
     "methodology": "Runline probabilities on this site come from a Poisson-difference margin model, which underdisperses real run scoring: baseball scores in clumps, so the true margin distribution has fatter tails than the model assumes and its runline numbers sit too close to the middle. The moneyline is the least exposed of the three markets, and any published runline pick carries that caveat on the row. A second, separate error: the runline counts every game the model leaves tied after nine as a +1.5 cover for both sides, while the moneyline splits the same games by the measured extra-innings home rate, so a +1.5 price runs high and a -1.5 price runs low. The measured split is published and not yet served, and a published runline pick states what it would change.",
     "seeAlso": ["moneyline", "total_line"]},
    {"id": "total_line", "term": "Total", "category": "betting",
     "aliases": ["over/under", "the total"], "priority": 100,
     "definition": "A bet on the combined runs scored by both teams, over or under a posted number. A total that lands exactly on a whole-number line is a push and returns the stake.",
     "methodology": "Totals carry the same Poisson underdispersion as the runline, and the same caveat rides any published total pick. Over 8.5 at one book and Under 9.5 at another are not two sides of one bet, so a total is priced only across books posting the same number.",
     "seeAlso": ["runline", "moneyline"]},
    {"id": "parlay", "term": "Parlay", "category": "betting",
     "aliases": ["accumulator", "same-game parlay", "SGP"], "priority": 101,
     "definition": "One bet chaining several legs, all of which must win. The payout multiplies, and so does the book's cut: a parlay compounds the vig on every leg.",
     "methodology": "Multiplying leg probabilities is only valid when the legs are INDEPENDENT, and legs from the same game never are. This site refuses to print a product for correlated legs rather than printing one with a warning attached, because a number that looks like a price is read as a price no matter what sits next to it.",
     "seeAlso": ["moneyline", "ev_per_unit"]},
    {"id": "clv", "term": "Closing line value", "category": "betting",
     "aliases": ["CLV", "beat the close"], "priority": 102,
     "definition": "Whether a bet's price at post beat the same bet's price at the moment the game started. Beating the close means the market moved toward the pick after it was posted.",
     "methodology": "CLV is the honest short-run test of a betting model, because the closing line is the sharpest estimate the market produces and winning a single bet is evidence of almost nothing. This site publishes two forms side by side: price CLV, the posted decimal over the closing decimal minus one, and probability CLV, the implied probability at close minus at post.",
     "seeAlso": ["implied_probability", "provisional_pick"]},
    {"id": "provisional_pick", "term": "Provisional pick", "category": "betting",
     "aliases": ["provisional"], "priority": 103,
     "definition": "A published pick from a model that has NOT been validated. The betting model's backtest is contaminated (its team inputs are season-to-date, so every graded game sits inside its own features), so no minimum edge has been measured and no pick here has a measured threshold behind it.",
     "methodology": "The alternative was showing nothing for a season, and the owner chose to publish with the label instead. Every provisional pick carries the flag, the floor it cleared and the basis of that floor in the payload itself, so a row lifted out of the page is still self-describing. Each one is also recorded in a paper ledger that settles against the result, which is how the evidence for a real threshold gets built.",
     "seeAlso": ["policy_floor", "brier_score", "clv"]},
    {"id": "policy_floor", "term": "Policy floor", "category": "betting",
     "aliases": ["provisional floor", "minimum edge"], "priority": 104,
     "definition": "The 6% edge a side must clear before it can be published while the model is unvalidated. It is a POLICY, chosen to be far stricter than anything the model can currently justify, and it is NOT a measurement.",
     "methodology": "The model's whole in-sample margin over a home-field baseline is 0.0079 Brier, and the out-of-sample margin will be thinner. Requiring six points of edge means a pick appears only when the model disagrees with the market by far more than the skill there is evidence for, so the failure mode is publishing nothing on most slates rather than something weak on all of them. Every slot on the page reads this same floor: a slot allowed to quietly use a lower one would be a threshold invented to make a pick appear, which is the single most dishonest number this module could publish. When the validation gates open, a measured threshold replaces it automatically.",
     "seeAlso": ["provisional_pick", "bet_edge", "brier_score"]},
    {"id": "brier_score", "term": "Brier score", "category": "betting",
     "aliases": ["Brier"], "priority": 105,
     "definition": "The standard accuracy score for probability forecasts: the mean squared error between the stated probability and the outcome (1 or 0). Lower is better, and it rewards being confident only when confidence is warranted.",
     "methodology": "A Brier score means nothing without the baseline it is compared against, and this site prints two: a flat 50% forecast and a home-field-only forecast. It also means nothing if the model saw the games it is being scored on, which is why every graded block on the betting page is labelled with the mode that produced it.",
     "seeAlso": ["provisional_pick", "policy_floor"]},
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


def merge_betting(path: Path | None = None) -> dict:
    """Add the betting vocabulary to the EXISTING data/glossary.json in place.

    WHY THIS IS NOT PART OF main(). `main()` rebuilds the whole payload from
    prospx/index.html's inline `const GLOSSARY` block, and that block no longer
    exists: extract_prospx() would raise on the missing match, and if it did not
    it would replace a 288-entry hand-edited artifact with whatever it could
    still scrape. The artifact has been the canonical source since this script
    ran once, so the only safe way to register new terms is to merge them into
    what is on disk.

    Idempotent, and it never overwrites an entry that is already there: the
    served copy is the one a human may have edited, and this script is
    provenance, not authority. Returns what it did so a caller can log it."""
    out = Path(path or (ROOT / "data" / "glossary.json"))
    payload = json.loads(out.read_text(encoding="utf-8"))
    have = {e["id"] for e in payload.get("entries") or []}
    added = []
    for e in BETTING_ENTRIES:
        if e["id"] in have:
            continue
        e = {**e, "module": e.get("module") or ["betting"]}
        payload.setdefault("entries", []).append(e)
        added.append(e["id"])
    groups = payload.setdefault("groups", {})
    for cat, label in GROUPS.items():
        groups.setdefault(cat, label)
    # Dangling cross-references render as a link to nothing, so they are dropped
    # here on the same rule main() applies.
    idset = {e["id"] for e in payload["entries"]}
    for e in payload["entries"]:
        if e.get("seeAlso"):
            e["seeAlso"] = [s for s in e["seeAlso"] if s in idset]
    if added:
        payload["version"] = glossary_version()
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return {"added": added, "n_entries": len(payload["entries"]),
            "group": GROUPS["betting"]}


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
    payload = {"version": glossary_version(), "groups": GROUPS, "entries": entries}
    out = ROOT / "data" / "glossary.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} - {len(entries)} entries")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--betting", action="store_true",
                    help="merge the betting vocabulary into the existing "
                         "data/glossary.json (safe, idempotent, additive)")
    ap.add_argument("--rebuild", action="store_true",
                    help="DESTRUCTIVE one-time rebuild from the legacy inline "
                         "sources; prospx/index.html no longer carries its "
                         "GLOSSARY block, so this will fail")
    args = ap.parse_args()
    if args.betting:
        print(merge_betting())
    elif args.rebuild:
        main()
    else:
        ap.error("pass --betting to register the betting terms; --rebuild is "
                 "the legacy one-time path and would replace the canonical "
                 "artifact")
