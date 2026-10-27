"""
Tobii Stream Engine Background Keepalive.
Keeps the 5L eye tracking sensor active so that UserPositionGuide (Tobii Experience)
and Gaze (Tobii Ghost) always receive frames instantly without cold starts.
"""
import ctypes
import os
import sys
import time

DLL_PATH = os.path.abspath("x64_patched_tobii_stream_engine.dll")
dll = ctypes.CDLL(DLL_PATH)

class TobiiGazePoint(ctypes.Structure):
    _fields_ = [
        ("timestamp_us", ctypes.c_int64),
        ("validity", ctypes.c_uint),
        ("position_x", ctypes.c_float),
        ("position_y", ctypes.c_float),
    ]

GAZE_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(TobiiGazePoint), ctypes.c_void_p)
def dummy_cb(p, u): pass
cb = GAZE_CB(dummy_cb)

dll.tobii_api_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p]
dll.tobii_api_create.restype = ctypes.c_int

dll.tobii_device_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_device_create.restype = ctypes.c_int

dll.tobii_gaze_point_subscribe.argtypes = [ctypes.c_void_p, GAZE_CB, ctypes.c_void_p]
dll.tobii_gaze_point_subscribe.restype = ctypes.c_int

dll.tobii_wait_for_callbacks.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
dll.tobii_wait_for_callbacks.restype = ctypes.c_int

dll.tobii_device_process_callbacks.argtypes = [ctypes.c_void_p]
dll.tobii_device_process_callbacks.restype = ctypes.c_int

dll.tobii_device_destroy.argtypes = [ctypes.c_void_p]
dll.tobii_device_destroy.restype = ctypes.c_int

dll.tobii_api_destroy.argtypes = [ctypes.c_void_p]
dll.tobii_api_destroy.restype = ctypes.c_int

def run():
    print("[keepalive] Starting Tobii Stream Engine Keepalive...")
    while True:
        api = ctypes.c_void_p()
        if dll.tobii_api_create(ctypes.byref(api), None, None) != 0:
            time.sleep(2)
            continue

        dev = ctypes.c_void_p()
        # Retry device connection
        connected = False
        for _ in range(10):
            if dll.tobii_device_create(api, b"tobii-prp://IS510-100211404854", 1, ctypes.byref(dev)) == 0:
                connected = True
                break
            time.sleep(1)

        if not connected:
            dll.tobii_api_destroy(api)
            time.sleep(2)
            continue

        r = dll.tobii_gaze_point_subscribe(dev, cb, None)
        print(f"[keepalive] Gaze stream active (status={r}). Hardware tracking running.")

        dev_ptr = ctypes.c_void_p(dev.value)
        consecutive_errors = 0
        while consecutive_errors < 10:
            res = dll.tobii_wait_for_callbacks(1, ctypes.byref(dev_ptr))
            if res == 0: # TOBII_ERROR_NO_ERROR
                dll.tobii_device_process_callbacks(dev)
                consecutive_errors = 0
            elif res == 6: # TOBII_ERROR_TIMED_OUT
                consecutive_errors = 0
            else:
                consecutive_errors += 1

        print("[keepalive] Connection lost or service restarted. Reconnecting...")
        try:
            dll.tobii_device_destroy(dev)
        except:
            pass
        try:
            dll.tobii_api_destroy(api)
        except:
            pass
        time.sleep(2)

if __name__ == "__main__":
    run()
