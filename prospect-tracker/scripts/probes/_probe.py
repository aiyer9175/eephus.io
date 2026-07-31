"""Shared polite-probe helper for the eFV data-source probes.

Every probe records HTTP status + content-type + byte size and writes the raw
payload under data/sources/samples/. Identifying UA, <=1 req/sec/host.
"""
import time
import urllib.request
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sources" / "samples"
UA = {"User-Agent": "eephus-io-datasourcing/1.0 (arkndjl@gmail.com)"}
_last = {"t": 0.0}


def probe(url, sample_name, throttle=1.0):
    """GET url, save body to samples/sample_name, return (status, ctype, bytes)."""
    SAMPLES.mkdir(parents=True, exist_ok=True)
    wait = throttle - (time.time() - _last["t"])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            status = r.status
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body, status, ctype = e.read(), e.code, e.headers.get("Content-Type", "")
    except Exception as e:                                    # noqa: BLE001
        print(f"  UNREACHABLE {url} -> {e}")
        return None, None, None
    finally:
        _last["t"] = time.time()
    (SAMPLES / sample_name).write_bytes(body)
    print(f"  HTTP {status}  {ctype}  {len(body)}B  -> samples/{sample_name}")
    return status, ctype, len(body)
