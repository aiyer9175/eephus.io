# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time builder for data/glossary.json - the unified definitions layer.

Extracts the legacy inline PROSPX GLOSSARY + the FA glossary, applies the
Phase-1 copy-audit fixes (docs/archive/glossary-copy-audit.md), restructures the
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
    "fantasy":       "Fantasy & DFS",
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
     "definition": "The homepage MLB News feed and ticker: MLB and MiLB transactions, debuts, IL moves, eFV changes and FA events, dated, typed by colour and glyph.",
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
     "aliases": ["edge", "model edge"], "priority": 90, "shelf": "foundation",
     "definition": "Model probability minus the de-vigged market probability for the same side of the same bet. A +6% edge means the model gives the side six points more chance than the market does once the book's cut is removed. It is a disagreement, not a profit: the model has to be right about the disagreement for it to be worth anything.",
     "methodology": "Both terms must describe the SAME wager. Books do not all post the same runline or total, so the line is chosen first by book count and prices are shopped only among the books posting it. Pairing one book's line with another book's price for the opposite side once produced a fabricated edge on this site, which is why the pairing is enforced in code and pinned by a test.",
     "seeAlso": ["devig", "implied_probability", "ev_per_unit", "policy_floor"]},
    {"id": "vig", "term": "Vig", "category": "betting",
     "aliases": ["vigorish", "juice", "hold", "overround"], "priority": 91, "shelf": "foundation",
     "definition": "The book's cut, built into the price rather than charged as a fee. Both sides of a coin flip are priced around -110, so the two implied probabilities add to about 105% instead of 100%; that extra 5 points is the vig, also called the hold or the overround.",
     "seeAlso": ["devig", "implied_probability", "fair_line"]},
    {"id": "devig", "term": "De-vig", "category": "betting",
     "aliases": ["de-vig", "devig", "no-vig", "remove the vig", "de-vigged"], "priority": 92, "shelf": "foundation",
     "definition": "Stripping the book's cut back out of a price to recover what the market actually thinks. This site uses the proportional method: divide each side's implied probability by their sum so the pair adds to 100%.",
     "methodology": "The de-vig is always taken from ONE book's two-sided market. Mixing the best price on one side with a different book's price on the other manufactures a fair line with a negative hold, which is a number no market ever offered. The payload names the book each fair line came from for exactly this reason.",
     "seeAlso": ["vig", "fair_line", "bet_edge"]},
    {"id": "fair_line", "term": "Fair line", "category": "betting",
     "aliases": ["fair price", "fair odds"], "priority": 93, "shelf": "foundation",
     "definition": "The price that would exactly match a probability with no cut taken. A 60% chance is a fair line of -150. Two different fair lines appear on the betting board: the model's, from its own probability, and the market's, from the de-vigged book prices.",
     "seeAlso": ["devig", "implied_probability", "bet_edge"]},
    {"id": "implied_probability", "term": "Implied probability", "category": "betting",
     "aliases": ["implied prob", "break-even rate"], "priority": 94, "shelf": "foundation",
     "definition": "The win rate a price needs just to break even. -150 implies 60%, +150 implies 40%. Because the vig is inside the price, the implied probabilities of two opposite sides always sum to more than 100%, which is why they are de-vigged before anything is compared to them.",
     "seeAlso": ["vig", "devig", "fair_line"]},
    {"id": "ev_per_unit", "term": "EV per unit", "category": "betting",
     "aliases": ["expected value", "EV/u"], "priority": 95, "shelf": "foundation",
     "definition": "Expected profit on a one-unit bet under the MODEL's probability: p times the profit if it wins, minus (1 - p) times the unit if it loses. +0.20 means the model expects to make a fifth of a unit per bet on average over many repetitions of the same wager.",
     "methodology": "EV is probability times payout, and payout dominates. Ranking a board by EV alone therefore selects the longest price on it almost every time, which is why the headline Pick of the Day is chosen on model probability inside a normal price band and long prices are judged on EV in their own slot. On a whole-number total the EV is scaled by the share of games that do not push. An EV computed from an unvalidated model is an expectation under an assumption, not a forecast.",
     "seeAlso": ["bet_edge", "kelly_criterion", "betting_unit"]},
    {"id": "betting_unit", "term": "Unit", "category": "betting",
     "aliases": ["unit", "1u", "flat stake"], "priority": 96, "shelf": "foundation",
     "definition": "One bet's worth of bankroll, whatever size a reader chooses. Results are reported in units so they mean the same thing at any bankroll. Every pick on this site's public record is recorded at a flat 1 unit.",
     "methodology": "The stake is flat on the record on purpose. A record kept in variable stakes cannot be audited from its own rows: a reader has to take it on trust that the sizing was decided before the result and not after it. A pick card may show a different suggested size, but the RECORDED stake never changes.",
     "seeAlso": ["kelly_criterion", "ev_per_unit"]},
    {"id": "kelly_criterion", "term": "Kelly", "category": "betting",
     "aliases": ["Kelly criterion", "quarter Kelly", "full Kelly"], "priority": 97, "shelf": "industry",
     "origin": "John L. Kelly Jr. (1956), the Kelly criterion.",
     "definition": "The stake fraction that maximizes long-run bankroll growth given a probability and a price. This site shows it as INFORMATION and never as a stake, and it shows a quarter of it.",
     "methodology": "Full Kelly is only optimal if the probability is right. It is very sensitive to overestimating an edge, and an unvalidated model is by definition a model whose edge estimate has not been checked, so a full-Kelly stake on one of these picks is a fast way to lose a bankroll. Quarter Kelly is served pre-divided so nobody has to do the arithmetic under the impression the site endorsed the larger number.",
     "seeAlso": ["betting_unit", "ev_per_unit", "provisional_pick"]},
    {"id": "moneyline", "term": "Moneyline", "category": "betting",
     "aliases": ["money line", "ML", "h2h"], "priority": 98, "shelf": "foundation",
     "definition": "A bet on which team wins the game, with no margin attached. Priced in American odds: -150 means risk 150 to win 100, +150 means risk 100 to win 150.",
     "seeAlso": ["runline", "total_line", "implied_probability"]},
    {"id": "runline", "term": "Runline", "category": "betting",
     "aliases": ["run line", "spread"], "priority": 99, "shelf": "foundation",
     "definition": "Baseball's spread, almost always 1.5 runs. The favourite at -1.5 has to win by two or more; the underdog at +1.5 wins the bet by losing by one or winning outright.",
     "methodology": "Runline probabilities on this site come from a Poisson-difference margin model, which puts too little weight in the tails: baseball scores in clumps, so the real margin distribution is wider than the model assumes. A one-parameter dispersion correction has a pre-registered gate and is served only if it passes; until then a published runline pick carries the caveat on its row. Games the model leaves tied after nine are split between the two sides at the measured extra-innings home rate.",
     "seeAlso": ["moneyline", "total_line", "run_dispersion"]},
    {"id": "total_line", "term": "Total", "category": "betting",
     "aliases": ["over/under", "the total"], "priority": 100, "shelf": "foundation",
     "definition": "A bet on the combined runs scored by both teams, over or under a posted number. A total that lands exactly on a whole-number line is a push and returns the stake.",
     "methodology": "Totals carry the same Poisson underdispersion as the runline, and the same caveat rides any published total pick. Over 8.5 at one book and Under 9.5 at another are not two sides of one bet, so a total is priced only across books posting the same number.",
     "seeAlso": ["runline", "moneyline", "run_dispersion"]},
    {"id": "parlay", "term": "Parlay", "category": "betting",
     "aliases": ["accumulator", "same-game parlay", "SGP"], "priority": 101, "shelf": "foundation",
     "definition": "One bet chaining several legs, all of which must win. The payout multiplies, and so does the book's cut: a parlay compounds the vig on every leg.",
     "methodology": "Multiplying leg probabilities is only valid when the legs are INDEPENDENT, and legs from the same game never are. The parlay builder blocks a moneyline and a runline on the same team (one bet with two prices) and prints a warning beside the other correlated combinations it knows: legs from the same game, a moneyline with that game's total, two props from one lineup, and a starter's strikeout prop with his team's moneyline.",
     "seeAlso": ["moneyline", "ev_per_unit"]},
    {"id": "clv", "term": "Closing line value", "category": "betting",
     "aliases": ["CLV", "beat the close"], "priority": 102, "shelf": "foundation",
     "definition": "Whether a bet's price when posted beat the same bet's price at the moment the game started. Beating the close means the market moved toward the pick after it was posted.",
     "methodology": "This site stopped serving CLV on 2026-09-07 (owner decision). The record is graded on realized results, and the CLV panels say they are retired rather than printing an empty grade.",
     "seeAlso": ["implied_probability", "provisional_pick"]},
    {"id": "provisional_pick", "term": "Provisional pick", "category": "betting",
     "aliases": ["provisional pick"], "priority": 103, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "A published pick from a model that has NOT cleared its validation gates. No minimum edge has been measured yet, so the pick cleared the policy floor instead, and the card says so.",
     "methodology": "The alternative was showing nothing for a season, and the owner chose to publish with the label instead. Every provisional pick carries the flag, the floor it cleared and the basis of that floor in the payload itself, so a row lifted out of the page is still self-describing. The Validation tab shows which gates are shut and how far each clock has run.",
     "seeAlso": ["policy_floor", "validation_clocks", "brier_score"]},
    {"id": "policy_floor", "term": "Policy floor", "category": "betting",
     "aliases": ["provisional floor", "minimum edge"], "priority": 104, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "The edge a side must clear before it can be published while the model is unvalidated. It is a POLICY, set well above anything the model's measured skill supports, and it is NOT a measurement. Each pick card prints the value it cleared.",
     "methodology": "Requiring a large edge means a pick appears only when the model disagrees with the market by far more than the skill there is evidence for, so the failure mode is publishing nothing on most slates rather than something weak on all of them. Every slot on the page reads this same floor. When the validation gates open, a measured threshold replaces it automatically.",
     "seeAlso": ["provisional_pick", "bet_edge", "validation_clocks"]},
    {"id": "brier_score", "term": "Brier score", "category": "betting",
     "aliases": ["Brier"], "priority": 105, "shelf": "industry",
     "origin": "Glenn W. Brier (1950), verification of probability forecasts.",
     "definition": "The standard accuracy score for probability forecasts: the mean squared error between the stated probability and the outcome (1 or 0). Lower is better, and it rewards being confident only when confidence is warranted.",
     "methodology": "A Brier score means nothing without a baseline scored on the same games, which is what the benchmark ladder provides. It also means nothing if the model saw the games it is being scored on, which is why every graded block on the betting page is labelled with the mode that produced it.",
     "seeAlso": ["benchmark_ladder", "vintage_grading", "reliability_curve"]},
    {"id": "reliability_curve", "term": "Reliability curve", "category": "betting",
     "aliases": ["calibration curve", "reliability diagram"], "priority": 106, "shelf": "foundation",
     "definition": "Forecasts grouped into probability bins, with each bin's average stated probability plotted against how often those bets actually won. A calibrated model sits on the diagonal: its 60% calls win about 60% of the time.",
     "methodology": "The Validation tab draws it from the calibration ledger, beside the bin table it is built from. It is a diagnostic only: no calibration correction is applied to the probabilities the page serves.",
     "seeAlso": ["brier_score", "benchmark_ladder"]},
    {"id": "run_dispersion", "term": "Run-dispersion correction", "category": "betting",
     "aliases": ["dispersion correction", "run dispersion"], "priority": 107, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "A one-parameter widening of the Poisson-difference margin model, which puts too little weight on lopsided scores. It would move runline and total prices, not the moneyline.",
     "methodology": "The correction was fitted and registered against a held-out gate before it was scored. The page reads the gate's verdict from the eval artifact: while the correction is not served, a runline or total price is the plain Poisson difference and the pick row says so. The alpha grid is on the Validation tab.",
     "seeAlso": ["runline", "total_line", "validation_clocks"]},
    {"id": "shadow_ledger", "term": "Shadow ledger", "category": "betting",
     "aliases": ["paper ledger", "paper bets"], "priority": 108, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "Paper bets the model would have made under each candidate selection rule, recorded at board prices and settled against the result. None of them is a published pick, and none counts toward the public record.",
     "methodology": "Each selection rule keeps its own tag and its own ROI. Tags are never pooled, because a combined ROI measures a mixture of rules nobody bet. The settled rows feed Clock B on the Validation tab.",
     "seeAlso": ["validation_clocks", "betting_unit"]},
    {"id": "validation_clocks", "term": "Validation clocks", "category": "betting",
     "aliases": ["gates", "clock A", "clock B"], "priority": 109, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "The counters that decide when the betting model can be called validated. Clock A counts games graded out of sample; Clock B counts settled paper bets per selection rule; Clock C is the gradable pool that caps Clock A.",
     "methodology": "Clock A and Clock B open different gates and are never added together. Until the gates open, picks are provisional and publish against the policy floor.",
     "seeAlso": ["vintage_grading", "shadow_ledger", "provisional_pick"]},
    {"id": "vintage_grading", "term": "Vintage mode", "category": "betting",
     "aliases": ["vintage", "vintage backtest"], "priority": 110, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "The out-of-sample way the betting model is graded: every past game is priced on a dated leaderboard snapshot taken before that game, so no graded game sits inside its own inputs.",
     "methodology": "A game with no earlier snapshot is skipped, not graded on today's numbers. The other mode, contaminated, prices games on season-to-date leaderboards that already contain them; it measures calibration only and cannot validate anything, and the page labels every block with the mode that produced it.",
     "seeAlso": ["validation_clocks", "benchmark_ladder", "brier_score"]},
    {"id": "benchmark_ladder", "term": "Benchmark ladder", "category": "betting",
     "aliases": ["benchmarks"], "priority": 111, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "The model's Brier score beside simpler forecasts scored on the same vintage games: a home-field constant, a published Elo, and the de-vigged market at the open and at the close. Its place on the ladder is the plain answer to whether it knows anything the simpler forecasts do not.",
     "methodology": "Every full tier is scored on one shared window of games, and the panel says so when the model sits last. A tier measured on fewer games renders apart, and a tier with no measurement prints its status instead of a number.",
     "seeAlso": ["brier_score", "vintage_grading"]},
]

# The DFS vocabulary /fantasy/ uses (assets/dfs.js). Same merge rules as the
# betting terms: additive, idempotent, never overwriting a served entry.
DFS_ENTRIES = [
    {"id": "dfs_points_per_1k", "term": "Points per $1k", "category": "fantasy",
     "module": ["fantasy"], "aliases": ["Pts/$1k"], "priority": 120, "shelf": "foundation",
     "definition": "Projected fantasy points per $1,000 of salary. The projection is ours and the salary is the one you entered, so the column fills only for players you priced.",
     "methodology": "Read it with the start rate: a high value on a low start rate is a cheap bench bat.",
     "seeAlso": ["dfs_start_rate", "dfs_matchup_multiplier"]},
    {"id": "dfs_start_rate", "term": "Start rate", "category": "fantasy",
     "module": ["fantasy"], "aliases": ["start"], "priority": 121, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "The projected chance a hitter is in the starting lineup, from his playing-time projection against a league plate-appearances-per-start anchor. A posted lineup card replaces it.",
     "seeAlso": ["dfs_points_per_1k", "dfs_matchup_multiplier"]},
    {"id": "dfs_matchup_multiplier", "term": "Matchup multiplier", "category": "fantasy",
     "module": ["fantasy"], "aliases": ["matchup"], "priority": 122, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io.",
     "definition": "How much the opponent and the park move a projection for one game: the inverse of the opponent's innings-weighted pitching index (the starter's SEM+ plus the club's Bullpen+), times the park factor.",
     "seeAlso": ["dfs_start_rate", "implied_team_total", "sem_plus", "bullpen_plus"]},
    {"id": "implied_team_total", "term": "Implied team total", "category": "fantasy",
     "module": ["fantasy", "betting"], "aliases": ["team total", "team totals", "Opp total"], "priority": 123, "shelf": "foundation",
     "definition": "The market's expected runs for one club: the posted game total split by each side's price with the book's margin removed, from a cached odds snapshot.",
     "methodology": "Shown for context. Nothing on the DFS page is priced off it: the points are our projections.",
     "seeAlso": ["total_line", "devig", "dfs_matchup_multiplier"]},
]


# ---- PROSPX Leaderboards vocabulary (2026-10-02, PROSPX_3_LB_LIBRARY) --------
# The condensed Leaderboards table (sitepass plan 5.2) puts data-gl="<id>" on
# every stat header, and the chip titles that carried their own definitions go
# away with the chips. These are the terms that had no entry. Each one says
# what the site computes, on the basis it computes it, so a header tooltip and
# the number under it agree. Same merge rules as the betting terms: additive,
# idempotent, never overwriting a served entry.
#
# OPS+ lvl and ERA- lvl are not here: ops_plus ("OPS+ (vs level)") and
# era_minus (its MiLB level-relative line) already define them on the served
# basis (K = 200 PA and K = 50 IP), so the headers point at those entries and
# PROSPX_LB_EXTENSIONS gives them the header labels as aliases.
PROSPX_LB_ENTRIES = [
    {"id": "sb", "term": "SB", "category": "hitter-stat",
     "module": ["prospx"], "aliases": ["SB", "Stolen bases", "Steals"],
     "priority": 9, "shelf": "foundation",
     "definition": "Stolen bases: the bases a runner gains by advancing on his own during a pitch, as the official scorer credits them. A season count, not a rate.",
     "methodology": "The PROSPX Leaderboards read it from the MLB Stats API season line at each level, with caught stealing (CS) carried beside it. A combined MiLB row adds the counts of the levels played.",
     "formula": "SB = stolen bases in the season line\nCombined MiLB row: SB = sum over the levels played\nSuccess rate = SB / (SB + CS)",
     "seeAlso": ["sprint_speed"]},
    {"id": "z_swing_pct", "term": "Z-Swing%", "category": "statcast",
     "module": ["prospx"], "aliases": ["Z-Swing", "Zone swing%", "In-zone swing%"],
     "priority": 15, "shelf": "industry",
     "origin": "Industry metric. Plate-discipline rate popularized by FanGraphs (swings at in-zone pitches).",
     "definition": "Share of pitches in the strike zone that the batter swings at. For a hitter it reads how often he offers at hittable pitches; for a pitcher it is the in-zone swing rate he induces.",
     "methodology": "In-zone swings divided by in-zone pitches, counted pitch by pitch from the MLB Stats API game feeds of the player's MiLB games. A pitch is in the zone when the feed labels it so. Where the feed has no zone label, a classifier trained on MLB pitches places it from its plate coordinates and the batter's zone top and bottom. Complex-league games use a model fit on that league's own called strikes and balls. The PROSPX Leaderboards need 200 pitches.",
     "formula": "Z-Swing% = in-zone swings / in-zone pitches x 100\nswing = swinging strike, foul, foul tip, bunt attempt or ball in play",
     "seeAlso": ["z_contact_pct", "chase_pct", "whiff_pct"]},
    {"id": "p90_ev", "term": "90th EV", "category": "statcast",
     "module": ["prospx"], "aliases": ["90th EV", "EV90", "90th percentile exit velocity"],
     "priority": 10, "shelf": "foundation",
     "definition": "The 90th percentile of a hitter's exit velocities, in mph: the speed his hardest tenth of batted balls reaches. It rests on many balls, so one swing moves it less than it moves Max EV.",
     "methodology": "Taken over every tracked batted ball in the MLB Stats API game feeds of the season at that level, with linear interpolation between the two nearest balls. The PROSPX Leaderboards need 10 batted balls.",
     "formula": "90th EV = the value at rank 0.9 x (n - 1) of the sorted exit velocities, interpolated\nn = tracked batted balls",
     "seeAlso": ["exit_velocity", "max_ev", "hard_hit_pct"]},
    {"id": "max_ev", "term": "Max EV", "category": "statcast",
     "module": ["prospx"], "aliases": ["MaxEV", "Maximum exit velocity", "Peak exit velocity"],
     "priority": 10, "shelf": "industry",
     "origin": "Industry metric. MLB Statcast (Baseball Savant) publishes max exit velocity; the MiLB figure here is read from the game feeds.",
     "definition": "The hardest-hit ball of a hitter's season at the level, in mph off the bat.",
     "methodology": "The single highest exit velocity among the tracked batted balls in the MLB Stats API game feeds. One swing sets it, so it tends to rise with the number of batted balls. The PROSPX Leaderboards need 5 batted balls.",
     "formula": "Max EV = max(exit velocity) over tracked batted balls",
     "seeAlso": ["p90_ev", "exit_velocity", "raw_power"]},
    {"id": "pull_air_pct", "term": "Pull-air%", "category": "statcast",
     "module": ["prospx"], "aliases": ["Pull-air", "Pull air%", "Pulled air ball rate"],
     "priority": 11, "shelf": "foundation",
     "definition": "Share of a hitter's batted balls that are fly balls, line drives or popups hit to his pull side.",
     "methodology": "The denominator is every tracked batted ball, not air balls alone. The trajectory comes from the game feed's tag; a ball with no tag counts as in the air at a launch angle of 10 degrees or more. The pull side comes from the hit coordinates: 15 degrees or more toward left field for a right-handed batter, toward right field for a left-handed one. The PROSPX Leaderboards need 10 batted balls.",
     "formula": "Pull-air% = pulled (fly balls + line drives + popups) / batted balls x 100",
     "seeAlso": ["pull_pct", "barrel_pct", "game_power"]},
    {"id": "fb_ivb", "term": "FB IVB", "category": "statcast",
     "module": ["prospx"], "aliases": ["Fastball IVB", "Induced vertical break", "IVB"],
     "priority": 12, "shelf": "industry",
     "origin": "Industry metric. Pitch-tracking measure published by MLB Statcast; the MiLB value here is the game feed's induced vertical break.",
     "definition": "Induced vertical break on a pitcher's main fastball, in inches: the vertical movement the pitch's spin creates, with gravity taken out. A higher number means the ball drops less than gravity alone would make it.",
     "methodology": "The main fastball is the most-thrown of his four-seamers, sinkers, two-seamers and cutters at the level, and the value is that pitch's mean break in the MLB Stats API game feeds. Sinkers and cutters run lower than four-seamers, so the number compares best between pitchers whose main fastball is the same type. The PROSPX Leaderboards need 20 tracked pitches.",
     "formula": "FB IVB = mean(induced vertical break) of the most-thrown pitch type among four-seam, sinker, two-seam and cutter",
     "seeAlso": ["fb_velo", "stf_plus", "vaa"]},
    {"id": "prospx_lb_qualified", "term": "Leaderboard qualifier", "category": "site-feature",
     "module": ["prospx"], "aliases": ["Rate-title qualifier", "Qualified (PROSPX Leaderboards)"],
     "priority": 85, "shelf": "foundation",
     "definition": "A PROSPX Leaderboards season line is qualified when it reaches the minor-league rate-title bar at its level that season: 2.7 plate appearances per team game for a hitter, 0.8 innings per team game for a pitcher.",
     "methodology": "Team games is the median number of completed regular-season games per club at the level that season, read from the MLB Stats API schedule. A combined MiLB row sums its levels and is measured against their team games averaged by exposure: plate appearances for a hitter, outs for a pitcher.",
     "formula": "Hitter: qualified when PA >= 2.7 x team games\nPitcher: qualified when IP >= 0.8 x team games\nCombined MiLB row: team games = sum(exposure x level team games) / sum(exposure), exposure = PA (hitter) or outs (pitcher)",
     "seeAlso": ["ops_plus", "era_minus"]},
    {"id": "xwoba_est", "term": "Est. xwOBA (PROSPX)", "category": "statcast",
     "module": ["prospx"], "aliases": ["Est. xwOBA", "Est. xwOBAcon", "xwOBA est", "xwOBAcon est", "Estimated xwOBA"],
     "priority": 50, "shelf": "ark",
     "origin": "Arkmetric, created by Noah J. Dengler, original to eephus.io. The nearest-neighbour shape follows the public TJStats (Thomas Nestico) approach of predicting batted-ball outcomes from launch speed and angle.",
     "definition": "The site's estimate of expected wOBA for MiLB hitters, built from the launch speed and launch angle of each tracked batted ball. It is a different number from MLB's Statcast xwOBA and comes from a different model.",
     "methodology": "The estimator is a k-nearest-neighbour average with k = 61. Each batted ball takes its value from the 61 nearest points of a fixed grid of launch speed and angle outcomes, weighted by inverse distance. The grid scores an out at 0 and a single, double, triple and home run at their wOBA weights. It encodes public batted-ball priors, and no Statcast training data ships with it.\n\nThe mean over a hitter's batted balls is Est. xwOBAcon. At 25 or more balls a bounded profile correction lifts barrel-heavy and hard ground-ball profiles and caps soft-contact ones. Est. xwOBA then adds plate results from the level's BB% and K%: walks at 0.69, strikeouts at zero, and Est. xwOBAcon on the remaining plate appearances. Hit-by-pitch is left out because several MiLB lines lack it. The PROSPX Leaderboards need 25 batted balls.",
     "formula": "per ball: v = sum(w_i x value_i) / sum(w_i) over the 61 nearest grid points\nw_i = 1 / (d_i + 0.75), d_i = ((EV - EV_i) / 4)^2 + ((LA - LA_i) / 8)^2\ngrid values: out 0, 1B 0.88, 2B 1.25, 3B 1.58, HR 2.03\nEst. xwOBAcon = mean(v) over batted balls + profile correction (25+ balls, bounded at -0.45 and +0.08)\nEst. xwOBA = 0.69 x BB rate + (1 - BB rate - K rate) x Est. xwOBAcon",
     "seeAlso": ["xwoba", "woba", "exit_velocity", "barrel_pct"]},
]

# Served entries the Leaderboards headers point at, given what they lack for
# that use: the header label as an alias, the PROSPX module badge, and one
# appended paragraph (a pitcher line, or the combined-row basis). Each append
# lands once: the merge looks for the paragraph before adding it.
PROSPX_LB_EXTENSIONS = {
    "ops_plus": {
        "aliases": ["OPS+ lvl"], "module": ["prospx"],
        "methodology": "On a combined MiLB row of the PROSPX Leaderboards each level keeps its own rescaled weights, and the baseline is the league wOBA of the levels played, weighted by plate appearances."},
    "era_minus": {
        "aliases": ["ERA- lvl"], "module": ["prospx"],
        "methodology": "On a combined MiLB row of the PROSPX Leaderboards the level ERA is the mean of the levels played, weighted by innings."},
    "z_contact_pct": {
        "aliases": ["Z-Con%"], "module": ["prospx"],
        "methodology": "For a pitcher it is the in-zone contact he allows per in-zone swing, and lower is better. The PROSPX Leaderboards count it from the MiLB game feeds on the zone rule Z-Swing% describes, with 200 pitches needed."},
    "chase_pct": {
        "aliases": ["Chase%"], "module": ["prospx"],
        "methodology": "For a pitcher it is the chase rate he induces, and higher is better."},
    "exit_velocity": {
        "aliases": ["Avg EVa"], "module": ["prospx"],
        "methodology": "For a pitcher (Avg EVa on the PROSPX Leaderboards) it is the same mean over the batted balls he allows, and lower is better."},
    "hard_hit_pct": {
        "aliases": ["Hard%", "HardA%"], "module": ["prospx"],
        "methodology": "For a pitcher (HardA% on the PROSPX Leaderboards) it is the same rate over the batted balls he allows, and lower is better."},
    "barrel_pct": {
        "aliases": ["BrlA%"], "module": ["prospx"],
        "methodology": "On MiLB tracked data the site approximates the band: 98 mph or more, at a launch angle from 26 to 30 degrees that widens by one degree each way per mph above 98, capped at 50 degrees. For a pitcher (BrlA% on the PROSPX Leaderboards) it is the same rate over the batted balls he allows, and lower is better."},
    "fb_velo": {
        "module": ["prospx"],
        "methodology": "The PROSPX Leaderboards print a separate MiLB figure: the mean speed of the pitcher's most-thrown fastball type (four-seam, sinker, two-seam or cutter) in the MLB Stats API game feeds, with 20 tracked pitches needed."},
    "fin_dollar_dvm": {
        "aliases": ["$DvM+"]},
    "xwoba": {
        "seeAlso": ["xwoba_est"],
        "replace": ("methodology",
                    "The value on player cards is our reconstruction from the tracking inputs available, not the official Savant figure.",
                    "PROSPX prints a different number for MiLB hitters, the site's own estimate from launch speed and angle: see Est. xwOBA (PROSPX).")},
}


def _write_payload(out: Path, payload: dict) -> None:
    """Write the glossary keeping the served file's own line endings and
    trailing newline, so a merge diffs as the changed entries and nothing else."""
    raw = out.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if raw.endswith(b"\n"):
        text += "\n"
    out.write_bytes(text.replace("\n", eol).encode("utf-8"))


def _sectioned(e: dict, groups: dict) -> dict:
    """The entry with its term shelf (`section`, LIBRARY_4) placed after
    `category`, by the one rule in tools/glossary_sections.py."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from glossary_sections import _insert_after, section_for
    return _insert_after(e, "category", "section", section_for(e, groups))


def merge_prospx_lb(path: Path | None = None) -> dict:
    """Add the PROSPX Leaderboards vocabulary to the EXISTING data/glossary.json.

    Same contract as merge_betting: additive and idempotent. A new entry is
    added only when its id is absent. An extension adds a missing alias, module
    badge or seeAlso id, appends its paragraph when that paragraph is not
    already in the field, and swaps a sentence only while the old sentence is
    still there, so a second run writes nothing."""
    out = Path(path or (ROOT / "data" / "glossary.json"))
    payload = json.loads(out.read_text(encoding="utf-8"))
    entries = payload.setdefault("entries", [])
    by_id = {e["id"]: e for e in entries}
    added, extended = [], []
    for e in PROSPX_LB_ENTRIES:
        if e["id"] in by_id:
            continue
        e = _sectioned(json.loads(json.dumps(e)), payload.get("groups") or GROUPS)
        entries.append(e)
        by_id[e["id"]] = e
        added.append(e["id"])
    for eid, ext in PROSPX_LB_EXTENSIONS.items():
        e = by_id.get(eid)
        if e is None:
            continue
        before = json.dumps(e, sort_keys=True)
        for key in ("aliases", "module", "seeAlso"):
            for v in ext.get(key) or []:
                have = e.setdefault(key, [])
                if v not in have:
                    have.append(v)
        para = ext.get("methodology")
        if para and para not in (e.get("methodology") or ""):
            e["methodology"] = (e["methodology"] + "\n\n" + para) if e.get("methodology") else para
        if ext.get("replace"):
            field, old, new = ext["replace"]
            if old in (e.get(field) or ""):
                e[field] = e[field].replace(old, new)
        if json.dumps(e, sort_keys=True) != before:
            extended.append(eid)
    idset = {e["id"] for e in entries}
    for e in entries:
        if e.get("seeAlso"):
            e["seeAlso"] = [s for s in e["seeAlso"] if s in idset]
    if added or extended:
        payload["version"] = glossary_version()
        _write_payload(out, payload)
    return {"added": added, "extended": extended, "n_entries": len(entries)}


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
    """Add the betting and DFS vocabulary to the EXISTING data/glossary.json in place.

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
    for e in BETTING_ENTRIES + DFS_ENTRIES:
        if e["id"] in have:
            continue
        e = {**e, "module": e.get("module") or [e.get("category") or "betting"]}
        e = _sectioned(e, {**GROUPS, **(payload.get("groups") or {})})
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
        # Keep the served file's own line endings and trailing newline, so a
        # merge diffs as the added entries and nothing else.
        raw = out.read_bytes()
        eol = "\r\n" if b"\r\n" in raw else "\n"
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        if raw.endswith(b"\n"):
            text += "\n"
        out.write_bytes(text.replace("\n", eol).encode("utf-8"))
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
    ap.add_argument("--prospx-lb", action="store_true",
                    help="merge the PROSPX Leaderboards vocabulary into the "
                         "existing data/glossary.json (safe, idempotent, additive)")
    ap.add_argument("--rebuild", action="store_true",
                    help="DESTRUCTIVE one-time rebuild from the legacy inline "
                         "sources; prospx/index.html no longer carries its "
                         "GLOSSARY block, so this will fail")
    args = ap.parse_args()
    if args.betting:
        print(merge_betting())
    elif args.prospx_lb:
        print(merge_prospx_lb())
    elif args.rebuild:
        main()
    else:
        ap.error("pass --betting or --prospx-lb to register those terms; --rebuild is "
                 "the legacy one-time path and would replace the canonical "
                 "artifact")
