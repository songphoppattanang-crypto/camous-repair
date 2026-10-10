# นำระบบขึ้น GitHub + Vercel + PostgreSQL

รุ่นนี้ใช้ **Flask เดิม**: รันในเครื่องใช้ SQLite; บน Vercel ใช้ PostgreSQL ผ่าน `DATABASE_URL`
ไม่ต้องเปลี่ยนเป็น React/Next.js
ไฟล์พร้อม deploy แต่ต้องสร้างฐานข้อมูลและเชื่อมบัญชีของคุณก่อน จึงจะมี URL ออนไลน์จริง

## ภาพรวม

```text
GitHub (โค้ด) → Vercel (เว็บ Flask + HTTPS) → Neon (PostgreSQL)
```

GitHub เก็บเฉพาะโค้ด ไม่เก็บรหัสผ่านหรือข้อมูลผู้ใช้
Vercel รันแอป ส่วน Neon เก็บข้อมูลถาวรแยกจากการ deploy
หากอาจารย์บังคับ SQLite ให้ใช้โหมดในเครื่องหรือ PythonAnywhere แทน
การเปลี่ยนเป็น PostgreSQL สำหรับออนไลน์ควรอธิบายในรายงาน

## 1. ติดตั้งในเครื่อง

แตก ZIP เปิดโฟลเดอร์ `campus-repair` ใน VS Code แล้วเปิด PowerShell
ใช้ Python 3.12 เพื่อให้ตรงกับ Vercel และชุดทดสอบ:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

หากต้องการลอง SQLite ในเครื่องก่อน ดู README; ไม่มี `DATABASE_URL` จะเลือก SQLite
เว็บออนไลน์จะเริ่มจากฐานข้อมูลใหม่ ไม่ย้ายรายการเดิมจาก SQLite อัตโนมัติ

## 2. สร้างฐานข้อมูลฟรีบน Neon

1. ไปที่ https://neon.com แล้วสมัครหรือเข้าสู่ระบบด้วยบัญชีของคุณ
2. สร้าง project เช่น `campus-repair` เลือก **Free** และ region ใกล้ผู้ใช้ หากมี Singapore ให้เลือกได้
3. กด **Connect** เลือก database และ role ของโปรเจกต์
4. คัดลอก **connection string** ที่เป็น `postgresql://...` พร้อม `sslmode=require`
5. สำหรับเว็บใช้ connection แบบ **pooled** เมื่อมีตัวเลือกนี้ เพื่อลดจำนวน connection

connection string มีรหัสผ่านฐานข้อมูล ห้ามอัปโหลดเข้า GitHub ห้ามส่งในแชต หรือใส่ใน README
อย่าเลือก upgrade หรือบริการเสียเงินหากต้องการใช้งานภายในแผนฟรี
ตรวจโควตาปัจจุบันจากหน้า Pricing/Dashboard ของ Neon; แผนฟรีไม่รับประกันทรัพยากรไม่จำกัด

## 3. สร้างตารางและ Admin จากเครื่อง

ไม่ต้องเพิ่มหน้าเว็บสำหรับสร้าง admin และไม่ต้องใช้ Vercel shell:

```powershell
.\.venv\Scripts\python.exe setup_online.py
```

วาง connection string ตอนถาม (ข้อความจะถูกซ่อน) แล้วกำหนด username, ชื่อแสดง และรหัสผ่าน admin
รหัสผ่านจะถามยืนยันแบบซ่อนและต้องมี 10–128 ตัวอักษร
โปรแกรมสร้างตารางและบัญชีโดยเชื่อมฐานข้อมูลออนไลน์จากเครื่องของคุณ ไม่บันทึก connection string ลงไฟล์
`init-db` ไม่ลบตารางหรือข้อมูลเดิม และ `create-admin` ไม่ทับชื่อผู้ใช้เดิม
หากสร้างตารางแล้วแต่สร้าง admin ไม่สำเร็จ สามารถลองคำสั่งนี้ใหม่ได้

สร้าง SECRET_KEY แยกสำหรับเว็บออนไลน์:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

เก็บค่านี้เป็นส่วนตัวเพื่อนำไปตั้งใน Vercel ไม่ต้องวางในโค้ด

## 4. นำโค้ดเข้า GitHub

1. ไป GitHub → **New repository** เลือกบัญชีส่วนตัว ชื่อ `campus-repair` และเลือก **Private**
2. ไม่ต้องสร้าง README จาก GitHub เพราะมีในโปรเจกต์แล้ว
3. อัปโหลด **เนื้อหาในโฟลเดอร์** `campus-repair` ให้ `app.py`, `index.py`, `requirements.txt` อยู่ระดับราก
4. อย่าอัปโหลด ZIP แทนไฟล์โค้ด

ถ้าใช้ Git ใน VS Code เปิด Source Control → Initialize Repository → stage/commit → Publish เป็น Private
ตรวจรายชื่อไฟล์ก่อน publish: ต้องไม่มี `.venv`, `instance`, `.env`, `.vercel` หรือไฟล์ฐานข้อมูล
`.gitignore` มีรายการเหล่านี้ให้แล้ว ส่วน `.env.example` เป็นเพียง placeholder อัปโหลดได้
โฟลเดอร์ `.github/workflows/tests.yml` ให้ GitHub Actions ทดสอบ SQLite และ PostgreSQL อัตโนมัติ
GitHub Actions ใน private repo มีโควตา ให้ตรวจการใช้งานของบัญชี

## 5. เชื่อม Vercel

1. สมัคร/เข้าสู่ระบบ https://vercel.com ด้วยบัญชี GitHub
2. **Add New → Project** แล้วเลือก repository `campus-repair`
3. ให้ Vercel เข้าถึงเฉพาะ repository ที่ต้องการ
4. **Framework Preset: Flask**; **Root Directory: ระดับรากที่มี app.py**
5. โค้ดกำหนด entrypoint `index:app` และ build `python build.py` ไว้แล้ว
6. เพิ่ม Environment Variables ก่อน Deploy:

| ชื่อ | ค่าที่ใช้ |
| --- | --- |
| DATABASE_URL | connection string PostgreSQL ของฐานข้อมูลที่สร้างตารางและ admin แล้ว |
| SECRET_KEY | random secret ที่สร้างในขั้นตอน 3 |
| COOKIE_SECURE | `1` |

ไม่ต้องเพิ่ม `ADMIN_PASSWORD` บน Vercel เพราะสร้าง admin จาก CLI แล้ว
ไม่ต้องกำหนด `VERCEL` เอง; แพลตฟอร์มใส่ให้อัตโนมัติ
แอปจะหยุดพร้อมข้อความตั้งค่าเมื่อบน Vercel ไม่มี DATABASE_URL/SECRET_KEY ไม่ fallback เป็น SQLite

7. กด **Deploy** แล้วเปิด URL `https://ชื่อโปรเจกต์.vercel.app`
8. ทุกครั้งที่แก้ environment ต้อง **Redeploy** เพื่อให้ deployment ใหม่ใช้ค่าใหม่
9. หากระบบ Deployment Protection ขอ login ให้ปรับตามผู้ชมที่ต้องการจาก dashboard ของคุณ

**Preview:** ถ้าใช้ preview deployment ต้องตั้ง environment ของ Preview ด้วย แนะนำใช้ฐานข้อมูล/branch แยกจาก Production
ไม่ควรให้ preview จาก branch ที่ไม่ไว้ใจเชื่อมข้อมูลจริง
หากใช้เพียง Production ให้ทดสอบ URL Production ก่อน

## 6. ตรวจหลัง deploy

1. เปิดหน้าแรกและหน้า login: CSS ต้องโหลดครบทั้งเดสก์ท็อปและมือถือ
2. สมัครสมาชิกใหม่และแจ้งซ่อมหนึ่งรายการ
3. ออกจากระบบแล้ว login Admin ที่สร้างไว้ ตรวจ dashboard และเปลี่ยนสถานะพร้อมบันทึก
4. Login User อีกครั้ง ต้องเห็นประวัติที่อัปเดต
5. สมัคร User อีกคน เปิด URL รายการของคนแรก ต้องได้ 404 และเปิด `/admin` ต้องได้ 403
6. Redeploy หนึ่งครั้ง: รายการเดิมต้องยังอยู่ เพราะข้อมูลเก็บใน PostgreSQL

## 7. สาเหตุที่พบบ่อย

| อาการ | วิธีตรวจ |
| --- | --- |
| Missing DATABASE_URL / SECRET_KEY | เพิ่ม environment ใน scope ที่ถูกต้อง แล้ว Redeploy |
| relation users does not exist | รัน setup_online.py กับฐานข้อมูลเดียวกับ Vercel |
| เชื่อมฐานข้อมูลไม่ได้ | ตรวจ connection string, password, sslmode และสถานะ Neon; ไม่พิมพ์ URL ลง public logs |
| ชื่อ admin ซ้ำ | ใช้บัญชีที่สร้างไว้หรือเลือกชื่อใหม่ ไม่มีการทับบัญชีเดิม |
| CSS 404 | ตรวจ build log ว่ารัน build.py และ Root Directory ถูกต้อง |
| Cookie/login ไม่ทำงาน | เปิดผ่าน HTTPS และอย่าเปิดหลาย URL คนละโดเมนสลับ session |
| แบบฟอร์มหมดอายุ | reload แล้วกรอกใหม่; SECRET_KEY ต้องเหมือนเดิมระหว่าง deploy |
| หน้า Preview เข้าไม่ได้ | ตรวจ Deployment Protection และ environment ของ Preview |

## 8. สำรองข้อมูลและขอบเขตฟรี

ใช้การสำรอง/ส่งออกจาก Neon หรือ `pg_dump` และเก็บสำรองส่วนตัว อย่าเก็บข้อมูลติดต่อไว้ใน GitHub
รหัสผ่านฐานข้อมูลและ secret ควรเก็บใน password manager หากรั่วต้องเปลี่ยนและ Redeploy
Vercel Hobby ใช้สำหรับโปรเจกต์ส่วนบุคคลที่ไม่ใช่เชิงพาณิชย์และมีโควตา;
การใช้งานประจำทั้งสถานศึกษาควรประเมินเงื่อนไขและทรัพยากรอีกครั้ง
รุ่นนี้ยังไม่มี rate limiting login; ก่อนเปิดรับผู้ใช้ทั่วไปควรเพิ่มการจำกัดความถี่

เอกสารทางการ (ตรวจวันที่ 10 ตุลาคม 2026):
- https://vercel.com/docs/frameworks/backend/flask
- https://vercel.com/docs/functions/runtimes
- https://vercel.com/docs/plans/hobby
- https://neon.com/pricing
- https://neon.com/docs/connect/connection-pooling
