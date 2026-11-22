# Security Policy

## Supported versions

This project is published on PyPI (https://pypi.org/project/aei-microwave-link-exposure/).
Only the latest published version and the latest commit on `main` are
supported.

| Version | Supported |
|---|---|
| 0.3.x | Yes, best-effort |
| < 0.3.0 | No |

## Reporting a vulnerability

**Please do not open a public GitHub issue for a suspected security
vulnerability.**

Report vulnerabilities privately using GitHub's private vulnerability
reporting (Security tab -> "Report a vulnerability") on the repository,
which opens a private advisory visible only to maintainers. If that
channel is unavailable, contact the maintainers through a private channel
and avoid including exploit details in any public forum.

Please include:
- A description of the vulnerability and its potential impact
- Steps to reproduce, or a minimal proof of concept
- The affected version(s)

## What to expect

- We will acknowledge receipt as soon as reasonably possible.
- We do not commit to a specific response-time or fix-time service level
  agreement (SLA). This is a small, community-maintained-scale project,
  not a commercially supported product.
- We will credit reporters who wish to be credited, once a fix is
  released.

## Scope

## Scope

The core (`exposure`, `physics`, `geometry`, `microwave`, `weather`, `provenance`, `representativeness`) is pure standard-library
Python: no network, no files, no environment variables, no code run from inputs. The network adapters are optional extras. Each
control below is covered by tests; the test file is named.

| Boundary | Control | Where | Tests |
|---|---|---|---|
| Network: Open-Meteo, ECCC SWOB-Realtime and radar WMS, ArcGIS (Ontario GeoHub, ISED mirror); all HTTPS and keyless | Fixed HTTPS endpoints; a timeout on every request; `requests` only in the optional extras | `providers/`, `infrastructure/` | `test_provider_eccc.py`, `test_infrastructure_*.py` |
| Remote responses | A response that is not a JSON object is refused; Open-Meteo fields that are missing, non-numeric or non-finite raise `ProviderResponseError` (a `ValueError`); a missing rain value is never read as 0 mm/h; hourly series that do not line up are refused; ECCC station or radar values that are not finite non-negative numbers count as "no reading"; stations and ISED rows with invalid coordinates are skipped and reported, not fatal | `providers/open_meteo.py`, `providers/eccc.py`, `infrastructure/ised.py`, `infrastructure/_arcgis.py` | `test_security_baseline.py` |
| Domain values | `WeatherObservation` rain rate must be finite and non-negative (temperature and wind finite or None); `MicrowaveLink` frequency and fade margin finite and positive; `MicrowaveSite` coordinates in range; exposure thresholds finite, non-negative and ordered | `weather.py`, `microwave.py`, `exposure.py` | `test_weather.py`, `test_microwave.py`, `test_security_baseline.py` |
| Truncated result sets | ArcGIS `exceededTransferLimit` is returned to the caller, never hidden | `infrastructure/_arcgis.py` | `test_infrastructure_arcgis.py` |

Dependencies: the network extras require `requests>=2.33` and `urllib3>=2.8` (security floors; Python >=3.10).

Privacy: the network adapters send the queried coordinates (or bounding box) to the public service they call. The core never makes
a request; a caller can supply its own `WeatherProvider` that reads local data instead.

Not in scope: the Streamlit demo (`app.py`) and the static `web/` demo are not part of the PyPI package. Open-Meteo's free tier is
for non-commercial use only; commercial use needs the caller's own subscription.
