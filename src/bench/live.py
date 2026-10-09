"""The live tier: a USER_SIM model writes briefs and answers cards in prose. Refuses to run unless configured."""

import asyncio
import json
import os

from corpus.llm import USER_SIM, USER_SIM_BRIEF, USER_SIM_REPLY

from .hidden import HiddenTrip

ENV = (USER_SIM.key_env, USER_SIM.base_url_env, USER_SIM.model_env)


class NotConfigured(SystemExit):
    pass


def require() -> None:
    missing = [k for k in ENV if not os.environ.get(k)]
    if missing:
        raise NotConfigured(f"the live tier needs {', '.join(missing)} (docs/LLM_PROVIDER.md, role USER_SIM)")


def _truth(t: HiddenTrip) -> str:
    return json.dumps(t.model_dump(mode="json", exclude={"id", "brief"}), ensure_ascii=False)


def brief(t: HiddenTrip) -> str:
    require()
    client, model = USER_SIM.own_client()
    return asyncio.run(USER_SIM_BRIEF.ask(client, model, trip=_truth(t)))["brief"].strip()


def reply(t: HiddenTrip, card: dict) -> str:
    require()
    client, model = USER_SIM.own_client()
    options = ", ".join(c["label"] for c in card["chips"]) or "-"
    return asyncio.run(USER_SIM_REPLY.ask(client, model, trip=_truth(t), question=card["text"],
                                          options=options))["reply"].strip()
