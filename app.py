import os
import hmac
import hashlib
import base64
import json
import threading
import random
import matplotlib.pyplot as plt
import seaborn as sns
import time
from dotenv import load_dotenv
from flask import Flask, request, abort, send_from_directory
import requests
import paho.mqtt.client as mqtt
from collections import deque

load_dotenv()

app = Flask(__name__)

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "#")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_SSL = os.environ.get("MQTT_SSL", "false").lower() == "true"
MQTT_SSL_VERIFY = os.environ.get("MQTT_SSL_VERIFY", "false").lower() == "true"
MQTT_CA_CERT = None

LINE_REPLY_URL     = "https://api.line.me/v2/bot/message/reply"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# Data storage for sensor logs
MAX_DATA_POINTS = 50  # Keep last 50 readings
sensor_data = {
    'timestamps': deque(maxlen=MAX_DATA_POINTS),
    'pressure': deque(maxlen=MAX_DATA_POINTS),
    'temperature': deque(maxlen=MAX_DATA_POINTS),
    'water_level': deque(maxlen=MAX_DATA_POINTS)
}

# ---------- Image Generator (Aesthetic Version) ----------
def generate_graph_image():
    """
    Generates a beautiful graph from stored sensor data and saves to static folder.
    """
    try:
        # Set non-interactive backend for thread safety
        plt.switch_backend('Agg')
        
        if not sensor_data['timestamps']:
            return False
            
        # Apply Seaborn style for a modern, clean look
        sns.set_theme(style="whitegrid", context="paper")
            
        # Create subplots for each sensor
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
        timestamps = list(sensor_data['timestamps'])
        latest_time = timestamps[-1] if timestamps else time.strftime("%H:%M:%S")
        
        # Main Title
        fig.suptitle(f'Boiler Operation - Latest: {latest_time}', fontsize=16, fontweight='bold', y=0.96)
        
        pressure = list(sensor_data['pressure'])
        temperature = list(sensor_data['temperature'])
        water_level = list(sensor_data['water_level'])
        
        # 1. Pressure plot
        ax1.plot(timestamps, pressure, color='#1f77b4', marker='o', linewidth=2.5, markersize=5)
        ax1.set_title('Pressure', fontweight='bold')
        ax1.set_ylabel('Pressure')
        ax1.set_ylim(0, 20)  # <-- กำหนด Range Pressure: 0 ถึง 20
        
        # 2. Temperature plot
        ax2.plot(timestamps, temperature, color='#d62728', marker='s', linewidth=2.5, markersize=5)
        ax2.set_title('Temperature', fontweight='bold')
        ax2.set_ylabel('Temperature (°C)')
        ax2.set_ylim(150, 200)  # <-- กำหนด Range Temperature: 150 ถึง 200
        
        # 3. Water Level plot
        ax3.plot(timestamps, water_level, color='#2ca02c', marker='^', linewidth=2.5, markersize=5)
        ax3.set_title('Water Level', fontweight='bold')
        ax3.set_xlabel('Time', fontweight='bold')
        ax3.set_ylabel('Water Level')
        ax3.set_ylim(0, 100)  # <-- กำหนด Range Water Level: 0 ถึง 100
        
        # Clean up axes styling
        for ax in (ax1, ax2, ax3):
            ax.tick_params(axis='x', rotation=45)
            # Remove top and right spines (borders) for minimalist look
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            # Make bottom and left spines slightly lighter
            ax.spines['left'].set_color('#CCCCCC')
            ax.spines['bottom'].set_color('#CCCCCC')
        
        # Adjust layout tightly so labels don't get cut off
        plt.tight_layout(rect=[0, 0.02, 1, 0.95])
        plt.subplots_adjust(hspace=0.4)
        
        # Ensure static folder exists
        if not os.path.exists('static'):
            os.makedirs('static')

        save_path = "./static/graph.png"
        # HIGH RESOLUTION SAVE (dpi=300)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close() # Important: Close plot to free up memory
        return True
    except Exception as e:
        print(f"[Error] Failed to generate graph: {e}")
        return False

# ---------- LINE helpers ----------

def _line_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }


def reply_message(reply_token: str, messages: list):
    payload = {"replyToken": reply_token, "messages": messages}
    resp = requests.post(LINE_REPLY_URL, headers=_line_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()


def broadcast_to_all(messages: list):
    payload = {"messages": messages}
    resp = requests.post(LINE_BROADCAST_URL, headers=_line_headers(), json=payload)
    resp.raise_for_status()
    print(f"[LINE] Broadcast sent: {messages}")


# ---------- LINE event handlers ----------

def handle_message(event: dict):
    reply_token = event.get("replyToken")
    msg_type = event["message"]["type"]

    if msg_type == "text":
        user_text = event["message"]["text"]
        
        # Check if user is requesting graph
        if user_text.lower() in ["graph", "chart", "data", "show graph"]:
            # Send the latest graph
            BASE_URL = os.environ.get("BASE_URL", "http://localhost:5050")
            timestamp = int(time.time())
            image_url = f"{BASE_URL}/static/graph.png?t={timestamp}"
            
            image_message = {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url
            }
            
            text_message = {
                "type": "text",
                "text": "Here's the latest sensor data graph:"
            }
            
            reply_message(reply_token, [text_message, image_message])
        elif user_text.lower() in ["latest", "current", "status"]:
            if sensor_data['timestamps']:
                latest_time = sensor_data['timestamps'][-1]
                latest_pressure = sensor_data['pressure'][-1]
                latest_temperature = sensor_data['temperature'][-1]
                latest_water_level = sensor_data['water_level'][-1]
                
                status_message = (
                    f"==[Boiler Status Update]==\n"
                    f"Latest data (as of {latest_time}):\n"
                    f"Pressure: {latest_pressure}\n"
                    f"Temperature: {latest_temperature}°C\n"
                    f"Water Level: {latest_water_level}"
                )
            else:
                status_message = "No sensor data available yet."
            
            reply_message(reply_token, [{"type": "text", "text": status_message}])
        else:
            reply_message(reply_token, [{"type": "text", "text": f"You said: {user_text}. Send 'graph' to see sensor data."}])
    elif msg_type == "sticker":
        reply_message(reply_token, [{"type": "text", "text": "Nice sticker!"}])
    else:
        reply_message(reply_token, [{"type": "text", "text": f"Received a {msg_type} message."}])


def handle_follow(event: dict):
    reply_token = event.get("replyToken")
    reply_message(
        reply_token,
        [{"type": "text", "text": "Thanks for following! You will receive MQTT updates here."}],
    )


def handle_unfollow(event: dict):
    user_id = event["source"].get("userId", "unknown")
    print(f"[LINE] User {user_id} unfollowed.")


EVENT_HANDLERS = {
    "message": handle_message,
    "follow": handle_follow,
    "unfollow": handle_unfollow,
}


# ---------- MQTT ----------

def on_connect(client, _userdata, _flags, reason_code, _properties):
    if not reason_code.is_failure:
        print(f"[MQTT] Connected, subscribing to '{MQTT_TOPIC}'")
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        print(f"[MQTT] Connection failed: {reason_code}")


def on_message(_client, _userdata, msg):
    try:
        # Parse JSON payload
        payload = json.loads(msg.payload.decode('utf-8'))
        topic = msg.topic
        print(f"[MQTT] Received data from {topic}: {payload}")
        
        # Extract sensor values
        pressure = payload.get('Pressure', 0)
        temperature = payload.get('Temperature', 0)
        water_level = payload.get('WaterLevel', 0)
        time_label = payload.get('time', time.strftime("%Y-%m-%d %H:%M:%S"))
        
        # Store data with timestamp label from payload
        sensor_data['timestamps'].append(time_label)
        sensor_data['pressure'].append(pressure)
        sensor_data['temperature'].append(temperature)
        sensor_data['water_level'].append(water_level)
        
        # Generate updated graph
        success = generate_graph_image()
        
        if success:
            BASE_URL = os.environ.get("BASE_URL", "http://localhost:5050")
            # We add a timestamp (cache buster) so LINE doesn't show an old cached image
            timestamp = int(time.time())
            image_url = f"{BASE_URL}/static/graph.png?t={timestamp}"
            
            image_message = {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url
            }
            
            text_message = {
                "type": "text",
                "text": f"New sensor data: Pressure={pressure}, Temperature={temperature}, WaterLevel={water_level}"
            }

            # broadcast_to_all([text_message, image_message])
            
    except json.JSONDecodeError as e:
        print(f"[MQTT] Failed to parse JSON payload: {e}")
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")


def start_mqtt():
    import ssl
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="lineoa-subscriber",
        protocol=mqtt.MQTTv311,
    )
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_SSL:
        cert_reqs = ssl.CERT_REQUIRED if MQTT_SSL_VERIFY else ssl.CERT_NONE
        client.tls_set(ca_certs=MQTT_CA_CERT, cert_reqs=cert_reqs)
        if not MQTT_SSL_VERIFY:
            client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_forever()


# ---------- Flask routes ----------

def verify_signature(body: bytes, signature: str) -> bool:
    hash_val = hmac.new(
        CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if not verify_signature(body, signature):
        abort(400, "Invalid signature")

    payload = json.loads(body)
    for event in payload.get("events", []):
        event_type = event.get("type")
        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            try:
                handler(event)
            except Exception as e:
                print(f"[LINE] Error handling {event_type}: {e}")

    return "OK", 200


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route("/", methods=["GET"])
def health():
    return "LINE OA Webhook running.", 200


if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)