from pathlib import Path

code = r'''import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================
# SAFE ENVIRONMENT VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Public business info
USDT_WALLET = os.getenv("USDT_WALLET", "TUUrCxQexypGX8wmXMeNf6mRq2PFFK9Jvz")
HESABPAY_NUMBER = os.getenv("HESABPAY_NUMBER", "+93 789 077 537")
WHATSAPP = os.getenv("WHATSAPP", "+93 789 077 537")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID is missing. Add it in Render Environment Variables.")

# =========================
# UC PACKAGES
# =========================
PACKAGES = {
    "60UC": {"uc": 60, "afn": 60, "usd": 0.95},
    "325UC": {"uc": 325, "afn": 300, "usd": 4.50},
    "660UC": {"uc": 660, "afn": 590, "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

# =========================
# SIMPLE TEMP STORAGE
# WARNING: This resets if Render restarts.
# Later we should move this to Supabase.
# =========================
wallets = {}
pending_wallet_deposits = {}

# Conversation states
SELECT_CURRENCY, SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, SEND_SCREENSHOT, ENTER_WALLET_AMOUNT, SEND_WALLET_SCREENSHOT = range(7)


# =========================
# KEYBOARDS
# =========================
def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
            [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
            [InlineKeyboardButton("📞 Support", callback_data="support")],
        ]
    )


# =========================
# START / MENU
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "✅ Fast delivery\n"
        "✅ Best prices\n"
        "✅ 24/7 support\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    return SELECT_CURRENCY


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    await query.edit_message_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    return SELECT_CURRENCY


# =========================
# SUPPORT
# =========================
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    text = (
        "📞 *Support & Help*\n\n"
        "Having issues? We're here to help!\n\n"
        f"💬 *WhatsApp:* {WHATSAPP}\n"
        f"✈️ *Telegram:* {TELEGRAM_SUPPORT}\n"
        f"🌐 *Website:* apexdigitalhouse.com\n\n"
        "Common issues:\n"
        "• Wrong Player ID entered\n"
        "• Payment not received\n"
        "• UC not delivered\n\n"
        "⏳ We respond within *30 minutes!*"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return SELECT_CURRENCY


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 *Support & Help*\n\n"
        f"💬 WhatsApp: {WHATSAPP}\n"
        f"✈️ Telegram: {TELEGRAM_SUPPORT}\n"
        f"🌐 Website: apexdigitalhouse.com\n\n"
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
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
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
        "Please type the amount in AFN you want to add.\n\n"
        "Example: `500`",
        parse_mode="Markdown",
    )

    return ENTER_WALLET_AMOUNT


async def enter_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid amount like `500`.", parse_mode="Markdown")
        return ENTER_WALLET_AMOUNT

    if amount <= 0:
        await update.message.reply_text("❌ Amount must be more than 0.")
        return ENTER_WALLET_AMOUNT

    if amount < 50:
        await update.message.reply_text("❌ Minimum wallet deposit is 50 AFN.")
        return ENTER_WALLET_AMOUNT

    context.user_data["wallet_deposit_amount"] = amount

    await update.message.reply_text(
        f"📲 *Wallet Deposit Request*\n\n"
        f"Amount: *{amount} AFN*\n\n"
        f"Send payment to HesabPay:\n"
        f"`{HESABPAY_NUMBER}`\n\n"
        "After payment, send your screenshot here.",
        parse_mode="Markdown",
    )

    return SEND_WALLET_SCREENSHOT


async def receive_wallet_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("wallet_deposit_amount")
    user = update.message.from_user

    if not amount:
        await update.message.reply_text("❌ Session expired. Please type /start again.")
        return ConversationHandler.END

    deposit_id = f"WALLET-{user.id}-{update.message.message_id}"

    pending_wallet_deposits[deposit_id] = {
        "user_id": user.id,
        "amount": amount,
        "username": user.username or "N/A",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }

    admin_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm Wallet Payment", callback_data=f"wallet_confirm_{deposit_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"wallet_reject_{deposit_id}"),
            ]
        ]
    )

    admin_msg = (
        "💰 *NEW WALLET DEPOSIT REQUEST*\n\n"
        f"Deposit ID: `{deposit_id}`\n"
        f"👤 Customer: {user.first_name} {user.last_name or ''}\n"
        f"🆔 Username: @{user.username or 'N/A'}\n"
        f"Telegram ID: `{user.id}`\n\n"
        f"Amount: *{amount} AFN*"
    )

    try:
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_keyboard,
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg + "\n\n⚠️ Customer did not send a photo.",
                parse_mode="Markdown",
                reply_markup=admin_keyboard,
            )
    except Exception as e:
        logging.error(f"Admin wallet notification failed: {e}")

    await update.message.reply_text(
        "✅ *Deposit request received!*\n\n"
        f"Amount: *{amount} AFN*\n\n"
        "We are checking your payment now.\n"
        "Once confirmed, your wallet balance will be updated.",
        parse_mode="Markdown",
    )

    context.user_data.clear()
    return ConversationHandler.END


async def wallet_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data

    if data.startswith("wallet_confirm_"):
        deposit_id = data.replace("wallet_confirm_", "")
        deposit = pending_wallet_deposits.get(deposit_id)

        if not deposit:
            await query.edit_message_caption(
                caption="⚠️ This wallet deposit was already handled or not found.",
                parse_mode="Markdown",
            )
            return

        user_id = deposit["user_id"]
        amount = deposit["amount"]

        wallets[user_id] = wallets.get(user_id, 0) + amount
        new_balance = wallets[user_id]

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ *Payment Confirmed!*\n\n"
                    f"*{amount} AFN* has been added to your wallet.\n\n"
                    f"💰 New wallet balance: *{new_balance} AFN*"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Could not notify user: {e}")

        pending_wallet_deposits.pop(deposit_id, None)

        text = (
            "✅ *Wallet Payment Confirmed*\n\n"
            f"Deposit ID: `{deposit_id}`\n"
            f"Amount added: *{amount} AFN*\n"
            f"New balance: *{new_balance} AFN*"
        )

        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text=text, parse_mode="Markdown")

    elif data.startswith("wallet_reject_"):
        deposit_id = data.replace("wallet_reject_", "")
        deposit = pending_wallet_deposits.get(deposit_id)

        if not deposit:
            await query.edit_message_caption(
                caption="⚠️ This wallet deposit was already handled or not found.",
                parse_mode="Markdown",
            )
            return

        user_id = deposit["user_id"]
        amount = deposit["amount"]

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ *Payment Not Confirmed*\n\n"
                    f"Your wallet deposit request for *{amount} AFN* was not approved.\n\n"
                    "Please contact support if you think this is a mistake."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Could not notify user: {e}")

        pending_wallet_deposits.pop(deposit_id, None)

        text = (
            "❌ *Wallet Deposit Rejected*\n\n"
            f"Deposit ID: `{deposit_id}`\n"
            f"Amount: *{amount} AFN*"
        )

        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text=text, parse_mode="Markdown")


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

    currency = query.data.split("_")[1]
    context.user_data["currency"] = currency

    keyboard = []
    for key, pkg in PACKAGES.items():
        if currency == "usd":
            label = f"🎮 {pkg['uc']} UC — ${pkg['usd']}"
        else:
            label = f"🎮 {pkg['uc']} UC — {pkg['afn']} AFN"
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
    pkg = PACKAGES[pkg_key]

    context.user_data["package"] = pkg_key
    context.user_data["pkg_details"] = pkg

    currency = context.user_data["currency"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

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
            "❌ Please enter a valid numeric PUBG Player ID.",
            parse_mode="Markdown",
        )
        return ENTER_PLAYER_ID

    context.user_data["player_id"] = player_id

    currency = context.user_data["currency"]
    pkg = context.user_data["pkg_details"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

    if currency == "usd":
        keyboard = [
            [InlineKeyboardButton("💎 USDT (TRC20)", callback_data="pay_usdt")],
            [InlineKeyboardButton("🔙 Start Over", callback_data="buy_uc")],
        ]
    else:
        user_id = update.message.from_user.id
        balance = wallets.get(user_id, 0)

        keyboard = [
            [InlineKeyboardButton("💰 Pay From Wallet", callback_data="pay_wallet")],
            [InlineKeyboardButton("📲 HesabPay", callback_data="pay_hesabpay")],
            [InlineKeyboardButton("⚡ AtomPay", callback_data="pay_atompay")],
            [InlineKeyboardButton("🏦 Azizi Bank", callback_data="pay_azizi")],
            [InlineKeyboardButton("🔙 Start Over", callback_data="buy_uc")],
        ]

        await update.message.reply_text(
            f"💰 Your wallet balance: *{balance} AFN*",
            parse_mode="Markdown",
        )

    await update.message.reply_text(
        f"✅ Player ID: *{player_id}*\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n\n"
        "⚠️ *Please double-check your Player ID!*\n"
        "Wrong ID = UC sent to wrong account!\n\n"
        "Select payment method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_PAYMENT


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payment = query.data.split("_", 1)[1]
    context.user_data["payment"] = payment

    pkg = context.user_data["pkg_details"]
    currency = context.user_data["currency"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    player_id = context.user_data["player_id"]

    user_id = query.from_user.id

    # Wallet payment for AFN orders
    if payment == "wallet":
        if currency != "afn":
            await query.edit_message_text("❌ Wallet payment is only available for AFN orders.")
            return ConversationHandler.END

        amount = pkg["afn"]
        balance = wallets.get(user_id, 0)

        if balance < amount:
            await query.edit_message_text(
                f"❌ *Not enough wallet balance.*\n\n"
                f"Your balance: *{balance} AFN*\n"
                f"Order amount: *{amount} AFN*\n\n"
                "Please add balance first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("➕ Add Balance", callback_data="add_wallet_balance")],
                        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
                    ]
                ),
            )
            return SELECT_CURRENCY

        wallets[user_id] = balance - amount
        new_balance = wallets[user_id]

        admin_msg = (
            "🎮 *NEW UC ORDER PAID BY WALLET*\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"💰 Paid: *{amount} AFN*\n"
            f"🎯 Player ID: `{player_id}`\n"
            f"💰 New wallet balance: *{new_balance} AFN*"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Admin UC wallet order notify failed: {e}")

        await query.edit_message_text(
            "✅ *Payment Confirmed From Wallet!*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n"
            f"💰 Paid: *{amount} AFN*\n"
            f"💰 Remaining wallet balance: *{new_balance} AFN*\n\n"
            "Your UC order is now being processed.",
            parse_mode="Markdown",
        )

        context.user_data.clear()
        return ConversationHandler.END

    if payment == "usdt":
        info = (
            "💎 *Send USDT (TRC20) to:*\n\n"
            f"`{USDT_WALLET}`\n\n"
            f"💰 Amount: *{price}*\n\n"
            "⚠️ TRC20 network only!\n"
            "⚠️ Send exact amount!"
        )
    elif payment == "hesabpay":
        info = (
            "📲 *Send via HesabPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    elif payment == "atompay":
        info = (
            "⚡ *Send via AtomPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    else:
        info = (
            "🏦 *Send via Azizi Bank to:*\n\n"
            "Account: Apex Digital House\n"
            f"Contact for details: {HESABPAY_NUMBER}\n\n"
            f"💰 Amount: *{price}*"
        )

    await query.edit_message_text(
        "📋 *Order Summary:*\n"
        f"🎮 {pkg['uc']} UC\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💰 {price}\n\n"
        f"{info}\n\n"
        "📸 *After payment, send your screenshot here!*",
        parse_mode="Markdown",
    )

    return SEND_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pkg = context.user_data.get("pkg_details")
    currency = context.user_data.get("currency", "usd")
    player_id = context.user_data.get("player_id", "Unknown")
    payment = context.user_data.get("payment", "Unknown")

    if not pkg:
        await update.message.reply_text("❌ Session expired. Please type /start to begin again.")
        return ConversationHandler.END

    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    user = update.message.from_user

    admin_msg = (
        "🔔 *NEW UC ORDER!*\n\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"🆔 @{user.username or 'N/A'} ({user.id})\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💳 Payment: *{payment.upper()}*"
    )

    try:
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=admin_msg,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg + "\n\n⚠️ No screenshot received!",
                parse_mode="Markdown",
            )
    except Exception as e:
        logging.error(f"Admin notify failed: {e}")

    await update.message.reply_text(
        "✅ *Order Received!*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"🎯 Player ID: *{player_id}*\n"
        f"💰 Amount: *{price}*\n\n"
        "⏳ UC will be sent within *30 minutes*!\n\n"
        "Need help? Type /support\n"
        "New order? Type /start",
        parse_mode="Markdown",
    )

    context.user_data.clear()
    return ConversationHandler.END


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
# MAIN APP
# =========================
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [
                CallbackQueryHandler(buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(wallet, pattern="^wallet$"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(support, pattern="^support$"),
                CallbackQueryHandler(select_currency, pattern="^currency_"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            SELECT_PACKAGE: [
                CallbackQueryHandler(select_package, pattern="^pkg_"),
                CallbackQueryHandler(buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
                CallbackQueryHandler(buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
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
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("support", support_command),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CallbackQueryHandler(wallet_admin_action, pattern="^wallet_(confirm|reject)_"))

    print("🤖 Apex UC Bot is running...")
    app.run_polling()
'''
path = Path("/mnt/data/apex_uc_bot_wallet.py")
path.write_text(code, encoding="utf-8")
print(str(path))
