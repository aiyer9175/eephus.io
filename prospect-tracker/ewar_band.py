# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The eWAR uncertainty band as served: the +/- beside eWAR and eWAR realized.

docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md (task EWAR_UNCERTAINTY_BAND, owner decision
EW3-50). The read (part 13.2) recorded PASS under amendment 13.1; this module builds the
band DARK behind BAND_LIVE (default False) and the owner's answer to EWUB-Q1 decides the
flip. While the flag is off nothing here changes a served file: `half_width()` returns
None, so every consumer emits exactly what it emitted before, and `python ewar_band.py`
writes only the preview under .cache/ewar_v3/preview/.

The band (gate part 2.1), for one player-season and one series, from the constants the
read fixed on its training seasons (k per term, an sd multiplier per exposure band):

    sigma^2 = [m_bat^2 k_bat PA + m_ebr^2 k_ebr PA + m_pit^2 k_pit IP] / RPW_s^2
              + m_src,bat^2 k_src,bat PA + m_src,pit^2 k_src,pit IP
    band    = eWAR +/- 1.2816 sigma       (a nominal 80 percent band)

k_pit is k_fip on the headline eWAR and k_ra on an eWAR realized pitcher-season that
carries the realized pitching basis R2. A side below its floor (20 PA, 5 IP) carries no
term, and a row with no side above its floor carries no band.

What the band is and is not (gate part 10, amendment 13.1): on seasons held out from
its constants it covered the other published WAR and a split-half rescaled season at a
rate between 70 and 90 percent in every playing-time band. It is not a confidence
interval for talent and makes no claim about where a player's true value lies.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import sys
from pathlib import Path

import ewar_uncertainty_band as U

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "ewar_band.json"
PREVIEW = ROOT / ".cache" / "ewar_v3" / "preview" / "ewar_band.json"
RECORD = ROOT / "data" / "_labs" / "ewar_uncertainty_band" / "record.json"
GATE_DOC = U.GATE_DOC

#: The flip (owner question EWUB-Q1). Off: no consumer prints a band.
BAND_LIVE = False

#: Decimals the +/- prints with, as eWAR itself.
DECIMALS = 1

_CACHE: dict | None = None
_R2: set | None = None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ the artifact
def build(record: dict | None = None) -> dict:
    """The served constants from the read's record; refuses unless the read recorded PASS."""
    raw = RECORD.read_bytes() if record is None else None
    rec = json.loads(raw.decode("utf-8")) if record is None else record
    if rec.get("disposition") != "PASS":
        raise U.BandRefusal(f"the read recorded {rec.get('disposition')!r}, not PASS: nothing is built")
    consts = rec["constants"]
    for term in U.TERM_FAMILY:
        k = float(consts["k"][term])
        if not (math.isfinite(k) and k > 0) or len(consts["m"][term]) != 4:
            raise U.BandRefusal(f"constant {term} is not usable")
    cov = {}
    for c in rec.get("cells") or []:
        cov.setdefault(c["family"], []).append(round(float(c["coverage"]), 3))
    return {
        "schema": 1, "model": "ewar_band", "generated_at": _now(), "gate": GATE_DOC,
        "record": "data/_labs/ewar_uncertainty_band/record.json",
        "record_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "nominal": 0.8, "z": U.Z80, "decimals": DECIMALS,
        "floors": dict(U.FLOOR), "edges": {k: list(v) for k, v in U.EDGES.items()},
        "constants": {"k": {t: float(v) for t, v in consts["k"].items()},
                      "m": {t: [float(x) for x in v] for t, v in consts["m"].items()}},
        "test_coverage_by_family": cov,
        "how": ("sigma^2 = [m_bat^2 k_bat PA + m_ebr^2 k_ebr PA + m_pit^2 k_pit IP] / RPW_s^2 + "
                "m_src,bat^2 k_src,bat PA + m_src,pit^2 k_src,pit IP; band = eWAR +/- 1.2816 sigma; "
                "k_pit = k_fip (eWAR) or k_ra (an eWAR realized pitcher-season on R2)"),
        "claim": ("On seasons held out from its constants the band covered the other published WAR and a "
                  "split-half rescaled season at a rate between 70 and 90 percent in every playing-time "
                  "band. It is not a confidence interval for talent."),
    }


def write(payload: dict, path: Path | None = None) -> Path:
    path = Path(path) if path is not None else (OUT if BAND_LIVE else PREVIEW)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path


def set_payload(payload: dict | None) -> None:
    """Inject (or clear) the payload and the R2 set: the test seam."""
    global _CACHE, _R2
    _CACHE = payload
    _R2 = None


def load() -> dict | None:
    """The served constants while the flag is on and the artifact exists; else None."""
    global _CACHE
    if not BAND_LIVE:
        return None
    if _CACHE is None:
        if not OUT.exists():
            return None
        _CACHE = json.loads(OUT.read_text(encoding="utf-8"))
    return _CACHE


# ------------------------------------------------------------------ the band
def _rpw(season: int) -> float | None:
    import league_constants
    lt = league_constants.league_totals(int(season))
    return float(lt["rpw"]) if lt and lt.get("rpw") else None


def carries_r2(mlbam: int, season: int) -> bool:
    """True when eWAR realized prices this pitcher-season on R2 (data/ewar_v3.json parts.r2)."""
    global _R2
    if _R2 is None:
        _R2 = set()
        try:
            import ewar_v3
            if ewar_v3.available():
                for mid, by_s in (ewar_v3.load().get("players") or {}).items():
                    for s, blk in (by_s or {}).items():
                        if "r2" in ((blk or {}).get("parts") or {}):
                            _R2.add((int(mid), int(s)))
        except (OSError, ValueError):
            _R2 = set()
    return (int(mlbam), int(season)) in _R2


def half_width(*, season: int, pa=None, ip=None, series: str = "headline", mlbam: int | None = None,
               payload: dict | None = None) -> float | None:
    """The band's 80 percent half-width in wins (unrounded), or None: the flag off, no
    artifact, no runs per win, or no side above its floor. `pa` and `ip` are the
    exposures of the number the band sits beside (a hitting line passes PA only, a
    pitching line IP only, a whole player both)."""
    blob = payload if payload is not None else load()
    if blob is None:
        return None
    if series not in ("headline", "realized"):
        raise ValueError(f"unknown series {series!r}")
    rpw = _rpw(season)
    if rpw is None:
        return None
    basis = "fip"
    if series == "realized" and ip is not None and mlbam is not None and carries_r2(mlbam, season):
        basis = "ra"
    sg = U.sigma(blob["constants"], pa=_f(pa), ip=_f(ip), rpw=rpw, pit_basis=basis)
    return None if sg is None else float(blob.get("z", U.Z80)) * sg["sigma"]


def pm(value: float | None) -> float | None:
    """The printed half-width (one decimal, as eWAR), or None."""
    return None if value is None else round(float(value), DECIMALS)


def _f(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            import bullpen_export
            return bullpen_export.ip_to_float(v)
        except (ValueError, TypeError):
            return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def main(argv=None) -> int:
    payload = build()
    path = write(payload)
    print(f"written {path} ({'served' if BAND_LIVE else 'preview: BAND_LIVE is False'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
