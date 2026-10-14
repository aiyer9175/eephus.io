# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The FA destination forward-read freeze (gate section 14, task Q9_04b commit 2).

Run once, on the day the look passed and before the 2026-27 qualifying-offer
acceptance deadline. Writes two files under data/_labs/ (which ships in neither
deploy consumer) and refuses to overwrite either:

  fa_destination_vectors.json  every priced class member's 30-club vector
                               under the arm the ship rule named, from the
                               artifact's serving fit (its coef_hash), on the
                               winter-start inputs of the served class (season
                               2026 payroll, wins and park factors, the behavior
                               priors through winter 2026, the member's projGuar
                               and projAav).
  fa_fit_teamfits.json         the Fit as served that day: data/fa_class.json's
                               teamFits block and each member's top-3 fits,
                               verbatim, with the file's sha256; beside them,
                               labelled, the 30-club Fit vector recomputed that
                               day by fa_fit.fit_scores (fa_fit_backtest.
                               class_component_matrix), with how it differs from
                               the served blocks, so the forward read can rank
                               every club.

It reads cached pages only, writes nothing else, never calls fa_export and
never multiplies P(enter) into P(signs). The gate document pins both files'
sha256 in a dated section 18 entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fa_destination as fd  # noqa: E402
import fa_fit_backtest as fb  # noqa: E402

EVAL_PATH = ROOT / "data" / "fa_destination_eval.json"
CLASS_PATH = ROOT / "data" / "fa_class.json"
FREEZE_DIR = ROOT / "data" / "_labs" / "fa_destination" / "frozen_2026_27"
VECTORS = "fa_destination_vectors.json"
TEAMFITS = "fa_fit_teamfits.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def concentration(vectors: dict) -> dict:
    """First-club counts of the frozen vectors (gate section 12, reported)."""
    first = Counter(fd.ORGS[max(range(fd.N_CLUBS), key=lambda j: (v[j], -j))]
                    for v in vectors.values())
    n = sum(first.values())
    return {"n": n, "first_club_counts": dict(sorted(first.items(), key=lambda kv: (-kv[1], kv[0]))),
            "distinct_first_clubs": len(first),
            "max_first_share": (max(first.values()) / n) if n else None}


def build_vectors(art: dict, cls: dict, ctx: dict, frozen_on: str) -> dict:
    arm = art["verdict"]["serve"]
    rec = art["reported"]["serving_fit"][arm]
    assert rec["coef_hash"] == art["coef_hash"]
    members = cls["members"]
    vec = fd.class_vectors(members, rec, ctx)
    unpriced = sorted(m["key"] for m in members if m["key"] not in vec)
    by_key = {m["key"]: m for m in members}
    clubs = {o: round(sum(v[j] for v in vec.values()), 6) for j, o in enumerate(fd.ORGS)}
    return {
        "model_id": fd.MODEL_ID, "gate_doc": fd.GATE_DOC, "frozen_on": frozen_on,
        "class_year": cls["class_year"], "arm": arm, "coef_hash": rec["coef_hash"],
        "features": rec["features"], "coefs": rec["coefs"],
        "standardization": rec["standardization"],
        "protocol_sha256": art["protocol_sha256"],
        "eval_artifact": "data/fa_destination_eval.json",
        "eval_artifact_sha256": _sha(EVAL_PATH),
        "inputs": {"fa_class_sha256": _sha(CLASS_PATH),
                   "fa_class_generated_at": cls.get("generated_at"),
                   "winter": ctx["winter"], "season_inputs": ctx["winter"] - 1,
                   "threshold_prev_usd": ctx["threshold_prev_usd"],
                   "payroll_clubs": len(ctx["pay"]), "wins_clubs": len(ctx["wins"]),
                   "park_clubs": sorted(k for k in ctx["park"] if k in fd.ORGS),
                   "park_missing_clubs": sorted(set(fd.ORGS) - set(ctx["park"])),
                   "prior_class_years": ctx["prior_class_years"]},
        "rules": {
            "price": "projGuar as the guarantee, projAav as the AAV (gate section 5, serving column)",
            "need": ("a club has need when any class member (locked or pending option) "
                     "leaves it at his position group, the build_rows proxy on the class"),
            "unpriced": "a member without projGuar or projAav gets no vector",
            "pending_option": "kept; the served copy reads 'if he reaches the market'",
            "p_enter": "never multiplied in",
            "refresh": "never refreshed from in-winter signings (gate section 14)"},
        "counts": {"members": len(members), "vectors": len(vec), "unpriced": unpriced,
                   "pending_option": sum(1 for k in vec if by_key[k].get("status") == "pending_option"),
                   "no_club_of_his_own": sorted(k for k in vec if by_key[k].get("from") not in fd.ORGS)},
        "concentration": concentration(vec),
        "expected_deals_if_every_vector_signs": clubs,
        "orgs": list(fd.ORGS),
        "members": {k: {"name": by_key[k].get("name"), "from": by_key[k].get("from"),
                        "status": by_key[k].get("status"), "pos": by_key[k].get("pos"),
                        "projGuar": by_key[k].get("projGuar"), "projAav": by_key[k].get("projAav"),
                        "p": vec[k]} for k in sorted(vec)},
    }


def build_teamfits(cls: dict, matrix: dict, frozen_on: str) -> dict:
    members = cls["members"]
    keys = [m["key"] for m in members]
    served_top3 = {m["key"]: m.get("fits") or [] for m in members}
    M = {m["key"]: m for m in (matrix.get("members") or [])}
    order_diff, max_fit_diff = 0, 0.0
    for k, top in served_top3.items():
        if k not in M:
            continue
        mine = sorted(M[k]["orgs"].items(), key=lambda kv: (-kv[1]["fit"], kv[0]))[:3]
        if [o for o, _ in mine] != [f["org"] for f in top]:
            order_diff += 1
        for (o, v), f in zip(mine, top):
            max_fit_diff = max(max_fit_diff, abs(float(v["fit"]) - float(f["fit"])))
    return {
        "frozen_on": frozen_on, "class_year": cls["class_year"],
        "source": "data/fa_class.json", "fa_class_sha256": _sha(CLASS_PATH),
        "fa_class_generated_at": cls.get("generated_at"),
        "frame": "pre-free-agency (the Fit is byte-identical under every OUTLOOK answer)",
        "served": {"member_keys": keys, "teamFits": cls["teamFits"],
                   "member_top3_fits": served_top3},
        "recomputed_30_club_fit": {
            "note": ("fa_fit.fit_scores on the served class, recomputed on the freeze day "
                     "through fa_fit_backtest.class_component_matrix; NOT the served export "
                     "(which keeps a member's top 3 and a club's top 12), so it ranks all 30 "
                     "clubs for the forward read; how it differs from the served blocks is "
                     "counted here"),
            "members_recomputed": len(M), "top3_order_differs_from_served": order_diff,
            "max_top3_fit_diff_vs_served": round(max_fit_diff, 6),
            "orgs": matrix.get("orgs"),
            "fit": {k: {o: v["fit"] for o, v in sorted(M[k]["orgs"].items())} for k in sorted(M)}},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frozen-on", default=date.today().isoformat())
    ap.add_argument("--out-dir", type=Path, default=FREEZE_DIR)
    a = ap.parse_args(argv)
    out_v, out_t = a.out_dir / VECTORS, a.out_dir / TEAMFITS
    if out_v.exists() or out_t.exists():
        print(f"refusing: a frozen file exists under {a.out_dir}; the freeze runs once")
        return 2
    art = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    if not art["verdict"]["serve"]:
        print("refusing: the look did not pass; the first forward read is the 2027-28 class")
        return 2
    import scrapers
    cls = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    with scrapers.cache_only():
        ctx = fd.winter_context(int(cls["class_year"]))
        matrix = fb.class_component_matrix(int(cls["class_year"]))
    vdoc = build_vectors(art, cls, ctx, a.frozen_on)
    tdoc = build_teamfits(cls, matrix, a.frozen_on)
    _write(out_v, vdoc)
    _write(out_t, tdoc)
    print(f"{out_v} sha256 {_sha(out_v)}")
    print(f"{out_t} sha256 {_sha(out_t)}")
    print(f"vectors {vdoc['counts']['vectors']} of {vdoc['counts']['members']}; "
          f"unpriced {vdoc['counts']['unpriced']}; concentration {vdoc['concentration']}")
    print(f"recomputed Fit: {tdoc['recomputed_30_club_fit']['members_recomputed']} members, "
          f"top-3 order differs for {tdoc['recomputed_30_club_fit']['top3_order_differs_from_served']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
