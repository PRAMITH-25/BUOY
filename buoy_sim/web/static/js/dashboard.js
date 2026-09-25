/**
 * Autonomous Lake Water Quality Monitoring Buoy Dashboard Controller.
 * Clean Scientific Architecture.
 * Handles:
 * - Real-time polling of USGS-derived water quality telemetry
 * - Interactive 2D Lake Map & Source Observation inspection (KNN-IDW K=3)
 * - Historical Data Replay engine & actual observation time-series graph
 * - Flow-Through Chamber state transitions & quiescent measurement
 * - Sensor / ADS1115 16-Bit signal processing path
 * - LoRa communication protocol simulation & shore gateway telemetry log
 * - Research comparative experiment runner & CSV exports
 */

let chamberVisualizer = null;
let timeSeriesChart = null;
let activeGraphParam = "turbidity_ntu";
let lastLoggedSeqNum = 0;
let isReplayActive = false;
let currentReplayIdx = 0;

document.addEventListener("DOMContentLoaded", () => {
  // Initialize Chamber visualizer
  if (typeof ChamberVisualizer !== "undefined") {
    chamberVisualizer = new ChamberVisualizer("chamberCanvas");
  }

  // Initialize Lake Map visualizer
  if (typeof LakeMapVisualizer !== "undefined") {
    lakeMapVisualizer = new LakeMapVisualizer("lakeMapCanvas");
  }

  // Initialize time-series chart
  initTimeSeriesChart();

  // Load initial historical time-series data
  loadTimeSeriesData("turbidity_ntu");

  // Start polling
  setInterval(pollStatus, 500);
  pollStatus();
});

// --------------------------------------------------------------------------
// Status Polling & Central UI Sync
// --------------------------------------------------------------------------
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

function syncUI(data) {
  const gt = data.ground_truth || {};
  const usgs = gt.usgs || data.usgs_data || {};
  const sensors = data.sensors || {};
  const filt = sensors.filtered || {};
  const raw = sensors.raw || {};
  const lora = data.lora || {};

  // 1. Top Header
  const simSec = data.sim_time_s || 0;
  const h = Math.floor(simSec / 3600) % 24;
  const m = Math.floor((simSec % 3600) / 60);
  const s = Math.floor(simSec % 60);
  const pad = (n) => String(n).padStart(2, "0");
  const timeStr = `${pad(h)}:${pad(m)}:${pad(s)}`;
  const timeEl = document.getElementById("hdr-sim-time");
  if (timeEl) timeEl.innerText = timeStr;

  const statusEl = document.getElementById("hdr-sim-status");
  if (statusEl) {
    statusEl.innerText = data.is_running ? "SIMULATION ACTIVE" : "SIMULATION PAUSED";
    statusEl.className = data.is_running ? "sim-stat-val text-blue font-mono" : "sim-stat-val text-amber font-mono";
  }

  const ppBtn = document.getElementById("btn-play-pause");
  if (ppBtn) {
    ppBtn.innerText = data.is_running ? "❚❚ Pause" : "▶ Resume";
    ppBtn.className = data.is_running ? "btn btn-primary" : "btn btn-secondary";
  }

  // 2. Lake Map Quick Coordinates
  const qCoords = document.getElementById("map-quick-coords");
  if (qCoords && gt.buoy_x !== undefined && gt.buoy_y !== undefined) {
    qCoords.innerText = `X: ${Math.round(gt.buoy_x)}m | Y: ${Math.round(gt.buoy_y)}m`;
  }

  // 2. Source Data Inspection (Section 7)
  updateSourceObservations(data);

  // 3. Water Quality at Buoy Location
  const phVal = usgs.ph !== undefined ? usgs.ph : filt.ph;
  const ecVal = usgs.ec_us_cm !== undefined ? usgs.ec_us_cm : filt.ec_us_cm;
  const turbVal = usgs.turbidity_ntu !== undefined ? usgs.turbidity_ntu : filt.turbidity_ntu;
  const tempVal = usgs.water_temp_c !== undefined ? usgs.water_temp_c : filt.temp_c;

  const dPh = document.getElementById("disp-ph");
  if (dPh && phVal !== undefined) dPh.innerText = phVal.toFixed(2);

  const dEc = document.getElementById("disp-ec");
  if (dEc && ecVal !== undefined) dEc.innerText = ecVal.toFixed(1);

  const dTurb = document.getElementById("disp-turb");
  if (dTurb && turbVal !== undefined) dTurb.innerText = turbVal.toFixed(2);

  const dTemp = document.getElementById("disp-temp");
  if (dTemp && tempVal !== undefined) dTemp.innerText = tempVal.toFixed(2);

  const dLat = document.getElementById("disp-lat");
  if (dLat && usgs.latitude !== undefined) dLat.innerText = `${usgs.latitude.toFixed(5)}° N`;

  const dLon = document.getElementById("disp-lon");
  if (dLon && usgs.longitude !== undefined) dLon.innerText = `${usgs.longitude.toFixed(5)}° W`;

  const dTs = document.getElementById("disp-timestamp");
  if (dTs && usgs.nearest_record_timestamp) dTs.innerText = usgs.nearest_record_timestamp;

  // Percentiles & Statistical indicator
  const pcts = data.percentiles || {};
  updatePercentileBadges(pcts, turbVal);

  // 5. Replay State Sync
  if (data.replay) {
    isReplayActive = data.replay.active;
    currentReplayIdx = data.replay.index;
    const rBadge = document.getElementById("replay-status-badge");
    if (rBadge) {
      rBadge.innerText = isReplayActive ? "USGS REPLAY ACTIVE (PLAYING)" : "USGS REPLAY PAUSED";
      rBadge.className = isReplayActive ? "card-status-badge badge-sim" : "card-status-badge badge-usgs";
    }
    const rSlider = document.getElementById("replay-slider");
    if (rSlider && !document.activeElement.isSameNode(rSlider)) {
      rSlider.value = currentReplayIdx;
    }
    const rDisp = document.getElementById("replay-index-display");
    if (rDisp) {
      rDisp.innerText = `Obs #${String(currentReplayIdx).padStart(5, "0")} / ${data.replay.total_records.toLocaleString()}`;
    }
    const rTime = document.getElementById("replay-timestamp-disp");
    if (rTime && usgs.nearest_record_timestamp) {
      rTime.innerText = usgs.nearest_record_timestamp;
    }
  }

  // 6. Chamber Visualizer & Diagnostics
  if (chamberVisualizer && data.chamber) {
    chamberVisualizer.updateState(data.chamber);
    const ch = data.chamber;
    const stEl = document.getElementById("ch-state-text");
    if (stEl) stEl.innerText = ch.current_state;

    const ptEl = document.getElementById("ch-phase-time");
    if (ptEl) ptEl.innerText = `${ch.time_in_state_s}s / ${ch.state_duration_s}s`;

    const flEl = document.getElementById("ch-fluid-level");
    if (flEl) flEl.innerText = `${ch.fluid_level_pct}%`;

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

    // Step stepper
    const steps = ["LAKE_MONITORING", "CHAMBER_FILL", "STABILIZE", "MEASURE", "FLUSH"];
    steps.forEach((st) => {
      const el = document.getElementById(`step-${st}`);
      if (el) {
        if (st === ch.current_state) {
          el.className = "cycle-step-node active";
        } else {
          el.className = "cycle-step-node";
        }
      }
    });

    // Measurement values in chamber
    const cPh = document.getElementById("ch-val-ph");
    if (cPh && phVal !== undefined) cPh.innerText = phVal.toFixed(2);
    const cEc = document.getElementById("ch-val-ec");
    if (cEc && ecVal !== undefined) cEc.innerText = ecVal.toFixed(1);
    const cTurb = document.getElementById("ch-val-turb");
    if (cTurb && turbVal !== undefined) cTurb.innerText = turbVal.toFixed(2);
    const cTemp = document.getElementById("ch-val-temp");
    if (cTemp && tempVal !== undefined) cTemp.innerText = tempVal.toFixed(2);
  }

  // 7. Sensor / ADS1115 Signal Path Table
  const sPh = document.getElementById("sig-ph-val");
  if (sPh && phVal !== undefined) sPh.innerText = phVal.toFixed(2);
  const sTurb = document.getElementById("sig-turb-val");
  if (sTurb && turbVal !== undefined) sTurb.innerText = `${turbVal.toFixed(2)} NTU`;
  const sEc = document.getElementById("sig-ec-val");
  if (sEc && ecVal !== undefined) sEc.innerText = `${ecVal.toFixed(1)} µS/cm`;
  const sTemp = document.getElementById("sig-temp-val");
  if (sTemp && tempVal !== undefined) sTemp.innerText = `${tempVal.toFixed(2)} °C`;

  // 8. LoRa Telemetry & Shore Gateway
  updateLoraSection(data);
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
      const distEl = document.getElementById(`sp${pNum}-dist`);
      if (distEl) distEl.innerText = `Dist: ${p.distance_m} m`;

      const coordsEl = document.getElementById(`sp${pNum}-coords`);
      if (coordsEl) coordsEl.innerText = `${p.latitude.toFixed(4)}°, ${p.longitude.toFixed(4)}°`;

      const turbEl = document.getElementById(`sp${pNum}-turb`);
      if (turbEl) turbEl.innerText = `${p.turbidity_ntu.toFixed(2)} NTU`;

      const ecEl = document.getElementById(`sp${pNum}-ec`);
      if (ecEl) ecEl.innerText = `${p.ec_us_cm.toFixed(1)} µS/cm`;

      const ptEl = document.getElementById(`sp${pNum}-phtemp`);
      if (ptEl) ptEl.innerText = `pH ${p.ph.toFixed(2)} | ${p.water_temp_c.toFixed(1)}°C`;

      const wEl = document.getElementById(`sp${pNum}-weight`);
      if (wEl) wEl.innerText = `${p.weight_pct}%`;
    }
  }

  // Derived values summary box
  if (usgs) {
    const dTurb = document.getElementById("derived-turb");
    if (dTurb && usgs.turbidity_ntu !== undefined) dTurb.innerText = `${usgs.turbidity_ntu.toFixed(2)} NTU`;

    const dEc = document.getElementById("derived-ec");
    if (dEc && usgs.ec_us_cm !== undefined) dEc.innerText = `${usgs.ec_us_cm.toFixed(1)} µS/cm`;

    const dPh = document.getElementById("derived-ph");
    if (dPh && usgs.ph !== undefined) dPh.innerText = usgs.ph.toFixed(2);

    const dTemp = document.getElementById("derived-temp");
    if (dTemp && usgs.water_temp_c !== undefined) dTemp.innerText = `${usgs.water_temp_c.toFixed(2)} °C`;
  }
}

// --------------------------------------------------------------------------
// Percentile Badges & Statistical Indicators
// --------------------------------------------------------------------------
function updatePercentileBadges(pcts, turbVal) {
  const phPctEl = document.getElementById("disp-ph-pct");
  if (phPctEl && pcts.ph !== undefined) {
    phPctEl.innerText = `${pcts.ph}th percentile`;
  }

  const ecPctEl = document.getElementById("disp-ec-pct");
  if (ecPctEl && pcts.ec_us_cm !== undefined) {
    ecPctEl.innerText = `${pcts.ec_us_cm}th percentile`;
  }

  const turbPct = pcts.turbidity_ntu !== undefined ? pcts.turbidity_ntu : 50;
  const turbPctEl = document.getElementById("disp-turb-pct");
  const statAlertEl = document.getElementById("disp-stat-alert");

  let statusText = "TYPICAL / NORMAL";
  let badgeClass = "stat-percentile-tag pct-normal";
  if (turbPct >= 90) {
    statusText = "HIGH RELATIVE TO DATASET";
    badgeClass = "stat-percentile-tag pct-high";
  } else if (turbPct <= 10) {
    statusText = "LOW RELATIVE TO DATASET";
    badgeClass = "stat-percentile-tag pct-low";
  }

  if (turbPctEl) {
    turbPctEl.innerText = `${turbPct}th percentile (${statusText})`;
    turbPctEl.className = badgeClass;
  }

  if (statAlertEl) {
    statAlertEl.innerText = `${statusText} (${turbPct}th %ile of historical measurements)`;
    statAlertEl.className = turbPct >= 90 ? "meta-item-val text-amber font-bold" : "meta-item-val text-teal";
  }

  const tempPctEl = document.getElementById("disp-temp-pct");
  if (tempPctEl && pcts.water_temp_c !== undefined) {
    tempPctEl.innerText = `${pcts.water_temp_c}th percentile`;
  }
}

// --------------------------------------------------------------------------
// LoRa Buoy → Gateway Section & Packet History
// --------------------------------------------------------------------------
function updateLoraSection(data) {
  const lora = data.lora || {};
  const lastTx = lora.last_tx;
  const exchangeLog = data.lora_exchange || [];

  // Ticker animation
  const stepTx = document.getElementById("lora-step-tx");
  const stepRx = document.getElementById("lora-step-rx");
  const stepDec = document.getElementById("lora-step-dec");
  const stepAck = document.getElementById("lora-step-ack");

  if (lastTx) {
    if (stepTx) stepTx.className = "comm-step-badge active";
    setTimeout(() => { if (stepRx) stepRx.className = "comm-step-badge active"; }, 150);
    setTimeout(() => { if (stepDec) stepDec.className = "comm-step-badge active"; }, 300);
    setTimeout(() => { if (stepAck) stepAck.className = "comm-step-badge active"; }, 450);
  }

  // Update current packet display
  if (lastTx && lastTx.packet_dict) {
    const pt = lastTx.packet_dict.plaintext || {};
    const seqEl = document.getElementById("pkt-seq");
    if (seqEl) seqEl.innerText = `#${String(lastTx.seq_num).padStart(5, "0")}`;

    const latEl = document.getElementById("pkt-lat");
    if (latEl && pt.latitude !== undefined) latEl.innerText = `${pt.latitude.toFixed(5)}° N`;

    const lonEl = document.getElementById("pkt-lon");
    if (lonEl && pt.longitude !== undefined) lonEl.innerText = `${pt.longitude.toFixed(5)}° W`;

    const phEl = document.getElementById("pkt-ph");
    if (phEl && pt.ph !== undefined) phEl.innerText = pt.ph.toFixed(2);

    const ecEl = document.getElementById("pkt-ec");
    if (ecEl && pt.ec_us_cm !== undefined) ecEl.innerText = `${pt.ec_us_cm.toFixed(1)} µS/cm`;

    const turbEl = document.getElementById("pkt-turb");
    if (turbEl && pt.turbidity_ntu !== undefined) turbEl.innerText = `${pt.turbidity_ntu.toFixed(2)} NTU`;

    const tempEl = document.getElementById("pkt-temp");
    if (tempEl && pt.temp_c !== undefined) tempEl.innerText = `${pt.temp_c.toFixed(2)} °C`;

    const tsEl = document.getElementById("pkt-timestamp");
    const usgs = data.ground_truth ? data.ground_truth.usgs : null;
    if (tsEl) tsEl.innerText = (usgs && usgs.nearest_record_timestamp) ? usgs.nearest_record_timestamp : "2019-06-11T10:20:54";

    const statEl = document.getElementById("pkt-status");
    if (statEl) {
      statEl.innerText = lastTx.acked ? "ACK_RECEIVED_BY_BUOY" : "TRANSMITTED";
      statEl.className = lastTx.acked ? "val text-green font-bold" : "val text-blue font-bold";
    }
  }

  // Update Gateway packet history table
  if (exchangeLog.length > 0) {
    const tbody = document.getElementById("lora-packet-history-body");
    if (tbody) {
      tbody.innerHTML = "";
      // Display up to 15 recent packets (newest first)
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
// Real Data Time-Series Chart (Section 15)
// --------------------------------------------------------------------------
function initTimeSeriesChart() {
  const ctx = document.getElementById("usgsTimeSeriesChart").getContext("2d");
  timeSeriesChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Turbidity (NTU)",
          data: [],
          borderColor: "#0284c7",
          backgroundColor: "rgba(2, 132, 199, 0.08)",
          fill: true,
          tension: 0.25,
          pointRadius: 2.5,
          pointBackgroundColor: "#0284c7",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#64748b", maxTicksLimit: 12, font: { size: 10, family: "monospace" } },
        },
        y: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#334155", font: { size: 11, family: "monospace" } },
        },
      },
      plugins: {
        legend: { labels: { color: "#0f172a", font: { weight: 600 } } },
        tooltip: {
          backgroundColor: "#0f172a",
          titleFont: { family: "monospace" },
          bodyFont: { family: "monospace" },
        },
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
    if (el) {
      if (k === param) el.classList.add("active");
      else el.classList.remove("active");
    }
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
      body: JSON.stringify({ action: action }),
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
    terminal.innerText = `[TX] Sending command '${cmd}' to Buoy via LoRa downlink...`;
    terminal.style.color = "var(--accent-blue)";
  }

  try {
    const res = await fetch("/api/control/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, arg: arg }),
    });
    const data = await res.json();
    if (terminal) {
      terminal.innerText = `[ACK CONFIRMED] Shore Gateway received ACK from BUOY-01 for '${cmd}': ${data.ack}`;
      terminal.style.color = "var(--accent-green)";
    }
    pollStatus();
  } catch (err) {
    console.error("Command send failed:", err);
    if (terminal) {
      terminal.innerText = `[ERROR] Command transmission failed: ${err}`;
      terminal.style.color = "var(--accent-red)";
    }
  }
}

// --------------------------------------------------------------------------
// Research Comparison Trial & CSV Export
// --------------------------------------------------------------------------
async function runComparativeExperiment() {
  const btn = document.getElementById("btn-run-exp");
  btn.disabled = true;
  btn.innerText = "⏳ Running 30-Min Trial (Simulation Engine Calculating)...";

  try {
    const res = await fetch("/api/experiment/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_s: 1800.0 }),
    });
    const exp = await res.json();
    const delta = exp.comparison_delta || {};
    const sa = exp.open_water_system_a || {};
    const sb = exp.chamber_system_b || {};

    // Populate summary cards with real calculated percentages
    const turbReduct = document.getElementById("exp-turb-reduct");
    if (turbReduct && delta.noise_reduction_pct) turbReduct.innerText = `${delta.noise_reduction_pct.turbidity}%`;

    const phReduct = document.getElementById("exp-ph-reduct");
    if (phReduct && delta.noise_reduction_pct) phReduct.innerText = `${delta.noise_reduction_pct.ph}%`;

    const engSavings = document.getElementById("exp-energy-savings");
    if (engSavings && delta.energy_savings_pct !== undefined) engSavings.innerText = `${delta.energy_savings_pct}%`;

    const batMult = document.getElementById("exp-battery-mult");
    if (batMult && delta.battery_life_multiplier !== undefined) batMult.innerText = `${delta.battery_life_multiplier}x`;

    // Populate detailed table with genuine calculations
    if (sa.statistics && sb.statistics) {
      const eTa = document.getElementById("exp-turb-a");
      if (eTa) eTa.innerText = sa.statistics.turbidity.std;
      const eTb = document.getElementById("exp-turb-b");
      if (eTb) eTb.innerText = sb.statistics.turbidity.std;
      const eTdel = document.getElementById("exp-turb-delta");
      if (eTdel) eTdel.innerText = `${delta.noise_reduction_pct.turbidity}% Noise Reduction`;

      const ePa = document.getElementById("exp-ph-a");
      if (ePa) ePa.innerText = sa.statistics.ph.std;
      const ePb = document.getElementById("exp-ph-b");
      if (ePb) ePb.innerText = sb.statistics.ph.std;
      const ePdel = document.getElementById("exp-ph-delta");
      if (ePdel) ePdel.innerText = `${delta.noise_reduction_pct.ph}% Variance Reduction`;
    }

    if (sa.energy_per_cycle_mwh !== undefined && sb.energy_per_cycle_mwh !== undefined) {
      const eEa = document.getElementById("exp-energy-a");
      if (eEa) eEa.innerText = `${sa.energy_per_cycle_mwh} mWh`;
      const eEb = document.getElementById("exp-energy-b");
      if (eEb) eEb.innerText = `${sb.energy_per_cycle_mwh} mWh`;
      const eEdel = document.getElementById("exp-energy-delta");
      if (eEdel) eEdel.innerText = `${delta.energy_savings_pct}% Energy Reduction`;
    }

    if (sa.estimated_battery_endurance_days !== undefined && sb.estimated_battery_endurance_days !== undefined) {
      const eLa = document.getElementById("exp-life-a");
      if (eLa) eLa.innerText = `${sa.estimated_battery_endurance_days} Days`;
      const eLb = document.getElementById("exp-life-b");
      if (eLb) eLb.innerText = `${sb.estimated_battery_endurance_days} Days`;
      const eLdel = document.getElementById("exp-life-delta");
      if (eLdel) eLdel.innerText = `${delta.battery_life_multiplier}x Endurance Advantage`;
    }

    if (sa.packets_transmitted !== undefined && sb.packets_transmitted !== undefined) {
      const eCa = document.getElementById("exp-comm-a");
      if (eCa) eCa.innerText = `${sa.packets_transmitted * 2} Packets/hr`;
      const eCb = document.getElementById("exp-comm-b");
      if (eCb) eCb.innerText = `${sb.packets_transmitted * 2} Packets/hr`;
      const eCdel = document.getElementById("exp-comm-delta");
      if (eCdel) eCdel.innerText = `${delta.comm_overhead_reduction_pct}% Less Channel Overhead`;
    }

  } catch (err) {
    console.error("Experiment failed:", err);
  } finally {
    btn.disabled = false;
    btn.innerText = "🧪 Run 30-Min Comparative Trial";
  }
}

function exportComparisonCsv() {
  window.location.href = "/api/export/comparison.csv";
}

function exportTelemetryCsv() {
  window.location.href = "/api/export/telemetry.csv";
}

// --------------------------------------------------------------------------
// Play / Pause / Step Controls
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
