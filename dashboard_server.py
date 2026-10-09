import os
import sys
import json
import asyncio
import datetime
import hmac
from pathlib import Path
from aiohttp import web

import db
import transcriber
import auth

# Configuration
PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8080")))
HOST = os.getenv("HOST", "0.0.0.0")

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
RECORDINGS_DIR = Path(transcriber.RECORDINGS_DIR)
TRANSCRIPTS_DIR = Path(transcriber.TRANSCRIPTS_DIR)
REPORTS_DIR = Path(db.REPORTS_DIR)

# Initialize database
try:
    db.init_db()
except Exception as e:
    print(f"[Dashboard Server Warning] DB init: {e}")

def set_bot_client(client):
    """Sets Telethon bot client instance for sending OTP messages."""
    auth.set_bot_client(client)

# --- Helper Utilities ---

def json_response(data, status=200):
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, default=str))

async def get_request_session(request):
    """Extracts and verifies session from Authorization header, query token, cookies, device token, or Telegram initData."""
    # 1. Bearer Token (Authorization: Bearer <token>)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        sess = auth.verify_session(token)
        if sess:
            return sess

    # 2. Query parameter token (?token=<token>)
    query_token = request.query.get("token", "").strip()
    if query_token:
        sess = auth.verify_session(query_token)
        if sess:
            return sess

    # 3. Cookie (tracker_session)
    cookie_token = request.cookies.get("tracker_session")
    if cookie_token:
        sess = auth.verify_session(cookie_token)
        if sess:
            return sess

    # 4. Device Token (Header X-Device-Token or Query device_token)
    device_token = request.headers.get("X-Device-Token", "").strip() or request.query.get("device_token", "").strip()
    if device_token:
        dev_data = auth.verify_device_token(device_token)
        if dev_data:
            uid = dev_data.get("user_id")
            uname = dev_data.get("username", "")
            if auth.is_user_authorized(uid, uname):
                token = auth.create_session(uid, uname, dev_data.get("name", ""), auth_type="device_token")
                return auth.verify_session(token)

    # 5. Direct Telegram initData header or query (for seamless WebApp requests)
    init_data = request.headers.get("X-Telegram-Init-Data", "").strip() or request.query.get("initData", "").strip()
    if init_data:
        user_data, _ = auth.validate_telegram_init_data(init_data)
        if user_data:
            uid = user_data.get("id")
            uname = user_data.get("username")
            if auth.is_user_authorized(uid, uname):
                token = auth.create_session(uid, uname, user_data.get("first_name", ""), auth_type="webapp_header")
                return auth.verify_session(token)

    return None

def find_audio_file_for_stream(stream_id, stream_meta=None):
    """Searches for an audio recording file corresponding to stream_id."""
    if not RECORDINGS_DIR.exists():
        return None
    
    # 1. Exact or partial match on stream_id
    for f in RECORDINGS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in [".mp3", ".wav", ".ogg", ".m4a", ".aac"]:
            if stream_id in f.name:
                return f

    # 2. Match on date or call_id if meta provided
    if stream_meta:
        call_id = str(stream_meta.get("call_id") or "").strip()
        if call_id and len(call_id) > 4:
            for f in RECORDINGS_DIR.iterdir():
                if f.is_file() and call_id in f.name:
                    return f
                    
        # Check start_time timestamp matching
        start_time = str(stream_meta.get("start_time") or "")[:10].replace("-", "")
        if start_time:
            for f in RECORDINGS_DIR.iterdir():
                if f.is_file() and start_time in f.name:
                    return f
    return None

def find_transcript_files_for_stream(stream_id):
    """Locates transcript and summary files for a given stream."""
    transcript_file = TRANSCRIPTS_DIR / f"transcript_{stream_id}.txt"
    summary_file = TRANSCRIPTS_DIR / f"summary_{stream_id}.md"

    # Also search for partial matches if stream_id varies slightly
    if not transcript_file.exists() and TRANSCRIPTS_DIR.exists():
        for f in TRANSCRIPTS_DIR.iterdir():
            if f.is_file() and f.name.startswith("transcript_") and stream_id in f.name:
                transcript_file = f
                break

    if not summary_file.exists() and TRANSCRIPTS_DIR.exists():
        for f in TRANSCRIPTS_DIR.iterdir():
            if f.is_file() and f.name.startswith("summary_") and stream_id in f.name:
                summary_file = f
                break

    return (
        transcript_file if transcript_file.exists() else None,
        summary_file if summary_file.exists() else None
    )

# --- Basic / Public Routes ---

async def handle_index(request):
    """Serves the main Mini App single page HTML."""
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="<h1>Telegram Stream Tracker Dashboard</h1><p>Frontend template initializing...</p>", content_type="text/html")
    return web.FileResponse(index_path)

async def api_health(request):
    """Basic health check ping for Railway / orchestrators."""
    return json_response({
        "status": "ok",
        "service": "telegram-stream-tracker",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

# --- Authentication Endpoints ---

async def api_auth_webapp(request):
    """Authenticates Telegram WebApp initData cryptographically."""
    try:
        data = await request.json()
        init_data = data.get("initData", "").strip()
        if not init_data:
            return json_response({"error": "initData is required"}, status=400)

        user_data, err = auth.validate_telegram_init_data(init_data)
        if not user_data:
            return json_response({"error": f"Invalid Telegram cryptographic signature: {err}"}, status=401)

        user_id = user_data.get("id")
        username = user_data.get("username", "")
        name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or f"User {user_id}"

        if not auth.is_user_authorized(user_id, username):
            return json_response({
                "error": "ACCESS_DENIED",
                "message": f"Telegram ID {user_id} (@{username or 'no_username'}) is not an authorized administrator.",
                "telegram_id": user_id,
                "username": username
            }, status=403)

        token = auth.create_session(user_id, username=username, name=name, auth_type="webapp")
        resp = json_response({
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "name": name,
                "auth_type": "webapp"
            }
        })
        resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_widget(request):
    """Authenticates direct Telegram Login Widget payload."""
    try:
        data = await request.json()
        auth_data = data.get("auth_data", {})
        if not auth_data:
            return json_response({"error": "Missing Telegram auth_data"}, status=400)

        verified, err = auth.validate_telegram_login_widget(auth_data)
        if not verified:
            return json_response({"error": f"Invalid Telegram authentication: {err}"}, status=401)

        user_id = verified.get("id")
        username = verified.get("username", "")
        first_name = verified.get("first_name", "")
        last_name = verified.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip() or f"User {user_id}"

        if not auth.is_user_authorized(user_id, username):
            return json_response({
                "error": "ACCESS_DENIED",
                "message": f"Telegram user @{username or 'no_user'} (ID: {user_id}) is not an authorized administrator.",
                "telegram_id": user_id,
                "username": username
            }, status=403)

        token = auth.create_session(user_id, username=username, name=full_name, auth_type="telegram_widget")
        resp = json_response({
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "name": full_name,
                "photo_url": verified.get("photo_url", ""),
                "auth_type": "telegram_widget"
            }
        })
        resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_config(request):
    """Returns public auth metadata (such as bot username for the Telegram Widget)."""
    bot_name = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    return json_response({
        "bot_username": bot_name,
        "has_passkey": bool(auth.get_admin_passkey())
    })

async def api_auth_inspect(request):
    """Inspects pending identity from launch token, WebApp initData, device token, or session."""
    # 1. Check launch token in query (?auth=...)
    launch_token = request.query.get("auth", "").strip()
    if launch_token:
        record = auth.verify_launch_token(launch_token)
        if record:
            user_id = record["user_id"]
            username = record.get("username", "")
            is_auth = auth.is_user_authorized(user_id, username)
            return json_response({
                "detected": True,
                "authorized": is_auth,
                "user": {
                    "id": user_id,
                    "username": username,
                    "name": record.get("name", f"User {user_id}"),
                },
                "launch_token": launch_token,
                "method": "bot_launch",
                "can_unlock": is_auth,
                "state": "pending_authorization"
            })

    # 2. Check X-Telegram-Init-Data header
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        user_data, _ = auth.validate_telegram_init_data(init_data)
        if user_data:
            user_id = user_data.get("id")
            username = user_data.get("username", "")
            name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or f"User {user_id}"
            is_auth = auth.is_user_authorized(user_id, username)
            return json_response({
                "detected": True,
                "authorized": is_auth,
                "user": {
                    "id": user_id,
                    "username": username,
                    "name": name,
                },
                "method": "telegram_webapp",
                "can_unlock": is_auth,
                "state": "pending_authorization"
            })

    # 3. Check X-Device-Token header (persistent device authorization)
    device_token = request.headers.get("X-Device-Token", "").strip()
    if device_token:
        dev_data = auth.verify_device_token(device_token)
        if dev_data:
            user_id = dev_data.get("user_id")
            username = dev_data.get("username", "")
            name = dev_data.get("name", f"User {user_id}")
            is_auth = auth.is_user_authorized(user_id, username)
            return json_response({
                "detected": True,
                "authorized": is_auth,
                "user": {
                    "id": user_id,
                    "username": username,
                    "name": name,
                },
                "method": "device_token",
                "can_unlock": is_auth,
                "state": "pending_authorization"
            })

    # 4. Check existing active session
    sess = await get_request_session(request)
    if sess:
        user_id = sess.get("user_id")
        username = sess.get("username")
        is_auth = auth.is_user_authorized(user_id, username)
        return json_response({
            "detected": True,
            "authorized": is_auth,
            "user": {
                "id": user_id,
                "username": username,
                "name": sess.get("name"),
            },
            "method": "session",
            "can_unlock": is_auth,
            "state": "pending_authorization"
        })

    return json_response({"detected": False, "state": "anonymous", "can_unlock": False})

async def api_auth_authorize(request):
    """Confirms user tap on [AUTHORIZE & ENTER CONTROL ROOM] or [UNLOCK CONTROL ROOM]. Creates session & cookie."""
    try:
        data = await request.json()
        launch_token = data.get("launch_token", "").strip()
        init_data = data.get("initData", "").strip()
        device_token = (data.get("device_token") or request.headers.get("X-Device-Token", "")).strip()

        # A: Authorize via bot launch token
        if launch_token:
            record = auth.verify_launch_token(launch_token)
            if not record:
                return json_response({"error": "Launch token has expired. Please launch from Telegram bot again."}, status=401)

            user_id = record["user_id"]
            username = record.get("username", "")
            name = record.get("name", "")

            if not auth.is_user_authorized(user_id, username):
                return json_response({"error": "ACCESS_DENIED", "message": f"User {user_id} (@{username}) is not authorized."}, status=403)

            token = auth.consume_launch_token(launch_token)
            fresh_device_token = auth.generate_device_token(user_id, username, name)
            resp = json_response({
                "success": True,
                "token": token,
                "device_token": fresh_device_token,
                "user": { "id": user_id, "username": username, "name": name, "auth_type": "bot_launch" }
            })
            resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
            return resp

        # B: Authorize via WebApp initData
        if init_data:
            user_data, err = auth.validate_telegram_init_data(init_data)
            if not user_data:
                return json_response({"error": f"Invalid Telegram initData: {err}"}, status=401)

            user_id = user_data.get("id")
            username = user_data.get("username", "")
            name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or f"User {user_id}"

            if not auth.is_user_authorized(user_id, username):
                return json_response({"error": "ACCESS_DENIED", "message": f"User {user_id} (@{username}) is not authorized."}, status=403)

            token = auth.create_session(user_id, username=username, name=name, auth_type="webapp")
            fresh_device_token = auth.generate_device_token(user_id, username, name)
            resp = json_response({
                "success": True,
                "token": token,
                "device_token": fresh_device_token,
                "user": { "id": user_id, "username": username, "name": name, "auth_type": "webapp" }
            })
            resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
            return resp

        # C: Authorize via persistent Device Token
        if device_token:
            dev_data = auth.verify_device_token(device_token)
            if not dev_data:
                return json_response({"error": "Device token has expired. Please launch from Telegram bot again."}, status=401)

            user_id = dev_data["user_id"]
            username = dev_data.get("username", "")
            name = dev_data.get("name", "")

            if not auth.is_user_authorized(user_id, username):
                return json_response({"error": "ACCESS_DENIED", "message": f"User {user_id} (@{username}) is not authorized."}, status=403)

            token = auth.create_session(user_id, username=username, name=name, auth_type="device_reauth")
            fresh_device_token = auth.generate_device_token(user_id, username, name)
            resp = json_response({
                "success": True,
                "token": token,
                "device_token": fresh_device_token,
                "user": { "id": user_id, "username": username, "name": name, "auth_type": "device_reauth" }
            })
            resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
            return resp

        # D: Authorize via active session (unlock locked screen)
        sess = await get_request_session(request)
        if sess:
            user_id = sess["user_id"]
            username = sess.get("username", "")
            name = sess.get("name", "")
            fresh_device_token = auth.generate_device_token(user_id, username, name)
            return json_response({
                "success": True,
                "token": request.headers.get("Authorization", "").replace("Bearer ", "").strip() or request.cookies.get("tracker_session", ""),
                "device_token": fresh_device_token,
                "user": { "id": user_id, "username": username, "name": name, "auth_type": "session_unlock" }
            })

        return json_response({"error": "Missing authorization credentials (launch token, initData, or device token)"}, status=400)
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_request_otp(request):
    """Sends a 6-digit OTP code directly to user's Telegram DM via the bot."""
    try:
        data = await request.json()
        target = data.get("target", "").strip()
        if not target:
            return json_response({"error": "Telegram ID or @Username is required"}, status=400)

        is_id = target.isdigit() or (target.startswith("-") and target[1:].isdigit())
        user_id = target if is_id else None
        username = None if is_id else target.lstrip("@")

        if not auth.is_user_authorized(user_id=user_id, username=username):
            return json_response({
                "error": "UNAUTHORIZED_IDENTITY",
                "message": f"'{target}' is not registered as an authorized administrator. Please contact the bot owner."
            }, status=403)

        code = auth.generate_otp_for_user(target)
        sent, msg = await auth.send_otp_via_telegram(target, code)
        if not sent:
            return json_response({"error": msg}, status=500)

        return json_response({
            "success": True,
            "message": f"Verification code dispatched to Telegram chat '{target}'.",
            "target": target
        })
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_verify_otp(request):
    """Validates user-submitted OTP code and creates session."""
    try:
        data = await request.json()
        target = data.get("target", "").strip()
        code = data.get("code", "").strip()

        if not target or not code:
            return json_response({"error": "Identity and 6-digit verification code are required"}, status=400)

        ok, msg = auth.verify_user_otp(target, code)
        if not ok:
            return json_response({"error": msg}, status=401)

        token = auth.create_session(user_id=target, username=target, name=f"Admin {target}", auth_type="otp")
        dev_token = auth.generate_device_token(target, username=target, name=f"Admin {target}")
        resp = json_response({
            "success": True,
            "token": token,
            "device_token": dev_token,
            "user": {
                "id": target,
                "name": f"Operator {target}",
                "auth_type": "otp"
            }
        })
        resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_login_passkey(request):
    """Validates master passkey / secret token."""
    try:
        data = await request.json()
        passkey = data.get("passkey", "").strip()
        master_key = auth.get_admin_passkey()

        if not master_key:
            return json_response({"error": "Master passkey is not configured in environment (DASHBOARD_AUTH_KEY)"}, status=400)

        if not hmac.compare_digest(passkey, master_key):
            return json_response({"error": "Invalid master passkey"}, status=401)

        token = auth.create_session(user_id="master_admin", username="owner", name="Master Operator", auth_type="passkey")
        dev_token = auth.generate_device_token("master_admin", username="owner", name="Master Operator")
        resp = json_response({
            "success": True,
            "token": token,
            "device_token": dev_token,
            "user": {
                "id": "master_admin",
                "name": "Master Operator",
                "auth_type": "passkey"
            }
        })
        resp.set_cookie("tracker_session", token, max_age=auth.SESSION_TTL_SECONDS, path="/", httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_auth_me(request):
    """Checks current active operator profile."""
    sess = await get_request_session(request)
    if not sess:
        return json_response({"authenticated": False}, status=401)

    return json_response({
        "authenticated": True,
        "user": {
            "id": sess.get("user_id"),
            "username": sess.get("username"),
            "name": sess.get("name"),
            "auth_type": sess.get("auth_type")
        }
    })

async def api_auth_logout(request):
    """Logs out and revokes session."""
    token = request.cookies.get("tracker_session")
    if token:
        auth.destroy_session(token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        auth.destroy_session(auth_header[7:].strip())

    resp = json_response({"success": True, "message": "Logged out successfully"})
    resp.del_cookie("tracker_session", path="/")
    return resp

# --- Protected API Handlers ---

async def api_status(request):
    """System health, stats, and active config."""
    try:
        all_streams = db.get_all_streams()
        tracked_groups = db.get_tracked_groups()
        admins = db.get_admin_recipients()
        active_streams = [s for s in all_streams if s.get("is_active") == 1]
    except Exception as e:
        return json_response({"status": "error", "message": str(e)}, status=500)

    sess = await get_request_session(request)
    is_authed = bool(sess)

    # Return full stats if authenticated
    return json_response({
        "status": "online",
        "authenticated": is_authed,
        "operator": sess.get("name") if sess else None,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_streams": len(all_streams) if is_authed else None,
        "active_streams_count": len(active_streams) if is_authed else None,
        "active_streams": active_streams if is_authed else [],
        "tracked_groups_count": len(tracked_groups) if is_authed else None,
        "admins_count": len(admins) if is_authed else None,
        "transcription_engine": transcriber.get_active_engine(),
        "features": {
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "auth_required": True,
            "has_passkey": bool(auth.get_admin_passkey())
        }
    })

async def api_streams(request):
    """Returns a list of all streams with metadata and asset availability."""
    chat_id = request.query.get("chat_id")
    limit = request.query.get("limit")
    limit = int(limit) if limit and limit.isdigit() else 100

    try:
        raw_streams = db.get_all_streams(chat_id=chat_id)
        sorted_streams = list(reversed(raw_streams))[:limit]
        
        result = []
        for s in sorted_streams:
            sid = s.get("stream_id")
            audio_f = find_audio_file_for_stream(sid, s)
            trans_f, sum_f = find_transcript_files_for_stream(sid)
            csv_path = s.get("csv_path")
            has_csv = bool(csv_path and os.path.exists(csv_path))

            s_copy = dict(s)
            s_copy["has_audio"] = bool(audio_f)
            s_copy["has_transcript"] = bool(trans_f)
            s_copy["has_summary"] = bool(sum_f)
            s_copy["has_csv"] = has_csv
            result.append(s_copy)

        return json_response({"streams": result, "count": len(result)})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_stream_detail(request):
    """Detailed stream info and participants leaderboard."""
    stream_id = request.match_info.get("stream_id")
    try:
        stream_meta, participants = db.get_stream_by_id(stream_id)
        if not stream_meta:
            if stream_id.isdigit():
                stream_meta = db.get_stream_by_index(int(stream_id))
                if stream_meta:
                    _, participants = db.get_stream_by_id(stream_meta["stream_id"])

        if not stream_meta:
            return json_response({"error": "Stream not found"}, status=404)

        sid = stream_meta["stream_id"]
        audio_f = find_audio_file_for_stream(sid, stream_meta)
        trans_f, sum_f = find_transcript_files_for_stream(sid)

        res = {
            "stream": stream_meta,
            "participants": participants,
            "participants_count": len(participants),
            "assets": {
                "has_audio": bool(audio_f),
                "audio_filename": audio_f.name if audio_f else None,
                "has_transcript": bool(trans_f),
                "has_summary": bool(sum_f),
                "has_csv": bool(stream_meta.get("csv_path") and os.path.exists(stream_meta.get("csv_path", "")))
            }
        }
        return json_response(res)
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_stream_audio(request):
    """Streams audio file with HTTP range support."""
    stream_id = request.match_info.get("stream_id")
    stream_meta, _ = db.get_stream_by_id(stream_id)
    audio_file = find_audio_file_for_stream(stream_id, stream_meta)

    if not audio_file or not audio_file.exists():
        return web.Response(text="Audio recording not found for this stream", status=404)

    return web.FileResponse(
        audio_file,
        headers={
            "Content-Disposition": f'inline; filename="{audio_file.name}"',
            "Accept-Ranges": "bytes"
        }
    )

async def api_stream_transcript(request):
    """Returns transcript content or downloads as text file."""
    stream_id = request.match_info.get("stream_id")
    trans_f, _ = find_transcript_files_for_stream(stream_id)

    download = request.query.get("download", "0") == "1"

    if not trans_f or not trans_f.exists():
        return json_response({"error": "Transcript not generated for this stream"}, status=404)

    if download:
        return web.FileResponse(
            trans_f,
            headers={"Content-Disposition": f'attachment; filename="transcript_{stream_id}.txt"'}
        )

    try:
        with open(trans_f, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return json_response({"stream_id": stream_id, "transcript": content})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_stream_summary(request):
    """Returns AI executive summary content or downloads as markdown file."""
    stream_id = request.match_info.get("stream_id")
    _, sum_f = find_transcript_files_for_stream(stream_id)

    download = request.query.get("download", "0") == "1"

    if not sum_f or not sum_f.exists():
        return json_response({"error": "Summary not generated for this stream"}, status=404)

    if download:
        return web.FileResponse(
            sum_f,
            headers={"Content-Disposition": f'attachment; filename="summary_{stream_id}.md"'}
        )

    try:
        with open(sum_f, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return json_response({"stream_id": stream_id, "summary": content})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_stream_csv(request):
    """Downloads participation CSV spreadsheet."""
    stream_id = request.match_info.get("stream_id")
    try:
        csv_path, stream_meta = db.get_or_generate_csv_for_stream(stream_id)
        if not csv_path or not os.path.exists(csv_path):
            return json_response({"error": "CSV report could not be generated for this session"}, status=404)

        filename = os.path.basename(csv_path)

        with open(csv_path, "rb") as f:
            csv_bytes = f.read()

        return web.Response(
            body=csv_bytes,
            content_type="text/csv",
            charset="utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_stream_send_csv(request):
    """Sends the CSV spreadsheet directly to the user's Telegram DM via the bot."""
    stream_id = request.match_info.get("stream_id")
    sess = request.get("session") or await get_request_session(request)
    if not sess:
        return json_response({"error": "Unauthorized"}, status=401)

    user_id = sess.get("user_id")
    if not user_id:
        return json_response({"error": "Telegram User ID not identified"}, status=400)

    csv_path, stream_meta = db.get_or_generate_csv_for_stream(stream_id)
    if not csv_path or not os.path.exists(csv_path):
        return json_response({"error": "CSV file not found"}, status=404)

    bot_client = auth.get_bot_client()
    if not bot_client:
        return json_response({"error": "Bot client unavailable"}, status=503)

    try:
        target = int(user_id) if str(user_id).isdigit() else user_id
        title = stream_meta.get("chat_title", "Voice Stream") if stream_meta else "Voice Stream"
        caption = f"📊 **Attendance Report**: {title}\nSession: `{stream_id}`"
        await bot_client.send_file(target, file=csv_path, caption=caption)
        return json_response({"success": True, "message": f"CSV dispatched to Telegram DM ({user_id})"})
    except Exception as e:
        return json_response({"error": f"Failed to send to Telegram DM: {e}"}, status=500)

async def api_groups_get(request):
    """List tracked groups."""
    try:
        groups = db.get_distinct_stream_groups()
        return json_response({"groups": groups})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_groups_post(request):
    """Add a new tracked group."""
    try:
        data = await request.json()
        target = data.get("target", "").strip()
        title = data.get("title", "").strip()
        entity_id = data.get("entity_id", "").strip()
        added_by = data.get("added_by", "Control Room Operator")

        if not target:
            return json_response({"error": "Target username or ChatID is required"}, status=400)

        ok = db.add_tracked_group(target, title=title, entity_id=entity_id, added_by=added_by)
        if ok:
            return json_response({"success": True, "message": f"Tracked group '{target}' saved successfully"})
        return json_response({"error": "Could not save tracked group"}, status=500)
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_groups_delete(request):
    """Remove a tracked group."""
    target = request.match_info.get("target")
    try:
        ok = db.remove_tracked_group(target)
        return json_response({"success": ok, "target": target})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_admins_get(request):
    """List admin recipients."""
    try:
        admins = db.get_admin_recipients()
        return json_response({"admins": admins})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_admins_post(request):
    """Add an admin recipient."""
    try:
        data = await request.json()
        target = data.get("target", "").strip()
        name = data.get("name", "").strip()
        added_by = data.get("added_by", "Control Room Operator")

        if not target:
            return json_response({"error": "Target username or ID is required"}, status=400)

        ok = db.add_admin_recipient(target, name=name, added_by=added_by)
        if ok:
            return json_response({"success": True, "message": f"Admin recipient '{target}' added successfully"})
        return json_response({"error": "Could not add admin recipient"}, status=500)
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_admins_delete(request):
    """Remove an admin recipient."""
    target = request.match_info.get("target")
    try:
        ok = db.remove_admin_recipient(target)
        return json_response({"success": ok, "target": target})
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

async def api_settings_get(request):
    """Fetch current app settings."""
    return json_response({
        "transcription_engine": transcriber.get_active_engine(),
        "min_attendance_seconds": int(os.getenv("MIN_ATTENDANCE_SECONDS", "30")),
        "auto_post_report": os.getenv("AUTO_POST_REPORT", "True").lower() in ("true", "1", "yes"),
        "auto_post_to_group": os.getenv("AUTO_POST_TO_GROUP", "False").lower() in ("true", "1", "yes"),
        "enable_audio_recording": os.getenv("ENABLE_AUDIO_RECORDING", "True").lower() in ("true", "1", "yes"),
        "keys": {
            "has_gemini": bool(os.getenv("GEMINI_API_KEY")),
            "has_groq": bool(os.getenv("GROQ_API_KEY")),
            "has_openai": bool(os.getenv("OPENAI_API_KEY")),
        }
    })

async def api_settings_post(request):
    """Update active transcription engine or settings."""
    try:
        data = await request.json()
        if "transcription_engine" in data:
            eng = data["transcription_engine"]
            if transcriber.set_active_engine(eng):
                os.environ["TRANSCRIPTION_ENGINE"] = eng
            else:
                return json_response({"error": f"Invalid engine '{eng}'. Supported: gemini, groq, openai, faster_whisper"}, status=400)

        return json_response({
            "success": True,
            "message": "Settings updated",
            "active_engine": transcriber.get_active_engine()
        })
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

# --- Application Factory ---

def create_app():
    app = web.Application()

    # CORS Middleware
    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Telegram-Init-Data"
            return response
        return middleware

    # Authentication Protection Middleware for /api/* routes
    async def auth_middleware(app, handler):
        async def middleware(request):
            path = request.path
            # Allow public index, static assets, health check, and auth endpoints
            if not path.startswith("/api/") or path.startswith("/api/auth/") or path == "/api/health" or path == "/api/status":
                return await handler(request)

            # Check authentication
            sess = await get_request_session(request)
            if not sess:
                return json_response({
                    "error": "UNAUTHORIZED",
                    "message": "Authentication required. Please authenticate with your Telegram ID or passkey."
                }, status=401)

            request["session"] = sess
            return await handler(request)
        return middleware

    app.middlewares.append(cors_middleware)
    app.middlewares.append(auth_middleware)

    # Static Routes
    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    # Frontend Single Page
    app.router.add_get("/", handle_index)

    # Public / Health
    app.router.add_get("/api/health", api_health)
    app.router.add_get("/api/status", api_status)

    # Auth Endpoints
    app.router.add_get("/api/auth/config", api_auth_config)
    app.router.add_get("/api/auth/inspect", api_auth_inspect)
    app.router.add_post("/api/auth/authorize", api_auth_authorize)
    app.router.add_post("/api/auth/telegram-webapp", api_auth_webapp)
    app.router.add_post("/api/auth/telegram-widget", api_auth_widget)
    app.router.add_post("/api/auth/request-otp", api_auth_request_otp)
    app.router.add_post("/api/auth/verify-otp", api_auth_verify_otp)
    app.router.add_post("/api/auth/login-passkey", api_auth_login_passkey)
    app.router.add_get("/api/auth/me", api_auth_me)
    app.router.add_post("/api/auth/logout", api_auth_logout)

    # Protected API Routes
    app.router.add_get("/api/streams", api_streams)
    app.router.add_get("/api/streams/{stream_id}", api_stream_detail)
    app.router.add_get("/api/streams/{stream_id}/audio", api_stream_audio)
    app.router.add_get("/api/streams/{stream_id}/transcript", api_stream_transcript)
    app.router.add_get("/api/streams/{stream_id}/summary", api_stream_summary)
    app.router.add_get("/api/streams/{stream_id}/csv", api_stream_csv)
    app.router.add_post("/api/streams/{stream_id}/send-csv", api_stream_send_csv)
    app.router.add_get("/api/streams/{stream_id}/send-csv", api_stream_send_csv)

    app.router.add_get("/api/groups", api_groups_get)
    app.router.add_post("/api/groups", api_groups_post)
    app.router.add_delete("/api/groups/{target}", api_groups_delete)

    app.router.add_get("/api/admins", api_admins_get)
    app.router.add_post("/api/admins", api_admins_post)
    app.router.add_delete("/api/admins/{target}", api_admins_delete)

    app.router.add_get("/api/settings", api_settings_get)
    app.router.add_post("/api/settings", api_settings_post)

    return app

async def start_dashboard_server(host=HOST, port=PORT):
    """Asynchronous entry point for running directly inside tracker.py event loop."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[Mini App Dashboard] 🚀 Web server running with Telegram Auth at http://{host}:{port}")
    return runner

if __name__ == "__main__":
    app = create_app()
    print(f"[Mini App Dashboard] Starting server with Telegram Auth on http://{HOST}:{PORT}...")
    web.run_app(app, host=HOST, port=PORT)
