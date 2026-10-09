import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

FIX = Path(__file__).parents[2] / "fixtures" / "gmaps"  # real captured pages: in the Drive data zip, not in git
AREA = [11.78, 108.30, 12.12, 108.66]


def parse_fixture(fixture: str, fn):
    if not (FIX / fixture).exists():
        pytest.skip(f"fixture {fixture} not present (Drive data zip)")

    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await (await b.new_context(java_script_enabled=False)).new_page()
            await page.set_content((FIX / fixture).read_text(encoding="utf-8"), wait_until="domcontentloaded")
            try:
                return await fn(page)
            finally:
                await b.close()
    return asyncio.run(run())


class _Context:
    async def new_page(self):  # wrapped by text_only; the fake runs never open a tab
        raise AssertionError("no tab in a fake profile")


@asynccontextmanager
async def fake_profile(source, headed=False):
    yield _Context()


class _Session:
    async def close(self):
        pass


@asynccontextmanager
async def fake_sessions(headed=False):
    async def new_session():
        return _Session()
    yield new_session


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path / "gmaps"
