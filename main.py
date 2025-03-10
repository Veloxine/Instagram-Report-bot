import os
import sys
import random
import logging
import re
from collections import defaultdict
from threading import Thread
import telebot
import instaloader
from flask import Flask
from dotenv import load_dotenv
import asyncio

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

# Initialize the Telegram bot
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = telebot.TeleBot(API_TOKEN)

# In-memory list to store user IDs
user_ids = set()

def add_user(user_id):
    user_ids.add(user_id)

def remove_user(user_id):
    user_ids.discard(user_id)

def get_all_users():
    return list(user_ids)

# List of keywords for different report categories
report_keywords = {
    "HATE": ["devil", "666", "savage", "love", "hate", "followers", "selling", "sold", "seller", "dick", "ban", "banned", "free", "method", "paid"],
    "SELF": ["suicide", "blood", "death", "dead", "kill myself"],
    "BULLY": ["@"],
    "VIOLENT": ["hitler", "osama bin laden", "guns", "soldiers", "masks", "flags"],
    "ILLEGAL": ["drugs", "cocaine", "plants", "trees", "medicines"],
    "PRETENDING": ["verified", "tick"],
    "NUDITY": ["nude", "sex", "send nudes"],
    "SPAM": ["phone number", "email", "contact"]
}

def check_keywords(text, keywords):
    return any(keyword in text.lower() for keyword in keywords)

def analyze_profile(profile_info):
    reports = defaultdict(int)
    profile_texts = [profile_info.get("username", ""), profile_info.get("biography", "")]

    for text in profile_texts:
        for category, keywords in report_keywords.items():
            if check_keywords(text, keywords):
                reports[category] += 1

    if reports:
        unique_counts = random.sample(range(1, 6), min(len(reports), 4))
        formatted_reports = {category: f"{count}x - {category}" for category, count in zip(reports.keys(), unique_counts)}
    else:
        selected_categories = random.sample(list(report_keywords.keys()), random.randint(2, 5))
        unique_counts = random.sample(range(1, 6), len(selected_categories))
        formatted_reports = {category: f"{count}x - {category}" for category, count in zip(selected_categories, unique_counts)}

    return formatted_reports

def get_public_instagram_info(username):
    L = instaloader.Instaloader()
    try:
        profile = instaloader.Profile.from_username(L.context, username)
        return {
            "username": profile.username,
            "full_name": profile.full_name,
            "biography": profile.biography,
            "follower_count": profile.followers,
            "following_count": profile.followees,
            "is_private": profile.is_private,
            "post_count": profile.mediacount,
            "external_url": profile.external_url,
        }
    except instaloader.exceptions.ProfileNotExistsException:
        return None
    except instaloader.exceptions.InstaloaderException as e:
        logging.error(f"An error occurred: {e}")
        return None

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    add_user(user_id)  # Add user to the list
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Help", callback_data='help'))
    markup.add(telebot.types.InlineKeyboardButton("Update Channel", url='t.me/team_loops'))
    bot.reply_to(message, "Welcome! Use /getmeth <username> to analyze an Instagram profile.", reply_markup=markup)

@bot.message_handler(commands=['getmeth'])
def analyze(message):
    username = message.text.split()[1:]  # Get username from command
    if not username:
        bot.reply_to(message, "😾 Incorrect format! Use /getmeth <username> (without @ & < >).")
        return

    username = ' '.join(username)
    bot.reply_to(message, f"🔍 Scanning Profile: {username}. Please wait...")

    profile_info = get_public_instagram_info(username)
    if profile_info:
        reports_to_file = analyze_profile(profile_info)
        result_text = f"**Public Information for {username}:**\n"
        result_text += f"Username: {profile_info.get('username', 'N/A')}\n"
        result_text += f"Full Name: {profile_info.get('full_name', 'N/A')}\n"
        result_text += f"Biography: {profile_info.get('biography', 'N/A')}\n"
        result_text += f"Followers: {profile_info.get('follower_count', 'N/A')}\n"
        result_text += f"Following: {profile_info.get('following_count', 'N/A')}\n"
        result_text += f"Private Account: {'Yes' if profile_info.get('is_private') else 'No'}\n"
        result_text += f"Posts: {profile_info.get('post_count', 'N/A')}\n"
        result_text += f"External URL: {profile_info.get('external_url', 'N/A')}\n\n"
        result_text += "Suggested Reports:\n"
        for report in reports_to_file.values():
            result_text += f"• {report}\n"

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Visit Profile", url=f"https://instagram.com/{profile_info['username']}"))
        markup.add(telebot.types.InlineKeyboardButton("Developer", url='t.me/focro'))

        bot.send_message(message.chat.id, result_text, reply_markup=markup, parse_mode='MarkdownV2')
    else:
        bot.reply_to(message, f"❌ Profile {username} not found or an error occurred.")

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    bot.reply_to(message, "Bot is restarting...")
    logging.info("Bot is restarting...")
    os.execv(sys.executable, ['python'] + sys.argv)

if __name__ == "__main__":
    print("Starting the bot...")
    logging.info("Bot started.")
    
    # Fix API Conflict: Use async polling instead of threading
    asyncio.run(bot.infinity_polling(timeout=10, long_polling_timeout=5))
