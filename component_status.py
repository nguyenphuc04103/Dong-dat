"""Non-blocking dashboard health; database checks run in a background worker."""
import threading
import time
import mysql.connector


def database_error(error, table=None):
    code = getattr(error, 'errno', None)
    if table is None:
        detail = str(error)
        table = next((name for name in ('members', 'lich_su_thoat_hiem', 'camera_photos') if name in detail), None)
    if code == 1932:
        return {'state': 'error', 'connected': True, 'error_code': code,
                'message': 'MySQL đã kết nối nhưng bảng ' + (table or 'trong iot_dongdat') +
                ' bị lỗi engine 1932. Chưa đọc/ghi được bảng; cần kiểm tra và phục hồi CSDL.'}
    if code == 1146:
        return {'state': 'error', 'connected': True, 'error_code': code,
                'message': 'CSDL thiếu bảng ' + (table or 'của dự án') + '. Chưa đọc/ghi được dữ liệu.'}
    if code == 1045:
        message = 'MySQL từ chối đăng nhập. Kiểm tra tài khoản CSDL của web.'
    elif code == 1049:
        message = 'Chưa tìm thấy CSDL iot_dongdat. Kiểm tra bước khởi tạo CSDL.'
    else:
        message = 'Không kết nối/đọc được MySQL. Kiểm tra MySQL trong XAMPP.'
    return {'state': 'error', 'connected': False, 'error_code': code, 'message': message}


class DatabaseHealth:
    def __init__(self, connect):
        self.connect = connect
        self.lock = threading.Lock()
        self.value = {'state': 'checking', 'connected': False, 'error_code': None,
                      'message': 'Đang kiểm tra MySQL và các bảng CSDL.', 'checked_at': None}

    def check(self):
        conn = cursor = None
        table = None
        try:
            conn = self.connect()
            cursor = conn.cursor()
            for table in ('lich_su_thoat_hiem', 'camera_photos', 'members'):
                cursor.execute('SELECT id FROM ' + table + ' LIMIT 0')
                cursor.fetchall()
            value = {'state': 'online', 'connected': True, 'error_code': None,
                     'message': 'MySQL đã kết nối; các bảng dự án đọc được.'}
        except mysql.connector.Error as error:
            value = database_error(error, table)
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except mysql.connector.Error:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except mysql.connector.Error:
                    pass
        value['checked_at'] = time.time()
        with self.lock:
            self.value = value
        return value

    def snapshot(self):
        with self.lock:
            return dict(self.value)


def camera_health(source, running, last_frame, frame_count, started_at, api_online=False, now=None):
    now = time.monotonic() if now is None else now
    if not source:
        state, message = 'unconfigured', 'Chưa có IP camera. Nhập IP ESP32-CAM ở phần cấu hình.'
    elif not running:
        state, message = 'offline', 'Tiến trình camera chưa chạy hoặc đã dừng.'
    elif last_frame and frame_count > 0 and now - last_frame <= 5:
        state, message = 'online', 'Đang nhận hình trực tiếp từ camera.'
    elif started_at and now - started_at < 10 and not last_frame:
        state, message = 'connecting', 'Đang kết nối luồng hình của ESP32-CAM.'
    elif api_online:
        state, message = 'offline', 'ESP32-CAM trả lời API nhưng chưa nhận được luồng live. Kiểm tra cổng 81 và /stream.'
    else:
        state, message = 'offline', 'Chưa nhận được hình camera. Kiểm tra nguồn, IP và Wi-Fi của ESP32-CAM.'
    return {'state': state, 'online': state == 'online', 'message': message,
            'last_frame_age': round(max(0, now-last_frame), 1) if last_frame else None}
