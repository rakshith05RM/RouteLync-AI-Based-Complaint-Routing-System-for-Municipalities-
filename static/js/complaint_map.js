// Single-complaint map on the officer detail page.
(function () {
  "use strict";
  const el = document.getElementById("complaint-map");
  if (!el || typeof L === "undefined") return;
  const point = [parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)];
  const colours = { CRITICAL: "#B42318", HIGH: "#EA580C", MEDIUM: "#2563EB", LOW: "#64748B" };
  const map = L.map(el).setView(point, 17);
  L.tileLayer(el.dataset.tileUrl, {
    maxZoom: 19, attribution: el.dataset.tileAttribution
  }).addTo(map);
  L.circleMarker(point, { radius: 10, color: "#ffffff", weight: 2,
    fillColor: colours[el.dataset.priority] || "#2563EB", fillOpacity: 0.95 }).addTo(map);
})();
