from flask import Flask, render_template, request, redirect, session, make_response, jsonify, send_from_directory
import os, requests, random, string, sqlite3, traceback
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date, timedelta, timezone

# ===== IST TIMEZONE FIX - IMPORTANT FOR RENDER =====
IST = timezone(timedelta(hours=5, minutes=30))
def now_ist():
    return datetime.now(IST).replace(tzinfo=None) # naive IST for DB compatibility

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
SITE_URL = "https://sd-tournaments.onrender.com"
ADMIN_USER_ID = 1
ADMIN_PASSWORD = "NANI19"

TOURNAMENT_TEMPLATES = [
    {"game": "Clash Squad", "type": "Solo", "map": "Bermuda", "fee": 30, "prize": 40, "total": 2, "per_kill": 0},
    {"game": "Clash Squad", "type": "Duo", "map": "Bermuda", "fee": 30, "prize": 80, "total": 4, "per_kill": 0},
    {"game": "Clash Squad", "type": "Squad", "map": "Bermuda", "fee": 25, "prize": 150, "total": 8, "per_kill": 0},
    {"game": "Bermuda", "type": "Solo", "map": "Bermuda", "fee": 15, "prize": 1000, "total": 48, "per_kill": 8},
]

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
        c.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)", (user_id, amount, type_, desc, now_ist().strftime("%d/%m %H:%M")))
        c.commit()
        c.close()
    except Exception as e:
        print(f"add_txn error {e}")

def parse_match_time(time_str):
    if not time_str: return None
    # Support both 24h and 12h formats
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M", "%H:%M", "%I:%M %p", "%d/%m %H:%M", "%d/%m %I:%M %p"]
    # Clean string like "15/10 09:00 AM" -> try
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

@app.template_filter('time12')
def time12_filter(time_str):
    try:
        dt = parse_match_time(time_str)
        if dt:
            return dt.strftime("%d/%m %I:%M %p")
        return time_str
    except:
        return time_str

@app.template_filter('time12only')
def time12only_filter(time_str):
    try:
        dt = parse_match_time(time_str)
        if dt:
            return dt.strftime("%I:%M %p")
        return time_str
    except:
        return time_str

def auto_expire_matches():
    try:
        conn = get_db()
        tournaments = conn.execute("SELECT id, time, fee, status, room_id, total, joined FROM tournaments WHERE status='UPCOMING'").fetchall()
        now = now_ist()
        print(f"--- AUTO EXPIRE CHECK IST {now} - Found {len(tournaments)} UPCOMING ---")
        expired = []
        for t in tournaments:
            try:
                tid = t['id'] if 'id' in t.keys() else t[0]
                time_str = t['time'] if 'time' in t.keys() else t[1]
                fee = t['fee'] if 'fee' in t.keys() else t[2]
                status = str(t['status'] if 'status' in t.keys() else t[3]).upper()
                room = t['room_id'] if 'room_id' in t.keys() else t[4]
                total = t['total'] if 'total' in t.keys() else t[5]
                joined_c = t['joined'] if 'joined' in t.keys() else t[6]

                if room and str(room).strip()!= "":
                    continue

                t_time = parse_match_time(time_str)
                if not t_time:
                    print(f"Skip {tid}: can't parse {time_str}")
                    continue

                # Future match -> skip
                if t_time > now:
                    continue

                # Check if 60 mins passed
                if now <= (t_time + timedelta(minutes=60)):
                    continue

                # FULL CHECK - MAIN LOGIC YOU ASKED
                try: total_slots = int(total)
                except: total_slots = 0
                try: joined_slots = int(joined_c)
                except:
                    try:
                        joined_slots = conn.execute("SELECT COUNT(*) FROM joined WHERE tournament_id=?", (tid,)).fetchone()[0]
                    except: joined_slots = 0

                is_full = total_slots > 0 and joined_slots >= total_slots

                if is_full:
                    print(f"Match {tid} FULL {joined_slots}/{total_slots} -> MOVING TO LIVE, NOT DELETING")
                    conn.execute("UPDATE tournaments SET status='LIVE' WHERE id=?", (tid,))
                    conn.commit()
                    continue

                print(f"Match {tid} EXPIRED {time_str} {joined_slots}/{total_slots} -> MARK FOR DELETE")
                expired.append((tid, int(fee) if fee else 0))

            except Exception as e_inner:
                print(f"Expire inner error: {e_inner}")
                continue

        for tid, fee in expired:
            try:
                joined_users = conn.execute("SELECT user_id FROM joined WHERE tournament_id=?", (tid,)).fetchall()
                for ju in joined_users:
                    uid = ju['user_id'] if hasattr(ju, 'keys') and 'user_id' in ju.keys() else ju[0]
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (fee, uid))
                    conn.execute("INSERT INTO transactions (user_id, amount, type, description, time) VALUES (?,?,?,?,?)",
                                 (uid, fee, "REFUND", f"Match #{tid} Expired - Auto Refund Rs {fee}", now_ist().strftime("%d/%m %H:%M")))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                conn.execute("DELETE FROM results WHERE match_id=?", (tid,))
                conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
                conn.commit()
                print(f"DELETED {tid}")
            except Exception as e:
                print(f"Delete error {tid}: {e}")
                try: conn.rollback()
                except: pass
        conn.close()
        print(f"--- AUTO EXPIRE DONE - Deleted {len(expired)} ---")
    except Exception as e:
        print(f"auto_expire_matches error: {e}")
        traceback.print_exc()

def generate_daily_tournaments():
    try:
        conn = get_db()
        today = now_ist().strftime("%Y-%m-%d")
        cnt = conn.execute("SELECT COUNT(*) FROM tournaments WHERE time LIKE?", (f"{today}%",)).fetchone()[0]
        if cnt >= 15:
            conn.close()
            return False
        start = now_ist().replace(hour=9, minute=0, second=0, microsecond=0)
        end = now_ist().replace(hour=21, minute=0, second=0, microsecond=0)
        times = []
        cur = start
        while cur <= end:
            times.append(cur)
            cur += timedelta(minutes=40)
        template_idx = 0
        for t_time in times:
            tpl = TOURNAMENT_TEMPLATES[template_idx % len(TOURNAMENT_TEMPLATES)]
            time_str = t_time.strftime("%Y-%m-%d %H:%M")
            conn.execute("INSERT INTO tournaments (game,type,map,time,prize,fee,per_kill,total,joined,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (tpl["game"], tpl["type"], tpl["map"], time_str, tpl["prize"], tpl["fee"], tpl["per_kill"], tpl["total"], 0, "UPCOMING"))
            template_idx += 1
        conn.commit()
        conn.close()
        print(f" Generated {len(times)} Daily Tournaments for {today}!")
        return True
    except Exception as e:
        print(f"Generate error: {e}")
        traceback.print_exc()
        return False

def check_and_generate_daily():
    try:
        conn = get_db()
        today = now_ist().strftime("%Y-%m-%d")
        cnt = conn.execute("SELECT COUNT(*) FROM tournaments WHERE time LIKE?", (f"{today}%",)).fetchone()[0]
        conn.close()
        if cnt < 10:
            generate_daily_tournaments()
    except: pass

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
    except Exception as e:
        print(f"init_db error: {e}")
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

@app.route('/manifest.json')
def manifest_root(): return send_from_directory('static', 'manifest.json')
@app.route('/sw.js')
def sw_root(): return send_from_directory('static', 'sw.js')
@app.route('/icon-192.png')
def icon192(): return send_from_directory('static', 'icon-192.png')
@app.route('/icon-512.png')
def icon512(): return send_from_directory('static', 'icon-512.png')

@app.errorhandler(500)
def handle_500(e):
    tb = traceback.format_exc()
    print(tb)
    return f"<h2>500 Error</h2><pre>{tb}</pre>", 500

@app.route('/health')
def health(): return "OK", 200

@app.route('/admin', methods=['GET','POST'])
@nocache
def admin():
    if 'user_id' not in session: return redirect('/login')
    if int(session['user_id'])!= ADMIN_USER_ID: return "<h2>Access Denied - Admin Only!</h2><a href='/'>Go Home</a>"
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
            elif action == 'auto_generate':
                generate_daily_tournaments()
            elif action == 'generate_room_id':
                mid = request.form.get('mid')
                auto_room = ''.join(random.choices(string.digits, k=6))
                auto_pass = ''.join(random.choices(string.digits, k=4))
                conn.execute("UPDATE tournaments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (auto_room, auto_pass, mid))
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
                    conn.execute("INSERT INTO transactions (user_id,amount,type,description,time) VALUES (?,?,?,?,?)", (uid,fee,"REFUND",f"Tournament {tid} Cancelled Refund",now_ist().strftime("%d/%m %H:%M")))
                conn.execute("DELETE FROM joined WHERE tournament_id=?", (tid,))
                conn.execute("DELETE FROM results WHERE match_id=?", (tid,))
                conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
                conn.commit()
            elif action == 'approve_result':
                rid = request.form.get('result_id')
                res = conn.execute("SELECT * FROM results WHERE id=?", (rid,)).fetchone()
                if res:
                    tour = conn.execute("SELECT per_kill, prize FROM tournaments WHERE id=?", (res['match_id'],)).fetchone()
                    per_kill = int(tour['per_kill'] or 0) if tour else 0
                    prize = int(res['kills'] or 0) * per_kill
                    if prize>0:
                        conn.execute("UPDATE users SET balance=balance+?, total_wins=total_wins+? WHERE id=?", (prize,res['kills'],res['user_id']))
                        conn.execute("INSERT INTO transactions (user_id,amount,type,description,time) VALUES (?,?,?,?,?)", (res['user_id'],prize,"CREDIT",f"Kills Prize Match {res['match_id']} - {res['kills']} kills",now_ist().strftime("%d/%m %H:%M")))
                    conn.execute("UPDATE results SET status='APPROVED' WHERE id=?", (rid,))
                    conn.commit()
            elif action == 'reject_result':
                rid = request.form.get('result_id')
                conn.execute("UPDATE results SET status='REJECTED' WHERE id=?", (rid,))
                conn.commit()
            elif action == 'approve_payment':
                pid = request.form.get('payment_id')
                pay = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
                if pay and pay['status']=='PENDING':
                    conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (pay['amount'],pay['user_id']))
                    conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (pid,))
                    conn.execute("INSERT INTO transactions (user_id,amount,type,description,time) VALUES (?,?,?,?,?)", (pay['user_id'],pay['amount'],"CREDIT",f"Deposit Approved Rs {pay['amount']}",now_ist().strftime("%d/%m %H:%M")))
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
                    conn.execute("INSERT INTO transactions (user_id,amount,type,description,time) VALUES (?,?,?,?,?)", (wd['user_id'],wd['amount'],"REFUND",f"Withdraw Rejected Refund Rs {wd['amount']}",now_ist().strftime("%d/%m %H:%M")))
                    conn.commit()
        except Exception as e:
            print(f"Admin action error {e}")
            traceback.print_exc()
            try: conn.rollback()
            except: pass
        return redirect('/admin')
    try:
        matches = conn.execute("SELECT * FROM tournaments ORDER BY time ASC, id ASC").fetchall()
        pending_results = conn.execute("SELECT r.*, u.username FROM results r JOIN users u ON r.user_id=u.id WHERE r.status='PENDING' ORDER BY r.id DESC").fetchall()
        all_results = conn.execute("SELECT r.*, u.username FROM results r JOIN users u ON r.user_id=u.id WHERE r.status!='PENDING' ORDER BY r.id DESC LIMIT 20").fetchall()
        pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
        pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
    except:
        matches = conn.execute("SELECT * FROM tournaments ORDER BY time ASC, id ASC").fetchall()
        pending_results = conn.execute("SELECT * FROM results WHERE status='PENDING' ORDER BY id DESC").fetchall()
        all_results = conn.execute("SELECT * FROM results WHERE status!='PENDING' ORDER BY id DESC LIMIT 20").fetchall()
        pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
        pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', matches=matches, pending_results=pending_results, all_results=all_results, pending_payments=pending_payments, pending_withdrawals=pending_withdrawals)

@app.route('/')
@nocache
def index():
    if 'user_id' not in session: return redirect('/login')
    try:
        check_and_generate_daily()
        auto_expire_matches()
    except: pass
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY time ASC, id ASC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user: session.clear(); conn.close(); return redirect('/login')
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids, site_url=SITE_URL)

@app.route('/submit_result', methods=['POST'])
@nocache
def submit_result():
    if 'user_id' not in session: return redirect('/login')
    match_id = request.form.get('match_id')
    kills = request.form.get('kills')
    file = request.files.get('screenshot')
    filename = ""
    if file and file.filename:
        filename = secure_filename(f"{match_id}_{session['user_id']}_{now_ist().strftime('%H%M%S')}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn = get_db()
    conn.execute("INSERT INTO results (match_id, user_id, kills, screenshot, status, time) VALUES (?,?,?,?,?,?)", (match_id, session['user_id'], kills, filename, 'PENDING', now_ist().strftime("%d/%m %H:%M")))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/match_result/<int:tid>')
@nocache
def match_result(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    try:
        t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        results = conn.execute("SELECT r.*, u.username FROM results r JOIN users u ON r.user_id=u.id WHERE r.match_id=? ORDER BY CAST(r.kills AS INTEGER) DESC", (tid,)).fetchall()
    except:
        t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        results = conn.execute("SELECT * FROM results WHERE match_id=? ORDER BY CAST(kills AS INTEGER) DESC", (tid,)).fetchall()
    conn.close()
    return render_template('match_result.html', t=t, results=results)

@app.route('/matches')
@nocache
def matches_page():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY time ASC, id ASC").fetchall()
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

@app.route('/refer/<code>')
@nocache
def referral_page(code):
    clean_code = code.upper().strip()
    session['ref_code'] = clean_code
    session.permanent = True
    return redirect('/register')

@app.route('/r/<code>')
@nocache
def referral_short(code): return redirect(f'/refer/{code.upper().strip()}')

@app.route('/refer')
@nocache
def refer_empty(): return redirect('/register')

@app.route('/account')
@nocache
def account():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    played = conn.execute("SELECT COUNT(*) FROM joined WHERE user_id=?", (session['user_id'],)).fetchone()[0]
    conn.close()
    return render_template('account.html', user=user, played=played, site_url=SITE_URL)

@app.route('/leaderboard')
@nocache
def leaderboard():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    top = conn.execute("SELECT id, username, total_wins, balance FROM users ORDER BY total_wins DESC, balance DESC LIMIT 20").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('leaderboard.html', top=top, user=user)

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
                    add_txn(ref_user['id'], 20, "CREDIT", f"Referral Bonus for {username}")
                    add_txn(user['id'], 20, "CREDIT", f"Welcome Bonus - Referred by {session['ref_code']}")
            session.permanent = True
            session['user_id'] = user['id']
            session.pop('ref_code', None)
            conn.close()
            return redirect('/')
        except Exception as e:
            try: conn.close()
            except: pass
            return render_template('register.html', error=f"Username exists bro! {e}")
    ref = session.get('ref_code', '')
    return render_template('register.html', ref_code=ref, site_url=SITE_URL)

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
                    conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], amt_i, utr.strip().upper(), now_ist().strftime("%d/%m %H:%M")))
                    conn.commit()
            elif upi_id and amount:
                amt = int(float(amount))
                user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
                if user and int(user['balance'] or 0) >= amt and amt >= 200:
                    conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?,'PENDING',?)", (session['user_id'], amt, upi_id.strip(), now_ist().strftime("%d/%m %H:%M")))
                    conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (amt, session['user_id']))
                    conn.commit()
        except Exception as e:
            print(f"Wallet error: {e}")
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

@app.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect('/login'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
