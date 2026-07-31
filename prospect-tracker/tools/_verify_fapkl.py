import os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = (r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
     r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad\enriched.pkl")
cached = pickle.load(open(P, "rb"))

def agg(rows, tag):
    tot = sum((r.get("_war_path") or {}).get("war_y1", 0.0) or 0.0 for r in rows)
    pit = sum((r.get("_war_path") or {}).get("war_y1", 0.0) or 0.0
              for r in rows if (r.get("pos") or "").upper() in ("SP", "RP", "P", "RHP", "LHP"))
    print("%-28s n=%d  sum war_y1 = %.2f   (pitcher-ish %.2f)" % (tag, len(rows), tot, pit))
    return tot

agg(cached, "CACHED enriched.pkl")
for flag in ("0", "1"):
    os.environ["EEPHUS_PIT_IP_AGE"] = flag
    for m in list(sys.modules):
        if m.startswith(("fa_", "proj_", "value_framework")):
            del sys.modules[m]
    import fa_market as fm
    agg(fm.enriched_signings(2015, 2026), "fresh, EEPHUS_PIT_IP_AGE=" + flag)
