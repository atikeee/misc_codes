import re, struct, sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
print(f"File size: {len(data):,}")

i = 2
step = 0
while i + 3 < len(data):
    b0, b1 = data[i], data[i+1]
    step += 1
    print(f"  step={step} offset={i:#06x} marker=0xFF{b1:02X}", end="")
    if b0 != 0xFF:
        print(f"  STOP: b0=0x{b0:02X} not 0xFF"); break
    if b1 in (0xD8,0xD9,0xD0,0xD1,0xD2,0xD3,0xD4,0xD5,0xD6,0xD7):
        print("  (no-length marker, skip 2)"); i += 2; continue
    if b1 == 0xDA:
        print("  SOS – stop"); break
    seg_len = (data[i+2] << 8) | data[i+3]
    payload  = data[i+4: i+2+seg_len]
    print(f"  seg_len={seg_len}  payload[:8]={payload[:8].hex()}", end="")

    if b1 == 0xE1 and b"http://ns.adobe.com/xap" in payload[:64]:
        print("  --> XMP FOUND")
        xmp = payload.decode("utf-8", errors="replace")
        m = re.search(r"<xmp:Rating>\s*([-\d]+)\s*</xmp:Rating>", xmp)
        print(f"     element regex: {m}")
        m2 = re.search(r'xmp:Rating\s*=\s*"([-\d]+)"', xmp)
        print(f"     attribute regex: {m2}")
        # show raw bytes around Rating
        idx = payload.find(b"Rating")
        print(f"     raw around Rating: {payload[max(0,idx-5):idx+30]!r}")
    elif b1 == 0xE1 and payload[:6] == b"Exif\x00\x00":
        print("  --> EXIF")
    else:
        print()

    i += 2 + seg_len