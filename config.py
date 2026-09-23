import os

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Telegram API Credentials (Get from https://my.telegram.org)
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")

# Telegram Bot Token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Target Channel or Group (Username or ID)
TARGET_CHAT = os.getenv("TARGET_CHAT", "@YourGroupOrChannel")

# In-Telegram Features:
# Automatically post reports when a call ends
AUTO_POST_REPORT = os.getenv("AUTO_POST_REPORT", "True").lower() in ("true", "1", "yes")

# Admin Chat / User ID to receive the reports privately (e.g. '@KingmattMO' or '1067204907' or comma-separated)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "@KingmattMO")

# Whether to also post the reports to the public group (Default: False)
AUTO_POST_TO_GROUP = os.getenv("AUTO_POST_TO_GROUP", "False").lower() in ("true", "1", "yes")

# Legacy compatibility
AUTO_POST_REPORT_TO_CHAT = AUTO_POST_REPORT

# Minimum attendance threshold (in seconds) to be counted as a genuine attendee (Default: 30s)
MIN_ATTENDANCE_SECONDS = int(os.getenv("MIN_ATTENDANCE_SECONDS", 30))

# Whether to completely exclude brief previewers (< MIN_ATTENDANCE_SECONDS) from CSV exports (Default: False)
EXCLUDE_PREVIEWS_FROM_CSV = os.getenv("EXCLUDE_PREVIEWS_FROM_CSV", "False").lower() in ("true", "1", "yes")

# Reports directory on disk
EXPORT_CSV = True
CSV_OUTPUT_DIR = os.getenv("CSV_OUTPUT_DIR", "reports")
