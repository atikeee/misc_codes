#!/usr/bin/env python3
"""
move_raw.py  –  Move RAW files to a 'raw' subfolder based on JPEG star rating.

Scans a directory tree for JPEG files rated 3 stars.
For each 3-star JPEG found, moves the matching RAW file (same base name,
any RAW extension) from the SAME folder into a 'raw' subdirectory there.

Usage
-----
  python move_raw.py C:\\path\\to\\photos
  python move_raw.py C:\\path\\to\\photos --dry-run

Notes
-----
- Processes one directory at a time (groups files by parent folder).
- Only moves the RAW file – the JPEG stays in place.
- Creates the 'raw' subfolder automatically if needed.
- Skips if the destination file already exists.
- --dry-run shows what would happen without touching anything.
"""

from __future__ import annotations

import argparse
import logging
import re
import struct
import sys
from pathlib import Path

# ── RAW extensions to look for ───────────────────────────────────────────────

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng",
    ".orf", ".rw2", ".raf", ".pef", ".ptx", ".3fr", ".mef", ".mrw",
    ".x3f", ".erf", ".rwl", ".srw", ".kdc", ".dcr",
}

# ── logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ── rating reader (same logic as raw2jpg.py) ─────────────────────────────────

def read_rating(path: Path) -> int:
    """
    Read star rating from a JPEG.  Checks:
      1. EXIF IFD0 tag 0x4746 (Rating, 0-5 direct)
      2. EXIF IFD0 tag 0x4749 (RatingPercent -> stars)
      3. XMP <xmp:Rating>N</xmp:Rating>
      4. XMP xmp:Rating="N"
      5. XMP <MicrosoftPhoto:Rating>N</MicrosoftPhoto:Rating>

    Scans ALL markers (not just APPn) because XnView MP places
    the XMP block after DQT markers.
    """
    rating_exif = None
    rating_xmp  = None

    def pct_to_stars(pct):
        if pct <= 0:  return 0
        if pct <= 1:  return 1
        if pct <= 25: return 2
        if pct <= 50: return 3
        if pct <= 75: return 4
        return 5

    try:
        data = path.read_bytes()
        i = 2  # skip SOI

        while i + 3 < len(data):
            b0, b1 = data[i], data[i + 1]
            if b0 != 0xFF:
                break
            if b1 in (0xD8, 0xD9, 0xD0, 0xD1, 0xD2,
                      0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
                i += 2
                continue
            if b1 == 0xDA:   # SOS – image data starts
                break
            seg_len = (data[i + 2] << 8) | data[i + 3]
            if seg_len < 2:
                break
            payload = data[i + 4: i + 2 + seg_len]

            # EXIF APP1
            if b1 == 0xE1 and payload[:6] == b"Exif\x00\x00":
                try:
                    tiff = payload[6:]
                    bo = "<" if tiff[:2] == b"II" else ">"
                    ifd0_off = struct.unpack_from(bo + "I", tiff, 4)[0]
                    n = struct.unpack_from(bo + "H", tiff, ifd0_off)[0]
                    for e in range(min(n, 128)):
                        eoff = ifd0_off + 2 + e * 12
                        if eoff + 12 > len(tiff):
                            break
                        tag, _, _, val = struct.unpack_from(bo + "HHII", tiff, eoff)
                        if tag == 0x4746:
                            rating_exif = val & 0xFFFF
                        elif tag == 0x4749 and rating_exif is None:
                            rating_exif = pct_to_stars(val & 0xFFFF)
                except Exception:
                    pass

            # XMP APP1
            elif b1 == 0xE1 and b"http://ns.adobe.com/xap" in payload[:64]:
                try:
                    xmp = payload.decode("utf-8", errors="replace")
                    m = re.search(r"<xmp:Rating>\s*([-\d]+)\s*</xmp:Rating>", xmp)
                    if m:
                        rating_xmp = int(m.group(1))
                    if rating_xmp is None:
                        m = re.search(r'xmp:Rating\s*=\s*"([-\d]+)"', xmp)
                        if m:
                            rating_xmp = int(m.group(1))
                    if rating_xmp is None:
                        m = re.search(r"xmp:Rating\s*=\s*'([-\d]+)'", xmp)
                        if m:
                            rating_xmp = int(m.group(1))
                    if rating_xmp is None:
                        m = re.search(
                            r"<MicrosoftPhoto:Rating>\s*(\d+)\s*</MicrosoftPhoto:Rating>",
                            xmp)
                        if m:
                            rating_xmp = pct_to_stars(int(m.group(1)))
                except Exception:
                    pass

            i += 2 + seg_len

    except Exception as exc:
        logging.debug("read_rating %s: %s", path.name, exc)

    if rating_exif is not None:
        rating = rating_exif
    elif rating_xmp is not None:
        rating = rating_xmp
    else:
        rating = 0

    return max(0, min(5, rating))


# ── core logic ────────────────────────────────────────────────────────────────

def process_directory(folder: Path, dry_run: bool) -> dict[str, int]:
    """
    Scan *folder* (non-recursive – called once per directory).
    Find all JPEGs rated 3 stars, then move matching RAW files to 'raw/'.
    Returns counts dict.
    """
    counts = {"moved": 0, "missing_raw": 0, "skipped": 0}

    # Build a quick lookup: lowercase stem -> list of RAW paths in this folder
    raw_by_stem: dict[str, list[Path]] = {}
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in RAW_EXTENSIONS:
            raw_by_stem.setdefault(f.stem.lower(), []).append(f)

    # Find JPEGs rated exactly 3 stars
    three_star_jpegs: list[Path] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        rating = read_rating(f)
        logging.debug("  %s  rating=%d", f.name, rating)
        if rating == 3:
            three_star_jpegs.append(f)

    if not three_star_jpegs:
        return counts

    logging.info("  %s  →  %d file(s) rated 3★", folder, len(three_star_jpegs))

    # For each 3-star JPEG, move the matching RAW
    for jpg in three_star_jpegs:
        stem = jpg.stem.lower()
        raws = raw_by_stem.get(stem, [])

        if not raws:
            logging.warning("  NO RAW  %-40s  (no matching RAW file found)", jpg.name)
            counts["missing_raw"] += 1
            continue

        raw_dir = folder / "raw"

        for raw_file in raws:
            dest = raw_dir / raw_file.name
            if dest.exists():
                logging.info("  SKIP    %s  (already in raw/)", raw_file.name)
                counts["skipped"] += 1
                continue

            if dry_run:
                logging.info("  DRY-RUN  would move  %s  →  raw/", raw_file.name)
                counts["moved"] += 1
            else:
                raw_dir.mkdir(exist_ok=True)
                raw_file.rename(dest)
                logging.info("  MOVED   %s  →  %s/raw/", raw_file.name, folder.name)
                counts["moved"] += 1

    return counts


def run(root: Path, dry_run: bool) -> None:
    if not root.is_dir():
        logging.error("Not a directory: %s", root)
        sys.exit(1)

    if dry_run:
        logging.info("DRY-RUN mode – no files will be moved")

    # Collect all unique directories that contain at least one JPEG
    dirs_with_jpegs: set[Path] = set()
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg"}:
            # skip files already inside a 'raw' subfolder
            if "raw" not in [p.name.lower() for p in f.parents]:
                dirs_with_jpegs.add(f.parent)

    if not dirs_with_jpegs:
        logging.warning("No JPEG files found under %s", root)
        return

    logging.info("Found %d folder(s) to scan", len(dirs_with_jpegs))

    total = {"moved": 0, "missing_raw": 0, "skipped": 0}
    for folder in sorted(dirs_with_jpegs):
        counts = process_directory(folder, dry_run)
        for k in total:
            total[k] += counts[k]

    logging.info("")
    action = "Would move" if dry_run else "Moved"
    logging.info("Done  %s=%d  missing_raw=%d  skipped=%d",
                 action, total["moved"], total["missing_raw"], total["skipped"])


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Move RAW files to raw/ subfolder when matching JPEG is rated 3 stars.",
        epilog="""
Examples
  python move_raw.py C:\\photos
  python move_raw.py C:\\photos --dry-run
        """,
    )
    p.add_argument("directory", help="Root directory to scan recursively")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be moved without actually moving anything")
    args = p.parse_args()
    run(Path(args.directory), args.dry_run)


if __name__ == "__main__":
    main()