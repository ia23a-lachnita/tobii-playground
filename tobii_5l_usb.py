"""Tobii Eye Tracker 5L - Direct USB communication via WinUSB

This script communicates directly with the Tobii Eye Tracker 5L's EyeChip
interface using the WinUSB driver (which is already installed).

Based on the reverse-engineered protocol from the tobii_ffg project:
https://github.com/simonvc/tobii_ffg/blob/main/PROTOCOL.md
"""

import ctypes
from ctypes import wintypes, Structure, Union, POINTER, byref
import struct
import time
import sys
import threading
from dataclasses import dataclass
from typing import Optional, Callable

# ============================================================
# WinUSB API Definitions
# ============================================================

winusb = ctypes.windll.winusb
kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi

# Constants
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_IO_PENDING = 997
ERROR_SUCCESS = 0

# WinUSB structures
class WINUSB_INTERFACE_DESCRIPTOR(Structure):
    _fields_ = [
        ('bLength', ctypes.c_byte),
        ('bDescriptorType', ctypes.c_byte),
        ('bInterfaceNumber', ctypes.c_byte),
        ('bAlternateSetting', ctypes.c_byte),
        ('bNumEndpoints', ctypes.c_byte),
        ('bInterfaceClass', ctypes.c_byte),
        ('bInterfaceSubClass', ctypes.c_byte),
        ('bInterfaceProtocol', ctypes.c_byte),
        ('iInterface', ctypes.c_byte),
    ]

class WINUSB_PIPE_INFORMATION(Structure):
    _fields_ = [
        ('PipeFlags', wintypes.DWORD),
        ('PipeType', wintypes.DWORD),
        ('EndpointId', ctypes.c_byte),
        ('Interval', ctypes.c_byte),
        ('MaximumPacketSize', wintypes.USHORT),
    ]

class OVERLAPPED(Structure):
    _fields_ = [
        ('Internal', ctypes.POINTER(ctypes.c_ulong)),
        ('InternalHigh', ctypes.POINTER(ctypes.c_ulong)),
        ('Offset', wintypes.DWORD),
        ('OffsetHigh', wintypes.DWORD),
        ('hEvent', wintypes.HANDLE),
    ]

# ============================================================
# Tobii 5L Protocol Constants
# ============================================================

# USB Endpoints (from tobii_ffg protocol)
EP_BULK_IN = 0x83      # Device -> Host data
EP_BULK_OUT = 0x05     # Host -> Device commands
EP_BULK_OUT_2 = 0x04   # Additional OUT endpoint

# Transport framing types
TRANSPORT_TYPE_COMMAND = 1
TRANSPORT_TYPE_RESPONSE = 2

# TTP opcodes
TTP_CMD = 0x51         # Host command
TTP_RSP = 0x52         # Response
TTP_PUSH = 0x53        # Async data push

# Object IDs
OBJ_GAZE_POINT = 0x500
OBJ_EYE_POSITION = 0x501
OBJ_PUPIL_DIAMETER = 0x504
OBJ_USER_PRESENCE = 0x508
OBJ_HEAD_POSE = 0x50e
OBJ_USER_POSITION_GUIDE = 0x1770

# Gaze stream packet offsets (from tobii_ffg)
GAZE_PACKET_SIZE = 1724
GAZE_VALIDITY_OFFSET = 154
GAZE_X_OFFSET = 1411
GAZE_Y_OFFSET = 1424

# ============================================================
# Device Discovery
# ============================================================

def find_tobii_5l():
    """Find the Tobii Eye Tracker 5L using WinUSB device enumeration."""
    # Try to open the EyeChip device directly
    # The device path format for WinUSB on Windows
    device_paths = [
        r"\\?\usb#vid_2104&pid_0314#is510-100211405834#{a5dcbf10-6530-11d2-901f-00c04fb951ed}",  # Generic USB GUID
    ]
    
    # Also try to find via SetupDi
    GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
    
    # Parse the GUID
    guid_str = GUID_DEVINTERFACE_USB_DEVICE.strip('{}')
    parts = guid_str.split('-')
    guid_bytes = (
        int(parts[0], 16).to_bytes(4, 'little') +
        int(parts[1], 16).to_bytes(2, 'little') +
        int(parts[2], 16).to_bytes(2, 'little') +
        bytes.fromhex(parts[3]) +
        bytes.fromhex(parts[4])
    )
    
    class GUID(Structure):
        _fields_ = [
            ('Data1', wintypes.DWORD),
            ('Data2', wintypes.WORD),
            ('Data3', wintypes.WORD),
            ('Data4', ctypes.c_byte * 8),
        ]
    
    guid = GUID()
    guid.Data1 = int(parts[0], 16)
    guid.Data2 = int(parts[1], 16)
    guid.Data3 = int(parts[2], 16)
    guid.Data4 = (ctypes.c_byte * 8)(*bytes.fromhex(parts[3] + parts[4]))
    
    # Use SetupDiGetClassDevs to find devices
    DIGCF_PRESENT = 0x00000002
    DIGCF_DEVICEINTERFACE = 0x00000010
    
    dev_info = setupapi.SetupDiGetClassDevsW(
        byref(guid), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    
    if dev_info == INVALID_HANDLE_VALUE:
        print("Failed to get device info")
        return None
    
    class SP_DEVICE_INTERFACE_DATA(Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('InterfaceClassGuid', GUID),
            ('Flags', wintypes.DWORD),
            ('Reserved', ctypes.POINTER(ctypes.c_ulong)),
        ]
    
    interface_data = SP_DEVICE_INTERFACE_DATA()
    interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
    
    idx = 0
    while setupapi.SetupDiEnumDeviceInterfaces(dev_info, None, byref(guid), idx, byref(interface_data)):
        # Get required size
        required_size = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, byref(interface_data), None, 0,
            byref(required_size), None
        )
        
        # Allocate buffer for detail data
        class SP_DEVICE_INTERFACE_DETAIL_DATA_W(Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('DevicePath', ctypes.c_wchar * (required_size.value // 2 if required_size.value > 4 else 256)),
            ]
        
        detail_data = SP_DEVICE_INTERFACE_DETAIL_DATA_W()
        detail_data.cbSize = 8  # sizeof(DWORD) for 64-bit
        
        if setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, byref(interface_data), byref(detail_data),
            required_size, byref(required_size), None
        ):
            path = detail_data.DevicePath
            if 'vid_2104' in path.lower() and 'pid_0314' in path.lower():
                print(f"Found Tobii 5L device: {path}")
                setupapi.SetupDiDestroyDeviceInfoList(dev_info)
                return path
        
        idx += 1
    
    setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return None


# ============================================================
# WinUSB Communication
# ============================================================

class Tobii5LUSB:
    """Direct USB communication with Tobii Eye Tracker 5L EyeChip."""
    
    def __init__(self):
        self.handle = INVALID_HANDLE_VALUE
        self.winusb_handle = None
        self.interface_handle = None
        self.seq = 0
        self.gaze_callback: Optional[Callable] = None
        self.running = False
        
    def open(self, device_path: str) -> bool:
        """Open the device and initialize WinUSB."""
        # Open the device file
        self.handle = kernel32.CreateFileW(
            device_path,
            0xC0000000,  # GENERIC_READ | GENERIC_WRITE
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            None
        )
        
        if self.handle == INVALID_HANDLE_VALUE:
            error = kernel32.GetLastError()
            print(f"Failed to open device: error {error}")
            return False
        
        # Initialize WinUSB
        self.winusb_handle = ctypes.c_void_p()
        if not winusb.WinUsb_Initialize(self.handle, byref(self.winusb_handle)):
            error = kernel32.GetLastError()
            print(f"Failed to initialize WinUSB: error {error}")
            kernel32.CloseHandle(self.handle)
            self.handle = INVALID_HANDLE_VALUE
            return False
        
        print(f"WinUSB initialized: {self.winusb_handle}")
        
        # Get interface descriptor for interface 0 (EyeChip)
        descriptor = WINUSB_INTERFACE_DESCRIPTOR()
        if not winusb.WinUsb_GetInterfaceDescriptor(
            self.winusb_handle, 0, byref(descriptor)
        ):
            print("Failed to get interface descriptor")
            self.close()
            return False
        
        print(f"Interface 0: {descriptor.bNumEndpoints} endpoints, "
              f"Class={descriptor.bInterfaceClass}, "
              f"SubClass={descriptor.bInterfaceSubClass}")
        
        # Get pipe information
        for i in range(descriptor.bNumEndpoints):
            pipe_info = WINUSB_PIPE_INFORMATION()
            if winusb.WinUsb_GetPipeInformation(
                self.winusb_handle, 0, i, byref(pipe_info)
            ):
                ep_addr = pipe_info.EndpointId
                max_size = pipe_info.MaximumPacketSize
                print(f"  Endpoint 0x{ep_addr:02x}: MaxPacket={max_size}, "
                      f"Type={pipe_info.PipeType}")
        
        return True
    
    def close(self):
        """Close the device."""
        self.running = False
        if self.winusb_handle:
            winusb.WinUsb_Free(self.winusb_handle)
            self.winusb_handle = None
        if self.handle != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(self.handle)
            self.handle = INVALID_HANDLE_VALUE
    
    def _build_ttp_payload(self, opcode: int, seq: int, status: int, 
                           object_id: int, data: bytes = b'') -> bytes:
        """Build a TTP (Tobii Transfer Protocol) payload."""
        header = struct.pack('>IIII', opcode, seq, status, object_id)
        return header + data
    
    def _build_transport_frame(self, frame_type: int, payload: bytes) -> bytes:
        """Build a transport frame with header and payload."""
        header = struct.pack('<II', frame_type, len(payload))
        return header + payload
    
    def send_command(self, opcode: int, status: int, object_id: int, 
                     data: bytes = b'') -> bool:
        """Send a command to the device."""
        payload = self._build_ttp_payload(opcode, self.seq, status, object_id, data)
        frame = self._build_transport_frame(TRANSPORT_TYPE_COMMAND, payload)
        
        bytes_written = wintypes.DWORD()
        overlapped = OVERLAPPED()
        
        result = winusb.WinUsb_WritePipe(
            self.winusb_handle,
            EP_BULK_OUT,
            frame,
            len(frame),
            byref(bytes_written),
            byref(overlapped)
        )
        
        if not result:
            error = kernel32.GetLastError()
            if error == ERROR_IO_PENDING:
                # Wait for completion
                kernel32.WaitForSingleObject(overlapped.hEvent, 5000)
                winusb.WinUsb_GetOverlappedResult(
                    self.winusb_handle, byref(overlapped), byref(bytes_written), False
                )
            else:
                print(f"Write failed: error {error}")
                return False
        
        self.seq += 1
        return True
    
    def read_data(self, timeout_ms: int = 1000) -> Optional[bytes]:
        """Read data from the device."""
        buffer = ctypes.create_string_buffer(4096)
        bytes_read = wintypes.DWORD()
        overlapped = OVERLAPPED()
        
        result = winusb.WinUsb_ReadPipe(
            self.winusb_handle,
            EP_BULK_IN,
            buffer,
            len(buffer),
            byref(bytes_read),
            byref(overlapped)
        )
        
        if not result:
            error = kernel32.GetLastError()
            if error == ERROR_IO_PENDING:
                # Wait for completion
                kernel32.WaitForSingleObject(overlapped.hEvent, timeout_ms)
                success = winusb.WinUsb_GetOverlappedResult(
                    self.winusb_handle, byref(overlapped), byref(bytes_read), False
                )
                if not success:
                    return None
            else:
                return None
        
        return buffer.raw[:bytes_read.value]
    
    def init_device(self) -> bool:
        """Send initialization sequence to start gaze streaming."""
        print("Sending initialization commands...")
        
        # Send init commands based on tobii_ffg protocol
        # These commands configure the device and subscribe to gaze streams
        
        # Command 1: Subscribe to user presence (0x508)
        if not self.send_command(TTP_CMD, 0, OBJ_USER_PRESENCE):
            print("Failed to subscribe to user presence")
            return False
        
        # Command 2: Subscribe to gaze point (0x500)
        if not self.send_command(TTP_CMD, 0, OBJ_GAZE_POINT):
            print("Failed to subscribe to gaze point")
            return False
        
        # Command 3: Subscribe to eye position (0x501)
        if not self.send_command(TTP_CMD, 0, OBJ_EYE_POSITION):
            print("Failed to subscribe to eye position")
            return False
        
        # Command 4: Subscribe to user position guide (0x1770)
        if not self.send_command(TTP_CMD, 0, OBJ_USER_POSITION_GUIDE):
            print("Failed to subscribe to user position guide")
            return False
        
        # Wait for responses
        time.sleep(0.5)
        
        # Read any response data
        for _ in range(10):
            data = self.read_data(timeout_ms=100)
            if data:
                print(f"Received {len(data)} bytes during init")
                self._parse_response(data)
        
        print("Initialization complete")
        return True
    
    def _parse_response(self, data: bytes):
        """Parse a response from the device."""
        if len(data) < 8:
            return
        
        # Parse transport frame header
        frame_type, payload_len = struct.unpack('<II', data[:8])
        
        if payload_len + 8 > len(data):
            payload_len = len(data) - 8
        
        payload = data[8:8 + payload_len]
        
        if len(payload) < 16:
            return
        
        # Parse TTP header
        opcode, seq, status, object_id = struct.unpack('>IIII', payload[:16])
        
        print(f"  Response: opcode=0x{opcode:02x} seq={seq} status=0x{status:08x} "
              f"obj=0x{object_id:04x}")
    
    def _parse_gaze_packet(self, data: bytes) -> Optional[dict]:
        """Parse a gaze stream packet."""
        if len(data) < GAZE_PACKET_SIZE:
            return None
        
        # Check validity
        validity = data[GAZE_VALIDITY_OFFSET]
        if validity == 0:
            return None  # Invalid gaze
        
        # Extract gaze coordinates (big-endian int16)
        gaze_x = struct.unpack('>h', data[GAZE_X_OFFSET:GAZE_X_OFFSET + 2])[0]
        gaze_y = struct.unpack('>h', data[GAZE_Y_OFFSET:GAZE_Y_OFFSET + 2])[0]
        
        # Normalize (divide by ~1000)
        norm_x = gaze_x / 1044.0 + 0.014
        norm_y = gaze_y / 1030.0 + 0.006
        
        return {
            'valid': True,
            'raw_x': gaze_x,
            'raw_y': gaze_y,
            'norm_x': norm_x,
            'norm_y': norm_y,
        }
    
    def start_streaming(self):
        """Start reading gaze data from the device."""
        self.running = True
        print("Starting gaze stream...")
        print("Press Ctrl+C to stop")
        
        while self.running:
            data = self.read_data(timeout_ms=100)
            if data:
                # Check if this is a gaze packet
                if len(data) >= GAZE_PACKET_SIZE:
                    # Parse transport frame
                    if len(data) >= 8:
                        frame_type, payload_len = struct.unpack('<II', data[:8])
                        
                        if frame_type == TRANSPORT_TYPE_COMMAND and payload_len + 8 >= len(data):
                            payload = data[8:]
                            if len(payload) >= 16:
                                opcode, seq, status, obj_id = struct.unpack('>IIII', payload[:16])
                                
                                if opcode == TTP_PUSH and obj_id == OBJ_GAZE_POINT:
                                    gaze = self._parse_gaze_packet(payload)
                                    if gaze and self.gaze_callback:
                                        self.gaze_callback(gaze)
                                    elif gaze:
                                        print(f"\rGaze: x={gaze['norm_x']:.3f} y={gaze['norm_y']:.3f} "
                                              f"(raw: {gaze['raw_x']}, {gaze['raw_y']})", end='', flush=True)
                                else:
                                    # Other async data
                                    pass
                
                # Also check for raw gaze data at known offsets
                if len(data) >= GAZE_PACKET_SIZE:
                    validity = data[GAZE_VALIDITY_OFFSET]
                    if validity != 0:
                        gaze_x = struct.unpack('>h', data[GAZE_X_OFFSET:GAZE_X_OFFSET + 2])[0]
                        gaze_y = struct.unpack('>h', data[GAZE_Y_OFFSET:GAZE_Y_OFFSET + 2])[0]
                        norm_x = gaze_x / 1044.0 + 0.014
                        norm_y = gaze_y / 1030.0 + 0.006
                        print(f"\rGaze: x={norm_x:.3f} y={norm_y:.3f} "
                              f"(raw: {gaze_x}, {gaze_y})", end='', flush=True)
            else:
                time.sleep(0.01)
        
        print("\nStream stopped")


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("Tobii Eye Tracker 5L - Direct USB Communication")
    print("=" * 60)
    
    # Find the device
    device_path = find_tobii_5l()
    if not device_path:
        print("\nTobii Eye Tracker 5L not found!")
        print("Make sure the device is connected.")
        return 1
    
    # Create USB interface
    tobii = Tobii5LUSB()
    
    # Open the device
    if not tobii.open(device_path):
        print("\nFailed to open device")
        return 1
    
    print("\nDevice opened successfully!")
    
    # Initialize the device
    if not tobii.init_device():
        print("\nFailed to initialize device")
        tobii.close()
        return 1
    
    # Start streaming
    try:
        tobii.start_streaming()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        tobii.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
