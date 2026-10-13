"""corpus.index: the semantic index of the corpus (docs/CORPUS.md §Chỉ mục ngữ nghĩa). Offline writes it
(`python -m corpus index`), online only reads it (Index)."""

from .compile import run as compile_index
from .embedder import Embedder
from .query import Cluster, Index, PhotoHit, PlaceHit, SpanHit, TextVec
from .vectors import run as embed_vectors

__all__ = ["Cluster", "Embedder", "Index", "PhotoHit", "PlaceHit", "SpanHit", "TextVec", "compile_index", "embed_vectors"]
