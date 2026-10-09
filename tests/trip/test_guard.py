from trip.domain.guard import bad_say, drop_questions, record_fact, split_lead
from trip.domain.state import TripState

TEXT = "Mình đi 3 ngày, thích chỗ yên tĩnh"


def put(state, field, value, quote, op="set", how="said", text=TEXT, catalog=None, compared=None):
    return record_fact(state, field, op, value, quote, how, text, 1, catalog, compared)


def test_a_quote_that_is_not_in_the_message_is_refused(catalog):
    st, note = put(TripState(), "days", "3", "ba ngày", catalog=catalog)
    assert not st.days.known and note.startswith("refused") and "quote" in note


def test_said_and_inferred_sources(catalog):
    st, _ = put(TripState(), "days", "3", "3 ngày", catalog=catalog)
    st, _ = put(st, "soft", "noise=quiet", "yên tĩnh", op="add", how="inferred", catalog=catalog)
    assert st.days.source == "user" and st.days.confidence == "high"
    assert st.soft["noise=quiet"].source == "inferred"


def test_a_value_that_does_not_parse_is_refused_with_the_reason(catalog):
    st, note = put(TripState(), "days", "nhiều", "3 ngày", catalog=catalog)
    assert not st.days.known and note.startswith("refused")


def test_a_malformed_or_unknown_feature_is_refused_with_the_format_so_the_agent_can_retry(catalog):
    for bad in ("no_such_feature=present", "noise=loudest:love", "noise"):
        st, note = put(TripState(), "soft", bad, "yên tĩnh", op="add", catalog=catalog)
        assert note.startswith("refused") and "feature=value:love|avoid" in note and not st.soft and not st.unmapped


def test_the_agent_can_choose_unmapped_itself(catalog):
    st, note = put(TripState(), "unmapped", "yên tĩnh", "yên tĩnh", op="add", catalog=catalog)
    assert note == "" and [u.phrase for u in st.unmapped] == ["yên tĩnh"]


def test_inference_cannot_overwrite_what_the_user_said(catalog):
    st, _ = put(TripState(), "days", "3", "3 ngày", catalog=catalog)
    st, _ = put(st, "days", "5", "3 ngày", how="inferred", catalog=catalog)
    assert st.days.value == 3


def test_the_at_suffix_is_a_weight_not_a_context(catalog):
    st, _ = put(TripState(), "soft", "crowd=low@love", "yên tĩnh", op="add", catalog=catalog)
    assert st.soft["crowd=low"].value == "love" and not st.unmapped
    st, _ = put(TripState(), "soft", "crowd=low@avoid", "yên tĩnh", op="add", catalog=catalog)
    assert st.soft["crowd=low"].value == "avoid"


def test_inferred_soft_from_a_compared_place_is_kept_only_for_its_traits(catalog):
    compared = [{"id": "0x11:0x1", "name": "Vườn Phẳng Lặng Xanh", "traits": [{"feature": "scenic_view", "value": "present"}]}]
    text = "Không thích quán giống Vườn Phẳng Lặng Xanh"
    st, note = put(TripState(), "soft", "noise=loud:avoid", "giống Vườn Phẳng Lặng Xanh", op="add", how="inferred",
                   text=text, catalog=catalog, compared=compared)
    assert note.startswith("refused") and not st.soft
    st, note = put(TripState(), "soft", "scenic_view=present:avoid", "giống Vườn Phẳng Lặng Xanh", op="add", how="inferred",
                   text=text, catalog=catalog, compared=compared)
    assert note == "" and "scenic_view=present" in st.soft


def test_say_with_a_number_the_user_never_said_is_refused(catalog):
    assert "5" in bad_say("Bạn đi 5 ngày nhỉ.", "Mình đi 3 ngày", TripState(), catalog, set())
    assert bad_say("Bạn đi 3 ngày nhỉ.", "Mình đi 3 ngày", TripState(), catalog, set()) is None


def test_say_naming_a_place_the_user_never_named_is_refused(catalog):
    assert bad_say("Bạn thử Vườn Phẳng Lặng Xanh nhé.", "yên tĩnh", TripState(), catalog, set()) == "names place 0x11:0x1"
    assert bad_say("Bạn thử Vườn Phẳng Lặng Xanh nhé.", "yên tĩnh", TripState(), catalog, {"0x11:0x1"}) is None


def test_drop_questions_keeps_the_acknowledgement():
    assert drop_questions("Mình hiểu rồi. Bạn đi mấy ngày?") == "Mình hiểu rồi."


def test_a_place_name_made_only_of_generic_words_is_not_a_place_mention(catalog):
    assert "du lich da lat" not in {k for k, _ in catalog.name_keys}  # the fixture has none; the rule is on the key
    from trip.domain.guard import GENERIC
    assert set("du lich da lat".split()) <= GENERIC and not set("vuon phang lang xanh".split()) <= GENERIC


def test_the_models_equals_sign_before_the_weight_is_read_as_a_weight(catalog):
    for raw, weight in (("crowd=low=avoid", "avoid"), ("crowd=low:avoid", "avoid"), ("crowd=low@love", "love"), ("crowd=low", "love")):
        st, note = put(TripState(), "soft", raw, "yên tĩnh", op="add", catalog=catalog)
        assert note == "" and st.soft["crowd=low"].value == weight, raw


def test_split_lead_keeps_only_the_question_in_the_card_text():
    assert split_lead("Tuyệt vời! Bạn đi mấy ngày?") == ("Tuyệt vời!", "Bạn đi mấy ngày?")
    assert split_lead("Bạn đi mấy ngày? Và đi cùng ai?") == ("", "Bạn đi mấy ngày? Và đi cùng ai?")
    assert split_lead("Hãy kể thêm về chuyến đi.") == ("", "Hãy kể thêm về chuyến đi.")  # no question: nothing to split
    assert split_lead("Tháng 12 khá lạnh, 10-20°C. Bạn đi tháng mấy?") == ("Tháng 12 khá lạnh, 10-20°C.", "Bạn đi tháng mấy?")
