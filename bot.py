import json
import threading
import time
import os
import random
import re
import requests
import pytz
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

def load_accounts():
    try:
        with open("accounts.txt", "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines() if line.strip()]
            accounts = []
            current_account = {}
            for line in lines:
                if line.startswith('TOKEN='):
                    current_account['token'] = line.split('=', 1)[1].strip()
                elif line.startswith('API_KEY='):
                    current_account['api_key'] = line.split('=', 1)[1].strip()
                    if 'token' in current_account and 'api_key' in current_account:
                        accounts.append(current_account)
                        current_account = {}
            return accounts
    except FileNotFoundError:
        raise ValueError("accounts.txt file not found!")

accounts = load_accounts()
if not accounts:
    raise ValueError("No accounts found in accounts.txt!")

discord_tokens = [acc['token'] for acc in accounts]
google_api_keys = [acc['api_key'] for acc in accounts]

GEMINI_MODEL = 'gemini-2.5-flash'

processed_message_ids = set()
used_api_keys = set()
last_generated_text = None
cooldown_time = 86400

def get_wib_time():
    wib = pytz.timezone('Asia/Jakarta')
    return datetime.now(wib).strftime('%H:%M:%S')

def print_banner():
    banner = f"""
{Fore.CYAN}DISCORD AUTO BOT{Style.RESET_ALL}
{Fore.WHITE}By: FEBRIYAN{Style.RESET_ALL}
{Fore.CYAN}============================================================{Style.RESET_ALL}
"""
    print(banner)

def log(message, level="INFO"):
    time_str = get_wib_time()
    
    if level == "INFO":
        color = Fore.CYAN
        symbol = "[INFO]"
    elif level == "SUCCESS":
        color = Fore.GREEN
        symbol = "[SUCCESS]"
    elif level == "ERROR":
        color = Fore.RED
        symbol = "[ERROR]"
    elif level == "WARNING":
        color = Fore.YELLOW
        symbol = "[WARNING]"
    elif level == "WAIT":
        color = Fore.MAGENTA
        symbol = ""
    else:
        color = Fore.WHITE
        symbol = "[LOG]"
    
    print(f"[{time_str}] {color}{symbol} {message}{Style.RESET_ALL}")

def get_random_api_key():
    available_keys = [key for key in google_api_keys if key not in used_api_keys]
    if not available_keys:
        log("All API keys hit 429 error. Waiting 24 hours before retry...", "ERROR")
        time.sleep(cooldown_time)
        used_api_keys.clear()
        return get_random_api_key()
    return random.choice(available_keys)

def get_random_message_from_file():
    try:
        with open("message.txt", "r", encoding="utf-8") as file:
            messages = [line.strip() for line in file.readlines() if line.strip()]
            return random.choice(messages) if messages else "No messages available in file."
    except FileNotFoundError:
        return "message.txt file not found!"

def generate_language_specific_prompt(user_message, prompt_language):
    if prompt_language == 'id':
        return f"Balas pesan berikut dalam bahasa Indonesia: {user_message}"
    elif prompt_language == 'en':
        return f"Reply to the following message in English: {user_message}"
    else:
        log(f"Invalid prompt language '{prompt_language}'. Message skipped.", "WARNING")
        return None

def generate_reply(prompt, prompt_language, use_google_ai=True):
    global last_generated_text
    if use_google_ai:
        google_api_key = get_random_api_key()
        lang_prompt = generate_language_specific_prompt(prompt, prompt_language)
        if lang_prompt is None:
            return None
        
        if prompt_language == 'id':
            ai_prompt = f"{lang_prompt}\n\nBuatlah menjadi 1 kalimat menggunakan bahasa sehari-hari Indonesia yang natural."
        else:
            ai_prompt = f"{lang_prompt}\n\nMake it 1 sentence using natural everyday English."
        
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={google_api_key}'
        
        headers = {'Content-Type': 'application/json'}
        data = {'contents': [{'parts': [{'text': ai_prompt}]}]}
        while True:
            try:
                response = requests.post(url, headers=headers, json=data)
                
                if response.status_code == 404:
                    log(f"Model {GEMINI_MODEL} not found or invalid API key. Using another API key...", "ERROR")
                    used_api_keys.add(google_api_key)
                    return generate_reply(prompt, prompt_language, use_google_ai)
                
                if response.status_code == 429:
                    log(f"API key hit rate limit (429). Using another API key...", "WARNING")
                    used_api_keys.add(google_api_key)
                    return generate_reply(prompt, prompt_language, use_google_ai)
                
                response.raise_for_status()
                result = response.json()
                generated_text = result['candidates'][0]['content']['parts'][0]['text']
                
                if generated_text == last_generated_text:
                    log("AI generated same text, requesting new text...", "WAIT")
                    continue
                    
                last_generated_text = generated_text
                return generated_text
                
            except requests.exceptions.RequestException as e:
                log(f"Request failed: {e}", "ERROR")
                time.sleep(2)
    else:
        return get_random_message_from_file()

def get_channel_info(channel_id, token):
    headers = {'Authorization': token}
    channel_url = f"https://discord.com/api/v9/channels/{channel_id}"
    try:
        channel_response = requests.get(channel_url, headers=headers)
        channel_response.raise_for_status()
        channel_data = channel_response.json()
        channel_name = channel_data.get('name', 'Unknown Channel')
        guild_id = channel_data.get('guild_id')
        server_name = "Direct Message"
        if guild_id:
            guild_url = f"https://discord.com/api/v9/guilds/{guild_id}"
            guild_response = requests.get(guild_url, headers=headers)
            guild_response.raise_for_status()
            guild_data = guild_response.json()
            server_name = guild_data.get('name', 'Unknown Server')
        return server_name, channel_name
    except requests.exceptions.RequestException as e:
        log(f"Error getting channel info: {e}", "ERROR")
        return "Unknown Server", "Unknown Channel"

def get_bot_info(token):
    headers = {'Authorization': token}
    try:
        response = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
        response.raise_for_status()
        data = response.json()
        username = data.get("username", "Unknown")
        discriminator = data.get("discriminator", "")
        bot_id = data.get("id", "Unknown")
        return username, discriminator, bot_id
    except requests.exceptions.RequestException as e:
        log(f"Failed to get bot account info: {e}", "ERROR")
        return "Unknown", "", "Unknown"

def auto_reply(channel_id, settings, token):
    headers = {'Authorization': token}
    if settings["use_google_ai"]:
        try:
            bot_info_response = requests.get('https://discord.com/api/v9/users/@me', headers=headers)
            bot_info_response.raise_for_status()
            bot_user_id = bot_info_response.json().get('id')
        except requests.exceptions.RequestException as e:
            log(f"Failed to get bot info: {e}", "ERROR")
            return

        while True:
            prompt = None
            reply_to_id = None
            log(f"Waiting {settings['read_delay']} seconds before reading messages...", "WAIT")
            time.sleep(settings["read_delay"])
            try:
                response = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages', headers=headers)
                response.raise_for_status()
                messages = response.json()
                if messages:
                    most_recent_message = messages[0]
                    message_id = most_recent_message.get('id')
                    author_id = most_recent_message.get('author', {}).get('id')
                    message_type = most_recent_message.get('type', '')
                    if author_id != bot_user_id and message_type != 8 and message_id not in processed_message_ids:
                        user_message = most_recent_message.get('content', '').strip()
                        attachments = most_recent_message.get('attachments', [])
                        if attachments or not re.search(r'\w', user_message):
                            log(f"Message not processed (not pure text).", "WARNING")
                        else:
                            log(f"Received: {user_message}", "INFO")
                            if settings["use_slow_mode"]:
                                slow_mode_delay = get_slow_mode_delay(channel_id, token)
                                log(f"Slow mode delay: {slow_mode_delay} seconds", "INFO")
                                log(f"Slow mode active, waiting {slow_mode_delay} seconds...", "WAIT")
                                time.sleep(slow_mode_delay)
                            prompt = user_message
                            reply_to_id = message_id
                            processed_message_ids.add(message_id)
                else:
                    prompt = None
            except requests.exceptions.RequestException as e:
                log(f"Request error: {e}", "ERROR")
                prompt = None

            if prompt:
                result = generate_reply(prompt, settings["prompt_language"], settings["use_google_ai"])
                if result is None:
                    log(f"Invalid prompt language. Message skipped.", "WARNING")
                else:
                    response_text = result if result else "Sorry, cannot reply to message."
                    if response_text.strip().lower() == prompt.strip().lower():
                        log(f"Reply same as received message. Not sending reply.", "WARNING")
                    else:
                        if settings["use_reply"]:
                            send_message(channel_id, response_text, token, reply_to=reply_to_id, 
                                         delete_after=settings["delete_bot_reply"], delete_immediately=settings["delete_immediately"])
                        else:
                            send_message(channel_id, response_text, token, 
                                         delete_after=settings["delete_bot_reply"], delete_immediately=settings["delete_immediately"])
            else:
                log(f"No new messages or invalid message.", "INFO")

            log(f"Waiting {settings['delay_interval']} seconds before next iteration...", "WAIT")
            time.sleep(settings["delay_interval"])
    else:
        while True:
            delay = settings["delay_interval"]
            log(f"Waiting {delay} seconds before sending message from file...", "WAIT")
            time.sleep(delay)
            message_text = generate_reply("", settings["prompt_language"], use_google_ai=False)
            if settings["use_reply"]:
                send_message(channel_id, message_text, token, delete_after=settings["delete_bot_reply"], delete_immediately=settings["delete_immediately"])
            else:
                send_message(channel_id, message_text, token, delete_after=settings["delete_bot_reply"], delete_immediately=settings["delete_immediately"])

def send_message(channel_id, message_text, token, reply_to=None, delete_after=None, delete_immediately=False):
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message_text}
    if reply_to:
        payload["message_reference"] = {"message_id": reply_to}
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        if response.status_code in [200, 201]:
            data = response.json()
            message_id = data.get("id")
            log(f"Message sent: \"{message_text}\"", "SUCCESS")
            if delete_after is not None:
                if delete_immediately:
                    log(f"Deleting message immediately without delay...", "WAIT")
                    threading.Thread(target=delete_message, args=(channel_id, message_id, token), daemon=True).start()
                elif delete_after > 0:
                    log(f"Message will be deleted in {delete_after} seconds...", "WAIT")
                    threading.Thread(target=delayed_delete, args=(channel_id, message_id, delete_after, token), daemon=True).start()
        else:
            log(f"Failed to send message. Status: {response.status_code}", "ERROR")
            log(f"API Response: {response.text}", "ERROR")
    except requests.exceptions.RequestException as e:
        log(f"Error sending message: {e}", "ERROR")

def delayed_delete(channel_id, message_id, delay, token):
    time.sleep(delay)
    delete_message(channel_id, message_id, token)

def delete_message(channel_id, message_id, token):
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}'
    try:
        response = requests.delete(url, headers=headers)
        if response.status_code == 204:
            log(f"Message ID {message_id} successfully deleted.", "SUCCESS")
        else:
            log(f"Failed to delete message. Status: {response.status_code}", "ERROR")
            log(f"API Response: {response.text}", "ERROR")
    except requests.exceptions.RequestException as e:
        log(f"Error deleting message: {e}", "ERROR")

def get_slow_mode_delay(channel_id, token):
    headers = {'Authorization': token, 'Accept': 'application/json'}
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        slow_mode_delay = data.get("rate_limit_per_user", 0)
        return slow_mode_delay
    except requests.exceptions.RequestException as e:
        log(f"Failed to get slow mode info: {e}", "ERROR")
        return 5

def get_server_settings(channel_id, channel_name):
    print(f"\n{Fore.CYAN}Enter settings for channel {channel_id} (Channel Name: {channel_name}):{Style.RESET_ALL}")
    use_google_ai = input(f"{Fore.GREEN}Use Google Gemini AI? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
    
    if use_google_ai:
        prompt_language = input(f"{Fore.GREEN}Select prompt language (en/id): {Style.RESET_ALL}").strip().lower()
        if prompt_language not in ["en", "id"]:
            print(f"{Fore.YELLOW}Invalid input. Defaulting to 'id'.{Style.RESET_ALL}")
            prompt_language = "id"
        enable_read_message = True
        read_delay = int(input(f"{Fore.GREEN}Enter message read delay (seconds): {Style.RESET_ALL}"))
        delay_interval = int(input(f"{Fore.GREEN}Enter interval (seconds) for each auto reply iteration: {Style.RESET_ALL}"))
        use_slow_mode = input(f"{Fore.GREEN}Use slow mode? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
    else:
        prompt_language = input(f"{Fore.GREEN}Select message language from file (en/id): {Style.RESET_ALL}").strip().lower()
        if prompt_language not in ["en", "id"]:
            print(f"{Fore.YELLOW}Invalid input. Defaulting to 'id'.{Style.RESET_ALL}")
            prompt_language = "id"
        enable_read_message = False
        read_delay = 0
        delay_interval = int(input(f"{Fore.GREEN}Enter delay (seconds) to send message from file: {Style.RESET_ALL}"))
        use_slow_mode = False

    use_reply = input(f"{Fore.GREEN}Send message as reply? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
    delete_reply = input(f"{Fore.GREEN}Delete bot reply after some seconds? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
    if delete_reply:
        delete_bot_reply = int(input(f"{Fore.GREEN}After how many seconds to delete reply? (0 for no, or enter delay): {Style.RESET_ALL}"))
        delete_immediately = input(f"{Fore.GREEN}Delete message immediately without delay? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
    else:
        delete_bot_reply = None
        delete_immediately = False

    return {
        "prompt_language": prompt_language,
        "use_google_ai": use_google_ai,
        "enable_read_message": enable_read_message,
        "read_delay": read_delay,
        "delay_interval": delay_interval,
        "use_slow_mode": use_slow_mode,
        "use_reply": use_reply,
        "delete_bot_reply": delete_bot_reply,
        "delete_immediately": delete_immediately
    }

if __name__ == "__main__":
    os.system('clear' if os.name == 'posix' else 'cls')
    print_banner()
    
    log(f"Using Gemini model: {GEMINI_MODEL}", "INFO")
    log(f"Loaded {len(accounts)} accounts successfully", "SUCCESS")
    
    print(f"\n{Fore.CYAN}============================================================{Style.RESET_ALL}\n")

    bot_accounts = {}
    for token in discord_tokens:
        username, discriminator, bot_id = get_bot_info(token)
        bot_accounts[token] = {"username": username, "discriminator": discriminator, "bot_id": bot_id}
        log(f"Bot Account: {username}#{discriminator} (ID: {bot_id})", "SUCCESS")

    channel_ids = [cid.strip() for cid in input(f"{Fore.GREEN}Enter channel IDs (separate with comma if more than one): {Style.RESET_ALL}").split(",") if cid.strip()]

    token = discord_tokens[0]
    channel_infos = {}
    for channel_id in channel_ids:
        server_name, channel_name = get_channel_info(channel_id, token)
        channel_infos[channel_id] = {"server_name": server_name, "channel_name": channel_name}
        log(f"[Channel {channel_id}] Connected to server: {server_name} | Channel Name: {channel_name}", "SUCCESS")

    server_settings = {}
    for channel_id in channel_ids:
        channel_name = channel_infos.get(channel_id, {}).get("channel_name", "Unknown Channel")
        server_settings[channel_id] = get_server_settings(channel_id, channel_name)

    print(f"\n{Fore.CYAN}============================================================{Style.RESET_ALL}\n")
    
    for cid, settings in server_settings.items():
        info = channel_infos.get(cid, {"server_name": "Unknown Server", "channel_name": "Unknown Channel"})
        delete_str = ("Immediately" if settings['delete_immediately'] else 
                     (f"In {settings['delete_bot_reply']} seconds" if settings['delete_bot_reply'] and settings['delete_bot_reply'] > 0 else "No"))
        log(
            f"[Channel {cid} | Server: {info['server_name']} | Channel: {info['channel_name']}] "
            f"Settings: Gemini AI = {'Active' if settings['use_google_ai'] else 'No'}, "
            f"Language = {settings['prompt_language'].upper()}, "
            f"Read Message = {'Active' if settings['enable_read_message'] else 'No'}, "
            f"Read Delay = {settings['read_delay']} seconds, "
            f"Interval = {settings['delay_interval']} seconds, "
            f"Slow Mode = {'Active' if settings['use_slow_mode'] else 'No'}, "
            f"Reply = {'Yes' if settings['use_reply'] else 'No'}, "
            f"Delete Message = {delete_str}",
            "INFO"
        )

    print(f"\n{Fore.CYAN}============================================================{Style.RESET_ALL}\n")

    token_index = 0
    for channel_id in channel_ids:
        token = discord_tokens[token_index % len(discord_tokens)]
        token_index += 1
        bot_info = bot_accounts.get(token, {"username": "Unknown", "discriminator": "", "bot_id": "Unknown"})
        thread = threading.Thread(
            target=auto_reply,
            args=(channel_id, server_settings[channel_id], token)
        )
        thread.daemon = True
        thread.start()
        log(f"[Channel {channel_id}] Bot active: {bot_info['username']}#{bot_info['discriminator']}", "SUCCESS")

    log("Bot is running on multiple servers... Press CTRL+C to stop.", "INFO")
    while True:
        time.sleep(10)
