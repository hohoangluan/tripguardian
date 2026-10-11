"""Feature ontology (config/ontology.yaml): the feature ids that every source's observations and the User Profile share.

Observations may only carry a feature and value listed here (gate, docs/CORPUS.md §6).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .crawl.common.files import ROOT

PATH = ROOT / "config" / "ontology.yaml"
UNKNOWN = "unknown"
VERIFY = ("always", "sampled")
CHECK = ("span",)  # review observations of this feature get a second Extractor read (REVIEW_VERIFY)


@dataclass(frozen=True)
class Feature:
    id: str
    group: str
    values: tuple[str, ...]
    hint: str
    verify: str = "sampled"
    caution_values: tuple[str, ...] = ()
    span_check: bool = False
    claims: dict = field(default_factory=dict)  # value -> what a review must state, for REVIEW_VERIFY


@dataclass(frozen=True)
class Ontology:
    version: int
    groups: tuple[str, ...]
    contexts: dict[str, tuple[str, ...]]
    features: dict[str, Feature]
    stay: frozenset[str] = frozenset()  # "feature" or "feature=value" a lodging (category group `stay`) may carry

    def applies(self, feature: str, value: str, category_group: str | None) -> bool:
        """Lodging carries only the stay set (config/ontology.yaml stay_features); every other place carries all."""
        return category_group != "stay" or feature in self.stay or f"{feature}={value}" in self.stay

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
        check = spec.get("check")
        if check is not None and check not in CHECK:
            raise ValueError(f"feature {fid}: check must be one of {CHECK}")
        claims = {str(k): v for k, v in (spec.get("claims") or {}).items()}
        if check == "span" and set(claims) != set(values):
            raise ValueError(f"feature {fid}: check: span needs claims for exactly {values}")
        features[fid] = Feature(fid, spec["group"], values, spec["hint"], verify, caution, check == "span", claims)
    stay = frozenset(str(s) for s in raw.get("stay_features") or ())
    for s in stay:
        fid, _, value = s.partition("=")
        if fid not in features or (value and value not in features[fid].values):
            raise ValueError(f"stay_features: unknown {s}")
    return Ontology(int(raw["version"]), groups, {k: tuple(v) for k, v in raw["contexts"].items()}, features, stay)


def load(path: Path = PATH) -> Ontology:
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")))
