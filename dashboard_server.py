import os
import sys
import json
import asyncio
import datetime
from pathlib import Path
from aiohttp import web

import db
import transcriber

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

# --- Helper Utilities ---

def json_response(data, status=200):
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, default=str))

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

# --- API Route Handlers ---

async def handle_index(request):
    """Serves the main Mini App single page HTML."""
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="<h1>Telegram Stream Tracker Dashboard</h1><p>Frontend template initializing...</p>", content_type="text/html")
    return web.FileResponse(index_path)

async def api_status(request):
    """System health, stats, and active config."""
    try:
        all_streams = db.get_all_streams()
        tracked_groups = db.get_tracked_groups()
        admins = db.get_admin_recipients()
        active_streams = [s for s in all_streams if s.get("is_active") == 1]
    except Exception as e:
        return json_response({"status": "error", "message": str(e)}, status=500)

    return json_response({
        "status": "online",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_streams": len(all_streams),
        "active_streams_count": len(active_streams),
        "active_streams": active_streams,
        "tracked_groups_count": len(tracked_groups),
        "admins_count": len(admins),
        "transcription_engine": transcriber.get_active_engine(),
        "features": {
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        }
    })

async def api_streams(request):
    """Returns a list of all streams with metadata and asset availability."""
    chat_id = request.query.get("chat_id")
    limit = request.query.get("limit")
    limit = int(limit) if limit and limit.isdigit() else 100

    try:
        raw_streams = db.get_all_streams(chat_id=chat_id)
        # Reverse to show newest first
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
            # Check by index if stream_id is numeric
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

    # aiohttp FileResponse natively handles HTTP Range / seeking
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
            return web.Response(text="CSV report could not be generated", status=404)

        filename = os.path.basename(csv_path)
        return web.FileResponse(
            csv_path,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return json_response({"error": str(e)}, status=500)

# --- Settings & Management Endpoints ---

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
        added_by = data.get("added_by", "Mini App Dashboard")

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
        added_by = data.get("added_by", "Mini App Dashboard")

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

    # CORS Middleware / Header injection for Mini App flexibility
    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
        return middleware

    app.middlewares.append(cors_middleware)

    # Static Routes
    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    # Frontend Single Page
    app.router.add_get("/", handle_index)

    # API Routes
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/streams", api_streams)
    app.router.add_get("/api/streams/{stream_id}", api_stream_detail)
    app.router.add_get("/api/streams/{stream_id}/audio", api_stream_audio)
    app.router.add_get("/api/streams/{stream_id}/transcript", api_stream_transcript)
    app.router.add_get("/api/streams/{stream_id}/summary", api_stream_summary)
    app.router.add_get("/api/streams/{stream_id}/csv", api_stream_csv)

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
    print(f"[Mini App Dashboard] 🚀 Web server running at http://{host}:{port}")
    return runner

if __name__ == "__main__":
    app = create_app()
    print(f"[Mini App Dashboard] Starting standalone server on http://{HOST}:{PORT}...")
    web.run_app(app, host=HOST, port=PORT)
