# Tải ảnh và hồ sơ thành viên

1. Bật MySQL trong XAMPP; chạy web bằng chay.bat.
2. Trong dashboard chọn **Quản lý thành viên**, hoặc mở http://127.0.0.1:5000/members.
3. Nhập họ tên, ngày sinh, điện thoại và căn hộ/phòng. Chọn một ảnh JPG/PNG có đúng một khuôn mặt rõ; tối đa 6 MB. Bấm **Lưu hồ sơ**.
4. AI nạp lại danh sách trong nền; không cần tắt live hay khởi động lại web. Có thể mất vài giây nếu AI đang xử lý khung hình.
5. Bấm **Sửa** để chỉnh thông tin/đổi ảnh. Bỏ dấu chọn dùng trong AI để ngừng dùng một hồ sơ; ảnh và hồ sơ vẫn được giữ trong CSDL.

## Dữ liệu lưu ở đâu?

- MySQL/MariaDB: CSDL iot_dongdat, bảng members lưu tên, ngày sinh, điện thoại, phòng, ảnh chân dung JPEG và dữ liệu khuôn mặt. Mã hồ sơ được giữ ổn định khi sửa tên. Họ tên có thể trùng; mỗi hồ sơ có mã riêng.
- lich_su_thoat_hiem lưu nhận diện trong lúc cảnh báo. Cột member_id liên kết hồ sơ; dòng lịch sử cũ giữ nguyên và có thể chưa có mã.
- camera_photos lưu thông tin ảnh camera. Các JPEG camera đã tải về vẫn nằm trong static/captures; không chuyển vào bảng members.
- data/face_registry.json là bản lưu tạm cho AI đọc nhanh, tạo lại từ MySQL. Không sửa tay. Hồ sơ và ảnh không mất khi tắt web/máy.
- Ảnh trong dataset cũ được nhập vào members ở lần chạy đầu kết nối MySQL, không xóa hoặc sửa ảnh gốc. File không có đúng một mặt không được nhập.

## Xem CSDL

Trang Quản lý thành viên cho xem hồ sơ và trạng thái/số dòng các bảng. Để duyệt bảng đầy đủ: trong XAMPP bật Apache và MySQL, vào http://localhost/phpmyadmin/, chọn iot_dongdat rồi chọn bảng và Browse/Duyệt. Web Python chạy cổng 5000 không cần Apache.

## Khi có lỗi

- Trang báo MySQL chưa kết nối: bật MySQL trong XAMPP rồi tải lại trang. Nếu CSDL chưa từng được tạo, khởi động lại web sau khi bật MySQL.
- Không nhận ảnh: dùng ảnh đúng một người, mặt rõ và đủ sáng. File JPG/PNG được kiểm tra từ nội dung ảnh, không chỉ phần mở rộng.
- Hai ảnh quá giống nhau của cùng một người nên nằm trong cùng một hồ sơ: nhận diện bằng một ảnh vẫn có thể sai, nhất là khi thiếu sáng, che mặt hoặc góc nhìn khác. Đây là hỗ trợ quan sát vùng camera, không xác nhận tất cả người trong nhà đã thoát.
- Ảnh hồ sơ bị trùng hoàn toàn sẽ bị từ chối, tránh gán cùng ảnh cho hai hồ sơ.

## Kiểm thử bản bổ sung

Đã dùng MySQL/MariaDB 10.4 thật trên cổng riêng 19306 trong workspace, không sửa CSDL XAMPP thật: 14 kiểm thử hồ sơ (tạo/sửa, ảnh, nhập dữ liệu cũ, trùng ảnh/tên, ngừng dùng/kích hoạt lại, lỗi CSDL, giới hạn ảnh và dữ liệu, ngăn request khác nguồn); 1 kiểm thử tiến trình AI thật nhận diện và nạp lại khi không có khung hình; 3 kiểm thử liên kết hồ sơ/lịch sử/danh sách, 16 kiểm thử hồi quy web, 19 kiểm tra JavaScript; thử Chrome tải ảnh, lưu/sửa hồ sơ và màn hình điện thoại. File cập nhật cũng đã thử sao lưu, thay file và khởi động lại trên web riêng. Chưa kiểm thử camera/mạch thật đang offline.
