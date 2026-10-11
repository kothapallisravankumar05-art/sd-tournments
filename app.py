from flask import Flask, request, jsonify, session, redirect, render_template_string
import sqlite3

app = Flask(__name__)
app.secret_key = "sd-tournaments-secret-123"
DB = "database.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, balance INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'pending')""")
    try:
        c.execute("INSERT INTO users (username,password,balance) VALUES (?,?,?)", ("admin","admin123",0))
    except:
        pass
    conn.commit()
    conn.close()
init_db()

# --- COMMON STYLE ---
STYLE = """
<style>
body{font-family:Arial;background:#0f172a;color:white;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
.card{background:#1e293b;padding:25px;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.5);width:350px;text-align:center}
input{width:90%;padding:10px;margin:8px 0;border-radius:8px;border:none}
button{background:#22c55e;color:white;padding:10px 20px;border:none;border-radius:8px;cursor:pointer;width:95%;font-weight:bold}
button:hover{background:#16a34a}
a{color:#38bdf8;text-decoration:none}
h2{color:#facc15}
</style>
"""

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id,username FROM users WHERE username=? AND password=?", (u,p))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id']=user[0]
            session['username']=user[1]
            return redirect('/wallet')
        return STYLE + "<div class='card'><h3>Wrong password bro!</h3><a href='/login'>Try again</a></div>"
    return STYLE + """
    <div class='card'>
    <h2>SD TOURNAMENTS</h2>
    <h3>Login</h3>
    <form method='post'>
    <input name='username' placeholder='Username' required><br>
    <input type='password' name='password' placeholder='Password' required><br>
    <button type='submit'>Login</button>
    </form><br>
    <a href='/register'>Create Account</a>
    </div>
    """

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)", (u,p))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            conn.close()
            return STYLE + "<div class='card'><h3>Username already undi bro!</h3><a href='/register'>Back</a></div>"
    return STYLE + """
    <div class='card'>
    <h2>SD TOURNAMENTS</h2>
    <h3>Register</h3>
    <form method='post'>
    <input name='username' placeholder='Username' required><br>
    <input type='password' name='password' placeholder='Password' required><br>
    <button type='submit'>Register</button>
    </form><br>
    <a href='/login'>Already have account? Login</a>
    </div>
    """

@app.route('/wallet')
def wallet():
    if 'user_id' not in session:
        return redirect('/login')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    conn.close()
    return STYLE + f"""
    <div class='card' style='width:400px'>
    <h2>WALLET</h2>
    <p>Hi <b>{session.get('username')}</b> | Balance: <b style='color:#22c55e'>{bal} Rs</b></p>
    <p style='font-size:13px'>UPI: <b>yourupi@phonepe</b><br>Pay chesi UTR kottu</p>
    <input id='amt' type='number' placeholder='Amount Min 10'>
    <input id='utr' placeholder='Enter 12 digit UTR'>
    <button onclick='pay()'>Submit Payment</button>
    <p id='msg' style='color:#facc15'></p>
    <br><a href='/logout'>Logout</a> | <a href='/admin/payments'>Admin Panel</a>
    </div>
    <script>
    function pay(){{
        fetch('/verify_upi',{{
            method:'POST',
            headers:{{'Content-Type':'application/json'}},
            body:JSON.stringify({{amount:document.getElementById('amt').value, utr:document.getElementById('utr').value}})
        }}).then(r=>r.json()).then(d=>{{document.getElementById('msg').innerText=d.msg}})
    }}
    </script>
    """

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
        return jsonify({'ok':True,'msg':'Pending bro! Admin verify chesi add chestadu!'})
    except:
        conn.close()
        return jsonify({'ok':False,'msg':'Ee UTR already vadaru bro!'})

@app.route('/admin/payments')
def admin_payments():
    if 'user_id' not in session:
        return redirect('/login')
    if session.get('username')!='admin':
        return STYLE+"<div class='card'><h3>Admin only bro!</h3></div>"
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    html = STYLE + "<div class='card' style='width:500px'><h2>Pending Payments</h2>"
    if not rows:
        html += "<p>No pending bro!</p>"
    for r in rows:
        html += f"<p style='text-align:left;background:#0f172a;padding:8px;border-radius:8px'>ID:{r[0]} | UserID:{r[1]} | Rs:{r[2]} | UTR:{r[3]} <a href='/admin/approve/{r[0]}' style='color:#22c55e;font-weight:bold'>[APPROVE]</a></p>"
    html += "<br><a href='/wallet'>Back to Wallet</a></div>"
    return html

@app.route('/admin/approve/<int:pid>')
def approve_pay(pid):
    if 'user_id' not in session:
        return redirect('/login')
    if session.get('username')!='admin':
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
    return STYLE + "<div class='card'><h3>Approved! Money Added!</h3><a href='/admin/payments'>Back</a></div>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
