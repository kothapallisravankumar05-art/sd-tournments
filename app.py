from flask import Flask, render_template, request, redirect, session
import sqlite3, os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "sd_secret_2024"
DB = "sd.db"
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# INIT
conn = get_db()
conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password TEXT, balance INTEGER DEFAULT 0)")
conn.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, type TEXT, map TEXT, time TEXT, prize INTEGER, fee INTEGER, per_kill INTEGER DEFAULT 0, total INTEGER DEFAULT 10, joined INTEGER DEFAULT 0, room_id TEXT, room_pass TEXT, status TEXT DEFAULT 'UPCOMING', winner_id TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS joined (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tournament_id INTEGER)")
conn.execute("CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, user_id INTEGER, kills INTEGER, screenshot TEXT, status TEXT DEFAULT 'PENDING')")
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

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']; p = request.form['password']
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

@app.route('/join/<int:tid>')
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
        return "<h2 style='color:red;text-align:center;padding:50px'>❌ Already Submitted! Wait for admin.</h2><a href='/'>Home</a>"
    filename = ""
    if 'screenshot' in request.files:
        f = request.files['screenshot']
        if f.filename:
            filename = secure_filename(f"{mid}_{session['user_id']}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn.execute("INSERT INTO results (match_id,user_id,kills,screenshot,status) VALUES (?,?,?,?, 'PENDING')", (mid, session['user_id'], kills, filename))
    conn.commit()
    conn.close()
    return "<body style='background:#111;color:#00ff88;text-align:center;padding:50px;font-family:Arial'><h2>✅ Submitted with Screenshot!</h2><p>Kills: "+kills+"</p><a href='/' style='background:#00ff88;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:900'>Go Home</a></body>"

@app.route('/match_result/<int:mid>')
def match_result(mid):
    conn = get_db()
    t = conn.execute("SELECT * FROM tournaments WHERE id=?", (mid,)).fetchone()
    results = conn.execute("SELECT * FROM results WHERE match_id=? AND status='APPROVED' ORDER BY kills DESC", (mid,)).fetchall()
    final=[]
    for r in results:
        u = conn.execute("SELECT username FROM users WHERE id=?", (r['user_id'],)).fetchone()
        prize = (int(t['prize']) if t else 0) + (int(r['kills'])*int(t['per_kill'] or 0))
        final.append({'player_name': u['username'] if u else f"User {r['user_id']}", 'kills': r['kills'], 'winning': prize})
    conn.close()
    return render_template('match_result.html', t=t, results=final)

@app.route('/wallet')
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn=get_db(); user=conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone(); conn.close()
    return render_template('wallet.html', user=user)

@app.route('/admin', methods=['GET','POST'])
def admin():
    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_match':
            conn.execute("INSERT INTO tournaments (game,type,map,time,prize,fee,per_kill,total,status) VALUES (?,?,?,?,?,?,?,?,'UPCOMING')", (request.form.get('game'), request.form.get('type'), request.form.get('map'), request.form.get('time'), request.form.get('prize'), request.form.get('fee'), request.form.get('per_kill',0), request.form.get('total',10)))
        elif action == 'set_room':
            conn.execute("UPDATE tournaments SET room_id=?, room_pass=?, status='LIVE' WHERE id=?", (request.form.get('room_id'), request.form.get('room_pass'), request.form.get('mid')))
        elif action == 'approve_result':
            r = conn.execute("SELECT match_id,user_id,kills FROM results WHERE id=?", (request.form.get('result_id'),)).fetchone()
            if r:
                m = conn.execute("SELECT prize,per_kill FROM tournaments WHERE id=?", (r['match_id'],)).fetchone()
                total_win = int(m['prize'] or 0) + (int(r['kills'] or 0)*int(m['per_kill'] or 0))
                conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (total_win, r['user_id']))
                conn.execute("UPDATE results SET status='APPROVED' WHERE id=?", (request.form.get('result_id'),))
                conn.execute("UPDATE tournaments SET status='COMPLETED', winner_id=? WHERE id=?", (r['user_id'], r['match_id']))
        elif action == 'reject_result':
            conn.execute("UPDATE results SET status='REJECTED' WHERE id=?", (request.form.get('result_id'),))
        conn.commit()
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    results = conn.execute("SELECT * FROM results ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', tournaments=tournaments, results=results)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
