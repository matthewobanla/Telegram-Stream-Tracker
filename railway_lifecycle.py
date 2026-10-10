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
AUTO_SHUTDOWN_ENABLED = os.getenv("RAILWAY_AUTO_SHUTDOWN", "True").lower() in ("true", "1", "yes")
IDLE_TIMEOUT_MINUTES = int(os.getenv("IDLE_SHUTDOWN_MINUTES", "15"))

# Railway Auto-injected or User-provided Variables
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN", "").strip()
RAILWAY_DEPLOYMENT_ID = os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip()
RAILWAY_SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "").strip()
RAILWAY_ENVIRONMENT_ID = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
RAILWAY_PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID", "").strip()

# Internal State
_stream_ever_detected = False
_boot_timestamp = datetime.datetime.now(datetime.timezone.utc)
_shutdown_in_progress = False

def is_railway_environment() -> bool:
    """Detects if running inside a Railway container."""
    return bool(RAILWAY_DEPLOYMENT_ID or RAILWAY_SERVICE_ID or os.getenv("RAILWAY_STATIC_URL"))

def mark_stream_active():
    """Signals the idle guard that a real stream was active, preventing early idle shutdown."""
    global _stream_ever_detected
    _stream_ever_detected = True

def remove_railway_deployment(deployment_id: str, api_token: str) -> bool:
    """
    Calls Railway GraphQL API to cancel/remove the active deployment.
    This stops the container execution and halts billing.
    """
    query = """
    mutation DeploymentRemove($id: String!) {
        deploymentRemove(id: $id)
    }
    """
    payload = {
        "query": query,
        "variables": {"id": deployment_id}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RAILWAY_GRAPHQL_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if "errors" in res:
                print(f"[Railway Lifecycle Error] GraphQL response error: {res['errors']}")
                return False
            return True
    except Exception as e:
        print(f"[Railway Lifecycle Error] Could not invoke deploymentRemove: {e}")
        return False

async def trigger_post_stream_shutdown(delay_seconds: int = 25):
    """
    Executed after stream ends and reports are dispatched.
    Waits for network transfers to complete, then shuts down Railway container.
    """
    global _shutdown_in_progress
    if _shutdown_in_progress or not AUTO_SHUTDOWN_ENABLED:
        return
    _shutdown_in_progress = True

    print(f"\n[Railway Lifecycle] 🛑 Stream completed & reports delivered.")
    print(f"[Railway Lifecycle] Scheduling container shutdown in {delay_seconds}s to conserve compute billing...")
    
    await asyncio.sleep(delay_seconds)

    if RAILWAY_API_TOKEN and RAILWAY_DEPLOYMENT_ID:
        print(f"[Railway Lifecycle] Calling Railway API to remove deployment {RAILWAY_DEPLOYMENT_ID}...")
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, remove_railway_deployment, RAILWAY_DEPLOYMENT_ID, RAILWAY_API_TOKEN)
        if success:
            print("[Railway Lifecycle] ✅ Deployment cancellation requested. Container will terminate immediately.")
        else:
            print("[Railway Lifecycle] ⚠️ API request failed. Exiting process with code 0...")
    else:
        print("[Railway Lifecycle] (RAILWAY_API_TOKEN not set). Exiting process cleanly with sys.exit(0)...")

    # Clean exit
    sys.exit(0)

async def idle_watchdog_loop(tracker_manager_ref):
    """
    Monitors container uptime. If no live stream begins within IDLE_TIMEOUT_MINUTES of boot,
    powers off the container to prevent accidental idle billing.
    """
    if not AUTO_SHUTDOWN_ENABLED:
        return

    print(f"[Railway Lifecycle] 🛡 Idle Watchdog active (Will power off in {IDLE_TIMEOUT_MINUTES}m if no stream starts).")

    while True:
        await asyncio.sleep(60)

        # Check if any stream is currently active
        has_active_tracker = len(tracker_manager_ref.get_all_active()) > 0
        if has_active_tracker:
            mark_stream_active()
            continue

        # If a stream occurred earlier, post-stream shutdown handles termination
        if _stream_ever_detected:
            continue

        # Check uptime
        uptime = (datetime.datetime.now(datetime.timezone.utc) - _boot_timestamp).total_seconds()
        if uptime >= IDLE_TIMEOUT_MINUTES * 60:
            print(f"\n[Railway Lifecycle] ⏰ Idle timeout reached ({IDLE_TIMEOUT_MINUTES} mins without stream start).")
            print("[Railway Lifecycle] Shutting down container to prevent idle cloud billing...")
            await trigger_post_stream_shutdown(delay_seconds=5)
            break
