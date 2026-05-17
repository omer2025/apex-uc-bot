import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = "8602835129:AAFGXQsEUBpWChMbZ9K5iy7wMEOLfM3wwaw"
ADMIN_ID = 8556241073
USDT_WALLET = "TUUrCxQexypGX8wmXMeNf6mRq2PFFK9Jvz"
HESABPAY_NUMBER = "+93 789 077 537"
WHATSAPP = "+93 789 077 537"
TELEGRAM_SUPPORT = "@Wajid_gaming_store"

PACKAGES = {
    "60UC":   {"uc": 60,   "afn": 60,   "usd": 0.95},
    "325UC":  {"uc": 325,  "afn": 300,  "usd": 4.50},
    "660UC":  {"uc": 660,  "afn": 590,  "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

SELECT_CURRENCY, SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, SEND_SCREENSHOT = range(5)

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
        [InlineKeyboardButton("📞 Support", callback_data="support")],
    ])

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
        reply_markup=main_keyboard()
    )
    return SELECT_CURRENCY

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
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_CURRENCY

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 *Support & Help*\n\n"
        f"💬 WhatsApp: {WHATSAPP}\n"
        f"✈️ Telegram: {TELEGRAM_SUPPORT}\n"
        f"🌐 Website: apexdigitalhouse.com\n\n"
        "⏳ We respond within *30 minutes!*",
        parse_mode="Markdown"
    )

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
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        f"📝 Please enter your *PUBG Mobile Player ID*\n\n"
        f"How to find your Player ID:\n"
        f"1️⃣ Open PUBG Mobile\n"
        f"2️⃣ Tap your profile picture\n"
        f"3️⃣ Your ID is shown below your name\n\n"
        f"⌨️ Type your Player ID now:",
        parse_mode="Markdown"
    )
    return ENTER_PLAYER_ID

async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()
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
        keyboard = [
            [InlineKeyboardButton("📲 HesabPay", callback_data="pay_hesabpay")],
            [InlineKeyboardButton("⚡ AtomPay", callback_data="pay_atompay")],
            [InlineKeyboardButton("🏦 Azizi Bank", callback_data="pay_azizi")],
            [InlineKeyboardButton("🔙 Start Over", callback_data="buy_uc")],
        ]

    await update.message.reply_text(
        f"✅ Player ID: *{player_id}*\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{price}*\n\n"
        f"⚠️ *Please double-check your Player ID!*\n"
        f"Wrong ID = UC sent to wrong account!\n\n"
        f"Select payment method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
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

    if payment == "usdt":
        info = (
            f"💎 *Send USDT (TRC20) to:*\n\n"
            f"`{USDT_WALLET}`\n\n"
            f"💰 Amount: *{price}*\n\n"
            f"⚠️ TRC20 network only!\n"
            f"⚠️ Send exact amount!"
        )
    elif payment == "hesabpay":
        info = (
            f"📲 *Send via HesabPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    elif payment == "atompay":
        info = (
            f"⚡ *Send via AtomPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    else:
        info = (
            f"🏦 *Send via Azizi Bank to:*\n\n"
            f"Account: Apex Digital House\n"
            f"Contact for details: {HESABPAY_NUMBER}\n\n"
            f"💰 Amount: *{price}*"
        )

    await query.edit_message_text(
        f"📋 *Order Summary:*\n"
        f"🎮 {pkg['uc']} UC\n"
        f"🎯 Player ID: `{player_id}`\n"
        f"💰 {price}\n\n"
        f"{info}\n\n"
        f"📸 *After payment, send your screenshot here!*",
        parse_mode="Markdown"
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
        f"🔔 *NEW UC ORDER!*\n\n"
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
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg + "\n\n⚠️ No screenshot received!",
                parse_mode="Markdown"
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
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "🎮 *Welcome to Apex Digital House!*\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return SELECT_CURRENCY

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled.\n\nType /start to begin a new order.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [
                CallbackQueryHandler(buy_uc, pattern="^buy_uc$"),
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
            ],
            SEND_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_screenshot),
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
    print("🤖 Apex UC Bot is running...")
    app.run_polling()
