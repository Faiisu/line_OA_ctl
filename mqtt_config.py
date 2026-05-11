"""
Loads MQTT broker configuration from either a credential JSON file
(MQTT_CREDENTIAL_FILE) or individual environment variables.

Credential JSON format (from Advantech/RabbitMQ device):
{
  "protocols": {
    "mqtt": {
      "host": "...", "port": 8883, "ssl": true,
      "username": "...", "password": "..."
    }
  },
  "x509": { "ca": "<base64-encoded PEM chain>" }
}
"""

import os
import json
import base64
import tempfile


def load_mqtt_config() -> dict:
    cred_file = os.environ.get("MQTT_CREDENTIAL_FILE")

    if cred_file:
        with open(cred_file) as f:
            data = json.load(f)

        mqtt_cred = data["protocols"]["mqtt"]
        config = {
            "broker":     mqtt_cred["host"],
            "port":       int(mqtt_cred["port"]),
            "ssl":        bool(mqtt_cred.get("ssl", False)),
            "ssl_verify": True,
            "username":   mqtt_cred.get("username", ""),
            "password":   mqtt_cred.get("password", ""),
            "ca_cert":    None,
        }

        ca_b64 = data.get("x509", {}).get("ca")
        if ca_b64 and config["ssl"]:
            ca_pem = base64.b64decode(ca_b64)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
            tmp.write(ca_pem)
            tmp.close()
            config["ca_cert"] = tmp.name
            print(f"[MQTT] Using CA cert from credential file → {tmp.name}")
    else:
        config = {
            "broker":     os.environ.get("MQTT_BROKER", "localhost"),
            "port":       int(os.environ.get("MQTT_PORT", 1883)),
            "ssl":        os.environ.get("MQTT_SSL", "false").lower() == "true",
            "ssl_verify": os.environ.get("MQTT_SSL_VERIFY", "true").lower() == "true",
            "username":   os.environ.get("MQTT_USERNAME", ""),
            "password":   os.environ.get("MQTT_PASSWORD", ""),
            "ca_cert":    None,
        }

    config["topic"] = os.environ.get("MQTT_TOPIC", "#")
    return config
