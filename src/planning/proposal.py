"""Internal arrangement proposals: typed capabilities and the LLM I/O boundary."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents import run_structured
from corpus.llm import AGENT, Task


class MovePlace(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    type: Literal['move_place']
    place: str
    day: int


class Reorder(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    type: Literal['reorder']
    day: int
    order: list[str]


class PlanningProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    fingerprint: str
    variant_id: str
    acts: list[Annotated[MovePlace | Reorder, Field(discriminator='type')]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def proposal_stream(fields):
    async def stream():
        task = Task(name='planning_proposal', role=AGENT,
                    prompt=('Choose only an existing variant ID and optionally move_place/reorder acts. '
                            'Preserve membership, hard constraints and all anchor/locked scheduled slots. '
                            'Reasons must reference diagnostics IDs. Return only schema JSON, no say. '
                            'Copy fingerprint exactly. Snapshot: {snapshot}'),
                    schema=PlanningProposal.model_json_schema(), max_tokens=2048)
        client, model = AGENT.client()
        try:
            async for delta in task.stream(client, model, snapshot=json.dumps(fields, ensure_ascii=False)):
                yield delta
        finally:
            await client.close()
    return stream()


async def run_proposal(fields, cfg, open_stream=proposal_stream):
    return await run_structured(fields, lambda _: None, cfg, PlanningProposal, open_stream)
