// "Nearby Weather Evidence" -- shown when a site marker is clicked.
//
// Two ECCC sources, both real, public, queried live and directly from the
// browser (both endpoints send Access-Control-Allow-Origin: *, confirmed
// live before writing this):
//
// - SWOB-Realtime (OGC API Features) for the 2-3 nearest reporting
//   stations -- same collection/fields the Python library's
//   find_nearest_station() already queries (src/aei_mw_exposure/providers/
//   eccc.py), just extended here to keep the top N instead of only 1, and
//   to also read air_temp / avg_wnd_spd_10m_pst1hr alongside the
//   precipitation field it already reads.
// - MSC GeoMet WMS GetFeatureInfo, the exact point-query pattern the
//   Python library already uses for RADAR_1KM_RRAI, reused here for two
//   different layers found live in GetCapabilities:
//     - HRDPA_2.5km_Precip-Accum6h -- a real analysis product (blends
//       gauge + radar + model for a period that already happened).
//     - HRDPS-WEonG_2.5km_AirTemp / HRDPS-WEonG_2.5km_WindSpeed -- these
//       are NWP MODEL output (a short-lead forecast, not an analysis of
//       what already happened), despite living in the same UI row --
//       labelled separately in the source note for exactly that reason.
//
// No custom interpolation or estimation between stations is done anywhere
// here -- every number shown is a value one of these two services
// returned directly for a queried point/bbox.

const SWOB_URL = "https://api.weather.gc.ca/collections/swob-realtime/items";
const GEOMET_WMS_URL = "https://geo.weather.gc.ca/geomet";
const KM_PER_DEGREE_LAT = 111.32; // same approximation as geometry.haversine_km's docstring notes at this scale

// Plain reimplementation of aei_mw_exposure.geometry.haversine_km -- a
// public geometric formula, not engineering logic specific to this
// project, so reproducing it in JS for a browser-only context isn't a
// change to the Python library.
function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371.0;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// -- SWOB-Realtime: nearest N stations, same query shape as
// find_nearest_station() (bbox + datetime window), extended to keep the
// top N by distance instead of only the closest one.
async function findNearestStations(lat, lon, count = 3, searchRadiusKm = 50, windowMinutes = 90) {
  const deg = searchRadiusKm / KM_PER_DEGREE_LAT;
  const bbox = `${lon - deg},${lat - deg},${lon + deg},${lat + deg}`;
  const now = new Date();
  const start = new Date(now.getTime() - windowMinutes * 60000).toISOString().replace(/\.\d+Z$/, "Z");
  const end = now.toISOString().replace(/\.\d+Z$/, "Z");

  const url = `${SWOB_URL}?bbox=${encodeURIComponent(bbox)}&datetime=${encodeURIComponent(`${start}/${end}`)}&limit=300&f=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Could not reach ECCC station data right now.");
  const data = await res.json();

  const latestByStation = new Map();
  for (const feature of data.features || []) {
    const props = feature.properties || {};
    const name = props["stn_nam-value"];
    const ts = props["date_tm-value"];
    if (!name || !ts) continue;
    const existing = latestByStation.get(name);
    if (!existing || ts > existing.properties["date_tm-value"]) {
      latestByStation.set(name, feature);
    }
  }

  const withDistance = [];
  for (const [name, feature] of latestByStation) {
    const [stationLon, stationLat] = feature.geometry.coordinates;
    const distanceKm = haversineKm(lat, lon, stationLat, stationLon);
    if (distanceKm > searchRadiusKm) continue;
    const props = feature.properties;
    withDistance.push({
      name,
      distanceKm,
      timestamp: props["date_tm-value"],
      temperatureC: props["air_temp"] ?? null,
      precipitationMm: props["pcpn_amt_pst1hr"] ?? null, // null means "not reported", not zero
      windKmh: props["avg_wnd_spd_10m_pst1hr"] ?? null,
    });
  }
  withDistance.sort((a, b) => a.distanceKm - b.distanceKm);
  return withDistance.slice(0, count);
}

// -- MSC GeoMet WMS GetFeatureInfo: one gridded-analysis point value per
// layer, same mechanism as get_radar_precipitation() in eccc.py.
async function getFeatureInfoValue(layer, lat, lon) {
  const halfDeg = 0.02; // small box around the point, consistent with the radar query's ~5 km box
  const bbox = `${lon - halfDeg},${lat - halfDeg},${lon + halfDeg},${lat + halfDeg}`;
  const params = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: "1.3.0",
    REQUEST: "GetFeatureInfo",
    LAYERS: layer,
    QUERY_LAYERS: layer,
    CRS: "CRS:84",
    BBOX: bbox,
    WIDTH: "101",
    HEIGHT: "101",
    I: "50",
    J: "50",
    INFO_FORMAT: "application/json",
    FEATURE_COUNT: "1",
  });
  try {
    const res = await fetch(`${GEOMET_WMS_URL}?${params.toString()}`);
    if (!res.ok) return null;
    const data = await res.json();
    const feature = (data.features || [])[0];
    if (!feature || feature.properties?.value === undefined || feature.properties?.value === null) return null;
    return { value: Number(feature.properties.value), time: feature.properties.time || null };
  } catch (e) {
    return null;
  }
}

async function getGriddedAnalysis(lat, lon) {
  const [precip, temp, wind] = await Promise.all([
    getFeatureInfoValue("HRDPA_2.5km_Precip-Accum6h", lat, lon),
    getFeatureInfoValue("HRDPS-WEonG_2.5km_AirTemp", lat, lon),
    getFeatureInfoValue("HRDPS-WEonG_2.5km_WindSpeed", lat, lon),
  ]);
  return {
    precipitationMm: precip ? precip.value : null,
    temperatureC: temp ? temp.value : null,
    // HRDPS reports wind speed in m/s; converted to km/h to match the
    // station table's units, nothing else changed about the value.
    windKmh: wind ? wind.value * 3.6 : null,
    anyData: !!(precip || temp || wind),
  };
}

// -- Agree/disagree heuristic ------------------------------------------
//
// THIS IS A STARTING HEURISTIC, NOT A VALIDATED SCIENTIFIC THRESHOLD.
// Precipitation reuses the exact 2.0 mm/h figure already used elsewhere in
// this project as DEFAULT_DISAGREEMENT_THRESHOLD_MM_H (representativeness.py),
// for consistency. The 3.0 degC temperature figure is newly proposed here,
// picked as a simple round number, not derived from any study or standard
// -- flagged as such in the UI text itself, not just this comment.
const TEMP_DISAGREEMENT_THRESHOLD_C = 3.0;
const PRECIP_DISAGREEMENT_THRESHOLD_MM = 2.0;

function assessAgreement(stations) {
  const temps = stations.map((s) => s.temperatureC).filter((v) => v !== null && v !== undefined);
  const precips = stations.map((s) => s.precipitationMm).filter((v) => v !== null && v !== undefined);

  const tempRange = temps.length >= 2 ? Math.max(...temps) - Math.min(...temps) : null;
  const precipRange = precips.length >= 2 ? Math.max(...precips) - Math.min(...precips) : null;

  const disagrees =
    (tempRange !== null && tempRange > TEMP_DISAGREEMENT_THRESHOLD_C) ||
    (precipRange !== null && precipRange > PRECIP_DISAGREEMENT_THRESHOLD_MM);

  if (tempRange === null && precipRange === null) {
    return { label: null, reason: null };
  }
  return disagrees
    ? { label: "Nearby observations disagree -- local conditions may vary.", disagrees: true }
    : { label: "Nearby observations agree.", disagrees: false };
}

// -- Rendering -----------------------------------------------------------

function fmt(value, unit, digits = 1) {
  return value === null || value === undefined ? "&mdash;" : `${value.toFixed(digits)} ${unit}`;
}

function renderEvidenceHtml(siteName, stations, gridded) {
  if (stations.length === 0 && !gridded.anyData) {
    return `<strong>${siteName}</strong><p class="evidence-note">No nearby weather evidence was available for this location just now.</p>`;
  }

  const rows = stations
    .map(
      (s) => `<tr>
        <td>${s.name}</td>
        <td>${s.distanceKm.toFixed(1)} km</td>
        <td>${fmt(s.temperatureC, "&deg;C")}</td>
        <td>${fmt(s.precipitationMm, "mm")}</td>
        <td>${fmt(s.windKmh, "km/h")}</td>
      </tr>`
    )
    .join("");

  const griddedRow = gridded.anyData
    ? `<tr>
        <td>Gridded analysis (Environment Canada)</td>
        <td>&mdash;</td>
        <td>${fmt(gridded.temperatureC, "&deg;C")}</td>
        <td>${fmt(gridded.precipitationMm, "mm")}</td>
        <td>${fmt(gridded.windKmh, "km/h")}</td>
      </tr>`
    : "";

  const agreement = assessAgreement(stations);
  const agreementHtml = agreement.label
    ? `<p class="evidence-flag${agreement.disagrees ? " evidence-flag-disagree" : ""}">${agreement.label}</p>`
    : "";

  return `
    <strong>${siteName}</strong>
    <table class="evidence-table">
      <thead><tr><th>Station</th><th>Distance</th><th>Temp</th><th>Precip</th><th>Wind</th></tr></thead>
      <tbody>${rows}${griddedRow}</tbody>
    </table>
    ${agreementHtml}
    <p class="evidence-note">source: ECCC SWOB-Realtime (stations); ECCC HRDPA (gridded precip, an analysis); ECCC HRDPS (gridded temp/wind, short-range model output, not an analysis)</p>
    <p class="evidence-note">Nearest observation does not necessarily mean fully representative of site conditions.</p>
  `;
}

// Attach the "click a marker -> show nearby weather evidence" behaviour to
// a Leaflet marker for one site. Exported for app.js to call from
// plotSites().
function attachWeatherEvidence(marker, site) {
  marker.bindPopup("Loading nearby weather evidence&hellip;", { maxWidth: 320 });
  marker.on("popupopen", async () => {
    marker.setPopupContent("Loading nearby weather evidence&hellip;");
    try {
      const [stations, gridded] = await Promise.all([
        findNearestStations(site.latitude, site.longitude, 3),
        getGriddedAnalysis(site.latitude, site.longitude),
      ]);
      marker.setPopupContent(renderEvidenceHtml(site.name, stations, gridded));
    } catch (err) {
      marker.setPopupContent(`<strong>${site.name}</strong><p class="evidence-note">Could not load weather evidence right now.</p>`);
    }
  });
}
