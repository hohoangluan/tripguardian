"""The typed hand-off accepts wishes before downstream ranking starts using them."""

from plan_fixtures import sample_trip
from test_planning_trip_gate import engine

from decision import DecisionOutput
from trip import SearchInput, TripState, compile_search_input


def test_nonempty_wishes_validate_and_can_be_planned():
    decision, records = sample_trip()
    pid = records[0]["id"]
    wishes = {"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": [pid]}],
              "kinds": [{"kind": "karaoke", "quote": "karaoke", "place_ids": [pid]}],
              "like": [{"place_id": pid, "but": ["crowd=low"], "quote": "giống quán này nhưng vắng hơn"}]}
    decision["trip_context"]["wishes"] = wishes
    decision["trip_context"]["ontology_version"] = compile_search_input(TripState()).ontology_version
    si = SearchInput.model_validate(decision["trip_context"])
    assert si.model_dump(mode="json")["wishes"] == wishes
    assert DecisionOutput.model_validate(decision).trip_context.wishes == si.wishes
    assert engine(records).create(decision)["id"]
