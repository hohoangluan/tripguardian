"""A base picked from a search (a booked lodging) is a centre by its own point, with no corpus record."""

from types import SimpleNamespace

from decision.fit import centers


def test_a_base_with_a_point_is_the_first_centre():
    base = SimpleNamespace(place_id=None, text="Ana Mandara Villas", lat=11.93, lng=108.42)
    si = SimpleNamespace(context=SimpleNamespace(base=base), anchors=[])
    cfg = SimpleNamespace(center={"name": "Chợ Đà Lạt", "lat": 11.94, "lng": 108.45})
    assert centers(si, {}, cfg) == [("Ana Mandara Villas", (11.93, 108.42))]
    si.context.base = SimpleNamespace(place_id=None, text="somewhere", lat=None, lng=None)
    assert centers(si, {}, cfg) == [("Chợ Đà Lạt", (11.94, 108.45))]
