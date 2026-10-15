"""
TIEN TRINH CAMERA RIENG (chay song song voi app.py va ai_process.py)

Chi lam 3 viec, khong lam gi khac:
  1. Doc webcam / ESP32-CAM lien tuc.
  2. Phat video MJPEG tren CONG RIENG (mac dinh 5001): http://<ip>:5001/video_feed
     -> khong dung chung Flask, khong dung chung ket noi trinh duyet, khong dung chung GIL voi MySQL / luu anh.
  3. Moi AI_INTERVAL giay chuyen 1 khung hinh moi nhat sang tien trinh AI (neu AI dang ranh).

Nho vay, du AI nhan dien / chup anh / ghi MySQL nang the nao thi video van chay deu.
"""
import os
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import queue

if os.environ.get("CAM_BACKEND", "auto").lower() == "dshow":
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_MSMF", "0")   # priority 0 = TAT han MSMF, nen chi dat khi ep DSHOW
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")   # MSMF mo nhanh, khong treo luc khoi dong
import cv2  # noqa: E402

# Tu sua FPS (khoa phoi sang + dong/mo lai webcam) lam video DUNG 15-20 giay ngay luc co mat nguoi.
# Mac dinh TAT. Bat lai bang: set CAM_TU_SUA=1
TU_SUA = os.environ.get("CAM_TU_SUA", "0") == "1"
# Mo hop thoai cai dat driver webcam 1 lan khi khoi dong (de tat Auto Exposure / Low Light / Dynamic FPS).
# Bat bang: set CAM_SETTINGS=1
MO_HOP_THOAI_DRIVER = os.environ.get("CAM_SETTINGS", "0") == "1"

# Chon backend webcam: auto (mac dinh: thu MSMF roi DSHOW) | dshow | msmf.   Vi du: set CAM_BACKEND=dshow
# MSMF la duong ma app Camera cua Windows dung -> hay het tut FPS khi co mat nguoi.
CAM_BACKEND = os.environ.get("CAM_BACKEND", "auto").lower()

# Ghi log chan doan thoi gian (doc camera / ma hoa / gui AI). Tat bang: set CAM_DEBUG=0
DEBUG = os.environ.get("CAM_DEBUG", "1") == "1"

_cond = threading.Condition()
_latest = {"jpg": None, "id": 0}
_web_sent = {"n": 0}


def _log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)


# ----------------------------- MO CAMERA: THU CAC CHE DO VA DO FPS THAT -----------------------------
# Webcam Windows hay roi vao che do "FPS dong" (thieu sang / tu phoi sang lau -> tut con 1-3 fps) hoac che do
# khong hop voi driver. Nen khong doan: thu tung che do, DO FPS THAT, chon che do tot nhat.
def _cau_hinh():
    D, M = cv2.CAP_DSHOW, getattr(cv2, "CAP_MSMF", None)
    dshow = [
        {"ten": "DSHOW mac dinh", "backend": D, "fourcc": None, "size": None, "fps": None, "khoa": None, "tu_dong": True},
        {"ten": "DSHOW YUY2 640x480", "backend": D, "fourcc": "YUY2", "size": (640, 480), "fps": 30, "khoa": None, "tu_dong": True},
        {"ten": "DSHOW MJPG 640x480", "backend": D, "fourcc": "MJPG", "size": (640, 480), "fps": 30, "khoa": None, "tu_dong": True},
    ]
    msmf = []
    if M is not None:
        msmf = [
            {"ten": "MSMF mac dinh", "backend": M, "fourcc": None, "size": None, "fps": None, "khoa": None, "tu_dong": True},
            {"ten": "MSMF MJPG 640x480", "backend": M, "fourcc": "MJPG", "size": (640, 480), "fps": 30, "khoa": None, "tu_dong": True},
        ]
    if CAM_BACKEND == "msmf" and msmf:
        ds = msmf
    elif CAM_BACKEND == "dshow":
        ds = dshow
    else:
        ds = msmf + dshow                  # auto: thu MSMF truoc (khong bi tut 1 fps khi co mat nguoi), khong duoc moi thu DSHOW
    for e in (-5, -6):      # khoa phoi sang ngan: chi dung de thu bang cam_test.py hoac tu sua khi fps tut
        ds.append({"ten": f"DSHOW khoa phoi sang {e}", "backend": D, "fourcc": None, "size": (640, 480),
                   "fps": 30, "khoa": e, "tu_dong": False})
    return ds


def _khoa_phoi_sang(cap, e):
    """Tat tu dong phoi sang, dat thoi gian phoi sang = 2^e giay (e=-5 -> 1/32s -> du cho 30fps)."""
    a = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)     # DirectShow: 0.25 = thu cong, 0.75 = tu dong
    b = cap.set(cv2.CAP_PROP_EXPOSURE, e)
    return bool(a), bool(b)


def _tu_dong_phoi_sang(cap):
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)


def _dat(cap, ch):
    if ch["fourcc"]:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*ch["fourcc"]))
    if ch["size"]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, ch["size"][0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ch["size"][1])
    if ch["fps"]:
        cap.set(cv2.CAP_PROP_FPS, ch["fps"])
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if ch["khoa"] is not None:
        _khoa_phoi_sang(cap, ch["khoa"])


def do_fps(cap, toi_da=4.0):
    """Doc thu ~1.5 giay. Tra ve (fps that, do sang trung binh 0-255)."""
    moc, sang = [], 0.0
    t0 = time.monotonic()
    while True:
        ok, fr = cap.read()
        now = time.monotonic()
        if ok:
            moc.append(now)
            sang = float(fr[::16, ::16].mean())
        if now - t0 > toi_da:
            break
        if len(moc) >= 3 and now - moc[1] >= 1.2:
            break
    if len(moc) >= 3:
        return (len(moc) - 2) / max(1e-6, moc[-1] - moc[1]), sang      # bo khung dau (khoi dong)
    if len(moc) == 2:
        return 1.0 / max(1e-6, moc[1] - moc[0]), sang
    return 0.0, sang


def _mo_voi(source, ch):
    cap = cv2.VideoCapture(source, ch["backend"])
    if not cap.isOpened():
        cap.release()
        return None
    _dat(cap, ch)
    return cap


def mo_camera(source):
    """Tra ve (cap, ten_che_do, fps, do_sang) hoac None.
    source la URL (ESP32-CAM): ket noi truc tiep. source la so (webcam): thu tung che do, chon che do co FPS cao nhat."""
    if isinstance(source, str):
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,3000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000])
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                _log(f"[CAM] Da ket noi ESP32-CAM: {source}")
                return cap, "URL", 0.0, 0.0
        cap.release()
        return None

    tot = None                                            # (fps, ch, sang)
    for ch in _cau_hinh():
        if not ch["tu_dong"]:
            continue
        cap = _mo_voi(source, ch)
        if cap is None:
            _log(f"[CAM] '{ch['ten']}' khong mo duoc.")
            continue
        fps, sang = do_fps(cap)
        cap.release()                                     # tha thiet bi truoc khi thu che do tiep theo
        _log(f"[CAM] Thu '{ch['ten']}': {fps:.1f} fps, do sang {sang:.0f}/255")
        if tot is None or fps > tot[0]:
            tot = (fps, ch, sang)
        if fps >= 12:
            break                                         # du tot, khong can thu them (tiet kiem thoi gian khoi dong)
    if tot is not None and tot[0] > 0:
        fps, ch, sang = tot
        cap = _mo_voi(source, ch)
        if cap is not None:
            _log(f"[CAM] CHON '{ch['ten']}' ({fps:.1f} fps).")
            if MO_HOP_THOAI_DRIVER:
                _log("[CAM] Mo hop thoai driver: bo chon Auto o Exposure, tat Low Light / Dynamic Frame Rate, bam OK.")
                cap.set(cv2.CAP_PROP_SETTINGS, 1)
            return cap, ch["ten"], fps, sang
    for idx in (0, 1, 2):                                 # khong che do nao doc duoc: thu camera khac
        if idx == source:
            continue
        cap = cv2.VideoCapture(idx, cv2.CAP_MSMF if CAM_BACKEND == "msmf" else cv2.CAP_DSHOW)
        if cap.isOpened() and cap.read()[0]:
            _log(f"[CAM] Dung camera index {idx}")
            return cap, f"index {idx}", 0.0, 0.0
        cap.release()
    return None


def tu_sua_fps_thap(cap, fps_hien_tai):
    """FPS tut giua chung (vd: thieu sang -> webcam keo dai thoi gian phoi sang). Thu khoa phoi sang ngan,
    giu lai neu fps len cao ma hinh khong qua toi, khong thi tra ve tu dong. Tra ve True neu da cai thien."""
    for e in (-5, -6):
        ok_a, ok_b = _khoa_phoi_sang(cap, e)
        fps, sang = do_fps(cap)
        _log(f"[CAM] Thu khoa phoi sang {e}: {fps:.1f} fps, do sang {sang:.0f}/255 "
             f"(driver nhan lenh: tat-tu-dong={ok_a}, dat-phoi-sang={ok_b})")
        if fps >= max(15.0, 2 * fps_hien_tai) and sang >= 30:
            _log(f"[CAM] Da khoa phoi sang {e}: video len {fps:.1f} fps.")
            return True
    _tu_dong_phoi_sang(cap)
    _log("[CAM] Khong cai thien duoc bang phan mem. Hay TANG ANH SANG phong / tranh nguoc sang, "
         "tat hieu ung camera cua Windows, doi cong USB.")
    return False


def kiem_tra_tat_ca(source=0):
    """Dung cho cam_test.py: thu TAT CA che do (ke ca khoa phoi sang) va in bang ket qua."""
    kq = []
    for ch in _cau_hinh():
        cap = _mo_voi(source, ch)
        if cap is None:
            print(f"  {ch['ten']:<32} khong mo duoc", flush=True)
            continue
        fps, sang = do_fps(cap)
        cap.release()
        kq.append((ch["ten"], fps, sang))
        print(f"  {ch['ten']:<32} {fps:5.1f} fps   do sang {sang:5.1f}/255", flush=True)
    return kq


# ----------------------------- SERVER VIDEO RIENG -----------------------------
def _tao_handler(max_fps):
    min_dt = 1.0 / max_fps

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"      # khong keep-alive: moi luong video 1 ket noi rieng, dong la het
        timeout = 10                       # trinh duyet ngung doc > 10s thi bo ket noi, khong treo luong

        def log_message(self, *args):
            pass

        def _dau(self, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/video_feed":
                self._phat_video()
            elif path == "/snapshot.jpg":
                with _cond:
                    data = _latest["jpg"]
                if data is None:
                    self.send_error(503)
                    return
                self._dau("image/jpeg")
                self.wfile.write(data)
            else:
                self.send_error(404)

        def _phat_video(self):
            self._dau("multipart/x-mixed-replace; boundary=frame")
            last, t_gui = -1, 0.0
            try:
                while True:
                    with _cond:
                        _cond.wait_for(lambda: _latest["id"] != last, timeout=2.0)
                        data, cur = _latest["jpg"], _latest["id"]
                    if data is None or cur == last:
                        continue
                    last = cur
                    cho = min_dt - (time.monotonic() - t_gui)
                    if cho > 0:
                        time.sleep(cho)
                    t_gui = time.monotonic()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
                    self.wfile.flush()
                    _web_sent["n"] += 1
            except (OSError, socket.error):
                return                      # trinh duyet dong tab / tai lai trang: binh thuong

    return Handler


def _chay_server(port, max_fps):
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    try:
        srv = Server(("0.0.0.0", port), _tao_handler(max_fps))
    except OSError as e:
        _log(f"[CAM] KHONG mo duoc cong video {port}: {e}. Doi VIDEO_PORT trong app.py.")
        return
    _log(f"[CAM] Video LIVE tai http://127.0.0.1:{port}/video_feed")
    srv.serve_forever()


# ----------------------------- VONG LAP CHINH -----------------------------
def chay_camera(cfg, ai_in, quake_ev, ai_ready_ev, fps_arr, frame_ctr, ai_pause_ev):
    """cfg: nguon, port, quality, max_fps, ai_interval, ai_luon_bat.
    fps_arr: mp.Array('d', 4) = [fps doc, fps khung khac nhau, fps gui web, do sang].  frame_ctr: mp.Value dem khung."""
    threading.Thread(target=_chay_server, args=(cfg["port"], cfg["max_fps"]), daemon=True).start()

    cap = None
    loi = 0
    t_fps = t_ai = time.monotonic()
    n_doc = n_khac = 0
    web_truoc = 0
    sig_truoc = None
    sang = 0.0
    cham = 0                    # so cua so 2 giay lien tiep co fps thap
    lan_sua, t_sua = 0, -1e9
    enc = [cv2.IMWRITE_JPEG_QUALITY, cfg["quality"]]
    tg_doc = tg_doc_max = tg_enc = tg_put_max = 0.0     # chan doan: tong/max thoi gian moi buoc trong 1 cua so
    t_slow_log = 0.0

    while True:
        if cap is None or loi > 30:
            if cap is not None:
                cap.release()
                _log("[CAM] Mat khung hinh, dang mo lai camera...")
            kq = mo_camera(cfg["source"])
            loi = 0
            if kq is None:
                _log(f"[CAM] Khong mo duoc camera ({cfg['source']}). Thu lai sau 3 giay...")
                time.sleep(3)
                continue
            cap = kq[0]
            cham = 0
            t_fps = time.monotonic()                      # cua so FPS dau tien chi tinh tu luc camera san sang
            n_doc = n_khac = 0
            web_truoc = _web_sent["n"]
            tg_doc = tg_doc_max = tg_enc = tg_put_max = 0.0

        _t = time.perf_counter()
        ok, frame = cap.read()
        _d = time.perf_counter() - _t
        tg_doc += _d
        tg_doc_max = max(tg_doc_max, _d)
        if DEBUG and _d > 0.5 and time.monotonic() - t_slow_log > 1.0:
            t_slow_log = time.monotonic()
            _log(f"[CAM] cap.read() bi chan {_d * 1000:.0f} ms luc {datetime.now():%H:%M:%S}")
        if not ok:
            loi += 1
            time.sleep(0.05)
            continue
        loi = 0

        n_doc += 1
        sig = frame[::48, ::48].tobytes()
        if sig != sig_truoc:
            n_khac += 1
            sig_truoc = sig
        now = time.monotonic()
        if now - t_fps >= 2.0:
            dt = now - t_fps
            sang = float(frame[::16, ::16].mean())
            fps_arr[0], fps_arr[1] = round(n_doc / dt, 1), round(n_khac / dt, 1)
            fps_arr[2] = round((_web_sent["n"] - web_truoc) / dt, 1)
            fps_arr[3] = round(sang, 0)
            n_tb = max(1, n_doc)
            t_fps, n_doc, n_khac, web_truoc = now, 0, 0, _web_sent["n"]
            cham = cham + 1 if fps_arr[0] < 8 else 0
            if cham > 0 and (cham == 1 or cham % 10 == 0):
                _log(f"[CAM] CANH BAO webcam cham: doc {fps_arr[0]} fps, khung khac nhau {fps_arr[1]} fps, "
                     f"gui web {fps_arr[2]} fps, do sang {sang:.0f}/255 | "
                     f"read TB {tg_doc / n_tb * 1000:.0f} ms (max {tg_doc_max * 1000:.0f}), "
                     f"encode TB {tg_enc / n_tb * 1000:.0f} ms, put-AI max {tg_put_max * 1000:.0f} ms")
            tg_doc = tg_doc_max = tg_enc = tg_put_max = 0.0
            # fps tut keo dai >= 6 giay: tu thu sua (toi da 3 lan, cach nhau >= 60 giay)
            if (TU_SUA and cham >= 3 and lan_sua < 3 and now - t_sua > 60 and not isinstance(cfg["source"], str)):
                lan_sua += 1
                t_sua = now
                if not tu_sua_fps_thap(cap, fps_arr[0]):
                    _log("[CAM] Dong va mo lai thiet bi webcam de dat lai trang thai driver...")
                    cap.release()
                    cap = None
                cham = 0
                t_fps, n_doc, n_khac, web_truoc = time.monotonic(), 0, 0, _web_sent["n"]
                continue

        _t = time.perf_counter()
        ok, buf = cv2.imencode(".jpg", frame, enc)
        tg_enc += time.perf_counter() - _t
        if ok:
            with _cond:
                _latest["jpg"] = buf.tobytes()
                _latest["id"] += 1
                _cond.notify_all()
            frame_ctr.value = _latest["id"]

        # chuyen khung cho AI (khong cho, khong xep hang: AI ban thi bo qua)
        if now - t_ai >= cfg["ai_interval"] and ai_ready_ev.is_set() and not ai_pause_ev.is_set() \
                and (cfg["ai_luon_bat"] or quake_ev.is_set()):
            t_ai = now
            _t = time.perf_counter()
            try:
                ai_in.put_nowait((frame, datetime.now()))
            except queue.Full:
                pass
            tg_put_max = max(tg_put_max, time.perf_counter() - _t)
