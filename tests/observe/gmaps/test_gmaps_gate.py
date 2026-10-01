import pytest

from corpus.llm import REVIEW_OBSERVE
from corpus.observe.gmaps.gate import BadAnswer, gate
from corpus.ontology import load

ONT = load()
REFS = {"r1": {"text": "View  đồi thông đẹp,\ncà phê hơi dở. Cuối tuần đông nghẹt"}}


def obs(**kw):
    base = {"feature": "scenic_view", "value": "present", "quote": "View đồi thông đẹp",
            "time_of_day": "unknown", "day_type": "unknown", "weather": "unknown"}
    return {**base, **kw}


def answer(*items):
    return {"reviews": list(items)}


def test_keeps_valid_observations_ignoring_case_and_whitespace():
    kept, proposed, dropped = gate(answer({"ref": "r1", "proposed": [], "observations": [
        obs(), obs(feature="crowd", value="high", quote="cuối tuần  đông nghẹt", day_type="weekend")]}), REFS, ONT)
    assert [(r, o["feature"], o["value"], o["context"]["day_type"]) for r, o in kept] == [
        ("r1", "scenic_view", "present", "unknown"), ("r1", "crowd", "high", "weekend")]
    assert kept[1][1]["quote"] == "cuối tuần  đông nghẹt"
    assert proposed == [] and not dropped


def test_drops_invented_quote_unknown_feature_bad_value_bad_context_unknown_ref():
    kept, _, dropped = gate(answer(
        {"ref": "r1", "proposed": [], "observations": [
            obs(quote="view tuyệt đỉnh"), obs(feature="wifi"), obs(feature="crowd", value="packed", quote="đông nghẹt"),
            obs(day_type="monday"), obs(quote="")]},
        {"ref": "r9", "proposed": [], "observations": [obs()]}), REFS, ONT)
    assert kept == []
    assert dropped == {"quote_not_in_review": 2, "not_in_ontology": 2, "bad_context": 1, "unknown_ref": 1}


def test_proposed_needs_label_and_real_quote():
    _, proposed, dropped = gate(answer({"ref": "r1", "observations": [], "proposed": [
        {"label": "pine smell", "quote": "đồi thông"}, {"label": "wifi", "quote": "wifi mạnh"}, {"label": "", "quote": "đồi thông"}]}),
        REFS, ONT)
    assert proposed == [("r1", {"label": "pine smell", "quote": "đồi thông"})]
    assert dropped == {"proposed_bad_quote": 2}


def test_malformed_answer_raises():
    with pytest.raises(BadAnswer):
        gate({"foo": 1}, REFS, ONT)


def test_review_observe_prompt_renders():
    text = REVIEW_OBSERVE.render(city="Đà Lạt", name="Quán A", category="Quán cà phê", ontology=ONT.prompt_text(),
                                 reviews='r1: {"a": 1}', note="")
    assert "Quán A (Quán cà phê)" in text and "- crowd = low | medium | high:" in text and 'r1: {"a": 1}' in text
