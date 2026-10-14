# สร้างอีเมลในฐานข้อมูล แล้วส่งผ่าน SMTP โดยไม่เก็บรหัสลับในโค้ด
import os
import ssl
import smtplib
from email.message import EmailMessage
from flask import current_app
from member import profile_fields

def queue_repair_mail(db, repair_id, status_label, event):
    row = db.execute('SELECT r.equipment,r.room,p.email FROM repairs r LEFT JOIN user_profiles p ON p.user_id=r.user_id WHERE r.id=?', (repair_id,)).fetchone()
    recipients = set()
    if row['email']: recipients.add(row['email'])
    recipients.update(r['email'] for r in db.execute("SELECT p.email FROM users u JOIN user_profiles p ON p.user_id=u.id WHERE u.role='admin'").fetchall())
    recipients.update(x.strip().lower() for x in os.environ.get('ADMIN_NOTIFICATION_EMAILS','').split(',') if x.strip())
    site = os.environ.get('SITE_URL','https://camous-repair.vercel.app').rstrip('/')
    if not site.startswith('https://'): raise ValueError('SITE_URL ต้องเริ่มด้วย https://')
    subject = f'{event} #{repair_id:04d} — {status_label}'
    body = f'รายการ #{repair_id:04d}\nอุปกรณ์: {row["equipment"]}\nสถานที่: {row["room"]}\nสถานะ: {status_label}\n\nเข้าสู่ระบบเพื่อดูรายละเอียด: {site}/repairs/{repair_id}\n\nอีเมลแจ้งเตือนจากระบบแจ้งซ่อมอุปกรณ์ภายในสถานศึกษา'
    ids = []
    for address in sorted(recipients):
        # ตรวจที่อยู่อีเมลก่อนนำมาเป็นผู้รับ ป้องกันอักขระแทรก header
        try: profile_fields({'email':address,'title':'อื่น ๆ'},student=False)
        except ValueError: continue
        ids.append(db.execute('INSERT INTO email_outbox(recipient,subject,body) VALUES(?,?,?)',(address,subject,body)).lastrowid)
    return ids

def deliver_pending(db, ids=None):
    host = os.environ.get('SMTP_HOST')
    username = os.environ.get('SMTP_USERNAME')
    password = os.environ.get('SMTP_PASSWORD')
    if not all((host, username, password)): return False
    if ids is not None:
        if not ids: return True
        placeholders = ','.join('?' for _ in ids)
        rows = db.execute("SELECT * FROM email_outbox WHERE status='pending' AND id IN (" + placeholders + ") ORDER BY id", tuple(ids)).fetchall()
    else:
        rows = db.execute("SELECT * FROM email_outbox WHERE status='pending' ORDER BY id LIMIT 20").fetchall()
    all_sent = True
    for row in rows:
        if ids is not None and row['id'] not in ids: continue
        # จองงานก่อนส่ง ป้องกันคำขอพร้อมกันส่งอีเมลรายการเดียวซ้ำ
        cur = db.execute("UPDATE email_outbox SET status='sending',attempts=attempts+1 WHERE id=? AND status='pending'",(row['id'],))
        db.commit()
        if cur.rowcount != 1: continue
        try:
            port = int(os.environ.get('SMTP_PORT','587'))
            if port not in (465,587): raise ValueError('ใช้ SMTP แบบ TLS เท่านั้น')
            message = EmailMessage()
            message['From'] = username
            message['To'] = row['recipient']
            message['Subject'] = row['subject']
            message['Message-ID'] = f'<repair-notice-{row["id"]}@{username.split("@")[-1]}>'
            message.set_content(row['body'])
            transport = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
            with transport(host,port,timeout=8) as smtp:
                if port == 587:
                    smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
                smtp.login(username,password)
                smtp.send_message(message)
            db.execute("UPDATE email_outbox SET status='sent' WHERE id=?",(row['id'],));db.commit()
        except Exception as exc:
            db.execute("UPDATE email_outbox SET status='pending' WHERE id=?",(row['id'],));db.commit()
            current_app.logger.warning('Email delivery failed: %s',type(exc).__name__)
            all_sent = False
    if ids is None and db.execute("SELECT id FROM email_outbox WHERE status='pending' LIMIT 1").fetchone():
        return False
    return all_sent
