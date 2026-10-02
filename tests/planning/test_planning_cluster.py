from plan_fixtures import CFG, line_travel

from planning.cluster import cluster_places, distance, split_to_fit


def test_places_of_one_area_that_are_close_form_one_cluster():
    travel = line_travel({"a": 0, "b": 1, "c": 2, "x": 10, "y": 11})                      # 5 minutes per unit
    got = cluster_places(["a", "b", "c", "x", "y"], {"a": "A", "b": "A", "c": "A", "x": "B", "y": "B"}, travel, CFG)
    assert got == [["a", "b", "c"], ["x", "y"]]


def test_a_cluster_is_cut_where_the_real_travel_gets_too_long():
    travel = line_travel({"a": 0, "b": 1, "far": 20})                                    # 100 minutes to "far"
    assert cluster_places(["a", "b", "far"], {}, travel, CFG) == [["a", "b"], ["far"]]


def test_the_farthest_members_decide_not_the_nearest_neighbours():
    travel = line_travel({"a": 0, "b": 4, "c": 8})        # a-b and b-c are 20, but a-c is 40 > cluster_max_min 25
    assert cluster_places(["a", "b", "c"], {}, travel, CFG) == [["a", "b"], ["c"]]


def test_clusters_of_different_areas_merge_only_when_they_touch():
    travel = line_travel({"a": 0, "b": 1})                                               # 5 minutes apart
    assert cluster_places(["a", "b"], {"a": "A", "b": "B"}, travel, CFG) == [["a", "b"]]
    travel = line_travel({"a": 0, "b": 4})                                               # 20 minutes apart
    assert cluster_places(["a", "b"], {"a": "A", "b": "B"}, travel, CFG) == [["a"], ["b"]]


def test_a_place_with_no_area_is_clustered_by_distance_alone():
    travel = line_travel({"a": 0, "b": 1})
    assert cluster_places(["a", "b"], {"a": None, "b": None}, travel, CFG) == [["a", "b"]]


def test_the_result_does_not_depend_on_the_input_order():
    travel = line_travel({"a": 0, "b": 1, "c": 2, "x": 30})
    assert cluster_places(["x", "c", "a", "b"], {}, travel, CFG) == cluster_places(["a", "b", "c", "x"], {}, travel, CFG)


def test_distance_is_symmetric_even_when_the_matrix_is_not():
    travel = line_travel({"a": 0, "b": 4})
    travel.legs[0][1] = (30, "motorbike")                                                # one way is slower
    assert distance("a", "b", travel) == distance("b", "a", travel) == 30


def test_a_cluster_too_big_for_a_day_is_split_around_its_farthest_pair():
    travel = line_travel({"a": 0, "b": 1, "c": 10, "d": 11})
    load = lambda ids: 60 * len(ids)
    assert split_to_fit([["a", "b", "c", "d"]], load, 150, travel) == [["a", "b"], ["c", "d"]]


def test_a_cluster_that_fits_is_left_alone_and_a_single_place_is_never_split():
    travel = line_travel({"a": 0, "b": 1})
    assert split_to_fit([["a", "b"]], lambda ids: 100, 150, travel) == [["a", "b"]]
    assert split_to_fit([["a"]], lambda ids: 999, 150, travel) == [["a"]]
