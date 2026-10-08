"""
Authentication & Authorization Engine for Telegram Stream Tracker
Supports:
1. Cryptographic Telegram WebApp initData validation (HMAC-SHA256 with BOT_TOKEN)
2. Telegram User ID & Username whitelist verification
3. One-Time Passcode (OTP) direct to Telegram DM for browser logins
4. Admin Passkey / Master Key support
5. Secure session token management
"""

import os
import hmac
import hashlib
import json
import time
import secrets
import datetime
from urllib.parse import parse_qsl

import db
import config

# In-memory storage for active sessions and pending OTPs
# session_token -> { user_id, username, name, auth_type, created_at, expires_at }
ACTIVE_SESSIONS = {}

# telegram_id_str -> { code, expires_at, attempts }
PENDING_OTPS = {}

SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 days
OTP_TTL_SECONDS = 10 * 60            # 10 minutes

# Reference to Telethon bot client for sending OTP messages
_bot_client_ref = None

def set_bot_client(client):
    global _bot_client_ref
    _bot_client_ref = client

def get_bot_client():
    return _bot_client_ref

def get_bot_token():
    return os.getenv("BOT_TOKEN", getattr(config, "BOT_TOKEN", "")).strip()

def get_admin_passkey():
    return os.getenv("DASHBOARD_AUTH_KEY", os.getenv("ADMIN_PASSWORD", "")).strip()

def get_authorized_identities():
    """
    Collects all authorized Telegram User IDs and Usernames from:
    1. ALLOWED_TELEGRAM_IDS or ADMIN_USER_IDS env vars
    2. ADMIN_CHAT_ID in env / config
    3. admin_recipients in SQLite database (excluding legacy DM auto-enrollments)
    4. Hardcoded owner fallback (Matthew Ọbańlá: 1067204907, KingmattMO)
    """
    authorized_ids = set()
    authorized_usernames = set()

    # Always include Matthew Ọbańlá as owner
    authorized_ids.add("1067204907")
    authorized_usernames.add("kingmattmo")

    # Env: ALLOWED_TELEGRAM_IDS / ADMIN_USER_IDS
    env_ids = os.getenv("ALLOWED_TELEGRAM_IDS", os.getenv("ADMIN_USER_IDS", ""))
    if env_ids:
        for item in env_ids.split(","):
            cleaned = item.strip()
            if cleaned.isdigit():
                authorized_ids.add(cleaned)
            elif cleaned:
                authorized_usernames.add(cleaned.lower().lstrip("@"))

    # Env / Config: ADMIN_CHAT_ID
    admin_chat = os.getenv("ADMIN_CHAT_ID", getattr(config, "ADMIN_CHAT_ID", ""))
    if admin_chat:
        for item in str(admin_chat).split(","):
            cleaned = item.strip()
            if cleaned.isdigit():
                authorized_ids.add(cleaned)
            elif cleaned:
                authorized_usernames.add(cleaned.lower().lstrip("@"))

    # Database: admin_recipients table
    try:
        db_admins = db.get_admin_recipients()
        for a in db_admins:
            target = str(a.get("target", "")).strip()
            added_by = str(a.get("added_by", ""))
            # Exclude old random DM auto-enrolls if any
            if added_by == "DM Interaction":
                continue
            if target.isdigit():
                authorized_ids.add(target)
            elif target:
                authorized_usernames.add(target.lower().lstrip("@"))
    except Exception:
        pass

    return authorized_ids, authorized_usernames

def is_user_authorized(user_id=None, username=None):
    """Checks if given user_id or username is an authorized administrator."""
    auth_ids, auth_usernames = get_authorized_identities()

    if user_id is not None and str(user_id).strip() in auth_ids:
        return True

    if username:
        clean_user = str(username).strip().lower().lstrip("@")
        if clean_user in auth_usernames:
            return True

    return False

# --- Telegram WebApp initData Cryptographic Validation ---

def validate_telegram_init_data(init_data_raw, bot_token=None):
    """
    Validates cryptographic signature sent by Telegram WebApp SDK (HMAC-SHA256).
    Returns (user_dict, error_message).
    """
    if not init_data_raw:
        return None, "Missing initData payload"

    token = (bot_token or get_bot_token()).strip()
    if not token:
        # If no bot token configured, reject for security
        return None, "Bot token not configured on server"

    try:
        parsed = dict(parse_qsl(init_data_raw, keep_blank_values=True))
        if "hash" not in parsed:
            return None, "Missing hash in initData"

        received_hash = parsed.pop("hash")

        # Sort remaining key-value pairs alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # secret_key = HMAC_SHA256("WebAppData", bot_token)
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()

        # calculated_hash = HMAC_SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None, "Invalid cryptographic signature"

        # Check auth_date expiration (allow 48 hours tolerance)
        auth_date = int(parsed.get("auth_date", 0))
        now = int(time.time())
        if auth_date and (now - auth_date > 48 * 3600):
            return None, "Telegram auth session has expired. Please reload the app."

        user_raw = parsed.get("user")
        if not user_raw:
            return None, "Missing user profile in initData"

        user_data = json.loads(user_raw)
        return user_data, None

    except Exception as e:
        return None, f"InitData validation error: {e}"

# --- Direct Telegram Login Widget Validation ---

def validate_telegram_login_widget(auth_data, bot_token=None):
    """
    Validates data received directly from the official Telegram Login Widget (data-telegram-login).
    auth_data dict contains: id, first_name, username, auth_date, hash, etc.
    Algorithm per https://core.telegram.org/widgets/login#checking-authorization:
      secret_key = SHA256(bot_token)
      data_check_string = sorted key=value pairs (excluding hash) joined by \n
      hash = HMAC-SHA256(data_check_string, secret_key)
    """
    if not auth_data or not isinstance(auth_data, dict):
        return None, "Missing authentication payload"

    received_hash = auth_data.get("hash")
    if not received_hash:
        return None, "Missing cryptographic hash in Telegram payload"

    token = (bot_token or get_bot_token()).strip()
    if not token:
        return None, "Bot token not configured on server"

    try:
        check_dict = {str(k): str(v) for k, v in auth_data.items() if k != "hash" and v is not None}
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_dict.items()))

        secret_key = hashlib.sha256(token.encode("utf-8")).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None, "Invalid cryptographic Telegram signature"

        auth_date = int(auth_data.get("auth_date", 0))
        now = int(time.time())
        if auth_date and (now - auth_date > 86400):
            return None, "Telegram login session has expired. Please log in again."

        return check_dict, None
    except Exception as e:
        return None, f"Telegram login verification error: {e}"

# --- Session Token Management ---

def create_session(user_id, username="", name="", auth_type="webapp"):
    """Generates a secure random session token and stores it."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    ACTIVE_SESSIONS[token] = {
        "user_id": str(user_id),
        "username": str(username or "").lstrip("@"),
        "name": str(name or f"User {user_id}"),
        "auth_type": auth_type,
        "created_at": now,
        "expires_at": now + SESSION_TTL_SECONDS
    }
    return token

def verify_session(token):
    """Returns session info if token is valid and unexpired, else None."""
    if not token or not isinstance(token, str):
        return None

    session = ACTIVE_SESSIONS.get(token)
    if not session:
        return None

    if time.time() > session.get("expires_at", 0):
        ACTIVE_SESSIONS.pop(token, None)
        return None

    return session

def destroy_session(token):
    """Revokes an active session token."""
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]

# --- Telegram OTP Generation & Verification ---

def generate_otp_for_user(target_identity):
    """
    target_identity: numeric Telegram ID or @username
    Returns 6-digit string code.
    """
    clean_target = str(target_identity).strip().lower().lstrip("@")
    code = f"{secrets.randbelow(900000) + 100000}"
    PENDING_OTPS[clean_target] = {
        "code": code,
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "attempts": 0
    }
    return code

def verify_user_otp(target_identity, submitted_code):
    """Verifies submitted OTP code. Returns boolean."""
    clean_target = str(target_identity).strip().lower().lstrip("@")
    record = PENDING_OTPS.get(clean_target)
    if not record:
        return False, "No pending code found. Please request a new code."

    if time.time() > record["expires_at"]:
        PENDING_OTPS.pop(clean_target, None)
        return False, "Verification code has expired. Please request a new code."

    record["attempts"] += 1
    if record["attempts"] > 5:
        PENDING_OTPS.pop(clean_target, None)
        return False, "Too many failed attempts. Please request a new code."

    if str(submitted_code).strip() == record["code"]:
        PENDING_OTPS.pop(clean_target, None)
        return True, "Code verified successfully"

    return False, "Incorrect verification code. Please try again."

async def send_otp_via_telegram(target_identity, code):
    """
    Sends the 6-digit code to the user's Telegram DM via the bot.
    """
    client = get_bot_client()
    if not client:
        return False, "Telegram Bot client is not currently connected."

    try:
        # Resolve target peer
        peer = int(target_identity) if str(target_identity).isdigit() else target_identity
        msg = (
            "🔐 **STREAM TRACKER CONTROL ROOM // AUTHENTICATION**\n\n"
            f"Your one-time login code is:\n"
            f"👉 `{code}` 👈\n\n"
            f"⏱ Valid for **10 minutes**.\n"
            f"If you did not request this code, you can safely ignore this message."
        )
        await client.send_message(peer, msg, parse_mode="markdown")
        return True, "Code sent to your Telegram chat"
    except Exception as e:
        return False, f"Could not message user on Telegram: {e}"
