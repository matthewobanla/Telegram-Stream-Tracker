import os
import json
import asyncio
import datetime
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# Directories
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")
TRANSCRIPTS_DIR = os.getenv("TRANSCRIPTS_DIR", "transcripts")

os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

# API Keys & Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ACTIVE_ENGINE = os.getenv("TRANSCRIPTION_ENGINE", "gemini").lower()  # gemini, groq, openai, faster_whisper

def get_active_engine():
    return ACTIVE_ENGINE

def set_active_engine(engine_name):
    global ACTIVE_ENGINE
    engine_name = engine_name.lower().strip()
    if engine_name in ["gemini", "groq", "openai", "faster_whisper"]:
        ACTIVE_ENGINE = engine_name
        return True
    return False

# Cache for dynamically discovered Gemini models
_cached_gemini_models = None

def get_available_gemini_models(api_key):
    """
    Dynamically queries Google Gemini API to discover active models supporting generateContent.
    Returns a list of (model_clean_name, api_version) tuples.
    """
    global _cached_gemini_models
    if _cached_gemini_models is not None:
        return _cached_gemini_models

    discovered = []
    for api_ver in ["v1beta", "v1"]:
        try:
            url = f"https://generativelanguage.googleapis.com/{api_ver}/models?key={api_key}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Telegram-Stream-Tracker"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("models", []):
                    methods = item.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        raw_name = item.get("name", "")
                        clean_name = raw_name.replace("models/", "").strip()
                        pair = (clean_name, api_ver)
                        if pair not in discovered:
                            discovered.append(pair)
        except Exception:
            continue

    if discovered:
        _cached_gemini_models = discovered
        return discovered
    return []

# --- 1. GEMINI TRANSCRIBER & SUMMARIZER ---
async def transcribe_and_summarize_gemini(audio_path, chat_title="Voice Stream"):
    """
    Uses Google Gemini API to analyze the audio directly, generate a full transcript,
    and produce an executive meeting summary report with key action points.
    """
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Read audio bytes & MIME type
    file_size = os.path.getsize(audio_path)
    ext = Path(audio_path).suffix.lower().lstrip(".")
    mime_type_map = {
        "mp3": "audio/mp3",
        "wav": "audio/wav",
        "m4a": "audio/m4a",
        "ogg": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac"
    }
    mime_type = mime_type_map.get(ext, "audio/mp3")

    # If audio is small (< 20MB), upload directly via inlineData or File API
    import base64
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""You are an expert AI meeting scribe and transcription assistant analyzing a recorded voice call from '{chat_title}'.

Please provide your output in TWO clearly separated sections:

=== SUMMARY REPORT ===
🎙 **Meeting / Call**: {chat_title}
📅 **Date / Time**: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

📌 **Core Theme & Purpose**:
(1-2 sentences summarizing what this call was about)

📝 **Executive Summary**:
(A comprehensive 2-4 paragraph breakdown of the main discussions, points raised, and core messages)

🔑 **Key Takeaways & Highlights**:
• Point 1
• Point 2
• Point 3

🎯 **Decisions & Action Items**:
• Action item 1 (Assigned/Mentioned)
• Decision 2

=== FULL TRANSCRIPT ===
(Provide the full verbatim or near-verbatim transcription of everything spoken during the call, with speaker labels/timestamps if discernible)
"""

    preferred_model = os.getenv("GEMINI_MODEL", "").strip()

    # Priority list of model candidates
    default_candidates = [
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-2.0-flash-exp"
    ]

    target_pairs = []
    if preferred_model:
        target_pairs.append((preferred_model, "v1beta"))
        target_pairs.append((preferred_model, "v1"))

    # Dynamically fetch available models from the API for the given key
    discovered_pairs = get_available_gemini_models(api_key)
    for model_name, api_ver in discovered_pairs:
        if (model_name, api_ver) not in target_pairs:
            target_pairs.append((model_name, api_ver))

    # Add default candidates as fallback
    for model_name in default_candidates:
        for api_ver in ["v1beta", "v1"]:
            if (model_name, api_ver) not in target_pairs:
                target_pairs.append((model_name, api_ver))

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64
                    }
                },
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192
        }
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    last_error = None
    res_json = None
    used_model_name = ""

    def _try_post(endpoint_url):
        req = urllib.request.Request(
            endpoint_url,
            data=payload_bytes,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    loop = asyncio.get_running_loop()

    for model_name, api_ver in target_pairs:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_name}:generateContent?key={api_key}"
        try:
            res_json = await loop.run_in_executor(None, _try_post, url)
            if res_json and "candidates" in res_json:
                used_model_name = f"{model_name} ({api_ver})"
                break
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8")
            last_error = f"Gemini API error ({he.code}) on {model_name} ({api_ver}): {err_body}"
            if he.code in (404, 400):
                continue
            else:
                continue
        except Exception as e:
            last_error = f"Gemini request error on {model_name}: {e}"
            continue

    if not res_json or not res_json.get("candidates"):
        raise RuntimeError(last_error or "All Gemini model endpoints failed.")

    candidates = res_json.get("candidates", [])
    content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

    # Parse sections
    summary_part = ""
    transcript_part = ""
    if "=== FULL TRANSCRIPT ===" in content_text:
        parts = content_text.split("=== FULL TRANSCRIPT ===")
        summary_part = parts[0].replace("=== SUMMARY REPORT ===", "").strip()
        transcript_part = parts[1].strip()
    else:
        summary_part = content_text
        transcript_part = content_text

    return {
        "engine": f"Gemini ({used_model_name})",
        "summary": summary_part,
        "transcript": transcript_part,
        "raw": content_text
    }

# --- 2. GROQ WHISPER TRANSCRIBER ---
async def transcribe_groq(audio_path):
    """Transcribes audio using ultra-fast Groq Whisper API."""
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")

    # Multipart form-data upload for Groq audio transcription
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    filename = Path(audio_path).name

    with open(audio_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"whisper-large-v3-turbo\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )

    def _sync_groq():
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, _sync_groq)
    return res.get("text", "")

# --- 3. OPENAI WHISPER TRANSCRIBER ---
async def transcribe_openai(audio_path):
    """Transcribes audio using OpenAI Whisper API."""
    api_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    filename = Path(audio_path).name

    with open(audio_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"whisper-1\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )

    def _sync_openai():
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, _sync_openai)
    return res.get("text", "")

# --- 4. LOCAL FASTER-WHISPER TRANSCRIBER ---
async def transcribe_faster_whisper(audio_path):
    """Transcribes audio locally using faster-whisper (offline fallback)."""
    def _sync_local():
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join([seg.text for seg in segments])
        return text

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_local)

# --- 5. TEXT SUMMARIZER (FOR WHISPER TRANSCRIPTS) ---
async def summarize_transcript_text(transcript_text, chat_title="Voice Stream"):
    """Summarizes plain transcript text into a structured executive report."""
    if not transcript_text.strip():
        return "⚠️ No spoken audio or intelligible dialogue was detected."

    # Use Gemini for summarization if available
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if api_key:
        prompt = f"""You are an executive scribe. Summarize this call transcript from '{chat_title}':

Transcript:
{transcript_text[:30000]}

Provide the summary formatted as:
🎙 **Meeting / Call**: {chat_title}
📅 **Date / Time**: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

📌 **Core Theme**:
(Summary)

📝 **Executive Summary**:
(Detailed overview of points discussed)

🔑 **Key Highlights**:
• Bullet points

🎯 **Decisions & Next Steps**:
• Action items
"""
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        payload_bytes = json.dumps(payload).encode("utf-8")

        def _sync_summary(endpoint_url):
            req = urllib.request.Request(endpoint_url, data=payload_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]

        loop = asyncio.get_running_loop()
        preferred_model = os.getenv("GEMINI_MODEL", "").strip()
        default_candidates = [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro"
        ]
        target_pairs = []
        if preferred_model:
            target_pairs.append((preferred_model, "v1beta"))
            target_pairs.append((preferred_model, "v1"))

        discovered_pairs = get_available_gemini_models(api_key)
        for model_name, api_ver in discovered_pairs:
            if (model_name, api_ver) not in target_pairs:
                target_pairs.append((model_name, api_ver))

        for model_name in default_candidates:
            for api_ver in ["v1beta", "v1"]:
                if (model_name, api_ver) not in target_pairs:
                    target_pairs.append((model_name, api_ver))

        for model_name, api_ver in target_pairs:
            url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_name}:generateContent?key={api_key}"
            try:
                summary_text = await loop.run_in_executor(None, _sync_summary, url)
                if summary_text:
                    return summary_text
            except Exception:
                continue

    # Fallback to simple text outline if no LLM key
    lines = [s.strip() for s in transcript_text.split(".") if len(s.strip()) > 10]
    preview = ". ".join(lines[:5]) + ("..." if len(lines) > 5 else ".")
    return (
        f"🎙 **Meeting / Call**: {chat_title}\n"
        f"📅 **Date**: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"📝 **Summary Preview**:\n{preview}\n\n"
        f"_See attached transcript document for full text._"
    )

# --- 6. UNIFIED PROCESSOR WITH AUTOMATIC FALLBACK ---
async def process_audio_file(audio_path, chat_title="Voice Stream", stream_id=None):
    """
    Unified entry point: processes an audio file through the active engine with automatic fallback.
    Returns: dict with summary, transcript, transcript_path, audio_path, engine_used
    """
    if not stream_id:
        stream_id = f"audio_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    result = None
    engine_used = ""
    errors = []

    preferred = ACTIVE_ENGINE

    # Try preferred engine first
    if preferred == "gemini":
        try:
            result = await transcribe_and_summarize_gemini(audio_path, chat_title=chat_title)
            engine_used = result.get("engine", "Gemini AI")
        except Exception as e:
            errors.append(f"Gemini failed ({e})")

    elif preferred == "groq":
        try:
            raw_text = await transcribe_groq(audio_path)
            summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
            result = {"summary": summary, "transcript": raw_text}
            engine_used = "Groq Whisper + LLM"
        except Exception as e:
            errors.append(f"Groq failed ({e})")

    elif preferred == "openai":
        try:
            raw_text = await transcribe_openai(audio_path)
            summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
            result = {"summary": summary, "transcript": raw_text}
            engine_used = "OpenAI Whisper + LLM"
        except Exception as e:
            errors.append(f"OpenAI failed ({e})")

    elif preferred == "faster_whisper":
        try:
            raw_text = await transcribe_faster_whisper(audio_path)
            summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
            result = {"summary": summary, "transcript": raw_text}
            engine_used = "Local Faster-Whisper"
        except Exception as e:
            errors.append(f"Faster-Whisper failed ({e})")

    # Fallback cascade if preferred failed or not configured
    if not result:
        # Fallback 1: Gemini
        if "gemini" not in preferred and os.getenv("GEMINI_API_KEY", GEMINI_API_KEY):
            try:
                result = await transcribe_and_summarize_gemini(audio_path, chat_title=chat_title)
                engine_used = f"{result.get('engine', 'Gemini AI')} (Fallback)"
            except Exception as e:
                errors.append(f"Gemini fallback failed ({e})")

        # Fallback 2: Groq
        if not result and os.getenv("GROQ_API_KEY", GROQ_API_KEY):
            try:
                raw_text = await transcribe_groq(audio_path)
                summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
                result = {"summary": summary, "transcript": raw_text}
                engine_used = "Groq Whisper (Fallback)"
            except Exception as e:
                errors.append(f"Groq fallback failed ({e})")

        # Fallback 3: OpenAI
        if not result and os.getenv("OPENAI_API_KEY", OPENAI_API_KEY):
            try:
                raw_text = await transcribe_openai(audio_path)
                summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
                result = {"summary": summary, "transcript": raw_text}
                engine_used = "OpenAI Whisper (Fallback)"
            except Exception as e:
                errors.append(f"OpenAI fallback failed ({e})")

        # Fallback 4: Local faster-whisper
        if not result:
            try:
                raw_text = await transcribe_faster_whisper(audio_path)
                summary = await summarize_transcript_text(raw_text, chat_title=chat_title)
                result = {"summary": summary, "transcript": raw_text}
                engine_used = "Local Faster-Whisper (Offline Fallback)"
            except Exception as e:
                errors.append(f"Faster-whisper fallback failed ({e})")

    if not result:
        raise RuntimeError(f"All transcription engines failed: {'; '.join(errors)}")

    # Save transcript and summary files
    transcript_file = os.path.join(TRANSCRIPTS_DIR, f"transcript_{stream_id}.txt")
    summary_file = os.path.join(TRANSCRIPTS_DIR, f"summary_{stream_id}.md")

    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(f"FULL TRANSCRIPT: {chat_title}\nGenerated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\nEngine: {engine_used}\n\n")
        f.write(result.get("transcript", ""))

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(result.get("summary", ""))

    return {
        "engine": engine_used,
        "summary": result.get("summary", ""),
        "transcript": result.get("transcript", ""),
        "transcript_path": transcript_file,
        "summary_path": summary_file,
        "audio_path": audio_path,
        "stream_id": stream_id
    }
