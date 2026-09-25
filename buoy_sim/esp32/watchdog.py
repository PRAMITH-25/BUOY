"""
ESP32-S3 Watchdog and Fault Injection System.
Tracks heartbeats of all 6 logical tasks:
- SensorTask
- ChamberTask
- ProcessingTask
- GPSTask
- LoRaTask
- PowerTask

If any task hangs beyond WATCHDOG_TIMEOUT_S (10s), triggers soft-reset,
logs reset reason, and recovers tasks.
"""
from typing import Dict, Any, List
from buoy_sim.core.config import WATCHDOG_TIMEOUT_S

class SoftwareWatchdog:
    def __init__(self, timeout_s: float = WATCHDOG_TIMEOUT_S):
        self.timeout_s = timeout_s
        self.tasks = [
            "SensorTask", "ChamberTask", "ProcessingTask",
            "GPSTask", "LoRaTask", "PowerTask"
        ]
        self.task_heartbeats: Dict[str, float] = {t: 0.0 for t in self.tasks}
        self.task_freeze_faults: Dict[str, bool] = {t: False for t in self.tasks}

        self.reset_count = 0
        self.last_reset_reason = "POWER_ON_RESET"
        self.reset_history: List[Dict[str, Any]] = []

    def feed(self, task_name: str, sim_time_s: float):
        """Task feeds the watchdog."""
        if not self.task_freeze_faults.get(task_name, False):
            self.task_heartbeats[task_name] = sim_time_s

    def inject_task_freeze(self, task_name: str):
        """Simulate an infinite loop or deadlock in a specific task."""
        if task_name in self.task_freeze_faults:
            self.task_freeze_faults[task_name] = True

    def clear_task_freeze(self, task_name: str):
        if task_name in self.task_freeze_faults:
            self.task_freeze_faults[task_name] = False

    def check(self, sim_time_s: float) -> Dict[str, Any]:
        """
        Check all task heartbeats against timeout threshold.
        """
        timed_out_tasks = []
        for task, last_hb in self.task_heartbeats.items():
            if (sim_time_s - last_hb) > self.timeout_s:
                timed_out_tasks.append(task)

        if timed_out_tasks:
            self.reset_count += 1
            reason = f"WATCHDOG_TIMEOUT_TASKS_{'_'.join(timed_out_tasks)}"
            self.last_reset_reason = reason
            reset_event = {
                "reset_num": self.reset_count,
                "timestamp": sim_time_s,
                "reason": reason,
                "failed_tasks": timed_out_tasks,
            }
            self.reset_history.append(reset_event)

            # Auto-recovery: unfreeze tasks and refresh heartbeats
            for t in self.tasks:
                self.task_freeze_faults[t] = False
                self.task_heartbeats[t] = sim_time_s

            return {
                "triggered": True,
                "reset_count": self.reset_count,
                "reason": reason,
                "failed_tasks": timed_out_tasks,
            }

        return {
            "triggered": False,
            "reset_count": self.reset_count,
            "last_reset_reason": self.last_reset_reason,
            "heartbeats": {t: round(sim_time_s - hb, 1) for t, hb in self.task_heartbeats.items()},
        }
