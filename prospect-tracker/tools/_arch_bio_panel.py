"""Point-in-time biometric panel from the DATED FanGraphs board archives.
Each processed folder is <slug>__<YYYY-MM-DD>; that date is the vintage.
READ-ONLY. Scratch lab."""
import csv, json, re, sys, collections
from pathlib import Path
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
from scrapers import normalize_key
try:
    from fangraphs_csv import fix_mojibake
except Exception:
    fix_mojibake = lambda s: s

BASE = Path(r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker\data\fangraphs_imports\processed")
HT = re.compile(r"(\d)\s*['\u2019]\s*(\d{1,2})?")

def ht_in(s):
    if not s: return None
    m = HT.search(str(s))
    if not m: return None
    ft, inch = int(m.group(1)), int(m.group(2) or 0)
    if not (4 <= ft <= 7) or inch > 11: return None
    return ft * 12 + inch

def norm(h):
    return (h or "").strip().lower()

panel = collections.defaultdict(list)   # key -> [(vintage, h, w, frame, athl, levers, fgid, slug)]
folders = 0
for d in sorted(BASE.iterdir()):
    if not d.is_dir(): continue
    if "__" not in d.name: continue
    vintage = d.name.rsplit("__", 1)[1]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", vintage): continue
    summ = list(d.glob("summary-*.csv"))
    if not summ: continue
    # physical file: Frame / Athl / Levers
    phys = {}
    for pf in d.glob("physical-*.csv"):
        with open(pf, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.DictReader(fh):
                r = {norm(k): v for k, v in row.items()}
                nm = fix_mojibake(r.get("name") or "")
                if not nm: continue
                phys[normalize_key(nm)] = (r.get("frame"), r.get("athl"), r.get("levers"))
    got = 0
    with open(summ[0], newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            r = {norm(k): v for k, v in row.items()}
            nm = fix_mojibake(r.get("name") or "")
            if not nm: continue
            k = normalize_key(nm)
            h = ht_in(r.get("ht")); 
            try: w = int(float(r.get("wt") or 0)) or None
            except Exception: w = None
            if h is None and w is None: continue
            f, a, lv = phys.get(k, (None, None, None))
            panel[k].append({"vintage": vintage, "h": h, "w": w, "frame": f, "athl": a,
                             "levers": lv, "fgid": r.get("playerid"), "slug": d.name})
            got += 1
    if got: folders += 1

for k in panel: panel[k].sort(key=lambda x: x["vintage"])
print("board folders contributing:", folders)
print("distinct players in panel:", len(panel))
print("total (player,vintage) observations:", sum(len(v) for v in panel.values()))
nf = sum(1 for v in panel.values() if any(x["frame"] not in (None, "") for x in v))
print("players with >=1 Frame obs:", nf)
json.dump({k: v for k, v in panel.items()}, open("tools/_arch_bio_panel.json", "w"))
