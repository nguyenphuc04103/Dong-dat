"""
TIEN TRINH AI RIENG (chay song song voi app.py)

Tai sao phai tach tien trinh?
  dlib / face_recognition chay rat nang va giu GIL cua Python. Neu chay chung tien trinh
  voi camera + Flask thi moi lan AI xu ly 1 khuon mat, video tren web bi DO.
  Chay o tien trinh rieng thi AI nang the nao video cung khong bi anh huong.

Giao tiep (multiprocessing.Queue):
  app.py  --(frame, thoi_gian)-->  in_q   --> tien trinh nay
  app.py  <--(ket qua)-----------  out_q  <-- tien trinh nay
Cac thong diep gui ve app.py (dict):
  {"loai": "san_sang", "ten": [...]}                    da load xong dataset
  {"loai": "ket_qua", "ts": ..., "khuon": [...]}        cac khuon mat tim thay
  {"loai": "loi", "noi_dung": "..."}                    loi khi xu ly 1 frame
Moi "khuon": {"box": (t, r, b, l) toa do anh goc, "ten", "quen", "anh": bytes JPEG | None, "idx"}
  "anh" = None nghia la nguoi nay vua duoc luu gan day (dang trong cooldown).
"""
import os
import time
import json
import queue


def ha_uu_tien():
    """Ha AI xuong muc uu tien THAP NHAT va chi cho chay tren mot nua so nhan CPU,
    de camera + trinh duyet luon co CPU -> video khong bao gio bi do khi AI dang xu ly."""
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = ctypes.c_void_p
            k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            h = k.GetCurrentProcess()
            k.SetPriorityClass(h, 0x00000040)               # IDLE_PRIORITY_CLASS
            n = os.cpu_count() or 1
            if n >= 4:
                dung = n // 2                                # AI chi dung nua tren cac nhan
                mask = ((1 << n) - 1) ^ ((1 << (n - dung)) - 1)
                k.SetProcessAffinityMask(h, mask)
        else:
            os.nice(10)
    except Exception:
        pass


def chon_khung_tot(ung_vien, nguong=0.4):
    """ung_vien: [(la_quen, khoang_cach, (t, r, b, l), ten)].
    Khi cac khung chong len nhau (HOG hay tra 2 khung cho 1 mat), giu khung nhan ra
    nguoi quen / co khoang cach nho nhat, bo khung con lai."""
    def dien_tich(loc):
        t, r, bt, l = loc
        return max(0, bt - t) * max(0, r - l)

    giu = []
    for uv in sorted(ung_vien, key=lambda x: (not x[0], x[1], -dien_tich(x[2]))):
        t, r, b, l = uv[2]
        trung = False
        for g in giu:
            t2, r2, b2, l2 = g[2]
            w = min(r, r2) - max(l, l2)
            h = min(b, b2) - max(t, t2)
            nho = max(1, min(dien_tich(uv[2]), dien_tich(g[2])))
            if w > 0 and h > 0 and (w * h) / nho > nguong:
                trung = True
                break
        if not trung:
            giu.append(uv)
    return giu


def cat_mat(frame, box, margin=0.8):
    """Cat vung quanh khuon mat (co le them de thay dau + vai) tu frame goc."""
    t, r, b, l = box
    h, w = frame.shape[:2]
    mh, mw = int((b - t) * margin), int((r - l) * margin)
    return frame[max(0, t - mh):min(h, b + mh), max(0, l - mw):min(w, r + mw)]


def load_dataset(face_recognition, dataset_dir):
    """Quet /dataset, moi anh = 1 nguoi (ten lay tu ten file)."""
    encodings, names = [], []
    os.makedirs(dataset_dir, exist_ok=True)
    for fname in sorted(os.listdir(dataset_dir)):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        ten = os.path.splitext(fname)[0].replace("_", " ")
        img = face_recognition.load_image_file(os.path.join(dataset_dir, fname))
        encs = face_recognition.face_encodings(img)
        if not encs:
            print(f"[AI] Bo qua {fname}: khong tim thay khuon mat.", flush=True)
            continue
        encodings.append(encs[0])
        names.append(ten)
    print(f"[AI] Da load {len(names)} khuon mat: {names}".encode("ascii", "replace").decode(), flush=True)
    return encodings, names


def load_registry(face_recognition, cfg):
    cache = cfg.get("registry_path")
    if cache and os.path.isfile(cache):
        import numpy as np
        with open(cache, encoding="utf8") as stream:
            rows = json.load(stream)
        return [np.asarray(r["encoding"],dtype=float) for r in rows], [r["key"] for r in rows]
    return load_dataset(face_recognition, cfg["dataset_dir"])


def chay_ai(in_q, out_q, cfg):
    """Ham chinh cua tien trinh AI. cfg: dataset_dir, tolerance, scale, nguoi_la,
    cooldown_quen, cooldown_la."""
    # Phai dat TRUOC khi import numpy/dlib: khong cho BLAS/OpenMP mo nhieu luong chiem het CPU
    for bien in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[bien] = "1"
    ha_uu_tien()
    out_q.cancel_join_thread()      # thoat nhanh, khong cho hang doi
    import cv2                      # chi tien trinh AI moi nap thu vien nang
    cv2.setNumThreads(1)
    import face_recognition

    known_enc, known_names = load_registry(face_recognition, cfg)
    out_q.put({"loai": "san_sang", "ten": list(known_names)})

    scale = cfg["scale"]
    inv = 1.0 / scale
    lan_cuoi = {}                   # ten -> thoi diem luu anh gan nhat (chong spam)

    while True:
        reload_event = cfg.get("reload_event")
        if reload_event is not None and reload_event.is_set():
            reload_event.clear()
            try:
                known_enc, known_names = load_registry(face_recognition, cfg)
                lan_cuoi.clear()
                out_q.put({"loai":"san_sang", "ten":list(known_names)})
            except Exception as error:
                out_q.put({"loai":"loi", "noi_dung":"Reload profiles: "+str(error)})
        try:
            item = in_q.get(timeout=1)
        except queue.Empty:
            continue
        if item is None:            # app.py bao dung
            return
        frame, ts = item
        _t0 = time.perf_counter()
        try:
            small = cv2.cvtColor(cv2.resize(frame, (0, 0), fx=scale, fy=scale), cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(small)
            if not locations:
                out_q.put({"loai": "ket_qua", "ts": ts, "khuon": []})   # bao "khong con ai" de xoa khung cu
                continue

            encodings = face_recognition.face_encodings(small, locations)
            if os.environ.get("CAM_DEBUG", "0") == "1":
                print(f"[AI] {len(locations)} mat, xu ly {time.perf_counter() - _t0:.2f}s", flush=True)
            ung_vien = []
            for loc, enc in zip(locations, encodings):
                ten, quen, kc = cfg["nguoi_la"], False, 9.9
                if known_enc:
                    dists = face_recognition.face_distance(known_enc, enc)
                    best = int(dists.argmin())
                    kc = float(dists[best])
                    if kc <= cfg["tolerance"]:
                        ten, quen = known_names[best], True
                ung_vien.append((quen, kc, loc, ten))

            now = time.monotonic()
            khuon = []
            for i, (quen, kc, (t, r, b, l), ten) in enumerate(chon_khung_tot(ung_vien)):
                box = (int(t * inv), int(r * inv), int(b * inv), int(l * inv))
                anh, moi = None, False
                cd = cfg["cooldown_quen"] if quen else cfg["cooldown_la"]
                if now - lan_cuoi.get(ten, -1e9) >= cd:
                    if quen:                                     # chi nguoi trong dataset moi chup anh
                        crop = cat_mat(frame, box)
                        if crop.size:
                            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                            if ok:
                                anh, moi = buf.tobytes(), True
                    else:
                        moi = True                               # nguoi la: chi bao, KHONG chup/luu anh
                    if moi:
                        lan_cuoi[ten] = now
                khuon.append({"box": box, "ten": ten, "quen": quen, "anh": anh, "moi": moi, "idx": i})
            out_q.put({"loai": "ket_qua", "ts": ts, "khuon": khuon})
        except Exception as e:
            out_q.put({"loai": "loi", "noi_dung": str(e)})
