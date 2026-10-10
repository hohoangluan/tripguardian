"""Read-only lookups behind the Trip agent's lookup tools."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ...domain.dates import relative_dates, weekday_vi
from ...domain.resolve import search
from ...domain.text import contains, fold
from ...infrastructure.catalog import Catalog


class RelativeDateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=80)


class PlaceLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=100)


class ToolExecutor:
    """Read-only lookups."""

    def __init__(self, catalog: Catalog, today: date):
        self.catalog, self.today = catalog, today

    def run(self, name: str, arguments: dict, text: str) -> dict:
        if name == "resolve_relative_date":
            inp = RelativeDateInput.model_validate(arguments)
            if not contains(text, inp.expression):
                raise ValueError("expression must appear in the user message")
            matches = relative_dates(fold(inp.expression), inp.expression.lower(), self.today)
            if not matches or matches[0].field != "start_date":
                return {"status": "unknown"}
            resolved = matches[0].value
            return {"status": "ok", "start_date": resolved.isoformat(), "weekday": weekday_vi(resolved)}
        if name == "search_places":
            inp = PlaceLookupInput.model_validate(arguments)
            if not contains(text, inp.query):
                raise ValueError("query must appear in the user message")
            return {"places": [{"id": p.id, "name": p.name, "category": p.category}
                                for p in search(inp.query, self.catalog)[:5]]}
        raise ValueError("unknown tool")
