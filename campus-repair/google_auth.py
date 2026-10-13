"""Google OIDC: Authlib ตรวจลายเซ็น ID token, issuer, audience, expiry, state และ nonce.

ผูกบัญชีด้วย Google sub ไม่ใช่ชื่อหรืออีเมล; เชื่อมบัญชีเก่าได้หลัง login บัญชีเดิมเท่านั้น
ไม่มีการเก็บ access token, refresh token หรือรหัสผ่าน Google
"""
import secrets
import time
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from joserfc.errors import JoseError
from requests.exceptions import RequestException
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, session, url_for
from werkzeug.security import generate_password_hash
from database import INTEGRITY_ERRORS


def init_google(app):
    from app import get_db
    bp = Blueprint('google_auth', __name__)
    keys = ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI')
    enabled = all(app.config.get(k) for k in keys)
    if enabled:
        uri = urlparse(app.config['GOOGLE_REDIRECT_URI'])
        if uri.scheme != 'https' and not (uri.scheme == 'http' and uri.hostname in ('localhost','127.0.0.1') and not app.config.get('ON_VERCEL')):
            raise RuntimeError('Google redirect URI requires HTTPS (localhost allowed for local testing)')
        if uri.path != '/auth/google/callback' or uri.query or uri.fragment or not uri.hostname:
            raise RuntimeError('Google redirect URI must end with /auth/google/callback')
    oauth = OAuth(app)
    google = oauth.register(
        name='google', client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':'openid email profile', 'code_challenge_method':'S256', 'timeout':15},
    )
    app.extensions['google_client'] = google

    @app.context_processor
    def google_context():
        return {'google_enabled': enabled}

    def require_enabled():
        if not enabled:
            abort(404)

    def start_flow(link_user_id=None):
        # เริ่มได้ทีละ flow ต่อ session; เก็บ purpose และเวลาที่ server ลง signed session
        nonce = secrets.token_urlsafe(32)
        session['google_flow'] = {'link_user_id':link_user_id, 'started':time.time(), 'nonce':nonce}
        try:
            return google.authorize_redirect(app.config['GOOGLE_REDIRECT_URI'],
                                             nonce=nonce, prompt='select_account')
        except (OAuthError, RequestException, ValueError):
            session.pop('google_flow', None)
            flash('เชื่อมต่อ Google ไม่สำเร็จ กรุณาลองใหม่', 'danger')
            return redirect(url_for('login'))

    @bp.post('/auth/google/login')
    def login_google():
        require_enabled()
        if g.user:
            return redirect(url_for('home'))
        return start_flow()

    @bp.get('/account/google')
    def account():
        require_enabled()
        if not g.user:
            return redirect(url_for('login'))
        if g.user['role'] != 'user':
            abort(403)
        identity = get_db().execute('SELECT * FROM google_identities WHERE user_id=?', (g.user['id'],)).fetchone()
        return render_template('google_account.html', identity=identity)

    @bp.post('/auth/google/link')
    def link_google():
        require_enabled()
        if not g.user:
            return redirect(url_for('login'))
        if g.user['role'] != 'user':
            abort(403)
        if get_db().execute('SELECT id FROM google_identities WHERE user_id=?', (g.user['id'],)).fetchone():
            flash('บัญชีนี้เชื่อม Google แล้ว', 'info')
            return redirect(url_for('google_auth.account'))
        return start_flow(g.user['id'])

    @bp.get('/auth/google/callback')
    def callback():
        require_enabled()
        flow = session.pop('google_flow', None)
        if not flow or time.time() - flow['started'] > 600:
            flash('คำขอเข้าสู่ระบบหมดอายุ กรุณาลองใหม่', 'danger')
            return redirect(url_for('login'))
        try:
            # ไม่อ่าน userinfo จาก query/form; ได้จาก ID token ที่ Authlib ตรวจสอบแล้วเท่านั้น
            token = google.authorize_access_token()
            info = token.get('userinfo')
            if not token.get('id_token') or not info:
                raise ValueError('Missing verified identity')
            if not secrets.compare_digest(str(info.get('nonce', '')), flow['nonce']):
                raise ValueError('Invalid nonce')
            sub = info.get('sub')
            email = info.get('email')
            if not isinstance(sub, str) or not 1 <= len(sub) <= 255 or info.get('email_verified') is not True or not isinstance(email, str) or not 3 <= len(email) <= 320:
                raise ValueError('Invalid verified identity')
            link_id = flow.get('link_user_id')
            db = get_db()
            identity = db.execute('SELECT i.*,u.role FROM google_identities i JOIN users u ON u.id=i.user_id WHERE i.google_sub=?', (sub,)).fetchone()
            if link_id is not None:
                # ต้องยังอยู่ใน session ของบัญชีที่เริ่มเชื่อม และไม่ให้ Google เพิ่มสิทธิ์ admin
                if not g.user or g.user['id'] != link_id or g.user['role'] != 'user':
                    raise ValueError('Link session changed')
                if identity and identity['user_id'] != link_id:
                    flash('บัญชี Google นี้เชื่อมกับผู้ใช้อื่นแล้ว ไม่สามารถย้ายบัญชีได้', 'danger')
                    return redirect(url_for('google_auth.account'))
                if not identity:
                    with db:
                        db.execute('INSERT INTO google_identities(user_id,google_sub,email) VALUES(?,?,?)', (link_id,sub,email))
                flash('เชื่อม Google แล้ว รายการแจ้งซ่อมเดิมยังอยู่ในบัญชีนี้', 'success')
                return redirect(url_for('google_auth.account'))
            if identity:
                if identity['role'] != 'user':
                    raise ValueError('Admin requires password login')
                user_id = identity['user_id']
            else:
                name = str(info.get('name') or 'ผู้ใช้ Google').strip()[:100] or 'ผู้ใช้ Google'
                # สร้าง hash ของรหัสสุ่มที่ไม่มีใครทราบ เพื่อคง schema เดิม ไม่เปิดช่อง password login
                with db:
                    user_id = db.execute('INSERT INTO users(username,name,password_hash,role) VALUES(?,?,?,?)',
                                         ('google_' + secrets.token_hex(12), name, generate_password_hash(secrets.token_urlsafe(64)), 'user')).lastrowid
                    db.execute('INSERT INTO google_identities(user_id,google_sub,email) VALUES(?,?,?)', (user_id,sub,email))
            session.clear()
            session['user_id'] = user_id
            session.permanent = True
            return redirect(url_for('my_repairs'))
        except (OAuthError, JoseError, RequestException, ValueError, *INTEGRITY_ERRORS):
            # ไม่ส่ง error provider/token/secret ลงหน้าเว็บหรือ flash
            flash('เข้าสู่ระบบหรือเชื่อม Google ไม่สำเร็จ กรุณาเริ่มใหม่ หากมีบัญชีเดิมให้เข้าสู่ระบบด้วยรหัสผ่านก่อนเชื่อม', 'danger')
            return redirect(url_for('login'))

    app.register_blueprint(bp)
