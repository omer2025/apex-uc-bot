from pathlib import Path

src_path = Path("/mnt/data/apex_60uc_afn_bot.py")
code = src_path.read_text(encoding="utf-8")

# Update the start text to make it closer to the other bot style
code = code.replace(
'''        "🎮 *Welcome to Apex Digital House!*\\n\\n"
        "🇦🇫 PUBG Mobile UC Store\\n\\n"
        f"✅ Product: *60 UC only*\\n"
        f"💰 Price: *{get_price_afn()} AFN*\\n"
        f"🗄️ Ready stock: *{available_stock()} code(s)*\\n\\n"
        "Choose an option below:",''',
'''        "⚡ *Apex UC Store*\\n\\n"
        "🎮 PUBG Mobile UC Delivery\\n"
        "This process may take a few seconds.\\n\\n"
        f"💰 60 UC — *{get_price_afn()} AFN*\\n"
        f"📦 Ready stock: *{available_stock()} code(s)*\\n\\n"
        "Choose an option below:",'''
)

code = code.replace(
'''        "🎮 *Apex Digital House*\\n\\n"
        f"60 UC Price: *{get_price_afn()} AFN*\\n"
        f"Ready stock: *{available_stock()} code(s)*\\n\\n"
        "Choose an option:",''',
'''        "⚡ *Apex UC Store*\\n\\n"
        f"💰 60 UC — *{get_price_afn()} AFN*\\n"
        f"📦 Ready stock: *{available_stock()} code(s)*\\n\\n"
        "Choose an option:",'''
)

code = code.replace(
'''        f"🎮 *Buy 60 UC*\\n\\n"
        f"Price: *{get_price_afn()} AFN*\\n\\n"
        "Please enter your PUBG Mobile Player ID.\\n\\n"
        "⚠️ Double-check your Player ID. Wrong ID = wrong delivery.",''',
'''        "📝 Please send / enter Player ID:\\n\\n"
        f"🎮 Package: *60 UC*\\n"
        f"💰 Price: *{get_price_afn()} AFN*\\n\\n"
        "⚠️ Double-check your Player ID. Wrong ID = wrong delivery.",'''
)

# Add bot command reset imports and function if not present
code = code.replace(
"from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup",
"from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand"
)

insert_after = '''async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Type /start to begin again.")
    return ConversationHandler.END


'''
set_commands_func = '''async def set_start_only_command(app: Application):
    # This removes /shop, /support, /payment from Telegram suggestions.
    # Only /start will show in the command menu.
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot")
    ])


'''
if "set_start_only_command" not in code:
    code = code.replace(insert_after, insert_after + set_commands_func)

code = code.replace(
'''    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(''',
'''    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(set_start_only_command)
        .build()
    )

    conv = ConversationHandler('''
)

out_path = Path("/mnt/data/apex_60uc_afn_bot_start_only.py")
out_path.write_text(code, encoding="utf-8")
print(f"Created {out_path}")
