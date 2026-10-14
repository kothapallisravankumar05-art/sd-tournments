from flask import Flask, render_template, request, redirect, session, make_response, jsonify, send_from_directory
import os, requests, random, string, sqlite3, traceback
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
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

MY_UPI_ID = os.getenv("UPI_ID", "9550043870@ibl")
SITE_URL = "https://sd-tourmments.onrender.com"
ADMIN_USER_ID = 1
ADMIN_PASSWORD = "NANI19"

class PGWrapper:
    def __init__(self, conn):
        self.conn = conn
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
        try: conn.execute("PRAGMA journal_mode=WAL;")
        except: pass
        return conn

def add_txn(user_id, amount, type_, desc):
    try:
        c = get_db()
        c.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (user_id, amount, type_, desc, datetime.now().strftime("%d/%m %H:%M")))
        c.commit()
        c.close()
    except Exception as e:
        print(f"add_txn error {e}")

# --- AUTO EXPIRY SYSTEM ---
def parse_match_time(time_str):
    if not time_str: return None
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M", "%H:%M", "%I:%M %p", "%d/%m %H:%M"]
    now = datetime.now()
    for fmt in formats:
        try:
            dt = datetime.strptime(str(time_str).strip(), fmt)
            if fmt in ["%H:%M", "%I:%M %p"]:
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except: continue
    return None

def auto_expire_matches():
    """Only UPCOMING matches auto refund after 2 hours"""
    try:
        conn = get_db()
        tournaments = conn.execute("SELECT id, time, fee, status FROM tournaments WHERE status='UPCOMING'").fetchall()
        now = datetime.now()
        expired = []
        for t in tournaments:
            t_time = parse_match_time(t['time'])
            if t_time and now > (t_time + timedelta(hours=2)):
                expired.append((t['id'], int(t['fee'] or 0)))
        for tid, fee in expired:
            try:
                joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
                for ju in joined_users:
                    uid = ju['user_id'] if hasattr(ju, 'keys') and 'user_id' in ju.keys() else ju[0]
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (fee, uid))
                    conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)",
                                 (uid, fee, "REFUND", f"Match #{tid} Expired - Auto Refund Rs {fee}", datetime.now().strftime("%d/%m %H:%M")))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                conn.execute("DELETE FROM results WHERE match_id=?", (tid,))
                conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
                conn.commit()
                print(f"⏰ Auto Expired UPCOMING Match {tid} - Refunded {len(joined_users)} users")
            except Exception as e:
                print(f"Auto expire error {tid}: {e}")
                try: conn.rollback()
                except: pass
        conn.close()
    except Exception as e:
        print(f"auto_expire_matches error: {e}")

def init_db():
    conn = get_db()
    try:
        if IS_POSTGRES:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0, last_bonus TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.commit()
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0, last_bonus TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.commit()
        print("✅ ALL TABLES READY - BUSINESSMAN FINAL")
    except Exception as e:
        print(f"❌ init_db error: {e}")
        traceback.print_exc()
        try: conn.rollback()
        except: pass
    finally:
        conn.close()

init_db()

def nocache(view):
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    wrapper.__name__ = view.__name__
    return wrapper

@app.errorhandler(500)
def handle_500(e):
    tb = traceback.format_exc()
    print(tb)
    return f"<h2>500 Error</h2><pre>{tb}</pre>", 500

@app.route('/health')
def health(): return "OK", 200

@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    try: auto_expire_matches()
    except: pass
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids)

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

@app.route('/register', methods=['GET','POST'])
@nocache
def register():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        phone = request.form.get('phone','').strip()
        if not username or not password:
            return render_template('register.html', error="Username & Password required!")
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
            session.permanent = True
            session['user_id'] = user['id']
            conn.close()
            return redirect('/')
        except Exception as e:
            try: conn.close()
            except: pass
            return render_template('register.html', error=f"Username exists bro! {e}")
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
@nocache
def login():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        u = (request.form.get('username') or request.form.get('phone') or "").strip()
        p = (request.form.get('password') or "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if not user: user = conn.execute("SELECT * FROM users WHERE phone=?", (u,)).fetchone()
        if not user: conn.close(); return render_template('login.html', error="Account Not Found!")
        if user['password']!= p:
            try:
                if not check_password_hash(user['password'], p):
                    conn.close(); return render_template('login.html', error="Wrong Password!")
            except: pass
        session.permanent = True
        session['user_id'] = user['id']
        conn.close()
        return redirect('/')
    return render_template('login.html')

@app.route('/wallet', methods=['GET','POST'])
@nocache
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    if request.method == 'POST':
        utr = request.form.get('utr')
        upi_id = request.form.get('upi_id') or request.form.get('upi')
        amount = request.form.get('amount')
        try:
            if utr and amount:
                dup = conn.execute("SELECT id FROM payments WHERE utr=?", (utr.strip().upper(),)).fetchone()
                if not dup:
                    amt_i = int(float(amount))
                    conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], amt_i, utr.strip().upper(), datetime.now().strftime("%d/%m %H:%M")))
                    conn.commit()
                    add_txn(session['user_id'], amt_i, "CREDIT", f"Deposit Request {amt_i} - {utr}")
            elif upi_id and amount:
                amt = int(float(amount))
                user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
                if user and int(user['balance'] or 0) >= amt and amt >= 200:
                    conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt, upi_id.strip(), datetime.now().strftime("%d/%m %H:%M")))
                    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (amt, session['user_id']))
                    conn.commit()
                    add_txn(session['user_id'], amt, "WITHDRAW", f"Withdrawal Request {amt} to {upi_id}")
        except Exception as e:
            print(f"Wallet POST error: {e}")
            traceback.print_exc()
            try: conn.rollback()
            except: pass
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
    return f'<body style="text-align:center;padding:40px"><h1>NEE ID = {session["user_id"]}</h1><a href="/admin">Admin</a></body>'

@app.route('/admin', methods=['GET','POST'])
@nocache
def admin():
    if 'user_id' not in session: return redirect('/login')
    if session['user_id']!= ADMIN_USER_ID:
        return f'<body style="text-align:center;padding:40px"><h2>Access Denied! Your ID: {session["user_id"]}</h2><a href="/myid">Check My ID</a></body>'
    if session.get('admin_unlocked')!= True:
        if request.method == 'POST' and request.form.get('admin_pass_input'):
            if request.form.get('admin_pass_input') == ADMIN_PASSWORD:
                session['admin_unlocked'] = True
            else:
                return '<body style="text-align:center;padding:60px"><h2>Wrong Password!</h2><a href="/admin">Try Again</a></body>'
        else:
            return '<body style="text-align:center;padding:40px"><div style="max-width:350px;margin:0 auto;border:1px solid #e5e7eb;padding:30px"><h2>ADMIN LOGIN</h2><form method="POST"><input type="password" name="admin_pass_input" placeholder="Password NANI19" style="width:100%;padding:14px" required><button type="submit" style="width:100%;background:#111;color:#fff;padding:12px">UNLOCK</button></form></div></body>'
    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action in ['add_tournament','create_match']:
            game = request.form.get('game'); typ = request.form.get('type')
            fee = request.form.get('entry_fee') or request.form.get('fee') or 0
            prize = request.form.get('prize'); total = request.form.get('total_slots') or request.form.get('total') or 10
            tim = request.form.get('time'); per_kill = request.form.get('per_kill') or 0
            conn.execute("INSERT INTO tournaments (game,type,map,time,prize,fee,per_kill,total,status) VALUES (?,?,?,?,?,?,?,?,'UPCOMING')", (game, typ, 'Bermuda', tim, prize, fee, per_kill, total))
        elif action == 'set_room':
            conn.execute("UPDATE tournaments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (request.form.get('room_id'), request.form.get('room_pass'), request.form.get('mid')))

        # --- SMART DELETE - LOSS LEKUNDA ---
        elif action in ['delete_tournament','cancel_match','cancel_tournament','delete_match']:
            tid = request.form.get('tournament_id') or request.form.get('mid') or request.form.get('match_id')
            if tid:
                try:
                    tid_int = int(tid)
                    tour = conn.execute("SELECT fee, status FROM tournaments WHERE id=?", (tid_int,)).fetchone()
                    if not tour:
                        conn.commit()
                    else:
                        fee = int(tour['fee'] or 0)
                        status = str(tour['status'] or 'UPCOMING').upper()
                        joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid_int,)).fetchall()
                        if status == 'UPCOMING':
                            # Refund only if not played
                            for ju in joined_users:
                                uid = ju['user_id'] if hasattr(ju, 'keys') and 'user_id' in ju.keys() else ju[0]
                                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (fee, uid))
                                conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)",
                                             (uid, fee, "REFUND", f"Match #{tid_int} Cancelled - Refund Rs {fee}", datetime.now().strftime("%d/%m %H:%M")))
                            print(f"🔄 Cancelled UPCOMING {tid_int} - Refunded {len(joined_users)}")
                        else:
                            # Played match - NO REFUND - Profit safe
                            print(f"✅ Deleted PLAYED {tid_int} - No Refund - Profit Safe")
                        conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid_int,))
                        conn.execute("DELETE FROM results WHERE match_id=?", (tid_int,))
                        conn.execute("DELETE FROM tournaments WHERE id=?", (tid_int,))
                        conn.commit()
                except Exception as e:
                    print(f"Refund error: {e}")
                    traceback.print_exc()
                    try: conn.rollback()
                    except: pass

        elif action == 'approve_payment':
            pid = request.form.get('payment_id') or request.form.get('id')
            if pid:
                p = conn.execute("SELECT user_id,amount,status FROM payments WHERE id=?", (pid,)).fetchone()
                if p and p['status'] == 'PENDING':
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (p['amount'], p['user_id']))
                    conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (pid,))
                    conn.commit()
                    add_txn(p['user_id'], p['amount'], "CREDIT", f"Deposit Approved - {p['amount']}")
        elif action == 'reject_payment':
            pid = request.form.get('payment_id') or request.form.get('id')
            if pid: conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (pid,))
        elif action == 'approve_withdrawal':
            conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (request.form.get('withdrawal_id'),))
        elif action == 'reject_withdrawal':
            w = conn.execute("SELECT user_id,amount FROM withdrawals WHERE id=?", (request.form.get('withdrawal_id'),)).fetchone()
            if w:
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (w['amount'], w['user_id']))
                conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (request.form.get('withdrawal_id'),))
                conn.commit()
                add_txn(w['user_id'], w['amount'], "CREDIT", f"Withdrawal Rejected - Refund {w['amount']}")
        conn.commit()
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
    pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', matches=tournaments, tournaments=tournaments, pending_payments=pending_payments, pending_withdrawals=pending_withdrawals, total_users=0, total_tour=len(tournaments), total_earning=0)

@app.route('/admin/cancel/<int:tid>', methods=['GET','POST'])
@nocache
def admin_cancel_match(tid):
    if 'user_id' not in session or session['user_id']!= ADMIN_USER_ID:
        return redirect('/login')
    conn = get_db()
    try:
        tour = conn.execute("SELECT fee, status FROM tournaments WHERE id=?", (tid,)).fetchone()
        fee = int(tour['fee'] or 0) if tour else 0
        status = str(tour['status'] or 'UPCOMING').upper() if tour else 'UPCOMING'
        joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
        if status == 'UPCOMING':
            for ju in joined_users:
                uid = ju['user_id'] if hasattr(ju, 'keys') and 'user_id' in ju.keys() else ju[0]
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (fee, uid))
                conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)",
                             (uid, fee, "REFUND", f"Match #{tid} Cancelled - Refund Rs {fee}", datetime.now().strftime("%d/%m %H:%M")))
        conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
        conn.execute("DELETE FROM results WHERE match_id=?", (tid,))
        conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
        conn.commit()
    except Exception as e:
        traceback.print_exc()
        try: conn.rollback()
        except: pass
    finally:
        conn.close()
    return redirect('/admin')

@app.route('/cleanup')
@nocache
def cleanup_public():
    try:
        auto_expire_matches()
        return "Cleanup Done - Expired UPCOMING matches refunded & deleted", 200
    except Exception as e:
        return f"Error: {e}", 500

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
    if len(utr) < 6: return jsonify({"ok":False, "msg":"UTR short - min 6 chars"})
    conn = get_db()
    dup = conn.execute("SELECT id, user_id FROM payments WHERE utr=?", (utr,)).fetchone()
    if dup: conn.close(); return jsonify({"ok":False, "msg":"UTR IS USED! Kotha UTR veyy bro!"})
    try:
        conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(float(amt)), utr, datetime.now().strftime("%d/%m %H:%M")))
        conn.commit()
        add_txn(session['user_id'], int(float(amt)), "CREDIT", f"Deposit Request {amt} - {utr}")
    except Exception as e: conn.close(); return jsonify({"ok":False, "msg":f"Error: {e}"})
    conn.close()
    return jsonify({"ok":True, "msg":"UTR Submitted! Approval Process."})

@app.route('/request_withdrawal', methods=['POST'])
@app.route('/withdraw', methods=['POST'])
@nocache
def request_withdrawal():
    if 'user_id' not in session: return redirect('/login')
    amount = request.form.get('amount')
    upi_id = request.form.get('upi_id') or request.form.get('upi')
    try: amount = int(float(str(amount).strip()))
    except: return f"<h3>Valid amount</h3><a href='/wallet'>Back</a>"
    if amount < 200: return f"<h3>Min 200 bro</h3><a href='/wallet'>Back</a>"
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if int(user['balance'] or 0) < amount:
        conn.close()
        return f"<h3>Balance low Rs {user['balance']}</h3><a href='/wallet'>Back</a>"
    try:
        conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amount, str(upi_id).strip(), datetime.now().strftime("%d/%m %H:%M")))
        conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, session['user_id']))
        conn.commit()
        conn.close()
        add_txn(session['user_id'], amount, "WITHDRAW", f"Withdrawal Request {amount} to {upi_id}")
        return redirect('/wallet')
    except Exception as e:
        try: conn.close()
        except: pass
        return f"<h3>Error {e}</h3><a href='/wallet'>Back</a>"

@app.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect('/login'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
