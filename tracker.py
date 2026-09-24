import os
import sys
import csv
import asyncio
import datetime
import warnings
from tabulate import tabulate
from telethon import TelegramClient, events, errors
from telethon.tl import types, functions
from telethon.sessions import StringSession, MemorySession
import base64
import config
import db

warnings.filterwarnings("ignore", category=DeprecationWarning)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SESSION_STRING = os.getenv("SESSION_STRING", getattr(config, "SESSION_STRING", "")).strip().strip("'").strip('"')
SESSION_B64 = os.getenv("SESSION_B64", getattr(config, "SESSION_B64", "")).strip().strip("'").strip('"')

if SESSION_STRING:
    print(f"[Session Loader] Configured SESSION_STRING ({len(SESSION_STRING)} chars, prefix: '{SESSION_STRING[:12]}...').")
elif SESSION_B64:
    try:
        decoded_bytes = base64.b64decode(SESSION_B64)
        with open("tracker_session.session", "wb") as f:
            f.write(decoded_bytes)
        print(f"[Session Loader] Successfully restored tracker_session.session ({len(decoded_bytes)} bytes) from SESSION_B64.")
    except Exception as e:
        print(f"[Session Loader Error] Could not decode SESSION_B64: {e}")

API_ID = int(os.getenv("API_ID", config.API_ID))
API_HASH = os.getenv("API_HASH", config.API_HASH)
BOT_TOKEN = os.getenv("BOT_TOKEN", getattr(config, "BOT_TOKEN", ""))
TARGET_CHAT_ENV = os.getenv("TARGET_CHAT", config.TARGET_CHAT)
AUTO_POST_REPORT = bool(os.getenv("AUTO_POST_REPORT", getattr(config, "AUTO_POST_REPORT", True)))
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", getattr(config, "ADMIN_CHAT_ID", "@KingmattMO"))
AUTO_POST_TO_GROUP = bool(os.getenv("AUTO_POST_TO_GROUP", getattr(config, "AUTO_POST_TO_GROUP", False)))
CSV_OUTPUT_DIR = os.getenv("CSV_OUTPUT_DIR", config.CSV_OUTPUT_DIR)
MIN_ATTENDANCE_SECONDS = int(os.getenv("MIN_ATTENDANCE_SECONDS", getattr(config, "MIN_ATTENDANCE_SECONDS", 30)))
EXCLUDE_PREVIEWS_FROM_CSV = bool(os.getenv("EXCLUDE_PREVIEWS_FROM_CSV", getattr(config, "EXCLUDE_PREVIEWS_FROM_CSV", False)))

os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
db.init_db()

# Initialize Telethon clients
if SESSION_STRING:
    user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)
    print(f"[Session Loader] Initialized Telegram client using SESSION_STRING.")
else:
    user_client = TelegramClient("tracker_session", API_ID, API_HASH, connection_retries=None, auto_reconnect=True)
    print(f"[Session Loader] Initialized Telegram client using local 'tracker_session.session' file.")

bot_client = TelegramClient(MemorySession(), API_ID, API_HASH, connection_retries=None, auto_reconnect=True)
bot_active = False

# Global cache for entity name resolution
entity_cache = {}

async def resolve_peer_info(client_instance, peer):
    pid = getattr(peer, "user_id", None) or getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
    if not pid:
        return None, "Unknown", ""

    if pid in entity_cache:
        return pid, entity_cache[pid]["name"], entity_cache[pid]["username"]

    try:
        entity = await client_instance.get_entity(peer)
        if isinstance(entity, types.User):
            first = getattr(entity, "first_name", "") or ""
            last = getattr(entity, "last_name", "") or ""
            name = f"{first} {last}".strip() or f"User {pid}"
            username = getattr(entity, "username", "") or ""
        else:
            name = getattr(entity, "title", "") or f"Channel {pid}"
            username = getattr(entity, "username", "") or ""

        entity_cache[pid] = {"name": name, "username": username}
        return pid, name, username
    except Exception:
        return pid, f"Participant {pid}", ""

# --- CALL SESSION TRACKER FOR A SINGLE STREAM ---
class CallSessionTracker:
    def __init__(self, call_input, chat_title="", chat_id=""):
        call_id = getattr(call_input, "id", None)
        now = datetime.datetime.now(datetime.timezone.utc)
        self.active_call_id = call_id
        self.active_call_input = call_input
        self.chat_title = chat_title
        self.chat_id = str(chat_id)
        self.call_start_time = now
        self.call_end_time = None
        self.active_stream_id = f"stream_{now.strftime('%Y%m%d_%H%M%S')}_{call_id}"
        self.participants = {}
        self.last_csv_path = None
        self.consecutive_empty_polls = 0

        db.save_stream_start(self.active_stream_id, call_id, chat_title, now, chat_id=self.chat_id)
        print(f"\n[LIVE STREAM STARTED] [{self.chat_title}] Stream ID: {self.active_stream_id} at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("Monitoring participant join/leave events...\n")

    def register_join(self, user_id: int, name: str, username: str = ""):
        now = datetime.datetime.now(datetime.timezone.utc)
        state_changed = False
        if user_id not in self.participants:
            self.participants[user_id] = {
                "name": name,
                "username": username,
                "sessions": [],
                "current_join": now
            }
            uname_str = f" (@{username})" if username else ""
            print(f" [+] JOIN [{self.chat_title}]: {name}{uname_str} [ID: {user_id}] at {now.strftime('%H:%M:%S UTC')} (Total: {len(self.participants)})")
            state_changed = True
        else:
            if name and not name.startswith("Participant ") and not name.startswith("User "):
                self.participants[user_id]["name"] = name
            if username:
                self.participants[user_id]["username"] = username

            if self.participants[user_id]["current_join"] is None:
                self.participants[user_id]["current_join"] = now
                uname_str = f" (@{self.participants[user_id]['username']})" if self.participants[user_id]['username'] else ""
                print(f" [+] REJOIN [{self.chat_title}]: {self.participants[user_id]['name']}{uname_str} [ID: {user_id}] at {now.strftime('%H:%M:%S UTC')}")
                state_changed = True

        if state_changed:
            try:
                db.save_participant_join(self.active_stream_id, user_id, self.participants[user_id]["name"], self.participants[user_id]["username"], now)
            except Exception as e:
                print(f"[DB Join Error] {e}")

    def register_leave(self, user_id: int):
        now = datetime.datetime.now(datetime.timezone.utc)
        if user_id in self.participants and self.participants[user_id]["current_join"] is not None:
            join_time = self.participants[user_id]["current_join"]
            self.participants[user_id]["sessions"].append((join_time, now))
            self.participants[user_id]["current_join"] = None
            session_duration_sec = (now - join_time).total_seconds()
            uname_str = f" (@{self.participants[user_id]['username']})" if self.participants[user_id]['username'] else ""
            print(f" [-] LEAVE [{self.chat_title}]: {self.participants[user_id]['name']}{uname_str} at {now.strftime('%H:%M:%S UTC')} (Session: {session_duration_sec/60:.1f} min)")
            try:
                db.save_participant_leave(self.active_stream_id, user_id, now)
            except Exception as e:
                print(f"[DB Leave Error] {e}")

    def end_call(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self.call_end_time = now

        for uid, pdata in self.participants.items():
            if pdata["current_join"] is not None:
                pdata["sessions"].append((pdata["current_join"], now))
                pdata["current_join"] = None

        print(f"\n[LIVE STREAM ENDED] [{self.chat_title}] Ended at: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        csv_file = self.generate_csv()
        db.save_stream_end(self.active_stream_id, now, csv_file)
        self.last_csv_path = csv_file
        self.generate_console_report()

        ended_stream_id = self.active_stream_id
        return ended_stream_id, csv_file

    def generate_csv(self):
        stats = self.get_current_stats()
        if not stats or not stats["participants"]:
            return ""

        clean_title = "".join(c for c in self.chat_title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:20]
        prefix = f"{clean_title}_" if clean_title else ""
        filename = f"report_{prefix}{stats['start_time'].strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(CSV_OUTPUT_DIR, filename)

        all_participants = stats["participants"]
        valid_attendees = [p for p in all_participants if p.get("total_sec", 0) >= MIN_ATTENDANCE_SECONDS]
        preview_attendees = [p for p in all_participants if p.get("total_sec", 0) < MIN_ATTENDANCE_SECONDS]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "User ID", "Name", "Username", "First Join (UTC)", "Last Leave (UTC)", "Session Count", "Total Duration (Minutes)", "Participation (%)", "Attendance Status"])
            for rank, p in enumerate(valid_attendees, 1):
                writer.writerow([rank, p["uid"], p["name"], p["username"], p["first_join"], p["last_leave"], p["session_count"], f"{p['total_min']:.2f}", f"{p['pct']:.2f}", "Attended"])
            
            if not EXCLUDE_PREVIEWS_FROM_CSV:
                for p in preview_attendees:
                    writer.writerow(["-", p["uid"], p["name"], p["username"], p["first_join"], p["last_leave"], p["session_count"], f"{p['total_min']:.2f}", f"{p['pct']:.2f}", f"Brief Preview (<{MIN_ATTENDANCE_SECONDS}s)"])

        self.last_csv_path = filepath
        print(f"\n[CSV Exported] Successfully saved to: {os.path.abspath(filepath)} (Attendees: {len(valid_attendees)}, Previews: {len(preview_attendees)})")
        return filepath

    def get_current_stats(self):
        if not self.call_start_time:
            return None

        start_time = self.call_start_time
        end_time = self.call_end_time or datetime.datetime.now(datetime.timezone.utc)
        total_call_sec = max(1.0, (end_time - start_time).total_seconds())
        total_call_min = total_call_sec / 60.0

        participant_stats = []
        for uid, pdata in self.participants.items():
            user_total_sec = sum((leave - join).total_seconds() for join, leave in pdata["sessions"])
            if pdata["current_join"] is not None:
                user_total_sec += (end_time - pdata["current_join"]).total_seconds()

            user_total_min = user_total_sec / 60.0
            pct = min(100.0, (user_total_sec / total_call_sec) * 100.0)

            first_join = pdata["sessions"][0][0].strftime("%H:%M:%S") if pdata["sessions"] else (pdata["current_join"].strftime("%H:%M:%S") if pdata["current_join"] else "N/A")
            last_leave = pdata["sessions"][-1][1].strftime("%H:%M:%S") if (pdata["sessions"] and pdata["current_join"] is None) else ("Online" if pdata["current_join"] else "N/A")

            participant_stats.append({
                "uid": uid,
                "name": pdata["name"],
                "username": pdata["username"],
                "first_join": first_join,
                "last_leave": last_leave,
                "session_count": len(pdata["sessions"]) + (1 if pdata["current_join"] else 0),
                "total_sec": user_total_sec,
                "total_min": user_total_min,
                "pct": pct,
                "is_online": pdata["current_join"] is not None
            })

        participant_stats.sort(key=lambda x: x["total_sec"], reverse=True)
        return {
            "start_time": start_time,
            "end_time": end_time,
            "chat_title": self.chat_title,
            "chat_id": self.chat_id,
            "is_active": self.call_end_time is None,
            "total_min": total_call_min,
            "total_sec": total_call_sec,
            "participants": participant_stats
        }

    def generate_console_report(self):
        stats = self.get_current_stats()
        if not stats or not stats["participants"]:
            return

        all_participants = stats["participants"]
        valid_attendees = [p for p in all_participants if p.get("total_sec", 0) >= MIN_ATTENDANCE_SECONDS]
        brief_count = len(all_participants) - len(valid_attendees)

        headers = ["Rank", "Name", "Username", "First Join", "Last Leave", "Sessions", "Total Time", "Participation"]
        table_rows = []
        for rank, p in enumerate(valid_attendees, 1):
            table_rows.append([
                rank,
                p["name"][:25],
                f"@{p['username']}" if p["username"] else "-",
                p["first_join"],
                p["last_leave"],
                p["session_count"],
                f"{p['total_min']:.1f} min",
                f"{p['pct']:.1f}%"
            ])

        print("\n" + "=" * 80)
        print(f"  LIVE STREAM PARTICIPATION REPORT: {self.chat_title}")
        print(f"  Start Time : {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  End Time   : {stats['end_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Duration   : {stats['total_min']:.2f} minutes ({int(stats['total_sec'])} seconds)")
        print(f"  Attendees  : {len(valid_attendees)} (plus {brief_count} previewers < {MIN_ATTENDANCE_SECONDS}s)")
        print("=" * 80)
        if table_rows:
            print(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))
        else:
            print(f"  No attendees exceeded the {MIN_ATTENDANCE_SECONDS}s threshold.")
        print("=" * 80 + "\n")

# --- MULTI-CALL TRACKER MANAGER ---
class MultiCallManager:
    def __init__(self):
        self.active_trackers = {}   # call_id -> CallSessionTracker
        self.chat_to_call = {}      # chat_id (str) -> call_id

    def get_tracker_for_call(self, call_id):
        if call_id in self.active_trackers:
            return self.active_trackers[call_id]
        return None

    def get_tracker_for_chat(self, chat_id):
        cid_str = str(chat_id)
        if cid_str in self.chat_to_call:
            call_id = self.chat_to_call[cid_str]
            return self.active_trackers.get(call_id)
        return None

    def start_call(self, call_input, chat_title, chat_id):
        call_id = getattr(call_input, "id", None)
        if not call_id:
            return None
        if call_id in self.active_trackers:
            return self.active_trackers[call_id]

        tracker = CallSessionTracker(call_input, chat_title, chat_id)
        self.active_trackers[call_id] = tracker
        self.chat_to_call[str(chat_id)] = call_id
        return tracker

    def end_call_by_id(self, call_id):
        if call_id in self.active_trackers:
            tracker = self.active_trackers.pop(call_id)
            if tracker.chat_id in self.chat_to_call and self.chat_to_call[tracker.chat_id] == call_id:
                del self.chat_to_call[tracker.chat_id]
            return tracker.end_call()
        return None, None

    def end_call_by_chat(self, chat_id):
        cid_str = str(chat_id)
        if cid_str in self.chat_to_call:
            call_id = self.chat_to_call[cid_str]
            return self.end_call_by_id(call_id)
        return None, None

    def get_all_active(self):
        return list(self.active_trackers.values())

tracker_manager = MultiCallManager()

# --- TRACKED GROUPS REGISTRY & RESOLUTION ---
tracked_entities = {}  # str(entity_id) -> {"target": target, "entity": entity, "title": title}
tracked_targets_map = {} # target (lowercase/str) -> entity

async def resolve_and_add_target(target_val, added_by="Owner"):
    """Resolves a target group/channel and adds it to the active tracking list and database."""
    global user_client, tracked_entities, tracked_targets_map
    target_str = str(target_val).strip()
    if not target_str:
        return False, "Target cannot be empty."

    # Parse numeric vs string
    if target_str.isdigit() or (target_str.startswith("-") and target_str[1:].isdigit()):
        lookup = int(target_str)
    else:
        lookup = target_str

    try:
        entity = await user_client.get_entity(lookup)
        title = getattr(entity, "title", target_str)
        entity_id_str = str(entity.id)
        username = getattr(entity, "username", "")
        formatted_target = f"@{username}" if username else str(entity.id)

        # Save to DB
        db.add_tracked_group(formatted_target, title=title, entity_id=entity_id_str, added_by=str(added_by))
        
        info = {"target": formatted_target, "entity": entity, "title": title, "entity_id": entity_id_str}
        tracked_entities[entity_id_str] = info
        tracked_targets_map[formatted_target.lower()] = info
        tracked_targets_map[entity_id_str] = info
        if username:
            tracked_targets_map[f"@{username.lower()}"] = info
            tracked_targets_map[username.lower()] = info

        print(f"[Tracked Group Added] ✅ '{title}' (ID: {entity_id_str}, Target: {formatted_target})")
        return True, f"✅ Successfully added group: **{title}** (`{formatted_target}`)"
    except Exception as e:
        print(f"[Tracked Group Error] Could not resolve '{target_str}': {e}")
        return False, f"⚠️ Could not resolve target `{target_str}`: {e}\n_Ensure your user account is a member of the group._"

async def untrack_target(target_val):
    """Removes a target group from tracking."""
    global tracked_entities, tracked_targets_map
    target_str = str(target_val).strip()
    if not target_str:
        return False, "Target cannot be empty."

    target_key = target_str.lower()
    matched_info = tracked_targets_map.get(target_key)
    
    # Try finding in tracked_entities
    if not matched_info:
        for eid, info in list(tracked_entities.items()):
            if info["target"].lower() == target_key or eid == target_str or info["title"].lower() == target_key:
                matched_info = info
                break

    removed_db = db.remove_tracked_group(target_str)
    if matched_info:
        eid = matched_info["entity_id"]
        title = matched_info["title"]
        tracked_entities.pop(eid, None)
        keys_to_del = [k for k, v in tracked_targets_map.items() if v.get("entity_id") == eid]
        for k in keys_to_del:
            tracked_targets_map.pop(k, None)
        return True, f"🗑 Removed **{title}** from tracked groups."
    elif removed_db:
        return True, f"🗑 Removed `{target_str}` from tracked groups."
    else:
        return False, f"⚠️ `{target_str}` was not found in the active tracked groups list."

def format_report_message(stream_meta, participants, is_active=False):
    status_tag = "🔴 LIVE NOW" if is_active else "🏁 CALL FINISHED"
    chat_title = stream_meta.get("chat_title", "")
    title_header = f" [{chat_title}]" if chat_title else ""
    start_dt = datetime.datetime.fromisoformat(stream_meta["start_time"]) if isinstance(stream_meta["start_time"], str) else stream_meta["start_time"]
    dur_min = stream_meta.get("duration_sec", 0) / 60.0 if not is_active else stream_meta.get("total_min", 0)

    # Separate genuine attendees from brief previews (< MIN_ATTENDANCE_SECONDS)
    valid_participants = []
    brief_count = 0
    for p in (participants or []):
        total_s = p.get("total_sec", 0)
        if not total_s and p.get("total_min"):
            total_s = p.get("total_min") * 60.0
        if total_s >= MIN_ATTENDANCE_SECONDS:
            valid_participants.append(p)
        else:
            brief_count += 1

    msg = f"📊 **Live Stream Participation Report{title_header}** ({status_tag})\n\n"
    msg += f"⏱ **Duration**: `{dur_min:.1f} mins`\n"

    if brief_count > 0:
        msg += f"👥 **Attendees**: `{len(valid_participants)}` _(+{brief_count} brief previews <{MIN_ATTENDANCE_SECONDS}s)_\n"
    else:
        msg += f"👥 **Total Attendees**: `{len(valid_participants)}`\n"

    msg += f"📅 **Started**: `{start_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}`\n\n"
    msg += "🏆 **Participant Leaderboard**:\n"

    if not valid_participants:
        if brief_count > 0:
            msg += f"_No attendees stayed longer than {MIN_ATTENDANCE_SECONDS}s ({brief_count} previewers recorded in CSV)._\n"
        else:
            msg += "_No participants recorded for this session._\n"
        return msg

    for rank, p in enumerate(valid_participants[:20], 1):
        uname = f" (@{p['username']})" if p.get('username') else ""
        dot = "🟢" if p.get("is_online") else "⚪️"
        total_m = p.get("total_min", 0)
        pct_val = p.get("pct", 0)
        sess_c = p.get("session_count", 1)
        msg += f"`#{rank:02d}` {dot} **{p['name']}**{uname}\n"
        msg += f"      └ ⏳ `{total_m:.1f}m` ({pct_val:.1f}%) | 🚪 `{sess_c}` joins\n"

    if len(valid_participants) > 20:
        msg += f"\n_...and {len(valid_participants) - 20} more attendees in CSV export._"
    elif brief_count > 0 and not EXCLUDE_PREVIEWS_FROM_CSV:
        msg += f"\n_Note: {brief_count} brief previewers (<{MIN_ATTENDANCE_SECONDS}s) archived in CSV spreadsheet._"

    return msg

async def send_auto_report(csv_path, expected_stream_id=None, group_entity=None, chat_title=""):
    """Sends the post-stream report and CSV directly to configured admin(s) and/or the specific group."""
    if not AUTO_POST_REPORT:
        return

    try:
        stream_meta, participants = db.get_latest_stream()
        if not stream_meta or not participants:
            return

        if expected_stream_id and stream_meta.get("stream_id") != expected_stream_id:
            print(f"[Auto-Report] Skipped sending report: latest stream '{stream_meta.get('stream_id')}' does not match expected '{expected_stream_id}'")
            return

        # Ignore accidental or phantom 0-second / empty streams
        if stream_meta.get("duration_sec", 0) < 5 and len(participants) == 0:
            print("[Auto-Report] Skipped auto-report for negligible empty stream session.")
            return

        report_text = format_report_message(stream_meta, participants, is_active=False)

        # Collect targets
        recipients = []
        db_recipients = db.get_admin_recipients()
        for r in db_recipients:
            if r not in recipients:
                recipients.append(r)

        if not recipients and ADMIN_CHAT_ID:
            for item in str(ADMIN_CHAT_ID).split(","):
                val = item.strip()
                if val and val not in recipients:
                    recipients.append(val)

        # If posting to group is enabled, include the specific group entity/target
        if AUTO_POST_TO_GROUP and group_entity is not None:
            try:
                await bot_client.send_message(group_entity, report_text, parse_mode="markdown")
                if csv_path and os.path.exists(csv_path):
                    await bot_client.send_file(
                        group_entity,
                        csv_path,
                        caption=f"📊 **Final Participation Spreadsheet ({chat_title})**\nDuration: {stream_meta.get('duration_sec', 0)/60.0:.1f} mins | Total: {len(participants)} callers"
                    )
                print(f"[Auto-Report] Successfully posted report into group: {chat_title}")
            except Exception as ge:
                print(f"[Auto-Report Notice] Could not post to group {chat_title}: {ge}")

        # Send to admin DMs
        for target in recipients:
            try:
                target_val = int(target) if (isinstance(target, str) and (target.isdigit() or (target.startswith("-") and target[1:].isdigit()))) else target
                bot_target = await bot_client.get_entity(target_val)
                await bot_client.send_message(bot_target, report_text, parse_mode="markdown")

                if csv_path and os.path.exists(csv_path):
                    await bot_client.send_file(
                        bot_target,
                        csv_path,
                        caption=f"📊 **Final Participation Spreadsheet ({chat_title})**\nDuration: {stream_meta.get('duration_sec', 0)/60.0:.1f} mins | Total: {len(participants)} callers"
                    )
                print(f"[Auto-Report] Successfully sent report and CSV to admin: {target}")
            except Exception as e:
                print(f"[Auto-Report Notice] Could not send to admin {target}: {e}")
                print(f"                     (Ensure admin sent /start to the bot once in private DM)")
    except Exception as e:
        print(f"[Auto-Report Error] Could not dispatch auto-report: {e}")

async def safe_reply(event, text, file=None, **kwargs):
    """Safely replies to a Telegram event, handling connection drops and formatting issues."""
    for attempt in range(2):
        try:
            if hasattr(event, "client") and event.client and not event.client.is_connected():
                await event.client.connect()
            if file:
                return await event.reply(message=text, file=file, **kwargs)
            return await event.reply(text, **kwargs)
        except (ConnectionError, OSError) as ce:
            print(f"[Bot Reply Notice] Connection dropped ({ce}), reconnecting and retrying...")
            try:
                if hasattr(event, "client") and event.client:
                    await event.client.connect()
            except Exception:
                pass
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Bot Reply Notice] Formatting error ({e}), retrying without markdown...")
            try:
                if file:
                    return await event.reply(message=text, file=file, parse_mode=None)
                return await event.reply(text, parse_mode=None)
            except Exception as e2:
                print(f"[Bot Reply Error] Failed to send reply: {e2}")
            break

# --- IN-TELEGRAM COMMAND HANDLERS ---
@bot_client.on(events.NewMessage)
async def bot_command_handler(event):
    text = event.raw_text.strip()
    if not text:
        return

    # If it's a private chat (DM) and user sends any text without a slash, reply with the menu
    if event.is_private and not (text.startswith("/") or text.startswith(".")):
        help_text = (
            "🤖 **Telegram Live Stream Tracker Bot (Multi-Group Ready)**\n\n"
            "**📊 Stream Reports & Live Stats:**\n"
            "• `/stats` or `/report` - Show participant leaderboard & participation %\n"
            "• `/livestatus` - Check live voice chat status across all tracked groups\n"
            "• `/export` or `/csv` - Download the CSV participation spreadsheet\n\n"
            "**👥 Group Tracking Management:**\n"
            "• `/groups` - View all currently tracked groups and their live status\n"
            "• `/trackhere` - (In group) Start tracking this group immediately\n"
            "• `/addgroup @group` - Add a group/channel by username or ID\n"
            "• `/removegroup @group` - Remove a group from tracking\n\n"
            "**👑 Admin Routing Options:**\n"
            "• `/admins` - View list of admins receiving auto-reports\n"
            "• `/addadmin @username` - Add an admin to receive reports in DM\n"
            "• `/removeadmin @username` - Remove an admin from reports\n"
            "• `/help` - Show this menu"
        )
        await safe_reply(event, help_text, parse_mode="markdown")
        return

    if not (text.startswith("/") or text.startswith(".")):
        return

    raw_cmd = text.split()[0].lower().replace(".", "/")
    cmd = raw_cmd.split("@")[0]
    print(f"[BOT COMMAND] Received '{raw_cmd}' from chat_id={event.chat_id}")

    # 1. GROUP MANAGEMENT COMMANDS
    if cmd in ["/groups", "/listgroups", "/trackedgroups"]:
        tracked_db = db.get_tracked_groups()
        if not tracked_db:
            await safe_reply(event, "⚠️ No groups are currently being tracked.\nUse `/trackhere` in a group or `/addgroup @username` to add one.", parse_mode="markdown")
            return

        msg = f"📋 **Tracked Groups & Live Status** ({len(tracked_db)}):\n\n"
        for idx, g in enumerate(tracked_db, 1):
            title = g.get("title") or g.get("target")
            target = g.get("target")
            eid = g.get("entity_id", "")
            
            # Check if this group has an active stream
            active_tracker = tracker_manager.get_tracker_for_chat(eid)
            if active_tracker:
                stats = active_tracker.get_current_stats()
                online_count = sum(1 for p in stats["participants"] if p["is_online"])
                status_icon = f"🔴 **LIVE NOW** ({stats['total_min']:.1f}m | 👥 {online_count} online)"
            else:
                status_icon = "⚪️ Idle"

            msg += f"`#{idx}` **{title}** (`{target}`)\n    └ Status: {status_icon}\n"

        msg += "\n_Use `/trackhere` in any group or `/addgroup @group` to add more._"
        await safe_reply(event, msg, parse_mode="markdown")

    elif cmd in ["/trackhere", "/trackthis"]:
        if event.is_private:
            await safe_reply(event, "⚠️ `/trackhere` can only be used inside a Telegram Group or Channel.\nTo add a group from DM, use `/addgroup @username`.", parse_mode="markdown")
            return

        chat_id = event.chat_id
        success, reply_msg = await resolve_and_add_target(chat_id, added_by=str(event.sender_id or "Admin"))
        await safe_reply(event, reply_msg, parse_mode="markdown")

    elif cmd in ["/addgroup", "/trackgroup", "/setgroup"]:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await safe_reply(event, "ℹ️ **Usage**: `/addgroup @group_username` or `/addgroup <ChatID>`\nExample: `/addgroup @kingshubBC`", parse_mode="markdown")
            return

        targets_to_add = [t.strip() for t in parts[1].split(",") if t.strip()]
        results = []
        for t in targets_to_add:
            if not t.startswith("@") and not t.isdigit() and not (t.startswith("-") and t[1:].isdigit()):
                t = f"@{t}"
            ok, msg = await resolve_and_add_target(t, added_by=str(event.sender_id or event.chat_id))
            results.append(msg)

        await safe_reply(event, "\n".join(results), parse_mode="markdown")

    elif cmd in ["/removegroup", "/untrack", "/delgroup", "/untrackhere"]:
        if cmd == "/untrackhere" or (len(text.split()) == 1 and not event.is_private):
            target_to_remove = str(event.chat_id)
        else:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await safe_reply(event, "ℹ️ **Usage**: `/removegroup @group_username` or `/removegroup <ChatID>`", parse_mode="markdown")
                return
            target_to_remove = parts[1].strip()

        ok, reply_msg = await untrack_target(target_to_remove)
        await safe_reply(event, reply_msg, parse_mode="markdown")

    # 2. STATS & LEADERBOARD COMMANDS
    elif cmd in ["/stats", "/report", "/leaderboard"]:
        chat_id_str = str(event.chat_id)
        active_tracker = tracker_manager.get_tracker_for_chat(chat_id_str)
        
        # If run inside a specific group with an active stream
        if active_tracker:
            stats = active_tracker.get_current_stats()
            msg = format_report_message(stats, stats["participants"], is_active=True)
            await safe_reply(event, msg, parse_mode="markdown")
            return

        # If not in active stream or run in DM, check if there are active streams anywhere
        active_all = tracker_manager.get_all_active()
        if event.is_private and active_all:
            # Show summary of all live streams
            for act in active_all:
                stats = act.get_current_stats()
                msg = format_report_message(stats, stats["participants"], is_active=True)
                await safe_reply(event, msg, parse_mode="markdown")
            return

        # Otherwise fetch latest completed stream from DB for this group or globally
        target_filter = None if event.is_private else chat_id_str
        stream_meta, participants = db.get_latest_stream(chat_id=target_filter)
        if stream_meta and participants:
            msg = format_report_message(stream_meta, participants, is_active=False)
            await safe_reply(event, msg, parse_mode="markdown")
        else:
            await safe_reply(event, "⚠️ No stream records found in database yet.", parse_mode="markdown")

    # 3. LIVE STATUS COMMAND
    elif cmd in ["/livestatus", "/status"]:
        tracked_db = db.get_tracked_groups()
        active_all = tracker_manager.get_all_active()

        if active_all:
            msg = f"🔴 **{len(active_all)} Live Stream(s) Currently ACTIVE**\n\n"
            for act in active_all:
                stats = act.get_current_stats()
                online_count = sum(1 for p in stats["participants"] if p["is_online"])
                msg += f"📍 **{act.chat_title}**\n"
                msg += f"   ⏱ Elapsed: `{stats['total_min']:.1f} mins`\n"
                msg += f"   👥 Online now: `{online_count}` callers (Total: `{len(stats['participants'])}`)\n\n"
            msg += "Type `/stats` for the live leaderboard."
            await safe_reply(event, msg, parse_mode="markdown")
        else:
            group_count = len(tracked_db)
            prev_stream, participants = db.get_latest_stream()
            prev_info = f"\n_Last stream ({prev_stream.get('chat_title', '')}) had {len(participants)} callers._" if prev_stream and participants else ""
            await safe_reply(
                event,
                f"⚪️ **No live streams are currently active** across {group_count} tracked group(s).{prev_info}\n\n"
                f"Type `/stats` or `/export` to view the last recorded attendance report.",
                parse_mode="markdown"
            )

    # 4. EXPORT SPREADSHEET COMMAND
    elif cmd in ["/export", "/csv"]:
        chat_id_str = str(event.chat_id)
        active_tracker = tracker_manager.get_tracker_for_chat(chat_id_str)
        
        if active_tracker:
            csv_path = active_tracker.generate_csv()
            if csv_path and os.path.exists(csv_path):
                await safe_reply(event, f"📄 In-progress participation CSV export for **{active_tracker.chat_title}**.", file=csv_path)
            else:
                await safe_reply(event, "⚠️ No participant data to export yet.")
            return

        # Check latest completed stream
        target_filter = None if event.is_private else chat_id_str
        stream_meta, participants = db.get_latest_stream(chat_id=target_filter)
        if stream_meta and stream_meta.get("csv_path") and os.path.exists(stream_meta["csv_path"]):
            chat_title = stream_meta.get("chat_title", "Stream")
            await safe_reply(event, f"📄 Latest completed stream CSV report for **{chat_title}**.", file=stream_meta["csv_path"])
        elif participants:
            filename = f"report_latest.csv"
            filepath = os.path.join(CSV_OUTPUT_DIR, filename)
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Rank", "User ID", "Name", "Username", "First Join (UTC)", "Last Leave (UTC)", "Session Count", "Total Duration (Minutes)", "Participation (%)"])
                for rank, p in enumerate(participants, 1):
                    writer.writerow([rank, p["user_id"], p["name"], p["username"], p["first_join"], p["last_leave"], p["session_count"], f"{p['total_min']:.2f}", f"{p['pct']:.2f}"])
            await safe_reply(event, "📄 Latest stream CSV report.", file=filepath)
        else:
            await safe_reply(event, "⚠️ No stream reports found in history.", parse_mode="markdown")

    # 5. ADMIN ROUTING COMMANDS
    elif cmd in ["/admins", "/adminlist"]:
        db_admins = db.get_admin_recipients()
        if not db_admins and ADMIN_CHAT_ID:
            db_admins = [x.strip() for x in str(ADMIN_CHAT_ID).split(",") if x.strip()]

        if db_admins:
            msg = "👑 **Configured Admin Recipients** (Receiving Post-Stream Reports):\n\n"
            for idx, a in enumerate(db_admins, 1):
                msg += f"`#{idx}` {a}\n"
            msg += "\n_Use `/addadmin @username` or `/removeadmin @username` to manage._"
            await safe_reply(event, msg, parse_mode="markdown")
        else:
            await safe_reply(event, "⚠️ No specific admin recipients configured. Set via `/addadmin @username`.", parse_mode="markdown")

    elif cmd in ["/addadmin", "/setadmin"]:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await safe_reply(event, "ℹ️ **Usage**: `/addadmin @username` or `/addadmin <UserID>`\nExample: `/addadmin @KingmattMO`", parse_mode="markdown")
        else:
            new_target = parts[1].strip()
            added_list = []
            for t in new_target.split(","):
                t = t.strip()
                if t:
                    if not t.startswith("@") and not t.isdigit() and not (t.startswith("-") and t[1:].isdigit()):
                        t = f"@{t}"
                    if db.add_admin_recipient(t, added_by=str(event.chat_id)):
                        added_list.append(t)

            all_admins = db.get_admin_recipients()
            await safe_reply(
                event,
                f"✅ **Admin Recipient Added**: {', '.join(added_list)}\n\n"
                f"📋 **Current Report Recipients** ({len(all_admins)}):\n" +
                "\n".join([f"• `{a}`" for a in all_admins]) +
                "\n\n_Note: Ensure the added admin sends `/start` to @KHkronosbot so Telegram allows private DMs._",
                parse_mode="markdown"
            )

    elif cmd in ["/removeadmin", "/deladmin"]:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await safe_reply(event, "ℹ️ **Usage**: `/removeadmin @username`\nExample: `/removeadmin @username`", parse_mode="markdown")
        else:
            target_to_remove = parts[1].strip()
            removed = db.remove_admin_recipient(target_to_remove)
            if not removed and not target_to_remove.startswith("@"):
                removed = db.remove_admin_recipient(f"@{target_to_remove}")

            all_admins = db.get_admin_recipients()
            if removed:
                await safe_reply(
                    event,
                    f"🗑 **Removed**: `{target_to_remove}`\n\n"
                    f"📋 **Remaining Report Recipients** ({len(all_admins)}):\n" +
                    ("\n".join([f"• `{a}`" for a in all_admins]) if all_admins else "_None (will use default config)_"),
                    parse_mode="markdown"
                )
            else:
                await safe_reply(event, f"⚠️ `{target_to_remove}` was not found in the admin list.\nType `/admins` to view the list.", parse_mode="markdown")

    # 6. HELP & START COMMAND
    elif cmd in ["/help", "/start"]:
        help_text = (
            "🤖 **Telegram Live Stream Tracker Bot (Multi-Group Ready)**\n\n"
            "**📊 Stream Reports & Live Stats:**\n"
            "• `/stats` or `/report` - Show latest participant leaderboard & participation %\n"
            "• `/livestatus` - Check live voice chat status across all tracked groups\n"
            "• `/export` or `/csv` - Download the CSV participation spreadsheet\n\n"
            "**👥 Group Tracking Management:**\n"
            "• `/groups` - View all currently tracked groups and their live status\n"
            "• `/trackhere` - (In group) Start tracking this group immediately\n"
            "• `/addgroup @group` - Add a group/channel by username or ID\n"
            "• `/removegroup @group` - Remove a group from tracking\n\n"
            "**👑 Admin Routing Options:**\n"
            "• `/admins` - View list of admins receiving auto-reports\n"
            "• `/addadmin @username` - Add an admin to receive reports in DM\n"
            "• `/removeadmin @username` - Remove an admin from reports\n"
            "• `/help` - Show this menu"
        )
        await safe_reply(event, help_text, parse_mode="markdown")

# --- USER CLIENT LIVE CALL POLLING & EVENTS ---
@user_client.on(events.Raw)
async def raw_event_handler(event):
    if isinstance(event, types.UpdateGroupCallParticipants):
        call_obj = getattr(event, "call", None)
        call_id = getattr(call_obj, "id", None)
        tracker = tracker_manager.get_tracker_for_call(call_id)
        if not tracker:
            return

        for p in event.participants:
            peer = p.peer
            pid, name, username = await resolve_peer_info(user_client, peer)
            if not pid:
                continue

            if getattr(p, "left", False):
                tracker.register_leave(pid)
            else:
                tracker.register_join(pid, name, username)

    elif isinstance(event, types.UpdateGroupCall):
        call_obj = getattr(event, "call", None)
        call_id = getattr(call_obj, "id", None)
        tracker = tracker_manager.get_tracker_for_call(call_id)
        
        if tracker:
            is_discarded = isinstance(call_obj, types.GroupCallDiscarded) or getattr(call_obj, "discarded", False)
            if is_discarded:
                print(f"\n[Raw Event] Received GroupCallDiscarded for active call ID {call_id} ({tracker.chat_title}).")
                group_eid = tracker.chat_id
                chat_title = tracker.chat_title
                matched_info = tracked_entities.get(group_eid)
                group_entity = matched_info.get("entity") if matched_info else None

                ended_stream_id, csv_file = tracker_manager.end_call_by_id(call_id)
                if ended_stream_id and AUTO_POST_REPORT:
                    asyncio.create_task(send_auto_report(csv_file, expected_stream_id=ended_stream_id, group_entity=group_entity, chat_title=chat_title))

async def background_poll_loop():
    POLL_MISS_THRESHOLD = 3  # Require 3 consecutive empty polls (~24s) before declaring call ended

    while True:
        try:
            current_tracked = list(tracked_entities.values())
            if not current_tracked:
                await asyncio.sleep(8)
                continue

            for item in current_tracked:
                entity = item["entity"]
                chat_title = item["title"]
                chat_id_str = item["entity_id"]

                try:
                    if isinstance(entity, (types.Channel, types.InputChannel, types.InputPeerChannel)):
                        full_chat_res = await user_client(functions.channels.GetFullChannelRequest(channel=entity))
                        group_call = full_chat_res.full_chat.call
                    else:
                        full_chat_res = await user_client(functions.messages.GetFullChatRequest(chat_id=entity.id))
                        group_call = full_chat_res.full_chat.call

                    active_tracker = tracker_manager.get_tracker_for_chat(chat_id_str)

                    if group_call:
                        call_id = getattr(group_call, "id", None)
                        if not active_tracker or active_tracker.active_call_id != call_id:
                            active_tracker = tracker_manager.start_call(group_call, chat_title, chat_id_str)

                        active_tracker.consecutive_empty_polls = 0
                        active_uids = set()
                        user_dict = {}
                        chat_dict = {}

                        offset = ""
                        all_participants = []
                        while True:
                            participants_res = await user_client(functions.phone.GetGroupParticipantsRequest(
                                call=group_call,
                                ids=[],
                                sources=[],
                                offset=offset,
                                limit=200
                            ))
                            
                            parts = getattr(participants_res, "participants", [])
                            all_participants.extend(parts)
                            for u in getattr(participants_res, "users", []):
                                user_dict[u.id] = u
                            for c in getattr(participants_res, "chats", []):
                                chat_dict[c.id] = c

                            offset = getattr(participants_res, "next_offset", "")
                            if not offset or not parts:
                                break

                        for p in all_participants:
                            if getattr(p, "left", False):
                                continue
                            peer = p.peer
                            pid, name, username = await resolve_peer_info(user_client, peer)
                            if pid:
                                active_uids.add(pid)
                                if pid in user_dict:
                                    u = user_dict[pid]
                                    first = getattr(u, "first_name", "") or ""
                                    last = getattr(u, "last_name", "") or ""
                                    fname = f"{first} {last}".strip()
                                    if fname:
                                        name = fname
                                    if getattr(u, "username", ""):
                                        username = u.username
                                elif pid in chat_dict:
                                    c = chat_dict[pid]
                                    if getattr(c, "title", ""):
                                        name = c.title
                                    if getattr(c, "username", ""):
                                        username = c.username

                                active_tracker.register_join(pid, name, username)

                        for uid in list(active_tracker.participants.keys()):
                            if uid not in active_uids and active_tracker.participants[uid]["current_join"] is not None:
                                active_tracker.register_leave(uid)

                    else:
                        if active_tracker:
                            active_tracker.consecutive_empty_polls += 1
                            if active_tracker.consecutive_empty_polls >= POLL_MISS_THRESHOLD:
                                print(f"\n[Polling Notice] Confirmed call ended for [{chat_title}] ({active_tracker.consecutive_empty_polls}/{POLL_MISS_THRESHOLD} checks). Finalizing stream...")
                                call_id = active_tracker.active_call_id
                                ended_stream_id, csv_file = tracker_manager.end_call_by_id(call_id)
                                if ended_stream_id and AUTO_POST_REPORT:
                                    asyncio.create_task(send_auto_report(csv_file, expected_stream_id=ended_stream_id, group_entity=entity, chat_title=chat_title))
                            else:
                                print(f"[Polling Notice] Call not detected in full chat info for [{chat_title}] ({active_tracker.consecutive_empty_polls}/{POLL_MISS_THRESHOLD} checks). Verifying before ending...")

                except Exception as pe:
                    # Individual chat poll error (e.g. temporary network or permission)
                    pass

        except Exception as e:
            print(f"[Polling Notice] {type(e).__name__}: {e}")

        await asyncio.sleep(8)

async def try_start_bot():
    global bot_active
    try:
        if not bot_client.is_connected():
            await bot_client.start(bot_token=BOT_TOKEN)
        bot_me = await bot_client.get_me()
        bot_active = True
        print(f"[UI Bot Online]  : @{bot_me.username} ({bot_me.first_name})")
    except errors.FloodWaitError as e:
        print(f"[Bot Cooldown]   : Telegram rate-limit for new bot login ({e.seconds}s). Running stream monitor in the meantime...")
        bot_active = False
        try:
            if bot_client.is_connected():
                await bot_client.disconnect()
        except Exception:
            pass
        asyncio.create_task(bot_retry_after(e.seconds))
    except Exception as e:
        print(f"[Bot Notice]     : {e}. Scheduling bot auto-retry in 15s...")
        bot_active = False
        try:
            if bot_client.is_connected():
                await bot_client.disconnect()
        except Exception:
            pass
        asyncio.create_task(bot_retry_after(15))

async def bot_retry_after(seconds):
    global bot_active
    try:
        await asyncio.sleep(seconds + 5)
        while not bot_active:
            try:
                if not bot_client.is_connected():
                    await bot_client.start(bot_token=BOT_TOKEN)
                bot_me = await bot_client.get_me()
                bot_active = True
                print(f"\n[UI Bot Activated] : @{bot_me.username} is now online in Telegram!")
                break
            except errors.FloodWaitError as fe:
                print(f"[Bot Cooldown Extended] Waiting {fe.seconds}s...")
                await asyncio.sleep(fe.seconds + 5)
            except Exception as be:
                print(f"[Bot Retry Wait] {be}. Retrying in 15s...")
                await asyncio.sleep(15)
    except Exception as e:
        print(f"[Bot Retry Notice] {e}")

async def main():
    print("=" * 60)
    print("Starting Telegram Live Stream Participant Tracker (Multi-Group)...")
    print("=" * 60)

    print("[Stream Monitor] : Connecting User Account to monitor voice/video streams...")
    while True:
        try:
            if not user_client.is_connected():
                await user_client.connect()
                if not await user_client.is_user_authorized():
                    if not sys.stdin or not sys.stdin.isatty():
                        print("\n" + "=" * 60)
                        print("[CRITICAL ERROR] Telegram User Account is NOT authorized!")
                        print("On Koyeb / Railway / Render, you must set the 'SESSION_B64' environment variable.")
                        print("Generate it on your PC by running: python export_session.py")
                        print("=" * 60 + "\n")
                        await asyncio.sleep(60)
                        continue
                    else:
                        await user_client.start()
            user_me = await user_client.get_me()
            if not user_me:
                if not sys.stdin or not sys.stdin.isatty():
                    print("\n" + "=" * 60)
                    print("[CRITICAL NOTICE] User session is not authorized.")
                    print("Please ensure 'SESSION_STRING' is set in your Railway / Koyeb variables.")
                    print("=" * 60 + "\n")
                    await asyncio.sleep(15)
                    continue
                else:
                    await user_client.start()
                    user_me = await user_client.get_me()

            first_name = getattr(user_me, "first_name", "") or getattr(user_me, "title", "User")
            uname = getattr(user_me, "username", "") or "NoUsername"
            print(f"[Stream Monitor] : Connected as {first_name} (@{uname})")
            break
        except Exception as e:
            print(f"[User Client Connect Retry] {e}. Retrying in 5s...")
            await asyncio.sleep(5)

    await try_start_bot()

    # Load and seed target groups from Config / ENV
    config_targets = [t.strip() for t in str(TARGET_CHAT_ENV).split(",") if t.strip()]
    for t in config_targets:
        db.add_tracked_group(t, added_by="Config")

    # Load all tracked groups from Database
    db_groups = db.get_tracked_groups()
    print(f"\nResolving {len(db_groups)} tracked target group(s)...")
    for g in db_groups:
        target = g.get("target") or g.get("entity_id")
        if target:
            await resolve_and_add_target(target, added_by=g.get("added_by", "Database"))

    print(f"\n[READY] Participant tracking active for {len(tracked_entities)} group(s)!")
    for eid, info in tracked_entities.items():
        print(f"  • {info['title']} ({info['target']})")
    print("  Auto-generates attendance CSV reports on stream end.")
    print("  Permanently persists all sessions to SQLite database.\n")

    poll_task = asyncio.create_task(background_poll_loop())

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:
        print(f"[Notice] Main loop interrupted ({type(e).__name__}: {e})")
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            if user_client.is_connected():
                await user_client.disconnect()
        except Exception:
            pass
        try:
            if bot_client.is_connected():
                await bot_client.disconnect()
        except Exception:
            pass

async def supervisor():
    try:
        loop = asyncio.get_running_loop()
        def handle_async_exception(loop, context):
            msg = context.get("exception", context.get("message"))
            print(f"[Network/AsyncIO Notice] {msg}")
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] AsyncIO Exception: {context}\n")
        loop.set_exception_handler(handle_async_exception)
    except Exception:
        pass

    while True:
        try:
            await main()
        except (KeyboardInterrupt, SystemExit):
            print("\nTracker stopped by user.")
            for active_tracker in tracker_manager.get_all_active():
                active_tracker.end_call()
            break
        except BaseException as e:
            err_msg = f"[{datetime.datetime.now()}] Supervisor caught: {type(e).__name__}: {e}\n"
            print(f"[Auto-Recover] {err_msg.strip()}. Reconnecting in 5s...")
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(err_msg)
                import traceback
                traceback.print_exc(file=f)
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(supervisor())
    except (KeyboardInterrupt, SystemExit):
        pass
    except BaseException as e:
        with open("crash.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] Top-level crash: {e}\n")
            import traceback
            traceback.print_exc(file=f)
