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
    parallel_env: str | None = None  # .env key: concurrent calls the endpoint takes (docs/LLM_PROVIDER.md)
    default_parallel: int = 36  # without parallel_env: the UIT key allows 40 (HTTP 429 above)

    def _on_uit(self) -> bool:
        """EXTRACTOR_ON_UIT=1 (process environment): this process runs the Extractor on the UIT Gemma, so a second
        process can work beside one on the LAN host (docs/LLM_PROVIDER.md §UIT API)."""
        return self.name == "extractor" and os.environ.get("EXTRACTOR_ON_UIT", "").strip() not in ("", "0")

    def also_uit(self) -> bool:
        """EXTRACTOR_ALSO_UIT=1 (process environment): an Extractor task that spreads calls over endpoints
        (`gmaps observe`) uses the UIT Gemma beside the LAN host (docs/LLM_PROVIDER.md §UIT API)."""
        return (self.name == "extractor" and not self._on_uit()
                and os.environ.get("EXTRACTOR_ALSO_UIT", "").strip() not in ("", "0"))

    @staticmethod
    def uit_client() -> tuple[AsyncOpenAI, str]:
        load_dotenv(ROOT / ".env")
        return AsyncOpenAI(api_key=os.environ["UIT_API_KEY"], base_url=os.environ["UIT_API_BASE_URL"]), os.environ["UIT_API_MODEL"]

    def client(self) -> tuple[AsyncOpenAI, str]:
        if self._on_uit():
            return self.uit_client()
        return self.own_client()

    def own_client(self) -> tuple[AsyncOpenAI, str]:
        """The role's own endpoint from .env, even in an EXTRACTOR_ON_UIT process (a UIT run borrowing the LAN host)."""
        load_dotenv(ROOT / ".env")
        return AsyncOpenAI(api_key=os.environ[self.key_env], base_url=os.environ[self.base_url_env]), os.environ[self.model_env]

    def parallel(self) -> int:
        """Concurrent calls a task of this role runs when it sets none itself."""
        if self._on_uit():
            return 38  # the UIT key takes 40; two stay free for the Agent
        return self.own_parallel()

    def own_parallel(self) -> int:
        load_dotenv(ROOT / ".env")
        return int(os.environ.get(self.parallel_env or "") or self.default_parallel)


EXTRACTOR = Role(
    name="extractor",
    purpose="high-volume, cheap calls: one small judgement or extraction per item",
    key_env="LLM_API_KEY", base_url_env="EXTRACTOR_BASE_URL", model_env="EXTRACTOR_MODEL",
    parallel_env="EXTRACTOR_PARALLEL",
)

# The Judge roles run on the UIT Gemma (docs/LLM_PROVIDER.md §UIT API): the key takes 40
# concurrent calls, 38 of them here. The live Agent has its own endpoint and credentials.
UIT = dict(key_env="UIT_API_KEY", base_url_env="UIT_API_BASE_URL", model_env="UIT_API_MODEL", default_parallel=38)

JUDGE = Role(
    name="judge",
    purpose="low-volume checks that gate what gets published",
    **UIT,
)

JUDGE_FIRST = Role(
    name="judge_first",
    purpose="optional cheaper first reader for the audit: its 'correct' stands, anything else goes to the Judge",
    **{**UIT, "model_env": "JUDGE_FIRST_MODEL"},  # unset = no first reader (judge.audit.first_reader)
)

JUDGE_STRONG = Role(
    name="judge_strong",
    purpose="the Judge's hardest calls: values that widen choices (suitable for elderly, kids, wheelchair)",
    **UIT,
)

AGENT = Role(
    name="agent",
    purpose="live conversation turns: one streamed structured call per user message (src/trip)",
    key_env="AGENT_API_KEY", base_url_env="AGENT_BASE_URL", model_env="AGENT_MODEL",
)

USER_SIM = Role(
    name="user_sim",
    purpose="benchmark only: plays a traveller from a hidden trip (python -m bench, --live / --briefs)",
    key_env="USER_SIM_API_KEY", base_url_env="USER_SIM_BASE_URL", model_env="USER_SIM_MODEL",
)
