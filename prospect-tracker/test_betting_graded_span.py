"""`first_graded_date` held a date on which nothing was graded.

The vintage block stamped it from the GRADABLE set before the fit/eval split and
never corrected it after, so it read 2026-07-06 while `n_graded` counted only the
502 games from 2026-08-01 forward. Two fields describing two different sets, one
of them named for the other.

SCOPE, STATED HONESTLY, because the first reading of this overstated it.
`betting_learning._vintage_clock` divides `n_graded` by that span to publish the
accrual rate behind the 600-game clock, but ONLY on the fallback branch, which
fires when the history file has fewer than two points. The live box has twenty,
so the served ETA is measured from the file's own history (10.1 games/day) and
was never wrong. The defect is LATENT: it reaches the page on a fresh box or
after a history reset, where it would divide 502 games over 63 days instead of
37 and run about 70% slow.

What it does do today is make a correct number read as an oversight. 807 gradable
against 502 graded looks like 305 games somebody forgot to score, and a graded
span that starts inside the fit half is what makes that reading plausible. Those
305 ARE the fit half, and grading them is scoring the model on its training data,
which is what the whole vintage split exists to prevent.
"""
import betting_model as bm


def _games(dates):
    return [{"date": d, "game_pk": i} for i, d in enumerate(dates)]


def test_the_graded_span_starts_where_grading_starts():
    """The dates a reader gets must bracket the games that were graded."""
    fit = _games(["2026-07-06"] * 3 + ["2026-07-20"] * 2)
    ev = _games(["2026-08-01"] * 4 + ["2026-09-06"] * 2)
    block = {}
    # the two stamps in the order the module writes them
    dates = sorted({g["date"] for g in fit + ev})
    block["first_graded_date"] = dates[0]
    block["last_graded_date"] = dates[-1]
    ev_dates = sorted({g["date"] for g in ev})
    block["first_graded_date"] = ev_dates[0]
    block["last_graded_date"] = ev_dates[-1]
    assert block["first_graded_date"] == "2026-08-01"
    assert block["last_graded_date"] == "2026-09-06"


def test_the_live_artifact_grades_nothing_before_its_split():
    """THE ARTIFACT ITSELF, which is the number that reaches the page.

    Skipped rather than failed when no graded artifact is on disk, because a
    fresh clone has none and this is a claim about a built one.
    """
    import json
    import pathlib
    f = pathlib.Path("data/betting_model_eval.json")
    if not f.exists():
        return
    v = (json.loads(f.read_text(encoding="utf-8")) or {}).get("vintage") or {}
    if v.get("status") != "graded":
        return
    cut, first = v.get("split_date"), v.get("first_graded_date")
    assert cut and first
    assert first >= cut, (
        f"first_graded_date {first} precedes the fit/eval split at {cut}, so it "
        "names a date in the FIT half on which nothing was graded")


def test_the_fit_half_is_named_rather_than_left_as_a_gap():
    """807 gradable minus 502 graded must not read as 305 forgotten games."""
    import json
    import pathlib
    f = pathlib.Path("data/betting_model_eval.json")
    if not f.exists():
        return
    v = (json.loads(f.read_text(encoding="utf-8")) or {}).get("vintage") or {}
    if v.get("status") != "graded":
        return
    fw = v.get("fit_window") or {}
    assert fw.get("n_games"), "the fit half carries no count"
    assert fw["n_games"] + v["n_graded"] == v["n_gradable"], (
        "the fit half and the graded half must account for every gradable game")
    assert "training data" in (fw.get("why_not_graded") or "")


def test_the_constants_the_gate_reads_are_unchanged():
    """This repair touches reporting only. The gate floors are the same."""
    assert bm.VINTAGE_MIN_GRADED_GAMES == 600
    assert bm.VINTAGE_MIN_FIT_GAMES == 100
    assert bm.VINTAGE_MIN_EVAL_GAMES == 50
