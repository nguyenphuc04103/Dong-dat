"""
Dashboard Nha Thong Minh: Bao Dong Dong Dat & Diem Danh AI
Backend: Flask + OpenCV + face_recognition + MySQL (XAMPP)

KIEN TRUC (3 TIEN TRINH de tach viec doc camera va AI):
  TIEN TRINH CAMERA (camera_process.py)  doc ESP32-CAM + phat video LIVE tren cong rieng (5001) + chuyen khung cho AI
  TIEN TRINH AI     (ai_process.py)      tim mat + nhan dien (dlib, nang), muc uu tien thap nhat
  TIEN TRINH CHINH  (app.py)             Flask dashboard (5000), MySQL, luu anh, cam bien rung, danh sach thoat hiem
Tach tien trinh giup AI / MySQL khong chan truc tiep luong doc video.

Cai dat: chay cai_dat.bat   |   Chay: chay.bat -> http://127.0.0.1:5000
"""
import os
if os.environ.get("CAM_BACKEND", "auto").lower() == "dshow":
    os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"  # chi tat MSMF khi ep dung DirectShow (priority 0 = TAT han backend)
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"          # an canh bao rac

import atexit
import multiprocessing as mp
import queue
import threading
import time
import zlib
from datetime import datetime

import mysql.connector
import requests
from flask import Flask, jsonify, redirect, render_template, request

import ai_process
import camera_process
from esp_bridge import EspBridge
from members import MemberStore, install_members

# ----------------------------- CAU HINH -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
CAPTURE_DIR = os.path.join(BASE_DIR, "static", "captures")   # noi luu anh chup
CAPTURE_REL = "static/captures"                              # duong dan tuong doi luu vao DB

# Device IPs are edited on the dashboard and saved in iot_config.json.
# Python reads the existing MCU APIs; no fake sensor and no extra ESP32 upload.

DB_CONFIG = {"host": "localhost", "user": os.environ.get("DB_USER", "root"),
             "password": os.environ.get("DB_PASSWORD", ""),
             "database": "iot_dongdat", "charset": "utf8mb4", "connection_timeout": 2}

# Nguon camera duoc tao tu IP ESP32-CAM da cau hinh / tu nhan.
CAMERA_SOURCE = None  # wait for the ESP32 IP advertised by ESP8266

TOLERANCE = 0.5              # do chat nhan dien (nho hon = chat hon)
NGUOI_LA = "Người lạ"        # nhan ghi vao DB khi khong khop ai

# --- AI chay ngam khi co bao dong dong dat ---
AI_INTERVAL = 2.0            # giay giua 2 lan lay mau (1-2 giay)
AI_SCALE = 0.5               # thu nho anh khi nhan dien (0.5 = 320x240 voi anh 640x480)
QUEUE_MAX = 2                # toi da so frame cho tien trinh AI (day thi bo frame moi, khong don)

# --- Chong spam: cung 1 nguoi chi luu anh/ghi DB/chen len web moi X giay ---
COOLDOWN_NGUOI_QUEN = 10.0   # giay
COOLDOWN_NGUOI_LA = 5.0      # giay (khong phan biet duoc tung nguoi la nen dung chung 1 moc)
# Moi nguoi trong dataset co 1 O RIENG duoi video. Anh chup luon GHI DE len 1 file duy nhat cua nguoi do
# (static/captures/face_xxxx.jpg). Nguoi la: khong luu anh.
# Anh da luu duoc giu lai khi khoi dong web; moi nguoi van ghi de anh khuon mat moi nhat.

# --- Che do chay AI ---
#   True : AI luon quet khi co nguoi vao khung hinh -> catalog duoi video luon cap nhat (dung de demo/test).
#          Chi khi co bao dong dong dat moi tinh "da thoat hiem" va ghi MySQL.
#   False: AI chi chay khi co bao dong dong dat (nhu thiet ke ban dau).
AI_LUON_BAT = True

# --- Video LIVE (tien trinh camera rieng) ---
VIDEO_PORT = 5001            # cong phat video; dashboard tu dong nap video tu cong nay
VIDEO_MAX_FPS = 25           # gioi han toc do day video len web
VIDEO_QUALITY = 75           # chat luong JPEG cua video (thap hon = nhe hon)

app = Flask(__name__)


def log(msg):
    """In log, khong bao gio nem loi ma hoa tren console Windows."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)


# ----------------------------- TRANG THAI CHIA SE -----------------------------
state_lock = threading.Lock()          # bao ve cac danh sach + cam bien + thong ke
danh_sach_tong = []
danh_sach_ket_lai = []
danh_sach_da_thoat = []
thong_ke = {"nguoi_la": 0}
thanh_vien = {}            # o cua tung nguoi trong dataset: ten -> {anh, thoi_gian, ngay, lan, v}
thong_tin_thoat = {}     # ten -> {"image_path": ..., "thoi_gian": datetime} (anh chup luc thoat)
sensor = {"rung": None, "last_shake": 0.0, "manual": False}
last_alarm_identity = None
camera_lifecycle_lock = threading.RLock()
event_transition_lock = threading.Lock()

# Cac co dung chung giua cac TIEN TRINH phai la multiprocessing (spawn), khong phai threading
_ctx = mp.get_context("spawn")
earthquake_event = _ctx.Event()        # is_earthquake: set() = True
ai_san_sang = _ctx.Event()             # set khi tien trinh AI da load xong dataset
ai_reload_ev = _ctx.Event()
ai_dung_ev = _ctx.Event()              # set = TAM DUNG AI (camera ngung gui khung) - de kiem tra video co do vi AI khong

# Tien trinh camera: ket qua chan doan chia se qua bo nho chung
cam_proc = None
fps_arr = None                         # [fps doc, fps khung khac nhau, fps gui web, do sang]
frame_ctr = None                       # so khung da phat (Dashboard dung de bao LIVE)

threads = {}

# Tien trinh AI rieng + 2 hang doi (frame di sang AI, ket qua tro ve)
ai_proc = None
ai_in = None
ai_out = None
ai_tat = threading.Event()             # set khi chuong trinh dang thoat: khong gui frame, khong bat lai AI


# ----------------------------- MYSQL -----------------------------
def ket_noi_mysql(with_db=True):
    cfg = dict(DB_CONFIG)
    if not with_db:
        cfg.pop("database")
    return mysql.connector.connect(**cfg)


def _text(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def khoi_tao_db():
    """Tao DB + bang. Tu dong nang cap bang cu: doi ten_nguoi -> ho_ten, them cot image_path."""
    try:
        conn = ket_noi_mysql(with_db=False)
        cur = conn.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS iot_dongdat CHARACTER SET utf8mb4")
        cur.execute("USE iot_dongdat")
        cur.execute(
            """CREATE TABLE IF NOT EXISTS lich_su_thoat_hiem (
                   id INT AUTO_INCREMENT PRIMARY KEY,
                   ho_ten VARCHAR(255),
                   thoi_gian DATETIME,
                   image_path VARCHAR(255) NULL
               ) DEFAULT CHARSET=utf8mb4"""
        )
        cur.execute("SHOW COLUMNS FROM lich_su_thoat_hiem")
        cot = {_text(r[0]) for r in cur.fetchall()}
        if "ten_nguoi" in cot and "ho_ten" not in cot:
            cur.execute("ALTER TABLE lich_su_thoat_hiem CHANGE ten_nguoi ho_ten VARCHAR(255)")
            log("[DB] Da doi cot ten_nguoi -> ho_ten")
        if "image_path" not in cot:
            cur.execute(
                "ALTER TABLE lich_su_thoat_hiem ADD COLUMN image_path VARCHAR(255) NULL AFTER thoi_gian"
            )
            log("[DB] Da them cot image_path")
        cur.execute("""CREATE TABLE IF NOT EXISTS camera_photos (
            id CHAR(64) PRIMARY KEY, image_path VARCHAR(255), kind VARCHAR(16),
            event_boot BIGINT UNSIGNED NULL, event_revision BIGINT UNSIGNED NULL,
            capture_number BIGINT UNSIGNED NULL, saved_at VARCHAR(40)
        ) DEFAULT CHARSET=utf8mb4""")
        cur.execute("SHOW COLUMNS FROM lich_su_thoat_hiem")
        if "member_id" not in {_text(r[0]) for r in cur.fetchall()}:
            cur.execute("ALTER TABLE lich_su_thoat_hiem ADD COLUMN member_id CHAR(32) NULL")
        conn.commit()
        cur.close()
        conn.close()
        log("[DB] San sang.")
    except mysql.connector.Error as e:
        log(f"[DB] Khong ket noi duoc MySQL (kiem tra XAMPP): {e}")


def ghi_log_thoat_hiem(ho_ten, thoi_gian, image_path, member_id=None):
    """INSERT 1 dong log: ten (hoac 'Nguoi la'), thoi gian chup, duong dan anh."""
    conn = None
    try:
        conn = ket_noi_mysql()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO lich_su_thoat_hiem (ho_ten, thoi_gian, image_path, member_id) VALUES (%s, %s, %s, %s)",
            (ho_ten, thoi_gian.strftime("%Y-%m-%d %H:%M:%S"), image_path, member_id),
        )
        conn.commit()
        cur.close()
        log(f"[DB] Da ghi log: {ho_ten} | {image_path}")
        return True
    except mysql.connector.Error as e:
        log(f"[DB] Loi ghi log '{ho_ten}': {e}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# MySQL owns profiles; AI reads an atomic cache without querying DB for every frame.
member_store = MemberStore(ket_noi_mysql, BASE_DIR, khoi_tao_db)

def member_name(key):
    profile = member_store.profiles.get(key, {})
    return profile.get("full_name", key) + (" · " + profile["apartment"] if profile.get("apartment") else "")

def members_changed():
    ai_reload_ev.set()

install_members(app, member_store, members_changed)
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024

@app.errorhandler(413)
def upload_too_large(error):
    return jsonify(ok=False, message="Ảnh quá lớn; tối đa 6 MB."), 413

# ----------------------------- DANH SACH THOAT HIEM -----------------------------
def cap_nhat_danh_sach_thoat(ten, image_path=None, ts=None):
    """Chuyen nguoi tu 'ket lai' sang 'da thoat' (chi lan dau) va nho anh chup luc thoat."""
    with state_lock:
        if ten in danh_sach_ket_lai:
            danh_sach_ket_lai.remove(ten)
            danh_sach_da_thoat.append(ten)
            thong_tin_thoat[ten] = {"image_path": image_path, "thoi_gian": ts or datetime.now()}


def bat_dau_dot_bao_dong():
    """Moi dot bao dong moi: tat ca nguoi trong dataset tro lai 'CON KET LAI', danh sach 'DA THOAT' xoa sach.
    (Neu khong, sau lan thoat dau tien 2 danh sach se dung yen mai mai.)"""
    with state_lock:
        danh_sach_ket_lai[:] = list(danh_sach_tong)
        danh_sach_da_thoat.clear()
        thong_tin_thoat.clear()
        thong_ke["nguoi_la"] = 0
    log("[ALERT] Dat lai danh sach: tat ca nguoi nha -> CON KET LAI")


# ----------------------------- CAM BIEN RUNG + BAO DONG -----------------------------
def nhan_trang_thai_esp(data, camera_ip):
    """The hardware owns alarm/reset. Connectivity loss must never clear an alarm."""
    global last_alarm_identity, CAMERA_SOURCE
    identity=(data.get("boot"),data.get("revision"))
    with event_transition_lock:
        with state_lock:
            sensor["rung"]=data.get("vibration")
        if data["alarm"]:
            if not earthquake_event.is_set() or (identity!=(None,None) and identity!=last_alarm_identity):
                bat_dau_dot_bao_dong()
            earthquake_event.set()
            last_alarm_identity=identity
        else:
            earthquake_event.clear()
    if camera_ip:
        source=f"http://{camera_ip}:81/stream"
        with camera_lifecycle_lock:
            if CAMERA_SOURCE!=source:
                CAMERA_SOURCE=source
                if cam_proc is not None and cam_proc.is_alive():
                    cam_proc.terminate();cam_proc.join(timeout=2)
                khoi_dong_camera()


def ghi_log_anh_camera(record):
    conn=None
    try:
        conn=ket_noi_mysql();cur=conn.cursor()
        cur.execute("""INSERT IGNORE INTO camera_photos
            (id,image_path,kind,event_boot,event_revision,capture_number,saved_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (record["id"],record["url"].lstrip("/"),record["kind"],record["event_boot"],
             record["event_revision"],record["capture_number"],record["saved_at"]))
        conn.commit();cur.close()
    except mysql.connector.Error as error:
        log(f"[DB] Anh da luu tren laptop; MySQL chua ghi duoc metadata: {error}")
    finally:
        if conn is not None:conn.close()


bridge=EspBridge(os.path.join(BASE_DIR,"iot_config.json"),
                 os.path.join(CAPTURE_DIR,"earthquake"),nhan_trang_thai_esp,ghi_log_anh_camera)
configured_camera_ip=bridge.get_config()["camera_ip"]
if configured_camera_ip:
    CAMERA_SOURCE=f"http://{configured_camera_ip}:81/stream"


def sensor_worker():
    bridge.controller_worker(ai_tat)


def photo_worker():
    bridge.photo_worker(ai_tat)


# ----------------------------- KHOI DONG CAC TIEN TRINH -----------------------------
def khoi_dong_ai():
    """Bat (hoac bat lai) tien trinh AI. Hang doi duoc tao 1 lan va giu nguyen khi AI khoi dong lai
    (tien trinh camera dang giu hang doi nay)."""
    global ai_proc, ai_in, ai_out
    if ai_in is None:
        ai_in = _ctx.Queue(maxsize=QUEUE_MAX)
        ai_in.cancel_join_thread()
        ai_out = _ctx.Queue()
    ai_san_sang.clear()
    cfg = {
        "dataset_dir": DATASET_DIR, "tolerance": TOLERANCE, "scale": AI_SCALE, "nguoi_la": NGUOI_LA,
        "cooldown_quen": COOLDOWN_NGUOI_QUEN, "cooldown_la": COOLDOWN_NGUOI_LA,
        "registry_path": str(member_store.cache), "reload_event": ai_reload_ev,
    }
    ai_proc = _ctx.Process(target=ai_process.chay_ai, args=(ai_in, ai_out, cfg), name="ai_process", daemon=True)
    ai_proc.start()
    log("[AI] Da khoi dong tien trinh AI rieng.")


def khoi_dong_camera():
    """Bat tien trinh camera: doc ESP32-CAM, phat LIVE va chuyen khung sang AI."""
    global cam_proc, fps_arr, frame_ctr
    if CAMERA_SOURCE is None or ai_tat.is_set():
        return
    if fps_arr is None:
        fps_arr = _ctx.Array("d", [0.0, 0.0, 0.0, 0.0])
        frame_ctr = _ctx.Value("l", 0)
    cfg = {
        "source": CAMERA_SOURCE, "port": VIDEO_PORT, "quality": VIDEO_QUALITY, "max_fps": VIDEO_MAX_FPS,
        "ai_interval": AI_INTERVAL, "ai_luon_bat": AI_LUON_BAT,
    }
    cam_proc = _ctx.Process(target=camera_process.chay_camera,
                            args=(cfg, ai_in, earthquake_event, ai_san_sang, fps_arr, frame_ctr, ai_dung_ev),
                            name="camera_process", daemon=True)
    cam_proc.start()
    log(f"[CAM] Da khoi dong tien trinh camera rieng. Video LIVE: http://127.0.0.1:{VIDEO_PORT}/video_feed")


def camera_watchdog_worker():
    """Tien trinh camera chet bat ngo thi bat lai (dashboard van chay)."""
    while True:
        time.sleep(3)
        with camera_lifecycle_lock:
            if cam_proc is not None and not cam_proc.is_alive() and not ai_tat.is_set():
                log("[CAM] Tien trinh camera da dung bat ngo, dang khoi dong lai...")
                khoi_dong_camera()


def dung_tien_trinh():
    ai_tat.set()
    ai_san_sang.clear()
    for pr in (cam_proc, ai_proc):
        try:
            if pr is not None and pr.is_alive():
                pr.terminate()           # khong giu du lieu quan trong, dung ngay cho nhanh
                pr.join(timeout=2)
        except Exception:
            pass


# ----------------------------- NHAN KET QUA TU AI: LUU ANH + CAP NHAT + GHI DB -----------------------------
def don_thu_muc_anh():
    """Tao thu muc neu thieu; giu anh camera va anh khuon mat da luu."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    # Preserve all downloaded camera photos and face images across web restarts.
    # No blanket deletion of captures: MySQL/history may reference those files.
    return


def luu_anh(jpeg_bytes, ten):
    """Ghi anh cua nguoi 'ten' vao 1 file CO DINH (ghi de anh cu). Tra ve duong dan tuong doi hoac None."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ten_file = f"face_{zlib.crc32(ten.encode('utf-8')):08x}.jpg"
    dich = os.path.join(CAPTURE_DIR, ten_file)
    tam = dich + ".tmp"
    try:
        with open(tam, "wb") as f:
            f.write(jpeg_bytes)
        os.replace(tam, dich)           # thay the nguyen khoi, trinh duyet khong bao gio doc phai file do dang
    except OSError as e:
        log(f"[IMG] Khong ghi duoc anh {ten_file}: {e}")
        return None
    return f"{CAPTURE_REL}/{ten_file}"


def xu_ly_ket_qua(msg):
    ts = msg["ts"]
    quake = earthquake_event.is_set()
    for f in msg["khuon"]:
        ten, quen = f["ten"], f["quen"]
        if quen and ten in member_store.profiles and not member_store.profiles[ten].get("active",True):
            continue
        if not f.get("moi"):
            # Dang trong cooldown (khong chup anh / ghi DB lai) nhung VAN phai cap nhat danh sach thoat hiem
            if quake and quen:
                with state_lock:
                    anh_cu = (thanh_vien.get(ten, {}).get("anh") or "").lstrip("/") or None
                cap_nhat_danh_sach_thoat(ten, anh_cu, ts)
            continue

        image_path = None
        if quen and f["anh"]:                   # CHI nguoi trong dataset moi duoc luu anh
            image_path = luu_anh(f["anh"], ten)
            with state_lock:                    # dien anh vao O cua dung nguoi do
                o = thanh_vien.setdefault(ten, {"anh": None, "thoi_gian": "", "ngay": "", "lan": 0, "v": 0})
                if image_path:
                    o["anh"] = "/" + image_path
                o["thoi_gian"] = ts.strftime("%H:%M:%S")
                o["ngay"] = ts.strftime("%d/%m/%Y %H:%M:%S")
                o["lan"] += 1
                o["v"] += 1                     # doi ?v= de trinh duyet nap lai dung anh moi

        if quake:                               # chi khi co bao dong moi tinh thoat hiem + ghi MySQL
            if quen:
                cap_nhat_danh_sach_thoat(ten, image_path, ts)
            else:
                with state_lock:
                    thong_ke["nguoi_la"] += 1
            ghi_log_thoat_hiem(member_name(ten), ts, image_path, member_store.profiles.get(ten,{}).get("id"))   # nguoi la: image_path = None (khong luu anh)


def update_member_roster(names):
    with state_lock:
        active = list(dict.fromkeys(names))
        danh_sach_tong[:] = active
        danh_sach_da_thoat[:] = [t for t in danh_sach_da_thoat if t in active]
        danh_sach_ket_lai[:] = [t for t in active if t not in danh_sach_da_thoat]
        for removed in list(thanh_vien):
            if removed not in active:
                del thanh_vien[removed]
        for ten in active:
            thanh_vien.setdefault(ten, {"anh": None, "thoi_gian": "", "ngay": "", "lan": 0, "v": 0})


def ai_result_worker():
    """Nhan thong diep tu tien trinh AI. Neu tien trinh AI chet thi tu bat lai (video van live)."""
    while True:
        try:
            msg = ai_out.get(timeout=2)
        except queue.Empty:
            if ai_proc is not None and not ai_proc.is_alive() and not ai_tat.is_set():
                log("[AI] Tien trinh AI da dung bat ngo, dang khoi dong lai...")
                time.sleep(2)
                khoi_dong_ai()
            continue
        except Exception as e:
            log(f"[AI] Loi doc ket qua: {e}")
            time.sleep(1)
            continue

        try:
            loai = msg.get("loai")
            if loai == "san_sang":
                update_member_roster(msg["ten"])
                ai_san_sang.set()
                log(f"[AI] San sang. Nguoi nha: {msg['ten']}")
            elif loai == "ket_qua":
                xu_ly_ket_qua(msg)
            elif loai == "loi":
                log(f"[AI] Loi xu ly frame: {msg['noi_dung']}")
        except Exception as e:
            log(f"[AI] Loi xu ly ket qua: {e}")


# ----------------------------- ROUTES -----------------------------
@app.route("/")
def index():
    return render_template("index.html", video_port=VIDEO_PORT)


@app.route("/video_feed")
def video_feed():
    """Duong dan cu: chuyen sang cong video rieng cua tien trinh camera."""
    host = request.host.split(":")[0]
    return redirect(f"http://{host}:{VIDEO_PORT}/video_feed")


@app.route("/api/get_data")
def api_get_data():
    quake = earthquake_event.is_set()
    iot=bridge.snapshot()
    controller=iot["controller"] or {}
    with state_lock:
        chi_tiet = []
        for ten in danh_sach_da_thoat:
            tt = thong_tin_thoat.get(ten, {})
            ip = tt.get("image_path")
            tg = tt.get("thoi_gian")
            chi_tiet.append({
                "ten": member_name(ten),
                "member_id": member_store.profiles.get(ten, {}).get("id"),
                "thoi_gian": tg.strftime("%H:%M:%S") if tg else "",
                "anh": ("/" + ip) if ip else None,      # vd: /static/captures/cap_....jpg
            })
        o_nguoi = []
        for ten in list(danh_sach_tong) + [t for t in thanh_vien if t not in danh_sach_tong]:
            o = thanh_vien.get(ten, {})
            anh = o.get("anh")
            o_nguoi.append({
                "ten": member_name(ten),
                "member_id": member_store.profiles.get(ten, {}).get("id"),
                "anh": f"{anh}?v={o['v']}" if anh else None,
                "thoi_gian": o.get("thoi_gian", ""),
                "ngay": o.get("ngay", ""),
                "lan": o.get("lan", 0),
            })
        return jsonify(
            {
                "rung_chan": sensor["rung"],
                "video_id": frame_ctr.value if frame_ctr is not None else 0,         # tang moi khi co khung hinh moi (Dashboard dung de bao LIVE)
                "trang_thai": ("OFFLINE" if not iot["online"] else "CANH BAO" if quake else
                               "ERROR" if controller.get("level")=="error" else "CALIBRATING" if controller.get("level")=="calibrating" else
                               "WARNING" if controller.get("warning") else "SAFE"),
                "iot": iot,
                "warning": controller.get("warning",False),
                "is_earthquake": quake,
                "thanh_vien": o_nguoi,         # moi nguoi trong dataset 1 o: anh moi nhat + gio
                "ai_dung": ai_dung_ev.is_set(),
                "fps": ({"cam": fps_arr[0], "khac": fps_arr[1], "web": fps_arr[2], "sang": fps_arr[3]} if fps_arr is not None else {}),        # chan doan toc do video
                "da_thoat": [member_name(t) for t in danh_sach_da_thoat],
                "da_thoat_chi_tiet": chi_tiet,
                "ket_lai": [member_name(t) for t in danh_sach_ket_lai],
                "tong": len(danh_sach_tong),
                "so_nguoi_la": thong_ke["nguoi_la"],
            }
        )


@app.route("/api/ai/<action>",methods=["POST"])
def api_ai(action):
    """Tam dung / chay lai AI ngay khi dang chay (de kiem tra: AI tat ma video van 1 fps -> loi o webcam)."""
    if action == "dung":
        ai_dung_ev.set()
    elif action == "chay":
        ai_dung_ev.clear()
    else:
        return jsonify({"ok": False, "message": "Dung /api/ai/dung hoac /api/ai/chay"}), 400
    return jsonify({"ok": True, "ai_dung": ai_dung_ev.is_set()})


def gui_lenh_mach(action):
    try:
        status,message=bridge.command(action)
        return jsonify({"ok":200<=status<300,"message":message}),status
    except ValueError as error:
        return jsonify({"ok":False,"message":str(error)}),400
    except requests.RequestException:
        return jsonify({"ok":False,"message":"Không kết nối được ESP8266. Kiểm tra IP và Wi-Fi."}),504


@app.route("/api/earthquake/<action>",methods=["POST"])
def api_earthquake(action):
    if action not in ("bat","tat"):
        return jsonify({"ok":False,"message":"Lệnh không hợp lệ"}),400
    return gui_lenh_mach("test" if action=="bat" else "reset")


@app.route("/api/control/<action>",methods=["POST"])
def api_control(action):
    return gui_lenh_mach(action)


@app.route("/api/iot/config",methods=["GET","POST"])
def api_iot_config():
    if request.method=="GET":
        return jsonify(bridge.get_config())
    try:
        data=request.get_json(silent=True)
        if not isinstance(data,dict):raise ValueError("Cần gửi cấu hình JSON.")
        return jsonify({"ok":True,"config":bridge.configure(data)})
    except (ValueError,KeyError) as error:
        return jsonify({"ok":False,"message":str(error)}),400
    except OSError:
        return jsonify({"ok":False,"message":"Không lưu được file cấu hình trên máy chủ."}),500


@app.route("/api/iot/status")
def api_iot_status():
    return jsonify(bridge.snapshot())


@app.route("/api/camera/photos")
def api_camera_photos():
    return jsonify({"photos":bridge.store.list()})


@app.route("/api/camera/capture",methods=["POST"])
def api_camera_capture():
    try:
        return jsonify({"ok":True,"photo":bridge.manual_capture()})
    except (requests.RequestException,ValueError,OSError) as error:
        return jsonify({"ok":False,"message":str(error)}),503


# ----------------------------- MAIN -----------------------------
def khoi_dong_luong():
    khoi_dong_ai()          # tao hang doi + tien trinh AI
    khoi_dong_camera()      # tien trinh camera dung hang doi cua AI
    for fn in (sensor_worker, photo_worker, ai_result_worker, camera_watchdog_worker):
        t = threading.Thread(target=fn, name=fn.__name__, daemon=True)
        t.start()
        threads[fn.__name__] = t
    atexit.register(dung_tien_trinh)


if __name__ == "__main__":
    don_thu_muc_anh()
    try:
        member_store.initialize()
    except (mysql.connector.Error, OSError, RuntimeError) as error:
        log("[MEMBERS] Chua dong bo ho so: " + str(error))
    khoi_dong_luong()
    # use_reloader=False de tranh mo webcam 2 lan
    app.run(host="0.0.0.0", port=int(os.environ.get("WEB_PORT","5000")), threaded=True, debug=False, use_reloader=False)
