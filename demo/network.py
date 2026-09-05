"""DEMO/SYNTHETIC microwave network around the Greater Toronto Area.

This is demo-only content -- it belongs to the Streamlit app, not the
library. It is built entirely out of ``aei_mw_exposure`` domain objects
(``MicrowaveSite``, ``MicrowaveLink``); it does not define its own types.

Site coordinates are real public landmarks, chosen so the map reads as a
real place. Frequency, polarization and fade margin per link are
illustrative values typical for the stated band/hop-length combination.
Both sites and links are explicitly ``provenance=Provenance.DEMO`` so they
can never be mistaken for the REAL infrastructure loaded separately in
``demo/infrastructure.py``.
"""

from __future__ import annotations

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance

_SOURCE = "AID Edge Inc. -- illustrative demo network, not real infrastructure"

DEMO_SITES: list[MicrowaveSite] = [
    MicrowaveSite("cn_tower", "CN Tower (downtown core)", 43.6426, -79.3871, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("scarborough", "Scarborough Civic Centre", 43.7764, -79.2318, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("mississauga", "Mississauga City Centre", 43.5890, -79.6441, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("vaughan", "Vaughan Metropolitan Centre", 43.7942, -79.5276, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("markham", "Markham Civic Centre", 43.8561, -79.3370, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("pearson", "Pearson Airport area", 43.6777, -79.6248, Provenance.DEMO, source=_SOURCE),
    MicrowaveSite("etobicoke", "Etobicoke Civic Centre", 43.6205, -79.5132, Provenance.DEMO, source=_SOURCE),
]

_SITES_BY_ID = {s.id: s for s in DEMO_SITES}

# (link_id, site_a_id, site_b_id, freq_ghz, polarization, fade_margin_db)
# Short urban hops -> higher band (18/23/38 GHz), typical for dense metro backhaul.
# Longer suburban hops -> lower band (6/11/15 GHz), larger fade margin by design.
_RAW_LINKS = [
    ("cn-scarb", "cn_tower", "scarborough", 18.0, "V", 32.0),
    ("cn-etob", "cn_tower", "etobicoke", 23.0, "V", 30.0),
    ("etob-pearson", "etobicoke", "pearson", 38.0, "V", 26.0),
    ("pearson-miss", "pearson", "mississauga", 23.0, "H", 30.0),
    ("miss-vaughan", "mississauga", "vaughan", 11.0, "V", 38.0),
    ("vaughan-markham", "vaughan", "markham", 15.0, "V", 34.0),
    ("markham-scarb", "markham", "scarborough", 11.0, "H", 38.0),
    ("cn-vaughan", "cn_tower", "vaughan", 6.0, "V", 42.0),
]

DEMO_LINKS: list[MicrowaveLink] = [
    MicrowaveLink(
        id=link_id,
        site_a=_SITES_BY_ID[a],
        site_b=_SITES_BY_ID[b],
        frequency_ghz=freq,
        polarization=pol,
        fade_margin_db=margin,
        provenance=Provenance.DEMO,
        source=_SOURCE,
    )
    for link_id, a, b, freq, pol, margin in _RAW_LINKS
]
