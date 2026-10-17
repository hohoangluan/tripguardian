"""Feature ontology (config/ontology.yaml): the feature ids that every source's observations and the User Profile share.

Observations may only carry a feature and value listed here (gate, docs/CORPUS.md §6).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .crawl.common.files import ROOT

PATH = ROOT / "config" / "ontology.yaml"
COMPANIONS = ROOT / "config" / "companions.yaml"
UNKNOWN = "unknown"
VERIFY = ("always", "sampled")
CHECK = ("span",)  # review observations of this feature get a second Extractor read (REVIEW_VERIFY)
NEEDS = ("amount_vnd", "days", "hour", "who", "verdict")  # fields a detail kind requires beyond its text
AUDIT = ("full", "sampled")  # Judge reads every detail of the kind / a sample
DETAIL_PREFIX = "detail."
DETAIL_GROUP = "detail"


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
class DetailKind:
    """A free-text observation kind (`detail.<id>`): words copied from a source, with fields the gate checks."""
    id: str
    hint: str
    claim: str  # what a source must state, for the Judge; {text} (and for fit {who}, {verdict}) are filled in
    audit: str = "sampled"
    targeted: bool = False  # an extremes / keywords sample counts
    owner: bool = False  # the business's own source (official page) counts
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Companion:
    id: str
    vi: str
    synonyms: tuple[str, ...]
    suitability: str | None  # ontology feature counting the same people


def fold_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split()).casefold()


@dataclass(frozen=True)
class Ontology:
    version: int
    groups: tuple[str, ...]
    contexts: dict[str, tuple[str, ...]]
    features: dict[str, Feature]
    stay: frozenset[str] = frozenset()  # "feature" or "feature=value" a lodging (category group `stay`) may carry
    details: dict[str, DetailKind] = field(default_factory=dict)
    companions: dict[str, Companion] = field(default_factory=dict)
    sensitive: frozenset[str] = frozenset()  # companions whose `bad` fit is a caution value

    def applies(self, feature: str, value: str, category_group: str | None) -> bool:
        """Lodging carries only the stay set (config/ontology.yaml stay_features); every other place carries all."""
        return category_group != "stay" or feature in self.stay or f"{feature}={value}" in self.stay

    def valid(self, feature: str, value: str) -> bool:
        f = self.features.get(feature)
        return f is not None and value in f.values

    def valid_context(self, key: str, value: str) -> bool:
        return value == UNKNOWN or value in self.contexts.get(key, ())

    def valid_detail(self, feature: str) -> bool:
        return self.detail_kind(feature) is not None

    def detail_kind(self, feature: str) -> DetailKind | None:
        return self.details.get(feature[len(DETAIL_PREFIX):]) if feature.startswith(DETAIL_PREFIX) else None

    def who(self, text: str) -> str:
        """Companion id when the words are an id or contain a synonym (longest synonym first); else the words as written
        (normalised): a person not in config/companions.yaml stays as the source said it."""
        key = fold_text(text)
        if key in self.companions:
            return key
        pairs = sorted(((fold_text(w), c.id) for c in self.companions.values() for w in c.synonyms),
                       key=lambda p: -len(p[0]))
        for word, cid in pairs:
            if word and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", key):
                return cid
        return key

    def as_feature(self, fid: str) -> Feature:
        """The ontology feature, or a stand-in for a detail kind (group `detail`, any value) so code written for
        features (judge audit, labels) handles both."""
        kind = self.detail_kind(fid)
        if kind is None:
            return self.features[fid]
        return Feature(fid, DETAIL_GROUP, ("*",), kind.hint)

    def prompt_text(self) -> str:
        lines = [f"- {f.id} = {' | '.join(f.values)}: {f.hint}" for f in self.features.values()]
        lines += [f"context {k} = {' | '.join(v)} | {UNKNOWN}" for k, v in self.contexts.items()]
        if self.details:
            lines.append("Detail kinds (kind: what to copy):")
            lines += [f"- detail {k.id}: {k.hint}" for k in self.details.values()]
            lines.append(f"who = {' | '.join(self.companions)} (or the source's own word)")
            lines.append("verdict = good | bad | conditional")
        return "\n".join(lines)


def parse(raw: dict, companions_raw: dict | None = None) -> Ontology:
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
    details = parse_details(raw.get("details") or ())
    companions, sensitive = parse_companions(companions_raw, features)
    return Ontology(int(raw["version"]), groups, {k: tuple(v) for k, v in raw["contexts"].items()}, features, stay,
                    details, companions, sensitive)


def parse_details(specs) -> dict[str, DetailKind]:
    details: dict[str, DetailKind] = {}
    for spec in specs:
        kid = spec["id"]
        if kid in details:
            raise ValueError(f"duplicate detail kind {kid}")
        if "{text}" not in spec["claim"]:
            raise ValueError(f"detail {kid}: claim needs {{text}}")
        needs = tuple(spec.get("needs") or ())
        if not set(needs) <= set(NEEDS):
            raise ValueError(f"detail {kid}: unknown needs {sorted(set(needs) - set(NEEDS))}")
        audit = spec.get("audit", "sampled")
        if audit not in AUDIT:
            raise ValueError(f"detail {kid}: audit must be one of {AUDIT}")
        details[kid] = DetailKind(kid, spec["hint"], spec["claim"], audit, bool(spec.get("targeted")),
                                  bool(spec.get("owner")), needs)
    return details


def parse_companions(raw: dict | None, features: dict[str, Feature]) -> tuple[dict[str, Companion], frozenset[str]]:
    companions: dict[str, Companion] = {}
    for spec in (raw or {}).get("companions") or ():
        cid = spec["id"]
        if cid in companions:
            raise ValueError(f"duplicate companion id {cid}")
        suit = spec.get("suitability")
        if suit is not None and suit not in features:
            raise ValueError(f"companion {cid}: suitability {suit} is not an ontology feature")
        companions[cid] = Companion(cid, spec["vi"], tuple(spec.get("synonyms") or ()), suit)
    sensitive = frozenset((raw or {}).get("sensitive") or ())
    if not sensitive <= set(companions):
        raise ValueError(f"sensitive companions not in the list: {sorted(sensitive - set(companions))}")
    return companions, sensitive


_LOADED: dict[tuple, Ontology] = {}


def _stamp(path: Path) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def load(path: Path = PATH, companions_path: Path = COMPANIONS) -> Ontology:
    """Parsed once per file version: the YAML parse costs ~0.18 s and every request validates against it. A file that
    changed on disk (mtime or size) is parsed again."""
    key = (str(path), _stamp(path), str(companions_path), _stamp(companions_path))
    hit = _LOADED.get(key)
    if hit is None:
        companions = yaml.safe_load(companions_path.read_text(encoding="utf-8")) if companions_path.exists() else None
        hit = _LOADED[key] = parse(yaml.safe_load(path.read_text(encoding="utf-8")), companions)
        for old in [k for k in _LOADED if k[0] == key[0] and k[2] == key[2] and k != key]:
            del _LOADED[old]
    return hit
