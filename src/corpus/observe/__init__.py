"""Observe (docs/CORPUS.md §4): each source's evidence -> observations in one shared format.

One sub-package per source (gmaps now, tiktok later); all write data/<source>/observations/<fid_dir>.json with
records built by observation(), which corpus.aggregate reads without knowing the source.
"""

CONTEXT_KEYS = ("time_of_day", "day_type", "weather")

# `sample` of an observation whose source was picked for what it says, not as it came: Maps' lowest / highest rated
# reviews ("extremes") and reviews found by searching a word ("keywords"). Such a sample over-represents complaints
# or one topic, so it may say THAT something is there (effort, facts of the place), never how many people think so.
TARGETED = {"extremes", "keywords"}
TARGETED_GROUPS = {"effort", "operation"}  # effort and visit_duration
TARGETED_FEATURES = {"entry_fee", "booking_needed", "cash_only", "vegetarian_options", "setting", "weather_exposed",
                     "wheelchair"}  # condition_change stays out of aggregate; judge status still reads its reports


def targeted_ok(feature) -> bool:
    """A targeted sample's observation of this ontology feature counts: effort and facts of the place, not opinions
    (quality, service, value, crowd, who it suits) whose share it would skew."""
    return feature.group in TARGETED_GROUPS or feature.id in TARGETED_FEATURES


def observation(*, id: str, place_fid: str, feature: str, value: str, context: dict, source_type: str, source_id: str,
                author: str | None, observed_at: str | None, quote: str, field: str, extractor: str,
                ontology_version: int, start_s: float | None = None, end_s: float | None = None,
                sample: str | None = None) -> dict:
    out = {"id": id, "place_fid": place_fid, "feature": feature, "value": value,
           "context": {k: context[k] for k in CONTEXT_KEYS}, "source_type": source_type, "source_id": source_id,
           "author": author, "observed_at": observed_at,
           "span": {"quote": quote, "field": field, "start_s": start_s, "end_s": end_s},
           "extractor": extractor, "ontology_version": ontology_version}
    if sample:
        out["sample"] = sample
    return out
