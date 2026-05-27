import os, json, logging, hashlib, hmac, asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters,
)
import aiohttp as aiohttp_client

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ── Config ────────────────────────────────────────────────────────────────
BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
MINI_APP_URL     = os.getenv("MINI_APP_URL", "https://your-site.com")
HESABPAY_API_KEY = os.getenv("HESABPAY_API_KEY", "MjY1NzNmMTgtZDI4YS00YzhjLTk0OWUtZDMwYjQ5MWNlNDU4X18yNDZmYjExMTRjOWQ2MTUxMjgzOA==")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")
WEBHOOK_PORT     = int(os.getenv("PORT", "8080"))  # Render sets PORT automatically

# HesabPay API endpoints
HESABPAY_CREATE_SESSION = "https://api.hesab.com/api/v1/payment/create-session"
HESABPAY_VERIFY         = "https://api.hesab.com/api/v1/hesab/webhooks/verify-signature"

if not BOT_TOKEN: raise ValueError("BOT_TOKEN missing")
if ADMIN_ID == 0: raise ValueError("ADMIN_ID missing")

PACKAGES = {
    "60UC":   {"uc": 60,   "afn": 60,   "usd": 0.95},
    "325UC":  {"uc": 325,  "afn": 300,  "usd": 4.50},
    "660UC":  {"uc": 660,  "afn": 590,  "usd": 9.10},
    "1800UC": {"uc": 1800, "afn": 1470, "usd": 22.65},
    "3850UC": {"uc": 3850, "afn": 2960, "usd": 45.50},
    "8100UC": {"uc": 8100, "afn": 5910, "usd": 90.85},
}

# In-memory storage
wallets:          dict = {}
pending_orders:   dict = {}   # session_id → order info
code_store:       dict = {key: [] for key in PACKAGES}

# States
SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, ADMIN_ADD_CODES = range(4)

# Global reference to the bot application (set in main)
bot_app = None


# ═══════════════════════════════════════════════════════════════════════════
# HESABPAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════

async def create_hesabpay_session(pkg_key: str, player_id: str, user_id: int) -> str | None:
    """
    Creates a HesabPay payment session and returns the checkout URL.
    The customer is redirected to this URL to complete payment.
    """
    pkg = PACKAGES[pkg_key]
    # HesabPay works in USD; convert AFN price to USD
    amount = pkg["usd"]

    payload = {
        "products": [
            {
                "name":     f"PUBG {pkg['uc']} UC — Player {player_id}",
                "quantity": 1,
                "price":    amount,
            }
        ],
        # We store order info in metadata so the webhook can find it
        "metadata": {
            "user_id":   str(user_id),
            "pkg_key":   pkg_key,
            "player_id": player_id,
        },
        "currency": "USD",
    }

    headers = {
        "Authorization": HESABPAY_API_KEY,
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                HESABPAY_CREATE_SESSION,
                json=payload,
                headers=headers,
                timeout=aiohttp_client.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                logging.info(f"HesabPay create-session response: {data}")
                # HesabPay returns a payment URL — key may be 'url', 'payment_url', or 'session_url'
                url = data.get("url") or data.get("payment_url") or data.get("session_url")
                session_id = data.get("session_id") or data.get("id")
                if url and session_id:
                    # Save pending order so webhook can match it
                    pending_orders[session_id] = {
                        "user_id":   user_id,
                        "pkg_key":   pkg_key,
                        "player_id": player_id,
                    }
                return url
    except Exception as e:
        logging.error(f"HesabPay create-session error: {e}")
        return None


async def verify_hesabpay_webhook(payload: dict, signature: str) -> bool:
    """Verify webhook signature with HesabPay API."""
    headers = {
        "Authorization": HESABPAY_API_KEY,
        "Content-Type":  "application/json",
    }
    body = {"signature": signature, **payload}
    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                HESABPAY_VERIFY,
                json=body,
                headers=headers,
                timeout=aiohttp_client.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                logging.info(f"HesabPay verify response: {data}")
                return data.get("valid") is True or data.get("verified") is True
    except Exception as e:
        logging.error(f"HesabPay verify error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK SERVER  (receives payment confirmation from HesabPay)
# ═══════════════════════════════════════════════════════════════════════════

async def hesabpay_webhook_handler(request: web.Request) -> web.Response:
    """
    HesabPay POSTs to this endpoint after payment is completed.
    We verify the signature, then auto-deliver the UC code.
    """
    global bot_app

    try:
        payload   = await request.json()
        signature = request.headers.get("X-Signature") or payload.get("signature", "")
        logging.info(f"HesabPay webhook received: {payload}")

        # Verify with HesabPay
        valid = await verify_hesabpay_webhook(payload, signature)
        if not valid:
            logging.warning("HesabPay webhook signature invalid!")
            return web.Response(status=400, text="Invalid signature")

        # Check payment status
        status     = payload.get("status") or payload.get("payment_status", "")
        session_id = payload.get("session_id") or payload.get("id", "")

        if status.lower() not in ("paid", "success", "completed"):
            logging.info(f"Payment not completed, status: {status}")
            return web.Response(text="ok")

        # Find the pending order
        order = pending_orders.get(session_id)
        if not order:
            # Try metadata fallback
            meta      = payload.get("metadata", {})
            user_id   = int(meta.get("user_id", 0))
            pkg_key   = meta.get("pkg_key", "")
            player_id = meta.get("player_id", "")
        else:
            user_id   = order["user_id"]
            pkg_key   = order["pkg_key"]
            player_id = order["player_id"]

        if not user_id or not pkg_key:
            logging.error("Could not find order for this webhook")
            return web.Response(status=400, text="Order not found")

        pkg = PACKAGES.get(pkg_key)
        if not pkg:
            return web.Response(status=400, text="Invalid package")

        # Check stock
        if not code_store.get(pkg_key):
            # No code available — notify admin, notify user
            await bot_app.bot.send_message(
                user_id,
                "✅ *Payment received!*\n\n"
                "⚠️ Unfortunately we are temporarily out of stock for this package.\n"
                "Our team will deliver your code manually within 30 minutes.\n\n"
                f"Contact: {TELEGRAM_SUPPORT}",
                parse_mode="Markdown",
            )
            await bot_app.bot.send_message(
                ADMIN_ID,
                f"⚠️ *OUT OF STOCK — MANUAL DELIVERY NEEDED*\n\n"
                f"User: `{user_id}`\n"
                f"Package: *{pkg['uc']} UC*\n"
                f"Player ID: `{player_id}`\n"
                f"Payment: ✅ CONFIRMED by HesabPay",
                parse_mode="Markdown",
            )
            pending_orders.pop(session_id, None)
            return web.Response(text="ok")

        # Pop code and deliver!
        code      = code_store[pkg_key].pop(0)
        remaining = len(code_store[pkg_key])

        # Notify admin
        await bot_app.bot.send_message(
            ADMIN_ID,
            f"🎮 *AUTO-DELIVERED ORDER*\n\n"
            f"👤 User: `{user_id}`\n"
            f"Package: *{pkg['uc']} UC*\n"
            f"Player ID: `{player_id}`\n"
            f"💰 Payment: ✅ CONFIRMED by HesabPay\n"
            f"🔑 Code sent: `{code}`\n"
            f"🗄️ Remaining stock: {remaining}",
            parse_mode="Markdown",
        )

        # Deliver code to customer
        await bot_app.bot.send_message(
            user_id,
            f"✅ *Payment Confirmed! Here is your UC Code:*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"🔑 *Your Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫\n"
            "New order? /start",
            parse_mode="Markdown",
        )

        pending_orders.pop(session_id, None)
        return web.Response(text="ok")

    except Exception as e:
        logging.error(f"Webhook handler error: {e}")
        return web.Response(status=500, text="Server error")


# ═══════════════════════════════════════════════════════════════════════════
# BOT HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    is_admin = update.message.from_user.id == ADMIN_ID

    kb = [
        [InlineKeyboardButton("⚡ Quick Buy — 60 UC (60 AFN)", callback_data="pkg_60UC")],
        [InlineKeyboardButton("🎮 All Packages",               callback_data="show_packages")],
        [InlineKeyboardButton("🚀 Open Mini App",              web_app=WebAppInfo(url=MINI_APP_URL))],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🗄️ Manage Codes", callback_data="admin_codes")])

    await update.message.reply_text(
        "🏪 *Welcome to Apex Digital House!*\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "✅ Fast delivery\n"
        "✅ Best prices\n"
        "✅ 24/7 support\n\n"
        "Choose an option below:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def show_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = []
    for key, pkg in PACKAGES.items():
        count = len(code_store.get(key, []))
        icon  = "✅" if count > 0 else "❌"
        kb.append([InlineKeyboardButton(
            f"{icon} {pkg['uc']} UC — {pkg['afn']} AFN / ${pkg['usd']}",
            callback_data=f"pkg_{key}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_start")])
    await query.edit_message_text(
        "🎮 *Select a UC Package:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    is_admin = query.from_user.id == ADMIN_ID
    kb = [
        [InlineKeyboardButton("⚡ Quick Buy — 60 UC (60 AFN)", callback_data="pkg_60UC")],
        [InlineKeyboardButton("🎮 All Packages",               callback_data="show_packages")],
        [InlineKeyboardButton("🚀 Open Mini App",              web_app=WebAppInfo(url=MINI_APP_URL))],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🗄️ Manage Codes", callback_data="admin_codes")])
    await query.edit_message_text(
        "🏪 *Welcome to Apex Digital House!*\n\nChoose an option below:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    pkg_key = query.data.replace("pkg_", "")
    pkg     = PACKAGES.get(pkg_key)
    if not pkg:
        return SELECT_PACKAGE
    if not code_store.get(pkg_key):
        await query.answer("❌ This package is out of stock!", show_alert=True)
        return SELECT_PACKAGE
    context.user_data["package"] = pkg_key
    await query.edit_message_text(
        f"✅ *{pkg['uc']} UC selected*\n\n"
        f"💰 Price: *{pkg['afn']} AFN* / *${pkg['usd']}*\n\n"
        "📝 Please enter your *PUBG Mobile Player ID*:\n\n"
        "How to find it:\n"
        "1️⃣ Open PUBG Mobile\n"
        "2️⃣ Tap your profile picture\n"
        "3️⃣ Your ID is below your name\n\n"
        "⌨️ Type your Player ID now:",
        parse_mode="Markdown",
    )
    return ENTER_PLAYER_ID


async def enter_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player_id = update.message.text.strip()
    if not player_id.isdigit() or len(player_id) < 5:
        await update.message.reply_text("❌ Please enter a valid numeric Player ID (min 5 digits).")
        return ENTER_PLAYER_ID

    context.user_data["player_id"] = player_id
    pkg_key = context.user_data["package"]
    pkg     = PACKAGES[pkg_key]
    balance = wallets.get(update.message.from_user.id, 0)

    kb = [
        [InlineKeyboardButton("💳 Pay via HesabPay (Auto)", callback_data="pay_hesabpay")],
        [InlineKeyboardButton("💰 Pay From Wallet",          callback_data="pay_wallet")],
        [InlineKeyboardButton("🔙 Change Package",           callback_data="show_packages")],
    ]
    await update.message.reply_text(
        f"✅ Player ID: *{player_id}*\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{pkg['afn']} AFN* / *${pkg['usd']}*\n\n"
        f"💳 Your wallet balance: *{balance} AFN*\n\n"
        "⚠️ *Double-check your Player ID!*\n\n"
        "Select payment method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PAYMENT


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query     = update.callback_query
    await query.answer()
    payment   = query.data.replace("pay_", "")
    pkg_key   = context.user_data["package"]
    pkg       = PACKAGES[pkg_key]
    player_id = context.user_data["player_id"]
    user_id   = query.from_user.id

    # ── Wallet payment ────────────────────────────────────────────────────
    if payment == "wallet":
        balance = wallets.get(user_id, 0)
        if balance < pkg["afn"]:
            await query.edit_message_text(
                f"❌ *Not enough wallet balance.*\n\n"
                f"Your balance: *{balance} AFN*\n"
                f"Required: *{pkg['afn']} AFN*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="back_start")
                ]]),
            )
            return SELECT_PACKAGE
        if not code_store.get(pkg_key):
            await query.edit_message_text("❌ Out of stock. Contact support.")
            return ConversationHandler.END

        wallets[user_id] = balance - pkg["afn"]
        code = code_store[pkg_key].pop(0)

        await context.bot.send_message(
            ADMIN_ID,
            f"🎮 *WALLET ORDER AUTO-DELIVERED*\n\n"
            f"👤 `{user_id}`\n"
            f"Package: *{pkg['uc']} UC*\n"
            f"Player ID: `{player_id}`\n"
            f"Paid: *{pkg['afn']} AFN* (wallet)\n"
            f"Code sent: `{code}`",
            parse_mode="Markdown",
        )
        await query.edit_message_text(
            f"✅ *Payment Confirmed & Code Delivered!*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"🔑 *Your UC Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫",
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ── HesabPay — create session and send link ───────────────────────────
    await query.edit_message_text(
        "⏳ Creating your payment link…",
    )

    pay_url = await create_hesabpay_session(pkg_key, player_id, user_id)

    if not pay_url:
        await query.edit_message_text(
            "❌ Could not create payment link right now.\n\n"
            f"Please contact support: {TELEGRAM_SUPPORT}",
        )
        return ConversationHandler.END

    await query.edit_message_text(
        f"💳 *Your HesabPay Payment Link is Ready!*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Amount: *${pkg['usd']}*\n"
        f"🎯 Player ID: `{player_id}`\n\n"
        "👇 Tap the button below to pay.\n"
        "Once your payment is confirmed, your UC code will be sent here *automatically*. ✅",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Pay Now via HesabPay", url=pay_url)
        ]]),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── Admin: code management ────────────────────────────────────────────────
async def admin_codes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    lines = ["🗄️ *UC Code Inventory*\n"]
    kb    = []
    for key, pkg in PACKAGES.items():
        count  = len(code_store.get(key, []))
        status = "✅" if count > 0 else "❌ EMPTY"
        lines.append(f"{status} *{pkg['uc']} UC* — {count} code(s)")
        kb.append([InlineKeyboardButton(
            f"➕ Add for {pkg['uc']} UC", callback_data=f"admin_addcodes_{key}"
        )])
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def admin_start_add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    pkg_key = query.data.replace("admin_addcodes_", "")
    context.user_data["adding_codes_for"] = pkg_key
    pkg = PACKAGES[pkg_key]
    await query.edit_message_text(
        f"➕ *Adding codes for {pkg['uc']} UC*\n\n"
        "Send one code per line:\n\n"
        "`CODE-ABCD-1234\nCODE-EFGH-5678`\n\n"
        "Type /cancel to stop.",
        parse_mode="Markdown",
    )
    return ADMIN_ADD_CODES


async def admin_receive_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return ConversationHandler.END
    pkg_key = context.user_data.get("adding_codes_for")
    if not pkg_key:
        await update.message.reply_text("❌ Session lost. Use /start.")
        return ConversationHandler.END
    codes = [c.strip() for c in update.message.text.strip().splitlines() if c.strip()]
    if not codes:
        await update.message.reply_text("No codes found. Send one per line.")
        return ADMIN_ADD_CODES
    code_store.setdefault(pkg_key, []).extend(codes)
    pkg = PACKAGES[pkg_key]
    await update.message.reply_text(
        f"✅ *{len(codes)} code(s) added* for *{pkg['uc']} UC*!\n"
        f"Total in stock: *{len(code_store[pkg_key])}*",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def admin_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lines = ["🗄️ *UC Code Inventory*\n"]
    for key, pkg in PACKAGES.items():
        count  = len(code_store.get(key, []))
        status = "✅" if count > 0 else "❌ EMPTY"
        lines.append(f"{status} *{pkg['uc']} UC* — {count} code(s)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled. Use /start to begin again.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — run bot + webhook server together
# ═══════════════════════════════════════════════════════════════════════════

async def run_webhook_server():
    app = web.Application()
    app.router.add_post("/hesabpay-webhook", hesabpay_webhook_handler)
    app.router.add_get("/",                  lambda r: web.Response(text="Apex UC Bot running"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    logging.info(f"Webhook server running on port {WEBHOOK_PORT}")


if __name__ == "__main__":
    import asyncio
    from telegram.ext import Application

    application = Application.builder().token(BOT_TOKEN).build()
    bot_app     = application

    buy_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",          start),
            CallbackQueryHandler(show_packages,  pattern="^show_packages$"),
            CallbackQueryHandler(select_package, pattern="^pkg_"),
        ],
        states={
            SELECT_PACKAGE: [
                CallbackQueryHandler(show_packages,  pattern="^show_packages$"),
                CallbackQueryHandler(select_package, pattern="^pkg_"),
                CallbackQueryHandler(back_start,     pattern="^back_start$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
                CallbackQueryHandler(show_packages,  pattern="^show_packages$"),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
                CallbackQueryHandler(show_packages,  pattern="^show_packages$"),
                CallbackQueryHandler(back_start,     pattern="^back_start$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )

    code_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_start_add_codes, pattern="^admin_addcodes_")],
        states={ADMIN_ADD_CODES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_codes)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(buy_conv)
    application.add_handler(code_conv)
    application.add_handler(CommandHandler("stock",        admin_stock_command))
    application.add_handler(CallbackQueryHandler(admin_codes_menu, pattern="^admin_codes$"))

    async def main():
        await run_webhook_server()
        async with application:
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            logging.info("🤖 Apex UC Bot running with HesabPay auto-payment…")
            # Run forever
            await asyncio.Event().wait()

    asyncio.run(main())
