# เพิ่มตารางที่ยังขาดให้ฐานข้อมูลเดิมก่อนอัปเดตเว็บ
"""เพิ่มตารางข้อมูลผู้แจ้งและรูปภาพในฐานข้อมูลเดิม ไม่ลบรายการเดิม."""
import getpass
import os
import secrets
from app import create_app, init_db

if __name__ == '__main__':
    url=getpass.getpass('วาง PostgreSQL connection string เดิม (ซ่อนข้อความ): ').strip()
    if not url.startswith(('postgresql://','postgres://')):
        raise SystemExit('ต้องเป็น PostgreSQL connection string')
    os.environ['DATABASE_URL']=url
    os.environ['SECRET_KEY']=secrets.token_hex(32)
    os.environ.pop('VERCEL',None)
    with create_app().app_context():
        init_db()
    print('เพิ่มตารางสมาชิก รูปภาพ และอีเมลแล้ว ข้อมูลเดิมยังอยู่ครบ')
