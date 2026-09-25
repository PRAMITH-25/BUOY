import unittest
from buoy_sim.sensors.environment import LakeEnvironment, WeatherState
from buoy_sim.sensors.water_sensors import WaterSensors
from buoy_sim.sensors.ads1115 import ADS1115Emulator
from buoy_sim.sensors.navigation import NEO6MGps, MPU6050Imu

class TestSensors(unittest.TestCase):
    def setUp(self):
        self.env = LakeEnvironment()
        self.sensors = WaterSensors()
        self.adc = ADS1115Emulator()
        self.gps = NEO6MGps()
        self.imu = MPU6050Imu()

    def test_environment_diurnal(self):
        # Morning at 08:00
        gt_morning = self.env.update(3600 * 8)
        self.assertGreater(gt_morning["solar_irradiance_w_m2"], 0)
        self.assertGreaterEqual(gt_morning["ph"], 7.0)
        self.assertLessEqual(gt_morning["ph"], 8.5)

        # Midnight at 00:00
        gt_night = self.env.update(3600 * 24)
        self.assertEqual(gt_night["solar_irradiance_w_m2"], 0.0)

    def test_environment_rain_runoff(self):
        gt_clear = self.env.update(3600 * 12)
        turb_clear = gt_clear["turbidity_ntu"]

        self.env.trigger_rain_runoff(intensity=0.9)
        gt_rain = self.env.update(3600 * 12.1)
        self.assertGreater(gt_rain["turbidity_ntu"], turb_clear + 50.0)
        self.assertEqual(gt_rain["weather"], WeatherState.RAIN_RUNOFF)

        self.env.clear_weather()
        gt_restored = self.env.update(3600 * 12.2)
        self.assertEqual(gt_restored["weather"], WeatherState.CLEAR)

    def test_water_sensors_quiescent_vs_open(self):
        gt = self.env.update(3600 * 12)
        # Chamber isolated & stabilized
        v_chamber = self.sensors.generate_analog_voltages(gt, is_chamber_isolated=True, chamber_stabilized=True)
        self.assertIn("v_ph", v_chamber)
        self.assertIn("v_ec", v_chamber)
        self.assertIn("v_turbidity", v_chamber)
        self.assertIn("temp_c", v_chamber)

        # Open lake
        v_open = self.sensors.generate_analog_voltages(gt, is_chamber_isolated=False, chamber_stabilized=False)
        self.assertGreater(v_open["v_ph"], 0.0)
        self.assertGreater(v_open["v_turbidity"], 0.0)

    def test_fault_sensor_disconnect(self):
        gt = self.env.update(3600 * 12)
        self.sensors.fault_sensor_disconnect = True
        v = self.sensors.generate_analog_voltages(gt, is_chamber_isolated=True)
        self.assertEqual(v["fault"], "SENSOR_DISCONNECTED")
        self.assertEqual(v["temp_c"], -99.0)

    def test_ads1115_conversion(self):
        raw_code, v_dig = self.adc.read_channel_raw(0, 2.500)
        self.assertAlmostEqual(v_dig, 2.500, places=2)
        self.assertGreater(raw_code, 0)
        self.assertLess(raw_code, 32767)

    def test_ads1115_fault_i2c(self):
        self.adc.fault_i2c_bus_hang = True
        res = self.adc.sample_all_channels({"v_ph": 2.5, "v_ec": 0.6, "v_turbidity": 4.0})
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "I2C_NACK_ERROR")

    def test_gps_and_imu(self):
        gps_data = self.gps.update(100.0)
        self.assertEqual(gps_data["fix_quality"], 1)
        self.assertGreater(gps_data["satellites"], 4)
        self.assertIn("$GPRMC", gps_data["nmea_rmc"])

        imu_data = self.imu.update(100.0, wave_height_m=0.15)
        self.assertIn("pitch_deg", imu_data)
        self.assertIn("roll_deg", imu_data)
        self.assertIn("accel_z_g", imu_data)
