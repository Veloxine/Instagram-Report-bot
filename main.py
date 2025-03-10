import os
import sys
import random
import logging
import re
import time
import requests
import instaloader
import asyncio
from collections import defaultdict
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

# Start the Flask app in a thread
keep_alive()

# Initialize Telegram bot
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
bot = telebot.TeleBot(API_TOKEN)

# Store temporary session IDs for active users
active_sessions = {}

# Mapping report types to Instagram's internal reason IDs
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

# Function to handle user login
@bot.message_handler(commands=['login'])
def request_login(message):
    bot.reply_to(message, "🔐 Send your Instagram login details in this format:\n`username password`", parse_mode="MarkdownV2")

@bot.message_handler(func=lambda message: len(message.text.split()) == 2)
def handle_login(message):
    username, password = message.text.split()

    L = instaloader.Instaloader()

    try:
        L.login(username, password)  # Log in to Instagram
        cookies = L.context._session.cookies.get_dict()
        session_id = cookies.get("sessionid")

        if session_id:
            active_sessions[message.chat.id] = session_id  # Store session temporarily
            bot.reply_to(message, "✅ Login successful! Your session is active for this session.")
        else:
            bot.reply_to(message, "❌ Error: Could not fetch session ID. Try again.")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Login failed: {e}")

# Function to fetch Instagram profile details
def get_public_instagram_info(username, session_id):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": f"sessionid={session_id}"
    }

    response = requests.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}", headers=headers)
    
    if response.status_code != 200:
        return None
    
    user_data = response.json().get("data", {}).get("user", {})
    
    if not user_data:
        return None
    
    return {
        "username": user_data.get("username"),
        "full_name": user_data.get("full_name"),
        "biography": user_data.get("biography"),
        "follower_count": user_data.get("edge_followed_by", {}).get("count"),
        "following_count": user_data.get("edge_follow", {}).get("count"),
        "is_private": user_data.get("is_private"),
        "post_count": user_data.get("edge_owner_to_timeline_media", {}).get("count"),
        "external_url": user_data.get("external_url"),
    }

# Function to report Instagram accounts with a selected reason
def report_instagram_account(username, session_id, report_reason, report_count=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": f"sessionid={session_id}"
    }

    user_info_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    response = requests.get(user_info_url, headers=headers)
    
    if response.status_code != 200:
        return f"❌ Error: Could not fetch user info (Error {response.status_code})"

    user_id = response.json().get("data", {}).get("user", {}).get("id")

    if not user_id:
        return "❌ Error: User not found on Instagram."

    report_url = "https://www.instagram.com/api/v1/users/report_user/"
    success_count = 0

    for _ in range(report_count):
        payload = {
            "user_id": user_id,
            "reason_id": report_reason,
            "source_name": "profile"
        }
        
        report_response = requests.post(report_url, headers=headers, data=payload)
        
        if report_response.status_code == 200:
            success_count += 1
        else:
            logging.error(f"❌ Failed to report {username}. Response: {report_response.text}")

        time.sleep(2)  # Delay to avoid detection

    return f"✅ Successfully reported **{username}** {success_count} times under **{list(REPORT_TYPES.keys())[list(REPORT_TYPES.values()).index(report_reason)]}**."

# Telegram bot command for reporting
@bot.message_handler(commands=['spamreport'])
def spam_report_command(message):
    user_id = message.chat.id

    if user_id not in active_sessions:
        bot.reply_to(message, "⚠️ You must log in first using /login.")
        return

    args = message.text.split()

    if len(args) < 3:
        bot.reply_to(message, "⚠️ Usage: /spamreport <username> <report_type> [count]\n\nAvailable report types:\n" + "\n".join(f"- {key}" for key in REPORT_TYPES.keys()))
        return

    username = args[1].strip()
    report_type = args[2].strip().upper()
    count = int(args[3]) if len(args) > 3 and args[3].isdigit() else 5  # Default: 5 reports

    if report_type not in REPORT_TYPES:
        bot.reply_to(message, "⚠️ Invalid report type! Available types:\n" + "\n".join(f"- {key}" for key in REPORT_TYPES.keys()))
        return

    bot.reply_to(message, f"🚨 Reporting **{username}** {count} times under **{report_type}**... Please wait.")

    result = report_instagram_account(username, active_sessions[user_id], REPORT_TYPES[report_type], count)

    bot.reply_to(message, result)

# Help command
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📌 **Available Commands:**\n\n"
        "🔹 `/login <username> <password>` - Log in to Instagram (temporary session).\n"
        "🔹 `/getmeth <username>` - Fetch Instagram profile details.\n"
        "🔹 `/spamreport <username> <report_type> <count>` - Report an account multiple times.\n"
        "🔹 **Report Types:**\n" + "\n".join(f"- {key}" for key in REPORT_TYPES.keys())
    )
    bot.reply_to(message, help_text, parse_mode='MarkdownV2')

if __name__ == "__main__":
    print("Starting the bot...")
    logging.info("Bot started.")
    asyncio.run(bot.infinity_polling(timeout=10, long_polling_timeout=5))
