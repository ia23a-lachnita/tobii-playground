import hid
import usb.core
import usb.util

# Tobii 5-family USB IDs (verified): Eye Tracker 5 runtime = 2104:0313
# (tobiifree device table), 5L variant = 2104:0314 (this unit's device path).
# 0x0525 was never a Tobii PID and matched nothing — fixed.
TOBII_VID = 0x2104
TOBII_PIDS = (0x0313, 0x0314)

# Check HID
devices = hid.enumerate()
for d in devices:
    if d['vendor_id'] == TOBII_VID and d['product_id'] in TOBII_PIDS:
        print(f"VID: {d['vendor_id']:04x} PID: {d['product_id']:04x}")
        print(f"Product: {d['product_string']}")
        print(f"Manufacturer: {d['manufacturer_string']}")
        print(f"Serial: {d['serial_number']}")
        print(f"Usage: {d['usage_page']:04x} / {d['usage']:04x}")
        print(f"Interface: {d['interface_number']}")
        print(f"Path: {d['path']}")
        print()

# Try pyusb
print("--- pyusb ---")
dev = None
for pid in TOBII_PIDS:
    dev = usb.core.find(idVendor=TOBII_VID, idProduct=pid)
    if dev is not None:
        break
if dev is None:
    # legacy fallback VID seen in older snippets
    dev = usb.core.find(idVendor=0x2171, idProduct=0x0525)
if dev is None:
    print("Device not found via pyusb")
else:
    print(f"Found: {dev.idVendor:04x}:{dev.idProduct:04x}")
    print(f"Manufacturer: {dev.manufacturer}")
    print(f"Product: {dev.product}")
    print(f"Serial: {dev.serial_number}")
    print(f"Configurations: {dev.bNumConfigurations}")
    for cfg in dev:
        print(f"  Config {cfg.bConfigurationValue}:")
        for intf in cfg:
            print(f"    Interface {intf.bInterfaceNumber}:")
            print(f"      Class: {intf.bInterfaceClass}")
            print(f"      SubClass: {intf.bInterfaceSubClass}")
            print(f"      Endpoints:")
            for ep in intf:
                ep_type = {0: 'Control', 1: 'Isochronous', 2: 'Bulk', 3: 'Interrupt'}
                direction = 'IN' if ep.bEndpointAddress & 0x80 else 'OUT'
                print(f"        EP {ep.bEndpointAddress:02x} ({direction}) {ep_type.get(ep.bmAttributes, '?')} max={ep.wMaxPacketSize}")
