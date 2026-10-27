"""
Railway Lifecycle & Cost-Optimization Controller
Manages:
1. Self-termination (scale-to-zero) via Railway GraphQL API after stream ends and reports are dispatched.
2. Idle watchdog: Shuts down the container if woken up by false alarm and no stream begins within IDLE_TIMEOUT_MINUTES.
"""

import os
import sys
import json
import asyncio
import datetime
import urllib.request
import urllib.error

RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

# Configuration
# Active by default: Shuts down container after IDLE_TIMEOUT_MINUTES of no stream or web activity
AUTO_SHUTDOWN_ENABLED = os.getenv("RAILWAY_AUTO_SHUTDOWN", "True").lower() in ("true", "1", "yes")
_raw_idle = os.getenv("IDLE_SHUTDOWN_MINUTES", "15").strip()
try:
    IDLE_TIMEOUT_MINUTES = max(1, int(_raw_idle))
except ValueError:
    IDLE_TIMEOUT_MINUTES = 15

# Railway Auto-injected or User-provided Variables
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN", "").strip()
RAILWAY_DEPLOYMENT_ID = os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip()
RAILWAY_SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "").strip()
RAILWAY_ENVIRONMENT_ID = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
RAILWAY_PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID", "").strip()

# Internal State
_stream_ever_detected = False
_last_stream_end_time = None
_boot_timestamp = datetime.datetime.now(datetime.timezone.utc)
_last_web_activity_time = datetime.datetime.now(datetime.timezone.utc)
_shutdown_in_progress = False
_cleanup_callbacks = []

def is_railway_environment() -> bool:
    """Detects if running inside a Railway container."""
    return bool(RAILWAY_DEPLOYMENT_ID or RAILWAY_SERVICE_ID or os.getenv("RAILWAY_STATIC_URL"))

def ensure_wake_webhook_registered() -> str:
    """
    Checks Telegram Bot API getWebhookInfo. If WAKE_WEBHOOK_URL or CLOUDFLARE_WORKER_URL
    is configured in environment variables and not yet set on Telegram, automatically
    registers it via setWebhook so Cloudflare Wake-on-Call is always active.
    Returns the currently active webhook URL (or empty string if none).
    """
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        return ""
    configured_worker_url = (
        os.getenv("WAKE_WEBHOOK_URL", "").strip()
        or os.getenv("CLOUDFLARE_WORKER_URL", "").strip()
        or "https://telegram-stream-scout.matthewobanla.workers.dev"
    )
    info_url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    try:
        req = urllib.request.Request(info_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            wh_url = data.get("result", {}).get("url", "").strip()
            if wh_url:
                return wh_url
    except Exception as e:
        print(f"[Railway Lifecycle] Webhook check notice: {e}", flush=True)

    if configured_worker_url:
        try:
            import urllib.parse
            encoded_url = urllib.parse.quote(configured_worker_url, safe=":/?&=")
            set_url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={encoded_url}&allowed_updates=%5B%22message%22%2C%22channel_post%22%5D"
            req = urllib.request.Request(set_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    print(f"[Railway Lifecycle] ✅ Auto-registered Cloudflare Wake Webhook: {configured_worker_url}", flush=True)
                    return configured_worker_url
        except Exception as e:
            print(f"[Railway Lifecycle] Auto-register webhook notice: {e}", flush=True)
    return ""

def register_cleanup_callback(cb):
    """Registers an async or sync callback to run before container termination."""
    if cb not in _cleanup_callbacks:
        _cleanup_callbacks.append(cb)

def mark_web_activity():
    """Signals the idle watchdog that an operator is actively using the dashboard."""
    global _last_web_activity_time
    _last_web_activity_time = datetime.datetime.now(datetime.timezone.utc)

def mark_stream_active():
    """Signals the idle guard that a real stream was active, preventing early idle shutdown."""
    global _stream_ever_detected, _last_stream_end_time
    _stream_ever_detected = True
    _last_stream_end_time = None

def mark_stream_ended():
    """Signals that a stream has ended, starting post-stream idle grace period."""
    global _last_stream_end_time
    _last_stream_end_time = datetime.datetime.now(datetime.timezone.utc)

def remove_railway_deployment(deployment_id: str, api_token: str) -> bool:
    """
    Calls Railway GraphQL API to stop or remove the active deployment.
    Tries deploymentStop first, then falls back to deploymentRemove.
    Supports both Account Tokens (Authorization: Bearer) and Project Tokens (Project-Access-Token).
    Supports both railway.com and railway.app endpoints.
    """
    endpoints = [
        "https://backboard.railway.com/graphql/v2",
        "https://backboard.railway.app/graphql/v2"
    ]
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    auth_variants = [
        ("Bearer", {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json", "User-Agent": USER_AGENT}),
        ("ProjectToken", {"Project-Access-Token": api_token, "Content-Type": "application/json", "User-Agent": USER_AGENT}),
        ("Combined", {"Authorization": f"Bearer {api_token}", "Project-Access-Token": api_token, "Content-Type": "application/json", "User-Agent": USER_AGENT})
    ]

    for op_name, query_body in [
        ("deploymentStop", "mutation DeploymentStop($id: String!) { deploymentStop(id: $id) }"),
        ("deploymentRemove", "mutation DeploymentRemove($id: String!) { deploymentRemove(id: $id) }"),
    ]:
        payload = {
            "query": query_body,
            "variables": {"id": deployment_id}
        }
        data = json.dumps(payload).encode("utf-8")
        
        for ep in endpoints:
            for auth_label, headers in auth_variants:
                req = urllib.request.Request(
                    ep,
                    data=data,
                    headers=headers
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        if "errors" in res:
                            print(f"[Railway Lifecycle Notice] {op_name} via {ep} ({auth_label}) errors: {res['errors']}")
                            continue
                        print(f"[Railway Lifecycle] ✅ {op_name} succeeded via {ep} using {auth_label} for {deployment_id}!")
                        return True
                except urllib.error.HTTPError as e:
                    err_msg = ""
                    try:
                        err_msg = e.read().decode("utf-8")[:150]
                    except Exception:
                        pass
                    print(f"[Railway Lifecycle Notice] {op_name} via {ep} ({auth_label}) HTTP {e.code}: {err_msg or e.reason}")
                except Exception as e:
                    print(f"[Railway Lifecycle Notice] {op_name} via {ep} ({auth_label}) error: {e}")

    return False

def fetch_active_deployment_id(project_id: str, service_id: str, api_token: str) -> str:
    """Queries Railway GraphQL API for the currently active deployment ID."""
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    query = """
    query GetDeployments($projectId: String!, $serviceId: String!) {
        deployments(input: { projectId: $projectId, serviceId: $serviceId }, first: 1) {
            edges {
                node {
                    id
                    status
                }
            }
        }
    }
    """
    payload = {
        "query": query,
        "variables": {"projectId": project_id, "serviceId": service_id}
    }
    data = json.dumps(payload).encode("utf-8")
    
    for ep in ["https://backboard.railway.com/graphql/v2", "https://backboard.railway.app/graphql/v2"]:
        for headers in [
            {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            {"Project-Access-Token": api_token, "Content-Type": "application/json", "User-Agent": USER_AGENT}
        ]:
            req = urllib.request.Request(
                ep,
                data=data,
                headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    edges = res.get("data", {}).get("deployments", {}).get("edges", [])
                    if edges:
                        return edges[0].get("node", {}).get("id", "")
            except Exception as e:
                print(f"[Railway Lifecycle] Deployment lookup notice ({ep}): {e}")
    return ""

async def trigger_post_stream_shutdown(delay_seconds: int = 25, force: bool = False):
    """
    Executed when the idle timeout is reached or when manually triggered via /shutdown.
    Waits for network transfers to complete, ensures the Wake Webhook is registered if configured,
    then shuts down the Railway container.
    """
    global _shutdown_in_progress
    if _shutdown_in_progress or (not AUTO_SHUTDOWN_ENABLED and not force):
        return

    _shutdown_in_progress = True
    loop = asyncio.get_running_loop()

    wh_url = await loop.run_in_executor(None, ensure_wake_webhook_registered)
    if wh_url:
        print(f"[Railway Lifecycle] ✅ Verified Telegram Wake-on-Call Webhook is active: {wh_url}", flush=True)
    else:
        print(
            "[Railway Lifecycle WARNING] ⚠️ No Telegram Webhook URL is currently registered on Bot API! "
            "Register your Cloudflare Worker URL via: python3 setup_wake_scout.py --set-webhook <WORKER_URL>",
            flush=True
        )

    print(f"\n[Railway Lifecycle] 🛑 Scheduling container shutdown in {delay_seconds}s to conserve compute billing...", flush=True)
    
    await asyncio.sleep(delay_seconds)

    target_dep_id = RAILWAY_DEPLOYMENT_ID
    if not target_dep_id and RAILWAY_API_TOKEN and (RAILWAY_SERVICE_ID and RAILWAY_PROJECT_ID):
        print("[Railway Lifecycle] Querying Railway for active deployment ID...", flush=True)
        target_dep_id = await loop.run_in_executor(None, fetch_active_deployment_id, RAILWAY_PROJECT_ID, RAILWAY_SERVICE_ID, RAILWAY_API_TOKEN)

    if RAILWAY_API_TOKEN and target_dep_id:
        print(f"[Railway Lifecycle] Calling Railway API to terminate deployment {target_dep_id}...", flush=True)
        success = await loop.run_in_executor(None, remove_railway_deployment, target_dep_id, RAILWAY_API_TOKEN)
        if success:
            print("[Railway Lifecycle] ✅ Deployment cancellation requested. Container will terminate immediately.", flush=True)
        else:
            print("[Railway Lifecycle] ⚠️ API request failed. Exiting process with os._exit(0)...", flush=True)
    else:
        if not RAILWAY_API_TOKEN:
            print("[Railway Lifecycle WARNING] ⚠️ RAILWAY_API_TOKEN is not set in environment variables!", flush=True)
            print("[Railway Lifecycle WARNING] Programmatic scale-to-zero requires RAILWAY_API_TOKEN in Railway service settings.", flush=True)
    # Execute any registered cleanup callbacks before terminating process
    for cb in _cleanup_callbacks:
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb()
            else:
                cb()
        except Exception as e:
            print(f"[Railway Lifecycle Cleanup Warning] {e}", flush=True)

    # Terminate process
    os._exit(0)

async def idle_watchdog_loop(tracker_manager_ref):
    """
    Monitors container uptime and idle activity:
    1. If no live stream begins within IDLE_TIMEOUT_MINUTES (15m) of boot, powers off the container.
    2. If a stream began and ended, and no new stream starts within IDLE_TIMEOUT_MINUTES (15m), powers off the container.
    3. Keeps container alive if an operator is actively using the web dashboard.
    """
    if not AUTO_SHUTDOWN_ENABLED:
        print("[Railway Lifecycle] 🌐 Auto-shutdown is disabled. Web dashboard & tracker will stay online 24/7.", flush=True)
        while True:
            await asyncio.sleep(3600)

    loop = asyncio.get_running_loop()
    wh_url = await loop.run_in_executor(None, ensure_wake_webhook_registered)
    print(f"[Railway Lifecycle] 🛡 Idle Watchdog active (Will power off after {IDLE_TIMEOUT_MINUTES}m of no live call or web activity).", flush=True)
    if wh_url:
        print(f"[Railway Lifecycle] ⚡️ Cloudflare Wake-on-Call Webhook active: {wh_url}", flush=True)
    else:
        print(
            "[Railway Lifecycle Notice] ⚠️ No Telegram Webhook URL is currently registered on Bot API. "
            "Set WAKE_WEBHOOK_URL in Railway variables or run: python3 setup_wake_scout.py --set-webhook <WORKER_URL>",
            flush=True
        )

    while True:
        try:
            await asyncio.sleep(60)

            # Check if any stream is currently active
            has_active_tracker = len(tracker_manager_ref.get_all_active()) > 0
            if has_active_tracker:
                mark_stream_active()
                continue

            now = datetime.datetime.now(datetime.timezone.utc)

            # Prevent shutdown if an operator has interacted with the dashboard recently
            web_idle_sec = (now - _last_web_activity_time).total_seconds()
            if web_idle_sec < IDLE_TIMEOUT_MINUTES * 60:
                continue

            # Scenario 1: A stream occurred earlier and has now concluded
            if _stream_ever_detected:
                if _last_stream_end_time is None:
                    mark_stream_ended()
                else:
                    idle_since_end = (now - _last_stream_end_time).total_seconds()
                    if idle_since_end >= IDLE_TIMEOUT_MINUTES * 60:
                        print(f"\n[Railway Lifecycle] ⏰ Post-stream idle timeout reached ({IDLE_TIMEOUT_MINUTES} mins after call ended).", flush=True)
                        print("[Railway Lifecycle] Shutting down container to conserve compute hours...", flush=True)
                        await trigger_post_stream_shutdown(delay_seconds=5)
                        break
                continue

            # Scenario 2: Container booted up, but no stream started within IDLE_TIMEOUT_MINUTES
            uptime = (now - _boot_timestamp).total_seconds()
            if uptime >= IDLE_TIMEOUT_MINUTES * 60:
                print(f"\n[Railway Lifecycle] ⏰ Idle timeout reached ({IDLE_TIMEOUT_MINUTES} mins without stream start or web activity).", flush=True)
                print("[Railway Lifecycle] Shutting down container to prevent idle cloud billing...", flush=True)
                await trigger_post_stream_shutdown(delay_seconds=5)
                break
        except Exception as e:
            print(f"[Railway Lifecycle Watchdog Notice] {e}", flush=True)
