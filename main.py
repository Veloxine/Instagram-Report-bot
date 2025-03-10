import os
import sys
import logging
import requests
import time
import instaloader
import asyncio
from threading import Thread
import telebot
from flask import Flask
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask app to keep the bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive"

def run_flask_app():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask_app)
    t.start()

# Start Flask app in a separate thread
keep_alive()

# Initialize Telegram bot
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
bot = telebot.TeleBot(API_TOKEN)

# Store active sessions (Temporary)
active_sessions = {}

# Instagram Report Types
REPORT_TYPES = {
    "HATE": 5,
    "SELF": 6,
    "BULLY": 7,
    "VIOLENT": 4,
    "ILLEGAL": 3,
    "PRETENDING": 1,
    "NUDITY": 2,
    "SPAM": 8
}

# **LOGIN TO INSTAGRAM**
@bot.message_handler(commands=['login'])
def request_login(message):
    bot.reply_to(message, "🔐 Send Instagram login as:\n`username password`", parse_mode="MarkdownV2")

@bot.message_handler(func=lambda message: len(message.text.split()) == 2)
def handle_login(message):
    username, password = message.text.split()

    L = instaloader.Instaloader()

    try:
        L.login(username, password)
        cookies = L.context._session.cookies.get_dict()
        session_id = cookies.get("sessionid")

        if session_id:
            active_sessions[message.chat.id] = session_id
            bot.reply_to(message, "✅ Login successful!")
        else:
            bot.reply_to(message, "❌ Error fetching session ID. Try again.")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Login failed: {e}")

# **FETCH INSTAGRAM PROFILE**
def get_instagram_info(username, session_id):
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": f"sessionid={session_id}"}
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"

    for _ in range(3):  # Retry up to 3 times
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json().get("data", {}).get("user", {})
            if user_data:
                return {
                    "username": user_data.get("username"),
                    "full_name": user_data.get("full_name"),
                    "biography": user_data.get("biography"),
                    "followers": user_data.get("edge_followed_by", {}).get("count"),
                    "following": user_data.get("edge_follow", {}).get("count"),
                    "private": user_data.get("is_private"),
                    "posts": user_data.get("edge_owner_to_timeline_media", {}).get("count"),
                    "external_url": user_data.get("external_url"),
                }
        time.sleep(2)
    return None

# **SPAM REPORT FUNCTION**
def report_instagram(username, session_id, report_reason, count=5):
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": f"sessionid={session_id}"}
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        return f"❌ Error: Could not fetch user info ({response.status_code})"

    user_id = response.json().get("data", {}).get("user", {}).get("id")
    if not user_id:
        return "❌ Error: User not found."

    report_url = "https://www.instagram.com/api/v1/users/report_user/"
    success = 0

    for _ in range(count):
        payload = {"user_id": user_id, "reason_id": report_reason, "source_name": "profile"}
        response = requests.post(report_url, headers=headers, data=payload)

        if response.status_code == 200:
            success += 1
        else:
            logging.error(f"❌ Report failed: {response.text}")
        time.sleep(2)

    return f"✅ Reported **{username}** {success} times under **{list(REPORT_TYPES.keys())[list(REPORT_TYPES.values()).index(report_reason)]}**."

# **COMMAND: GET PROFILE**
@bot.message_handler(commands=['getmeth'])
def getmeth_command(message):
    user_id = message.chat.id
    if user_id not in active_sessions:
        bot.reply_to(message, "⚠️ Please log in using /login.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: /getmeth <username>")
        return

    username = args[1].strip()
    bot.reply_to(message, f"🔍 Fetching {username}... Please wait.")

    info = get_instagram_info(username, active_sessions[user_id])

    if info:
        bot.reply_to(message, f"📌 **{info['username']}**\n👤 {info['full_name']}\n📄 {info['biography']}\n👥 {info['followers']} followers\n🔗 {info['external_url']}")
    else:
        bot.reply_to(message, "❌ Error fetching profile.")

# **COMMAND: REPORT ACCOUNT**
@bot.message_handler(commands=['spamreport'])
def spam_report_command(message):
    user_id = message.chat.id
    if user_id not in active_sessions:
        bot.reply_to(message, "⚠️ Please log in using /login.")
        return

    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Usage: /spamreport <username> <report_type> [count]\n📌 Available types:\n" + "\n".join(f"- {key}" for key in REPORT_TYPES.keys()))
        return

    username = args[1].strip()
    report_type = args[2].strip().upper()
    count = int(args[3]) if len(args) > 3 and args[3].isdigit() else 5

    if report_type not in REPORT_TYPES:
        bot.reply_to(message, "⚠️ Invalid report type!\n📌 Available types:\n" + "\n".join(f"- {key}" for key in REPORT_TYPES.keys()))
        return

    bot.reply_to(message, f"🚨 Reporting **{username}** {count} times under **{report_type}**...")

    result = report_instagram(username, active_sessions[user_id], REPORT_TYPES[report_type], count)
    bot.reply_to(message, result)

# **COMMAND: HELP MENU**
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "📌 **Commands:**\n/login - Log in\n/getmeth <username> - Get profile\n/spamreport <username> <type> <count> - Report user")

# **SAFE BOT POLLING**
if __name__ == "__main__":
    print("Bot starting...")
    logging.info("Bot started.")
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except requests.exceptions.ConnectionError:
            logging.error("🔴 Connection lost. Restarting...")
            time.sleep(5)
