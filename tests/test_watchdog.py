import unittest
from buoy_sim.esp32.watchdog import SoftwareWatchdog

class TestWatchdog(unittest.TestCase):
    def setUp(self):
        self.wd = SoftwareWatchdog(timeout_s=10.0)

    def test_heartbeat_feeding(self):
        t = 50.0
        for task in self.wd.tasks:
            self.wd.feed(task, t)

        diag = self.wd.check(t + 2.0)
        self.assertFalse(diag["triggered"])

    def test_task_freeze_triggers_reset(self):
        t = 100.0
        for task in self.wd.tasks:
            self.wd.feed(task, t)

        # Freeze SensorTask
        self.wd.inject_task_freeze("SensorTask")

        # Try to feed again at t+5
        for task in self.wd.tasks:
            self.wd.feed(task, t + 5.0)

        # Advance beyond 10s timeout
        diag = self.wd.check(t + 11.5)
        self.assertTrue(diag["triggered"])
        self.assertEqual(diag["reset_count"], 1)
        self.assertIn("SensorTask", diag["failed_tasks"])
