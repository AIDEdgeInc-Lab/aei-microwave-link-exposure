"""GTA / York Region locations offered by the Explorer's location picker.

V1 scope is explicitly regional, not nationwide (see the infrastructure
adapters' own docstrings for why: they've only been checked against this
area). A predefined list is enough for V1 -- no geocoding service.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    name: str
    center_lat: float
    center_lon: float
    half_width_deg: float  # bbox half-width, applied to both lat and lon

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_lon, min_lat, max_lon, max_lat) for ArcGIS envelope queries."""
        return (
            self.center_lon - self.half_width_deg,
            self.center_lat - self.half_width_deg,
            self.center_lon + self.half_width_deg,
            self.center_lat + self.half_width_deg,
        )


LOCATIONS: list[Location] = [
    Location("GTA / York Region (wide view)", 43.80, -79.45, 0.55),
    Location("Toronto", 43.6532, -79.3832, 0.13),
    Location("Newmarket", 44.0592, -79.4613, 0.10),
    Location("Markham", 43.8561, -79.3370, 0.10),
    Location("Richmond Hill", 43.8828, -79.4403, 0.10),
    Location("Vaughan", 43.8361, -79.4985, 0.10),
    Location("Mississauga", 43.5890, -79.6441, 0.13),
]

LOCATIONS_BY_NAME = {loc.name: loc for loc in LOCATIONS}
