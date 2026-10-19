"""Great-circle distance helpers (PostGIS is not required)."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEGREE_LATITUDE = 111.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1_r, lng1_r, lat2_r, lng2_r = map(math.radians, (lat1, lng1, lat2, lng2))
    a = (
        math.sin((lat2_r - lat1_r) / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin((lng2_r - lng1_r) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box_deltas(latitude: float, radius_km: float) -> tuple[float, float]:
    """Degrees of latitude / longitude that cover ``radius_km`` around ``latitude``.

    Used as an index-friendly prefilter before the exact haversine check.
    """
    lat_delta = radius_km / KM_PER_DEGREE_LATITUDE
    lng_delta = radius_km / (KM_PER_DEGREE_LATITUDE * max(math.cos(math.radians(latitude)), 0.01))
    return lat_delta, lng_delta


def eta_minutes(distance_km: float, average_speed_kmph: float) -> int:
    if average_speed_kmph <= 0:
        return 0
    return max(math.ceil(distance_km / average_speed_kmph * 60), 1) if distance_km > 0 else 0
