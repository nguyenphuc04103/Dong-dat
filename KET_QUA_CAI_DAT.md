# Cài đặt thực tế trên máy — 07/10/2026

- Đã sửa và chạy `cai_dat.bat` trong thư mục Downloads của người dùng, bằng Python 3.13.2 64-bit ở `C:\Python\Python313\python.exe`.
- Lỗi TLS ban đầu trỏ tới `certifi/cacert.pem` tại thư mục Python cũ. Bộ cài nay dùng CA bundle hợp lệ của pip trong `venv`; chỉ đặt biến môi trường cho phiên cài, giữ xác minh HTTPS. Không sửa PATH hay chứng chỉ toàn máy. Tham khảo [pip HTTPS certificates](https://pip.pypa.io/en/stable/topics/https-certificates/).
- Đã tải/cài đủ thư viện, kết thúc bằng `OK - cai dat xong`, exit code 0. Thư viện trong `venv`; cache tải trong `.pip-cache` của web.
- Đã import face_recognition, OpenCV, Flask, MySQL connector, Requests, Pillow; dlib/model thực tế tạo được mã hóa 128 chiều cho ảnh trong dataset. Đây là kiểm tra chạy được model, chưa đo độ chính xác với người/camera thật.
- Bộ v7 dùng `dlib-bin` để cung cấp module `dlib`, và cài face_recognition bằng `--no-deps`. Vì tên distribution khác, pip có thể cảnh báo thiếu metadata `dlib`; module thực tế đã được kiểm tra bằng tạo mã hóa khuôn mặt. Cảnh báo pkg_resources deprecated cũng chưa phải lỗi chạy; giữ setuptools dưới 81 như bộ cài.
- Sửa thêm khởi tạo camera từ IP đã cấu hình, để Python không phải chờ ESP8266 online mới khởi động tiến trình live.
- Đã khởi động web thật và nhận HTTP 200 cho dashboard, cấu hình IP, dữ liệu và danh sách ảnh. IP giữ ESP8266 `192.168.0.104`, ESP32-CAM `192.168.0.103`. Python relay live khởi động, trả đúng loại nội dung MJPEG; chưa nhận khung hình từ camera thật.
- Thời điểm kiểm tra: hai địa chỉ ESP không phản hồi; MySQL tại 127.0.0.1:3306 chưa nhận kết nối. Dashboard báo OFFLINE đúng trạng thái. Khi dùng, cần cấp nguồn/kết nối Wi-Fi cho mạch và bật MySQL. Chưa xác nhận ghi DB/ảnh từ mạch thật trong lần cài này.

Web đã được chạy nền tại http://127.0.0.1:5000. Đừng mở thêm một `chay.bat` khi web này còn chạy vì dùng chung cổng. Log nằm trong `web-stdout.log` và `web-stderr.log`; thông tin tiến trình chính nằm trong `web-run.pid.json`. Các file trước khi sửa được giữ bằng hậu tố `.bak`.

Cập nhật này bổ sung cho kết quả kiểm tra phần mềm trong `KIEM_THU.md`, thay cho giới hạn “chưa cài bộ AI trên máy” của lần kiểm tra trước. Phần MySQL/mạch thật vẫn cần kết nối hoạt động.
