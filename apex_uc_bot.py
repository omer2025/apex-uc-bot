import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ============ CONFIGURATION ============
BOT_TOKEN = "8602835129:AAFGXQsEUBpWChMbZ9K5iy7wMEOLfM3wwaw"
ADMIN_ID = 8556241073
USDT_WALLET = "TUUrCxQexypGX8wmXMeNf6mRq2PFFK9Jvz"
HESABPAY_NUMBER = "+93 789 077 537"  # Update this with your HesabPay number

# ============ UC PACKAGES ============
PACKAGES = {
    "60UC": {"uc": 60, "afn": 60, "usd": 0.95},
    "325UC": {"uc": 325, "afn": 300, "usd": 4.50},
    "660UC": {"uc": 660, "afn": 590, "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

# ============ STATES ============
SELECT_CURRENCY, SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, SEND_SCREENSHOT = range(5)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ============ START ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💵 Pay in USD (USDT)", callback_data="currency_usd")],
        [InlineKeyboardButton("🇦🇫 Pay in Afghani (AFN)", callback_data="currency_afn")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎮 *Welcome to Apex Digital House UC Store!*\n\n"
        "We provide instant PUBG Mobile UC top-ups.\n\n"
        "Please select your preferred currency:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    return SELECT_CURRENCY

# ============ SELECT CURRENCY ============
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
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_start")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎮 *Select your UC Package:*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    return SELECT_PACKAGE

# ============ SELECT PACKAGE ============
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
        f"✅ You selected: *{pkg['uc']} UC* — *{price}*\n\n"
        f"📝 Please enter your *PUBG Mobile Player ID*:\n\n"
        f"_(You can find your Player ID in PUBG Mobile → Profile)_",
        parse_mode="Markdown",
    )
    return ENTER_PLAYER_ID

# ============ ENTER PLAYER ID ============
async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text
    context.user_data["player_id"] = player_id
    currency = context.user_data["currency"]

    if currency == "usd":
        keyboard = [
            [InlineKeyboardButton("💎 USDT (TRC20)", callback_data="pay_usdt")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📲 HesabPay", callback_data="pay_hesabpay")],
            [InlineKeyboardButton("⚡ AtomPay", callback_data="pay_atompay")],
            [InlineKeyboardButton("🏦 Azizi Bank", callback_data="pay_azizi")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Player ID saved: *{player_id}*\n\n"
        f"💳 *Select your payment method:*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    return SELECT_PAYMENT

# ============ SELECT PAYMENT ============
async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment = query.data.split("_", 1)[1]
    context.user_data["payment"] = payment

    pkg = context.user_data["pkg_details"]
    currency = context.user_data["currency"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

    if payment == "usdt":
        payment_info = (
            f"💎 *Send USDT (TRC20) to:*\n\n"
            f"`{USDT_WALLET}`\n\n"
            f"💰 Amount: *{price}*"
        )
    elif payment == "hesabpay":
        payment_info = (
            f"📲 *Send via HesabPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    elif payment == "atompay":
        payment_info = (
            f"⚡ *Send via AtomPay to:*\n\n"
            f"`{HESABPAY_NUMBER}`\n\n"
            f"💰 Amount: *{price}*"
        )
    elif payment == "azizi":
        payment_info = (
            f"🏦 *Send via Azizi Bank to:*\n\n"
            f"Account: Apex Digital House\n"
            f"Contact us for bank details: {HESABPAY_NUMBER}\n\n"
            f"💰 Amount: *{price}*"
        )

    await query.edit_message_text(
        f"{payment_info}\n\n"
        f"📸 After payment, please send us your *payment screenshot* to confirm your order.",
        parse_mode="Markdown",
    )
    return SEND_SCREENSHOT

# ============ RECEIVE SCREENSHOT ============
async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pkg = context.user_data["pkg_details"]
    currency = context.user_data["currency"]
    player_id = context.user_data["player_id"]
    payment = context.user_data["payment"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    user = update.message.from_user

    # Notify admin
    admin_message = (
        f"🔔 *NEW UC ORDER!*\n\n"
        f"👤 Customer: {user.first_name} {user.last_name or ''}\n"
        f"🆔 Telegram: @{user.username or 'N/A'} ({user.id})\n"
        f"🎮 Package: {pkg['uc']} UC\n"
        f"💰 Price: {price}\n"
        f"🎯 Player ID: {player_id}\n"
        f"💳 Payment: {payment.upper()}\n"
    )

    try:
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=update.message.photo[-1].file_id,
                caption=admin_message,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message + "\n⚠️ No screenshot received!",
                parse_mode="Markdown",
            )
    except Exception as e:
        logging.error(f"Failed to notify admin: {e}")

    # Confirm to customer
    await update.message.reply_text(
        "✅ *Order Received!*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"🎯 Player ID: *{player_id}*\n"
        f"💰 Amount: *{price}*\n\n"
        "⏳ Your UC will be sent within *30 minutes*.\n"
        "Thank you for choosing *Apex Digital House!* 🚀\n\n"
        "Type /start to make another order.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END

# ============ BACK TO START ============
async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Pay in USD (USDT)", callback_data="currency_usd")],
        [InlineKeyboardButton("🇦🇫 Pay in Afghani (AFN)", callback_data="currency_afn")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎮 *Welcome to Apex Digital House UC Store!*\n\n"
        "We provide instant PUBG Mobile UC top-ups.\n\n"
        "Please select your preferred currency:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    return SELECT_CURRENCY

# ============ CANCEL ============
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Order cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ============ MAIN ============
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [
                CallbackQueryHandler(select_currency, pattern="^currency_"),
                CallbackQueryHandler(back_start, pattern="^back_start$"),
            ],
            SELECT_PACKAGE: [
                CallbackQueryHandler(select_package, pattern="^pkg_"),
                CallbackQueryHandler(back_start, pattern="^back_start$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
                CallbackQueryHandler(back_start, pattern="^back_start$"),
            ],
            SEND_SCREENSHOT: [
                MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, receive_screenshot),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    print("🤖 Apex UC Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
