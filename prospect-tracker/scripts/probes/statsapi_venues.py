"""Probe: MLB StatsAPI venues metadata (elevation, lat-lon, azimuth, dimensions).
Queryable per sportId (11=AAA .. 16=CPX). Run: python scripts/probes/statsapi_venues.py
"""
from _probe import probe

BASE = "https://statsapi.mlb.com/api/v1"
HYDR = "hydrate=location,fieldInfo,timezone"

if __name__ == "__main__":
    print("statsapi_venues_meta:")
    for sp in (1, 11, 12, 13, 14, 16):
        probe(f"{BASE}/venues?{HYDR}&sportId={sp}", f"venues_sport{sp}.json")
    print("  OK - join venueId -> teams/games; carries location.defaultCoordinates "
          "(lat/lon), location.elevation, fieldInfo dimensions/roofType, azimuthAngle.")
