#!/usr/bin/env python3
import argparse
import struct
import re
import os
from pathlib import Path

def read_rating(path: Path) -> int:
    """Reads star rating from JPEG metadata (EXIF or XMP)."""
    def pct_to_stars(pct):
        if pct <= 0: return 0
        if pct <= 1: return 1
        if pct <= 25: return 2
        if pct <= 50: return 3
        if pct <= 75: return 4
        return 5

    rating_exif = None
    rating_xmp = None

    try:
        data = path.read_bytes()
        i = 2  # skip SOI
        while i + 3 < len(data):
            b0, b1 = data[i], data[i + 1]
            if b0 != 0xFF: break
            if b1 in (0xD8, 0xD9, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
                i += 2
                continue
            if b1 == 0xDA: break # Start of Scan
            seg_len = (data[i + 2] << 8) | data[i + 3]
            if seg_len < 2: break
            payload = data[i + 4: i + 2 + seg_len]

            # Check EXIF
            if b1 == 0xE1 and payload[:6] == b"Exif\x00\x00":
                try:
                    tiff = payload[6:]
                    bo = "<" if tiff[:2] == b"II" else ">"
                    ifd0_off = struct.unpack_from(bo + "I", tiff, 4)[0]
                    n = struct.unpack_from(bo + "H", tiff, ifd0_off)[0]
                    for e in range(min(n, 128)):
                        eoff = ifd0_off + 2 + e * 12
                        tag, _, _, val = struct.unpack_from(bo + "HHII", tiff, eoff)
                        if tag == 0x4746: rating_exif = val & 0xFFFF
                        elif tag == 0x4749 and rating_exif is None:
                            rating_exif = pct_to_stars(val & 0xFFFF)
                except: pass

            # Check XMP
            elif b1 == 0xE1 and b"http://ns.adobe.com/xap" in payload[:64]:
                try:
                    xmp = payload.decode("utf-8", errors="replace")
                    m = re.search(r"<xmp:Rating>\s*([-\d]+)\s*</xmp:Rating>", xmp)
                    if not m: m = re.search(r'xmp:Rating\s*=\s*"([-\d]+)"', xmp)
                    if m: rating_xmp = int(m.group(1))
                except: pass
            i += 2 + seg_len
    except: pass

    res = rating_exif if rating_exif is not None else (rating_xmp if rating_xmp is not None else 0)
    return max(0, min(5, res))

def main():
    parser = argparse.ArgumentParser(description="Delete JPEGs with a 1-star rating.")
    parser.add_argument("-d", "--directory", required=True, help="Directory to scan recursively")
    args = parser.parse_args()

    root_dir = Path(args.directory)
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"[ERROR] Directory not found: {args.directory}")
        return

    print(f"Scanning: {root_dir}...")
    deleted_count = 0
    
    for p in root_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}:
            if read_rating(p) == 1:
                print(f"DELETING: {p.name} (1-star)")
                try:
                    p.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f" [!] Failed to delete {p.name}: {e}")

    print(f"\nDone. Deleted {deleted_count} files.")

if __name__ == "__main__":
    main()