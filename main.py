import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# جلب البيانات من متغيرات البيئة (Railway)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")

bot = telebot.TeleBot(BOT_TOKEN)

# قاموس مؤقت لحفظ روابط المستخدمين
user_urls = {}

# دالة التحقق من الاشتراك الإجباري
def is_subscribed(user_id):
    for ch in [CHANNEL_1, CHANNEL_2]:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                return False
        except Exception as e:
            print(f"Error checking sub for {ch}: {e}")
            return False
    return True

# لوحة أزرار الاشتراك الإجباري
def sub_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 القناة الأولى", url=f"https://t.me/{CHANNEL_1.replace('@', '')}"))
    markup.add(InlineKeyboardButton("📢 القناة الثانية", url=f"https://t.me/{CHANNEL_2.replace('@', '')}"))
    markup.add(InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub"))
    return markup

# لوحة اختيار نوع التحميل
def download_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎬 فيديو", callback_data="dl_video"),
        InlineKeyboardButton("🎵 صوت", callback_data="dl_audio")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في القنوات التالية أولاً لاستخدام البوت:",
            reply_markup=sub_keyboard()
        )
        return
    bot.send_message(message.chat.id, "أهلاً بك! 🖐️\nأرسل لي رابط الفيديو من أي منصة (تيك توك، انستغرام، يوتيوب...) وسأقوم بتحميله لك.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    if not is_subscribed(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ يجب عليك الاشتراك في القنوات أولاً لتتمكن من استخدام البوت:",
            reply_markup=sub_keyboard()
        )
        return

    url = message.text.strip()
    if url.startswith("http://") or url.startswith("https://"):
        user_urls[user_id] = url
        bot.send_message(message.chat.id, "اختر نوع الملف الذي تريد تحميله:", reply_markup=download_keyboard())
    else:
        bot.send_message(message.chat.id, "❌ يرجى إرسال رابط صحيح يبدأ بـ http أو https.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

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

        file_template = f"download_{user_id}.%(ext)s"
        
        ydl_opts = {
            'outtmpl': file_template,
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb']
                }
            }
        }

        if is_audio:
            ydl_opts['format'] = 'bestaudio/best'
        else:
            # طلب فيديو متكامل محتوياً على الصوت مباشرة
            ydl_opts['format'] = 'best[ext=mp4]/best'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

            with open(filename, 'rb') as f:
                if is_audio:
                    bot.send_audio(chat_id, f, caption="تم التحميل بنجاح 🎵")
                else:
                    bot.send_video(chat_id, f, caption="تم التحميل بنجاح 🎬")

            bot.delete_message(chat_id, msg.message_id)

            if os.path.exists(filename):
                os.remove(filename)

        except Exception as e:
            bot.edit_message_text(f"❌ حدث خطأ أثناء التحميل: {str(e)[:100]}", chat_id, msg.message_id)

bot.infinity_polling()
