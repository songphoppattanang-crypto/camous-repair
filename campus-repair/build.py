"""Vercel เสิร์ฟไฟล์ public ผ่าน CDN; คัดลอก CSS โดยคง URL /static/... เดิม."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
shutil.copytree(root / 'static', root / 'public' / 'static', dirs_exist_ok=True)
print('Static assets prepared for Vercel')
