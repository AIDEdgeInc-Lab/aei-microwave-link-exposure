// Checkpoint build: first screen only (title, subtitle, map, primary/secondary
// actions). Site data, upload flow, and results are intentionally not wired
// up yet -- see CHECKPOINT note in the task this was built from.

const map = L.map("map", {
  zoomControl: true,
  attributionControl: true,
}).setView([43.64, -79.38], 9);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

document.getElementById("btn-upload").addEventListener("click", () => {
  // Wired up in the next build phase.
});

document.getElementById("btn-example").addEventListener("click", () => {
  // Wired up in the next build phase.
});
