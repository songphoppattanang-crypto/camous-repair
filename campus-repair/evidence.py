# ตรวจและย่อรูปหลักฐานก่อนเก็บ ไม่เก็บข้อมูลพิกัดจากภาพ
"""ตรวจภาพตามเนื้อไฟล์ และแปลงเป็น WebP โดยไม่เก็บ EXIF/พิกัด GPS."""
from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 10 * 1024 * 1024
MAX_STORED = 500 * 1024


# ตรวจไฟล์จริง ย่อภาพ และคืนภาพ WebP สำหรับเก็บในฐานข้อมูล
def prepare_photo(upload):
    if upload is None or not upload.filename:
        raise ValueError('กรุณาแนบภาพอุปกรณ์หรืออาการเสียอย่างน้อย 1 ภาพ')
    extension = Path(upload.filename).suffix.lower()
    formats = {'.jpg':'JPEG', '.jpeg':'JPEG', '.png':'PNG', '.webp':'WEBP'}
    if extension not in formats:
        raise ValueError('รองรับภาพ JPG, PNG และ WebP เท่านั้น')
    # อ่านเกินเพดานมา 1 ไบต์ เพื่อจับไฟล์ที่ใหญ่เกินกำหนด
    data = upload.stream.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('รูปภาพต้องมีขนาดไม่เกิน 10 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != formats[extension] or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('ชนิดภาพไม่ตรงกับนามสกุล หรือเป็นภาพเคลื่อนไหว')
                width, height = image.size
                if width * height > 24_000_000 or min(width, height) < 100:
                    raise ValueError('ภาพต้องมีด้านสั้นอย่างน้อย 100 พิกเซล และไม่เกิน 24 ล้านพิกเซล')
                # ตรวจว่าไฟล์ภาพอ่านได้จริงและไม่เสีย
                image.verify()
            with Image.open(BytesIO(data)) as image:
                clean = ImageOps.exif_transpose(image).convert('RGB')
                # ย่อภาพให้ด้านยาวไม่เกิน 1280 พิกเซล
                clean.thumbnail((1280,1280))
                output = BytesIO()
                # แปลงภาพเป็น WebP เพื่อลดพื้นที่จัดเก็บ
                clean.save(output,format='WEBP',quality=80,method=4)
                result = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError('ไม่สามารถอ่านภาพได้ กรุณาใช้ไฟล์ภาพที่สมบูรณ์') from None
    if len(result) > MAX_STORED:
        raise ValueError('ภาพมีรายละเอียดมากเกินไป กรุณาลดขนาดภาพแล้วลองใหม่')
    return result
