"""
Flask Web Application & REST API for Solar-Powered Lake Monitoring Buoy Digital Prototype.
Provides:
- Real-time telemetry streaming and dashboard state
- LoRa Shore Gateway command terminal and security testing
- Interactive chamber state visualization
- Fault injection controls
- Research comparison experiment runner
- CSV exports for telemetry and experiment datasets
"""
import threading
import time
from typing import Dict, Any, List
from flask import Flask, render_template, jsonify, request, Response

from buoy_sim.esp32.system import BuoySystem
from buoy_sim.experiments.comparison import ComparisonExperiment, DEFAULT_EXPERIMENT_PARAMS
from buoy_sim.experiments.exporter import TelemetryExporter
from buoy_sim.lora.packet import (
    CMD_TRIGGER_MEASUREMENT, CMD_CHANGE_INTERVAL, CMD_REQUEST_STATUS,
    CMD_INITIATE_CHAMBER, CMD_LOW_POWER_MODE
)
from buoy_sim.core.location import get_location_config, set_location_config, get_nearby_stations
from buoy_sim.data.weather_client import get_weather_client
from buoy_sim.data.usgs_api_client import get_usgs_api_client

app = Flask(__name__)

# Global Simulation Instance
system = BuoySystem(initial_soc_pct=85.0)

# Simulation Engine State
sim_lock = threading.Lock()
is_running = True
speed_multiplier = 5.0  # Default 5x real-time speed
latest_comparison: Dict[str, Any] = {}
latest_comparison_logs: tuple = ([], [])

# Historical time-series buffers for graphs (max 300 points)
history_points: List[Dict[str, Any]] = []

# USGS Historical Replay Engine & LoRa Exchange Log
replay_active = False
replay_index = 0
replay_last_tick = time.time()
weather_last_sync = 0.0
lora_exchange_log: List[Dict[str, Any]] = []

def background_sim_loop():
    """Background simulation thread running time steps."""
    global is_running, speed_multiplier, history_points, replay_active, replay_index, replay_last_tick, weather_last_sync
    last_wall_time = time.time()

    while True:
        now = time.time()
        wall_dt = now - last_wall_time
        last_wall_time = now

        if is_running:
            # Sync real Open-Meteo weather every 5 minutes (cached with 10m TTL)
            if now - weather_last_sync >= 300.0:
                weather_last_sync = now
                try:
                    w_client = get_weather_client()
                    with sim_lock:
                        lat, lon = system.gps.latitude, system.gps.longitude
                    w_data = w_client.get_weather(lat, lon)
                    with sim_lock:
                        system.env.apply_weather_data(w_data)
                except Exception:
                    pass
            # Advance USGS Historical Data Replay if active
            if replay_active and (now - replay_last_tick >= max(0.4, 2.0 / max(0.5, speed_multiplier * 0.4))):
                replay_last_tick = now
                with sim_lock:
                    loader = system.env._usgs_loader
                    if loader and loader.valid_records:
                        replay_index = (replay_index + 1) % len(loader.valid_records)
                        rec = loader.get_replay_record(replay_index)
                        from buoy_sim.data.usgs_loader import usgs_latlon_to_map_xy
                        bx, by = usgs_latlon_to_map_xy(rec["latitude"], rec["longitude"])
                        system.set_buoy_position(bx, by)

            # Advance simulation by wall_dt * speed_multiplier
            sim_dt = min(30.0, max(0.5, wall_dt * speed_multiplier))
            with sim_lock:
                snap = system.step(sim_dt)

                # Record any LoRa transmission event
                if snap.get("lora") and snap["lora"].get("last_tx"):
                    tx = snap["lora"]["last_tx"]
                    seq = tx.get("seq_num")
                    if not lora_exchange_log or lora_exchange_log[-1].get("seq_num") != seq:
                        t_str = time.strftime("%H:%M:%S")
                        pkt = tx.get("packet_dict", {}).get("plaintext", {})
                        usgs_t = snap.get("ground_truth", {}).get("usgs", {}).get("nearest_record_timestamp", t_str)
                        lora_exchange_log.append({
                            "time_str": t_str,
                            "direction": "BUOY-01 → GATEWAY",
                            "event": f"DATA #{seq:04d}",
                            "seq_num": seq,
                            "status": "ACCEPTED" if tx.get("acked") else "TRANSMITTED",
                            "ph": pkt.get("ph", snap["sensors"]["filtered"]["ph"]),
                            "ec": pkt.get("ec_us_cm", snap["sensors"]["filtered"]["ec_us_cm"]),
                            "turb": pkt.get("turbidity_ntu", snap["sensors"]["filtered"]["turbidity_ntu"]),
                            "temp": pkt.get("temp_c", snap["sensors"]["filtered"]["temp_c"]),
                            "lat": snap.get("ground_truth", {}).get("usgs_latitude", 41.5796),
                            "lon": snap.get("ground_truth", {}).get("usgs_longitude", -81.5792),
                            "usgs_timestamp": usgs_t,
                            "ack_str": f"ACK #{seq:04d}" if tx.get("acked") else "--",
                            "node": "BUOY-01"
                        })
                        if len(lora_exchange_log) > 60:
                            lora_exchange_log.pop(0)

                # Append to history buffer
                hist_entry = {
                    "sim_time_s": snap["sim_time_s"],
                    "time_str": time.strftime("%H:%M:%S", time.gmtime(snap["sim_time_s"])),
                    "hour_of_day": round(snap["hour_of_day"], 2),
                    "ph": snap["sensors"]["filtered"]["ph"],
                    "turbidity_ntu": snap["sensors"]["filtered"]["turbidity_ntu"],
                    "ec_us_cm": snap["sensors"]["filtered"]["ec_us_cm"],
                    "temp_c": snap["sensors"]["filtered"]["temp_c"],
                    "soc_pct": snap["power"]["battery"]["soc_pct"],
                    "voltage_v": snap["power"]["battery"]["voltage_v"],
                    "solar_mw": snap["power"]["solar_power_mw"],
                    "load_mw": snap["power"]["load_power_mw"],
                    "chamber_state": snap["chamber"]["current_state"],
                }
                history_points.append(hist_entry)
                if len(history_points) > 300:
                    history_points.pop(0)

        time.sleep(0.15)  # ~6.6 updates per second

# Start background simulation worker
worker_thread = threading.Thread(target=background_sim_loop, daemon=True)
worker_thread.start()

# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
    with sim_lock:
        snap = system.last_snapshot or system.step(0.1)
        snap["is_running"] = is_running
        snap["speed_multiplier"] = speed_multiplier
        snap["usgs_info"] = system.env.usgs_info

        # Add USGS Contributors and Percentiles
        loader = system.env._usgs_loader
        usgs_cond = system.env.get_usgs_conditions(system.buoy_x, system.buoy_y)
        snap["usgs_data"] = usgs_cond
        snap["contributors"] = usgs_cond.get("contributors", [])
        if loader:
            snap["percentiles"] = {
                "ph": loader.get_percentile("ph", usgs_cond["ph"]),
                "ec_us_cm": loader.get_percentile("ec_us_cm", usgs_cond["ec_us_cm"]),
                "turbidity_ntu": loader.get_percentile("turbidity_ntu", usgs_cond["turbidity_ntu"]),
                "water_temp_c": loader.get_percentile("water_temp_c", usgs_cond["water_temp_c"]),
            }
        else:
            snap["percentiles"] = {"ph": 50, "ec_us_cm": 50, "turbidity_ntu": 50, "water_temp_c": 50}

        snap["replay"] = {
            "active": replay_active,
            "index": replay_index,
            "total_records": len(loader.valid_records) if (loader and loader.valid_records) else 0,
        }
        snap["lora_exchange"] = list(lora_exchange_log)[-20:]

        # Real Location & Weather Integration
        loc = get_location_config()
        snap["location"] = {
            "water_body_name": loc.get("water_body_name"),
            "region": loc.get("region"),
            "latitude": system.gps.latitude,
            "longitude": system.gps.longitude,
        }
        w_client = get_weather_client()
        w_data = w_client._cache or {}
        snap["weather_summary"] = {
            "air_temperature_c": w_data.get("air_temperature_c"),
            "precipitation_mm": w_data.get("precipitation_mm", 0.0),
            "rain_mm": w_data.get("rain_mm", 0.0),
            "wind_speed_m_s": w_data.get("wind_speed_m_s"),
            "wind_direction_deg": w_data.get("wind_direction_deg"),
            "cloud_cover_pct": w_data.get("cloud_cover_pct"),
            "shortwave_radiation_w_m2": w_data.get("shortwave_radiation_w_m2"),
            "status": w_data.get("status", "REAL_API_DATA" if w_data else "OFFLINE_FALLBACK"),
            "source": w_data.get("source", "Open-Meteo Weather API"),
            "observation_time": w_data.get("observation_time"),
        }
        return jsonify(snap)

@app.route("/api/usgs/info", methods=["GET"])
def get_usgs_info():
    """Return USGS dataset summary (measurement count, valid count, bounds, ranges)."""
    with sim_lock:
        return jsonify(system.env.usgs_info)

@app.route("/api/usgs/grid", methods=["GET"])
def get_usgs_grid():
    """Return 2D interpolated grid of real USGS measurements across the lake map."""
    param = request.args.get("param", "turbidity_ntu")
    try:
        cols = max(10, min(100, int(request.args.get("cols", 50))))
        rows = max(10, min(60, int(request.args.get("rows", 30))))
    except ValueError:
        cols, rows = 50, 30
    with sim_lock:
        return jsonify(system.env.get_spatial_grid(param, cols, rows))

@app.route("/api/history", methods=["GET"])
def get_history():
    with sim_lock:
        return jsonify(history_points[-120:])

@app.route("/api/control/play", methods=["POST"])
def play_sim():
    global is_running
    is_running = True
    return jsonify({"status": "RUNNING"})

@app.route("/api/control/pause", methods=["POST"])
def pause_sim():
    global is_running
    is_running = False
    return jsonify({"status": "PAUSED"})

@app.route("/api/control/step", methods=["POST"])
def step_sim():
    with sim_lock:
        dt = float(request.json.get("dt_s", 2.0)) if request.is_json else 2.0
        snap = system.step(dt)
        return jsonify(snap)

@app.route("/api/control/speed", methods=["POST"])
def set_speed():
    global speed_multiplier
    speed = float(request.json.get("speed", 5.0)) if request.is_json else 5.0
    speed_multiplier = max(0.5, min(60.0, speed))
    return jsonify({"speed_multiplier": speed_multiplier})

@app.route("/api/control/weather", methods=["POST"])
def set_weather():
    with sim_lock:
        w_type = request.json.get("weather", "CLEAR") if request.is_json else "CLEAR"
        if w_type == "RAIN_RUNOFF":
            system.env.trigger_rain_runoff(intensity=0.85)
        else:
            system.env.clear_weather()
        return jsonify({"weather": system.env.weather, "rain_intensity": system.env.rain_intensity})

@app.route("/api/control/buoy_position", methods=["POST"])
@app.route("/api/buoy/position", methods=["POST"])
def set_buoy_position():
    with sim_lock:
        data = request.get_json(silent=True) or request.form or {}
        if "latitude" in data and "longitude" in data:
            lat = float(data["latitude"])
            lon = float(data["longitude"])
            pos_info = system.set_buoy_lat_lon(lat, lon)
        else:
            x = float(data.get("x", 500.0))
            y = float(data.get("y", 300.0))
            pos_info = system.set_buoy_position(x, y)

        snap = system.step(0.0)
        # Query USGS data for the new buoy position
        usgs_data = system.env.get_usgs_conditions(system.buoy_x, system.buoy_y)
        return jsonify({
            "status": "POSITION_UPDATED",
            "buoy_x": system.buoy_x,
            "buoy_y": system.buoy_y,
            "zone_id": pos_info.get("zone_id", "normal"),
            "zone_name": pos_info["zone_name"],
            "latitude": pos_info["latitude"],
            "longitude": pos_info["longitude"],
            "sensors": snap["sensors"],
            "ground_truth": snap["ground_truth"],
            "spatial": snap["spatial"],
            "usgs_data": usgs_data,
        })

@app.route("/api/control/command", methods=["POST"])
def send_command():
    with sim_lock:
        cmd_str = request.json.get("command", "") if request.is_json else ""
        arg = int(request.json.get("arg", 0)) if request.is_json else 0

        cmd_map = {
            "trigger_measurement": CMD_TRIGGER_MEASUREMENT,
            "change_sampling_interval": CMD_CHANGE_INTERVAL,
            "request_status": CMD_REQUEST_STATUS,
            "initiate_chamber_cycle": CMD_INITIATE_CHAMBER,
            "enter_low_power_mode": CMD_LOW_POWER_MODE,
        }
        cmd_id = cmd_map.get(cmd_str)
        if cmd_id is None:
            return jsonify({"error": f"Unknown command: {cmd_str}"}), 400

        cmd_info = system.gateway.queue_downlink_command(cmd_id, arg)
        t_str = time.strftime("%H:%M:%S")

        # Downlink command entry
        lora_exchange_log.append({
            "time_str": t_str,
            "direction": "GATEWAY → BUOY-01",
            "event": f"CMD #{cmd_info['gateway_seq']}: {cmd_str.upper()}",
            "seq_num": cmd_info["gateway_seq"],
            "status": "QUEUED_DOWNLINK",
            "ph": "--", "ec": "--", "turb": "--", "temp": "--",
            "lat": "--", "lon": "--",
            "usgs_timestamp": t_str,
            "ack_str": "ACK (PENDING)",
            "node": "GATEWAY"
        })

        # Immediately execute and record ACK so user sees the complete round trip
        if cmd_id in (CMD_TRIGGER_MEASUREMENT, CMD_INITIATE_CHAMBER):
            system.chamber.request_manual_cycle()
            ack_msg = "CHAMBER_CYCLE_TRIGGERED"
        elif cmd_id == CMD_CHANGE_INTERVAL:
            system.telemetry_interval_s = float(arg)
            ack_msg = f"INTERVAL_SET_{arg}S"
        else:
            ack_msg = "STATUS_REPORT_OK"

        lora_exchange_log.append({
            "time_str": t_str,
            "direction": "BUOY-01 → GATEWAY",
            "event": f"ACK #{cmd_info['gateway_seq']}: {ack_msg}",
            "seq_num": cmd_info["gateway_seq"],
            "status": "EXECUTED",
            "ph": "--", "ec": "--", "turb": "--", "temp": "--",
            "lat": "--", "lon": "--",
            "usgs_timestamp": t_str,
            "ack_str": "ACK_CONFIRMED",
            "node": "BUOY-01"
        })

        return jsonify({"status": "QUEUED_AND_ACKED", "command_info": cmd_info, "ack": ack_msg})

@app.route("/api/usgs/contributors", methods=["GET"])
def get_usgs_contributors():
    with sim_lock:
        x = float(request.args.get("x", system.buoy_x))
        y = float(request.args.get("y", system.buoy_y))
        cond = system.env.get_usgs_conditions(x, y)
        loader = system.env._usgs_loader
        percentiles = {}
        if loader:
            percentiles = {
                "ph": loader.get_percentile("ph", cond["ph"]),
                "ec_us_cm": loader.get_percentile("ec_us_cm", cond["ec_us_cm"]),
                "turbidity_ntu": loader.get_percentile("turbidity_ntu", cond["turbidity_ntu"]),
                "water_temp_c": loader.get_percentile("water_temp_c", cond["water_temp_c"]),
            }
        return jsonify({
            "buoy_x": x,
            "buoy_y": y,
            "latitude": cond.get("latitude"),
            "longitude": cond.get("longitude"),
            "ph": cond.get("ph"),
            "ec_us_cm": cond.get("ec_us_cm"),
            "turbidity_ntu": cond.get("turbidity_ntu"),
            "water_temp_c": cond.get("water_temp_c"),
            "timestamp": cond.get("nearest_record_timestamp"),
            "lookup_method": cond.get("lookup_method", "KNN-IDW (K=3)"),
            "contributors": cond.get("contributors", []),
            "percentiles": percentiles,
        })

@app.route("/api/usgs/replay", methods=["GET", "POST"])
@app.route("/api/usgs/replay/record", methods=["GET"])
def usgs_replay():
    global replay_active, replay_index
    loader = system.env._usgs_loader
    total = len(loader.valid_records) if (loader and loader.valid_records) else 0

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        action = data.get("action", "")
        with sim_lock:
            if action == "play":
                replay_active = True
            elif action == "pause":
                replay_active = False
            elif action == "reset":
                replay_active = False
                replay_index = 0
            elif action == "next":
                if total > 0:
                    replay_index = (replay_index + 1) % total
            elif action == "prev":
                if total > 0:
                    replay_index = (replay_index - 1 + total) % total
            elif action == "goto":
                idx = int(data.get("index", 0))
                if total > 0:
                    replay_index = max(0, min(idx, total - 1))

            # Apply current record to buoy
            if loader and loader.valid_records:
                rec = loader.get_replay_record(replay_index)
                from buoy_sim.data.usgs_loader import usgs_latlon_to_map_xy
                bx, by = usgs_latlon_to_map_xy(rec["latitude"], rec["longitude"])
                system.set_buoy_position(bx, by)
                snap = system.step(0.0)

    # Return current replay status and record
    rec = loader.get_replay_record(replay_index) if (loader and loader.valid_records) else {}
    return jsonify({
        "active": replay_active,
        "index": replay_index,
        "total_records": total,
        "record": rec,
    })

@app.route("/api/usgs/timeseries", methods=["GET"])
def usgs_timeseries():
    param = request.args.get("param", "turbidity_ntu")
    start = int(request.args.get("start", max(0, replay_index - 20)))
    count = int(request.args.get("count", 50))
    loader = system.env._usgs_loader
    if not loader:
        return jsonify([])
    return jsonify(loader.get_chronological_timeseries(param, start, count))

@app.route("/api/lora/exchange", methods=["GET"])
def get_lora_exchange():
    with sim_lock:
        return jsonify({
            "log": list(lora_exchange_log)[-30:],
            "total_sent": system.lora_node.total_transmitted,
            "total_acked": system.lora_node.total_acked,
        })

@app.route("/api/control/fault", methods=["POST"])
def inject_fault():
    with sim_lock:
        fault_type = request.json.get("fault_type", "") if request.is_json else ""
        enable = bool(request.json.get("enable", True)) if request.is_json else True

        if fault_type == "sensor_disconnect":
            system.water_sensors.fault_sensor_disconnect = enable
        elif fault_type == "i2c_hang":
            system.adc.fault_i2c_bus_hang = enable
        elif fault_type == "pump_stall":
            system.chamber.fault_pump_stall = enable
        elif fault_type == "lora_loss":
            system.channel.fault_forced_packet_loss = enable
        elif fault_type == "gps_lost":
            system.gps.fault_lock_lost = enable
        elif fault_type == "task_freeze":
            task_name = request.json.get("task_name", "SensorTask")
            if enable:
                system.watchdog.inject_task_freeze(task_name)
            else:
                system.watchdog.clear_task_freeze(task_name)
        else:
            return jsonify({"error": f"Unknown fault type: {fault_type}"}), 400

        return jsonify({"status": "FAULT_UPDATED", "fault_type": fault_type, "enabled": enable})

@app.route("/api/control/security_test", methods=["POST"])
def security_test():
    with sim_lock:
        test_type = request.json.get("test_type", "tamper") if request.is_json else "tamper"

        if test_type == "tamper":
            res = system.lora_node.simulate_tampered_packet({"timestamp": system.sim_time_s})
            return jsonify({
                "test": "TAMPER_DETECTION",
                "result": res,
                "expected": "Gateway rejected packet with MIC_VERIFICATION_FAILED_INTEGRITY_COMPROMISED",
                "success": (res["gw_status"] == "REJECTED" and "MIC" in str(res["gw_error"])),
            })
        elif test_type == "replay":
            res = system.lora_node.simulate_replay_attack(old_seq=max(1, system.lora_node.seq_num - 5))
            return jsonify({
                "test": "REPLAY_ATTACK_DETECTION",
                "result": res,
                "expected": "Gateway rejected packet with REPLAY_ATTACK_DETECTED",
                "success": (res["gw_status"] == "REJECTED" and "REPLAY" in str(res["gw_error"])),
            })
        return jsonify({"error": "Unknown test type"}), 400

@app.route("/api/experiment/run", methods=["POST"])
def run_experiment():
    global latest_comparison, latest_comparison_logs
    data = request.get_json(silent=True) or {}
    duration_s = float(data.get("duration_s", 1800.0))

    # Extract configurable chamber/experiment parameters from request
    exp_params = {}
    for key in DEFAULT_EXPERIMENT_PARAMS:
        if key in data and data[key] is not None:
            try:
                val = data[key]
                if key == "pump_energy_j_override" and val == "":
                    val = None
                exp_params[key] = float(val) if val is not None else None
            except (ValueError, TypeError):
                pass  # Use default if parsing fails

    exp = ComparisonExperiment(duration_s=duration_s, step_s=2.0, params=exp_params if exp_params else None)
    summary = exp.run()

    with sim_lock:
        latest_comparison = summary
        latest_comparison_logs = (exp.logs_a, exp.logs_b)

    return jsonify(summary)


@app.route("/api/power", methods=["GET"])
def get_power():
    """Return compact power subsystem status for the dashboard power panel."""
    with sim_lock:
        snap = system.last_snapshot or system.step(0.1)
        pwr = snap.get("power", {})
        bat = pwr.get("battery", {})
        return jsonify({
            "solar_power_mw": pwr.get("solar_power_mw", 0.0),
            "solar_irradiance_w_m2": pwr.get("solar_irradiance_w_m2", 0.0),
            "load_power_mw": pwr.get("load_power_mw", 0.0),
            "net_power_mw": pwr.get("net_power_mw", 0.0),
            "soc_pct": bat.get("soc_pct", 0.0),
            "voltage_v": bat.get("voltage_v", 0.0),
            "remaining_wh": bat.get("remaining_wh", 0.0),
            "estimated_endurance_days": pwr.get("estimated_endurance_days", 0.0),
            "estimated_endurance_hours": pwr.get("estimated_endurance_hours", 0.0),
            "power_mode": pwr.get("power_mode", "ACTIVE"),
            "chamber_cycle_energy_mwh": pwr.get("chamber_cycle_energy_mwh", 0.0),
            "currents_ma": pwr.get("currents_ma", {}),
            "total_consumed_wh": pwr.get("total_consumed_wh", 0.0),
            "total_harvested_wh": pwr.get("total_harvested_wh", 0.0),
        })


@app.route("/api/experiment/defaults", methods=["GET"])
def get_experiment_defaults():
    """Return default experiment parameters for the dashboard."""
    return jsonify(DEFAULT_EXPERIMENT_PARAMS)


@app.route("/api/map", methods=["GET"])
def get_map():
    """Return map configuration, bounding coordinates, and current buoy GPS coordinates."""
    loc = get_location_config()
    with sim_lock:
        return jsonify({
            "water_body_name": loc["water_body_name"],
            "region": loc["region"],
            "center": {
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
            },
            "buoy": {
                "latitude": system.gps.latitude,
                "longitude": system.gps.longitude,
                "buoy_x": system.buoy_x,
                "buoy_y": system.buoy_y,
            },
            "zoom": loc["zoom"],
            "bounds": loc["bounds"],
            "tile_provider": {
                "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
                "max_zoom": 19,
            },
            "status": "REAL_MAP_ACTIVE",
            "nearby_stations_count": len(get_nearby_stations()),
        })


@app.route("/api/environment", methods=["GET"])
def get_environment():
    """Return unified environmental conditions (weather, spatial zone, water baseline)."""
    loc = get_location_config()
    w_client = get_weather_client()
    with sim_lock:
        lat = system.gps.latitude
        lon = system.gps.longitude
        w_data = w_client.get_weather(lat, lon)
        usgs_cond = system.env.get_usgs_conditions(system.buoy_x, system.buoy_y)
        return jsonify({
            "location": loc,
            "buoy_position": {
                "latitude": lat,
                "longitude": lon,
                "buoy_x": system.buoy_x,
                "buoy_y": system.buoy_y,
                "zone_id": system.env.current_zone_id,
                "zone_name": system.env.get_current_zone_name(),
                "flow_speed_m_s": getattr(system.env.spatial_field, 'base_flow_speed', 0.0),
            },
            "weather": w_data,
            "water_baseline": {
                "ph": usgs_cond.get("ph"),
                "ec_us_cm": usgs_cond.get("ec_us_cm"),
                "turbidity_ntu": usgs_cond.get("turbidity_ntu"),
                "water_temp_c": usgs_cond.get("water_temp_c"),
                "data_source": usgs_cond.get("data_source_label", "USGS HISTORICAL DATA"),
                "timestamp": usgs_cond.get("nearest_record_timestamp"),
            },
            "simulation_note": "Weather and water baseline are external environmental inputs driving virtual buoy sensors.",
        })


@app.route("/api/weather", methods=["GET"])
def get_weather():
    """Return live weather from Open-Meteo API (or cached/fallback)."""
    force = request.args.get("refresh", "false").lower() == "true"
    with sim_lock:
        lat = system.gps.latitude
        lon = system.gps.longitude
    w_client = get_weather_client()
    weather = w_client.get_weather(lat, lon, force_refresh=force)
    with sim_lock:
        system.env.apply_weather_data(weather)
    return jsonify(weather)


@app.route("/api/water-data", methods=["GET"])
def get_water_data():
    """Return USGS Water Services API real-time observation data (or cached/fallback)."""
    force = request.args.get("refresh", "false").lower() == "true"
    with sim_lock:
        lat = system.gps.latitude
        lon = system.gps.longitude
    api_client = get_usgs_api_client()
    data = api_client.get_water_data(force_refresh=force, buoy_lat=lat, buoy_lon=lon)
    return jsonify(data)


@app.route("/api/stations", methods=["GET"])
def get_stations():
    """Return nearby water-quality monitoring stations with coordinates and available parameters."""
    stations = get_nearby_stations()
    return jsonify({
        "count": len(stations),
        "stations": stations,
        "demonstration_site": get_location_config()["water_body_name"],
        "source": "USGS National Water Information System",
    })


@app.route("/api/location/config", methods=["GET", "POST"])
def location_config():
    """Get or update demonstration location."""
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        lat = float(data.get("latitude", 41.57963))
        lon = float(data.get("longitude", -81.57919))
        name = data.get("water_body_name")
        updated = set_location_config(lat, lon, name)
        with sim_lock:
            system.set_buoy_lat_lon(lat, lon)
        return jsonify({"status": "LOCATION_UPDATED", "config": updated})
    return jsonify(get_location_config())


@app.route("/api/export/telemetry.csv", methods=["GET"])
def export_telemetry_csv():
    with sim_lock:
        records = list(system.gateway.telemetry_history)
        if not records and history_points:
            records = [{
                "timestamp": h["sim_time_s"],
                "seq_num": i + 1,
                "ph": h["ph"],
                "ec_us_cm": h["ec_us_cm"],
                "turbidity_ntu": h["turbidity_ntu"],
                "temp_c": h["temp_c"],
                "soc_pct": h["soc_pct"],
                "solar_power_mw": h["solar_mw"],
                "latitude": 42.5872,
                "longitude": -88.4334,
                "chamber_state": h["chamber_state"],
                "quality_flag": "VALID",
            } for i, h in enumerate(history_points)]

        csv_content = TelemetryExporter.export_telemetry_csv(records)
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=buoy_telemetry_sim.csv"}
        )

@app.route("/api/export/comparison.csv", methods=["GET"])
def export_comparison_csv():
    with sim_lock:
        logs_a, logs_b = latest_comparison_logs
        if not logs_a or not logs_b:
            exp = ComparisonExperiment(duration_s=600.0, step_s=2.0)
            exp.run()
            logs_a, logs_b = exp.logs_a, exp.logs_b

        csv_content = TelemetryExporter.export_comparison_csv(logs_a, logs_b)
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=buoy_open_vs_chamber_comparison.csv"}
        )
