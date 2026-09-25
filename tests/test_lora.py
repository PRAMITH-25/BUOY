import unittest
from buoy_sim.lora.packet import LoRaPacketBuilder, LoRaSecurity, CMD_TRIGGER_MEASUREMENT
from buoy_sim.lora.gateway import LoRaGateway
from buoy_sim.lora.buoy_node import BuoyLoRaNode
from buoy_sim.lora.channel import LoRaChannelModel

class TestLoRa(unittest.TestCase):
    def setUp(self):
        self.sec = LoRaSecurity()
        self.builder = LoRaPacketBuilder(self.sec)
        self.gateway = LoRaGateway()
        self.channel = LoRaChannelModel()
        self.channel.config["packet_loss_base_rate"] = 0.0
        self.node = BuoyLoRaNode(gateway=self.gateway, channel=self.channel)

    def test_packet_encryption_and_mic_acceptance(self):
        telemetry = {
            "timestamp": 12345.0, "ph": 7.62, "ec_us_cm": 382.0, "turbidity_ntu": 8.4,
            "temp_c": 21.4, "soc_pct": 82.5, "solar_power_mw": 450.0,
            "latitude": 42.5872, "longitude": -88.4334,
            "chamber_state": "MEASURE", "quality_flag": "VALID"
        }
        tx_res = self.node.transmit_telemetry(telemetry)
        self.assertTrue(tx_res["acked"])
        self.assertEqual(tx_res["gateway_response"]["status"], "ACCEPTED")

        # Verify decrypted payload
        dec = tx_res["gateway_response"]["decode_result"]["data"]
        self.assertAlmostEqual(dec["ph"], 7.62, places=2)
        self.assertAlmostEqual(dec["turbidity_ntu"], 8.4, places=1)

    def test_tampered_packet_rejection(self):
        t_res = self.node.simulate_tampered_packet({"timestamp": 1000.0})
        self.assertEqual(t_res["gw_status"], "REJECTED")
        self.assertIn("MIC_VERIFICATION_FAILED", str(t_res["gw_error"]))

    def test_replay_attack_rejection(self):
        # Sequence 1 already received
        self.gateway.last_seen_seq_num = 10
        r_res = self.node.simulate_replay_attack(old_seq=5)
        self.assertEqual(r_res["gw_status"], "REJECTED")
        self.assertEqual(r_res["gw_error"], "REPLAY_ATTACK_DETECTED")

    def test_gateway_downlink_command(self):
        self.gateway.queue_downlink_command(CMD_TRIGGER_MEASUREMENT)
        tx_res = self.node.transmit_telemetry({"timestamp": 2000.0})
        self.assertIsNotNone(tx_res["downlink_command"])
        self.assertEqual(tx_res["downlink_command"]["cmd_id"], CMD_TRIGGER_MEASUREMENT)
