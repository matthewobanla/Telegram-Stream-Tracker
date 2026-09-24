# 🎙️ Telegram Live Stream Participant Tracker

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Telethon](https://img.shields.io/badge/library-Telethon-orange.svg)](https://github.com/LonamiWebs/Telethon)
[![Database](https://img.shields.io/badge/database-SQLite3-lightgrey.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An automated participant tracking and analytics system for **Telegram Group & Channel Voice and Video Streams**.

The tracker records real-time participant join/leave/rejoin events, computes exact listening durations and percentage participation, maintains persistent SQLite history, generates CSV export spreadsheets, and auto-posts leaderboard reports directly into your Telegram chat.

---

## ✨ Features

- ⏱ **Precision Time Tracking**: Tracks exact join, drop-off, and rejoin timestamps for every participant.
- 📊 **Participation Metrics**: Calculates total minutes listened and individual attendance percentages `(User Duration / Stream Duration) * 100%`.
- 🏆 **Interactive Leaderboard**: Sorts attendees from most active to least active.
- 🤖 **In-Chat Telegram Bot**: Allows admins and members to query `/stats`, `/livestatus`, and download `/export` spreadsheets directly in Telegram.
- 📤 **Auto-Post Reports**: Automatically posts a formatted summary report and attaches the `.csv` file to the chat when a stream concludes.
- 💾 **Persistent SQLite Database**: Stores all stream sessions, caller history, and stats across app restarts (`tracker.db`).
- 📁 **CSV Exports**: Automatically archives detailed attendee spreadsheets to the `reports/` folder.
- 🚀 **24/7 Cloud & Docker Ready**: Containerized with Docker and ready for deployment on VPS, Render, Railway, or local servers.

---

## 🏗️ How It Works (Dual-Engine Architecture)

Due to Telegram API restrictions, standard Telegram bots cannot access group voice call streams or view live voice chat participants. 

This tracker solves that with a **Dual-Engine** design:

1. **User Client (`user_client`)**: Connects using your Telegram user account credentials (via Telethon MTProto) to monitor voice chat events (`UpdateGroupCallParticipants`), resolve participant profiles, and track call durations.
2. **Bot Client (`bot_client`)**: Runs concurrently to handle in-chat commands (`/stats`, `/livestatus`, `/export`) and automatically send post-stream reports with CSV files to the chat.

```
┌────────────────────────────────────────────────────────┐
│                   TELEGRAM VOICE CALL                  │
└──────────────────────────┬─────────────────────────────┘
                           │ Raw Events & Polling
                           ▼
             ┌───────────────────────────┐
             │  User Client (Telethon)   │
             └─────────────┬─────────────┘
                           │
                 [ Session Tracker ] ──► [ SQLite DB & CSV ]
                           │
                           ▼
             ┌───────────────────────────┐
             │    Bot Client (Token)     │
             └─────────────┬─────────────┘
                           │
                           ▼
          Auto-Post Report & CSV to Telegram Group
```

---

## 📋 Prerequisites

Before getting started, you need:

1. **Telegram API ID & Hash**:
   - Go to [my.telegram.org](https://my.telegram.org) and log in.
   - Click **API development tools** and create a new application.
   - Copy your `App api_id` and `App api_hash`.

2. **Telegram Bot Token**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, choose a name and username.
   - Copy the generated `HTTP API Token`.

3. **Group / Channel Permissions**:
   - The **User Account** must be a member of the target group or channel.
   - The **Bot** must be added to the target group and promoted to **Administrator** (with permissions to *Send Messages* and *Send Media/Documents*).

---

## 🚀 Quick Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/telegram-stream-tracker.git
cd telegram-stream-tracker
```

### 2. Set Up a Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

You can configure the application using environment variables (`.env`) or by directly updating `config.py`.

### Option A: Using `.env` (Recommended)
Copy the template file:
```bash
cp .env.example .env
```
Edit `.env` with your credentials:
```ini
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TARGET_CHAT=@YourGroupOrChannel
AUTO_POST_REPORT_TO_CHAT=True
CSV_OUTPUT_DIR=reports
```

### Option B: Using `config.py`
Open `config.py` and replace placeholder values with your credentials.

---

## 🔑 One-Time User Account Login

To allow the user client to connect to Telegram, run the login script once:

```bash
python login.py
```
1. Enter your phone number (international format, e.g., `+1234567890`).
2. Enter the login confirmation code sent to your Telegram app.
3. If you have 2-Factor Authentication (2FA) enabled, enter your password.

This will generate a secure `tracker_session.session` file locally. Future runs will authenticate automatically without asking for codes.

---

## ▶️ Running the Tracker

Start the live tracking daemon:

```bash
python tracker.py
```

When started, the console will confirm:
- `[UI Bot Online]` — Bot is active and listening for Telegram commands.
- `[Stream Monitor]` — User client is connected and monitoring voice calls in the target group.

The tracker will now run continuously in the background, automatically detecting when voice calls start and end.

---

## 💬 In-Telegram Bot Commands

Members and admins can use the following commands in any group or in private DM with the bot:

| Command | Description |
| :--- | :--- |
| **`/trackhere`** | *(In Group)* Immediately starts tracking attendance for the current group. |
| **`/addgroup @group`** | Adds a target group/channel by username or Chat ID to active tracking. |
| **`/removegroup @group`** | Removes a group from tracking. |
| **`/groups`** | Lists all currently tracked groups and their real-time live stream statuses. |
| **`/stats`** or **`/report`** | Displays the top 20 participant leaderboard and duration statistics for the active stream or last completed stream. |
| **`/livestatus`** | Checks if a live stream is currently active across all tracked groups with elapsed time and online count. |
| **`/export`** or **`/csv`** | Generates and sends the complete `.csv` participation spreadsheet directly in the chat. |
| **`/admins`** | Lists all configured admins receiving auto-reports. |
| **`/addadmin @user`** | Adds an admin to receive post-stream reports & CSVs in private DM. |
| **`/removeadmin @user`** | Removes an admin from report delivery. |
| **`/help`** | Displays the available commands and help menu. |

---

## 📊 Sample Output & Reports

### Terminal Console Output
```text
================================================================================
  LIVE STREAM PARTICIPATION REPORT
  Start Time : 2026-08-14 20:12:00 UTC
  End Time   : 2026-08-14 20:20:00 UTC
  Duration   : 8.00 minutes (480 seconds)
  Total Users: 29
================================================================================
╒════════╤══════════════════╤═════════════════╤══════════════╤══════════════╤════════════╤══════════════╤═════════════════╕
│   Rank │ Name             │ Username        │ First Join   │ Last Leave   │   Sessions │ Total Time   │ Participation   │
╞════════╪══════════════════╪═════════════════╪══════════════╪══════════════╪════════════╪══════════════╪═════════════════╡
│      1 │ Matthew Ọbańlá   │ @KingmattMO     │ 20:12:00     │ 20:20:00     │          1 │ 8.0 min      │ 100.0%          │
│      2 │ Esther Olajide   │ @toluwa_nisola  │ 20:12:00     │ 20:20:00     │          1 │ 8.0 min      │ 100.0%          │
│      3 │ Adekunle Philip  │ @philipecclesia │ 20:12:01     │ 20:20:00     │          1 │ 8.0 min      │ 100.0%          │
...
```

### Auto-Posted Telegram Summary
```text
📊 Live Stream Participation Report (🏁 CALL FINISHED)

⏱ Duration: 8.0 mins
👥 Total Participants: 29
📅 Started: 2026-08-14 20:12:00 UTC

🏆 Participant Leaderboard:
#01 ⚪️ Matthew Ọbańlá (@KingmattMO)
      └ ⏳ 8.0m (100.0%) | 🚪 1 joins
#02 ⚪️ Esther Olajide (@toluwa_nisola)
      └ ⏳ 8.0m (100.0%) | 🚪 1 joins
#03 ⚪️ Adekunle Philip (@philipecclesia)
      └ ⏳ 8.0m (100.0%) | 🚪 1 joins
...
[File Attached: report_20260814_202000.csv]
```

---

## 🐳 Docker Deployment

### 1. Build and Run with Docker
```bash
# Build the image
docker build -t telegram-stream-tracker .

# Run container (mounting session and db files)
docker run -d \
  --name stream-tracker \
  --env-file .env \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/tracker_session.session:/app/tracker_session.session \
  -v $(pwd)/tracker.db:/app/tracker.db \
  telegram-stream-tracker
```

### 2. Docker Compose (Optional)
Create a `docker-compose.yml`:
```yaml
version: '3.8'
services:
  tracker:
    build: .
    container_name: telegram-stream-tracker
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./reports:/app/reports
      - ./tracker_session.session:/app/tracker_session.session
      - ./tracker.db:/app/tracker.db
```
Start with:
```bash
docker compose up -d
```

---

## ☁️ Cloud Deployment (Render / VPS)

### Render Worker Setup
1. Create a **Background Worker** on [Render](https://render.com).
2. Connect your Git repository.
3. Use the following build settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python tracker.py`
4. Add your Environment Variables (`API_ID`, `API_HASH`, `BOT_TOKEN`, `TARGET_CHAT`) in the Render Dashboard.
5. Upload your `tracker_session.session` file as a secret file or persistent disk to avoid re-login.

### Linux VPS (Systemd Service)
Create a service file at `/etc/systemd/system/telegram-tracker.service`:
```ini
[Unit]
Description=Telegram Live Stream Participant Tracker
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/telegram-stream-tracker
ExecStart=/path/to/telegram-stream-tracker/.venv/bin/python tracker.py
Restart=always
RestartSec=10
EnvironmentFile=/path/to/telegram-stream-tracker/.env

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-tracker
sudo systemctl start telegram-tracker
```

---

## 🛡️ Security & Privacy Best Practices

- **Never commit `.session` files**: Session files grant full access to your Telegram account. Keep `*.session` in your `.gitignore` at all times.
- **Keep Bot Tokens & API Keys Private**: Never hardcode credentials into public code. Use environment variables or `.env` files.
- **Bot Permissions**: Only grant the bot Administrator rights needed to post messages and upload files.

---

## 📄 Database Schema

The app uses SQLite (`tracker.db`) with three tables:

- `streams`: Stores stream ID, call ID, chat title, start/end timestamps, duration, total participants, and active status.
- `participants`: Stores caller records per stream (User ID, name, username, first join, last leave, session count, duration, participation %).
- `sessions`: Stores individual join/leave intervals for users who drop off and rejoin multiple times.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!
1. Fork the repository
2. Create your branch: `git checkout -b feature/NewFeature`
3. Commit your changes: `git commit -m 'Add NewFeature'`
4. Push to branch: `git push origin feature/NewFeature`
5. Open a Pull Request

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
