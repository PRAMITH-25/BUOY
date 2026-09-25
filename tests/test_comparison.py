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
