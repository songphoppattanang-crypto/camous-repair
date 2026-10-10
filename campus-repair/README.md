# ระบบแจ้งซ่อมและติดตามสถานะการซ่อมอุปกรณ์คอมพิวเตอร์ภายในสถานศึกษา

โปรเจกต์รายวิชา Python ใช้ **Python Flask + SQLite + HTML/Jinja + CSS + Bootstrap 5**
เว็บไซต์ภาษาไทยโทนฟ้าขาว รองรับมือถือ ไม่มีบริการเสียเงิน ไม่มี API ภายนอก
Bootstrap เก็บในโปรเจกต์ จึงไม่ต้องใช้อินเทอร์เน็ตขณะเปิดเว็บ หลังติดตั้ง dependencies แล้ว

**รุ่น 2: พร้อมเตรียม deploy บน GitHub + Vercel** ดู [DEPLOY_VERCEL_TH.md](DEPLOY_VERCEL_TH.md)
ในเครื่องยังใช้ SQLite ตามคู่มือเดิม; หากกำหนด `DATABASE_URL` จะใช้ PostgreSQL ภายนอกผ่าน psycopg
โหมดออนไลน์ต้องใช้อินเทอร์เน็ตเพื่อเชื่อมฐานข้อมูล โดยไม่มี frontend framework เพิ่ม
แนะนำ Python 3.12 ซึ่งเป็นเวอร์ชันที่ทดสอบและกำหนดให้ Vercel ใช้

## 1. สิ่งที่ระบบทำได้

| บทบาท | ความสามารถ |
| --- | --- |
| ผู้ใช้ | สมัครสมาชิก, เข้าสู่ระบบ, ออกจากระบบ, แจ้งซ่อม, ดูเฉพาะรายการของตัวเองและประวัติการซ่อม |
| ผู้ดูแล | เข้าสู่ระบบ, ดูจำนวนแยก 4 สถานะ, ค้นหารายการทั้งหมด, กรองสถานะ, เปลี่ยนสถานะ, บันทึกการซ่อม |

สถานะ: **รอรับเรื่อง → กำลังดำเนินการ → เสร็จสิ้น / ไม่สามารถซ่อมได้**
ผู้ดูแลสามารถย้อนสถานะได้เมื่อต้องตรวจซ้ำ โดยต้องใส่บันทึกทุกครั้งและเก็บประวัติไว้
ระบบไม่ลบรายการหรือประวัติผ่านหน้าเว็บ เพื่อรักษาหลักฐานการดำเนินงาน

## 2. เตรียม Windows และ VS Code

1. ติดตั้ง Python 3.12 ขึ้นไปจาก https://www.python.org/downloads/windows/ (แนะนำ 3.12 หรือ 3.13) และเลือก **Add Python to PATH**
2. ติดตั้ง VS Code และส่วนขยาย Python ของ Microsoft
3. แตก ZIP แล้วใช้ **File → Open Folder** เปิดโฟลเดอร์ `campus-repair` ที่มี `app.py`
4. เปิด **Terminal → New Terminal** เลือก PowerShell

ตรวจ Python และสร้าง virtual environment:

```powershell
py --version
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

คำสั่งทั้งหมดในคู่มือนี้เรียก Python ของ `.venv` โดยตรง จึงไม่ต้องเปลี่ยน Execution Policy เพื่อ activate
ใน VS Code กด `Ctrl+Shift+P` → **Python: Select Interpreter** → เลือก `.venv\Scripts\python.exe`

## 3. สร้างฐานข้อมูลและผู้ดูแล

```powershell
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app create-admin --username admin --name "ผู้ดูแลระบบ"
```

คำสั่งสร้าง admin จะถามรหัสผ่านและถามยืนยันแบบซ่อน ใช้ 10–128 ตัวอักษร เช่น วลีที่จำง่ายแต่เดายาก
ชื่อ `admin` เป็นเพียงชื่อบัญชี ไม่มีรหัสผ่านเริ่มต้นในโค้ด
หากชื่อมีอยู่แล้ว คำสั่งจะหยุด ไม่เปลี่ยนผู้ใช้เดิมเป็น admin และไม่ทับรหัสผ่าน
`init-db` สร้างตารางที่ยังไม่มี โดยไม่ลบข้อมูลเดิม

หากจำเป็นต้องใช้ environment แทน prompt:

```powershell
$env:ADMIN_PASSWORD = Read-Host "กำหนดรหัสผ่าน admin" -MaskInput
.\.venv\Scripts\python.exe -m flask --app app create-admin --username admin --name "ผู้ดูแลระบบ"
Remove-Item Env:ADMIN_PASSWORD
```

`-MaskInput` ใช้ได้ใน PowerShell 7; Windows PowerShell 5.1 ให้ใช้คำสั่งแบบ prompt ด้านบน
อย่าใส่รหัสผ่านจริงในไฟล์หรือในคำสั่งที่ถูกเก็บในประวัติ terminal

## 4. ข้อมูลตัวอย่าง (เลือกใช้)

```powershell
.\.venv\Scripts\python.exe -m flask --app app seed-demo
```

กำหนดรหัสผ่าน demo ตาม prompt จะได้บัญชี **student_demo** และข้อมูลอุปกรณ์ตัวอย่าง 4 รายการ ครบทุกสถานะ
ใช้รหัสผ่านที่คุณเพิ่งตั้งเพื่อ login ไม่มีรหัสผ่านสาธิตฝังในไฟล์
สั่งซ้ำแล้วจะหยุดเพื่อไม่เพิ่มข้อมูลซ้ำ ข้อมูลทั้งหมดเป็นข้อมูลสมมติ
ผู้ใช้สามารถสมัครสมาชิกใหม่เองได้โดยไม่ต้อง seed
รองรับ `DEMO_PASSWORD` เช่นเดียวกับ `ADMIN_PASSWORD` หากต้องการใช้ environment

## 5. รันเว็บไซต์

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

เปิด http://127.0.0.1:5000 ในเบราว์เซอร์ หยุดด้วย `Ctrl+C`
อีกวิธีคือ `.\.venv\Scripts\python.exe app.py` หลัง `init-db` แล้ว
ไม่เปิด debug อัตโนมัติ

เมื่อใช้ครั้งแรก ระบบสร้าง `instance/secret.key` แบบสุ่มและเก็บไว้สำหรับ session/CSRF
ห้ามส่งไฟล์นี้ให้ผู้อื่น สามารถกำหนด `SECRET_KEY` ผ่าน environment แทนได้
หากเปลี่ยน secret ผู้ใช้ที่ login อยู่จะต้อง login ใหม่
ข้อมูลอยู่ใน `instance/repair.sqlite3` และยังอยู่หลังปิดเซิร์ฟเวอร์
สำรองทั้งโฟลเดอร์ `instance` ขณะหยุดเซิร์ฟเวอร์ และเก็บไฟล์สำรองเป็นส่วนตัวเพราะมีข้อมูลติดต่อ

## 6. ทดลองใช้งานทั้งสองบทบาท

### ผู้ใช้

1. เปิดหน้าสมัครสมาชิก: ชื่อ–นามสกุล, username ภาษาอังกฤษ/ตัวเลข/`_.-` 3–40 ตัว, password 10–128 ตัว และยืนยัน
2. Login แล้วระบบพาไป **รายการแจ้งซ่อมของฉัน**
3. กด **แจ้งซ่อมใหม่** ใส่อุปกรณ์ `PC-101`, ห้อง `อาคาร 2 ห้อง 201`, อาการ `เปิดเครื่องแล้วหน้าจอไม่แสดงภาพ`, ข้อมูลติดต่อที่สมมติขึ้น
4. ส่งแบบฟอร์มแล้วเห็นสถานะ **รอรับเรื่อง** และประวัติสร้างรายการ
5. ออกจากระบบ หรือเปิดอีก browser/profile เพื่อทดสอบ admin พร้อมกัน

### ผู้ดูแล

1. Login ด้วย username และ password ที่ตั้งจาก `create-admin`
2. เห็นหน้า **ภาพรวมการแจ้งซ่อม** แสดงจำนวนทั้ง 4 สถานะ
3. เปิดรายการทั้งหมด ค้นหา `PC-101` หรือชื่อผู้แจ้ง/ห้อง/หมายเลข
4. เปิดรายละเอียด เลือก **กำลังดำเนินการ** และบันทึก `ตรวจสอบสายสัญญาณและทดสอบจอภาพ`
5. กดบันทึก แล้วเปลี่ยนเป็น **เสร็จสิ้น** พร้อมบันทึก `เปลี่ยนสาย HDMI และทดสอบใช้งานแล้ว`
6. สร้างอีกงานเพื่อทดลอง **ไม่สามารถซ่อมได้** พร้อมระบุเหตุผล เช่น `แผงวงจรเสียและไม่มีอะไหล่ทดแทน`
7. กลับไป login ฝั่ง User จะเห็นสถานะใหม่และประวัติทุกครั้งที่บันทึก

### ตรวจสิทธิ์และ validation ด้วยมือ

| การทดลอง | ผลที่ควรได้ |
| --- | --- |
| User A แจ้งซ่อม แล้ว User B เปิด `/repairs/หมายเลขของ A` | 404 ไม่แสดงข้อมูล |
| User เปิด `/admin` | 403 |
| ยังไม่ login เปิดรายการ | พาไป login |
| ส่งแบบฟอร์มไม่มี/ปลอม CSRF token | 400 |
| ส่งบันทึกว่างหรือสถานะนอก 4 ค่า | ไม่แก้ข้อมูลและแจ้งข้อผิดพลาด |
| สมัครชื่อซ้ำหรือรหัสผ่านสั้น | แจ้งข้อผิดพลาด |
| รายละเอียดมี HTML/script | แสดงเป็นข้อความ ไม่รัน script |
| Logout | ยกเลิก session; เปิดข้อมูลส่วนตัวต้อง login ใหม่ |

## 7. รันทดสอบอัตโนมัติ

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

มี 13 ชุดทดสอบ ครอบคลุมสมัครสมาชิก/hash/ชื่อซ้ำ, login/logout, การแยกข้อมูล User,
การกันสิทธิ์ admin, flow ครบ 4 สถานะและประวัติ, CSRF, validation/SQL query,
HTML escaping, CLI admin/seed, การเปิดหน้า/ไฟล์ CSS, transaction rollback และการตั้งค่าบน Vercel
ใช้ฐานข้อมูลแยกชั่วคราว ไม่แตะข้อมูลใช้งานจริง และเปิด CSRF ในการทดสอบด้วย

## 8. โครงสร้างและส่วนสำคัญ

```text
campus-repair/
├── app.py                 # Flask factory, routes, SQLite, permissions และ CLI
├── database.py            # เลือก SQLite / PostgreSQL และ adapter SQL ขนาดเล็ก
├── schema.sql             # ตาราง users, repairs, repair_history และ indexes
├── schema_postgres.sql    # ตารางชุดเดียวกันสำหรับ PostgreSQL
├── index.py               # Flask entrypoint สำหรับ Vercel
├── build.py               # เตรียมไฟล์ CSS ใน public/static สำหรับ Vercel CDN
├── setup_online.py        # สร้างตาราง/Admin ออนไลน์จากเครื่อง โดยซ่อน connection string
├── pyproject.toml         # Python 3.12, dependencies และ Vercel entrypoint
├── vercel.json            # Framework และ build command
├── DEPLOY_VERCEL_TH.md     # คู่มือ GitHub + Vercel + Neon
├── .github/workflows/     # ทดสอบสองฐานข้อมูลบน GitHub Actions
├── requirements.txt       # dependencies Python
├── README.md              # คู่มือนี้
├── REPORT_TH.md           # รายงานย่อและแนวทางนำเสนอ
├── TEST_RESULTS_TH.md     # ผลทดสอบในสภาพแวดล้อมที่สร้างโปรเจกต์
├── templates/             # หน้า HTML + Jinja และส่วนตารางที่ใช้ซ้ำ
├── static/
│   ├── style.css          # ดีไซน์ฟ้าขาวและ responsive
│   └── vendor/            # Bootstrap CSS และ MIT license
├── tests/test_app.py      # unittest + Flask test client
└── instance/              # สร้างขณะรัน: SQLite และ secret (ไม่รวมใน ZIP)
```

- `create_app()` ตั้งค่าแอปและ routes; Flask CLI เรียก factory นี้อัตโนมัติ
- `get_db()` เปิด connection ต่อ request, ใช้ `sqlite3.Row` อ่านชื่อคอลัมน์ และปิดเมื่อจบ request
- เมื่อมี `DATABASE_URL`, `database.py` ใช้ psycopg เชื่อม PostgreSQL และแปลง placeholders/เวลา/insert id
  เพื่อให้ routes เดิมเข้าใจง่าย; ตาราง PostgreSQL แยกไฟล์เพราะไวยากรณ์ต่างจาก SQLite
- บน Vercel ต้องตั้ง `DATABASE_URL` และ `SECRET_KEY`, เปิด secure cookies อัตโนมัติ และไม่เขียนไฟล์ instance
- `build.py` สร้าง `public/static` จาก static เดิม ทำให้ URL ของ CSS เหมือนกันทั้งสองโหมด
- `login_required` / `admin_required` ตรวจ session และบทบาทจากฐานข้อมูลที่ server
- `get_repair()` ตรวจเจ้าของรายการหรือ admin ก่อนส่งข้อมูล จึงแก้ URL เพื่อดูของผู้อื่นไม่ได้
- คำสั่ง SQL ใช้ placeholders `?` แยกข้อมูลออกจาก SQL ป้องกัน SQL injection
- `generate_password_hash()` / `check_password_hash()` เก็บและตรวจรหัสผ่านแบบ hash
- `CSRFProtect` ตรวจทุก POST รวม login/register/logout; Jinja ใส่ token ใน form
- `with db:` ทำให้ update สถานะและ history สำเร็จด้วยกัน หรือ rollback หากผิดพลาด
- Jinja autoescape แปลง HTML ที่ผู้ใช้พิมพ์เป็นข้อความ; ไม่ใช้ `|safe` กับข้อมูลผู้ใช้
- Session เป็น signed cookie: เก็บเฉพาะ user id, ไม่เก็บรหัสผ่าน; ตรวจ role ใหม่จาก DB ทุก request
- เก็บเวลาเป็นข้อความเขตไทย UTC+7 เพื่อให้นักศึกษาเข้าใจง่าย
- HTML validation ช่วย UX และตรวจซ้ำใน Python ไม่เชื่อข้อมูลจาก browser

## 9. แก้ปัญหาที่พบบ่อย

- `py` ไม่พบ: ติดตั้ง Python พร้อม PATH แล้วเปิด VS Code ใหม่ หรือใช้ `python` แทน `py`
- `No module named flask`: ติดตั้ง requirements ด้วย Python ตัวเดียวกับที่ใช้ run ตรวจ interpreter `.venv`
- `no such table: users`: รัน `init-db` จากโฟลเดอร์ที่มี `app.py`
- `Address already in use`: เปลี่ยน `--port 5001` แล้วเปิด URL พอร์ตนั้น
- แบบฟอร์มหมดอายุ: reload หน้าแล้วกรอกใหม่ อย่าใช้หลายหน้าที่เปิดก่อน logout/login
- หน้าตาไม่โหลด: ใช้ URL ผ่าน Flask server ไม่เปิด HTML ด้วยการดับเบิลคลิก

## 10. ขอบเขต

เหมาะกับการเรียนและการสาธิตในเครื่องเดียว ข้อมูลอยู่ใน SQLite ไม่รวมการยืมคืน ไฟล์แนบ อีเมล หรือการจ่ายเงิน
โหมด Vercel เก็บข้อมูลใน PostgreSQL ภายนอกและให้บริการผ่านระบบ WSGI ของ Vercel;
ไม่ใช้ Flask development server บนเว็บไซต์ออนไลน์
ก่อนนำไปใช้จริงหลายคนควรเพิ่ม rate limiting การ login, การดูแลสำรองข้อมูล, HTTPS และ production WSGI server
หากใช้ HTTPS ให้กำหนด `COOKIE_SECURE=1`; การรัน localhost ด้วย HTTP ใช้ค่าเริ่มต้นเพื่อ login ได้
อย่าใช้ Flask development server เปิดบริการสาธารณะ และอย่าแจกฐานข้อมูลที่มีข้อมูลติดต่อจริง
Bootstrap เป็นซอฟต์แวร์ MIT ดู `static/vendor/bootstrap-LICENSE.txt`
