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
        
        # Also auto-update local .env if present
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                lines = f.readlines()
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith("SESSION_STRING="):
                    lines[i] = f"SESSION_STRING={string_val}\n"
                    updated = True
                    break
            if not updated:
                lines.append(f"\nSESSION_STRING={string_val}\n")
            with open(".env", "w", encoding="utf-8") as f:
                f.writelines(lines)
            print("✅ Auto-updated 'SESSION_STRING' in your local .env file.")

        print("\n" + "=" * 60)
        print("✅ NEW SESSION STRING GENERATED AND SAVED TO 'session_string.txt'")
        print("=" * 60)
        print("NEXT STEP FOR RAILWAY:")
        print("1. Go to your Railway Project -> Service -> Variables")
        print("2. Set 'SESSION_STRING' to the new value from 'session_string.txt'")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"[Export Notice] Run 'python export_session.py' to generate session string: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
