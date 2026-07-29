# SCRATCH: arm definitions for the ablation audit.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_ablate import KEYS, N_NOISE

GROUPS = {
    "hit": {
        "G_production":  ["obp_rel", "k_rel", "peak_k_rel", "ops_rel"],
        "G_contact":     ["k_rel", "peak_k_rel"],
        "G_onbase":      ["obp_rel", "ops_rel"],
        "G_tools":       ["tool_hit", "tool_speed"],
        "G_age":         ["age", "age_rel_level"],
        "G_cohort":      ["is_ifa", "is_college", "milb_missing"],
        "G_track":       ["n_milb_seasons", "level_rank"],
        "G_all_but_fv":  [k for k in KEYS["hit"] if k != "fv"],
    },
    "pit": {
        "G_production":  ["peak_k_rel", "k_rel", "bb_rel", "x_era_k"],
        "G_k":           ["peak_k_rel", "k_rel"],
        "G_age":         ["age", "age_rel_level"],
        "G_all_but_fv":  [k for k in KEYS["pit"] if k != "fv"],
    },
}

# a-priori (mechanism-motivated) minimal sets, declared BEFORE seeing bootstrap results
MINIMAL = {
    "hit": {
        "M_fv_only":        ["fv"],
        "M_phase1":         ["fv", "obp_rel", "k_rel"],
        "M_prod":           ["fv", "obp_rel", "k_rel", "peak_k_rel", "ops_rel"],
        "M_prod_age":       ["fv", "obp_rel", "k_rel", "age_rel_level"],
        "M_prod_age_tools": ["fv", "obp_rel", "k_rel", "age_rel_level", "tool_hit", "tool_speed"],
        "M_core6":          ["fv", "obp_rel", "k_rel", "peak_k_rel", "age_rel_level", "milb_missing"],
        "M_no_late_adds":   ["fv", "obp_rel", "k_rel", "peak_k_rel", "age_rel_level",
                             "n_milb_seasons", "tool_hit", "tool_speed"],
    },
    "pit": {
        "M_fv_only":        ["fv"],
        "M_kbb":            ["fv", "k_rel", "bb_rel"],
        "M_kbb_peak":       ["fv", "peak_k_rel", "k_rel", "bb_rel"],
        "M_kbb_age":        ["fv", "peak_k_rel", "k_rel", "bb_rel", "age_rel_level"],
        "M_no_xerak_age":   ["fv", "peak_k_rel", "k_rel", "bb_rel", "age_rel_level", "tool_fb"],
    },
}


def arms_for(side):
    """name -> list of column NAMES (resolved against D['idx'])."""
    base = list(KEYS[side])
    out = {"base": base}
    for f in base:
        out["drop:" + f] = [k for k in base if k != f]
        out["perm:" + f] = [("~perm~" + k if k == f else k) for k in base]
    for g, fs in GROUPS[side].items():
        out["dropG:" + g] = [k for k in base if k not in fs]
    for m, fs in MINIMAL[side].items():
        out["min:" + m] = list(fs)
    for j in range(N_NOISE):
        out["noise:%d" % j] = base + ["~noise~%d" % j]
    return out
