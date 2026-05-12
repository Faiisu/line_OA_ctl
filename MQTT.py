"""
MQTT monitor for WildLife Tracker — publish or subscribe to the device topic.

Install: pip install paho-mqtt
Usage:
  python MQTT.py subscribe          # listen for incoming GPS data
  python MQTT.py publish            # send a test GPS payload
  python MQTT.py publish --lat 13.756 --lon 100.501 --acc 5.0 --alt 10.0
"""

import argparse
import json
import time
import ssl
import threading
import random
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

load_dotenv()

# ── Broker config ──────────────────────────────────────────────────────────
CLIENT_ID = "python-wildlife-monitor"

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "#")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_SSL = os.environ.get("MQTT_SSL", "false").lower() == "true"
MQTT_SSL_VERIFY = os.environ.get("MQTT_SSL_VERIFY", "false").lower() == "true"
MQTT_CA_CERT = None



def build_client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_SSL:
        cert_reqs = ssl.CERT_REQUIRED if MQTT_SSL_VERIFY else ssl.CERT_NONE
        client.tls_set(
            ca_certs=MQTT_CA_CERT,
            cert_reqs=cert_reqs,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        if not MQTT_SSL_VERIFY:
            client.tls_insecure_set(True)
    return client


# ── Subscribe mode ──────────────────────────────────────────────────────────
def on_connect_sub(client, _userdata, _flags, reason_code, _properties):
    if not reason_code.is_failure:
        print(f"[SUB] Connected — subscribing to '{MQTT_TOPIC}'")
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        print(f"[SUB] Connection failed: {reason_code}")


def on_message(_client, _userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        print(
            f"[{time.strftime('%H:%M:%S')}] "
            f"lat={data.get('lat'):.6f}  "
            f"lon={data.get('lon'):.6f}  "
            f"acc={data.get('acc')} m  "
            f"alt={data.get('alt')} m"
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"[MSG] raw: {msg.payload}")


def run_subscribe():
    client = build_client(CLIENT_ID + "-sub")
    client.on_connect = on_connect_sub
    client.on_message = on_message

    print(f"[SUB] Connecting to {MQTT_BROKER}:{MQTT_PORT} …")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever()


# ── Publish mode ────────────────────────────────────────────────────────────
def run_publish(lat: float, lon: float, acc: float, alt: float):
    connected = threading.Event()

    def on_connect_pub(_client, _userdata, _flags, reason_code, _properties):
        if not reason_code.is_failure:
            if not connected.is_set():
                print(f"[PUB] Connected to {MQTT_BROKER} {MQTT_TOPIC}")
                connected.set()
        else:
            print(f"[PUB] Connection failed: {reason_code}")

    client = build_client(CLIENT_ID + "-pub")
    client.on_connect = on_connect_pub

    print(f"[PUB] Connecting to {MQTT_BROKER}:{MQTT_PORT} …")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    if not connected.wait(timeout=10):
        print("[PUB] Timed out waiting for connection")
        client.loop_stop()
        return

    for i in range(100):
        payload = json.dumps({"Pressure": random.randint(10, 16),
                            "Temperature": random.randint(175, 180),
                            "WaterLevel": random.randint(50, 70),
                            "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        info = client.publish(MQTT_TOPIC, payload, qos=1)
        info.wait_for_publish(timeout=5)
        print(f"[PUB] Sent → {payload}  (mid={info.mid})")
        time.sleep(1)

    client.loop_stop()
    client.disconnect()


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WildLife Tracker MQTT monitor")
    parser.add_argument("mode", choices=["subscribe", "publish"],
                        help="subscribe: listen for data  |  publish: send a test payload")
    parser.add_argument("--lat",  type=float, default=13.756331)
    parser.add_argument("--lon",  type=float, default=100.501762)
    parser.add_argument("--acc",  type=float, default=5.0)
    parser.add_argument("--alt",  type=float, default=10.0)

    args = parser.parse_args()

    if args.mode == "subscribe":
        run_subscribe()
    else:
        run_publish(args.lat, args.lon, args.acc, args.alt)
            


if __name__ == "__main__":
    main()
