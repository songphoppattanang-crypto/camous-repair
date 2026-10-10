"""ทดสอบ flow จริงผ่าน Flask test client โดยเปิด CSRF protection."""
import os
import re
import sys
import unittest
import uuid
import psycopg
from psycopg import sql
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, get_db, init_db
from werkzeug.security import generate_password_hash, check_password_hash


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).resolve().parents[1] / 'instance' / ('test-' + uuid.uuid4().hex + '.sqlite3')
        self.pg_url = os.environ.get('TEST_DATABASE_URL')
        self.pg_schema = 'test_' + uuid.uuid4().hex if self.pg_url else None
        if self.pg_url:
            with psycopg.connect(self.pg_url, autocommit=True) as db:
                db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.pg_schema)))
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only-key',
                               'DATABASE': str(self.db_path), 'DATABASE_URL': self.pg_url,
                               'DATABASE_SCHEMA': self.pg_schema})
        self.client = self.app.test_client()
        with self.app.app_context():
            init_db()
            db = get_db()
            for username, role in [('alice','user'), ('bob','user'), ('admin','admin')]:
                db.execute('INSERT INTO users(username,name,password_hash,role) VALUES(?,?,?,?)',
                           (username, username, generate_password_hash('Testing12345!'), role))
            db.commit()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        if self.pg_url:
            with psycopg.connect(self.pg_url, autocommit=True) as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.pg_schema)))

    def token(self, path):
        response = self.client.get(path)
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match, 'CSRF token must exist on ' + path)
        return match.group(1)

    def login(self, username='alice'):
        return self.client.post('/login', data={'csrf_token': self.token('/login'), 'username': username, 'password': 'Testing12345!'})

    def logout(self):
        return self.client.post('/logout', data={'csrf_token': self.token('/repairs')})

    def repair(self, description='เปิดเครื่องแล้วหน้าจอไม่แสดงภาพ'):
        return self.client.post('/repairs/new', data={'csrf_token': self.token('/repairs/new'), 'equipment': 'PC-001', 'room': 'ห้อง 201', 'description': description, 'contact': 'โทร 0812345678'})

    def test_register_hash_duplicate_and_validation(self):
        data = {'csrf_token': self.token('/register'), 'username': 'newstudent', 'name': 'นักศึกษาใหม่', 'password': 'NewPassword12!', 'confirm_password': 'NewPassword12!','role':'admin'}
        self.assertEqual(self.client.post('/register', data=data).status_code, 302)
        with self.app.app_context():
            user = get_db().execute("SELECT * FROM users WHERE username='newstudent'").fetchone()
            self.assertEqual(user['role'], 'user')
            self.assertNotEqual(user['password_hash'], data['password'])
            self.assertTrue(check_password_hash(user['password_hash'], data['password']))
        self.assertIn('ถูกใช้งานแล้ว', self.client.post('/register', data=data).get_data(as_text=True))
        data.update(username='shortpw', password='short', confirm_password='short')
        self.assertIn('10–128', self.client.post('/register', data=data).get_data(as_text=True))

    def test_login_logout_and_wrong_password(self):
        bad = self.client.post('/login', data={'csrf_token':self.token('/login'),'username':'alice','password':'incorrect'})
        self.assertIn('ไม่ถูกต้อง', bad.get_data(as_text=True))
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get('/repairs').status_code, 200)
        self.assertEqual(self.logout().status_code, 302)
        self.assertEqual(self.client.get('/repairs').status_code, 302)

    def test_user_cannot_access_other_user_or_admin(self):
        self.login()
        self.repair()
        self.logout()
        self.login('bob')
        self.assertEqual(self.client.get('/repairs/1').status_code, 404)
        self.assertNotIn('PC-001', self.client.get('/repairs').get_data(as_text=True))
        self.assertEqual(self.client.get('/admin').status_code, 403)
        self.assertEqual(self.client.get('/admin/repairs').status_code, 403)
        response = self.client.post('/admin/repairs/1/update', data={'csrf_token':self.token('/repairs'),'status':'done','note':'ปลอมสิทธิ์'})
        self.assertEqual(response.status_code, 403)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT status FROM repairs').fetchone()['status'], 'pending')

    def test_complete_admin_status_history_search_flow(self):
        self.login()
        self.assertEqual(self.repair().status_code, 302)
        self.logout()
        self.login('admin')
        self.assertEqual(self.client.get('/admin').status_code, 200)
        for status in ('working','done','unrepairable','pending'):
            response = self.client.post('/admin/repairs/1/update', data={'csrf_token': self.token('/repairs/1'),'status':status,'note':'ตรวจสอบอุปกรณ์และบันทึกผล ' + status})
            self.assertEqual(response.status_code, 302)
        self.assertIn('PC-001', self.client.get('/admin/repairs?q=PC-001&status=pending').get_data(as_text=True))
        self.assertNotIn('PC-001', self.client.get('/admin/repairs?status=done').get_data(as_text=True))
        self.logout()
        self.login()
        self.assertIn('ตรวจสอบอุปกรณ์', self.client.get('/repairs/1').get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM repair_history').fetchone()[0], 5)

    def test_csrf_for_all_mutations(self):
        for path in ('/login','/register','/logout','/repairs/new','/admin/repairs/1/update'):
            self.assertEqual(self.client.post(path, data={}).status_code, 400)
        self.assertEqual(self.client.post('/login',data={'csrf_token':'forged'}).status_code, 400)
        self.assertEqual(self.client.get('/logout').status_code, 405)

    def test_validation_and_parameterized_queries(self):
        self.login()
        self.assertEqual(self.repair(description='สั้น').status_code, 200)
        self.repair()
        self.logout()
        self.login('admin')
        for status, note in [('invalid','มีบันทึก'),('done','')]:
            self.client.post('/admin/repairs/1/update', data={'csrf_token':self.token('/repairs/1'),'status':status,'note':note})
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT status FROM repairs').fetchone()[0], 'pending')
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM repairs').fetchone()[0], 1)
        self.assertEqual(self.client.get("/admin/repairs?q=' OR 1=1 --").status_code, 200)

    def test_html_escaping(self):
        self.login()
        self.repair(description='<script>alert(1)</script>')
        html = self.client.get('/repairs/1').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_transaction_rolls_back_when_history_fails(self):
        with self.app.app_context():
            db = get_db()
            with self.assertRaises(Exception):
                with db:
                    rid = db.execute('INSERT INTO repairs(user_id,equipment,room,description,contact) VALUES(?,?,?,?,?)',
                                     (1,'rollback-device','201','transaction test','contact')).lastrowid
                    # FK ของผู้บันทึกไม่ถูกต้อง ต้องยกเลิกทั้งรายการและ history
                    db.execute('INSERT INTO repair_history(repair_id,actor_id,status,note) VALUES(?,?,?,?)',
                               (rid,99999,'pending','must fail'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM repairs').fetchone()[0], 0)

    def test_cli_safe_admin_seed_and_idempotent_init(self):
        runner = self.app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['init-db']).exit_code, 0)
        with patch.dict(os.environ, {'ADMIN_PASSWORD':'AdminTesting123!' } ):
            self.assertEqual(runner.invoke(args=['create-admin','--username','newadmin','--name','ผู้ดูแล']).exit_code, 0)
            self.assertNotEqual(runner.invoke(args=['create-admin','--username','alice','--name','ผู้ดูแล']).exit_code, 0)
        with patch.dict(os.environ, {'DEMO_PASSWORD':'DemoTesting123!'}):
            self.assertEqual(runner.invoke(args=['seed-demo']).exit_code, 0)
            self.assertNotEqual(runner.invoke(args=['seed-demo']).exit_code, 0)
        self.assertEqual(runner.invoke(args=['init-db']).exit_code, 0)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT role FROM users WHERE username='alice'").fetchone()[0], 'user')
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM repairs').fetchone()[0], 4)

    def test_public_pages_assets_missing_and_guest(self):
        for path in ('/','/login','/register','/static/style.css','/static/vendor/bootstrap.min.css'):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        for path in ('/admin','/repairs','/repairs/new','/repairs/1','/admin/repairs'):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.login()
        self.assertEqual(self.client.get('/repairs/9999').status_code, 404)
        self.assertIn('no-store', self.client.get('/repairs').headers['Cache-Control'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
