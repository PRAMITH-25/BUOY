"""
BuoySystem: Top-Level Autonomous Buoy Simulation Coordinator.
Ties together:
- Lake Environment
- Water Sensors & ADS1115
- Signal Processing & Navigation
- Chamber State Machine
- Solar & Battery Power Management
- LoRa Node & Shore Gateway
- ESP32-S3 Logical Tasks & Software Watchdog
"""
from typing import Dict, Any, Optional
from buoy_sim.core.events import ChamberState, SystemPowerMode
from buoy_sim.sensors.environment import LakeEnvironment
from buoy_sim.sensors.water_sensors import WaterSensors
from buoy_sim.sensors.ads1115 import ADS1115Emulator
from buoy_sim.sensors.navigation import NEO6MGps, MPU6050Imu
from buoy_sim.sensors.signal_filter import SignalFilter
from buoy_sim.chamber.state_machine import ChamberStateMachine
from buoy_sim.power.power_manager import PowerManager
from buoy_sim.lora.channel import LoRaChannelModel
from buoy_sim.lora.gateway import LoRaGateway
from buoy_sim.lora.buoy_node import BuoyLoRaNode
from buoy_sim.esp32.watchdog import SoftwareWatchdog
from buoy_sim.esp32.tasks import (
    SensorTask, ChamberTask, ProcessingTask, GPSTask, LoRaTask, PowerTask
)

class BuoySystem:
    def __init__(self, initial_soc_pct: float = 85.0):
        # Physical Environment & Sensors
        self.env = LakeEnvironment()
        self.water_sensors = WaterSensors()
        self.adc = ADS1115Emulator()
        self.gps = NEO6MGps()
        self.imu = MPU6050Imu()

        # Signal Processing
        self.filter = SignalFilter()

        # Chamber
        self.chamber = ChamberStateMachine()

        # Power
        self.power_mgr = PowerManager(initial_soc_pct=initial_soc_pct)

        # LoRa & Shore Gateway
        self.gateway = LoRaGateway()
        self.channel = LoRaChannelModel()
        self.lora_node = BuoyLoRaNode(gateway=self.gateway, channel=self.channel)

        # Watchdog
        self.watchdog = SoftwareWatchdog()

        # ESP32-S3 Logical Tasks
        self.sensor_task = SensorTask(self.water_sensors, self.adc)
        self.chamber_task = ChamberTask(self.chamber)
        self.proc_task = ProcessingTask(self.filter)
        self.gps_task = GPSTask(self.gps, self.imu)
        self.lora_task = LoRaTask(self.lora_node)
        self.power_task = PowerTask(self.power_mgr)

        # Simulation State
        self.sim_time_s = 3600.0 * 8.0  # Start at 08:00 AM
        self.telemetry_interval_s = 60.0 # Transmit telemetry every 60s
        self.time_since_last_tx_s = 0.0

        # Virtual 2D lake position
        self.buoy_x = self.env.buoy_x
        self.buoy_y = self.env.buoy_y

        # Most recent snapshot
        self.last_snapshot: Dict[str, Any] = {}

    def set_buoy_position(self, x: float, y: float) -> Dict[str, Any]:
        """Update virtual buoy position, GPS anchor, and local environmental conditions."""
        from buoy_sim.sensors.spatial_field import map_xy_to_lat_lon
        cx, cy = self.env.set_buoy_position(x, y)
        self.buoy_x = cx
        self.buoy_y = cy
        lat, lon = map_xy_to_lat_lon(cx, cy)
        self.gps.set_anchor(lat, lon)
        return {
            "buoy_x": self.buoy_x,
            "buoy_y": self.buoy_y,
            "latitude": lat,
            "longitude": lon,
            "zone_name": self.env.get_current_zone_name(),
            "zone_id": self.env.current_zone_id,
        }

    def step(self, dt_s: float = 1.0) -> Dict[str, Any]:
        """
        Execute one discrete simulation step of length dt_s seconds.
        """
        self.sim_time_s += dt_s
        self.time_since_last_tx_s += dt_s

        # 1. Update Lake Environment
        ground_truth = self.env.update(self.sim_time_s)

        # 2. Chamber Task & Watchdog Heartbeat
        self.watchdog.feed("ChamberTask", self.sim_time_s)
        chamber_diag = self.chamber_task.step(dt_s)
        is_isolated = self.chamber.is_isolated
        is_stabilized = self.chamber.fluid_stabilized

        # 3. Sensor Task
        self.watchdog.feed("SensorTask", self.sim_time_s)
        sensor_res = self.sensor_task.step(ground_truth, is_isolated, is_stabilized)
        voltages = sensor_res["raw_voltages"]
        temp_c = voltages.get("temp_c", 20.0)

        # 4. Processing Task
        self.watchdog.feed("ProcessingTask", self.sim_time_s)
        adc_voltages = sensor_res["adc_result"].get("voltages", {
            "v_ph": voltages["v_ph"], "v_ec": voltages["v_ec"], "v_turbidity": voltages["v_turbidity"]
        })
        proc_data = self.proc_task.step(adc_voltages, temp_c)

        # 5. GPS & IMU Task
        self.watchdog.feed("GPSTask", self.sim_time_s)
        nav_data = self.gps_task.step(
            self.sim_time_s, ground_truth["wave_height_m"], ground_truth["wave_period_s"]
        )

        # 6. LoRa Task: Transmit if scheduled or cycle completed
        self.watchdog.feed("LoRaTask", self.sim_time_s)
        tx_result = None
        is_transmitting = False

        should_transmit = (
            self.time_since_last_tx_s >= self.telemetry_interval_s or
            (chamber_diag["transitioned"] and chamber_diag["current_state"] == ChamberState.MEASURE.value)
        )

        if should_transmit:
            self.time_since_last_tx_s = 0.0
            is_transmitting = True

            filtered = proc_data["filtered"]
            telemetry_packet = {
                "timestamp": self.sim_time_s,
                "ph": filtered["ph"],
                "ec_us_cm": filtered["ec_us_cm"],
                "turbidity_ntu": filtered["turbidity_ntu"],
                "temp_c": filtered["temp_c"],
                "soc_pct": self.power_mgr.battery.soc_pct,
                "solar_power_mw": self.power_mgr.solar_panel.calculate_generation(
                    ground_truth["solar_irradiance_w_m2"], temp_c, ground_truth["hour_of_day"]
                )["solar_power_mw"],
                "latitude": nav_data["gps"]["latitude"],
                "longitude": nav_data["gps"]["longitude"],
                "chamber_state": chamber_diag["current_state"],
                "quality_flag": proc_data["quality_flag"],
            }
            tx_result = self.lora_task.step(telemetry_packet)

            # Process any downlink commands returned by gateway
            if tx_result and tx_result.get("downlink_command"):
                self._execute_downlink_command(tx_result["downlink_command"])

        # 7. Power Task
        self.watchdog.feed("PowerTask", self.sim_time_s)
        power_diag = self.power_task.step(
            dt_s=dt_s,
            irradiance_w_m2=ground_truth["solar_irradiance_w_m2"],
            temp_c=temp_c,
            hour_of_day=ground_truth["hour_of_day"],
            chamber_state=chamber_diag["current_state"],
            pump_active=chamber_diag["pump_active"],
            is_sampling=True,
            is_lora_tx=is_transmitting,
            is_lora_rx=is_transmitting,
            is_gps_tracking=True
        )

        # 8. Watchdog Monitoring & Self-Check
        wd_diag = self.watchdog.check(self.sim_time_s)

        # Package full diagnostic snapshot
        self.last_snapshot = {
            "sim_time_s": self.sim_time_s,
            "hour_of_day": ground_truth["hour_of_day"],
            "ground_truth": ground_truth,
            "spatial": {
                "buoy_x": self.buoy_x,
                "buoy_y": self.buoy_y,
                "zone_id": ground_truth.get("zone_id", "normal"),
                "zone_name": ground_truth.get("zone_name", "Normal Water (Main Lake Basin)"),
                "flow_speed_m_s": ground_truth.get("flow_speed_m_s", 0.18),
                "flow_direction_deg": ground_truth.get("flow_direction_deg", 0.0),
            },
            "chamber": chamber_diag,
            "sensors": proc_data,
            "navigation": nav_data,
            "power": power_diag,
            "lora": {
                "last_tx": tx_result,
                "node_stats": {
                    "total_transmitted": self.lora_node.total_transmitted,
                    "total_acked": self.lora_node.total_acked,
                    "total_dropped": self.lora_node.total_dropped,
                    "seq_num": self.lora_node.seq_num,
                },
                "gateway_stats": {
                    "accepted": self.gateway.total_packets_accepted,
                    "rejected": self.gateway.total_packets_rejected,
                    "mic_failures": self.gateway.mic_failures,
                    "replay_attempts": self.gateway.replay_attempts,
                }
            },
            "watchdog": wd_diag,
        }
        return self.last_snapshot

    def _execute_downlink_command(self, cmd_data: Dict[str, Any]):
        """Execute remote command received from Shore Gateway."""
        from buoy_sim.lora.packet import (
            CMD_TRIGGER_MEASUREMENT, CMD_CHANGE_INTERVAL, CMD_REQUEST_STATUS,
            CMD_INITIATE_CHAMBER, CMD_LOW_POWER_MODE
        )
        cmd_id = cmd_data.get("cmd_id")
        arg = cmd_data.get("cmd_arg", 0)

        if cmd_id == CMD_TRIGGER_MEASUREMENT or cmd_id == CMD_INITIATE_CHAMBER:
            self.chamber.request_manual_cycle()
        elif cmd_id == CMD_CHANGE_INTERVAL:
            if arg > 0:
                self.chamber.timing["lake_monitoring_interval_s"] = float(arg)
                self.telemetry_interval_s = min(60.0, float(arg))
        elif cmd_id == CMD_LOW_POWER_MODE:
            self.power_mgr.power_mode = SystemPowerMode.LIGHT_SLEEP
