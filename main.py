import os
import time
import requests
import urllib3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
import yt_dlp

# تعطيل تحذيرات SSL غير الموثوقة للمحركات البديلة
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# رفع مهلة الاتصال والرفع لتليجرام لمنع خطأ ReadTimeout أثناء إرسال الفيديوهات
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 300

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

COOLDOWN_TIME = 5 
MAX_FILE_SIZE_BYTES = 48 * 1024 * 1024  # 48MB

# ==================== تنظيف النصوص لتفادي خطأ ماركداون ====================

def clean_markdown(text):
    """تنظيف النصوص من الرموز الخاصة التي تسبب خطأ Parse Entities في تليجرام"""
    if not text:
        return ""
    for char in ['_', '*', '`', '[']:
        text = str(text).replace(char, ' ')
    return text.strip()

# ==================== دوال حفظ وتتبع المستخدمين ====================

def save_user(user_id):
    """حفظ أيدي المستخدم في ملف لحساب الإحصائيات"""
    try:
        if not os.path.exists("users.txt"):
            with open("users.txt", "w") as f:
                f.write(f"{user_id}\n")
            return
        
        with open("users.txt", "r") as f:
            users = f.read().splitlines()
        
        if str(user_id) not in users:
            with open("users.txt", "a") as f:
                f.write(f"{user_id}\n")
    except Exception as e:
        print(f"Error saving user: {e}")

def get_users_count():
    """حساب عدد المستخدمين الكلي"""
    if not os.path.exists("users.txt"):
        return 0
    try:
        with open("users.txt", "r") as f:
            users = set(f.read().splitlines())
        return len(users)
    except Exception:
        return 0

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

# ==================== لوحات الأزرار ====================

def start_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💡 طريقة الاستخدام", callback_data="help_usage"),
        InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/alqyser0")
    )
    return markup

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
    if os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 20:
        return "cookies.txt"
    elif YT_COOKIES_ENV:
        try:
            with open("cookies.txt", "w", encoding="utf-8") as f:
                f.write(YT_COOKIES_ENV)
            return "cookies.txt"
        except Exception as e:
            print(f"Error writing cookies: {e}")
    return None

# ==================== المحركات البديلة لليوتيوب ====================

def download_via_piped(url, is_audio=False):
    """محرك Piped المحدث مع تجاوز شهادات SSL المتضاربة"""
    video_id = None
    if "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in url:
        video_id = url.split("shorts/")[1].split("?")[0]
    
    if not video_id:
        raise Exception("Invalid YouTube ID")

    piped_instances = [
        "https://pipedapi.kavin.rocks",
        "https://api.piped.private.coffee",
        "https://pipedapi.mha.fi",
        "https://piped-api.garudalinux.org",
        "https://pipedapi.astro.swag.ph"
    ]

    for api in piped_instances:
        try:
            res = requests.get(f"{api}/streams/{video_id}", timeout=10, verify=False)
            if res.status_code == 200:
                data = res.json()
                file_url = None
                title = data.get("title", "مقطع يوتيوب")
                
                if is_audio:
                    audio_streams = data.get("audioStreams", [])
                    if audio_streams:
                        file_url = audio_streams[0].get("url")
                else:
                    video_streams = data.get("videoStreams", [])
                    for v in video_streams:
                        if v.get("quality") in ["720p", "480p", "360p"] and v.get("videoOnly") is False:
                            file_url = v.get("url")
                            break
                    if not file_url and video_streams:
                        file_url = video_streams[0].get("url")

                if file_url:
                    ext = "mp3" if is_audio else "mp4"
                    filename = f"download_piped_{int(time.time())}.{ext}"
                    with requests.get(file_url, stream=True, timeout=(15, 180), verify=False) as r:
                        r.raise_for_status()
                        downloaded = 0
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=16384):
                                if chunk:
                                    downloaded += len(chunk)
                                    if downloaded > MAX_FILE_SIZE_BYTES:
                                        f.close()
                                        if os.path.exists(filename):
                                            os.remove(filename)
                                        raise Exception("FileTooBig")
                                    f.write(chunk)
                    return filename, title
        except Exception as e:
            print(f"Piped instance {api} failed: {e}")
            continue

    raise Exception("Piped Engine Failed")

def download_via_invidious(url, is_audio=False):
    """محرك Invidious الاحتياطي المباشر"""
    video_id = None
    if "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in url:
        video_id = url.split("shorts/")[1].split("?")[0]

    if not video_id:
        raise Exception("Invalid YouTube ID")

    invidious_instances = [
        "https://yewtu.be",
        "https://invidious.privacydev.net",
        "https://invidious.drgns.space",
        "https://inv.tux.pizza"
    ]

    for inv in invidious_instances:
        try:
            res = requests.get(f"{inv}/api/v1/videos/{video_id}", timeout=10, verify=False)
            if res.status_code == 200:
                data = res.json()
                title = data.get("title", "مقطع يوتيوب")
                format_streams = data.get("formatStreams", [])
                file_url = None

                if is_audio:
                    adaptive = data.get("adaptiveFormats", [])
                    for a in adaptive:
                        if "audio" in a.get("type", ""):
                            file_url = a.get("url")
                            break
                else:
                    for f_stream in format_streams:
                        if f_stream.get("qualityLabel") in ["720p", "480p", "360p"]:
                            file_url = f_stream.get("url")
                            break
                    if not file_url and format_streams:
                        file_url = format_streams[0].get("url")

                if file_url:
                    ext = "mp3" if is_audio else "mp4"
                    filename = f"download_inv_{int(time.time())}.{ext}"
                    with requests.get(file_url, stream=True, timeout=(15, 180), verify=False) as r:
                        r.raise_for_status()
                        downloaded = 0
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=16384):
                                if chunk:
                                    downloaded += len(chunk)
                                    if downloaded > MAX_FILE_SIZE_BYTES:
                                        f.close()
                                        if os.path.exists(filename):
                                            os.remove(filename)
                                        raise Exception("FileTooBig")
                                    f.write(chunk)
                    return filename, title
        except Exception as e:
            print(f"Invidious instance {inv} failed: {e}")
            continue

    raise Exception("Invidious Engine Failed")

def download_via_cobalt(url, is_audio=False):
    """محرك Cobalt"""
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

    res = requests.post(api_url, json=payload, headers=headers, timeout=(10, 40), verify=False)
    data = res.json()
    
    if data.get("status") in ["redirect", "tunnel"]:
        file_url = data.get("url")
        ext = "mp3" if is_audio else "mp4"
        filename = f"download_yt_{int(time.time())}.{ext}"
        
        with requests.get(file_url, stream=True, timeout=(15, 180), verify=False) as r:
            r.raise_for_status()
            downloaded = 0
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=16384):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_SIZE_BYTES:
                            f.close()
                            if os.path.exists(filename):
                                os.remove(filename)
                            raise Exception("FileTooBig")
                        f.write(chunk)
        return filename, "مقطع فيديو"
    else:
        raise Exception(data.get("text", "Cobalt Error"))

# ==================== معالجة الأوامر ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    first_name = clean_markdown(message.from_user.first_name or "المستخدم")
    save_user(user_id)

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
        f"أهلاً بك يا **{first_name}** 👋\n\n"
        "📥 **بوت التحميل الشامل السريع**\n"
        "أرسل لي أي رابط من (يوتيوب، تيك توك، انستغرام، فيسبوك...) وسأقوم بتحميله لك فوراً بأعلى جودة ممتازة! ✨"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=start_keyboard())

@bot.message_handler(commands=['stats'])
def stats(message):
    user_id = message.from_user.id
    if ADMIN_ID and user_id == ADMIN_ID:
        total_users = get_users_count()
        bot.reply_to(message, f"📊 **إحصائيات البوت الحالية:**\n\n👤 عدد المستخدمين الكلي: `{total_users}` مستخدم", parse_mode="Markdown")
    else:
        bot.reply_to(message, "🚫 هذا الأمر مخصص لمالك البوت فقط.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    save_user(user_id)

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
        bot.send_message(message.chat.id, "🎬 اختر النوع الذي تريد تنزيله:", reply_markup=download_keyboard())
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

    if call.data == "help_usage":
        bot.answer_callback_query(
            call.id,
            "💡 طريقة الاستخدام:\n1. انسخ رابط أي فيديو من أي منصة.\n2. أرسله للبوت هنا مباشرة.\n3. اضغط على (فيديو) أو (صوت).",
            show_alert=True
        )
        return

    if call.data == "help_dev":
        bot.answer_callback_query(
            call.id,
            "👨‍💻 مطوّر البوت: @alqyser0",
            show_alert=True
        )
        return

    if call.data in ["dl_video", "dl_audio"]:
        url = user_urls.get(user_id)
        if not url:
            bot.send_message(chat_id, "❌ انتهت الجلسة، يرجى إرسال الرابط من جديد.")
            return

        is_audio = (call.data == "dl_audio")
        
        msg = bot.send_message(chat_id, "🔍 **جاري فحص وتجهيز الرابط...**", parse_mode="Markdown")

        filename = None
        video_title = "مقطع فيديو"
        download_success = False

        cookie_file = get_cookie_file()
        file_template = f"download_{user_id}_{int(time.time())}.%(ext)s"

        # إعدادات yt-dlp النظيفة والفعالة لعميل iOS و Android لمنع حظر الداتا سنتر
        ydl_opts = {
            'outtmpl': file_template,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'max_filesize': MAX_FILE_SIZE_BYTES,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android']
                }
            }
        }

        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file

        if is_audio:
            ydl_opts['format'] = 'bestaudio/best'
        else:
            ydl_opts['format'] = 'best[filesize<48M]/best[height<=720]/best[height<=480]/best'

        try:
            bot.edit_message_text("📥 **جاري جلب وتحميل الفيديو من المصدر...**", chat_id, msg.message_id, parse_mode="Markdown")
        except Exception:
            pass

        # 1️⃣ المحاولة الأولى عبر yt-dlp بنظام العميل الذكي ios / android
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                video_title = info.get("title", "مقطع فيديو")
                download_success = True
        except Exception as e:
            err_msg = str(e)
            print(f"yt-dlp primary attempt failed: {err_msg}")

            # 2️⃣ المحاولة الثانية عبر محرك Piped المحدث مع تجاوز SSL
            try:
                filename, video_title = download_via_piped(url, is_audio=is_audio)
                download_success = True
            except Exception as piped_err:
                print(f"Piped attempt failed: {piped_err}")
                
                # 3️⃣ المحاولة الثالثة عبر محرك Invidious الاحتياطي
                try:
                    filename, video_title = download_via_invidious(url, is_audio=is_audio)
                    download_success = True
                except Exception as inv_err:
                    print(f"Invidious attempt failed: {inv_err}")
                    
                    # 4️⃣ المحاولة الرابعة عبر محرك Cobalt
                    try:
                        filename, video_title = download_via_cobalt(url, is_audio=is_audio)
                        download_success = True
                    except Exception as cobalt_err:
                        print(f"Cobalt attempt failed: {cobalt_err}")
                        if "FileTooBig" in str(cobalt_err) or "FileTooBig" in str(piped_err):
                            bot.edit_message_text("⚠️ الفيديو أضخم من 48MB ولا يمكن إرساله عبر التليجرام.", chat_id, msg.message_id)
                        else:
                            bot.edit_message_text("❌ تعذر تحميل هذا المقطع حالياً، يرجى تجربة فيديو آخر.", chat_id, msg.message_id)
                        return

        if download_success and filename and os.path.exists(filename):
            try:
                file_size = os.path.getsize(filename)
                if file_size > MAX_FILE_SIZE_BYTES:
                    bot.edit_message_text("⚠️ الفيديو أضخم من 48MB ولا يمكن إرساله عبر التليجرام.", chat_id, msg.message_id)
                    return

                try:
                    bot.edit_message_text("📤 **جاري رفع الفيديو إلى التليجرام...**", chat_id, msg.message_id, parse_mode="Markdown")
                except Exception:
                    pass

                safe_title = clean_markdown(video_title[:60])
                bot_username = clean_markdown(bot.get_me().username)

                caption_text = (
                    f"🎬 **تم التحميل بنجاح!**\n\n"
                    f"📌 **العنوان:** {safe_title}\n\n"
                    f"🤖 **بواسطة:** @{bot_username}"
                )

                try:
                    with open(filename, 'rb') as f:
                        if is_audio:
                            bot.send_audio(chat_id, f, caption=caption_text, parse_mode="Markdown", timeout=300)
                        else:
                            bot.send_video(chat_id, f, caption=caption_text, parse_mode="Markdown", timeout=300)
                except Exception:
                    with open(filename, 'rb') as f:
                        if is_audio:
                            bot.send_audio(chat_id, f, caption=f"🎬 تم التحميل بنجاح!\n📌 العنوان: {video_title[:60]}\n🤖 بواسطة: @{bot.get_me().username}")
                        else:
                            bot.send_video(chat_id, f, caption=f"🎬 تم التحميل بنجاح!\n📌 العنوان: {video_title[:60]}\n🤖 بواسطة: 
