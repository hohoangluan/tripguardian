"""Sunrise and sunset, computed here (NOAA solar position). No network, no cache, no new dependency.

Planning needs these to pin sunset places to the end of a day and misty places to its start.
"""

import math
from datetime import date

_J2000 = date(2000, 1, 1).toordinal()
_ZENITH = math.radians(90.833)  # 90°50': the sun's disc plus average refraction at the horizon


def _sun_position(days_since_j2000: float) -> tuple[float, float]:
    """Equation of time in minutes and solar declination in radians."""
    n = days_since_j2000
    mean_anomaly = math.radians((357.529 + 0.98560028 * n) % 360)
    mean_longitude = (280.459 + 0.98564736 * n) % 360
    ecliptic_longitude = math.radians((mean_longitude + 1.915 * math.sin(mean_anomaly)
                                       + 0.020 * math.sin(2 * mean_anomaly)) % 360)
    obliquity = math.radians(23.439 - 0.00000036 * n)
    declination = math.asin(math.sin(obliquity) * math.sin(ecliptic_longitude))
    right_ascension = math.degrees(math.atan2(math.cos(obliquity) * math.sin(ecliptic_longitude),
                                              math.cos(ecliptic_longitude))) % 360
    equation_of_time = 4 * ((mean_longitude - right_ascension + 180) % 360 - 180)
    return equation_of_time, declination


def sun_times(d: date, lat: float, lng: float, tz_offset_h: float = 7.0) -> tuple[int, int] | None:
    """Local clock minutes of sunrise and sunset, or None where the sun neither rises nor sets that day."""
    equation_of_time, declination = _sun_position(d.toordinal() - _J2000 + 0.5)
    phi = math.radians(lat)
    cos_hour_angle = ((math.cos(_ZENITH) - math.sin(phi) * math.sin(declination))
                      / (math.cos(phi) * math.cos(declination)))
    if not -1.0 <= cos_hour_angle <= 1.0:
        return None
    half_day_min = 4 * math.degrees(math.acos(cos_hour_angle))
    solar_noon_min = 720 - 4 * lng - equation_of_time + tz_offset_h * 60
    return round(solar_noon_min - half_day_min), round(solar_noon_min + half_day_min)
