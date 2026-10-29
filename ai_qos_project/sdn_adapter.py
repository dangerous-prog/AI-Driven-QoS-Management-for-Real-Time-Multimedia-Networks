"""
sdn_adapter.py
==============
Optional Software-Defined Networking (SDN) Controller Adapter for Option B.

Provides an integration boundary between the Dynamic QoS Controller and an
external OpenFlow SDN controller (e.g., Ryu, ONOS, or OpenDaylight).

Capabilities:
1. Probes SDN controller REST API health (e.g., Ryu REST API on port 8080).
2. Falls back seamlessly to Simulated SDN Mode if no live Ryu controller is running.
3. Translates high-level QoS actions (NORMAL, PROTECT_REALTIME, SEVERE_CONGESTION)
   into standard OpenFlow 1.3 Meter and Queue Configuration payloads.
4. Maintains an audit log of all SDN configuration changes.
"""

from __future__ import annotations
import json
import logging
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

import config

logger = logging.getLogger("sdn_adapter")


class SDNControllerAdapter:
    """
    Adapter interfacing the AI QoS controller with an OpenFlow SDN controller.
    """

    def __init__(
        self,
        controller_url: str = config.SDN_CONTROLLER_URL,
        dpid: str = config.SDN_SWITCH_DPID,
        timeout_s: float = 0.5,
    ):
        self.controller_url = controller_url.rstrip("/")
        self.dpid = dpid
        self.timeout_s = timeout_s
        self.live_connected: bool = False
        self.audit_log: List[Dict[str, Any]] = []

        # Probe controller upon initialization
        self.check_connection()

    def check_connection(self) -> bool:
        """Probe if a real SDN controller REST API is reachable."""
        try:
            req = urllib.request.Request(
                f"{self.controller_url}/stats/switches",
                headers={"User-Agent": "AI-QoS-Controller"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status == 200:
                    self.live_connected = True
                    return True
        except Exception:
            self.live_connected = False
        return False

    def build_openflow_qos_payload(self, qos_action: str) -> Dict[str, Any]:
        """
        Map high-level QoS actions to OpenFlow 1.3 Meter & Queue rate configurations.
        """
        action_params = config.QOS_ACTIONS.get(qos_action, config.QOS_ACTIONS["NORMAL"])
        weights = {
            "voice": action_params["voice_weight"],
            "video": action_params["video_weight"],
            "background": action_params["bg_weight"],
        }

        # Rates computed relative to 10 Mbps bottleneck link
        total_kbps = config.LINK_CAPACITY_MBPS * 1000
        rates_kbps = {
            "voice_meter_rate_kbps": int(total_kbps * weights["voice"]),
            "video_meter_rate_kbps": int(total_kbps * weights["video"]),
            "bg_meter_rate_kbps":    int(total_kbps * weights["background"]),
        }

        return {
            "dpid": self.dpid,
            "action": qos_action,
            "mode": action_params["mode"],
            "rates_kbps": rates_kbps,
            "openflow_meters": [
                {
                    "meter_id": 1,
                    "flags": ["KBPS", "BURST"],
                    "bands": [{"type": "DROP", "rate": rates_kbps["voice_meter_rate_kbps"], "burst_size": 32}],
                },
                {
                    "meter_id": 2,
                    "flags": ["KBPS", "BURST"],
                    "bands": [{"type": "DROP", "rate": rates_kbps["video_meter_rate_kbps"], "burst_size": 128}],
                },
                {
                    "meter_id": 3,
                    "flags": ["KBPS", "BURST"],
                    "bands": [{"type": "DROP", "rate": rates_kbps["bg_meter_rate_kbps"], "burst_size": 256}],
                },
            ],
        }

    def apply_action(self, qos_action: str, current_time_s: float = 0.0) -> Dict[str, Any]:
        """
        Apply a QoS action by pushing OpenFlow configuration or logging in simulated mode.
        """
        payload = self.build_openflow_qos_payload(qos_action)
        payload["timestamp_s"] = current_time_s
        payload["live_push_successful"] = False

        if self.live_connected:
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.controller_url}/stats/meterentry/add",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    if resp.status == 200:
                        payload["live_push_successful"] = True
            except Exception as e:
                payload["error"] = str(e)

        self.audit_log.append(payload)
        return payload

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return self.audit_log
