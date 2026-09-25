"""
Solar-Powered Autonomous Lake Water Quality Monitoring Buoy
Web Dashboard Server Launcher.

Usage:
  python run_web.py [--host 0.0.0.0] [--port 5000] [--debug]

For production (Render / gunicorn), the Procfile and render.yaml are used instead.
The PORT environment variable is honoured automatically when set by the platform.
"""
import argparse
import os
from buoy_sim.web.app import app

def main():
    # Read PORT from environment (Render injects this); fall back to CLI arg, then 5000
    env_port = int(os.environ.get("PORT", 0))

    parser = argparse.ArgumentParser(description="Launch Buoy Digital Simulation Web Dashboard")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=env_port or 5000,
                        help="Port number (default: PORT env var, then 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    port = env_port or args.port

    print("=" * 80)
    print(" SOLAR-POWERED AUTONOMOUS LAKE WATER QUALITY MONITORING BUOY")
    print(" Web Dashboard & Interactive Digital Twin Server")
    print("=" * 80)
    print(f"[*] Server running at: http://{args.host}:{port}")
    print("[*] Interactive Chamber State Animation: LAKE -> FILL -> STABILIZE -> MEASURE -> FLUSH")
    print("[*] Live Water Quality Telemetry: pH, EC/TDS, Turbidity, Water Temperature")
    print("[*] LoRa Shore Gateway Terminal with HMAC-SHA256 MIC & Replay Defense Testing")
    print("[*] USGS Lake Erie Historical Dataset: KNN-IDW (K=3) Spatial Interpolation")
    print("[*] Press Ctrl+C to terminate.")
    print("=" * 80)

    app.run(host=args.host, port=port, debug=args.debug, use_reloader=False)

if __name__ == "__main__":
    main()
