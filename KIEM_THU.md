# Kiểm tra tích hợp — 06/10/2026

| Nhóm | Đã đạt |
|---|---|
| Flask/HTTP thật với hai ESP mô phỏng | **16 bài**: rung thật theo API, IP camera, mức nhẹ, giữ/reset báo động, đợt mới sau reset bị bỏ lỡ, từ chối đóng cửa, tắt còi, OFFLINE không xóa báo động, MPU lỗi/lấy nền, lưu IP, ảnh đầu/ảnh phút/thủ công, không trùng ảnh khi reset/restart, JPEG lỗi, đổi metadata lúc tải, HTTP methods, API cũ và camera lỗi |
| JavaScript web | **19 kiểm tra**: trạng thái/mức rung, lệnh, IP, offline/lỗi, ảnh và phản hồi |
| JavaScript ESP8266 | **7 kiểm tra** cho mức nhẹ/LCD/còi/reset |
| Chrome thật | Trang/CSS nội bộ, TEST/ảnh đầu, đóng cửa bị từ chối, mute, chụp thủ công, RESET/giữ ảnh, lỗi IP, không lỗi JS; màn 390 px không tràn ngang |
| OpenCV thật | Giải mã HTTP MJPEG mô phỏng thành NumPy frame; tiến trình Python relay JPEG live; frame tới hàng đợi AI; pause AI không dừng live, resume nhận frame mới |
| ESP8266 | Biên dịch/liên kết cả bản kiểm tra logic và production, core 3.1.2; chi tiết trong gói firmware |

Browser dùng ảnh giả để tránh đợi luồng vô hạn; OpenCV kiểm tra riêng với HTTP MJPEG thật, ảnh mô phỏng. Không dùng ảnh riêng của thành viên để đánh giá AI.

Chưa nạp/gửi lệnh tác động tới mạch thật; API ESP8266 tại IP cấu hình chưa truy cập được từ môi trường thử. Chưa xác minh OV3660 thật chạy đồng thời, thời gian chụp, chữ LCD, nhịp còi, nguồn điện. Chưa chạy nhận diện face_recognition với dataset thật/đo độ chính xác; thử đường vào AI kết thúc ở hàng đợi khung hình.

Chưa kết nối MySQL/XAMPP thật hay chạy lại bộ cài dlib. Đã kiểm tra lưu/tải lại JPEG+JSON và cấu trúc lệnh DB; cần thử MySQL trên máy nhóm. Không đổi firmware ESP32; API lấy từ chính source đang chạy người dùng gửi.

Script thử/ảnh giao diện nằm trong workspace, không đóng kèm thư viện thử nghiệm trong ZIP. ZIP chỉ có source web, dataset gốc, CSS nội bộ và hướng dẫn.
