"""Tobii Eye Tracker 5L - Stream Engine Python Interface
Works with tobii_stream_engine.dll (x64) after Platform Runtime is installed.
"""

import ctypes
from ctypes import (
    c_void_p, c_char_p, c_int, c_uint, c_float, c_double,
    Structure, Union, POINTER, CFUNCTYPE, byref, sizeof
)
import time
import sys

DLL_PATH = r"C:\Users\xursc\AppData\Local\TobiiGhost\app-1.14.1\x64\tobii_stream_engine.dll"

class TobiiGazePoint(Structure):
    _fields_ = [
        ("timestamp", c_double),
        ("validity", c_int),
        ("position_x", c_float),
        ("position_y", c_float),
    ]

class TobiiGazeOrigin(Structure):
    _fields_ = [
        ("timestamp", c_double),
        ("validity_left", c_int),
        ("validity_right", c_int),
        ("position_left_x", c_float),
        ("position_left_y", c_float),
        ("position_left_z", c_float),
        ("position_right_x", c_float),
        ("position_right_y", c_float),
        ("position_right_z", c_float),
    ]

class TobiiEyePositionNormalized(Structure):
    _fields_ = [
        ("timestamp", c_double),
        ("validity_left", c_int),
        ("validity_right", c_int),
        ("position_left_x", c_float),
        ("position_left_y", c_float),
        ("position_left_z", c_float),
        ("position_right_x", c_float),
        ("position_right_y", c_float),
        ("position_right_z", c_float),
    ]

class TobiiHeadPose(Structure):
    _fields_ = [
        ("timestamp", c_double),
        ("validity", c_int),
        ("position_x", c_float),
        ("position_y", c_float),
        ("position_z", c_float),
        ("rotation_x", c_float),
        ("rotation_y", c_float),
        ("rotation_z", c_float),
    ]

# Callback types
GAZE_POINT_CALLBACK = CFUNCTYPE(None, c_int, c_void_p, POINTER(TobiiGazePoint))
GAZE_ORIGIN_CALLBACK = CFUNCTYPE(None, c_int, c_void_p, POINTER(TobiiGazeOrigin))
EYE_POSITION_CALLBACK = CFUNCTYPE(None, c_int, c_void_p, POINTER(TobiiEyePositionNormalized))
HEAD_POSE_CALLBACK = CFUNCTYPE(None, c_int, c_void_p, POINTER(TobiiHeadPose))
ENUM_CALLBACK = CFUNCTYPE(None, c_char_p, c_void_p)


class TobiiTracker:
    def __init__(self, dll_path=DLL_PATH):
        self.dll = ctypes.CDLL(dll_path)
        self.api = c_void_p()
        self.device = c_void_p()
        self._callbacks = []
        self._setup_api()
    
    def _setup_api(self):
        dll = self.dll
        
        dll.tobii_api_create.argtypes = [c_void_p, c_void_p, c_void_p]
        dll.tobii_api_create.restype = c_int
        
        dll.tobii_api_destroy.argtypes = [c_void_p]
        dll.tobii_api_destroy.restype = None
        
        dll.tobii_enumerate_local_device_urls.argtypes = [c_void_p, c_void_p, c_void_p]
        dll.tobii_enumerate_local_device_urls.restype = c_int
        
        dll.tobii_enumerate_local_device_urls_ex.argtypes = [POINTER(ENUM_CALLBACK), c_void_p]
        dll.tobii_enumerate_local_device_urls_ex.restype = c_int
        
        dll.tobii_device_create.argtypes = [c_void_p, c_char_p, c_void_p]
        dll.tobii_device_create.restype = c_int
        
        dll.tobii_device_destroy.argtypes = [c_void_p]
        dll.tobii_device_destroy.restype = c_int
        
        dll.tobii_gaze_point_subscribe.argtypes = [c_void_p, c_int, POINTER(GAZE_POINT_CALLBACK), c_void_p]
        dll.tobii_gaze_point_subscribe.restype = c_int
        
        dll.tobii_gaze_point_unsubscribe.argtypes = [c_void_p]
        dll.tobii_gaze_point_unsubscribe.restype = c_int
        
        dll.tobii_gaze_origin_subscribe.argtypes = [c_void_p, c_int, POINTER(GAZE_ORIGIN_CALLBACK), c_void_p]
        dll.tobii_gaze_origin_subscribe.restype = c_int
        
        dll.tobii_gaze_origin_unsubscribe.argtypes = [c_void_p]
        dll.tobii_gaze_origin_unsubscribe.restype = c_int
        
        dll.tobii_eye_position_normalized_subscribe.argtypes = [c_void_p, c_int, POINTER(EYE_POSITION_CALLBACK), c_void_p]
        dll.tobii_eye_position_normalized_subscribe.restype = c_int
        
        dll.tobii_eye_position_normalized_unsubscribe.argtypes = [c_void_p]
        dll.tobii_eye_position_normalized_unsubscribe.restype = c_int
        
        dll.tobii_head_pose_subscribe.argtypes = [c_void_p, c_int, POINTER(HEAD_POSE_CALLBACK), c_void_p]
        dll.tobii_head_pose_subscribe.restype = c_int
        
        dll.tobii_head_pose_unsubscribe.argtypes = [c_void_p]
        dll.tobii_head_pose_unsubscribe.restype = c_int
        
        dll.tobii_wait_for_callbacks.argtypes = [c_void_p]
        dll.tobii_wait_for_callbacks.restype = c_int
        
        dll.tobii_error_message.argtypes = [c_int]
        dll.tobii_error_message.restype = c_char_p
    
    def create(self):
        result = self.dll.tobii_api_create(byref(self.api), None, None)
        print(f"API create: {result}")
        return result
    
    def enumerate_devices(self):
        buf = ctypes.create_string_buffer(8192)
        sz = c_uint(8192)
        result = self.dll.tobii_enumerate_local_device_urls(self.api, buf, byref(sz))
        if sz.value > 0:
            raw = buf.value.decode('utf-8', errors='replace')
            urls = [u for u in raw.split('\x00') if u.strip()]
            for u in urls:
                print(f"  Found device: {u}")
            return urls
        return []
    
    def create_device(self, url):
        url_bytes = url.encode() if isinstance(url, str) else url
        result = self.dll.tobii_device_create(self.api, url_bytes, byref(self.device))
        print(f"Device create ({url}): {result}")
        return result
    
    def subscribe_gaze_point(self, callback):
        cb = GAZE_POINT_CALLBACK(callback)
        self._callbacks.append(cb)
        result = self.dll.tobii_gaze_point_subscribe(self.device, 0, byref(cb), None)
        return result
    
    def subscribe_gaze_origin(self, callback):
        cb = GAZE_ORIGIN_CALLBACK(callback)
        self._callbacks.append(cb)
        result = self.dll.tobii_gaze_origin_subscribe(self.device, 0, byref(cb), None)
        return result
    
    def subscribe_eye_position(self, callback):
        cb = EYE_POSITION_CALLBACK(callback)
        self._callbacks.append(cb)
        result = self.dll.tobii_eye_position_normalized_subscribe(self.device, 0, byref(cb), None)
        return result
    
    def subscribe_head_pose(self, callback):
        cb = HEAD_POSE_CALLBACK(callback)
        self._callbacks.append(cb)
        result = self.dll.tobii_head_pose_subscribe(self.device, 0, byref(cb), None)
        return result
    
    def wait_for_frame(self, timeout_ms=16):
        timeout = ctypes.c_uint(timeout_ms)
        result = self.dll.tobii_wait_for_callbacks(self.device)
        return result
    
    def unsubscribe_all(self):
        try:
            self.dll.tobii_gaze_point_unsubscribe(self.device)
        except:
            pass
        try:
            self.dll.tobii_gaze_origin_unsubscribe(self.device)
        except:
            pass
        try:
            self.dll.tobii_eye_position_normalized_unsubscribe(self.device)
        except:
            pass
        try:
            self.dll.tobii_head_pose_unsubscribe(self.device)
        except:
            pass
    
    def destroy(self):
        self.unsubscribe_all()
        self.dll.tobii_device_destroy(self.device)
        self.dll.tobii_api_destroy(self.api)


def main():
    print("Tobii Eye Tracker 5L - Stream Engine")
    print("=" * 50)
    
    tracker = TobiiTracker()
    
    result = tracker.create()
    if result != 0:
        print(f"Failed to create API: {result}")
        return
    
    print("\nEnumerating devices...")
    urls = tracker.enumerate_devices()
    
    if not urls:
        print("No devices found!")
        print("Make sure the Platform Runtime service is installed and running.")
        print("Run install_tobii_runtime.bat as Administrator.")
        tracker.destroy()
        return
    
    url = urls[0]
    print(f"\nConnecting to: {url}")
    result = tracker.create_device(url)
    if result != 0:
        print(f"Failed to create device: {result}")
        tracker.destroy()
        return
    
    # Subscribe to all streams
    print("\nSubscribing to data streams...")
    
    gaze_count = [0]
    
    def on_gaze_point(status, user_data, data):
        gaze_count[0] += 1
        if data.contents.validity == 0:  # TOBII_VALIDITY_VALID
            print(f"  Gaze: x={data.contents.position_x:.4f} y={data.contents.position_y:.4f} t={data.contents.timestamp:.3f}")
    
    def on_gaze_origin(status, user_data, data):
        if data.contents.validity_left == 0:
            print(f"  Left eye origin:  ({data.contents.position_left_x:.1f}, {data.contents.position_left_y:.1f}, {data.contents.position_left_z:.1f})")
        if data.contents.validity_right == 0:
            print(f"  Right eye origin: ({data.contents.position_right_x:.1f}, {data.contents.position_right_y:.1f}, {data.contents.position_right_z:.1f})")
    
    def on_head_pose(status, user_data, data):
        if data.contents.validity == 0:
            print(f"  Head: pos=({data.contents.position_x:.1f}, {data.contents.position_y:.1f}, {data.contents.position_z:.1f}) rot=({data.contents.rotation_x:.1f}, {data.contents.rotation_y:.1f}, {data.contents.rotation_z:.1f})")
    
    result = tracker.subscribe_gaze_point(on_gaze_point)
    print(f"  Gaze point subscribe: {result}")
    
    result = tracker.subscribe_gaze_origin(on_gaze_origin)
    print(f"  Gaze origin subscribe: {result}")
    
    result = tracker.subscribe_head_pose(on_head_pose)
    print(f"  Head pose subscribe: {result}")
    
    # Wait for data
    print("\nReading eye tracking data (Ctrl+C to stop)...")
    print("-" * 50)
    
    frame_count = 0
    try:
        while True:
            result = tracker.wait_for_frame(1000)
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"  [Frame {frame_count}, {gaze_count[0]} gaze points received]")
    except KeyboardInterrupt:
        print(f"\n\nStopped. Total frames: {frame_count}, gaze points: {gaze_count[0]}")
    finally:
        tracker.destroy()


if __name__ == "__main__":
    main()
