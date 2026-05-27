import os, json, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters,
)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
MINI_APP_URL     = os.getenv("MINI_APP_URL", "https://your-site.com")   # ← your hosted URL
USDT_WALLET      = os.getenv("USDT_WALLET",      "YOUR_USDT_WALLET")
HESABPAY_NUMBER  = os.getenv("HESABPAY_NUMBER",  "+93 789 077 537")
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@Wajid_gaming_store")

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

# In-memory storage (replace with a database for production)
wallets:                  dict = {}
pending_wallet_deposits:  dict = {}
pending_orders:           dict = {}
code_store:               dict = {key: [] for key in PACKAGES}

ADMIN_ADD_CODES = 0


# ── /start ───────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    is_admin = user.id == ADMIN_ID

    # Main button opens the Mini App
    kb = [[InlineKeyboardButton(
        "🎮 Open Apex Store",
        web_app=WebAppInfo(url=MINI_APP_URL)
    )]]

    if is_admin:
        kb.append([InlineKeyboardButton("🗄️ Manage Codes", callback_data="admin_codes")])

    await update.message.reply_text(
        f"👋 Welcome to *Apex Digital House*, {user.first_name}!\n\n"
        "Afghanistan's #1 PUBG UC Store 🇦🇫\n\n"
        "Tap the button below to open the store:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ── Mini App data handler ────────────────────────────────────────────────
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives JSON sent by tg.sendData() in the Mini App."""
    raw  = update.message.web_app_data.data
    user = update.message.from_user

    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("❌ Invalid data from app.")
        return

    dtype = data.get("type")

    # ── Deposit request ──────────────────────────────────────────────────
    if dtype == "deposit":
        amount = data.get("amount", 0)
        method = data.get("method", "hesabpay")
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

        pay_info = USDT_WALLET if method == "usdt" else HESABPAY_NUMBER

        await context.bot.send_message(
            ADMIN_ID,
            f"💰 *WALLET DEPOSIT REQUEST*\n\n"
            f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 `{user.id}`\n"
            f"Amount: *{amount} AFN*\n"
            f"Method: *{method.upper()}*\n"
            f"Deposit ID: `{deposit_id}`",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        await update.message.reply_text(
            f"✅ *Deposit request received!*\n\n"
            f"Amount: *{amount} AFN*\n"
            f"Send to: `{pay_info}`\n\n"
            "Once admin confirms your payment, your wallet will be updated.",
            parse_mode="Markdown",
        )

    # ── Order request ────────────────────────────────────────────────────
    elif dtype == "order":
        pkg_key = data.get("pkg")
        pid     = data.get("pid")
        payment = data.get("payment")
        pkg     = PACKAGES.get(pkg_key)

        if not pkg:
            await update.message.reply_text("❌ Invalid package. Please try again.")
            return

        currency = "usd" if payment == "usdt" else "afn"
        price    = f"${pkg['usd']}" if currency == "usd" else f"{pkg['afn']} AFN"

        # Wallet order — instant if admin confirmed deposit before
        if payment == "wallet":
            balance = wallets.get(user.id, 0)
            if balance < pkg["afn"]:
                await update.message.reply_text(
                    f"❌ *Not enough balance.*\n\n"
                    f"Your balance: *{balance} AFN*\n"
                    f"Required: *{pkg['afn']} AFN*\n\n"
                    "Please add balance first.",
                    parse_mode="Markdown",
                )
                return

            if not code_store.get(pkg_key):
                await update.message.reply_text("❌ This package is currently out of stock. Contact support.")
                return

            wallets[user.id] = balance - pkg["afn"]
            code = code_store[pkg_key].pop(0)

            await context.bot.send_message(
                ADMIN_ID,
                f"🎮 *WALLET ORDER — AUTO DELIVERED*\n\n"
                f"👤 `{user.id}` | @{user.username or 'N/A'}\n"
                f"Package: *{pkg['uc']} UC*\n"
                f"Player ID: `{pid}`\n"
                f"Paid: *{pkg['afn']} AFN*\n"
                f"Code sent: `{code}`",
                parse_mode="Markdown",
            )
            await update.message.reply_text(
                f"✅ *Payment Confirmed & Code Delivered!*\n\n"
                f"🎮 Package: *{pkg['uc']} UC*\n"
                f"🎯 Player ID: `{pid}`\n\n"
                f"🔑 *Your UC Code:*\n`{code}`\n\n"
                "Thank you for shopping at Apex Digital House! 🇦🇫",
                parse_mode="Markdown",
            )
            return

        # HesabPay / USDT — needs admin confirmation
        order_id = f"ORDER-{user.id}-{update.message.message_id}"
        pending_orders[order_id] = {
            "user_id":   user.id,
            "pkg_key":   pkg_key,
            "player_id": pid,
            "payment":   payment,
            "price":     price,
        }

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm & Send Code", callback_data=f"order_confirm_{order_id}"),
            InlineKeyboardButton("❌ Reject",              callback_data=f"order_reject_{order_id}"),
        ]])

        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 *NEW UC ORDER*\n\n"
            f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 `{user.id}`\n"
            f"Order ID: `{order_id}`\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"💰 Price: *{price}*\n"
            f"🎯 Player ID: `{pid}`\n"
            f"💳 Payment: *{payment.upper()}*\n"
            f"🗄️ Codes in stock: *{len(code_store.get(pkg_key, []))}*",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        pay_info = (f"💎 USDT Wallet:\n`{USDT_WALLET}`"
                    if payment == "usdt"
                    else f"📲 HesabPay:\n`{HESABPAY_NUMBER}`")
        await update.message.reply_text(
            f"✅ *Order Received!*\n\n"
            f"🎮 {pkg['uc']} UC — {price}\n"
            f"🎯 Player ID: `{pid}`\n\n"
            f"{pay_info}\n\n"
            "Send your payment screenshot here and we'll confirm shortly! ⏳",
            parse_mode="Markdown",
        )


# ── Screenshot handler (for screenshot sent directly to bot) ─────────────
async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """If user sends a photo directly to bot, forward to admin."""
    user = update.message.from_user
    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=f"📸 Screenshot from {user.first_name} (@{user.username or 'N/A'}) ID:`{user.id}`",
        parse_mode="Markdown",
    )
    await update.message.reply_text("📸 Screenshot received! Admin is reviewing your payment.")


# ── Wallet admin actions ─────────────────────────────────────────────────
async def wallet_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data
    if data.startswith("wallet_confirm_"):
        deposit_id = data.replace("wallet_confirm_", "")
        deposit    = pending_wallet_deposits.get(deposit_id)
        if not deposit:
            await query.edit_message_text("⚠️ Already handled or not found.")
            return
        user_id = deposit["user_id"]
        amount  = deposit["amount"]
        wallets[user_id] = wallets.get(user_id, 0) + amount
        new_bal = wallets[user_id]
        await context.bot.send_message(
            user_id,
            f"✅ *Payment Confirmed!*\n\n"
            f"*{amount} AFN* added to your wallet.\n"
            f"💰 New balance: *{new_bal} AFN*\n\n"
            "Open the store to place your order!",
            parse_mode="Markdown",
        )
        pending_wallet_deposits.pop(deposit_id, None)
        await query.edit_message_text(f"✅ Confirmed — {amount} AFN. New balance: {new_bal} AFN")

    elif data.startswith("wallet_reject_"):
        deposit_id = data.replace("wallet_reject_", "")
        deposit    = pending_wallet_deposits.get(deposit_id)
        if not deposit:
            await query.edit_message_text("⚠️ Already handled or not found.")
            return
        user_id = deposit["user_id"]
        amount  = deposit["amount"]
        await context.bot.send_message(
            user_id,
            f"❌ *Deposit Rejected*\n\n"
            f"Your deposit of *{amount} AFN* was not approved.\n"
            f"Contact support: {TELEGRAM_SUPPORT}",
            parse_mode="Markdown",
        )
        pending_wallet_deposits.pop(deposit_id, None)
        await query.edit_message_text(f"❌ Rejected — {amount} AFN deposit.")


# ── Order admin actions ──────────────────────────────────────────────────
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
            await query.edit_message_text("⚠️ Already handled or not found.")
            return
        pkg_key   = order["pkg_key"]
        pkg       = PACKAGES[pkg_key]
        user_id   = order["user_id"]
        player_id = order["player_id"]

        if not code_store.get(pkg_key):
            await query.edit_message_text(f"❌ Out of stock for {pkg['uc']} UC! Add codes first.")
            return

        code      = code_store[pkg_key].pop(0)
        remaining = len(code_store[pkg_key])

        await context.bot.send_message(
            user_id,
            f"✅ *Payment Confirmed! Here is your UC Code:*\n\n"
            f"🎮 Package: *{pkg['uc']} UC*\n"
            f"🎯 Player ID: `{player_id}`\n\n"
            f"🔑 *Your Code:*\n`{code}`\n\n"
            "Thank you for shopping at Apex Digital House! 🇦🇫",
            parse_mode="Markdown",
        )
        pending_orders.pop(order_id, None)
        await query.edit_message_text(
            f"✅ Order confirmed — Code `{code}` sent.\n"
            f"Remaining stock for {pkg['uc']} UC: *{remaining}*",
            parse_mode="Markdown",
        )

    elif data.startswith("order_reject_"):
        order_id = data.replace("order_reject_", "")
        order    = pending_orders.get(order_id)
        if not order:
            await query.edit_message_text("⚠️ Already handled or not found.")
            return
        user_id = order["user_id"]
        pkg     = PACKAGES[order["pkg_key"]]
        await context.bot.send_message(
            user_id,
            f"❌ *Order Rejected*\n\n"
            f"Your order for *{pkg['uc']} UC* was not approved.\n"
            f"Contact support: {TELEGRAM_SUPPORT}",
            parse_mode="Markdown",
        )
        pending_orders.pop(order_id, None)
        await query.edit_message_text(f"❌ Rejected — {pkg['uc']} UC order.")


# ── Admin code management ────────────────────────────────────────────────
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
        await update.message.reply_text("❌ Session lost. Use /start again.")
        return ConversationHandler.END

    codes = [c.strip() for c in update.message.text.strip().splitlines() if c.strip()]
    if not codes:
        await update.message.reply_text("❌ No codes found. Send one per line.")
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
    await update.message.reply_text("Cancelled. Use /start to open the store.")
    return ConversationHandler.END


# ── Main ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler just for admin code entry
    code_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_start_add_codes, pattern="^admin_addcodes_")],
        states={ADMIN_ADD_CODES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_codes)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("stock",   admin_stock_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO, receive_screenshot))
    app.add_handler(CallbackQueryHandler(admin_codes_menu,      pattern="^admin_codes$"))
    app.add_handler(CallbackQueryHandler(wallet_admin_action,   pattern="^wallet_(confirm|reject)_"))
    app.add_handler(CallbackQueryHandler(order_admin_action,    pattern="^order_(confirm|reject)_"))
    app.add_handler(code_conv)

    print("🤖 Apex UC Bot + Mini App running…")
    app.run_polling()
