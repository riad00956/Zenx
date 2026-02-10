"""
ZEN X HOST BOT v4.0 - Telegram Bot Handlers
All bot commands, callbacks, and message handlers
"""

import os
import telebot
import threading
import time
import random
import json
import uuid
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from telebot import types
from werkzeug.utils import secure_filename

# Import shared functions
from main import (
    Config, get_db, execute_db, get_user, get_user_bots,
    backup_database, get_system_stats, get_available_nodes,
    check_prime_expiry, update_user_bot_count, create_progress_bar,
    log_event, log_bot_event, send_notification, start_bot_monitoring,
    assign_bot_to_node, extract_zip_file
)

bot = telebot.TeleBot(Config.TOKEN, parse_mode="Markdown")
logger = telebot.logger

# User session management
user_sessions = {}

# ==================== HELPER FUNCTIONS ====================

def get_main_keyboard(user_id):
    """Get main menu keyboard"""
    user = get_user(user_id)
    prime_status = check_prime_expiry(user_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if not prime_status['expired']:
        # Prime is active - show all features
        buttons = [
            "📤 Upload Bot", "🤖 My Bots", "🚀 Deploy Bot",
            "📊 Dashboard", "⚙️ Settings", "👑 Prime Info",
            "🔔 Notifications", "📈 Statistics", "🛒 Marketplace",
            "🔄 Auto Recovery", "💾 Backups", "🌐 Nodes"
        ]
    else:
        # Free user
        buttons = [
            "🔑 Activate Prime", "👑 Prime Info", "📞 Contact Admin",
            "ℹ️ Help", "📊 Free Dashboard", "🛒 Browse Bots"
        ]
    
    # Arrange buttons
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        markup.add(*[types.KeyboardButton(btn) for btn in row])
    
    if user_id == Config.ADMIN_ID:
        markup.add(types.KeyboardButton("👑 Admin Panel"))
    
    markup.add(types.KeyboardButton("🏠 Main Menu"))
    return markup

def get_admin_keyboard():
    """Get admin keyboard with all new features"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "🎫 Generate Key", "👥 All Users", "🤖 All Bots",
        "📈 Statistics", "🗄️ View Database", "💾 Backup DB",
        "⚙️ Maintenance", "🌐 Nodes Status", "🔧 Server Logs",
        "📊 System Info", "🔔 Broadcast", "🔄 Cleanup",
        "🛒 Marketplace", "💰 Sales", "🧪 Bot Trials",
        "💳 Payments", "📱 Web Panel", "🔐 Security"
    ]
    
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        markup.add(*[types.KeyboardButton(btn) for btn in row])
    
    markup.add(types.KeyboardButton("🏠 Main Menu"))
    return markup

def get_marketplace_keyboard():
    """Get marketplace keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("🛒 Browse Bots", callback_data="marketplace_browse"),
        types.InlineKeyboardButton("💰 My Purchases", callback_data="marketplace_purchases")
    )
    
    if Config.ADMIN_ID:
        markup.add(
            types.InlineKeyboardButton("👑 Sell Bot", callback_data="marketplace_sell"),
            types.InlineKeyboardButton("📊 Sales Stats", callback_data="marketplace_stats")
        )
    
    markup.add(types.InlineKeyboardButton("❌ Close", callback_data="close_marketplace"))
    return markup

def get_payment_keyboard(bot_id, price):
    """Get payment method keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("💰 bKash", callback_data=f"pay_bkash_{bot_id}_{price}"),
        types.InlineKeyboardButton("📱 Nagad", callback_data=f"pay_nagad_{bot_id}_{price}")
    )
    
    markup.add(
        types.InlineKeyboardButton("🚀 Rocket", callback_data=f"pay_rocket_{bot_id}_{price}"),
        types.InlineKeyboardButton("🏦 Bank", callback_data=f"pay_bank_{bot_id}_{price}")
    )
    
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data=f"bot_{bot_id}"))
    return markup

# ==================== COMMAND HANDLERS ====================

@bot.message_handler(commands=['start', 'menu', 'help'])
def handle_commands(message):
    """Handle start, menu, and help commands"""
    uid = message.from_user.id
    username = message.from_user.username or "User"
    
    if Config.MAINTENANCE and uid != Config.ADMIN_ID:
        bot.send_message(message.chat.id, 
            "🛠 **System Maintenance**\n\nWe're currently upgrading our servers. Please try again later.")
        return
    
    # Register user if not exists
    user = get_user(uid)
    if not user:
        join_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("""
            INSERT OR IGNORE INTO users 
            (id, username, expiry, file_limit, is_prime, join_date, last_renewal, last_active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (uid, username, None, 1, 0, join_date, None, join_date), commit=True)
        user = get_user(uid)
    
    # Clear old session
    user_sessions.pop(uid, None)
    
    prime_status = check_prime_expiry(uid)
    
    # Check for notifications
    unread = execute_db("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", 
                       (uid,), fetchone=True)
    unread_count = unread[0] if unread else 0
    
    # Welcome message with enhanced design
    text = f"""
✨ **WELCOME TO ZEN X HOST v4.0** ✨
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 **User:** @{username}
🆔 **ID:** `{uid}`
💎 **Status:** {'👑 PRIME ACTIVE' if not prime_status['expired'] else '⚠️ PRIME EXPIRED'}
📅 **Join Date:** {user['join_date'] if user else 'N/A'}
🔔 **Notifications:** {unread_count} unread
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Account Summary:**
• Plan: {'Prime' if not prime_status['expired'] else 'Free'}
• File Limit: `{user['file_limit'] if user else 1}` files
• Bots Deployed: {user['total_bots_deployed'] or 0}
• Total Deployments: {user['total_deployments'] or 0}
• Expiry: {prime_status.get('days_left', '0')} days left
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 *Select an option from the keyboard below:*
"""
    
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(uid))

@bot.message_handler(commands=['admin'])
def handle_admin(message):
    """Admin command handler"""
    uid = message.from_user.id
    if uid == Config.ADMIN_ID:
        user_sessions[uid] = {'state': 'admin_panel'}
        
        text = """
👑 **ADMIN CONTROL PANEL v4.0**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 **New Features Available:**
✅ Bot Marketplace System
✅ Advanced Bot Analytics
✅ Bot Trial System
✅ Payment Integration
✅ Script Backup & Test
✅ Web Admin Panel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Select an option from the keyboard below:*
"""
        bot.send_message(message.chat.id, text, reply_markup=get_admin_keyboard())
    else:
        bot.reply_to(message, "⛔ **Access Denied!**")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    """Handle all text messages"""
    uid = message.from_user.id
    text = message.text
    session = user_sessions.get(uid, {})
    
    # Handle session states
    if session.get('state') == 'waiting_for_key':
        process_key_input(message)
    elif session.get('state') == 'waiting_for_bot_name':
        process_bot_name_input(message)
    elif session.get('state') == 'waiting_for_marketplace_title':
        process_marketplace_title(message)
    elif session.get('state') == 'waiting_for_marketplace_desc':
        process_marketplace_desc(message)
    elif session.get('state') == 'waiting_for_marketplace_price':
        process_marketplace_price(message)
    elif session.get('state') == 'waiting_for_payment':
        process_payment_info(message)
    else:
        # Handle main menu buttons
        handle_main_menu_buttons(message)

# ==================== MAIN MENU HANDLERS ====================

def handle_main_menu_buttons(message):
    """Handle main menu button presses"""
    uid = message.from_user.id
    text = message.text
    
    if text == "📤 Upload Bot":
        handle_upload_request(message)
    elif text == "🤖 My Bots":
        handle_my_bots(message)
    elif text == "🚀 Deploy Bot":
        handle_deploy_new(message)
    elif text == "📊 Dashboard":
        handle_dashboard(message)
    elif text == "⚙️ Settings":
        handle_settings(message)
    elif text == "👑 Prime Info":
        handle_premium_info(message)
    elif text == "🔑 Activate Prime":
        handle_activate_prime(message)
    elif text == "🛒 Marketplace":
        handle_marketplace(message)
    elif text == "🔔 Notifications":
        handle_notifications(message)
    elif text == "📈 Statistics":
        handle_user_statistics(message)
    elif text == "👑 Admin Panel":
        handle_admin_panel(message)
    elif text == "🏠 Main Menu":
        handle_commands(message)
    elif text in ["🛒 Browse Bots", "📞 Contact Admin", "ℹ️ Help", "📊 Free Dashboard"]:
        handle_free_features(message, text)
    else:
        handle_admin_buttons(message, text)

def handle_upload_request(message):
    """Handle bot upload request"""
    uid = message.from_user.id
    prime_status = check_prime_expiry(uid)
    
    if prime_status['expired']:
        bot.send_message(message.chat.id,
            "⚠️ **Prime Required**\n\nYour Prime subscription has expired. Please renew to upload files.")
        return
    
    # Check bot limit
    user_bots = get_user_bots(uid)
    if len(user_bots) >= Config.MAX_BOTS_PER_USER:
        bot.send_message(message.chat.id,
            f"❌ **Bot Limit Reached**\n\nYou can only have {Config.MAX_BOTS_PER_USER} bots at a time.")
        return
    
    user_sessions[uid] = {'state': 'waiting_for_file'}
    
    bot.send_message(message.chat.id, """
📤 **UPLOAD BOT FILE v4.0**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Enhanced Features:*
✅ Auto-recovery system
✅ Script validation
✅ Library auto-install
✅ Multi-format support
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Please send your Python (.py) bot file or ZIP file.**

**Requirements:**
• Max size: 5.5MB
• Allowed: .py, .zip
• Must have main() function
• No malicious code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Send file now or type 'cancel' to abort*
""")

def handle_my_bots(message):
    """Display user's bots"""
    uid = message.from_user.id
    bots = get_user_bots(uid)
    
    if not bots:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📤 Upload Bot", callback_data="upload"),
            types.InlineKeyboardButton("🛒 Buy Bot", callback_data="marketplace_browse")
        )
        
        bot.send_message(message.chat.id, """
🤖 **MY BOTS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No bots found. You can:
• Upload your own bot
• Buy from marketplace
• Get a free trial
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""", reply_markup=markup)
        return
    
    running_bots = sum(1 for b in bots if b['status'] == "Running")
    auto_restart_bots = sum(1 for b in bots if b['auto_restart'] == 1)
    
    text = f"""
🤖 **MY BOTS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Statistics:**
• Total Bots: {len(bots)}
• Running: {running_bots}
• Stopped: {len(bots) - running_bots}
• Auto-Recovery: {auto_restart_bots}/{len(bots)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for bot_info in bots[:10]:
        status_icon = "🟢" if bot_info['status'] == "Running" else "🔴"
        auto_icon = "🔁" if bot_info['auto_restart'] == 1 else "⏸️"
        created = bot_info['created_at'].split()[0] if bot_info['created_at'] else "N/A"
        btn_text = f"{status_icon}{auto_icon} {bot_info['bot_name']} ({created})"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"bot_{bot_info['id']}"))
    
    markup.add(
        types.InlineKeyboardButton("📤 Upload New", callback_data="upload"),
        types.InlineKeyboardButton("🛒 Marketplace", callback_data="marketplace_browse")
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

def handle_marketplace(message):
    """Display marketplace"""
    uid = message.from_user.id
    prime_status = check_prime_expiry(uid)
    
    if prime_status['expired']:
        bot.send_message(message.chat.id,
            "⚠️ **Prime Required**\n\nYou need active Prime to access marketplace.")
        return
    
    conn = get_db()
    c = conn.cursor()
    
    # Get featured bots
    c.execute("""
        SELECT mb.*, d.bot_name, u.username as seller_username
        FROM marketplace_bots mb
        JOIN deployments d ON mb.bot_id = d.id
        JOIN users u ON mb.seller_id = u.id
        WHERE mb.status = 'available'
        ORDER BY mb.purchases DESC
        LIMIT 5
    """)
    
    featured = c.fetchall()
    
    # Get categories
    c.execute("SELECT DISTINCT category FROM marketplace_bots WHERE status='available'")
    categories = [row[0] for row in c.fetchall()]
    
    conn.close()
    
    text = """
🛒 **BOT MARKETPLACE v4.0**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Buy & Sell Premium Bots*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 **Featured Bots:**
"""
    
    for item in featured:
        text += f"\n• **{item['title']}** - ${item['price']:.2f}"
        text += f"\n  👤 @{item['seller_username']}"
        text += f"\n  📝 {item['description'][:50]}..."
        text += f"\n  🛒 ID: `{item['id']}`\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "💡 *Use inline buttons to browse:*"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Category buttons
    for cat in categories[:4]:
        markup.add(types.InlineKeyboardButton(f"📁 {cat}", callback_data=f"marketplace_cat_{cat}"))
    
    markup.add(
        types.InlineKeyboardButton("🔍 Search", callback_data="marketplace_search"),
        types.InlineKeyboardButton("💰 My Orders", callback_data="marketplace_orders")
    )
    
    if uid == Config.ADMIN_ID:
        markup.add(types.InlineKeyboardButton("👑 Sell Bot", callback_data="marketplace_sell"))
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

# ==================== ADMIN HANDLERS ====================

def handle_admin_panel(message):
    """Admin panel handler"""
    uid = message.from_user.id
    if uid == Config.ADMIN_ID:
        user_sessions[uid] = {'state': 'admin_panel'}
        bot.send_message(message.chat.id, """
👑 **ADMIN CONTROL PANEL v4.0**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 **Enhanced Features:**
✅ Bot Marketplace System
✅ Advanced Analytics
✅ Bot Trial Management
✅ Payment System
✅ Script Backup & Testing
✅ Web Admin Interface
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Select an option from keyboard:*
""", reply_markup=get_admin_keyboard())
    else:
        bot.reply_to(message, "⛔ **Access Denied!**")

def handle_admin_buttons(message, button_text):
    """Handle admin button presses"""
    uid = message.from_user.id
    
    if uid != Config.ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Access Denied!")
        return
    
    if button_text == "🛒 Marketplace":
        admin_marketplace(message)
    elif button_text == "💰 Sales":
        admin_sales(message)
    elif button_text == "🧪 Bot Trials":
        admin_trials(message)
    elif button_text == "💳 Payments":
        admin_payments(message)
    elif button_text == "📱 Web Panel":
        admin_web_panel(message)
    else:
        # Handle existing admin buttons (from original code)
        pass

def admin_marketplace(message):
    """Admin marketplace management"""
    conn = get_db()
    c = conn.cursor()
    
    # Get marketplace stats
    c.execute("""
        SELECT 
            COUNT(*) as total_listings,
            SUM(price) as total_value,
            COUNT(CASE WHEN status='available' THEN 1 END) as available,
            COUNT(CASE WHEN status='sold' THEN 1 END) as sold
        FROM marketplace_bots
    """)
    
    stats = dict(c.fetchone())
    
    # Get recent sales
    c.execute("""
        SELECT mp.*, mb.title, u.username as buyer
        FROM marketplace_purchases mp
        JOIN marketplace_bots mb ON mp.listing_id = mb.id
        JOIN users u ON mp.buyer_id = u.id
        ORDER BY mp.purchased_at DESC
        LIMIT 5
    """)
    
    recent_sales = c.fetchall()
    
    conn.close()
    
    text = f"""
🛒 **MARKETPLACE ADMIN**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Statistics:**
• Total Listings: {stats['total_listings']}
• Available: {stats['available']}
• Sold: {stats['sold']}
• Total Value: ${stats['total_value'] or 0:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Recent Sales:**
"""
    
    for sale in recent_sales:
        text += f"\n• {sale['title']} - ${sale['price']:.2f}"
        text += f"\n  👤 @{sale['buyer']}"
        text += f"\n  📅 {sale['purchased_at']}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ List Bot", callback_data="admin_marketplace_add"),
        types.InlineKeyboardButton("📊 Analytics", callback_data="admin_marketplace_stats"),
        types.InlineKeyboardButton("📋 All Listings", callback_data="admin_marketplace_list"),
        types.InlineKeyboardButton("💰 Sales Report", callback_data="admin_marketplace_report")
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

def admin_trials(message):
    """Admin bot trial management"""
    conn = get_db()
    c = conn.cursor()
    
    # Get trial stats
    c.execute("""
        SELECT 
            COUNT(*) as total_trials,
            COUNT(CASE WHEN status='active' THEN 1 END) as active,
            COUNT(CASE WHEN status='expired' THEN 1 END) as expired
        FROM bot_trials
    """)
    
    stats = dict(c.fetchone())
    
    # Get active trials
    c.execute("""
        SELECT bt.*, d.bot_name, u.username
        FROM bot_trials bt
        JOIN deployments d ON bt.bot_id = d.id
        JOIN users u ON bt.user_id = u.id
        WHERE bt.status = 'active'
        ORDER BY bt.expires_at
        LIMIT 5
    """)
    
    active_trials = c.fetchall()
    
    conn.close()
    
    text = f"""
🧪 **BOT TRIALS ADMIN**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Statistics:**
• Total Trials: {stats['total_trials']}
• Active: {stats['active']}
• Expired: {stats['expired']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ **Active Trials:**
"""
    
    for trial in active_trials:
        expires = datetime.fromisoformat(trial['expires_at'])
        remaining = expires - datetime.now()
        hours = remaining.total_seconds() // 3600
        
        text += f"\n• {trial['bot_name']}"
        text += f"\n  👤 @{trial['username']}"
        text += f"\n  🆔 Code: `{trial['trial_code']}`"
        text += f"\n  ⏰ {int(hours)}h remaining\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Create Trial", callback_data="admin_trial_create"),
        types.InlineKeyboardButton("📋 All Trials", callback_data="admin_trial_list"),
        types.InlineKeyboardButton("📊 Analytics", callback_data="admin_trial_stats"),
        types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_trials")
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

def admin_payments(message):
    """Admin payment management"""
    conn = get_db()
    c = conn.cursor()
    
    # Get payment stats
    c.execute("""
        SELECT 
            COUNT(*) as total_payments,
            SUM(amount) as total_amount,
            COUNT(CASE WHEN status='completed' THEN 1 END) as completed,
            COUNT(CASE WHEN status='pending' THEN 1 END) as pending
        FROM payment_logs
    """)
    
    stats = dict(c.fetchone())
    
    # Get recent payments
    c.execute("""
        SELECT pl.*, u.username
        FROM payment_logs pl
        LEFT JOIN users u ON pl.user_id = u.id
        ORDER BY pl.created_at DESC
        LIMIT 5
    """)
    
    recent_payments = c.fetchall()
    
    conn.close()
    
    text = f"""
💳 **PAYMENT MANAGEMENT**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Statistics:**
• Total Payments: {stats['total_payments']}
• Completed: {stats['completed']}
• Pending: {stats['pending']}
• Total Amount: ${stats['total_amount'] or 0:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Recent Payments:**
"""
    
    for payment in recent_payments:
        text += f"\n• ${payment['amount']:.2f} via {payment['method']}"
        text += f"\n  👤 @{payment['username'] or 'N/A'}"
        text += f"\n  📝 {payment['purpose'][:30]}..."
        text += f"\n  📅 {payment['created_at']}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 All Payments", callback_data="admin_payments_list"),
        types.InlineKeyboardButton("📊 Revenue Report", callback_data="admin_payments_report"),
        types.InlineKeyboardButton("⚙️ Methods", callback_data="admin_payments_methods"),
        types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_payments")
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

def admin_web_panel(message):
    """Admin web panel info"""
    text = f"""
📱 **WEB ADMIN PANEL**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **Access URL:**
`http://your-server.com:{Config.PORT}/admin/login`

🔐 **Default Credentials:**
• Username: `admin`
• Password: `admin123`

🚀 **Features:**
✅ Full bot management
✅ Marketplace control
✅ Payment tracking
✅ Analytics dashboard
✅ User management
✅ System monitoring
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Change default password after first login!*
"""
    
    bot.send_message(message.chat.id, text)

# ==================== CALLBACK HANDLERS ====================

@bot.callback_query_handler(func=lambda call: True)
def callback_manager(call):
    """Handle all callback queries"""
    uid = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    try:
        if call.data.startswith("marketplace_"):
            handle_marketplace_callbacks(call)
        elif call.data.startswith("admin_"):
            handle_admin_callbacks(call)
        elif call.data.startswith("pay_"):
            handle_payment_callbacks(call)
        elif call.data.startswith("bot_"):
            bot_id = call.data.split("_")[1]
            show_bot_details(call, bot_id)
        elif call.data.startswith("trial_"):
            handle_trial_callbacks(call)
        else:
            # Handle existing callbacks
            handle_standard_callbacks(call)
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "⚠️ Error occurred!")

def handle_marketplace_callbacks(call):
    """Handle marketplace callbacks"""
    data = call.data
    
    if data == "marketplace_browse":
        browse_marketplace(call)
    elif data == "marketplace_sell":
        start_sell_bot(call)
    elif data.startswith("marketplace_view_"):
        listing_id = data.split("_")[2]
        view_listing(call, listing_id)
    elif data.startswith("marketplace_buy_"):
        listing_id = data.split("_")[2]
        start_purchase(call, listing_id)
    elif data.startswith("marketplace_cat_"):
        category = data.split("_")[2]
        browse_category(call, category)

def handle_admin_callbacks(call):
    """Handle admin callbacks"""
    data = call.data
    
    if data == "admin_marketplace_add":
        admin_add_listing(call)
    elif data == "admin_trial_create":
        admin_create_trial(call)
    elif data.startswith("admin_bot_test_"):
        bot_id = data.split("_")[3]
        test_bot(call, bot_id)
    elif data.startswith("admin_bot_backup_"):
        bot_id = data.split("_")[3]
        backup_bot_script(call, bot_id)
    elif data.startswith("admin_bot_analytics_"):
        bot_id = data.split("_")[3]
        show_bot_analytics(call, bot_id)

def handle_payment_callbacks(call):
    """Handle payment callbacks"""
    parts = call.data.split("_")
    method = parts[1]
    bot_id = parts[2]
    price = parts[3]
    
    show_payment_details(call, method, bot_id, price)

def handle_trial_callbacks(call):
    """Handle trial callbacks"""
    if call.data == "trial_create":
        create_trial_request(call)
    elif call.data.startswith("trial_use_"):
        trial_code = call.data.split("_")[2]
        use_trial(call, trial_code)

# ==================== PAYMENT PROCESSING ====================

def show_payment_details(call, method, bot_id, price):
    """Show payment details for selected method"""
    uid = call.from_user.id
    
    payment_methods = {
        'bkash': {
            'name': 'bKash',
            'number': '017xxxxxxxx',
            'type': 'Personal',
            'instructions': 'Send payment and enter transaction ID below'
        },
        'nagad': {
            'name': 'Nagad',
            'number': '018xxxxxxxx',
            'type': 'Personal',
            'instructions': 'Send payment and enter transaction ID below'
        },
        'rocket': {
            'name': 'Rocket',
            'number': '017xxxxxxxx',
            'type': 'Personal',
            'instructions': 'Send payment and enter transaction ID below'
        },
        'bank': {
            'name': 'Bank Transfer',
            'bank': 'City Bank Ltd.',
            'account': '123456789',
            'branch': 'Dhaka',
            'instructions': 'Transfer amount and enter transaction ID below'
        }
    }
    
    method_info = payment_methods.get(method, {})
    
    text = f"""
💳 **PAYMENT: {method_info.get('name', method).upper()}**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Amount:** ${float(price):.2f}
🤖 **Bot ID:** {bot_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 **Payment Details:**
"""
    
    if method == 'bank':
        text += f"🏦 Bank: {method_info.get('bank')}\n"
        text += f"📋 Account: {method_info.get('account')}\n"
        text += f"🏢 Branch: {method_info.get('branch')}\n"
    else:
        text += f"📱 Number: {method_info.get('number')}\n"
        text += f"👤 Type: {method_info.get('type')}\n"
    
    text += f"\n📝 **Instructions:**\n{method_info.get('instructions')}"
    text += f"\n\n🔢 **Send payment and enter transaction ID below:**"
    
    # Store payment session
    user_sessions[uid] = {
        'state': 'waiting_for_payment',
        'method': method,
        'bot_id': bot_id,
        'price': price
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data=f"bot_{bot_id}"))
    
    bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

def process_payment_info(message):
    """Process payment transaction ID"""
    uid = message.from_user.id
    chat_id = message.chat.id
    transaction_id = message.text.strip()
    
    session = user_sessions.get(uid, {})
    
    if not session or session.get('state') != 'waiting_for_payment':
        bot.send_message(chat_id, "❌ Invalid session. Please start over.")
        return
    
    method = session['method']
    bot_id = session['bot_id']
    price = session['price']
    
    # Record payment
    conn = get_db()
    c = conn.cursor()
    
    created_at = datetime.now().isoformat()
    
    # Create payment log
    c.execute("""
        INSERT INTO payment_logs 
        (user_id, amount, method, transaction_id, status, purpose, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        uid,
        float(price),
        method,
        transaction_id,
        'pending',
        f'Bot purchase: {bot_id}',
        created_at
    ))
    
    payment_id = c.lastrowid
    
    # Create purchase record
    c.execute("""
        INSERT INTO marketplace_purchases 
        (listing_id, buyer_id, price, status, payment_method, transaction_id, purchased_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        bot_id,  # Using bot_id as listing_id for simplicity
        uid,
        float(price),
        'pending',
        method,
        transaction_id,
        created_at
    ))
    
    purchase_id = c.lastrowid
    
    conn.commit()
    conn.close()
    
    # Clear session
    user_sessions.pop(uid, None)
    
    # Send confirmation
    text = f"""
✅ **PAYMENT RECORDED**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Amount:** ${float(price):.2f}
📱 **Method:** {method.upper()}
🔢 **Transaction ID:** `{transaction_id}`
📋 **Payment ID:** `{payment_id}`
🛒 **Order ID:** `{purchase_id}`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏳ **Status:** Pending Approval
📞 **Contact admin for approval:** @{Config.ADMIN_USERNAME}
"""
    
    bot.send_message(chat_id, text)
    
    # Notify admin
    admin_text = f"""
🛒 **NEW ORDER RECEIVED**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 **User:** @{message.from_user.username or uid}
💰 **Amount:** ${float(price):.2f}
📱 **Method:** {method.upper()}
🔢 **Transaction ID:** `{transaction_id}`
🤖 **Bot ID:** {bot_id}
🛒 **Order ID:** {purchase_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **Approve:** /approve_order {purchase_id}
❌ **Reject:** /reject_order {purchase_id}
"""
    
    bot.send_message(Config.ADMIN_ID, admin_text)

# ==================== BOT TESTING & BACKUP ====================

def test_bot(call, bot_id):
    """Test run a bot"""
    from main import test_run_bot
    
    success, message = test_run_bot(bot_id)
    
    if success:
        text = f"""
🧪 **BOT TEST COMPLETED**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **Status:** Success
🤖 **Bot ID:** {bot_id}
📝 **Result:**
{message[:1000]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    else:
        text = f"""
🧪 **BOT TEST FAILED**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ **Status:** Failed
🤖 **Bot ID:** {bot_id}
📝 **Error:**
{message[:1000]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id, "🧪 Test completed!")

def backup_bot_script(call, bot_id):
    """Backup bot script"""
    from main import backup_bot_script
    
    backup_path = backup_bot_script(bot_id)
    
    if backup_path:
        try:
            with open(backup_path, 'rb') as f:
                bot.send_document(call.message.chat.id, f,
                                 caption=f"📦 **Bot Script Backup**\n\n🤖 Bot ID: {bot_id}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            backup_path.unlink(missing_ok=True)
            bot.answer_callback_query(call.id, "✅ Backup sent!")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:50]}")
    else:
        bot.answer_callback_query(call.id, "❌ Backup failed!")

def show_bot_analytics(call, bot_id):
    """Show bot analytics"""
    conn = get_db()
    c = conn.cursor()
    
    # Get bot info
    c.execute("SELECT * FROM deployments WHERE id = ?", (bot_id,))
    bot_info = dict(c.fetchone())
    
    # Get analytics
    c.execute("""
        SELECT * FROM bot_analytics 
        WHERE bot_id = ? 
        ORDER BY date DESC 
        LIMIT 7
    """, (bot_id,))
    
    analytics = c.fetchall()
    
    conn.close()
    
    text = f"""
📊 **BOT ANALYTICS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 **Bot:** {bot_info['bot_name']}
🆔 **ID:** {bot_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 **Last 7 Days Performance:**
"""
    
    if analytics:
        for stat in analytics:
            uptime_hours = stat['uptime_seconds'] / 3600
            text += f"\n📅 {stat['date']}:"
            text += f"\n  ⏰ Uptime: {uptime_hours:.1f}h"
            text += f"\n  🔄 Restarts: {stat['restarts']}"
            text += f"\n  🖥️ CPU: {stat['cpu_avg']:.1f}%"
            text += f"\n  💾 RAM: {stat['ram_avg']:.1f}%"
            text += f"\n  ❌ Errors: {stat['errors']}\n"
    else:
        text += "\nNo analytics data available yet."
    
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id, "📊 Analytics sent!")

# ==================== FILE UPLOAD HANDLER ====================

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads"""
    uid = message.from_user.id
    session = user_sessions.get(uid, {})
    
    if session.get('state') != 'waiting_for_file':
        return
    
    try:
        file_name = message.document.file_name.lower()
        
        if not (file_name.endswith('.py') or file_name.endswith('.zip')):
            bot.reply_to(message, "❌ **Invalid File Type!**\n\nOnly Python (.py) or ZIP (.zip) files allowed.")
            return
        
        if message.document.file_size > 5.5 * 1024 * 1024:
            bot.reply_to(message, "❌ **File Too Large!**\n\nMaximum file size is 5.5MB.")
            return
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        original_name = message.document.file_name
        
        # Save file
        project_path = Path(Config.PROJECT_DIR)
        safe_name = secure_filename(original_name)
        
        # Check for duplicates
        counter = 1
        original_safe_name = safe_name
        while (project_path / safe_name).exists():
            name_parts = original_safe_name.rsplit('.', 1)
            safe_name = f"{name_parts[0]}_{counter}.{name_parts[1]}"
            counter += 1
        
        file_path = project_path / safe_name
        file_path.write_bytes(downloaded)
        
        # Update session
        user_sessions[uid] = {
            'state': 'waiting_for_bot_name',
            'filename': safe_name,
            'original_name': original_name
        }
        
        bot.reply_to(message, """
🤖 **BOT NAME SETUP**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **File uploaded successfully!**
📁 **Saved as:** `{safe_name}`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enter a name for your bot (max 50 chars):
Example: `News Bot v2.0`, `Music Player`, `AI Assistant`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".format(safe_name=safe_name))
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        bot.reply_to(message, f"❌ **Error:** {str(e)[:100]}")

def process_bot_name_input(message):
    """Process bot name input"""
    uid = message.from_user.id
    chat_id = message.chat.id
    
    if message.text.lower() == 'cancel':
        user_sessions.pop(uid, None)
        bot.send_message(chat_id, "❌ Cancelled.", reply_markup=get_main_keyboard(uid))
        return
    
    session = user_sessions.get(uid, {})
    if 'filename' not in session:
        bot.send_message(chat_id, "❌ Session expired. Please upload again.")
        return
    
    bot_name = message.text.strip()[:50]
    filename = session['filename']
    original_name = session['original_name']
    
    # Save to database
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    execute_db("""
        INSERT INTO deployments 
        (user_id, bot_name, filename, pid, start_time, status, last_active, auto_restart, created_at, updated_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        uid, bot_name, filename, 0, None, "Uploaded", created_at, 1, created_at, created_at
    ), commit=True)
    
    # Update user bot count
    update_user_bot_count(uid)
    
    # Clear session
    user_sessions.pop(uid, None)
    
    # Send success message
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 Deploy Now", callback_data=f"deploy_new"),
        types.InlineKeyboardButton("⚙️ Settings", callback_data=f"settings"),
        types.InlineKeyboardButton("🛒 Sell Bot", callback_data=f"marketplace_sell"),
        types.InlineKeyboardButton("🤖 My Bots", callback_data=f"my_bots")
    )
    
    text = f"""
✅ **BOT UPLOADED SUCCESSFULLY**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 **Name:** {bot_name}
📁 **File:** `{original_name}`
📊 **Status:** Ready for deployment
🔁 **Auto-Recovery:** Enabled
📅 **Uploaded:** {created_at}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 *What would you like to do next?*
"""
    
    bot.send_message(chat_id, text, reply_markup=markup)
    send_notification(uid, f"Bot '{bot_name}' uploaded successfully!")

# ==================== START BOT POLLING ====================

def start_bot():
    """Start the Telegram bot"""
    print("🤖 Telegram Bot starting...")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
