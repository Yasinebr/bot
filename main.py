import logging
import random
import json
from uuid import uuid4
from datetime import datetime, timedelta
import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
)

# --- تنظیمات پایه ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "7761003160:AAGtSTunegKVm2BukVYl8BOda3woy8P_vgQ"

# --- حالت‌های گفتگو ---
CHOOSING, PLAYING, WAITING_FOR_RESPONSE = range(3)

# --- دیتابیس ساده ---
games_db = {}
users_db = {}
responses_db = []
user_challenges = {}  # برای مدیریت چالش‌های کاربران

# --- سوالات ---
QUESTIONS = {
    "truth": [
        "آخرین پیام پاک شده‌ات چی بود؟",
        "اگر قرار بود یک نفر از گروه حذف کنی کیه؟",
        "بدترین ویژگی خودت چیه؟",
        "رازیه که تا حالا به کسی نگفتی؟",
        "یک دروغی که اخیراً گفتی؟"
    ],
    "dare": [
        "عکس سلفت رو بفرست!",
        "برای 1 دقیقه آواز بخون!",
        "پروفایلت رو 24 ساعت عوض کن!",
        "یک جمله با صدای بلند فریاد بزن!",
        "استاتوس توهین آمیز بذار!"
    ]
}


# --- توابع کمکی ---
async def generate_invite_link(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    unique_id = str(uuid4())
    users_db[unique_id] = user_id
    bot_username = (await context.bot.get_me()).username
    return f"https://t.me/{bot_username}?start={unique_id}"


def save_response(user_id: int, question_type: str, question: str, answer: str):
    """ذخیره پاسخ کاربر در دیتابیس"""
    try:
        # افزودن پاسخ جدید
        responses_db.append({
            "user_id": user_id,
            "type": question_type,
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat()
        })

        # ذخیره در فایل
        with open("responses.json", "w", encoding="utf-8") as f:
            json.dump(responses_db, f, ensure_ascii=False, indent=2)

        logger.info(f"Response saved for user {user_id}, type: {question_type}")
        return True
    except Exception as e:
        logger.error(f"Error saving response: {e}")
        return False


async def send_challenge_message(context: ContextTypes.DEFAULT_TYPE, user_id: int, question: str, challenge_type: str):
    """ارسال پیام چالش به کاربر و تنظیم وضعیت"""
    challenge_id = str(uuid4())

    # انتخاب دکمه مناسب بر اساس نوع چالش
    if challenge_type == "truth":
        keyboard = [
            [InlineKeyboardButton("ذخیره پاسخ 💾", callback_data=f"save_truth_{challenge_id}")],
            [InlineKeyboardButton("بازگشت ◀️", callback_data="back")]
        ]
        title = "🔍 حقیقت"
    else:  # dare
        keyboard = [
            [InlineKeyboardButton("انجام دادم ✅", callback_data=f"complete_dare_{challenge_id}")],
            [InlineKeyboardButton("بازگشت ◀️", callback_data="back")]
        ]
        title = "💥 جرئت"

    # ارسال پیام با دکمه‌های مناسب
    message = await context.bot.send_message(
        chat_id=user_id,
        text=f"{title}:\n{question}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # ذخیره اطلاعات چالش
    user_challenges[user_id] = {
        "challenge_id": challenge_id,
        "question": question,
        "type": challenge_type,
        "message_id": message.message_id,
        "answered": False,
        "has_replied": False,
        "answer": None
    }

    return message.message_id


# --- توابع رسیدگی به چالش‌ها ---
async def handle_truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب حقیقت"""
    user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
    question = random.choice(QUESTIONS["truth"])

    # ارسال پیام چالش
    message_id = await send_challenge_message(context, user_id, question, "truth")

    # ارسال راهنمای پاسخ
    await context.bot.send_message(
        chat_id=user_id,
        text="⚠️ لطفاً برای پاسخ به این سوال:\n1. روی پیام بالا ریپلای کنید\n2. پاسخ خود را بنویسید\n3. سپس دکمه 'ذخیره پاسخ' را بزنید",
        reply_to_message_id=message_id
    )

    return WAITING_FOR_RESPONSE


async def handle_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب جرئت"""
    user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
    question = random.choice(QUESTIONS["dare"])

    # ارسال پیام چالش
    message_id = await send_challenge_message(context, user_id, question, "dare")

    # ارسال راهنمای پاسخ
    await context.bot.send_message(
        chat_id=user_id,
        text="⚠️ لطفاً برای پاسخ به این چالش:\n1. روی پیام بالا ریپلای کنید\n2. پاسخ/عکس/ویدئو خود را ارسال کنید\n3. سپس دکمه 'انجام دادم' را بزنید",
        reply_to_message_id=message_id
    )

    return WAITING_FOR_RESPONSE


async def handle_save_truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره پاسخ به چالش حقیقت"""
    query = update.callback_query
    user_id = query.from_user.id
    challenge_id = query.data.split("_")[2]

    if user_id in user_challenges and user_challenges[user_id]["challenge_id"] == challenge_id:
        if user_challenges[user_id]["has_replied"]:
            # ذخیره پاسخ
            save_response(
                user_id=user_id,
                question_type="truth",
                question=user_challenges[user_id]["question"],
                answer=user_challenges[user_id]["answer"]
            )

            # بروزرسانی پیام
            await query.edit_message_text(
                text=f"✅ پاسخ شما ثبت شد!\nسوال: {user_challenges[user_id]['question']}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("بازگشت به منوی اصلی ◀️", callback_data="back")]
                ])
            )

            # پاک کردن اطلاعات چالش
            del user_challenges[user_id]
            return CHOOSING
        else:
            await query.answer("⚠️ لطفاً ابتدا به پیام چالش ریپلای کنید!", show_alert=True)
            return WAITING_FOR_RESPONSE

    await query.answer("مشکلی پیش آمد، لطفاً دوباره تلاش کنید.", show_alert=True)
    return CHOOSING


async def handle_complete_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تکمیل چالش جرئت"""
    query = update.callback_query
    user_id = query.from_user.id
    challenge_id = query.data.split("_")[2]

    if user_id in user_challenges and user_challenges[user_id]["challenge_id"] == challenge_id:
        if user_challenges[user_id]["has_replied"]:
            # ذخیره پاسخ
            save_response(
                user_id=user_id,
                question_type="dare",
                question=user_challenges[user_id]["question"],
                answer="[انجام شد]"  # یا می‌توانید اطلاعات بیشتری ذخیره کنید
            )

            # بروزرسانی پیام
            await query.edit_message_text(
                text=f"✅ چالش شما ثبت شد!\nچالش: {user_challenges[user_id]['question']}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("بازگشت به منوی اصلی ◀️", callback_data="back")]
                ])
            )

            # پاک کردن اطلاعات چالش
            del user_challenges[user_id]
            return CHOOSING
        else:
            await query.answer("⚠️ لطفاً ابتدا به پیام چالش ریپلای کنید!", show_alert=True)
            return WAITING_FOR_RESPONSE

    await query.answer("مشکلی پیش آمد، لطفاً دوباره تلاش کنید.", show_alert=True)
    return CHOOSING


# --- مدیریت پاسخ‌ها ---
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پاسخ‌های کاربر به چالش‌ها"""
    user_id = update.message.from_user.id

    # بررسی اینکه آیا پیام ریپلای است و به چالش مربوطه پاسخ می‌دهد
    if update.message.reply_to_message and user_id in user_challenges:
        challenge = user_challenges[user_id]
        if update.message.reply_to_message.message_id == challenge["message_id"]:
            # ثبت پاسخ در حافظه موقت
            if update.message.text:
                user_challenges[user_id]["answer"] = update.message.text
            elif update.message.photo:
                # برای تصویر، آخرین (بزرگترین) سایز را ذخیره می‌کنیم
                user_challenges[user_id]["answer"] = f"[تصویر: {update.message.photo[-1].file_id}]"
            elif update.message.video:
                user_challenges[user_id]["answer"] = f"[ویدئو: {update.message.video.file_id}]"
            elif update.message.voice:
                user_challenges[user_id]["answer"] = f"[صدا: {update.message.voice.file_id}]"
            else:
                user_challenges[user_id]["answer"] = "[محتوای رسانه‌ای]"

            # علامت‌گذاری به عنوان پاسخ داده شده
            user_challenges[user_id]["has_replied"] = True

            # تأیید دریافت پاسخ با دکمه مناسب
            challenge_type = user_challenges[user_id]["type"]
            challenge_id = user_challenges[user_id]["challenge_id"]

            if challenge_type == "truth":
                button_text = "ذخیره پاسخ 💾"
                callback_data = f"save_truth_{challenge_id}"
            else:  # dare
                button_text = "انجام دادم ✅"
                callback_data = f"complete_dare_{challenge_id}"

            # ارسال پیام با دکمه جدید (با شناسه callback مناسب)
            await update.message.reply_text(
                f"✅ پاسخ شما دریافت شد! حالا روی دکمه زیر کلیک کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(button_text, callback_data=callback_data)]
                ])
            )

            return WAITING_FOR_RESPONSE

    # اگر پیام ریپلای نبود یا به چالش مربوط نبود
    if user_id in user_challenges:
        await update.message.reply_text(
            "⚠️ لطفاً برای پاسخ به چالش، روی پیام چالش ریپلای کنید.",
            reply_to_message_id=user_challenges[user_id]["message_id"]
        )

    return WAITING_FOR_RESPONSE


# --- دستورات اصلی ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات و یا پذیرش دعوت به بازی دو نفره"""
    if context.args:
        inviter_id = users_db.get(context.args[0])
        if inviter_id:
            await start_private_game(update, context, inviter_id, update.effective_user.id)
            return PLAYING

    keyboard = [
        [
            InlineKeyboardButton("حقیقت 🎲", callback_data="truth"),
            InlineKeyboardButton("جرئت 💣", callback_data="dare")
        ],
        [
            InlineKeyboardButton("بازی دو نفره 👥", callback_data="invite"),
            InlineKeyboardButton(
                "اضافه کردن به گروه ➕",
                switch_inline_query=""
            )
        ]
    ]

    await update.message.reply_text(
        "🎮 به بازی جرئت یا حقیقت خوش آمدید!\n"
        "می‌توانید در گروه اضافه کنید یا در چت خصوصی بازی کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING


# --- مدیریت بازی دو نفره ---
async def start_private_game(update: Update, context: ContextTypes.DEFAULT_TYPE, inviter_id: int, invitee_id: int):
    """شروع بازی دو نفره"""
    game_id = str(uuid4())
    games_db[game_id] = {
        "players": [inviter_id, invitee_id],
        "current_turn": inviter_id,
        "questions": []
    }

    for player in games_db[game_id]["players"]:
        await context.bot.send_message(
            chat_id=player,
            text="🎉 بازی دو نفره شروع شد!\n"
                 "هر بازیکن به نوبت سوال دریافت می‌کند.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("شروع بازی", callback_data=f"start_{game_id}")],
                [InlineKeyboardButton("لغو بازی", callback_data="cancel")]
            ]))


async def handle_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت شروع بازی دو نفره"""
    query = update.callback_query
    game_id = query.data.split("_")[1]
    game = games_db.get(game_id)

    if game:
        question_type = random.choice(["truth", "dare"])
        question = random.choice(QUESTIONS[question_type])
        game["questions"].append(question)

        for player in game["players"]:
            await context.bot.send_message(
                chat_id=player,
                text=f"🎯 {'حقیقت' if question_type == 'truth' else 'جرئت'}:\n{question}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("پاسخ دادم ✅", callback_data=f"answered_{game_id}")],
                    [InlineKeyboardButton("لغو بازی ❌", callback_data="cancel")]
                ]))


async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد لینک دعوت برای بازی دو نفره"""
    query = update.callback_query
    invite_link = await generate_invite_link(context, query.from_user.id)
    await query.edit_message_text(
        text=f"📩 لینک دعوت اختصاصی شما:\n{invite_link}\n\n"
             "این لینک را برای دوستتان بفرستید تا بازی دو نفره شروع شود!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بازگشت به منوی اصلی ◀️", callback_data="back")]
        ]))


# --- مدیریت دکمه‌ها ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک بر روی دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    logger.info(f"Button pressed: {query.data} by user {user_id}")

    # دکمه‌های اصلی
    if query.data == "truth":
        return await handle_truth(update, context)
    elif query.data == "dare":
        return await handle_dare(update, context)
    elif query.data == "invite":
        await handle_invite(update, context)
        return CHOOSING
    elif query.data.startswith("start_"):
        await handle_game_start(update, context)
        return PLAYING
    elif query.data == "cancel":
        await query.edit_message_text("❌ بازی لغو شد")
        return CHOOSING

    # دکمه بازگشت
    elif query.data == "back":
        # حذف چالش فعلی اگر وجود داشته باشد
        if user_id in user_challenges:
            del user_challenges[user_id]

        # بازگشت به منوی اصلی با دکمه‌های جدید
        await query.edit_message_text(
            text="به منوی اصلی بازگشتید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("حقیقت 🎲", callback_data="truth"),
                 InlineKeyboardButton("جرئت 💣", callback_data="dare")],
                [InlineKeyboardButton("بازی دو نفره 👥", callback_data="invite")]
            ])
        )
        return CHOOSING

    # دکمه ذخیره پاسخ حقیقت
    elif query.data.startswith("save_truth_"):
        challenge_id = query.data.split("_")[2]
        logger.info(f"Saving truth response for challenge {challenge_id}")

        if user_id in user_challenges and user_challenges[user_id]["challenge_id"] == challenge_id:
            if user_challenges[user_id]["has_replied"]:
                # ذخیره پاسخ
                save_response(
                    user_id=user_id,
                    question_type="truth",
                    question=user_challenges[user_id]["question"],
                    answer=user_challenges[user_id]["answer"]
                )

                # بروزرسانی پیام
                await query.edit_message_text(
                    text=f"✅ پاسخ شما ثبت شد!\nسوال: {user_challenges[user_id]['question']}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("بازگشت به منوی اصلی ◀️", callback_data="back")]
                    ])
                )

                # پاک کردن اطلاعات چالش
                del user_challenges[user_id]
                return CHOOSING
            else:
                await query.answer("⚠️ لطفاً ابتدا به پیام چالش ریپلای کنید!", show_alert=True)
                return WAITING_FOR_RESPONSE
        else:
            logger.warning(f"Challenge not found for user {user_id}, challenge_id {challenge_id}")
            await query.answer("مشکلی پیش آمد، لطفاً دوباره تلاش کنید.", show_alert=True)
            return CHOOSING

    # دکمه تکمیل چالش جرئت
    elif query.data.startswith("complete_dare_"):
        challenge_id = query.data.split("_")[2]
        logger.info(f"Completing dare challenge {challenge_id}")

        if user_id in user_challenges and user_challenges[user_id]["challenge_id"] == challenge_id:
            if user_challenges[user_id]["has_replied"]:
                # ذخیره پاسخ
                save_response(
                    user_id=user_id,
                    question_type="dare",
                    question=user_challenges[user_id]["question"],
                    answer=user_challenges[user_id]["answer"] if user_challenges[user_id]["answer"] else "[انجام شد]"
                )

                # بروزرسانی پیام
                await query.edit_message_text(
                    text=f"✅ چالش شما ثبت شد!\nچالش: {user_challenges[user_id]['question']}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("بازگشت به منوی اصلی ◀️", callback_data="back")]
                    ])
                )

                # پاک کردن اطلاعات چالش
                del user_challenges[user_id]
                return CHOOSING
            else:
                await query.answer("⚠️ لطفاً ابتدا به پیام چالش ریپلای کنید!", show_alert=True)
                return WAITING_FOR_RESPONSE
        else:
            logger.warning(f"Challenge not found for user {user_id}, challenge_id {challenge_id}")
            await query.answer("مشکلی پیش آمد، لطفاً دوباره تلاش کنید.", show_alert=True)
            return CHOOSING

    # اگر هیچ کدام از حالت‌های بالا نبود
    logger.warning(f"Unknown callback data: {query.data}")
    await query.answer("دکمه نامعتبر یا منقضی شده", show_alert=True)
    return CHOOSING


# --- مدیریت اینلاین کوئری ---
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کوئری‌های اینلاین برای اضافه کردن ربات به گروه"""
    query = update.inline_query.query
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="اضافه کردن ربات به گروه",
            description="این ربات را به گروه مورد نظر خود اضافه کنید",
            input_message_content=InputTextMessageContent(
                "لطفاً این ربات را به گروه مورد نظر خود اضافه کنید"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("شروع بازی", callback_data="start")]
            ])
        )
    ]
    await update.inline_query.answer(results)


# --- بخش راهنمای استفاده ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش راهنمای استفاده از ربات"""
    help_text = """
📚 راهنمای استفاده از ربات جرئت یا حقیقت:

🎮 روش‌های بازی:
1. در گروه:
   - ربات را به گروه اضافه کنید
   - از دکمه‌های 'حقیقت' یا 'جرئت' استفاده کنید
   - سوال تصادفی برای همه نمایش داده می‌شود

2. بازی دو نفره در پیوی:
   - روی 'بازی دو نفره' کلیک کنید
   - لینک دعوت را برای دوستتان بفرستید
   - پس از پیوستن دوست، بازی شروع می‌شود

🛠️ امکانات ربات:
- ذخیره پاسخ‌ها برای مراجعه بعدی
- امکان لغو بازی در هر مرحله
- انتخاب کاملا تصادفی سوالات
- رابط کاربری آسان با دکمه‌های شفاف

📌 نکات مهم:
- در بازی دو نفره، هر بازیکن به نوبت سوال دریافت می‌کند
- پاسخ‌ها فقط برای شما و دوستتان قابل مشاهده است
- می‌توانید بازی را در هر مرحله لغو کنید

برای شروع بازی /start را بزنید یا از دکمه‌های زیر استفاده کنید:
"""

    keyboard = [
        [
            InlineKeyboardButton("شروع بازی 🎮", callback_data="start_game"),
            InlineKeyboardButton(
                "اضافه کردن به گروه ➕",
                switch_inline_query=""
            )
        ]
    ]

    await update.message.reply_text(
        text=help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو عملیات جاری"""
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END


# --- تنظیم دستورات بات ---
async def post_init(application):
    """تنظیم دستورات بات"""
    await application.bot.set_my_commands([
        BotCommand("start", "شروع بازی"),
        BotCommand("help", "راهنمای کامل استفاده از ربات"),
        BotCommand("cancel", "لغو بازی جاری")
    ])


# اطمینان از بارگیری پاسخ‌های قبلی در شروع برنامه
def load_responses():
    """بارگیری پاسخ‌های ذخیره شده قبلی"""
    global responses_db
    try:
        with open("responses.json", "r", encoding="utf-8") as f:
            responses_db = json.load(f)
        logger.info(f"Loaded {len(responses_db)} responses from database")
    except FileNotFoundError:
        logger.info("No previous responses database found. Starting fresh.")
        responses_db = []
    except Exception as e:
        logger.error(f"Error loading responses: {e}")
        responses_db = []


# --- تعریف متغیرهای جدید برای بازی گروهی ---
group_games = {}  # مدیریت بازی‌های گروهی
JOINED_GAME = 4  # حالت جدید برای پیوستن به بازی گروهی


# --- توابع مدیریت بازی گروهی ---
async def start_group_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آغاز بازی جدید در گروه"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # بررسی آیا پیام در گروه ارسال شده است
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return ConversationHandler.END

    # بررسی آیا بازی قبلی در حال اجراست
    if chat_id in group_games and group_games[chat_id]["status"] == "active":
        await update.message.reply_text(
            "⚠️ یک بازی در حال حاضر در این گروه در حال اجراست.\n"
            "برای پیوستن به بازی از دستور /join استفاده کنید."
        )
        return ConversationHandler.END

    # ایجاد بازی جدید
    group_games[chat_id] = {
        "creator": user_id,
        "status": "waiting",  # وضعیت‌های ممکن: waiting, active, finished
        "players": [user_id],
        "current_player_index": 0,
        "rounds": 0,
        "max_rounds": 10,  # تعداد دورهای پیش‌فرض
        "join_time": datetime.now() + timedelta(minutes=1),  # زمان پیوستن به بازی - کاهش به 1 دقیقه
        "questions": []
    }

    # دریافت نام کاربر ایجاد کننده
    user = update.effective_user
    creator_name = user.first_name
    if user.last_name:
        creator_name += f" {user.last_name}"

    # ارسال پیام اعلان شروع بازی
    keyboard = [
        [InlineKeyboardButton("پیوستن به بازی 🎮", callback_data="join_game")],
        [InlineKeyboardButton("شروع بازی ▶️", callback_data="begin_game")],
        [InlineKeyboardButton("لغو بازی ❌", callback_data="cancel_group_game")]
    ]

    message = await update.message.reply_text(
        f"🎮 کاربر {creator_name} یک بازی جرئت یا حقیقت ایجاد کرد!\n\n"
        "👥 برای پیوستن به بازی روی دکمه زیر کلیک کنید یا دستور /join را بزنید\n"
        f"⏱ زمان پیوستن به بازی: 1 دقیقه\n\n"  # تغییر پیام برای نشان دادن 1 دقیقه
        f"بازیکنان (1): {creator_name}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # ذخیره شناسه پیام برای بروزرسانی‌های بعدی
    group_games[chat_id]["announcement_message_id"] = message.message_id

    # تنظیم تایمر برای شروع خودکار بازی پس از پایان زمان پیوستن
    context.job_queue.run_once(
        auto_start_game,
        60,  # 1 دقیقه - تغییر از 300 ثانیه به 60 ثانیه
        chat_id=chat_id,
        name=f"start_game_{chat_id}"
    )

    return ConversationHandler.END



async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوستن به بازی گروهی با دستور"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # بررسی آیا بازی در گروه وجود دارد
    if chat_id not in group_games or group_games[chat_id]["status"] != "waiting":
        await update.message.reply_text(
            "❌ در حال حاضر بازی فعالی برای پیوستن وجود ندارد.\n"
            "برای شروع بازی جدید از دستور /startgame استفاده کنید."
        )
        return ConversationHandler.END

    # بررسی آیا کاربر قبلاً به بازی پیوسته است
    if user_id in group_games[chat_id]["players"]:
        await update.message.reply_text(
            "✅ شما قبلاً به این بازی پیوسته‌اید."
        )
        return ConversationHandler.END

    # افزودن کاربر به لیست بازیکنان
    group_games[chat_id]["players"].append(user_id)

    # دریافت نام کاربر
    user = update.effective_user
    player_name = user.first_name
    if user.last_name:
        player_name += f" {user.last_name}"

    # بروزرسانی پیام اعلان با لیست جدید بازیکنان
    await update_player_list(context, chat_id)

    # تأیید پیوستن به بازی
    await update.message.reply_text(
        f"✅ کاربر {player_name} به بازی پیوست!"
    )

    return ConversationHandler.END


async def join_game_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوستن به بازی گروهی با دکمه"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    user_id = query.from_user.id

    # بررسی آیا بازی در گروه وجود دارد
    if chat_id not in group_games:
        await query.answer("❌ در حال حاضر بازی فعالی برای پیوستن وجود ندارد.", show_alert=True)
        return

    if group_games[chat_id]["status"] != "waiting":
        await query.answer("⚠️ مهلت پیوستن به بازی به پایان رسیده است.", show_alert=True)
        return

    # بررسی آیا کاربر قبلاً به بازی پیوسته است
    if user_id in group_games[chat_id]["players"]:
        await query.answer("✅ شما قبلاً به این بازی پیوسته‌اید.", show_alert=True)
        return

    # افزودن کاربر به لیست بازیکنان
    group_games[chat_id]["players"].append(user_id)

    # دریافت نام کاربر
    user = query.from_user
    player_name = user.first_name
    if user.last_name:
        player_name += f" {user.last_name}"

    # بروزرسانی پیام اعلان با لیست جدید بازیکنان
    await update_player_list(context, chat_id)

    # تأیید پیوستن به بازی
    await query.message.reply_text(
        f"✅ کاربر {player_name} به بازی پیوست!"
    )


# --- اصلاح تابع شروع بازی با دکمه ---
async def begin_game_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بازی با کلیک روی دکمه شروع بازی"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    user_id = query.from_user.id

    # بررسی وجود بازی
    if chat_id not in group_games:
        await query.answer("❌ بازی‌ای برای شروع وجود ندارد.", show_alert=True)
        return

    game = group_games[chat_id]

    # بررسی اینکه آیا کاربر سازنده بازی است
    if user_id != game["creator"]:
        await query.answer("⚠️ فقط ایجاد کننده بازی می‌تواند بازی را شروع کند.", show_alert=True)
        return

    # بررسی تعداد بازیکنان
    if len(game["players"]) < 2:
        await query.answer("⚠️ برای شروع بازی حداقل به 2 بازیکن نیاز است.", show_alert=True)
        return

    # شروع بازی
    await begin_group_game(context, chat_id, by_button=True)

async def update_player_list(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """بروزرسانی لیست بازیکنان در پیام اعلان"""
    if chat_id not in group_games:
        return

    game = group_games[chat_id]

    # جمع‌آوری اسامی بازیکنان
    player_names = []
    for player_id in game["players"]:
        try:
            user = await context.bot.get_chat_member(chat_id, player_id)
            name = user.user.first_name
            if user.user.last_name:
                name += f" {user.user.last_name}"
            player_names.append(name)
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            player_names.append(f"کاربر #{player_id}")

    # ساخت متن جدید
    join_time_str = game["join_time"].strftime("%H:%M:%S")
    players_str = "\n".join([f"{i + 1}. {name}" for i, name in enumerate(player_names)])

    keyboard = [
        [InlineKeyboardButton("پیوستن به بازی 🎮", callback_data="join_game")],
        [InlineKeyboardButton("شروع بازی ▶️", callback_data="begin_game")],
        [InlineKeyboardButton("لغو بازی ❌", callback_data="cancel_group_game")]
    ]

    # بروزرسانی پیام
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game["announcement_message_id"],
            text=f"🎮 بازی جرئت یا حقیقت ایجاد شده است!\n\n"
                 f"👥 برای پیوستن به بازی روی دکمه زیر کلیک کنید یا دستور /join را بزنید\n"
                 f"⏱ پایان زمان پیوستن: {join_time_str}\n\n"
                 f"بازیکنان ({len(player_names)}):\n{players_str}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error updating player list: {e}")



async def auto_start_game(context: ContextTypes.DEFAULT_TYPE):
    """شروع خودکار بازی پس از پایان زمان پیوستن"""
    job = context.job
    chat_id = job.chat_id

    if chat_id not in group_games or group_games[chat_id]["status"] != "waiting":
        return

    # شروع بازی اگر حداقل 2 بازیکن وجود داشته باشد
    if len(group_games[chat_id]["players"]) >= 2:
        await begin_group_game(context, chat_id)
    else:
        # لغو بازی در صورت کمبود بازیکن
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ تعداد بازیکنان کافی نیست (حداقل 2 نفر). بازی لغو شد."
        )
        del group_games[chat_id]


async def begin_group_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int, by_button: bool = False):
    """شروع بازی گروهی پس از پیوستن بازیکنان"""
    if chat_id not in group_games:
        return

    game = group_games[chat_id]

    # بررسی تعداد بازیکنان (حداقل 2 نفر)
    if len(game["players"]) < 2:
        if by_button:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ برای شروع بازی حداقل به 2 بازیکن نیاز است."
            )
        return

    # تغییر وضعیت بازی به فعال
    game["status"] = "active"

    # حذف تایمر خودکار اگر موجود باشد
    current_jobs = context.job_queue.get_jobs_by_name(f"start_game_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()

    # اعلام شروع بازی
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎬 بازی جرئت یا حقیقت آغاز شد!\n\n"
             "قوانین بازی:\n"
             "1. هر بازیکن به نوبت انتخاب می‌کند: جرئت یا حقیقت\n"
             "2. پس از پاسخ به سوال، نوبت به بازیکن بعدی می‌رسد\n"
             "3. بازی پس از اتمام تعداد دورها یا دستور /endgame پایان می‌یابد"
    )

    # شروع نوبت اولین بازیکن
    await start_player_turn(context, chat_id)


async def start_player_turn(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """شروع نوبت بازیکن فعلی"""
    if chat_id not in group_games or group_games[chat_id]["status"] != "active":
        return

    game = group_games[chat_id]
    player_index = game["current_player_index"]
    player_id = game["players"][player_index]

    # دریافت نام کاربر
    try:
        user = await context.bot.get_chat_member(chat_id, player_id)
        player_name = user.user.first_name
        if user.user.last_name:
            player_name += f" {user.user.last_name}"
    except:
        player_name = f"کاربر #{player_id}"

    # ایجاد دکمه‌های انتخاب
    keyboard = [
        [
            InlineKeyboardButton("حقیقت 🎲", callback_data=f"group_truth_{player_id}"),
            InlineKeyboardButton("جرئت 💣", callback_data=f"group_dare_{player_id}")
        ]
    ]

    # ارسال پیام نوبت
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎯 نوبت {player_name} است!\n\nلطفاً یکی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_group_truth_dare(update: Update, context: ContextTypes.DEFAULT_TYPE, choice_type: str):
    """مدیریت انتخاب جرئت یا حقیقت در بازی گروهی"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    callback_data = query.data  # group_truth_12345678 یا group_dare_12345678
    target_user_id = int(callback_data.split("_")[2])

    # بررسی اینکه آیا کاربر مجاز به انتخاب است
    if chat_id not in group_games or group_games[chat_id]["status"] != "active":
        await query.message.reply_text("❌ بازی فعالی در این گروه وجود ندارد.")
        return

    game = group_games[chat_id]
    current_player_id = game["players"][game["current_player_index"]]

    # فقط کاربر فعلی یا مدیر بازی می‌تواند انتخاب کند
    if query.from_user.id != current_player_id and query.from_user.id != game["creator"]:
        await query.answer("این نوبت شما نیست!", show_alert=True)
        return

    # انتخاب سوال تصادفی
    if choice_type == "truth":
        question = random.choice(QUESTIONS["truth"])
        type_text = "حقیقت 🎲"
    else:  # dare
        question = random.choice(QUESTIONS["dare"])
        type_text = "جرئت 💣"

    # دریافت نام کاربر
    try:
        user = await context.bot.get_chat_member(chat_id, current_player_id)
        player_name = user.user.first_name
        if user.user.last_name:
            player_name += f" {user.user.last_name}"
    except:
        player_name = f"کاربر #{current_player_id}"

    # ارسال سوال
    keyboard = [
        [InlineKeyboardButton("پاسخ دادم ✅", callback_data=f"group_answered_{current_player_id}")],
        [InlineKeyboardButton("نوبت بعدی ⏭", callback_data="next_player")]
    ]

    await query.edit_message_text(
        text=f"👤 {player_name} {type_text} را انتخاب کرد!\n\n"
             f"سوال:\n{question}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # ذخیره سوال در تاریخچه بازی
    game["questions"].append({
        "player": current_player_id,
        "player_name": player_name,
        "type": choice_type,
        "question": question,
        "answered": False
    })


async def handle_group_answered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پاسخ به سوال در بازی گروهی"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    callback_data = query.data  # group_answered_12345678
    target_user_id = int(callback_data.split("_")[2])

    # بررسی اینکه آیا کاربر مجاز به پاسخ است
    if chat_id not in group_games or group_games[chat_id]["status"] != "active":
        return

    game = group_games[chat_id]
    current_player_id = game["players"][game["current_player_index"]]

    # فقط کاربر فعلی یا مدیر بازی می‌تواند اعلام کند که پاسخ داده شد
    if query.from_user.id != current_player_id and query.from_user.id != game["creator"]:
        await query.answer("این نوبت شما نیست!", show_alert=True)
        return

    # علامت گذاری سوال به عنوان پاسخ داده شده
    game["questions"][-1]["answered"] = True

    # بروزرسانی پیام برای نشان دادن پاسخ
    current_text = query.message.text
    keyboard = [
        [InlineKeyboardButton("نوبت بعدی ⏭", callback_data="next_player")]
    ]

    await query.edit_message_text(
        text=f"{current_text}\n\n✅ پاسخ داده شد!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def next_player_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتقال نوبت به بازیکن بعدی"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id

    if chat_id not in group_games or group_games[chat_id]["status"] != "active":
        return

    game = group_games[chat_id]

    # فقط کاربر فعلی یا مدیر بازی می‌تواند نوبت را منتقل کند
    current_player_id = game["players"][game["current_player_index"]]
    if query.from_user.id != current_player_id and query.from_user.id != game["creator"]:
        await query.answer("شما نمی‌توانید نوبت را تغییر دهید!", show_alert=True)
        return

    # افزایش شمارنده بازیکن و رسیدن به بازیکن بعدی
    game["current_player_index"] = (game["current_player_index"] + 1) % len(game["players"])

    # بررسی اتمام یک دور کامل
    if game["current_player_index"] == 0:
        game["rounds"] += 1

        # بررسی پایان بازی
        if game["rounds"] >= game["max_rounds"]:
            await end_group_game(context, chat_id)
            return

    # شروع نوبت بازیکن بعدی
    await start_player_turn(context, chat_id)


async def end_group_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """پایان بازی گروهی"""
    if chat_id not in group_games:
        return

    game = group_games[chat_id]

    # ساخت خلاصه بازی
    summary = "🏁 بازی جرئت یا حقیقت به پایان رسید!\n\n"
    summary += f"👥 تعداد بازیکنان: {len(game['players'])}\n"
    summary += f"🔄 تعداد دورها: {game['rounds']}\n\n"

    # آمار بازی
    truth_count = len([q for q in game["questions"] if q["type"] == "truth"])
    dare_count = len([q for q in game["questions"] if q["type"] == "dare"])

    summary += f"📊 آمار بازی:\n"
    summary += f"🎲 حقیقت: {truth_count}\n"
    summary += f"💣 جرئت: {dare_count}\n\n"

    summary += "برای شروع بازی جدید از دستور /startgame استفاده کنید."

    await context.bot.send_message(
        chat_id=chat_id,
        text=summary
    )

    # حذف بازی از لیست بازی‌های فعال
    del group_games[chat_id]


async def cancel_group_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو بازی گروهی"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if chat_id not in group_games:
        await query.answer("❌ بازی فعالی برای لغو وجود ندارد.", show_alert=True)
        return

    game = group_games[chat_id]

    # فقط ایجادکننده بازی می‌تواند آن را لغو کند
    if user_id != game["creator"]:
        await query.answer("⚠️ فقط ایجادکننده بازی می‌تواند آن را لغو کند!", show_alert=True)
        return

    # اعلام لغو بازی
    await query.edit_message_text(
        text="❌ بازی توسط ایجادکننده لغو شد."
    )

    # حذف بازی از لیست بازی‌های فعال
    del group_games[chat_id]



async def end_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پایان دادن به بازی گروهی با دستور"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in group_games:
        await update.message.reply_text("❌ بازی فعالی برای پایان دادن وجود ندارد.")
        return ConversationHandler.END

    game = group_games[chat_id]

    # فقط ایجادکننده بازی می‌تواند آن را پایان دهد
    if user_id != game["creator"]:
        await update.message.reply_text("⚠️ فقط ایجادکننده بازی می‌تواند آن را پایان دهد!")
        return ConversationHandler.END

    await end_group_game(context, chat_id)
    return ConversationHandler.END


# --- اضافه کردن هندلرهای جدید به تابع main ---
def main_updated():
    # بارگیری پاسخ‌های قبلی
    load_responses()

    # راه‌اندازی ربات
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # اضافه کردن هندلرهای اصلی
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    # اضافه کردن هندلرهای بازی گروهی
    app.add_handler(CommandHandler("startgame", start_group_game))
    app.add_handler(CommandHandler("join", join_game))
    app.add_handler(CommandHandler("endgame", end_game_command))

    # اضافه کردن هندلرهای دکمه‌های گروهی
    app.add_handler(CallbackQueryHandler(join_game_button, pattern="^join_game$"))
    app.add_handler(CallbackQueryHandler(begin_game_button, pattern="^begin_game$"))  # استفاده از تابع جدید
    app.add_handler(CallbackQueryHandler(cancel_group_game, pattern="^cancel_group_game$"))
    app.add_handler(CallbackQueryHandler(next_player_turn, pattern="^next_player$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: handle_group_truth_dare(u, c, "truth"), pattern="^group_truth_"))
    app.add_handler(CallbackQueryHandler(lambda u, c: handle_group_truth_dare(u, c, "dare"), pattern="^group_dare_"))
    app.add_handler(CallbackQueryHandler(handle_group_answered, pattern="^group_answered_"))

    # اضافه کردن هندلر اصلی مکالمه
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(button_handler)],
            PLAYING: [CallbackQueryHandler(button_handler)],
            WAITING_FOR_RESPONSE: [
                # پردازش پاسخ‌های متنی، تصویری و ویدئویی
                MessageHandler(
                    filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO,
                    handle_response
                ),
                CallbackQueryHandler(button_handler)  # برای مدیریت دکمه‌ها در این حالت
            ],
            JOINED_GAME: [CallbackQueryHandler(button_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)

    # شروع پردازش پیام‌ها
    logger.info("Bot started!")
    app.run_polling()

# جایگزینی تابع main با نسخه به‌روزرسانی شده
if __name__ == "__main__":
    main_updated()