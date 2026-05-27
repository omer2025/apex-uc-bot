import os
import logging
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

USDT_WALLET = os.getenv("USDT_WALLET", "YOUR_USDT_WALLET")
HESABPAY_NUMBER = os.getenv("HESABPAY_NUMBER", "+93 789 077 537")
WHATSAPP = os.getenv("WHATSAPP", "+93 789 077 537")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing. Set it in environment variables.")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID missing. Set it in environment variables.")

# =========================
# UC PACKAGES
# =========================
PACKAGES = {
    "60UC":   {"uc": 60,   "afn": 60,   "usd": 0.95},
    "325UC":  {"uc": 325,  "afn": 300,  "usd": 4.50},
    "660UC":  {"uc": 660,  "afn": 590,  "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

# =========================
# IN-MEMORY STORAGE
# WARNING: Resets on restart. Move to a database (e.g. Supabase) for production.
#
# wallets               → { user_id: balance_afn }
# pending_wallet_deposits → { deposit_id: {...} }
# pending_orders        → { order_id: {...} }
# code_store            → { pkg_key: ["CODE1", "CODE2", ...] }
# =========================
wallets: dict = {}
pending_wallet_deposits: dict = {}
pending_orders: dict = {}
code_store: dict = {key: [] for key in PACKAGES}   # pre-fill keys

# =========================
# CONVERSATION STATES
# =========================
(
    SELECT_CURRENCY,
    SELECT_PACKAGE,
    ENTER_PLAYER_ID,
    SELECT_PAYMENT,
    SEND_SCREENSHOT,
    ENTER_WALLET_AMOUNT,
    SEND_WALLET_SCREENSHOT,
    ADMIN_ADD_CODES,
) = range(8)


# =========================
# HELPERS
# =========================
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Buy UC",       callback_data="buy_uc")],
        [InlineKeyboardButton("💰 My Wallet",    callback_data="wallet")],
        [InlineKeyboardButton("📞 Support",      callback_data="support")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    """Extra keyboard shown only to the admin in /start."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Buy UC",          callback_data="buy_uc")],
        [InlineKeyboardButton("💰 My Wallet",       callback_data="wallet")],
        [InlineKeyboardButton("📞 Support",         callback_data="support")],
        [InlineKeyboardButton("🗄️ Manage UC Codes", callback_data="admin_codes")],
    ])


# =========================
# START / MENU
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    is_admin = update.message.from_user.id == ADMIN_ID
    kb = admin_keyboard() if is_admin else main_keyboard()

    await update.message.reply_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "✅ Fast delivery\n"
        "✅ Best prices\n"
        "✅ 24/7 support\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return SELECT_CURRENCY


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    is_admin = query.from_user.id == ADMIN_ID
    kb = admin_keyboard() if is_admin else main_keyboard()

    await query.edit_message_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return SELECT_CURRENCY


# =========================
# SUPPORT
# =========================
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    await query.edit_message_text(
        f"📞 *Support & Help*\n\n"
        f"💬 WhatsApp: {WHATSAPP}\n"
        f"✈️ Telegram: {TELEGRAM_SUPPORT}\n\n"
        "⏳ We respond within *30 minutes!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_CURRENCY


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 *Support & Help*\n\n"
        f"💬 WhatsApp: {WHATSAPP}\n"
        f"✈️ Telegram: {TELEGRAM_SUPPORT}\n\n"
        "⏳ We respond within *30 minutes!*",
        parse_mode="Markdown",
    )


# =========================
# WALLET
# =========================
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = wallets.get(user_id, 0)

    keyboard = [
        [InlineKeyboardButton("➕ Add Balance", callback_data="add_wallet_balance")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        f"💰 *Your Wallet*\n\n"
        f"Balance: *{balance} AFN*\n\n"
        "Choose an option:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_CURRENCY


async def add_wallet_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ *Add Wallet Balance*\n\n"
        "Type the amount in AFN you want to add.\n\n"
        "Example: `500`\n"
        "Minimum: 50 AFN",
        parse_mode="Markdown",
    )
    return ENTER_WALLET_AMOUNT


async def enter_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number like `500`.", parse_mode="Markdown")
        return ENTER_WALLET_AMOUNT

    if amount < 50:
        await update.message.reply_text("❌ Minimum deposit is 50 AFN.")
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
    user = update.message.from_user

    if not amount:
        await update.message.reply_text("❌ Session expired. Please type /start again.")
        return ConversationHandler.END

    deposit_id = f"WALLET-{user.id}-{update.message.message_id}"
    pending_wallet_deposits[deposit_id] = {
        "user_id":    user.id,
        "amount":     amount,
        "username":   user.username or "N/A",
        "first_name": user.first_name or "",
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"wallet_confirm_{deposit_id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"wallet_reject_{deposit_id}"),
    ]])
    caption = (
        f"💰 *WALLET DEPOSIT REQUEST*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 Telegram ID: `{user.id}`\n"
        f"Deposit ID: `{deposit_id}`\n\n"
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
            caption + "\n\n⚠️ No screenshot sent.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    await update.message.reply_text(
        "✅ *Deposit request received!*\n\n"
        f"Amount: *{amount} AFN*\n\n"
        "Waiting for admin to confirm your payment. ⏳",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def wallet_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data

    if data.startswith("wallet_confirm_"):
        deposit_id = data.replace("wallet_confirm_", "")
        deposit = pending_wallet_deposits.get(deposit_id)
        if not deposit:
            await query.edit_message_caption(caption="⚠️ Already handled or not found.")
            return

        user_id = deposit["user_id"]
        amount  = deposit["amount"]
        wallets[user_id] = wallets.get(user_id, 0) + amount
        new_balance = wallets[user_id]

        await context.bot.send_message(
            user_id,
            f"✅ *Payment Confirmed!*\n\n"
            f"*{amount} AFN* added to your wallet.\n"
            f"💰 New balance: *{new_balance} AFN*",
            parse_mode="Markdown",
        )
        pending_wallet_deposits.pop(deposit_id, None)
        caption = f"✅ Confirmed — {amount} AFN added. New balance: {new_balance} AFN"
        if query.message.photo:
            await query.edit_message_caption(caption=caption)
        else:
            await query.edit_message_text(caption)

    elif data.startswith("wallet_reject_"):
        deposit_id = data.replace("wallet_reject_", "")
        deposit = pending_wallet_deposits.get(deposit_id)
        if not deposit:
            await query.edit_message_caption(caption="⚠️ Already handled or not found.")
            return

        user_id = deposit["user_id"]
        amount  = deposit["amount"]
        await context.bot.send_message(
            user_id,
            f"❌ *Payment Rejected*\n\n"
            f"Your deposit of *{amount} AFN* was not approved.\n"
            "Contact support if you think this is a mistake.",
            parse_mode="Markdown",
        )
        pending_wallet_deposits.pop(deposit_id, None)
        caption = f"❌ Rejected — {amount} AFN deposit."
        if query.message.photo:
            await query.edit_message_caption(caption=caption)
        else:
            await query.edit_message_text(caption)


# =========================
# ADMIN — CODE MANAGEMENT
# =========================
async def admin_codes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin the code inventory and options to add codes."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    lines = ["🗄️ *UC Code Inventory*\n"]
    keyboard = []
    for key, pkg in PACKAGES.items():
        count = len(code_store.get(key, []))
        status = "✅" if count > 0 else "❌ EMPTY"
        lines.append(f"{status} *{pkg['uc']} UC* — {count} code(s) available")
        keyboard.append([InlineKeyboardButton(
            f"➕ Add codes for {pkg['uc']} UC",
            callback_data=f"admin_addcodes_{key}",
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_CURRENCY


async def admin_start_add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin picked a package to add codes to."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    pkg_key = query.data.replace("admin_addcodes_", "")
    context.user_data["adding_codes_for"] = pkg_key
    pkg = PACKAGES[pkg_key]

    await query.edit_message_text(
        f"➕ *Adding codes for {pkg['uc']} UC*\n\n"
        "Send one code per line. Example:\n\n"
        "`CODE-ABCD-1234\nCODE-EFGH-5678`\n\n"
        "Type /cancel to stop.",
        parse_mode="Markdown",
    )
    return ADMIN_ADD_CODES


async def admin_receive_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin sends lines of codes; store them."""
    if update.message.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    pkg_key = context.user_data.get("adding_codes_for")
    if not pkg_key:
        await update.message.reply_text("❌ Session lost. Start again from the menu.")
        return ConversationHandler.END

    raw   = update.message.text.strip()
    codes = [c.strip() for c in raw.splitlines() if c.strip()]

    if not codes:
        await update.message.reply_text("❌ No valid codes found. Please send one code per line.")
        return ADMIN_ADD_CODES

    code_store.setdefault(pkg_key, []).extend(codes)
    pkg = PACKAGES[pkg_key]

    await update.message.reply_text(
        f"✅ *{len(codes)} code(s) added* for *{pkg['uc']} UC*!\n\n"
        f"Total in stock: *{len(code_store[pkg_key])} code(s)*",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# =========================
# BUY UC
# =========================
async def buy_uc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("💵 Pay in USD (USDT)", callback_data="currency_usd")],
        [InlineKeyboardButton("🇦🇫 Pay in Afghani (AFN)", callback_data="currency_afn")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "🎮 *Buy PUBG UC*\n\nSelect your payment currency:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_CURRENCY


async def select_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency = "usd" if "usd" in query.data else "afn"
    context.user_data["currency"] = currency

    keyboard = []
    for key, pkg in PACKAGES.items():
        count = len(code_store.get(key, []))
        stock = f"({count} in stock)" if count > 0 else "(OUT OF STOCK)"
        label = (
            f"🎮 {pkg['uc']} UC — ${pkg['usd']} {stock}"
            if currency == "usd"
            else f"🎮 {pkg['uc']} UC — {pkg['afn']} AFN {stock}"
        )
        keyboard.append([InlineKeyboardButton(label, callback_data=f"pkg_{key}")])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="buy_uc")])
    await query.edit_message_text(
        "🎮 *Select UC Package:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_PACKAGE


async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pkg_key = query.data.split("_", 1)[1]
    pkg     = PACKAGES[pkg_key]

    # Check stock
    if not code_store.get(pkg_key):
        await query.answer("⚠️ This package is currently out of stock!", show_alert=True)
        return SELECT_PACKAGE

    context.user_data["package"] = pkg_key
    currency = context.user_data["currency"]
    price    = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

    await query.edit_message_text(
        f"✅ Selected: *{pkg['uc']} UC* — *{price}*\n\n"
        "📝 Please enter your *PUBG Mobile Player ID*\n\n"
        "How to find your Player ID:\n"
        "1️⃣ Open PUBG Mobile\n"
        "2️⃣ Tap your profile picture\n"
        "3️⃣ Your ID is shown below your name\n\n"
        "⌨️ Type your Player ID now:",
        parse_mode="Markdown",
    )
    return ENTER_PLAYER_ID


async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()

    if not player_id.isdigit() or len(player_id) < 5:
        await update.message.reply_text(
            "❌ Please enter a valid numeric PUBG Player ID (at least 5 digits)."
        )
        return ENTER_PLAYER_ID

    context.user_data["player_id"] = player_id
    currency = context.user_data["currency"]
    pkg_key  = context.user_data["package"]
    pkg      = PACKAGES[pkg_key]
    price    = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    user_id  = update.message.from_user.id
    balance  = wallets.get(user_id, 0)

    if currency == "usd":
        keyboard = [
            [InlineKeyboardButton("💎 USDT (TRC20)", callback_data="pay_usdt")],
            [InlineKeyboardButton("🔙 Start Over",    callback_data="buy_uc")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("💰 Pay From Wallet", callback_data="pay_wallet")],
            [InlineKeyboardButton("📲 HesabPay",        callback_data="pay_hesabpay")],
            [InlineKeyboardButton("🔙 Start Over",      callback_data="buy_uc")],
        ]

    await update.message.reply_text(
        f"✅ Player ID: *{player_id}*\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n\n"
        f"💳 Your wallet balance: *{balance} AFN*\n\n"
        "⚠️ *Double-check your Player ID!* Wrong ID = UC sent to wrong account!\n\n"
        "Select payment method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_PAYMENT


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()

    payment  = query.data.split("_", 1)[1]
    pkg_key  = context.user_data["package"]
    pkg      = PACKAGES[pkg_key]
    currency = context.user_data["currency"]
    player_id = context.user_data["player_id"]
    user_id  = query.from_user.id
    price    = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

    # ── Instant wallet payment ──────────────────────────────────────────────
    if payment == "wallet":
        if currency != "afn":
            await query.edit_message_text("❌ Wallet payment is only available for AFN orders.")
            return ConversationHandler.END

        amount  = pkg["afn"]
        balance = wallets.get(user_id, 0)

        if balance < amount:
            await query.edit_message_text(
                f"❌ *Not enough wallet balance.*\n\n"
                f"Your balance: *{balance} AFN*\n"
                f"Order amount: *{amount} AFN*\n\n"
                "Please add balance first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Balance",  callback_data="add_wallet_balance")],
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
                ]),
            )
            return SELECT_CURRENCY

        # Check stock again right before delivery
        if not code_store.get(pkg_key):
            await query.edit_message_text(
                "❌ *Out of stock!*\n\nSorry, this package just ran out. Contact support.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        # Deduct balance and pop code
        wallets[user_id]  = balance - amount
        new_balance       = wallets[user_id]
        code              = code_store[pkg_key].pop(0)

        # Notify admin
        await context.bot.send_message(
            ADMIN_ID,
            f"🎮 *UC ORDER (WALLET PAID — AUTO DELIVERED)*\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"💰 Paid: *{amount} AFN* (from wallet)\n"
            f"🎯 Player ID: `{player_id}`\n"
            f"🔑 Code sent: `{code}`\n"
            f"💰 Remaining wallet balance: *{new_balance} AFN*",
            parse_mode="Markdown",
        )

        # Deliver code to user
        await query.edit_message_text(
            f"✅ *Payment Confirmed & UC Code Delivered!*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n"
            f"💰 Paid: *{amount} AFN*\n"
            f"💰 Remaining balance: *{new_balance} AFN*\n\n"
            f"🔑 *Your UC Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫",
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ── Manual payment (screenshot required) ───────────────────────────────
    if payment == "usdt":
        payment_text = (
            f"💎 *Send USDT (TRC20) to:*\n\n"
            f"`{USDT_WALLET}`\n\n"
            f"💰 Amount: *{price}*\n\n"
            "⚠️ TRC20 network only! Send exact amount!"
        )
    else:  # hesabpay
        payment_text = (
            f"📲 *Send via HesabPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )

    context.user_data["payment"] = payment

    await query.edit_message_text(
        f"📋 *Order Summary*\n"
        f"🎮 {pkg['uc']} UC\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💰 {price}\n\n"
        f"{payment_text}\n\n"
        "📸 *After payment, send your screenshot here!*",
        parse_mode="Markdown",
    )
    return SEND_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pkg_key   = context.user_data.get("package")
    player_id = context.user_data.get("player_id", "Unknown")
    payment   = context.user_data.get("payment", "Unknown")

    if not pkg_key:
        await update.message.reply_text("❌ Session expired. Please type /start to begin again.")
        return ConversationHandler.END

    pkg      = PACKAGES[pkg_key]
    currency = context.user_data.get("currency", "usd")
    price    = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    user     = update.message.from_user

    order_id = f"ORDER-{user.id}-{update.message.message_id}"
    pending_orders[order_id] = {
        "user_id":   user.id,
        "pkg_key":   pkg_key,
        "player_id": player_id,
        "payment":   payment,
        "price":     price,
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm & Send Code", callback_data=f"order_confirm_{order_id}"),
        InlineKeyboardButton("❌ Reject",              callback_data=f"order_reject_{order_id}"),
    ]])

    admin_caption = (
        f"🔔 *NEW UC ORDER*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 Telegram ID: `{user.id}`\n"
        f"Order ID: `{order_id}`\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💳 Payment: *{payment.upper()}*\n\n"
        f"🗄️ Codes in stock for this package: *{len(code_store.get(pkg_key, []))}*"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=admin_caption,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            ADMIN_ID,
            admin_caption + "\n\n⚠️ No screenshot received!",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    await update.message.reply_text(
        "✅ *Order Received!*\n\n"
        f"🎮 {pkg['uc']} UC\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💰 {price}\n\n"
        "⏳ We are checking your payment.\n"
        "Your UC code will be sent to you here once confirmed!\n\n"
        "Need help? Type /support",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# =========================
# ADMIN — ORDER CONFIRMATION
# =========================
async def order_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data

    if data.startswith("order_confirm_"):
        order_id = data.replace("order_confirm_", "")
        order    = pending_orders.get(order_id)
        if not order:
            if query.message.photo:
                await query.edit_message_caption(caption="⚠️ Order already handled or not found.")
            else:
                await query.edit_message_text("⚠️ Order already handled or not found.")
            return

        pkg_key   = order["pkg_key"]
        pkg       = PACKAGES[pkg_key]
        user_id   = order["user_id"]
        player_id = order["player_id"]

        # Check stock
        if not code_store.get(pkg_key):
            if query.message.photo:
                await query.edit_message_caption(
                    caption=f"❌ Out of stock for {pkg['uc']} UC! Add codes first."
                )
            else:
                await query.edit_message_text(
                    f"❌ Out of stock for {pkg['uc']} UC! Add codes first."
                )
            return

        # Pop a code
        code = code_store[pkg_key].pop(0)
        remaining = len(code_store[pkg_key])

        # Send code to user
        await context.bot.send_message(
            user_id,
            f"✅ *Payment Confirmed! Here is your UC Code:*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"🔑 *Your Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫\n"
            "New order? Type /start",
            parse_mode="Markdown",
        )

        pending_orders.pop(order_id, None)
        confirm_text = (
            f"✅ *Order Confirmed & Code Sent*\n\n"
            f"Order ID: `{order_id}`\n"
            f"🔑 Code sent: `{code}`\n"
            f"🗄️ Remaining stock for {pkg['uc']} UC: *{remaining}*"
        )
        if query.message.photo:
            await query.edit_message_caption(caption=confirm_text, parse_mode="Markdown")
        else:
            await query.edit_message_text(confirm_text, parse_mode="Markdown")

    elif data.startswith("order_reject_"):
        order_id = data.replace("order_reject_", "")
        order    = pending_orders.get(order_id)
        if not order:
            if query.message.photo:
                await query.edit_message_caption(caption="⚠️ Order already handled or not found.")
            else:
                await query.edit_message_text("⚠️ Order already handled or not found.")
            return

        user_id = order["user_id"]
        pkg     = PACKAGES[order["pkg_key"]]

        await context.bot.send_message(
            user_id,
            f"❌ *Payment Not Confirmed*\n\n"
            f"Your order for *{pkg['uc']} UC* was rejected.\n\n"
            "Please contact support if you think this is a mistake.\n"
            f"📞 {TELEGRAM_SUPPORT}",
            parse_mode="Markdown",
        )
        pending_orders.pop(order_id, None)
        reject_text = f"❌ Order rejected — {pkg['uc']} UC\nOrder ID: `{order_id}`"
        if query.message.photo:
            await query.edit_message_caption(caption=reject_text, parse_mode="Markdown")
        else:
            await query.edit_message_text(reject_text, parse_mode="Markdown")


# =========================
# CANCEL
# =========================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled.\n\nType /start to begin a new order.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# =========================
# ADMIN COMMANDS
# =========================
async def admin_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: /stock — show current code inventory."""
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return

    lines = ["🗄️ *Current UC Code Inventory*\n"]
    for key, pkg in PACKAGES.items():
        count  = len(code_store.get(key, []))
        status = "✅" if count > 0 else "❌ EMPTY"
        lines.append(f"{status} *{pkg['uc']} UC* — {count} code(s)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =========================
# MAIN APP
# =========================
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [
                CallbackQueryHandler(buy_uc,             pattern="^buy_uc$"),
                CallbackQueryHandler(wallet,             pattern="^wallet$"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(support,            pattern="^support$"),
                CallbackQueryHandler(select_currency,    pattern="^currency_"),
                CallbackQueryHandler(admin_codes_menu,   pattern="^admin_codes$"),
                CallbackQueryHandler(main_menu,          pattern="^main_menu$"),
            ],
            SELECT_PACKAGE: [
                CallbackQueryHandler(select_currency,    pattern="^currency_"),
                CallbackQueryHandler(select_package,     pattern="^pkg_"),
                CallbackQueryHandler(buy_uc,             pattern="^buy_uc$"),
                CallbackQueryHandler(main_menu,          pattern="^main_menu$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment,     pattern="^pay_"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(buy_uc,             pattern="^buy_uc$"),
                CallbackQueryHandler(main_menu,          pattern="^main_menu$"),
            ],
            SEND_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_screenshot),
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
        },
        fallbacks=[
            CommandHandler("cancel",  cancel),
            CommandHandler("start",   start),
            CommandHandler("support", support_command),
            CommandHandler("stock",   admin_stock_command),
            # Admin code management via callback (re-entry from any state)
            CallbackQueryHandler(admin_codes_menu,      pattern="^admin_codes$"),
            CallbackQueryHandler(admin_start_add_codes, pattern="^admin_addcodes_"),
            CallbackQueryHandler(main_menu,             pattern="^main_menu$"),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("stock",   admin_stock_command))
    app.add_handler(CallbackQueryHandler(wallet_admin_action, pattern="^wallet_(confirm|reject)_"))
    app.add_handler(CallbackQueryHandler(order_admin_action,  pattern="^order_(confirm|reject)_"))

    print("🤖 Apex UC Bot is running...")
    app.run_polling()
