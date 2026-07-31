"""Is the FA de-staling rate a MARKET quantity or an ENGINE artifact?

fa_market.dollars_per_war_by_winter divides realized guarantees by the CURRENT
engine's PROJECTED WAR.  So the "market inflation rate" the FA lane now ships
(DESTALE_MODE='series') is a ratio whose DENOMINATOR the projections lane moved
this same session (P-IPAGE aged pitcher ip_proj).  Recompute the series and the
fitted rate with the arm ON and OFF.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run(flag):
    os.environ["EEPHUS_PIT_IP_AGE"] = flag
    for m in list(sys.modules):
        if m.startswith(("fa_", "proj_", "value_framework")):
            del sys.modules[m]
    import fa_market as fm
    t = time.time()
    enr = fm.enriched_signings(2015, 2026)
    ser = fm.dollars_per_war_by_winter(enr)
    print("EEPHUS_PIT_IP_AGE=%s  n=%d  %.1fs" % (flag, len(enr), time.time() - t))
    print("  series:", {y: round(v / 1e6, 3) for y, v in sorted(ser.items())})
    for cy in (2024, 2025, 2026, 2027):
        print("   destale rate for class %d = %.5f   winter_dpw = %.0f"
              % (cy, fm._destale_rate(ser, cy), fm.winter_dpw(ser, cy)))
    return ser

a = run("1")
b = run("0")
print("\nratio ON/OFF by winter:",
      {y: round(a[y] / b[y], 4) for y in sorted(set(a) & set(b))})
