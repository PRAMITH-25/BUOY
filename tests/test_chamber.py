import unittest
from buoy_sim.chamber.state_machine import ChamberStateMachine
from buoy_sim.core.events import ChamberState

class TestChamber(unittest.TestCase):
    def setUp(self):
        self.chamber = ChamberStateMachine({
            "lake_monitoring_interval_s": 10,
            "fill_duration_s": 4,
            "stabilize_duration_s": 4,
            "measure_duration_s": 3,
            "flush_duration_s": 4,
        })

    def test_full_chamber_cycle_transitions(self):
        # 1. Starts in LAKE_MONITORING
        self.assertEqual(self.chamber.current_state, ChamberState.LAKE_MONITORING)
        self.assertFalse(self.chamber.is_isolated)

        # 2. Advance 10.5s -> transitions to CHAMBER_FILL
        res = self.chamber.update(10.5)
        self.assertEqual(self.chamber.current_state, ChamberState.CHAMBER_FILL)
        self.assertTrue(self.chamber.pump_active)
        self.assertTrue(self.chamber.is_isolated)

        # 3. Advance 4.5s -> transitions to STABILIZE
        res = self.chamber.update(4.5)
        self.assertEqual(self.chamber.current_state, ChamberState.STABILIZE)
        self.assertFalse(self.chamber.pump_active)

        # 3b. Advance 2.5s within STABILIZE -> fluid settles and stabilizes
        res = self.chamber.update(2.5)
        self.assertTrue(self.chamber.fluid_stabilized)

        # 4. Advance remaining 2s -> transitions to MEASURE
        res = self.chamber.update(2.0)
        self.assertEqual(self.chamber.current_state, ChamberState.MEASURE)
        self.assertTrue(self.chamber.is_measuring_window)
        self.assertTrue(self.chamber.fluid_stabilized)

        # 5. Advance 3.5s -> transitions to FLUSH
        res = self.chamber.update(3.5)
        self.assertEqual(self.chamber.current_state, ChamberState.FLUSH)
        self.assertTrue(self.chamber.pump_active)

        # 6. Advance 4.5s -> returns to LAKE_MONITORING
        res = self.chamber.update(4.5)
        self.assertEqual(self.chamber.current_state, ChamberState.LAKE_MONITORING)
        self.assertEqual(self.chamber.total_cycles_completed, 1)

    def test_manual_cycle_request(self):
        self.chamber.request_manual_cycle()
        res = self.chamber.update(0.1)
        self.assertEqual(self.chamber.current_state, ChamberState.CHAMBER_FILL)
