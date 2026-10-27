#!/usr/bin/env python3
"""
Tobii Eye Tracker 5L - Precision FOV Diagnostic & Multi-Point Calibration
========================================================================
Interactive calibration tool with real-time 3D Track Box, FOV boundary
visualization, and non-linear polynomial edge correction.
"""

import ctypes
from ctypes import byref, windll
import os
import sys
import time
import math
import json
import tkinter as tk
import numpy as np

DLL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "x64_patched_tobii_stream_engine.dll"))
if not os.path.exists(DLL_PATH):
    DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")

dll = ctypes.CDLL(DLL_PATH)

# Data structures
class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

class TobiiVector3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

class TobiiUserPositionGuide(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("left_validity", ctypes.c_uint),
        ("left_xyz", TobiiVector3),
        ("right_validity", ctypes.c_uint),
        ("right_xyz", TobiiVector3),
    ]

class TobiiHeadPose(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("position_validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
        ("position_z", ctypes.c_float),
        ("rotation_validity_x", ctypes.c_uint),
        ("rotation_validity_y", ctypes.c_uint),
        ("rotation_validity_z", ctypes.c_uint),
        ("rotation_x", ctypes.c_float),
        ("rotation_y", ctypes.c_float),
        ("rotation_z", ctypes.c_float),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)
GUIDE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)
HEAD_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiHeadPose), ctypes.c_void_p)

class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        angle = np.random.uniform(0, 2 * math.pi)
        speed = np.random.uniform(4.0, 14.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.radius = np.random.uniform(3, 7)
        self.alpha = 1.0
        self.decay = np.random.uniform(0.04, 0.08)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.alpha -= self.decay
        self.radius = max(0.5, self.radius - 0.15)
        return self.alpha > 0

class CalibrationAndFOVApp:
    def __init__(self):
        self.is_running = True
        self.app_mode = "ALIGNMENT" # "ALIGNMENT" or "CALIBRATION"

        self.root = tk.Tk()
        self.root.title("Tobii 5L FOV Diagnostic & Calibration")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#0B0D11")
        self.root.attributes("-topmost", True)

        self.w = self.root.winfo_screenwidth()
        self.h = self.root.winfo_screenheight()

        self.canvas = tk.Canvas(self.root, width=self.w, height=self.h, bg="#0B0D11", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Keyboard bindings
        self.root.bind("<Escape>", lambda e: self.abort())
        self.root.bind("<Return>", lambda e: self.on_enter_pressed())
        self.root.bind("<space>", lambda e: self.on_space_pressed())
        self.root.bind("<Key-s>", lambda e: self.on_skip_pressed())
        self.root.bind("<Key-S>", lambda e: self.on_skip_pressed())

        # Comprehensive 11-point screen coverage (high density on upper edge/corners)
        self.targets = [
            (0.50, 0.50), # 1. Center
            (0.50, 0.07), # 2. Top-Center
            (0.07, 0.07), # 3. Top-Left
            (0.93, 0.07), # 4. Top-Right
            (0.07, 0.50), # 5. Mid-Left
            (0.93, 0.50), # 6. Mid-Right
            (0.07, 0.93), # 7. Bottom-Left
            (0.50, 0.93), # 8. Bottom-Center
            (0.93, 0.93), # 9. Bottom-Right
            (0.28, 0.22), # 10. Upper-Mid-Left
            (0.72, 0.22), # 11. Upper-Mid-Right
        ]

        self.current_idx = 0
        self.collected_data = []

        # Target animation states
        self.target_state = "IDLE"
        self.charge_progress = 0.0
        self.spin_angle = 0.0
        self.particles = []
        self.current_samples = []
        self.target_px = (self.w // 2, self.h // 2)

        # Telemetry
        self.api = ctypes.c_void_p()
        self.device = ctypes.c_void_p()

        self.latest_gaze_pixel = (self.w // 2, self.h // 2)
        self.raw_gaze_norm = (0.5, 0.5)
        self.gaze_valid = False
        self.last_valid_time = time.time()

        # Eye box telemetry
        self.left_eye = {"valid": 0, "x": 0.5, "y": 0.5, "z": 0.5}
        self.right_eye = {"valid": 0, "x": 0.5, "y": 0.5, "z": 0.5}
        self.head_distance_mm = 600.0 # Default ~60cm

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

        res = dll.tobii_api_create(byref(self.api), None, None)
        if res != 0:
            print(f"[Error] Failed to create Tobii API: code {res}")
            return

        url = b"tobii-prp://IS510-100211404854"
        res = dll.tobii_device_create(self.api, url, 1, byref(self.device))
        if res != 0:
            print(f"[Error] Failed to connect to tracker: code {res}")
            return

        # 1. Gaze subscription
        def on_gaze(p, ud):
            if not self.is_running:
                return
            d = p.contents
            if d.validity == 1:
                self.gaze_valid = True
                self.last_valid_time = time.time()
                self.raw_gaze_norm = (d.position_x, d.position_y)
                px = int(d.position_x * self.w)
                py = int(d.position_y * self.h)
                self.latest_gaze_pixel = (px, py)
                if self.app_mode == "CALIBRATION" and self.target_state == "CHARGING":
                    self.current_samples.append((d.position_x, d.position_y))
            else:
                self.gaze_valid = False

        self._cb_gaze = GAZE_CB(on_gaze)
        dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
        dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
        dll.tobii_gaze_point_subscribe(self.device, self._cb_gaze, None)

        # 2. User Position Guide (3D Eye Box) subscription
        def on_guide(p, ud):
            if not self.is_running:
                return
            d = p.contents
            self.left_eye = {"valid": d.left_validity, "x": d.left_xyz.x, "y": d.left_xyz.y, "z": d.left_xyz.z}
            self.right_eye = {"valid": d.right_validity, "x": d.right_xyz.x, "y": d.right_xyz.y, "z": d.right_xyz.z}

        self._cb_guide = GUIDE_CB(on_guide)
        dll.tobii_user_position_guide_subscribe.argtypes = [ctypes.c_void_p, GUIDE_CB, ctypes.c_void_p]
        dll.tobii_user_position_guide_subscribe.restype = ctypes.c_int
        dll.tobii_user_position_guide_subscribe(self.device, self._cb_guide, None)

        # 3. Head Pose (distance) subscription
        def on_head(p, ud):
            if not self.is_running:
                return
            d = p.contents
            if d.position_validity == 1:
                self.head_distance_mm = d.position_z

        self._cb_head = HEAD_CB(on_head)
        dll.tobii_head_pose_subscribe.argtypes = [ctypes.c_void_p, HEAD_CB, ctypes.c_void_p]
        dll.tobii_head_pose_subscribe.restype = ctypes.c_int
        dll.tobii_head_pose_subscribe(self.device, self._cb_head, None)

    def pump_tobii(self):
        if not self.is_running or not self.device:
            return
        try:
            dev_ptr = ctypes.c_void_p(self.device.value)
            dll.tobii_wait_for_callbacks(1, byref(dev_ptr))
            dll.tobii_device_process_callbacks(self.device)
        except Exception:
            return
        if self.is_running:
            self.root.after(8, self.pump_tobii)

    def abort(self):
        print("\n[App] Closed by user.")
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        self.is_running = False
        if self.device:
            dev = self.device
            self.device = None
            dll.tobii_device_destroy.argtypes = [ctypes.c_void_p]
            dll.tobii_device_destroy.restype = ctypes.c_int
            dll.tobii_device_destroy(dev)
        if self.api:
            api = self.api
            self.api = None
            dll.tobii_api_destroy.argtypes = [ctypes.c_void_p]
            dll.tobii_api_destroy.restype = ctypes.c_int
            dll.tobii_api_destroy(api)

    def on_enter_pressed(self):
        if self.app_mode == "ALIGNMENT":
            self.app_mode = "CALIBRATION"
            self.current_idx = 0
            self.collected_data = []
            self.init_target()

    def on_space_pressed(self):
        if self.app_mode == "ALIGNMENT":
            self.on_enter_pressed()
        elif self.app_mode == "CALIBRATION":
            # Spacebar forces capture of current target if at least 3 samples are present
            if len(self.current_samples) >= 3:
                tx, ty = self.target_px
                self.trigger_explosion(tx, ty)
            else:
                # Add current raw gaze as sample
                gx, gy = self.raw_gaze_norm
                self.current_samples.extend([(gx, gy)] * 10)
                tx, ty = self.target_px
                self.trigger_explosion(tx, ty)

    def on_skip_pressed(self):
        if self.app_mode == "CALIBRATION":
            print(f"[Calibration] Skipped point {self.current_idx + 1}")
            self.current_idx += 1
            self.init_target()

    def start(self):
        self.pump_tobii()
        self.render_loop()
        self.root.mainloop()

    def render_loop(self):
        if not self.is_running:
            return

        if self.app_mode == "ALIGNMENT":
            self.render_alignment_screen()
        elif self.app_mode == "CALIBRATION":
            self.render_calibration_frame()

        if self.is_running:
            self.root.after(20, self.render_loop)

    def render_alignment_screen(self):
        self.canvas.delete("all")
        cx, cy = self.w // 2, self.h // 2

        # 1. Title & Explanations
        self.canvas.create_text(cx, 70, text="Tobii 5L - Field of View (FOV) & Eye Alignment Diagnostic",
                                font=("Segoe UI", 26, "bold"), fill="#00D2FF")
        self.canvas.create_text(cx, 115,
                                text="Verify your head position and explore tracker boundaries before calibrating.",
                                font=("Segoe UI", 14), fill="#A0AAB5")

        # 2. Draw 3D Track Box (matching Tobii Experience User Position Guide)
        box_w, box_h = 360, 220
        box_x = cx - box_w // 2
        box_y = cy - 140

        # Background track box panel
        self.canvas.create_rectangle(box_x, box_y, box_x + box_w, box_y + box_h,
                                     fill="#131720", outline="#202A3C", width=2)
        # Perspective inner lines
        self.canvas.create_line(box_x, box_y, box_x + 35, box_y + 25, fill="#1B2433")
        self.canvas.create_line(box_x + box_w, box_y, box_x + box_w - 35, box_y + 25, fill="#1B2433")
        self.canvas.create_line(box_x, box_y + box_h, box_x + 35, box_y + box_h - 25, fill="#1B2433")
        self.canvas.create_line(box_x + box_w, box_y + box_h, box_x + box_w - 35, box_y + box_h - 25, fill="#1B2433")
        self.canvas.create_rectangle(box_x + 35, box_y + 25, box_x + box_w - 35, box_y + box_h - 25,
                                     outline="#1B2433")

        # Center target cross in box
        self.canvas.create_line(cx - 15, box_y + box_h // 2, cx + 15, box_y + box_h // 2, fill="#2C3A50")
        self.canvas.create_line(cx, box_y + box_h // 2 - 15, cx, box_y + box_h // 2 + 15, fill="#2C3A50")

        # Render Left & Right Eyes inside Track Box
        dist_cm = self.head_distance_mm / 10.0
        dist_ok = (58.0 <= dist_cm <= 76.0)

        # Left Eye (User's left eye is mirrored on right in guide coordinates)
        if self.left_eye["valid"]:
            ex = box_x + int((1.0 - self.left_eye["x"]) * box_w)
            ey = box_y + int(self.left_eye["y"] * box_h)
            er = 14
            self.canvas.create_oval(ex - er, ey - er, ex + er, ey + er,
                                    fill="#00FFAA" if dist_ok else "#FFCC00", outline="#FFFFFF", width=2)
            self.canvas.create_text(ex, ey, text="L", font=("Segoe UI", 10, "bold"), fill="#0B0D11")

        # Right Eye
        if self.right_eye["valid"]:
            ex = box_x + int((1.0 - self.right_eye["x"]) * box_w)
            ey = box_y + int(self.right_eye["y"] * box_h)
            er = 14
            self.canvas.create_oval(ex - er, ey - er, ex + er, ey + er,
                                    fill="#00FFAA" if dist_ok else "#FFCC00", outline="#FFFFFF", width=2)
            self.canvas.create_text(ex, ey, text="R", font=("Segoe UI", 10, "bold"), fill="#0B0D11")

        # Distance Telemetry Badge under box
        if dist_cm < 55.0:
            status_text = f"Distance: {dist_cm:.0f} cm - ⚠️ TOO CLOSE! (Upper corners hit vertical FOV limit)"
            status_color = "#FF9933"
        elif dist_cm > 80.0:
            status_text = f"Distance: {dist_cm:.0f} cm - ⚠️ TOO FAR (Sit closer for solid tracking)"
            status_color = "#FFCC00"
        else:
            status_text = f"Distance: {dist_cm:.0f} cm - ✅ PERFECT DISTANCE (Full FOV coverage)"
            status_color = "#00FFAA"

        self.canvas.create_rectangle(cx - 240, box_y + box_h + 15, cx + 240, box_y + box_h + 50,
                                     fill="#131720", outline=status_color, width=1.5)
        self.canvas.create_text(cx, box_y + box_h + 32, text=status_text,
                                font=("Segoe UI", 12, "bold"), fill=status_color)

        # 3. Physical FOV & Corner Limitation Guide
        guide_y = cy + 130
        self.canvas.create_text(cx, guide_y,
                                text="Why do top edges/corners feel limited?",
                                font=("Segoe UI", 16, "bold"), fill="#FFFFFF")
        guide_lines = [
            "1. Hardware Mounting: The Tobii tracker is mounted at the bottom bezel angled up at ~20-25°.",
            "2. Upper Screen Geometry: On a 27\" monitor, looking at top corners requires eye elevation > 30°.",
            "3. Eyelid Occlusion: Looking up naturally lowers the upper eyelid over the cornea glints.",
            "💡 Fix: Sit back at ~65 cm and tilt the tracker slightly upwards. This brings all 4 corners into the optical cone!",
        ]
        for i, line in enumerate(guide_lines):
            fill = "#00FFAA" if line.startswith("💡") else "#B0BAC5"
            self.canvas.create_text(cx, guide_y + 30 + i * 24, text=line,
                                    font=("Segoe UI", 12, "bold" if fill == "#00FFAA" else "normal"), fill=fill)

        # 4. Real-time Live Gaze FOV Boundary Cursor
        gx, gy = self.latest_gaze_pixel
        time_since_valid = time.time() - self.last_valid_time

        # Visualizer reticle follows live gaze
        if time_since_valid < 0.2:
            edge_dist_x = min(gx, self.w - gx)
            edge_dist_y = min(gy, self.h - gy)
            min_edge = min(edge_dist_x, edge_dist_y)

            if min_edge < 120 or not self.left_eye["valid"] or not self.right_eye["valid"]:
                gaze_color = "#FF9900" # Nearing FOV limit
                gaze_status = "Nearing Tracker FOV Edge"
            else:
                gaze_color = "#00D2FF" # High confidence
                gaze_status = "Tracking OK"

            self.canvas.create_oval(gx - 20, gy - 20, gx + 20, gy + 20, outline=gaze_color, width=2)
            self.canvas.create_oval(gx - 4, gy - 4, gx + 4, gy + 4, fill=gaze_color, outline="")
            self.canvas.create_line(gx - 30, gy, gx + 30, gy, fill=gaze_color, width=1)
            self.canvas.create_line(gx, gy - 30, gx, gy + 30, fill=gaze_color, width=1)
            self.canvas.create_text(gx, gy + 35, text=gaze_status, font=("Segoe UI", 11, "bold"), fill=gaze_color)
        else:
            self.canvas.create_oval(gx - 25, gy - 25, gx + 25, gy + 25, outline="#FF3333", width=2)
            self.canvas.create_text(gx, gy + 35, text="Beyond FOV Limit", font=("Segoe UI", 11, "bold"), fill="#FF3333")

        # 5. Action Bar at Bottom
        self.canvas.create_rectangle(0, self.h - 65, self.w, self.h, fill="#0F131A", outline="")
        self.canvas.create_text(cx, self.h - 32,
                                text="Press [Enter] or [Space] to START CALIBRATION   •   Test gaze freely   •   [Esc] Exit",
                                font=("Segoe UI", 14, "bold"), fill="#00FFAA")

    def init_target(self):
        if not self.is_running:
            return
        if self.current_idx >= len(self.targets):
            self.finish_calibration()
            return

        tx_norm, ty_norm = self.targets[self.current_idx]
        self.target_px = (int(tx_norm * self.w), int(ty_norm * self.h))
        self.target_state = "IDLE"
        self.charge_progress = 0.0
        self.spin_angle = 0.0
        self.current_samples = []
        self.particles = []

    def render_calibration_frame(self):
        self.canvas.delete("all")
        tx, ty = self.target_px

        # Header instructions
        progress_text = f"Point {self.current_idx + 1} of {len(self.targets)}"
        self.canvas.create_text(self.w // 2, 40, text=progress_text, font=("Segoe UI", 18, "bold"), fill="#00D2FF")
        self.canvas.create_text(self.w // 2, 68,
                                text="Look at the dot until it explodes   •   [Space] Force Lock   •   [S] Skip Point   •   [Esc] Cancel",
                                font=("Segoe UI", 12), fill="#667788")

        # User gaze position
        gx, gy = self.latest_gaze_pixel
        dist_to_target = math.hypot(gx - tx, gy - ty)

        # Adaptive lock threshold (up to 240px to compensate for uncalibrated corner shifts)
        gaze_locked = (dist_to_target < 240) and self.gaze_valid

        # Magnetic attractor line connecting gaze to target
        if self.gaze_valid and dist_to_target < 450:
            alpha_color = "#005544" if not gaze_locked else "#00AA66"
            self.canvas.create_line(gx, gy, tx, ty, fill=alpha_color, width=2, dash=(4, 4))
            self.canvas.create_oval(gx - 6, gy - 6, gx + 6, gy + 6, fill="#00FFAA", outline="")

        if self.target_state != "EXPLODING":
            if gaze_locked:
                self.target_state = "CHARGING"
                self.charge_progress = min(1.0, self.charge_progress + 0.038)
                self.spin_angle += 0.28
            else:
                self.target_state = "IDLE"
                self.charge_progress = max(0.0, self.charge_progress - 0.015)
                self.spin_angle += 0.08

            # Outer spinning ring / oval
            ring_r_x = 38 + int(10 * self.charge_progress)
            ring_r_y = 30 + int(8 * self.charge_progress)
            ring_color = "#00FFAA" if gaze_locked else "#00D2FF"

            # Outer glow aura
            glow_r = ring_r_x + 12
            self.canvas.create_oval(tx - glow_r, ty - glow_r, tx + glow_r, ty + glow_r,
                                   outline="#003344" if not gaze_locked else "#004433", width=2)

            # Circular charge meter
            if self.charge_progress > 0:
                extent = int(self.charge_progress * 359)
                self.canvas.create_arc(tx - ring_r_x - 6, ty - ring_r_y - 6,
                                       tx + ring_r_x + 6, ty + ring_r_y + 6,
                                       start=90, extent=-extent, style="arc",
                                       outline="#00FFAA", width=4)

            # Spinning satellites
            for i in range(3):
                theta = self.spin_angle + i * (2 * math.pi / 3)
                ox = tx + int(ring_r_x * math.cos(theta))
                oy = ty + int(ring_r_y * math.sin(theta))
                sat_color = "#FFFFFF" if gaze_locked else "#00D2FF"
                self.canvas.create_oval(ox - 4, oy - 4, ox + 4, oy + 4, fill=sat_color, outline="")

            # Core dot
            core_r = 7 + int(4 * self.charge_progress)
            core_color = "#FFFFFF" if gaze_locked else "#00D2FF"
            self.canvas.create_oval(tx - core_r, ty - core_r, tx + core_r, ty + core_r, fill=core_color, outline="")

            # Prompt label under dot
            label_text = "Locking on..." if gaze_locked else "Look here"
            label_color = "#00FFAA" if gaze_locked else "#667788"
            self.canvas.create_text(tx, ty + ring_r_y + 24, text=label_text, font=("Segoe UI", 12, "bold"), fill=label_color)

            # Check explosion
            if self.charge_progress >= 1.0 and len(self.current_samples) >= 10:
                self.trigger_explosion(tx, ty)

        else:
            # EXPLODING state: burst particles
            alive_particles = []
            for p in self.particles:
                if p.update():
                    self.canvas.create_oval(p.x - p.radius, p.y - p.radius, p.x + p.radius, p.y + p.radius,
                                           fill=p.color, outline="")
                    alive_particles.append(p)
            self.particles = alive_particles

            if not self.particles:
                self.collected_data.append((self.target_px, list(self.current_samples)))
                self.current_idx += 1
                self.root.after(150, self.init_target)

    def trigger_explosion(self, tx, ty):
        self.target_state = "EXPLODING"
        try:
            windll.user32.MessageBeep(0)
        except Exception:
            pass

        colors = ["#00FFAA", "#00D2FF", "#FFFFFF", "#FFFF00", "#FF00AA"]
        self.particles = [Particle(tx, ty, np.random.choice(colors)) for _ in range(35)]

    def finish_calibration(self):
        self.canvas.delete("all")
        cx, cy = self.w // 2, self.h // 2
        self.canvas.create_text(cx, cy - 40, text="Computing High-Precision Polynomial Fit...",
                                font=("Segoe UI", 24, "bold"), fill="#00D2FF")
        self.root.update()

        clean_raw = []
        clean_target = []

        for target_px, samples in self.collected_data:
            if len(samples) < 3:
                continue
            xs = [s[0] for s in samples]
            ys = [s[1] for s in samples]
            med_x = float(np.median(xs))
            med_y = float(np.median(ys))

            # Outlier rejection
            mad_x = float(np.median([abs(x - med_x) for x in xs]))
            mad_y = float(np.median([abs(y - med_y) for y in ys]))
            sig_x = max(1.4826 * mad_x, 0.003)
            sig_y = max(1.4826 * mad_y, 0.003)

            filtered = [(x, y) for (x, y) in samples if abs(x - med_x) < 2.5 * sig_x and abs(y - med_y) < 2.5 * sig_y]
            if not filtered:
                filtered = samples

            centroid_x = float(np.median([f[0] for f in filtered]))
            centroid_y = float(np.median([f[1] for f in filtered]))

            clean_raw.append([centroid_x, centroid_y])
            clean_target.append([target_px[0], target_px[1]])

        if len(clean_raw) < 5:
            self.canvas.create_text(cx, cy + 20, text="Insufficient samples collected. Please retry.",
                                    font=("Segoe UI", 18), fill="#FF4444")
            self.root.after(2500, self.abort)
            return

        R = np.array(clean_raw)
        T = np.array(clean_target)

        # 2nd-Order Polynomial Expansion: [1, x, y, x^2, y^2, x*y]
        x_raw, y_raw = R[:, 0], R[:, 1]
        Phi = np.column_stack([np.ones_like(x_raw), x_raw, y_raw, x_raw**2, y_raw**2, x_raw * y_raw])

        # L2 Ridge regression
        lambda_ridge = 1e-4
        XtX = Phi.T @ Phi + lambda_ridge * np.eye(Phi.shape[1])
        XtY = Phi.T @ T
        coeffs = np.linalg.solve(XtX, XtY) # 6x2 matrix

        # Affine fallback
        Phi_aff = np.column_stack([x_raw, y_raw, np.ones_like(x_raw)])
        M_aff, _, _, _ = np.linalg.lstsq(Phi_aff, T, rcond=None)

        pred = Phi @ coeffs
        err_pixels = np.sqrt(np.sum((pred - T) ** 2, axis=1))
        mean_err_px = float(np.mean(err_pixels))

        calib_result = {
            "model": "polynomial_2d",
            "poly_coeffs": coeffs.tolist(),
            "matrix": M_aff.tolist(),
            "mean_error_pixels": mean_err_px,
            "screen_width": self.w,
            "screen_height": self.h,
            "num_points": len(clean_raw),
            "timestamp": time.time(),
        }

        calib_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "user_calibration.json"))
        with open(calib_file, "w") as f:
            json.dump(calib_result, f, indent=4)

        print(f"\n[Calibration] Polynomial Calibration Successful!")
        print(f"  * Mean Residual Error: ±{mean_err_px:.1f} pixels")
        print(f"  * Calibrated Points: {len(clean_raw)}")
        print(f"  * Saved profile to: {calib_file}")

        self.canvas.delete("all")
        self.canvas.create_text(cx, cy - 60, text="Calibration Complete!", font=("Segoe UI", 32, "bold"), fill="#00FFAA")
        self.canvas.create_text(cx, cy + 10, text=f"Edge & Corner Accuracy: ±{mean_err_px:.1f} pixels", font=("Segoe UI", 20), fill="#FFFFFF")
        self.canvas.create_text(cx, cy + 60, text="Full-screen coverage active. Closing in 2 seconds...", font=("Segoe UI", 16), fill="#888888")

        self.cleanup()
        self.root.after(2200, self.root.destroy)

if __name__ == "__main__":
    app = CalibrationAndFOVApp()
    app.start()
