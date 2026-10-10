import sqlite3
import datetime
import csv
import db

db.init_db()

csv_path = "reports/livestream_attendance_report.csv"
stream_id = "stream_20260814_201200_-5734923756965228090"
start_time = "2026-08-14T20:12:00"
end_time = "2026-08-14T20:20:00"
call_id = "-5734923756965228090"
chat_title = "CHURCH IS HERE |||| KINGS' HUB BC"

with db.get_connection() as conn:
    c = conn.cursor()

    c.execute("UPDATE streams SET is_active = 0")
    c.execute("""
    INSERT OR REPLACE INTO streams (stream_id, call_id, chat_title, start_time, end_time, duration_sec, total_participants, csv_path, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (stream_id, call_id, chat_title, start_time, end_time, 480.0, 29, csv_path))

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c.execute("""
            INSERT OR REPLACE INTO participants (stream_id, user_id, name, username, first_join, last_leave, session_count, total_sec, total_min, pct, is_online)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                stream_id,
                int(row["User ID"]),
                row["Name"],
                row["Username"],
                row["First Join (UTC)"],
                row["Last Leave (UTC)"],
                int(row["Session Count"]),
                float(row["Total Duration (Minutes)"]) * 60.0,
                float(row["Total Duration (Minutes)"]),
                float(row["Participation (%)"]),
            ))

print("Saved stream data to tracker.db successfully!")
