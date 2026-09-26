/**
 * Leaflet Digital Twin Map Visualizer
 *
 * Implements a real geographic digital twin using Leaflet.js, OpenStreetMap &
 * Satellite tile providers, anchored to real Lake Erie / Cuyahoga River coordinates.
 * Features:
 * - Real geographic water body mapping with Street & Satellite tile layers.
 * - Draggable Virtual Buoy marker synchronized with ESP32-S3 GPS anchor.
 * - Mooring radius circle indicator.
 * - Real USGS monitoring stations catalog with live/cached hydrological data popups.
 * - Real-time weather widget powered by Open-Meteo API.
 * - Coordinated two-way position synchronization with the hydrodynamic canvas map.
 */

class RealLeafletMap {
  constructor(containerId = "realLeafletMap") {
    this.containerId = containerId;
    this.map = null;
    this.buoyMarker = null;
    this.mooringCircle = null;
    this.stationLayer = null;
    this.stations = [];
    this.isDragging = false;
    this.lastSentLat = null;
    this.lastSentLon = null;
    this.throttleTimer = null;
    this.config = {
      latitude: 41.57963,
      longitude: -81.57919,
      zoom: 13,
      water_body_name: "Lake Erie (Cleveland / Euclid Nearshore)",
    };

    this.init();
  }

  async init() {
    const container = document.getElementById(this.containerId);
    if (!container) return;

    if (typeof L === "undefined") {
      console.warn("Leaflet library (L) not loaded yet.");
      return;
    }

    try {
      const res = await fetch("/api/map");
      if (res.ok) {
        const data = await res.json();
        this.config = data;
      }
    } catch (err) {
      console.warn("Using default map config, /api/map error:", err);
    }

    const centerLat = (this.config.center && this.config.center.latitude) || this.config.latitude || 41.57963;
    const centerLon = (this.config.center && this.config.center.longitude) || this.config.longitude || -81.57919;
    const zoomLevel = this.config.zoom || 13;

    // Tile Layers
    const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });

    const esriSatellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        maxZoom: 18,
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
      }
    );

    const openTopo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 17,
      attribution: 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
    });

    // Initialize Map
    this.map = L.map(this.containerId, {
      center: [centerLat, centerLon],
      zoom: zoomLevel,
      layers: [osmLayer],
      attributionControl: true,
      zoomControl: true,
    });

    // Base Layers Control
    const baseMaps = {
      "OpenStreetMap (Streets)": osmLayer,
      "Esri World Imagery (Satellite)": esriSatellite,
      "OpenTopoMap (Topography)": openTopo,
    };

    this.stationLayer = L.layerGroup().addTo(this.map);
    const overlayMaps = {
      "USGS Monitoring Stations": this.stationLayer,
    };

    L.control.layers(baseMaps, overlayMaps, { position: "topright" }).addTo(this.map);

    // Initial Buoy Position
    const buoyLat = (this.config.buoy && this.config.buoy.latitude) || centerLat;
    const buoyLon = (this.config.buoy && this.config.buoy.longitude) || centerLon;

    // Custom Buoy Icon with pulsating radar wave
    const buoyIcon = L.divIcon({
      className: "leaflet-buoy-icon-wrap",
      html: `
        <div class="buoy-radar-ping"></div>
        <div class="buoy-marker-pin">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" fill="#0284c7" stroke="#ffffff" stroke-width="2.5"/>
            <circle cx="12" cy="12" r="4.5" fill="#38bdf8"/>
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
      popupAnchor: [0, -18],
    });

    // Draggable Buoy Marker
    this.buoyMarker = L.marker([buoyLat, buoyLon], {
      icon: buoyIcon,
      draggable: true,
      autoPan: true,
      title: "Virtual Buoy (Drag to move)",
    }).addTo(this.map);

    // Mooring radius circle (15m visual footprint)
    this.mooringCircle = L.circle([buoyLat, buoyLon], {
      radius: 35, // 35m visual watch circle
      color: "#0284c7",
      fillColor: "#38bdf8",
      fillOpacity: 0.18,
      weight: 1.5,
      dashArray: "4, 4",
    }).addTo(this.map);

    this.buoyMarker.bindPopup(`
      <div class="leaflet-buoy-popup">
        <div class="popup-badge badge-sim">SIMULATION · VIRTUAL BUOY</div>
        <h4>Autonomous Solar Buoy</h4>
        <div class="popup-meta">
          <div><strong>Latitude:</strong> <span id="popup-buoy-lat">${buoyLat.toFixed(5)}°</span></div>
          <div><strong>Longitude:</strong> <span id="popup-buoy-lon">${buoyLon.toFixed(5)}°</span></div>
          <div><strong>Mooring:</strong> 15m radius watch circle</div>
          <div class="popup-note">Drag marker anywhere on Lake Erie to sample spatial water quality.</div>
        </div>
      </div>
    `);

    // Drag Events
    this.buoyMarker.on("dragstart", () => {
      this.isDragging = true;
    });

    this.buoyMarker.on("drag", (e) => {
      const pos = e.target.getLatLng();
      if (this.mooringCircle) {
        this.mooringCircle.setLatLng(pos);
      }
      this.throttleSendPosition(pos.lat, pos.lng);
      this.updateQuickCoords(pos.lat, pos.lng);
    });

    this.buoyMarker.on("dragend", (e) => {
      this.isDragging = false;
      const pos = e.target.getLatLng();
      if (this.mooringCircle) {
        this.mooringCircle.setLatLng(pos);
      }
      this.sendPositionImmediate(pos.lat, pos.lng);
    });

    // Load nearby stations & weather
    await this.loadNearbyStations();
    await this.loadWeatherWidget();
  }

  updateQuickCoords(lat, lon) {
    const el = document.getElementById("map-quick-coords");
    if (el) {
      el.innerText = `Lat: ${lat.toFixed(5)}° | Lon: ${lon.toFixed(5)}°`;
    }
    const popLat = document.getElementById("popup-buoy-lat");
    const popLon = document.getElementById("popup-buoy-lon");
    if (popLat) popLat.innerText = `${lat.toFixed(5)}°`;
    if (popLon) popLon.innerText = `${lon.toFixed(5)}°`;
  }

  throttleSendPosition(lat, lon) {
    if (this.throttleTimer) return;
    this.throttleTimer = setTimeout(() => {
      this.throttleTimer = null;
      if (
        this.lastSentLat === null ||
        Math.hypot(lat - this.lastSentLat, lon - this.lastSentLon) > 0.0001
      ) {
        this.sendPositionImmediate(lat, lon);
      }
    }, 60);
  }

  async sendPositionImmediate(lat, lon) {
    this.lastSentLat = lat;
    this.lastSentLon = lon;
    try {
      const res = await fetch("/api/buoy/position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ latitude: lat, longitude: lon }),
      });
      if (!res.ok) return;
      const data = await res.json();

      // Synchronize with canvas visualizer if present
      if (window.lakeMapVisualizer && data.buoy_x !== undefined && data.buoy_y !== undefined) {
        window.lakeMapVisualizer.targetBuoyX = data.buoy_x;
        window.lakeMapVisualizer.targetBuoyY = data.buoy_y;
        window.lakeMapVisualizer.currentLat = data.latitude;
        window.lakeMapVisualizer.currentLon = data.longitude;
        if (data.usgs_data) {
          window.lakeMapVisualizer.localUsgs = data.usgs_data;
        }
        window.lakeMapVisualizer.zoneName = data.zone_name;
        window.lakeMapVisualizer.zoneId = data.zone_id;
      }

      if (typeof pollStatus === "function") {
        pollStatus();
      }
    } catch (err) {
      console.error("Failed to sync buoy GPS position:", err);
    }
  }

  updateBuoyPosition(lat, lon) {
    if (this.isDragging || !this.buoyMarker) return;
    const current = this.buoyMarker.getLatLng();
    if (Math.hypot(current.lat - lat, current.lng - lon) > 0.00005) {
      this.buoyMarker.setLatLng([lat, lon]);
      if (this.mooringCircle) {
        this.mooringCircle.setLatLng([lat, lon]);
      }
      this.updateQuickCoords(lat, lon);
    }
  }

  async loadNearbyStations() {
    try {
      const res = await fetch("/api/stations");
      if (!res.ok) return;
      const data = await res.json();
      this.stations = data.stations || [];
      this.renderStationMarkers(this.stations);
      this.renderStationsTable(this.stations);
    } catch (err) {
      console.warn("Could not load USGS stations:", err);
    }
  }

  renderStationMarkers(stations) {
    if (!this.stationLayer) return;
    this.stationLayer.clearLayers();

    const stationIcon = L.divIcon({
      className: "leaflet-station-icon-wrap",
      html: `
        <div class="station-marker-pin">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="3" width="18" height="18" rx="4" fill="#16a34a" stroke="#ffffff" stroke-width="2"/>
            <path d="M8 12h8M12 8v8" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
        </div>
      `,
      iconSize: [26, 26],
      iconAnchor: [13, 13],
      popupAnchor: [0, -13],
    });

    stations.forEach((st) => {
      const marker = L.marker([st.latitude, st.longitude], {
        icon: stationIcon,
        title: `${st.agency} ${st.station_id}: ${st.station_name}`,
      });

      const paramsHtml = (st.parameters_available || [])
        .map((p) => `<span class="station-param-tag">${p.name} (${p.unit || "unitless"})</span>`)
        .join(" ");

      marker.bindPopup(`
        <div class="leaflet-station-popup">
          <div class="popup-badge badge-real">REAL DATA · ${st.agency} STREAMGAGE</div>
          <h4>${st.station_name}</h4>
          <div class="station-meta">
            <div><strong>Station ID:</strong> <code>${st.station_id}</code></div>
            <div><strong>Water Body:</strong> ${st.water_body || "Lake Erie Basin"}</div>
            <div><strong>Coordinates:</strong> ${st.latitude.toFixed(4)}°, ${st.longitude.toFixed(4)}°</div>
            <div><strong>Distance from Buoy:</strong> <span class="text-green font-bold">${st.distance_km.toFixed(1)} km</span></div>
            <div class="station-params-block">
              <strong>Monitored Parameters:</strong>
              <div class="params-tags-list">${paramsHtml}</div>
            </div>
            <div class="station-link-row">
              <a href="https://waterdata.usgs.gov/monitoring-location/${st.station_id}" target="_blank" rel="noopener noreferrer" class="btn-usgs-link">
                View on USGS WaterData ↗
              </a>
            </div>
          </div>
        </div>
      `);

      this.stationLayer.addLayer(marker);
    });
  }

  renderStationsTable(stations) {
    const listEl = document.getElementById("nearby-stations-list");
    if (!listEl) return;

    if (!stations.length) {
      listEl.innerHTML = `<div class="text-muted" style="padding:10px;">No USGS stations found in this region.</div>`;
      return;
    }

    listEl.innerHTML = stations
      .map(
        (st) => `
        <div class="station-card-compact" onclick="focusStationOnMap(${st.latitude}, ${st.longitude})">
          <div class="st-card-head">
            <span class="st-id-tag">USGS ${st.station_id}</span>
            <span class="st-dist-tag">${st.distance_km.toFixed(1)} km</span>
          </div>
          <div class="st-name">${st.station_name}</div>
          <div class="st-meta">${st.water_body}</div>
        </div>
      `
      )
      .join("");
  }

  async loadWeatherWidget() {
    try {
      const res = await fetch("/api/weather");
      if (!res.ok) return;
      const w = await res.json();
      this.updateWeatherDisplay(w);
    } catch (err) {
      console.warn("Could not load weather data:", err);
    }
  }

  updateWeatherDisplay(w) {
    const tempEl = document.getElementById("weather-air-temp");
    const windEl = document.getElementById("weather-wind-speed");
    const rainEl = document.getElementById("weather-precipitation");
    const solarEl = document.getElementById("weather-solar-irrad");
    const statusEl = document.getElementById("weather-status-badge");
    const noteEl = document.getElementById("weather-disclaimer-note");

    if (tempEl && w.air_temperature_c !== undefined) {
      tempEl.innerText = `${w.air_temperature_c.toFixed(1)} °C`;
    }
    if (windEl && w.wind_speed_m_s !== undefined) {
      windEl.innerText = `${w.wind_speed_m_s.toFixed(1)} m/s (${w.wind_direction_deg || 0}°)`;
    }
    if (rainEl && w.precipitation_mm !== undefined) {
      rainEl.innerText = `${w.precipitation_mm.toFixed(1)} mm`;
    }
    if (solarEl && w.solar_irradiance_w_m2 !== undefined) {
      solarEl.innerText = `${Math.round(w.solar_irradiance_w_m2)} W/m²`;
    }
    if (statusEl && w.status) {
      if (w.status === "REAL_API_DATA") {
        statusEl.className = "card-status-badge badge-real";
        statusEl.innerText = "REAL WEATHER · OPEN-METEO";
      } else if (w.status === "CACHED_DATA") {
        statusEl.className = "card-status-badge badge-cached";
        statusEl.innerText = "CACHED WEATHER · OPEN-METEO";
      } else {
        statusEl.className = "card-status-badge badge-warn";
        statusEl.innerText = "OFFLINE FALLBACK WEATHER";
      }
    }
    if (noteEl && w.disclaimer) {
      noteEl.innerText = w.disclaimer;
    }
  }

  invalidateSize() {
    if (this.map) {
      setTimeout(() => {
        this.map.invalidateSize();
      }, 100);
    }
  }
}

// Global instance handle
let realLeafletMap = null;

function initLeafletDigitalTwin() {
  if (typeof L !== "undefined" && !realLeafletMap) {
    realLeafletMap = new RealLeafletMap("realLeafletMap");
  }
}

function switchMapMode(mode) {
  const leafletWrap = document.getElementById("leafletMapWrapper");
  const canvasWrap = document.getElementById("canvasMapWrapper");
  const btnLeaflet = document.getElementById("btn-mode-leaflet");
  const btnHeatmap = document.getElementById("btn-mode-heatmap");
  const heatmapControls = document.getElementById("heatmapControlsRow");

  if (mode === "leaflet") {
    if (leafletWrap) leafletWrap.style.display = "block";
    if (canvasWrap) canvasWrap.style.display = "none";
    if (heatmapControls) heatmapControls.style.display = "none";
    if (btnLeaflet) btnLeaflet.classList.add("active");
    if (btnHeatmap) btnHeatmap.classList.remove("active");
    if (realLeafletMap) realLeafletMap.invalidateSize();
  } else {
    if (leafletWrap) leafletWrap.style.display = "none";
    if (canvasWrap) canvasWrap.style.display = "block";
    if (heatmapControls) heatmapControls.style.display = "flex";
    if (btnLeaflet) btnLeaflet.classList.remove("active");
    if (btnHeatmap) btnHeatmap.classList.add("active");
  }
}

function focusStationOnMap(lat, lon) {
  switchMapMode("leaflet");
  if (realLeafletMap && realLeafletMap.map) {
    realLeafletMap.map.setView([lat, lon], 14, { animate: true });
  }
}
