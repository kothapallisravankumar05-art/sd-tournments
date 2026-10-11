from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, random, requests
from datetime import timedelta

ADMIN_PASS = "SD@12345"
DB = 'sd_tournament.db'
app = Flask(__name__)
app.secret_key = "sd_final_secure"
app.permanent_session_lifetime = timedelta(days=3650)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, username TEXT, balance INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, game TEXT, time TEXT, prize INTEGER, per_kill INTEGER, fee INTEGER, type TEXT, map TEXT, total INTEGER, room_id TEXT DEFAULT '', room_pass TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS joins (id INTEGER PRIMARY KEY, match_id INTEGER, user_id INTEGER, ff_id TEXT, ff_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'pending')''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'pending')''')
    c.execute("SELECT COUNT(*) FROM matches")
    if c.fetchone()[0]==0:
        c.execute("INSERT INTO matches (game,time,prize,per_kill,fee,type,map,total,room_id,room_pass) VALUES (?,?,?,?,?,?,?,?,?,?)", ('FF MAX','Tonight 11 PM',1000,10,50,'Solo','Bermuda',48,'',''))
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    u=c.fetchone()
    c.execute("SELECT m.*, (SELECT COUNT(*) FROM joins WHERE match_id=m.id) as joined FROM matches m ORDER BY m.id DESC")
    matches=c.fetchall()
    c.execute("SELECT m.* FROM matches m JOIN joins j ON m.id=j.match_id WHERE j.user_id=? AND m.room_id!=''", (session['user_id'],))
    my_rooms=c.fetchall()
    conn.close()

    match_list=[]
    for m in matches:
        match_list.append({'id':m[0],'game':m[1],'time':m[2],'prize':m[3],'per_kill':m[4],'fee':m[5],'type':m[6],'map':m[7],'total':m[8],'room_id':m[9],'room_pass':m[10],'joined':m[11]})
    my_room_list=[]
    for r in my_rooms:
        my_room_list.append({'id':r[0],'game':r[1],'time':r[2],'prize':r[3],'type':r[6],'room_id':r[9],'room_pass':r[10]})

    if not u:
        session.clear()
        return redirect('/login')

    user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[3]}
    return render_template('index.html', user=user, tournaments=match_list, my_rooms=my_room_list)

# ============ REAL OTP LOGIN - IKKADA MARCHA BRO! ============
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        phone=request.form['phone']
        if not phone.isdigit() or len(phone)!= 10:
            return "<script>alert('10 digit number pettali bro!');history.back()</script>"
        otp=str(random.randint(100000,999999))
        session['otp']=otp
        session['temp_phone']=phone

        # --- REAL SMS SEND ---
        try:
            API_KEY = "weIpq7TfyKLDa915uGC8trkihjZv2FmB0P4bJHASndUoMVOR63eOtn5vVsDExcFX6HomkBbNz1WpfqTi" # <--- IKKADA NEE KEY PETTU BRO!!!
            url = "https://www.fast2sms.com/dev/bulkV2"
            payload = f"variables_values={otp}&route=otp&numbers={phone}"
            headers = {'authorization': API_KEY, 'Content-Type': "application/x-www-form-urlencoded"}
            requests.post(url, data=payload, headers=headers)
        except Exception as e:
            print(e)

        return render_template('verify.html', phone=phone) # otp teesesanu - demo aipoyindi!
    return render_template('login.html')

@app.route('/verify', methods=['POST'])
def verify():
    if request.form['otp']==session.get('otp'):
        conn=sqlite3.connect(DB)
        c=conn.cursor()
        c.execute("SELECT * FROM users WHERE phone=?",(session['temp_phone'],))
        u=c.fetchone()
        if not u:
            c.execute("INSERT INTO users (phone, username, balance) VALUES (?,?,0)",(session['temp_phone'],f"FF_Player_{session['temp_phone'][-4:]}"))
            conn.commit()
            c.execute("SELECT * FROM users WHERE phone=?",(session['temp_phone'],))
            u=c.fetchone()
        conn.close()
        session.permanent = True
        session['user_id']=u[0]
        return redirect('/')
    return "<script>alert('Wrong OTP');history.back()</script>"

@app.route('/join/<int:tid>', methods=['GET','POST'])
def join(tid):
    if 'user_id' not in session:
        return redirect('/login')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT * FROM matches WHERE id=?",(tid,))
    m=c.fetchone()
    c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],))
    u=c.fetchone()
    c.execute("SELECT COUNT(*) FROM joins WHERE match_id=?",(tid,))
    joined=c.fetchone()[0]
    c.execute("SELECT * FROM joins WHERE match_id=? AND user_id=?",(tid,session['user_id']))
    already=c.fetchone()
    if already:
        conn.close()
        return f"<script>alert('Already joined!');location='/'</script>"
    if request.method=='POST':
        if u[3] < m[5]:
            conn.close()
            return f"<script>alert('Balance takkuva!');location='/wallet'</script>"
        c.execute("UPDATE users SET balance=balance-? WHERE id=?",(m[5],session['user_id']))
        c.execute("INSERT INTO joins (match_id,user_id,ff_id,ff_name) VALUES (?,?,?,?)",(tid,session['user_id'],request.form['ff_id'],request.form['ff_name']))
        conn.commit()
        conn.close()
        return f"<script>alert('Joined Success!');location='/'</script>"
    conn.close()
    tour=(m[0],m[0],m[6],m[1],m[2],m[5],m[3],m[7],m[8],m[9],m[10])
    return render_template('join.html', tour=tour, joined=joined, user=u)

@app.route('/admin', methods=['GET','POST'])
def admin():
    if session.get('is_admin')!= True:
        if request.method=='POST' and request.form.get('admin_pass'):
            if request.form.get('admin_pass') == "101210":
                session['is_admin'] = True
            else:
                return "<script>alert('Wrong Admin Password!');location='/admin'</script>"
        else:
            return '''<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{background:#0f172a;color:#fff;font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.box{background:#1e293b;padding:30px;border-radius:15px;text-align:center}input{padding:12px;border-radius:8px;border:none;margin:10px;width:200px}button{padding:12px 20px;background:#00ff88;border:none;border-radius:8px;font-weight:900}</style></head><body><div class="box"><h2>🔐 ADMIN LOGIN</h2><form method="POST"><input type="password" name="admin_pass" placeholder="Admin Password" required><br><button>LOGIN</button></form></div></body></html>'''

    conn=sqlite3.connect(DB)
    c=conn.cursor()
    if request.method=='POST':
        action=request.form.get('action')
        if action=='add_match':
            c.execute("INSERT INTO matches (game,time,prize,per_kill,fee,type,map,total) VALUES (?,?,?,?,?,?,?,?)",(request.form['game'],request.form['time'],int(request.form['prize']),int(request.form['per_kill']),int(request.form['fee']),request.form['type'],request.form['map'],int(request.form['total'])))
        elif action=='set_room':
            c.execute("UPDATE matches SET room_id=?, room_pass=? WHERE id=?",(request.form['room_id'],request.form['room_pass'],int(request.form['mid'])))
        conn.commit()

    c.execute("SELECT m.*, (SELECT COUNT(*) FROM joins WHERE match_id=m.id) as joined FROM matches m ORDER BY m.id DESC")
    matches_raw=c.fetchall()

    c.execute("SELECT p.id, u.phone, p.amount, p.utr FROM payments p JOIN users u ON p.user_id=u.id WHERE p.status='pending'")
    pending_payments=c.fetchall()
    c.execute("SELECT w.id, u.phone, w.amount, w.upi_id FROM withdrawals w JOIN users u ON w.user_id=u.id WHERE w.status='pending'")
    pending_withdraws=c.fetchall()

    conn.close()
    matches=[]
    for m in matches_raw:
        matches.append({'id':m[0],'game':m[1],'time':m[2],'prize':m[3],'per_kill':m[4],'fee':m[5],'type':m[6],'map':m[7],'total':m[8],'room_id':m[9],'room_pass':m[10],'joined':m[11]})
    return render_template('admin.html', matches=matches, pending_payments=pending_payments, pending_withdraws=pending_withdraws)

@app.route('/wallet')
def wallet():
    if 'user_id' not in session:
        return redirect('/login')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],))
    u=c.fetchone()
    c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC",(session['user_id'],))
    deposits=c.fetchall()
    c.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC",(session['user_id'],))
    withdraws=c.fetchall()
    conn.close()
    user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[3]}
    d_list=[]
    for d in deposits:
        d_list.append({'amount':d[2],'utr':d[3],'status':d[4]})
    w_list=[]
    for w in withdraws:
        w_list.append({'amount':w[2],'upi':w[3],'status':w[4]})
    return render_template('wallet.html', user=user, deposits=d_list, withdraws=w_list)

@app.route('/add-money', methods=['POST'])
def add_money():
    if 'user_id' not in session:
        return redirect('/login')
    if request.is_json:
        data = request.get_json()
        amt_str = data.get('amount')
        utr = data.get('utr')
    else:
        amt_str = request.form.get('amount')
        utr = request.form.get('utr')
    try:
        amt = int(amt_str)
    except:
        amt = 0
    if amt < 10:
        if request.is_json:
            return jsonify(ok=False, msg='Min 10 Rs bro!')
        else:
            return "<script>alert('Min 10 Rs bro!');location='/wallet'</script>"
    if not utr or len(str(utr)) < 5:
        if request.is_json:
            return jsonify(ok=False, msg='UTR pettali bro!')
        else:
            return "<script>alert('UTR pettali bro!');location='/wallet'</script>"
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    try:
        c.execute("INSERT INTO payments (user_id,amount,utr,status) VALUES (?,?,?,?)",(session['user_id'], amt, str(utr).strip(), 'pending'))
        conn.commit()
        conn.close()
        if request.is_json:
            return jsonify(ok=True, msg='Pending bro! Admin approve chesthe ne add avthundi')
        else:
            return "<script>alert('Pending! Admin Approve chesthe add avthundi!');location='/wallet'</script>"
    except:
        conn.close()
        if request.is_json:
            return jsonify(ok=False, msg='Ee UTR already vadaru bro!')
        else:
            return "<script>alert('Ee UTR already undi!');location='/wallet'</script>"

@app.route('/admin/approve_payment/<int:pid>')
def approve_payment(pid):
    if session.get('is_admin')!= True:
        return redirect('/admin')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT user_id, amount FROM payments WHERE id=?",(pid,))
    p=c.fetchone()
    if p:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?",(p[1], p[0]))
        c.execute("UPDATE payments SET status='approved' WHERE id=?",(pid,))
        conn.commit()
    conn.close()
    return "<script>alert('Approved! Money Added!');location='/admin'</script>"

@app.route('/withdraw', methods=['GET','POST'])
def withdraw():
    if 'user_id' not in session:
        return redirect('/login')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],))
    u=c.fetchone()
    if request.method=='POST':
        try:
            amt=int(request.form.get('amount',0))
        except:
            amt=0
        upi=request.form.get('upi_id','').strip()
        if amt < 100:
            conn.close()
            return "<script>alert('Bro Min 100 Rs undali!');history.back()</script>"
        if u[3] < amt:
            conn.close()
            return "<script>alert('Balance takkuva bro!');location='/wallet'</script>"
        c.execute("UPDATE users SET balance=balance-? WHERE id=?",(amt, session['user_id']))
        c.execute("INSERT INTO withdrawals (user_id,amount,upi_id,status) VALUES (?,?,?,?)",(session['user_id'],amt,upi,'pending'))
        conn.commit()
        conn.close()
        return "<script>alert('Withdrawal Request Pending! 24hrs lo UPI ki vasthadi!');location='/wallet'</script>"
    conn.close()
    return render_template('withdraw.html', user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[3]})

@app.route('/admin/approve_withdraw/<int:wid>')
def approve_withdraw(wid):
    if session.get('is_admin')!= True:
        return redirect('/admin')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("UPDATE withdrawals SET status='approved' WHERE id=?",(wid,))
    conn.commit()
    conn.close()
    return "<script>alert('Withdrawal Paid!');location='/admin'</script>"

@app.route('/admin/reject_withdraw/<int:wid>')
def reject_withdraw(wid):
    if session.get('is_admin')!= True:
        return redirect('/admin')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT user_id, amount FROM withdrawals WHERE id=?",(wid,))
    w=c.fetchone()
    if w:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?",(w[1], w[0]))
        c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?",(wid,))
        conn.commit()
    conn.close()
    return "<script>alert('Rejected & Refunded!');location='/admin'</script>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/set-winner', methods=['POST'])
def set_winner():
    if session.get('is_admin')!= True:
        return redirect('/admin')
    match_id = int(request.form['match_id'])
    winner_phone = request.form['winner_phone']
    prize = int(request.form['prize_amount'])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE phone=?", (winner_phone,))
    w = c.fetchone()
    if w:
        c.execute("UPDATE users SET balance = balance +? WHERE phone=?", (prize, winner_phone))
        c.execute("DELETE FROM joins WHERE match_id=?", (match_id,))
        conn.commit()
        msg = f"Winner {winner_phone} ki Rs.{prize} add chesam!"
    else:
        msg = "User not found!"
    conn.close()
    return f"<script>alert('{msg}');location='/admin'</script>"

@app.route('/admin-logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=True)
