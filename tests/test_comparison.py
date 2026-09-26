import unittest
from buoy_sim.experiments.comparison import ComparisonExperiment
from buoy_sim.experiments.exporter import TelemetryExporter

class TestComparison(unittest.TestCase):
    def test_comparison_experiment_run(self):
        exp = ComparisonExperiment(duration_s=120.0, step_s=2.0)
        summary = exp.run()

        self.assertIn("open_water_system_a", summary)
        self.assertIn("chamber_system_b", summary)
        self.assertIn("comparison_delta", summary)
        self.assertIn("disclaimer", summary)

        # Turbidity noise should be lower in chamber
        std_turb_a = summary["open_water_system_a"]["statistics"]["turbidity"]["std"]
        std_turb_b = summary["chamber_system_b"]["statistics"]["turbidity"]["std"]
        self.assertLess(std_turb_b, std_turb_a)

        # CSV export
        csv_data = TelemetryExporter.export_comparison_csv(exp.logs_a, exp.logs_b)
        self.assertIn("sys_a_ph", csv_data)
        self.assertIn("sys_b_ph", csv_data)

    def test_configurable_parameters(self):
        custom_params = {
            "fill_time_s": 45.0,
            "stabilize_time_s": 90.0,
            "flush_time_s": 25.0,
            "measure_duration_s": 12.0,
            "noise_scale": 1.5,
        }
        exp = ComparisonExperiment(duration_s=60.0, step_s=2.0, params=custom_params)
        summary = exp.run()

        self.assertIn("simulation_params_used", summary)
        self.assertEqual(summary["simulation_params_used"]["fill_time_s"], 45.0)
        self.assertEqual(summary["simulation_params_used"]["stabilize_time_s"], 90.0)
        self.assertEqual(summary["simulation_params_used"]["noise_scale"], 1.5)
        self.assertIn("validation_note", summary)
        self.assertIn("require physical validation", summary["validation_note"].lower())

    def test_scientific_disclaimer_and_metrics(self):
        exp = ComparisonExperiment(duration_s=60.0, step_s=2.0)
        summary = exp.run()

        # Scientific disclaimer must clearly state it is simulated
        self.assertIn("SIMULATED", summary["disclaimer"])
        self.assertIn("physical validation", summary["disclaimer"].lower())

        # Subsystems must report duty cycle and energy
        sys_a = summary["open_water_system_a"]
        sys_b = summary["chamber_system_b"]
        self.assertIn("duty_cycle_pct", sys_a)
        self.assertIn("duty_cycle_pct", sys_b)
        self.assertIn("energy_per_cycle_mwh", sys_a)
        self.assertIn("energy_per_cycle_mwh", sys_b)

