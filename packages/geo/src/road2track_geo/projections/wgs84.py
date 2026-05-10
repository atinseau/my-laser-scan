"""Conversions WGS84 ↔ ENU local.

Approximation flat-earth, valable pour des tronçons < 10-15 km autour d'un point
d'origine. Erreur < 0.3 m / km à nos latitudes.

Pour des tronçons plus longs ou plus de précision, passer à pyproj + EPSG:4978
(ECEF) puis rotation. Pour le POC, suffisant.

Cf. specs/06-modele-donnees.md §1 (WGS84 stocké, ENU local interne).
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

EARTH_RADIUS_M: float = 6371000.0


def wgs84_to_enu_flat(
    lat: float,
    lon: float,
    alt: float,
    origin_lat: float,
    origin_lon: float,
    origin_alt: float,
) -> tuple[float, float, float]:
    """Convertit (lat, lon, alt) WGS84 → (east, north, up) ENU local."""
    dlat = math.radians(lat - origin_lat)
    dlon = math.radians(lon - origin_lon)
    east = EARTH_RADIUS_M * math.cos(math.radians(origin_lat)) * dlon
    north = EARTH_RADIUS_M * dlat
    up = alt - origin_alt
    return east, north, up


def wgs84_array_to_enu_flat(
    lats: NDArray[np.float64],
    lons: NDArray[np.float64],
    alts: NDArray[np.float64],
    origin_lat: float,
    origin_lon: float,
    origin_alt: float,
) -> NDArray[np.float64]:
    """Conversion vectorisée. Retourne un tableau (N, 3) ENU."""
    dlat = np.radians(lats - origin_lat)
    dlon = np.radians(lons - origin_lon)
    east = EARTH_RADIUS_M * np.cos(np.radians(origin_lat)) * dlon
    north = EARTH_RADIUS_M * dlat
    up = alts - origin_alt
    return np.stack([east, north, up], axis=1)


def enu_to_wgs84_flat(
    east: float,
    north: float,
    up: float,
    origin_lat: float,
    origin_lon: float,
    origin_alt: float,
) -> tuple[float, float, float]:
    """Inverse : (east, north, up) → (lat, lon, alt) WGS84."""
    dlat = north / EARTH_RADIUS_M
    dlon = east / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))
    lat = origin_lat + math.degrees(dlat)
    lon = origin_lon + math.degrees(dlon)
    alt = origin_alt + up
    return lat, lon, alt
