import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# ================= CONFIGURATION =================
# 1. Paste your Telegram Bot Token from BotFather here
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# 2. Create a Telegram Group, add your bot and your co-admin to it. 
#    Get the Group Chat ID (you can use @userinfobot or @RawDataBot to find it).
#    It will look like a negative number, e.g., -1001234567890
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))  # <-- CHANGE THIS
# =================================================

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# The questions and their corresponding keys for the final log
QUESTIONS = [
    ("🏬 Whats The Store Name?", "Store Name"),
    ("📅 When Was The Date Package Was Delivered? DD/MM", "Delivery Date"),
    ("👤 Whats The Full Name On The Order?", "Full Name"),
    ("📧 Whats The Email Address?", "Email Address"),
    ("📦 Full address incl. postal code", "Shipping Address"),
    ("💳 Billing Address?", "Billing Address"),
    ("🔢 Whats The Order Number?", "Order Number"),
    ("🚚 Carrier Tracking Number?", "Carrier Tracking Number"),
    ("📞 Phone Number?", "Phone Number"),
    ("🔐 Login:Password Combination?", "Login:Password Combination")
]

# ================= START COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reset user state
    context.user_data.clear()
    
    welcome_text = (
        "🎁 <b>Welcome to the Paradise Kitchen Refunds Form Submission Bot!</b>\n\n"
        "Click the button below to start submitting your information.\n\n"
        "📝 <b>Note:</b> You can type /stop at any time to cancel the form.\n\n"
        "For B4U orders dm @chefsatoshii"
    )
    
    keyboard = [[InlineKeyboardButton("📝 SUBMIT INFORMATION", callback_data="start_form")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")

# ================= FORM LOGIC =================
async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    context.user_data['step'] = 0
    context.user_data['data'] = {}
    context.user_data['attempts'] = 5
    context.user_data['in_form'] = True
    
    # Send the first question
    await send_question(query.message.chat_id, context)

async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step', 0)
    q_text, _ = QUESTIONS[step]
    checkmarks = "✅" * (step + 1)
    
    msg = (
        f"{checkmarks}\n\n"
        f"<b>{q_text}</b>\n\n"
        f"📢 Please send only text messages. Attempts left: {context.user_data['attempts']}\n"
        f"💡 Type /stop to cancel the form"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('in_form'):
        return
        
    step = context.user_data.get('step', 0)
    
    if step >= len(QUESTIONS):
        return # Should be handled by buttons
        
    # Check if it's a text message
    if not update.message.text:
        context.user_data['attempts'] -= 1
        if context.user_data['attempts'] <= 0:
            context.user_data['in_form'] = False
            await update.message.reply_text("❌ You have run out of attempts. Form cancelled. Type /start to try again.")
        else:
            await update.message.reply_text(
                f"❌ Please send only text messages.\n\n"
                f"📢 Attempts left: {context.user_data['attempts']}\n"
                f"💡 Type /stop to cancel the form"
            )
        return

    # Save the answer
    _, key = QUESTIONS[step]
    context.user_data['data'][key] = update.message.text
    context.user_data['step'] += 1
    
    # Check if form is complete
    if context.user_data['step'] < len(QUESTIONS):
        await send_question(update.message.chat_id, context)
    else:
        await show_summary(update.message.chat_id, context)

async def show_summary(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['in_form'] = False
    data = context.user_data['data']
    
    summary_text = "📋 <b>Please review your submission:</b>\n\n"
    for _, key in QUESTIONS:
        val = data.get(key, "Not provided")
        summary_text += f"<b>{key}:</b> {val}\n"
    
    summary_text += "\n<b>Is this information correct?</b>"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Submit", callback_data="yes_submit"),
            InlineKeyboardButton("🔄 No, Redo", callback_data="no_redo")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(chat_id=chat_id, text=summary_text, reply_markup=reply_markup, parse_mode="HTML")

# ================= CALLBACK BUTTONS =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_form":
        await start_form(update, context)
        
    elif query.data == "yes_submit":
        data = context.user_data.get('data', {})
        user = query.from_user
        
        # Build the admin log message
        log_text = (
            f"📥 <b>New Refund Form Submission</b>\n"
            f"Submitted by: @{user.username} (ID: {user.id})\n\n"
        )
        for _, key in QUESTIONS:
            log_text += f"<b>{key}:</b> {data.get(key, 'Not provided')}\n"
            
        # Send to the admin group
        try:
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=log_text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to send to admin group: {e}")
            
        # Send final confirmation to user
        await query.edit_message_text(
            text="✅ Thank you! Your order is in progress. You'll be contacted by an admin upon completion.",
            parse_mode="HTML"
        )
        
        # Clear user data
        context.user_data.clear()
        
    elif query.data == "no_redo":
        await query.edit_message_text(text="🔄 Let's start over.")
        context.user_data['step'] = 0
        context.user_data['data'] = {}
        context.user_data['attempts'] = 5
        context.user_data['in_form'] = True
        await send_question(query.message.chat_id, context)

# ================= STOP COMMAND =================
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('in_form'):
        context.user_data.clear()
        await update.message.reply_text("❌ You have cancelled the form.")
    else:
        await update.message.reply_text("❌ You don't have an active form.")

# ================= MAIN =================
if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    
    # Button handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handler (for form answers)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    application.run_polling()
