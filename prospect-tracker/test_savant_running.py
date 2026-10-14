"""savant_running.py, offline (baserunning.md 4.5): shape refusals, the fail-soft
fetch, the season-inert board never named, and data/savant_sprint.json never
written. No test here opens a socket: every fetch goes through a fake opener."""
import hashlib
import io
import re
import urllib.error
from pathlib import Path

import pytest

import savant_running as SR

HERE = Path(__file__).resolve().parent

BRV_HEAD = ('"player_id","entity_name","team_name","start_year","end_year","runner_runs_tot",'
            '"runner_runs_XB","runner_runs_SBX","N_runner_moved","N_runner_moved_XB"\n')
STEAL_HEAD = ('"player_id","player_name","team_name","start_year","end_year","key_target_base",'
              '"runs_stolen_on_running_act","n_init","n_sb","n_cs","n_pk"\n')


def _brv(season, rows=((1, 2.5, 1.5, 1.0, 40, 30),)):
    body = "".join(f'{pid},"X, Y","AZ",{season},{season},{t},{xb},{sbx},{n},{nxb}\n'
                   for pid, t, xb, sbx, n, nxb in rows)
    return BRV_HEAD + body


def _steal(season):
    return STEAL_HEAD + f'1,"X, Y","AZ",{season},{season},"All",0.5,300,4,1,0\n'


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(text):
    def op(req, timeout=60):
        return _Resp(text.encode("utf-8"))
    return op


def _failing(req, timeout=60):
    raise urllib.error.URLError("offline")


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(SR, "CACHE_DIR", tmp_path / "savant_running")
    monkeypatch.setattr(SR, "MIN_INTERVAL", 0.0)
    return tmp_path


def test_shape_ok_refuses_another_seasons_rows():
    assert SR.shape_ok(_brv(2024), 2024, "brv")
    assert not SR.shape_ok(_brv(2023), 2024, "brv")
    mixed = _brv(2024) + '2,"A, B","NYY",2025,2025,1,1,0,10,8\n'
    assert not SR.shape_ok(mixed, 2024, "brv")
    assert SR.shape_ok(_steal(2025), 2025, "steal")
    assert not SR.shape_ok(_steal(2025), 2024, "steal")


def test_shape_ok_refuses_a_missing_pinned_field_and_an_empty_board():
    no_xb = _brv(2024).replace('"runner_runs_XB",', "").replace(",1.5,", ",", 1)
    assert not SR.shape_ok(no_xb, 2024, "brv")
    assert not SR.shape_ok(BRV_HEAD, 2015, "brv")          # the 2015 file is header only
    assert not SR.shape_ok("", 2024, "brv")


def test_a_failed_fetch_keeps_the_cache():
    good = SR.fetch_text(2024, "brv", force=True, opener=_opener(_brv(2024)))
    assert SR.parse(good)[1]["runner_runs_XB"] == 1.5
    path = SR.cache_path(2024, "brv")
    before = path.read_bytes()
    assert SR.fetch_text(2024, "brv", force=True, opener=_failing) == good
    assert path.read_bytes() == before


def test_a_refused_response_never_overwrites_the_cache():
    SR.fetch_text(2024, "brv", force=True, opener=_opener(_brv(2024)))
    before = SR.cache_path(2024, "brv").read_bytes()
    got = SR.fetch_text(2024, "brv", force=True, opener=_opener(_brv(2023)))
    assert SR.cache_path(2024, "brv").read_bytes() == before
    assert SR.parse(got)[1]["N_runner_moved_XB"] == 30
    assert SR.fetch_text(2019, "steal", force=True, opener=_opener("<html>error</html>")) == ""
    assert not SR.cache_path(2019, "steal").exists()


def test_one_request_per_board_and_season_with_the_house_user_agent():
    seen = []

    def op(req, timeout=60):
        seen.append((req.full_url, req.get_header("User-agent")))
        return _Resp(_steal(2025).encode("utf-8"))
    SR.fetch_text(2025, "steal", force=True, opener=op)
    url, ua = seen[0]
    assert "season_start=2025" in url and "season_end=2025" in url and "n=1" in url
    assert "basestealing-run-value" in url and ua == SR.UA
    assert SR.MIN_INTERVAL == 0.0 and SR.__dict__.get("_last_request") is not None


def test_the_interval_constant_is_one_point_one_seconds():
    src = (HERE / "savant_running.py").read_text(encoding="utf-8")
    assert re.search(r"^MIN_INTERVAL = 1\.1$", src, re.M)


def test_the_season_inert_board_appears_nowhere():
    src = (HERE / "savant_running.py").read_text(encoding="utf-8")
    assert not re.search(r"/leaderboard/baserunning(?![-\w])", src)
    for url in SR.BOARDS.values():
        assert re.search(r"/leaderboard/(baserunning|basestealing)-run-value\?", url)


def test_sprint_never_writes_the_served_sprint_file(monkeypatch):
    import savant_sprint
    out = HERE / "data" / "savant_sprint.json"
    before = hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None
    csv_text = ('"last_name, first_name","player_id","team","position","age","competitive_runs",'
                '"bolts","hp_to_1b","sprint_speed"\n"Y, X",1,"AZ","CF",25,100,5,4.1,29.5\n')
    monkeypatch.setattr(savant_sprint, "fetch_raw", lambda y, force=False: csv_text)

    def boom(*a, **k):
        raise AssertionError("savant_sprint.build must not run")
    monkeypatch.setattr(savant_sprint, "build", boom)
    rows = SR.sprint_rows(2026)
    assert rows and rows[0]["ft_s"] == 29.5 and rows[0]["season"] == 2026
    after = hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None
    assert before == after
    src = (HERE / "savant_running.py").read_text(encoding="utf-8")
    assert not re.search(r"savant_sprint\.build\s*\(", src)
    assert "OUT" not in re.findall(r"savant_sprint\.(\w+)", src)


def test_cached_text_never_requests(monkeypatch):
    def no_net(*a, **k):
        raise AssertionError("cached_text must not fetch")
    monkeypatch.setattr(SR.urllib.request, "urlopen", no_net)
    assert SR.cached_text(2024, "brv") == ""
    SR.fetch_text(2024, "brv", force=True, opener=_opener(_brv(2024)))
    assert SR.parse(SR.cached_text(2024, "brv"))[1]["runner_runs_tot"] == 2.5
    assert set(SR.load(2024, offline=True)) == {"brv", "steal", "fetched_at"}
