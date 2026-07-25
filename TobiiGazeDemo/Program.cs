using System;
using System.Runtime.InteropServices;
using System.Threading;

class TobiiGazeDirect
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
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr CreateFile(string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition, uint dwFlagsAndAttributes, IntPtr hTemplateFile);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr hObject);

    [StructLayout(LayoutKind.Sequential)]
    struct SP_DEVICE_INTERFACE_DATA { public int cbSize; public Guid InterfaceClassGuid; public int Flags; public IntPtr Reserved; }
    [StructLayout(LayoutKind.Sequential)]
    struct WINUSB_SETUP_PACKET { public byte RequestType; public byte Request; public ushort Value; public ushort Index; public ushort Length; }

    static Guid WINUSB_GUID = new Guid("85C0F97C-E2B1-422A-92A9-5F96072E79D8");
    static IntPtr _usbHandle;
    static byte _outEp = 0x05, _inEp = 0x83;
    static uint _seq = 0;
    static uint _gazeCount = 0;
    static uint _lastValidL = 99, _lastValidR = 99;

    // Q42 fixed-point constants
    const double Q42_SCALE = 4398046511104.0; // 2^42

    static void Main()
    {
        Console.WriteLine("Tobii Eye Tracker 5L - Direct USB Gaze (v4)");
        Console.WriteLine("=============================================");
        Console.WriteLine();

        if (!OpenDevice()) { Console.WriteLine("Failed to open device"); return; }

        // Session Open
        Console.WriteLine("[1] Session Open...");
        var setup = new WINUSB_SETUP_PACKET { RequestType = 0x41, Request = 0x41 };
        uint xfer;
        WinUsb_ControlTransfer(_usbHandle, setup, null, 0, out xfer, IntPtr.Zero);

        // HELLO with stream IDs 0x0001..0x0008 (same as tobiifree)
        Console.WriteLine("[2] HELLO...");
        SendRequest(0x3E8, new byte[] {
            0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x09,
            0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00,
            0x02, 0x00, 0x01, 0x00, 0x03, 0x00, 0x01, 0x00, 0x04, 0x00, 0x01,
            0x00, 0x05, 0x00, 0x01, 0x00, 0x06, 0x00, 0x01, 0x00, 0x07, 0x00,
            0x01, 0x00, 0x08 });
        var rsp = ReadResponse();
        Console.WriteLine($"  RSP: op=0x{ReadU32BE(rsp, 20):X4} plen={ReadU32BE(rsp, 28)}");

        // Query realm
        Console.WriteLine("\n[3] QUERY_REALM...");
        SendRequest(0x640, new byte[] { 0x00, 0x00 });
        rsp = ReadResponse();
        Console.WriteLine($"  realm_type=0");

        // GET current display area
        Console.WriteLine("\n[4] GET_DISPLAY_AREA...");
        SendRequest(0x596, Array.Empty<byte>());
        rsp = ReadResponse();
        uint daPlen = ReadU32BE(rsp, 28);
        Console.WriteLine($"  plen={daPlen}");
        if (daPlen > 0)
            Console.WriteLine($"  data={Hex(rsp, 32, 160)}");

        // SET display area for a 24" 16:9 monitor (531mm x 299mm)
        // Tracker center is at (0,0,0), display corners in mm
        Console.WriteLine("\n[5] SET_DISPLAY_AREA (24in 16:9)...");
        SetDisplayArea(531.0, 299.0, -265.5, -149.5, 0.0);

        // Read it back to confirm
        Console.WriteLine("\n[6] GET_DISPLAY_AREA (after set)...");
        SendRequest(0x596, Array.Empty<byte>());
        rsp = ReadResponse();
        daPlen = ReadU32BE(rsp, 28);
        Console.WriteLine($"  plen={daPlen}");
        if (daPlen > 0)
        {
            // Try to decode the corners
            int pos = 34; // skip 2 mystery bytes
            if (pos + 48 <= rsp.Length)
            {
                double tlX = ReadQ42(rsp, pos); pos += 13;
                double tlY = ReadQ42(rsp, pos); pos += 13;
                double tlZ = ReadQ42(rsp, pos); pos += 13;
                Console.WriteLine($"  TL=({tlX:F1},{tlY:F1},{tlZ:F1})mm");
            }
            if (pos + 39 <= rsp.Length)
            {
                double trX = ReadQ42(rsp, pos); pos += 13;
                double trY = ReadQ42(rsp, pos); pos += 13;
                double trZ = ReadQ42(rsp, pos); pos += 13;
                Console.WriteLine($"  TR=({trX:F1},{trY:F1},{trZ:F1})mm");
            }
            if (pos + 39 <= rsp.Length)
            {
                double blX = ReadQ42(rsp, pos); pos += 13;
                double blY = ReadQ42(rsp, pos); pos += 13;
                double blZ = ReadQ42(rsp, pos); pos += 13;
                Console.WriteLine($"  BL=({blX:F1},{blY:F1},{blZ:F1})mm");
            }
        }

        // Subscribe to gaze_point (0x0500)
        Console.WriteLine("\n[7] SUBSCRIBE gaze_point (0x0500)...");
        SendSubscribe(0x0500);
        rsp = ReadResponse();
        Console.WriteLine($"  RSP: op=0x{ReadU32BE(rsp, 20):X4} plen={ReadU32BE(rsp, 28)}");

        // Read gaze - run for 90 seconds
        Console.WriteLine("\n[8] Reading gaze (90s)...");
        Console.WriteLine("    Sit 40-80cm from tracker, look directly at it.");
        Console.WriteLine("    Move your head slowly left/right, up/down.\n");
        var startTime = DateTime.Now;
        int totalNotify = 0;
        int validFrames = 0;
        while (DateTime.Now - startTime < TimeSpan.FromSeconds(90))
        {
            byte[] buf = new byte[16384];
            uint xferBytes;
            bool ok = WinUsb_ReadPipe(_usbHandle, _inEp, buf, (uint)buf.Length, out xferBytes, IntPtr.Zero);
            if (!ok || xferBytes == 0)
            {
                int err = Marshal.GetLastWin32Error();
                if (err == 0) continue;
                break;
            }

            uint magic = ReadU32BE(buf, 8);
            uint op = ReadU32BE(buf, 20);
            uint plen = ReadU32BE(buf, 28);

            if (magic == 0x53 && op == 0x500 && plen > 0)
            {
                _gazeCount++;
                ParseGazeTLV(buf, 32, (int)Math.Min(plen, (uint)(xferBytes - 32)));
            }
            else if (magic == 0x53)
            {
                totalNotify++;
                if (totalNotify <= 3)
                    Console.WriteLine($"  NOTIFY op=0x{op:X4} plen={plen}");
            }
        }

        Console.WriteLine($"\nDone. Gaze samples: {_gazeCount}, valid frames: {validFrames}");
        setup = new WINUSB_SETUP_PACKET { RequestType = 0x41, Request = 0x42 };
        WinUsb_ControlTransfer(_usbHandle, setup, null, 0, out xfer, IntPtr.Zero);
        WinUsb_Free(_usbHandle);
        CloseHandle(_usbHandle);
    }

    static void SetDisplayArea(double w, double h, double ox, double oy, double z)
    {
        // Build set_display_area payload: [00 00][point TL][point TR][point BL][end marker]
        byte[] payload = new byte[256];
        int n = 0;
        payload[n++] = 0x00; payload[n++] = 0x00;

        // TL corner
        n += WritePoint3D(payload, n, ox, oy + h, z);
        // TR corner
        n += WritePoint3D(payload, n, ox + w, oy + h, z);
        // BL corner
        n += WritePoint3D(payload, n, ox, oy, z);

        // End marker: tag(0x10100) + u32(0x3039)
        payload[n++] = 0x05; // TLV type = prolog
        payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x04; // size
        WriteU32BE(payload, n, 0x010100); n += 4;
        payload[n++] = 0x02; // TLV type = u32
        payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x00; payload[n++] = 0x04;
        WriteU32BE(payload, n, 0x3039); n += 4;

        byte[] trimmed = new byte[n];
        Array.Copy(payload, trimmed, n);
        SendRequest(0x5A0, trimmed);
        var rsp = ReadResponse();
        Console.WriteLine($"  SET response: op=0x{ReadU32BE(rsp, 20):X4} plen={ReadU32BE(rsp, 28)}");
    }

    static int WritePoint3D(byte[] buf, int offset, double x, double y, double z)
    {
        int n = offset;
        // prolog: [type=5][size=4][tag=0x031F41]
        buf[n++] = 0x05;
        buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x04;
        WriteU32BE(buf, n, 0x031F41); n += 4;
        // x Q42
        n += WriteQ42(buf, n, x);
        // y Q42
        n += WriteQ42(buf, n, y);
        // z Q42
        n += WriteQ42(buf, n, z);
        return n - offset;
    }

    static int WriteQ42(byte[] buf, int offset, double value)
    {
        int n = offset;
        buf[n++] = 0x04; // TLV type = Q42
        buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x00; buf[n++] = 0x08; // size
        long scaled = (long)Math.Round(value * Q42_SCALE);
        buf[n++] = (byte)(scaled >> 56);
        buf[n++] = (byte)(scaled >> 48);
        buf[n++] = (byte)(scaled >> 40);
        buf[n++] = (byte)(scaled >> 32);
        buf[n++] = (byte)(scaled >> 24);
        buf[n++] = (byte)(scaled >> 16);
        buf[n++] = (byte)(scaled >> 8);
        buf[n++] = (byte)scaled;
        return n - offset;
    }

    static double ReadQ42(byte[] d, int o)
    {
        if (o + 13 > d.Length) return 0;
        if (d[o] != 0x04) return 0;
        long v = ((long)d[o + 5] << 56) | ((long)d[o + 6] << 48) | ((long)d[o + 7] << 40) | ((long)d[o + 8] << 32)
               | ((long)d[o + 9] << 24) | ((long)d[o + 10] << 16) | ((long)d[o + 11] << 8) | d[o + 12];
        return v / Q42_SCALE;
    }

    static void SendSubscribe(uint streamId)
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

    static bool OpenDevice()
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
                devicePath = Marshal.PtrToStringAuto(detailBuf + 4);
            Marshal.FreeHGlobal(detailBuf);
        }
        SetupDiDestroyDeviceInfoList(devInfo);
        if (devicePath == null) return false;
        Console.WriteLine($"Device: {devicePath}");
        IntPtr devHandle = CreateFile(devicePath, 0xC0000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        if (devHandle == new IntPtr(-1)) { Console.WriteLine($"CreateFile error: {Marshal.GetLastWin32Error()}"); return false; }
        if (!WinUsb_Initialize(devHandle, out _usbHandle)) { Console.WriteLine($"WinUsb_Initialize error: {Marshal.GetLastWin32Error()}"); CloseHandle(devHandle); return false; }
        Console.WriteLine($"Endpoints: OUT=0x{_outEp:X2} IN=0x{_inEp:X2}");
        return true;
    }

    static void SendRequest(uint opcode, byte[] payload)
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
        uint xfer;
        WinUsb_WritePipe(_usbHandle, _outEp, frame, (uint)frame.Length, out xfer, IntPtr.Zero);
    }

    static byte[] ReadResponse()
    {
        byte[] buf = new byte[16384];
        uint xfer;
        if (WinUsb_ReadPipe(_usbHandle, _inEp, buf, (uint)buf.Length, out xfer, IntPtr.Zero))
        {
            byte[] result = new byte[xfer];
            Array.Copy(buf, result, xfer);
            return result;
        }
        return Array.Empty<byte>();
    }

    static uint ReadU32BE(byte[] d, int o) => o + 4 <= d.Length ? (uint)(d[o] << 24 | d[o + 1] << 16 | d[o + 2] << 8 | d[o + 3]) : 0;
    static void WriteU32BE(byte[] d, int o, uint v) { d[o] = (byte)(v >> 24); d[o + 1] = (byte)(v >> 16); d[o + 2] = (byte)(v >> 8); d[o + 3] = (byte)v; }
    static void WriteU32LE(byte[] d, int o, uint v) { d[o] = (byte)v; d[o + 1] = (byte)(v >> 8); d[o + 2] = (byte)(v >> 16); d[o + 3] = (byte)(v >> 24); }
    static string Hex(byte[] data, int offset, int length = 48)
    {
        int end = Math.Min(offset + length, data.Length);
        var sb = new System.Text.StringBuilder();
        for (int i = offset; i < end; i++) sb.Append($"{data[i]:X2} ");
        return sb.ToString().Trim();
    }

    static void ParseGazeTLV(byte[] buf, int payloadStart, int payloadLen)
    {
        int pos = payloadStart;
        int end = Math.Min(payloadStart + payloadLen, buf.Length);
        if (pos + 2 > end) return;
        pos += 2;

        if (pos + 9 > end) return;
        if (buf[pos] != 0x05) return;
        pos += 5;
        uint rowTag = ReadU32BE(buf, pos); pos += 4;
        int colCount = (int)((rowTag >> 16) & 0xFFF);

        var cols = new System.Collections.Generic.Dictionary<uint, object>();
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
                    cols[colId] = ReadU32BE(buf, pos); pos += 4;
                    break;
                case 3: // fixed16x16
                    if (pos + 9 > end) goto done;
                    pos += 5;
                    cols[colId] = (double)((int)ReadU32BE(buf, pos)) / 65536.0; pos += 4;
                    break;
                case 4: // Q42
                    if (pos + 13 > end) goto done;
                    pos += 5;
                    long qv = ((long)ReadU32BE(buf, pos) << 32) | ReadU32BE(buf, pos + 4); pos += 8;
                    cols[colId] = qv / Q42_SCALE;
                    break;
                case 5: // prolog (struct)
                    if (pos + 9 > end) goto done;
                    pos += 5;
                    uint structTag = ReadU32BE(buf, pos); pos += 4;
                    if (structTag == 0x021F40) // point2d
                    {
                        if (pos + 26 > end) goto done;
                        pos += 5; double px = ((long)ReadU32BE(buf, pos) << 32 | ReadU32BE(buf, pos + 4)) / Q42_SCALE; pos += 8;
                        pos += 5; double py = ((long)ReadU32BE(buf, pos) << 32 | ReadU32BE(buf, pos + 4)) / Q42_SCALE; pos += 8;
                        cols[colId] = new double[] { px, py };
                    }
                    else if (structTag == 0x031F41) // point3d
                    {
                        if (pos + 39 > end) goto done;
                        pos += 5; double p3x = ((long)ReadU32BE(buf, pos) << 32 | ReadU32BE(buf, pos + 4)) / Q42_SCALE; pos += 8;
                        pos += 5; double p3y = ((long)ReadU32BE(buf, pos) << 32 | ReadU32BE(buf, pos + 4)) / Q42_SCALE; pos += 8;
                        pos += 5; double p3z = ((long)ReadU32BE(buf, pos) << 32 | ReadU32BE(buf, pos + 4)) / Q42_SCALE; pos += 8;
                        cols[colId] = new double[] { p3x, p3y, p3z };
                    }
                    else goto done;
                    break;
                case 6: // s64
                    if (pos + 13 > end) goto done;
                    pos += 5;
                    cols[colId] = (double)(((long)ReadU32BE(buf, pos) << 32) | ReadU32BE(buf, pos + 4)); pos += 8;
                    break;
                default: goto done;
            }
        }
        done:

        uint vL = cols.ContainsKey(0x07) ? Convert.ToUInt32(cols[0x07]) : 99;
        uint vR = cols.ContainsKey(0x0d) ? Convert.ToUInt32(cols[0x0d]) : 99;
        uint trackL = cols.ContainsKey(0x26) ? Convert.ToUInt32(cols[0x26]) : 0;
        uint trackR = cols.ContainsKey(0x28) ? Convert.ToUInt32(cols[0x28]) : 0;

        // Print every frame where something changes, or first 10, or every 500th
        bool changed = vL != _lastValidL || vR != _lastValidR;
        if (changed || _gazeCount <= 10 || (_gazeCount % 500 == 0))
        {
            Console.Write($"  #{_gazeCount,5} vL={vL} vR={vR}");
            if (cols.ContainsKey(0x14)) Console.Write($" frame={cols[0x14]}");
            if (trackL == 1 && cols.ContainsKey(0x25))
            {
                var p = (double[])cols[0x25];
                Console.Write($"  L_pos=({p[0]:F3},{p[1]:F3},{p[2]:F3})");
            }
            if (trackR == 1 && cols.ContainsKey(0x27))
            {
                var p = (double[])cols[0x27];
                Console.Write($"  R_pos=({p[0]:F3},{p[1]:F3},{p[2]:F3})");
            }
            if (vL == 0 && cols.ContainsKey(0x05))
            {
                var p = (double[])cols[0x05];
                Console.Write($"  GAZE_L=({p[0]:F4},{p[1]:F4})");
            }
            if (vR == 0 && cols.ContainsKey(0x0b))
            {
                var p = (double[])cols[0x0b];
                Console.Write($"  GAZE_R=({p[0]:F4},{p[1]:F4})");
            }
            if (cols.ContainsKey(0x1c) && cols[0x1c] is double[] g && g[0] > -0.5)
                Console.Write($"  GAZE=({g[0]:F4},{g[1]:F4})");
            Console.WriteLine();
            _lastValidL = vL;
            _lastValidR = vR;
        }
    }
}
