from pathlib import Path

bot_code = r'''import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing. Set it in environment variables.")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID missing. Set it in environment variables.")

DB_PATH = "apex_test_uc_bot.db"
PRODUCT_KEY = "60UC"
PRODUCT_UC = 60
PRODUCT_PRICE_AFN = 60

# Your test 60 UC code
TEST_CODE = "Tb89s6pq2q2649k5D9"

MAIN_MENU, ENTER_PLAYER_ID = range(2)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uc_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'available',
                used_by INTEGER,
                used_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                player_id TEXT,
                code TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        # Auto-load your one test code if it is not already in the database
        conn.execute("""
            INSERT OR IGNORE INTO uc_codes(product_key, code, status)
            VALUES (?, ?, 'available')
        """, (PRODUCT_KEY, TEST_CODE))


def stock_count():
    with db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS c FROM uc_codes
            WHERE product_key=? AND status='available'
        """, (PRODUCT_KEY,)).fetchone()
        return int(row["c"])


def get_and_use_code(user_id):
    with db() as conn:
        code_row = conn.execute("""
            SELECT id, code FROM uc_codes
            WHERE product_key=? AND status='available'
            ORDER BY id ASC
            LIMIT 1
        """, (PRODUCT_KEY,)).fetchone()

        if not code_row:
            return None

        conn.execute("""
            UPDATE uc_codes
            SET status='used', used_by=?, used_at=?
            WHERE id=?
        """, (user_id, now(), code_row["id"]))

        return code_row["code"]


def save_order(user, player_id, code):
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO orders(user_id, username, first_name, player_id, code, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'delivered', ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            player_id,
            code,
            now(),
        ))
        return cur.lastrowid


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Buy / Test 60 UC", callback_data="buy_60uc")],
    ])


async def set_start_only_command(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot")
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "⚡ *Apex UC Test Bot*\n\n"
        "🎮 Product: *60 UC only*\n"
        f"💰 Price: *{PRODUCT_PRICE_AFN} AFN*\n"
        f"📦 Ready stock: *{stock_count()} code(s)*\n\n"
        "For testing, this bot will send the code automatically after Player ID.",
        parse_mode="Markdown",
        reply_markup=menu_keyboard(),
    )
    return MAIN_MENU


async def buy_60uc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if stock_count() <= 0:
        await query.edit_message_text(
            "❌ *Out of stock.*\n\nThe test code was already used.",
            parse_mode="Markdown",
        )
        return MAIN_MENU

    await query.edit_message_text(
        "📝 Please send / enter Player ID:\n\n"
        "🎮 Package: *60 UC*\n"
        f"💰 Price: *{PRODUCT_PRICE_AFN} AFN*\n\n"
        "⚠️ This is test mode. Code will be delivered automatically.",
        parse_mode="Markdown",
    )
    return ENTER_PLAYER_ID


async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()
    user = update.message.from_user

    if not player_id.isdigit() or len(player_id) < 5:
        await update.message.reply_text("❌ Please enter a valid numeric PUBG Player ID.")
        return ENTER_PLAYER_ID

    await update.message.reply_text("⏳ Checking player info, please wait...")
    await update.message.reply_text("⚡ Loading PUBG UC, please wait...\n_This process may take a few seconds._", parse_mode="Markdown")

    code = get_and_use_code(user.id)
    if not code:
        await update.message.reply_text("❌ Out of stock. No 60 UC code is available.")
        return MAIN_MENU

    order_id = save_order(user, player_id, code)

    await update.message.reply_text(
        f"⚡ *UC Code Delivery Completed!*\n\n"
        f"🆔 Order ID: `#{order_id}`\n"
        f"👤 Username: @{user.username or 'N/A'}\n"
        f"🆔 ID: `{player_id}`\n"
        f"🎁 Package: *60 UC*\n"
        f"💰 Total: *{PRODUCT_PRICE_AFN} AFN*\n\n"
        f"📦 *Redeem Code:*\n"
        f"✅ `{code}`\n\n"
        "🌍 Region: Global",
        parse_mode="Markdown",
    )

    await update.message.reply_text(
        f"Admin note: remaining 60 UC stock = {stock_count()} code(s)."
    )

    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"✅ *TEST ORDER AUTO DELIVERED*\n\n"
            f"Order ID: `#{order_id}`\n"
            f"User: {user.first_name} (@{user.username or 'N/A'})\n"
            f"Telegram ID: `{user.id}`\n"
            f"Player ID: `{player_id}`\n"
            f"Code sent: `{code}`\n"
            f"Remaining stock: *{stock_count()}*",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    return MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return MAIN_MENU


if __name__ == "__main__":
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(set_start_only_command)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(buy_60uc, pattern="^buy_60uc$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)

    print("🤖 Apex 60 UC TEST bot is running...")
    app.run_polling()
'''

path = Path("/mnt/data/apex_60uc_test_auto_bot.py")
path.write_text(bot_code, encoding="utf-8")
print(f"Created {path}")
