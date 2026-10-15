"""
KIEM TRA WEBCAM LIEN TUC (khong chay Flask / AI).
Moi che do chay 15 giay, in FPS tung giay. Trong luc do: giay 1-5 KHONG co mat, giay 6-10 DUA MAT VAO,
giay 11-15 RA KHOI khung hinh. Xem che do nao FPS khong tut khi co mat.
Cach dung: tat chay.bat roi chay:  venv\\Scripts\\python cam_test.py
"""
import os
import time
import camera_process as C
import cv2

THOI_GIAN = 15


def thu(ch):
    cap = C._mo_voi(0, ch)
    if cap is None:
        print(f"\n== {ch['ten']}: khong mo duoc", flush=True)
        return None
    print(f"\n== {ch['ten']}  (giay 6-10: dua mat vao)", flush=True)
    t0 = time.monotonic()
    giay, n, sang, fps_list = 0, 0, 0.0, []
    while time.monotonic() - t0 < THOI_GIAN:
        ok, fr = cap.read()
        if ok:
            n += 1
            sang = float(fr[::16, ::16].mean())
        s = int(time.monotonic() - t0)
        if s > giay:
            giay = s
            fps_list.append(n)
            print(f"  giay {giay:2d}: {n:3d} fps  {'#' * min(n, 40):<40} sang {sang:3.0f}", flush=True)
            n = 0
    cap.release()
    co_mat = fps_list[5:10]
    return min(co_mat) if co_mat else 0


print("Dong het chuong trinh dang dung webcam truoc khi chay file nay.")
modes = [c for c in C._cau_hinh() if c["tu_dong"]]
kq = []
for ch in modes:
    input(f"\nNhan Enter de thu '{ch['ten']}' ...")
    kq.append((ch["ten"], thu(ch)))
print("\n===== TOM TAT (FPS thap nhat luc co mat) =====")
for ten, v in kq:
    print(f"  {ten:<24} {'khong mo duoc' if v is None else str(v) + ' fps'}")
print("\nChe do nao giu >= 15 fps luc co mat la che do nen dung.")
print("DSHOW tut con MSMF tot  ->  chay:  set CAM_BACKEND=msmf   roi chay.bat")
input("\nNhan Enter de thoat...")
