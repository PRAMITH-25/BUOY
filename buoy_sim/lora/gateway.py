"""
LoRa Shore Gateway Model.
Receives telemetry packets, validates HMAC-SHA256 MIC, detects replay attacks,
generates ACK frames, logs telemetry history, and manages downlink commands.
"""
from typing import Dict, Any, List, Optional
from collections import deque
from buoy_sim.lora.packet import (
    LoRaPacketBuilder, LoRaSecurity, MSG_TYPE_TELEMETRY, MSG_TYPE_ACK,
    CMD_TRIGGER_MEASUREMENT, CMD_CHANGE_INTERVAL, CMD_REQUEST_STATUS,
    CMD_INITIATE_CHAMBER, CMD_LOW_POWER_MODE
)

class LoRaGateway:
    def __init__(self):
        self.builder = LoRaPacketBuilder()
        self.last_seen_seq_num = 0
        self.gateway_seq_num = 1000
        self.received_packets: deque = deque(maxlen=100)
        self.rejected_packets: deque = deque(maxlen=50)
        self.pending_downlink_commands: deque = deque()

        # Telemetry storage
        self.telemetry_history: List[Dict[str, Any]] = []

        # Statistics
        self.total_packets_received = 0
        self.total_packets_accepted = 0
        self.total_packets_rejected = 0
        self.mic_failures = 0
        self.replay_attempts = 0

    def queue_downlink_command(self, cmd_id: int, cmd_arg: int = 0) -> Dict[str, Any]:
        """Queue a remote command for the buoy."""
        cmd_info = {
            "cmd_id": cmd_id,
            "cmd_arg": cmd_arg,
            "gateway_seq": self.gateway_seq_num,
        }
        self.pending_downlink_commands.append(cmd_info)
        self.gateway_seq_num += 1
        return cmd_info

    def process_incoming_frame(self, frame_bytes: bytes, rf_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming RF packet from Buoy.
        Returns result dict and optional ACK/command packet bytes.
        """
        self.total_packets_received += 1
        decode_res = self.builder.decode_packet(frame_bytes, self.last_seen_seq_num)

        log_entry = {
            "timestamp": decode_res.get("timestamp", 0),
            "seq_num": decode_res.get("seq_num", 0),
            "rssi_dbm": rf_metadata.get("rssi_dbm", -95.0),
            "snr_db": rf_metadata.get("snr_db", 6.0),
            "latency_ms": rf_metadata.get("round_trip_latency_ms", 120.0),
            "valid": decode_res["valid"],
            "error": decode_res.get("error"),
            "data": decode_res.get("data"),
            "frame_hex": frame_bytes.hex()[:32] + "...",
        }

        ack_bytes = None
        downlink_cmd_bytes = None

        if decode_res["valid"]:
            self.total_packets_accepted += 1
            seq = decode_res["seq_num"]
            self.last_seen_seq_num = max(self.last_seen_seq_num, seq)
            self.received_packets.append(log_entry)

            if decode_res.get("data"):
                telemetry_record = dict(decode_res["data"])
                telemetry_record["seq_num"] = seq
                telemetry_record["timestamp"] = decode_res["timestamp"]
                self.telemetry_history.append(telemetry_record)

            # Check if there is a pending downlink command to piggyback or send
            if self.pending_downlink_commands:
                cmd = self.pending_downlink_commands.popleft()
                downlink_cmd_bytes = self.builder.build_command_packet(
                    cmd["cmd_id"], cmd["cmd_arg"], cmd["gateway_seq"]
                )
                log_entry["downlink_command_sent"] = cmd
            else:
                # Standard ACK
                self.gateway_seq_num += 1
                ack_bytes = self.builder.build_ack_packet(seq, self.gateway_seq_num)
        else:
            self.total_packets_rejected += 1
            if decode_res.get("error") == "REPLAY_ATTACK_DETECTED":
                self.replay_attempts += 1
            elif "MIC_VERIFICATION_FAILED" in str(decode_res.get("error")):
                self.mic_failures += 1
            self.rejected_packets.append(log_entry)

        return {
            "status": "ACCEPTED" if decode_res["valid"] else "REJECTED",
            "decode_result": decode_res,
            "log_entry": log_entry,
            "ack_bytes": ack_bytes,
            "downlink_cmd_bytes": downlink_cmd_bytes,
        }
