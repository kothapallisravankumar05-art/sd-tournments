from flask import Flask, request, jsonify, session, redirect, render_template_string
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "sd-tournaments-secret-123"
DB = "database.db"

# --- DB Setup ---
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        balance INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        utr TEXT UNIQUE,
        status TEXT DEFAULT 'pending'
    )""")
    # admin user create
    try:
        c.execute("INSERT INTO users (username,password,balance) VALUES (?,?,?)", ("admin","admin123",0))
    except:
        pass
    conn.commit()
    conn.close()

init_db()

# --- Home ---
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/wallet')
    return redirect('/login')

# --- Login ---
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id,username FROM users WHERE username=? AND password=?", (username,password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect('/wallet')
        return "Wrong username/password bro!"
    return render_template_string("""
    <h2>Login</h2>
    <form method='post'>
    Username: <input name='username'><br>
    Password: <input type='password' name='password'><br>
    <button type='submit'>Login</button>
    </form>
    <a href='/register'>Register</a>
    """)

# --- Register ---
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)", (username,password))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            conn.close()
            return "Username already undi bro!"
    return render_template_string("""
    <h2>Register</h2>
    <form method='post'>
    Username: <input name='username'><br>
    Password: <input type='password' name='password'><br>
    <button type='submit'>Register</button>
    </form>
    """)

# --- Wallet ---
@app.route('/wallet')
def wallet():
    if 'user_id' not in session:
        return redirect('/login')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    conn.close()
    return render_template_string(f"""
    <h2>Wallet - Balance: {bal} Rs</h2>
    <p>Username: {session.get('username')}</p>
    <p>UPI ID: yourupi@phonepe (example)</p>
    <input id='amt' placeholder='Amount min 10'>
    <input id='utr' placeholder='UTR Number'>
    <button onclick='pay()'>Submit UTR</button>
    <p id='msg'></p>
    <a href='/logout'>Logout</a> | <a href='/admin/payments'>Admin</a>
    <script>
    function pay(){{
        fetch('/verify_upi', {{
            method:'POST',
            headers:{{'Content-Type':'application/json'}},
            body:JSON.stringify({{amount:document.getElementById('amt').value, utr:document.getElementById('utr').value}})
        }}).then(r=>r.json()).then(d=>{{document.getElementById('msg').innerText=d.msg}})
    }}
    </script>
    """)

# --- SAFE Verify UPI - NO AUTO ADD ---
@app.route('/verify_upi', methods=['POST'])
def verify_upi():
    if 'user_id' not in session:
        return jsonify({'ok':False,'msg':'Login chey bro!'})
    data = request.get_json()
    amt = int(data.get('amount',0) or 0)
    utr = str(data.get('utr','')).strip()
    if amt < 10:
        return jsonify({'ok':False,'msg':'Min 10 Rs bro!'})
    if len(utr) < 5:
        return jsonify({'ok':False,'msg':'Valid UTR kotu bro!'})
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'pending')")
    try:
        c.execute("INSERT INTO payments (user_id,amount,utr,status) VALUES (?,?,?,?)", (session['user_id'],amt,utr,'pending'))
        conn.commit()
        conn.close()
        return jsonify({'ok':True,'msg':'Pending bro! Admin check chesi approve chestadu!'})
    except:
        conn.close()
        return jsonify({'ok':False,'msg':'Ee UTR already vadaru bro!'})

# --- Admin Pending List ---
@app.route('/admin/payments')
def admin_payments():
    if 'user_id' not in session:
        return redirect('/login')
    if session.get('username')!= 'admin':
        return "Admin only bro!"
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    html = "<h2>Pending Payments</h2>"
    if not rows:
        html += "No pending payments bro! All clear!"
    for r in rows:
        html += f"<p>ID:{r[0]} | User:{r[1]} | Amount:{r[2]} | UTR:{r[3]} <a href='/admin/approve/{r[0]}'><b>[Approve]</b></a></p>"
    html += "<br><a href='/wallet'>Back to Wallet</a>"
    return html

# --- Admin Approve ---
@app.route('/admin/approve/<int:pid>')
def approve_pay(pid):
    if 'user_id' not in session:
        return redirect('/login')
    if session.get('username')!= 'admin':
        return "Admin only"
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id,amount FROM payments WHERE id=?", (pid,))
    pay = c.fetchone()
    if pay:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (pay[1],pay[0]))
        c.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    return "Approved! <a href='/admin/payments'>Back</a>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
