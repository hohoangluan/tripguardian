from trip.text import contains, fold, squash


def test_fold_keeps_length_and_strips_marks():
    s = "Mẹ đau gối, Đà Lạt"
    assert fold(s) == "me dau goi, da lat"
    assert len(fold(s)) == len(s)


def test_contains_ignores_marks_and_punctuation():
    assert contains("Tháng 12 đi Đà Lạt, mẹ đau gối!", "Mẹ  đau gối")
    assert contains("đau gối", "đau")
    assert not contains("đau gối", "au g")
    assert squash("  A--b ") == "a b"
