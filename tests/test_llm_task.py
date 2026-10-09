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


def test_planning_turn_renders_with_every_field():
    from corpus.llm import PLANNING_TURN
    text = PLANNING_TURN.render(features="noise: quiet|loud", days="Ngày 1: ...", variants="V1 | ...",
                                lodging="L1 | ...", text="bỏ chỗ này đi")
    assert "bỏ chỗ này đi" in text and "V1" in text


class _Stream:
    """An openai-style async stream of text pieces; counts how many were read and whether it was closed."""

    def __init__(self, pieces):
        self.pieces, self.read, self.closed = pieces, 0, False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for p in self.pieces:
            self.read += 1
            yield type("Ch", (), {"choices": [type("D", (), {"delta": type("T", (), {"content": p})()})()]})()

    async def close(self):
        self.closed = True


class StreamClient:
    def __init__(self, streams):
        self.streams, self.calls = list(streams), 0
        self.chat = type("C", (), {"completions": self})()

    async def create(self, **kw):
        assert kw["stream"] is True
        self.calls += 1
        return self.streams.pop(0)


def test_looping_answer_is_cut_and_asked_once_more():
    answer = json.dumps({"verdict": "supports", "reason": ""})
    loop = _Stream(['{"verdict": "supports", "reason": "", "x": '] + ["\n  "] * 1000)
    client = StreamClient([loop, _Stream([answer])])
    out = asyncio.run(tasks.REVIEW_VERIFY.ask(client, "m", name="A", category="c", claim="x", passage="y"))
    assert out["verdict"] == "supports" and client.calls == 2
    assert loop.closed and loop.read < 200  # cut at ~300 chars of whitespace, not read to the end


def test_answer_that_loops_again_fails_after_two_calls():
    client = StreamClient([_Stream(["{"] + [" " * 100] * 10) for _ in range(4)])
    try:
        asyncio.run(tasks.REVIEW_VERIFY.ask(client, "m", name="A", category="c", claim="x", passage="y"))
    except tasks.Runaway:
        pass
    else:
        raise AssertionError("expected Runaway")
    assert client.calls == tasks.RUNAWAYS


def test_pretty_printed_answer_is_not_a_loop():
    pretty = json.dumps({"verdict": "supports", "reason": "ok"}, indent=8)
    client = StreamClient([_Stream(list(pretty))])
    out = asyncio.run(tasks.REVIEW_VERIFY.ask(client, "m", name="A", category="c", claim="x", passage="y"))
    assert out["verdict"] == "supports" and client.calls == 1
