import unittest
from buoy_sim.power.solar_model import SolarPanelModel
from buoy_sim.power.battery_model import BatteryModel
from buoy_sim.power.power_manager import PowerManager

class TestPower(unittest.TestCase):
    def setUp(self):
        self.solar = SolarPanelModel()
        self.battery = BatteryModel(initial_soc_pct=80.0)
        self.pm = PowerManager(initial_soc_pct=80.0)

    def test_solar_generation(self):
        # Midday generation
        gen_noon = self.solar.calculate_generation(solar_irradiance_w_m2=900.0, ambient_temp_c=22.0, hour_of_day=12.0)
        self.assertGreater(gen_noon["solar_power_mw"], 500.0)

        # Night generation
        gen_night = self.solar.calculate_generation(solar_irradiance_w_m2=0.0, ambient_temp_c=18.0, hour_of_day=23.0)
        self.assertEqual(gen_night["solar_power_mw"], 0.0)

    def test_battery_discharge_and_ocv(self):
        # Discharge battery with 100 mA for 1 hour
        res = self.battery.update(dt_s=3600.0, load_current_ma=100.0, charge_current_ma=0.0)
        self.assertLess(res["soc_pct"], 80.0)
        self.assertGreater(res["voltage_v"], 3.20)
        self.assertFalse(res["bms_cutoff_active"])

    def test_power_manager_endurance(self):
        res = self.pm.update(
            dt_s=1.0, solar_irradiance_w_m2=0.0, ambient_temp_c=20.0, hour_of_day=20.0,
            chamber_state="LAKE_MONITORING", pump_active=False, is_sampling=False,
            is_lora_tx=False, is_lora_rx=False, is_gps_tracking=True
        )
        self.assertGreater(res["estimated_endurance_days"], 5.0)
