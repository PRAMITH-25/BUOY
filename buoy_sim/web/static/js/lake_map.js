/**
 * Interactive 2D Virtual Lake/River Environment Visualizer & Controller.
 * 
 * Enhanced Capabilities:
 * - Real USGS Observation Heatmap / Spatial Contour Layer (Turbidity, EC, Temperature, pH).
 * - True data-derived colormap representing genuine Lake Erie observations.
 * - Smooth buoy movement transition via lerp interpolation and hydrodynamic wake trail.
 * - Visible measurement / sampling intake radius with animated concentric acoustic/sampling pulses.
 * - Measurement animation state machine sequence:
 *   BUOY AT LOCATION -> SAMPLING -> CHAMBER FILL -> STABILIZE -> MEASURE -> FLUSH -> MEASUREMENT COMPLETE
 * - Floating glassmorphic buoy telemetry HUD displaying real-time USGS coordinates and water values.
 * - Animated water flow direction streamlines and moving advective particles.
 * - Parameter selector for seamless switching between USGS physical fields.
 */

class LakeMapVisualizer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");

    // Virtual lake dimensions (meters)
    this.worldWidth = 1000.0;
    this.worldHeight = 600.0;

    // Buoy positional state (with lerp target for smooth glides)
    this.buoyX = 500.0;
    this.buoyY = 300.0;
    this.targetBuoyX = 500.0;
    this.targetBuoyY = 300.0;
    this.isDragging = false;
    this.isHoveringBuoy = false;
    this.lastSentX = 500.0;
    this.lastSentY = 300.0;
    this.throttleTimer = null;

    // Movement wake trail
    this.trail = [];
    this.maxTrailPoints = 35;

    // Environmental metadata from server
    this.zoneName = "Normal Water (Main Lake Basin)";
    this.zoneId = "normal";
    this.flowSpeed = 0.18;
    this.flowDirDeg = 0.0;
    this.currentLat = 41.57963;
    this.currentLon = -81.57919;

    // Real USGS local values at buoy
    this.localUsgs = {
      ph: 8.35,
      ec_us_cm: 291.0,
      turbidity_ntu: 3.34,
      water_temp_c: 20.1,
      timestamp: "2019-06-11T10:20:54",
    };

    // USGS Spatial Grid Layer State
    this.activeParam = "turbidity_ntu"; // 'turbidity_ntu' | 'ec_us_cm' | 'water_temp_c' | 'ph' | 'none'
    this.gridCache = {};
    this.currentGrid = null;
    this.offscreenGridCanvas = document.createElement("canvas");
    this.offscreenGridCtx = this.offscreenGridCanvas.getContext("2d");

    // Measurement Animation Sequence State (Task 3)
    this.measurementState = "IDLE";
    // Sequence stages: IDLE -> BUOY_AT_LOCATION -> SAMPLING -> CHAMBER_FILL -> STABILIZE -> MEASURE -> FLUSH -> MEASUREMENT_COMPLETE -> IDLE
    this.seqTimer = null;
    this.seqStartTime = 0;
    this.seqPhaseTime = 0;
    this.isSampling = false;

    // Animation state
    this.animTime = 0.0;
    this.particles = [];
    this.initParticles(75);

    // Setup mouse & touch event listeners
    this.initEvents();

    // Load initial heatmap grid
    this.setHeatmapParam("turbidity_ntu");

    // Start render loop
    this.render = this.render.bind(this);
    requestAnimationFrame(this.render);
  }

  // -----------------------------------------------------------
  // Heatmap & Parameter Field Management
  // -----------------------------------------------------------
  async setHeatmapParam(param) {
    this.activeParam = param;
    this.updateParamButtons();

    if (param === "none") {
      this.currentGrid = null;
      this.updateLegendBar(null);
      return;
    }

    if (this.gridCache[param]) {
      this.currentGrid = this.gridCache[param];
      this.cacheOffscreenGrid(this.currentGrid);
      this.updateLegendBar(this.currentGrid);
      return;
    }

    try {
      const res = await fetch(`/api/usgs/grid?param=${param}&cols=60&rows=36`);
      if (!res.ok) return;
      const data = await res.json();
      this.gridCache[param] = data;
      if (this.activeParam === param) {
        this.currentGrid = data;
        this.cacheOffscreenGrid(data);
        this.updateLegendBar(data);
      }
    } catch (err) {
      console.error("Failed to load USGS grid for", param, err);
    }
  }

  updateParamButtons() {
    const paramKeyMap = {
      'turbidity_ntu': 'turbidity',
      'ec_us_cm': 'ec',
      'ph': 'ph',
      'water_temp_c': 'temp'
    };
    const shortKey = paramKeyMap[this.activeParam] || this.activeParam;
    const buttons = document.querySelectorAll(".btn-param");
    buttons.forEach((btn) => {
      const dp = btn.getAttribute("data-param") || "";
      const id = btn.id || "";
      if (dp === this.activeParam || id === `btn-param-${shortKey}` || id === `btn-param-${this.activeParam}`) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  updateLegendBar(grid) {
    const minEl = document.getElementById("legend-min-val") || document.getElementById("heatmap-scale-min");
    const maxEl = document.getElementById("legend-max-val") || document.getElementById("heatmap-scale-max");
    const titleEl = document.getElementById("legend-param-title") || document.getElementById("heatmap-scale-title");
    const previewEl = document.getElementById("legend-gradient-bar") || document.getElementById("heatmap-gradient-preview");

    if (!grid) {
      if (minEl) minEl.innerText = "--";
      if (maxEl) maxEl.innerText = "--";
      if (titleEl) titleEl.innerText = "Hydro Basin Flow Map";
      return;
    }

    if (minEl) minEl.innerText = `${grid.min_val} ${grid.unit}`.trim();
    if (maxEl) maxEl.innerText = `${grid.max_val} ${grid.unit}`.trim();
    if (titleEl) titleEl.innerText = `${grid.label}:`;

    if (previewEl) {
      previewEl.style.background = this.getGradientCss(grid.parameter);
    }
  }

  getGradientCss(param) {
    if (param === "turbidity_ntu") {
      return "linear-gradient(to right, #0a2540, #14532d, #ca8a04, #dc2626, #7f1d1d)";
    } else if (param === "ec_us_cm") {
      return "linear-gradient(to right, #082f49, #0284c7, #0d9488, #10b981, #059669)";
    } else if (param === "water_temp_c") {
      return "linear-gradient(to right, #1e1b4b, #2563eb, #06b6d4, #f59e0b, #ef4444)";
    } else if (param === "ph") {
      return "linear-gradient(to right, #1e293b, #0284c7, #14b8a6, #eab308, #f97316)";
    }
    return "linear-gradient(to right, #001f3f, #0074D9, #2ECC40, #FFDC00, #FF4136)";
  }

  cacheOffscreenGrid(gridData) {
    const cols = gridData.cols;
    const rows = gridData.rows;
    this.offscreenGridCanvas.width = cols;
    this.offscreenGridCanvas.height = rows;
    const ctx = this.offscreenGridCtx;
    const imgData = ctx.createImageData(cols, rows);
    const data = imgData.data;

    const minV = gridData.min_val;
    const maxV = gridData.max_val;
    const range = Math.max(0.0001, maxV - minV);
    const param = gridData.parameter;

    let pIdx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const val = gridData.grid[r][c];
        const norm = Math.max(0, Math.min(1, (val - minV) / range));
        const color = this.getColorForNorm(norm, param);

        data[pIdx]     = color[0]; // R
        data[pIdx + 1] = color[1]; // G
        data[pIdx + 2] = color[2]; // B
        data[pIdx + 3] = 205;      // Alpha (subtle transparency for water context)
        pIdx += 4;
      }
    }
    ctx.putImageData(imgData, 0, 0);
  }

  getColorForNorm(t, param) {
    // Scientific perceptual colormaps tailored to genuine USGS physical metrics
    if (param === "turbidity_ntu") {
      // Clear Blue -> Greenish -> Sediment Amber -> Murky Dark Red
      if (t < 0.25) {
        const f = t / 0.25;
        return [Math.round(10 + f * 10), Math.round(37 + f * 46), Math.round(64 + f * -19)];
      } else if (t < 0.5) {
        const f = (t - 0.25) / 0.25;
        return [Math.round(20 + f * 182), Math.round(83 + f * 55), Math.round(45 + f * -41)];
      } else if (t < 0.75) {
        const f = (t - 0.5) / 0.25;
        return [Math.round(202 + f * 18), Math.round(138 + f * -100), Math.round(4 + f * 34)];
      } else {
        const f = (t - 0.75) / 0.25;
        return [Math.round(220 + f * -93), Math.round(38 + f * -9), Math.round(38 + f * -9)];
      }
    } else if (param === "ec_us_cm") {
      // Deep Blue baseline -> Cyan -> Teal -> Emerald Mineral Stream
      if (t < 0.33) {
        const f = t / 0.33;
        return [Math.round(8 + f * -6), Math.round(47 + f * 85), Math.round(73 + f * 126)];
      } else if (t < 0.66) {
        const f = (t - 0.33) / 0.33;
        return [Math.round(2 + f * 11), Math.round(132 + f * 16), Math.round(199 + f * -63)];
      } else {
        const f = (t - 0.66) / 0.34;
        return [Math.round(13 + f * 3), Math.round(148 + f * 37), Math.round(136 + f * -7)];
      }
    } else if (param === "water_temp_c") {
      // Cool Offshore Deep Indigo -> Cyan -> Sunlight Amber -> Warm Red
      if (t < 0.3) {
        const f = t / 0.3;
        return [Math.round(30 + f * 7), Math.round(27 + f * 72), Math.round(75 + f * 160)];
      } else if (t < 0.6) {
        const f = (t - 0.3) / 0.3;
        return [Math.round(37 + f * 10), Math.round(99 + f * 115), Math.round(235 + f * -23)];
      } else if (t < 0.85) {
        const f = (t - 0.6) / 0.25;
        return [Math.round(47 + f * 198), Math.round(214 + f * -56), Math.round(212 + f * -201)];
      } else {
        const f = (t - 0.85) / 0.15;
        return [Math.round(245 + f * -6), Math.round(158 + f * -90), Math.round(11 + f * 57)];
      }
    } else {
      // pH: Buffering Blue -> Turquoise -> Mild Gold
      if (t < 0.5) {
        const f = t / 0.5;
        return [Math.round(30 + f * -28), Math.round(41 + f * 91), Math.round(59 + f * 140)];
      } else {
        const f = (t - 0.5) / 0.5;
        return [Math.round(2 + f * 232), Math.round(132 + f * 47), Math.round(199 + f * -191)];
      }
    }
  }

  // -----------------------------------------------------------
  // Measurement Sequence Animation (Task 3)
  // -----------------------------------------------------------
  startMeasurementSequence() {
    if (this.measurementState !== "IDLE" && this.measurementState !== "MEASUREMENT_COMPLETE") {
      return;
    }
    clearTimeout(this.seqTimer);

    const stages = [
      { name: "BUOY AT LOCATION", duration: 800, sampling: false },
      { name: "SAMPLING", duration: 1200, sampling: true },
      { name: "CHAMBER FILL", duration: 1500, sampling: true },
      { name: "STABILIZE", duration: 1500, sampling: true },
      { name: "MEASURE", duration: 1500, sampling: true },
      { name: "FLUSH", duration: 1500, sampling: false },
      { name: "MEASUREMENT COMPLETE", duration: 1400, sampling: false },
    ];

    let currentIdx = 0;
    const nextStage = () => {
      if (currentIdx >= stages.length) {
        this.measurementState = "IDLE";
        this.isSampling = false;
        return;
      }
      const stage = stages[currentIdx];
      this.measurementState = stage.name;
      this.isSampling = stage.sampling;
      currentIdx++;
      this.seqTimer = setTimeout(nextStage, stage.duration);
    };

    nextStage();
  }

  // -----------------------------------------------------------
  // Particle & Fluid Flow Simulation
  // -----------------------------------------------------------
  initParticles(count) {
    this.particles = [];
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: Math.random() * this.worldWidth,
        y: Math.random() * this.worldHeight,
        life: Math.random() * 120,
        maxLife: 100 + Math.random() * 80,
        speedFactor: 0.7 + Math.random() * 0.6,
      });
    }
  }

  initEvents() {
    const cvs = this.canvas;

    const getMousePos = (e) => {
      const rect = cvs.getBoundingClientRect();
      const scaleX = this.worldWidth / rect.width;
      const scaleY = this.worldHeight / rect.height;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      const mx = (clientX - rect.left) * scaleX;
      const my = (clientY - rect.top) * scaleY;
      return {
        x: Math.max(0, Math.min(this.worldWidth, mx)),
        y: Math.max(0, Math.min(this.worldHeight, my)),
      };
    };

    const isNearBuoy = (pos) => {
      const dx = pos.x - this.buoyX;
      const dy = pos.y - this.buoyY;
      return Math.sqrt(dx * dx + dy * dy) < 45.0; // Click radius
    };

    cvs.addEventListener("mousedown", (e) => {
      const pos = getMousePos(e);
      this.isDragging = true;
      this.moveToPosition(pos.x, pos.y);
      cvs.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
      const pos = getMousePos(e);
      if (this.isDragging) {
        this.moveToPosition(pos.x, pos.y);
      } else {
        const near = isNearBuoy(pos);
        if (near !== this.isHoveringBuoy) {
          this.isHoveringBuoy = near;
          cvs.style.cursor = near ? "grab" : "crosshair";
        }
      }
    });

    window.addEventListener("mouseup", () => {
      if (this.isDragging) {
        this.isDragging = false;
        cvs.style.cursor = this.isHoveringBuoy ? "grab" : "default";
        this.sendPositionImmediate(this.targetBuoyX, this.targetBuoyY);
        this.startMeasurementSequence();
      }
    });

    // Touch events for mobile/tablet
    cvs.addEventListener("touchstart", (e) => {
      const pos = getMousePos(e);
      this.isDragging = true;
      this.moveToPosition(pos.x, pos.y);
      e.preventDefault();
    }, { passive: false });

    window.addEventListener("touchmove", (e) => {
      if (this.isDragging) {
        const pos = getMousePos(e);
        this.moveToPosition(pos.x, pos.y);
      }
    });

    window.addEventListener("touchend", () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.sendPositionImmediate(this.targetBuoyX, this.targetBuoyY);
        this.startMeasurementSequence();
      }
    });
  }

  moveToPosition(x, y) {
    this.targetBuoyX = Math.max(0, Math.min(this.worldWidth, x));
    this.targetBuoyY = Math.max(0, Math.min(this.worldHeight, y));

    // When dragging directly, smoothly track mouse
    if (this.isDragging) {
      this.buoyX += (this.targetBuoyX - this.buoyX) * 0.45;
      this.buoyY += (this.targetBuoyY - this.buoyY) * 0.45;
    }

    this.updateHUDCoordinates();
    this.throttleSendPosition(this.targetBuoyX, this.targetBuoyY);
  }

  jumpToPreset(presetKey) {
    const presets = {
      normal: { x: 780.0, y: 300.0 },
      runoff: { x: 160.0, y: 130.0 },
      high_cond: { x: 175.0, y: 480.0 },
      mixing: { x: 540.0, y: 310.0 },
    };
    const target = presets[presetKey];
    if (target) {
      this.targetBuoyX = target.x;
      this.targetBuoyY = target.y;
      this.updateHUDCoordinates();
      this.sendPositionImmediate(this.targetBuoyX, this.targetBuoyY);
      this.startMeasurementSequence();
    }
  }

  throttleSendPosition(x, y) {
    if (this.throttleTimer) return;
    this.throttleTimer = setTimeout(() => {
      this.throttleTimer = null;
      if (Math.hypot(x - this.lastSentX, y - this.lastSentY) > 2.0) {
        this.sendPositionImmediate(x, y);
      }
    }, 45); // 45ms throttle for live responsiveness
  }

  async sendPositionImmediate(x, y) {
    this.lastSentX = x;
    this.lastSentY = y;
    try {
      const res = await fetch("/api/control/buoy_position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }),
      });
      if (!res.ok) return;
      const data = await res.json();
      this.zoneName = data.zone_name;
      this.zoneId = data.zone_id;
      this.currentLat = data.latitude;
      this.currentLon = data.longitude;

      if (window.realLeafletMap && data.latitude !== undefined && data.longitude !== undefined) {
        window.realLeafletMap.updateBuoyPosition(data.latitude, data.longitude);
      }

      if (data.usgs_data) {
        this.localUsgs = data.usgs_data;
      }
      this.updateHUDInfo();
      if (typeof pollStatus === "function") {
        pollStatus();
      }
    } catch (err) {
      console.error("Failed to update buoy position:", err);
    }
  }

  updateFromStatus(spatialData, gpsData) {
    if (!this.isDragging && spatialData) {
      if (Math.hypot(spatialData.buoy_x - this.targetBuoyX, spatialData.buoy_y - this.targetBuoyY) > 4.0) {
        this.targetBuoyX = spatialData.buoy_x;
        this.targetBuoyY = spatialData.buoy_y;
      }
      this.zoneName = spatialData.zone_name;
      this.zoneId = spatialData.zone_id;
      this.flowSpeed = spatialData.flow_speed_m_s || 0.18;
      this.flowDirDeg = spatialData.flow_direction_deg || 0.0;
    }
    if (gpsData) {
      this.currentLat = gpsData.latitude;
      this.currentLon = gpsData.longitude;
    }
    this.updateHUDInfo();
  }

  updateHUDCoordinates() {
    const coordEl = document.getElementById("map-hud-coords");
    if (coordEl) {
      coordEl.innerText = `X: ${Math.round(this.buoyX)}m | Y: ${Math.round(this.buoyY)}m`;
    }
  }

  updateHUDInfo() {
    this.updateHUDCoordinates();
    const zoneEl = document.getElementById("map-hud-zone");
    if (zoneEl) {
      zoneEl.innerText = this.zoneName;
      zoneEl.className = `zone-badge zone-${this.zoneId}`;
    }
    const gpsEl = document.getElementById("map-hud-gps");
    if (gpsEl) {
      gpsEl.innerText = `${this.currentLat.toFixed(5)}° N, ${this.currentLon.toFixed(5)}° W`;
    }
    const flowEl = document.getElementById("map-hud-flow");
    if (flowEl) {
      const cardinal = this.getCardinal(this.flowDirDeg);
      flowEl.innerText = `${this.flowSpeed.toFixed(2)} m/s @ ${Math.round(this.flowDirDeg)}° (${cardinal})`;
    }
    const usgsPosEl = document.getElementById("map-hud-usgs-pos");
    if (usgsPosEl) {
      const LAT_MIN = 41.565827, LAT_MAX = 41.593431;
      const LON_MIN = -81.599167, LON_MAX = -81.559214;
      const normX = Math.max(0, Math.min(1, this.buoyX / this.worldWidth));
      const normY = Math.max(0, Math.min(1, this.buoyY / this.worldHeight));
      const uLat = LAT_MIN + normY * (LAT_MAX - LAT_MIN);
      const uLon = LON_MIN + normX * (LON_MAX - LON_MIN);
      usgsPosEl.innerText = `${uLat.toFixed(5)}° N, ${uLon.toFixed(5)}° W`;
    }
  }

  getCardinal(deg) {
    const val = Math.floor((deg / 45) + 0.5);
    const arr = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"];
    return arr[val % 8];
  }

  // -----------------------------------------------------------
  // Canvas Rendering Loop
  // -----------------------------------------------------------
  render() {
    this.animTime += 0.025;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const sx = w / this.worldWidth;
    const sy = h / this.worldHeight;

    // Smooth lerp buoy movement transition (Task 2)
    const lerpSpeed = this.isDragging ? 0.40 : 0.15;
    this.buoyX += (this.targetBuoyX - this.buoyX) * lerpSpeed;
    this.buoyY += (this.targetBuoyY - this.buoyY) * lerpSpeed;

    // Add point to movement wake trail
    if (this.trail.length === 0 || Math.hypot(this.buoyX - this.trail[this.trail.length - 1].x, this.buoyY - this.trail[this.trail.length - 1].y) > 1.5) {
      this.trail.push({ x: this.buoyX, y: this.buoyY, alpha: 1.0 });
      if (this.trail.length > this.maxTrailPoints) {
        this.trail.shift();
      }
    }

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    // 1. Draw Real USGS Heatmap Layer or Base Hydro Basin
    if (this.activeParam !== "none" && this.currentGrid) {
      this.drawHeatmapField(ctx, w, h);
    } else {
      this.drawBasin(ctx, w, h);
      this.drawHydrologicalZones(ctx, sx, sy);
    }

    // 2. Draw Water Flow Direction Streamlines & Advective Particles
    this.drawFlowVectors(ctx, sx, sy);
    this.drawParticles(ctx, sx, sy);

    // 3. Draw Buoy Movement Wake Trail
    this.drawBuoyTrail(ctx, sx, sy);

    // 4. Draw Region Labels
    this.drawRegionLabels(ctx, sx, sy);

    // 5. Draw Draggable Buoy Marker, Sampling Radius & Telemetry Badge
    this.drawBuoy(ctx, sx, sy);

    // 6. Draw Measurement Sequence Overlay (Task 3)
    this.drawMeasurementSequenceBanner(ctx, w, h);

    ctx.restore();
    requestAnimationFrame(this.render);
  }

  drawHeatmapField(ctx, w, h) {
    ctx.save();
    // Render smooth interpolated image from offscreen grid canvas
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(this.offscreenGridCanvas, 0, 0, w, h);

    // Subtle wave shimmer overlay
    ctx.globalAlpha = 0.06;
    ctx.fillStyle = "#ffffff";
    for (let i = 0; i < 4; i++) {
      const phase = this.animTime * 0.7 + i * 1.5;
      const yWave = (h * 0.25) + i * (h * 0.2) + Math.sin(phase) * 10;
      ctx.beginPath();
      ctx.moveTo(0, yWave);
      for (let x = 0; x <= w; x += 50) {
        ctx.lineTo(x, yWave + Math.sin(x * 0.012 + phase) * 6);
      }
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();

    // Border
    ctx.strokeStyle = "rgba(0, 210, 255, 0.4)";
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, w - 2, h - 2);
  }

  drawBasin(ctx, w, h) {
    const baseGrad = ctx.createLinearGradient(0, 0, w, h);
    baseGrad.addColorStop(0, "#081b2e");
    baseGrad.addColorStop(0.5, "#0b2847");
    baseGrad.addColorStop(1, "#0d355c");
    ctx.fillStyle = baseGrad;
    ctx.fillRect(0, 0, w, h);
  }

  drawHydrologicalZones(ctx, sx, sy) {
    // Runoff Plume (NW)
    const rx = 160.0 * sx, ry = 130.0 * sy, rrad = 220.0 * sx;
    const rGrad = ctx.createRadialGradient(rx, ry, 10, rx + 50 * sx, ry + 20 * sy, rrad);
    rGrad.addColorStop(0, "rgba(215, 130, 40, 0.65)");
    rGrad.addColorStop(0.5, "rgba(180, 105, 30, 0.35)");
    rGrad.addColorStop(1, "rgba(100, 65, 20, 0.0)");
    ctx.fillStyle = rGrad;
    ctx.beginPath();
    ctx.ellipse(rx + 30 * sx, ry + 20 * sy, rrad * 1.1, rrad * 0.7, Math.PI / 7, 0, Math.PI * 2);
    ctx.fill();

    // Mineral Stream (SW)
    const mx = 175.0 * sx, my = 480.0 * sy, mrad = 200.0 * sx;
    const mGrad = ctx.createRadialGradient(mx, my, 10, mx + 50 * sx, my - 20 * sy, mrad);
    mGrad.addColorStop(0, "rgba(0, 230, 160, 0.60)");
    mGrad.addColorStop(0.5, "rgba(0, 180, 130, 0.30)");
    mGrad.addColorStop(1, "rgba(0, 100, 80, 0.0)");
    ctx.fillStyle = mGrad;
    ctx.beginPath();
    ctx.ellipse(mx + 30 * sx, my - 20 * sy, mrad * 1.05, mrad * 0.65, -Math.PI / 8, 0, Math.PI * 2);
    ctx.fill();
  }

  drawFlowVectors(ctx, sx, sy) {
    const arrows = [
      { x: 90, y: 110, angle: 26, len: 26, color: "rgba(255, 175, 60, 0.65)" },
      { x: 230, y: 170, angle: 24, len: 24, color: "rgba(255, 175, 60, 0.55)" },
      { x: 380, y: 230, angle: 18, len: 22, color: "rgba(255, 175, 60, 0.45)" },
      { x: 90, y: 490, angle: -22, len: 26, color: "rgba(0, 240, 180, 0.65)" },
      { x: 240, y: 440, angle: -20, len: 24, color: "rgba(0, 240, 180, 0.55)" },
      { x: 390, y: 380, angle: -15, len: 22, color: "rgba(0, 240, 180, 0.45)" },
      { x: 520, y: 290, angle: 6, len: 24, color: "rgba(0, 210, 255, 0.65)" },
      { x: 670, y: 310, angle: 2, len: 22, color: "rgba(0, 210, 255, 0.55)" },
      { x: 830, y: 310, angle: 0, len: 22, color: "rgba(0, 210, 255, 0.55)" },
      { x: 940, y: 310, angle: 0, len: 25, color: "rgba(0, 210, 255, 0.75)" },
    ];

    ctx.save();
    arrows.forEach((arr) => {
      const px = arr.x * sx;
      const py = arr.y * sy;
      const rad = (arr.angle * Math.PI) / 180;
      const length = arr.len * sx;

      ctx.strokeStyle = arr.color;
      ctx.fillStyle = arr.color;
      ctx.lineWidth = 1.8;

      ctx.beginPath();
      ctx.moveTo(px, py);
      const ex = px + Math.cos(rad) * length;
      const ey = py + Math.sin(rad) * length;
      ctx.lineTo(ex, ey);
      ctx.stroke();

      const headLen = 6 * sx;
      ctx.beginPath();
      ctx.moveTo(ex, ey);
      ctx.lineTo(ex - headLen * Math.cos(rad - Math.PI / 6), ey - headLen * Math.sin(rad - Math.PI / 6));
      ctx.lineTo(ex - headLen * Math.cos(rad + Math.PI / 6), ey - headLen * Math.sin(rad + Math.PI / 6));
      ctx.closePath();
      ctx.fill();
    });
    ctx.restore();
  }

  drawParticles(ctx, sx, sy) {
    ctx.save();
    this.particles.forEach((p) => {
      p.life++;
      if (p.life > p.maxLife || p.x > this.worldWidth) {
        p.x = Math.random() * 80;
        p.y = Math.random() * this.worldHeight;
        p.life = 0;
      }

      let vx = 0.9 * p.speedFactor;
      let vy = 0.0;
      if (p.y < 280) vy += 0.32;
      else if (p.y > 340) vy -= 0.28;

      p.x += vx;
      p.y += vy;

      const px = p.x * sx;
      const py = p.y * sy;
      const alpha = Math.sin((p.life / p.maxLife) * Math.PI) * 0.45;
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha.toFixed(2)})`;
      ctx.beginPath();
      ctx.arc(px, py, 1.4 * sx, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  drawBuoyTrail(ctx, sx, sy) {
    if (this.trail.length < 2) return;
    ctx.save();
    for (let i = 0; i < this.trail.length - 1; i++) {
      const p1 = this.trail[i];
      const p2 = this.trail[i + 1];
      const ageNorm = i / this.trail.length; // 0 (oldest) to 1 (newest)
      ctx.strokeStyle = `rgba(0, 210, 255, ${(ageNorm * 0.45).toFixed(2)})`;
      ctx.lineWidth = Math.max(1, 3.5 * ageNorm * sx);
      ctx.beginPath();
      ctx.moveTo(p1.x * sx, p1.y * sy);
      ctx.lineTo(p2.x * sx, p2.y * sy);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawRegionLabels(ctx, sx, sy) {
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const labels = [
      { text: "SEDIMENT RUNOFF CREEK (HIGH TURBIDITY)", x: 230, y: 65, color: "#ffb74d", bg: "rgba(20, 15, 10, 0.75)" },
      { text: "MINERAL TRIBUTARY (HIGH CONDUCTIVITY)", x: 240, y: 555, color: "#00e676", bg: "rgba(10, 25, 15, 0.75)" },
      { text: "CONFLUENCE & MIXING REGION", x: 540, y: 220, color: "#80d8ff", bg: "rgba(15, 25, 45, 0.75)" },
      { text: "MAIN BASIN (NORMAL WATER)", x: 800, y: 220, color: "#b0bec5", bg: "rgba(15, 25, 40, 0.75)" },
      { text: "LAKE OUTFLOW →", x: 920, y: 350, color: "#00d2ff", bg: "rgba(10, 30, 50, 0.75)" },
    ];

    labels.forEach((lbl) => {
      const lx = lbl.x * sx;
      const ly = lbl.y * sy;
      ctx.font = `600 ${Math.max(9, 10 * sx)}px sans-serif`;
      const metrics = ctx.measureText(lbl.text);
      const padX = 7 * sx;
      const padY = 3.5 * sy;

      ctx.fillStyle = lbl.bg;
      ctx.fillRect(lx - metrics.width / 2 - padX, ly - 8 * sy - padY, metrics.width + padX * 2, 16 * sy + padY * 2);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
      ctx.lineWidth = 1;
      ctx.strokeRect(lx - metrics.width / 2 - padX, ly - 8 * sy - padY, metrics.width + padX * 2, 16 * sy + padY * 2);
      ctx.fillStyle = lbl.color;
      ctx.fillText(lbl.text, lx, ly);
    });
    ctx.restore();
  }

  drawBuoy(ctx, sx, sy) {
    const bx = this.buoyX * sx;
    const by = this.buoyY * sy;

    ctx.save();

    // 1. Visible Measurement / Sampling Intake Radius (Task 2)
    const samplingRadius = 45.0 * sx;
    ctx.save();
    ctx.strokeStyle = this.isSampling ? "rgba(0, 230, 118, 0.65)" : "rgba(0, 210, 255, 0.35)";
    ctx.fillStyle = this.isSampling ? "rgba(0, 230, 118, 0.08)" : "rgba(0, 210, 255, 0.04)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.arc(bx, by, samplingRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    // 2. Active Sampling Pulse Wave (Task 2 & 3)
    if (this.isSampling) {
      const sPhase = (this.animTime * 3.0) % (Math.PI * 2);
      const sRad = (15 + sPhase * 14) * sx;
      const sAlpha = Math.max(0, 0.7 - sRad / (samplingRadius * 1.2));
      ctx.strokeStyle = `rgba(0, 230, 118, ${sAlpha.toFixed(2)})`;
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(bx, by, sRad, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      // Normal hydrodynamic wave ripple
      const pPhase = (this.animTime * 1.5) % (Math.PI * 2);
      const pRad = (16 + pPhase * 7) * sx;
      const alpha = Math.max(0, 0.5 - (pRad / (36 * sx)));
      ctx.strokeStyle = `rgba(0, 210, 255, ${alpha.toFixed(2)})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(bx, by, pRad, 0, Math.PI * 2);
      ctx.stroke();
    }

    // 3. Hover aura
    if (this.isDragging || this.isHoveringBuoy) {
      ctx.fillStyle = "rgba(0, 210, 255, 0.22)";
      ctx.beginPath();
      ctx.arc(bx, by, 26 * sx, 0, Math.PI * 2);
      ctx.fill();
    }

    // 4. Buoy Float Collar (High-visibility Safety Orange)
    const floatRadius = 14 * sx;
    const collarGrad = ctx.createRadialGradient(bx - 3, by - 3, 2, bx, by, floatRadius);
    collarGrad.addColorStop(0, "#ffd54f");
    collarGrad.addColorStop(0.7, "#ff9100");
    collarGrad.addColorStop(1, "#e65100");

    ctx.fillStyle = collarGrad;
    ctx.beginPath();
    ctx.arc(bx, by, floatRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.6;
    ctx.stroke();

    // 5. Central Solar Panel Deck
    const deckRadius = 7.5 * sx;
    ctx.fillStyle = "#102a43";
    ctx.beginPath();
    ctx.arc(bx, by, deckRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#00d2ff";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Solar grid
    ctx.strokeStyle = "rgba(0, 210, 255, 0.5)";
    ctx.beginPath();
    ctx.moveTo(bx - deckRadius, by);
    ctx.lineTo(bx + deckRadius, by);
    ctx.moveTo(bx, by - deckRadius);
    ctx.lineTo(bx, by + deckRadius);
    ctx.stroke();

    // 6. Flashing Central Beacon LED
    const ledFlash = Math.sin(this.animTime * (this.isSampling ? 10 : 5)) > 0;
    const ledColor = this.isSampling ? (ledFlash ? "#00e676" : "#004d40") : (ledFlash ? "#00d2ff" : "#003b46");
    ctx.fillStyle = ledColor;
    ctx.shadowColor = this.isSampling ? "#00e676" : "#00d2ff";
    ctx.shadowBlur = ledFlash ? 12 : 2;
    ctx.beginPath();
    ctx.arc(bx, by, 2.6 * sx, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // 7. Floating Local Water-Quality HUD Badge (Task 2)
    this.drawFloatingBuoyHUD(ctx, bx, by, sx, sy);

    ctx.restore();
  }

  drawFloatingBuoyHUD(ctx, bx, by, sx, sy) {
    const floatRadius = 14 * sx;
    const LAT_MIN = 41.565827, LAT_MAX = 41.593431;
    const LON_MIN = -81.599167, LON_MAX = -81.559214;
    const normX = Math.max(0, Math.min(1, this.buoyX / this.worldWidth));
    const normY = Math.max(0, Math.min(1, this.buoyY / this.worldHeight));
    const uLat = LAT_MIN + normY * (LAT_MAX - LAT_MIN);
    const uLon = LON_MIN + normX * (LON_MAX - LON_MIN);

    const titleText = `BUOY-01 • ${this.isSampling ? "SAMPLING ACTIVE" : "MONITORING"}`;
    const gpsText = `${uLat.toFixed(5)}° N, ${uLon.toFixed(5)}° W`;
    const valText = `pH ${this.localUsgs.ph.toFixed(2)} | EC ${Math.round(this.localUsgs.ec_us_cm)} | Turb ${this.localUsgs.turbidity_ntu.toFixed(2)} NTU | ${this.localUsgs.water_temp_c.toFixed(1)}°C`;

    ctx.font = `700 ${Math.max(9.5, 10.5 * sx)}px monospace`;
    const w1 = ctx.measureText(titleText).width;
    const w2 = ctx.measureText(gpsText).width;
    ctx.font = `600 ${Math.max(9, 10 * sx)}px monospace`;
    const w3 = ctx.measureText(valText).width;
    const boxW = Math.max(w1, w2, w3) + 20 * sx;
    const boxH = 44 * sy;

    // Place badge above buoy (or below if near top border)
    let boxY = by - floatRadius - boxH - 12 * sy;
    if (boxY < 10) boxY = by + floatRadius + 14 * sy;

    // Glassmorphic panel background
    ctx.fillStyle = "rgba(10, 15, 26, 0.88)";
    ctx.strokeStyle = this.isSampling ? "rgba(0, 230, 118, 0.6)" : "rgba(0, 210, 255, 0.4)";
    ctx.lineWidth = 1.2;

    const boxX = Math.max(10, Math.min(this.canvas.width - boxW - 10, bx - boxW / 2));
    ctx.beginPath();
    ctx.roundRect(boxX, boxY, boxW, boxH, 6);
    ctx.fill();
    ctx.stroke();

    // Header line
    ctx.textAlign = "left";
    ctx.font = `700 ${Math.max(9.5, 10.5 * sx)}px monospace`;
    ctx.fillStyle = this.isSampling ? "#00e676" : "#00d2ff";
    ctx.fillText(titleText, boxX + 8 * sx, boxY + 13 * sy);

    // GPS coordinates
    ctx.font = `600 ${Math.max(8.5, 9.5 * sx)}px monospace`;
    ctx.fillStyle = "#94a3b8";
    ctx.fillText(gpsText, boxX + 8 * sx, boxY + 26 * sy);

    // Local water values
    ctx.font = `700 ${Math.max(9, 10 * sx)}px monospace`;
    ctx.fillStyle = "#f8fafc";
    ctx.fillText(valText, boxX + 8 * sx, boxY + 39 * sy);
  }

  drawMeasurementSequenceBanner(ctx, w, h) {
    if (this.measurementState === "IDLE") return;

    ctx.save();
    const steps = [
      "BUOY AT LOCATION",
      "SAMPLING",
      "CHAMBER FILL",
      "STABILIZE",
      "MEASURE",
      "FLUSH",
      "MEASUREMENT COMPLETE"
    ];

    const curIdx = steps.indexOf(this.measurementState);
    const bannerW = Math.min(w - 40, 860);
    const bannerH = 34;
    const bx = (w - bannerW) / 2;
    const by = h - bannerH - 12;

    // Background pill
    ctx.fillStyle = "rgba(10, 16, 28, 0.92)";
    ctx.strokeStyle = "rgba(0, 210, 255, 0.5)";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.roundRect(bx, by, bannerW, bannerH, 17);
    ctx.fill();
    ctx.stroke();

    // Render sequence steps
    const stepCount = steps.length;
    const stepW = bannerW / stepCount;

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    steps.forEach((step, idx) => {
      const sx = bx + idx * stepW + stepW / 2;
      const sy = by + bannerH / 2;

      let color = "#64748b";
      let prefix = "○";
      if (idx < curIdx) {
        color = "#00d2ff"; // Done
        prefix = "✓";
      } else if (idx === curIdx) {
        color = "#00e676"; // Active
        prefix = "▶";
      }

      ctx.font = idx === curIdx ? "700 9px monospace" : "600 8.5px monospace";
      ctx.fillStyle = color;
      ctx.fillText(`${prefix} ${step}`, sx, sy);

      // Separator arrow
      if (idx < stepCount - 1) {
        ctx.fillStyle = "#334155";
        ctx.fillText("→", bx + (idx + 1) * stepW, sy);
      }
    });

    ctx.restore();
  }
}

// Global visualizer instance
let lakeMapVisualizer = null;

function setHeatmapParameter(param) {
  if (lakeMapVisualizer) {
    lakeMapVisualizer.setHeatmapParam(param);
  }
}

