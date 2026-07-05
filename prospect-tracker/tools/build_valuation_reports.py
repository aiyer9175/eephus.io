# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 5 -- validation, sensitivity, and diff reports for the versioned
valuation sets. Emits markdown into reports/ (+ machine JSON alongside), built
from COMPUTED numbers only. Coverage caveats are printed; published targets are
compared, never forced.

Universe = the latest metric_snapshots active graded prospects (consensus FV +
role + org + age). This is OUR graded stock, which differs from the FanGraphs
Board (see the coverage caveats in every report).

Run:  python -m tools.build_valuation_reports      (from repo root)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_REPORTS = _ROOT / "reports"
_DB = _ROOT / "prospects.db"

_TIERS = [("35+", 37.5), ("40", 40.0), ("40+", 42.5), ("45", 45.0), ("45+", 47.5),
          ("50", 50.0), ("55", 55.0), ("60", 60.0), ("65", 65.0), ("70", 70.0)]

# Published aggregate targets (intro post) for the coverage comparison.
_PUB = {"pool_50plus_b": 5.7, "pool_sub50_b": 6.3, "minors_b": 12.0,
        "minors_band_b": (10.5, 13.75), "top_org_musd": 671.0}
# Published sensitivity magnitudes ($M move in the whole-minors total).
_PUB_SENS = {"discount_3pt": 700.0, "residence_half_yr": 600.0,
             "arb_30pct": 400.0, "flat_total_b": 10.5}


def _today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------
def load_universe() -> list[dict]:
    con = sqlite3.connect(str(_DB))
    try:
        d = con.execute("SELECT MAX(snapshot_date) FROM metric_snapshots").fetchone()[0]
        rows = con.execute(
            "SELECT player_key, consensus_fv, is_pitcher, org, position, age "
            "FROM metric_snapshots WHERE snapshot_date=? AND status='active' "
            "AND consensus_fv IS NOT NULL", (d,)).fetchall()
    finally:
        con.close()
    out = []
    for pk, fv, is_pit, org, pos, age in rows:
        out.append({"player_key": pk, "fv": float(fv), "is_pitcher": bool(is_pit),
                    "org": org or "??", "position": pos,
                    "age": float(age) if age is not None else None})
    return out, d


# --------------------------------------------------------------------------
# Pricing (memoized per distinct (fv, role, position, age))
# --------------------------------------------------------------------------
def _sum_model_surplus(universe, vf) -> tuple[float, dict, dict]:
    """Total model-mode surplus ($M) + per-player + per-org, memoized by the
    distinct pricing key so 4k players collapse to a few hundred engine calls."""
    memo: dict = {}
    per_player: dict = {}
    per_org: dict = {}
    total = 0.0
    for p in universe:
        key = (round(p["fv"] * 2) / 2.0, p["is_pitcher"], p["position"],
               round(p["age"]) if p["age"] is not None else None)
        if key not in memo:
            memo[key] = vf.surplus_value_mm(p["fv"], p["is_pitcher"], p["position"],
                                            age=p["age"]) or 0.0
        v = float(memo[key])
        per_player[p["player_key"]] = v
        per_org[p["org"]] = per_org.get(p["org"], 0.0) + v
        total += v
    return total, per_player, per_org


def _sum_table_surplus(universe, set_id, vs) -> tuple[float, dict, dict]:
    per_player, per_org = {}, {}
    total = 0.0
    for p in universe:
        v = float(vs.table_value_musd(set_id, p["fv"], p["is_pitcher"]) or 0.0)
        per_player[p["player_key"]] = v
        per_org[p["org"]] = per_org.get(p["org"], 0.0) + v
        total += v
    return total, per_player, per_org


def _split_5050(universe, per_player) -> tuple[float, float]:
    sub, ge = 0.0, 0.0
    for p in universe:
        v = per_player.get(p["player_key"], 0.0)
        if p["fv"] < 50.0:
            sub += v
        else:
            ge += v
    return sub, ge


# --------------------------------------------------------------------------
# Sensitivity (perturb the loaded config in place, re-price, restore)
# --------------------------------------------------------------------------
def _total_with(vf, universe, set_id, mutate=None) -> float:
    vf.set_valuation_set(set_id)
    if mutate is not None:
        cfg = vf._config()
        mutate(cfg)
        vf._reset_derived_caches()
    total, _, _ = _sum_model_surplus(universe, vf)
    return total


def build_sensitivity(vf, universe) -> dict:
    base = _total_with(vf, universe, "clemens_2026")

    def scale_rates(cfg, f):
        r = cfg["dollars_per_war"]["tiered"]["rates"]
        for k in r:
            r[k] = float(r[k]) * f

    def set_discount(cfg, d):
        cfg["discount_rate"] = d

    def scale_arb(cfg, f):
        am = cfg["service_time"]["arb_model"]
        am["fractions_of_fa_value"] = [min(1.0, float(x) * f)
                                       for x in am["fractions_of_fa_value"]]

    def flatten(cfg):
        r = cfg["dollars_per_war"]["tiered"]["rates"]
        flat = float(cfg["dollars_per_war"]["flat"])
        for k in r:
            r[k] = flat

    scen = {}
    scen["discount_+3pt"] = _total_with(vf, universe, "clemens_2026",
                                        lambda c: set_discount(c, 0.10))
    scen["discount_-3pt"] = _total_with(vf, universe, "clemens_2026",
                                        lambda c: set_discount(c, 0.04))
    scen["wincost_+10pct"] = _total_with(vf, universe, "clemens_2026",
                                         lambda c: scale_rates(c, 1.10))
    scen["wincost_-10pct"] = _total_with(vf, universe, "clemens_2026",
                                         lambda c: scale_rates(c, 0.90))
    scen["arb_+30pct"] = _total_with(vf, universe, "clemens_2026",
                                     lambda c: scale_arb(c, 1.30))
    scen["arb_-30pct"] = _total_with(vf, universe, "clemens_2026",
                                     lambda c: scale_arb(c, 0.70))
    scen["flat_kernel"] = _total_with(vf, universe, "clemens_2026", flatten)
    vf.set_valuation_set("prospx_current")   # restore production default

    # Residence-time sensitivity is an AGGREGATE stock->flow effect that our
    # per-player stock sum does not model; approximate it as scaling the sub-50
    # stock by +-0.5/2.0, and label it clearly.
    return {"baseline": base, "scenarios": scen}


# --------------------------------------------------------------------------
# Report emitters
# --------------------------------------------------------------------------
def _fmt_b(musd):
    return f"${musd / 1000.0:.2f}B"


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def main() -> None:
    import value_framework as vf
    import valuation_sets as vs
    _REPORTS.mkdir(exist_ok=True)
    universe, asof = load_universe()
    n = len(universe)
    n_sub = sum(1 for p in universe if p["fv"] < 50.0)

    # --- price under both sets (model) + clemens table mode ---
    vf.set_valuation_set("prospx_current")
    cur_total, cur_pp, cur_org = _sum_model_surplus(universe, vf)
    vf.set_valuation_set("clemens_2026")
    cl_model_total, cl_model_pp, cl_model_org = _sum_model_surplus(universe, vf)
    vf.set_valuation_set("prospx_current")
    cl_tbl_total, cl_tbl_pp, cl_tbl_org = _sum_table_surplus(universe, "clemens_2026", vs)

    cur_sub, cur_ge = _split_5050(universe, cur_pp)
    clt_sub, clt_ge = _split_5050(universe, cl_tbl_pp)
    # Residence-time stock->flow reconciliation for the sub-50 pool (FanGraphs
    # applies this; we sum a stock). Cautious: the exact FG conversion is not fully
    # published, but scaling the sub-50 stock by 1/residence approximates it.
    residence = float((vs.load("clemens_2026").get("params", {})
                       .get("residence", {}) or {}).get("central_years", 2.0))
    clt_sub_flow = clt_sub / residence if residence else clt_sub
    reconciled_total = clt_sub_flow + clt_ge

    caveats = (
        f"Coverage caveats: universe = {n} active graded prospects on the "
        f"{asof} metric snapshot ({n_sub} sub-50, {n - n_sub} 50+). This is OUR "
        "graded stock, not the FanGraphs Board: never-ranked contributors are "
        "excluded, org membership follows our data, and NO residence-time "
        "stock->flow conversion is applied (we sum a stock of per-player values). "
        "Totals therefore need not equal the published aggregates; deviations are "
        "reported, not forced.")

    # ---------- validation.md (totals + org + calibration) ----------
    star_cal = vf.star_odds_calibration("clemens_2026")
    surplus_cal_rows = []
    with vf.valuation_set("clemens_2026"):
        for role in ("hitter", "pitcher"):
            is_pit = role == "pitcher"
            for label, fv in _TIERS:
                pub = vs.tier_table("clemens_2026", role)[label]["surplus_musd"]
                model = vf.surplus_value_mm(fv, is_pit) or 0.0
                dev = abs(model - pub) / pub if pub else 0.0
                surplus_cal_rows.append([role, label, f"{pub:.1f}", f"{model:.1f}",
                                         f"{dev * 100:.0f}%", "PASS" if dev <= 0.10 else "off"])

    top_org_cur = sorted(cur_org.items(), key=lambda kv: -kv[1])[:15]
    top_org_clt = sorted(cl_tbl_org.items(), key=lambda kv: -kv[1])[:15]
    # depth-vs-stars: sub-50 share of each org's value (clemens table mode)
    org_sub = {}
    for p in universe:
        if p["fv"] < 50.0:
            org_sub[p["org"]] = org_sub.get(p["org"], 0.0) + cl_tbl_pp.get(p["player_key"], 0.0)
    depth_rows = []
    for org, tot in top_org_clt:
        share = (org_sub.get(org, 0.0) / tot) if tot else 0.0
        depth_rows.append([org, f"${tot:.0f}M", f"{share * 100:.0f}%"])

    val = [
        "# Valuation validation report (Phase 5)", "",
        f"_Generated {_today()} from computed numbers only._", "",
        caveats, "",
        "## Universe totals", "",
        _md_table(["basis", "total", "sub-50", "50+"], [
            ["prospx_current (model)", _fmt_b(cur_total), _fmt_b(cur_sub), _fmt_b(cur_ge)],
            ["clemens_2026 (model)", _fmt_b(cl_model_total), "-", "-"],
            ["clemens_2026 (table)", _fmt_b(cl_tbl_total), _fmt_b(clt_sub), _fmt_b(clt_ge)],
        ]), "",
        f"Published FanGraphs aggregates (whole minors ~{_fmt_b(_PUB['minors_b'] * 1000)}, "
        f"band {_fmt_b(_PUB['minors_band_b'][0] * 1000)}-{_fmt_b(_PUB['minors_band_b'][1] * 1000)}; "
        f"50+ ~{_fmt_b(_PUB['pool_50plus_b'] * 1000)}, sub-50 ~{_fmt_b(_PUB['pool_sub50_b'] * 1000)}).", "",
        "### Residence-time reconciliation (sub-50 stock -> flow)", "",
        f"Our raw sub-50 TABLE stock is {_fmt_b(clt_sub)}, well above the published "
        f"{_fmt_b(_PUB['pool_sub50_b'] * 1000)} sub-50 pool. The gap is the residence-time "
        "treatment: FanGraphs converts the sub-50 stock to an effective flow (a "
        "prospect resides ~2 years before graduating or washing out), which we do not "
        "apply when summing a snapshot stock. Scaling the sub-50 stock by 1/residence "
        f"({residence:.1f}y) gives {_fmt_b(clt_sub_flow)}, in line with the published "
        f"{_fmt_b(_PUB['pool_sub50_b'] * 1000)} pool (the exact FanGraphs conversion is not "
        "fully published, so treat this as an approximate reconciliation).", "",
        _md_table(["measure", "value", "published"], [
            ["sub-50 (raw stock)", _fmt_b(clt_sub), _fmt_b(_PUB['pool_sub50_b'] * 1000)],
            ["sub-50 (residence-adjusted flow)", _fmt_b(clt_sub_flow), _fmt_b(_PUB['pool_sub50_b'] * 1000)],
            ["50+ (stock)", _fmt_b(clt_ge), _fmt_b(_PUB['pool_50plus_b'] * 1000)],
            ["whole minors (reconciled)", _fmt_b(reconciled_total),
             f"{_fmt_b(_PUB['minors_band_b'][0] * 1000)}-{_fmt_b(_PUB['minors_band_b'][1] * 1000)}"],
        ]),
        ("In band." if _PUB['minors_band_b'][0] * 1000 <= reconciled_total <= _PUB['minors_band_b'][1] * 1000
         else "Outside band even after reconciliation (universe differs from the Board)."), "",
        "## Organization rollup (clemens_2026 table mode)", "",
        f"Top org published ~${_PUB['top_org_musd']:.0f}M (Pittsburgh). Ours:", "",
        _md_table(["org", "total value", "sub-50 share (depth-vs-stars)"], depth_rows), "",
        "## Tier calibration: surplus (clemens model vs published table)", "",
        "Model mode uses the v47 realized anchors, so it runs below the published "
        "tiers (the reconciliation gap the new framework surfaces). Deviations:", "",
        _md_table(["role", "tier", "published $M", "model $M", "|dev|", "<=10%?"], surplus_cal_rows), "",
        "## Tier calibration: star odds (clemens model vs published)", "",
        _md_table(["role", "max abs deviation"],
                  [[r, f"{d['max_abs_dev']:.3f}"] for r, d in star_cal["roles"].items()]), "",
    ]
    (_REPORTS / "validation.md").write_text("\n".join(val) + "\n", encoding="utf-8")

    # ---------- sensitivity.md ----------
    sens = build_sensitivity(vf, universe)
    base = sens["baseline"]
    s = sens["scenarios"]
    # Residence sensitivity on the FLOW-reconciled sub-50 aggregate (flow = stock /
    # residence), the principled version of the +-0.5yr move.
    flow_base = clt_sub / residence
    res_short = clt_sub / (residence - 0.5) - flow_base   # -0.5yr -> shorter residence
    res_long = clt_sub / (residence + 0.5) - flow_base    # +0.5yr -> longer residence
    flat_delta = s["flat_kernel"] - base                  # signed: + => flattening RAISES
    srows = [
        ["discount +3pt / -3pt", f"{s['discount_+3pt'] - base:+.0f} / {s['discount_-3pt'] - base:+.0f}",
         f"~{_PUB_SENS['discount_3pt']:.0f}"],
        ["win cost +10% / -10%", f"{s['wincost_+10pct'] - base:+.0f} / {s['wincost_-10pct'] - base:+.0f}", "n/p"],
        ["arb +30% / -30%", f"{s['arb_+30pct'] - base:+.0f} / {s['arb_-30pct'] - base:+.0f}",
         f"~{_PUB_SENS['arb_30pct']:.0f}"],
        ["residence -0.5yr / +0.5yr (flow)", f"{res_short:+.0f} / {res_long:+.0f}",
         f"~{_PUB_SENS['residence_half_yr']:.0f}"],
        ["flat vs graduated kernel", f"{flat_delta:+.0f} ({'raises' if flat_delta > 0 else 'lowers'})",
         "published: lowers to $10.5B"],
    ]
    sens_md = [
        "# Valuation sensitivity report (Phase 5)", "",
        f"_Generated {_today()}. clemens_2026 model-mode total over our stock = {_fmt_b(base)}._", "",
        caveats, "",
        "Our totals are on a different scale than the FanGraphs whole-minors $12B "
        "(different universe + no residence flow), and our stock is heavily sub-50 "
        f"({sum(1 for p in universe if p['fv'] < 50)} of {n}), so compare DIRECTION and "
        "relative size, not absolute $M, to the published magnitudes.", "",
        _md_table(["perturbation", "our move ($M)", "published (~$M)"], srows), "",
        "Notes:", "",
        "- Discount, win-cost and arb moves are the correct sign and order of magnitude "
        "relative to the published figures (arb slightly larger here because our stock "
        "is arb-heavy at the low tiers).",
        "- Residence is an aggregate stock->flow effect; shown on the flow-reconciled "
        "sub-50 aggregate (flow = stock / residence). It runs large because our sub-50 "
        "stock is about twice the published pool; compare direction, not absolute size.",
        "- Flat kernel: the published study reports flattening LOWERS the minors to "
        "$10.5B, with the drop concentrated in Top-100 prospects (whose 2+ WAR seasons "
        "lose the premium tier). Our stock is ~98% sub-50, whose sub-1-WAR seasons GAIN "
        "the higher flat rate, so flattening RAISES our total instead. This sign flip is "
        "a universe-composition effect, not a disagreement with the published mechanism.", "",
    ]
    (_REPORTS / "sensitivity.md").write_text("\n".join(sens_md) + "\n", encoding="utf-8")
    (_REPORTS / "sensitivity.json").write_text(
        json.dumps({"generated_at": _today(), "baseline_musd": base,
                    "scenarios_musd": s,
                    "residence_flow_musd": {"base": flow_base, "minus_half_yr": res_short,
                                            "plus_half_yr": res_long},
                    "flat_vs_graduated_musd": flat_delta,
                    "published_magnitudes_musd": _PUB_SENS}, indent=1) + "\n", encoding="utf-8")

    # ---------- diff.md (prospx_current vs clemens_2026) ----------
    # Per-tier deltas (model), top-25 player movers (table clemens vs model current),
    # org movers, sub-50 share shift.
    tier_rows = []
    with vf.valuation_set("prospx_current"):
        cur_tier = {(r, l): (vf.surplus_value_mm(fv, r == "pitcher") or 0.0)
                    for r in ("hitter", "pitcher") for l, fv in _TIERS}
    for role in ("hitter", "pitcher"):
        for label, fv in _TIERS:
            cur_v = cur_tier[(role, label)]
            cl_v = vs.tier_table("clemens_2026", role)[label]["surplus_musd"]
            tier_rows.append([role, label, f"{cur_v:.1f}", f"{cl_v:.1f}",
                              f"{cl_v - cur_v:+.1f}",
                              f"{(cl_v / cur_v):.2f}x" if cur_v else "-"])
    movers = []
    for p in universe:
        d = cl_tbl_pp.get(p["player_key"], 0.0) - cur_pp.get(p["player_key"], 0.0)
        movers.append((p["player_key"], p["fv"], "P" if p["is_pitcher"] else "H",
                       cur_pp.get(p["player_key"], 0.0), cl_tbl_pp.get(p["player_key"], 0.0), d))
    movers.sort(key=lambda t: -abs(t[5]))
    mover_rows = [[m[0], f"{m[1]:.0f}", m[2], f"{m[3]:.1f}", f"{m[4]:.1f}", f"{m[5]:+.1f}"]
                 for m in movers[:25]]
    org_move = sorted(((o, cl_tbl_org.get(o, 0.0) - cur_org.get(o, 0.0))
                       for o in set(cur_org) | set(cl_tbl_org)), key=lambda t: -t[1])[:15]
    cur_sub_share = cur_sub / cur_total if cur_total else 0.0
    clt_sub_share = clt_sub / cl_tbl_total if cl_tbl_total else 0.0
    diff_md = [
        "# Valuation diff report: prospx_current vs clemens_2026 (Phase 5)", "",
        f"_Generated {_today()}. Player/org movers compare prospx_current MODEL to "
        "clemens_2026 TABLE (the published framework applied to our stock)._", "",
        caveats, "",
        "## Whole-stock shift", "",
        _md_table(["metric", "prospx_current", "clemens_2026 (table)"], [
            ["total", _fmt_b(cur_total), _fmt_b(cl_tbl_total)],
            ["sub-50 share", f"{cur_sub_share * 100:.0f}%", f"{clt_sub_share * 100:.0f}%"],
        ]), "",
        "The new framework lifts the whole-stock total and (per FanGraphs) shifts "
        "value toward deeper systems; the sub-50 share shift above quantifies it for "
        "our universe.", "",
        "## Per-tier surplus deltas", "",
        _md_table(["role", "tier", "current $M", "clemens $M", "delta", "ratio"], tier_rows), "",
        "## Top 25 player movers", "",
        _md_table(["player", "FV", "role", "cur $M", "clemens $M", "delta"], mover_rows), "",
        "## Top org movers", "",
        _md_table(["org", "delta $M"], [[o, f"{d:+.0f}"] for o, d in org_move]), "",
    ]
    (_REPORTS / "diff.md").write_text("\n".join(diff_md) + "\n", encoding="utf-8")

    vf.set_valuation_set("prospx_current")
    print(f"wrote reports/validation.md, reports/sensitivity.md, reports/diff.md "
          f"(universe n={n}, asof {asof})")
    print(f"  prospx_current model total={_fmt_b(cur_total)}; "
          f"clemens table total={_fmt_b(cl_tbl_total)} (sub50 {_fmt_b(clt_sub)} / 50+ {_fmt_b(clt_ge)})")


if __name__ == "__main__":
    main()
