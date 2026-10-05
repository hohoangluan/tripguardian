from corpus.observe import official as off


def fact(kind, quote, amount=0, audience="none", open_="", close="", days=()):
    return {"kind": kind, "quote": quote, "amount_vnd": amount, "audience": audience, "open": open_, "close": close,
            "days": list(days)}


PAGE = "GIÁ VÉ THAM QUAN\n150 000\nVND/ 1 người\nTrẻ 90–120cm\n75.000đ / em\nDưới 90cm\nMiễn phí\nGiờ mở cửa\n08:00 – 18:00"


def test_gate_keeps_only_what_the_page_states():
    assert off.gate(fact("ticket", "GIÁ VÉ THAM QUAN 150 000 VND/ 1 người", 150000, "adult"), PAGE, None) is None
    assert off.gate(fact("ticket", "Trẻ 90–120cm 75.000đ / em", 75000, "child"), PAGE, None) is None
    assert off.gate(fact("ticket", "GIÁ VÉ THAM QUAN 150 000", 120000, "adult"), PAGE, None) == "amount_not_in_quote"
    assert off.gate(fact("ticket", "vé 99k", 99000, "adult"), PAGE, None) == "quote_not_in_page"
    assert off.gate(fact("ticket", "Trẻ 90–120cm 75.000đ / em", 75000, "other"), PAGE, None) == "not_entry_ticket"
    week = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    assert off.gate(fact("hours", "Giờ mở cửa 08:00 – 18:00", open_="08:00", close="18:00", days=week), PAGE, None) is None
    assert off.gate(fact("hours", "Giờ mở cửa 08:00 – 18:00", open_="07:00", close="18:00", days=week),
                    PAGE, None) == "hours_not_in_quote"


def test_shared_site_needs_the_place_name_near_the_quote():
    page = "Khu du lịch Thác Datanla\nVé 50.000đ/người\n" + "x" * 900 + "\nKDL Langbiang\nVé 30.000đ/người"
    words = off.name_words("Khu du lịch Thác Datanla")
    assert off.gate(fact("ticket", "Vé 50.000đ/người", 50000, "adult"), page, words) is None
    assert off.gate(fact("ticket", "Vé 30.000đ/người", 30000, "adult"), page, words) == "shared_site_other_place"


def test_build_drops_child_only_free_entry_and_conflicting_hours():
    doc = {"fid": "F", "website": "https://x.vn", "fetched_at": "2026-10-05T00:00:00+00:00"}
    kept = [("u", fact("ticket", "150 000 VND", 150000, "adult")), ("u", fact("free", "Dưới 90cm Miễn phí")),
            ("u", fact("hours", "08:00 – 18:00", open_="08:00", close="18:00", days=["mon"])),
            ("u", fact("hours", "09:00 16:00", open_="09:00", close="16:00", days=["mon"]))]
    res = off.build(doc, {"name": "X"}, kept, 7)
    assert [(o["feature"], o["value"], o["author"]) for o in res["observations"]] == [("entry_fee", "paid", "official:F")]
    assert res["place_facts"]["hours"] is None and res["place_facts"]["tickets_vnd"] == {"adult": [150000], "child": []}
    lunch = off.hours_of([fact("hours", "", open_="07:00", close="11:00", days=["sat"]),
                          fact("hours", "", open_="13:00", close="17:00", days=["sat"])])
    assert lunch == {"sat": [["07:00", "11:00"], ["13:00", "17:00"]]}


def test_chunks_skip_repeated_site_lines_and_pages_without_prices_or_hours():
    pages = [{"url": "a", "text": "MENU\nLiên hệ\nVé 50k"}, {"url": "b", "text": "MENU\nLiên hệ\nGiới thiệu chung"}]
    assert off.chunks(pages) == [("a", "MENU\nLiên hệ\nVé 50k")]


def test_official_site_skips_social_and_resellers():
    from corpus.crawl.official.pages import official_site, pick_links
    assert official_site("https://zoodoodalat.com/") and not official_site("https://www.facebook.com/x")
    assert not official_site("https://ticketssee.com/thunglungtinhyeu/") and not official_site(None)
    links = [["/gia-ve", "Giá vé"], ["https://other.com/gia-ve", "Giá vé"], ["/blog/post-1", "Tin"],
             ["/lien-he#map", "Liên hệ"], ["/menu.pdf", "Bảng giá"]]
    assert pick_links("https://x.vn/", links, 4) == ["https://x.vn/gia-ve", "https://x.vn/lien-he"]
