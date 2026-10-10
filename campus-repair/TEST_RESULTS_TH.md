# ผลการทดสอบรุ่น GitHub + Vercel

วันที่: 10 ตุลาคม 2026 (ประเทศไทย)

## สภาพแวดล้อม

- Windows, Python 3.12
- ติดตั้ง requirements ใน virtual environment ใหม่ได้จริง
- PostgreSQL 18.6 จาก binary ของ EDB ทดสอบแยกในเครื่อง และเชื่อมผ่าน psycopg 3.2.13
- PostgreSQL ทดสอบเฉพาะ localhost; ไม่ใช่ฐานข้อมูลใช้งานจริงหรือ Neon ของผู้ใช้

## ผลทดสอบ

| การตรวจ | ผล |
| --- | --- |
| unittest กับ SQLite | ผ่าน 13 ชุด |
| unittest ชุดเดียวกันกับ PostgreSQL จริง | ผ่าน 13 ชุด |
| สมัครสมาชิก / hash / ชื่อซ้ำ / ป้องกันสมัครเป็น admin | ผ่านทั้งสองฐานข้อมูล |
| Login / logout / session / สิทธิ์ User และ Admin | ผ่านทั้งสองฐานข้อมูล |
| User A และ B เข้าถึงรายการข้ามกันไม่ได้ | ผ่านทั้งสองฐานข้อมูล |
| แจ้งซ่อม → Admin เปลี่ยนครบ 4 สถานะ → User อ่านประวัติ | ผ่านทั้งสองฐานข้อมูล |
| ค้นหา / กรอง / validation / CSRF / HTML escaping | ผ่านทั้งสองฐานข้อมูล |
| ประวัติล้มเหลวแล้ว rollback รายการพร้อมกัน | ผ่านทั้งสองฐานข้อมูล |
| CLI init-db / create-admin / seed-demo | ผ่านทั้งสองฐานข้อมูล |
| บน Vercel ไม่มี SECRET_KEY หรือ DATABASE_URL | หยุดด้วยข้อผิดพลาดการตั้งค่า |
| Flask factory บน Vercel | ไม่เขียนโฟลเดอร์ instance; secure cookies เปิด |
| requirements และ pyproject dependencies ตรงกัน | ผ่าน |
| build.py คัดลอกไฟล์ CSS ไป public/static | ผ่าน |
| import index:app ในโหมด Vercel | ผ่านโดยตั้งค่าฐานข้อมูลทดสอบ |

ชุดทดสอบใช้ฐานข้อมูลหรือ schema ใหม่ทุกครั้ง ไม่เปลี่ยนข้อมูลจริง
GitHub Actions มี configuration ทดสอบ SQLite + PostgreSQL 16 แต่ยังไม่ได้รันบน GitHub จริง

## สิ่งที่ยังไม่ได้ยืนยัน

- ยังไม่ได้สร้างหรือเผยแพร่ repository บนบัญชี GitHub ของผู้ใช้
- ยังไม่ได้สร้าง Neon หรือ deploy ผ่านบัญชี Vercel ของผู้ใช้ จึงยังไม่มี URL เว็บไซต์จริง
- ยังไม่ได้ทดสอบ Vercel build บนระบบ cloud หรือ connection pooling ของ Neon
- ยังไม่ได้ตรวจภาพหน้าจอผ่าน browser; หน้าจอคงจากรุ่นเดิม
  เครื่องมือ browser เคยปฏิเสธการเข้าถึง localhost ตามสิทธิ์ จึงไม่ข้ามข้อจำกัดนั้น
- ไม่รับประกันจำนวนผู้ใช้หรือความพร้อมใช้งานของแผนฟรี และยังไม่มี login rate limiting

## ไฟล์ส่งมอบ

ZIP ไม่มีฐานข้อมูล, secret.key, .env จริง, virtual environment หรือบัญชีทดสอบ
ทำตาม DEPLOY_VERCEL_TH.md เพื่อสร้างฐานข้อมูล/admin และตั้ง environment ของคุณก่อน Deploy
โหมด SQLite ยังรันด้วยคำสั่งเดิมใน README ได้
