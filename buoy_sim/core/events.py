"""
Event and message definitions for ESP32-S3 tasks and buoy system.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict
import time

class TaskState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    SLEEPING = "SLEEPING"
    ERROR = "ERROR"

class SystemPowerMode(Enum):
    ACTIVE = "ACTIVE"
    MODEM_SLEEP = "MODEM_SLEEP"
    LIGHT_SLEEP = "LIGHT_SLEEP"
    DEEP_SLEEP = "DEEP_SLEEP"

class ChamberState(Enum):
    LAKE_MONITORING = "LAKE_MONITORING"
    CHAMBER_FILL = "CHAMBER_FILL"
    STABILIZE = "STABILIZE"
    MEASURE = "MEASURE"
    FLUSH = "FLUSH"

class EventType(Enum):
    TIMER_TICK = "TIMER_TICK"
    CHAMBER_STATE_CHANGE = "CHAMBER_STATE_CHANGE"
    TRIGGER_MEASUREMENT = "TRIGGER_MEASUREMENT"
    RAW_SAMPLES_READY = "RAW_SAMPLES_READY"
    PROCESSED_DATA_READY = "PROCESSED_DATA_READY"
    GPS_UPDATE = "GPS_UPDATE"
    TRANSMIT_TELEMETRY = "TRANSMIT_TELEMETRY"
    LORA_ACK_RECEIVED = "LORA_ACK_RECEIVED"
    LORA_COMMAND_RECEIVED = "LORA_COMMAND_RECEIVED"
    LORA_TX_TIMEOUT = "LORA_TX_TIMEOUT"
    POWER_STATUS_UPDATE = "POWER_STATUS_UPDATE"
    WATCHDOG_HEARTBEAT = "WATCHDOG_HEARTBEAT"
    WATCHDOG_TIMEOUT = "WATCHDOG_TIMEOUT"
    FAULT_INJECTED = "FAULT_INJECTED"
    FAULT_CLEARED = "FAULT_CLEARED"

@dataclass
class SimEvent:
    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    source_task: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
