"""ชั้นเชื่อมต่อเล็ก ๆ: SQL เดิมใช้ SQLite ในเครื่อง หรือ PostgreSQL เมื่อมี DATABASE_URL.

ใช้ placeholders เสมอ การแปลง SQL ด้านล่างใช้เฉพาะ SQL ที่เขียนในโปรเจกต์
ไม่รับ SQL จากผู้ใช้ และไม่ใช่ตัวแปลง SQL สำหรับงานทั่วไป
"""
import sqlite3
import psycopg
from psycopg.rows import dict_row

INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
THAI_NOW = "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Bangkok', 'YYYY-MM-DD HH24:MI:SS')"


class Record(dict):
    """อ่านได้ทั้ง row['name'] และ row[0] เหมือน sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor, inserted_id=None):
        self.cursor = cursor
        self.lastrowid = inserted_id

    def fetchone(self):
        row = self.cursor.fetchone()
        return Record(row) if row is not None else None

    def fetchall(self):
        return [Record(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PostgresDB:
    def __init__(self, url, schema=None):
        # autocommit ป้องกัน SELECT ค้าง transaction; with db ใช้ transaction จริง
        kwargs = {'autocommit': True, 'row_factory': dict_row, 'connect_timeout': 10}
        if schema:
            kwargs['options'] = '-c search_path=' + schema
        self.connection = psycopg.connect(url, **kwargs)
        self.transactions = []

    def execute(self, sql, params=()):
        sql = sql.replace("datetime('now','+7 hours')", THAI_NOW).replace('?', '%s')
        is_insert = sql.lstrip().upper().startswith('INSERT INTO ')
        if is_insert:
            sql = sql.rstrip().rstrip(';') + ' RETURNING id'
        cursor = self.connection.execute(sql, params)
        inserted_id = cursor.fetchone()['id'] if is_insert else None
        return Cursor(cursor, inserted_id)

    def executescript(self, script):
        with self:
            for statement in script.split(';'):
                if statement.strip():
                    self.connection.execute(statement)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        transaction = self.connection.transaction()
        transaction.__enter__()
        self.transactions.append(transaction)
        return self

    def __exit__(self, *args):
        return self.transactions.pop().__exit__(*args)


def connect_database(config):
    if config.get('DATABASE_URL'):
        return PostgresDB(config['DATABASE_URL'], config.get('DATABASE_SCHEMA'))
    db = sqlite3.connect(config['DATABASE'])
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db
