/**
 * Autonomous Lake Water Quality Monitoring Buoy — Dashboard Controller
 *
 * Handles:
 * - Real-time polling & UI sync (water quality, GPS, subsystems, chamber)
 * - Zone-reactive buoy position updates
 * - Flow-Through Chamber state transitions
 * - Collapsible advanced sections
 * - CSV exports
 *
 * Sections 4 (LoRa), 5 (Power), 6 (Research Experiment) have been removed.
 * Backend LoRa/power/experiment APIs remain intact for test coverage.
 */

let chamberVisualizer = null;

// Track collapsible open states
const collapsibleStates = {};

document.addEventListener("DOMContentLoaded", () => {
  // Initialize Chamber visualizer
  if (typeof ChamberVisualizer !== "undefined") {
    chamberVisualizer = new ChamberVisualizer("chamberCanvas");
  }

  // Initialize Lake Map visualizer if canvas is present
  if (typeof LakeMapVisualizer !== "undefined" && document.getElementById("lakeMapCanvas")) {
    lakeMapVisualizer = new LakeMapVisualizer("lakeMapCanvas");
  }

  // Initialize Leaflet Digital Twin Map
  if (typeof initLeafletDigitalTwin === "function") {
    initLeafletDigitalTwin();
  }

  // Start polling on each tick
  setInterval(pollAll, 500);
  pollAll();
});

// --------------------------------------------------------------------------
// Combined poll (status + power separate to avoid overloading /api/status)
// --------------------------------------------------------------------------
async function pollAll() {
  await pollStatus();
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    syncUI(data);
  } catch (err) {
    console.error("Status poll error:", err);
  }
}

// --------------------------------------------------------------------------
// Central UI Sync
// --------------------------------------------------------------------------
function syncUI(data) {
  const gt = data.ground_truth || {};
  const usgs = gt.usgs || data.usgs_data || {};
  const sensors = data.sensors || {};
  const filt = sensors.filtered || {};
  const pwr = data.power || {};
  const bat = pwr.battery || {};
  const lora = data.lora || {};

  // ---- Header Stats ----
  const simSec = data.sim_time_s || 0;
  const h = Math.floor(simSec / 3600) % 24;
  const m = Math.floor((simSec % 3600) / 60);
  const s = Math.floor(simSec % 60);
  const pad = (n) => String(n).padStart(2, "0");
  const timeStr = `${pad(h)}:${pad(m)}:${pad(s)}`;
  setText("hdr-sim-time", timeStr);

  const statusEl = document.getElementById("hdr-sim-status");
  if (statusEl) {
    statusEl.innerText = data.is_running ? "ACTIVE" : "PAUSED";
    statusEl.className = data.is_running ? "sim-stat-val text-green font-mono" : "sim-stat-val text-amber font-mono";
  }

  const ppBtn = document.getElementById("btn-play-pause");
  if (ppBtn) {
    ppBtn.innerText = data.is_running ? "❚❚ Pause" : "▶ Resume";
    ppBtn.className = data.is_running ? "btn btn-primary" : "btn btn-secondary";
  }

  if (bat.soc_pct !== undefined) {
    const socEl = document.getElementById("hdr-soc");
    if (socEl) {
      socEl.innerText = bat.soc_pct.toFixed(1) + "%";
      socEl.className = bat.soc_pct > 50 ? "sim-stat-val text-green font-mono" :
                        bat.soc_pct > 20 ? "sim-stat-val text-amber font-mono" :
                        "sim-stat-val text-red font-mono";
    }
  }

  // ---- Section 1: Authoritative Buoy Coordinates & Sensor Values ----
  const buoyState = data.buoy_state || {};
  const envVals = buoyState.environmental_values || {};
  const simZone = data.sim_zone || {};
  const wq = data.water_quality || {};

  const buoyLat = buoyState.latitude !== undefined ? buoyState.latitude :
                  (data.gps && data.gps.latitude !== undefined ? data.gps.latitude :
                  (data.location && data.location.latitude !== undefined ? data.location.latitude :
                  (data.latitude !== undefined ? data.latitude :
                  (usgs.latitude !== undefined ? usgs.latitude : 41.5830))));
  const buoyLon = buoyState.longitude !== undefined ? buoyState.longitude :
                  (data.gps && data.gps.longitude !== undefined ? data.gps.longitude :
                  (data.location && data.location.longitude !== undefined ? data.location.longitude :
                  (data.longitude !== undefined ? data.longitude :
                  (usgs.longitude !== undefined ? usgs.longitude : -81.5750))));

  const bx = gt.buoy_x !== undefined ? gt.buoy_x : (buoyState.x !== undefined ? buoyState.x : (data.buoy_x !== undefined ? data.buoy_x : data.x));
  const by = gt.buoy_y !== undefined ? gt.buoy_y : (buoyState.y !== undefined ? buoyState.y : (data.buoy_y !== undefined ? data.buoy_y : data.y));

  if (bx !== undefined && by !== undefined) {
    setText("canvas-quick-coords", `X: ${Math.round(bx)}m | Y: ${Math.round(by)}m`);
  }
  if (buoyLat !== undefined && buoyLon !== undefined) {
    setText("map-quick-coords", `Lat: ${buoyLat.toFixed(5)}° | Lon: ${buoyLon.toFixed(5)}°`);
    if (window.realLeafletMap) {
      window.realLeafletMap.updateBuoyPosition(buoyLat, buoyLon);
    }
  }

  // Authoritative Sensor Values: Priority Zone Engine (Simulated Water Quality) -> Filtered
  const phVal = wq.ph !== undefined ? wq.ph :
                (data.ph !== undefined ? data.ph :
                (usgs.ph !== undefined ? usgs.ph :
                (envVals.ph !== undefined ? envVals.ph : filt.ph)));
  const ecVal = wq.ec_us_cm !== undefined ? wq.ec_us_cm :
                (data.ec_us_cm !== undefined ? data.ec_us_cm :
                (usgs.ec_us_cm !== undefined ? usgs.ec_us_cm :
                (envVals.ec_us_cm !== undefined ? envVals.ec_us_cm : filt.ec_us_cm)));
  const turbVal = wq.turbidity_ntu !== undefined ? wq.turbidity_ntu :
                  (data.turbidity_ntu !== undefined ? data.turbidity_ntu :
                  (usgs.turbidity_ntu !== undefined ? usgs.turbidity_ntu :
                  (envVals.turbidity_ntu !== undefined ? envVals.turbidity_ntu : filt.turbidity_ntu)));
  const tempVal = wq.water_temp_c !== undefined ? wq.water_temp_c :
                  (data.water_temp_c !== undefined ? data.water_temp_c :
                  (usgs.water_temp_c !== undefined ? usgs.water_temp_c :
                  (envVals.water_temp_c !== undefined ? envVals.water_temp_c : filt.temp_c)));

  // ---- Simulation Zone Display & Highlighting ----
  const zoneName = simZone.name || data.zone_name || (simZone.zone_id ? simZone.zone_id.replace(/_/g, " ").toUpperCase() : "SIMULATION REGION");
  const zoneDesc = simZone.description || "Simulated regional water dynamics";
  const zoneId = simZone.zone_id || data.zone_id;

  setText("active-zone-name", zoneName);
  setText("active-zone-desc", zoneDesc);
  setText("telemetry-zone-tag", zoneName.replace(" — SIMULATION ZONE", ""));

  if (simZone.color) {
    const nameEl = document.getElementById("active-zone-name");
    if (nameEl) nameEl.style.color = simZone.color;
  }

  if (window.realLeafletMap && zoneId) {
    window.realLeafletMap.highlightZone(zoneId);
  }

  // ---- Buoy Position Panel (right of map) ----
  if (buoyLat !== undefined) setText("pos-lat", `${buoyLat.toFixed(5)}° N`);
  if (buoyLon !== undefined) setText("pos-lon", `${Math.abs(buoyLon).toFixed(5)}° W`);
  if (simZone.zone_id) setText("pos-timestamp", `Sim Zone: ${simZone.zone_id.replace(/_/g, " ").toUpperCase()}`);
  else if (buoyState.timestamp !== undefined) setText("pos-timestamp", `Sim: ${buoyState.timestamp.toFixed(1)}s`);
  else if (usgs.nearest_record_timestamp) setText("pos-timestamp", usgs.nearest_record_timestamp);

  if (phVal !== undefined) setText("pos-ph", Number(phVal).toFixed(2));
  if (ecVal !== undefined) setText("pos-ec", Number(ecVal).toFixed(1));
  if (turbVal !== undefined) setText("pos-turb", Number(turbVal).toFixed(2));
  if (tempVal !== undefined) setText("pos-temp", Number(tempVal).toFixed(2));

  // ---- Section 2: Water Quality Cards ----
  if (phVal !== undefined) setText("disp-ph", Number(phVal).toFixed(2));
  if (ecVal !== undefined) setText("disp-ec", Number(ecVal).toFixed(1));
  if (turbVal !== undefined) setText("disp-turb", Number(turbVal).toFixed(2));
  if (tempVal !== undefined) setText("disp-temp", Number(tempVal).toFixed(2));

  // ---- Source Observations (collapsible KNN-IDW detail) ----
  try {
    updateSourceObservations(data);
  } catch (obsErr) {
    console.warn("Source observations sync warning:", obsErr);
  }

  // Percentile badges
  const pcts = data.percentiles || {};
  updatePercentileBadges(pcts, turbVal);

  // ---- Section 2: Subsystem Status ----
  updateSubsystemStatus(data);

  // ---- Section 3: Chamber ----
  if (chamberVisualizer && data.chamber) {
    chamberVisualizer.updateState(data.chamber);
    const ch = data.chamber;
    setText("ch-state-text", ch.current_state);
    setText("ch-phase-time", `${ch.time_in_state_s}s / ${ch.state_duration_s}s`);
    setText("ch-fluid-level", `${ch.fluid_level_pct}%`);

    const pmEl = document.getElementById("ch-pump-motor");
    if (pmEl) {
      pmEl.innerText = ch.pump_active ? "RUNNING (ACTIVE)" : "OFF (STANDBY)";
      pmEl.className = ch.pump_active ? "diag-val text-blue font-bold font-mono" : "diag-val text-muted font-mono";
    }

    const sqEl = document.getElementById("ch-stabilized");
    if (sqEl) {
      sqEl.innerText = ch.fluid_stabilized ? "QUIESCENT (STABILIZED)" : "AGITATED (FLOWING)";
      sqEl.className = ch.fluid_stabilized ? "diag-val text-green font-bold font-mono" : "diag-val text-amber font-mono";
    }

    // Stepper nodes
    ["LAKE_MONITORING", "CHAMBER_FILL", "STABILIZE", "MEASURE", "FLUSH"].forEach((st) => {
      const el = document.getElementById(`step-${st}`);
      if (el) el.className = st === ch.current_state ? "cycle-step-node active" : "cycle-step-node";
    });

    // Chamber current values
    if (phVal !== undefined) setText("ch-val-ph", phVal.toFixed(2));
    if (ecVal !== undefined) setText("ch-val-ec", ecVal.toFixed(1));
    if (turbVal !== undefined) setText("ch-val-turb", turbVal.toFixed(2));
    if (tempVal !== undefined) setText("ch-val-temp", tempVal.toFixed(2));

    // Subsystem chamber badge
    setText("subsys-chamber", ch.current_state.replace(/_/g, " "));
    const chStatus = document.getElementById("subsys-chamber-status");
    if (chStatus) {
      chStatus.innerText = ch.pump_active ? "● PUMP ACTIVE" : (ch.current_state === "MEASURE" ? "● MEASURING" : "● ACTIVE");
      chStatus.className = ch.current_state === "MEASURE" ? "subsys-status status-ok" : "subsys-status status-ok";
    }
  }

}

// --------------------------------------------------------------------------
// Subsystem Status Update
// --------------------------------------------------------------------------
function updateSubsystemStatus(data) {
  const gt = data.ground_truth || {};
  const usgs = gt.usgs || {};
  const pwr = data.power || {};
  const bat = pwr.battery || {};
  const lora = data.lora || {};
  const gpsData = data.gps || {};

  // GPS
  const bState = data.buoy_state || {};
  const latDisplay = bState.latitude !== undefined ? bState.latitude : (gpsData.latitude !== undefined ? gpsData.latitude : usgs.latitude);
  const lonDisplay = bState.longitude !== undefined ? bState.longitude : (gpsData.longitude !== undefined ? gpsData.longitude : usgs.longitude);
  if (latDisplay !== undefined && lonDisplay !== undefined) {
    setText("subsys-gps", `${latDisplay.toFixed(4)}°N, ${Math.abs(lonDisplay).toFixed(4)}°W`);
  }
  const gpsStatus = document.getElementById("subsys-gps-status");
  const gpsFault = data.watchdog && data.watchdog.faults && data.watchdog.faults.includes("GPS_LOST");
  if (gpsStatus) {
    gpsStatus.innerText = gpsFault ? "● LOST" : "● LOCKED";
    gpsStatus.className = gpsFault ? "subsys-status status-err" : "subsys-status status-ok";
  }

  // IMU (MPU6050)
  const imuData = data.mpu6050 || {};
  if (imuData.roll_deg !== undefined) {
    setText("subsys-imu", `Roll: ${imuData.roll_deg.toFixed(1)}° | Pitch: ${imuData.pitch_deg !== undefined ? imuData.pitch_deg.toFixed(1) : "0.0"}°`);
  }
  const imuStatus = document.getElementById("subsys-imu-status");
  if (imuStatus) {
    const motion = imuData.motion_detected;
    imuStatus.innerText = motion ? "● MOTION DETECTED" : "● STABLE";
    imuStatus.className = motion ? "subsys-status status-warn" : "subsys-status status-ok";
  }

  // Battery
  if (bat.soc_pct !== undefined) {
    setText("subsys-soc", `${bat.soc_pct.toFixed(1)}%`);
    const socSt = document.getElementById("subsys-soc-status");
    if (socSt) {
      const soc = bat.soc_pct;
      socSt.innerText = soc > 50 ? "● NORMAL" : soc > 20 ? "● LOW" : "● CRITICAL";
      socSt.className = soc > 50 ? "subsys-status status-ok" : soc > 20 ? "subsys-status status-warn" : "subsys-status status-err";
    }
  }

  // Solar
  if (pwr.solar_power_mw !== undefined) {
    setText("subsys-solar", `${pwr.solar_power_mw.toFixed(0)} mW`);
    const solSt = document.getElementById("subsys-solar-status");
    if (solSt) {
      solSt.innerText = pwr.solar_power_mw > 10 ? "● HARVESTING" : "● STANDBY";
      solSt.className = pwr.solar_power_mw > 10 ? "subsys-status status-ok" : "subsys-status status-warn";
    }
  }

  // LoRa status
  if (lora.last_tx) {
    const seq = lora.last_tx.seq_num || 0;
    setText("subsys-lora", `PKT #${String(seq).padStart(5, "0")}`);
    const loraSt = document.getElementById("subsys-lora-status");
    if (loraSt) {
      loraSt.innerText = lora.last_tx.acked ? "● ACK RECEIVED" : "● TRANSMITTED";
      loraSt.className = lora.last_tx.acked ? "subsys-status status-ok" : "subsys-status status-warn";
    }
  }
}

// (Section 4 LoRa, Section 5 Power, Section 6 Experiment functions removed — sections not present in dashboard)
// --------------------------------------------------------------------------
// Source Observations (KNN-IDW K=3 Inspection)
// --------------------------------------------------------------------------
function updateSourceObservations(data) {
  const usgs = data.ground_truth ? data.ground_truth.usgs : data.usgs_data;
  const contributors = (usgs && usgs.contributors && usgs.contributors.length > 0)
    ? usgs.contributors
    : (data.contributors || []);

  if (contributors.length >= 3) {
    for (let i = 0; i < 3; i++) {
      const p = contributors[i];
      const pNum = i + 1;
      setText(`sp${pNum}-dist`, `Dist: ${p.distance_m} m`);
      setText(`sp${pNum}-coords`, `${p.latitude.toFixed(4)}°, ${p.longitude.toFixed(4)}°`);
      setText(`sp${pNum}-turb`, `${p.turbidity_ntu.toFixed(2)} NTU`);
      setText(`sp${pNum}-ec`, `${p.ec_us_cm.toFixed(1)} µS/cm`);
      setText(`sp${pNum}-phtemp`, `pH ${p.ph.toFixed(2)} | ${p.water_temp_c.toFixed(1)}°C`);
      setText(`sp${pNum}-weight`, `${p.weight_pct}%`);
    }
  }

  // Derived values summary box
  if (usgs) {
    if (usgs.turbidity_ntu !== undefined) setText("derived-turb", `${usgs.turbidity_ntu.toFixed(2)} NTU`);
    if (usgs.ec_us_cm !== undefined) setText("derived-ec", `${usgs.ec_us_cm.toFixed(1)} µS/cm`);
    if (usgs.ph !== undefined) setText("derived-ph", usgs.ph.toFixed(2));
    if (usgs.water_temp_c !== undefined) setText("derived-temp", `${usgs.water_temp_c.toFixed(2)} °C`);
  }
}

// --------------------------------------------------------------------------
// Percentile Badges
// --------------------------------------------------------------------------
function updatePercentileBadges(pcts, turbVal) {
  const phPctEl = document.getElementById("disp-ph-pct");
  if (phPctEl && pcts.ph !== undefined) phPctEl.innerText = `${pcts.ph}th pct`;

  const ecPctEl = document.getElementById("disp-ec-pct");
  if (ecPctEl && pcts.ec_us_cm !== undefined) ecPctEl.innerText = `${pcts.ec_us_cm}th pct`;

  const turbPct = pcts.turbidity_ntu !== undefined ? pcts.turbidity_ntu : 50;
  const turbPctEl = document.getElementById("disp-turb-pct");
  let statusText = "TYPICAL";
  let badgeClass = "stat-percentile-tag pct-normal";
  if (turbPct >= 90) { statusText = "HIGH"; badgeClass = "stat-percentile-tag pct-high"; }
  else if (turbPct <= 10) { statusText = "LOW"; badgeClass = "stat-percentile-tag pct-low"; }
  if (turbPctEl) { turbPctEl.innerText = `${turbPct}th pct`; turbPctEl.className = badgeClass; }

  const tempPctEl = document.getElementById("disp-temp-pct");
  if (tempPctEl && pcts.water_temp_c !== undefined) tempPctEl.innerText = `${pcts.water_temp_c}th pct`;
}
// LoRa section removed from dashboard HTML — function stub only
function updateLoraSection(data) { /* no-op: section removed */ }

// --------------------------------------------------------------------------
// Collapsible Sections
// --------------------------------------------------------------------------
function toggleCollapsible(sectionId) {
  const el = document.getElementById(sectionId);
  const chevron = document.getElementById(`chevron-${sectionId}`);
  if (!el) return;

  const isVisible = el.style.display !== "none";
  el.style.display = isVisible ? "none" : "block";
  collapsibleStates[sectionId] = !isVisible;

  if (chevron) {
    chevron.textContent = isVisible ? "▼" : "▲";
  }
}
// --------------------------------------------------------------------------
// No-op stubs for removed sections (backend APIs remain intact)
// --------------------------------------------------------------------------
async function sendLoraCommand(cmd, arg = 0) { /* no-op: LoRa section removed */ }
async function runComparativeExperiment() { /* no-op: Experiment section removed */ }
async function controlReplay(action) { /* no-op: Replay section removed */ }
async function onReplaySlider(val) { /* no-op: Replay section removed */ }
function switchGraphParam(param) { /* no-op: Chart section removed */ }

function exportComparisonCsv() { window.location.href = "/api/export/comparison.csv"; }
function exportTelemetryCsv() { window.location.href = "/api/export/telemetry.csv"; }

// --------------------------------------------------------------------------
// Play / Pause / Step / Speed Controls
// --------------------------------------------------------------------------
async function togglePlayPause() {
  const btn = document.getElementById("btn-play-pause");
  const isPause = btn.innerText.includes("Pause");
  await fetch(isPause ? "/api/control/pause" : "/api/control/play", { method: "POST" });
  pollStatus();
}

async function stepSim(dt) {
  await fetch("/api/control/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dt_s: dt }),
  });
  pollStatus();
}

async function setSpeed(val) {
  await fetch("/api/control/speed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speed: parseFloat(val) }),
  });
}

// --------------------------------------------------------------------------
// Utility: Safe innerHTML setter (handles HTML in pm-val etc.)
// --------------------------------------------------------------------------
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = value;
}
