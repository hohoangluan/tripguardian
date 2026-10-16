import pytest


@pytest.mark.parametrize("text", ["3 ngày", "Ít đông, Xe máy, Đi với người yêu", "Đi đèo thế nào cho an toàn?",
                                  "bạn có thể làm được gì", "không hợp pháp chỗ nào?", "bạn là ai", "hello banj hien"])
def test_everything_that_is_not_a_known_attack_is_left_to_the_agent(text):
    from agents import ChatSafety

    assert ChatSafety()(text, "Bạn đi mấy ngày?") is None


def test_chat_admission_never_calls_a_model(monkeypatch):
    from agents import ChatSafety
    from corpus import llm

    monkeypatch.setattr(type(llm.JUDGE), "client", lambda self: pytest.fail("admission reached a model"))
    assert ChatSafety()("Mình muốn một chuyến đi có trải nghiệm thật đặc biệt", "") is None


def test_agent_policy_lets_the_agent_judge_scope_and_answer_questions_about_itself():
    from corpus.llm import CHAT_POLICY

    assert "treat it as in scope" in CHAT_POLICY
    assert "what you can do" in CHAT_POLICY and "why you declined" in CHAT_POLICY


@pytest.mark.parametrize("text", ["x" * 4001, "x\x00y", "x‮y", "http://127.0.0.1/admin", "http://169.254.169.254/",
                                  "file:///etc/passwd", "https://user:pass@example.com/", "https://example.com:22/",
                                  "http://100.64.0.1/", "javascript:alert(1)"])
def test_invalid_input_and_unsafe_urls_are_blocked(text):
    from agents import ChatSafety

    assert ChatSafety()(text, "") is not None
