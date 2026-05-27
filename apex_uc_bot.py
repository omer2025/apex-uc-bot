from pathlib import Path

bot_code = r'''import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# =========================
# ENVIRONMENT VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

HESABPAY_NUMBER = os.getenv("HESABPAY_NUMBER", "+93 789 077 537")
WHATSAPP = os.getenv("WHATSAPP", "+93 789 077 537")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing. Set it in environment variables.")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID missing. Set it in environment variables.")

# =========================
# SETTINGS - AFN ONLY / 60 UC ONLY
# =========================
PRODUCT_KEY = "60UC"
PRODUCT_UC = 60
PRODUCT_PRICE_AFN = int(os.getenv("UC60_PRICE_AFN", "60"))

DB_PATH = "apex_uc_bot.db"

(
    MAIN_MENU,
    ENTER_PLAYER_ID,
    SELECT_PAYMENT,
    SEND_ORDER_SCREENSHOT,
    ENTER_WALLET_AMOUNT,
    SEND_WALLET_SCREENSHOT,
    ADMIN_ADD_CODES,
    ADMIN_SET_PRICE,
) = range(8)


# =========================
# DATABASE
# =========================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance_afn INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uc_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'available',
                used_by INTEGER,
                used_order_id INTEGER,
                added_at TEXT,
                used_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                product_key TEXT NOT NULL,
                uc_amount INTEGER NOT NULL,
                price_afn INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                code_id INTEGER,
                created_at TEXT,
                confirmed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                amount_afn INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT,
                confirmed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES('uc60_price_afn', ?)",
            (str(PRODUCT_PRICE_AFN),)
        )


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_user(user):
    with db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users(user_id, username, first_name, balance_afn, created_at)
            VALUES (?, ?, ?, 0, ?)
        """, (user.id, user.username or "", user.first_name or "", now()))
        conn.execute("""
            UPDATE users SET username=?, first_name=? WHERE user_id=?
        """, (user.username or "", user.first_name or "", user.id))


def get_price_afn():
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='uc60_price_afn'").fetchone()
        return int(row["value"]) if row else PRODUCT_PRICE_AFN


def set_price_afn(price):
    with db() as conn:
        conn.execute("""
            INSERT INTO settings(key, value) VALUES('uc60_price_afn', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (str(price),))


def get_balance(user_id):
    with db() as conn:
        row = conn.execute("SELECT balance_afn FROM users WHERE user_id=?", (user_id,)).fetchone()
        return int(row["balance_afn"]) if row else 0


def add_balance(user_id, amount):
    with db() as conn:
        conn.execute("UPDATE users SET balance_afn = balance_afn + ? WHERE user_id=?", (amount, user_id))


def deduct_balance(user_id, amount):
    with db() as conn:
        balance = get_balance(user_id)
        if balance < amount:
            return False
        conn.execute("UPDATE users SET balance_afn = balance_afn - ? WHERE user_id=?", (amount, user_id))
        return True


def available_stock():
    with db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS count FROM uc_codes
            WHERE product_key=? AND status='available'
        """, (PRODUCT_KEY,)).fetchone()
        return int(row["count"])


def add_codes(codes):
    added = 0
    duplicates = 0
    with db() as conn:
        for code in codes:
            try:
                conn.execute("""
                    INSERT INTO uc_codes(product_key, code, status, added_at)
                    VALUES (?, ?, 'available', ?)
                """, (PRODUCT_KEY, code, now()))
                added += 1
            except sqlite3.IntegrityError:
                duplicates += 1
    return added, duplicates


def create_order(user, player_id, payment_method):
    price = get_price_afn()
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO orders(user_id, username, first_name, product_key, uc_amount, price_afn,
                               player_id, payment_method, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            PRODUCT_KEY,
            PRODUCT_UC,
            price,
            player_id,
            payment_method,
            now(),
        ))
        return cur.lastrowid


def create_wallet_deposit(user, amount):
    with db() as conn:
        cur = conn.execute("""
            INSERT INTO wallet_deposits(user_id, username, first_name, amount_afn, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (user.id, user.username or "", user.first_name or "", amount, now()))
        return cur.lastrowid


def get_order(order_id):
    with db() as conn:
        return conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()


def get_deposit(deposit_id):
    with db() as conn:
        return conn.execute("SELECT * FROM wallet_deposits WHERE id=?", (deposit_id,)).fetchone()


def deliver_code_for_order(order_id):
    """
    Returns: (ok, message, code, remaining_stock)
    """
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return False, "Order not found.", None, available_stock()
        if order["status"] != "pending":
            return False, "Order already handled.", None, available_stock()

        code_row = conn.execute("""
            SELECT id, code FROM uc_codes
            WHERE product_key=? AND status='available'
            ORDER BY id ASC
            LIMIT 1
        """, (PRODUCT_KEY,)).fetchone()

        if not code_row:
            return False, "Out of stock. Add codes first.", None, 0

        conn.execute("""
            UPDATE uc_codes
            SET status='used', used_by=?, used_order_id=?, used_at=?
            WHERE id=?
        """, (order["user_id"], order_id, now(), code_row["id"]))

        conn.execute("""
            UPDATE orders
            SET status='confirmed', code_id=?, confirmed_at=?
            WHERE id=?
        """, (code_row["id"], now(), order_id))

        remaining = conn.execute("""
            SELECT COUNT(*) AS count FROM uc_codes
            WHERE product_key=? AND status='available'
        """, (PRODUCT_KEY,)).fetchone()["count"]

        return True, "Code delivered.", code_row["code"], int(remaining)


def reject_order(order_id):
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order or order["status"] != "pending":
            return None
        conn.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
        return order


def confirm_deposit(deposit_id):
    with db() as conn:
        dep = conn.execute("SELECT * FROM wallet_deposits WHERE id=?", (deposit_id,)).fetchone()
        if not dep or dep["status"] != "pending":
            return None
        conn.execute("""
            UPDATE wallet_deposits SET status='confirmed', confirmed_at=? WHERE id=?
        """, (now(), deposit_id))
        conn.execute("""
            UPDATE users SET balance_afn = balance_afn + ? WHERE user_id=?
        """, (dep["amount_afn"], dep["user_id"]))
        return dep


def reject_deposit(deposit_id):
    with db() as conn:
        dep = conn.execute("SELECT * FROM wallet_deposits WHERE id=?", (deposit_id,)).fetchone()
        if not dep or dep["status"] != "pending":
            return None
        conn.execute("UPDATE wallet_deposits SET status='rejected' WHERE id=?", (deposit_id,))
        return dep


# =========================
# KEYBOARDS
# =========================
def menu_keyboard(is_admin=False):
    rows = [
        [InlineKeyboardButton("🎮 Buy 60 UC", callback_data="buy_60uc")],
        [InlineKeyboardButton("💰 My Wallet", callback_data="wallet")],
        [InlineKeyboardButton("📞 Support", callback_data="support")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🗄️ Manage UC Codes", callback_data="admin_codes")])
        rows.append([InlineKeyboardButton("💵 Set 60 UC Price", callback_data="admin_set_price")])
    return InlineKeyboardMarkup(rows)


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]])


# =========================
# USER FLOW
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.message.from_user)
    context.user_data.clear()
    user = update.message.from_user
    is_admin = user.id == ADMIN_ID

    await update.message.reply_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "🇦🇫 PUBG Mobile UC Store\n\n"
        f"✅ Product: *60 UC only*\n"
        f"💰 Price: *{get_price_afn()} AFN*\n"
        f"🗄️ Ready stock: *{available_stock()} code(s)*\n\n"
        "Choose an option below:",
        parse_mode="Markdown",
        reply_markup=menu_keyboard(is_admin),
    )
    return MAIN_MENU


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user)
    context.user_data.clear()

    await query.edit_message_text(
        "🎮 *Apex Digital House*\n\n"
        f"60 UC Price: *{get_price_afn()} AFN*\n"
        f"Ready stock: *{available_stock()} code(s)*\n\n"
        "Choose an option:",
        parse_mode="Markdown",
        reply_markup=menu_keyboard(query.from_user.id == ADMIN_ID),
    )
    return MAIN_MENU


async def buy_60uc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user)

    if available_stock() <= 0:
        await query.edit_message_text(
            "❌ *60 UC is out of stock right now.*\n\nPlease contact support.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return MAIN_MENU

    context.user_data["product"] = PRODUCT_KEY

    await query.edit_message_text(
        f"🎮 *Buy 60 UC*\n\n"
        f"Price: *{get_price_afn()} AFN*\n\n"
        "Please enter your PUBG Mobile Player ID.\n\n"
        "⚠️ Double-check your Player ID. Wrong ID = wrong delivery.",
        parse_mode="Markdown",
    )
    return ENTER_PLAYER_ID


async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()

    if not player_id.isdigit() or len(player_id) < 5:
        await update.message.reply_text("❌ Please enter a valid numeric PUBG Player ID.")
        return ENTER_PLAYER_ID

    context.user_data["player_id"] = player_id
    user_id = update.message.from_user.id
    price = get_price_afn()
    balance = get_balance(user_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Pay From Wallet", callback_data="pay_wallet")],
        [InlineKeyboardButton("📲 Direct HesabPay Transfer", callback_data="pay_hesabpay")],
        [InlineKeyboardButton("🔙 Start Over", callback_data="main_menu")],
    ])

    await update.message.reply_text(
        f"📋 *Order Summary*\n\n"
        f"🎮 Package: *60 UC*\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💰 Price: *{price} AFN*\n"
        f"💳 Your wallet: *{balance} AFN*\n\n"
        "Choose payment method:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return SELECT_PAYMENT


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user)

    player_id = context.user_data.get("player_id")
    if not player_id:
        await query.edit_message_text("❌ Session expired. Type /start again.")
        return ConversationHandler.END

    price = get_price_afn()
    user = query.from_user
    payment = query.data.replace("pay_", "")

    if payment == "wallet":
        balance = get_balance(user.id)
        if balance < price:
            await query.edit_message_text(
                f"❌ *Not enough wallet balance.*\n\n"
                f"Your wallet: *{balance} AFN*\n"
                f"Price: *{price} AFN*\n\n"
                "You can add balance or use direct HesabPay transfer.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Wallet Balance", callback_data="add_wallet_balance")],
                    [InlineKeyboardButton("📲 Direct HesabPay Transfer", callback_data="pay_hesabpay")],
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
                ]),
            )
            return SELECT_PAYMENT

        if available_stock() <= 0:
            await query.edit_message_text("❌ Out of stock. Please contact support.", reply_markup=back_keyboard())
            return MAIN_MENU

        order_id = create_order(user, player_id, "wallet")
        if not deduct_balance(user.id, price):
            await query.edit_message_text("❌ Wallet payment failed. Please try again.")
            return ConversationHandler.END

        ok, msg, code, remaining = deliver_code_for_order(order_id)
        if not ok:
            add_balance(user.id, price)
            await query.edit_message_text(f"❌ {msg}\nYour wallet was refunded.", reply_markup=back_keyboard())
            return MAIN_MENU

        new_balance = get_balance(user.id)

        await context.bot.send_message(
            ADMIN_ID,
            f"✅ *AUTO DELIVERY — WALLET PAID*\n\n"
            f"Order ID: `{order_id}`\n"
            f"User: {user.first_name} (@{user.username or 'N/A'})\n"
            f"Telegram ID: `{user.id}`\n"
            f"Package: *60 UC*\n"
            f"Price: *{price} AFN*\n"
            f"Player ID: `{player_id}`\n"
            f"Code sent: `{code}`\n"
            f"Remaining stock: *{remaining}*",
            parse_mode="Markdown",
        )

        await query.edit_message_text(
            f"⚡ *UC Code Delivery Completed!*\n\n"
            f"🆔 Order ID: `#{order_id}`\n"
            f"🎮 Package: *60 UC*\n"
            f"🎯 Player ID: `{player_id}`\n"
            f"💰 Paid: *{price} AFN*\n"
            f"💳 Balance After: *{new_balance} AFN*\n\n"
            f"📦 *Redeem Code:*\n"
            f"✅ `{code}`\n\n"
            "Thank you for shopping with Apex Digital House 🇦🇫",
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Direct transfer
    order_id = create_order(user, player_id, "hesabpay")
    context.user_data["order_id"] = order_id

    await query.edit_message_text(
        f"📲 *Direct HesabPay Transfer*\n\n"
        f"Order ID: `#{order_id}`\n"
        f"Package: *60 UC*\n"
        f"Player ID: `{player_id}`\n"
        f"Amount: *{price} AFN*\n\n"
        f"Send payment to HesabPay:\n`{HESABPAY_NUMBER}`\n\n"
        "After payment, send the screenshot here. 📸",
        parse_mode="Markdown",
    )
    return SEND_ORDER_SCREENSHOT


async def receive_order_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("order_id")
    if not order_id:
        await update.message.reply_text("❌ Session expired. Type /start again.")
        return ConversationHandler.END

    order = get_order(order_id)
    user = update.message.from_user

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm & Send Code", callback_data=f"order_confirm_{order_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"order_reject_{order_id}"),
    ]])

    caption = (
        f"🔔 *NEW 60 UC ORDER — DIRECT TRANSFER*\n\n"
        f"Order ID: `#{order_id}`\n"
        f"User: {user.first_name} (@{user.username or 'N/A'})\n"
        f"Telegram ID: `{user.id}`\n\n"
        f"Package: *60 UC*\n"
        f"Price: *{order['price_afn']} AFN*\n"
        f"Player ID: `{order['player_id']}`\n"
        f"Stock: *{available_stock()} code(s)*"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            ADMIN_ID,
            caption + "\n\n⚠️ Customer did not send a photo screenshot.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    await update.message.reply_text(
        "✅ *Order received!*\n\n"
        "We are checking your payment. Your UC code will be sent here after confirmation.",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# =========================
# WALLET
# =========================
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user)

    balance = get_balance(query.from_user.id)
    await query.edit_message_text(
        f"💰 *Your Wallet*\n\n"
        f"Balance: *{balance} AFN*\n\n"
        "You can add balance first, then future orders can be delivered instantly.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Wallet Balance", callback_data="add_wallet_balance")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]),
    )
    return MAIN_MENU


async def add_wallet_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user)

    await query.edit_message_text(
        "➕ *Add Wallet Balance*\n\n"
        "Type the amount in AFN.\n\n"
        "Example: `500`\n"
        "Minimum: *50 AFN*",
        parse_mode="Markdown",
    )
    return ENTER_WALLET_AMOUNT


async def enter_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a number only. Example: `500`", parse_mode="Markdown")
        return ENTER_WALLET_AMOUNT

    if amount < 50:
        await update.message.reply_text("❌ Minimum wallet deposit is 50 AFN.")
        return ENTER_WALLET_AMOUNT

    context.user_data["wallet_amount"] = amount

    await update.message.reply_text(
        f"📲 *Wallet Deposit: {amount} AFN*\n\n"
        f"Send payment to HesabPay:\n`{HESABPAY_NUMBER}`\n\n"
        "After payment, send your screenshot here. 📸",
        parse_mode="Markdown",
    )
    return SEND_WALLET_SCREENSHOT


async def receive_wallet_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("wallet_amount")
    if not amount:
        await update.message.reply_text("❌ Session expired. Type /start again.")
        return ConversationHandler.END

    user = update.message.from_user
    ensure_user(user)
    deposit_id = create_wallet_deposit(user, amount)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm Deposit", callback_data=f"wallet_confirm_{deposit_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"wallet_reject_{deposit_id}"),
    ]])

    caption = (
        f"💰 *NEW WALLET DEPOSIT*\n\n"
        f"Deposit ID: `#{deposit_id}`\n"
        f"User: {user.first_name} (@{user.username or 'N/A'})\n"
        f"Telegram ID: `{user.id}`\n"
        f"Amount: *{amount} AFN*"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            ADMIN_ID,
            caption + "\n\n⚠️ Customer did not send a photo screenshot.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    await update.message.reply_text(
        "✅ *Wallet deposit request received!*\n\nWaiting for admin confirmation.",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# =========================
# ADMIN ACTIONS
# =========================
async def order_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data

    if data.startswith("order_confirm_"):
        order_id = int(data.replace("order_confirm_", ""))
        order = get_order(order_id)
        if not order or order["status"] != "pending":
            text = "⚠️ Order already handled or not found."
            if query.message.photo:
                await query.edit_message_caption(caption=text)
            else:
                await query.edit_message_text(text)
            return

        ok, msg, code, remaining = deliver_code_for_order(order_id)
        if not ok:
            text = f"❌ {msg}"
            if query.message.photo:
                await query.edit_message_caption(caption=text)
            else:
                await query.edit_message_text(text)
            return

        await context.bot.send_message(
            order["user_id"],
            f"⚡ *UC Code Delivery Completed!*\n\n"
            f"🆔 Order ID: `#{order_id}`\n"
            f"🎮 Package: *60 UC*\n"
            f"🎯 Player ID: `{order['player_id']}`\n"
            f"💰 Paid: *{order['price_afn']} AFN*\n\n"
            f"📦 *Redeem Code:*\n"
            f"✅ `{code}`\n\n"
            "Thank you for shopping with Apex Digital House 🇦🇫",
            parse_mode="Markdown",
        )

        text = (
            f"✅ *Order Confirmed & Code Sent*\n\n"
            f"Order ID: `#{order_id}`\n"
            f"Code sent: `{code}`\n"
            f"Remaining stock: *{remaining}*"
        )
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, parse_mode="Markdown")

    elif data.startswith("order_reject_"):
        order_id = int(data.replace("order_reject_", ""))
        order = reject_order(order_id)
        if not order:
            text = "⚠️ Order already handled or not found."
            if query.message.photo:
                await query.edit_message_caption(caption=text)
            else:
                await query.edit_message_text(text)
            return

        await context.bot.send_message(
            order["user_id"],
            f"❌ *Payment Not Confirmed*\n\n"
            f"Your order `#{order_id}` for *60 UC* was rejected.\n\n"
            f"Please contact support: {TELEGRAM_SUPPORT}",
            parse_mode="Markdown",
        )

        text = f"❌ Order rejected — `#{order_id}`"
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, parse_mode="Markdown")


async def wallet_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data

    if data.startswith("wallet_confirm_"):
        deposit_id = int(data.replace("wallet_confirm_", ""))
        dep = confirm_deposit(deposit_id)
        if not dep:
            text = "⚠️ Deposit already handled or not found."
            if query.message.photo:
                await query.edit_message_caption(caption=text)
            else:
                await query.edit_message_text(text)
            return

        new_balance = get_balance(dep["user_id"])

        await context.bot.send_message(
            dep["user_id"],
            f"✅ *Wallet Deposit Confirmed!*\n\n"
            f"Amount added: *{dep['amount_afn']} AFN*\n"
            f"New wallet balance: *{new_balance} AFN*",
            parse_mode="Markdown",
        )

        text = (
            f"✅ *Deposit Confirmed*\n\n"
            f"Deposit ID: `#{deposit_id}`\n"
            f"Added: *{dep['amount_afn']} AFN*\n"
            f"New balance: *{new_balance} AFN*"
        )
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, parse_mode="Markdown")

    elif data.startswith("wallet_reject_"):
        deposit_id = int(data.replace("wallet_reject_", ""))
        dep = reject_deposit(deposit_id)
        if not dep:
            text = "⚠️ Deposit already handled or not found."
            if query.message.photo:
                await query.edit_message_caption(caption=text)
            else:
                await query.edit_message_text(text)
            return

        await context.bot.send_message(
            dep["user_id"],
            f"❌ *Wallet Deposit Rejected*\n\n"
            f"Deposit ID: `#{deposit_id}`\n"
            f"Amount: *{dep['amount_afn']} AFN*\n\n"
            "Contact support if this is a mistake.",
            parse_mode="Markdown",
        )

        text = f"❌ Deposit rejected — `#{deposit_id}`"
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, parse_mode="Markdown")


async def admin_codes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return MAIN_MENU

    await query.edit_message_text(
        f"🗄️ *60 UC Code Inventory*\n\n"
        f"Available stock: *{available_stock()} code(s)*\n\n"
        "Choose an option:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add 60 UC Codes", callback_data="admin_add_codes")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]),
    )
    return MAIN_MENU


async def admin_start_add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return MAIN_MENU

    await query.edit_message_text(
        "➕ *Add 60 UC Codes*\n\n"
        "Send one code per line.\n\n"
        "Example:\n"
        "`CODE123\nCODE456\nCODE789`\n\n"
        "Type /cancel to stop.",
        parse_mode="Markdown",
    )
    return ADMIN_ADD_CODES


async def admin_receive_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return ConversationHandler.END

    codes = [line.strip() for line in update.message.text.splitlines() if line.strip()]
    if not codes:
        await update.message.reply_text("❌ No codes found. Send one code per line.")
        return ADMIN_ADD_CODES

    added, duplicates = add_codes(codes)

    await update.message.reply_text(
        f"✅ *Codes Added*\n\n"
        f"Added: *{added}*\n"
        f"Duplicates skipped: *{duplicates}*\n"
        f"Current stock: *{available_stock()}*",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def admin_set_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return MAIN_MENU

    await query.edit_message_text(
        f"💵 *Set 60 UC Price*\n\n"
        f"Current price: *{get_price_afn()} AFN*\n\n"
        "Type the new price in AFN.\n\n"
        "Example: `75`",
        parse_mode="Markdown",
    )
    return ADMIN_SET_PRICE


async def admin_set_price_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return ConversationHandler.END

    try:
        price = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a number only. Example: `75`", parse_mode="Markdown")
        return ADMIN_SET_PRICE

    if price <= 0:
        await update.message.reply_text("❌ Price must be greater than 0.")
        return ADMIN_SET_PRICE

    set_price_afn(price)
    await update.message.reply_text(
        f"✅ 60 UC price updated to *{price} AFN*.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return

    await update.message.reply_text(
        f"🗄️ *Stock Report*\n\n"
        f"60 UC available codes: *{available_stock()}*\n"
        f"Current price: *{get_price_afn()} AFN*",
        parse_mode="Markdown",
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"📞 *Support*\n\n"
        f"WhatsApp: {WHATSAPP}\n"
        f"Telegram: {TELEGRAM_SUPPORT}",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )
    return MAIN_MENU


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 *Support*\n\n"
        f"WhatsApp: {WHATSAPP}\n"
        f"Telegram: {TELEGRAM_SUPPORT}",
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return ConversationHandler.END


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
                CallbackQueryHandler(buy_60uc, pattern="^buy_60uc$"),
                CallbackQueryHandler(wallet, pattern="^wallet$"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(support, pattern="^support$"),
                CallbackQueryHandler(admin_codes_menu, pattern="^admin_codes$"),
                CallbackQueryHandler(admin_start_add_codes, pattern="^admin_add_codes$"),
                CallbackQueryHandler(admin_set_price_start, pattern="^admin_set_price$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            SEND_ORDER_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_order_screenshot),
            ],
            ENTER_WALLET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_wallet_amount),
            ],
            SEND_WALLET_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_wallet_screenshot),
            ],
            ADMIN_ADD_CODES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_codes),
            ],
            ADMIN_SET_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_price_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("support", support_command),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CallbackQueryHandler(order_admin_action, pattern="^order_(confirm|reject)_"))
    app.add_handler(CallbackQueryHandler(wallet_admin_action, pattern="^wallet_(confirm|reject)_"))

    print("🤖 Apex 60 UC AFN Bot is running...")
    app.run_polling()
'''

path = Path("/mnt/data/apex_60uc_afn_bot.py")
path.write_text(bot_code, encoding="utf-8")
print(f"Created {path}")
