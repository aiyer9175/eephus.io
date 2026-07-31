"""Probe: MLB StatsAPI draft (official slot pickValue + signingBonus).
Run: python scripts/probes/draft_statsapi.py
"""
from _probe import probe

BASE = "https://statsapi.mlb.com/api/v1"

if __name__ == "__main__":
    print("draft_statsapi:")
    probe(f"{BASE}/draft/2024", "draft_2024_01.json")
    probe(f"{BASE}/draft/prospects/2024", "draft_prospects_2024_02.json")
    probe(f"{BASE}/draft/2016", "draft_2016_coverage_03.json")  # bonus/slot start 2017
    print("  OK - join person.id -> mlbam spine; fields pickValue (slot $), "
          "signingBonus (actual $), pickNumber, school. Bonus/slot 2017+.")
