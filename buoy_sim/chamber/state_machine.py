"""
Flow-Through Chamber State Machine and Cycle Controller.
Sequence:
LAKE_MONITORING -> CHAMBER_FILL -> STABILIZE -> MEASURE -> FLUSH -> LAKE_MONITORING
"""
from typing import Dict, Any, Optional
from buoy_sim.core.events import ChamberState
from buoy_sim.core.config import CHAMBER_DEFAULT_TIMING

class ChamberStateMachine:
    def __init__(self, timing_config: Optional[Dict[str, float]] = None):
        self.timing = dict(CHAMBER_DEFAULT_TIMING)
        if timing_config:
            self.timing.update(timing_config)

        self.current_state = ChamberState.LAKE_MONITORING
        self.time_in_state_s = 0.0
        self.total_cycles_completed = 0
        self.manual_cycle_requested = False

        # Physical state models (simulated pump & valves)
        self.pump_active = False
        self.inlet_valve_open = False
        self.flush_valve_open = False
        self.chamber_fluid_level_pct = 0.0  # 0% to 100%
        self.fluid_stabilized = False
        self.optical_shield_sealed = True

        # Fault injection
        self.fault_pump_stall = False
        self.fault_valve_stuck = False

    def request_manual_cycle(self):
        """Trigger an out-of-schedule measurement cycle immediately."""
        self.manual_cycle_requested = True

    def _transition_to(self, new_state: ChamberState):
        self.current_state = new_state
        self.time_in_state_s = 0.0
        # Immediately set physical outputs for the new state
        if new_state == ChamberState.LAKE_MONITORING:
            self.pump_active = False
            self.inlet_valve_open = False
            self.flush_valve_open = False
            self.fluid_stabilized = False
        elif new_state == ChamberState.CHAMBER_FILL:
            self.pump_active = not self.fault_pump_stall
            self.inlet_valve_open = True
            self.flush_valve_open = False
            self.fluid_stabilized = False
        elif new_state == ChamberState.STABILIZE:
            self.pump_active = False
            self.inlet_valve_open = False
            self.flush_valve_open = False
            self.chamber_fluid_level_pct = 100.0
        elif new_state == ChamberState.MEASURE:
            self.pump_active = False
            self.inlet_valve_open = False
            self.flush_valve_open = False
            self.chamber_fluid_level_pct = 100.0
            self.fluid_stabilized = True
        elif new_state == ChamberState.FLUSH:
            self.pump_active = not self.fault_pump_stall
            self.inlet_valve_open = False
            self.flush_valve_open = True
            self.fluid_stabilized = False

    def update(self, dt_s: float) -> Dict[str, Any]:
        self.time_in_state_s += dt_s
        transitioned = False
        prev_state = self.current_state

        if self.fault_pump_stall and self.pump_active:
            self.pump_active = False

        if self.current_state == ChamberState.LAKE_MONITORING:
            interval = self.timing["lake_monitoring_interval_s"]
            if self.time_in_state_s >= interval or self.manual_cycle_requested:
                self.manual_cycle_requested = False
                self._transition_to(ChamberState.CHAMBER_FILL)
                transitioned = True

        elif self.current_state == ChamberState.CHAMBER_FILL:
            fill_dur = max(1.0, self.timing["fill_duration_s"])
            self.chamber_fluid_level_pct = min(100.0, (self.time_in_state_s / fill_dur) * 100.0)
            if self.time_in_state_s >= self.timing["fill_duration_s"]:
                self._transition_to(ChamberState.STABILIZE)
                transitioned = True

        elif self.current_state == ChamberState.STABILIZE:
            stab_dur = max(1.0, self.timing["stabilize_duration_s"])
            self.fluid_stabilized = (self.time_in_state_s >= (0.5 * stab_dur))
            if self.time_in_state_s >= self.timing["stabilize_duration_s"]:
                self._transition_to(ChamberState.MEASURE)
                transitioned = True

        elif self.current_state == ChamberState.MEASURE:
            if self.time_in_state_s >= self.timing["measure_duration_s"]:
                self._transition_to(ChamberState.FLUSH)
                transitioned = True

        elif self.current_state == ChamberState.FLUSH:
            flush_dur = max(1.0, self.timing["flush_duration_s"])
            self.chamber_fluid_level_pct = max(0.0, 100.0 - (self.time_in_state_s / flush_dur) * 100.0)
            if self.time_in_state_s >= self.timing["flush_duration_s"]:
                self.total_cycles_completed += 1
                self._transition_to(ChamberState.LAKE_MONITORING)
                transitioned = True

        return {
            "current_state": self.current_state.value,
            "previous_state": prev_state.value,
            "transitioned": transitioned,
            "time_in_state_s": round(self.time_in_state_s, 2),
            "state_duration_s": self._get_current_state_duration(),
            "pump_active": self.pump_active,
            "inlet_valve_open": self.inlet_valve_open,
            "flush_valve_open": self.flush_valve_open,
            "fluid_level_pct": round(self.chamber_fluid_level_pct, 1),
            "fluid_stabilized": self.fluid_stabilized,
            "total_cycles_completed": self.total_cycles_completed,
            "fault": "PUMP_STALL" if self.fault_pump_stall else None,
        }

    def _get_current_state_duration(self) -> float:
        if self.current_state == ChamberState.LAKE_MONITORING:
            return float(self.timing["lake_monitoring_interval_s"])
        elif self.current_state == ChamberState.CHAMBER_FILL:
            return float(self.timing["fill_duration_s"])
        elif self.current_state == ChamberState.STABILIZE:
            return float(self.timing["stabilize_duration_s"])
        elif self.current_state == ChamberState.MEASURE:
            return float(self.timing["measure_duration_s"])
        elif self.current_state == ChamberState.FLUSH:
            return float(self.timing["flush_duration_s"])
        return 0.0

    @property
    def is_isolated(self) -> bool:
        return self.current_state in (
            ChamberState.CHAMBER_FILL,
            ChamberState.STABILIZE,
            ChamberState.MEASURE,
            ChamberState.FLUSH
        )

    @property
    def is_measuring_window(self) -> bool:
        return self.current_state == ChamberState.MEASURE
