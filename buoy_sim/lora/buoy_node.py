"""
Buoy LoRa Node Task & Communication Engine.
Handles packet transmission, ACK wait windows, retries with exponential backoff,
downlink command execution, and flash buffer during link failure.
"""
from typing import Dict, Any, Optional, List
from collections import deque
from buoy_sim.lora.packet import LoRaPacketBuilder, MSG_TYPE_COMMAND, MSG_TYPE_ACK
from buoy_sim.lora.channel import LoRaChannelModel
from buoy_sim.lora.gateway import LoRaGateway

class BuoyLoRaNode:
    def __init__(self, gateway: LoRaGateway, channel: Optional[LoRaChannelModel] = None):
        self.gateway = gateway
        self.channel = channel or LoRaChannelModel()
        self.builder = LoRaPacketBuilder()

        self.seq_num = 1
        self.ack_pending = False
        self.current_retry_count = 0
        self.max_retries = 3

        # Buffers
        self.tx_history: deque = deque(maxlen=100)
        self.flash_offline_buffer: deque = deque(maxlen=200)

        # Statistics
        self.total_transmitted = 0
        self.total_acked = 0
        self.total_retries = 0
        self.total_dropped = 0

    def transmit_telemetry(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build, encrypt, and transmit telemetry packet over channel to gateway.
        """
        packet_dict = self.builder.build_telemetry_packet(
            seq_num=self.seq_num,
            timestamp=telemetry_data.get("timestamp", 0.0),
            ph=telemetry_data.get("ph", 7.5),
            ec_us_cm=telemetry_data.get("ec_us_cm", 350.0),
            turbidity_ntu=telemetry_data.get("turbidity_ntu", 8.0),
            temp_c=telemetry_data.get("temp_c", 20.0),
            battery_soc_pct=telemetry_data.get("soc_pct", 80.0),
            solar_power_mw=telemetry_data.get("solar_power_mw", 0.0),
            latitude=telemetry_data.get("latitude", 42.58),
            longitude=telemetry_data.get("longitude", -88.43),
            chamber_state=telemetry_data.get("chamber_state", "LAKE_MONITORING"),
            quality_flag=telemetry_data.get("quality_flag", "VALID")
        )

        frame_bytes = packet_dict["frame_bytes"]
        self.total_transmitted += 1

        # Channel RF propagation
        rf_meta = self.channel.simulate_transmission(len(frame_bytes))

        # Result container
        result = {
            "seq_num": self.seq_num,
            "packet_dict": packet_dict,
            "rf_metadata": rf_meta,
            "status": "TRANSMITTED",
            "acked": False,
            "downlink_command": None,
        }

        if rf_meta["packet_lost"]:
            self.total_retries += 1
            result["status"] = "PACKET_LOST_IN_AIR"
            # Buffer for retry or flash
            if self.current_retry_count < self.max_retries:
                self.current_retry_count += 1
            else:
                self.total_dropped += 1
                self.flash_offline_buffer.append(packet_dict)
                self.current_retry_count = 0
                self.seq_num += 1
        else:
            # Reached gateway
            gw_res = self.gateway.process_incoming_frame(frame_bytes, rf_meta)
            result["gateway_response"] = gw_res

            if gw_res["status"] == "ACCEPTED":
                self.total_acked += 1
                self.current_retry_count = 0
                result["acked"] = True
                self.seq_num += 1

                # Check if gateway returned a command
                if gw_res.get("downlink_cmd_bytes"):
                    cmd_decode = self.builder.decode_packet(gw_res["downlink_cmd_bytes"], 0)
                    if cmd_decode["valid"] and cmd_decode["msg_type"] == "COMMAND":
                        result["downlink_command"] = cmd_decode

        self.tx_history.append(result)
        return result

    def simulate_tampered_packet(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deliberately flip a byte in the payload to demonstrate Gateway rejection of modified packet.
        """
        packet_dict = self.builder.build_telemetry_packet(
            seq_num=self.seq_num + 500,
            timestamp=telemetry_data.get("timestamp", 0.0),
            ph=telemetry_data.get("ph", 7.5),
            ec_us_cm=telemetry_data.get("ec_us_cm", 350.0),
            turbidity_ntu=telemetry_data.get("turbidity_ntu", 8.0),
            temp_c=telemetry_data.get("temp_c", 20.0),
            battery_soc_pct=telemetry_data.get("soc_pct", 80.0),
            solar_power_mw=0.0,
            latitude=42.58,
            longitude=-88.43,
            chamber_state="LAKE_MONITORING",
            quality_flag="VALID"
        )
        raw_frame = bytearray(packet_dict["frame_bytes"])
        # Flip bit in payload
        raw_frame[18] ^= 0xFF

        rf_meta = self.channel.simulate_transmission(len(raw_frame))
        rf_meta["packet_lost"] = False
        gw_res = self.gateway.process_incoming_frame(bytes(raw_frame), rf_meta)

        return {
            "tampered": True,
            "gw_status": gw_res["status"],
            "gw_error": gw_res["decode_result"].get("error"),
            "rf_metadata": rf_meta,
        }

    def simulate_replay_attack(self, old_seq: int) -> Dict[str, Any]:
        """
        Deliberately resend an old sequence number to demonstrate Replay Attack detection.
        """
        packet_dict = self.builder.build_telemetry_packet(
            seq_num=old_seq,
            timestamp=100.0,
            ph=7.0, ec_us_cm=300.0, turbidity_ntu=5.0, temp_c=20.0,
            battery_soc_pct=80.0, solar_power_mw=0.0, latitude=42.58, longitude=-88.43,
            chamber_state="LAKE_MONITORING", quality_flag="VALID"
        )
        rf_meta = self.channel.simulate_transmission(len(packet_dict["frame_bytes"]))
        rf_meta["packet_lost"] = False
        gw_res = self.gateway.process_incoming_frame(packet_dict["frame_bytes"], rf_meta)

        return {
            "replay": True,
            "gw_status": gw_res["status"],
            "gw_error": gw_res["decode_result"].get("error"),
            "rf_metadata": rf_meta,
        }
