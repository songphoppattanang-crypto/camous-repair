"""ระบบแจ้งซ่อม: routes, validation, permissions และคำสั่ง CLI ในไฟล์เดียว."""
import os
import re
import secrets
from datetime import timedelta
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import check_password_hash, generate_password_hash
from database import connect_database, INTEGRITY_ERRORS

STATUSES = {'pending': 'รอรับเรื่อง', 'working': 'กำลังดำเนินการ',
            'done': 'เสร็จสิ้น', 'unrepairable': 'ไม่สามารถซ่อมได้'}
csrf = CSRFProtect()


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
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=on_vercel or os.environ.get('COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    csrf.init_app(app)
    app.teardown_appcontext(close_db)

    @app.before_request
    def load_user():
        g.user = None
        if session.get('user_id'):
            g.user = get_db().execute('SELECT * FROM users WHERE id=?',
                                     (session['user_id'],)).fetchone()
            if g.user is None:
                session.clear()

    @app.context_processor
    def common():
        return {'statuses': STATUSES}

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if g.get('user'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/')
    def home():
        if g.user:
            return redirect(url_for('admin_dashboard' if g.user['role'] == 'admin' else 'my_repairs'))
        return render_template('home.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '')
            error = None
            if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username):
                error = 'ชื่อผู้ใช้ต้องเป็นภาษาอังกฤษ ตัวเลข หรือ _ . - จำนวน 3–40 ตัว'
            elif not 2 <= len(name) <= 100:
                error = 'ชื่อผู้แจ้งต้องมี 2–100 ตัวอักษร'
            elif not 10 <= len(password) <= 128:
                error = 'รหัสผ่านต้องมี 10–128 ตัวอักษร'
            elif password != request.form.get('confirm_password'):
                error = 'ยืนยันรหัสผ่านไม่ตรงกัน'
            if error:
                flash(error, 'danger')
            else:
                try:
                    db = get_db()
                    db.execute('INSERT INTO users(username,name,password_hash) VALUES(?,?,?)',
                               (username, name, generate_password_hash(password)))
                    db.commit()
                    flash('สมัครสมาชิกแล้ว กรุณาเข้าสู่ระบบ', 'success')
                    return redirect(url_for('login'))
                except INTEGRITY_ERRORS:
                    flash('ชื่อผู้ใช้นี้ถูกใช้งานแล้ว', 'danger')
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            user = get_db().execute('SELECT * FROM users WHERE username=?',
                                   (request.form.get('username', '').strip().lower(),)).fetchone()
            password = request.form.get('password', '')
            if len(password) <= 128 and user and check_password_hash(user['password_hash'], password):
                session.clear()
                session['user_id'] = user['id']
                session.permanent = True
                return redirect(url_for('home'))
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
        return render_template('login.html')

    @app.post('/logout')
    @login_required
    def logout():
        session.clear()
        flash('ออกจากระบบแล้ว', 'success')
        return redirect(url_for('login'))

    @app.get('/repairs')
    @login_required
    def my_repairs():
        rows = get_db().execute('SELECT * FROM repairs WHERE user_id=? ORDER BY id DESC',
                                (g.user['id'],)).fetchall()
        return render_template('repairs.html', repairs=rows)

    @app.route('/repairs/new', methods=['GET', 'POST'])
    @login_required
    def new_repair():
        if g.user['role'] != 'user':
            abort(403)
        if request.method == 'POST':
            fields = {k: request.form.get(k, '').strip() for k in
                      ('equipment', 'room', 'description', 'contact')}
            limits = {'equipment': (2, 100), 'room': (1, 100),
                      'description': (10, 2000), 'contact': (5, 200)}
            if any(not lo <= len(fields[k]) <= hi for k, (lo, hi) in limits.items()):
                flash('กรอกข้อมูลให้ครบ: อุปกรณ์ 2–100, ห้อง 1–100, อาการ 10–2,000 และข้อมูลติดต่อ 5–200 ตัวอักษร', 'danger')
            else:
                db = get_db()
                with db:
                    cur = db.execute('INSERT INTO repairs(user_id,equipment,room,description,contact) VALUES(?,?,?,?,?)',
                                     (g.user['id'], *fields.values()))
                    db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                               (cur.lastrowid, g.user['id'], 'pending', 'สร้างรายการแจ้งซ่อม'))
                flash('ส่งรายการแจ้งซ่อมแล้ว', 'success')
                return redirect(url_for('repair_detail', repair_id=cur.lastrowid))
        return render_template('new_repair.html')

    @app.get('/repairs/<int:repair_id>')
    @login_required
    def repair_detail(repair_id):
        # ตรวจสิทธิ์ที่ server ทุกครั้ง แม้พิมพ์ URL หรือเปลี่ยนหมายเลขเอง
        row = get_repair(repair_id)
        history = get_db().execute('SELECT h.*,u.name AS actor FROM repair_history h JOIN users u ON u.id=h.actor_id WHERE repair_id=? ORDER BY h.id DESC', (repair_id,)).fetchall()
        return render_template('detail.html', repair=row, history=history)

    @app.get('/admin')
    @admin_required
    def admin_dashboard():
        counts = {s: 0 for s in STATUSES}
        for row in get_db().execute('SELECT status,COUNT(*) AS total FROM repairs GROUP BY status'):
            counts[row['status']] = row['total']
        return render_template('dashboard.html', counts=counts)

    @app.get('/admin/repairs')
    @admin_required
    def admin_repairs():
        q = request.args.get('q', '').strip()[:100]
        status = request.args.get('status', '')
        sql = 'SELECT r.*,u.name AS owner FROM repairs r JOIN users u ON u.id=r.user_id WHERE 1=1'
        params = []
        if q:
            sql += ' AND (r.equipment LIKE ? OR r.room LIKE ? OR u.name LIKE ? OR CAST(r.id AS TEXT)=?)'
            params += ['%' + q + '%'] * 3 + [q]
        if status in STATUSES:
            sql += ' AND r.status=?'
            params.append(status)
        rows = get_db().execute(sql + ' ORDER BY r.id DESC', params).fetchall()
        return render_template('admin_repairs.html', repairs=rows, q=q, selected_status=status)

    @app.post('/admin/repairs/<int:repair_id>/update')
    @admin_required
    def update_repair(repair_id):
        get_repair(repair_id)
        status = request.form.get('status', '')
        note = request.form.get('note', '').strip()
        if status not in STATUSES or not 3 <= len(note) <= 2000:
            flash('เลือกสถานะที่ถูกต้อง และใส่บันทึกการซ่อม 3–2,000 ตัวอักษร', 'danger')
        else:
            db = get_db()
            with db:
                db.execute("UPDATE repairs SET status=?,updated_at=datetime('now','+7 hours') WHERE id=?", (status, repair_id))
                db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                           (repair_id, g.user['id'], status, note))
            flash('บันทึกสถานะและประวัติการซ่อมแล้ว', 'success')
        return redirect(url_for('repair_detail', repair_id=repair_id))

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('error.html', code=400, message='แบบฟอร์มหมดอายุหรือไม่ถูกต้อง กรุณาเปิดหน้าใหม่แล้วลองอีกครั้ง'), 400

    for code, message in [(403, 'คุณไม่มีสิทธิ์ใช้งานหน้านี้'), (404, 'ไม่พบข้อมูลหรือรายการที่คุณเข้าถึงได้'), (413, 'ข้อมูลที่ส่งมีขนาดใหญ่เกินกำหนด')]:
        app.register_error_handler(code, lambda error, c=code, m=message: (render_template('error.html', code=c, message=m), c))

    @app.cli.command('init-db')
    def init_db_command():
        """สร้างตารางโดยไม่ลบข้อมูลเดิม."""
        init_db()
        click.echo('สร้างตารางเรียบร้อย (ข้อมูลเดิมยังอยู่)')

    @app.cli.command('create-admin')
    @click.option('--username', prompt='Admin username')
    @click.option('--name', prompt='Display name', default='ผู้ดูแลระบบ')
    def create_admin(username, name):
        """สร้าง admin: รับรหัสผ่านแบบซ่อน หรือ ADMIN_PASSWORD."""
        username = username.strip().lower()
        password = os.environ.get('ADMIN_PASSWORD') or click.prompt('Password (10-128 characters)', hide_input=True, confirmation_prompt=True)
        if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username) or not 2 <= len(name.strip()) <= 100 or not 10 <= len(password) <= 128:
            raise click.ClickException('ข้อมูลไม่ถูกต้อง: username 3–40, name 2–100, password 10–128')
        init_db()
        db = get_db()
        try:
            with db:
                db.execute('INSERT INTO users(username,name,password_hash,role) VALUES(?,?,?,?)',
                           (username, name.strip(), generate_password_hash(password), 'admin'))
        except INTEGRITY_ERRORS:
            raise click.ClickException('ชื่อผู้ใช้มีอยู่แล้ว ไม่เปลี่ยนสิทธิ์หรือทับรหัสผ่านเดิม')
        click.echo('สร้างบัญชีผู้ดูแลเรียบร้อย')

    @app.cli.command('seed-demo')
    def seed_demo():
        """สร้างนักศึกษาตัวอย่างและรายการ 4 สถานะ ครั้งเดียว."""
        password = os.environ.get('DEMO_PASSWORD') or click.prompt('Demo password (10-128 characters)', hide_input=True, confirmation_prompt=True)
        if not 10 <= len(password) <= 128:
            raise click.ClickException('รหัสผ่านต้องมี 10–128 ตัวอักษร')
        init_db()
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username='student_demo'").fetchone():
            raise click.ClickException('มี student_demo แล้ว ไม่เพิ่มข้อมูลซ้ำ')
        with db:
            uid = db.execute('INSERT INTO users(username,name,password_hash) VALUES(?,?,?)',
                             ('student_demo', 'นักศึกษาตัวอย่าง', generate_password_hash(password))).lastrowid
            for i, status in enumerate(STATUSES):
                rid = db.execute('INSERT INTO repairs(user_id,equipment,room,description,contact,status) VALUES(?,?,?,?,?,?)',
                                 (uid, ['คอมพิวเตอร์ PC-01', 'เครื่องพิมพ์ PR-02', 'จอภาพ MN-03', 'เมาส์ MS-04'][i], 'ห้องคอมพิวเตอร์ 201', 'ข้อมูลสาธิต: อุปกรณ์ทำงานผิดปกติ กรุณาตรวจสอบ', 'ติดต่อเจ้าหน้าที่ห้องคอมพิวเตอร์', status)).lastrowid
                db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                           (rid, uid, status, 'ข้อมูลสาธิตสถานะเริ่มต้นสำหรับทดลองระบบ'))
        click.echo('สร้าง student_demo และรายการตัวอย่าง 4 รายการแล้ว')
    return app


def get_db():
    from flask import current_app
    if 'db' not in g:
        g.db = connect_database(current_app.config)
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    from flask import current_app
    filename = 'schema_postgres.sql' if current_app.config.get('DATABASE_URL') else 'schema.sql'
    get_db().executescript((Path(current_app.root_path) / filename).read_text(encoding='utf-8'))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user['role'] != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def get_repair(repair_id):
    row = get_db().execute('SELECT r.*,u.name AS owner FROM repairs r JOIN users u ON u.id=r.user_id WHERE r.id=?', (repair_id,)).fetchone()
    if row is None or (g.user['role'] != 'admin' and row['user_id'] != g.user['id']):
        abort(404)
    return row


if __name__ == '__main__':
    create_app().run(debug=False)
