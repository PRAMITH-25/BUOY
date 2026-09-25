import unittest
from buoy_sim.sensors.signal_filter import SignalFilter

class TestSignalFilter(unittest.TestCase):
    def setUp(self):
        self.filter = SignalFilter(median_window=5, moving_avg_window=7)

    def test_filter_removes_outlier_spike(self):
        # Normal steady sequence around 2.50 V
        for _ in range(6):
            self.filter.filter_sample("v_ph", 2.50)

        # Inject extreme single-sample impulse spike (e.g. 3.50 V)
        filtered_val = self.filter.filter_sample("v_ph", 3.50)
        # Median filter should reject the spike
        self.assertLess(filtered_val, 2.70)

    def test_process_adc_voltages_calibration(self):
        # Neutral pH ~ 2.500 V, clean turbidity ~ 4.01 V, moderate EC ~ 0.635 V
        voltages = {"v_ph": 2.500, "v_ec": 0.635, "v_turbidity": 4.008}
        temp_c = 25.0

        for _ in range(5):
            res = self.filter.process_adc_voltages(voltages, temp_c)

        filtered = res["filtered"]
        self.assertAlmostEqual(filtered["ph"], 7.00, delta=0.1)
        self.assertAlmostEqual(filtered["turbidity_ntu"], 8.5, delta=2.0)
        self.assertGreater(filtered["ec_us_cm"], 300.0)
        self.assertEqual(res["quality_flag"], "VALID")
