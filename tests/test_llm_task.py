import asyncio
import json

import httpx
import openai

from corpus.llm import tasks
from corpus.llm.roles import Endpoint


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class FakeClient:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0
        self.chat = type("C", (), {"completions": self})()

    async def create(self, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return type("R", (), {"choices": [_Msg(json.dumps({"verdict": "supports", "reason": ""}))]})()


def test_server_error_is_retried(monkeypatch):
    monkeypatch.setattr(tasks, "RETRY_S", 0)
    req = httpx.Request("POST", "http://llm")
    err = openai.InternalServerError("Internal error encountered.", response=httpx.Response(500, request=req), body=None)
    client = FakeClient([err])
    out = asyncio.run(tasks.REVIEW_VERIFY.ask(client, "m", name="A", category="c", claim="x", passage="y"))
    assert out["verdict"] == "supports" and client.calls == 2


def test_endpoint_reads_env_and_is_off_without_it(monkeypatch):
    monkeypatch.setattr("corpus.llm.roles.load_dotenv", lambda *a, **k: None)
    e = Endpoint("T_KEY", "T_URL", "T_MODEL", "T_PARALLEL", default_url="http://default/v1")
    monkeypatch.delenv("T_KEY", raising=False)
    assert e.client() is None
    monkeypatch.setenv("T_KEY", "k")
    monkeypatch.setenv("T_MODEL", "gemma")
    monkeypatch.setenv("T_PARALLEL", "24")
    client, model, parallel = e.client()
    assert model == "gemma" and parallel == 24 and str(client.base_url).startswith("http://default/v1")
