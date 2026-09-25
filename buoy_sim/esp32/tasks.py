"""
ESP32-S3 Logical Tasks:
- SensorTask: Manages ADS1115 and temperature acquisition
- ChamberTask: Governs flow-through chamber state transitions
- ProcessingTask: Runs median/moving-average filters and calibrations
- GPSTask: Handles NEO-6M GPS updates and mooring drift
- LoRaTask: Assembles packets and transmits to Shore Gateway
- PowerTask: Controls power modes and solar/battery balance
"""
from typing import Dict, Any, Optional
from buoy_sim.core.events import TaskState, ChamberState, SystemPowerMode
from buoy_sim.sensors.ads1115 import ADS1115Emulator
from buoy_sim.sensors.water_sensors import WaterSensors
from buoy_sim.sensors.navigation import NEO6MGps, MPU6050Imu
from buoy_sim.sensors.signal_filter import SignalFilter
from buoy_sim.chamber.state_machine import ChamberStateMachine
from buoy_sim.power.power_manager import PowerManager
from buoy_sim.lora.buoy_node import BuoyLoRaNode
from buoy_sim.lora.gateway import LoRaGateway
from buoy_sim.esp32.watchdog import SoftwareWatchdog

class SensorTask:
    def __init__(self, sensors: WaterSensors, adc: ADS1115Emulator):
        self.sensors = sensors
        self.adc = adc
        self.state = TaskState.IDLE
        self.last_raw_voltages: Dict[str, float] = {}
        self.last_adc_result: Dict[str, Any] = {}

    def step(self, ground_truth: Dict[str, Any], is_isolated: bool, is_stabilized: bool) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        self.last_raw_voltages = self.sensors.generate_analog_voltages(
            ground_truth, is_chamber_isolated=is_isolated, chamber_stabilized=is_stabilized
        )
        self.last_adc_result = self.adc.sample_all_channels(self.last_raw_voltages)
        self.state = TaskState.IDLE
        return {
            "raw_voltages": self.last_raw_voltages,
            "adc_result": self.last_adc_result,
        }

class ChamberTask:
    def __init__(self, chamber: ChamberStateMachine):
        self.chamber = chamber
        self.state = TaskState.IDLE

    def step(self, dt_s: float) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        res = self.chamber.update(dt_s)
        self.state = TaskState.IDLE
        return res

class ProcessingTask:
    def __init__(self, signal_filter: SignalFilter):
        self.filter = signal_filter
        self.state = TaskState.IDLE
        self.last_processed: Dict[str, Any] = {}

    def step(self, voltages: Dict[str, float], temp_c: float) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        self.last_processed = self.filter.process_adc_voltages(voltages, temp_c)
        self.state = TaskState.IDLE
        return self.last_processed

class GPSTask:
    def __init__(self, gps: NEO6MGps, imu: MPU6050Imu):
        self.gps = gps
        self.imu = imu
        self.state = TaskState.IDLE
        self.last_gps: Dict[str, Any] = {}
        self.last_imu: Dict[str, Any] = {}

    def step(self, sim_time_s: float, wave_height_m: float, wave_period_s: float) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        self.last_gps = self.gps.update(sim_time_s)
        self.last_imu = self.imu.update(sim_time_s, wave_height_m, wave_period_s)
        self.state = TaskState.IDLE
        return {"gps": self.last_gps, "imu": self.last_imu}

class LoRaTask:
    def __init__(self, buoy_node: BuoyLoRaNode):
        self.node = buoy_node
        self.state = TaskState.IDLE
        self.last_tx_result: Optional[Dict[str, Any]] = None

    def step(self, telemetry_payload: Dict[str, Any]) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        self.last_tx_result = self.node.transmit_telemetry(telemetry_payload)
        self.state = TaskState.IDLE
        return self.last_tx_result

class PowerTask:
    def __init__(self, power_manager: PowerManager):
        self.pm = power_manager
        self.state = TaskState.IDLE
        self.last_power_result: Dict[str, Any] = {}

    def step(
        self,
        dt_s: float,
        irradiance_w_m2: float,
        temp_c: float,
        hour_of_day: float,
        chamber_state: str,
        pump_active: bool,
        is_sampling: bool,
        is_lora_tx: bool,
        is_lora_rx: bool,
        is_gps_tracking: bool
    ) -> Dict[str, Any]:
        self.state = TaskState.RUNNING
        self.last_power_result = self.pm.update(
            dt_s, irradiance_w_m2, temp_c, hour_of_day,
            chamber_state, pump_active, is_sampling,
            is_lora_tx, is_lora_rx, is_gps_tracking
        )
        self.state = TaskState.IDLE
        return self.last_power_result
