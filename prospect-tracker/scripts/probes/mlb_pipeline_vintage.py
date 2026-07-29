"""Probe: MLB Pipeline vintage boards via the open GraphQL host.
Native point-in-time Top-100 boards 2011-2026, keyed on mlbam. No auth.
Run: python scripts/probes/mlb_pipeline_vintage.py
"""
import json
import urllib.request
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sources" / "samples"
URL = "https://data-graph.mlb.com/graphql"
UA = {"User-Agent": "eephus-io-datasourcing/1.0", "Content-Type": "application/json"}

# getPlayerRankingsFromSelection(slug: sel-pr-YYYY-top100) -> ranked players w/ mlbam id
def _query(slug):
    q = ('{getPlayerRankingsFromSelection(limit:100,slug:"%s")'
         '{rank playerEntity{position eta player{id fullName}}}}' % slug)
    body = json.dumps({"query": q}).encode()
    req = urllib.request.Request(URL, data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

if __name__ == "__main__":
    print("mlb_pipeline_graphql (vintage boards):")
    SAMPLES.mkdir(parents=True, exist_ok=True)
    for yr in (2021, 2026):
        try:
            st, ct, body = _query(f"sel-pr-{yr}-top100")
            (SAMPLES / f"mlbpipeline_vintage{yr}.json").write_bytes(body)
            top = (json.loads(body).get("data", {})
                   .get("getPlayerRankingsFromSelection") or [{}])[0]
            print(f"  {yr}: HTTP {st} {len(body)}B  #1 = "
                  f"{top.get('playerEntity',{}).get('player',{}).get('fullName')}")
        except Exception as e:                               # noqa: BLE001
            print(f"  {yr}: UNREACHABLE -> {e}")
    print("  NOTE: tool-grade subfields (PlayerEntityGrades) are lazy/hidden; "
          "introspection disabled -> ~0.5d XHR capture to enumerate them.")
