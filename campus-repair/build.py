# เตรียมไฟล์รูปและ CSS ให้ Vercel เสิร์ฟผ่านโฟลเดอร์ public
"""Vercel เสิร์ฟไฟล์ public ผ่าน CDN; คัดลอก CSS โดยคง URL /static/... เดิม."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
# คัดลอก static ไป public โดยคง URL เดิม
shutil.copytree(root / 'static', root / 'public' / 'static', dirs_exist_ok=True)
print('Static assets prepared for Vercel')
