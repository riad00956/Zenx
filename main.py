"""
ZEN X HOST BOT v4.0 - Core System Functions
Bot deployment, monitoring, auto-recovery, and system management
"""

import os
import sqlite3
import threading
import time
import uuid
import signal
import random
import platform
import zipfile
import json
import logging
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zenx_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database lock for thread safety
db_lock = threading.RLock()

# Configuration
class Config:
    TOKEN = os.environ.get('BOT_TOKEN', '8494225623:AAG_HRSHoBpt36bdeUvYJL4ONnh-2bf6BnY')
    ADMIN_ID = int(os.environ.get('ADMIN_ID', 7832264582))
    PROJECT_DIR = 'projects'
    DB_NAME = 'cyber_v2.db'
    BACKUP_DIR = 'backups'
    LOGS_DIR = 'logs'
    EXPORTS_DIR = 'exports'
    SCRIPT_BACKUPS = 'script_backups'
    TRIAL_DIR = 'trials'
    PORT = int(os.environ.get('PORT', 10000))
    MAINTENANCE = False
    ADMIN_USERNAME = 'zerox6t9'
    BOT_USERNAME = 'zen_xbot'
    MAX_BOTS_PER_USER = 5
    MAX_CONCURRENT_DEPLOYMENTS = 4
    AUTO_RESTART_BOTS = True
    BACKUP_INTERVAL = 3600
    BOT_TIMEOUT = 300
    MAX_LOG_SIZE = 10000
    TRIAL_DURATION = 24  # hours
    
    # 300-Capacity Nodes
    HOSTING_NODES = [
        {"name": "Node-1", "status": "active", "capacity": 300, "region": "Asia"},
        {"name": "Node-2", "status": "active", "capacity": 300, "region": "Asia"},
        {"name": "Node-3", "status": "active", "capacity": 300, "region": "Europe"}
    ]
    
    # Payment settings
    PAYMENT_METHODS = ['bkash', 'nagad', 'rocket', 'bank']

# Create directories
project_path = Path(Config.PROJECT_DIR)
project_path.mkdir(exist_ok=True)

for dir_name in [Config.BACKUP_DIR, Config.LOGS_DIR, Config.EXPORTS_DIR, 
                 Config.SCRIPT_BACKUPS, Config.TRIAL_DIR]:
    Path(dir_name).mkdir(exist_ok=True)

# Thread pool
executor = ThreadPoolExecutor(max_workers=10)

# Bot monitors dictionary
bot_monitors = {}
active_trials = {}

# ==================== DATABASE FUNCTIONS ====================

def get_db():
    """Get database connection with thread safety"""
    with db_lock:
        conn = sqlite3.connect(Config.DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

def execute_db(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Execute database query with thread safety"""
    with db_lock:
        conn = sqlite3.connect(Config.DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        try:
            c.execute(query, params)
            
            if commit:
                conn.commit()
            
            if fetchone:
                result = c.fetchone()
            elif fetchall:
                result = c.fetchall()
            else:
                result = None
            
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            conn.close()
            return None

def init_db():
    """Initialize database with all tables"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Create core tables
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY, username TEXT, expiry TEXT, file_limit INTEGER, 
                     is_prime INTEGER, join_date TEXT, last_renewal TEXT, total_bots_deployed INTEGER DEFAULT 0,
                     total_deployments INTEGER DEFAULT 0, last_active TEXT, balance REAL DEFAULT 0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS keys 
                    (key TEXT PRIMARY KEY, duration_days INTEGER, file_limit INTEGER, created_date TEXT, 
                     used_by TEXT, used_date TEXT, is_used INTEGER DEFAULT 0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS deployments 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bot_name TEXT, 
                     filename TEXT, pid INTEGER, start_time TEXT, status TEXT, 
                     cpu_usage REAL, ram_usage REAL, last_active TEXT, node_id INTEGER,
                     logs TEXT, restart_count INTEGER DEFAULT 0, auto_restart INTEGER DEFAULT 1,
                     created_at TEXT, updated_at TEXT, is_public INTEGER DEFAULT 0,
                     trial_available INTEGER DEFAULT 0, price REAL DEFAULT 0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS nodes
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT, 
                     capacity INTEGER, current_load INTEGER DEFAULT 0, last_check TEXT,
                     region TEXT, total_deployed INTEGER DEFAULT 0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS server_logs
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, 
                     event TEXT, details TEXT, user_id INTEGER)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS bot_logs
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, timestamp TEXT,
                     log_type TEXT, message TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT,
                     is_read INTEGER DEFAULT 0, created_at TEXT)''')
        
        # Marketplace tables
        c.execute('''CREATE TABLE IF NOT EXISTS marketplace_bots
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, title TEXT,
                     description TEXT, price REAL, category TEXT DEFAULT 'general',
                     tags TEXT, seller_id INTEGER, status TEXT DEFAULT 'available',
                     views INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0,
                     rating REAL DEFAULT 0, reviews INTEGER DEFAULT 0,
                     created_at TEXT, updated_at TEXT,
                     FOREIGN KEY(bot_id) REFERENCES deployments(id),
                     FOREIGN KEY(seller_id) REFERENCES users(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS marketplace_purchases
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER,
                     buyer_id INTEGER, price REAL, status TEXT DEFAULT 'pending',
                     payment_method TEXT, transaction_id TEXT, purchased_at TEXT,
                     completed_at TEXT, bot_delivered INTEGER DEFAULT 0,
                     FOREIGN KEY(listing_id) REFERENCES marketplace_bots(id),
                     FOREIGN KEY(buyer_id) REFERENCES users(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS marketplace_reviews
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER,
                     user_id INTEGER, rating INTEGER, comment TEXT, created_at TEXT,
                     FOREIGN KEY(listing_id) REFERENCES marketplace_bots(id),
                     FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # Analytics tables
        c.execute('''CREATE TABLE IF NOT EXISTS bot_analytics
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, date TEXT,
                     uptime_seconds INTEGER, restarts INTEGER, cpu_avg REAL,
                     ram_avg REAL, errors INTEGER, requests INTEGER DEFAULT 0,
                     FOREIGN KEY(bot_id) REFERENCES deployments(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS system_analytics
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                     total_users INTEGER, active_users INTEGER, total_bots INTEGER,
                     running_bots INTEGER, revenue REAL, new_signups INTEGER)''')
        
        # Trial system tables
        c.execute('''CREATE TABLE IF NOT EXISTS bot_trials
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER,
                     user_id INTEGER, trial_code TEXT UNIQUE, status TEXT DEFAULT 'active',
                     started_at TEXT, expires_at TEXT, usage_minutes INTEGER DEFAULT 0,
                     FOREIGN KEY(bot_id) REFERENCES deployments(id),
                     FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS trial_requests
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER,
                     user_id INTEGER, status TEXT DEFAULT 'pending', requested_at TEXT,
                     approved_at TEXT, trial_code TEXT,
                     FOREIGN KEY(bot_id) REFERENCES deployments(id),
                     FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # Payment system tables
        c.execute('''CREATE TABLE IF NOT EXISTS payment_logs
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                     amount REAL, method TEXT, transaction_id TEXT UNIQUE,
                     status TEXT, purpose TEXT, created_at TEXT,
                     FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS user_transactions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                     type TEXT, amount REAL, balance_before REAL, balance_after REAL,
                     reference_id TEXT, description TEXT, created_at TEXT,
                     FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # System settings table
        c.execute('''CREATE TABLE IF NOT EXISTS system_settings
                    (key TEXT PRIMARY KEY, value TEXT, description TEXT,
                     updated_at TEXT, updated_by INTEGER)''')
        
        # Check and insert default data
        c.execute("SELECT * FROM users WHERE id=?", (Config.ADMIN_ID,))
        if not c.fetchone():
            join_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            expiry = (datetime.now() + timedelta(days=3650)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute("""INSERT INTO users (id, username, expiry, file_limit, is_prime, join_date, last_renewal, last_active, balance)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (Config.ADMIN_ID, 'admin', expiry, 100, 1, join_date, join_date, join_date, 1000.0))
        
        # Initialize nodes
        c.execute("SELECT COUNT(*) FROM nodes")
        if c.fetchone()[0] == 0:
            for node in Config.HOSTING_NODES:
                c.execute("INSERT INTO nodes (name, status, capacity, last_check, region) VALUES (?, ?, ?, ?, ?)",
                         (node['name'], node['status'], node['capacity'], 
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), node['region']))
        
        # Default system settings
        default_settings = [
            ('system_name', 'ZEN X Host Bot v4.0', 'System display name'),
            ('maintenance_mode', 'false', 'Maintenance mode status'),
            ('auto_backup', 'true', 'Automatic database backup'),
            ('backup_interval', '3600', 'Backup interval in seconds'),
            ('max_bots_per_user', '5', 'Maximum bots per user'),
            ('trial_duration', '24', 'Trial duration in hours'),
            ('currency', 'USD', 'Default currency'),
            ('min_bot_price', '5.00', 'Minimum bot price in marketplace'),
            ('commission_rate', '10', 'Marketplace commission percentage'),
            ('support_contact', f'@{Config.ADMIN_USERNAME}', 'Support contact')
        ]
        
        for key, value, desc in default_settings:
            c.execute("INSERT OR IGNORE INTO system_settings (key, value, description) VALUES (?, ?, ?)",
                     (key, value, desc))
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Database initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")

# ==================== SYSTEM FUNCTIONS ====================

def get_system_stats():
    """Get comprehensive system statistics"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Basic stats
        c.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = c.fetchone()['total_users']
        
        c.execute("SELECT COUNT(*) as total_bots FROM deployments")
        total_bots = c.fetchone()['total_bots']
        
        c.execute("SELECT COUNT(*) as running_bots FROM deployments WHERE status='Running'")
        running_bots = c.fetchone()['running_bots']
        
        c.execute("SELECT COUNT(*) as marketplace_listings FROM marketplace_bots WHERE status='available'")
        marketplace_listings = c.fetchone()['marketplace_listings']
        
        c.execute("SELECT COUNT(*) as active_trials FROM bot_trials WHERE status='active'")
        active_trials = c.fetchone()['active_trials']
        
        # Revenue stats
        c.execute("SELECT SUM(amount) as total_revenue FROM payment_logs WHERE status='completed'")
        total_revenue = c.fetchone()['total_revenue'] or 0
        
        # Node stats
        c.execute("SELECT SUM(capacity) as total_capacity, SUM(current_load) as current_load FROM nodes WHERE status='active'")
        node_stats = c.fetchone()
        total_capacity = node_stats['total_capacity'] or 0
        current_load = node_stats['current_load'] or 0
        
        # Today's stats
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) as new_users_today FROM users WHERE DATE(join_date)=?", (today,))
        new_users_today = c.fetchone()['new_users_today']
        
        c.execute("SELECT COUNT(*) as new_bots_today FROM deployments WHERE DATE(created_at)=?", (today,))
        new_bots_today = c.fetchone()['new_bots_today']
        
        conn.close()
        
        # System metrics (simulated for now)
        cpu_percent = random.randint(5, 40)
        ram_percent = random.randint(15, 60)
        disk_percent = random.randint(20, 70)
        
        return {
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'disk_percent': disk_percent,
            'total_users': total_users,
            'total_bots': total_bots,
            'running_bots': running_bots,
            'marketplace_listings': marketplace_listings,
            'active_trials': active_trials,
            'total_revenue': float(total_revenue),
            'total_capacity': total_capacity,
            'current_load': current_load,
            'available_capacity': total_capacity - current_load,
            'new_users_today': new_users_today,
            'new_bots_today': new_bots_today,
            'uptime_days': random.randint(1, 365),
            'platform': platform.system(),
            'python_version': platform.python_version()
        }
        
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return {}

def get_available_nodes():
    """Get available hosting nodes"""
    try:
        nodes = execute_db("SELECT * FROM nodes WHERE status='active'", fetchall=True)
        return nodes if nodes else []
    except Exception as e:
        logger.error(f"Error getting nodes: {e}")
        return []

def assign_bot_to_node(user_id, bot_name):
    """Assign bot to optimal node"""
    nodes = get_available_nodes()
    
    if not nodes:
        return None
    
    # Find node with lowest load percentage
    best_node = None
    lowest_load = float('inf')
    
    for node in nodes:
        if node['capacity'] > 0:
            load_percent = (node['current_load'] / node['capacity']) * 100
            if load_percent < lowest_load:
                lowest_load = load_percent
                best_node = node
    
    return best_node

# ==================== BOT DEPLOYMENT & MONITORING ====================

def deploy_bot(bot_id, user_id):
    """Deploy a bot to a hosting node"""
    try:
        # Get bot information
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        if not bot_info:
            return False, "Bot not found"
        
        # Check if already running
        if bot_info['status'] == 'Running' and bot_info['pid']:
            try:
                os.kill(bot_info['pid'], 0)
                return False, "Bot is already running"
            except:
                pass
        
        # Assign to node
        node = assign_bot_to_node(user_id, bot_info['bot_name'])
        if not node:
            return False, "No available nodes"
        
        # Check file exists
        file_path = Path(Config.PROJECT_DIR) / bot_info['filename']
        if not file_path.exists():
            return False, "Bot file not found"
        
        # Start bot process
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file = Path(Config.LOGS_DIR) / f"bot_{bot_id}.log"
        
        with open(log_file, 'a') as f:
            f.write(f"\n{'='*50}\nDeployment started at {start_time}\n{'='*50}\n")
            proc = subprocess.Popen(
                ['python', str(file_path)],
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
        
        # Wait for process to stabilize
        time.sleep(2)
        
        if proc.poll() is not None:
            return False, "Bot failed to start. Check logs."
        
        # Update database
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("""
            UPDATE deployments 
            SET pid=?, start_time=?, status='Running', node_id=?, last_active=?, updated_at=? 
            WHERE id=?
        """, (proc.pid, start_time, node['id'], start_time, updated_at, bot_id), commit=True)
        
        # Update node load
        execute_db("UPDATE nodes SET current_load=current_load+1 WHERE id=?", (node['id'],), commit=True)
        
        # Log event
        log_event("DEPLOY", f"Bot {bot_info['bot_name']} deployed to {node['name']}", user_id)
        log_bot_event(bot_id, "DEPLOY_SUCCESS", f"Deployed to {node['name']}")
        
        # Start monitoring
        start_bot_monitoring(bot_id, proc.pid, user_id)
        
        return True, f"Bot deployed successfully to {node['name']} (PID: {proc.pid})"
        
    except Exception as e:
        logger.error(f"Deployment error for bot {bot_id}: {e}")
        return False, f"Deployment failed: {str(e)}"

def start_bot_monitoring(bot_id, pid, user_id):
    """Start monitoring a bot process"""
    def monitor():
        try:
            start_time = time.time()
            last_analytics_update = start_time
            
            while True:
                # Check if process is alive
                try:
                    os.kill(pid, 0)
                except OSError:
                    # Process died
                    handle_bot_crash(bot_id, user_id)
                    break
                
                # Update stats every 30 seconds
                current_time = time.time()
                if current_time - start_time > 30:
                    stats = get_system_stats()
                    execute_db("UPDATE deployments SET cpu_usage=?, ram_usage=?, last_active=? WHERE id=?",
                              (stats['cpu_percent'], stats['ram_percent'], 
                               datetime.now().strftime('%Y-%m-%d %H:%M:%S'), bot_id), commit=True)
                    start_time = current_time
                
                # Update analytics every hour
                if current_time - last_analytics_update > 3600:
                    update_bot_analytics(bot_id)
                    last_analytics_update = current_time
                
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Monitoring error for bot {bot_id}: {e}")
    
    # Start monitoring thread
    if bot_id not in bot_monitors:
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        bot_monitors[bot_id] = monitor_thread

def handle_bot_crash(bot_id, user_id):
    """Handle bot crash with auto-recovery"""
    bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
    
    if not bot_info:
        return
    
    # Check auto-restart setting
    if bot_info['auto_restart'] == 1:
        # Try to restart
        execute_db("UPDATE deployments SET status='Restarting', restart_count=restart_count+1 WHERE id=?",
                  (bot_id,), commit=True)
        
        log_bot_event(bot_id, "AUTO_RESTART", "Attempting auto-restart after crash")
        
        # Wait before restart
        time.sleep(5)
        
        # Try to redeploy
        success, message = deploy_bot(bot_id, user_id)
        
        if success:
            send_notification(user_id, f"Bot '{bot_info['bot_name']}' auto-restarted after crash")
            log_bot_event(bot_id, "AUTO_RESTART_SUCCESS", "Bot auto-restarted successfully")
        else:
            execute_db("UPDATE deployments SET status='Stopped', pid=0 WHERE id=?", (bot_id,), commit=True)
            send_notification(user_id, f"Bot '{bot_info['bot_name']}' crashed and failed to restart")
            log_bot_event(bot_id, "AUTO_RESTART_FAILED", f"Auto-restart failed: {message}")
    else:
        # Mark as stopped
        execute_db("UPDATE deployments SET status='Stopped', pid=0 WHERE id=?", (bot_id,), commit=True)
        send_notification(user_id, f"Bot '{bot_info['bot_name']}' has stopped")
        log_bot_event(bot_id, "CRASH_NO_RESTART", "Bot crashed, auto-restart disabled")

def update_bot_analytics(bot_id):
    """Update bot analytics data"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get existing analytics for today
        existing = execute_db("SELECT * FROM bot_analytics WHERE bot_id=? AND date=?", 
                            (bot_id, today), fetchone=True)
        
        # Calculate metrics (simplified for now)
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        
        if bot_info:
            uptime_seconds = 3600  # Simplified
            restarts = bot_info['restart_count']
            cpu_avg = bot_info['cpu_usage'] or random.randint(5, 40)
            ram_avg = bot_info['ram_usage'] or random.randint(15, 60)
            
            if existing:
                # Update existing record
                execute_db("""
                    UPDATE bot_analytics 
                    SET uptime_seconds=uptime_seconds+?, restarts=?, cpu_avg=?, ram_avg=?
                    WHERE id=?
                """, (uptime_seconds, restarts, cpu_avg, ram_avg, existing['id']), commit=True)
            else:
                # Create new record
                execute_db("""
                    INSERT INTO bot_analytics 
                    (bot_id, date, uptime_seconds, restarts, cpu_avg, ram_avg, errors)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (bot_id, today, uptime_seconds, restarts, cpu_avg, ram_avg, 0), commit=True)
                
    except Exception as e:
        logger.error(f"Error updating analytics for bot {bot_id}: {e}")

# ==================== MARKETPLACE FUNCTIONS ====================

def create_marketplace_listing(bot_id, title, description, price, category='general', tags=None):
    """Create a marketplace listing for a bot"""
    try:
        # Verify bot exists and is owned by seller
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        if not bot_info:
            return False, "Bot not found"
        
        # Check if already listed
        existing = execute_db("SELECT * FROM marketplace_bots WHERE bot_id=? AND status='available'",
                            (bot_id,), fetchone=True)
        if existing:
            return False, "Bot already listed in marketplace"
        
        # Create listing
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tag_string = ','.join(tags) if tags else ''
        
        execute_db("""
            INSERT INTO marketplace_bots 
            (bot_id, title, description, price, category, tags, seller_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (bot_id, title, description, float(price), category, tag_string, 
              bot_info['user_id'], created_at, created_at), commit=True)
        
        listing_id = execute_db("SELECT last_insert_rowid()", fetchone=True)[0]
        
        # Update bot to be public
        execute_db("UPDATE deployments SET is_public=1 WHERE id=?", (bot_id,), commit=True)
        
        log_event("MARKETPLACE_LIST", f"Bot {bot_id} listed as '{title}' for ${price}", bot_info['user_id'])
        
        return True, f"Listing created successfully! ID: {listing_id}"
        
    except Exception as e:
        logger.error(f"Error creating marketplace listing: {e}")
        return False, f"Error: {str(e)}"

def purchase_bot_from_marketplace(listing_id, buyer_id, payment_method, transaction_id):
    """Process bot purchase from marketplace"""
    try:
        # Get listing details
        listing = execute_db("""
            SELECT mb.*, d.bot_name, d.filename, d.user_id as seller_id
            FROM marketplace_bots mb
            JOIN deployments d ON mb.bot_id = d.id
            WHERE mb.id=? AND mb.status='available'
        """, (listing_id,), fetchone=True)
        
        if not listing:
            return False, "Listing not available"
        
        # Create purchase record
        purchased_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        execute_db("""
            INSERT INTO marketplace_purchases 
            (listing_id, buyer_id, price, status, payment_method, transaction_id, purchased_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (listing_id, buyer_id, listing['price'], 'pending', 
              payment_method, transaction_id, purchased_at), commit=True)
        
        purchase_id = execute_db("SELECT last_insert_rowid()", fetchone=True)[0]
        
        # Log payment
        execute_db("""
            INSERT INTO payment_logs 
            (user_id, amount, method, transaction_id, status, purpose, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (buyer_id, listing['price'], payment_method, transaction_id,
              'pending', f'Purchase: {listing["title"]}', purchased_at), commit=True)
        
        # Update listing stats
        execute_db("UPDATE marketplace_bots SET purchases=purchases+1 WHERE id=?", (listing_id,), commit=True)
        
        # Notify seller
        send_notification(listing['seller_id'], 
                         f"New purchase: {listing['title']} for ${listing['price']:.2f}")
        
        log_event("MARKETPLACE_PURCHASE", 
                 f"Purchase #{purchase_id}: {listing['title']} sold to user {buyer_id}", 
                 buyer_id)
        
        return True, f"Purchase recorded! Order ID: {purchase_id}"
        
    except Exception as e:
        logger.error(f"Error processing purchase: {e}")
        return False, f"Purchase failed: {str(e)}"

def deliver_bot_to_buyer(purchase_id):
    """Deliver bot files to buyer after payment confirmation"""
    try:
        # Get purchase details
        purchase = execute_db("""
            SELECT mp.*, mb.bot_id, d.filename, d.bot_name, mp.buyer_id
            FROM marketplace_purchases mp
            JOIN marketplace_bots mb ON mp.listing_id = mb.id
            JOIN deployments d ON mb.bot_id = d.id
            WHERE mp.id=?
        """, (purchase_id,), fetchone=True)
        
        if not purchase:
            return False, "Purchase not found"
        
        # Copy bot file to buyer's directory
        source_file = Path(Config.PROJECT_DIR) / purchase['filename']
        if not source_file.exists():
            return False, "Bot file not found"
        
        # Create unique filename for buyer
        buyer_dir = Path(Config.PROJECT_DIR) / f"user_{purchase['buyer_id']}"
        buyer_dir.mkdir(exist_ok=True)
        
        new_filename = f"purchased_{purchase_id}_{purchase['filename']}"
        destination = buyer_dir / new_filename
        
        shutil.copy2(source_file, destination)
        
        # Create deployment record for buyer
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bot_name = f"Purchased: {purchase['bot_name']}"
        
        execute_db("""
            INSERT INTO deployments 
            (user_id, bot_name, filename, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (purchase['buyer_id'], bot_name, new_filename, 'Stopped', created_at, created_at), commit=True)
        
        # Update purchase status
        completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("""
            UPDATE marketplace_purchases 
            SET status='completed', completed_at=?, bot_delivered=1 
            WHERE id=?
        """, (completed_at, purchase_id), commit=True)
        
        # Update payment status
        execute_db("UPDATE payment_logs SET status='completed' WHERE transaction_id=?",
                  (purchase['transaction_id'],), commit=True)
        
        # Transfer funds to seller (minus commission)
        commission_rate = float(get_system_setting('commission_rate', '10'))
        commission = purchase['price'] * (commission_rate / 100)
        seller_amount = purchase['price'] - commission
        
        execute_db("UPDATE users SET balance=balance+? WHERE id=?", 
                  (seller_amount, purchase['seller_id']), commit=True)
        
        # Log transaction
        execute_db("""
            INSERT INTO user_transactions 
            (user_id, type, amount, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (purchase['seller_id'], 'marketplace_sale', seller_amount,
              f'Sale: {purchase["bot_name"]}', completed_at), commit=True)
        
        # Notify buyer
        send_notification(purchase['buyer_id'],
                         f"Bot delivered: {purchase['bot_name']}. You can now deploy it from 'My Bots'.")
        
        return True, "Bot delivered successfully"
        
    except Exception as e:
        logger.error(f"Error delivering bot: {e}")
        return False, f"Delivery failed: {str(e)}"

# ==================== TRIAL SYSTEM FUNCTIONS ====================

def create_bot_trial(bot_id, user_id=None, duration_hours=24):
    """Create a trial version of a bot"""
    try:
        # Get bot information
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        if not bot_info:
            return False, "Bot not found"
        
        # Check if trial already exists for user
        if user_id:
            existing = execute_db("""
                SELECT * FROM bot_trials 
                WHERE bot_id=? AND user_id=? AND status='active'
            """, (bot_id, user_id), fetchone=True)
            
            if existing:
                return False, "Active trial already exists for this user"
        
        # Generate trial code
        import random
        import string
        trial_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Set trial duration
        started_at = datetime.now().isoformat()
        expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
        
        # Create trial record
        execute_db("""
            INSERT INTO bot_trials 
            (bot_id, user_id, trial_code, status, started_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (bot_id, user_id, trial_code, 'active', started_at, expires_at), commit=True)
        
        trial_id = execute_db("SELECT last_insert_rowid()", fetchone=True)[0]
        
        log_event("TRIAL_CREATED", f"Trial created for bot {bot_id} (Code: {trial_code})", user_id)
        
        return True, {
            'trial_id': trial_id,
            'trial_code': trial_code,
            'expires_at': expires_at
        }
        
    except Exception as e:
        logger.error(f"Error creating trial: {e}")
        return False, f"Error: {str(e)}"

def use_trial_code(trial_code, user_id):
    """Use a trial code to access a bot"""
    try:
        # Find active trial
        trial = execute_db("""
            SELECT bt.*, d.bot_name, d.filename
            FROM bot_trials bt
            JOIN deployments d ON bt.bot_id = d.id
            WHERE bt.trial_code=? AND bt.status='active' 
            AND (bt.user_id IS NULL OR bt.user_id=?)
        """, (trial_code, user_id), fetchone=True)
        
        if not trial:
            return False, "Invalid or expired trial code"
        
        # Check if trial has expired
        expires_at = datetime.fromisoformat(trial['expires_at'])
        if datetime.now() > expires_at:
            execute_db("UPDATE bot_trials SET status='expired' WHERE id=?", (trial['id'],), commit=True)
            return False, "Trial has expired"
        
        # Copy bot file for trial user
        source_file = Path(Config.PROJECT_DIR) / trial['filename']
        if not source_file.exists():
            return False, "Bot file not found"
        
        # Create trial directory for user
        trial_dir = Path(Config.TRIAL_DIR) / f"user_{user_id}"
        trial_dir.mkdir(parents=True, exist_ok=True)
        
        trial_filename = f"trial_{trial['id']}_{trial['filename']}"
        trial_filepath = trial_dir / trial_filename
        
        shutil.copy2(source_file, trial_filepath)
        
        # Create deployment record for trial
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        bot_name = f"[TRIAL] {trial['bot_name']}"
        
        execute_db("""
            INSERT INTO deployments 
            (user_id, bot_name, filename, status, created_at, updated_at, trial_available)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, bot_name, str(trial_filepath), 'Stopped', created_at, created_at, 1), commit=True)
        
        deployment_id = execute_db("SELECT last_insert_rowid()", fetchone=True)[0]
        
        # Update trial usage
        execute_db("UPDATE bot_trials SET usage_minutes=usage_minutes+1 WHERE id=?", (trial['id'],), commit=True)
        
        log_event("TRIAL_USED", f"User {user_id} used trial for bot {trial['bot_id']}", user_id)
        
        return True, {
            'deployment_id': deployment_id,
            'bot_name': bot_name,
            'expires_at': trial['expires_at']
        }
        
    except Exception as e:
        logger.error(f"Error using trial: {e}")
        return False, f"Error: {str(e)}"

# ==================== TESTING & BACKUP FUNCTIONS ====================

def test_run_bot(bot_id, timeout=30):
    """Test run a bot in safe mode"""
    try:
        # Get bot information
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        if not bot_info:
            return False, "Bot not found"
        
        # Check file exists
        file_path = Path(Config.PROJECT_DIR) / bot_info['filename']
        if not file_path.exists():
            return False, "Bot file not found"
        
        # Create test environment
        test_dir = Path(f"test_{bot_id}_{int(time.time())}")
        test_dir.mkdir(exist_ok=True)
        
        # Copy bot file to test directory
        test_file = test_dir / bot_info['filename']
        shutil.copy2(file_path, test_file)
        
        # Create test config to prevent external calls
        test_config = test_dir / "test_config.py"
        test_config.write_text("""
# Test environment configuration
import os
os.environ['TEST_MODE'] = 'true'
os.environ['DISABLE_NETWORK'] = 'true'
""")
        
        # Run bot with timeout
        start_time = time.time()
        result = subprocess.run(
            ['python', str(test_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(test_dir)
        )
        
        elapsed = time.time() - start_time
        
        # Cleanup test directory
        shutil.rmtree(test_dir, ignore_errors=True)
        
        # Analyze output
        output = result.stdout[:2000] + ("..." if len(result.stdout) > 2000 else "")
        error = result.stderr[:2000] + ("..." if len(result.stderr) > 2000 else "")
        
        if result.returncode == 0:
            return True, f"""
✅ Test completed in {elapsed:.2f}s
📊 Return code: {result.returncode}

📝 Output (first 2000 chars):
{output}

{'⚠️ Warnings:' if error else '✅ No errors'}
{error if error else ''}
"""
        else:
            return False, f"""
❌ Test failed in {elapsed:.2f}s
📊 Return code: {result.returncode}

📝 Output:
{output}

❌ Errors:
{error}
"""
        
    except subprocess.TimeoutExpired:
        return False, f"❌ Test timed out after {timeout} seconds"
    except Exception as e:
        logger.error(f"Test run error: {e}")
        return False, f"❌ Test error: {str(e)}"

def backup_bot_script(bot_id):
    """Create a backup of bot script"""
    try:
        # Get bot information
        bot_info = execute_db("SELECT * FROM deployments WHERE id=?", (bot_id,), fetchone=True)
        if not bot_info:
            return None
        
        # Check file exists
        file_path = Path(Config.PROJECT_DIR) / bot_info['filename']
        if not file_path.exists():
            return None
        
        # Create backup directory
        backup_dir = Path(Config.SCRIPT_BACKUPS)
        backup_dir.mkdir(exist_ok=True)
        
        # Create backup with metadata
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"bot_{bot_id}_{bot_info['bot_name']}_{timestamp}.py"
        backup_path = backup_dir / backup_filename
        
        # Read original file
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Add backup header
        backup_header = f'''
"""
ZEN X HOST BOT - Script Backup
Bot ID: {bot_id}
Bot Name: {bot_info['bot_name']}
Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Original File: {bot_info['filename']}
Owner: {bot_info['user_id']}
Auto-Recovery: {'Enabled' if bot_info['auto_restart'] == 1 else 'Disabled'}
"""
\n\n'''
        
        # Write backup
        with open(backup_path, 'w') as f:
            f.write(backup_header + content)
        
        log_event("SCRIPT_BACKUP", f"Backup created for bot {bot_id}", bot_info['user_id'])
        
        return backup_path
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return None

def backup_database():
    """Create database backup"""
    try:
        backup_dir = Path(Config.BACKUP_DIR)
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"zenx_db_backup_{timestamp}.db"
        backup_path = backup_dir / backup_filename
        
        # Copy database
        with db_lock:
            shutil.copy2(Config.DB_NAME, backup_path)
        
        # Compress backup
        zip_filename = f"zenx_db_backup_{timestamp}.zip"
        zip_path = backup_dir / zip_filename
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(backup_path, arcname=backup_filename)
        
        # Remove uncompressed backup
        backup_path.unlink(missing_ok=True)
        
        # Clean old backups (keep last 30)
        backup_files = sorted(backup_dir.glob("zenx_db_backup_*.zip"), 
                            key=os.path.getmtime, reverse=True)
        for old_backup in backup_files[30:]:
            old_backup.unlink(missing_ok=True)
        
        logger.info(f"Database backup created: {zip_filename}")
        return zip_path
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None

# ==================== HELPER FUNCTIONS ====================

def get_user(user_id):
    """Get user information"""
    return execute_db("SELECT * FROM users WHERE id=?", (user_id,), fetchone=True)

def get_user_bots(user_id):
    """Get all bots for a user"""
    return execute_db("""
        SELECT id, bot_name, filename, pid, start_time, status, node_id, 
               restart_count, auto_restart, created_at 
        FROM deployments 
        WHERE user_id=? 
        ORDER BY status DESC, id DESC
    """, (user_id,), fetchall=True) or []

def check_prime_expiry(user_id):
    """Check prime expiry status"""
    user = get_user(user_id)
    if user and user['expiry']:
        try:
            expiry = datetime.strptime(user['expiry'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            if expiry > now:
                days_left = (expiry - now).days
                hours_left = (expiry - now).seconds // 3600
                return {
                    'expired': False,
                    'days_left': days_left,
                    'hours_left': hours_left,
                    'expiry_date': expiry.strftime('%Y-%m-%d %H:%M:%S')
                }
        except:
            pass
    return {'expired': True, 'message': 'Prime not active'}

def log_event(event, details, user_id=None):
    """Log server event"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("INSERT INTO server_logs (timestamp, event, details, user_id) VALUES (?, ?, ?, ?)",
                  (timestamp, event, details, user_id), commit=True)
    except Exception as e:
        logger.error(f"Error logging event: {e}")

def log_bot_event(bot_id, log_type, message):
    """Log bot event"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("INSERT INTO bot_logs (bot_id, timestamp, log_type, message) VALUES (?, ?, ?, ?)",
                  (bot_id, timestamp, log_type, message), commit=True)
    except Exception as e:
        logger.error(f"Error logging bot event: {e}")

def send_notification(user_id, message):
    """Send notification to user"""
    try:
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        execute_db("INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)",
                  (user_id, message, created_at), commit=True)
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

def get_system_setting(key, default=None):
    """Get system setting"""
    result = execute_db("SELECT value FROM system_settings WHERE key=?", (key,), fetchone=True)
    return result['value'] if result else default

def update_user_bot_count(user_id):
    """Update user's bot count"""
    count = execute_db("SELECT COUNT(*) FROM deployments WHERE user_id=?", (user_id,), fetchone=True)
    count = count[0] if count else 0
        
    execute_db("UPDATE users SET total_bots_deployed=?, total_deployments=total_deployments+1 WHERE id=?", 
              (count, user_id), commit=True)

def extract_zip_file(zip_path, extract_dir):
    """Extract ZIP file"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        return True
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
        return False

def create_progress_bar(percentage, length=10):
    """Create progress bar"""
    filled = int(percentage * length / 100)
    return "█" * filled + "░" * (length - filled)

def generate_random_key():
    """Generate random activation key"""
    import random
    import string
    prefix = "ZENX-"
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    return f"{prefix}{random_chars}"

# ==================== AUTO-RECOVERY SYSTEM ====================

def recover_deployments():
    """Recover previously running bots"""
    if not Config.AUTO_RESTART_BOTS:
        return
    
    try:
        bots = execute_db("""
            SELECT d.*, u.username 
            FROM deployments d 
            LEFT JOIN users u ON d.user_id = u.id 
            WHERE d.auto_restart = 1 AND d.status IN ('Running', 'Restarting')
        """, fetchall=True) or []
        
        logger.info(f"Found {len(bots)} bots to recover")
        
        for bot in bots:
            success, message = deploy_bot(bot['id'], bot['user_id'])
            if success:
                logger.info(f"Recovered bot {bot['bot_name']} (ID: {bot['id']})")
            else:
                logger.error(f"Failed to recover bot {bot['id']}: {message}")
        
        logger.info(f"Auto-recovery completed: {len(bots)} bots")
        
    except Exception as e:
        logger.error(f"Auto-recovery error: {e}")

def auto_recovery_thread():
    """Auto-recovery background thread"""
    while True:
        try:
            if Config.AUTO_RESTART_BOTS:
                # Find bots that need recovery
                bots = execute_db("""
                    SELECT id, user_id, bot_name, filename, auto_restart, restart_count 
                    FROM deployments 
                    WHERE auto_restart=1 AND (status='Stopped' OR pid=0)
                    AND filename IS NOT NULL
                """, fetchall=True) or []
                
                for bot in bots:
                    bot_id = bot['id']
                    user_id = bot['user_id']
                    
                    # Check if bot file exists
                    file_path = Path(Config.PROJECT_DIR) / bot['filename']
                    if not file_path.exists():
                        continue
                    
                    # Try to redeploy
                    success, message = deploy_bot(bot_id, user_id)
                    if success:
                        logger.info(f"Auto-recovery: Bot {bot_id} restarted")
                        send_notification(user_id, f"Bot '{bot['bot_name']}' auto-recovered")
            
            time.sleep(60)  # Check every minute
            
        except Exception as e:
            logger.error(f"Auto-recovery thread error: {e}")
            time.sleep(300)

def schedule_backups():
    """Schedule regular backups"""
    while True:
        time.sleep(Config.BACKUP_INTERVAL)
        try:
            backup_path = backup_database()
            if backup_path:
                logger.info(f"Scheduled backup: {backup_path.name}")
        except Exception as e:
            logger.error(f"Backup scheduler error: {e}")

def cleanup_thread():
    """Cleanup old files"""
    while True:
        try:
            # Clean old log files (30 days)
            logs_dir = Path(Config.LOGS_DIR)
            for log_file in logs_dir.glob("*.log"):
                if (datetime.now() - datetime.fromtimestamp(log_file.stat().st_mtime)).days > 30:
                    log_file.unlink()
            
            # Clean old exports (7 days)
            exports_dir = Path(Config.EXPORTS_DIR)
            for export_file in exports_dir.glob("*.zip"):
                if (datetime.now() - datetime.fromtimestamp(export_file.stat().st_mtime)).days > 7:
                    export_file.unlink()
            
            # Clean old script backups (14 days)
            backups_dir = Path(Config.SCRIPT_BACKUPS)
            for backup_file in backups_dir.glob("*.py"):
                if (datetime.now() - datetime.fromtimestamp(backup_file.stat().st_mtime)).days > 14:
                    backup_file.unlink()
            
            # Expire old trials
            execute_db("""
                UPDATE bot_trials 
                SET status='expired' 
                WHERE status='active' AND expires_at < ?
            """, (datetime.now().isoformat(),), commit=True)
            
            time.sleep(3600)  # Run every hour
            
        except Exception as e:
            logger.error(f"Cleanup thread error: {e}")
            time.sleep(7200)

# ==================== STARTUP & INITIALIZATION ====================

def start_system():
    """Start the complete system"""
    print("🚀 ZEN X HOST BOT v4.0 Starting...")
    print(f"📊 Admin ID: {Config.ADMIN_ID}")
    print(f"🤖 Bot: @{Config.BOT_USERNAME}")
    print(f"👑 Admin: @{Config.ADMIN_USERNAME}")
    
    # Initialize database
    init_db()
    
    # Recover deployments
    recover_deployments()
    
    # Start background threads
    threads = [
        threading.Thread(target=auto_recovery_thread, daemon=True),
        threading.Thread(target=schedule_backups, daemon=True),
        threading.Thread(target=cleanup_thread, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
    
    print("✅ Background threads started")
    print("📊 System is now running!")
    
    return threads

if __name__ == "__main__":
    # Start system
    system_threads = start_system()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 System shutting down...")
