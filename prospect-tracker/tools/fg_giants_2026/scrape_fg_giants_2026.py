# Scraper for FanGraphs "San Francisco Giants Top 50 Prospects" (2026).
# Data is server-rendered into the post HTML (a summary <table class="sortable">
# + per-prospect detail cards .tool-item.top-prospects-tool). No JS render needed
# (verified live). Tool grades are present/future (e.g. 30/40); future is the
# projected 20-80 scouting grade.
import json, re, urllib.request
from bs4 import BeautifulSoup

URL = "https://blogs.fangraphs.com/san-francisco-giants-top-50-prospects/"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
soup = BeautifulSoup(html, "lxml")

def fg_id(href):
    m = re.search(r"/players/[^/]+/([a-z0-9]+)/", href or "")
    return m.group(1) if m else None

# ---- 1) Summary table: Rk, Name, Age, Highest Level, Position, ETA, FV ----
summary = {}
stable = None
for t in soup.select("table.sortable"):
    heads = [th.get_text(strip=True) for th in t.select("thead th")]
    if "Name" in heads and "FV" in heads:
        stable = t; break
assert stable is not None, "summary table not found"
cols = [th.get_text(strip=True) for th in stable.select("thead th")]
for tr in stable.select("tbody tr"):
    tds = tr.find_all("td")
    if len(tds) != len(cols):
        continue
    row = {cols[i]: tds[i].get_text(strip=True) for i in range(len(cols))}
    a = tr.find("a", href=True)
    rank = int(row["Rk"])
    summary[rank] = {
        "rank": rank,
        "name": (a.get_text(strip=True) if a else row.get("Name")),
        "fg_player_id": fg_id(a["href"]) if a else None,
        "fg_url": a["href"] if a else None,
        "age": row.get("Age"),
        "level": row.get("Highest Level"),
        "position": row.get("Position"),
        "eta": row.get("ETA"),
        "fv": row.get("FV"),
    }

# ---- 2) Detail cards: tool grades (present/future) + bio FV cross-check ----
cards = {}
for card in soup.select("div.tool-item.top-prospects-tool"):
    h3 = card.select_one("h3.header-name")
    if not h3:
        continue
    txt = h3.get_text(" ", strip=True)
    m = re.match(r"^\s*(\d+)\.", txt)
    if not m:
        continue
    rank = int(m.group(1))
    a = h3.find("a")
    card_pos = card.get("data-position")
    # bio table -> FV (cross-check) + age/ht/wt/bat-thr
    bio = {}
    for bt in card.select("div.table-grey table"):
        cells = bt.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            k = cells[i].get_text(strip=True)
            v = cells[i + 1].get_text(strip=True)
            if cells[i].name == "th":
                bio[k] = v
    # tool-grade table: the table-player-0 table WITH a populated thead
    tools = {}
    for tt in card.select("div.table-player-0 table"):
        ths = [th.get_text(strip=True) for th in tt.select("thead th") if th.get_text(strip=True)]
        tds = [td.get_text(strip=True) for td in tt.select("tbody td") if td.get_text(strip=True)]
        if not ths or len(tds) < len(ths):
            continue
        for label, val in zip(ths, tds):
            present, future = None, None
            if "/" in val and label.lower() not in ("sits/tops",):
                parts = [p.strip() for p in val.split("/")]
                if len(parts) == 2:
                    present, future = parts
            tools[label] = {"raw": val, "present": present, "future": future}
    cards[rank] = {
        "rank": rank,
        "name": a.get_text(strip=True) if a else None,
        "card_position": card_pos,
        "bio_fv": bio.get("FV"),
        "bio_age": bio.get("Age"),
        "bio_height": bio.get("Height"),
        "bio_weight": bio.get("Weight"),
        "bio_bat_thr": bio.get("Bat / Thr"),
        "tools": tools,
    }

# ---- 3) Merge ----
out = []
for rank in sorted(summary):
    s = summary[rank]; c = cards.get(rank, {})
    # cross-check name + FV between summary and card
    s["card_name"] = c.get("name")
    s["card_position"] = c.get("card_position")
    s["bio_fv"] = c.get("bio_fv")
    s["bio_bat_thr"] = c.get("bio_bat_thr")
    s["fv_consistent"] = (str(s["fv"]) == str(c.get("bio_fv"))) if c.get("bio_fv") else None
    s["tools"] = c.get("tools", {})
    out.append(s)

payload = {
    "source_name": "FanGraphs Giants 2026 Top 50",
    "source_url": URL,
    "org": "SFG",
    "published": "2026-06-05",
    "scraped_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    "count": len(out),
    "prospects": out,
}
with open(r"c:\tmp\fg_giants_2026_raw.json", "w", encoding="utf-8") as fp:
    json.dump(payload, fp, ensure_ascii=False, indent=2)

print("scraped", len(out), "prospects")
print("with tools:", sum(1 for p in out if p["tools"]))
print("fv inconsistencies:", [p["rank"] for p in out if p["fv_consistent"] is False])
print("missing card/tools:", [p["rank"] for p in out if not p["tools"]])
# show first 3 + one pitcher
for p in out[:3]:
    print(p["rank"], p["name"], p["position"], p["level"], "age", p["age"], "FV", p["fv"],
          "| tools:", {k: v["future"] or v["raw"] for k, v in p["tools"].items()})
