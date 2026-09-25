"""
LoRa Packet Format, Encryption, and HMAC Authentication.
Demonstrates:
- Structured binary-like packet serialization
- Monotonically increasing frame sequence counter (anti-replay)
- Payload encryption (AES-CTR emulation via secure PRF keystream)
- HMAC-SHA256 truncated Message Integrity Code (MIC, 4 bytes)
- Deliberate packet tampering and replay test helpers
"""
import struct
import hmac
import hashlib
import time
from typing import Dict, Any, Tuple, Optional
from buoy_sim.core.config import BUOY_DEVICE_ID, GATEWAY_DEVICE_ID, LORA_SYNC_WORD, DEFAULT_PSK_HEX

# Message Types
MSG_TYPE_TELEMETRY = 0x01
MSG_TYPE_ACK = 0x02
MSG_TYPE_COMMAND = 0x03
MSG_TYPE_COMMAND_RESP = 0x04

# Remote Command Identifiers
CMD_TRIGGER_MEASUREMENT = 0x10
CMD_CHANGE_INTERVAL = 0x11
CMD_REQUEST_STATUS = 0x12
CMD_INITIATE_CHAMBER = 0x13
CMD_LOW_POWER_MODE = 0x14

COMMAND_NAMES = {
    CMD_TRIGGER_MEASUREMENT: "trigger_measurement",
    CMD_CHANGE_INTERVAL: "change_sampling_interval",
    CMD_REQUEST_STATUS: "request_status",
    CMD_INITIATE_CHAMBER: "initiate_chamber_cycle",
    CMD_LOW_POWER_MODE: "enter_low_power_mode",
}

class LoRaSecurity:
    def __init__(self, psk_hex: str = DEFAULT_PSK_HEX):
        self.key_bytes = bytes.fromhex(psk_hex)

    def compute_mic(self, header_bytes: bytes, payload_bytes: bytes) -> bytes:
        """Compute 4-byte truncated HMAC-SHA256 Message Integrity Code."""
        h = hmac.new(self.key_bytes, header_bytes + payload_bytes, hashlib.sha256)
        return h.digest()[:4]

    def _generate_keystream(self, seq_num: int, length: int) -> bytes:
        """Derive reproducible stream cipher keystream from PSK and sequence number."""
        counter_bytes = struct.pack(">I", seq_num)
        derived = hashlib.sha256(self.key_bytes + counter_bytes).digest()
        keystream = bytearray()
        block_idx = 0
        while len(keystream) < length:
            block = hashlib.sha256(derived + struct.pack(">I", block_idx)).digest()
            keystream.extend(block)
            block_idx += 1
        return bytes(keystream[:length])

    def encrypt_payload(self, plaintext: bytes, seq_num: int) -> bytes:
        keystream = self._generate_keystream(seq_num, len(plaintext))
        return bytes(b ^ k for b, k in zip(plaintext, keystream))

    def decrypt_payload(self, ciphertext: bytes, seq_num: int) -> bytes:
        return self.encrypt_payload(ciphertext, seq_num)

class LoRaPacketBuilder:
    def __init__(self, security: Optional[LoRaSecurity] = None):
        self.security = security or LoRaSecurity()

    def build_telemetry_packet(
        self,
        seq_num: int,
        timestamp: float,
        ph: float,
        ec_us_cm: float,
        turbidity_ntu: float,
        temp_c: float,
        battery_soc_pct: float,
        solar_power_mw: float,
        latitude: float,
        longitude: float,
        chamber_state: str,
        quality_flag: str
    ) -> Dict[str, Any]:
        """
        Build authenticated and encrypted LoRa telemetry packet.
        """
        # Pack Header: Sync(1B) + Version(1B) + BuoyID(2B) + GatewayID(2B) + MsgType(1B) + Seq(4B) + Time(4B)
        # 15 bytes
        header = struct.pack(
            ">BBHHBII",
            LORA_SYNC_WORD,
            0x01,  # Protocol version
            BUOY_DEVICE_ID,
            GATEWAY_DEVICE_ID,
            MSG_TYPE_TELEMETRY,
            seq_num,
            int(timestamp)
        )

        # Pack Plaintext Payload:
        # pH*100 (H), EC (H), Turbidity*10 (H), Temp*100 (h), SOC*10 (H), Solar_mw (H),
        # Lat*1e6 (i), Lon*1e6 (i), State_code (B), Quality_code (B) -> 26 bytes
        state_map = {"LAKE_MONITORING": 0, "CHAMBER_FILL": 1, "STABILIZE": 2, "MEASURE": 3, "FLUSH": 4}
        state_code = state_map.get(chamber_state, 0)
        quality_code = 1 if quality_flag == "VALID" else 0

        raw_payload = struct.pack(
            ">HHHhHHiibb",
            int(round(ph * 100)),
            int(round(min(65535, ec_us_cm))),
            int(round(min(65535, turbidity_ntu * 10))),
            int(round(temp_c * 100)),
            int(round(battery_soc_pct * 10)),
            int(round(min(65535, solar_power_mw))),
            int(round(latitude * 1e6)),
            int(round(longitude * 1e6)),
            state_code,
            quality_code
        )

        # Encrypt payload
        encrypted_payload = self.security.encrypt_payload(raw_payload, seq_num)

        # Compute HMAC-SHA256 MIC over header + encrypted payload
        mic = self.security.compute_mic(header, encrypted_payload)

        # Complete packet frame
        raw_frame = header + encrypted_payload + mic

        return {
            "seq_num": seq_num,
            "timestamp": timestamp,
            "msg_type": "TELEMETRY",
            "header_hex": header.hex(),
            "payload_hex": encrypted_payload.hex(),
            "mic_hex": mic.hex(),
            "frame_bytes": raw_frame,
            "frame_hex": raw_frame.hex(),
            "size_bytes": len(raw_frame),
            "plaintext": {
                "ph": round(ph, 3),
                "ec_us_cm": round(ec_us_cm, 1),
                "turbidity_ntu": round(turbidity_ntu, 2),
                "temp_c": round(temp_c, 2),
                "soc_pct": round(battery_soc_pct, 1),
                "solar_power_mw": round(solar_power_mw, 1),
                "latitude": latitude,
                "longitude": longitude,
                "chamber_state": chamber_state,
                "quality_flag": quality_flag,
            }
        }

    def decode_packet(self, frame_bytes: bytes, last_seen_seq: int) -> Dict[str, Any]:
        """
        Validate, verify MIC, check replay, and decrypt incoming frame.
        """
        if len(frame_bytes) < 19:  # Min header (15) + MIC (4)
            return {"valid": False, "error": "PACKET_TOO_SHORT"}

        header = frame_bytes[:15]
        mic = frame_bytes[-4:]
        encrypted_payload = frame_bytes[15:-4]

        sync, ver, src_id, dst_id, msg_type, seq_num, ts = struct.unpack(">BBHHBII", header)

        if sync != LORA_SYNC_WORD:
            return {"valid": False, "error": "INVALID_SYNC_WORD", "seq_num": seq_num}

        # 1. Replay check
        if seq_num <= last_seen_seq and msg_type == MSG_TYPE_TELEMETRY:
            return {
                "valid": False,
                "error": "REPLAY_ATTACK_DETECTED",
                "seq_num": seq_num,
                "last_seen_seq": last_seen_seq,
                "mic_hex": mic.hex(),
            }

        # 2. MIC Verification (HMAC-SHA256)
        expected_mic = self.security.compute_mic(header, encrypted_payload)
        if mic != expected_mic:
            return {
                "valid": False,
                "error": "MIC_VERIFICATION_FAILED_INTEGRITY_COMPROMISED",
                "seq_num": seq_num,
                "provided_mic": mic.hex(),
                "expected_mic": expected_mic.hex(),
            }

        # 3. Decrypt Payload
        decrypted = self.security.decrypt_payload(encrypted_payload, seq_num)

        if msg_type == MSG_TYPE_TELEMETRY and len(decrypted) >= 22:
            ph_x100, ec, turb_x10, temp_x100, soc_x10, solar_mw, lat_x1e6, lon_x1e6, state_c, qual_c = struct.unpack(
                ">HHHhHHiibb", decrypted
            )
            state_names = ["LAKE_MONITORING", "CHAMBER_FILL", "STABILIZE", "MEASURE", "FLUSH"]
            chamber_name = state_names[state_c] if 0 <= state_c < len(state_names) else "UNKNOWN"
            qual_name = "VALID" if qual_c == 1 else "INVALID"

            return {
                "valid": True,
                "error": None,
                "msg_type": "TELEMETRY",
                "seq_num": seq_num,
                "timestamp": ts,
                "src_id": hex(src_id),
                "dst_id": hex(dst_id),
                "mic_verified": True,
                "data": {
                    "ph": round(ph_x100 / 100.0, 3),
                    "ec_us_cm": round(float(ec), 1),
                    "turbidity_ntu": round(turb_x10 / 10.0, 2),
                    "temp_c": round(temp_x100 / 100.0, 2),
                    "soc_pct": round(soc_x10 / 10.0, 1),
                    "solar_power_mw": round(float(solar_mw), 1),
                    "latitude": round(lat_x1e6 / 1e6, 6),
                    "longitude": round(lon_x1e6 / 1e6, 6),
                    "chamber_state": chamber_name,
                    "quality_flag": qual_name,
                }
            }

        elif msg_type == MSG_TYPE_ACK:
            ack_seq = struct.unpack(">I", decrypted[:4])[0] if len(decrypted) >= 4 else seq_num
            return {
                "valid": True,
                "error": None,
                "msg_type": "ACK",
                "seq_num": seq_num,
                "ack_for_seq": ack_seq,
                "mic_verified": True,
            }

        elif msg_type == MSG_TYPE_COMMAND and len(decrypted) >= 5:
            cmd_id, cmd_arg = struct.unpack(">BI", decrypted[:5])
            cmd_name = COMMAND_NAMES.get(cmd_id, f"UNKNOWN_{cmd_id}")
            return {
                "valid": True,
                "error": None,
                "msg_type": "COMMAND",
                "seq_num": seq_num,
                "cmd_id": cmd_id,
                "cmd_name": cmd_name,
                "cmd_arg": cmd_arg,
                "mic_verified": True,
            }

        return {"valid": True, "error": None, "msg_type": f"TYPE_{msg_type}", "seq_num": seq_num}

    def build_ack_packet(self, ack_for_seq: int, gateway_seq: int) -> bytes:
        """Create authenticated ACK packet from Gateway to Buoy."""
        header = struct.pack(
            ">BBHHBII",
            LORA_SYNC_WORD, 0x01, GATEWAY_DEVICE_ID, BUOY_DEVICE_ID,
            MSG_TYPE_ACK, gateway_seq, int(time.time())
        )
        payload = struct.pack(">I", ack_for_seq)
        enc_payload = self.security.encrypt_payload(payload, gateway_seq)
        mic = self.security.compute_mic(header, enc_payload)
        return header + enc_payload + mic

    def build_command_packet(self, cmd_id: int, cmd_arg: int, gateway_seq: int) -> bytes:
        """Create authenticated Command packet from Gateway to Buoy."""
        header = struct.pack(
            ">BBHHBII",
            LORA_SYNC_WORD, 0x01, GATEWAY_DEVICE_ID, BUOY_DEVICE_ID,
            MSG_TYPE_COMMAND, gateway_seq, int(time.time())
        )
        payload = struct.pack(">BI", cmd_id, cmd_arg)
        enc_payload = self.security.encrypt_payload(payload, gateway_seq)
        mic = self.security.compute_mic(header, enc_payload)
        return header + enc_payload + mic
