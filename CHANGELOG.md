# Changelog

All notable changes to this project are recorded here. This project is
published on PyPI: https://pypi.org/project/aei-microwave-link-exposure/.

## [0.1.2] - 2026-09-04

### Changed

- Default Explorer map view recentered on Lake Ontario/Toronto waterfront
  for clearer geographic context; refreshed screenshot to reflect current
  UI (previous screenshot predated the My Sites redesign).

## [0.1.1] - 2026-09-04

### Fixed

- Fix images and badges not rendering in PyPI long_description (relative
  paths don't resolve off-GitHub); no functional change.

## [0.1.0] - 2026-09-04

### Added

- `calculate_exposure()` - ITU-R P.838-3 (specific rain attenuation) +
  ITU-R P.530 (effective path length) exposure calculation for a
  terrestrial microwave point-to-point link, given weather observations at
  each endpoint.
- `MicrowaveSite` / `MicrowaveLink` domain model with mandatory
  `Provenance` (`REAL` / `DERIVED` / `DEMO` / `NOT_AVAILABLE` /
  `USER_PROVIDED`) on every object.
- `assess_representativeness()` - compares a live ECCC observing station,
  an Open-Meteo model reading, and (where available) ECCC radar for a
  given site, producing a plain-language, threshold-driven
  `RepresentativenessLevel`.
- Optional real-data adapters: Ontario GeoHub (MNRF tower dataset), ISED
  Spectrum Licences Site Data, Open-Meteo (keyless), ECCC SWOB-Realtime,
  ECCC radar (`RADAR_1KM_RRAI`).
- **Microwave Weather Explorer** (`app.py`, Streamlit + Folium) - upload
  your own infrastructure sites, analyze them against live public weather
  evidence, inspect the result on a map, and export an Evidence CSV; plus
  a bundled real-infrastructure/demo-network example region (GTA/York
  Region, Canada).
- Zero runtime dependencies in the core library (`aei_mw_exposure`);
  `requests`/`streamlit`/`folium`/`streamlit-folium` are all gated behind
  optional extras.
