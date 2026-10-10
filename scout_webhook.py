#!/usr/bin/env python3
"""
Python Serverless Webhook: Telegram Wake-on-Call Scout for Railway
Run standalone with Python standard library (zero external dependencies).
Can be deployed to:
- Vercel (Python runtime)
- Render (Free Web Service)
- Supabase Edge Functions / Fly.io / Modal / any micro-container
"""

import os
import sys
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

RAILWAY_GRAPHQL_ENDPOINT = "https://backboard.railway.app/graphql/v2"

# Configuration from Environment Variables
PORT = int(os.getenv("PORT", "8000"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN", "").strip()
RAILWAY_SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "").strip()
RAILWAY_ENVIRONMENT_ID = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()

def wake_railway():
    """Calls Railway GraphQL API to deploy/wake the tracking container."""
    if not (RAILWAY_API_TOKEN and RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID):
        print("[Scout Error] Missing Railway configuration (TOKEN, SERVICE_ID, or ENVIRONMENT_ID).")
        return False, "Missing Railway configuration"

    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
        serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    payload = {
        "query": query,
        "variables": {
            "serviceId": RAILWAY_SERVICE_ID,
            "environmentId": RAILWAY_ENVIRONMENT_ID
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RAILWAY_GRAPHQL_ENDPOINT,
        data=data,
        headers={
            "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if "errors" in res:
                return False, str(res["errors"])
            return True, "Deployment triggered successfully"
    except Exception as e:
        return False, str(e)

def send_telegram_alert(chat_id, text):
    """Sends a Telegram message notifying the group that the tracker is waking up."""
    if not (BOT_TOKEN and chat_id):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Telegram Reply Error] {e}")

class ScoutWebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "service": "telegram-railway-wake-scout",
            "ready": bool(RAILWAY_API_TOKEN and RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID)
        }).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            update = json.loads(post_data.decode("utf-8"))
            msg = update.get("message") or update.get("channel_post") or {}
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            chat_title = chat.get("title", "Telegram Stream")
            text = (msg.get("text") or "").strip().lower()

            is_auto_start = bool(msg.get("video_chat_started") is not None or msg.get("voice_chat_started") is not None)
            is_manual_cmd = text in ("/wake", "/track", "/startstream", "/start_stream")

            if is_auto_start or is_manual_cmd:
                print(f"[Scout] Trigger in [{chat_title}] ({chat_id}) -> {'Auto Live' if is_auto_start else text}")
                success, msg_info = wake_railway()

                if success:
                    print(f"[Scout] ✅ Woke Railway service {RAILWAY_SERVICE_ID}!")
                    alert = (
                        "🎙 **Live Stream Detected!**\n\n"
                        "⚡️ Waking up the **Telegram Stream Tracker** on Railway...\n"
                        "Attendance tracking & recording will attach automatically in ~20s."
                    ) if is_auto_start else "🚀 **Tracker Waking Up on Railway...**"
                    send_telegram_alert(chat_id, alert)
                else:
                    print(f"[Scout] ❌ Failed to wake Railway: {msg_info}")

        except Exception as e:
            print(f"[Scout Error] {e}")

        # Always return 200 to Telegram to acknowledge the webhook
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

if __name__ == "__main__":
    print(f"[Scout Webhook] Starting HTTP listener on port {PORT}...")
    server = HTTPServer(("0.0.0.0", PORT), ScoutWebhookHandler)
    server.serve_forever()
