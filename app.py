import os
import hmac
import hashlib
import base64
import json
import threading
import random
import matplotlib.pyplot as plt
import time
from dotenv import load_dotenv
from flask import Flask, request, abort
import requests
import paho.mqtt.client as mqtt

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

# ---------- Image Generator (for demonstration) ----------
def generate_graph_image(data_string: str):
    """
    Parses MQTT data and saves a plot to the static folder.
    Assumes data is a comma-separated string of numbers like "10,20,15,30"
    """
    try:
        # Convert payload to list of floats
        data_points = [float(x.strip()) for x in data_string.split(",")]
        
        plt.figure(figsize=(10, 5))
        plt.plot(data_points, marker='o', linestyle='-', color='b')
        plt.title(f"MQTT Data Stream - {time.strftime('%H:%M:%S')}")
        plt.xlabel("Sample Index")
        plt.ylabel("Value")
        plt.grid(True)

        # Ensure static folder exists
        if not os.path.exists('static'):
            os.makedirs('static')

        save_path = "static/graph.png"
        plt.savefig(save_path)
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
        reply_message(reply_token, [{"type": "text", "text": f"You said: {user_text}"}])
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
    payload = [random.randint(0, 10) for _ in range(10)]
    topic = msg.topic
    print(f"[MQTT] Received data from {topic}")
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5050")
    # Generate the graph
    success = generate_graph_image(",".join(map(str, payload)))

    if success:
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
            "text": f"New update from {topic}!"
        }

        broadcast_to_all([text_message, image_message])
    else:
        # Fallback if graph fails
        broadcast_to_all([{"type": "text", "text": f"Data received but graph failed: {payload}"}])


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


@app.route("/", methods=["GET"])
def health():
    return "LINE OA Webhook running.", 200


if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
