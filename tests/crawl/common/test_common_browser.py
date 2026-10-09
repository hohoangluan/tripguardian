import asyncio
import json
import re

from corpus.crawl.common import browser


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


def test_attach_opens_tabs_in_the_signed_in_context():
    """A login window keeps its session in a new_context(), which CDP clients see under the default context: attached
    tabs and cookies must come from the signed-in context. Two clients (two crawl processes on one login window) open
    tabs at once: each gets its own tabs, none shared, none left open after closing."""
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch(channel=browser.CHANNEL, args=["--remote-debugging-port=9599"])
            login = await b.new_context()
            await login.add_cookies([{"name": "SID", "value": "x", "url": "https://www.google.com"}])
            await login.new_page()
            try:
                async with browser._attach("http://127.0.0.1:9599") as one, \
                        browser._attach("http://127.0.0.1:9599") as two:
                    names = [c["name"] for c in await one.cookies("https://www.google.com")]
                    pages = await asyncio.gather(*[ctx.new_page() for ctx in (one, two) for _ in range(4)])
                    ids = []
                    for page in pages:
                        s = await page.context.new_cdp_session(page)
                        ids.append((await s.send("Target.getTargetInfo"))["targetInfo"]["targetId"])
                    for page in pages:
                        await page.close()
                    left = len([t for t in (await (await b.new_browser_cdp_session()).send("Target.getTargets"))
                                ["targetInfos"] if t["type"] == "page"])
                return "SID" in names, len(set(ids)), left
            finally:
                await b.close()

    assert asyncio.run(run()) == (True, 8, 1)


def test_a_captcha_solved_in_one_tab_lets_the_other_waiting_tab_reload(monkeypatch):
    async def headed(page):
        return False

    monkeypatch.setattr(browser, "_is_headless", headed)

    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch(channel=browser.CHANNEL)
            ctx = await b.new_context()
            one, two = await ctx.new_page(), await ctx.new_page()
            for page in (one, two):
                await page.set_content("<div>Kéo thanh trượt để ghép hình</div>")

            async def person_solves_one():
                await asyncio.sleep(1)
                await one.set_content("<div>video list</div>")
            asyncio.create_task(person_solves_one())
            try:  # no wait_s: both wait as long as it takes; two passes on its reload (blank page, no slider)
                await asyncio.wait_for(asyncio.gather(browser.wait_for_person(one, "tiktok"),
                                                      browser.wait_for_person(two, "tiktok")), 20)
                return "both continued"
            finally:
                await b.close()

    assert asyncio.run(run()) == "both continued"


def test_attach_closes_tabs_left_open_and_tabs_of_dead_processes(monkeypatch, tmp_path):
    """Tabs in a login window outlive the process that opened them: on exit a process closes what it left open, and
    the next process to attach closes the tabs a killed process (no exit) left behind."""
    import subprocess
    import sys

    monkeypatch.setattr(browser, "TABS_DIR", tmp_path)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()

    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch(channel=browser.CHANNEL, args=["--remote-debugging-port=9598"])
            login = await b.new_context()
            await login.new_page()
            cdp = await b.new_browser_cdp_session()
            cid = (await cdp.send("Target.getBrowserContexts"))["browserContextIds"][0]

            async def pages():
                return len([t for t in (await cdp.send("Target.getTargets"))["targetInfos"] if t["type"] == "page"])

            try:
                url = "http://127.0.0.1:9598"
                orphans = [(await cdp.send("Target.createTarget", {"url": "about:blank", "browserContextId": cid}))
                           ["targetId"] for _ in range(2)]
                (tmp_path / f"{re.sub(r'\W', '_', url)}__{dead.pid}.json").write_text(json.dumps(orphans))
                before = await pages()
                async with browser._attach(url) as ctx:
                    reaped = await pages()
                    await ctx.new_page()  # never closed by the caller
                    opened = await pages()
                return before, reaped, opened, await pages(), sorted(f.name for f in tmp_path.iterdir())
            finally:
                await b.close()

    assert asyncio.run(run()) == (3, 1, 2, 1, [])
