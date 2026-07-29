import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fa_lab as lab

if __name__ == "__main__":
    arms = ["strict_comps", "noise1_7"]
    r = lab.boot(arms, B=300, metrics=("guar_mae", "mega_mae", "aav_mae", "yrs_mae"), workers=10)
    out = os.path.join(lab.SCRATCH, "boot_wave4.json")
    json.dump(r, open(out, "w"), indent=1, default=float)
    print("B =", r["B"], " champ guar_mae mean =", round(r["champ"]["guar_mae"], 4))
    print(f"{'arm':<16}{'metric':<10}{'cand':>9}{'delta':>9}{'sd':>8}{'ci95lo':>9}{'ci95hi':>9}{'P(imp)':>8}")
    for a in arms:
        for m in ("guar_mae", "mega_mae", "aav_mae", "yrs_mae"):
            d = r["arms"][a][m]
            print(f"{a:<16}{m:<10}{d['cand_mean']:>9.4f}{d['delta_mean']:>+9.4f}"
                  f"{d['delta_sd']:>8.4f}{d['ci95'][0]:>+9.4f}{d['ci95'][1]:>+9.4f}{d['p_improves']:>8.3f}")
