# สร้างอีเมลในฐานข้อมูล แล้วส่งผ่าน SMTP โดยไม่เก็บรหัสลับในโค้ด
import os
import re
import ssl
import smtplib
from email.message import EmailMessage
from flask import current_app
from member import profile_fields

def queue_repair_mail(db, repair_id, status_label, event):
    row = db.execute('SELECT r.*,u.name AS account_name,p.email,p.title,p.faculty,p.major,e.reporter_name,e.student_id,a.assignee FROM repairs r JOIN users u ON u.id=r.user_id LEFT JOIN user_profiles p ON p.user_id=r.user_id LEFT JOIN repair_evidence e ON e.repair_id=r.id LEFT JOIN repair_assignments a ON a.repair_id=r.id WHERE r.id=?', (repair_id,)).fetchone()
    recipients = set()
    if row['email']: recipients.add(row['email'])
    recipients.update(r['email'] for r in db.execute("SELECT p.email FROM users u JOIN user_profiles p ON p.user_id=u.id WHERE u.role='admin'").fetchall())
    recipients.update(x.strip().lower() for x in os.environ.get('ADMIN_NOTIFICATION_EMAILS','').split(',') if x.strip())
    site = os.environ.get('SITE_URL','https://camous-repair.vercel.app').rstrip('/')
    if not site.startswith('https://'): raise ValueError('SITE_URL ต้องเริ่มด้วย https://')
    subject = f'{event} #{repair_id:04d} — {status_label}'
    # เก็บรายละเอียดและประวัติ ณ เวลาที่แจ้ง เพื่อให้การส่งซ้ำได้ข้อความเดิม
    history = db.execute('SELECT h.*,u.name AS actor FROM repair_history h JOIN users u ON u.id=h.actor_id WHERE h.repair_id=? ORDER BY h.id', (repair_id,)).fetchall()
    cancellation = db.execute('SELECT c.*,u.name AS actor FROM repair_cancellations c JOIN users u ON u.id=c.actor_id WHERE repair_id=?',(repair_id,)).fetchone()
    if cancellation:
        history.append({'status':'cancelled','created_at':cancellation['created_at'],'actor':cancellation['actor'],'note':cancellation['reason']})
    labels = {'pending':'รอรับเรื่อง','working':'กำลังดำเนินการ','done':'เสร็จสิ้น','unrepairable':'ไม่สามารถซ่อมได้','cancelled':'ยกเลิกแล้ว'}
    lines = [
        f'รายการ #{repair_id:04d}', event,
        f'สถานะล่าสุด: {status_label}',
        f'แจ้งเมื่อ: {row["created_at"]} (เวลาไทย)',
        f'อัปเดตเมื่อ: {row["updated_at"]} (เวลาไทย)',
        '', 'ข้อมูลผู้แจ้ง',
        f'ชื่อ–นามสกุล: {row["reporter_name"] or row["account_name"]}',
        f'คำนำหน้า: {row["title"] or "ไม่ได้ระบุ"}',
        f'รหัสนักศึกษา: {row["student_id"] or "ไม่ได้ระบุ"}',
        f'คณะ: {row["faculty"] or "ไม่ได้ระบุ"}',
        f'สาขา: {row["major"] or "ไม่ได้ระบุ"}',
        f'อีเมล: {row["email"] or "ไม่ได้ระบุ"}',
        f'ข้อมูลติดต่อ: {row["contact"]}',
        '', 'รายละเอียดการแจ้งซ่อม',
        f'อุปกรณ์: {row["equipment"]}',
        f'สถานที่: {row["room"]}',
        f'ผู้รับผิดชอบ: {row["assignee"] or "ยังไม่ได้มอบหมาย"}',
        'อาการที่พบ:', row['description'],
        '', 'ประวัติการดำเนินการ',
    ]
    for item in history:
        lines.extend([f'{item["created_at"]} | {labels.get(item["status"], item["status"])}',
                      f'ผู้ดำเนินการ: {item["actor"]}', f'บันทึก: {item["note"]}', ''])
    if not history: lines.append('ยังไม่มีประวัติ')
    has_photo = db.execute('SELECT id FROM repair_evidence WHERE repair_id=?',(repair_id,)).fetchone()
    lines.extend(['ภาพอุปกรณ์: ดูไฟล์รูปที่แนบมากับอีเมล' if has_photo else 'ภาพอุปกรณ์: ไม่มีภาพแนบ',
                  '', f'หากต้องการดำเนินการบนเว็บ: {site}/repairs/{repair_id}',
                  'อีเมลแจ้งเตือนจากระบบแจ้งซ่อมอุปกรณ์ภายในสถานศึกษา'])
    body = '\n'.join(lines)
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
            # แนบรูปของรายการนี้เท่านั้น ผู้รับแต่ละคนได้รับอีเมลแยกกัน
            match = re.search(r'^รายการ #(\d+)', row['body'], re.MULTILINE)
            if match:
                repair_id = int(match.group(1))
                evidence = db.execute('SELECT photo FROM repair_evidence WHERE repair_id=?',(repair_id,)).fetchone()
                if evidence:
                    message.add_attachment(bytes(evidence['photo']),maintype='image',subtype='webp',
                                           filename=f'repair-{repair_id:04d}.webp')
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
