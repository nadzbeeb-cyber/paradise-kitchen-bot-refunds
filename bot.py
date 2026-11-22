import os
import logging
import sqlite3
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# ================= CONFIGURATION =================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0")) 

# Railway Volume path for the database
DB_PATH = "/app/data/orders.db" 

# --- YOUR LINKS ---
GROUP_LINK = "https://t.me/+p9UywWB_4MMxZGNh"
STORE_NA_LINK = "https://rentry.co/3v7b9vus"
STORE_EU_LINK = "https://rentry.co/zzhinprb"
# =================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= FORM QUESTIONS =================
REFUND_QUESTIONS = [
    ("🏬 Whats The Store Name?", "Store Name", "text"),
    ("📅 When Was The Date Package Was Delivered? DD/MM", "Delivery Date", "text"),
    ("👤 Whats The Full Name On The Order?", "Full Name", "text"),
    ("📧 Whats The Email Address?", "Email Address", "text"),
    ("📦 Full address incl. postal code", "Shipping Address", "text"),
    ("💳 Billing Address?", "Billing Address", "text"),
    ("🔢 Whats The Order Number?", "Order Number", "text"),
    ("📞 Phone Number?", "Phone Number", "text"),
    ("🔐 Login:Password Combination?", "Login:Password Combination", "text")
]

B4U_QUESTIONS = [
    ("🏬 Whats The Store Name?", "Store Name", "text"),
    ("🛒 Please send a picture of your cart.\n\n📸 <b>Post all pictures at once.</b>\nWhen you are done, click the 'Done' button below.", "Cart Pictures", "media"),
    ("📦 Full address incl. postal code", "Shipping Address", "text"),
    ("💰 Total with tax?", "Total with tax", "text")
]

# ================= DATABASE =================
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            type TEXT,
            status TEXT,
            claimed_by TEXT,
            data TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_order(order_id, order_type, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (order_id, type, status, data) VALUES (?, ?, ?, ?)",
                   (order_id, order_type, "Open", json.dumps(data)))
    conn.commit()
    conn.close()

def update_order_status(order_id, status, claimed_by=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ?, claimed_by = ? WHERE order_id = ?", (status, claimed_by, order_id))
    conn.commit()
    conn.close()

def get_detailed_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
    counts = dict(cursor.fetchall())
    
    cursor.execute("SELECT order_id, type FROM orders WHERE status = 'Open' ORDER BY order_id DESC LIMIT 15")
    open_orders = cursor.fetchall()
    
    cursor.execute("SELECT order_id, type, claimed_by FROM orders WHERE status = 'Claimed' ORDER BY order_id DESC LIMIT 15")
    claimed_orders = cursor.fetchall()
    
    conn.close()
    return counts, open_orders, claimed_orders

# ================= MENUS & BUTTONS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    # Embedded links in the text using HTML format
    welcome_text = (
        "🎁 <b>Welcome to the Paradise Club!</b>\n\n"
        "Join our community and browse our store lists:\n"
        "💬 <a href='https://t.me/+p9UywWB_4MMxZGNh'>Join Our Telegram Group</a>\n"
        "🇺🇸 <a href='https://rentry.co/3v7b9vus'>North America Store List</a>\n"
        "🇪🇺 <a href='https://rentry.co/zzhinprb'>Europe Store List</a>\n\n"
        "💬 <b>Support:</b> @chefsatoshii\n"
        "📝 <b>Note:</b> You can type /stop at any time to cancel a form."
    )
    
    # Buttons for easy access
    keyboard = [
        [InlineKeyboardButton("💬 Join Our Group", url=GROUP_LINK)],
        [InlineKeyboardButton("🇺🇸 North America Store List", url=STORE_NA_LINK)],
        [InlineKeyboardButton("🇪🇺 Europe Store List", url=STORE_EU_LINK)],
        [InlineKeyboardButton("💸 Submit Refund Form", callback_data="start_refund")],
        [InlineKeyboardButton("🛍️ B4U Orders", callback_data="start_b4u")]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE, form_type):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['step'] = 0
    context.user_data['data'] = {}
    context.user_data['attempts'] = 5
    context.user_data['in_form'] = True
    context.user_data['type'] = form_type
    await send_question(query.message.chat_id, context)

async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step', 0)
    form_type = context.user_data.get('type')
    questions = REFUND_QUESTIONS if form_type == "refund" else B4U_QUESTIONS
    q_text, _, q_type = questions[step]
    checkmarks = "✅" * (step + 1)
    
    msg = (
        f"{checkmarks}\n\n"
        f"<b>{q_text}</b>\n\n"
        f"📢 Please send only text messages. Attempts left: {context.user_data['attempts']}\n"
        f"💡 Type /stop to cancel the form"
    )
    
    if q_type == "media":
        keyboard = [[InlineKeyboardButton("✅ Done uploading pictures", callback_data="done_media")]]
        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('in_form'): return
    step = context.user_data.get('step', 0)
    form_type = context.user_data.get('type')
    questions = REFUND_QUESTIONS if form_type == "refund" else B4U_QUESTIONS
    
    if step >= len(questions): return 
    
    _, key, q_type = questions[step]
    
    if q_type == "media":
        if update.message.photo:
            file_id = update.message.photo[-1].file_id 
            context.user_data['data'].setdefault(key, []).append(file_id)
            await update.message.reply_text("📸 Image saved. Send more or click 'Done'.")
        elif update.message.document and update.message.document.mime_type.startswith("image/"):
            file_id = update.message.document.file_id
            context.user_data['data'].setdefault(key, []).append(file_id)
            await update.message.reply_text("📸 Image saved. Send more or click 'Done'.")
        else:
            await update.message.reply_text("❌ Please send an image, or click the '✅ Done uploading pictures' button to proceed.")
        return 
        
    if not update.message.text:
        context.user_data['attempts'] -= 1
        if context.user_data['attempts'] <= 0:
            context.user_data['in_form'] = False
            await update.message.reply_text("❌ You have run out of attempts. Form cancelled.")
        else:
            await update.message.reply_text(f"❌ Please send only text.\n\n📢 Attempts left: {context.user_data['attempts']}\n💡 Type /stop to cancel.")
        return

    context.user_data['data'][key] = update.message.text
    context.user_data['step'] += 1
    
    if context.user_data['step'] < len(questions):
        await send_question(update.message.chat_id, context)
    else:
        await show_summary(update.message.chat_id, context)

async def show_summary(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['in_form'] = False
    data = context.user_data['data']
    form_type = context.user_data.get('type')
    questions = REFUND_QUESTIONS if form_type == "refund" else B4U_QUESTIONS
    
    summary_text = f"📋 <b>Please review your {form_type.upper()} submission:</b>\n\n"
    for _, key, q_type in questions:
        if q_type == "media":
            count = len(data.get(key, []))
            summary_text += f"<b>{key}:</b> [{count} Image(s) Attached]\n"
        else:
            summary_text += f"<b>{key}:</b> {data.get(key, 'Not provided')}\n"
            
    summary_text += "\n<b>Is this information correct?</b>"
    
    keyboard = [[
        InlineKeyboardButton("✅ Yes, Submit", callback_data="yes_submit"),
        InlineKeyboardButton("🔄 No, Redo", callback_data="no_redo")
    ]]
    await context.bot.send_message(chat_id=chat_id, text=summary_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ================= ADMIN ACTIONS & CALLBACKS =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "start_refund": await start_form(update, context, "refund")
    elif data == "start_b4u": await start_form(update, context, "b4u")
    
    elif data == "done_media":
        context.user_data['step'] += 1
        form_type = context.user_data.get('type')
        questions = REFUND_QUESTIONS if form_type == "refund" else B4U_QUESTIONS
        if context.user_data['step'] < len(questions):
            await query.edit_message_reply_markup(reply_markup=None) 
            await send_question(query.message.chat_id, context)
        else:
            await query.edit_message_reply_markup(reply_markup=None)
            await show_summary(query.message.chat_id, context)
    
    elif data == "yes_submit":
        user_data = context.user_data.get('data', {})
        form_type = context.user_data.get('type')
        user = query.from_user
        order_id = f"{form_type[:3].upper()}-{user.id}-{int(query.message.date.timestamp())}"
        
        save_order(order_id, form_type, user_data)
        
        log_text = f"📥 <b>New {form_type.upper()} Submission</b>\nOrder Ref: <code>{order_id}</code>\nSubmitted by: @{user.username} (ID: {user.id})\n\n"
        for key, val in user_data.items():
            if isinstance(val, list):
                log_text += f"<b>{key}:</b> [{len(val)} Image(s) Below]\n"
            else:
                log_text += f"<b>{key}:</b> {val}\n"
                
        keyboard = [[
            InlineKeyboardButton("🤝 Claim Order", callback_data=f"claim_{order_id}"),
            InlineKeyboardButton("❌ Close Order", callback_data=f"close_{order_id}")
        ]]
        
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=log_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        
        for key, val in user_data.items():
            if isinstance(val, list) and len(val) > 0:
                if len(val) == 1:
                    await context.bot.send_photo(chat_id=ADMIN_GROUP_ID, photo=val[0], caption=f"Images for {order_id}")
                else:
                    media_group = [InputMediaPhoto(media=file_id) for file_id in val[:10]]
                    await context.bot.send_media_group(chat_id=ADMIN_GROUP_ID, media=media_group)
                    if len(val) > 10:
                        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text="⚠️ Note: Only the first 10 images were displayed here.")
        
        await query.edit_message_text(text=f"✅ Thank you! Your {form_type.upper()} order is in progress.\n\nYou'll be contacted by an admin upon completion.", parse_mode="HTML")
        context.user_data.clear()
        
    elif data == "no_redo":
        await query.edit_message_text(text="🔄 Let's start over.")
        context.user_data['step'] = 0
        context.user_data['data'] = {}
        context.user_data['attempts'] = 5
        context.user_data['in_form'] = True
        await send_question(query.message.chat_id, context)

    elif data.startswith("claim_"):
        order_id = data.split("_")[1]
        admin_name = query.from_user.first_name
        update_order_status(order_id, "Claimed", admin_name)
        
        new_keyboard = [[
            InlineKeyboardButton("🔓 Unclaim", callback_data=f"unclaim_{order_id}"),
            InlineKeyboardButton("✅ Close Order", callback_data=f"close_{order_id}")
        ]]
        text = query.message.text_html + f"\n\n🤝 <b>Status: CLAIMED by {admin_name}</b>"
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(new_keyboard), parse_mode="HTML")

    elif data.startswith("unclaim_"):
        order_id = data.split("_")[1]
        update_order_status(order_id, "Open", None)
        
        new_keyboard = [[
            InlineKeyboardButton("🤝 Claim Order", callback_data=f"claim_{order_id}"),
            InlineKeyboardButton("❌ Close Order", callback_data=f"close_{order_id}")
        ]]
        text = query.message.text_html
        if "Status: CLAIMED" in text:
             text = text.split("\n\n🤝")[0]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(new_keyboard), parse_mode="HTML")

    elif data.startswith("close_"):
        order_id = data.split("_")[1]
        update_order_status(order_id, "Closed", query.from_user.first_name)
        
        text = query.message.text_html + f"\n\n✅ <b>Status: CLOSED</b>"
        await query.edit_message_text(text=text, reply_markup=None, parse_mode="HTML")

# ================= STATS COMMAND =================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    
    counts, open_orders, claimed_orders = get_detailed_stats()
    
    msg = "📊 <b>Order Tracking Stats</b>\n\n"
    msg += f"🟢 <b>Open:</b> {counts.get('Open', 0)} | 🤝 <b>Claimed:</b> {counts.get('Claimed', 0)} | ✅ <b>Closed:</b> {counts.get('Closed', 0)}\n\n"
    
    msg += "🟢 <b>Open Orders:</b>\n"
    if not open_orders:
        msg += "<i>None</i>\n"
    else:
        for order_id, o_type in open_orders:
            msg += f"• <code>{order_id}</code> ({o_type.capitalize()})\n"
            
    msg += "\n🤝 <b>Claimed Orders:</b>\n"
    if not claimed_orders:
        msg += "<i>None</i>\n"
    else:
        for order_id, o_type, claimed_by in claimed_orders:
            msg += f"• <code>{order_id}</code> ({o_type.capitalize()}) - <i>Claimed by {claimed_by}</i>\n"
            
    if len(msg) > 4000:
        await update.message.reply_text("📊 <b>Stats too long to display fully.</b> Please close some orders to see the list.", parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('in_form'):
        context.user_data.clear()
        await update.message.reply_text("❌ Form cancelled.")
    else:
        await update.message.reply_text("❌ You don't have an active form.")

# ================= MAIN =================
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stop', stop))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()
