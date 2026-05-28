import os, json, logging, asyncio
from aiohttp import web
import aiohttp as aiohttp_client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters,
)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ── Config ────────────────────────────────────────────────────────────────
BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
MINI_APP_URL     = os.getenv("MINI_APP_URL", "https://apexdigitalhouse.com/app")
HESABPAY_API_KEY = os.getenv("HESABPAY_API_KEY", "MjY1NzNmMTgtZDI4YS00YzhjLTk0OWUtZDMwYjQ5MWNlNDU4X18yNDZmYjExMTRjOWQ2MTUxMjgzOA==")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")
PORT             = int(os.getenv("PORT", "8080"))

HESABPAY_CREATE  = "https://api.hesab.com/api/v1/payment/create-session"
HESABPAY_VERIFY  = "https://api.hesab.com/api/v1/hesab/webhooks/verify-signature"

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

wallets:        dict = {}
pending_orders: dict = {}
code_store:     dict = {key: [] for key in PACKAGES}

SELECT_PACKAGE, ENTER_PLAYER_ID, SELECT_PAYMENT, SEND_SCREENSHOT, ADMIN_ADD_CODES, ENTER_DEPOSIT_AMOUNT, WAIT_DEPOSIT_SCREENSHOT = range(7)

bot_app = None  # set in main


# ── HesabPay ──────────────────────────────────────────────────────────────
async def create_hesabpay_session(pkg_key, player_id, user_id):
    pkg = PACKAGES[pkg_key]
    headers = {
        "Authorization": HESABPAY_API_KEY,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    # Try multiple payload formats since HesabPay docs are not fully public
    payload = {
        "amount":      pkg["usd"],
        "currency":    "USD",
        "description": f"PUBG {pkg['uc']} UC - Player ID: {player_id}",
        "reference":   f"{user_id}-{pkg_key}",
        "products": [{
            "name":     f"PUBG {pkg['uc']} UC",
            "quantity": 1,
            "price":    pkg["usd"],
        }],
        "metadata": {
            "user_id":   str(user_id),
            "pkg_key":   pkg_key,
            "player_id": str(player_id),
        },
    }
    try:
        async with aiohttp_client.ClientSession() as s:
            async with s.post(
                HESABPAY_CREATE,
                json=payload,
                headers=headers,
                timeout=aiohttp_client.ClientTimeout(total=15),
            ) as r:
                text = await r.text()
                logging.info(f"HesabPay status={r.status} response={text}")
                try:
                    data = json.loads(text)
                except Exception:
                    logging.error(f"HesabPay non-JSON response: {text}")
                    return None
                # Try all possible URL field names
                url = (data.get("url") or data.get("payment_url") or
                       data.get("session_url") or data.get("checkout_url") or
                       data.get("redirect_url") or data.get("link"))
                session_id = (data.get("session_id") or data.get("id") or
                              data.get("transaction_id") or data.get("reference"))
                if url:
                    sid = session_id or f"{user_id}-{pkg_key}"
                    pending_orders[sid] = {
                        "user_id": user_id, "pkg_key": pkg_key, "player_id": player_id
                    }
                    return url
                logging.error(f"HesabPay no URL in response: {data}")
                return None
    except Exception as e:
        logging.error(f"HesabPay create-session error: {e}")
        return None


async def verify_hesabpay_webhook(payload, signature):
    headers = {"Authorization": HESABPAY_API_KEY, "Content-Type": "application/json"}
    try:
        async with aiohttp_client.ClientSession() as s:
            async with s.post(HESABPAY_VERIFY, json={"signature": signature, **payload}, headers=headers, timeout=aiohttp_client.ClientTimeout(total=10)) as r:
                data = await r.json()
                return data.get("valid") is True or data.get("verified") is True
    except Exception as e:
        logging.error(f"HesabPay verify error: {e}")
        return False


# ── Webhook server ────────────────────────────────────────────────────────
async def hesabpay_webhook(request):
    global bot_app
    try:
        payload   = await request.json()
        signature = request.headers.get("X-Signature") or payload.get("signature", "")
        logging.info(f"Webhook received: {payload}")

        valid = await verify_hesabpay_webhook(payload, signature)
        if not valid:
            return web.Response(status=400, text="Invalid signature")

        status     = (payload.get("status") or payload.get("payment_status", "")).lower()
        session_id = payload.get("session_id") or payload.get("id", "")

        if status not in ("paid", "success", "completed"):
            return web.Response(text="ok")

        order = pending_orders.get(session_id)
        if order:
            user_id, pkg_key, player_id = order["user_id"], order["pkg_key"], order["player_id"]
        else:
            meta      = payload.get("metadata", {})
            user_id   = int(meta.get("user_id", 0))
            pkg_key   = meta.get("pkg_key", "")
            player_id = meta.get("player_id", "")

        if not user_id or not pkg_key:
            return web.Response(status=400, text="Order not found")

        pkg = PACKAGES.get(pkg_key)
        if not pkg:
            return web.Response(status=400, text="Invalid package")

        if not code_store.get(pkg_key):
            await bot_app.bot.send_message(user_id,
                "✅ *Payment received!*\n\n⚠️ Temporarily out of stock.\nWe will deliver your code manually within 30 minutes.\n\nContact: " + TELEGRAM_SUPPORT,
                parse_mode="Markdown")
            await bot_app.bot.send_message(ADMIN_ID,
                f"⚠️ *OUT OF STOCK — MANUAL DELIVERY*\n\nUser: `{user_id}`\nPackage: *{pkg['uc']} UC*\nPlayer ID: `{player_id}`\nPayment: ✅ CONFIRMED",
                parse_mode="Markdown")
            pending_orders.pop(session_id, None)
            return web.Response(text="ok")

        code      = code_store[pkg_key].pop(0)
        remaining = len(code_store[pkg_key])

        await bot_app.bot.send_message(ADMIN_ID,
            f"🎮 *AUTO-DELIVERED*\n\nUser: `{user_id}`\nPackage: *{pkg['uc']} UC*\nPlayer ID: `{player_id}`\nCode: `{code}`\nRemaining stock: {remaining}",
            parse_mode="Markdown")
        await bot_app.bot.send_message(user_id,
            f"✅ *Payment Confirmed! Here is your UC Code:*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"🔑 *Your Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫\nNew order? /start",
            parse_mode="Markdown")

        pending_orders.pop(session_id, None)
        return web.Response(text="ok")

    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return web.Response(status=500, text="error")


async def stock_api(request):
    data = {key: len(codes) for key, codes in code_store.items()}
    return web.Response(
        text=json.dumps(data),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def run_server():
    app = web.Application()
    app.router.add_post("/hesabpay-webhook", hesabpay_webhook)
    app.router.add_get("/stock",             stock_api)
    app.router.add_get("/",                  lambda r: web.Response(text="Apex UC Bot running ✅"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Server running on port {PORT}")


# ── Bot handlers ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    is_admin = update.message.from_user.id == ADMIN_ID

    # Set the menu button to open Mini App
    try:
        await context.bot.set_chat_menu_button(
            chat_id=update.message.chat_id,
            menu_button={"type": "web_app", "text": "🚀 Store", "web_app": {"url": MINI_APP_URL}},
        )
    except Exception as e:
        logging.warning(f"Could not set menu button: {e}")

    kb = [
        [
            InlineKeyboardButton("🛍️ Browse Products", callback_data="show_packages"),
            InlineKeyboardButton("💰 My Wallet",        callback_data="my_wallet"),
        ],
        [
            InlineKeyboardButton("📋 My Orders",        callback_data="my_orders"),
            InlineKeyboardButton("💬 Support",          callback_data="support"),
        ],
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
            f"{icon} {pkg['uc']} UC — {pkg['afn']} AFN",
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
        [
            InlineKeyboardButton("🛍️ Browse Products", callback_data="show_packages"),
            InlineKeyboardButton("💰 My Wallet",        callback_data="my_wallet"),
        ],
        [
            InlineKeyboardButton("📋 My Orders",        callback_data="my_orders"),
            InlineKeyboardButton("💬 Support",          callback_data="support"),
        ],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🗄️ Manage Codes", callback_data="admin_codes")])
    await query.edit_message_text(
        "🏪 *Welcome to Apex Digital House!*\n\nChoose an option below:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def my_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = wallets.get(user_id, 0)
    kb = [
        [InlineKeyboardButton("➕ Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_start")],
    ]
    await query.edit_message_text(
        f"💰 *My Wallet*\n\n"
        f"🆔 Telegram ID: `{user_id}`\n\n"
        f"💵 *Current Balance:*\n"
        f"*{balance} AFN*\n\n"
        "Tap *Add Balance* to top up your wallet.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def add_balance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("📲 HesabPay",   callback_data="deposit_hesabpay")],
        [InlineKeyboardButton("💎 USDT TRC20", callback_data="deposit_usdt")],
        [InlineKeyboardButton("🔙 Back",       callback_data="my_wallet")],
    ]
    await query.edit_message_text(
        "➕ *Add Wallet Balance*\n\n"
        "Choose your payment method:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def deposit_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("deposit_", "")
    context.user_data["deposit_method"] = method

    if method == "hesabpay":
        info = f"📲 *Send via HesabPay to:*\n\n`{HESABPAY_NUMBER}`"
    else:
        info = f"💎 *Send USDT (TRC20) to:*\n\n`{USDT_WALLET}`\n\n⚠️ TRC20 network only!"

    kb = [[InlineKeyboardButton("🔙 Back", callback_data="add_balance")]]
    await query.edit_message_text(
        f"➕ *Add Wallet Balance*\n\n"
        f"{info}\n\n"
        "📸 After sending, reply with:\n"
        "1️⃣ The *amount* you sent (e.g. `500`)\n"
        "2️⃣ Your *payment screenshot*\n\n"
        "Type the amount now:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ENTER_DEPOSIT_AMOUNT


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_start")]]
    await query.edit_message_text(
        "📋 *My Orders*\n\n"
        "Your recent orders will appear here.\n\n"
        "To place a new order tap *Browse Products*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SELECT_PACKAGE


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_start")]]
    await query.edit_message_text(
        "💬 *Support & Help*\n\n"
        f"✈️ Telegram: {TELEGRAM_SUPPORT}\n"
        f"📲 WhatsApp: +93 789 077 537\n\n"
        "⏳ We respond within 30 minutes!",
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
        f"💰 Price: *{pkg['afn']} AFN*\n\n"
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
    pkg     = PACKAGES[context.user_data["package"]]
    balance = wallets.get(update.message.from_user.id, 0)
    kb = [
        [InlineKeyboardButton("💳 Pay via HesabPay (Auto)", callback_data="pay_hesabpay")],
        [InlineKeyboardButton("💰 Pay From Wallet",          callback_data="pay_wallet")],
        [InlineKeyboardButton("🔙 Change Package",           callback_data="show_packages")],
    ]
    await update.message.reply_text(
        f"✅ Player ID: *{player_id}*\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Price: *{pkg['afn']} AFN*\n\n"
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

    if payment == "wallet":
        balance = wallets.get(user_id, 0)
        if balance < pkg["afn"]:
            await query.edit_message_text(
                f"❌ *Not enough balance.*\n\nYour balance: *{balance} AFN*\nRequired: *{pkg['afn']} AFN*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_start")]]),
            )
            return SELECT_PACKAGE
        if not code_store.get(pkg_key):
            await query.edit_message_text("❌ Out of stock. Contact support.")
            return ConversationHandler.END
        wallets[user_id] = balance - pkg["afn"]
        code = code_store[pkg_key].pop(0)
        await context.bot.send_message(ADMIN_ID,
            f"🎮 *WALLET ORDER AUTO-DELIVERED*\n\nUser: `{user_id}`\nPackage: *{pkg['uc']} UC*\nPlayer ID: `{player_id}`\nCode: `{code}`",
            parse_mode="Markdown")
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

    # HesabPay
    await query.edit_message_text("⏳ Creating your payment link…")
    pay_url = await create_hesabpay_session(pkg_key, player_id, user_id)
    if not pay_url:
        # Fallback to manual payment
        await query.edit_message_text(
            f"💳 *Pay via HesabPay*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"💰 Amount: *{pkg['afn']} AFN*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"📲 Send payment to:\n`+93 789 077 537`\n\n"
            "📸 After paying, send your screenshot here and admin will confirm.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_start")
            ]]),
        )
        context.user_data.clear()
        return ConversationHandler.END
    await query.edit_message_text(
        f"💳 *Your HesabPay Payment Link is Ready!*\n\n"
        f"🎮 Package: *{pkg['uc']} UC*\n"
        f"💰 Amount: *${pkg['usd']}*\n"
        f"🎯 Player ID: `{player_id}`\n\n"
        "Tap the button below to pay.\n"
        "Your UC code will be sent here *automatically* once payment is confirmed. ✅",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now via HesabPay", url=pay_url)]]),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── Admin code management ─────────────────────────────────────────────────
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
        kb.append([InlineKeyboardButton(f"➕ Add for {pkg['uc']} UC", callback_data=f"admin_addcodes_{key}")])
    await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def admin_start_add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    pkg_key = query.data.replace("admin_addcodes_", "")
    context.user_data["adding_codes_for"] = pkg_key
    pkg = PACKAGES[pkg_key]
    await query.edit_message_text(
        f"➕ *Adding codes for {pkg['uc']} UC*\n\nSend one code per line.\nType /cancel to stop.",
        parse_mode="Markdown")
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
        f"✅ *{len(codes)} code(s) added* for *{pkg['uc']} UC*!\nTotal: *{len(code_store[pkg_key])}*",
        parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lines = ["🗄️ *UC Code Inventory*\n"]
    for key, pkg in PACKAGES.items():
        count  = len(code_store.get(key, []))
        status = "✅" if count > 0 else "❌ EMPTY"
        lines.append(f"{status} *{pkg['uc']} UC* — {count} code(s)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def enter_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number e.g. `500`", parse_mode="Markdown")
        return ENTER_DEPOSIT_AMOUNT

    if amount < 50:
        await update.message.reply_text("❌ Minimum deposit is 50 AFN.")
        return ENTER_DEPOSIT_AMOUNT

    context.user_data["deposit_amount"] = amount
    method = context.user_data.get("deposit_method", "hesabpay")

    await update.message.reply_text(
        f"✅ Amount: *{amount} AFN*\n\n"
        f"📸 Now send your payment screenshot:",
        parse_mode="Markdown",
    )
    return WAIT_DEPOSIT_SCREENSHOT


async def receive_deposit_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount  = context.user_data.get("deposit_amount")
    method  = context.user_data.get("deposit_method", "hesabpay")
    user    = update.message.from_user

    if not amount:
        await update.message.reply_text("❌ Session expired. Use /start again.")
        return ConversationHandler.END

    deposit_id = f"WALLET-{user.id}-{update.message.message_id}"
    pending_wallet_deposits[deposit_id] = {
        "user_id":    user.id,
        "amount":     amount,
        "username":   user.username or "N/A",
        "first_name": user.first_name or "",
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"wallet_confirm_{deposit_id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"wallet_reject_{deposit_id}"),
    ]])

    caption = (
        f"💰 *WALLET DEPOSIT REQUEST*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 `{user.id}`\n"
        f"Amount: *{amount} AFN*\n"
        f"Method: *{method.upper()}*\n"
        f"ID: `{deposit_id}`"
    )

    if update.message.photo:
        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    else:
        await context.bot.send_message(
            ADMIN_ID,
            caption + "\n\n⚠️ No screenshot sent!",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    await update.message.reply_text(
        f"✅ *Deposit request sent!*\n\n"
        f"Amount: *{amount} AFN*\n\n"
        "Admin will confirm your payment shortly.\n"
        "Once confirmed your wallet will be updated automatically! ⏳",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END



    context.user_data.clear()
    await update.message.reply_text("Cancelled. Use /start to begin again.")
    return ConversationHandler.END


# ── Main ──────────────────────────────────────────────────────────────────
async def main():
    global bot_app

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
                CallbackQueryHandler(show_packages,       pattern="^show_packages$"),
                CallbackQueryHandler(select_package,      pattern="^pkg_"),
                CallbackQueryHandler(back_start,          pattern="^back_start$"),
                CallbackQueryHandler(my_wallet,           pattern="^my_wallet$"),
                CallbackQueryHandler(add_balance_menu,    pattern="^add_balance$"),
                CallbackQueryHandler(deposit_instructions,pattern="^deposit_"),
                CallbackQueryHandler(my_orders,           pattern="^my_orders$"),
                CallbackQueryHandler(support,             pattern="^support$"),
            ],
            ENTER_PLAYER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_player_id),
                CallbackQueryHandler(show_packages, pattern="^show_packages$"),
            ],
            SELECT_PAYMENT: [
                CallbackQueryHandler(select_payment, pattern="^pay_"),
                CallbackQueryHandler(show_packages,  pattern="^show_packages$"),
                CallbackQueryHandler(back_start,     pattern="^back_start$"),
            ],
            SEND_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_screenshot),
            ],
            ENTER_DEPOSIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_deposit_amount),
            ],
            WAIT_DEPOSIT_SCREENSHOT: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_deposit_screenshot),
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
    application.add_handler(CommandHandler("stock", stock_command))
    application.add_handler(CallbackQueryHandler(admin_codes_menu, pattern="^admin_codes$"))

    # Start webhook server and bot together
    await run_server()
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logging.info("🤖 Apex UC Bot running with HesabPay auto-payment…")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
