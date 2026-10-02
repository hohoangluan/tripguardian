"""Facts about a place that objectives, robustness and backups share, read from its serving record.

No evidence -> None or 0, never a guess: a place with no weather evidence is not counted as exposed.
"""

from corpus.serving import feature

from .model import Place


def _value(place: Place, fid: str) -> str | None:
    f = feature(place.rec, fid)
    return f["value"] if f else None


def exposure(place: Place) -> str | None:
    """exposed | sheltered | None. weather_exposed decides; without it, setting outdoor / indoor does."""
    w = _value(place, "weather_exposed")
    if w == "present":
        return "exposed"
    if w == "sheltered":
        return "sheltered"
    s = _value(place, "setting")
    return "exposed" if s == "outdoor" else "sheltered" if s == "indoor" else None


def preference(place: Place, soft_weights: list) -> float:
    """Sum of the positive soft weights whose feature value the place has. Context of a weight is ignored: Planning
    does not know it per visit."""
    return float(sum(w["weight"] for w in soft_weights
                     if w.get("weight", 0) > 0 and _value(place, w["feature"]) == w["value"]))


def kind_group(place: Place) -> str | None:
    """The category group: what "the same kind of experience" means for diversity and for a backup."""
    return place.rec["identity"].get("category_group")
