"""
ZEN X HOST BOT v4.0 - Flask Web Server
Powerful web interface and API system with auto-recovery
"""

import os
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file, Response, session, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import zipfile
import io

# Configuration
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'zenx-secret-key-2024')
    DB_NAME = 'cyber_v2.db'
    PROJECT_DIR = 'projects'
    BACKUP_DIR = 'backups'
    LOGS_DIR = 'logs'
    EXPORTS_DIR = 'exports'
    SCRIPT_BACKUPS = 'script_backups'
    PORT = int(os.environ.get('PORT', 10000))
    ADMIN_ID = int(os.environ.get('ADMIN_ID', 7832264582))
    ADMIN_USERNAME = 'zerox6t9'
    BOT_USERNAME = 'zen_xbot'
    
    # Payment Methods
    PAYMENT_METHODS = {
        'bkash': {'name': 'bKash', 'number': '01965064030', 'type': 'Personal'},
        'nagad': {'name': 'Nagad', 'number': '01965064030', 'type': 'Personal'},
        'rocket': {'name': 'Rocket', 'number': '❌', 'type': 'Personal'},
        'bank': {'name': 'Bank Transfer', 'details': 'City Bank Ltd.\nAccount: n/a\nBranch: n/a'}
    }

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")

# Database helper
def get_db():
    conn = sqlite3.connect(Config.DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database with new tables
def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Create marketplace tables
    c.execute('''CREATE TABLE IF NOT EXISTS marketplace_bots
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 bot_id INTEGER,
                 title TEXT,
                 description TEXT,
                 price REAL,
                 category TEXT,
                 tags TEXT,
                 seller_id INTEGER,
                 status TEXT DEFAULT 'available',
                 views INTEGER DEFAULT 0,
                 purchases INTEGER DEFAULT 0,
                 created_at TEXT,
                 updated_at TEXT,
                 FOREIGN KEY(bot_id) REFERENCES deployments(id),
                 FOREIGN KEY(seller_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS marketplace_purchases
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 listing_id INTEGER,
                 buyer_id INTEGER,
                 price REAL,
                 status TEXT DEFAULT 'pending',
                 payment_method TEXT,
                 transaction_id TEXT,
                 purchased_at TEXT,
                 completed_at TEXT,
                 FOREIGN KEY(listing_id) REFERENCES marketplace_bots(id),
                 FOREIGN KEY(buyer_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_analytics
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 bot_id INTEGER,
                 date TEXT,
                 uptime_seconds INTEGER,
                 restarts INTEGER,
                 cpu_avg REAL,
                 ram_avg REAL,
                 errors INTEGER,
                 FOREIGN KEY(bot_id) REFERENCES deployments(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_trials
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 bot_id INTEGER,
                 user_id INTEGER,
                 trial_code TEXT,
                 status TEXT DEFAULT 'active',
                 started_at TEXT,
                 expires_at TEXT,
                 FOREIGN KEY(bot_id) REFERENCES deployments(id),
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS payment_logs
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 amount REAL,
                 method TEXT,
                 transaction_id TEXT,
                 status TEXT,
                 purpose TEXT,
                 created_at TEXT)''')
    
    conn.commit()
    conn.close()

# Middleware for admin authentication
@app.before_request
def check_auth():
    if request.endpoint in ['admin_login', 'static', 'api_status', 'index']:
        return
    
    if 'admin_logged_in' not in session and request.endpoint.startswith('admin_'):
        return redirect(url_for('admin_login'))

# Routes
@app.route('/')
def index():
    """Main landing page"""
    return render_template('index.html', 
                         bot_username=Config.BOT_USERNAME,
                         admin_username=Config.ADMIN_USERNAME)

@app.route('/status')
def status():
    """System status API"""
    conn = get_db()
    c = conn.cursor()
    
    # Get system stats
    c.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = c.fetchone()['total_users']
    
    c.execute("SELECT COUNT(*) as total_bots FROM deployments")
    total_bots = c.fetchone()['total_bots']
    
    c.execute("SELECT COUNT(*) as running_bots FROM deployments WHERE status='Running'")
    running_bots = c.fetchone()['running_bots']
    
    c.execute("SELECT COUNT(*) as active_nodes FROM nodes WHERE status='active'")
    active_nodes = c.fetchone()['active_nodes']
    
    conn.close()
    
    return jsonify({
        'status': 'online',
        'version': 'v4.0',
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_users': total_users,
            'total_bots': total_bots,
            'running_bots': running_bots,
            'active_nodes': active_nodes
        }
    })

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Simple admin authentication (in production, use proper auth)
        if username == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            session['admin_id'] = Config.ADMIN_ID
            return redirect(url_for('admin_dashboard'))
        
        return render_template('admin_login.html', error='Invalid credentials')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard"""
    conn = get_db()
    c = conn.cursor()
    
    # Get system statistics
    c.execute("""
        SELECT 
            (SELECT COUNT(*) FROM users) as total_users,
            (SELECT COUNT(*) FROM deployments) as total_bots,
            (SELECT COUNT(*) FROM deployments WHERE status='Running') as running_bots,
            (SELECT COUNT(*) FROM nodes WHERE status='active') as active_nodes,
            (SELECT COUNT(*) FROM marketplace_bots) as marketplace_listings,
            (SELECT COUNT(*) FROM marketplace_purchases WHERE status='pending') as pending_orders,
            (SELECT COUNT(*) FROM bot_trials WHERE status='active') as active_trials
    """)
    
    stats = dict(c.fetchone())
    
    # Recent activities
    c.execute("""
        SELECT * FROM server_logs 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)
    recent_logs = c.fetchall()
    
    # Recent purchases
    c.execute("""
        SELECT mp.*, mb.title, u.username as buyer_username
        FROM marketplace_purchases mp
        JOIN marketplace_bots mb ON mp.listing_id = mb.id
        JOIN users u ON mp.buyer_id = u.id
        ORDER BY mp.purchased_at DESC
        LIMIT 5
    """)
    recent_purchases = c.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html',
                         stats=stats,
                         recent_logs=recent_logs,
                         recent_purchases=recent_purchases,
                         payment_methods=Config.PAYMENT_METHODS)

@app.route('/admin/bots')
def admin_bots():
    """Admin bot management"""
    conn = get_db()
    c = conn.cursor()
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    # Get all bots with user info
    c.execute("""
        SELECT d.*, u.username, u.id as user_id, 
               n.name as node_name, n.region
        FROM deployments d
        LEFT JOIN users u ON d.user_id = u.id
        LEFT JOIN nodes n ON d.node_id = n.id
        ORDER BY d.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    
    bots = c.fetchall()
    
    # Count total bots
    c.execute("SELECT COUNT(*) as total FROM deployments")
    total = c.fetchone()['total']
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin_bots.html',
                         bots=bots,
                         page=page,
                         total_pages=total_pages,
                         total=total)

@app.route('/admin/bot/<int:bot_id>')
def admin_bot_detail(bot_id):
    """Admin bot detail page"""
    conn = get_db()
    c = conn.cursor()
    
    # Get bot details
    c.execute("""
        SELECT d.*, u.username, u.id as user_id,
               n.name as node_name, n.region, n.capacity
        FROM deployments d
        LEFT JOIN users u ON d.user_id = u.id
        LEFT JOIN nodes n ON d.node_id = n.id
        WHERE d.id = ?
    """, (bot_id,))
    
    bot = c.fetchone()
    
    if not bot:
        return "Bot not found", 404
    
    # Get bot analytics
    c.execute("""
        SELECT * FROM bot_analytics 
        WHERE bot_id = ? 
        ORDER BY date DESC 
        LIMIT 7
    """, (bot_id,))
    analytics = c.fetchall()
    
    # Get bot logs
    log_file = Path(Config.LOGS_DIR) / f"bot_{bot_id}.log"
    logs = ""
    if log_file.exists():
        with open(log_file, 'r') as f:
            logs = f.read()[-5000:]  # Last 5000 chars
    
    # Get bot trials
    c.execute("""
        SELECT bt.*, u.username
        FROM bot_trials bt
        LEFT JOIN users u ON bt.user_id = u.id
        WHERE bt.bot_id = ?
        ORDER BY bt.started_at DESC
    """, (bot_id,))
    trials = c.fetchall()
    
    conn.close()
    
    return render_template('admin_bot_detail.html',
                         bot=bot,
                         analytics=analytics,
                         logs=logs,
                         trials=trials,
                         payment_methods=Config.PAYMENT_METHODS)

@app.route('/admin/bot/<int:bot_id>/backup')
def admin_bot_backup(bot_id):
    """Download bot script backup"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT filename FROM deployments WHERE id = ?", (bot_id,))
    bot = c.fetchone()
    
    if not bot:
        return "Bot not found", 404
    
    file_path = Path(Config.PROJECT_DIR) / bot['filename']
    
    if not file_path.exists():
        return "Bot file not found", 404
    
    # Create backup directory
    backup_dir = Path(Config.SCRIPT_BACKUPS)
    backup_dir.mkdir(exist_ok=True)
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"bot_{bot_id}_{timestamp}.py"
    backup_path = backup_dir / backup_filename
    
    # Copy file
    import shutil
    shutil.copy2(file_path, backup_path)
    
    return send_file(backup_path, as_attachment=True)

@app.route('/admin/bot/<int:bot_id>/test')
def admin_bot_test(bot_id):
    """Test run bot"""
    from bot import test_run_bot
    
    success, message = test_run_bot(bot_id)
    
    return jsonify({
        'success': success,
        'message': message
    })

@app.route('/admin/bot/<int:bot_id>/analytics')
def admin_bot_analytics(bot_id):
    """Get bot analytics data"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM bot_analytics 
        WHERE bot_id = ? 
        ORDER BY date ASC
    """, (bot_id,))
    
    analytics = c.fetchall()
    
    conn.close()
    
    # Format for chart
    dates = [a['date'] for a in analytics]
    uptime = [a['uptime_seconds'] / 3600 for a in analytics]  # Convert to hours
    cpu = [a['cpu_avg'] for a in analytics]
    ram = [a['ram_avg'] for a in analytics]
    
    return jsonify({
        'dates': dates,
        'uptime': uptime,
        'cpu': cpu,
        'ram': ram
    })

@app.route('/admin/marketplace')
def admin_marketplace():
    """Admin marketplace management"""
    conn = get_db()
    c = conn.cursor()
    
    # Get all marketplace listings
    c.execute("""
        SELECT mb.*, d.bot_name, u.username as seller_username,
               COUNT(mp.id) as total_purchases
        FROM marketplace_bots mb
        JOIN deployments d ON mb.bot_id = d.id
        JOIN users u ON mb.seller_id = u.id
        LEFT JOIN marketplace_purchases mp ON mb.id = mp.listing_id
        GROUP BY mb.id
        ORDER BY mb.created_at DESC
    """)
    
    listings = c.fetchall()
    
    # Get recent purchases
    c.execute("""
        SELECT mp.*, mb.title, u.username as buyer_username
        FROM marketplace_purchases mp
        JOIN marketplace_bots mb ON mp.listing_id = mb.id
        JOIN users u ON mp.buyer_id = u.id
        ORDER BY mp.purchased_at DESC
        LIMIT 20
    """)
    
    purchases = c.fetchall()
    
    conn.close()
    
    return render_template('admin_marketplace.html',
                         listings=listings,
                         purchases=purchases)

@app.route('/admin/marketplace/create', methods=['POST'])
def admin_create_listing():
    """Create marketplace listing"""
    data = request.json
    
    conn = get_db()
    c = conn.cursor()
    
    # Validate bot exists and belongs to admin
    c.execute("SELECT id, user_id FROM deployments WHERE id = ?", (data['bot_id'],))
    bot = c.fetchone()
    
    if not bot or bot['user_id'] != Config.ADMIN_ID:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid bot ID'})
    
    # Check if already listed
    c.execute("SELECT id FROM marketplace_bots WHERE bot_id = ? AND status = 'available'", (data['bot_id'],))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return jsonify({'success': False, 'message': 'Bot already listed'})
    
    # Create listing
    created_at = datetime.now().isoformat()
    c.execute("""
        INSERT INTO marketplace_bots 
        (bot_id, title, description, price, category, tags, seller_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['bot_id'],
        data['title'],
        data['description'],
        data['price'],
        data.get('category', 'general'),
        ','.join(data.get('tags', [])),
        Config.ADMIN_ID,
        created_at,
        created_at
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Listing created successfully'})

@app.route('/admin/marketplace/<int:listing_id>/update', methods=['POST'])
def admin_update_listing(listing_id):
    """Update marketplace listing"""
    data = request.json
    
    conn = get_db()
    c = conn.cursor()
    
    updated_at = datetime.now().isoformat()
    c.execute("""
        UPDATE marketplace_bots 
        SET title = ?, description = ?, price = ?, category = ?, tags = ?, updated_at = ?
        WHERE id = ?
    """, (
        data['title'],
        data['description'],
        data['price'],
        data.get('category', 'general'),
        ','.join(data.get('tags', [])),
        updated_at,
        listing_id
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Listing updated successfully'})

@app.route('/admin/marketplace/<int:listing_id>/delete')
def admin_delete_listing(listing_id):
    """Delete marketplace listing"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("DELETE FROM marketplace_bots WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Listing deleted successfully'})

@app.route('/admin/orders')
def admin_orders():
    """Admin order management"""
    conn = get_db()
    c = conn.cursor()
    
    status_filter = request.args.get('status', 'all')
    
    query = """
        SELECT mp.*, mb.title, u.username as buyer_username,
               s.username as seller_username
        FROM marketplace_purchases mp
        JOIN marketplace_bots mb ON mp.listing_id = mb.id
        JOIN users u ON mp.buyer_id = u.id
        JOIN users s ON mb.seller_id = s.id
    """
    
    if status_filter != 'all':
        query += f" WHERE mp.status = '{status_filter}'"
    
    query += " ORDER BY mp.purchased_at DESC"
    
    c.execute(query)
    orders = c.fetchall()
    
    conn.close()
    
    return render_template('admin_orders.html',
                         orders=orders,
                         status_filter=status_filter)

@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
def admin_update_order(order_id):
    """Update order status"""
    data = request.json
    new_status = data.get('status')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("UPDATE marketplace_purchases SET status = ? WHERE id = ?", (new_status, order_id))
    
    if new_status == 'completed':
        completed_at = datetime.now().isoformat()
        c.execute("UPDATE marketplace_purchases SET completed_at = ? WHERE id = ?", (completed_at, order_id))
        
        # Get order details
        c.execute("""
            SELECT mp.listing_id, mp.buyer_id, mb.bot_id
            FROM marketplace_purchases mp
            JOIN marketplace_bots mb ON mp.listing_id = mb.id
            WHERE mp.id = ?
        """, (order_id,))
        
        order = c.fetchone()
        
        if order:
            # Grant bot access to buyer
            # This would need to be implemented based on your system
            pass
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Order marked as {new_status}'})

@app.route('/admin/trials')
def admin_trials():
    """Admin bot trial management"""
    conn = get_db()
    c = conn.cursor()
    
    # Get active trials
    c.execute("""
        SELECT bt.*, d.bot_name, u.username, 
               u2.username as created_by_username
        FROM bot_trials bt
        JOIN deployments d ON bt.bot_id = d.id
        JOIN users u ON bt.user_id = u.id
        LEFT JOIN users u2 ON d.user_id = u2.id
        ORDER BY bt.started_at DESC
    """)
    
    trials = c.fetchall()
    
    # Get bot options for creating trials
    c.execute("""
        SELECT d.id, d.bot_name, u.username
        FROM deployments d
        JOIN users u ON d.user_id = u.id
        WHERE d.user_id = ?
        ORDER BY d.bot_name
    """, (Config.ADMIN_ID,))
    
    admin_bots = c.fetchall()
    
    conn.close()
    
    return render_template('admin_trials.html',
                         trials=trials,
                         admin_bots=admin_bots)

@app.route('/admin/trial/create', methods=['POST'])
def admin_create_trial():
    """Create bot trial"""
    data = request.json
    
    conn = get_db()
    c = conn.cursor()
    
    # Validate bot exists and belongs to admin
    c.execute("SELECT id FROM deployments WHERE id = ? AND user_id = ?", 
              (data['bot_id'], Config.ADMIN_ID))
    
    bot = c.fetchone()
    
    if not bot:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid bot ID'})
    
    # Generate trial code
    import random
    import string
    trial_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    # Set trial duration (default 24 hours)
    hours = int(data.get('hours', 24))
    
    started_at = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(hours=hours)).isoformat()
    
    c.execute("""
        INSERT INTO bot_trials 
        (bot_id, user_id, trial_code, status, started_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data['bot_id'],
        data.get('user_id', 0),  # 0 means any user can use with code
        trial_code,
        'active',
        started_at,
        expires_at
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True, 
        'message': 'Trial created successfully',
        'trial_code': trial_code
    })

@app.route('/admin/payments')
def admin_payments():
    """Admin payment management"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT pl.*, u.username
        FROM payment_logs pl
        LEFT JOIN users u ON pl.user_id = u.id
        ORDER BY pl.created_at DESC
        LIMIT 100
    """)
    
    payments = c.fetchall()
    
    # Payment statistics
    c.execute("""
        SELECT 
            COUNT(*) as total_payments,
            SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_revenue,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_payments
        FROM payment_logs
    """)
    
    stats = dict(c.fetchone())
    
    conn.close()
    
    return render_template('admin_payments.html',
                         payments=payments,
                         stats=stats,
                         payment_methods=Config.PAYMENT_METHODS)

@app.route('/admin/settings')
def admin_settings():
    """Admin system settings"""
    conn = get_db()
    c = conn.cursor()
    
    # Get system settings from database
    c.execute("SELECT * FROM system_settings")
    settings = {row['key']: row['value'] for row in c.fetchall()}
    
    conn.close()
    
    return render_template('admin_settings.html',
                         settings=settings,
                         payment_methods=Config.PAYMENT_METHODS)

@app.route('/admin/settings/update', methods=['POST'])
def admin_update_settings():
    """Update system settings"""
    data = request.json
    
    conn = get_db()
    c = conn.cursor()
    
    for key, value in data.items():
        c.execute("""
            INSERT OR REPLACE INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Settings updated successfully'})

@app.route('/admin/nodes')
def admin_nodes():
    """Admin node management"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM nodes ORDER BY id")
    nodes = c.fetchall()
    
    # Node statistics
    c.execute("""
        SELECT 
            COUNT(*) as total_nodes,
            SUM(capacity) as total_capacity,
            SUM(current_load) as current_load,
            COUNT(CASE WHEN status = 'active' THEN 1 END) as active_nodes
        FROM nodes
    """)
    
    stats = dict(c.fetchone())
    
    conn.close()
    
    return render_template('admin_nodes.html',
                         nodes=nodes,
                         stats=stats)

@app.route('/admin/users')
def admin_users():
    """Admin user management"""
    conn = get_db()
    c = conn.cursor()
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    c.execute("""
        SELECT u.*, 
               COUNT(d.id) as bot_count,
               COUNT(CASE WHEN d.status = 'Running' THEN 1 END) as running_bots
        FROM users u
        LEFT JOIN deployments d ON u.id = d.user_id
        GROUP BY u.id
        ORDER BY u.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    
    users = c.fetchall()
    
    c.execute("SELECT COUNT(*) as total FROM users")
    total = c.fetchone()['total']
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin_users.html',
                         users=users,
                         page=page,
                         total_pages=total_pages,
                         total=total)

@app.route('/admin/analytics')
def admin_analytics():
    """Admin analytics dashboard"""
    conn = get_db()
    c = conn.cursor()
    
    # Daily user registrations (last 30 days)
    c.execute("""
        SELECT DATE(join_date) as date, COUNT(*) as count
        FROM users
        WHERE join_date >= date('now', '-30 days')
        GROUP BY DATE(join_date)
        ORDER BY date
    """)
    
    user_registrations = c.fetchall()
    
    # Daily bot deployments (last 30 days)
    c.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM deployments
        WHERE created_at >= date('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    
    bot_deployments = c.fetchall()
    
    # Revenue by month
    c.execute("""
        SELECT strftime('%Y-%m', created_at) as month, 
               SUM(amount) as revenue
        FROM payment_logs
        WHERE status = 'completed'
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month
        LIMIT 12
    """)
    
    monthly_revenue = c.fetchall()
    
    # Top selling bots
    c.execute("""
        SELECT mb.title, COUNT(mp.id) as sales, SUM(mp.price) as revenue
        FROM marketplace_purchases mp
        JOIN marketplace_bots mb ON mp.listing_id = mb.id
        WHERE mp.status = 'completed'
        GROUP BY mb.id
        ORDER BY sales DESC
        LIMIT 10
    """)
    
    top_bots = c.fetchall()
    
    conn.close()
    
    return render_template('admin_analytics.html',
                         user_registrations=user_registrations,
                         bot_deployments=bot_deployments,
                         monthly_revenue=monthly_revenue,
                         top_bots=top_bots)

# API Endpoints
@app.route('/api/marketplace')
def api_marketplace():
    """API for marketplace listings"""
    conn = get_db()
    c = conn.cursor()
    
    category = request.args.get('category', 'all')
    sort = request.args.get('sort', 'newest')
    
    query = """
        SELECT mb.*, d.bot_name, u.username as seller_username,
               d.filename, d.status as bot_status
        FROM marketplace_bots mb
        JOIN deployments d ON mb.bot_id = d.id
        JOIN users u ON mb.seller_id = u.id
        WHERE mb.status = 'available'
    """
    
    if category != 'all':
        query += f" AND mb.category = '{category}'"
    
    if sort == 'price_low':
        query += " ORDER BY mb.price ASC"
    elif sort == 'price_high':
        query += " ORDER BY mb.price DESC"
    elif sort == 'popular':
        query += " ORDER BY mb.purchases DESC"
    else:  # newest
        query += " ORDER BY mb.created_at DESC"
    
    c.execute(query)
    listings = c.fetchall()
    
    conn.close()
    
    return jsonify([dict(row) for row in listings])

@app.route('/api/bot/<int:bot_id>/details')
def api_bot_details(bot_id):
    """API for bot details"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT d.*, u.username, n.name as node_name, n.region
        FROM deployments d
        LEFT JOIN users u ON d.user_id = u.id
        LEFT JOIN nodes n ON d.node_id = n.id
        WHERE d.id = ?
    """, (bot_id,))
    
    bot = c.fetchone()
    
    if not bot:
        return jsonify({'error': 'Bot not found'}), 404
    
    conn.close()
    
    return jsonify(dict(bot))

@app.route('/api/purchase', methods=['POST'])
def api_purchase():
    """API for purchasing bots"""
    data = request.json
    
    # Validate data
    required_fields = ['listing_id', 'buyer_id', 'payment_method', 'transaction_id']
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check listing exists and is available
    c.execute("SELECT * FROM marketplace_bots WHERE id = ? AND status = 'available'", 
              (data['listing_id'],))
    
    listing = c.fetchone()
    
    if not listing:
        conn.close()
        return jsonify({'success': False, 'message': 'Listing not available'})
    
    # Create purchase record
    purchased_at = datetime.now().isoformat()
    
    c.execute("""
        INSERT INTO marketplace_purchases 
        (listing_id, buyer_id, price, status, payment_method, transaction_id, purchased_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data['listing_id'],
        data['buyer_id'],
        listing['price'],
        'pending',
        data['payment_method'],
        data['transaction_id'],
        purchased_at
    ))
    
    purchase_id = c.lastrowid
    
    # Log payment
    c.execute("""
        INSERT INTO payment_logs 
        (user_id, amount, method, transaction_id, status, purpose, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data['buyer_id'],
        listing['price'],
        data['payment_method'],
        data['transaction_id'],
        'pending',
        f'Bot purchase: {listing["title"]}',
        purchased_at
    ))
    
    # Update listing views/purchases
    c.execute("UPDATE marketplace_bots SET purchases = purchases + 1 WHERE id = ?", 
              (data['listing_id'],))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Purchase recorded successfully',
        'purchase_id': purchase_id
    })

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    emit('connected', {'message': 'Connected to ZEN X Hosting'})

@socketio.on('bot_status_update')
def handle_bot_status_update(data):
    """Handle bot status updates"""
    # Broadcast to all clients
    emit('bot_status_changed', data, broadcast=True)

@socketio.on('system_stats_update')
def handle_system_stats_update():
    """Send system stats update"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            (SELECT COUNT(*) FROM deployments WHERE status='Running') as running_bots,
            (SELECT COUNT(*) FROM users) as total_users,
            (SELECT COUNT(*) FROM nodes WHERE status='active') as active_nodes
    """)
    
    stats = dict(c.fetchone())
    conn.close()
    
    emit('system_stats', stats)

if __name__ == '__main__':
    # Create necessary directories
    Path('templates').mkdir(exist_ok=True)
    Path('static').mkdir(exist_ok=True)
    Path(Config.SCRIPT_BACKUPS).mkdir(exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Create default templates if they don't exist
    create_default_templates()
    
    print(f"🚀 ZEN X Hosting Web Server starting on port {Config.PORT}")
    socketio.run(app, host='0.0.0.0', port=Config.PORT, debug=True)

def create_default_templates():
    """Create default HTML templates"""
    templates_dir = Path('templates')
    
    # Create index.html
    index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZEN X Bot Hosting v4.0</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            max-width: 1200px;
            width: 90%;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        h1 {
            font-size: 3.5rem;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #00dbde, #fc00ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }
        
        .tagline {
            font-size: 1.2rem;
            opacity: 0.9;
            margin-bottom: 20px;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }
        
        .feature-card {
            background: rgba(255, 255, 255, 0.1);
            padding: 25px;
            border-radius: 15px;
            transition: transform 0.3s, background 0.3s;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .feature-card:hover {
            transform: translateY(-5px);
            background: rgba(255, 255, 255, 0.15);
        }
        
        .feature-icon {
            font-size: 2.5rem;
            margin-bottom: 15px;
            color: #00dbde;
        }
        
        .feature-title {
            font-size: 1.3rem;
            margin-bottom: 10px;
            color: #fff;
        }
        
        .feature-desc {
            font-size: 0.95rem;
            opacity: 0.8;
            line-height: 1.5;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .stat-card {
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .stat-number {
            font-size: 2.5rem;
            font-weight: bold;
            color: #00dbde;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 0.9rem;
            opacity: 0.8;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .cta-section {
            text-align: center;
            padding: 40px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 15px;
            margin-bottom: 30px;
        }
        
        .cta-title {
            font-size: 2rem;
            margin-bottom: 20px;
            color: #fff;
        }
        
        .cta-button {
            display: inline-block;
            padding: 15px 40px;
            background: linear-gradient(45deg, #00dbde, #fc00ff);
            color: white;
            text-decoration: none;
            border-radius: 50px;
            font-size: 1.1rem;
            font-weight: bold;
            transition: transform 0.3s, box-shadow 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .cta-button:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.3);
        }
        
        .links {
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .link-button {
            padding: 12px 30px;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            text-decoration: none;
            border-radius: 10px;
            transition: background 0.3s;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .link-button:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        
        .footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 0.9rem;
            opacity: 0.7;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
            }
            
            h1 {
                font-size: 2.5rem;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
            
            .stats {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 ZEN X HOST BOT v4.0</h1>
            <p class="tagline">Ultimate Bot Hosting Solution with Auto-Recovery & Marketplace</p>
        </div>
        
        <div class="features">
            <div class="feature-card">
                <div class="feature-icon">🚀</div>
                <h3 class="feature-title">Auto-Recovery System</h3>
                <p class="feature-desc">Automatic bot recovery on crashes, server restarts, and failures with intelligent monitoring.</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">🛒</div>
                <h3 class="feature-title">Bot Marketplace</h3>
                <p class="feature-desc">Buy and sell Telegram bots with secure payment system and trial options.</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <h3 class="feature-title">Advanced Analytics</h3>
                <p class="feature-desc">Real-time bot performance tracking, uptime monitoring, and detailed statistics.</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">🔒</div>
                <h3 class="feature-title">Secure Hosting</h3>
                <p class="feature-desc">300-capacity nodes with multi-region support and encrypted backups.</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">💳</div>
                <h3 class="feature-title">Payment Integration</h3>
                <p class="feature-desc">Multiple payment methods: bKash, Nagad, Rocket, and Bank Transfer.</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <h3 class="feature-title">Ultra Fast</h3>
                <p class="feature-desc">Optimized for high performance with 99.9% uptime guarantee and low latency.</p>
            </div>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number" id="total-bots">0</div>
                <div class="stat-label">Active Bots</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-number" id="total-users">0</div>
                <div class="stat-label">Total Users</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-number" id="uptime">99.9%</div>
                <div class="stat-label">System Uptime</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-number" id="nodes">3</div>
                <div class="stat-label">Hosting Nodes</div>
            </div>
        </div>
        
        <div class="cta-section">
            <h2 class="cta-title">Start Hosting Your Bots Today!</h2>
            <p style="margin-bottom: 25px; opacity: 0.9;">Join thousands of developers who trust ZEN X for their bot hosting needs.</p>
            <a href="https://t.me/{{ bot_username }}" class="cta-button" target="_blank">
                🚀 Launch Telegram Bot
            </a>
        </div>
        
        <div class="links">
            <a href="/admin/login" class="link-button">👑 Admin Panel</a>
            <a href="/status" class="link-button">📊 System Status</a>
            <a href="https://t.me/{{ admin_username }}" class="link-button">📞 Contact Admin</a>
            <a href="/api/marketplace" class="link-button">🛒 Browse Marketplace</a>
        </div>
        
        <div class="footer">
            <p>© 2024 ZEN X Host Bot v4.0 | Powered by 300-Capacity Multi-Node Hosting</p>
            <p style="margin-top: 10px;">Contact: @{{ admin_username }} | Bot: @{{ bot_username }}</p>
        </div>
    </div>
    
    <script>
        // Fetch live stats
        async function updateStats() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                document.getElementById('total-bots').textContent = data.stats.running_bots;
                document.getElementById('total-users').textContent = data.stats.total_users;
            } catch (error) {
                console.log('Error fetching stats:', error);
            }
        }
        
        // Update stats on load
        updateStats();
        
        // Update every 30 seconds
        setInterval(updateStats, 30000);
    </script>
</body>
</html>
    """
    
    (templates_dir / 'index.html').write_text(index_html)
    
    # Create admin login template
    login_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - ZEN X Hosting</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-container {
            width: 100%;
            max-width: 400px;
            padding: 20px;
        }
        
        .login-box {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo h1 {
            color: white;
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .logo p {
            color: rgba(255, 255, 255, 0.8);
            font-size: 0.9rem;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            color: rgba(255, 255, 255, 0.9);
            margin-bottom: 8px;
            font-size: 0.9rem;
        }
        
        .form-control {
            width: 100%;
            padding: 15px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            color: white;
            font-size: 1rem;
            transition: border-color 0.3s;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #00dbde;
        }
        
        .btn-login {
            width: 100%;
            padding: 15px;
            background: linear-gradient(45deg, #00dbde, #fc00ff);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.3s, box-shadow 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }
        
        .btn-login:active {
            transform: translateY(0);
        }
        
        .error-message {
            background: rgba(255, 0, 0, 0.1);
            border: 1px solid rgba(255, 0, 0, 0.3);
            color: #ff6b6b;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 0.9rem;
        }
        
        .forgot-password {
            text-align: center;
            margin-top: 20px;
        }
        
        .forgot-password a {
            color: rgba(255, 255, 255, 0.7);
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.3s;
        }
        
        .forgot-password a:hover {
            color: #00dbde;
        }
        
        .version {
            text-align: center;
            margin-top: 30px;
            color: rgba(255, 255, 255, 0.5);
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-box">
            <div class="logo">
                <h1>🤖 ZEN X</h1>
                <p>v4.0 Admin Panel</p>
            </div>
            
            {% if error %}
            <div class="error-message">
                {{ error }}
            </div>
            {% endif %}
            
            <form method="POST" action="">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" class="form-control" required 
                           placeholder="Enter admin username">
                </div>
                
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" class="form-control" required 
                           placeholder="Enter password">
                </div>
                
                <button type="submit" class="btn-login">
                    🔐 Login to Dashboard
                </button>
            </form>
            
            <div class="forgot-password">
                <a href="https://t.me/{{ admin_username }}">Contact Super Admin</a>
            </div>
            
            <div class="version">
                ZEN X Host Bot v4.0 | © 2024
            </div>
        </div>
    </div>
</body>
</html>
    """
    
    (templates_dir / 'admin_login.html').write_text(login_html)
    
    # Create other templates would follow similar pattern...
    # For brevity, I'll show one more example
    
    dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - ZEN X Hosting</title>
    <style>
        /* Admin dashboard styles would go here */
        /* This is a simplified version for example */
    </style>
</head>
<body>
    <h1>Admin Dashboard</h1>
    <!-- Full dashboard implementation would be here -->
</body>
</html>
    """
    
    (templates_dir / 'admin_dashboard.html').write_text(dashboard_html)
    
    print("✅ Default templates created successfully")
