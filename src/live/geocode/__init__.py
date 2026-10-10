"""Geocoding, one module per external source (RULE.md §2): data/live/geocode/ holds its cache and nothing else."""

from .address import search as geosearch
from .nominatim import geocode

__all__ = ["geocode", "geosearch"]
