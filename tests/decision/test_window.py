from types import SimpleNamespace

from decision.window import extend, merge

CFG = SimpleNamespace(page_size=4, keep_factor=2, replace_below=0.3)
R = [f"P{i}" for i in range(20)]


def test_first_window_is_the_top_page():
    win, ch = merge([], R, set(), CFG)
    assert win == ["P0", "P1", "P2", "P3"]
    assert ch == {"kept": 0, "added": 4, "removed": 0, "replaced_all": False}


def test_same_ranking_changes_nothing():
    win, ch = merge(["P0", "P1", "P2", "P3"], R, set(), CFG)
    assert win == ["P0", "P1", "P2", "P3"] and ch["added"] == ch["removed"] == 0


def test_dropped_place_slot_is_filled_in_place_by_the_best_new_one():
    win, ch = merge(["P0", "P1", "P2", "P3"], ["P0", "P2", "P3", "P9", "P8"], set(), CFG)
    assert win == ["P0", "P9", "P2", "P3"]
    assert ch == {"kept": 3, "added": 1, "removed": 1, "replaced_all": False}


def test_a_kept_place_far_down_the_new_ranking_is_removed():
    ranked = ["N0", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "P0", "P1", "P2", "P3"]
    win, ch = merge(["P0", "P1", "P2", "P3"], ranked, set(), CFG)
    assert ch["replaced_all"] and win == ["N0", "N1", "N2", "N3"]


def test_pinned_places_stay_in_place_even_when_ranked_low():
    ranked = ["N0", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "P1"]
    win, _ = merge(["P0", "P1", "P2", "P3"], ranked, {"P1"}, CFG)
    assert win[1] == "P1" and "P0" not in win


def test_extend_adds_the_next_page_without_duplicates():
    assert extend(["P0", "P2"], R, CFG) == ["P0", "P2", "P1", "P3", "P4", "P5"]
    assert extend(R, R, CFG) == R


def test_short_ranking_never_overflows():
    win, _ = merge([], ["P0", "P1"], set(), CFG)
    assert win == ["P0", "P1"]
    win, ch = merge(["P0", "P1", "P2"], ["P0"], set(), CFG)
    assert win == ["P0"] and ch["removed"] == 2
