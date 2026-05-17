import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ============ CONFIGURATION ============
BOT_TOKEN = "8602835129:AAFGXQsEUBpWChMbZ9K5iy7wMEOLfM3wwaw"
ADMIN_ID = 8556241073
USDT_WALLET = "TUUrCxQexypGX8wmXMeNf6mRq2PFFK9Jvz"
HESABPAY_NUMBER = "+93 789 077 537"
MIN_TOPUP_USD = 5.0
MIN_TOPUP_AFN = 325.0

# ============ UC PACKAGES ============
PACKAGES = {
    "60UC":   {"uc": 60,   "afn": 60,   "usd": 0.95},
    "325UC":  {"uc": 325,  "afn": 300,  "usd": 4.50},
    "660UC":  {"uc": 660,  "afn": 590,  "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

# ============ STATES ============
(MAIN_MENU, SELECT_TOPUP, ENTER_TOPUP_AMOUNT, SEND_HESABPAY_SCREENSHOT,
 SELECT_PACKAGE, ENTER_PLAYER_ID, CONFIRM_ORDER) = range(7)

# ============ DATABASE ============
def init_db():
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        usd_balance REAL DEFAULT 0,
        afn_balance REAL DEFAULT 0,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        type TEXT,
        amount REAL,
        currency TEXT,
        description TEXT,
        status TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_topups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        amount REAL,
        currency TEXT,
        method TEXT,
        screenshot_file_id TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(telegram_id, username, first_name):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name, usd_balance, afn_balance, created_at) VALUES (?,?,?,0,0,?)",
              (telegram_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_balance(telegram_id):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("SELECT usd_balance, afn_balance FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (0, 0)

def add_balance(telegram_id, amount, currency):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    if currency == "USD":
        c.execute("UPDATE users SET usd_balance = usd_balance + ? WHERE telegram_id=?", (amount, telegram_id))
    else:
        c.execute("UPDATE users SET afn_balance = afn_balance + ? WHERE telegram_id=?", (amount, telegram_id))
    conn.commit()
    conn.close()

def deduct_balance(telegram_id, amount, currency):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    if currency == "USD":
        c.execute("UPDATE users SET usd_balance = usd_balance - ? WHERE telegram_id=?", (amount, telegram_id))
    else:
        c.execute("UPDATE users SET afn_balance = afn_balance - ? WHERE telegram_id=?", (amount, telegram_id))
    conn.commit()
    conn.close()

def add_transaction(telegram_id, type_, amount, currency, description, status):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("INSERT INTO transactions (telegram_id, type, amount, currency, description, status, created_at) VALUES (?,?,?,?,?,?,?)",
              (telegram_id, type_, amount, currency, description, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_pending_topup(telegram_id, amount, currency, method, screenshot_file_id=None):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("INSERT INTO pending_topups (telegram_id, amount, currency, method, screenshot_file_id, created_at) VALUES (?,?,?,?,?,?)",
              (telegram_id, amount, currency, method, screenshot_file_id, datetime.now().isoformat()))
    topup_id = c.lastrowid
    conn.commit()
    conn.close()
    return topup_id

def get_pending_topup(topup_id):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("SELECT * FROM pending_topups WHERE id=?", (topup_id,))
    result = c.fetchone()
    conn.close()
    return result

def delete_pending_topup(topup_id):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("DELETE FROM pending_topups WHERE id=?", (topup_id,))
    conn.commit()
    conn.close()

def get_transactions(telegram_id, limit=5):
    conn = sqlite3.connect("wallet.db")
    c = conn.cursor()
    c.execute("SELECT type, amount, currency, description, status, created_at FROM transactions WHERE telegram_id=? ORDER BY id DESC LIMIT ?",
              (telegram_id, limit))
    result = c.fetchall()
    conn.close()
    return result

# ============ USDT AUTO-DETECTION ============
def check_usdt_payment(expected_amount):
    try:
        url = f"https://apilist.tronscanapi.com/api/token_trc20/transfers?toAddress={USDT_WALLET}&limit=5&start=0"
        response = requests.get(url, timeout=10)
        data = response.json()
        if "token_transfers" in data:
            for tx in data["token_transfers"]:
                amount = float(tx.get("quant", 0)) / 1000000
                timestamp = tx.get("block_ts", 0) / 1000
                age = datetime.now().timestamp() - timestamp
                if abs(amount - expected_amount) < 0.01 and age < 3600:
                    return True, amount
        return False, 0
    except:
        return False, 0

# ============ MAIN MENU ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username or "", user.first_name or "")
    usd_bal, afn_bal = get_balance(user.id)
    keyboard = [
        [InlineKeyboardButton("👛 My Wallet", callback_data="wallet"),
         InlineKeyboardButton("➕ Top Up", callback_data="topup")],
        [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
        [InlineKeyboardButton("📊 Transaction History", callback_data="history"),
         InlineKeyboardButton("📞 Support", callback_data="support")],
    ]
    await update.message.reply_text(
        f"🎮 *Welcome to Apex Digital House!*\n\n"
        f"👋 Hello {user.first_name}!\n\n"
        f"💰 *Your Balance:*\n"
        f"💵 USD: ${usd_bal:.2f}\n"
        f"🇦🇫 AFN: {afn_bal:.0f} AFN\n\n"
        f"What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

# ============ WALLET ============
async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    usd_bal, afn_bal = get_balance(user.id)
    keyboard = [
        [InlineKeyboardButton("➕ Top Up Wallet", callback_data="topup")],
        [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        f"👛 *Your Wallet*\n\n"
        f"💵 USD Balance: *${usd_bal:.2f}*\n"
        f"🇦🇫 AFN Balance: *{afn_bal:.0f} AFN*\n\n"
        f"Minimum top-up:\n"
        f"• USDT: ${MIN_TOPUP_USD}\n"
        f"• HesabPay: {MIN_TOPUP_AFN:.0f} AFN",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

# ============ TOP UP ============
async def show_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💎 USDT (Auto - USD)", callback_data="topup_usdt")],
        [InlineKeyboardButton("📲 HesabPay (Manual - AFN)", callback_data="topup_hesabpay")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "➕ *Top Up Wallet*\n\n"
        "Select your top-up method:\n\n"
        "💎 *USDT* — Automatic, instant\n"
        "📲 *HesabPay* — Manual, confirmed by admin",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TOPUP

async def topup_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["topup_method"] = "usdt"
    await query.edit_message_text(
        f"💎 *USDT Top-Up*\n\n"
        f"Minimum: *${MIN_TOPUP_USD}*\n\n"
        f"Please enter the amount in USD you want to top up:\n"
        f"_(Example: 10)_",
        parse_mode="Markdown"
    )
    return ENTER_TOPUP_AMOUNT

async def topup_hesabpay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["topup_method"] = "hesabpay"
    await query.edit_message_text(
        f"📲 *HesabPay Top-Up*\n\n"
        f"Minimum: *{MIN_TOPUP_AFN:.0f} AFN*\n\n"
        f"Please enter the amount in AFN you want to top up:\n"
        f"_(Example: 500)_",
        parse_mode="Markdown"
    )
    return ENTER_TOPUP_AMOUNT

async def enter_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = context.user_data.get("topup_method")
    try:
        amount = float(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Please enter a valid number!")
        return ENTER_TOPUP_AMOUNT

    if method == "usdt":
        if amount < MIN_TOPUP_USD:
            await update.message.reply_text(f"❌ Minimum USDT top-up is ${MIN_TOPUP_USD}!")
            return ENTER_TOPUP_AMOUNT
        context.user_data["topup_amount"] = amount
        context.user_data["topup_currency"] = "USD"
        await update.message.reply_text(
            f"💎 *USDT Payment Instructions*\n\n"
            f"Send exactly *${amount:.2f} USDT (TRC20)* to:\n\n"
            f"`{USDT_WALLET}`\n\n"
            f"⚠️ Send *exactly* ${amount:.2f} USDT\n"
            f"⚠️ Use *TRC20* network only\n\n"
            f"After sending, type /checkpayment to verify automatically!",
            parse_mode="Markdown"
        )
        return MAIN_MENU

    else:  # hesabpay
        if amount < MIN_TOPUP_AFN:
            await update.message.reply_text(f"❌ Minimum HesabPay top-up is {MIN_TOPUP_AFN:.0f} AFN!")
            return ENTER_TOPUP_AMOUNT
        context.user_data["topup_amount"] = amount
        context.user_data["topup_currency"] = "AFN"
        await update.message.reply_text(
            f"📲 *HesabPay Payment Instructions*\n\n"
            f"Send *{amount:.0f} AFN* to:\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"📸 After sending, please send your *payment screenshot* here.",
            parse_mode="Markdown"
        )
        return SEND_HESABPAY_SCREENSHOT

async def receive_hesabpay_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("topup_amount")
    currency = context.user_data.get("topup_currency", "AFN")
    user = update.effective_user
    screenshot_file_id = None
    if update.message.photo:
        screenshot_file_id = update.message.photo[-1].file_id
    topup_id = add_pending_topup(user.id, amount, currency, "hesabpay", screenshot_file_id)
    keyboard = [
        [InlineKeyboardButton(f"✅ Confirm #{topup_id}", callback_data=f"confirm_topup_{topup_id}"),
         InlineKeyboardButton(f"❌ Reject #{topup_id}", callback_data=f"reject_topup_{topup_id}")]
    ]
    admin_msg = (
        f"💰 *NEW TOP-UP REQUEST #{topup_id}*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 ID: {user.id}\n"
        f"💵 Amount: {amount:.0f} {currency}\n"
        f"💳 Method: HesabPay"
    )
    try:
        if screenshot_file_id:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=screenshot_file_id,
                caption=admin_msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg + "\n\n⚠️ No screenshot!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logging.error(f"Admin notify failed: {e}")
    await update.message.reply_text(
        f"✅ *Top-up request received!*\n\n"
        f"Amount: *{amount:.0f} AFN*\n"
        f"Request ID: *#{topup_id}*\n\n"
        f"⏳ Admin will confirm within 30 minutes.\n"
        f"Your balance will be updated automatically.",
        parse_mode="Markdown"
    )
    return MAIN_MENU

# ============ CHECK USDT PAYMENT ============
async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get("topup_amount")
    if not amount:
        await update.message.reply_text("❌ No pending USDT payment found. Please start a new top-up with /start")
        return MAIN_MENU
    await update.message.reply_text("🔍 Checking blockchain for your payment...")
    found, actual_amount = check_usdt_payment(amount)
    if found:
        add_balance(user.id, actual_amount, "USD")
        add_transaction(user.id, "topup", actual_amount, "USD", "USDT top-up", "completed")
        context.user_data.pop("topup_amount", None)
        usd_bal, afn_bal = get_balance(user.id)
        await update.message.reply_text(
            f"✅ *Payment Confirmed!*\n\n"
            f"💵 Added: *${actual_amount:.2f} USD*\n"
            f"💰 New Balance: *${usd_bal:.2f} USD*\n\n"
            f"Type /start to buy UC!",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ *USDT Auto-Confirmed*\n\n"
                 f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
                 f"💵 Amount: ${actual_amount:.2f} USD",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"⏳ Payment not found yet.\n\n"
            f"Make sure you sent exactly *${amount:.2f} USDT* on *TRC20* network.\n\n"
            f"Try /checkpayment again in a few minutes.",
            parse_mode="Markdown"
        )
    return MAIN_MENU

# ============ ADMIN CONFIRM/REJECT TOPUP ============
async def admin_confirm_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Not authorized!", show_alert=True)
        return
    topup_id = int(query.data.split("_")[-1])
    topup = get_pending_topup(topup_id)
    if not topup:
        await query.edit_message_caption("❌ Top-up not found or already processed!")
        return
    telegram_id = topup[1]
    amount = topup[2]
    currency = topup[3]
    add_balance(telegram_id, amount, currency)
    add_transaction(telegram_id, "topup", amount, currency, f"HesabPay top-up confirmed by admin", "completed")
    delete_pending_topup(topup_id)
    usd_bal, afn_bal = get_balance(telegram_id)
    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=f"✅ *Top-Up Confirmed!*\n\n"
                 f"💰 Added: *{amount:.0f} {currency}*\n"
                 f"💵 USD Balance: *${usd_bal:.2f}*\n"
                 f"🇦🇫 AFN Balance: *{afn_bal:.0f} AFN*\n\n"
                 f"Type /start to buy UC!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Failed to notify user: {e}")
    await query.edit_message_caption(f"✅ Top-up #{topup_id} confirmed! {amount:.0f} {currency} added.")

async def admin_reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Not authorized!", show_alert=True)
        return
    topup_id = int(query.data.split("_")[-1])
    topup = get_pending_topup(topup_id)
    if not topup:
        await query.edit_message_caption("❌ Top-up not found or already processed!")
        return
    telegram_id = topup[1]
    amount = topup[2]
    currency = topup[3]
    delete_pending_topup(topup_id)
    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=f"❌ *Top-Up Rejected*\n\n"
                 f"Amount: {amount:.0f} {currency}\n\n"
                 f"Please contact support: {HESABPAY_NUMBER}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Failed to notify user: {e}")
    await query.edit_message_caption(f"❌ Top-up #{topup_id} rejected.")

# ============ BUY UC ============
async def show_buy_uc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    usd_bal, afn_bal = get_balance(user.id)
    keyboard = [
        [InlineKeyboardButton("💵 Pay with USD Balance", callback_data="buy_usd")],
        [InlineKeyboardButton("🇦🇫 Pay with AFN Balance", callback_data="buy_afn")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        f"🎮 *Buy UC*\n\n"
        f"💵 USD Balance: *${usd_bal:.2f}*\n"
        f"🇦🇫 AFN Balance: *{afn_bal:.0f} AFN*\n\n"
        f"Select payment currency:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PACKAGE

async def show_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    context.user_data["buy_currency"] = currency
    user = update.effective_user
    usd_bal, afn_bal = get_balance(user.id)
    keyboard = []
    for key, pkg in PACKAGES.items():
        if currency == "usd":
            price = pkg["usd"]
            label = f"🎮 {pkg['uc']} UC — ${price}"
            affordable = usd_bal >= price
        else:
            price = pkg["afn"]
            label = f"🎮 {pkg['uc']} UC — {price} AFN"
            affordable = afn_bal >= price
        if affordable:
            keyboard.append([InlineKeyboardButton(f"✅ {label}", callback_data=f"pkg_{key}")])
        else:
            keyboard.append([InlineKeyboardButton(f"❌ {label} (insufficient)", callback_data="insufficient")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="buy_uc")])
    await query.edit_message_text(
        "🎮 *Select UC Package:*\n\n"
        "✅ = You can afford\n❌ = Need more balance",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PACKAGE

async def insufficient_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ Insufficient balance! Please top up first.", show_alert=True)
    return SELECT_PACKAGE

async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pkg_key = query.data.split("_", 1)[1]
    pkg = PACKAGES[pkg_key]
    context.user_data["selected_pkg"] = pkg_key
    context.user_data["pkg_details"] = pkg
    currency = context.user_data.get("buy_currency", "usd")
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    await query.edit_message_text(
        f"✅ Selected: *{pkg['uc']} UC* — *{price}*\n\n"
        f"📝 Please enter your *PUBG Mobile Player ID*:\n\n"
        f"_(Find it in PUBG Mobile → Profile)_",
        parse_mode="Markdown"
    )
    return ENTER_PLAYER_ID

async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()
    context.user_data["player_id"] = player_id
    pkg = context.user_data["pkg_details"]
    currency = context.user_data.get("buy_currency", "usd")
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Order", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")],
    ]
    await update.message.reply_text(
        f"📋 *Order Summary*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n"
        f"🎯 Player ID: *{player_id}*\n\n"
        f"Confirm your order?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    pkg = context.user_data["pkg_details"]
    player_id = context.user_data["player_id"]
    currency = context.user_data.get("buy_currency", "usd")
    usd_bal, afn_bal = get_balance(user.id)
    if currency == "usd":
        price = pkg["usd"]
        if usd_bal < price:
            await query.edit_message_text("❌ Insufficient USD balance! Please top up first.")
            return MAIN_MENU
        deduct_balance(user.id, price, "USD")
        price_str = f"${price}"
    else:
        price = pkg["afn"]
        if afn_bal < price:
            await query.edit_message_text("❌ Insufficient AFN balance! Please top up first.")
            return MAIN_MENU
        deduct_balance(user.id, price, "AFN")
        price_str = f"{price} AFN"
    add_transaction(user.id, "purchase", price, currency.upper(), f"{pkg['uc']} UC purchase", "pending")
    usd_new, afn_new = get_balance(user.id)
    admin_msg = (
        f"🔔 *NEW UC ORDER!*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 Telegram ID: {user.id}\n"
        f"🎮 Package: {pkg['uc']} UC\n"
        f"💰 Price: {price_str}\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💳 Paid from wallet"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Admin notify failed: {e}")
    await query.edit_message_text(
        f"✅ *Order Placed Successfully!*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"🎯 Player ID: *{player_id}*\n"
        f"💰 Paid: *{price_str}*\n"
        f"💵 Remaining USD: *${usd_new:.2f}*\n"
        f"🇦🇫 Remaining AFN: *{afn_new:.0f} AFN*\n\n"
        f"⏳ UC will be delivered within *30 minutes*!\n"
        f"Thank you for choosing *Apex Digital House!* 🚀",
        parse_mode="Markdown"
    )
    return MAIN_MENU

# ============ TRANSACTION HISTORY ============
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    transactions = get_transactions(user.id)
    if not transactions:
        text = "📊 *Transaction History*\n\nNo transactions yet."
    else:
        text = "📊 *Last 5 Transactions:*\n\n"
        for tx in transactions:
            type_, amount, currency, desc, status, created_at = tx
            emoji = "➕" if type_ == "topup" else "🎮"
            date = created_at[:10]
            text += f"{emoji} {desc}\n💰 {amount:.2f} {currency} — {status}\n📅 {date}\n\n"
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# ============ SUPPORT ============
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
    await query.edit_message_text(
        f"📞 *Support*\n\n"
        f"Need help? Contact us:\n\n"
        f"💬 WhatsApp: {HESABPAY_NUMBER}\n"
        f"✈️ Telegram: @Wajid_gaming_store\n"
        f"🌐 Website: apexdigitalhouse.com\n\n"
        f"We respond within 30 minutes!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

# ============ MAIN MENU CALLBACK ============
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    usd_bal, afn_bal = get_balance(user.id)
    keyboard = [
        [InlineKeyboardButton("👛 My Wallet", callback_data="wallet"),
         InlineKeyboardButton("➕ Top Up", callback_data="topup")],
        [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
        [InlineKeyboardButton("📊 Transaction History", callback_data="history"),
         InlineKeyboardButton("📞 Support", callback_data="support")],
    ]
    await query.edit_message_text(
        f"🎮 *Apex Digital House*\n\n"
        f"💰 *Your Balance:*\n"
        f"💵 USD: ${usd_bal:.2f}\n"
        f"🇦🇫 AFN: {afn_bal:.0f} AFN\n\n"
        f"What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MAIN_MENU

# ============ CANCEL ============
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ============ MAIN ============
if __name__ == "__main__":
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(show_wallet, pattern="^wallet$"),
                CallbackQueryHandler(show_topup, pattern="^topup$"),
                CallbackQueryHandler(show_buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(show_history, pattern="^history$"),
                CallbackQueryHandler(show_support, pattern="^support$"),
                CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
                CallbackQueryHandler(admin_confirm_topup, pattern="^confirm_topup_"),
                CallbackQueryHandler(admin_reject_topup, pattern="^reject_topup_"),
                CommandHandler("checkpayment", check_payment),
            ],
            SELECT_TOPUP: [
                CallbackQueryHandler(topup_usdt, pattern="^topup_usdt$"),
                CallbackQueryHandler(topup_hesabpay, pattern="^topup_hesabpay$"),
                CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
            ],
            ENTER_TOPUP_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_topup_amount),
            ],
            SEND_HESABPAY_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_hesabpay_screenshot),
            ],
            SELECT_PACKAGE: [
                CallbackQueryHandler(show_packages, pattern="^buy_(usd|afn)$"),
                CallbackQueryHandler(select_package, pattern="^pkg_"),
                CallbackQueryHandler(insufficient_balance, pattern="^insufficient$"),
                CallbackQueryHandler(show_buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order, pattern="^confirm_order$"),
                CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_confirm_topup, pattern="^confirm_topup_"))
    app.add_handler(CallbackQueryHandler(admin_reject_topup, pattern="^reject_topup_"))
    print("🤖 Apex UC Bot with Wallet System is running...")
    app.run_polling()
