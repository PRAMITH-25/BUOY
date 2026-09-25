"""
Power Management & Subsystem Energy Accounting.
Tracks ESP32-S3 power modes (Active, Modem-sleep, Light-sleep, Deep-sleep),
sensor power, pump power, LoRa power, and estimates battery endurance.
"""
from typing import Dict, Any, Optional
from buoy_sim.core.events import SystemPowerMode, ChamberState
from buoy_sim.core.config import POWER_CONSUMPTION_MA
from buoy_sim.power.solar_model import SolarPanelModel
from buoy_sim.power.battery_model import BatteryModel

class PowerManager:
    def __init__(self, initial_soc_pct: float = 85.0):
        self.solar_panel = SolarPanelModel()
        self.battery = BatteryModel(initial_soc_pct=initial_soc_pct)
        self.power_mode = SystemPowerMode.ACTIVE

        # Energy metrics
        self.total_energy_consumed_j = 0.0
        self.total_solar_harvested_j = 0.0
        self.chamber_cycle_energy_j = 0.0

        # Moving average of net power for endurance estimation
        self.avg_power_consumption_mw = 48.0

    def calculate_subsystem_current_ma(
        self,
        power_mode: SystemPowerMode,
        chamber_state: str,
        pump_active: bool,
        is_sampling: bool,
        is_lora_tx: bool,
        is_lora_rx: bool,
        is_gps_tracking: bool
    ) -> Dict[str, float]:
        """
        Compute current draw breakdown across all buoy subsystems.
        """
        # 1. ESP32-S3 CPU
        if power_mode == SystemPowerMode.ACTIVE:
            cpu_ma = POWER_CONSUMPTION_MA["esp32_active"]
        elif power_mode == SystemPowerMode.MODEM_SLEEP:
            cpu_ma = POWER_CONSUMPTION_MA["esp32_modem_sleep"]
        elif power_mode == SystemPowerMode.LIGHT_SLEEP:
            cpu_ma = POWER_CONSUMPTION_MA["esp32_light_sleep"]
        else: # DEEP_SLEEP
            cpu_ma = POWER_CONSUMPTION_MA["esp32_deep_sleep"]

        # 2. Sensors & ADC
        if is_sampling:
            sensors_ma = POWER_CONSUMPTION_MA["ads1115_active"] + POWER_CONSUMPTION_MA["sensors_analog_active"]
        else:
            sensors_ma = 0.02  # quiescent / off

        # 3. GPS & IMU
        gps_ma = POWER_CONSUMPTION_MA["gps_active"] if is_gps_tracking else POWER_CONSUMPTION_MA["gps_standby"]
        imu_ma = POWER_CONSUMPTION_MA["mpu6050_active"] if power_mode == SystemPowerMode.ACTIVE else 0.05

        # 4. Chamber Micro-Pump (5V boost regulator, ~280mA @ 5V -> ~420mA @ 3.3V equivalent)
        pump_ma = (POWER_CONSUMPTION_MA["pump_active_5v"] * 5.0 / 3.70) if pump_active else 0.0

        # 5. LoRa Radio
        if is_lora_tx:
            lora_ma = POWER_CONSUMPTION_MA["lora_tx"]
        elif is_lora_rx:
            lora_ma = POWER_CONSUMPTION_MA["lora_rx"]
        else:
            lora_ma = POWER_CONSUMPTION_MA["lora_sleep"]

        total_ma = cpu_ma + sensors_ma + gps_ma + imu_ma + pump_ma + lora_ma

        return {
            "cpu_ma": round(cpu_ma, 2),
            "sensors_ma": round(sensors_ma, 2),
            "gps_ma": round(gps_ma, 2),
            "imu_ma": round(imu_ma, 2),
            "pump_ma": round(pump_ma, 2),
            "lora_ma": round(lora_ma, 2),
            "total_ma": round(total_ma, 2),
        }

    def update(
        self,
        dt_s: float,
        solar_irradiance_w_m2: float,
        ambient_temp_c: float,
        hour_of_day: float,
        chamber_state: str,
        pump_active: bool,
        is_sampling: bool,
        is_lora_tx: bool,
        is_lora_rx: bool,
        is_gps_tracking: bool
    ) -> Dict[str, Any]:
        """
        Advance power simulation step.
        """
        # Solar generation
        solar_diag = self.solar_panel.calculate_generation(
            solar_irradiance_w_m2, ambient_temp_c, hour_of_day
        )
        solar_charge_ma = solar_diag["solar_current_ma_at_3v7"]

        # Subsystem currents
        currents = self.calculate_subsystem_current_ma(
            self.power_mode, chamber_state, pump_active,
            is_sampling, is_lora_tx, is_lora_rx, is_gps_tracking
        )
        load_current_ma = currents["total_ma"]

        # Battery update
        bat_diag = self.battery.update(dt_s, load_current_ma, solar_charge_ma)
        v_bat = bat_diag["voltage_v"]

        # Power & Energy accounting
        p_load_mw = load_current_ma * v_bat
        p_solar_mw = solar_diag["solar_power_mw"]
        delta_energy_consumed_j = (p_load_mw / 1000.0) * dt_s
        delta_solar_harvested_j = (p_solar_mw / 1000.0) * dt_s

        self.total_energy_consumed_j += delta_energy_consumed_j
        self.total_solar_harvested_j += delta_solar_harvested_j

        if chamber_state != ChamberState.LAKE_MONITORING.value:
            self.chamber_cycle_energy_j += delta_energy_consumed_j
        elif pump_active == False and chamber_state == ChamberState.LAKE_MONITORING.value and self.chamber_cycle_energy_j > 0:
            # Cycle just finished, keep cycle energy for diagnostics then reset on next start
            pass

        # Update average power with exponential decay
        self.avg_power_consumption_mw = 0.99 * self.avg_power_consumption_mw + 0.01 * p_load_mw

        # Estimated endurance on remaining battery without solar
        remaining_wh = bat_diag["remaining_wh"]
        avg_watts = max(0.02, self.avg_power_consumption_mw / 1000.0)
        endurance_hours = remaining_wh / avg_watts
        endurance_days = endurance_hours / 24.0

        return {
            "power_mode": self.power_mode.value,
            "solar_power_mw": solar_diag["solar_power_mw"],
            "solar_irradiance_w_m2": solar_irradiance_w_m2,
            "sun_elevation_deg": solar_diag["sun_elevation_deg"],
            "load_power_mw": round(p_load_mw, 1),
            "net_power_mw": round(p_solar_mw - p_load_mw, 1),
            "currents_ma": currents,
            "battery": bat_diag,
            "total_consumed_wh": round(self.total_energy_consumed_j / 3600.0, 3),
            "total_harvested_wh": round(self.total_solar_harvested_j / 3600.0, 3),
            "chamber_cycle_energy_mwh": round((self.chamber_cycle_energy_j / 3600.0) * 1000.0, 2),
            "chamber_cycle_energy_j": round(self.chamber_cycle_energy_j, 2),
            "estimated_endurance_days": round(endurance_days, 1),
            "estimated_endurance_hours": round(endurance_hours, 1),
        }

    def reset_cycle_energy(self):
        self.chamber_cycle_energy_j = 0.0
