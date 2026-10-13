from flask import Flask, render_template, request, redirect, session
import sqlite3, os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "sd_secret_2024"
DB = "sd.db"
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

# INIT ALL TABLES
conn = get_db()
conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password TEXT, balance INTEGER DEFAULT 0)")
conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT DEFAULT 'Bermuda', time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER)")
conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'PENDING', time TEXT)")
conn.commit()
conn.close()

@app.route('/')
def index():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    my_joined = conn.execute("SELECT tournament_id FROM joined WHERE user_id=?", (session['user_id'],)).fetchall()
    my_joined_ids = [r[0] for r in my_joined]
    conn.close()
    return render_template('index.html', tournaments=t, user=user, my_joined_ids=my_joined_ids)

@app.route('/health')
def health():
    return "OK", 200

@app.route('/register', methods=['GET','POST'])
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = (request.form.get('username') or request.form.get('phone') or "").strip()
        p = (request.form.get('password') or "").strip()
        if not u or not p:
            return "<h3>Phone/Username and Password kavali bro! <a href='/login'>Back</a></h3>"
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p)).fetchone()
        if user:
            session['user_id'] = user['id']
            conn.close()
            return redirect('/')
        conn.execute("INSERT INTO users (username,password,balance) VALUES (?,?,?)", (u,p,0))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        session['user_id'] = user['id']
        conn.close()
        return redirect('/')
    return render_template('login.html')

@app.route('/join/<int:tid>', methods=['GET','POST'])
def join(tid):
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    ex = conn.execute("SELECT * FROM joined WHERE user_id=? AND tournament_id=?", (session['user_id'], tid)).fetchone()
    if not ex:
        conn.execute("INSERT INTO joined (user_id,tournament_id) VALUES (?,?)", (session['user_id'], tid))
        conn.execute("UPDATE tournaments SET joined = joined + 1 WHERE id=?", (tid,))
        conn.commit()
    conn.close()
    return redirect('/')

@app.route('/submit_result', methods=['POST'])
def submit_result():
    if 'user_id' not in session: return redirect('/login')
    mid = request.form.get('match_id')
    kills = request.form.get('kills','0')
    conn = get_db()
    ex = conn.execute("SELECT * FROM results WHERE match_id=? AND user_id=?", (mid, session['user_id'])).fetchone()
    if ex:
        conn.close()
        return "<body style='background:#111;color:#ff4444;text-align:center;padding:50px;font-family:Arial'><h2>❌ Already Submitted!</h2><br><a href='/' style='background:#00ff88;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none'>Go Home</a></body>"
    filename = ""
    if 'screenshot' in request.files:
        f = request.files['screenshot']
        if f.filename:
            filename = secure_filename(f"{mid}_{session['user_id']}_{datetime.now().strftime('%H%M%S')}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn.execute("INSERT INTO results (match_id,user_id,kills,screenshot,status,time) VALUES (?,?,?,?, 'PENDING',?)", (mid, session['user_id'], kills, filename, datetime.now().strftime("%d/%m %H:%M")))
    conn.commit()
    conn.close()
    return "<body style='background:#111;color:#00ff88;text-align:center;padding:50px;font-family:Arial'><h2>✅ Submitted!</h2><p>Kills: "+kills+"</p><br><a href='/' style='background:#00ff88;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none'>Go Home</a></body>"

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

# --- FINAL FIXED WALLET - 100% WORKING ---
@app.route('/wallet', methods=['GET','POST'])
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn = get_db()
    if request.method == 'POST':
        amount = request.form.get('amount') or request.form.get('w_amount')
        utr = request.form.get('utr') or request.form.get('txn_id') or ""
        upi_id = request.form.get('upi_id')

        # Add Money
        if amount and utr:
            try:
                conn.execute("INSERT INTO payments (user_id, amount, utr, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(amount), utr, datetime.now().strftime("%d/%m %H:%M")))
                conn.commit()
                conn.close()
                return "<body style='background:#0a1628;color:#00ff88;text-align:center;padding:50px;font-family:Arial'><h2>✅ UTR Submitted!</h2><p>₹"+str(amount)+" - UTR:"+utr+"<br>Admin verify chesi add chestadu.</p><br><a href='/wallet' style='background:#00ff88;color:#000;padding:12px 25px;border-radius:10px;text-decoration:none;font-weight:900'>Back to Wallet</a></body>"
            except Exception as e:
                pass

        # Withdraw
        if amount and upi_id:
            user = conn.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],)).fetchone()
            if user and user['balance'] >= int(amount) and int(amount) >= 200:
                conn.execute("INSERT INTO withdrawals (user_id, amount, upi_id, status, time) VALUES (?,?,?, 'PENDING',?)", (session['user_id'], int(amount), upi_id, datetime.now().strftime("%d/%m %H:%M")))
                conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (int(amount), session['user_id']))
                conn.commit()
            conn.close()
            return redirect('/wallet')

    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    payments = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    withdrawals = conn.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    conn.close()
    return render_template('wallet.html', user=user, payments=payments, withdrawals=withdrawals, wallet=user['balance'] if user else 0)

@app.route('/admin', methods=['GET','POST'])
def admin():
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
        elif action == 'delete_tournament': conn.execute("DELETE FROM tournaments WHERE id=?", (request.form.get('tournament_id'),))
        elif action == 'approve_result':
            r = conn.execute("SELECT match_id,user_id,kills FROM results WHERE id=?", (request.form.get('result_id'),)).fetchone()
            if r:
                m = conn.execute("SELECT prize,per_kill FROM tournaments WHERE id=?", (r['match_id'],)).fetchone()
                total_win = int(m['prize'] or 0) + (int(r['kills'] or 0)*int(m['per_kill'] or 0))
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (total_win, r['user_id']))
                conn.execute("UPDATE results SET status='APPROVED' WHERE id=?", (request.form.get('result_id'),))
                conn.execute("UPDATE tournaments SET status='COMPLETED', winner_id=? WHERE id=?", (r['user_id'], r['match_id']))
        elif action == 'reject_result': conn.execute("UPDATE results SET status='REJECTED' WHERE id=?", (request.form.get('result_id'),))
        elif action == 'approve_payment':
            p = conn.execute("SELECT user_id,amount FROM payments WHERE id=?", (request.form.get('payment_id'),)).fetchone()
            if p:
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (p['amount'], p['user_id']))
                conn.execute("UPDATE payments SET status='APPROVED' WHERE id=?", (request.form.get('payment_id'),))
        elif action == 'reject_payment': conn.execute("UPDATE payments SET status='REJECTED' WHERE id=?", (request.form.get('payment_id'),))
        elif action == 'approve_withdrawal': conn.execute("UPDATE withdrawals SET status='APPROVED' WHERE id=?", (request.form.get('withdrawal_id'),))
        elif action == 'reject_withdrawal':
            w = conn.execute("SELECT user_id,amount FROM withdrawals WHERE id=?", (request.form.get('withdrawal_id'),)).fetchone()
            if w:
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (w['amount'], w['user_id']))
                conn.execute("UPDATE withdrawals SET status='REJECTED' WHERE id=?", (request.form.get('withdrawal_id'),))
        conn.commit()
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    pending_payments = conn.execute("SELECT * FROM payments WHERE status='PENDING' ORDER BY id DESC").fetchall()
    pending_withdrawals = conn.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()
    pending_results = conn.execute("SELECT results.*, users.username FROM results LEFT JOIN users ON results.user_id=users.id WHERE results.status='PENDING' ORDER BY results.id DESC").fetchall()
    conn.close()
    return render_template('admin.html', matches=tournaments, tournaments=tournaments, pending_payments=pending_payments, pending_withdrawals=pending_withdrawals, pending_results=pending_results)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/forgot')
def forgot():
    return "Contact Admin on WhatsApp!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
