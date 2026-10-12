"""Geocoding, one module per external source (RULE.md §2): data/live/geocode/ holds its cache and nothing else."""

from .nominatim import geocode
from .photon import geosearch

__all__ = ["geocode", "geosearch"]
