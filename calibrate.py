#!/usr/bin/env python3
"""
Tobii Eye Tracker 5L - Rapid 5-Point Calibration Tool
======================================================
Calibrates the user's individual fovea-to-optical axis (angle kappa)
and physical mounting geometry in ~10 seconds.

Fits an optimal 2D affine calibration transform:
    [Screen_X, Screen_Y]^T = A * [Raw_Norm_X, Raw_Norm_Y]^T + B

Saves the result to `user_calibration.json`, which is automatically loaded
by `tobii_controller.py` for pixel-accurate cursor control.
"""

import ctypes
from ctypes import byref, windll
import os
import sys
import time
import json
import tkinter as tk
import numpy as np

DLL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "x64_patched_tobii_stream_engine.dll"))
dll = ctypes.CDLL(DLL_PATH)

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)

class CalibrationApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tobii 5L Rapid Calibration")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#111111")
        self.root.attributes("-topmost", True)

        self.w = self.root.winfo_screenwidth()
        self.h = self.root.winfo_screenheight()

        self.canvas = tk.Canvas(self.root, width=self.w, height=self.h, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.root.bind("<Escape>", lambda e: self.abort())

        # Calibration targets (normalized coordinates)
        self.targets = [
            (0.50, 0.50), # 1. Center
            (0.15, 0.15), # 2. Top-Left
            (0.85, 0.15), # 3. Top-Right
            (0.15, 0.85), # 4. Bottom-Left
            (0.85, 0.85), # 5. Bottom-Right
        ]

        self.current_idx = 0
        self.collected_data = [] # List of (target_pixel, [raw_samples])

        # Tobii stream setup
        self.api = ctypes.c_void_p()
        self.device = ctypes.c_void_p()
        self.latest_gaze = None
        self.recording = False
        self.current_samples = []

        self.init_tobii()

    def init_tobii(self):
        dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
        dll.tobii_api_create.restype = ctypes.c_int
        dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        dll.tobii_device_create.restype = ctypes.c_int
        dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        dll.tobii_wait_for_callbacks.restype = ctypes.c_int
        dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
        dll.tobii_device_process_callbacks.restype = ctypes.c_int

        dll.tobii_api_create(byref(self.api), None, None)
        url = b"tobii-prp://IS510-100211404854"
        res = dll.tobii_device_create(self.api, url, 1, byref(self.device))
        if res != 0:
            print(f"[Error] Failed to connect to tracker: code {res}")
            self.root.destroy()
            return

        def on_gaze(p, ud):
            d = p.contents
            if d.validity == 1:
                self.latest_gaze = (d.position_x, d.position_y)
                if self.recording:
                    self.current_samples.append((d.position_x, d.position_y))

        self._cb = GAZE_CB(on_gaze)
        dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
        dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
        dll.tobii_gaze_point_subscribe(self.device, self._cb, None)

    def abort(self):
        print("\n[Calibration] Aborted by user.")
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        if self.device:
            dll.tobii_device_destroy(self.device)
        if self.api:
            dll.tobii_api_destroy(self.api)

    def pump_tobii(self):
        if self.device:
            dev_ptr = ctypes.c_void_p(self.device.value)
            dll.tobii_wait_for_callbacks(1, byref(dev_ptr))
            dll.tobii_device_process_callbacks(self.device)
        self.root.after(10, self.pump_tobii)

    def start(self):
        self.pump_tobii()
        self.show_intro()
        self.root.mainloop()

    def show_intro(self):
        self.canvas.delete("all")
        cx, cy = self.w // 2, self.h // 2
        self.canvas.create_text(cx, cy - 80, text="Tobii 5L Rapid Calibration", font=("Segoe UI", 32, "bold"), fill="#00D2FF")
        self.canvas.create_text(cx, cy - 10, text="Look at each colored dot as it appears and follow it with your eyes.", font=("Segoe UI", 18), fill="#CCCCCC")
        self.canvas.create_text(cx, cy + 30, text="Keep your head comfortably still in your normal sitting posture.", font=("Segoe UI", 16), fill="#888888")
        self.canvas.create_text(cx, cy + 120, text="Starting in 2 seconds... (Press Esc to cancel)", font=("Segoe UI", 14, "italic"), fill="#00FF88")

        self.root.after(2200, self.next_target)

    def next_target(self):
        if self.current_idx >= len(self.targets):
            self.finish_calibration()
            return

        tx_norm, ty_norm = self.targets[self.current_idx]
        tx_px = int(tx_norm * self.w)
        ty_px = int(ty_norm * self.h)

        self.current_target_px = (tx_px, ty_px)
        self.current_samples = []
        self.recording = False

        self.animate_target(tx_px, ty_px, 0)

    def animate_target(self, x, y, step):
        self.canvas.delete("all")

        # Instruction counter
        counter_txt = f"Point {self.current_idx + 1} of {len(self.targets)}"
        self.canvas.create_text(self.w // 2, 40, text=counter_txt, font=("Segoe UI", 16), fill="#555555")

        # Outer ring pulsates
        radius = 24 + int(6 * np.sin(step * 0.25))
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, outline="#00D2FF", width=3)
        # Inner dot
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#FFFFFF", outline="")

        if step == 20: # 600ms settling time elapsed, begin recording
            self.recording = True

        if step < 50: # ~1.5s total time per dot
            self.root.after(30, lambda: self.animate_target(x, y, step + 1))
        else:
            self.recording = False
            self.collected_data.append((self.current_target_px, list(self.current_samples)))
            try:
                windll.user32.MessageBeep(0)
            except Exception:
                pass
            self.current_idx += 1
            self.root.after(250, self.next_target)

    def finish_calibration(self):
        self.canvas.delete("all")
        cx, cy = self.w // 2, self.h // 2
        self.canvas.create_text(cx, cy - 40, text="Calculating Calibration Matrix...", font=("Segoe UI", 24), fill="#00D2FF")
        self.root.update()

        # Process samples with median & MAD
        clean_raw = []
        clean_target = []

        for target_px, samples in self.collected_data:
            if len(samples) < 5:
                continue
            xs = [s[0] for s in samples]
            ys = [s[1] for s in samples]
            med_x = float(np.median(xs))
            med_y = float(np.median(ys))

            # MAD filtering
            mad_x = float(np.median([abs(x - med_x) for x in xs]))
            mad_y = float(np.median([abs(y - med_y) for y in ys]))
            sig_x = max(1.4826 * mad_x, 0.005)
            sig_y = max(1.4826 * mad_y, 0.005)

            filtered = [(x, y) for (x, y) in samples if abs(x - med_x) < 2.5 * sig_x and abs(y - med_y) < 2.5 * sig_y]
            if not filtered:
                filtered = samples

            centroid_x = float(np.median([f[0] for f in filtered]))
            centroid_y = float(np.median([f[1] for f in filtered]))

            clean_raw.append([centroid_x, centroid_y, 1.0])
            clean_target.append([target_px[0], target_px[1]])

        if len(clean_raw) < 3:
            self.canvas.create_text(cx, cy + 20, text="Insufficient gaze samples collected. Please retry.", font=("Segoe UI", 18), fill="#FF4444")
            self.root.after(2500, self.abort)
            return

        # Solve least-squares: Raw @ M = Target -> M = (3x2)
        # [raw_x, raw_y, 1.0] @ [[a11, a21], [a12, a22], [bx, by]] = [target_x, target_y]
        R = np.array(clean_raw)
        T = np.array(clean_target)
        M, residuals, rank, s = np.linalg.lstsq(R, T, rcond=None)

        pred = R @ M
        err_pixels = np.sqrt(np.sum((pred - T) ** 2, axis=1))
        mean_err_px = float(np.mean(err_pixels))

        calib_result = {
            "matrix": M.tolist(), # 3x2 matrix
            "mean_error_pixels": mean_err_px,
            "screen_width": self.w,
            "screen_height": self.h,
            "num_points": len(clean_raw),
            "timestamp": time.time(),
        }

        calib_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "user_calibration.json"))
        with open(calib_file, "w") as f:
            json.dump(calib_result, f, indent=4)

        print(f"\n[Calibration] Calibration successful!")
        print(f"  * Mean Residual Error: {mean_err_px:.1f} pixels")
        print(f"  * Profile saved to: {calib_file}")

        self.canvas.delete("all")
        self.canvas.create_text(cx, cy - 60, text="Calibration Complete!", font=("Segoe UI", 32, "bold"), fill="#00FF88")
        self.canvas.create_text(cx, cy + 10, text=f"Accuracy: ±{mean_err_px:.1f} pixels across screen", font=("Segoe UI", 20), fill="#FFFFFF")
        self.canvas.create_text(cx, cy + 60, text="Calibration profile active. Closing in 2 seconds...", font=("Segoe UI", 16), fill="#888888")

        self.cleanup()
        self.root.after(2200, self.root.destroy)

if __name__ == "__main__":
    app = CalibrationApp()
    app.start()
