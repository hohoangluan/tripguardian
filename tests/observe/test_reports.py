import pytest

from corpus.observe import reports as obs_reports
from corpus.review import reports


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_add_stores_a_report_and_checks_its_fields(data):
    rec = reports.add("0x1:0x2", "  Quán   đã đóng cửa  ", "browser-abc")
    assert (rec["place_id"], rec["text"], rec["reporter"]) == ("0x1:0x2", "Quán đã đóng cửa", "browser-abc")
    assert reports.load() == [rec]
    for bad in (("", "x", "browser-abc"), ("0x1:0x2", "", "browser-abc"), ("0x1:0x2", "x" * 1001, "browser-abc"),
                ("0x1:0x2", "ok", "abc")):
        with pytest.raises(ValueError):
            reports.add(*bad)


def _said(n_people, feature="steep_or_stairs", value="present", place="0x1:0x2"):
    reps = [{"id": f"r{i}", "at": f"2026-10-0{1 + i % 5}T00:00:00+00:00", "place_id": place, "reporter": f"person-{i}",
             "text": "nhiều bậc thang"} for i in range(n_people)]
    said = {r["id"]: [{"feature": feature, "value": value, "quote": "nhiều bậc thang",
                       "context": {"time_of_day": "unknown", "day_type": "unknown", "weather": "unknown"}}]
            for r in reps}
    return reps, said


def test_one_person_never_changes_the_corpus():
    reps, said = _said(obs_reports.REPORTS_MIN - 1)
    assert obs_reports.group(reps, said) == {}


def test_enough_different_people_saying_the_same_becomes_evidence():
    reps, said = _said(obs_reports.REPORTS_MIN)
    assert len(obs_reports.group(reps, said)["0x1:0x2"]) == obs_reports.REPORTS_MIN


def test_one_person_reporting_many_times_counts_once():
    reps, said = _said(1)
    many = [{**reps[0], "id": f"r{i}"} for i in range(obs_reports.REPORTS_MIN + 2)]
    assert obs_reports.group(many, {r["id"]: said["r0"] for r in many}) == {}
