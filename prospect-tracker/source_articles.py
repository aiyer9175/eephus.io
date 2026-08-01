from __future__ import annotations

import re
from pathlib import Path

from scrapers import Snapshot, normalize_key
from trades import canonical_org


def _date_from_name(path: Path) -> str:
    m = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", path.name)
    if not m:
        return ""
    return "-".join(m.groups())


def _event_key(source: str, event_date: str, event_type: str, player_key: str, suffix: str = "") -> str:
    parts = [source, event_date, event_type, player_key]
    if suffix:
        parts.append(str(suffix))
    return "|".join(parts)


def _event(path: Path, player_name: str, event_type: str, *,
           rank_before: int | None = None, rank_after: int | None = None,
           confidence: float = 0.7, payload: dict | None = None,
           excerpt: str | None = None) -> dict:
    event_date = _date_from_name(path)
    player_key = normalize_key(player_name)
    suffix = rank_after if rank_after is not None else rank_before if rank_before is not None else ""
    return {
        "event_key": _event_key("baseballamerica", event_date, event_type, player_key, suffix),
        "player_key": player_key,
        "player_name": player_name,
        "source": "baseballamerica",
        "event_date": event_date,
        "event_type": event_type,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "confidence": confidence,
        "payload": payload or {},
        "excerpt": excerpt or "",
    }


def _parse_rank_token(value: str) -> int | None:
    value = (value or "").strip()
    if not value or value in {"—", "-", "Gr.", "Dr."}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_ba_top100_list(path: Path) -> tuple[list[Snapshot], list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines()]
    event_date = _date_from_name(path)
    interval = f"Baseball America {event_date} Top 100"
    snapshots: list[Snapshot] = []
    events: list[dict] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^(\d{1,3})\.\s+(.+)$", line)
        if not m:
            continue
        rank = int(m.group(1))
        name = m.group(2).strip()
        team = ""
        pos = None
        j = idx + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt or nxt.startswith("Headshot of"):
                j += 1
                continue
            if nxt.startswith("|"):
                pos = nxt.lstrip("|").strip()
                break
            if re.match(r"^\d{1,3}\.\s+", nxt):
                break
            if not team:
                team = nxt
            j += 1
        snapshots.append(Snapshot(
            source="baseballamerica",
            snapshot_date=event_date,
            interval_label=interval,
            player_key=normalize_key(name),
            player_name=name,
            position=pos,
            org=canonical_org(team) or team or None,
            rank=rank,
            fv=None,
            status="active",
        ))
        events.append(_event(path, name, "top100_rank", rank_after=rank,
                             confidence=1.0, payload={"rank": rank, "position": pos, "team": team}))
    return snapshots, events


def parse_ba_top100_movement(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    events: list[dict] = []
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"Graduated", "Joined", "Dropped"}:
            section = line.lower()
            continue
        m = re.match(r"^(.+?),\s+([^,]+),\s+(.+?)\s+\((?:Was\s+)?No\.\s+(\d+)(?:,\s+added in-month)?\)$", line)
        if section and m:
            name = m.group(1).strip()
            rank = int(m.group(4))
            if section == "joined":
                events.append(_event(path, name, "top100_joined", rank_after=rank,
                                     confidence=1.0, excerpt=line))
            elif section == "dropped":
                events.append(_event(path, name, "top100_dropped", rank_before=rank,
                                     confidence=1.0, excerpt=line))
            elif section == "graduated":
                events.append(_event(path, name, "top100_graduated", rank_before=rank,
                                     confidence=0.8, excerpt=line))
            continue
        if "\t" not in raw or raw.startswith("Player\t"):
            continue
        parts = raw.split("\t")
        if len(parts) < 8:
            continue
        name, org, jan, apr, dif_apr, may, dif_may, june = parts[:8]
        dif_june = parts[8] if len(parts) > 8 else ""
        rank_after = _parse_rank_token(june)
        rank_before = _parse_rank_token(may) or _parse_rank_token(apr) or _parse_rank_token(jan)
        payload = {
            "org": org,
            "jan": _parse_rank_token(jan),
            "apr": _parse_rank_token(apr),
            "may": _parse_rank_token(may),
            "june": rank_after,
            "june_token": june,
            "june_diff": _parse_rank_token(dif_june),
        }
        events.append(_event(path, name, "top100_movement", rank_before=rank_before,
                             rank_after=rank_after, confidence=0.9, payload=payload, excerpt=raw))
    return events


def parse_ba_statcast_by_age(path: Path) -> list[dict]:
    events: list[dict] = []
    current_age = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        m_age = re.match(r"^Age\s+(\d{2})$", line)
        if m_age:
            current_age = int(m_age.group(1))
            continue
        if "\t" not in raw or raw.upper().startswith("PLAYER\t") or raw.upper().startswith("PLAYEr\t"):
            continue
        parts = raw.split("\t")
        if len(parts) < 9:
            continue
        name = parts[0].strip()
        if not name or name == "Reset":
            continue
        payload = {
            "age_bucket": current_age,
            "pos": parts[1].strip() if len(parts) > 1 else None,
            "org": parts[2].strip() if len(parts) > 2 else None,
            "team": parts[3].strip() if len(parts) > 3 else None,
            "bats": parts[4].strip() if len(parts) > 4 else None,
            "age": parts[5].strip() if len(parts) > 5 else None,
            "pa": _parse_rank_token(parts[6]) if len(parts) > 6 else None,
            "z_contact_pct": parts[7].strip() if len(parts) > 7 else None,
            "chase_pct": parts[8].strip() if len(parts) > 8 else None,
            "hard_hit_pct": parts[9].strip() if len(parts) > 9 else None,
            "p90_ev": parts[10].strip() if len(parts) > 10 else None,
        }
        events.append(_event(path, name, "statcast_by_age_standout",
                             confidence=0.75, payload=payload, excerpt=raw))
    injury_terms = ("injury", "injured", "surgery", "fractured", "sprain", "setback")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        low = line.lower()
        if not any(term in low for term in injury_terms):
            continue
        for name in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", line):
            if name in {"June Top", "Filter Reset"}:
                continue
            events.append(_event(path, name, "injury_note", confidence=0.45,
                                 payload={"article": path.name}, excerpt=line[:400]))
    return events


def parse_source_article_drops(data_dir: Path) -> tuple[list[Snapshot], list[dict]]:
    snapshots: list[Snapshot] = []
    events: list[dict] = []
    statcast_standout_events: list[dict] = []
    for path in sorted(data_dir.glob("*.txt")):
        name = path.name.lower()
        if "ba_t100list" in name:
            snap, ev = parse_ba_top100_list(path)
            snapshots.extend(snap)
            events.extend(ev)
        elif "top100_movement" in name:
            events.extend(parse_ba_top100_movement(path))
        elif "statcast_byage" in name:
            ev = parse_ba_statcast_by_age(path)
            events.extend(ev)
            statcast_standout_events.extend(e for e in ev if e.get("event_type") == "statcast_by_age_standout")
    snapshot_keys = {s.player_key for s in snapshots}
    for event in statcast_standout_events:
        if event["player_key"] in snapshot_keys:
            continue
        payload = event.get("payload") or {}
        # A BA age-band statcast table is not a ranked list, but it is an
        # explicit editorial standout. Emit a conservative single-source
        # FV-40 snapshot only when this article set has no ranked snapshot
        # for the player; normal consensus shrinkage still pulls the
        # single-source confidence down.
        snapshots.append(Snapshot(
            source="baseballamerica_statcast_by_age",
            snapshot_date=event.get("event_date") or "",
            interval_label=f"Baseball America {event.get('event_date') or ''} Statcast By Age",
            player_key=event["player_key"],
            player_name=event["player_name"],
            position=payload.get("pos"),
            org=canonical_org(payload.get("org") or "") or payload.get("org"),
            rank=None,
            fv=40.0,
            status="active",
        ))
    deduped = {}
    for event in events:
        deduped[event["event_key"]] = event
    return snapshots, list(deduped.values())
