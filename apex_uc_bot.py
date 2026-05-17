import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = "8602835129:AAFGXQsEUBpWChMbZ9K5iy7wMEOLfM3wwaw"
ADMIN_ID = 8556241073
USDT_WALLET = "TUUrCxQexypGX8wmXMeNf6mRq2PFFK9Jvz"
HESABPAY_NUMBER = "+93 789 077 537"

PACKAGES = {
    "60UC":   {"uc": 60,   "afn": 60,   "usd": 0.95},
    "325UC":  {"uc": 325,  "afn": 300,  "usd": 4.50},
    "660UC":  {"uc": 660,  "afn": 590,  "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

SELECT_CURRENCY, SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, SEND_SCREENSHOT = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💵 Pay in USD (USDT)", callback_data="currency_usd")],
        [InlineKeyboardButton("🇦🇫 Pay in Afghani (AFN)", callback_data="currency_afn")],
    ]
    await update.message.reply_text(
        "🎮 *Welcome to Apex Digital House UC Store!*\n\nInstant PUBG Mobile UC top-ups.\n\nPlease select your preferred currency:",
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
        label = f"🎮 {pkg['uc']} UC — ${pkg['usd']}" if currency == "usd" else f"🎮 {pkg['uc']} UC — {pkg['afn']} AFN"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"pkg_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_start")])
    await query.edit_message_text("🎮 *Select your UC Package:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
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
    await query.edit_message_text(f"✅ You selected: *{pkg['uc']} UC* — *{price}*\n\n📝 Please enter your *PUBG Mobile Player ID*:\n\n_(Find it in PUBG Mobile → Profile)_", parse_mode="Markdown")
    return ENTER_PLAYER_ID

async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text
    context.user_data["player_id"] = player_id
    currency = context.user_data["currency"]
    if currency == "usd":
        keyboard = [[InlineKeyboardButton("💎 USDT (TRC20)", callback_data="pay_usdt")],[InlineKeyboardButton("🔙 Back", callback_data="back_start")]]
    else:
        keyboard = [[InlineKeyboardButton("📲 HesabPay", callback_data="pay_hesabpay")],[InlineKeyboardButton("⚡ AtomPay", callback_data="pay_atompay")],[InlineKeyboardButton("🏦 Azizi Bank", callback_data="pay_azizi")],[InlineKeyboardButton("🔙 Back", callback_data="back_start")]]
    await update.message.reply_text(f"✅ Player ID saved: *{player_id}*\n\n💳 *Select payment method:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_PAYMENT

async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment = query.data.split("_", 1)[1]
    context.user_data["payment"] = payment
    pkg = context.user_data["pkg_details"]
    currency = context.user_data["currency"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    if payment == "usdt":
        info = f"💎 *Send USDT (TRC20) to:*\n\n`{USDT_WALLET}`\n\n💰 Amount: *{price}*"
    elif payment == "hesabpay":
        info = f"📲 *Send via HesabPay to:*\n\n`{HESABPAY_NUMBER}`\n\n💰 Amount: *{price}*"
    elif payment == "atompay":
        info = f"⚡ *Send via AtomPay to:*\n\n`{HESABPAY_NUMBER}`\n\n💰 Amount: *{price}*"
    else:
        info = f"🏦 *Send via Azizi Bank:*\n\nContact: {HESABPAY_NUMBER}\n\n💰 Amount: *{price}*"
    await query.edit_message_text(f"{info}\n\n📸 After payment, send your *payment screenshot* to confirm your order.", parse_mode="Markdown")
    return SEND_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pkg = context.user_data["pkg_details"]
    currency = context.user_data["currency"]
    player_id = context.user_data["player_id"]
    payment = context.user_data["payment"]
    price = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"
    user = update.message.from_user
    admin_msg = f"🔔 *NEW UC ORDER!*\n\n👤 {user.first_name} {user.last_name or ''}\n🆔 @{user.username or 'N/A'} ({user.id})\n🎮 Package: {pkg['uc']} UC\n💰 Price: {price}\n🎯 Player ID: {player_id}\n💳 Payment: {payment.upper()}"
    try:
        if update.message.photo:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=admin_msg, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg + "\n\n⚠️ No screenshot received!", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Admin notify failed: {e}")
    await update.message.reply_text("✅ *Order Received!*\n\n" + f"🎮 Package: *{pkg['uc']} UC*\n🎯 Player ID: *{player_id}*\n💰 Amount: *{price}*\n\n⏳ Your UC will be sent within *30 minutes*.\nThank you for choosing *Apex Digital House!* 🚀\n\nType /start to make another order.", parse_mode="Markdown")
    return ConversationHandler.END

async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("💵 Pay in USD (USDT)", callback_data="currency_usd")],[InlineKeyboardButton("🇦🇫 Pay in Afghani (AFN)", callback_data="currency_afn")]]
    await query.edit_message_text("🎮 *Welcome to Apex Digital House UC Store!*\n\nPlease select your preferred currency:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_CURRENCY

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return ConversationHandler.END

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [CallbackQueryHandler(select_currency, pattern="^currency_"), CallbackQueryHandler(back_start, pattern="^back_start$")],
            SELECT_PACKAGE: [CallbackQueryHandler(select_package, pattern="^pkg_"), CallbackQueryHandler(back_start, pattern="^back_start$")],
            ENTER_PLAYER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id)],
            SELECT_PAYMENT: [CallbackQueryHandler(select_payment, pattern="^pay_"), CallbackQueryHandler(back_start, pattern="^back_start$")],
            SEND_SCREENSHOT: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    print("🤖 Apex UC Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
