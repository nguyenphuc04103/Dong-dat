"""Validate one portrait in a separate process, keeping Flask/video responsive."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import io, json, sys
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

def encode_portrait(raw):
    Image.MAX_IMAGE_PIXELS = 16000000
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG'):
                raise ValueError('Chỉ nhận ảnh JPG hoặc PNG.')
            if image.width * image.height > 16000000:
                raise ValueError('Ảnh quá lớn; tối đa 16 triệu điểm ảnh.')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1200,1200))
            import numpy as np
            import face_recognition
            array = np.asarray(image)
            locations = face_recognition.face_locations(array)
            if len(locations) != 1:
                raise ValueError('Ảnh phải có đúng một khuôn mặt rõ nét; hiện tìm thấy %d.' % len(locations))
            encodings = face_recognition.face_encodings(array, locations)
            if len(encodings) != 1:
                raise ValueError('Không trích xuất được khuôn mặt; hãy chọn ảnh rõ hơn.')
            buffer = io.BytesIO()
            # Keep DB packets below XAMPP's common 1 MB packet limit.
            for quality in (90,80,70,60):
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=quality, optimize=True)
                if buffer.tell() <= 512000:
                    break
            if buffer.tell() > 512000:
                image.thumbnail((800,800))
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=75, optimize=True)
            return buffer.getvalue(), encodings[0].tolist()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('File không phải ảnh hợp lệ hoặc kích thước quá lớn.')

if __name__ == '__main__':
    try:
        image, encoding = encode_portrait(Path(sys.argv[1]).read_bytes())
        Path(sys.argv[2]).write_bytes(image)
        Path(sys.argv[3]).write_text(json.dumps({'encoding':encoding}), encoding='utf8')
    except Exception as error:
        Path(sys.argv[3]).write_text(json.dumps({'error':str(error)}, ensure_ascii=False), encoding='utf8')
        sys.exit(1)
