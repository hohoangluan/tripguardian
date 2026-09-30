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
