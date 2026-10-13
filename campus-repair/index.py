# จุดเริ่มต้นที่ Vercel ใช้โหลดเว็บ Flask
"""Vercel จะ import Flask instance ชื่อ app จากไฟล์นี้."""
from app import create_app

# สร้างแอปให้ระบบโฮสต์เรียกใช้
app = create_app()
