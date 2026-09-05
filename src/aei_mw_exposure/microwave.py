"""Terrestrial microwave domain model: sites and point-to-point links.

Deliberately small. No RSL/ATPC/state-machine modelling, no vendor
adapters, no operator-specific logic -- this is the generic geometry and
identity a link needs to be run through the physics layer, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Union

from .geometry import haversine_km
from .provenance import Provenance

Polarization = Literal["H", "V"]

_VALID_POLARIZATIONS = ("H", "V")

# What a source's published, display-only fields may contain. Deliberately
# a plain scalar union, not Any: different public sources publish
# different, non-overlapping fields (height, licensee, band, ...), but all
# of them are simple values -- never a nested structure. This is checked
# by convention (every current adapter only ever stores str/int/float),
# not enforced at runtime; it exists so the type hint tells the truth.
MetadataValue = Union[str, int, float]


@dataclass(frozen=True)
class MicrowaveSite:
    """A point location -- a real tower/station, or a demo/placeholder point.

    ``provenance`` is required, not defaulted: every site must say where
    its data comes from. ``source`` is a free-text citation (e.g. an
    agency + dataset name); ``metadata`` carries whatever else the source
    actually published (height, licensee, frequency band, ...) as plain
    key/value pairs -- deliberately unstructured, since different public
    sources publish different, non-overlapping fields, and a field that
    isn't in ``metadata`` simply wasn't published for this site. Never
    invent a value to fill a gap.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    provenance: Provenance
    source: Optional[str] = None
    metadata: Dict[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude out of range: {self.longitude}")


@dataclass(frozen=True)
class MicrowaveLink:
    """A point-to-point microwave hop between two sites.

    ``length_km`` is never supplied by the caller -- it is always derived
    from the two sites' real coordinates via haversine distance, so it
    can't drift out of sync with where the sites actually are.

    ``provenance`` is required and is a statement about the LINK, not
    about its endpoints: two REAL sites do not make a REAL link. This
    library never constructs a link from two independently-sourced real
    sites -- see ``aei_mw_exposure.infrastructure``, which only ever produces
    ``MicrowaveSite`` objects, never links, because public data does not
    establish which real sites (if any) talk to each other.
    """

    id: str
    site_a: MicrowaveSite
    site_b: MicrowaveSite
    frequency_ghz: float
    polarization: Polarization
    fade_margin_db: float
    provenance: Provenance
    source: Optional[str] = None
    length_km: float = field(init=False)

    def __post_init__(self) -> None:
        if self.site_a.id == self.site_b.id:
            raise ValueError("a link's two endpoints must be different sites")
        if self.frequency_ghz <= 0:
            raise ValueError(f"frequency_ghz must be positive, got {self.frequency_ghz}")
        if self.fade_margin_db <= 0:
            raise ValueError(f"fade_margin_db must be positive, got {self.fade_margin_db}")
        if self.polarization not in _VALID_POLARIZATIONS:
            raise ValueError(f"polarization must be one of {_VALID_POLARIZATIONS}, got {self.polarization!r}")
        distance = haversine_km(
            self.site_a.latitude, self.site_a.longitude, self.site_b.latitude, self.site_b.longitude
        )
        object.__setattr__(self, "length_km", distance)
