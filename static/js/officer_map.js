// Complaint map for officers. Popup text is built with DOM methods (textContent), never innerHTML,
// because complaint titles are written by citizens.
(function () {
  "use strict";
  const el = document.getElementById("map");
  const dataEl = document.getElementById("map-data");
  if (!el || !dataEl || typeof L === "undefined") return;

  const complaints = JSON.parse(dataEl.textContent);
  const colours = { CRITICAL: "#B42318", HIGH: "#EA580C", MEDIUM: "#2563EB", LOW: "#64748B" };
  const map = L.map(el);
  L.tileLayer(el.dataset.tileUrl, {
    maxZoom: 19, attribution: el.dataset.tileAttribution
  }).addTo(map);

  function line(parent, text, cls) {
    const p = document.createElement("div");
    if (cls) p.className = cls;
    p.textContent = text;
    parent.appendChild(p);
  }
  function popup(c) {
    const box = document.createElement("div");
    const head = document.createElement("strong");
    head.textContent = c.ref;
    box.appendChild(head);
    line(box, c.title);
    line(box, c.address, "small text-secondary");
    const areaWard = [c.area, c.ward ? "Ward " + c.ward : ""].filter(Boolean).join(", ");
    if (areaWard) line(box, areaWard, "small text-secondary");
    line(box, c.priority_label + " priority \u00b7 " + c.status, "small");
    const link = document.createElement("a");
    link.href = c.url; link.textContent = "Open complaint";
    box.appendChild(link);
    return box;
  }

  const group = L.featureGroup();
  complaints.forEach(function (c) {
    L.circleMarker([c.lat, c.lng], {
      radius: 9, color: "#ffffff", weight: 2, fillColor: colours[c.priority] || "#2563EB", fillOpacity: 0.95
    }).bindPopup(popup(c)).addTo(group);
  });
  group.addTo(map);

  if (complaints.length) { map.fitBounds(group.getBounds().pad(0.2), { maxZoom: 17 }); }
  else { map.setView([20.5937, 78.9629], 5); }
})();
