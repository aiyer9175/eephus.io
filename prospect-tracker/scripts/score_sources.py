"""Score + rank verified data-source candidates for the eFV data-sourcing audit.

Rubric (runbook section 6): weighted 0-5 axes minus penalties; final ranking
metric = weighted_score / eng_days (information gain per engineering-day). Every
candidate here was hit LIVE this session with recorded HTTP evidence + a saved
sample payload under data/sources/samples/ (no fabricated endpoints).

Run: python scripts/score_sources.py
"""
W = {"ortho": 0.20, "efv": 0.18, "history": 0.18, "coverage": 0.13,
     "stability": 0.10, "grain": 0.08, "vintage": 0.08, "freshness": 0.05}

# id: (scores dict, penalties dict, eng_days, one-line note)
# penalties: legal (-2 high / -0.75 ambiguous), match (-1 if <90% join), fragility (-0.5 headless)
C = {
 "tj_surgery_list": (
   dict(ortho=5, efv=3, history=5, coverage=3, stability=3, grain=2, vintage=4, freshness=3),
   dict(legal=0, match=0, fragility=0), 1.0,
   "Tommy John list; native mlbamid 99%, 1974-2026; un-starves the injury-history ledger"),
 "draft_statsapi": (
   dict(ortho=2, efv=3, history=5, coverage=5, stability=5, grain=2, vintage=3, freshness=3),
   dict(legal=0, match=0, fragility=0), 1.0,
   "official pickValue(slot)+signingBonus 2017+, picks to 1965, MLBAM ~100%"),
 "statsapi_venues_meta": (
   dict(ortho=4, efv=2, history=3, coverage=5, stability=5, grain=1, vintage=2, freshness=2),
   dict(legal=0, match=0, fragility=0), 1.0,
   "park elevation/lat-lon/azimuth/dims MLB+MiLB; feeds F-tier normalization"),
 "mlb_pipeline_graphql": (
   dict(ortho=2, efv=4, history=5, coverage=4, stability=3, grain=2, vintage=5, freshness=4),
   dict(legal=0.75, match=0, fragility=0), 1.5,
   "open GraphQL; NATIVE grade vintages 2011-2026 -> de-leak the top pre-debut feature"),
 "statsapi_sport17_23_leagues": (
   dict(ortho=3, efv=2, history=3, coverage=3, stability=5, grain=2, vintage=3, freshness=3),
   dict(legal=0, match=0, fragility=0), 2.0,
   "AFL + Caribbean winter (17) + LMB/partner (23), MLBAM-native"),
 "statsapi_sport22_college": (
   dict(ortho=3, efv=3, history=4, coverage=4, stability=5, grain=2, vintage=3, freshness=4),
   dict(legal=0, match=0, fragility=0), 2.5,
   "NCAA D1 + Cape Cod + Appalachian, MLBAM-native; solves the amateur join"),
 "pitchiq_prospecttilt": (
   dict(ortho=4, efv=3, history=2, coverage=4, stability=2, grain=3, vintage=2, freshness=5),
   dict(legal=0.75, match=0.5, fragility=0), 1.5,
   "MiLB Filth+/Stuff+ model to Complex/DSL + graduates.json; current-season snapshot"),
 "prospect_savant": (
   dict(ortho=3, efv=3, history=2, coverage=3, stability=2, grain=4, vintage=2, freshness=5),
   dict(legal=0.75, match=0, fragility=0), 2.5,
   "AAA Statcast percentiles + bat-tracking + AFL/ST, 2023+; overlaps Savant minors"),
 "statsapi_abs_challenge": (
   dict(ortho=5, efv=2, history=2, coverage=2, stability=4, grain=5, vintage=3, freshness=5),
   dict(legal=0, match=0, fragility=0), 3.5,
   "2026 ABS challenge/overturn per-pitch signal (reviewDetails); needs semantic validation"),
 "awards_statsapi": (
   dict(ortho=2, efv=1, history=5, coverage=3, stability=5, grain=2, vintage=3, freshness=3),
   dict(legal=0, match=0, fragility=0), 1.0,
   "accolades; downstream of WAR (the eFV label) -> weak incremental"),
 "intl_bonus_pools": (
   dict(ortho=2, efv=1, history=3, coverage=2, stability=2, grain=1, vintage=2, freshness=2),
   dict(legal=0, match=1, fragility=0), 0.5,
   "team-level intl pool caps (MLBTR); NO player join -> PROSPX org context only"),
}

def score(s, pen, eng):
    base = sum(W[k] * s[k] for k in W)
    p = pen.get("legal", 0) + pen.get("match", 0) + pen.get("fragility", 0)
    p += 0.25 * max(0, eng - 1)          # eng cost beyond the first day
    return base, base - p

rows = []
for cid, (s, pen, eng, note) in C.items():
    base, net = score(s, pen, eng)
    rows.append((net / eng, net, base, eng, cid, note))
rows.sort(reverse=True)

print(f"{'rank':>4} {'score/eng':>9} {'net':>5} {'raw':>5} {'eng_d':>5}  source")
print("-" * 100)
for i, (ratio, net, base, eng, cid, note) in enumerate(rows, 1):
    print(f"{i:>4} {ratio:>9.2f} {net:>5.2f} {base:>5.2f} {eng:>5.1f}  {cid}")
    print(f"{'':>27}{note}")
print(f"\ntotal eng-days for the recommended set (top 5): "
      f"{sum(r[3] for r in rows[:5]):.1f}")
