import sqlite3
import datetime
import os

DB_PATH = os.getenv("DB_PATH", "tracker.db")

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

def get_admin_recipients():
    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute("SELECT target, name, added_by FROM admin_recipients ORDER BY id ASC")
            return [dict(row) for row in c.fetchall()]
        except Exception:
            c.execute("SELECT target FROM admin_recipients ORDER BY id ASC")
            return [{"target": row["target"], "name": "", "added_by": ""} for row in c.fetchall()]

def add_admin_recipient(target, name="", added_by="Owner"):
    target = str(target).strip()
    if not target:
        return False
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
            return True
        except Exception as e:
            try:
                c.execute("INSERT OR IGNORE INTO admin_recipients (target, added_by, added_at) VALUES (?, ?, ?)", (target, str(added_by), now_str))
                return True
            except Exception:
                return False

def remove_admin_recipient(target):
    target = target.strip()
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admin_recipients WHERE LOWER(target) = LOWER(?) OR target = ?", (target, target))
        return c.rowcount > 0

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
    with get_connection() as conn:
        c = conn.cursor()
        if chat_id is not None and str(chat_id).strip():
            cid_str = str(chat_id).strip()
            # Try to match numeric ID (accounting for potential -100 prefix differences), username, or title
            clean_id = cid_str.replace("-100", "").replace("-", "")
            c.execute("""
            SELECT * FROM streams 
            WHERE chat_id = ? 
               OR chat_id = ? 
               OR chat_id LIKE ? 
               OR chat_title LIKE ? 
            ORDER BY rowid DESC LIMIT 1
            """, (cid_str, f"-100{clean_id}", f"%{clean_id}%", f"%{cid_str}%"))
            stream = c.fetchone()
        else:
            stream = None

        if not stream:
            c.execute("SELECT * FROM streams ORDER BY rowid DESC LIMIT 1")
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

def get_stream_history(limit=5, chat_id=None):
    with get_connection() as conn:
        c = conn.cursor()
        if chat_id is not None and str(chat_id).strip():
            cid_str = str(chat_id).strip()
            clean_id = cid_str.replace("-100", "").replace("-", "")
            c.execute("""
            SELECT * FROM streams 
            WHERE is_active = 0 AND (chat_id = ? OR chat_id LIKE ? OR chat_title LIKE ?)
            ORDER BY rowid DESC LIMIT ?
            """, (cid_str, f"%{clean_id}%", f"%{cid_str}%", limit))
        else:
            c.execute("SELECT * FROM streams WHERE is_active = 0 ORDER BY rowid DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        return [dict(r) for r in rows]
