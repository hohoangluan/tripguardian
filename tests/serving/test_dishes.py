from corpus.serving import dishes


def rec(rid, name, dishes_=(), order=()):
    return {"id": rid, "identity": {"name": name}, "menu": {"dishes": list(dishes_), "photos": []} if dishes_ else None,
            "details": {"order": [{"text": t, "n": n} for t, n in order]}}


def test_fold_ignores_case_accents_and_d_bar():
    assert dishes.fold("Bánh Bèo  Chén") == "banh beo chen"
    assert dishes.fold("Sữa đậu nành") == "sua dau nanh"


def test_phrase_is_whole_words():
    assert dishes.has_phrase("banh canh gio heo", "banh canh")
    assert not dishes.has_phrase("banh canhh", "banh canh")
    assert not dishes.has_phrase("canh chua", "banh canh")


def test_search_ranks_popular_menu_over_menu_over_review_order():
    rs = [rec("c", "C", order=[("bánh canh cua", 5)]),
          rec("b", "B", [{"name": "Bánh canh giò heo", "popular": False}]),
          rec("a", "A", [{"name": "Bánh canh cá lóc", "popular": True}]),
          rec("d", "D", [{"name": "Canh chua", "popular": True}])]
    assert [h["id"] for h in dishes.search(rs, "bánh canh")] == ["a", "b", "c"]


def test_alias_and_english_name():
    rs = [rec("a", "A", [{"name": "Sữa nành nóng"}]), rec("b", "B", [{"name": "Soy milk", "name_en": "Sữa đậu nành"}])]
    assert {h["id"] for h in dishes.search(rs, "sữa đậu nành")} == {"a", "b"}


def test_unknown_dish_is_empty_not_none_serving():
    assert dishes.search([rec("a", "A", [{"name": "Phở bò"}])], "bánh bèo") == []
    assert dishes.search([], "") == []


def test_menu_of_dedupes_and_needs_content():
    doc = {"has_menu_tab": True, "highlights": [{"name": "Bánh bèo", "popular": True}],
           "sections": [{"name": "Món chính", "items": [{"name": "Bánh Bèo"}, {"name": "Phở", "price": "50.000 ₫"}]}], "photos": []}
    m = dishes.menu_of(doc)
    assert [d["name"] for d in m["dishes"]] == ["Bánh bèo", "Phở"] and m["dishes"][1]["price"] == "50.000 ₫"
    assert dishes.menu_of({"has_menu_tab": False}) is None
    assert dishes.menu_of({"has_menu_tab": True, "highlights": [], "sections": [], "photos": []}) is None


def test_accented_query_does_not_fold_pho_into_pho_mai():
    rs = [rec("a", "A", [{"name": "Phô mai sợi"}]), rec("b", "B", [{"name": "Phở bò"}])]
    assert [h["id"] for h in dishes.search(rs, "phở")] == ["b"]
    assert {h["id"] for h in dishes.search(rs, "pho")} == {"a", "b"}  # typed without accents: both are possible
