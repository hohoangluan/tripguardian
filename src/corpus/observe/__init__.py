"""Observe (docs/CORPUS.md §4): each source's evidence -> observations in one shared format.

One sub-package per source (gmaps now, tiktok later); all write data/<source>/observations/<fid_dir>.json with
records built by observation(), which corpus.aggregate reads without knowing the source.
"""

CONTEXT_KEYS = ("time_of_day", "day_type", "weather")


def observation(*, id: str, place_fid: str, feature: str, value: str, context: dict, source_type: str, source_id: str,
                author: str | None, observed_at: str | None, quote: str, field: str, extractor: str,
                ontology_version: int, start_s: float | None = None, end_s: float | None = None) -> dict:
    return {"id": id, "place_fid": place_fid, "feature": feature, "value": value,
            "context": {k: context[k] for k in CONTEXT_KEYS}, "source_type": source_type, "source_id": source_id,
            "author": author, "observed_at": observed_at,
            "span": {"quote": quote, "field": field, "start_s": start_s, "end_s": end_s},
            "extractor": extractor, "ontology_version": ontology_version}
