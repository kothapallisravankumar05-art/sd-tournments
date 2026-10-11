from flask import Flask, request, jsonify, session, redirect
import sqlite3, random

app = Flask(__name__)
app.secret_key = "sd-tournaments-final-2024"
DB = "database.db"

def get_db():
    return sqlite3.connect(DB)

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, phone TEXT, password TEXT, balance INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'pending')")
    c.execute("CREATE TABLE IF NOT EXISTS tournaments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, game TEXT, entry_fee INTEGER, prize INTEGER, slots INTEGER)")
    # default admin
    try:
        c.execute("INSERT INTO users (username,phone,password,balance) VALUES ('admin','9999999999','admin123',0)")
    except:
        pass
    # default tournaments
    c.execute("SELECT COUNT(*) FROM tournaments")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO tournaments (name,game,entry_fee,prize,slots) VALUES ('Free Fire Solo','Free Fire',20,200,100)")
        c.execute("INSERT INTO tournaments (name,game,entry_fee,prize,slots) VALUES ('BGMI Squad','BGMI',100,1000,25)")
        c.execute("INSERT INTO tournaments (name,game,entry_fee,prize,slots) VALUES ('CODM Battle','CODM',50,500,50)")
    conn.commit()
    conn.close()

init_db()

STYLE = """
<style>
body{font-family:Arial;background:#0a0e1a;color:#fff;margin:0;padding:0;display:flex;justify-content:center}
.card{background:#1e293b;padding:20px;border-radius:15px;width:90%;max-width:400px;margin:20px auto;text-align:center;box-shadow:0 0 20px #000}
input{width:92%;padding:12px;margin:8px 0;border-radius:8px;border:none;background:#0f172a;color:#fff}
button{background:#facc15;color:#000;padding:12px;border:none;border-radius:8px;width:96%;font-weight:bold;cursor:pointer;margin-top:10px}
button:hover{background:#eab308}
a{color:#38bdf8;text-decoration:none;font-size:14px}
h2{color:#facc15;margin:5px}
.tbox{background:#0f172a;padding:12px;border-radius:10px;margin:10px 0;text-align:left;border-left:4px solid #facc15}
.small{font-size:12px;color:#94a3b8}
</style>
"""

# ---------- HOME / TOURNAMENTS ----------
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    c.execute("SELECT * FROM tournaments")
    tourns = c.fetchall()
    conn.close()

    html = STYLE + f"<div class='card'><h2>SD TOURNAMENTS 🏆</h2><p>Hi <b>{session.get('username')}</b> | Wallet: <b style='color:#22c55e'>{bal} Rs</b></p>"
    for t in tourns:
        html += f"<div class='tbox'><b>{t[1]}</b> <span class='small'>({t[2]})</span><br>Entry: {t[3]} Rs | Prize: {t[4]} Rs | Slots: {t[5]}<br><button onclick=\"joinT({t[0]},{t[3]})\">Join Now</button></div>"
    html += f"<br><a href='/wallet'>💰 Wallet / Add Money</a> | <a href='/logout'>Logout</a>"
    if session.get('username') == 'admin':
        html += "<br><br><a href='/admin'>🔧 Admin Panel</a>"
    html += "<p id='msg' style='color:#facc15'></p></div>"
    html += """
    <script>
    function joinT(id,fee){
        if(confirm('Join this tournament for '+fee+' Rs?')){
            fetch('/join/'+id).then(r=>r.json()).then(d=>{document.getElementById('msg').innerText=d.msg; if(d.ok) location.reload();})
        }
    }
    </script>
    """
    return html

@app.route('/join/<int:tid>')
def join_tournament(tid):
    if 'user_id' not in session:
        return jsonify(ok=False, msg='Login chey bro!')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT entry_fee FROM tournaments WHERE id=?", (tid,))
    fee = c.fetchone()
    if not fee:
        conn.close()
        return jsonify(ok=False, msg='Tournament ledu!')
    fee = fee[0]
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    if bal < fee:
        conn.close()
        return jsonify(ok=False, msg=f'Balance takkuva bro! Need {fee} Rs. Wallet lo add chey!')
    c.execute("UPDATE users SET balance=balance-? WHERE id=?", (fee, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify(ok=True, msg=f'Joined! {fee} Rs deducted!')

# ---------- LOGIN ----------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, username FROM users WHERE username=? AND password=?", (u,p))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id']=user[0]
            session['username']=user[1]
            return redirect('/')
        return STYLE + "<div class='card'><h3>Wrong username/password!</h3><a href='/login'>Try again</a></div>"
    return STYLE + "<div class='card'><h2>SD TOURNAMENTS</h2><h3>Login</h3><form method='post'><input name='username' placeholder='Username' required><input type='password' name='password' placeholder='Password' required><button>Login</button></form><br><a href='/register'>New? Register + OTP</a></div>"

# ---------- REGISTER + OTP ----------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        ph = request.form.get('phone')
        p = request.form.get('password')
        otp = str(random.randint(1000,9999))
        session['reg_data'] = {'username':u, 'phone':ph, 'password':p}
        session['otp'] = otp
        # DEMO lo OTP screen paina chupistam, real lo SMS velthundi
        return STYLE + f"<div class='card'><h2>OTP Verification</h2><p class='small'>OTP sent to {ph}</p><p style='color:#22c55e'>DEMO OTP: <b>{otp}</b></p><form method='post' action='/verify_otp'><input name='otp' placeholder='Enter 4 digit OTP' required><button>Verify OTP</button></form></div>"
    return STYLE + "<div class='card'><h2>Register</h2><form method='post'><input name='username' placeholder='Username' required><input name='phone' placeholder='Phone Number' required><input type='password' name='password' placeholder='Password' required><button>Get OTP</button></form><br><a href='/login'>Already have account?</a></div>"

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form.get('otp')
    if user_otp == session.get('otp'):
        data = session.get('reg_data')
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username,phone,password) VALUES (?,?,?)", (data['username'], data['phone'], data['password']))
            conn.commit()
            conn.close()
            session.pop('otp', None)
            session.pop('reg_data', None)
            return STYLE + "<div class='card'><h3>Registered Success bro! ✅</h3><a href='/login'>Login Now</a></div>"
        except:
            conn.close()
            return STYLE + "<div class='card'><h3>Username already undi!</h3><a href='/register'>Back</a></div>"
    else:
        return STYLE + "<div class='card'><h3>Wrong OTP bro!</h3><a href='/register'>Try again</a></div>"

# ---------- WALLET ----------
@app.route('/wallet')
def wallet():
    if 'user_id' not in session:
        return redirect('/login')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    conn.close()
    return STYLE + f"<div class='card'><h2>Wallet 💰</h2><p>Balance: <b style='color:#22c55e'>{bal} Rs</b></p><p class='small'>UPI ID: sd-tournament@phonepe<br>1. UPI lo pay chey<br>2. UTR copy chesi kinda pettu</p><input id='amt' type='number' placeholder='Amount (Min 10)'><input id='utr' placeholder='12 Digit UTR'><button onclick='pay()'>Submit for Admin Verify</button><p id='msg' style='color:#facc15'></p><br><a href='/'>Back to Tournaments</a></div><script>function pay(){{fetch('/verify_upi',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{amount:document.getElementById('amt').value,utr:document.getElementById('utr').value}})}}).then(r=>r.json()).then(d=>{{document.getElementById('msg').innerText=d.msg}})}}<\/script>"

@app.route('/verify_upi', methods=['POST'])
def verify_upi():
    if 'user_id' not in session:
        return jsonify(ok=False, msg='Login chey!')
    data = request.get_json()
    try:
        amt = int(data.get('amount',0))
    except:
        amt = 0
    utr = str(data.get('utr','')).strip()
    if amt < 10:
        return jsonify(ok=False, msg='Min 10 Rs bro!')
    if len(utr) < 6:
        return jsonify(ok=False, msg='Valid UTR pettu bro!')
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO payments (user_id,amount,utr,status) VALUES (?,?,?,?)", (session['user_id'], amt, utr, 'pending'))
        conn.commit()
        conn.close()
        return jsonify(ok=True, msg='Pending bro! Admin 5 mins lo approve chestadu!')
    except:
        conn.close()
        return jsonify(ok=False, msg='Ee UTR already use chesav bro!')

# ---------- ADMIN ----------
@app.route('/admin')
def admin_home():
    if 'user_id' not in session or session.get('username')!= 'admin':
        return STYLE + "<div class='card'><h3>Admin only bro!</h3><a href='/'>Home</a></div>"
    return STYLE + "<div class='card'><h2>Admin Panel 🔧</h2><a href='/admin/payments'><button>Pending Payments</button></a><br><br><a href='/admin/tournaments'><button>Add Tournament</button></a><br><br><a href='/'>Back to Home</a></div>"

@app.route('/admin/payments')
def admin_payments():
    if 'user_id' not in session or session.get('username')!= 'admin':
        return redirect('/login')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT p.id, u.username, p.amount, p.utr FROM payments p JOIN users u ON p.user_id=u.id WHERE p.status='pending'")
    rows = c.fetchall()
    conn.close()
    html = STYLE + "<div class='card' style='max-width:500px'><h2>Pending Payments</h2>"
    if not rows:
        html += "<p>No pending bro!</p>"
    for r in rows:
        html += f"<div class='tbox'>ID:{r[0]} | User:{r[1]}<br>Amount: {r[2]} Rs<br>UTR: {r[3]}<br><a href='/admin/approve/{r[0]}' style='color:#22c55e;font-weight:bold'>✅ APPROVE</a> | <a href='/admin/reject/{r[0]}' style='color:red'>❌ REJECT</a></div>"
    html += "<br><a href='/admin'>Back</a></div>"
    return html

@app.route('/admin/approve/<int:pid>')
def approve_pay(pid):
    if 'user_id' not in session or session.get('username')!= 'admin':
        return "Admin only"
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM payments WHERE id=?", (pid,))
    pay = c.fetchone()
    if pay:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (pay[1], pay[0]))
        c.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    return STYLE + "<div class='card'><h3>Approved! ✅ Money Added!</h3><a href='/admin/payments'>Back</a></div>"

@app.route('/admin/reject/<int:pid>')
def reject_pay(pid):
    if 'user_id' not in session or session.get('username')!= 'admin':
        return "Admin only"
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return STYLE + "<div class='card'><h3>Rejected!</h3><a href='/admin/payments'>Back</a></div>"

@app.route('/admin/tournaments', methods=['GET','POST'])
def admin_tourns():
    if 'user_id' not in session or session.get('username')!= 'admin':
        return redirect('/login')
    if request.method == 'POST':
        name = request.form.get('name')
        game = request.form.get('game')
        fee = request.form.get('fee')
        prize = request.form.get('prize')
        slots = request.form.get('slots')
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO tournaments (name,game,entry_fee,prize,slots) VALUES (?,?,?,?,?)", (name,game,fee,prize,slots))
        conn.commit()
        conn.close()
        return redirect('/')
    return STYLE + "<div class='card'><h2>Add Tournament</h2><form method='post'><input name='name' placeholder='Tournament Name' required><input name='game' placeholder='Game (Free Fire/BGMI)' required><input name='fee' type='number' placeholder='Entry Fee' required><input name='prize' type='number' placeholder='Prize Money' required><input name='slots' type='number' placeholder='Slots' required><button>Add Tournament</button></form><br><a href='/admin'>Back</a></div>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
