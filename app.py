"""Microwave Weather Explorer -- Streamlit app.

Upload your own infrastructure sites to see what independent public weather
evidence exists near each one, anywhere the underlying weather/ECCC data has
coverage. Also bundles one real public-infrastructure example region
(GTA/York Region) with a small illustrative demo microwave network, for
transparent microwave engineering analysis where confirmed/demo link data
exists.

This file is a CONSUMER of the ``aei_mw_exposure`` library: it fetches real
infrastructure and weather, builds the illustrative demo network, calls
``calculate_exposure``, and renders results on a map. It contains no
attenuation formulas and does not decide what counts as REAL vs DEMO --
that classification is carried on the domain objects themselves
(``Provenance``), not invented here.

Run: streamlit run app.py
"""

from __future__ import annotations

import csv
import io
import time

import folium
import streamlit as st
from streamlit_folium import st_folium

from demo.locations import LOCATIONS, LOCATIONS_BY_NAME
from demo.network import DEMO_LINKS, DEMO_SITES
from demo.user_sites import parse_user_sites_csv
from aei_mw_exposure import LinkExposure, MicrowaveSite, Provenance, calculate_exposure, summarize
from aei_mw_exposure.infrastructure import ised as ised_infra
from aei_mw_exposure.infrastructure import ontario_geohub as geohub_infra
from aei_mw_exposure.providers import eccc
from aei_mw_exposure.providers.open_meteo import OpenMeteoProvider
from aei_mw_exposure.representativeness import assess_representativeness

st.set_page_config(page_title="Microwave Weather Explorer", layout="wide")

SEVERITY_COLOR = {"low": "#2ca25f", "moderate": "#e6b800", "high": "#d7191c"}
SEVERITY_LABEL = {"low": "Low", "moderate": "Moderate", "high": "High"}
DEMO_SITE_COLOR = "#3182bd"       # blue
GEOHUB_COLOR = "#6a3d9a"          # purple
ISED_COLOR = "#e6550d"            # orange
USER_SITE_COLOR = "#c51b7d"       # magenta -- distinct from every other marker/line colour in use
SELECTED_RING_COLOR = "#111111"   # neutral, not reused for anything else
STATION_MARKER_COLOR = "cadetblue"  # a folium.Icon palette colour -- deliberately not purple/orange/blue/severity
STATION_LINE_COLOR = "#777777"    # neutral gray -- must not read as a microwave link
MAX_REAL_MARKERS_PER_SOURCE = 300  # defensive cap, not a UX feature

WEATHER_TTL_SECONDS = 600     # matches Open-Meteo's own update cadence
INFRA_TTL_SECONDS = 1800      # public infrastructure records don't change minute to minute
REPRESENTATIVENESS_TTL_SECONDS = 300  # ECCC stations/radar update every 1-6 min; stay a polite client
_provider = OpenMeteoProvider()

# Wall-clock cache keys -- independent of any user selection, so computed
# once up front and reused by every cached fetch below.
weather_cache_key = int(time.time() // WEATHER_TTL_SECONDS)
infra_cache_key = int(time.time() // INFRA_TTL_SECONDS)
repr_cache_key = int(time.time() // REPRESENTATIVENESS_TTL_SECONDS)


@st.cache_data(ttl=INFRA_TTL_SECONDS, show_spinner="Loading real infrastructure (Ontario GeoHub)...")
def load_geohub(bbox, _cache_bust: int):
    try:
        sites, skipped, exceeded = geohub_infra.load_towers_in_bbox(bbox)
        return sites[:MAX_REAL_MARKERS_PER_SOURCE], skipped, None, exceeded
    except Exception as exc:  # live public service -- degrade, don't crash
        return [], [], str(exc), False


@st.cache_data(ttl=INFRA_TTL_SECONDS, show_spinner="Loading real infrastructure (ISED)...")
def load_ised(bbox, _cache_bust: int):
    try:
        sites, skipped, exceeded = ised_infra.load_sites_in_bbox(bbox)
        return sites[:MAX_REAL_MARKERS_PER_SOURCE], skipped, None, exceeded
    except Exception as exc:
        return [], [], str(exc), False


@st.cache_data(ttl=WEATHER_TTL_SECONDS, show_spinner="Fetching live weather for the demo network...")
def get_demo_weather(_cache_bust: int):
    return _provider.get_current_many(DEMO_SITES)


@st.cache_data(ttl=WEATHER_TTL_SECONDS, show_spinner="Fetching live weather for this area...")
def get_location_weather(location_name: str, lat: float, lon: float, _cache_bust: int):
    # A real, fixed reference coordinate (the location's center) -- not a
    # telecom site. Weather here is REAL/live; it is not per-tower weather,
    # since fetching one call per real site would be both slow and an
    # unreasonable load on a free public API for a wide-area view.
    reference_point = MicrowaveSite(
        id=f"loc-{location_name}",
        name=f"{location_name} (area reference point)",
        latitude=lat,
        longitude=lon,
        provenance=Provenance.REAL,
        source="Location center coordinate, not a telecom site",
    )
    return _provider.get_current(reference_point)


@st.cache_data(ttl=REPRESENTATIVENESS_TTL_SECONDS, show_spinner="Finding the nearest weather station (ECCC)...")
def get_nearest_station_cached(lat: float, lon: float, _cache_bust: int):
    try:
        return eccc.find_nearest_station(lat, lon), None
    except Exception as exc:  # live public service -- degrade, don't crash
        return None, str(exc)


@st.cache_data(ttl=REPRESENTATIVENESS_TTL_SECONDS, show_spinner="Reading radar precipitation (ECCC)...")
def get_radar_cached(lat: float, lon: float, _cache_bust: int):
    try:
        return eccc.get_radar_precipitation(lat, lon), None
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=WEATHER_TTL_SECONDS, show_spinner="Fetching model weather at this site...")
def get_site_model_weather_cached(site_id: str, site_name: str, lat: float, lon: float, _cache_bust: int):
    # Primitives only (not a MicrowaveSite) -- MicrowaveSite.metadata is a
    # dict, which is unhashable, and st.cache_data needs hashable args.
    probe = MicrowaveSite(id=site_id, name=site_name, latitude=lat, longitude=lon, provenance=Provenance.REAL)
    try:
        return _provider.get_current(probe), None
    except Exception as exc:
        return None, str(exc)


def _exposures_to_csv(exposures: list[LinkExposure]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "link_id", "site_a", "site_b", "length_km", "frequency_ghz", "polarization",
        "fade_margin_db", "rain_rate_mm_h_used", "source_site_id", "predicted_attenuation_db",
        "exposure_ratio", "severity", "provenance",
    ])
    for e in exposures:
        writer.writerow([
            e.link.id, e.link.site_a.name, e.link.site_b.name, f"{e.link.length_km:.2f}",
            e.link.frequency_ghz, e.link.polarization, e.link.fade_margin_db,
            e.rain_rate_mm_h, e.source_site_id, e.attenuation.predicted_attenuation_db,
            e.exposure_ratio, e.severity, e.link.provenance.value,
        ])
    return buf.getvalue()


def _sites_to_csv(sites: list[MicrowaveSite]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "name", "latitude", "longitude", "provenance", "source", "metadata"])
    for s in sites:
        writer.writerow([s.id, s.name, s.latitude, s.longitude, s.provenance.value, s.source or "", dict(s.metadata)])
    return buf.getvalue()


def _user_site_result_row(rep) -> dict:  # rep: WeatherRepresentativeness
    """One flat, human-readable row -- no internal Python objects, no
    fabricated values. A field the underlying evidence didn't supply is
    left as an explicit empty string, not zero or a guess."""
    station = rep.nearest_station
    model = rep.model_observation
    radar = rep.radar_observation
    station_precip = (
        f"{station.rain_rate_mm_h:.1f}" if station is not None and rep.station_reports_precipitation else ""
    )
    # Ordered for scanning: site identity, then the interpreted result up
    # front (what an engineer scans first), then the evidence behind it,
    # then secondary identifiers (coordinates) last.
    return {
        "Site": rep.site.name,
        "Representativeness": rep.level.replace("_", " ").title(),
        "Nearest ECCC station": station.source.split("--")[-1].strip() if station else "",
        "Station distance (km)": f"{rep.station_distance_km:.1f}" if rep.station_distance_km is not None else "",
        "Station precipitation (mm/h)": station_precip,
        "Model precipitation (mm/h)": f"{model.rain_rate_mm_h:.1f}" if model else "",
        "Radar precipitation (mm/h)": f"{radar.rain_rate_mm_h:.1f}" if radar else "",
        "Explanation": rep.note,
        "Site ID": rep.site.id,
        "Latitude": rep.site.latitude,
        "Longitude": rep.site.longitude,
    }


def _user_site_results_to_csv(results) -> str:  # results: list[WeatherRepresentativeness]
    rows = [_user_site_result_row(r) for r in results]
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return buf.getvalue()


# --- header -----------------------------------------------------------
st.title("Microwave Weather Explorer")
st.subheader("Is it the weather, or your hardware? Evidence before the truck roll.")
st.caption(
    "RSL tells you something changed. It does not, by itself, tell you why. Upload your "
    "infrastructure sites below to see what independent public weather evidence exists at each "
    "location -- a live observing station, a model reading, and radar where available -- so "
    "weather can be weighed as a plausible contributor before anyone drives out. This tool does "
    "not diagnose hardware and does not predict outages; it shows the evidence, transparently."
)

# --- my sites (bring your own) -- the primary journey ----------------------
st.header("My Sites")
st.caption(
    "Upload → Analyze → Inspect → Export. Works anywhere the underlying public weather/ECCC "
    "data has coverage -- not limited to any one region."
)
col_upload, col_example = st.columns([3, 1])
with col_upload:
    uploaded_file = st.file_uploader(
        "Upload CSV (required columns: site_id, name, latitude, longitude)",
        type=["csv"],
        key="user_sites_uploader",
    )
with col_example:
    st.write("")
    st.write("")
    try:
        with open("examples/my_sites_example.csv", "rb") as _f:
            st.download_button(
                "Download example CSV",
                data=_f.read(),
                file_name="my_sites_example.csv",
                mime="text/csv",
                help="A working example file with 4 sample sites -- try the workflow before using your own data.",
            )
    except FileNotFoundError:
        pass

user_sites: list[MicrowaveSite] = []
if uploaded_file is None:
    st.info("Upload your sites to begin -- or download the example CSV above to try the workflow first.")
if uploaded_file is not None:
    csv_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
    try:
        user_sites, user_parse_errors = parse_user_sites_csv(csv_text)
        status = f"{len(user_sites)} valid site(s) found."
        if user_parse_errors:
            status += f" {len(user_parse_errors)} row(s) need attention -- see below."
        (st.success if not user_parse_errors else st.warning)(status)
        if user_parse_errors:
            with st.expander(f"{len(user_parse_errors)} row(s) need attention"):
                for err in user_parse_errors:
                    st.write(f"- {err}")
    except ValueError as exc:
        st.error(
            f"Could not read this file: {exc} Fix the file and upload again -- no partial data "
            f"was kept from this attempt."
        )

if user_sites:
    current_ids = [s.id for s in user_sites]
    if st.button("Analyze Sites", type="primary"):
        progress = st.progress(0.0, text="Analyzing...")
        results = []
        for i, s in enumerate(user_sites):
            _station_result, _ = get_nearest_station_cached(s.latitude, s.longitude, repr_cache_key)
            _radar_obs, _ = get_radar_cached(s.latitude, s.longitude, repr_cache_key)
            _model_obs, _ = get_site_model_weather_cached(s.id, s.name, s.latitude, s.longitude, weather_cache_key)
            if _station_result is not None:
                _station_obs, _distance_km, _has_precip = _station_result
                results.append(
                    assess_representativeness(
                        site=s,
                        nearest_station=_station_obs,
                        station_distance_km=_distance_km,
                        station_reports_precipitation=_has_precip,
                        model_observation=_model_obs,
                        radar_observation=_radar_obs,
                    )
                )
            else:
                results.append(assess_representativeness(site=s, model_observation=_model_obs, radar_observation=_radar_obs))
            progress.progress((i + 1) / len(user_sites), text=f"Analyzing... {i + 1}/{len(user_sites)}")
        progress.empty()
        st.session_state["user_site_results"] = results
        st.session_state["user_site_ids"] = current_ids

    # Only trust stored results if they match the currently-uploaded site
    # list -- a different upload invalidates the previous analysis rather
    # than silently mixing results from two different files.
    if st.session_state.get("user_site_ids") == current_ids:
        user_site_results = st.session_state.get("user_site_results", [])
    else:
        user_site_results = []
else:
    user_site_results = []

if user_site_results:
    _level_counts: dict[str, int] = {}
    for _r in user_site_results:
        _level_counts[_r.level] = _level_counts.get(_r.level, 0) + 1
    _stations_found = sum(1 for _r in user_site_results if _r.nearest_station is not None)

    st.write("**Summary**")
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Sites analyzed", len(user_site_results))
    sm2.metric("Nearest station found", f"{_stations_found}/{len(user_site_results)}")
    sm3.metric(
        "Representativeness breakdown",
        ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in _level_counts.items()),
    )
    if _level_counts.get("insufficient_evidence"):
        st.caption(
            "\"Insufficient evidence\" means there wasn't enough independent weather evidence "
            "nearby to make a comparison for that site -- an honest result, not an error."
        )

    st.write(f"**Evidence Ledger** -- {len(user_site_results)} site(s):")
    st.dataframe([_user_site_result_row(r) for r in user_site_results], use_container_width=True, hide_index=True)
    st.caption(
        "Weather evidence supports or weakens weather as a plausible contributor. It does not "
        "determine hardware condition, and it is not an outage prediction."
    )
    st.download_button(
        "Download Evidence CSV",
        data=_user_site_results_to_csv(user_site_results),
        file_name="my_sites_weather_representativeness.csv",
        mime="text/csv",
    )
    st.caption(
        "Export the current analysis as a CSV evidence snapshot for engineering review or "
        "internal sharing -- reflects the moment you clicked Analyze, not live/ongoing "
        "monitoring. Empty cells mean the underlying source did not provide that value, not zero."
    )

st.divider()

# --- explore public infrastructure (secondary, example region) -------------
st.header("Explore public infrastructure")
st.caption(
    "A separate, secondary area of this Explorer: real public telecom infrastructure records "
    "and a small illustrative demo microwave network, currently available for the GTA/York "
    "Region (Canada) as an example. This does not affect the sites you uploaded above."
)

col_loc, col_refresh = st.columns([3, 1])
with col_loc:
    location_name = st.selectbox("Explore a location", [loc.name for loc in LOCATIONS])
with col_refresh:
    st.write("")
    if st.button("Refresh all data"):
        st.cache_data.clear()

location = LOCATIONS_BY_NAME[location_name]

show_ised = st.checkbox(
    "Also show real ISED cellular sites (a much denser layer -- see 'What REAL/DERIVED/DEMO/NOT AVAILABLE mean' below)",
    value=False,
)

geohub_sites, geohub_skipped, geohub_error, geohub_server_truncated = load_geohub(location.bbox, infra_cache_key)
ised_sites_all, ised_skipped, ised_error, ised_server_truncated = (
    load_ised(location.bbox, infra_cache_key) if show_ised else ([], [], None, False)
)

# ISED site density varies from a handful to several hundred per view (see
# module docstring: one row per licensed channel, deduplicated to one site
# per coordinate -- still dense in city cores). Cap what's actually drawn
# so the map stays legible; nothing here is hidden, just not all rendered.
ISED_DISPLAY_CAP = 80
if len(ised_sites_all) > ISED_DISPLAY_CAP:
    ised_sites_all = sorted(
        ised_sites_all,
        key=lambda s: (s.latitude - location.center_lat) ** 2 + (s.longitude - location.center_lon) ** 2,
    )
    ised_sites, ised_truncated = ised_sites_all[:ISED_DISPLAY_CAP], len(ised_sites_all) - ISED_DISPLAY_CAP
else:
    ised_sites, ised_truncated = ised_sites_all, 0

location_weather = get_location_weather(location.name, location.center_lat, location.center_lon, weather_cache_key)
demo_weather = get_demo_weather(weather_cache_key)

demo_exposures = [calculate_exposure(link=link, weather_by_site=demo_weather) for link in DEMO_LINKS]
demo_summary = summarize(demo_exposures)

if geohub_error:
    st.warning(f"Ontario GeoHub real-infrastructure layer unavailable right now: {geohub_error}")
elif not geohub_sites:
    st.caption(
        "No Ontario GeoHub tower records found in this bounding box. This dataset's own coverage "
        "is real but uneven across the province -- it does not claim completeness for every area."
    )
elif geohub_server_truncated:
    st.caption(
        "Ontario GeoHub's server reached its own result limit for this bounding box -- more "
        "real towers exist here than are shown. This is not this app's own display cap."
    )
if ised_error:
    st.info(
        "ISED cellular-site layer unavailable right now. This mirror is updated only twice a "
        f"year and is flagged deprecated by its host, so this can happen: {ised_error}"
    )
else:
    if ised_server_truncated:
        st.caption(
            "ISED's server reached its own 1000-row limit for this bounding box (it returns one "
            "row per licensed channel, before this app's own deduplication) -- the real cellular "
            "site count here is very likely higher than shown."
        )
    if ised_truncated:
        st.caption(
            f"Showing the {ISED_DISPLAY_CAP} ISED cellular sites nearest this location's centre "
            f"({ised_truncated} more exist in this view but aren't drawn, to keep the map legible)."
        )

s1, s2, s3, s4 = st.columns(4)
s1.metric("Real sites shown", len(geohub_sites) + len(ised_sites))
s2.metric("Live weather (area)", f"{location_weather.rain_rate_mm_h:.1f} mm/h")
s3.metric("Demo links", len(DEMO_LINKS))
s4.metric("Demo links exposed (moderate+)", demo_summary.exposed_moderate_plus)
st.caption(
    f"Weather as of {location_weather.timestamp} -- source: {location_weather.source}. "
    f"Auto-refreshes every {WEATHER_TTL_SECONDS // 60} min, or click Refresh."
)

# --- selection -------------------------------------------------------------
# Chosen here, before the map, so both the map and the panel below reflect
# the same selection in one rerun -- no separate "Analyze" step.
st.subheader("Inspect")

options: dict[str, object] = {}
# Your own uploaded sites come first -- if you have any, the one you'd
# most likely want to inspect is already the default selection below,
# instead of an unrelated public/demo entry.
for s in user_sites:
    options[f"[YOUR SITE] {s.name}"] = s
for e in demo_exposures:
    label = f"[DEMO LINK] {e.link.site_a.name} <-> {e.link.site_b.name} ({SEVERITY_LABEL[e.severity]})"
    options[label] = e
for s in geohub_sites:
    options[f"[REAL - GeoHub] {s.name}"] = s
for s in ised_sites:
    options[f"[REAL - ISED cellular] {s.name}"] = s

chosen_label = st.selectbox("Choose a site or link to inspect", list(options.keys()))
chosen = options[chosen_label]

# Weather representativeness only applies to a selected REAL site (a DEMO
# link has none). Fetched once here; both the map markers below and the
# inspector panel read the same `rep` result.
rep = None
station_has_precip = False
station_error = radar_error = model_error = None
if not isinstance(chosen, LinkExposure):
    _site = chosen
    station_result, station_error = get_nearest_station_cached(_site.latitude, _site.longitude, repr_cache_key)
    radar_obs, radar_error = get_radar_cached(_site.latitude, _site.longitude, repr_cache_key)
    model_obs, model_error = get_site_model_weather_cached(_site.id, _site.name, _site.latitude, _site.longitude, weather_cache_key)
    if station_result is not None:
        station_obs, station_distance_km, station_has_precip = station_result
        rep = assess_representativeness(
            site=_site,
            nearest_station=station_obs,
            station_distance_km=station_distance_km,
            station_reports_precipitation=station_has_precip,
            model_observation=model_obs,
            radar_observation=radar_obs,
        )

# --- map -----------------------------------------------------------------
zoom = 9 if location.half_width_deg > 0.3 else 11
m = folium.Map(location=[location.center_lat, location.center_lon], zoom_start=zoom, tiles="OpenStreetMap")

for site in geohub_sites:
    folium.CircleMarker(
        location=[site.latitude, site.longitude],
        radius=6,
        color=GEOHUB_COLOR,
        fill=True,
        fill_color=GEOHUB_COLOR,
        fill_opacity=0.75,
        weight=1,
        popup=folium.Popup(
            f"<b>{site.name}</b><br>"
            f"<b style='color:{GEOHUB_COLOR}'>REAL SITE</b> -- {site.source}<br>"
            + "".join(f"{k}: {v}<br>" for k, v in site.metadata.items()),
            max_width=280,
        ),
        tooltip=f"REAL (GeoHub): {site.name}",
    ).add_to(m)

for site in ised_sites:
    folium.CircleMarker(
        location=[site.latitude, site.longitude],
        radius=6,
        color=ISED_COLOR,
        fill=True,
        fill_color=ISED_COLOR,
        fill_opacity=0.75,
        weight=1,
        popup=folium.Popup(
            f"<b>{site.name}</b><br>"
            f"<b style='color:{ISED_COLOR}'>REAL SITE (cellular, not microwave)</b> -- {site.source}<br>"
            + "".join(f"{k}: {v}<br>" for k, v in site.metadata.items()),
            max_width=280,
        ),
        tooltip=f"REAL (ISED cellular): {site.name}",
    ).add_to(m)

for site in user_sites:
    folium.CircleMarker(
        location=[site.latitude, site.longitude],
        radius=7,
        color=USER_SITE_COLOR,
        fill=True,
        fill_color=USER_SITE_COLOR,
        fill_opacity=0.75,
        weight=1,
        popup=folium.Popup(
            f"<b>{site.name}</b><br>"
            f"<b style='color:{USER_SITE_COLOR}'>USER-PROVIDED SITE</b> -- {site.source}<br>"
            f"Not independently verified against any public record.",
            max_width=280,
        ),
        tooltip=f"Your site: {site.name}",
    ).add_to(m)

for site in DEMO_SITES:
    folium.CircleMarker(
        location=[site.latitude, site.longitude],
        radius=8,
        color=DEMO_SITE_COLOR,
        fill=True,
        fill_color=DEMO_SITE_COLOR,
        fill_opacity=0.5,
        weight=1,
        dash_array="4",
        popup=folium.Popup(f"<b>{site.name}</b><br><b>DEMO SITE</b> -- {site.source}", max_width=280),
        tooltip=f"DEMO: {site.name}",
    ).add_to(m)

for exp in demo_exposures:
    site_a, site_b = exp.link.site_a, exp.link.site_b
    color = SEVERITY_COLOR[exp.severity]
    weight = 3 if exp.severity == "low" else (5 if exp.severity == "moderate" else 7)
    popup_html = (
        f"<b>{site_a.name} <-> {site_b.name}</b><br>"
        f"<b>DEMO LINK</b> using <b>LIVE weather</b><br>"
        f"{exp.link.length_km:.1f} km, {exp.link.frequency_ghz:.0f} GHz {exp.link.polarization}, "
        f"fade margin {exp.link.fade_margin_db:.0f} dB<br>"
        f"Rain used: {exp.rain_rate_mm_h:.1f} mm/h<br>"
        f"Predicted attenuation: <b>{exp.attenuation.predicted_attenuation_db:.1f} dB</b> "
        f"({exp.exposure_ratio * 100:.0f}% of fade margin)<br>"
        f"Severity: <b style='color:{color}'>{SEVERITY_LABEL[exp.severity]}</b>"
    )
    folium.PolyLine(
        locations=[[site_a.latitude, site_a.longitude], [site_b.latitude, site_b.longitude]],
        color=color,
        weight=weight,
        opacity=0.85,
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=f"DEMO LINK: {site_a.name} <-> {site_b.name} -- {SEVERITY_LABEL[exp.severity]}",
    ).add_to(m)

# The selected site's nearest ECCC observation, and the physical distance
# between them -- drawn only when a REAL site is selected AND a station
# was actually found. Never fabricated, never drawn for a DEMO link, and
# deliberately styled to be impossible to mistake for a microwave link
# (a pin marker, not a circle; a thin gray dashed line, not a coloured
# severity line).
if rep is not None and rep.nearest_station is not None:
    _sel = chosen
    _station = rep.nearest_station
    _sel_label = "Your site" if _sel.provenance is Provenance.USER_PROVIDED else "Selected site"
    folium.CircleMarker(
        location=[_sel.latitude, _sel.longitude],
        radius=14,
        color=SELECTED_RING_COLOR,
        fill=False,
        weight=2,
        dash_array="3,4",
        tooltip=f"{_sel_label}: {_sel.name}",
    ).add_to(m)
    folium.Marker(
        location=[_station.latitude, _station.longitude],
        icon=folium.Icon(color=STATION_MARKER_COLOR, icon="tint", prefix="fa"),
        popup=folium.Popup(
            f"<b>Nearest ECCC weather station</b><br>{_station.source.split('--')[-1].strip()}<br>"
            f"{_station.timestamp}<br>{rep.station_distance_km:.1f} km from {_sel.name}",
            max_width=260,
        ),
        tooltip=f"Nearest ECCC station: {_station.source.split('--')[-1].strip()} ({rep.station_distance_km:.1f} km away)",
    ).add_to(m)
    folium.PolyLine(
        locations=[[_sel.latitude, _sel.longitude], [_station.latitude, _station.longitude]],
        color=STATION_LINE_COLOR,
        weight=2,
        opacity=0.8,
        dash_array="6,6",
        popup=folium.Popup(
            f"Distance between infrastructure and weather observation: "
            f"<b>{rep.station_distance_km:.1f} km</b><br><i>Not a microwave link.</i>",
            max_width=240,
        ),
        tooltip=f"Weather-observation distance: {rep.station_distance_km:.1f} km (not a microwave link)",
    ).add_to(m)

legend_html = f"""
<div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
     background: white; padding: 10px 14px; border-radius: 6px; border: 1px solid #ccc;
     font-size: 13px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); color: #111;">
  <b>Legend</b><br>
  <span style="color:{GEOHUB_COLOR};">&#9679;</span> REAL site -- Ontario GeoHub tower<br>
  <span style="color:{ISED_COLOR};">&#9679;</span> REAL site -- ISED cellular<br>
  <span style="color:{DEMO_SITE_COLOR};">&#9679;</span> DEMO site (synthetic)<br>
  <span style="color:{USER_SITE_COLOR};">&#9679;</span> Your site (uploaded, not independently verified)<br>
  <span style="color:{SEVERITY_COLOR['low']};">&#9644;&#9644;</span> DEMO link -- Low exposure<br>
  <span style="color:{SEVERITY_COLOR['moderate']};">&#9644;&#9644;</span> DEMO link -- Moderate<br>
  <span style="color:{SEVERITY_COLOR['high']};">&#9644;&#9644;</span> DEMO link -- High<br>
  <span style="color:{SELECTED_RING_COLOR};">&#9711;</span> Selected site<br>
  <span style="color:{STATION_LINE_COLOR};">&#128167;</span> Nearest ECCC weather station, and the distance to it (gray dashed line -- <b>not</b> a microwave link)<br>
  <span style="font-size:11px;color:#555;">No line is ever drawn between two REAL sites --<br>public data does not confirm real link topology.</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

st_folium(m, width=None, height=560, returned_objects=[])
st.caption("Click a site or link on the map for its popup detail. Select below to see its weather evidence.")

# --- inspector panel ---------------------------------------------------
# `chosen`, `rep`, and the fetch results were already computed above (before
# the map), so this panel and the map markers reflect the same selection.

if isinstance(chosen, LinkExposure):
    exp = chosen
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Observed weather** (LIVE)")
        st.write(exp.rain_rate_assumption)
        st.metric("Rain rate used", f"{exp.rain_rate_mm_h:.1f} mm/h")
    with c2:
        st.markdown("**Calculated exposure** (DERIVED)")
        st.write(f"Method: {exp.attenuation.method}")
        st.code(exp.attenuation.assumption, language=None)
        st.metric("Predicted attenuation", f"{exp.attenuation.predicted_attenuation_db:.1f} dB")
        st.metric("Fade margin (link spec)", f"{exp.link.fade_margin_db:.0f} dB")
        st.metric("Exposure ratio", f"{exp.exposure_ratio * 100:.0f}%")
    with c3:
        severity_color = {"high": "red", "moderate": "orange", "low": "green"}[exp.severity]
        st.markdown(f"**Inferred implication -- :{severity_color}[{SEVERITY_LABEL[exp.severity]}]**")
        st.write(exp.operational_note)
        st.caption("This link's geometry/frequency/fade margin are DEMO/SYNTHETIC. The weather driving this calculation is real and live.")
else:
    site: MicrowaveSite = chosen
    provenance_label = {
        "real": "REAL", "derived": "DERIVED", "demo": "DEMO",
        "not_available": "NOT AVAILABLE", "user_provided": "USER-PROVIDED",
    }[site.provenance.value]
    st.markdown(f"**{site.name}** -- provenance: **{provenance_label}**")
    st.write(f"Source: {site.source or 'unknown'}")
    st.write(f"Coordinates: {site.latitude:.5f}, {site.longitude:.5f}")
    if site.metadata:
        st.write("Published metadata:")
        st.table({k: [v] for k, v in site.metadata.items()})
    else:
        st.caption("No further published metadata for this record.")

    st.markdown("**Weather representativeness**")
    st.caption(
        "How much independent weather evidence exists near this specific site, and does it "
        "agree? Not a forecast, not a confidence score -- see 'What REAL/DERIVED/DEMO/NOT "
        "AVAILABLE mean here' below for exactly what this does and doesn't claim."
    )
    if station_error:
        st.caption(f"ECCC station lookup unavailable right now: {station_error}")
    if rep is not None:
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.caption("OBSERVED")
            st.write(f"Nearest ECCC weather station: {rep.nearest_station.source.split('--')[-1].strip()} (shown on the map above)")
            st.write(f"Station time: {rep.nearest_station.timestamp}")
            st.write(
                f"Station precipitation: {rep.nearest_station.rain_rate_mm_h:.1f} mm/h"
                if rep.station_reports_precipitation
                else "Station precipitation: not published by this station"
            )
            if rep.model_observation:
                st.write(f"Model precipitation: {rep.model_observation.rain_rate_mm_h:.1f} mm/h ({rep.model_observation.source})")
            else:
                st.write("Model precipitation: unavailable" + (f" ({model_error})" if model_error else ""))
            if rep.radar_observation:
                st.write(f"Radar rate: {rep.radar_observation.rain_rate_mm_h:.1f} mm/h (estimated, {rep.radar_observation.timestamp})")
            elif radar_error:
                st.write(f"Radar: unavailable ({radar_error})")
            else:
                st.write("Radar evidence: not available for this location/time.")
        with rc2:
            st.caption("CALCULATED")
            st.metric("Station distance", f"{rep.station_distance_km:.1f} km")
            if rep.precipitation_difference_mm_h is not None:
                st.metric("Station vs. model difference", f"{rep.precipitation_difference_mm_h:.1f} mm/h")
            else:
                st.write("Difference: not calculable (see note)")
        with rc3:
            level_color = {
                "consistent": "green",
                "moderate_disagreement": "orange",
                "high_disagreement": "red",
                "insufficient_evidence": "gray",
            }[rep.level]
            level_label = rep.level.replace("_", " ").title()
            st.caption("INTERPRETED")
            st.markdown(f":{level_color}[**{level_label}**]")
            st.write(rep.note)
            if rep.level == "insufficient_evidence":
                st.caption(
                    "This is an honest, expected result when nearby evidence is thin -- not an "
                    "error and not a low-risk result."
                )
        st.caption(
            "Weather evidence supports or weakens weather as a plausible contributor. It does "
            "not determine hardware condition, and it is not an outage prediction."
        )
    elif not station_error:
        st.info(
            "No nearby ECCC observing station was available for this location -- no station "
            "reported in the last 90 minutes within the search radius used here, so there is no "
            "independent evidence to compare. The site itself remains available above."
        )

    st.info(
        "Confirmed microwave link topology for this site: **NOT AVAILABLE**. Public data "
        "does not establish which other site (if any) this location forms a point-to-point "
        "link with, so no line is drawn and no exposure is calculated for it."
    )

# --- export -------------------------------------------------------------
st.subheader("Export")
exp_col, site_col = st.columns(2)
with exp_col:
    st.download_button(
        "Download demo link exposure (CSV)",
        data=_exposures_to_csv(demo_exposures),
        file_name="demo_link_exposure.csv",
        mime="text/csv",
    )
with site_col:
    all_real_sites = geohub_sites + ised_sites
    st.download_button(
        "Download real sites in this view (CSV)",
        data=_sites_to_csv(all_real_sites),
        file_name=f"real_sites_{location.name.replace(' ', '_').replace('/', '-')}.csv",
        mime="text/csv",
        disabled=not all_real_sites,
    )

st.divider()
with st.expander("What REAL / DERIVED / DEMO / NOT AVAILABLE mean here"):
    st.markdown(
        """
- **REAL** -- directly from a cited public source: Ontario GeoHub's Tower dataset (MNRF, Open
  Government Licence - Ontario) and/or ISED's Spectrum Licences Site Data (Government of
  Canada, Open Government Licence - Canada, via an Esri Canada mirror). Only fields the
  source actually published are shown -- a blank field means the source didn't publish it,
  not that we don't know it.
- **DERIVED** -- calculated from REAL or DEMO inputs using a stated method: link distance
  (haversine on real coordinates) and the exposure calculation itself (ITU-R P.838-3/P.530).
- **DEMO** -- the illustrative 7-site/8-link Toronto network. Realistic-looking coordinates,
  synthetic frequencies/fade margins. Never confused with real infrastructure in this UI.
- **USER-PROVIDED** -- uploaded through "My Sites" below. This is presumably real
  infrastructure, but it is *not* REAL in this app's sense: nothing here independently
  verifies an uploaded location against any public record. Never merged with, or styled to
  look like, Ontario GeoHub/ISED data.
- **NOT AVAILABLE** -- confirmed point-to-point microwave link topology between two real
  sites. No Canadian public source used here establishes this, so no line is ever drawn
  between two REAL (or USER-PROVIDED) sites, regardless of how close or well-aligned they
  look on the map.

The ISED cellular layer is real telecom infrastructure but is **cellular/mobile spectrum
site data** (e.g. Freedom Mobile base stations), not microwave-band data -- it is shown
separately from, and never merged with, the Ontario GeoHub tower layer.

The Toronto demo network's exposure calculation uses REAL, LIVE weather -- only its
network geometry (which sites, which frequencies, which fade margins) is synthetic.

**Weather representativeness** (shown when you select a REAL site) compares independent
public weather evidence near that site -- a live ECCC observing station, a model value
(Open-Meteo) at the site's own coordinates, and, when available, an ECCC radar-estimated
rate at the site's own coordinates. Station distance and any station/model difference are
calculated facts. The Low/Moderate/High-style label is a simple, stated, overridable
convention (see `representativeness.py`) -- **not** a statistical confidence score, and
**not** a forecast. Not every station publishes precipitation; when one doesn't, this is
shown explicitly rather than treated as zero rain.
        """
    )
