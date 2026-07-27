import os
import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
import yt_dlp

# جلب بيانات البيئة من Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
ADMIN_ID_ENV = os.getenv("ADMIN_ID")
YT_COOKIES_ENV = os.getenv("YT_COOKIES")

try:
    ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV else None
except ValueError:
    ADMIN_ID = None

bot = telebot.TeleBot(BOT_TOKEN)

user_urls = {}
user_last_request = {}
banned_users = set()

COOLDOWN_TIME = 10 
MAX_FILE_SIZE_BYTES = 48 * 1024 * 1024

def is_user_banned(user_id):
    return user_id in banned_users

def is_subscribed(user_id):
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    
    for ch in [CHANNEL_1, CHANNEL_2]:
        if not ch:
            continue
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                return False
        except Exception as e:
            print(f"Error checking sub for {ch}: {e}")
            return False
    return True

def sub_keyboard():
    markup = InlineKeyboardMarkup()
    ch1_url = f"https://t.me/{CHANNEL_1.replace('@', '')}" if CHANNEL_1 else "https://t.me"
    ch2_url = f"https://t.me/{CHANNEL_2.replace('@', '')}" if CHANNEL_2 else "https://t.me"
    
    markup.add(InlineKeyboardButton("📢 القناة الأولى", url=ch1_url))
    markup.add(InlineKeyboardButton("📢 القناة الثانية", url=ch2_url))
    markup.add(InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub"))
    return markup

def download_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎬 فيديو", callback_data="dl_video"),
        InlineKeyboardButton("🎵 صوت", callback_data="dl_audio")
    )
    return markup

def get_cookie_file():
    """التحقق من وجود ملف الكوكيز في المشروع أو متغيرات البيئة"""
    if os.path.exists("cookies.txt"):
        return "cookies.txt"
    elif YT_COOKIES_ENV:
        try:
            with open("cookies.txt", "w", encoding="utf-8") as f:
                f.write(YT_COOKIES_ENV)
            return "cookies.txt"
        except Exception as e:
            print(f"Error writing cookies: {e}")
    return None

def download_via_cobalt(url, is_audio=False):
    """المحرك البديل لليوتيوب"""
    api_url = "https://api.cobalt.tools/"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    payload = {
        "url": url,
        "videoQuality": "720"
    }
    if is_audio:
        payload["downloadMode"] = "audio"
        payload["audioFormat"] = "mp3"

    res = requests.post(api_url, json=payload, headers=headers, timeout=25)
    data = res.json()
    
    if data.get("status") in ["redirect", "tunnel"]:
        file_url = data.get("url")
        ext = "mp3" if is_audio else "mp4"
        filename = f"download_yt_{int(time.time())}.{ext}"
        
        with requests.get(file_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            downloaded = 0
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_SIZE_BYTES:
                            f.close()
                            if os.path.exists(filename):
                                os.remove(filename)
                            raise Exception("FileTooBig")
                        f.write(chunk)
        return filename
    else:
        raise Exception(data.get("text", "Cobalt Error"))

# ==================== معالجة الرسائل والأوامر ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        bot.send_message(message.chat.id, "🚫 أنت محظور من استخدام هذا البوت.")
        return

    if not is_subscribed(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في القنوات التالية أولاً لاستخدام البوت:",
            reply_markup=sub_keyboard()
        )
        return

    welcome_msg = (
        "أهلاً بك! 🖐️\n\n"
        "أرسل لي رابط فيديو من أي منصة (تيك توك، انستغرام، يوتيوب، فيسبوك...) وسأقوم بتحميله لك فوراً."
    )
    bot.send_message(message.chat.id, welcome_msg)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        return

    if not is_subscribed(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ يجب عليك الاشتراك في القنوات أولاً لتتمكن من استخدام البوت:",
            reply_markup=sub_keyboard()
        )
        return

    current_time = time.time()
    if user_id in user_last_request:
        elapsed = current_time - user_last_request[user_id]
        if elapsed < COOLDOWN_TIME:
            wait_time = int(COOLDOWN_TIME - elapsed)
            bot.reply_to(message, f"⏱️ يرجى الانتظار {wait_time} ثوانٍ قبل إرسال رابط آخر.")
            return

    url = message.text.strip()

    if url.startswith("http://") or url.startswith("https://"):
        user_urls[user_id] = url
        user_last_request[user_id] = current_time
        bot.send_message(message.chat.id, "اختر نوع الملف الذي تريد تحميله:", reply_markup=download_keyboard())
    else:
        bot.send_message(message.chat.id, "❌ يرجى إرسال رابط صحيح يبدأ بـ http:// أو https://")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 أنت محظور.", show_alert=True)
        return

    if call.data == "check_sub":
        if is_subscribed(user_id):
            bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك!")
            bot.send_message(chat_id, "أرسل لي الرابط الآن وسأقوم بتحميله لك.")
        else:
            bot.answer_callback_query(call.id, "❌ لم تشترك في جميع القنوات بعد!", show_alert=True)
        return

    if call.data in ["dl_video", "dl_audio"]:
        url = user_urls.get(user_id)
        if not url:
            bot.send_message(chat_id, "❌ انتهت الجلسة، يرجى إرسال الرابط من جديد.")
            return

        is_audio = (call.data == "dl_audio")
        msg = bot.send_message(chat_id, "⏳ جاري جلب وتحميل المحتوى، انتظر لحظات...")

        filename = None
        download_success = False

        cookie_file = get_cookie_file()
        file_template = f"download_{user_id}_{int(time.time())}.%(ext)s"

        ydl_opts = {
            'outtmpl': file_template,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'max_filesize': MAX_FILE_SIZE_BYTES,
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'mweb', 'android_creator', 'tv']
                }
            }
        }

        # استخدام الكوكيز إن وجد لتفادي الحظر تماماً
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file

        if is_audio:
            ydl_opts['format'] = 'bestaudio/best'
        else:
            ydl_opts['format'] = 'best[filesize<48M]/best[height<=720]/best[height<=480]/best'

        # المحاولة الأولى عبر yt-dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                download_success = True
        except Exception as e:
            err_msg = str(e)
            print(f"yt-dlp failed: {err_msg}")
            
            # المحاولة الثانية عبر المحرك البديل
            try:
                filename = download_via_cobalt(url, is_audio=is_audio)
                download_success = True
            except Exception as cobalt_err:
                if "FileTooBig" in str(cobalt_err):
                    bot.edit_message_text("⚠️ الفيديو أضخم من 48MB ولا يمكن إرساله عبر التليجرام.", chat_id, msg.message_id)
                else:
                    bot.edit_message_text("❌ تعذر تحميل فيديو يوتيوب، يرجى تجربة فيديو آخر.", chat_id, msg.message_id)
                return

        if download_success and filename and os.path.exists(filename):
            try:
                file_size = os.path.getsize(filename)
                if file_size > MAX_FILE_SIZE_BYTES:
                    bot.edit_message_text("⚠️ الفيديو أضخم من 48MB ولا يمكن إرساله عبر التليجرام.", chat_id, msg.message_id)
                    return

                with open(filename, 'rb') as f:
                    if is_audio:
                        bot.send_audio(chat_id, f, caption="تم التحميل بنجاح 🎵")
                    else:
                        bot.send_video(chat_id, f, caption="تم التحميل بنجاح 🎬")

                bot.delete_message(chat_id, msg.message_id)
            except ApiTelegramException as e:
                bot.edit_message_text(f"❌ خطأ تليجرام: {e.description}", chat_id, msg.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ حدث خطأ أثناء الإرسال: {str(e)[:100]}", chat_id, msg.message_id)
            finally:
                if filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except Exception:
                        pass

bot.infinity_polling(skip_pending=True)
    
