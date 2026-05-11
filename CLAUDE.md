# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python app.py          # webhook server + MQTT listener
python MQTT.py subscribe   # subscribe to MQTT topic (debug/monitor)
python MQTT.py publish     # publish a test GPS payload
```

For local development, expose via ngrok and set the webhook URL in LINE Developers Console:
```bash
ngrok http 5050
# Webhook URL: https://<ngrok-url>/webhook
```

## Environment variables

All config lives in `.env` (loaded automatically via `load_dotenv()`):

| Variable | Purpose |
|---|---|
| `LINE_CHANNEL_SECRET` | HMAC-SHA256 signature verification |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API auth |
| `MQTT_BROKER` | Broker hostname |
| `MQTT_PORT` | `8883` for TLS (HiveMQ), `1883` for plain |
| `MQTT_TOPIC` | Topic to subscribe/publish |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | Broker credentials |
| `PORT` | Flask port (default 5000) |

## Architecture

**`app.py`** — the main process. Runs two concurrent components:
- A **Flask webhook server** that receives LINE events, verifies HMAC-SHA256 signatures, and dispatches to handlers in `EVENT_HANDLERS`.
- A **MQTT subscriber** running in a daemon thread (`start_mqtt`). On any incoming MQTT message, `on_message` calls `broadcast_to_all` which posts to LINE's `/v2/bot/message/broadcast` API — reaching all followers without tracking user IDs.

**`MQTT.py`** — standalone CLI tool (subscribe or publish) for testing/monitoring the MQTT broker directly. Uses hardcoded credentials and is independent of `app.py`.

**TLS**: port 8883 triggers `client.tls_set()` automatically in both `app.py` and `MQTT.py`. Required for broker.hivemq.com.

**Adding a new LINE event type**: define a handler function and register it in `EVENT_HANDLERS` dict — no other wiring needed.
