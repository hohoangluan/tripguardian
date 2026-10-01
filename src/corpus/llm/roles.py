"""Model roles (docs/specs/CORPUS_SPEC.md, Vai trò model): which .env keys point each role at its model.

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

    def client(self) -> tuple[AsyncOpenAI, str]:
        load_dotenv(ROOT / ".env")
        return AsyncOpenAI(api_key=os.environ[self.key_env], base_url=os.environ[self.base_url_env]), os.environ[self.model_env]


@dataclass(frozen=True)
class Endpoint:
    """Another provider serving a role with the same model, used next to the role's own (docs/LLM_PROVIDER.md).
    Off when its key or model is not set."""
    key_env: str
    base_url_env: str
    model_env: str
    parallel_env: str
    default_url: str
    default_parallel: int = 16

    def client(self) -> tuple[AsyncOpenAI, str, int] | None:
        load_dotenv(ROOT / ".env")
        if not os.environ.get(self.key_env) or not os.environ.get(self.model_env):
            return None
        return (AsyncOpenAI(api_key=os.environ[self.key_env],
                            base_url=os.environ.get(self.base_url_env) or self.default_url),
                os.environ[self.model_env], int(os.environ.get(self.parallel_env) or self.default_parallel))


EXTRACTOR = Role(
    name="extractor",
    purpose="high-volume, cheap calls: one small judgement or extraction per item",
    key_env="LLM_API_KEY", base_url_env="EXTRACTOR_BASE_URL", model_env="EXTRACTOR_MODEL",
)

# Gemma on the Gemini API (Google AI Studio): one key, its own rate limits
EXTRACTOR_EXTRA = (Endpoint("GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_MODEL", "GEMINI_PARALLEL",
                            default_url="https://generativelanguage.googleapis.com/v1beta/openai/"),)

JUDGE = Role(
    name="judge",
    purpose="low-volume checks that gate what gets published",
    key_env="JUDGE_API_KEY", base_url_env="JUDGE_BASE_URL", model_env="JUDGE_MODEL",
)
