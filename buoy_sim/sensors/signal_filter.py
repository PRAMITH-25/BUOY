"""
Signal Processing Pipeline for Water Quality Telemetry.
Includes:
- Moving Average and Median filtering
- Outlier / bubble spike rejection
- Raw vs Filtered noise statistical comparison (Mean, Std Dev, Variance, SNR, Peak-to-Peak)
- Quality validation flags
"""
import math
from collections import deque
from typing import List, Dict, Any, Optional
import numpy as np
from buoy_sim.core.config import (
    PH_CALIBRATION, EC_CALIBRATION, TURBIDITY_CALIBRATION, TEMP_CALIBRATION
)

class SignalFilter:
    def __init__(self, median_window: int = 5, moving_avg_window: int = 7):
        self.median_window = median_window
        self.moving_avg_window = moving_avg_window

        self.buffers = {
            "v_ph": deque(maxlen=moving_avg_window),
            "v_ec": deque(maxlen=moving_avg_window),
            "v_turbidity": deque(maxlen=moving_avg_window),
            "temp_c": deque(maxlen=moving_avg_window),
        }

        self.history_size = 50
        self.raw_history = {k: deque(maxlen=self.history_size) for k in self.buffers}
        self.filtered_history = {k: deque(maxlen=self.history_size) for k in self.buffers}

    def reset(self):
        for buf in self.buffers.values():
            buf.clear()
        for hist in self.raw_history.values():
            hist.clear()
        for hist in self.filtered_history.values():
            hist.clear()

    def filter_sample(self, param: str, raw_val: float) -> float:
        buf = self.buffers[param]
        buf.append(raw_val)
        self.raw_history[param].append(raw_val)

        if len(buf) < 3:
            filtered = raw_val
        else:
            recent = list(buf)[-self.median_window:]
            med_val = float(np.median(recent))
            temp_list = list(buf)[:-1] + [med_val]
            filtered = float(np.mean(temp_list))

        self.filtered_history[param].append(filtered)
        return filtered

    def process_adc_voltages(
        self,
        voltages: Dict[str, float],
        temp_c: float
    ) -> Dict[str, Any]:
        f_v_ph = self.filter_sample("v_ph", voltages["v_ph"])
        f_v_ec = self.filter_sample("v_ec", voltages["v_ec"])
        f_v_turb = self.filter_sample("v_turbidity", voltages["v_turbidity"])
        f_temp_c = self.filter_sample("temp_c", temp_c)

        temp_k = f_temp_c + 273.15
        nernst_slope = PH_CALIBRATION["slope_v_per_ph"] * (temp_k / 298.15)
        raw_ph = 7.0 + (voltages["v_ph"] - PH_CALIBRATION["v_neutral"]) / nernst_slope
        filtered_ph = 7.0 + (f_v_ph - PH_CALIBRATION["v_neutral"]) / nernst_slope

        alpha = EC_CALIBRATION["temp_coefficient"]
        temp_comp_denom = 1.0 + alpha * (f_temp_c - 25.0)

        raw_ec_uncomp = max(0.0, (voltages["v_ec"] - EC_CALIBRATION["v_zero"]) * EC_CALIBRATION["v_to_ec_factor"])
        filtered_ec_uncomp = max(0.0, (f_v_ec - EC_CALIBRATION["v_zero"]) * EC_CALIBRATION["v_to_ec_factor"])

        raw_ec = raw_ec_uncomp / max(0.1, (1.0 + alpha * (temp_c - 25.0)))
        filtered_ec = filtered_ec_uncomp / max(0.1, temp_comp_denom)
        filtered_tds = filtered_ec * EC_CALIBRATION["tds_factor"]

        # Exact inverse optical turbidity curve:
        # NTU = K_half * (V_clean - V) / (V - V_min)
        v_clean = TURBIDITY_CALIBRATION["v_clean"]
        v_min = TURBIDITY_CALIBRATION["v_min"]
        k_half = TURBIDITY_CALIBRATION["k_half"]

        def v_to_ntu(v):
            v_clamped = max(v_min + 0.01, min(v_clean, v))
            delta = v_clean - v_clamped
            denom = max(0.001, v_clamped - v_min)
            ntu = k_half * delta / denom
            return max(0.0, min(3000.0, ntu))

        raw_turbidity = v_to_ntu(voltages["v_turbidity"])
        filtered_turbidity = v_to_ntu(f_v_turb)

        quality_flag = "VALID"
        if not (PH_CALIBRATION["min_valid_ph"] <= filtered_ph <= PH_CALIBRATION["max_valid_ph"]):
            quality_flag = "OUT_OF_BOUNDS_PH"
        elif not (EC_CALIBRATION["min_valid_ec"] <= filtered_ec <= EC_CALIBRATION["max_valid_ec"]):
            quality_flag = "OUT_OF_BOUNDS_EC"
        elif not (TURBIDITY_CALIBRATION["min_valid_ntu"] <= filtered_turbidity <= TURBIDITY_CALIBRATION["max_valid_ntu"]):
            quality_flag = "OUT_OF_BOUNDS_TURBIDITY"
        elif not (TEMP_CALIBRATION["min_valid_temp"] <= f_temp_c <= TEMP_CALIBRATION["max_valid_temp"]):
            quality_flag = "OUT_OF_BOUNDS_TEMP"

        return {
            "quality_flag": quality_flag,
            "raw": {
                "ph": round(raw_ph, 3),
                "ec_us_cm": round(raw_ec, 1),
                "turbidity_ntu": round(raw_turbidity, 2),
                "temp_c": round(temp_c, 2),
                "v_ph": round(voltages["v_ph"], 4),
                "v_ec": round(voltages["v_ec"], 4),
                "v_turbidity": round(voltages["v_turbidity"], 4),
            },
            "filtered": {
                "ph": round(filtered_ph, 3),
                "ec_us_cm": round(filtered_ec, 1),
                "tds_ppm": round(filtered_tds, 1),
                "turbidity_ntu": round(filtered_turbidity, 2),
                "temp_c": round(f_temp_c, 2),
                "v_ph": round(f_v_ph, 4),
                "v_ec": round(f_v_ec, 4),
                "v_turbidity": round(f_v_turb, 4),
            },
            "statistics": self.get_noise_statistics(),
        }

    def get_noise_statistics(self) -> Dict[str, Any]:
        stats = {}
        for param in self.buffers:
            raw_arr = np.array(self.raw_history[param]) if len(self.raw_history[param]) > 2 else np.array([1.0, 1.0])
            filt_arr = np.array(self.filtered_history[param]) if len(self.filtered_history[param]) > 2 else np.array([1.0, 1.0])

            raw_mean = float(np.mean(raw_arr))
            raw_std = float(np.std(raw_arr))
            raw_var = float(np.var(raw_arr))
            raw_ptp = float(np.ptp(raw_arr))

            filt_mean = float(np.mean(filt_arr))
            filt_std = float(np.std(filt_arr))
            filt_var = float(np.var(filt_arr))
            filt_ptp = float(np.ptp(filt_arr))

            noise_reduct_pct = max(0.0, (1.0 - (filt_std / max(1e-6, raw_std))) * 100.0) if raw_std > 1e-6 else 0.0

            raw_snr_db = 20.0 * math.log10(abs(raw_mean) / max(1e-6, raw_std)) if raw_std > 1e-6 else 99.0
            filt_snr_db = 20.0 * math.log10(abs(filt_mean) / max(1e-6, filt_std)) if filt_std > 1e-6 else 99.0

            stats[param] = {
                "raw_mean": round(raw_mean, 4),
                "raw_std": round(raw_std, 5),
                "raw_var": round(raw_var, 6),
                "raw_ptp": round(raw_ptp, 4),
                "filtered_mean": round(filt_mean, 4),
                "filtered_std": round(filt_std, 5),
                "filtered_var": round(filt_var, 6),
                "filtered_ptp": round(filt_ptp, 4),
                "noise_reduction_pct": round(noise_reduct_pct, 1),
                "raw_snr_db": round(raw_snr_db, 2),
                "filtered_snr_db": round(filt_snr_db, 2),
            }
        return stats
