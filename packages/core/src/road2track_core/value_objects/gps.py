"""Coordonnée géographique WGS84 (lat / lon / alt)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GPSCoord(BaseModel):
    """Coordonnée WGS84 immutable.

    Cf. specs/06-modele-donnees.md §3.
    """

    model_config = ConfigDict(frozen=True)

    lat: float = Field(ge=-90.0, le=90.0, description="Latitude en degrés décimaux WGS84")
    lon: float = Field(ge=-180.0, le=180.0, description="Longitude en degrés décimaux WGS84")
    alt: float = Field(description="Altitude en mètres au-dessus du géoïde WGS84")
