"""Probe: Tommy John surgery list (community DB) CSV export.
Native mlbamid, 1974-2026. Run: python scripts/probes/tj_surgery_list.py
"""
from _probe import probe

SHEET = "1gQujXQQGOVNaiuwSN680Hq-FDVsCwvN-3AazykOBON0"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET}/export?format=csv"

if __name__ == "__main__":
    print("tj_surgery_list:")
    st, ct, n = probe(URL, "tj_list_export_01.csv")
    if st == 200:
        # first data row is a donations banner; real header is row 2 (Player,...,mlbamid,...)
        print("  OK - parse: skip row 1, DictReader; join on mlbamid; "
              "as-of feature = surgery Year < decision cutoff year")
