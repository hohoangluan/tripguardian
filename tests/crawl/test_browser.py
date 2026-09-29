import asyncio

from corpus.crawl import browser


def test_login_required_tells_how_to_fix():
    assert "python -m corpus login tiktok" in str(browser.LoginRequired("tiktok"))


def test_pause_stays_in_range(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(browser.asyncio, "sleep", fake_sleep)
    for _ in range(50):
        asyncio.run(browser.pause())
    assert all(2.0 <= s <= 5.0 for s in slept)


def test_is_captcha_detects_slider_text():
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await b.new_page()
            await page.set_content("<div>Kéo thanh trượt để ghép hình</div>")
            hit = await browser.is_captcha(page)
            await page.set_content("<div>video list</div>")
            miss = await browser.is_captcha(page)
            await b.close()
            return hit, miss

    assert asyncio.run(run()) == (True, False)


def _captcha_page(fn):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await b.new_page()
            await page.set_content("<div>Kéo thanh trượt để ghép hình</div>")
            try:
                return await fn(page)
            finally:
                await b.close()
    return asyncio.run(run())


def test_captcha_in_headless_stops():
    async def fn(page):
        try:
            await browser.wait_for_person(page, "tiktok", wait_s=5)
        except browser.LoginRequired:
            return "stopped"
    assert _captcha_page(fn) == "stopped"


def test_captcha_in_headed_waits_for_person(monkeypatch):
    async def headed(page):
        return False

    monkeypatch.setattr(browser, "_is_headless", headed)

    async def fn(page):
        async def person_solves():
            await asyncio.sleep(1)
            await page.set_content("<div>video list</div>")
        asyncio.create_task(person_solves())
        await browser.wait_for_person(page, "tiktok", wait_s=10)
        return "continued"
    assert _captcha_page(fn) == "continued"
