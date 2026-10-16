from types import SimpleNamespace

from decision.window import change, pages, window

CFG = SimpleNamespace(page_size=4, replace_below=0.3)
R = [f"P{i}" for i in range(10)]


def test_a_page_is_a_slice_of_the_ranking_best_first():
    assert window(R, 0, CFG) == (["P0", "P1", "P2", "P3"], 0)
    assert window(R, 1, CFG) == (["P4", "P5", "P6", "P7"], 1)
    assert pages(len(R), CFG) == 3 and pages(0, CFG) == 1


def test_a_page_past_the_end_shows_the_last_one():
    assert window(R, 9, CFG) == (["P8", "P9"], 2)
    assert window([], 3, CFG) == ([], 0)


def test_change_counts_what_a_new_ranking_did_to_the_page():
    assert change([], ["P0", "P1"], CFG) == {"kept": 0, "added": 0, "removed": 0, "replaced_all": False}  # first look
    assert change(["P0", "P1", "P2", "P3"], ["P0", "P2", "P3", "P9"], CFG) == {
        "kept": 3, "added": 1, "removed": 1, "replaced_all": False}
    assert change(["P0", "P1", "P2", "P3"], ["N0", "N1", "N2", "N3"], CFG)["replaced_all"]
