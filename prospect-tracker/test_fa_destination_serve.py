# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served FA destination payload (task Q9_19, gate section 16).

docs/fa-2026-10/FA_DESTINATION_GATE.md section 19 named arm N; the payload is
built behind fa_destination.FA_DESTINATION_SERVE (default False) from the
artifact's frozen serving fit through fa_destination's own design builder.
Pinned here:

- the flag is off, the /fa/ shell carries no destination switch while it is
  off, and the exporter writes only the preview path under .cache;
- the served vector reproduces from the frozen coefficients (an independent
  softmax over the Fit twin and incumbency), its coef_hash equals the
  artifact's, and it agrees with the forward-read freeze of section 18;
- no client code multiplies P(enter) into P(signs), and the payload carries no
  P(enter) field;
- every number the Model view prints is a field of the payload, copied from
  the two artifacts (no literal in the client);
- data/fa_class.json, fa_meta.json and the gate artifacts are byte-identical
  with the flag on and off.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

import fa_destination as fd
import fa_export

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FA_JS = ROOT / "assets" / "fa.js"
FROZEN_VECTORS = DATA / "_labs" / "fa_destination" / "frozen_2026_27" / "fa_destination_vectors.json"
UNTOUCHED = ("fa_class.json", "fa_meta.json", "fa_gate2_eval.json", "fa_dpw_series.json",
             "fa_gate3_eval.json", "fa_destination_eval.json")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built():
    import scrapers
    cls = _load("fa_class.json")
    art = _load("fa_destination_eval.json")
    with scrapers.cache_only():
        ctx = fd.winter_context(int(cls["class_year"]))
    payload = fd.served_payload(cls["members"], int(cls["class_year"]), art,
                                _load("fa_gate3_eval.json"), ctx, generated_at="2026-10-14")
    return {"cls": cls, "art": art, "ctx": ctx, "payload": payload}


def test_flag_is_off_and_the_shell_carries_no_switch():
    import build_site
    assert fd.FA_DESTINATION_SERVE is False
    assert build_site._fa_dest_attr() == ""
    assert "data-fa-dest" not in build_site.build_fa()


def test_the_shell_switch_follows_the_flag(monkeypatch):
    import build_site
    monkeypatch.setattr(fd, "FA_DESTINATION_SERVE", True)
    assert build_site._fa_dest_attr() == ' data-fa-dest="live"'


def test_the_served_vector_reproduces_from_the_frozen_coefficients(built):
    art, cls, ctx, payload = built["art"], built["cls"], built["ctx"], built["payload"]
    arm = art["verdict"]["serve"]
    rec = art["reported"]["serving_fit"][arm]
    assert payload["arm"] == arm == "N"
    assert payload["coef_hash"] == rec["coef_hash"] == art["coef_hash"]
    assert set(rec["features"]) == {"fit_analog", "incumbent"}
    tau, gamma = rec["coefs"]["fit_analog"], rec["coefs"]["incumbent"]
    priced = [m for m in cls["members"] if m.get("projGuar") and m.get("projAav")]
    assert len(payload["members"]) == len(priced)
    vec = fd.class_vectors(cls["members"], rec, ctx)
    for k, served in payload["members"].items():
        p = np.asarray(vec[k])
        assert abs(p.sum() - 1.0) < 1e-9
        order = sorted(range(fd.N_CLUBS), key=lambda j: (-p[j], fd.ORGS[j]))[:fd.SERVED_TOP]
        assert [o for o, _ in served["top"]] == [fd.ORGS[j] for j in order]
        for (o, q), j in zip(served["top"], order):
            assert abs(q - p[j]) <= 5e-5 + 1e-12
        assert abs(served["rest_p"] - (1 - sum(p[j] for j in order))) <= 5e-5 + 1e-12
    # an independent softmax over tau x F + gamma x I1 for one member
    k0 = sorted(payload["members"])[0]
    m0 = next(m for m in cls["members"] if m["key"] == k0)
    keys, comps_all, X, names = fd._class_design(cls["members"], rec, ctx, None)
    c0 = comps_all[keys.index(k0)]
    u = np.array([tau * fd.fit_analog(c0[o]) + gamma * c0[o]["incumbent"] for o in fd.ORGS])
    p0 = np.exp(u - u.max()) / np.exp(u - u.max()).sum()
    assert np.allclose(p0, vec[k0], atol=1e-12)
    if m0.get("from") in fd.ORGS:
        assert c0[m0["from"]]["incumbent"] == 1.0


def test_a_tampered_serving_fit_is_refused(built):
    art = json.loads(json.dumps(built["art"]))
    arm = art["verdict"]["serve"]
    art["reported"]["serving_fit"][arm]["coefs"]["incumbent"] += 1e-9
    with pytest.raises(ValueError):
        fd.serving_record(art)


def test_the_served_vector_agrees_with_the_forward_read_freeze(built):
    """Section 18's freeze holds the vectors the forward read scores. The served
    copy rebuilds from the same coefficients on today's cached season-2026 club
    inputs; it may differ only below half a printed percent (a Savant park
    factor page re-fetched after the freeze moves the 5th decimal)."""
    fz = json.loads(FROZEN_VECTORS.read_text(encoding="utf-8"))
    payload = built["payload"]
    assert fz["coef_hash"] == payload["coef_hash"]
    assert set(payload["members"]) <= set(fz["members"])
    orgs = fz["orgs"]
    for k, served in payload["members"].items():
        frozen = dict(zip(orgs, fz["members"][k]["p"]))
        for o, q in served["top"]:
            assert abs(frozen[o] - q) < 0.005, (k, o)
        assert served["top"][0][0] == max(orgs, key=lambda o: (frozen[o], -orgs.index(o)))


def test_payload_shape_counts_only(built):
    payload = built["payload"]
    for key in ("model_id", "generated_at", "class_year", "arm", "coef_hash", "members", "clubs"):
        assert key in payload
    assert payload["model_id"] == "fa_destination"
    assert set(payload["clubs"]) == set(fd.ORGS)
    for c in payload["clubs"].values():
        assert set(c) == {"expected_mlb_deals", "realized_mean"}
    total = sum(c["expected_mlb_deals"] for c in payload["clubs"].values())
    assert abs(total - len(payload["members"])) < 0.2
    raw = json.dumps(payload)
    def field_names(obj, skip_member_keys=False):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if not skip_member_keys:
                    yield k
                yield from field_names(v, k == "members" and obj is payload)
        elif isinstance(obj, list):
            for v in obj:
                yield from field_names(v)
    dollar = [k for k in field_names(payload) if re.search(r"usd|dollar|guar|salary", k, re.I)]
    assert not dollar, dollar
    for v in payload["members"].values():
        assert len(v["top"]) == fd.SERVED_TOP
        assert len(v["drivers"]) == fd.SERVED_DRIVER_CLUBS
        assert all(set(d) <= set(fd.DRIVER_LABELS) and len(d) <= fd.SERVED_DRIVERS for d in v["drivers"])
    assert len(raw.encode("utf-8")) < 80_000


def test_p_enter_is_never_multiplied_in(built):
    raw = json.dumps(built["payload"]).lower()
    assert "enter" not in raw
    js = FA_JS.read_text(encoding="utf-8")
    start = js.index("// ---- Where he signs (fa_destination, Q9_19)")
    end = js.index("// ---- IL days, last three seasons")
    blocks = [js[start:end]]
    for fn in ("function destCardBlock", "function destModelHTML"):
        i = js.index(fn)
        blocks.append(js[i:js.index("\n  }\n", i)])
    for b in blocks:
        assert "enterProb" not in b and "p_enter" not in b
    for line in js.splitlines():
        if "dest" in line.lower() and "enterProb" in line:
            pytest.fail(f"a destination line reads P(enter): {line.strip()}")


def test_the_model_view_prints_only_payload_fields(built):
    js = FA_JS.read_text(encoding="utf-8")
    i = js.index("function destModelHTML")
    body = js[i:js.index("\n  }\n", i)]
    assert not re.search(r"\b0\.\d{2,}\b", body), "a printed number is hardcoded in the Model view"
    model = built["payload"]["model"]
    art = built["art"]
    for arm, row in model["destination"]["metrics"].items():
        for m, v in row.items():
            assert v == round(float(art["metrics"][arm][m]), 4)
    g3 = _load("fa_gate3_eval.json")
    for arm, row in g3["results"].items():
        assert model["gate3"]["rows"][arm] == row
    assert model["destination"]["verdict"]["serve"] == "N"
    assert model["destination"]["clauses"]["P"]["C3"] is False


def _write_both_ways(tmp_path, monkeypatch, on: bool):
    monkeypatch.setattr(fd, "FA_DESTINATION_SERVE", on)
    prev, live = tmp_path / f"prev{on}" / "fa_destinations.json", tmp_path / f"live{on}" / "fa_destinations.json"
    monkeypatch.setattr(fa_export, "DEST_PREVIEW_PATH", prev)
    monkeypatch.setattr(fa_export, "DEST_LIVE_PATH", live)
    cls = _load("fa_class.json")
    before = json.dumps(cls, sort_keys=True)
    import scrapers
    with scrapers.cache_only():
        out = fa_export._write_destinations(cls)
    assert json.dumps(cls, sort_keys=True) == before, "the payload build mutated fa_class"
    return out, prev, live


def test_flag_routes_the_output_and_nothing_else_moves(tmp_path, monkeypatch):
    shas = {n: _sha(DATA / n) for n in UNTOUCHED}
    out_off, prev_off, live_off = _write_both_ways(tmp_path, monkeypatch, False)
    assert out_off and prev_off.exists() and not live_off.exists()
    out_on, prev_on, live_on = _write_both_ways(tmp_path, monkeypatch, True)
    assert out_on and live_on.exists() and not prev_on.exists()
    a = json.loads(prev_off.read_text(encoding="utf-8"))
    b = json.loads(live_on.read_text(encoding="utf-8"))
    assert a == b
    assert {n: _sha(DATA / n) for n in UNTOUCHED} == shas
    assert not (DATA / "fa_destinations.json").exists()


def test_rest_p_and_top_sum_to_one(built):
    for v in built["payload"]["members"].values():
        assert math.isclose(sum(p for _, p in v["top"]) + v["rest_p"], 1.0, abs_tol=1e-3)
