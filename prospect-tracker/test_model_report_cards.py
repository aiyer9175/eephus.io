"""Model Report Cards v0 guards. The card blocks put proof numbers on the
Models & Proofs view, so the load-bearing risk is a card number drifting from
its eval artifact. These tests are the anti-drift fence: every champion/baseline
must trace to a value in the row's committed artifact (within display rounding),
the card schema must validate, and the number must survive refresh_stamps().
"""
import json
import io
from pathlib import Path

import model_registry as mr

HERE = Path(__file__).parent


def _cards():
    reg = mr.load()
    return [m for m in reg["models"] if m.get("card")]


def _flatten_numbers(obj):
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _flatten_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _flatten_numbers(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.append(float(obj))
    return out


def test_at_least_the_flagship_cards_exist():
    ids = {m["model_id"] for m in _cards()}
    assert {"fa_projection_marcel", "eta", "consensus_fv", "sem_plus"} <= ids


def test_registry_validates_with_cards():
    assert mr.validate() == []


def test_card_numbers_trace_to_artifact():
    """Each headline champion/baseline is a display-rounding of some value in
    the row's eval artifact (abs tol max(0.02, 2% of value))."""
    problems = []
    for m in _cards():
        art = HERE / m["eval_artifact"]
        nums = _flatten_numbers(json.loads(art.read_text(encoding="utf-8")))
        for h in m["card"]["headline"]:
            for role in ("champion", "baseline"):
                target = float(h[role])
                tol = max(0.02, abs(target) * 0.02)
                if not any(abs(target - x) <= tol for x in nums):
                    problems.append(
                        f"{m['model_id']} card {role}={target} not found in {m['eval_artifact']}")
    assert not problems, "\n".join(problems)


def test_refresh_stamps_preserves_card(tmp_path, monkeypatch):
    """refresh_stamps() rewrites the registry monthly; the card field must
    round-trip. Run it against a temp copy so the committed file is untouched."""
    reg = mr.load()
    before = {m["model_id"]: m["card"] for m in reg["models"] if m.get("card")}
    tmp = tmp_path / "reg.json"
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    monkeypatch.setattr(mr, "REGISTRY_PATH", tmp)
    mr.refresh_stamps()
    after = json.loads(tmp.read_text(encoding="utf-8"))
    got = {m["model_id"]: m.get("card") for m in after["models"]}
    for mid, card in before.items():
        assert got.get(mid) == card, f"{mid} card lost or altered by refresh_stamps"
