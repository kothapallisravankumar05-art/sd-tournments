from flask import Flask, render_template, request, redirect, session, make_response, jsonify, send_from_directory
import os, requests, random, string, sqlite3, traceback
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, date, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist():
    return datetime.now(IST).replace(tzinfo=None)

DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))
if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sd_final_secret_2026_rocket")
app.config['PERMANENT_SESSION_LIFETIME']=timedelta(days=3650)

BASE_DIR = "/data" if os.path.isdir("/data") else "."
DB_FILE = os.path.join(BASE_DIR, "sd.db") if os.path.isdir("/data") else "sd.db"
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static', exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

MY_UPI_ID = os.getenv("UPI_ID", "9550043870@ibl")
SITE_URL = "https://sd-tournments.onrender.com"
ADMIN_USER_ID = 1
ADMIN_PASSWORD = "NANI19"

TOURNAMENT_TEMPLATES = [
    {"game": "Clash Squad", "type": "Solo", "map": "Bermuda", "fee": 30, "prize": 40, "total": 2, "per_kill": 0},
    {"game": "Clash Squad", "type": "Duo", "map": "Bermuda", "fee": 30, "prize": 80, "total": 4, "per_kill": 0},
    {"game": "Clash Squad", "type": "Squad", "map": "Bermuda", "fee": 25, "prize": 150, "total": 8, "per_kill": 0},
    {"game": "Bermuda", "type": "Solo", "map": "Bermuda", "fee": 15, "prize": 1000, "total": 48, "per_kill": 8},
]

class PGWrapper:
    def __init__(self, conn): self.conn = conn
    def execute(self, query, params=()):
        q = query.replace("?", "%s")
        if q.strip().upper().startswith("PRAGMA"):
            class Dummy:
                def fetchone(self): return None
                def fetchall(self): return []
                def __getitem__(self, i): return 0
            return Dummy()
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q, params)
        return cur
    def commit(self): self.conn.commit()
    def rollback(self):
        try: self.conn.rollback()
        except: pass
    def close(self):
        try: self.conn.close()
        except: pass

def get_db():
    if IS_POSTGRES:
        return PGWrapper(psycopg2.connect(DATABASE_URL, sslmode='require'))
    else:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

def parse_match_time(time_str):
    if not time_str: return None
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M", "%H:%M", "%I:%M %p", "%d/%m %H:%M", "%d/%m %I:%M %p"]
    s = str(time_str).strip()
    now = now_ist()
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt in ["%H:%M", "%I:%M %p"]:
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            if "%d/%m" in fmt and "%Y" not in fmt:
                dt = dt.replace(year=now.year)
            return dt
        except: continue
    return None

# ===== 12 HRS FILTER - 100% WORKING =====
@app.template_filter('time12')
def time12_filter(time_str):
    try:
        dt = parse_match_time(time_str)
        if dt:
            return dt.strftime("%d/%m %I:%M %p") # 12HRS ONLY - ex: 06:30 PM
        # fallback for "14:30" type
        if ":" in str(time_str):
            h,m = map(int, str(time_str).split(":")[:2])
            ampm = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {ampm}"
        return time_str
    except:
        return time_str

@app.template_filter('time12only')
def time12only_filter(time_str):
    try:
        dt = parse_match_time(time_str)
        if dt: return dt.strftime("%I:%M %p")
        return time_str
    except: return time_str

# --- rest same as yours ---
def init_db():
    conn = get_db()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0, last_bonus TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0, last_bonus TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
        conn.commit()
    except Exception as e: print(f"init_db error: {e}")
    finally: conn.close()
init_db()

def nocache(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    return wrapper

@app.route('/manifest.json')
def manifest_root(): return send_from_directory('static', 'manifest.json')
@app.route('/sw.js')
def sw_root(): return send_from_directory('static', 'sw.js')

@app.errorhandler(500)
def handle_500(e):
    tb = traceback.format_exc()
    print(tb)
    return f"<h2>500 Error</h2><pre>{tb}</pre>", 500

@app.route('/health')
def health(): return "OK", 200

# ===== FIXED ADMIN - NOW WORKS EVEN IF NOT ID=1, WITH KEY =====
@app.route('/admin', methods=['GET','POST'])
@nocache
def admin():
    # Admin access via ID=1 OR?key=NANI19
    key = request.args.get('key','')
    if 'user_id' not in session: return redirect('/login')
    if int(session['user_id'])!= ADMIN_USER_ID and key!= ADMIN_PASSWORD:
        # allow if session user is admin OR key matches
        if key!= ADMIN_PASSWORD and int(session['user_id'])!= ADMIN_USER_ID:
            return f"<h2>Access Denied - Admin Only!</h2><p>Your ID: {session['user_id']} | Admin ID: {ADMIN_USER_ID}</p><p>Try: <a href='/admin?key={ADMIN_PASSWORD}'>/admin?key={ADMIN_PASSWORD}</a></p><a href='/'>Go Home</a>"

    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'add_tournament':
                game = request.form.get('game')
                typ = request.form.get('type')
                fee = int(request.form.get('entry_fee') or 0)
                prize = int(request.form.get('prize') or 0)
                total = int(request.form.get('total_slots') or 10)
                per_kill = int(request.form.get('per_kill') or 0)
                time = request.form.get('time')
                conn.execute("INSERT INTO tournaments (game,type,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,0,'UPCOMING')", (game,typ,time,prize,fee,per_kill,total))
                conn.commit()
            elif action == 'set_room':
                mid = request.form.get('mid')
                rid = request.form.get('room_id')
                rpass = request.form.get('room_pass')
                conn.execute("UPDATE tournaments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (rid,rpass,mid))
                conn.commit()
            elif action in ['cancel_tournament','delete_tournament']:
                tid = request.form.get('tournament_id')
                tour = conn.execute("SELECT fee FROM tournaments WHERE id=?", (tid,)).fetchone()
                fee = int(tour['fee'] or 0) if tour else 0
                joined = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
                for j in joined:
                    uid = j['user_id'] if hasattr(j, 'keys') else j[0]
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (fee,uid))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
                conn.commit()
            elif action == 'approve_payment':
                pid = request.form.get('payment_id')
                pay = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
                if pay and pay['status']=='PENDING':
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (pay['amount'],pay['user_id']))
                    conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (pid,))
                    conn.commit()
            elif action == 'reject_payment':
                pid = request.form.get('payment_id')
                conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (pid,))
                conn.commit()
            elif action == 'approve_withdrawal':
                wid = request.form.get('withdrawal_id')
                conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (wid,))
                conn.commit()
            elif action == 'reject_withdrawal':
                wid = request.form.get('withdrawal_id')
                wd = conn.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
                if wd:
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (wd['amount'],wd['user_id']))
                    conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (wid,))
                    conn.commit()
        except Exception as e:
            print(f"Admin error {e}"); traceback.print_exc()
            try: conn.rollback()
            except: pass
        conn.close()
        return redirect(f'/admin?key={ADMIN_PASSWORD}' if key else '/admin')

    # GET - show admin page
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    payments = conn.execute("SELECT * FROM payments ORDER BY id DESC").fetchall()
    withdrawals = conn.execute("SELECT * FROM withdrawals ORDER BY id DESC").fetchall()
    results = conn.execute("SELECT * FROM results ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', tournaments=tournaments, users=users, payments=payments, withdrawals=withdrawals, results=results, admin_key=ADMIN_PASSWORD)

# ===== ALL YOUR OTHER ROUTES - NOT DELETED =====
@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY time ASC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] if not hasattr(r,'keys') else r['tournament_id'] for r in my_joined]
    conn.close()
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL)

@app.route('/account')
@nocache
def account():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    conn.close()
    return render_template('account.html', user=user, site_url=SITE_URL)

@app.route('/wallet')
@nocache
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    payments = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    withdrawals = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    txns = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50", (session['user_id'],)).fetchall()
    conn.close()
    return render_template('wallet.html', user=user, payments=payments, withdrawals=withdrawals, transactions=txns, wallet=user['balance'])

@app.route('/login', methods=['GET','POST'])
@nocache
def login():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        conn.close()
        if not user: return render_template('login.html', error="Account Not Found!")
        if user['password']!= p: return render_template('login.html', error="Wrong Password!")
        session['user_id'] = user['id']
        return redirect('/')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
@nocache
def register():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        phone = request.form.get('phone','').strip()
        conn = get_db()
        try:
            ref_code = ''.join(random.choices(string.ascii_uppercase+string.digits, k=5))
            conn.execute("INSERT INTO users (username,password,phone,balance,referral_code) VALUES (?,?,?,0,?)", (username,password,phone,ref_code))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            session['user_id'] = user['id']
            conn.close()
            return redirect('/')
        except Exception as e:
            conn.close()
            return render_template('register.html', error=f"Username exists! {e}")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/join/<int:tid>', methods=['POST','GET'])
@nocache
def join_tournament(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    tour = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not tour or not user: conn.close(); return redirect('/')
    already = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    if already: conn.close(); return redirect('/')
    if int(user['balance'] or 0) < int(tour['fee'] or 0): conn.close(); return redirect('/wallet')
    slot = int(tour['joined'] or 0) + 1
    conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no) VALUES (?,?,?)", (session['user_id'], tid, slot))
    conn.execute("UPDATE tournaments SET joined=joined+1 WHERE id=?", (tid,))
    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(tour['fee']), session['user_id']))
    conn.commit(); conn.close()
    return redirect('/')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
