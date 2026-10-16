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
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    assert not j.unsupported("x", "y") and j.bad_reply("x") is None


def test_judge_ranks_features_by_probability(cloudflare, monkeypatch):
    from trip.domain.state import ontology
    feats = list(ontology().features.values())[:3]
    ids = [f.id for f in feats]
    fake(monkeypatch, [{"name": clef.FEATURE, "choice": ids[1], "probabilities": {ids[0]: 0.1, ids[1]: 0.6, ids[2]: 0.3, "none": 0.0}}])
    assert clef.Judge(Settings()).features("view núi", feats) == [ids[1]]  # 0.3 and 0.1 are below clef_feature_min
