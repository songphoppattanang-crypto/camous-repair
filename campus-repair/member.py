# ตรวจข้อมูลสมาชิก ใช้ร่วมกันทั้งสมัครสมาชิกและแก้ข้อมูลบัญชี
import re
TITLES = ('นาย', 'นาง', 'นางสาว', 'อื่น ๆ')
def profile_fields(form, student=True):
    data = {key: form.get(key, '').strip() for key in ('email','title','student_id','faculty','major')}
    data['email'] = data['email'].lower()
    if len(data['email']) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", data['email']):
        raise ValueError('กรุณากรอกอีเมลให้ถูกต้อง')
    if data['title'] not in TITLES:
        raise ValueError('กรุณาเลือกคำนำหน้า')
    if student and not re.fullmatch(r'[0-9]{8,15}(?:-[0-9]{1,2})?', data['student_id']):
        raise ValueError('กรุณากรอกรหัสนักศึกษาให้ถูกต้อง')
    if student and any(not 2 <= len(data[key]) <= 100 for key in ('faculty','major')):
        raise ValueError('กรุณากรอกคณะและสาขา 2–100 ตัวอักษร')
    if any(len(data[key]) > 100 for key in ('student_id','faculty','major')):
        raise ValueError('ข้อมูลยาวเกินกำหนด')
    return data
