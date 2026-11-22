# Changelog

All notable changes to this project are recorded here. This project is
published on PyPI: https://pypi.org/project/aei-microwave-link-exposure/.

## [0.3.0] - 2026-11-22

Security baseline: invalid numbers and missing upstream values are refused instead of flowing into a result. Valid inputs give the same results as 0.2.0.

### Changed (Python support and dependency floors)

- **Python 3.9 is no longer supported (`requires-python >=3.10`).** Every patched release of `requests` (2.33.0+) and `urllib3` (2.7.0+/2.8.0+) requires Python 3.10, so on Python 3.9 the network extras could only install versions with known advisories. pip on Python 3.9 keeps resolving the previous release.
- **Security floors in the network extras:** `requests>=2.33` and `urllib3>=2.8`. These close CVE-2026-25645 (requests) and CVE-2026-44431, -44432, -97687, -97688 and -97689 (urllib3). `urllib3` is listed directly so that an environment cannot keep an older, vulnerable copy that `requests` alone would accept.

### Changed (behaviour on invalid or missing data)

- **A NaN or infinite rain rate is refused.** `WeatherObservation` raises `ValueError` for a non-finite `rain_rate_mm_h`, and for a non-finite `temperature_c` or `wind_speed_kmh` (None stays allowed). In 0.2.0 a NaN rain rate passed the sign check. At one endpoint, `calculate_exposure` silently used the other endpoint's rain, so the result looked fully measured. At both endpoints, the exposure ratio was NaN and was classified "low".
- **`MicrowaveLink`** refuses a non-finite `frequency_ghz` or `fade_margin_db`. **`calculate_exposure`** refuses non-finite, negative or inverted thresholds.
- **Open-Meteo: a missing rain value is no longer read as 0 mm/h.** `get_current` raises `ProviderResponseError` when the response has neither `rain` nor `precipitation`. `get_forecast` raises when an hour's precipitation is missing, and when the time and precipitation series do not line up. A real 0.0 reading is unchanged, and so is the existing preference for `rain`, then `precipitation` when rain is 0. Missing sections or fields, non-numeric or non-finite values, and a response that is not a JSON object also raise `ProviderResponseError` (a `ValueError`), not a `KeyError` or a NaN.
- **ECCC:** a station precipitation or radar value that is not a finite, non-negative number is treated as "no reading" (`reports_precipitation=False`, or `None` from the radar), never as a value. A station with broken coordinates is skipped instead of aborting the search. A non-object SWOB response raises `ValueError`.
- **ISED / ArcGIS:** a row with non-finite or out-of-range coordinates is reported in `skipped` like a row with none, instead of aborting `load_sites`. Non-object responses raise, and non-object features are dropped.

### Added

- `SECURITY.md`: reporting policy and the library's security boundaries, controls and tests.
- `aei_mw_exposure.providers.open_meteo.ProviderResponseError`.

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
