"""
Prospect Savant CSV enrichment.

The local CSV exports are optional. When present, the export step attaches
their underlying metrics to tracked players by normalized (name, org).
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path


FILES = (
    ("AAA", "hitter", "ps_aaa_hitters.csv"),
    ("AAA", "pitcher", "ps_aaa_pitchers.csv"),
    ("A", "hitter", "ps_a_hitters.csv"),
    ("A", "pitcher", "ps_a_pitchers.csv"),
)


def _norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _num(v) -> float | None:
    if v in (None, "", "—"):
        return None
    text = str(v).strip()
    # Spreadsheet exports sometimes protect negative values as "'-1.23".
    if text.startswith("'"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return None


def _pick(row: dict, *names: str) -> float | None:
    for name in names:
        value = _num(row.get(name))
        if value is not None:
            return value
    return None


def _metric_row(row: dict, level: str, role: str) -> dict:
    base = {
        "source": "prospect_savant",
        "level": level,
        "role": role,
        "name": row.get("Name"),
        "org": row.get("Org"),
        "pos": row.get("Pos"),
        "age": _pick(row, "Age"),
        "pa": _pick(row, "PA"),
        "pitches": _pick(row, "Pitches"),
        "ps_score": _pick(row, "PS Score"),
        "xwoba": _pick(row, "xwOBA"),
        "woba": _pick(row, "wOBA"),
        "xba": _pick(row, "xBA"),
        "xslg": _pick(row, "xSLG"),
        "bb_pct": _pick(row, "BB%"),
        "k_pct": _pick(row, "K%"),
        "chase_pct": _pick(row, "Chase%"),
        "whiff_pct": _pick(row, "Whiff%"),
        "swstr_pct": _pick(row, "SwStr%"),
        "barrels": _pick(row, "Barrels"),
        "ev": _pick(row, "EV"),
        "max_ev": _pick(row, "Max EV"),
        "hard_hit_pct": _pick(row, "Hard Hit%"),
        "ba": row.get("BA"),
        "obp": row.get("OBP"),
        "slg": row.get("SLG"),
    }
    if role == "hitter":
        base.update({
            "power": _pick(row, "Power"),
            "discipline": _pick(row, "Discipline"),
            "ev_90": _pick(row, "90th% EV"),
            "ev_50": _pick(row, "50th% EV"),
            "hr": _pick(row, "HR"),
        })
    else:
        base.update({
            "contact_quality": _pick(row, "Contact Quality"),
            "max_velo": _pick(row, "Max Velo"),
        })
    return {k: v for k, v in base.items() if v not in (None, "")}


def load_prospect_savant(base_dir: Path) -> dict[tuple[str, str], dict]:
    """
    Return {(normalized_name, org): metric_dict}.

    If the same player appears in multiple files, prefer the highest PS Score,
    then the larger PA/pitch sample.
    """
    out: dict[tuple[str, str], dict] = {}
    for level, role, filename in FILES:
        path = base_dir / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                name = row.get("Name")
                org = row.get("Org")
                if not name or not org:
                    continue
                metric = _metric_row(row, level, role)
                key = (_norm_name(name), org.upper())
                existing = out.get(key)
                if existing is None:
                    out[key] = metric
                    continue
                existing_score = existing.get("ps_score") or 0
                metric_score = metric.get("ps_score") or 0
                existing_sample = existing.get("pa") or existing.get("pitches") or 0
                metric_sample = metric.get("pa") or metric.get("pitches") or 0
                if (metric_score, metric_sample) > (existing_score, existing_sample):
                    out[key] = metric
    return out


def attach_prospect_savant(players: list[dict], base_dir: Path) -> int:
    metrics = load_prospect_savant(base_dir)
    count = 0
    for p in players:
        key = (_norm_name(p.get("player_name")), (p.get("org") or "").upper())
        metric = metrics.get(key)
        if metric:
            p["prospect_savant"] = metric
            count += 1
    return count
