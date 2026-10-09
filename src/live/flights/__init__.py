"""Flights to and from the city, one module per source (RULE.md §2): data/live/flights/ holds its cache."""

from .google import flights
from .google import url as flights_url

__all__ = ["flights", "flights_url"]
