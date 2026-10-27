#!/usr/bin/env python3
"""
Tobii Eye Tracker 5L Enterprise PC & Mouse Controller
======================================================
Provides full PC control via eye tracking:
  1. Warp-on-Hotkey (Mouse Warp): Instantly snap mouse pointer to where you look on hotkey press.
  2. Continuous Smooth Gaze Mouse: 1€ adaptive filtering with fixation stabilization and zero-lag saccades.
  3. Dwell Clicking: Stare at any button or link to automatically left-click.
  4. Enterprise Telemetry: Real-time 2D gaze, 6DOF head pose, and 3D eye position.
  5. Toggle Hotkey: One key (F9) to instantly enable/disable tracking.
"""

import ctypes
from ctypes import wintypes, byref, windll
import os
import sys
import time
import math
import json
import threading

# Load patched 64-bit Tobii Stream Engine DLL
DLL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "x64_patched_tobii_stream_engine.dll"))
if not os.path.exists(DLL_PATH):
    DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")

dll = ctypes.CDLL(DLL_PATH)

# Windows Virtual Keys
VK_LBUTTON   = 0x01
VK_RBUTTON   = 0x02
VK_MBUTTON   = 0x04
VK_XBUTTON1  = 0x05
VK_XBUTTON2  = 0x06
VK_CAPITAL   = 0x14 # Caps Lock
VK_ESCAPE    = 0x1B
VK_SPACE     = 0x20
VK_F8        = 0x77
VK_F9        = 0x78
VK_F10       = 0x79
VK_F12       = 0x7B

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

# Tobii Stream Engine Structures
class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
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

class TobiiVector3(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]

class TobiiUserPositionGuide(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("left_validity", ctypes.c_uint),
        ("left_xyz", TobiiVector3),
        ("right_validity", ctypes.c_uint),
        ("right_xyz", TobiiVector3),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)
HEAD_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiHeadPose), ctypes.c_void_p)
GUIDE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiUserPositionGuide), ctypes.c_void_p)

# Win32 helpers
def get_cursor_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    windll.user32.SetCursorPos(int(x), int(y))

def click_mouse(button='left'):
    down_flag = MOUSEEVENTF_LEFTDOWN if button == 'left' else MOUSEEVENTF_RIGHTDOWN
    up_flag = MOUSEEVENTF_LEFTUP if button == 'left' else MOUSEEVENTF_RIGHTUP
    windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
    time.sleep(0.015)
    windll.user32.mouse_event(up_flag, 0, 0, 0, 0)

def is_key_down(vk_code):
    return (windll.user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

def get_screen_resolution():
    w = windll.user32.GetSystemMetrics(0) # SM_CXSCREEN
    h = windll.user32.GetSystemMetrics(1) # SM_CYSCREEN
    return (w if w > 0 else 1920, h if h > 0 else 1080)


class OneEuroFilter:
    """1€ Filter: Adaptive Low-Pass Filter for high accuracy fixation + instantaneous saccade tracking."""
    def __init__(self, min_cutoff=0.8, beta=0.03, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def _alpha(self, cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt) if dt > 0 else 1.0

    def filter(self, x, t):
        if self.t_prev is None:
            self.x_prev = x
            self.dx_prev = 0.0
            self.t_prev = t
            return x

        dt = max(t - self.t_prev, 0.0001)
        # Compute derivative (velocity)
        dx = (x - self.x_prev) / dt
        edx = self.dx_prev + self._alpha(self.d_cutoff, dt) * (dx - self.dx_prev)
        self.dx_prev = edx

        # Adaptive cutoff based on velocity
        cutoff = self.min_cutoff + self.beta * abs(edx)
        alpha = self._alpha(cutoff, dt)
        x_filtered = self.x_prev + alpha * (x - self.x_prev)
        self.x_prev = x_filtered
        self.t_prev = t
        return x_filtered

    def reset(self):
        self.x_prev = None
        self.t_prev = None
        self.dx_prev = 0.0


class TobiiMouseController:
    def __init__(self, config_file="mouse_settings.json"):
        self.config_file = config_file
        self.load_config()

        self.screen_w, self.screen_h = get_screen_resolution()
        print(f"[Controller] Primary Display: {self.screen_w} x {self.screen_h}")

        self.filter_x = OneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)
        self.filter_y = OneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)

        self.latest_gaze_norm = (0.5, 0.5)
        self.latest_gaze_pixel = (self.screen_w // 2, self.screen_h // 2)
        self.gaze_valid = False
        self.last_gaze_time = 0.0

        # Dwell click tracking
        self.dwell_start_time = None
        self.dwell_anchor = (0, 0)
        self.last_click_time = 0.0

        # State
        self.is_running = True
        self.continuous_mode = self.config.get("continuous_mode_enabled", False)
        self.dwell_click_enabled = self.config.get("dwell_click_enabled", False)
        self.warp_key = getattr(sys.modules[__name__], self.config.get("warp_key", "VK_CAPITAL"), VK_CAPITAL)
        self.toggle_key = getattr(sys.modules[__name__], self.config.get("toggle_key", "VK_F9"), VK_F9)

        # Prev key states for edge trigger
        self.prev_toggle_down = False
        self.prev_warp_down = False

        # Tobii Stream Engine pointers
        self.api = ctypes.c_void_p()
        self.device = ctypes.c_void_p()

    def load_config(self):
        defaults = {
            "warp_key": "VK_CAPITAL",        # Caps Lock for instant Mouse Warp
            "toggle_key": "VK_F9",           # F9 to pause/resume continuous mode
            "continuous_mode_enabled": False, # Start with Warp-on-Hotkey; F9 enables continuous tracking
            "dwell_click_enabled": False,    # Hands-free dwell clicking
            "dwell_time_seconds": 0.55,      # 550ms gaze dwell triggers click
            "dwell_radius_pixels": 40,       # Movement tolerance during dwell
            "dwell_cooldown_seconds": 0.80,  # Cooldown between clicks
            "min_cutoff": 0.70,              # Lower = smoother on fixations (less jitter)
            "beta": 0.04,                    # Higher = faster snap on saccades (zero lag)
            "screen_margin_x": 0,
            "screen_margin_y": 0,
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    defaults.update(json.load(f))
            except Exception as e:
                print(f"[Config] Error reading {self.config_file}: {e}")
        else:
            with open(self.config_file, "w") as f:
                json.dump(defaults, f, indent=4)

        self.config = defaults
        self.min_cutoff = float(defaults["min_cutoff"])
        self.beta = float(defaults["beta"])
        self.dwell_time = float(defaults["dwell_time_seconds"])
        self.dwell_radius = float(defaults["dwell_radius_pixels"])
        self.dwell_cooldown = float(defaults["dwell_cooldown_seconds"])

    def on_gaze_data(self, p_data, ud):
        d = p_data.contents
        now = time.time()
        if d.validity == 1:
            self.gaze_valid = True
            self.last_gaze_time = now
            self.latest_gaze_norm = (d.position_x, d.position_y)

            # Filter coordinates
            fx = self.filter_x.filter(d.position_x, now)
            fy = self.filter_y.filter(d.position_y, now)

            # Screen bounds clamping
            px = int(max(0, min(self.screen_w - 1, fx * self.screen_w)))
            py = int(max(0, min(self.screen_h - 1, fy * self.screen_h)))
            self.latest_gaze_pixel = (px, py)
        else:
            if now - self.last_gaze_time > 0.25:
                self.gaze_valid = False

    def on_head_pose(self, p_data, ud):
        pass # Available for head tilt / scroll expansion

    def on_user_guide(self, p_data, ud):
        pass

    def init_stream_engine(self):
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
            print(f"[Tobii] Error creating API: {res}")
            return False

        url = b"tobii-prp://IS510-100211404854"
        res = dll.tobii_device_create(self.api, url, 1, byref(self.device))
        if res != 0:
            print(f"[Tobii] Error creating device: {res}")
            return False

        # Subscribe to gaze
        self._cb_gaze = GAZE_CB(self.on_gaze_data)
        dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
        dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
        r_gaze = dll.tobii_gaze_point_subscribe(self.device, self._cb_gaze, None)

        # Subscribe to head pose
        self._cb_head = HEAD_CB(self.on_head_pose)
        dll.tobii_head_pose_subscribe.argtypes = [ctypes.c_void_p, HEAD_CB, ctypes.c_void_p]
        dll.tobii_head_pose_subscribe.restype = ctypes.c_int
        r_head = dll.tobii_head_pose_subscribe(self.device, self._cb_head, None)

        print(f"[Tobii] Connected: Gaze Sub={r_gaze}, Head Pose Sub={r_head}")
        return True

    def warp_to_gaze(self):
        """Instantly teleport cursor to current gaze position."""
        if self.gaze_valid:
            gx, gy = self.latest_gaze_pixel
            set_cursor_pos(gx, gy)
            # Reset filter so subsequent continuous motion doesn't interpolate from old position
            self.filter_x.reset()
            self.filter_y.reset()

    def process_mouse_interaction(self):
        now = time.time()

        # Check Toggle Hotkey (F9)
        toggle_down = is_key_down(self.toggle_key)
        if toggle_down and not self.prev_toggle_down:
            self.continuous_mode = not self.continuous_mode
            status = "ENABLED" if self.continuous_mode else "PAUSED"
            print(f"\n>>> [Mouse Mode] Continuous Eye Tracking is now {status} <<<")
            try:
                windll.user32.MessageBeep(0)
            except Exception:
                pass
            self.filter_x.reset()
            self.filter_y.reset()
            self.dwell_start_time = None
        self.prev_toggle_down = toggle_down

        # Check Warp Hotkey (Caps Lock / configured key)
        warp_down = is_key_down(self.warp_key)
        if warp_down:
            self.warp_to_gaze()
        self.prev_warp_down = warp_down

        # Continuous Tracking Mode
        if self.continuous_mode and self.gaze_valid:
            gx, gy = self.latest_gaze_pixel
            set_cursor_pos(gx, gy)

            # Dwell Click Handling
            if self.dwell_click_enabled:
                dist = math.hypot(gx - self.dwell_anchor[0], gy - self.dwell_anchor[1])
                if dist > self.dwell_radius or self.dwell_start_time is None:
                    # Moved outside anchor: restart dwell timer
                    self.dwell_anchor = (gx, gy)
                    self.dwell_start_time = now
                else:
                    dwell_duration = now - self.dwell_start_time
                    if dwell_duration >= self.dwell_time and (now - self.last_click_time) >= self.dwell_cooldown:
                        print(f" [Dwell Click] Clicked at ({gx}, {gy})")
                        click_mouse('left')
                        self.last_click_time = now
                        self.dwell_start_time = None
                        try:
                            windll.user32.MessageBeep(0)
                        except Exception:
                            pass

    def run(self):
        print("=" * 65)
        print("   Tobii Eye Tracker 5L - Enterprise Mouse & PC Controller   ")
        print("=" * 65)
        print(f" * Warp-on-Hotkey: Press [{self.config['warp_key']}] to snap cursor to gaze instantly")
        print(f" * Continuous Mode: Press [{self.config['toggle_key']}] to toggle hands-free tracking")
        print(f" * Dwell Clicking: {'ENABLED' if self.dwell_click_enabled else 'DISABLED'} (toggle in {self.config_file})")
        print(f" * Press Ctrl+C in this console to exit")
        print("=" * 65)

        if not self.init_stream_engine():
            print("[Error] Failed to initialize eye tracker.")
            return

        last_status_print = 0
        try:
            while self.is_running:
                dev_ptr = ctypes.c_void_p(self.device.value)
                dll.tobii_wait_for_callbacks(1, byref(dev_ptr))
                dll.tobii_device_process_callbacks(self.device)

                self.process_mouse_interaction()

                now = time.time()
                if now - last_status_print > 1.5:
                    mode_str = "CONTINUOUS" if self.continuous_mode else "WARP-ONLY"
                    valid_str = "TRACKING (Valid)" if self.gaze_valid else "LOOKING AWAY"
                    sys.stdout.write(f"\rStatus: [{mode_str}] | Eye State: [{valid_str:16s}] | Gaze: ({self.latest_gaze_pixel[0]:4d}, {self.latest_gaze_pixel[1]:4d})")
                    sys.stdout.flush()
                    last_status_print = now

                time.sleep(0.005) # 200Hz loop

        except KeyboardInterrupt:
            print("\n[Controller] Stopping...")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        if self.device:
            dll.tobii_device_destroy.argtypes = [ctypes.c_void_p]
            dll.tobii_device_destroy.restype = ctypes.c_int
            dll.tobii_device_destroy(self.device)
        if self.api:
            dll.tobii_api_destroy.argtypes = [ctypes.c_void_p]
            dll.tobii_api_destroy.restype = ctypes.c_int
            dll.tobii_api_destroy(self.api)
        print("[Controller] Cleaned up and exited.")

if __name__ == "__main__":
    controller = TobiiMouseController()
    controller.run()
