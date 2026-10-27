#!/usr/bin/env python3
"""
Wake-on-Call Diagnostic & Setup Helper
1. Inspects your current Telegram Bot Webhook status.
2. Validates Railway API credentials (RAILWAY_API_TOKEN, RAILWAY_SERVICE_ID, RAILWAY_ENVIRONMENT_ID).
3. Tests waking/redeploying your Railway service via GraphQL API.
4. Allows you to set or clear the Telegram Webhook URL pointing to your Cloudflare Worker / Scout.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# Load .env
def load_env():
    env = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = load_env()
BOT_TOKEN = os.getenv("BOT_TOKEN", ENV.get("BOT_TOKEN", "")).strip()
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN", ENV.get("RAILWAY_API_TOKEN", "")).strip()
RAILWAY_SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", ENV.get("RAILWAY_SERVICE_ID", "")).strip()
RAILWAY_ENVIRONMENT_ID = os.getenv("RAILWAY_ENVIRONMENT_ID", ENV.get("RAILWAY_ENVIRONMENT_ID", "")).strip()

def check_bot_webhook():
    print("\n" + "=" * 60)
    print("1. TELEGRAM BOT WEBHOOK STATUS")
    print("=" * 60)
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN is missing in .env")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            res = data.get("result", {})
            wh_url = res.get("url", "")
            if wh_url:
                print(f"✅ Active Webhook URL: {wh_url}")
                print(f"   Pending Updates: {res.get('pending_update_count', 0)}")
                if res.get("last_error_message"):
                    print(f"   ⚠️ Last Error: {res.get('last_error_message')}")
            else:
                print("⚠️ No Webhook URL is currently registered on Telegram.")
                print("   Telegram cannot push 'video_chat_started' to wake Railway when offline.")
                print("   Deploy 'scout_cloudflare_worker.js' to Cloudflare Workers, then register its URL.")
    except Exception as e:
        print(f"❌ Error querying Telegram API: {e}")

def test_wake_railway():
    print("\n" + "=" * 60)
    print("2. RAILWAY WAKE-ON-CALL API TEST")
    print("=" * 60)
    if not (RAILWAY_API_TOKEN and RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID):
        print("⚠️ Missing Railway credentials:")
        print(f"   • RAILWAY_API_TOKEN:      {'✅ Present' if RAILWAY_API_TOKEN else '❌ Missing'}")
        print(f"   • RAILWAY_SERVICE_ID:    {'✅ Present' if RAILWAY_SERVICE_ID else '❌ Missing'}")
        print(f"   • RAILWAY_ENVIRONMENT_ID: {'✅ Present' if RAILWAY_ENVIRONMENT_ID else '❌ Missing'}")
        print("\nTo enable programmatic scale-to-zero and wake-on-call:")
        print("1. Generate RAILWAY_API_TOKEN at: Railway Dashboard -> Account Settings -> Tokens")
        print("2. Copy RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID from your Railway project URL:")
        print("   railway.com/project/<PROJECT_ID>/service/<SERVICE_ID>?environmentId=<ENVIRONMENT_ID>")
        return False

    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
        serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    payload = json.dumps({
        "query": query,
        "variables": {
            "serviceId": RAILWAY_SERVICE_ID,
            "environmentId": RAILWAY_ENVIRONMENT_ID
        }
    }).encode("utf-8")

    endpoints = [
        "https://backboard.railway.app/graphql/v2",
        "https://backboard.railway.com/graphql/v2"
    ]

    for ep in endpoints:
        req = urllib.request.Request(
            ep,
            data=payload,
            headers={
                "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
                "Project-Access-Token": RAILWAY_API_TOKEN,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode())
                if "errors" in res and res["errors"]:
                    print(f"❌ Railway API error from {ep}: {res['errors']}")
                    continue
                print(f"✅ Success! Woke Railway service {RAILWAY_SERVICE_ID} via {ep}!")
                return True
        except Exception as e:
            print(f"⚠️ Failed via {ep}: {e}")
    return False

def set_webhook(worker_url):
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN is missing in .env")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={worker_url}&drop_pending_updates=true&allowed_updates=[\"message\",\"channel_post\"]"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                print(f"✅ Webhook successfully set to: {worker_url}")
            else:
                print(f"❌ Failed to set webhook: {data}")
    except Exception as e:
        print(f"❌ Error setting webhook: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--set-webhook":
        set_webhook(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--wake":
        test_wake_railway()
    else:
        check_bot_webhook()
        test_wake_railway()
        print("\nUsage:")
        print("  python setup_wake_scout.py                         # Run diagnostics")
        print("  python setup_wake_scout.py --wake                  # Test waking Railway container directly")
        print("  python setup_wake_scout.py --set-webhook <URL>     # Register your Cloudflare Scout URL on Telegram")
        print("=" * 60 + "\n")
