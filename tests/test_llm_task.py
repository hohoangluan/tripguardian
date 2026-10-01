import asyncio
import json

import httpx
import openai

from corpus.llm import tasks


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
