"""Validated local capability declarations; loading never executes workflow data."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


TOOL_ACCESS = {
    'trip': {'trip.clues': 'read', 'trip.compile': 'read', 'trip.turn': 'write'},
    'decision': {'decision.candidates': 'read', 'decision.compare': 'read',
                 'decision.turn': 'write', 'decision.act': 'write', 'decision.confirm': 'write'},
    'planning': {'planning.variants': 'read', 'planning.diagnostics': 'read',
                 'planning.propose': 'read'},
}


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str
    access: Literal['read', 'write']


class SkillSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: Literal['trip', 'decision', 'planning']
    workflow: tuple[str, ...] = Field(min_length=1)
    tools: tuple[ToolSpec, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_capabilities(self):
        allowed = TOOL_ACCESS[self.name]
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError('duplicate tool declaration')
        if any(allowed.get(tool.name) != tool.access for tool in self.tools):
            raise ValueError('tool or access is not allowed for this skill')
        if any(not step.strip() for step in self.workflow):
            raise ValueError('workflow steps must be nonempty')
        return self


def load_skill(path: Path) -> SkillSpec:
    """Read a local YAML declaration with a fixed module/tool allowlist."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise ValueError('invalid skill YAML') from exc
    return SkillSpec.model_validate(data)


def permit_tool(skill: SkillSpec, name: str) -> ToolSpec:
    """Return a declared tool or reject invocation outside this skill's capability."""
    validated = SkillSpec.model_validate(skill.model_dump())
    for tool in validated.tools:
        if tool.name == name:
            return tool
    raise ValueError(f"tool {name!r} is not declared for skill {skill.name!r}")
