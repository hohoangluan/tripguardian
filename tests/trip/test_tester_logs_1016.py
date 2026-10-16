"""Regressions from the testers' sessions of 2026-10-16 (logs/run/trip_turns.log)."""

import json
from datetime import date, timedelta

from trip.agent.tools import TurnTools, complete_facts
from trip.domain.dates import exact_date
from trip.domain.guard import bad_say, names_group, record_fact, trim_say
from trip.domain.prepass import prepass
from trip.domain.readiness import missing
from trip.domain.state import TripState

TODAY = date(2026, 10, 16)


def dates(text):
    return [(p.field, p.value) for p in prepass(text, TODAY).proposals if p.field in ("start_date", "days")]


# ---------- dates the user wrote in full ----------

def test_from_one_date_to_another_is_the_start_and_the_length():
    # was read as 10/10/2027 and 11 days: the range rule took the first date's month as a day
    assert dates("đi từ 17/10 đến 20/10") == [("start_date", date(2026, 10, 17)), ("days", 4)]


def test_a_date_in_words_with_its_year_is_the_start():
    text = "Đi từ 0h30 sáng ngày 17 tháng 10 năm 2026 đến 5h chiều ngày 20 tháng 10 năm 2026"
    assert dates(text) == [("start_date", date(2026, 10, 17)), ("days", 4)]


def test_a_said_trip_length_wins_over_the_calendar_span():
    text = "3 ngày 2 đêm, đi từ ngày 17 tháng 10 năm 2026 đến ngày 20 tháng 10 năm 2026"
    assert dates(text) == [("start_date", date(2026, 10, 17)), ("days", 3)]


def test_a_written_year_is_kept():
    assert dates("đi 17/10/2027") == [("start_date", date(2027, 10, 17))]


def test_a_day_range_in_words_is_read():
    assert dates("từ 17 đến 20 tháng 10") == [("start_date", date(2026, 10, 17)), ("days", 4)]


def test_record_fact_takes_a_full_date_with_its_year():
    for words in ("17 tháng 10 năm 2026", "ngày 17 tháng 10 năm 2026", "17/10/2026"):
        assert exact_date(words, TODAY) == date(2026, 10, 17), words
    assert exact_date("in a week", TODAY) == TODAY + timedelta(days=7)


# ---------- who goes ----------

def test_alone_in_english_names_solo():
    for quote in ("No one", "alone", "just me", "by myself"):
        assert names_group(quote, "solo"), quote


# ---------- care notes ----------

def test_an_allergy_kept_in_the_users_words_answers_care(catalog):
    st, note = record_fact(TripState(), "unmapped", "add", "Có dị ứng lạc", "Có dị ứng lạc", "said",
                           "Có dị ứng lạc", 1, catalog)
    assert note == "" and st.care.value == "listed" and st.care.source == "user"
    assert "care" not in dict(missing(st))


def test_a_wish_that_is_no_care_note_leaves_care_open(catalog):
    st, _ = record_fact(TripState(), "unmapped", "add", "kỷ niệm 3 năm", "kỷ niệm 3 năm", "said",
                        "kỷ niệm 3 năm", 1, catalog)
    assert not st.care.known


def test_a_longer_telling_of_the_same_wish_replaces_it(catalog):
    st, _ = record_fact(TripState(), "unmapped", "add", "Có dị ứng lạc", "Có dị ứng lạc", "said", "Có dị ứng lạc", 1, catalog)
    longer = "Có dị ứng lạc; cần tránh cả nguy cơ lẫn lạc do dùng chung dụng cụ chế biến"
    st, _ = record_fact(st, "unmapped", "add", longer, "Có", "said", "Có", 2, catalog, history=((1, "Có dị ứng lạc"),))
    assert [u.phrase for u in st.unmapped] == [longer]


# ---------- replies ----------

def test_a_long_reply_is_never_cut_inside_a_sentence():
    say = ("Mình chưa có thông tin được kiểm chứng để giới thiệu một cửa hàng thuê xe cụ thể. Khi thuê, bạn nên chọn "
           "nơi có hợp đồng rõ ràng, kiểm tra phanh, lốp, đèn và quay lại tình trạng xe lúc nhận; đồng thời bảo đảm "
           "giấy phép lái xe của bạn hợp lệ với loại xe thuê.")
    assert trim_say(say) == "Mình chưa có thông tin được kiểm chứng để giới thiệu một cửa hàng thuê xe cụ thể."


def test_a_long_lead_before_the_question_ends_at_a_clause():
    say = ("Bạn tự lái ô tô cùng người yêu, muốn ngắm cảnh, săn mây, uống cà phê và đi chợ đêm, cần nơi có bãi đỗ ô tô "
           "và hạn chế đường dốc. Mình cần làm rõ mốc thời gian: 0h30 ngày 17/10 là giờ xuất phát từ TP.HCM và 17h "
           "ngày 20/10 là giờ phải có mặt lại TP.HCM, đúng không?")
    out = trim_say(say)
    assert len(out) <= 250 and out.endswith("đúng không?")
    assert not out.split(". ")[0].endswith((" và", " với", " của"))


def test_a_limit_the_tool_gave_may_be_said_back(catalog):
    st = TripState()
    assert bad_say("Mình chỉ hỗ trợ tối đa 20 người.", "6 triệu người", st, catalog, set(),
                   told="people=6000000 is out of range (1, 20)") is None
    assert bad_say("Mình chỉ hỗ trợ tối đa 20 người.", "6 triệu người", st, catalog, set()) is not None


# ---------- facts shown while the reply is still being written ----------

def test_complete_facts_reads_only_the_finished_objects():
    head = '{"facts": [{"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}, {"field": "pa'
    assert complete_facts(head) == [{"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}]
    assert complete_facts('{"facts": [{"field": "x", "quote": "a } b"}') == [{"field": "x", "quote": "a } b"}]
    assert complete_facts('{"say": "hi"') == []


def test_a_finished_fact_reaches_the_screen_before_the_call_ends(catalog):
    text = "Có dị ứng lạc, đi 3 ngày"
    seen = []
    tools = TurnTools(TripState(), text, 1, catalog, TODAY, on_state=seen.append)
    args = json.dumps({"facts": [{"field": "unmapped", "op": "add", "value": "Có dị ứng lạc", "quote": "Có dị ứng lạc"},
                                 {"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}], "say": "Ok"},
                      ensure_ascii=False)
    tools.preview(args[:args.index('{"field": "days"')])
    assert len(seen) == 1 and seen[0].care.value == "listed" and not seen[0].days.known
    tools.preview(args)
    assert len(seen) == 2 and seen[1].days.value == 3
    assert not tools.state.care.known and not tools.recorded  # a preview writes nothing


# ---------- what the words already answer is not asked again ----------

from trip.domain.derive import derive  # noqa: E402
from trip.domain.state import Evidence, Update, apply  # noqa: E402


def said(state, field, value, quote, op="set"):
    return apply(state, Update(field=field, op=op, value=value, source="user", confidence="high",
                               evidence=Evidence(turn=1, quote=quote)))


def test_alone_is_one_person_and_a_partner_two(catalog):
    st = derive(said(TripState(), "companions", ["solo"], "1 mình"), catalog, 1)
    assert st.people.value == 1 and "companions" not in dict(missing(st))
    st = derive(said(TripState(), "companions", ["partner"], "với người yêu"), catalog, 1)
    assert st.people.value == 2
    st = derive(said(st, "companions", "friends", "và 2 bạn", op="add"), catalog, 2)
    assert not st.people.known  # the party grew: how many is asked


def test_a_said_count_is_never_replaced(catalog):
    st = said(said(TripState(), "people", 3, "3 người"), "companions", ["partner"], "với người yêu")
    assert derive(st, catalog, 1).people.value == 3


def test_staying_near_the_centre_is_the_lodging_point(catalog):
    from trip.domain.state import Base
    st = derive(said(TripState(), "base", Base(text="khách sạn 5 sao gần trung tâm"), "gần trung tâm"), catalog, 1)
    assert st.lodging.known and st.lodging.value.lat and "lodging" not in dict(missing(st))
    st = derive(said(TripState(), "base", Base(text="homestay"), "homestay"), catalog, 1)
    assert not st.lodging.known  # where exactly is still asked


def test_a_knee_the_user_named_gets_the_care_limit_without_a_question(catalog):
    from trip.domain.state import Signal
    st = TripState().model_copy(update={"signals": (Signal(kind="knee", quote="bà ngoại đau gối", turn=1),)})
    st = derive(st, catalog, 1)
    assert {h.feature for h in st.hard} >= {"steep_or_stairs", "long_walk"}
    assert "care" not in dict(missing(st))



def test_an_hour_only_arrival_lands_on_the_first_and_last_day(catalog):
    st = said(said(TripState(), "start_date", date(2026, 12, 24), "24/12"), "days", 4, "4 ngày")
    tools = TurnTools(st, "tới 15h ngày đầu về 11h ngày cuối", 1, catalog, TODAY)
    tools.run("record_fact", {"facts": [
        {"field": "frame.arrive", "op": "set", "value": '{"at":"first_dayT15:00"}', "quote": "tới 15h ngày đầu",
         "how": "said"},
        {"field": "frame.leave", "op": "set", "value": "11:00", "quote": "về 11h ngày cuối", "how": "said"}]})
    assert tools.state.frame.arrive.value.at == "2026-12-24T15:00"
    assert tools.state.frame.leave.value.at == "2026-12-27T11:00"


def test_a_date_said_in_an_earlier_turn_is_read(catalog):
    tools = TurnTools(TripState(), "No one, just me", 2, catalog, TODAY, history=((1, "Leaving in a week."),))
    out = tools.run("record_fact", {"facts": [{"field": "start_date", "op": "set", "value": "in a week",
                                               "quote": "Leaving in a week", "how": "said"}]})
    assert "error" not in out and tools.state.start_date.value == TODAY + timedelta(days=7)


def test_a_stay_kept_as_a_wish_becomes_the_lodging_when_it_says_where(catalog):
    st, _ = record_fact(TripState(), "unmapped", "add", "ở khách sạn 5 sao bất kỳ gần trung tâm thành phố",
                        "ở khách sạn 5 sao bất kỳ gần trung tâm thành phố", "said",
                        "ở khách sạn 5 sao bất kỳ gần trung tâm thành phố", 1, catalog)
    st = derive(st, catalog, 1)
    assert st.lodging.known and not st.unmapped


def test_only_the_sentence_with_an_invented_figure_is_dropped():
    from trip.domain.guard import prune_say
    say = "Bạn đi cùng người yêu, tự lái ô tô. Chuyến này là 4 ngày nhé. Bạn xuất phát lúc 0h30 đúng không?"
    out = prune_say(say, lambda x: "numbers" if "4" in x else None)
    assert out == "Bạn đi cùng người yêu, tự lái ô tô. Bạn xuất phát lúc 0h30 đúng không?"


def test_a_question_on_how_strict_a_said_limit_is_counts_as_a_re_ask():
    from trip.domain.guard import asks_settled_care
    assert asks_settled_care("Gia đình có hai bé. Bà đi bộ đoạn ngắn và lên vài bậc thang được không?")
    assert asks_settled_care("Bạn ấy có cần tránh cả món có nguy cơ tiếp xúc chéo với lạc không?")
    assert not asks_settled_care("Chill với bạn là ngồi cà phê ngắm đồi, hay dạo hồ buổi chiều?")
    assert not asks_settled_care("Bạn muốn ở gần trung tâm hay gần hồ?")


def test_the_same_question_twice_in_a_row_is_a_re_ask():
    from trip.domain.guard import same_question
    first = ("Bạn đi cùng người yêu, tự lái ô tô. Bạn nói 3 ngày 2 đêm nhưng mốc đi–về trải từ 17 đến 20/10: ý bạn là "
             "xuất phát từ TP.HCM lúc 0h30 ngày 17/10 và có mặt lại TP.HCM lúc 17h ngày 20/10, còn thời gian ở Đà Lạt "
             "là 3 ngày 2 đêm, đúng không?")
    again = ("Mình hiểu bạn không giới hạn chi phí. Về thời gian, bạn xuất phát từ TP.HCM lúc 0h30 ngày 17/10 và có "
             "mặt lại TP.HCM lúc 17h ngày 20/10, còn ở Đà Lạt 3 ngày 2 đêm, đúng không?")
    assert same_question(again, first)
    assert not same_question("Bạn muốn đi chậm hay nhiều nơi?", first)
    assert not same_question("Mình ghi lại rồi.", first)


def test_each_fact_shows_its_line_while_the_call_is_written(catalog):
    text = "đi với người yêu 3 ngày"
    traces = []
    tools = TurnTools(TripState(), text, 1, catalog, TODAY, on_trace=traces.append, on_state=lambda st: None)
    args = json.dumps({"facts": [{"field": "companions", "op": "add", "value": "partner", "quote": "với người yêu"},
                                 {"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}]}, ensure_ascii=False)
    tools.preview(None)
    tools.preview(args[:args.index('{"field": "days"')])
    labels = [s["label"] for s in traces[-1]["steps"]]
    assert any("“với người yêu”" in x for x in labels) and not any("3 ngày" in x for x in labels)
    assert traces[-1]["steps"][0]["id"] == "split" and traces[-1]["steps"][0]["status"] == "ok"
    tools.preview(args)
    assert any("“3 ngày”" in s["label"] and s["status"] == "run" for s in traces[-1]["steps"])
