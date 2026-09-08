// Infrastructure Weather Map -- static, framework-free frontend for the
// aei-microwave-link-exposure Explorer's core question: where is the
// nearest available weather observation to my site? No backend: the
// example dataset is a static snapshot of the real Ontario GeoHub tower
// data (same adapter the Streamlit Explorer uses), and "Upload My Sites"
// parses the user's CSV entirely in the browser.

const map = L.map("map", {
  zoomControl: true,
  attributionControl: true,
}).setView([43.64, -79.38], 9);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const sitesLayer = L.layerGroup().addTo(map);

const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("status");

let pendingSites = null; // sites parsed from an uploaded CSV, waiting on "Analyze Sites"

function setStatus(html) {
  statusEl.hidden = false;
  statusEl.innerHTML = html;
}

function clearStatus() {
  statusEl.hidden = true;
  statusEl.innerHTML = "";
}

// A very small, forgiving CSV parser -- this project's uploaded files are
// simple (no embedded commas/quotes expected), matching the same minimal
// schema the Python "Upload My Sites" flow already uses.
function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    throw new Error("This file is empty.");
  }
  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idIdx = header.indexOf("site_id");
  const nameIdx = header.indexOf("site_name") !== -1 ? header.indexOf("site_name") : header.indexOf("name");
  const latIdx = header.indexOf("latitude");
  const lonIdx = header.indexOf("longitude");
  if (idIdx === -1 || nameIdx === -1 || latIdx === -1 || lonIdx === -1) {
    throw new Error("Missing required columns. Expected: site_id, site_name, latitude, longitude.");
  }

  const sites = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    const lat = parseFloat(cols[latIdx]);
    const lon = parseFloat(cols[lonIdx]);
    if (!cols[idIdx] || Number.isNaN(lat) || Number.isNaN(lon)) {
      continue; // skip an invalid row rather than fail the whole upload
    }
    sites.push({
      site_id: cols[idIdx].trim(),
      name: (cols[nameIdx] || cols[idIdx]).trim(),
      latitude: lat,
      longitude: lon,
    });
  }
  return sites;
}

function plotSites(sites, color) {
  sitesLayer.clearLayers();
  const markers = [];
  sites.forEach((s) => {
    const m = L.circleMarker([s.latitude, s.longitude], {
      radius: 6,
      color,
      weight: 2,
      fillColor: color,
      fillOpacity: 0.6,
    }).bindTooltip(s.name);
    m.addTo(sitesLayer);
    markers.push(m);
  });
  if (markers.length > 0) {
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.15));
  }
}

// -- Upload My Sites --------------------------------------------------

document.getElementById("btn-upload").addEventListener("click", () => {
  fileInput.value = ""; // allow re-selecting the same file
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = () => {
    try {
      const sites = parseCsv(String(reader.result));
      if (sites.length === 0) {
        setStatus('<p class="status-error">No valid site rows were found in this file.</p>');
        return;
      }
      pendingSites = sites;
      setStatus(
        `<p class="status-line">${sites.length} site${sites.length === 1 ? "" : "s"} ready</p>` +
          '<button id="btn-analyze" class="btn btn-primary">Analyze Sites</button>'
      );
      document.getElementById("btn-analyze").addEventListener("click", () => {
        plotSites(pendingSites, "#c51b7d");
        setStatus(`<p class="status-line">${pendingSites.length} site${pendingSites.length === 1 ? "" : "s"} shown on the map</p>`);
      });
    } catch (err) {
      setStatus(`<p class="status-error">${err.message}</p>`);
    }
  };
  reader.readAsText(file);
});

// -- Explore Example Sites ---------------------------------------------

document.getElementById("btn-example").addEventListener("click", async () => {
  setStatus('<p class="status-line">Loading example sites&hellip;</p>');
  try {
    const res = await fetch("example_sites.json");
    if (!res.ok) throw new Error("Could not load example sites right now.");
    const sites = await res.json();
    plotSites(sites, "#6a3d9a");
    setStatus(
      `<p class="status-line">${sites.length} example infrastructure sites shown</p>` +
        '<p class="status-error" style="color:var(--ink-soft);font-weight:400;">Real Ontario GeoHub tower locations (GTA/York Region) -- a static example snapshot, not live data.</p>'
    );
  } catch (err) {
    setStatus(`<p class="status-error">${err.message}</p>`);
  }
});
