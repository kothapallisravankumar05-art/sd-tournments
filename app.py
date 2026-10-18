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
            conn.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT UNIQUE, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0, game_id TEXT DEFAULT '', game_name TEXT DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, match_id INTEGER, user_id INTEGER, kills INTEGER, status TEXT DEFAULT 'PENDING', screenshot TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER, title TEXT, message TEXT, is_read INTEGER DEFAULT 0, time TEXT)")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT UNIQUE, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0, game_id TEXT DEFAULT '', game_name TEXT DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, status TEXT DEFAULT 'PENDING', screenshot TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, message TEXT, is_read INTEGER DEFAULT 0, time TEXT)")
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

def generate_referral_code_unique(conn):
    for _ in range(10):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = conn.execute("SELECT id FROM users WHERE referral_code=?", (code,)).fetchone()
        if not exists:
            return code
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_notification(conn, user_id, title, message):
    try:
        conn.execute("INSERT INTO notifications (user_id, title, message, is_read, time) VALUES (?,?,?,?,?)",
                     (user_id, title, message, 0, now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
    except Exception as e:
        print(f"Notify error {e}")

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
            if full_time < now_full: 
                continue
            dup = conn.execute("SELECT id FROM tournments WHERE time=?", (full_time,)).fetchone()
            if dup: 
                continue
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

# --- BRO FIXED LOGIC HERE 🔥 ---
def cleanup_expired_matches(conn):
    try:
        now_str = now_ist().strftime("%Y-%m-%d %H:%M")
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        
        # 1. TIME AYIPOINA + 0 JOINED = VENTANE DELETE
        expired_empty = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined=0", (now_str,)).fetchall()
        for tour in expired_empty:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("DELETE FROM tournments WHERE id=?", (tid,))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                print(f"🗑️ Auto Deleted Empty: {tid}")
            except: pass

        # 2. TIME AYIPOINA + JOINED>0 = 1 HOUR TARWATA COMPLETED
        expired_with = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined>0 AND status IN ('UPCOMING','LIVE')", (one_hour_ago,)).fetchall()
        for tour in expired_with:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("UPDATE tournments SET status='COMPLETED' WHERE id=?", (tid,))
                print(f"✅ Completed: {tid}")
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
    except: return f"File not found {filename}", 404

@app.route('/static/uploads/<path:filename>')
@nocache
def serve_static_upload(filename):
    try:
        return send_from_directory("static/uploads", filename)
    except:
        try:
            return send_from_directory(UPLOAD_FOLDER, filename)
        except: return f"Not found {filename}", 404

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
        now_str = now_ist().strftime("%Y-%m-%d %H:%M")
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        # FIXED: Empty matches immediate delete
        conn.execute("DELETE FROM tournments WHERE time < ? AND joined=0", (now_str,))
        conn.execute("UPDATE tournments SET status='COMPLETED' WHERE time < ? AND joined>0 AND status IN ('UPCOMING','LIVE')", (one_hour_ago,))
        conn.commit()
        conn.close()
        return f"<h1>✅ Cleaned Empty Matches Deleted<br><a href='/'>Home</a></h1>"
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
        return f"<h1> Generated {c}<br><a href='/'>Home</a> | <a href='/debug'>Debug</a></h1>"
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
    if not user:
        session.clear()
        conn.close()
        return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    try:
        notif_count = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()[0]
    except:
        notif_count = 0
    conn.close()
    return render_template('index.html', tournaments=t, tournments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL, completed=completed, live_matches=live, results_data=results_data, notif_count=notif_count)

# ... rest of your routes same as before ...

@app.route('/register', methods=['GET','POST'])
@nocache
def register():
    if 'user_id' in session: return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        phone = request.form.get('phone','').strip()
        if not username or not password:
            return render_template('register.html', error="Username & Password Required!")
        conn = get_db()
        try:
            ref_code_new = generate_referral_code_unique(conn)
            conn.execute("INSERT INTO users (username,password,phone,balance,referral_code,referred_by) VALUES (?,?,?,?,?,0)", (username,password,phone,0,ref_code_new))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            ref_code_session = session.get('ref_code')
            if ref_code_session:
                ref_code_session = ref_code_session.upper().strip()
                ref_user = conn.execute("SELECT id,balance FROM users WHERE referral_code=?", (ref_code_session,)).fetchone()
                if ref_user and int(ref_user['id']) != int(user['id']):
                    already_referred = int(user['referred_by'] or 0) != 0
                    if not already_referred:
                        conn.execute("UPDATE users SET balance=balance+10 WHERE id=?", (int(ref_user['id']),))
                        conn.execute("UPDATE users SET balance=balance+10, referred_by=? WHERE id=?", (int(ref_user['id']), int(user['id'])))
                        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(ref_user['id']), 10, 'CREDIT', f'Referral Bonus from {username}', now_ist().strftime("%d/%m %H:%M")))
                        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(user['id']), 10, 'CREDIT', f'Referral Bonus from {ref_code_session}', now_ist().strftime("%d/%m %H:%M")))
                        create_notification(conn, int(ref_user['id']), "🎉 Referral Success!", f"{username} joined with your code! +₹10 added")
                        create_notification(conn, int(user['id']), "🎉 Welcome Bonus!", f"You got ₹10 referral bonus from {ref_code_session}!")
                        conn.commit()
            session.permanent = True
            session['user_id'] = user['id']
            session.pop('ref_code', None)
            conn.close()
            return redirect('/')
        except Exception as e:
            try: conn.close()
            except: pass
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
def referral_redirect(code):
    session['ref_code'] = code.upper().strip()
    session.permanent = True
    return redirect('/register')

@app.route('/referral')
@nocache
def referral_dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user:
        conn.close()
        session.clear()
        return redirect('/login')
    if not user['referral_code']:
        new_code = generate_referral_code_unique(conn)
        conn.execute("UPDATE users SET referral_code=? WHERE id=?", (new_code, user['id']))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    code = user['referral_code']
    link = f"{SITE_URL}/refer/{code}"
    total_refs = conn.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user['id'],)).fetchone()[0]
    conn.close()
    earnings = int(total_refs or 0) * 10
    html = f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family:sans-serif;background:#0f0f0f;color:white;text-align:center;padding:20px}}
    .card{{background:#1e1e1e;padding:20px;border-radius:15px;max-width:400px;margin:auto}}
    input{{width:90%;padding:12px;border-radius:8px;border:none;background:#2a2a2a;color:white;text-align:center}}
    button{{padding:12px 25px;background:#6c5ce7;color:white;border:none;border-radius:10px;font-weight:bold;margin-top:10px;cursor:pointer}}
    .stat{{display:flex;justify-content:space-around;margin-top:20px}}
    .stat div{{background:#2a2a2a;padding:15px;border-radius:10px;width:40%}}
    </style></head><body>
    <div class="card">
    <h2>🔥 Refer & Earn</h2>
    <p style="color:#aaa">Per Referral <b style="color:#00ff88">You Get 10Rs + Friend Gets 10Rs</b></p>
    <p>Your Referral Link:</p>
    <input id="rlink" value="{link}" readonly>
    <br><button onclick="navigator.clipboard.writeText(document.getElementById('rlink').value);alert('Copied!')">📋 Copy Link</button>
    <br><br>
    <a href="https://wa.me/?text={urllib.parse.quote(f'Join SD Tournament & Get 10Rs Bonus! {link}')}" target="_blank"><button style="background:#25D366">WhatsApp Share</button></a>
    <div class="stat">
    <div><h2>{total_refs}</h2><small>Total Referrals</small></div>
    <div><h2>₹{earnings}</h2><small>Total Earned</small></div>
    </div>
    <br><p>Code: <b>{code}</b></p>
    <br><a href="/" style="color:#6c5ce7;text-decoration:none">← Back Home</a>
    </div></body></html>
    """
    return html

@app.route('/notifications')
@nocache
def notifications_page():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    notifs = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (session['user_id'],)).fetchall()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session['user_id'],))
    conn.commit()
    conn.close()
    html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>body{font-family:sans-serif;background:#f9fafb;padding:15px} .card{background:white;padding:15px;border-radius:12px;margin-bottom:10px;border:1px solid #e5e7eb} .unread{border-left:4px solid #6c5ce7} h2{margin-bottom:15px}</style></head><body>"
    html += f"<h2>🔔 Notifications</h2><a href='/' style='color:#6c5ce7;text-decoration:none'>← Back Home</a><br><br>"
    if not notifs:
        html += "<div class='card'>No notifications yet!</div>"
    for n in notifs:
        d = dict(n)
        cls = "card unread" if d['is_read']==0 else "card"
        html += f"<div class='{cls}'><b>{d['title']}</b><br><small>{d['message']}</small><br><small style='color:#999'>{d['time']}</small></div>"
    html += "</body></html>"
    return html

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

# ... Add your other routes here (join, slots, etc.) - No change needed ...

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
