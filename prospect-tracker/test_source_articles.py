from pathlib import Path

from source_articles import (
    parse_source_article_drops,
    parse_ba_statcast_by_age,
    parse_ba_top100_list,
    parse_ba_top100_movement,
)


def test_parse_ba_top100_list(tmp_path: Path):
    p = tmp_path / "2026_06_03_BA_t100list.txt"
    p.write_text(
        "Headshot of Josh Adamczewski\n"
        "79. Josh Adamczewski\n"
        "Milwaukee Brewers\n"
        "| OF\n",
        encoding="utf-8",
    )

    snapshots, events = parse_ba_top100_list(p)

    assert snapshots[0].player_key == "josh_adamczewski"
    assert snapshots[0].source == "baseballamerica"
    assert snapshots[0].rank == 79
    assert snapshots[0].org == "MIL"
    assert events[0]["event_type"] == "top100_rank"
    assert events[0]["rank_after"] == 79


def test_parse_ba_top100_movement_joined_dropped_and_table(tmp_path: Path):
    p = tmp_path / "2026-06-03_top100_movement.txt"
    p.write_text(
        "Joined\n"
        "Josh Adamczewski, 2B/OF, Brewers (No. 79, added in-month)\n"
        "Dropped\n"
        "Kyson Witherspoon, RHP, Red Sox (Was No. 73)\n"
        "Player\tOrg\tJAN\tAPR\tDIF\tMAY\tDIF\tJUNE\tDIF\n"
        "Aidan Miller\tPhillies\t14\t17\t-3\t30\t-13\t61\t-31\n",
        encoding="utf-8",
    )

    events = parse_ba_top100_movement(p)
    by_type = {e["event_type"]: e for e in events if e["player_key"] != "aidan_miller"}
    aidan = next(e for e in events if e["player_key"] == "aidan_miller")

    assert by_type["top100_joined"]["player_key"] == "josh_adamczewski"
    assert by_type["top100_dropped"]["player_key"] == "kyson_witherspoon"
    assert aidan["event_type"] == "top100_movement"
    assert aidan["rank_before"] == 30
    assert aidan["rank_after"] == 61
    assert aidan["payload"]["june_diff"] == -31


def test_parse_ba_statcast_by_age_table(tmp_path: Path):
    p = tmp_path / "2026-06-03_statcast_byage.txt"
    p.write_text(
        "Age 21\n"
        "PLAYER\tPOS\tORG\tTEAM\tBATS\tAGE\tPA\tZCON\tCHASE\tHIT95+\t90TH EV\n"
        "Josh Adamczewski\tOF\tMIL\tWisconsin\tL\t21\t173\t83%\t18%\t51.50%\t105.8\n",
        encoding="utf-8",
    )

    events = parse_ba_statcast_by_age(p)

    assert events[0]["event_type"] == "statcast_by_age_standout"
    assert events[0]["player_key"] == "josh_adamczewski"
    assert events[0]["payload"]["pa"] == 173
    assert events[0]["payload"]["p90_ev"] == "105.8"


def test_statcast_by_age_snapshot_carries_no_fabricated_grade(tmp_path: Path):
    """The BA age-band statcast table publishes NO grade, so our snapshot must not
    invent one.

    This assertion is INVERTED from what it was. It used to pin `fv == 40.0`, a
    constant source_articles assigned itself and consensus.avg_fv then counted as a
    published vote at full weight. Measured 2026-07-30: 34 of the 41 live rows landed
    on players who already carried a real grade. Owner decision: the source carries
    identity + statcast context and nothing else. If this ever goes back to a number,
    it is a fabricated consensus vote again.
    """
    (tmp_path / "2026-06-03_statcast_byage.txt").write_text(
        "Age 18\n"
        "PLAYER\tPOS\tORG\tTEAM\tBATS\tAGE\tPA\tZCON\tCHASE\tHIT95+\t90TH EV\n"
        "Richard Matic\t3B\tNYY\tFCL Yankees\tR\t18\t99\t89%\t15%\t43.30%\t102.5\n",
        encoding="utf-8",
    )

    snapshots, events = parse_source_article_drops(tmp_path)

    richard = next(s for s in snapshots if s.player_key == "richard_matic")
    assert richard.source == "baseballamerica_statcast_by_age"
    assert richard.fv is None
    assert richard.rank is None      # and no rank either: this source has neither
    # The row still carries identity so the player stays tracked, and the statcast
    # read still reaches source_events.
    assert richard.position == "3B"
    assert richard.status == "active"
    assert any(e["player_key"] == "richard_matic" for e in events)


def test_no_source_article_snapshot_invents_a_grade(tmp_path: Path):
    """Guard the CLASS, not just the one source: nothing this parser emits may carry
    an FV unless the outlet printed a number we parsed. Today that means every
    source_articles snapshot is grade-free (BA prints ranks on the Top 100 and
    nothing on the statcast table)."""
    (tmp_path / "2026_06_03_BA_t100list.txt").write_text(
        "18. Josuar Gonzalez\nSan Francisco Giants\n| SS\n", encoding="utf-8")
    (tmp_path / "2026-06-03_statcast_byage.txt").write_text(
        "Age 18\n"
        "PLAYER\tPOS\tORG\tTEAM\tBATS\tAGE\tPA\tZCON\tCHASE\tHIT95+\t90TH EV\n"
        "Richard Matic\t3B\tNYY\tFCL Yankees\tR\t18\t99\t89%\t15%\t43.30%\t102.5\n",
        encoding="utf-8")

    snapshots, _events = parse_source_article_drops(tmp_path)

    assert snapshots, "expected at least one snapshot"
    graded = [(s.source, s.player_key, s.fv) for s in snapshots if s.fv is not None]
    assert not graded, f"source_articles emitted an FV nobody published: {graded}"


def test_statcast_by_age_does_not_add_snapshot_when_top100_exists(tmp_path: Path):
    (tmp_path / "2026_06_03_BA_t100list.txt").write_text(
        "18. Josuar Gonzalez\n"
        "San Francisco Giants\n"
        "| SS\n",
        encoding="utf-8",
    )
    (tmp_path / "2026-06-03_statcast_byage.txt").write_text(
        "Age 18\n"
        "PLAYER\tPOS\tORG\tTEAM\tBATS\tAGE\tPA\tZCON\tCHASE\tHIT95+\t90TH EV\n"
        "Josuar Gonzalez\tSS\tSF\tACL Giants\tS\t18\t49\t82%\t16%\t53.80%\t106.2\n",
        encoding="utf-8",
    )

    snapshots, _events = parse_source_article_drops(tmp_path)

    josuar = [s for s in snapshots if s.player_key == "josuar_gonzalez"]
    assert len(josuar) == 1
    assert josuar[0].source == "baseballamerica"
