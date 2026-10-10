"""สร้างตารางและ admin บน PostgreSQL จากเครื่องของผู้ใช้ ไม่บันทึก connection string."""
import getpass
import os
import secrets
import subprocess
import sys
from pathlib import Path


def main():
    print('เตรียมฐานข้อมูลออนไลน์: ใช้ฐานข้อมูลใหม่สำหรับโปรเจกต์นี้')
    url = getpass.getpass('วาง PostgreSQL connection string (ซ่อนข้อความ): ').strip()
    if not url.startswith(('postgresql://', 'postgres://')):
        print('ต้องเป็น PostgreSQL connection string', file=sys.stderr)
        return 1
    env = os.environ.copy()
    env.pop('VERCEL', None)
    env['DATABASE_URL'] = url
    env['SECRET_KEY'] = secrets.token_hex(32)
    root = Path(__file__).resolve().parent
    for command in ('init-db', 'create-admin'):
        result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', command],
                                cwd=root, env=env)
        if result.returncode:
            print('ขั้นตอนนี้ไม่สำเร็จ ตรวจการเชื่อมต่อหรือชื่อบัญชี แล้วลองใหม่', file=sys.stderr)
            return result.returncode
    print('ฐานข้อมูลและ admin พร้อมแล้ว ตั้ง DATABASE_URL/SECRET_KEY ใน Vercel ก่อน deploy')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
