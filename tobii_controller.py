#!/usr/bin/env python3
"""
Tobii Eye Tracker 5L Enterprise PC & Mouse Controller
======================================================
Zero-lag gaze pointing controller (all clicking handled with physical mouse):
  1. Instant Mouse Warp (Caps Lock): Teleports cursor to gaze with zero latency.
  2. Continuous Hands-Free Eye Mouse (F9): 1€ adaptive filter (steady fixations, instant saccades).
  3. High-Precision Polynomial Calibration: Automatically evaluates `user_calibration.json`.
  4. Live Alignment Nudge: Ctrl + Arrow Keys to adjust cursor offset in real time.
"""

import ctypes
from ctypes import wintypes, byref, windll
import os
import sys
import time
import json
import math

# Load patched 64-bit Tobii Stream Engine DLL
DLL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "x64_patched_tobii_stream_engine.dll"))
if not os.path.exists(DLL_PATH):
    DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")

dll = ctypes.CDLL(DLL_PATH)

# Windows Virtual Keys
VK_CONTROL   = 0x11
VK_CAPITAL   = 0x14 # Caps Lock
VK_ESCAPE    = 0x1B
VK_SPACE     = 0x20
VK_LEFT      = 0x25
VK_UP        = 0x26
VK_RIGHT     = 0x27
VK_DOWN      = 0x28
VK_F8        = 0x77
VK_F9        = 0x78
VK_F10       = 0x79
VK_F12       = 0x7B

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
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

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

def get_cursor_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    windll.user32.SetCursorPos(int(x), int(y))

def is_key_down(vk_code):
    return (windll.user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

def get_screen_resolution():
    w = windll.user32.GetSystemMetrics(0) # SM_CXSCREEN
    h = windll.user32.GetSystemMetrics(1) # SM_CYSCREEN
    return (w if w > 0 else 1920, h if h > 0 else 1080)


class FastOneEuroFilter:
    """Ultra-responsive 1€ Filter tuned specifically for normalized gaze coordinates."""
    def __init__(self, min_cutoff=1.2, beta=8.0, d_cutoff=1.0):
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
        dx = (x - self.x_prev) / dt
        edx = self.dx_prev + self._alpha(self.d_cutoff, dt) * (dx - self.dx_prev)
        self.dx_prev = edx

        cutoff = self.min_cutoff + self.beta * abs(edx)
        alpha = self._alpha(cutoff, dt)
        x_filtered = self.x_prev + alpha * (x - self.x_prev)
        self.x_prev = x_filtered
        self.t_prev = t
        return x_filtered

    def reset(self, x=None):
        self.x_prev = x
        self.t_prev = None
        self.dx_prev = 0.0


class TobiiMouseController:
    def __init__(self, config_file="mouse_settings.json"):
        self.config_file = config_file
        self.screen_w, self.screen_h = get_screen_resolution()
        print(f"[Controller] Primary Display: {self.screen_w} x {self.screen_h}")

        self.poly_x = None
        self.poly_y = None
        self.aff_x = None
        self.aff_y = None
        self.load_calibration()
        self.load_config()

        # Filters with tuned high-speed response
        self.filter_x = FastOneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)
        self.filter_y = FastOneEuroFilter(min_cutoff=self.min_cutoff, beta=self.beta)

        self.latest_raw_pixel = (self.screen_w // 2, self.screen_h // 2)
        self.latest_filtered_pixel = (self.screen_w // 2, self.screen_h // 2)
        self.gaze_valid = False
        self.last_gaze_time = 0.0

        # State flags
        self.is_running = True
        self.continuous_mode = self.config.get("continuous_mode_enabled", False)
        self.warp_key = getattr(sys.modules[__name__], self.config.get("warp_key", "VK_CAPITAL"), VK_CAPITAL)
        self.toggle_key = getattr(sys.modules[__name__], self.config.get("toggle_key", "VK_F9"), VK_F9)

        # Key state tracking
        self.prev_toggle_down = False
        self.prev_warp_down = False
        self.prev_arrows = {"up": False, "down": False, "left": False, "right": False}

        # Tobii Stream Engine pointers
        self.api = ctypes.c_void_p()
        self.device = ctypes.c_void_p()

    def load_calibration(self):
        calib_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "user_calibration.json"))
        if os.path.exists(calib_file):
            try:
                with open(calib_file, "r") as f:
                    data = json.load(f)
                    if "poly_coeffs" in data:
                        raw_c = data["poly_coeffs"]
                        self.poly_x = [row[0] for row in raw_c]
                        self.poly_y = [row[1] for row in raw_c]
                    if "matrix" in data:
                        raw_m = data["matrix"]
                        self.aff_x = [raw_m[0][0], raw_m[1][0], raw_m[2][0]]
                        self.aff_y = [raw_m[0][1], raw_m[1][1], raw_m[2][1]]

                    if self.use_affine and self.aff_x is not None:
                        print(f"[Calibration] Active: High-Stability Affine Profile (Mean Error: ±{data.get('mean_error_pixels', 0):.1f} px)")
                    elif self.poly_x is not None:
                        print(f"[Calibration] Active: Polynomial Profile ({data.get('num_points', 9)} points, Mean Error: ±{data.get('mean_error_pixels', 0):.1f} px)")
            except Exception as e:
                print(f"[Calibration] Error loading {calib_file}: {e}")
        else:
            print("[Calibration] No custom profile found. Run 'python calibrate.py' for sub-centimeter accuracy.")

    def load_config(self):
        defaults = {
            "warp_key": "VK_CAPITAL",           # Caps Lock for instant Mouse Warp
            "toggle_key": "VK_F9",              # F9 to toggle continuous hands-free tracking
            "continuous_mode_enabled": False,   # Start with Warp-on-Hotkey
            "edge_gain": 1.12,                  # Edge Overdrive: allows effortless reaching of borders
            "use_affine": True,                 # Use affine matrix to avoid polynomial Runge curling
            "min_cutoff": 1.2,                  # Responsive fixation filtering
            "beta": 8.0,                        # High beta = instantaneous zero-lag saccades
            "offset_x": 0,                      # Manual horizontal alignment nudge (Ctrl+Left/Right)
            "offset_y": 0,                      # Manual vertical alignment nudge (Ctrl+Up/Down)
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
        self.edge_gain = float(defaults.get("edge_gain", 1.12))
        self.use_affine = bool(defaults.get("use_affine", True))
        self.min_cutoff = float(defaults.get("min_cutoff", 1.2))
        self.beta = float(defaults.get("beta", 8.0))
        self.offset_x = int(defaults.get("offset_x", 0))
        self.offset_y = int(defaults.get("offset_y", 0))

    def save_config(self):
        self.config["offset_x"] = self.offset_x
        self.config["offset_y"] = self.offset_y
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def map_to_pixel(self, x, y):
        """High-precision coordinate projection with Progressive Edge Overdrive."""
        # 1. Progressive Edge Overdrive (zero distortion inside content, smooth reach on tabs/taskbar)
        if self.edge_gain > 1.0:
            dev_x = x - 0.5
            x = 0.5 + dev_x * (1.0 + (self.edge_gain - 1.0) * (4.0 * dev_x * dev_x))
            dev_y = y - 0.5
            y = 0.5 + dev_y * (1.0 + (self.edge_gain - 1.0) * (4.0 * dev_y * dev_y))

        # 2. Coordinate Mapping
        if self.use_affine and self.aff_x is not None:
            ax = self.aff_x
            ay = self.aff_y
            px = int(ax[0]*x + ax[1]*y + ax[2]) + self.offset_x
            py = int(ay[0]*x + ay[1]*y + ay[2]) + self.offset_y
        elif self.poly_x is not None:
            cx = self.poly_x
            cy = self.poly_y
            x2 = x * x
            y2 = y * y
            xy = x * y
            px = int(cx[0] + cx[1]*x + cx[2]*y + cx[3]*x2 + cx[4]*y2 + cx[5]*xy) + self.offset_x
            py = int(cy[0] + cy[1]*x + cy[2]*y + cy[3]*x2 + cy[4]*y2 + cy[5]*xy) + self.offset_y
        elif self.aff_x is not None:
            ax = self.aff_x
            ay = self.aff_y
            px = int(ax[0]*x + ax[1]*y + ax[2]) + self.offset_x
            py = int(ay[0]*x + ay[1]*y + ay[2]) + self.offset_y
        else:
            px = int(x * self.screen_w) + self.offset_x
            py = int(y * self.screen_h) + self.offset_y

        # 3. Primary screen bounds clamping
        px = max(0, min(self.screen_w - 1, px))
        py = max(0, min(self.screen_h - 1, py))
        return px, py

    def on_gaze_data(self, p_data, ud):
        d = p_data.contents
        now = time.time()

        if d.validity == 1:
            self.gaze_valid = True
            self.last_gaze_time = now

            # 1. Instant Raw Position (zero lag for mouse warp)
            raw_px, raw_py = self.map_to_pixel(d.position_x, d.position_y)
            self.latest_raw_pixel = (raw_px, raw_py)

            # 2. Filtered Position (fast adaptive smoothing for continuous mode)
            fx = self.filter_x.filter(d.position_x, now)
            fy = self.filter_y.filter(d.position_y, now)
            filt_px, filt_py = self.map_to_pixel(fx, fy)
            self.latest_filtered_pixel = (filt_px, filt_py)
        else:
            if now - self.last_gaze_time > 0.25:
                self.gaze_valid = False

    def on_head_pose(self, p_data, ud):
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

        self._cb_gaze = GAZE_CB(self.on_gaze_data)
        dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
        dll.tobii_gaze_point_subscribe.restype = ctypes.c_int
        r_gaze = dll.tobii_gaze_point_subscribe(self.device, self._cb_gaze, None)

        self._cb_head = HEAD_CB(self.on_head_pose)
        dll.tobii_head_pose_subscribe.argtypes = [ctypes.c_void_p, HEAD_CB, ctypes.c_void_p]
        dll.tobii_head_pose_subscribe.restype = ctypes.c_int
        r_head = dll.tobii_head_pose_subscribe(self.device, self._cb_head, None)

        print(f"[Tobii] Connected: Gaze Sub={r_gaze}, Head Pose Sub={r_head}")
        return True

    def warp_to_gaze(self):
        """Instantly teleport cursor to raw gaze position with zero smoothing lag."""
        if self.gaze_valid:
            gx, gy = self.latest_raw_pixel
            set_cursor_pos(gx, gy)
            # Reset continuous filter to current warp location
            self.filter_x.reset()
            self.filter_y.reset()

    def check_live_nudge(self):
        """Ctrl + Arrow keys adjust alignment in real time."""
        if not is_key_down(VK_CONTROL):
            return

        changed = False
        step = 8

        down = is_key_down(VK_DOWN)
        if down and not self.prev_arrows["down"]:
            self.offset_y += step
            changed = True
        self.prev_arrows["down"] = down

        up = is_key_down(VK_UP)
        if up and not self.prev_arrows["up"]:
            self.offset_y -= step
            changed = True
        self.prev_arrows["up"] = up

        left = is_key_down(VK_LEFT)
        if left and not self.prev_arrows["left"]:
            self.offset_x -= step
            changed = True
        self.prev_arrows["left"] = left

        right = is_key_down(VK_RIGHT)
        if right and not self.prev_arrows["right"]:
            self.offset_x += step
            changed = True
        self.prev_arrows["right"] = right

        if changed:
            print(f"\n [Offset Adjusted] X={self.offset_x:+d} px, Y={self.offset_y:+d} px")
            self.save_config()

    def process_mouse_interaction(self):
        self.check_live_nudge()

        # Check Toggle Hotkey (F9)
        toggle_down = is_key_down(self.toggle_key)
        if toggle_down and not self.prev_toggle_down:
            self.continuous_mode = not self.continuous_mode
            status = "ENABLED" if self.continuous_mode else "PAUSED"
            print(f"\n>>> [Mouse Mode] Continuous Eye Tracking is now {status} <<<")
            self.filter_x.reset()
            self.filter_y.reset()
        self.prev_toggle_down = toggle_down

        # Warp Key (Caps Lock) Handling
        warp_down = is_key_down(self.warp_key)
        if warp_down:
            self.warp_to_gaze()
        self.prev_warp_down = warp_down

        # Continuous Tracking Mode
        if self.continuous_mode and self.gaze_valid:
            gx, gy = self.latest_filtered_pixel
            set_cursor_pos(gx, gy)

    def run(self):
        print("=" * 70)
        print("      Tobii Eye Tracker 5L - Enterprise PC & Mouse Controller      ")
        print("=" * 70)
        print(f" * Mouse Warp:          Hold [{self.config['warp_key']}] to snap cursor to gaze instantly")
        print(f" * Clicking:            Use your physical mouse to click normally")
        print(f" * Continuous Mode:     Press [{self.config['toggle_key']}] to toggle hands-free tracking")
        print(f" * Live Alignment:      Ctrl + Arrow Keys to nudge offset on the fly")
        print(f" * Rapid Calibration:   Run 'python calibrate.py' for sub-centimeter accuracy")
        print(f" * Exit:                Ctrl+C in this console")
        print("=" * 70)

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
                if now - last_status_print > 1.2:
                    mode_str = "CONTINUOUS" if self.continuous_mode else "WARP"
                    valid_str = "TRACKING" if self.gaze_valid else "LOOKING AWAY"
                    sys.stdout.write(f"\rMode: [{mode_str:10s}] | State: [{valid_str:12s}] | Gaze: ({self.latest_raw_pixel[0]:4d}, {self.latest_raw_pixel[1]:4d}) | Offset: ({self.offset_x:+d}, {self.offset_y:+d})")
                    sys.stdout.flush()
                    last_status_print = now

                time.sleep(0.003) # 330Hz ultra-low latency loop

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
