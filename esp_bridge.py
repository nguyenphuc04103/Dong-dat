"""Local gateway for the existing ESP8266/ESP32 HTTP APIs.

No synthetic shaking and no additional network work inside the MCU sensor loop.
Sensor polling and photo transfer run in separate Python workers.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import ipaddress
import json
import math
import os
from pathlib import Path
import threading
import time

from PIL import Image, UnidentifiedImageError
import requests

MAX_JPEG = 256 * 1024
TIMEOUT = (1.0, 2.0)


def lan_ip(value, optional=False):
    value = str(value).strip()
    if optional and not value:
        return ""
    address = ipaddress.IPv4Address(value)
    if not address.is_private or address.is_unspecified or address.is_multicast or address.is_reserved:
        raise ValueError("Nhập IPv4 trong mạng nội bộ, ví dụ 192.168.0.104; không nhập URL.")
    return str(address)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def controller_state(data):
    if not isinstance(data, dict) or type(data.get("alarm")) is not bool:
        raise ValueError("ESP8266 không trả đúng API /api.")
    if type(data.get("mpu")) is not bool or type(data.get("mpu_ready")) is not bool:
        raise ValueError("API thiếu trạng thái MPU.")
    value = data.get("vibration")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                              not math.isfinite(value) or not 0 <= value <= 16):
        raise ValueError("Giá trị rung không hợp lệ.")
    if data["mpu_ready"] and value is None:
        raise ValueError("MPU sẵn sàng nhưng thiếu số rung.")
    result = dict(data)
    qualified = data.get("warning", value is not None and 1 <= value < 2)
    result["warning"] = bool(qualified and data["mpu"] and data["mpu_ready"] and not data["alarm"])
    result["level"] = ("alarm" if data["alarm"] else "error" if not data["mpu"] else
                       "calibrating" if not data["mpu_ready"] else "warning" if result["warning"] else "safe")
    return result


def camera_state(data):
    if not isinstance(data, dict) or type(data.get("camera_ready")) is not bool:
        raise ValueError("ESP32 không trả đúng API camera.")
    for key in ("captures", "manual_captures", "controller_boot", "revision", "generation"):
        value = data.get(key)
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError("API camera thiếu bộ đếm hợp lệ: " + key)
    for key in ("first_capture_ms", "latest_capture_ms"):
        value = data.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= 0xffffffff):
            raise ValueError("API camera có thời gian không hợp lệ.")
    return data


class PhotoStore:
    """Immutable JPEGs and per-photo metadata survive web restart, independent of MySQL."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.records = {}
        for path in self.root.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if (record.get("id") == path.stem and len(path.stem) == 64 and
                        self.root.joinpath(path.stem + ".jpg").is_file()):
                    self.records[path.stem] = record
            except (OSError, ValueError):
                continue

    def save(self, data, identity, kind, details):
        if not data or len(data) > MAX_JPEG:
            raise ValueError("Ảnh rỗng hoặc vượt giới hạn 256 KiB.")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != "JPEG" or image.width > 2048 or image.height > 2048:
                    raise ValueError("Camera phải gửi JPEG, tối đa 2048×2048.")
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Camera trả dữ liệu không phải ảnh JPEG hợp lệ.") from error
        key = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        meta = self.root / (key + ".json")
        target = self.root / (key + ".jpg")
        with self.lock:
            if meta.exists() and target.exists():
                record = json.loads(meta.read_text(encoding="utf-8"))
                self.records[key] = record
                return record, False
            saved = datetime.now(timezone.utc).isoformat()
            record = {"id": key, "kind": kind, "saved_at": saved,
                      "url": "/static/captures/earthquake/" + key + ".jpg", **details}
            temp = target.with_suffix(".jpg.tmp")
            temp.write_bytes(data)
            os.replace(temp, target)
            atomic_json(meta, record)
            self.records[key] = record
            return record, True

    def list(self, limit=100):
        with self.lock:
            records = deepcopy(list(self.records.values()))
        return sorted(records, key=lambda r: r["saved_at"], reverse=True)[:limit]


class EspBridge:
    def __init__(self, config_file, photo_root, on_state=None, on_photo=None):
        self.config_file = Path(config_file)
        self.lock = threading.RLock()
        self.photo_lock = threading.Lock()
        self.last_manual_identity = None
        config = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.config = {"controller_ip": lan_ip(config["controller_ip"]),
                       "camera_ip": lan_ip(config.get("camera_ip", ""), optional=True)}
        self.store = PhotoStore(photo_root)
        self.on_state, self.on_photo = on_state, on_photo
        self.state = {"online": False, "controller": None, "camera_ip": self.config["camera_ip"],
                      "camera_online": False, "camera": None, "last_seen": None, "error": "Chưa kết nối ESP8266",
                      "photo_error": "", "photo_last_seen": None}

    def snapshot(self):
        with self.lock:
            result = deepcopy(self.state)
        result["controller_age_s"] = None if result["last_seen"] is None else round(time.monotonic()-result["last_seen"], 1)
        if result["controller_age_s"] is not None and result["controller_age_s"] > 5:
            result["online"] = False
        return result

    def get_config(self):
        with self.lock:
            return dict(self.config)

    def configure(self, data):
        config = {"controller_ip": lan_ip(data["controller_ip"]),
                  "camera_ip": lan_ip(data.get("camera_ip", ""), optional=True)}
        with self.lock:
            atomic_json(self.config_file, config)
            self.config = config
            self.state.update(online=False, controller=None, camera_ip=config["camera_ip"],
                              camera_online=False, camera=None, last_seen=None, error="Đang kết nối địa chỉ mới")
        return config

    @staticmethod
    def get_json(ip):
        response = requests.get("http://" + ip + "/api", timeout=TIMEOUT, allow_redirects=False)
        response.raise_for_status()
        if len(response.content) > 16384:
            raise ValueError("API trả dữ liệu quá lớn.")
        return response.json()

    def poll_controller(self):
        config = self.get_config()
        try:
            data = controller_state(self.get_json(config["controller_ip"]))
            discovered = data.get("camera_ip", "") if data.get("camera_online") else ""
            camera_ip = config["camera_ip"] or lan_ip(discovered, optional=True)
            with self.lock:
                if config != self.config:
                    return
                self.state.update(online=True, controller=data, camera_ip=camera_ip,
                                  last_seen=time.monotonic(), error="")
            # Never invoke callbacks while holding the bridge lock.
            if self.on_state:
                self.on_state(data, camera_ip)
        except (requests.RequestException, ValueError, KeyError) as error:
            with self.lock:
                if config == self.config:
                    self.state.update(online=False, error=str(error))
            # Retain the last alarm state; disconnection is not a reset.

    def command(self, action):
        commands = {"mo_cua": "open", "dong_cua": "close", "tat_coi": "mute",
                    "reset": "reset", "test": "test"}
        if action not in commands:
            raise ValueError("Lệnh không hợp lệ.")
        ip = self.get_config()["controller_ip"]
        response = requests.get("http://"+ip+"/cmd", params={"x": commands[action]},
                                timeout=TIMEOUT, allow_redirects=False)
        # Preserve HTTP 409: closing the door during an alarm is refused by the controller.
        response.encoding = "utf-8"
        return response.status_code, response.text[:1000]

    @staticmethod
    def photo_identity(ip, data, kind):
        if kind == "manual":
            key = [ip, kind, data.get("manual_captures")]
        else:
            # revision changes on RESET although image buffers remain unchanged.
            key = [ip, kind, data.get("controller_boot"), data.get("generation")]
            key += [data.get("first_capture_ms"), data.get("latest_capture_ms") if kind == "latest" else None,
                    data.get("captures") if kind == "latest" else 1]
        return key

    def save_photo(self, ip, jpeg, info, kind):
        identity = self.photo_identity(ip, info, kind)
        if kind == "manual":
            identity += [sha256(jpeg).hexdigest()]
        record, created = self.store.save(jpeg, identity, kind,
            {"camera_ip": ip, "event_boot": info.get("controller_boot") if kind != "manual" else None,
             "event_revision": info.get("revision") if kind != "manual" else None,
             "event_generation": info.get("generation") if kind != "manual" else None,
             "capture_number": info.get("manual_captures") if kind == "manual" else
                               info.get("captures") if kind == "latest" else 1})
        if created and self.on_photo:
            self.on_photo(record)
        return record

    @staticmethod
    def get_jpeg(ip, route):
        with requests.get("http://"+ip+route, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if not response.headers.get("Content-Type", "").lower().startswith("image/jpeg"):
                raise ValueError("Endpoint camera không trả JPEG.")
            parts, total = [], 0
            for block in response.iter_content(8192):
                total += len(block)
                if total > MAX_JPEG:
                    raise ValueError("Ảnh camera quá lớn.")
                parts.append(block)
            return b"".join(parts)

    def poll_photos(self):
        with self.photo_lock:
            ip = self.snapshot()["camera_ip"]
            if not ip:
                return
            try:
                data = camera_state(self.get_json(ip))
                with self.lock:
                    self.state.update(camera=data, camera_online=True, photo_last_seen=time.monotonic(), photo_error="")
                if not data["camera_ready"]:
                    return
                jobs = []
                if data.get("captures", 0) > 0:
                    jobs.append(("first", "/alarm.jpg"))
                    if data["captures"] > 1:
                        jobs.append(("latest", "/latest.jpg"))
                if data.get("manual_captures", 0) > 0:
                    jobs.append(("manual", "/manual.jpg"))
                else:
                    self.last_manual_identity = None
                for kind, route in jobs:
                    identity = self.photo_identity(ip, data, kind)
                    token = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                    if (kind == "manual" and self.last_manual_identity == identity) or (kind != "manual" and token in self.store.records):
                        continue
                    jpeg = self.get_jpeg(ip, route)
                    after = camera_state(self.get_json(ip))
                    # Prevent labeling a photo with metadata from a different event/minute.
                    if self.photo_identity(ip, after, kind) != identity:
                        continue
                    self.save_photo(ip, jpeg, data, kind)
                    if kind == "manual":
                        self.last_manual_identity = identity
            except (requests.RequestException, ValueError, KeyError, OSError) as error:
                with self.lock:
                    self.state.update(camera_online=False, photo_error=str(error))

    def manual_capture(self):
        with self.photo_lock:
            ip = self.snapshot()["camera_ip"]
            if not ip:
                raise ValueError("Chưa nhận được IP camera.")
            jpeg = self.get_jpeg(ip, "/capture")
            data = camera_state(self.get_json(ip))
            if not data.get("camera_ready"):
                raise ValueError("Không xác nhận được trạng thái camera sau chụp.")
            result = self.save_photo(ip, jpeg, data, "manual")
            self.last_manual_identity = self.photo_identity(ip, data, "manual")
            return result

    def controller_worker(self, stop):
        while not stop.is_set():
            self.poll_controller()
            stop.wait(1)

    def photo_worker(self, stop):
        while not stop.is_set():
            self.poll_photos()
            stop.wait(1)
