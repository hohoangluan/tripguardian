"""Model roles (docs/CORPUS.md, Vai trò model): which .env keys point each role at its model.

Which model fills a role is config (docs/LLM_PROVIDER.md); code asks for a role, never for a model.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ..crawl.common.files import ROOT


@dataclass(frozen=True)
class Role:
    name: str
    purpose: str
    key_env: str
    base_url_env: str
    model_env: str
    guided: bool = True  # the server honours response_format json_schema; False: the schema goes in the prompt

    def client(self) -> tuple[AsyncOpenAI, str]:
        load_dotenv(ROOT / ".env")
        return AsyncOpenAI(api_key=os.environ[self.key_env], base_url=os.environ[self.base_url_env]), os.environ[self.model_env]


EXTRACTOR = Role(
    name="extractor",
    purpose="high-volume, cheap calls: one small judgement or extraction per item",
    key_env="LLM_API_KEY", base_url_env="EXTRACTOR_BASE_URL", model_env="EXTRACTOR_MODEL",
)

JUDGE = Role(
    name="judge",
    purpose="low-volume checks that gate what gets published",
    key_env="JUDGE_API_KEY", base_url_env="JUDGE_BASE_URL", model_env="JUDGE_MODEL", guided=False,
)

JUDGE_FIRST = Role(
    name="judge_first",
    purpose="optional cheaper first reader for the audit: its 'correct' stands, anything else goes to the Judge",
    key_env="JUDGE_API_KEY", base_url_env="JUDGE_BASE_URL", model_env="JUDGE_FIRST_MODEL", guided=False,
)

JUDGE_STRONG = Role(
    name="judge_strong",
    purpose="the Judge's hardest calls: values that widen choices (suitable for elderly, kids, wheelchair)",
    key_env="JUDGE_API_KEY", base_url_env="JUDGE_BASE_URL", model_env="JUDGE_STRONG_MODEL", guided=False,
)

AGENT = Role(
    name="agent",
    purpose="live conversation turns: one streamed structured call per user message (src/trip)",
    key_env="AGENT_API_KEY", base_url_env="AGENT_BASE_URL", model_env="AGENT_MODEL",
)
