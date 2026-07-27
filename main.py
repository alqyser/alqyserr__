import os
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# جلب بيانات البيئة من Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
ADMIN_ID_ENV = os.getenv("ADMIN_ID")

# تحويل آيدي الأدمن إلى رقم إن وجد
try:
    ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV else None
except ValueError:
    ADMIN_ID = None

bot = telebot.TeleBot(BOT_TOKEN)

# خزن مؤقت في الذاكرة
user_urls = {}
user_last_request = {}
banned_users = set()

# وقت الانتظار لمنع الإغراق (10 ثوانٍ بين كل طلب)
COOLDOWN_TIME = 10 

# ==================== دوال الحماية والتحقق ====================

def is_user_banned(user_id):
    return user_id in banned_users

def is_subscribed(user_id):
    # الأدمن مستثنى من الاشتراك الإجباري
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

# ==================== معالجات الأوامر ====================

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

# ==================== أوامر الإدارة للأدمن ====================

@bot.message_handler(commands=['ban'])
def ban_user_command(message):
    user_id = message.from_user.id
    if not ADMIN_ID or user_id != ADMIN_ID:
        return

    try:
        target_id = int(message.text.split()[1])
        banned_users.add(target_id)
        bot.reply_to(message, f"✅ تم حظر المستخدم `{target_id}` بنجاح.", parse_mode="Markdown")
    except (IndexError, ValueError):
        bot.reply_to(message, "⚠️ الاستخدام الصحيح: `/ban USER_ID`", parse_mode="Markdown")

@bot.message_handler(commands=['unban'])
def unban_user_command(message):
    user_id = message.from_user.id
    if not ADMIN_ID or user_id != ADMIN_ID:
        return

    try:
        target_id = int(message.text.split()[1])
        if target_id in banned_users:
            banned_users.remove(target_id)
            bot.reply_to(message, f"✅ تم إلغاء حظر المستخدم `{target_id}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ هذا المستخدم غير محظور بالأساس.")
    except (IndexError, ValueError):
        bot.reply_to(message, "⚠️ الاستخدام الصحيح: `/unban USER_ID`", parse_mode="Markdown")

# ==================== معالجة الرسائل والروابط ====================

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id

    # 1. فحص الحظر
    if is_user_banned(user_id):
        return

    # 2. فحص الاشتراك الإجباري
    if not is_subscribed(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ يجب عليك الاشتراك في القنوات أولاً لتتمكن من استخدام البوت:",
            reply_markup=sub_keyboard()
        )
        return

    # 3. حماية Anti-Spam (فحص المهل الزمنية)
    current_time = time.time()
    if user_id in user_last_request:
        elapsed = current_time - user_last_request[user_id]
        if elapsed < COOLDOWN_TIME:
            wait_time = int(COOLDOWN_TIME - elapsed)
            bot.reply_to(message, f"⏱️ يرجى الانتظار {wait_time} ثوانٍ قبل إرسال رابط آخر لتجنب الضغط على السيرفر.")
            return

    url = message.text.strip()

    # 4. فحص صحة المدخلات
    if url.startswith("http://") or url.startswith("https://"):
        user_urls[user_id] = url
        user_last_request[user_id] = current_time
        bot.send_message(message.chat.id, "اختر نوع الملف الذي تريد تحميله:", reply_markup=download_keyboard())
    else:
        bot.send_message(message.chat.id, "❌ يرجى إرسال رابط صحيح يبدأ بـ http:// أو https://")

# ==================== معالجة أزرار التحميل ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 أنت محظور من استخدام البوت.", show_alert=True)
        return

    if call.data == "check_sub":
        if is_subscribed(user_id):
            bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك! يمكنك الآن استخدام البوت.")
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

        file_template = f"download_{user_id}_{int(time.time())}.%(ext)s"
        filename = None

        # إعدادات الحماية والتخفي لـ yt-dlp
        ydl_opts = {
            'outtmpl': file_template,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,  # إغلاق الاتصال إذا لم يستجب السيرفر خلال 30 ثانية
            'max_filesize': 50 * 1024 * 1024,  # حد أقصى 50MB
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb']
                }
            }
        }

        if is_audio:
            ydl_opts['format'] = 'bestaudio/best'
        else:
            ydl_opts['format'] = 'best[filesize<50M]/best[height<=720]/best'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

            # فحص حجم الملف الفعلي على القرص
            if filename and os.path.exists(filename):
                file_size = os.path.getsize(filename)
                if file_size > 50 * 1024 * 1024:
                    bot.edit_message_text(
                        "⚠️ الفيديو المطلوب حجمه أكبر من 50 ميغابايت!\n"
                        "قوانين شركة تليجرام تمنع البوتات من إرسال ملفات تتجاوز هذا الحجم.",
                        chat_id,
                        msg.message_id
                    )
                    return

                with open(filename, 'rb') as f:
                    if is_audio:
                        bot.send_audio(chat_id, f, caption="تم التحميل بنجاح 🎵")
                    else:
                        bot.send_video(chat_id, f, caption="تم التحميل بنجاح 🎬")

                bot.delete_message(chat_id, msg.message_id)

        except yt_dlp.utils.FileTooBig:
            bot.edit_message_text(
                "⚠️ الفيديو المطلوب حجمه أكبر من 50 ميغابايت!\n"
                "قوانين تليجرام تمنع البوتات من إرسال ملفات تتجاوز هذا الحجم.",
                chat_id,
                msg.message_id
            )
        except Exception as e:
            error_msg = str(e)[:100]
            bot.edit_message_text(f"❌ حدث خطأ أثناء التحميل: {error_msg}", chat_id, msg.message_id)

        finally:
            # تنظيف آمن للحفاظ على المساحة ومنع امتلائها مهما حدث
            if filename and os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception as clean_err:
                    print(f"Error deleting file {filename}: {clean_err}")

# بدء التشغيل مع تجاهل الرسائل المتراكمة القديمة عند الاستئناف
bot.infinity_polling(skip_pending=True)
        
