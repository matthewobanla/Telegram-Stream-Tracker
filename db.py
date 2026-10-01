import sqlite3
import datetime
import os
import csv
import re
import json

DB_PATH = os.getenv("DB_PATH", "tracker.db")
ADMINS_JSON_FILE = os.getenv("ADMINS_JSON_FILE", "admins.json")

SEED_STREAM_ID = "stream_20260814_201200_-5734923756965228090"
SEED_PARTICIPANTS = [
    (1067204907, "Matthew Ọbańlá", "KingmattMO", "20:12:00", "20:20:00", 1, 480.0, 8.00, 100.00),
    (1187478939, "Esther Olajide", "toluwa_nisola", "20:12:00", "20:20:00", 1, 480.0, 8.00, 100.00),
    (1633978817, "Sis Damilola Oladipupo", "", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (1568346316, "Bro Arthur Ogodo", "", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (5021886681, "Adekunle Philip KH", "philipecclesia", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (6154808428, "Bro dare", "Daiveedladray", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (1623337363, "Titilayo Rosiji", "titilee82", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (1055188344, "Bro Isaac Oladipupo", "Olaking1", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (1198580304, "Sis Esther Olusola", "", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (5736853479, "Sis Chinwendu KH", "", "20:12:01", "20:20:00", 1, 478.8, 7.98, 99.79),
    (1768740489, "Sis Adejoke Kings Hub", "", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (8452374462, "Bro Daniel Emblem", "", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (1902811470, "Modupe Lawal", "Oluwaseun_modupe", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (2050735724, "Sis Bright KH", "Bright633", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (8579726991, "Favour", "", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (5450495252, "Sister Titilayo Oladipupo", "Teelahyor5", "20:12:02", "20:20:00", 1, 478.2, 7.97, 99.58),
    (1733858222, "Sis Adeola Adeoye", "", "20:12:03", "20:20:00", 1, 477.0, 7.95, 99.38),
    (1192562832, "Dotun Collins", "", "20:12:23", "20:20:00", 1, 457.2, 7.62, 95.21),
    (549053856, "Leye Rosiji", "OlaleyeR", "20:13:01", "20:20:00", 1, 418.8, 6.98, 87.29),
    (5198092341, "Damilola Kingshub", "Mo_rireoluwa", "20:13:19", "20:20:00", 1, 400.8, 6.68, 83.54),
    (6374190576, "Sis Blessing Kings Hub", "Blessingore", "20:12:03", "20:20:00", 3, 379.8, 6.33, 79.17),
    (5330295657, "Oshilaja Titilayo KH", "", "20:12:08", "20:20:00", 3, 328.8, 5.48, 68.54),
    (6169690410, "Sis BEKKY KINGS HUB", "beckyz_Artistry", "20:12:02", "20:14:30", 3, 145.2, 2.42, 30.21),
    (5842104960, "Sis Joy Igele", "", "20:12:02", "20:13:10", 3, 37.2, 0.62, 7.71),
    (1070491258, "Sia Funke KH", "Beezalel", "20:13:57", "20:14:05", 1, 7.8, 0.13, 1.67),
    (1074618195, "Bro Bukunmi KH", "adebarigold", "20:13:57", "20:14:05", 1, 7.8, 0.13, 1.67),
    (2020680914, "TALKINGWILLY", "talkingwilly", "20:13:35", "20:13:40", 1, 4.8, 0.08, 1.04),
    (7373745365, "Akanbi Folakemi", "", "20:13:00", "20:13:02", 1, 1.8, 0.03, 0.42),
    (655988041, "Emmanuel", "", "20:14:28", "20:14:30", 1, 1.8, 0.03, 0.42)
]

def seed_initial_stream(cursor):
    cursor.execute("""
    INSERT OR REPLACE INTO streams (stream_id, call_id, chat_title, start_time, end_time, duration_sec, total_participants, csv_path, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (SEED_STREAM_ID, "-5734923756965228090", "CHURCH IS HERE |||| KINGS' HUB BC", "2026-08-14T20:12:00", "2026-08-14T20:20:00", 480.0, 29, "reports/livestream_attendance_report.csv"))

    for uid, name, uname, fjoin, lleave, scount, tsec, tmin, pct in SEED_PARTICIPANTS:
        cursor.execute("""
        INSERT OR REPLACE INTO participants (stream_id, user_id, name, username, first_join, last_leave, session_count, total_sec, total_min, pct, is_online)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (SEED_STREAM_ID, uid, name, uname, fjoin, lleave, scount, tsec, tmin, pct))

def get_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS streams (
            stream_id TEXT PRIMARY KEY,
            call_id TEXT,
            chat_title TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_sec REAL DEFAULT 0,
            total_participants INTEGER DEFAULT 0,
            csv_path TEXT,
            is_active INTEGER DEFAULT 1
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            stream_id TEXT,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            first_join TEXT,
            last_leave TEXT,
            session_count INTEGER DEFAULT 1,
            total_sec REAL DEFAULT 0,
            total_min REAL DEFAULT 0,
            pct REAL DEFAULT 0,
            is_online INTEGER DEFAULT 1,
            PRIMARY KEY (stream_id, user_id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id TEXT,
            user_id INTEGER,
            join_time TEXT,
            leave_time TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS admin_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT UNIQUE,
            added_by TEXT,
            added_at TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS tracked_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT UNIQUE,
            title TEXT,
            entity_id TEXT,
            added_by TEXT,
            added_at TEXT,
            is_active INTEGER DEFAULT 1
        )
        """)

        try:
            c.execute("ALTER TABLE streams ADD COLUMN chat_id TEXT")
        except Exception:
            pass

        c.execute("SELECT COUNT(*) FROM streams")
        if c.fetchone()[0] == 0:
            seed_initial_stream(c)

    try:
        sync_all_csv_reports_to_db()
    except Exception:
        pass

def get_tracked_groups():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM tracked_groups WHERE is_active = 1 ORDER BY id ASC")
        return [dict(row) for row in c.fetchall()]

def add_tracked_group(target, title="", entity_id="", added_by="Owner"):
    target = str(target).strip()
    if not target:
        return False
    with get_connection() as conn:
        c = conn.cursor()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            c.execute("""
            INSERT INTO tracked_groups (target, title, entity_id, added_by, added_at, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(target) DO UPDATE SET 
                title = CASE WHEN excluded.title != '' THEN excluded.title ELSE tracked_groups.title END,
                entity_id = CASE WHEN excluded.entity_id != '' THEN excluded.entity_id ELSE tracked_groups.entity_id END,
                is_active = 1
            """, (target, title, str(entity_id) if entity_id else "", str(added_by), now_str))
            return True
        except Exception as e:
            print(f"[DB Add Group Error] {e}")
            return False

def remove_tracked_group(target):
    target = str(target).strip()
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tracked_groups WHERE LOWER(target) = LOWER(?) OR target = ? OR entity_id = ?", (target, target, str(target)))
        return c.rowcount > 0

def update_tracked_group_info(target, title, entity_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE tracked_groups SET title = ?, entity_id = ? WHERE target = ? OR entity_id = ?", (title, str(entity_id), str(target), str(entity_id)))

def _save_admins_to_json():
    try:
        with get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute("SELECT target, name, added_by FROM admin_recipients ORDER BY id ASC")
                admins = [dict(row) for row in c.fetchall()]
            except Exception:
                admins = []
        if admins:
            with open(ADMINS_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(admins, f, indent=2)
    except Exception:
        pass

def _sync_admins_from_json():
    if not os.path.exists(ADMINS_JSON_FILE):
        return
    try:
        with open(ADMINS_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        target = item.get("target")
                        name = item.get("name", "")
                        added_by = item.get("added_by", "JSON Backup")
                        if target:
                            add_admin_recipient(target, name=name, added_by=added_by, skip_json_write=True)
    except Exception:
        pass

def get_admin_recipients():
    try:
        _sync_admins_from_json()
    except Exception:
        pass

    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute("SELECT target, name, added_by FROM admin_recipients ORDER BY id ASC")
            return [dict(row) for row in c.fetchall()]
        except Exception:
            c.execute("SELECT target FROM admin_recipients ORDER BY id ASC")
            return [{"target": row["target"], "name": "", "added_by": ""} for row in c.fetchall()]

def add_admin_recipient(target, name="", added_by="Owner", skip_json_write=False):
    target = str(target).strip()
    if not target:
        return False
    if not target.startswith("@") and not target.isdigit() and not (target.startswith("-") and target[1:].isdigit()):
        target = f"@{target}"
    success = False
    with get_connection() as conn:
        c = conn.cursor()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            c.execute("ALTER TABLE admin_recipients ADD COLUMN name TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            c.execute("""
            INSERT INTO admin_recipients (target, name, added_by, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(target) DO UPDATE SET 
                name = CASE WHEN excluded.name != '' THEN excluded.name ELSE admin_recipients.name END
            """, (target, str(name), str(added_by), now_str))
            success = True
        except Exception as e:
            try:
                c.execute("INSERT OR IGNORE INTO admin_recipients (target, added_by, added_at) VALUES (?, ?, ?)", (target, str(added_by), now_str))
                success = True
            except Exception:
                success = False

    if success and not skip_json_write:
        _save_admins_to_json()
    return success

def remove_admin_recipient(target):
    target = target.strip()
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admin_recipients WHERE LOWER(target) = LOWER(?) OR target = ?", (target, target))
        removed = c.rowcount > 0
    if removed:
        _save_admins_to_json()
    return removed

def save_stream_start(stream_id, call_id, chat_title, start_time_dt, chat_id=""):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE streams SET is_active = 0 WHERE call_id = ? OR (chat_id != '' AND chat_id = ?)", (str(call_id), str(chat_id)))
        c.execute("""
        INSERT OR REPLACE INTO streams (stream_id, call_id, chat_title, chat_id, start_time, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """, (stream_id, str(call_id), chat_title, str(chat_id) if chat_id else "", start_time_dt.isoformat()))

def save_participant_join(stream_id, user_id, name, username, join_time_dt):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM participants WHERE stream_id = ? AND user_id = ?", (stream_id, user_id))
        row = c.fetchone()
        join_str = join_time_dt.isoformat()

        if not row:
            c.execute("""
            INSERT INTO participants (stream_id, user_id, name, username, first_join, is_online, session_count)
            VALUES (?, ?, ?, ?, ?, 1, 1)
            """, (stream_id, user_id, name, username, join_str))
        else:
            curr_name = name if (name and not name.startswith("User ") and not name.startswith("Participant ")) else row["name"]
            curr_uname = username or row["username"]
            sess_count = row["session_count"] + (1 if row["is_online"] == 0 else 0)
            c.execute("""
            UPDATE participants
            SET name = ?, username = ?, is_online = 1, session_count = ?
            WHERE stream_id = ? AND user_id = ?
            """, (curr_name, curr_uname, sess_count, stream_id, user_id))

        c.execute("""
        INSERT INTO sessions (stream_id, user_id, join_time)
        VALUES (?, ?, ?)
        """, (stream_id, user_id, join_str))

def save_participant_leave(stream_id, user_id, leave_time_dt):
    with get_connection() as conn:
        c = conn.cursor()
        leave_str = leave_time_dt.isoformat()

        c.execute("""
        SELECT id, join_time FROM sessions
        WHERE stream_id = ? AND user_id = ? AND leave_time IS NULL
        ORDER BY id DESC LIMIT 1
        """, (stream_id, user_id))
        sess = c.fetchone()

        added_sec = 0.0
        if sess:
            join_dt = datetime.datetime.fromisoformat(sess["join_time"])
            added_sec = max(0.0, (leave_time_dt - join_dt).total_seconds())
            c.execute("UPDATE sessions SET leave_time = ? WHERE id = ?", (leave_str, sess["id"]))

        c.execute("SELECT total_sec FROM participants WHERE stream_id = ? AND user_id = ?", (stream_id, user_id))
        p = c.fetchone()
        if p:
            new_total_sec = p["total_sec"] + added_sec
            new_total_min = new_total_sec / 60.0
            c.execute("""
            UPDATE participants
            SET is_online = 0, last_leave = ?, total_sec = ?, total_min = ?
            WHERE stream_id = ? AND user_id = ?
            """, (leave_str, new_total_sec, new_total_min, stream_id, user_id))

def save_stream_end(stream_id, end_time_dt, csv_path=""):
    with get_connection() as conn:
        c = conn.cursor()
        end_str = end_time_dt.isoformat()

        c.execute("""
        SELECT id, user_id, join_time FROM sessions
        WHERE stream_id = ? AND leave_time IS NULL
        """, (stream_id,))
        open_sessions = c.fetchall()

        for s in open_sessions:
            join_dt = datetime.datetime.fromisoformat(s["join_time"])
            added_sec = max(0.0, (end_time_dt - join_dt).total_seconds())
            c.execute("UPDATE sessions SET leave_time = ? WHERE id = ?", (end_str, s["id"]))
            
            c.execute("SELECT total_sec FROM participants WHERE stream_id = ? AND user_id = ?", (stream_id, s["user_id"]))
            p = c.fetchone()
            if p:
                new_sec = p["total_sec"] + added_sec
                c.execute("""
                UPDATE participants
                SET is_online = 0, last_leave = ?, total_sec = ?, total_min = ?
                WHERE stream_id = ? AND user_id = ?
                """, (end_str, new_sec, new_sec / 60.0, stream_id, s["user_id"]))

        c.execute("SELECT start_time FROM streams WHERE stream_id = ?", (stream_id,))
        st = c.fetchone()
        total_stream_sec = 1.0
        if st and st["start_time"]:
            start_dt = datetime.datetime.fromisoformat(st["start_time"])
            total_stream_sec = max(1.0, (end_time_dt - start_dt).total_seconds())

        c.execute("SELECT user_id, total_sec FROM participants WHERE stream_id = ?", (stream_id,))
        all_p = c.fetchall()
        for p in all_p:
            pct = min(100.0, (p["total_sec"] / total_stream_sec) * 100.0)
            c.execute("UPDATE participants SET pct = ? WHERE stream_id = ? AND user_id = ?", (pct, stream_id, p["user_id"]))

        total_count = len(all_p)
        c.execute("""
        UPDATE streams
        SET end_time = ?, duration_sec = ?, total_participants = ?, csv_path = ?, is_active = 0
        WHERE stream_id = ?
        """, (end_str, total_stream_sec, total_count, csv_path, stream_id))

def get_latest_stream(chat_id=None):
    """Retrieves the most recent stream session and its participants, sorted chronologically by start_time."""
    try:
        finalize_dangling_streams()
        sync_all_csv_reports_to_db()
    except Exception:
        pass

    with get_connection() as conn:
        c = conn.cursor()
        stream = None
        if chat_id is not None and str(chat_id).strip():
            cid_str = str(chat_id).strip()
            clean_id = cid_str.replace("-100", "").replace("-", "")
            c.execute("""
            SELECT * FROM streams 
            WHERE (chat_id = ? OR chat_id = ? OR chat_id LIKE ? OR chat_title LIKE ?)
              AND (total_participants > 0 OR duration_sec > 10)
            ORDER BY start_time DESC, rowid DESC LIMIT 1
            """, (cid_str, f"-100{clean_id}", f"%{clean_id}%", f"%{cid_str}%"))
            stream = c.fetchone()

        if not stream:
            c.execute("""
            SELECT * FROM streams 
            WHERE total_participants > 0 OR duration_sec > 10
            ORDER BY start_time DESC, rowid DESC LIMIT 1
            """)
            stream = c.fetchone()

        if not stream:
            c.execute("SELECT * FROM streams ORDER BY start_time DESC, rowid DESC LIMIT 1")
            stream = c.fetchone()

        if not stream:
            return None, []

        c.execute("""
        SELECT * FROM participants
        WHERE stream_id = ?
        ORDER BY total_sec DESC
        """, (stream["stream_id"],))
        participants = c.fetchall()
        return dict(stream), [dict(p) for p in participants]

def sync_all_csv_reports_to_db(reports_dir="reports"):
    """Scans reports folder and imports all historical CSV reports into tracker.db."""
    if not os.path.exists(reports_dir):
        return
    with get_connection() as conn:
        c = conn.cursor()
        for fname in sorted(os.listdir(reports_dir)):
            if not fname.endswith(".csv") or fname.startswith(".") or fname in ("report_latest.csv", "today_report.csv"):
                continue
            filepath = os.path.join(reports_dir, fname)
            
            match = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", fname)
            if match:
                y, m, d, hh, mm, ss = match.groups()
                timestamp_key = f"{y}{m}{d}_{hh}{mm}{ss}"
                stream_id = f"stream_{timestamp_key}"
                start_time_iso = f"{y}-{m}-{d}T{hh}:{mm}:{ss}"
            else:
                mtime = os.path.getmtime(filepath)
                start_time_iso = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
                clean_name = os.path.splitext(fname)[0]
                stream_id = f"stream_{clean_name}"

            c.execute("SELECT COUNT(*) FROM streams WHERE stream_id = ? OR start_time = ? OR csv_path = ?", (stream_id, start_time_iso, filepath))
            if c.fetchone()[0] > 0:
                continue
            
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    reader = list(csv.DictReader(f))
                    if not reader:
                        continue
                    
                    total_participants = len(reader)
                    max_dur_min = 0.0
                    for row in reader:
                        try:
                            d = float(row.get("Total Duration (Minutes)", 0) or 0)
                            if d > max_dur_min:
                                max_dur_min = d
                        except Exception:
                            pass
                    
                    duration_sec = max_dur_min * 60.0 if max_dur_min > 0 else 60.0

                    title_match = re.search(r"report_\d{8}_\d{6}_(.+)\.csv", fname)
                    if title_match:
                        chat_title = title_match.group(1).replace("_", " ").strip()
                    else:
                        chat_title = "CHURCH IS HERE |||| KINGS' HUB BC"
                    
                    chat_id = "4399983308" if "FGC" in chat_title else "1335265990"
                    
                    c.execute("""
                    INSERT OR REPLACE INTO streams (stream_id, call_id, chat_title, chat_id, start_time, end_time, duration_sec, total_participants, csv_path, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (stream_id, stream_id, chat_title, chat_id, start_time_iso, start_time_iso, duration_sec, total_participants, filepath))
                    
                    for row in reader:
                        try:
                            uid = int(row.get("User ID", 0) or 0)
                            if not uid:
                                continue
                            name = row.get("Name", "")
                            uname = row.get("Username", "")
                            fjoin = row.get("First Join (UTC)", "")
                            lleave = row.get("Last Leave (UTC)", "")
                            scount = int(row.get("Session Count", 1) or 1)
                            tmin = float(row.get("Total Duration (Minutes)", 0) or 0)
                            pct = float(row.get("Participation (%)", 0) or 0)
                            
                            c.execute("""
                            INSERT OR REPLACE INTO participants (stream_id, user_id, name, username, first_join, last_leave, session_count, total_sec, total_min, pct, is_online)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                            """, (stream_id, uid, name, uname, fjoin, lleave, scount, tmin * 60.0, tmin, pct))
                        except Exception:
                            pass
            except Exception as e:
                print(f"[DB Sync CSV Notice] Failed to sync {fname}: {e}")

def finalize_dangling_streams():
    """Auto-recovers and finalizes any dangling or interrupted active streams in the database."""
    with get_connection() as conn:
        c = conn.cursor()
        dangling = c.execute("SELECT * FROM streams WHERE is_active = 1").fetchall()
        for s in dangling:
            sid = s["stream_id"]
            chat_title = s["chat_title"] or "Voice Stream"
            start_time_str = s["start_time"]
            
            time_info = c.execute("""
                SELECT MIN(join_time), MAX(join_time), MAX(leave_time) 
                FROM sessions WHERE stream_id = ?
            """, (sid,)).fetchone()
            
            max_time = time_info[2] or time_info[1] or start_time_str
            c.execute("UPDATE sessions SET leave_time = ? WHERE stream_id = ? AND leave_time IS NULL", (max_time, sid))
            
            parts = c.execute("SELECT * FROM participants WHERE stream_id = ?", (sid,)).fetchall()
            total_p = len(parts)
            
            if total_p > 0 and start_time_str:
                try:
                    start_dt = datetime.datetime.fromisoformat(start_time_str)
                    end_dt = datetime.datetime.fromisoformat(max_time)
                except Exception:
                    start_dt = datetime.datetime.now(datetime.timezone.utc)
                    end_dt = start_dt + datetime.timedelta(minutes=5)
                
                dur_sec = max(1.0, (end_dt - start_dt).total_seconds())
                
                for p in parts:
                    p_uid = p["user_id"]
                    p_sec = p["total_sec"] or 0.0
                    if p_sec <= 0:
                        p_sessions = c.execute("SELECT join_time, leave_time FROM sessions WHERE stream_id = ? AND user_id = ?", (sid, p_uid)).fetchall()
                        accum_sec = 0.0
                        for ps in p_sessions:
                            try:
                                jt = datetime.datetime.fromisoformat(ps["join_time"])
                                lt = datetime.datetime.fromisoformat(ps["leave_time"] or max_time)
                                accum_sec += max(0.0, (lt - jt).total_seconds())
                            except Exception:
                                pass
                        p_sec = accum_sec if accum_sec > 0 else 60.0
                    
                    pct = min(100.0, (p_sec / dur_sec) * 100.0)
                    c.execute("""
                        UPDATE participants 
                        SET total_sec = ?, total_min = ?, pct = ?, is_online = 0 
                        WHERE stream_id = ? AND user_id = ?
                    """, (p_sec, p_sec / 60.0, pct, sid, p_uid))
                
                os.makedirs("reports", exist_ok=True)
                clean_title = "".join(ch for ch in chat_title if ch.isalnum() or ch in (' ', '_', '-')).strip().replace(" ", "_")
                start_clean = start_time_str[:19].replace(":", "").replace("-", "").replace("T", "_")
                csv_filename = f"report_{start_clean}_{clean_title[:30]}.csv"
                csv_path = os.path.join("reports", csv_filename)
                
                updated_parts = c.execute("SELECT * FROM participants WHERE stream_id = ? ORDER BY total_sec DESC", (sid,)).fetchall()
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Rank", "User ID", "Name", "Username", "First Join (UTC)", "Last Leave (UTC)", "Session Count", "Total Duration (Minutes)", "Participation (%)"])
                    for rank, up in enumerate(updated_parts, 1):
                        writer.writerow([
                            rank,
                            up["user_id"],
                            up["name"],
                            up["username"],
                            up["first_join"],
                            up["last_leave"] or max_time,
                            up["session_count"],
                            f"{up['total_min']:.2f}",
                            f"{up['pct']:.2f}"
                        ])
                
                c.execute("""
                    UPDATE streams 
                    SET end_time = ?, duration_sec = ?, total_participants = ?, csv_path = ?, is_active = 0 
                    WHERE stream_id = ?
                """, (end_dt.isoformat(), dur_sec, total_p, csv_path, sid))
            else:
                c.execute("UPDATE streams SET is_active = 0, duration_sec = 0.0, total_participants = 0 WHERE stream_id = ?", (sid,))

def get_distinct_stream_groups():
    """Returns a list of distinct group titles and chat_ids that have recorded streams."""
    try:
        finalize_dangling_streams()
        sync_all_csv_reports_to_db()
    except Exception:
        pass
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
        SELECT chat_title, COALESCE(chat_id, '') as chat_id, COUNT(*) as stream_count 
        FROM streams 
        WHERE (total_participants > 0 OR duration_sec > 0 OR is_active = 0)
        GROUP BY chat_title, chat_id
        ORDER BY MAX(start_time) DESC
        """)
        return [dict(r) for r in c.fetchall()]

def get_all_streams(chat_id=None):
    """Returns all completed streams with 1-based sequential index numbers (1 = first, N = latest)."""
    try:
        finalize_dangling_streams()
        sync_all_csv_reports_to_db()
    except Exception:
        pass

    with get_connection() as conn:
        c = conn.cursor()
        rows = []
        if chat_id is not None and str(chat_id).strip() and str(chat_id).strip().lower() != "all":
            cid_str = str(chat_id).strip()
            clean_id = cid_str.replace("-100", "").replace("-", "")
            c.execute("""
            SELECT * FROM streams 
            WHERE (is_active = 0 OR end_time IS NOT NULL OR duration_sec > 0 OR total_participants > 0)
              AND (chat_id = ? OR chat_id LIKE ? OR chat_title LIKE ?)
            ORDER BY start_time ASC, rowid ASC
            """, (cid_str, f"%{clean_id}%", f"%{cid_str}%"))
            rows = [dict(r) for r in c.fetchall()]
        else:
            c.execute("""
            SELECT * FROM streams 
            WHERE (is_active = 0 OR end_time IS NOT NULL OR duration_sec > 0 OR total_participants > 0)
            ORDER BY start_time ASC, rowid ASC
            """)
            rows = [dict(r) for r in c.fetchall()]

        for idx, r in enumerate(rows, 1):
            r["index_num"] = idx

        return rows

def get_stream_by_index(index_num, chat_id=None):
    """Fetches a stream by its 1-based sequential index number."""
    all_streams = get_all_streams(chat_id=chat_id)
    target_idx = int(index_num)
    for s in all_streams:
        if s.get("index_num") == target_idx:
            return s
    return None

def get_stream_by_id(stream_id):
    """Fetches a stream and its participants by stream_id."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM streams WHERE stream_id = ?", (stream_id,))
        row = c.fetchone()
        if not row:
            return None, []
        c.execute("SELECT * FROM participants WHERE stream_id = ? ORDER BY total_sec DESC", (stream_id,))
        parts = [dict(p) for p in c.fetchall()]
        return dict(row), parts

def get_or_generate_csv_for_stream(stream_id_or_index, chat_id=None):
    """Returns the filepath to the CSV for a specific stream (by index or stream_id), generating it from DB if missing."""
    stream_meta = None
    participants = []
    
    if str(stream_id_or_index).isdigit():
        stream_meta = get_stream_by_index(int(stream_id_or_index), chat_id=chat_id)
        if stream_meta:
            _, participants = get_stream_by_id(stream_meta["stream_id"])
    else:
        stream_meta, participants = get_stream_by_id(str(stream_id_or_index))

    if not stream_meta:
        return None, None

    csv_path = stream_meta.get("csv_path")
    if csv_path and os.path.exists(csv_path) and os.path.getsize(csv_path) > 30:
        return csv_path, stream_meta

    if not participants:
        _, participants = get_stream_by_id(stream_meta["stream_id"])

    os.makedirs("reports", exist_ok=True)
    safe_title = "".join([c if c.isalnum() else "_" for c in stream_meta.get("chat_title", "stream")])[:20]
    start_clean = str(stream_meta.get("start_time", "session"))[:19].replace(":", "").replace("-", "_").replace("T", "_")
    filename = f"report_{safe_title}_{start_clean}.csv"
    filepath = os.path.join("reports", filename)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "User ID", "Name", "Username", "First Join (UTC)", "Last Leave (UTC)", "Session Count", "Total Duration (Minutes)", "Participation (%)"])
        for rank, p in enumerate(participants, 1):
            writer.writerow([
                rank,
                p.get("user_id", ""),
                p.get("name", ""),
                p.get("username", ""),
                p.get("first_join", ""),
                p.get("last_leave", ""),
                p.get("session_count", 1),
                f"{p.get('total_min', 0.0):.2f}",
                f"{p.get('pct', 0.0):.2f}"
            ])

    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE streams SET csv_path = ? WHERE stream_id = ?", (filepath, stream_meta["stream_id"]))

    return filepath, stream_meta

def get_stream_history(limit=50, chat_id=None):
    all_streams = get_all_streams(chat_id=chat_id)
    # Return newest streams first
    rev = list(reversed(all_streams))
    if limit:
        return rev[:limit]
    return rev
