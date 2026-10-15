# Trạng thái kết nối trên dashboard

Web Python mở trên cổng 5000 dù camera hoặc MySQL không hoạt động. Camera live dùng cổng 5001. Dashboard có mục riêng cho Web, Camera, CSDL và AI; camera chưa nhận khung hình không được báo LIVE.

- Camera không kết nối: dashboard hiển thị thông báo ngay trong vùng live. Vẫn xem được giao diện, hồ sơ và ảnh đã lưu nếu dịch vụ tương ứng hoạt động. Camera tiếp tục thử kết nối trong nền; cùng một lỗi không in lặp mỗi 3 giây.
- CSDL không kết nối: dashboard báo lỗi MySQL. Lỗi 1932 được phân biệt với MySQL chưa bật: đó là lỗi đọc bảng của engine, không phải thiếu driver hay Python. Phần hiển thị này không xóa/tạo lại bảng lỗi hoặc phục hồi dữ liệu.
- Khi sửa IP camera bằng nút KẾT NỐI, luồng live đổi sang IP mới ngay cả lúc ESP8266 đang offline. Cần nhập IP thực tế của ESP32-CAM và đảm bảo laptop truy cập được mạng của mạch.
- Kiểm tra/khởi tạo CSDL chạy trong nền; dashboard không phải chờ MySQL hoặc xử lý ảnh chân dung trước khi mở.

Kiểm thử: 8 kiểm thử trạng thái/dịch vụ, 16 kiểm thử hồi quy API, 25 kiểm tra JavaScript và kiểm thử Chrome với lỗi MySQL 1932 thật, camera offline, màn hình điện thoại. Preview thử trên cổng 19050, không bật cổng web thật 5000 hay camera relay 5001. Không gửi lệnh mở cửa/còi/reset tới mạch và không xóa CSDL.
