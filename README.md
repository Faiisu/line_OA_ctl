# LINE OA Basic Webhook

A minimal Python webhook server for LINE Official Account (LINE OA) using Flask.

---

## Features

- Verifies LINE webhook signatures (HMAC-SHA256)
- Handles incoming message events (text, sticker, and other types)
- Handles follow / unfollow events
- Replies to users via the LINE Messaging API

---

## Prerequisites

- Python 3.10+
- A [LINE Developer](https://developers.line.biz/) account
- A LINE Official Account with the Messaging API channel enabled
- A public HTTPS URL for the webhook (use [ngrok](https://ngrok.com/) for local development)

---

## Setup

### 1. Get LINE credentials

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Create a **Provider** and a **Messaging API** channel
3. Under **Basic settings**, copy the **Channel secret**
4. Under **Messaging API**, issue and copy the **Channel access token**

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
LINE_CHANNEL_SECRET=your_channel_secret_here
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here
PORT=5000
```

Then load them before running:
```bash
export $(cat .env | xargs)
```

### 4. Run the server

```bash
python app.py
```

The server starts on `http://0.0.0.0:5000`.

---

## Expose locally with ngrok (for development)

LINE requires a public HTTPS URL for the webhook.

```bash
ngrok http 5050
```

Copy the `https://...ngrok.io` URL from the output.

---

## Register the webhook URL

1. Go to your channel in the [LINE Developers Console](https://developers.line.biz/console/)
2. Navigate to **Messaging API** tab
3. Set **Webhook URL** to:
   ```
   https://your-ngrok-url.ngrok.io/webhook
   ```
4. Enable **Use webhook**
5. Click **Verify** — you should get a success response

---

## Project structure

```
LineOA_basicCtrl/
├── app.py              # Main Flask webhook server
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── README.md           # This file
```

---

## How it works

### Webhook endpoint: `POST /webhook`

LINE sends all events (messages, follows, etc.) as JSON to this endpoint.

**Signature verification** — every request includes an `X-Line-Signature` header. The server recomputes the HMAC-SHA256 hash of the request body using the Channel Secret and rejects any request that does not match.

**Event routing** — the payload contains a list of events. Each event is dispatched to a handler by type:

| Event type  | Handler           | Behavior                            |
|-------------|-------------------|-------------------------------------|
| `message`   | `handle_message`  | Echoes text; acknowledges stickers  |
| `follow`    | `handle_follow`   | Sends a welcome message             |
| `unfollow`  | `handle_unfollow` | Logs the user ID                    |

### Reply API

Replies use the LINE **Reply Message API** (`/v2/bot/message/reply`) with the `replyToken` from the event. Reply tokens expire after 30 seconds.

---

## Extending the bot

### Add a new event type

```python
def handle_postback(event: dict):
    reply_token = event["replyToken"]
    data = event["postback"]["data"]
    reply_message(reply_token, [{"type": "text", "text": f"Postback: {data}"}])

EVENT_HANDLERS["postback"] = handle_postback
```

### Send a rich message (buttons template)

```python
reply_message(reply_token, [{
    "type": "template",
    "altText": "Choose an option",
    "template": {
        "type": "buttons",
        "text": "What would you like to do?",
        "actions": [
            {"type": "message", "label": "Help", "text": "help"},
            {"type": "uri", "label": "Visit site", "uri": "https://example.com"},
        ]
    }
}])
```

---

## Deploying to production

Any platform that can run Python and expose HTTPS works:

| Platform       | Notes                                      |
|----------------|--------------------------------------------|
| Railway        | `railway up` — auto HTTPS                  |
| Render         | Free tier available, auto HTTPS            |
| Fly.io         | `fly deploy` — global edge                 |
| AWS/GCP/Azure  | Use a load balancer with TLS termination   |

Set `LINE_CHANNEL_SECRET` and `LINE_CHANNEL_ACCESS_TOKEN` as environment variables on the platform, then update the webhook URL in the LINE Developers Console.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| 400 Invalid signature | Check that `LINE_CHANNEL_SECRET` is correct and the raw request body is used for verification |
| 401 Unauthorized on reply | Check that `LINE_CHANNEL_ACCESS_TOKEN` is correct and not expired |
| Webhook verify fails | Make sure the server is reachable at the HTTPS URL and the `/webhook` path returns 200 |
| Reply token expired | Events must be processed within 30 seconds of receipt |
