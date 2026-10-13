"""corpus.index online side on a tiny hand-made index (no model, no files): a place matches only through several
photos of several posters, kinds below the minimum are dropped, and style tags need several posters."""

import json

import numpy as np

from corpus.index import Index
from corpus.index.compile import place_styles

CFG = {"places_by_photos": {"min_photos": 2, "min_authors": 2, "per_place": 3, "owner_weight": 0.6},
       "clusters": {"k_max": 4, "min_places": 2, "photos": 3}, "search": {"k_photos": 50, "k_spans": 10}}
STYLES = {"version": 1, "min_authors": 2, "styles": [{"id": "retro", "label": "Hoài cổ", "hint": ""},
                                                       {"id": "retro_saigon", "parent": "retro", "label": "Sài Gòn xưa", "hint": ""}]}


def unit(*v):
    a = np.array(v, np.float32)
    return a / np.linalg.norm(a)


def index(rows, places=None):
    vecs = np.stack([r.pop("v") for r in rows])
    places = places or {r["place_id"]: {"name": r["place_id"], "styles": {}, "near_duplicate_group": None} for r in rows}
    return Index(version="t", root=None, places=places, styles=STYLES, photo_vecs=vecs, photo_rows=rows, cfg=CFG)


def row(pid, author, v, owner=False):
    return {"place_id": pid, "file": f"gmaps/places/{pid}/photos/{author}.jpg", "author": author, "owner": owner,
            "source": "gmaps", "v": v}


def test_a_place_matches_only_through_several_photos_of_several_posters():
    ix = index([row("a", "u1", unit(1, 0, 0)), row("a", "u2", unit(1, 0.1, 0)),       # two posters: counts
                row("b", "u3", unit(1, 0, 0)),                                         # one photo: luck
                row("c", "u4", unit(1, 0, 0)), row("c", "u4", unit(1, 0.05, 0))])     # one poster twice: luck
    hits = ix.search_photos(unit(1, 0, 0))
    assert [p.place_id for p in ix.places_by_photos(hits)] == ["a"]
    assert {p.place_id for p in ix.places_by_photos(hits, min_photos=1, min_authors=1)} == {"a", "b", "c"}


def test_the_owners_photos_weigh_less_and_within_limits_the_search():
    ix = index([row("a", "u1", unit(1, 0, 0), owner=True), row("a", "u2", unit(1, 0, 0), owner=True),
                row("b", "u3", unit(1, 0.2, 0)), row("b", "u4", unit(1, 0.2, 0))])
    ranked = ix.places_by_photos(ix.search_photos(unit(1, 0, 0)))
    assert [p.place_id for p in ranked] == ["b", "a"]
    assert {h.place_id for h in ix.search_photos(unit(1, 0, 0), within={"b"})} == {"b"}


def test_similar_places_leave_out_the_place_and_its_near_duplicates():
    rows = [row(p, f"u{p}", unit(1, i * 0.1, 0)) for i, p in enumerate("abcd")]
    places = {p: {"name": p, "styles": {}, "near_duplicate_group": "g" if p in "ab" else None} for p in "abcd"}
    ix = index(rows, places)
    assert [p.place_id for p in ix.similar_places("a")] == ["c", "d"]


def test_clusters_need_enough_places_and_carry_real_photos_and_the_child_style():
    rows = [row(f"r{i}", f"u{i}", unit(1, 0.01 * i, 0)) for i in range(3)] + \
           [row(f"g{i}", f"v{i}", unit(0, 1, 0.01 * i)) for i in range(3)]
    places = {r["place_id"]: {"name": r["place_id"], "near_duplicate_group": None,
                              "styles": {"retro": {}, "retro_saigon": {}} if r["place_id"].startswith("r") else {}}
              for r in rows}
    ix = index(rows, places)
    assert ix.clusters(["r0", "r1", "g0"]) == []  # fewer than 2 * min_places
    kinds = ix.clusters(list(places))
    assert len(kinds) == 2
    retro = next(k for k in kinds if k.places[0].startswith("r"))
    assert retro.style == "retro_saigon"  # the child tag beats its parent
    assert all(f in {r["file"] for r in ix.photo_rows if r["place_id"] == p} for p, f in retro.photos)


def test_a_style_tag_needs_several_posters_and_a_child_counts_for_its_parent(tmp_path):
    def obs(author, feature, n):
        return {"id": f"gmaps_style:p{n}:{feature}", "feature": feature, "author": author, "source_id": f"p{n}",
                "span": {"field": f"gmaps/places/x/photos/p{n}.jpg", "quote": "đèn vàng, ghế gỗ"}}
    d = tmp_path / "gmaps" / "style_observations"
    d.mkdir(parents=True)
    (d / "0x1_0x2.json").write_text(json.dumps({"observations": [
        obs("u1", "retro_saigon", 1), obs("u2", "retro_saigon", 2), obs("u3", "retro", 3), obs("u4", "minimal", 4)]}))
    tags = place_styles(tmp_path, "0x1:0x2", STYLES)
    assert set(tags) == {"retro_saigon", "retro"}  # minimal: one poster only
    assert tags["retro"]["authors"] == 3 and tags["retro_saigon"]["evidence"][0]["file"].endswith("p1.jpg")
