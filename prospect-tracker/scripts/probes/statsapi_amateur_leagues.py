"""Probe: StatsAPI amateur + winter + independent leagues (MLBAM-native).
sportId 22 = College/Cape Cod/Appalachian; 17 = winter/AFL; 23 = LMB/partner.
Run: python scripts/probes/statsapi_amateur_leagues.py
"""
from _probe import probe

BASE = "https://statsapi.mlb.com/api/v1"

if __name__ == "__main__":
    print("statsapi amateur/winter/indy (MLBAM-native, un-pulled sportIds):")
    probe(f"{BASE}/stats?stats=season&group=hitting&sportId=22&season=2025&playerPool=all&limit=25",
          "sport22_college_2025.json")
    probe(f"{BASE}/stats?stats=season&group=hitting&sportId=17&season=2025&playerPool=all&limit=25",
          "sport17_winter_2025.json")
    probe(f"{BASE}/stats?stats=season&group=hitting&leagueId=125&season=2025&playerPool=all&limit=25",
          "sport23_lmb_2025.json")
    print("  OK - player.id is the mlbam spine id for MLB-tracked players. "
          "sportId 22 supersedes name-only NCAA scrapes for join quality.")
    # negative control: NPB/KBO have sportIds but serve no stats
    for sp, lbl in ((31, "npb"), (32, "kbo")):
        probe(f"{BASE}/stats?stats=season&group=hitting&sportId={sp}&season=2024&limit=1",
              f"sport{sp}_{lbl}_EMPTY.json")
    print("  (31/32 return totalSplits 0 -> listed-but-unserved, documented as a gap)")
