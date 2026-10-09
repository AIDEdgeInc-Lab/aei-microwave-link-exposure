# Changelog

All notable changes to this project are recorded here. This project is
published on PyPI: https://pypi.org/project/aei-microwave-link-exposure/.

## [0.2.0] - 2026-10-09

### Changed -- predicted rain attenuation is different. Please re-run saved analyses.

- **The rain-coefficient table did not match ITU-R P.838-3.** Releases up to 0.1.5 looked k and alpha up in a 24-row table "transcribed from the published
  recommendation"; compared with Table 5 of the Recommendation, 21 of the 24 rows were wrong (only 1, 2 and 4 GHz were right). The Recommendation defines k and alpha
  as continuous functions of frequency (its equations 2 and 3, constants in Tables 1-4); 0.2.0 evaluates those equations directly. There is no table and no interpolation any more.
- **Size of the change (vertical polarization, same rain rate).** The old library under-stated specific attenuation: at 5-10 GHz it gave 0.09-0.43 of the Recommendation's
  value (e.g. 10 GHz, 32 mm/h: 0.071 dB/km instead of 0.763); at 10.5-20 GHz 0.17-0.95; at 21-100 GHz 0.95-0.99 (32 mm/h; see the Velorona RAIN_COEFFICIENT_AUDIT). Links in the 6-10 GHz bands, where much microwave backhaul runs,
  change most, so their predicted attenuation, exposure ratio and severity increase, and some move to a worse class.
- Terrestrial links use path elevation 0 and tilt 0 (H) / 90 degrees (V): equations (4)-(5) reduce to kH/kV and alphaH/alphaV. The 1-100 GHz limit of this library is unchanged
  (the Recommendation covers 1-1000 GHz). The P.530 effective-path factor, the rain-rate selection and the severity thresholds are unchanged.
- Verified against Table 5 of the Recommendation at every tabulated frequency 1-100 GHz (`tests/test_p838_table5.py`, generated from the ITU PDF) and against the open-source ITU-Rpy 0.4.0.
- `_P838_TABLE` is removed (it was private).

## [0.1.5] - 2026-10-08

### Changed

- PyPI project links: Homepage now points to https://aidedgeinc.com/tools/ and a Source link points to this repository (package
  metadata only; no code, API or dependency change).

## [0.1.4] - 2026-09-18

### Fixed

- `estimate_rain_attenuation()` reproduces the caller's frequency exactly in
  its `assumption` string. It was formatted with `{freq_ghz:.0f}`, so a
  7.25 GHz input read back as "7 GHz". That string is the method disclosure
  and is quoted verbatim by downstream evidence exports, where it appeared
  beside the same frequency at full precision -- a record that contradicted
  itself within one row. Shortest round-trip is used rather than `%g`, which
  would truncate 18.123456 GHz to 18.1235. `rain_rate_mm_h` is unchanged.
- Corrected license metadata to Apache-2.0 (previously inconsistent with README/PyPI listing).

## [0.1.3] - 2026-09-04

### Changed

- **License changed from MIT to Apache-2.0**, for consistency with
  other AID Edge aei-* engineering libraries (aei-geo-features,
  aei-3gpp-kpi-validator). Versions 0.1.0-0.1.2 remain under MIT as
  originally published; this change applies to 0.1.3 and later only.

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
