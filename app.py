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

# ===== PWA FIX - START - 100% INSTALL FIX =====
@app.route('/static/manifest.json')
def pwa_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/static/sw.js')
def pwa_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def pwa_manifest_root():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def pwa_sw_root():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/static/icon-192.png')
def pwa_icon_192():
    return send_from_directory('static', 'icon-192.png', mimetype='image/png')

@app.route('/static/icon-512.png')
def pwa_icon_512():
    return send_from_directory('static', 'icon-512.png', mimetype='image/png')

@app.route('/static/icon.png')
def pwa_icon():
    return send_from_directory('static', 'icon.png', mimetype='image/png')
# ===== PWA FIX - END =====

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
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id SERIAL PRIMARY KEY, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, first_prize INTEGER DEFAULT 0, second_prize INTEGER DEFAULT 0, third_prize INTEGER DEFAULT 0, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
            conn.execute("CREATE TABLE IF NOT EXISTS joined (id SERIAL PRIMARY KEY, user_id INTEGER, tournament_id INTEGER, slot_no INTEGER DEFAULT 0, game_id TEXT DEFAULT '', game_name TEXT DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, description TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, match_id INTEGER, user_id INTEGER, kills INTEGER, status TEXT DEFAULT 'PENDING', screenshot TEXT, time TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER, title TEXT, message TEXT, is_read INTEGER DEFAULT 0, time TEXT)")
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, phone TEXT, balance INTEGER DEFAULT 0, referral_code TEXT UNIQUE, referred_by INTEGER DEFAULT 0, total_wins INTEGER DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS tournments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, first_prize INTEGER DEFAULT 0, second_prize INTEGER DEFAULT 0, third_prize INTEGER DEFAULT 0, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING')")
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

def migrate_prizes():
    conn = get_db()
    try:
        for q in [
            "ALTER TABLE tournments ADD COLUMN first_prize INTEGER DEFAULT 0",
            "ALTER TABLE tournments ADD COLUMN second_prize INTEGER DEFAULT 0",
            "ALTER TABLE tournments ADD COLUMN third_prize INTEGER DEFAULT 0"
        ]:
            try: conn.execute(q)
            except: pass
        conn.commit()
    except: pass
    finally: conn.close()

init_db()
migrate_game_id()
migrate_prizes()

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
        types = [("Free Fire","Clash Squad",30,50,2),("Free Fire","Duo",30,100,4),("Free Fire","Squad",25,180,8),("Free Fire","Solo",15,1000,48)]
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
            conn.execute("INSERT INTO tournments (game,type,map,time,prize,first_prize,second_prize,third_prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'UPCOMING')",
                         (g,t_type,'Bermuda',full_time,prize,prize,0,0,fee,per_kill,total))
            created+=1
        conn.commit()
        return created
    except Exception as e:
        print(f"Gen Error {e}")
        traceback.print_exc()
        return 0

def cleanup_expired_matches(conn):
    try:
        now_str = now_ist().strftime("%Y-%m-%d %H:%M")
        one_hour_ago = (now_ist() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        expired_empty = conn.execute("SELECT id FROM tournments WHERE time < ? AND joined=0", (now_str,)).fetchall()
        for tour in expired_empty:
            try:
                tid = tour['id'] if 'id' in tour else tour[0]
                conn.execute("DELETE FROM tournments WHERE id=?", (tid,))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                print(f"🗑️ Deleted 0 Joined Match: {tid}")
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
        conn.execute("DELETE FROM tournments WHERE time < ? AND joined=0", (now_str,))
        conn.execute("UPDATE tournments SET status='COMPLETED' WHERE time < ? AND joined>0 AND status IN ('UPCOMING','LIVE')", (one_hour_ago,))
        conn.commit()
        conn.close()
        return f"<h1> Cleaned - 0 Joined Deleted<br><a href='/'>Home</a></h1>"
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
        fp = d.get('first_prize', d.get('prize',0))
        sp = d.get('second_prize',0)
        tp = d.get('third_prize',0)
        html += f"{d['time']} - {d['type']} - {d['status']} - {d['joined']}/{d['total']} - 1st:{fp} 2nd:{sp} 3rd:{tp}<br>"
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

@app.route('/api/notifications')
@nocache
def api_notifications():
    if 'user_id' not in session:
        return jsonify([])
    conn = get_db()
    notifs = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 20", (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifs])

@app.route('/api/notifications/count')
@nocache
def api_notif_count():
    if 'user_id' not in session:
        return jsonify({"count":0})
    conn = get_db()
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (session['user_id'],)).fetchone()[0]
    except:
        cnt = 0
    conn.close()
    return jsonify({"count": int(cnt or 0)})

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
    amount = request.args.get('amount', '20')
    try: amt = int(float(amount))
    except: amt = 20
    upi_link = f"upi://pay?pa={MY_UPI_ID}&pn=SDTournament&am={amt}&cu=INR"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(upi_link)}"
    return jsonify({"qr_url": qr_url, "upi_link": upi_link})

@app.route('/verify_upi', methods=['POST'])
@nocache
def verify_upi():
    if 'user_id' not in session: return jsonify({"ok": False, "msg": "Login require!"}), 401
    conn = None
    try:
        data = request.get_json() if request.is_json else request.form
        utr = (data.get('utr') or "").strip().upper()
        amount = data.get('amount') or 0
        if not utr or len(utr) < 6: return jsonify({"ok": False, "msg": "Enter Valid UTR !"}), 400
        conn = get_db()
        dup = conn.execute("SELECT id FROM payments WHERE utr=?", (utr,)).fetchone()
        if dup:
            conn.close()
            return jsonify({"ok": False, "msg": "UTR Used Enter Valid Utr !"}), 400
        amt_i = int(float(amount))
        conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt_i, utr, now_ist().strftime("%d/%m %H:%M")))
        conn.commit(); conn.close()
        return jsonify({"ok": True, "msg": f" ₹{amt_i} Submitted!"})
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
        if len(phone) < 4: return render_template('forgot.html', error="Enter Phone/Username !")
        if len(new_pass) < 4: return render_template('forgot.html', error="Password Min 4 Characters!")
        if new_pass != confirm_pass: return render_template('forgot.html', error="Incorrect Password!")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        if not user: user = conn.execute("SELECT * FROM users WHERE username=?", (phone,)).fetchone()
        if not user:
            conn.close()
            return render_template('forgot.html', error="Account Not Found!")
        conn.execute("UPDATE users SET password=? WHERE id=?", (new_pass, user['id']))
        conn.commit(); conn.close()
        return render_template('forgot.html', success=" Password Changed!")
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
            my_slots = conn.execute("SELECT slot_no FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchall()
            my_slot_list = [int(r[0]) for r in my_slots]
        except:
            taken_slots = {}
            my_slot_list = []
        conn.close()
        return render_template('slots.html', tour=tour, t=tour, user=user, taken_slots=taken_slots, my_slot_list=my_slot_list)
    except Exception as e:
        print(f"slots error {e}")
        traceback.print_exc()
        return f"Slots Error: {e} - <a href='/'>Home</a>"

@app.route('/confirm_join/<int:tid>')
@nocache
def confirm_join(tid):
    try:
        if 'user_id' not in session: return redirect('/login')
        slot_param = request.args.get('slot_no') or request.args.get('slot') or request.args.get('slots') or "1"
        slot_list = []
        for part in str(slot_param).replace(' ', '').split(','):
            try:
                if part.strip(): slot_list.append(int(part.strip()))
            except: pass
        if not slot_list: slot_list = [1]
        conn = get_db()
        tour = conn.execute("SELECT * FROM tournments WHERE id=?", (tid,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        if not tour: return redirect('/')
        if not user: return redirect('/login')
        return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_list[0], slot_nos=slot_list, slot_nos_str=",".join(map(str, slot_list)), total_fee=int(tour['fee'] or 0) * len(slot_list))
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
        if request.method == 'GET':
            slot_param = request.args.get('slot') or request.args.get('slot_no') or request.args.get('slots') or "1"
            slot_list = []
            for part in str(slot_param).replace(' ', '').split(','):
                try:
                    if part.strip(): slot_list.append(int(part.strip()))
                except: pass
            if not slot_list: slot_list = [1]
            conn.close()
            return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_list[0], slot_nos=slot_list, slot_nos_str=",".join(map(str, slot_list)), total_fee=int(tour['fee'] or 0) * len(slot_list))
        
        game_id = (request.form.get('game_id') or '').strip()
        game_name = (request.form.get('game_name') or '').strip()
        slot_params = []
        for key in ['slot_no', 'slot_nos', 'slots', 'slot_nos_str']:
            vals = request.form.getlist(key)
            for v in vals:
                if v:
                    for part in str(v).replace(' ', '').split(','):
                        try:
                            if part.strip(): slot_params.append(int(part.strip()))
                        except: pass
        seen = set()
        slot_nos = []
        for s in slot_params:
            if s not in seen:
                seen.add(s)
                slot_nos.append(s)
        if not slot_nos: slot_nos = [1]

        if not game_id or not game_name:
            conn.close()
            return render_template('join_confirm.html', t=tour, tour=tour, user=user, slot_no=slot_nos[0], slot_nos=slot_nos, slot_nos_str=",".join(map(str, slot_nos)), total_fee=int(tour['fee'] or 0) * len(slot_nos), error="Game ID & Game Name Required !")

        fee_per = int(tour['fee'] or 0)
        total_fee_needed = fee_per * len(slot_nos)

        if int(user['balance'] or 0) < total_fee_needed:
            conn.close()
            return redirect('/wallet')

        already_taken = []
        for sn in slot_nos:
            taken = conn.execute("SELECT id FROM joined WHERE tournament_id=? AND slot_no=?", (tid, sn)).fetchone()
            if taken:
                already_taken.append(sn)
        if already_taken:
            conn.close()
            return f"<h3>Slot {already_taken} already taken! <a href='/slots/{tid}'>Choose Other Slots</a></h3>"

        for slot_no in slot_nos:
            try:
                conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no, game_id, game_name) VALUES (?,?,?,?,?)", (session['user_id'], tid, slot_no, game_id, game_name))
            except:
                conn.execute("INSERT INTO joined (user_id, tournament_id, slot_no) VALUES (?,?,?)", (session['user_id'], tid, slot_no))

        conn.execute("UPDATE tournments SET joined=joined+? WHERE id=?", (len(slot_nos), tid))
        conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (total_fee_needed, session['user_id']))
        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (session['user_id'], total_fee_needed, 'DEBIT', f"Join T{tid} Slots {','.join(map(str, slot_nos))}", now_ist().strftime("%d/%m %H:%M")))
        create_notification(conn, session['user_id'], " Joined!", f"You joined {tour['type']} match at {tour['time']} - {len(slot_nos)} slots ({','.join(map(str, slot_nos))})!")
        conn.commit()
        conn.close()
        return redirect('/my_tournments')
    except Exception as e:
        print(f"join error {e}")
        traceback.print_exc()
        try: conn.close()
        except: pass
        return f"Join Error: {e} - <a href='/slots/{tid}'>Try Again</a>"

@app.route('/my_tournments')
@app.route('/my_tournaments')
@app.route('/my_matches')
@app.route('/my_match')
@app.route('/mymatches')
@app.route('/my-matches')
@app.route('/matches')
@app.route('/match_history')
@nocache
def my_tournments():
    if 'user_id' not in session: return redirect('/login')
    conn = None
    try:
        conn = get_db()
        data = conn.execute("SELECT j.*, t.game, t.type, t.time, t.map, t.prize, t.first_prize, t.second_prize, t.third_prize, t.fee, t.per_kill, t.status, t.room_id, t.room_pass FROM joined j JOIN tournments t ON j.tournament_id=t.id WHERE j.user_id=? ORDER BY j.id DESC", (session['user_id'],)).fetchall()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        conn.close()
        try:
            return render_template('my_tournaments.html', joined=data, user=user)
        except:
            return render_template('my_tournments.html', joined=data, user=user)
    except Exception as e:
        print(f"my_tournments error {e}")
        traceback.print_exc()
        try:
            if conn: conn.close()
        except: pass
        return f"<h3>My Tournaments Error: {e}</h3><a href='/'>Home</a>"

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
    match_id = request.form.get('match_id') or request.form.get('tournament_id') or 0
    try: match_id = int(match_id)
    except: return f"<h3>Invalid Match ID <a href='/my_tournments'>Back</a></h3>"
    conn = get_db()
    try:
        joined = conn.execute("SELECT id FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], match_id)).fetchone()
        if not joined:
            conn.close()
            return f"<h3>⚠️ Not Join! <a href='/'>Home</a></h3>"
        fname = ""
        if 'screenshot' in request.files:
            f = request.files['screenshot']
            if f and f.filename and f.filename.strip() != '':
                ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else 'jpg'
                if ext not in ['jpg','jpeg','png','webp','bmp']: ext='jpg'
                fname = f"{session['user_id']}_{match_id}_{random.randint(1000,99999)}.{ext}"
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                os.makedirs("static/uploads", exist_ok=True)
                f.save(os.path.join(UPLOAD_FOLDER, fname))
        if not fname:
            ex = conn.execute("SELECT screenshot FROM results WHERE match_id=? AND user_id=?", (match_id, session['user_id'])).fetchone()
            if ex and ex['screenshot']:
                fname = ex['screenshot']
            else:
                conn.close()
                return f"<h3>⚠️ Select Screenshot ! <a href='/my_tournments'>Back</a></h3>"
        existing = conn.execute("SELECT id FROM results WHERE match_id=? AND user_id=?", (match_id, session['user_id'])).fetchone()
        if existing:
            conn.execute("UPDATE results SET kills=0, screenshot=?, status='PENDING', time=? WHERE id=?", (fname, now_ist().strftime("%d/%m %H:%M"), existing['id']))
        else:
            conn.execute("INSERT INTO results (match_id,user_id,kills,status,screenshot,time) VALUES (?,?,?,?,?,?)",(match_id,session['user_id'],0,'PENDING',fname,now_ist().strftime("%d/%m %H:%M")))
        conn.commit()
        conn.close()
        return redirect(f'/match_result/{match_id}')
    except Exception as e:
        print(f"Submit error {e}")
        traceback.print_exc()
        try: conn.close()
        except: pass
        return f"<h3>Error {e} <a href='/my_tournments'>Back</a></h3>"

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
                first_prize = int(request.form.get('first_prize') or prize)
                second_prize = int(request.form.get('second_prize') or 0)
                third_prize = int(request.form.get('third_prize') or 0)
                total = int(request.form.get('total_slots') or 8); per_kill = int(request.form.get('per_kill') or 0)
                time_str = request.form.get('time') or now_ist().strftime("%Y-%m-%d %H:%M")
                conn.execute("INSERT INTO tournments (game,type,map,time,prize,first_prize,second_prize,third_prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'UPCOMING')",(game, typ, 'Bermuda', time_str, prize, first_prize, second_prize, third_prize, fee, per_kill, total)); conn.commit()
            elif action == 'set_room':
                mid = request.form.get('mid'); room_id = request.form.get('room_id'); room_pass = request.form.get('room_pass')
                if mid: 
                    conn.execute("UPDATE tournments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (room_id, room_pass, int(mid)))
                    joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (int(mid),)).fetchall()
                    for ju in joined_users:
                        create_notification(conn, ju['user_id'] if isinstance(ju, dict) or hasattr(ju, '__getitem__') else ju[0], "🔴 Room Ready!", f"Match {mid} Room ID: {room_id} Pass: {room_pass} - Join Now!")
                    conn.commit()
            elif action == 'generate_room_id':
                mid = request.form.get('mid')
                if mid:
                    rid = ''.join(random.choices(string.digits, k=6)); rpass = ''.join(random.choices(string.digits, k=4))
                    conn.execute("UPDATE tournments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (rid, rpass, int(mid)))
                    joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (int(mid),)).fetchall()
                    for ju in joined_users:
                        uid = ju['user_id'] if 'user_id' in ju else ju[0]
                        create_notification(conn, int(uid), "🔴 Room Ready!", f"Match {mid} - ID:{rid} Pass:{rpass}")
                    conn.commit()
            elif action == 'approve_result':
                rid = request.form.get('result_id')
                custom_kills = request.form.get('custom_kills') or request.form.get('new_kills') or "0"
                if rid:
                    try:
                        k = int(custom_kills)
                        if k<0: k=0
                        if k>30: k=30
                        conn.execute("UPDATE results SET kills=?, status='APPROVED' WHERE id=?", (k, int(rid)))
                        conn.commit()
                    except: pass
            elif action == 'update_kills':
                rid = request.form.get('result_id')
                new_kills = request.form.get('new_kills') or "0"
                if rid:
                    try:
                        k = int(new_kills)
                        if k<0: k=0
                        if k>30: k=30
                        conn.execute("UPDATE results SET kills=? WHERE id=?", (k, int(rid)))
                        conn.commit()
                    except: pass
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
                prize_type = request.form.get('prize_type') or 'first'
                custom_kills = request.form.get('custom_kills') or "0"
                if mid and winner_id:
                    tour = conn.execute("SELECT prize, first_prize, second_prize, third_prize, per_kill FROM tournments WHERE id=?", (int(mid),)).fetchone()
                    prize_map = {
                        'first': int(tour['first_prize'] if tour and tour['first_prize'] else tour['prize'] if tour else 0),
                        'second': int(tour['second_prize'] if tour and tour['second_prize'] else 0),
                        'third': int(tour['third_prize'] if tour and tour['third_prize'] else 0)
                    }
                    prize = prize_map.get(prize_type, prize_map['first'])
                    per_kill = int(tour['per_kill'] if tour and tour['per_kill'] else 0)
                    try:
                        kills = int(custom_kills)
                        if kills<0: kills=0
                        if kills>30: kills=30
                    except: kills=0
                    conn.execute("UPDATE results SET kills=?, status='APPROVED' WHERE match_id=? AND user_id=?", (kills, int(mid), int(winner_id)))
                    total_prize = prize + (per_kill * kills)
                    if total_prize > 0:
                        conn.execute("UPDATE users SET balance=balance+?, total_wins=total_wins+1 WHERE id=?", (total_prize, int(winner_id)))
                        conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (int(winner_id), total_prize, 'CREDIT', f'Won Match {mid} {prize_type} Prize {total_prize} ({kills}K)', now_ist().strftime("%d/%m %H:%M")))
                        create_notification(conn, int(winner_id), "🏆 You Won!", f"Match {mid} - {prize_type} Prize ₹{total_prize} added! {kills} kills")
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
                        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(p['amount']), int(p['user_id'])))
                        create_notification(conn, int(p['user_id']), " Payment Approved", f"₹{p['amount']} added to wallet!")
                        conn.commit()
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
