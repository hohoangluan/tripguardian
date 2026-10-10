import json

import pytest

from trip.infrastructure import clef
from trip.infrastructure.settings import Settings


class Response:
    def __init__(self, answers):
        self.body = json.dumps({"result": {"answers": answers}}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a):
        return self.body


def answer(name, choice, p):
    return {"name": name, "choice": choice, "probabilities": {choice: p}}


@pytest.fixture
def cloudflare(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setattr(clef, "load_dotenv", lambda *_: None)
    for name in ("CLEF_TIMEOUT_S", "CLEF_MODEL", "CLEF_MODEL_ID"):  # the developer's .env may set these
        monkeypatch.delenv(name, raising=False)


def fake(monkeypatch, answers, seen=None):
    def urlopen(request, timeout):
        if seen is not None:
            seen.append((request, timeout))
        return Response(answers)
    monkeypatch.setattr(clef.urllib.request, "urlopen", urlopen)


def test_the_request_carries_the_message_the_open_card_and_its_questions(cloudflare, monkeypatch):
    seen = []
    fake(monkeypatch, [answer(clef.SCOPE, "A", 0.99)], seen)
    clef.route("tháng 12 lạnh không?", Settings(), "Bạn đi mấy ngày?")
    request, timeout = seen[0]
    body = json.loads(request.data)
    assert body["state"] == {"user_message": "tháng 12 lạnh không?", "open_question": "Bạn đi mấy ngày?"}
    assert set(body["questions"]) == {clef.SCOPE, clef.DATA} and timeout == 1.0
    assert request.full_url.endswith("/accounts/acc/ai/run/@cf/cloudflare/clef-flash")


def test_it_rejects_only_when_sure(cloudflare, monkeypatch):
    fake(monkeypatch, [answer(clef.SCOPE, "B", 0.95)])
    assert clef.route("x", Settings()).reject == "off_topic"
    fake(monkeypatch, [answer(clef.SCOPE, "C", 0.95)])
    assert clef.route("x", Settings()).reject == "abuse"
    fake(monkeypatch, [answer(clef.SCOPE, "B", 0.6)])
    assert clef.route("x", Settings()).reject is None


def test_it_flags_a_question_for_figures_only_when_sure(cloudflare, monkeypatch):
    fake(monkeypatch, [answer(clef.DATA, "A", 0.9)])
    assert clef.route("x", Settings()).asks_data is True
    fake(monkeypatch, [answer(clef.DATA, "A", 0.5)])
    assert clef.route("x", Settings()).asks_data is False
    fake(monkeypatch, [answer(clef.DATA, "B", 0.99)])
    assert clef.route("x", Settings()).asks_data is False


def test_a_missing_key_or_a_failing_call_decides_nothing(cloudflare, monkeypatch):
    def boom(request, timeout):
        raise TimeoutError
    monkeypatch.setattr(clef.urllib.request, "urlopen", boom)
    assert clef.route("x", Settings()) == clef.ClefRoute()
    fake(monkeypatch, [{"unexpected": 1}])
    assert clef.route("x", Settings()) == clef.ClefRoute()
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    assert clef.route("x", Settings()) == clef.ClefRoute()


def test_it_reads_the_real_reply_where_answers_are_a_dict_keyed_by_question(cloudflare, monkeypatch):
    fake(monkeypatch, {clef.SCOPE: {"choice": "B", "probabilities": {"A": 0.07, "B": 0.91, "C": 0.03}},
                       clef.DATA: {"choice": "A", "probabilities": {"A": 0.97, "B": 0.01, "C": 0.01}}})
    assert clef.route("giá bitcoin hôm nay", Settings()) == clef.ClefRoute("off_topic", True)


def test_data_question_lists_every_lookup_tool():
    from trip.agent import SPECS, STOPPING
    from trip.infrastructure.clef import LOOKUPS
    assert set(LOOKUPS) == set(SPECS) - set(STOPPING) - {"record_fact"}


def test_judge_vetoes_only_when_sure_and_never_when_clef_is_down(cloudflare, monkeypatch):
    j = clef.Judge(Settings())
    fake(monkeypatch, [answer(clef.SUPPORT, "B", 0.95)])
    assert j.unsupported("yên tĩnh", "khách muốn: x")
    fake(monkeypatch, [answer(clef.SUPPORT, "B", 0.7)])
    assert not j.unsupported("yên tĩnh", "khách muốn: x")
    fake(monkeypatch, [answer(clef.PROMISE, "A", 0.95), answer(clef.INVENT, "B", 0.9)])
    assert j.bad_reply("Mình sẽ gợi ý ngay") == "promises results"
    fake(monkeypatch, [answer(clef.PROMISE, "B", 0.99), answer(clef.INVENT, "A", 0.95)])
    assert j.bad_reply("Quán mở đến 22h") == "states a fact nobody gave"
    fake(monkeypatch, [answer(clef.REPEAT, "A", 0.95)])
    assert j.repeats("Bạn đi mấy ngày?", "{}")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    assert not j.unsupported("x", "y") and j.bad_reply("x") is None and not j.repeats("x", "{}")


def test_judge_says_whether_a_typed_answer_is_clear_for_its_field(cloudflare, monkeypatch):
    j = clef.Judge(Settings())
    fake(monkeypatch, [answer(clef.CLARITY, "A", 0.9)])
    assert j.clear_for_field("4 ngày", "số ngày") is True
    fake(monkeypatch, [answer(clef.CLARITY, "A", 0.5)])
    assert j.clear_for_field("4 ngày", "số ngày") is False
    fake(monkeypatch, [answer(clef.CLARITY, "B", 0.9)])
    assert j.clear_for_field("kiểu gì cũng được", "sở thích") is False
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    assert j.clear_for_field("4 ngày", "số ngày") is False  # down: the chat resolves it


def test_judge_ranks_features_by_probability(cloudflare, monkeypatch):
    from trip.domain.state import ontology
    feats = list(ontology().features.values())[:3]
    ids = [f.id for f in feats]
    fake(monkeypatch, [{"name": clef.FEATURE, "choice": ids[1], "probabilities": {ids[0]: 0.1, ids[1]: 0.6, ids[2]: 0.3, "none": 0.0}}])
    assert clef.Judge(Settings()).features("view núi", feats) == [ids[1]]  # 0.3 and 0.1 are below clef_feature_min
