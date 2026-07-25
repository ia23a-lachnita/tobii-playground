import hid

devices = hid.enumerate()
for d in devices:
    vid = d.get('vendor_id', 0)
    pid = d.get('product_id', 0)
    if vid == 0x2104:
        print(f"VID={vid:04x} PID={pid:04x} usage_page={d.get('usage_page')} usage={d.get('usage')}")
        print(f"  product: {d.get('product_string', '')}")
        print(f"  manufacturer: {d.get('manufacturer_string', '')}")
        print(f"  path: {d.get('path', '')}")
        print()

# Also check for any HID devices that might be the EyeChip
print("All HID devices:")
for d in devices:
    vid = d.get('vendor_id', 0)
    pid = d.get('product_id', 0)
    usage_page = d.get('usage_page', 0)
    usage = d.get('usage', 0)
    if vid != 0:
        print(f"  VID={vid:04x} PID={pid:04x} UP={usage_page:04x} U={usage:04x} product={d.get('product_string', '')[:30]}")
