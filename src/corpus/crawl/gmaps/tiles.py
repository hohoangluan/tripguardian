"""Map tiles (lat, lng, zoom) covering a city area. A search shows about one browser viewport around its tile."""

import math

VIEWPORT = (1280, 900)  # px, as in browser.open_profile


def span(zoom: int, lat: float) -> tuple[float, float]:
    """(lat, lng) degrees the browser viewport shows at this zoom (Web Mercator, 256 px tiles)."""
    deg = 360 / (256 * 2 ** zoom)
    return VIEWPORT[1] * deg * math.cos(math.radians(lat)), VIEWPORT[0] * deg


def root_tiles(area, zoom: int) -> list[tuple]:
    lat0, lng0, lat1, lng1 = area
    dlat, dlng = span(zoom, (lat0 + lat1) / 2)
    nlat, nlng = math.ceil((lat1 - lat0) / dlat), math.ceil((lng1 - lng0) / dlng)
    return [(round(lat0 + (i + 0.5) * (lat1 - lat0) / nlat, 6), round(lng0 + (j + 0.5) * (lng1 - lng0) / nlng, 6), zoom)
            for i in range(nlat) for j in range(nlng)]


def children(tile: tuple) -> list[tuple]:
    """Four viewports one zoom in that together show the parent's viewport."""
    lat, lng, zoom = tile
    dlat, dlng = span(zoom, lat)
    return [(round(lat + a * dlat / 4, 6), round(lng + b * dlng / 4, 6), zoom + 1) for a in (-1, 1) for b in (-1, 1)]


def overlaps(tile: tuple, area) -> bool:
    lat, lng, zoom = tile
    dlat, dlng = span(zoom, lat)
    lat0, lng0, lat1, lng1 = area
    return lat0 - dlat / 2 <= lat <= lat1 + dlat / 2 and lng0 - dlng / 2 <= lng <= lng1 + dlng / 2


def bounds(tile: tuple, margin: float = 0.1) -> list[float]:
    """[lat0, lng0, lat1, lng1] the tile's viewport shows, widened by margin on each side."""
    lat, lng, zoom = tile
    dlat, dlng = span(zoom, lat)
    h, w = dlat * (0.5 + margin), dlng * (0.5 + margin)
    return [lat - h, lng - w, lat + h, lng + w]


def in_area(lat: float | None, lng: float | None, area) -> bool:
    if not area:
        return True
    lat0, lng0, lat1, lng1 = area
    return lat is not None and lat0 <= lat <= lat1 and lng0 <= lng <= lng1
