"""
Solar Generation Model.
Simulates solar irradiance, panel tilt, thermal derating, MPPT/buck converter efficiency,
and power output in mW.
"""
import math
from typing import Dict, Any
from buoy_sim.core.config import SOLAR_SPECS
from buoy_sim.core.seed import global_rng

class SolarPanelModel:
    def __init__(self, specs: Dict[str, Any] = SOLAR_SPECS):
        self.specs = specs
        self.panel_tilt_deg = 25.0  # optimal fixed tilt for temperate latitude
        self.panel_area_m2 = 0.075   # approx 10W panel surface area

    def calculate_generation(
        self,
        solar_irradiance_w_m2: float,
        ambient_temp_c: float,
        hour_of_day: float
    ) -> Dict[str, float]:
        """
        Calculate instantaneous solar power harvested in mW.
        """
        if solar_irradiance_w_m2 <= 0.0 or not (6.0 <= hour_of_day <= 18.0):
            return {
                "solar_power_mw": 0.0,
                "solar_current_ma_at_3v7": 0.0,
                "panel_temp_c": ambient_temp_c,
                "sun_elevation_deg": 0.0,
            }

        # Solar elevation angle
        sun_elevation_rad = math.sin(math.pi * (hour_of_day - 6.0) / 12.0)
        sun_elevation_deg = math.degrees(math.asin(max(0.0, min(1.0, sun_elevation_rad))))

        # Cell temperature in full sun (rises ~25C above ambient at 1000 W/m2)
        panel_temp_c = ambient_temp_c + 25.0 * (solar_irradiance_w_m2 / 1000.0)

        # Thermal derating: -0.40% per deg C above 25 C
        temp_delta = max(0.0, panel_temp_c - 25.0)
        temp_derate_factor = 1.0 + (self.specs["temp_coeff_pct_c"] / 100.0) * temp_delta

        # Incident power on panel
        incident_power_w = solar_irradiance_w_m2 * self.panel_area_m2
        ideal_electrical_w = (incident_power_w / 1000.0) * self.specs["peak_power_w"]

        # MPPT converter efficiency
        harvested_w = ideal_electrical_w * temp_derate_factor * self.specs["mppt_efficiency"]
        harvested_w = max(0.0, min(self.specs["peak_power_w"], harvested_w))

        solar_power_mw = harvested_w * 1000.0
        # Charging current into 3.7V battery bus
        charging_current_ma = solar_power_mw / 3.70

        return {
            "solar_power_mw": round(solar_power_mw, 1),
            "solar_current_ma_at_3v7": round(charging_current_ma, 1),
            "panel_temp_c": round(panel_temp_c, 1),
            "sun_elevation_deg": round(sun_elevation_deg, 1),
        }
