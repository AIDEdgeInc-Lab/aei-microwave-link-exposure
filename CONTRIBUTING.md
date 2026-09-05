# Contributing

This is intentionally a small library. Most contributions fit in one
module — you shouldn't need to read the whole project to change one part
of it.

## Where things live

| You want to... | Edit... | Depends on |
|---|---|---|
| Add/change a weather source (a new API, a CSV loader, a test fixture) | `src/aei_mw_exposure/providers/` (new file, implementing `WeatherProvider` from `weather.py`) | `weather.py`'s `WeatherObservation` / `WeatherProvider` only |
| Change what a weather observation carries | `src/aei_mw_exposure/weather.py` | Nothing upstream; `exposure.py` and every provider read this |
| Change the microwave site/link model | `src/aei_mw_exposure/microwave.py` | `geometry.py` for distance |
| Change or extend the physics (e.g. a different ITU recommendation, gaseous/fog attenuation) | `src/aei_mw_exposure/physics.py` | Nothing — pure functions, no domain types |
| Change how exposure/severity is derived from an attenuation estimate | `src/aei_mw_exposure/exposure.py` | `physics.py`, `microwave.py`, `weather.py` |
| Add/change a real public infrastructure source (a new government dataset) | `src/aei_mw_exposure/infrastructure/` (new file: a `parse_*` function + a `fetch_*` function, see `ontario_geohub.py`/`ised.py`) | `microwave.py`'s `MicrowaveSite`, `provenance.py` |
| Add/change how provenance is tracked or labeled | `src/aei_mw_exposure/provenance.py` | Read by `microwave.py` |
| Change how weather evidence is compared/interpreted for a site | `src/aei_mw_exposure/representativeness.py` | `weather.py`'s `WeatherObservation`; populated by `providers/eccc.py` |
| Change "Bring your own sites" CSV parsing/validation | `demo/user_sites.py` (stdlib `csv` only, no pandas, no Streamlit import) | `MicrowaveSite`, `Provenance.USER_PROVIDED` |
| Change the demo network, the location list, or the Explorer app | `demo/network.py`, `demo/locations.py`, `demo/user_sites.py`, `app.py` | The public API only (`aei_mw_exposure`) — never edit calculation logic here |

The dependency direction is one-way: `geometry -> microwave`, `physics`
(standalone) `-> exposure -> app`; `provenance -> microwave -> infrastructure`.
Nothing in `aei_mw_exposure` imports from `app.py` or `demo/`.

**Before adding a new infrastructure source**, read the non-negotiable rule
in `src/aei_mw_exposure/infrastructure/__init__.py`: adapters produce
`MicrowaveSite` objects only, never `MicrowaveLink`. No Canadian public
source found so far establishes which real site links to which — do not
add code that infers one from proximity, azimuth, frequency, or any
combination of these, no matter how confident the match looks.

## Ground rules

- **The core package (`aei_mw_exposure`) never imports Streamlit, Folium, or
  any UI library.** If your change needs one of those, it belongs in
  `app.py`, not in `src/`.
- **No hidden calculations.** If you add a computed value, expose the
  inputs and method that produced it (see `AttenuationEstimate` for the
  pattern) — don't return a bare label like "High" without the numbers
  behind it.
- **State simplifications, don't hide them.** If a formula reuses a
  design-rule approximation for something it wasn't originally meant for
  (as the current P.530 effective-path factor does), say so in a
  docstring or the result's `assumption` field.
- **Don't claim more than the data supports.** Never label synthetic or
  demo data as if it were real, and never call an exposure estimate an
  "outage" — this library has no outage data to validate that claim.
- **Keep dependencies out of the core.** New third-party packages belong
  behind an optional extra (see `pyproject.toml`) unless they're needed by
  every single user of the library.

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

Tests should be deterministic and offline — no live network calls in
`tests/`. If you're testing a provider, feed it a canned response rather
than hitting the real API.

## Running the Explorer locally

```bash
pip install -e ".[explorer,open-meteo,infrastructure]"
streamlit run app.py
```

## Style

Type hints and a one-line docstring for anything non-obvious. No large
docstring blocks, no unused imports, no dead code — this project stays
readable by staying small.
