import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corpus.crawl.tiktok import page as tpage

FIX = Path(__file__).parents[2] / "fixtures" / "tiktok"


@pytest.fixture(autouse=True)
def fast_rounds(monkeypatch):
    monkeypatch.setattr(tpage, "ROUND_S", 0.01)
    monkeypatch.setattr(tpage, "STALE_ROUNDS", 5)
    monkeypatch.setattr(tpage, "STATE_WAIT_S", 0.05)
    monkeypatch.setattr(tpage, "STATE_POLL_S", 0.01)


@asynccontextmanager
async def fake_profile(source, headed=False):
    yield object()


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path / "tiktok"


class _Resp:
    def __init__(self, payload):
        # payload alone = a top-level comment page; (url, payload) for other APIs
        url, self.payload = payload if isinstance(payload, tuple) else ("https://www.tiktok.com/api/comment/list/?c=1", payload)
        self.url = url

    async def json(self):
        return self.payload

    async def text(self):
        return "" if self.payload == "" else json.dumps(self.payload)  # "" = a throttled session's empty body


class FakePage:
    """Serves one API page per scroll until the pages run out; evaluate() returns the video item."""

    def __init__(self, pages, item=None):
        self.pages, self.handlers, self.item = list(pages), {}, item
        self.mouse = self
        self.first = self.last = self

    def on(self, event, fn):
        self.handlers[event] = fn

    async def _next(self, *a, **k):
        if self.pages:
            payload = self.pages.pop(0)
            if isinstance(payload, tuple) and payload[0] == "late":  # still in flight: lands a moment later
                late = _Resp(payload[1])
                self.handlers.get("request", lambda r: None)(late)  # sent now
                asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(self.handlers["response"](late)))
            elif payload is not None:  # None = the API has not answered yet
                resp = _Resp(payload)
                self.handlers.get("request", lambda r: None)(resp)
                await self.handlers["response"](resp)

    async def route(self, pattern, handler):
        pass

    async def wait_for(self, **kw):
        pass

    goto = click = scroll_into_view_if_needed = wheel = _next

    async def evaluate(self, js):
        return self.item

    def locator(self, sel):
        return self

    def filter(self, **kw):
        return self

    async def count(self):
        return 1

    async def close(self):
        pass


class FakeCtx:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page


@pytest.fixture
def no_person(monkeypatch):
    monkeypatch.setattr(tpage, "wait_for_person", lambda page, source: asyncio.sleep(0))
    monkeypatch.setattr(tpage, "_expand", lambda page, sel: asyncio.sleep(0, 0))
