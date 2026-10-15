# DuAn_IoT_AI v7 — tích hợp hai ESP

Sửa từ ZIP v7 của nhóm, giữ Python AI và dataset. Thay rung giả bằng dữ liệu ESP8266, thay webcam bằng live ESP32-CAM, sửa đường dẫn điều khiển và thêm lưu ảnh camera xuống máy chạy web.

**Giữ ESP32-CAM đang chạy được. Chỉ nạp ESP8266_CanhBaoNhe để có cảnh báo nhẹ và lệnh TẮT CÒI riêng.**

## Cách kết nối

```text
MPU/LCD/còi/cửa ← ESP8266
                    │ UDP báo động/reset qua Wi-Fi
                    ↓
                ESP32-CAM
                    │ HTTP ảnh + MJPEG live
                    ↓
ESP8266 /api → Python trên laptop → web nhóm + AI + ảnh trên ổ đĩa
```

Hai mạch và laptop cần ở cùng LAN, được phép trao đổi với nhau. Wi-Fi khách có chế độ cô lập thiết bị có thể ngăn kết nối. Không nối thêm dây tín hiệu giữa hai mạch.

ESP32 đang có `/api`, `/capture`, `/alarm.jpg`, `/latest.jpg`, `/manual.jpg`, live cổng 81. Python dùng các API này; không cần viết/nạp firmware ESP32 mới. ESP8266 tự phát hiện rung/tác động cửa/còi, độc lập với web và AI.

## Chạy

1. Giải nén đầy đủ ra thư mục cố định. Nạp gói ESP8266 theo hướng dẫn trong đó; ESP32 giữ nguyên.
2. Nếu chưa cài web nhóm: dùng Python 3.10/3.11 theo bộ v7, chạy `cai_dat.bat`. Bộ cài AI gốc được giữ; khả năng cài dlib trên máy bạn chưa được kiểm thử lại lần này.
3. Bật **MySQL trong XAMPP**, chạy `chay.bat`. Mặc định root không mật khẩu như v7; nếu khác, chỉnh `DB_USER` / `DB_PASSWORD` trong môi trường hoặc BAT.
4. Mở **http://127.0.0.1:5000** trên laptop. Gói cập nhật ngày 07/10/2026 đã điền ESP8266 `192.168.0.104` và ESP32-CAM `192.168.0.103` theo IP bạn cung cấp. Python tự dùng cấu hình này khi chạy; không cần nhập lại nếu địa chỉ vẫn đúng.
5. Nếu IP thay đổi, sửa hai ô rồi bấm **KẾT NỐI**. Chỉ nhập IP, không nhập URL/cổng. Có thể để IP ESP32 trống để tự nhận qua ESP8266. Cấu hình lưu trong `iot_config.json`; lấy IP ESP8266 bằng Serial Monitor 115200, gửi `ip`.

Điền IP trong web không làm địa chỉ của mạch thành cố định. Firmware hiện để router cấp IP qua DHCP; đổi từ `.102` sang `.104` chưa chứng minh `.102` đang bị thiết bị khác dùng. Muốn giữ hai địa chỉ lâu dài, đặt DHCP/Address Reservation trên router, gắn MAC mỗi mạch với IP tương ứng. Xem [hướng dẫn TP-Link](https://www.tp-link.com/us/support/faq/182/); vị trí menu tùy model router.

Nếu đã cài v7 ở thư mục khác: sao lưu thư mục đó, chép `app.py`, `camera_process.py`, `esp_bridge.py`, `iot_config.json`, `templates/index.html`, `static/vendor/bootstrap.min.css` và hướng dẫn mới vào đúng vị trí của thư mục đang dùng. Giữ `venv`, dataset và ảnh đã có; không cần di chuyển `venv`. Không yêu cầu framework AI mới.

Dashboard dùng **5000**, Python relay live dùng **5001**. Điện thoại cùng LAN mở `http://IP-laptop:5000`; Windows Firewall cần cho Python nhận kết nối nội bộ tới hai cổng. Trang riêng hai ESP vẫn dùng được.

`cam_test.py` / `chay_driver.bat` là công cụ webcam cũ được giữ lại; không phải bước cần chạy để xem ESP32.

## Hành vi/nút

- **1 ≤ rung < 2 g đủ mẫu:** cảnh báo nhẹ, ba tiếng ngắn mỗi 10 giây; LCD hiện độ rung và câu yêu cầu. Không tự mở cửa/chụp ảnh.
- **Từ 2 g đủ mẫu:** mở cửa/còi, gửi báo động camera. Camera chụp ngay khi nhận lệnh, rồi mỗi **60 giây** đến RESET. Python tải ảnh; web cập nhật trạng thái khoảng mỗi giây, danh sách ảnh mỗi 5 giây nên ảnh có thể hiện muộn hơn lúc chụp.
- **Bật báo động thử:** gửi TEST tới mạch thật, mở cửa/bật còi/chụp ảnh. Bấm tắt hoặc RESET kết thúc báo động thật.
- **TẮT CÒI:** chỉ tắt tiếng; giữ báo động/cửa/camera. ESP8266 cũ chưa có `mute` sẽ báo lệnh không hợp lệ: dùng bản cảnh báo nhẹ đi kèm.
- **RESET:** kết thúc báo động, đóng cửa, yêu cầu camera dừng chụp tự động. Live/ảnh đã lưu còn giữ.
- **CHỤP ẢNH NGAY:** chụp thủ công và lưu về laptop, không thay lịch tự động.
- Đóng cửa trong báo động bị mạch từ chối; web hiển thị phản hồi thật.
- Mất kết nối báo OFFLINE, không tự reset hay báo SAFE. ESP8266 tiếp tục theo trạng thái của mạch.

## Lưu ảnh

- Camera lưu ảnh đầu, ảnh theo dõi mới nhất, ảnh thủ công mới nhất trong **RAM/PSRAM**, mất khi reboot/tắt nguồn.
- Python tải JPEG kèm JSON vào **`static/captures/earthquake/`**. Restart web/reset không xóa ảnh đã tải. Không cần SD cho cách này, nhưng laptop/web phải chạy và kết nối được camera.
- MySQL **`camera_photos`** lưu đường dẫn/metadata; JPEG nằm trên ổ đĩa. MySQL lỗi vẫn lưu file; lỗi metadata báo log, chưa có hàng đợi tự ghi bù.
- Web liệt kê 100 ảnh gần nhất; file cũ vẫn tồn tại, chưa tự dọn theo dung lượng. Thời gian trên ảnh là thời gian máy Python lưu, không phải thời gian camera đã đồng bộ.
- Web/mạng ngừng nhiều phút: camera chỉ giữ ảnh đầu và mới nhất, không thể khôi phục mọi ảnh mỗi phút đã bị ghi đè. Muốn lịch sử đầy đủ khi mất mạng cần SD hoặc bộ lưu cục bộ ở bước sau.

## AI

Giữ `ai_process.py`, cách đọc dataset của nhóm. Khung hình thật ESP32 qua tiến trình camera riêng tới Python AI; không tạo model mới.

Các danh sách “đã thoát” / “còn kẹt lại” vẫn dùng quy tắc cũ: thấy khuôn mặt trong báo động thì chuyển danh sách. Điều này chỉ xác nhận người xuất hiện trong vùng camera, chưa xác minh hướng đi/đã thoát khỏi tòa nhà. Giao diện có ghi chú; độ chính xác nhận diện chưa được đo lần này.

## API Python

| Method | Đường dẫn | Mục đích |
|---|---|---|
| GET | `/api/get_data` | Dashboard IoT/AI |
| GET | `/api/iot/status` | Kết nối/dữ liệu hai mạch/lỗi ảnh |
| GET / POST | `/api/iot/config` | IP: `controller_ip`, `camera_ip` |
| POST | `/api/control/mo_cua` | ESP8266 `open` |
| POST | `/api/control/dong_cua` | `close`, giữ phản hồi từ chối khi báo động |
| POST | `/api/control/tat_coi` | `mute` |
| POST | `/api/control/reset` | `reset` |
| POST | `/api/control/test` | `test`, tác động thật |
| GET | `/api/camera/photos` | Ảnh trên laptop |
| POST | `/api/camera/capture` | Chụp/lưu thủ công |

Bản này chạy **nội bộ**, chưa host Internet hay thêm đăng nhập/phân quyền. Server ngoài Internet không tự truy cập IP LAN của ESP: cần gateway gửi dữ liệu/ảnh ra ngoài, tài khoản/quyền xem camera và cơ chế live. Chỉ thêm API không giải quyết kết nối này.

Xem `KIEM_THU.md` và `THU_TREN_MACH.md`. Tham khảo: [Flask testing](https://flask.palletsprojects.com/en/stable/testing/), [Requests timeouts](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts), [ESP32 camera](https://github.com/espressif/esp32-camera).
