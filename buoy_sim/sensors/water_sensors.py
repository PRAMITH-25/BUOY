"""
Virtual Water Quality Sensors: pH, EC/TDS, Turbidity, and Temperature.
Converts lake ground truth water properties into analog voltages for ADS1115
and models both open-water continuous exposure and isolated flow-through chamber exposure.
"""
import math
from typing import Dict, Any
from buoy_sim.core.config import (
    PH_CALIBRATION, EC_CALIBRATION, TURBIDITY_CALIBRATION, TEMP_CALIBRATION
)
from buoy_sim.core.seed import global_rng

class WaterSensors:
    def __init__(self):
        self.fault_sensor_disconnect = False
        self.fault_probe_out_of_water = False

    def generate_analog_voltages(
        self,
        ground_truth: Dict[str, Any],
        is_chamber_isolated: bool,
        chamber_stabilized: bool = True
    ) -> Dict[str, float]:
        rng = global_rng.np

        if self.fault_sensor_disconnect:
            return {
                "v_ph": 0.05,
                "v_ec": 0.00,
                "v_turbidity": 4.85,
                "temp_c": -99.0,
                "fault": "SENSOR_DISCONNECTED",
            }

        if self.fault_probe_out_of_water:
            return {
                "v_ph": 1.10,
                "v_ec": 0.01,
                "v_turbidity": 4.25,
                "temp_c": ground_truth["water_temp_c"] + 4.0,
                "fault": "PROBE_OUT_OF_WATER",
            }

        temp_c = ground_truth["water_temp_c"]
        ph_true = ground_truth["ph"]
        ec_true = ground_truth["ec_us_cm"]
        turb_true = ground_truth["turbidity_ntu"]

        # 1. Temperature
        temp_noise = float(rng.normal(0.0, 0.02 if is_chamber_isolated else 0.10))
        measured_temp_c = temp_c + temp_noise

        # 2. pH Sensor (Nernst model)
        temp_k = measured_temp_c + 273.15
        nernst_slope = PH_CALIBRATION["slope_v_per_ph"] * (temp_k / 298.15)
        v_ph_ideal = PH_CALIBRATION["v_neutral"] + nernst_slope * (ph_true - 7.0)

        if is_chamber_isolated:
            ph_noise_v = float(rng.normal(0.0, 0.0012 if chamber_stabilized else 0.0050))
        else:
            wave_factor = ground_truth.get("wave_height_m", 0.12) / 0.12
            ph_noise_v = float(rng.normal(0.0, 0.0140 * wave_factor))

        v_ph = max(0.1, min(4.5, v_ph_ideal + ph_noise_v))

        # 3. EC / TDS Sensor
        alpha = EC_CALIBRATION["temp_coefficient"]
        ec_temp_uncompensated = ec_true * (1.0 + alpha * (measured_temp_c - 25.0))
        v_ec_ideal = EC_CALIBRATION["v_zero"] + (ec_temp_uncompensated / EC_CALIBRATION["v_to_ec_factor"])

        if is_chamber_isolated:
            ec_noise_v = float(rng.normal(0.0, 0.0010 if chamber_stabilized else 0.0040))
        else:
            ec_noise_v = float(rng.normal(0.0, 0.0150))

        v_ec = max(0.02, min(3.3, v_ec_ideal + ec_noise_v))

        # 4. Turbidity Sensor (Optical Nephelometric)
        # V(NTU) = V_clean - (V_clean - V_min) * (NTU / (NTU + K_half))
        v_clean = TURBIDITY_CALIBRATION["v_clean"]
        v_min = TURBIDITY_CALIBRATION["v_min"]
        k_half = TURBIDITY_CALIBRATION["k_half"]
        ratio = turb_true / (turb_true + k_half)
        v_turb_ideal = v_clean - (v_clean - v_min) * ratio

        if is_chamber_isolated:
            turb_noise_v = float(rng.normal(0.0, 0.0015 if chamber_stabilized else 0.0150))
        else:
            solar_irradiance = ground_truth.get("solar_irradiance_w_m2", 0.0)
            ambient_light_leak_v = float(rng.normal(0.0, 0.030 * (solar_irradiance / 800.0 + 0.15)))
            wave_slosh_v = float(rng.normal(0.0, 0.020))
            turb_noise_v = ambient_light_leak_v + wave_slosh_v

        v_turbidity = max(0.5, min(4.5, v_turb_ideal + turb_noise_v))

        return {
            "v_ph": v_ph,
            "v_ec": v_ec,
            "v_turbidity": v_turbidity,
            "temp_c": measured_temp_c,
            "fault": None,
        }
