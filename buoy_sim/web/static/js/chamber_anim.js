/**
 * Flow-Through Measurement Chamber Interactive Canvas Rendering Engine.
 * Clean Scientific & Engineering UI Aesthetics.
 * Visualizes:
 * - Fluid isolation cylinder & water level fill/drain
 * - Inflow valve & micro-pump with animated flow particles
 * - Flush valve & discharge pipe
 * - Opaque optical light shielding
 * - Quiescent settling indicator
 * - Internal sensor probes (pH, EC, Turbidity, Temp)
 */

class ChamberVisualizer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.width = this.canvas.width;
    this.height = this.canvas.height;

    this.fluidLevelPct = 0;
    this.pumpActive = false;
    this.inletValve = false;
    this.flushValve = false;
    this.isStabilized = false;
    this.currentState = "LAKE_MONITORING";

    this.particleOffset = 0;
    this.animationFrame = null;
    this.startLoop();
  }

  updateState(chamberData) {
    this.fluidLevelPct = chamberData.fluid_level_pct || 0;
    this.pumpActive = chamberData.pump_active || false;
    this.inletValve = chamberData.inlet_valve_open || false;
    this.flushValve = chamberData.flush_valve_open || false;
    this.isStabilized = chamberData.fluid_stabilized || false;
    this.currentState = chamberData.current_state || "LAKE_MONITORING";
  }

  startLoop() {
    const loop = () => {
      this.draw();
      this.particleOffset += 1.5;
      this.animationFrame = requestAnimationFrame(loop);
    };
    this.animationFrame = requestAnimationFrame(loop);
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    // Clean background
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, this.width, this.height);

    // Lake water body (Left)
    ctx.fillStyle = "#e0f2fe";
    ctx.fillRect(10, 35, 75, 150);
    ctx.strokeStyle = "#bae6fd";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(10, 35, 75, 150);

    ctx.fillStyle = "#0369a1";
    ctx.font = "bold 10px sans-serif";
    ctx.fillText("LAKE WATER", 14, 110);
    ctx.fillText("AMBIENT", 24, 125);

    // Draw Inflow Pipe & Pump (from lake to chamber)
    this.drawInflowPipe(ctx);

    // Draw Chamber Cylinder (Center)
    this.drawChamber(ctx);

    // Draw Flush / Drain Pipe (Right)
    this.drawFlushPipe(ctx);

    // Status Overlay
    this.drawOverlayText(ctx);
  }

  drawInflowPipe(ctx) {
    // Pipe path
    ctx.strokeStyle = this.inletValve ? "#0284c7" : "#cbd5e1";
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(85, 70);
    ctx.lineTo(170, 70);
    ctx.stroke();

    // Valve 1 (Inlet)
    ctx.fillStyle = this.inletValve ? "#16a34a" : "#94a3b8";
    ctx.beginPath();
    ctx.arc(120, 70, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Pump symbol
    ctx.fillStyle = this.pumpActive ? "#0284c7" : "#64748b";
    ctx.beginPath();
    ctx.arc(148, 70, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 9px sans-serif";
    ctx.fillText("P", 144, 73);

    // Flowing particles
    if (this.inletValve && this.pumpActive) {
      ctx.fillStyle = "#38bdf8";
      for (let i = 90; i < 170; i += 18) {
        const x = ((i + this.particleOffset) % 80) + 90;
        if (x < 170) {
          ctx.beginPath();
          ctx.arc(x, 70, 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }

  drawFlushPipe(ctx) {
    // Flush Pipe from Chamber (285, 175) to right (380, 175)
    ctx.strokeStyle = this.flushValve ? "#16a34a" : "#cbd5e1";
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(285, 175);
    ctx.lineTo(375, 175);
    ctx.stroke();

    // Flush Valve
    ctx.fillStyle = this.flushValve ? "#16a34a" : "#94a3b8";
    ctx.beginPath();
    ctx.arc(330, 175, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Flush Output drain tank
    ctx.fillStyle = "#f1f5f9";
    ctx.fillRect(375, 150, 75, 50);
    ctx.strokeStyle = "#cbd5e1";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(375, 150, 75, 50);

    ctx.fillStyle = "#475569";
    ctx.font = "bold 9px sans-serif";
    ctx.fillText("PURGE FLUSH", 380, 175);
    ctx.fillText("DISCHARGE", 384, 188);

    if (this.flushValve && this.pumpActive) {
      ctx.fillStyle = "#38bdf8";
      for (let i = 290; i < 375; i += 18) {
        const x = ((i + this.particleOffset) % 85) + 290;
        if (x < 375) {
          ctx.beginPath();
          ctx.arc(x, 175, 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }

  drawChamber(ctx) {
    const cx = 170;
    const cy = 40;
    const cw = 115;
    const ch = 145;

    // Chamber Opaque Enclosure (dark optical shield)
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(cx, cy, cw, ch);
    ctx.strokeStyle = "#0f172a";
    ctx.lineWidth = 2.5;
    ctx.strokeRect(cx, cy, cw, ch);

    // Inner chamber observation window
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(cx + 6, cy + 6, cw - 12, ch - 12);

    // Fluid fill level
    const fillHeight = (this.fluidLevelPct / 100.0) * (ch - 14);
    if (fillHeight > 2) {
      const grad = ctx.createLinearGradient(cx, cy + ch - fillHeight, cx, cy + ch);
      grad.addColorStop(0, "rgba(56, 189, 248, 0.65)");
      grad.addColorStop(1, "rgba(2, 132, 199, 0.85)");
      ctx.fillStyle = grad;
      ctx.fillRect(cx + 6, cy + ch - fillHeight - 6, cw - 12, fillHeight);

      // Water meniscus / surface line
      ctx.strokeStyle = this.isStabilized ? "#4ade80" : "#38bdf8";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx + 6, cy + ch - fillHeight - 6);
      ctx.lineTo(cx + cw - 6, cy + ch - fillHeight - 6);
      ctx.stroke();
    }

    // 4 Sensor Probes dipped into chamber from top
    this.drawProbe(ctx, cx + 22, cy, "pH", "#a78bfa");
    this.drawProbe(ctx, cx + 46, cy, "TURB", "#38bdf8");
    this.drawProbe(ctx, cx + 70, cy, "EC", "#34d399");
    this.drawProbe(ctx, cx + 94, cy, "°C", "#fb923c");

    // Optical Shield Barrier Label
    ctx.fillStyle = "#64748b";
    ctx.font = "bold 8px sans-serif";
    ctx.fillText("DARK OPTICAL ENCLOSURE", cx + 5, cy + ch + 14);
  }

  drawProbe(ctx, x, y, label, color) {
    // Probe stem
    ctx.fillStyle = "#64748b";
    ctx.fillRect(x - 2, y, 4, 62);

    // Probe sensing tip
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y + 65, 4, 0, Math.PI * 2);
    ctx.fill();

    // Probe label
    ctx.fillStyle = color;
    ctx.font = "bold 8px sans-serif";
    ctx.fillText(label, x - 7, y - 3);
  }

  drawOverlayText(ctx) {
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 11px monospace";
    ctx.fillText(`CHAMBER: ${this.currentState}`, 160, 218);

    if (this.isStabilized) {
      ctx.fillStyle = "#16a34a";
      ctx.font = "bold 10px sans-serif";
      ctx.fillText("● QUIESCENT FLUID (OPTICAL ISOLATION ACTIVE)", 80, 20);
    } else if (this.pumpActive) {
      ctx.fillStyle = "#0284c7";
      ctx.font = "bold 10px sans-serif";
      ctx.fillText("⚡ PUMP ACTIVE (SAMPLE HYDRAULIC TRANSFER)", 100, 20);
    }
  }
}
