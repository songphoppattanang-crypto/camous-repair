// รับภาพต้นฉบับไม่เกิน 10 MB และย่อในเครื่องก่อนส่งฟอร์ม
(() => {
  const input = document.getElementById('photo');
  if (!input) return;
  const form = input.form;
  const feedback = document.getElementById('photo-feedback');
  const button = form.querySelector('button[type="submit"], button:not([type])');
  const maxSize = 10 * 1024 * 1024;
  let busy = false;
  let ready = false;
  input.addEventListener('change', () => {
    ready = false;
    input.setCustomValidity('');
    feedback.textContent = '';
    if (input.files[0] && input.files[0].size > maxSize) {
      input.setCustomValidity('รูปภาพต้องมีขนาดไม่เกิน 10 MB');
      input.reportValidity();
    }
  });
  // อ่านเป็น data URL ซึ่งนโยบายความปลอดภัยของเว็บอนุญาต
  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('อ่านไฟล์ไม่ได้ กรุณาเลือกภาพใหม่'));
      reader.onload = () => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('อ่านภาพไม่ได้ กรุณาเลือก JPG, PNG หรือ WebP ที่สมบูรณ์'));
        image.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }
  form.addEventListener('submit', async (event) => {
    if (ready) return;
    event.preventDefault();
    if (busy) return;
    const file = input.files[0];
    if (!file || !form.reportValidity()) return;
    if (file.size > maxSize) { feedback.textContent = 'รูปภาพต้องมีขนาดไม่เกิน 10 MB'; return; }
    if (!/\.(jpe?g|png|webp)$/i.test(file.name)) { feedback.textContent = 'รองรับ JPG, PNG และ WebP เท่านั้น'; return; }
    busy = true;
    button.disabled = true;
    input.disabled = true;
    feedback.textContent = 'กำลังเตรียมรูปภาพ กรุณารอสักครู่…';
    try {
      const image = await loadImage(file);
      if (Math.min(image.naturalWidth, image.naturalHeight) < 100 || image.naturalWidth * image.naturalHeight > 24000000) {
        throw new Error('ภาพต้องมีด้านสั้นอย่างน้อย 100 พิกเซล และไม่เกิน 24 ล้านพิกเซล');
      }
      // ย่อด้านยาวเหลือ 1280 พิกเซล และแปลงเป็น JPEG ก่อนส่ง
      const scale = Math.min(1, 1280 / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(image.naturalWidth * scale);
      canvas.height = Math.round(image.naturalHeight * scale);
      const context = canvas.getContext('2d');
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
      if (!blob || blob.size > 3 * 1024 * 1024) throw new Error('ลดขนาดภาพไม่สำเร็จ กรุณาเลือกภาพใหม่');
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], 'repair-photo.jpg', { type: 'image/jpeg' }));
      input.files = transfer.files;
      input.disabled = false;
      button.disabled = false;
      ready = true;
      feedback.textContent = 'เตรียมภาพแล้ว กำลังส่งรายการ…';
      form.requestSubmit(button);
    } catch (error) {
      feedback.textContent = error.message || 'เตรียมภาพไม่สำเร็จ กรุณาลองอีกครั้ง';
    } finally {
      busy = false;
      input.disabled = false;
      button.disabled = false;
    }
  });
})();
