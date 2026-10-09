import pytest
from gmaps_helpers import parse_fixture

from corpus.crawl.common.browser import LoginRequired
from corpus.crawl.gmaps import page as gpage


def test_signed_out_page_is_detected():
    # Google can end the session while the SID cookie stays: Maps then shows fewer results and no reviews.
    with pytest.raises(LoginRequired):
        parse_fixture("logged_out.html", gpage.check_signed_in)


@pytest.mark.parametrize("fixture", ["place.html", "feed.html", "reviews.html"])
def test_signed_in_pages_pass(fixture):
    parse_fixture(fixture, gpage.check_signed_in)


def test_text_only_blocks_pictures_on_own_tabs_not_the_shared_context():
    import asyncio
    from corpus.crawl.gmaps import page as page_mod

    routed = []

    class Tab:
        async def route(self, pattern, handler):
            routed.append(("tab", pattern))

    class Ctx:
        async def route(self, *a):
            routed.append(("context",))

        async def new_page(self):
            return Tab()

    async def run():
        ctx = Ctx()
        await page_mod.text_only(ctx)
        assert routed == []  # nothing on the context: other processes' tabs keep their pictures
        await ctx.new_page()

    asyncio.run(run())
    assert routed == [("tab", page_mod._PICTURES)]
