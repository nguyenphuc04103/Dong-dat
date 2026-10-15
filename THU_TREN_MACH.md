# Thử từng chức năng trên thiết bị

Các bước có tác động cửa/còi thật. Quan sát mạch/số trên web. Không cần tháo linh kiện hay đổi dây đang chạy.

1. **Kết nối:** bật hai mạch, chạy Python, cấu hình IP. Số rung phải theo MPU. Nếu OFFLINE, mở `http://IP-ESP8266/api` và `http://IP-ESP32/api` trên laptop để phân biệt sai IP với lỗi Python.
2. **Live:** hình phải từ ESP32, không phải webcam laptop. Mở `http://IP-ESP32:81/stream` nếu Python chưa có hình. Live dùng được khi chưa báo động.
3. **Mức nhẹ:** 1–dưới 2 g đủ mẫu: LCD/web mức nhẹ, ba tiếng ngắn; giữ cảnh báo để nghe lặp 10 giây. Cửa/camera không tự kích hoạt. Dưới 1 g thì mức nhẹ dừng.
4. **Báo động:** TEST thử chuỗi tác động trước, sau đó rung MPU đạt 2 g đủ mẫu để kiểm tra cảm biến. Cửa mở/còi; camera chụp và ảnh đầu hiện sau thời gian tải/cập nhật.
5. **Chu kỳ:** giữ báo động 65–75 giây. Bộ đếm tăng/có ảnh theo dõi mới được lưu. Nút chụp thủ công không chứng minh chu kỳ tự động.
6. **Thủ công:** CHỤP ẢNH NGAY có ảnh mới, không reset lịch tự động.
7. **Tắt còi:** tiếng dừng, cửa/camera vẫn giữ báo động. Đóng cửa phải bị từ chối.
8. **RESET:** tắt còi/đóng cửa, camera ngừng tăng ảnh tự động sau khi nhận reset; live/ảnh đã lưu còn.
9. **Lưu trữ:** restart Python còn ảnh. Reboot camera mất ảnh RAM nhưng không mất ảnh đã tải xuống laptop.
10. **Mạng:** mất kết nối phải OFFLINE, không tự SAFE/reset. Khôi phục cập nhật lại. Không kỳ vọng tải bù đủ mọi ảnh cũ khi laptop offline nhiều phút.
11. **AI:** thử dataset/ánh sáng/góc nhìn thật. Tạm dừng AI vẫn live. Nhận diện mặt chưa xác nhận thoát nhà; hướng ra/vào cần bổ sung.

Khi lỗi, lưu `/api/iot/status` và Serial mạch liên quan. Không gửi mật khẩu Wi-Fi hay ảnh cá nhân không cần thiết.
