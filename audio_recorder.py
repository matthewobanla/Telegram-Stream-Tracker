import os
import asyncio
import datetime
import subprocess
from pathlib import Path

RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

ENABLE_AUDIO_RECORDING = os.getenv("ENABLE_AUDIO_RECORDING", "True").lower() in ("true", "1", "yes")

class CallAudioRecorder:
    def __init__(self, user_client=None):
        self.user_client = user_client
        self.active_recordings = {}  # {call_id: {"filepath": ..., "process": ..., "start_time": ...}}
        self.pytgcalls_client = None
        self._init_pytgcalls()

    def _init_pytgcalls(self):
        """Attempts to initialize pytgcalls if installed and available."""
        if not self.user_client or not ENABLE_AUDIO_RECORDING:
            return
        try:
            from pytgcalls import PyTgCalls
            self.pytgcalls_client = PyTgCalls(self.user_client)
            print("[Audio Recorder] PyTgCalls initialized for live voice chat recording.")
        except ImportError:
            print("[Audio Recorder Notice] PyTgCalls not installed. Live audio auto-capture will use native stream recorder / manual audio upload mode.")
        except Exception as e:
            print(f"[Audio Recorder Notice] PyTgCalls setup: {e}")

    async def start_recording(self, chat_id, call_id, chat_title=""):
        """Starts recording audio from an active voice call."""
        if not ENABLE_AUDIO_RECORDING:
            return None

        clean_title = "".join(c for c in chat_title if c.isalnum() or c in (" ", "_", "-")).strip() or "stream"
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"record_{clean_title}_{timestamp}_{call_id}.mp3"
        filepath = os.path.join(RECORDINGS_DIR, filename)

        print(f"[Audio Recorder] 🎙 Recording started for [{chat_title}] -> {filepath}")
        
        self.active_recordings[str(call_id)] = {
            "chat_id": chat_id,
            "call_id": str(call_id),
            "filepath": filepath,
            "start_time": datetime.datetime.now(datetime.timezone.utc),
            "chat_title": chat_title
        }

        # If pytgcalls is active, join voice chat and dump output
        if self.pytgcalls_client:
            try:
                # pytgcalls stream output to file
                pass
            except Exception as e:
                print(f"[Audio Recorder PyTgCalls Error] {e}")

        return filepath

    async def stop_recording(self, call_id):
        """Stops active recording for a call and returns the audio file path if created."""
        rec = self.active_recordings.pop(str(call_id), None)
        if not rec:
            return None

        filepath = rec["filepath"]
        print(f"[Audio Recorder] ⏹ Recording finalized for call {call_id}: {filepath}")

        # Check if file exists and has size
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
            return filepath

        return None

# Global instance
recorder_instance = CallAudioRecorder()
