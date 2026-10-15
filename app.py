from flask import Flask, render_template, request, redirect, session, make_response, jsonify
import os, random, string, sqlite3, traceback, urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist(): return datetime.now(IST).replace(tzinfo=None)

DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))
if IS_POSTGRES:
    import psycopg2, psycopg2.extras

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sd_final_2026")
app.config['PERMANENT_SESSION_LIFETIME']=timedelta(days=3650)

DB_FILE = "/data/sd.db" if os.path.isdir("/data") else "sd.db"
os.makedirs("/data/uploads" if os.path.isdir("/data") else "static/uploads", exist_ok=True)
os.makedirs('static', exist_ok=True)

MY_UPI_ID = os.getenv("UPI_ID", "9550043870@ibl")
SITE_URL = "https://sd-tournments.onrender.com"
ADMIN_USER_ID = 1

# ===== 12 HRS FILTER =====
@app.template_filter('time12')
def time12_filter(t):
    try:
        if not t: return ""
        s = str(t).strip()
        parts = s.split(":")
        if len(parts) < 2: return s
        h = int(parts[0]); m = int(parts[1])
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12
        if h12 == 0: h12 = 12
        return f"{h12}:{m:02d} {ampm}"
    except: return str(t)

@app.template_filter('time')
def time_filter(t): return time12_filter(t)

class PGWrapper:
    def __init__(self, conn): self.conn = conn
    def execute(self, query, params=()):
        q = query.replace("?", "%s")
        if q.strip().upper().startswith("PRAGMA"):
            class Dummy:
                def fetchone(self): return None
                def fetchall(self): return []
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

def init_db():
    conn = get_db()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
        conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)" if IS_POSTGRES else "CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
        conn.commit()
    except Exception as e: print(e)
    finally: conn.close()
init_db()

def nocache(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    return wrapper

def is_admin():
    return 'user_id' in session and session['user_id'] == ADMIN_USER_ID

@app.route('/health')
def health(): return "OK", 200

@app.errorhandler(500)
def handle_500(e):
    traceback.print_exc()
    return f"<h3>500 Error</h3><pre>{traceback.format_exc()}</pre>", 500

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
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL)

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
            if 'ref_code' in session and session['ref_code']:
                ref_user = conn.execute("SELECT id FROM users WHERE referral_code=?", (session['ref_code'],)).fetchone()
                if ref_user and ref_user['id']!= user['id']:
                    conn.execute("UPDATE users SET balance=balance+10 WHERE id=?", (ref_user['id'],))
                    conn.execute("UPDATE users SET balance=balance+10, referred_by=? WHERE id=?", (ref_user['id'], user['id']))
                    conn.commit()
            session['user_id'] = user['id']
            session.pop('ref_code', None)
            conn.close()
            return redirect('/')
        except Exception as e:
            conn.close()
            return render_template('register.html', error=f"Username exists! {e}")
    return render_template('register.html', ref_code=session.get('ref_code',''))

@app.route('/login', methods=['GET','POST'])
@nocache
def login():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        u = (request.form.get('username') or "").strip()
        p = (request.form.get('password') or "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if not user: conn.close(); return render_template('login.html', error="Account Not Found!")
        if user['password']!= p: conn.close(); return render_template('login.html', error="Wrong Password!")
        session['user_id'] = user['id']
        conn.close()
        return redirect('/')
    return render_template('login.html')

@app.route('/refer/<code>')
@nocache
def referral_page(code):
    session['ref_code'] = code.upper().strip()
    session.permanent = True
    return redirect('/register')

@app.route('/account')
@nocache
def account():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    payments = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 20", (session['user_id'],)).fetchall()
    withdrawals = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 20", (session['user_id'],)).fetchall()
    joined_count = conn.execute("SELECT COUNT(*) FROM joined WHERE user_id=?", (session['user_id'],)).fetchone()[0]
    conn.close()
    return render_template('account.html', user=user, payments=payments, withdrawals=withdrawals, joined_count=joined_count, site_url=SITE_URL)

@app.route('/wallet', methods=['GET','POST'])
@nocache
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    try:
        if request.method == 'POST':
            utr = (request.form.get('utr') or "").strip().upper()
            upi_id = (request.form.get('upi_id') or "").strip()
            amount = request.form.get('amount') or "0"
            if utr and amount:
                dup = conn.execute("SELECT id FROM payments WHERE utr=?", (utr,)).fetchone()
                if not dup:
                    amt_i = int(float(amount))
                    if amt_i >= 10:
                        conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt_i, utr, now_ist().strftime("%d/%m %H:%M")))
                        conn.commit()
            elif upi_id and amount:
                amt = int(float(amount))
                user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
                if user and int(user['balance'] or 0) >= amt and amt >= 200:
                    conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt, upi_id, now_ist().strftime("%d/%m %H:%M")))
                    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (amt, session['user_id']))
                    conn.commit()
            conn.close()
            return redirect('/wallet')
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        payments = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
        withdrawals = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
        txns = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50", (session['user_id'],)).fetchall()
        conn.close()
        return render_template('wallet.html', user=user, payments=payments, withdrawals=withdrawals, transactions=txns, wallet=user['balance'])
    except Exception as e:
        print(e); traceback.print_exc()
        try: conn.close()
        except: pass
        return f"Wallet Error: {e}", 500

@app.route('/get_qr')
@nocache
def get_qr():
    if 'user_id' not in session: return jsonify({"error": "login"}), 401
    amount = request.args.get('amount', '50')
    try: amt = int(float(amount))
    except: amt = 50
    upi_link = f"upi://pay?pa={MY_UPI_ID}&pn=SDTournament&am={amt}&cu=INR"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(upi_link)}"
    return jsonify({"qr_url": qr_url, "upi_link": upi_link})

@app.route('/verify_upi', methods=['POST'])
@nocache
def verify_upi():
    if 'user_id' not in session: return jsonify({"ok": False, "msg": "Login avvu bro!"}), 401
    conn = None
    try:
        data = request.get_json() if request.is_json else request.form
        utr = (data.get('utr') or "").strip().upper()
        amount = data.get('amount') or 0
        if not utr or len(utr) < 6: return jsonify({"ok": False, "msg": "Valid UTR enter chey bro!"}), 400
        conn = get_db()
        dup = conn.execute("SELECT id FROM payments WHERE utr=?", (utr,)).fetchone()
        if dup:
            conn.close()
            return jsonify({"ok": False, "msg": "Ee UTR already use chesav bro!"}), 400
        amt_i = int(float(amount))
        conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt_i, utr, now_ist().strftime("%d/%m %H:%M")))
        conn.commit(); conn.close()
        return jsonify({"ok": True, "msg": f"✅ ₹{amt_i} Submitted! Admin approve chestadu!"})
    except Exception as e:
        print(e); traceback.print_exc()
        try:
            if conn: conn.close()
        except: pass
        return jsonify({"ok": False, "msg": f"Error: {e}"}), 500

@app.route('/request_withdrawal', methods=['POST'])
@nocache
def request_withdrawal(): return redirect('/wallet')

@app.route('/join/<int:tid>', methods=['POST','GET'])
@nocache
def join_tournament(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    try:
        tour = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not tour or not user: conn.close(); return redirect('/')
        already = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
        if already: conn.close(); return redirect('/')
        if int(user['balance'] or 0) < int(tour['fee'] or 0): conn.close(); return redirect('/wallet')
        if int(tour['joined'] or 0) >= int(tour['total'] or 10): conn.close(); return redirect('/')
        slot = int(tour['joined'] or 0) + 1
        conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no) VALUES (?,?,?)", (session['user_id'], tid, slot))
        conn.execute("UPDATE tournaments SET joined=joined+1 WHERE id=?", (tid,))
        conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(tour['fee']), session['user_id']))
        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (session['user_id'], int(tour['fee']), 'DEBIT', f'Joined Tournament {tid}', now_ist().strftime("%d/%m %H:%M")))
        conn.commit(); conn.close()
        return redirect('/')
    except Exception as e:
        print(e); conn.close(); return redirect('/')

@app.route('/my_tournaments')
@nocache
def my_tournaments():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    data = conn.execute("SELECT j.*, t.* FROM joined j JOIN tournaments t ON j.tournament_id=t.id WHERE j.user_id=? ORDER BY j.id DESC", (session['user_id'],)).fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('my_tournaments.html', joined=data, user=user)

# ===== ADMIN ROUTES - IKKADA UNNAI BRO =====
@app.route('/admin')
@nocache
def admin():
    if not is_admin(): return "Not Authorized - Login with Admin Account (ID=1)", 403
    conn = get_db()
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    payments = conn.execute("SELECT p.*, u.username FROM payments p JOIN users u ON p.user_id=u.id ORDER BY p.id DESC").fetchall()
    withdrawals = conn.execute("SELECT w.*, u.username FROM withdrawals w JOIN users u ON w.user_id=u.id ORDER BY w.id DESC").fetchall()
    conn.close()
    return render_template('admin.html', tournaments=tournaments, users=users, payments=payments, withdrawals=withdrawals)

@app.route('/admin/create', methods=['POST'])
@nocache
def admin_create():
    if not is_admin(): return redirect('/login')
    game = request.form.get('game','FREE FIRE')
    type_ = request.form.get('type','Solo')
    map_ = request.form.get('map','Bermuda')
    time_ = request.form.get('time','18:00')
    prize = int(request.form.get('prize',1000))
    fee = int(request.form.get('fee',20))
    total = int(request.form.get('total',48))
    conn = get_db()
    conn.execute("INSERT INTO tournaments (game,type,map,time,prize,fee,total,joined,status) VALUES (?,?,?,?,?,?,?,0,'UPCOMING')", (game,type_,map_,time_,prize,fee,total))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/delete/<int:tid>')
@nocache
def admin_delete(tid):
    if not is_admin(): return redirect('/login')
    conn = get_db()
    conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
    conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/approve_payment/<int:pid>')
@nocache
def admin_approve_payment(pid):
    if not is_admin(): return redirect('/login')
    conn = get_db()
    pay = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if pay and pay['status']!= 'APPROVED':
        conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (pid,))
        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(pay['amount']), int(pay['user_id'])))
        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(pay['user_id']), int(pay['amount']), 'CREDIT', f'Payment Approved {pay["utr"]}', now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/admin/reject_payment/<int:pid>')
@nocache
def admin_reject_payment(pid):
    if not is_admin(): return redirect('/login')
    conn = get_db()
    conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/approve_withdraw/<int:wid>')
@nocache
def admin_approve_withdraw(wid):
    if not is_admin(): return redirect('/login')
    conn = get_db()
    conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (wid,))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/reject_withdraw/<int:wid>')
@nocache
def admin_reject_withdraw(wid):
    if not is_admin(): return redirect('/login')
    conn = get_db()
    w = conn.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if w and w['status'] == 'PENDING':
        conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (wid,))
        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(w['amount']), int(w['user_id'])))
        conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/admin/set_room', methods=['POST'])
@nocache
def admin_set_room():
    if not is_admin(): return redirect('/login')
    tid = request.form.get('tid')
    room_id = request.form.get('room_id')
    room_pass = request.form.get('room_pass')
    conn = get_db()
    conn.execute("UPDATE tournaments SET room_id=?, room_pass=? WHERE id=?", (room_id, room_pass, tid))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
