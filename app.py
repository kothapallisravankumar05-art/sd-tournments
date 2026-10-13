from flask import Flask, render_template, request, redirect, session, jsonify, flash
import sqlite3, os
from datetime import timedelta

DB = 'sd_tournament.db'
app = Flask(__name__)
app.secret_key = "sd_final_secure_2026"
app.permanent_session_lifetime = timedelta(days=3650)

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = "0"
    response.headers["Pragma"] = "no-cache"
    return response

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, username TEXT UNIQUE, password TEXT, balance INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, game TEXT, time TEXT, prize INTEGER, per_kill INTEGER, fee INTEGER, type TEXT, map TEXT, total INTEGER, room_id TEXT DEFAULT '', room_pass TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS joins (id INTEGER PRIMARY KEY, match_id INTEGER, user_id INTEGER, ff_id TEXT, ff_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE, status TEXT DEFAULT 'pending')''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'pending')''')
    c.execute("SELECT COUNT(*) FROM matches")
    if c.fetchone()[0]==0:
        c.execute("INSERT INTO matches (game,time,prize,per_kill,fee,type,map,total) VALUES (?,?,?,?,?,?,?,?)", ('FF MAX','Tonight 11 PM',1000,10,50,'Solo','Bermuda',48))
    conn.commit()
    conn.close()

init_db()

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = "0"          
    response.headers["Pragma"] = "no-cache"   
    return response

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    u=c.fetchone()
    if not u:
        session.clear()
        return redirect('/login')
    c.execute("SELECT m.*, (SELECT COUNT(*) FROM joins WHERE match_id=m.id) as joined FROM matches m ORDER BY m.id DESC")
    matches=c.fetchall()
    c.execute("SELECT match_id FROM joins WHERE user_id=?", (session['user_id'],))
    my_joined_ids = [r[0] for r in c.fetchall()]
    c.execute("SELECT m.* FROM matches m JOIN joins j ON m.id=j.match_id WHERE j.user_id=? AND m.room_id!=''", (session['user_id'],))
    my_rooms=c.fetchall()
    conn.close()
    match_list=[{'id':m[0],'game':m[1],'time':m[2],'prize':m[3],'per_kill':m[4],'fee':m[5],'type':m[6],'map':m[7],'total':m[8],'room_id':m[9],'room_pass':m[10],'joined':m[11]} for m in matches]
    my_room_list=[{'id':r[0],'game':r[1],'time':r[2],'prize':r[3],'type':r[6],'room_id':r[9],'room_pass':r[10]} for r in my_rooms]
    user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[4]}
    return render_template('index.html', user=user, tournaments=match_list, my_rooms=my_room_list, my_joined_ids=my_joined_ids, results=[])

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect('/')
    if request.method=='POST':
        phone=request.form['phone']
        password=request.form['password']
        conn=sqlite3.connect(DB)
        c=conn.cursor()
        c.execute("SELECT * FROM users WHERE phone=? AND password=?", (phone, password))
        u=c.fetchone()
        conn.close()
        if u:
            session.permanent = True
            session['user_id']=u[0]
            return redirect('/')
        else:
            return "<script>alert('Phone or Password wrong bro!');history.back()</script>"
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if 'user_id' in session:
        return redirect('/')
    if request.method=='POST':
        phone=request.form['phone']
        username=request.form['username']
        password=request.form['password']
        if len(phone)!=10 or not phone.isdigit():
            return "<script>alert('10 digit number pettali bro!');history.back()</script>"
        conn=sqlite3.connect(DB)
        c=conn.cursor()
        try:
            c.execute("INSERT INTO users (phone, username, password, balance) VALUES (?,?,?,0)", (phone, username, password))
            conn.commit()
            conn.close()
            return "<script>alert('Register success bro! Ippudu login avvu!');location='/login'</script>"
        except:
            conn.close()
            return "<script>alert('Ee Phone/Username already undi bro!');history.back()</script>"
    return render_template('register.html')

@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method=='POST':
        phone = request.form['phone']
        new_pass = request.form['new_password']
        conn=sqlite3.connect(DB)
        c=conn.cursor()
        c.execute("SELECT * FROM users WHERE phone=?", (phone,))
        u=c.fetchone()
        if not u:
            conn.close()
            return "<script>alert('Ee number tho account ledu bro!');history.back()</script>"
        c.execute("UPDATE users SET password=? WHERE phone=?", (new_pass, phone))
        conn.commit()
        conn.close()
        return "<script>alert('Password marchindi bro! Ippudu login avvu!');location='/login'</script>"
    return render_template('forgot.html')

@app.route('/join/<int:tid>', methods=['GET','POST'])
def join(tid):
    if 'user_id' not in session: return redirect('/login')
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT * FROM matches WHERE id=?",(tid,)); m=c.fetchone()
    c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],)); u=c.fetchone()
    c.execute("SELECT COUNT(*) FROM joins WHERE match_id=?",(tid,)); joined=c.fetchone()[0]
    c.execute("SELECT * FROM joins WHERE match_id=? AND user_id=?",(tid,session['user_id'])); already=c.fetchone()
    if already:
        conn.close()
        return f"<script>alert('Already joined!');location='/'</script>"
    if request.method=='POST':
        if u[4] < m[5]:
            conn.close()
            return f"<script>alert('Balance takkuva!');location='/wallet'</script>"
        c.execute("UPDATE users SET balance=balance-? WHERE id=?",(m[5],session['user_id']))
        c.execute("INSERT INTO joins (match_id,user_id,ff_id,ff_name) VALUES (?,?,?,?)",(tid,session['user_id'],request.form['ff_id'],request.form['ff_name']))
        conn.commit(); conn.close()
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
    conn=sqlite3.connect(DB); c=conn.cursor()
    if request.method=='POST':
        action=request.form.get('action')
        if action=='add_match':
            c.execute("INSERT INTO matches (game,time,prize,per_kill,fee,type,map,total) VALUES (?,?,?,?,?,?,?,?)",(request.form['game'],request.form['time'],int(request.form['prize']),int(request.form['per_kill']),int(request.form['fee']),request.form['type'],request.form['map'],int(request.form['total'])))
        elif action=='set_room':
            c.execute("UPDATE matches SET room_id=?, room_pass=? WHERE id=?",(request.form['room_id'],request.form['room_pass'],int(request.form['mid'])))
        conn.commit()
    c.execute("SELECT m.*, (SELECT COUNT(*) FROM joins WHERE match_id=m.id) as joined FROM matches m ORDER BY m.id DESC"); matches_raw=c.fetchall()
    c.execute("SELECT p.id, u.phone, p.amount, p.utr FROM payments p JOIN users u ON p.user_id=u.id WHERE p.status='pending'"); pending_payments=c.fetchall()
    c.execute("SELECT w.id, u.phone, w.amount, w.upi_id FROM withdrawals w JOIN users u ON w.user_id=u.id WHERE w.status='pending'"); pending_withdraws=c.fetchall()
    conn.close()
    matches=[{'id':m[0],'game':m[1],'time':m[2],'prize':m[3],'per_kill':m[4],'fee':m[5],'type':m[6],'map':m[7],'total':m[8],'room_id':m[9],'room_pass':m[10],'joined':m[11]} for m in matches_raw]
    return render_template('admin.html', matches=matches, pending_payments=pending_payments, pending_withdraws=pending_withdraws)

@app.route('/wallet')
def wallet():
    if 'user_id' not in session: return redirect('/login')
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],)); u=c.fetchone()
    if u is None:
        session.clear(); return redirect('/login')
    c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC",(session['user_id'],)); deposits=c.fetchall()
    c.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC",(session['user_id'],)); withdraws=c.fetchall()
    conn.close()
    user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[4]}
    d_list=[{'amount':d[2],'utr':d[3],'status':d[4]} for d in deposits]
    w_list=[{'amount':w[2],'upi':w[3],'status':w[4]} for w in withdraws]
    return render_template('wallet.html', user=user, deposits=d_list, withdraws=w_list)

@app.route('/add-money', methods=['POST'])
def add_money():
    if 'user_id' not in session: return redirect('/login')
    amt_str = request.get_json().get('amount') if request.is_json else request.form.get('amount')
    utr = request.get_json().get('utr') if request.is_json else request.form.get('utr')
    try: amt = int(amt_str)
    except: amt = 0
    if amt < 20: return jsonify(ok=False, msg='❌ Min Rs.20 Required!') if request.is_json else "<script>alert('❌ Min Rs.20 Required !');location='/wallet'</script>"
    if not utr or len(str(utr)) != 12 or not str(utr).isdigit(): return jsonify(ok=False, msg='❌ UTR 12 digits !') if request.is_json else "<script>alert('❌ UTR 12 digits wrong!');location='/wallet'</script>"
    conn=sqlite3.connect(DB); c=conn.cursor()
    try:
        c.execute("INSERT INTO payments (user_id,amount,utr,status) VALUES (?,?,?,?)",(session['user_id'], amt, str(utr).strip(), 'pending'))
        conn.commit(); conn.close()
        return jsonify(ok=True, msg='Pending bro!') if request.is_json else "<script>alert('Pending! Admin Approve chesthe add avthundi!');location='/wallet'</script>"
    except:
        conn.close()
        return jsonify(ok=False, msg='Ee UTR already vadaru bro!') if request.is_json else "<script>alert('Ee UTR already undi!');location='/wallet'</script>"

@app.route('/admin/approve_payment/<int:pid>')
def approve_payment(pid):
    if session.get('is_admin')!= True: return redirect('/admin')
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, amount FROM payments WHERE id=?",(pid,)); p=c.fetchone()
    if p:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?",(p[1], p[0]))
        c.execute("UPDATE payments SET status='approved' WHERE id=?",(pid,)); conn.commit()
    conn.close()
    return "<script>alert('Approved! Money Added!');location='/admin'</script>"

@app.route('/withdraw', methods=['GET','POST'])
def withdraw():
    if 'user_id' not in session: return redirect('/login')
    conn=sqlite3.connect(DB);c=conn.cursor();c.execute("SELECT * FROM users WHERE id=?",(session['user_id'],));u=c.fetchone()
    if request.method=='POST':
        amt=int(request.form['amount'])
        if u[4] < amt or amt < 50: conn.close();return "<script>alert('Balance ledu or Min 50');history.back()</script>"
        c.execute("UPDATE users SET balance=balance-? WHERE id=?",(amt,session['user_id']))
        c.execute("INSERT INTO withdrawals (user_id,amount,upi_id,status) VALUES (?,?,?,?)",(session['user_id'],amt,request.form['upi_id'],'pending'));conn.commit();conn.close()
        return "<script>alert('Withdraw Request Sent');location='/wallet'</script>"
    conn.close()
    return render_template('withdraw.html', user={'id':u[0],'phone':u[1],'username':u[2],'balance':u[4]})

@app.route('/admin/approve_withdraw/<int:wid>')
def approve_withdraw(wid):
    if session.get('is_admin')!=True: return redirect('/admin')
    conn=sqlite3.connect(DB);c=conn.cursor();c.execute("UPDATE withdrawals SET status='approved' WHERE id=?",(wid,));conn.commit();conn.close()
    return "<script>alert('Withdraw Approved');location='/admin'</script>"

@app.route('/admin/reject_withdraw/<int:wid>')
def reject_withdraw(wid):
    if session.get('is_admin')!=True: return redirect('/admin')
    conn=sqlite3.connect(DB);c=conn.cursor();c.execute("SELECT user_id,amount FROM withdrawals WHERE id=?",(wid,));w=c.fetchone()
    if w: c.execute("UPDATE users SET balance=balance+? WHERE id=?",(w[1],w[0]));c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?",(wid,));conn.commit()
    conn.close();return "<script>alert('Rejected & Refunded');location='/admin'</script>"

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/admin-logout')
def admin_logout():
    session.pop('is_admin', None); return redirect('/')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=True)
