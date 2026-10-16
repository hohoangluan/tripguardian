"""Offline normalization of saved observations; raw sources and labels are never rewritten."""

from .run import Normalization, normalize

__all__ = ["Normalization", "normalize"]
