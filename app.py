from flask import Flask, render_template, request, redirect, session, make_response, jsonify, send_from_directory
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
UPLOAD_FOLDER = "static/uploads"
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

def generate_daily_matches(conn):
    try:
        now = now_ist()
        today = now.strftime("%Y-%m-%d")
        now_full = now.strftime("%Y-%m-%d %H:%M")
        exact_slots = ["09:00","09:40","10:20","11:00","11:40","12:20","13:00","13:40","14:20","15:00","15:40","16:20","17:00","17:40","18:20","19:00","19:40","20:20","21:00"]
        types = [("Free Fire","Clash Squad",30,40,2),("Free Fire","Duo",30,80,4),("Free Fire","Squad",25,150,8),("Free Fire","Solo",15,1000,48)]
        created=0
        for idx, slot in enumerate(exact_slots):
            full_time = f"{today} {slot}"
            if full_time < now_full: continue
            dup = conn.execute("SELECT id FROM tournments WHERE time=?", (full_time,)).fetchone()
            if dup: continue
            g,t_type,fee,prize,total = types[idx % len(types)]
            per_kill = 8 if t_type=='Solo' else 0
            conn.execute("INSERT INTO tournments (game,type,map,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?, 'UPCOMING')",
                         (g,t_type,'Bermuda',full_time,prize,fee,per_kill,total,0))
            created+=1
        if created < 3:
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            for idx, slot in enumerate(exact_slots[:10]):
                full_time = f"{tomorrow} {slot}"
                dup = conn.execute("SELECT id FROM tournments WHERE time=?", (full_time,)).fetchone()
                if dup: continue
                g,t_type,fee,prize,total = types[idx % len(types)]
                per_kill = 8 if t_type=='Solo' else 0
                conn.execute("INSERT INTO tournments (game,type,map,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?, 'UPCOMING')",
                             (g,t_type,'Bermuda',full_time,prize,fee,per_kill,total,0))
                created+=1
        conn.commit()
        return created
    except Exception as e:
        print(f"Gen Error {e}")
        traceback.print_exc()
        return 0

def cleanup_expired_matches(conn):
    try:
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        three_hour_ago = (now_ist() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
        expired_empty = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined=0 AND status='UPCOMING'", (three_hour_ago,)).fetchall()
        for tour in expired_empty:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("DELETE FROM tournments WHERE id=?", (tid,))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
            except: pass
        expired_with = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined>0 AND status IN ('UPCOMING','LIVE')", (one_hour_ago,)).fetchall()
        for tour in expired_with:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("UPDATE tournments SET status='COMPLETED' WHERE id=?", (tid,))
            except: pass
        if expired_empty or expired_with:
            conn.commit()
    except Exception as e:
        print(f"Cleanup Error: {e}")

def nocache(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    return wrapper

@app.route('/health')
def health(): return "OK", 200

@app.route('/uploads/<filename>')
@nocache
def serve_upload(filename):
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        return f"File not found {filename}", 404

@app.route('/static/uploads/<path:filename>')
@nocache
def serve_static_upload(filename):
    try:
        return send_from_directory("static/uploads", filename)
    except:
        try:
            return send_from_directory(UPLOAD_FOLDER, filename)
        except Exception as e:
            return f"Not found {filename}", 404

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
    return "<h1>🔥 NUKED <a href='/force'>Force Now</a></h1>"

@app.route('/cleanup')
@nocache
def cleanup_only_expired():
    conn = get_db()
    try:
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        conn.execute("DELETE FROM tournments WHERE time < ? AND joined=0 AND status='UPCOMING'", (one_hour_ago,))
        conn.execute("UPDATE tournments SET status='COMPLETED' WHERE time < ? AND joined>0 AND status IN ('UPCOMING','LIVE')", (one_hour_ago,))
        conn.commit()
        conn.close()
        return f"<h1>✅ Cleaned<br><a href='/'>Home</a></h1>"
    except Exception as e:
        conn.close()
        return f"Error {e}"

@app.route('/force')
@nocache
def force_generate():
    conn = get_db()
    try:
        c = generate_daily_matches(conn)
        conn.close()
        return f"<h1>✅ Generated {c}<br><a href='/'>Home</a> | <a href='/debug'>Debug</a></h1>"
    except Exception as e:
        conn.close()
        return f"<h1>Error {e}</h1>"

@app.route('/debug')
@nocache
def debug_page():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tournments ORDER BY time ASC LIMIT 50").fetchall()
    conn.close()
    html = "<h2>DB:</h2>"
    for r in rows:
        d = dict(r)
        html += f"{d['time']} - {d['type']} - {d['status']} - {d['joined']}/{d['total']}<br>"
    html += "<br><a href='/'>Home</a> | <a href='/nuke'>Nuke</a> | <a href='/force'>Force</a>"
    return html

# ✅ FINAL FIXED - RESULTS TAB WORKING
@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    try:
        cleanup_expired_matches(conn)
        grace_check = (now_ist()).strftime("%Y-%m-%d %H:%M")
        row = conn.execute("SELECT COUNT(*) FROM tournments WHERE time >= ? AND status IN ('UPCOMING','LIVE')", (grace_check,)).fetchone()
        cnt = int(row[0] if row and row[0] else 0) if not IS_POSTGRES else int(row['count'] if row else 0)
        if cnt < 5:
            generate_daily_matches(conn)
    except Exception as e:
        print(f"Index error {e}")
    grace = (now_ist() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    t = conn.execute("SELECT * FROM tournments WHERE status IN ('UPCOMING','LIVE') AND time >= ? ORDER BY time ASC", (grace,)).fetchall()
    if len(t) == 0:
        t = conn.execute("SELECT * FROM tournments WHERE status IN ('UPCOMING','LIVE') ORDER BY time ASC LIMIT 50").fetchall()
    
    completed = conn.execute("SELECT * FROM tournments WHERE status='COMPLETED' ORDER BY time DESC LIMIT 100").fetchall()
    live = conn.execute("SELECT * FROM tournments WHERE status='LIVE' ORDER BY time ASC LIMIT 50").fetchall()
    
    results_data = {}
    try:
        all_results = conn.execute("SELECT r.*, u.username FROM results r LEFT JOIN users u ON r.user_id=u.id WHERE r.status='APPROVED' ORDER BY r.kills DESC").fetchall()
        for r in all_results:
            mid = r['match_id']
            if mid not in results_data:
                results_data[mid] = []
            results_data[mid].append(dict(r))
    except Exception as e:
        print(f"Results error {e}")

    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('index.html', tournments=t, tournaments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL, completed=completed, live_matches=live, results_data=results_data)

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
    try:
        if 'user_id' not in session: return redirect('/login')
        conn = get_db()
        tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not tour:
            conn.close()
            return redirect('/')
        try:
            joined_users = conn.execute("SELECT j.slot_no, u.username FROM joined j JOIN users u ON j.user_id=u.id WHERE j.tournament_id=? ORDER BY j.slot_no", (tid,)).fetchall()
            taken_slots = {int(row['slot_no']): str(row['username'])[:6] for row in joined_users}
        except:
            taken_slots = {}
        try:
            already = conn.execute("SELECT * FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
        except:
            already = None
        conn.close()
        return render_template('slots.html', tour=tour, t=tour, user=user, taken_slots=taken_slots, already=already)
    except Exception as e:
        print(f"slots error {e}")
        traceback.print_exc()
        return f"Slots Error: {e} - <a href='/'>Home</a>"

@app.route('/confirm_join/<int:tid>')
@nocache
def confirm_join(tid):
    try:
        if 'user_id' not in session: return redirect('/login')
        slot_no = request.args.get('slot_no') or request.args.get('slot') or "1"
        try: slot_no = int(slot_no)
        except: slot_no = 1
        conn = get_db()
        tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        if not tour: return redirect('/')
        if not user: return redirect('/login')
        return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no)
    except Exception as e:
        print(f"confirm_join error {e}")
        traceback.print_exc()
        return f"Confirm Join Error: {e} - <a href='/slots/{tid}'>Back</a> | <a href='/'>Home</a>"

@app.route('/join/<int:tid>', methods=['GET','POST'])
@nocache
def join_tournament(tid):
    try:
        if 'user_id' not in session: return redirect('/login')
        conn = get_db()
        tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not tour or not user:
            conn.close()
            return redirect('/')
        already = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
        if already:
            conn.close()
            return redirect('/my_tournaments')
        if request.method == 'GET':
            slot_no = request.args.get('slot') or request.args.get('slot_no') or 1
            try: slot_no = int(slot_no)
            except: slot_no = 1
            conn.close()
            return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no)
        game_id = (request.form.get('game_id') or '').strip()
        game_name = (request.form.get('game_name') or '').strip()
        slot_no = request.form.get('slot_no') or 1
        try: slot_no = int(slot_no)
        except: slot_no = 1
        if not game_id or not game_name:
            conn.close()
            return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_no, error="Game ID & IGN Required Bro!")
        if int(user['balance'] or 0) < int(tour['fee'] or 0):
            conn.close()
            return redirect('/wallet')
        taken = conn.execute("SELECT id FROM joined WHERE tournament_id=? AND slot_no=?", (tid, slot_no)).fetchone()
        if taken:
            conn.close()
            return redirect(f'/slots/{tid}')
        try:
            conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no, game_id, game_name) VALUES (?,?,?,?,?)", (session['user_id'], tid, slot_no, game_id, game_name))
        except:
            conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no) VALUES (?,?,?)", (session['user_id'], tid, slot_no))
        conn.execute("UPDATE tournments SET joined=joined+1 WHERE id=?", (tid,))
        conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(tour['fee']), session['user_id']))
        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (session['user_id'], int(tour['fee']), 'DEBIT', f'Join T{tid} S{slot_no}', now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
        conn.close()
        return redirect('/my_tournaments')
    except Exception as e:
        print(f"join error {e}")
        traceback.print_exc()
        try: conn.close()
        except: pass
        return f"Join Error: {e} - <a href='/slots/{tid}'>Try Again</a>"

@app.route('/my_tournaments')
@nocache
def my_tournaments():
    if 'user_id' not in session: return redirect('/login')
    conn = None
    try:
        conn = get_db()
        data = conn.execute("SELECT j.*, t.game, t.type, t.time, t.map, t.prize, t.fee, t.status, t.room_id, t.room_pass FROM joined j JOIN tournments t ON j.tournament_id=t.id WHERE j.user_id=? ORDER BY j.id DESC", (session['user_id'],)).fetchall()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        try:
            return render_template('my_tournaments.html', joined=data, user=user)
        except Exception as te:
            print(f"Template missing {te}, showing fallback")
            html = """
            <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>body{background:#0a0a0a;color:#fff;font-family:Arial;padding:12px}.card{background:#1a1a1a;padding:12px;border-radius:12px;margin:10px 0;border:1px solid #333}</style></head><body>
            <h2 style="color:#00ff88">MY TOURNAMENTS</h2>
            """
            if not data:
                html += "<p style='color:#888'>No tournaments joined yet<br><br><a href='/' style='color:#00ff88'>Join Now</a></p>"
            for j in data:
                d = dict(j)
                html += f"<div class='card'><b>#{d.get('tournament_id')} {d.get('game')} {d.get('type')}</b><br>Slot #{d.get('slot_no')} | Time {d.get('time')}<br>Game ID: {d.get('game_id','N/A')} | IGN: {d.get('game_name','N/A')}<br>"
                if d.get('room_id'):
                    html += f"<div style='color:#00ff88;margin-top:6px'>Room: {d.get('room_id')} | Pass: {d.get('room_pass')}</div>"
                else:
                    html += "<div style='color:#888;font-size:12px;margin-top:6px'>Room ID will come 10 min before</div>"
                html += "</div>"
            html += "<br><a href='/' style='background:#fff;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:900'>HOME</a></body></html>"
            return html
    except Exception as e:
        print(f"my_tournaments error {e}")
        traceback.print_exc()
        try:
            if conn: conn.close()
        except: pass
        return f"<h3>My Tournaments Error: {e}</h3><a href='/'>Home</a>"

@app.route('/my_tournments')
@nocache
def my_tournments_alias(): 
    return redirect('/my_tournaments')

@app.route('/leaderboard')
@nocache
def leaderboard():
    conn = get_db()
    try:
        top = conn.execute("SELECT id, username, total_wins, balance FROM users ORDER BY total_wins DESC LIMIT 50").fetchall()
        user = None
        if 'user_id' in session:
            user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        return render_template('leaderboard.html', top=top, user=user, my_rank=0)
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
        if not joined: 
            conn.close()
            return redirect('/')
        fname=""
        if 'screenshot' in request.files:
            f=request.files['screenshot']
            if f and f.filename and f.filename != '':
                ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else 'jpg'
                if ext not in ['jpg','jpeg','png','webp']: ext='jpg'
                fname=f"{session['user_id']}_{match_id}_{random.randint(1000,9999)}.{ext}"
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                save_path = os.path.join(UPLOAD_FOLDER, fname)
                f.save(save_path)
        existing = conn.execute("SELECT id FROM results WHERE match_id=? AND user_id=?", (int(match_id), session['user_id'])).fetchone()
        if existing:
            old = conn.execute("SELECT screenshot FROM results WHERE id=?", (existing['id'],)).fetchone()
            old_fname = old['screenshot'] if old and old['screenshot'] else ""
            final_fname = fname if fname else old_fname
            conn.execute("UPDATE results SET kills=?, screenshot=?, status='PENDING', time=? WHERE id=?", (kills_i, final_fname, now_ist().strftime("%d/%m %H:%M"), existing['id']))
        else:
            conn.execute("INSERT INTO results (match_id,user_id,kills,status,screenshot,time) VALUES (?,?,?,?,?,?)",(int(match_id),session['user_id'],kills_i,'PENDING',fname,now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
    except Exception as e: 
        print(f"Submit error {e}")
        traceback.print_exc()
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
            elif action == 'approve_result':
                rid = request.form.get('result_id')
                if rid:
                    r = conn.execute("SELECT r.*, t.per_kill FROM results r JOIN tournments t ON r.match_id=t.id WHERE r.id=?", (int(rid),)).fetchone()
                    if r:
                        conn.execute("UPDATE results SET status='APPROVED' WHERE id=?", (int(rid),))
                        if r['per_kill'] and int(r['per_kill']) > 0 and int(r['kills']) > 0:
                            kp = int(r['per_kill']) * int(r['kills'])
                            conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (kp, int(r['user_id'])))
                            conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(r['user_id']), kp, 'CREDIT', f'Kill Prize M{r["match_id"]} {r["kills"]}K', now_ist().strftime("%d/%m %H:%M")))
                        conn.commit()
            elif action == 'reject_result':
                rid = request.form.get('result_id')
                if rid:
                    conn.execute("UPDATE results SET status='REJECTED' WHERE id=?", (int(rid),)); conn.commit()
            elif action == 'complete_match':
                tid = request.form.get('tournament_id')
                if tid:
                    conn.execute("UPDATE tournments SET status='COMPLETED' WHERE id=?", (int(tid),)); conn.commit()
            elif action == 'declare_winner':
                mid = request.form.get('match_id')
                winner_id = request.form.get('winner_id')
                if mid and winner_id:
                    tour = conn.execute("SELECT prize, per_kill FROM tournments WHERE id=?", (int(mid),)).fetchone()
                    prize = int(tour['prize'] if tour and tour['prize'] else 0)
                    per_kill = int(tour['per_kill'] if tour and tour['per_kill'] else 0)
                    wr = conn.execute("SELECT * FROM results WHERE match_id=? AND user_id=?", (int(mid), int(winner_id))).fetchone()
                    kills = int(wr['kills'] if wr and wr['kills'] else 0)
                    total_prize = prize + (per_kill * kills)
                    if total_prize > 0:
                        conn.execute("UPDATE users SET balance=balance+?, total_wins=total_wins+1 WHERE id=?", (total_prize, int(winner_id)))
                        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(winner_id), total_prize, 'CREDIT', f'Won Match {mid} Prize {prize}+{per_kill}x{kills}={total_prize}', now_ist().strftime("%d/%m %H:%M")))
                    conn.execute("UPDATE results SET status='APPROVED' WHERE match_id=? AND user_id=?", (int(mid), int(winner_id)))
                    conn.execute("UPDATE tournments SET status='COMPLETED' WHERE id=?", (int(mid),))
                    conn.commit()
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
