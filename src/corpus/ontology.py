"""Feature ontology (config/ontology.yaml): the feature ids that every source's observations and the User Profile share.

Observations may only carry a feature and value listed here (gate, docs/specs/CORPUS_SPEC.md §6).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from .crawl.common.files import ROOT

PATH = ROOT / "config" / "ontology.yaml"
UNKNOWN = "unknown"
VERIFY = ("always", "sampled")


@dataclass(frozen=True)
class Feature:
    id: str
    group: str
    values: tuple[str, ...]
    hint: str
    verify: str = "sampled"
    caution_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ontology:
    version: int
    groups: tuple[str, ...]
    contexts: dict[str, tuple[str, ...]]
    features: dict[str, Feature]

    def valid(self, feature: str, value: str) -> bool:
        f = self.features.get(feature)
        return f is not None and value in f.values

    def valid_context(self, key: str, value: str) -> bool:
        return value == UNKNOWN or value in self.contexts.get(key, ())

    def prompt_text(self) -> str:
        lines = [f"- {f.id} = {' | '.join(f.values)}: {f.hint}" for f in self.features.values()]
        lines += [f"context {k} = {' | '.join(v)} | {UNKNOWN}" for k, v in self.contexts.items()]
        return "\n".join(lines)


def parse(raw: dict) -> Ontology:
    groups = tuple(raw["groups"])
    features: dict[str, Feature] = {}
    for spec in raw["features"]:
        fid = spec["id"]
        if fid in features:
            raise ValueError(f"duplicate feature id {fid}")
        values = tuple(str(v) for v in spec.get("values") or ())
        if not values:
            raise ValueError(f"feature {fid}: no values")
        if spec["group"] not in groups:
            raise ValueError(f"feature {fid}: unknown group {spec['group']}")
        caution = tuple(spec.get("caution_values") or ())
        if not set(caution) <= set(values):
            raise ValueError(f"feature {fid}: caution values {caution} not in {values}")
        verify = spec.get("verify", "sampled")
        if verify not in VERIFY:
            raise ValueError(f"feature {fid}: verify must be one of {VERIFY}")
        features[fid] = Feature(fid, spec["group"], values, spec["hint"], verify, caution)
    return Ontology(int(raw["version"]), groups, {k: tuple(v) for k, v in raw["contexts"].items()}, features)


def load(path: Path = PATH) -> Ontology:
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")))
