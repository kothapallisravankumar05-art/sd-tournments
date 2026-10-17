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
UPLOAD_FOLDER = "/data/uploads" if os.path.isdir("/data") else "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('static/uploads', exist_ok=True)
MY_UPI_ID = os.getenv("UPI_ID", "9550043870@ibl")
SITE_URL = "https://sd-tournments.onrender.com"

@app.template_filter('time12')
def time12_filter(t):
    try:
        if not t: return ""
        s = str(t).strip()
        if " " in s: s = s.split(" ")[-1]
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
@app.template_filter('time12only')
def time12only_filter(t): return time12_filter(t)

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
        if IS_POSTGRES:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0, game_id TEXT DEFAULT '', game_name TEXT DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, match_id INTEGER, user_id INTEGER, kills INTEGER, status TEXT DEFAULT 'PENDING', screenshot TEXT, time TEXT)")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0, game_id TEXT DEFAULT '', game_name TEXT DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, status TEXT DEFAULT 'PENDING', screenshot TEXT, time TEXT)")
        conn.commit()
    except Exception as e: print(e)
    finally: conn.close()

def migrate_game_id():
    conn = get_db()
    try:
        for q in ["ALTER TABLE joined ADD COLUMN game_id TEXT DEFAULT ''", "ALTER TABLE joined ADD COLUMN game_name TEXT DEFAULT ''"]:
            try: conn.execute(q)
            except: pass
        conn.commit()
    except: pass
    finally: conn.close()

init_db()
migrate_game_id()

# ===== FIXED FINAL LOGIC =====
def generate_daily_matches(conn):
    try:
        now = now_ist()
        today_str = now.strftime("%Y-%m-%d")
        now_str = now.strftime("%Y-%m-%d %H:%M")
        print(f"Generating for {today_str}, now={now_str}")
        try:
            if IS_POSTGRES:
                row = conn.execute("SELECT COUNT(*) as count FROM tournments WHERE time LIKE ? AND status='UPCOMING' AND time >= ?", (f"{today_str}%", now_str)).fetchone()
                future_count = int(row['count'] if row and 'count' in row else 0)
            else:
                row = conn.execute("SELECT COUNT(*) FROM tournments WHERE time LIKE ? AND status='UPCOMING' AND time >= ?", (f"{today_str}%", now_str)).fetchone()
                future_count = int(row[0] if row else 0)
            print(f"Future count: {future_count}")
            if future_count >= 8:
                return 0
        except Exception as e:
            print(f"Count error {e}")

        start_time = now.replace(second=0, microsecond=0) + timedelta(minutes=10)
        nine_am = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if start_time < nine_am:
            start_time = nine_am
        if start_time.hour >= 21:
            start_time = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            print(f"After 9PM, starting tomorrow {start_time}")

        types = [("Free Fire","Clash Squad",30,40,2),("Free Fire","Duo",30,80,4),("Free Fire","Squad",25,150,8),("Free Fire","Solo",15,1000,48)]
        created = 0
        for i in range(19):
            t = start_time + timedelta(minutes=i*40)
            if t.day == start_time.day and t.hour > 21:
                break
            if t.day != start_time.day and t.hour > 21:
                break
            time_str = t.strftime("%Y-%m-%d %H:%M")
            dup = conn.execute("SELECT id FROM tournments WHERE time=?", (time_str,)).fetchone()
            if dup:
                continue
            game, typ, fee, prize, total = types[i % len(types)]
            per_kill = 8 if typ == 'Solo' else 0
            conn.execute("INSERT INTO tournments (game,type,map,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?, 'UPCOMING')",
                        (game, typ, 'Bermuda', time_str, prize, fee, per_kill, total, 0))
            created += 1
        conn.commit()
        print(f"GENERATED {created} from {start_time}")
        return created
    except Exception as e:
        print(f"Gen Error: {e}")
        traceback.print_exc()
        return 0

def cleanup_expired_matches(conn):
    try:
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        print(f"Cleanup before {one_hour_ago}")
        expired_empty = conn.execute("SELECT id, time FROM tournments WHERE time < ? AND joined=0 AND status='UPCOMING'", (one_hour_ago,)).fetchall()
        print(f"Found {len(expired_empty)} empty to DELETE")
        for tour in expired_empty:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("DELETE FROM tournments WHERE id=?", (tid,))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
            except: pass
        expired_with = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined>0 AND status='UPCOMING'", (one_hour_ago,)).fetchall()
        print(f"Found {len(expired_with)} to COMPLETE")
        for tour in expired_with:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("UPDATE tournments SET status='COMPLETED' WHERE id=?", (tid,))
            except: pass
        if expired_empty or expired_with:
            conn.commit()
    except Exception as e:
        print(f"Cleanup Error: {e}")
        traceback.print_exc()

def nocache(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    return wrapper

@app.route('/health')
def health(): return "OK", 200

@app.route('/nuke')
@nocache
def nuke_all():
    conn = get_db()
    try:
        if IS_POSTGRES:
            cur = conn.conn.cursor()
            cur.execute("TRUNCATE TABLE joined, tournments RESTART IDENTITY CASCADE")
            conn.conn.commit()
        else:
            conn.execute("DELETE FROM joined")
            conn.execute("DELETE FROM tournments")
            conn.commit()
    except:
        try:
            conn.execute("DELETE FROM joined")
            conn.execute("DELETE FROM tournments")
            conn.commit()
        except: pass
    conn.close()
    return "<h1>🔥 NUKED! <a href='/force'>Force</a></h1>"

@app.route('/cleanup')
@nocache
def cleanup_only_expired():
    conn = get_db()
    try:
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        conn.execute("DELETE FROM tournments WHERE time < ? AND joined=0 AND status='UPCOMING'", (one_hour_ago,))
        conn.execute("UPDATE tournments SET status='COMPLETED' WHERE time < ? AND joined>0 AND status='UPCOMING'", (one_hour_ago,))
        conn.commit()
        conn.close()
        return f"<h1>✅ Cleaned expired (1h old)<br><a href='/'>Home</a></h1>"
    except Exception as e:
        conn.close()
        return f"Error {e}"

@app.route('/force')
@nocache
def force_generate():
    conn = get_db()
    try:
        c = generate_daily_matches(conn)
        if IS_POSTGRES:
            row = conn.execute("SELECT COUNT(*) as count FROM tournments WHERE status='UPCOMING' AND time >= ?", (now_ist().strftime("%Y-%m-%d %H:%M"),)).fetchone()
            cnt = int(row['count'] if row else 0)
        else:
            row = conn.execute("SELECT COUNT(*) FROM tournments WHERE status='UPCOMING' AND time >= ?", (now_ist().strftime("%Y-%m-%d %H:%M"),)).fetchone()
            cnt = int(row[0] if row else 0)
        conn.close()
        return f"<h1>Generated {c}, Future {cnt}<br><a href='/'>Home</a> | <a href='/debug'>Debug</a></h1>"
    except Exception as e:
        conn.close()
        return f"<h1>Error {e}</h1>"

@app.route('/debug')
@nocache
def debug_page():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tournments ORDER BY time ASC LIMIT 50").fetchall()
    conn.close()
    html = "<h2>DB Tournaments:</h2>"
    for r in rows:
        html += f"{dict(r)}<br>"
    html += "<br><a href='/'>Home</a> | <a href='/nuke'>Nuke</a> | <a href='/force'>Force</a>"
    return html

@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    try:
        cleanup_expired_matches(conn)
        generate_daily_matches(conn)
    except Exception as e:
        print(f"Index error {e}")
    now_str = now_ist().strftime("%Y-%m-%d %H:%M")
    today_str = now_ist().strftime("%Y-%m-%d")
    t = conn.execute("SELECT * FROM tournments WHERE status='UPCOMING' AND time >= ? ORDER BY time ASC", (now_str,)).fetchall()
    if len(t) == 0:
        t = conn.execute("SELECT * FROM tournments WHERE status='UPCOMING' AND time LIKE ? ORDER BY time ASC", (f"{today_str}%",)).fetchall()
    if len(t) == 0:
        t = conn.execute("SELECT * FROM tournments WHERE status='UPCOMING' ORDER BY time ASC LIMIT 30").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    # FIX: Send both names - tournaments and tournments - so HTML never fails
    return render_template('index.html', tournments=t, tournaments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL)

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
            session.permanent = True
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
        if not user: user = conn.execute("SELECT * FROM users WHERE phone=?", (u,)).fetchone()
        if not user: conn.close(); return render_template('login.html', error="Account Not Found!")
        if user['password']!= p: conn.close(); return render_template('login.html', error="Wrong Password!")
        session.permanent = True
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

@app.route('/deposit_history')
@nocache
def deposit_history():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    history = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (int(session['user_id']),)).fetchall()
    conn.close()
    return render_template('deposit_history.html', history=history, user=user)

@app.route('/withdraw_history')
@nocache
def withdraw_history():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    history = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC", (int(session['user_id']),)).fetchall()
    conn.close()
    return render_template('withdraw_history.html', history=history, user=user)

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
        return jsonify({"ok": True, "msg": f"✅ ₹{amt_i} Submitted!"})
    except Exception as e:
        try:
            if conn: conn.close()
        except: pass
        return jsonify({"ok": False, "msg": f"Error: {e}"}), 500

@app.route('/forgot', methods=['GET','POST'])
@nocache
def forgot_password():
    if request.method == 'POST':
        phone = (request.form.get('phone') or request.form.get('username') or "").strip()
        new_pass = (request.form.get('new_password') or "").strip()
        confirm_pass = (request.form.get('confirm_password') or new_pass).strip()
        if len(phone) < 4: return render_template('forgot.html', error="Phone/Username Enter Chey Bro!")
        if len(new_pass) < 4: return render_template('forgot.html', error="Password Min 4 Characters!")
        if new_pass != confirm_pass: return render_template('forgot.html', error="Passwords Match Kavatledu!")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        if not user: user = conn.execute("SELECT * FROM users WHERE username=?", (phone,)).fetchone()
        if not user:
            conn.close()
            return render_template('forgot.html', error="Account Not Found!")
        conn.execute("UPDATE users SET password=? WHERE id=?", (new_pass, user['id']))
        conn.commit(); conn.close()
        return render_template('forgot.html', success="✅ Password Changed!")
    return render_template('forgot.html')

@app.route('/slots/<int:tid>')
@nocache
def slots_page(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not tour: conn.close(); return redirect('/')
    joined_users = conn.execute("SELECT j.slot_no, u.username FROM joined j JOIN users u ON j.user_id=u.id WHERE j.tournament_id=? ORDER BY j.slot_no", (tid,)).fetchall()
    taken_slots = {row['slot_no']: row['username'] for row in joined_users}
    already = conn.execute("SELECT * FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    conn.close()
    return render_template('slots.html', tour=tour, t=tour, user=user, taken_slots=taken_slots, total_slots=len(taken_slots), already=already)

@app.route('/confirm_join/<int:tid>')
@nocache
def confirm_join(tid):
    if 'user_id' not in session: return redirect('/login')
    slot_no = request.args.get('slot_no') or request.args.get('slot')
    if not slot_no: return redirect(f'/slots/{tid}')
    conn = get_db()
    tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    if not tour: return redirect('/')
    return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no)

@app.route('/join/<int:tid>', methods=['GET','POST'])
@nocache
def join_tournament(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not tour or not user: conn.close(); return redirect('/')
    already = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    if already: conn.close(); return redirect('/my_tournaments')
    if request.method == 'GET':
        slot_no = request.args.get('slot') or request.args.get('slot_no') or 1
        try: slot_no = int(slot_no)
        except: slot_no = 1
        conn.close()
        return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no)
    game_id = request.form.get('game_id','').strip()
    game_name = request.form.get('game_name','').strip()
    slot_no = request.form.get('slot_no') or 1
    try: slot_no = int(slot_no)
    except: slot_no = 1
    if not game_id or not game_name:
        conn.close()
        return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no, error="Game ID & IGN Enter Chey Bro!")
    if int(user['balance'] or 0) < int(tour['fee'] or 0): conn.close(); return redirect('/wallet')
    taken = conn.execute("SELECT id FROM joined WHERE tournament_id=? AND slot_no=?", (tid, slot_no)).fetchone()
    if taken: conn.close(); return redirect(f'/slots/{tid}')
    conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no, game_id, game_name) VALUES (?,?,?,?,?)", (session['user_id'], tid, slot_no, game_id, game_name))
    conn.execute("UPDATE tournments SET joined=joined+1 WHERE id=?", (tid,))
    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(tour['fee']), session['user_id']))
    conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (session['user_id'], int(tour['fee']), 'DEBIT', f'Joined T{tid} S{slot_no} ID:{game_id}', now_ist().strftime("%d/%m %H:%M")))
    conn.commit(); conn.close()
    return redirect('/my_tournaments')

@app.route('/my_tournaments')
@nocache
def my_tournaments():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    data = conn.execute("SELECT j.*, t.game, t.type, t.time, t.map, t.prize, t.fee, t.status, t.room_id, t.room_pass FROM joined j JOIN tournments t ON j.tournament_id=t.id WHERE j.user_id=? ORDER BY j.id DESC", (session['user_id'],)).fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('my_tournaments.html', joined=data, user=user)

@app.route('/my_tournments')
@nocache
def my_tournments_alias(): return redirect('/my_tournaments')

@app.route('/leaderboard')
@nocache
def leaderboard():
    conn = get_db()
    try:
        top = conn.execute("SELECT id, username, total_wins, balance FROM users ORDER BY total_wins DESC LIMIT 50").fetchall()
        user = None; my_rank = 0
        if 'user_id' in session:
            user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        return render_template('leaderboard.html', top=top, user=user, my_rank=my_rank)
    except:
        try: conn.close()
        except: pass
        return redirect('/')

@app.route('/submit_result', methods=['POST'])
@nocache
def submit_result():
    if 'user_id' not in session: return redirect('/login')
    match_id = request.form.get('match_id') or 0
    kills = request.form.get('kills') or 0
    try: kills_i=int(kills)
    except: kills_i=0
    conn=get_db()
    try:
        joined = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], int(match_id))).fetchone()
        if not joined: conn.close(); return redirect('/')
        fname=""
        if 'screenshot' in request.files:
            f=request.files['screenshot']
            if f and f.filename:
                fname=f"{session['user_id']}_{match_id}_{random.randint(1000,9999)}.jpg"
                f.save(os.path.join(UPLOAD_FOLDER,fname))
        existing = conn.execute("SELECT id FROM results WHERE match_id=? AND user_id=?", (int(match_id), session['user_id'])).fetchone()
        if existing:
            conn.execute("UPDATE results SET kills=?, screenshot=?, status='PENDING', time=? WHERE id=?", (kills_i, fname, now_ist().strftime("%d/%m %H:%M"), existing['id']))
        else:
            conn.execute("INSERT INTO results (match_id,user_id,kills,status,screenshot,time) VALUES (?,?,?,?,?,?)",(int(match_id),session['user_id'],kills_i,'PENDING',fname,now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
    except Exception as e: print(e)
    finally: conn.close()
    return redirect(f'/match_result/{match_id}')

@app.route('/match_result/<int:mid>')
@nocache
def match_result(mid):
    conn=get_db()
    tour=conn.execute("SELECT * FROM tournments WHERE id=?",(mid,)).fetchone()
    results=conn.execute("SELECT r.*,u.username FROM results r LEFT JOIN users u ON r.user_id=u.id WHERE r.match_id=? ORDER BY r.kills DESC",(mid,)).fetchall()
    conn.close()
    return render_template('match_result.html', t=tour, results=results) if tour else redirect('/')

@app.route('/admin', methods=['GET','POST'])
@nocache
def admin_panel():
    ADMIN_PASSWORD = "101210"
    if 'is_admin_logged' not in session:
        if request.method == 'POST':
            pwd = request.form.get('admin_password','')
            if pwd == ADMIN_PASSWORD:
                session['is_admin_logged'] = True
                return redirect('/admin')
            else:
                return "<html><body><h3>Wrong Password!</h3><form method='POST'><input type='password' name='admin_password'><button>LOGIN</button></form></body></html>"
        return "<html><body><h3>ADMIN LOGIN</h3><form method='POST'><input type='password' name='admin_password' placeholder='Password'><button>LOGIN</button></form><a href='/'>Home</a></body></html>"
    conn = get_db()
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'auto_generate':
                generate_daily_matches(conn)
            elif action == 'add_tournament':
                game = request.form.get('game','Free Fire'); typ = request.form.get('type','Squad')
                fee = int(request.form.get('entry_fee') or 25); prize = int(request.form.get('prize') or 150)
                total = int(request.form.get('total_slots') or 8); per_kill = int(request.form.get('per_kill') or 0)
                time_str = request.form.get('time') or now_ist().strftime("%Y-%m-%d %H:%M")
                conn.execute("INSERT INTO tournments (game,type,map,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?, 'UPCOMING')",(game, typ, 'Bermuda', time_str, prize, fee, per_kill, total, 0)); conn.commit()
            elif action == 'set_room':
                mid = request.form.get('mid'); room_id = request.form.get('room_id'); room_pass = request.form.get('room_pass')
                if mid: conn.execute("UPDATE tournments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (room_id, room_pass, int(mid))); conn.commit()
            elif action == 'generate_room_id':
                mid = request.form.get('mid')
                if mid:
                    rid = ''.join(random.choices(string.digits, k=6)); rpass = ''.join(random.choices(string.digits, k=4))
                    conn.execute("UPDATE tournments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (rid, rpass, int(mid))); conn.commit()
            elif action == 'cancel_tournament':
                tid = request.form.get('tournament_id')
                if tid:
                    joined_users = conn.execute("SELECT j.user_id, t.fee FROM joined j JOIN tournments t ON j.tournament_id=t.id WHERE j.tournament_id=?", (int(tid),)).fetchall()
                    for ju in joined_users:
                        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (ju['fee'] or 0, ju['user_id']))
                    conn.execute("DELETE FROM joined WHERE tournament_id=?", (int(tid),))
                    conn.execute("UPDATE tournments SET status='CANCELLED' WHERE id=?", (int(tid),)); conn.commit()
            elif action == 'delete_tournament':
                tid = request.form.get('tournament_id')
                if tid:
                    joined_users = conn.execute("SELECT j.user_id, t.fee FROM joined j JOIN tournments t ON j.tournament_id=t.id WHERE j.tournament_id=?", (int(tid),)).fetchall()
                    for ju in joined_users:
                        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (ju['fee'] or 0, ju['user_id']))
                    conn.execute("DELETE FROM joined WHERE tournament_id=?", (int(tid),))
                    conn.execute("DELETE FROM tournments WHERE id=?", (int(tid),)); conn.commit()
            elif action == 'approve_payment':
                pid = request.form.get('payment_id')
                if pid:
                    p = conn.execute("SELECT * FROM payments WHERE id=?", (int(pid),)).fetchone()
                    if p and p['status'] == 'PENDING':
                        conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (int(pid),))
                        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(p['amount']), int(p['user_id']))); conn.commit()
            elif action == 'reject_payment':
                pid = request.form.get('payment_id')
                if pid: conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (int(pid),)); conn.commit()
            elif action == 'approve_withdrawal':
                wid = request.form.get('withdrawal_id')
                if wid: conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (int(wid),)); conn.commit()
            elif action == 'reject_withdrawal':
                wid = request.form.get('withdrawal_id')
                if wid:
                    w = conn.execute("SELECT * FROM withdrawals WHERE id=?", (int(wid),)).fetchone()
                    if w and w['status']=='PENDING':
                        conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (int(wid),))
                        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(w['amount']), int(w['user_id']))); conn.commit()
        raw = conn.execute("SELECT * FROM tournments ORDER BY time ASC").fetchall()
        matches = []
        for mm in raw:
            d = dict(mm)
            try:
                j = conn.execute("SELECT u.username, j.slot_no FROM joined j JOIN users u ON j.user_id=u.id WHERE j.tournament_id=?", (mm['id'],)).fetchall()
                d['joined_list'] = ", ".join([f"{x['slot_no']}:{x['username']}" for x in j]) if j else ""
            except:
                d['joined_list'] = ""
            matches.append(d)
        pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
        pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
        try: pending_results = conn.execute("SELECT r.*, u.username FROM results r LEFT JOIN users u ON r.user_id=u.id WHERE r.status='PENDING' ORDER BY r.id DESC").fetchall()
        except: pending_results = []
        conn.close()
        return render_template('admin.html', matches=matches, pending_payments=pending_payments, pending_withdrawals=pending_withdrawals, pending_results=pending_results)
    except Exception as e:
        print(e); traceback.print_exc()
        try: conn.close()
        except: pass
        return f"Admin Error: {e}", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
