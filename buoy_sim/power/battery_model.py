"""
Battery Model with BMS Protection.
Simulates LiFePO4 / Li-ion cell:
- Coulomb counting for State of Charge (SOC %)
- Nonlinear Open-Circuit Voltage (OCV) curve
- Internal resistance voltage drop under load
- Overvoltage (4.20V) and undervoltage (3.10V) BMS cutoffs
"""
import math
from typing import Dict, Any
from buoy_sim.core.config import BATTERY_SPECS

class BatteryModel:
    def __init__(self, initial_soc_pct: float = 85.0, specs: Dict[str, Any] = BATTERY_SPECS):
        self.specs = specs
        self.capacity_mah = specs["nominal_capacity_mah"]
        self.soc_pct = max(0.0, min(100.0, initial_soc_pct))
        self.nominal_voltage = specs["nominal_voltage_v"]
        self.terminal_voltage_v = self.calculate_ocv(self.soc_pct)
        self.total_energy_wh = (self.capacity_mah / 1000.0) * self.nominal_voltage
        self.bms_cutoff_active = False

    def calculate_ocv(self, soc: float) -> float:
        """
        Realistic Open-Circuit Voltage curve for Li-ion / LiFePO4 cell.
        """
        s = max(0.0, min(100.0, soc)) / 100.0
        # Empirical Li-ion sigmoid-polynomial curve
        ocv = 3.20 + 0.58 * s + 0.42 * (s**3) - 0.20 * math.exp(-25.0 * max(0.001, s))
        return max(self.specs["min_cutoff_voltage_v"], min(self.specs["max_voltage_v"], ocv))

    def update(
        self,
        dt_s: float,
        load_current_ma: float,
        charge_current_ma: float
    ) -> Dict[str, Any]:
        """
        Advance battery state over dt_s seconds.
        """
        dt_hours = dt_s / 3600.0

        # Effective current into battery
        net_charge_ma = (charge_current_ma * self.specs["charge_efficiency"]) - load_current_ma
        delta_mah = net_charge_ma * dt_hours

        # Update SOC
        delta_soc_pct = (delta_mah / self.capacity_mah) * 100.0
        self.soc_pct = max(0.0, min(100.0, self.soc_pct + delta_soc_pct))

        # Open circuit voltage
        ocv = self.calculate_ocv(self.soc_pct)

        # Voltage under load/charge: V = OCV + I*R
        i_net_a = net_charge_ma / 1000.0
        v_drop = i_net_a * self.specs["internal_resistance_ohm"]
        self.terminal_voltage_v = max(self.specs["min_cutoff_voltage_v"], min(self.specs["max_voltage_v"], ocv + v_drop))

        # BMS protection
        if self.terminal_voltage_v <= self.specs["min_cutoff_voltage_v"] or self.soc_pct <= 2.0:
            self.bms_cutoff_active = True
        elif self.bms_cutoff_active and self.soc_pct >= 10.0:
            self.bms_cutoff_active = False

        remaining_mah = (self.soc_pct / 100.0) * self.capacity_mah
        remaining_wh = (remaining_mah / 1000.0) * self.nominal_voltage

        return {
            "soc_pct": round(self.soc_pct, 2),
            "voltage_v": round(self.terminal_voltage_v, 3),
            "ocv_v": round(ocv, 3),
            "remaining_mah": round(remaining_mah, 1),
            "remaining_wh": round(remaining_wh, 2),
            "net_current_ma": round(net_charge_ma, 1),
            "bms_cutoff_active": self.bms_cutoff_active,
        }
