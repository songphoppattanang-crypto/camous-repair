# ไฟล์หลักของเว็บ: รับฟอร์ม ตรวจสิทธิ์ และจัดการรายการแจ้งซ่อม
"""ระบบแจ้งซ่อม: routes, validation, permissions และคำสั่ง CLI ในไฟล์เดียว."""
import os
import re
import secrets
import hashlib
from io import BytesIO
from datetime import timedelta
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, send_file
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import check_password_hash, generate_password_hash
from database import connect_database, INTEGRITY_ERRORS
from evidence import prepare_photo, MAX_UPLOAD
from member import profile_fields, TITLES, valid_password
from notifications import queue_repair_mail, deliver_pending
from enhancements import paginate, display_repairs
from dashboard_stats import dashboard_data, date_filter

STATUSES = {'pending': 'รอรับเรื่อง', 'working': 'กำลังดำเนินการ',
            'done': 'เสร็จสิ้น', 'unrepairable': 'ไม่สามารถซ่อมได้', 'cancelled': 'ยกเลิกแล้ว'}
csrf = CSRFProtect()


# สร้างแอป ตั้งค่าความปลอดภัย และผูกหน้าต่าง ๆ ของเว็บ
def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    on_vercel = os.environ.get('VERCEL') == '1'
    database_url = os.environ.get('DATABASE_URL')
    if on_vercel and (not database_url or not os.environ.get('SECRET_KEY')):
        raise RuntimeError('Vercel requires DATABASE_URL and SECRET_KEY environment variables')
    if not on_vercel:
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    # สร้าง secret ในเครื่องครั้งแรก ไม่ใส่ secret จริงไว้ใน source/ZIP
    secret = os.environ.get('SECRET_KEY')
    if not secret and not test_config and not on_vercel:
        key_file = Path(app.instance_path) / 'secret.key'
        try:
            with key_file.open('x', encoding='utf-8') as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = key_file.read_text(encoding='utf-8').strip()
    app.config.from_mapping(
        SECRET_KEY=secret or secrets.token_hex(32),
        DATABASE=str(Path(app.instance_path) / 'repair.sqlite3'),
        DATABASE_URL=database_url,
        ON_VERCEL=on_vercel,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=on_vercel or os.environ.get('COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=MAX_UPLOAD + 64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    # เปิดการตรวจ token ของฟอร์มเพื่อป้องกันคำขอปลอม
    csrf.init_app(app)
    app.teardown_appcontext(close_db)

    @app.before_request
    # อ่านบัญชีที่ล็อกอินจาก session ก่อนเปิดแต่ละหน้า
    def load_user():
        g.user = None
        if session.get('user_id'):
            g.user = get_db().execute('SELECT * FROM users WHERE id=?',
                                     (session['user_id'],)).fetchone()
            if g.user is None or session.get('password_version') != hashlib.sha256(g.user['password_hash'].encode()).hexdigest():
                g.user = None
                # ล้างข้อมูลการล็อกอินเดิม
                session.clear()

    @app.context_processor
    # ส่งชื่อสถานะภาษาไทยให้ทุกหน้าใช้ร่วมกัน
    def common():
        return {'statuses': STATUSES, 'titles': TITLES}

    @app.after_request
    # เพิ่ม header ความปลอดภัยและไม่แคชหน้าของผู้ใช้
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if g.get('user'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/')
    # เปิดหน้าแรก หรือส่งคนที่ล็อกอินแล้วไปหน้าตามสิทธิ์
    def home():
        if g.user:
            return redirect(url_for('admin_dashboard' if g.user['role'] == 'admin' else 'my_repairs'))
        return render_template('home.html')

    @app.route('/register', methods=['GET', 'POST'])
    # รับข้อมูลสมัครสมาชิก ตรวจข้อมูล แล้วเก็บรหัสผ่านแบบแฮช
    def register():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '')
            error = None
            try:
                profile = profile_fields(request.form)
            except ValueError as exc:
                error = str(exc)
            if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username):
                error = 'ชื่อผู้ใช้ต้องเป็นภาษาอังกฤษ ตัวเลข หรือ _ . - จำนวน 3–40 ตัว'
            elif not 2 <= len(name) <= 100:
                error = 'ชื่อผู้แจ้งต้องมี 2–100 ตัวอักษร'
            elif not valid_password(password):
                error = 'รหัสผ่านต้องมี 8–128 ตัวอักษร และมีตัวพิมพ์ใหญ่ A–Z อย่างน้อย 1 ตัว'
            elif password != request.form.get('confirm_password'):
                error = 'ยืนยันรหัสผ่านไม่ตรงกัน'
            if error:
                flash(error, 'danger')
            else:
                try:
                    db = get_db()
                    with db:
                        cur = db.execute('INSERT INTO users(username,name,password_hash) VALUES(?,?,?)',
                                         (username, name, generate_password_hash(password)))
                        db.execute('INSERT INTO user_profiles(user_id,email,title,student_id,faculty,major) VALUES(?,?,?,?,?,?)',
                                   (cur.lastrowid, *profile.values()))
                    flash('สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ', 'success')
                    return redirect(url_for('login'))
                except INTEGRITY_ERRORS:
                    flash('ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้งานแล้ว', 'danger')
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    # ตรวจชื่อผู้ใช้และรหัสผ่าน แล้วจำบัญชีไว้ใน session
    def login():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            user = get_db().execute('SELECT u.* FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE lower(u.username)=? OR lower(p.email)=?',
                                   (request.form.get('username', '').strip().lower(),) * 2).fetchone()
            password = request.form.get('password', '')
            # เทียบรหัสผ่านที่กรอกกับแฮชของบัญชี
            if len(password) <= 128 and user and check_password_hash(user['password_hash'], password):
                # ล้างข้อมูลการล็อกอินเดิม
                session.clear()
                session['user_id'] = user['id']
                session['password_version'] = hashlib.sha256(user['password_hash'].encode()).hexdigest()
                session.permanent = True
                return redirect(url_for('home'))
            flash('ชื่อผู้ใช้ อีเมล หรือรหัสผ่านไม่ถูกต้อง', 'danger')
        return render_template('login.html')

    @app.post('/logout')
    @login_required
    # ล้าง session เพื่อออกจากระบบ
    def logout():
        # ล้างข้อมูลการล็อกอินเดิม
        session.clear()
        flash('ออกจากระบบแล้ว', 'success')
        return redirect(url_for('login'))

    @app.get('/repairs')
    @login_required
    # ดึงเฉพาะรายการของบัญชีที่กำลังล็อกอิน
    def my_repairs():
        status = request.args.get('status','')
        query = 'SELECT r.*,c.id AS cancelled_id FROM repairs r LEFT JOIN repair_cancellations c ON c.repair_id=r.id WHERE r.user_id=?'
        params=[g.user['id']]
        if status in STATUSES:
            query += " AND (CASE WHEN c.id IS NOT NULL THEN 'cancelled' ELSE r.status END)=?"
            params.append(status)
        rows, pagination = paginate(get_db(),query,params)
        return render_template('repairs.html',repairs=display_repairs(rows),selected_status=status,pagination=pagination)

    @app.route('/repairs/new', methods=['GET', 'POST'])
    @login_required
    # ตรวจข้อมูลผู้แจ้งและภาพ ก่อนสร้างรายการแจ้งซ่อม
    def new_repair():
        if g.user['role'] != 'user':
            abort(403)
        # ใช้ตัวตนจากบัญชีที่ล็อกอิน ไม่รับชื่อหรือรหัสนักศึกษาจากฟอร์ม
        profile = get_db().execute('SELECT student_id FROM user_profiles WHERE user_id=?', (g.user['id'],)).fetchone()
        if profile is None or not re.fullmatch(r'[0-9]{8,15}(?:-[0-9]{1,2})?', profile['student_id']):
            flash('กรุณาเพิ่มรหัสนักศึกษาในข้อมูลบัญชีก่อนแจ้งซ่อม', 'warning')
            return redirect(url_for('account'))
        if request.method == 'POST':
            fields = {k: request.form.get(k, '').strip() for k in
                      ('equipment', 'room', 'description', 'contact')}
            reporter_name = g.user['name'].strip()
            student_id = profile['student_id']
            photo = None
            error = None
            try:
                photo = prepare_photo(request.files.get('photo'))
            except ValueError as exc:
                error = str(exc)
            limits = {'equipment': (2, 100), 'room': (1, 100),
                      'description': (10, 2000), 'contact': (9, 10)}
            if not re.fullmatch(r'0[0-9]{8,9}', fields['contact']):
                error = 'กรุณากรอกเบอร์โทรศัพท์ที่ขึ้นต้นด้วย 0 จำนวน 9–10 หลัก ไม่เว้นวรรคหรือใส่ขีด'
            if error:
                flash(error, 'danger')
            elif any(not lo <= len(fields[k]) <= hi for k, (lo, hi) in limits.items()):
                flash('กรอกข้อมูลให้ครบ: อุปกรณ์ 2–100, ห้อง 1–100, อาการ 10–2,000 และเบอร์โทรศัพท์ 9–10 หลัก', 'danger')
            else:
                db = get_db()
                # บันทึกเป็นชุดเดียว ถ้าขั้นตอนใดผิดพลาดให้ย้อนกลับ
                with db:
                    cur = db.execute('INSERT INTO repairs(user_id,equipment,room,description,contact) VALUES(?,?,?,?,?)',
                                     (g.user['id'], *fields.values()))
                    db.execute('INSERT INTO repair_evidence(repair_id,reporter_name,student_id,photo) VALUES(?,?,?,?)',
                               (cur.lastrowid,reporter_name,student_id,photo))
                    db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                               (cur.lastrowid, g.user['id'], 'pending', 'สร้างรายการแจ้งซ่อม'))
                    mail_ids = queue_repair_mail(db, cur.lastrowid, STATUSES['pending'], 'ได้รับรายการแจ้งซ่อมใหม่')
                if not deliver_pending(db, mail_ids):
                    flash('บันทึกรายการแล้ว แต่อีเมลแจ้งเตือนยังรอส่ง', 'warning')
                flash('ส่งรายการแจ้งซ่อมแล้ว', 'success')
                return redirect(url_for('repair_detail', repair_id=cur.lastrowid))
        return render_template('new_repair.html')

    @app.get('/repairs/<int:repair_id>')
    @login_required
    # เปิดรายละเอียดและประวัติ หลังตรวจสิทธิ์เข้าถึง
    def repair_detail(repair_id):
        # ตรวจสิทธิ์ที่ server ทุกครั้ง แม้พิมพ์ URL หรือเปลี่ยนหมายเลขเอง
        row = get_repair(repair_id)
        history = get_db().execute('SELECT h.*,u.name AS actor FROM repair_history h JOIN users u ON u.id=h.actor_id WHERE repair_id=? ORDER BY h.id DESC', (repair_id,)).fetchall()
        cancellation = get_db().execute('SELECT c.*,u.name AS actor FROM repair_cancellations c JOIN users u ON u.id=c.actor_id WHERE repair_id=?',(repair_id,)).fetchone()
        if cancellation:
            history.insert(0, {'status':'cancelled','note':cancellation['reason'],'created_at':cancellation['created_at'],'actor':cancellation['actor']})
        return render_template('detail.html', repair=row, history=history)

    @app.get('/repairs/<int:repair_id>/photo')
    @login_required
    # ส่งภาพให้เจ้าของรายการหรือผู้ดูแลเท่านั้น
    def repair_photo(repair_id):
        get_repair(repair_id)  # ตรวจเจ้าของหรือ Admin ก่อนอ่าน bytes ทุกครั้ง
        evidence = get_db().execute('SELECT photo FROM repair_evidence WHERE repair_id=?', (repair_id,)).fetchone()
        if evidence is None:
            abort(404)
        response = send_file(BytesIO(bytes(evidence['photo'])),mimetype='image/webp',
                             download_name=f'repair-{repair_id}.webp',max_age=0)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        return response

    @app.get('/admin')
    @admin_required
    # นับรายการแต่ละสถานะเพื่อแสดงบนแดชบอร์ด
    def admin_dashboard():
        return render_template('dashboard.html', **dashboard_data(get_db(),STATUSES))

    @app.get('/admin/repairs')
    @admin_required
    # ค้นหาและกรองรายการทั้งหมดสำหรับผู้ดูแล
    def admin_repairs():
        q = request.args.get('q', '').strip()[:100]
        status = request.args.get('status', '')
        sql = 'SELECT r.*,u.name AS owner,e.reporter_name,e.student_id,c.id AS cancelled_id FROM repairs r JOIN users u ON u.id=r.user_id LEFT JOIN repair_evidence e ON e.repair_id=r.id LEFT JOIN repair_cancellations c ON c.repair_id=r.id WHERE 1=1'
        params = []
        if q:
            sql += ' AND (r.equipment LIKE ? OR r.room LIKE ? OR u.name LIKE ? OR e.reporter_name LIKE ? OR e.student_id LIKE ? OR CAST(r.id AS TEXT)=?)'
            params += ['%' + q + '%'] * 5 + [q]
        if status in STATUSES:
            sql += " AND (CASE WHEN c.id IS NOT NULL THEN 'cancelled' ELSE r.status END)=?"
            params.append(status)
        if request.args.get('date'):
            anchor,period,start,end=date_filter()
            sql += ' AND r.created_at>=? AND r.created_at<?'
            params.extend([start.isoformat(),end.isoformat()])
        rows,pagination = paginate(get_db(),sql,params)
        return render_template('admin_repairs.html', repairs=display_repairs(rows), q=q, selected_status=status,pagination=pagination)

    @app.post('/admin/repairs/<int:repair_id>/update')
    @admin_required
    # อัปเดตสถานะพร้อมบันทึกประวัติการซ่อม
    def update_repair(repair_id):
        repair = get_repair(repair_id)
        if repair['status']=='cancelled':
            flash('รายการนี้ยกเลิกแล้ว ไม่สามารถอัปเดตการซ่อมได้','warning')
            return redirect(url_for('repair_detail',repair_id=repair_id))
        assignee = request.form.get('assignee','').strip()
        status = request.form.get('status', '')
        note = request.form.get('note', '').strip()
        if status not in STATUSES or status=='cancelled' or not 3 <= len(note) <= 2000 or len(assignee)>100:
            flash('เลือกสถานะที่ถูกต้อง และใส่บันทึกการซ่อม 3–2,000 ตัวอักษร', 'danger')
        else:
            db = get_db()
            # บันทึกเป็นชุดเดียว ถ้าขั้นตอนใดผิดพลาดให้ย้อนกลับ
            with db:
                if current_db_is_postgres():
                    db.execute('SELECT id FROM repairs WHERE id=? FOR UPDATE',(repair_id,)).fetchone()
                if get_repair(repair_id)['status']=='cancelled': abort(409)
                cur = db.execute("UPDATE repairs SET status=?,updated_at=datetime('now','+7 hours') WHERE id=? AND NOT EXISTS(SELECT 1 FROM repair_cancellations WHERE repair_id=?)", (status, repair_id,repair_id))
                if cur.rowcount != 1: abort(409)
                db.execute('INSERT INTO repair_assignments(repair_id,assignee,actor_id) VALUES(?,?,?) ON CONFLICT(repair_id) DO UPDATE SET assignee=excluded.assignee,actor_id=excluded.actor_id',(repair_id,assignee,g.user['id']))
                if assignee != (repair['assignee'] or ''):
                    note = 'ผู้รับผิดชอบ: '+(assignee or 'ยังไม่ได้มอบหมาย')+'\n'+note
                db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                           (repair_id, g.user['id'], status, note))
                mail_ids = queue_repair_mail(db, repair_id, STATUSES[status], 'อัปเดตสถานะการซ่อม')
            if not deliver_pending(db, mail_ids):
                flash('บันทึกสถานะแล้ว แต่อีเมลแจ้งเตือนยังรอส่ง', 'warning')
            flash('บันทึกสถานะและประวัติการซ่อมแล้ว', 'success')
        return redirect(url_for('repair_detail', repair_id=repair_id))

    @app.errorhandler(CSRFError)
    # แจ้งให้เปิดฟอร์มใหม่ เมื่อ token ไม่ถูกต้องหรือหมดอายุ
    def csrf_error(error):
        return render_template('error.html', code=400, message='แบบฟอร์มหมดอายุหรือไม่ถูกต้อง กรุณาเปิดหน้าใหม่แล้วลองอีกครั้ง'), 400

    for code, message in [(403, 'คุณไม่มีสิทธิ์ใช้งานหน้านี้'), (404, 'ไม่พบข้อมูลหรือรายการที่คุณเข้าถึงได้'), (413, 'ข้อมูลที่ส่งมีขนาดใหญ่เกินกำหนด')]:
        app.register_error_handler(code, lambda error, c=code, m=message: (render_template('error.html', code=c, message=m), c))

    @app.post('/account/password')
    @login_required
    # เปลี่ยนรหัสผ่านโดยตรวจรหัสเดิม และให้อุปกรณ์อื่นเข้าสู่ระบบใหม่
    def change_password():
        old = request.form.get('current_password','')
        new = request.form.get('password','')
        if len(old)>128 or not check_password_hash(g.user['password_hash'],old):
            flash('รหัสผ่านเดิมไม่ถูกต้อง','danger')
        elif not valid_password(new) or new != request.form.get('confirm_password'):
            flash('รหัสผ่านใหม่ต้องมี 8–128 ตัวอักษร และมีตัวพิมพ์ใหญ่ A–Z อย่างน้อย 1 ตัวและยืนยันให้ตรงกัน','danger')
        elif check_password_hash(g.user['password_hash'],new):
            flash('กรุณาใช้รหัสผ่านใหม่ที่ต่างจากรหัสเดิม','danger')
        else:
            hashed = generate_password_hash(new)
            db=get_db()
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,g.user['id']));db.commit()
            session.clear();session['user_id']=g.user['id'];session.permanent=True
            session['password_version']=hashlib.sha256(hashed.encode()).hexdigest()
            flash('เปลี่ยนรหัสผ่านแล้ว อุปกรณ์อื่นต้องเข้าสู่ระบบใหม่','success')
        return redirect(url_for('account'))

    @app.post('/repairs/<int:repair_id>/cancel')
    @login_required
    # ยกเลิกได้เฉพาะเจ้าของงานที่ยังรอรับเรื่อง เก็บข้อมูลเดิมไว้ครบ
    def cancel_repair(repair_id):
        repair=get_repair(repair_id)
        if g.user['role']!='user' or repair['user_id']!=g.user['id']:abort(403)
        reason=request.form.get('reason','').strip()
        if not 3<=len(reason)<=1000:
            flash('กรุณาระบุเหตุผลการยกเลิก 3–1,000 ตัวอักษร','danger')
            return redirect(url_for('repair_detail',repair_id=repair_id))
        db=get_db()
        with db:
            # ล็อกแถวงานก่อน เพื่อไม่ให้ยกเลิกพร้อมกับที่ Admin รับงาน
            if current_db_is_postgres():
                db.execute('SELECT id FROM repairs WHERE id=? FOR UPDATE',(repair_id,)).fetchone()
            current=get_repair(repair_id)
            if current['status']!='pending':
                flash('ยกเลิกได้เฉพาะรายการที่ยังรอรับเรื่อง','warning')
                return redirect(url_for('repair_detail',repair_id=repair_id))
            db.execute('INSERT INTO repair_cancellations(repair_id,actor_id,reason) VALUES(?,?,?)',(repair_id,g.user['id'],reason))
            db.execute("UPDATE repairs SET updated_at=datetime('now','+7 hours') WHERE id=?",(repair_id,))
            mail_ids=queue_repair_mail(db,repair_id,STATUSES['cancelled'],'ผู้แจ้งยกเลิกรายการ')
        if not deliver_pending(db,mail_ids):flash('ยกเลิกแล้ว แต่อีเมลยังรอส่ง','warning')
        flash('ยกเลิกรายการแล้ว ข้อมูลและประวัติเดิมยังอยู่','success')
        return redirect(url_for('repair_detail',repair_id=repair_id))

    @app.get('/admin/emails')
    @admin_required
    # ดูผลการส่งอีเมล โดยไม่เปิดเผยรหัสผ่าน SMTP
    def admin_emails():
        selected=request.args.get('status','')
        query='SELECT id,recipient,subject,status,attempts FROM email_outbox WHERE 1=1';params=[]
        if selected in ('pending','sending','sent'):query+=' AND status=?';params.append(selected)
        rows,pagination=paginate(get_db(),query,params)
        counts={key:0 for key in ('pending','sending','sent')}
        for row in get_db().execute('SELECT status,COUNT(*) AS total FROM email_outbox GROUP BY status'):counts[row['status']]=row['total']
        return render_template('admin_emails.html',emails=rows,pagination=pagination,counts=counts,selected_status=selected)

    @app.post('/admin/emails/<int:email_id>/retry')
    @admin_required
    # ส่งใหม่เฉพาะงานรอส่ง ไม่ส่งซ้ำงานที่สำเร็จหรือกำลังส่งอยู่
    def retry_email(email_id):
        db=get_db();row=db.execute('SELECT status FROM email_outbox WHERE id=?',(email_id,)).fetchone()
        if row is None:abort(404)
        if row['status']!='pending':
            flash('ส่งใหม่ได้เฉพาะอีเมลที่รอส่ง','warning')
        else:
            sent=deliver_pending(db,[email_id])
            flash('ส่งอีเมลแล้ว' if sent else 'ยังส่งไม่ได้ กรุณาตรวจการตั้งค่า SMTP หรือ Logs','success' if sent else 'warning')
        return redirect(url_for('admin_emails'))

    @app.get('/admin/users')
    @admin_required
    # ผู้ดูแลค้นหาบัญชีทั่วไป ไม่ดึงแฮชรหัสผ่านไปแสดง
    def admin_users():
        q = request.args.get('q', '').strip()[:100]
        query = "SELECT u.id,u.username,u.name,u.created_at,p.email,p.title,p.student_id,p.faculty,p.major FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.role='user'"
        params = []
        if q:
            query += ' AND (u.username LIKE ? OR u.name LIKE ? OR p.email LIKE ? OR p.student_id LIKE ?)'
            params = ['%' + q + '%'] * 4
        rows,pagination = paginate(get_db(),query,params)
        return render_template('admin_users.html',users=rows,q=q,pagination=pagination)

    @app.route('/admin/users/<int:user_id>', methods=['GET','POST'])
    @admin_required
    # เปิดข้อมูลผู้ใช้ และตั้งรหัสผ่านใหม่โดยเก็บเฉพาะแฮช
    def admin_user_detail(user_id):
        db = get_db()
        user = db.execute("SELECT u.id,u.username,u.name,u.created_at,p.email,p.title,p.student_id,p.faculty,p.major FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=? AND u.role='user'",(user_id,)).fetchone()
        if user is None: abort(404)
        if request.method == 'POST':
            password = request.form.get('password','')
            if not valid_password(password):
                flash('รหัสผ่านใหม่ต้องมี 8–128 ตัวอักษร และมีตัวพิมพ์ใหญ่ A–Z อย่างน้อย 1 ตัว','danger')
            elif password != request.form.get('confirm_password'):
                flash('ยืนยันรหัสผ่านไม่ตรงกัน','danger')
            else:
                db.execute("UPDATE users SET password_hash=? WHERE id=? AND role='user'",(generate_password_hash(password),user_id))
                db.commit()
                flash('ตั้งรหัสผ่านใหม่แล้ว ผู้ใช้ต้องเข้าสู่ระบบอีกครั้ง','success')
                return redirect(url_for('admin_user_detail',user_id=user_id))
        total = db.execute('SELECT COUNT(*) AS total FROM repairs WHERE user_id=?',(user_id,)).fetchone()['total']
        return render_template('admin_user_detail.html',user=user,total=total)

    @app.route('/account', methods=['GET','POST'])
    @login_required
    # บัญชีเดิมเพิ่มอีเมลและข้อมูลสมาชิกได้ โดยไม่เปลี่ยนเจ้าของรายการ
    def account():
        db = get_db()
        if request.method == 'POST':
            try:
                profile = profile_fields(request.form, student=g.user['role']=='user')
                db.execute('INSERT INTO user_profiles(user_id,email,title,student_id,faculty,major) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,title=excluded.title,student_id=excluded.student_id,faculty=excluded.faculty,major=excluded.major', (g.user['id'],*profile.values()))
                db.commit()
                flash('บันทึกข้อมูลบัญชีแล้ว', 'success')
                return redirect(url_for('account'))
            except ValueError as exc:
                flash(str(exc), 'danger')
            except INTEGRITY_ERRORS:
                flash('อีเมลนี้มีบัญชีใช้งานแล้ว', 'danger')
        profile = db.execute('SELECT * FROM user_profiles WHERE user_id=?',(g.user['id'],)).fetchone()
        return render_template('account.html', profile=profile)

    @app.cli.command('retry-emails')
    # ส่งอีเมลที่ยังค้างหลังตั้งค่า SMTP หรือแก้ปัญหาการเชื่อมต่อ
    def retry_emails():
        init_db()
        click.echo('ส่งครบแล้ว' if deliver_pending(get_db()) else 'ยังมีอีเมลรอส่ง ตรวจการตั้งค่า SMTP')

    @app.cli.command('init-db')
    # คำสั่งสร้างตารางโดยเก็บข้อมูลเดิมไว้
    def init_db_command():
        """สร้างตารางโดยไม่ลบข้อมูลเดิม."""
        init_db()
        click.echo('สร้างตารางเรียบร้อย (ข้อมูลเดิมยังอยู่)')

    @app.cli.command('create-admin')
    @click.option('--username', prompt='Admin username')
    @click.option('--name', prompt='Display name', default='ผู้ดูแลระบบ')
    # สร้างบัญชีผู้ดูแลจากข้อมูลที่กรอกใน Terminal
    def create_admin(username, name):
        """สร้าง admin: รับรหัสผ่านแบบซ่อน หรือ ADMIN_PASSWORD."""
        username = username.strip().lower()
        password = os.environ.get('ADMIN_PASSWORD') or click.prompt('Password (8-128 characters, at least one uppercase A-Z)', hide_input=True, confirmation_prompt=True)
        if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username) or not 2 <= len(name.strip()) <= 100 or not valid_password(password):
            raise click.ClickException('ข้อมูลไม่ถูกต้อง: username 3–40, name 2–100, password 8–128 และมี A–Z อย่างน้อย 1 ตัว')
        init_db()
        db = get_db()
        try:
            # บันทึกเป็นชุดเดียว ถ้าขั้นตอนใดผิดพลาดให้ย้อนกลับ
            with db:
                db.execute('INSERT INTO users(username,name,password_hash,role) VALUES(?,?,?,?)',
                           # แปลงรหัสผ่านเป็นแฮช ไม่เก็บรหัสผ่านจริง
                           (username, name.strip(), generate_password_hash(password), 'admin'))
        except INTEGRITY_ERRORS:
            raise click.ClickException('ชื่อผู้ใช้มีอยู่แล้ว ไม่เปลี่ยนสิทธิ์หรือทับรหัสผ่านเดิม')
        click.echo('สร้างบัญชีผู้ดูแลเรียบร้อย')

    @app.cli.command('seed-demo')
    # เพิ่มบัญชีและรายการตัวอย่างสำหรับลองระบบ
    def seed_demo():
        """สร้างนักศึกษาตัวอย่างและรายการ 4 สถานะ ครั้งเดียว."""
        password = os.environ.get('DEMO_PASSWORD') or click.prompt('Demo password (8-128 characters, at least one uppercase A-Z)', hide_input=True, confirmation_prompt=True)
        if not valid_password(password):
            raise click.ClickException('รหัสผ่านต้องมี 8–128 ตัวอักษร และมีตัวพิมพ์ใหญ่ A–Z อย่างน้อย 1 ตัว')
        init_db()
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username='student_demo'").fetchone():
            raise click.ClickException('มี student_demo แล้ว ไม่เพิ่มข้อมูลซ้ำ')
        # บันทึกเป็นชุดเดียว ถ้าขั้นตอนใดผิดพลาดให้ย้อนกลับ
        with db:
            uid = db.execute('INSERT INTO users(username,name,password_hash) VALUES(?,?,?)',
                             # แปลงรหัสผ่านเป็นแฮช ไม่เก็บรหัสผ่านจริง
                             ('student_demo', 'นักศึกษาตัวอย่าง', generate_password_hash(password))).lastrowid
            for i, status in enumerate(key for key in STATUSES if key != 'cancelled'):
                rid = db.execute('INSERT INTO repairs(user_id,equipment,room,description,contact,status) VALUES(?,?,?,?,?,?)',
                                 (uid, ['คอมพิวเตอร์ PC-01', 'เครื่องพิมพ์ PR-02', 'จอภาพ MN-03', 'เมาส์ MS-04'][i], 'ห้องคอมพิวเตอร์ 201', 'ข้อมูลสาธิต: อุปกรณ์ทำงานผิดปกติ กรุณาตรวจสอบ', 'ติดต่อเจ้าหน้าที่ห้องคอมพิวเตอร์', status)).lastrowid
                db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                           (rid, uid, status, 'ข้อมูลสาธิตสถานะเริ่มต้นสำหรับทดลองระบบ'))
        click.echo('สร้าง student_demo และรายการตัวอย่าง 4 รายการแล้ว')
    return app


# ใช้การเชื่อมต่อฐานข้อมูลร่วมกันภายในคำขอเดียว
def get_db():
    from flask import current_app
    if 'db' not in g:
        g.db = connect_database(current_app.config)
    return g.db


# ปิดการเชื่อมต่อเมื่อจบคำขอ
def close_db(error=None):
    db = g.pop('db', None)
    if db:
        db.close()


# เลือก schema ให้ตรงกับฐานข้อมูลแล้วสร้างตาราง
def init_db():
    from flask import current_app
    filename = 'schema_postgres.sql' if current_app.config.get('DATABASE_URL') else 'schema.sql'
    get_db().executescript((Path(current_app.root_path) / filename).read_text(encoding='utf-8'))


# บังคับให้ล็อกอินก่อนใช้หน้าที่ครอบด้วยตัวนี้
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


# ตรวจว่าบัญชีมีสิทธิ์ผู้ดูแลก่อนให้เข้าหน้า
def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user['role'] != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# ดึงรายการและกันผู้ใช้ไม่ให้เปิดข้อมูลของคนอื่น
def get_repair(repair_id):
    row = get_db().execute('SELECT r.*,u.name AS owner,e.reporter_name,e.student_id,e.id AS evidence_id,c.id AS cancelled_id,a.assignee FROM repairs r JOIN users u ON u.id=r.user_id LEFT JOIN repair_evidence e ON e.repair_id=r.id LEFT JOIN repair_cancellations c ON c.repair_id=r.id LEFT JOIN repair_assignments a ON a.repair_id=r.id WHERE r.id=?', (repair_id,)).fetchone()
    if row is None or (g.user['role'] != 'admin' and row['user_id'] != g.user['id']):
        abort(404)
    return display_repairs([row])[0]


def current_db_is_postgres():
    from flask import current_app
    return bool(current_app.config.get('DATABASE_URL'))


if __name__ == '__main__':
    create_app().run(debug=False)
