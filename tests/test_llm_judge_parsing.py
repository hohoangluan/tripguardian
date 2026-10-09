import asyncio
import dataclasses
import json

import httpx
import openai
import pytest

from corpus.llm import tasks


def test_parse_answer_takes_the_last_object_around_prose():
    assert tasks.parse_answer('Sure.\n```json\n{"a": 1}\n```') == {"a": 1}
    assert tasks.parse_answer('{"x": 0} then {"items": []}') == {"items": []}
    fenced = '```json\n{"items": [{"ref": "i1"}, {"ref": "i2"}]}\n```'
    assert tasks.parse_answer(fenced) == {"items": [{"ref": "i1"}, {"ref": "i2"}]}  # not its last item
    assert tasks.parse_answer('thinking {not json} ```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    with pytest.raises(json.JSONDecodeError):
        tasks.parse_answer("no json here")


def test_validate_checks_required_and_enum():
    schema = tasks.AUDIT_SCHEMA
    tasks.validate({"items": [{"ref": "i1", "verdict": "correct", "reason": "ok"}]}, schema)
    with pytest.raises(tasks.SchemaError):
        tasks.validate({"items": [{"ref": "i1", "verdict": "maybe", "reason": ""}]}, schema)
    with pytest.raises(tasks.SchemaError):
        tasks.validate({"ref": "i1", "verdict": "correct", "reason": ""}, schema)  # a truncated answer's last item


class _Stream:
    def __init__(self, text):
        self.text = text

    def __aiter__(self):
        async def gen():
            yield type("C", (), {"choices": [type("D", (), {"delta": type("X", (), {"content": self.text})()})()]})()
        return gen()


class PoolClient:
    """First model answers a usage limit, the second answers."""

    def __init__(self):
        self.models = []
        self.chat = type("C", (), {"completions": self})()

    async def create(self, **kw):
        self.models.append(kw["model"])
        if kw["model"] == "a":
            req = httpx.Request("POST", "http://x")
            raise openai.InternalServerError("[codex/a] [429]: The usage limit has been reached (reset after 3m)",
                                             response=httpx.Response(503, request=req), body=None)
        return _Stream(json.dumps({"relation": "different", "reason": "r"}))


def test_pool_rests_a_spent_model_and_asks_the_next(monkeypatch):
    monkeypatch.setattr(tasks, "_REST", {})
    client = PoolClient()
    proxy = dataclasses.replace(tasks.SAME_PLACE, role=dataclasses.replace(tasks.SAME_PLACE.role, guided=False))  # a streaming proxy
    out = asyncio.run(proxy.ask(client, "a,b", city="c", a="A", b="B", meters=1))
    assert out["relation"] == "different" and out["_model"] == "b" and client.models == ["a", "b"]
    assert tasks.pick("a,b") == "b"  # a rests ~3 minutes
    tasks._REST["b"] = tasks._REST["a"]
    with pytest.raises(tasks.OutOfQuota):
        tasks.pick("a,b")


def test_unsupported_model_on_one_account_rests_briefly():
    req = httpx.Request("POST", "http://x")
    e = openai.BadRequestError("[400]: The 'gpt-5.6-sol' model is not supported when using Codex with a ChatGPT "
                               "account.", response=httpx.Response(400, request=req), body=None)
    assert tasks._quota_rest(e) == tasks.UNSUPPORTED_REST_S
    plain = openai.BadRequestError("bad field", response=httpx.Response(400, request=req), body=None)
    assert tasks._quota_rest(plain) is None


def test_extractor_on_uit_switch_moves_only_the_extractor(monkeypatch):
    from corpus.llm import roles
    monkeypatch.setenv("UIT_API_KEY", "k")
    monkeypatch.setenv("UIT_API_BASE_URL", "https://uit/v1")
    monkeypatch.setenv("UIT_API_MODEL", "uit-gemma")
    monkeypatch.setenv("EXTRACTOR_ON_UIT", "1")
    client, model = roles.EXTRACTOR.client()
    assert str(client.base_url).startswith("https://uit") and model == "uit-gemma" and roles.EXTRACTOR.parallel() == 38
    monkeypatch.delenv("EXTRACTOR_ON_UIT")
    assert not str(roles.EXTRACTOR.client()[0].base_url).startswith("https://uit")
