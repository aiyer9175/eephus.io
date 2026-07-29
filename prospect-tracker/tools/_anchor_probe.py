"""SCRATCH probe: MLB Pipeline data-graph getPlayerEntity per-player grades.

Verifies live HTTP + records samples under .cache/anchor_probe/.
"""
from __future__ import annotations
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

URL = "https://data-graph.mlb.com/graphql"
UA = "eephus.io-prospect-tracker/1.0 (+https://eephus.io; arkndjl@gmail.com)"
OUT = Path(__file__).resolve().parent.parent / ".cache" / "anchor_probe"
OUT.mkdir(parents=True, exist_ok=True)
_last = 0.0


def post(query: str, timeout: int = 30):
    global _last
    w = 1.1 - (time.time() - _last)
    if w > 0:
        time.sleep(w)
    _last = time.time()
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


if __name__ == "__main__":
    q = sys.argv[1]
    st, js = post(q)
    print("HTTP", st)
    print(json.dumps(js)[:4000])
