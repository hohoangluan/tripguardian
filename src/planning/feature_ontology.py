"""The feature ontology, parsed once per process: reading config/ontology.yaml costs ~0.1 s, and the lodging list, the
relax check and the validator each asked for it on every call (an edit paid it twice)."""

from functools import cache

from corpus.ontology import load


@cache
def ontology():
    return load()
