def test_in_order_catches_a_mixed_in_default_list():
    from corpus.crawl.gmaps.extremes import SORTS, in_order
    r = lambda *xs: [{"rating": f"{x} sao"} for x in xs]  # noqa: E731
    assert in_order(r(1, 1, 2, 5), SORTS["lowest"])
    assert not in_order(r(5, 5, 4, 1, 1), SORTS["lowest"])  # ~10 "relevant" reviews read before the sort applied
    assert in_order(r(5, 4, 1) + [{"rating": None}], SORTS["highest"])
    assert not in_order(r(5, 5, 1, 5), SORTS["highest"])
