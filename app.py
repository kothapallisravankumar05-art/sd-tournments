from flask import Flask, render_template, request, redirect, session, make_response, jsonify, send_from_directory
import os, requests, random, string, sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sd_final_secret_2026_rocket")
app.config['PERMANENT_SESSION_LIFETIME']=timedelta(days=3650)

if os.path.isdir("/data"):
    BASE_DIR = "/data"
    DB_FILE = os.path.join(BASE_DIR, "sd.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
else:
    BASE_DIR = "."
    DB_FILE = "sd.db"
    UPLOAD_FOLDER = 'static/uploads'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static', exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

MY_UPI_ID = os.getenv("UPI_ID", "yourname@phonepe")
SITE_URL = "https://sd-tournments.onrender.com"
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("CHAT_ID", "PASTE_YOUR_CHAT_ID_HERE")
ADMIN_USER_ID = 1
ADMIN_PASSWORD = "NANI19"

def send_notify(msg):
    try:
        if "PASTE" in BOT_TOKEN or not BOT_TOKEN: return
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except: pass

class PGWrapper:
    def __init__(self, conn):
        self.conn = conn
        self.last_cur = None
    def execute(self, query, params=()):
        q = query.replace("?", "%s")
        if q.strip().upper().startswith("PRAGMA"):
            class Dummy:
                def fetchone(self): return None
                def fetchall(self): return []
            return Dummy()
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(q, params)
        self.last_cur = cur
        return cur
    def commit(self): self.conn.commit()
    def close(self):
        try:
            if self.last_cur: self.last_cur.close()
        except: pass
        self.conn.close()

def get_db():
    if IS_POSTGRES:
        pg_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return PGWrapper(pg_conn)
    else:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except: pass
        return conn

def add_txn(user_id, amount, type_, desc):
    try:
        c = get_db()
        c.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (user_id, amount, type_, desc, datetime.now().strftime("%d/%m %H:%M")))
        c.commit()
        c.close()
    except: pass

conn = get_db()
conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0, last_bonus TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)")
conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
try:
    conn.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE users ADD COLUMN total_wins INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE users ADD COLUMN last_bonus TEXT")
    conn.execute("ALTER TABLE joined ADD COLUMN slot_no INTEGER DEFAULT 0")
except: pass
conn.commit()
conn.close()

def nocache(view):
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    wrapper.__name__ = view.__name__
    return wrapper

@app.route('/google08d3e829b688619a.html')
def google_verify(): return "google-site-verification: google08d3e829b688619a.html"
@app.route('/manifest.json')
def manifest(): return send_from_directory('static', 'manifest.json')
@app.route('/sw.js')
def service_worker(): return send_from_directory('static', 'sw.js', mimetype='application/javascript')
@app.route('/sitemap.xml')
def sitemap():
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{SITE_URL}/</loc><priority>1.0</priority><lastmod>{date.today()}</lastmod></url>
<url><loc>{SITE_URL}/login</loc><priority>0.9</priority><lastmod>{date.today()}</lastmod></url>
<url><loc>{SITE_URL}/register</loc><priority>0.9</priority><lastmod>{date.today()}</lastmod></url>
<url><loc>{SITE_URL}/matches</loc><priority>0.8</priority><lastmod>{date.today()}</lastmod></url>
<url><loc>{SITE_URL}/leaderboard</loc><priority>0.7</priority><lastmod>{date.today()}</lastmod></url>
</urlset>'''
    return make_response(xml, 200, {'Content-Type': 'application/xml'})
@app.route('/robots.txt')
def robots(): return make_response(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", 200, {'Content-Type': 'text/plain'})
@app.route('/health')
def health(): return "OK", 200

@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids)

@app.route('/matches')
@nocache
def matches_page():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('matches.html', tournaments=t, user=user, my_joined_ids=my_joined_ids)

@app.route('/match/<int:tid>')
@nocache
def match_detail(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    joined_count = conn.execute("SELECT COUNT(*) FROM joined WHERE tournament_id=?", (tid,)).fetchone()[0]
    my = conn.execute("SELECT * FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    conn.close()
    if not t: return "Match not found"
    return render_template('match_detail.html', t=t, user=user, joined_count=joined_count, my_join=my)

@app.route('/slots/<int:tid>')
@nocache
def slots_page(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    taken = conn.execute("SELECT slot_no FROM joined WHERE tournament_id=?", (tid,)).fetchall()
    taken_slots = [r[0] for r in taken]
    conn.close()
    return render_template('slots.html', t=t, taken_slots=taken_slots)

@app.route('/confirm_join/<int:tid>')
@nocache
def confirm_join(tid):
    if 'user_id' not in session: return redirect('/login')
    slot_no = request.args.get('slot_no')
    if not slot_no: return redirect(f'/slots/{tid}')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    taken = conn.execute("SELECT * FROM joined WHERE tournament_id=? AND slot_no=?", (tid, int(slot_no))).fetchone()
    if taken:
        conn.close()
        return f"<h2>Slot {slot_no} Already Taken!</h2><a href='/slots/{tid}'>Back</a>"
    conn.close()
    return render_template('confirm_join.html', t=t, user=user, slot_no=slot_no)

@app.route('/final_join/<int:tid>', methods=['POST'])
def final_join(tid):
    if 'user_id' not in session: return redirect('/login')
    slot_no = request.form.get('slot_no')
    game_name = request.form.get('game_name','').strip()
    if not slot_no: return redirect(f'/slots/{tid}')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    tour = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    ex = conn.execute("SELECT * FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    if ex: conn.close(); return redirect(f'/match/{tid}')
    fee = int(tour['fee'] or 0)
    if user['balance'] < fee: conn.close(); return f"<h2>Balance Low! Need {fee}</h2><a href='/wallet'>Add Money</a>"
    conn.execute("INSERT INTO joined (user_id,tournament_id,slot_no) VALUES (?,?,?)", (session['user_id'], tid, int(slot_no)))
    if game_name and game_name!= user['username']: conn.execute("UPDATE users SET username=? WHERE id=?", (game_name, session['user_id']))
    conn.execute("UPDATE tournaments SET joined = joined + 1 WHERE id=?", (tid,))
    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (fee, session['user_id']))
    conn.commit(); conn.close()
    add_txn(session['user_id'], fee, "DEBIT", f"Joined Tournament #{tid} Slot {slot_no}")
    return redirect(f'/match/{tid}')

@app.route('/join/<int:tid>')
def join(tid): return redirect(f'/slots/{tid}')

@app.route('/leaderboard')
@nocache
def leaderboard():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    top = conn.execute("SELECT id, username, total_wins, balance FROM users ORDER BY total_wins DESC, balance DESC LIMIT 20").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('leaderboard.html', top=top, user=user)

@app.route('/refer/<code>')
def referral_page(code):
    session['ref_code'] = code
    return redirect('/register')

@app.route('/register', methods=['GET','POST'])
@nocache
def register():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        phone = request.form.get('phone','').strip()
        if not username or not password:
            return "<h2>Username & Password required</h2><a href='/register'>Back</a>"
        conn = get_db()
        try:
            ref_code = ''.join(random.choices(string.ascii_uppercase+string.digits, k=5))
            conn.execute("INSERT INTO users (username,password,phone,balance,referral_code) VALUES (?,?,?,0,?)", (username,password,phone,ref_code))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

            if 'ref_code' in session and session['ref_code']:
                ref_user = conn.execute("SELECT id FROM users WHERE referral_code=?", (session['ref_code'],)).fetchone()
                if ref_user and ref_user['id']!= user['id']:
                    conn.execute("UPDATE users SET balance=balance+20 WHERE id=?", (ref_user['id'],))
                    conn.execute("UPDATE users SET balance=balance+20, referred_by=? WHERE id=?", (ref_user['id'], user['id']))
                    conn.commit()
                    try:
                        add_txn(ref_user['id'], 20, "REFERRAL", f"Referral bonus for {username}")
                        add_txn(user['id'], 20, "REFERRAL", "Welcome Referral Bonus ₹20")
                        send_notify(f"🎁 <b>REFERRAL BONUS</b>\n{username} joined via {session['ref_code']}\nBoth got ₹20")
                    except: pass

            session.permanent = True
            session['user_id'] = user['id']
            conn.close()
            try: send_notify(f"👤 <b>NEW USER</b>\n{username}\nPhone: {phone}")
            except: pass
            return redirect('/')
        except Exception as e:
            try: conn.close()
            except: pass
            return f"<h2>Username exists or Error: {e}</h2><a href='/register'>Back</a>"
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
@nocache
def login():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        u = request.form.get('username') or request.form.get('phone') or ""
        p = request.form.get('password') or ""
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u.strip(),p.strip())).fetchone()
        if not user: user = conn.execute("SELECT * FROM users WHERE phone=? AND password=?", (u.strip(),p.strip())).fetchone()
        if user: session.permanent =True;session['user_id']=user['id']; conn.close(); return redirect('/')
        conn.close()
        return "<h3>Wrong Password</h3><a href='/login'>Back</a>"
    return render_template('login.html')

@app.route('/forgot', methods=['GET','POST'])
@nocache
def forgot():
    if request.method == 'POST':
        u = (request.form.get('username') or request.form.get('phone') or "").strip()
        new_pass = (request.form.get('new_password') or "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if not user: user = conn.execute("SELECT * FROM users WHERE phone=?", (u,)).fetchone()
        if not user: conn.close(); return "<h2>User Not Found</h2>"
        conn.execute("UPDATE users SET password=? WHERE id=?", (new_pass, user['id'])); conn.commit(); conn.close()
        return "<h2>Password Reset Done</h2><a href='/login'>Login</a>"
    return render_template('forgot.html')

@app.route('/submit_result', methods=['POST'])
def submit_result():
    if 'user_id' not in session: return redirect('/login')
    mid = request.form.get('match_id'); kills = request.form.get('kills','0')
    conn = get_db()
    ex = conn.execute("SELECT * FROM results WHERE match_id=? AND user_id=?", (mid, session['user_id'])).fetchone()
    if ex: conn.close(); return "<h2>Already Submitted</h2>"
    filename = ""
    if 'screenshot' in request.files:
        f = request.files['screenshot']
        if f.filename:
            filename = secure_filename(f"{mid}_{session['user_id']}_{datetime.now().strftime('%H%M%S')}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn.execute("INSERT INTO results (match_id,user_id,kills,screenshot,status,time) VALUES (?,?,?,?, 'PENDING',?)", (mid, session['user_id'], kills, filename, datetime.now().strftime("%d/%m %H:%M")))
    conn.commit(); conn.close()
    send_notify(f"🏆 <b>RESULT</b>\nUser {session['user_id']}\nMatch {mid}\nKills {kills}")
    return f"<h2>Submitted {kills} Kills</h2><a href='/'>Home</a>"

@app.route('/match_result/<int:mid>')
def match_result(mid):
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments WHERE id=?", (mid,)).fetchone()
    results = conn.execute("SELECT * FROM results WHERE match_id=? AND status='APPROVED' ORDER BY kills DESC", (mid,)).fetchall()
    final=[]
    for r in results:
        u = conn.execute("SELECT username FROM users WHERE id=?", (r['user_id'],)).fetchone()
        prize = (int(t['prize']) if t and t['prize'] else 0) + (int(r['kills'])*int(t['per_kill'] or 0) if t else 0)
        final.append({'player_name': u['username'] if u else f"User {r['user_id']}", 'kills': r['kills'], 'winning': prize})
    conn.close()
    return render_template('match_result.html', t=t, results=final)

@app.route('/wallet', methods=['GET','POST'])
@nocache
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    if request.method == 'POST':
        amount = request.form.get('amount'); utr = request.form.get('utr') or ""; upi_id = request.form.get('upi_id')
        if amount and utr:
            try:
                utr_clean = utr.strip().upper()
                dup_check = conn.execute("SELECT id FROM payments WHERE utr=?", (utr_clean,)).fetchone()
                if not dup_check:
                    conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(amount), utr_clean, datetime.now().strftime("%d/%m %H:%M")))
                    conn.commit()
                    send_notify(f"💰 <b>DEPOSIT</b>\nUser {session['user_id']}\n₹{amount}\nUTR {utr_clean}")
            except: pass
        if amount and upi_id:
            user = conn.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],)).fetchone()
            if user and user['balance'] >= int(amount) and int(amount) >= 200:
                conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(amount), upi_id, datetime.now().strftime("%d/%m %H:%M")))
                conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(amount), session['user_id']))
                conn.commit()
                add_txn(session['user_id'], int(amount), "DEBIT", f"Withdraw to {upi_id}")
                send_notify(f"💸 <b>WITHDRAW</b>\nUser {session['user_id']}\n₹{amount}\nUPI {upi_id}")
        conn.close()
        return redirect('/wallet')
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    payments = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    withdrawals = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    txns = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50", (session['user_id'],)).fetchall()
    conn.close()
    return render_template('wallet.html', user=user, payments=payments, withdrawals=withdrawals, transactions=txns, wallet=user['balance'])

@app.route('/myid')
@nocache
def myid():
    if 'user_id' not in session: return redirect('/login')
    return f"""
    <body style="background:#0a1628;color:#fff;font-family:Arial;text-align:center;padding:40px">
    <h1 style="color:gold">NEE ID = {session['user_id']}</h1>
    <p>Idhi ADMIN_USER_ID lo pettu bro!</p>
    <a href="/admin" style="color:#00ff88">Admin ki vellu</a> | <a href="/" style="color:#fff">Home</a>
    </body>
    """

@app.route('/admin', methods=['GET','POST'])
@nocache
def admin():
    if 'user_id' not in session: return redirect('/login')
    if session['user_id']!= ADMIN_USER_ID:
        return f"""
        <body style="background:#0a1628;color:#fff;font-family:Arial;text-align:center;padding:40px">
        <h2 style="color:#ff4444">⛔ Access Denied!</h2>
        <p>Your ID: {session['user_id']} | Required ID: {ADMIN_USER_ID}</p>
        <p style="color:gold">app.py lo ADMIN_USER_ID = {session['user_id']} ani marchu!</p>
        <a href="/myid" style="color:#00ff88">Check My ID</a> | <a href="/">Home</a>
        </body>
        """

    if session.get('admin_unlocked')!= True:
        if request.method == 'POST' and request.form.get('admin_pass_input'):
            if request.form.get('admin_pass_input') == ADMIN_PASSWORD:
                session['admin_unlocked'] = True
            else:
                return """<body style="background:#0a1628;color:#fff;font-family:Arial;text-align:center;padding:60px"><h2 style="color:#ff4444">❌ Wrong Password NANI19 kaadu!</h2><a href="/admin" style="color:#00ff88">Try Again</a></body>"""
        else:
            return f"""
            <body style="background:#0a1628;color:#fff;font-family:Arial;text-align:center;padding:40px">
            <div style="background:#162435;padding:30px;border-radius:15px;max-width:350px;margin:0 auto;border:1px solid gold">
            <h2 style="color:gold">🔒 ADMIN LOGIN</h2><p style="color:#888;font-size:13px">ID {ADMIN_USER_ID} - Enter Password</p>
            <form method="POST"><input type="password" name="admin_pass_input" placeholder="Password NANI19" style="width:100%;padding:14px;border-radius:10px;border:none;margin:15px 0;box-sizing:border-box" required>
            <button type="submit" style="width:100%;background:gold;color:#000;padding:12px;border:none;border-radius:10px;font-weight:900;cursor:pointer">UNLOCK ADMIN</button></form></div></body>"""

    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action in ['add_tournament','create_match']:
            game = request.form.get('game'); typ = request.form.get('type')
            fee = request.form.get('entry_fee') or request.form.get('fee') or 0
            prize = request.form.get('prize'); total = request.form.get('total_slots') or request.form.get('total') or 10
            tim = request.form.get('time'); per_kill = request.form.get('per_kill') or 0
            conn.execute("INSERT INTO tournaments (game,type,map,time,prize,fee,per_kill,total,status) VALUES (?,?,?,?,?,?,?,?,'UPCOMING')", (game, typ, 'Bermuda', tim, prize, fee, per_kill, total))
        elif action == 'set_room': conn.execute("UPDATE tournaments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (request.form.get('room_id'), request.form.get('room_pass'), request.form.get('mid')))
        elif action == 'delete_tournament':
            tid = request.form.get('tournament_id')
            if tid:
                tour = conn.execute("SELECT fee FROM tournaments WHERE id=?", (tid,)).fetchone()
                if tour:
                    fee_amt = int(tour['fee'] or 0)
                    joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
                    for ju in joined_users:
                        conn.execute("UPDATE users SET balance = balance +? WHERE id=?", (fee_amt, ju['user_id']))
                        add_txn(ju['user_id'], fee_amt, "REFUND", f"Refund - Tournament #{tid} Deleted")
                    conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                    conn.execute("DELETE FROM results WHERE match_id=?", (tid,))
                conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
        elif action == 'cancel_tournament':
            tid = request.form.get('tournament_id')
            if tid:
                tour = conn.execute("SELECT fee FROM tournaments WHERE id=?", (tid,)).fetchone()
                if tour:
                    fee_amt = int(tour['fee'] or 0)
                    joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
                    for ju in joined_users:
                        conn.execute("UPDATE users SET balance = balance +? WHERE id=?", (fee_amt, ju['user_id']))
                        add_txn(ju['user_id'], fee_amt, "REFUND", f"Refund - Tournament #{tid} Cancelled")
                conn.execute("UPDATE tournaments SET status='CANCELLED' WHERE id=?", (tid,))
        elif action == 'approve_payment':
            pid = request.form.get('payment_id') or request.form.get('id')
            if pid:
                p = conn.execute("SELECT user_id,amount,status FROM payments WHERE id=?", (pid,)).fetchone()
                if p and p['status'] == 'PENDING':
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (p['amount'], p['user_id']))
                    conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (pid,))
                    add_txn(p['user_id'], p['amount'], "CREDIT", f"Deposit Approved ₹{p['amount']}")
        elif action == 'reject_payment':
            pid = request.form.get('payment_id') or request.form.get('id')
            if pid: conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (pid,))
        elif action == 'approve_withdrawal': conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (request.form.get('withdrawal_id'),))
        elif action == 'reject_withdrawal':
            w = conn.execute("SELECT user_id,amount FROM withdrawals WHERE id=?", (request.form.get('withdrawal_id'),)).fetchone()
            if w:
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (w['amount'], w['user_id']))
                conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (request.form.get('withdrawal_id'),))
                add_txn(w['user_id'], w['amount'], "REFUND", f"Withdrawal Rejected Refund ₹{w['amount']}")
        elif action == 'approve_result':
            r = conn.execute("SELECT match_id,user_id,kills FROM results WHERE id=?", (request.form.get('result_id'),)).fetchone()
            if r:
                m = conn.execute("SELECT prize,per_kill FROM tournaments WHERE id=?", (r['match_id'],)).fetchone()
                total_win = int(m['prize'] or 0) + (int(r['kills'] or 0)*int(m['per_kill'] or 0))
                conn.execute("UPDATE users SET balance=balance+?, total_wins=total_wins+1 WHERE id=?", (total_win, r['user_id']))
                conn.execute("UPDATE results SET status='APPROVED' WHERE id=?", (request.form.get('result_id'),))
                conn.execute("UPDATE tournaments SET status='COMPLETED', winner_id=? WHERE id=?", (r['user_id'], r['match_id']))
                add_txn(r['user_id'], total_win, "WIN", f"Won Tournament #{r['match_id']} - {r['kills']} kills")
        elif action == 'reject_result': conn.execute("UPDATE results SET status='REJECTED' WHERE id=?", (request.form.get('result_id'),))
        conn.commit()
    try:
        tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
        pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
        pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
        pending_results = conn.execute("SELECT results.*, users.username FROM results LEFT JOIN users ON results.user_id=users.id WHERE results.status='PENDING' ORDER BY results.id DESC").fetchall()
        all_results = conn.execute("SELECT results.*, users.username FROM results LEFT JOIN users ON results.user_id=users.id WHERE results.status!='PENDING' ORDER BY results.id DESC LIMIT 20").fetchall()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_tour = conn.execute("SELECT COUNT(*) FROM tournaments").fetchone()[0]
        total_earning = conn.execute("SELECT SUM(fee * joined) FROM tournaments").fetchone()[0] or 0
        conn.close()
        return render_template('admin.html', matches=tournaments, tournaments=tournaments, pending_payments=pending_payments, pending_withdrawals=pending_withdrawals, pending_results=pending_results, all_results=all_results, total_users=total_users, total_tour=total_tour, total_earning=total_earning)
    except:
        tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
        conn.close()
        html = "<body style='background:#0a1628;color:#fff;font-family:Arial;padding:20px'><h1 style='color:gold'>👑 ADMIN</h1>"
        html += "<div style='background:#162435;padding:20px;border-radius:10px'><h3>Create</h3><form method='POST'><input type='hidden' name='action' value='create_match'><input name='game' placeholder='Game' required style='padding:10px;margin:5px'><input name='type' placeholder='Type' style='padding:10px;margin:5px'><input name='prize' placeholder='Prize' style='padding:10px;margin:5px'><input name='fee' placeholder='Fee' style='padding:10px;margin:5px'><input name='total' placeholder='Slots' style='padding:10px;margin:5px'><button style='background:gold;padding:10px'>CREATE</button></form></div>"
        for t in tournaments: html += f"<div style='background:#1a2a40;padding:10px;margin:5px'>ID {t['id']} - {t['game']} ₹{t['prize']}</div>"
        return html + "</body>"

@app.route('/account')
@nocache
def account():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    played = conn.execute("SELECT COUNT(*) FROM joined WHERE user_id=?", (session['user_id'],)).fetchone()[0]
    conn.close()
    return render_template('account.html', user=user, played=played)

@app.route('/add_money')
@nocache
def add_money():
    if 'user_id' not in session: return redirect('/login')
    return render_template('add_money.html')

@app.route('/get_upi_link')
@nocache
def get_upi():
    if 'user_id' not in session: return jsonify({"ok":False})
    amt = request.args.get('amount','0')
    try: amt = int(float(amt))
    except: return jsonify({"ok":False})
    link = f"upi://pay?pa={MY_UPI_ID}&pn=SD&am={amt}&cu=INR"
    return jsonify({"ok":True, "upi_link": link})

@app.route('/verify_upi', methods=['POST'])
@nocache
def verify():
    if 'user_id' not in session: return jsonify({"ok":False, "msg":"Login Require"})
    data = request.get_json() or {}
    utr = (data.get('utr') or "").strip().upper()
    amt = data.get('amount')
    if len(utr) < 6: return jsonify({"ok":False, "msg":"UTR short - ENTER 12 digit "})
    conn = get_db()
    dup = conn.execute("SELECT id, user_id FROM payments WHERE utr=?", (utr,)).fetchone()
    if dup:
        conn.close()
        if int(dup['user_id']) == session['user_id']:
            return jsonify({"ok":False, "msg":"UTR IS USED - Duplicate!"})
        else:
            return jsonify({"ok":False, "msg":"UTR Is Used Try Again! "})
    try:
        conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(float(amt)), utr, datetime.now().strftime("%d/%m %H:%M")))
        conn.commit()
        send_notify(f"💰 <b>NEW DEPOSIT</b>\nUser {session['user_id']}\n₹{amt}\nUTR {utr}")
    except Exception as e:
        conn.close()
        return jsonify({"ok":False, "msg":f"Error: {e}"})
    conn.close()
    return jsonify({"ok":True, "msg":"UTR Submitted - Wait For Approval!"})

@app.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect('/login'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
