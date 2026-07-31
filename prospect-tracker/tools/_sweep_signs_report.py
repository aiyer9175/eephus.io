import json, sys
from pathlib import Path
d = json.loads((Path(__file__).resolve().parent.parent / "data" / "xfv_sign_audit.json").read_text())
print("replica:", d["replica_check"])
for side in ("hit", "pit"):
    a = d["flagship"][side]
    print()
    print("==== FLAGSHIP", side, "n=", a["n"], "alpha=", a["alpha"], "folds=", len(a["fold_years"]), a["fold_years"])
    hdr = ("feature".ljust(16) + "dec".rjust(4) + "served".rjust(9) + "foldmn".rjust(9) +
           "fmin".rjust(8) + "fmax".rjust(8) + "pos/n".rjust(7) + "agr".rjust(5) +
           "margP".rjust(8) + "margS".rjust(8) + "olsPart".rjust(9) + "noPartner".rjust(10) + "  verdict")
    print(hdr)
    for k, v in a["features"].items():
        nop = "" if v["w_without_partner"] is None else "%+.4f" % v["w_without_partner"]
        print(k.ljust(16) + ("%+d" % v["declared"]).rjust(4) +
              ("%+.4f" % v["served_w"]).rjust(9) +
              ("%+.4f" % v["fold_w_mean"]).rjust(9) +
              ("%+.3f" % v["fold_w_min"]).rjust(8) +
              ("%+.3f" % v["fold_w_max"]).rjust(8) +
              ("%d/%d" % (v["folds_positive"], v["folds_n"])).rjust(7) +
              str(v["folds_agreeing_with_declaration"]).rjust(5) +
              ("%+.4f" % (v["marginal_wpearson"] or 0)).rjust(8) +
              ("%+.4f" % (v["marginal_spearman"] or 0)).rjust(8) +
              ("%+.4f" % v["ols_partial_std"]).rjust(9) +
              nop.rjust(10) + "  " + v["verdict"])
    print("contradictions:", a["contradictions"])
print()
print("==== PROVISIONAL (efv_ungraded no-FV sets)")
for side in ("hit", "pit"):
    p = d["provisional"][side]
    print(side, "n=", p["n"], "contradictions=", p["contradictions"], "undeclared=", p["undeclared"])
    for k, v in p["features"].items():
        tag = "CONTRADICTS" if v["contradiction"] else ("UNDECLARED" if v["undeclared"] else "")
        print("  " + k.ljust(16) + "decl=" + str(v["declared"]).rjust(5) +
              ("  w=%+.4f" % v["served_w"]) + ("  marg=%+.4f  " % v["marginal_wpearson"]) + tag)
if "drop_gate" in d:
    print()
    print("==== DROP GATE")
    for name, g in d["drop_gate"].items():
        print(name, json.dumps(g, indent=1))
