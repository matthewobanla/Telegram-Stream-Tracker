import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession, SQLiteSession
import config

SESSION_FILE = "tracker_session.session"

async def main():
    print("=" * 60)
    print("Telegram User Account Authentication (One-Time Setup)")
    print("=" * 60)
    print("This links your Telegram account so the tracker can monitor")
    print("group voice/video streams and fetch all participants.\n")

    # If an old session file exists, clean it up to avoid AuthKeyDuplicatedError
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
            print("[Clean Setup] Removed old session cache.")
        except Exception:
            pass

    client = TelegramClient("tracker_session", config.API_ID, config.API_HASH)
    await client.start()

    me = await client.get_me()
    uname = f"@{me.username}" if getattr(me, "username", "") else "NoUsername"
    print(f"\n[SUCCESS] Logged in as: {me.first_name} ({uname})")

    # Export StringSession automatically
    try:
        sqlite_sess = SQLiteSession("tracker_session")
        string_val = StringSession.save(sqlite_sess)
        sqlite_sess.close()
        with open("session_string.txt", "w", encoding="utf-8") as f:
            f.write(string_val)
        print("\n" + "=" * 60)
        print("✅ NEW SESSION STRING GENERATED AND SAVED TO 'session_string.txt'")
        print("=" * 60)
        print("Copy the text from 'session_string.txt' and update 'SESSION_STRING' on Railway.")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"[Export Notice] Run 'python export_session.py' to generate session string: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
