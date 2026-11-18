// Location search, map pin and GPS for the complaint form.
//  * typing searches real places through RouteLync's own endpoint (/geo/search/), never a third-party URL from the browser
//  * choosing a result, tapping the map, dragging the pin or using GPS all go through setPoint(), so the pin, the
//    coordinates, the address and the signed token always describe the SAME place
//  * all text from the service is inserted with textContent (never as HTML)
(function () {
  "use strict";
  const root = document.getElementById("location-picker");
  if (!root || typeof L === "undefined") return;
  const $ = (id) => document.getElementById(id);
  const input = $("location-search"), list = $("location-results"), status = $("location-status"), chosen = $("location-chosen");
  const lat = $("id_latitude"), lon = $("id_longitude"), token = $("id_location_token"), source = $("id_location_source");
  const addr = $("id_address_text"), street = $("id_street"), landmark = $("id_landmark"), area = $("id_area");
  const useBtn = $("use-location"), clearBtn = $("clear-location"), gpsStatus = $("gps-status");
  const form = $("complaint-form");
  const bbox = (root.dataset.bbox || "").split(",").map(Number);
  const hasBox = bbox.length === 4 && bbox.every(Number.isFinite);
  let serviceAreaStatus = "unknown";

  function say(text, kind) {
    status.textContent = text;
    status.className = "form-text " + (kind === "error" ? "text-danger" : kind === "ok" ? "text-success" : "");
  }

  // ------------------------------------------------------------------ map
  const map = L.map("location-map", { scrollWheelZoom: true });
  L.tileLayer(root.dataset.tileUrl, {
    maxZoom: 19, attribution: root.dataset.tileAttribution
  }).addTo(map);
  requestAnimationFrame(function () { map.invalidateSize(); });
  let marker = null;
  let lastGood = null;
  let ignoreMapUntil = 0;         // a tap on a search result must not "fall through" to the map underneath once the list closes

  function currentPoint() {
    const a = parseFloat(lat.value), b = parseFloat(lon.value);
    return Number.isFinite(a) && Number.isFinite(b) ? { lat: a, lng: b } : null;
  }
  const start = currentPoint();
  if (start) { map.setView([start.lat, start.lng], 17); } else if (hasBox) { map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]]); } else { map.setView([20.59, 78.96], 5); }

  function ensureMarker(point) {
    if (!marker) {
      marker = L.marker([point.lat, point.lng], { draggable: true, keyboard: true, title: "Drag to adjust the location" }).addTo(map);
      marker.on("dragend", function () { const p = marker.getLatLng(); movedByUser({ lat: p.lat, lng: p.lng }, "MAP"); });
    } else { marker.setLatLng([point.lat, point.lng]); }
  }
  if (start) { ensureMarker(start); lastGood = start; }

  // One function sets the pin, the coordinates and the token together, so they cannot disagree.
  function setPoint(point, from, result, zoom) {
    ensureMarker(point);
    lat.value = point.lat.toFixed(6); lon.value = point.lng.toFixed(6);
    source.value = from;
    token.value = result && result.token ? result.token : "";
    serviceAreaStatus = result && result.service_area_status ? result.service_area_status : "unknown";
    lastGood = { lat: point.lat, lng: point.lng };
    if (zoom) map.setView([point.lat, point.lng], Math.max(map.getZoom(), zoom));
    const label = result && result.label ? result.label : "";
    chosen.textContent = "Selected location: " + (label ? label + " " : "") + "(" + lat.value + ", " + lon.value + ")";
    lat.setAttribute("aria-invalid", "false");
  }

  function fillFromResult(r) {
    function put(field, value) {                          // never overwrite something the citizen typed themselves
      if (!field || !value) return;
      if (!field.value || field.dataset.auto === "1") { field.value = value; field.dataset.auto = "1"; }
    }
    put(addr, r.label); put(street, r.street); put(landmark, r.name);
    if (area) {
      const normalize = (value) => (value || "").toLowerCase().replace(/bangalore/g, "bengaluru").replace(/\s+district$/, "").trim();
      const hints = [r.area_hint, r.district].filter(Boolean).map(normalize);
      for (const option of Array.from(area.options)) {
        const name = normalize(option.dataset.areaName || option.text);
        if (option.value && hints.some((h) => h === name)) {
          if (area.value !== option.value) { area.value = option.value; area.dispatchEvent(new Event("change", { bubbles: true })); }
          break;
        }
      }
    }
  }
  [addr, street, landmark].forEach(function (f) { if (f) f.addEventListener("input", function () { f.dataset.auto = "0"; }); });

  // ------------------------------------------------------------------ reverse lookup
  let reverseController = null;
  async function reverse(point, from) {
    if (reverseController) reverseController.abort();
    reverseController = new AbortController();
    say("Finding the address...");
    try {
      const response = await fetch(root.dataset.reverseUrl + "?lat=" + point.lat.toFixed(6) + "&lng=" + point.lng.toFixed(6),
        { signal: reverseController.signal, headers: { "Accept": "application/json" }, credentials: "same-origin" });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        token.value = ""; serviceAreaStatus = "unknown";
        say(data.error || "Could not verify this location. The map pin is kept; please search for the full place name.", "error");
        return;
      }
      setPoint(point, from, data.result);
      fillFromResult(data.result);
      if (data.result.service_area_status === "available") {
        if (!input.value.trim() || from !== "SEARCH") input.value = data.result.label;
        say("Address filled in from the pin. Check it and correct anything that is wrong.", "ok");
      } else if (data.result.service_area_status === "unavailable") {
        say("Sorry, RouteLync currently serves only Bengaluru Urban and Bengaluru Rural. The map pin is kept.", "error");
      } else {
        say("The location is on the map, but its district could not be verified. Search for a place in Bengaluru Urban or Bengaluru Rural.", "error");
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        token.value = ""; serviceAreaStatus = "unknown";
        say("The address service is unavailable. The map pin is kept; search for the place again in a moment.", "error");
      }
    }
  }
  function movedByUser(point, from) { setPoint(point, from, null); reverse(point, from); }
  map.on("click", function (e) {
    if (Date.now() < ignoreMapUntil) return;
    movedByUser({ lat: e.latlng.lat, lng: e.latlng.lng }, "MAP");
  });

  function clearPoint() {
    if (marker) { map.removeLayer(marker); marker = null; }
    lat.value = ""; lon.value = ""; token.value = ""; source.value = ""; lastGood = null; serviceAreaStatus = "unknown"; chosen.textContent = "";
  }

  // ------------------------------------------------------------------ search with a dropdown
  let results = [], active = -1, timer = null, searchController = null;
  function closeList() { list.hidden = true; list.textContent = ""; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; }
  function highlight(i) {
    active = i;
    Array.from(list.children).forEach(function (li, idx) { li.classList.toggle("active", idx === i); li.setAttribute("aria-selected", idx === i ? "true" : "false"); });
    if (i >= 0) input.setAttribute("aria-activedescendant", "loc-opt-" + i); else input.removeAttribute("aria-activedescendant");
  }
  function note(text) {
    list.textContent = "";
    const li = document.createElement("li"); li.className = "list-group-item small text-secondary"; li.textContent = text; li.setAttribute("role", "presentation");
    list.appendChild(li); list.hidden = false; input.setAttribute("aria-expanded", "true");
  }
  function render(items) {
    list.textContent = ""; results = items; active = -1;
    items.forEach(function (r, i) {
      const li = document.createElement("li");
      li.id = "loc-opt-" + i; li.className = "list-group-item list-group-item-action"; li.setAttribute("role", "option"); li.setAttribute("aria-selected", "false");
      const main = document.createElement("div"); main.className = "fw-semibold"; main.textContent = r.name || r.street || r.city || r.label;
      const sub = document.createElement("div"); sub.className = "small text-secondary"; sub.textContent = r.label;
      li.appendChild(main); li.appendChild(sub);
      li.addEventListener("pointerdown", function (e) { e.preventDefault(); choose(i); });       // mouse and touch, before blur closes the list
      list.appendChild(li);
    });
    list.hidden = false; input.setAttribute("aria-expanded", "true");
  }
  function choose(i) {
    const r = results[i]; if (!r) return;
    ignoreMapUntil = Date.now() + 700;
    setPoint({ lat: r.lat, lng: r.lng }, "SEARCH", r, 17);
    fillFromResult(r);
    input.value = r.label; closeList();
    if (r.service_area_status === "available") {
      say("Location selected. Check the pin and the address below.", "ok");
    } else if (r.service_area_status === "unavailable") {
      say("Sorry, RouteLync currently serves only Bengaluru Urban and Bengaluru Rural. The map pin is kept.", "error");
    } else {
      say("The map pin is selected, but the district could not be verified.", "error");
    }
  }
  async function search(q) {
    if (searchController) searchController.abort();
    searchController = new AbortController();
    note("Searching...");
    try {
      const response = await fetch(root.dataset.searchUrl + "?q=" + encodeURIComponent(q), { signal: searchController.signal, headers: { "Accept": "application/json" }, credentials: "same-origin" });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) { note(data.error || "Search failed. You can still tap the map."); return; }
      if (!data.results.length) { note("No places found. Try a different spelling, or tap the map."); return; }
      render(data.results);
    } catch (err) {
      if (err.name !== "AbortError") note("Location search is unavailable. You can still tap the map to place the pin.");
    }
  }
  input.addEventListener("input", function () {
    if (token.value) {
      token.value = "";
      serviceAreaStatus = "unknown";
      chosen.textContent = "The search changed. The previous pin stays visible; choose a result to update it.";
    }
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { closeList(); return; }
    timer = setTimeout(function () { search(q); }, 350);                    // wait for a pause in typing
  });
  input.addEventListener("keydown", function (e) {
    const open = !list.hidden && results.length;
    if (e.key === "ArrowDown" && open) { e.preventDefault(); highlight((active + 1) % results.length); }
    else if (e.key === "ArrowUp" && open) { e.preventDefault(); highlight((active - 1 + results.length) % results.length); }
    else if (e.key === "Enter") { if (open && results.length) { e.preventDefault(); choose(active >= 0 ? active : 0); } else { e.preventDefault(); } }
    else if (e.key === "Escape") { closeList(); }
  });
  input.addEventListener("blur", function () { setTimeout(closeList, 150); });

  // ------------------------------------------------------------------ GPS (only when the person presses the button)
  if (useBtn) {
    useBtn.addEventListener("click", function () {
      if (!window.isSecureContext) {
        gpsStatus.textContent = "Location access requires HTTPS or localhost. Open this site securely, or search for the place and choose it on the map.";
        gpsStatus.className = "small text-danger";
        return;
      }
      if (!("geolocation" in navigator)) { gpsStatus.textContent = "This browser cannot share location. Search for the place or tap the map instead."; gpsStatus.className = "small text-danger"; return; }
      useBtn.disabled = true; gpsStatus.textContent = "Getting your location..."; gpsStatus.className = "small";
      navigator.geolocation.getCurrentPosition(function (pos) {
        useBtn.disabled = false;
        const point = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        gpsStatus.textContent = "Location found (accuracy about " + Math.round(pos.coords.accuracy) + " m). Check the pin.";
        gpsStatus.className = "small text-success";
        if (clearBtn) clearBtn.hidden = false;
        setPoint(point, "GPS", null, 17);
        reverse(point, "GPS");
      }, function (err) {
        useBtn.disabled = false;
        const reasons = {
          1: "Location permission was denied. Allow it in browser site settings and Windows Location privacy settings, then try again.",
          2: "This laptop could not determine a location. Turn on Windows Location services and Wi-Fi, or search for the place and choose it on the map.",
          3: "Getting your location took too long. Check Windows Location services and Wi-Fi, then retry or search for the place."
        };
        gpsStatus.textContent = reasons[err.code] || "Could not get your location."; gpsStatus.className = "small text-danger";
      }, { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 });
    });
  }
  if (clearBtn) clearBtn.addEventListener("click", function () { clearPoint(); clearBtn.hidden = true; say("Location cleared. Search, tap the map, or use your current location."); });

  if (start && !token.value) reverse(start, "MAP");

  // ------------------------------------------------------------------ do not submit without a location
  if (form) form.addEventListener("submit", function (e) {
    if (!currentPoint() || !token.value || serviceAreaStatus !== "available") {
      e.preventDefault();
      if (serviceAreaStatus === "unavailable") {
        say("Sorry, RouteLync currently serves only Bengaluru Urban and Bengaluru Rural.", "error");
      } else if (serviceAreaStatus === "unknown") {
        say("Please wait for the location to be verified in Bengaluru Urban or Bengaluru Rural.", "error");
      } else {
        say("Please choose a place from search, tap the map, or use your current location and wait for verification.", "error");
      }
      lat.setAttribute("aria-invalid", "true");
      root.scrollIntoView({ behavior: "smooth", block: "center" });
      input.focus();
    }
  });
})();
