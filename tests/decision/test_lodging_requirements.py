import pytest

from agents import ToolError
from decision import Data, Engine, Store, Tools, load_settings
from fixtures import hard, si, srec


@pytest.mark.parametrize("feature,value,features", [
    ("steep_or_stairs", "present", {"steep_or_stairs": "present"}),
    ("steep_or_stairs", "present", {}),
    ("parking", "hard", {"parking": "hard"}),
])
def test_user_selected_corpus_lodging_still_checks_trip_requirements(feature, value, features):
    record = srec("stay", group="stay", category="Khách sạn", features=features)
    engine = Engine(Data([record]), load_settings(), Store(None))
    view = engine.create(si(hard_filters=[hard(feature, value)]).model_dump(mode="json"))
    with pytest.raises(ValueError, match="requirement"):
        engine.act(view["id"], {"type": "set_lodging", "lodging": {"kind": "corpus", "id": "stay"}})


def test_eating_requirement_does_not_apply_to_accommodation_selection():
    engine = Engine(Data([srec("stay", group="stay", category="Khách sạn")]), load_settings(), Store(None))
    view = engine.create(si(hard_filters=[hard("vegetarian_options", "yes", op="eq")]).model_dump(mode="json"))
    out = engine.act(view["id"], {"type": "set_lodging", "lodging": {"kind": "corpus", "id": "stay"}})
    assert out["view"]["lodging"]["chosen"]["id"] == "stay"


@pytest.mark.parametrize("features", [{"steep_or_stairs": "present"}, {}])
def test_rebased_requirements_block_lodging_handoff_without_losing_selection(features):
    records = [srec("cafe", features={"steep_or_stairs": "absent"}),
               srec("stay", group="stay", category="Khách sạn", features=features)]
    engine = Engine(Data(records), load_settings(), Store(None))
    tools = Tools(engine)
    sid = tools.create({"search_input": si().model_dump(mode="json")})["id"]
    engine.act(sid, {"type": "select", "place_id": "cafe"})
    engine.act(sid, {"type": "set_lodging", "lodging": {"kind": "corpus", "id": "stay"}})
    tools.rebase(sid, {"search_input": si(hard_filters=[hard("steep_or_stairs", "present")]).model_dump(mode="json")})

    assert tools.read(sid, "draft", {})["output"] is None
    with pytest.raises(ToolError, match="lodging requirement") as error:
        tools.apply(sid, "confirm", {}, lambda *_: None)
    assert error.value.status == 409
    assert engine.store.get(sid).output is None
    assert engine.load(sid)["view"]["selected"] == ["cafe"]
    assert engine.load(sid)["view"]["lodging"]["chosen"]["id"] == "stay"

    # The recovery read still supplies context to browse replacement lodging.
    assert tools.read(sid, "draft", {"any": True})["output"]["lodging"]["id"] == "stay"
    engine.act(sid, {"type": "clear_lodging"})
    assert tools.apply(sid, "confirm", {}, lambda *_: None)["confirmed"][0]["id"] == "cafe"


def test_booked_corpus_lodging_also_checks_current_requirements_at_handoff():
    records = [srec("cafe", features={"steep_or_stairs": "absent"}),
               srec("stay", group="stay", category="Khách sạn")]
    engine = Engine(Data(records), load_settings(), Store(None))
    tools = Tools(engine)
    booked = {"kind": "corpus", "place_id": "stay", "text": "Stay", "lat": 11.94, "lng": 108.44}
    search_input = si(context={"lodging_booked": "yes", "lodging": booked},
                      hard_filters=[hard("steep_or_stairs", "present")])
    sid = tools.create({"search_input": search_input.model_dump(mode="json")})["id"]
    engine.act(sid, {"type": "select", "place_id": "cafe"})
    assert tools.read(sid, "draft", {})["output"] is None
    with pytest.raises(ToolError, match="lodging requirement"):
        tools.apply(sid, "confirm", {}, lambda *_: None)
