import ctypes
import os
import sys
import time

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

class tobii_point2d_t(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]

class tobii_point3d_t(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

class tobii_display_area_t(ctypes.Structure):
    _fields_ = [
        ("top_left", tobii_point3d_t),
        ("top_right", tobii_point3d_t),
        ("bottom_left", tobii_point3d_t),
    ]

class tobii_gaze_point_t(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_int),
        ("position", tobii_point2d_t),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(tobii_gaze_point_t), ctypes.c_void_p)

dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_api_create.restype = ctypes.c_int

dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_device_create.restype = ctypes.c_int

dll.tobii_get_display_area.argtypes = [ctypes.c_void_p, ctypes.POINTER(tobii_display_area_t)]
dll.tobii_get_display_area.restype = ctypes.c_int

dll.tobii_set_display_area.argtypes = [ctypes.c_void_p, ctypes.POINTER(tobii_display_area_t)]
dll.tobii_set_display_area.restype = ctypes.c_int

dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int

dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

api = ctypes.c_void_p()
res = dll.tobii_api_create(ctypes.byref(api), None, None)
print("tobii_api_create:", res)

device = ctypes.c_void_p()
url = b"tobii-prp://IS510-100211404854"
res = dll.tobii_device_create(api, url, 1, ctypes.byref(device))
print("tobii_device_create:", res)

disp = tobii_display_area_t()
dll.tobii_get_display_area(device, ctypes.byref(disp))
print(f"Current Display Area: TL=({disp.top_left.x},{disp.top_left.y},{disp.top_left.z}) TR=({disp.top_right.x},{disp.top_right.y}) BL=({disp.bottom_left.x},{disp.bottom_left.y})")

# Set real display area
import math
w = 597.9
h = 336.2
ox = -597.9 / 2.0
oy = 14.0
z = -15.0
tiltDeg = 5.0
rad = tiltDeg * math.pi / 180.0
cosT = math.cos(rad)
sinT = math.sin(rad)

new_disp = tobii_display_area_t()
new_disp.bottom_left.x = float(ox)
new_disp.bottom_left.y = float(oy)
new_disp.bottom_left.z = float(z)

new_disp.top_left.x = float(ox)
new_disp.top_left.y = float(oy + h * cosT)
new_disp.top_left.z = float(z + h * sinT)

new_disp.top_right.x = float(ox + w)
new_disp.top_right.y = float(oy + h * cosT)
new_disp.top_right.z = float(z + h * sinT)

res_set = dll.tobii_set_display_area(device, ctypes.byref(new_disp))
print(f"tobii_set_display_area result: {res_set}")

dll.tobii_get_display_area(device, ctypes.byref(disp))
print(f"New Display Area: TL=({disp.top_left.x:.1f},{disp.top_left.y:.1f},{disp.top_left.z:.1f}) TR=({disp.top_right.x:.1f},{disp.top_right.y:.1f},{disp.top_right.z:.1f}) BL=({disp.bottom_left.x:.1f},{disp.bottom_left.y:.1f},{disp.bottom_left.z:.1f})")

cb_count = 0
valid_count = 0

def gaze_callback(p_gaze, user_data):
    global cb_count, valid_count
    cb_count += 1
    g = p_gaze.contents
    if g.validity == 1:
        valid_count += 1
    if cb_count <= 5 or g.validity == 1:
        print(f"  Gaze #{cb_count}: valid={g.validity} pos=({g.position.x:.4f}, {g.position.y:.4f}) ts={g.timestamp_us}")

cb_holder = GAZE_CB(gaze_callback)
res_sub = dll.tobii_gaze_point_subscribe(device, cb_holder, None)
print("tobii_gaze_point_subscribe:", res_sub)

t0 = time.time()
while time.time() - t0 < 3.0:
    dev_ptr = ctypes.c_void_p(device.value)
    dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
    dll.tobii_device_process_callbacks(device)

print(f"Finished: {cb_count} callbacks, {valid_count} valid")
