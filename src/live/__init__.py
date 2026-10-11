"""Live Context: facts fetched per request from outside (docs/PLANNING.md §Live Context).

Three rules hold for everything in here:
  - it never writes Place Intelligence; the only thing it writes is its own cache under data/live/;
  - every value it returns carries `source` and `fetched_at`, so Planning can label it an estimate;
  - a source that does not answer raises Unavailable. Nothing here invents a value to fill a gap.
"""

from .advisories import advisories
from .buses import buses, buses_url
from .events import events
from .flights import flights, flights_url
from .geocode import geocode, geosearch
from .holidays import holidays
from .http import Unavailable
from .osrm import route_shape, travel_matrix
from .settings import Settings
from .settings import load as load_settings
from .lodging import lodging_near, lodging_seen
from .sun import sun_times
from .weather import weather

__all__ = ["Settings", "Unavailable", "advisories", "buses", "buses_url", "events", "flights", "flights_url", "geocode", "geosearch", "holidays", "load_settings", "lodging_near", "lodging_seen", "route_shape",
           "sun_times", "travel_matrix", "weather"]
