/**
 * Autonomous Lake Water Quality Monitoring Buoy — Dashboard Controller
 * 
 * Handles:
 * - Real-time polling & UI sync (water quality, GPS, subsystems, chamber, LoRa, power)
 * - Interactive 2D Lake Map & KNN-IDW Source Observation inspection
 * - Historical USGS Data Replay
 * - Flow-Through Chamber state transitions
 * - ADS1115 signal processing path (advanced collapsible)
 * - LoRa communication protocol simulation
 * - Power subsystem compact panel
 * - Research comparative experiment with configurable parameters
 * - Collapsible advanced sections
 * - CSV exports
 */

let chamberVisualizer = null;
let timeSeriesChart = null;
let activeGraphParam = "turbidity_ntu";
let lastLoggedSeqNum = 0;
let isReplayActive = false;
let currentReplayIdx = 0;

// Track collapsible open states
const collapsibleStates = {};

document.addEventListener("DOMContentLoaded", () => {
  // Initialize Chamber visualizer
  if (typeof ChamberVisualizer !== "undefined") {
    chamberVisualizer = new ChamberVisualizer("chamberCanvas");
  }

  // Initialize Lake Map visualizer
  if (typeof LakeMapVisualizer !== "undefined") {
    lakeMapVisualizer = new LakeMapVisualizer("lakeMapCanvas");
  }

  // Initialize time-series chart (even if collapsed)
  initTimeSeriesChart();

  // Load initial historical time-series data
  loadTimeSeriesData("turbidity_ntu");

  // Start polling – status + power on each tick
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

  // ---- Section 1: Map Quick Coords ----
  if (gt.buoy_x !== undefined && gt.buoy_y !== undefined) {
    setText("map-quick-coords", `X: ${Math.round(gt.buoy_x)}m | Y: ${Math.round(gt.buoy_y)}m`);
  }

  // ---- Source Observations (collapsible KNN-IDW detail) ----
  updateSourceObservations(data);

  // ---- Buoy Position Panel (right of map) ----
  const phVal  = usgs.ph !== undefined ? usgs.ph : filt.ph;
  const ecVal  = usgs.ec_us_cm !== undefined ? usgs.ec_us_cm : filt.ec_us_cm;
  const turbVal = usgs.turbidity_ntu !== undefined ? usgs.turbidity_ntu : filt.turbidity_ntu;
  const tempVal = usgs.water_temp_c !== undefined ? usgs.water_temp_c : filt.temp_c;

  if (usgs.latitude !== undefined) setText("pos-lat", `${usgs.latitude.toFixed(5)}° N`);
  if (usgs.longitude !== undefined) setText("pos-lon", `${usgs.longitude.toFixed(5)}° W`);
  if (usgs.nearest_record_timestamp) setText("pos-timestamp", usgs.nearest_record_timestamp);
  if (phVal !== undefined) setText("pos-ph", phVal.toFixed(2));
  if (ecVal !== undefined) setText("pos-ec", ecVal.toFixed(1));
  if (turbVal !== undefined) setText("pos-turb", turbVal.toFixed(2));
  if (tempVal !== undefined) setText("pos-temp", tempVal.toFixed(2));

  // ---- Section 2: Water Quality Cards ----
  if (phVal !== undefined) setText("disp-ph", phVal.toFixed(2));
  if (ecVal !== undefined) setText("disp-ec", ecVal.toFixed(1));
  if (turbVal !== undefined) setText("disp-turb", turbVal.toFixed(2));
  if (tempVal !== undefined) setText("disp-temp", tempVal.toFixed(2));

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

  // ---- Section 4: LoRa ----
  updateLoraSection(data);

  // ---- Section 5: Power Panel ----
  updatePowerPanel(pwr, bat);

  // ---- Advanced: Signal Path ----
  if (phVal !== undefined) setText("sig-ph-val", phVal.toFixed(2));
  if (turbVal !== undefined) setText("sig-turb-val", `${turbVal.toFixed(2)} NTU`);
  if (ecVal !== undefined) setText("sig-ec-val", `${ecVal.toFixed(1)} µS/cm`);
  if (tempVal !== undefined) setText("sig-temp-val", `${tempVal.toFixed(2)} °C`);

  // ---- Replay ----
  if (data.replay) {
    isReplayActive = data.replay.active;
    currentReplayIdx = data.replay.index;
    const rBadge = document.getElementById("replay-status-badge");
    if (rBadge) {
      rBadge.innerText = isReplayActive ? "REPLAY PLAYING" : "REPLAY PAUSED";
      rBadge.className = isReplayActive ? "card-status-badge badge-sim" : "card-status-badge badge-usgs";
    }
    const rSlider = document.getElementById("replay-slider");
    if (rSlider && !document.activeElement.isSameNode(rSlider)) rSlider.value = currentReplayIdx;
    const rDisp = document.getElementById("replay-index-display");
    if (rDisp) rDisp.innerText = `Obs #${String(currentReplayIdx).padStart(5, "0")} / ${(data.replay.total_records || 0).toLocaleString()}`;
    const rTime = document.getElementById("replay-timestamp-disp");
    if (rTime && usgs.nearest_record_timestamp) rTime.innerText = usgs.nearest_record_timestamp;
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
  if (usgs.latitude !== undefined && usgs.longitude !== undefined) {
    setText("subsys-gps", `${usgs.latitude.toFixed(4)}°N, ${usgs.longitude.toFixed(4)}°W`);
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

// --------------------------------------------------------------------------
// Power Panel Update (Section 5)
// --------------------------------------------------------------------------
function updatePowerPanel(pwr, bat) {
  if (!pwr || Object.keys(pwr).length === 0) return;

  const solar = pwr.solar_power_mw !== undefined ? pwr.solar_power_mw : 0;
  const irr   = pwr.solar_irradiance_w_m2 !== undefined ? pwr.solar_irradiance_w_m2 : 0;
  const soc   = bat.soc_pct !== undefined ? bat.soc_pct : 0;
  const volt  = bat.voltage_v !== undefined ? bat.voltage_v : 0;
  const load  = pwr.load_power_mw !== undefined ? pwr.load_power_mw : 0;
  const net   = pwr.net_power_mw !== undefined ? pwr.net_power_mw : 0;
  const mode  = pwr.power_mode || "ACTIVE";
  const cycleE = pwr.chamber_cycle_energy_mwh !== undefined ? pwr.chamber_cycle_energy_mwh : 0;
  const endD  = pwr.estimated_endurance_days !== undefined ? pwr.estimated_endurance_days : 0;
  const endH  = pwr.estimated_endurance_hours !== undefined ? pwr.estimated_endurance_hours : 0;
  const harv  = pwr.total_harvested_wh !== undefined ? pwr.total_harvested_wh : 0;
  const cons  = pwr.total_consumed_wh !== undefined ? pwr.total_consumed_wh : 0;

  setText("pw-solar", `${solar.toFixed(0)} <span class="pm-unit">mW</span>`);
  setText("pw-irradiance", `Irradiance: ${irr.toFixed(1)} W/m²`);
  setText("pw-soc", `${soc.toFixed(1)} <span class="pm-unit">%</span>`);
  setText("pw-voltage", `Voltage: ${volt.toFixed(3)} V`);
  setText("pw-load", `${load.toFixed(0)} <span class="pm-unit">mW</span>`);
  const netSign = net >= 0 ? "+" : "";
  setText("pw-net", `Net: ${netSign}${net.toFixed(0)} mW`);
  setText("pw-mode", mode.replace(/_/g, " "));
  setText("pw-cycle-energy", `Cycle energy: ${cycleE.toFixed(2)} mWh`);
  setText("pw-endurance", `${endD.toFixed(1)} <span class="pm-unit">days</span>`);
  setText("pw-endurance-hrs", `${endH.toFixed(0)} hours (no solar)`);
  setText("pw-harvested", `${harv.toFixed(3)} <span class="pm-unit">Wh</span>`);
  setText("pw-consumed", `Consumed: ${cons.toFixed(3)} Wh`);

  // Color-code load
  const loadEl = document.getElementById("pw-load");
  if (loadEl) {
    if (load > 300) loadEl.className = "pm-val text-red";
    else if (load > 150) loadEl.className = "pm-val text-amber";
    else loadEl.className = "pm-val";
  }
}

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

// --------------------------------------------------------------------------
// LoRa Section Update
// --------------------------------------------------------------------------
function updateLoraSection(data) {
  const lora = data.lora || {};
  const lastTx = lora.last_tx;
  const exchangeLog = data.lora_exchange || [];

  // Ticker
  if (lastTx) {
    const stepTx = document.getElementById("lora-step-tx");
    const stepRx = document.getElementById("lora-step-rx");
    const stepDec = document.getElementById("lora-step-dec");
    const stepAck = document.getElementById("lora-step-ack");
    if (stepTx) stepTx.className = "comm-step-badge active";
    setTimeout(() => { if (stepRx) stepRx.className = "comm-step-badge active"; }, 150);
    setTimeout(() => { if (stepDec) stepDec.className = "comm-step-badge active"; }, 300);
    setTimeout(() => { if (stepAck) stepAck.className = "comm-step-badge active"; }, 450);
    setTimeout(() => {
      [stepTx, stepRx, stepDec, stepAck].forEach(el => { if (el) el.className = "comm-step-badge"; });
    }, 1800);
  }

  // Current packet
  if (lastTx && lastTx.packet_dict) {
    const pt = lastTx.packet_dict.plaintext || {};
    setText("pkt-seq", `#${String(lastTx.seq_num).padStart(5, "0")}`);
    if (pt.latitude !== undefined) setText("pkt-lat", `${pt.latitude.toFixed(5)}° N`);
    if (pt.longitude !== undefined) setText("pkt-lon", `${pt.longitude.toFixed(5)}° W`);
    if (pt.ph !== undefined) setText("pkt-ph", pt.ph.toFixed(2));
    if (pt.ec_us_cm !== undefined) setText("pkt-ec", `${pt.ec_us_cm.toFixed(1)} µS/cm`);
    if (pt.turbidity_ntu !== undefined) setText("pkt-turb", `${pt.turbidity_ntu.toFixed(2)} NTU`);
    if (pt.temp_c !== undefined) setText("pkt-temp", `${pt.temp_c.toFixed(2)} °C`);

    const usgs = data.ground_truth ? data.ground_truth.usgs : null;
    const tsEl = document.getElementById("pkt-timestamp");
    if (tsEl) tsEl.innerText = (usgs && usgs.nearest_record_timestamp) ? usgs.nearest_record_timestamp : "--";

    const statEl = document.getElementById("pkt-status");
    if (statEl) {
      statEl.innerText = lastTx.acked ? "ACK_RECEIVED_BY_BUOY" : "TRANSMITTED";
      statEl.className = lastTx.acked ? "val text-green font-bold" : "val text-blue font-bold";
    }

    // LoRa subsystem badge
    setText("subsys-lora", `PKT #${String(lastTx.seq_num).padStart(5, "0")}`);
  }

  // Gateway packet history table
  if (exchangeLog.length > 0) {
    const tbody = document.getElementById("lora-packet-history-body");
    if (tbody) {
      tbody.innerHTML = "";
      const reversed = [...exchangeLog].reverse();
      reversed.forEach((entry) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="font-mono font-bold text-blue">${entry.event || `#${entry.seq_num}`}</td>
          <td class="font-mono">${entry.time_str || "--"}</td>
          <td class="font-mono">${entry.usgs_timestamp || "--"}</td>
          <td>${typeof entry.ph === "number" ? entry.ph.toFixed(2) : entry.ph}</td>
          <td>${typeof entry.ec === "number" ? entry.ec.toFixed(1) : entry.ec}</td>
          <td>${typeof entry.turb === "number" ? entry.turb.toFixed(2) : entry.turb}</td>
          <td>${typeof entry.temp === "number" ? entry.temp.toFixed(1) : entry.temp}</td>
          <td>${typeof entry.lat === "number" ? entry.lat.toFixed(5) + "° N" : entry.lat}</td>
          <td>${typeof entry.lon === "number" ? entry.lon.toFixed(5) + "° W" : entry.lon}</td>
          <td><span class="text-green font-bold">✔ ${entry.ack_str || "ACK"}</span></td>
        `;
        tbody.appendChild(tr);
      });
    }
  }
}

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

  // Reload chart if replay section just opened
  if (!isVisible && sectionId === "adv-replay" && timeSeriesChart) {
    loadTimeSeriesData(activeGraphParam);
  }
}

// --------------------------------------------------------------------------
// USGS Time-Series Chart
// --------------------------------------------------------------------------
function initTimeSeriesChart() {
  const canvas = document.getElementById("usgsTimeSeriesChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  timeSeriesChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Turbidity (NTU)",
        data: [],
        borderColor: "#0284c7",
        backgroundColor: "rgba(2, 132, 199, 0.08)",
        fill: true,
        tension: 0.25,
        pointRadius: 2,
        pointBackgroundColor: "#0284c7",
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { grid: { color: "#f1f5f9" }, ticks: { color: "#64748b", maxTicksLimit: 12, font: { size: 10, family: "JetBrains Mono" } } },
        y: { grid: { color: "#f1f5f9" }, ticks: { color: "#334155", font: { size: 11, family: "JetBrains Mono" } } },
      },
      plugins: {
        legend: { labels: { color: "#0f172a", font: { weight: 600 } } },
        tooltip: { backgroundColor: "#0f172a", titleFont: { family: "JetBrains Mono" }, bodyFont: { family: "JetBrains Mono" } },
      },
    },
  });
}

async function loadTimeSeriesData(param) {
  try {
    const res = await fetch(`/api/usgs/timeseries?param=${param}&count=60`);
    if (!res.ok) return;
    const points = await res.json();
    if (!points || !points.length || !timeSeriesChart) return;

    const labels = points.map((p) => p.timestamp ? p.timestamp.slice(11, 19) : `#${p.index}`);
    const dataVals = points.map((p) => p.value);

    const meta = {
      turbidity_ntu: { label: "Turbidity (NTU)", color: "#d97706", bg: "rgba(217, 119, 6, 0.08)" },
      ec_us_cm: { label: "Conductivity (EC µS/cm)", color: "#0d9488", bg: "rgba(13, 148, 136, 0.08)" },
      ph: { label: "Water pH", color: "#8b5cf6", bg: "rgba(139, 92, 246, 0.08)" },
      water_temp_c: { label: "Water Temperature (°C)", color: "#ea580c", bg: "rgba(234, 88, 12, 0.08)" },
    }[param] || { label: param, color: "#0284c7", bg: "rgba(2, 132, 199, 0.08)" };

    timeSeriesChart.data.labels = labels;
    timeSeriesChart.data.datasets[0].label = meta.label;
    timeSeriesChart.data.datasets[0].data = dataVals;
    timeSeriesChart.data.datasets[0].borderColor = meta.color;
    timeSeriesChart.data.datasets[0].backgroundColor = meta.bg;
    timeSeriesChart.data.datasets[0].pointBackgroundColor = meta.color;
    timeSeriesChart.update();
  } catch (err) {
    console.error("Time-series fetch failed:", err);
  }
}

function switchGraphParam(param) {
  activeGraphParam = param;
  const tabs = {
    turbidity_ntu: "tab-graph-turb",
    ec_us_cm: "tab-graph-ec",
    ph: "tab-graph-ph",
    water_temp_c: "tab-graph-temp",
  };
  Object.keys(tabs).forEach((k) => {
    const el = document.getElementById(tabs[k]);
    if (el) el.classList.toggle("active", k === param);
  });
  loadTimeSeriesData(param);
}

// --------------------------------------------------------------------------
// Historical Replay Controls
// --------------------------------------------------------------------------
async function controlReplay(action) {
  try {
    const res = await fetch("/api/usgs/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    const data = await res.json();
    isReplayActive = data.active;
    currentReplayIdx = data.index;
    pollStatus();
    loadTimeSeriesData(activeGraphParam);
  } catch (err) {
    console.error("Replay control failed:", err);
  }
}

async function onReplaySlider(val) {
  try {
    const res = await fetch("/api/usgs/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "goto", index: parseInt(val, 10) }),
    });
    const data = await res.json();
    currentReplayIdx = data.index;
    pollStatus();
    loadTimeSeriesData(activeGraphParam);
  } catch (err) {
    console.error("Slider jump failed:", err);
  }
}

// --------------------------------------------------------------------------
// LoRa Shore Gateway Commands
// --------------------------------------------------------------------------
async function sendLoraCommand(cmd, arg = 0) {
  const terminal = document.getElementById("cmd-terminal-status");
  if (terminal) {
    terminal.innerText = `[TX] Sending '${cmd}' to BUOY-01 via simulated LoRa downlink...`;
    terminal.style.color = "var(--accent-blue)";
  }
  try {
    const res = await fetch("/api/control/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, arg }),
    });
    const data = await res.json();
    if (terminal) {
      terminal.innerText = `[ACK CONFIRMED] Gateway received ACK from BUOY-01 for '${cmd}': ${data.ack}`;
      terminal.style.color = "var(--accent-green)";
    }
    pollStatus();
  } catch (err) {
    console.error("Command send failed:", err);
    if (terminal) {
      terminal.innerText = `[ERROR] Command failed: ${err}`;
      terminal.style.color = "var(--accent-red)";
    }
  }
}

// --------------------------------------------------------------------------
// Research Comparison Trial — Configurable Params
// --------------------------------------------------------------------------
async function runComparativeExperiment() {
  const btn = document.getElementById("btn-run-exp");
  const statusTxt = document.getElementById("exp-status-text");
  const validNote = document.getElementById("exp-validation-note");
  const resultsDiv = document.getElementById("exp-results");

  btn.disabled = true;
  btn.innerText = "⏳ Running Trial (Simulation Engine Calculating)...";
  if (statusTxt) statusTxt.innerText = "Please wait — running simulation engine...";

  // Collect configurable parameters from UI
  const fillTime     = parseFloat(document.getElementById("param-fill-time")?.value || 30);
  const stabTime     = parseFloat(document.getElementById("param-stab-time")?.value || 60);
  const flushTime    = parseFloat(document.getElementById("param-flush-time")?.value || 20);
  const measureDur   = parseFloat(document.getElementById("param-measure-dur")?.value || 8);
  const noiseScale   = parseFloat(document.getElementById("param-noise-scale")?.value || 1.0);
  const durationMin  = parseFloat(document.getElementById("param-duration")?.value || 30);
  const durationSec  = durationMin * 60;

  const payload = {
    duration_s: durationSec,
    fill_time_s: fillTime,
    stabilize_time_s: stabTime,
    flush_time_s: flushTime,
    measure_duration_s: measureDur,
    noise_scale: noiseScale,
  };

  try {
    const res = await fetch("/api/experiment/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const exp = await res.json();
    const delta = exp.comparison_delta || {};
    const sa = exp.open_water_system_a || {};
    const sb = exp.chamber_system_b || {};

    // Show results section
    if (resultsDiv) resultsDiv.style.display = "block";

    // Show validation note
    if (validNote) {
      validNote.style.display = "block";
      validNote.innerHTML = `<strong>⚠ Simulation Note:</strong> ${exp.validation_note || exp.disclaimer || "Results are simulation outputs only."}`;
    }

    // Summary cards
    if (delta.noise_reduction_pct) {
      setText("exp-turb-reduct", `${delta.noise_reduction_pct.turbidity}%`);
      setText("exp-ph-reduct", `${delta.noise_reduction_pct.ph}%`);
    }
    if (delta.energy_savings_pct !== undefined) setText("exp-energy-savings", `${delta.energy_savings_pct}%`);
    if (delta.battery_life_multiplier !== undefined) setText("exp-battery-mult", `${delta.battery_life_multiplier}×`);

    // Detail table
    if (sa.statistics && sb.statistics) {
      setText("exp-turb-a", sa.statistics.turbidity.std);
      setText("exp-turb-b", sb.statistics.turbidity.std);
      setText("exp-turb-delta", delta.noise_reduction_pct ? `${delta.noise_reduction_pct.turbidity}% diff (simulated)` : "--");
      setText("exp-ph-a", sa.statistics.ph.std);
      setText("exp-ph-b", sb.statistics.ph.std);
      setText("exp-ph-delta", delta.noise_reduction_pct ? `${delta.noise_reduction_pct.ph}% diff (simulated)` : "--");
    }

    setText("exp-time-a", `${sa.duty_cycle_pct || 100}%`);
    setText("exp-time-b", `${sb.duty_cycle_pct !== undefined ? sb.duty_cycle_pct.toFixed(2) : "--"}%`);
    if (delta.active_sampling_duty_cycle_reduction_pct !== undefined) {
      setText("exp-time-delta", `${delta.active_sampling_duty_cycle_reduction_pct}% duty cycle reduction`);
    }

    if (sa.energy_per_cycle_mwh !== undefined && sb.energy_per_cycle_mwh !== undefined) {
      setText("exp-energy-a", `${sa.energy_per_cycle_mwh} mWh`);
      setText("exp-energy-b", `${sb.energy_per_cycle_mwh} mWh`);
      setText("exp-energy-delta", `${delta.energy_savings_pct || "--"}% reduction (simulated)`);
    }

    if (sa.estimated_battery_endurance_days !== undefined && sb.estimated_battery_endurance_days !== undefined) {
      setText("exp-life-a", `${sa.estimated_battery_endurance_days} Days`);
      setText("exp-life-b", `${sb.estimated_battery_endurance_days} Days`);
      setText("exp-life-delta", `${delta.battery_life_multiplier || "--"}× ratio (simulated)`);
    }

    if (sa.packets_transmitted !== undefined && sb.packets_transmitted !== undefined) {
      setText("exp-comm-a", `${sa.packets_transmitted * 2} Packets/hr`);
      setText("exp-comm-b", `${sb.packets_transmitted * 2} Packets/hr`);
      setText("exp-comm-delta", `${delta.comm_overhead_reduction_pct || "--"}% less overhead`);
    }

    // Show params used
    const paramsUsedEl = document.getElementById("exp-params-used");
    if (paramsUsedEl && exp.simulation_params_used) {
      const p = exp.simulation_params_used;
      paramsUsedEl.innerHTML = `<strong>Parameters used in this run:</strong> fill=${p.fill_time_s}s · stabilize=${p.stabilize_time_s}s · flush=${p.flush_time_s}s · measure=${p.measure_duration_s}s · noise_scale=${p.noise_scale} · duration=${exp.duration_hours}h`;
    }

    if (statusTxt) statusTxt.innerText = `Trial complete — ${exp.duration_hours}h simulation`;

  } catch (err) {
    console.error("Experiment failed:", err);
    if (statusTxt) statusTxt.innerText = "Trial failed — check console for errors";
  } finally {
    btn.disabled = false;
    btn.innerText = "🧪 Run Comparative Trial (with above parameters)";
  }
}

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
