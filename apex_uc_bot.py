import os
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

USDT_WALLET = os.getenv("USDT_WALLET", "YOUR_USDT_WALLET")
HESABPAY_NUMBER = os.getenv("HESABPAY_NUMBER", "+93 789 077 537")
WHATSAPP = os.getenv("WHATSAPP", "+93 789 077 537")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID missing")

PACKAGES = {
    "60UC": {"uc": 60, "afn": 60, "usd": 0.95},
    "325UC": {"uc": 325, "afn": 300, "usd": 4.50},
    "660UC": {"uc": 660, "afn": 590, "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
}

wallets = {}
pending_wallet_deposits = {}

(
    SELECT_CURRENCY,
    SELECT_PACKAGE,
    ENTER_PLAYER_ID,
    SELECT_PAYMENT,
    SEND_SCREENSHOT,
    ENTER_WALLET_AMOUNT,
    SEND_WALLET_SCREENSHOT,
) = range(7)


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎮 Buy UC", callback_data="buy_uc")],
            [InlineKeyboardButton("💰 Wallet", callback_data="wallet")],
            [InlineKeyboardButton("📞 Support", callback_data="support")],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "🎮 Welcome to Apex Digital House!\n\n"
        "Choose an option below:",
        reply_markup=main_keyboard(),
    )

    return SELECT_CURRENCY


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🎮 Welcome to Apex Digital House!\n\n"
        "Choose an option below:",
        reply_markup=main_keyboard(),
    )

    return SELECT_CURRENCY


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]

    await query.edit_message_text(
        f"📞 Support\n\n"
        f"WhatsApp: {WHATSAPP}\n"
        f"Telegram: {TELEGRAM_SUPPORT}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_CURRENCY


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
        f"💰 Wallet Balance: {balance} AFN",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_CURRENCY


async def add_wallet_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Type amount you want to add.\n\nExample: 500"
    )

    return ENTER_WALLET_AMOUNT


async def enter_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("Enter valid amount.")
        return ENTER_WALLET_AMOUNT

    context.user_data["wallet_amount"] = amount

    await update.message.reply_text(
        f"Send {amount} AFN to HesabPay:\n\n"
        f"{HESABPAY_NUMBER}\n\n"
        f"Then send screenshot here."
    )

    return SEND_WALLET_SCREENSHOT


async def receive_wallet_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("wallet_amount")
    user = update.message.from_user

    deposit_id = f"WALLET-{user.id}-{update.message.message_id}"

    pending_wallet_deposits[deposit_id] = {
        "user_id": user.id,
        "amount": amount,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data=f"wallet_confirm_{deposit_id}",
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"wallet_reject_{deposit_id}",
                ),
            ]
        ]
    )

    caption = (
        f"💰 Wallet Deposit\n\n"
        f"User ID: {user.id}\n"
        f"Amount: {amount} AFN"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=caption,
            reply_markup=keyboard,
        )

    await update.message.reply_text(
        "✅ Deposit request received.\nWaiting for admin confirmation."
    )

    return ConversationHandler.END


async def wallet_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("wallet_confirm_"):
        deposit_id = data.replace("wallet_confirm_", "")

        deposit = pending_wallet_deposits.get(deposit_id)

        if not deposit:
            return

        user_id = deposit["user_id"]
        amount = deposit["amount"]

        wallets[user_id] = wallets.get(user_id, 0) + amount

        await context.bot.send_message(
            user_id,
            f"✅ Payment confirmed.\n\n"
            f"{amount} AFN added to your wallet.\n"
            f"New Balance: {wallets[user_id]} AFN",
        )

        await query.edit_message_caption(
            caption="✅ Wallet payment confirmed."
        )

        pending_wallet_deposits.pop(deposit_id, None)

    elif data.startswith("wallet_reject_"):
        deposit_id = data.replace("wallet_reject_", "")

        deposit = pending_wallet_deposits.get(deposit_id)

        if not deposit:
            return

        user_id = deposit["user_id"]

        await context.bot.send_message(
            user_id,
            "❌ Payment rejected."
        )

        await query.edit_message_caption(
            caption="❌ Wallet payment rejected."
        )

        pending_wallet_deposits.pop(deposit_id, None)


async def buy_uc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("USD", callback_data="currency_usd")],
        [InlineKeyboardButton("AFN", callback_data="currency_afn")],
    ]

    await query.edit_message_text(
        "Choose currency:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_PACKAGE


async def select_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency = query.data.split("_")[1]
    context.user_data["currency"] = currency

    keyboard = []

    for key, pkg in PACKAGES.items():
        if currency == "usd":
            text = f"{pkg['uc']} UC - ${pkg['usd']}"
        else:
            text = f"{pkg['uc']} UC - {pkg['afn']} AFN"

        keyboard.append(
            [InlineKeyboardButton(text, callback_data=f"pkg_{key}")]
        )

    await query.edit_message_text(
        "Choose package:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_PACKAGE


async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pkg_key = query.data.split("_")[1]

    context.user_data["package"] = pkg_key

    await query.edit_message_text(
        "Enter PUBG Player ID:"
    )

    return ENTER_PLAYER_ID


async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()

    context.user_data["player_id"] = player_id

    keyboard = [
        [InlineKeyboardButton("HesabPay", callback_data="pay_hesabpay")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt")],
    ]

    await update.message.reply_text(
        "Choose payment method:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SELECT_PAYMENT


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payment = query.data.split("_")[1]

    pkg_key = context.user_data["package"]
    pkg = PACKAGES[pkg_key]

    currency = context.user_data["currency"]

    if currency == "usd":
        price = f"${pkg['usd']}"
    else:
        price = f"{pkg['afn']} AFN"

    if payment == "hesabpay":
        payment_text = f"HesabPay:\n{HESABPAY_NUMBER}"
    else:
        payment_text = f"USDT Wallet:\n{USDT_WALLET}"

    await query.edit_message_text(
        f"Send payment:\n\n"
        f"{payment_text}\n\n"
        f"Amount: {price}\n\n"
        f"After payment send screenshot here."
    )

    return SEND_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pkg_key = context.user_data["package"]
    pkg = PACKAGES[pkg_key]

    player_id = context.user_data["player_id"]

    caption = (
        f"🎮 New UC Order\n\n"
        f"UC: {pkg['uc']}\n"
        f"Player ID: {player_id}"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=caption,
        )

    await update.message.reply_text(
        "✅ Order received.\nWe are checking payment now."
    )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text("Cancelled.")

    return ConversationHandler.END


if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CURRENCY: [
                CallbackQueryHandler(buy_uc, pattern="^buy_uc$"),
                CallbackQueryHandler(wallet, pattern="^wallet$"),
                CallbackQueryHandler(support, pattern="^support$"),
                CallbackQueryHandler(add_wallet_balance, pattern="^add_wallet_balance$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            SELECT_PACKAGE: [
                CallbackQueryHandler(select_currency, pattern="^currency_"),
                CallbackQueryHandler(select_package, pattern="^pkg_"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
            ],
            SEND_SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
            ],
            ENTER_WALLET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_wallet_amount),
            ],
            SEND_WALLET_SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_wallet_screenshot),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    app.add_handler(conv)

    app.add_handler(
        CallbackQueryHandler(
            wallet_admin_action,
            pattern="^wallet_(confirm|reject)_",
        )
    )

    print("Bot Running...")
    app.run_polling()
