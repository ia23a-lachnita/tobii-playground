using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace TobiiGazeVisualizer;

/// <summary>
/// Direct USB communication with Tobii Eye Tracker 5L using WinUSB.
/// Implements the TTP/TLV binary protocol for gaze streaming.
/// </summary>
public class TobiiUsb : IDisposable
{
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr SetupDiGetClassDevs(ref Guid ClassGuid, IntPtr Enumerator, IntPtr hwndParent, int Flags);
    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiEnumDeviceInterfaces(IntPtr DeviceInfoSet, IntPtr DeviceInfoData,
        ref Guid InterfaceClassGuid, int MemberIndex, ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr DeviceInfoSet,
        ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData, IntPtr DeviceInterfaceDetailData,
        int DeviceInterfaceDetailDataSize, ref int RequiredSize, IntPtr DeviceInfoData);
    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiDestroyDeviceInfoList(IntPtr DeviceInfoSet);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_Initialize(IntPtr DeviceHandle, out IntPtr InterfaceHandle);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_ControlTransfer(IntPtr InterfaceHandle, WINUSB_SETUP_PACKET SetupPacket,
        byte[] Buffer, uint BufferLength, out uint LengthTransferred, IntPtr Overlapped);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_WritePipe(IntPtr InterfaceHandle, byte PipeID,
        byte[] Buffer, uint BufferLength, out uint LengthTransferred, IntPtr Overlapped);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_ReadPipe(IntPtr InterfaceHandle, byte PipeID,
        byte[] Buffer, uint BufferLength, out uint LengthTransferred, IntPtr Overlapped);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_Free(IntPtr InterfaceHandle);
    [DllImport("winusb.dll", SetLastError = true)]
    static extern bool WinUsb_SetPipePolicy(IntPtr InterfaceHandle, byte PipeID, uint PolicyType,
        uint PolicyLength, ref uint Policy);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr CreateFile(string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition, uint dwFlagsAndAttributes, IntPtr hTemplateFile);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr hObject);

    const uint PIPE_TRANSFER_TIMEOUT = 0x03;

    [StructLayout(LayoutKind.Sequential)]
    struct SP_DEVICE_INTERFACE_DATA { public int cbSize; public Guid InterfaceClassGuid; public int Flags; public IntPtr Reserved; }
    [StructLayout(LayoutKind.Sequential)]
    struct WINUSB_SETUP_PACKET { public byte RequestType; public byte Request; public ushort Value; public ushort Index; public ushort Length; }

    static Guid WINUSB_GUID = new("85C0F97C-E2B1-422A-92A9-5F96072E79D8");
    static double Q42_SCALE = 4398046511104.0; // 2^42

    IntPtr _devHandle, _usbHandle;
    byte _outEp = 0x05, _inEp = 0x83;
    uint _seq;
    bool _disposed;

    public bool IsConnected => _usbHandle != IntPtr.Zero && _usbHandle != new IntPtr(-1);
    public bool IsTracking { get; private set; }

    /// <summary>Fired when a gaze sample is received. Normalized [0,1] coordinates.</summary>
    public event Action<double, double, bool, bool>? OnGaze;

    /// <summary>Fired when connection status changes.</summary>
    public event Action<bool>? OnConnectionChanged;

    Thread? _readThread;
    CancellationTokenSource? _cts;

    // Display area: full physical screen dimensions
    // Tracker is tilted upward ~20° when mounted on bottom bezel
    const double MONITOR_W_MM = 597.9;
    const double MONITOR_H_MM = 336.2;
    const double MONITOR_Y_BOTTOM_MM = 15.0;
    const double MONITOR_Z_BOTTOM_MM = -10.0;
    const double MONITOR_X_SHIFT_MM = 0.0;
    const double TRACKER_TILT_DEG = 20.0;

    public bool Connect()
    {
        var devInfo = SetupDiGetClassDevs(ref WINUSB_GUID, IntPtr.Zero, IntPtr.Zero, 0x12);
        if (devInfo == IntPtr.Zero || devInfo == new IntPtr(-1)) return false;

        string? devicePath = null;
        for (int i = 0; ; i++)
        {
            var ifData = new SP_DEVICE_INTERFACE_DATA();
            ifData.cbSize = Marshal.SizeOf(ifData);
            if (!SetupDiEnumDeviceInterfaces(devInfo, IntPtr.Zero, ref WINUSB_GUID, i, ref ifData)) break;
            int required = 0;
            SetupDiGetDeviceInterfaceDetail(devInfo, ref ifData, IntPtr.Zero, 0, ref required, IntPtr.Zero);
            IntPtr detailBuf = Marshal.AllocHGlobal(required);
            Marshal.WriteInt32(detailBuf, 8);
            if (SetupDiGetDeviceInterfaceDetail(devInfo, ref ifData, detailBuf, required, ref required, IntPtr.Zero))
            {
                // Take the first enumerated WinUSB device; previously the loop
                // kept overwriting devicePath and connected to the LAST match.
                devicePath ??= Marshal.PtrToStringAuto(detailBuf + 4);
            }
            Marshal.FreeHGlobal(detailBuf);
            if (devicePath != null) break;
        }
        SetupDiDestroyDeviceInfoList(devInfo);
        if (devicePath == null) return false;

        _devHandle = CreateFile(devicePath, 0xC0000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        if (_devHandle == new IntPtr(-1)) return false;
        if (!WinUsb_Initialize(_devHandle, out _usbHandle))
        {
            CloseHandle(_devHandle);
            return false;
        }

        // Set read timeout to prevent blocking on short packets
        uint timeout = 100; // 100ms
        WinUsb_SetPipePolicy(_usbHandle, _inEp, PIPE_TRANSFER_TIMEOUT, sizeof(uint), ref timeout);

        // Session Open
        var setup = new WINUSB_SETUP_PACKET { RequestType = 0x41, Request = 0x41 };
        WinUsb_ControlTransfer(_usbHandle, setup, Array.Empty<byte>(), 0, out _, IntPtr.Zero);

        // HELLO
        SendRequest(0x3E8, new byte[] {
            0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x09,
            0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
            0x02, 0x00, 0x01, 0x00, 0x03, 0x00, 0x01, 0x00, 0x04, 0x00, 0x01,
            0x00, 0x05, 0x00, 0x01, 0x00, 0x06, 0x00, 0x01, 0x00, 0x07, 0x00,
            0x01, 0x00, 0x08 });
        ReadResponse();

        // QUERY_REALM
        SendRequest(0x640, new byte[] { 0x00, 0x00 });
        ReadResponse();

        // SET display area - account for tracker tilt angle
        double leftEdge = -MONITOR_W_MM / 2 + MONITOR_X_SHIFT_MM;
        SetDisplayArea(MONITOR_W_MM, MONITOR_H_MM, leftEdge, MONITOR_Y_BOTTOM_MM, MONITOR_Z_BOTTOM_MM, TRACKER_TILT_DEG);

        // GET display area (confirm)
        SendRequest(0x596, Array.Empty<byte>());
        var getResponse = ReadResponse();
        System.IO.File.WriteAllBytes(System.IO.Path.Combine(AppContext.BaseDirectory, "get_display_area_response.bin"), getResponse);

        // SUBSCRIBE gaze_point (0x0500)
        SendSubscribe(0x0500);
        ReadResponse();

        OnConnectionChanged?.Invoke(true);
        return true;
    }

    public void StartTracking()
    {
        if (_readThread != null) return;
        _cts = new CancellationTokenSource();
        _readThread = new Thread(ReadLoop) { IsBackground = true };
        _readThread.Start(_cts.Token);
    }

    public void StopTracking()
    {
        _cts?.Cancel();
        _readThread?.Join(1000);
        _readThread = null;
    }

    void ReadLoop(object? tokenObj)
    {
        var ct = (CancellationToken)tokenObj!;
        byte[] buf = new byte[16384];
        int consecErrors = 0;

        while (!ct.IsCancellationRequested)
        {
            if (!WinUsb_ReadPipe(_usbHandle, _inEp, buf, (uint)buf.Length, out uint xferBytes, IntPtr.Zero))
            {
                int err = Marshal.GetLastWin32Error();
                // 997 = ERROR_IO_PENDING, 121 = ERROR_SEM_TIMEOUT (no data within
                // the 100 ms pipe timeout — happens whenever the user is out of
                // range, blinks long, or looks away). Both are TRANSIENT.
                // The old code did `break` on anything but 997, so the first
                // idle moment killed the thread permanently: all numbers froze
                // at their last values and calibration collected zero samples.
                if (err == 997 || err == 121)
                {
                    consecErrors = 0;
                    IsTracking = false;
                    continue;
                }
                if (++consecErrors < 200)
                {
                    Thread.Sleep(25);
                    continue;
                }
                // Sustained failure (e.g. device unplugged): idle-poll slowly
                // until cancelled. Never `break` — StartTracking refuses to
                // start a second thread while _readThread != null, so exiting
                // here would brick the stream until app restart.
                IsTracking = false;
                consecErrors = 0;
                Thread.Sleep(500);
                continue;
            }
            consecErrors = 0;
            if (xferBytes < 32) continue;

            uint magic = ReadU32BE(buf, 8);
            uint op = ReadU32BE(buf, 20);
            uint plen = ReadU32BE(buf, 28);

            if (magic == 0x53 && op == 0x500 && plen > 0)
                ParseGaze(buf, 32, Math.Min((int)plen, (int)(xferBytes - 32)));
        }
    }

    void ParseGaze(byte[] buf, int start, int len)
    {
        int pos = start;
        int end = start + len;
        if (pos + 2 > end) return;
        pos += 2;

        if (pos + 9 > end || buf[pos] != 0x05) return;
        pos += 5;
        uint rowTag = ReadU32BE(buf, pos); pos += 4;
        int colCount = (int)((rowTag >> 16) & 0xFFF);

        double gazeX = -1, gazeY = -1;
        uint validL = 4, validR = 4;

        for (int i = 0; i < colCount && pos + 18 <= end; i++)
        {
            if (buf[pos] != 0x05) break;
            pos += 5;
            uint colTag = ReadU32BE(buf, pos); pos += 4;
            if (colTag != 0x020BB9) break;
            if (buf[pos] != 0x02 || pos + 9 > end) break;
            pos += 5;
            uint colId = ReadU32BE(buf, pos); pos += 4;

            if (pos + 1 > end) break;
            byte vType = buf[pos];
            switch (vType)
            {
                case 2: // u32
                    if (pos + 9 > end) goto done;
                    pos += 5;
                    uint uVal = ReadU32BE(buf, pos); pos += 4;
                    if (colId == 0x07) validL = uVal;
                    else if (colId == 0x0d) validR = uVal;
                    break;
                case 3: // fixed16x16
                    pos += 5; pos += 4;
                    break;
                case 4: // Q42
                    pos += 5; pos += 8;
                    break;
                case 5: // prolog (struct)
                    if (pos + 9 > end) goto done;
                    pos += 5;
                    uint structTag = ReadU32BE(buf, pos); pos += 4;
                    if (structTag == 0x021F40) // point2d
                    {
                        if (pos + 26 > end) goto done;
                        pos += 5;
                        double px = ReadQ42Signed(buf, pos); pos += 8;
                        pos += 5;
                        double py = ReadQ42Signed(buf, pos); pos += 8;
                        if (colId == 0x1c) { gazeX = px; gazeY = py; } // combined binocular 2D
                    }
                    else if (structTag == 0x031F41) // point3d
                    {
                        pos += 5; pos += 8;
                        pos += 5; pos += 8;
                        pos += 5; pos += 8;
                    }
                    else goto done;
                    break;
                case 6: // s64
                    pos += 5; pos += 8;
                    break;
                default: goto done;
            }
        }
        done:

        bool isValid = validL == 0 || validR == 0;
        if (gazeX >= 0 && gazeY >= 0)
        {
            IsTracking = isValid;
            OnGaze?.Invoke(gazeX, gazeY, validL == 0, validR == 0);
        }
    }

    void SetDisplayArea(double w, double h, double ox, double oy, double z, double tiltDeg = 0)
    {
        byte[] payload = new byte[220]; // extra space for transformed points
        int n = 0;
        payload[n++] = 0x00; payload[n++] = 0x00;

        // Rect+tilt -> corners, pivoting about the bottom-left corner.
        // tl = bl + h*(cos tilt, sin tilt); tr = tl + (w, 0, 0).
        // Positive tilt = screen top leaning away from the tracker, matching
        // tobiifree driver/src/tracker.zig setDisplayArea and the Tobii_Linux
        // reference case (600x335mm screen, 15 deg tilt:
        // BL=(-300,10,0) -> TL=(-300,333.585,86.704), i.e. top Z POSITIVE).
        // The previous revision rotated about the tracker origin with a
        // flipped Z sign (TL z=-129.5 instead of ~+105 for this monitor),
        // defining a wrong plane that the software calibration then had to
        // absorb. The device echoes whatever plane it is given (verified via
        // get_display_area_response.bin), so a correct plane matters for
        // linearity at the screen edges.
        double rad = tiltDeg * Math.PI / 180.0;
        double cosT = Math.Cos(rad);
        double sinT = Math.Sin(rad);

        double blX = ox;
        double blY = oy;
        double blZ = z;
        double tlX = blX;
        double tlY = blY + h * cosT;
        double tlZ = blZ + h * sinT;
        double trX = blX + w;
        double trY = tlY;
        double trZ = tlZ;

        n += WritePoint3D(payload, n, tlX, tlY, tlZ);   // TL
        n += WritePoint3D(payload, n, trX, trY, trZ);   // TR
        n += WritePoint3D(payload, n, blX, blY, blZ);   // BL

        // End marker tag
        payload[n++] = 0x05;
        payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x04;
        WriteU32BE(payload, n, 0x010100); n += 4;
        payload[n++] = 0x02;
        payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x04;
        WriteU32BE(payload, n, 0x3039); n += 4;

        byte[] trimmed = new byte[n];
        Array.Copy(payload, trimmed, n);

        // Debug: write payload next to the binaries (gitignored *.bin)
        System.IO.File.WriteAllBytes(System.IO.Path.Combine(AppContext.BaseDirectory, "display_area_payload.bin"), trimmed);

        SendRequest(0x5A0, trimmed);
        var response = ReadResponse();

        // Debug: write response next to the binaries (gitignored *.bin)
        System.IO.File.WriteAllBytes(System.IO.Path.Combine(AppContext.BaseDirectory, "display_area_response.bin"), response);
    }

    int WritePoint3D(byte[] buf, int offset, double x, double y, double z)
    {
        int n = offset;
        buf[n++] = 0x05;
        buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x04;
        WriteU32BE(buf, n, 0x031F41); n += 4;
        n += WriteQ42(buf, n, x);
        n += WriteQ42(buf, n, y);
        n += WriteQ42(buf, n, z);
        return n - offset;
    }

    int WriteQ42(byte[] buf, int offset, double value)
    {
        int n = offset;
        buf[n++] = 0x04;
        buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x08;
        long scaled = (long)Math.Round(value * Q42_SCALE);
        buf[n++] = (byte)(scaled >> 56); buf[n++] = (byte)(scaled >> 48);
        buf[n++] = (byte)(scaled >> 40); buf[n++] = (byte)(scaled >> 32);
        buf[n++] = (byte)(scaled >> 24); buf[n++] = (byte)(scaled >> 16);
        buf[n++] = (byte)(scaled >> 8); buf[n++] = (byte)scaled;
        return n - offset;
    }

    void SendSubscribe(uint streamId)
    {
        byte[] payload = new byte[20];
        payload[0] = 0x00; payload[1] = 0x00;
        payload[2] = 0x02; payload[3] = 0x00; payload[4] = 0x00; payload[5] = 0x00; payload[6] = 0x04;
        payload[7] = (byte)(streamId >> 24); payload[8] = (byte)(streamId >> 16);
        payload[9] = (byte)(streamId >> 8); payload[10] = (byte)streamId;
        payload[11] = 0x17; payload[12] = 0x00; payload[13] = 0x00; payload[14] = 0x00; payload[15] = 0x04;
        payload[16] = 0x00; payload[17] = 0x00; payload[18] = 0x00; payload[19] = 0x00;
        SendRequest(0x4C4, payload);
    }

    void SendRequest(uint opcode, byte[] payload)
    {
        uint seq = ++_seq;
        byte[] frame = new byte[8 + 24 + payload.Length];
        frame[0] = 0x00;
        WriteU32LE(frame, 4, (uint)(24 + payload.Length));
        frame[8] = 0x51;
        WriteU32BE(frame, 12, seq);
        WriteU32BE(frame, 20, opcode);
        WriteU32BE(frame, 28, (uint)payload.Length);
        Array.Copy(payload, 0, frame, 32, payload.Length);
        WinUsb_WritePipe(_usbHandle, _outEp, frame, (uint)frame.Length, out _, IntPtr.Zero);
    }

    byte[] ReadResponse()
    {
        byte[] buf = new byte[16384];
        if (WinUsb_ReadPipe(_usbHandle, _inEp, buf, (uint)buf.Length, out uint xfer, IntPtr.Zero))
        {
            byte[] result = new byte[xfer];
            Array.Copy(buf, result, xfer);
            return result;
        }
        return Array.Empty<byte>();
    }

    static uint ReadU32BE(byte[] d, int o) => o + 4 <= d.Length ? (uint)(d[o] << 24 | d[o + 1] << 16 | d[o + 2] << 8 | d[o + 3]) : 0;

    // Signed Q42 (TLV type 4): 8-byte big-endian SIGNED int / 2^42.
    // The old code zero-extended the high word ((long)uint << 32), which
    // decodes any negative value (e.g. left display corners, x < 0) as a huge
    // positive number. Gaze column 0x1c is always in [0,1] so it happened to
    // work, but the helper is required for display-area readback and any
    // future column. Reference: tobiifree driver/src/tlv.zig readFixed22x42.
    static double ReadQ42Signed(byte[] d, int o)
    {
        if (o + 8 > d.Length) return 0;
        long v = ((long)(int)ReadU32BE(d, o) << 32) | ReadU32BE(d, o + 4);
        return v / Q42_SCALE;
    }
    static void WriteU32BE(byte[] d, int o, uint v) { d[o] = (byte)(v >> 24); d[o + 1] = (byte)(v >> 16); d[o + 2] = (byte)(v >> 8); d[o + 3] = (byte)v; }
    static void WriteU32LE(byte[] d, int o, uint v) { d[o] = (byte)v; d[o + 1] = (byte)(v >> 8); d[o + 2] = (byte)(v >> 16); d[o + 3] = (byte)(v >> 24); }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        StopTracking();
        if (_usbHandle != IntPtr.Zero && _usbHandle != new IntPtr(-1))
        {
            var setup = new WINUSB_SETUP_PACKET { RequestType = 0x41, Request = 0x42 };
            WinUsb_ControlTransfer(_usbHandle, setup, Array.Empty<byte>(), 0, out _, IntPtr.Zero);
            WinUsb_Free(_usbHandle);
        }
        if (_devHandle != IntPtr.Zero && _devHandle != new IntPtr(-1))
            CloseHandle(_devHandle);
        OnConnectionChanged?.Invoke(false);
    }
}
